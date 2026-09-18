"""R58 判据⑤：Chroma ⇄ PGVector 双写的离线可证部分。

本文件不连真实 PostgreSQL、不起服务、不写磁盘上的 Chroma 目录：所有 PG 语句都落在
FakeConnection 上，它把每一条 SQL 记进 statements，并可按令牌注入失败。
"两侧都不落地"在这里的可证形式是：PG 侧 rollback 计数 +1 且 commit 计数为 0
（psycopg3 在第一句话开事务、到 commit() 才可见，回滚即"这一行从未存在"），
Chroma 侧是 FakeCollection 里最终没有这一条 id。

每条用例都钉着一处具体实现，删掉那处实现本用例必须变红（反证刀清单见交付说明）。
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from app.db import migrations as mig
from app.rag import indexing, pg_store, retriever

DIM = 8  # 与真实 768 无关：镜像这条腿只认库口径，见 _scope_env


class MirrorError(RuntimeError):
    """替代 psycopg / chromadb 的报错，只用来触发实现里的 except 分支。"""


class FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [] if self._row is None else [self._row]

    @property
    def rowcount(self):
        return 0


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def executemany(self, sql, rows):
        rows = [tuple(row) for row in rows]
        self.connection._hit(sql, rows)
        self.connection.row_count += len(rows)


class FakeConnection:
    """假 psycopg 连接：记录语句、按令牌注入失败、统计事务边界。"""

    MARKERS = {
        "scope_probe": "FROM vector_scope",
        "type_probe": "pg_attribute",
        "claim": "UPDATE vector_scope",
        "upsert": "INSERT INTO chunk_vectors",
        "delete": "DELETE FROM chunk_vectors",
    }

    def __init__(self, *, scope_row, column_type, fail_on=(), timeline=None):
        self.scope_row = scope_row
        self.column_type = column_type
        self.fail_on = set(fail_on)
        self.timeline = timeline if timeline is not None else []
        self.statements: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self.row_count = 0

    def _label(self, sql):
        for label, needle in self.MARKERS.items():
            if needle in sql:
                return label
        return "other"

    def _hit(self, sql, params=None):
        self.statements.append((sql, params))
        label = self._label(sql)
        self.timeline.append(label)
        if label in self.fail_on:
            raise MirrorError(f"injected failure at {label}")

    def execute(self, sql, params=None):
        self._hit(sql, params)
        if "FROM vector_scope" in sql:
            return FakeResult(self.scope_row)
        if "pg_attribute" in sql:
            return FakeResult({"format_type": self.column_type})
        if "count(*)" in sql:
            return FakeResult({"count": self.row_count})
        return FakeResult(None)

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.timeline.append("commit")
        if "commit" in self.fail_on:
            raise MirrorError("injected failure at commit")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.timeline.append("rollback")

    def close(self):
        self.closes += 1


class FakeSplitter:
    def split_text(self, content):
        return [item for item in content.split("\n") if item]


class FakeEmbedding:
    """替掉 Ollama：不发请求，只给宽度正确的非零向量。"""

    last_error = None

    def __init__(self, width):
        self.width = width

    def embed_documents(self, texts):
        return [[0.25] * self.width for _ in texts]

    def embed_query(self, text):
        return [0.25] * self.width


class FakeCollection:
    """假 Chroma collection：只在内存里记账，绝不落盘。"""

    def __init__(self, rows=(), *, fail_add=False, fail_delete=False, timeline=None):
        self.rows = {row["id"]: row for row in rows}
        self.fail_add = fail_add
        self.fail_delete = fail_delete
        self.timeline = timeline if timeline is not None else []

    def get(self, ids=None, where=None, include=None):
        if ids is not None:
            picked = [self.rows[item] for item in ids if item in self.rows]
        else:
            key, value = next(iter(where.items()))
            picked = [row for row in self.rows.values() if row["metadata"].get(key) == value]
        result = {
            "ids": [row["id"] for row in picked],
            "documents": [row["document"] for row in picked],
            "metadatas": [row["metadata"] for row in picked],
        }
        if include is not None:
            result["embeddings"] = [row["embedding"] for row in picked]
        return result

    def add(self, ids, documents, metadatas, embeddings=None):
        self.timeline.append("chroma:add")
        if self.fail_add:
            raise MirrorError("injected chroma add failure")
        for position, vector_id in enumerate(ids):
            self.rows[vector_id] = {
                "id": vector_id,
                "document": documents[position],
                "metadata": dict(metadatas[position]),
                "embedding": list(embeddings[position]) if embeddings is not None else [],
            }

    def delete(self, ids):
        self.timeline.append("chroma:delete")
        if self.fail_delete:
            raise MirrorError("injected chroma delete failure")
        for vector_id in ids:
            self.rows.pop(vector_id, None)


def _scope_env(monkeypatch, *, dim=DIM, model="nomic-embed-test", switch="on"):
    """把运行时 embedding 口径与双写开关钉成用例要的样子。"""
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(dim))
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, model)
    monkeypatch.setattr(retriever, "EMBEDDING_DIM", dim)
    if switch is None:
        monkeypatch.delenv(pg_store.DUAL_WRITE_ENV, raising=False)
    else:
        monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, switch)
    pg_store.reset_vector_mirror_diagnostics()


def _scope_row(dim=DIM, model="nomic-embed-test", distance="cosine"):
    return (model, dim, distance)


def _wire(monkeypatch, connection):
    """把 pg_store 唯一的建连接边界换成假连接，其余逻辑一律走真实实现。"""
    urls = []
    monkeypatch.setattr(pg_store, "_connect", _connect_factory(connection, urls))
    return urls


def _connect_factory(connection, urls):
    def _connect(url, connection_factory):
        urls.append(url)
        return connection

    return _connect


def _retriever(monkeypatch, collection, dim=DIM):
    obj = object.__new__(retriever.DocumentRetriever)
    obj.collection = collection
    obj.splitter = FakeSplitter()
    obj.embedding = FakeEmbedding(dim)
    monkeypatch.setattr(
        retriever.DocumentRetriever, "stores_vectors", property(lambda self: True)
    )
    return obj


def _row(vector_id, document="old", metadata=None, embedding=None):
    return {
        "id": vector_id,
        "document": document,
        "metadata": metadata or {"filename": vector_id.rsplit("_", 1)[0], "chunk_index": 0},
        "embedding": embedding if embedding is not None else [0.5] * DIM,
    }


# --------------------------------------------------------------- 判据③ / ⑤b


def test_switch_defaults_to_off(monkeypatch):
    """未设开关 = 关；不认识的值也算关（保守侧）。"""
    _scope_env(monkeypatch, switch=None)
    assert pg_store.dual_write_enabled() is False
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "ture")
    assert pg_store.dual_write_enabled() is False
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    assert pg_store.dual_write_enabled() is True


def test_switch_off_sends_no_postgres_statement(monkeypatch):
    """判据⑤b：开关关掉 ⇒ 一次连接都不建、一条 PG 语句都不发。"""
    _scope_env(monkeypatch, switch=None)
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    urls = _wire(monkeypatch, connection)
    assert pg_store.vector_mirror() is None

    collection = FakeCollection()
    ok, message = _retriever(monkeypatch, collection).add_document("a.md", "one\ntwo")
    assert ok is True and "2" in message
    assert urls == []
    assert connection.statements == []
    assert connection.commits == connection.rollbacks == connection.closes == 0
    assert len(collection.rows) == 2


def test_open_vector_mirror_hook_follows_the_switch(monkeypatch):
    """判据③：同一个钩子，开关关闭时返回 None 且不碰连接边界，开关打开时返回真镜像腿。"""
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    urls = _wire(monkeypatch, connection)
    retriever_obj = _retriever(monkeypatch, FakeCollection())

    _scope_env(monkeypatch, switch=None)
    assert retriever_obj._open_vector_mirror() is None
    retriever_obj.add_document("b.md", "text")
    retriever_obj.delete_document("b.md")
    assert urls == []
    assert connection.statements == []

    _scope_env(monkeypatch, switch="1")
    mirror = retriever_obj._open_vector_mirror()
    assert isinstance(mirror, pg_store.VectorMirror)
    assert len(urls) == 1
    mirror.close()


# --------------------------------------------------------------- 判据⑤a / ②


def test_postgres_upsert_failure_leaves_neither_leg(monkeypatch):
    """判据⑤a：PG upsert 失败 ⇒ Chroma 没写、PG 回滚、原样抛，不降级成只写 Chroma。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(
        scope_row=_scope_row(), column_type=f"vector({DIM})", fail_on={"upsert"}
    )
    _wire(monkeypatch, connection)
    collection = FakeCollection()

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        _retriever(monkeypatch, collection).add_document("c.md", "one\ntwo")
    assert excinfo.value.reason == retriever.REASON_VECTOR_MIRROR_WRITE_FAILED
    assert collection.rows == {}
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_chroma_failure_rolls_back_postgres(monkeypatch):
    """判据⑤a 另一侧：Chroma 失败 ⇒ PG 事务回滚，不留"PG 有向量 ⇔ Chroma 无"。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    _wire(monkeypatch, connection)
    collection = FakeCollection(fail_add=True)

    with pytest.raises(MirrorError):
        _retriever(monkeypatch, collection).add_document("d.md", "one\ntwo")
    assert collection.rows == {}
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert any("INSERT INTO chunk_vectors" in sql for sql, _ in connection.statements)


def test_commit_failure_rolls_back_both_legs(monkeypatch):
    """两腿都写完、PG 提交失败 ⇒ 同样整体退回（Chroma 靠补偿删除，PG 靠事务回滚）。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(
        scope_row=_scope_row(), column_type=f"vector({DIM})", fail_on={"commit"}
    )
    _wire(monkeypatch, connection)
    collection = FakeCollection(timeline=connection.timeline)

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        _retriever(monkeypatch, collection).add_document("e.md", "one\ntwo")
    assert excinfo.value.reason == retriever.REASON_VECTOR_MIRROR_WRITE_FAILED
    assert collection.rows == {}
    assert "chroma:delete" in connection.timeline
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_stale_document_survives_failed_mirror_delete(monkeypatch):
    """判据⑤a 的半态：PG 删旧失败 ⇒ Chroma 的旧向量一个字都不动。"""
    _scope_env(monkeypatch)
    stale = _row("f.md_0", metadata={"filename": "f.md", "chunk_index": 0, "hash": "old"})
    connection = FakeConnection(
        scope_row=_scope_row(), column_type=f"vector({DIM})", fail_on={"delete"}
    )
    _wire(monkeypatch, connection)
    collection = FakeCollection(rows=[stale])

    with pytest.raises(retriever.VectorWriteRejectedError):
        _retriever(monkeypatch, collection).add_document("f.md", "brand new")
    assert collection.rows == {"f.md_0": stale}
    assert "chroma:delete" not in connection.timeline
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_postgres_leg_is_written_before_chroma(monkeypatch):
    """写序钉死：探测 → PG upsert → Chroma add → commit。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    _wire(monkeypatch, connection)
    collection = FakeCollection(timeline=connection.timeline)

    _retriever(monkeypatch, collection).add_document("g.md", "one\ntwo\nthree")
    assert connection.timeline == [
        "scope_probe",
        "type_probe",
        "upsert",
        "chroma:add",
        "commit",
    ]
    assert connection.commits == 1
    assert len(collection.rows) == 3


def test_delete_document_dual_deletes(monkeypatch):
    """删文档也走同事务双腿：先读快照 → PG 删 → Chroma 删 → commit。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    _wire(monkeypatch, connection)
    collection = FakeCollection(rows=[_row("h.md_0")], timeline=connection.timeline)

    _retriever(monkeypatch, collection).delete_document("h.md")
    assert collection.rows == {}
    assert connection.timeline[-3:] == ["delete", "chroma:delete", "commit"]
    assert connection.commits == 1


