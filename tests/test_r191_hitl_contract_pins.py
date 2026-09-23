"""R191 · 契约里 HITL 那一节必须与 chat.py 的构造点同源（全离线：不起服务、不连库、不打模型）。

R175（并树 36e512a）给 ``GET /hitl/pending`` 加了两枚字段（``failed_turns[]`` 与
``failed_turns_has_more``）和一枚终态（``failed``），却一字未动 ``docs/api/contract-v1.md`` ——
那枚文件是前端的唯一真相源。R191 补写了那一节（甲半），本文件钉的是**补的那一节不许漂**。

手法照 ``tests/test_r186_row_scope_contract.py``（借方法，不借断言）：散文里不许出现手抄的形状。

  ① 三处键集合全部用 AST 从 ``app/api/v1/chat.py::hitl_pending`` 现抠 —— 那枚 ``return`` dict（信封）、
     ``items.append({...})`` 里那个 dict、``failed_turns`` 推导式里那个 dict —— 与契约的两枚键表以及节首
     那块 Shape 速记**双向**对判：文档多列一枚（替后端开洞）与少列一枚（前端无从可读）都红；
     「``labels`` 是两枚元素形状的唯一差别」这条裁决也由代码来当，不由散文来当；
  ② 取值域五行（``status`` / ``items[].status`` / ``failed_turns[].status`` / ``DECIDED_STATUSES`` /
     ``pending_approvals_status_check``）逐枚与 ``app/storage/pending_approvals.py`` 的常量对判，常量
     再解回模块级字面量；两腿各自传给 ``_items_with_status`` 的那一枚状态也现抠；
  ③ 契约里那几条**行为**裁决不许只写在散文里：两腿各自 over-fetch ``limit + 1``、``count`` 就是
     ``len(items)``、两枚 ``*_has_more`` 由同一算法算出、归属过滤两腿同一个表达式（fail-closed）、
     🔴 以及「``offset`` 不移动失败那一腿」（``failed_items`` 的 offset 实参恒为字面量 ``0``）；
  ④ 端点路径从装饰器与 ``app/main.py`` 的 prefix 现算，两枚小节标题必须把路径与字段绑在同一行上；
  ⑤ 🔴 **PG 缺口那一段是本文件的引信**：只要代码侧仍报缺口（``ALL_STATUSES - PG_STATUSES`` 非空），
     契约就必须明写「PG 今天存不下 ``failed``、那一行留在 ``awaiting``」。R190 把那枚 CHECK 放开之后
     本文件**必须红一次**，逼写文档的人回来改那一段 —— 那不是回归，恰恰是这枚引信存在的目的。
     缺口今天还在的第三条证据不收散文：``migrations/0008_pending_approvals.sql`` 的 CHECK 文本与
     ``PG_STATUSES`` 必须是同一枚集合，且按文件名序取**最后一条**重定义（R190 的新脚本会盖掉 0008）。

判据⑤(b) 的反证路径：把契约里 ``**🔴 The PG gap`` 那一段删掉 ⇒
``test_the_contract_states_the_pg_gap_while_the_gap_exists`` 具名红；把
``pending_approvals_status_check accepts:`` 那一行删掉 ⇒
``test_documented_status_domains_match_the_code_constants`` 具名红。
"""
from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT_PY = ROOT / "app" / "api" / "v1" / "chat.py"
STORE_PY = ROOT / "app" / "storage" / "pending_approvals.py"
MAIN_PY = ROOT / "app" / "main.py"
ORCHESTRATOR_PY = ROOT / "app" / "agents" / "orchestrator.py"
MIGRATIONS_DIR = ROOT / "migrations"
CONTRACT = ROOT / "docs" / "api" / "contract-v1.md"

ENDPOINT = "GET /api/v1/hitl/pending"
SECTION_HEADING = "## HITL Pending Listing"
ENVELOPE_SUBHEAD = f"`{ENDPOINT}` -> response envelope"
FAILED_SUBHEAD = f"`{ENDPOINT}` -> `failed_turns[]` rows"
STATUS_SUBHEAD = "The `failed` terminal status, and where PostgreSQL still cannot store it"

