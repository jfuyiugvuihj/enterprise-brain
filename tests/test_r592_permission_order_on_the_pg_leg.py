# -*- coding: utf-8 -*-
"""R59 块2 判据③ —— 谓词下推之后，「先按权限过滤、后去重」必须还长在原来的位置上。

计划书 §3 P4 把这条写成硬要求：R45/R57 定的口径是先按权限过滤、后去重，下推 PG WHERE 之后
过滤仍必须发生在去重之前的同一位置；R45/R57 全套越权用例逐条平移且全绿；禁改断言迁就实现。

本文件就是「平移」那一半：把同样几种越权形状搬到切读态重跑一遍，一格一格的判据都写在用例里。
原有那三件（tests/test_prefiltering.py 21 枚、tests/test_classification_fail_closed.py 6 枚、
tests/test_r159_cross_scope_matrix.py 3 枚）在本单里一个字未改，交回单给的是它们与切读态
并排跑的读数。判定本体仍只有 app/rag/filters.py 的 DocumentRetrievalScope.allows 一处：
本文件不新写第二套密级/部门规则，也不放宽任何一档。

五种形状：

1. 镜像漏给一行不属于这个账号的（模拟「召回实现不执行 where」那一类，正是 _retain_permitted
   存在的理由）：端点交给模型的那段上下文里一个字都不许出现，而且必须走「命中了但一份都不
   给看」那第二张脸，不许改口成检索无结果。
2. 镜像交回 classification 为 NULL 的行（R57 fail-closed）：同样不可见；且命中字典里那一格
   必须是 None，不许被凭空补成 1 级 —— 骗过唯一权限判定的正是那个默认值。
3. 同一串正文的两份拷贝，第一份缺密级、第二份合法：顺序若错成先去重后过滤，合法那份会跟着
   第一份一起被丢掉，于是凭空误拒一条合法文档。本格用同一份正文把两种顺序区分开。
4. 翻译不出来的谓词（一枚 $or）：下推腿必须拒答，而不是退化成「没有 WHERE」。拒答之后退回
   遗留腿，同一份 where 原样带过去，一条 SQL 都不发。
5. 含空串的 $in（filters 今天造不出这种形状，但那是判据的边界，不是实现可以选脸的地方）：
   同样拒答、同样带着谓词回落，稳定码 vector_read_filter_untranslatable。

反证：把 retrieval_pipeline 里 _retain_permitted 与 _deduplicate 的嵌套换成先去重后过滤
⇒ 第 3 格当场红；把 pg_store._scope_clause 的空串分支摘掉 ⇒ 第 5 格当场红；把 _hit_dicts
的 classification 改回 meta.get(...) 带默认值 1 ⇒ 第 2 格当场红。
"""

import pytest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.rag import indexing
from app.rag import pg_store
from app.rag import retrieval_pipeline as pipeline_module
from app.rag import retriever as rt
from app.rag.filters import resolve_document_retrieval_scope
from app.rag.retriever import DocumentRetriever

DIM = 4
QUERY = [0.5] * DIM

MINE = "研发中心的差旅标准。"
THEIRS = "财务中心的报销标准。"
NOLEVEL = "研发中心那份没标密级的旧制度。"
DUPE = "同一串正文，两份拷贝。"

RD = "研发中心"
FIN = "财务中心"

WHERE_STAFF = {"$and": [{"classification": {"$in": [1, 2]}},
                        {"department": {"$in": [RD]}}]}
WHERE_OR = {"$or": [WHERE_STAFF, {"filename": {"$eq": "x.txt"}}]}
WHERE_EMPTY_DEPARTMENT = {"department": {"$in": [""]}}


def _row(vector_id, content, filename, classification, department, distance=1.0):
    """按 pg_store._READ_COLUMNS 加 distance 的顺序摆一行，不按行号记。"""
    return (vector_id, content, filename, 0, classification, department, distance)


def _meta(filename, classification, department):
    return {"filename": filename, "chunk_index": 0,
            "classification": classification, "department": department}


def _user(username, department, role="staff"):
    return {"id": username, "username": username, "role": role, "department": department}


