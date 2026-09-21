"""
Unified document loader for PDF / DOCX / DOC / TXT / Markdown.

R130: every loader below ends in :func:`sanitize_text`, because pypdf really does hand
back a NUL character (measured in documents/AI-Agent学习路线图.pdf) and a PostgreSQL
text column cannot hold one.
"""
from pathlib import Path

from pypdf import PdfReader

from app.common.logger import logger

#: U+0000 -- the one character a PostgreSQL ``text`` column refuses, and therefore the
#: one character this module drops. psycopg only complains about it from inside
#: ``executemany``, by which point the batch has no document name left to report, so
#: the drop belongs here, at the edge where a third-party parser stops being our problem.
#: The mirror in app/rag/pg_store.py keeps its own gate for anything arriving by another
#: route: two layers, each doing its own job.
NUL_CHARACTER = "\x00"


def sanitize_text(text: str) -> str:
    """Drop NUL characters and nothing else.

    Deliberately surgical (R130 判据①): whitespace, blank lines, emoji, letter case and
    every other control character belong to the document, so they leave unchanged. A text
    without NUL comes back byte-identical, which is what keeps the already-indexed corpus
    (R130 判据④: 985 chunks, none of them dirty) untouched by this ticket.
    """
    if NUL_CHARACTER not in text:
        return text
    return text.replace(NUL_CHARACTER, "")


def load_pdf(file_path: str) -> str:
    """Extract PDF text locally with pypdf."""
    reader = PdfReader(file_path)
    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text.strip())
    text = sanitize_text("\n\n".join(parts).strip())
    logger.info(f"Loaded PDF with pypdf: {file_path} ({len(text)} chars)")
    return text


def load_docx(file_path: str) -> str:
    """Extract plain text from .docx."""
    from docx import Document

    doc = Document(file_path)
    return sanitize_text("\n".join(p.text for p in doc.paragraphs if p.text.strip()))


def load_doc(file_path: str) -> str:
    """Best-effort extraction for old .doc files."""
    import olefile

    ole = olefile.OleFileIO(file_path)
    if ole.exists("WordDocument"):
        stream = ole.openstream("WordDocument")
        raw = stream.read()
        text = "".join(chr(b) for b in raw if 31 < b < 127 or b in (10, 13))
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 2]
        ole.close()
        return sanitize_text("\n".join(lines))
    ole.close()
    return ""


def load_txt(file_path: str) -> str:
    """Read TXT with automatic encoding detection."""
    for encoding in ["utf-8", "gbk", "gb2312"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return sanitize_text(f.read())
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to detect text encoding: {file_path}")


def load_md(file_path: str) -> str:
    """Read Markdown as plain source text, reusing TXT encoding detection."""
    return sanitize_text(load_txt(file_path))


def load_document(file_path: str) -> str:
    """Auto-detect file type and return plain text."""
    ext = Path(file_path).suffix.lower()
    logger.info(f"Loading document: {file_path} ({ext})")

    if ext == ".pdf":
        return sanitize_text(load_pdf(file_path))
    if ext == ".docx":
        return sanitize_text(load_docx(file_path))
    if ext == ".doc":
        return sanitize_text(load_doc(file_path))
    if ext == ".txt":
        return sanitize_text(load_txt(file_path))
    if ext == ".md":
        return sanitize_text(load_md(file_path))
    raise ValueError(f"Unsupported file format: {ext}")
