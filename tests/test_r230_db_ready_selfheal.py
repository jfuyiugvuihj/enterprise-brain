"""R230 反证钉：生产鉴权的 `_db_ready` 死锁——启动探针抖一下 = 401 到重启为止。

病（在本树 e1511cb 上自己复现的通路，不是抄来的结论；行号按基点 e1511cb，本单之后会挪）：
`_db_ready` 只有两处置真——import 期探针（`:376`）与 `_get_conn()`（`:392`）。而 7 枚
鉴权函数**先**问 `_memory_store_denied()`（`:181`），生产 + 内存表时它记一条 ERROR 就
`return True`，调用方当场 default-deny，永远走不到 `_get_conn()`。
于是"容器启动那一刻 PG 还在恢复"= `_db_ready` 恒 False = 全公司登不进来，直到有人重启。

比交回单说的还要死一层（`test_the_runtime_flip_inside_get_conn_is_unreachable`）：
`_get_conn()` 那枚置真长在 `if not _db_ready` 里，而要走到那一行必须先过
`if _using_memory_store(): return _FakeConn()`，而后者恰在 `_db_ready` 为假时为真
⇒ 那一格**恒不可达**。所以修前全仓唯一能让它翻真的通路是 import 探针那一枚，运行期
一次重探都没有——生产被拒绝挡住，开发被 `_FakeConn` 挡住。

本文件钉两件事：
1. 拒绝之前必须先有一次**有界**重探的机会（判据 1、2、4）；
2. 重探失败时对外可见的结果与修前**逐字节相同**（判据 3：default-deny 一字不放宽，
   内存表永远不是一条放行的路）。

一条真连接都不许发出去：`tests/conftest.py:41-53` 已把 DATABASE_URL 钉成
`127.0.0.1:1` + `connect_timeout=1`，本文件再加一枚哨兵，真驱动一旦想 connect 就当场炸。
"""
import builtins
import inspect
import io
import sys
import time
import types
from types import SimpleNamespace

import bcrypt
import pytest

from app.common import auth

# 真实驱动只用来取异常类形状（psycopg.OperationalError 就是现网那枚），不拿它建连。
psycopg = pytest.importorskip("psycopg")

BLIP = psycopg.OperationalError(
    "failed to resolve host 'postgres': [Errno -3] Temporary failure in name resolution"
)

ADMIN = "admin"
ADMIN_PASSWORD = "admin123"
NEW_PASSWORD = "brand-new-1"

# 修前逐格读数：这些就是 default-deny 今天对用户吐的东西（判据 3 一个字都不许改它们，
# 本单只改"什么时候才允许走到它们面前"）。
DENIED_NOW = {
    "verify_password": False,
    "list_users": [],
    "get_user": None,
    "create_user": (False, "production_user_store_unavailable"),
    "upsert_sso_user": (False, "production_user_store_unavailable"),
    "delete_user": False,
    "change_password": (False, "原密码错误"),
}

REFUSAL_ERROR = (
    "[Auth] production user store is not durable; refused user lookup "
    "(set DATABASE_URL and run migrations)"
)


class _Result:
    """`dict_row` 口径的假结果：行就是 dict，`get_user` 那句 `dict(row)` 才成立。"""

    def __init__(self, row=None, rows=(), rowcount=0):
        self._row = row
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

