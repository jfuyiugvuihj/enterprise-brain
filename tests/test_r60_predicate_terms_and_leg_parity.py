# -*- coding: utf-8 -*-
"""PGVector 唯一写路径：退役开关不能改变写入或重新启用遗留存储。

离线连接记录实际 SQL 与入库行，验证同名更新预读、向量写入和失败边界。
"""

from __future__ import annotations

import pytest

from app.rag import hot_index
from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

DIM = 8
MODEL = "nomic-embed-test"
DOC = "a.txt"
BODY = "一\n二"
IDS = ["a.txt_0", "a.txt_1"]

#: 写腿那五枚语句的固定形状（两档共用，本文件按它做逐字节对照）。
WRITE_LEG = ("scope_probe", "type_probe", "upsert_many", "commit", "close")


class RecordingCollection:
    """假遗留腿：每一次 get/add/delete 都留下参数原样，供"哪条腿被调用、调用几次"对账。"""

    name = "enterprise_docs"

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.adds: list[list[str]] = []
        self.deletes: list[list[str]] = []
        self.gets: list = []
        self.last_add: dict = {}

    def count(self) -> int:
        return len(self.rows)

    def get(self, where=None, ids=None, include=None, limit=None, offset=None):
        self.gets.append({"where": where, "ids": ids, "include": include})
        picked = sorted(self.rows.values(), key=lambda row: row["id"])
        if where:
            key, value = next(iter(where.items()))
            picked = [row for row in picked if (row["metadata"] or {}).get(key) == value]
        result = {
            "ids": [row["id"] for row in picked],
            "documents": [row["document"] for row in picked],
            "metadatas": [row["metadata"] for row in picked],
        }
        if include is not None:
            result["embeddings"] = [row["embedding"] for row in picked]
        return result

    def add(self, ids, documents, metadatas, embeddings=None):
        self.adds.append([str(item) for item in ids])
        self.last_add = {
            "ids": [str(item) for item in ids],
            "documents": list(documents),
            "metadatas": [dict(item or {}) for item in metadatas],
            "embeddings": [list(item) for item in embeddings] if embeddings else None,
        }
        for position, vector_id in enumerate(ids):
            self.rows[vector_id] = {
                "id": vector_id,
                "document": documents[position],
                "metadata": dict(metadatas[position] or {}),
                "embedding": list(embeddings[position]) if embeddings else [],
            }

    def delete(self, ids):
        self.deletes.append([str(item) for item in ids])
        for vector_id in ids:
            self.rows.pop(vector_id, None)

    def query(self, **kwargs):
        raise AssertionError("R60 的形状钉不去问检索")


class Result:
    def __init__(self, one=None, many=None):
        self._one, self._many = one, list(many or [])

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class RecordingConnection:
    """假 psycopg 连接：语句按 (标记, SQL 原文, 参数) 逐条记账，标记一律取 pg_store 真源。"""

    def __init__(self):
        self.statements: list[tuple[str, str, str]] = []
        self.upsert_rows: list[tuple] = []

    def label(self, text: str) -> str:
        if text == pg_store._SELECT_DOCUMENT_ROWS_SQL:
            return "doc_rows"
        if text == pg_store._SELECT_DOCUMENT_NAMES_SQL:
            return "doc_names"
        if "UPDATE vector_scope" in text:
            return "claim"
        if "FROM vector_scope" in text:
            return "scope_probe"
        if "pg_attribute" in text:
            return "type_probe"
        if "DELETE FROM chunk_vectors" in text:
            return "delete"
        if "INSERT INTO chunk_vectors" in text:
            return "upsert"
        if "count(*)" in text:
            return "count"
        return "other"

    @property
    def kinds(self):
        return [item[0] for item in self.statements]

    def execute(self, sql, params=None):
        text = str(sql)
        label = self.label(text)
        self.statements.append((label, text, repr(params)))
        if label == "scope_probe":
            return Result(one=(MODEL, DIM, "cosine"))
        if label == "type_probe":
            return Result(one={"format_type": "vector(%d)" % DIM})
        if label == "doc_rows":
            return Result(many=[])
        if label == "doc_names":
            return Result(many=[])
        if label == "count":
            return Result(one={"count": 0})
        return Result()

    def cursor(self):
        outer = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def executemany(self, sql, rows):
                text = str(sql)
                captured = [tuple(row) for row in rows]
                outer.upsert_rows.extend(captured)
                outer.statements.append(("upsert_many", text, repr(captured)))

        return Cursor()

    def commit(self):
        self.statements.append(("commit", "", ""))

    def rollback(self):
        self.statements.append(("rollback", "", ""))

    def close(self):
        self.statements.append(("close", "", ""))


class FakeSplitter:
    def split_text(self, content):
        return [item for item in content.split("\n") if item]


class FakeEmbedding:
    last_error = None

    def embed_documents(self, texts):
        return [[0.25] * DIM for _ in texts]

    def embed_query(self, text):
        return [0.25] * DIM


