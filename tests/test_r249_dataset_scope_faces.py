"""R249 判据 J-5 —— 落到表里之后，越权一格都不许回退。

三格新覆盖：同部门可读、跨部门不可读、密级不足不可读。判定仍然只从
``app/common/policy.py::authorization_decision`` 拿（rbac / policy 本单一字未改），
资源侧的口径仍然只有 ``DatasetRecord.resource_scope`` 这一处；本件钉的是"版本链 + 落表"
这两件事没有把它俩改掉。

第四格钉版本寻址：``scope_for_version`` 交回的是**父 dataset 行**的口径换了个 version_id。
``dataset_versions`` 没有密级列也没有部门列（加列是迁移，不归本单），所以一个版本永远不许
成为比它所属数据集更宽的资源；查不到的版本交回 None，policy 把 None 读成
``resource_scope_missing`` —— 缺行是关起来，不是放行到当前版本。
"""
from __future__ import annotations

import pytest

from app.agents.contracts import Principal
from app.common.permissions import ACTION_ANALYZE, ACTION_VIEW
from app.common.policy import authorization_decision
from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

DEPT = "r249-finance"
OTHER_DEPT = "r249-hr"


def _user(username: str, department: str, role: str = "manager") -> dict:
    return {"id": f"u-{username}", "username": username, "role": role, "department": department}


def _principal(username: str, department: str = DEPT, role: str = "manager") -> Principal:
    return Principal.from_user(_user(username, department, role))


@pytest.fixture()
def registry(tmp_path):
    return DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())


def _registered(registry, tmp_path, filename: str, **fields):
    path = tmp_path / filename
    path.write_text("department,revenue\n%s,100\n" % DEPT, encoding="utf-8")
    return registry.register(path, principal=_principal("owner"), filename=filename, **fields)


# ==================================================================== 三格权限矩阵


@pytest.mark.parametrize(
    "reader, department, classification, expected_allowed, expected_reason",
    [
        ("peer", DEPT, "internal", True, "department_scope_match"),
        ("foreign", OTHER_DEPT, "internal", False, "department_scope_denied"),
        ("manager", DEPT, "confidential", False, "clearance_insufficient"),
        ("staff", DEPT, "internal", False, "clearance_insufficient"),
    ],
    ids=["same-department-reads", "cross-department-refused", "clearance-too-low", "staff-below-internal"],
)
def test_the_three_scope_faces_survive_the_move_to_tables(
    registry, tmp_path, reader, department, classification, expected_allowed, expected_reason
) -> None:
    """同部门可读 / 跨部门不可读 / 密级不足不可读：读数来自表里的行，判定来自 policy。"""
    record = _registered(registry, tmp_path, "sales.csv", classification=classification)
    role = "staff" if reader == "staff" else "manager"
    viewer = _principal(reader, department, role)

    decision = authorization_decision(
        viewer, record.resource_scope, action=ACTION_VIEW, require_resource_scope=True
    )

    assert decision.allowed is expected_allowed, decision.model_dump()
    assert decision.reason_code == expected_reason, decision.model_dump()


def test_the_owner_reads_their_own_row_and_a_foreign_delete_is_not_a_scope_question(
    registry, tmp_path
) -> None:
    """本人按 owner_match 读；跨部门的删除走 permission_denied —— 两个码不许互相顶替。"""
    from app.common.permissions import ACTION_DELETE

    record = _registered(registry, tmp_path, "sales.csv")

    assert (
        authorization_decision(
            _principal("owner"), record.resource_scope, action=ACTION_VIEW, require_resource_scope=True
        ).reason_code
        == "owner_match"
    )
    foreign_delete = authorization_decision(
        _principal("foreign", OTHER_DEPT), record.resource_scope, action=ACTION_DELETE, require_resource_scope=True
    )
    assert foreign_delete.allowed is False
    assert foreign_delete.reason_code == "permission_denied"


def test_an_anonymous_or_unprivileged_subject_is_refused_before_the_table_is_read(
    registry, tmp_path
) -> None:
    """表读到了不等于人可读：没有 principal、或角色里没有 view，一律 False。"""
    record = _registered(registry, tmp_path, "sales.csv")

    assert (
        authorization_decision(None, record.resource_scope, action=ACTION_VIEW).reason_code
        == "authentication_required"
    )
    no_view = _principal("viewer").model_copy(update={"permissions": [ACTION_ANALYZE]})
    assert (
        authorization_decision(
            no_view, record.resource_scope, action=ACTION_VIEW, require_resource_scope=True
        ).reason_code
        == "permission_denied"
    )


# ================================================================== 版本链上的口径


