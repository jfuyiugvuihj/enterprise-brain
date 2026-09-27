"""R359 · 存储拒答不许被翻译成「这家公司现在没有异常」（告警面四条腿一起过闸）。

症状（总控在基点 `426834d` 现取）：`app/api/v1/alerts.py::list_alerts` 在
`_database_available()` 为假时把进程内 `_MEM_ALERTS` 筛完直接 `return {"alerts": [...]}`。
客户机上 PG 没起来或迁移没跑 ⇒ 那一支每次回 **200 + 空数组**，而前端照字面画的正是
「当前没有触发中的告警」（`frontend/src/lib/alerts.js::ALERTS_EMPTY_TITLE`）。一条部署缺陷
被说成一句业务结论。同族三处早已裁定：`/users`（R356）、`/dashboard`（R332，
`dashboard.py:143`）、通知（R299，`notifications.py:161`）—— 都是 503 `storage_unavailable`。

本件的判据分成两张脸，缺一不可，所以两方向各有一组钉：

- **甲 该有库而库不在 ⇒ 拒答**：生产环境（沿用 `_is_production_environment()`）且
  `_database_available()` 为假 ⇒ 503 + 仓里已有的 `storage_unavailable`，零新增错误码。
- **乙 开发态一个字都不许跟着死**：裸机上内存 store 是今天合法的后端，那一支的回包形状、
  行数、排序逐字不变（把开发态也打成 503，下面那批 `..._development_...` 当场红）。
- **丙 所有读腿与写腿一起过闸**：列表 / 单条详情 / 规则列表 / 手动巡检 + 规则增删 /
  确认 / 关闭 / 转派，九枚出口逐枚点名；写腿在存储没就绪时既不许回「成功」，也不许只落
  内存再假装已落库。修一格留三扇侧门，`test_every_alert_route_reaches_the_storage_gate`
  与九枚出口的行为钉各红一次。
- **丁 `detail` 字面量全在封闭枚举里**：照 R332 那把 AST 钉（`test_r332_dashboard_trend.py`）
  扫本模块，并把「插值型 detail」这一格今天唯一的存量钉成棘轮。
- **戊 不新增第二份「库在不在」判定，也不新增 `_db_ready` 的读者**：`_db_ready` 在本模块
  的读点仍是一枚（`test_r246` 那本账按 AST 数读者，多一枚就红）。

全部离线：不起服务、不连库、不打模型。替身库 `_MiniStore` 与 `tests/test_r251_alert_disposal.py`
的 `_LedgerConnection` 同级——给本单判据当凭据，产品代码不读它。
"""
from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.contracts import ErrorEnvelope
from app.common.auth import create_token
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
ALERTS_PY = ROOT / "app" / "api" / "v1" / "alerts.py"

#: 仓里已有的那一码：dashboard / notifications / chat 三处出口都在吐它。
STORAGE_CODE = "storage_unavailable"
GATE = "_require_ready_store"
AUTH_GATE = "_require_alert_management"

DEPT_OWN = "r359-own"
DEPT_FX = "r359-fx"
MANAGER = "r359-own-manager"
FX_MANAGER = "r359-fx-manager"
ADMINISTRATOR = "r359-admin"
STAFF = "r359-staff"
FIXED_TS = "2026-09-27T09:00:00+08:00"

#: 台账投影里 0014 那八枚处置列（写死的名单，不从产品代码派生）。
DISPOSAL_COLUMNS = (
    "status", "acknowledged_by", "acknowledged_at", "closed_by", "closed_at",
    "assignee", "assigned_by", "assigned_at",
)

LEDGER = "/api/v1/alerts"
DETAIL = f"{LEDGER}/1"
RULES = f"{LEDGER}/rules"
RULE_ONE = f"{RULES}/1"
CHECK = f"{LEDGER}/check"

OWN_MESSAGE = "R359T 本部门营收跌破阈值"
FX_MESSAGE = "R359T 别部门毛利跌破阈值"
LEGACY_MESSAGE = "R359T 归属列出现之前的巡检告警"
SWEEP_MESSAGE = "R359T 巡检写进内存台账的那一行"

RULE_BODY = {"name": "r359-profit", "metric": "profit", "op": "lt", "threshold": 10}

#: 无库那条腿今天的种子行：两条有归属、一条连 department 都没有（归属列之前的历史行）。
def _seeds() -> list[dict]:
    base = {"rule_id": 7, "ai_analysis": "", "read": False}
    return [
        {**base, "id": 1, "message": OWN_MESSAGE, "department": DEPT_OWN,
         "created_at": "2026-09-26T09:00:00"},
        {**base, "id": 2, "message": FX_MESSAGE, "department": DEPT_FX,
         "created_at": "2026-09-26T09:30:00"},
        {"id": 3, **base, "message": LEGACY_MESSAGE, "created_at": "2026-09-25T08:00:00"},
    ]


#: 开发态那条腿**应该**交回的样子：逐枚手抄，不从产品函数派生 —— 判的就是那一条腿的形状。
EXPECTED_LEGACY_ROW = {
    "id": 3, "rule_id": 7, "ai_analysis": "", "read": False,
    "message": LEGACY_MESSAGE, "created_at": "2026-09-25T08:00:00",
    "status": "open", "acknowledged_by": "", "acknowledged_at": "",
    "closed_by": "", "closed_at": "", "assignee": "", "assigned_by": "", "assigned_at": "",
}
EXPECTED_OWN_ROW = {
    "id": 1, "rule_id": 7, "ai_analysis": "", "read": False,
    "message": OWN_MESSAGE, "created_at": "2026-09-26T09:00:00", "department": DEPT_OWN,
    "status": "open", "acknowledged_by": "", "acknowledged_at": "",
    "closed_by": "", "closed_at": "", "assignee": "", "assigned_by": "", "assigned_at": "",
}
EXPECTED_RULE_ROW = {
    "id": 1, "name": "r359-profit", "metric": "profit", "op": "lt", "threshold": 10.0,
    "enabled": True,
}

