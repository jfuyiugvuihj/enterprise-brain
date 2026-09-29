"""Transitional owner registry for protected chat sessions.

R495 turned one fact about this module from an accident into a contract: this ledger is
keyed on the **username** namespace. Before R495 that was true only because the user
lookup in ``app/common/auth.py`` happens to leave ``id`` out of its SELECT, so
``Principal.from_user`` fell back to the username. Add ``id`` to that SELECT and
``principal.user_id`` silently becomes a bigint, every ledger row stops matching, and
``GET /api/v1/sessions`` answers 200 with ``[]`` for everybody -- no error, no warning,
no failed status code. From R495 the namespace is declared once
(:data:`SESSION_OWNER_NAMESPACE`), every owner key -- write leg and read leg alike -- is
produced by one formula (:func:`session_owner_key`), and a principal whose key left that
namespace while the ledger still holds rows written under its username is refused out
loud instead of being read as "owns nothing".
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.agents.contracts import Principal
from app.common.logger import logger

#: R495 · 会话归属键命名空间的唯一真源：全仓只有这里把「台账按哪套键认人」写成字面。
#: 想知道归属键是谁就读这一枚；要换命名空间也只改这一枚，且必须与台账迁移同单进行。
SESSION_OWNER_NAMESPACE = "username"
#: 另一套键的名字：那句查人 SELECT 一旦补上 `id`，`app/agents/contracts.py` 的
#: `Principal.from_user` 就优先取 `user["id"]`，归属键当场从用户名换到这一套。
OWNER_NAMESPACE_FROM_USER_ID = "user_id"


class SessionOwnerNamespaceError(PermissionError):
    """台账上的归属键与这枚 principal 的归属键不再是同一套命名空间。

    这不是新造的对外码：`app/api/v1/chat.py` 的写腿本来就把 `bind()` 抛出的
    `PermissionError` 折成 403 `permission_denied`，本单沿用那一格口径，只让这种拒绝在
    日志与 traceback 里留下自己的名字。宁可拒写也不静默：命名空间一换，读腿会对全员回
    空列表，那交出去的是「你没有会话」这句假话，不是一次拒绝。
    """


def session_owner_key(principal: Principal) -> str:
    """R495 · 归属键的唯一算式：全仓只有这里把一枚 principal 变成台账里的 owner 键。

    🔴 不许长出第二把尺。写腿（`bind`）与读腿（`is_owned_by`）都从这里取键，所以命名空间
    要么两边一起换、要么一起不换。它「今天等于用户名」这件事由 `SESSION_OWNER_NAMESPACE`
    声明，并由 `tests/test_r495_session_owner_namespace_is_declared.py` 拿
    `app/common/auth.py` 真源那句 SELECT 对账——不再靠 SELECT 恰好少一列。
    """
    return str(principal.user_id or "").strip()


def session_owner_namespace(principal: Principal) -> str:
    """现读这枚 principal 的归属键落在哪套命名空间。它不判归属，只说这把键是谁。

    交回空串 = 这把键压根不存在（无身份主体）：那既不属于 username 也不属于 user_id，
    调用方按「无从判定」处理，不许把它当成某一档。
    """
    key = session_owner_key(principal)
    if not key:
        return ""
    username = str(principal.username or "").strip()
    if username and username == key:
        return SESSION_OWNER_NAMESPACE
    return OWNER_NAMESPACE_FROM_USER_ID


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
        owner_key = session_owner_key(principal)
        if not session_id or not owner_key or principal.status != "active":
            raise PermissionError("an active principal and session id are required")
        drift = self._owner_key_drift(principal)
        if drift:
            # 写腿当场响。这一格若放行，台账就长出一套新键，而读腿会替全员把它读成空列表。
            logger.error(f"[Sessions] R495 归属键命名空间漂移，写腿拒: {drift}")
            raise SessionOwnerNamespaceError(drift)
        with self._lock:
            existing = self._records.get(session_id)
            if existing is not None:
                if existing.status != "active" or existing.owner_id != owner_key:
                    raise PermissionError("session is not owned by the active principal")
                return existing
            record = SessionRecord(
                session_id=session_id,
                owner_id=owner_key,
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
        if record is None:
            return False
        owned = record.owner_id == session_owner_key(principal)
        if not owned:
            # 读腿不 raise：R484 把「不是你的会话要像不存在一样」钉成了 False（404 / 不进出口），
            # 在这里改成报错就是拿一种新形状换掉那格既有判定。但也不许无声：命名空间漂了与
            # 「这个人确实没有会话」在出口上长得一模一样，只有证词能把两者分开。
            drift = self._owner_key_drift(principal)
            if drift:
                logger.error(f"[Sessions] R495 归属键命名空间漂移，读腿按不属于交回: {drift}")
        return owned

    def _owner_keys_on_ledger(self) -> list[str]:
        """台账上当前挂着的所有归属键。只用来出证词，不参与归属判定，因此不是第二把尺。"""
        with self._lock:
            return [record.owner_id for record in self._records.values()]

    def _owner_key_drift(self, principal: Principal) -> str:
        """命名空间被换掉的证词；没换则交回空串。它只出证词，从不判归属。

        只看一件事：这枚 principal 的键不在 `SESSION_OWNER_NAMESPACE` 声明的那套里，而台账
        上已经有一行恰好拿它的**用户名**当归属键——那就是同一个人此刻有两套键。今天真库那份
        台账（`owner_id` 全是用户名字符串）走的就是这一形，所以这条证词在离线夹具上同样成立：
        它比的是台账自己的字节与 principal 自己的两个字段，不连库、不打出口、不落新键。
        """
        if session_owner_namespace(principal) == SESSION_OWNER_NAMESPACE:
            return ""
        username = str(principal.username or "").strip()
        if not username:
            return ""
        keys = self._owner_keys_on_ledger()
        rows = keys.count(username)
        if not rows:
            return ""
        return (
            "owner-key namespace moved off %r: this principal resolves to the %r namespace "
            "while the ledger already holds %d row(s) keyed on its username (%d row(s) on the "
            "ledger); every read leg would answer empty for everybody -- migrate the ledger "
            "and SESSION_OWNER_NAMESPACE in the same change"
            % (
                SESSION_OWNER_NAMESPACE,
                OWNER_NAMESPACE_FROM_USER_ID,
                rows,
                len(keys),
            )
        )


session_registry = SessionRegistry(
    os.getenv("SESSION_REGISTRY_PATH", "./data/.session-metadata.json")
)