def _assemble(monkeypatch, *, backend, dual="on", stores=True):
    """装一台不碰 chromadb、不碰 psycopg 的 DocumentRetriever；``stores`` 摆 ``stores_vectors``。"""
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(DIM))
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, MODEL)
    monkeypatch.setattr(rt, "EMBEDDING_DIM", DIM)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, dual)
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, backend)
    pg_store.reset_vector_mirror_diagnostics()
    connection = RecordingConnection()
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: connection)
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    monkeypatch.setattr(DocumentRetriever, "stores_vectors",
                        property(lambda self: stores))
    instance = object.__new__(DocumentRetriever)
    instance.collection = RecordingCollection()
    instance.splitter = FakeSplitter()
    instance.embedding = FakeEmbedding()
    return instance, connection


def _write_once(monkeypatch, backend):
    instance, connection = _assemble(monkeypatch, backend=backend)
    ok, message = instance.add_document(DOC, BODY)
    assert ok is True, message
    return {"kinds": connection.kinds,
            "write_leg": connection.statements[-len(WRITE_LEG):],
            "upsert_rows": list(connection.upsert_rows),
            "legacy_adds": list(instance.collection.adds),
            "legacy_rows": instance.collection.count()}


# ---------------- 判据⑦(c) 第三形：``stores_vectors`` 单独是一枚牙，摘掉它必须红 ----------------


def test_retired_store_flag_cannot_redirect_writes(monkeypatch):
    """退役的无向量存储标志不能把行重定向到 JSON。"""
    instance, _connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                      dual="on", stores=False)
    assert instance._writes_go_to_pgvector() is True


def test_retired_store_flag_still_writes_pg_only(monkeypatch):
    """即使遗留标志为假，上传只写 PG。"""
    instance, connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                     dual="on", stores=False)

    ok, _message = instance.add_document(DOC, BODY)

    assert ok is True
    assert len(connection.upsert_rows) == 2
    assert connection.kinds.count("commit") == 1
    assert instance.collection.adds == []

def test_retired_switches_do_not_turn_off_pg_writes(monkeypatch):
    """生产已退出双写，旧开关为 off 时仍保持 PG 唯一写路径。"""
    instance, _connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                      dual="on", stores=True)
    assert instance._writes_go_to_pgvector() is True

    instance.collection = RecordingCollection()
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "off")
    assert instance._writes_go_to_pgvector() is True

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    assert instance._writes_go_to_pgvector() is True


# ------------------- 判据①的 A/B：两档之间只许差"遗留腿接不接行"那一格 -------------------


def test_the_postgres_leg_is_byte_identical_on_both_backend_positions(monkeypatch):
    """``INDEX_BACKEND`` 两档交给 PG 的语句原文与绑定参数逐字节等；停写不改 PG 那本账。"""
    chroma = _write_once(monkeypatch, indexing.INDEX_BACKEND_DEFAULT)
    pgvector = _write_once(monkeypatch, indexing.PGVECTOR_BACKEND)

    assert chroma["write_leg"][0:2] == pgvector["write_leg"][0:2]
    assert chroma["write_leg"][-3:] == pgvector["write_leg"][-3:], (
        "写腿那三枚语句在两档之间不一样了：SQL 原文或参数漂了一枚")
    assert [item[0] for item in chroma["write_leg"]] == list(WRITE_LEG)
    assert [item[0] for item in pgvector["write_leg"]] == list(WRITE_LEG)
    assert chroma["upsert_rows"] == pgvector["upsert_rows"], (
        "交进 chunk_vectors 的行本身在两档之间不同 —— 停写只该决定遗留腿接不接行")
    assert len(chroma["upsert_rows"]) == 2
    assert [str(row[0]) for row in chroma["upsert_rows"]] == IDS


def test_retired_backend_constant_does_not_reenable_legacy_leg(monkeypatch):
    """两种旧常量取值都只写 PG，不能悄悄恢复第二份向量库。"""
    chroma = _write_once(monkeypatch, indexing.INDEX_BACKEND_DEFAULT)
    pgvector = _write_once(monkeypatch, indexing.PGVECTOR_BACKEND)

    assert chroma["legacy_adds"] == []
    assert chroma["legacy_rows"] == 0
    assert pgvector["legacy_adds"] == []
    assert pgvector["legacy_rows"] == 0

    # 判据③那句问句是两档之间唯一被允许多出来的 PG 语句，而且只多这一句。
    assert chroma["kinds"].count("doc_rows") == 1
    assert pgvector["kinds"].count("doc_rows") == 1
    assert pgvector["kinds"][:4] == ["scope_probe", "type_probe", "doc_rows", "close"]
    assert pgvector["kinds"] == chroma["kinds"]


def test_dual_write_off_still_writes_pg(monkeypatch):
    """退役双写旋钮关闭后，文件上传仍写现役 PG。"""
    instance, connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                     dual="off", stores=True)

    assert instance._writes_go_to_pgvector() is True
    ok, _message = instance.add_document(DOC, BODY)
    assert ok is True
    assert len(connection.upsert_rows) == 2
    assert instance.collection.adds == []
