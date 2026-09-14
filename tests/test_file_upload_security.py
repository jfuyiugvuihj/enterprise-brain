from pathlib import Path

import pytest

from app.documents.file_security import (
    UploadSecurityError,
    build_storage_path,
    inspect_upload_header,
    sanitize_upload_filename,
    stream_to_temporary_file,
)


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
