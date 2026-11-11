# -*- coding: utf-8 -*-
"""PGVector 唯一写路径的上传、同名更新、删除与目录读回回归。

假 PG 表按现役 SQL 列序储存行，旧 collection 只用于反证不应被调用。
全程离线，不连接 PostgreSQL 或模型。
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
#: 与 VectorMirror.build_rows 交回的那一行同列序（pg_store._UPSERT_COLUMNS）：假表按它记账，
#: 再把 pg_store 的两枚 SELECT 真源翻译回各自的列序。桩不抄 SQL，只读 SQL 常量。
UPSERT_COLUMNS = ("vector_id", "filename", "chunk_index", "content", "classification",
                  "department", "visibility", "content_sha256", "index_version_id", "embedding",
                  "embedding_model", "embedding_dimension", "distance_function")


class StoreError(RuntimeError):
    """注入失败用；形状照 tests/test_r58_pgvector_dual_write.py 的 MirrorError。"""


# ------------------------------------------------------------------ 遗留腿（假 Chroma）


class LegacyHandle:
    """一枚会记账的假目录：add/delete 真的改行数，count() 就是第④格读的那个数。"""

    name = "enterprise_docs"

    def __init__(self, rows=()):
        self.rows = {row["id"]: dict(row) for row in rows}
        self.adds: list[list[str]] = []
        self.deletes: list[list[str]] = []
        self.gets: list[dict] = []

    def count(self) -> int:
        return len(self.rows)

    def get(self, where=None, ids=None, include=None, limit=None, offset=None):
        self.gets.append({"where": where, "ids": ids})
        if ids is not None:
            picked = [self.rows[item] for item in ids if item in self.rows]
        else:
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
        raise AssertionError("R60 的写删判据不去问检索")


def legacy_row(vector_id, document="上一版的正文", metadata=None, embedding=None):
    return {
        "id": vector_id,
        "document": document,
        "metadata": metadata if metadata is not None
        else {"filename": vector_id.rsplit("_", 1)[0], "chunk_index": 0,
              "classification": 2, "department": "研发中心", "hash": "legacy-hash"},
        "embedding": embedding if embedding is not None else [0.5] * DIM,
    }


def pg_row(vector_id, filename, chunk_index, content, sha, *, classification=2,
           department="研发中心"):
    """按 _UPSERT_VECTOR_SQL 的列序摆一行，给假表当存量。"""
    return (vector_id, filename, chunk_index, content, classification, department,
            "private", sha,
            None, "[0.1]", MODEL, DIM, "cosine")


# -------------------------------------------------------------------- PG 那一腿（假表）


class PgTable:
    """chunk_vectors 的内存替身：按 vector_id 存行，行形状＝upsert 的列序。"""

    def __init__(self, rows=()):
        self.rows = {}
        for row in rows:
            self.rows[str(row[0])] = tuple(row)

    def _at(self, row, column):
        return row[UPSERT_COLUMNS.index(column)]

    def names(self):
        return sorted({str(self._at(row, "filename")) for row in self.rows.values()
                       if str(self._at(row, "filename"))})

    def ids_for(self, filename):
        picked = [row for row in self.rows.values()
                  if str(self._at(row, "filename")) == str(filename)]
        picked.sort(key=lambda row: (int(row[UPSERT_COLUMNS.index("chunk_index")]),
                                     str(row[0])))
        return picked

    def select_rows(self, filename):
        """按 pg_store._SELECT_DOCUMENT_ROWS_SQL 的列序交回，不在这儿做任何补默认值的事。"""
        return [(str(self._at(row, "vector_id")), self._at(row, "content"),
                 self._at(row, "chunk_index"), self._at(row, "classification"),
                 self._at(row, "department"), self._at(row, "content_sha256"))
                for row in self.ids_for(filename)]


class PgResult:
    def __init__(self, one=None, many=None):
        self._one, self._many = one, list(many or [])

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class PgCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def executemany(self, sql, rows):
        self.connection.upsert(sql, [tuple(row) for row in rows])


class PgConnection:
    """假 psycopg 连接：语句标记一律取 pg_store 的真源常量。"""

    def __init__(self, table, *, fail_on=()):
        self.table = table
        self.fail_on = set(fail_on)
        self.log: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def label_for(self, text):
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

    def _fire(self, label):
        self.log.append(label)
        if label in self.fail_on:
            raise StoreError("injected failure at " + label)

    def upsert(self, sql, rows):
        self._fire("upsert")
        for row in rows:
            self.table.rows[str(row[0])] = row

    def execute(self, sql, params=None):
        label = self.label_for(str(sql))
        self._fire(label)
        if label == "scope_probe":
            return PgResult(one=(MODEL, DIM, "cosine"))
        if label == "type_probe":
            return PgResult(one={"format_type": "vector(%d)" % DIM})
        if label == "doc_rows":
            return PgResult(many=self.table.select_rows(params[0]))
        if label == "doc_names":
            return PgResult(many=[(name,) for name in self.table.names()])
        if label == "delete":
            for vector_id in list(params[0]):
                self.table.rows.pop(str(vector_id), None)
        if label == "count":
            return PgResult(one={"count": len(self.table.rows)})
        return PgResult()

    def cursor(self):
        return PgCursor(self)

    def commit(self):
        self._fire("commit")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.log.append("rollback")

    def close(self):
        self.closes += 1


# ------------------------------------------------------------------------- 装配一台用例


class FakeSplitter:
    def split_text(self, content):
        return [item for item in content.split("\n") if item]


class FakeEmbedding:
    last_error = None

    def __init__(self, width=DIM):
        self.width = width

    def embed_documents(self, texts):
        return [[0.25] * self.width for _ in texts]

    def embed_query(self, text):
        return [0.25] * self.width


def _knob(monkeypatch, backend):
    """把读后端开关摆成用例要的那一档：``None`` ＝ 出厂（什么都不设）。"""
    if backend is None:
        monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
        monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)
    else:
        monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, backend)


def _assemble(monkeypatch, *, backend, dual="on", table=None, legacy=None,
              fail_on=(), hot=False):
    """装一台不碰 chromadb、不碰 psycopg 的 DocumentRetriever，返回 (实例, 假连接, 假表)。

    热集默认关掉：本文件判的是"行落到哪一库"，热集那一层归 test_r44_* 那族管。
    """
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(DIM))
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, MODEL)
    monkeypatch.setattr(rt, "EMBEDDING_DIM", DIM)
    if dual is None:
        monkeypatch.delenv(pg_store.DUAL_WRITE_ENV, raising=False)
    else:
        monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, dual)
    _knob(monkeypatch, backend)
    pg_store.reset_vector_mirror_diagnostics()
    table = PgTable() if table is None else table
    connection = PgConnection(table, fail_on=fail_on)
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: connection)
    instance = object.__new__(DocumentRetriever)
    instance.collection = LegacyHandle() if legacy is None else legacy
    instance.splitter = FakeSplitter()
    instance.embedding = FakeEmbedding()
    monkeypatch.setattr(DocumentRetriever, "stores_vectors",
                        property(lambda self: True))
    noted: dict = {}
    if hot:
        monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: True)

        class _Hot:
            def note_write(self, **kwargs):
                noted["write"] = [str(item) for item in (kwargs.get("ids") or [])]

            def note_delete(self, ids, *, scope_key=None):
                noted["delete"] = [str(item) for item in ids]

            def reset(self, reason=""):
                noted["reset"] = reason

        monkeypatch.setattr(hot_index, "get_hot_index", lambda: _Hot())
    else:
        monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    instance._r60_noted = noted
    return instance, connection, table


# ------------------------------------------------------------- 判据①：写路径唯一化 + 一字不改


def test_pgvector_primary_write_leaves_the_legacy_store_empty(monkeypatch):
    """判据①第一半（＝第④格的离线形状）：PG +2 行、Chroma +0 行，两枚计数同时现取。"""
    instance, _connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    before_pg, before_legacy = len(table.rows), instance.collection.count()

    ok, _message = instance.add_document("b.txt", "三\n四")

    assert ok is True
    assert (len(table.rows), instance.collection.count()) == (before_pg + 2, before_legacy)
    assert instance.collection.adds == [], "停写态里遗留腿仍被交了一次 add"


def test_default_backend_writes_only_pg(monkeypatch):
    """默认配置下上传的文本块只进入 PG。"""
    instance, connection, table = _assemble(monkeypatch, backend=indexing.INDEX_BACKEND_DEFAULT)

    ok, _message = instance.add_document("a.txt", "一\n二")

    assert ok is True
    assert instance.collection.count() == 0
    assert len(table.rows) == 2
    assert instance.collection.adds == []
    assert "upsert" in connection.log and "commit" in connection.log


def test_unset_switches_still_write_pg(monkeypatch):
    """不设置已退役的两个旋钮也不能把上传退回旧库。"""
    instance, connection, table = _assemble(monkeypatch, backend=None, dual=None)

    instance.add_document("a.txt", "一\n二")

    assert instance.collection.count() == 0
    assert "upsert" in connection.log and "commit" in connection.log
    assert len(table.rows) == 2


def test_retired_dual_write_off_still_writes_pg(monkeypatch):
    """双写旋钮关闭后上传仍落 PG，不能成功回执却零写入。"""
    instance, _connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                             dual="off")

    ok, _message = instance.add_document("b.txt", "三\n四")

    assert ok is True
    assert instance.collection.count() == 0
    assert len(table.rows) == 2


def test_retired_switches_cannot_reenable_legacy_writes(monkeypatch):
    """旧配置值变化时，写目标始终只有 PG。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    assert instance._writes_go_to_pgvector() is True
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    assert instance._writes_go_to_pgvector() is True
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, "not-a-backend")
    assert instance._writes_go_to_pgvector() is True


