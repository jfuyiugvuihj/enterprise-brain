r"""R396 · 常驻形状钉：那几本行号账**再抄一次数字就当场红**，锚点读不到必须**喊**不许静默跳过。

病灶（工单 R396 §一，总控本机实测；本单基点 `49489c3`）：`tests/test_r377_*` 与
`tests/test_r383_catalog_*` 两枚在册尺子把 `app/documents/catalog.py` 的行号抄成常量——
`RAISE_SITES` 抄抛点、`GUARD_BY_MODULE` 抄五枚 catch-all、`CALL_SITES` 抄五枚调用点、
`GATE_503_EXIT` 抄那枚 503 出口，r383 另抄 `GATE_EXIT_LINE` 与一枚五格行号列表。代价落在生产码上：
`ae2fbb4`（R394）为了并树被逼成行数中性（catalog 903⇒903），`3337f9a`（R392）撑长
`app/memory/*` 之后 r377 当场重取十枚行号。

已做的派生（判据 1，手法照 R346 @00945a9，机器在 `scripts/r396_anchor_ledger.py`）：账上每格换成
一枚**锚点 token**（符号名 + 该符号内唯一的语句形状），行号运行时现读；`tests/test_r346_*` 一格未动。

本件是那笔债的看守，常驻四件事：

  ① 四把尺子扫「两枚被改口的件 + 本件自己」：模块级账里出现字面整数、顶着行号名字的账里躺着整数、
     锚点账里混进整数、断言拿
     现场读数比抄下来的整数——三种形状任出现一种就当场红（判据 6）。尺子自己在
     `test_the_shape_rulers_fire_on_the_shape_they_ban` 里拿合成源码自证量得到、也不冤枉合法的
     计数与状态码（照 R346 那枚自证钉的样子）。
  ② 契约钉：`_CONTRACT` 逐枚点名每本账记哪几枚生产文件、每本几格、用什么锚点种类；账被改名、
     被删、少一格、多一格、退回抄数，全部红在明处。
  ③ K1 常驻版：在被记账文件里插一行（**只在内存里**，盘上零写入）⇒ 那一本的每一格自己跟过去，
     而结构腿（现场扫 try/handler）与锚点腿在挤过的树上仍逐格相等。这正是抄数做不到的那一格。
  ④ K2 常驻版：把锚点改名（闸函数 / handler 里那句日志 / 调用点所在的 scope / 抛点原文 /
     `chat.py` 那枚被调符号连 def 带调用点整枚改名）⇒ 机器必须抛 `AssertionError` 并点名锚点
     （`锚点现读不到`），绝不静默跳过（静默跳过 = 假绿，比红更坏）；另钉「三枚件里不许有
     skip/xfail/豁免名单」，从源头堵掉"用豁免过关"这条路。
  ⑤ 两族账分开点名：单站点账逐格一行，多站点账（`calls:`，R396 令一那本 `CHAT_MIGRATION_GATES`）
     只记被调符号、落点枚数由现场说——它同时是 R397 在途那格「合法多一枚调用点」的保险。

🔴 所有变异都在内存副本上叠（`pad_above` / `str.replace` / `tmp_path`），本件一次都不写 `app/**`。
   落盘插行既越写域，又会让门里其他件在同一枚 HEAD 上量出两种结果。

🔴 效力边界：本件只读源码文本（变异一律在内存副本上叠，`write_text` 只写 pytest 的 `tmp_path`），
不写生产码、不起服务、不连库、不打模型；它证明的是「账与现场同序、抄数进不了账」，catalog 那枚闸
的运行时行为仍由 r377 / r383 自己的格子负责。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts import r396_anchor_ledger as anchor

REPO = Path(__file__).resolve().parents[1]
R377 = "tests/test_r377_migrations_first_family_is_contained_at_the_store_layer.py"
R383 = "tests/test_r383_catalog_refuses_a_store_that_is_not_there.py"
SELF = "tests/test_r396_line_numbers_are_derived_not_copied.py"
WATCHED = (R377, R383, SELF)

CAT = "app/documents/catalog.py"
AUTH = "app/common/auth.py"
LONG_TERM = "app/memory/long_term.py"
PROFILE = "app/memory/profile.py"
ALERTS = "app/api/v1/alerts.py"
CHAT = "app/api/v1/chat.py"
BOOKED = (ALERTS, AUTH, CAT, CHAT, LONG_TERM, PROFILE)

#: 「像行号」的地板。写成品字（`4 * 10`）而不是 `40`：本件的模块级尺子也扫本件自己。
SHAPE_FLOOR = 4 * 10
#: 反证刀 K1 在内存里插的行数（不落盘，见插行那枚常驻件）。
K1_PAD = 7
#: HTTP 状态码长得很像行号（405 尤其），逐枚具名豁免——只豁免这一族，不豁免"某个数字"。
STATUS_CODES = frozenset(
    {200, 201, 204, 301, 302, 304, 400, 401, 403, 404, 405, 409, 413, 418, 422, 429, 500, 501, 502, 503, 504}
)
#: 交出「行号」的量具：断言里出现这些名字/调用，就算现场读数那一侧。
LINE_READINGS = frozenset(
    {
        "_anchor_lines", "_anchor_one", "anchor_line", "derive_ledger", "call_line", "guard_line",
        "http_raise_line", "raise_statement_line", "_raise_sites", "_raise_sites_with_status",
        "_anchor_sites", "_guarded_call_lines", "_unguarded_call_lines", "_db_ready_reads", "splitlines",
        "anchor_sites", "call_sites", "derive_sites", "production_branch_lines",
        "line_ledger", "readings", "booked", "drift_report", "repo_sources",
    }
)
#: 这几枚吃进去的整数是「数了几枚」，不是「第几行」：与 R346 同一条口径，只此一家。
COUNTISH = frozenset({"len", "sum", "count", "min", "max"})
ANCHOR_PREFIXES = tuple(f"{kind}:" for kind in anchor.ANCHOR_KINDS)
#: 豁免的形状用拼出来的常量，免得本件自己的源码文本撞上按 AST 取证的那枚扫描（照 R346）。
SKIP_TAIL = ("skip", "skip" + "if", "x" + "fail")
LEDGER_ARGS = ("allow" + "_list", "ex" + "empt", "exemptions", "ignore", "exclude")

#: 账本契约：逐枚点名「哪本账、记哪几枚生产文件、每本几格、用什么锚点种类」。
_CONTRACT = {
    R377: {
        "RAISE_SITES": ((anchor.KIND_RAISE, AUTH, 1), (anchor.KIND_RAISE, CAT, 1),
                        (anchor.KIND_RAISE, LONG_TERM, 1), (anchor.KIND_RAISE, PROFILE, 1)),
        "GUARD_BY_MODULE": ((anchor.KIND_GUARD, AUTH, 2), (anchor.KIND_GUARD, CAT, 5),
                            (anchor.KIND_GUARD, LONG_TERM, 2), (anchor.KIND_GUARD, PROFILE, 2)),
        "CALL_SITES": ((anchor.KIND_CALL, AUTH, 2), (anchor.KIND_CALL, CAT, 5),
                       (anchor.KIND_CALL, LONG_TERM, 2), (anchor.KIND_CALL, PROFILE, 2)),
        "GATE_503_EXIT": ((anchor.KIND_HTTP_RAISE, CAT, 1),),
        "ALERTS_GATE_503_EXIT": ((anchor.KIND_HTTP_RAISE, ALERTS, 1),),
        #: R396 令一：`chat.py` 那本账只记**被调符号**，落点几枚由现场说（在途 R397 正往那棵加读腿闸）。
        "CHAT_MIGRATION_GATES": ((anchor.KIND_CALLS, CHAT, 1),),
    },
    R383: {
        "GATE_EXIT_ANCHORS": ((anchor.KIND_HTTP_RAISE, CAT, 1),),
        "ENSURE_CALL_ANCHORS": ((anchor.KIND_CALL, CAT, 5),),
    },
}
LEDGER_CASES = [(ruler, name) for ruler in sorted(_CONTRACT) for name in sorted(_CONTRACT[ruler])]



# ------------------------------------------------------------------------------ 现读与四把形状尺子
def _source(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"被扫的文件不见了: {path}"
    return path.read_text(encoding="utf-8")


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except ValueError:
        return None


def _int_values(node: ast.AST) -> list[int]:
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
        and isinstance(child.value, int)
        and not isinstance(child.value, bool)
    ]


def _status_exemption(source: str) -> frozenset[int]:
    """唯一那条豁免：只认「本件自己模块级那枚字面量 frozenset，且逐枚都在 HTTP 定义域里」。"""
    for name, node in _module_assignments(source):
        if name != "STATUS_CODES":
            continue
        members = [value for value in _int_values(node) if anchor.is_http_status(value)]
        if members and len(members) == len(_int_values(node)):
            return frozenset(members)  # 一枚成员都不是状态码形状，这格就不配拥有豁免
    return frozenset()


def _module_assignments(source: str) -> list[tuple[str, ast.AST]]:
    tree = ast.parse(source)
    rows: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names, value = [t.id for t in node.targets if isinstance(t, ast.Name)], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names, value = [node.target.id], node.value
        else:
            continue
        if value is not None:
            rows.extend((name, value) for name in names)
    return rows


def _anchor_cells(value) -> list[str]:
    if isinstance(value, dict):
        return [cell for inner in value.values() for cell in _anchor_cells(inner)]
    if isinstance(value, (tuple, list, set)):
        return [cell for inner in value for cell in _anchor_cells(inner)]
    if isinstance(value, str) and value.startswith(ANCHOR_PREFIXES):
        return [value]
    return []


def _live_ledgers(source: str) -> dict[str, object]:
    """交出这枚件里所有「装着锚点 token 的模块级账」（按形状认，不按名字猜）。"""
    ledgers = {}
    for name, node in _module_assignments(source):
        value = _literal(node)
        if value is not None and _anchor_cells(value):
            ledgers[name] = value
    return ledgers


def _ruler_module_numbers(label: str, source: str) -> list[str]:
    """尺子 1：模块级账里出现「看着像行号」的抄数（唯一豁免 = 本件自己那枚状态码字面量集合）。"""
    exempt = _status_exemption(source)
    offenders = []
    for name, node in _module_assignments(source):
        for value in _int_values(node):
            if value >= SHAPE_FLOOR and value not in exempt:
                offenders.append(f"{label}:{name} 里抄了枚字面整数 {value}（行号一律现读）")
    return offenders


def _ruler_line_named(label: str, source: str) -> list[str]:
    """尺子 2：顶着 `*_LINE` / `*LEDGER*` 名字的模块级格子里一枚整数都不许躺（`GATE_EXIT_LINE` 原形）。"""
    offenders = []
    for name, node in _module_assignments(source):
        if not anchor.is_line_named(name):
            continue
        for value in _int_values(node):
            offenders.append(f"{label}:{name} 是一枚行号账，格子里躺着字面整数 {value}")
    return offenders


def _ruler_numbers_in_ledgers(label: str, source: str) -> list[str]:
    """尺子 3：锚点账里混进任何整数 = 有人把抄数塞回锚点旁边。"""
    offenders = []
    for name, node in _module_assignments(source):
        value = _literal(node)
        if value is None or not _anchor_cells(value):
            continue
        for number in _int_values(node):
            offenders.append(f"{label}:{name} 这本锚点账里混进了字面整数 {number}")
    return offenders


def _names_and_calls(node: ast.AST) -> tuple[set[str], set[str]]:
    names: set[str] = set()
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Call):
            target = child.func
            if isinstance(target, ast.Attribute):
                calls.add(target.attr)
            elif isinstance(target, ast.Name):
                calls.add(target.id)
    return names, calls


def _reading_bound_names(body: ast.AST) -> set[str]:
    """一枚作用域里「被行号读数喂出来的局部名字」，迭代到不动点（别名也算，R346 那条教训）。"""
    bound: set[str] = set()
    while True:
        grown = set(bound)
        for node in ast.walk(body):
            if not isinstance(node, ast.Assign):
                continue
            names, calls = _names_and_calls(node.value)
            if calls & LINE_READINGS or names & bound:
                grown.update(target.id for target in node.targets if isinstance(target, ast.Name))
        if grown == bound:
            return bound
        bound = grown


def _touches_readings(node: ast.AST, bound: set[str]) -> bool:
    names, calls = _names_and_calls(node)
    return bool(calls & LINE_READINGS or names & bound)


def _count_ids(node: ast.AST) -> set[int]:
    ids: set[int] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        target = child.func
        name = target.attr if isinstance(target, ast.Attribute) else (
            target.id if isinstance(target, ast.Name) else ""
        )
        if name in COUNTISH:
            ids.update(id(sub) for sub in ast.walk(child))
    return ids


def _ruler_readings_versus_copied(label: str, source: str) -> list[str]:
    """尺子 4：现场读数与抄下来的整数出现在同一枚比较里（判据 1 说的「等号两侧」）。

    这一把**不认状态码豁免**：与行号读数比对的那一枚整数就是行号，哪怕它恰好也是 405。
    """
    offenders: set[str] = set()
    tree = ast.parse(source)
    bodies: list[ast.AST] = [tree]
    bodies += [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for body in bodies:
        bound = _reading_bound_names(body)
        for node in ast.walk(body):
            if not isinstance(node, ast.Compare):
                continue
            sides = [node.left, *node.comparators]
            for index, side in enumerate(sides):
                if not _touches_readings(side, bound):
                    continue
                for other in sides[:index] + sides[index + 1:]:
                    exempt = _count_ids(other)
                    for child in ast.walk(other):
                        if (
                            isinstance(child, ast.Constant)
                            and isinstance(child.value, int)
                            and not isinstance(child.value, bool)
                            and child.value >= SHAPE_FLOOR
                            and id(child) not in exempt
                        ):
                            offenders.add(f"{label}: 断言 :{node.lineno} 拿现场读数比抄下来的 {child.value}")
    return sorted(offenders)


RULERS = (
    ("模块级抄数", _ruler_module_numbers),
    ("行号命名账", _ruler_line_named),
    ("锚点账混整数", _ruler_numbers_in_ledgers),
    ("读数比抄数", _ruler_readings_versus_copied),
)
RULER_BY_NAME = dict(RULERS)


def _dotted(node: ast.AST) -> str:
    """`pytest.mark.skip` 这种链的完整点号名；链根不是名字就交空串（照 R346 的取证口径）。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _structural(source: str) -> dict[int, int]:
    """结构腿（与两枚在册尺子同一口径，这里独立实现一份）：`{被 catch-all 兜住的调用行: handler 行}`。"""
    guarded: dict[int, int] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Try):
            continue
        handlers = [h for h in node.handlers if h.type is None or "Exception" in ast.dump(h.type)]
        if not handlers:
            continue
        inner = min(h.lineno for h in handlers)
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_ensure":
                guarded[call.lineno] = inner
    return guarded



