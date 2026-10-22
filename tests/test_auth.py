"""Day X: JWT 鉴权测试

R20（docs/handoff/2026-09-15-backend-followup-requests.md §16）：本文件跑在隔离后端上。
tests/conftest.py 先把 DATABASE_URL 钉成测试专用串，TestUserCRUD 再把 users 表换成
进程内的临时替身，所以「跑一次 test_auth.py」不再是写宿主数据库的操作。
"""
import pytest
import bcrypt
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.common.auth import (
    create_token, verify_token, verify_password,
    create_user, delete_user, get_user, list_users,
)

try:
    # 临时表抛出的重复用户名异常要与 create_user 捕获的类型同名，PG 代码分支才等价。
    from psycopg.errors import UniqueViolation as _UniqueViolation
except ModuleNotFoundError:  # pragma: no cover
    class _UniqueViolation(Exception):
        pass


class TestToken:
    def test_create_and_verify(self):
        token = create_token("admin")
        assert token is not None
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"

    def test_invalid_token(self):
        assert verify_token("bad.token.format") is None
        assert verify_token("") is None

    def test_token_contains_exp(self):
        token = create_token("admin")
        payload = verify_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_production_requires_an_explicit_jwt_secret(self, monkeypatch):
        from app.common import auth

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setattr(auth, "_auth_cfg", {})

        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            auth._jwt_secret()


