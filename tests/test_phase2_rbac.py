"""阶段 2（权限·密级模型）测试"""
import uuid
import pytest
from app.common import rbac


class TestClearance:
    def test_levels(self):
        assert rbac.clearance_for("staff") == 1
        assert rbac.clearance_for("manager") == 2
        assert rbac.clearance_for("admin") == 3
        assert rbac.clearance_for(None) == 1  # 缺省 staff

    def test_allowed_levels(self):
        assert rbac.allowed_levels("staff") == [1]
        assert rbac.allowed_levels("manager") == [1, 2]
        assert rbac.allowed_levels("admin") == [1, 2, 3]


def _pg_ok() -> bool:
    from app.common import auth
    try:
        auth._get_conn().close()
        return True
    except Exception:
        return False


class TestUserColumns:
    def test_create_user_with_role_and_get(self):
        if not _pg_ok():
            pytest.skip("Postgres 未运行，跳过用户列测试")
        from app.common import auth
        uname = f"t_{uuid.uuid4().hex[:6]}"
        try:
            ok, msg = auth.create_user(uname, "pass1234", role="manager", department="hr")
            assert ok is True, msg
            u = auth.get_user(uname)
            assert u is not None
            assert u["role"] == "manager"
            assert u["department"] == "hr"
        finally:
            try:
                conn = auth._get_conn()
                conn.execute("DELETE FROM users WHERE username = %s", (uname,))
                conn.commit()
                conn.close()
            except Exception:
                pass

    def test_invalid_role_rejected(self):
        from app.common import auth
        ok, msg = auth.create_user("t_badrole", "pass1234", role="superuser")
        assert ok is False
