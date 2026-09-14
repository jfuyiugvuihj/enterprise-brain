import zipfile

import pytest


def test_backup_round_trip_includes_manifest_and_files(tmp_path):
    from app.common.backup import create_backup, restore_backup

    source = tmp_path / "source"
    (source / "documents").mkdir(parents=True)
    (source / "documents" / "policy.txt").write_text("住宿费标准500元", encoding="utf-8")
    (source / "chroma_db").mkdir()
    (source / "chroma_db" / "index.bin").write_bytes(b"index")
    archive = tmp_path / "backup.zip"
    restored = tmp_path / "restored"

    manifest = create_backup(source, archive)
    restore_backup(archive, restored)

    assert manifest["files"] == 2
    assert (restored / "documents" / "policy.txt").read_text(encoding="utf-8") == "住宿费标准500元"
    assert (restored / "chroma_db" / "index.bin").read_bytes() == b"index"


def test_restore_rejects_path_traversal(tmp_path):
    from app.common.backup import restore_backup

    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../outside.txt", "blocked")

    with pytest.raises(ValueError, match="path traversal"):
        restore_backup(archive, tmp_path / "restored")
