"""R602 · 通知中心那条 PG 腿：row_factory 必须真的走到驱动，而不只是"从手里递出去"。

事故 #106（跟进单 §160.7）：`app/notifications/states.py::_conn` 从 `fea3161`（09-26，
R299 的收口笔）起写的是 `open_connection_with_policy(settings, row_factory=dict_row)`，
而边界那枚 `connect_with_policy` 从前是全具名关键字、无 `**kwargs` —— 多给的 `row_factory`
无处可去，这条腿一被走到就 TypeError。它在真库里一次都没通过而全量门一路绿，原因只有一句：**在册
测试桩全部打在 `states._conn` 上**。所以本件第一条纪律写死在这里 ——

    🔴 本文件一枚 `_conn` 桩都不许有。看守的是真签名：要么从 `connect_with_policy` 自己那
    四枚注入缝（connect / transient / sleep / clock）喂一枚会收下 row_factory 的假 connect
    并断言它真被传到，要么走 `R602_REAL_PG=1` 那枚端到端（默认 skip，常驻门一次真握手都不发）。

零真库、零服务、零模型：除最后那枚按 env 开关的端到端之外，本件不发一次握手。
"""
import os

import psycopg
import pytest
from psycopg.rows import dict_row

from app.db import connection
from app.notifications import states as state_store

#: 一枚永不落地的 DSN（tests/conftest.py:41 同一口径）：本件所有的"连"都停在假 connect 上。
URL = "postgresql://r602_pytest@127.0.0.1:1/r602_pytest"

#: 四枚策略开关逐枚擦干净：策略读数来自 os.environ，不许带上上一枚的粘性。
POLICY_ENVS = (
    connection.ENV_CONNECT_TIMEOUT,
    connection.ENV_CONNECT_KEEPALIVES,
    connection.ENV_CONNECT_ATTEMPTS,
    connection.ENV_CONNECT_BUDGET,
)

#: 端到端那枚钉的开关。默认关：常驻门不许对真库发一次握手（照 tests/test_r540_* 的先例）。
REAL_PG = os.environ.get("R602_REAL_PG") == "1"


class Boom(Exception):
    pass


