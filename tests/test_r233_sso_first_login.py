"""R233 反证钉：SSO 首次登录 = 库里没有这个用户，而铸占位口令的 `secrets` 根本没有 import。

病（在基点 ccf8942 上自己复现的通路，不是抄来的结论）：`app/common/auth.py` 在
`upsert_sso_user` 里用 `secrets.token_urlsafe(24)` 给**新用户**铸本地占位口令（内存表支
`:612` / PG 支 `:627`），而该文件的 import 块里从来没有 `secrets`
（`git log -S "secrets.token_urlsafe" -- app/common/auth.py` 到 `de13e90`，与 R229/R230 无关）。
两支的症状完全不同，所以各钉一枚：
- PG 支被函数自己的 `except Exception` 吞成 `(False, "SSO 用户同步失败: name 'secrets'
  is not defined")`，再经 `app/api/v1/auth.py:143` 变成一发 500 —— 客户读到的是"SSO 同步
  失败"，永远看不出真因，且一笔用户都没落库；
- 内存表支没有人兜底，`NameError` 直接砸调用方脸上，对外只剩一句 "Internal Server Error"。
为什么至今没炸：已存在的用户走 UPDATE 支不碰这段代码；而 R229/R230 的钉全用已存在用户
（`tests/test_r229_connect_retry.py:60` 那枚假连接对 `SELECT id FROM users` 恒返回
`{"id": 7}`）⇒ 它们的绿证明不了这条路能走，本单不拿它当凭据。

本文件把两件事分开钉，免得"修好了"三个字自证：
1. **修后为绿的行为钉**：新建用户真的落库，真的拿到一枚不可猜的占位口令；
2. **常绿的病状钉**：把 `auth.secrets` 这枚名字摘掉（= 修前那个文件的真实状态），两支各自
   吐出的那串字面量一字不差。判据 5 的整块 import 摘除跑的就是第 1 组，它必须当场红。

一条真连接都不许发出去：`tests/conftest.py:41-53` 已把 DATABASE_URL 钉成 `127.0.0.1:1` +
`connect_timeout=1`，本文件再加两枚哨兵 —— 复核模块里那枚 DSN 串，以及真驱动一旦想 connect
就当场炸。全程只用假 psycopg 连接对象。
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import bcrypt
import pytest

from app.common import auth

psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[1]
AUTH_SOURCE = (ROOT / "app" / "common" / "auth.py").read_text(encoding="utf-8")

SSO_USER = "first.sso.login"
#: 真驱动在 import 期的原值：用例会把 `auth.psycopg` 摘成 None，回滚时必须有东西可复原。
_REAL_PSYCOPG = auth.psycopg
#: 任何一枚 DSN 都不许指着真主机；建连全部由用例注入假连接，这枚串只做兜底。
UNROUTABLE_DSN = "postgresql://r233@127.0.0.1:1/r233?connect_timeout=1"
BLIP = psycopg.OperationalError("failed to resolve host 'postgres' [Errno -3]")

# 修前逐格读数 = 客户今天看到的症状。字面量钉死在这儿，摘掉名字复现时必须一字不差。
PG_SYMPTOM = (False, "SSO 用户同步失败: name 'secrets' is not defined")
MEMORY_SYMPTOM = "name 'secrets' is not defined"
SUCCESS = (True, "SSO 用户已同步")


class _Result:
    def __init__(self, row=None, rows=(), rowcount=0):
        self._row = row
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _Table:
    """假 users 表：只认 `upsert_sso_user` / `verify_password` / 读路径真会发的那几句 SQL。

    语句与 commit 全程记账，所以"新建用户到底落没落库、UPDATE 支有没有偷偷重铸口令"
    是读数，不是推测。
    """

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.statements = []
        self.commits = 0

    def _by_name(self, username):
        return next((row for row in self.rows if row["username"] == username), None)

    def execute(self, sql, params=None):
        text = " ".join(sql.lower().split())
        params = tuple(params or ())
        self.statements.append(text)
        if text.startswith("select to_regclass"):
            return _Result(row={"table_name": "users"})
        if text.startswith("select count(*) as c from users"):
            return _Result(row={"c": len(self.rows)})
        if text.startswith("select id from users where username"):
            hit = self._by_name(params[0])
            return _Result(row={"id": hit["id"]} if hit else None)
        if text.startswith("select password_hash from users where username"):
            hit = self._by_name(params[0])
            return _Result(row={"password_hash": hit["password_hash"]} if hit else None)
        if text.startswith("select username, role, department from users where username"):
            hit = self._by_name(params[0])
            return _Result() if not hit else _Result(
                row={key: hit[key] for key in ("username", "role", "department")}
            )
        if text.startswith("select id, username, role, department, created_at from users"):
            columns = ("id", "username", "role", "department", "created_at")
            return _Result(
                rows=[{key: row[key] for key in columns} for row in self.rows],
                rowcount=len(self.rows),
            )
        if text.startswith("insert into users"):
            username, password_hash, role, department = params
            self.rows.append(
                {
                    "id": max((row["id"] for row in self.rows), default=0) + 1,
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                    "department": department or "",
                    "created_at": "now",
                }
            )
            return _Result(rowcount=1)
        if text.startswith("update users set role"):
            role, department, username = params
            hit = self._by_name(username)
            if hit:
                hit["role"], hit["department"] = role, department
            return _Result(rowcount=1 if hit else 0)
        raise AssertionError(f"未预期的 SQL: {sql}")

    def commit(self):
        self.commits += 1

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Recorder:
    """假 logger：把"对外可见的日志"变成可比对的字符串列表，供泄漏钉取证。"""

    def __init__(self):
        self.records = []

    def _emit(self, level):
        def send(message, *args):
            self.records.append(f"{level}: {message % args if args else message}")

        return send

    def __getattr__(self, level):
        if level.startswith("_"):
            raise AttributeError(level)
        return self._emit(level.upper())


@pytest.fixture(autouse=True)
def database_url_is_aimed_at_the_reserved_port():
    """哨兵一：本文件的模块态必须仍然指着 conftest 那枚不通的 DSN，一枚真握手都不许发。"""
    assert "127.0.0.1:1/" in auth._PG_URL, auth._PG_URL
    assert "connect_timeout=1" in auth._PG_URL, auth._PG_URL
    assert "localhost" not in auth._PG_URL and ":5432" not in auth._PG_URL, auth._PG_URL


@pytest.fixture(autouse=True)
def no_real_driver_connect(monkeypatch):
    """哨兵二：真驱动的 connect 一律当场炸（假连接全部由用例自己塞）。"""

    def refuse(*args, **kwargs):
        raise AssertionError(
            "tests/test_r233_sso_first_login.py 试图开一条真 PostgreSQL 连接；"
            "R233 全程只用假 psycopg，按 R20 的口径判失败"
        )

    monkeypatch.setattr(psycopg, "connect", refuse, raising=False)
    monkeypatch.setattr(auth.time, "sleep", lambda seconds: None)


def _pg(monkeypatch, rows=None):
    """造"生产 + 库在线 + 库里没有这个人"：SSO 首次登录的真实现场。"""
    table = _Table(rows)
    connects = []

    def fake_raw_conn():
        connects.append(1)
        return table

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "r233-nail-secret-that-is-long-enough-for-hs256")
    monkeypatch.setattr(auth, "_db_ready", True)
    monkeypatch.setattr(auth, "_PG_URL", UNROUTABLE_DSN, raising=False)
    monkeypatch.setattr(auth, "_MEM_USERS", {}, raising=False)
    monkeypatch.setattr(auth, "_raw_conn", fake_raw_conn)
    logger = _Recorder()
    monkeypatch.setattr(auth, "logger", logger)
    return SimpleNamespace(table=table, connects=connects, logger=logger)


def _memory(monkeypatch, *, no_driver):
    """造"库里没有这个人 + 走进程内用户表"。两种成因都钉，免得只在缺驱动时成立。

    `no_driver=True` 是驱动缺失；`False` 是驱动在但启动探针没连上（`_db_ready=False`）。
    两者都让 `_using_memory_store()` 为真，而开发态下 `_memory_store_denied` 不挡这条路。
    """
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(auth, "psycopg", None if no_driver else _REAL_PSYCOPG)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(auth, "_MEM_USERS", {}, raising=False)
    monkeypatch.setattr(auth, "_PG_URL", UNROUTABLE_DSN, raising=False)


def _route_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.auth import router as auth_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def _sso_headers():
    return {
        "X-SSO-Token": "edge-token",
        "X-SSO-User": SSO_USER,
        "X-SSO-Role": "manager",
        "X-SSO-Department": "sales",
    }


# ---------------------------------------------------------------- 判据 1：修前必红的行为钉
def test_a_brand_new_sso_identity_is_created_on_postgres(monkeypatch):
    """PG 支：库里查不到这个人 ⇒ 必须真的 INSERT 一枚带占位口令的新行。

    修前读数（摘掉 import 复跑）：返回 `PG_SYMPTOM`，`table.rows` 空、`commits` 为 0 ——
    一次 SSO 同步整笔丢掉，而对外只说"SSO 用户同步失败"。
    """
    env = _pg(monkeypatch)

    assert auth.upsert_sso_user(SSO_USER, role="manager", department="sales") == SUCCESS

    row = env.table._by_name(SSO_USER)
    assert row is not None, env.table.rows
    assert row["role"] == "manager" and row["department"] == "sales"
    assert isinstance(row["password_hash"], str) and row["password_hash"], row
    assert env.table.commits == 1, env.table.statements
    assert len(env.connects) == 1, "首次登录只该花一枚连接（R229 的每请求一连接口径）"


@pytest.mark.parametrize("no_driver", [True, False], ids=["no-driver", "db-not-ready"])
def test_a_brand_new_sso_identity_is_created_in_the_memory_store(monkeypatch, no_driver):
    """内存表支：同一条新建路径没人兜底，修前直接把 NameError 砸给调用方。"""
    _memory(monkeypatch, no_driver=no_driver)

    assert auth.upsert_sso_user(SSO_USER, role="staff", department="ops") == SUCCESS

    row = auth._MEM_USERS.get(SSO_USER)
    assert row and row["password_hash"], row
    assert row["role"] == "staff" and row["id"] == 1, row


def test_the_sso_login_route_answers_200_for_a_first_time_identity(monkeypatch):
    """端到端：客户接上 SSO 后的第一发 `POST /api/v1/sso/login` 就该拿到 token。

    修前读数：500，`detail` 就是 `PG_SYMPTOM[1]` 那一句。
    """
    monkeypatch.setenv("SSO_ENABLED", "1")
    monkeypatch.setenv("SSO_SHARED_TOKEN", "edge-token")
    env = _pg(monkeypatch)

    response = _route_client().post("/api/v1/sso/login", headers=_sso_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == SSO_USER and body["role"] == "manager"
    payload = auth.verify_token(body["token"])
    assert payload and payload["sub"] == SSO_USER
    assert env.table._by_name(SSO_USER) is not None, env.table.rows


# -------------------------------------------------------------------- 判据 1：常绿的病状钉
def test_the_pg_branch_swallows_the_missing_mint_into_that_exact_message(monkeypatch):
    """把 `secrets` 摘掉 = 修前那个文件的真实状态，此处逐字钉住客户看到的那句话。"""
    env = _pg(monkeypatch)
    # raising=False：修前那枚名字本来就不存在，摘它与不摘它读数相同 —— 病状钉必须跨
    # "修前/修后"两种状态一字不差，否则判据 5 的摘除跑会把红涨到这些钉上。
    monkeypatch.delattr(auth, "secrets", raising=False)

    assert auth.upsert_sso_user(SSO_USER, role="manager", department="sales") == PG_SYMPTOM
    assert env.table.rows == [], "症状必须只来自铸口令，不许留下半笔写入"
    assert env.table.commits == 0, env.table.statements
    assert any(stmt.startswith("select id from users") for stmt in env.table.statements)
    assert not any(stmt.startswith("insert into users") for stmt in env.table.statements)


@pytest.mark.parametrize("no_driver", [True, False], ids=["no-driver", "db-not-ready"])
def test_the_memory_branch_raises_the_bare_nameerror(monkeypatch, no_driver):
    """内存表支没有 `except Exception`：同一枚缺陷换一具面孔，直接抛。"""
    _memory(monkeypatch, no_driver=no_driver)
    monkeypatch.delattr(auth, "secrets", raising=False)

    with pytest.raises(NameError) as excinfo:
        auth.upsert_sso_user(SSO_USER)
    assert str(excinfo.value) == MEMORY_SYMPTOM
    assert auth._MEM_USERS == {}, "抛错之前一个人都没建出来"


def test_the_route_reports_the_swallowed_symptom_when_the_mint_is_missing(monkeypatch):
    """对外形状：PG 支那一句经 `app/api/v1/auth.py:143` 就是一发 500 + 那句原文。"""
    monkeypatch.setenv("SSO_ENABLED", "1")
    monkeypatch.setenv("SSO_SHARED_TOKEN", "edge-token")
    _pg(monkeypatch)
    monkeypatch.delattr(auth, "secrets", raising=False)

    response = _route_client().post("/api/v1/sso/login", headers=_sso_headers())

    assert response.status_code == 500, response.text
    assert response.json()["detail"] == PG_SYMPTOM[1]


def test_the_route_dies_silently_in_memory_mode_when_the_mint_is_missing(monkeypatch):
    """内存表支的对外形状是裸 500，连"SSO"三个字都没有——两支症状不同，都要留档。"""
    monkeypatch.setenv("SSO_ENABLED", "1")
    monkeypatch.setenv("SSO_SHARED_TOKEN", "edge-token")
    _memory(monkeypatch, no_driver=True)
    monkeypatch.delattr(auth, "secrets", raising=False)

    response = _route_client().post("/api/v1/sso/login", headers=_sso_headers())

    assert response.status_code == 500, response.text
    assert "Internal Server Error" in response.text
    assert "secrets" not in response.text


# ---------------------------------------------------------------- 判据 2：占位口令的性质
def _mint_placeholder(monkeypatch, username=SSO_USER):
    env = _pg(monkeypatch)
    assert auth.upsert_sso_user(username, role="staff", department="ops") == SUCCESS
    return env, env.table._by_name(username)


def test_the_placeholder_is_a_bcrypt_digest_and_not_an_empty_password(monkeypatch):
    _env, row = _mint_placeholder(monkeypatch)
    digest = row["password_hash"]

    assert isinstance(digest, str) and digest.strip() == digest
    assert digest not in ("", "None", "none", "null"), digest
    assert digest.startswith("$2") and len(digest) == 60, digest
    assert bcrypt.checkpw(b"not-the-placeholder", digest.encode()) is False


def test_the_placeholder_is_reshaped_for_every_new_identity(monkeypatch):
    """三枚首次登录必须拿到三枚不同的摘要（含不同盐）：它不是写死的常量口令。"""
    env = _pg(monkeypatch)
    digests = []
    for name in ("first", "second", "third"):
        assert auth.upsert_sso_user(name, role="staff", department="ops") == SUCCESS
        digests.append(env.table._by_name(name)["password_hash"])

    assert len(set(digests)) == 3, digests
    assert len({digest[:29] for digest in digests}) == 3, "bcrypt 盐也得不同"


def test_no_plausible_password_opens_an_sso_account(monkeypatch):
    """钉"永远不可能匹配任何真实密码"：可猜集合逐条验，一枚都进不来。"""
    _env, row = _mint_placeholder(monkeypatch)
    digest = row["password_hash"]

    candidates = [
        "",
        " ",
        "None",
        "none",
        "null",
        SSO_USER,
        SSO_USER.split(".")[0],
        "staff",
        "manager",
        "sso",
        "sso-user",
        "placeholder",
        "changeme",
        "change-me",
        "admin",
        "admin123",
        "password",
        "Password1",
        "123456",
        "enterprise_brain",
        digest,
    ]
    matched = [guess for guess in candidates if auth.verify_password(SSO_USER, guess)]
    assert matched == [], matched
    assert auth.verify_password(SSO_USER, digest) is False, "bcrypt 单向：摘要本身不是口令"


def _callee_name(call):
    """`bcrypt.hashpw(...)` -> "bcrypt.hashpw"，供写法约束那两枚钉比对形状。"""
    parts = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _upsert_sso_user_fn():
    tree = ast.parse(AUTH_SOURCE)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "upsert_sso_user"
    )
    return tree, fn


def _mints(fn):
    return [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "token_urlsafe"
    ]


def test_the_mint_is_a_csprng_with_at_least_128_bits_and_no_substitute():
    """结构钉：这两枚占位口令只能由 `secrets.token_urlsafe(<>=16 字节)` 铸出来。

    它挡住的是"以后有人把随机换成常量 / 换成 `random` / 缩短到 8 字节"，也就是
    把上面那枚"可猜集合"从实践结论升级成写法约束。
    """
    _tree, fn = _upsert_sso_user_fn()
    mints = _mints(fn)

    assert len(mints) == 2, [node.lineno for node in mints]
    for mint in mints:
        assert isinstance(mint.func.value, ast.Name) and mint.func.value.id == "secrets", mint.lineno
        assert len(mint.args) == 1 and isinstance(mint.args[0], ast.Constant), mint.lineno
        nbytes = mint.args[0].value
        assert isinstance(nbytes, int) and nbytes >= 16, f"{nbytes} 字节太短，占位口令要 >= 128 bit"


def test_the_preimage_never_gets_a_name_it_goes_straight_into_the_hasher():
    """最硬的一枚：原像（那 24 字节随机数）在这条路上从来没有名字。

    "永远不可能匹配任何真实密码"不靠纪律，靠这段 AST 形状：每一枚 mint 的直接父节点必须是
    `.encode`，再上一层必须是 `bcrypt.hashpw(...)` 的实参位 ⇒ 它一出生就进哈希器，函数里
    没有任何一处能把它 return、log 或塞进审计。想改写法的人必须先让这枚钉红一次。
    """
    _tree, fn = _upsert_sso_user_fn()
    parents = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    mints = _mints(fn)
    assert len(mints) == 2, mints
    for mint in mints:
        encode = parents[mint]
        assert isinstance(encode, ast.Attribute) and encode.attr == "encode", ast.dump(encode)
        call = parents[encode]
        assert isinstance(call, ast.Call) and call.args == [], ast.dump(call)
        hashpw = parents[call]
        assert isinstance(hashpw, ast.Call) and _callee_name(hashpw) == "bcrypt.hashpw", ast.dump(hashpw)


def test_the_file_that_uses_secrets_also_imports_secrets():
    """本单那枚缺陷的直接回归钉：用了 `secrets.X` 就必须 import 它，一字不能少。"""
    tree = ast.parse(AUTH_SOURCE)
    used = {
        node.func.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "secrets"
    }
    imported = {
        (alias.asname or alias.name.split(".")[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert used, "这条钉假设本文件仍然在用 secrets；哪天不用了请连本单一起删"
    assert used <= imported, f"用了 {sorted(used - imported)} 却没有 import"


def test_the_placeholder_never_leaves_the_user_store(monkeypatch):
    """不可猜的前提是没人拿得到它：任何读路径、日志、对外响应都不许带出这枚摘要。"""
    env, row = _mint_placeholder(monkeypatch)
    digest = row["password_hash"]

    assert auth.list_users() == [
        {"id": 1, "username": SSO_USER, "role": "staff", "department": "ops", "created_at": "now"}
    ], auth.list_users()
    for user in auth.list_users():
        assert "password_hash" not in user
    assert auth.get_user(SSO_USER) == {"username": SSO_USER, "role": "staff", "department": "ops"}
    assert digest not in json.dumps(auth.list_users(), ensure_ascii=False)
    assert digest not in "\n".join(env.logger.records), env.logger.records


# ------------------------------------------------------- 判据 3：不许顺手改语义
def test_the_sso_wording_and_return_shape_are_unchanged_in_both_branches(monkeypatch):
    """成功那句、失败那句、返回形状（二元组 + bool 在前）全部按修前原文钉住。"""
    env = _pg(monkeypatch)
    ok, message = auth.upsert_sso_user(SSO_USER)
    assert (ok, message) == (True, "SSO 用户已同步")
    assert isinstance(ok, bool) and isinstance(message, str)

    assert auth.upsert_sso_user("") == (False, "用户名不能为空")
    assert auth.upsert_sso_user("x", role="root") == SUCCESS
    assert env.table._by_name("x")["role"] == "staff", "非法角色回落到 staff，这条判定没动"
    assert auth.upsert_sso_user("x", role="manager") == SUCCESS, "第二次同步仍走 UPDATE 支"
    assert auth.verify_password("x", "x") is False


def test_an_unreachable_database_still_answers_with_the_same_failure_shape(monkeypatch):
    """库真不通时仍是 `(False, "SSO 用户同步失败: <原文>")`，兜底那句一个字没改。"""
    connects = []

    def refuse():
        connects.append(1)
        raise BLIP

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "_db_ready", True)
    monkeypatch.setattr(auth, "_raw_conn", refuse)

    ok, message = auth.upsert_sso_user(SSO_USER, role="admin", department="ops")

    assert ok is False
    assert message.startswith("SSO 用户同步失败: ")
    assert "failed to resolve host" in message
    assert len(connects) == auth._CONNECT_ATTEMPTS, connects


def test_an_existing_user_never_remints_its_password(monkeypatch):
    """UPDATE 支形状不变：两句 SQL、一次 commit、摘要原样不动，本单没碰它。"""
    keep = bcrypt.hashpw(b"real-password", bcrypt.gensalt()).decode()
    env = _pg(monkeypatch, rows=[
        {"id": 4, "username": SSO_USER, "password_hash": keep, "role": "staff",
         "department": "", "created_at": "now"}
    ])

    assert auth.upsert_sso_user(SSO_USER, role="admin", department="ops") == SUCCESS

    assert env.table._by_name(SSO_USER)["password_hash"] == keep
    assert [stmt.split(")")[0] for stmt in env.table.statements] == [
        "select id from users where username = %s",
        "update users set role = %s, department = %s where username = %s",
    ], env.table.statements
    assert env.table.commits == 1
    assert not any(stmt.startswith("insert") for stmt in env.table.statements)
    assert auth.verify_password(SSO_USER, "real-password") is True, "已存在用户的口令不受影响"


def test_the_bootstrap_admin_seed_is_untouched(monkeypatch):
    """`_seed_bootstrap_admin` 仍是空表 seed 一枚 admin：本单没把占位口令的写法渗进它。"""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEPARTMENT", "it")
    boot = bcrypt.hashpw(b"bootstrap-pw", bcrypt.gensalt()).decode()
    monkeypatch.setenv("AUTH_PASSWORD_HASH", boot)
    table = _Table()

    auth._create_schema(table)

    assert len(table.rows) == 1, table.rows
    assert table.rows[0]["username"] == "admin" and table.rows[0]["role"] == "admin"
    assert table.rows[0]["password_hash"] == boot
    assert table.commits == 1, table.statements
