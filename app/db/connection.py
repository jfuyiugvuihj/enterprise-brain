"""Offline-safe database configuration and connection boundary.

This module validates configuration and exposes a connection factory contract. It does
not connect or create schema during import; deployment code must call that explicitly.

R238 adds one more thing here: the single home for the connect latency policy (timeout,
bounded retry, backoff, budget). It is deliberately *not* imported by any call site in
this ticket. The claim that this module is "the production boundary" is still only a
goal, not a fact: 14 sites in ``app/**`` still call ``psycopg.connect`` straight past
it, and ``tests/test_r238_bare_connect_ratchet.py`` pins that reading so it can only go
down, never up.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.common.logger import logger


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    scheme: str
    host: str
    port: int | None
    database: str
    sslmode: str | None = None

    @property
    def is_postgresql(self) -> bool:
        return self.scheme in {"postgresql", "postgres"}


def parse_database_settings(url: str) -> DatabaseSettings:
    value = (url or "").strip()
    if not value:
        raise ValueError("DATABASE_URL is required")
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"postgresql", "postgres"}:
        raise ValueError("only PostgreSQL URLs are supported by the production boundary")
    if not parsed.hostname:
        raise ValueError("database host is required")
    if not parsed.path or parsed.path == "/":
        raise ValueError("database name is required")
    return DatabaseSettings(
        url=value,
        scheme=scheme,
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/"),
        sslmode=dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair).get("sslmode"),
    )


def open_connection(settings: DatabaseSettings):
    """Create a psycopg connection only when an integration caller explicitly asks."""
    import psycopg

    return psycopg.connect(settings.url)


# ---------------------------------------------------------------------------
# R238 —— 建连时延策略的唯一之家。R238 自己一个调用点都不迁；第一枚迁入者是 R299。
#
# 这一节今天的读者 = 测试 + 一枚生产调用方（app/notifications/states.py:30）。它把"超时 / 有界重试 / 退避 / 预算"收成一份
# 可复用入口，为的是让下一批迁移不必各自在这堵墙前面盖小房子（R229 已经在鉴权那一侧
# 盖了一间，R230 又在拒绝之前加了一枚 15s 节流重探，两间都还着，墙本身还在）。判据②要
# 的就是"一处策略"；"一处"能不能守住，靠的是 tests/test_r238_bare_connect_ratchet.py
# 那枚棘轮，它挡住第 15 枚裸 connect 长出来。
# ---------------------------------------------------------------------------

#: 四枚开关，**全部默认关**。
#:
#: 不设这些 env 时 :func:`connect_policy` 交回的读数就是"无超时、不重试、无保活"，
#: 也就是 2026-09-25 今天的事实；:func:`open_connection` 与 :func:`connect_with_policy`
#: 在这套默认下发出的是同一个调用。判据①钉的是这条：把默认从"关"翻成"开"必须让
#: tests/test_r238_connect_boundary_policy.py 当场红。理由是账面上的——一次 DNS 抖动能
#: 同时掀翻边界外那 14 条路，而其中若干条今天根本没有超时兜着，所以"加超时"本身就是一
#: 次行为变更，得由操作者逐条签字，不许本单替他签。
ENV_CONNECT_TIMEOUT = "DB_CONNECT_TIMEOUT_SECONDS"
ENV_CONNECT_KEEPALIVES = "DB_CONNECT_KEEPALIVES"
ENV_CONNECT_ATTEMPTS = "DB_CONNECT_ATTEMPTS"
ENV_CONNECT_BUDGET = "DB_CONNECT_RETRY_BUDGET_SECONDS"

#: 这五个数**不是本单定的**：它们与 app/common/auth.py:39-43 里 R229 已经钉住的
#: ``_CONNECT_TIMEOUT_SECONDS / _CONNECT_ATTEMPTS / _RETRY_BACKOFF_BASE_SECONDS /
#: _RETRY_BACKOFF_CAP_SECONDS / _RETRY_BUDGET_SECONDS`` 逐个相等，等式由
#: tests/test_r238_connect_boundary_policy.py 用 AST 比字面量把住（不走 import：任何
#: ``import app.common.auth`` 都会向宿主发一次真握手）。
#:
#: 两处的最终关系，写死在这里：本模块是这五个数的**未来唯一之家**，auth 那份是**今天的
#: 事实源**；把 auth 搬进来是下一单的活，本单不动 app/common/auth.py 一个字节。在它搬
#: 之前，两枚名字必须同红同绿、不许各自漂移，更不许出现第三份互不相同的重试预算（判据③）。
CONNECT_TIMEOUT_SECONDS = 2
CONNECT_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 0.05
RETRY_BACKOFF_CAP_SECONDS = 0.2
RETRY_BUDGET_SECONDS = 3.0

#: 保活只开这一枚开关，且**不给 keepalives_idle 造默认数**：那是第二套时延参数，判据③
#: 不许。要调 idle 请操作者自己写进 DSN，本单连那个键都不开。
KEEPALIVE_ON_VALUES = frozenset({"1", "on", "true", "yes"})

#: 与 app/common/auth.py:306 同一个式子：DSN 里已经写了超时，就以库上的读数为准，策略
#: 不覆盖操作者。tests/conftest.py:41 把测试 DSN 钉成 127.0.0.1:1?connect_timeout=1，
#: 靠的正是这条不被覆盖。
DSN_CONNECT_TIMEOUT = re.compile(r"(?:[?&;]|\s)connect_timeout\s*=")


@dataclass(frozen=True)
class ConnectPolicy:
    """一次建连的时延读数。frozen：交出去之后不许被人改走。

    默认构造出来的就是"今天"：``connect_timeout=None``（不设上界，归 OS 解析器说了算）、
    ``attempts=1``（失败即抛，绝不重放）、``keepalives=False``、没有预算。
    """

    connect_timeout: int | None = None
    attempts: int = 1
    budget_seconds: float | None = None
    keepalives: bool = False
    rejected: tuple = ()

    @property
    def enabled(self) -> bool:
        """有没有人真的把某枚开关拧开过。False 时一切走的就是今天那条代码路径。"""
        return self.connect_timeout is not None or self.attempts > 1 or self.keepalives


def _setting(environ, name: str) -> str:
    source = os.environ if environ is None else environ
    return str(source.get(name) or "").strip()


def _num_setting(environ, name: str, rejected: list, cast, ok):
    """读一枚数值开关。读不成、或落在 ok 之外，一律当作**没设**（也就是关）。

    与 app/rag/pg_store.py:175 的 dual_write_enabled 同一个口径：拼错的值是等着上线的
    typo，它必须被记一笔，然后退回那个"今天还能工作"的状态 —— 危险的方向是把 typo
    读成"开"。
    """
    raw = _setting(environ, name)
    if not raw:
        return None
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        rejected.append((name, raw))
        return None
    if not ok(value):
        rejected.append((name, raw))
        return None
    return value


def connect_policy(environ=None) -> ConnectPolicy:
    """把四枚 env 读成一份策略；**一个都不设就是今天**。"""
    rejected: list = []
    timeout = _num_setting(environ, ENV_CONNECT_TIMEOUT, rejected, int, lambda v: v >= 1)
    attempts = _num_setting(environ, ENV_CONNECT_ATTEMPTS, rejected, int, lambda v: v >= 1)
    budget = _num_setting(environ, ENV_CONNECT_BUDGET, rejected, float, lambda v: v > 0)
    raw_keepalives = _setting(environ, ENV_CONNECT_KEEPALIVES).lower()
    keepalives = raw_keepalives in KEEPALIVE_ON_VALUES
    if raw_keepalives and not keepalives:
        rejected.append((ENV_CONNECT_KEEPALIVES, raw_keepalives))
    if (attempts or 1) > 1:
        # 只写 attempts 不写 timeout，等于拿一条可能挂死的握手再挂三次，比不重试更坏。
        # 补齐用的还是 R229 那两个数，不新造第三个数。
        if timeout is None:
            timeout = CONNECT_TIMEOUT_SECONDS
        if budget is None:
            budget = RETRY_BUDGET_SECONDS
    for name, raw in rejected:
        logger.warning(f"[DB] {name}={raw!r} 读不出来，这一项保持关闭（今天的默认）")
    return ConnectPolicy(
        connect_timeout=timeout,
        attempts=attempts or 1,
        budget_seconds=budget,
        keepalives=keepalives,
        rejected=tuple(rejected),
    )


def connect_kwargs(policy: ConnectPolicy, url: str = "") -> dict:
    """把策略翻成递给 ``psycopg.connect`` 的 kwargs。**策略关着就返回空 dict**。

    空 dict 是判据①的落点：``connect(url)`` 与 ``connect(url, **{})`` 逐字节等价，
    所以不设 env 时这一节对真实调用零影响。
    """
    kwargs: dict = {}
    if policy.connect_timeout is not None and not DSN_CONNECT_TIMEOUT.search(url or ""):
        kwargs["connect_timeout"] = policy.connect_timeout
    if policy.keepalives:
        kwargs["keepalives"] = 1
    return kwargs


def transient_connect_errors(driver=None) -> tuple:
    """只有 ``OperationalError`` 够格重试；连这枚类都拿不到时一律不重试。

    规则与 app/common/auth.py:325 同源，本单不重述理由（理由在那枚函数的 docstring 里：
    宁可少吸一次抖动，也不许把一条可能已经落盘的写语句重放）。返回空元组的意思是
    "不重试"，不是"什么都重试" —— ``except ()`` 什么都抓不住，异常照原样往外抛。
    """
    if driver is None:
        import psycopg

        driver = psycopg
    operational = getattr(driver, "OperationalError", None)
    if isinstance(operational, type) and issubclass(operational, BaseException):
        return (operational,)
    return ()


def connect_with_policy(url: str, *, policy=None, environ=None, connect=None,
                        transient=None, sleep=None, clock=None):
    """按 :func:`connect_policy` 的读数开一条连接：超时 + 有界重试 + 指数退避 + 预算。

    env 一个都不设时走的是 ``connect(url)`` 一发：不睡、不重试、不加超时，和
    ``open_connection()`` 今天做的事完全相同。判据②：本节今天只有一枚调用方（R299 的 notifications 那一族），
    第二枚起要先对判据——账记在 tests/test_r238_connect_boundary_policy.py 的语义账上，不是行号账。

    ``connect`` / ``transient`` / ``sleep`` / ``clock`` 是给测试留的缝（与本仓
    ``connection_factory=`` 同一族做法）。注入假 connect 而不给 transient 时重试自动
    关掉，免得拿一枚不存在的异常类去 except。
    """
    plan = connect_policy(environ) if policy is None else policy
    if connect is None:
        import psycopg

        connect = psycopg.connect
        if transient is None:
            transient = transient_connect_errors(psycopg)
    if transient is None:
        transient = ()
    kwargs = connect_kwargs(plan, url)
    monotonic = time.monotonic if clock is None else clock
    sleeper = time.sleep if sleep is None else sleep
    attempts = max(1, plan.attempts)
    budget = RETRY_BUDGET_SECONDS if plan.budget_seconds is None else plan.budget_seconds
    timeout = plan.connect_timeout or 0
    started = monotonic()
    for attempt in range(1, attempts + 1):
        try:
            return connect(url, **kwargs)
        except transient as exc:
            elapsed = monotonic() - started
            backoff = min(
                RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                RETRY_BACKOFF_CAP_SECONDS,
            )
            # "剩下的预算装不下一整次尝试就放手"，而不是"还剩一秒就再试"：与
            # app/common/auth.py:394 同一条式子，两枚名字必须一起改才跑得动。
            if attempt >= attempts or elapsed + backoff + timeout > budget:
                if attempts > 1:
                    logger.warning(
                        f"[DB] 建连失败，不再重试（第 {attempt}/{attempts} 次，已耗 "
                        f"{elapsed:.3f}s，预算 {budget}s）: {type(exc).__name__}: {exc}"
                    )
                raise
            logger.warning(
                f"[DB] 建连失败，{backoff:g}s 后重试（第 {attempt}/{attempts} 次）: "
                f"{type(exc).__name__}: {exc}"
            )
            sleeper(backoff)


def open_connection_with_policy(settings: DatabaseSettings, **kwargs):
    """``open_connection()`` 的策略版：留给后续调用点迁入时用的同形入口。

    env 全关时它发出的调用与 ``open_connection(settings)`` 逐字节相同；本单不改
    ``open_connection`` 一个字节，也不把任何调用方指到这里。
    """
    return connect_with_policy(settings.url, **kwargs)
