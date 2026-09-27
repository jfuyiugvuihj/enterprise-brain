import json
import os
import sys
from datetime import datetime, timedelta, timezone

from app.common.logger import logger
from app.common.table_presence import ABSENT, PRESENT, UNKNOWN, probe_table

_tz = timezone(timedelta(hours=8))
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_initialized = False
_MEM_PROFILES: dict[str, dict] = {}
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def compose_profile_context(profile: dict | None) -> str:
    if not profile:
        return ""
    parts = []
    if profile.get("department"):
        parts.append(f"department: {profile['department']}")
    if profile.get("position"):
        parts.append(f"position: {profile['position']}")
    preferences = profile.get("preferences") or []
    if preferences:
        parts.append("preferences: " + ", ".join(str(item) for item in preferences))
    role = profile.get("role")
    if role:
        parts.append(f"role: {role}")
    return "\n".join(parts)


def _conn():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _database_available() -> bool:
    auth_module = sys.modules.get("app.common.auth")
    return bool(auth_module and getattr(auth_module, "_db_ready", False))


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


#: 「连得上库」与「该由迁移建的那枚表在位」是两件事，生产这一格两件都得问。问句与 NULL 判法只
#: 有一处，即 `app/common/table_presence.py`；本模块不再另写一套查表的办法。三值里只有 PRESENT
#: 配得上 durable，另两值各自一句人话，档位一枚都不新长（都落回本模块已有的 unavailable + read_only）。
UNWARRANTED_DETAILS = {
    ABSENT: (
        "user_profiles is not in the database; run migrations/"
        "0003_legacy_runtime_tables.sql before profiles can be stored"
    ),
    UNKNOWN: "the database did not answer whether user_profiles is there; profile writes are refused",
}


def _table_warrant() -> str:
    """「画像表由 PG 服务」这句声称拿什么背书：生产环境现查那张表，其余一字不改。

    为什么只有生产去问：开发态的画像写在同一个库里，表由 `_ensure()` 在第一次写时建起来；那三张脸
    （开发 / 裸机 / 离线）各有既有的钉，本单不碰。生产恰恰相反——那里没有任何东西会替谁建表，
    「旗标说就绪」与「这张表在」之间只隔着一次没跑完的迁移，所以只有那一格需要一句现查。
    """
    if not _is_production_environment():
        return PRESENT
    return probe_table(_conn, "user_profiles")


def profile_storage_state() -> dict:
    """Report where user profiles are actually stored.

    R392 治的是这一格。`_database_available()` 回答的是「这个进程连得上 PostgreSQL」：它读的是
    `app/common/auth.py` 那枚 `_db_ready`，而那枚旗标的凭据是 `users` 表的现查，一步都没查过
    `user_profiles`。于是在「生产 + 旗标为真 + 迁移没跑全」这一格上，健康报答「user_profiles 由 PG
    服务、durable: True」，同一时刻 `PUT /api/v1/profile` 正因为 R383 那道闸答 503
    `storage_unavailable`——一台机器两张嘴对同一格说相反的话，而健康报是客户装机第一眼读的那一张。
    从今天起「声称 postgres / durable」必须拿那次现查当凭据；问不出来就照问不出来的样子说，既不
    说在，也不假装不在。
    """
    if _database_available():
        warrant = _table_warrant()
        if warrant == PRESENT:
            return {
                "storage_mode": "postgres",
                "durable": True,
                "shared_across_processes": True,
                "protection": "none",
                "detail": "user_profiles table served by PostgreSQL",
            }
        return {
            "storage_mode": "unavailable",
            "durable": False,
            "shared_across_processes": False,
            "protection": "read_only",
            "detail": UNWARRANTED_DETAILS[warrant],
        }
    if _is_production_environment():
        return {
            "storage_mode": "unavailable",
            "durable": False,
            "shared_across_processes": False,
            "protection": "read_only",
            "detail": "user database is unavailable; profile writes are refused",
        }
    return {
        "storage_mode": "memory",
        "durable": False,
        "shared_across_processes": False,
        "protection": "none",
        "detail": "development in-process dictionary",
    }


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as conn:
        if _is_production_environment():
            row = conn.execute("SELECT to_regclass('public.user_profiles') AS table_name").fetchone()
            if not row or row["table_name"] is None:
                raise RuntimeError("user_profiles table is required in production; run migrations first")
            _initialized = True
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                department TEXT,
                position TEXT,
                preferences JSON,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    _initialized = True


