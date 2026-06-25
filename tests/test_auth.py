"""Day X: JWT 鉴权测试"""
import pytest
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


class TestPassword:
    def test_admin_login(self):
        assert verify_password("admin", "admin123") is True

    def test_wrong_password(self):
        assert verify_password("admin", "wrongpass") is False

    def test_nonexistent_user(self):
        assert verify_password("no_such_user", "anything") is False


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