class _FakeUsers:
    """假 users 表：只认 `app/common/auth.py` 真会发的那几句 SQL，其余当场炸。

    语句 / commit / close 全程记账，所以"重探有没有偷偷做 DDL、有没有漏关连接"是
    读数，不是推测。
    """

    def __init__(self, rows=None):
        if rows is None:
            rows = [
                {
                    "id": 1,
                    "username": ADMIN,
                    "password_hash": bcrypt.hashpw(
                        ADMIN_PASSWORD.encode(), bcrypt.gensalt()
                    ).decode(),
                    "role": "admin",
                    "department": "ops",
                    "created_at": "now",
                }
            ]
        self.rows = rows
        self.statements = []
        self.commits = 0
        self.closes = 0

    def _by_name(self, username):
        return next((row for row in self.rows if row["username"] == username), None)

    def execute(self, sql, params=None):
        text = " ".join(sql.lower().split())
        params = tuple(params or ())
        self.statements.append(text)
        if text.startswith("select to_regclass"):
            return _Result(row={"table_name": "users"})
        if text.startswith("select count(*) as c from users"):
            return _Result(row={"c": len(self.rows)})
        if text.startswith("select password_hash from users where username"):
            hit = self._by_name(params[0])
            return _Result(row={"password_hash": hit["password_hash"]} if hit else None)
        if text.startswith("select username, role, department from users where username"):
            hit = self._by_name(params[0])
            if not hit:
                return _Result()
            return _Result(row={key: hit[key] for key in ("username", "role", "department")})
        if text.startswith("select id, username, role, department, created_at from users"):
            return _Result(rows=list(self.rows), rowcount=len(self.rows))
        if text.startswith("select id from users where username"):
            hit = self._by_name(params[0])
            return _Result(row={"id": hit["id"]} if hit else None)
        if text.startswith("insert into users"):
            username, password_hash, role, department = params
            self.rows.append(
                {
                    "id": max(row["id"] for row in self.rows) + 1,
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                    "department": department or "",
                    "created_at": "now",
                }
            )
            return _Result()
        if text.startswith("update users set role"):
            role, department, username = params
            hit = self._by_name(username)
            if hit:
                hit["role"], hit["department"] = role, department
            return _Result()
        if text.startswith("update users set password_hash"):
            password_hash, username = params
            hit = self._by_name(username)
            if hit:
                hit["password_hash"] = password_hash
            return _Result()
        if text.startswith("delete from users where id"):
            keep = [row for row in self.rows if row["id"] != params[0]]
            removed = len(self.rows) - len(keep)
            self.rows = keep
            return _Result(rowcount=removed)
        raise AssertionError(f"未预期的 SQL: {sql}")

    def commit(self):
        self.commits += 1

    def close(self):
        self.closes += 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        # 真 psycopg 的 `with conn:` 只管提交/回滚，关连接是调用方的事，这里同形。
        return False


class _Recorder:
    """假 logger：把"对外可见的日志"变成可比对的元组列表。"""

    def __init__(self):
        self.records = []

    def _emit(self, level):
        def send(message, *args):
            self.records.append((level, str(message % args if args else message)))

        return send

    def __getattr__(self, level):
        if level.startswith("_"):
            raise AttributeError(level)
        return self._emit(level.upper())

    def errors(self):
        return [message for level, message in self.records if level == "ERROR"]


def _flaky_conn(table, fail_times=0, real_sleep=None):
    """造假 `_raw_conn`：前 `fail_times` 发抛连接错误，之后每发都回到同一枚假表。

    `real_sleep` 给了就在抛之前真的睡那么久——判据 4 要的是实测，不是常数相减。
    """
    connects = []

    def fake_raw_conn():
        connects.append(1)
        if len(connects) <= fail_times:
            if real_sleep:
                time.sleep(real_sleep)
            raise BLIP
        return table

    return fake_raw_conn, connects


@pytest.fixture(autouse=True)
def no_real_driver_connect(monkeypatch):
    """哨兵：本文件任何用例都不许经真驱动建连（假 conn 一律走 monkeypatch._raw_conn）。"""

    def refuse(*args, **kwargs):
        raise AssertionError(
            "tests/test_r230_db_ready_selfheal.py 试图开一条真 PostgreSQL 连接；"
            "R230 全程只用假 psycopg，按 R20 的口径判失败"
        )

    monkeypatch.setattr(psycopg, "connect", refuse, raising=False)
    yield


@pytest.fixture
def no_sleep(monkeypatch):
    """把 R229 的退避睡人抓成读数：证明重探按预算走了，而测试一秒都不真等。"""
    slept = []
    monkeypatch.setattr(auth.time, "sleep", lambda seconds: slept.append(seconds))
    return slept