# --------------------------------------------------------------------- 九枚出口（判据丙）
#
# 读腿四枚：台账列表、单条详情、规则列表、手动巡检（巡检的读侧——它先读规则与数据再答话）。
# 写腿五枚：规则增、规则删、确认、关闭、转派。逐枚点名，不留侧门。
EXITS: list[tuple[str, str, str, dict | None]] = [
    ("read_ledger_list", "get", LEDGER, None),
    ("read_alert_detail", "get", DETAIL, None),
    ("read_rule_list", "get", RULES, None),
    ("read_manual_sweep", "post", CHECK, None),
    ("write_rule_create", "post", RULES, RULE_BODY),
    ("write_rule_delete", "delete", RULE_ONE, None),
    ("write_alert_ack", "post", f"{DETAIL}/ack", None),
    ("write_alert_close", "post", f"{DETAIL}/close", None),
    ("write_alert_assign", "post", f"{DETAIL}/assign", {"assignee": ADMINISTRATOR}),
]
EXIT_IDS = [exit[0] for exit in EXITS]
WRITE_EXITS = [exit for exit in EXITS if exit[0].startswith("write_")]
READ_EXITS = [exit for exit in EXITS if exit[0].startswith("read_")]

#: 三道处置拒绝出口的三枚码名（写死在这里，与 `app/api/v1/alerts.py` 的常量对账用）。
ALERT_DISPOSAL_CODES = {
    "not_found": "resource_not_found",
    "conflict": "conflict",
    "assignee": "validation_error",
}

#: 本件射程内的九条 HTTP 出口，函数名一枚不少一枚不多：多出第十条腿而没进这张表就红。
ROUTE_ROSTER = {
    "create_rule", "list_rules", "delete_rule",
    "list_alerts", "check_now", "get_alert",
    "acknowledge_alert", "close_alert", "assign_alert",
}


def _account(username: str, role: str, department: str) -> dict:
    return {"id": "u-" + username, "username": username, "role": role, "department": department}


def _accounts() -> dict[str, dict]:
    return {
        MANAGER: _account(MANAGER, "manager", DEPT_OWN),
        FX_MANAGER: _account(FX_MANAGER, "manager", DEPT_FX),
        ADMINISTRATOR: _account(ADMINISTRATOR, "admin", ""),
        STAFF: _account(STAFF, "staff", DEPT_OWN),
    }


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _call(client: TestClient, exit: tuple, username: str | None = None):
    _label, method, path, body = exit
    kwargs = {} if username is None else {"headers": _headers(username)}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


class _SweepSpy:
    """把「真巡检会往内存台账追加行」这件事如实记下来，而不是另造一份判定。

    替身只替 `evaluate_all` 一枚出口：本件判的是闸在不在它前面，扫描本身的口径归 R345。
    """

    def __init__(self, ledger: list[dict]):
        self.calls: list[dict] = []
        self._ledger = ledger

    def __call__(self, principal=None, scan_summary=None):
        self.calls.append({"principal": principal, "scan_summary": scan_summary})
        self._ledger.append(
            {"id": 900, "rule_id": 7, "message": SWEEP_MESSAGE, "read": False}
        )
        return [{"message": SWEEP_MESSAGE, "ai_analysis": ""}]


class _MiniStore:
    """只认本件真会发的那几条语句的替身库：证明「库在时生产照常作答」，不是第二份 schema。

    行级归属谓词它**不求值**（那要再造一份判定），归属落在不在 WHERE 里由
    `tests/test_r176_alert_row_scope.py` 判；本件的 with-store 用例一律走 administrator，
    那一档谓词为空，所以这里既不假装守住了归属，也不需要守住。
    """

    def __init__(self, rows: list[dict], rules: list[dict]):
        self.rows = [dict(row) for row in rows]
        self.rules = [dict(rule) for rule in rules]
        self.executed: list[tuple[str, tuple]] = []
        self.commits = 0
        self._result: list[dict] = []
        self._rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        upper = text.upper()
        self.executed.append((text, tuple(params)))
        self._result = []
        if "INFORMATION_SCHEMA.COLUMNS" in upper:
            # 生产那一腿在处置前会查 alerts.status：迁移跑过了，列在。
            self._result = [{"column_name": "status"}]
        elif upper.startswith("SELECT * FROM ALERT_RULES"):
            self._result = [dict(rule) for rule in self.rules]
        elif upper.startswith("INSERT INTO ALERT_RULES"):
            new_id = max([int(rule["id"]) for rule in self.rules], default=0) + 1
            self.rules.append({"id": new_id, "name": params[0], "metric": params[1],
                               "op": params[2], "threshold": params[3], "enabled": True})
            self._result = [{"id": new_id}]
        elif upper.startswith("DELETE FROM ALERT_RULES"):
            wanted = int(params[0])
            before = len(self.rules)
            self.rules = [rule for rule in self.rules if int(rule["id"]) != wanted]
            self._rowcount = before - len(self.rules)
        elif upper.startswith("SELECT * FROM ALERTS") and "ID = %S" in upper:
            wanted = int(params[0])
            self._result = [dict(row) for row in self.rows if int(row["id"]) == wanted]
        elif upper.startswith("SELECT * FROM ALERTS"):
            self._result = [dict(row) for row in self.rows]
        elif upper.startswith("UPDATE ALERTS"):
            self._rowcount = self._apply_update(text, tuple(params))
        else:
            raise AssertionError(f"替身库收到了本件预期之外的语句: {text}")
        return self

    def _apply_update(self, text: str, params: tuple) -> int:
        set_clause = text.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
        columns = re.findall(r"(\w+) = %s", set_clause)
        target = next((row for row in self.rows if int(row["id"]) == int(params[-1])), None)
        if target is None:
            return 0
        target.update(dict(zip(columns, params[:-1])))
        return 1

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)

    @property
    def rowcount(self):
        return self._rowcount

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("本件不判回滚那一格：走到这里说明替身库被用歪了")


