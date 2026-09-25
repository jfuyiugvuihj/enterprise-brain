"""JWT auth and user management with PostgreSQL fallback."""
import os
import re
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import yaml
from dotenv import load_dotenv
from fastapi import Request

from app.common.logger import logger

load_dotenv()

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None
    dict_row = None

_tz = timezone(timedelta(hours=8))
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")

# ---------------------------------------------------------------------------
# R229 乙案（把短暂解析失败收敛成可重试）——鉴权建连的时延参数。
#
# 现网症状：/queue/status 间歇 500，栈停在
# `psycopg.OperationalError: failed to resolve host 'postgres' [Errno -3]`。
# 根因是鉴权这条路"每个请求新建一条 psycopg 连接、失败即抛给调用方"，而
# `_raw_conn()` 连 `connect_timeout` 都没有，于是解析器抖一下 = 用户一个 500。
#
# 下面五个数全是"有界"，不是"最优"：调大能多吸一点抖动，调大的同时拉长最坏情况
# 的单请求时延，而这条路跑在事件循环上（见 `_connect_for_request` 代价 5）。
# ---------------------------------------------------------------------------
_CONNECT_TIMEOUT_SECONDS = 2
_CONNECT_ATTEMPTS = 3
_RETRY_BACKOFF_BASE_SECONDS = 0.05
_RETRY_BACKOFF_CAP_SECONDS = 0.2
_RETRY_BUDGET_SECONDS = 3.0

# ---------------------------------------------------------------------------
# R230 自愈：上面那五个数管的是"一枚请求怎么连"，这枚数管的是"隔多久才许再问一次"。
#
# 它不是第二套时延参数——超时/退避/预算仍然只有 R229 那五枚，本单一个新数都不带。
# 它是一枚节流：没有它，每一发撞上门的登录请求都会自己去握一次手（见
# `_retry_readiness_probe` 的代价 2）。
# ---------------------------------------------------------------------------
_READY_PROBE_INTERVAL_SECONDS = 15.0

_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
_config = {}
try:
    with open(_config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f) or {}
except FileNotFoundError:
    pass

_auth_cfg = _config.get("auth", {})
_EXPIRE_HOURS = _auth_cfg.get("token_expire_hours", 24)

PUBLIC_PATHS = {"/", "/docs", "/openapi.json", "/redoc", "/api/v1/login", "/api/v1/health", "/api/v1/sso/login"}
_MEM_USERS: dict[str, dict] = {}
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}


class _FakeRow:
    def __init__(self, row: dict | None = None, rowcount: int = 0):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class _FakeConn:
    def execute(self, sql: str, params=None):
        text = sql.lower()
        params = params or ()
        if "select id from users where username" in text:
            username = params[0] if params else ""
            row = _MEM_USERS.get(username)
            return _FakeRow({"id": row["id"]} if row else None)
        if "delete from users where username like" in text:
            removed = 0
            for key, user in list(_MEM_USERS.items()):
                if key.startswith("test_"):
                    _MEM_USERS.pop(key, None)
                    removed += 1
            return _FakeRow(rowcount=removed)
        if "delete from users where username =" in text:
            username = params[0] if params else ""
            removed = 1 if _MEM_USERS.pop(username, None) else 0
            return _FakeRow(rowcount=removed)
        return _FakeRow()

    def commit(self):
        return None

    def close(self):
        return None


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _jwt_secret() -> str:
    secret = (
        os.getenv("JWT_SECRET")
        or os.getenv("JWT_SECRET_KEY")
        or _auth_cfg.get("jwt_secret")
        or ""
    ).strip()
    if secret:
        return secret
    if _is_production_environment():
        raise RuntimeError("JWT_SECRET or JWT_SECRET_KEY is required in production")
    return "dev-secret-change-me"


def _bootstrap_admin_credentials() -> tuple[str, str]:
    username = os.getenv("AUTH_USERNAME", "").strip()
    password_hash = os.getenv("AUTH_PASSWORD_HASH", "").strip()
    if _is_production_environment():
        if not username:
            raise RuntimeError(
                "AUTH_USERNAME is required in production: it names the first administrator account"
            )
        if not password_hash:
            raise RuntimeError(
                "AUTH_PASSWORD_HASH is required in production: it is the credential of the first "
                "administrator account (see deploy/README.server.md)"
            )
    if not username:
        username = "admin"
    if not password_hash:
        password_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
    return username, password_hash


