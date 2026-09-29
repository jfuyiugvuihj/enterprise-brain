# -*- coding: utf-8 -*-
"""R388 · 通知**读腿**的两张脸：「这一格问不出」不等于「这个人什么都没读过」。

症状（总控在基点 `b498c88` 现读到行号，本件自己复量一遍）：生命周期那本账活在 PostgreSQL 上，
写腿由 R376 治过（`states.py::_require_writable_store` 在「生产 + 库不在位」那一格拒写并抛具名
错，出口翻 503），而读腿一字未治 —— `recipient_states`（`:131`）与 `read_state`（`:157`）在同一
格照样回落进程内那本 `_ROWS`，于是 `inbox.py:100` 拿到 `{}`，`:105` 那句
`state = stored.get(item.id) or STATE_UNREAD` 把**每一条**通知判成未读，`unread_total`（`:112`）
跟着虚高。员工明明读过、明明划掉过，徽标还是满的。这与业主最反感的那句病是同一句：把「问不出」
说成「没有」—— 这一次是反过来说成「全是新的」。

四格判据，逐格有钉：

- 甲 读腿两张脸分开。生产而库不在位：`recipient_states` 交回 None（问不出），不再交回那本内存
  空账；开发/裸机一字不动，那本账在那里仍是合法后端。
- 乙 列表照读（与 R373「那一格不供数、别的一格照答」同口径）。整页 503 是本单明确不要的形状：
  它替一格问不出把文档腿、审批腿一起打死。缺席登记在新添的 `state_ledger` 那一格，形状与
  `sources` 那台台账同族（`included` / `reason_code` / 两枚计数），`reason_code` 只取在册的那两枚。
- 丙 计数不脏。`unread_total` / `unread_returned` 一枚都不把未知算成未读；`?state=unread` 那一页
  也不收数不清的条目。0 说的是「数不清」，而那件事由 `state_ledger` 那一格说出去。
- 丁 别人的腿不许跟着动。`apply_state`（写腿）与 `can_address`（可寻址性）今天的行为逐格保持；
  缺表那一格照旧整页 503（`tests/test_r299_notification_inbox.py` 钉过的旧脸，不许被缺席并走）。

全部离线：不起服务、不连库、不打模型、不写 chroma_db/。反证刀落在 `tests/_temp_edit_overlay.py`
那台影子根里，被跟踪文件全程只读，进出各量一次 sha256。
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import alerts as alerts_api
from app.common.auth import create_token
from app.common.authorization import principal_from_request
from app.documents import catalog
from app.main import app
from app.notifications import inbox as inbox_module
from app.notifications import sources as sources_module
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

REPO = Path(__file__).resolve().parents[1]
#: 本单的记名锚点（与 r366 / r373 同一手法）：与现场读数比等号的是它，不是「工作树 vs HEAD」。
BASE = "b498c88"

STATES_PY = REPO / "app" / "notifications" / "states.py"
INBOX_PY = REPO / "app" / "notifications" / "inbox.py"
CONTRACTS_PY = REPO / "app" / "notifications" / "contracts.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
BELL_VUE = REPO / "frontend" / "src" / "components" / "NotificationBell.vue"

INBOX_PATH = "/api/v1/notifications"
READ_PATH = INBOX_PATH + "/read"
DISMISS_PATH = INBOX_PATH + "/dismiss"

#: 两枚在册取值，一枚都不新造：'ok' 是 sources.py::SourceBundle 的 reason_code 缺省，
#: storage_unavailable 是 alerts / dashboard / notifications 三处出口今天都在吐的那一枚。
ANSWERED_CODE = "ok"
STORAGE_CODE = "storage_unavailable"

#: 本单那一节的标题（判「追加过且只追加一次」）。
SECTION_HEADING = (
    "## A read that cannot be answered must not be read as an empty ledger (2026-09-27, R388)"
)

DEPT = "r388-finance"
OWNER = "r388-owner"
STRANGER = "r388-stranger"
SESSION = "r388-session-1"
THEIR_SESSION = "r388-session-2"
ALERT_ID = 8801
DOCUMENT_NAME = "r388-note.pdf"
DOCUMENT_ID = "document:" + DOCUMENT_NAME + "#v1"
APPROVAL_ID = "approval:" + SESSION
ALERT_NOTIFICATION_ID = "alert:" + str(ALERT_ID)
#: 生产而库不在位那一格该长的形状（逐格与生产者对平，不靠注释维持）。
ABSENT_CELL = {
    "included": False,
    "reason_code": STORAGE_CODE,
    "unknown_total": 2,
    "unknown_returned": 2,
}
ANSWERED_CELL = {
    "included": True,
    "reason_code": ANSWERED_CODE,
    "unknown_total": 0,
    "unknown_returned": 0,
}


def _account(username: str, role: str = "manager") -> dict:
    return {"id": username, "username": username, "role": role, "department": DEPT}


ACCOUNTS = {OWNER: _account(OWNER), STRANGER: _account(STRANGER, role="staff")}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """两枚账号进鉴权中间件真正用的那一次查询；宿主真起 PG 也不许分掉读数。"""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    monkeypatch.setattr(auth, "_db_ready", False)


@pytest.fixture(autouse=True)
def offline_legs(monkeypatch):
    """三本源账加生命周期账全钉在内存形状，每枚用例换新账本（防跨用例泄漏）。"""
    monkeypatch.setattr(hitl_store, "_MEM_ROWS", {})
    monkeypatch.setattr(hitl_store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_api, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts_api, "_database_available", lambda: False)
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: False)


@pytest.fixture()
def document_store(monkeypatch, tmp_path):
    """文档腿用真的离线 catalog，落点搬进 tmp_path（与 r299 / r366 同一间屋子）。"""
    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root))

    def add(filename: str, *, owner: str) -> str:
        stored = root / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本" + chr(10) + "100 80" + chr(10), encoding="utf-8")
        catalog.record_local_document_version(
            filename, 1, DEPT, str(stored), 1, owner_id=owner, index_status="indexed",
        )
        return filename

    return add


@pytest.fixture()
def world(document_store):
    """三腿各有一条、都归 OWNER：一轮挂起、一枚开着的告警、一篇进了索引的文档。"""
    hitl_store.record_awaiting(SESSION, OWNER, ["chart"], request_id="req-r388")
    hitl_store.record_awaiting(THEIR_SESSION, STRANGER, ["chart"], request_id="req-r388-theirs")
    alerts_api._MEM_ALERTS.append(
        {
            "id": ALERT_ID,
            "rule_id": 1,
            "message": "R388 营收跌破阈值",
            "read": False,
            "department": DEPT,
            "created_at": "2026-09-27T09:00:00+08:00",
        }
    )
    document_store(DOCUMENT_NAME, owner=OWNER)
    return SimpleNamespace(alert=ALERT_ID, session=SESSION, document=DOCUMENT_NAME)


@pytest.fixture()
def client():
    return TestClient(app)


def _headers(username: str = OWNER) -> dict:
    return {"Authorization": "Bearer " + create_token(username)}


def _produce(monkeypatch) -> None:
    """客户机那一格：`APP_ENV=production` 而库不在位 —— 本单治的就是这一格。"""
    monkeypatch.setenv("APP_ENV", "production")


def _develop(monkeypatch) -> None:
    """开发/裸机那一格：同一枚「库不在」，环境不是生产 —— 闸在这里不许咬。"""
    monkeypatch.setenv("APP_ENV", "development")


def _inbox(client, username: str = OWNER, **params):
    return client.get(INBOX_PATH, headers=_headers(username), params=params)


def _post(client, path: str, ids, username: str = OWNER):
    return client.post(path, headers=_headers(username), json={"ids": list(ids)})


def _ids(body: dict) -> list:
    return sorted(row["id"] for row in body["notifications"])


def _state_column(body: dict) -> list:
    return [row["state"] for row in body["notifications"]]


def _source_cells(body: dict, source: str) -> list:
    """那一腿的行，逐格去掉生命周期那一列：源账给的东西与本单无关。"""
    return [
        {key: value for key, value in row.items() if key != "state"}
        for row in body["notifications"]
        if row["source_type"] == source
    ]


def _request(username: str) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(principal=None, username=username), headers={})


def _principal(username: str):
    request = _request(username)
    principal = principal_from_request(request)
    assert principal is not None, username + " 解析不出 principal，本件的直调没有意义"
    return principal, request


def _git_show(revision: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO), "show", revision + ":" + relative],
        capture_output=True, check=True,
    ).stdout


def _as_blob_text(raw: bytes) -> str:
    """一律落到 git blob 那一层（LF）比对：本仓 core.autocrlf=true，两个形状不许混着比。"""
    return raw.decode("utf-8").replace(chr(13) + chr(10), chr(10))


def _tracked_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _function(tree, name: str):
    found = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, name + " 应当恰有一枚定义，实测 " + str(len(found))
    return found[0]


def _call_text(node) -> list:
    return [ast.unparse(call) for call in ast.walk(node) if isinstance(call, ast.Call)]


class _Result:
    """psycopg dict_row 的最小把手：读不到就是 None / 空列表，不替谁说谎。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeStateTable:
    """`notification_states` 的替身：只被教过四条语句，没教过的当场抛。

    什么都答的桩会把「这一腿根本没被执行」糊成一枚绿钉（r376 同一条纪律）。
    """

    TABLE = "notification_states"

    def __init__(self):
        self.rows = {}
        self.log = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def commit(self):
        self.commits += 1

    @property
    def write_statements(self):
        return [entry for entry in self.log if entry[0].lower().startswith("insert")]

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        bound = tuple(params or ())
        self.log.append((statement, bound))
        head = statement.lower()
        if head.startswith("select to_regclass"):
            return _Result([{"table_name": self.TABLE}])
        if head.startswith("select notification_id, state from"):
            return _Result(
                [
                    {"notification_id": key[1], "state": row["state"]}
                    for key, row in self.rows.items()
                    if key[0] == bound[0]
                ]
            )
        if head.startswith("select state from"):
            row = self.rows.get(bound)
            return _Result([{"state": row["state"]}] if row else [])
        if head.startswith("insert into"):
            identifier, person, state, _recorded, _updated = bound
            self.rows[(person, identifier)] = {"state": state}
            return _Result([])
        raise AssertionError("替身没被教过这条语句，不替谁说谎：" + statement)


