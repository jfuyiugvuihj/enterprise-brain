# -*- coding: utf-8 -*-
"""R60 判据①②③ —— 停写之后的写路径唯一化必须真的在码上，而且必须留得下退路。

这一枚文件不许只查环境变量。``INDEX_BACKEND=pgvector`` 答得漂亮而 ``_write_batch`` 背地里
还往 Chroma 塞行，是这一单最坏的一种假话：双写看起来还在跑、诊断里 read_backend 也确实
是 pgvector，而"退役中的遗留件"其实每天都在长新行 —— 于是没有任何一天能把它归档下线。
所以本文件的断言全落在**两腿各自的行数**上，一枚一枚数：

1. 遗留腿那枚假目录是一张可数的表（``LegacyHandle.count()``），不是只记调用次数的桩：
   第④格的形状（PG +N / Chroma +0）在这里先离线量一遍，真库现取读数见交付纸第④格。
2. PG 那一腿是一张按 ``chunk_vectors`` 列形状记账的假表；语句标记一律取 ``pg_store`` 里的
   真源常量，本桩不自带第二份 SQL —— 改了 SQL 而桩还是绿，就是桩在骗人。
3. 删除这一腿问的是"行住在哪一库"，不是"遗留腿知道些什么"：只住在 PG 的行必须删得掉，
   两腿都持有的行必须两边都删掉，热集收到的必须是并集。

开关退回 ``chroma`` 那一档（＝唯一的回滚通路）时要求的是**逐字不变**：一次
``collection.get(where=...)``、一次 ``collection.add``、一条 SQL 都不许多问 PG。判据②
的常驻钉是这里唯一不许"改一改就算过"的一枚：停写靠判定，不靠把代码摘掉。

全程离线：不连 PostgreSQL、不起服务、不开 chromadb、不打模型。
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.rag import hot_index
from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

REPO = pathlib.Path(__file__).resolve().parents[1]
RETRIEVER_PY = REPO / "app" / "rag" / "retriever.py"

DIM = 8
MODEL = "nomic-embed-test"
#: 与 VectorMirror.build_rows 交回的那一行同列序（pg_store._UPSERT_COLUMNS）：假表按它记账，
#: 再把 pg_store 的两枚 SELECT 真源翻译回各自的列序。桩不抄 SQL，只读 SQL 常量。
UPSERT_COLUMNS = ("vector_id", "filename", "chunk_index", "content", "classification",
                  "department", "content_sha256", "index_version_id", "embedding",
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
    return (vector_id, filename, chunk_index, content, classification, department, sha,
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


def test_the_legacy_knob_still_writes_both_legs_unchanged(monkeypatch):
    """判据①第二半＋判据②：开关退回 chroma，遗留腿照旧接行，PG 那一腿也照旧写。

    这一枚同时是判据⑦第二把的正面：不许把双写一起关成零写 —— 两腿都写才是那一档的今天。
    """
    instance, connection, table = _assemble(monkeypatch, backend=indexing.INDEX_BACKEND_DEFAULT)

    ok, _message = instance.add_document("a.txt", "一\n二")

    assert ok is True
    assert instance.collection.count() == 2
    assert len(table.rows) == 2
    assert instance.collection.adds == [["a.txt_0", "a.txt_1"]]
    assert "upsert" in connection.log and "commit" in connection.log


def test_the_shipped_default_sends_no_postgres_statement(monkeypatch):
    """判据①「行为一字不改」最严的一档：什么都不设 ＝ 一条 SQL 都不发，行全在遗留腿。"""
    instance, connection, table = _assemble(monkeypatch, backend=None, dual=None)

    instance.add_document("a.txt", "一\n二")

    assert instance.collection.count() == 2
    assert connection.log == []
    assert len(table.rows) == 0


def test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write(monkeypatch):
    """判据②反证第二把的形状：开关在 pgvector 而双写关着，遗留腿必须仍写。

    谁都不写是本单最贵的错：上传报成功、两库里都没有这份文档的向量。
    """
    instance, _connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                             dual="off")

    ok, _message = instance.add_document("b.txt", "三\n四")

    assert ok is True
    assert instance.collection.count() == 2
    assert len(table.rows) == 0


def test_the_pgvector_write_predicate_is_the_read_switch_itself(monkeypatch):
    """判据②：停写靠"后端判定"，判定来自 indexing 那一把开关，而且每次调用现读。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    assert instance._writes_go_to_pgvector() is True
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    assert instance._writes_go_to_pgvector() is False
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, "not-a-backend")
    assert instance._writes_go_to_pgvector() is False, "拼错的值必须留在出厂档，不许猜另一台"