# ------------------------------------------------------------------------ 三套底座
def _wire_offline(monkeypatch, environment: str | None):
    """把「存储没就绪」这一件事钉成读数，环境那一支由调用方定（这就是两张脸的分界线）。"""
    from app.api.v1 import alerts
    from app.common import auth

    rows = _seeds()
    rules = [dict(EXPECTED_RULE_ROW)]
    accounts = _accounts()
    sweep = _SweepSpy(rows)

    touched = {"conn": 0, "ensure": 0}

    def _no_connection():
        touched["conn"] += 1
        raise AssertionError("闸没拦在前面：这一发真的去开连接了")

    def _no_ensure():
        touched["ensure"] += 1
        raise AssertionError("闸没拦在前面：这一发真的去查 schema 了")

    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", rows)
    monkeypatch.setattr(alerts, "_MEM_RULES", rules)
    monkeypatch.setattr(alerts, "_MEM_NEXT_RULE_ID", 1)
    monkeypatch.setattr(alerts, "_alert_disposal_now", lambda: FIXED_TS)
    monkeypatch.setattr(alerts, "_conn", _no_connection)
    monkeypatch.setattr(alerts, "_ensure", _no_ensure)
    monkeypatch.setattr(alerts, "evaluate_all", sweep)
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    return SimpleNamespace(
        alerts=alerts, rows=rows, rules=rules, accounts=accounts, sweep=sweep,
        touched=touched, client=TestClient(app), mp=monkeypatch,
    )


@pytest.fixture()
def prod(monkeypatch):
    """客户机那一格：APP_ENV=production 而 PG 没起（或迁移没跑）。"""
    return _wire_offline(monkeypatch, "production")


@pytest.fixture()
def dev(monkeypatch):
    """裸机那一格：开发环境 + 同一枚「库不在」的读数。"""
    return _wire_offline(monkeypatch, "development")


@pytest.fixture()
def store(monkeypatch):
    """生产环境而库**在**：本件的闸不许把这正常的那一格一起打死。"""
    from app.api.v1 import alerts
    from app.common import auth

    rows = [
        {"id": 1, "rule_id": 7, "message": OWN_MESSAGE, "department": DEPT_OWN,
         "ai_analysis": "", "read": False, "created_at": "2026-09-26T09:00:00",
         "status": "open", "acknowledged_by": "", "acknowledged_at": "", "closed_by": "",
         "closed_at": "", "assignee": "", "assigned_by": "", "assigned_at": ""},
    ]
    connection = _MiniStore(rows, [dict(EXPECTED_RULE_ROW)])
    accounts = _accounts()
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_MEM_RULES", [])
    monkeypatch.setattr(alerts, "_ensure", lambda: None)
    monkeypatch.setattr(alerts, "_conn", lambda: connection)
    monkeypatch.setattr(alerts, "_alert_disposal_now", lambda: FIXED_TS)
    # 巡检那一腿留真身（它才是本单要的「库在时照常作答」），只把两份磁盘/登记表读数换成
    # 离线常量：本件不判扫描口径（R345），也不许在测试里读宿主 DATA_DIR 与真登记表。
    monkeypatch.setattr(
        alerts, "_scan_data_files",
        lambda principal: ([], {"data_dir_configured": False, "scoped_to_principal": False,
                                "reason": "tenant_data_dir_unavailable"}),
    )
    monkeypatch.setattr(alerts, "_dataset_department_index", lambda: {})
    monkeypatch.setenv("APP_ENV", "production")
    return SimpleNamespace(
        alerts=alerts, connection=connection, accounts=accounts,
        client=TestClient(app), mp=monkeypatch,
    )


# ================================================================== 甲：生产 + 库不在 ⇒ 拒答
def test_production_without_a_store_refuses_the_ledger(prod):
    """症状本身：`GET /alerts` 不许再用一张空台账冒充「没有异常」。"""
    response = prod.client.get(LEDGER, headers=_headers(MANAGER))

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert response.json() != {"alerts": []}, "拒答被洗回空数组 = 本单没修"


def test_the_refusal_names_the_code_the_repo_already_uses(prod):
    """零新增错误码：拒答用的是 dashboard / notifications / chat 同一枚词，不是替本单新开的。"""
    response = prod.client.get(LEDGER, headers=_headers(MANAGER))
    enum_codes = get_args(ErrorEnvelope.model_fields["code"].annotation)

    assert response.json()["detail"] == STORAGE_CODE
    assert STORAGE_CODE in enum_codes, "这枚码不在封闭枚举里，说明有人换了词"


