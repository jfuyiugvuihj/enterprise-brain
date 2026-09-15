"""JWT auth and user management with PostgreSQL fallback."""
import os
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
        "department": "",
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


def _memory_store_denied(operation: str) -> bool:
    """Refuse to authenticate against a process-local user table in production.

    Login is a write path (user creation, SSO sync, password change), so there is no
    read-only form of this store: two workers would disagree about who exists. Every
    caller keeps its previous default-deny behaviour when this returns True.
    """
    if not (_is_production_environment() and _using_memory_store()):
        return False
    logger.error(
        f"[Auth] production user store is not durable; refused {operation} "
        "(set DATABASE_URL and run migrations)"
    )
    return True


def _raw_conn():
    if psycopg is None:
        raise RuntimeError("psycopg unavailable")
    return psycopg.connect(_PG_URL, row_factory=dict_row)


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
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) "
        "ON CONFLICT (username) DO NOTHING",
        (username, password_hash, "admin"),
    )
    conn.commit()
    logger.info("[Security] Initial admin account created from configured bootstrap credentials")


_db_ready = False
if psycopg is not None:
    try:
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
    conn = _raw_conn()
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
