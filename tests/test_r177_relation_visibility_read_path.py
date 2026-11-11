"""R177 - visibility on the knowledge-graph read path.

Reproduces the one A-class cell R163 handed back,
``intelligence_route.peer_cannot_see_anothers_triples``: a manager who shares the
author's department, and is not the author, read another author's triple *content*
out of ``GET /api/v1/knowledge-graph/relations`` - out of records that carry
``"visibility": "private"`` on the wire themselves.

Identity naming follows the R163 matrix verbatim (``r159-<kind>-<cell>``, departments
``r159-own`` / ``r159-fx``, content tokens ``R159-ENT-*`` / ``R159-TARGET-*`` /
``R159-SRC-INTEL-*``), so this file and that cell measure one thing. The matrix file is
deliberately not copied in: it is red on other cells, and a red test in the tree pins the
baseline for every other agent.

The rule this module holds the product to, in one line: a record's own ``visibility``
decides who may be **shown** it, and the department-and-clearance scope decides who may
**act on** a record they were pointed at. Collapsing those two questions is what made
either the leak or the review ledger impossible, and the two predicates in
``app/knowledge_graph/service.py`` are named after the split.

Everything runs offline and in-process. The graph is a store-less ``KnowledgeGraph()`` -
a development dictionary that never opens a file - except where a test names the
``tmp_path`` store it uses, so nothing here can write into ``data/**``.
"""
import asyncio
import json

import pytest

DEPT_OWN = "r159-own"
DEPT_FOREIGN = "r159-fx"
CELL_ID = "intelligence_route.peer_cannot_see_anothers_triples"

#: The three content tokens R163 listed as forbidden for that cell. A hit on any of them
#: means another author's triple text reached this caller's response.
FORBIDDEN = ("R159-ENT-", "R159-TARGET-", "R159-SRC-INTEL-")

_ROLE_OF = {
    "keeper": "manager",
    "peer": "manager",
    "xdept": "manager",
    "staff": "staff",
    "admin": "admin",
}


def _account(kind: str, suffix: str = "") -> dict:
    """One actor, built the way the R163 matrix builds it: role plus department, nothing else."""
    department = DEPT_FOREIGN if kind == "xdept" else DEPT_OWN
    username = "r159-" + kind + "-" + CELL_ID + suffix
    return {"id": "u-" + username, "username": username, "role": _ROLE_OF[kind], "department": department}


def _principal(kind: str, suffix: str = ""):
    from app.agents.contracts import Principal

    return Principal.from_user(_account(kind, suffix))


def _request(principal):
    state = type("State", (), {"principal": principal, "username": principal.username})()
    return type("Request", (), {"state": state})()


