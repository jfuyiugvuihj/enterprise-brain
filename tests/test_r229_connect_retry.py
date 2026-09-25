"""R229 反证钉：鉴权建连的"短暂解析失败 -> 有界重试"（乙案）。

病：`/queue/status` 间歇 500，栈停在
`psycopg.OperationalError: failed to resolve host 'postgres' [Errno -3]`
（`app/main.py:277 dispatch` -> `app/common/auth.py get_user` -> `_raw_conn`）。
根因是每个鉴权请求新建一条 psycopg 连接，既不等位也不重试，DNS 抖一下就红。

这一文件的每一枚钉都只碰假 conn 与 monkeypatch：一条真连接也不许发出去，一次真 PG
也不许连（`tests/conftest.py:41-53` 已把 DATABASE_URL 钉成 `127.0.0.1:1` +
`connect_timeout=1`，本文件再加一枚哨兵，真驱动一旦想 connect 就当场炸）。
"""
import ast
import builtins
import io
import sys
import types

import pytest

from app.common import auth

# 真实驱动只用来取异常类形状（psycopg.OperationalError 就是现网那枚），不拿它建连。
psycopg = pytest.importorskip("psycopg")

BLIP = psycopg.OperationalError(
    "failed to resolve host 'postgres': [Errno -3] Temporary failure in name resolution"
)


class _Rows:
    """`dict_row` 口径的假结果：行就是 dict，`get_user` 那句 `dict(row)` 才成立。"""

    USER = {"username": "u1", "role": "staff", "department": "ops"}

    def __init__(self, row=USER):
        self._row = row
        self.rowcount = 0 if row is None else 1

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class _RecordingConn:
    """假连接：记下发过的语句与 commit 次数，永远不碰网络。"""

    def __init__(self, fail_on_execute=None):
        self.statements = []
        self.commits = 0
        self.closed = False
        self._fail_on_execute = fail_on_execute

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if self._fail_on_execute is not None:
            raise self._fail_on_execute
        text = sql.lower()
        if "select id from users" in text:
            return _Rows({"id": 7})
        if "select username, role, department from users" in text:
            return _Rows(_Rows.USER)
        return _Rows(None)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False


def _flaky_conn(first_error=None, attempts_to_fail=1, clock=None, conns=None):
    """造假 `_raw_conn`：默认只在第 `attempts_to_fail` 次调用上抛一次连接错误。

    `attempts_to_fail=0` = 每次都抛；`clock` 给了就在抛之前把单调钟推走，用来
    模拟"这一发尝试真的耗掉了一个 connect_timeout"。
    """
    calls = []

    def fake_raw_conn():
        calls.append(1)
        should_fail = attempts_to_fail == 0 or len(calls) == attempts_to_fail
        if should_fail:
            if clock is not None:
                clock[0] += auth._CONNECT_TIMEOUT_SECONDS
            raise first_error or BLIP
        conn = _RecordingConn()
        if conns is not None:
            conns.append(conn)
        return conn

    return fake_raw_conn, calls


@pytest.fixture
def no_sleep(monkeypatch):
    """把退避睡人抓成读数：既证明重试真的等了，也证明测试一秒都不真等。"""
    slept = []
    monkeypatch.setattr(auth.time, "sleep", lambda seconds: slept.append(seconds))
    return slept


@pytest.fixture
def pg_branch(monkeypatch):
    """把 auth 推到"走 PostgreSQL 分支"的形状上，且不碰真库。"""
    monkeypatch.setattr(auth, "_db_ready", True)
    monkeypatch.setattr(auth, "_PG_URL", "postgresql://u@postgres:5432/eb")
    assert auth._using_memory_store() is False
    return auth


@pytest.fixture(autouse=True)
def no_real_driver_connect(monkeypatch):
    """哨兵：本文件任何用例都不许经真驱动建连（假 conn 一律走 monkeypatch._raw_conn）。"""

    def refuse(*args, **kwargs):
        raise AssertionError(
            "tests/test_r229_connect_retry.py 试图开一条真 PostgreSQL 连接；"
            "R229 全程只用假 conn，按 R20 的口径判失败"
        )

    monkeypatch.setattr(psycopg, "connect", refuse, raising=False)
    yield


