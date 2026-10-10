"""Project spreadsheet recall through the same row policy used by data tools."""
import os
from dataclasses import replace
from pathlib import Path

import pandas as pd

from app.common.logger import logger
from app.common.policy import is_administrator
from app.common.rbac import filter_dataframe_rows
from app.rag.spreadsheets import SEGMENT_CHAR_BUDGET, load_spreadsheet
from app.rag.tables import render_tables


def project_spreadsheet_hit(hit, sheet, principal):
    if is_administrator(principal):
        return hit
    content = str(hit.get("content") or "").strip()
    original = sheet.text
    start = original.find(content) if content else -1
    if start < 0:
        return None  # stale/unparseable chunks cannot carry unrestricted rows
    stop = start + len(content)
    blocks = []
    offset = 0
    for block in sheet.blocks:
        rendered = render_tables([block], SEGMENT_CHAR_BUDGET)
        position = original.find(rendered, offset)
        if position < 0:
            return None
        offset = position + len(rendered)
        if position >= stop or offset <= start:
            continue
        frame = pd.DataFrame(block.rows, columns=block.header)
        visible = filter_dataframe_rows(frame, role=principal.role, department=principal.department)
        # Keep the original chunk boundary: never expand a small hit into a whole workbook.
        visible = visible.loc[[index for index in visible.index if block.row_lines[index] in content]]
        if not visible.empty:
            # Captions/full-width rows may contain totals from outside the visible rows.
            blocks.append(replace(block, rows=tuple(visible.itertuples(index=False, name=None)),
                                  captions=(), full_width_rows=(), context=""))
    safe = render_tables(blocks, SEGMENT_CHAR_BUDGET) if blocks else ""
    return {**hit, "content": safe} if safe.strip() else None


def spreadsheet_projector(principal, scope):
    """One request-local parse per source; only catalogued files under storage roots."""
    from app.documents.catalog import latest_document_version

    parsed = {}
    roots = [Path(os.getenv(key, default)).resolve()
             for key, default in (("DATA_DIR", "./data"), ("DOCUMENTS_DIR", "./documents"))]

    def project(hit):
        filename = str(hit.get("source") or "")
        if Path(filename).suffix.lower() not in (".csv", ".xlsx") or is_administrator(principal):
            return hit
        try:
            if filename not in parsed:
                row = latest_document_version(filename)
                if not row or not scope.allows(row):
                    parsed[filename] = None
                else:
                    path = Path(str(row.get("storage_path") or "")).resolve()
                    if not any(path.is_relative_to(root) for root in roots):
                        parsed[filename] = None
                    else:
                        parsed[filename] = load_spreadsheet(path, display_name=filename)
            sheet = parsed[filename]
            return project_spreadsheet_hit(hit, sheet, principal) if sheet else None
        except Exception as exc:
            logger.warning("Spreadsheet row projection refused: %s", type(exc).__name__)
            return None

    return project