@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_every_storage_leg_refuses_in_production(prod, exit):
    """判据丙（生产那一半）：九枚出口逐枚 503，一枚侧门都不留。"""
    response = _call(prod.client, exit, MANAGER)

    assert response.status_code == 503, f"{exit[0]} 还在作答: {response.text}"
    assert response.json() == {"detail": STORAGE_CODE}, exit[0]


@pytest.mark.parametrize("exit", READ_EXITS, ids=[exit[0] for exit in READ_EXITS])
def test_a_read_leg_never_answers_with_an_empty_collection(prod, exit):
    """读侧四枚：200 加空集合就是本单要杀的那个形状，逐枚点名。"""
    response = _call(prod.client, exit, MANAGER)

    assert response.status_code != 200, f"{exit[0]} 用 200 回了话: {response.text}"
    body = response.json()
    assert not any(value == [] for value in body.values()), f"{exit[0]} 交回了空集合: {body}"


@pytest.mark.parametrize("exit", WRITE_EXITS, ids=[exit[0] for exit in WRITE_EXITS])
def test_no_write_leg_dresses_a_failed_write_as_success(prod, exit):
    """写侧五枚：既不许回「成功」，也不许只落内存再假装已落库（判据丙后半）。"""
    alerts = prod.alerts
    ledger_before = [dict(row) for row in alerts._MEM_ALERTS]
    rules_before = [dict(rule) for rule in alerts._MEM_RULES]

    response = _call(prod.client, exit, ADMINISTRATOR)

    assert response.status_code == 503, f"{exit[0]} 答了成功: {response.text}"
    assert response.json() == {"detail": STORAGE_CODE}, exit[0]
    assert alerts._MEM_ALERTS == ledger_before, f"{exit[0]} 往内存台账里写了行"
    assert alerts._MEM_RULES == rules_before, f"{exit[0]} 往内存规则里写了行"


def test_the_manual_sweep_does_not_run_at_all(prod):
    """巡检的读侧也被闸在前面：一次做不成的巡检不许留下「扫过了」的痕迹。"""
    response = prod.client.post(CHECK, headers=_headers(MANAGER))

    assert response.status_code == 503
    assert prod.sweep.calls == [], "evaluate_all 照跑了：内存台账会被它写脏"
    assert [row["message"] for row in prod.alerts._MEM_ALERTS] == [
        OWN_MESSAGE, FX_MESSAGE, LEGACY_MESSAGE
    ]


@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_the_refusal_comes_before_any_connection_or_schema_probe(prod, exit):
    """拒答必须排在 `_ensure()` 与 `_conn()` 之前：那两枚在本件里是被记数的桩。

    两个方向一起判。闸排在它们后面 ⇒ 计数不为零，而且 TestClient 会把桩抛出的
    AssertionError 原样重抛，这一枚直接红；闸排在前面 ⇒ 计数恒零，九枚出口都答 503。
    """
    response = _call(prod.client, exit, ADMINISTRATOR)

    assert response.status_code == 503, exit[0]
    assert prod.touched == {"conn": 0, "ensure": 0}, (
        f"{exit[0]} 在拒答之前先碰了存储出口: {prod.touched}"
    )


# ================================================ 乙：开发态那一条腿，逐字不许跟着死（判据乙）
def test_the_development_ledger_still_answers_from_the_memory_store(dev):
    """同一枚「库不在」的读数，换个环境就必须照常作答：两张脸分开，不是一律 503。"""
    response = dev.client.get(LEDGER, headers=_headers(MANAGER))

    assert response.status_code == 200, response.text
    assert response.json() == {"alerts": [EXPECTED_LEGACY_ROW, EXPECTED_OWN_ROW]}


def test_the_development_row_count_order_and_shape_are_untouched(dev):
    """行数、排序、投影三格逐字钉：本单只加了一道闸，那一条腿的一个字都没动。

    250 行走 `islice(..., 100)`：拿满 100 条、按 id 递减、且只裁在页外——这条钉同时守着
    R176「不许在 LIMIT 之后再筛」那件事在无库这一腿上的形状。
    """
    many = [{"id": index, "rule_id": 7, "message": f"row-{index}", "read": False}
            for index in range(1, 251)]
    dev.alerts._MEM_ALERTS[:] = many

    body = dev.client.get(LEDGER, headers=_headers(ADMINISTRATOR)).json()

    assert len(body["alerts"]) == 100
    assert [row["id"] for row in body["alerts"]] == list(range(250, 150, -1))
    # 投影 = 种子那四枚列 + 八枚处置列；名单自己先对一次账，免得 EXPECTED_* 抄漏了还绿着。
    assert set(EXPECTED_LEGACY_ROW) - {"id", "rule_id", "ai_analysis", "read",
                                       "message", "created_at"} == set(DISPOSAL_COLUMNS)
    assert set(body["alerts"][0]) == {"id", "rule_id", "message", "read", *DISPOSAL_COLUMNS}


def test_the_development_detail_and_rule_list_still_answer(dev):
    """另外两枚读腿在开发态照常回话，且行级归属那一刀没被本单碰钝。"""
    detail = dev.client.get(DETAIL, headers=_headers(MANAGER))
    foreign = dev.client.get(DETAIL, headers=_headers(FX_MANAGER))
    rules = dev.client.get(RULES, headers=_headers(MANAGER))

    assert detail.status_code == 200 and detail.json() == {"alert": EXPECTED_OWN_ROW}
    assert foreign.status_code == 404, "别部门那条在开发态也不许读得到"
    assert rules.status_code == 200 and rules.json() == {"rules": [EXPECTED_RULE_ROW]}


