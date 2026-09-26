# -*- coding: utf-8 -*-
"""R59 块1 判据②(a)/④/⑤ —— 切读态下"PG 腿交回 0 行"必须降级，不许当合法空答案。

R269（`c3b2983`，跟进单 §101.15 二·第①处）点名的三处"切读治不到"里，这一处与引擎无关：
旧读法把库的 0 行原样交回，用户拿到的是一份空上下文，而唯一的降级分支只挂在
"embedding 挂掉"那一支上（R269 记的 `retriever.py:1490-1492` 即 `search()` 里遗留腿那一
支，本班改动后行号已漂；它今天还在答生产流量，判据⑤不许动它的现行为）。切到 PG 之后同一个形状只会换个引擎发生：权限谓词落空、
`vector_scope` 判定为不认识 ⇒ 0 行 ⇒ 空上下文。所以降级这一刀必须落在本块，
而不是等合闸之后再补。

全程不连真库、不打 Ollama、不开服务：PG 腿走 `connection_factory` 那枚既有接缝（假连接
按语句前缀分派，并且**真的尊重 LIMIT** —— 上一班的假件无视 LIMIT，k=0 那格就是假绿）；
遗留腿走一只记账的假 collection，`query()` 与 `get()` 分开记，因为本单要钉的正是
"降级读的是内容，不是那台要退役的 ANN"。

反证（判据⑥）：
- 把 `_pgvector_hits` 的 `if not rows:` 那一支摘掉（改成 `if False and not rows:`）
  ⇒ 本文件点名五枚红：`test_zero_rows_from_the_pg_leg_degrade_instead_of_answering_empty` /
  `test_the_degraded_answer_says_which_leg_it_came_from` /
  `test_the_degradation_never_asks_the_retiring_ann` /
  `test_the_empty_search_and_the_empty_leg_are_two_different_readings` /
  `test_k_zero_still_invents_no_hits`（实测 5 failed, 5 passed）。
- 把 `indexing.INDEX_BACKEND_DEFAULT` 翻成 pgvector ⇒
  `test_the_default_ships_on_the_legacy_engine` 红（判据⑤）。
"""

import pytest

from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

DIM = 4
QUERY = [0.5] * DIM
WHERE_ADMIN = {"classification": {"$in": [1, 2, 3]}}

BODY_A = "住宿费标准是每晚500元。"
BODY_B = "年假按工龄计算。"


def _row(vector_id, *, content, filename, chunk_index, classification, department,
         distance=1.0):
    return (vector_id, content, filename, chunk_index, classification, department,
            distance)


ROWS_TWO = [
    _row("a.txt_0", content=BODY_A, filename="a.txt", chunk_index=0,
         classification=2, department="研发中心"),
    _row("b.txt_1", content=BODY_B, filename="b.txt", chunk_index=1,
         classification=None, department=""),
]


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


class _PgDouble:
    """探测两条 + 读一条。尊重 LIMIT：k=0 与谓词落空都得真的交回 0 行。"""

    def __init__(self, rows=None, *, distance_function="l2"):
        configured = indexing.configured_embedding_scope()
        self.scope_row = (configured.embedding_model, int(configured.dimension),
                          distance_function)
        self.column_type = ("vector(%d)" % int(configured.dimension),)
        self.rows = ROWS_TWO if rows is None else rows
        self.statements = []
        self.commits = 0
        self.closes = 0

    def execute(self, sql, params=None):
        statement = str(sql)
        if params is not None and statement.count("%s") != len(params):
            raise AssertionError("占位符 %d 个、绑定值 %d 个：%s"
                                 % (statement.count("%s"), len(params), statement))
        self.statements.append((statement, params))
        if "vector_scope" in statement:
            return _Result(scalar=self.scope_row)
        if "pg_attribute" in statement:
            return _Result(scalar=self.column_type)
        if "FROM " + pg_store.DEFAULT_VECTOR_TABLE in statement:
            kept = list(self.rows)
            if params:
                limit = int(params[-1])
                kept = kept[:limit] if limit > 0 else []
                # 谓词落空那一格由假件扮演真库：绑进来的集合里没有这一行，就不交。
                lists = [item for item in params if isinstance(item, list)]
                for column, index in (("classification", 4), ("department", 5)):
                    for allowed in lists:
                        if allowed and statement.find(column + " = ANY") >= 0:
                            kept = [row for row in kept
                                    if row[index] is not None and row[index] in allowed]
            return _Result(rows=kept)
        raise AssertionError("假连接收到没准备好的语句：" + statement)

    def search_statements(self):
        return [item for item in self.statements if "ORDER BY embedding" in item[0]]

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closes += 1


