"""Structured table extraction for PDF and DOCX.

Tables are emitted as :class:`ContentBlock` rows (a tuple of cell tuples), never
spliced into prose.  A parser that cannot read a file, or that reads some pages
but fails on others, reports that explicitly through :class:`TableParseRun`
instead of returning a flat string that looks like ordinary text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.rag.parser_result import (
    BlockType,
    ContentBlock,
    ParseError,
    ParseStatus,
    ParserType,
    SourceLocation,
)


@dataclass(frozen=True)
class TableParseRun:
    """Tables found by one parser plus an honest aggregate status.

    ``status`` is ``empty`` when the file simply contains no tables, ``failed``
    when the parser could not read the file at all, and ``partial_success`` when
    at least one page/table failed while others succeeded.
    """

    blocks: tuple[ContentBlock, ...] = ()
    status: ParseStatus = ParseStatus.EMPTY
    warnings: tuple[str, ...] = ()
    errors: tuple[ParseError, ...] = ()

    def as_dict(self) -> dict:
        return {
            "blocks": [block.as_dict() for block in self.blocks],
            "status": self.status.value,
            "warnings": list(self.warnings),
            "errors": [error.as_dict() for error in self.errors],
        }


def _clean_cell(value) -> str:
    if value is None:
        return ""
    return str(value)


def _rows_from_table(table) -> tuple[tuple[str, ...], ...]:
    """Normalise pdfplumber / python-docx rows to tuples of strings."""
    rows: list[tuple[str, ...]] = []
    for row in table:
        rows.append(tuple(_clean_cell(cell) for cell in row))
    return tuple(rows)


def _table_block(
    source: str,
    rows: tuple[tuple[str, ...], ...],
    *,
    page: int | None = None,
    table_index: int | None = None,
) -> ContentBlock:
    return ContentBlock(
        block_type=BlockType.TABLE,
        parser_type=ParserType.PDF_TABLE if page is not None else ParserType.DOCX_TABLE,
        rows=rows,
        location=SourceLocation(
            file_path=source,
            page=page,
            table_index=table_index,
        ),
    )


def extract_docx_tables(file_path: str) -> TableParseRun:
    """Extract every table in a .docx, preserving row/column order."""
    from docx import Document

    source = str(Path(file_path))
    try:
        document = Document(file_path)
    except Exception as exc:
        error = ParseError(
            code="docx_table_open_failed",
            message=f"could not open DOCX for table extraction: {exc}",
            parser=ParserType.DOCX_TABLE,
            location=SourceLocation(file_path=source),
        )
        return TableParseRun(
            status=ParseStatus.FAILED,
            errors=(error,),
            warnings=(error.message,),
        )

    blocks: list[ContentBlock] = []
    for index, table in enumerate(document.tables, start=1):
        rows = tuple(
            tuple(_clean_cell(cell.text) for cell in row.cells)
            for row in table.rows
        )
        if rows:
            blocks.append(
                _table_block(source, rows, table_index=index)
            )

    status = ParseStatus.SUCCESS if blocks else ParseStatus.EMPTY
    return TableParseRun(blocks=tuple(blocks), status=status)


def extract_pdf_tables(file_path: str) -> TableParseRun:
    """Extract grid/stream tables from a PDF, keeping page and table position."""
    import pdfplumber

    source = str(Path(file_path))
    try:
        pdf = pdfplumber.open(file_path)
    except Exception as exc:
        error = ParseError(
            code="pdf_table_open_failed",
            message=f"could not open PDF for table extraction: {exc}",
            parser=ParserType.PDF_TABLE,
            location=SourceLocation(file_path=source),
        )
        return TableParseRun(
            status=ParseStatus.FAILED,
            errors=(error,),
            warnings=(error.message,),
        )

    blocks: list[ContentBlock] = []
    errors: list[ParseError] = []
    warnings: list[str] = []
    try:
        for page_number, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception as exc:
                error = ParseError(
                    code="pdf_table_page_failed",
                    message=f"page {page_number} table extraction failed: {exc}",
                    parser=ParserType.PDF_TABLE,
                    location=SourceLocation(file_path=source, page=page_number),
                )
                errors.append(error)
                warnings.append(error.message)
                continue

            for index, table in enumerate(tables, start=1):
                rows = _rows_from_table(table)
                if rows:
                    blocks.append(
                        _table_block(source, rows, page=page_number, table_index=index)
                    )
    finally:
        pdf.close()

    if not blocks and errors:
        return TableParseRun(
            status=ParseStatus.FAILED,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
    if errors:
        return TableParseRun(
            blocks=tuple(blocks),
            status=ParseStatus.PARTIAL_SUCCESS,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
    return TableParseRun(
        blocks=tuple(blocks),
        status=ParseStatus.SUCCESS if blocks else ParseStatus.EMPTY,
        warnings=tuple(warnings),
    )