def _call(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture()
def graph(monkeypatch):
    """A fresh in-process ledger mounted on the route, restored by monkeypatch."""
    from app.api.v1 import intelligence
    from app.knowledge_graph.service import KnowledgeGraph

    monkeypatch.setattr(intelligence, "_graph", KnowledgeGraph())
    yield intelligence


def _write(intelligence, *, author_kind: str = "keeper", author_suffix: str = "-author", tag: str = "") -> dict:
    """One triple, written by a named author through the real route.

    The write has to actually land: otherwise "nobody can see it" is a green nobody
    earned, which is the check R163 built into its own driver.
    """
    record = _call(
        intelligence.add_relation(
            intelligence.RelationRequest(
                source_entity="R159-ENT-" + tag + CELL_ID,
                relation="规定",
                target="R159-TARGET-" + tag + CELL_ID,
                source="R159-SRC-INTEL-" + tag + CELL_ID + " 第 1 页",
            ),
            _request(_principal(author_kind, author_suffix)),
        )
    )
    assert record.get("relation_id"), "the ledger did not store the triple"
    return record


def _wire(payload) -> str:
    return json.dumps({"listing": payload}, ensure_ascii=False, default=str)


def _list(intelligence, kind: str, suffix: str = "") -> dict:
    return _call(intelligence.list_relations(None, None, _request(_principal(kind, suffix))))


def _assert_peer_sees_no_content(intelligence):
    """The judgement of the R163 cell, factored out so the reversal pins can reuse it."""
    listing = _list(intelligence, "peer")
    leaked = [token for token in FORBIDDEN if token in _wire(listing)]
    assert not leaked, "同部门非作者拿到了别人的三元组正文：" + str(leaked)
    assert listing["relations"] == []


def _assert_foreign_sees_no_content(intelligence):
    """The cross-department leg, same shape: nothing of another author's may come back."""
    listing = _list(intelligence, "xdept")
    leaked = [token for token in FORBIDDEN if token in _wire(listing)]
    assert not leaked, "跨部门读数人拿到了别人的三元组正文：" + str(leaked)
    assert listing["relations"] == []


# ============================================================ the cell R163 handed back


def test_same_department_peer_cannot_see_anothers_triples(graph):
    """R163 的 A 类格：同部门、同角色、只换主人，正文不该照发。"""
    record = _write(graph)
    assert record["visibility"] == "private", "这一格的前提：记录自己就写着 private"
    _assert_peer_sees_no_content(graph)


def test_the_route_on_the_wire_withholds_it_too(graph, monkeypatch):
    """Same judgement over a real HTTP round trip, not only over the coroutine.

    The A-class claim is about a disclosure a client can hit, so the pin is placed on the
    transport that serves it: ``GET /api/v1/knowledge-graph/relations`` through
    TestClient, with only the account lookup stubbed.
    """
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    peer = _account("peer")
    author = _account("keeper", "-author")
    accounts = {peer["username"]: peer, author["username"]: author}
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))

    _write(graph)
    client = TestClient(app)
    response = client.get(
        "/api/v1/knowledge-graph/relations",
        headers={"Authorization": "Bearer " + auth.create_token(peer["username"])},
    )

    assert response.status_code == 200
    assert response.json()["relations"] == []
    assert not [token for token in FORBIDDEN if token in response.text]

    as_author = client.get(
        "/api/v1/knowledge-graph/relations",
        headers={"Authorization": "Bearer " + auth.create_token(author["username"])},
    )
    assert [item["source_entity"] for item in as_author.json()["relations"]] == ["R159-ENT-" + CELL_ID]


# ================================================================= the controls for it


def test_author_still_sees_own_triples(graph):
    """正向对照（R163 的 keeper 格）：绿不是「谁都看不见」刷出来的。"""
    _write(graph)
    listing = _list(graph, "keeper", "-author")
    assert [item["source_entity"] for item in listing["relations"]] == ["R159-ENT-" + CELL_ID]


def test_cross_department_reader_sees_nothing(graph):
    """正向对照（R163 补的 xdept 格）：部门轴今天就在生效，本件不许把它改松。"""
    _write(graph)
    _assert_foreign_sees_no_content(graph)


def test_a_staff_colleague_in_the_department_sees_nothing_either(graph):
    """同部门不是可见性，与角色无关：staff 与 manager 在这一格上必须同命。"""
    _write(graph, author_kind="staff", author_suffix="-staff-author")
    assert _list(graph, "staff")["relations"] == []


def test_an_administrator_still_sees_the_triple(graph):
    """administrator 豁免面的既有读数：修完还得是「看得见」，不许顺手缩小。"""
    _write(graph)
    listing = _list(graph, "admin")
    assert [item["source_entity"] for item in listing["relations"]] == ["R159-ENT-" + CELL_ID]
    assert listing["relations"][0]["visibility"] == "private"


# =============================== the boundary the fix must not move: the review exit


