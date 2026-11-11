"""R251 —— 告警处置闭环：确认 / 转派 / 关闭（判据 J-1 / J-2 / J-3）。

题面来源：docs/version-roadmap-and-next-week-plan-2026-09-22.md 第 263 行那一句"告警支持确认、
转派或关闭中的至少一部分闭环"。基线 e82619c 上 alerts.py 的实测：路由只有 ``POST/GET
/alerts/rules``、``DELETE /alerts/rules/{id}``、``GET /alerts``、``POST /alerts/check`` 五枚，
**一条处置口都没有**；简报里说的"ack/confirm/dismiss/resolve/assign 命中 3 处"抠开是五枚行的
子串命中（``falls back`` 一枚、``Path.resolve()``/``Resolve the tenant DATA_DIR`` 四枚），
零枚端点 —— 台账今天只能读，不能处置。本件把三件动作做成闭环，并钉住：

* **J-1 状态机**：词表封闭（open / acknowledged / closed），``closed`` 是终态；跳转表只有
  open→acknowledged、open→closed、acknowledged→closed，加上"转派原地不动状态"。非法跳转必须
  被拒**且数据没被改写** —— 读写两侧都取证：返回值 + 再读一次 + 有库那条腿的语句账。
* **J-2 三件动作各自可寻址**：ack / close / assign 各一枚，断言「谁、什么时候、对哪条告警、
  做了什么」在**再读一次**时逐字段一致（详情与列表都读到处置后的状态，不只是写进去）。
* **J-3 越权 0 条**：staff / manager / admin / auditor × 三动作 = 12 格逐格判；被拒方不许用
  状态码之差试出「这条告警在不在」，所以别部门的行与不存在的 id 必须逐字节同答。

凭据分层（谁给哪条判据作证，不许混）：

1. **无库那条腿**（``_database_available() -> False``）跑真代码 + 真内存台账：12 格矩阵、
   状态机、"处置后再读一次"全在这儿真跑真读，摘守卫（反证①）、把角色门改成恒真（反证③）
   都会真的让它红。
2. **有库那条腿**用本文件自带的 ``_LedgerConnection``：它只回答本件真会发的三类语句，按 id
   把值落到自己的行字典里。它**不是** PostgreSQL，也不求值归属谓词（那会造出第二份行级判定，
   而 ``alert_row_visible`` 与 ``alert_row_scope_sql`` 同源这件事已由
   ``tests/test_r176_alert_row_scope.py::test_offline_and_sql_branches_share_one_scope_decision``
   钉住）。这条腿判两件事：语句与参数的形状（归属谓词进没进 WHERE、守卫语句发没发、commit
   有没有落），以及"再读一次读到的是这张替身里**现在**的值"—— 正因如此，把处置改成只算不写
   （反证②）会让这一格当场红，而不是让断言退化成比字符串。
3. **词表同源**：DDL 那一份拼写在 ``migrations/0014_alert_disposal_columns.sql`` 的 CHECK 里，
   本文件从 ``app.db.migrations`` 现读那一版来对判 ``ALERT_STATUSES``，手抄一枚都不许。

真库没跑：``tests/conftest.py`` 把测试期的 DATABASE_URL 钉在不可能的端口上（宿主 PostgreSQL
结构性禁止入测试），迁移的双路证明走离线 DDL 重放，见
``tests/test_r251_alert_disposal_migration.py`` 顶部自述。
"""
from __future__ import annotations

import re
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common.audit import get_audit_events
from app.common.auth import create_token
from app.common.permissions import ACTION_MANAGE_ALERTS
from app.main import app

DEPT_OWN = "r251-own"
DEPT_FX = "r251-fx"
DEPT_VICTIM = "r251-victim"
OWN_MESSAGE = "R251T-ALERT-OWN 部门 r251-own 的营收跌破阈值"
FX_MESSAGE = "R251T-ALERT-FX 部门 r251-fx 的毛利跌破阈值"
LEGACY_MESSAGE = "R251T-ALERT-LEGACY 处置列出现之前的巡检告警"
VICTIM_MESSAGE = "R251T-ALERT-VICTIM 部门 r251-victim 的现金流已经见底"

OWN_ALERT = 1
FX_ALERT = 2
LEGACY_ALERT = 3
ACKED_ALERT = 4
CLOSED_ALERT = 5
VICTIM_ALERT = 6
MISSING_ALERT = 999999

#: 桩上去的服务端时钟：J-2 要逐字段读回"什么时候"，所以这一枚必须是有名字的常量。
FIXED_TS = "2026-09-25T10:00:00+08:00"
#: 已经落在 4 / 5 号行上的旧处置：非法跳转必须不许覆盖它们。
FIRST_ACKER = "r251-first-acker"
FIRST_ACK_TS = "2026-09-25T09:30:00+08:00"
FIRST_CLOSER = "r251-first-closer"
FIRST_CLOSE_TS = "2026-09-25T09:40:00+08:00"