class _AbsentTableConnection:
    """PG 起着而 0016 没跑：`to_regclass` 答 NULL，其余语句一概不接。

    「一概不接」是这枚替身的一部分：谁把那道检表闸绕过、拿这张不存在的表去读行，这里当场抛
    —— 缺表被洗成空账正是本单不许并走的那张脸（刀戊量的就是它）。
    """

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        self.statements.append(statement)
        if statement.lower().startswith("select to_regclass"):
            return _Result([{"table_name": None}])
        raise AssertionError("缺表的连接不该被读到行：那道检表闸被绕过了 " + statement)


def _wire_pg(monkeypatch, table):
    """把生命周期那一层接到「库在位」的世界上：三本源账仍走内存，与基点同形。"""
    monkeypatch.setattr(state_store, "_database_available", lambda: True)
    monkeypatch.setattr(state_store, "_conn", lambda: table)
    return table


# =============================================== 甲 · 读腿两张脸（存储层直调，不经 HTTP）


def test_production_without_a_store_the_read_leg_says_it_cannot_answer(monkeypatch, world):
    """客户机那一格：recipient_states 交回 None，而不是那本恒为空的进程内账。"""
    _produce(monkeypatch)

    assert state_store.recipient_states(OWNER) is None, "读腿还在交回内存那本账"
    assert state_store._ROWS == {}, "读腿顺手往内存里写了一行"


def test_the_empty_ledger_and_the_absent_ledger_are_two_different_words(monkeypatch, world):
    """{} 与 None 是两句话：前者「查过了，确实没有行」，后者「这本账压根没答」。

    两枚世界只差 `APP_ENV`，同一枚收件人、同一本空账 —— 基点上它们逐字同形，那正是本单治的格。
    """
    _develop(monkeypatch)
    answered = state_store.recipient_states(OWNER)
    _produce(monkeypatch)
    silent = state_store.recipient_states(OWNER)

    assert answered == {}, "开发那一格今天不该改：那本内存账在那里是合法后端"
    assert silent is None, "问不出被洗成了「没有」"
    assert (answered is None) != (silent is None), "两枚世界长出了同一张脸"


def test_an_empty_recipient_still_answers_an_empty_dict(monkeypatch, world):
    """空收件人不是「问不出」：那一格从来没有账可问，交 {} 是它本来的语义。"""
    _produce(monkeypatch)

    assert state_store.recipient_states("") == {}
    assert state_store.recipient_states(None) == {}


def test_read_state_refuses_the_production_cell_instead_of_calling_it_unread(monkeypatch, world):
    """单枚读那一格不许把「问不出」兼成 None —— None 在这儿的意思是「没行」，即未读。"""
    _produce(monkeypatch)

    with pytest.raises(state_store.NotificationStateStoreMissing):
        state_store.read_state(OWNER, APPROVAL_ID)
    assert state_store._ROWS == {}


def test_read_state_in_development_still_answers_none_for_no_row(monkeypatch, world):
    """开发那一格一字未动：没有行就是未读，与基点同一张脸。"""
    _develop(monkeypatch)

    assert state_store.read_state(OWNER, APPROVAL_ID) is None
    state_store.apply_state(OWNER, APPROVAL_ID, "read")
    assert state_store.read_state(OWNER, APPROVAL_ID) == "read"


