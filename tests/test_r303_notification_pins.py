# -*- coding: utf-8 -*-
"""R303 · 通知中心收口（一）：truncated 的两半支、部分成功的写侧语义、三源满载的一次耗时。

本单不加功能，只把 R299 自己在三笔诚实账里点名的四处「写了没人验」逐条变成钉。判据①③④落在
本文件，判据②与它的两枚反证在 tests/test_r303_pg_upsert_leg.py。

判据①的形状：实现里那一行 truncated = truncated or len(rows) >= ALERT_LEG_PAGE 是一句有两个
理由的 or。R299 的窗口件只铺到 55 枚，先被 SOURCE_WINDOW 裁掉，右边那一支从来没被执行过。这里
因此铺两批**只可能触发一支**的量：55 枚 open（过窗口、未过台账页）钉左支；100 行台账里只留 1 枚
open（候选数远在窗口之下、行数恰好撞满台账那一腿的页）钉右支。两枚件都把「是哪一支在置位」写进
断言所用的 candidates / scanned 两格，而不是让下一个人去读代码推断。

判据③的形状：写侧是「逐条给结论」，一条越权不挡其余。这一格最容易被一次「顺手清理」改成整批
事务 —— 那既改了语义（别人的一枚 id 让这个人的其它动作全丢），又让 changed 变成不可信。所以钉的
不是响应码，而是一枚语义不变量：混批里被拒的那一条自己吃 reason，其余照写、照计数；并且把「被拒
的那枚在前还是在后」几种次序都判一遍 —— 只在一种次序下成立的实现，本身就是半批回滚。

判据④的形状：三本账合并后在内存里切页，只有 offset 游标、没有 keyset。这一枚件量的是**离线钉
口径的一次耗时**（每源铺到窗口上限，走 TestClient，PostgreSQL 与宿主模型都不可用），数字随断言
一起打印并写进契约，且必须自带那句「这不是真机读数」—— 测试替身的毫秒数说成生产性能就是假话。

反证纪律（判据⑤）：变异只落 tests/_temp_edit_overlay.py 那台影子根（临时目录副本），并 exec 进
内存里同一枚模块字典；盘上的被跟踪文件全程只读，进出各量一次 sha256。锚点按行列表给，换行由文件
自己决定（本仓 CRLF），命中数不是恰好一枚就整体不落盘。
"""
from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.api.v1 import alerts as alerts_api
from app.documents import catalog
from app.notifications import inbox as inbox_module
from app.notifications import sources as sources_module
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
SOURCES_PY = REPO / "app" / "notifications" / "sources.py"
NOTIFICATIONS_PY = REPO / "app" / "api" / "v1" / "notifications.py"
STATES_PY = REPO / "app" / "notifications" / "states.py"

INBOX_PATH = "/api/v1/notifications"
READ_PATH = "/api/v1/notifications/read"
DISMISS_PATH = "/api/v1/notifications/dismiss"

DEPT_FINANCE = "r303-finance"
DEPT_HR = "r303-hr"
FINANCE_MANAGER = "r303-finance-manager"
HR_MANAGER = "r303-hr-manager"

#: 契约里那些字段名是拿反引号包的；反引号在本文件里只由这一枚常量拼出来，不写进字面量。
BACKTICK = chr(96)

#: 判据④的读数落在模块字典里：跑一次现量一次，不许有人把上一窗口的毫秒数抄进断言。
FULL_WINDOW_READ: dict[str, float] = {}


def _account(username: str, department: str, role: str) -> dict:
    return {"id": username, "username": username, "role": role, "department": department}


ACCOUNTS = {
    FINANCE_MANAGER: _account(FINANCE_MANAGER, DEPT_FINANCE, "manager"),
    HR_MANAGER: _account(HR_MANAGER, DEPT_HR, "manager"),
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """Serve the fixture accounts through the lookup the auth middleware uses."""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    monkeypatch.setattr(auth, "_db_ready", False)


@pytest.fixture(autouse=True)
def offline_legs(monkeypatch):
    """Pin every leg to its in-memory shape: a reachable PostgreSQL cannot split the truth."""
    monkeypatch.setattr(hitl_store, "_MEM_ROWS", {})
    monkeypatch.setattr(hitl_store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_api, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts_api, "_database_available", lambda: False)
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: False)