def _headers(username):
    from app.common.auth import create_token

    return {"Authorization": "Bearer " + create_token(username)}


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


class _PgDouble:
    """假镜像：行由用例给，并且自己数占位符。

    块1 立过这条规矩（跟进单与 pg_store._scope_clause 的注释都记着）：一枚不数 arity 的假
    连接会给坏 SQL 放行。读路径上每一枚语句的 %s 个数都等于参数个数，这里逐条判。
    """

    def __init__(self, rows=()):
        configured = indexing.configured_embedding_scope()
        self.scope_row = (configured.embedding_model, int(configured.dimension), "l2")
        self.column_type = ("vector(%d)" % int(configured.dimension),)
        self.rows = list(rows)
        self.statements = []

    def execute(self, sql, params=None):
        statement = str(sql)
        values = list(params or [])
        if statement.count("%s") != len(values):
            raise AssertionError(
                "SQL 占位符与参数不等：" + str(statement.count("%s")) + " 对 "
                + str(len(values)))
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
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _matches(metadata, where):
    """假库对 where 的求值：复刻 chromadb 的 $and / $in / $eq 与「缺键不匹配」。

    这不是第二套权限规则。生产判定只有 scope.allows 一处；这里只是让假句柄像真库一样先按
    where 裁行，好把「下推那层没执行 where」与「执行了但仍漏一行」分成两格。
    """
    if not where:
        return True
    if "$or" in where:
        return any(_matches(metadata, clause) for clause in where["$or"])
    if "$and" in where:
        return all(_matches(metadata, clause) for clause in where["$and"])
    for key, condition in where.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$eq" in condition and value != condition["$eq"]:
                return False
        elif value != condition:
            return False
    return True


class _Handle:
    """旧引擎句柄：query() 与 get() 分开记，两处都按 where 裁行（与 chroma 同形）。"""

    name = "enterprise_docs"

    def __init__(self, rows=()):
        self._rows = list(rows)
        self.queries = []
        self.gets = []

    def _kept(self, where):
        return [row for row in self._rows
                if _matches(row[2] if len(row) > 2 else {}, where)]

    def query(self, **kwargs):
        self.queries.append(kwargs)
        kept = self._kept(kwargs.get("where"))
        limit = int(kwargs.get("n_results") or 0)
        if limit:
            kept = kept[:limit]
        return {
            "ids": [[row[0] for row in kept]],
            "documents": [[row[1] for row in kept]],
            "metadatas": [[row[2] for row in kept]],
        }

    def get(self, where=None):
        self.gets.append(where)
        kept = self._kept(where)
        return {
            "ids": [row[0] for row in kept],
            "documents": [row[1] for row in kept],
            "metadatas": [row[2] for row in kept],
        }


def _legacy(vector_id, content, classification, department):
    """遗留腿的行形状：(vector_id, content, metadata)，与 _Handle._kept 的约定一致。"""
    return (vector_id, content, _meta(vector_id.split(".")[0], classification, department))


class _AnsweringModel:
    def __init__(self):
        self.prompts = []

    def chat(self, messages=None, source=None, stream=True):
        self.prompts.append(messages[0]["content"])
        delta = SimpleNamespace(content="回答完成")
        return [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]


class _CapturingReranker:
    def __init__(self):
        self.inputs = []

    def rerank(self, query, docs, top_k=5):
        self.inputs.append(list(docs))
        return list(docs)[:top_k]


class _NoKeywordRecall:
    def search(self, query, k=10, pred=None):
        return []


def _switch_on(monkeypatch, double):
    """切读态：只走块1 那枚开关（模块常量那一脉），不自造第二把。"""
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    pg_store.reset_vector_read_diagnostics()
    rt.reset_search_shape()


def _retriever(tmp_path, monkeypatch, handle):
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = handle
    return instance


def _pipeline(instance):
    semantic = pipeline_module.SemanticSearcher.__new__(pipeline_module.SemanticSearcher)
    semantic.retriever = instance
    pipeline = pipeline_module.RetrievalPipeline.__new__(pipeline_module.RetrievalPipeline)
    pipeline.semantic = semantic
    pipeline.bm25 = _NoKeywordRecall()
    pipeline.rewriter = SimpleNamespace(rewrite=lambda query: {})
    pipeline.reranker = _CapturingReranker()
    return pipeline