@pytest.mark.parametrize("exit", WRITE_EXITS, ids=[exit[0] for exit in WRITE_EXITS])
def test_the_development_write_legs_still_write_and_still_answer(dev, exit):
    """内存 store 在裸机上是合法后端：五枚写口一枚都不许跟着生产一起吃闸。"""
    response = _call(dev.client, exit, ADMINISTRATOR)

    assert response.status_code == 200, f"{exit[0]} 在开发态被拒了: {response.text}"
    if exit[0] == "write_rule_create":
        assert response.json() == {"id": 1, "status": "ok"}
        assert dev.alerts._MEM_RULES[-1]["name"] == RULE_BODY["name"]
    elif exit[0] == "write_rule_delete":
        assert response.json() == {"status": "ok"}
        assert dev.alerts._MEM_RULES == []
    else:
        status = {"write_alert_ack": "acknowledged", "write_alert_close": "closed",
                  "write_alert_assign": "open"}[exit[0]]
        alert = response.json()["alert"]
        assert alert["status"] == status and alert["id"] == 1


def test_the_development_sweep_still_runs(dev):
    """巡检的读侧在开发态照跑：闸不许顺手把这一格也打死。"""
    response = dev.client.post(CHECK, headers=_headers(MANAGER))

    assert response.status_code == 200, response.text
    assert len(dev.sweep.calls) == 1
    assert set(response.json()) == {"triggered", "scan_scope"}
    assert response.json()["triggered"] == [{"message": SWEEP_MESSAGE, "ai_analysis": ""}]


# 环境写法这两族照 `_PRODUCTION_ENVIRONMENTS` + `.strip().lower()` 现算：非生产那一族
# 一枚都不许吃闸（🔴 判据乙的反方向），生产那一族四种写法一枚都不许漏过闸。
NON_PRODUCTION_ENVIRONMENTS = ("development", "test", "staging", "", "prod1", "production-env")
PRODUCTION_ENVIRONMENTS = ("production", "prod", "PRODUCTION", " Production ")

#: 环境这一维用两枚代表出口（一读一写）就够咬，九枚出口的全维点名在上面那两组里。
GATE_PROBE_EXITS = [EXITS[0], EXITS[6]]


@pytest.mark.parametrize("environment", NON_PRODUCTION_ENVIRONMENTS)
@pytest.mark.parametrize("exit", GATE_PROBE_EXITS, ids=[exit[0] for exit in GATE_PROBE_EXITS])
def test_the_gate_never_bites_outside_a_production_environment(dev, exit, environment):
    """🔴 反方向的那枚钉：把开发态也一起打成 503，本枚当场红。"""
    dev.mp.setenv("APP_ENV", environment)

    response = _call(dev.client, exit, ADMINISTRATOR)

    assert response.status_code == 200, (
        f"APP_ENV={environment!r} 不是生产，这一条腿被本单的闸打死了: {response.text}"
    )


@pytest.mark.parametrize("environment", PRODUCTION_ENVIRONMENTS)
@pytest.mark.parametrize("exit", GATE_PROBE_EXITS, ids=[exit[0] for exit in GATE_PROBE_EXITS])
def test_every_production_spelling_refuses(dev, exit, environment):
    """生产档的四种写法（大小写与空格）一起拒：闸不许只认字面量 "production"。"""
    dev.mp.setenv("APP_ENV", environment)

    response = _call(dev.client, exit, ADMINISTRATOR)

    assert response.status_code == 503, f"APP_ENV={environment!r} 漏过了闸: {response.text}"
    assert response.json() == {"detail": STORAGE_CODE}, exit[0]


def test_the_default_environment_is_the_development_one(dev):
    """`APP_ENV` 压根没设（客户机之外最常见的起法）= 不是生产，那条腿照常回话。"""
    dev.mp.delenv("APP_ENV", raising=False)

    assert dev.client.get(LEDGER, headers=_headers(MANAGER)).status_code == 200


# ==================================================== 生产而库在：闸不许把正常那一格打死
def test_production_answers_normally_when_the_store_is_ready(store):
    """`_database_available()` 为真 ⇒ 闸一个字都不说，读写照旧落库。"""
    listed = store.client.get(LEDGER, headers=_headers(ADMINISTRATOR))
    detail = store.client.get(DETAIL, headers=_headers(ADMINISTRATOR))
    rules = store.client.get(RULES, headers=_headers(ADMINISTRATOR))

    assert listed.status_code == 200 and listed.json()["alerts"][0]["id"] == 1
    assert detail.status_code == 200 and detail.json()["alert"]["message"] == OWN_MESSAGE
    assert rules.status_code == 200 and rules.json()["rules"][0]["name"] == RULE_BODY["name"]


@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_every_leg_still_answers_when_production_has_its_store(store, exit):
    """九枚出口全在库在时答话，且一个字都不落内存台账：闸不是「生产一律 503」。"""
    response = _call(store.client, exit, ADMINISTRATOR)

    assert response.status_code == 200, f"{exit[0]} 在库在时也被拒了: {response.text}"
    assert store.alerts._MEM_ALERTS == [], f"{exit[0]} 绕过了库"
    assert store.alerts._MEM_RULES == [], f"{exit[0]} 绕过了库"
    assert store.connection.executed, f"{exit[0]} 没走到存储"