# --------------------------------------------------------------------- 账的读法与合成形状（给尺子自证用）
def _ledger_table(ruler: str, name: str):
    ledgers = _live_ledgers(_source(ruler))
    assert name in ledgers, f"{ruler} 里读不到账 {name}：账被删了、改名了，还是退回抄数了？"
    return ledgers[name]


def _cells(table) -> tuple[str, ...]:
    return tuple(_anchor_cells(table))


def _bookings(ruler: str, name: str) -> list[tuple[str, tuple[str, ...]]]:
    """摊平一本账：dict 账按 key（生产文件）分组；单文件账的落点由 `_CONTRACT` 那一格点名。"""
    table = _ledger_table(ruler, name)
    if isinstance(table, dict):
        return [(relative, _cells(cells)) for relative, cells in table.items()]
    booked = sorted({relative for _kind, relative, _count in _CONTRACT[ruler][name]})
    assert len(booked) == 1, f"{ruler}:{name} 这本账不是 dict，契约里也没有唯一落点：{booked}"
    return [(booked[0], _cells(table))]


def _cells_for(ruler: str, name: str, relative: str) -> tuple[str, ...]:
    return dict(_bookings(ruler, name))[relative]


def _contract_cases() -> list[tuple[str, str, str, str, int]]:
    return [
        (ruler, ledger, kind, relative, count)
        for ruler in sorted(_CONTRACT)
        for ledger in sorted(_CONTRACT[ruler])
        for kind, relative, count in _CONTRACT[ruler][ledger]
    ]