#: 契约里那五行取值域的行首锚（冒号之后就是域本身，竖线顺序即文档承诺的顺序）
DOMAIN_PATTERNS = {
    "status": r"^`pending_approvals\.status` value domain: (.+)$",
    "items_status": r"^`items\[\]\.status` value domain: (.+)$",
    "failed_status": r"^`failed_turns\[\]\.status` value domain: (.+)$",
    "decided": r"^`DECIDED_STATUSES`: (.+)$",
    "pg": r"^`pending_approvals_status_check` accepts: (.+)$",
}

#: 🔴 缺口那一段的锚词：任一枚被删掉都等于契约不再替员工说这句话
GAP_ANCHORS = (
    "**🔴 The PG gap",
    "PostgreSQL cannot",
    "stays `awaiting`",
    "`failed_items` reads it back",
    "the migration R190 is proposing widens that CHECK",
    "not writing `refused` or `abandoned` to make the numbers add up",
    "migrations/0008_pending_approvals.sql",
)

#: 信封那一节里前端唯一能据以说话的行为裁决（缺一条，界面上就有一句没据可依）
ENVELOPE_RULE_ANCHORS = (
    "inside the same `try`",
    "still `503 storage_unavailable` for the whole call",
    "never reconfirmed against the graph",
    "asks the graph once per listed to-do and zero times per failed turn",
    "newest `limit`",
    "Empty `items` plus non-empty `failed_turns` is a real state",
)

CHECK_PATTERN = re.compile(
    r"pending_approvals_status_check\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]*)\)", re.IGNORECASE
)


def _text(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(ROOT)} 不在了"
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


@lru_cache(maxsize=None)
def _tree(path: Path) -> ast.Module:
    return ast.parse(_text(path))


def _flat(text: str) -> str:
    """把折行摊平：锚词是**句子**，Markdown 的换行不该把它们切开。"""
    return re.sub(r"\s+", " ", text)


# ==================== 契约侧 ====================


def _section_text() -> str:
    text = _text(CONTRACT)
    start = text.find(SECTION_HEADING)
    assert start != -1, f"契约里找不到 {SECTION_HEADING!r} 这一节：改名可以，请连本钉一起改"
    tail = text[start + len(SECTION_HEADING):]
    end = re.search(r"^## ", tail, re.MULTILINE)
    section = text[start:start + len(SECTION_HEADING) + (end.start() if end else len(tail))]
    assert len(section) > 4000, "HITL 这一节短得不对劲，后面每枚钉都会变成空响"
    return section


def _split_section() -> tuple[str, dict[str, str]]:
    """返回（R13 主体，小节标题 -> 小节正文）。"""
    section = _section_text()
    chunks = re.split(r"^### ", section, flags=re.MULTILINE)
    subs: dict[str, str] = {}
    for chunk in chunks[1:]:
        head, _, body = chunk.partition("\n")
        subs[head.strip()] = body
    assert set(subs) == {ENVELOPE_SUBHEAD, FAILED_SUBHEAD, STATUS_SUBHEAD}, (
        f"这一节的小节名单变了（{sorted(subs)}）：换标题可以，请连契约里的互指与本钉一起改"
    )
    assert len(chunks[0]) > 1500, "R13 那段主体的长度不该由这次补写来缩短"
    return chunks[0], subs


def _table_keys(body: str) -> list[str]:
    keys = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", body, re.MULTILINE)
    assert keys, "这一节里一枚键表都没有，键集合的钉就是空响"
    return keys


def _table_row(body: str, key: str) -> str:
    for match in re.finditer(r"^\|\s*`([a-z_]+)`\s*\|.*$", body, re.MULTILINE):
        if match.group(1) == key:
            return match.group(0)
    raise AssertionError(f"键表里少了 {key!r} 那一行")


def _json_blocks(body: str) -> list[dict]:
    blocks = re.findall(r"```json\n(.*?)\n```", body, re.DOTALL)
    assert blocks, "这一节里没有 JSON 例子块，形状没钉住"
    return [json.loads(block) for block in blocks]


