"""Long-term memory with PostgreSQL fallback."""
import json
import os

import numpy as np

from app.common.logger import logger

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None
    dict_row = None

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_initialized = False
_MEMORY: dict[str, list[dict]] = {}


class _FakeResult:
    def __init__(self, rows=None, rowcount=0):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def execute(self, sql: str, params=None):
        text = sql.lower()
        params = params or ()
        if "delete from memories where user_id" in text:
            user_id = params[0] if params else ""
            removed = len(_MEMORY.pop(user_id, []))
            return _FakeResult(rowcount=removed)
        return _FakeResult()

    def commit(self):
        return None

    def close(self):
        return None


def _conn():
    if psycopg is None:
        return _FakeConn()
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _init():
    if psycopg is None:
        return
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding JSON,
                created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
        conn.commit()


def _ensure():
    global _initialized
    if _initialized:
        return
    if psycopg is not None:
        _init()
    _initialized = True


def _embed(texts):
    try:
        from app.rag.retriever import OllamaEmbeddings
        emb = OllamaEmbeddings()
        return emb.embed_documents(texts)
    except Exception as exc:
        logger.warning(f"[Memory] embedding fallback: {exc}")
        return None


def _cosine(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def remember(user_id: str, content: str) -> bool:
    if not content or not content.strip():
        return False
    emb = _embed([content])
    vec = emb[0] if emb else None
    try:
        _ensure()
        if psycopg is None:
            _MEMORY.setdefault(user_id, []).append({"content": content.strip(), "embedding": vec})
            return True
        with _conn() as conn:
            conn.execute(
                "INSERT INTO memories (user_id, content, embedding) VALUES (%s, %s, %s)",
                (user_id, content.strip(), json.dumps(vec) if vec else None),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.error(f"[Memory] write failed: {exc}")
        return False


def recall(user_id: str, query: str, k: int = 3) -> list[str]:
    try:
        _ensure()
        if psycopg is None:
            rows = _MEMORY.get(user_id, [])[-200:]
        else:
            with _conn() as conn:
                rows = conn.execute(
                    "SELECT content, embedding FROM memories WHERE user_id = %s ORDER BY id DESC LIMIT 200",
                    (user_id,),
                ).fetchall()
    except Exception as exc:
        logger.error(f"[Memory] read failed: {exc}")
        return []

    if not rows:
        return []

    qvec = None
    emb = _embed([query])
    if emb:
        qvec = emb[0]

    scored = []
    for r in rows:
        content = r["content"]
        score = 0.0
        if qvec and r.get("embedding"):
            try:
                score = _cosine(qvec, r["embedding"])
            except Exception:
                score = 0.0
        else:
            score = sum(1 for ch in query if ch in content) / max(len(query), 1)
        scored.append((score, content))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in scored[:k] if score > 0]