STAFF = "r251-staff"
AUDITOR = "r251-auditor"
OWN_MANAGER = "r251-manager-own"
FX_MANAGER = "r251-manager-fx"
ADMINISTRATOR = "r251-admin"
TARGET_MANAGER = "r251-target-own"
#: 三枚不合格的转派目标：查无此人 / 读不到这一行 / 没有处置告警的能力。
GHOST = "r251-ghost-does-not-exist"

#: 每个身份"看得见哪些行"的唯一一份表，与 alert_row_visible 的口径一致：administrator 不设条件，
#: manager 只看本部门的 + 无归属历史行，staff / auditor 连门都进不来（所以任何目标都答 403）。
IN_SCOPE = {
    OWN_MANAGER: {OWN_ALERT, ACKED_ALERT, CLOSED_ALERT, LEGACY_ALERT},
    FX_MANAGER: {FX_ALERT, LEGACY_ALERT},
    ADMINISTRATOR: {OWN_ALERT, FX_ALERT, VICTIM_ALERT, ACKED_ALERT, CLOSED_ALERT, LEGACY_ALERT},
    STAFF: set(),
    AUDITOR: set(),
    TARGET_MANAGER: {OWN_ALERT, ACKED_ALERT, CLOSED_ALERT, LEGACY_ALERT},
}

#: 审计泄漏探针：别人的告警正文与别人的部门一个字都不许进台账。主体**自己**的部门不在探针里 ——
#: 那是 app/common/audit.py 记录 actor_departments 的既有形状，不是外泄。
FORBIDDEN_IN_AUDIT = ("R251T-ALERT", DEPT_VICTIM)

#: J-3 那 12 格：四档角色 × 三动作。
ROLE_MATRIX = [
    (role, action)
    for role in ("staff", "manager", "admin", "auditor")
    for action in ("ack", "close", "assign")
]

#: 每一格里"被拒"的那一格该由哪个目标来作证：staff / auditor 在资源级那道门前就被判掉，
#: 任何目标都答同一句 403；manager 的被拒格是别人的行（404）；admin 没有行级越权可判，
#: 它的被拒格是「这条根本不存在」（404）。
REFUSAL_CELLS = {
    "staff": (STAFF, OWN_ALERT, "permission_denied"),
    "auditor": (AUDITOR, OWN_ALERT, "permission_denied"),
    "manager": (OWN_MANAGER, VICTIM_ALERT, "resource_not_found"),
    "admin": (ADMINISTRATOR, MISSING_ALERT, "resource_not_found"),
}

NEW_VERSION = "0014"
NEW_FILENAME = "0014_alert_disposal_columns.sql"


# --------------------------------------------------------------------- 身份与台账
def _account(username: str, role: str, department: str, **overrides) -> dict:
    account = {
        "id": "u-" + username,
        "username": username,
        "role": role,
        "department": department,
    }
    account.update(overrides)
    return account


def _seeds() -> list[dict]:
    """六枚行：本部门 / 别部门 / 谁的都不算的受害行 / 无归属历史行 / 已确认 / 已关闭（终态）。"""
    base = {"rule_id": 7, "ai_analysis": "", "read": False, "created_at": "2026-09-25T09:00:00+08:00"}
    return [
        {**base, "id": OWN_ALERT, "message": OWN_MESSAGE, "department": DEPT_OWN},
        {**base, "id": FX_ALERT, "message": FX_MESSAGE, "department": DEPT_FX},
        {**base, "id": VICTIM_ALERT, "message": VICTIM_MESSAGE, "department": DEPT_VICTIM},
        # 无归属行：处置列出现之前塞进来的形状，连 department 都没有。
        {"id": LEGACY_ALERT, "rule_id": 7, "message": LEGACY_MESSAGE, "read": False},
        {
            **base,
            "id": ACKED_ALERT,
            "message": OWN_MESSAGE + "-acked",
            "department": DEPT_OWN,
            "status": "acknowledged",
            "acknowledged_by": FIRST_ACKER,
            "acknowledged_at": FIRST_ACK_TS,
        },
        {
            **base,
            "id": CLOSED_ALERT,
            "message": OWN_MESSAGE + "-closed",
            "department": DEPT_OWN,
            "status": "closed",
            "closed_by": FIRST_CLOSER,
            "closed_at": FIRST_CLOSE_TS,
        },
    ]


def _accounts() -> dict[str, dict]:
    return {
        STAFF: _account(STAFF, "staff", DEPT_OWN),
        AUDITOR: _account(AUDITOR, "auditor", DEPT_OWN),
        OWN_MANAGER: _account(OWN_MANAGER, "manager", DEPT_OWN),
        FX_MANAGER: _account(FX_MANAGER, "manager", DEPT_FX),
        ADMINISTRATOR: _account(ADMINISTRATOR, "admin", ""),
        TARGET_MANAGER: _account(TARGET_MANAGER, "manager", DEPT_OWN),
    }


