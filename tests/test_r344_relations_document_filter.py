r"""R344 判据 ①③④⑤：GET /knowledge-graph/relations 的「任一端命中」筛法。

病根：员工读一篇制度时，那一篇**只作为客体**登记过的关系（《差旅管理办法》 --依据-->
《员工手册》，手册在 ``target`` 位）在服务端那道只筛主体的枚举里永远筛不到，于是前端只能
不带参数全量拉、再在浏览器里筛（frontend/src/components/DocumentPreviewModal.vue:48-50 把
这件事写在了自己的注释里）。本件钉的就是新增的 ``document`` 腿，以及它**不许**动的那些东西。

四把反证的常驻形状（工单判据 ⑦）：
  刀A -> ``test_a_document_registered_only_in_the_target_slot_is_found_by_the_new_leg``：
         同一行，旧腿筛不到、新腿筛得到，两半各一条断言，本单没做空气。
  刀B -> ``test_a_registration_spelling_variant_answers_as_the_same_document``：把归一摘成
         ``==`` 原样比较就红（大小写、全角空格、BOM、首尾空白各占一行）。
  刀C -> ``test_a_name_one_character_off_does_not_answer``：把归一换成 includes / 前缀就红。
  刀D -> ``test_the_document_filter_never_releases_a_private_row`` 与
         ``test_the_permission_leg_is_asked_about_the_rows_the_filter_matched``：前者点名那枚
         私有记录的 relation_id（不是只断言条数），后者断言权限判定真的在这一行上发生过——
         「筛过实体就直接 return」那种写法在第二格上当场红。

全部离线、进程内：图是 ``KnowledgeGraph()`` 开发字典，写口不碰 ``data/**``；上线那一段走
TestClient，只桩掉账号查询，与 tests/test_r177_relation_visibility_read_path.py 同法。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

from app.agents.contracts import Principal
from app.knowledge_graph.service import KnowledgeGraph, Relation

DEPT = "r344-ops"
DEPT_FOREIGN = "r344-fx"
HANDBOOK = "员工手册"
POLICY = "差旅管理办法"
EXPENSE = "报销标准"
EVIDENCE = POLICY + ".pdf 第 3 页"

_ROLE_OF = {
    "keeper": "manager",
    "peer": "manager",
    "xdept": "manager",
    "staff": "staff",
    "admin": "admin",
}


def _account(kind: str, suffix: str = "") -> dict:
    department = DEPT_FOREIGN if kind == "xdept" else DEPT
    username = "r344-" + kind + suffix
    return {"id": "u-" + username, "username": username, "role": _ROLE_OF[kind], "department": department}


def _principal(kind: str, suffix: str = "") -> Principal:
    return Principal.from_user(_account(kind, suffix))


def _request(principal: Principal):
    state = type("State", (), {"principal": principal, "username": principal.username})()
    return type("Request", (), {"state": state})()


def _call(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture()
def graph(monkeypatch) -> KnowledgeGraph:
    """A store-less ledger: the development dictionary, so no write can reach disk."""
    monkeypatch.setenv("APP_ENV", "development")
    return KnowledgeGraph()


@pytest.fixture()
def route(monkeypatch):
    """The real route, mounted on a fresh in-memory ledger."""
    from app.api.v1 import intelligence

    monkeypatch.setenv("APP_ENV", "development")
    memory = KnowledgeGraph()
    monkeypatch.setattr(intelligence, "_graph", memory)
    return intelligence


def _add(ledger: KnowledgeGraph, subject: str, link: str, object_: str, principal: Principal) -> Relation:
    return ledger.add_relation(subject, link, object_, EVIDENCE, principal=principal)


def _ids(rows: list[dict]) -> list[str]:
    return [item["relation_id"] for item in rows]


# ===================================================== 刀A：本篇只出现在客体位


def test_a_document_registered_only_in_the_target_slot_is_found_by_the_new_leg(graph):
    """判据①：任一端命中。旧腿（只筛主体）在这一行上永远是空的——这正是本单要修的那格。"""
    author = _principal("keeper", "-author")
    row = _add(graph, POLICY, "依据", HANDBOOK, author)

    old_leg = graph.browse(source_entity=HANDBOOK, principal=author)
    assert old_leg == [], "前提不成立：主体腿已经能筛到客体位了，本单就无事可做"

    new_leg = graph.browse(document=HANDBOOK, principal=author)
    assert _ids(new_leg) == [row.relation_id]
    assert new_leg[0]["target"] == HANDBOOK
    assert new_leg[0]["source_entity"] == POLICY


def test_a_document_registered_in_the_subject_slot_is_still_found(graph):
    """正向对照：主体位那一篇换了新腿也照样在，绿不是靠「谁都不给」刷出来的。"""
    author = _principal("keeper", "-author")
    row = _add(graph, POLICY, "依据", HANDBOOK, author)
    assert _ids(graph.browse(document=POLICY, principal=author)) == [row.relation_id]


def test_a_row_that_names_the_document_on_both_ends_comes_back_once(graph):
    """判据①后半：两端都是它，算一次，不许重复出行。"""
    author = _principal("keeper", "-author")
    row = _add(graph, HANDBOOK, "引用", HANDBOOK, author)
    _add(graph, HANDBOOK, "依据", EXPENSE, author)

    listing = graph.browse(document=HANDBOOK, principal=author)
    assert _ids(listing).count(row.relation_id) == 1
    assert len(_ids(listing)) == len(set(_ids(listing))), "同一行出现了两次"


def test_the_route_answers_the_new_leg_on_the_wire(route, monkeypatch):
    """同一道判断必须真的在线上：前端将来按篇取，取的是这一发。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    author = _account("keeper", "-author")
    monkeypatch.setattr(auth, "get_user", lambda username: {author["username"]: author}.get(username))
    row = _add(route._graph, POLICY, "依据", HANDBOOK, Principal.from_user(author))

    client = TestClient(app)
    headers = {"Authorization": "Bearer " + auth.create_token(author["username"])}
    filtered = client.get("/api/v1/knowledge-graph/relations", params={"document": HANDBOOK}, headers=headers)
    unfiltered = client.get("/api/v1/knowledge-graph/relations", headers=headers)

    assert filtered.status_code == 200
    assert [item["relation_id"] for item in filtered.json()["relations"]] == [row.relation_id]
    # 不带参数取全量的既有读法一字不改：它还是这一位能看见的全部。
    assert [item["relation_id"] for item in unfiltered.json()["relations"]] == [row.relation_id]