class RecordingConnect:
    """会收下 row_factory 的假 connect：只记账，绝不握手。"""

    def __init__(self, failures=()):
        self.calls = []
        self._failures = list(failures)

    def connect(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._failures:
            raise self._failures.pop(0)
        return "conn<%d>" % len(self.calls)


def _clean_policy(monkeypatch):
    """把四枚策略 env 擦干净：这一节的默认就是"关着"，判据①那条账按默认读。"""
    for name in POLICY_ENVS:
        monkeypatch.delenv(name, raising=False)


def _pg_world(monkeypatch):
    """只把"库在不在"那一格拧成真，`_conn` 一个字都不桩 —— 桩 _conn 就是本单的病。"""
    monkeypatch.setattr(state_store, "_database_available", lambda: True)


# ------------------------------------------------------------------ 判据③：真签名
def test_the_real_states_conn_leg_delivers_row_factory_to_the_driver(monkeypatch):
    """本单核心那一枚：真 `states._conn()` 一路走到驱动，驱动必须真收到 row_factory。

    换掉的入口是驱动那一层（`psycopg.connect`），不是 `_conn`：`_conn` 与被它调用的
    `open_connection_with_policy` / `connect_with_policy` 全程原样跑，所以这枚咬的是**签名
    接得住**，不是"形状看着像"。把 `states.py` 里那枚 `row_factory=dict_row` 摘掉，这枚
    当场红（判据④·甲）。
    """
    driver = RecordingConnect()
    _clean_policy(monkeypatch)
    monkeypatch.setattr(psycopg, "connect", driver.connect)

    result = state_store._conn()

    assert result == "conn<1>", result
    assert len(driver.calls) == 1, driver.calls
    args, kwargs = driver.calls[0]
    assert args == (state_store._PG_URL,), args
    assert kwargs.get("row_factory") is dict_row, (
        "row_factory 又递不下去了：驱动那一层收到 %r —— 通知中心的 PG 腿会当场 TypeError" % (kwargs,)
    )


def test_the_recipient_read_reaches_the_driver_with_row_factory(monkeypatch):
    """读腿整条走一遍（`recipient_states` -> `_conn`），不许只在 `_conn` 那一格验。

    这枚把调用方也拖进来：`_require_table` 读的是 `row["table_name"]`，所以驱动一旦收不到
    `row_factory`，即便签名侥幸不抛，读回来也是 tuple，那一格只是换一种死法。
    """
    _clean_policy(monkeypatch)
    _pg_world(monkeypatch)

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            if "to_regclass" in sql:
                return _Result([{"table_name": "notification_states"}])
            return _Result([{"notification_id": "alert:1", "state": "read"}])

    made = []

    def connect(*args, **kwargs):
        assert kwargs.get("row_factory") is dict_row, kwargs
        made.append(args)
        return _Conn()

    monkeypatch.setattr(psycopg, "connect", connect)

    assert state_store.recipient_states("r602") == {"alert:1": "read"}
    assert made == [(state_store._PG_URL,)], made


def test_forwarding_leaves_the_bare_call_shape_alone_when_the_caller_says_nothing(monkeypatch):
    """判据①那本账不许被转发撞坏：调用方不多给一枚时，发出去的调用逐字节等于今天。

    `connect_kwargs` 关着时交回空 dict，转发格为空时合并出来还是空 dict。这枚一红就说明
    "修 row_factory"顺手给默认路径加了参数 —— 那是 R238 判据①的雷，不归本单。
    """
    driver = RecordingConnect()
    _clean_policy(monkeypatch)

    settings = connection.parse_database_settings(URL)
    connection.open_connection_with_policy(settings, connect=driver.connect)

    assert driver.calls == [((URL,), {})], driver.calls


def test_a_forwarded_kwarg_and_a_policy_kwarg_travel_in_the_same_call(monkeypatch):
    """操作者拧开超时 env 时，转发那一格与策略那枚必须同时到驱动。"""
    driver = RecordingConnect()
    _clean_policy(monkeypatch)
    monkeypatch.setenv(connection.ENV_CONNECT_TIMEOUT, "3")

    connection.connect_with_policy(URL, connect=driver.connect, row_factory=dict_row)

    assert driver.calls == [((URL,), {"row_factory": dict_row, "connect_timeout": 3})], driver.calls


def test_the_policy_wins_over_a_caller_supplied_latency_kwarg(monkeypatch):
    """调用方拿同名键盖操作者的读数 = 不许（R238 判据③：时延参数只许一处说了算）。"""
    driver = RecordingConnect()
    _clean_policy(monkeypatch)
    monkeypatch.setenv(connection.ENV_CONNECT_TIMEOUT, "3")

    connection.connect_with_policy(URL, connect=driver.connect, connect_timeout=99, row_factory=dict_row)

    assert driver.calls[0][1] == {"row_factory": dict_row, "connect_timeout": 3}, driver.calls[0][1]


def test_the_retry_seams_still_bite_next_to_a_forwarded_kwarg(monkeypatch):
    """四枚测试缝一枚都不许被转发撞坏，且重试的每一次都带上转发那一枚。

    `transient` / `sleep` / `clock` 走的还是 R238 那条算式，转发只多并入一个 dict。这枚
    顺带反证"每次重试重新算一遍 kwargs"那类写法：三发必须逐字节同形。
    """
    driver = RecordingConnect(failures=[Boom("blip"), Boom("blip2"), Boom("blip3")])
    slept = []
    _clean_policy(monkeypatch)

    with pytest.raises(Boom):
        connection.connect_with_policy(
            URL,
            environ={connection.ENV_CONNECT_ATTEMPTS: "3"},
            connect=driver.connect,
            transient=(Boom,),
            sleep=slept.append,
            clock=lambda: 0.0,
            row_factory=dict_row,
        )

    assert len(driver.calls) == 3, driver.calls
    assert all(call[1].get("row_factory") is dict_row for call in driver.calls), driver.calls
    assert driver.calls[0] == driver.calls[2], (driver.calls[0], driver.calls[2])
    assert len(slept) == 2, slept


def test_a_failure_on_the_way_to_the_driver_is_not_washed_into_an_empty_ledger(monkeypatch):
    """反"拿 try/except 把 500 糊成空账"那一格（派工词与 states.py:65-66 同一条纪律）。

    驱动抛出来的错必须原样往外走：`recipient_states` 不许在这条腿上把它折成 `{}`（"真没有
    行"）也不许折成 `None`（"这本账答不上"）—— 那两枚脸各有各的判据，一枚都不许由一次
    TypeError 代签。
    """
    _clean_policy(monkeypatch)
    _pg_world(monkeypatch)

    def connect(*args, **kwargs):
        raise Boom("the leg is broken again")

    monkeypatch.setattr(psycopg, "connect", connect)

    with pytest.raises(Boom):
        state_store.recipient_states("r602")


# --------------------------------------------------- 判据③·乙：按 env 开关的端到端
@pytest.mark.skipif(
    not REAL_PG,
    reason="端到端要真库：设 R602_REAL_PG=1 才跑（常驻门一次真握手都不发）",
)
def test_the_real_pg_leg_answers_with_mapping_rows():
    """真库那一遍：走真签名读 `notification_states`，交回来的必须是 mapping 行。

    这枚是"在册钉全 mock `_conn`"那一族的反面 —— 它一枚桩都不打，直接对那本账发 SELECT。
    跑法（backend 容器里，那枚 venv 带 psycopg）：

        R602_REAL_PG=1 python -m pytest -q tests/test_r602_notification_pg_leg.py

    默认关：本机全量门不许对客户的库发握手（跟进单 R20 那条口径）。
    """
    read_back = state_store.recipient_states("r602-live-probe")

    assert read_back is not None, "真库答上了却交回 None：读腿被折成了「答不上」"
    assert isinstance(read_back, dict), type(read_back)

    with state_store._conn() as conn:
        row = conn.execute("SELECT to_regclass('public.notification_states') AS table_name").fetchone()

    assert isinstance(row, dict), "驱动没收到 row_factory：交回来的还是 tuple %r" % (type(row),)
    assert row["table_name"] is not None, (
        "notification_states 不在这台库上（0016 没跑）—— §160.7 那句「读了也存不进」就是它"
    )