class _LedgerConnection:
    """alerts 的极小替身：只认本件真会发的三类语句，按 id 落值，并记账发了哪些语句。

    定位与 ``tests/test_r176_alert_row_scope.py`` 的 ``_RecordingConnection`` 同级：给本单判据
    当凭据，产品代码不读它，也不是第二份 schema 事实源。它**不求值归属谓词**（那要再造一份
    行级判定），归属在不在 WHERE 里由结构性用例判。
    """

    def __init__(self, rows: list[dict]):
        self.rows = {int(row["id"]): dict(row) for row in rows}
        self.executed: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        args = tuple(params or ())
        self.executed.append((text, args))
        if text.startswith("SELECT * FROM alerts WHERE id = %s"):
            row = self.rows.get(int(args[0]))
            return _Cursor([dict(row)] if row else [], 1 if row else 0)
        if text.startswith("UPDATE alerts SET"):
            head = text.split(" WHERE ")[0]
            columns = re.findall(r"(\w+) = %s", head)
            assert len(columns) == len(args) - 1, (text, args)
            row = self.rows.get(int(args[-1]))
            if row is None:
                return _Cursor([], 0)
            row.update(zip(columns, args[:-1]))
            return _Cursor([], 1)
        raise AssertionError("处置这条腿不该发出别的语句：" + text)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def statements(self) -> list[str]:
        return [text for text, _ in self.executed]

    def updates(self) -> list[tuple[str, tuple]]:
        return [(text, args) for text, args in self.executed if text.startswith("UPDATE ")]


class _Cursor:
    def __init__(self, rows: list[dict], rowcount: int):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def _wire(monkeypatch, accounts: dict[str, dict]):
    """身份缝：令牌 → username → 账号表（与 tests/test_r176_* 同一个口径）。"""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    return auth


@pytest.fixture()
def ledger(monkeypatch):
    """无库那条腿：真内存台账 + 桩时钟。"""
    from app.api.v1 import alerts

    accounts = _accounts()
    rows = _seeds()
    _wire(monkeypatch, accounts)
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", rows)
    monkeypatch.setattr(alerts, "_MEM_RULES", [])
    monkeypatch.setattr(alerts, "_alert_disposal_now", lambda: FIXED_TS)
    monkeypatch.delenv("APP_ENV", raising=False)
    return SimpleNamespace(
        alerts=alerts, rows=rows, accounts=accounts, client=TestClient(app), mp=monkeypatch
    )


@pytest.fixture()
def db_ledger(monkeypatch):
    """有库那条腿：替身连接 + 桩时钟 + 桩 _ensure（schema 由 migrations 负责，不归本件）。"""
    from app.api.v1 import alerts

    accounts = _accounts()
    #: 有库那条腿的行形状＝0014 已经跑过的形状：八枚处置列全在场（无库那条腿故意留几枚缺键，
    #: 用来判 alert_ledger_row 给存量行补列那一格）。
    connection = _LedgerConnection(
        [{**alerts.ALERT_DISPOSAL_DEFAULTS, **row} for row in _seeds()]
    )
    _wire(monkeypatch, accounts)
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_ensure", lambda: None)
    monkeypatch.setattr(alerts, "_conn", lambda: connection)
    monkeypatch.setattr(alerts, "_alert_disposal_now", lambda: FIXED_TS)
    monkeypatch.setenv("APP_ENV", "development")
    return SimpleNamespace(
        alerts=alerts, connection=connection, accounts=accounts,
        client=TestClient(app), mp=monkeypatch,
    )


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _body_for(action: str, target: int, actor: str) -> dict | None:
    if action != "assign":
        return None
    if actor == ADMINISTRATOR and target == FX_ALERT:
        return {"assignee": ADMINISTRATOR}
    return {"assignee": TARGET_MANAGER}


def _post(client, username: str, target: int, action: str):
    kwargs = {"headers": _headers(username)}
    body = _body_for(action, target, username)
    if body is not None:
        kwargs["json"] = body
    return client.post(f"/api/v1/alerts/{target}/{action}", **kwargs)


def _row(client, username: str, target: int) -> dict:
    return client.get(f"/api/v1/alerts/{target}", headers=_headers(username)).json()["alert"]


def _listed(client, username: str) -> dict[int, dict]:
    return {
        int(row["id"]): row
        for row in client.get("/api/v1/alerts", headers=_headers(username)).json()["alerts"]
    }


def _expected(target: int, username: str) -> tuple[int, str]:
    """这一格对这个目标该怎么答 —— 判据 J-3 唯一一处判表，取值全来自 ``IN_SCOPE``。

    staff / auditor 连资源级那道门都过不了，于是**任何**目标都答同一句 403：存在与否在这一档
    根本不值得区分。过了门的人，看不见的行与不存在的 id 必须同一句话（404 ``resource_not_found``），
    这是平台既有口径（``app/api/v1/chat.py``、``app/api/v1/data.py``、``app/api/v1/artifacts.py``
    早就把越权读答成 404），本单不另立一条。
    """
    if username in (STAFF, AUDITOR):
        return 403, "permission_denied"
    if target in IN_SCOPE[username]:
        return 200, ""
    return 404, "resource_not_found"


