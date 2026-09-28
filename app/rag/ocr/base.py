"""The OCR engine contract.

An OCR engine is anything with a ``name`` and a ``recognize`` method that maps
rendered page bytes to text plus a confidence value.  Keeping the contract
this small is the point: the upload API and the indexer talk to
:class:`OcrRun`, never to a particular vendor SDK.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OcrPageResult:
    """One page's OCR output.

    ``text`` is the raw recognised string; ``confidence`` is optional and
    engine-defined, so downstream code must treat it as an opaque 0..1 signal
    rather than a calibrated probability.
    """

    page: int
    text: str
    confidence: float | None = None
    engine: str = ""

    def as_dict(self) -> dict:
        payload: dict = {"page": self.page, "text": self.text, "engine": self.engine}
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload


class OcrEngineError(Exception):
    """A recognised, attributable OCR failure.

    ``retryable`` marks transient failures (timeout, engine not warmed up)
    apart from permanent ones (missing model, unsupported image).  Raising this
    instead of a raw ``Exception`` is what lets the orchestrator record a
    stable ``code`` instead of a stack trace.
    """

    def __init__(
        self,
        page: int,
        message: str,
        *,
        code: str = "ocr_engine_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.page = page
        self.message = message
        self.code = code
        self.retryable = retryable


@runtime_checkable
class OcrEngine(Protocol):
    """Minimal engine surface every adapter implements."""

    name: str

    def recognize(self, image: bytes, page: int) -> OcrPageResult:
        """Recognise one rendered page image and return text + confidence."""
        ...