def _domain(body: str, key: str) -> list[str]:
    match = re.search(DOMAIN_PATTERNS[key], body, re.MULTILINE)
    assert match, f"契约里少了取值域那一行（{key} -> {DOMAIN_PATTERNS[key]}）"
    return [token.strip() for token in match.group(1).split("|")]


def _shape_block_keys(lead: str) -> list[str]:
    """节首那块 Shape 速记里出现过的键名（本钉就是不许它变成第二套真相）。"""
    fences = [
        fence for fence in re.findall(r"^```\n(.*?)\n```", lead, re.DOTALL | re.MULTILINE)
        if '"items"' in fence
    ]
    assert len(fences) == 1, f"节首的 Shape 速记实取 {len(fences)} 块：那种速记只许有一枚"
    return re.findall(r'"([a-z_]+)"', fences[0])


def _documented_int(body: str, constant: str) -> int:
    hits = re.findall(rf"`{constant}` \((\d+)\)", body)
    assert len(hits) == 1, f"{constant} 的数字在契约里实取 {len(hits)} 处：只许有一处，其余请引常量名"
    return int(hits[0])


# ==================== 代码侧：AST 现抠（零手抄） ====================


def _function(tree: ast.Module, name: str, origin: Path) -> ast.AST:
    found = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"{origin.name} 里 {name} 应当只有一处，实取 {len(found)} 处"
    return found[0]


def _dict_keys(node: ast.Dict) -> list[str]:
    keys = []
    for key in node.keys:
        assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
            "构造点的键必须是字面量字符串，否则本钉读不到形状"
        )
        keys.append(key.value)
    return keys


def _dict_value(node: ast.Dict, key: str) -> ast.expr:
    for dict_key, value in zip(node.keys, node.values):
        if isinstance(dict_key, ast.Constant) and dict_key.value == key:
            return value
    raise AssertionError(f"构造点里没有 {key!r} 这一枚键：契约与代码此刻正在互相说谎")


def _pending_fn() -> ast.AST:
    return _function(_tree(CHAT_PY), "hitl_pending", CHAT_PY)


def _envelope_dict() -> ast.Dict:
    returns = [
        node for node in ast.walk(_pending_fn())
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    ]
    assert len(returns) == 1, (
        f"hitl_pending 的返回体应当只有一枚 dict 字面量（实取 {len(returns)} 枚）：多一枚就是多一处真相源"
    )
    return returns[0].value


def _items_element_dict() -> ast.Dict:
    found = [
        node.args[0] for node in ast.walk(_pending_fn())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append" and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "items" and node.args and isinstance(node.args[0], ast.Dict)
    ]
    assert len(found) == 1, f"items.append 的 dict 字面量实取 {len(found)} 枚"
    return found[0]


def _failed_comprehension() -> ast.ListComp:
    value = _dict_value(_envelope_dict(), "failed_turns")
    assert isinstance(value, ast.ListComp), (
        "failed_turns 不再是推导式：契约那句「同一本账的第二次读、不参与复核」要重读"
    )
    return value


def _failed_element_dict() -> ast.Dict:
    element = _failed_comprehension().elt
    assert isinstance(element, ast.Dict), "failed_turns 的元素不再是 dict 字面量：请同步契约与本钉"
    return element


def _assignments(node: ast.AST) -> dict[str, str]:
    out: dict[str, str] = {}
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            for target in sub.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = ast.unparse(sub.value)
    return out


def _leg_call(dotted: str) -> ast.Call:
    calls = [
        node for node in ast.walk(_pending_fn())
        if isinstance(node, ast.Call) and ast.unparse(node.func) == dotted
    ]
    assert len(calls) == 1, f"{dotted} 在本端点的调用点实取 {len(calls)} 处：契约讲的是唯一那一处"
    return calls[0]


def _keyword(call: ast.Call, name: str) -> str:
    for keyword in call.keywords or []:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    raise AssertionError(f"{ast.unparse(call.func)}(...) 不再传 {name} 这一枚关键字实参")