if _is_production_environment():
    _jwt_secret()


def _load_memory_admin():
    username, password_hash = _bootstrap_admin_credentials()
    _MEM_USERS[username] = {
        "id": 1,
        "username": username,
        "password_hash": password_hash,
        "role": "admin",
        "department": _bootstrap_admin_department(),
    }


def _using_memory_store() -> bool:
    return psycopg is None or not _db_ready


def user_storage_state() -> dict:
    """Name the user store this process authenticates against."""
    if psycopg is not None and _db_ready:
        return {
            "storage_mode": "postgres",
            "durable": True,
            "shared_across_processes": True,
            "protection": "none",
            "detail": "users table served by PostgreSQL",
        }
    reason = (
        "psycopg driver is unavailable"
        if psycopg is None
        else "PostgreSQL is not reachable, users live in the process-local table"
    )
    return {
        "storage_mode": "unavailable" if _is_production_environment() else "memory",
        "durable": False,
        "shared_across_processes": False,
        "protection": "refuse_start" if _is_production_environment() else "none",
        "detail": reason,
    }


_last_ready_probe_at: float | None = None


def _retry_readiness_probe() -> bool:
    """在"拒绝"落下来之前，给这个进程一次重新确认用户库是不是真的不通的机会。

    为什么必须长在这一支（R230 的病）：`_db_ready` 全仓只有两处置真——import 期探针
    与 `_get_conn()`。而后者的那一枚长在 `if not _db_ready` 里，要走到那一行必须先过
    开头的 `if _using_memory_store(): return _FakeConn()`，而 `_using_memory_store()`
    恰在 `_db_ready` 为假时为真 ⇒ 那一格恒不可达。生产里 `_memory_store_denied` 又抢在
    `_get_conn()` 之前把 7 枚鉴权入口全挡住，于是"容器起来那一刻 PG 还在恢复"就等于
    之后每一发鉴权都被拒，且没有任何重探通路，直到有人重启进程。这一枚就是缺的那条通路。

    三条硬约束，逐条有钉（`tests/test_r230_db_ready_selfheal.py`）：
    (a) 有界：两次重探之间至少隔 `_READY_PROBE_INTERVAL_SECONDS`，且"本窗口已探过"
        由开头那枚时间戳**先落地再握手**保证，所以同一窗口里撞进来的并发登录只有一枚
        会真去建连，其余照旧直接拒。
    (b) 复用：建连走 `_connect_for_request`，也就是 R229 那套 `connect_timeout` / 退避
        / 预算；本函数自己不带任何时延参数、不睡人、不加池。
    (c) 安静：探不通就 `return False`，调用方落原来那条 ERROR、给原来那个拒答，对外
        可见结果一个字节都不变。default-deny 不放宽，内存表永远不是一条放行的路。

    代价，写清楚了才许用：
    1. 撞上门的那一发请求替全场付一次握手。最坏情况是"黑洞式失败"（每一发都跑满
       `connect_timeout` 才红）：实测 2.001 s，界是 R229 的 `_RETRY_BUDGET_SECONDS`
       = 3.0 s（慢死时预算装不下第二次尝试，所以一枚探测只吃一次 connect，拿不到第三
       次）。这条路跑在事件循环上（`app/main.py:246` 的 `async def dispatch` 直调同步
       `get_user`），这 2 s 是全场的，不是这一个用户的。
    2. 占空比由节流兜住：一个窗口只发生一枚探测（实测 200 发登录在窗口内共多花
       0.003 s，建连仍为 3 次）。快速失败（PG 容器还没起来 = connection refused，现网
       最常见）一枚探测 = 3 次尝试 + 50 ms + 100 ms 退避 = 实测 0.151 s，摊到 15 s
       窗口 = 1.00% 的事件循环；只有黑洞式失败才到 13.33%。窗口内其余请求各付
       实测 22 µs（一次单调钟比较 + 原来那条 ERROR）。
    3. 治好那一发多花一枚建连（探测一枚 + 它自己的查询一枚），此后稳态仍是"每请求
       一枚连接"；不加池 ⇒ 不新增常驻连接。
    4. `psycopg is None`（驱动缺失）直接不探：那不是抖动，重启之外没有恢复通路，
       探一次都是白付钱。开发环境同样不探——它不被这一支挡着，本单不动它的语义。
    5. 就绪判据与 import 探针同源（`_connect_for_request` + `_create_schema`），所以
       生产形态下它只读两句 SELECT（`to_regclass` + `COUNT`），零 DDL、零 commit；
       表空时与探针同形地 seed 第一枚管理员——那是探针本来就有的写点，不是本单新增。
    6. 只把 `_db_ready` 从 False 翻到 True，永不反向：这枚旗另有 6 处读者（alerts /
       chat / catalog / profile / registry / pending_approvals），把它们一起翻正正是
       本单要的效果，而翻回假是本单不该有的副作用。
    """
    global _db_ready, _last_ready_probe_at

    if psycopg is None or _db_ready or not _is_production_environment():
        return False
    now = time.monotonic()
    if (
        _last_ready_probe_at is not None
        and now - _last_ready_probe_at < _READY_PROBE_INTERVAL_SECONDS
    ):
        return False
    _last_ready_probe_at = now

    try:
        conn = _connect_for_request("production user store")
    except Exception as exc:  # noqa: BLE001 - 探不通 = 照旧拒绝，不许把错递给调用方
        logger.debug(f"[Auth] R230 重探未连上用户库，维持拒绝: {type(exc).__name__}: {exc}")
        return False

    ready = False
    try:
        _create_schema(conn)
        ready = True
    except Exception as exc:  # noqa: BLE001 - 连上了但用户表不可用，同样是拒绝
        logger.debug(f"[Auth] R230 重探连上但用户表不可用，维持拒绝: {type(exc).__name__}: {exc}")
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - 关不掉交给 GC，不影响就绪判定
            pass

    if not ready:
        return False
    _db_ready = True
    logger.info("[Auth] R230 生产用户库在启动探针失败后重新可用，鉴权不再需要重启进程")
    return True


