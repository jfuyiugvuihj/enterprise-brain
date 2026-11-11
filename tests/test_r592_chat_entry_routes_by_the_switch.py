# -*- coding: utf-8 -*-
"""R59 块2 判据①②④ —— chat.py 那两张检索脸必须真的跟着 INDEX_BACKEND 走，默认一格不许翻。

计划书 §3 P4 给这一格定的回滚点是「开关拨回 Chroma ＝ 秒级回退」。这句话要有凭据，就得有人
在端点这一层量，而不是只在检索器那一层量：块1 的三枚文件把腿接在 app/rag/retriever.py 与
app/rag/retrieval_pipeline.py 里面，本文件证明的是 chat.py 走进那条腿的全过程。两张脸：
一张是 chat.py 自己唯一那处检索调用（旧版 /chat），另一张是 /ask 借用的那条管线
（由 app/agents/tools.py 调 search_for_principal —— 那枚文件不在本单写域，这里只驱动它）。

六格读数，逐格分开：

1. 默认态（谁都没设 env、常量也没翻）：旧引擎的句柄被问了一次 query，PG 一条 SQL 不发，
   answered_by 是 chroma，交给模型的正文来自旧引擎。这一格是判据①的反证钉落点 ——
   把 indexing.INDEX_BACKEND_DEFAULT 改成 pgvector，本用例当场红。
2. 只设 INDEX_BACKEND=pgvector（模块常量留在出厂值）：排名 SQL 恰好一条，旧句柄 query 与
   get 都是零次，answered_by 是 pgvector，交给模型的正文只可能来自 PG 那一份。
3. 切读态下谓词真的进了 SQL：接线最容易偷的一手是"换了引擎、没带 WHERE"，它答得比谁都快，
   漏的却是别人的部门。所以这里现取 sql_scope_filter 收到的那份 where 与那条 SQL 的参数。
4. PG 腿交回 0 行：块1 判据②(a) 那格降级必须在端点上照样成立 —— 只许内容扫描、不许问那台
   ANN，reason 仍是 pgvector_read_leg_zero_rows。接错一次线，这格就会被"PG 也答了"绕过去。
5. 开关拨回去：同一个进程、同一枚检索器，先 on 后 off，第二问必须回到旧句柄且不新增 SQL。
   回滚点说的是"不重启、不改代码"，所以两问必须在同一进程里发生。
6. /ask 那条管线跟着同一枚开关走：只切一张脸就是计划书 §9.1 给热集立过的那半切态。

全程不连库、不打模型、不在仓库目录建 PersistentClient：假连接走 pg_store._connect 那个既有缝，
旧引擎句柄换成记账替身，检索器一律用 tmp_path 下的目录构造（与块1 同一条路）。
权限过滤的位置（先过滤、后去重）不在本文件重述：另一枚 r592 件专管那一格。
"""

import pytest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.rag import indexing
from app.rag import pg_store
from app.rag import retrieval_pipeline as pipeline_module
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

DIM = 4
QUERY = [0.5] * DIM

#: PG 那份正文与旧引擎那份正文是两串不同的字：回答里出现哪一串，就是"谁答的"的端点级证据。
#: 两侧都给 classification=1 / department=dept-a，让 staff-a 过得了 scope.allows。
PG_TEXT = "PG镜像里的住宿费标准是每晚500元。"
LEGACY_TEXT = "旧引擎里的住宿费标准是每晚400元。"

PG_ROW = ("policy.txt_0", PG_TEXT, "policy.txt", 0, 1, "dept-a", 1.25)


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
    """假 PG 连接：分开记「问排名的那条 SQL」与别的语句，行内容由用例给。"""

    def __init__(self, rows=(PG_ROW,)):
        configured = indexing.configured_embedding_scope()
        self.scope_row = (configured.embedding_model, int(configured.dimension), "l2")
        self.column_type = ("vector(%d)" % int(configured.dimension),)
        self.rows = list(rows)
        self.statements = []

    def execute(self, sql, params=None):
        statement = str(sql)
        self.statements.append((statement, params))
        if statement == pg_store._APPLY_HNSW_EF_SEARCH_SQL:
            # R386：读腿在排名 SQL 之前，会在同一笔事务里把 HNSW 候选宽度定一次。本假件只登记、
            # 不解读——这行该不该发、发在事务内还是事务外、值取自哪一枚真源，全部由
            # tests/test_r386_hnsw_ef_search_is_set_before_the_ranking_sql.py 钉住；在这儿再判
            # 一遍就是 R380 那族"防线只有一处"的病。
            return _Result(scalar="")
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


