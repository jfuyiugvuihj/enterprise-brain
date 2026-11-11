"""R142 · 契约里那份错误码表必须与 ``ErrorEnvelope.code`` 同源；裸码必须有人记账。

来历（R32 交工时自报、总控核过并立单）：``docs/api/contract-v1.md`` 的
``## REST Error Envelope`` 那张表只列 26 枚，而枚举已经 29 枚 —— 缺
``context_limit_exceeded``（R30）、``row_scope_denied`` / ``no_visible_rows``（R64）。
三枚都是**真实在吐**的码，客户端照契约写分支就会漏掉整条道。全仓当时没有任何一枚用例
读那张表，所以它漂了三个单没人看见。这一枚钉先让它红，再补表。

三条自守的规矩（抄 R132 的纪律）：
  ① 清单一律从 ``app/agents/contracts.py`` 的 AST 现扫，本文件**零手抄码名**；
  ② 只读源码与 markdown 文本，不 import ``app**``（不碰模型、不碰库、不起服务）；
  ③ 解析不到就抛，绝不回空集合 —— 空集合会让"集合相等"变成恒真。
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO / "docs" / "api" / "contract-v1.md"
CONTRACTS_PY = REPO / "app" / "agents" / "contracts.py"
APP_DIR = REPO / "app"
FRONTEND_ERRCODES = REPO / "frontend" / "src" / "lib" / "errcodes.js"
VOCABULARY_TEST = REPO / "tests" / "test_error_code_vocabulary.py"

SECTION_TITLE = "## REST Error Envelope"
TABLE_INTRO = "Error responses use a stable `code` from:"
#: 表与枚举同源，不是等长：这两枚字面量在本文件里只用于"解析器没瞎"的对照组
MIN_CODES_TODAY = 26
#: 换行符用 chr(10) 现取：本仓的文件是 CRLF，源码里写反斜杠 n 很容易被编辑器改掉
NL = chr(10)


def _read(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(REPO)} 不在了"
    return path.read_text(encoding="utf-8")


def _enum_codes_from(source: str) -> list[str]:
    """按 AST 抠 ``ErrorEnvelope.code`` 的 Literal 成员，顺序就是声明顺序。"""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "ErrorEnvelope":
            for stmt in node.body:
                annotation = getattr(stmt, "annotation", None)
                if (isinstance(annotation, ast.Subscript)
                        and getattr(annotation.value, "id", "") == "Literal"):
                    codes = [element.value for element in annotation.slice.elts
                             if isinstance(element, ast.Constant) and isinstance(element.value, str)]
                    if not codes:
                        raise AssertionError("ErrorEnvelope.code 的 Literal 解析出零枚码，对照组也不许放行")
                    return codes
    raise AssertionError("app/agents/contracts.py 里找不到 ErrorEnvelope.code 的 Literal[...]，形状变了")


def _table_codes_from(doc_text: str) -> list[str]:
    """吃 ``TABLE_INTRO`` 之后那一整串 ``- `code``` 行，吃到断行为止。

    刻意不按整节正则扫：那节里还有别的 bullet 与表格行，扫宽了会把不相干的反引号词
    当成码，"表落后于枚举"这种漂移就再也读不出来了。
    """
    start = doc_text.find(TABLE_INTRO)
    if start == -1:
        raise AssertionError(f"契约里找不到表头那句 {TABLE_INTRO!r}：标题被改，对账要先改这里")
    lines = doc_text[start + len(TABLE_INTRO):].splitlines()
    codes = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if codes:
                break
            continue
        match = re.fullmatch(r"- `([a-z][a-z0-9_]*)`", stripped)
        if not match:
            break
        codes.append(match.group(1))
    if not codes:
        raise AssertionError("契约里那张错误码表一枚都没解析出来，对账不能降级成恒真")
    return codes


def _error_section() -> str:
    text = _read(CONTRACT_DOC)
    start = text.find(SECTION_TITLE)
    if start == -1:
        raise AssertionError(f"契约里找不到 {SECTION_TITLE!r} 这一节")
    following = re.compile(r"^## ", re.MULTILINE).search(text, start + len(SECTION_TITLE))
    return text[start: following.start() if following else len(text)]


def enum_codes() -> list[str]:
    return _enum_codes_from(_read(CONTRACTS_PY))


def table_codes() -> list[str]:
    return _table_codes_from(_read(CONTRACT_DOC))


# ==================== 判据① 表与枚举同源（补表前先红过一次） ====================


def test_the_contract_table_lists_exactly_the_codes_the_enum_ratifies():
    """表里缺哪枚就指名报哪枚，多列哪枚也一样 —— 不拉齐数字，只把差集摊开。"""
    declared, documented = enum_codes(), table_codes()

    missing = [code for code in declared if code not in documented]
    invented = [code for code in documented if code not in declared]
    assert missing == [], "契约的错误码表落后于枚举，客户端照表写分支会漏掉：" + "、".join(missing)
    assert invented == [], "契约列了枚举里没有的码名（表在替后端开洞）：" + "、".join(invented)


def test_the_table_mirrors_the_enum_order_not_a_re_sorted_copy():
    """同源之外还要同序：枚举里 ``internal_error`` 刻意留在最后（兜底码一眼可辨），
    表把它排到中间就等于换了一份语义。要重排，先重排枚举并说明理由。"""
    declared, documented = enum_codes(), table_codes()

    assert documented == declared, (
        "表与枚举成员相同但顺序不同：表是镜像不是抄本，顺序本身也是契约。"
        f"{NL}  枚举: {declared}{NL}  表  : {documented}"
    )


def test_the_two_parsers_are_not_blind():
    """反空转：两枚解析器都必须真的读出东西；解析失败必须抛而不是回空。"""
    declared, documented = enum_codes(), table_codes()

    assert len(declared) >= MIN_CODES_TODAY, len(declared)
    assert len(documented) >= MIN_CODES_TODAY, len(documented)
    assert len(set(declared)) == len(declared), "枚举里有重码"
    assert len(set(documented)) == len(documented), "表里有重行"
    # 没有 Literal 块的源码必须抛，不能被读成"零枚码 = 与空表相等"
    try:
        _enum_codes_from("class ErrorEnvelope:" + NL + "    code: str" + NL)
    except AssertionError:
        pass
    else:
        raise AssertionError("解析器在抠不到 Literal 时回上了风头，对账会退化成恒真")
    try:
        _table_codes_from(TABLE_INTRO + NL + NL + "随便一句话。" + NL)
    except AssertionError:
        pass
    else:
        raise AssertionError("解析器在表为空时回上了风头，对账会退化成恒真")


def test_the_note_under_the_table_stops_counting_names():
    """表下面那段注不许再写"这八枚/那七枚"：数量会随每一单漂，机制不会。

    它必须改成指机制（谁追认、由哪枚用例钉住同源），并把"裸 detail 串"那一族交代在原地。
    """
    section = _error_section()

    stale = re.findall(r"(?:eight|seven|nine|ten|\d+)\s+names", section, re.IGNORECASE)
    assert stale == [], f"表下注又回到数名字了：{stale} —— 改成指名机制与用例"
    assert "test_error_code_vocabulary" in section, "表下注不再指名追认机制的出处"
    assert "test_r142_error_code_table_sync" in section, "表下注不指名这枚同源钉，下一个人还是看不见它"


# ==================== 判据②：裸码必须有人记账（R142 立的那张新账） ====================
#
# 契约表下注写着「每一枚裸 detail 串都记在
# tests/test_error_code_vocabulary.py::BARE_CODES_OUTSIDE_THE_ENUM 里」，这句话本身得有人验，
# 否则它就只是另一段会漂的散文。三头一起钉：
#   扫描器 —— app/** 里静态抠得到的 detail 码名，必须 ∈ 枚举 ∪ 账；
#   出处   —— 账里每一枚的 emitter 位锚（``file::symbol``）今天还站着那枚字面量；
#   归一   —— 账与 frontend/src/lib/errcodes.js::LEGACY_ALIASES 键集合相等，且 folds_into 是真枚举成员。
# 扫描器只覆盖静态半族（字面量 / 模块级常量 / dict 里的 code:），那就是它的全部职责：
# 动态半族（``detail=decision.reason_code`` 这种 raise 处连字面量都没有的）改由「出处 + 归一」两头钉，
# 因为抠属性值要先跑起来，而本文件的纪律是不 import app/**。

CODE_SHAPE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
REGISTER_NAME = "BARE_CODES_OUTSIDE_THE_ENUM"
#: 静态可解析的裸码 today 就有 9 枚；账比这还薄说明扫描器或表被动过，而不是"变干净了"
MIN_REGISTER_TODAY = 9

R37_ENQUEUE_TEST = REPO / "tests" / "test_r37_report_lane_enqueue.py"
LEGACY_ALIAS_DECL = "export const LEGACY_ALIASES"


def _licensed_register() -> dict[str, dict]:
    """从词汇表源码里抠登记表，刻意不 import 那枚文件。

    import 会把 app/** 整条依赖链拉起来（本文件的纪律是只读源码）；用 AST 还顺带钉住
    「这张表必须是纯字面量」—— 表里塞进计算式就等于把账做成活的，谁都能悄悄改。
    """
    for node in ast.walk(ast.parse(_read(VOCABULARY_TEST))):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == REGISTER_NAME for t in node.targets):
            table = ast.literal_eval(node.value)
            if not isinstance(table, dict) or not table:
                raise AssertionError(f"{REGISTER_NAME} 空了或形状变了，记账不能降级成恒真")
            for code, entry in table.items():
                if not isinstance(entry, dict) or not {"emitter", "folds_into", "why"} <= set(entry):
                    raise AssertionError(f"{REGISTER_NAME}[{code}] 缺 emitter/folds_into/why 三字段之一")
            return table
    raise AssertionError(f"tests/test_error_code_vocabulary.py 里找不到 {REGISTER_NAME}")


def _detail_codes_from(source: str, origin: str) -> dict[str, list[str]]:
    """抠一份源码里静态可解析的 ``HTTPException(detail=...)`` 码名，值带 ``file::函数`` 位锚。"""
    tree = ast.parse(source)
    consts = {
        t.id: node.value.value
        for node in tree.body if isinstance(node, ast.Assign) for t in node.targets
        if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    funcs = sorted(
        [(node.lineno, node.end_lineno, node.name)
         for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))],
        key=lambda item: item[1] - item[0],
    )

    def symbol_of(lineno: int) -> str:
        for start, end, name in funcs:
            if start <= lineno <= end:
                return name
        return "<module>"

    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException"):
            continue
        for keyword in node.keywords:
            if keyword.arg != "detail":
                continue
            value = keyword.value
            codes: list[str] = []
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                codes = [value.value]
            elif isinstance(value, ast.Name) and value.id in consts:
                codes = [consts[value.id]]
            elif isinstance(value, ast.Dict):
                codes = [v.value for k, v in zip(value.keys, value.values)
                         if isinstance(k, ast.Constant) and k.value == "code"
                         and isinstance(v, ast.Constant) and isinstance(v.value, str)]
            # 其余形状（f-string / 属性值 / 函数调用）静态抠不到：见本节开头的分工说明
            for code in codes:
                if CODE_SHAPE.match(code):
                    found.setdefault(code, []).append(f"{origin}::{symbol_of(node.lineno)}")
    return found


def _static_detail_codes() -> dict[str, list[str]]:
    emitted: dict[str, list[str]] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        origin = path.relative_to(REPO).as_posix()
        for code, anchors in _detail_codes_from(_read(path), origin).items():
            emitted.setdefault(code, []).extend(anchors)
    if len(emitted) < 15:
        raise AssertionError(f"扫描器只认出 {len(emitted)} 枚 detail 码名，多半是形状变了而不是码变少了")
    return emitted


def _legacy_alias_folds() -> dict[str, str]:
    """吃前端 LEGACY_ALIASES 的第一层键，以及每个键折叠到的枚举码。"""
    text = _read(FRONTEND_ERRCODES)
    start = text.find(LEGACY_ALIAS_DECL)
    if start == -1:
        raise AssertionError(f"frontend/src/lib/errcodes.js 里找不到 {LEGACY_ALIAS_DECL}")
    brace = text.index("{", start)
    depth = 0
    end = -1
    for index in range(brace, len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            end = index
            break
    if end == -1:
        raise AssertionError("LEGACY_ALIASES 没找到收尾的 }，键表没法读")
    folds: dict[str, str] = {}
    pending: tuple[str, list[str]] | None = None
    for line in text[brace:end].splitlines():
        if line.strip().startswith("//"):
            continue
        entry = re.match(r"  ([a-z][a-z0-9_]*): (.*)$", line)
        if entry:
            name, rest = entry.group(1), entry.group(2)
            folded = re.search(r"code: '([a-z_]+)'", rest)
            if folded:
                folds[name] = folded.group(1)
                pending = None
            else:
                pending = (name, [rest])
            continue
        if pending is not None:
            folded = re.search(r"code: '([a-z_]+)'", line)
            if folded:
                folds[pending[0]] = folded.group(1)
                pending = None
    if len(folds) < 15:
        raise AssertionError(f"前端别名表只读出 {len(folds)} 条，解析姿势变了")
    return folds


def _owned_error_block() -> str:
    """本节里 R142 真正管得住的那一段：码表条目 + 紧跟其后的表下注（blockquote）。

    边界按形状读，不按行号读：从 ``TABLE_INTRO`` 起，连续吃 ``- `code``` 行与 ``>`` 行，
    遇到第一行不是这两类的正文就停 —— 那已经是别人单子的段落。读空或读不到 blockquote 就抛，
    免得"段不存在"被当成"段里没有裸行号"而蒙混过关。
    """
    section = _error_section()
    body = section[section.find(TABLE_INTRO) + len(TABLE_INTRO):]
    kept: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "":
            continue  # 列表与 blockquote 之间本来就有空行，它不算断开
        if stripped.startswith(">") or re.fullmatch(r"- `[a-z][a-z0-9_]*`", stripped):
            kept.append(stripped)
        else:
            break     # 第一段不相干的正文：那已经是别人单子的段落
    if not any(item.startswith(">") for item in kept):
        raise AssertionError("读不到表下注那串 blockquote，这一段没法钉，先修解析器")
    return chr(10).join(kept)


def test_static_detail_codes_are_either_ratified_or_licensed():
    """判据②主干：往响应体里现造一枚裸码，必须当场红，并指名它从哪个函数吐出来。"""
    declared, licensed = set(enum_codes()), set(_licensed_register())
    emitted = _static_detail_codes()

    unaccounted = sorted(code for code in emitted if code not in declared and code not in licensed)
    assert unaccounted == [], "这些码正在被吐出，既不在封闭枚举里也没记账：" + "; ".join(
        f"{code} <- {', '.join(sorted(set(emitted[code])))}" for code in unaccounted)


def test_a_licensed_bare_code_is_not_allowed_to_sneak_into_the_enum():
    """账与枚举互斥：一枚码进了枚举就该搬进 RATIFIED，账里留着它说明有人在两头下注。"""
    declared = set(enum_codes())
    sneaked = sorted(code for code in _licensed_register() if code in declared)
    assert sneaked == [], (
        f"这些码已经进了 ErrorEnvelope.code，请把它们从 {REGISTER_NAME} 移进 RATIFIED 并同步前端键集合："
        + "、".join(sneaked))


def test_every_licensed_bare_code_still_has_a_live_emitter():
    """出处必须还站在原位锚上：改文件名、搬函数、删码，三种都在这里红。"""
    register = _licensed_register()

    for code, entry in sorted(register.items()):
        for anchor in [entry["emitter"], *entry.get("also_emitted_by", [])]:
            origin, _, symbol = anchor.partition("::")
            path = REPO / origin
            assert path.exists(), f"{code} 的出处 {origin} 不在了"
            tree = ast.parse(_read(path))
            if symbol == "<module>":
                top_level = [node for node in tree.body if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom))]
                lives = [node.lineno for stmt in top_level for node in ast.walk(stmt)
                         if isinstance(node, ast.Constant) and node.value == code]
                assert lives, f"{code} 不再出现在 {origin} 的模块级常量里，账要摘或位锚要改"
                continue
            funcs = [node for node in ast.walk(tree)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol]
            assert funcs, f"{code} 的位锚 {origin}::{symbol} 里已经没有这枚函数（改名或搬走了）"
            inside = [
                node.lineno for func in funcs for node in ast.walk(func)
                if isinstance(node, ast.Constant) and node.value == code
            ]
            assert inside, f"{code} 已经不在 {origin}::{symbol} 里了 —— 位锚要跟着改，别改成会漂的行号"


def test_the_backend_register_and_the_frontend_alias_table_agree():
    """两头相等：新增裸码没人写人话句 -> 红；人话句失了出处 -> 红。folds_into 还得是真枚举成员。"""
    licensed, folds = set(_licensed_register()), set(_legacy_alias_folds())

    assert sorted(licensed - folds) == [], "后端记了账、前端没有归一，界面只能对它说兜底句：" + "、".join(
        sorted(licensed - folds))
    assert sorted(folds - licensed) == [], "前端在归一一枚后端没记账的裸码：" + "、".join(sorted(folds - licensed))
    declared = set(enum_codes())
    wrong = {code: entry["folds_into"] for code, entry in _licensed_register().items()
             if entry["folds_into"] not in declared}
    assert wrong == {}, f"folds_into 必须落在封闭枚举里：{wrong}"


def test_idempotency_key_required_is_named_on_every_side_that_matters():
    """R142 裁的那枚码：后端账、契约、行为用例、前端归一，四边都得还在。"""
    entry = _licensed_register()["idempotency_key_required"]
    assert entry["emitter"].endswith("::_enqueue_ask_turn"), entry["emitter"]
    assert "R142" in entry.get("ruling", ""), "这枚码的裁定要留在账里，别让下一个人重新查一遍"
    assert "契约变更" in entry["why"], "为什么不折叠的那笔账得写在原地"

    doc = _read(CONTRACT_DOC)
    row = [line for line in doc.splitlines()
           if re.fullmatch(r"\|\s*`?POST /api/v1/ask`?\s*\|\s*400\s*\|\s*`idempotency_key_required`\s*\|\s*", line)]
    assert row, "契约 /ask 状态表里那行 400 idempotency_key_required 不见了"
    assert re.search(r"detail `idempotency_key_required`", doc), "契约正文不再指名这枚码，光剩状态表不算登记"

    r37 = _read(R37_ENQUEUE_TEST)
    assert re.search(r"detail\s*==\s*\"idempotency_key_required\"", r37), (
        "行为用例不再逐字钉这枚字符串：要么它被改名（那是契约变更，得重开单子），"
        "要么这枚裸码失去了最后一道行为保护")


def test_the_scanner_and_the_alias_parser_are_not_blind():
    """反空转：对照组 IN/OUT 都看得见，合成源里的新裸码必须被抠出来，散文与 f-string 不许误伤。"""
    emitted = _static_detail_codes()
    assert "resource_not_found" in emitted, "扫描器连枚举码都认不出来了"
    assert "idempotency_key_required" in emitted and "upload_too_large" in emitted
    assert any(anchor.endswith("::_enqueue_ask_turn") for anchor in emitted["idempotency_key_required"])
    assert len(_licensed_register()) >= MIN_REGISTER_TODAY

    caught = _detail_codes_from(
        "from fastapi import HTTPException\n"
        "async def handler():\n"
        "    raise HTTPException(status_code=400, detail='brand_new_unlicensed_code')\n",
        "synthetic.py",
    )
    assert caught == {"brand_new_unlicensed_code": ["synthetic.py::handler"]}, caught

    noise = _detail_codes_from(
        "from fastapi import HTTPException\n"
        "async def handler(user_id):\n"
        "    raise HTTPException(status_code=404, detail='用户不存在')\n"
        "    raise HTTPException(status_code=400, detail=f'动态 {user_id}')\n"
        "    raise HTTPException(status_code=403, detail=decision.reason_code)\n",
        "synthetic.py",
    )
    assert noise == {}, f"扫描器把人话与动态值当成了码：{noise}"
    assert _legacy_alias_folds()["idempotency_key_required"] == "validation_error"


# ==================== 判据③：位锚不许漂回裸行号 ====================


def test_the_code_table_and_its_note_anchor_on_symbols_not_line_numbers():
    """R142 自己的那一段（码表 + 表下注）不许出现 ``foo.py:123``：本仓已经被"一改就漂的行号"
    咬过不止一次。同节里 R10 那张鉴权码表还留着五处裸行号，它属于别人的正文，本单只具名交总控，
    不替它猜该指哪一枚 raise。
    """
    block = _owned_error_block()

    offenders = re.findall(r"[A-Za-z0-9_./\\-]+\.(?:py|js|vue|md):\d+", block)
    assert offenders == [], "码表与表下注里又写了会漂的裸行号，改成指名函数名/符号名：" + ", ".join(sorted(set(offenders)))


def test_the_note_stops_counting_the_register_too():
    """同一条规矩适用于新账：几枚裸码是运行时的量，谁在记账才是契约该说的话。"""
    block = _owned_error_block()

    counting = re.findall(r"\d+\s+(?:names|codes|bare)", block, re.IGNORECASE)
    assert counting == [], f"注里又在数名字：{counting}"
    assert REGISTER_NAME in block, "表下注不再指名那本裸码账"
    assert "idempotency_key_required" in block, "R142 裁过的那枚码得从契约里看得见去向"
