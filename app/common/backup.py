import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_BACKUP_DIRS = (
    "documents",
    "data",
    "chroma_db",
    "static/exports",
    "logs",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(
    source_root: str | Path,
    archive_path: str | Path,
    include_dirs: tuple[str, ...] = DEFAULT_BACKUP_DIRS,
    extra_files: tuple[str, ...] = (),
) -> dict:
    root = Path(source_root).resolve()
    archive = Path(archive_path).resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    candidates = []
    for relative in (*include_dirs, *extra_files):
        candidate = (root / relative).resolve()
        if candidate.is_file():
            candidates.append(candidate)
        elif candidate.is_dir():
            candidates.extend(path for path in candidate.rglob("*") if path.is_file())

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(candidates):
            relative = path.relative_to(root).as_posix()
            handle.write(path, relative)
            entries.append(
                {
                    "path": relative,
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": len(entries),
            "entries": entries,
        }
        handle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def _safe_member_path(destination: Path, member_name: str) -> Path:
    target = (destination / member_name).resolve()
    if os.path.commonpath([str(destination), str(target)]) != str(destination):
        raise ValueError("path traversal in backup archive")
    return target


def restore_backup(archive_path: str | Path, destination: str | Path) -> dict:
    archive = Path(archive_path).resolve()
    target_root = Path(destination).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            if member.filename == "manifest.json":
                continue
            target = _safe_member_path(target_root, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(member) as source, target.open("wb") as output:
                output.write(source.read())
        manifest = json.loads(handle.read("manifest.json").decode("utf-8"))
    for entry in manifest.get("entries", []):
        restored = _safe_member_path(target_root, entry["path"])
        if not restored.exists() or _sha256(restored) != entry["sha256"]:
            raise ValueError(f"backup checksum mismatch: {entry['path']}")
    return manifest