@pytest.fixture()
def rd_user(monkeypatch):
    """研发中心、档位含 1 与 2 的普通账号。"""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: _user("rd-user", RD))
    return "rd-user"


def _post(message="差旅标准是什么"):
    from app.main import app

    return TestClient(app).post("/api/v1/chat", json={"message": message},
                               headers=_headers("rd-user"))


# ---------------------------------------- 1 · 镜像漏给别人的行，一个字都不许进上下文


def test_a_foreign_row_from_the_mirror_never_reaches_the_answer(tmp_path, monkeypatch,
                                                                rd_user):
    """形状 1：下推带了 WHERE，镜像仍漏给一行财务中心的 —— 端点必须裁掉它。

    判据两格：越权正文一个字不进上下文；并且必须走「命中了但一份都不给看」那第二张脸，
    不许改口成检索无结果（两张脸是 R45/R154 定的口径，切读不许把它们并成一张）。
    """
    double = _PgDouble(rows=[_row("fin.txt_0", THEIRS, "fin.txt", 1, FIN)])
    _switch_on(monkeypatch, double)
    instance = _retriever(tmp_path, monkeypatch, _Handle())
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", instance)
    model = _AnsweringModel()
    monkeypatch.setattr(chat, "model_handler", model)

    assert _post().status_code == 200
    assert len(double.search_statements()) == 1
    prompt = model.prompts[0]
    assert THEIRS not in prompt, "越权正文进了模型上下文"
    assert "暂无相关文档" not in prompt, "改口成了检索无结果"
    assert "可见范围之外" in prompt, "没走那张『命中了但不给看』的脸"
    scope = resolve_document_retrieval_scope(Principal.from_user(_user("rd-user", RD)))
    assert scope.refusal_code({"classification": 1, "department": FIN}) == (
        "department_scope_denied")


# ------------------------------------------- 2 · NULL 密级那一行仍然 fail-closed


def test_a_null_classification_row_from_the_mirror_stays_invisible(tmp_path, monkeypatch,
                                                                   rd_user):
    """形状 2（R57）：PG 的 classification 是 NULL —— 不可见，而且不许被补成 1 级。

    两格分开判：命中字典里那一格必须还是 None（默认值 1 正是当年骗过唯一权限判定的写法），
    端点那一头必须看不见这份正文。反证：把 retriever._hit_dicts 的 classification 改回
    meta.get(...) 带默认值 1 ⇒ 第一格当场红。
    """
    double = _PgDouble(rows=[_row("rd.txt_0", NOLEVEL, "rd.txt", None, RD)])
    _switch_on(monkeypatch, double)
    instance = _retriever(tmp_path, monkeypatch, _Handle())

    hits = instance.search("差旅标准", k=5, where=WHERE_STAFF)

    assert [hit["classification"] for hit in hits] == [None], "缺密级被凭空补了值"
    scope = resolve_document_retrieval_scope(Principal.from_user(_user("rd-user", RD)))
    assert hits and scope.allows(hits[0]) is False
    assert scope.refusal_code(hits[0]) == "resource_scope_missing"

    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", instance)
    model = _AnsweringModel()
    monkeypatch.setattr(chat, "model_handler", model)
    _post()
    assert NOLEVEL not in model.prompts[0], "缺密级那份上了屏"
    assert "可见范围之外" in model.prompts[0]


# ------------------------------------- 3 · 过滤必须在去重之前（顺序错了就是误拒）


