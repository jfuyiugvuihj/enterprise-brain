# -*- coding: utf-8 -*-
"""R60 块 1 —— 在册那枚件没盖到的两格形状：判定的第三枚牙 + 两档开关的 PG 腿逐字节对照。

本文件**不重复** ``tests/test_r60_write_path_unique_under_pgvector.py`` 已经钉住的格子，
只补它量不到的两格，全程离线（不连 PostgreSQL、不起服务、不开 chromadb、不打模型）：

1. 判据⑦(c) 的第三形。``_writes_go_to_pgvector`` 由三枚条件与成（计划书 §3 P5 判据②的
   "停写靠判定"），在册那枚件逐枚量过其中两枚 —— ``VECTOR_DUAL_WRITE``（
   ``test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write``）与 ``INDEX_BACKEND``
   （``test_the_pgvector_write_predicate_is_the_read_switch_itself``）。第三枚
   ``stores_vectors`` 一直没被单独量：把判定改成 ``dual_write and primary`` 之后，那枚件
   42 条全绿（本席 10-03 现取，见交工纸第②格刀 e）。它不是无害的：``stores_vectors`` 为假
   就是 chromadb 装不上时那枚离线 ``_JsonCollection``，行全住在 JSON 文件里；判定这时答
   ``True``，删除与"这份文档有哪些行"那两句就都会去问 PG，而 PG 那本账是空的。
   计划书 §15 S5 那一格写的正是这条判定将来会被误读成关键词降级 —— 先钉住今天。
2. 判据①的 A/B 对照。开关两档各自被单独钉过，但没有一枚钉把两档**摆在一起**比：
   停写只许改变"遗留腿接不接行"这一格，交给 PostgreSQL 的语句原文与绑定参数必须逐字节等。
   两档之间多出来的那一句只许是判据③的那次问句（"``filename`` 的行在不在 PG"）。

判据④⑤（现机读数与回滚演练）不在本文件，也不许在本文件里被说成已完成。
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


def test_the_predicate_is_false_for_a_store_that_holds_no_vectors(monkeypatch):
    """离线 ``_JsonCollection`` 没有向量列：两把开关都拨到"停写"，判定也必须是 False。"""
    instance, _connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                      dual="on", stores=False)

    assert instance._writes_go_to_pgvector() is False, (
        "判定不再问 stores_vectors —— 离线 JSON 那档里，行不住在 PostgreSQL，"
        "答 True 就是让删除与名单去问一本空账")


def test_an_offline_store_writes_the_json_leg_and_asks_postgres_nothing(monkeypatch):
    """同一条判据的行为面：整笔写入一条 SQL 都不许多发，行必须落在那枚 JSON 文件里。"""
    instance, connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                     dual="on", stores=False)

    ok, _message = instance.add_document(DOC, BODY)

    assert ok is True
    assert connection.statements == [], "离线档问了 PostgreSQL：" + repr(connection.kinds)
    assert instance.collection.adds == [IDS], "停写判定把离线那腿也一起关掉了 —— 那是零写"
    assert instance.collection.count() == 2


def test_the_predicate_is_true_only_when_all_three_terms_hold(monkeypatch):
    """三枚条件的正反面一次量完：少任何一枚（或两枚）都不许答 True。"""
    instance, _connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                      dual="on", stores=True)
    assert instance._writes_go_to_pgvector() is True

    instance.collection = RecordingCollection()
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "off")
    assert instance._writes_go_to_pgvector() is False, "双写关着还有 PG 腿可交行？"

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    assert instance._writes_go_to_pgvector() is False, "主写退回 chroma，遗留腿必须照旧接行"


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


def test_the_only_difference_between_the_two_positions_is_the_legacy_leg(monkeypatch):
    """A/B 差集逐枚点名：chroma 档一次 ``add`` 接两行、不问 PG 的行在哪；pgvector 档反之。"""
    chroma = _write_once(monkeypatch, indexing.INDEX_BACKEND_DEFAULT)
    pgvector = _write_once(monkeypatch, indexing.PGVECTOR_BACKEND)

    assert chroma["legacy_adds"] == [IDS]
    assert chroma["legacy_rows"] == 2
    assert pgvector["legacy_adds"] == [], "停写档里遗留腿又被交了一次 add"
    assert pgvector["legacy_rows"] == 0

    # 判据③那句问句是两档之间唯一被允许多出来的 PG 语句，而且只多这一句。
    assert chroma["kinds"].count("doc_rows") == 0, "退回档多问了 PG —— 判据①「一字不改」破了"
    assert pgvector["kinds"].count("doc_rows") == 1
    assert pgvector["kinds"][:4] == ["scope_probe", "type_probe", "doc_rows", "close"]
    # 停写档相对退回档多出来的 PG 流量，只许是判据③那一次问句，按整组点名。
    read_ask = ["scope_probe", "type_probe", "doc_rows", "close"]
    assert pgvector["kinds"] == read_ask + chroma["kinds"], (
        "两档之间多出来的 PG 语句不止判据③那一次问句：%r vs %r"
        % (pgvector["kinds"], chroma["kinds"]))


def test_the_stop_write_branch_is_inside_the_pg_leg(monkeypatch):
    """形状面最后一条：判定为真而 PG 腿不存在时（``mirror is None``）不许演成零写。

    在册那枚件用 ``dual="off"`` 量过同一格；本席把它换成"读那把开关现读到的答复"再量一遍：
    ``_writes_go_to_pgvector`` 里 ``dual_write_enabled()`` 与 ``pgvector_writes_are_primary()``
    是 ``and`` 关系，所以"PG 腿没开"必然蕴含"判定为假"。这枚钉钉的是**蕴含关系的写法**：
    谁把停写判定挪到 ``if mirror is not None`` 之外，零写当场红。
    """
    instance, connection = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                     dual="off", stores=True)

    assert instance._writes_go_to_pgvector() is False
    ok, _message = instance.add_document(DOC, BODY)
    assert ok is True
    assert connection.statements == []
    assert instance.collection.adds == [IDS]


@pytest.mark.parametrize("term", ["stores_vectors", "dual_write_enabled",
                                  "pgvector_writes_are_primary"])
def test_each_term_of_the_predicate_is_named_in_the_source(term):
    """常驻钉（判据②"不许硬删"的写面）：三枚条件必须都还写在判定那一段里。"""
    import ast
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "app" / "rag" / "retriever.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    body = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "_writes_go_to_pgvector")
    names = {getattr(node, "attr", None) or getattr(node, "id", None)
             for node in ast.walk(body) if isinstance(node, (ast.Attribute, ast.Name))}

    assert term in names, (
        "判定里 %s 那一枚条件不在了 —— 三枚条件少一枚，停写就不再是「靠开关/后端判定」这句话" % term)