def test_failed_pg_write_does_not_report_success_or_write_legacy(monkeypatch):
    """PG 写失败时不能将任务伪装成成功，也不能改写旧 collection。"""
    instance, connection, table = _assemble(
        monkeypatch, backend=indexing.PGVECTOR_BACKEND, fail_on=("upsert",))
    with pytest.raises(rt.VectorWriteRejectedError) as caught:
        instance.add_document("a.txt", "一\n二")
    assert caught.value.reason == pg_store.REASON_VECTOR_MIRROR_WRITE_FAILED
    assert table.rows == {}
    assert instance.collection.adds == []
    assert connection.rollbacks == 1


def test_pg_unavailable_does_not_fall_back_to_legacy_write(monkeypatch):
    """PG 连接失败时，旧 collection 不得代收新文档。"""
    instance, connection, table = _assemble(
        monkeypatch, backend=indexing.PGVECTOR_BACKEND, fail_on=("scope_probe",))
    with pytest.raises(rt.VectorWriteRejectedError) as caught:
        instance.add_document("a.txt", "一\n二")
    assert caught.value.reason == pg_store.REASON_VECTOR_MIRROR_UNAVAILABLE
    assert table.rows == {}
    assert instance.collection.adds == []


# --------------------------------------------------------------------- 判据③：删除那一腿


