# -*- coding: utf-8 -*-
r"""R404 · `document_version_history`：判定之前只读一行 —— 已落树（跟进单 §126 第二节·乙方向）。

## 一、坐标勘正（保留上一班的取证，逐字仍成立）

`document_version_history` 全仓只有一处定义，在 `app/api/v1/chat.py`；`app/documents/catalog.py`
里**没有**这个符号——那本模块只做存储，一次权限判定都没有。工单点名的 `list_document_versions`
是被读的那半条腿，判定与留账都在 chat.py。`test_the_symbol_is_not_where_the_ledger_says` 就是
这格勘正的看守：哪天有人把这枚函数搬进 catalog，它当场红，逼账本改口。

## 二、本班落的码（乙方向，四件事）

1. `app/documents/catalog.py` 补 `latest_document_version()`：单行读，`ORDER BY version DESC`
   同一句 SQL 带上 `LIMIT 1`。它借 `list_document_versions(filename, limit=1)` 落地，所以本模块
   的 `_ensure()` 调用点与 catch-all 配对**一枚都没多**——那两本账由 R377／R383 按 AST 穷尽数着，
   多一枚当场红（`test_the_catalog_single_row_reader_borrows_the_existing_ensure_scope` 提前把
   这格钉死，不必等那两枚件替本单说话）。
2. 路由的判定输入 = 台账最新那一行，判定之前只许这一次读数。
3. 判定过程落审计台账：`record_audit`（chat.py 唯一那枚日志器），动词按门分——这一扇门记它自己
   判定用的 `resource:view`，与下载／删除各自的动词并列，零新增码，不另立第二套形状。
4. 全量读 `list_document_versions(filename)` 仍在，位置挪到判定**之后**，只喂响应正文。

两张脸按现读认下来（§126 第二节原话）：台账有行而盘上文件已没 ⇒ 判定仍读那一行（403 那张脸不许
被 `os.path.exists` 翻成 404，那是 chat.py 另一枚读者 `_latest_document_version` 的事）；无台账行
⇒ 判定之前先 404。`tests/test_document_route_authorization.py` 里那句 `== 403` 一字未动。

## 三、上一班影子方案的账（随乙结掉，不留过期话）

`STAGED_OLD` / `STAGED_NEW` 那对影子锚点**已随落码删除**：改口不再停在影子副本上，现场就是它本
身，再抄一份"打算改成什么样"只会漂。取而代之：本件的每一把刀都切在 AST 现读派生的区间或形状锚点
上（`test_the_landed_anchors_are_cut_on_exactly_one_place_each` 先验锚点唯一，再让刀落），一枚绝对
行号都不抄——这是 R396 那一族债的同一格。上一班那句"改口必须行数中性"随之作废：落码净 +18 行，
`chat.py` 之后的手抄坐标已漂。
返工那一笔（基点 `4cd0a1c`）由本单自己落两处文档：`docs/perf/r387-label-lineage-2026-09-27.md` §1 那张
血缘表跑 `scripts/r387_label_lineage.py --emit-doc-cells` 重落地，`docs/handoff/2026-09-26-v1-frontend-gap-list.md`
文末另起一段记三枚手抄坐标的现读；本件自己仍然一枚绝对行号都不抄。

## 四、反证（全部只在内存里的影子副本上叠；被跟踪文件进门取 sha、出门比 sha）

K1 把旧序放回路由体（先全量读、再拿 `versions[0]` 判） ⇒ 顺序两把钉同时红
K2 `resource_scope={}` ⇒ 审计钉红
K3 `resource_scope=_document_resource_scope(filename, principal)` ⇒ 审计钉红（填错对象）
K4 摘掉 `policy_version=...` ⇒ 审计钉红
K5 摘掉整条 `record_audit(...)` ⇒ 审计钉红（判据 d：判定过程不记审计）
K6 把拒绝体挪到留账之前 ⇒ 「denied 不再进台账」红
K7 翻档不翻码：`LANDED` 与现场互证，把现状钉翻回"不记审计"的形状当场红
K8 把单行读换回全量读（判据 a） ⇒ 单行读钉红
"""


from __future__ import annotations

import ast
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHAT_REL = "app/api/v1/chat.py"
CATALOG_REL = "app/documents/catalog.py"
TRACKED = (CHAT_REL, CATALOG_REL)

ROUTE = "document_version_history"
AUTHORIZE = "_authorize_document_request"
SINGLE_READER = "latest_document_version"
HISTORY_READER = "list_document_versions"
FILE_ASKING_READER = "_latest_document_version"
DECISION = "_document_authorization_decision"
AUDIT = "record_audit"
SCOPE_BUILDER = "_document_resource_scope"

