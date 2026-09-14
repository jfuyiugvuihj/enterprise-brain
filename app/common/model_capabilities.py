"""Offline-testable Ollama model discovery and conservative capability inference."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ModelCapabilities:
    name: str
    chat: bool = False
    embedding: bool = False
    tags: tuple[str, ...] = ()
    size_bytes: int | None = None
    parameter_size: str | None = None
    available: bool = True
    error_code: str | None = None
    error_message: str | None = None


def normalize_model_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("model name is required")
    return value


def infer_capabilities(model: dict[str, Any]) -> ModelCapabilities:
    name = normalize_model_name(str(model.get("name") or model.get("model") or ""))
    details = model.get("details") or {}
    family = " ".join(
        str(value).lower()
        for value in (name, details.get("family"), details.get("families"), details.get("format"))
        if value
    )
    embedding = any(token in family for token in ("embed", "bge", "e5", "gte"))
    chat = not embedding
    tags = tuple(str(tag) for tag in (model.get("tags") or details.get("families") or ()) if tag)
    return ModelCapabilities(
        name=name,
        chat=chat,
        embedding=embedding,
        tags=tags,
        size_bytes=model.get("size"),
        parameter_size=details.get("parameter_size"),
    )


@dataclass
class DiscoveryResult:
    models: list[ModelCapabilities] = field(default_factory=list)
    available: bool = True
    error_code: str | None = None
    error_message: str | None = None

    def for_purpose(self, purpose: str) -> list[ModelCapabilities]:
        if purpose == "chat":
            return [model for model in self.models if model.chat and model.available]
        if purpose in {"embedding", "embeddings"}:
            return [model for model in self.models if model.embedding and model.available]
        raise ValueError("unsupported model purpose")


def discover_ollama_models(
    fetch: Callable[[str], dict[str, Any]],
    base_url: str,
) -> DiscoveryResult:
    """Discover from an injected transport; tests never contact a real Ollama server."""
    url = (base_url or "").rstrip("/") + "/api/tags"
    try:
        payload = fetch(url)
        models = [infer_capabilities(item) for item in (payload.get("models") or [])]
        return DiscoveryResult(models=models)
    except Exception as exc:
        return DiscoveryResult(
            available=False,
            error_code="model_unavailable",
            error_message=str(exc),
        )
