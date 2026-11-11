"""R376 · 「标记已读」不许在落不了库的时候说「记下了」（生命周期写腿的诚实性）。

症状（总控在基点 `796540e` 现取，本件自己复量过一遍）：`app/notifications/states.py` 是唯一
一条会写 `notification_states` 的腿，而它选腿那一格只看 `_database_available()`，**不看
`APP_ENV`**。于是客户机（生产 + PG 没起 / 迁移没跑）上 `POST /api/v1/notifications/read` 照写
进程内 `_ROWS`、照回 200 + `changed: true`。进程一重启那本账就没了，那条通知重新变未读 ——
回执里那句「记下了」从头到尾没对应过一次落库。契约 R366 一节 `:4056-4061` 已经把这一格登记为
「只报不改」，本单就是它欠的那笔。

形状照 R359（告警）与 R367（看板）刚落地的样子长，不另造一套：

- 判据甲 该有库而库不在 ⇒ **写腿拒答**：503 `storage_unavailable`（`app/api/v1/notifications.py`
  既有的那一支 except 早就在翻这枚错），零新增错误码、零新增 reason 词、出口一字未改。
- 判据乙 开发/裸机一个字都不改：那条内存腿今天仍是合法后端，200 + `changed: true` + `_ROWS`
  落行，逐格保持（把开发支一起打死同样是假话，只不过反着说）。
- 判据丙 回执诚实性单独钉：同一发写请求在「库在」与「库不在」两个世界里的回执**必须不等**；
  而读腿与写腿对「有没有记下」这一件事的说法必须一致 —— 拒答之后收件箱仍然逐条未读，这才是
  与 503 同源的那句话。
- 判据丁 授权与可寻址性在先：401 那一支、`notification_not_addressable` 那一支逐字不变，
  存储错与权限错不许合并成一格。

全部离线：不起服务、不连库、不打模型。`_FakeStateTable` 只被教过四条语句，没教过的当场抛 ——
什么都答的桩会把「这条腿根本没被执行」糊成一枚绿钉。
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import alerts as alerts_api
from app.common.auth import create_token
from app.main import app
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store

REPO = Path(__file__).resolve().parents[1]
STATES_PY = REPO / "app" / "notifications" / "states.py"

INBOX_PATH = "/api/v1/notifications"
READ_PATH = "/api/v1/notifications/read"
DISMISS_PATH = "/api/v1/notifications/dismiss"
WRITE_PATHS = [READ_PATH, DISMISS_PATH]
WRITE_PATH_IDS = ["mark_as_read", "dismiss"]

#: 仓里已有的那一码：出口 `:161` / `:191` 两支 except 今天就在吐它，本单一枚新码都不开。
STORAGE_CODE = "storage_unavailable"
NOT_ADDRESSABLE = "notification_not_addressable"
REASON_APPLIED = "applied"

DEPT = "r376-finance"
READER = "r376-reader"
STRANGER = "r376-stranger"
SESSION_ID = "r376-session-1"
STRANGER_SESSION = "r376-session-2"
MINE = f"approval:{SESSION_ID}"
THEIRS = f"approval:{STRANGER_SESSION}"
#: 本件那枚固定时钟：`_NOW` 交回的是 datetime（`_now()` 对它调 isoformat），不是拼好的字符串。
FIXED_MOMENT = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
FIXED_TS = FIXED_MOMENT.isoformat(timespec="seconds")

#: 装绊线之前先把**真身**抓在手里：一枚用例里先后接两个世界时，计数器不许套在计数器上。
_REAL_READ_STATE = state_store.read_state


def _account(username: str) -> dict:
    return {"id": username, "username": username, "role": "manager", "department": DEPT}


ACCOUNTS = {READER: _account(READER), STRANGER: _account(STRANGER)}


class _Result:
    """psycopg dict_row 的最小把手：取不到就是 None / 空列表，不替谁说谎。"""

    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeStateTable:
    """`notification_states` 的替身：记 SQL 与绑定参数，并按语句真的改一份行。

    只被教过四条语句（表在不在、整份读、单枚 FOR UPDATE 读、写口）。写口按 PostgreSQL 语义落：
    带 ON CONFLICT 就撞在 reader_key 上做 UPDATE，不带冲突目标撞上同一枚键是唯一约束冲突。
    """

    TABLE = "notification_states"

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, str]] = {}
        self.log: list[tuple[str, tuple]] = []
        self.commits = 0
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def commit(self) -> None:
        self.commits += 1

    @property
    def write_statements(self) -> list:
        return [entry for entry in self.log if entry[0].lower().startswith("insert")]

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        bound = tuple(params or ())
        with self._lock:
            self.log.append((statement, bound))
            head = statement.lower()
            if head.startswith("select to_regclass"):
                return _Result([{"table_name": self.TABLE}])
            if head.startswith("select notification_id, state from"):
                person = bound[0]
                return _Result(
                    [
                        {"notification_id": key[0], "state": row["state"]}
                        for key, row in self.rows.items()
                        if key[1] == person
                    ]
                )
            if head.startswith("select state from"):
                # 绑定序与 app/notifications/states.py 那条语句逐字同序：recipient 在前。
                person, identifier = bound
                row = self.rows.get((person, identifier))
                return _Result([{"state": row["state"]}] if row else [])
            if head.startswith("insert into"):
                self._apply_insert(statement, bound)
                return _Result([])
            raise AssertionError("替身没被教过这条语句，不替谁说谎：" + statement)

    def _apply_insert(self, statement: str, bound: tuple) -> None:
        identifier, person, state, recorded_at, updated_at = bound
        key = (person, identifier)
        if " on conflict " not in statement.lower() and key in self.rows:
            raise AssertionError("duplicate key on notification_states_reader_key: " + str(key))
        existing = self.rows.get(key)
        self.rows[key] = {
            "state": state,
            "recorded_at": existing["recorded_at"] if existing else recorded_at,
            "updated_at": updated_at,
        }


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """把这两枚账号喂进鉴权中间件真正用的那一次查询；`_db_ready` 钉成假。"""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    monkeypatch.setattr(auth, "_db_ready", False)


@pytest.fixture(autouse=True)
def source_legs_offline(monkeypatch):
    """三条**源**账全钉在内存形状：本件只治生命周期那一格，别把邻居的腿一起拖进来。"""
    monkeypatch.setattr(hitl_store, "_MEM_ROWS", {})
    monkeypatch.setattr(hitl_store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_api, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts_api, "_database_available", lambda: False)
    hitl_store.record_awaiting(SESSION_ID, READER, ["chart"], request_id="req-r376-mine")
    hitl_store.record_awaiting(STRANGER_SESSION, STRANGER, ["chart"], request_id="req-r376-theirs")


def _wire(monkeypatch, *, store_ready: bool) -> SimpleNamespace:
    """接生命周期这一层，并给三条出口各装一枚计数器。

    `conn` / `read_state` / `now` 三枚都是本件既有的缝：拒答那一格应当在**任何一次读写之前**
    发生，所以那三个数就是「闸到底排在哪儿」的读数，不靠注释维持。
    """
    table = _FakeStateTable() if store_ready else None
    touched = {"conn": 0, "read_state": 0, "now": 0}
    real_read = _REAL_READ_STATE

    def _conn():
        touched["conn"] += 1
        if table is None:
            raise AssertionError("库不在位却去连了：这一格该拒在门外，不该伸手碰连接")
        return table

    def _read(recipient, notification_id):
        touched["read_state"] += 1
        return real_read(recipient, notification_id)

    def _now():
        touched["now"] += 1
        return FIXED_MOMENT

    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: store_ready)
    monkeypatch.setattr(state_store, "_conn", _conn)
    monkeypatch.setattr(state_store, "read_state", _read)
    monkeypatch.setattr(state_store, "_NOW", _now)
    return SimpleNamespace(table=table, touched=touched)


@pytest.fixture
def prod_no_store(monkeypatch):
    """客户机那一格：`APP_ENV=production` 而库没就绪 —— 今天会偷偷写内存并回 changed: true。"""
    monkeypatch.setenv("APP_ENV", "production")
    world = _wire(monkeypatch, store_ready=False)
    world.client = TestClient(app)
    return world


@pytest.fixture
def prod_with_store(monkeypatch):
    """对照世界：同一枚生产档，库这次在位。"""
    monkeypatch.setenv("APP_ENV", "production")
    world = _wire(monkeypatch, store_ready=True)
    world.client = TestClient(app)
    return world


@pytest.fixture
def dev_no_store(monkeypatch):
    """裸机那一格：同一枚「库不在」，环境不是生产 —— 闸在这里不许咬。"""
    monkeypatch.setenv("APP_ENV", "development")
    world = _wire(monkeypatch, store_ready=False)
    world.client = TestClient(app)
    return world


def _headers(username: str = READER) -> dict:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _post(client, path: str, ids: list[str], username: str = READER):
    return client.post(path, headers=_headers(username), json={"ids": ids})


def _applied(body: dict) -> list[dict]:
    return [row for row in body.get("results", []) if row.get("reason") == REASON_APPLIED]


# ------------------------------------------------- 判据甲：生产 + 无库 ⇒ 写腿拒答，一字不写


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_production_without_a_store_refuses_the_write(prod_no_store, path):
    response = _post(prod_no_store.client, path, [MINE])

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}, "拒答必须回仓里已有的那一码"
    assert state_store._ROWS == {}, "拒答之余还往内存腿写了一行"


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_the_refusal_precedes_every_ledger_clock_and_connection(prod_no_store, path):
    _post(prod_no_store.client, path, [MINE])

    assert prod_no_store.touched == {"conn": 0, "read_state": 0, "now": 0}, (
        "闸排在读写之后了：拒答之前碰过的出口 " + str(prod_no_store.touched)
    )


def test_the_storage_layer_refuses_on_its_own_without_http(prod_no_store):
    """直调也拒：诚实性不许只在路由那一层成立。"""
    with pytest.raises(state_store.NotificationStateStoreMissing):
        state_store.apply_state(READER, MINE, "read")

    assert state_store._ROWS == {}
    assert prod_no_store.touched["conn"] == 0


def test_the_callers_own_error_still_answers_first(prod_no_store):
    """空收件人/空编号仍是 ValueError：闸不许把调用方自己的错洗成存储错。"""
    with pytest.raises(ValueError):
        state_store.apply_state("", MINE, "read")
    with pytest.raises(ValueError):
        state_store.apply_state(READER, "", "read")

    assert prod_no_store.touched == {"conn": 0, "read_state": 0, "now": 0}


def test_no_write_receipt_claims_a_change_that_was_not_recorded(prod_no_store):
    """判据②的那一格：不许既 200 又 changed: true。"""
    response = _post(prod_no_store.client, READ_PATH, [MINE])

    if response.status_code == 200:  # 今天（未修）会走到这里，这正是本单要红的地方
        assert _applied(response.json()) == [], "200 回执里出现了『记下了』那一格，而什么都没落库"
        raise AssertionError("生产无库却回了 200：这一格就是本单治的病")
    assert response.status_code == 503


# ------------------------------------------------- 判据丙：两个世界的回执必须不等


def _receipt_in(monkeypatch, path: str, *, store_ready: bool):
    """在一个世界里发一次写，把回执按 (状态码, 体) 抄回来；换世界靠的是同一只 monkeypatch。"""
    monkeypatch.setenv("APP_ENV", "production")
    world = _wire(monkeypatch, store_ready=store_ready)
    response = _post(TestClient(app), path, [MINE])
    return (response.status_code, response.json()), world


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_the_same_request_answers_differently_in_the_two_worlds(monkeypatch, path):
    """判据②的行为钉：同一发请求，「库在」与「库不在」两世界的回执**必须不等**。"""
    recorded, ready_world = _receipt_in(monkeypatch, path, store_ready=True)
    refused, _missing_world = _receipt_in(monkeypatch, path, store_ready=False)

    assert recorded[0] == 200, recorded
    assert refused[0] == 503, refused
    assert recorded != refused, "两世界回执同一张脸：那句『改了』就是在撒谎"
    assert recorded[1]["changed"] == 1 and "changed" not in refused[1]
    assert ready_world.touched["conn"] >= 1, "PG 腿根本没被执行，200 是从哪儿来的"


def test_a_ready_store_records_once_and_says_so(prod_with_store):
    response = _post(prod_with_store.client, READ_PATH, [MINE])

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {"id": MINE, "state": "read", "changed": True, "reason": REASON_APPLIED}
    ]
    assert prod_with_store.table.rows[(READER, MINE)]["state"] == "read", "回执说落了库，库里没行"
    assert prod_with_store.table.commits == 1
    assert prod_with_store.touched["conn"] >= 1, "PG 腿根本没被执行过"
    assert state_store._ROWS == {}, "落库之余又往内存抄了一份：那是第二本账"


def test_a_repeated_mark_in_a_ready_store_still_says_changed_false(prod_with_store):
    """幂等那一格不许被闸顺手打死：第二次 200 + changed False，且不重写。"""
    first = _post(prod_with_store.client, DISMISS_PATH, [MINE])
    second = _post(prod_with_store.client, DISMISS_PATH, [MINE])

    assert first.json()["results"][0]["changed"] is True
    assert second.status_code == 200, second.text
    assert second.json()["results"][0] == {
        "id": MINE, "state": "dismissed", "changed": False, "reason": REASON_APPLIED,
    }
    assert len(prod_with_store.table.write_statements) == 1, "第二次点击又写了一枚行"


# ------------------------------------------------- 判据乙：开发/裸机那一支一个字都不改


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_development_without_a_store_answers_exactly_as_before(dev_no_store, path):
    response = _post(dev_no_store.client, path, [MINE])

    assert response.status_code == 200, response.text
    expected_state = "read" if path == READ_PATH else "dismissed"
    assert response.json()["results"] == [
        {"id": MINE, "state": expected_state, "changed": True, "reason": REASON_APPLIED}
    ]
    assert state_store._ROWS[(READER, MINE)]["state"] == expected_state
    assert dev_no_store.touched["conn"] == 0, "开发态那条腿不该去连库"


def test_the_development_leg_keeps_its_idempotent_answer(dev_no_store):
    _post(dev_no_store.client, DISMISS_PATH, [MINE])
    again = _post(dev_no_store.client, DISMISS_PATH, [MINE])

    assert again.status_code == 200, again.text
    assert again.json()["results"][0]["changed"] is False


@pytest.mark.parametrize(
    "environment", ["development", "test", "staging", "", "prod1", "production-env"]
)
def test_the_gate_never_bites_outside_a_production_environment(monkeypatch, environment):
    """生产档不许只认字面量：非生产拼写一律照旧落内存腿（`prod1` 那种近似值也不算生产）。"""
    monkeypatch.setenv("APP_ENV", environment)
    _wire(monkeypatch, store_ready=False)
    client = TestClient(app)

    response = _post(client, READ_PATH, [MINE])

    assert response.status_code == 200, f"APP_ENV={environment!r} 不是生产却被拒了: {response.text}"
    assert state_store._ROWS != {}


@pytest.mark.parametrize("environment", ["production", "prod", "PRODUCTION", " Production "])
def test_every_production_spelling_refuses(monkeypatch, environment):
    monkeypatch.setenv("APP_ENV", environment)
    _wire(monkeypatch, store_ready=False)
    client = TestClient(app)

    response = _post(client, READ_PATH, [MINE])

    assert response.status_code == 503, f"APP_ENV={environment!r} 漏过了闸: {response.text}"
    assert state_store._ROWS == {}


# ------------------------------------------------- 判据丁：401 / 不可寻址那一支逐字不变


def test_an_anonymous_caller_never_meets_the_storage_answer(prod_no_store):
    response = prod_no_store.client.post(READ_PATH, json={"ids": [MINE]})

    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "authentication_required"}
    assert prod_no_store.touched == {"conn": 0, "read_state": 0, "now": 0}


def test_an_unaddressable_id_keeps_its_own_receipt_while_the_store_refuses(prod_no_store):
    """权限错与存储错是两格，各答各的：别人的编号仍是 200 + not_addressable。"""
    response = _post(prod_no_store.client, READ_PATH, [THEIRS], username=READER)

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {"id": THEIRS, "state": None, "changed": False, "reason": NOT_ADDRESSABLE}
    ]
    assert state_store._ROWS == {}


def test_one_recordable_id_is_enough_to_refuse_the_whole_call(prod_no_store):
    """混着一枚管得着的就不许拼成 200：要么逐格 not_addressable，要么整体 503。"""
    response = _post(prod_no_store.client, READ_PATH, [THEIRS, MINE])

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert "results" not in response.json(), "半张回执：落库失败的那一格被 200 洗掉了"
    assert state_store._ROWS == {}


# ------------------------------------------------- 判据丙的下半：读腿与写腿说同一句话


def test_the_inbox_still_answers_while_the_write_leg_refuses(prod_no_store):
    """读侧不跟着翻脸（R366 追认的那一格），但它说的必须是同一句『这一格问不出』（R388）。

    基点上这一枚断的是 `== {}` 加逐条 `"unread"`：写侧刚说完「落不了库」，读侧就替这台机器宣布
    「这个人什么都没读过、每一条都是新的」。同一件事两张脸，正是本单治的病。今天两半都反着钉：
    整页照答 200（不许把还答得着的文档腿、告警腿一起打死），而状态那一格交回显式的未知。
    """
    write = _post(prod_no_store.client, READ_PATH, [MINE])
    read = prod_no_store.client.get(INBOX_PATH, headers=_headers())

    assert write.status_code == 503
    assert read.status_code == 200, read.text
    body = read.json()
    assert state_store.recipient_states(READER) is None, "读腿还在那一格交回内存空账"
    assert state_store._ROWS == {}
    assert [row["state"] for row in body["notifications"]] == [None]
    assert body["total"] == body["returned"] == 1, "条目本身被状态那一格一起抹掉了"
    assert body["unread_total"] == body["unread_returned"] == 0, "未知被算成了未读：徽标虚高就是这一格"
    assert body["state_ledger"] == {
        "included": False,
        "reason_code": STORAGE_CODE,
        "unknown_total": 1,
        "unknown_returned": 1,
    }


def test_a_refusal_leaves_no_reader_state_for_the_read_leg_to_remember(prod_no_store):
    """基点上那对矛盾（写侧说改了、重启后读侧说没有）从此不可能再拼出来。

    R388 把下半句也钉住了：读侧此刻说的不是「没有」，是「问不出」——所以它既不留下 `_ROWS`
    里那次虚构的已读，也不许拿 `{}` 替这台机器宣布「每一条都是新的」。
    """
    _post(prod_no_store.client, DISMISS_PATH, [MINE])
    state_store.reset_for_testing()

    assert state_store._ROWS == {}, "内存腿里还留着一次『成功』的已读"
    assert state_store.recipient_states(READER) is None, "读腿把内存那本账当答案交回来了"
    after = prod_no_store.client.get(INBOX_PATH, headers=_headers())
    assert [row["state"] for row in after.json()["notifications"]] == [None]
    assert after.json()["unread_total"] == 0


# ------------------------------------------------- 现读：本件的读数不靠注释维持


def test_the_gate_reads_the_ruler_the_repo_already_has(prod_no_store, monkeypatch):
    """摘掉「借来的那枚尺」看闸是否跟着失效：答是的就是同一枚，没有第二把尺。"""
    monkeypatch.setattr(alerts_api, "_is_production_environment", lambda: False)

    response = _post(prod_no_store.client, READ_PATH, [MINE])

    assert response.status_code == 200, "闸自己另算了一遍 APP_ENV：它没在借那枚尺"
