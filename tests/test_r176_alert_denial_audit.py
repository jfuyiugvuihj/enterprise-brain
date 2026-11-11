"""R176 判据③ —— 告警面的拒绝必须落进既有审计账本，而且不许把内容抄进去。

来历：越权矩阵 R163 在 ``alert_route.staff_read_denial_is_audited`` 与
``alert_route.staff_rule_write_is_denied`` 两格判出 C 类红 —— ``app/api/v1/alerts.py``
全文 ``record_audit`` 出现 0 次，``_require_alert_management``（:96-107）两条 raise 出口
都不记账，而这条门被五个调用点复用 ⇒ 告警面所有能力性拒绝在审计日志里查无此笔。

取舍（写死在报告里，这里只钉结果）：

- 只走既有通路 ``app/common/audit.py::record_audit``（账本集合 ``audit_events``，
  出口 ``GET /api/v1/audit/events``），不自造第二套事件表。
- 只在**拒绝**这一侧记账。跨部门被裁掉的那几行不是一次拒绝事件（与检索按档位裁剪同理），
  台账每次开面板与每次刷新都要读一遍，把放行写成审计只会淹掉账本 —— 这一条由
  ``test_row_scope_narrowing_is_not_fabricated_as_a_denial`` 反向钉住。
- 事件载荷只允许：动作、判定结果、资源名、稳定码、主体。别人的告警正文、部门值、
  密级值一个字都不许进 payload，由 ``test_denial_audit_never_carries_the_foreign_body`` 钉。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.common.audit import AUDIT_COLLECTION, get_audit_events
from app.common.auth import create_token
from app.common.permissions import ACTION_MANAGE_ALERTS
from app.main import app

DEPT_OWN = "r176-own"
DEPT_FOREIGN = "r176-fx"
#: 泄漏探针：正文取 ASCII 主干（中文整句可能被转义而匹配不上，主干不会）。
VICTIM_MESSAGE = "R176T-ALERT-BODY 部门 r176-own 的现金流已经见底"
VICTIM_CLASSIFICATION = "r176core"
#: 这一格不该出现在审计载荷里的三样东西：正文主干、别人的部门值、别人的密级值。
FORBIDDEN_IN_AUDIT = (
    "R176T-ALERT-BODY",
    DEPT_OWN,
    VICTIM_CLASSIFICATION,
    str(AUDIT_COLLECTION),
)
CELL_READ = "alert_route.staff_read_denial_is_audited"
CELL_WRITE = "alert_route.staff_rule_write_is_denied"


def _username(kind: str, cell_id: str) -> str:
    return "r176-" + kind + "-" + cell_id


def _account(kind: str, cell_id: str, **overrides) -> dict:
    user = {
        "id": "u-" + _username(kind, cell_id),
        "username": _username(kind, cell_id),
        "role": kind,
        "department": DEPT_FOREIGN,
    }
    user.update(overrides)
    return user


@pytest.fixture()
def scene(monkeypatch):
    """离线现场：staff / manager / admin 三种身份，台账里躺着别人部门的一条告警正文。"""
    from app.api.v1 import alerts
    from app.common import auth

    accounts: dict[str, dict] = {}

    def _serve(kind: str, cell_id: str, **overrides) -> str:
        username = _username(kind, cell_id)
        accounts[username] = _account(kind, cell_id, **overrides)
        return username

    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [
        {
            "id": 1,
            "rule_id": 1,
            "message": VICTIM_MESSAGE,
            "read": False,
            "department": DEPT_OWN,
            "classification": VICTIM_CLASSIFICATION,
        }
    ])
    monkeypatch.setattr(alerts, "_MEM_RULES", [])
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    return SimpleNamespace(alerts=alerts, accounts=accounts, serve=_serve,
                           client=TestClient(app), mp=monkeypatch)


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _alert_events(username: str = "") -> list[dict]:
    """从**真账本**读回这一格的告警面审计行（按主体归因，不另起一套事件表）。"""
    events = get_audit_events(action=ACTION_MANAGE_ALERTS)
    if username:
        events = [event for event in events if str(event.get("username") or "") == username]
    return events


# ==================== 🔴 两枚 C 格（判据③） ====================


def test_staff_read_denial_is_audited(scene):
    """判据③的红：staff 读台账被拒，之前全件 ``record_audit`` 出现 0 次。"""
    xclear = scene.serve("staff", CELL_READ)

    response = scene.client.get("/api/v1/alerts", headers=_headers(xclear))

    assert response.status_code == 403, "能力性拒绝的口径本件不许改：403"
    assert response.json()["detail"] == "permission_denied", "稳定码同样不许改"
    rows = [event for event in _alert_events(xclear) if event.get("outcome") == "denied"]
    assert rows, (
        "判据③审计缺席：staff 读台账被拒，在审计日志里查不到一笔。"
        f"实测该主体（{xclear}）在 alerts:manage 这个动作下 0 行。"
    )
    row = rows[-1]
    assert row["reason"] == "permission_denied", row
    assert row["resource"] == "alerts", f"审计要看得出是哪一面拒的：{row!r}"


def test_staff_rule_write_is_denied(scene):
    """判据③的红（同一根因的第二格）：写规则被拒同样得记账，而且规则不许落库。"""
    xclear = scene.serve("staff", CELL_WRITE)

    response = scene.client.post(
        "/api/v1/alerts/rules",
        headers=_headers(xclear),
        json={"name": "r176-new-rule", "metric": "cost", "op": "lt", "threshold": 2.0},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"
    assert scene.alerts._MEM_RULES == [], "被拒的写请求不能留下任何一行规则"
    rows = [event for event in _alert_events(xclear) if event.get("outcome") == "denied"]
    assert rows, (
        f"判据③审计缺席：staff 写规则被拒，审计日志里查不到一笔（主体 {xclear}）。"
    )
    assert rows[-1]["resource"] == "alert_rules", (
        "读台账与写规则是两条不同的口，审计里必须分得清是哪条拒的：" + repr(rows[-1])
    )


def test_unauthenticated_gate_exit_is_audited(scene):
    """这道门自己的 401 出口也要留痕（调用点已核：见下面 why）。

    查过调用点才敢这么写：``app/main.py:96-136`` 的 AuthMiddleware 在路由之前就把「没有
    token / token 验不过 / 查无此人」全部答成 401 ``authentication_required``，所以 HTTP 侧
    打不到 ``_require_alert_management`` 的那半条 401 出口 —— 它是给门上留的（离线/内部直调
    与任何不再经过该中间件的挂载点）。因此这一格从门上直接验，而不是伪造成一次 HTTP 请求。
    """
    from fastapi import HTTPException

    before = [
        event
        for event in _alert_events()
        if event.get("outcome") == "denied" and event.get("reason") == "authentication_required"
    ]
    anonymous = SimpleNamespace(state=SimpleNamespace(username="", principal=None), headers={})

    with pytest.raises(HTTPException) as raised:
        scene.alerts._require_alert_management(anonymous)

    assert raised.value.status_code == 401
    assert raised.value.detail == "authentication_required"
    after = [
        event
        for event in _alert_events()
        if event.get("outcome") == "denied" and event.get("reason") == "authentication_required"
    ]
    assert len(after) > len(before), "判据③审计缺席：401 那半条出口不留痕"
    row = after[-1]
    assert row["username"] == "anonymous" and row["resource"] == scene.alerts.ALERT_LEDGER_RESOURCE, row


def test_alert_denials_land_in_the_one_existing_journal(scene):
    """判据③：走的就是既有那本账（``audit_events``），没有第二套事件表。

    两笔都从**运维侧那条读口**再认一次：``GET /api/v1/audit/events`` 的 source 写死了
    ``app.common.audit.get_audit_events``，本件的拒绝行要能从那里读出来，才算进了同一本账。
    """
    from app.api.v1.observability import AUDIT_EVENT_SOURCE

    xclear = scene.serve("staff", "alert_route.denial_uses_the_shared_journal")

    scene.client.get("/api/v1/alerts", headers=_headers(xclear))

    rows = _alert_events(xclear)
    assert rows, "拒绝没进账本"
    row = rows[-1]
    assert str(row["event_id"]).startswith("aud-"), row
    assert row["created_at"] and row["expires_at"], "缺时间戳/保留期的记录不是这本账的形状"
    assert row["policy_version"], "审计行要能追溯到判据版本"
    assert row["outcome"] == "denied" and row["action"] == ACTION_MANAGE_ALERTS, row

    admin = scene.serve("admin", "alert_route.denial_readable_on_the_audit_api")
    listed = scene.client.get(
        "/api/v1/audit/events",
        headers=_headers(admin),
        params={"username": xclear, "action": ACTION_MANAGE_ALERTS, "outcome": "denied"},
    )

    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["source"] == AUDIT_EVENT_SOURCE, payload["source"]
    ids = [str(event.get("event_id")) for event in payload["events"]]
    assert row["event_id"] in ids, (
        "同一本账却读不回来：说明它落在了既有审计通路之外 —— " + str(ids[:5])
    )


def test_denial_audit_never_carries_the_foreign_body(scene):
    """判据③不许泄漏：正文、部门值、密级值一个字都不许抄进审计载荷。

    台账里躺着 r176-own 的一条告警正文；被拒的是 r176-fx 的 staff。他的拒绝记录只需要
    「谁、想干什么、哪一口、判据码」四件事，不需要受害者那条告警长什么样。
    """
    xclear = scene.serve("staff", "alert_route.denial_audit_stays_clean")
    assert scene.alerts._MEM_ALERTS[0]["message"] == VICTIM_MESSAGE

    scene.client.get("/api/v1/alerts", headers=_headers(xclear))

    rows = _alert_events(xclear)
    assert rows, f"这一格的前半截是『有审计』：主体 {xclear} 实测 0 行"
    for row in rows:
        wire = json.dumps(row, ensure_ascii=False, default=str)
        for token in FORBIDDEN_IN_AUDIT:
            assert token not in wire, (
                f"判据③泄漏：审计行把「{token}」抄进了载荷 —— {wire[:400]}"
            )
        assert row["resource_scope"] == {}, f"资源级判定没有资源可抄：{row!r}"
        assert row["before_summary"] == {} and row["after_summary"] == {}, (
            f"拒绝事件不该带正文摘要：{row!r}"
        )


def test_row_scope_narrowing_is_not_fabricated_as_a_denial(scene):
    """反向钉：跨部门被裁掉的那几行不是一次拒绝事件。

    资源级这一层放行、行级裁到 0 行，交回的是 200 + 空页（不是 403，也不是假空的 0）；
    台账每次开面板与每次刷新都要读一遍，把放行写成 denied 会把这本账淹掉。
    """
    xdept = scene.serve("manager", "alert_route.narrowing_is_not_a_denial")
    assert scene.alerts._MEM_ALERTS[0]["department"] == DEPT_OWN

    response = scene.client.get("/api/v1/alerts", headers=_headers(xdept))

    assert response.status_code == 200
    assert response.json()["alerts"] == []
    assert [
        event for event in _alert_events(xdept) if event.get("outcome") == "denied"
    ] == [], "放行的一次阅读不该产生 denied 行；那会把每次开面板都写成告警噪声"