def test_delete_document_commit_failure_restores_both_legs(monkeypatch):
    """删到一半提交失败 ⇒ PG 回滚 + Chroma 放回旧行，不留"PG 有 ⇔ Chroma 无"。"""
    _scope_env(monkeypatch)
    stale = _row("i.md_0")
    connection = FakeConnection(
        scope_row=_scope_row(), column_type=f"vector({DIM})", fail_on={"commit"}
    )
    _wire(monkeypatch, connection)
    collection = FakeCollection(rows=[stale], timeline=connection.timeline)

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        _retriever(monkeypatch, collection).delete_document("i.md")
    assert excinfo.value.reason == retriever.REASON_VECTOR_MIRROR_WRITE_FAILED
    assert collection.rows == {"i.md_0": stale}
    # 提交失败 → PG 回滚 → Chroma 把刚删掉的行放回：两腿又一致了
    assert connection.timeline[-4:] == [
        "chroma:delete",
        "commit",
        "rollback",
        "chroma:add",
    ]
    assert connection.commits == 0
    assert connection.rollbacks == 1


# --------------------------------------------------------------- 判据⑤c / ⑤d


def test_mirror_refuses_vector_wider_than_migrated_column(monkeypatch):
    """判据⑤c：R21 闸门放行（长度=EMBEDDING_DIM），pg_store 仍按库口径拒。"""
    # R21 的闸门看运行时声明（这里 4），镜像的闸门看库口径（这里 8）：两把尺子都要在
    _scope_env(monkeypatch)
    monkeypatch.setattr(retriever, "EMBEDDING_DIM", 4)
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    _wire(monkeypatch, connection)
    mirror = pg_store.vector_mirror()

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        mirror.add(
            ids=["i.md_0"],
            documents=["text"],
            metadatas=[{"filename": "i.md", "chunk_index": 0}],
            embeddings=[[0.25] * 4],
        )
    assert excinfo.value.reason == retriever.REASON_DIMENSION_MISMATCH
    assert not any("INSERT INTO chunk_vectors" in sql for sql, _ in connection.statements)
    assert connection.commits == 0
    assert pg_store.vector_mirror_diagnostics()["rejected_writes"] == 1


