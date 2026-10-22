# -*- coding: utf-8 -*-
r"""R582 判据①②③④⑤ —— 告警处置的三枚写口必须各落一行 ``audit_events``。

病灶（总控 10-03 现取，跟进单 §154 一）：``app/api/v1/alerts.py`` 全文只有一处写账
（``_audit_alert_denial`` → ``record_audit(..., "denied", ...)``），三枚处置写口
``acknowledge_alert`` / ``close_alert`` / ``assign_alert`` 全部经 ``_dispose_alert``，
**成功路径一个字节都不进 ``audit_events``**。R577 真跑 ``ack → assign → close``（服务端各
200，``alerts`` 表 id=1 已 closed、id=2 acknowledged）之后，按 ``resource/action like
'%alert%'`` 查账交回 **0 行**。客户问「谁在什么时候关掉了这条告警」时账上答不出，只剩
``alerts`` 表那三列时间戳 —— 而表列不是审计账：不可追加，也没有主体身份链。

本件钉住的五格（一格一枚钉，不许合并）：

* **①** 三枚写口各落一行，动作字面量互不相同，且一律派生自在册符号 ``ACTION_MANAGE_ALERTS``
  乘 ``ALERT_ACTIONS`` —— 件里出现一枚写死的 ``"alerts:manage:xxx"`` 常量就红。
* **②** 拒绝那一格的形状一字未改：状态码与 ``detail`` 逐字对账，且 ``denied`` 仍只有
  ``_audit_alert_denial`` 一条通路（AST 现扫全件的 ``record_audit`` 调用点）。
* **③** 转派那一格同时记「谁派的」与「派给谁」，两枚都取**处置之后读回的那一行**。
* **④** 三把反证刀（``KNIVES``）：摘掉写账调用／把三枚动作收成同一枚字面量／账上少了
  assignee 那一格，各自让自己那一格变哑；每把先在未变异的隔离副本上跑正控确认它会咬。
  🔴 变异只落 ``tests/_temp_edit_overlay.py`` 造的隔离副本，盘上那枚 ``alerts.py`` 全程只读，
  每把刀进出各取一次 sha256 对账（``tests/test_r253_no_test_rewrites_a_tracked_file.py`` 的规矩）。
* **⑤** 取数口径只有 ``resource`` / ``action``（外加 ``outcome``）：``audit_events`` **没有
  ``route`` 列**，列名从 0005 的 DDL 现读判住 —— 凡写「按 route 计数」的判据都取不到数。

泄漏口径沿用 R176：正文、部门值、密级值一个字都不许进载荷。今天放行侧也开始记账，那一格
探针就跟着扩到 ``allowed`` 行（``test_the_allowed_line_carries_no_foreign_content``）。

凭据分层：无库那条腿（``_database_available() -> False``）与有库那条腿（本件自带的替身连接）
各钉一遍，因为写账点只有**一枚**、坐在两条腿合流之后 —— 少钉一腿就证不到「两条腿都走到」。
真库没跑：``tests/conftest.py`` 把测试期的 DATABASE_URL 钉在保留端口 1 上。
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common.audit import get_audit_events
from app.common.auth import create_token
from app.common.permissions import ACTION_MANAGE_ALERTS
from app.main import app
from tests import _temp_edit_overlay as overlay

ALERTS_PY = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "alerts.py"

DEPT_OWN = "r582-own"
DEPT_FX = "r582-fx"
DEPT_VICTIM = "r582-victim"
BODY_TOKEN = "R582T-ALERT-BODY"
CLASSIFICATION = "r582core"
#: 泄漏探针（与 R176/R251 同一族口径）：正文主干取 ASCII，中文整句可能被转义而匹配不上。
FORBIDDEN_IN_AUDIT = (BODY_TOKEN, DEPT_FX, DEPT_VICTIM, CLASSIFICATION)

OWN_ALERT = 1
FX_ALERT = 2
ACKED_ALERT = 3
VICTIM_ALERT = 4

ACTOR = "r582-manager-own"
TARGET = "r582-target-own"
FX_MANAGER = "r582-manager-fx"
STAFF = "r582-staff"
ADMINISTRATOR = "r582-admin"

FIXED_TS = "2026-10-03T09:00:00+08:00"

#: 每枚动作一个**合法起点**的行：ack 从 open，close 从 acknowledged，assign 从 open。
PROBE_CELLS = (
    ("ack", OWN_ALERT),
    ("close", ACKED_ALERT),
    ("assign", OWN_ALERT),
)


def _account(username: str, role: str, department: str, **overrides) -> dict:
    account = {"id": "u-" + username, "username": username, "role": role, "department": department}
    account.update(overrides)
    return account


def _accounts() -> dict[str, dict]:
    return {
        ACTOR: _account(ACTOR, "manager", DEPT_OWN),
        TARGET: _account(TARGET, "manager", DEPT_OWN),
        FX_MANAGER: _account(FX_MANAGER, "manager", DEPT_FX),
        ADMINISTRATOR: _account(ADMINISTRATOR, "admin", ""),
        STAFF: _account(STAFF, "staff", DEPT_OWN),
    }


def _seeds() -> list[dict]:
    """四枚行：本部门 / 别部门 / 已确认 / 受害行（admin 全见，用来喂泄漏探针）。"""
    base = {"rule_id": 7, "ai_analysis": "", "read": False, "created_at": "2026-10-03T08:00:00+08:00"}
    return [
        {**base, "id": OWN_ALERT, "message": BODY_TOKEN + " 本部门营收跌破阈值",
         "department": DEPT_OWN, "classification": CLASSIFICATION},
        {**base, "id": FX_ALERT, "message": BODY_TOKEN + " 别部门毛利跌破阈值",
         "department": DEPT_FX, "classification": CLASSIFICATION},
        {**base, "id": ACKED_ALERT, "message": BODY_TOKEN + " 已确认待关闭",
         "department": DEPT_OWN, "classification": CLASSIFICATION,
         "status": "acknowledged", "acknowledged_by": "r582-first-acker",
         "acknowledged_at": "2026-10-03T08:30:00+08:00"},
        {**base, "id": VICTIM_ALERT, "message": BODY_TOKEN + " 受害部门现金流见底",
         "department": DEPT_VICTIM, "classification": CLASSIFICATION},
    ]


def _principal(username: str) -> Principal:
    return Principal.from_user(_accounts()[username])


def _alerts_source() -> str:
    """盘上那枚件的字（**换行统一成 LF**）：刀锚点与 AST 都按这一份算，盘上原件只读。

    盘上是单形 CRLF（交工纸 §一/§七 现算自证 ``count('\r') == count('\n') == count('\r\n') == 行数``），
    锚点若按 CRLF 拼就得把每枚锚点写两遍换行；统一取 LF 之后，变异只存在于内存里那一份字节。
    """
    return ALERTS_PY.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _tracked_sha() -> str:
    return hashlib.sha256(ALERTS_PY.read_bytes()).hexdigest()[:12]


# ------------------------------------------------------------------ 账（按 resource/action 取数）
def _journal(action_literal: str, resource: str = "") -> list[dict]:
    """判据⑤：这本账只有 ``action`` / ``resource`` / ``outcome`` 三把钥匙可寻址。

    ``audit_events`` 没有 ``route`` 列（``test_the_ledger_has_no_route_column`` 钉住），所以这里
    一次都不按 route 取数，也不许任何断言偷偷改用 HTTP 路径名。
    """
    rows = get_audit_events(action=action_literal)
    if resource:
        rows = [row for row in rows if row.get("resource") == resource]
    return rows


def _since(before: set[str]) -> list[dict]:
    """因为这一次处置而多出来的账行（不靠「此刻盘面脏不脏」这类永真判据）。"""
    return [row for row in get_audit_events() if str(row.get("event_id")) not in before]


def _snapshot() -> set[str]:
    return {str(row.get("event_id")) for row in get_audit_events()}


# ------------------------------------------------------------------ 替身连接（有库那条腿）
class _StubConnection:
    """``alerts`` 的极小替身：只认处置这条腿真会发的两类语句，按 id 落值。

    定位与 ``tests/test_r251_alert_disposal.py::_LedgerConnection`` 同级：给本单判据当凭据，
    产品代码不读它，也不是第二份 schema 事实源。归属谓词不在这里求值（那是再造一份行级判定）。
    """

    def __init__(self, rows: list[dict]):
        self.rows = {int(row["id"]): dict(row) for row in rows}
        self.commits = 0
        self.updates = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        args = tuple(params or ())
        if text.startswith("SELECT * FROM alerts WHERE id = %s"):
            row = self.rows.get(int(args[0]))
            return _StubCursor([dict(row)] if row else [], 1 if row else 0)
        if text.startswith("UPDATE alerts SET"):
            columns = re.findall(r"(\w+) = %s", text.split(" WHERE ")[0])
            assert len(columns) == len(args) - 1, (text, args)
            row = self.rows.get(int(args[-1]))
            if row is None:
                return _StubCursor([], 0)
            row.update(zip(columns, args[:-1]))
            self.updates += 1
            return _StubCursor([], 1)
        raise AssertionError("处置这条腿不该发出别的语句：" + text)

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("写成了却回滚：本件的替身不接受这种形状")


class _StubCursor:
    def __init__(self, rows: list[dict], rowcount: int):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None


# ------------------------------------------------------------------ 现场
def _wire(monkeypatch) -> dict[str, dict]:
    from app.common import auth

    accounts = _accounts()
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    return accounts


def _arm_memory_leg(module, monkeypatch) -> None:
    """把「无库那条腿」装进给定那枚模块：活模块与隔离副本共用同一套装法（判据④要用后者）。"""
    monkeypatch.setattr(module, "_database_available", lambda: False)
    monkeypatch.setattr(module, "_MEM_ALERTS", _seeds())
    monkeypatch.setattr(module, "_MEM_RULES", [])
    monkeypatch.setattr(module, "_alert_disposal_now", lambda: FIXED_TS)
    monkeypatch.delenv("APP_ENV", raising=False)


@pytest.fixture()
def scene(monkeypatch):
    """真 HTTP 出口 + 无库那条腿：三枚写口各处置一次，账上应当多三行。"""
    from app.api.v1 import alerts

    _wire(monkeypatch)
    _arm_memory_leg(alerts, monkeypatch)
    return SimpleNamespace(alerts=alerts, client=TestClient(app), mp=monkeypatch)


@pytest.fixture()
def db_scene(monkeypatch):
    """有库那条腿：替身连接 + 桩 ``_ensure``，写账点与内存腿必须是同一枚。"""
    from app.api.v1 import alerts

    _wire(monkeypatch)
    connection = _StubConnection(
        [{**alerts.ALERT_DISPOSAL_DEFAULTS, **row} for row in _seeds()]
    )
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_ensure", lambda: None)
    monkeypatch.setattr(alerts, "_conn", lambda: connection)
    monkeypatch.setattr(alerts, "_alert_disposal_now", lambda: FIXED_TS)
    monkeypatch.setenv("APP_ENV", "development")
    return SimpleNamespace(
        alerts=alerts, connection=connection, client=TestClient(app), mp=monkeypatch
    )


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _dispose(client, username: str, alert_id: int, action: str, assignee: str = ""):
    kwargs = {"headers": _headers(username)}
    if action == "assign":
        kwargs["json"] = {"assignee": assignee}
    return client.post(f"/api/v1/alerts/{alert_id}/{action}", **kwargs)


def _action_literal(module, action: str) -> str:
    return module.ALERT_DISPOSAL_AUDIT_ACTIONS[action]


def _bite(module, actor: str = ACTOR) -> dict[str, list[dict]]:
    """在给定那枚模块上把三枚动作各处置一次，交回「每一枚动作账上多出来的行」。

    判据①③与三把刀共用这一枚把手：刀下与正控走的是同一条取数路，差别只在装进去的那份字节。
    """
    out: dict[str, list[dict]] = {}
    for action, alert_id in PROBE_CELLS:
        before = _snapshot()
        assignee = TARGET if action == "assign" else ""
        module._dispose_alert(_principal(actor), alert_id, action, assignee)
        out[action] = _since(before)
    return out


# ============================================================================ 判据①
@pytest.mark.parametrize("action,alert_id", PROBE_CELLS)
def test_each_disposal_outlet_lands_exactly_one_allowed_line(scene, action, alert_id):
    """①：三枚写口各落**一行**账，判定词是放行，资源名与拒绝那一格同一道口子。"""
    before = _snapshot()

    response = _dispose(scene.client, ACTOR, alert_id, action, TARGET if action == "assign" else "")

    assert response.status_code == 200, response.text
    rows = _since(before)
    assert len(rows) == 1, (
        f"判据①：{action} 处置成功（200）却落了 {len(rows)} 行账，要求恰好一行 —— "
        + json.dumps(rows, ensure_ascii=False)[:400]
    )
    row = rows[0]
    assert row["action"] == _action_literal(scene.alerts, action), row
    assert row["outcome"] == scene.alerts.ALERT_DISPOSAL_AUDIT_OUTCOME, row
    assert row["resource"] == scene.alerts.ALERT_DISPOSAL_RESOURCE, row
    assert row["username"] == ACTOR, row
    assert str(row["event_id"]).startswith("aud-"), row
    assert row["created_at"] and row["expires_at"] and row["policy_version"], row


def test_the_three_action_literals_are_distinct_and_derived_from_the_registered_symbol(scene):
    """①：三枚字面量互不相同，且一律派生自 ``ACTION_MANAGE_ALERTS``——写死一枚就红。"""
    alerts = scene.alerts
    table = alerts.ALERT_DISPOSAL_AUDIT_ACTIONS
    assert set(table) == set(alerts.ALERT_ACTIONS), table
    assert len(set(table.values())) == len(alerts.ALERT_ACTIONS), (
        "判据①：三枚处置动作在账上必须互不相同，实测 " + repr(table)
    )
    for action in alerts.ALERT_ACTIONS:
        assert table[action] == f"{ACTION_MANAGE_ALERTS}:{action}", (
            f"判据①：动作名要走在册符号（ACTION_MANAGE_ALERTS 乘 ALERT_ACTIONS），{action} 对不上"
        )
    hardcoded = sorted(
        node.value.value
        for node in ast.walk(ast.parse(_alerts_source()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value.startswith(ACTION_MANAGE_ALERTS + ":")
    )
    assert not hardcoded, "判据①：件里现编了写死的动作字面量 " + repr(hardcoded)
    # 三枚写口真的各走各的名字：同一场里处置三次，账上应当是三种 action
    for action, alert_id in PROBE_CELLS:
        _dispose(scene.client, ACTOR, alert_id, action, TARGET if action == "assign" else "")
    landed = {row["action"] for row in _journal(_action_literal(alerts, "ack"))} | {
        row["action"] for row in _journal(_action_literal(alerts, "close"))
    } | {row["action"] for row in _journal(_action_literal(alerts, "assign"))}
    assert landed == set(table.values()), landed


def test_the_disposal_line_lands_in_the_one_existing_journal(scene):
    """①的落点：那行账在既有 ``audit_events`` 里，能从运维读口再认一次，不是第二套事件表。"""
    from app.api.v1.observability import AUDIT_EVENT_SOURCE

    before = _snapshot()
    _dispose(scene.client, ACTOR, OWN_ALERT, "ack")
    row = _since(before)[-1]

    listed = scene.client.get(
        "/api/v1/audit/events",
        headers=_headers(ADMINISTRATOR),
        params={"username": ACTOR, "action": row["action"], "outcome": row["outcome"]},
    )

    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["source"] == AUDIT_EVENT_SOURCE, payload["source"]
    ids = [str(event.get("event_id")) for event in payload["events"]]
    assert row["event_id"] in ids, "同一本账却读不回来：" + str(ids[:5])


@pytest.mark.parametrize("action,alert_id", PROBE_CELLS)
def test_the_durable_leg_lands_the_same_one_line(db_scene, action, alert_id):
    """①的第二条腿：写账点只有一枚、坐在两条腿合流之后，所以有库那条腿同样各落一行。"""
    alerts = db_scene.alerts
    before = _snapshot()
    updates_before = db_scene.connection.updates

    response = _dispose(db_scene.client, ADMINISTRATOR, alert_id, action,
                        TARGET if action == "assign" else "")

    assert response.status_code == 200, response.text
    assert db_scene.connection.updates == updates_before + 1, "这一腿根本没写库，账却落了"
    rows = _since(before)
    assert len(rows) == 1, (
        f"判据①（有库腿）：{action} 落成后应恰好一行，实测 {len(rows)} 行"
    )
    assert rows[0]["action"] == _action_literal(alerts, action), rows[0]
    assert rows[0]["outcome"] == alerts.ALERT_DISPOSAL_AUDIT_OUTCOME, rows[0]
    status = rows[0]["after_summary"]["status"]
    stored = str(db_scene.connection.rows[alert_id].get("status") or "open")
    assert status == stored, (
        f"账上写的状态与库里现在那一版不一致：账={status} 库={stored}"
    )


# ============================================================================ 判据②
@pytest.mark.parametrize(
    "actor,alert_id,action,assignee,status_code,detail",
    [
        (STAFF, OWN_ALERT, "ack", "", 403, "permission_denied"),
        (STAFF, OWN_ALERT, "close", "", 403, "permission_denied"),
        (STAFF, OWN_ALERT, "assign", TARGET, 403, "permission_denied"),
        (FX_MANAGER, OWN_ALERT, "ack", "", 404, "resource_not_found"),
        (ADMINISTRATOR, 999999, "close", "", 404, "resource_not_found"),
        (ACTOR, ACKED_ALERT, "ack", "", 409, "conflict"),
        (ACTOR, ACKED_ALERT, "assign", "r582-nobody", 400, "validation_error"),
    ],
)
def test_a_refusal_keeps_its_exact_shape_and_lands_one_denied_line_only(
    scene, actor, alert_id, action, assignee, status_code, detail
):
    """②：拒绝那一格的状态码与 ``detail`` 逐字未动，而且账上仍只有 ``denied`` 那一面。"""
    before = _snapshot()

    response = _dispose(scene.client, actor, alert_id, action, assignee)

    assert response.status_code == status_code, response.text
    assert response.json()["detail"] == detail, response.text
    rows = _since(before)
    denied = [row for row in rows if row["outcome"] == "denied"]
    allowed = [row for row in rows if row["outcome"] == "allowed"]
    assert len(denied) == 1, ("判据②：一次拒绝必须恰好一笔账，实测 " + str(len(denied)))
    assert allowed == [], f"判据②：被拒的那一笔不许落 allowed 行 —— {allowed!r}"
    assert rows == denied, f"除这一笔拒绝之外不许多出任何账行：{rows!r}"
    row = denied[0]
    assert row["action"] == ACTION_MANAGE_ALERTS, row
    assert row["resource"] == scene.alerts.ALERT_DISPOSAL_RESOURCE, row
    assert row["reason"] == detail, row


def test_denied_still_has_exactly_one_path_and_allowed_one_path(scene):
    """②＋①：全件的 ``record_audit`` 调用点现扫——``denied`` 只走 ``_audit_alert_denial``，``allowed`` 只走 ``_audit_alert_disposal``。"""
    sites = _record_audit_sites(_alerts_source())
    assert set(sites) == {"_audit_alert_denial", "_audit_alert_disposal"}, (
        "判据②：拒绝通路唯一 / 判据①：处置写账点唯一。实测调用点 " + repr(sites)
    )
    assert sites["_audit_alert_denial"] == ["denied"], sites
    assert sites["_audit_alert_disposal"] == [scene.alerts.ALERT_DISPOSAL_AUDIT_OUTCOME], sites


def _record_audit_sites(source: str) -> dict[str, list[str]]:
    """谁在什么函数里调 ``record_audit``，判定词取第三枚位置参数（常量名现解）。"""
    tree = ast.parse(source)
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants[node.targets[0].id] = node.value.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                constants[node.target.id] = node.value.value
    owners = [
        (node.name, node.lineno, (node.end_lineno or node.lineno))
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def owner_of(lineno: int) -> str:
        for name, start, end in owners:
            if start <= lineno <= end:
                return name
        return "<module>"

    def literal(node) -> str:
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Name):
            return constants.get(node.id, node.id)
        return "<expr>"

    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
        if name != "record_audit":
            continue
        outcome = literal(node.args[2]) if len(node.args) >= 3 else ""
        out.setdefault(owner_of(node.lineno), []).append(outcome)
    return out


# ============================================================================ 判据③
def test_assign_lands_both_the_assigner_and_the_assignee(scene):
    """③：转派那一格账上同时有「谁派的」与「派给谁」，两枚都取处置之后读回的那一行。"""
    before = _snapshot()

    response = _dispose(scene.client, ACTOR, OWN_ALERT, "assign", TARGET)

    assert response.status_code == 200, response.text
    rows = _since(before)
    assert len(rows) == 1, rows
    summary = rows[0]["after_summary"]
    assert summary.get("assignee") == TARGET, f"判据③：账上少了「派给谁」那一格 —— {summary!r}"
    assert summary.get("assigned_by") == ACTOR, f"判据③：账上少了「谁派的」那一格 —— {summary!r}"
    assert summary.get("actor") == ACTOR, summary
    assert summary["assignee"] != summary["assigned_by"], (
        "派单人与接手人写成同一枚，就等于只记了前者：" + repr(summary)
    )
    assert rows[0]["action"] == _action_literal(scene.alerts, "assign"), rows[0]
    # 行本身也说同一句话：账与 alerts 行不能各写一套
    row = scene.client.get(
        f"/api/v1/alerts/{OWN_ALERT}", headers=_headers(TARGET)
    ).json()["alert"]
    assert (row["assignee"], row["assigned_by"]) == (summary["assignee"], summary["assigned_by"]), row


def test_ack_and_close_name_the_actor_in_the_same_shape(scene):
    """③的对照：确认与关闭没有接手人，但「谁做的」照样在场（三枚写口同形，不各写一套）。"""
    for action, alert_id in (("ack", OWN_ALERT), ("close", ACKED_ALERT)):
        before = _snapshot()

        response = _dispose(scene.client, ACTOR, alert_id, action)

        assert response.status_code == 200, (action, response.text)
        rows = _since(before)
        assert len(rows) == 1, (action, rows)
        assert rows[0]["after_summary"]["actor"] == ACTOR, rows[0]
        assert rows[0]["after_summary"]["action"] == action, rows[0]


# ============================================================================ 泄漏口径
@pytest.mark.parametrize("action,alert_id", PROBE_CELLS)
def test_the_allowed_line_carries_no_foreign_content(scene, action, alert_id):
    """R176 那枚泄漏探针今天照适用于放行侧：正文、部门值、密级值一个字都不进载荷。"""
    before = _snapshot()

    response = _dispose(scene.client, ADMINISTRATOR, VICTIM_ALERT, action,
                        ADMINISTRATOR if action == "assign" else "")

    assert response.status_code == 200, response.text
    for row in _since(before):
        wire = json.dumps(row, ensure_ascii=False, default=str)
        for token in FORBIDDEN_IN_AUDIT:
            assert token not in wire, f"泄漏：审计行把「{token}」抄进了载荷 —— {wire[:400]}"
        assert row["resource_scope"] == {}, row
        assert row["before_summary"] == {}, row


# ============================================================================ 判据⑤
def test_the_ledger_has_no_route_column(scene):
    """⑤：``audit_events`` 没有 ``route`` 列——列名从 0005 的 DDL 现读，凡写「按 route 计数」的判据取不到数。"""
    from app.db.migrations import MIGRATIONS

    item = next(migration for migration in MIGRATIONS if migration.version == "0005")
    body = item.sql.split("CREATE TABLE IF NOT EXISTS audit_events (", 1)[1].split("\n);", 1)[0]
    columns = {
        line.strip().split()[0]
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("--")
    }
    assert "route" not in columns, "判据⑤的前提被推翻了：" + repr(sorted(columns))
    assert {"action", "resource", "outcome"} <= columns, sorted(columns)
    assert re.search(r"\broute\b", item.sql, re.I) is None, "迁移里出现了 route 字样，取数口径要重判"


# ============================================================================ 判据④
#: 三把刀的锚点全部现读唯一（0 处或 >1 处都当场红）。victim 一栏写「摘掉它，哪一枚主钉会跟着变哑」。
KNIVES: dict[str, dict[str, str]] = {
    "K1_record_audit_call_dropped": {
        # 整枚调用一并摘掉：只摘头几行会留下悬空的实参，编译都过不去（那不是刀，是语法错）。
        "anchor": (
            "    audit_log.record_audit(\n"
            "        principal,\n"
            "        ALERT_DISPOSAL_AUDIT_ACTIONS[action],\n"
            "        ALERT_DISPOSAL_AUDIT_OUTCOME,\n"
            "        ALERT_DISPOSAL_RESOURCE,\n"
            "        ALERT_DISPOSAL_AUDIT_REASON,\n"
            "        after_summary={\n"
            '            \"actor\": str(getattr(principal, \"username\", \"\") or \"\"),\n'
            '            \"alert_id\": int(alert_id),\n'
            '            \"action\": action,\n'
            '            \"status\": str(row.get(\"status\") or ALERT_STATUS_OPEN),\n'
            '            \"assigned_by\": str(row.get(\"assigned_by\") or \"\"),\n'
            '            \"assignee\": str(row.get(\"assignee\") or \"\"),\n'
            "        },\n"
            "    )\n"
        ),
        "replace": "    return None  # 刀①：摘掉写账调用\n",
        "victim": "test_each_disposal_outlet_lands_exactly_one_allowed_line",
        "expect": "empty",
    },
    "K2_three_actions_collapse_to_one_literal": {
        "anchor": '    action: f"{ACTION_MANAGE_ALERTS}:{action}" for action in ALERT_ACTIONS\n',
        "replace": '    action: f"{ACTION_MANAGE_ALERTS}:{ALERT_ACTIONS[0]}" for action in ALERT_ACTIONS\n',
        "victim": "test_the_three_action_literals_are_distinct_and_derived_from_the_registered_symbol",
        "expect": "merged",
    },
    "K3_assignee_cell_dropped": {
        "anchor": '            "assignee": str(row.get("assignee") or ""),\n',
        "replace": "",
        "victim": "test_assign_lands_both_the_assigner_and_the_assignee",
        "expect": "no_assignee",
    },
}


def _isolated(text: str, monkeypatch):
    """把一份字节装进**新造**的隔离模块：盘上那枚 ``alerts.py`` 与活模块都不开口。"""
    from app.api.v1 import alerts

    probe = overlay.isolated_module(alerts, text, str(ALERTS_PY))
    _arm_memory_leg(probe, monkeypatch)
    return probe


@pytest.mark.parametrize("knife", sorted(KNIVES))
def test_every_knife_blinds_the_nail_it_targets(knife, monkeypatch):
    """④：三把刀各自让各自那一格变哑；同一把先在未变异的隔离副本上跑正控，确认它会咬。"""
    spec = KNIVES[knife]
    _wire(monkeypatch)
    before_sha = _tracked_sha()
    source = _alerts_source()
    assert source.count(spec["anchor"]) == 1, f"{knife} 的锚点不唯一（刀等于没动东西）"
    mutated = source.replace(spec["anchor"], spec["replace"])
    assert mutated != source, knife

    control = _bite(_isolated(source, monkeypatch))
    under = _bite(_isolated(mutated, monkeypatch))

    if spec["expect"] == "empty":
        assert [len(control[action]) for action, _ in PROBE_CELLS] == [1, 1, 1], control
        assert [len(under[action]) for action, _ in PROBE_CELLS] == [0, 0, 0], (
            f"刀①摘掉 {spec['victim']} 的写账调用之后，账上仍有行 —— 那枚主钉是假的"
        )
    elif spec["expect"] == "merged":
        assert len({row["action"] for rows in control.values() for row in rows}) == 3, control
        merged = {row["action"] for rows in under.values() for row in rows}
        assert len(merged) == 1, f"刀②把三枚动作收成同一枚之后仍交出多种动作名：{merged}"
        assert [len(rows) for rows in under.values()] == [1, 1, 1], (
            "刀②只许把名字收成同一枚，不许顺手把账也摘掉：" + repr(under)
        )
    else:
        assignee_cells = [row["after_summary"].get("assignee") for row in control["assign"]]
        assert assignee_cells == [TARGET], control
        missing = [
            "assignee" not in row["after_summary"] for row in under["assign"]
        ]
        assert all(missing), f"刀③摘掉 assignee 那一格之后账上还在：{under['assign']}"

    assert _tracked_sha() == before_sha, (
        f"{knife} 把盘上那枚 alerts.py 改了（摘前 {before_sha} → 摘后 {_tracked_sha()}）"
    )