# ===================================================== 刀B：归一，不是原样相等


@pytest.mark.parametrize(
    ("registered", "queried"),
    [
        ("差旅管理办法.PDF", "差旅管理办法.pdf"),
        ("差旅管理办法.pdf", "差旅管理办法.PDF"),
        ("员工手\u3000册.pdf", "员工手册.pdf"),
        ("\ufeff员工手册.pdf", "员工手册.pdf"),
        ("员工\t手册.pdf", "员工手册.pdf"),
        ("STAFF Handbook", "staff handbook"),
        ("STAFF handbook", "staffhandbook"),
    ],
)
def test_a_registration_spelling_variant_answers_as_the_same_document(graph, registered: str, queried: str):
    """登记名里的大小写与空白不参与身份：摘成 ``==`` 原样比较，这一格当场红。"""
    author = _principal("keeper", "-author")
    row = _add(graph, registered, "依据", "住宿费上限", author)
    assert _ids(graph.browse(document=queried, principal=author)) == [row.relation_id]


# ===================================================== 刀C：整名相等，不许 includes


@pytest.mark.parametrize(
    ("registered", "queried"),
    [
        (HANDBOOK + ".pdf", HANDBOOK),
        (HANDBOOK + "补充规定", HANDBOOK),
        (HANDBOOK, HANDBOOK + ".pdf"),
        (HANDBOOK, HANDBOOK + "补充规定"),
        ("员工", HANDBOOK),
        (HANDBOOK, "员工"),
        ("手册", HANDBOOK),
        (HANDBOOK + "\u200b.pdf", HANDBOOK + ".pdf"),
        ("差旅管理办法", "差旅管理"),
    ],
)
def test_a_name_one_character_off_does_not_answer(graph, registered: str, queried: str):
    """差一个字就不是同一篇：换成 includes / startswith，这一格当场红。"""
    author = _principal("keeper", "-author")
    _add(graph, registered, "依据", "住宿费上限", author)
    assert graph.browse(document=queried, principal=author) == []