# ======================================================= J-1：状态机与"拒了不许改数据"
def test_the_vocabulary_is_closed_and_the_terminal_state_is_named(ledger):
    """词表就是那三枚；``closed`` 是唯一终态；别处不许长出第四枚拼写。"""
    from app.api.v1 import alerts

    assert alerts.ALERT_STATUSES == ("open", "acknowledged", "closed")
    assert alerts.ALERT_TERMINAL_STATUSES == frozenset({"closed"})
    assert alerts.ALERT_ACTIONS == ("ack", "close", "assign")
    # 每一枚动作写的列都在 0014 落盘的列集合里（拼错一枚列名，写库会撞 UndefinedColumn）。
    columns = set(alerts.ALERT_DISPOSAL_DEFAULTS)
    for action, written in alerts.ALERT_DISPOSAL_WRITE_COLUMNS.items():
        assert action in alerts.ALERT_ACTIONS
        assert set(written) <= columns, written


def test_the_state_machine_admits_exactly_the_named_transitions(ledger):
    """三动作 × 三状态 = 9 格，逐格判"合法起点"，并判写完落成哪一格。"""
    from app.api.v1 import alerts

    open_to = {
        "ack": ("acknowledged", True),
        "close": ("closed", True),
        "assign": ("open", True),
    }
    acknowledged_to = {
        "ack": ("acknowledged", False),   # 已经有人认领了：再确认一次不合法，也不许覆盖第一笔
        "close": ("closed", True),
        "assign": ("acknowledged", True),
    }
    closed_to = {"ack": ("acknowledged", False), "close": ("closed", False), "assign": ("open", False)}

    for current, table in (
        ("open", open_to),
        ("acknowledged", acknowledged_to),
        ("closed", closed_to),
    ):
        for action, (target, allowed) in table.items():
            guard = alerts.alert_disposal_guard(action, current)
            assert guard is allowed, f"{action} from {current}: got {guard}, want {allowed}"
            if allowed:
                # 合法跳转的目标必须还在词表里（assign 是原地，不算跳转但也算合法一格）。
                assert alerts.alert_disposal_target_status(action, current) == target
            else:
                assert alerts.alert_disposal_target_status(action, current) is None
    # 词表外的当前状态与没指名的动作都进不来。
    assert alerts.alert_disposal_guard("ack", "resolved") is False
    assert alerts.alert_disposal_guard("reopen", "closed") is False


def test_writes_refuse_an_illegal_transition_instead_of_returning_an_empty_one(ledger):
    """守卫与写集是一根链子：没判守卫就调写集，要抛，不许回一份空写集让人安静地什么都不做。"""
    from app.api.v1 import alerts

    with pytest.raises(ValueError, match="非法的告警处置跳转"):
        alerts.alert_disposal_writes("ack", "closed", actor=OWN_MANAGER, disposed_at=FIXED_TS)
    columns, values = alerts.alert_disposal_writes(
        "assign", "open", actor=OWN_MANAGER, assignee=TARGET_MANAGER, disposed_at=FIXED_TS
    )
    assert columns == ("assignee", "assigned_by", "assigned_at")
    assert values == (TARGET_MANAGER, OWN_MANAGER, FIXED_TS)


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_a_refused_transition_leaves_the_row_untouched_on_both_sides(ledger, action):
    """J-1 的行为侧：已关闭 → 任何动作都是 409，而**读写两侧**都取证说没改过。"""
    response = _post(ledger.client, OWN_MANAGER, CLOSED_ALERT, action)

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "conflict", response.text
    after = _row(ledger.client, OWN_MANAGER, CLOSED_ALERT)
    assert after["status"] == "closed"
    assert after["closed_by"] == FIRST_CLOSER and after["closed_at"] == FIRST_CLOSE_TS
    assert after["acknowledged_by"] == "" and after["acknowledged_at"] == ""
    assert after["assignee"] == "" and after["assigned_by"] == "" and after["assigned_at"] == ""
    # 台账里那一行本身（不是响应编出来的）也没动。
    stored = next(row for row in ledger.rows if row["id"] == CLOSED_ALERT)
    assert stored["status"] == "closed"
    assert stored.get("acknowledged_by", "") == "" and stored.get("assignee", "") == ""


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_a_refused_transition_emits_no_write_at_all_on_the_database_leg(db_ledger, action):
    """有库那条腿的"拒的时候数据没被改写"：409 之后语句账里一条 UPDATE 都没有，更没 commit。"""
    before = dict(db_ledger.connection.rows[CLOSED_ALERT])

    response = _post(db_ledger.client, OWN_MANAGER, CLOSED_ALERT, action)

    assert response.status_code == 409, response.text
    assert db_ledger.connection.updates() == [], db_ledger.connection.statements()
    assert db_ledger.connection.commits == 0, db_ledger.connection.statements()
    assert db_ledger.connection.rows[CLOSED_ALERT] == before