@pytest.fixture()
def document_store(monkeypatch, tmp_path):
    """The real offline catalog, rooted in tmp_path (the shape R299 already uses)."""
    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root))

    def add(filename: str, *, department: str, owner: str, classification: int = 1,
            index_status: str = "indexed") -> str:
        stored = root / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本" + chr(10) + "100 80" + chr(10), encoding="utf-8")
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
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _headers(username: str) -> dict:
    from app.common.auth import create_token

    return {"Authorization": "Bearer " + create_token(username)}


def _inbox(client, username: str, **params):
    return client.get(INBOX_PATH, headers=_headers(username), params=params)


def _seed_alert(alert_id: int, department: str, *, minute: int = 0, status: str = "open") -> dict:
    row = {
        "id": alert_id,
        "rule_id": 1,
        "message": "R303 库存周转告警 " + str(alert_id),
        "read": False,
        "department": department,
        "created_at": "2026-09-26T09:" + format(minute % 60, "02d") + ":00+08:00",
    }
    if status != "open":
        # 缺 status 键按 open 读是台账那一侧的默认值，所以只有非 open 才需要写出来。
        row["status"] = status
    alerts_api._MEM_ALERTS.append(row)
    return row


def _park(session_id: str, owner: str) -> None:
    hitl_store.record_awaiting(session_id, owner, ["chart"], request_id="req-" + session_id)


def _contract_text() -> str:
    return CONTRACT.read_bytes().decode("utf-8")


# ------------------------------------------------- 反证窗：只改内存与影子副本，不碰盘上的字


def _name_of(path: Path) -> str:
    return path.name


