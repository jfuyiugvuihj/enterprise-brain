"""R367 · 看板那两屏不许把「存储没答话」画成「这家公司一切正常」。

症状（总控在基点 `b291324` 现取，本件不重述论证）：R359（并树 `4382443`）给
`app/api/v1/alerts.py:64 _require_ready_store` 装了闸门，生产 + 无库 ⇒ 九枚告警出口改答
503 `storage_unavailable`。同一台坏机上，看板两屏仍从进程内台账读数：
`app/api/v1/dashboard.py::_alert_counts` / `::_alert_series` 在 `_database_available()` 为假时
数 `alerts._MEM_ALERTS`（客户机上永远为空），`::_pending_count` 走
`pending_approvals.open_items`，而那条腿在无库时静默回落 `_MEM_ROWS`。于是
`GET /dashboard/summary` 交四格零、`GET /dashboard/trend` 交全零折线，而 R340 那套按档边
回放的口径在一具空尸体上算得完美无缺。

本件的判据分两张脸，两方向各有一组钉：

- **甲 生产 + 对应 store 不在 ⇒ 整屏 503**（判据 1）：两条路由都答 `503
  storage_unavailable`，零新增错误码。为什么不能只让某一格不供数：`alerts` 那一格的缺席已经
  被**权限**占了（403 ⇒ 键消失），再拿它表达「存储坏了」就是两件事一张脸；
  `documents_ready` 又被 R284 钉成「永远是一枚整数」。
- **乙 开发态与裸机一个字都不改**（判据 2）：内存 store 今天仍是合法后端，那一支的回包
  形状、键在不在、行数、排序逐字保持 —— `test_development_*` 与
  `test_every_non_production_name_*` 逐枚点名。把开发态一起打死同样是说假话，只不过反着说，
  所以这一组钉就是反证刀③的靶子。
- **丙 不新造第三本探针账**（判据 3）：生产判定沿用 `alerts._is_production_environment()`
  那一枚既有读数，库在不在沿用各条腿自己的 `_database_available()`；静态那半枚在
  `tests/test_r367_gate_shape_pins.py`，本件的环境钉则证明用的是**那一枚**名单而不是抄本。
- **丁 闸门排在授权之后**（判据 4）：匿名 401、无 analyze 权限 403、被告警门拒掉的调用方
  仍然只丢键 —— 这三枚钉就是反证刀④的靶子。
- **戊 待批那两条路互不冒充**（判据 5）：PG 整个不在 ⇒ 本单新闸，`open_items` 一次都不许
  被调用；PG 在而 `0008` 没跑 ⇒ `:149` 那枚既有捕获，`open_items` 必须被调用；其它
  `RuntimeError` 仍然原样往上走，不许被翻成 503。

全部离线：不起服务、不连库、不打模型、不写 `chroma_db/`。文档与数据集那两本书钉在
`tmp_path` 的 JSON 路径上，所以没有一枚用例数到宿主的真实目录，也没有一枚读 `auth._db_ready`。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.contracts import ErrorEnvelope
from app.common.auth import create_token
from app.main import app
from app.storage import pending_approvals as ledger

SUMMARY = "/api/v1/dashboard/summary"
TREND = "/api/v1/dashboard/trend"

#: 仓里已有的那一码：`_pending_count` 的既有捕获、`_trend_unreadable`、通知、/users 都在吐它。
STORAGE_CODE = "storage_unavailable"

SHANGHAI = timezone(timedelta(hours=8))

MANAGER = "r367-manager"
STAFF = "r367-staff"
OUTSIDER = "r367-outsider"


def _user(username: str, department: str, role: str = "manager") -> dict:
    return {"id": username, "username": username, "role": role, "department": department}


ACCOUNTS = {
    MANAGER: _user(MANAGER, "finance"),
    STAFF: _user(STAFF, "finance", "staff"),
    # 没有 resource:analyze：看板两屏共用那道门，它两边都进不来。
    OUTSIDER: _user(OUTSIDER, "legal", "auditor"),
}


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _alert_row(message: str, *, department: str, read: bool = False,
               created_at: str = "2026-09-20T09:00:00+08:00") -> dict:
    """One alert in the shape ``alerts.py`` stamps, disposal columns included."""
    return {
        "id": 1, "rule_id": 7, "message": message, "ai_analysis": "",
        "department": department, "created_at": created_at, "read": read,
        "status": "open", "acknowledged_at": "", "closed_at": "",
    }


class _Spy:
    """Count how often a leg was entered: that count is what tells this ticket's gate apart
    from R13's pre-existing catch, so the two doors cannot impersonate each other."""

    def __init__(self, target=None, result=None, error: Exception | None = None) -> None:
        self.calls = 0
        self._target = target
        self._result = result
        self._error = error

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._target is not None:
            return self._target(*args, **kwargs)
        return self._result