def test_a_second_ack_is_refused_and_keeps_the_first_acknowledger(ledger):
    """「谁第一次认领了这条」是台账上唯一那句关于认领的话，后一次点击不许把它覆盖。"""
    response = _post(ledger.client, OWN_MANAGER, ACKED_ALERT, "ack")

    assert response.status_code == 409, response.text
    after = _row(ledger.client, OWN_MANAGER, ACKED_ALERT)
    assert after["acknowledged_by"] == FIRST_ACKER
    assert after["acknowledged_at"] == FIRST_ACK_TS


# ================================================================ J-2：三件动作可寻址
def test_ack_is_addressable_and_reads_back_who_when_and_what(ledger):
    """确认：读回的行逐字段说清「谁、什么时候、对哪条告警做了什么」，详情与列表同口径。"""
    response = _post(ledger.client, OWN_MANAGER, OWN_ALERT, "ack")

    assert response.status_code == 200, response.text
    body = response.json()["alert"]
    assert body["id"] == OWN_ALERT
    assert body["status"] == "acknowledged"
    assert body["acknowledged_by"] == OWN_MANAGER
    assert body["acknowledged_at"] == FIXED_TS
    # 别的动作一格都不许被顺带写掉，通知已读那一格也不归处置动（R188 的账）。
    assert body["closed_by"] == "" and body["closed_at"] == ""
    assert body["assignee"] == "" and body["assigned_by"] == "" and body["assigned_at"] == ""
    assert body["read"] is False
    assert body["message"] == OWN_MESSAGE and body["department"] == DEPT_OWN

    assert _row(ledger.client, OWN_MANAGER, OWN_ALERT) == body, "详情读的不是刚写进去的那一版"
    assert _listed(ledger.client, OWN_MANAGER)[OWN_ALERT] == body, "列表还停在处置之前的状态"
    stored = next(row for row in ledger.rows if row["id"] == OWN_ALERT)
    assert stored["status"] == "acknowledged" and stored["acknowledged_by"] == OWN_MANAGER


def test_close_is_addressable_from_an_acknowledged_alert(ledger):
    """关闭：确认过的告警能关；关完之后处置人、时间、终态三样都读得到。"""
    response = _post(ledger.client, OWN_MANAGER, ACKED_ALERT, "close")

    assert response.status_code == 200, response.text
    body = response.json()["alert"]
    assert body["status"] == "closed"
    assert body["closed_by"] == OWN_MANAGER and body["closed_at"] == FIXED_TS
    assert body["acknowledged_by"] == FIRST_ACKER, "关闭不许抹掉前一笔确认"
    assert _row(ledger.client, OWN_MANAGER, ACKED_ALERT) == body
    assert _listed(ledger.client, OWN_MANAGER)[ACKED_ALERT] == body


def test_close_without_an_ack_is_legal(ledger):
    """没确认也能直接关：一条已经处置完的告警不必先补一次「我看过了」才销得掉。"""
    body = _post(ledger.client, OWN_MANAGER, OWN_ALERT, "close").json()["alert"]

    assert body["status"] == "closed"
    assert body["acknowledged_by"] == "" and body["acknowledged_at"] == ""
    assert body["closed_by"] == OWN_MANAGER


def test_assign_moves_the_holder_and_leaves_the_state_alone(ledger):
    """转派：换处置人与落「谁派的」，状态一格都不动（派出去不等于决定了）。"""
    response = ledger.client.post(
        f"/api/v1/alerts/{OWN_ALERT}/assign",
        headers=_headers(OWN_MANAGER),
        json={"assignee": TARGET_MANAGER},
    )

    assert response.status_code == 200, response.text
    body = response.json()["alert"]
    assert body["status"] == "open", "转派不许动状态"
    assert body["assignee"] == TARGET_MANAGER
    assert body["assigned_by"] == OWN_MANAGER and body["assigned_at"] == FIXED_TS
    assert body["acknowledged_by"] == "" and body["closed_by"] == ""
    assert _row(ledger.client, OWN_MANAGER, OWN_ALERT) == body
    assert _listed(ledger.client, TARGET_MANAGER)[OWN_ALERT] == body, "接手人读到的必须是派给他那一版"