def test_every_version_carries_the_scope_of_the_dataset_it_belongs_to(registry, tmp_path) -> None:
    """v1/v2/v3 各自可寻址，但授权口径同源：父行的部门、密级、所有者。"""
    for index in range(3):
        path = tmp_path / "sales.csv"
        path.write_text(f"department,revenue\n{DEPT},{index}\n", encoding="utf-8")
        registry.register(path, principal=_principal("owner"), filename="sales.csv")
    record = registry.get_active_by_filename("sales.csv")
    foreign = _principal("foreign", OTHER_DEPT)

    scopes = [registry.scope_for_version(version) for version in registry.versions(record.dataset_id)]

    assert [scope.version_id for scope in scopes] == [
        f"{record.dataset_id}:v1",
        f"{record.dataset_id}:v2",
        f"{record.dataset_id}:v3",
    ]
    for scope in scopes:
        assert scope.resource_id == record.dataset_id
        assert scope.department_ids == record.department_ids
        assert scope.classification == record.classification
        assert (
            authorization_decision(
                foreign, scope, action=ACTION_VIEW, require_resource_scope=True
            ).allowed
            is False
        )
    assert (
        authorization_decision(
            _principal("peer", DEPT), scopes[0], action=ACTION_VIEW, require_resource_scope=True
        ).allowed
        is True
    )


def test_an_unknown_version_addresses_no_scope_at_all(registry, tmp_path) -> None:
    """查不到的版本交回 None：policy 读成 resource_scope_missing，而不是回落到当前版本。"""
    record = _registered(registry, tmp_path, "sales.csv")

    assert registry.scope_for_version(f"{record.dataset_id}:v9") is None
    decision = authorization_decision(
        _principal("foreign", OTHER_DEPT),
        registry.scope_for_version(f"{record.dataset_id}:v9"),
        action=ACTION_VIEW,
        require_resource_scope=True,
    )
    assert decision.allowed is False
    assert decision.reason_code == "resource_scope_missing"


def test_a_retired_dataset_keeps_its_status_in_the_scope_and_its_name_free(
    registry, tmp_path
) -> None:
    """退役不回退权限读数：行还在、状态是 deleted、名字已让给下一条链。"""
    record = _registered(registry, tmp_path, "sales.csv")
    assert registry.soft_delete(record.dataset_id) is True

    retired = registry.get(record.dataset_id)

    assert retired.status == "deleted"
    assert retired.resource_scope.status == "deleted"
    assert registry.list() == []
    assert [item.dataset_id for item in registry.list(include_retired=True)] == [record.dataset_id]
    assert registry.get_active_by_filename("sales.csv") is None
    assert registry.scope_for_version(record.version_id).status == "deleted"


def test_a_scope_is_built_from_the_row_not_from_the_caller_s_assumptions(
    registry, tmp_path
) -> None:
    """resource_scope 现义：owner / departments / classification / visibility / version / status 全来自表里的当前行。"""
    record = _registered(
        registry, tmp_path, "sales.csv", classification="confidential", visibility="department"
    )

    scope = record.resource_scope

    assert scope.resource_type == "dataset"
    assert scope.resource_id == record.dataset_id
    assert scope.owner_id == "u-owner"
    assert scope.department_ids == [DEPT]
    assert scope.classification == "confidential"
    assert scope.visibility == "department"
    assert scope.version_id == record.current_version_id
    assert scope.status == "active"

def test_a_lower_classification_on_a_later_registration_widens_the_whole_chain(
    registry, tmp_path
) -> None:
    """钉住一笔债：版本继承父行口径，所以把密级往下改会一并放宽历史版本。

    ``dataset_versions`` 没有 classification / department 列（加列属迁移，本单不许碰
    ``migrations/``），历史版本的内容与哈希都还在表里，但判定口径只有父行那一份。这条钉的是
    "今天确实如此"，不是"这样对"：要按版本各自的密级判，得等一枚给 dataset_versions 加列的迁移。
    """
    path = tmp_path / "sales.csv"
    path.write_text(f"department,revenue\n{DEPT},1\n", encoding="utf-8")
    confidential = registry.register(
        path, principal=_principal("owner"), classification="confidential"
    )
    path.write_text(f"department,revenue\n{DEPT},2\n", encoding="utf-8")
    registry.register(path, principal=_principal("owner"), filename="sales.csv", classification="public")
    staff_peer = _principal("staff-peer", DEPT, "staff")

    assert registry.get(confidential.dataset_id).classification == "public"
    assert (
        registry.get_version(confidential.dataset_id, 1).content_sha256
        == confidential.content_sha256
    )
    assert (
        authorization_decision(
            staff_peer,
            registry.scope_for_version(f"{confidential.dataset_id}:v1"),
            action=ACTION_VIEW,
            require_resource_scope=True,
        ).allowed
        is True
    )