#: 改口已落树。本件的现状钉全部换成目标钉；K7 负责咬「翻了档而码没翻」。
LANDED = True

#: K1 的靶子：落码之前那段旧序（先取全量、`versions[0]` 当判定输入）。只活在内存里。
LEGACY_ORDER = (
    "    principal = _document_principal_or_error(request)",
    "    versions = list_document_versions(filename)",
    "    if not versions:",
    "        raise HTTPException(status_code=404, detail=\"resource_not_found\")",
    "    decision = _document_authorization_decision(principal, filename, versions[0], ACTION_VIEW)",
    "    if not decision.allowed:",
    "        raise HTTPException(status_code=403, detail=decision.reason_code)",
    "    return {",
)

#: 形状锚点（落码现场各恰好一处；先由锚点唯一钉验过，刀才落下去）。
SCOPE_ANCHOR = "        resource_scope=_document_resource_scope(filename, latest),"
SCOPE_WRONG = "        resource_scope=_document_resource_scope(filename, principal),"
SCOPE_EMPTY = "        resource_scope={},"
#: 单线的 policy_version 那行在 chat.py 里其实有 3 处（其他条腿也用同一把 keyword），
#: 所以刀口取「scope + policy_version 」这一对，靠 latest 保证唯一。
POLICY_ANCHOR = (
    "        resource_scope=_document_resource_scope(filename, latest),\n"
    "        policy_version=decision.policy_version,\n"
)
POLICY_ONLY = "        resource_scope=_document_resource_scope(filename, latest),\n"
SINGLE_READ_ANCHOR = "    latest = latest_document_version(filename)\n"
SINGLE_READ_LEGACY = (
    "    versions = list_document_versions(filename)\n"
    "    latest = versions[0] if versions else None\n"
)


def _sha16():
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest()[:16] for rel in TRACKED}


def _text(relative: str) -> str:
    path = REPO / relative
    assert path.exists(), "%s 不在了" % relative
    return path.read_text(encoding="utf-8")


def _lf(text: str) -> str:
    """刀口一律在 LF 形状上切：盘上是 CRLF，带 \\n 的字面锚点会切偏（假刀）。"""
    return text.replace("\r\n", "\n")


def _chat_text() -> str:
    return _lf(_text(CHAT_REL))


def _chat_lines() -> list[str]:
    return _chat_text().splitlines(keepends=True)


def _tree(relative: str) -> ast.Module:
    return ast.parse(_text(relative), filename=relative)


def _function(tree: ast.AST, name: str):
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, "%s 在 %s 里有 %d 处定义" % (name, getattr(tree, "filename", tree), len(found))
    return found[0]


def _calls_inside(node, wanted) -> dict:
    found: dict[str, list] = {}
    for call in ast.walk(node):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in wanted:
            found.setdefault(call.func.id, []).append(call)
    return found


def _call_lines(node, wanted) -> dict:
    return {
        name: sorted(call.lineno for call in calls)
        for name, calls in _calls_inside(node, wanted).items()
    }


def _order_state(route_node) -> dict:
    """路由体内：单行读 / 全量读 / 权限判定 / 问文件在不在的那枚旧读者，各落在哪一行。"""
    inside = _calls_inside(
        route_node, {SINGLE_READER, HISTORY_READER, DECISION, AUTHORIZE, FILE_ASKING_READER}
    )
    judgments = [call.lineno for call in inside.get(DECISION, [])] + [
        call.lineno for call in inside.get(AUTHORIZE, [])
    ]
    return {
        "single": sorted(call.lineno for call in inside.get(SINGLE_READER, [])),
        "full": sorted(call.lineno for call in inside.get(HISTORY_READER, [])),
        "judgment": min(judgments, default=None),
        "file_asking": sorted(call.lineno for call in inside.get(FILE_ASKING_READER, [])),
        "delegated": bool(inside.get(AUTHORIZE)),
    }


def _judgment_reads_one_row(state: dict, landed: bool = LANDED) -> bool:
    return bool(
        landed
        and len(state["single"]) == 1
        and state["judgment"] is not None
        and state["single"][0] < state["judgment"]
        and not state["file_asking"]
    )


def _full_read_only_feeds_the_response(state: dict, landed: bool = LANDED) -> bool:
    return bool(
        landed
        and state["judgment"] is not None
        and state["full"]
        and min(state["full"]) > state["judgment"]
    )


def _absence_exits(route_node) -> list[int]:
    lines = []
    for node in ast.walk(route_node):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            dumped = ast.unparse(node.exc)
            if "status_code=404" in dumped and "resource_not_found" in dumped:
                lines.append(node.lineno)
    return sorted(lines)