class _Handle:
    """旧引擎句柄的记账替身：query()＝那台 ANN，get()＝内容扫描，两笔分开数。"""

    name = "enterprise_docs"

    def __init__(self, rows=None):
        stored = rows if rows is not None else [
            ("legacy.txt_0", LEGACY_TEXT, {"filename": "legacy.txt", "chunk_index": 0,
                                           "classification": 1, "department": "dept-a"})]
        self._stored = stored
        self.queries = []
        self.gets = []

    def query(self, **kwargs):
        """chroma 的 query 形状：三列都是"一问一组"的嵌套列。"""
        self.queries.append(kwargs)
        return {
            "ids": [[item[0] for item in self._stored]],
            "documents": [[item[1] for item in self._stored]],
            "metadatas": [[item[2] for item in self._stored]],
        }

    def get(self, where=None):
        """chroma 的 get 形状：平列。降级腿与 list_documents 读的是这一张。"""
        self.gets.append(where)
        return {
            "ids": [item[0] for item in self._stored],
            "documents": [item[1] for item in self._stored],
            "metadatas": [item[2] for item in self._stored],
        }


class _AnsweringModel:
    """记下真正送进模型的 prompt —— "端点最终把谁的正文交给了模型"只能在这里量。"""

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
    """关键词腿交零条：这一格只量语义腿，不掺第二路召回。"""

    def __init__(self):
        self.calls = []

    def search(self, query, k=10, pred=None):
        self.calls.append((query, k))
        return []


def _quiet_the_switch(monkeypatch):
    """恢复到「谁都没说过话」：宿主 shell 里残留的 INDEX_BACKEND 不许冒充读数。"""
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)


def _arm_pg(monkeypatch, double):
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    pg_store.reset_vector_read_diagnostics()
    rt.reset_search_shape()


def _real_retriever(tmp_path, monkeypatch, handle):
    """真构造一枚检索器（目录在 tmp_path 下），只换 embedding 与旧引擎句柄。"""
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = handle
    return instance


def _post_legacy_chat(message="住宿费标准是多少"):
    from app.main import app

    return TestClient(app).post("/api/v1/chat", json={"message": message},
                               headers=_headers("staff-a"))


@pytest.fixture()
def staff_a(monkeypatch):
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: _user("staff-a", "dept-a"))
    return "staff-a"


# ------------------------------------------------------ 1 · 默认态：端点仍读旧引擎


