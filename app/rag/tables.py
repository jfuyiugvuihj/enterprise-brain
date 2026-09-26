"""R300: PDF / Word tables -> anchored markdown, inside the existing chunk budget.

================================================================== 接线 (本单不接线)
R300 delivers a module, its tests and this contract only. app/rag/loader.py belongs to R298
(two tickets in flight on one file is the write-domain conflict this project already keeps an
accident ledger for), so the two lines below are landed by 总控 in 波次二, after R298 has
merged. Anchor them on the return statement rather than on a line number:

    loader.py:36  def load_pdf   -- its return, loader.py:46:
                    ->  return tables.extract_pdf_text(file_path)
    loader.py:49  def load_docx  -- its return, loader.py:54:
                    ->  return tables.extract_docx_text(file_path, <its paragraph join, untouched>)

Match the return statement, not the number: R298 is inside that file right now and will move them.
Neither replacement loses a step. load_pdf ends on "return text" after sanitize_text, and every
string this module hands back ends in _finish(), which is loader.sanitize_text itself -- so the
R130 gate still runs, and a tableless PDF comes back byte-for-byte as load_pdf returns it today.

extract_pdf_text() reuses pypdf byte-for-byte when a document holds no table, so the already
indexed corpus does not move; when it does hold one, the prose half comes from
pdf_prose_without_tables() -- measured on documents/refactor_guide.pdf pages 2/3/8: dropping
table bboxes removes table lines and adds nothing else. R298's OCR leg composes through the
extra_prose argument -- whatever text a caller owns is prepended as-is, tables appended once.

============ what a third-party parser hands back (measured) ============
The two formats disagree about merged cells, and both disagree with what a reader sees:

* pdfplumber 0.11.10 fills a rectangular grid. A span's text lands in one position and the
  positions it covers come back as None; a row shorter than the widest row is padded with the
  empty string (documents/refactor_guide.pdf page 2: 9 columns from a 3-cell header row). A
  vertical span glues its two source cells with a newline into the first position and leaves
  the covered position None.
* python-docx 1.2.0 repeats a merged cell's text in every position the span covers, so one
  value arrives twice inside the same row, joined with a newline as well.
* doc.paragraphs never carries a table cell (a table-only .docx yields an empty list), so
  today's load_docx drops every Word table, and appending this module's text to it cannot
  duplicate it. doc.tables lists top-level tables only and a cell's .text does not contain its
  nested table either -- both halves would be lost, which is why extract_docx_tables() recurses.
* pdfplumber finds nothing at all when a table has no borders (measured: 0 tables), and it
  splits a cell whose text overflows its own column across the neighbouring columns.

Everything above is normalized into one shape: every grid position carries the value that
visually covers it, an in-cell newline becomes a single space, a pipe is escaped, a row that is
one full-width span becomes a caption line instead of N copies of itself.

================================================================== the budget is not ours to invent
app/rag/retriever.py:889-893 owns the project's only chunking strategy (RecursiveCharacterText
Splitter, chunk_size=500, chunk_overlap=50). A block longer than that ruler is cut on newline
by the splitter and the tail half loses its anchor -- measured against the real splitter:
segments up to 498 characters stay atomic, from 499 up half the chunks arrive anchor-less. So a
table is emitted as parts of at most SEGMENT_CHAR_BUDGET characters, every part re-anchored,
no row emitted twice. That is alignment with the existing ruler, not a second chunker: the two
constants below are pinned to the upstream literals by tests/test_r300_tables.py, the way R206
pins the other ruler.

================================================================== measured cost, and the ceilings it buys
All twelve PDFs the repository carries were walked on this machine (26 Sep): 61 pages, 9
tables, one file with tables at all. documents/refactor_guide.pdf -- 28 pages, 9 tables, 422
cells, 1 362 characters of raw cell text over 57 parsed rows, longest rendered row 70
characters -- costs 1.7 s warm and 2.5 s cold for the table walk, and 3.0 s for the same walk
when it also returns the table-excluded prose; two separate passes over it measured 4.9 s,
which is why _walk_pdf does one. AI-Agent学习路线图.pdf (8 pages, no table) is 0.5 s because
its CMaps are expensive; the ten static/exports reports (2-3 pages, no table) are 7-24 ms.
So 3.5-108 ms per page, and 9 of the 57 parsed rows in the one table-bearing file are blank
and get dropped, leaving 48 rows in 16 anchored segments. Uploads go through
asyncio.to_thread, so the shape of the cost matters: MAX_TABLE_PAGES stops a walk at 400
pages, MAX_TABLE_CHARS at 40 000 characters of table, TABLE_TIME_BUDGET_SECONDS at 12 s --
on the densest file here the time budget is the one that binds, at roughly 110 pages.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.common.logger import logger

#: tests/test_r300_tables.py reads app/rag/retriever.py and goes red if these two drift, so the
#: packing below can never quietly become a second, wider ruler.
CHUNK_SIZE_CHARS = 500
CHUNK_OVERLAP_CHARS = 50

#: Blocks are joined with this, so it has to fit inside the budget next to the overlap reserve.
BLOCK_SEPARATOR = "\n\n"
SEGMENT_CHAR_BUDGET = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS - len(BLOCK_SEPARATOR)

#: ~108 ms per page measured above, table walk and excluded-prose walk taken together.
MAX_TABLE_PAGES = 400
MAX_TABLE_CHARS = 40_000
TABLE_TIME_BUDGET_SECONDS = 12.0

#: A table is flush with a page edge when it ends or starts within this many points of it --
#: the geometric signal that pagination broke a table rather than there being two tables.
FLUSH_TOLERANCE_PT = 96.0

#: The separator inside one anchor line, quoted by the tests and by the 回执.
ANCHOR_JOIN = " · "
MAX_CONTEXT_CHARS = 40

_HORIZONTAL_RUN = re.compile(r"[ \t　]+")
_LINE_RUN = re.compile(r"[\r\n]+")

#: A .docx has no page to stop at, so its ceiling is a count of tables and of nesting depth.
MAX_TABLES_PER_DOCUMENT = 200
MAX_NESTING_DEPTH = 3

PDF_SUFFIXES = (".pdf",)
DOCX_SUFFIXES = (".docx",)


@dataclass(frozen=True)
class TableBlock:
    """One table, normalized, carrying the provenance needed to point back at it.

    'ordinal' counts tables in document order across every page ('2.1' for a table nested
    inside the second one); 'page' and 'end_page' are 1-based and None for a format without
    pages. 'rows' never holds a row twice, 'spans' is how many grid positions a merge covered,
    'full_width_rows' which rendered rows became a caption instead of N copies of one value.
    """

    filename: str
    ordinal: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    source: str
    page: int | None = None
    end_page: int | None = None
    spans: int = 0
    context: str = ""
    captions: tuple[str, ...] = ()
    full_width_rows: tuple[int, ...] = ()

    @property
    def width(self) -> int:
        return len(self.header)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def page_label(self) -> str:
        if self.page is None:
            return ""
        if self.end_page is not None and self.end_page != self.page:
            return f"第{self.page}-{self.end_page}页"
        return f"第{self.page}页"

    def anchor(self, part: int = 1, parts: int = 1) -> str:
        """The line that lets a citation bar walk a hit back to the page it came from.

        app/agents/evidence.py records a document hit as filename plus chunk_index only, so
        the anchor has to sit inside the chunk text for 第2页 表1 to survive to the reader.
        """
        pieces = [self.filename]
        if self.page_label:
            pieces.append(self.page_label)
        label = f"表{self.ordinal}"
        if parts > 1:
            label = f"{label}（{part}/{parts}段）"
        pieces.append(label)
        if self.spans:
            pieces.append(f"合并单元格{self.spans}处")
        if self.context:
            pieces.append(f"前文「{self.context}」")
        return ANCHOR_JOIN.join(pieces)

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for row in (self.header,) + self.rows:
            digest.update("\x1f".join(row).encode("utf-8"))
            digest.update(b"\x1e")
        return digest.hexdigest()[:16]

    @staticmethod
    def _pipe(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    @property
    def header_line(self) -> str:
        return self._pipe(self.header)

    @property
    def separator_line(self) -> str:
        return "|" + "|".join(["---"] * self.width) + "|"

    @property
    def caption_line(self) -> str:
        if not self.captions:
            return ""
        return "> " + " / ".join(self.captions)

    @property
    def row_lines(self) -> tuple[str, ...]:
        lines = []
        for index, row in enumerate(self.rows):
            if index in self.full_width_rows:
                lines.append("> " + next((cell for cell in row if cell), ""))
            else:
                lines.append(self._pipe(row))
        return tuple(lines)

    @property
    def char_count(self) -> int:
        lines = [self.header_line, self.caption_line, *self.row_lines]
        return sum(len(line) + 1 for line in lines if line)

    def parts(self, budget: int = SEGMENT_CHAR_BUDGET) -> list[tuple[str, ...]]:
        """Group row lines so that anchor + header + separator + rows stays inside the ruler."""
        frame = len(self.header_line) + len(self.separator_line) + len(self.anchor()) + 6
        cap = max(64, budget - frame)
        units: list[list[str]] = []
        for index, row in enumerate(self.rows):
            line = self.row_lines[index]
            units.append([line] if len(line) <= cap else _degrade_row(self.header, row, cap))
        groups: list[list[str]] = [[]]
        used = 0
        for unit in units:
            for line in unit:
                if groups[-1] and used + len(line) + 1 > cap:
                    groups.append([])
                    used = 0
                groups[-1].append(line)
                used += len(line) + 1
        return [tuple(group) for group in groups if group]

    def _assemble(self, groups: list[tuple[str, ...]]) -> str:
        """Put an anchor -- and only an anchor -- on top of every group of lines."""
        total = len(groups)
        rendered = []
        for index, group in enumerate(groups, 1):
            head = [self.anchor(index, total) if total > 1 else self.anchor()]
            if index == 1 and self.captions:
                head.append(self.caption_line)
            rendered.append("\n".join([*head, *group]))
        return BLOCK_SEPARATOR.join(rendered)

    def to_markdown(self, budget: int = SEGMENT_CHAR_BUDGET) -> str:
        groups = self.parts(budget)
        if not groups:
            return self._header_only(budget)
        return self._assemble([(self.header_line, self.separator_line, *group) for group in groups])

    def _header_only(self, budget: int = SEGMENT_CHAR_BUDGET) -> str:
        """A table with no data rows -- one row in the source, or a nested table that is all
        header -- still may not arrive wider than the ruler.

        When the header line fits, that is the whole rendering. When it does not, the columns
        are named one per line, packed into budget-sized parts and re-anchored like any other
        table: which is all a header-only table says anyway.
        """
        plain = self._assemble([(self.header_line, self.separator_line)])
        if len(plain) <= budget:
            return plain
        # anchor(99, 99) is the widest anchor this block can print, so the reservation holds
        # whatever number of parts the field lines end up in.
        cap = max(64, budget - len(self.anchor(99, 99)) - len(self.caption_line) - 3)
        fields = _degrade_row(self.header, ("",) * self.width, cap)
        groups: list[list[str]] = [[]]
        used = 0
        for line in fields:
            if groups[-1] and used + len(line) + 1 > cap:
                groups.append([])
                used = 0
            groups[-1].append(line)
            used += len(line) + 1
        return self._assemble([tuple(group) for group in groups if group])


@dataclass(frozen=True)
class TableSet:
    """Every table found in one document, plus what finding them cost."""

    filename: str
    source: str
    blocks: tuple[TableBlock, ...] = ()
    pages: int = 0
    pages_scanned: int = 0
    truncated: str = ""
    elapsed_s: float = 0.0

    @property
    def table_count(self) -> int:
        return len(self.blocks)

    @property
    def row_count(self) -> int:
        return sum(block.row_count for block in self.blocks)

    @property
    def char_count(self) -> int:
        return sum(block.char_count for block in self.blocks)

    @property
    def text(self) -> str:
        return render_tables(self.blocks)

    def duplicates(self) -> list[str]:
        """Anchors whose fingerprint already appeared: the 反证 for one table arriving twice."""
        seen: set[str] = set()
        repeated = []
        for block in self.blocks:
            if block.fingerprint in seen:
                repeated.append(block.anchor())
            seen.add(block.fingerprint)
        return repeated

    def summary(self) -> dict:
        """The cheap half of stats(): what a log line needs, without rendering anything.

        stats() calls text and parts(), i.e. it lays every table out twice. Fine for a test
        or a receipt, wrong for the line that runs on each upload.
        """
        return {
            "filename": self.filename,
            "source": self.source,
            "pages": self.pages,
            "pages_scanned": self.pages_scanned,
            "tables": self.table_count,
            "rows": self.row_count,
            "truncated": self.truncated,
            "elapsed_s": round(self.elapsed_s, 3),
        }

    def stats(self) -> dict:
        return {
            "filename": self.filename,
            "source": self.source,
            "pages": self.pages,
            "pages_scanned": self.pages_scanned,
            "tables": self.table_count,
            "rows": self.row_count,
            "table_chars": self.char_count,
            "rendered_chars": len(self.text),
            "segments": sum(len(block.parts()) for block in self.blocks),
            "elapsed_s": round(self.elapsed_s, 3),
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class DocumentTables:
    """Prose and tables kept apart, so a table can never prove a document has text.

    'has_prose' reads prose and nothing else. 'text' is what a loader hands the existing
    chunker: prose first, anchored tables after, one string, every row exactly once.
    """

    filename: str
    source: str
    prose: str
    tables: TableSet
    extra_prose: str = ""

    @property
    def table_text(self) -> str:
        return self.tables.text

    @property
    def text(self) -> str:
        pieces = [self.prose, self.extra_prose, self.table_text]
        return _finish(BLOCK_SEPARATOR.join(piece.strip() for piece in pieces if piece.strip()))

    @property
    def has_prose(self) -> bool:
        """R300 判据⑥: judged on prose alone, so a table-only document says False and has text."""
        return bool((self.prose + self.extra_prose).strip())

    @property
    def table_count(self) -> int:
        return self.tables.table_count

    def stats(self) -> dict:
        merged = dict(self.tables.stats())
        merged.update({
            "text_chars": len(self.text),
            "prose_chars": len(self.prose),
            "extra_prose_chars": len(self.extra_prose),
            "has_prose": self.has_prose,
        })
        return merged


@dataclass
class _Shaped:
    """A block plus the pagination facts that decide whether the next one continues it."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    captions: tuple[str, ...] = ()
    spans: int = 0
    full_width: tuple[int, ...] = ()
    page: int | None = None
    end_page: int | None = None
    first_on_page: bool = True
    last_on_page: bool = True
    flush_top: bool = False
    flush_bottom: bool = False
    context: str = ""
    source: str = "pdf"

    @property
    def width(self) -> int:
        return len(self.header)

    def to_block(self, filename: str, ordinal: str) -> TableBlock:
        return TableBlock(
            filename=filename,
            ordinal=ordinal,
            header=self.header,
            rows=self.rows,
            source=self.source,
            page=self.page,
            end_page=self.end_page,
            spans=self.spans,
            context=self.context,
            captions=self.captions,
            full_width_rows=self.full_width,
        )


