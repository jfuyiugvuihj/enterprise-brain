r"""R396 · 手抄行号账的派生化机器：账上写「身份」，行号在运行时现读。

病灶（工单 R396 §一，总控本机实测）：`tests/test_r377_migrations_first_family_is_contained_at_the_store_layer.py`
与 `tests/test_r383_catalog_refuses_a_store_that_is_not_there.py` 两枚在册尺子把
`app/documents/catalog.py` 的**行号抄成常量**，于是任何落在这一棵里的修复都必须做到「行数中性」
才能并树（`ae2fbb4`（R394）那一笔 906⇒906 就是这条债留下的疤；`3337f9a`（R392）撑长
`app/memory/*` 之后，r377 当场重取了十枚行号）。本机器把每一格从「位置」换成「锚点身份」：
符号名 + 该符号内唯一的语句形状，行号由 `anchor_line()` 现读。

手法照 `tests/test_r346_line_ledger_is_derived_not_copied.py`（R346 @00945a9）的两腿纪律：
锚点腿走「身份 → 现场」，结构腿走「AST 扫描 → 落点」，两条腿互相算不出对方，所以它们相等才是
真判据而不是同义反复。🔴 与 R346 同源的另一条纪律：本机器**只读源码文本**，每一枚量具都收
`sources`（`rel -> 源码文本`）作参数，所以反证刀可以在**内存里**往被记账文件插行，盘上一个字节
都不动 —— 全量门里跑它也安全。

锚点 token 语法（`kind:payload`；payload 内再按第一个 `:` 切）:

  · `call:<scope>:<callee>`      那枚 scope（具名函数，或 `-` = 模块顶层、剔除所有 def/class）里
                                 唯一一枚直接调用 `<callee>()` 的行。同 scope 内多一枚即红。
  · `guard:<needle>`             吃掉调用点的那枚 catch-all `except` 的 handler 行：判据是它的**函数体里**
                                 躺着一枚含 `<needle>` 的字符串常量，且这样的 handler 全文件只有这一枚、
                                 `<needle>` 在原文里也只出现一次。
  · `http_raise:<func>:<status>` 那枚闸函数里唯一一枚 `raise HTTPException(status_code=<status>, ...)` 的行。
  · `raise:<func>:<statement>`   那枚函数里语句原文（空白折叠后）逐字等于 `<statement>` 的 `raise` 的行。

🔴 读不到就读不到：0 枚、多枚、token 形状不认，三种都当场抛 `AssertionError` 并点名锚点，
绝不静默跳过（静默跳过 = 假绿，比红更坏）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Mapping

REPO = Path(__file__).resolve().parents[1]
#: 模块顶层那枚 scope 的写法（`call:-:_create_schema` = 「模块级 import 期探针里的那一枚调用」）。
MODULE_SCOPE = "-"
KIND_CALL = "call"
#: 多站点锚点：账上记「被调符号」，落点有几枚由现场说（`app/api/v1/chat.py` 那族闸是这种）。
KIND_CALLS = "calls"
KIND_GUARD = "guard"
KIND_HTTP_RAISE = "http_raise"
KIND_RAISE = "raise"
ANCHOR_KINDS = (KIND_CALL, KIND_CALLS, KIND_GUARD, KIND_HTTP_RAISE, KIND_RAISE)
#: 只有这一枚种类交多枚落点，其余一律「一格一行」（多一枚就红：那是抄数的老形状）。
MULTI_SITE_KINDS = (KIND_CALLS,)
#: 生产分支的形状：`if _is_production_environment():` 为真那一支。
PRODUCTION_RULER = "_is_production_environment"
#: HTTP 状态码的协议定义域：`STATUS_CODES` 那种豁免表只允许落在这里面。
HTTP_MIN = 100
HTTP_MAX = 599
#: 顶着这几个名字的模块级格子按「行号账」对待：一枚字面整数都不许躺（`GATE_EXIT_LINE` 是原形）。
LINE_NAMED = re.compile(r"(^|_)(LINE|LINES|LEDGER)(_|$)")
#: 三句喊话的前缀：反证刀 K2 就靠它们自证「锚点找不到了」是**红**而不是**跳**。
ANCHOR_MISSING = "锚点现读不到"
ANCHOR_AMBIGUOUS = "锚点现读多枚"
ANCHOR_SHAPE = "锚点 token 形状不认"


def read_sources(*rels: str) -> dict[str, str]:
    """按 utf-8 读盘上的源码文本：只读，不写，不改，一个字节都不回写。"""
    sources: dict[str, str] = {}
    for rel in rels:
        path = REPO / rel
        assert path.is_file(), f"被记账的文件不见了: {path}"
        sources[rel] = path.read_text(encoding="utf-8")
    return sources


def pad_above(source: str, line: int, count: int = 1) -> str:
    """在 ``line`` 那一行正上方插 ``count`` 行注释噪声（只在内存里）：反证刀 K1 的刀柄。"""
    lines = source.splitlines(keepends=True)
    assert 1 <= line <= len(lines), f"插行位置越界: {line} / 全文 {len(lines)} 行"
    pad = "".join(f"# r396 K1 drift pad #{index}\n" for index in range(count))
    return "".join(lines[: line - 1]) + pad + "".join(lines[line - 1 :])


def _tree(sources: Mapping[str, str], rel: str) -> ast.Module:
    assert rel in sources, f"本轮源码表里没有 {rel}：调用方得先把这一棵读进来"
    return ast.parse(sources[rel])


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _segment(source: str, node: ast.AST) -> str:
    return _normalize(ast.get_source_segment(source, node) or "")


def _require_one(label: str, rel: str, lines: list[int]) -> int:
    if not lines:
        raise AssertionError(f"{ANCHOR_MISSING}: {rel} 里锚点 {label} 现读 0 枚（锚点被改名、搬走或删了）")
    if len(lines) > 1:
        raise AssertionError(f"{ANCHOR_AMBIGUOUS}: {rel} 里锚点 {label} 现读 {len(lines)} 枚 {lines}")
    return lines[0]


def _is_catch_all(handler: ast.ExceptHandler) -> bool:
    return handler.type is None or "Exception" in ast.dump(handler.type)


def is_line_named(name: str) -> bool:
    """这枚名字是不是「行号账」的形状（`*_LINE` / `*LEDGER*`）：形状钉的命名腿。"""
    return bool(LINE_NAMED.search(name))


def is_http_status(value) -> bool:
    """只在协议定义域里的整数才允许当状态码豁免（行号可以长在它外面，码不能）。"""
    return isinstance(value, int) and not isinstance(value, bool) and HTTP_MIN <= value <= HTTP_MAX


def _named_function(sources: Mapping[str, str], rel: str, name: str, label: str = "") -> ast.AST:
    tree = _tree(sources, rel)
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    shout_for = label or f"symbol:{name}"
    if not found:
        raise AssertionError(
            f"{ANCHOR_MISSING}: {rel} 里锚点 {shout_for} 现读 0 枚（锚点被改名、搬走或删了）"
        )
    if len(found) > 1:
        raise AssertionError(
            f"{ANCHOR_AMBIGUOUS}: {rel} 里锚点 {shout_for} 现读 {len(found)} 枚，锚点不唯一"
        )
    return found[0]


def _owned_nodes(root: ast.AST, predicate) -> list[ast.AST]:
    """``root`` 自己那一层里的节点：钻进嵌套 def/class 就不算这一枚 scope 的。"""
    found: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if predicate(child):
                found.append(child)
            visit(child)

    visit(root)
    return found


def call_sites(sources: Mapping[str, str], rel: str, callee: str) -> tuple[int, ...]:
    """锚点腿（多站点）：全文件里 `<callee>()` 的直接调用点，枚数由现场说。

    🔴 读不到照样喊：0 枚 = 锚点被改名/搬走/删了，交空元组让上层静默通过就是假绿。
    """
    assert callee, f"{ANCHOR_SHAPE}: calls 锚点得写出被调符号"
    hits = sorted(
        {
            node.lineno
            for node in ast.walk(_tree(sources, rel))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == callee
        }
    )
    if not hits:
        raise AssertionError(
            f"{ANCHOR_MISSING}: {rel} 里锚点 {KIND_CALLS}:{callee} 现读 0 枚（锚点被改名、搬走或删了）"
        )
    return tuple(hits)


def production_branch_lines(sources: Mapping[str, str], rel: str) -> set[int]:
    """`if _is_production_environment():` 为真那一支盖住的行号集合（生产分支的形状）。"""
    covered: set[int] = set()
    for node in ast.walk(_tree(sources, rel)):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Call):
            continue
        ruler = node.test.func
        name = ruler.attr if isinstance(ruler, ast.Attribute) else (ruler.id if isinstance(ruler, ast.Name) else "")
        if name != PRODUCTION_RULER:
            continue
        for statement in node.body:
            covered.update(range(statement.lineno, (statement.end_lineno or statement.lineno) + 1))
    return covered


def call_line(sources: Mapping[str, str], rel: str, scope: str, callee: str) -> int:
    """锚点腿（调用点）：那枚 scope 里唯一一枚 ``<callee>()`` 直接调用的行。"""
    assert scope and callee, f"{ANCHOR_SHAPE}: call 锚点要写全 scope 与被调符号"
    label = f"{KIND_CALL}:{scope}:{callee}"
    root = _tree(sources, rel) if scope == MODULE_SCOPE else _named_function(sources, rel, scope, label)
    hits = _owned_nodes(
        root,
        lambda node: isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == callee,
    )
    return _require_one(f"call:{scope}:{callee}", rel, sorted({node.lineno for node in hits}))


def guard_line(sources: Mapping[str, str], rel: str, needle: str) -> int:
    """锚点腿（catch-all handler）：body 里躺着那枚 ``<needle>`` 字符串常量的 handler 行。"""
    assert needle, f"{ANCHOR_SHAPE}: guard 锚点得给一句 handler 体内唯一的语句形状"
    raw = sources[rel].count(needle)
    if raw != 1:
        shout = ANCHOR_MISSING if not raw else ANCHOR_AMBIGUOUS
        raise AssertionError(f"{shout}: {rel} 里锚点 {KIND_GUARD}:{needle} 原文出现 {raw} 次")
    hits = []
    for node in ast.walk(_tree(sources, rel)):
        if not isinstance(node, ast.ExceptHandler) or not _is_catch_all(node):
            continue
        strings = [
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        ]
        if any(needle in text for text in strings):
            hits.append(node.lineno)
    return _require_one(f"guard:{needle}", rel, sorted(set(hits)))


def _http_raise_lines(node: ast.AST, status: int) -> list[int]:
    found = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Raise) or not isinstance(child.exc, ast.Call):
            continue
        if not isinstance(child.exc.func, ast.Name) or child.exc.func.id != "HTTPException":
            continue
        for keyword in child.exc.keywords:
            if keyword.arg != "status_code":
                continue
            try:
                value = ast.literal_eval(keyword.value)
            except ValueError:
                continue  # 参数化的出口（``status_code=status``）不是本机器要锚的那一格
            if value == status:
                found.append(child.lineno)
    return sorted(found)


def http_raise_line(sources: Mapping[str, str], rel: str, func: str, status: str) -> int:
    """锚点腿（HTTP 出口）：那枚闸函数里唯一一枚 ``raise HTTPException(status_code=<status>)`` 的行。"""
    assert func and status.isdigit(), f"{ANCHOR_SHAPE}: http_raise 锚点要写全闸函数名与状态码"
    label = f"{KIND_HTTP_RAISE}:{func}:{status}"
    hits = _http_raise_lines(_named_function(sources, rel, func, label), int(status))
    return _require_one(f"http_raise:{func}:{status}", rel, hits)


def raise_statement_line(sources: Mapping[str, str], rel: str, func: str, statement: str) -> int:
    """锚点腿（抛点原文）：那枚函数里语句原文逐字等于 ``<statement>`` 的 ``raise`` 的行。"""
    assert func and statement.strip(), f"{ANCHOR_SHAPE}: raise 锚点要写全函数名与那句原文"
    source = sources[rel]
    wanted = _normalize(statement)
    label = f"{KIND_RAISE}:{func}:{statement}"
    hits = [
        node.lineno
        for node in ast.walk(_named_function(sources, rel, func, label))
        if isinstance(node, ast.Raise) and _segment(source, node) == wanted
    ]
    return _require_one(f"raise:{func}:{statement}", rel, sorted(set(hits)))


def anchor_fields(anchor: str) -> tuple[str, ...]:
    """交回 ``(kind, payload)``：形状不认就当场喊，不许蒙混成一格抄数。"""
    kind, _, rest = anchor.partition(":")
    if kind not in ANCHOR_KINDS:
        raise AssertionError(f"{ANCHOR_SHAPE}: {anchor!r} 不属于本机器认的 {ANCHOR_KINDS}")
    assert rest.strip(), f"{ANCHOR_SHAPE}: {anchor!r} 的 payload 是空的"
    return (kind, rest)


def anchor_symbol(anchor: str) -> str:
    """交出锚点里那枚符号身份（scope / 闸函数名 / 被调符号）：断言里不再第二次抄一遍名字。"""
    kind, rest = anchor_fields(anchor)
    if kind == KIND_GUARD:
        raise AssertionError(f"{ANCHOR_SHAPE}: guard 锚点的身份就是那句语句形状，它不带符号名")
    if kind == KIND_CALLS:
        return rest
    return rest.partition(":")[0]


def raise_statement_of(anchor: str) -> str:
    """从 ``raise:<func>:<statement>`` 里摘出那句抛点原文：给「改口就红」那一腿复用同一枚锚点。"""
    kind, rest = anchor_fields(anchor)
    assert kind == KIND_RAISE, f"{ANCHOR_SHAPE}: 只有 raise 锚点带抛点原文，实收 {anchor!r}"
    return rest.partition(":")[2]


def anchor_sites(sources: Mapping[str, str], rel: str, anchor: str) -> tuple[int, ...]:
    """一枚锚点 token → 它在现场的那些行（`calls:` 交多枚，其余交一枚；0 枚一律喊）。"""
    kind, rest = anchor_fields(anchor)
    if kind == KIND_CALLS:
        return call_sites(sources, rel, rest)
    return (anchor_line(sources, rel, anchor),)


def derive_sites(sources: Mapping[str, str], rel: str, anchors) -> tuple[int, ...]:
    """逐格现读一本「枚数由现场说」的账：交回所有落点，升序、去重。"""
    sites = [line for anchor in anchors for line in anchor_sites(sources, rel, anchor)]
    assert len(sites) == len(set(sites)), f"{ANCHOR_AMBIGUOUS}: {rel} 的两格锚点读出了同一行 {sites}"
    return tuple(sorted(sites))


def is_multi_site(anchor: str) -> bool:
    """这枚锚点是不是「一格多落点」的形状（只有 `calls:` 是）。"""
    return anchor_fields(anchor)[0] in MULTI_SITE_KINDS


def anchor_line(sources: Mapping[str, str], rel: str, anchor: str) -> int:
    """一枚锚点 token → 它在现场的那一行。读不到/读多枚一律红，见模块头的三句喊话。"""
    kind, rest = anchor_fields(anchor)
    if kind == KIND_CALLS:
        raise AssertionError(f"{ANCHOR_SHAPE}: {KIND_CALLS} 锚点交多枚落点，要用 anchor_sites() 读")
    if kind == KIND_CALL:
        scope, _, callee = rest.partition(":")
        return call_line(sources, rel, scope, callee)
    if kind == KIND_GUARD:
        return guard_line(sources, rel, rest)
    if kind == KIND_HTTP_RAISE:
        func, _, status = rest.partition(":")
        return http_raise_line(sources, rel, func, status)
    func, _, statement = rest.partition(":")
    return raise_statement_line(sources, rel, func, statement)


def derive_ledger(
    sources: Mapping[str, str], rel: str, anchors: tuple[str, ...]
) -> tuple[int, ...]:
    """逐格现读一本账：多站点逐格一 token，交回的读数与锚点逐格同序。"""
    assert isinstance(anchors, tuple), (
        f"{ANCHOR_SHAPE}: {rel} 的账格得写成 token 元组，实收 {type(anchors).__name__}"
    )
    return tuple(anchor_line(sources, rel, anchor) for anchor in anchors)
