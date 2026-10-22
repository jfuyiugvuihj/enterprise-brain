"""R248 J-4 —— 落进 PG 之后，越权判定一个字都不许变。

本单不许改 ``app/common/rbac.py`` 与 ``app/common/policy.py``，只许调用它们：
``clearance_for`` 依旧是密级档位的唯一来源（下面每个账号的 clearance 都由它现算），可见性
判定依旧只有 ``authorization_decision`` 一处。登记表换了地方，判据不该跟着换——
"同部门可读 / 跨部门不可读 / 密级不足不可读"三格在 JSON 时代是什么读数，在表时代必须还是
什么读数。

再加一格删：同部门的 manager 没有 ``resource:delete`` 就撤不掉别人的产物，而这一格今天走的
是**新的写路径**（``soft_delete`` 直接改表列），所以它既是权限钉也是落库钉。

🔴 R413（09-28，H13 结案＝甲，``auditor`` 补到 3 档）之后本文件改了一格读数、留了一格牙：
``peer-auditor`` 对同部门 internal 件从 ``clearance_insufficient`` 变成 ``department_scope_match``
—— 这就是裁定的实效（审计员读不到机密件就是假审计）；而「密级不足」那一族没被摘掉，它挪到
``peer-staff``（1 档 < 2）身上继续咬，两条腿一枚都不许少。

库是假的（``tests.test_r248_artifact_table_source._FakePostgres``，范式抄 R229），本文件一枚
哨兵再钉一遍：真连接一概开不出来。
"""
import pytest
from fastapi.testclient import TestClient

from app.storage.artifacts import ArtifactRegistry
from tests.test_r248_artifact_table_source import _FakePostgres

psycopg = pytest.importorskip("psycopg")

LIST_PATH = "/api/v1/artifacts"
ACCOUNTS = {
    "owner-manager": ("manager", "finance"),
    "peer-manager": ("manager", "finance"),
    "peer-auditor": ("auditor", "finance"),
    "peer-staff": ("staff", "finance"),
    "hr-manager": ("manager", "hr"),
    "finance-admin": ("admin", "finance"),
}


@pytest.fixture(autouse=True)
def no_real_driver_connect(monkeypatch):
    """哨兵：权限矩阵也不许顺手连宿主库（口径同 tests/test_r229_connect_retry.py:117-127）。"""

    def refuse(*args, **kwargs):
        raise AssertionError("R248 的权限矩阵件试图开一条真 PostgreSQL 连接")

    monkeypatch.setattr(psycopg, "connect", refuse, raising=False)


@pytest.fixture()
def users(monkeypatch):
    """账号表：字典里只写 role 与 department，clearance 一律由 ``rbac.clearance_for`` 现算。"""
    from app.common import auth

    def get_user(username):
        entry = ACCOUNTS.get(username)
        if entry is None:
            return None
        role, department = entry
        return {"id": username, "username": username, "role": role, "department": department}

    monkeypatch.setattr(auth, "get_user", get_user)
    return ACCOUNTS


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def _headers(username):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _principal(username, department=None, role=None):
    from app.agents.contracts import Principal

    account_role, account_department = ACCOUNTS.get(username, (role, department))
    return Principal.from_user(
        {
            "id": username,
            "username": username,
            "role": role or account_role,
            "department": department or account_department,
        }
    )


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """一枚指着假表的 registry，连同它写进去的行。"""
    from app.storage import artifacts as artifact_storage

    db = _FakePostgres()
    root = tmp_path / "static"
    root.mkdir(parents=True, exist_ok=True)
    registry = ArtifactRegistry(
        root, metadata_path=tmp_path / "sidecar.json", persistence=db.adapter()
    )
    monkeypatch.setattr(artifact_storage, "artifact_registry", registry)
    registry.db = db  # type: ignore[attr-defined]  # 只为把"表里那行原样"递到断言手里
    return registry


def _put(registry, filename, *, classification="internal", owner="owner-manager", **fields):
    path = registry.root / filename
    path.write_bytes(b"\x89PNG chart bytes")
    return registry.register(
        path,
        artifact_type=fields.pop("artifact_type", "chart"),
        principal=_principal(owner),
        classification=classification,
        **fields,
    )


def _decision(username, record, action):
    from app.common.policy import authorization_decision

    return authorization_decision(
        _principal(username),
        record.resource_scope,
        action=action,
        require_resource_scope=True,
    )


def test_the_scope_policy_reads_is_the_scope_the_table_holds(store):
    """owner 与部门必须真是表里的值：路由与登记处都不算第二遍。"""
    record = _put(store, "revenue.png")
    row = store.db.rows[record.artifact_id]

    assert row["owner_id"] == "owner-manager"
    assert row["status"] == "active"
    assert row["metadata"]["department_ids"] == ["finance"]
    assert row["metadata"]["classification"] == "internal"
    again = store.get(record.artifact_id)
    assert again.resource_scope.model_dump() == record.resource_scope.model_dump()
    assert again.resource_scope.owner_id == row["owner_id"]
    assert again.resource_scope.department_ids == row["metadata"]["department_ids"]