class _AlertConnection:
    """The PostgreSQL answer for both alert legs: one count row, one series of rows."""

    def __init__(self, count_row: dict, rows: list[dict]) -> None:
        self.count_row = count_row
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, text, params=None):
        if "COUNT(*)" in text:
            return SimpleNamespace(fetchone=lambda: self.count_row)
        return SimpleNamespace(fetchall=lambda: [dict(row) for row in self.rows])


class _NoLedgerTableConnection:
    """PostgreSQL is up and migration ``0008`` is not: ``to_regclass`` answers NULL."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, text, params=None):
        return SimpleNamespace(fetchone=lambda: {"table_name": None})


class Machine:
    """One install, wired so a test only chooses 「is this production」 and 「which store is up」.

    Nothing is stubbed on the judgment side: the only switches are the two existing probes
    (``alerts._database_available`` / ``pending_approvals._database_available``) and
    ``APP_ENV``, which is what the production reader actually looks at.
    """

    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        from app.api.v1 import alerts as alerts_module
        from app.api.v1 import data
        from app.common import auth
        from app.documents import catalog
        from app.storage import datasets as datasets_module
        from app.storage.datasets import DatasetRegistry

        self.mp = monkeypatch
        self.alerts = alerts_module
        self.ledger = ledger

        monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))

        # The two books this ticket does not touch, pinned to their offline JSON path inside
        # tmp_path: no case can count a host directory or a real ``document_versions`` table.
        monkeypatch.setattr(catalog, "_database_available", lambda: False)
        documents = tmp_path / "documents"
        documents.mkdir()
        monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(documents))
        root = tmp_path / "data"
        root.mkdir()
        registry = DatasetRegistry(root=root, metadata_path=root / ".dataset-metadata.json")
        monkeypatch.setattr(data, "DATA_DIR", str(root))
        monkeypatch.setattr(data, "dataset_registry", registry)
        monkeypatch.setattr(datasets_module, "dataset_registry", registry)

        monkeypatch.setattr(alerts_module, "_MEM_ALERTS", [])
        monkeypatch.setattr(alerts_module, "_ensure", lambda: None)
        monkeypatch.setattr(alerts_module, "_conn",
                            lambda: _AlertConnection({"total": 0, "unread": 0}, []))
        monkeypatch.setattr(ledger, "_MEM_ROWS", {})
        monkeypatch.setattr(ledger, "_conn", lambda: _NoLedgerTableConnection())

        # Every leg keeps its real body; the spy only counts. That is what makes
        # ``open_items.calls`` a reading rather than a wish.
        self.read_ledger = _Spy(target=ledger.open_items)
        monkeypatch.setattr(ledger, "open_items", self.read_ledger)
        self.client = TestClient(app)

    # ------------------------------------------------------------------ the environment
    def production(self) -> "Machine":
        return self.environment("production")

    def development(self) -> "Machine":
        return self.environment("development")

    def environment(self, value: str) -> "Machine":
        self.mp.setenv("APP_ENV", value)
        return self

    def no_environment(self) -> "Machine":
        self.mp.delenv("APP_ENV", raising=False)
        return self

    # ------------------------------------------------------------------------ the legs
    def alerts_missing(self, *rows: dict) -> "Machine":
        """No store: the in-process list below is all this machine has, and that is the lie."""
        self.mp.setattr(self.alerts, "_database_available", lambda: False)
        self.mp.setattr(self.alerts, "_MEM_ALERTS", list(rows))
        return self

    def alerts_present(self, *, total: int = 0, unread: int = 0) -> "Machine":
        self.mp.setattr(self.alerts, "_database_available", lambda: True)
        self.mp.setattr(
            self.alerts, "_conn",
            lambda: _AlertConnection({"total": total, "unread": unread}, []),
        )
        self.mp.setattr(self.alerts, "_MEM_ALERTS", [])
        return self

    def ledger_missing(self, *, parked: int = 0) -> "Machine":
        """PG is not there at all: the real read walks ``_MEM_ROWS`` and raises nothing."""
        self.mp.setattr(self.ledger, "_database_available", lambda: False)
        for index in range(parked):
            ledger.record_awaiting(f"r367-{index}", MANAGER, ["chart"], request_id="req-1")
        return self

    def ledger_present(self, *, rows: int = 0) -> "Machine":
        """The ledger answers, so any refusal on the screen can only have come from another leg."""
        self.mp.setattr(self.ledger, "_database_available", lambda: True)
        self.read_ledger = _Spy(result=[{"id": n} for n in range(rows)])
        self.mp.setattr(self.ledger, "open_items", self.read_ledger)
        return self

    def ledger_table_absent(self) -> "Machine":
        """PG is up and ``0008`` is not: the real read raises the real named error."""
        self.mp.setattr(self.ledger, "_database_available", lambda: True)
        return self

    def ledger_broken(self, error: Exception) -> "Machine":
        self.mp.setattr(self.ledger, "_database_available", lambda: True)
        self.read_ledger = _Spy(error=error)
        self.mp.setattr(self.ledger, "open_items", self.read_ledger)
        return self


@pytest.fixture()
def machine(monkeypatch, tmp_path):
    return Machine(monkeypatch, tmp_path)


# ------------------------------------------------------ 甲 · 生产 + 无库 ⇒ 整屏拒答（判据 1）
def test_summary_refuses_when_the_alert_store_is_not_there(machine):
    """`_alert_counts` 的无库一支：客户机上那张表永远是空的，零不是答案。"""
    machine.production().ledger_present(rows=1).alerts_missing(
        _alert_row("R367T 本部门营收跌破阈值", department="finance"),
        _alert_row("R367T 已读的那一条", department="finance", read=True),
    )

    response = machine.client.get(SUMMARY, headers=_headers(MANAGER))

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert '"alerts"' not in response.text, "拒答里还夹着一格数出来的零，就是本单要修的那张脸"


def test_trend_refuses_when_the_alert_store_is_not_there(machine):
    """`_alert_series` 的无库一支：全零折线连同 R340 那套完美无缺的档边回放一起作废。"""
    machine.production().ledger_present().alerts_missing(
        _alert_row("R367T 这个月的一条", department="finance",
                   created_at=datetime.now(SHANGHAI).isoformat()),
    )

    response = machine.client.get(TREND, headers=_headers(MANAGER))

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert "series" not in response.json(), "半条折线比整条更难看：这一屏没有部分作答的形状"


def test_summary_refuses_when_the_ledger_store_is_not_there(machine):
    """判据 1 + 5（待批腿 · 新闸）：PG 整个不在时 `open_items` 一次都不许被调用。"""
    machine.production().alerts_present(total=4, unread=2).ledger_missing()

    response = machine.client.get(SUMMARY, headers=_headers(MANAGER))

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert machine.read_ledger.calls == 0, (
        "走到了 open_items：那是「静默回落 _MEM_ROWS 再数」的旧路，本单判的就是它不许被走"
    )


def test_a_tile_that_did_answer_does_not_rescue_the_screen(machine):
    """判据 1：整屏拒答，不是「某一格不供数」—— 另一条腿答得出来也救不回来。"""
    machine.production().ledger_present(rows=3).alerts_missing(
        _alert_row("R367T 空表上的告警", department="finance"),
    )

    response = machine.client.get(SUMMARY, headers=_headers(MANAGER))

    assert response.status_code == 503, response.text
    assert set(response.json()) == {"detail"}, "屏上还剩几格数字，就是把拒答做成了一半作答"


#: 哪一屏赖以计数、哪一屏不赖：/trend 没有待批那一格，本单就不许给它加一道待批的闸
#: （多拒一次同样是替调用方编故事，判据 2 分的是两张脸，不是一律 503）。
@pytest.mark.parametrize(
    "route, leg, refuses",
    [
        (SUMMARY, "alerts", True),
        (SUMMARY, "ledger", True),
        (TREND, "alerts", True),
        (TREND, "ledger", False),
    ],
)
def test_the_refusal_wears_the_code_the_repo_already_ships(machine, route, leg, refuses):
    """判据 1 后半 · 零新增错误码：拒答的那几格吐的都是仓里那一枚词，且它在枚举里。"""
    machine.production()
    if leg == "alerts":
        machine.ledger_present().alerts_missing()
    else:
        machine.alerts_present().ledger_missing()

    response = machine.client.get(route, headers=_headers(MANAGER))

    if not refuses:
        assert response.status_code == 200, response.text
        assert set(response.json()) == {
            "generated_for", "period", "buckets", "time_zone", "series", "undated"
        }, "本单给 /trend 长出了一种它没有的腿：那一屏不数待批"
        return
    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert STORAGE_CODE in get_args(ErrorEnvelope.__annotations__["code"]), (
        "这一码不在枚举里，本单就成了新增错误码"
    )


# ------------------------------------- 乙 · 开发态与裸机一个字都不改（判据 2，反证刀③的靶）
def test_development_still_counts_the_memory_ledgers_verbatim(machine):
    """裸机上内存 store 是合法后端：回包的键、行数、形状逐字保持，包括待批那一格。"""
    machine.no_environment().ledger_missing(parked=2).alerts_missing(
        _alert_row("R367T 本机第一条", department="finance"),
        _alert_row("R367T 本机已读的一条", department="finance", read=True),
    )

    response = machine.client.get(SUMMARY, headers=_headers(MANAGER))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "generated_for": MANAGER,
        "pending_approvals": 2,
        "documents": 0,
        "documents_ready": 0,
        "datasets": 0,
        "alerts": {"total": 2, "unread": 1},
    }
    assert machine.read_ledger.calls == 1, "开发态那一次读被本单省掉了，就不是「一个字都不改」"


def test_development_still_draws_the_memory_alert_bars(machine):
    """判据 2：/trend 那一支照旧从内存台账画折线，档边回放的口径不许被本单打哑。"""
    stamp = datetime.now(SHANGHAI)
    machine.development().ledger_missing().alerts_missing(
        _alert_row("R367T 本月未闭环", department="finance", created_at=stamp.isoformat()),
        _alert_row("R367T 本月已读的那一条", department="finance", read=True,
                   created_at=stamp.isoformat()),
    )

    response = machine.client.get(TREND, headers=_headers(MANAGER))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["series"][-1]["alerts"] == 2, "开发态那根柱子被本单一起打死了"
    assert body["series"][-1]["alerts_open"] == 2
    assert sum(point["alerts"] for point in body["series"]) == 2
    assert {"alerts", "alerts_open"} <= set(body["undated"])


@pytest.mark.parametrize("environment", ["development", "staging", "test", "production-line"])
def test_every_non_production_name_keeps_answering(machine, environment):
    """判据 2：分开的是两张脸，不是一律 503 —— 名单沿用 alerts 那一枚，一词不加一词不改。"""
    machine.environment(environment).ledger_present().alerts_missing(
        _alert_row("R367T 这台机器没有库，但有台账", department="finance"),
    )

    assert machine.client.get(SUMMARY, headers=_headers(MANAGER)).status_code == 200
    assert machine.client.get(TREND, headers=_headers(MANAGER)).status_code == 200


@pytest.mark.parametrize("environment", ["production", "prod", "PRODUCTION", " prod "])
def test_every_production_name_refuses(machine, environment):
    """判据 1 的边界：`strip().lower() in {"production", "prod"}` 是 alerts 的那一枚读数。"""
    machine.environment(environment).ledger_present().alerts_missing()

    assert machine.client.get(SUMMARY, headers=_headers(MANAGER)).status_code == 503
    assert machine.client.get(TREND, headers=_headers(MANAGER)).status_code == 503


# -------------------------------------- 丁 · 闸门次序（判据 4，反证刀④的靶）
@pytest.mark.parametrize("route", [SUMMARY, TREND])
def test_an_anonymous_caller_still_hears_the_permission_answer(machine, route):
    """先答「你是谁」，再答「这台机器的库在不在」—— 反过来 503 就成了一枚探针。"""
    machine.production().ledger_missing().alerts_missing()

    assert machine.client.get(route).status_code == 401


@pytest.mark.parametrize("route", [SUMMARY, TREND])
def test_a_caller_without_analyze_rights_still_hears_the_permission_answer(machine, route):
    """判据 4：没有 analyze 权限的调用方拿 403，与这家客户起没起 PG 无关。"""
    machine.production().ledger_missing().alerts_missing()

    assert machine.client.get(route, headers=_headers(OUTSIDER)).status_code == 403


@pytest.mark.parametrize("route", [SUMMARY, TREND])
def test_a_denied_alert_caller_still_loses_the_key_rather_than_the_screen(machine, route):
    """判据 4：403 ⇒ 键消失这一枚既有形状不许动，闸只能在拿到 principal 之后落。"""
    machine.production().ledger_present(rows=2).alerts_missing(
        _alert_row("R367T 员工看不见的那一条", department="finance"),
    )

    response = machine.client.get(route, headers=_headers(STAFF))

    assert response.status_code == 200, response.text
    body = response.json()
    assert "alerts" not in body
    assert not [key for point in body.get("series", []) for key in point if "alert" in key]
    assert not [key for key in body.get("undated", {}) if "alert" in key]
    if route == SUMMARY:
        assert body["pending_approvals"] == 2, "待批那一格答得好好的，屏不许跟着少一格"


# ------------------------------------ 戊 · 待批那两条路互不冒充（判据 5）
def test_the_missing_ledger_table_still_refuses_through_the_pre_existing_catch(machine):
    """判据 5：PG 在、`0008` 没跑 ⇒ 走 `:149` 那枚既有捕获，本单的闸一次都不许抢先。"""
    machine.production().alerts_present().ledger_table_absent()

    response = machine.client.get(SUMMARY, headers=_headers(MANAGER))

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert machine.read_ledger.calls == 1, (
        "open_items 没被调用：新闸抢了既有捕获那条路，两条路就冒充成一枚了"
    )


def test_the_pre_existing_catch_still_names_the_migration_it_waits_for(machine):
    """判据 5：既有捕获仍是 `raise ... from exc`，运维要的仍是「run migrations」那一句。"""
    machine.production().alerts_present().ledger_table_absent()

    with pytest.raises(ledger.PendingApprovalStoreMissing) as caught:
        ledger.open_items(owner_user_id=MANAGER)

    assert "migrations/0008" in str(caught.value)


@pytest.mark.parametrize("door", ["no_store", "no_table"])
def test_the_two_ledger_refusals_are_two_different_doors(machine, door):
    """判据 5：两条路各留各的凭据 —— 新闸不带动因、不碰账本；既有捕获带着缺表那个因。"""
    from app.api.v1 import dashboard

    machine.production().alerts_present()
    if door == "no_store":
        machine.ledger_missing()
    else:
        machine.ledger_table_absent()

    with pytest.raises(HTTPException) as caught:
        dashboard._pending_count(SimpleNamespace(user_id=MANAGER))

    error = caught.value
    assert (error.status_code, error.detail) == (503, STORAGE_CODE)
    if door == "no_store":
        assert machine.read_ledger.calls == 0, "新闸之后还去读了账本，两条路就并成一条了"
        assert error.__cause__ is None, "无库这一支不许由缺表那个因引起"
    else:
        assert machine.read_ledger.calls == 1, "既有捕获那条路被本单的闸抢先了"
        assert isinstance(error.__cause__, ledger.PendingApprovalStoreMissing), (
            "缺表这一支的因被换掉了：那枚具名异常就是它存在的理由"
        )
        assert "migrations/0008" in str(error.__cause__)


def test_any_other_ledger_failure_keeps_its_own_shape(machine):
    """判据 5：把任何 RuntimeError 都翻成 503 等于替真正的 bug 打掩护 —— 驱动缺失同理。"""
    machine.production().alerts_present().ledger_broken(RuntimeError("connection pool exhausted"))

    with pytest.raises(RuntimeError, match="connection pool exhausted"):
        machine.client.get(SUMMARY, headers=_headers(MANAGER))
