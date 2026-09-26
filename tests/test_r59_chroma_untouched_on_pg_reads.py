# -*- coding: utf-8 -*-
"""R59 块1 判据① —— `INDEX_BACKEND=pgvector` 的读路径真实装：不再构造、也不再调用 Chroma。

这一枚不许只查环境变量。`read_backend()` 说 "pgvector" 而读腿偷偷回头问旧引擎，是这一单
最坏的一种假话：它长得像切完了（诊断里 answered_by 甚至可能对），而 R269 量到的那台
ANN（`ef_search` 恒 100、近重复吃光候选预算、零 compaction）仍在服务流量。所以本文件的
断言全落在**行为**上，分三层，一层比一层难绕：

1. 运行期毒化：把 `retriever.chromadb` 换成"一构造就抛"的假模块。读路径上任何一次
   `PersistentClient(...)` / `EphemeralClient(...)` 都当场红，藏在哪一分支里都躲不掉。
2. 句柄记账：假 collection 分开记 `query()`（那台 ANN）与 `get()`（内容扫描）。
   切读态答出行 ⇒ 两者都是零次；0 行降级 ⇒ 只允许 `get()`（判据②a 的降级腿读内容）。
3. 源码层：AST 扫四枚读函数，出现任何"造 client / 拿 collection"的调用名即红。
   写出来但今天走不到的分支同样挡得住——那正是"以后顺手加一行"的形状。

语料腿（BM25 的取数）也归本文件：切读态它必须从 PGVector 取，否则"切了读"只对语义腿
成立，而每次建语料照样朝退役引擎开一次全库 `get()`——半切比不切更难查（计划书 §9.1
给热集让路立的正是这条理由）。

反证（判据⑥第三条）：往 `_pgvector_hits` 开头塞一行 `chromadb.PersistentClient(path="x")`
⇒ `test_switched_reads_construct_no_chroma_client` 与
`test_no_read_function_asks_the_retiring_engine_for_a_handle` 双双红。
"""

import ast
import pathlib

import pytest

from app.rag import indexing
from app.rag import pg_store
from app.rag import retrieval_pipeline as pipeline_module
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

DIM = 4
QUERY = [0.5] * DIM
WHERE_ADMIN = {"classification": {"$in": [1, 2, 3]}}

ROWS = [("a.txt_0", "住宿费标准是每晚500元。", "a.txt", 0, 2, "研发中心", 1.25)]

#: 读函数里一个都不许出现的名字。构造句柄与"取/建集合"都在内——切读态的读路径拿到
#: collection 的那一瞬间，就已经在问旧引擎了，不管后面问不问。
FORBIDDEN_READ_CALLS = frozenset({
    "PersistentClient", "EphemeralClient", "Client", "get_or_create_collection",
    "create_collection", "get_collection", "delete_collection",
})

READ_FUNCTIONS = ("search", "_pgvector_hits", "_hot_hits", "_keyword_hits")


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


class _PgDouble:
    def __init__(self, rows=None):
        configured = indexing.configured_embedding_scope()
        self.scope_row = (configured.embedding_model, int(configured.dimension), "l2")
        self.column_type = ("vector(%d)" % int(configured.dimension),)
        self.rows = ROWS if rows is None else rows
        self.statements = []

    def execute(self, sql, params=None):
        statement = str(sql)
        self.statements.append((statement, params))
        if "vector_scope" in statement:
            return _Result(scalar=self.scope_row)
        if "pg_attribute" in statement:
            return _Result(scalar=self.column_type)
        if "FROM " + pg_store.DEFAULT_VECTOR_TABLE in statement:
            return _Result(rows=self.rows)
        raise AssertionError("假连接收到没准备好的语句：" + statement)

    def search_statements(self):
        return [item for item in self.statements if "ORDER BY embedding" in item[0]]

    def corpus_statements(self):
        return [item for item in self.statements
                if "ORDER BY embedding" not in item[0] and "vector_scope" not in item[0]
                and "pg_attribute" not in item[0]]

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _Handle:
    """记每一次调用，且一律答出行：答出行时还去碰它，就是本文件要抓的现行。"""

    name = "enterprise_docs"

    def __init__(self):
        self.queries = []
        self.gets = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {"ids": [["a.txt_0"]], "documents": [["旧引擎的正文"]],
                "metadatas": [[{"filename": "a.txt", "chunk_index": 0,
                                "classification": 2, "department": "研发中心"}]]}

    def get(self, where=None):
        self.gets.append(where)
        return {"ids": [], "documents": [], "metadatas": []}


class _PoisonedChromadb:
    """一构造就抛。切读态的读路径如果还想拿句柄，红在这里，而不是悄悄成功。"""

    __version__ = "poisoned-for-r59"

    def _refuse(self, name):
        raise AssertionError(
            "切读态的读路径构造了 Chroma 句柄（%s）：退役中的引擎不许出现在读路径上" % name)

    def PersistentClient(self, *args, **kwargs):
        self._refuse("PersistentClient")

    def EphemeralClient(self, *args, **kwargs):
        self._refuse("EphemeralClient")

    def Client(self, *args, **kwargs):
        self._refuse("Client")