def _reverted_chat_text() -> str:
    """K1 的影子副本：把路由体第一段换成旧序（AST 现读区间，不抄行号）。"""
    lines = _chat_lines()
    tree = ast.parse("".join(lines), filename=CHAT_REL)
    route = _function(tree, ROUTE)
    returns = [stmt for stmt in route.body if isinstance(stmt, ast.Return)]
    assert len(returns) == 1, returns
    start, end = route.body[0].lineno, returns[0].lineno
    block = "\n".join(LEGACY_ORDER) + "\n"
    return "".join(lines[: start - 1] + [block] + lines[end:])


def _span_of(node) -> str:
    lines = _chat_lines()
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def _audit_nodes(route_node):
    audit = _calls_inside(route_node, {AUDIT})[AUDIT]
    assert len(audit) == 1, audit
    denials = [
        node
        for node in ast.walk(route_node)
        if isinstance(node, ast.If) and ast.unparse(node.test).startswith("not decision.allowed")
    ]
    assert denials, denials
    return audit[0], min(denials, key=lambda node: node.lineno)


def _moved_denial_text() -> str:
    """K6 的影子副本：拒绝体挪到留账之前（区间由 AST 现读）。"""
    lines = _chat_lines()
    tree = ast.parse("".join(lines), filename=CHAT_REL)
    audit_call, denial = _audit_nodes(_function(tree, ROUTE))
    a_start, a_end = audit_call.lineno, audit_call.end_lineno
    d_start, d_end = denial.lineno, denial.end_lineno
    assert a_end < d_start, (a_start, a_end, d_start, d_end)
    denial_block = "".join(lines[d_start - 1 : d_end])
    return "".join(
        lines[: a_start - 1] + [denial_block] + lines[a_start - 1 : d_start - 1] + lines[d_end:]
    )


def _silenced_journal_text() -> str:
    """K5 的影子副本：整条 record_audit(...) 摘掉（判据 d 的刀）。"""
    lines = _chat_lines()
    tree = ast.parse("".join(lines), filename=CHAT_REL)
    audit_call, _denial = _audit_nodes(_function(tree, ROUTE))
    return "".join(lines[: audit_call.lineno - 1] + lines[audit_call.end_lineno :])


def _mutated(anchor: str, replacement: str) -> str:
    text = _chat_text()
    assert text.count(anchor) == 1, text.count(anchor)
    return text.replace(anchor, replacement)


def _audit_state(tree, target: str = ROUTE) -> dict:
    """留账那格不许变松：通路唯一、scope 齐、scope 与判定读同一枚对象、denied 先进台账。"""
    helper = _function(tree, target)
    audits = _call_lines(helper, {AUDIT}).get(AUDIT, [])
    assert len(audits) == 1, "留账调用不再是恰好一枚（target=%s）：%s" % (target, audits)
    call = _calls_inside(helper, {AUDIT})[AUDIT][0]
    keywords = {keyword.arg for keyword in call.keywords if keyword.arg}
    missing = {"resource_scope", "policy_version"} - keywords
    assert not missing, "审计少了关键字：%s" % sorted(missing)
    scope = next(keyword.value for keyword in call.keywords if keyword.arg == "resource_scope")
    assert isinstance(scope, ast.Call) and scope.func.id == SCOPE_BUILDER, (
        "resource_scope 不再由 %s 构造：填的是 %s" % (SCOPE_BUILDER, ast.unparse(scope))
    )
    decision_call = next(
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == DECISION
    )
    decision_args = [arg.id for arg in decision_call.args if isinstance(arg, ast.Name)]
    scope_args = [arg.id for arg in scope.args if isinstance(arg, ast.Name)]
    assert scope_args == decision_args[1:3], (
        "留账的 scope 与判定读的那一行不再是同一枚对象：scope=%s 判定=%s" % (scope_args, decision_args)
    )
    denials = [
        node.lineno
        for node in ast.walk(helper)
        if isinstance(node, ast.If) and ast.unparse(node.test).startswith("not decision.allowed")
    ]
    assert denials, "判定被拒那一段不在了：留账与拒绝的先后无法核对"
    assert min(denials) > call.lineno, (
        "denied 不再进台账：record_audit 落在第 %s 行，拒绝体从第 %s 行就开始" % (call.lineno, min(denials))
    )
    return {"audit_line": call.lineno, "scope_args": scope_args, "denial_line": min(denials)}

# ==================== 坐标勘正的看守 ====================


