"""图谱核对记录（R15-b 的前半段）：谁能核、核完留下什么、生产只读时拒什么。

这里全部离线跑：一个 tmp_path 下的 JSON store 就是一个可写部署，另一份用例钉住的是
`KNOWLEDGE_GRAPH_STORE_PATH` 缺失时的生产只读口径——与 `GET /api/v1/health/details` 的
`storage.subsystems.knowledge_graph` 同一套判断，不依赖真机 PostgreSQL。
"""
import json

import pytest

from app.agents.contracts import Principal
from app.common.monitoring import ProductionReadOnlyProtection
from app.knowledge_graph import service
from app.knowledge_graph.service import (
    REJECTED,
    RELATION_STATUSES,
    UNVERIFIED,
    VERIFIED,
    KnowledgeGraph,
)

DOC = "\u5dee\u65c5\u8d39\u62a5\u9500\u5236\u5ea6.pdf"
SECTION = "\u7b2c3\u9875 \u4f4f\u5bbf\u8d39\u6807\u51c6"


def _principal(user_id: str, *, department: str = "\u7814\u53d1\u90e8", clearance: int = 1, approve: bool = False):
    permissions = ["resource:view", "resource:upload"]
    if approve:
        permissions.append("resource:approve")
    return Principal(
        user_id=user_id,
        username=user_id,
        roles=["manager" if approve else "staff"],
        permissions=permissions,
        department=department,
        department_ids=[department],
        clearance=clearance,
    )


def _relation(graph: KnowledgeGraph, *, author: str = "u-1") -> str:
    record = graph.add_relation(
        "\u5dee\u65c5\u5236\u5ea6",
        "\u89c4\u5b9a",
        "\u4f4f\u5bbf\u4e0a\u9650",
        f"{DOC} {SECTION}",
        principal=_principal(author),
    )
    return record.relation_id


# ------------------------------------------------------------------- 状态域


def test_the_status_and_verification_domains_are_closed_enumerations():
    assert RELATION_STATUSES == ("candidate", "confirmed", "promoted", "rejected")
    assert (UNVERIFIED, VERIFIED, REJECTED) == ("unverified", "verified", "rejected")
    graph = KnowledgeGraph()
    relation_id = _relation(graph)
    record = graph.get(relation_id, principal=_principal("u-1"))
    assert record is not None
    assert (record.status, record.verification_state) == ("candidate", UNVERIFIED)
    assert record.verified is False


def test_an_unknown_or_unreadable_relation_reads_as_nothing():
    graph = KnowledgeGraph()
    relation_id = _relation(graph)

    assert graph.get(relation_id) is None
    assert graph.get(relation_id, principal=None) is None
    assert graph.get(relation_id, principal=_principal("u-2", department="\u5e02\u573a\u90e8")) is None
    assert graph.get("no-such-id", principal=_principal("u-1")) is None


# ------------------------------------------------------------------- 核对


def test_a_reviewer_records_the_document_and_section_behind_a_relation(tmp_path):
    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")
    relation_id = _relation(graph)

    record = graph.record_verification(
        relation_id,
        principal=_principal("u-9", approve=True),
        document=DOC,
        section=SECTION,
        note="\u4e0e\u5236\u5ea6\u9644\u4ef6\u4e00\u81f4",
    )

    assert record.verification_state == VERIFIED
    assert record.verified is True
    assert record.verified_document == DOC and record.verified_section == SECTION
    assert record.verified_by == "u-9" and record.verified_at
    assert record.verification_note == "\u4e0e\u5236\u5ea6\u9644\u4ef6\u4e00\u81f4"
    # A certification is not a promotion: the ledger says "checked", nothing more.
    assert record.status == "confirmed"
    assert record.promoted_definition_id == ""
    assert record.version == 2
    payload = graph.query("\u5dee\u65c5\u5236\u5ea6", principal=_principal("u-9", approve=True))[0]
    assert payload["verification_state"] == VERIFIED
    assert payload["verified_document"] == DOC
    assert payload["promoted_definition_id"] == ""


def test_the_author_may_never_certify_their_own_relation(tmp_path):
    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")
    relation_id = _relation(graph)
    author_with_approval = _principal("u-1", approve=True)

    with pytest.raises(PermissionError, match="self_verification_refused"):
        graph.record_verification(relation_id, principal=author_with_approval, document=DOC, section=SECTION)

    assert graph.get(relation_id, principal=_principal("u-1")).verification_state == UNVERIFIED
    assert graph.get(relation_id, principal=_principal("u-1")).version == 1


@pytest.mark.parametrize(
    "principal, code",
    [
        (None, "authentication_required"),
        (_principal("u-2", department="\u5e02\u573a\u90e8", approve=True), "permission_denied"),
        (_principal("u-9", approve=False), "approval_permission_required"),
    ],
)
def test_who_may_not_verify_a_relation(tmp_path, principal, code):
    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")
    relation_id = _relation(graph)

    with pytest.raises(PermissionError, match=code):
        graph.record_verification(relation_id, principal=principal, document=DOC, section=SECTION)

    assert graph.get(relation_id, principal=_principal("u-1")).verification_state == UNVERIFIED


