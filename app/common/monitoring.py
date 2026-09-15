"""Runtime health aggregation plus the production storage guard.

Each durable subsystem reports the store it is *actually* using, so an operator never
sees a green health check while enterprise state lives in a process-local dictionary.
"""
import json
import os
import shutil
import time
from pathlib import Path
from urllib.request import urlopen

_PRODUCTION_ENVIRONMENTS = {"production", "prod"}

# name -> (module, function returning that subsystem storage state)
_STORAGE_SUBSYSTEMS = (
    ("users", "app.common.auth", "user_storage_state"),
    ("memories", "app.memory.long_term", "memory_storage_state"),
    ("user_profiles", "app.memory.profile", "profile_storage_state"),
    ("knowledge_graph", "app.knowledge_graph.service", "knowledge_graph_storage_state"),
    ("open_platform_apps", "app.common.open_platform", "app_registry_storage_state"),
)

# Subsystems whose non-durable state is writable in development but blocked in
# production, where a restart or a second worker instance would silently lose it.
_WRITE_GATED_SUBSYSTEMS = ("memories", "user_profiles", "knowledge_graph", "open_platform_apps")


class ProductionReadOnlyProtection(RuntimeError):
    """A write was attempted while the subsystem had no durable store to accept it."""


def is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _unavailable_state(detail: str) -> dict:
    return {
        "storage_mode": "unavailable",
        "durable": False,
        "shared_across_processes": False,
        "protection": "read_only",
        "detail": detail,
    }


def _subsystem_state(module_path: str, function_name: str) -> dict:
    """Read one subsystem state without ever failing a health request."""
    try:
        import importlib

        return dict(getattr(importlib.import_module(module_path), function_name)())
    except Exception as exc:  # pragma: no cover - defensive for a monitoring surface
        return _unavailable_state(f"status_probe_failed: {type(exc).__name__}")


def queue_storage_state() -> dict:
    """The reliable queue only exists with Redis; there was never a memory queue."""
    configured = bool(os.getenv("REDIS_URL", "").strip())
    return {
        "storage_mode": "redis" if configured else "unavailable",
        "durable": configured,
        "shared_across_processes": configured,
        "protection": "none" if configured else "disabled",
        "backend": "redis" if configured else "none",
        "detail": "REDIS_URL configured" if configured else "REDIS_URL is required for the reliable queue",
    }


def storage_snapshot() -> dict:
    """Report every subsystem store truthfully, including the process-local ones."""
    subsystems = {"queue": queue_storage_state()}
    for name, module_path, function_name in _STORAGE_SUBSYSTEMS:
        subsystems[name] = _subsystem_state(module_path, function_name)
    return {
        "subsystems": subsystems,
        "durable": sorted(name for name, state in subsystems.items() if state["durable"]),
        "read_only_protected": sorted(
            name for name, state in subsystems.items() if state["protection"] == "read_only"
        ),
        "refuses_startup": sorted(
            name for name, state in subsystems.items() if state["protection"] == "refuse_start"
        ),
        "single_instance_only": sorted(
            name for name, state in subsystems.items()
            if state["storage_mode"] == "memory" and not state["shared_across_processes"]
        ),
    }


def _health_problems(environment: str, dependencies: dict, storage: dict) -> list[str]:
    """Only production fails closed; development keeps its in-memory conveniences."""
    if environment not in _PRODUCTION_ENVIRONMENTS:
        return []
    subsystems = storage["subsystems"]
    problems: list[str] = []
    if not subsystems["users"]["durable"]:
        problems.append("users_store_not_persistent")
    for name in _WRITE_GATED_SUBSYSTEMS:
        if not subsystems[name]["durable"]:
            problems.append(f"{name}_read_only")
    if subsystems["queue"]["storage_mode"] != "redis":
        problems.append("queue_unavailable")
    for name in ("postgres", "redis", "ollama"):
        status = str(dependencies.get(name, {}).get("status") or "unavailable")
        if status != "ok":
            problems.append(f"{name}_{status}")
    if dependencies.get("ollama", {}).get("model_present") is False:
        problems.append("model_not_available")
    return problems