def test_the_disposal_write_lands_in_the_store_and_reads_back(store):
    """写腿在库在时真落库：交回的是库里现在什么样，不是「我以为写成什么样」。"""
    response = store.client.post(f"{DETAIL}/ack", headers=_headers(ADMINISTRATOR))

    updated = [sql for sql, _ in store.connection.executed if sql.upper().startswith("UPDATE")]
    assert response.status_code == 200, response.text
    assert len(updated) == 1, store.connection.executed
    assert store.connection.rows[0]["status"] == "acknowledged"
    assert store.connection.rows[0]["acknowledged_by"] == ADMINISTRATOR
    assert response.json()["alert"]["status"] == "acknowledged"
    assert store.connection.commits == 1


# ================================================ 闸排在授权之后：不许做成「有没有 PG」的探针
@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_an_anonymous_caller_never_meets_the_storage_answer(prod, exit):
    """匿名一律 401 `authentication_required`，永远拿不到 503。

    这一格答话的是 `app/main.py::AuthMiddleware`（它在路由之前就把匿名挡掉），所以本枚钉的是
    「存储那一句永远不会说给匿名者听」，不是闸与授权门的先后——先后由下面两枚钉：
    `..._gets_the_permission_answer_not_the_storage_answer`（staff 那格，行为）与
    `test_the_gate_is_wired_after_the_authorization_gate_everywhere`（九条路由，AST）。
    """
    response = _call(prod.client, exit, None)

    assert response.status_code == 401, f"{exit[0]} 把匿名者答成了存储拒答: {response.text}"
    assert response.json()["detail"] == "authentication_required", exit[0]
    assert prod.touched == {"conn": 0, "ensure": 0}


@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_a_staff_caller_gets_the_permission_answer_not_the_storage_answer(prod, exit):
    """有身份没权限仍是 403 `permission_denied`：本单一枚状态码的归属都没动。"""
    response = _call(prod.client, exit, STAFF)

    assert response.status_code == 403, f"{exit[0]}: {response.text}"
    assert response.json()["detail"] == "permission_denied", exit[0]


@pytest.mark.parametrize("leg", ["list_alerts", "get_alert"])
def test_the_refusal_is_carried_by_direct_calls_too(prod, leg):
    """`app/notifications/sources.py:150` 与 `inbox.py:159` 直接 await 这两枚端点。

    单一事实源（契约 :2092 明写「called directly so the resource gate ... keep exactly one
    definition」）意味着闸也一起生效：本枚钉住「直调同样吐 503」，并把跨模块的那一格后果
    写实——收件箱的告警腿与 `can_address` 都会看见这枚 503（两处都只折 403 / 401·403·404，
    其余原样 raise）。已在回执「只报不改」登记，改不改归 notifications 的业主或总控。
    """
    from app.api.v1 import alerts as module

    # 一枚够用的 Request 投影：授权那一层只读 state.username（authorization.py:34-47），
    # 直调的调用方（notifications/sources.py:150、inbox.py:159）传的是真 Request，同一把尺。
    request = SimpleNamespace(
        state=SimpleNamespace(principal=None, username=ADMINISTRATOR), headers={}
    )
    call = module.list_alerts if leg == "list_alerts" else module.get_alert
    arguments = () if leg == "list_alerts" else (1,)

    async def _direct():
        return await call(*arguments, request=request)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(_direct())

    assert caught.value.status_code == 503
    assert caught.value.detail == STORAGE_CODE


def test_the_illegal_operator_still_answers_its_own_400_in_development(dev):
    """`create_rule` 那枚插值 detail 的形状不许被本单顺手改掉（那是另一枚单的口径）。"""
    response = dev.client.post(RULES, headers=_headers(ADMINISTRATOR),
                               json={**RULE_BODY, "op": "nope"})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("非法操作符")


# ============================================================== 结构钉：侧门 / 码表 / 探针
def _tree() -> ast.Module:
    return ast.parse(ALERTS_PY.read_text(encoding="utf-8"))


def _top_level_functions(tree) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _callees(function) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found.setdefault(node.func.id, []).append(node.lineno)
    return found


def _reaches_gate(function_name: str, functions: dict, seen: tuple = ()) -> bool:
    """这枚函数沿调用图（含一层层往下）能不能走到闸：侧门就是走不到那一格。"""
    if function_name in seen or function_name not in functions:
        return False
    calls = _callees(functions[function_name])
    if GATE in calls:
        return True
    return any(
        _reaches_gate(name, functions, seen + (function_name,))
        for name in calls
        if name in functions
    )


def _gate_entry_lineno(function_name: str, functions: dict) -> int:
    """这一枚函数里最早一个「会走到闸」的调用点的行号。"""
    calls = _callees(functions[function_name])
    entries = [min(linenos) for name, linenos in calls.items() if name == GATE or _reaches_gate(name, functions)]
    assert entries, f"{function_name} 根本走不到闸"
    return min(entries)


def _router_routes(tree) -> dict[str, ast.AST]:
    methods = {"get", "post", "put", "delete", "patch", "head", "options"}
    routes: dict[str, ast.AST] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            callee = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (
                isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Name)
                and callee.value.id == "router"
                and callee.attr in methods
            ):
                routes[node.name] = node
    return routes


def _enum_codes() -> set[str]:
    return set(get_args(ErrorEnvelope.model_fields["code"].annotation))