# ------------------------------------------------------------------ 判据 1 的读数
def test_call_site_counts_are_pinned():
    """`_raw_conn` 直接调用点 2 枚、`_get_conn` 调用点 7 枚 —— 选路的依据钉死在这里。

    修前：`_raw_conn()` = import 探针 + `_get_conn()`；修后仍是 2 枚，只是第二枚挪进了
    `_connect_for_request`（它只做一件事：调 `_raw_conn()`）。`_get_conn()` 那 7 枚调用者
    = verify_password / list_users / create_user / get_user / upsert_sso_user /
    delete_user / change_password，即"每个鉴权动作一条新连接"。数不一致就说明代码变了
    形而注释还在撒谎，两者都算红。
    """
    source = io.open(auth.__file__, encoding="utf-8").read()
    tree = ast.parse(source)
    raw_calls = get_conn_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None)
            if name == "_raw_conn":
                raw_calls += 1
            elif name == "_get_conn":
                get_conn_calls += 1
    assert raw_calls == 2, f"_raw_conn 直接调用点应为 2 枚，实测 {raw_calls}"
    assert get_conn_calls == 7, f"_get_conn 调用点应为 7 枚，实测 {get_conn_calls}"


# -------------------------------------------------------------- 判据 2 乙案主钉
def test_one_blip_is_absorbed_with_exactly_one_reconnect(pg_branch, no_sleep, monkeypatch):
    """反证钉（主）：注入一次"只失败一次的解析错误"，重试后必须成功，且只重连一次。

    摘掉修复（`_get_conn` 退回直接 `_raw_conn()`）时红在这一格：第一发就抛给调用方，
    用户拿到的是 500，读数也不可能是"建连 2 次 + 退避 1 次"。
    """
    fake, calls = _flaky_conn()
    monkeypatch.setattr(auth, "_raw_conn", fake)

    user = auth.get_user("u1")

    assert user == _Rows.USER
    assert len(calls) == 2, f"抖动应只多花一次重连，实测建连 {len(calls)} 次"
    assert no_sleep == [auth._RETRY_BACKOFF_BASE_SECONDS], no_sleep


def test_repeated_failure_stops_at_the_attempt_cap(pg_branch, no_sleep, monkeypatch):
    """一直失败也只能试 `_CONNECT_ATTEMPTS` 次，且原错误类型原样抛回（401/500 形状不变）。"""
    fake, calls = _flaky_conn(attempts_to_fail=0)
    monkeypatch.setattr(auth, "_raw_conn", fake)

    with pytest.raises(psycopg.OperationalError):
        auth.get_user("u1")

    assert len(calls) == auth._CONNECT_ATTEMPTS, len(calls)
    assert no_sleep == [0.05, 0.1], no_sleep
    assert sum(no_sleep) <= auth._RETRY_BACKOFF_CAP_SECONDS * 2