def _module_assign(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name
        ):
            return node.value
    raise AssertionError(f"{name} 不再是模块级常量：取值域失去了唯一的源")


def _status_constants() -> dict[str, str]:
    out: dict[str, str] = {}
    for node in _tree(STORE_PY).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out[node.targets[0].id] = node.value.value
    return out


def _status_value(name: str) -> str:
    constants = _status_constants()
    assert name in constants, f"pending_approvals.py 里没有状态常量 {name}"
    return constants[name]


def _status_seq(name: str) -> list[str]:
    """把 ALL_STATUSES / DECIDED_STATUSES / PG_STATUSES 按源码顺序解成字面值。"""
    value = _module_assign(_tree(STORE_PY), name)
    if isinstance(value, ast.Call):
        assert ast.unparse(value.func) == "frozenset", f"{name} 不再是 frozenset(...)：本钉读不到它的取值域"
        value = value.args[0]
    assert isinstance(value, (ast.Tuple, ast.Set, ast.List)), f"{name} 的字面量形状读不出来"
    constants = _status_constants()
    resolved = []
    for element in value.elts:
        assert isinstance(element, ast.Name) and element.id in constants, (
            f"{name} 里出现了裸字面量或外来的名字：{ast.unparse(element)}（取值域必须引用具名常量）"
        )
        resolved.append(constants[element.id])
    assert len(resolved) == len(set(resolved)), f"{name} 里有重复值"
    return resolved


def _leg_status(function_name: str) -> str:
    """``open_items`` / ``failed_items`` 各自传给唯一那份 SQL 的那一格状态。"""
    calls = [
        node for node in ast.walk(_function(_tree(STORE_PY), function_name, STORE_PY))
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "_items_with_status"
    ]
    assert len(calls) == 1, f"{function_name} 不再只问一次 _items_with_status：WHERE 那一份复制了"
    argument = calls[0].args[0] if calls[0].args else None
    assert isinstance(argument, ast.Name), f"{function_name} 的状态实参不再是具名常量"
    constants = _status_constants()
    assert argument.id in constants, f"{function_name} 传了一枚不认识的状态名：{argument.id}"
    return constants[argument.id]


def _parked_steps() -> list[str]:
    value = _module_assign(_tree(ORCHESTRATOR_PY), "_HITL_PARKED")
    assert isinstance(value, ast.Tuple), "_HITL_PARKED 不再是元组：parked_steps 的取值域失去了源"
    return [element.value for element in value.elts if isinstance(element, ast.Constant)]