class _R303Edit(overlay.ShadowEdit):
    """一扇 R303 的反证窗：变异落临时目录里的影子副本，并 exec 进内存那一枚模块字典。

    锚点按**行列表**给，换行由被改文件自己决定：本仓文件体是纯 CRLF，把换行写进锚点字面量迟早
    对不上，命中数就会读成 0 处，反证当场变成一枚空转的钉。命中数不是恰好一处，整片变异不落盘；
    变异文本还要先过一枚 compile()，语法不过就连窗都不开。
    """

    tag = "r303"
    #: 🔴 R466：变异只落影子副本，不 exec 进活模块。整份码体重跑会把 sources.py 每一枚顶层
    #: 函数换成新身体（本席现取：9 枚把手身份全换），而那次 exec 在 __enter__ 里——它一炸就
    #: 没有 __exit__ 来还原。改绑走 r466.install_mutation，只碰变了的那几枚名字。
    execs_module = False

    def __init__(self, path: Path, old_lines, new_lines) -> None:
        super().__init__(path)
        self.old_lines = tuple(old_lines)
        self.new_lines = tuple(new_lines)

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        old = newline.join(self.old_lines)
        hits = text.count(old)
        assert hits == 1, (
            _name_of(self.path) + " 里锚点命中 " + str(hits) + " 处（要求恰好 1 处）：变异整体不落盘"
        )
        mutated = text.replace(old, newline.join(self.new_lines), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _mutate(path: Path, old_lines, new_lines, rebind=()):
    """开一扇反证窗：变异只落影子副本，窗内只把**变了的那几枚顶层绑定**装进活模块，出门逐枚装回。

    rebind 讲清的是 import 语句那次一次性拷贝这件事：sources.py 换掉的 alert_candidates 不会自己
    爬进 inbox 的命名空间，所以窗内指过去、退出时按快照装回去。盘上那枚文件全程只读。

    🔴 R466：旧姿势是 ``execs_module = True``——开窗那一刻把变异后的整份码体 exec 进 sys.modules
    里那枚活模块。姿势件在本仓 ``r466.install_mutation``，与 ``test_r457_*:169-242`` 同一族：
    模块体不重跑，没变的名字连对象身份都不动；变了的名字在 finally 里逐枚装回原对象。
    """
    mutated_module = overlay.module_of(overlay.rel_of(path))
    assert mutated_module is not None, _name_of(path) + " 对应的模块还没被导入，改绑无处可落"
    with _R303Edit(path, old_lines, new_lines) as info, \
            r466.install_mutation(mutated_module, path, info.read_text()) as mutant:
        snapshots = [(target, attr, getattr(target, attr)) for target, attr in rebind]
        for target, attr, _before in snapshots:
            assert attr in mutant, (
                "窗内要改绑的 %s 不在本扇窗改动的顶层绑定里（实取 %s）：这把刀空转" % (attr, sorted(mutant)))
            setattr(target, attr, mutant[attr])
        try:
            yield info
        finally:
            for target, attr, before in snapshots:
                setattr(target, attr, before)


def _tracked_sha(path: Path) -> str:
    """盘上那枚被跟踪文件的 sha256：反证进出的字节凭据（本件对它只读）。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------- 判据①：truncated 的两半支各有一枚专件


def _alert_projection(client, username: str = FINANCE_MANAGER, **params) -> dict:
    response = _inbox(client, username, **params)
    assert response.status_code == 200, response.text
    return response.json()["sources"]["alert"]


def _assert_candidate_window_branch(client, username: str, scanned: int) -> dict:
    """左半支专件：候选数超过 SOURCE_WINDOW，而台账那一腿交回的行数还没撞页。"""
    window = sources_module.SOURCE_WINDOW
    leg_page = sources_module.ALERT_LEG_PAGE
    projection = _alert_projection(client, username)
    assert projection["scanned"] == scanned, "scanned 读数不对：" + str(projection["scanned"])
    assert projection["scanned"] < leg_page, (
        "铺量 " + str(projection["scanned"]) + " 已经撞上 ALERT_LEG_PAGE，左半支没被单独触发过"
    )
    assert projection["candidates"] == window, (
        "候选数该被窗口裁到 " + str(window) + "，实得 " + str(projection["candidates"])
    )
    assert projection["truncated"] is True, (
        "左半支没被记下：truncated=" + str(projection["truncated"])
        + " 而 candidates=" + str(projection["candidates"]) + " > SOURCE_WINDOW=" + str(window)
    )
    return projection


def _assert_alert_leg_page_branch(client) -> dict:
    """右半支专件：台账恰好交回 ALERT_LEG_PAGE 行，而候选数远在窗口之下。"""
    window = sources_module.SOURCE_WINDOW
    leg_page = sources_module.ALERT_LEG_PAGE
    projection = _alert_projection(client)
    assert projection["scanned"] == leg_page, (
        "scanned 应恰好撞满台账那一腿的页：期望 " + str(leg_page)
        + "，实得 " + str(projection["scanned"])
    )
    assert projection["candidates"] < window, (
        "候选数 " + str(projection["candidates"]) + " 必须小于 SOURCE_WINDOW=" + str(window)
        + "，否则这枚件分不清是左半支还是右半支在置位"
    )
    assert projection["truncated"] is True, (
        "右半支没被记下：truncated=" + str(projection["truncated"])
        + " 而 scanned=" + str(projection["scanned"]) + " >= ALERT_LEG_PAGE=" + str(leg_page)
    )
    return projection


def test_the_candidate_window_half_of_truncated_fires_on_its_own(client):
    """55 枚 open 告警：过 50 的窗口、不过 100 的台账页，能置上 truncated 的只有左半支。"""
    for index in range(55):
        _seed_alert(1200 + index, DEPT_FINANCE, minute=index)

    _assert_candidate_window_branch(client, FINANCE_MANAGER, 55)
    body = _inbox(client, FINANCE_MANAGER).json()
    assert body["total"] == sources_module.SOURCE_WINDOW
    assert body["is_exact"] is False


def test_the_alert_leg_page_half_of_truncated_fires_on_its_own(client):
    """100 行台账里只有 1 枚还没关闭：候选远在窗口之下，能置上 truncated 的只有右半支。

    R299 的窗口件从来没走到过这一支 —— 它铺到 55 枚就被 SOURCE_WINDOW 裁了。这一枚件刻意把 99
    枚做成 closed：它们仍然算台账交回的行（scanned 100），却不再算候选（candidates 1），两支因此
    被回执自己分开，不必有人去读代码推断。
    """
    for index in range(100):
        _seed_alert(1300 + index, DEPT_FINANCE, minute=index, status="closed")
    _seed_alert(1400, DEPT_FINANCE)  # 最后铺的那枚最新，落在台账那一腿的页内

    _assert_alert_leg_page_branch(client)
    body = _inbox(client, FINANCE_MANAGER).json()
    assert [row["id"] for row in body["notifications"]] == ["alert:1400"]
    assert body["total"] == 1
    assert body["is_exact"] is False, "只看得到一枚不等于整本账只有一枚：那一腿自己就截过页"


def test_the_two_halves_stay_distinguishable_from_the_receipt_alone(client):
    """两支同时在场的第三种铺量也要读得出来：scanned 撞页、候选也撞窗，两格各说各的数。"""
    for index in range(100):
        _seed_alert(1500 + index, DEPT_FINANCE, minute=index)
    for index in range(40):
        _seed_alert(1700 + index, DEPT_HR, minute=index)

    projection = _alert_projection(client)
    assert projection["scanned"] == sources_module.ALERT_LEG_PAGE
    assert projection["candidates"] == sources_module.SOURCE_WINDOW
    assert projection["truncated"] is True
    hr = _alert_projection(client, HR_MANAGER)
    assert (hr["scanned"], hr["candidates"], hr["truncated"]) == (40, 40, False), (
        "同一枚常量在另一个部门身上不该既说裁过又说没裁：这正是 is_exact 那格的下界语义"
    )


def test_every_name_the_receipt_sends_has_a_word_in_the_contract(client, document_store):
    """判据①与③的后半句：回执里有而契约里没有的字段名，一律算假话（不许只有实现有）。

    读侧与写侧各取一次真回执，字段名从响应里现攒、不抄清单：实现往回执上多添一格而契约没跟着
    长，这一枚就该红 —— 那正是「只有实现有、契约没有」的形状。
    """
    _seed_alert(1210, DEPT_FINANCE)
    body = _inbox(client, FINANCE_MANAGER).json()
    names = {"is_exact", "returned", "total", "unread_total", "unread_returned", "has_more"}
    for projection in body["sources"].values():
        names |= set(projection)

    _seed_mixed_batch(document_store)
    receipt = client.post(
        DISMISS_PATH,
        headers=_headers(FINANCE_MANAGER),
        json={"ids": [OWN_ALERT_ID, OTHER_APPROVAL_ID]},
    ).json()
    names |= set(receipt)
    for row in receipt["results"]:
        names |= set(row)
        names.add(str(row["reason"]))

    text = _contract_text()
    spelled = BACKTICK + "{}" + BACKTICK
    unmentioned = sorted(name for name in names if spelled.format(name) not in text)
    assert unmentioned == [], "这些回执字段在契约里逐字没有名字：" + ", ".join(unmentioned)


def test_the_contract_names_both_window_constants_with_their_live_values():
    """两半支的边界值必须由契约点名，而且点的是**代码里那两枚数**，不是散文抄来的旧数。"""
    text = _contract_text()
    window = sources_module.SOURCE_WINDOW
    leg_page = sources_module.ALERT_LEG_PAGE
    assert BACKTICK + "SOURCE_WINDOW" + BACKTICK + " (" + str(window) + ")" in text, (
        "契约没写 SOURCE_WINDOW=" + str(window)
    )
    assert BACKTICK + "ALERT_LEG_PAGE" + BACKTICK + " (" + str(leg_page) + ")" in text, (
        "契约没写 ALERT_LEG_PAGE=" + str(leg_page)
    )
    assert "keyset" in text, "契约要说明这一页是合并后内存切页、只有 offset 游标，没有 keyset"


# ------------------------------------------------------------ 判据③：部分成功不许退化成整批

OWN_ALERT_ID = "alert:1800"
OTHER_APPROVAL_ID = "approval:sess-r303-hr"
GHOST_ALERT_ID = "alert:9998"
OWN_DOCUMENT_ID = "document:r303-note.pdf#v1"
UNADDRESSABLE = (OTHER_APPROVAL_ID, GHOST_ALERT_ID)


def _seed_mixed_batch(document_store):
    _seed_alert(1800, DEPT_FINANCE)
    _park("sess-r303-hr", HR_MANAGER)
    document_store("r303-note.pdf", department=DEPT_FINANCE, owner=FINANCE_MANAGER)


def _assert_partial_success(client, ids) -> dict:
    """混批逐条给结论：越权的那一条自己吃 reason，其余照写、照计数，回执仍是 200。

    这一枚 helper 就是判据③的那枚不变量本身，反证 (c) 也在同一枚 helper 上跑红字 —— 不许另搓
    一份「只看状态码」的弱判，那等于把牙齿留在窗外。
    """
    response = client.post(DISMISS_PATH, headers=_headers(FINANCE_MANAGER), json={"ids": list(ids)})
    assert response.status_code == 200, (
        "一次越权的 id 不该把整批改写成一条错误：实得 "
        + str(response.status_code) + " " + response.text
    )
    receipt = response.json()
    verdicts = {row["id"]: row for row in receipt["results"]}
    assert receipt["requested"] == len(ids)
    refused = [one for one in ids if one in UNADDRESSABLE]
    accepted = [one for one in ids if one not in UNADDRESSABLE]
    for one in refused:
        verdict = verdicts[one]
        assert verdict["state"] is None, verdict
        assert verdict["changed"] is False, verdict
        assert verdict["reason"] == "notification_not_addressable", verdict
    for one in accepted:
        verdict = verdicts[one]
        assert verdict["state"] == "dismissed", verdict
        assert verdict["changed"] is True, verdict
        assert verdict["reason"] == "applied", verdict
    assert receipt["changed"] == len(accepted), (
        "changed 数的是真正写下的条数：期望 " + str(len(accepted))
        + "，实得 " + str(receipt["changed"])
    )
    stored = state_store.recipient_states(FINANCE_MANAGER)
    assert stored == {one: "dismissed" for one in accepted}, (
        "一条越权把其余几条一起回滚了：写侧退化成整批事务，实得 " + str(sorted(stored))
    )
    return receipt


@pytest.mark.parametrize(
    "ids",
    [
        [OWN_ALERT_ID, OTHER_APPROVAL_ID, OWN_DOCUMENT_ID],
        [OTHER_APPROVAL_ID, OWN_ALERT_ID, OWN_DOCUMENT_ID],
        [OWN_DOCUMENT_ID, GHOST_ALERT_ID, OWN_ALERT_ID],
    ],
)
def test_one_unaddressable_id_refuses_itself_and_leaves_its_neighbours_written(
    client, document_store, ids
):
    """被拒的那枚在前、在中、在后都得是同一个结论：只拒它自己。

    三种次序不是凑数：把闸门放在循环第一枚的实现只在一种次序下成立，先写两条再撞上越权的实现
    只在另一种次序下成立。逐条给结论的语义对次序无关，所以三种都判。
    """
    _seed_mixed_batch(document_store)
    _assert_partial_success(client, ids)

    body = _inbox(client, FINANCE_MANAGER).json()
    assert [row["id"] for row in body["notifications"]] == []
    assert (body["total"], body["unread_total"]) == (0, 0)
    # 别人的那一枚仍然在他自己的账上，一处都没被替别人写过。
    assert state_store.recipient_states(HR_MANAGER) == {}


def test_the_refusal_and_the_writes_share_one_response_and_one_receipt(client, document_store):
    """同一批里既有 applied 又有 notification_not_addressable：两格 reason 同框才是逐条语义。"""
    _seed_mixed_batch(document_store)

    receipt = _assert_partial_success(client, [OWN_ALERT_ID, OTHER_APPROVAL_ID])

    assert {row["reason"] for row in receipt["results"]} == {
        "applied",
        "notification_not_addressable",
    }
    read_back = _inbox(client, HR_MANAGER).json()
    assert OTHER_APPROVAL_ID in sorted(row["id"] for row in read_back["notifications"])


def test_marking_a_batch_read_keeps_the_same_per_id_semantics(client, document_store):
    """read 那枚动作与 dismiss 同一条写侧语义：一条越权不挡其余，且条目留在列表里。"""
    _seed_mixed_batch(document_store)
    ids = [OWN_ALERT_ID, OTHER_APPROVAL_ID, OWN_DOCUMENT_ID]

    response = client.post(READ_PATH, headers=_headers(FINANCE_MANAGER), json={"ids": ids})

    assert response.status_code == 200, response.text
    verdicts = {row["id"]: row for row in response.json()["results"]}
    assert verdicts[OWN_ALERT_ID]["state"] == "read"
    assert verdicts[OTHER_APPROVAL_ID]["reason"] == "notification_not_addressable"
    assert state_store.recipient_states(FINANCE_MANAGER) == {
        OWN_ALERT_ID: "read",
        OWN_DOCUMENT_ID: "read",
    }
    body = _inbox(client, FINANCE_MANAGER).json()
    assert (body["total"], body["unread_total"]) == (2, 0), "read 只降未读数，不把条目拿出去"


# --------------------------------------------------------------- 判据④：三源满载的一次耗时


def test_three_sources_at_their_window_caps_are_merged_paged_and_timed(client, document_store):
    """三本账同时铺到窗口上限，走离线 TestClient 现量一次读，并把毫秒数交回报告。

    这个数字是**钉口径**，不是真机读数：无 PostgreSQL、无宿主模型、无 HTTP 服务，三本账各自是
    内存腿或临时目录里的 JSON 账。它说明的是「合并后内存切页这条读路径在最坏的一页上花了多少
    毫秒」，不是生产延迟，也不进三档 SLO 那张表 —— 契约里那句同样的话由本件与它对判。
    """
    for index in range(55):
        _park("sess-r303-full-" + format(index, "03d"), FINANCE_MANAGER)
    for index in range(100):
        _seed_alert(2000 + index, DEPT_FINANCE, minute=index)
    for index in range(55):
        document_store("r303-full-" + format(index, "03d") + ".pdf",
                       department=DEPT_FINANCE, owner=FINANCE_MANAGER)

    warm = _inbox(client, FINANCE_MANAGER, limit=100)
    assert warm.status_code == 200, warm.text

    started = time.perf_counter()
    body = _inbox(client, FINANCE_MANAGER, limit=100).json()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    FULL_WINDOW_READ["ms"] = elapsed_ms

    window = sources_module.SOURCE_WINDOW
    assert body["total"] == 3 * window, "三源各裁到 " + str(window) + " 才对得上满载口径"
    assert body["returned"] == 100 and body["has_more"] is True
    assert body["unread_total"] == 3 * window
    for source, projection in sorted(body["sources"].items()):
        assert projection["candidates"] == window, source + " 没铺到窗口上限：" + str(projection)
        assert projection["truncated"] is True, source + " 这一格的满载读数不对：" + str(projection)
    assert body["is_exact"] is False
    assert elapsed_ms > 0.0
    print(
        "[R303·判据④] 三源满载一次读 = " + format(elapsed_ms, ".1f") + " ms（total="
        + str(body["total"]) + " returned=" + str(body["returned"])
        + "，离线钉口径，非真机读数）"
    )


# ------------------------------------------------------------------- 判据⑤：反证 (a) 与 (c)


def test_counter_evidence_a_deleting_the_leg_page_half_reddens_only_that_pin(client):
    """反证 (a)：把 truncated 的右半支删回只看窗口 ⇒ 右半支专件红，左半支专件仍绿。

    两支各红各绿才叫「两枚专件」；一删两支一起红，说明那两枚件在判同一句话。
    """
    for index in range(100):
        _seed_alert(1300 + index, DEPT_FINANCE, minute=index, status="closed")
    _seed_alert(1400, DEPT_FINANCE)
    for index in range(55):
        _seed_alert(2400 + index, DEPT_HR, minute=index)
    before = _tracked_sha(SOURCES_PY)

    with _mutate(
        SOURCES_PY,
        ["        truncated=truncated or len(rows) >= ALERT_LEG_PAGE,"],
        ["            truncated=truncated,"],
        rebind=[(inbox_module, "alert_candidates")],
    ) as info:
        with pytest.raises(AssertionError) as caught:
            _assert_alert_leg_page_branch(client)
        assert "truncated" in str(caught.value), str(caught.value)
        # 同一扇窗里左半支照旧成立：这枚件钉的不是同一句话。
        _assert_candidate_window_branch(client, HR_MANAGER, 55)

    assert info["restored"] is True
    assert _tracked_sha(SOURCES_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    _assert_alert_leg_page_branch(client)  # 出窗即复原：同一枚件重新为绿


#: 整批事务那枚反证的锚与变异：把逐条闸门换成「先全批复核，一枚越权就整条拒」。
_BATCH_GATE_ANCHOR = (
    "    results: list[dict[str, Any]] = []",
    "    changed_count = 0",
    "    try:",
)
_BATCH_GATE_MUTANT = (
    "    if not all([await can_address(principal, request, one) for one in ids]):",
    "        raise HTTPException(status_code=403, detail=NOT_ADDRESSABLE)",
    "    results: list[dict[str, Any]] = []",
    "    changed_count = 0",
    "    try:",
)


def test_counter_evidence_c_a_batch_rollback_breaks_the_partial_success_pin(client, document_store):
    """反证 (c)：把写侧换成整批闸门 ⇒ 判据③那枚不变量必须红，且盘上文件一个字节没动。"""
    _seed_mixed_batch(document_store)
    before = _tracked_sha(NOTIFICATIONS_PY)

    with _mutate(NOTIFICATIONS_PY, _BATCH_GATE_ANCHOR, _BATCH_GATE_MUTANT) as info:
        with pytest.raises(AssertionError) as caught:
            _assert_partial_success(client, [OWN_ALERT_ID, OTHER_APPROVAL_ID])
        assert "整批" in str(caught.value) or "403" in str(caught.value), str(caught.value)
        assert state_store.recipient_states(FINANCE_MANAGER) == {}, (
            "变异版把整条请求拒了，却还留下半行：那已经不是整批语义"
        )

    assert info["restored"] is True
    assert _tracked_sha(NOTIFICATIONS_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    # 出窗复跑：同一枚不变量重新为绿，证明红的来自变异而不是这扇窗留下的残渣。
    _seed_alert(1801, DEPT_FINANCE)
    _assert_partial_success(client, ["alert:1801", OTHER_APPROVAL_ID])


def test_the_counter_evidence_window_touches_no_tracked_file():
    """反证窗自己的纪律：三枚被改文件的 sha256 全程恒定，窗内也只有那一枚文件在窗里。

    🔴 R466 把窗内/窗尾两半都改写实了。旧写法只比对象身份（``is`` / ``is not``），而那两格读的
    正好是 ``execs_module = True`` 一次全模块重跑顺手造出来的形状：窗内 ``is`` 成立既证明不了
    变异在被执行，窗尾 ``is not`` 成立也只是因为旧码体被又跑了一遍、长出了第二枚同名对象——它
    甚至不是盘上那一枚。现在窗内比**码体指纹**（消费者指的函数必须等于影子副本那份码，且只准
    改动的那几枚绑定换身体），窗尾比**每一枚顶层把手的身份与码体都回到开窗前那一枚**。
    """
    targets = (SOURCES_PY, NOTIFICATIONS_PY, STATES_PY)
    before = {path: _tracked_sha(path) for path in targets}
    untouched = r466.live_view(sources_module)
    disk_text = SOURCES_PY.read_bytes().decode("utf-8")
    mutated = None

    with _mutate(
        SOURCES_PY,
        ["        truncated=truncated or len(rows) >= ALERT_LEG_PAGE,"],
        ["            truncated=truncated,"],
        rebind=[(inbox_module, "alert_candidates")],
    ) as info:
        assert overlay.open_windows() == (overlay.rel_of(SOURCES_PY),)
        shadow_codes = r466.compiled_view(info.read_text(), str(SOURCES_PY))
        mutated = r466.changed_bindings(disk_text, info.read_text())[0]
        assert mutated == ["alert_candidates"], "本扇窗改动的顶层绑定与锚点不符：实取 %s" % (mutated,)
        assert r466.fn_digest(inbox_module.alert_candidates) == shadow_codes["alert_candidates"], (
            "消费者跑的不是影子副本那份码：变异没被执行，这把刀是钝的"
        )
        churned = r466.identity_diff(untouched, r466.live_view(sources_module))
        assert set(churned) <= set(mutated), (
            "窗内活模块换了没被点名的把手身体：变异 exec 进了整份码体：%s" % (churned,)
        )

    assert {path: _tracked_sha(path) for path in targets} == before, "盘上被跟踪文件被动过一字节"
    assert inbox_module.alert_candidates is sources_module.alert_candidates, (
        "消费者没装回活模块那一枚：出窗没还原"
    )
    assert r466.diff_view(untouched, r466.live_view(sources_module)) == [], (
        "出窗后 sources 还有码体是变异的：反证窗把变异漏在活模块上了"
    )
    assert r466.identity_diff(untouched, r466.live_view(sources_module)) == [], (
        "出窗后 sources 还有顶层把手没回到开窗前那一枚：整份码体被重跑过"
    )

# ------------------------------------------------- 判据④的口径句：数字会漂，那句警告不许漂


def test_the_contract_keeps_the_millisecond_reading_labeled_as_a_test_double():
    """判据④的红线：毫秒数可以随机器漂，「这是离线钉口径、不是真机读数」不许从契约里消失。

    契约一旦丢了这一句，下一班就会把测试替身的读数当性能承诺写进 SLO 那张表 —— 所以钉的是措辞
    本身，而不是某个数字。
    """
    text = _contract_text()
    assert "not a production reading" in text, (
        "契约不再声明这一格是钉口径：满载读数就会被读成生产性能"
    )
    assert "test-double" in text, "契约要明写这是测试替身上的读数"
    assert "no keyset cursor" in text, "契约要说明这一页只有 offset 游标、合并后内存切页"
    assert "Three-Tier SLO Contract" in text, "要同时说清这一格不进那张真机 SLO 表"
