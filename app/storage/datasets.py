"""Transitional local Dataset metadata with resource-scope support."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.agents.contracts import Principal, ResourceScope
from app.storage.persistence import build_persistence_adapter


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class DatasetRecord:
    dataset_id: str
    filename: str
    owner_id: str
    department_ids: list[str]
    classification: str
    visibility: str
    storage_path: str
    content_sha256: str
    status: str
    created_at: str
    version_id: str

    @property
    def resource_scope(self) -> ResourceScope:
        return ResourceScope(
            resource_type="dataset",
            resource_id=self.dataset_id,
            owner_id=self.owner_id,
            department_ids=list(self.department_ids),
            classification=self.classification,
            visibility=self.visibility,
            version_id=self.version_id,
            status=self.status,
        )


class DatasetRegistry:
    """JSON-backed transition registry until Dataset/DatasetVersion tables are active."""

    def __init__(
        self,
        root: str | Path,
        metadata_path: str | Path | None = None,
        persistence=None,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = Path(metadata_path or self.root / ".dataset-metadata.json").resolve()
        self._lock = Lock()
        self.persistence = persistence
        self._records = self._load()

    def _contained_path(self, value: str | Path, *, must_exist: bool) -> Path:
        path = Path(value).resolve(strict=must_exist)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("dataset storage path escapes registry root") from exc
        return path

    def _load(self) -> dict[str, DatasetRecord]:
        if not self.metadata_path.exists():
            return {}
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            records = {}
            for raw in payload.get("datasets", []):
                record = DatasetRecord(**raw)
                self._contained_path(record.storage_path, must_exist=False)
                records[record.dataset_id] = record
            return records
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        payload = {"datasets": [asdict(record) for record in self._records.values()]}
        fd, temp_name = tempfile.mkstemp(
            prefix=".dataset-metadata.",
            suffix=".json",
            dir=self.metadata_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.metadata_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def register(
        self,
        storage_path: str | Path,
        *,
        principal: Principal,
        filename: str | None = None,
        classification: str = "internal",
        visibility: str = "private",
    ) -> DatasetRecord:
        if principal.status != "active" or not principal.user_id:
            raise PermissionError("active principal is required to register a dataset")
        path = self._contained_path(storage_path, must_exist=True)
        logical_filename = Path(filename or path.name).name
        if not logical_filename or logical_filename in {".", ".."}:
            raise ValueError("dataset filename is required")
        departments = sorted(
            {
                value
                for value in [principal.department, *principal.department_ids]
                if value
            }
        )
        if not departments:
            raise ValueError("dataset owner must have a department scope")

        with self._lock:
            if self.get_active_by_filename(logical_filename) is not None:
                raise ValueError("an active dataset already uses this filename")
            dataset_id = uuid.uuid4().hex
            record = DatasetRecord(
                dataset_id=dataset_id,
                filename=logical_filename,
                owner_id=str(principal.user_id),
                department_ids=departments,
                classification=classification,
                visibility=visibility,
                storage_path=str(path),
                content_sha256=_hash_file(path),
                status="active",
                created_at=_utc_now().isoformat(),
                version_id=f"{dataset_id}:v1",
            )
            self._records[dataset_id] = record
            self._save()
            if self.persistence is not None:
                self.persistence.upsert(
                    "datasets",
                    record.dataset_id,
                    {
                        "dataset_id": record.dataset_id,
                        "owner_id": record.owner_id,
                        "filename": record.filename,
                        "department_ids": record.department_ids,
                        "classification": record.classification,
                        "visibility": record.visibility,
                        "storage_key": record.storage_path,
                        "content_sha256": record.content_sha256,
                        "status": record.status,
                        "current_version_id": record.version_id,
                        "created_at": record.created_at,
                        "metadata": {"version_id": record.version_id},
                    },
                )
            return record

    def get_active_by_filename(self, filename: str) -> DatasetRecord | None:
        candidates = [
            record
            for record in self._records.values()
            if record.filename == filename and record.status == "active"
        ]
        if not candidates:
            return None
        record = max(candidates, key=lambda item: item.created_at)
        path = self._contained_path(record.storage_path, must_exist=False)
        return record if path.is_file() else None

    def active_records(self) -> list[DatasetRecord]:
        records = []
        for record in self._records.values():
            if record.status != "active":
                continue
            path = self._contained_path(record.storage_path, must_exist=False)
            if path.is_file():
                records.append(record)
        return sorted(records, key=lambda item: item.created_at, reverse=True)


_DATA_ROOT = Path(os.getenv("DATA_DIR", "./data"))
_PERSISTENCE = build_persistence_adapter()
dataset_registry = DatasetRegistry(_DATA_ROOT, persistence=_PERSISTENCE)