def test_no_connection_is_opened_on_the_way_to_answering_absence(monkeypatch, world):
    """答「问不出」那一格不许伸手碰库：_conn 被碰一次就是当场红（r376 同一条口径）。"""
    _produce(monkeypatch)

    def _boom():
        raise AssertionError("答『问不出』却去连了库")

    monkeypatch.setattr(state_store, "_conn", _boom)
    assert state_store.recipient_states(OWNER) is None
    with pytest.raises(state_store.NotificationStateStoreMissing):
        state_store.read_state(OWNER, APPROVAL_ID)


def test_a_ready_store_reads_its_rows_verbatim(monkeypatch, world):
    """PG 在位时读腿一个字都没变：整份读回来、按 notification_id 索引。"""
    _develop(monkeypatch)
    table = _wire_pg(monkeypatch, _FakeStateTable())
    table.rows[(OWNER, APPROVAL_ID)] = {"state": "read"}
    table.rows[(STRANGER, APPROVAL_ID)] = {"state": "dismissed"}

    assert state_store.recipient_states(OWNER) == {APPROVAL_ID: "read"}
    assert state_store.read_state(OWNER, APPROVAL_ID) == "read"


def test_a_ready_store_with_no_table_still_raises_the_named_error(monkeypatch, world):
    """库起着而 0016 没跑：那一格仍是具名错，不是 None —— 缺表与无库是两枚不同的问题。"""
    _develop(monkeypatch)
    monkeypatch.setattr(state_store, "_database_available", lambda: True)
    monkeypatch.setattr(state_store, "_conn", lambda: _AbsentTableConnection())

    with pytest.raises(state_store.NotificationStateStoreMissing):
        state_store.recipient_states(OWNER)
    with pytest.raises(state_store.NotificationStateStoreMissing):
        state_store.read_state(OWNER, APPROVAL_ID)


# ================================================ 乙 · 列表照读，缺席那一格显式登记（出口级）