def test_delete_asks_postgres_when_the_legacy_store_holds_nothing(monkeypatch):
    """判据③要害：停写之后新行只住 PG。

    只问遗留腿的删除在这里一无所获、静悄悄 return，端点报删除成功，而那份"已删除"的文档
    每一行还在 chunk_vectors 里被检索 —— 本用例钉的就是这条链子能不能真删掉。
    """
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    instance.add_document("b.txt", "三\n四")
    assert instance.collection.count() == 0 and len(table.rows) == 2
    connection.log.clear()

    instance.delete_document("b.txt")

    assert "doc_rows" in connection.log, "删除之前没问 PG 有哪些行"
    assert "delete" in connection.log
    assert len(table.rows) == 0, "PG 那一腿没被删干净"
    assert instance.collection.deletes == [], "遗留腿没持有的东西，不许假装删过"


def test_delete_only_changes_the_active_pg_store(monkeypatch):
    """旧归档行不参与现役删除，PG 中对应文档必须删净。"""
    table = PgTable([pg_row("a.txt_0", "a.txt", 0, "上一版的正文", "legacy-hash")])
    legacy = LegacyHandle([legacy_row("a.txt_0")])
    instance, connection, _t = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                         table=table, legacy=legacy, hot=True)

    instance.delete_document("a.txt")

    assert legacy.count() == 1
    assert len(table.rows) == 0
    assert instance.collection.deletes == []
    assert "delete" in connection.log
    assert instance._r60_noted.get("delete") == ["a.txt_0"]


def test_a_pg_only_delete_is_not_refused_for_lacking_a_legacy_snapshot(monkeypatch):
    """判据③：只住在 PG 的行没有 Chroma 副本；不许因为"读不出旧向量快照"而拒删。

    那枚闸门（REASON_VECTOR_MIRROR_UNAVAILABLE）护的是"回滚时无货可放回"；遗留腿本来没有
    这一批行，就没有可放回的东西，硬读一份空快照再把闸门扳下来是把它用成了障碍。
    """
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    instance.add_document("b.txt", "三\n四")
    connection.log.clear()

    instance.delete_document("b.txt")

    assert len(table.rows) == 0
    assert "doc_rows" in connection.log and "delete" in connection.log


