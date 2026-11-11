"""Resource-ID based local file storage with containment and atomic writes."""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredFile:
    resource_id: str
    path: Path
    size: int
    sha256: str


class LocalFileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_resource_id(self, resource_id: str) -> str:
        value = (resource_id or "").strip()
        if not value or value in {".", ".."} or any(part in {".", ".."} for part in Path(value).parts):
            raise ValueError("invalid resource id")
        if Path(value).name != value or os.sep in value or (os.altsep and os.altsep in value):
            raise ValueError("resource id must be a single path component")
        return value

    def path_for(self, resource_id: str, suffix: str = "") -> Path:
        safe_id = self._safe_resource_id(resource_id)
        safe_suffix = suffix if not suffix or suffix.startswith(".") else f".{suffix}"
        path = (self.root / f"{safe_id}{safe_suffix}").resolve()
        if os.path.commonpath([str(self.root), str(path)]) != str(self.root):
            raise ValueError("storage path escapes root")
        return path

    def write_bytes(self, resource_id: str, content: bytes, suffix: str = "") -> StoredFile:
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        target = self.path_for(resource_id, suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{resource_id}.", dir=self.root)
        digest = hashlib.sha256(content).hexdigest()
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return StoredFile(resource_id, target, len(content), digest)

    def read_bytes(self, resource_id: str, suffix: str = "") -> bytes:
        return self.path_for(resource_id, suffix).read_bytes()

    def delete(self, resource_id: str, suffix: str = "") -> bool:
        path = self.path_for(resource_id, suffix)
        if not path.exists():
            return False
        path.unlink()
        return True
