"""R98 判据 1-3：checkpointer 不许谎报降级，也不许静默降级。

口径出处 = docs/handoff/2026-09-15-backend-followup-requests.md §41.1：
* 判据 1 —— 连接池必须 autocommit。PostgresSaver.setup() 自带三枚 CREATE INDEX
  CONCURRENTLY（实测 .venv/Lib/site-packages/langgraph/checkpoint/postgres/__init__.py 的
  MIGRATIONS[6]/[7]/[8]），psycopg 默认在事务块里执行 ⇒ 不开 autocommit 每次启动都必抛。
  这一条不改 migrations/**、不新增建表 SQL。
* 判据 2 —— 降级走 logger.error，并把"当前 checkpointer 后端"挂到 /api/v1/health/details；
  生产环境下降级即为不通过，口径同 app/api/v1/alerts.py:62 与 app/api/v1/chat.py:520。
* 判据 3 —— a) 传给池的 autocommit 参量与 setup() 调用次数；b) 探活真失败时确实退回
  MemorySaver 且打了 error 级日志；c) 新增的 health 节在 postgres / memory 两种后端下取值正确。

全程不碰数据库：psycopg、psycopg_pool、PostgresSaver 三样都是 monkeypatch 出来的桩，
tests/conftest.py 另把 DATABASE_URL 钉在保留端口 1 上兜底。
"""
import inspect
import logging
import sys
from types import SimpleNamespace

import psycopg
import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents import orchestrator
from app.common import monitoring

#: 生产环境实证那句真因（跟进单 §41.1 的日志原文），反证与断言都拿它当靶子。
TRANSACTION_BLOCK_ERROR = "CREATE INDEX CONCURRENTLY cannot run inside a transaction block"

#: 旧代码那句谎话的字面片段。任何一条日志里都不许再出现。
LIE = "Postgres 不可用"


class _FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakePool:
    def __init__(self, conninfo, kwargs):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.closed = False

    def close(self):
        self.closed = True


class _Instrument:
    """一台能同时读出"探了几次活、建了几个池、setup() 被叫了几次"的仪器。"""

    def __init__(self):
        self.calls = []
        self.connections = []
        self.pools = []
        self.savers = []
        self.connect_error = None
        self.setup_error = None
        instrument = self

        class FakePsycopg:
            @staticmethod
            def connect(conninfo, **kwargs):
                instrument.calls.append("connect")
                connection = _FakeConnection()
                instrument.connections.append({"conninfo": conninfo, "kwargs": kwargs})
                if instrument.connect_error is not None:
                    raise instrument.connect_error
                return connection

        def fake_connection_pool(conninfo, **kwargs):
            instrument.calls.append("pool")
            pool = _FakePool(conninfo, kwargs)
            instrument.pools.append(pool)
            return pool

        self.psycopg = FakePsycopg
        self.psycopg_pool = SimpleNamespace(ConnectionPool=fake_connection_pool)

        class FakePostgresSaver:
            def __init__(self, conn):
                self.conn = conn

            def setup(self):
                instrument.calls.append("setup")
                instrument.savers.append(self)
                if instrument.setup_error is not None:
                    raise instrument.setup_error

        self.saver_class = FakePostgresSaver

    @property
    def pool_kwargs(self):
        assert len(self.pools) == 1, self.calls
        return self.pools[0].kwargs


@pytest.fixture
def db(monkeypatch):
    """把 orchestrator 看得见的外部依赖换成桩；判据 3 明令"不许真连数据库"。"""
    import langgraph.checkpoint.postgres as postgres_checkpoint

    instrument = _Instrument()
    monkeypatch.setattr(orchestrator, "psycopg", instrument.psycopg)
    monkeypatch.setattr(orchestrator, "psycopg_pool", instrument.psycopg_pool)
    monkeypatch.setattr(postgres_checkpoint, "PostgresSaver", instrument.saver_class)
    monkeypatch.setenv("APP_ENV", "development")
    # _make_checkpointer() 是整体改写模块级状态的，这里用"同值 setattr"记下原值，用例结束
    # 由 monkeypatch 自动还原，免得 postgres 后端的结论漏给全量回归里的下一个用例。
    monkeypatch.setattr(orchestrator, "_CHECKPOINT_STATE", orchestrator.checkpointer_storage_state())
    return instrument


def _error_lines(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]


# ------------------------------------------------------------------------------------
# 判据 1 + 判据 3a：池必须 autocommit，setup() 必须真的被叫到一次
# ------------------------------------------------------------------------------------
def test_the_pool_is_opened_in_autocommit_and_setup_runs_once(db):
    checkpointer = orchestrator._make_checkpointer()

    # 顺序也是判据的一部分：探活失败就不该先建池（旧代码同一个 try 里两件事，才让
    # "池建好了、setup() 炸了"被读成"数据库不可用"）。
    assert db.calls == ["connect", "pool", "setup"], db.calls
    assert db.pool_kwargs["kwargs"]["autocommit"] is True
    assert db.pool_kwargs["kwargs"] == {"autocommit": True, "prepare_threshold": 0}
    assert db.pool_kwargs["open"] is True
    assert len(db.savers) == 1
    # setup() 跑的就是那个 autocommit 池，不是另一条连接。
    assert db.savers[0].conn is db.pools[0]
    assert checkpointer is db.savers[0]
    assert db.pools[0].closed is False
    assert db.connections[0]["kwargs"] == {"connect_timeout": 2}
    assert orchestrator.checkpointer_storage_state()["backend"] == "postgres"
    # 判据 1 的边界：修 autocommit 不靠自己动 DDL，migrations/** 一律没被我们碰过。
    source = inspect.getsource(orchestrator._make_checkpointer)
    assert ".execute(" not in source, source
    assert "CREATE TABLE" not in source.upper(), source