def _module_string_constants(tree) -> dict[str, str]:
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def _detail_shapes(tree) -> list[tuple[str, str, str | None]]:
    """每一枚 `HTTPException(detail=...)`：(所在函数, 形状, 静态抠得到的码名或 None)。

    比 R332 那把钉多解一层——本模块的码有三枚躺在模块级常量上（`ALERT_DISPOSAL_*_CODE`），
    只认字面量就会把那一族整个漏掉，闸新吐的那枚字面量也就没人对账。
    """
    consts = _module_string_constants(tree)
    functions = _top_level_functions(tree)
    by_line = sorted([(node.lineno, node.end_lineno, name) for name, node in functions.items()])

    def symbol_of(lineno: int) -> str:
        for start, end, name in by_line:
            if start <= lineno <= (end or start):
                return name
        return "<module>"

    shapes: list[tuple[str, str, str | None]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "HTTPException"):
            continue
        for keyword in node.keywords:
            if keyword.arg != "detail":
                continue
            value = keyword.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                shapes.append((symbol_of(node.lineno), "literal", value.value))
            elif isinstance(value, ast.Name) and value.id in consts:
                shapes.append((symbol_of(node.lineno), f"const:{value.id}", consts[value.id]))
            elif isinstance(value, ast.JoinedStr):
                shapes.append((symbol_of(node.lineno), "interpolated", None))
            else:
                shapes.append((symbol_of(node.lineno), "opaque", None))
    return shapes


def test_the_route_roster_is_exactly_the_nine_exits_this_ticket_covers():
    """出口名单自己也要钉：添一条不记账的告警路由，本枚先红，再谈闸在不在。"""
    assert set(_router_routes(_tree())) == ROUTE_ROSTER


@pytest.mark.parametrize("route", sorted(ROUTE_ROSTER))
def test_every_alert_route_reaches_the_storage_gate(route):
    """🔴 判据丙的结构性那一半：九条路由沿调用图每一条都必经那道闸。

    摘掉某一枚闸（只修列表、留下详情/规则/巡检/三条处置）——本枚对被摘那条当场红；
    行为那一半由上面那组九格点名同时咬住，两边各是一把独立的牙。
    """
    functions = _top_level_functions(_tree())

    assert _reaches_gate(route, functions), f"{route} 不再经过 _require_ready_store：侧门开了"


def test_the_gate_is_wired_after_the_authorization_gate_everywhere():
    """源码里也判一次先后：先答「你能不能」，再答「库在不在」，九条路由一条都不许反。"""
    functions = _top_level_functions(_tree())
    tree = _tree()

    for route, node in sorted(_router_routes(tree).items()):
        calls = _callees(node)
        assert AUTH_GATE in calls, f"{route} 不先过授权门"
        assert min(calls[AUTH_GATE]) < _gate_entry_lineno(route, functions), (
            f"{route} 把存储闸排到了授权门之前：401/403 与 503 之差会漏出部署状态"
        )


def test_the_disposal_helper_refuses_before_it_touches_either_backend():
    """三条处置写口共用那一枚 helper：闸要排在它分腿之前，否则内存那条腿照样被写。"""
    functions = _top_level_functions(_tree())
    calls = _callees(functions["_dispose_alert"])

    assert GATE in calls and "_database_available" in calls
    assert min(calls[GATE]) < min(calls["_database_available"])


def test_the_gate_reuses_both_existing_rulers_instead_of_recopying_them():
    """判据戊：闸只问两枚既有读数，既不碰 `_db_ready`，也不自己读 `os.getenv`。"""
    functions = _top_level_functions(_tree())
    gate = functions[GATE]
    calls = _callees(gate)
    body = [
        stmt for stmt in gate.body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
    ]
    source = chr(10).join(ast.unparse(stmt) for stmt in body)  # 只看可执行体，散文不算

    assert "_database_available" in calls and "_is_production_environment" in calls
    assert "_db_ready" not in source, "闸里自己读旗标 = 第二份「库在不在」判定"
    assert "getenv" not in calls and "APP_ENV" not in source
    assert "_MEM_ALERTS" not in source and "_MEM_RULES" not in source


def test_the_module_still_has_exactly_one_reader_of_the_ready_flag():
    """`_db_ready` 在本模块的读点仍是一枚（`app/common/auth.py:231` 那本账按枚数人）。"""
    tree = _tree()
    functions = _top_level_functions(tree)
    probe = functions["_database_available"]
    probe_lines = set(range(probe.lineno, (probe.end_lineno or probe.lineno) + 1))
    readers: list[int] = []
    for node in ast.walk(tree):
        loads_flag = (
            isinstance(node, ast.Name) and node.id == "_db_ready" and isinstance(node.ctx, ast.Load)
        ) or (
            isinstance(node, ast.Attribute) and node.attr == "_db_ready"
            and isinstance(node.ctx, ast.Load)
        ) or (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr"}
            and any(isinstance(arg, ast.Constant) and arg.value == "_db_ready"
                    for arg in node.args[1:2])
        )
        if loads_flag:
            readers.append(node.lineno)

    assert readers, "探针本体不见了，本单判据就无从谈起"
    assert len(readers) == 1, f"本模块多出了 `_db_ready` 读者，R246 那本账会红：{readers}"
    assert set(readers) <= probe_lines, "读点搬出了 `_database_available()`"


def test_the_module_did_not_grow_a_second_production_ruler():
    """`APP_ENV` 在本模块只出现一次：是不是生产仍然只由 `_is_production_environment()` 说了算。"""
    source = ALERTS_PY.read_text(encoding="utf-8")

    assert source.count('"APP_ENV"') == 1


