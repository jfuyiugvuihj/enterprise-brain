"""R59b 判据④：读路径接到 PGVector 之后，这几枚钉子必须能反证。

写法照 R44/R158 那一族的规矩：全程不连真库、不打 Ollama、不开服务。假连接按语句前缀分派，
并把每一条**发出去的 SQL 原文**记下来 —— 这一单要钉的不是"答案对不对"，而是"什么语句被发
出去了"：权限谓词有没有进 WHERE、翻译不出来时是不是干脆没发、只读腿有没有顺手 commit。
先验（RAG_ACTIVITY_PRIOR）显式关掉：它默认要读一张计数表，那是真 IO，本文件一条都不许发。

每枚用例都留了一处"摘掉守卫就变红"的地方，逐条写在 docstring 里：

- 默认仍在 chroma —— 把 `indexing.INDEX_BACKEND` 翻过去，这条立刻红。
- 切了读就不许多问 Chroma —— 把 PG 腿改成恒回 None（等于没接上），这条立刻红。
- 认不出的过滤器**一条向量 SQL 都不许发** —— 把 `sql_scope_filter` 的 raise 换成 `return "", []`，
  这条立刻红；而那处改动看着无害，交回的却是别人的高分 chunk。
- 双写没开就不许读 —— 删掉 `read_topk` 里 `mirror is None` 那一支，这条立刻红。
- 密级 NULL 原样交回 None —— 在读腿把它补成 1，这条立刻红（R57 的 fail-closed）。
- 热集在切读态让路 —— 删掉 `_hot_hits` 顶部那枚守卫，这条立刻红（半切比不切更难查）。
"""

import pytest

from app.rag import hot_index
from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

DIM = 4
QUERY = [0.5] * DIM

#: 与 app/rag/filters.py 交出的两份形状逐字同形：管理员一份，其余一份 $and。
WHERE_ADMIN = {"classification": {"$in": [1, 2, 3]}}
WHERE_DEPARTMENT = {"$and": [{"classification": {"$in": [1, 2]}},
                             {"department": {"$in": ["研发中心"]}}]}


def _row(vector_id, *, content, filename, chunk_index, classification, department,
         distance=1.0):
    """一行 `_READ_COLUMNS` + distance 的裸 tuple：假连接就按这个形状回。"""
    return (vector_id, content, filename, chunk_index, classification, department,
            distance)


ROWS = [
    _row("a.txt_0", content="住宿费标准是每晚500元。", filename="a.txt", chunk_index=0,
         classification=2, department="研发中心", distance=1.25),
    _row("b.txt_1", content="年假按工龄计算。", filename="b.txt", chunk_index=1,
         classification=None, department="", distance=2.5),
]


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


class _FakeConnection:
    """vector_mirror() 的三条语句都从这一枚假件走：探测两条，读一条。"""

    def __init__(self, rows=None, *, distance_function="l2"):
        configured = indexing.configured_embedding_scope()
        dimension = int(configured.dimension)
        self.scope_row = (configured.embedding_model, dimension, distance_function)
        self.column_type = ("vector(%d)" % dimension,)
        self.rows = ROWS if rows is None else rows
        self.statements = []
        self.commits = 0
        self.closes = 0

    def execute(self, sql, params=None):
        statement = str(sql)
        if params is not None and statement.count("%s") != len(params):
            raise AssertionError(
                "发出的 SQL 占位符 %d 个、绑定值 %d 个，对不上：%s"
                % (statement.count("%s"), len(params), statement))
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

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closes += 1


class _NeverAsked:
    """切了读之后，遗留 Chroma 腿一个调用都不该收到；收到就是 AssertionError。"""

    name = "legacy_chroma_must_not_be_asked"

    def query(self, **kwargs):
        raise AssertionError("PG 腿答了就不许再问 collection.query：" + repr(kwargs))

    def get(self, **kwargs):
        raise AssertionError("PG 腿答了就不许再问 collection.get：" + repr(kwargs))


@pytest.fixture
def connection(monkeypatch):
    """把 pg_store 唯一的建连接缝换成假件：vector_mirror() 走的就是 _connect。"""
    fake = _FakeConnection()
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: fake)
    return fake