def test_mirror_rejects_all_zero_vectors_before_any_sql(monkeypatch):
    """判据⑤d：全零走 pg_store 这条腿也被拒，而且是零 SQL 的拒。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(scope_row=_scope_row(), column_type=f"vector({DIM})")
    _wire(monkeypatch, connection)
    mirror = pg_store.vector_mirror()

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        mirror.add(
            ids=["j.md_0"],
            documents=["text"],
            metadatas=[{"filename": "j.md", "chunk_index": 0}],
            embeddings=[[0.0] * DIM],
        )
    assert excinfo.value.reason == retriever.REASON_ALL_ZERO_VECTOR
    assert not any("INSERT INTO chunk_vectors" in sql for sql, _ in connection.statements)
    assert mirror.written == 0
    assert pg_store.vector_mirror_diagnostics()["last_failure"]["reason"] == (
        retriever.REASON_ALL_ZERO_VECTOR
    )


# --------------------------------------------------------------- 判据②开关侧


def test_mirror_refuses_unmigrated_database(monkeypatch):
    """开关开了但没跑 0010：拒开镜像并关掉连接，不退化成只写 Chroma。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(scope_row=None, column_type="")
    _wire(monkeypatch, connection)

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        pg_store.vector_mirror()
    assert excinfo.value.reason == retriever.REASON_VECTOR_MIRROR_UNAVAILABLE
    assert connection.closes == 1