def _in_force_check() -> tuple[set[str], str]:
    """生效中的 ``pending_approvals_status_check`` 取值域：按文件名序取最后一条重定义。"""
    hits: list[tuple[str, set[str]]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        for match in CHECK_PATTERN.finditer(_text(path)):
            hits.append((path.name, {item.strip().strip("'\"") for item in match.group(1).split(",")}))
    assert hits, "migrations/ 里找不到 pending_approvals_status_check：那枚 CHECK 不见了"
    origin, allowed = hits[-1]
    return allowed, origin


def _route_key(function_name: str) -> tuple[str, str]:
    fn = _function(_tree(CHAT_PY), function_name, CHAT_PY)
    routes = []
    for decorator in fn.decorator_list:
        if (
            isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in {"get", "post", "put", "delete"} and decorator.args
        ):
            argument = decorator.args[0]
            assert isinstance(argument, ast.Constant), "路由路径不再是字面量：本钉读不到它"
            routes.append((decorator.func.attr, str(argument.value)))
    assert len(routes) == 1, f"{function_name} 挂了 {len(routes)} 条路由：本钉要按条对判"
    return routes[0]


def _chat_prefix() -> str:
    for node in ast.walk(_tree(MAIN_PY)):
        if (
            isinstance(node, ast.Call)
            and ast.unparse(node.func).endswith("include_router")
            and node.args and ast.unparse(node.args[0]) == "chat.router"
        ):
            for keyword in node.keywords or []:
                if keyword.arg == "prefix":
                    assert isinstance(keyword.value, ast.Constant), "chat 路由的 prefix 不再是字面量"
                    return str(keyword.value.value)
    raise AssertionError("main.py 不再以 include_router(chat.router, prefix=...) 挂载聊天路由")


# ==================== ① 键集合：文档与构造点双向对判 ====================


def test_documented_envelope_keys_are_the_keys_hitl_pending_returns():
    _, subs = _split_section()
    assert _table_keys(subs[ENVELOPE_SUBHEAD]) == _dict_keys(_envelope_dict()), (
        "契约信封键表与 return dict 不再是同一串（顺序也算）："
        "多列一枚是替后端开洞，少列一枚是前端无从可读到"
    )
    assert "`labels`" in _table_row(subs[ENVELOPE_SUBHEAD], "items"), (
        "items 那一行不再交代它比失败行多带 labels：两枚列表的差别就只剩散文在说了"
    )


def test_documented_failed_turn_keys_are_the_keys_the_comprehension_builds():
    _, subs = _split_section()
    built = _dict_keys(_failed_element_dict())
    assert _table_keys(subs[FAILED_SUBHEAD]) == built, (
        "failed_turns 的键表与推导式里那个 dict 不同源"
    )
    rows = [row for block in _json_blocks(subs[FAILED_SUBHEAD]) for row in block["failed_turns"]]
    assert rows, "failed_turns 没有例子行：形状没钉住"
    for row in rows:
        assert list(row) == built, f"例子块的键与构形处不等：{sorted(row)}"
        assert row["status"] == _status_value("FAILED"), "例子里的 status 是构形处不会产出的那一格"
        for step in row["parked_steps"]:
            assert step in _parked_steps(), f"例子里的 {step!r} 不在 _HITL_PARKED 里：那是界面说不出的步骤名"


def test_labels_is_the_only_difference_between_the_two_element_shapes():
    items_keys = _dict_keys(_items_element_dict())
    failed_keys = _dict_keys(_failed_element_dict())
    assert set(items_keys) - set(failed_keys) == {"labels"}, (
        f"待办行比失败行多出的不再只有 labels：{sorted(set(items_keys) - set(failed_keys))}"
    )
    assert not set(failed_keys) - set(items_keys), (
        "失败行带上了待办行没有的键：契约那句「同一本账、同一份记录形状」当场是假话"
    )
    _, subs = _split_section()
    assert "no `labels` key" in _flat(subs[FAILED_SUBHEAD]), (
        "那一节不再明写「故意没有 labels」：前端会以为缺字段是自己的 bug"
    )


def test_the_shape_block_at_the_top_of_the_section_is_the_same_shape():
    lead, subs = _split_section()
    documented = set(_shape_block_keys(lead))
    built = (
        set(_dict_keys(_envelope_dict()))
        | set(_dict_keys(_items_element_dict()))
        | set(_dict_keys(_failed_element_dict()))
    )
    assert documented == built, (
        f"节首那块速记与两枚键表/构造点不再同源：多了 {sorted(documented - built)}、少了 {sorted(built - documented)}"
    )

# ==================== ② 取值域：与 pending_approvals.py 的常量同源 ====================


def test_documented_status_domains_match_the_code_constants():
    _, subs = _split_section()
    body = subs[STATUS_SUBHEAD]
    assert _domain(body, "status") == _status_seq("ALL_STATUSES"), (
        "契约写的状态取值域与 ALL_STATUSES 不再同一串：文档写窄了就是少一格终态"
    )
    assert _domain(body, "decided") == _status_seq("DECIDED_STATUSES"), (
        "契约那行 DECIDED_STATUSES 与常量不再同源：failed 是不是一格闭合，界面上就看这一行"
    )
    assert _domain(body, "pg") == _status_seq("PG_STATUSES"), (
        "契约那行 CHECK 的接受域与 PG_STATUSES 不再同源：那一格是「PG 写不进」这句话的一半证据"
    )
    assert _domain(body, "items_status") == [_leg_status("open_items")], (
        "items[].status 恒为 awaiting 这句不再成立：待办那一屏会开始列出已经闭合的行"
    )
    assert _domain(body, "failed_status") == [_leg_status("failed_items")], (
        "failed_turns[].status 那一行与 failed_items 实际问的那一格不再同源"
    )
    assert _domain(body, "failed_status") == [_status_value("FAILED")]


def test_the_gap_between_the_two_documented_domains_is_exactly_failed():
    _, subs = _split_section()
    body = subs[STATUS_SUBHEAD]
    full = set(_domain(body, "status"))
    pg = set(_domain(body, "pg"))
    assert full - pg == {_status_value("FAILED")}, (
        "契约那两行域之间的差已不再只有 failed：那一句「PG 少一格」得重写"
    )
    assert pg <= full, "PG 的接受域出现了代码里的状态域没有的名字"


# ==================== ③ 行为裁决：offset / limit / count / has_more / 归属 ====================


def test_the_documented_paging_rules_are_what_the_code_does():
    open_call = _leg_call("pending_approvals.open_items")
    failed_call = _leg_call("pending_approvals.failed_items")
    assert _keyword(open_call, "limit") == "applied_limit + 1", (
        "待办那一腿不再多问一行：契约那句 has_more 的来路要重读"
    )
    assert _keyword(failed_call, "limit") == "applied_limit + 1", (
        "失败那一腿不再多问一行：failed_turns_has_more 就是没有依据的一句话"
    )
    assert _keyword(open_call, "offset") == "applied_offset", "offset 不再驱动待办那一腿"
    assert _keyword(failed_call, "offset") == "0", (
        "🔴 失败那一腿开始吃 offset 了：契约那句「offset 不移动 failed_turns」当场是假话，"
        "而界面那句「看更早的」会把同一批失败行当成第二页列回来"
    )
    assert _keyword(failed_call, "owner_user_id") == _keyword(open_call, "owner_user_id"), (
        "两腿的归属过滤不再是同一个表达式：不带归属就读失败账本就是读全司"
    )


def test_count_and_the_two_has_more_flags_are_computed_the_way_the_table_says():
    envelope = _envelope_dict()
    assert ast.unparse(_dict_value(envelope, "count")) == "len(items)", (
        "count 不再就是 len(items)：契约那句「它是页长不是总数」要重读"
    )
    assignments = _assignments(_pending_fn())
    for flag, source in (("has_more", "rows"), ("failed_turns_has_more", "failed_rows")):
        variable = ast.unparse(_dict_value(envelope, flag))
        assert variable in assignments, f"{flag} 的值来自一枚本钉读不到的变量：{variable}"
        assert assignments[variable] == f"len({source}) > applied_limit", (
            f"{flag} 的算法换了（现在是 {assignments[variable]}）：两枚 *_has_more 说的是同一件事这句不再成立"
        )
    assert ast.unparse(_dict_value(envelope, "failed_turns_has_more")) == "failed_has_more"


def test_the_recheck_leg_stays_out_of_the_failed_list():
    asks = [
        node for node in ast.walk(_pending_fn())
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "check_interrupt"
    ]
    assert len(asks) == 1, f"复核腿出现了 {len(asks)} 处调用：契约那句「每条待办问一次」要重读"
    in_failed = [
        node for node in ast.walk(_failed_comprehension())
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "check_interrupt"
    ]
    assert not in_failed, (
        "🔴 failed_turns 开始向图复核了：那一行会被就地判成 stale（「已作废」），"
        "正是 R175 要消灭的那句话"
    )


def test_documented_limit_numbers_are_the_route_constants():
    _, subs = _split_section()
    body = subs[ENVELOPE_SUBHEAD]
    assignments = _assignments(_tree(CHAT_PY))
    assert _documented_int(body, "DEFAULT_PENDING_LIMIT") == int(assignments["DEFAULT_PENDING_LIMIT"])
    assert _documented_int(body, "MAX_PENDING_LIMIT") == int(assignments["MAX_PENDING_LIMIT"])
    assert assignments["applied_limit"] == "max(1, min(int(limit), MAX_PENDING_LIMIT))", (
        "夹逼那一步的形状变了：契约那句「至少 1、至多上限」要按新形状重写"
    )
    assert "clamped to at least 1 and at most" in _flat(_table_row(body, "limit")), (
        "limit 那一行不再写夹逼区间：客户端会以为传什么就是什么"
    )


def test_the_envelope_rules_the_frontend_relies_on_are_still_written_down():
    _, subs = _split_section()
    flattened = _flat(subs[ENVELOPE_SUBHEAD])
    for anchor in ENVELOPE_RULE_ANCHORS:
        assert _flat(anchor) in flattened, f"信封那一节不再交代：{anchor}"


# ==================== ④ 端点路径：从装饰器与 prefix 现算 ====================


def test_the_endpoint_in_the_subheads_is_the_registered_route():
    method, path = _route_key("hitl_pending")
    assert (method, path) == ("get", "/hitl/pending"), f"路由本身变了：{method} {path}"
    endpoint = f"{method.upper()} {_chat_prefix()}{path}"
    assert endpoint == ENDPOINT, f"契约与本钉讲的已经不是同一条路：{endpoint}"
    assert ENVELOPE_SUBHEAD == f"`{endpoint}` -> response envelope"
    assert FAILED_SUBHEAD == f"`{endpoint}` -> `failed_turns[]` rows", (
        "小节标题不再把端点与 failed_turns 绑在同一行上"
    )


# ==================== ⑤ 🔴 PG 缺口：引信 ====================


def test_the_contract_states_the_pg_gap_while_the_gap_exists():
    """🔴 R190 并树之后这一枚必须红一次：那是它的目的，不是它的故障。

    今天（施工基点 c053ddd）线上事实是：本机文件账把那一行闭合成 failed 并读得回来，PG 那一行
    仍留在 awaiting —— 因为 ``failed`` 不在 0008 的 ``pending_approvals_status_check`` 里。
    只要代码侧还报这枚缺口，契约就必须把这句话写在纸上；缺口一旦闭合，这句话就成了假话，
    本钉必须拦住它继续躺着。
    """
    _, subs = _split_section()
    body = subs[STATUS_SUBHEAD]
    flattened = _flat(body)
    gap = set(_status_seq("ALL_STATUSES")) - set(_status_seq("PG_STATUSES"))
    assert gap, (
        "🔴 引信按设计红这一次：代码侧的 PG 缺口已经闭合（ALL_STATUSES 与 PG_STATUSES 同一枚集合，"
        "R190 的 CHECK 应当已经并树），而契约里那段「PG 今天存不下 failed」已经变成假话 —— "
        "请改写 STATUS_SUBHEAD 那一节并删掉 GAP_ANCHORS 里那些句子，别让它继续躺着骗人"
    )
    assert gap == {_status_value("FAILED")}, f"缺口今天不再是只有 failed 一枚：{sorted(gap)}"
    for anchor in GAP_ANCHORS:
        assert anchor in body or _flat(anchor) in flattened, (
            f"契约不再明写 PG 缺口（锚词 {anchor!r} 不见了）：那一格今天仍是线上事实，不许写成已经能用"
        )


def test_the_check_constraint_and_the_pg_constant_agree():
    """缺口的第三条证据不收散文：SQL 那枚 CHECK 与 PG_STATUSES 必须同一枚集合。"""
    allowed, origin = _in_force_check()
    assert allowed == set(_status_seq("PG_STATUSES")), (
        f"{origin} 里生效的 pending_approvals_status_check 与 PG_STATUSES 不再同一枚集合："
        "R190 并树后的预期红 —— app/storage/pending_approvals.py 的常量注释与本文件的"
        " STATUS_SUBHEAD 那一节都要跟着改写"
    )
    assert _status_value("FAILED") not in allowed, (
        "CHECK 已经认得 failed 了：契约那句「PG 腿今天存不下」必须删，不许留成第二套真相"
    )
