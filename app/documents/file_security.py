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


# Knowledge-base upload whitelist: every extension here must be handled by
# app.rag.loader.load_document(), otherwise a stored file is deleted and the
# upload route fails with a 500 parse error. Spreadsheets are datasets, not
# knowledge-base documents, and belong to POST /api/v1/upload-excel.
_ALLOWED_TYPES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".txt": ("text/plain", ()),
    ".md": ("text/markdown", ()),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        (b"PK\x03\x04",),
    ),
}
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")

# Disguise guard for the *middle* of an uploaded filename (ticket R91).
#
# The rule this replaces refused any name holding two dots, which conflates an
# attack (`policy.pdf.txt`, `policy.md.exe`) with the way people really name
# documents. 11 of the 99 knowledge-base files in `documents/` carry a version
# number — `费用报销管理制度V2.1.txt`, `IT安全管理制度V3.1.txt`,
# `MYBI_V3.1_更新日志.txt` — and every one of them came back as
# `unsupported_file`, including the answer source of eval question `doc-01`.
# Refusing a version number is not protection, it is a hole in the corpus.
#
# A disguised type is still caught, just by the layers that actually work:
#   * the *final* suffix must be in `_ALLOWED_TYPES` (checked by
#     `inspect_upload_header`), so `report.exe` is out whatever precedes it;
#   * the file header must match that suffix, so a `policy.docx` full of `%PDF`
#     bytes is out;
#   * the bytes on disk are named `uuid + one whitelisted suffix`
#     (`build_storage_path`), so a double extension never exists on the
#     filesystem and can never be executed from there.
# The middle of the name survives only as the *display* filename, which the UI
# lists and a re-download reuses, and that is exactly where "looks like a
# document, is an executable" misleads a person. So this check is narrowed to a
# closed, explainable set: a middle segment that is itself a known document /
# executable / script / web / archive suffix, the four whitelisted document types
# included. Anything else between two dots —
# `V2.1`, `1_更新日志`, `Q3.预算` — is a naming habit, not a file type, and passes.
_DOUBLE_EXTENSION_BLOCKLIST = frozenset(
    {
        # the four knowledge-base types themselves: `policy.md.exe` and
        # `notes.txt.exe` are precisely the costumes this rule exists to catch
        ".txt", ".md", ".pdf", ".docx",
        # other documents and office containers
        ".doc", ".xls", ".xlsx", ".ppt", ".pptx",
        # windows executables, libraries and installers
        ".exe", ".dll", ".com", ".scr", ".msi", ".lnk", ".jar",
        # scripts
        ".js", ".vbs", ".bat", ".cmd", ".sh", ".ps1",
        # web-served content
        ".php", ".html", ".htm", ".svg",
        # layered archives: the `payload.tar.gz.exe` chain
        ".tar", ".gz", ".bz2", ".xz", ".zip", ".rar", ".7z",
    }
)


def sanitize_upload_filename(filename: str | None) -> str:
    value = (filename or "").strip()
    if not value or value in {".", ".."}:
        raise UploadSecurityError("upload filename is required")
    if "/" in value or "\\" in value:
        raise UploadSecurityError("upload filename must not contain path separators")
    safe = Path(value).name
    if safe != value:
        raise UploadSecurityError("upload filename must not contain path segments")
    if safe.startswith("."):
        raise UploadSecurityError("upload filename must not start with a dot")
    stem, _, final_suffix = safe.rpartition(".")
    for segment in stem.split("."):
        if f".{segment.lower()}" in _DOUBLE_EXTENSION_BLOCKLIST:
            raise UploadSecurityError(
                f"double extensions are not allowed: .{segment}.{final_suffix}"
            )
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
