"""Versioned index publication with atomic local metadata and rollback."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from uuid import uuid4


@dataclass
class IndexVersion:
    index_version_id: str
    index_id: str
    source_version_id: str
    backend: str
    chunk_count: int
    checksum: str
    status: str
    created_at: str
    published_at: str | None = None


class IndexRegistry:
    def __init__(self, metadata_path: str | Path):
        self.metadata_path = Path(metadata_path).resolve()
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._versions: dict[str, IndexVersion] = {}
        self._current: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.metadata_path.exists():
            return
        payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self._versions = {
            raw["index_version_id"]: IndexVersion(**raw)
            for raw in payload.get("versions", [])
        }
        self._current = {
            str(key): str(value)
            for key, value in (payload.get("current") or {}).items()
        }

    def _save(self) -> None:
        payload = {
            "versions": [asdict(version) for version in self._versions.values()],
            "current": self._current,
        }
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.metadata_path.name}.",
            suffix=".tmp",
            dir=self.metadata_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.metadata_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create_version(
        self,
        *,
        index_id: str,
        source_version_id: str,
        backend: str,
        chunk_count: int,
        checksum: str,
    ) -> IndexVersion:
        if not index_id.strip() or not source_version_id.strip():
            raise ValueError("index_id and source_version_id are required")
        if backend not in {"chroma", "pgvector"}:
            raise ValueError("unsupported index backend")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("index checksum must be a SHA-256 hex digest")
        version = IndexVersion(
            index_version_id=f"{index_id}:v{uuid4().hex}",
            index_id=index_id,
            source_version_id=source_version_id,
            backend=backend,
            chunk_count=int(chunk_count),
            checksum=checksum,
            status="building",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._versions[version.index_version_id] = version
            self._save()
        return version

    def validate(self, index_version_id: str) -> IndexVersion:
        with self._lock:
            version = self._versions[index_version_id]
            if version.chunk_count <= 0:
                raise ValueError("index chunk_count must be greater than zero")
            if not re.fullmatch(r"[0-9a-f]{64}", version.checksum):
                raise ValueError("index checksum is invalid")
            version.status = "validated"
            self._save()
            return version

    def publish(self, index_version_id: str) -> IndexVersion:
        with self._lock:
            version = self.validate(index_version_id)
            previous_id = self._current.get(version.index_id)
            if previous_id and previous_id in self._versions:
                self._versions[previous_id].status = "superseded"
            version.status = "published"
            version.published_at = datetime.now(timezone.utc).isoformat()
            self._current[version.index_id] = version.index_version_id
            self._save()
            return version

    def current(self, index_id: str) -> IndexVersion:
        with self._lock:
            version_id = self._current.get(index_id)
            if not version_id:
                raise KeyError(index_id)
            return self._versions[version_id]

    def rollback(self, index_id: str, index_version_id: str) -> IndexVersion:
        with self._lock:
            version = self._versions[index_version_id]
            if version.index_id != index_id:
                raise ValueError("index version belongs to another index")
            if version.status not in {"published", "superseded"}:
                raise ValueError("only a published index version can be restored")
            current_id = self._current.get(index_id)
            if current_id and current_id in self._versions:
                self._versions[current_id].status = "superseded"
            version.status = "published"
            version.published_at = datetime.now(timezone.utc).isoformat()
            self._current[index_id] = version.index_version_id
            self._save()
            return version
