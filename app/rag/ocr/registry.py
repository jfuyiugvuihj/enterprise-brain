"""Engine registry that makes the OCR backend replaceable.

No engine is registered automatically.  ``get_engine`` therefore fails with a
stable, explainable error on a fresh process, which is exactly what keeps an
unconfigured deployment from silently returning placeholder OCR text.
"""
from __future__ import annotations

from app.rag.ocr.base import OcrEngine


class OcrEngineUnavailable(RuntimeError):
    """Raised when no engine is configured or the requested one is missing."""


_ENGINES: dict[str, OcrEngine] = {}
_DEFAULT_NAME: str | None = None


def register_engine(engine: OcrEngine, *, default: bool = False) -> None:
    """Register an adapter, optionally making it the default."""
    name = getattr(engine, "name", "") or engine.__class__.__name__
    _ENGINES[name] = engine
    if default or _DEFAULT_NAME is None:
        globals()["_DEFAULT_NAME"] = name


def available_engines() -> tuple[str, ...]:
    return tuple(_ENGINES)


def get_engine(name: str | None = None) -> OcrEngine:
    """Return the named engine, the configured default, or raise."""
    target = name or _DEFAULT_NAME
    if target is None:
        raise OcrEngineUnavailable(
            "no OCR engine configured; register one with register_engine() "
            "before enabling OCR"
        )
    engine = _ENGINES.get(target)
    if engine is None:
        raise OcrEngineUnavailable(f"OCR engine {target!r} is not registered")
    return engine
