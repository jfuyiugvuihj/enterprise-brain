"""JWT 鉴权 — PostgreSQL 管理账号，config.yaml 仅存 JWT 密钥"""
import os
import secrets
import jwt
import bcrypt
import yaml
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timezone, timedelta
from fastapi import Request
from app.common.logger import logger

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
# S1: 密钥优先读环境变量 JWT_SECRET；config.yaml 仅作向后兼容回退
_SECRET = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY") or _auth_cfg.get("jwt_secret") or "dev-secret-change-me"
_EXPIRE_HOURS = _auth_cfg.get("token_expire_hours", 24)

PUBLIC_PATHS = {"/", "/docs", "/openapi.json", "/redoc", "/api/v1/login", "/api/v1/health"}


def _raw_conn():
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _create_schema(conn):
    """建用户表 + 阶段2 列 + 默认管理员（在给定连接上执行）"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
        )
    """)
    # 阶段 2：补 department/role 列（已有库自动迁移）
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS department TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'staff'")
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        # S2: 首次启动生成随机 admin 密码并打印到日志，强制修改
        initial_password = secrets.token_urlsafe(12)
        hsh = bcrypt.hashpw(initial_password.encode(), bcrypt.gensalt()).decode()
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", ("admin", hsh, "admin"))
        conn.commit()
        logger.warning(f"[安全] 初始 admin 密码: {initial_password} （登录后请立即修改）")


_db_ready = False
try:
    _c = _raw_conn()
    _create_schema(_c)
    _c.close()
    _db_ready = True
except Exception as _e:
    logger.warning(f"[Auth] Postgres 暂不可用，将在首次连接时建表: {_e}")


def _get_conn():
    """导入不硬依赖库；首次成功连接时懒建表"""
    global _db_ready
    conn = _raw_conn()
    if not _db_ready:
        try:
            _create_schema(conn)
            _db_ready = True
        except Exception:
            pass
    return conn


def verify_password(username: str, password: str) -> bool:
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
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# ====== 用户管理 CRUD ======

def list_users() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT id, username, created_at FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def create_user(username: str, password: str, role: str = "staff",
                department: str | None = None) -> tuple[bool, str]:
    if not username or not password:
        return False, "用户名和密码不能为空"
    if len(password) < 6:
        return False, "密码至少 6 位"
    if role not in ("staff", "manager", "admin"):
        return False, f"非法角色: {role}"
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
    """返回 {username, role, department}，不存在返回 None"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT username, role, department FROM users WHERE username = %s",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def delete_user(user_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return cur.rowcount > 0


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    if not verify_password(username, old_password):
        return False, "原密码错误"
    if len(new_password) < 6:
        return False, "新密码至少 6 位"
    with _get_conn() as conn:
        hsh = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password_hash = %s WHERE username = %s", (hsh, username))
        conn.commit()
    return True, "密码已更新"
