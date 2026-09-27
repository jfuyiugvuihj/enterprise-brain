"""R376 · 写侧那道闸的形状：不新造尺、不新造码、不新造 except、不并权限错与存储错。

同仓先例摆在那儿，本件照同一族判法数读者：

- 「库在不在」只许有一枚探针 —— `app/notifications/states.py::_database_available`。`_db_ready`
  的读者总数由 `tests/test_r246_honest_readiness_claims.py` 按 AST 管着，本件再钉一层
  「states.py 里仍是一枚」。
- 「是不是生产」只许借现成的尺 —— 与 `app/api/v1/dashboard.py`（R367）借的是同一枚
  `app/api/v1/alerts.py::_is_production_environment`。全仓那八枚定义一枚都不许多长；states.py
  自己既不许 `os.getenv("APP_ENV")`，也不许写死 `"production"` 字面量。
- 错误码零新增 —— 拒答走既有那一枚具名错，出口 `app/api/v1/notifications.py` 的两支 except
  今天就在把它翻成 503 `storage_unavailable`，所以本件出口一个字都没改（R381 之后写侧那一支
  多接一枚具名类型，名单钉随之一同改口，等号判法未松）；`detail` 的取值集合、
  `reason` 的词表、成功回执的键集合，本件一枚都不许多长。
- 判据④：401 那一支与 `notification_not_addressable` 那一支逐格保持。收件箱侧那两张折叠名单
  （`inbox.py::can_address` 的 401/403/404、`sources.py::alert_candidates` 的 403/503）各自从
  AST 现读并钉死：503 不许并回「不可寻址」那一格，404 也不许被翻成「存储没就绪」。

存储层（states.py）自己一枚 HTTPException 都不许 raise —— 那是出口那一层的活儿，两层各自留名。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import pytest
from app.agents.contracts import ErrorEnvelope
from app.api.v1 import alerts as alerts_api
from app.notifications import states as state_store

ROOT = Path(__file__).resolve().parents[1]
STATES_PY = ROOT / "app" / "notifications" / "states.py"
OUTLET_PY = ROOT / "app" / "api" / "v1" / "notifications.py"
INBOX_PY = ROOT / "app" / "notifications" / "inbox.py"
SOURCES_PY = ROOT / "app" / "notifications" / "sources.py"
CONTRACT = ROOT / "docs" / "api" / "contract-v1.md"
BEHAVIOR_PY = ROOT / "tests" / "test_r376_notifications_refuse_a_store_that_is_not_there.py"

#: 契约里本件那一节的标题（判「追加过且只追加一次」，也判「被人整节复制过」）。
R376_HEADING = "## A write that cannot be stored must not say it was (2026-09-27, R376)"

GATE = "_require_writable_store"
STORAGE_CODE = "storage_unavailable"
NOT_ADDRESSABLE = "notification_not_addressable"
REASON_APPLIED = "applied"

#: 基点 `796540e` 上 app/** 里 `_is_production_environment` 的定义数（本单借尺，一枚不许多长）。
PRODUCTION_RULER_DEFS_AT_BASE = 8

#: 出口那三支 HTTPException 的既有脸：本单一枚不加、一枚不减。
OUTLET_ERROR_FACES = {
    (401, "authentication_required"),
    (422, "validation_error"),
    (503, STORAGE_CODE),
}

#: 出口的异常型名单（多接一种 = 替真 bug 打掩护，少接一种 = 换了脸）。
#: `_ids_from_body` 那三支客户端形状错 + 两支出口各自翻译的存储拒答。本件交工时读写两支各只接一枚
#: 生命周期错（五枚），R381 只在**写侧**那一支多接了审批账本那枚具名错（六枚）—— 等号判法一字未松，
#: 改的是右侧名单本身，那格改动与它的判据见 docs/api/contract-v1.md 的 R381 一节。
LIFECYCLE_TYPE = "NotificationStateStoreMissing"
OUTLET_HANDLER_ROSTER = sorted(
    ["Exception", "NotificationIdError", "ValidationError"]
    + [LIFECYCLE_TYPE]
    + [LIFECYCLE_TYPE, "PendingApprovalStoreMissing"]
)

#: 生命周期那一层的顶层函数名单，含本单新添的那一枚闸（顺序即读法）。
STATES_MODULE_ROSTER = [
    "_database_available",
    "_conn",
    "_now",
    "_require_table",
    GATE,
    "recipient_states",
    "read_state",
    "apply_state",
    "reset_for_testing",
]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """同步与异步都算：`_apply` / `can_address` / `alert_candidates` 今天全是 async def。"""
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"{name} 应当恰有一枚定义，实测 {len(found)} 枚"
    return found[0]


def _callee(call: ast.Call) -> str:
    return getattr(call.func, "attr", "") or getattr(call.func, "id", "") or "?"


def _call_names(node: ast.AST) -> list[str]:
    return [_callee(call) for call in ast.walk(node) if isinstance(call, ast.Call)]


def _http_raises(tree: ast.AST) -> set[tuple[int, str]]:
    """(status_code, detail) 两格都只认字面常量：插值型 detail 不当成已知脸。"""
    faces: set[tuple[int, str]] = set()
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _callee(call) == "HTTPException"):
            continue
        values = {}
        for keyword in call.keywords:
            if keyword.arg in {"status_code", "detail"} and isinstance(keyword.value, ast.Constant):
                values[keyword.arg] = keyword.value.value
        if "status_code" in values:
            faces.add((values["status_code"], values.get("detail")))
    return faces


def _handler_types(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for handler in ast.walk(tree):
        if isinstance(handler, ast.ExceptHandler) and handler.type is not None:
            # R381 修形：`except (A, B)` 的 `handler.type` 是一枚 ast.Tuple，按它自己迭代会炸。
            nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
            names.extend(getattr(node, "attr", "") or getattr(node, "id", "") for node in nodes)
    return sorted(names)


def _status_codes_in(node: ast.AST) -> set[int]:
    return {
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, int)
    }


def _folded_statuses(function: ast.FunctionDef) -> dict[str, set[int]]:
    """从 AST 现读「哪几个状态码被折进了 return 那一族、哪些留在 raise 那一族」。

    名单是派生的，不是手抄的：多折一枚、少折一枚、或把 503 从 raise 挪进 `return False`，
    都会在这里露出来。判的只有 `if exc.status_code ...` 那种分支，别的不算。
    """
    folded: set[int] = set()
    refused: set[int] = set()
    for branch in ast.walk(function):
        if not isinstance(branch, ast.If) or "status_code" not in ast.unparse(branch.test):
            continue
        codes = _status_codes_in(branch.test)
        if not codes:
            continue
        if any(isinstance(item, ast.Raise) for item in ast.walk(branch)):
            refused |= codes
        elif any(
            isinstance(item, ast.Return) and item.value is not None for item in ast.walk(branch)
        ):
            folded |= codes
    return {"folded_into_return": folded, "re_raised": refused}


# ----------------------------------------------------------- 判据①：一枚尺、一枚探针


def test_states_py_defines_no_second_production_ruler():
    """判的是**代码**，不是散文：文件里提到 APP_ENV 的注释不算一把新尺。"""
    tree = _tree(STATES_PY)
    source = _source(STATES_PY)
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    getenv_args = {
        ast.unparse(argument)
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and _callee(call) == "getenv"
        for argument in call.args
    }
    compared = {
        operand.value
        for branch in ast.walk(tree)
        if isinstance(branch, ast.Compare)
        for operand in [branch.left, *branch.comparators]
        if isinstance(operand, ast.Constant) and operand.value in {"production", "prod"}
    }

    assert "_is_production_environment" not in names, "states.py 自己长出了第二把生产判定尺"
    assert "APP_ENV" not in getenv_args, "states.py 自己 getenv 起 APP_ENV 来了：那是第二把尺"
    assert "_PRODUCTION_ENVIRONMENTS" not in source, "把别人那把尺的词表抄一遍，也是第二把"
    assert compared == set(), "把生产拼写写进了比较式：那枚尺改 spelling 时这里会静默失效"


def test_the_borrowed_ruler_is_the_one_r367_borrowed():
    gate = _function(_tree(STATES_PY), GATE)

    assert "alerts_api._is_production_environment()" in ast.unparse(gate), (
        "闸没在问那枚既有的尺：" + ast.unparse(gate)
    )
    assert state_store.alerts_api._is_production_environment is alerts_api._is_production_environment, (
        "借来的尺换了主人"
    )


def test_the_production_ruler_did_not_gain_a_definition_anywhere():
    definitions = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        definitions.extend(
            path.relative_to(ROOT).as_posix()
            for node in ast.walk(_tree(path))
            if isinstance(node, ast.FunctionDef) and node.name == "_is_production_environment"
        )

    assert len(definitions) == PRODUCTION_RULER_DEFS_AT_BASE, (
        f"基点上 {PRODUCTION_RULER_DEFS_AT_BASE} 把尺，现在 {len(definitions)} 把：{definitions}"
    )


def test_states_py_gained_no_second_store_probe():
    """`_db_ready` 在 states.py 仍只有一枚读者，「库在不在」仍只算一遍。"""
    tree = _tree(STATES_PY)
    readers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "_db_ready":
            readers.add(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and _callee(node) in {"getattr", "hasattr"}
            and any(isinstance(a, ast.Constant) and a.value == "_db_ready" for a in node.args[1:2])
        ):
            readers.add(node.lineno)
    probes = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_database_available"
    ]

    assert len(readers) == 1, f"`_db_ready` 在 states.py 有了第二枚读者：{sorted(readers)}"
    assert probes == ["_database_available"], "库里在不在被算了第二遍"


def test_the_outlet_gained_no_ruler_and_no_probe():
    """生产判定只住在存储层那一格：出口再算一遍，就是两处答案会各漂一次。"""
    source = _source(OUTLET_PY)

    assert "_is_production_environment" not in source
    assert "_database_available" not in source
    assert "APP_ENV" not in source


# ----------------------------------------------------------- 判据①：零新增错误码、零新增 reason


def test_the_refusal_reuses_a_code_the_enumeration_already_ratified():
    assert STORAGE_CODE in set(get_args(ErrorEnvelope.model_fields["code"].annotation)), (
        "本件依赖的那一码不在既有的封闭枚举里"
    )
    assert (503, STORAGE_CODE) in _http_raises(_tree(OUTLET_PY))


def test_the_outlet_emits_no_new_error_face():
    faces = _http_raises(_tree(OUTLET_PY))

    assert faces == OUTLET_ERROR_FACES, "出口那三支脸多了一枚或少了一枚：" + str(sorted(faces))


def test_the_outlet_still_translates_exactly_one_exception_type():
    """出口承接名单（R381 改口：等号右侧从五枚长成六枚，判法一字未松）。

    函数名与它那一格都保留原样：它钉的是「生命周期那枚具名错被读写两支各接一次」，那一格一枚没少。
    R381 只把审批账本那枚错接进**写侧**那一支，读侧那支没接 —— 那枚错今天走不到读出口
    （`sources.py::approval_candidates` 早已把它折成逐腿缺席），接进去等于把 R373 刀一在读出口量到的
    裸 500 洗成 503，钝掉别人那扇反证窗。改的只有等号右侧那份名单；`==` 判法、两支存储出口各恰一枚
    503、detail 恒为 `storage_unavailable` 三格判据一字未动。
    """
    tree = _tree(OUTLET_PY)

    assert _handler_types(tree) == OUTLET_HANDLER_ROSTER, (
        "出口的 except 名单变了：多接一型等于替真 bug 打掩护"
    )
    handlers = [
        handler for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and LIFECYCLE_TYPE in _handler_types(handler)
    ]
    assert len(handlers) == 2, f"接那枚生命周期错的 except 应为两支（一读一写），实测 {len(handlers)}"
    for handler in handlers:
        raises = [
            call for call in ast.walk(handler)
            if isinstance(call, ast.Call) and _callee(call) == "HTTPException"
        ]
        assert len(raises) == 1, "一支 except 里翻出了两张脸"
        details = {
            keyword.value.value for keyword in raises[0].keywords
            if keyword.arg == "detail" and isinstance(keyword.value, ast.Constant)
        }
        assert details == {STORAGE_CODE}, "except 翻出来的不是仓里已有的那一码"


def test_the_storage_layer_still_raises_no_http_exception():
    source = _source(STATES_PY)

    assert "HTTPException" not in source, "存储层自己发起 HTTP 来了：那是出口的活儿"
    assert "detail=" not in source
    gate = _function(_tree(STATES_PY), GATE)
    raised = [
        _callee(node.exc) or getattr(node.exc, "id", "")
        for node in ast.walk(gate)
        if isinstance(node, ast.Raise) and node.exc is not None
    ]
    assert raised == ["NotificationStateStoreMissing"], (
        "闸抛的不是那枚既有具名错，而是另起一型：" + str(raised)
    )


def test_the_outlet_reason_roster_is_still_two_words():
    """`reason` 只准有『applied』与『不可寻址』两枚：本单没为『没落库』新造第三个词。"""
    constants = {
        node.targets[0].id: node.value.value
        for node in _tree(OUTLET_PY).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }

    assert constants["NOT_ADDRESSABLE"] == NOT_ADDRESSABLE
    assert constants["REASON_APPLIED"] == REASON_APPLIED
    assert STORAGE_CODE not in constants.values(), "存储错被折进了一格 reason 词：那是第二张脸"


def test_the_success_receipt_fields_are_unchanged():
    """写侧成功回执仍是那四枚键：没往里加 `persisted` 之类的第三句说法。"""
    rows = []
    for node in ast.walk(_function(_tree(OUTLET_PY), "_apply")):
        if isinstance(node, ast.Dict):
            names = {
                item.value if isinstance(item, ast.Constant) else ast.unparse(item)
                for item in node.keys
                if item is not None
            }
            if "reason" in names:
                rows.append(names)

    assert rows and all(row == {"id", "state", "changed", "reason"} for row in rows), (
        "回执行的键集合长了一枚：" + str(rows)
    )


# ----------------------------------------------------------- 判据④：闸的位置与两张名单


def test_the_gate_is_called_before_any_ledger_or_clock_access():
    """顺序钉（AST）：闸排在 `read_state` / `_now` / 内存写 / `_conn` 之前。"""
    body = _function(_tree(STATES_PY), "apply_state").body
    first: dict[str, int] = {}

    def _note(name: str, index: int) -> None:
        if name not in first or index < first[name]:
            first[name] = index

    for index, statement in enumerate(body):
        _note(GATE, index) if GATE in _call_names(statement) else None
        for name in _call_names(statement):
            _note(name, index)
        for node in ast.walk(statement):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and getattr(target.value, "id", "") == "_ROWS":
                        _note("memory_write", index)

    assert first[GATE] == min(first[GATE], first["read_state"] - 1), str(first)
    assert first[GATE] < first["read_state"], "闸排在读之后了：拒答之前先碰了那本账"
    assert first[GATE] < first["memory_write"], "内存腿先被写了，闸才落下：那是先斩后奏"
    assert first[GATE] < first.get("_conn", first[GATE] + 1), "拒答之前先去连了库"


def test_the_auth_and_addressability_branches_keep_their_own_faces():
    """401 那一支与『不可寻址』那一支逐格保持：本单没把存储错并进去。"""
    tree = _tree(OUTLET_PY)
    guard = _function(tree, "_principal_or_401")

    assert _http_raises(guard) == {(401, "authentication_required")}, "401 那一支被人改过脸"
    assert (403, "permission_denied") not in _http_raises(tree), "出口不该长出 403：权限判定不在这层"

    block = next(
        node
        for node in ast.walk(_function(tree, "_apply"))
        if isinstance(node, ast.If) and "can_address" in ast.unparse(node.test)
    )
    unparse = ast.unparse(block)
    assert "record_audit" in unparse and "NOT_ADDRESSABLE" in unparse, "不可寻址那一支被并走了"
    assert "HTTPException" not in unparse and STORAGE_CODE not in unparse, (
        "不可寻址那一支里长出了 503：权限错与存储错合并成一格了"
    )


def test_the_inbox_fold_list_is_still_three_statuses_and_excludes_storage():
    """`can_address` 折的是 401/403/404，503 仍走裸 raise（R366 的裁定，本件复算）。"""
    folded = _folded_statuses(_function(_tree(INBOX_PY), "can_address"))

    assert folded["folded_into_return"] == {401, 403, 404}, str(folded)
    assert 503 not in folded["folded_into_return"], "503 被折成了『不可寻址』：存储拒答洗成已解决"
    assert 503 in folded["re_raised"], "503 那一支不再上抛了"


def test_the_alert_leg_fold_list_stays_separate():
    """`alert_candidates` 折的是 403 与 503，与本单那一格互不相干，各自派生各自钉。"""
    folded = _folded_statuses(_function(_tree(SOURCES_PY), "alert_candidates"))

    assert folded["folded_into_return"] == {403, 503}, str(folded)


# ----------------------------------------------------------- 别顺手删的那一格


def test_reset_for_testing_still_clears_the_memory_ledger():
    """`_ROWS.clear()` 防的是进程内账本跨用例泄漏：本单一个字没动它。"""
    reset = _function(_tree(STATES_PY), "reset_for_testing")

    assert "clear" in _call_names(reset), "内存腿的清空那一格被人删了"
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "clear"
        and getattr(node.value, "id", "") == "_ROWS"
        for node in ast.walk(reset)
    ), "clear 不再是 _ROWS 的方法调用"


@pytest.fixture
def bare_machine(monkeypatch):
    """裸机那一格：库不在、APP_ENV 不是生产 —— 上面那枚功能钉要真的能写。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: False)