def test_the_symbol_is_not_where_the_ledger_says():
    catalog = _tree(CATALOG_REL)
    names = {
        node.name
        for node in ast.walk(catalog)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert ROUTE not in names, "catalog 里长出了 %s：工单那句「catalog.py 的 document_version_history」不再是假话，账要改口" % ROUTE
    source = _text(CATALOG_REL)
    for marker in (AUDIT, "authorization_decision", "principal_from_request"):
        assert source.count(marker) <= 1, (
            "catalog 开始自己做权限/留账（%s 命中 %d 次）：R404 的改造点不再唯一，本件要重取" % (marker, source.count(marker))
        )
    assert SINGLE_READER in names, "catalog 里没有 %s：乙方向的单行读没落，判定腿又回到全量读了" % SINGLE_READER
    _function(_tree(CHAT_REL), ROUTE)


# ==================== 目标态：判定之前只读一行 ====================


def test_the_judgment_reads_one_row_before_it_judges():
    state = _order_state(_function(_tree(CHAT_REL), ROUTE))
    assert _judgment_reads_one_row(state), (
        "判定之前读的不止一行（判据 a 的形状）：%s —— 单行读必须恰好一枚且排在判定之前，"
        "也不许换成问 os.path.exists 的那枚旧读者" % state
    )


def test_the_full_version_listing_only_feeds_the_response():
    state = _order_state(_function(_tree(CHAT_REL), ROUTE))
    assert _full_read_only_feeds_the_response(state), (
        "全量读又跑到判定之前了（病灶原形状）：%s —— 它只许在判定之后喂响应正文" % state
    )


def test_the_absence_of_a_ledger_row_is_answered_before_the_judgment():
    route = _function(_tree(CHAT_REL), ROUTE)
    absences = _absence_exits(route)
    state = _order_state(route)
    assert len(absences) == 1, "那张「无台账行」的脸不恰好一枚：%s" % absences
    assert absences[0] < state["judgment"], (
        "404 排到了判定之后（判据 b 的第二张脸翻了）：404 在第 %s 行，判定在第 %s 行"
        % (absences[0], state["judgment"])
    )


def test_the_judgment_leaves_one_journal_entry_on_the_shared_channel():
    tree = _tree(CHAT_REL)
    _audit_state(tree, ROUTE)
    _audit_state(tree, AUTHORIZE)


def test_the_route_shares_the_one_journal_channel_and_grows_no_second_logger():
    source = _text(CHAT_REL)
    assert source.count("from app.common.audit import record_audit") == 1, (
        "chat.py 里 audit 通路的 import 不再恰好一枚：本单判据要的是同一条唯一通路"
    )
    route = _function(_tree(CHAT_REL), ROUTE)
    nested = [
        node
        for node in ast.walk(route)
        if node is not route and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert nested == [], "路由体里长出了内嵌函数（第二套留账形状的常见前身）：%s" % [n.name for n in nested]
    attribute_calls = {
        ast.unparse(call.func)
        for call in ast.walk(route)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }
    assert not [name for name in attribute_calls if name.startswith("logger.")], (
        "判定过程改用 logger 落账 = 第二枚日志器：%s" % sorted(attribute_calls)
    )


def test_the_catalog_single_row_reader_borrows_the_existing_ensure_scope():
    fn = _function(_tree(CATALOG_REL), SINGLE_READER)
    calls = _call_lines(fn, {HISTORY_READER, "_ensure", "_conn", "_database_available"})
    assert calls.get("_ensure", []) == [], (
        "catalog 的单行读自己又开了一枚 _ensure() 调用点：R377／R383 那本穷尽账会当场红，"
        "本单不许为了读一行去改那两枚件的账"
    )
    assert calls.get("_conn", []) == [], "同上：存储连接点一枚都不许多"
    listed = _calls_inside(fn, {HISTORY_READER})[HISTORY_READER]
    assert len(listed) == 1, listed
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in listed[0].keywords}
    assert keywords == {"limit": "1"}, "单行读不是 limit=1：%s" % keywords


def test_the_landed_anchors_are_cut_on_exactly_one_place_each():
    text = _chat_text()
    for anchor in (SCOPE_ANCHOR, POLICY_ANCHOR, SINGLE_READ_ANCHOR):
        assert text.count(anchor) == 1, "锚点 %r 在盘上不是恰好一处（%d）：刀会切偏成假反证" % (anchor, text.count(anchor))
    assert text.count(SCOPE_WRONG) == 0 and text.count(SCOPE_EMPTY) == 0
    assert _reverted_chat_text() != text


# ==================== 反证 K1–K8 ====================


def test_k1_the_old_order_fires_the_sequence_pins():
    before = _sha16()
    state = _order_state(_function(ast.parse(_reverted_chat_text(), filename=CHAT_REL), ROUTE))
    assert not _judgment_reads_one_row(state), "K1 没咬住：旧序仍然算「判定只读一行」"
    assert not _full_read_only_feeds_the_response(state), "K1 没咬住：全量读排在判定之前却不被认"
    assert _sha16() == before


def test_k2_an_empty_resource_scope_goes_red():
    before = _sha16()
    tree = ast.parse(_mutated(SCOPE_ANCHOR, SCOPE_EMPTY), filename=CHAT_REL)
    try:
        _audit_state(tree, ROUTE)
    except AssertionError as raised:
        assert "resource_scope" in str(raised), raised
    else:
        raise AssertionError("K2 没咬住：scope 填空了而审计钉仍是绿的")
    assert _sha16() == before


def test_k3_a_wrong_scope_source_goes_red():
    before = _sha16()
    tree = ast.parse(_mutated(SCOPE_ANCHOR, SCOPE_WRONG), filename=CHAT_REL)
    try:
        _audit_state(tree, ROUTE)
    except AssertionError as raised:
        assert "同一枚对象" in str(raised), raised
    else:
        raise AssertionError("K3 没咬住：scope 填成 principal 而审计钉仍是绿的")
    assert _sha16() == before


def test_k4_dropping_policy_version_goes_red():
    before = _sha16()
    tree = ast.parse(_mutated(POLICY_ANCHOR, POLICY_ONLY), filename=CHAT_REL)
    try:
        _audit_state(tree, ROUTE)
    except AssertionError as raised:
        assert "policy_version" in str(raised), raised
    else:
        raise AssertionError("K4 没咬住：policy_version 被摘掉而审计钉仍是绿的")
    assert _sha16() == before


def test_k5_silencing_the_journal_goes_red():
    """判据 d 的刀：判定过程不记审计 ⇒ 审计钉必须红。"""
    before = _sha16()
    tree = ast.parse(_silenced_journal_text(), filename=CHAT_REL)
    try:
        _audit_state(tree, ROUTE)
    except AssertionError as raised:
        assert "留账调用" in str(raised), raised
    else:
        raise AssertionError("K5 没咬住：整条 record_audit 摘光了而本件仍是绿的")
    assert _sha16() == before


def test_k6_raising_the_denial_before_the_journal_goes_red():
    before = _sha16()
    tree = ast.parse(_moved_denial_text(), filename=CHAT_REL)
    try:
        _audit_state(tree, ROUTE)
    except AssertionError as raised:
        assert "denied 不再进台账" in str(raised), raised
    else:
        raise AssertionError("K6 没咬住：拒绝体挪到留账之前而本件仍是绿的")
    assert _sha16() == before


def test_k7_flipping_the_ledger_without_the_code_goes_red():
    """LANDED 不是免检通道：翻档与翻码必须一边发生变化时，目标钉就要红。"""
    before = _sha16()
    assert LANDED is True, "改口还在树上：把档翻回 False 等于宣称本单没落码，而现场已经落了"
    state = _order_state(_function(_tree(CHAT_REL), ROUTE))
    assert _judgment_reads_one_row(state) and _full_read_only_feeds_the_response(state), (
        "现场与档对不上：%s ⇒ 改口没落全，或者本件的判据实现漂了" % state
    )
    # 翻档不翻码：把自己宣称「还没落地」，两把目标钉必须立刻闭嘴（钉不是常青白）
    assert not _judgment_reads_one_row(state, landed=False), "档翻掉了钉还绿着：LANDED 根本不承载判据"
    assert not _full_read_only_feeds_the_response(state, landed=False), "同上"
    # 翻码不翻档：把旧序塞回去，同样必须红
    legacy = _order_state(_function(ast.parse(_reverted_chat_text(), filename=CHAT_REL), ROUTE))
    assert not _judgment_reads_one_row(legacy) and not _full_read_only_feeds_the_response(legacy), legacy
    assert _sha16() == before


def test_k8_a_full_read_back_as_judgment_input_goes_red():
    """判据 a 的刀：把单行读换回全量读 ⇒ 单行读钉必须红。"""
    before = _sha16()
    mutated = _mutated(SINGLE_READ_ANCHOR, SINGLE_READ_LEGACY)
    state = _order_state(_function(ast.parse(mutated, filename=CHAT_REL), ROUTE))
    assert not _judgment_reads_one_row(state), "K8 没咬住：判定输入换回全量读了而单行读钉仍是绿的"
    assert not _full_read_only_feeds_the_response(state), "K8 没咬住：全量读又跑到判定之前而响应钉仍是绿的"
    assert _sha16() == before