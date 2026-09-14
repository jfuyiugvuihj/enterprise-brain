import pytest

from app.agents.contracts import Principal
from app.knowledge_graph.service import KnowledgeGraph


def _principal(user_id="u-1", department="研发部", clearance=1):
    return Principal(
        user_id=user_id,
        username=user_id,
        roles=["staff"],
        permissions=["resource:view", "resource:upload"],
        department=department,
        clearance=clearance,
    )


def test_knowledge_graph_keeps_candidate_relation_with_source():
    graph = KnowledgeGraph()

    record = graph.add_relation("差旅制度", "规定", "住宿上限", "差旅费报销制度.pdf 第3页", principal=_principal())

    assert record.status == "candidate"
    assert record.source == "差旅费报销制度.pdf 第3页"
    assert record.owner_id == "u-1"
    assert record.department_ids == ["研发部"]
    assert record.version == 1


def test_knowledge_graph_requires_an_owner_and_a_source():
    graph = KnowledgeGraph()

    with pytest.raises(PermissionError):
        graph.add_relation("a", "b", "c", "doc.pdf", principal=_principal(user_id=""))

    with pytest.raises(ValueError):
        graph.add_relation("a", "b", "c", "   ", principal=_principal())


def test_knowledge_graph_can_confirm_relation():
    graph = KnowledgeGraph()
    author = _principal()
    record = graph.add_relation("制度", "规定", "上限", "制度.pdf 第1页", principal=author)

    assert graph.confirm(record.relation_id, principal=author) is True
    assert graph.query("制度", principal=author)[0]["status"] == "confirmed"
    assert graph.query("制度", principal=author)[0]["version"] == 2


def test_knowledge_graph_hides_relations_from_other_departments_and_anonymous_callers():
    graph = KnowledgeGraph()
    author = _principal()
    graph.add_relation("制度", "规定", "上限", "制度.pdf 第1页", principal=author)

    assert graph.query("制度") == []
    assert graph.query("制度", principal=_principal(user_id="u-2", department="市场部")) == []
    stranger = _principal(user_id="u-3", department="研发部")
    assert [item["relation_id"] for item in graph.query("制度", principal=stranger)] == [
        next(iter(graph._relations))
    ]
    assert graph.confirm(next(iter(graph._relations)), principal=_principal(user_id="u-4", department="市场部")) is False