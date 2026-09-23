"""Scanned / image-page detection on top of pypdf.

The rule is deliberately conservative: a page is only routed to OCR when it has
no extractable text *and* contains at least one image.  A genuinely blank page
(no text, no image) stays empty rather than being sent to an OCR engine that
would spend CPU to return nothing.
"""
from __future__ import annotations

from typing import Any, Iterable


def page_has_extractable_text(page: Any) -> bool:
    try:
        text = page.extract_text() or ""
    except Exception:
        return False
    return bool(text.strip())


def page_has_images(page: Any) -> bool:
    images = getattr(page, "images", None)
    if images is not None:
        return bool(images)
    resources = page.get("/Resources", {}) if hasattr(page, "get") else {}
    xobjects = resources.get("/XObject", {}) if isinstance(resources, dict) else {}
    return any(
        isinstance(value, dict) and value.get("/Subtype") == "/Image"
        for value in xobjects.values()
    )


def page_requires_ocr(page: Any) -> bool:
    return (not page_has_extractable_text(page)) and page_has_images(page)


def scanned_pages(reader: Any) -> tuple[int, ...]:
    """1-based page numbers that need OCR."""
    pages = getattr(reader, "pages", ())
    return tuple(
        number
        for number, page in enumerate(pages, start=1)
        if page_requires_ocr(page)
    )


def has_scanned_pages(reader: Any) -> bool:
    return bool(scanned_pages(reader))
