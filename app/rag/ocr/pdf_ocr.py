"""Orchestrate OCR over the scanned pages of one PDF.

The orchestrator is what turns an engine into parse blocks: it requests each
scanned page's rendered image, calls the engine, and records page number,
confidence and failure state per block.  Rendering is injected so this module
never depends on a PDF rasteriser (poppler / pypdfium2) at import time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from app.rag.parser_result import (
    BlockType,
    ContentBlock,
    ParseError,
    ParseStatus,
    ParserType,
    SourceLocation,
)
from app.rag.ocr.base import OcrEngineError, OcrPageResult
from app.rag.ocr.detect import scanned_pages

PageRenderer = Callable[[int], bytes]


def _block(page: int, source: str, *, content: str, confidence: float | None, errors: tuple[ParseError, ...]) -> ContentBlock:
    return ContentBlock(
        block_type=BlockType.OCR,
        parser_type=ParserType.OCR,
        content=content,
        location=SourceLocation(file_path=source, page=page),
        confidence=confidence,
        errors=errors,
    )


def _error(page: int, code: str, message: str, *, retryable: bool = False) -> ParseError:
    return ParseError(
        code=code,
        message=message,
        parser=ParserType.OCR,
        location=SourceLocation(file_path="", page=page),
        retryable=retryable,
    )


@dataclass(frozen=True)
class OcrRun:
    """The aggregate OCR result for a document.

    ``status`` never collapses failure into success: a page whose engine raised,
    produced no text, or fell below the confidence threshold keeps an error on
    its block, and the run reflects that as ``partial_success`` or ``failed``.
    """

    pages_requested: tuple[int, ...]
    blocks: tuple[ContentBlock, ...]
    status: ParseStatus
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "pages_requested": list(self.pages_requested),
            "blocks": [block.as_dict() for block in self.blocks],
            "status": self.status.value,
            "warnings": list(self.warnings),
        }


def classify_ocr_status(blocks: Iterable[ContentBlock]) -> ParseStatus:
    block_list = tuple(blocks)
    if not block_list:
        return ParseStatus.EMPTY
    has_content = any(block.content.strip() for block in block_list)
    has_errors = any(block.errors for block in block_list)
    if has_errors and not has_content:
        return ParseStatus.FAILED
    if has_errors:
        return ParseStatus.PARTIAL_SUCCESS
    return ParseStatus.SUCCESS


def ocr_scanned_pages(
    reader: object,
    engine: object,
    render_page: PageRenderer,
    *,
    source: str = "",
    pages: Iterable[int] | None = None,
    confidence_threshold: float | None = None,
) -> OcrRun:
    """OCR the scanned pages of ``reader`` and return structured blocks.

    ``pages`` overrides detection (1-based).  ``confidence_threshold``, when
    set, marks low-confidence pages with ``ocr_low_confidence`` without
    discarding their text, so a human can review instead of silently losing it.
    """
    page_numbers = tuple(pages) if pages is not None else scanned_pages(reader)
    blocks: list[ContentBlock] = []
    warnings: list[str] = []

    for page_number in page_numbers:
        try:
            image = render_page(page_number)
        except Exception as exc:
            blocks.append(
                _block(
                    page_number,
                    source,
                    content="",
                    confidence=None,
                    errors=(
                        _error(page_number, "ocr_render_failed", f"page render failed: {exc}"),
                    ),
                )
            )
            continue

        try:
            result: OcrPageResult = engine.recognize(image, page_number)
        except OcrEngineError as exc:
            blocks.append(
                _block(
                    page_number,
                    source,
                    content="",
                    confidence=None,
                    errors=(_error(page_number, exc.code, exc.message, retryable=exc.retryable),),
                )
            )
            continue
        except Exception as exc:
            blocks.append(
                _block(
                    page_number,
                    source,
                    content="",
                    confidence=None,
                    errors=(_error(page_number, "ocr_engine_error", f"OCR engine failed: {exc}"),),
                )
            )
            continue

        text = (result.text or "").strip()
        if not text:
            blocks.append(
                _block(
                    page_number,
                    source,
                    content="",
                    confidence=result.confidence,
                    errors=(_error(page_number, "ocr_empty_page", "OCR returned no text for this page"),),
                )
            )
            warnings.append(f"page {page_number}: OCR returned no text")
            continue

        if confidence_threshold is not None and result.confidence is not None and result.confidence < confidence_threshold:
            blocks.append(
                _block(
                    page_number,
                    source,
                    content=text,
                    confidence=result.confidence,
                    errors=(
                        _error(
                            page_number,
                            "ocr_low_confidence",
                            f"confidence {result.confidence} below threshold {confidence_threshold}",
                        ),
                    ),
                )
            )
            warnings.append(f"page {page_number}: OCR confidence below threshold")
            continue

        blocks.append(
            _block(
                page_number,
                source,
                content=text,
                confidence=result.confidence,
                errors=(),
            )
        )

    return OcrRun(
        pages_requested=page_numbers,
        blocks=tuple(blocks),
        status=classify_ocr_status(blocks),
        warnings=tuple(warnings),
    )