def test_the_chat_entry_ships_on_the_legacy_face(tmp_path, monkeypatch, staff_a):
    """判据①：不给 env 时，/chat 这一问由旧引擎答复，PG 一条 SQL 都不发。

    这一格是计划书 :334 那句「逐题对拍读数出来之前，不许把任何生产路径的默认读后端翻成
    PGVector」在端点层的形状。反证：把 indexing.INDEX_BACKEND_DEFAULT 改成 pgvector ⇒
    本用例红（SQL 变 1 条、answered_by 变 pgvector、旧句柄 query 归零）。
    """
    _quiet_the_switch(monkeypatch)
    double = _PgDouble()
    _arm_pg(monkeypatch, double)
    handle = _Handle()
    _instance = _real_retriever(tmp_path, monkeypatch, handle)
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", _instance)
    model = _AnsweringModel()
    monkeypatch.setattr(chat, "model_handler", model)

    assert indexing.read_backend() == "chroma"
    response = _post_legacy_chat()

    assert response.status_code == 200
    assert response.text == "回答完成"
    assert len(handle.queries) == 1, "默认态这一问必须由旧引擎那台 ANN 答复"
    assert double.search_statements() == [], "默认态一条 SQL 都不许发"
    assert rt.search_shape_diagnostics()["last"]["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA
    assert LEGACY_TEXT in model.prompts[0]
    assert PG_TEXT not in model.prompts[0]


# ------------------------------------------------------ 2 · env 一拨，端点跟着换腿


def test_the_env_switch_moves_the_chat_entry_to_the_pg_leg(tmp_path, monkeypatch, staff_a):
    """判据②：只设 env（常量留在出厂值），/chat 这一问就从 PG 腿取正文。

    开关名沿用块1 的那一枚，本文件不自造第二把：拨的是 indexing.INDEX_BACKEND_ENV，
    读的是 retriever 与 pg_store 已有的那两本账。
    """
    _quiet_the_switch(monkeypatch)
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    double = _PgDouble()
    _arm_pg(monkeypatch, double)
    handle = _Handle()
    instance = _real_retriever(tmp_path, monkeypatch, handle)
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", instance)
    model = _AnsweringModel()
    monkeypatch.setattr(chat, "model_handler", model)

    response = _post_legacy_chat()

    assert response.status_code == 200
    assert len(double.search_statements()) == 1, "切读态这一问恰好一条排名 SQL"
    assert handle.queries == [], "旧引擎那台 ANN 被问了：切读只成了半切"
    assert handle.gets == [], "PG 答出行时不该再去扫内容"
    assert rt.search_shape_diagnostics()["last"]["answered_by"] == (
        rt.RETRIEVAL_SERVER_PGVECTOR)
    assert pg_store.vector_read_diagnostics()["answered"] == 1
    assert PG_TEXT in model.prompts[0]
    assert LEGACY_TEXT not in model.prompts[0]


# ------------------------------------------ 3 · 权限谓词跟着一起下推（不许被接线丢掉）


def test_the_scope_reaches_the_sql_at_the_endpoint(tmp_path, monkeypatch, staff_a):
    """判据②第二半：/chat 交出的那份谓词真的进了 SQL，而不是被接线时丢掉。

    只看 answered_by 会放过"换了引擎、没带 WHERE"这一种形状。这里现取 sql_scope_filter
    收到的 where 对象（下推的唯一入口）与那条 SQL 的参数：两者都必须带着 staff-a 的部门。
    """
    _quiet_the_switch(monkeypatch)
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    double = _PgDouble()
    _arm_pg(monkeypatch, double)
    instance = _real_retriever(tmp_path, monkeypatch, _Handle())
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", instance)
    monkeypatch.setattr(chat, "model_handler", _AnsweringModel())

    captured = []
    original = pg_store.sql_scope_filter

    def _spy(where):
        captured.append(where)
        return original(where)

    monkeypatch.setattr(pg_store, "sql_scope_filter", _spy)
    _post_legacy_chat()

    # 一份 $and 会在递归里被问三次（顶层 + 两枚叶子），所以这里判的是"整份谓词第一个到达
    # 翻译入口"那一笔；翻译次数本身由块1 那枚 where 等价性件管，不在本单重复。
    assert captured, "谓词没经过唯一的翻译入口，下推没有发生"
    where = captured[0]
    assert where["$and"][1]["department"]["$in"] == ["dept-a"], repr(where)
    sql, params = double.search_statements()[-1]
    assert "WHERE" in sql, "带了权限谓词却没有 WHERE：" + sql
    # = ANY(%s::text[]) 交回的是"一枚数组参数"，所以这里把每层列表摊平再比，
    # 免得把"参数确实带上了部门"这一格误判成没带上。
    flat = []

    def _flatten(values):
        for value in values:
            if isinstance(value, (list, tuple)):
                _flatten(value)
            else:
                flat.append(str(value))

    _flatten(list(params))
    assert "dept-a" in flat, "部门没进 SQL 参数：" + repr(params)
    assert str(where["$and"][0]["classification"]["$in"][0]) in flat, repr(params)


# ------------------------------------------------------ 4 · 0 行降级不被接线绕过


def test_pg_zero_rows_still_degrades_at_the_chat_entry(tmp_path, monkeypatch, staff_a):
    """判据④：PG 答 0 行时，端点交给模型的仍是降级腿的正文，不是"暂无相关文档"。

    块1 在检索器里立的规矩（R269 纠正的那条假话）若因 chat.py 接线而绕过去，用户就拿到一份
    空上下文。所以这里量的不是内部函数，而是端点最终交给模型的那段上下文与那枚稳定码。
    """
    _quiet_the_switch(monkeypatch)
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    double = _PgDouble(rows=[])
    _arm_pg(monkeypatch, double)
    handle = _Handle()
    instance = _real_retriever(tmp_path, monkeypatch, handle)
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", instance)
    model = _AnsweringModel()
    monkeypatch.setattr(chat, "model_handler", model)

    response = _post_legacy_chat()

    assert response.status_code == 200
    assert len(double.search_statements()) == 1, "PG 那一腿确实问过，只是交回 0 行"
    assert handle.gets != [], "降级要读内容；内容扫描一次都没有＝接线绕过了降级"
    assert handle.queries == [], "降级只读内容，不许回头问那台 ANN"
    reading = rt.search_shape_diagnostics()["last"]
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_KEYWORD_STORE
    assert reading["degradation_reason"] == rt.RETRIEVAL_REASON_PG_ZERO_ROWS
    assert LEGACY_TEXT in model.prompts[0]
    assert "暂无相关文档" not in model.prompts[0]


# ------------------------------------------------------ 5 · 回滚点：同进程拨回去


def test_flipping_the_knob_back_returns_to_the_legacy_face_in_one_process(
        tmp_path, monkeypatch, staff_a):
    """回滚点：开关拨回 Chroma ＝ 秒级回退，不重启、不改代码。

    两问打在同一个进程、同一枚检索器上，中间只改 env：第一问 PG 答，第二问旧引擎答，
    并且第二问不再新增任何 SQL。这一格是"敢切"的凭据 —— 切不过去随时退得回来。
    """
    _quiet_the_switch(monkeypatch)
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    double = _PgDouble()
    _arm_pg(monkeypatch, double)
    handle = _Handle()
    instance = _real_retriever(tmp_path, monkeypatch, handle)
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "retriever", instance)
    monkeypatch.setattr(chat, "model_handler", _AnsweringModel())

    _post_legacy_chat()

    assert len(double.search_statements()) == 1
    assert handle.queries == []

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.INDEX_BACKEND_DEFAULT)
    _post_legacy_chat()

    assert indexing.read_backend() == "chroma"
    assert len(double.search_statements()) == 1, "拨回去以后还发 SQL，回滚点就是句假话"
    assert len(handle.queries) == 1, "拨回去以后旧引擎一次都没被问，退的不是同一张脸"
    assert rt.search_shape_diagnostics()["last"]["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA


# ------------------------------------------------------ 6 · /ask 那张脸同一个开关


def test_the_ask_face_routes_by_the_same_switch(tmp_path, monkeypatch):
    """/ask 借的那条管线跟着同一枚开关走 —— 只切一张脸就是计划书 §9.1 立过的那半切态。

    只换 PG 连接、旧引擎句柄、embedding、重排器与关键词腿；改写走 fast 档。
    为的是这一格只量一件事：语义腿到没到 PG，而端点那条链上没有人偷偷回读旧引擎。
    """
    from app.agents.contracts import Principal

    _quiet_the_switch(monkeypatch)
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    double = _PgDouble()
    _arm_pg(monkeypatch, double)
    handle = _Handle()
    instance = _real_retriever(tmp_path, monkeypatch, handle)

    semantic = pipeline_module.SemanticSearcher.__new__(pipeline_module.SemanticSearcher)
    semantic.retriever = instance

    pipeline = pipeline_module.RetrievalPipeline.__new__(pipeline_module.RetrievalPipeline)
    pipeline.semantic = semantic
    pipeline.bm25 = _NoKeywordRecall()
    pipeline.rewriter = SimpleNamespace(rewrite=lambda query: {})
    pipeline.reranker = _CapturingReranker()
    principal = Principal.from_user(_user("staff-a", "dept-a"))

    docs, _rewrites = pipeline.search_for_principal("住宿费标准", principal, top_k=5,
                                                   tier="fast")

    assert len(double.search_statements()) >= 1, "/ask 那条腿没问到 PG：两张脸只切了一张"
    assert handle.queries == [], "/ask 这条链上旧引擎那台 ANN 仍被问着"
    assert [doc["content"] for doc in docs] == [PG_TEXT]
    assert rt.search_shape_diagnostics()["answered_by"].get(
        rt.RETRIEVAL_SERVER_PGVECTOR) >= 1