def test_slow_attempts_give_up_instead_of_burning_the_budget(pg_branch, no_sleep, monkeypatch):
    """每发都慢到超时时只吃一次尝试：剩下的预算装不下"退避 + 完整一次"就当场放手。

    这条钉的是最坏情况时延。这条路跑在事件循环上（`app/main.py:246` 的 async dispatch
    直调同步 `get_user`），多等不是等自己这一发，是等全场。
    """
    clock = [0.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    fake, calls = _flaky_conn(attempts_to_fail=0, clock=clock)
    monkeypatch.setattr(auth, "_raw_conn", fake)

    with pytest.raises(psycopg.OperationalError):
        auth.get_user("u1")

    assert len(calls) == 1, f"慢死场景不该再掏第二次尝试，实测 {len(calls)}"
    assert no_sleep == [], no_sleep


def test_failure_after_connect_is_never_retried_or_replayed(pg_branch, no_sleep, monkeypatch):
    """判据 2 的硬界：重试只许限于"未建立连接之前"，不许重放已经发出去的语句。

    连接建好之后才失败（`execute` 抛 OperationalError），建连次数必须还是 1、那条语句
    必须只发一遍。摘掉修复这格也过，所以它是护栏，不是反证钉。
    """
    conns = []

    def fake_raw_conn():
        conn = _RecordingConn(fail_on_execute=psycopg.OperationalError("server closed the connection"))
        conns.append(conn)
        return conn

    monkeypatch.setattr(auth, "_raw_conn", fake_raw_conn)

    with pytest.raises(psycopg.OperationalError):
        auth.get_user("u1")

    assert len(conns) == 1, len(conns)
    assert len(conns[0].statements) == 1, conns[0].statements
    assert no_sleep == [], no_sleep


def test_write_path_keeps_one_commit_and_one_statement_set(pg_branch, no_sleep, monkeypatch):
    """`upsert_sso_user` 的事务边界一字不改：抖动前后都只一遍语句、一次 commit。

    今天（修前）这格也红，但红法不同：`upsert_sso_user` 自己 `except Exception` 兜住，
    返回 (False, "SSO 用户同步失败: ...") —— 一次 DNS 抖动就把一次 SSO 同步整笔丢掉。
    修后抖动被吸收，语句仍是 SELECT + UPDATE 两遍不多、commit 恰好一次。
    """
    conns = []
    fake, calls = _flaky_conn(conns=conns)
    monkeypatch.setattr(auth, "_raw_conn", fake)

    ok, message = auth.upsert_sso_user("u1", role="admin", department="ops")

    assert ok is True, message
    assert message == "SSO 用户已同步"
    assert len(calls) == 2, calls
    assert len(conns) == 1, "抖动只该多花一次建连，不该多花一条连接去写"
    assert len(conns[0].statements) == 2, conns[0].statements
    assert conns[0].commits == 1, conns[0].commits


def test_non_transient_error_is_not_retried(pg_branch, no_sleep, monkeypatch):
    """不在名单里的错（语法/权限类）一次都不许多试，形状原样抛给调用方。"""
    fake, calls = _flaky_conn(first_error=psycopg.ProgrammingError("syntax error"))
    monkeypatch.setattr(auth, "_raw_conn", fake)

    with pytest.raises(psycopg.ProgrammingError):
        auth.get_user("u1")

    assert len(calls) == 1, len(calls)
    assert no_sleep == [], no_sleep


def test_unreadable_driver_shape_disables_retry_silently(pg_branch, no_sleep, monkeypatch):
    """`auth.psycopg` 被换成 `object()` 时（tests/test_auth_database.py:90 的口径）必须安静退回今天"失败即抛"。

    拿不到异常类就不该拿它做 `except` —— 这里要的是"不重试"，不是"什么都不catch 而炸在
    except 子句上"。
    """
    calls = []

    def fake_raw_conn():
        calls.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(auth, "psycopg", object())
    monkeypatch.setattr(auth, "_raw_conn", fake_raw_conn)

    with pytest.raises(RuntimeError):
        auth._connect_for_request("user store access")

    assert len(calls) == 1, len(calls)
    assert no_sleep == [], no_sleep


def test_memory_store_branch_still_opens_nothing(monkeypatch):
    """内存分支（无驱动）一个字节都不许被本单改动：建连次数恒为 0。"""
    calls = []
    monkeypatch.setattr(auth, "psycopg", None)
    monkeypatch.setattr(auth, "_raw_conn", lambda: calls.append(1))
    monkeypatch.setattr(auth, "_db_ready", True)

    assert auth._using_memory_store() is True
    assert isinstance(auth._get_conn(), auth._FakeConn)
    assert calls == []


# ------------------------------------------------------------------ connect_timeout
def _fake_driver(seen):
    def connect(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _RecordingConn()

    module = types.ModuleType("psycopg")
    module.connect = connect
    module.OperationalError = psycopg.OperationalError
    module.rows = types.SimpleNamespace(dict_row=object())
    return module


def test_connect_timeout_is_added_when_dsn_has_none(monkeypatch):
    """判据 2 的另一半：没写超时的 DSN 必须被补上 `connect_timeout`。

    今天这枚 connect 一个超时都没有，解析卡住时归 OS 解析器说了算。摘掉修复这格必红
    （kwargs 里根本不会有 `connect_timeout`）。
    """
    seen = {}
    monkeypatch.setattr(auth, "psycopg", _fake_driver(seen))
    monkeypatch.setattr(auth, "_PG_URL", "postgresql://u@postgres:5432/eb")

    auth._raw_conn()

    assert seen["connect_timeout"] == auth._CONNECT_TIMEOUT_SECONDS, seen
    assert seen["row_factory"] is not None


def test_connect_timeout_from_dsn_is_not_overridden(monkeypatch):
    """DSN 自带超时时以 DSN 为准：conftest 那枚 `connect_timeout=1` 不许被本单改成 2s。"""
    seen = {}
    monkeypatch.setattr(auth, "psycopg", _fake_driver(seen))
    monkeypatch.setattr(
        auth, "_PG_URL", "postgresql://u@postgres:5432/eb?connect_timeout=1&keepalives=1"
    )

    auth._raw_conn()

    assert "connect_timeout" not in seen, seen


def test_pinned_test_database_url_keeps_its_own_timeout():
    """本单跑起来时确实走在"DSN 已带超时"的分支上（tests/conftest.py 的口径未被顶掉）。"""
    assert "connect_timeout=1" in auth._PG_URL, auth._PG_URL
    assert auth._connect_kwargs() == {}


# ---------------------------------------------------------------- 判据 4 的 import 门
def _module_level_calls(tree):
    """模块体里、任何函数/类定义之外的调用节点。"""
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                found.append(sub)
    return found


def test_import_period_opens_no_pool_and_no_retry_hook():
    """反证钉（import 期零建连·静态半边）：模块级不许出现任何 connect，也不许有池。

    甲案的门禁（`open=True` 式的 import 期开池）与乙案的门禁（不许把重试挂到 import
    探针上）合成这一条：模块级那枚探针只许调既有的 `_raw_conn()`。
    """
    source = io.open(auth.__file__, encoding="utf-8").read()
    tree = ast.parse(source)

    assert "ConnectionPool" not in source, "本单选乙案，不许在鉴权文件里开第二枚池"
    assert "open=True" not in source, "import 期开池是本案明令禁止的写法"

    calls = _module_level_calls(tree)
    connects = [c for c in calls if getattr(c.func, "attr", "") == "connect"]
    assert not connects, "模块级不许出现任何 connect 调用"

    retried_probe = [c for c in calls if getattr(c.func, "id", "") == "_connect_for_request"]
    assert not retried_probe, "import 期探针不许走重试（启动时没有人在等答复）"

    probes = [c for c in calls if getattr(c.func, "id", "") == "_raw_conn"]
    assert len(probes) == 1, f"模块级探针应恰为 1 枚 _raw_conn()，实测 {len(probes)}"


def test_importing_auth_makes_exactly_the_preexisting_probe_connection(monkeypatch):
    """反证钉（import 期零建连·运行时半边）：换一枚假驱动重新 import，建连恰 1 次、退避 0 次。

    修前修后这个读数都是 1 —— 本单没有把任何新的 import 期建连引进来，也没让探针吃
    重试（吃了就是 3 次）。假驱动把 connect 直接抛成解析失败，所以走的正是"PG 不在线"
    那条 except 分支，一次真 socket 也不会开。
    """
    connects = []
    slept = []

    class _ProbeError(Exception):
        pass

    module = types.ModuleType("psycopg")
    module.OperationalError = _ProbeError
    module.errors = types.SimpleNamespace(UniqueViolation=_ProbeError)

    def connect(*args, **kwargs):
        connects.append(kwargs)
        raise _ProbeError("failed to resolve host 'postgres'")

    module.connect = connect
    module.rows = types.SimpleNamespace(dict_row=object())
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setitem(sys.modules, "psycopg", module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_module)
    monkeypatch.setattr(auth.time, "sleep", lambda seconds: slept.append(seconds))

    # 这里刻意不用 importlib.reload / import_module：那两枚都会把重新执行出来的模块
    # 挂回 sys.modules 与父包的属性上，等于把一枚"_db_ready=False、驱动是假的"的
    # auth 留给后面所有测试文件（踩过，红在 tests/test_auth.py 与
    # test_auth_stable_codes.py，且红得很像产品缺陷）。把同一份源码 exec 进一枚临时
    # namespace，读数是同格的，进程里那枚真 auth 一个字都不动。
    namespace = {"__name__": "r229_import_probe", "__file__": auth.__file__, "__builtins__": builtins}
    exec(compile(io.open(auth.__file__, encoding="utf-8").read(), auth.__file__, "exec"), namespace)

    assert len(connects) == 1, f"import 期建连次数应恰为探针那一枚，实测 {len(connects)}"
    assert slept == [], "import 期一次退避都不许睡"
    assert namespace["_db_ready"] is False
    assert namespace["psycopg"] is module


def test_the_import_probe_leaves_the_real_module_alone():
    """上一枚 exec 不许在进程里留下第二枚 auth：`sys.modules` 与父包都还得指着原件。

    这条是被自己的坑逼出来的：exec 版本红不了，但换成 reload 版本就会红在这里，
    而不是让后面的鉴权件莫名其妙地红。
    """
    import app.common as app_common

    assert sys.modules["app.common.auth"] is auth
    assert app_common.auth is auth
    assert auth._PG_URL.startswith("postgresql://enterprise_brain_pytest@127.0.0.1:1/")