def _read_ledger(relative: str, cells: tuple[str, ...], sources: dict[str, str]) -> tuple[int, ...]:
    """按账的形状现读：`calls:` 一本交回所有落点（升序去重），其余逐格一行。

    两族混着读就是假绿——`anchor_line()` 遇见 `calls:` 会当场喊形状不认，所以这里先替它把
    「哪一本该用哪条读法」说清楚，而不是悄悄退回其中一条。
    """
    multi = [anchor.is_multi_site(cell) for cell in cells]
    assert all(multi) or not any(multi), f"{relative} 的一本账里混了两种锚点形状：{cells}"
    if multi[0]:
        return anchor.derive_sites(sources, relative, cells)
    return anchor.derive_ledger(sources, relative, cells)


#: 一格一只落点 vs 一格多落点（`calls:`）：两族分开点名，谁也不许从参数化里漏出去。
CONTRACT_CASES = _contract_cases()
SINGLE_SITE_CASES = [case for case in CONTRACT_CASES if case[2] != anchor.KIND_CALLS]
MULTI_SITE_CASES = [case for case in CONTRACT_CASES if case[2] == anchor.KIND_CALLS]


_CATALOG_GATE = "http_raise:_require_ready_store:503"
_CATALOG_CALL = "call:peek_next_document_version:_ensure"
_CATALOG_GUARD = "guard:current listing fallback"
#: 抛点那一格的锚点从 r377 现读（不在本件里第二遍抄那句原文，改口了本件跟着红）。
_CATALOG_RAISE = _cells_for(R377, "RAISE_SITES", CAT)[0]
#: 令一那本账的锚点也从 r377 现读：本件不第二次抄被调符号名，改了名两边一起喊。
_CHAT_GATE = _cells_for(R377, "CHAT_MIGRATION_GATES", CHAT)[0]

