"""R238 判据①②③：默认不许翻、策略只许有一处、常数不许有第二份。

三件事各自有钉，反证也各自指名：

- 判据①（默认关）由 ``test_no_env_means_no_timeout_no_retry_no_keepalives`` /
  ``test_the_dataclass_defaults_are_the_off_values`` /
  ``test_off_policy_emits_exactly_one_bare_call`` 三枚把住。把 ``ConnectPolicy`` 的任何
  一枚默认从"关"翻成"开"，或者把 ``connect_policy`` 里"只有 attempts>1 才补超时/预算"
  那两条 fallback 提前，至少一枚当场红。
- 判据②（一处策略）由 ``test_connection_py_imports_no_call_site`` 与
  ``test_no_call_site_imports_the_new_policy_yet`` 把住：本节零调用方，且
  ``app/db/connection.py`` 不许 import 任何调用方。
- 判据③（不许第二份时延参数）由 ``test_the_latency_numbers_are_not_a_second_set`` 与
  ``test_this_module_invents_no_extra_latency_names`` 把住。前者用 AST 比对本模块与
  ``app/common/auth.py`` 里那五枚常数的**字面量**，全程不 import auth —— 任何
  ``import app.common.auth`` 都会在 import 期发一次真握手（auth.py:474 的
  ``_c = _raw_conn()``），所以本文件一条真握手都不许发。

本文件不开库、不起服务、不打模型：建连一律注入假 connect。
"""
import ast
import io
import re
import sys
from pathlib import Path

import pytest

from app.db import connection

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_SOURCE = REPO_ROOT / "app" / "common" / "auth.py"

# 五枚名字：本模块与 auth.py 必须逐个相等（判据③的最终关系：这里是未来的家，
# auth 那份是今天的事实源，迁 auth 是下一单）。
R229_PAIRS = {
    "CONNECT_TIMEOUT_SECONDS": "_CONNECT_TIMEOUT_SECONDS",
    "CONNECT_ATTEMPTS": "_CONNECT_ATTEMPTS",
    "RETRY_BACKOFF_BASE_SECONDS": "_RETRY_BACKOFF_BASE_SECONDS",
    "RETRY_BACKOFF_CAP_SECONDS": "_RETRY_BACKOFF_CAP_SECONDS",
    "RETRY_BUDGET_SECONDS": "_RETRY_BUDGET_SECONDS",
}

URL = "postgresql://enterprise_brain@postgres:5432/enterprise_brain"


class Boom(Exception):
    pass