def _stuck(monkeypatch, fail_times=0, real_sleep=None, memory_users=None):
    """造 R230 的死局现场：生产 + 启动探针失败过（`_db_ready=False`）+ 库此刻已回来。

    `psycopg` 保持真驱动（`connect` 被哨兵拦着、`_raw_conn` 被换成假的），因为
    `_using_memory_store() = psycopg is None or not _db_ready` 的后半支才是本单的病；
    前半支（缺驱动）没有"恢复"这回事，也不该修。
    """
    table = _FakeUsers()
    fake, connects = _flaky_conn(table, fail_times=fail_times, real_sleep=real_sleep)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_USERNAME", ADMIN)
    monkeypatch.setenv(
        "AUTH_PASSWORD_HASH",
        bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode(),
    )
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(auth, "_PG_URL", "postgresql://u@postgres:5432/eb")
    monkeypatch.setattr(auth, "_last_ready_probe_at", None, raising=False)
    monkeypatch.setattr(auth, "_MEM_USERS", memory_users if memory_users is not None else {})
    monkeypatch.setattr(auth, "_raw_conn", fake)
    logger = _Recorder()
    monkeypatch.setattr(auth, "logger", logger)
    return SimpleNamespace(table=table, connects=connects, logger=logger)


# ------------------------------------------------------------- 判据 1：复现钉
def _fake_driver(state):
    """假 psycopg 模块：第 1 发（import 期探针）抛解析错误，之后可用。

    这就是现网那一幕：容器起来那一刻 PG 还在恢复，探针红了，`_db_ready` 留在 False，
    而几秒之后库其实已经连得上。
    """

    def connect(*args, **kwargs):
        state["connects"].append(kwargs)
        if len(state["connects"]) == 1:
            raise BLIP
        return state["table"]

    module = types.ModuleType("psycopg")
    module.connect = connect
    module.OperationalError = psycopg.OperationalError
    module.errors = types.SimpleNamespace(UniqueViolation=psycopg.errors.UniqueViolation)
    module.rows = types.SimpleNamespace(dict_row=object())
    return module


def test_the_blip_at_startup_heals_on_the_next_login_without_a_restart(monkeypatch):
    """反证钉（主）：探针红在生产 + 库随后恢复 = 下一发登录就该进来，而不是等重启。

    修前读数（本文件第一版在未修的 e1511cb 上跑出来的）：import 之后 `_db_ready is
    False`，`get_user` 返回 `None`（= `app/main.py:277-282` 那一格的 401），且建连次数
    停在 1 —— 除了重启没有任何通路能让它自己好。摘掉判据 2 的重探就红在这一格。
    """
    import app.common as app_common

    state = {"connects": [], "table": _FakeUsers()}
    module = _fake_driver(state)
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "r230-nail-secret")
    monkeypatch.setenv("AUTH_USERNAME", ADMIN)
    monkeypatch.setenv(
        "AUTH_PASSWORD_HASH",
        bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode(),
    )
    monkeypatch.setitem(sys.modules, "psycopg", module)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_module)

    # 刻意不用 importlib.reload / import_module：那两枚会把重执行出来的模块挂回
    # sys.modules 与父包（R229 踩过）。exec 进临时 namespace，读数同格，进程里那枚
    # 真 auth 一个字都不动。
    namespace = {
        "__name__": "r230_selfheal_probe",
        "__file__": auth.__file__,
        "__builtins__": builtins,
    }
    source = io.open(auth.__file__, encoding="utf-8").read()
    exec(compile(source, auth.__file__, "exec"), namespace)

    # ① 死局的起点：探针那一发确实红了，`_db_ready` 留在 False。
    assert len(state["connects"]) == 1, state["connects"]
    assert namespace["_db_ready"] is False

    # ② 库其实已经回来了（第 2 发 connect 是好的），下一发查人就该放行。
    user = namespace["get_user"](ADMIN)

    assert user == {"username": ADMIN, "role": "admin", "department": "ops"}, user
    assert namespace["_db_ready"] is True

    # ③ 代价要数得出来：治好那一发多花一枚建连（探测一枚 + 它自己的查询一枚），
    #    此后回到"每请求一枚连接"的稳态，不多不少。
    assert len(state["connects"]) == 3, state["connects"]
    namespace["get_user"](ADMIN)
    assert len(state["connects"]) == 4, state["connects"]

    # ④ exec 不许在进程里留下第二枚 auth。
    assert sys.modules["app.common.auth"] is auth
    assert app_common.auth is auth
    assert auth._db_ready is False