def test_a_reviewer_in_the_department_still_reaches_anothers_relation(tmp_path):
    """核对腿不动：非作者的同部门复核人仍然读得到、核得了这条断言。

    This is the reason ``visibility`` filters the listing and not the scope test. The
    ledger refuses self-certification on purpose - an author may never verify their own
    claim - so a reviewer must be able to open somebody else's record, and
    tests/test_knowledge_graph.py together with
    tests/test_knowledge_graph_verification.py pin that reading today. Narrowing it would
    have closed the disclosure by breaking the only productive exit the graph has
    (promotion), which is not a trade this slice was asked to make.
    """
    from app.knowledge_graph.service import VERIFIED, KnowledgeGraph

    graph = KnowledgeGraph(store_path=tmp_path / "relations.json")
    author = _principal("keeper", "-author")
    record = graph.add_relation(
        "R159-ENT-review", "规定", "R159-TARGET-review", "R159-SRC-INTEL-review 第 1 页", principal=author
    )

    reviewer = _principal("peer")
    verified = graph.record_verification(
        record.relation_id, principal=reviewer, document="R159-SRC-INTEL-review", section="第 1 页"
    )

    assert verified.verification_state == VERIFIED
    assert verified.verified_by == reviewer.user_id
    # The listing still hides it from that same reviewer...
    assert graph.browse(principal=reviewer) == []
    # ...while the review exit still reads it back.
    assert graph.get(record.relation_id, principal=reviewer).relation_id == record.relation_id


def test_an_anonymous_caller_is_refused_before_any_listing(graph):
    """没有主体就没有读数：这条早于本件成立，本件不许它变成「按部门兜底」。"""
    from fastapi import HTTPException

    _write(graph)
    request_without_state = type("R", (), {"state": None})()

    with pytest.raises(HTTPException) as refused:
        _call(graph.list_relations(None, None, request_without_state))

    assert refused.value.status_code == 401
    assert refused.value.detail == "authentication_required"


# ======================================================== visibility as a live label


def test_every_label_the_ledger_writes_is_decided_by_the_read_path():
    """一个新默认值若落在读路径不认识的区间里，它会当场变成「随便看」。

    ``discloses_to`` only withholds labels it recognises, so the value the ledger
    actually writes has to be one of them. This pins that pairing rather than a literal:
    a future default of ``"shared"``/``""``/``None`` still fails here until somebody
    decides what it means.
    """
    from app.knowledge_graph.service import WITHHELD_VISIBILITIES, KnowledgeGraph

    written = KnowledgeGraph().add_relation(
        "a", "规定", "b", "doc.pdf 第 1 页", principal=_principal("keeper", "-author")
    )

    assert str(written.visibility).strip().lower() in WITHHELD_VISIBILITIES


def test_a_record_with_no_visibility_label_fails_closed(tmp_path):
    """一份没带标签的存量记录按最严的读法办：缺失不等于公开。"""
    from app.knowledge_graph.service import KnowledgeGraph

    store = tmp_path / "relations.json"
    store.write_text(
        json.dumps(
            {"knowledge_graph_relations": {"legacy-1": {
                "relation_id": "legacy-1", "source_entity": "R159-ENT-legacy", "relation": "规定",
                "target": "R159-TARGET-legacy", "source": "R159-SRC-INTEL-legacy 第 1 页",
                "owner_id": _principal("keeper", "-author").user_id,
                "department_ids": [DEPT_OWN], "classification": "2", "created_at": "",
            }}}
        ),
        encoding="utf-8",
    )

    graph = KnowledgeGraph(store_path=store)

    assert [item["relation_id"] for item in graph.browse(principal=_principal("peer"))] == []
    assert [item["relation_id"] for item in graph.browse(principal=_principal("keeper", "-author"))] == ["legacy-1"]


def test_a_label_somebody_set_on_purpose_is_honoured_the_other_way(tmp_path):
    """反方向也要真成立：标签不是「一律挡住」的别名，否则它仍然不算被读了。

    No write path sets this today - ``RelationRequest`` carries no such field and
    ``add_relation`` never passes one - so the state is built the only way it can be
    reached, in a store record. The point of the pin is the branch, not the value: a
    label outside the withheld set has to fall through to the department-and-clearance
    decision, which is what keeps ``visibility`` an input rather than a blanket.
    """
    from app.knowledge_graph.service import KnowledgeGraph

    author = _principal("keeper", "-author")
    store = tmp_path / "relations.json"
    store.write_text(
        json.dumps(
            {"knowledge_graph_relations": {"pub-1": {
                "relation_id": "pub-1", "source_entity": "R159-ENT-public", "relation": "规定",
                "target": "R159-TARGET-public", "source": "R159-SRC-INTEL-public 第 1 页",
                "owner_id": author.user_id, "visibility": "department",
                "department_ids": [DEPT_OWN], "classification": "2", "created_at": "",
            }}}
        ),
        encoding="utf-8",
    )

    graph = KnowledgeGraph(store_path=store)

    assert [item["relation_id"] for item in graph.browse(principal=_principal("peer"))] == ["pub-1"]
    assert graph.browse(principal=_principal("xdept")) == []