def _memory_store_denied(operation: str) -> bool:
    """Refuse to authenticate against a process-local user table in production.

    Login is a write path (user creation, SSO sync, password change), so there is no
    read-only form of this store: two workers would disagree about who exists. Every
    caller keeps its previous default-deny behaviour when this returns True.

    R230 puts one rate-limited re-probe *ahead* of the refusal and changes nothing
    about the refusal itself. Before this, a deployment whose import-time probe blipped
    denied every login until somebody restarted the process, because the only runtime
    code able to set ``_db_ready`` sat behind this very check. When the probe fails,
    the ERROR below and the caller's default-deny answer are byte-for-byte what they
    always were: an unreachable user store still refuses, it never falls back to the
    process-local table.
    """
    if not (_is_production_environment() and _using_memory_store()):
        return False
    if _retry_readiness_probe():
        return False
    logger.error(
        f"[Auth] production user store is not durable; refused {operation} "
        "(set DATABASE_URL and run migrations)"
    )
    return True


def _raw_conn():
    if psycopg is None:
        raise RuntimeError("psycopg unavailable")
    return psycopg.connect(_PG_URL, row_factory=dict_row, **_connect_kwargs())


# `connect_timeout` 在 libpq 里是 URI 的查询参数（?connect_timeout=2），也认
# 空格式 conninfo（connect_timeout=2），两种都认下来，才谈得上"不覆盖它"。
_DSN_CONNECT_TIMEOUT = re.compile(r"(?:[?&;]|\s)connect_timeout\s*=")


def _connect_kwargs() -> dict:
    """给这枚 connect 补上 `connect_timeout`，除非 DSN 自己已经写了。

    今天这枚 connect 是没有任何超时的：解析卡住时归 OS 解析器说了算，glibc 默认能
    拖到 5s 以上还会自己叠重发。本单不加池、不改连接归属，只把"最坏情况无上限"换成
    "最坏情况有上限"，这一条比下面那枚重试更值钱。

    不覆盖 DSN 里已有的 `connect_timeout` 是有意的：`tests/conftest.py:51` 把测试 DSN
    钉成 `127.0.0.1:1` 并断言串里带着 `connect_timeout=1`，那是"探活必须快"的测试口径，
    本单不许把它改成 2s。库上真写了超时就以库上的读数为准。
    """
    if _DSN_CONNECT_TIMEOUT.search(_PG_URL or ""):
        return {}
    return {"connect_timeout": _CONNECT_TIMEOUT_SECONDS}