@pytest.mark.parametrize(
    "operation, args",
    [
        ("verify_password", (ADMIN, ADMIN_PASSWORD)),
        ("list_users", ()),
        ("get_user", (ADMIN,)),
        ("create_user", ("ghost", "pass1234")),
        ("upsert_sso_user", (ADMIN,)),
        ("delete_user", (1,)),
        ("change_password", (ADMIN, ADMIN_PASSWORD, NEW_PASSWORD)),
    ],
)
def test_every_authentication_entry_point_gets_its_recovery_chance(
    monkeypatch, operation, args
):
    """7 枚入口一枚都不能漏：只有 `_memory_store_denied` 拿到重探机会才算解开死锁。

    `app/main.py:246` 的 `async def dispatch` 直调的是同步 `get_user`，但运维建号、
    改密、SSO 同步走另外 6 枚入口——漏一枚就是漏一条"只能重启"的路。每一轮都把状态
    摆回"探针红过"（`_db_ready=False` + 节流清零）再打这一枚。
    """
    stuck = _stuck(monkeypatch)

    result = getattr(auth, operation)(*args)

    assert result != DENIED_NOW[operation], (operation, result)
    assert auth._db_ready is True
    assert auth._using_memory_store() is False
    assert stuck.connects, "这一枚入口根本没试过重新建连"

# ------------------------------------------------- 判据 2：自愈修法的三条硬界
def test_the_reprobe_is_rate_limited(monkeypatch, no_sleep):
    """反证钉（有界）：库还是不通时，200 发登录只能换来一枚探测，不是 200 次握手。

    修前读数是 0 枚探测（一次都不试，所以永不自愈），摘掉判据 2 同样红在这一格。
    到点（`_READY_PROBE_INTERVAL_SECONDS`）之后必须再给一次机会，否则本单只是把
    "重启才能好"换成了"永远不再试"。
    """
    stuck = _stuck(monkeypatch, fail_times=10 ** 6)
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])

    for _ in range(200):
        assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    assert len(stuck.connects) == auth._CONNECT_ATTEMPTS, stuck.connects
    assert no_sleep == [0.05, 0.1], no_sleep

    clock[0] += auth._READY_PROBE_INTERVAL_SECONDS - 1
    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    assert len(stuck.connects) == auth._CONNECT_ATTEMPTS, "间隔没走完就再握手 = 本单白做"

    clock[0] += 1
    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    assert len(stuck.connects) == 2 * auth._CONNECT_ATTEMPTS, stuck.connects


def test_the_reprobe_reuses_the_r229_connect_path(monkeypatch):
    """判据 2(b)：重探走 `_connect_for_request`，也就是 R229 那套超时/预算，不另起一套。"""
    _stuck(monkeypatch)
    seen = []
    table = _FakeUsers()

    def spy(operation):
        seen.append(operation)
        return table

    monkeypatch.setattr(auth, "_connect_for_request", spy)

    assert auth._retry_readiness_probe() is True
    assert len(seen) == 1, seen
    assert auth._db_ready is True


def test_the_probe_introduces_no_second_set_of_latency_parameters():
    """时延常量集合只许多出"最小重探间隔"这一枚，且它本身不是超时/退避。"""
    # 查的是代码体，不是散文：docstring 里"复用 R229 的 connect_timeout"这类话必须
    # 允许出现，否则这条钉只会惩罚写得清楚的注释。
    source = inspect.getsource(auth._retry_readiness_probe)
    source = source.replace(auth._retry_readiness_probe.__doc__ or "", "")

    assert "sleep" not in source, "重探自己不许睡人；睡只在 R229 的退避里"
    assert "connect_timeout" not in source, "超时只有 `_connect_kwargs` 那一处口径"
    assert "psycopg.connect" not in source, "重探不许绕过 `_connect_for_request` 直连"
    assert "ConnectionPool" not in source, "本单同样不许加池"
    assert {name for name in vars(auth) if name.endswith("_SECONDS")} == {
        "_CONNECT_TIMEOUT_SECONDS",
        "_RETRY_BACKOFF_BASE_SECONDS",
        "_RETRY_BACKOFF_CAP_SECONDS",
        "_RETRY_BUDGET_SECONDS",
        "_READY_PROBE_INTERVAL_SECONDS",
    }