def test_stopping_the_write_is_a_switch_and_not_a_deletion():
    """判据②常驻钉：``_write_batch`` 里那一枚 ``collection.add`` 必须还在源码里。

    把它摘掉也能让第④格今天绿，但那是把退路拆了：回滚＝改码重新发版，而不是把开关拨回
    chroma。所以这枚钉只看 AST，不看今天的读数 —— 读数会随每笔并树漂，结构不会。
    """
    tree = ast.parse(RETRIEVER_PY.read_text(encoding="utf-8"))
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_write_batch":
            body = node
            break
    assert body is not None, "_write_batch 不在了 —— 那已经不是停写，是删码"
    handed = [item for item in ast.walk(body)
              if isinstance(item, ast.Call)
              and isinstance(item.func, ast.Attribute) and item.func.attr == "add"
              and isinstance(item.func.value, ast.Attribute)
              and item.func.value.attr == "collection"]
    assert len(handed) >= 2, (
        "遗留腿的 add 调用被摘掉了（现读 %d 枚；离线那支与正常那支都得在）" % len(handed))


def test_the_write_leg_reads_no_second_switch():
    """判据②：retriever.py 里不许长出第二枚名字带 BACKEND 的环境变量。

    凭据：计划书 R592 那枚"一把开关"的钉对端点层立的正是这条，写路径同理。
    """
    source = RETRIEVER_PY.read_text(encoding="utf-8")
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            dotted = getattr(func, "attr", None) or getattr(func, "id", None)
            via_environ_get = (dotted == "get"
                               and getattr(getattr(func, "value", None), "attr", "") == "environ")
            if (dotted == "getenv" or via_environ_get) and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.append(first.value)
        elif isinstance(node, ast.Subscript):
            value = node.value
            if (getattr(value, "attr", "") == "environ"
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                names.append(node.slice.value)
    second = [name for name in names if "BACKEND" in name.upper()]
    assert second == [], "retriever.py 自己读了后端开关：" + repr(second)
    assert "pgvector_writes_are_primary" in source, "写路径没问那一把开关，问的是别的什么"


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


def test_delete_removes_legacy_rows_too_and_notes_the_union(monkeypatch):
    """判据③「不留孤儿」：两腿都持有的那份文档，删完之后哪一腿都不许留着它的行。"""
    table = PgTable([pg_row("a.txt_0", "a.txt", 0, "上一版的正文", "legacy-hash")])
    legacy = LegacyHandle([legacy_row("a.txt_0")])
    instance, connection, _t = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                         table=table, legacy=legacy, hot=True)

    instance.delete_document("a.txt")

    assert legacy.count() == 0, "删了 PG、Chroma 还留着孤儿行"
    assert len(table.rows) == 0, "两腿里只剩一腿有行同样是没删干净"
    assert instance.collection.deletes == [["a.txt_0"]]
    assert "delete" in connection.log
    assert instance._r60_noted.get("delete") == ["a.txt_0"], "_note_hot_delete 必须收到并集"


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
    """判据③：PG 问不出行 ⇒ 拒答。退回"遗留腿知道的那些"就是报一次没定位成功的删除。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              legacy=LegacyHandle([legacy_row("a.txt_0")]),
                                              fail_on=("doc_rows",))

    with pytest.raises(rt.VectorWriteRejectedError) as caught:
        instance.delete_document("a.txt")

    assert caught.value.reason == rt.REASON_VECTOR_MIRROR_UNAVAILABLE
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
    """判据③的读回面：app/api/v1/chat.py:4786 拿这份名单过滤可见文档。

    停在切换那一刻就是假话：之后上传的每一枚文档都不在名单里，而它明明能被供应商检索出来。
    """
    legacy = LegacyHandle([legacy_row("a.txt_0")])
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              legacy=legacy)
    instance.add_document("b.txt", "三\n四")

    assert instance.list_documents() == ["b.txt"]

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    assert instance.list_documents() == ["a.txt"], "开关退回 chroma 时名单仍只来自遗留腿，一字不改"


def test_the_hot_index_still_learns_the_written_ids(monkeypatch):
    """判据③的边角：热集那本账记的是"id 还有没有效"，与行住在哪一库无关，写与删都得收到。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              hot=True)

    instance.add_document("b.txt", "三\n四")

    assert instance._r60_noted.get("write") == ["b.txt_0", "b.txt_1"]
    instance.delete_document("b.txt")
    assert instance._r60_noted.get("delete") == ["b.txt_0", "b.txt_1"]