def test_reupload_under_pgvector_retires_the_old_pg_rows(monkeypatch):
    """判据①＋③：同名重传在停写态里必须"删旧 PG 行、只写新 PG 行"，遗留腿一根毛都不涨。"""
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    instance.add_document("b.txt", "三\n四")
    legacy_after_first = instance.collection.count()
    connection.log.clear()

    ok, _message = instance.add_document("b.txt", "三\n四\n五")

    assert ok is True
    assert len(table.rows) == 3, "旧行没被裁掉：同名重传在 PG 里叠成了两套正文"
    assert {str(row[0]) for row in table.rows.values()} == {"b.txt_0", "b.txt_1", "b.txt_2"}
    assert instance.collection.count() == legacy_after_first
    assert "delete" in connection.log


def test_unchanged_content_is_skipped_from_the_pg_hash(monkeypatch):
    """判据③的边角："内容没变就跳过"读的那枚 hash 必须来自持有行的那一腿。"""
    instance, _connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    content = "三\n四"
    instance.add_document("b.txt", content)
    rows_before = len(table.rows)

    ok, message = instance.add_document("b.txt", content)

    assert ok is False and "未变化" in message
    assert len(table.rows) == rows_before


def test_undo_does_not_delete_rows_the_legacy_leg_never_held(monkeypatch):
    """判据②＋③：补偿只能撤"本次真写过的"。停写态里遗留腿没写过，就不许去撤它。"""
    instance, connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    legacy = instance.collection
    legacy.rows = {"b.txt_0": legacy_row("b.txt_0")}
    mirror = instance._open_vector_mirror()
    snapshot = {"ids": ["b.txt_0"], "documents": ["上一版的正文"],
                "metadatas": [legacy_row("b.txt_0")["metadata"]],
                "embeddings": [[0.5] * DIM]}

    instance._undo_vector_write(mirror, ["b.txt_0"], snapshot, stale_deleted=False)

    assert legacy.deletes == [], "撤销一次没发生过的写入，等于自己制造一次删除"
    assert "b.txt_0" in legacy.rows
    assert connection.rollbacks == 1, "PG 那一腿的回滚仍是硬要求"


def test_a_postgres_that_cannot_answer_is_a_refusal_not_a_fallback(monkeypatch):
    """PG 查行失败时删除不得改动旧集合，也不得报告成功。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              legacy=LegacyHandle([legacy_row("a.txt_0")]),
                                              fail_on=("doc_rows",))

    with pytest.raises(StoreError):
        instance.delete_document("a.txt")

    assert instance.collection.deletes == [], "拒答之前一个字节都不许动"


def test_document_chunks_follows_the_store_that_holds_the_rows(monkeypatch):
    """判据③的读回面：发布记录读回的必须是当前那一版正文，不是遗留目录里的上一版。"""
    legacy = LegacyHandle([legacy_row("b.txt_0")])
    instance, _connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                             legacy=legacy)
    instance.add_document("b.txt", "三\n四")
    legacy.gets.clear()

    rows = instance.document_chunks("b.txt")

    assert [row["content"] for row in rows] == ["三", "四"]
    assert [row["vector_id"] for row in rows] == ["b.txt_0", "b.txt_1"]
    assert rows[0]["hash"], "发布记录的 content_hash 取自 PG 的 content_sha256"
    assert legacy.gets == [], "停写态的读回不许再去问遗留目录"
    assert len(table.rows) == 2


def test_list_documents_follows_the_same_answer(monkeypatch):
    """资料目录只列 PG 中的文档，旧集合的孤儿名不应出现。"""
    legacy = LegacyHandle([legacy_row("a.txt_0")])
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              legacy=legacy)
    instance.add_document("b.txt", "三\n四")

    assert instance.list_documents() == ["b.txt"]

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    assert instance.list_documents() == ["b.txt"]


def test_delete_invalidates_cached_ids_without_dual_writing(monkeypatch):
    """PG 删除通知热集失效，但 PG 上传不能向旧集合双写。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              hot=True)

    instance.add_document("b.txt", "三\n四")

    assert instance._r60_noted.get("write") is None
    assert instance.collection.adds == []
    instance.delete_document("b.txt")
    assert instance._r60_noted.get("delete") == ["b.txt_0", "b.txt_1"]
