"""Built-in OCR engine adapters.

Only the stub is used by the test suite and neither adapter is registered by
default: production must explicitly select an engine, otherwise OCR reports a
clear "no engine configured" failure instead of silently inventing text.
"""
from __future__ import annotations

from app.rag.ocr.base import OcrEngineError, OcrPageResult
from app.rag.ocr.registry import OcrEngineUnavailable


class StubOcrEngine:
    """Deterministic, offline test double.  Never use it in production.

    It returns the supplied ``default_text`` for every page unless
    ``page_texts`` maps a page number to a different string, which lets tests
    exercise empty pages, low confidence and per-page variation without any
    model or network access.
    """

    name = "stub"

    def __init__(
        self,
        default_text: str = "stub ocr text",
        confidence: float | None = 0.95,
        page_texts: dict[int, str] | None = None,
    ) -> None:
        self.default_text = default_text
        self.confidence = confidence
        self.page_texts = dict(page_texts or {})

    def recognize(self, image: bytes, page: int) -> OcrPageResult:
        return OcrPageResult(
            page=page,
            text=self.page_texts.get(page, self.default_text),
            confidence=self.confidence,
            engine=self.name,
        )


class TesseractOcrEngine:
    """Optional adapter around the Tesseract command-line OCR engine.

    This adapter is the documented example of plugging a real engine into the
    registry.  It imports ``pytesseract`` and ``PIL`` lazily and raises
    :class:`OcrEngineUnavailable` with deployment instructions when either is
    missing, so importing this module never fails on a machine without OCR.
    """

    name = "tesseract"

    def __init__(self, lang: str = "eng", tesseract_cmd: str | None = None) -> None:
        self.lang = lang
        self.tesseract_cmd = tesseract_cmd

    def _require_tesseract(self):
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
        except ImportError as exc:
            raise OcrEngineUnavailable(
                "tesseract adapter needs 'pytesseract' and 'Pillow'; install them "
                "offline and provide a local Tesseract binary + language data"
            ) from exc
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        return pytesseract, Image

    def recognize(self, image: bytes, page: int) -> OcrPageResult:
        pytesseract, Image = self._require_tesseract()
        try:
            from io import BytesIO

            pil_image = Image.open(BytesIO(image))
            text = pytesseract.image_to_string(pil_image, lang=self.lang)
            confidence = self._mean_confidence(pytesseract, pil_image)
        except Exception as exc:  # tesseract raises many OS-level error types
            raise OcrEngineError(
                page,
                f"tesseract failed: {exc}",
                code="ocr_tesseract_failed",
                retryable=False,
            ) from exc
        return OcrPageResult(page=page, text=text or "", confidence=confidence, engine=self.name)

    @staticmethod
    def _mean_confidence(pytesseract, image) -> float | None:
        """Mean word confidence when the engine exposes it, else ``None``."""
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            values = [int(v) for v in data.get("conf", []) if str(v).strip() not in ("", "-1")]
            return sum(values) / len(values) if values else None
        except Exception:
            return None
