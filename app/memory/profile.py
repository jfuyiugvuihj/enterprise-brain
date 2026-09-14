import json
import os
import sys
from datetime import datetime, timedelta, timezone

from app.common.logger import logger

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


def get_profile(user_id: str, fallback: dict | None = None) -> dict:
    profile = dict(fallback or {})
    if not _database_available():
        profile.update(_MEM_PROFILES.get(user_id, {}))
        return profile
    try:
        _ensure()
        with _conn() as conn:
            row = conn.execute(
                "SELECT department, position, preferences, updated_at FROM user_profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if row:
            stored = dict(row)
            if stored.get("preferences"):
                stored["preferences"] = json.loads(stored["preferences"])
            profile.update({k: v for k, v in stored.items() if v not in (None, "")})
    except Exception as exc:
        logger.warning(f"[Profile] load skipped: {exc}")
    return profile


def upsert_profile(user_id: str, department: str = "", position: str = "", preferences: list | None = None) -> bool:
    if not _database_available():
        _MEM_PROFILES[user_id] = {
            "department": department,
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
                INSERT INTO user_profiles (user_id, department, position, preferences, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET department = EXCLUDED.department,
                    position = EXCLUDED.position,
                    preferences = EXCLUDED.preferences,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, department or None, position or None, payload, now),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning(f"[Profile] save failed: {exc}")
        return False
