"""
长期记忆 —— PostgreSQL 持久化（决策 1：存数据库，重启不丢）

不依赖 pgvector：向量存为 JSON，召回时在 Python 内做余弦排序
（单用户记忆量小，线性扫描足够，且避免额外扩展依赖）。
"""
import os
import json
import numpy as np
import psycopg
from psycopg.rows import dict_row
from app.common.logger import logger

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")


def _conn():
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _init():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding JSON,
                created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
        conn.commit()


_initialized = False


def _ensure():
    """懒建表：导入时不连库，首次使用时才建（无库时抛异常由调用方降级）"""
    global _initialized
    if not _initialized:
        _init()
        _initialized = True


def _embed(texts):
    """懒加载 Ollama embedding，失败返回 None 列表（降级为关键词召回）"""
    try:
        from app.rag.retriever import OllamaEmbeddings
        emb = OllamaEmbeddings()
        return emb.embed_documents(texts)
    except Exception as e:
        logger.warning(f"[Memory] embedding 失败，降级关键词召回: {e}")
        return None


def _cosine(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def remember(user_id: str, content: str) -> bool:
    """写入一条长期记忆"""
    if not content or not content.strip():
        return False
    emb = _embed([content])
    vec = emb[0] if emb else None
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                "INSERT INTO memories (user_id, content, embedding) VALUES (%s, %s, %s)",
                (user_id, content.strip(), json.dumps(vec) if vec else None),
            )
            conn.commit()
        logger.info(f"[Memory] 记住 ({user_id}): {content[:40]}")
        return True
    except Exception as e:
        logger.error(f"[Memory] 写入失败: {e}")
        return False


def recall(user_id: str, query: str, k: int = 3) -> list[str]:
    """召回与 query 相关的长期记忆（语义优先，失败退关键词/最新）"""
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT content, embedding FROM memories WHERE user_id = %s ORDER BY id DESC LIMIT 200",
                (user_id,),
            ).fetchall()
    except Exception as e:
        logger.error(f"[Memory] 读取失败: {e}")
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
        if qvec and r["embedding"]:
            try:
                score = _cosine(qvec, r["embedding"])
            except Exception:
                score = 0.0
        else:
            # 关键词降级：重叠字数
            score = sum(1 for ch in query if ch in content) / max(len(query), 1)
        scored.append((score, content))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k] if _ > 0]  # 只返回有相关度的
