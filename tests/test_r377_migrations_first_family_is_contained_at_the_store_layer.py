"""R377 · 「run migrations first」同族另外四枚：逐枚取证之后判定**不折 503**，本单零生产码改动。

R371 把 `app/api/v1/alerts.py` 那三句在 HTTP 出口折成 503 之后，交回「同族那句话在另外六枚模块
各长着一枚」。本单领到其中四枚：`app/common/auth.py`、`app/documents/catalog.py`、
`app/memory/long_term.py`、`app/memory/profile.py`（行号在本单基点 `07356f1` 重取，不沿用上一班）。

四问逐枚答完的结论是：**四枚全部判不可达**——每一枚的抛点都被本模块自己的宽捕获吃在
store 层，没有任何一枚能把这句 RuntimeError 递到 HTTP 出口，四枚模块里 `HTTPException` 与
`status_code=503` 的抛出数都是 **0**（判据 2：模块根本没有拒答闸，就不许现造一枚闸来凑达标）。
现场量到的真实回话一律取自 `TestClient(..., raise_server_exceptions=False)`，逐枚点名:

  · `auth.py:414`（吃掉它的是 `:257` R230 重探、`:478` import 探针）
    ⇒ `POST /api/v1/login` 答 **401** `{"detail":"用户名或密码错误"}`；
      `GET /api/v1/profile` 答 **401** `{"detail":"authentication_required"}`
  · `catalog.py:516`（吃掉它的是 `:552 / :700 / :722 / :754 / :819` 五枚）
    ⇒ `GET /api/v1/documents` 与 `/documents/catalog` 答 **200** `{"documents":[]}`；
      `GET /api/v1/documents/{f}/versions` 答 **404** `resource_not_found`
  · `long_term.py:69`（吃掉它的是 `:176` 写、`:192` 读）
    ⇒ 这一枚压根没有自己的 HTTP 出口: `remember()` 答 `False`、`recall()` 答 `[]`
  · `profile.py:83`（吃掉它的是 `:141` 读、`:190` 写）
    ⇒ `GET /api/v1/profile` 答 **200**（退回 `users` 那一行）；
      `PUT /api/v1/profile` 答 **500** `{"detail":"画像保存失败"}` —— 那枚 500 是**路由层自己
      写的** `HTTPException`（`app/api/v1/auth.py:281`，不在本单写域），不是逃出去的裸 500

🔴 两件必须说清的边界，不许从这份记录里读丢：
1. 「不折 503」不等于「这一族没问题」。catalog 与 profile 那两枚的真症状是**反方向**的：存储现查到
   缺表，出口却答 200 空集 / 200 画像，把「问不出」说成「没有」——那是 R359/R356/R332 同一条裁定
   （存储拒答不许翻译成空集），修它要摘掉 store 层的回落、并给模块配一枚闸，越出本单写域，已进
   回执「只报不改」。
2. 效力边界：本件全部跑在**替身台账**上。替身只求值「`to_regclass('public.x')` 这一次现查怎么答」，
   不求值任何真实 SQL、不碰真库、不起容器。所以本件证明的是「出口在读到缺表时答什么」，
   **不**证明「跑 migrations 真能把那一格补出来」。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.common import auth
from app.documents import catalog
from app.main import app
from app.memory import long_term, profile

REPO = Path(__file__).resolve().parents[1]
SENTENCE = "run migrations first"
BARE_500_BODY = "Internal Server Error"

#: 本单基点 `07356f1` 现取的抛点：一枚模块一句，行号与消息文本逐字登记（有人改口就红）。
RAISE_SITES = {
    "app/common/auth.py": (
        414,
        'raise RuntimeError("users table is required in production; run migrations first")',
    ),
    "app/documents/catalog.py": (
        516,
        'raise RuntimeError("document_versions table is required in production; '
        'run migrations first")',
    ),
    "app/memory/long_term.py": (
        69,
        'raise RuntimeError("memories table is required in production; run migrations first")',
    ),
    "app/memory/profile.py": (
        83,
        'raise RuntimeError("user_profiles table is required in production; '
        'run migrations first")',
    ),
}

#: 把抛点吃在 store 层的那几行：一枚模块的每一枚 `_ensure()` / `_create_schema()` 调用点，
#: 都必须落在列出的那枚 catch-all handler 的 `try` 里面（AST 判，见下面的形状钉）。
GUARD_BY_MODULE = {
    "app/common/auth.py": (257, 478),
    "app/documents/catalog.py": (552, 700, 722, 754, 819),
    "app/memory/long_term.py": (176, 192),
    "app/memory/profile.py": (141, 190),
}

#: 每枚模块里 `_ensure()` / `_create_schema()` 的直接调用点行数（`app/**` 全仓现读）。
CALL_SITES = {
    "app/common/auth.py": (255, 475),
    "app/documents/catalog.py": (545, 671, 710, 742, 807),
    "app/memory/long_term.py": (165, 183),
    "app/memory/profile.py": (130, 173),
}

GUARDED_FUNCTIONS = frozenset({"_ensure", "_create_schema"})
_REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)

ADMIN = "r377-admin"
ACCOUNT = {"id": "u-r377", "username": ADMIN, "role": "admin", "department": "", "status": "active"}


def _as_authenticated_user(monkeypatch, module) -> None:
    """让中间件与授权层都答得出这个人：本件只判存储那一格，不重开权限的账（判据 4）。"""
    monkeypatch.setattr(
        module, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None
    )


class _Recorder:
    """把出口日志留下来：证明那句 RuntimeError 真的**在请求期间抛过一次**，只是没逃出去。"""

    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def debug(self, message, *args, **kwargs):
        self.lines.append(("debug", str(message)))

    def info(self, message, *args, **kwargs):
        self.lines.append(("info", str(message)))


    def warning(self, message, *args, **kwargs):
        self.lines.append(("warning", str(message)))

    def error(self, message, *args, **kwargs):
        self.lines.append(("error", str(message)))


    def mentions(self, needle: str) -> list[str]:
        return [text for _level, text in self.lines if needle in text]


class _Store:
    """替身台账：只对 `to_regclass('public.x')` 这一枚现查作答，别的语句一律不认。"""

    def __init__(self, tables=(), label="store"):
        self.tables = set(tables)
        self.label = label
        self.statements: list[str] = []
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        found = _REGCLASS.search(text)
        if not found:
            self._rows = []
            return self
        name = found.group(1)
        self._rows = [{"table_name": name if name in self.tables else None}]
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def commit(self):
        raise AssertionError(f"{self.label}: 生产分支不许在运行期提交 DDL")

    def close(self):
        return None


def _source(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"写集里的文件不见了: {path}"
    return path.read_text(encoding="utf-8")


def _tree(relative: str) -> ast.Module:
    return ast.parse(_source(relative))


def _is_catch_all(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    dumped = ast.dump(handler.type)
    return "Exception" in dumped


def _guarded_call_lines(tree: ast.Module) -> dict[int, int]:
    """`{调用行: 包住它的 catch-all handler 行}`；没有 catch-all 兜着的调用点不会出现在这里。"""
    guarded: dict[int, int] = {}

    class Walk(ast.NodeVisitor):
        def visit_Try(self, node):  # noqa: N802
            handlers = [handler for handler in node.handlers if _is_catch_all(handler)]
            if handlers:
                inner = min(handler.lineno for handler in handlers)
                for call in ast.walk(node):
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id in GUARDED_FUNCTIONS
                    ):
                        guarded[call.lineno] = inner
            self.generic_visit(node)

    Walk().visit(tree)
    return guarded


def _unguarded_call_lines(tree: ast.Module) -> list[int]:
    found = [
        call.lineno
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in GUARDED_FUNCTIONS
    ]
    guarded = _guarded_call_lines(tree)
    return [line for line in sorted(found) if line not in guarded]


def _raise_sites(tree: ast.Module, status_code: str) -> list[int]:
    """按 AST 数 `raise HTTPException(status_code=<status_code>, ...)` 的抛出点。"""
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
                continue  # 参数化的抛出点（`status_code=status_code`）不是本件要数的那一格
            if value == int(status_code):
                lines.append(node.lineno)
    return sorted(lines)


# ======================================= 第 2 节判据 1：抛点逐枚在册，一句不多、一句不少
@pytest.mark.parametrize("relative", sorted(RAISE_SITES))
def test_each_module_carries_exactly_one_of_those_sentences(relative):
    """R371 交回来的「各一枚」在本单基点上复核成立：一枚模块恰好一句，且行号与措辞逐字未动。"""
    source = _source(relative)
    line, expected = RAISE_SITES[relative]
    occurrences = [
        number for number, text in enumerate(source.splitlines(), start=1) if SENTENCE in text
    ]

    assert occurrences == [line], f"{relative} 的抛点应当恰好一枚且在 :{line}，实测 {occurrences}"
    assert expected in source, f"{relative}:{line} 那句话被改口了：{expected}"


# ============================ 第 2 节判据 2：没有 HTTP 出口——四枚模块既无 HTTPException 也无 503
@pytest.mark.parametrize("relative", sorted(RAISE_SITES))
def test_none_of_the_four_modules_owns_an_http_exit(relative):
    """判据 2 的前提：这四枚是 store 层，闸门一枚都没有，所以「现造一枚闸」不在许可范围内。"""
    tree = _tree(relative)

    assert "HTTPException" not in _source(relative), f"{relative} 里出现了 HTTPException：本件的判定作废"
    assert _raise_sites(tree, "503") == [], f"{relative} 长出了 503 抛出点：改判前请先重取可达性"


def test_r371_alone_still_owns_the_single_migration_exit():
    """对照：全仓那句「缺迁移答 503」仍然只有 alerts 那一枚闸在答，本单没有把它复制一份。"""
    assert _raise_sites(_tree("app/api/v1/alerts.py"), "503") == [133]


# ================== 第 2 节判据 2 的正面：每一枚调用点都被本模块的 catch-all 吃在 store 层
@pytest.mark.parametrize("relative", sorted(RAISE_SITES))
def test_every_call_site_is_swallowed_by_the_named_handlers(relative):
    """`_ensure()` / `_create_schema()` 的每一枚直接调用点，都必须落在登记过的那几行 catch-all 里。

    🔴 这张表就是「判不可达」的全部依据：调用点一枚不少（与基点现读相等）、且一枚不漏地有 catch-all
    兜着。少一枚 handler、多一枚裸调用点，本件立刻红——那才是「这句错能逃到 HTTP 出口」的形状。
    """
    tree = _tree(relative)
    guarded = _guarded_call_lines(tree)
    expected_handlers = set(GUARD_BY_MODULE[relative])
    expected_calls = CALL_SITES[relative]

    assert sorted(guarded) == sorted(expected_calls), (
        f"{relative} 的受保护调用点变了：登记 {sorted(expected_calls)}，实测 {sorted(guarded)}"
    )
    assert sorted(set(guarded.values())) == sorted(expected_handlers), (
        f"{relative} 吃掉它的 handler 变了：登记 {sorted(expected_handlers)}，"
        f"实测 {sorted(set(guarded.values()))}"
    )
    assert _unguarded_call_lines(tree) == [], (
        f"{relative} 长出没有 catch-all 兜着的调用点：{_unguarded_call_lines(tree)}"
    )


def test_the_two_out_of_write_set_modules_are_still_report_only():
    """`orchestrator.py` / `chat.py` 两枚不在本单写域：这里只登记事实，一根手指都不动。

    R384 改口（只报先行，改的就是下面这一枚断言的口径）：原件把 `chat.py` 那枚 `raise` 的**整行
    原文**抄进断言，正是 R346 / R351 点名的"抄一句源文本当判据"那族病。R384 把那一枚 raise 折成
    同族具名子类 `ChatSchemaNotMigratedError`（消息文本一个字节没改，改的只有类型与换行形状），
    原断言就把一次合法改动判成事故。本件真正要登记的从来不是那行的形状，而是**那一句在 `chat.py`
    里仍然只有一枚**，所以判据换成句子计数。类型与出口形状由 R384 自己的件逐枚钉着
    （`tests/test_r384_migrations_first_refuses_at_the_ask_exit.py`），一条都没松。
    """
    orchestrator = _source("app/agents/orchestrator.py")
    chat = _source("app/api/v1/chat.py")
    checkpoint = "PostgresSaver checkpointer is required in production; run migrations first"

    assert orchestrator.count(checkpoint) == 1, "checkpointer 那一句被复制了：可达性账要重取"
    assert chat.count("table is required in production; run migrations first") == 1, (
        "chat 那一句被复制了：可达性账要重取")
    assert chat.count("_require_migrated_tables(") == 3, "chat 的调用点数目变了：可达性账要重取"


# ============================================================= 现场量测：auth.py 那一格答 401


@pytest.fixture
def recorder(monkeypatch):
    """把某一枚模块的 logger 换成记账器：证明那句错真的在请求期间抛过一次。"""

    def wire(module):
        sink = _Recorder()
        monkeypatch.setattr(module, "logger", sink)
        return sink

    return wire


@pytest.fixture
def production(monkeypatch):
    """生产态：`APP_ENV=production`；其余口径全走 conftest 的钉，不连真库、不起服务。"""
    monkeypatch.setenv("APP_ENV", "production")


def _login_client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_the_missing_users_table_refuses_login_with_401_not_a_bare_500(
    production, recorder, monkeypatch
):
    """auth.py:414 在请求路径上真抛过一次，被 R230 重探那枚 catch-all 吃掉 ⇒ 客户看到 401。"""
    from app.common import auth as auth_module

    sink = recorder(auth_module)
    monkeypatch.setattr(auth_module, "psycopg", object())
    monkeypatch.setattr(auth_module, "_db_ready", False)
    monkeypatch.setattr(auth_module, "_last_ready_probe_at", None)
    monkeypatch.setattr(auth_module, "_connect_for_request", lambda operation: _Store(label="auth"))

    response = _login_client().post("/api/v1/login", json={"username": ADMIN, "password": "secret123"})

    assert SENTENCE in "".join(sink.mentions("R230 重探连上但用户表不可用")), "抛点没被走到：本件判不了可达性"
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "用户名或密码错误"}
    assert BARE_500_BODY not in response.text


def test_the_missing_users_table_answers_the_profile_route_with_the_middlewares_401(
    production, recorder, monkeypatch
):
    """中间件那一腿同样过这枚闸：`get_user` 被拒 ⇒ 401 `authentication_required`，不是 500。"""
    from app.common import auth as auth_module

    sink = recorder(auth_module)
    monkeypatch.setattr(auth_module, "psycopg", object())
    monkeypatch.setattr(auth_module, "_db_ready", False)
    monkeypatch.setattr(auth_module, "_last_ready_probe_at", None)
    monkeypatch.setattr(auth_module, "_connect_for_request", lambda operation: _Store(label="auth"))

    response = _login_client().get(
        "/api/v1/profile", headers={"Authorization": f"Bearer {auth.create_token(ADMIN)}"}
    )

    assert sink.mentions("R230 重探连上但用户表不可用"), sink.lines
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "authentication_required"}
    assert BARE_500_BODY not in response.text


# ============================================================ 现场量测：catalog.py 那一格答 200 空
def _catalog_store(monkeypatch, recorder):
    from app.common import auth as auth_module

    sink = recorder(catalog)
    monkeypatch.setattr(auth_module, "_db_ready", True)
    monkeypatch.setattr(auth_module, "_memory_store_denied", lambda operation: False)
    _as_authenticated_user(monkeypatch, auth_module)
    monkeypatch.setattr(catalog, "_initialized", False)
    monkeypatch.setattr(catalog, "_conn", lambda: _Store(label="catalog"))
    return sink


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(ADMIN)}"}


def test_the_missing_document_versions_table_answers_200_empty_and_never_500(
    production, recorder, monkeypatch
):
    """catalog.py:516 被 :722 那枚 catch-all 吃掉 ⇒ 回落本地台账，答 200 空集（判不可达，也记下真症状）。"""
    sink = _catalog_store(monkeypatch, recorder)
    client = _login_client()

    listing = client.get("/api/v1/documents", headers=_headers())
    catalog_view = client.get("/api/v1/documents/catalog", headers=_headers())

    assert listing.status_code == 200, listing.text
    assert catalog_view.status_code == 200, catalog_view.text
    assert listing.json() == {"documents": []}
    assert catalog_view.json() == {"documents": []}
    assert BARE_500_BODY not in listing.text + catalog_view.text
    assert sink.mentions("current listing fallback"), "抛点没在请求期间走到：可达性判定缺证据"
    assert any(SENTENCE in line for _level, line in sink.lines), sink.lines


def test_the_missing_document_versions_table_says_404_not_500_on_version_history(
    production, recorder, monkeypatch
):
    sink = _catalog_store(monkeypatch, recorder)

    response = _login_client().get("/api/v1/documents/r377-missing.pdf/versions", headers=_headers())

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "resource_not_found"}
    assert sink.mentions("history fallback"), sink.lines


# ============================================================ 现场量测：profile.py 读 200 / 写 500(有码)
def _profile_store(monkeypatch, recorder):
    from app.common import auth as auth_module

    sink = recorder(profile)
    monkeypatch.setattr(auth_module, "_db_ready", True)
    monkeypatch.setattr(auth_module, "_memory_store_denied", lambda operation: False)
    _as_authenticated_user(monkeypatch, auth_module)
    monkeypatch.setattr(profile, "_initialized", False)
    monkeypatch.setattr(profile, "_conn", lambda: _Store(label="profile"))
    return sink


def test_the_missing_user_profiles_table_reads_200_without_the_stored_columns(
    production, recorder, monkeypatch
):
    sink = _profile_store(monkeypatch, recorder)

    response = _login_client().get("/api/v1/profile", headers=_headers())

    assert response.status_code == 200, response.text
    assert response.json()["profile"]["username"] == ADMIN
    assert "updated_at" not in response.json()["profile"], "PG 那一腿没读成，不许冒充读成了"
    assert sink.mentions("load skipped"), sink.lines
    assert any(SENTENCE in line for _level, line in sink.lines), sink.lines


def test_the_missing_user_profiles_table_writes_an_authored_500_from_the_route_not_a_bare_one(
    production, recorder, monkeypatch
):
    """PUT /profile 那枚 500 是 `app/api/v1/auth.py:281` 自己写的 `HTTPException`。

    store 层（本单写域）在这一格只把错误咽下并 `return False`；要改那一格得改路由 + 给
    `app/memory/profile.py` 现造一枚闸，两样都越出本单，已进「只报不改」。
    """
    sink = _profile_store(monkeypatch, recorder)

    response = _login_client().put(
        "/api/v1/profile", json={"position": "boss", "preferences": ["r377"]}, headers=_headers()
    )

    assert response.status_code == 500, response.text
    assert response.json() == {"detail": "画像保存失败"}, "裸 500 的响应体不是这个：那说明捕获面被摘过"
    assert BARE_500_BODY not in response.text
    assert sink.mentions("save failed"), sink.lines
    assert any(SENTENCE in line for _level, line in sink.lines), sink.lines


# ========================================================== 现场量测：long_term.py 没有 HTTP 脸
def test_the_missing_memories_table_answers_empty_at_the_function_boundary(
    production, recorder, monkeypatch
):
    """`remember()`/`recall()` 是 long_term 唯一的对外形状，两枚都答「空」而不是上抛（:176/:192）。"""
    sink = recorder(long_term)
    monkeypatch.setattr(long_term, "psycopg", object())
    monkeypatch.setattr(long_term, "_initialized", False)
    monkeypatch.setattr(long_term, "_conn", lambda: _Store(label="memory"))
    monkeypatch.setattr(long_term, "_embed", lambda texts: None)

    assert long_term.recall("r377-user", "问题", k=3) == []
    assert long_term.remember("r377-user", "一条记忆") is False
    assert sink.mentions("read failed"), sink.lines
    assert sink.mentions("write failed"), sink.lines
    assert sum(bool(SENTENCE in line) for _level, line in sink.lines) == 2


def _importers_of(dotted: str) -> list[str]:
    """`app/**` 里哪些文件 import 了这一枚模块（按 AST 的 import 边判，不算字符串巧合）。"""
    found: list[str] = []
    for path in sorted((REPO / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            label = str(path.relative_to(REPO)).replace("\\", "/")
            if isinstance(node, ast.ImportFrom) and (node.module or "") == dotted:
                found.append(f"{label}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == dotted:
                        found.append(f"{label}:{node.lineno}")
    return sorted(set(found))


def test_the_memory_legs_have_no_http_exit_of_their_own():
    """`long_term` 在 `app/**` 里只被 graph 节点用，没有任何 API 模块 import 它。

    起图跑模型不在本单许可内（禁模型、禁服务），所以这一枚的 HTTP 脸只取到「函数边界」那一层：
    `remember()`/`recall()` 各自把错咽在 :176/:192。下面那枚 import 边就是「它没有 API 出口」的证据。
    """
    importers = _importers_of("app.memory.long_term")
    api_importers = [edge for edge in importers if edge.startswith("app/api/")]

    assert importers, "app.memory.long_term 的 import 边整个不见了，本件的判据失效"
    assert api_importers == [], f"有人给 long_term 新接了 HTTP 出口：可达性判定要重做 {api_importers}"


# =========================================== 效力边界：源码层继续抛 RuntimeError，本单一个字没改
@pytest.mark.parametrize(
    ("relative", "table", "expected"),
    [
        (
            "app/memory/long_term.py",
            "memories",
            "memories table is required in production; run migrations first",
        ),
        (
            "app/memory/profile.py",
            "user_profiles",
            "user_profiles table is required in production; run migrations first",
        ),
        (
            "app/documents/catalog.py",
            "document_versions",
            "document_versions table is required in production; run migrations first",
        ),
    ],
)
def test_the_source_layer_still_raises_the_named_sentence(monkeypatch, relative, table, expected):
    """既有钉（`tests/test_memory_production_schema.py:83`）打的就是这一层：本单不替换基类语义。"""
    from fastapi import HTTPException

    module = {"app/memory/long_term.py": long_term, "app/memory/profile.py": profile,
              "app/documents/catalog.py": catalog}[relative]
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(module, "_initialized", False, raising=False)
    monkeypatch.setattr(module, "psycopg", object(), raising=False)
    monkeypatch.setattr(module, "_conn", lambda: _Store(tables=(), label=table))

    with pytest.raises(RuntimeError) as caught:
        module._ensure()

    assert str(caught.value) == expected
    assert not isinstance(caught.value, HTTPException)
    assert type(caught.value) is RuntimeError, "本单没给这四枚模块加具名子类：一句都不该有"


def test_the_auth_source_layer_still_raises_the_named_sentence(monkeypatch):
    """`tests/test_bootstrap_admin.py:107` 的家：`_create_schema` 本身照旧抛裸 RuntimeError。"""
    from fastapi import HTTPException

    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError) as caught:
        auth._create_schema(_Store(label="users"))

    assert str(caught.value) == "users table is required in production; run migrations first"
    assert not isinstance(caught.value, HTTPException)
    assert type(caught.value) is RuntimeError
