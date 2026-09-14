"""Transitional owner registry for protected chat sessions."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.agents.contracts import Principal


@dataclass
class SessionRecord:
    session_id: str
    owner_id: str
    status: str
    created_at: str


class SessionRegistry:
    """JSON-backed owner mapping until the canonical Session table is migrated."""

    def __init__(self, metadata_path: str | Path):
        self.metadata_path = Path(metadata_path).resolve()
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._records = self._load()

    def _load(self) -> dict[str, SessionRecord]:
        if not self.metadata_path.exists():
            return {}
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            return {
                raw["session_id"]: SessionRecord(**raw)
                for raw in payload.get("sessions", [])
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError, KeyError):
            return {}

    def _save(self) -> None:
        payload = {"sessions": [asdict(record) for record in self._records.values()]}
        fd, temp_name = tempfile.mkstemp(
            prefix=".session-metadata.",
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

    def bind(self, session_id: str, principal: Principal) -> SessionRecord:
        session_id = str(session_id or "").strip()
        if not session_id or not principal.user_id or principal.status != "active":
            raise PermissionError("an active principal and session id are required")
        with self._lock:
            existing = self._records.get(session_id)
            if existing is not None:
                if existing.status != "active" or existing.owner_id != str(principal.user_id):
                    raise PermissionError("session is not owned by the active principal")
                return existing
            record = SessionRecord(
                session_id=session_id,
                owner_id=str(principal.user_id),
                status="active",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._records[session_id] = record
            self._save()
            return record

    def get_active(self, session_id: str) -> SessionRecord | None:
        record = self._records.get(str(session_id or ""))
        return record if record is not None and record.status == "active" else None

    def is_owned_by(self, session_id: str, principal: Principal) -> bool:
        record = self.get_active(session_id)
        return bool(record and record.owner_id == str(principal.user_id))


session_registry = SessionRegistry(
    os.getenv("SESSION_REGISTRY_PATH", "./data/.session-metadata.json")
)
