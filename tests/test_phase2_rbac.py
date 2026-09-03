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


class TestDocVisible:
    def test_staff_public(self):
        assert rbac.doc_visible(1, "", "staff", "sales") is True

    def test_staff_blocked_internal(self):
        assert rbac.doc_visible(2, "", "staff", "sales") is False

    def test_manager_internal(self):
        assert rbac.doc_visible(2, "", "manager", "sales") is True

    def test_manager_blocked_secret(self):
        assert rbac.doc_visible(3, "", "manager", "sales") is False

    def test_department_scope(self):
        # 内部文档限定 hr 部门，sales 的 manager 不可见
        assert rbac.doc_visible(2, "hr", "manager", "sales") is False
        assert rbac.doc_visible(2, "hr", "manager", "hr") is True

    def test_admin_sees_all(self):
        assert rbac.doc_visible(3, "hr", "admin", "sales") is True


class TestFilters:
    def test_admin_no_where(self):
        assert rbac.build_where("admin", "x") is None

    def test_staff_where(self):
        w = rbac.build_where("staff", "sales")
        assert w is not None
        assert {"classification": {"$in": [1]}} in w["$and"]

    def test_pred_filters(self):
        docs = [
            {"classification": 1, "department": ""},
            {"classification": 3, "department": ""},
            {"classification": 2, "department": "hr"},
        ]
        pred = rbac.make_pred("staff", "sales")
        assert [d for d in docs if pred(d)] == [docs[0]]

        pred_m = rbac.make_pred("manager", "hr")
        assert [d for d in docs if pred_m(d)] == [docs[0], docs[2]]

        pred_a = rbac.make_pred("admin", "x")
        assert [d for d in docs if pred_a(d)] == docs


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