class FakeDriver:
    """假 psycopg：只记账，绝不握手。"""

    def __init__(self, failures=()):
        self.calls = []
        self._failures = list(failures)

    def connect(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._failures:
            raise self._failures.pop(0)
        return f"conn<{len(self.calls)}>"


class Clock:
    """手工推进的时钟：预算这条算式要能复现，就不能用真时间。"""

    def __init__(self, steps=(0.0,)):
        self._steps = list(steps)
        self.now = 0.0

    def __call__(self):
        value = self.now
        if self._steps:
            self.now += self._steps.pop(0)
        return value


def _sleeper():
    bag = []

    def sleep(seconds):
        bag.append(seconds)

    return sleep, bag


def _function_source(source: str, name: str) -> str:
    """切出一枚顶层函数的原文（连带它前面几行，够用即可），给"这一枚没被偷偷改"用。"""
    lines = source.splitlines()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            head = max(0, start - 2)
            return "\n".join(lines[head:node.end_lineno])
    raise AssertionError(f"模块里没有 {name}()")


def _literal_assignments(source: str) -> dict:
    """读一个模块顶层 ``NAME = <数字>`` 的**字面量**，不 import 它。"""
    found = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
            found[target.id] = value.value
    return found


def _connection_source() -> str:
    return io.open(connection.__file__, encoding="utf-8").read()


# ------------------------------------------------------------- 判据①：默认不许翻
def test_no_env_means_no_timeout_no_retry_no_keepalives():
    """反证钉（①·甲）：env 一个都不设时，读数必须逐字节等于"今天"。

    今天的事实是：无超时、不重试、无保活、无预算。把 ``ConnectPolicy`` 的任何一枚默认
    从"关"翻成"开"，这一枚当场红。
    """
    policy = connection.connect_policy({})

    assert policy.connect_timeout is None, "默认不许给建连加超时，那是行为变更"
    assert policy.attempts == 1, "默认不许重试：一条可能已经落盘的语句不能被重放"
    assert policy.budget_seconds is None
    assert policy.keepalives is False
    assert policy.rejected == ()
    assert policy.enabled is False


def test_the_dataclass_defaults_are_the_off_values():
    """反证钉（①·乙）：直接构造的默认值也必须全是关。

    与上一枚分开设防：翻 env 读取里的 fallback 红上一枚，翻 dataclass 的默认红这一枚。
    """
    default = connection.ConnectPolicy()

    assert default.connect_timeout is None
    assert default.attempts == 1
    assert default.keepalives is False
    assert default.enabled is False
    assert connection.connect_kwargs(default, URL) == {}


def test_off_policy_emits_exactly_one_bare_call():
    """反证钉（①·丙）：策略关着时发出去的调用必须与今天完全同形。

    ``connect(url)`` 一个 kwargs 都不许多，一次都不许多，一觉都不许多睡。
    """
    driver = FakeDriver()
    sleep, bag = _sleeper()

    result = connection.connect_with_policy(
        URL, environ={}, connect=driver.connect, sleep=sleep, clock=Clock()
    )

    assert result == "conn<1>"
    assert driver.calls == [((URL,), {})], driver.calls
    assert bag == []


def test_open_connection_is_still_the_untouched_entrypoint(monkeypatch):
    """``open_connection()`` 一个字节都不许被本单改动 —— 它是既有入口，不归本节管。

    判据②说得很死：本单只造边界，不迁调用点。所以已有的那枚入口必须继续裸发
    ``psycopg.connect(settings.url)``，否则就是偷偷迁了 14 条路里的一条。
    """
    driver = FakeDriver()
    monkeypatch.setitem(sys.modules, "psycopg", driver)
    monkeypatch.delenv(connection.ENV_CONNECT_TIMEOUT, raising=False)
    monkeypatch.delenv(connection.ENV_CONNECT_KEEPALIVES, raising=False)
    settings = connection.parse_database_settings(URL)

    connection.open_connection(settings)

    assert driver.calls == [((URL,), {})], driver.calls


def test_open_connection_ignores_the_policy_env_even_when_it_is_on(monkeypatch):
    """把超时 env 拧开，``open_connection`` 依旧不许动。

    与上一枚成对：上一枚防"默认被翻"，这一枚防"已有入口被偷偷接上策略"。
    """
    driver = FakeDriver()
    monkeypatch.setitem(sys.modules, "psycopg", driver)
    monkeypatch.setenv(connection.ENV_CONNECT_TIMEOUT, "3")
    monkeypatch.setenv(connection.ENV_CONNECT_KEEPALIVES, "on")
    settings = connection.parse_database_settings(URL)

    connection.open_connection(settings)

    assert driver.calls == [((URL,), {})], driver.calls
    body = _function_source(_connection_source(), "open_connection")
    assert "ENV_CONNECT" not in body, "open_connection 里不许出现读 env 的分支"
    assert "connect_policy" not in body and "connect_with_policy" not in body


# ----------------------------------------------- 判据①的对立面：拧开了要真的管用
def test_timeout_env_adds_the_kwarg_and_flips_enabled():
    policy = connection.connect_policy({connection.ENV_CONNECT_TIMEOUT: "3"})

    assert policy.enabled is True
    assert policy.connect_timeout == 3
    assert connection.connect_kwargs(policy, URL) == {"connect_timeout": 3}


def test_dsn_carried_timeout_wins_over_the_env():
    """DSN 自己写了超时，策略就不许覆盖：操作者的数比我们的默认大。

    三种写法都得认（URI 查询位、& 续接、空格式 conninfo），口径与 auth.py:306 同一枚
    正则。漏一种就是拿 env 把库上的读数盖掉。
    """
    policy = connection.connect_policy({connection.ENV_CONNECT_TIMEOUT: "5"})

    for url in (
        "postgresql://u@h:5432/db?connect_timeout=1",
        "postgresql://u@h:5432/db?application_name=x&connect_timeout=1",
        "host=h dbname=db connect_timeout=1",
    ):
        assert connection.connect_kwargs(policy, url) == {}, url


def test_keepalive_switch_adds_only_keepalives():
    """保活只加 ``keepalives=1``，idle 交给 libpq/OS —— 本单不给它造第二个数。"""
    policy = connection.connect_policy({connection.ENV_CONNECT_KEEPALIVES: "on"})

    assert policy.keepalives is True
    assert connection.connect_kwargs(policy, URL) == {"keepalives": 1}


@pytest.mark.parametrize("raw", ["ture", "0", "-1", "off", "yes please"])
def test_a_garbage_value_stays_off_and_is_reported(raw):
    """拼错的值不许被读成"开"：记一笔，然后退回今天那个还能工作的状态。

    口径抄 app/rag/pg_store.py:175 的 dual_write_enabled。
    """
    policy = connection.connect_policy({connection.ENV_CONNECT_KEEPALIVES: raw})

    assert policy.keepalives is False
    assert policy.enabled is False
    assert (connection.ENV_CONNECT_KEEPALIVES, raw) in policy.rejected, policy.rejected


def test_a_garbage_timeout_is_not_silently_promoted_to_on():
    policy = connection.connect_policy({connection.ENV_CONNECT_TIMEOUT: "soon"})

    assert policy.connect_timeout is None
    assert policy.rejected == ((connection.ENV_CONNECT_TIMEOUT, "soon"),)
    assert connection.connect_kwargs(policy, URL) == {}


def test_attempts_alone_borrows_r229_numbers_not_new_ones():
    """只写 attempts 时，超时与预算借用 R229 那两枚数，绝不新造第三个数（判据③）。"""
    policy = connection.connect_policy({connection.ENV_CONNECT_ATTEMPTS: "5"})

    assert policy.attempts == 5
    assert policy.connect_timeout == connection.CONNECT_TIMEOUT_SECONDS
    assert policy.budget_seconds == connection.RETRY_BUDGET_SECONDS


# ------------------------------------- 判据②③：重试算式与 R229 同式，且默认零影响
def test_one_blip_is_absorbed_with_exactly_one_reconnect():
    driver = FakeDriver(failures=[Boom("failed to resolve host 'postgres'")])
    sleep, bag = _sleeper()

    result = connection.connect_with_policy(
        URL,
        environ={connection.ENV_CONNECT_ATTEMPTS: "3"},
        connect=driver.connect,
        transient=(Boom,),
        sleep=sleep,
        clock=Clock(),
    )

    assert result == "conn<2>"
    assert len(driver.calls) == 2
    assert bag == [connection.RETRY_BACKOFF_BASE_SECONDS], bag
    assert driver.calls[1] == driver.calls[0], "重试必须发同一个形状"


def test_backoff_is_exponential_and_capped():
    driver = FakeDriver(failures=[Boom(n) for n in "abcde"])
    sleep, bag = _sleeper()

    with pytest.raises(Boom):
        connection.connect_with_policy(
            URL,
            environ={connection.ENV_CONNECT_ATTEMPTS: "5"},
            connect=driver.connect,
            transient=(Boom,),
            sleep=sleep,
            clock=Clock(),
        )

    assert bag == [0.05, 0.1, 0.2, 0.2], bag   # 0.05 翻倍两次就撞在 0.2 的封顶上


def test_the_budget_gives_up_instead_of_burning_more_than_r229_allowed():
    """每发都慢死时不许把预算烧穿：与 auth.py:394 同一条算式。

    预算 3.0s、超时 2s：第一发已经耗掉 1.5s，再退避 0.05s 加一次完整 2s 尝试就是
    3.55s > 3.0s，所以就地放手，一觉都不许多睡。
    """
    driver = FakeDriver(failures=[Boom("slow"), Boom("slower")])
    sleep, bag = _sleeper()

    with pytest.raises(Boom):
        connection.connect_with_policy(
            URL,
            environ={
                connection.ENV_CONNECT_ATTEMPTS: "3",
                connection.ENV_CONNECT_BUDGET: str(connection.RETRY_BUDGET_SECONDS),
            },
            connect=driver.connect,
            transient=(Boom,),
            sleep=sleep,
            clock=Clock(steps=(1.5, 1.5, 1.5, 1.5)),
        )

    assert len(driver.calls) == 1, driver.calls
    assert bag == [], "预算装不下一次完整尝试时，一次都不许睡"


def test_a_non_transient_failure_is_never_retried():
    """``transient=()`` 的意思是"不重试"，不是"什么都重试"。

    ``except ()`` 什么都抓不住，异常照原样往外抛 —— 这也是 env 全关、或驱动形状读不
    出来时的那条退路。
    """
    driver = FakeDriver(failures=[Boom("already written to disk")])
    sleep, bag = _sleeper()

    with pytest.raises(Boom):
        connection.connect_with_policy(
            URL,
            environ={connection.ENV_CONNECT_ATTEMPTS: "3"},
            connect=driver.connect,
            transient=(),
            sleep=sleep,
            clock=Clock(),
        )

    assert len(driver.calls) == 1
    assert bag == []


def test_transient_rule_is_operational_error_only():
    """重试名单与 auth.py:325 同源：只认 OperationalError，拿不到类就返回空元组。"""
    psycopg = pytest.importorskip("psycopg")

    assert connection.transient_connect_errors(psycopg) == (psycopg.OperationalError,)
    assert connection.transient_connect_errors(object()) == ()
    assert connection.transient_connect_errors(psycopg) == connection.transient_connect_errors()


# ------------------------------- 判据③：那五枚数只许有一份，名字也只许有一套
def test_the_latency_numbers_are_not_a_second_set():
    """本模块那五枚数必须与 auth.py 里 R229 钉住的逐个相等（判据③）。

    比的是**字面量**，走 AST 不走 import：import auth 会发真握手。谁单独漂移这一枚就
    红；两枚一起改也红 —— 那正是要的形状：一份策略只有一个数值源，改一次数就得同时
    改两处，直到下一单把 auth 搬进来为止。
    """
    auth_numbers = _literal_assignments(AUTH_SOURCE.read_text(encoding="utf-8"))
    mine = _literal_assignments(_connection_source())

    for here, there in R229_PAIRS.items():
        assert here in mine, f"本模块少了 {here}"
        assert there in auth_numbers, f"auth.py 里的 {there} 不在了，迁移的前提就塌了"
        assert mine[here] == auth_numbers[there], (
            f"{here}={mine[here]} 与 auth 的 {there}={auth_numbers[there]} 不相等"
        )


def test_this_module_invents_no_extra_latency_names():
    """``*_SECONDS`` 这个名字后缀在本模块只许有 R229 那四枚（判据③的字面钉子）。

    口径抄 tests/test_r230_db_ready_selfheal.py:423 对 auth 做的那一枚：它管 auth，
    这一枚管 connection.py。想加一枚 keepalives_idle_seconds，得先过总控。
    """
    names = {name for name in vars(connection) if name.endswith("_SECONDS")}
    expected = {name for name in R229_PAIRS if name.endswith("_SECONDS")}
    assert names == expected, names


# ------------------------------------------------- 判据②：一处策略，且零调用方
def test_connection_py_imports_no_call_site():
    """本节不许 import 任何调用方：依赖必须单向，将来谁迁过来都不成环。"""
    tree = ast.parse(_connection_source())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    call_sites = {
        "app.common.auth", "app.agents.orchestrator", "app.rag.indexing",
        "app.rag.retriever", "app.rag.pg_store", "app.documents.catalog",
        "app.memory.long_term", "app.memory.profile", "app.semantics.registry",
        "app.storage.persistence", "app.storage.pending_approvals",
        "app.common.monitoring", "app.api.v1.chat", "app.api.v1.alerts",
        "app.api.v1.feedback",
    }
    assert not (imported & call_sites), sorted(imported & call_sites)
    assert "app.common.logger" in imported, "日志走本仓既有那枚 logger，不自己配 handler"


def test_no_call_site_imports_the_new_policy_yet():
    """反向也一样：今天 app/** 里除本模块外，一枚调用方都不许已经在用这一节。

    本单定位就是"只造边界与棘轮，一个调用点都不迁"。这一枚红了说明有人提前迁了，
    那是另一单的活，得先对判据。
    """
    new_names = (
        "connect_policy", "connect_with_policy", "open_connection_with_policy",
        "connect_kwargs", "ConnectPolicy", "transient_connect_errors",
    )
    offenders = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "app/db/connection.py":
            continue
        source = path.read_text(encoding="utf-8")
        hit = [name for name in new_names if re.search(r"\b" + name + r"\b", source)]
        if hit:
            offenders.append(f"{rel}: {hit}")

    assert offenders == [], "本单不迁调用点：" + "; ".join(offenders)