"""R381 · 出口那两支 except 的形状：只在写侧多接一枚具名类型，一枚都不许多。

判据与用例的对应（回执第 1/2/3 格引用这里）：

- 名单钉（判据乙）：出口 `except` 的具名类型名单从基点 `0d4f5ec` 的五枚长成六枚，多出来的正是
  那一枚 `PendingApprovalStoreMissing`，而且它只长在**写侧**那一支。名单用等号判，多一枚（并脸）
  与少一枚（换脸）各红一次；`RuntimeError` 这枚父类不在名单里，也不许进来。
- 读侧不并进来（判据①的可达性那一格）：`list_notifications` 那一支仍只接生命周期一枚。那枚账本错
  今天走不到读出口 —— `sources.py::approval_candidates` 早把它折成逐腿缺席（R373 的裁定），出口再
  接一次就是把一枚问不出的腿折成整页 503，顺手钝掉 R373 刀一在那支上量到的裸 500 反证。
- 脸钉（判据乙后半）：`status_code=503` 的抛出点全模块仍**恰两枚**，读写两支 except 各吐一枚
  `HTTPException(503, 'storage_unavailable')` 且带 `from exc`；(status, detail) 面集合与基点
  逐字相同 —— 零新增错误码、零新增 reason 词、零新增状态档位。
- 静默吞钉（判据丙）：那两支 except 里不许出现 `return`。把拒答折成空回执正是 R373 判过的
  「问不出」被说成「不在了」。
- 宽捕获钉（判据乙）：本文件的宽捕获数仍恰一枚，且它必须还站在 `_ids_from_body` 里 —— 那是
  R299 登记过的「非法 JSON 与超限同脸」，不是本单新开的洞。出口没长第二枚。
- 不越界钉（判据丙后半）：`app/notifications/inbox.py::can_address` 的承接名单与那一支裸
  `raise` 逐字未动。本件治的是出口不说人话，不是让写侧闭嘴。

读数一律走 `tests/_temp_edit_overlay.py` 的当前视图：窗外读盘上的被跟踪文件，反证窗内读影子
副本 —— 所以这枚名单钉在变异版下真的会红，而盘上字节全程只读（同机多枚 Agent 的纪律）。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import pytest
from app.agents.contracts import ErrorEnvelope
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store
from tests import _temp_edit_overlay as overlay

REPO = Path(__file__).resolve().parents[1]
OUTLET_PY = REPO / "app" / "api" / "v1" / "notifications.py"
INBOX_PY = REPO / "app" / "notifications" / "inbox.py"
CHAT_PY = REPO / "app" / "api" / "v1" / "chat.py"
DASHBOARD_PY = REPO / "app" / "api" / "v1" / "dashboard.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"

STORAGE_CODE = "storage_unavailable"
LIFECYCLE_TYPE = "NotificationStateStoreMissing"
LEDGER_TYPE = "PendingApprovalStoreMissing"

#: 基点 `0d4f5ec` 上出口那五枚承接名：`_ids_from_body` 的三支客户端形状错 + 读写两支那枚生命周期错。
BASE_OUTLET_HANDLER_ROSTER = [
    "Exception",
    "NotificationIdError",
    LIFECYCLE_TYPE,
    LIFECYCLE_TYPE,
    "ValidationError",
]

#: 本单交工后的名单：基点那五枚原样保留，只在**写侧**那一支多长一枚账本错（六枚）。等号判，
#: 不判包含 —— 读侧那一支要是也长出这枚，这一行就会红，而它今天不该红（可达性见模块文档串）。
OUTLET_HANDLER_ROSTER = sorted(
    BASE_OUTLET_HANDLER_ROSTER + [LEDGER_TYPE]
)

#: 出口那三支脸（401 / 422 / 503）：本单一枚不加、一枚不减，与 R376 那枚钉同一份读数。
OUTLET_ERROR_FACES = {
    (401, "authentication_required"),
    (422, "validation_error"),
    (503, STORAGE_CODE),
}

#: 契约里本单那一节的标题（判「追加过且只追加一次」，也判「被人整节复制过」）。
R381_HEADING = (
    "## The write exit answers the approval ledger the same way it answers its own "
    "(2026-09-27, R381)"
)


def _text(path: Path) -> str:
    """当前视图的字节：反证窗内是影子副本，窗外是盘上的被跟踪文件。"""
    return overlay.authoritative_text(overlay.rel_of(path))


def _disk_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_text(path))


def _function(tree: ast.Module, name: str) -> ast.AST:
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"{name} 应当恰有一枚定义，实测 {len(found)} 枚"
    return found[0]


def _parents(tree: ast.Module) -> dict:
    mapping: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            mapping[id(child)] = parent
    return mapping


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str:
    mapping = _parents(tree)
    current = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = mapping.get(id(current))
    return "-"


def _handler_names(handler: ast.ExceptHandler) -> list[str]:
    """具名承接的名字列表：`except (A, B) as exc` 摊成两枚，裸 `except:` 摊成一枚空串。"""
    if handler.type is None:
        return [""]
    nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return [getattr(node, "attr", "") or getattr(node, "id", "") for node in nodes]


def _roster(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for handler in ast.walk(tree):
        if isinstance(handler, ast.ExceptHandler) and handler.type is not None:
            names.extend(_handler_names(handler))
    return sorted(names)


def _folded_handler(tree: ast.Module) -> ast.ExceptHandler:
    """本单唯一那一格改动：写侧那支同时接生命周期与审批账本两枚具名错。"""
    found = [
        handler
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and sorted(_handler_names(handler)) == sorted([LIFECYCLE_TYPE, LEDGER_TYPE])
    ]
    assert len(found) == 1, f"同时接那两枚具名错的 except 应恰一支（写侧），实测 {len(found)}"
    return found[0]


def _storage_handlers(tree: ast.Module) -> list[ast.ExceptHandler]:
    """把存储拒答翻成 503 的那两支 except —— 读写各一枚，一支都不许多、一枚都不许少。"""
    return [
        handler
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and LIFECYCLE_TYPE in _handler_names(handler)
    ]


def _http_raises(node: ast.AST) -> set:
    """(status_code, detail) 两格都只认字面常量：插值型 detail 不当成已知脸。"""
    faces: set = set()
    for call in ast.walk(node):
        if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "HTTPException"):
            continue
        values = {}
        for keyword in call.keywords:
            if keyword.arg in {"status_code", "detail"} and isinstance(keyword.value, ast.Constant):
                values[keyword.arg] = keyword.value.value
        if "status_code" in values:
            faces.add((values["status_code"], values.get("detail")))
    return faces


def _status_503_raises(node: ast.AST) -> list[ast.Call]:
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and getattr(call.func, "id", "") == "HTTPException"
        and any(
            keyword.arg == "status_code"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == 503
            for keyword in call.keywords
        )
    ]


# --------------------------------------------------------------- 判据乙：名单与脸


def test_the_outlet_roster_is_exactly_the_six_ratified_names():
    """名单用等号判：多一枚（并脸）与少一枚（换脸）在这里各红一次。"""
    roster = _roster(_tree(OUTLET_PY))

    assert roster == OUTLET_HANDLER_ROSTER, "出口的 except 名单变了：" + str(roster)


def test_this_ticket_grew_the_roster_by_exactly_one_named_type():
    """把「只长这一枚」钉成可复算的数：基点五枚 ⇒ 交工六枚，多出来的那枚正是账本那一型。

    右侧那份名单是**写死的字面量**，光比它自己永远不会红，所以这里把同一个数也判在盘上那支
    `except` 现读的名单上：反证刀把折叠摘掉（五枚）或再折一枚进去（七枚），这一枚都必红。
    """
    assert len(BASE_OUTLET_HANDLER_ROSTER) == 5
    assert len(OUTLET_HANDLER_ROSTER) == 6
    added = sorted(set(OUTLET_HANDLER_ROSTER) - set(BASE_OUTLET_HANDLER_ROSTER))
    assert added == [LEDGER_TYPE], f"本单折进来的不止那一枚具名类型：{added}"
    assert "RuntimeError" not in OUTLET_HANDLER_ROSTER, "接父类就是替真 bug 打掩护"

    roster = _roster(_tree(OUTLET_PY))
    assert len(roster) == len(OUTLET_HANDLER_ROSTER), f"盘上的名单枚数变了：{roster}"
    assert sorted(set(roster) - set(BASE_OUTLET_HANDLER_ROSTER)) == [LEDGER_TYPE], (
        f"盘上多出来/少掉的那一枚不是账本错：{roster}"
    )
    assert roster.count(LEDGER_TYPE) == 1, (
        "那枚账本错只该在写侧被接一次；接进读侧就是把 R373 的逐腿缺席折成整页 503"
    )


def test_the_ledger_type_is_folded_at_the_write_exit_only():
    """可达性判据（判据①）：那枚账本错只在今天真走得到的那一支被接住，读侧那支一字未动。"""
    tree = _tree(OUTLET_PY)
    folded = _folded_handler(tree)
    handlers = {tuple(_handler_names(node)) for node in _storage_handlers(tree)}

    assert _enclosing_function(tree, folded) == "_apply", "折叠不在写侧那支里：出口走形了"
    assert handlers == {
        (LIFECYCLE_TYPE, LEDGER_TYPE),
        (LIFECYCLE_TYPE,),
    }, f"读写两支的承接名单不是「写二读一」：{sorted(handlers)}"


def test_the_storage_handlers_are_exactly_two_one_read_one_write():
    tree = _tree(OUTLET_PY)
    handlers = _storage_handlers(tree)

    assert len(handlers) == 2, f"接这两枚具名错的 except 应为两支（一读一写），实测 {len(handlers)}"
    assert {_enclosing_function(tree, handler) for handler in handlers} == {
        "_apply",
        "list_notifications",
    }, "两支承接不在读写那两个出口里"


def test_each_storage_handler_raises_exactly_one_503_and_chains_the_original():
    tree = _tree(OUTLET_PY)
    handlers = _storage_handlers(tree)
    assert len(handlers) == 2, "本枚不许在空名单上空转：先数到人，再逐枚判脸"

    for handler in handlers:
        raises = [node for node in ast.walk(handler) if isinstance(node, ast.Raise)]
        assert len(raises) == 1, "一支 except 里翻出了两张脸"
        assert raises[0].exc is not None and ast.unparse(raises[0].exc).startswith("HTTPException(")
        assert ast.unparse(raises[0].cause) == "exc", "丢了 from exc：那枚账本错就不再是它的出处"
        assert _http_raises(handler) == {(503, STORAGE_CODE)}, "翻出来的不是仓里已有的那一码"


def test_the_module_still_emits_exactly_two_503_raises():
    """判据乙的计数：全模块 `status_code=503` 抛出点恰两枚 —— 多一枚就是新开了一道门。"""
    tree = _tree(OUTLET_PY)
    calls = _status_503_raises(tree)

    assert len(calls) == 2, f"503 抛出点应恰两枚，实测 {len(calls)} 枚"
    assert {
        _enclosing_function(tree, call) for call in calls
    } == {"_apply", "list_notifications"}, "503 从别的格子里长出来了"


def test_the_fold_added_no_error_face_and_reuses_a_ratified_code():
    tree = _tree(OUTLET_PY)

    assert _http_raises(tree) == OUTLET_ERROR_FACES, "出口那三支脸多了一枚或少了一枚"
    assert STORAGE_CODE in set(get_args(ErrorEnvelope.model_fields["code"].annotation)), (
        "接进来的那一码不在既有的封闭枚举里"
    )


# --------------------------------------------------------------- 判据丙：不许静默吞


def test_neither_storage_handler_returns_a_receipt():
    """两支 except 里一枚 `return` 都不许有：把「问不出」答成一张回执就是吞。"""
    for handler in _storage_handlers(_tree(OUTLET_PY)):
        assert not [node for node in ast.walk(handler) if isinstance(node, ast.Return)], (
            "存储拒答被折成了回执：那正是 R373 判过的那张脸"
        )


def test_the_ledger_type_is_a_runtime_error_sibling_not_the_parent():
    """接的是那枚具名类型，不是它的父类：把 RuntimeError 接进来等于替真正的 bug 打掩护。"""
    assert issubclass(hitl_store.PendingApprovalStoreMissing, RuntimeError)
    assert issubclass(state_store.NotificationStateStoreMissing, RuntimeError)
    assert hitl_store.PendingApprovalStoreMissing is not state_store.NotificationStateStoreMissing
    assert not issubclass(
        hitl_store.PendingApprovalStoreMissing, state_store.NotificationStateStoreMissing
    ), "两枚错成了父子：那支 except 就只剩一枚在说话"
    assert not issubclass(
        state_store.NotificationStateStoreMissing, hitl_store.PendingApprovalStoreMissing
    ), "两枚错成了父子：那支 except 就只剩一枚在说话"
    assert "RuntimeError" not in _roster(_tree(OUTLET_PY)), "出口把两枚具名错宽成了一枚父类"


def test_the_outlet_gained_no_broad_catch():
    """宽捕获只许是 R299 那一枚，而且必须还站在 `_ids_from_body` 里。"""
    tree = _tree(OUTLET_PY)
    broad = [
        handler
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and (
            handler.type is None
            or sorted(_handler_names(handler)) in ([""], ["Exception"], ["BaseException"])
        )
    ]

    assert len(broad) == 1, f"出口的宽捕获应恰一枚（R299 那一枚），实测 {len(broad)}"
    assert _enclosing_function(tree, broad[0]) == "_ids_from_body", "那一枚挪了地方：本单不许搬别人的账"


def test_the_outlet_gained_no_ruler_and_no_probe():
    """与 R376 同一格禁令的复算：本单只多一枚 except 名字，不多一把生产尺。"""
    source = _text(OUTLET_PY)

    assert "_is_production_environment" not in source
    assert "_database_available" not in source
    assert "APP_ENV" not in source


# --------------------------------------------------------------- 判据丙后半：不越界


def test_inbox_still_raises_the_ledger_refusal_bare():
    """`can_address` 那一支仍是裸 `raise`，承接名单一字未动：出口说话，不叫写侧闭嘴。"""
    handlers = [
        node
        for node in ast.walk(_function(_tree(INBOX_PY), "can_address"))
        if isinstance(node, ast.ExceptHandler)
    ]
    assert {tuple(_handler_names(node)) for node in handlers} == {
        ("HTTPException",),
        ("PendingApprovalStoreMissing",),  # 具名 = 属性的末名，与 `_handler_names` 同一读法
        ("TypeError", "ValueError"),
    }, f"写侧的承接名单变了（本单禁域）：{[tuple(_handler_names(n)) for n in handlers]}"
    ledger = [node for node in handlers if LEDGER_TYPE in _handler_names(node)]
    assert len(ledger) == 1
    body = [node for node in ledger[0].body if not isinstance(node, ast.Expr)]
    assert len(body) == 1 and isinstance(body[0], ast.Raise) and body[0].exc is None, (
        "写侧那支不再裸上抛：R373 的裁定被改写了"
    )


def test_the_import_spelling_is_the_one_the_api_layer_already_uses():
    """本单没引新依赖形状：这一行与 chat.py / dashboard.py 那两枚逐字同形。"""
    line = "from app.storage import pending_approvals"

    assert line in _text(OUTLET_PY).splitlines(), "出口没按仓里那一枚写法接账本"
    for neighbour in (CHAT_PY, DASHBOARD_PY):
        assert line in _disk_text(neighbour).splitlines(), (
            f"{Path(neighbour).name} 不再是那枚 import 的出处：口径要一起改口"
        )


# --------------------------------------------------------------- 契约与字节形状


def test_the_contract_appends_the_r381_section_once():
    text = _disk_text(CONTRACT)

    assert text.count(R381_HEADING) == 1, "R381 那一节标题不是一枚（或整节被人复制过）"
    section = text.split(R381_HEADING, 1)[1]
    for marker in (STORAGE_CODE, LEDGER_TYPE, LIFECYCLE_TYPE, "migrations/0008", "can_address"):
        assert marker in section, f"契约那一节没提 {marker}"


def test_the_contract_section_says_which_grids_stay_bare():
    """只报不改那两格也要写进契约：缺列与驱动缺失今天仍是裸 500，别把人读成「都治了」。"""
    section = _disk_text(CONTRACT).split(R381_HEADING, 1)[1]

    for marker in ("UndefinedColumn", "driver is unavailable", "500"):
        assert marker in section, f"契约那一节没把仍裸 500 的那两格写清楚：{marker}"


@pytest.mark.parametrize(
    "path",
    [
        OUTLET_PY,
        INBOX_PY,
        CONTRACT,
        Path(__file__).resolve(),
        REPO / "tests" / "test_r381_outlet_answers_the_absent_approval_ledger.py",
        # 本单改过口的那枚既有件也在内：它今天也是交付件，字节形状该一起判（名单与那条改口的理由
        # 写在文件头，落在这份名单里的是「它没被写坏」这一格）。
        REPO / "tests" / "test_r376_gate_shape_pins.py",
    ],
    ids=["outlet", "inbox", "contract", "pins", "behavior", "r376pins"],
)
def test_every_delivered_file_keeps_the_repository_byte_shape(path):
    blob = Path(path).read_bytes()

    assert blob[:3] != b"\xef\xbb\xbf", f"{Path(path).name} 带上了 BOM"
    assert blob.count(b"\n") == blob.count(b"\r\n"), f"{Path(path).name} 里有 lone LF"
    assert blob.replace(b"\r\n", b"").count(b"\r") == 0, f"{Path(path).name} 里有 lone CR"
    assert blob.decode("utf-8").count("\ufffd") == 0, f"{Path(path).name} 里出现 U+FFFD：编码被写坏过"