def test_the_inbox_still_lists_every_leg_that_answers(monkeypatch, client, world):
    """判据乙的正身：客户机上整页仍 200，答得出的腿一条不少 —— 不许整页 503。"""
    _produce(monkeypatch)

    response = _inbox(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _ids(body) == [APPROVAL_ID, DOCUMENT_ID], "照答的腿被那一格问不出一起打死了"
    assert body["total"] == body["returned"] == 2
    assert body["has_more"] is False


def test_the_state_cell_declares_itself_absent_with_a_ratified_reason(monkeypatch, client, world):
    """state_ledger 那一格的读数：没答、为什么没答、数不清几条，各说各的。"""
    _produce(monkeypatch)

    body = _inbox(client).json()

    assert body["state_ledger"] == ABSENT_CELL, "缺席那一格的形状不对：" + str(body["state_ledger"])
    assert body["state_ledger"]["reason_code"] == sources_module.STORAGE_UNAVAILABLE


def test_every_row_answers_null_rather_than_unread(monkeypatch, client, world):
    """逐条那一格交回 null（答不上），不再冒充 unread（有依据说它没读过）。"""
    _produce(monkeypatch)

    body = _inbox(client).json()

    assert _state_column(body) == [None, None], str(_state_column(body))


def test_the_answering_legs_are_identical_across_the_two_worlds(monkeypatch, client, world):
    """判据乙的下半句：状态这一格变了脸，源账那几列一个字符都不许多、不许变。"""
    _develop(monkeypatch)
    dev = _inbox(client).json()
    _produce(monkeypatch)
    prod = _inbox(client).json()

    assert sorted(prod["sources"]) == sorted(dev["sources"]) == ["alert", "approval", "document"]
    for source in ("approval", "document"):
        assert prod["sources"][source] == dev["sources"][source], source
        assert _source_cells(prod, source) == _source_cells(dev, source), source
    # 开发那一格三腿全答（生产无库时告警那一腿本来就不供数，那是 R373 的旧账），故三行全未读；
    # 唯一该不同的两格仍是：逐条的 state 与状态台账自己。
    assert _state_column(dev) == ["unread", "unread", "unread"], str(_state_column(dev))
    assert dev["state_ledger"] == ANSWERED_CELL, str(dev["state_ledger"])


def test_the_new_cell_is_isomorphic_with_the_sources_projections(monkeypatch, client, world):
    """形状与 sources 同族：included / reason_code 两枚共有键逐枚同名同义。"""
    _produce(monkeypatch)

    body = _inbox(client).json()
    shared = {"included", "reason_code"}

    assert shared <= set(body["state_ledger"]), str(sorted(body["state_ledger"]))
    for projection in body["sources"].values():
        assert shared <= set(projection)
    assert isinstance(body["state_ledger"]["included"], bool)
    assert isinstance(body["state_ledger"]["unknown_total"], int)
    assert isinstance(body["state_ledger"]["unknown_returned"], int)


def test_the_state_ledger_roster_is_exactly_four_keys(monkeypatch, client, world):
    """那一格只有四枚键：多一枚就是第二本账，少一枚就少一句可核对的话。"""
    _produce(monkeypatch)

    body = _inbox(client).json()

    assert set(body["state_ledger"]) == {
        "included", "reason_code", "unknown_total", "unknown_returned",
    }, str(sorted(body["state_ledger"]))


def test_no_reason_word_outside_the_register_is_ever_emitted(monkeypatch, client, world):
    """零新增码：两枚世界 × 四格台账交回的 reason_code 全落在在册那两枚里。"""
    seen = set()
    for shift in (_develop, _produce):
        shift(monkeypatch)
        body = _inbox(client).json()
        seen.add(body["state_ledger"]["reason_code"])
        for projection in body["sources"].values():
            seen.add(projection["reason_code"])

    assert seen <= {ANSWERED_CODE, STORAGE_CODE}, "交回了词表外的 reason_code：" + str(sorted(seen))


def test_the_reason_words_are_the_ones_the_repository_already_has(monkeypatch, client, world):
    """两枚取值都取自现成在册码：'ok' 是那枚 dataclass 的缺省，另一枚是三枚源腿早就在用的那一枚在册码'。"""
    _develop(monkeypatch)
    answered = _inbox(client).json()["state_ledger"]["reason_code"]
    _produce(monkeypatch)
    silent = _inbox(client).json()["state_ledger"]["reason_code"]

    assert answered == sources_module.SourceBundle(source_type="alert").reason_code, (
        "答上了那一格与 sources 的缺省不同词：那是第二套说法"
    )
    assert silent == inbox_module.STORAGE_UNAVAILABLE == sources_module.STORAGE_UNAVAILABLE
    assert answered != silent


# ======================================================= 丙 · 两枚未读计数一枚都不脏


def test_unknown_states_do_not_enter_the_unread_counts(monkeypatch, client, world):
    """判据丙正身：unread_total / unread_returned 不把未知算成未读，差额记在 unknown 两格。"""
    _produce(monkeypatch)

    body = _inbox(client).json()

    assert (body["total"], body["returned"]) == (2, 2)
    assert (body["unread_total"], body["unread_returned"]) == (0, 0), "徽标虚高就是这一格"
    assert body["unread_total"] + body["state_ledger"]["unknown_total"] == body["total"]
    assert body["unread_returned"] + body["state_ledger"]["unknown_returned"] == body["returned"]


def test_the_two_worlds_differ_only_in_the_lifecycle_face(monkeypatch, client, world):
    """两世界只差状态那一格：条目一条不少，未读少的正好是数不清的那几条。"""
    _develop(monkeypatch)
    dev = _inbox(client).json()
    _produce(monkeypatch)
    prod = _inbox(client).json()

    # 两世界的条目本来只差告警那一腿（生产无库时它不供数，R373 旧账，与本单无关）；剩下的差
    # 只有状态这一格：dev 三行全有依据说是未读，prod 两行全数不清，而数不清一枚都不进未读。
    assert _ids(dev) == [ALERT_NOTIFICATION_ID, APPROVAL_ID, DOCUMENT_ID], str(_ids(dev))
    assert _ids(prod) == [APPROVAL_ID, DOCUMENT_ID], str(_ids(prod))
    for source in ("approval", "document"):
        assert _source_cells(prod, source) == _source_cells(dev, source), source
    assert dev["state_ledger"]["unknown_total"] == 0
    assert prod["state_ledger"]["unknown_total"] == prod["total"]
    assert (dev["total"], dev["unread_total"]) == (3, 3)
    assert (prod["total"], prod["unread_total"]) == (2, 0)
    for body in (dev, prod):
        assert body["unread_total"] + body["state_ledger"]["unknown_total"] == body["total"]
        assert body["unread_returned"] + body["state_ledger"]["unknown_returned"] == body["returned"]


def test_the_unread_filter_page_refuses_rows_it_cannot_state(monkeypatch, client, world):
    """`?state=unread` 问的是「有依据说它没读过」：数不清的条目一枚都不进那一页。"""
    _produce(monkeypatch)

    unread = _inbox(client, state="unread").json()
    read = _inbox(client, state="read").json()
    everything = _inbox(client, state="all").json()

    assert unread["notifications"] == [] and unread["returned"] == 0
    assert unread["total"] == everything["total"] == 2, "条目本身不许被过滤那一格裁掉"
    assert read["notifications"] == []
    # 那一页一条都没有，所以 returned 那一格跟着归零；total 仍说全集的数不清条数。
    assert unread["state_ledger"] == dict(ABSENT_CELL, unknown_returned=0), str(unread["state_ledger"])
    assert unread["state_ledger"]["unknown_total"] == ABSENT_CELL["unknown_total"]
    assert everything["state_ledger"] == ABSENT_CELL


def test_the_development_page_and_counts_are_exactly_the_base_face(monkeypatch, client, world):
    """开发/裸机一字不动：整页、逐条 state、两枚计数与基点逐格同形。"""
    _develop(monkeypatch)

    body = _inbox(client).json()

    assert _ids(body) == [ALERT_NOTIFICATION_ID, APPROVAL_ID, DOCUMENT_ID], str(_ids(body))
    assert _state_column(body) == ["unread", "unread", "unread"], str(_state_column(body))
    assert (body["total"], body["unread_total"]) == (3, 3)
    assert (body["returned"], body["unread_returned"]) == (3, 3)
    assert body["state_ledger"] == ANSWERED_CELL


def test_a_read_mark_in_development_still_drops_the_unread_count(monkeypatch, client, world):
    """那本内存账仍会动：标一次已读 ⇒ 未读 2→1、逐条 state 变 read、条目仍留在列表里。"""
    _develop(monkeypatch)
    before = _inbox(client).json()
    marked = _post(client, READ_PATH, [APPROVAL_ID])
    after = _inbox(client).json()

    assert before["unread_total"] == 3
    assert marked.status_code == 200, marked.text
    assert marked.json()["results"][0]["changed"] is True
    assert after["unread_total"] == 2
    assert dict(zip(_ids(after), _state_column(after)))[APPROVAL_ID] == "read"
    assert after["state_ledger"] == ANSWERED_CELL


def test_a_dismissal_in_development_still_leaves_the_list(monkeypatch, client, world):
    """「划掉的那一条不进列表、也不进两枚计数」这句老语义在开发那一格一字未动。"""
    _develop(monkeypatch)

    dismissed = _post(client, DISMISS_PATH, [APPROVAL_ID])
    body = _inbox(client).json()

    assert dismissed.status_code == 200, dismissed.text
    assert _ids(body) == [ALERT_NOTIFICATION_ID, DOCUMENT_ID], str(_ids(body))
    assert (body["total"], body["unread_total"]) == (2, 2)


def test_switching_worlds_leaves_no_stale_read_state(monkeypatch, client, world):
    """开发先标一枚已读、再换到生产那一格：未知一枚都不进未读，也不许留着上一轮的读数。"""
    _develop(monkeypatch)
    _post(client, READ_PATH, [APPROVAL_ID])
    _produce(monkeypatch)

    body = _inbox(client).json()

    assert _state_column(body) == [None, None], "换了世界还认得上一轮的已读：那是第二本账"
    assert body["unread_total"] == 0
    assert body["state_ledger"]["unknown_total"] == 2


# ================================== 丁 · 别人的腿不许跟着动（apply_state / can_address / 缺表）


def test_apply_state_in_development_is_unchanged_down_to_the_receipt(monkeypatch, client, world):
    """写腿（states.py:174）那一条腿今天的行为一字未改：回执四枚键、幂等、内存落行。"""
    _develop(monkeypatch)

    first = _post(client, READ_PATH, [APPROVAL_ID]).json()
    second = _post(client, READ_PATH, [APPROVAL_ID]).json()

    assert first == {
        "action": "read", "requested": 1, "changed": 1,
        "results": [{"id": APPROVAL_ID, "state": "read", "changed": True, "reason": "applied"}],
    }
    assert second["results"][0]["changed"] is False, "幂等那一格被本单顺手改了"
    assert state_store.recipient_states(OWNER) == {APPROVAL_ID: "read"}


def test_apply_state_in_production_without_a_store_still_refuses(monkeypatch, client, world):
    """R376 那一刀的形状逐格保持：503 storage_unavailable，内存腿一个字不写。"""
    _produce(monkeypatch)

    response = _post(client, DISMISS_PATH, [APPROVAL_ID])

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert state_store._ROWS == {}
    assert state_store.recipient_states(OWNER) is None


def test_apply_state_against_a_ready_store_still_writes_exactly_one_row(monkeypatch, client, world):
    """库在位那条腿一字未动：一次 INSERT、一次 commit、下一读就认得它。"""
    _develop(monkeypatch)
    table = _wire_pg(monkeypatch, _FakeStateTable())

    response = _post(client, READ_PATH, [APPROVAL_ID])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0] == {
        "id": APPROVAL_ID, "state": "read", "changed": True, "reason": "applied",
    }
    assert len(table.write_statements) == 1
    assert table.commits == 1
    assert table.rows[(OWNER, APPROVAL_ID)] == {"state": "read"}
    body = _inbox(client).json()
    assert dict(zip(_ids(body), _state_column(body)))[APPROVAL_ID] == "read"
    assert body["state_ledger"] == ANSWERED_CELL


