from pathlib import Path

import pytest

from app.documents.file_security import (
    _ALLOWED_TYPES,
    UploadSecurityError,
    build_storage_path,
    inspect_upload_header,
    sanitize_upload_filename,
    stream_to_temporary_file,
)
from app.rag.loader import load_document


def test_sanitize_upload_filename_rejects_client_path_segments():
    with pytest.raises(UploadSecurityError, match="path separators"):
        sanitize_upload_filename("../../secrets.pdf")

    with pytest.raises(UploadSecurityError, match="path separators"):
        sanitize_upload_filename(r"..\secrets.pdf")


def test_inspect_upload_header_rejects_extension_and_magic_mismatch():
    with pytest.raises(UploadSecurityError, match="does not match"):
        inspect_upload_header("report.pdf", b"MZ" + b"\x00" * 32)


def test_inspect_upload_header_accepts_a_pdf_signature():
    result = inspect_upload_header("report.pdf", b"%PDF-1.7\n")

    assert result.extension == ".pdf"
    assert result.media_type == "application/pdf"


def test_build_storage_path_uses_resource_id_and_stays_under_root(tmp_path):
    stored = build_storage_path(tmp_path, "e89d2c08-6d74-4e7a-baa5-1f2a7c8b9d0e", ".pdf")

    assert stored.parent == tmp_path.resolve()
    assert stored.name == "e89d2c08-6d74-4e7a-baa5-1f2a7c8b9d0e.pdf"


def test_build_storage_path_rejects_an_invalid_resource_id(tmp_path):
    with pytest.raises(UploadSecurityError, match="resource id"):
        build_storage_path(tmp_path, "../outside", ".pdf")


def test_stream_to_temporary_file_writes_in_chunks_and_returns_a_private_path(tmp_path):
    source = iter([b"first-", b"second"])
    temp_path = stream_to_temporary_file(source, tmp_path, max_bytes=32)

    assert temp_path.parent == tmp_path.resolve()
    assert temp_path.suffix == ".tmp"
    assert temp_path.read_bytes() == b"first-second"


def test_stream_to_temporary_file_removes_partial_content_when_limit_is_exceeded(tmp_path):
    with pytest.raises(UploadSecurityError, match="size limit"):
        stream_to_temporary_file(iter([b"1234", b"5678"]), tmp_path, max_bytes=6)

    assert list(tmp_path.iterdir()) == []


def test_upload_security_error_keeps_the_stable_contract_code():
    assert UploadSecurityError.code == "unsupported_file"


def test_knowledge_base_whitelist_is_limited_to_parsable_document_types():
    assert set(_ALLOWED_TYPES) == {".pdf", ".txt", ".md", ".docx"}


def test_inspect_upload_header_rejects_double_extensions():
    with pytest.raises(UploadSecurityError, match="double extensions"):
        inspect_upload_header("policy.pdf.txt", b"%PDF-1.7\n")

    with pytest.raises(UploadSecurityError, match="double extensions"):
        inspect_upload_header("policy.md.exe", b"MZ\x90\x00")


def test_inspect_upload_header_rejects_a_forged_docx_body():
    with pytest.raises(UploadSecurityError, match="does not match"):
        inspect_upload_header("policy.docx", b"%PDF-1.7 not really a docx")


@pytest.mark.parametrize("filename", ["sheet.xlsx", "table.csv", "legacy.doc", "payload.exe"])
def test_inspect_upload_header_rejects_extensions_outside_the_knowledge_base(filename):
    with pytest.raises(UploadSecurityError, match="unsupported upload extension") as exc_info:
        inspect_upload_header(filename, b"whatever")

    assert exc_info.value.code == "unsupported_file"


@pytest.mark.parametrize("extension", [".xlsx", ".csv"])
def test_build_storage_path_refuses_dataset_spreadsheet_extensions(tmp_path, extension):
    with pytest.raises(UploadSecurityError, match="unsupported upload extension"):
        build_storage_path(tmp_path, "resource-0001", extension)


def test_build_storage_path_normalizes_a_bare_whitelisted_extension(tmp_path):
    stored = build_storage_path(tmp_path, "resource-0001", "md")

    assert stored.parent == tmp_path.resolve()
    assert stored.name == "resource-0001.md"


@pytest.mark.parametrize("extension", sorted(_ALLOWED_TYPES))
def test_every_whitelisted_extension_is_routed_by_load_document(tmp_path, extension):
    """Guard the drift that made an accepted upload fail with an HTTP 500."""
    document = tmp_path / f"policy{extension}"
    document.write_bytes(b"# policy\n\nrevenue grew 12 percent.\n")

    try:
        load_document(str(document))
    except Exception as exc:  # a parser rejecting junk is fine; a dispatch gap is not
        assert "Unsupported file format" not in str(exc), (
            f"{extension} passes the upload whitelist but cannot be parsed"
        )