def _switched_retriever(tmp_path, monkeypatch, rows=None):
    double = _PgDouble(rows=rows)
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_read_diagnostics()
    rt.reset_search_shape()
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = _Handle()
    return instance, double


# --------------------------------------------------------------- 语义腿：不构造、不调用


def test_switched_reads_construct_no_chroma_client(tmp_path, monkeypatch):
    """判据①第一层：读这一问的全过程里，一次句柄构造都没有（构造=当场抛，不是计数）。"""
    retriever, _double = _switched_retriever(tmp_path, monkeypatch)
    monkeypatch.setattr(rt, "chromadb", _PoisonedChromadb())

    hits = retriever.search("住宿费", k=5, where=WHERE_ADMIN)

    assert [item["content"] for item in hits] == ["住宿费标准是每晚500元。"]
    assert hits[0]["retrieval_mode"] == DocumentRetriever.MODE_SEMANTIC


def test_switched_reads_ask_the_legacy_handle_nothing(tmp_path, monkeypatch):
    """判据①第二层：PG 答了行，旧引擎的句柄上 `query()` 与 `get()` 都是零次。

    `answered_by == pgvector` 只证明"有人自称答了"，证明不了没人被问过；所以这里两笔都要
    现取：计数为零，且发出的 SQL 恰好一条。
    """
    retriever, double = _switched_retriever(tmp_path, monkeypatch)

    retriever.search("住宿费", k=5, where=WHERE_ADMIN)

    assert retriever.collection.queries == []
    assert retriever.collection.gets == []
    assert len(double.search_statements()) == 1
    assert rt.search_shape_diagnostics()["last"]["answered_by"] == (
        rt.RETRIEVAL_SERVER_PGVECTOR)


@pytest.mark.parametrize("where", [None, WHERE_ADMIN,
                                   {"$and": [WHERE_ADMIN,
                                             {"department": {"$in": ["研发中心"]}}]}])
def test_every_legal_scope_shape_reaches_pg_without_the_legacy_handle(tmp_path, monkeypatch,
                                                                     where):
    """三份合法谓词形状：都真的下推到 SQL，且都没碰旧句柄（不是"没带谓词所以没读 PG"）。"""
    retriever, double = _switched_retriever(tmp_path, monkeypatch)

    hits = retriever.search("住宿费", k=5, where=where)

    assert hits
    sql, params = double.search_statements()[-1]
    assert ("WHERE" in sql) == bool(where), sql
    assert retriever.collection.queries == []


def test_no_read_function_asks_the_retiring_engine_for_a_handle():
    """判据①第三层：AST 扫源码。写出来但今天走不到的构造，同样在这里红。

    为什么光有运行期毒化不够：一行 `client = chromadb.PersistentClient(...)` 藏在
    `if not rows:` 里面时，跑到的用例看不见它，而它离"哪天这分支被走到"只差一次改动。
    """
    source = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in READ_FUNCTIONS:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                called = inner.func
                name = getattr(called, "attr", None) or getattr(called, "id", None)
                if name in FORBIDDEN_READ_CALLS:
                    offenders.append("%s:%s" % (node.name, inner.lineno))
    assert offenders == [], "读路径里出现了向向量库要句柄的调用：" + repr(offenders)


# ---------------------------------------------------------------- 语料腿：跟着开关走


def test_the_lexical_corpus_follows_the_read_switch(tmp_path, monkeypatch):
    """切读态的 BM25 语料来自 PGVector，且压根不构造 DocumentRetriever。

    这条是判据①的"一律"两个字：语义腿切了、语料腿没切，就等于每次建索引仍朝退役引擎
    开一次全库 get()。这里用一枚会抛的 DocumentRetriever 当哨兵——被构造就是红。
    """
    double = _PgDouble()
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_corpus_diagnostics()

    def _no_retriever(*args, **kwargs):
        raise AssertionError("切读态建语料不许构造 DocumentRetriever")

    monkeypatch.setattr(rt, "DocumentRetriever", _no_retriever)

    searcher = pipeline_module.BM25Searcher()
    searcher.build_index()

    assert len(searcher.documents) == len(ROWS)
    assert searcher.documents[0]["source"] == "a.txt"
    assert searcher.documents[0]["classification"] == 2
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_PGVECTOR
    assert double.corpus_statements(), "语料腿一条 SQL 都没发，就不算从 PG 取的"


