"""R229 判据 3 的钉子：加了超时与有界重试之后，鉴权语义一格不许变。

这里钉的是"对用户怎么说、用什么码说、什么情况下拒"：401/403 的产出条件、错误码、
用户可见文案、生产环境的 memory store 拒绝，全部按修前的原文钉住。重试只准发生在
"连接还没建立"那一格，所以它既不该把一枚 500 变成 401，也不该把一枚 401 变成 500。
"""
import pytest

from app.common import auth

psycopg = pytest.importorskip("psycopg")

BLIP = psycopg.OperationalError("failed to resolve host 'postgres' [Errno -3]")

# 修前的原文，一字不改（app/api/v1/auth.py 与前端都指着这些串）。
USER_MESSAGES = {
    "empty": "用户名和密码不能为空",
    "short": "密码至少 6 位",
    "bad_role": "非法角色: root",
    "duplicate": "用户 'dup' 已存在",
    "created": "创建成功",
    "sso_synced": "SSO 用户已同步",
}


@pytest.fixture
def dead_db(monkeypatch):
    """库彻底不在线：每一发建连都抛现网那枚解析错误，退避不许真睡。"""
    monkeypatch.setattr(auth, "_db_ready", True)
    monkeypatch.setattr(auth, "_PG_URL", "postgresql://u@postgres:5432/eb")
    monkeypatch.setattr(auth.time, "sleep", lambda seconds: None)
    calls = []

    def fake_raw_conn():
        calls.append(1)
        raise BLIP

    monkeypatch.setattr(auth, "_raw_conn", fake_raw_conn)
    return calls


@pytest.mark.parametrize("lookup", ["get_user", "verify_password", "list_users", "delete_user"])
def test_dead_db_still_surfaces_the_same_exception_type(dead_db, lookup):
    """重试耗尽后仍把 psycopg.OperationalError 原样抛出：middleware 那一格的形状不变。

    修前 = 第一发就抛；修后 = 最多 `_CONNECT_ATTEMPTS` 发之后抛同一枚。摘掉修复这格
    也过，所以它是"别把 500 悄悄改成 401/False"的护栏，不是反证钉。
    """
    fn = getattr(auth, lookup)
    args = {"get_user": ("u1",), "verify_password": ("u1", "pw"),
            "list_users": (), "delete_user": (1,)}[lookup]

    with pytest.raises(psycopg.OperationalError):
        fn(*args)

    assert len(dead_db) == auth._CONNECT_ATTEMPTS, dead_db


def test_create_user_validation_messages_are_unchanged(dead_db, monkeypatch):
    """校验层的文案与顺序不经过建连，重试不许把它们挪位。"""
    assert auth.create_user("", "") == (False, USER_MESSAGES["empty"])
    assert auth.create_user("u1", "123") == (False, USER_MESSAGES["short"])
    assert auth.create_user("u1", "pass1234", role="root") == (False, USER_MESSAGES["bad_role"])
    assert len(dead_db) == 0, "参数校验阶段一发连接都不该开"


def test_sso_failure_message_keeps_its_shape(dead_db, monkeypatch):
    """库不在线时 SSO 仍返回 (False, "SSO 用户同步失败: ...")，兜底那句不许被改成抛异常。"""
    ok, message = auth.upsert_sso_user("u1", role="admin", department="ops")

    assert ok is False
    assert message.startswith("SSO 用户同步失败: ")
    assert "failed to resolve host" in message
    assert len(dead_db) == auth._CONNECT_ATTEMPTS, dead_db


def test_production_memory_store_refusal_is_untouched(monkeypatch):
    """生产 + 内存用户表 = 拒绝鉴权（401 的产地之一），这条判定与本单无关，钉住它没被碰。"""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "psycopg", None)
    monkeypatch.setattr(auth, "_db_ready", False)
    connects = []
    monkeypatch.setattr(auth, "_raw_conn", lambda: connects.append(1))
    monkeypatch.setattr(auth, "_connect_for_request", lambda operation: connects.append(1))

    assert auth.get_user("admin") is None
    assert auth.verify_password("admin", "admin123") is False
    assert auth.list_users() == []
    assert auth.create_user("newone", "pass1234") == (False, "production_user_store_unavailable")
    assert auth.upsert_sso_user("newone") == (False, "production_user_store_unavailable")
    assert auth.delete_user(1) is False
    assert connects == [], "拒绝路径上一发连接都不该开"


def test_user_storage_state_wording_is_unchanged(monkeypatch):
    """`user_storage_state` 的 detail 文案是运维读数，本单一字未动。"""
    monkeypatch.setattr(auth, "psycopg", None)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setenv("APP_ENV", "development")

    state = auth.user_storage_state()

    assert state["storage_mode"] == "memory"
    assert state["durable"] is False
    assert state["protection"] == "none"
    assert state["detail"] == "psycopg driver is unavailable"