#: 「该由 migrations 建的那枚表不在」在本模块只有一句话术：``_ensure`` 生产分支那一句。判定只认
#: 它的前缀，不认「任何异常」——把宽捕获整体翻成拒答等于替真正的 bug 打掩护（同 R371 的裁定）。
MIGRATION_REQUIRED_PREFIX = "user_profiles table is required in production"
#: 排查路径：两张脸共用出口那一侧已有的 503 ``storage_unavailable``（零新增错误码），能把它们
#: 分辨开的只有下面那两行日志。
MIGRATION_REQUIRED_HINT = "migrations/0003_legacy_runtime_tables.sql"


class ProfileStoreUnavailable(RuntimeError):
    """画像存储拒答。这不等于「画像存不下」，更不等于「这家公司没有画像」。

    形状照 ``app/common/auth.py::UserStoreUnavailable``（R356）：判定留在存储层，出口那一侧只做
    一次窄翻译。存储层自己一枚 HTTP 异常都不发起，那是出口的活儿（同 R376 的裁定）。
    """


def _schema_needs_migrations(exc: BaseException) -> bool:
    """这枚异常是不是「画像表还没建」：只认 ``_ensure`` 抛出的那一句前缀，其余一概不认。"""
    return str(exc).startswith(MIGRATION_REQUIRED_PREFIX)


def require_ready_store(operation: str, *, migrations_missing: bool = False) -> None:
    """生产环境 + 画像存储未就绪 = 这一格拒答，不许悄悄回一句「保存失败」。

    判的两件事都是本模块既有的读数，一枚都不新造：库在不在取 ``_database_available()``（:39，
    本模块唯一那枚 ``_db_ready`` 读者，总数由 ``tests/test_r246_honest_readiness_claims.py`` 按
    AST 管着），是不是生产取 ``_is_production_environment()``（:44，与
    ``app/api/v1/alerts.py:61`` 同一把尺）。两支同时成立才拒。

    ``migrations_missing`` 是同一道门上的第二种「没就绪」：库连着、旗标也在 True，可 ``_ensure()``
    已经现查到 ``user_profiles`` 不在。R383 之前这两格在出口答的是同一句 ``画像保存失败`` + 500，
    而「存储没迁移」与「存储没起」是两条完全不同的排查路（一条跑 migrations/0003，一条查
    DATABASE_URL 与 PG 进程），一句话盖住两张脸就是本单要修的病灶。

    开发/裸机/离线那一支一个字都不改：``_database_available()`` 为假且不是生产时，画像照旧落
    ``_MEM_PROFILES`` 并答 ``True``，``PUT /api/v1/profile`` 照旧 200。
    """
    if (_database_available() and not migrations_missing) or not _is_production_environment():
        return
    if migrations_missing:
        logger.warning(
            f"[Profile] 生产库缺该由迁移建的画像表，这一格拒答而不是回一句保存失败: operation={operation} "
            f"code=storage_unavailable migration={MIGRATION_REQUIRED_HINT}"
        )
    else:
        logger.warning(
            f"[Profile] 生产环境画像存储没起，这一格拒答而不是回一句保存失败: operation={operation} "
            "code=storage_unavailable（PG 未起）"
        )
    raise ProfileStoreUnavailable(operation)