# ================================================ 判据③：既有 source_entity 腿一字不改


@pytest.mark.parametrize(
    "queried",
    [" " + HANDBOOK, HANDBOOK + " ", "员工手\u3000册", "员工手册.PDF", HANDBOOK + "\t"],
)
def test_the_subject_leg_still_demands_the_whole_registered_name_verbatim(graph, queried: str):
    """主体腿不许顺手也归一化：它仍是整名逐字相等，那是它一直以来的语义。"""
    author = _principal("keeper", "-author")
    _add(graph, HANDBOOK, "引用", EXPENSE, author)
    assert graph.browse(source_entity=queried, principal=author) == []
    assert graph.browse(source_entity=HANDBOOK, principal=author), "正向对照：逐字给就对得上"


def test_the_new_leg_is_an_addition_and_not_a_replacement(graph):
    """两枚参数各管各的：只给 document 时主体腿不参与，只给 source_entity 时新腿不参与。"""
    author = _principal("keeper", "-author")
    row = _add(graph, POLICY, "依据", HANDBOOK, author)
    assert _ids(graph.browse(document=HANDBOOK, principal=author)) == [row.relation_id]
    assert _ids(graph.browse(source_entity=POLICY, principal=author)) == [row.relation_id]
    assert graph.browse(principal=author), "不带任何筛法时仍是全量"


def test_document_and_source_entity_intersect_and_do_not_overwrite_each_other(graph):
    """判据③：同时给出按 AND 交集，不许互相覆盖——覆盖掉的那一半会悄悄放宽结果。"""
    author = _principal("keeper", "-author")
    policy_about_handbook = _add(graph, POLICY, "依据", HANDBOOK, author)
    handbook_about_expense = _add(graph, HANDBOOK, "规定", EXPENSE, author)
    _add(graph, "部门预算", "参照", EXPENSE, author)

    assert _ids(graph.browse(source_entity=HANDBOOK, document=HANDBOOK, principal=author)) == [
        handbook_about_expense.relation_id
    ]
    assert _ids(graph.browse(source_entity=POLICY, document=HANDBOOK, principal=author)) == [
        policy_about_handbook.relation_id
    ]
    # 主体是另一篇、客体才是这篇：交集必须为空，而不是让 document 盖掉 source_entity。
    assert graph.browse(source_entity="部门预算", document=HANDBOOK, principal=author) == []


def test_document_and_relation_intersect(graph):
    """关系词那一腿同样与 document 取交集。"""
    author = _principal("keeper", "-author")
    cited = _add(graph, POLICY, "依据", HANDBOOK, author)
    _add(graph, POLICY, "废止", HANDBOOK, author)

    assert _ids(graph.browse(relation="依据", document=HANDBOOK, principal=author)) == [cited.relation_id]
    assert graph.browse(relation="废止", document=EXPENSE, principal=author) == []


# ================================================== 判据④：授权腿不许搬家、不许绕


def test_an_anonymous_principal_still_gets_nothing(graph):
    """principal is None 那一支照旧返回 []：新参数不许成为第二条出口。"""
    author = _principal("keeper", "-author")
    _add(graph, POLICY, "依据", HANDBOOK, author)
    assert graph.browse(document=HANDBOOK, principal=None) == []