def test_verified_without_a_locator_is_refused_and_rejection_is_recorded(tmp_path):
    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")
    reviewer = _principal("u-9", approve=True)

    missing = _relation(graph, author="u-1")
    with pytest.raises(ValueError, match="relation_verification_evidence_required"):
        graph.record_verification(missing, principal=reviewer, document=DOC, section="  ")
    with pytest.raises(ValueError, match="relation_verification_outcome"):
        graph.record_verification(missing, principal=reviewer, outcome="maybe")

    rejected = graph.record_verification(
        missing, principal=reviewer, outcome=REJECTED, note="\u5f15\u7528\u7684\u662f\u5e9f\u6b62\u7248\u5236\u5ea6"
    )
    assert rejected.verification_state == REJECTED
    assert rejected.status == "rejected"
    assert rejected.verified is False
    # A refusal says who refused and when, and never fills in the "certified against" pair.
    assert rejected.verified_by == "u-9" and rejected.verified_at
    assert rejected.verified_document == "" and rejected.verified_section == ""

    with pytest.raises(ValueError, match="relation_not_verified"):
        graph.reviewable(missing, principal=reviewer)


def test_a_relation_nobody_has_recorded_cannot_be_verified(tmp_path):
    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")

    with pytest.raises(LookupError, match="relation_not_found"):
        graph.record_verification("nope", principal=_principal("u-9", approve=True), document=DOC, section=SECTION)
    with pytest.raises(LookupError, match="relation_not_found"):
        graph.record_promotion("nope", principal=_principal("u-9", approve=True), definition_id="md:x")


# --------------------------------------------------------------- 跨进程可见


def test_the_review_survives_a_restart_and_stays_out_of_the_way_of_other_scopes(tmp_path):
    path = tmp_path / "relations.json"
    first = KnowledgeGraph(store_path=path)
    relation_id = _relation(first)
    first.record_verification(relation_id, principal=_principal("u-9", approve=True), document=DOC, section=SECTION)

    restarted = KnowledgeGraph(store_path=path)
    record = restarted.get(relation_id, principal=_principal("u-9", approve=True))
    assert record is not None
    assert (record.verification_state, record.verified_by, record.version) == (VERIFIED, "u-9", 2)
    assert record.promoted_definition_id == ""

    record = restarted.record_promotion(
        relation_id, principal=_principal("u-9", approve=True), definition_id="md:system:expense.x:v1"
    )
    assert (record.status, record.promoted_definition_id) == ("promoted", "md:system:expense.x:v1")
    assert KnowledgeGraph(store_path=path).get(relation_id, principal=_principal("u-1")).status == "promoted"


def test_a_record_written_before_the_review_columns_existed_still_loads(tmp_path):
    """旧 store 里没有这些键：默认值必须就是"从未核对"，而不是崩掉或自称已核对。"""
    path = tmp_path / "relations.json"
    legacy = {
        "relation_id": "legacy-1",
        "source_entity": "\u5236\u5ea6",
        "relation": "\u89c4\u5b9a",
        "target": "\u4e0a\u9650",
        "source": "\u5236\u5ea6.pdf \u7b2c1\u9875",
        "owner_id": "u-1",
        "department_ids": ["\u7814\u53d1\u90e8"],
        "classification": "1",
        "visibility": "private",
        "status": "candidate",
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    from app.storage.persistence import JsonPersistenceAdapter

    JsonPersistenceAdapter(path).upsert(service._STORE_COLLECTION, "legacy-1", legacy)

    graph = KnowledgeGraph(store_path=path)
    record = graph.get("legacy-1", principal=_principal("u-1"))
    assert record.verification_state == UNVERIFIED
    assert record.verified is False
    assert record.promoted_definition_id == ""
    with pytest.raises(ValueError, match="relation_not_verified"):
        graph.reviewable("legacy-1", principal=_principal("u-9", approve=True))
    # 旧记录被读进来之后仍然可以正常写回，字段补齐。
    graph.record_verification("legacy-1", principal=_principal("u-9", approve=True), document=DOC, section=SECTION)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored[service._STORE_COLLECTION]["legacy-1"]["verification_state"] == VERIFIED


# ----------------------------------------------------------------- 生产只读


def test_production_without_a_store_path_reports_read_only_and_refuses_every_write(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("KNOWLEDGE_GRAPH_STORE_PATH", raising=False)

    state = service.knowledge_graph_storage_state()
    assert state["storage_mode"] == "unavailable"
    assert state["protection"] == "read_only"
    assert state["detail"] == "KNOWLEDGE_GRAPH_STORE_PATH is not configured; relation writes are refused"
    assert state["durable"] is False

    graph = KnowledgeGraph()
    assert graph.storage_state() == state
    with pytest.raises(ProductionReadOnlyProtection, match="knowledge_graph_read_only"):
        graph.add_relation("a", "\u89c4\u5b9a", "b", f"{DOC} {SECTION}", principal=_principal("u-1"))


def test_the_review_writes_go_through_the_same_read_only_guard(monkeypatch, tmp_path):
    """核对与晋升都必须落在同一个写入门禁上，否则只读生产会被 Side API 绕过。"""
    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")
    relation_id = _relation(graph)
    graph.record_verification(relation_id, principal=_principal("u-9", approve=True), document=DOC, section=SECTION)
    before = graph.get(relation_id, principal=_principal("u-9", approve=True))

    def refuse():
        raise ProductionReadOnlyProtection("knowledge_graph_read_only: guard reached")

    monkeypatch.setattr(graph, "_reject_in_memory_write", refuse)
    with pytest.raises(ProductionReadOnlyProtection, match="guard reached"):
        graph.record_verification(relation_id, principal=_principal("u-9", approve=True), document=DOC, section="x")
    with pytest.raises(ProductionReadOnlyProtection, match="guard reached"):
        graph.record_promotion(relation_id, principal=_principal("u-9", approve=True), definition_id="md:y")

    after = graph.get(relation_id, principal=_principal("u-9", approve=True))
    assert (after.version, after.verification_note) == (before.version, before.verification_note)