def test_reset_for_testing_still_empties_the_leg(bare_machine):
    state_store.apply_state("r376-shape", "alert:1", "read")
    assert state_store.recipient_states("r376-shape") == {"alert:1": "read"}

    state_store.reset_for_testing()

    assert state_store.recipient_states("r376-shape") == {}
    assert state_store._ROWS == {}


# ----------------------------------------------------------- 本件的落点与全文的形状


def test_the_module_roster_names_the_new_gate_once():
    functions = [node.name for node in _tree(STATES_PY).body if isinstance(node, ast.FunctionDef)]

    assert functions.count(GATE) == 1, functions
    assert functions == STATES_MODULE_ROSTER, "生命周期这一层的顶层函数名单变了：" + str(functions)


def test_the_contract_appends_the_new_face_once():
    text = _source(CONTRACT)

    assert text.count(R376_HEADING) == 1, "R376 那一节标题不是一枚（或整节被人复制过）"
    section = text.split(R376_HEADING, 1)[1]
    for marker in (STORAGE_CODE, "APP_ENV", "changed", "_ROWS", "notification_states"):
        assert marker in section, f"契约那一节没提 {marker}"


@pytest.mark.parametrize(
    "path",
    [STATES_PY, OUTLET_PY, CONTRACT, Path(__file__).resolve(), BEHAVIOR_PY],
    ids=["states", "outlet", "contract", "pins", "behavior"],
)
def test_every_delivered_file_keeps_the_repository_byte_shape(path):
    blob = path.read_bytes()

    assert blob[:3] != b"\xef\xbb\xbf", f"{path.name} 带上了 BOM"
    assert blob.count(b"\n") == blob.count(b"\r\n"), f"{path.name} 里有 lone LF"
    assert blob.decode("utf-8").count("\ufffd") == 0, f"{path.name} 里出现 U+FFFD：编码被写坏过"