def test_the_document_filter_never_releases_a_private_row(graph):
    """刀D：命中实体不等于命中权限。断言点名那枚私有记录，不靠条数蒙。"""
    author = _principal("keeper", "-author")
    private = _add(graph, POLICY, "依据", HANDBOOK, author)
    peer = _principal("peer")

    listing = graph.browse(document=HANDBOOK, principal=peer)
    ids = _ids(listing)
    assert private.relation_id not in ids, "客体位筛过了就直接返回，越权那一行上了屏"
    assert ids == []
    body = json.dumps(listing, ensure_ascii=False, default=str)
    assert private.owner_id not in body
    assert HANDBOOK not in body and POLICY not in body, "别人的三元组正文漏给了同部门非作者"
    # 同一个筛法，作者自己看得见：上面的空不是「谁都看不见」。
    assert _ids(graph.browse(document=HANDBOOK, principal=author)) == [private.relation_id]


def test_the_permission_leg_is_asked_about_the_rows_the_filter_matched(graph, monkeypatch):
    """先筛实体就把权限判定整段跳过，这一格红：它断言判定真的在这一行上发生过。"""
    from app.knowledge_graph import service

    author = _principal("keeper", "-author")
    private = _add(graph, POLICY, "依据", HANDBOOK, author)
    asked: list[str] = []
    real_browse = KnowledgeGraph.can_browse

    def spy(record, principal):
        asked.append(record.relation_id)
        return bool(real_browse(record, principal))

    monkeypatch.setattr(service.KnowledgeGraph, "can_browse", staticmethod(spy))
    assert graph.browse(document=HANDBOOK, principal=_principal("peer")) == []
    assert asked == [private.relation_id], "实体筛过的候选行没有经过 can_browse：授权腿被绕过了"


def test_a_cross_department_reader_still_gets_nothing_through_the_new_leg(graph):
    """部门轴不许因为新参数被改松：与 test_r177 那条同判。"""
    author = _principal("keeper", "-author")
    _add(graph, POLICY, "依据", HANDBOOK, author)
    assert graph.browse(document=HANDBOOK, principal=_principal("xdept")) == []


def test_an_administrator_still_sees_the_row_through_the_new_leg(graph):
    """administrator 豁免面照常生效，且返回的记录仍写着它自己的可见性。"""
    author = _principal("keeper", "-author")
    private = _add(graph, POLICY, "依据", HANDBOOK, author)
    listing = graph.browse(document=HANDBOOK, principal=_principal("admin"))
    assert _ids(listing) == [private.relation_id]
    assert listing[0]["visibility"] == "private"


def test_a_staff_clearance_row_follows_the_same_legs(graph):
    """staff 密级下这一格与 manager 同命：筛法不碰密级，也不碰可见性计算。"""
    writer = _principal("staff", "-author")
    row = _add(graph, POLICY, "依据", HANDBOOK, writer)
    assert _ids(graph.browse(document=HANDBOOK, principal=writer)) == [row.relation_id]
    assert graph.browse(document=HANDBOOK, principal=_principal("staff")) == []
    assert _ids(graph.browse(document=HANDBOOK, principal=_principal("admin"))) == [row.relation_id]


def test_the_scope_leg_still_has_no_document_parameter():
    """判据④：新腿只长在 browse 上。query 是 scope answer，不许上屏，也不许被这道筛法喂到。"""
    import inspect

    assert "document" not in inspect.signature(KnowledgeGraph.query).parameters
    assert "document" in inspect.signature(KnowledgeGraph.browse).parameters
    assert "document" in inspect.signature(KnowledgeGraph._listing).parameters


def test_the_scope_leg_still_answers_for_a_peer(graph):
    """同一行人：peer 过 can_read 不过 can_browse。scope 腿的既有读数一字未动。"""
    author = _principal("keeper", "-author")
    private = _add(graph, POLICY, "依据", HANDBOOK, author)
    peer = _principal("peer")
    assert _ids(graph.query(principal=peer)) == [private.relation_id]
    assert _ids(graph.query(POLICY, "依据", principal=peer)) == [private.relation_id]
    assert graph.browse(principal=peer) == [], "评审出口不许被搬到允许上屏的那条腿上"


