"""Controlled metadata and delivery boundary for generated artifacts."""
from __future__ import annotations

import hashlib
import json
import mimetypes
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


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("artifact timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    owner_id: str
    department_ids: list[str]
    classification: str
    visibility: str
    storage_path: str
    filename: str
    content_sha256: str
    status: str
    created_at: str
    expires_at: str | None = None
    source_version_id: str | None = None

    @property
    def content_url(self) -> str:
        return f"/api/v1/artifacts/{self.artifact_id}/content"

    @property
    def download_url(self) -> str:
        return f"/api/v1/artifacts/{self.artifact_id}/download"

    @property
    def resource_scope(self) -> ResourceScope:
        return ResourceScope(
            resource_type="artifact",
            resource_id=self.artifact_id,
            owner_id=self.owner_id,
            department_ids=list(self.department_ids),
            classification=self.classification,
            visibility=self.visibility,
            version_id=self.source_version_id,
            status=self.status,
        )

    @property
    def media_type(self) -> str:
        return mimetypes.guess_type(self.filename)[0] or "application/octet-stream"

    def is_active(self, now: datetime | None = None) -> bool:
        if self.status != "active":
            return False
        expiry = _parse_datetime(self.expires_at)
        return expiry is None or expiry > (now or _utc_now())

    def public_payload(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content_url": self.content_url,
            "download_url": self.download_url,
            "expires_at": self.expires_at,
        }


class ArtifactRegistry:
    """A JSON-backed local registry until the canonical Artifact table is integrated."""

    def __init__(
        self,
        root: str | Path,
        metadata_path: str | Path | None = None,
        persistence=None,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = Path(metadata_path or self.root / ".artifact-metadata.json").resolve()
        self._lock = Lock()
        self.persistence = persistence
        self._records = self._load()

    def _contained_path(self, value: str | Path, *, must_exist: bool) -> Path:
        path = Path(value).resolve(strict=must_exist)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("artifact storage path escapes registry root") from exc
        return path

    def _load(self) -> dict[str, ArtifactRecord]:
        if not self.metadata_path.exists():
            return {}
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            records = {}
            for raw in payload.get("artifacts", []):
                record = ArtifactRecord(**raw)
                self._contained_path(record.storage_path, must_exist=False)
                records[record.artifact_id] = record
            return records
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        payload = {"artifacts": [asdict(record) for record in self._records.values()]}
        fd, temp_name = tempfile.mkstemp(
            prefix=".artifact-metadata.",
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
        artifact_type: str,
        principal: Principal,
        classification: str = "internal",
        visibility: str = "private",
        source_version_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> ArtifactRecord:
        if principal.status != "active" or not principal.user_id:
            raise PermissionError("active principal is required to create an artifact")
        if not artifact_type.strip():
            raise ValueError("artifact type is required")
        path = self._contained_path(storage_path, must_exist=True)
        departments = sorted(
            {
                value
                for value in [principal.department, *principal.department_ids]
                if value
            }
        )
        if not departments:
            raise ValueError("artifact owner must have a department scope")
        if expires_at is not None and expires_at.tzinfo is None:
            raise ValueError("artifact expiry must include a timezone")

        record = ArtifactRecord(
            artifact_id=uuid.uuid4().hex,
            artifact_type=artifact_type,
            owner_id=str(principal.user_id),
            department_ids=departments,
            classification=classification,
            visibility=visibility,
            storage_path=str(path),
            filename=path.name,
            content_sha256=_hash_file(path),
            status="active",
            created_at=_utc_now().isoformat(),
            expires_at=expires_at.astimezone(timezone.utc).isoformat() if expires_at else None,
            source_version_id=source_version_id,
        )
        with self._lock:
            self._records[record.artifact_id] = record
            self._save()
            if self.persistence is not None:
                self.persistence.upsert(
                    "artifacts",
                    record.artifact_id,
                    {
                        "artifact_id": record.artifact_id,
                        "owner_id": record.owner_id,
                        "resource_type": "artifact",
                        "resource_id": record.artifact_id,
                        "source_version_id": record.source_version_id,
                        "storage_key": record.storage_path,
                        "content_sha256": record.content_sha256,
                        "status": record.status,
                        "expires_at": record.expires_at,
                        "created_at": record.created_at,
                        "metadata": {
                            "artifact_type": record.artifact_type,
                            "filename": record.filename,
                            "department_ids": record.department_ids,
                            "classification": record.classification,
                            "visibility": record.visibility,
                        },
                    },
                )
        return record

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock:
            return self._records.get(artifact_id)

    def get_active(self, artifact_id: str) -> ArtifactRecord | None:
        record = self.get(artifact_id)
        if record is None or not record.is_active():
            return None
        path = self._contained_path(record.storage_path, must_exist=False)
        if not path.is_file():
            return None
        return record

    def list_active(
        self,
        *,
        artifact_type: str | None = None,
        owner_id: str | None = None,
    ) -> list[ArtifactRecord]:
        """Every record that could actually be delivered right now, newest first.

        ``get`` answers for any id and ``get_active`` for one id; a list needs the same
        two liveliness checks ``get_active`` already makes - the record has not been
        retired, has not expired, and its bytes are still on disk - because a catalogue
        that advertises an artifact which 404s on open has described a state this process
        did not produce. Deciding *who* may see a record stays out of here on purpose:
        that is the policy's job, and a second copy of the access rule in the registry is
        how two chains start disagreeing.
        """
        with self._lock:
            candidates = [
                record
                for record in self._records.values()
                if record.status == "active"
                and (artifact_type is None or record.artifact_type == artifact_type)
                and (owner_id is None or record.owner_id == str(owner_id))
            ]
        deliverable = [
            record
            for record in candidates
            if record.is_active()
            and self._contained_path(record.storage_path, must_exist=False).is_file()
        ]
        return sorted(deliverable, key=lambda item: (item.created_at, item.artifact_id), reverse=True)

    def soft_delete(self, artifact_id: str) -> bool:
        with self._lock:
            record = self._records.get(artifact_id)
            if record is None or record.status != "active":
                return False
            record.status = "deleted"
            self._save()
            if self.persistence is not None:
                self.persistence.upsert(
                    "artifacts",
                    record.artifact_id,
                    {
                        "artifact_id": record.artifact_id,
                        "owner_id": record.owner_id,
                        "resource_type": "artifact",
                        "resource_id": record.artifact_id,
                        "source_version_id": record.source_version_id,
                        "storage_key": record.storage_path,
                        "content_sha256": record.content_sha256,
                        "status": record.status,
                        "expires_at": record.expires_at,
                        "created_at": record.created_at,
                        "metadata": {
                            "artifact_type": record.artifact_type,
                            "filename": record.filename,
                            "department_ids": record.department_ids,
                            "classification": record.classification,
                            "visibility": record.visibility,
                        },
                    },
                )
            return True


_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
_PERSISTENCE = build_persistence_adapter()
artifact_registry = ArtifactRegistry(_STATIC_ROOT, persistence=_PERSISTENCE)


def register_artifact(
    storage_path: str | Path,
    *,
    artifact_type: str,
    principal: Principal,
    classification: str = "internal",
    visibility: str = "private",
    source_version_id: str | None = None,
    expires_at: datetime | None = None,
) -> ArtifactRecord:
    return artifact_registry.register(
        storage_path,
        artifact_type=artifact_type,
        principal=principal,
        classification=classification,
        visibility=visibility,
        source_version_id=source_version_id,
        expires_at=expires_at,
    )
