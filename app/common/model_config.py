"""Local model routing configuration.

The first version only manages a model that lives on the customer's own machine. The
model name is either configured explicitly or discovered from the local Ollama registry;
it is never invented, because a fabricated name would advertise a model that may not be
installed.
"""
from dataclasses import dataclass
import json
import os
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_DISCOVERY_CACHE: tuple[float, str, str] | None = None


@dataclass(frozen=True)
class LocalModelSettings:
    base_url: str
    model_name: str
    api_key: str
    model_source: str = "none"


def _normalize_base_url(value: str) -> str:
    base_url = (value or "").strip().rstrip("/")
    if not base_url:
        base_url = _DEFAULT_OLLAMA_BASE_URL

    parsed = urlsplit(base_url)
    if parsed.hostname in {"localhost", "::1"}:
        netloc = f"127.0.0.1:{parsed.port}" if parsed.port else "127.0.0.1"
        base_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    if not base_url.endswith("/v1"):
        base_url += "/v1"
    return base_url


def _native_base_url(base_url: str) -> str:
    """Ollama's registry API is served without the OpenAI-compatible /v1 suffix."""
    trimmed = (base_url or "").strip().rstrip("/")
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return trimmed or _DEFAULT_OLLAMA_BASE_URL


def _fetch_registry(url: str) -> dict:
    timeout = float(os.getenv("OLLAMA_DISCOVERY_TIMEOUT_SECONDS", "1.5"))
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_chat_model(base_url: str, *, fetch: Callable[[str], dict] | None = None) -> str:
    """Return the first chat-capable model registered locally, or an empty string."""
    from app.common.model_capabilities import discover_ollama_models

    result = discover_ollama_models(fetch or _fetch_registry, base_url)
    if not result.available:
        return ""
    try:
        candidates = result.for_purpose("chat")
    except ValueError:
        return ""
    return candidates[0].name if candidates else ""


def _cached_discovery(base_url: str) -> str:
    """Cache discovery so repeated graph construction cannot stampede the local model."""
    global _DISCOVERY_CACHE
    ttl = float(os.getenv("OLLAMA_DISCOVERY_TTL_SECONDS", "60"))
    now = time.monotonic()
    cache = _DISCOVERY_CACHE
    if cache is not None and cache[2] == base_url and now - cache[0] < ttl:
        return cache[1]
    discovered = discover_chat_model(base_url)
    _DISCOVERY_CACHE = (now, discovered, base_url)
    return discovered


def reset_model_discovery_cache() -> None:
    global _DISCOVERY_CACHE
    _DISCOVERY_CACHE = None


def get_local_model_settings(
    *,
    model_name: str | None = None,
    discover: Callable[[str], str] | None = None,
) -> LocalModelSettings:
    """Resolve the internal OpenAI-compatible endpoint and the model to use on it."""
    base_url = _normalize_base_url(
        os.getenv("LOCAL_MODEL_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or _DEFAULT_OLLAMA_BASE_URL
    )
    configured = (
        (os.getenv("LOCAL_MODEL_NAME") or "").strip() or (os.getenv("OLLAMA_MODEL") or "").strip()
    )
    if model_name is not None:
        resolved = model_name.strip()
        source = "configured" if resolved else "none"
    elif configured:
        resolved, source = configured, "configured"
    else:
        resolved = ((discover or _cached_discovery)(_native_base_url(base_url)) or "").strip()
        source = "discovered" if resolved else "none"
    return LocalModelSettings(
        base_url=base_url,
        model_name=resolved,
        api_key=os.getenv("LOCAL_MODEL_API_KEY", "local"),
        model_source=source,
    )