def _transient_connect_errors() -> tuple:
    """只有 `OperationalError` 够格重试；连这枚类都拿不到时，一律不重试。

    现网那枚 `failed to resolve host` 就是 `psycopg.OperationalError`，实测 psycopg
    3.3.5 里 `ConnectionTimeout` / `CannotConnectNow` / `TooManyConnections` 也都挂在
    它下面，所以一枚 `OperationalError` 就盖住了"服务端还没受理这条语句"的整类失败。
    `ProgrammingError`、`UniqueViolation` 这类"语句已经到达服务端"的错不在名单里：
    宁可少吸一次抖动，也不许把一条可能已经落盘的写语句重放。

    返回空元组的意思是"不重试"，不是"什么都重试"。`tests/test_auth_database.py:90`
    会把 `auth.psycopg` 换成一个 `object()`，那时代码里根本取不到异常类，必须安静地
    退回今天"失败即抛"的行为，而不是拿一个不存在的类去做 `except`。
    """
    operational = getattr(psycopg, "OperationalError", None) if psycopg is not None else None
    if isinstance(operational, type) and issubclass(operational, BaseException):
        return (operational,)
    return ()


def _connect_for_request(operation: str):
    """新建一条鉴权连接，只把"连接尚未建立"这一段失败收敛成有界重试。

    为什么是乙（有界重试）而不是甲（连接池）——先把数出来账摆平：
    `_raw_conn()` 的直接调用点全仓 **2 枚**（本文件 import 探针 `_c = _raw_conn()`
    与 `_get_conn()` 里的 `conn = _raw_conn()`），`_get_conn()` 的调用点 **7 枚**
    （verify_password / list_users / create_user / get_user / upsert_sso_user /
    delete_user / change_password）。而一发已登录请求在热路径上只走 `get_user`
    一处（`app/main.py:277`；`_authorize_queue_task` 用的是 middleware 已经塞进
    `request.state.principal` 的对象，不再查库），即"每请求 1 条新连接"。
    频率读数：run7 相 1 整窗 0 次，今晨 78 发 /queue/status 里 1 次（约 1.3%）。

    也就是说：看到的是解析器抖了一下，不是连接被用光。池能把 78 次握手压成个位数，
    但它消不掉同一个依赖——池补到 min_size、或回收一条被服务端掐死的连接时，照样
    得现场做一次 DNS + 解析，抖动那一下它一样红，只是红的次数少些。而它的代价是立刻
    落在账面上的：`app/agents/orchestrator.py:174` 已经在同进程里开了枚
    min_size=5/max_size=50 的池（findings.md:377 记的就是这笔"replicas x 50 必须小于
    max_connections"的账），本文件又被 backend / worker / mcp_server 三方各自 import，
    第二枚池意味着每个进程再多常驻 min_size 条连接，而 `deploy/docker-compose.server.yml:22`
    把 PG 上限定成 `POSTGRES_MAX_CONNECTIONS:-200`。实测 app/** 里 auth.py 之外还有 14 处
    `psycopg.connect`（其中 7 处连 `connect_timeout` 都没有），池只治得到鉴权这一棵，治不到整体连接数。

    结论：先按症状下刀（超时 + 有界重试），把池留给总控当"全仓一处连接边界"来定，
    而不是在这里偷偷加第二枚常驻池、还要为它背一层"池坏了不能把鉴权打死"的回退码。

    代价，写清楚了才许用：
    1. 抖动是拿"最坏情况更慢"换的。今天失败立刻抛；现在最坏要多掏一次退避。上界由
       `_RETRY_BUDGET_SECONDS` 与下面那句"剩下的预算装不下一次完整尝试就放手"共同兜住。
    2. 重试只发生在"连接还没建立"这一格：`_raw_conn()` 除了 connect 什么都不做，
       抛出来就意味一条语句也没递上去，所以不可能重放写。`_create_schema()` 与
       `upsert_sso_user` 的 commit 全在拿到连接之后，一次尝试都不多给。
    3. 快速失败才吃得到 3 次机会，慢死（每发都跑到超时）只吃 1 次——多等不如快失败。
       这也是为什么预算用"装得下一次完整尝试"来卡，而不是"只要还剩一秒就再试"。
    4. 退避是定死的指数（50ms -> 100ms，封顶 200ms），没加 jitter。失败同批醒来这个
       风险今天不存在（每请求一条连接，没有共享资源可争），量级上去再说。
    5. 这条路跑在事件循环上：`app/main.py:246` 是 `async def dispatch`，里面直接调
       同步的 `get_user()`。所以 `time.sleep` 的每一毫秒都是全场共享的，这也是
       `connect_timeout` 比"重试次数"更要紧的原因。把鉴权挪出事件循环是总控的账。
    """
    transient = _transient_connect_errors()
    started = time.monotonic()
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            return _raw_conn()
        except transient as exc:
            elapsed = time.monotonic() - started
            backoff = min(
                _RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                _RETRY_BACKOFF_CAP_SECONDS,
            )
            fits = elapsed + backoff + _CONNECT_TIMEOUT_SECONDS <= _RETRY_BUDGET_SECONDS
            if attempt >= _CONNECT_ATTEMPTS or not fits:
                logger.warning(
                    f"[Auth] {operation} 建连失败，不再重试"
                    f"（第 {attempt}/{_CONNECT_ATTEMPTS} 次，已耗 {elapsed:.3f}s，"
                    f"预算 {_RETRY_BUDGET_SECONDS}s）: {type(exc).__name__}: {exc}"
                )
                raise
            logger.warning(
                f"[Auth] {operation} 建连失败，{backoff * 1000:.0f}ms 后重连"
                f"（第 {attempt}/{_CONNECT_ATTEMPTS} 次）: {type(exc).__name__}: {exc}"
            )
            time.sleep(backoff)
    raise RuntimeError("unreachable: _connect_for_request used up its attempts")