#: K2 的靶子：(说明, 被动的生产文件, 现场里那句锚点依据, 改成什么, 用哪枚锚点, 期望机器喊哪一句)
BROKEN_ANCHORS = (
    ("闸函数改名", CAT, "def _require_ready_store(", "def _require_ready_store__r396(", _CATALOG_GATE,
     anchor.ANCHOR_MISSING),
    ("handler 里那句日志改名", CAT, _CATALOG_GUARD.partition(":")[2], "listing fallback moved house",
     _CATALOG_GUARD, anchor.ANCHOR_MISSING),
    ("调用点所在的 scope 改名", CAT, "def peek_next_document_version(", "def peek_next_document_version__r396(",
     _CATALOG_CALL, anchor.ANCHOR_MISSING),
    ("抛点那句原文改口", CAT, "run migrations first", "run the migrations first please", _CATALOG_RAISE,
     anchor.ANCHOR_MISSING),
    ("迁移闸连 def 带调用点整枚改名（多站点账读不到照样喊）", CHAT, "_require_migrated_tables(conn,",
     "_require_migrated_tables__r396(conn,", _CHAT_GATE, anchor.ANCHOR_MISSING),
)
#: 抄数退回账上的四种形状（全部合成，不碰生产码）：(说明, 合成源码, 该由哪把尺子抓到)
BANNED_CASES = (
    ("模块级一枚裸行号（`GATE_EXIT_LINE = 405` 的原形）", 'GATE_EXIT_LINE = 405\nADMIN = "r396"\n',
     "行号命名账"),
    ("锚点旁边躺着一枚行号（`(609, 739, 782)` 的原形）",
     'CALL_SITES = {"app/documents/catalog.py": ("call:current_documents:_ensure", 782)}\n', "锚点账混整数"),
    ("现场读数与裸行号比对", "def test_gate():\n    exits = _raise_sites(tree, 503)\n    assert exits == [405]\n",
     "读数比抄数"),
    ("行号先进局部变量、再别名一圈去比（R346 抓过的那族）",
     "def test_sites():\n    ledger = _anchor_lines(relative, CELLS)\n    today = sorted(ledger)\n"
     "    assert today == [609, 739, 782, 817, 890]\n",
     "读数比抄数"),
)
#: 三种合法形状：尺子不许误伤（计数、状态码、与派生名比）。
LEGAL_CASES = (
    ("数了几枚不是第几行", "def test_count():\n    assert len(_db_ready_reads(source)) == 1\n"),
    ("HTTP 状态码不是行号", "def test_face():\n    assert response.status_code == 503\n"),
    ("读数与派生出来的名字比", "def test_derived():\n    assert _raise_sites(tree, 503) == [gate_exit]\n"),
    ("锚点账一格数字都不带",
     'CALL_SITES = {"app/documents/catalog.py": ("call:current_documents:_ensure",)}\n'),
)



