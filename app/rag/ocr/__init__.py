"""OCR adapter layer for the V2 file-parsing line.

The package deliberately contains no real OCR engine and downloads nothing.
It defines the :class:`OcrEngine` contract, a registry so an engine can be
swapped without touching upload/indexing code, a deterministic offline stub
for tests, scanned-page detection, and an orchestrator that turns OCR output
into :class:`ContentBlock` objects with page, confidence and failure state.
"""
from app.rag.ocr.base import OcrEngineError, OcrPageResult
from app.rag.ocr.engines import StubOcrEngine, TesseractOcrEngine
from app.rag.ocr.registry import (
    OcrEngineUnavailable,
    available_engines,
    get_engine,
    register_engine,
)
from app.rag.ocr.detect import (
    has_scanned_pages,
    page_has_extractable_text,
    page_has_images,
    page_requires_ocr,
    scanned_pages,
)
from app.rag.ocr.pdf_ocr import OcrRun, ocr_scanned_pages

__all__ = [
    "OcrEngineError",
    "OcrPageResult",
    "StubOcrEngine",
    "TesseractOcrEngine",
    "OcrEngineUnavailable",
    "available_engines",
    "get_engine",
    "register_engine",
    "has_scanned_pages",
    "page_has_extractable_text",
    "page_has_images",
    "page_requires_ocr",
    "scanned_pages",
    "OcrRun",
    "ocr_scanned_pages",
]