def test_the_probe_writes_nothing_when_the_user_table_is_already_there(monkeypatch):
    """生产形态的重探是只读的：两句 SELECT，零 DDL，零 commit，连接当场关掉。"""
    _stuck(monkeypatch)
    table = _FakeUsers()
    monkeypatch.setattr(auth, "_raw_conn", lambda: table)

    assert auth._retry_readiness_probe() is True

    assert table.commits == 0, table.commits
    assert table.closes == 1, "探测用的连接必须当场关掉，不能等人来收"
    assert all(
        not statement.upper().startswith(("CREATE", "ALTER", "INSERT", "UPDATE", "DELETE"))
        for statement in table.statements
    ), table.statements
    assert len(table.statements) == 2, table.statements


# ------------------------------------------------- 判据 3：default-deny 一字不放宽
def test_the_refusal_is_byte_identical_when_the_database_is_still_down(monkeypatch, no_sleep):
    """库真不通时，对外可见结果与修前逐字节相同：同一句 ERROR，同一个拒答，仍是 401。"""
    stuck = _stuck(monkeypatch, fail_times=10 ** 6)
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])

    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]

    assert stuck.logger.errors() == [REFUSAL_ERROR], stuck.logger.errors()
    assert auth._db_ready is False
    assert auth._using_memory_store() is True

    # 多一枚探测不多一条拒绝日志：仍然是"每拒一次一条 ERROR"。
    clock[0] += auth._READY_PROBE_INTERVAL_SECONDS
    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    assert stuck.logger.errors() == [REFUSAL_ERROR, REFUSAL_ERROR], stuck.logger.errors()


def test_a_refused_request_never_gets_let_in_by_the_memory_table(monkeypatch, no_sleep):
    """严禁把"拒绝"换成"用内存表放行"：内存里躺着正确口令，也仍然是拒。

    这条是判据 3 的下限——鉴权降级成假象比 401 严重得多。摘掉修复这格也过（护栏）。
    """
    _stuck(
        monkeypatch,
        fail_times=10 ** 6,
        memory_users={
            ADMIN: {
                "id": 1,
                "username": ADMIN,
                "password_hash": bcrypt.hashpw(
                    ADMIN_PASSWORD.encode(), bcrypt.gensalt()
                ).decode(),
                "role": "admin",
                "department": "ops",
            }
        },
    )

    assert auth.verify_password(ADMIN, ADMIN_PASSWORD) is DENIED_NOW["verify_password"]
    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    assert auth.list_users() == DENIED_NOW["list_users"]
    assert auth.create_user("ghost", "pass1234") == DENIED_NOW["create_user"]
    assert auth.upsert_sso_user(ADMIN) == DENIED_NOW["upsert_sso_user"]
    assert auth.delete_user(1) is DENIED_NOW["delete_user"]
    assert (
        auth.change_password(ADMIN, ADMIN_PASSWORD, NEW_PASSWORD)
        == DENIED_NOW["change_password"]
    )
    assert auth.user_storage_state()["storage_mode"] == "unavailable"
    assert auth.user_storage_state()["protection"] == "refuse_start"


def test_no_probe_is_attempted_when_the_driver_is_missing(monkeypatch):
    """缺驱动（`psycopg is None`）没有"恢复"这回事：一次握手都不许试，拒答不变。

    这同时保住 `tests/test_r229_auth_semantics.py:92` 那句"拒绝路径上一发连接都不该开"。
    """
    connects = []
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "psycopg", None)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(auth, "_last_ready_probe_at", None, raising=False)
    monkeypatch.setattr(auth, "_raw_conn", lambda: connects.append(1))
    monkeypatch.setattr(auth, "_connect_for_request", lambda operation: connects.append(1))

    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    assert auth.verify_password(ADMIN, ADMIN_PASSWORD) is DENIED_NOW["verify_password"]
    assert connects == [], connects
    assert auth._retry_readiness_probe() is False