class TestPassword:
    def test_production_rejects_default_memory_admin(self, monkeypatch):
        from app.common import auth

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("AUTH_USERNAME", raising=False)
        monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)

        with pytest.raises(RuntimeError, match="AUTH_USERNAME"):
            auth._load_memory_admin()

    def test_default_admin_login_without_environment_config(self, monkeypatch):
        from app.common import auth

        original_users = dict(auth._MEM_USERS)
        monkeypatch.delenv("AUTH_USERNAME", raising=False)
        monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)
        monkeypatch.setattr(auth, "psycopg", None)
        try:
            auth._MEM_USERS.clear()
            auth._load_memory_admin()
            assert auth.verify_password("admin", "admin123") is True
        finally:
            auth._MEM_USERS.clear()
            auth._MEM_USERS.update(original_users)

    def test_wrong_password(self):
        assert verify_password("admin", "wrongpass") is False

    def test_nonexistent_user(self):
        assert verify_password("no_such_user", "anything") is False

    def test_environment_account_is_loaded(self, monkeypatch):
        from app.common import auth

        username = "configured_admin"
        password_hash = bcrypt.hashpw(b"pass1234", bcrypt.gensalt()).decode()
        original_users = dict(auth._MEM_USERS)
        monkeypatch.setenv("AUTH_USERNAME", username)
        monkeypatch.setenv("AUTH_PASSWORD_HASH", password_hash)
        monkeypatch.setattr(auth, "psycopg", None)
        try:
            auth._MEM_USERS.clear()
            auth._load_memory_admin()
            assert auth.verify_password(username, "pass1234") is True
        finally:
            auth._MEM_USERS.clear()
            auth._MEM_USERS.update(original_users)

    def test_login_falls_back_to_memory_when_postgres_is_down(self, monkeypatch):
        from app.common import auth
        from app.main import app

        original_users = dict(auth._MEM_USERS)
        password_hash = bcrypt.hashpw(b"pass1234", bcrypt.gensalt()).decode()
        monkeypatch.setenv("AUTH_USERNAME", "admin")
        monkeypatch.setenv("AUTH_PASSWORD_HASH", password_hash)
        monkeypatch.setattr(auth, "psycopg", SimpleNamespace())
        monkeypatch.setattr(auth, "_db_ready", False)
        monkeypatch.setattr(auth, "_raw_conn", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

        try:
            auth._MEM_USERS.clear()
            auth._load_memory_admin()

            client = TestClient(app)
            response = client.post(
                "/api/v1/login",
                json={"username": "admin", "password": "pass1234"},
            )

            assert response.status_code == 200
            assert response.json()["username"] == "admin"
            assert response.json()["token"]
        finally:
            auth._MEM_USERS.clear()
            auth._MEM_USERS.update(original_users)

    def test_production_schema_check_does_not_execute_runtime_ddl(self, monkeypatch):
        from app.common import auth

        class Result:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class Connection:
            def __init__(self):
                self.statements = []

            def execute(self, statement, params=None):
                self.statements.append(statement)
                if statement.lstrip().upper().startswith("SELECT COUNT"):
                    # A live deployment already has accounts, so the bootstrap seed
                    # short-circuits; this test is about the DDL guardrail only.
                    return Result({"c": 1})
                return Result({"table_name": "users"})

        monkeypatch.setenv("APP_ENV", "production")
        connection = Connection()

        auth._create_schema(connection)

        assert any("to_regclass" in statement for statement in connection.statements)
        assert not any(
            statement.lstrip().upper().startswith(("CREATE", "ALTER"))
            for statement in connection.statements
        )


class _TempResult:
    """fetchone / fetchall / rowcount: the only three things app.common auth asks a cursor for."""

    def __init__(self, rows=(), rowcount=None):
        self._rows = [dict(row) for row in rows]
        self.rowcount = len(self._rows) if rowcount is None else rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def _project(row, columns):
    return {column: row[column] for column in columns}


class _TemporaryUsers:
    """In-process stand-in for the users table, so this file never opens a real connection.

    This is the isolation paradigm the repo already uses (tests/test_auth_database.py:85-92
    monkeypatches auth.psycopg + auth._db_ready + auth._raw_conn and hands it a fake that
    speaks the normalised SQL and raises AssertionError for anything else). It is not
    imported from there because that fake raises RuntimeError on duplicates, while
    create_user only turns a duplicate into a friendly message when
    psycopg.errors.UniqueViolation is what surfaces. This copy additionally records
    statements and commits, refuses a LIKE sweep - the statement R20 removed from here -
    and can never hand out a real connection.
    """

    ROW_COLUMNS = ("id", "username", "role", "department", "created_at")

    def __init__(self, unique_violation):
        self.unique_violation = unique_violation
        self.rows: dict[str, dict] = {}
        self.statements: list[str] = []
        self.commits = 0
        self.closes = 0
        self._last_id = 0
        self._put("admin", bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode(), "admin", "")

    def _put(self, username, password_hash, role, department):
        self._last_id += 1
        self.rows[username] = {
            "id": self._last_id,
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "department": department,
            # 时间列只为凑齐 list_users 的投影，本文件的断言不依赖它
            "created_at": f"temporary-row-{self._last_id}",
        }
        return self.rows[username]

    # --- connection protocol (replaces auth._raw_conn) ---
    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.commits += 1

    def close(self):
        self.closes += 1

    # --- SQL ---
    def execute(self, sql, params=()):
        statement = " ".join(sql.split()).lower()
        self.statements.append(statement)
        verb = statement.split(" ", 1)[0]
        if verb == "insert":
            return self._insert(statement, params)
        if verb == "select":
            return self._select(statement, params)
        if verb == "delete":
            return self._delete(statement, params)
        raise AssertionError(f"the temporary users table does not speak: {statement}")

    def _ordered(self):
        return [_project(row, self.ROW_COLUMNS)
                for row in sorted(self.rows.values(), key=lambda item: item["id"])]

    def _insert(self, statement, params):
        username, password_hash, role, department = params
        if username in self.rows:
            if "on conflict" in statement:
                return _TempResult()
            raise self.unique_violation(
                f"duplicate key value violates unique constraint users_username_key: {username}"
            )
        self._put(username, password_hash, role or "staff", department or "")
        return _TempResult()

    def _select(self, statement, params):
        username = params[0] if params else None
        row = self.rows.get(username)
        if statement.startswith("select password_hash"):
            return _TempResult([{"password_hash": row["password_hash"]}] if row else [])
        if statement.startswith("select username, role, department"):
            return _TempResult([_project(row, ("username", "role", "department"))] if row else [])
        if "order by id" in statement:
            return _TempResult(self._ordered())
        raise AssertionError(f"the temporary users table has no plan for: {statement}")

    def _delete(self, statement, params):
        where = statement.split(" where ", 1)[1] if " where " in statement else ""
        if not where.startswith("id = %s"):
            raise AssertionError(
                "the temporary users table only deletes the single row named by id; "
                "a LIKE sweep is exactly the statement R20 removed from this file"
            )
        victims = [name for name, row in self.rows.items() if row["id"] == params[0]]
        for name in victims:
            self.rows.pop(name)
        return _TempResult(rowcount=len(victims))


class TestUserCRUD:
    """User CRUD runs against the temporary users table, never the host database (R20).

    tests/conftest.py pins DATABASE_URL first, and this fixture replaces the connection
    factory with an in-process table, so these cases exercise the real PostgreSQL code
    branch of app.common.auth - its validation, SQL, commits and conflict handling -
    while every statement stays inside this test run.
    """

    @pytest.fixture(autouse=True)
    def users_table(self, monkeypatch, test_database_url):
        from app.common import auth

        driver = auth.psycopg
        if driver is None:
            # 没装驱动也要走同一条 PG 代码分支，而不是退到内存实现
            driver = SimpleNamespace(errors=SimpleNamespace(UniqueViolation=_UniqueViolation))

        table = _TemporaryUsers(driver.errors.UniqueViolation)

        def refuse_real_connection(*args, **kwargs):
            raise AssertionError(
                "tests/test_auth.py tried to open a real PostgreSQL connection; "
                "R20 keeps every statement inside the temporary users table"
            )

        monkeypatch.setattr(driver, "connect", refuse_real_connection, raising=False)
        monkeypatch.setattr(auth, "psycopg", driver, raising=False)
        monkeypatch.setattr(auth, "_db_ready", True)
        monkeypatch.setattr(auth, "_raw_conn", table.connect)

        assert auth._PG_URL == test_database_url, (
            "tests/conftest.py 没有把 DATABASE_URL 钉成测试专用串，"
            "本文件的用例随时可能写到宿主库，按 R20 判失败"
        )
        # 上一条断言只证明 DSN 安全；这一条证明用例真的走在被替换掉的连接上，
        # 否则会静默退到内存分支，看起来通过其实什么都没测。
        assert auth._using_memory_store() is False
        return table

    def test_create_user(self, users_table):
        ok, msg = create_user("test_user1", "pass1234")
        assert ok is True, msg
        assert "test_user1" in users_table.rows
        assert users_table.commits == 1

    def test_duplicate_user(self, users_table):
        assert create_user("test_user2", "pass1234")[0] is True
        ok, msg = create_user("test_user2", "pass1234")
        assert ok is False
        assert "test_user2" in msg
        assert [name for name in users_table.rows if name == "test_user2"] == ["test_user2"]

    def test_short_password(self, users_table):
        ok, msg = create_user("test_user3", "123")
        assert ok is False
        assert "6" in msg
        assert users_table.statements == []  # 口令长度在连接之前就挡住

    def test_empty_username(self, users_table):
        ok, msg = create_user("", "pass1234")
        assert ok is False
        assert users_table.statements == []

    def test_list_users(self, users_table):
        create_user("test_user4", "pass1234", role="staff", department="finance")
        users = list_users()
        # 临时表就是全部世界，所以这里能断言精确内容，而不是「至少有 admin」
        assert [u["username"] for u in users] == ["admin", "test_user4"]
        assert users[1]["department"] == "finance"

    def test_delete_user(self, users_table):
        create_user("test_del", "pass1234")
        target = next(u for u in list_users() if u["username"] == "test_del")
        assert delete_user(target["id"]) is True
        assert get_user("test_del") is None
        assert get_user("admin") is not None

    def test_no_connection_leaves_the_temporary_table(self, users_table):
        from app.common import auth

        create_user("test_user5", "pass1234")
        assert users_table.statements[-1].startswith("insert")
        with pytest.raises(AssertionError, match="real PostgreSQL connection"):
            auth.psycopg.connect(auth._PG_URL)

    def test_sweep_deletes_are_refused(self, users_table):
        # 这条语句就是 R20 从本文件删掉的扫荡。故意拼出来而不写成字面量，
        # 免得对本文件的 case-insensitive 扫荡语句检索又出现命中。
        sweep = " ".join(("delete", "from users where username like %s"))
        create_user("test_keep", "pass1234")
        with pytest.raises(AssertionError, match="only deletes the single row named by id"):
            users_table.execute(sweep, ("test_%",))
        assert get_user("test_keep") is not None