# ============================================================ 判据⑤：形状一字不改


def test_the_response_shape_and_labels_are_untouched(graph):
    """不新增键、不改键名、不删键：密级与可见性照原样回，筛法只裁行数。"""
    author = _principal("keeper", "-author")
    record = _add(graph, POLICY, "依据", HANDBOOK, author)

    rows = graph.browse(document=HANDBOOK, principal=author)
    expected_keys = {field.name for field in dataclasses.fields(Relation)} | {"version_id"}
    assert len(rows) == 1
    assert set(rows[0]) == expected_keys
    assert rows[0] == record.to_dict()
    assert rows[0]["owner_id"] == author.user_id
    assert rows[0]["classification"] == record.classification
    assert rows[0]["visibility"] == record.visibility, "可见性计算不许因为这道筛法改动分毫"


def test_the_listing_scans_the_store_it_already_scanned(graph, monkeypatch):
    """判据⑥：不许加迁移、加表、加索引、改存储格式。这一格钉住新腿没有偷偷长出第二条读路。"""
    from app.knowledge_graph import service

    author = _principal("keeper", "-author")
    row = _add(graph, POLICY, "依据", HANDBOOK, author)
    calls: list[int] = []
    real_sync = KnowledgeGraph._sync_from_store

    def counting_sync(self):
        calls.append(len(self._relations))
        return real_sync(self)

    monkeypatch.setattr(service.KnowledgeGraph, "_sync_from_store", counting_sync)
    assert _ids(graph.browse(document=HANDBOOK, principal=author)) == [row.relation_id]
    assert calls == [1], "这道筛法没走既有那道全内存扫描，而是另起了一处读数"
    assert graph.storage_state()["storage_mode"] == "memory"


def test_the_route_still_takes_the_request_as_its_third_positional_argument(route):
    """签名里 ``document`` 排在 ``request`` 之后是有原因的：仓里既有调用按位置传 request。"""
    author = _principal("keeper", "-author")
    row = _add(route._graph, POLICY, "依据", HANDBOOK, author)

    def ids(*args, **kwargs) -> list[str]:
        return _ids(_call(route.list_relations(*args, **kwargs))["relations"])

    assert ids(POLICY, None, _request(author)) == [row.relation_id]
    assert ids(None, None, _request(author), HANDBOOK) == [row.relation_id]
    assert ids(None, None, _request(author), HANDBOOK) == ids(None, None, _request(author), document=HANDBOOK)
    # 只给位置参数、不给 document：既有全量读法一字未变。
    assert ids(None, None, _request(author)) == [row.relation_id]
    assert ids(HANDBOOK, None, _request(author)) == []


def test_the_wire_shape_is_still_one_key_around_the_rows(route, monkeypatch):
    """判据⑤从出口再量一次：响应还是 ``{"relations": [...]}``，行内键一字不多一字不少。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    account = _account("keeper", "-author")
    monkeypatch.setattr(auth, "get_user", lambda username: {account["username"]: account}.get(username))
    author = Principal.from_user(account)
    record = _add(route._graph, POLICY, "依据", HANDBOOK, author)

    client = TestClient(app)
    headers = {"Authorization": "Bearer " + auth.create_token(account["username"])}
    response = client.get("/api/v1/knowledge-graph/relations", params={"document": HANDBOOK}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"relations"}
    assert [item["relation_id"] for item in body["relations"]] == [record.relation_id]
    expected_keys = {field.name for field in dataclasses.fields(Relation)} | {"version_id"}
    assert set(body["relations"][0]) == expected_keys
    assert body["relations"][0]["target"] == HANDBOOK
    assert body["relations"][0]["source_entity"] == POLICY
    assert "document" not in body["relations"][0], "筛法参数不许回写进记录里"
