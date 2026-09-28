"""OCR adapter and orchestrator failure semantics.

The core guarantee tested here is that OCR never silently degrades into a
normal empty document: an engine error, an empty page and low confidence each
produce a block carrying a stable error code and confidence, and the run status
reflects that instead of reporting success.
"""
import pytest

from app.rag.ocr import OcrEngineUnavailable, get_engine, register_engine
from app.rag.ocr.base import OcrEngineError
from app.rag.ocr.engines import StubOcrEngine
from app.rag.ocr.pdf_ocr import classify_ocr_status, ocr_scanned_pages
from app.rag.parser_result import BlockType, ParseStatus, ParserType


def _render(page: int) -> bytes:
    return b"rendered-page-%d" % page


def test_registry_raises_when_no_engine_configured(monkeypatch):
    import app.rag.ocr.registry as registry

    monkeypatch.setattr(registry, "_ENGINES", {})
    monkeypatch.setattr(registry, "_DEFAULT_NAME", None)
    with pytest.raises(OcrEngineUnavailable):
        registry.get_engine()


def test_registry_can_swap_engines(monkeypatch):
    import app.rag.ocr.registry as registry

    monkeypatch.setattr(registry, "_ENGINES", {})
    monkeypatch.setattr(registry, "_DEFAULT_NAME", None)
    engine = StubOcrEngine(default_text="first")
    register_engine(engine, default=True)
    assert get_engine() is engine
    assert "stub" in registry.available_engines()


def test_success_run_keeps_page_and_confidence():
    engine = StubOcrEngine(page_texts={1: "line one", 2: "line two"}, confidence=0.9)
    run = ocr_scanned_pages(object(), engine, _render, source="scan.pdf", pages=[1, 2])

    assert run.status is ParseStatus.SUCCESS
    assert run.pages_requested == (1, 2)
    assert [block.content for block in run.blocks] == ["line one", "line two"]
    assert all(block.confidence == 0.9 for block in run.blocks)
    assert all(block.block_type is BlockType.OCR for block in run.blocks)
    assert all(block.parser_type is ParserType.OCR for block in run.blocks)
    assert [block.location.page for block in run.blocks] == [1, 2]


def test_engine_error_is_failed_not_silent():
    class BrokenEngine:
        name = "broken"

        def recognize(self, image, page):
            raise OcrEngineError(page, "model missing", code="ocr_model_missing", retryable=False)

    run = ocr_scanned_pages(object(), BrokenEngine(), _render, source="scan.pdf", pages=[1])

    assert run.status is ParseStatus.FAILED
    assert run.blocks[0].content == ""
    assert run.blocks[0].errors[0].code == "ocr_model_missing"


def test_empty_ocr_page_is_reported_not_masked():
    engine = StubOcrEngine(default_text="", confidence=0.5)
    run = ocr_scanned_pages(object(), engine, _render, source="scan.pdf", pages=[1])

    assert run.status is ParseStatus.FAILED
    assert run.blocks[0].errors[0].code == "ocr_empty_page"


def test_low_confidence_is_partial_success_with_warning_and_text_kept():
    engine = StubOcrEngine(default_text="fuzzy", confidence=0.4)
    run = ocr_scanned_pages(
        object(), engine, _render, source="scan.pdf", pages=[1], confidence_threshold=0.8
    )

    assert run.status is ParseStatus.PARTIAL_SUCCESS
    assert run.blocks[0].content == "fuzzy"
    assert run.blocks[0].errors[0].code == "ocr_low_confidence"
    assert run.warnings


def test_mixed_success_and_failure_is_partial_success():
    class MixedEngine:
        name = "mixed"

        def __init__(self):
            self.calls = 0

        def recognize(self, image, page):
            self.calls += 1
            if page == 1:
                from app.rag.ocr.base import OcrPageResult

                return OcrPageResult(page=page, text="good", confidence=0.9, engine=self.name)
            raise OcrEngineError(page, "timeout", code="ocr_timeout", retryable=True)

    run = ocr_scanned_pages(object(), MixedEngine(), _render, source="scan.pdf", pages=[1, 2])
    assert run.status is ParseStatus.PARTIAL_SUCCESS
    assert run.blocks[0].content == "good"
    assert run.blocks[1].errors[0].code == "ocr_timeout"
    assert run.blocks[1].errors[0].retryable is True


def test_classify_status_empty_blocks_is_empty():
    assert classify_ocr_status([]) is ParseStatus.EMPTY