def _create_schema(conn):
    if _is_production_environment():
        row = conn.execute("SELECT to_regclass('public.users') AS table_name").fetchone()
        if not row or row["table_name"] is None:
            raise RuntimeError("users table is required in production; run migrations first")
        _seed_bootstrap_admin(conn)
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
        )
        """
    )
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS department TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'staff'")
    conn.commit()
    _seed_bootstrap_admin(conn)


def _bootstrap_admin_department() -> str:
    """The department the first administrator owns, when the operator names one.

    Signing in and managing users works without a department, but a writer has to own
    one: both the dataset and the artifact registry refuse a principal with no
    department scope, so a departmentless administrator cannot upload data or produce
    a chart. Naming it here is what makes the account usable on a fresh install.
    """
    return os.getenv("AUTH_DEPARTMENT", "").strip()


def _seed_bootstrap_admin(conn) -> None:
    """Give an empty user table the administrator named in the environment.

    ``migrations/0003`` creates ``users`` with no rows, and every route that can add a
    user already requires a session, so a production deployment started against a fresh
    database had no account to sign in with and no way to create one. The seed only runs
    while the table is empty, and ``ON CONFLICT`` stops the backend, worker and scheduler
    - which each probe the database at import time - from losing a race against each
    other. A deleted operator account is therefore never resurrected.
    """
    if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]:
        return
    username, password_hash = _bootstrap_admin_credentials()
    conn.execute(
        "INSERT INTO users (username, password_hash, role, department) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
        (username, password_hash, "admin", _bootstrap_admin_department() or None),
    )
    conn.commit()
    logger.info("[Security] Initial admin account created from configured bootstrap credentials")


_db_ready = False
if psycopg is not None:
    try:
        # 这枚 import 期探针刻意不走 `_connect_for_request`：启动时还没有人在等答复，
        # 把重试放在这里只会把"PG 没起来"换成"容器多停几秒"，拖住健康检查与重启循环。
        # 探针失败今天也只记一条 warning，真正的补救在请求路径上（`_get_conn` 会重建表）。
        # 同理，`_connect_kwargs()` 对这枚探针也有效：DSN 没写超时时，它不再能无限期挂住 import。
        _c = _raw_conn()
        _create_schema(_c)
        _c.close()
        _db_ready = True
    except Exception as exc:
        logger.warning(f"[Auth] Postgres 不可用，将在首次连接时建表: {exc}")
        _load_memory_admin()
else:
    _load_memory_admin()


def _get_conn():
    global _db_ready
    if _using_memory_store():
        return _FakeConn()
    conn = _connect_for_request("user store access")
    if not _db_ready:
        try:
            _create_schema(conn)
            _db_ready = True
        except Exception:
            pass
    return conn


def verify_password(username: str, password: str) -> bool:
    if _memory_store_denied("password verification"):
        return False
    if _using_memory_store():
        row = _MEM_USERS.get(username)
        return bool(row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()))
    with _get_conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username = %s", (username,)).fetchone()
    if not row:
        return False
    return bcrypt.checkpw(password.encode(), row["password_hash"].encode())


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": datetime.now(_tz),
        "exp": datetime.now(_tz) + timedelta(hours=_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def list_users() -> list[dict]:
    if _memory_store_denied("user listing"):
        return []
    if _using_memory_store():
        return [
            {"id": user["id"], "username": user["username"], "role": user["role"], "department": user["department"], "created_at": ""}
            for user in sorted(_MEM_USERS.values(), key=lambda item: item["id"])
        ]
    with _get_conn() as conn:
        rows = conn.execute("SELECT id, username, role, department, created_at FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str = "staff", department: str | None = None) -> tuple[bool, str]:
    if not username or not password:
        return False, "用户名和密码不能为空"
    if len(password) < 6:
        return False, "密码至少 6 位"
    if role not in ("staff", "manager", "admin"):
        return False, f"非法角色: {role}"

    if _memory_store_denied("user creation"):
        return False, "production_user_store_unavailable"
    if _using_memory_store():
        if username in _MEM_USERS:
            return False, f"用户 '{username}' 已存在"
        _MEM_USERS[username] = {
            "id": max((u["id"] for u in _MEM_USERS.values()), default=0) + 1,
            "username": username,
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            "role": role,
            "department": department or "",
        }
        return True, "创建成功"

    try:
        with _get_conn() as conn:
            hsh = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO users (username, password_hash, role, department) VALUES (%s, %s, %s, %s)",
                (username, hsh, role, department),
            )
            conn.commit()
            return True, "创建成功"
    except psycopg.errors.UniqueViolation:
        return False, f"用户 '{username}' 已存在"


def get_user(username: str) -> dict | None:
    if _memory_store_denied("user lookup"):
        return None
    if _using_memory_store():
        row = _MEM_USERS.get(username)
        return {"username": row["username"], "role": row["role"], "department": row["department"]} if row else None
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT username, role, department FROM users WHERE username = %s",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def upsert_sso_user(username: str, role: str = "staff", department: str | None = None) -> tuple[bool, str]:
    if not username:
        return False, "用户名不能为空"
    if role not in ("staff", "manager", "admin"):
        role = "staff"

    if _memory_store_denied("SSO user sync"):
        return False, "production_user_store_unavailable"
    if _using_memory_store():
        if username in _MEM_USERS:
            _MEM_USERS[username]["role"] = role
            _MEM_USERS[username]["department"] = department or ""
        else:
            _MEM_USERS[username] = {
                "id": max((u["id"] for u in _MEM_USERS.values()), default=0) + 1,
                "username": username,
                "password_hash": bcrypt.hashpw(secrets.token_urlsafe(24).encode(), bcrypt.gensalt()).decode(),
                "role": role,
                "department": department or "",
            }
        return True, "SSO 用户已同步"

    try:
        with _get_conn() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET role = %s, department = %s WHERE username = %s",
                    (role, department, username),
                )
            else:
                placeholder = bcrypt.hashpw(secrets.token_urlsafe(24).encode(), bcrypt.gensalt()).decode()
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, department) VALUES (%s, %s, %s, %s)",
                    (username, placeholder, role, department),
                )
            conn.commit()
        return True, "SSO 用户已同步"
    except Exception as exc:
        return False, f"SSO 用户同步失败: {exc}"


def delete_user(user_id: int) -> bool:
    if _memory_store_denied("user deletion"):
        return False
    if _using_memory_store():
        for key, user in list(_MEM_USERS.items()):
            if user["id"] == user_id:
                _MEM_USERS.pop(key, None)
                return True
        return False
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return cur.rowcount > 0


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    if not verify_password(username, old_password):
        return False, "原密码错误"
    if len(new_password) < 6:
        return False, "新密码至少 6 位"
    if _memory_store_denied("password change"):
        return False, "production_user_store_unavailable"
    if _using_memory_store():
        _MEM_USERS[username]["password_hash"] = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        return True, "密码已更新"
    with _get_conn() as conn:
        hsh = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password_hash = %s WHERE username = %s", (hsh, username))
        conn.commit()
    return True, "密码已更新"