def test_the_runtime_flip_inside_get_conn_is_unreachable(monkeypatch):
    """修前事实（本单独立复核到的差异，留着当护栏）：`_get_conn()` 里那枚置真恒不可达。

    走到 `if not _db_ready` 之前必须先过 `if _using_memory_store(): return _FakeConn()`，
    而前者成立时后者必真 ⇒ 那一格永远跑不到。也就是说：运行期重探这件事在本仓从来没
    存在过，R230 的探测是唯一一枚活的。本单不顺手改这一格（它归"全仓一处连接边界"）。
    """
    _stuck(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")

    conn = auth._get_conn()

    assert isinstance(conn, auth._FakeConn)
    assert auth._db_ready is False, (
        "_get_conn 修前修后都翻不了这枚旗；能翻它的只有 _retry_readiness_probe"
    )

def test_a_recovered_process_stops_reporting_an_unavailable_store(monkeypatch):
    """`_db_ready` 是全仓共用的就绪旗（alerts / chat / catalog / profile / registry /
    pending_approvals 六处都读它）：修好之后健康读数也得跟着翻正。"""
    _stuck(monkeypatch)

    assert auth.user_storage_state()["storage_mode"] == "unavailable"
    assert auth.get_user(ADMIN) is not None

    state = auth.user_storage_state()
    assert state["storage_mode"] == "postgres"
    assert state["durable"] is True
    assert state["protection"] == "none"


def test_the_steady_state_costs_one_connect_per_request_again(monkeypatch):
    """治好之后回到 R229 的稳态账：一枚请求一枚连接，只有"治好那一发"多花一枚。"""
    stuck = _stuck(monkeypatch)

    assert auth.get_user(ADMIN) is not None
    assert len(stuck.connects) == 2, stuck.connects
    for _ in range(5):
        assert auth.get_user(ADMIN) is not None
    assert len(stuck.connects) == 7, stuck.connects


# --------------------------------------------------------- 判据 4：代价要量出来
def test_the_worst_case_added_latency_of_one_reprobe_is_measured(monkeypatch):
    """最坏情况实测（不是估算）：黑洞式失败——每一发都跑满 `connect_timeout` 才红。

    这条路跑在事件循环上（`app/main.py:246` 的 `async def dispatch` 直调同步
    `get_user`），所以"探测失败"花的不是探测者自己的时间，是全场的。本单给它的界
    就是 R229 那枚预算：单发最坏 ≤ `_RETRY_BUDGET_SECONDS`，且一个间隔窗口只发生一枚。
    """
    stuck = _stuck(monkeypatch, fail_times=10 ** 6, real_sleep=auth._CONNECT_TIMEOUT_SECONDS)

    started = time.perf_counter()
    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    elapsed = time.perf_counter() - started

    # 下限证明这确实是"跑满超时"那一发（不是拿快失败冒充最坏情况交差）。
    assert elapsed >= auth._CONNECT_TIMEOUT_SECONDS * 0.9, elapsed
    # 上限就是钉住的界：绝不许超过预算，也不许在同一窗口内再来第二枚探测。
    assert elapsed <= auth._RETRY_BUDGET_SECONDS, elapsed
    assert len(stuck.connects) == 1, "慢死场景一枚探测只吃一次尝试（R229 第 3 条代价）"

    started = time.perf_counter()
    assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    throttled = time.perf_counter() - started
    assert throttled < 0.005, throttled


def test_the_amortized_cost_while_the_database_is_down_is_small(monkeypatch):
    """快速失败（现网最常见：PG 容器还没起来 = connection refused）下的总代价实测。

    这里不打桩 sleep：200 发登录的总加时就是运维真会看见的数字，读数写进交回单。
    """
    stuck = _stuck(monkeypatch, fail_times=10 ** 6)

    started = time.perf_counter()
    for _ in range(200):
        assert auth.get_user(ADMIN) is DENIED_NOW["get_user"]
    elapsed = time.perf_counter() - started

    assert len(stuck.connects) == auth._CONNECT_ATTEMPTS, stuck.connects
    # 一枚探测 = 3 次快失败 + 两次退避（50ms + 100ms），所以 200 发的总加时应当远小于
    # 一个重试预算；这条就是"不许把每一发登录变成一次现场握手"的实测形式。
    assert elapsed < auth._RETRY_BUDGET_SECONDS, elapsed


def test_the_constants_the_next_person_will_ask_about():
    """把钉住的界原样交出来，免得下一个人重新猜一遍常数。"""
    assert auth._CONNECT_TIMEOUT_SECONDS == 2
    assert auth._CONNECT_ATTEMPTS == 3
    assert auth._RETRY_BUDGET_SECONDS == 3.0
    assert auth._READY_PROBE_INTERVAL_SECONDS == 15.0