class _ChromaDouble:
    """只记账：语义腿（query）与内容扫描（get）分开记，本文件多枚钉靠这两个计数。"""

    name = "enterprise_docs"

    def __init__(self, documents=()):
        self.documents = list(documents)
        self.queries = []
        self.gets = []

    def query(self, **kwargs):
        """按 chromadb 的"每问一组列"形状交回，并尊重 n_results。

        空列表是一种答复，不是一种形状：遗留腿那一条在本文件里既要能答出行（默认态、
        回滚态），也要能答出 0 行（拒答退回时），所以它按自己存的正文回，而不是硬交空。
        """
        self.queries.append(kwargs)
        wanted = int(kwargs.get("n_results") or 0)
        picked = self.documents[:wanted] if wanted > 0 else []
        return {
            "ids": [["legacy_%d" % position for position in range(len(picked))]],
            "documents": [picked],
            "metadatas": [[{"filename": "legacy.txt", "chunk_index": position,
                            "classification": 1, "department": ""}
                           for position in range(len(picked))]],
        }

    def get(self, where=None):
        self.gets.append(where)
        return {
            "ids": ["legacy_%d" % position for position in range(len(self.documents))],
            "documents": self.documents,
            "metadatas": [{"filename": "legacy.txt", "chunk_index": position,
                           "classification": 1, "department": ""}
                          for position in range(len(self.documents))],
        }


@pytest.fixture
def switched(request, tmp_path, monkeypatch):
    """切读态 + 双写在开 + 一条指定内容的 PG 腿，默认答卷 ROWS_TWO。

    要换答卷的用例写 `@pytest.mark.parametrize("switched", [[]], indirect=True)`；
    这里不用自定义 marker，因为登记它的地方是 pyproject.toml 的 markers（本块禁域），
    而未登记的 marker 在 `--strict-markers` 下会直接报错、平时也刷一片告警。
    """
    rows = getattr(request, "param", ROWS_TWO)
    double = _PgDouble(rows=rows)
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_read_diagnostics()
    pg_store.reset_vector_corpus_diagnostics()
    rt.reset_search_shape()
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = _ChromaDouble(["年假按工龄计算。"])
    return instance


def _shape():
    return rt.search_shape_diagnostics()["last"]


# ------------------------------------------------------------------ ②(a) 0 行即降级


@pytest.mark.parametrize("switched", [[]], indirect=True)
def test_zero_rows_from_the_pg_leg_degrade_instead_of_answering_empty(switched):
    """判据②(a) 正身：0 行不再是"库说没有"，而是一次带稳定码的降级。

    把 `_pgvector_hits` 里 `if not rows:` 那一支删掉，这条立刻红：交回来的会是空列表，
    而 `answered_by` 会停在 pgvector——用户拿空上下文，日志上一切正常。
    """
    hits = switched.search("年假", k=5, where=WHERE_ADMIN)

    assert hits, "0 行必须降级，不许把空上下文交回用户"
    assert [item["retrieval_mode"] for item in hits] == ["keyword_fallback"]
    assert hits[0]["retrieval_reason"] == rt.RETRIEVAL_REASON_PG_ZERO_ROWS
    assert switched.last_search_mode == DocumentRetriever.MODE_KEYWORD
    assert switched.last_search_reason == rt.RETRIEVAL_REASON_PG_ZERO_ROWS


@pytest.mark.parametrize("switched", [[]], indirect=True)
def test_the_degraded_answer_says_which_leg_it_came_from(switched):
    """判据④（R21 那条"看得见"）的延续：稳定码必须有文案，答案侧不许退化成"未记录原因"。"""
    hits = switched.search("年假", k=5, where=WHERE_ADMIN)

    notice = rt.retrieval_degradation_notice(hits)
    assert notice
    assert "未记录原因" not in notice, "新降级码忘了进 EMBEDDING_REASON_LABELS"
    assert "关键词" in notice


@pytest.mark.parametrize("switched", [[]], indirect=True)
def test_the_degradation_never_asks_the_retiring_ann(switched):
    """降级读内容，不读那台要退役的 ANN：query() 零次、get() 至多一次。

    这一枚是判据①与②(a) 的交界：0 行降级如果去问 Chroma 的向量索引，"切了读"就只是一句
    话——R269 那 21 题的病正在那台 ANN 上，降级腿绕开它才算真绕开。
    """
    switched.search("年假", k=5, where=WHERE_ADMIN)

    assert switched.collection.queries == [], "降级腿不许问 collection.query"
    assert len(switched.collection.gets) == 1
    assert switched.collection.gets[0] == WHERE_ADMIN, "降级腿仍带着同一份权限谓词"


@pytest.mark.parametrize("switched", [[]], indirect=True)
def test_the_empty_search_and_the_empty_leg_are_two_different_readings(switched):
    """空结果口径（判据②c 第二处）逐条裁定：0 行的这一问记在关键词腿，PG 腿另记一笔 0。

    裁定写在这里，不写"应一致"：一次问只记一笔 search_shape（与 R158 同规），那一笔说的是
    "谁答了用户"＝关键词腿；"PG 腿答了几行"记在 pg_store 自己的账上。两本账分开的理由是
    它们回答两件事——一件是客户为什么没看到来源，一件是切读合闸后有没有静默退回。
    """
    hits = switched.search("年假", k=5, where=WHERE_ADMIN)

    reading = _shape()
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_KEYWORD_STORE
    assert reading["leg"] == DocumentRetriever.MODE_KEYWORD
    assert reading["degradation_reason"] == rt.RETRIEVAL_REASON_PG_ZERO_ROWS
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ANSWERED
    assert reading["rows_returned"] == len(hits) == reading["hits_built"]
    leg = pg_store.vector_read_diagnostics()
    assert leg["answered"] == 1 and leg["rows"] == 0
    assert leg["last_bypass"] is None, "0 行是答复，不是拒答：不许把两件事记成同一枚码"