#: R296：``users`` 那一行是部门归属的唯一事实源（``Principal`` 也是从它造的，见
#: ``app/agents/contracts.py`` 的 ``Principal.from_user``）。``user_profiles.department``
#: 是历史留下的第二份真相：员工曾经经 ``PUT /api/v1/profile`` 自助写它，而它又会**盖住** ``users``
#: 的权威值。从今天起读路径不再取它、写路径不再喂它；表里已经存下的旧值一个字都不动（本单不删数据），
#: 清理口径写在 ``docs/api/contract-v1.md`` 的 R296 一节，由业主决定。
LEGACY_DEPARTMENT_FIELD = "department"


def _without_legacy_department(stored: dict) -> dict:
    """剥掉画像存储里那列遗留的部门，其余字段照旧返回。

    做成两条读腿共用的一枚函数，而不是只在 SELECT 里少写一列：PG 那一支靠不选它，内存那一支靠丢键，
    共用同一条口径，旧值才不会从另一条腿漏回画像与 prompt。
    """
    return {key: value for key, value in stored.items() if key != LEGACY_DEPARTMENT_FIELD}


def get_profile(user_id: str, fallback: dict | None = None) -> dict:
    """读画像；返回里的 ``department`` 只可能来自 ``fallback``。

    ``fallback`` 是调用方从 ``users`` 现取的那一行（``app/api/v1/auth.py`` 的 GET 走
    ``auth.get_user``，``app/agents/nodes.py`` 的 load_memory 走同一张表），不是画像存储里的值。
    ``user_profiles`` 那一列遗留值一个字都不进返回值。
    """
    profile = dict(fallback or {})
    if not _database_available():
        profile.update(_without_legacy_department(_MEM_PROFILES.get(user_id, {})))
        return profile
    try:
        _ensure()
        with _conn() as conn:
            row = conn.execute(
                "SELECT position, preferences, updated_at FROM user_profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if row:
            stored = _without_legacy_department(dict(row))
            if stored.get("preferences"):
                stored["preferences"] = json.loads(stored["preferences"])
            profile.update({k: v for k, v in stored.items() if v not in (None, "")})
    except Exception as exc:
        logger.warning(f"[Profile] load skipped: {exc}")
    return profile


def upsert_profile(user_id: str, department: str = "", position: str = "", preferences: list | None = None) -> bool:
    """存画像。``department`` 是遗留参数，本函数不再把它写进任何存储。

    为什么留着参数而不同时删掉：生产调用点只有 ``PUT /api/v1/profile``，而它从今天起对带
    ``department`` 的请求整发拒（R296 判据②），值永远到不了这里；真有人往这格塞非空值就只落一行
    警告——既不静默，也不逼内部调用点在一次改动里同时长两处。

    表里已经存下的旧值既不覆盖也不清空：覆盖等于替业主删数据，继续喂又会长回第二份真相，所以这一列
    今天的准确说法是「没人写、也没人读」。清理它属于数据迁移，归业主。
    """
    if department:
        logger.warning("[Profile] department is no longer stored (R296): users holds the authoritative value")
    if not _database_available() and _is_production_environment():
        logger.error(
            "[Profile] production profile store is not durable; write refused "
            "(set DATABASE_URL and run migrations)"
        )
        return False
    if not _database_available():
        # 内存表与 PG 那一支同口径：department 不进存储（R296）。
        _MEM_PROFILES[user_id] = {
            "position": position,
            "preferences": list(preferences or []),
            "updated_at": datetime.now(_tz).isoformat(),
        }
        return True
    try:
        _ensure()
        now = datetime.now(_tz).isoformat()
        payload = json.dumps(preferences or [], ensure_ascii=False)
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, position, preferences, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET position = EXCLUDED.position,
                    preferences = EXCLUDED.preferences,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, position or None, payload, now),
            )
            conn.commit()
        return True
    except Exception as exc:
        if _schema_needs_migrations(exc):
            require_ready_store("profile write", migrations_missing=True)
        logger.warning(f"[Profile] save failed: {exc}")
        return False
