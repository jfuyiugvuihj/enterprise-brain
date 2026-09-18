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
    # R21: the embedding model is a second, separately pinned model, and its absence is
    # invisible to every other check here -- a registry that never served nomic-embed-text
    # still answers /api/tags with 200. ``is False`` only fires when the registry was
    # actually read and the model was not in it; "nobody looked" stays silent, because an
    # unprobed registry is not evidence of a missing model.
    if dependencies.get("ollama", {}).get("embedding_model_present") is False:
        problems.append("embedding_model_missing")
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
    from app.common.model_config import get_local_model_settings, inference_compute_state

    settings = get_local_model_settings()
    # R26b: the compute verdict rides with the model so /health/details can tell "the
    # model is slow" apart from "this machine never used its GPU". It is read from the
    # last observation the production discovery path recorded -- no probe is issued here,
    # because a health poll must not stampede the local model server. ``unknown`` covers
    # both "nobody has probed yet" and "the probe could not see the device".
    compute = inference_compute_state()
    return {
        "base_url": settings.base_url,
        "name": settings.model_name or None,
        "source": settings.model_source,
        "inference_compute": compute["kind"],
        "inference_compute_detail": compute["detail"],
        "inference_compute_error_code": compute["error_code"],
        "inference_compute_age_seconds": compute["age_seconds"],
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
        "embedding": _embedding_state(),
        "hot_index": _hot_index_state(),
        "problems": problems,
    }


def _hot_index_state() -> dict:
    """R44 热集的进程内观测块（R79 判据①）：关没关、命中多少、为什么绕行。

    读的是 app/rag/hot_index.py 的 hot_index_snapshot()，不是那份被 R44 用例钉成
    五个键精确相等的 hot_index_diagnostics() —— 配置态与实例态塞不进被钉死的形状。
    与 _embedding_state() 同两条纪律：一，只读内存计数，为了解释自己绝不开 socket、
    绝不读向量库；二，刻意不并进 problems —— 上一轮绕行原因码不是当下故障，
    一次健康巡检因为"热集在冷却"就变红是假警报。
    """
    try:
        from app.rag.hot_index import hot_index_snapshot

        return dict(hot_index_snapshot() or {})
    except Exception:  # noqa: BLE001 - 一层加速缓存读不到，不许把健康报告问出异常
        # 分不清"没装"还是"关了"的时候，宁可报读不到，也不替运维猜一个 False。
        return {"enabled": None, "state_error": "unavailable"}


def _embedding_state() -> dict:
    """Last embedding failure cause and counters, read from the retriever in process.

    This answers "why is the vector leg down" for /health/details without opening a
    socket -- a health poll must never reach the model server to explain itself. It is
    deliberately NOT folded into ``problems``: a failure from earlier in the process
    lifetime is not a current outage, and the code that belongs in ``problems``
    (embedding_model_missing) comes from the registry probe instead.
    """
    try:
        from app.rag.retriever import embedding_diagnostics

        return dict(embedding_diagnostics() or {})
    except Exception:  # noqa: BLE001 - a broken retriever must not break the report
        return {}


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


def _embedding_model_name() -> str:
    """The embedding model the vector leg will actually call, or "" when unknowable.

    ``app/rag/retriever.py`` owns that name, so it is read from there rather than copied
    into this file: a second literal would keep reporting green after somebody re-points
    the model. The import is lazy and failure-tolerant -- an unreadable constant means
    "unknown", never "missing" -- and it opens no socket.
    """
    try:
        from app.rag.retriever import EMBED_MODEL
    except Exception:  # noqa: BLE001 - a broken import must not break the health report
        return ""
    return str(EMBED_MODEL or "").strip()


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
            # R21: the embedding model is answered from the registry this probe already
            # read, so the check costs no extra request -- a health poll must not
            # stampede the local model server, and must not open a socket for a name.
            embedding_model = _embedding_model_name()
            if embedding_model:
                probe["embedding_model"] = embedding_model
                probe["embedding_model_present"] = any(
                    _model_tags_match(embedding_model, name) for name in registered
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