# --------------------------------------------------------------------------------------- 账本契约
@pytest.mark.parametrize(("ruler", "ledger"), LEDGER_CASES)
def test_the_contract_covers_every_live_ledger(ruler, ledger):
    """判据 6 的地基：那几枚件里所有「装着锚点的模块级账」都在契约里，没有漏网的平行账本。"""
    live = sorted(_live_ledgers(_source(ruler)))

    assert live == sorted(_CONTRACT[ruler]), f"{ruler} 里的账本清单与契约不等：{live}"
    assert ledger in live, f"{ruler} 里读不到 {ledger}"


@pytest.mark.parametrize(("ruler", "ledger", "kind", "relative", "count"), CONTRACT_CASES)
def test_each_ledger_books_the_contracted_cells(ruler, ledger, kind, relative, count):
    """每本账逐枚点名生产文件、格数与锚点种类：少一格、多一格、种类换掉，全红在明处。"""
    cells = _cells_for(ruler, ledger, relative)

    assert len(cells) == count, f"{ruler}:{ledger} 在 {relative} 上该有 {count} 格，实收 {cells}"
    for cell in cells:
        assert anchor.anchor_fields(cell)[0] == kind, f"{ruler}:{ledger} 锚点 {cell} 的种类不是 {kind}"


@pytest.mark.parametrize(("ruler", "ledger", "kind", "relative", "count"), SINGLE_SITE_CASES)
def test_every_anchor_resolves_to_exactly_one_line(ruler, ledger, kind, relative, count):
    """判据 1（单站点那一族）：账上每一格都读得到现场，且一格只读出一行。"""
    cells = _cells_for(ruler, ledger, relative)
    lines = _read_ledger(relative, cells, anchor.read_sources(relative))

    assert kind != anchor.KIND_CALLS, f"{ruler}:{ledger} 是多站点账，别从这一枚混进来"
    assert len(lines) == count == len(cells)
    assert len(set(lines)) == len(lines), f"{ruler}:{ledger} 逐格派生出行号撞车：{dict(zip(cells, lines))}"
    assert all(line > 1 for line in lines), f"{ruler}:{ledger} 派生出了不可能是行号的读数 {lines}"


@pytest.mark.parametrize(("ruler", "ledger", "kind", "relative", "count"), MULTI_SITE_CASES)
def test_a_multi_site_ledger_books_which_not_how_many(ruler, ledger, kind, relative, count):
    """判据 1 + R396 令一（多站点那一族）：账上只记**被调符号**，落点几枚由现场说。

    这里一枚枚数都不抄：R397 正往 `app/api/v1/chat.py` 加读腿闸（合法地多一枚调用点），
    抄死枚数的那格明天就红。要证的只有三件事——每一枚落点都真是那枚符号的直接调用、
    每一枚都还在生产分支里、读不到就当场喊（喊话由 K2 那枚常驻件守着）。
    """
    cells = _cells_for(ruler, ledger, relative)
    sources = anchor.read_sources(relative)
    sites = _read_ledger(relative, cells, sources)
    callee = anchor.anchor_symbol(cells[0])
    production = anchor.production_branch_lines(sources, relative)
    lines = sources[relative].splitlines()

    assert kind == anchor.KIND_CALLS, f"{ruler}:{ledger} 不是多站点账，走上面那一枚"
    assert len(cells) == count and all(anchor.anchor_fields(cell)[0] == kind for cell in cells)
    assert sites == anchor.call_sites(sources, relative, callee), f"{ruler}:{ledger} 落点与现场对不上"
    assert all(f"{callee}(" in lines[number - 1] for number in sites), (
        f"{ruler}:{ledger} 派生出的落点不是那枚符号的调用：{sites}"
    )
    assert sum(1 for line in lines if line.lstrip().startswith(f"def {callee}(")) == 1, (
        f"{ruler}:{ledger} 记的被调符号在 {relative} 里不止一枚 def，锚点不唯一"
    )
    assert all(not lines[number - 1].lstrip().startswith("def ") for number in sites), (
        f"{ruler}:{ledger} 把 def 那一行也数成了落点：{sites}"
    )
    assert set(sites) <= production, f"{ruler}:{ledger} 落点长到了生产分支之外：{sorted(set(sites) - production)}"



def test_the_contract_books_exactly_the_booked_production_files():
    """契约里点名的落点文件 == `BOOKED`：谁新添一本记别的文件的账，必须先在这格挂号。"""
    booked = sorted({
        relative
        for ledgers in _CONTRACT.values()
        for cases in ledgers.values()
        for _kind, relative, _count in cases
    })

    assert booked == sorted(BOOKED), (booked, sorted(BOOKED))


def test_the_two_rulers_book_the_same_catalog_call_sites():
    """两枚在册尺子对同一族调用点必须逐格同锚点：派生化之后，改一边就得当场对不上。"""
    from_r377 = _cells_for(R377, "CALL_SITES", CAT)
    from_r383 = _cells_for(R383, "ENSURE_CALL_ANCHORS", CAT)

    assert from_r377 == from_r383, (from_r377, from_r383)


