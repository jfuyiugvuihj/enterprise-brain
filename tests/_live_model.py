"""Shared gate for tests that must talk to a live local model.

Like the PostgreSQL and Redis acceptance gates, these tests only run when the operator
opts in *and* the service is actually reachable, so a routine offline run never turns red
because a laptop service happens to be stopped, and a real-model run is always explicit.
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

ENV_FLAG = "EB_OLLAMA_ACCEPTANCE"
_TAG_TIMEOUT_SECONDS = 5


def acceptance_requested() -> bool:
    return os.getenv(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _native(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    return url[: -len("/v1")] if url.endswith("/v1") else url


def registry_models(base_url: str) -> list[str]:
    """Names reported by the local registry, or an empty list when it is unreachable."""
    try:
        with urllib.request.urlopen(_native(base_url) + "/api/tags", timeout=_TAG_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - an unreachable registry is "not available", not an error
        return []
    return [str(item.get("name") or "") for item in payload.get("models", []) if item.get("name")]


def live_chat_model() -> str:
    """Resolve the model the platform would use, but only when the registry answers."""
    from app.common.model_config import get_local_model_settings

    try:
        settings = get_local_model_settings()
    except Exception:  # noqa: BLE001
        return ""
    if not registry_models(settings.base_url):
        return ""
    return settings.model_name


def reason_without_live_model() -> str:
    if not acceptance_requested():
        return f"set {ENV_FLAG}=1 to run the real local-model acceptance tests"
    return f"{ENV_FLAG}=1 is set but no chat model is reachable on the configured Ollama endpoint"


live_model_required = pytest.mark.skipif(
    not acceptance_requested() or not live_chat_model(),
    reason=reason_without_live_model(),
)