def test_load_document_reads_markdown_with_encoding_detection(tmp_path):
    document = tmp_path / "policy.md"
    document.write_bytes("# 季度经营分析\n\n营收环比增长 12%。\n".encode("utf-8"))

    assert load_document(str(document)) == "# 季度经营分析\n\n营收环比增长 12%。\n"


def test_load_document_reads_gbk_markdown(tmp_path):
    document = tmp_path / "legacy.md"
    document.write_bytes("# 旧文档\n".encode("gbk"))

    assert "旧文档" in load_document(str(document))


def test_load_document_still_rejects_dataset_spreadsheets(tmp_path):
    workbook = tmp_path / "sales.xlsx"
    workbook.write_bytes(b"PK\x03\x04not-a-real-workbook")

    with pytest.raises(ValueError, match="Unsupported file format"):
        load_document(str(workbook))


def _document_upload_client(monkeypatch, tmp_path):
    """Serve the real document router on a probe app: no port, no app.main lifespan."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.agents import tools
    from app.api.v1 import chat

    class FakeRetriever:
        def __init__(self):
            self.indexed = {}

        def add_document(self, filename, content, classification, department):
            self.indexed = {
                "filename": filename,
                "content": content,
                "classification": classification,
                "department": department,
            }
            return True, "indexed 2 chunks"

    retriever = FakeRetriever()
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", retriever)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    probe = FastAPI()
    probe.include_router(chat.router, prefix="/api/v1")
    return TestClient(probe), retriever


def _upload_client_as(monkeypatch, tmp_path, username: str, department: str):
    """Serve the document router with one authenticated subject, no middleware."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common.identity import Principal

    client, retriever = _document_upload_client(monkeypatch, tmp_path)
    principal = Principal.from_user(
        {"id": username, "username": username, "role": "staff", "department": department}
    )

    probe = FastAPI()

    @probe.middleware("http")
    async def _authenticate(request, call_next):
        request.state.principal = principal
        return await call_next(request)

    probe.include_router(chat.router, prefix="/api/v1")
    return TestClient(probe), retriever


def test_upload_route_rejects_a_spreadsheet_before_writing_files(tmp_path, monkeypatch):
    import asyncio
    import io

    from fastapi import HTTPException, UploadFile

    from app.api.v1 import chat

    def forbidden(*args, **kwargs):
        raise AssertionError("a rejected upload must not reach the parser or the index")

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "load_document", forbidden)
    monkeypatch.setattr(chat, "peek_next_document_version", forbidden)

    workbook = io.BytesIO(b"PK\x03\x04fake workbook body")
    upload = UploadFile(filename="sales.xlsx", file=workbook)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsupported_file"
    assert list(tmp_path.iterdir()) == []


def test_upload_route_rejects_a_csv_before_writing_files(tmp_path, monkeypatch):
    import asyncio
    import io

    from fastapi import HTTPException, UploadFile

    from app.api.v1 import chat

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))

    upload = UploadFile(filename="expenses.csv", file=io.BytesIO(b"month,amount\n2026-01,120\n"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsupported_file"
    assert list(tmp_path.iterdir()) == []


def test_http_upload_ingests_a_markdown_document(tmp_path, monkeypatch):
    body = "# 库存周转\n\n周转天数 32 天。\n"
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("inventory.md", body.encode("utf-8"), "text/markdown")},
        data={"classification": "2", "department": "operations"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["filename"] == "inventory.md"
    assert payload["message"] == "indexed 2 chunks"
    assert retriever.indexed["content"] == body
    assert retriever.indexed["classification"] == 2
    assert (tmp_path / payload["stored_name"]).read_text(encoding="utf-8") == body


def test_upload_inherits_the_uploader_department_and_not_the_form_one(
    tmp_path, monkeypatch
):
    client, retriever = _upload_client_as(monkeypatch, tmp_path, "warehouse-clerk", "仓储部")

    response = client.post(
        "/api/v1/upload",
        files={"file": ("stock.txt", "库存周转 32 天。".encode("utf-8"), "text/plain")},
        data={"classification": "1", "department": "财务部"},
    )

    assert response.status_code == 200, response.text
    assert retriever.indexed["department"] == "仓储部"
    assert response.json()["department"] == "仓储部"


def test_an_upload_with_no_subject_stays_unscoped(tmp_path, monkeypatch):
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("orphan.txt", "无主文档".encode("utf-8"), "text/plain")},
        data={"classification": "1", "department": "随便填"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["department"] == ""
    assert retriever.indexed["department"] is None


def test_http_upload_rejects_a_spreadsheet_with_a_stable_error_code(tmp_path, monkeypatch):
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={
            "file": (
                "sales.xlsx",
                b"PK\x03\x04fake workbook body",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "unsupported_file"}
    assert retriever.indexed == {}
    assert list(tmp_path.iterdir()) == []
