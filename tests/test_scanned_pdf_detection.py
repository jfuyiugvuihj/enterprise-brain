"""Scanned-page detection over pypdf.

The detection unit uses duck-typed pages so the rule itself is tested without
needing a rasteriser, and two real pypdf reads over fpdf2-generated PDFs prove
the integration end-to-end: a text page is never sent to OCR and an image-only
page always is.
"""
from pypdf import PdfReader

from app.rag.ocr.detect import (
    page_has_extractable_text,
    page_has_images,
    page_requires_ocr,
    scanned_pages,
)


def _write_pdf(path, *, text: str | None = None, with_image: bool = False):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    if text:
        pdf.set_font("Helvetica", size=12)
        pdf.cell(text=text)
    if with_image:
        from io import BytesIO

        from PIL import Image

        image = Image.new("RGB", (4, 4), (255, 255, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        pdf.image(buffer, x=0, y=0, w=10, h=10)
    pdf.output(str(path))


class _FakePage:
    def __init__(self, text: str = "", images=()):
        self._text = text
        self._images = list(images)

    def extract_text(self):
        return self._text

    @property
    def images(self):
        return self._images


class _FakeReader:
    def __init__(self, pages):
        self.pages = pages


def test_text_page_has_extractable_text_and_no_images():
    page = _FakePage("revenue grew 12%", images=[])
    assert page_has_extractable_text(page)
    assert not page_has_images(page)
    assert not page_requires_ocr(page)


def test_image_only_page_requires_ocr():
    page = _FakePage("", images=["image-object"])
    assert not page_has_extractable_text(page)
    assert page_has_images(page)
    assert page_requires_ocr(page)


def test_blank_page_is_not_routed_to_ocr():
    page = _FakePage("", images=[])
    assert not page_has_extractable_text(page)
    assert not page_has_images(page)
    assert not page_requires_ocr(page)


def test_scanned_pages_reports_one_based_page_numbers():
    reader = _FakeReader([_FakePage("text"), _FakePage("", images=["img"]), _FakePage("", images=["img"])])
    assert scanned_pages(reader) == (2, 3)


def test_text_pdf_has_no_scanned_pages(tmp_path):
    path = tmp_path / "text.pdf"
    _write_pdf(path, text="hello world")
    assert scanned_pages(PdfReader(str(path))) == ()


def test_image_only_pdf_has_one_scanned_page(tmp_path):
    path = tmp_path / "image.pdf"
    _write_pdf(path, with_image=True)
    assert scanned_pages(PdfReader(str(path))) == (1,)
