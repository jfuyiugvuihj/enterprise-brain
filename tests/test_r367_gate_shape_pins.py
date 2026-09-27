"""R367 · 闸门的形状：一枚判定、三条腿、零新增探针账、契约补上的那一格。

本件判的不是行为（那在
`tests/test_r367_dashboard_refuses_a_store_that_is_not_there.py`），是**形状**：判据 3（不新造
第三本探针账）、判据 4（闸门次序）、判据 5（既有捕获仍是具名那一型）三条都要求「下一个改这个
文件的人不能悄悄做到」，所以它们必须是静态钉，而不是行为钉的副产品。判据 6（R365 请总控转给
本族的那格契约文字）也在本件：契约那段话要与代码同读一口井，否则又是一句靠注释维持的口径。

范围全部离线：读文件、跑一次 `git show` 取锚点原文，不 import 产品代码、不起服务、不连库。
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: 本单的基点。只当素材读：与现场读数的等号一侧不许同时出现它（硬规矩 4）。
BASE = "b291324"

DASHBOARD = REPO / "app" / "api" / "v1" / "dashboard.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"

#: 本单那一枚节标题的前缀（与前两单同一把尺子：只取 marker 认的同一枚名字）。
OWN_SECTION_HEADING = "The overview screens refuse a store that is not there"

GATE = "_refuse_unaccounted_screen"
LEG_FUNCTIONS = {"_pending_count", "_alert_counts", "_alert_series"}
ROUTE_FUNCTIONS = {"dashboard_summary", "dashboard_trend"}

#: 本模块里构造 503 的全部出处，具名点名：闸那一枚是本单新增，另外两枚是存量。
STORAGE_DOOR_OWNERS = {GATE, "_trend_unreadable", "_pending_count"}

#: 各条腿交出授权答案的那一枚调用；闸必须排在它之后（判据 4）。
AUTHORIZATION_CALLS = {
    "_alert_counts": ("alerts_api._require_alert_management",),
    "_alert_series": ("_alert_management_principal",),
}


def _source(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path))


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _calls(node: ast.AST) -> list[ast.Call]:
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)]


def _callee(call: ast.Call) -> str:
    return ast.unparse(call.func)


def _keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    return None


def _gate_calls(function: ast.AST) -> list[ast.Call]:
    return [call for call in _calls(function) if _callee(call) == GATE]


def _owner_map(tree: ast.Module) -> dict[int, ast.AST]:
    parent = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def owner(node):
        while node is not None and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node = parent.get(node)
        return getattr(node, "name", "<module>")

    return owner


def _base_file(relative: str) -> str:
    """锚点版本的原文（``git show``）：判「某物在基点上就存在」，不抄今天的读数。"""
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE}:{relative}"],
        capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return _base_normalize(result.stdout.decode("utf-8"))


def _base_normalize(raw: str) -> str:
    return raw.replace("\r\n", "\n")


def _section(text: str, marker: str) -> str:
    headings = [match.start() for match in re.finditer(r"(?m)^## ", text)]
    matched = [start for start in headings if marker in text[start:text.find("\n", start)]]
    assert len(matched) == 1, f"契约里带 {marker} 的二级节应有 1 枚，实得 {len(matched)}"
    start = matched[0]
    following = [position for position in headings if position > start]
    return text[start:following[0]] if following else text[start:]


@pytest.fixture()
def dashboard():
    return _functions(_tree(DASHBOARD))


# ------------------------------------------------- 判据 3 · 不新造第三本探针账
def test_the_module_defines_no_second_production_or_storage_probe(dashboard):
    """`_is_production_environment` 与 `_database_available` 都不许在本模块长出新定义。"""
    assert "_is_production_environment" not in dashboard, (
        "本模块自己定义了一枚生产判定：那是第二本探针账"
    )
    assert "_database_available" not in dashboard, "本模块自己定义了一枚库探针：第二本探针账"


def test_the_module_reads_neither_the_readiness_flag_nor_the_environment():
    """判据 3：`_db_ready` 与 `APP_ENV` 都不许在本模块被直接读 —— 那两本账各有主人。

    `app/common/auth.py` 的重探 docstring 按枚数 `_db_ready` 的读者，
    `tests/test_r246_honest_readiness_claims.py` 拿 AST 复核那个数目：本模块多一枚读者就会把
    那本账读成假话，而那枚钉红的时候改的是别人的口径。环境名单同理，只有一份。
    """
    tree = _tree(DASHBOARD)
    loaded = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
              and isinstance(node.ctx, ast.Load)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                  and isinstance(node.ctx, ast.Load)}
    assert "_db_ready" not in loaded | attributes, "本模块直接读了 auth._db_ready"

    # 判的是读数，不是字面：本件的 docstring 会点名 `APP_ENV`，那不算读者。
    tree = _tree(DASHBOARD)
    read_calls = [
        _callee(call) for call in _calls(tree)
        if _callee(call).endswith(("getenv", "environ.get", "environ.setdefault"))
    ]
    subscripts = [
        ast.unparse(node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Subscript) and ast.unparse(node.value).startswith("os.environ")
    ]
    assert not read_calls, f"本模块自己读环境：{read_calls}"
    assert not subscripts, f"本模块自己读 os.environ：{subscripts}"

    literals = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "APP_ENV" not in literals, "本模块把环境名当字面量传进了判定 = 第二份生产判定"
    assert "_db_ready" not in literals, "本模块用 getattr 读就绪旗标：那是第二本探针账"


def test_the_gate_asks_the_production_question_through_the_existing_reader():
    """判据 3：生产判定用的是 `alerts.py:60` 那一枚读者，本单没在 dashboard 里再写一枚。"""
    gate = _functions(_tree(DASHBOARD))[GATE]
    asked = [_callee(call) for call in _calls(gate)]

    assert asked.count("alerts_api._is_production_environment") == 1, asked
    assert not [
        name for name in asked
        if name.endswith("_is_production_environment")
        and name != "alerts_api._is_production_environment"
    ], f"闸问了第二枚生产判定：{asked}"


def test_each_leg_hands_the_gate_its_own_storage_probe():
    """判据 3：库在不在取各条腿自己的 `_database_available()`，不合并、不派一枚新的。"""
    dashboard = _functions(_tree(DASHBOARD))
    expected = {
        "_pending_count": "pending_approvals._database_available()",
        "_alert_counts": "alerts_api._database_available()",
        "_alert_series": "alerts_api._database_available()",
    }

    for name, probe in expected.items():
        calls = _gate_calls(dashboard[name])
        assert len(calls) == 1, f"{name} 里闸被调了 {len(calls)} 次"
        assert _keyword(calls[0], "database_available") == probe, (
            f"{name} 交给闸的探针不是 {probe}：那条腿的账本换主人了"
        )


def test_the_three_probes_the_gate_uses_already_existed_at_the_base():
    """判据 3 的正面证据：闸用的三枚读数在基点上就存在，本单只是调用它们。"""
    places = {
        "app/api/v1/alerts.py": ("def _database_available(", "def _is_production_environment("),
        "app/storage/pending_approvals.py": ("def _database_available(",),
    }

    for relative, signatures in places.items():
        base = _base_file(relative)
        for signature in signatures:
            assert signature in base, f"{relative} 在 {BASE} 上就没有 {signature}：那是新造的探针"
        live = _source(REPO / relative)
        for signature in signatures:
            assert signature in live, f"{relative} 的 {signature} 在本单之后消失了"


# ------------------------------------------------- 判据 1 · 一屏一枚闸，没有侧门
def test_the_gate_is_one_function_called_from_exactly_three_legs(dashboard):
    """一枚闸、三条腿、别处不许自己拒答。"""
    assert GATE in dashboard, "闸没了"
    tree = _tree(DASHBOARD)
    owner = _owner_map(tree)

    calls = [call for call in _calls(tree) if _callee(call) == GATE]
    assert {owner(call) for call in calls} == LEG_FUNCTIONS, (
        f"闸的调用点不是那三条腿：{sorted({owner(call) for call in calls})}"
    )
    assert len(calls) == 3, f"闸被调了 {len(calls)} 次：某条腿多了一道，或多了侧门"


def test_the_module_opens_exactly_the_storage_doors_it_names():
    """503 的出处逐枚点名：本单只添闸那一枚，别处长出第四枚就红。"""
    tree = _tree(DASHBOARD)
    owner = _owner_map(tree)
    doors: dict[str, list[int]] = {}
    for call in _calls(tree):
        if _callee(call) == "HTTPException" and _keyword(call, "status_code") == "503":
            doors.setdefault(owner(call), []).append(call.lineno)

    assert set(doors) == STORAGE_DOOR_OWNERS, f"503 的出处变了：{doors}"
    assert len(doors[GATE]) == 1, f"闸里长出了第二枚拒答：{doors[GATE]}"


def test_every_refusal_word_is_the_one_the_repo_already_ships():
    """判据 1 后半（静态那半）：本模块所有 503 都吐 `storage_unavailable`，零新增错误码。"""
    codes = {
        _keyword(call, "detail")
        for call in _calls(_tree(DASHBOARD))
        if _callee(call) == "HTTPException" and _keyword(call, "status_code") == "503"
    }

    assert codes == {"'storage_unavailable'"}, f"503 出现了第二张脸：{codes}"


# ------------------------------------------------- 判据 4 · 闸门次序
def test_every_gate_call_sits_behind_its_leg_authorization(dashboard):
    """判据 4（静态那半）：先答「你是谁、能不能做」，再答「这台机器的库在不在」。"""
    for name, auth_calls in AUTHORIZATION_CALLS.items():
        function = dashboard[name]
        gates = _gate_calls(function)
        assert len(gates) == 1, f"{name} 里的闸枚数不是 1"
        for auth_call in auth_calls:
            asked = [call.lineno for call in _calls(function) if _callee(call) == auth_call]
            assert asked, f"{name} 不再问 {auth_call}：那本账得改口"
            assert gates[0].lineno > max(asked), (
                f"{name}: 闸({gates[0].lineno})排到了 {auth_call}({max(asked)})之前 —— "
                "401/403 与 503 之差会变成「这家客户起没起 PG」的探针"
            )


def test_the_pending_leg_gates_before_it_touches_the_ledger(dashboard):
    """判据 4：待批这一腿的授权在路由里（`_pending_count` 收到的就是已过门的 principal），
    所以本模块侧的形状是「闸在 `try` 之前、在任何一次账本读之前」。"""
    function = dashboard["_pending_count"]
    gates = _gate_calls(function)
    assert len(gates) == 1
    trial = next(node for node in function.body if isinstance(node, ast.Try))

    assert gates[0].lineno < trial.lineno, (
        f"闸({gates[0].lineno})排到了账本读({trial.lineno})之后：静默回落已经发生过了"
    )
    assert isinstance(function.body[1], ast.Expr), "闸之前不许再长出一句正事"


def test_the_alert_legs_still_answer_denial_before_storage(dashboard):
    """判据 4：403 ⇒ 返回 ``None``（那一格消失）这一枚既有形状不许动，也不许被闸抢先。"""
    for name in ("_alert_counts", "_alert_series"):
        function = dashboard[name]
        denied = [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
            and node.value.value is None
        ]
        assert denied, f"{name} 的「拒绝 ⇒ 这一格不出现」形状不见了"
        gates = _gate_calls(function)
        assert gates[0].lineno > min(denied), (
            f"{name}: 闸({gates[0].lineno})排到了拒绝那一支({min(denied)})之前"
        )


def test_the_routes_authorize_before_any_leg_that_can_refuse(dashboard):
    """判据 4 的路由侧：两屏第一件正事都是 `intelligence._authorized`，闸长在它后面。"""
    for route in ROUTE_FUNCTIONS:
        function = dashboard[route]
        authorized = [
            call.lineno for call in _calls(function)
            if _callee(call) == "intelligence._authorized"
        ]
        assert authorized, f"{route} 不再走那道共用的 analyze 门"
        for name in LEG_FUNCTIONS:
            for call in _calls(function):
                if _callee(call) == name:
                    assert call.lineno > authorized[0], (
                        f"{route}: {name}({call.lineno})排到了授权({authorized[0]})之前"
                    )


def test_the_gate_reads_nothing_before_it_decides(dashboard):
    """判据 4 的补刀：闸体里除了那两枚判定不读任何账，也没有「先读后拒」的形状。"""
    gate = dashboard[GATE]
    decision = next(node for node in gate.body if isinstance(node, ast.If))
    tested = ast.unparse(decision.test)

    assert tested == "database_available or not alerts_api._is_production_environment()", (
        f"闸的第一句判定换了形状：{tested}"
    )


# ------------------------------------------------- 判据 5 · 既有捕获仍是具名那一型
def test_the_r13_catch_is_still_the_exact_named_type(dashboard):
    """判据 5：不许删、不许合、不许放宽成 `RuntimeError`（驱动缺失也走那条路）。"""
    handlers = [
        node for node in ast.walk(dashboard["_pending_count"])
        if isinstance(node, ast.ExceptHandler) and node.type is not None
    ]

    assert len(handlers) == 1, f"待批这一腿的捕获枚数不是 1：{len(handlers)}"
    handler = handlers[0]
    assert ast.unparse(handler.type) == "pending_approvals.PendingApprovalStoreMissing", (
        f"既有捕获换型了：{ast.unparse(handler.type)}"
    )
    assert handler.name == "exc", "既有捕获的具名因被改了：`raise ... from` 读不到了"
    raises = [node for node in ast.walk(handler) if isinstance(node, ast.Raise)]
    assert len(raises) == 1, "捕获里应当恰好一枚重抛"
    error = raises[0].exc
    assert _callee(error) == "HTTPException"
    assert _keyword(error, "status_code") == "503"
    assert _keyword(error, "detail") == "'storage_unavailable'"
    assert raises[0].cause is not None, "`raise ... from exc` 的因被丢了：运维拿不到那句缺表"


def test_the_module_translates_no_broad_exception_anywhere():
    """判据 5 的推广：本模块不许出现 `except RuntimeError` / `Exception` 的宽捕获。"""
    broad = [
        (ast.unparse(node.type), node.lineno)
        for node in ast.walk(_tree(DASHBOARD))
        if isinstance(node, ast.ExceptHandler) and node.type is not None
        and ast.unparse(node.type) in {"RuntimeError", "Exception", "BaseException"}
    ]

    assert not broad, f"出现了宽捕获，真 bug 会被它洗成 503：{broad}"


# ------------------------------------------------- 判据 6 · 契约补上的那一格
def test_the_contract_appends_one_section_and_deletes_nothing():
    """硬规矩 4 那把尺子：文末纯追加、节数只增、本单那一枚标题在追加段里恰一枚。"""
    base = _base_file("docs/api/contract-v1.md")
    now = _source(CONTRACT)

    assert now.startswith(base), "契约不是纯追加：文末之前的每一个字都不许动"
    assert now.count("\n## ") >= base.count("\n## ") + 1, "一节都没长出来：本单没往契约里写口径"
    assert now[len(base):].count("\n## " + OWN_SECTION_HEADING) == 1, "本单那一节在追加段里恰一枚"


def test_the_new_section_states_the_two_faces_and_why_absence_was_not_available():
    """判据 1 的理由要进契约：为什么整屏拒答，以及开发态那一支为什么一个字都不改。"""
    section = _section(_source(CONTRACT), "R367")

    for marker in (
        "storage_unavailable", "_refuse_unaccounted_screen", "_alert_counts", "_alert_series",
        "_pending_count", "_MEM_ALERTS", "_MEM_ROWS", "403", "documents_ready", "R284",
        "R332", "R356", "R359", "R299", "401",
    ):
        assert marker in section, f"契约那一节没提 {marker}"
    assert "503" in section and "200" in section, "两张脸没各自写清答什么"
    assert "openapi" not in section.lower(), "这一节不改契约机读件：那是另一枚单的事"


def test_the_new_section_carries_the_bucket_edge_paragraph_r365_asked_for():
    """判据 6：最新一档的档边用 `min(_bucket_end, now)` 夹住，闭档按各自档边回放。"""
    section = _section(_source(CONTRACT), "R367")

    for marker in ("min(_bucket_end", "_trend_now", "replay", "edge", "当下"):
        assert marker in section, f"档边那一格缺了 {marker}"
    assert "newest" in section or "最新" in section, "没说清只有还没闭合的那一档对当下回放"


def test_the_bucket_edge_words_in_the_contract_match_the_code():
    """契约与代码同读一口井：那段话用的写法代码里仍在；改了代码不改话，本枚红。"""
    source = _source(DASHBOARD)

    assert "now = _trend_now()" in source, "每请求只读一次钟那句话在代码里没了"
    assert "horizon[start] = min(_bucket_end(period, start), now)" in source, (
        "档边夹住这一件事换了写法：契约那段话得跟着改口"
    )


# ------------------------------------------------------ 硬规矩 5 · 字节形状
@pytest.mark.parametrize(
    "relative",
    [
        "app/api/v1/dashboard.py",
        "docs/api/contract-v1.md",
        "tests/test_r367_dashboard_refuses_a_store_that_is_not_there.py",
        "tests/test_r367_gate_shape_pins.py",
    ],
)
def test_the_files_this_ticket_touched_keep_the_repo_line_ending(relative):
    """全件 CRLF、lone LF 0、无 BOM：本单动的与新建的都按仓里那把尺子交。"""
    data = (REPO / relative).read_bytes()

    assert not data.startswith(b"\xef\xbb\xbf"), f"{relative} 带了 BOM"
    assert b"\r\r\n" not in data, f"{relative} 出现了 \\r\\r\\n：那是重复转换"
    lone = data.count(b"\n") - data.count(b"\r\n")
    assert lone == 0, f"{relative} 有 {lone} 枚 lone LF"
    assert data.count(b"\r\n") > 0, f"{relative} 整个不是 CRLF"