def _build_retriever(tmp_path, monkeypatch, *, backend):
    if backend is not None:
        monkeypatch.setattr(indexing, "INDEX_BACKEND", backend)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    hot_index.reset_hot_index_diagnostics()
    pg_store.reset_vector_read_diagnostics()
    rt.reset_search_shape()
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    return instance


@pytest.fixture
def retriever_on(tmp_path, monkeypatch, connection):
    """切读态：开关在 pgvector、双写在开、Chroma 腿设成"一问就红"。"""
    instance = _build_retriever(tmp_path, monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    instance.collection = _NeverAsked()
    return instance


@pytest.fixture
def retriever_off(tmp_path, monkeypatch, connection):
    """默认态：INDEX_BACKEND 一个字不动（仍是 chroma），读腿必须一 SQL 都不发。"""
    return _build_retriever(tmp_path, monkeypatch, backend=None)


# ---------------------------------------------------------------------- 开关本身


def test_the_switch_defaults_to_the_legacy_engine(retriever_off, connection):
    """本轮硬要求"默认值不翻"：把 indexing.INDEX_BACKEND 的字面量改掉，这条立刻红。"""
    assert indexing.read_backend() == "chroma"
    assert indexing.pgvector_reads_enabled() is False
    assert retriever_off._pgvector_hits(list(QUERY), 5, WHERE_ADMIN) is None
    assert connection.search_statements() == []
    assert connection.statements == []


def test_an_unrecognised_backend_does_not_move_the_reads(monkeypatch):
    """"pg_vetcor" 这种手滑必须留在遗留引擎上并说一句话，不许悄悄试另一个引擎。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND", "pg_vetcor")

    assert indexing.read_backend() == "chroma"
    assert indexing.pgvector_reads_enabled() is False


def test_the_version_ledger_and_the_read_path_share_one_backend_set():
    """台账认的两个值与读路径认的两个值是同一份字面量，不许长成两套。"""
    assert indexing.INDEX_BACKENDS == frozenset({"chroma", "pgvector"})
    assert indexing.INDEX_BACKEND in indexing.INDEX_BACKENDS
    assert indexing.PGVECTOR_BACKEND == "pgvector"


# ---------------------------------------------------------------------- 读腿真的答


def test_switched_reads_answer_from_pgvector_and_are_attributed_to_it(retriever_on,
                                                                     connection):
    """把 PG 腿的返回值改成 None（等于没接上）：这条立刻红，因为 Chroma 那条会先炸。"""
    hits = retriever_on.search("住宿费标准", k=5, where=WHERE_ADMIN)

    assert [item["source"] for item in hits] == ["a.txt", "b.txt"]
    assert [item["content"] for item in hits] == [row[1] for row in ROWS]
    assert [item["chunk_index"] for item in hits] == [0, 1]
    assert [item["department"] for item in hits] == ["研发中心", ""]
    reading = rt.search_shape_diagnostics()["last"]
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_PGVECTOR
    assert reading["leg"] == "semantic"
    assert reading["rows_returned"] == len(ROWS) == reading["hits_built"]
    assert len(connection.search_statements()) == 1


def test_the_pg_hits_carry_exactly_the_hit_dict_shape(retriever_on):
    """R44 钉住的命中形状：换引擎不许多一个键、少一个键 —— 与 _hit_dicts 逐项对。

    形状对不等于内容对：只比键名时，把 `_READ_COLUMNS` 里的 classification 摘掉仍然全绿
    （缺的键会由 `_hit_dicts` 补成 None，键集合一个字没变）。2026-09-24 的变异复验就是
    靠这条抓出来的，所以下面这行点名列是必需的，不是装饰。
    """
    hits = retriever_on.search("q", k=5, where=WHERE_ADMIN)
    baseline = retriever_on._hit_dicts(["正文"], [{"filename": "x.txt"}], "semantic", "")

    assert set(hits[0]) == set(baseline[0])
    assert all(item["retrieval_mode"] == "semantic" for item in hits)
    assert all(item["retrieval_reason"] == "" for item in hits)
    #: 点名列：每一列都得真从 SQL 里走回来，且不许被后面的补默认值蒙过去。
    assert [item["classification"] for item in hits] == [2, None]
    assert [item["source"] for item in hits] == ["a.txt", "b.txt"]
    assert [item["content"] for item in hits] == [row[1] for row in ROWS]


def test_a_null_classification_comes_back_as_null_not_as_level_one(retriever_on):
    """R57：缺密级那行原样交回 None，由后面的闸门裁；读腿不许替它把密级补成 1。"""
    hits = retriever_on.search("q", k=5, where=WHERE_ADMIN)

    assert hits[1]["classification"] is None


def test_the_read_leg_commits_nothing(retriever_on, connection):
    """只读腿不顺手 commit：探测开的那个事务随连接结束，读不该留下任何写痕迹。"""
    retriever_on.search("q", k=5, where=WHERE_ADMIN)

    assert connection.commits == 0
    assert connection.closes >= 1


def test_k_zero_asks_for_no_rows_instead_of_a_negative_limit(retriever_on, connection):
    """LIMIT 负数在 PG 里是语法错误：k<=0 折成 0 行，与遗留腿一样答不出东西。"""
    retriever_on.search("q", k=0, where=WHERE_ADMIN)
    assert connection.search_statements()[-1][1][-1] == 0

    #: k=0 与 k<0 必须折成同一个东西：只断言 k=0 时，`limit = int(k)` 这种写法也能过，
    #: 负数就会原样送进 LIMIT 变成 PG 语法错误。所以这里补一发负数。
    retriever_on.search("q", k=-5, where=WHERE_ADMIN)
    assert connection.search_statements()[-1][1][-1] == 0


# ---------------------------------------------------------------------- 谓词下推


def test_scope_filter_travels_into_the_where_clause(retriever_on, connection):
    """判据④的正身：权限谓词进了 SQL，而不是取回整库再在 Python 里筛。"""
    retriever_on.search("q", k=5, where=WHERE_DEPARTMENT)

    sql, params = connection.search_statements()[-1]
    assert "WHERE" in sql, sql
    assert "classification = ANY(%s::integer[])" in sql
    assert "department = ANY(%s::text[])" in sql
    lists = [item for item in params if isinstance(item, list)]
    assert [1, 2] in lists
    assert ["研发中心"] in lists


def test_the_filter_is_bound_as_a_parameter_not_pasted_into_the_sql(retriever_on,
                                                                   connection):
    retriever_on.search("q", k=5, where={"department": {"$in": ["研发中心'或1=1"]}})

    sql, params = connection.search_statements()[-1]
    assert "研发中心" not in sql, "部门名被拼进了语句本体，不是绑参"
    assert ["研发中心'或1=1"] in [item for item in params if isinstance(item, list)]


@pytest.mark.parametrize("where", [
    {"filename": {"$in": ["a.txt"]}},
    {"$or": [WHERE_ADMIN]},
    {"classification": {"$eq": 1}},
    {"classification": {"$in": ["1"]}},
    {"classification": {"$in": [1]}, "department": {"$in": ["研发中心"]}},
    {"department": {"$in": [{"nested": 1}]}},
    "not-a-dict",
    {"classification": 2},
])
def test_an_untranslatable_filter_sends_no_vector_query(where, connection, monkeypatch):
    """本单的反证钉：把 `sql_scope_filter` 的 raise 换成 `return "", []` 这条立刻红。

    那处改动看着无害 —— 只是"不认识就不过滤" —— 交回的却是别人的高分 chunk：权限过滤掉进
    "当作没有过滤"那一格，而名次照旧、看起来完全像一次正常召回。
    """
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    pg_store.reset_vector_read_diagnostics()

    with pytest.raises(pg_store.VectorReadRejectedError) as refused:
        pg_store.read_topk(query_vector=list(QUERY), k=5, where=where)

    assert refused.value.reason == pg_store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE
    assert connection.search_statements() == []


def test_no_filter_at_all_is_a_legal_shape(connection, monkeypatch):
    """where=None 是热集与 scripts/compare_vector_recall.py 用的合法形状，不是翻译失败。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")

    clause, params = pg_store.sql_scope_filter(None)
    rows = pg_store.read_topk(query_vector=list(QUERY), k=5, where=None)

    assert clause == "" and params == []
    assert len(rows) == len(ROWS)
    assert "WHERE" not in connection.search_statements()[-1][0]


# ---------------------------------------------------------------------- 其余拒答面


def test_reads_refuse_while_the_dual_write_switch_is_off(monkeypatch):
    """双写没开，chunk_vectors 是一库空：读切过去只会问出零行，那必须是拒答而不是空答。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "off")

    with pytest.raises(pg_store.VectorReadRejectedError) as refused:
        pg_store.read_topk(query_vector=list(QUERY), k=5, where=WHERE_ADMIN)

    assert refused.value.reason == pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE


def test_an_unmapped_distance_spelling_is_a_refusal_not_a_guessed_operator(
        monkeypatch):
    """0010 的 CHECK 只收三种拼法；认不出来就不许挑一个算符把排序凑出来。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: _FakeConnection(
        distance_function="l1"))

    with pytest.raises(pg_store.VectorReadRejectedError) as refused:
        pg_store.read_topk(query_vector=list(QUERY), k=5, where=WHERE_ADMIN)

    assert refused.value.reason == pg_store.REASON_VECTOR_READ_OPERATOR_UNKNOWN


