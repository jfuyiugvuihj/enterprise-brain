"""Unified parse result contract for the V2 file-parsing line.

Every parser in ``app/rag/loader.py`` (and the new OCR / table / spreadsheet
parsers) eventually reports through these types instead of returning a bare
``str``.  The old ``load_document() -> str`` entry point stays byte-for-byte
compatible; richer callers use :func:`DocumentParseResult` and pick the blocks
they understand, so text extraction, OCR and structured tables can share one
shape without pretending they are the same thing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ParseStatus(str, Enum):
    """What one whole document parse ended up as.

    ``empty`` is deliberately distinct from ``failed``: a file whose pages are
    all genuinely blank is a truthful empty result, while an OCR failure or an
    unsupported table is a failure that must not be silently downgraded to an
    empty document.
    """

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    EMPTY = "empty"
    FAILED = "failed"


class ParserType(str, Enum):
    """Which parser produced a block. Kept explicit so callers never have to guess."""

    PYPDF = "pypdf"
    PYTHON_DOCX = "python_docx"
    OLEFILE = "olefile"
    TEXT_ENCODING = "text_encoding"
    MARKDOWN = "markdown"
    OCR = "ocr"
    PDF_TABLE = "pdf_table"
    DOCX_TABLE = "docx_table"
    EXCEL_KB = "excel_kb"
    CSV_KB = "csv_kb"


class BlockType(str, Enum):
    """The semantic kind of a :class:`ContentBlock`.

    ``table`` keeps row/column structure; ``data_rows`` is the spreadsheet
    knowledge-base import shape (header + rows with a source range); ``text``
    and ``ocr`` are linear text whose only difference is provenance.
    """

    TEXT = "text"
    TABLE = "table"
    OCR = "ocr"
    DATA_ROWS = "data_rows"


@dataclass(frozen=True)
class SourceLocation:
    """Where a block came from, at the granularity the parser actually knows.

    Every field is optional on purpose: pypdf knows a page but not a sheet,
    openpyxl knows a sheet but not a page.  ``row_start`` / ``row_end`` are
    1-based inclusive and ``column_start`` / ``column_end`` are 1-based
    inclusive so humans and the frontend can read them without offset maths.
    """

    file_path: str
    page: int | None = None
    sheet: str | None = None
    table_index: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    section_path: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"file_path": self.file_path}
        for key in (
            "page",
            "sheet",
            "table_index",
            "row_start",
            "row_end",
            "column_start",
            "column_end",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.section_path:
            payload["section_path"] = list(self.section_path)
        return payload

    def label(self) -> str:
        """A short human-readable location, used by the index text renderer."""
        parts: list[str] = []
        if self.sheet:
            parts.append(f"sheet={self.sheet}")
        if self.page is not None:
            parts.append(f"page={self.page}")
        if self.table_index is not None:
            parts.append(f"table={self.table_index}")
        if self.section_path:
            parts.append("section=" + " > ".join(self.section_path))
        if self.row_start is not None or self.row_end is not None:
            parts.append(f"rows={self.row_start or ''}-{self.row_end or ''}")
        if self.column_start is not None or self.column_end is not None:
            parts.append(f"cols={self.column_start or ''}-{self.column_end or ''}")
        return " ".join(parts)


@dataclass(frozen=True)
class ParseError:
    """A concrete, non-silent explanation of a parse problem.

    ``code`` is a stable machine-readable token; ``message`` is for humans.
    ``retryable`` tells an orchestrator whether re-running the same input can
    plausibly change the outcome (a transient OCR failure) or cannot (an
    unsupported table layout).
    """

    code: str
    message: str
    parser: ParserType
    location: SourceLocation | None = None
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "parser": self.parser.value if isinstance(self.parser, ParserType) else str(self.parser),
            "retryable": self.retryable,
        }
        if self.location is not None:
            payload["location"] = self.location.as_dict()
        return payload


@dataclass(frozen=True)
class ContentBlock:
    """One parse product: a text run, a structured table, OCR text or data rows.

    Exactly one of ``content`` / ``rows`` carries meaning depending on
    ``block_type``:

    * ``text`` / ``ocr`` -> ``content`` string;
    * ``table`` / ``data_rows`` -> ``rows`` (each row a tuple of cell strings),
      optionally prefixed by ``header``.

    ``confidence`` is only meaningful for OCR blocks and is therefore optional
    everywhere else.
    """

    block_type: BlockType
    parser_type: ParserType
    content: str = ""
    rows: tuple[tuple[str, ...], ...] = ()
    header: tuple[str, ...] = ()
    location: SourceLocation | None = None
    confidence: float | None = None
    errors: tuple[ParseError, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "block_type": self.block_type.value,
            "parser_type": self.parser_type.value,
        }
        if self.block_type in (BlockType.TEXT, BlockType.OCR):
            payload["content"] = self.content
        if self.header:
            payload["header"] = list(self.header)
        if self.rows:
            payload["rows"] = [list(row) for row in self.rows]
        if self.location is not None:
            payload["location"] = self.location.as_dict()
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.errors:
            payload["errors"] = [error.as_dict() for error in self.errors]
        return payload

    @property
    def is_structured(self) -> bool:
        return self.block_type in (BlockType.TABLE, BlockType.DATA_ROWS)


def _cells_to_text(rows: Iterable[Iterable[str]]) -> str:
    """Render rows deterministically with tabs and newlines.

    Tabs and newlines are stripped from cell content so a spreadsheet value can
    never inject a fake row boundary into the index text.
    """
    rendered: list[str] = []
    for row in rows:
        cells = [str(cell).replace("\t", " ").replace("\n", " ") for cell in row]
        rendered.append("\t".join(cells))
    return "\n".join(rendered)


def render_block_for_index(block: ContentBlock) -> str:
    """Deterministic index text for one block, including its location prefix.

    This is the representation the knowledge-base index should store: it keeps
    page/sheet/table/row provenance in-band so retrieval answers can point back
    to the original file, and it never flattens a table into misleading prose.
    """
    location = block.location.label() if block.location is not None else ""
    if block.block_type in (BlockType.TEXT, BlockType.OCR):
        body = block.content
    else:
        parts: list[str] = []
        if block.header:
            parts.append(_cells_to_text([block.header]))
        if block.rows:
            parts.append(_cells_to_text(block.rows))
        body = "\n".join(parts) if parts else ""
    if location and body:
        return f"[{location}]\n{body}"
    if location:
        return f"[{location}]"
    return body


@dataclass(frozen=True)
class DocumentParseResult:
    """The aggregate result of parsing one file.

    ``status`` is derived from the blocks and errors by the factory helpers;
    ``failure_reason`` is the top-level explanation when ``status`` is
    ``failed``, and ``warnings`` carries non-fatal signals (for example
    low-confidence OCR) that a UI must be able to surface.
    """

    source: str
    extension: str
    status: ParseStatus
    blocks: tuple[ContentBlock, ...] = ()
    parsers: tuple[ParserType, ...] = ()
    failure_reason: str | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[ParseError, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return Path(self.source).name

    @property
    def plain_text(self) -> str:
        """Linear text only, in the order the parsers produced it.

        Mirrors the existing ``load_document`` semantics: table blocks are not
        spliced into the plain text, which is exactly what prevents a table from
        becoming misleading prose by accident.
        """
        return "\n\n".join(
            block.content
            for block in self.blocks
            if block.block_type in (BlockType.TEXT, BlockType.OCR) and block.content
        )

    def to_index_text(self) -> str:
        """Deterministic index representation of every block.

        The knowledge-base indexer should consume this rather than
        ``plain_text`` when it wants tables and data rows included with their
        provenance.
        """
        return "\n\n".join(
            render_block_for_index(block) for block in self.blocks
        ).strip()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "extension": self.extension,
            "status": self.status.value,
            "parsers": [parser.value for parser in self.parsers],
        }
        if self.blocks:
            payload["blocks"] = [block.as_dict() for block in self.blocks]
        if self.failure_reason is not None:
            payload["failure_reason"] = self.failure_reason
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        if self.errors:
            payload["errors"] = [error.as_dict() for error in self.errors]
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def success(
        cls,
        source: str,
        extension: str,
        blocks: Iterable[ContentBlock] = (),
        parsers: Iterable[ParserType] = (),
        warnings: Iterable[str] = (),
        errors: Iterable[ParseError] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "DocumentParseResult":
        return cls(
            source=source,
            extension=extension,
            status=ParseStatus.SUCCESS,
            blocks=tuple(blocks),
            parsers=tuple(parsers),
            warnings=tuple(warnings),
            errors=tuple(errors),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def partial(
        cls,
        source: str,
        extension: str,
        blocks: Iterable[ContentBlock] = (),
        parsers: Iterable[ParserType] = (),
        warnings: Iterable[str] = (),
        errors: Iterable[ParseError] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "DocumentParseResult":
        return cls(
            source=source,
            extension=extension,
            status=ParseStatus.PARTIAL_SUCCESS,
            blocks=tuple(blocks),
            parsers=tuple(parsers),
            warnings=tuple(warnings),
            errors=tuple(errors),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def empty(
        cls,
        source: str,
        extension: str,
        parsers: Iterable[ParserType] = (),
        warnings: Iterable[str] = (),
        errors: Iterable[ParseError] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "DocumentParseResult":
        return cls(
            source=source,
            extension=extension,
            status=ParseStatus.EMPTY,
            parsers=tuple(parsers),
            warnings=tuple(warnings),
            errors=tuple(errors),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failed(
        cls,
        source: str,
        extension: str,
        failure_reason: str,
        parsers: Iterable[ParserType] = (),
        blocks: Iterable[ContentBlock] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "DocumentParseResult":
        return cls(
            source=source,
            extension=extension,
            status=ParseStatus.FAILED,
            blocks=tuple(blocks),
            parsers=tuple(parsers),
            failure_reason=failure_reason,
            metadata=dict(metadata or {}),
        )