def _finish(text: str) -> str:
    """Route every public string through the R130 gate that lives in app/rag/loader.py.

    Imported inside the function on purpose: 波次二 has loader.py import this module, and a
    top-level import of loader here would close that cycle at import time. tests/test_r300_tables.py
    pins the absence of a module-level import.
    """
    from app.rag.loader import sanitize_text

    return sanitize_text(text)


def _cell_text(value: object) -> str:
    """One grid cell in the shape a reader sees: no newline, an escaped pipe, no run of spaces."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = _LINE_RUN.sub(" ", text)
    text = _HORIZONTAL_RUN.sub(" ", text).strip()
    return text.replace("|", "\\|")


def _rectangular(grid: Sequence[Sequence[object]]) -> tuple[list[list[str]], list[list[bool]]]:
    """Fill a parser grid into values plus a covered map, so a merge loses nothing.

    A position the parser reported as None is covered by a span: it borrows the resolved value
    to its left (a horizontal span) and, failing that, the value above it (a vertical span).
    Measured on documents/refactor_guide.pdf page 2 and on the R300 fixtures -- pdfplumber
    leaves a covered position as None, an empty-but-real cell as the empty string, and glues a
    vertical span's two source cells with a newline into the first position.
    """
    if not grid:
        return [], []
    width = max(len(row) for row in grid)
    values: list[list[str]] = []
    covered: list[list[bool]] = []
    for row in grid:
        cells = list(row) + [None] * (width - len(row))
        line: list[str] = []
        flags: list[bool] = []
        for cell in cells:
            flags.append(cell is None)
            line.append("" if cell is None else _cell_text(cell))
        values.append(line)
        covered.append(flags)
    for index, line in enumerate(values):
        previous = ""
        for position, cell in enumerate(line):
            if covered[index][position]:
                line[position] = previous
            else:
                previous = cell
    for index in range(1, len(values)):
        for position, cell in enumerate(values[index]):
            if covered[index][position] and not cell:
                values[index][position] = values[index - 1][position]
    return values, covered


def _is_full_width(cells: Sequence[str], flags: Sequence[bool]) -> bool:
    """True when one span covers the whole row: N copies of a value say less than a caption.

    Exactly one position of the row is a real cell (flags mark the ones a span covered), and
    every position carries the same text -- which is what both parsers hand back for a row
    that is a single merged banner. Requiring every position to be covered would never match,
    because the cell doing the covering is itself not covered.
    """
    filled = [cell for cell in cells if cell]
    if len(cells) < 2 or not filled or sum(1 for flag in flags if not flag) != 1:
        return False
    return len(set(filled)) == 1


def _shape_from(values: Sequence[Sequence[str]], flags: Sequence[Sequence[bool]]) -> _Shaped | None:
    """Turn a rectangular grid into header / rows / captions, or nothing when it is only blanks."""
    values = [list(row) for row in values]
    flags = [list(row) for row in flags]
    kept_values: list[list[str]] = []
    kept_flags: list[list[bool]] = []
    for row, marks in zip(values, flags):
        if any(row):
            kept_values.append(row)
            kept_flags.append(marks)
    if not kept_values:
        return None
    spans = sum(1 for marks in kept_flags for mark in marks if mark)
    captions: list[str] = []
    cursor = 0
    while (
        cursor < len(kept_values)
        and len(kept_values) - cursor > 2
        and _is_full_width(kept_values[cursor], kept_flags[cursor])
    ):
        captions.append(next(cell for cell in kept_values[cursor] if cell))
        cursor += 1
    header = tuple(kept_values[cursor])
    if not any(header):
        return None
    rows: list[tuple[str, ...]] = []
    full_width: list[int] = []
    for offset, (row, marks) in enumerate(zip(kept_values[cursor + 1:], kept_flags[cursor + 1:])):
        if _is_full_width(row, marks):
            full_width.append(offset)
        rows.append(tuple(row))
    return _Shaped(
        header=header, rows=tuple(rows), captions=tuple(captions), spans=spans, full_width=tuple(full_width)
    )


def _shape(grid: Sequence[Sequence[object]]) -> _Shaped | None:
    """The pdfplumber entry into _shape_from(): normalize a parser grid first."""
    return _shape_from(*_rectangular(grid))


def _chunk_line(line: str, width: int) -> list[str]:
    """Cut one over-long line into budget-sized pieces: lossy in shape, never in text."""
    if width <= 0 or len(line) <= width:
        return [line]
    return [line[start:start + width] for start in range(0, len(line), width)]


def _degrade_row(header: Sequence[str], row: Sequence[str], width: int) -> list[str]:
    """A row too wide for one pipe line becomes one named field per line.

    Measured: a pdfplumber cell whose text overflows its own column is already split across the
    neighbouring columns, so this path is reached by documents with genuinely long cells --
    mostly Word, where a cell holds a whole paragraph. Every line stays under the ruler and
    still names its column, which a mid-cell cut would not.
    """
    lines: list[str] = []
    for index, value in enumerate(row):
        label = header[index] if index < len(header) and header[index] else f"列{index + 1}"
        pieces = _chunk_line(value, max(1, width - len(label) - 6)) or [""]
        for piece_index, piece in enumerate(pieces):
            head = label if piece_index == 0 else f"{label}（续{piece_index}）"
            lines.append(f"- {head}: {piece}")
    return lines


def render_tables(blocks: Sequence[TableBlock], budget: int = SEGMENT_CHAR_BUDGET) -> str:
    """The anchored markdown for a set of tables -- plain text, no metadata, one channel."""
    return _finish(BLOCK_SEPARATOR.join(block.to_markdown(budget) for block in blocks))


def _continues(earlier: _Shaped, later: _Shaped) -> bool:
    """Would pagination, rather than an author, have put these two tables side by side?"""
    if earlier.end_page is None or later.page is None:
        return False
    return (
        later.page == earlier.end_page + 1
        and earlier.last_on_page
        and later.first_on_page
        and earlier.flush_bottom
        and later.flush_top
        and later.width == earlier.width
    )


def _absorb(earlier: _Shaped, later: _Shaped) -> _Shaped:
    """Stitch a continuation onto the table it belongs to, under one anchor.

    A repeated header row is dropped (Word writes one on every page); any other first row is
    data and is kept, so stitching can only ever remove a row the page above already emitted.
    """
    repeated_header = bool(later.header) and later.header == earlier.header
    carried: list[tuple[str, ...]] = []
    if not repeated_header and any(later.header):
        carried.append(later.header)
    shift = len(carried)
    return _Shaped(
        header=earlier.header,
        rows=(*earlier.rows, *carried, *later.rows),
        captions=tuple(dict.fromkeys((*earlier.captions, *later.captions))),
        spans=earlier.spans + later.spans,
        full_width=(*earlier.full_width, *(len(earlier.rows) + shift + index for index in later.full_width)),
        page=earlier.page,
        end_page=later.end_page if later.end_page is not None else later.page,
        first_on_page=earlier.first_on_page,
        last_on_page=later.last_on_page,
        flush_top=earlier.flush_top,
        flush_bottom=later.flush_bottom,
        context=earlier.context,
        source=earlier.source,
    )


def _docx_grid(table: object) -> tuple[list[list[str]], list[list[bool]]]:
    """Cleaned rows of cell text plus a covered map, by cell identity, never by comparing text.

    The cleaning is the same _cell_text the PDF path uses, and it is not decoration: a Word
    cell holds paragraphs, so its text arrives with newlines inside it, and a newline in a
    markdown row both breaks the row and hands the existing splitter a separator in the middle
    of one cell. Measured on python-docx 1.2.0: a merged cell is reported in every position its span
    covers -- a horizontal and a vertical span both hand back the same w:tc -- so identity is
    what marks a position as covered. Comparing text instead would call two coincidentally
    equal cells a merge. The references are kept on purpose: lxml only guarantees a proxy
    stays the same object while something holds it.
    """
    values: list[list[str]] = []
    covered: list[list[bool]] = []
    held: list[object] = []
    above: dict[int, int] = {}
    for row in table.rows:
        line: list[str] = []
        marks: list[bool] = []
        seen: set[int] = set()
        current: dict[int, int] = {}
        for position, cell in enumerate(row.cells):
            handle = cell._tc
            held.append(handle)
            key = id(handle)
            marks.append(key in seen or above.get(position) == key)
            seen.add(key)
            current[position] = key
            line.append(_cell_text(cell.text))
        above = current
        values.append(line)
        covered.append(marks)
    return values, covered


def _docx_nested(table: object) -> list[tuple[str, object]]:
    """Tables inside a cell, in document order, each reported once (merged cells repeat)."""
    found: list[tuple[str, object]] = []
    seen: list[object] = []
    for row in table.rows:
        for position, cell in enumerate(row.cells):
            handle = cell._tc
            if any(handle is kept for kept in seen):
                continue
            seen.append(handle)
            for child in cell.tables:
                found.append((str(position + 1), child))
    return found


def _walk_docx_table(
    table: object, filename: str, ordinal: str, context: str, depth: int = 0
) -> list[TableBlock]:
    values, marks = _docx_grid(table)
    blocks: list[TableBlock] = []
    shaped = _shape_from(values, marks)
    if shaped is not None:
        shaped.source = "docx"
        shaped.context = context
        blocks.append(shaped.to_block(filename, ordinal))
    if depth < MAX_NESTING_DEPTH:
        for child_index, (_position, child) in enumerate(_docx_nested(table), 1):
            blocks.extend(_walk_docx_table(child, filename, f"{ordinal}.{child_index}", "", depth + 1))
    return blocks


def _clamp_bbox(bbox: Sequence[float], width: float, height: float) -> tuple[float, float, float, float]:
    """Keep a reported bbox inside the page box.

    Measured: a table whose last row runs off the foot of the page (a 35-row band on a 792-point
    Letter page) hands back a bbox whose bottom is 802, and pdfplumber refuses to crop with it
    -- "Bounding box ... is not fully within parent page bounding box". The exception came from
    outside_bbox(), which is prose plumbing, so one over-long table would have failed the whole
    document. Clamping is the fix; the row itself is still extracted.
    """
    left, top, right, bottom = (float(value) for value in bbox)
    return (
        max(0.0, min(left, width)),
        max(0.0, min(top, height)),
        max(0.0, min(right, width)),
        max(0.0, min(bottom, height)),
    )


def _walk_pdf(
    file_path: str | Path,
    *,
    want_prose: bool,
    max_pages: int = MAX_TABLE_PAGES,
    max_chars: int = MAX_TABLE_CHARS,
    time_budget_s: float = TABLE_TIME_BUDGET_SECONDS,
    merge_continuations: bool = True,
) -> tuple[TableSet, str]:
    """One pdfplumber pass for both halves: the tables, and the text with their boxes cut out.

    A second pass was measured at 4.889 s wall for documents/refactor_guide.pdf against 2.454 s
    for the tables alone -- the page walk is the cost, so prose and tables share it.
    """
    import pdfplumber

    path = Path(file_path)
    started = time.monotonic()
    shaped: list[_Shaped] = []
    prose_parts: list[str] = []
    pages = 0
    scanned = 0
    truncated = ""
    with pdfplumber.open(str(path)) as pdf:
        pages = len(pdf.pages)
        for index, page in enumerate(pdf.pages, 1):
            if index > max_pages:
                truncated = f"pages:{scanned}of{pages}"
                break
            if time.monotonic() - started > time_budget_s:
                truncated = f"time:{scanned}of{pages}"
                break
            scanned = index
            found = page.find_tables()
            height = float(page.height)
            width = float(page.width)
            keep = page
            for position, table in enumerate(found):
                left, top, right, bottom = _clamp_bbox(table.bbox, width, height)
                if want_prose:
                    keep = keep.outside_bbox((left, top, right, bottom))
                block = _shape(table.extract())
                if block is None:
                    continue
                block.page = index
                block.end_page = index
                block.first_on_page = position == 0
                block.last_on_page = position == len(found) - 1
                block.flush_top = top <= FLUSH_TOLERANCE_PT
                block.flush_bottom = height - bottom <= FLUSH_TOLERANCE_PT
                shaped.append(block)
            if want_prose:
                text = (keep.extract_text() or "").strip()
                if text:
                    prose_parts.append(text)

    stitched: list[_Shaped] = []
    for block in shaped:
        if merge_continuations and stitched and _continues(stitched[-1], block):
            stitched[-1] = _absorb(stitched[-1], block)
        else:
            stitched.append(block)

    blocks: list[TableBlock] = []
    used = 0
    for index, item in enumerate(stitched, 1):
        block = item.to_block(path.name, str(index))
        if blocks and used + block.char_count > max_chars:
            truncated = truncated or f"chars:{len(blocks)}of{len(stitched)}"
            break
        blocks.append(block)
        used += block.char_count
    result = TableSet(
        filename=path.name,
        source="pdf",
        blocks=tuple(blocks),
        pages=pages,
        pages_scanned=scanned,
        truncated=truncated,
        elapsed_s=time.monotonic() - started,
    )
    return result, _finish(BLOCK_SEPARATOR.join(prose_parts))


def extract_pdf_tables(
    file_path: str | Path,
    *,
    max_pages: int = MAX_TABLE_PAGES,
    max_chars: int = MAX_TABLE_CHARS,
    time_budget_s: float = TABLE_TIME_BUDGET_SECONDS,
    merge_continuations: bool = True,
) -> TableSet:
    """Every bordered table in a PDF, one block each, stitched across a page break when it was
    pagination that split it.

    merge_continuations is the measured answer to a table that runs off the bottom of a page:
    pdfplumber sees two tables, and this module calls them one when the first is the last table
    on its page and ends within FLUSH_TOLERANCE_PT of the foot, the second is the first on the
    next page and starts within it of the head, and both have the same column count. Anything
    narrower stays two blocks with two anchors -- the rule is deliberately biased against
    guessing, and both outcomes are pinned by tests/test_r300_tables.py.
    """
    tables, _ = _walk_pdf(
        file_path,
        want_prose=False,
        max_pages=max_pages,
        max_chars=max_chars,
        time_budget_s=time_budget_s,
        merge_continuations=merge_continuations,
    )
    logger.info(f"R300 表格抽取 pdf: {tables.summary()}")
    return tables


def extract_docx_tables(
    file_path: str | Path,
    *,
    max_tables: int = MAX_TABLES_PER_DOCUMENT,
    max_chars: int = MAX_TABLE_CHARS,
) -> TableSet:
    """Every table in a .docx, including the ones Word nests inside a cell.

    'pages' stays 0 on purpose: a .docx has no page model until it is laid out, so the anchor
    locates a table by document order plus the paragraph in front of it. Measured: those
    paragraphs never contain a cell, so a caller that keeps its own paragraph join and appends
    this text cannot emit anything twice.
    """
    from docx import Document
    from docx.text.paragraph import Paragraph

    path = Path(file_path)
    started = time.monotonic()
    document = Document(str(path))
    blocks: list[TableBlock] = []
    context = ""
    used = 0
    truncated = ""
    ordinal = 0
    stop = False
    for item in document.iter_inner_content():
        if stop:
            break
        if isinstance(item, Paragraph):
            if item.text.strip():
                context = item.text.strip()[:MAX_CONTEXT_CHARS]
            continue
        ordinal += 1
        if len(blocks) >= max_tables:
            truncated = f"tables:{ordinal - 1}"
            break
        for block in _walk_docx_table(item, path.name, str(ordinal), context):
            if blocks and used + block.char_count > max_chars:
                truncated = truncated or f"chars:{len(blocks)}"
                stop = True
                break
            blocks.append(block)
            used += block.char_count
    result = TableSet(
        filename=path.name,
        source="docx",
        blocks=tuple(blocks),
        truncated=truncated,
        elapsed_s=time.monotonic() - started,
    )
    logger.info(f"R300 表格抽取 docx: {result.summary()}")
    return result


def extract_tables(file_path: str | Path, **limits: object) -> TableSet:
    """Dispatch on suffix the way load_document does, and refuse everything else out loud."""
    suffix = Path(file_path).suffix.lower()
    if suffix in PDF_SUFFIXES:
        return extract_pdf_tables(file_path, **limits)
    if suffix in DOCX_SUFFIXES:
        return extract_docx_tables(file_path, **limits)
    raise ValueError(f"R300 表格抽取不支持该格式: {suffix or file_path}")


def pdf_prose_without_tables(file_path: str | Path) -> str:
    """pdfplumber's own page text with every table bbox cut out of it.

    This is the half that keeps a table from arriving twice. Measured on
    documents/refactor_guide.pdf pages 2/3/8: cut the bboxes and the only lines that go are the
    table's, none are added. It is not the string pypdf returns -- which is exactly why
    line-level dedup against pypdf output was rejected (measured: 1 of 62 table lines matched,
    so the two parsers do not agree on where a line ends).
    """
    _, prose = _walk_pdf(file_path, want_prose=True)
    return prose


def pdf_prose_via_loader(file_path: str | Path) -> str:
    """Today's load_pdf output, imported rather than copied, so it cannot drift.

    A PDF with no table keeps this, which is what makes the wiring in 波次二 a no-op for the
    already indexed corpus instead of a mass re-index.
    """
    from app.rag.loader import load_pdf

    return load_pdf(str(file_path))


def extract_document(
    file_path: str | Path,
    *,
    prose: str | None = None,
    extra_prose: str = "",
    **limits: object,
) -> DocumentTables:
    """Prose and tables as two values plus the one string a chunker should see.

    prose=None picks the safe half for the format: for a PDF with no table that is
    pdf_prose_via_loader(), for a PDF with one it is the same single page walk with the table
    boxes cut out. For a .docx it is the empty string, because only the caller knows which
    paragraph join it wants to keep. Handing prose in explicitly wins for a PDF re-introduces
    the duplicate this function exists to avoid, so the loader wiring in 波次二 must not.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        tables, walked = _walk_pdf(path, want_prose=True, **limits)
        if prose is None:
            prose = walked if tables.blocks else pdf_prose_via_loader(path)
        source = "pdf"
    elif suffix in DOCX_SUFFIXES:
        tables = extract_docx_tables(path, **limits)
        if prose is None:
            prose = ""
        source = "docx"
    else:
        raise ValueError(f"R300 表格抽取不支持该格式: {suffix or file_path}")
    return DocumentTables(
        filename=path.name,
        source=source,
        prose=prose,
        extra_prose=extra_prose,
        tables=tables,
    )


def extract_pdf_text(file_path: str | Path, extra_prose: str = "", **limits: object) -> str:
    """The loader.py:44 replacement: PDF text with every table anchored, exactly once each."""
    return extract_document(file_path, extra_prose=extra_prose, **limits).text


def extract_docx_text(file_path: str | Path, prose: str = "", **limits: object) -> str:
    """The loader.py:54 replacement: the caller's paragraph join, with Word's tables appended."""
    return extract_document(file_path, prose=prose, **limits).text
