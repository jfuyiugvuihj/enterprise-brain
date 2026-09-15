"""Day X: JWT 鉴权测试"""
import pytest
import bcrypt
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.common.auth import (
    create_token, verify_token, verify_password,
    create_user, delete_user, list_users,
)


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


class TestUserCRUD:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        """测试后清理"""
        yield
        # 删除测试用户
        try:
            from app.common.auth import _get_conn
            conn = _get_conn()
            conn.execute("DELETE FROM users WHERE username LIKE 'test_%'")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def test_create_user(self):
        ok, msg = create_user("test_user1", "pass1234")
        assert ok is True, msg

    def test_duplicate_user(self):
        create_user("test_user2", "pass1234")
        ok, msg = create_user("test_user2", "pass1234")
        assert ok is False

    def test_short_password(self):
        ok, msg = create_user("test_user3", "123")
        assert ok is False
        assert "6" in msg

    def test_empty_username(self):
        ok, msg = create_user("", "pass1234")
        assert ok is False

    def test_list_users(self):
        users = list_users()
        assert isinstance(users, list)
        assert len(users) >= 1  # 至少默认 admin 存在
        assert any(u["username"] == "admin" for u in users)

    def test_delete_user(self):
        create_user("test_del", "pass1234")
        # delete_user 需要知道 user_id
        from app.common.auth import _get_conn
        conn = _get_conn()
        row = conn.execute("SELECT id FROM users WHERE username = %s", ("test_del",)).fetchone()
        conn.close()
        if row:
            assert delete_user(row["id"]) is True
