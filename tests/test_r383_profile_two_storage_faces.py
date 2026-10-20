"""R383 腿 B：`PUT /api/v1/profile` 的两张存储脸必须各说各话。

改之前的现场（R377 量到、本件在基点 `96179ff` 复核）：「`user_profiles` 缺表」与「`_db_ready`
为假」两格今天答**同一个** `500 {"detail": "画像保存失败"}`。那是两句假话压成一句：一来「存储
没迁移」与「存储没起」是两条完全不同的排查路（一条跑 `migrations/0003_legacy_runtime_tables.sql`，
一条查 `DATABASE_URL` 与 PG 进程），一句话盖住两张脸；二来那一格根本不知道自己为什么失败，却
断言了「保存失败」。改之后：前两格各拒 503 `storage_unavailable`（零新增错误码、零新增 status
档位），那两行日志分头说清排查路；500 只留给「存储自报就绪、这一写却真没成」那第三格。

形状上本单守三条：
· 判定留在存储层，出口只做一次窄翻译——照 R356 的 `except auth.UserStoreUnavailable`，路由不许
  用存储状态反推拒答（那是第二本账，`tests/test_r356_users_refusal_face.py:319` 已经钉过）。
· `app/memory/profile.py` 一枚 HTTP 异常都不发起：它抛具名 `ProfileStoreUnavailable`，
  `app/api/v1/auth.py` 把它翻成那枚已有的 503（同 R376「存储层不发起 HTTP」的裁定）。
· 闸只借现成的读数：`_database_available()`（本模块唯一一枚 `_db_ready` 读者）与
  `_is_production_environment()`（与 `app/api/v1/alerts.py:61` 同一把尺），一枚都不新造。

`GET /api/v1/profile` 那一格本单**判不动**（改口与说理见回执第 ⑤ 栏），本件把它今天这张脸钉住，
免得下一班顺手把它一起折成 503。

🔴 效力边界：全部跑在替身台账上，不求值真实 SQL、不碰真库、不起服务、不 DROP 任何东西。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.common import auth
from app.main import app
from app.memory import profile

REPO = Path(__file__).resolve().parents[1]
PROFILE_REL = "app/memory/profile.py"
ROUTE_REL = "app/api/v1/auth.py"
STORAGE_CODE = "storage_unavailable"
SAVE_FAILURE = "画像保存失败"
BARE_500_BODY = "Internal Server Error"
GATE_MISSING_TABLE = "code=storage_unavailable migration=migrations/0003"
GATE_NO_STORE = "code=storage_unavailable（PG 未起）"
REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)

ADMIN = "r383b-admin"
ACCOUNT = {"id": "u-r383b", "username": ADMIN, "role": "admin", "department": "", "status": "active"}


class _Sink:
    def __init__(self):
        self.lines: list[str] = []

    def _log(self, message, *args, **kwargs):
        self.lines.append(str(message))

    debug = info = warning = error = exception = _log

    def containing(self, needle: str) -> list[str]:
        return [line for line in self.lines if needle in line]


class _Store:
    """替身台账：缺表时只回答那一次 to_regclass；表在时让 INSERT 过去并记下 commit。"""

    def __init__(self, tables=(), label="profile"):
        self.tables = set(tables)
        self.label = label
        self.statements: list[str] = []
        self.commits = 0
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        assert not text.upper().startswith(("CREATE", "ALTER")), f"{self.label}: 运行期提交了 DDL"
        found = REGCLASS.search(text)
        if found:
            name = found.group(1)
            self._rows = [{"table_name": name if name in self.tables else None}]
        else:
            self._rows = []
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def commit(self):
        self.commits += 1

    def close(self):
        return None


def _source(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"写域里的文件不见了: {path}"
    return path.read_text(encoding="utf-8")


def _raise_sites_with_status(tree: ast.Module, status: int) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not isinstance(node.exc.func, ast.Name) or node.exc.func.id != "HTTPException":
            continue
        for keyword in node.exc.keywords:
            if keyword.arg != "status_code":
                continue
            try:
                value = ast.literal_eval(keyword.value)
            except ValueError:
                continue
            if value == status:
                lines.append(node.lineno)
    return sorted(lines)


def _function(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _raise_details_with_status(tree: ast.Module, status: int) -> list[str]:
    """把 `raise HTTPException(status_code=<status>, detail=...)` 里那句 detail 逐字取出来。"""
    details: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not isinstance(node.exc.func, ast.Name) or node.exc.func.id != "HTTPException":
            continue
        seen_status = seen_detail = None
        for keyword in node.exc.keywords:
            if keyword.arg == "status_code":
                try:
                    seen_status = ast.literal_eval(keyword.value)
                except ValueError:
                    continue
            elif keyword.arg == "detail":
                seen_detail = keyword.value
        if seen_status == status and isinstance(seen_detail, ast.Constant):
            details.append(str(seen_detail.value))
    return details

def _db_ready_reads(source: str) -> list[int]:
    tree = ast.parse(source)
    lines: list[int] = []
    for node in ast.walk(tree):
        attribute = isinstance(node, ast.Attribute) and node.attr == "_db_ready"
        name = isinstance(node, ast.Name) and node.id == "_db_ready"
        if (attribute or name) and isinstance(node.ctx, ast.Load):
            lines.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in {"getattr", "hasattr"}:
                continue
            names = [arg.value for arg in node.args[1:] if isinstance(arg, ast.Constant)]
            if "_db_ready" in names:
                lines.append(node.lineno)
    return sorted(set(lines))


@pytest.fixture
def world(monkeypatch, tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir()
    sink = _Sink()
    monkeypatch.setattr(profile, "logger", sink)
    monkeypatch.setattr(profile, "_initialized", False)
    monkeypatch.setattr(auth, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None)
    monkeypatch.setattr(auth, "_memory_store_denied", lambda operation: False, raising=False)
    profile._MEM_PROFILES.clear()
    yield {"sink": sink, "monkeypatch": monkeypatch}
    profile._MEM_PROFILES.clear()


def _arm(world, *, environment, db_ready, tables):
    monkeypatch = world["monkeypatch"]
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setattr(auth, "_db_ready", db_ready)
    store = _Store(tables=tables, label="profile")
    monkeypatch.setattr(profile, "_conn", lambda: store)
    return store


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(ADMIN)}"}


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _put(world, body=None):
    return _client().put("/api/v1/profile", json=body if body is not None else {"position": "boss"},
                         headers=_headers())


# ==================================================== 那张被改口的脸：两格不再共用一句假话
def test_a_missing_table_refuses_503_instead_of_the_authored_500(world):
    _arm(world, environment="production", db_ready=True, tables=())

    response = _put(world)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert SAVE_FAILURE not in response.text, "那句它不知道原因的「画像保存失败」又回来了"
    assert BARE_500_BODY not in response.text


def test_a_store_that_never_came_up_refuses_503_too(world):
    _arm(world, environment="production", db_ready=False, tables=())

    response = _put(world)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert SAVE_FAILURE not in response.text


def test_the_two_gaps_log_two_different_routes(world):
    """共用一枚码是本单的硬规矩（零新增错误码）；把它们分辨开的只有那两行日志。"""
    _arm(world, environment="production", db_ready=True, tables=())
    _put(world)
    missing = world["sink"].containing(GATE_MISSING_TABLE)
    assert missing, world["sink"].lines

    world["sink"].lines.clear()
    _arm(world, environment="production", db_ready=False, tables=())
    _put(world)
    down = world["sink"].containing(GATE_NO_STORE)
    assert down, world["sink"].lines
    assert not world["sink"].containing(GATE_MISSING_TABLE), "缺表那一行的排查路又被并给了没起的库"


def test_the_refusal_writes_nothing_to_any_ledger(world):
    """拒答之后进程内那本账必须还是空的：R296/R56 给这一格的实质保证，一个字都不许松。"""
    _arm(world, environment="production", db_ready=True, tables=())

    _put(world)

    assert profile._MEM_PROFILES == {}, profile._MEM_PROFILES


def test_the_direct_call_contract_for_a_down_store_is_unchanged(world):
    """存储层的旧契约照旧：库没起时 `upsert_profile()` 仍然答 `False`（`test_deployment_guards:501`）。

    改口只发生在出口那一张脸上——路由先问一次闸，所以生产客户读到的是 503，而不是那句 500。
    """
    _arm(world, environment="production", db_ready=False, tables=())

    assert profile.upsert_profile(ADMIN, position="boss") is False
    assert profile._MEM_PROFILES == {}


# ==================================================== 三张脸：权限那张不许被并进存储那张
def test_the_permission_answer_stands_before_the_storage_answer(world):
    """department 自助写仍然 403 `department_override_denied`，即便此刻存储正缺表。

    顺序反了就把 403 与 503 之差做成了一枚「这台机器跑没跑 migrations」的探针。
    """
    _arm(world, environment="production", db_ready=True, tables=())

    response = _put(world, {"position": "boss", "department": "it"})

    assert response.status_code == 403, response.text
    assert STORAGE_CODE not in response.text
    assert "department_override_denied" in response.text


def test_an_anonymous_caller_never_meets_the_storage_answer(world):
    response = _client().put("/api/v1/profile", json={"position": "boss"})

    assert response.status_code == 401, response.text
    assert STORAGE_CODE not in response.text


# ==================================================== 判据④：开发/裸机/离线那一条腿一个字没改
@pytest.mark.parametrize("environment", [None, "development", "dev", "staging", "test", "local"])
def test_the_gate_never_bites_outside_a_production_environment(world, environment):
    """同一枚「库没起」的读数，换个环境就必须照旧存进程内表并答 200：两张脸，不是一律 503。"""
    _arm(world, environment=environment, db_ready=False, tables=())

    response = _put(world, {"position": "tester", "preferences": ["concise"]})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}
    saved = profile._MEM_PROFILES[ADMIN]
    assert saved["position"] == "tester", saved
    assert saved["preferences"] == ["concise"], saved
    assert profile.profile_storage_state()["storage_mode"] == "memory"


def test_production_with_its_table_still_writes_and_still_answers_ok(world):
    """闸不是「生产一律 503」：库在、表在，这一格照旧落 PG 并答 200。"""
    store = _arm(world, environment="production", db_ready=True, tables=("user_profiles",))

    response = _put(world, {"position": "boss", "preferences": ["r383"]})

    assert response.status_code == 200, response.text
    assert store.commits == 1, store.statements
    assert any("INSERT INTO user_profiles" in line for line in store.statements), store.statements


# ==================================================== 判据⑤那一格：GET 的脸本单判不动，钉住它
def test_the_profile_read_keeps_its_partial_but_true_face(world):
    """`GET /api/v1/profile` 在生产缺表时仍答 200，但只交它真读得到的那几列（本单的裁定）。

    它没有把拒答折成空集：`position` / `preferences` / `updated_at` 三列一个都不出现，客户读到的
    是「从 `users` 现取的那一行」，不是一句「你没有画像」。本单不改它，理由是这一枚同时喂
    `app/agents/nodes.py:1697` 的 load_memory——把一枚 503 塞进问答链路会把「这一轮带不带职位
    偏好」变成「这一轮答不出来」。这里钉住两条不许漂移的边界：不许冒充读成了 PG，也不许因此
    被顺手折成 503。
    """
    _arm(world, environment="production", db_ready=True, tables=())

    response = _client().get("/api/v1/profile", headers=_headers())

    assert response.status_code == 200, response.text
    body = response.json()["profile"]
    assert body["username"] == ADMIN, body
    for column in ("position", "preferences", "updated_at"):
        assert column not in body, f"PG 那一腿没读成，不许冒充读成了：{column}"
    assert world["sink"].containing("load skipped"), world["sink"].lines


# ==================================================== 判据②：形状一枚都不许多长
def test_the_storage_layer_owns_no_http_exit_of_its_own():
    """`app/memory/profile.py` 一枚 HTTP 异常都不发起：那是出口的活儿（R376 同一条裁定）。"""
    source = _source(PROFILE_REL)

    assert "HTTPException" not in source, "画像存储层自己发起 HTTP 来了"
    assert _raise_sites_with_status(ast.parse(source), 503) == []
    assert _raise_sites_with_status(ast.parse(source), 500) == []


def test_the_route_translates_exactly_one_named_refusal():
    """出口只做一次窄翻译：`except ProfileStoreUnavailable`，不接 `Exception`、不接 `RuntimeError`。"""
    tree = ast.parse(_source(ROUTE_REL))
    route = _function(tree, "update_my_profile")
    assert route is not None, "PUT /profile 这一枚路由不见了"

    caught: list[str] = []
    for node in ast.walk(route):
        if isinstance(node, ast.ExceptHandler):
            caught.append(ast.unparse(node.type) if node.type else "bare")

    assert caught == ["ProfileStoreUnavailable"], caught
    exits = _raise_sites_with_status(tree, 503)
    assert len(exits) == 2, f"auth.py 里那道存储拒答应当只有名册与画像两枚出口：{exits}"
    assert route.lineno <= exits[-1] <= route.end_lineno, "503 不在 PUT /profile 里：翻译搬了家"


def test_the_route_does_not_re_derive_the_refusal_itself():
    """第二本账禁令（R356 同一条）：路由不许自己反推存储状态。"""
    source = _source(ROUTE_REL)

    for forbidden in ("profile_storage_state", "_database_available", "_db_ready", "_is_production"):
        assert forbidden not in source, f"路由绕过存储层的闸自己问那道门 = 第二本账：{forbidden}"


def test_the_module_did_not_grow_a_second_store_probe():
    assert len(_db_ready_reads(_source(PROFILE_REL))) == 1


def test_the_refusal_reuses_a_code_the_enumeration_already_ratifies():
    codes: list[str] = []
    for node in ast.walk(ast.parse(_source("app/agents/contracts.py"))):
        if isinstance(node, ast.ClassDef) and node.name == "ErrorEnvelope":
            for stmt in node.body:
                annotation = getattr(stmt, "annotation", None)
                literal = isinstance(annotation, ast.Subscript) and (
                    getattr(annotation.value, "id", "") == "Literal"
                )
                if literal:
                    codes.extend(e.value for e in annotation.slice.elts if isinstance(e, ast.Constant))

    assert codes, "contracts.py 里读不到 ErrorEnvelope.code 的 Literal，判器不许降级成恒真"
    assert STORAGE_CODE in codes, "本单不许为了「存储拒答」新造一枚码"
    # 🔴 反证刀 4b 的收口（R383 自钉收紧）：出口那两枚 503 交出的都必须逐字是这枚码。
    details = _raise_details_with_status(ast.parse(_source(ROUTE_REL)), 503)
    assert details == [STORAGE_CODE, STORAGE_CODE], f"auth.py 那两枚 503 交出的不是已批准的码：{details}"


def test_the_source_layer_still_raises_the_bare_named_sentence(world):
    """`_ensure()` 那一层一个字没改：仍然抛裸 `RuntimeError`，没有具名子类（R377 钉的就是这层）。"""
    _arm(world, environment="production", db_ready=True, tables=())

    with pytest.raises(RuntimeError) as caught:
        profile._ensure()

    assert str(caught.value) == (
        "user_profiles table is required in production; run migrations first"
    )
    assert type(caught.value) is RuntimeError
    named = profile.ProfileStoreUnavailable
    assert not isinstance(caught.value, named), "给这一层加了具名子类：R377 那枚可达性账要重取"
