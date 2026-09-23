"""Minimal knowledge-base import mode for Excel and CSV.

This is deliberately separate from ``app/tools/excel.py``, which stays the
business-analysis chain.  The import mode emits one ``data_rows`` block per
worksheet (or per CSV file): a header row plus data rows, with the sheet name,
row range and source file attached to the block.  The indexer is expected to
consume ``render_block_for_index`` rather than dumping the whole workbook into
one unbounded string; ``max_rows_per_sheet`` puts an explicit, auditable bound
on how much of a sheet enters the index.
"""
from __future__ import annotations

import csv
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

DEFAULT_MAX_ROWS = 1000


@dataclass(frozen=True)
class SpreadsheetKbRun:
    """Structured spreadsheet import result.

    ``metadata`` keeps workbook-level facts (sheet names, total row counts) so
    a caller can report "imported rows 1-1000 of 43210" instead of pretending
    the whole workbook is in the index.
    """

    blocks: tuple[ContentBlock, ...] = ()
    status: ParseStatus = ParseStatus.EMPTY
    warnings: tuple[str, ...] = ()
    errors: tuple[ParseError, ...] = ()
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "blocks": [block.as_dict() for block in self.blocks],
            "status": self.status.value,
            "warnings": list(self.warnings),
            "errors": [error.as_dict() for error in self.errors],
            "metadata": dict(self.metadata),
        }


def _clean_cell(value) -> str:
    if value is None:
        return ""
    return str(value)


def _header_from_row(row) -> tuple[str, ...]:
    """Use the first non-empty run of cells as the header, trimming trailing empties."""
    cells = tuple(_clean_cell(cell) for cell in row)
    last = len(cells)
    while last > 0 and not cells[last - 1].strip():
        last -= 1
    return cells[:last]


def _data_block(
    source: str,
    *,
    sheet: str | None,
    header: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    row_start: int,
    row_end: int,
    parser_type: ParserType,
) -> ContentBlock:
    return ContentBlock(
        block_type=BlockType.DATA_ROWS,
        parser_type=parser_type,
        header=header,
        rows=rows,
        location=SourceLocation(
            file_path=source,
            sheet=sheet,
            row_start=row_start,
            row_end=row_end,
            column_start=1,
            column_end=len(header),
        ),
    )


def extract_excel_kb(file_path: str, *, max_rows_per_sheet: int | None = DEFAULT_MAX_ROWS) -> SpreadsheetKbRun:
    """Import an ``.xlsx`` workbook sheet by sheet, headers + data rows only."""
    from openpyxl import load_workbook

    source = str(Path(file_path))
    try:
        workbook = load_workbook(file_path, data_only=True, read_only=True)
    except Exception as exc:
        error = ParseError(
            code="excel_kb_open_failed",
            message=f"could not open workbook: {exc}",
            parser=ParserType.EXCEL_KB,
            location=SourceLocation(file_path=source),
        )
        return SpreadsheetKbRun(
            status=ParseStatus.FAILED,
            errors=(error,),
            warnings=(error.message,),
        )

    blocks: list[ContentBlock] = []
    warnings: list[str] = []
    sheet_rows: dict[str, int] = {}
    try:
        for sheet in workbook.worksheets:
            header: tuple[str, ...] = ()
            rows: list[tuple[str, ...]] = []
            total_data_rows = 0
            row_start = 2
            last_row = 1
            for row_number, raw in enumerate(sheet.iter_rows(min_row=1, values_only=True), start=1):
                if row_number == 1:
                    header = _header_from_row(raw)
                    continue
                if not any(_clean_cell(cell).strip() for cell in raw):
                    continue
                total_data_rows += 1
                if max_rows_per_sheet is not None and total_data_rows > max_rows_per_sheet:
                    continue
                cleaned = tuple(_clean_cell(cell) for cell in raw)
                rows.append(cleaned)
                last_row = row_number

            sheet_rows[sheet.title] = total_data_rows
            if max_rows_per_sheet is not None and total_data_rows > max_rows_per_sheet:
                warnings.append(
                    f"sheet {sheet.title}: imported {max_rows_per_sheet} of {total_data_rows} data rows"
                )

            if not header and not rows:
                continue

            blocks.append(
                _data_block(
                    source,
                    sheet=sheet.title,
                    header=header,
                    rows=tuple(rows),
                    row_start=row_start if rows else None,
                    row_end=last_row if rows else None,
                    parser_type=ParserType.EXCEL_KB,
                )
            )
    finally:
        workbook.close()

    status = ParseStatus.PARTIAL_SUCCESS if warnings else (ParseStatus.SUCCESS if blocks else ParseStatus.EMPTY)
    return SpreadsheetKbRun(
        blocks=tuple(blocks),
        status=status,
        warnings=tuple(warnings),
        metadata={"sheet_rows": sheet_rows, "max_rows_per_sheet": max_rows_per_sheet},
    )


def extract_csv_kb(
    file_path: str,
    *,
    max_rows: int | None = DEFAULT_MAX_ROWS,
    encoding: str | None = None,
) -> SpreadsheetKbRun:
    """Import one CSV in knowledge-base mode, preserving header, rows and range."""
    source = str(Path(file_path))

    text = None
    if encoding is not None:
        try:
            text = Path(file_path).read_text(encoding=encoding)
        except (UnicodeDecodeError, OSError) as exc:
            error = ParseError(
                code="csv_kb_open_failed",
                message=f"could not read CSV: {exc}",
                parser=ParserType.CSV_KB,
                location=SourceLocation(file_path=source),
            )
            return SpreadsheetKbRun(status=ParseStatus.FAILED, errors=(error,), warnings=(error.message,))
    else:
        for candidate in ("utf-8", "gbk", "gb2312"):
            try:
                text = Path(file_path).read_text(encoding=candidate)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            error = ParseError(
                code="csv_kb_encoding_failed",
                message="could not detect CSV encoding",
                parser=ParserType.CSV_KB,
                location=SourceLocation(file_path=source),
            )
            return SpreadsheetKbRun(status=ParseStatus.FAILED, errors=(error,), warnings=(error.message,))

    reader = csv.reader(text.splitlines())
    header: tuple[str, ...] = ()
    rows: list[tuple[str, ...]] = []
    total_data_rows = 0
    last_row = 1
    for row_number, raw in enumerate(reader, start=1):
        if row_number == 1:
            header = _header_from_row(raw)
            continue
        if not any(cell.strip() for cell in raw):
            continue
        total_data_rows += 1
        if max_rows is not None and total_data_rows > max_rows:
            continue
        rows.append(tuple(raw))
        last_row = row_number

    warnings: list[str] = []
    if max_rows is not None and total_data_rows > max_rows:
        warnings.append(f"imported {max_rows} of {total_data_rows} data rows")

    if not header and not rows:
        return SpreadsheetKbRun(
            status=ParseStatus.EMPTY,
            metadata={"total_rows": 0, "max_rows": max_rows},
        )

    block = _data_block(
        source,
        sheet=None,
        header=header,
        rows=tuple(rows),
        row_start=2 if rows else None,
        row_end=last_row if rows else None,
        parser_type=ParserType.CSV_KB,
    )
    status = ParseStatus.PARTIAL_SUCCESS if warnings else ParseStatus.SUCCESS
    return SpreadsheetKbRun(
        blocks=(block,),
        status=status,
        warnings=tuple(warnings),
        metadata={"total_rows": total_data_rows, "max_rows": max_rows},
    )