def test_a_pg_leg_that_answers_rows_is_not_a_degradation(switched):
    """反向半句：答出行时腿标注仍是 semantic、retrieval_reason 仍是空串——换引擎不是降级。"""
    hits = switched.search("住宿费", k=5, where=WHERE_ADMIN)

    assert hits and all(item["retrieval_mode"] == "semantic" for item in hits)
    assert all(item["retrieval_reason"] == "" for item in hits)
    assert _shape()["answered_by"] == rt.RETRIEVAL_SERVER_PGVECTOR
    assert switched.collection.queries == [] and switched.collection.gets == []


@pytest.mark.parametrize("switched", [[]], indirect=True)
def test_k_zero_still_invents_no_hits(switched):
    """k=0 与真库答 0 行不能长成同一张脸，但两者都不许多给命中。"""
    hits = switched.search("年假", k=0, where=WHERE_ADMIN)

    assert hits == []
    assert _shape()["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert _shape()["degradation_reason"] == rt.RETRIEVAL_REASON_PG_ZERO_ROWS
    assert switched.collection.queries == []


def test_a_refused_pg_leg_still_falls_back_to_the_legacy_semantic_leg(switched, monkeypatch):
    """口径的最后一格，写明白而不是藏起来：唯一还允许问 ANN 的分支是"这一腿根本没答"。

    这条既有语义（R59b `test_a_refusal_falls_back_to_the_legacy_leg_which_still_filters`）
    本块原样保留，因为它换到的是可用性与"不许放宽过滤"两样都保的一边；但它必须**可分辨**：
    形状记 chroma，`vector_read_diagnostics` 记那枚拒答码。半切与不切的区别就在这两笔账上。
    """
    def _refuse(url, factory):
        raise pg_store.VectorReadRejectedError("连不上",
                                               reason=pg_store.REASON_VECTOR_READ_FAILED)

    monkeypatch.setattr(pg_store, "_connect", _refuse)

    hits = switched.search("住宿费", k=5, where=WHERE_ADMIN)

    assert hits and hits[0]["retrieval_mode"] == DocumentRetriever.MODE_SEMANTIC
    assert switched.collection.queries, "拒答才允许走遗留语义腿"
    assert _shape()["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_FAILED)


# --------------------------------------------------------------- ⑤默认不翻 / ④一条 env


def test_the_default_ships_on_the_legacy_engine(tmp_path, monkeypatch):
    """判据⑤：出厂默认仍是 chroma，且默认态一条 SQL 都不发、语料腿也不建连接。

    把 `app/rag/indexing.py:50` 的 INDEX_BACKEND_DEFAULT 翻成 pgvector，这条当场红。
    """
    double = _PgDouble()
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    rt.reset_search_shape()

    assert indexing.INDEX_BACKEND_DEFAULT == "chroma"
    assert indexing.read_backend() == "chroma"
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = _ChromaDouble(["住宿费标准是每晚500元。"])

    hits = instance.search("住宿费", k=5, where=WHERE_ADMIN)

    assert double.statements == []
    assert hits and hits[0]["retrieval_mode"] == DocumentRetriever.MODE_SEMANTIC
    assert instance.collection.queries, "默认态照旧问遗留腿"
    assert _shape()["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA
    assert pg_store.switched_corpus() is None
    assert pg_store.vector_corpus_diagnostics()["source"] == (
        pg_store.CORPUS_SOURCE_NOT_SWITCHED)


def test_rolling_back_takes_one_environment_variable(switched, monkeypatch):
    """判据④：同一进程里把 env 拨回 chroma，下一问就重新由遗留腿答，且不再发 SQL。

    回滚不许依赖重启之外的东西：翻 env 之后 PG 腿交 0 条 SQL、遗留腿交回命中，就是
    "一条 env 秒级回退"的可执行定义。
    """
    assert switched.search("住宿费", k=5, where=WHERE_ADMIN)
    sql_before = len(switched.collection.queries)

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, "chroma")
    hits = switched.search("住宿费", k=5, where=WHERE_ADMIN)

    assert hits, "回滚之后必须仍能答"
    assert len(switched.collection.queries) == sql_before + 1
    assert _shape()["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA


def test_an_unrecognised_backend_value_leaves_the_read_path_alone(tmp_path, monkeypatch):
    """拼错的值不算表态：留在遗留腿上并说一句话（与 R231 那条告警同一个口径）。"""
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, "pg_vetcor")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    double = _PgDouble()
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)

    assert indexing.read_backend() == "chroma"
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = _ChromaDouble(["住宿费标准是每晚500元。"])
    instance.search("住宿费", k=5, where=WHERE_ADMIN)

    assert double.statements == []
