"""R299 · 收件箱的读模型与权限：三本既有账的投影，两套计数口径，零条越权。

本件与 tests/test_r299_notification_states.py 的分工写死在文件名里：那一件管迁移与生命周期词表
（判据①⑥），本件管「谁看见什么、数出来是多少、能不能动手」（判据②③④），并负责判据⑦里越权与
计数那两枚反证。

判据②在这一层只有一种钉法：**业务账一动，收件箱必须跟着动**。所以本文件不去数新表里有几行（那
正是第二本账的样子），而是把一条告警在它自己的台账里关掉，再看收件箱还剩什么 —— 只有当收件箱没有
自己的历史可以保留时，它才真的只是一份投影。

判据③全部沿用既有判定，本件一个新过滤器都不写：审批看 pending_approvals 的行归属，告警看
alerts.alert_row_visible，文档看 chat.list_document_catalog 背后的 authorization_decision。硬门
是越权 0 条，所以每一枚「看不见」的用例都配一枚「同一枚 id 由他去 dismiss 也写不下行」；另有两枚
反证分别把行级谓词与密级门槛拆掉，证明挡住他的是那道门，不是巧合。

判据④把 R278 踩过的那一格写进字段名：returned / unread_returned 是**本页长度**，total /
unread_total 是**候选窗口内的全集总数**，四枚各自命名、互不冒充，并有专枚钉住「整表长度与页长都
不等于未读总数」。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import alerts as alerts_api
from app.documents import catalog
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store

REPO = Path(__file__).resolve().parents[1]
MIGRATION_FILENAME = "0016_notification_states.sql"

INBOX_PATH = "/api/v1/notifications"
READ_PATH = "/api/v1/notifications/read"
DISMISS_PATH = "/api/v1/notifications/dismiss"
ALERT_CLOSE_PATH = "/api/v1/alerts/{alert_id}/close"

DEPT_FINANCE = "r299-finance"
DEPT_HR = "r299-hr"

FINANCE_STAFF = "r299-finance-staff"
FINANCE_MANAGER = "r299-finance-manager"
HR_MANAGER = "r299-hr-manager"
ADMINISTRATOR = "r299-administrator"
#: 同部门、同角色，只有密级不同：判据③那一格「同部门不同密级」的两条腿之一。
FINANCE_STAFF_C3 = "r299-finance-staff-c3"


def _account(username: str, department: str, role: str, **extra) -> dict:
    row = {"id": username, "username": username, "role": role, "department": department}
    row.update(extra)
    return row


ACCOUNTS = {
    FINANCE_STAFF: _account(FINANCE_STAFF, DEPT_FINANCE, "staff"),
    FINANCE_STAFF_C3: _account(FINANCE_STAFF_C3, DEPT_FINANCE, "staff", clearance=3),
    FINANCE_MANAGER: _account(FINANCE_MANAGER, DEPT_FINANCE, "manager"),
    HR_MANAGER: _account(HR_MANAGER, DEPT_HR, "manager"),
    ADMINISTRATOR: _account(ADMINISTRATOR, "", "admin"),
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """Serve the fixture accounts through the lookup the auth middleware uses."""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    monkeypatch.setattr(auth, "_db_ready", False)


@pytest.fixture(autouse=True)
def offline_legs(monkeypatch):
    """Pin every leg to its in-memory shape, so a reachable PostgreSQL cannot split the truth."""
    monkeypatch.setattr(hitl_store, "_MEM_ROWS", {})
    monkeypatch.setattr(hitl_store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_api, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts_api, "_database_available", lambda: False)
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: False)


@pytest.fixture(autouse=True)
def document_store(monkeypatch, tmp_path):
    """The real offline catalog, rooted in tmp_path.

    Rows are written through ``record_local_document_version`` so the authorization judgment
    under test reads the same shape a deployed catalog row carries (same as R14-A1's fixture).
    """
    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root))

    def add(
        filename: str,
        *,
        department: str,
        owner: str,
        classification: int = 1,
        index_status: str = "indexed",
    ) -> str:
        stored = root / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本\n100 80\n", encoding="utf-8")
        catalog.record_local_document_version(
            filename,
            classification,
            department,
            str(stored),
            1,
            owner_id=owner,
            index_status=index_status,
        )
        return filename

    return add


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def _headers(username: str) -> dict:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _inbox(client, username: str, **params):
    return client.get(INBOX_PATH, headers=_headers(username), params=params)


def _ids(payload: dict) -> list[str]:
    return sorted(row["id"] for row in payload["notifications"])


def _park(session_id: str, owner: str) -> None:
    hitl_store.record_awaiting(session_id, owner, ["chart"], request_id="req-r299")


def _seed_alert(
    alert_id: int,
    department: str,
    *,
    minute: int = 0,
    status: str = "open",
) -> dict:
    row = {
        "id": alert_id,
        "rule_id": 1,
        "message": f"R299 营收跌破阈值 {alert_id}",
        "read": False,
        "department": department,
        "created_at": f"2026-09-26T09:{minute:02d}:00+08:00",
    }
    if status != "open":
        # 缺 status 键按 open 读是台账那一侧的默认值，所以只有非 open 才需要写出来。
        row["status"] = status
    alerts_api._MEM_ALERTS.append(row)
    return row


def _dismiss(client, username: str, *identifiers: str):
    return client.post(
        DISMISS_PATH, headers=_headers(username), json={"ids": list(identifiers)}
    )


def _mark_read(client, username: str, *identifiers: str):
    return client.post(READ_PATH, headers=_headers(username), json={"ids": list(identifiers)})

# -------------------------------------------------------------- 判据①②：一份收件箱，三本账


def test_the_three_ledgers_arrive_as_one_inbox_with_stable_ids(client, document_store):
    """三枚源各出一枚，ID 由源那一侧的键拼出，读两次得到同一串。

    稳定 ID 的意义在这里被具体检查：读者状态要能挂得住，靠的不是本单生成的自增号，而是
    「审批就是那一轮的 session_id、告警就是台账里的 id、文档就是 filename#v 版本」——三枚键
    都活在本单之外的账上。
    """
    _park("sess-r299-a", FINANCE_MANAGER)
    _seed_alert(701, DEPT_FINANCE)
    document_store("r299-plan.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER)
    expected = ["alert:701", "approval:sess-r299-a", "document:r299-plan.pdf#v1"]

    first = _inbox(client, FINANCE_MANAGER).json()
    second = _inbox(client, FINANCE_MANAGER).json()

    assert _ids(first) == expected
    assert _ids(first) == _ids(second), "同一批账读两次不该换名字：状态会挂不住"
    assert set(first["sources"]) == {"approval", "alert", "document"}, "第四枚源就是第四本账"
    assert {row["state"] for row in first["notifications"]} == {"unread"}
    assert (first["total"], first["unread_total"], first["returned"]) == (3, 3, 3)
    # 光是读一遍，不该在生命周期那一层留下任何一行 —— unread 是「没有行」，不是一次写。
    assert state_store._ROWS == {}


def test_a_terminal_alert_leaves_the_inbox_because_the_inbox_keeps_no_copy(client):
    """判据②的正面证据：告警在自己的台账里被关掉，收件箱下一读就没有它。

    用的是台账那个真端点（POST /alerts/{id}/close），不是把收件箱里那一格抹掉。如果收件箱
    偷偷存了一份候选，关掉之后它还能靠自己的那份继续催人来 —— 那正是本单禁止的第二本账。
    """
    _seed_alert(711, DEPT_FINANCE)
    assert "alert:711" in _ids(_inbox(client, FINANCE_MANAGER).json())

    closed = client.post(
        ALERT_CLOSE_PATH.format(alert_id=711), headers=_headers(FINANCE_MANAGER)
    )

    assert closed.status_code == 200
    assert closed.json()["alert"]["status"] == "closed"
    body = _inbox(client, FINANCE_MANAGER).json()
    assert _ids(body) == []
    assert (body["total"], body["unread_total"]) == (0, 0)
    assert state_store.recipient_states(FINANCE_MANAGER) == {}


def test_a_decided_approval_todo_disappears_with_the_same_read(client):
    """同一件事在审批那一本账上成立：决定之后台账闭合，收件箱不许再挂着那一枚。"""
    _park("sess-r299-b", FINANCE_MANAGER)
    assert "approval:sess-r299-b" in _ids(_inbox(client, FINANCE_MANAGER).json())

    hitl_store.mark_status("sess-r299-b", hitl_store.RESUMED)

    body = _inbox(client, FINANCE_MANAGER).json()
    assert "approval:sess-r299-b" not in _ids(body)


def test_a_source_the_caller_has_no_right_to_read_is_omitted_with_a_reason(client):
    """staff 读不了告警台账：这一格不供数并说得出原因，而不是回一枚看着像平安的 0。

    口径抄自看板 R188 那一格（宁缺勿零）。区别只在收件箱把它写在 sources 投影里，让前端能
    把「你没权限看这一类」和「这一类今天没有事」画成两张脸。
    """
    _seed_alert(712, DEPT_FINANCE)

    body = _inbox(client, FINANCE_STAFF).json()

    assert body["sources"]["alert"]["included"] is False
    assert body["sources"]["alert"]["reason_code"] == "permission_denied"
    assert not any(row["source_type"] == "alert" for row in body["notifications"])
    # 同一次读里，另一枚有权的账号确实看得到：省略的是权限，不是这一类源。
    assert "alert:712" in _ids(_inbox(client, FINANCE_MANAGER).json())


def test_a_document_that_never_entered_the_index_is_not_a_completion_notice(client, document_store):
    """文档那一格只认 catalog 自己写下的 indexed：excluded 与历史行都不算「索引完成」。"""
    document_store("r299-draft.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER, index_status="excluded")
    document_store("r299-legacy.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER, index_status="unknown")
    document_store("r299-real.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER)

    ids = _ids(_inbox(client, FINANCE_MANAGER).json())

    assert ids == ["document:r299-real.pdf#v1"]


# ------------------------------------------------------------------ 判据③：越权 0 条是硬门


def test_one_persons_approval_todo_never_lands_in_another_persons_inbox(client):
    """「A 看不到 B 的」那一枚硬门用例，连同「A 也替 B 划不掉它」。"""
    _park("sess-r299-owned", FINANCE_MANAGER)

    assert "approval:sess-r299-owned" in _ids(_inbox(client, FINANCE_MANAGER).json())
    assert "approval:sess-r299-owned" not in _ids(_inbox(client, HR_MANAGER).json())
    assert "approval:sess-r299-owned" not in _ids(_inbox(client, ADMINISTRATOR).json())

    refused = _dismiss(client, HR_MANAGER, "approval:sess-r299-owned").json()

    assert refused["requested"] == 1
    assert refused["changed"] == 0
    assert refused["results"][0]["state"] is None
    assert refused["results"][0]["reason"] == "notification_not_addressable"
    # 越权写一行都没落下，而且真正的主人仍然看到一枚未读。
    assert state_store._ROWS == {}
    owner = _inbox(client, FINANCE_MANAGER).json()
    rows = [row for row in owner["notifications"] if row["id"] == "approval:sess-r299-owned"]
    assert [row["state"] for row in rows] == ["unread"]
    assert (owner["total"], owner["unread_total"]) == (1, 1)


def test_an_administrators_scope_does_not_reach_the_hitl_ledger(client):
    """管理员在告警与文档上不受部门限制，不等于他能替别人决定挂起项。

    审批那一本账的归属谓词从来不是部门，是 owner_user_id。这一枚钉的是「别把管理员当成能读
    别人的待办」这条既端口径，收件箱不在这里新增第二种管理员。
    """
    _park("sess-r299-private", FINANCE_MANAGER)

    assert "approval:sess-r299-private" not in _ids(_inbox(client, ADMINISTRATOR).json())


def test_the_same_department_with_a_lower_clearance_cannot_see_the_classified_document(
    client, document_store
):
    """「同部门不同密级看不到」那一枚硬门用例，两向都判。"""
    document_store(
        "r299-secrecy.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER, classification=2
    )
    identifier = "document:r299-secrecy.pdf#v1"

    staff = _inbox(client, FINANCE_STAFF).json()
    manager = _inbox(client, FINANCE_MANAGER).json()

    assert identifier not in _ids(staff)
    assert identifier in _ids(manager)
    assert (manager["total"], manager["unread_total"]) == (1, 1)
    assert (staff["total"], staff["unread_total"]) == (0, 0)

    refused = _dismiss(client, FINANCE_STAFF, identifier).json()
    assert refused["changed"] == 0
    assert refused["results"][0]["reason"] == "notification_not_addressable"
    assert state_store._ROWS == {}


def test_counter_evidence_a_raising_the_clearance_admits_the_document(client, document_store):
    """反证（判据⑦·越权那枚之一）：把密级抬到 3，同一份文档立刻可见。

    这一枚证明上面那句「看不见」是 authorization_decision 判出来的，而不是文档那一腿恰好没
    供数。顺手也证明抬上去之后 dismiss 写得下了 —— 挡住写的和挡住读的是同一道门。
    """
    document_store(
        "r299-secrecy.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER, classification=2
    )
    identifier = "document:r299-secrecy.pdf#v1"
    assert identifier not in _ids(_inbox(client, FINANCE_STAFF).json())

    body = _inbox(client, FINANCE_STAFF_C3).json()

    assert identifier in _ids(body)
    assert _dismiss(client, FINANCE_STAFF_C3, identifier).json()["changed"] == 1
    assert state_store.recipient_states(FINANCE_STAFF_C3) == {identifier: "dismissed"}


def test_counter_evidence_b_removing_the_row_predicate_admits_another_departments_alert(
    client, monkeypatch
):
    """反证（判据⑦·越权那枚之二）：摘掉 alert_row_visible，别的部门的告警立刻流进来。

    本单没有自己的行级过滤器可摘 —— 这正是它只是一份投影的证据。把台账那一侧的谓词换成恒真，
    收件箱跟着变脏，说明「跨部门不可见」这一格有牙，而且牙齿长在既有的那一份定义上。
    """
    _seed_alert(720, DEPT_HR)
    assert "alert:720" not in _ids(_inbox(client, FINANCE_MANAGER).json())
    assert "alert:720" in _ids(_inbox(client, HR_MANAGER).json())
    assert "alert:720" in _ids(_inbox(client, ADMINISTRATOR).json())

    monkeypatch.setattr(alerts_api, "alert_row_visible", lambda principal, row: True)

    assert "alert:720" in _ids(_inbox(client, FINANCE_MANAGER).json())
    assert _dismiss(client, FINANCE_MANAGER, "alert:720").json()["changed"] == 1

# ----------------------------------------------- 判据④：两套计数口径，各有一枚反证钉住


def test_the_two_counting_bases_stay_apart_across_pages(client):
    """12 枚未读、页宽 5：returned 说本页，total / unread_total 说全集，四枚各自命名。

    第二页只交回 2 条，但两枚总数一个字都不改 —— 这一格 R278 踩过（一个说不清口径的 count
    最后被摘掉），本件把它钉死成断言而不是注释。
    """
    for index in range(12):
        _seed_alert(800 + index, DEPT_FINANCE, minute=index)

    first = _inbox(client, FINANCE_MANAGER, limit=5, offset=0).json()
    assert first["returned"] == 5
    assert first["unread_returned"] == 5
    assert first["total"] == 12
    assert first["unread_total"] == 12
    assert first["has_more"] is True
    assert first["returned"] != first["total"], "页长冒充全集总数就是 R278 那一格"

    tail = _inbox(client, FINANCE_MANAGER, limit=5, offset=10).json()
    assert tail["returned"] == 2
    assert tail["unread_returned"] == 2
    assert (tail["total"], tail["unread_total"]) == (12, 12), "翻页不许改变全集的答案"


def test_marking_a_page_read_lowers_the_whole_set_unread_count_not_the_membership(client):
    """read 只降未读数，不把条目从列表里拿掉；两条计数因此各走各的。"""
    for index in range(12):
        _seed_alert(800 + index, DEPT_FINANCE, minute=index)
    page = [row["id"] for row in _inbox(client, FINANCE_MANAGER, limit=5).json()["notifications"]]

    written = _mark_read(client, FINANCE_MANAGER, *page).json()

    assert written["changed"] == 5
    body = _inbox(client, FINANCE_MANAGER).json()
    assert (body["returned"], body["total"], body["unread_total"]) == (12, 12, 7)

    unread_only = _inbox(client, FINANCE_MANAGER, state="unread", limit=20).json()
    assert unread_only["returned"] == 7
    assert unread_only["unread_returned"] == 7
    # total / unread_total 说的是全集，与 state 过滤无关；过滤只裁这一页。
    assert (unread_only["total"], unread_only["unread_total"]) == (12, 7)


def test_counter_evidence_c_the_unread_count_is_neither_the_page_nor_the_whole_overlay(client):
    """反证（判据⑦·计数那枚）：未读总数与「本页长度」「覆盖层行数」互不相等。

    刻意铺出四组互不相等的数：7 枚候选，3 枚已读、1 枚已划掉、3 枚未读，另外还给同事写 1 行。
    于是本页长度 2、全集 6、这个人的覆盖层 4 行、整张覆盖层 5 行，而正确的未读总数是 3。
    谁把 unread_total 数成整表长度、这个人的行数，或者干脆数本页，这一枚当场红。
    """
    for index in range(7):
        _seed_alert(850 + index, DEPT_FINANCE, minute=index)
    for index in range(3):
        state_store.apply_state(FINANCE_MANAGER, f"alert:{850 + index}", "read")
    state_store.apply_state(FINANCE_MANAGER, "alert:853", "dismissed")
    state_store.apply_state(HR_MANAGER, "alert:854", "read")

    body = _inbox(client, FINANCE_MANAGER, limit=2).json()

    assert body["returned"] == 2
    assert body["unread_returned"] == 2
    assert body["total"] == 6, "已划掉的那一枚不再算这个人的账"
    assert body["unread_total"] == 3
    assert len(state_store.recipient_states(FINANCE_MANAGER)) == 4
    assert len(state_store._ROWS) == 5
    wrong_bases = {
        body["returned"],
        body["unread_returned"],
        len(state_store._ROWS),
        len(state_store.recipient_states(FINANCE_MANAGER)),
    }
    assert wrong_bases == {2, 4, 5}, wrong_bases
    assert body["unread_total"] not in wrong_bases


def test_an_exhausted_source_window_says_so_instead_of_calling_the_lower_bound_exact(client):
    """窗口裁过任何一枚源，is_exact 就必须是 False，并把扫到的条数一起交回。

    全集在这里只是**下界**：把下界说成精确数就是假话，而数得动与否本来就该是看得见的字段。
    55 枚告警跨过每枚源 50 的那道读侧代价上限，台账那一腿自己那条 LIMIT 100 还没撞上。
    """
    for index in range(3):
        _seed_alert(900 + index, DEPT_FINANCE, minute=index)

    small = _inbox(client, FINANCE_MANAGER).json()
    assert small["is_exact"] is True
    assert small["sources"]["alert"]["truncated"] is False
    assert (small["total"], small["sources"]["alert"]["scanned"]) == (3, 3)

    for index in range(52):
        _seed_alert(910 + index, DEPT_FINANCE, minute=index % 60)

    big = _inbox(client, FINANCE_MANAGER).json()
    assert big["sources"]["alert"]["truncated"] is True
    assert big["sources"]["alert"]["scanned"] == 55
    assert big["total"] == 50, "窗口外的候选不该被算进这份答复"
    assert big["is_exact"] is False


# ---------------------------------------------------- 判据④：两个动作，幂等且单向


def test_dismissing_is_idempotent_and_read_cannot_resurrect_it(client):
    """重复 dismiss 不报错也不改变结论；已划掉的不许被「标为已读」悄悄放回去。"""
    _seed_alert(870, DEPT_FINANCE)
    identifier = "alert:870"

    first = _dismiss(client, FINANCE_MANAGER, identifier).json()
    assert (first["changed"], first["results"][0]["state"]) == (1, "dismissed")

    again = _dismiss(client, FINANCE_MANAGER, identifier).json()
    assert (again["changed"], again["results"][0]["state"]) == (0, "dismissed"), "第二次是同一结论"

    revived = _mark_read(client, FINANCE_MANAGER, identifier).json()
    assert (revived["changed"], revived["results"][0]["state"]) == (0, "dismissed")

    body = _inbox(client, FINANCE_MANAGER).json()
    assert _ids(body) == []
    assert (body["total"], body["unread_total"]) == (0, 0)
    # dismissed 不是可过滤的状态：已经出账的东西要在台账里看，收件箱不供第二份历史。
    assert _inbox(client, FINANCE_MANAGER, state="dismissed").status_code == 422


def test_reading_then_dismissing_advances_once_and_only_once(client):
    """read → dismiss 是唯一的升级方向，两步各写一行结论，第二步之后 read 不再有意义。"""
    _seed_alert(871, DEPT_FINANCE)
    identifier = "alert:871"

    read = _mark_read(client, FINANCE_MANAGER, identifier).json()
    assert (read["changed"], read["results"][0]["state"]) == (1, "read")
    assert _inbox(client, FINANCE_MANAGER).json()["unread_total"] == 0

    dismissed = _dismiss(client, FINANCE_MANAGER, identifier).json()
    assert (dismissed["changed"], dismissed["results"][0]["state"]) == (1, "dismissed")
    assert state_store.recipient_states(FINANCE_MANAGER) == {identifier: "dismissed"}
    assert _ids(_inbox(client, FINANCE_MANAGER).json()) == []


def test_the_write_side_accepts_the_same_action_twice_in_one_call(client):
    """同一批里重复的 id 会先去重，再逐条给结论；一条都不许多写。"""
    _seed_alert(872, DEPT_FINANCE)
    _seed_alert(873, DEPT_FINANCE, minute=1)

    once = _mark_read(client, FINANCE_MANAGER, "alert:872", "alert:872", "alert:873").json()

    assert once["requested"] == 2, "回执里说的就是去重后的条数"
    assert once["changed"] == 2
    assert [row["state"] for row in once["results"]] == ["read", "read"]
    assert len(state_store.recipient_states(FINANCE_MANAGER)) == 2


# --------------------------------------------- 出口形状：身份、代填、缺表与非法 id


def test_an_anonymous_caller_gets_no_inbox_and_no_count(client):
    response = client.get(INBOX_PATH)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


@pytest.mark.parametrize(
    "payload",
    [
        {"ids": ["alert:880"], "recipient": HR_MANAGER},
        {"ids": ["alert:880"], "username": HR_MANAGER},
        {"ids": ["alert:880"], "department": DEPT_HR},
        {"ids": ["alert:880"], "state": "dismissed"},
        {"ids": []},
        {"ids": ["approval:"]},
        {"ids": ["invoice:880"]},
        {"notification_ids": ["alert:880"]},
    ],
)
def test_the_body_cannot_name_a_recipient_or_smuggle_a_fourth_source(client, payload):
    """收件人永远取会话那一侧的投影；body 里多出任何一格都是整条拒，不做半收。

    ``approval:`` 与 ``invoice:880`` 两枚走的是同一条形状判定：认不出源、或拼不出稳定键，
    一律 422。拒绝的理由只能是形状，不能是「这一枚存不存在」，否则 422 就成了枚举工具。
    """
    _seed_alert(880, DEPT_FINANCE)

    response = client.post(
        READ_PATH, headers=_headers(FINANCE_MANAGER), json=payload
    )

    assert response.status_code == 422, payload
    assert response.json()["detail"] == "validation_error"
    assert state_store._ROWS == {}, "一次被拒的写不许留下半行"
    assert _inbox(client, FINANCE_MANAGER).json()["unread_total"] == 1


@pytest.mark.parametrize("params", [{"state": "dismissed"}, {"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_an_out_of_range_page_or_filter_is_refused_before_any_ledger_is_read(client, params):
    _seed_alert(881, DEPT_FINANCE)

    response = _inbox(client, FINANCE_MANAGER, **params)

    assert response.status_code == 422
    assert response.json()["detail"] == "validation_error"


class _AbsentTableConnection:
    """``to_regclass`` answering NULL is the only thing this fake is allowed to say."""

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)
        return type("Result", (), {"fetchone": lambda self: {"table_name": None}})()


def _no_state_table(monkeypatch):
    monkeypatch.setattr(state_store, "_database_available", lambda: True)
    conn = _AbsentTableConnection()
    monkeypatch.setattr(state_store, "_conn", lambda: conn)
    return conn


def test_a_missing_migration_refuses_the_inbox_instead_of_a_quiet_empty_answer(client, monkeypatch):
    """0016 没跑 ⇒ 503。把「表没迁移」洗成「这个人没有已读记录」正是判据⑥要防的那类假绿。"""
    _seed_alert(890, DEPT_FINANCE)
    _no_state_table(monkeypatch)

    response = _inbox(client, FINANCE_MANAGER)

    assert response.status_code == 503
    assert response.json() == {"detail": "storage_unavailable"}


def test_a_missing_migration_refuses_the_write_the_same_way(client, monkeypatch):
    _seed_alert(891, DEPT_FINANCE)
    _no_state_table(monkeypatch)

    response = _dismiss(client, FINANCE_MANAGER, "alert:891")

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"


def test_only_the_missing_table_refuses_with_503_a_different_error_stays_a_bug(client, monkeypatch):
    """503 只接具名那一种错：把任何异常都洗成「存储不可用」，就是替真正的 bug 打掩护。"""
    _seed_alert(892, DEPT_FINANCE)
    monkeypatch.setattr(state_store, "_database_available", lambda: True)

    def broken():
        raise RuntimeError("connection pool exhausted")

    monkeypatch.setattr(state_store, "_conn", broken)

    with pytest.raises(RuntimeError, match="connection pool exhausted"):
        _inbox(client, FINANCE_MANAGER)


# ------------------------------------------------- 判据②的结构性证据：表里存了什么


def _table_block() -> str:
    ddl = (REPO / "migrations" / MIGRATION_FILENAME).read_text(encoding="utf-8")
    # 锚点取整句建表语句，不是 "CREATE TABLE" 六个字：文件头的散文里也写着这个词，
    # 从那里切下去会把注释当成列清单，结构判就成了看运气红的东西。
    marker = "CREATE TABLE IF NOT EXISTS notification_states ("
    assert marker in ddl, "0016 里找不到那枚建表语句：这一枚结构判不能空转"
    return ddl.split(marker, 1)[1].split(");", 1)[0]


def test_the_new_table_holds_reader_state_and_no_shadow_of_the_underlying_facts():
    """表结构本身就是判据②的证据：只有读者状态那几列，没有正文、部门、密级、状态列。

    这一枚不数行数、不看代码，读的是落库的形状。谁哪天往这张表上补一列 message 或
    department，它就红 —— 那正是「顺手长成第二本账」的第一步。
    """
    columns = []
    for line in _table_block().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("CONSTRAINT", "CHECK", "--")) or stripped == ")":
            continue
        first = re.split(r"\s+", stripped)[0]
        assert re.fullmatch(r"[a-z_]+", first), f"读不懂这一列：{stripped}"
        columns.append(first)

    assert columns == ["id", "notification_id", "recipient", "state", "recorded_at", "updated_at"]
    for shadow in ("message", "title", "detail", "body", "department", "classification", "owner"):
        assert shadow not in columns


def test_the_overlay_writes_no_more_than_the_table_can_hold(client):
    """内存腿与 PG 腿同形状：一行只有状态与两枚时间戳，认不出任何一条业务事实。"""
    _seed_alert(900, DEPT_FINANCE)

    _mark_read(client, FINANCE_MANAGER, "alert:900")

    written = list(state_store._ROWS.values())
    assert [sorted(row) for row in written] == [["recorded_at", "state", "updated_at"]]
    assert written[0]["state"] == "read"
    assert list(state_store._ROWS) == [(FINANCE_MANAGER, "alert:900")]