def test_the_gate_anchor_is_shared_by_both_rulers():
    """那枚 503 出口在两枚件里是同一枚闸的**身份**，不是一枚抄下来的行号。"""
    assert _cells_for(R377, "GATE_503_EXIT", CAT) == _cells_for(R383, "GATE_EXIT_ANCHORS", CAT)


def test_the_raise_ledger_still_quotes_the_sentence_verbatim():
    """抛点账的 payload 仍是那句原文：改口 = 锚点读不到 = 红，这条腿一格没松。"""
    cell = _cells_for(R377, "RAISE_SITES", CAT)[0]
    statement = anchor.raise_statement_of(cell)

    assert "run migrations first" in statement, statement
    assert statement.startswith("raise RuntimeError("), statement
    assert anchor.anchor_symbol(cell) == "_ensure", cell


# ------------------------------------------------------------------------------------ 判据 6：形状钉
@pytest.mark.parametrize("relative", WATCHED)
def test_no_production_line_number_is_copied_into_a_ledger(relative):
    """常驻形状钉：这三枚件里任何一本账再抄一枚字面行号常量，本件当场红（判据 6）。"""
    source = _source(relative)
    offenders = [
        hit for _name, ruler in RULERS for hit in ruler(relative, source)
    ]

    assert offenders == [], "行号又被人抄回账上了：" + " / ".join(offenders)


@pytest.mark.parametrize(("label", "source", "ruler"), BANNED_CASES)
def test_the_shape_rulers_fire_on_the_shape_they_ban(label, source, ruler):
    """尺子自证（照 R346 那枚的样子）：禁的形状必须真量得到，否则判据 6 是句空话。"""
    offenders = RULER_BY_NAME[ruler]("synthetic:" + label, source)

    assert offenders, f"{ruler} 没量到它自己宣布禁止的形状：{label}"


@pytest.mark.parametrize(("label", "source"), LEGAL_CASES)
def test_the_shape_rulers_stay_silent_on_legal_shapes(label, source):
    """尺子不冤枉合法形状：数了几枚、状态码、与派生名比，都不算抄行号。"""
    fired = [name for name, ruler in RULERS if ruler("synthetic:" + label, source)]

    assert fired == [], f"{label} 被 {fired} 误伤"


def test_the_status_code_exemption_is_narrow_and_named():
    """唯一那条豁免（HTTP 状态码）自己也得钉住：逐枚落在协议定义域，且只能写在那枚字面量集合里。"""
    assert _status_exemption(_source(SELF)) == STATUS_CODES, "豁免表被换成了可变口径"
    assert all(anchor.is_http_status(code) for code in STATUS_CODES), sorted(STATUS_CODES)
    assert _status_exemption(BANNED_CASES[0][1]) == frozenset(), "一枚裸行号不该自带豁免"


# ------------------------------------------------------------------------------ K1：插一行账自己跟上
@pytest.mark.parametrize(("ruler", "ledger"), LEDGER_CASES)
def test_inserting_a_line_moves_the_ledger_not_the_door(ruler, ledger):
    """判据 2 的 K1 常驻版：在被记账文件里插一行 ⇒ 那一本的每一格自己跟着搬（只在内存里）。"""
    for relative, cells in _bookings(ruler, ledger):
        source = _source(relative)
        before = _read_ledger(relative, cells, {relative: source})
        crowded = {relative: anchor.pad_above(source, min(before), K1_PAD)}
        after = _read_ledger(relative, cells, crowded)

        assert after == tuple(line + K1_PAD for line in before), (
            f"{ruler}:{ledger} 在 {relative} 上方插 {K1_PAD} 行以后账没跟上：{before} -> {after}"
        )


def test_the_ledger_follows_a_symbol_that_moved(tmp_path):
    """把整棵文件复制进 tmp_path 并在 `_ensure` 头上插两行：账自己跟上，盘上那一棵一个字节没动。"""
    moved_by = 2
    source = _source(CAT)
    assert source.count("def _ensure():") == 1
    copy = tmp_path / CAT
    copy.parent.mkdir(parents=True)
    copy.write_text(source.replace("def _ensure():", "def _ensure():\n    pass\n", 1), encoding="utf-8")
    cells = _cells_for(R383, "ENSURE_CALL_ANCHORS", CAT)
    base = anchor.derive_ledger({CAT: source}, CAT, cells)
    after = anchor.derive_ledger({CAT: copy.read_text(encoding="utf-8")}, CAT, cells)

    assert after == tuple(line + moved_by for line in base), (base, after)
    assert _source(CAT) == source, "本件把被记账的文件写坏了：它只准读"


def test_the_two_legs_agree_on_the_crowded_tree():
    """插行之后锚点腿与结构腿仍逐格相等：这才是「债真的还掉了」，不是两条腿一起飘。"""
    source = _source(CAT)
    calls = _cells_for(R383, "ENSURE_CALL_ANCHORS", CAT)
    guards = _cells_for(R377, "GUARD_BY_MODULE", CAT)
    crowded = anchor.pad_above(source, min(_structural(source)), K1_PAD)
    crowded_tree = {CAT: crowded}

    assert sorted(_structural(source)) == sorted(anchor.derive_ledger({CAT: source}, CAT, calls))
    assert sorted(_structural(source).values()) == sorted(anchor.derive_ledger({CAT: source}, CAT, guards))
    assert sorted(_structural(crowded)) == sorted(anchor.derive_ledger(crowded_tree, CAT, calls))
    assert sorted(_structural(crowded).values()) == sorted(anchor.derive_ledger(crowded_tree, CAT, guards))

