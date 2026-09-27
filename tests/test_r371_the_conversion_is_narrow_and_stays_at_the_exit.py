"""R371 · 源文形状钉：转换必须**窄**、必须长在**出口那一层**、不许开第二道 503 门。

本件全部按 AST/源码读，不起服务也不连库。它钉的是形状，行为那半边在
`tests/test_r371_migrations_first_answers_503_not_500.py`（那张「每句 × 每出口」的可达性表）。

四把形状牙：

- 判据 4（窄）：把结论翻译成 503 的那一句 `except`，捕获类型**只许**是 `AlertSchemaNotMigratedError`。
  `except Exception` / `except RuntimeError` / 裸 `except:` 一旦出现在这一层——也就是「把任何运行时
  错误都翻成 503，替真正的 bug 打掩护」——本件当场红。既有那六枚宽捕获（`evaluate_all` 两枚、
  `_ai_analysis`、`_permitted_dataset_files`、`_dataset_department_index`、`daily_report`）逐枚按
  所属函数记账：新长出第七枚宽捕获的函数红。
- 判据 2（层）：`_ensure()` 与 `_require_alert_disposal_schema()` 里不许出现 `HTTPException`，
  也不许调用转换器；八枚 HTTP 出口各自带一层转换（出口 = 路由函数，不是共用的 helper）。
- 判据 1（一枚门）：全模块 `status_code=503` 的抛出点仍然恰好一枚，且仍在 `_require_ready_store`
  里面——转换是**借**那扇门，不是新盖一扇（R359 也按 AST 钉同一格，本件是第二把独立的牙）。
- 判据 3/6③（话与账）：三句话逐字还在、仍以同族类型抛出，第四句（`_dispose_alert` 那句
  「写成了却读不回来」）仍是裸 `RuntimeError`；三格各自指名的迁移文件必须真在 `migrations/` 里。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALERTS_PY = ROOT / "app" / "api" / "v1" / "alerts.py"

FAMILY = "AlertSchemaNotMigratedError"
DOOR = "_require_ready_store"
HELPER = "_migrations_first_at_http_exit"
SCHEMA_PROBES = ("_ensure", "_require_alert_disposal_schema")

#: 本单加了转换的八枚 HTTP 出口（判据 1：凡能逃到出口的，出口必须答 503）。
WRAPPED_ROUTES = {
    "create_rule", "list_rules", "delete_rule", "list_alerts", "get_alert",
    "acknowledge_alert", "close_alert", "assign_alert",
}
#: 不套转换的两枚，各有各的凭据（不许当逃逸报，也不许顺手加一层假账）：
#: - `check_now`：它那一腿的 `_ensure()` 在 `evaluate_all` 里已被既有宽捕获吃掉（R345 钉「永不上抛」）。
#: - `_dispose_alert`：三条处置写口共用的 helper，不是 HTTP 出口（判据 2 的层界）。
EATEN_ROUTES = {"check_now": "evaluate_all"}
SCHEMA_HELPERS = {"_dispose_alert"}
#: 三条处置写口不直接调 `_ensure()`：它们调共用的 `_dispose_alert`，所以出现在「带转换」名单
#: 里而不出现在「直接查 schema」名单里。
DISPOSAL_ROUTES = {"acknowledge_alert", "close_alert", "assign_alert"}

#: 交付现场读到的六枚既有宽捕获所属函数（`git show HEAD:app/api/v1/alerts.py` 数出来的存量）。
PREEXISTING_BROAD_CATCHES = {
    "_dataset_department_index", "_ai_analysis", "_permitted_dataset_files",
    "evaluate_all", "daily_report",
}

#: 三句消息文本（判据 3）：逐字比对，改口即红。
SENTENCE_LITERALS = (
    '"alerts.department column is required in production; run migrations first"',
    '"alerts.status column is required in production; run migrations first"',
    'f"{table_name} table is required in production; run migrations first"',
)

#: 不属于本族、也不许被翻译掉的那一句（判据 4 的反面：真 bug 不许洗成 503）。
FOREIGN_SENTENCE = "alert disposal wrote a row that cannot be read back"


def _tree() -> ast.Module:
    return ast.parse(ALERTS_PY.read_text(encoding="utf-8"))


def _source() -> str:
    return ALERTS_PY.read_text(encoding="utf-8")


def _functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _callees(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def _caught_names(handler: ast.ExceptHandler) -> set[str]:
    def short(expression: ast.AST) -> str:
        if isinstance(expression, ast.Name):
            return expression.id
        if isinstance(expression, ast.Attribute):
            return expression.attr
        return ast.unparse(expression)

    if handler.type is None:
        return {"<bare>"}
    if isinstance(handler.type, ast.Tuple):
        return {short(element) for element in handler.type.elts}
    return {short(handler.type)}


def _handlers(tree: ast.Module) -> list[ast.ExceptHandler]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]


def _handler_function(tree: ast.Module) -> dict[ast.ExceptHandler, str]:
    owner: dict[ast.ExceptHandler, str] = {}
    for name, node in _functions(tree).items():
        for handler in ast.walk(node):
            if isinstance(handler, ast.ExceptHandler):
                owner[handler] = name
    return owner


def _raises_http(node: ast.AST) -> bool:
    return "HTTPException" in _callees(node)


def _calls_route_with_its_own_name(route: str, node: ast.AST) -> bool:
    """转换器实参里必须点名这枚路由：日志说「哪一条腿拒的」，九枚不许共用一个假名字。"""
    return any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        and call.func.id == HELPER and call.args
        and isinstance(call.args[0], ast.Constant) and call.args[0].value == route
        for call in ast.walk(node)
    )


def _status_503_sites(tree: ast.Module) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "HTTPException"
        and any(keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == 503 for keyword in node.keywords)
    ]


# ================================================= 判据 4：捕获只做一件事——只接同族那一种错
def test_only_the_named_family_is_translated_at_an_http_exit():
    """任何「把结论交给存储门 / 自己抛 HTTP」的 `except`，捕获类型必须恰好是这一族。"""
    tree = _tree()
    translators = [
        handler for handler in _handlers(tree)
        if DOOR in _callees(handler) or _raises_http(handler)
    ]

    assert translators, "本单的转换不见了：没有任何出口再接这一族错误"
    for handler in translators:
        assert _caught_names(handler) == {FAMILY}, (
            f"alerts.py:{handler.lineno} 把 503 翻译做在了 {sorted(_caught_names(handler))} 上："
            "宽捕获会替真正的 bug 打掩护（驱动缺失也走这条路）"
        )


def test_the_conversion_layer_catches_no_broad_shape():
    """转换器本体只许有一枚 `except`，且既不是 `Exception`/`BaseException`/`RuntimeError` 也不是裸 `except:`。"""
    helper = _functions(_tree())[HELPER]
    handlers = [node for node in ast.walk(helper) if isinstance(node, ast.ExceptHandler)]

    assert len(handlers) == 1, ast.unparse(helper)
    caught = _caught_names(handlers[0])
    assert caught == {FAMILY}, caught
    assert not caught & {"Exception", "BaseException", "RuntimeError", "<bare>"}


def test_no_bare_except_anywhere_in_the_module():
    """裸 `except:` 一枚都不许有（它连 `KeyboardInterrupt` 都吞）。"""
    assert [
        handler for handler in _handlers(_tree()) if handler.type is None
    ] == []


def test_the_broad_catches_stay_the_pre_existing_ones():
    """宽捕获的存量账：仍然只有那五枚函数里的那些，第六枚函数长出宽捕获就红。

    🔴 这把尺不数总数（总数是手抄账，插一行注释都会漂），它数的是「哪些函数里有宽捕获」，
    并对多出来的那一枚点名行号。
    """
    tree = _tree()
    owner = _handler_function(tree)
    broad = {
        owner.get(handler, "<module>")
        for handler in _handlers(tree)
        if "Exception" in _caught_names(handler) or "BaseException" in _caught_names(handler)
    }

    extra = sorted(broad - PREEXISTING_BROAD_CATCHES)
    assert extra == [], (
        f"多出了宽捕获的函数 {extra}：本单只准接 {FAMILY}，宽捕获等于把真 bug 翻成 503"
    )
    assert any(handler.type is not None and "Exception" in _caught_names(handler)
               for handler in _handlers(tree)), "既有那六枚宽捕获不见了：巡检退出的口径变了"


# ================================================= 判据 2：转换只做在 HTTP 出口那一层
@pytest.mark.parametrize("probe", SCHEMA_PROBES)
def test_the_schema_probes_stay_runtime_error_talkers(probe):
    """`_ensure()` / `_require_alert_disposal_schema()` 既不抛 HTTP，也不自己套转换。"""
    node = _functions(_tree())[probe]

    assert not _raises_http(node), f"{probe} 被改成了 HTTP 脸：既有 pytest.raises 的账被改了"
    assert HELPER not in _callees(node), f"{probe} 自己翻译了自己：层界没了"
    assert FAMILY in _callees(node), f"{probe} 不再抛这一族：本单的窄捕获会空响"


def test_the_shared_disposal_helper_does_not_translate_itself():
    """`_dispose_alert` 是三条写口共用的 helper，不是出口：转换留在路由上。

    它当然还会经 `_refuse_alert_disposal` 抛 404/409/400（R251 的存量），本枚判的只是
    「同族那三句没有在这一层被翻译」。
    """
    node = _functions(_tree())["_dispose_alert"]

    assert HELPER not in _callees(node)
    assert DOOR in _callees(node), "R359 那道闸不该被搬走：它管的是「库根本不在」那一格"


@pytest.mark.parametrize("route", sorted(WRAPPED_ROUTES))
def test_every_escaping_exit_carries_its_own_conversion(route):
    """八枚能逃的出口逐枚点名：路由函数里必须有一次转换器调用（判据 1 的形状那一半）。"""
    node = _functions(_tree())[route]

    assert HELPER in _callees(node), f"{route} 不再翻译同族错误：它会交裸 500"
    assert _calls_route_with_its_own_name(route, node), f"{route} 的 operation 名不是自己"


def test_the_eaten_exit_is_deliberately_not_wrapped():
    """`check_now` 那一格被既有宽捕获吃掉：本单不在它上面加假账（可达性表里那一行）。"""
    functions = _functions(_tree())

    assert HELPER not in _callees(functions[EATEN_ROUTES["check_now"]])
    assert HELPER not in _callees(functions["evaluate_all"])


def test_every_schema_probe_call_site_is_accounted_for():
    """谁调 `_ensure()` / `_require_alert_disposal_schema()`，逐枚归账：未记账的第九枚调用点红。"""
    functions = _functions(_tree())
    callers = {
        name
        for name, node in functions.items()
        if any(probe in _callees(node) for probe in SCHEMA_PROBES)
    }
    wrapped = {
        name for name, node in functions.items() if HELPER in _callees(node)
    }

    assert callers == (WRAPPED_ROUTES - DISPOSAL_ROUTES) | SCHEMA_HELPERS \
        | set(EATEN_ROUTES.values()), sorted(callers)
    assert wrapped == WRAPPED_ROUTES, sorted(wrapped)
    assert DISPOSAL_ROUTES <= wrapped, "三条处置写口不再各自带转换：helper 被当成了出口"


# =============================================== 判据 1：借那一枚门，不新盖第二道 503
def test_the_module_still_opens_exactly_one_storage_door():
    """全模块 `status_code=503` 仍然恰好一枚，且仍在 `_require_ready_store` 里（R359 之外的第二把牙）。"""
    tree = _tree()
    sites = _status_503_sites(tree)

    assert len(sites) == 1, f"503 出口长出了 {len(sites)} 枚: {[s.lineno for s in sites]}"
    door = _functions(tree)[DOOR]
    assert door.lineno <= sites[0].lineno <= (door.end_lineno or door.lineno), (
        "那枚 503 搬出了存储门：有人绕过闸自己拒答"
    )


def test_the_conversion_funnels_through_the_existing_gate():
    """转换器不自己抛 503：它把结论交给闸，且明说「这一格是迁移没跑」。"""
    helper = _functions(_tree())[HELPER]
    calls = [
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == DOOR
    ]

    assert len(calls) == 1, ast.unparse(helper)
    assert not _raises_http(helper), "转换器自己开了一第二道门"
    flags = {
        keyword.arg: ast.unparse(keyword.value)
        for call in calls for keyword in call.keywords
    }
    assert flags == {"migrations_missing": "True"}, flags


def test_alerts_does_not_rely_on_a_global_safety_net():
    """本件不靠全局兜底把 500 洗白：模块里既没有 `exception_handler`，也没有中间件形状的补丁。"""
    source = _source()

    assert "exception_handler" not in source
    assert "middleware" not in source


# ============================================= 判据 3 / 4 反面：话没改口，别的话也没被卷进来
def test_the_three_sentences_are_verbatim_and_raise_the_family():
    """三句原文逐字还在，且都以同族类型抛出（判据 3 + 判据 1 的出处）。"""
    source = _source()
    tree = _tree()
    raised = {
        ast.unparse(node.exc.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name) and node.exc.func.id == FAMILY
    }

    for literal in SENTENCE_LITERALS:
        assert literal in source, f"这句话被改口了：{literal}"
    assert len(raised) == 3, sorted(raised)
    assert any("table is required in production" in expression for expression in raised)


def test_the_foreign_runtime_error_stays_foreign():
    """第四句（写成了却读不回来）仍是裸 `RuntimeError`：真 bug 不许被本单翻译掉。"""
    tree = _tree()
    foreign = {
        ast.unparse(node.exc.args[0]).strip("'")
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name) and node.exc.func.id == "RuntimeError"
    }

    assert foreign == {FOREIGN_SENTENCE}, sorted(foreign)


def test_the_family_is_declared_once_on_the_runtime_error_base():
    """只加一层具名：本模块 `RuntimeError` 的直接子类恰好这一枚，基类语义没被替换。"""
    classes = [
        node for node in _tree().body
        if isinstance(node, ast.ClassDef)
        and [ast.unparse(base) for base in node.bases] == ["RuntimeError"]
    ]

    assert [node.name for node in classes] == [FAMILY], [node.name for node in classes]
    assert classes[0].keywords == [], "子类不该带额外的基类参数"


# ==================================================== 判据 6③：三格各自指名的迁移文件要真存在
@pytest.mark.parametrize("schema_object", [
    "alert_rules table", "alerts table", "alerts.department column", "alerts.status column",
])
def test_each_hint_names_a_migration_file_that_exists(schema_object):
    from app.api.v1 import alerts

    migration = alerts.MIGRATION_REQUIRED_HINTS[schema_object]

    assert migration.startswith("migrations/"), migration
    assert (ROOT / migration).is_file(), f"{migration} 不在 migrations/ 里"


def test_the_three_cells_resolve_to_three_different_remedies():
    """缺表 / 缺归属列 / 缺处置列 ⇒ 三枚不同的迁移文件；认不出来时说的是 unknown，不是沉默。"""
    from app.api.v1 import alerts

    hints = {
        "table": alerts.migration_hint_for(
            "alerts table is required in production; run migrations first"),
        "department": alerts.migration_hint_for(
            "alerts.department column is required in production; run migrations first"),
        "status": alerts.migration_hint_for(
            "alerts.status column is required in production; run migrations first"),
    }

    assert len(set(hints.values())) == 3, hints
    assert hints["table"].startswith("migrations/0003")
    assert hints["department"].startswith("migrations/0012")
    assert hints["status"].startswith("migrations/0014")
    assert alerts.migration_hint_for("some other story") == "unknown"


def test_every_hint_key_is_the_head_of_a_real_sentence():
    """映射表的键必须真对得上模块里那几句话：改掉一句话而忘了改账，本枚红。"""
    from app.api.v1 import alerts

    sentences = [
        f"{key} is required in production; run migrations first"
        for key in alerts.MIGRATION_REQUIRED_HINTS
    ]

    for sentence in sentences:
        assert alerts.migration_hint_for(sentence) != "unknown", sentence