def test_mirror_refuses_dimension_drift(monkeypatch):
    """库里的列宽与运行时口径不符 ⇒ 拒开（R22 禁一个库存两套维度）。"""
    _scope_env(monkeypatch, dim=DIM)
    connection = FakeConnection(scope_row=_scope_row(64), column_type="vector(64)")
    _wire(monkeypatch, connection)

    with pytest.raises(retriever.VectorWriteRejectedError) as excinfo:
        pg_store.vector_mirror()
    assert excinfo.value.reason == retriever.REASON_VECTOR_MIRROR_SCOPE_MISMATCH
    assert connection.commits == 0


def test_unclaimed_scope_is_labeled_by_first_writer(monkeypatch):
    """0010 留 unknown 时，第一次写入用 UPDATE 认领模型，列宽仍逐条核对。"""
    _scope_env(monkeypatch)
    connection = FakeConnection(
        scope_row=_scope_row(model=indexing.SCOPE_UNKNOWN),
        column_type=f"vector({DIM})",
    )
    _wire(monkeypatch, connection)
    mirror = pg_store.vector_mirror()
    sent = mirror.add(
        ids=["k.md_0"],
        documents=["text"],
        metadatas=[{"filename": "k.md", "chunk_index": 0}],
        embeddings=[[0.25] * DIM],
    )
    assert sent == 1
    assert connection.row_count == 1
    assert connection.timeline[2] == "claim"
    assert mirror.scope.embedding_model == indexing.SCOPE_UNKNOWN


# --------------------------------------------------------------- 判据⑤e


def test_0010_is_registered_in_the_manifest():
    """正向对照：0010 在 manifest 里，且 digest 与文件内容逐字相符。"""
    entry = next((item for item in mig.MIGRATIONS if item.version == "0010"), None)
    assert entry is not None and entry.name == "pgvector_chunks"
    sql = (mig._DEFAULT_MIGRATIONS_DIR / "0010_pgvector_chunks.sql").read_text(
        encoding="utf-8"
    )
    assert hashlib.sha256(sql.encode("utf-8")).hexdigest() == entry.checksum


def test_unregistered_migration_fails_discovery(tmp_path):
    """判据⑤e：把 0010 从 manifest 里摘掉，迁移加载器必须 fail closed。"""
    copied = tmp_path / "migrations"
    shutil.copytree(mig._DEFAULT_MIGRATIONS_DIR, copied)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.pop("0010_pgvector_chunks.sql")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        mig.discover_migrations(copied)
    assert "untracked files: 0010_pgvector_chunks.sql" in str(excinfo.value)


def test_tampered_migration_fails_discovery(tmp_path):
    """已登记的迁移被改一个字也要报错：digest 是承重的，不是装饰。"""
    copied = tmp_path / "migrations"
    shutil.copytree(mig._DEFAULT_MIGRATIONS_DIR, copied)
    target = copied / "0010_pgvector_chunks.sql"
    target.write_text(target.read_text(encoding="utf-8") + "\n-- tamper\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        mig.discover_migrations(copied)
    assert "checksum mismatch" in str(excinfo.value)