def test_a_missing_migration_still_refuses_the_whole_page_with_503(monkeypatch, client, world):
    """缺表那张脸不许被本单的缺席并走：库起着而 0016 没跑 ⇒ 整页 503（r299 钉过的旧账）。"""
    _produce(monkeypatch)
    monkeypatch.setattr(state_store, "_database_available", lambda: True)
    monkeypatch.setattr(state_store, "_conn", lambda: _AbsentTableConnection())

    response = _inbox(client)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}


def test_an_unrelated_error_in_the_lifecycle_leg_stays_a_bug(monkeypatch, client, world):
    """503 与「缺席」都只接各自那一种脸：别的异常既不许被洗成缺席，也不许被洗成存储错。"""
    _develop(monkeypatch)
    monkeypatch.setattr(state_store, "_database_available", lambda: True)

    def _broken():
        raise RuntimeError("connection pool exhausted")

    monkeypatch.setattr(state_store, "_conn", _broken)

    with pytest.raises(RuntimeError, match="connection pool exhausted"):
        _inbox(client)


@pytest.mark.parametrize(
    "identifier,expected",
    [(APPROVAL_ID, True), ("approval:" + THEIR_SESSION, False), ("alert:999999", False)],
    ids=["own_approval", "someone_elses_approval", "ghost_alert"],
)
def test_can_address_still_answers_from_the_three_ledgers(monkeypatch, world, identifier, expected):
    """可寻址性那一腿（inbox.py:139）一字未动：答案永远来自那三本账自己的读路径。"""
    _develop(monkeypatch)
    principal, request = _principal(OWNER)

    verdict = asyncio.run(inbox_module.can_address(principal, request, identifier))

    assert verdict is expected, identifier + " 的判定被本单改过：" + str(verdict)


@pytest.mark.parametrize("shift", [_produce, _develop], ids=["production", "development"])
def test_can_address_does_not_consult_the_lifecycle_ledger(monkeypatch, world, shift):
    """状态这本账答不答得上，与「这一枚你管不管得着」是两件事：两世界同一句回答。"""
    shift(monkeypatch)
    principal, request = _principal(OWNER)
    seen = []
    real = state_store.recipient_states

    def _spy(recipient):
        seen.append(recipient)
        return real(recipient)

    monkeypatch.setattr(state_store, "recipient_states", _spy)

    assert asyncio.run(inbox_module.can_address(principal, request, APPROVAL_ID)) is True
    refused = asyncio.run(
        inbox_module.can_address(principal, request, "approval:" + THEIR_SESSION)
    )
    assert refused is False
    assert seen == [], "can_address 读了生命周期那本账：那是把状态账当成了权限来源"


# ================================== 戊 · 形状：一把尺、零新增码、出口一字未改、契约纯追加


def test_the_read_legs_borrow_the_ruler_the_write_gate_already_borrowed():
    """三枚调用点各借一次那把尺：全文件三枚、零枚定义、零枚自算 APP_ENV。"""
    tree = _tree(STATES_PY)
    source = STATES_PY.read_text(encoding="utf-8")
    borrowed = "_is_production_environment()"

    per_function = {
        name: sum(borrowed in call for call in _call_text(_function(tree, name)))
        for name in ("_require_writable_store", "recipient_states", "read_state")
    }
    assert per_function == {
        "_require_writable_store": 1, "recipient_states": 1, "read_state": 1,
    }, "读腿的借尺次数漂了：" + str(per_function)
    # 只数真调用（AST 里的 Call 节点）：docstring 里提它一句也是提，按字符数会把注释算成调用
    call_sites = [
        text
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for text in _call_text(node)
        if borrowed in text
    ]
    assert len(call_sites) == 3, "states.py 里这把尺被真调用了 " + str(len(call_sites)) + " 次"
    assert "def _is_production_environment" not in source, "states.py 长出了第二把尺"
    assert "getenv(\"APP_ENV\")" not in source, "states.py 自己 getenv 起 APP_ENV 来了"
    assert "_PRODUCTION_ENVIRONMENTS" not in source, "把别人那把尺的词表抄一遍，也是第二把"


def test_the_lifecycle_leg_reads_the_store_probe_once_and_never_a_second_time():
    """`_database_available` 仍是 states.py 唯一那枚库探针，`_db_ready` 读者仍是一枚。"""
    tree = _tree(STATES_PY)
    source = STATES_PY.read_text(encoding="utf-8")
    probes = [
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_database_available"
    ]

    assert probes == ["_database_available"], "库里在不在被算了第二遍"
    readers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "_db_ready":
            readers.add(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr"}
            and any(isinstance(a, ast.Constant) and a.value == "_db_ready" for a in node.args[1:2])
        ):
            readers.add(node.lineno)

    assert len(readers) == 1, (
        "_db_ready 在 states.py 有了第二枚读者：" + str(sorted(readers))
    )


def test_inbox_py_never_asks_itself_whether_the_store_is_there():
    """判「答没答」的信号只能来自那本账交回的值：读模型里不许长出第二枚探针（r366 同尺）。"""
    source = INBOX_PY.read_text(encoding="utf-8")

    for probe in ("_db_ready", "_database_available", "_is_production_environment", "APP_ENV"):
        assert probe not in source, "inbox.py 自己算了一遍 " + probe


def test_the_storage_layer_still_raises_no_http_exception():
    """HTTP 那层的话由出口说：本单没让存储层自己吐码，也没新接一枚 except。"""
    source = STATES_PY.read_text(encoding="utf-8")

    assert "HTTPException" not in source
    assert "detail=" not in source
    handlers = []
    for path in sorted((REPO / "app").rglob("*.py")):
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.ExceptHandler) or node.type is None:
                continue
            types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for item in types:
                if getattr(item, "attr", "") == "NotificationStateStoreMissing":
                    handlers.append(path.relative_to(REPO).as_posix())
    assert handlers == ["app/api/v1/notifications.py", "app/api/v1/notifications.py"], str(handlers)


def test_unknown_is_a_face_not_a_fourth_state_word():
    """STATE_UNKNOWN 是 JSON null，不许混进那两枚封闭集（0016 的 CHECK 也不认它）。"""
    from app.notifications import contracts

    assert contracts.STATE_UNKNOWN is None
    assert contracts.STATE_UNKNOWN not in contracts.NOTIFICATION_STATES
    assert contracts.STATE_UNKNOWN not in inbox_module.STATE_FILTERS
    assert "unknown" not in [str(word).lower() for word in contracts.NOTIFICATION_STATES]