# ================================================================= 丁：detail 字面量对账（照 R332）
def test_every_static_detail_in_the_module_is_a_ratified_code():
    """本模块每一枚静态可解析的 `detail` 都必须在封闭枚举里，一枚裸码都不许新造。

    手法照 `tests/test_r332_dashboard_trend.py`（AST 扫整个 `app/api/v1/dashboard.py`），
    多解一层模块级常量。枚举解析不出码名时对账当场红，不许降级成恒真。
    """
    codes = _enum_codes()
    assert codes, "枚举解析不出码名，对账不能降级成恒真"

    shapes = _detail_shapes(_tree())
    assert len(shapes) >= 6, f"扫描器只认出 {len(shapes)} 枚 detail，多半是形状变了"
    resolved = {code for _symbol, _kind, code in shapes if code is not None}

    unaccounted = sorted(code for code in resolved if code not in codes)
    assert unaccounted == [], f"本模块出现了枚举之外的裸码：{unaccounted}"
    assert STORAGE_CODE in resolved, "闸那一枚码没进对账，本件的钉就是空的"


def test_the_one_interpolated_detail_is_still_only_the_pre_existing_one():
    """插值型 detail 静态抠不到：把它钉成一枚存量，第二枚长出来就红。

    R332 那把钉直接断言「本模块零插值」。`alerts.py` 今天做不到——`create_rule` 那枚
    400 的 `detail=f"非法操作符: {data.op}"` 是存量口径，改掉它是响应体变更（另一枚单的
    事，本单不顺手做）。所以这里钉的是「存量恰好这一枚、且在原函数里」，效果等价：
    谁想用插值绕过码表对账，本枚当场红。已登记给总控，见回执「只报不改」。
    """
    interpolated = {
        symbol for symbol, kind, _code in _detail_shapes(_tree()) if kind == "interpolated"
    }
    opaque = {
        symbol for symbol, kind, _code in _detail_shapes(_tree()) if kind == "opaque"
    }

    assert interpolated == {"create_rule"}, (
        f"插值型 detail 长出了第二枚 {sorted(interpolated)}：码表对账会有读不到的洞"
    )
    # 两处 opaque 都是「码从参数进来」：`decision.reason_code`（授权层，R142 已单独记账）
    # 与 `_refuse_alert_disposal(code=...)`。名单钉死成这两枚，第三枚隐身就红。
    assert opaque == {"_require_alert_management", "_refuse_alert_disposal"}, (
        f"静态抠不到的 detail 又多了一处 {sorted(opaque)}：请连同码表一起改口，别让它隐身"
    )


def test_the_opaque_refusal_codes_are_still_ratified_at_their_call_sites():
    """上一枚钉把洞标出来，这一枚把洞填上：从参数进来的码逐枚在调用点对账。

    `_refuse_alert_disposal` 是三道处置拒绝出口共用的一次抛出，`code` 全是模块级常量，
    所以静态可解。授权层那一处（`detail=decision.reason_code`）的取值集合归
    `app/common/policy.py` 与 R142 那本账，本件不改它，也不许有新的调用点长进来。
    """
    tree = _tree()
    consts = _module_string_constants(tree)
    codes = {
        consts.get(argument.id)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "_refuse_alert_disposal"
        for argument in node.args[1:2]
        if isinstance(argument, ast.Name)
    }

    assert None not in codes, "处置拒绝的 code 实参不再是模块级常量，对账读不到了"
    assert codes == {
        ALERT_DISPOSAL_CODES["not_found"],
        ALERT_DISPOSAL_CODES["conflict"],
        ALERT_DISPOSAL_CODES["assignee"],
    }, f"处置拒绝的码集变了：{sorted(codes)}"
    assert codes <= _enum_codes(), f"从参数进来的裸码：{sorted(codes - _enum_codes())}"


def test_the_module_opens_exactly_one_storage_door():
    """整个模块只有那一处 503，且吐的就是既有那枚码：不许长出第二张「存储不在」的脸。"""
    tree = _tree()
    doors = [
        (symbol_of, code)
        for symbol_of, kind, code in _detail_shapes(tree)
        if False
    ]  # noqa: F841  -- 形状先说清楚：下面按 status_code 数，不按码名猜

    sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "HTTPException"
        and any(keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == 503 for keyword in node.keywords)
    ]
    assert len(sites) == 1, f"503 出口应当恰好一枚，实取 {len(sites)}: {[s.lineno for s in sites]}"
    assert _detail_shapes_of(sites[0], _module_string_constants(tree)) == STORAGE_CODE
    assert sites[0].lineno in range(
        _top_level_functions(tree)[GATE].lineno,
        (_top_level_functions(tree)[GATE].end_lineno or 0) + 1,
    ), "那枚 503 不在闸里：有人绕过闸自己拒答"


def _detail_shapes_of(call: ast.Call, consts: dict[str, str]) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != "detail":
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        if isinstance(value, ast.Name):
            return consts.get(value.id)
    return None


def test_the_refusal_word_is_the_one_the_repo_already_ships():
    """零新增错误码（判据甲后半）：同一个词在仓里已有三处 503 出口，本单只是第四条。"""
    neighbours = {
        "app/api/v1/dashboard.py": '"storage_unavailable"',
        "app/api/v1/notifications.py": "'storage_unavailable'",
        "app/api/v1/chat.py": '"storage_unavailable"',
    }

    for relative, literal in neighbours.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert literal in source and "status_code=503" in source, (
            f"{relative} 不再是那枚词的出处：本单的口径要跟它一起改口"
        )
    assert f'detail="{STORAGE_CODE}"' in ALERTS_PY.read_text(encoding="utf-8")