def test_the_label_rule_itself_refuses_an_absent_reader():
    """``discloses_to`` 对「没有读数人」必须回 False，而不是按部门兜底。

    The predicate is public, and a listing built without a principal must not fall
    through to the department branch on a ``None``. ``_listing`` already returns nothing
    when nobody is attached to the request; this pins the helper's own answer so the two
    cannot disagree about what "nobody asked" means.
    """
    from app.knowledge_graph.service import discloses_to

    author = _principal("keeper", "-author")

    assert discloses_to("private", author.user_id, None) is False
    assert discloses_to("", "", None) is False
    assert discloses_to("private", author.user_id, author) is True
    assert discloses_to("private", "u-somebody-else", _principal("admin")) is True


# ======================================================= 判据④：三把反证，常驻在这里


def test_reversal_one_removing_the_visibility_filter_reds_the_cell(graph, monkeypatch):
    """① 摘掉新加的可见性过滤 ⇒ 那一格必红。

    ``can_browse`` degenerated back into ``can_read`` is exactly the code before this
    fix, so the cell has to come back red. A pin that survives its own removal is not a
    pin.
    """
    from app.knowledge_graph.service import KnowledgeGraph

    _write(graph)
    _assert_peer_sees_no_content(graph)

    monkeypatch.setattr(KnowledgeGraph, "can_browse", staticmethod(KnowledgeGraph.can_read))

    with pytest.raises(AssertionError):
        _assert_peer_sees_no_content(graph)


def test_reversal_two_administrator_for_everyone_reds_an_existing_permission_test(monkeypatch):
    """② 把 ``administrator`` 豁免改成全员 ⇒ 既存权限件必红。

    The existing test named here is green before the mutation and red after it, which is
    what makes this a counter-proof instead of an accident: ``administrator_scope`` is
    the one rule in policy.py that walks past the department, so widening it to the
    population has to break something that was already watching the department.
    """
    from app.common import policy
    from tests import test_intelligence_route_authorization as existing

    run = _guarded(existing.test_knowledge_graph_relations_are_owner_scoped)
    run()  # green before the mutation, or the red below would prove nothing

    monkeypatch.setattr(policy, "_is_administrator", lambda principal, permissions: True)

    with pytest.raises(AssertionError):
        run()


def _guarded(test_function):
    """Wrap one existing route test so it can be re-run here with the graph restored.

    That file assigns ``intelligence._graph`` without putting it back, which is harmless
    when pytest runs it on its own and is not harmless when this module calls it on
    purpose, so the save and restore live here instead.
    """
    from app.api.v1 import intelligence

    def run():
        previous = intelligence._graph
        try:
            return test_function()
        finally:
            intelligence._graph = previous

    return run


def test_reversal_three_private_as_same_department_reds_both_legs(graph, monkeypatch):
    """③ 把 private 判成「同部门全员可见」⇒ 跨部门与跨归属两枚用例都必红。

    The mutation is the misreading the two legs exist to catch: a reader-side department
    test standing in for the record's own rule. It drops the resource scope with it -
    which is why the cross-department leg goes red as well as the peer leg, and why both
    assertions are made here instead of only the one the ticket names.
    """
    from app.knowledge_graph.service import KnowledgeGraph

    def mutated(record, principal):
        if principal is None:
            return False
        return bool(str(principal.department or "").strip())

    _write(graph)
    _assert_peer_sees_no_content(graph)
    _assert_foreign_sees_no_content(graph)

    monkeypatch.setattr(KnowledgeGraph, "can_browse", staticmethod(mutated))

    with pytest.raises(AssertionError):
        _assert_peer_sees_no_content(graph)
    with pytest.raises(AssertionError):
        _assert_foreign_sees_no_content(graph)