def test_the_new_response_names_are_all_spelled_out_in_the_contract(monkeypatch, client, world):
    """回执里有而契约里没有的字段名一律算假话（r303 同尺：名字逐枚现攒，不抄清单）。"""
    _produce(monkeypatch)
    body = _inbox(client).json()

    names = {"state_ledger"} | set(body["state_ledger"])
    text = CONTRACT.read_bytes().decode("utf-8")
    backtick = chr(96)
    unmentioned = sorted(name for name in names if backtick + name + backtick not in text)

    assert unmentioned == [], "这些新字段在契约里逐字没有名字：" + ", ".join(unmentioned)


def test_the_contract_appends_one_section_and_deletes_nothing():
    """三笔账都与提交先后无关：① 前缀等式（历史一字不动）② 长度变长 ③ 本单节标题恰一枚。"""
    base = _as_blob_text(_git_show(BASE, "docs/api/contract-v1.md"))
    now = _as_blob_text(CONTRACT.read_bytes())

    assert now.startswith(base), "契约不是纯追加：文末之前的每一个字都不许动"
    assert len(now) > len(base), "契约没长东西：本单一格都没写"
    assert now[len(base):].count(SECTION_HEADING) == 1, "本单那一节在追加段里不是一枚"
    assert now.count(SECTION_HEADING) == 1, "本单那一节被人整节复制过"


def test_the_new_contract_section_says_which_face_lives_where():
    """契约把三张脸写清：null 不是第四枚状态词、整页不 503、零新增码、开发那一格不动。"""
    text = _as_blob_text(CONTRACT.read_bytes())
    start = text.index(SECTION_HEADING)
    following = text.find(chr(10) + "## ", start + len(SECTION_HEADING))
    section = text[start:following if following != -1 else len(text)]

    for marker in (
        "state_ledger", "unread_total", "unread_returned", "unknown_total", "unknown_returned",
        "null", STORAGE_CODE, "503", "notification_states", "recipient_states", "apply_state",
        "can_address", "Zero new error code", "development",
    ):
        assert marker in section, "契约那一节没提 " + marker
    assert "not a fourth state word" in section, "契约没写清 null 与第四枚状态词的分别"


@pytest.mark.parametrize(
    "path",
    [STATES_PY, INBOX_PY, CONTRACTS_PY, CONTRACT, Path(__file__).resolve(), BELL_VUE],
    ids=["states", "inbox", "contracts", "contract", "pins", "bell"],
)
def test_every_delivered_file_keeps_the_repository_byte_shape(path):
    blob = path.read_bytes()

    assert blob[:3] != b"\xef\xbb\xbf", path.name + " 带上了 BOM"
    assert blob.count(b"\n") == blob.count(b"\r\n"), path.name + " 里有 lone LF"
    assert blob.decode("utf-8").count("\ufffd") == 0, path.name + " 里出现 U+FFFD：编码被写坏过"


# ================================================= 己 · 反证刀：四把，逐把只在影子根里落变异