def enforce_production_storage_guard() -> dict:
    """Refuse to serve when identity state cannot be trusted, degrade the rest.

    The user store has no safe read-only form: login writes sessions and user rows, so
    an instance whose users live in a dictionary would authenticate differently per
    worker. It therefore refuses to start. The remaining subsystems only accumulate
    derived state, so they keep serving reads with writes blocked, which is observable
    through ``/health/details`` and reversible without a redeploy.
    """
    storage = storage_snapshot()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    subsystems = storage["subsystems"]
    report = {
        "enforced": is_production_environment(),
        "environment": environment,
        "refused": sorted(
            name for name in subsystems
            if not subsystems[name]["durable"] and subsystems[name]["protection"] == "refuse_start"
        ),
        "read_only": sorted(
            name for name in subsystems
            if not subsystems[name]["durable"] and subsystems[name]["protection"] == "read_only"
        ),
        "disabled": sorted(
            name for name in subsystems
            if not subsystems[name]["durable"] and subsystems[name]["protection"] == "disabled"
        ),
        "subsystems": subsystems,
    }
    if not report["enforced"]:
        return report
    if report["refused"]:
        detail = "; ".join(
            f"{name}={subsystems[name]['storage_mode']} ({subsystems[name]['detail']})"
            for name in report["refused"]
        )
        raise RuntimeError(
            "production storage guard refused startup: "
            f"{detail}; a persistent user store is required (set DATABASE_URL and run migrations)"
        )
    if report["read_only"]:
        from app.common.logger import logger

        logger.warning(
            "[Storage guard] production read-only protection active for: "
            + ", ".join(report["read_only"])
        )
    return report


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
    environment = os.getenv("APP_ENV", "development").strip().lower()
    dependencies = _dependency_snapshot()
    storage = storage_snapshot()
    problems = _health_problems(environment, dependencies, storage)
    return {
        "status": "ok" if not problems else "degraded",
        "environment": environment,
        "timestamp": time.time(),
        "disk": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "model": _model_snapshot(),
        "queue": dict(storage["subsystems"]["queue"]),
        "dependencies": dependencies,
        "performance": performance or {},
        "storage": storage,
        "problems": problems,
    }


def _model_tags_match(configured: str, registered: str) -> bool:
    """Compare a pinned model name with a tag the local server reports."""
    def trim(value: str) -> str:
        value = value.strip().lower()
        return value[: -len(":latest")] if value.endswith(":latest") else value

    left, right = trim(configured), trim(registered)
    if not left or not right:
        return False
    return left == right or left.startswith(right + ":") or right.startswith(left + ":")


def _registered_local_models(payload: dict) -> list[str]:
    return [str(item.get("name") or "") for item in (payload or {}).get("models") or []]


def _probe_ollama() -> dict:
    """Probe the model server, and separately probe whether the pinned model is on it.

    These are two different facts, and only the second one decides whether a request can
    be answered. A server with nothing pulled still answers ``/api/tags`` with 200, while
    every generation request fails and the platform falls back to its offline reply, so
    reporting the endpoint as merely reachable produced a green light over an unusable
    installation.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        with urlopen(f"{base_url}/api/tags", timeout=1) as response:
            if response.status != 200:
                return {"status": "unavailable"}
            try:
                registered = _registered_local_models(json.loads(response.read().decode("utf-8")))
            except Exception:
                return {"status": "ok"}
            probe = {"status": "ok", "model_count": len(registered)}
            configured = (
                os.getenv("LOCAL_MODEL_NAME") or os.getenv("OLLAMA_MODEL") or ""
            ).strip()
            if configured:
                probe["model_present"] = any(
                    _model_tags_match(configured, name) for name in registered
                )
            return probe
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
