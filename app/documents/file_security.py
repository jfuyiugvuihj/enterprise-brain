from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class UploadSecurityError(ValueError):
    """Raised when an uploaded file fails the local safety contract."""

    code = "unsupported_file"


@dataclass(frozen=True)
class UploadInspection:
    original_filename: str
    display_filename: str
    extension: str
    media_type: str


_ALLOWED_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".txt": ("text/plain", ()),
    ".md": ("text/markdown", ()),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        (b"PK\x03\x04",),
    ),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        (b"PK\x03\x04",),
    ),
    ".csv": ("text/csv", ()),
}
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")


def sanitize_upload_filename(filename: str | None) -> str:
    value = (filename or "").strip()
    if not value or value in {".", ".."}:
        raise UploadSecurityError("upload filename is required")
    if "/" in value or "\\" in value:
        raise UploadSecurityError("upload filename must not contain path separators")
    safe = Path(value).name
    if safe != value:
        raise UploadSecurityError("upload filename must not contain path segments")
    if safe.count(".") > 1:
        raise UploadSecurityError("double extensions are not allowed")
    return safe


def inspect_upload_header(filename: str, header: bytes | bytearray | memoryview) -> UploadInspection:
    display_filename = sanitize_upload_filename(filename)
    extension = Path(display_filename).suffix.lower()
    if extension not in _ALLOWED_TYPES:
        raise UploadSecurityError(f"unsupported upload extension: {extension}")

    media_type, signatures = _ALLOWED_TYPES[extension]
    sample = bytes(header or b"")
    if signatures and not any(sample.startswith(signature) for signature in signatures):
        raise UploadSecurityError(f"file header does not match extension {extension}")
    return UploadInspection(
        original_filename=filename,
        display_filename=display_filename,
        extension=extension,
        media_type=media_type,
    )


def build_storage_path(root: str | Path, resource_id: str, extension: str) -> Path:
    clean_extension = extension if extension.startswith(".") else f".{extension}"
    if clean_extension.lower() not in _ALLOWED_TYPES:
        raise UploadSecurityError(f"unsupported upload extension: {clean_extension}")
    if not _RESOURCE_ID_RE.match(resource_id or ""):
        raise UploadSecurityError("invalid resource id for upload storage")

    root_path = Path(root).resolve()
    storage_path = (root_path / f"{resource_id}{clean_extension.lower()}").resolve()
    if storage_path.parent != root_path:
        raise UploadSecurityError("upload storage path escapes the configured root")
    return storage_path


def stream_to_temporary_file(
    chunks: Iterable[bytes],
    directory: str | Path,
    *,
    max_bytes: int,
) -> Path:
    """Write an upload incrementally and remove partial output on any failure."""
    if max_bytes <= 0:
        raise UploadSecurityError("upload size limit must be positive")

    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    temp_path = root / f".upload-{secrets.token_hex(16)}.tmp"
    written = 0
    try:
        with temp_path.open("xb") as output:
            for chunk in chunks:
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise UploadSecurityError("upload chunks must be bytes")
                payload = bytes(chunk)
                written += len(payload)
                if written > max_bytes:
                    raise UploadSecurityError("upload exceeds the configured size limit")
                output.write(payload)
            output.flush()
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
