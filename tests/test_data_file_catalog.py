import asyncio
import os
import time

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_list_data_files_filters_formats_and_returns_metadata(tmp_path, monkeypatch):
    from app.api.v1 import data

    old_file = tmp_path / "old.csv"
    old_file.write_text("name,value\nold,1\n", encoding="utf-8")
    os.utime(old_file, (time.time() - 10, time.time() - 10))

    new_file = tmp_path / "new.xlsx"
    new_file.write_bytes(b"placeholder")
    (tmp_path / "ignore.txt").write_text("ignore", encoding="utf-8")

    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))

    result = asyncio.run(data.list_data_files())

    assert [item["filename"] for item in result["files"]] == ["new.xlsx", "old.csv"]
    assert result["files"][0]["extension"] == ".xlsx"
    assert result["files"][0]["size"] > 0
    assert result["files"][0]["size_label"]
    assert result["files"][0]["modified_at"]


def test_list_data_files_returns_empty_list_for_empty_directory(tmp_path, monkeypatch):
    from app.api.v1 import data

    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))

    assert asyncio.run(data.list_data_files()) == {"files": []}


def test_data_panel_has_file_catalog_and_refreshes_after_upload():
    source = (ROOT / "frontend" / "src" / "components" / "DataPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "dataFiles" in source
    assert "loadDataFiles" in source
    assert "selectDataFile" in source
    assert "暂无数据文件" in source
    assert "await loadDataFiles(file.name)" in source


def test_data_panel_quick_question_includes_selected_filename():
    source = (ROOT / "frontend" / "src" / "components" / "DataPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "emit('ask', { query: q, filename: dataFile.value })" in source
    assert "if (!dataFile.value) return" in source


def test_chat_request_forwards_selected_data_filename():
    app_source = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    chat_source = (ROOT / "frontend" / "src" / "components" / "ChatPanel.vue").read_text(
        encoding="utf-8"
    )

    assert "nextTick(() =>" in app_source
    assert "window.dispatchEvent(new CustomEvent('chat-ask', { detail: query }))" in app_source
    assert "data_filename: dataFilename" in chat_source
    assert "if (!response.ok)" in chat_source


def test_ask_initializes_session_schema_before_writing_messages():
    source = (ROOT / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")

    assert "def _ensure_sessions_table():" in source
    assert "_ensure_sessions_table()" in source


def test_quick_data_question_forces_data_analysis_context():
    source = (ROOT / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")

    assert "请仅使用数据分析工具分析数据文件" in source
    assert "orchestration_msg" in source