def test_the_permission_filter_still_runs_before_deduplication(tmp_path, monkeypatch):
    """形状 3（R45 缺陷②）：同一串正文两份拷贝，先到的那份缺密级。

    先去重后过滤 ⇒ 合法那份跟着缺密级那份一起被丢，凭空误拒一条合法文档；
    先过滤后去重 ⇒ 合法那份留下。两串正文一字不差，所以这一格只可能由顺序决定。
    """
    double = _PgDouble(rows=[
        _row("dup-a.txt_0", DUPE, "dup-a.txt", None, RD),
        _row("dup-b.txt_0", DUPE, "dup-b.txt", 1, RD),
    ])
    _switch_on(monkeypatch, double)
    instance = _retriever(tmp_path, monkeypatch, _Handle())
    pipeline = _pipeline(instance)
    principal = Principal.from_user(_user("rd-user", RD))
    scope = resolve_document_retrieval_scope(principal)

    seen = []
    original = pipeline_module._deduplicate

    def _spy(docs):
        seen.append(list(docs))
        return original(docs)

    monkeypatch.setattr(pipeline_module, "_deduplicate", _spy)
    docs, _rewrites = pipeline.search_for_principal("差旅标准", principal, top_k=5,
                                                   tier="fast")

    assert seen, "去重那一步没被走到，这一格就无从判起"
    for batch in seen:
        for hit in batch:
            assert scope.allows(hit), "去重收到了未过滤的命中：顺序漂成了先去重"
    assert [doc["content"] for doc in docs] == [DUPE], "合法那份被误拒了（或两份都留下了）"
    assert pipeline.reranker.inputs[-1] and all(
        scope.allows(hit) for hit in pipeline.reranker.inputs[-1])


# ------------------------------- 4 · 翻译不出来的谓词：拒答下推，但不许丢掉权限过滤


def test_an_untranslatable_predicate_refuses_the_pushdown(tmp_path, monkeypatch):
    """形状 4：一枚 $or。下推腿只能拒答，不能退化成「没有 WHERE」。

    判三格：一条排名 SQL 都不发；同一份 where 原样带进遗留腿（回落不等于放宽）；
    稳定码 vector_read_filter_untranslatable 记进那本绕行账。
    """
    double = _PgDouble(rows=[_row("rd.txt_0", MINE, "rd.txt", 1, RD)])
    _switch_on(monkeypatch, double)
    handle = _Handle(rows=[_legacy("rd.txt_0", MINE, 1, RD)])
    instance = _retriever(tmp_path, monkeypatch, handle)

    hits = instance.search("差旅标准", k=5, where=WHERE_OR)

    assert double.search_statements() == [], "谓词没翻译出来还发 SQL，就是发了条没 WHERE 的"
    assert handle.queries, "拒答之后没回遗留腿"
    assert handle.queries[-1]["where"] == WHERE_OR, "回落时把权限谓词丢了"
    assert [hit["content"] for hit in hits] == [MINE]
    reading = pg_store.vector_read_diagnostics()
    assert reading["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE)
    assert reading["answered"] == 0


# ------------------------------ 5 · 含空串的 $in：两侧表示法不同，宁可拒答也不猜


def test_an_empty_department_value_refuses_the_pushdown_too(tmp_path, monkeypatch):
    """形状 5（块1 判据②c 的权限半边）：department 的 $in 里有空串。

    镜像把缺部门归一成空串，遗留引擎那边压根没有这个键 —— 同一份 $in 在两侧答案相反。
    猜哪一侧都会让下推后的过滤比它替代的那份更宽或更窄，所以只能拒答：不发 SQL、带着同一份
    where 回落遗留腿、记同一枚稳定码。反证：摘掉 pg_store._scope_clause 里那个空串分支
    ⇒ 本用例当场红（会发出一条把空串当命中条件的 SQL）。
    """
    double = _PgDouble(rows=[_row("rd.txt_0", MINE, "rd.txt", 1, RD)])
    _switch_on(monkeypatch, double)
    handle = _Handle(rows=[_legacy("rd.txt_0", MINE, 1, RD)])
    instance = _retriever(tmp_path, monkeypatch, handle)

    hits = instance.search("差旅标准", k=5, where=WHERE_EMPTY_DEPARTMENT)

    assert double.search_statements() == [], "空串那一档发了 SQL：下推比原口径宽"
    assert handle.queries[-1]["where"] == WHERE_EMPTY_DEPARTMENT
    assert hits == [], "遗留腿按原口径答：没有哪个账号的可见部门是空串"
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE)