def test_the_operator_follows_the_recorded_scope(connection, monkeypatch):
    """索引是 vector_l2_ops 建的，SQL 就必须走 <->；换口径就换算符，不写死。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")

    pg_store.read_topk(query_vector=list(QUERY), k=5, where=WHERE_ADMIN)

    assert pg_store.DISTANCE_OPERATORS["l2"] in connection.search_statements()[-1][0]


def test_a_refusal_falls_back_to_the_legacy_leg_which_still_filters(
        retriever_on, connection, monkeypatch):
    """拒答不许把检索问出异常：退回遗留腿，而且那一条仍带着同一份 where 下推。"""
    asked = {}

    class _Answers:
        name = "legacy_chroma"

        def query(self, **kwargs):
            asked.update(kwargs)
            return {"ids": [["c.txt_0"]], "documents": [["正文"]],
                    "metadatas": [[{"filename": "c.txt", "chunk_index": 0,
                                    "classification": 1, "department": "研发中心"}]],
                    "distances": [[0.5]]}

    monkeypatch.setattr(
        pg_store, "_connect",
        lambda url, factory: (_ for _ in ()).throw(pg_store.VectorWriteRejectedError(
            "连不上", reason=pg_store.REASON_VECTOR_MIRROR_UNAVAILABLE,
            model=configured_model())))
    retriever_on.collection = _Answers()

    hits = retriever_on.search("q", k=5, where=WHERE_DEPARTMENT)

    assert [item["source"] for item in hits] == ["c.txt"]
    assert asked["where"] == WHERE_DEPARTMENT
    assert rt.search_shape_diagnostics()["last"]["answered_by"] == (
        rt.RETRIEVAL_SERVER_CHROMA)
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_MIRROR_UNAVAILABLE)
    assert connection.search_statements() == []


def configured_model():
    return indexing.configured_embedding_scope().embedding_model


# ---------------------------------------------------------------------- 热集让路


def test_the_hot_index_steps_aside_when_reads_are_switched(retriever_on, monkeypatch):
    """删掉 `_hot_hits` 顶部那枚守卫：这条立刻红 —— 假 collection 的 get() 会先炸。

    热集常驻的是 Chroma 那一份向量。读路径切到 PG 之后让它继续抢答，"切了读"就只对热集问
    不出的那部分生效，大半流量仍在读旧引擎，而诊断里它长得像已经切完了。
    """
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: True)

    assert retriever_on._hot_hits(list(QUERY), 5, WHERE_ADMIN, None) is None
    assert hot_index.hot_index_diagnostics()["last_bypass_reason"] == (
        hot_index.REASON_READ_BACKEND_SWITCHED)
    assert retriever_on.collection.__class__.__name__ == "_NeverAsked"
