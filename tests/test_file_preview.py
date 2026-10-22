from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_text_document_preview_returns_readable_content(tmp_path):
    from app.documents.preview import build_document_preview

    source = tmp_path / "notes.txt"
    source.write_text("第一行\n第二行", encoding="utf-8")

    result = build_document_preview(str(source), "notes.txt")

    assert result["kind"] == "text"
    assert result["text"] == "第一行\n第二行"
    assert result["filename"] == "notes.txt"


def test_pdf_document_preview_is_marked_for_native_browser_reader(tmp_path):
    from app.documents.preview import build_document_preview

    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = build_document_preview(str(source), "report.pdf")

    assert result["kind"] == "pdf"
    assert result["filename"] == "report.pdf"


def test_markdown_document_preview_returns_readable_content(tmp_path):
    from app.documents.preview import build_document_preview

    source = tmp_path / "stock.md"
    source.write_text("# 库存周转\n\n周转天数 32 天。", encoding="utf-8")

    result = build_document_preview(str(source), "stock.md")

    assert result["kind"] == "text"
    assert "库存周转" in result["text"]
    assert result["truncated"] is False


def test_markdown_document_preview_detects_legacy_encoding(tmp_path):
    from app.documents.preview import build_document_preview

    source = tmp_path / "legacy.md"
    source.write_bytes("# 财务口径\n\n毛利率 31%\n".encode("gbk"))

    result = build_document_preview(str(source), "legacy.md")

    assert result["kind"] == "text"
    assert "毛利率" in result["text"]


def test_every_ingestible_document_extension_has_a_preview_route():
    """上传白名单与预览白名单不得各说各话。"""
    from app.documents.file_security import _ALLOWED_TYPES
    from app.documents.preview import PDF_EXTENSIONS, TEXT_EXTENSIONS

    assert set(_ALLOWED_TYPES) <= TEXT_EXTENSIONS | PDF_EXTENSIONS

def test_dataframe_preview_contains_rows_columns_and_profile():
    from app.api.v1.data import build_dataframe_preview

    frame = pd.DataFrame(
        [
            {"部门": "研发", "人数": 3},
            {"部门": "销售", "人数": 5},
        ]
    )

    result = build_dataframe_preview(frame, "sales.xlsx")

    assert result["filename"] == "sales.xlsx"
    assert result["columns"] == ["部门", "人数"]
    assert result["rows"] == [
        {"部门": "研发", "人数": 3},
        {"部门": "销售", "人数": 5},
    ]
    assert result["profile"]["rows"] == 2
    assert result["profile"]["column_count"] == 2


def test_document_preview_ui_supports_text_and_pdf():
    source = (ROOT / "frontend" / "src" / "components" / "DocumentPreviewModal.vue").read_text(
        encoding="utf-8"
    )

    assert "kind === 'pdf'" in source
    assert "kind === 'text'" in source
    assert "<pre" in source


def test_data_panel_exposes_preview_and_original_file_actions():
    source = (ROOT / "frontend" / "src" / "components" / "DataPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "DocumentPreviewModal" in source
    assert "downloadDataFile" in source
    assert "openDataFile" in source
    assert "previewOpen" in source