def test_an_assignee_can_still_ack_and_close_the_alert_assigned_to_him(ledger):
    """闭环真合得上：派给谁之后，那一格对他仍然是合法的起点，他能自己确认再关掉。"""
    ledger.client.post(
        f"/api/v1/alerts/{OWN_ALERT}/assign",
        headers=_headers(OWN_MANAGER),
        json={"assignee": TARGET_MANAGER},
    )

    acked = _post(ledger.client, TARGET_MANAGER, OWN_ALERT, "ack")
    assert acked.status_code == 200, acked.text
    assert acked.json()["alert"]["acknowledged_by"] == TARGET_MANAGER
    closed = _post(ledger.client, TARGET_MANAGER, OWN_ALERT, "close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["alert"]["status"] == "closed"


def test_the_disposal_timestamp_comes_from_the_servers_own_clock(ledger):
    """不桩时钟那一格：让产品那枚函数自己产出时间串，再判落进台账的就是它。

    刻意不在测试里重算一遍 ``datetime.now(...)``：那等于测一份测试自己写的时钟。这里取真函数
    的输出（因此 +08:00 与 ``timespec="seconds"`` 两件事都由产品说了算），把它当作这一笔处置
    的时间戳写进去，再读回来逐字比对。
    """
    live = ledger.alerts._alert_disposal_now()
    ledger.mp.setattr(ledger.alerts, "_alert_disposal_now", lambda: live)

    body = _post(ledger.client, OWN_MANAGER, OWN_ALERT, "ack").json()["alert"]
    parsed = datetime.fromisoformat(body["acknowledged_at"])

    assert body["acknowledged_at"] == live, (body["acknowledged_at"], live)
    assert parsed.utcoffset().total_seconds() == 8 * 3600, live


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_the_database_leg_persists_and_reads_the_disposal_back(db_ledger, action):
    """有库那条腿：UPDATE 真发、commit 真落，再读一次读到的是这张台账**现在**的值。

    反证②（把处置改成只算不写）红在这一格：摘掉 UPDATE 之后，再读回来还是处置之前的行。
    """
    target = OWN_ALERT
    assignee = {"ack": "", "close": "", "assign": TARGET_MANAGER}[action]
    if action == "assign":
        response = db_ledger.client.post(
            f"/api/v1/alerts/{target}/assign", headers=_headers(OWN_MANAGER), json={"assignee": assignee}
        )
    else:
        response = _post(db_ledger.client, OWN_MANAGER, target, action)

    assert response.status_code == 200, response.text
    body = response.json()["alert"]
    if action == "ack":
        assert body["status"] == "acknowledged" and body["acknowledged_by"] == OWN_MANAGER
    elif action == "close":
        assert body["status"] == "closed" and body["closed_by"] == OWN_MANAGER
    else:
        assert body["status"] == "open" and body["assignee"] == TARGET_MANAGER
        assert body["assigned_by"] == OWN_MANAGER
    assert body["acknowledged_at"] == FIXED_TS or body["closed_at"] == FIXED_TS or body["assigned_at"] == FIXED_TS

    updates = db_ledger.connection.updates()
    assert len(updates) == 1, db_ledger.connection.statements()
    sql, params = updates[0]
    assert sql.startswith("UPDATE alerts SET"), sql
    assert params[-1] == target, params
    assert db_ledger.connection.commits == 1, db_ledger.connection.statements()
    # 再读一次（详情走的是同一条归属谓词的 SELECT），读到的是替身里现在的行。
    assert _row(db_ledger.client, OWN_MANAGER, target) == body
    assert db_ledger.connection.rows[target]["status"] == body["status"]


# ================================================= J-3：12 格逐格判 + 存在性不外泄
@pytest.mark.parametrize("role,action", ROLE_MATRIX)
def test_the_role_by_action_matrix_answers_cell_by_cell(ledger, role, action):
    """J-3 的十二格：谁能做、谁不能做、不能做的那一格数据一格都没变。"""
    from app.api.v1 import alerts

    actor = {"staff": STAFF, "manager": OWN_MANAGER, "admin": ADMINISTRATOR, "auditor": AUDITOR}[role]
    expected_status, expected_code = _expected(OWN_ALERT, actor)

    response = _post(ledger.client, actor, OWN_ALERT, action)

    assert response.status_code == expected_status, response.text
    if expected_code:
        assert response.json()["detail"] == expected_code, response.text
        stored = next(row for row in ledger.rows if row["id"] == OWN_ALERT)
        assert alerts.alert_row_status(stored) == "open", "被拒的一格不许把行推向前"
        assert stored.get("acknowledged_by", "") == "" and stored.get("assignee", "") == ""
    else:
        assert response.json()["alert"]["id"] == OWN_ALERT


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_a_foreign_row_and_a_missing_id_answer_byte_for_byte_the_same(ledger, action):
    """过了资源级那道门的人，也不许用状态码之差试出「这条告警在不在」。

    别部门的行（存在、内容不归他）与一个从没出现过的 id 必须同一句话：404
    ``resource_not_found`` + 同一个响应体。这条口径不是本单发明的：详情读、列表读与
    ``app/api/v1/chat.py`` / ``app/api/v1/data.py`` / ``app/api/v1/artifacts.py`` 早就这么答。
    """
    foreign = _post(ledger.client, OWN_MANAGER, FX_ALERT, action)
    missing = _post(ledger.client, OWN_MANAGER, MISSING_ALERT, action)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json(), (foreign.text, missing.text)
    assert foreign.json()["detail"] == "resource_not_found"
    # 详情读同一条口径，否则「能不能 GET 到」又是一条存在性信道。
    assert (
        ledger.client.get(f"/api/v1/alerts/{FX_ALERT}", headers=_headers(OWN_MANAGER)).json()
        == ledger.client.get(f"/api/v1/alerts/{MISSING_ALERT}", headers=_headers(OWN_MANAGER)).json()
    )
    # 列表里根本没有这一条：三处读法给出的可见集合必须是同一个。
    assert FX_ALERT not in _listed(ledger.client, OWN_MANAGER)


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_a_denial_at_the_resource_gate_does_not_reveal_anything_either(ledger, action):
    """staff / auditor：门在任何一次查行之前就已经把人的能力判掉了。

    对存在的行、别人部门的行、不存在的 id 三格都答同一句 403，所以「403 还是 404」根本试不出
    任何东西 —— 这一档不需要知道存在性，因为它连这一条能不能读都还没被问。
    """
    for actor in (STAFF, AUDITOR):
        bodies = set()
        for target in (OWN_ALERT, FX_ALERT, MISSING_ALERT):
            response = _post(ledger.client, actor, target, action)
            assert response.status_code == 403, response.text
            assert response.json()["detail"] == "permission_denied", response.text
            bodies.add(response.text)
        assert len(bodies) == 1, (actor, bodies)


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_a_manager_of_another_department_sees_nothing_to_act_on(ledger, action):
    """fx 部门的 manager 对本部门的行：与不存在的 id 同答 404，且不留下任何一行改动。"""
    before = dict(next(row for row in ledger.rows if row["id"] == OWN_ALERT))

    response = _post(ledger.client, FX_MANAGER, OWN_ALERT, action)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "resource_not_found"
    assert next(row for row in ledger.rows if row["id"] == OWN_ALERT) == before


@pytest.mark.parametrize("action", ("ack", "close", "assign"))
def test_an_unattributed_row_is_disposable_for_whoever_cleared_the_gate(ledger, action):
    """无归属历史行：与 alert_row_visible 既有口径一致 —— 过了门就看得见，也就处置得了。

    派给谁这一格除外：转派目标同样要看得见这一条，而任何人都看得见它，所以合法。
    """
    response = _post(ledger.client, OWN_MANAGER, LEGACY_ALERT, action)

    assert response.status_code == 200, response.text
    assert response.json()["alert"]["id"] == LEGACY_ALERT


@pytest.mark.parametrize(
    "assignee",
    [
        GHOST,                                    # 查无此人
        FX_MANAGER,                               # 真人，但读不到这一行
        STAFF,                                    # 真人，读得到，但没有 alerts:manage
        AUDITOR,                                  # 同上，另一档角色
        _account("r251-suspended", "manager", DEPT_OWN, status="suspended")["username"],
    ],
)
def test_every_ineligible_assignee_refuses_with_one_single_code(ledger, assignee):
    """转派目标不合格的四格（外加停用账号）共用一枚码，响应逐字相同。

    拆开答就是用户名枚举口：「这个人存不存在」「他是什么部门」都不归调用方知道。
    """
    if assignee not in ledger.accounts:
        ledger.accounts[assignee] = _account(assignee, "manager", DEPT_OWN, status="suspended")
    before = dict(next(row for row in ledger.rows if row["id"] == OWN_ALERT))

    response = ledger.client.post(
        f"/api/v1/alerts/{OWN_ALERT}/assign",
        headers=_headers(OWN_MANAGER),
        json={"assignee": assignee},
    )
    ghost = ledger.client.post(
        f"/api/v1/alerts/{OWN_ALERT}/assign",
        headers=_headers(OWN_MANAGER),
        json={"assignee": "r251-nobody-at-all-404"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "validation_error"
    assert ghost.text == response.text, (ghost.text, response.text)
    assert next(row for row in ledger.rows if row["id"] == OWN_ALERT) == before, "拒了就不许落一半"


def test_an_empty_assignee_is_refused_the_same_way(ledger):
    """空串走同一枚码，不新造一句「请填写用户名」的形状。"""
    response = ledger.client.post(
        f"/api/v1/alerts/{OWN_ALERT}/assign", headers=_headers(OWN_MANAGER), json={"assignee": ""}
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "validation_error"


# ============================================================== 审计：只记拒绝那一侧
@pytest.mark.parametrize("role,action", ROLE_MATRIX)
def test_every_refusal_lands_one_line_in_the_existing_ledger(ledger, role, action):
    """12 格里被拒的每一格都在既有那本账（``audit_events``）里留一行，且那行不带别人的内容。

    ``reason`` 取的就是响应那枚稳定码（本件不为审计另开第二份码表），``resource`` 点名是三道口里
    哪一道拒的；别人的告警正文与别人的部门一个字都不进载荷 —— 与
    ``tests/test_r176_alert_denial_audit.py`` 同一个探针口径。
    """
    import json

    actor, target, expected_code = REFUSAL_CELLS[role]

    response = _post(ledger.client, actor, target, action)

    assert response.status_code in (403, 404), response.text
    assert response.json()["detail"] == expected_code, response.text
    rows = [
        event
        for event in get_audit_events(action=ACTION_MANAGE_ALERTS)
        if str(event.get("username") or "") == actor and event.get("outcome") == "denied"
    ]
    assert rows, f"这一格被拒却在账上查无此笔：{role}/{action}"
    line = rows[-1]
    assert line["reason"] == expected_code, line
    assert line["resource"] == ledger.alerts.ALERT_DISPOSAL_RESOURCE, line
    payload = json.dumps(line, ensure_ascii=False)
    assert all(token not in payload for token in FORBIDDEN_IN_AUDIT), line


def test_an_allowed_disposal_adds_exactly_one_audit_line(ledger):
    """R582 改口：处置成功的那一笔必须落一行账。

    旧的那句「成功不记账，因为谁做了什么已经在那行数据上」把 ``alerts`` 的三列时间戳当成了审计账，
    而表列不可追加、也没有主体身份链——客户问「谁在什么时候关掉了这条告警」时台账答不出。
    这一枚钉曾把那句假话钉成常驻，所以随 R582 一起改口，不是放宽：账动作名不许现编，
    只能是被测模块自己派生出来的那一枚（``ALERT_DISPOSAL_AUDIT_ACTIONS``），与判据①同源。

    另一半口径仍然钉死：**读**台账不是一次事件。三次读过去，账上的行数一格都不许动。
    """
    import json

    ledger.mp.setattr(ledger.alerts, "ALERT_DISPOSAL_RESOURCE", "r251-audit-probe-resource")
    action_name = ledger.alerts.ALERT_DISPOSAL_AUDIT_ACTIONS["ack"]
    assert action_name != ACTION_MANAGE_ALERTS, "账动作名必须是被派生出来的那一枚，不是裸权限词"

    def lines() -> list:
        return [
            event
            for event in get_audit_events(action=action_name)
            if str(event.get("username") or "") == OWN_MANAGER
        ]

    before = lines()
    assert _post(ledger.client, OWN_MANAGER, OWN_ALERT, "ack").status_code == 200
    after = lines()

    assert len(after) == len(before) + 1, (before, after)
    line = after[-1]
    assert line["outcome"] == ledger.alerts.ALERT_DISPOSAL_AUDIT_OUTCOME, line
    assert line["reason"] == ledger.alerts.ALERT_DISPOSAL_AUDIT_REASON, line
    assert line["resource"] == "r251-audit-probe-resource", line
    payload = json.dumps(line, ensure_ascii=False)
    assert all(token not in payload for token in FORBIDDEN_IN_AUDIT), line

    # 读台账不是事件：连着读三遍，那一格不许多出行。
    before_read = lines()
    for _ in range(3):
        lines()
    assert lines() == before_read, (before_read, lines())


# ================================================================= 词表与 DDL 同源
def _check_words_from_0014() -> set[str]:
    """从迁移目录现读 0014 那枚 CHECK  admitting 的取值集合（走 loader，不手读文件）。"""
    from app.db.migrations import MIGRATIONS

    from test_r183_184_migration_pair import executable_statements

    item = next(migration for migration in MIGRATIONS if migration.version == NEW_VERSION)
    checks = [
        statement
        for statement in executable_statements(item.sql)
        if "ADD CONSTRAINT" in statement.upper()
    ]
    assert len(checks) == 1, checks
    words = re.findall(r"'([^']*)'", checks[0].split("CHECK", 1)[1])
    assert words, checks
    return set(words)


def test_the_landed_check_and_the_product_vocabulary_are_one_set(ledger):
    """0014 的 CHECK 与 ``ALERT_STATUSES`` 必须逐枚相等：谁多一枚少一枚当场红。"""
    from app.api.v1 import alerts

    assert _check_words_from_0014() == set(alerts.ALERT_STATUSES)
    assert set(alerts.ALERT_DISPOSAL_DEFAULTS["status"] for _ in [0]) <= _check_words_from_0014()


def test_every_status_the_machine_can_write_is_admitted_by_the_check(ledger):
    """状态机写得出的一切，数据库那一腿都不许拒。"""
    from app.api.v1 import alerts

    written = {
        alerts.alert_disposal_target_status(action, current)
        for action in alerts.ALERT_ACTIONS
        for current in alerts.ALERT_STATUSES
        if alerts.alert_disposal_guard(action, current)
    }
    admitted = _check_words_from_0014()
    assert written <= admitted, (written, admitted)