# ------------------------------------------------- R396 令一：合法多一枚调用点 = 账跟着长，门不许红
def test_a_new_legal_call_site_grows_the_derived_ledger():
    """R396 令一的 K1 常驻铰：往 `chat.py` 生产分支里再插一枚**合法**调用点 = 账跟着长、门仍绿。

    在途 R397 正做这件事（读腿闸内部转手 `_require_migrated_tables`，实测 2=>3 枚调用点）。老账抄的
    是 `chat.count("_require_migrated_tables(") == 3`，明天就被顶成假红；派生之后这一格只往账上添一枚
    落点。插行全程在内存里做，盘上那一棵一个字节都不动（最后那枚断言就是这条的自证）。
    """
    cells = (_CHAT_GATE,)
    sources = anchor.read_sources(CHAT)
    source = sources[CHAT]
    callee = anchor.anchor_symbol(_CHAT_GATE)
    before = _read_ledger(CHAT, cells, sources)
    rows = source.splitlines(keepends=True)
    lowest = before[-1]
    statement = rows[lowest - 1]
    indent = statement[: len(statement) - len(statement.lstrip())]
    crowded = "".join(
        rows[:lowest] + [f'{indent}{callee}(conn, "chat_r396_knife")\n'] + rows[lowest:]
    )
    crowded_tree = {CHAT: crowded}
    grown = _read_ledger(CHAT, cells, crowded_tree)
    production = anchor.production_branch_lines(crowded_tree, CHAT)
    textual = [
        number
        for number, row in enumerate(crowded.splitlines(), start=1)
        if f"{callee}(" in row and not row.lstrip().startswith("def ")
    ]

    ast.parse(crowded)
    assert len(before) >= 1, f"{CHAT} 的落点账是空的：锚点早就读不到了"
    assert grown == before + (lowest + 1,), f"多一枚合法调用点以后账没跟着长：{before} -> {grown}"
    assert grown == tuple(textual), f"两条腿在挤过的树上对不上：{grown} vs {textual}"
    assert set(grown) <= production, f"派生出的落点跑出了生产分支：{sorted(set(grown) - production)}"
    assert crowded.count(f"{callee}(") == source.count(f"{callee}(") + 1, (
        "老账那枚抄下来的数字本来就会跟着合法调用点漂：这正是它必须派生化的一格")
    assert anchor.read_sources(CHAT)[CHAT] == source, "本件把盘上的 chat.py 写坏了：它只准读"


def test_a_call_site_outside_the_production_branch_is_still_caught():
    """令一的后半句不许丢：每一枚派生落点仍逐格证它在生产分支里 = 越支的那一枚必被抓住。

    派生化不许把判据退化成「数得到就行」。这里在内存里把同一枚符号调到
    `if _is_production_environment():` 之外（模块级，插在它自己那枚 def 的上方）：落点照实多一枚，
    而那一枚必须被 `<= production` 那一腿点名，不是被静默吸收成一次合法增长。
    """
    cells = (_CHAT_GATE,)
    sources = anchor.read_sources(CHAT)
    source = sources[CHAT]
    callee = anchor.anchor_symbol(_CHAT_GATE)
    definition = min(
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == callee
    )
    rows = source.splitlines(keepends=True)
    stray = "".join(
        rows[: definition - 1] + [f'{callee}(conn, "r396_outside_leg")\n'] + rows[definition - 1 :]
    )
    stray_tree = {CHAT: stray}
    sites = _read_ledger(CHAT, cells, stray_tree)
    production = anchor.production_branch_lines(stray_tree, CHAT)

    ast.parse(stray)
    assert len(sites) == len(anchor.call_sites(sources, CHAT, callee)) + 1, sites
    assert sorted(set(sites) - production) == [definition], (
        f"越出生产分支的那一枚调用点没被抓到：{sorted(set(sites) - production)}")


# --------------------------------------- 判据 6 + 令一：不许把「落点枚数」抄回账上（行号地板抓不到）
def _booked_multi_site_callees() -> set[str]:
    """账上所有 `calls:` 锚点的被调符号：它们的落点**计数**就是 R396 令一不许抄回的那一枚整数。"""
    symbols: set[str] = set()
    for ruler, name in LEDGER_CASES:
        for _relative, cells in _bookings(ruler, name):
            symbols.update(
                anchor.anchor_symbol(cell) for cell in cells if anchor.is_multi_site(cell)
            )
    return symbols