def test_a_refused_corpus_leg_falls_back_and_says_so(tmp_path, monkeypatch):
    """语料腿拒答时退回旧路，但必须留下名字：source=legacy_chroma + 一枚拒答码。

    裁定的另一半：拒答**不许**冒充"库是空的"。空语料的 BM25 腿会安静地一条都不召回，
    那比不切更难查——R158 给答复侧立的"两种 0 必须分家"同一条规矩管这里。
    """
    def _refuse(url, factory):
        raise pg_store.VectorReadRejectedError(
            "连不上", reason=pg_store.REASON_VECTOR_READ_FAILED)

    monkeypatch.setattr(pg_store, "_connect", _refuse)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_corpus_diagnostics()
    pg_store.reset_vector_read_diagnostics()

    built = {}

    class _Legacy:
        def __init__(self, *args, **kwargs):
            pass

        collection = _Handle()

    monkeypatch.setattr(rt, "DocumentRetriever", _Legacy)
    built["legacy"] = _Legacy.collection

    pipeline_module.BM25Searcher().build_index()

    assert built["legacy"].gets == [None], "退回旧路时问的是全库内容扫描"
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_LEGACY
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_FAILED)


def test_an_empty_mirror_is_a_zero_row_corpus_not_a_fallback(tmp_path, monkeypatch):
    """三态契约的第三态：镜像真的 0 行 ＝ 语料是空的，不许回头问旧库。

    上面那枚管「拒答不许冒充空库」，这一枚管反方向：「空库不许冒充拒答」。两条合起来才
    是 `switched_corpus()` 的三态（not_switched / legacy / pgvector）。走错这一格在生产上
    长这样：一次全量重建刚把 `chunk_vectors` 清空、还没回灌，切读态的 BM25 语料于是悄悄
    从退役引擎取——双写断了没人知道，而答案看起来完全正常。把 `read_corpus` 的空结果
    折成 None（或把本枚的哨兵换成一枚不会抛的假件）都会让它红。
    """
    double = _PgDouble(rows=[])
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_corpus_diagnostics()

    def _no_retriever(*args, **kwargs):
        raise AssertionError("0 行镜像不许被读成『这一腿没答』，退回旧库就是假切读")

    monkeypatch.setattr(rt, "DocumentRetriever", _no_retriever)

    searcher = pipeline_module.BM25Searcher()
    searcher.build_index()

    assert searcher.corpus == [] and searcher.documents == []
    assert searcher.bm25 is None, "空语料不建 BM25，也不假装建了"
    assert double.corpus_statements(), "语料腿必须真发过那条 SQL，而不是被跳过"
    reading = pg_store.vector_corpus_diagnostics()
    assert reading["source"] == pg_store.CORPUS_SOURCE_PGVECTOR, reading
    assert reading["rows"] == 0, reading

def test_the_default_state_opens_no_connection_for_a_corpus(tmp_path, monkeypatch):
    """默认态：建语料不发 SQL、不建连接。翻开关的代价今天为零，这一枚是它的凭据。"""
    def _refuse(url, factory):
        raise AssertionError("默认态建语料不许连 PostgreSQL")

    monkeypatch.setattr(pg_store, "_connect", _refuse)
    monkeypatch.delenv(pg_store.DUAL_WRITE_ENV, raising=False)
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_corpus_diagnostics()

    assert pg_store.switched_corpus() is None
    assert pg_store.vector_corpus_diagnostics()["source"] == (
        pg_store.CORPUS_SOURCE_NOT_SWITCHED)


# --------------------------------------------------------- ②(c) 权限口径：纵深那一层不变


@pytest.mark.parametrize("poisoned", [
    {"vector_id": "x.txt_9", "content": "别人的高分块", "filename": "x.txt",
     "chunk_index": 9, "classification": None, "department": "研发中心"},
    {"vector_id": "y.txt_9", "content": "别的部门的高分块", "filename": "y.txt",
     "chunk_index": 9, "classification": 1, "department": "市场部"},
])
def test_a_pg_hit_the_scope_rejects_is_dropped_before_dedup(tmp_path, monkeypatch,
                                                            poisoned):
    """权限口径（判据②c 第三处）：换引擎不改"先过滤、后去重"那一处位置（R45/R57）。

    假 PG 腿故意交回一条越权行（等价于"召回实现没执行 where"那种形状），
    `retrieval_pipeline._retain_permitted` 必须在去重与 RRF 之前把它裁掉。
    这一格与"SQL 里带没带谓词"无关：谓词下推是第一道，本地复核是第二道，两道都要在换引擎
    之后继续各自成立——把它们合成一道正是切读最容易犯的错。
    """
    from app.rag.filters import DocumentRetrievalScope

    scope = DocumentRetrievalScope(
        filters=WHERE_ADMIN, reason_code="department_scope",
        classification_levels=frozenset({2, 3}), departments=frozenset({"研发中心"}))
    hit = {"content": poisoned["content"], "source": poisoned["filename"],
           "chunk_index": poisoned["chunk_index"],
           "classification": poisoned["classification"],
           "department": poisoned["department"],
           "retrieval_mode": "semantic", "retrieval_reason": ""}

    kept = pipeline_module._retain_permitted([hit, dict(hit)], scope.allows)

    assert kept == [], "越权行进了名次：判定不再只出自 filters.py 一处"
    deduped = pipeline_module._deduplicate([hit])
    assert len(deduped) == 1, "过滤发生在去重之前，本方法不代它决定顺序"
