"""R176 判据①② —— 告警台账的行级归属（改前先红，修完必绿）。

来历：越权矩阵 R163 在 `alert_route.foreign_manager_reads_scoped_alert` 这一格判出
🔴 A 类内容越权 —— 任一部门的 manager 打 `GET /api/v1/alerts` 就能拿到别人部门的告警正文。
那枚矩阵文件红着，不许进本树（会把主树基线钉死），所以这里按 R163 的命名口径自造最小复现：
身份 `r176-<kind>-<cell_id>`、部门 `r176-own` / `r176-fx`、正文令牌 `R176T-ALERT-*`。
落点全部走 tmp_path 与 monkeypatch 出来的内存台账，不碰 `data/**`。

两层判定各管各的，缺一不可：

- 资源级授权（``_require_alert_management``）：这个人到底能不能用告警功能。staff 顶回来
  403 + 稳定码 ``permission_denied``，这条口径本件一个字都不改。
- 行级归属（``alert_row_visible`` / ``alert_row_scope_sql``）：这一条告警是不是他的部门。
  过得了第一层，不等于每一条都归他读。

管理员豁免沿用平台唯一那一条判定（``app/common/policy.py::is_administrator``），既不扩大
也不改坏：administrator 看全司，其它角色只看「本部门的 + 归属列出现之前的历史行」。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common.auth import create_token
from app.main import app

DEPT_OWN = "r176-own"
DEPT_FOREIGN = "r176-fx"
OWN_ALERT_MESSAGE = "R176T-ALERT-OWN 部门 r176-own 的营收跌破阈值"
FOREIGN_ALERT_MESSAGE = "R176T-ALERT-FX 部门 r176-fx 的毛利跌破阈值"
LEGACY_ALERT_MESSAGE = "R176T-ALERT-LEGACY 归属列出现之前的巡检告警"
RULE_NAME = "r176-rule"
CELL_FOREIGN_READ = "alert_route.foreign_manager_reads_scoped_alert"


def _username(kind: str, cell_id: str) -> str:
    """照 R163 的口径造全局唯一 username：审计与台账都要能按人归因到具体格子。"""
    return "r176-" + kind + "-" + cell_id


def _account(kind: str, cell_id: str, **overrides) -> dict:
    department = DEPT_FOREIGN if kind == "xdept" else ("" if kind == "nodept" else DEPT_OWN)
    role = {"xdept": "manager", "nodept": "manager", "xclear": "staff", "admin": "admin"}.get(
        kind, "manager"
    )
    user = {
        "id": "u-" + _username(kind, cell_id),
        "username": _username(kind, cell_id),
        "role": role,
        "department": department,
    }
    user.update(overrides)
    return user


def _principal(kind: str, cell_id: str, **overrides) -> Principal:
    return Principal.from_user(_account(kind, cell_id, **overrides))


@pytest.fixture()
def ledger(monkeypatch):
    """离线台账现场：内存告警表 + 按 username 查人的认证缝 + 三条种子告警。

    种子刻意放两条有归属、一条没归属：没归属那条是归属列出现之前写进去的历史行，它同时也是
    ``tests/test_dashboard_summary.py`` 里「计数与列表要一致」所依赖的那个形状。
    """
    from app.api.v1 import alerts
    from app.common import auth

    accounts: dict[str, dict] = {}

    def _serve(kind: str, cell_id: str, **overrides) -> str:
        username = _username(kind, cell_id)
        accounts[username] = _account(kind, cell_id, **overrides)
        return username

    rows = [
        {"id": 1, "rule_id": 1, "message": OWN_ALERT_MESSAGE, "read": False,
         "department": DEPT_OWN},
        {"id": 2, "rule_id": 1, "message": FOREIGN_ALERT_MESSAGE, "read": False,
         "department": DEPT_FOREIGN},
        {"id": 3, "rule_id": 1, "message": LEGACY_ALERT_MESSAGE, "read": False},
    ]
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", rows)
    monkeypatch.setattr(
        alerts,
        "_MEM_RULES",
        [{"id": 1, "name": RULE_NAME, "metric": "revenue", "op": "lt", "threshold": 1.0,
          "enabled": True}],
    )
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    return SimpleNamespace(
        alerts=alerts, rows=rows, accounts=accounts, serve=_serve,
        client=TestClient(app), mp=monkeypatch,
    )


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _messages(body: dict) -> list[str]:
    return [str(alert.get("message") or "") for alert in body["alerts"]]


# ==================== 🔴 A 类那一格（判据①） ====================


def test_foreign_manager_reads_scoped_alert(ledger):
    """判据①的红：r176-fx 的 manager 不该拿到 r176-own 部门的告警正文。

    改前的产品证据：``GET /alerts`` 把整张台账原样交回（无库时 ``reversed(_MEM_ALERTS)``，
    有库时 ``SELECT * FROM alerts``），唯一的门是 ``alerts:manage`` 能力判定 —— 它既不看
    部门也不看归属 ⇒ 正文照抄。
    """
    xdept = ledger.serve("xdept", CELL_FOREIGN_READ)

    body = ledger.client.get("/api/v1/alerts", headers=_headers(xdept)).json()

    assert FOREIGN_ALERT_MESSAGE in _messages(body), (
        "正向对照不成立：自己部门那条没出现，这一格的绿就是空转刷出来的"
    )
    assert OWN_ALERT_MESSAGE not in _messages(body), (
        "判据①内容越权：别人部门的告警正文原样出现在响应里 —— " + str(_messages(body))
    )


def test_manager_only_reads_his_own_department_alerts(ledger):
    """对称的那半条判据②：r176-own 的 manager 同样读不到 r176-fx 那条。"""
    keeper = ledger.serve("keeper", "alert_route.reads_own_rows_only")

    body = ledger.client.get("/api/v1/alerts", headers=_headers(keeper)).json()

    messages = _messages(body)
    assert OWN_ALERT_MESSAGE in messages
    assert FOREIGN_ALERT_MESSAGE not in messages, (
        "判据①内容越权（反向）：自己部门之外的告警正文照样漏了出去 —— " + str(messages)
    )


def test_row_scope_keeps_the_administrator_exactly_as_policy_defines_it(ledger):
    """既有豁免语义不许改坏：administrator 仍然看得到两个部门。"""
    admin = ledger.serve("admin", "alert_route.administrator_sees_every_department")

    body = ledger.client.get("/api/v1/alerts", headers=_headers(admin)).json()

    messages = _messages(body)
    assert OWN_ALERT_MESSAGE in messages and FOREIGN_ALERT_MESSAGE in messages


def test_row_scope_exemption_does_not_reach_a_manager(ledger):
    """判据④第三把的常驻形态：豁免只有 administrator 一条路，manager 不是豁免对象。

    资源级这一层 manager 与 admin 同样放行（都持有 ``alerts:manage``），所以一旦有人把归属
    过滤写成「管理员豁免全员」，这一格会与上面那格一起红 —— 它只看部门，不看能力。
    """
    xdept = ledger.serve("xdept", "alert_route.exemption_is_not_for_managers")

    response = ledger.client.get("/api/v1/alerts", headers=_headers(xdept))

    assert response.status_code == 200, "资源级这一层仍然放行：他是 manager"
    assert OWN_ALERT_MESSAGE not in _messages(response.json()), (
        "行级这一层必须把非本部门的正文裁掉；裁不掉就是豁免被写成了全员"
    )


def test_principal_without_a_department_reads_no_attributed_alert(ledger):
    """无部门账号只看无归属历史行：空作用域不等于全公司可见（fail-closed）。"""
    nodept = ledger.serve("nodept", "alert_route.no_department_reads_nothing_attributed")

    body = ledger.client.get("/api/v1/alerts", headers=_headers(nodept)).json()

    messages = _messages(body)
    assert LEGACY_ALERT_MESSAGE in messages, "历史行按既有心智保留（见 tests/test_dashboard_summary.py）"
    assert OWN_ALERT_MESSAGE not in messages and FOREIGN_ALERT_MESSAGE not in messages, (
        "判据①内容越权：没有作用域的账号照样翻到了有归属的正文 —— " + str(messages)
    )


def test_row_scope_leaves_the_rule_list_alone(ledger):
    """判据②的边界：规则是租户级配置，本件只裁「告警正文」这一条轴。

    这一格同时钉住绿不是空转刷出来的：跨部门 manager 仍然看得见那条规则，说明上面几格裁掉
    的是行，不是把整个面板关掉。
    """
    xdept = ledger.serve("xdept", "alert_route.foreign_manager_still_lists_rules")

    rules = ledger.client.get("/api/v1/alerts/rules", headers=_headers(xdept)).json()

    assert [rule["name"] for rule in rules["rules"]] == [RULE_NAME]


def test_capability_denial_is_not_answered_with_an_empty_list(ledger):
    """行级过滤不许把能力性 403 洗成 200 空列表（看板 G4 已裁的口径）。"""
    xclear = ledger.serve("xclear", "alert_route.denied_caller_still_gets_403")

    response = ledger.client.get("/api/v1/alerts", headers=_headers(xclear))

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"


# ==================== 写侧要真的落下归属，否则读侧的过滤器是空的 ====================


class _RecordingConnection:
    """替 ``psycopg`` 记账：只留执行过的语句与参数，绝不碰任何端口。"""

    def __init__(self, rows: list[dict] | None = None, row: dict | None = None):
        self.executed: list[tuple[str, object]] = []
        self.rows = rows if rows is not None else []
        self.row = row
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def commit(self):
        self.commits += 1


@pytest.fixture()
def tenant_data(monkeypatch, tmp_path):
    """租户 DATA_DIR + 数据集登记表，全部落在 tmp_path 里。"""
    from app.api.v1 import alerts, data
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / "tenant-data"
    root.mkdir()
    registry = DatasetRegistry(root=root, metadata_path=root / ".dataset-metadata.json")
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_RULES", [])
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_ai_analysis", lambda rule, value: "r176 analysis")
    monkeypatch.setattr(alerts, "send_im_notification", lambda *a, **k: True)

    def _csv(name: str, profit: float) -> Path:
        path = root / name
        path.write_text(f"store,profit\nwest,{profit:.2f}\n", encoding="utf-8")
        return path

    rule = {"id": 7, "name": "profit-floor", "metric": "profit", "op": "gt",
            "threshold": 1.0, "enabled": True}
    return SimpleNamespace(
        alerts=alerts, root=root, registry=registry, csv=_csv, rule=rule, mp=monkeypatch
    )


def _registered_own_dataset(tenant_data, cell_id: str, filename: str):
    """登记一份 r176-own 的数据集，返回它的 manager principal。"""
    keeper = _principal("keeper", cell_id)
    tenant_data.registry.register(
        tenant_data.csv(filename, 42.0), principal=keeper, filename=filename
    )
    return keeper


def test_scoped_sweep_stamps_the_alert_with_its_owning_department(tenant_data):
    """判据②写侧：巡检产出的每一条告警都得带着归属，读侧才有东西可裁。"""
    alerts = tenant_data.alerts
    keeper = _registered_own_dataset(tenant_data, "alert_route.write_stamps_department",
                                     "r176-own-book.csv")
    alerts._MEM_RULES.append(dict(tenant_data.rule))

    triggered = alerts.evaluate_all(principal=keeper)

    assert [item["message"] for item in triggered] == ["profit-floor: profit=42.0 (gt 1.0)"]
    recorded = alerts._MEM_ALERTS
    assert len(recorded) == 1
    assert recorded[0].get("department") == DEPT_OWN, f"写侧没落归属：{recorded[0]!r}"


def test_alert_written_for_one_department_is_invisible_to_the_other(tenant_data):
    """端到端一把尺：写侧盖的章，就是读侧裁人的依据。"""
    alerts = tenant_data.alerts
    keeper = _registered_own_dataset(tenant_data, "alert_route.end_to_end_writer_scope",
                                     "r176-own-book.csv")
    xdept = _principal("xdept", "alert_route.end_to_end_reader_scope")
    alerts._MEM_RULES.append(dict(tenant_data.rule))
    alerts.evaluate_all(principal=keeper)

    visible = [alert for alert in alerts._MEM_ALERTS if alerts.alert_row_visible(xdept, alert)]

    assert visible == [], f"别人部门的告警仍然可达：{visible!r}"
    assert alerts.alert_row_visible(keeper, alerts._MEM_ALERTS[0]) is True


def test_sweep_without_a_principal_uses_the_datasets_own_department(tenant_data):
    """定时巡检（无 Principal）按数据自己的部门盖章，不是按「谁能看告警」盖章。"""
    alerts = tenant_data.alerts
    _registered_own_dataset(tenant_data, "alert_route.scheduler_uses_dataset_scope",
                            "r176-registered.csv")
    alerts._MEM_RULES.append(dict(tenant_data.rule))

    alerts.evaluate_all()

    assert alerts._MEM_ALERTS[0].get("department") == DEPT_OWN, (
        f"登记表里有部门，写侧却没盖章：{alerts._MEM_ALERTS[0]!r}"
    )


def test_sweep_over_an_unregistered_file_stays_unattributed(tenant_data):
    """没登记、也没 Principal ⇒ 无归属历史行，不许瞎猜一个部门。"""
    alerts = tenant_data.alerts
    tenant_data.csv("r176-unregistered.csv", 42.0)
    alerts._MEM_RULES.append(dict(tenant_data.rule))

    alerts.evaluate_all()

    assert alerts._MEM_ALERTS[0].get("department") == ""


# ==================== 有库那一腿必须把归属落进 SQL ====================


def test_database_read_pushes_the_row_scope_into_sql(ledger):
    """归属过滤要落在查询上：``LIMIT 100`` 之后才在 Python 里裁，会把整页别人的告警读空。"""
    connection = _RecordingConnection(
        rows=[{"id": 2, "message": FOREIGN_ALERT_MESSAGE, "department": DEPT_FOREIGN}]
    )
    ledger.mp.setattr(ledger.alerts, "_database_available", lambda: True)
    ledger.mp.setattr(ledger.alerts, "_initialized", True)
    ledger.mp.setattr(ledger.alerts, "_conn", lambda: connection)
    xdept = ledger.serve("xdept", "alert_route.sql_pushes_row_scope")

    body = ledger.client.get("/api/v1/alerts", headers=_headers(xdept)).json()

    assert _messages(body) == [FOREIGN_ALERT_MESSAGE]
    selects = [
        (sql, params)
        for sql, params in connection.executed
        if sql.lstrip().upper().startswith("SELECT")
    ]
    assert selects, connection.executed
    sql, params = selects[0]
    assert "department" in sql, "读路径没把归属条件带进 SQL，等于裁了个空：" + sql
    assert params and DEPT_FOREIGN in list(params[0]), f"归属参数没带上调用者的部门：{params!r}"


def test_database_read_gives_the_administrator_no_row_predicate(ledger):
    """既有豁免不许扩大：管理员那一腿的 SQL 里不该出现任何归属条件。"""
    connection = _RecordingConnection(rows=[])
    ledger.mp.setattr(ledger.alerts, "_database_available", lambda: True)
    ledger.mp.setattr(ledger.alerts, "_initialized", True)
    ledger.mp.setattr(ledger.alerts, "_conn", lambda: connection)
    admin = ledger.serve("admin", "alert_route.administrator_sql_has_no_predicate")

    ledger.client.get("/api/v1/alerts", headers=_headers(admin))

    selects = [sql for sql, _ in connection.executed if sql.lstrip().upper().startswith("SELECT")]
    assert selects and all("department" not in sql for sql in selects), selects


def test_offline_and_sql_branches_share_one_scope_decision(ledger):
    """两条腿共用同一个判据：Python 谓词与 SQL 谓词读同一个部门集合，不许分叉。"""
    from app.api.v1 import alerts

    xdept = _principal("xdept", "alert_route.branches_agree")
    admin = _principal("admin", "alert_route.branches_agree")

    assert alerts.alert_row_scope_departments(xdept) == {DEPT_FOREIGN}
    assert alerts.alert_row_scope_departments(admin) is None, (
        "administrator 的豁免是「这一层不设条件」，不是「换一组部门去查」"
    )
    assert alerts.alert_row_scope_sql(admin) == ("", ())
    predicate, params = alerts.alert_row_scope_sql(xdept)
    assert "department" in predicate and params and set(params[0]) == {DEPT_FOREIGN}
    seen = {row["id"]: alerts.alert_row_visible(xdept, row) for row in ledger.rows}
    assert seen == {1: False, 2: True, 3: True}, seen


def test_database_write_inserts_the_department(tenant_data):
    """有库那条 INSERT 也带着归属列；rule_id / message 的位次是既存件钉着的，不许动。"""
    alerts = tenant_data.alerts
    keeper = _registered_own_dataset(
        tenant_data, "alert_route.sql_write_stamps_department", "r176-own-book.csv"
    )
    connection = _RecordingConnection(rows=[dict(tenant_data.rule)], row={"id": 11})
    tenant_data.mp.setattr(alerts, "_database_available", lambda: True)
    tenant_data.mp.setattr(alerts, "_ensure", lambda: None)
    tenant_data.mp.setattr(alerts, "_conn", lambda: connection)

    alerts.evaluate_all(principal=keeper)

    inserts = [params for sql, params in connection.executed if "INSERT INTO alerts" in sql]
    assert len(inserts) == 1, connection.executed
    assert inserts[0][0] == 7 and str(inserts[0][1]).startswith("profit-floor")
    assert DEPT_OWN in list(inserts[0]), f"归属没进 INSERT：{inserts[0]!r}"


def test_lazy_schema_makes_room_for_the_ownership_column(ledger):
    """懒建表那一腿要认归属列，否则开发库里这个字段永远写不进去。"""
    connection = _RecordingConnection()
    ledger.mp.setattr(ledger.alerts, "_initialized", False)
    ledger.mp.setattr(ledger.alerts, "_conn", lambda: connection)
    ledger.mp.setenv("APP_ENV", "development")

    ledger.alerts._ensure()

    statements = " ".join(sql.upper() for sql, _ in connection.executed)
    assert "DEPARTMENT" in statements, "建表/改表语句里没有归属列：" + statements


class _ProdSchemaConnection:
    """按语句回话的生产库替身：表在不在、列在不在，各答各的。"""

    def __init__(self, columns_present: bool):
        self.columns_present = columns_present
        self.executed: list[str] = []
        self._next: object = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        text = str(sql)
        self.executed.append(text)
        if "to_regclass" in text:
            self._next = {"table_name": "alerts"}
        elif "information_schema" in text:
            self._next = {"column_name": "department"} if self.columns_present else None
        else:
            self._next = None
        return self

    def fetchone(self):
        return self._next

    def commit(self):
        raise AssertionError("production schema checks must not commit runtime DDL")


def _run_production_ensure(ledger, columns_present: bool) -> _ProdSchemaConnection:
    connection = _ProdSchemaConnection(columns_present)
    ledger.mp.setattr(ledger.alerts, "_initialized", False)
    ledger.mp.setattr(ledger.alerts, "_conn", lambda: connection)
    ledger.mp.setenv("APP_ENV", "production")
    return connection


def test_production_refuses_a_missing_ownership_column(ledger):
    """生产库缺归属列：像缺表一样说 run migrations first，不许退成 500、更不许放行读全司。"""
    connection = _run_production_ensure(ledger, columns_present=False)

    with pytest.raises(RuntimeError, match="run migrations first"):
        ledger.alerts._ensure()

    assert any("information_schema" in sql for sql in connection.executed), connection.executed


def test_production_schema_check_does_not_run_runtime_ddl(ledger):
    """列在的时候：认出它来就收工，本件不许在生产库上偷偷 CREATE / ALTER。"""
    connection = _run_production_ensure(ledger, columns_present=True)

    ledger.alerts._ensure()

    assert not [
        sql for sql in connection.executed if sql.lstrip().upper().startswith(("CREATE", "ALTER"))
    ], connection.executed
