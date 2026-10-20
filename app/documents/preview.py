from pathlib import Path

from app.rag.loader import load_document


# R306: `.xlsx` / `.csv` preview as text too -- load_document() hands back the anchored
# markdown the indexer stores, so what a person reads is what a retrieval hit quotes.
# `display_name` is deliberately NOT passed here (R306 ruling 3): previewing a stored file
# is not a second read path, and the name that reaches this function is whatever the
# caller typed into /documents/{filename}/preview -- threading it into the parser would
# let one file carry two different anchors depending on who asked. So the anchor's first
# field stays the stored name in a preview, while the indexed body carries the uploaded
# name. That split is written down in docs/api/contract-v1.md, not left silent.
TEXT_EXTENSIONS = {".txt", ".md", ".doc", ".docx", ".xlsx", ".csv"}
PDF_EXTENSIONS = {".pdf"}
MAX_PREVIEW_CHARS = 200_000


def build_document_preview(
    file_path: str,
    filename: str | None = None,
    max_chars: int = MAX_PREVIEW_CHARS,
    *, principal=None,
) -> dict:
    """Return browser-friendly metadata for a document preview."""
    path = Path(file_path)
    display_name = filename or path.name
    extension = path.suffix.lower()

    if extension in {'.csv', '.xlsx'} and principal is not None:
        import pandas as pd
        from app.common.rbac import filter_dataframe_rows_with_scope
        from app.tools.excel import load_excel
        from app.api.v1.data import _row_scope_status

        if extension == '.xlsx':
            with pd.ExcelFile(path, engine='openpyxl') as workbook:
                frames = [(name, workbook.parse(name)) for name in workbook.sheet_names]
        else:
            frames = [(display_name, load_excel(str(path)))]
        pieces = []
        counts = {'rows_in': 0, 'rows_visible': 0, 'reason_code': ''}
        for name, frame in frames:
            visible, info = filter_dataframe_rows_with_scope(frame,
                role=principal.role, department=principal.department or '')
            counts['rows_in'] += len(frame)
            counts['rows_visible'] += len(visible)
            if info.get('reason_code'):
                counts['reason_code'] = info['reason_code']
            pieces.append('工作表：' + name + '\n' + visible.to_csv(index=False))
        text = '\n\n'.join(pieces)
        return {'filename': display_name, 'kind': 'text', 'text': text[:max_chars],
                'truncated': len(text) > max_chars, 'row_scope': _row_scope_status(counts)}

    if extension in PDF_EXTENSIONS:
        return {
            "filename": display_name,
            "kind": "pdf",
            "text": "",
        }

    if extension in TEXT_EXTENSIONS:
        text = load_document(str(path))
        return {
            "filename": display_name,
            "kind": "text",
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
        }

    raise ValueError(f"Unsupported preview format: {extension}")