def _copied_callee_counts(label: str, source: str, symbols: set[str]) -> list[str]:
    """量「拿被调符号的文本计数去比一枚裸整数」这一形状：老那一格 `... == 3` 就是它。

    行号地板（`SHAPE_FLOOR`）天生抓不到枚数——枚数小于 40。所以这一族单独立尺：只有**多站点账
    记过的那枚被调符号**、且同一枚比较的另一侧是一枚裸整数时才算犯。`count(那句原文) == 1`
    （R384 留给「这句话全文只有一枚」的合法计数）与 `count(...) == len(...)`（两条现读腿互校）
    都不在射程里：它们记的不是派生落点的枚数。
    """
    offenders: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        sides = [node.left, *node.comparators]
        bare = [
            side
            for side in sides
            if isinstance(side, ast.Constant)
            and isinstance(side.value, int)
            and not isinstance(side.value, bool)
        ]
        if not bare:
            continue
        for side in sides:
            for call in (child for child in ast.walk(side) if isinstance(child, ast.Call)):
                target = call.func
                name = target.attr if isinstance(target, ast.Attribute) else (
                    target.id if isinstance(target, ast.Name) else ""
                )
                if name not in COUNTISH:
                    continue
                for argument in call.args:
                    if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
                        continue
                    offenders.update(
                        f"{label}: 断言 :{node.lineno} 把 {symbol} 的落点枚数抄成了裸整数 "
                        f"{[item.value for item in bare]}"
                        for symbol in sorted(symbols)
                        if f"{symbol}(" in argument.value
                    )
    return sorted(offenders)


@pytest.mark.parametrize("relative", WATCHED)
def test_nobody_books_a_count_of_the_derived_call_sites(relative):
    """判据 6 + R396 令一：那几枚件里再拿「被调符号的计数 == 裸整数」记账，当场红。

    防的就是下一班图省事：`chat.count("_require_migrated_tables(") == 3` 那一格在基点是死的，
    在途 R397 一加读腿闸就把它顶红；抄回来的人只会把 3 改成 4，明天照红。
    """
    symbols = _booked_multi_site_callees()

    assert symbols, "账上一枚 `calls:` 多站点锚点都没有：令一那本账被整枚删了？"
    assert _copied_callee_counts(relative, _source(relative), symbols) == [], (
        f"{relative} 把派生落点的枚数抄成了裸整数：R397 一加读腿闸它就红")


def test_the_callee_count_ruler_fires_on_the_shape_it_bans():
    """尺子自证：把老那一格喂给它必须量得到，同时不冤枉两族合法形状（哑尺比没尺更坏）。"""
    symbols = _booked_multi_site_callees()
    callee = sorted(symbols)[0]
    banned = f'def probe(chat):\n    assert chat.count("{callee}(") == 3, "账要重取"\n'
    sentence = f'def probe(chat):\n    assert chat.count("{callee}") == 1\n'
    two_legs = f'def probe(chat, rows):\n    assert chat.count("{callee}(") == len(rows)\n'

    assert _copied_callee_counts("合成·抄枚数", banned, symbols), "老形状逃过了尺子：这枚尺子是哑的"
    assert not _copied_callee_counts("合成·句子计数", sentence, symbols), (
        "冤枉了「这句话全文只有一枚」那一族合法计数")
    assert not _copied_callee_counts("合成·两腿互校", two_legs, symbols), (
        "冤枉了两条现读腿互校：那一侧不是裸整数")


# ------------------------------------------------------------------------ K2：锚点读不到必须喊，不许静默跳过
@pytest.mark.parametrize(("label", "relative", "needle", "into", "cell", "shout"), BROKEN_ANCHORS)
def test_a_broken_anchor_shouts_rather_than_skipping(label, relative, needle, into, cell, shout):
    """判据 2 的 K2 常驻版：锚点被改名/搬走 ⇒ 当场点名锚点，绝不静默跳过（跳过 = 假绿，比红更坏）。"""
    source = _source(relative)
    assert source.count(needle) >= 1, f"靶子本身对不上：{label} {needle}"
    mutated = source.replace(needle, into)
    assert mutated != source, f"{label} 没改成任何东西"

    with pytest.raises(AssertionError) as caught:
        anchor.anchor_sites({relative: mutated}, relative, cell)
    message = str(caught.value)

    assert message.startswith(shout), (label, message)
    assert cell in message, f"喊了却没点名锚点，运维照句子找不到门：{label} {message}"


@pytest.mark.parametrize("cell", ("line:405", "616", "call:current_documents"))
def test_a_number_dressed_as_an_anchor_is_rejected_by_shape(cell):
    """抄数伪装成锚点（`line:405`、裸 `"616"`、缺 payload）也算红：形状不认就当场喊。"""
    with pytest.raises(AssertionError) as caught:
        anchor.anchor_line(anchor.read_sources(CAT), CAT, cell)

    assert str(caught.value).startswith(anchor.ANCHOR_SHAPE), str(caught.value)


@pytest.mark.parametrize("relative", WATCHED)
def test_nobody_opens_an_exemption_for_the_derivation(relative):
    """三枚件都没有豁免入口：不 skip、不 xfail、也没有「豁免名单」这种参数或形参（照 R346 判据⑤）。"""
    tree = ast.parse(_source(relative))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted.rpartition(".")[2] in SKIP_TAIL:
                offenders.append(f"{relative}:{node.lineno} {dotted}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            offenders.extend(
                f"{relative}:{node.lineno} {node.name} 的形参 {arg}"
                for arg in (a.arg for a in node.args.args)
                if arg in LEDGER_ARGS
            )
        elif isinstance(node, ast.keyword) and node.arg in LEDGER_ARGS:
            offenders.append(f"{relative}:{node.lineno} 实参 {node.arg}")

    assert offenders == [], "这枚门是靠豁免过关的：" + " / ".join(offenders)