class _R388Edit(overlay.ShadowEdit):
    """一扇 R388 的反证窗：变异只落临时目录里的影子副本，并 exec 进内存那一枚模块字典。

    锚点按行列表给，换行由被改文件自己决定（本仓纯 CRLF）；命中数不是恰好一枚就整体不落盘，
    变异文本还要先过 compile()，语法不过连窗都不开（r303 / r373 同一手法）。
    """

    tag = "r388"
    #: 🔴 R466：变异只落影子副本，不 exec 进活模块（整份码体重跑会换新每一枚顶层把手的身体，
    #: 而那次 exec 在 __enter__ 里，它一炸就没有 __exit__ 还原）。改绑走 r466.install_mutation。
    execs_module = False

    def __init__(self, path, old_lines, new_lines):
        super().__init__(path)
        self.old_lines = tuple(old_lines)
        self.new_lines = tuple(new_lines)

    def mutate(self, text):
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        old = newline.join(self.old_lines)
        hits = text.count(old)
        assert hits == 1, (
            self.path.name + " 里锚点命中 " + str(hits) + " 处（要求恰好 1 处）：变异整体不落盘"
        )
        mutated = text.replace(old, newline.join(self.new_lines), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _mutate(path, old_lines, new_lines, rebind=()):
    """开一扇反证窗：变异只落影子副本，窗内只把**变了的那几枚顶层绑定**装进活模块，出门逐枚装回。

    🔴 R466：旧姿势 execs_module=True 会把变异后的整份码体 exec 进 sys.modules 那枚模块——
    states/inbox 每一枚顶层把手换新身体，本件 :952 那句「反证窗 exec 整份码体会洗掉它，故可
    重钉」记的就是这场副作用。现在模块体不重跑，窗内装的替身不会被洗掉，重钉仍是幂等的。
    姿势件与 test_r457_audit_retention_execution_leg.py:169-242 同一族。
    """
    mutated_module = overlay.module_of(overlay.rel_of(path))
    assert mutated_module is not None, path.name + " 对应的模块还没被导入，改绑无处可落"
    with _R388Edit(path, old_lines, new_lines) as info, \
            r466.install_mutation(mutated_module, path, info.read_text()) as mutant:
        snapshots = [(target, attr, getattr(target, attr)) for target, attr in rebind]
        for target, attr, _before in snapshots:
            assert attr in mutant, (
                "窗内要改绑的 " + attr + " 不在本扇窗改动的顶层绑定里（实取 " + str(sorted(mutant)) + "）：这把刀空转")
            setattr(target, attr, mutant[attr])
        try:
            yield info
        finally:
            for target, attr, before in snapshots:
                setattr(target, attr, before)


def _missing_table_world(monkeypatch) -> None:
    """把生命周期那一层接到「库起着而 0016 没跑」的世界。反证窗 exec 整份码体会洗掉它，故可重钉。"""
    monkeypatch.setattr(state_store, "_database_available", lambda: True)
    monkeypatch.setattr(state_store, "_conn", lambda: _AbsentTableConnection())


def _absent_face(monkeypatch, client) -> dict:
    """本单的正脸，一枚可读把手：整页 200、逐条 null、缺席那一格说实话、两枚未读不脏。"""
    _produce(monkeypatch)
    response = _inbox(client)

    assert response.status_code == 200, "整页不再照答：" + str(response.status_code)
    body = response.json()
    assert _state_column(body) == [None, None], "逐条那一格没交回 null：" + str(_state_column(body))
    assert body["state_ledger"] == ABSENT_CELL, "state_ledger 读数不对：" + str(body["state_ledger"])
    assert (body["unread_total"], body["unread_returned"]) == (0, 0), "未知被算成未读了"
    assert _ids(body) == [APPROVAL_ID, DOCUMENT_ID], "照答的腿少了条目"
    return body


def _dev_face_untouched(monkeypatch, client) -> dict:
    """开发那一格的正脸（各把刀都要证明它没被顺手波及）。"""
    _develop(monkeypatch)
    body = _inbox(client).json()

    assert _state_column(body) == ["unread", "unread", "unread"], str(_state_column(body))
    assert body["state_ledger"] == ANSWERED_CELL
    assert (body["unread_total"], body["total"]) == (3, 3)
    return body


#: 刀甲：读腿退回回落那本内存空账（基点的形状）——摘掉「问不出」那一支。
FALLBACK_ANCHOR = [
    "    if not _database_available():",
    "        if alerts_api._is_production_environment():",
    "            # 生产而库不在位：那本内存账在客户机上恒为空，交回去就是替这台机器宣布「这个人",
]
FALLBACK_MUTANT = [
    "    if not _database_available():",
    "        if False:",
    "            # 生产而库不在位：那本内存账在客户机上恒为空，交回去就是替这台机器宣布「这个人",
]

#: 刀乙：未知被算成未读（计数虚高那一格）。
COUNT_ANCHOR = [
    "            state = (stored.get(item.id) or STATE_UNREAD) if ledger_answered else STATE_UNKNOWN",
]
COUNT_MUTANT = [
    "            state = (stored.get(item.id) or STATE_UNREAD) if ledger_answered else STATE_UNREAD",
]

#: 刀丙：整页 503 —— 把还答得着的两条腿一起打死（本单明确不要的那一种）。
PAGE_ANCHOR = [
    "    ledger_answered = read_back is not None",
]
PAGE_MUTANT = [
    "    ledger_answered = read_back is not None",
    "    if not ledger_answered:",
    "        raise state_store.NotificationStateStoreMissing('mutant: fold the whole page')",
]

#: 刀丁：read_state 把「问不出」兼成 None（= 未读），单枚读那一格换脸。
SINGLE_ANCHOR = [
    "    if not _database_available():",
    "        if alerts_api._is_production_environment():",
    "            raise NotificationStateStoreMissing(",
    "                f'{TABLE} cannot be read in production without PostgreSQL ('",
]
SINGLE_MUTANT = [
    "    if not _database_available():",
    "        if False:",
    "            raise NotificationStateStoreMissing(",
    "                f'{TABLE} cannot be read in production without PostgreSQL ('",
]

#: 刀戊：缺表那一格被洗成「空账」——本单不许并走的两张脸之一（r299 也钉着）。
MIGRATION_ANCHOR = [
    "def _require_table(conn) -> None:",
    "    row = conn.execute('SELECT to_regclass(%s) AS table_name', (f'public.{TABLE}',)).fetchone()",
    "    if not row or row['table_name'] is None:",
]
MIGRATION_MUTANT = [
    "def _require_table(conn) -> None:",
    "    row = conn.execute('SELECT to_regclass(%s) AS table_name', (f'public.{TABLE}',)).fetchone()",
    "    if False:",
]


def test_the_counter_evidence_window_touches_no_tracked_file(monkeypatch, client, world):
    """下面几把刀的公共前提：窗开在影子根里，盘上那两枚被跟踪文件全程只读。"""
    before_states = _tracked_sha(STATES_PY)
    before_inbox = _tracked_sha(INBOX_PY)

    with _mutate(STATES_PY, FALLBACK_ANCHOR, FALLBACK_MUTANT) as info:
        # 窗开着的时候，盘上那两枚字节凭据必须一动不动——变异只落在影子根里
        assert _tracked_sha(STATES_PY) == before_states, "反证窗碰了盘上的 states.py"
        assert _tracked_sha(INBOX_PY) == before_inbox, "反证窗碰了盘上的 inbox.py"

    assert info["restored"] is True and info["shadow_clean"] is True, "影子副本没回到盘上的字"
    assert _tracked_sha(STATES_PY) == before_states
    assert _tracked_sha(INBOX_PY) == before_inbox


def test_counter_evidence_a_the_memory_fallback_reddens_the_read_leg(monkeypatch, client, world):
    """刀甲：读腿一退回内存空账，「问不出」那三格读数当场红，开发那一格照旧绿。"""
    before = _tracked_sha(STATES_PY)

    with _mutate(STATES_PY, FALLBACK_ANCHOR, FALLBACK_MUTANT) as info:
        with pytest.raises(AssertionError) as caught:
            _absent_face(monkeypatch, client)
        assert "state_ledger" in str(caught.value) or "null" in str(caught.value), str(caught.value)
        assert state_store.recipient_states(OWNER) == {}, "变异版竟然还交回 None"
        _dev_face_untouched(monkeypatch, client)

    assert info["restored"] is True
    assert _tracked_sha(STATES_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    _absent_face(monkeypatch, client)  # 出窗即绿：红来自变异，不是这扇窗的残渣


def test_counter_evidence_b_counting_unknown_as_unread_reddens_the_counts(monkeypatch, client, world):
    """刀乙：把未知算成未读，两枚计数与那一格读数一起红；开发那一格不受影响。"""
    from app.api.v1 import notifications as outlet_module

    before = _tracked_sha(INBOX_PY)

    with _mutate(
        INBOX_PY, COUNT_ANCHOR, COUNT_MUTANT, rebind=[(outlet_module, "build_inbox")],
    ) as info:
        with pytest.raises(AssertionError) as caught:
            _absent_face(monkeypatch, client)
        # 逐条那一格交回的是 'unread' 冒充：未读计数与它一起红
        assert "'unread'" in str(caught.value) or "未读" in str(caught.value), str(caught.value)
        _dev_face_untouched(monkeypatch, client)

    assert info["restored"] is True
    assert _tracked_sha(INBOX_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    _absent_face(monkeypatch, client)


def test_counter_evidence_c_a_whole_page_503_reddens_the_answering_legs(monkeypatch, client, world):
    """刀丙：状态这一格一改口就抛到整页，「列表照读」当场红 —— 这正是本单不要的那一种做法。"""
    from app.api.v1 import notifications as outlet_module

    before = _tracked_sha(INBOX_PY)

    with _mutate(
        INBOX_PY, PAGE_ANCHOR, PAGE_MUTANT, rebind=[(outlet_module, "build_inbox")],
    ) as info:
        with pytest.raises(AssertionError) as caught:
            _absent_face(monkeypatch, client)
        assert "整页" in str(caught.value), str(caught.value)
        _dev_face_untouched(monkeypatch, client)

    assert info["restored"] is True
    assert _tracked_sha(INBOX_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    _absent_face(monkeypatch, client)


def _single_read_face() -> None:
    """单枚读那张脸的把手（刀丁拿它跑红）：问不出必须是具名错，不许是 None（＝未读）。"""
    try:
        state_store.read_state(OWNER, APPROVAL_ID)
    except state_store.NotificationStateStoreMissing:
        return
    raise AssertionError("read_state 没抛具名错：问不出被兼成了未读")


def test_counter_evidence_d_read_state_answering_unread_reddens_its_own_pin(monkeypatch, world):
    """刀丁：单枚读把「问不出」兼成 None（未读），那一枚专件必须红，开发那一格仍绿。"""
    before = _tracked_sha(STATES_PY)
    _produce(monkeypatch)
    _single_read_face()  # 盘上真身：这张脸今天站得住

    with _mutate(STATES_PY, SINGLE_ANCHOR, SINGLE_MUTANT) as info:
        with pytest.raises(AssertionError) as caught:
            _single_read_face()
        assert "兼成了未读" in str(caught.value), str(caught.value)
        _develop(monkeypatch)
        assert state_store.read_state(OWNER, APPROVAL_ID) is None, "开发那一格被这把刀波及了"

    assert info["restored"] is True
    assert _tracked_sha(STATES_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    _produce(monkeypatch)
    _single_read_face()  # 出窗即绿：红来自变异，不是这扇窗的残渣


def test_counter_evidence_e_folding_the_missing_table_reddens_the_503_face(monkeypatch, client, world):
    """刀戊：谁把缺表也洗成「空账」，503 那张脸与整页读数当场红（本单没并走它）。"""
    before = _tracked_sha(STATES_PY)
    _produce(monkeypatch)
    _missing_table_world(monkeypatch)
    assert _inbox(client).status_code == 503, "盘上真身：缺表那张脸今天就是 503"

    # 反证窗 exec 的是整份码体，窗内才是变异版说了算的世界，所以那一格读数在窗里现钉一次。
    with _mutate(STATES_PY, MIGRATION_ANCHOR, MIGRATION_MUTANT) as info:
        _missing_table_world(monkeypatch)
        with pytest.raises(AssertionError) as caught:
            _inbox(client)
        assert "检表闸被绕过" in str(caught.value), str(caught.value)

    assert info["restored"] is True
    assert _tracked_sha(STATES_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    _missing_table_world(monkeypatch)
    assert _inbox(client).status_code == 503, "出窗后那张 503 的脸没回来"

# ============================ 庚 · 本单没治好的那一格：登记成 strict xfail，不留裸红

#: 这一枚断言今天**就该失败**，所以它不许以裸红的形式活在门里（全量门零失败是本仓今天的纪律），
#: 也不许被删掉（删了就等于宣布这一格治好了）。三条理由，逐条可查：
#:   ① 门今天绿：红只在变异与登记里，不出现在回归上；
#:   ② 读数不撒谎：pytest 把 xfailed 单列一枚，永远不计进 passed，谁读都读不到「通过」；
#:   ③ 修好的那一刻当场红：strict=True ⇒ XPASS(strict) 是 error，逼接手的人回来销账——
#:      比裸红更强，因为裸红大家都习惯了。
#: 具名阻塞与出处（逐枚可 rg，命中已核）：未读徽标那三个数今天归取数层独占，而
#: `frontend/src/lib/notifications.js` 里 `state_ledger` 零命中。把该文件整体钉死、本单不许放宽的
#: 四枚既有钉（与派工词所列、R385 交回《39e2b22》所记为同四枚）：
#:   - `frontend/src/lib/__tests__/r375-write-retryable-dict.test.js:38` 那本基线 `const REF = 796540e`；
#:   - 同件 `:236` 除两枚之外的每一枚导出都要与那本基线逐字同 sha；
#:   - 同件 `:262` 对 `notifications.js` 要求 `added` 恰为 `[]`：一枚新导出都不许多；
#:   - `frontend/src/lib/__tests__/r333-notification-inbox.test.js:143` 把 `normalizeInbox` 钉死八枚键。
#: 同件 `:95` 现量该层错误码名集合，方向相同 —— 记作第五枚，不顶第四枚的数。
#: R385 实测：改读一次即连既有 r333-notification-bell 咬 6 枚。解铃要总控裁定，执行层不自开这道门（判据③）。
@pytest.mark.xfail(
    strict=True,
    reason=(
        "具名阻塞：取数层 frontend/src/lib/notifications.js 读不到 state_ledger 那一格（rg 现量零命中），"
        "于是「数不清」在屏上仍会长成 0。四枚既有钉整体冻结该文件（与派工词、R385 交回 39e2b22 所记同四枚）："
        "r375-write-retryable-dict.test.js:38 那本基线 REF 796540e、同件 :236 每枚导出与该基线逐字同 sha、"
        "同件 :262 对 notifications.js 要求 added 恰为 []（一枚新导出都不许多）、"
        "r333-notification-inbox.test.js:143 钉死 normalizeInbox 八枚键；同件 :95 现量该层错误码名，同向第五枚。"
        "R385 实测改读一次即连既有 r333-notification-bell 咬 6 枚，判据③不许执行层放宽。"
        "真接上的那一刻这一枚以 XPASS(strict) 当场红，逼人来销账。"
    ),
)
def test_the_badge_layer_can_eventually_say_it_cannot_count():
    """那一格今天还没接进取数层：这一枚**应当**失败，失败由 strict xfail 记账，不算通过。"""
    source = (REPO / "frontend" / "src" / "lib" / "notifications.js").read_text(encoding="utf-8")

    assert "state_ledger" in source, (
        "取数层还是读不到 state_ledger：屏上那个 0 仍然分不清「都没有」与「数不清」"
    )


def test_the_registered_xfail_is_strict_named_and_alone():
    """登记出去的那一枚必须仍是 strict、仍带出处、仍是全件唯一一枚：谁摘条件谁红。"""
    tree = _tree(Path(__file__).resolve())
    marked = []
    decorators = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            printed = ast.unparse(dec)
            decorators.append(printed)
            if printed.startswith("pytest.mark.xfail"):
                call = dec if isinstance(dec, ast.Call) else None
                keywords = {kw.arg: kw for kw in (call.keywords if call else [])}
                marked.append((node.name, call is not None, keywords))

    assert len(marked) == 1, "本件的 xfail 不是恰好一枚：" + str([item[0] for item in marked])
    name, is_call, keywords = marked[0]
    assert is_call, "xfail 少了括号：没有 reason 的登记等于没登记"
    assert "strict" in keywords and "reason" in keywords, name + " 那枚 xfail 少了 strict 或 reason"
    assert ast.unparse(keywords["strict"].value) == "True", "strict 不许写成变量或函数调用"
    reason = keywords["reason"].value
    assert isinstance(reason, ast.Constant) and isinstance(reason.value, str), "reason 必须是字面量"
    for needle in ("notifications.js", "state_ledger", "r333", "r375", "XPASS(strict)", ":38", ":262", "796540e"):
        assert needle in reason.value, "reason 里少了出处 " + needle
    for escape in ("待并树", "在途", "下一班", "暂缓", "先红后治"):
        assert escape not in reason.value, "reason 里出现逃逸措辞：" + escape
    assert not [d for d in decorators if "skip" in d], "本件给自己开了 skip"


def test_the_xfail_target_is_a_real_failure_today():
    """strict xfail 只有在目标今天真红时才成立：这一枚把「它今天确实失败」也钉住。"""
    source = (REPO / "frontend" / "src" / "lib" / "notifications.js").read_text(encoding="utf-8")

    assert "state_ledger" not in source, (
        "取数层已经读那一格了：那一枚 xfail 该当场销账（否则它会以 XPASS(strict) 咬门）"
    )