@pytest.mark.parametrize(
    ("username", "expected_allowed", "expected_reason"),
    [
        ("owner-manager", True, "owner_match"),
        ("peer-manager", True, "department_scope_match"),
        ("hr-manager", False, "department_scope_denied"),
        ("peer-auditor", True, "department_scope_match"),
        ("peer-staff", False, "clearance_insufficient"),
        ("finance-admin", True, "administrator_scope"),
    ],
)
def test_view_cells_match_the_standard_source(store, username, expected_allowed, expected_reason):
    """六格视图判据（R413 起 auditor 那一格翻成放行，密级不足那一格交给 staff）：码子逐字来自
    ``authorization_decision``，本单不发明新码。"""
    from app.common.rbac import ROLE_CLEARANCE, clearance_for

    record = _put(store, "revenue.png")
    decision = _decision(username, record, "resource:view")

    assert decision.allowed is expected_allowed, decision.model_dump()
    assert decision.reason_code == expected_reason, decision.model_dump()
    role = ACCOUNTS[username][0]
    # clearance 这一维仍由 rbac 现算：换库不换档位表
    assert _principal(username).clearance == clearance_for(role) == ROLE_CLEARANCE.get(role, 1)


def test_same_department_peer_opens_it_and_cross_department_peer_does_not(store, client, users):
    record = _put(store, "revenue.png")

    assert client.get(
        f"/api/v1/artifacts/{record.artifact_id}/content", headers=_headers("peer-manager")
    ).status_code == 200
    assert client.get(
        f"/api/v1/artifacts/{record.artifact_id}/download", headers=_headers("peer-manager")
    ).status_code == 200
    refused = client.get(
        f"/api/v1/artifacts/{record.artifact_id}/content", headers=_headers("hr-manager")
    )
    assert refused.status_code == 403
    assert refused.json()["detail"] == "department_scope_denied"


def test_insufficient_clearance_is_denied_on_both_legs(store, client, users):
    """同一条 internal 挡 staff（档位 1 < 2），一条 confidential 挡 manager（2 < 3）。

    R413 之前这枚钉的左边那条腿是 auditor（那时它静默拿 1 档）；auditor 补到 3 档以后这条腿
    不再有东西可挡，**换**到 staff 而不是删 —— 密级维度必须一直有枚角色被它挡在门外。
    """
    internal = _put(store, "internal.png")
    confidential = _put(store, "confidential.png", classification="confidential")

    for username, artifact in (("peer-staff", internal), ("peer-manager", confidential)):
        response = client.get(
            f"/api/v1/artifacts/{artifact.artifact_id}/content", headers=_headers(username)
        )
        assert response.status_code == 403, (username, artifact.classification)
        assert response.json()["detail"] == "clearance_insufficient"


def test_the_list_advertises_exactly_what_the_caller_may_open(store, client, users):
    mine = _put(store, "mine.png")
    secret = _put(store, "secret.png", classification="confidential")

    visible = client.get(LIST_PATH, headers=_headers("peer-manager")).json()
    hidden = client.get(LIST_PATH, headers=_headers("hr-manager")).json()
    unauthenticated = client.get(LIST_PATH)

    assert [item["artifact_id"] for item in visible["artifacts"]] == [mine.artifact_id]
    assert visible["total"] == 1 and visible["returned"] == 1
    assert secret.artifact_id not in [item["artifact_id"] for item in visible["artifacts"]]
    assert hidden["artifacts"] == [] and hidden["total"] == 0
    assert unauthenticated.status_code == 401


def test_a_same_department_manager_still_cannot_retire_a_peers_artifact(store, client, users):
    """撤单走的是新的表写路径：没有 ``resource:delete`` 就一枚字节都不许动。"""
    record = _put(store, "revenue.png")
    path = store.root / "revenue.png"

    refused = client.delete(
        f"/api/v1/artifacts/{record.artifact_id}", headers=_headers("peer-manager")
    )
    assert refused.status_code == 403
    assert refused.json()["detail"] == "permission_denied"
    assert store.get(record.artifact_id).status == "active"
    assert store.db.rows[record.artifact_id]["status"] == "active"
    assert path.is_file()

    allowed = client.delete(
        f"/api/v1/artifacts/{record.artifact_id}", headers=_headers("finance-admin")
    )
    assert allowed.status_code == 200
    assert store.get(record.artifact_id).status == "deleted"
    assert store.get_active(record.artifact_id) is None
    assert not path.exists()


def test_the_registry_itself_makes_no_access_decision(store):
    """登记处只回答"有没有这枚、还能不能交付"，谁准看是 policy 的事：第二条判据链不许长出来。"""
    record = _put(store, "revenue.png")

    assert store.get(record.artifact_id) is not None
    assert store.get_active(record.artifact_id) is not None
    assert [item.artifact_id for item in store.list_active(owner_id="somebody-else")] == []
    assert [item.artifact_id for item in store.list_active(artifact_type="chart")] == [
        record.artifact_id
    ]