# ------------------------------------------------------------------------------------
# 判据 3b：探活真失败 → 确实退回 MemorySaver，而且打的是 error 级
# ------------------------------------------------------------------------------------
def test_a_failed_probe_degrades_in_development_and_logs_at_error_level(db, caplog):
    db.connect_error = psycopg.OperationalError("connection to server at 127.0.0.1 port 1 failed")

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        checkpointer = orchestrator._make_checkpointer()

    assert isinstance(checkpointer, MemorySaver)
    assert db.pools == [], "探活失败不该再建池"
    errors = _error_lines(caplog)
    assert errors, "降级不许再静默：至少要有一行 error"
    assert any("Postgres 探活失败" in line for line in errors), caplog.text
    assert any("数据库不可达" in line and "port 1 failed" in line for line in errors), caplog.text
    assert any("已降级 MemorySaver" in line for line in errors), caplog.text
    state = orchestrator.checkpointer_storage_state()
    assert state["backend"] == "memory" and state["durable"] is False
    assert "port 1 failed" in state["detail"]


# ------------------------------------------------------------------------------------
# 判据 2 的反证靶：真因是事务块，就不许再写成"Postgres 不可用"
# ------------------------------------------------------------------------------------
def test_a_setup_failure_is_never_blamed_on_postgres_being_unavailable(db, caplog):
    db.setup_error = RuntimeError(TRANSACTION_BLOCK_ERROR)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        checkpointer = orchestrator._make_checkpointer()

    assert isinstance(checkpointer, MemorySaver)
    assert db.calls == ["connect", "pool", "setup"], db.calls
    all_lines = [record.getMessage() for record in caplog.records]
    assert all(LIE not in line for line in all_lines), all_lines
    errors = _error_lines(caplog)
    assert any(TRANSACTION_BLOCK_ERROR in line for line in errors), caplog.text
    assert any("数据库可达" in line for line in errors), caplog.text
    # 池建了又失败就要收尾，别把 5 条连接漏在开发态进程里。
    assert db.pools[0].closed is True
    state = orchestrator.checkpointer_storage_state()
    assert state["backend"] == "memory" and "transaction block" in state["detail"]


# ------------------------------------------------------------------------------------
# 判据 2 + 3c：health 那一节在两种后端下都要取对值，并且与 orchestrator 同源
# ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            "postgres",
            {
                "storage_mode": "postgres",
                "durable": True,
                "shared_across_processes": True,
                "backend": "postgres",
            },
        ),
        (
            "memory",
            {
                "storage_mode": "memory",
                "durable": False,
                "shared_across_processes": False,
                "backend": "memory",
            },
        ),
    ],
)
def test_the_checkpointer_block_reports_both_backends(db, outcome, expected):
    if outcome == "memory":
        db.connect_error = psycopg.OperationalError("connection refused")

    orchestrator._make_checkpointer()

    section = monitoring.checkpointer_storage_state()
    assert section == orchestrator.checkpointer_storage_state(), "两块必须同源"
    for key, value in expected.items():
        assert section[key] is value, section
    assert section["detail"], section
    assert section["protection"] == "none", section


def test_the_checkpointer_block_is_served_by_the_health_route(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    # 健康快照的三个依赖探针一律不打真 socket（同 tests/test_deployment_guards.py:41）。
    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})
    orchestrator._make_checkpointer()

    client = TestClient(app)
    response = client.get(
        "/api/v1/health/details",
        headers={"Authorization": f"Bearer {auth.create_token('admin')}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "checkpointer" in body, sorted(body)
    assert body["checkpointer"] == orchestrator.checkpointer_storage_state()
    assert body["checkpointer"]["storage_mode"] == "postgres"


def test_monitoring_answers_honestly_before_the_orchestrator_has_loaded(monkeypatch):
    # orchestrator 是懒导入的（app/api/v1/chat.py:1201），所以"还没决定"是一个真状态；
    # 但 monitoring 自建的兜底形状必须和真出口逐键相等，否则两处的键会各写各的。
    monkeypatch.setitem(sys.modules, "app.agents.orchestrator", None)

    fallback = monitoring.checkpointer_storage_state()

    assert set(fallback) == set(orchestrator.checkpointer_storage_state())
    assert fallback["backend"] == "none" and fallback["durable"] is False
    assert "not built a checkpointer yet" in fallback["detail"]


# ------------------------------------------------------------------------------------
# 判据 2 的生产口径：降级即不通过（与 alerts.py:62、chat.py:520 同一句话）
# ------------------------------------------------------------------------------------
@pytest.mark.parametrize("stage", ["probe", "setup"])
def test_production_refuses_a_degraded_checkpointer(db, monkeypatch, caplog, stage):
    monkeypatch.setenv("APP_ENV", "production")
    if stage == "probe":
        db.connect_error = psycopg.OperationalError("connection refused")
    else:
        db.setup_error = RuntimeError(TRANSACTION_BLOCK_ERROR)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(RuntimeError, match="required in production; run migrations first"):
            orchestrator._make_checkpointer()

    assert not any(LIE in record.getMessage() for record in caplog.records), caplog.text
    assert any(record.levelno >= logging.ERROR for record in caplog.records), caplog.text
    state = orchestrator.checkpointer_storage_state()
    assert state["storage_mode"] == "unavailable" and state["backend"] == "none"
    assert state["protection"] == "refuse_start", state
