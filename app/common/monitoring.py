import os
import shutil
import time
from pathlib import Path
from urllib.request import urlopen


def _model_snapshot() -> dict:
    """Report the model the routing boundary will actually use, or none."""
    from app.common.model_config import get_local_model_settings

    settings = get_local_model_settings()
    return {
        "base_url": settings.base_url,
        "name": settings.model_name or None,
        "source": settings.model_source,
    }


def build_health_snapshot(performance: dict | None = None) -> dict:
    usage = shutil.disk_usage(Path.cwd())
    return {
        "status": "ok",
        "timestamp": time.time(),
        "disk": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "model": _model_snapshot(),
        "queue": {
            "backend": "redis" if os.getenv("REDIS_URL") else "memory",
        },
        "dependencies": _dependency_snapshot(),
        "performance": performance or {},
    }


def _probe_ollama() -> dict:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urlopen(f"{base_url}/api/tags", timeout=1) as response:
            return {"status": "ok" if response.status == 200 else "unavailable"}
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def _probe_postgres() -> dict:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return {"status": "not_configured"}
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=1) as conn:
            vector = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            ).fetchone()[0]
            ledger = conn.execute(
                "SELECT to_regclass('public.schema_migrations')"
            ).fetchone()[0]
        return {
            "status": "ok" if vector and ledger else "degraded",
            "pgvector": bool(vector),
            "migration_ledger": bool(ledger),
        }
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def _probe_redis() -> dict:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return {"status": "not_configured"}
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def _dependency_snapshot() -> dict:
    return {
        "ollama": _probe_ollama(),
        "postgres": _probe_postgres(),
        "redis": _probe_redis(),
    }
