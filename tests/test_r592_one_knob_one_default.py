# -*- coding: utf-8 -*-
"""R59 块2 判据①②④ —— 一把开关、一个出厂默认、两本分得开的账。

本单的范围是「把 chat.py 的检索入口接上块1 那条腿」。接线最容易留下的三种后遗症，
一件一枚钉：

1. 自造第二把开关（判据②）。块1 用的那把是 app/rag/indexing.py 的 INDEX_BACKEND ——
   现取凭据：indexing.py:57 的 INDEX_BACKEND_ENV、:2040 的 read_backend()、:2087 的
   pgvector_reads_enabled()，而 retriever._pgvector_hits 与 pg_store.switched_corpus 读的
   正是 pgvector_reads_enabled()。本文件把「chat.py 里不许长出第二处裁决点」钉成源码棘轮：
   端点层既不读那枚常量的字面量，也不许新读一枚名字里带 BACKEND / VECTOR_READ / PGVECTOR
   的环境变量。两把开关最坏的形状不是多一行代码，而是两台机器上各拨一把，然后诊断里
   看着像切完了 —— 计划书 §9.1 给热集让路立的正是这条理由。
2. 默认值被顺手翻掉（判据①）。三格一起判：出厂常量本身、不给 env 时 read_backend() 的答复、
   以及**调用点**上真服务一次问答的那张脸（只看签名不看调用点是本仓抓过的老错）。
   反证钉：把 indexing.INDEX_BACKEND_DEFAULT 改成 pgvector ⇒ 本文件与
   test_r592_chat_entry_routes_by_the_switch.py 的默认态那格一起红。
3. 两本账分不开（判据④）。同一个进程里先后走 PG 腿与遗留腿各一问，answered_by 必须两枚
   键都在、各记 1 次；vector_read_diagnostics 那边 attempts/answered/bypass 必须只数 PG
   那一腿。"切了读"与"没切"在读数上长同一个样，就等于没有回滚凭据。

全程只读源码与内存计数，不连库、不打模型。
"""

import ast
import pathlib

import pytest

from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever

REPO = pathlib.Path(__file__).resolve().parents[1]
CHAT_PY = REPO / "app" / "api" / "v1" / "chat.py"

#: 块1 那把开关的全部合法拼法。出现任何一枚别的名字就是第二把。
THE_ONE_KNOB = "INDEX_BACKEND"
KNOB_SHAPED = ("BACKEND", "VECTOR_READ", "PGVECTOR", "PG_READ", "READ_SOURCE")

#: 端点层不许直接问退役引擎的那几枚调用名（拿句柄＝绕过了那条腿）。
ENGINE_HANDLE_CALLS = frozenset({
    "PersistentClient", "EphemeralClient", "get_collection", "get_or_create_collection",
    "create_collection",
})


def _source(path: pathlib.Path) -> str:
    assert path.exists(), str(path) + " 不在了"
    return path.read_text(encoding="utf-8")


def _env_names_read_by(source: str) -> list:
    """AST 抠一枚文件里所有 os.getenv("X") / os.environ["X"] 的字面量名。

    抠不到就抛：回空集合会把"没有第二把开关"变成恒真。
    """
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            dotted = getattr(func, "attr", None) or getattr(func, "id", None)
            # 三种拼法都要认：os.getenv("X")、getenv("X")、os.environ.get("X")。
            # 只认第一种的话，这枚棘轮能被最直白的那一种写法绕过去。
            via_environ_get = (dotted == "get"
                               and getattr(getattr(func, "value", None), "attr", "")
                               == "environ")
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
    if not names:
        raise AssertionError("一枚文件里一枚环境变量都没读到，判器本身坏了")
    return names


def _calls_named(source: str, wanted) -> list:
    """AST 扫这枚文件里所有被调用的属性名/裸名，命中 wanted 的就记下来。"""
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in wanted:
                offenders.append("%s:%s" % (name, node.lineno))
    return offenders


# ------------------------------------------------- 1 · 一把开关，端点层不许再裁一次


def test_chat_py_never_grows_a_second_read_switch():
    """判据②：chat.py 里不许出现第二枚读后端开关，也不许自读块1 那枚常量。

    唯一裁决点是 indexing.read_backend()。端点层再读一次常量、或新起一枚环境变量，
    就会出现"两台机器各拨一把"那种读数永远对不齐的形状。
    """
    source = _source(CHAT_PY)
    names = _env_names_read_by(source)

    second = [name for name in names
              if name != THE_ONE_KNOB and any(shape in name for shape in KNOB_SHAPED)]
    assert second == [], "chat.py 里长出了第二把读后端开关：" + repr(second)
    assert THE_ONE_KNOB not in names, (
        "端点层自己读了 INDEX_BACKEND：裁决点从 indexing.read_backend() 挪走了")


def test_the_retrieval_entry_asks_the_retriever_not_the_engine():
    """判据②第二半：chat.py 那条检索入口只能问检索器，不能自己拿向量库句柄。

    块1 那条腿长在 DocumentRetriever.search 里面；端点一旦自己拿句柄问引擎，切读对它
    就永远不生效 —— 而那正是"接线接了个假动作"的形状。
    """
    offenders = _calls_named(_source(CHAT_PY), ENGINE_HANDLE_CALLS)
    assert offenders == [], "端点层直接向向量库要了句柄：" + repr(offenders)


# ----------------------------------------------------------- 2 · 出厂默认仍是 Chroma


def test_the_shipped_default_is_still_the_legacy_engine():
    """判据①第一格：常量本身。计划书 :334 那句「逐题对拍读数出来之前不许翻默认」。"""
    assert indexing.INDEX_BACKEND_DEFAULT == "chroma"
    assert indexing.PGVECTOR_BACKEND == "pgvector"


def test_no_env_leaves_the_reader_on_the_legacy_engine(monkeypatch):
    """判据①第二格：不给 env，read_backend()/pgvector_reads_enabled() 的答复。

    这里连"宿主 shell 里残留一枚 INDEX_BACKEND"都要判掉：R231 的实测记着那一格 ——
    机器上有 pgvector 时，默认态钉会当场红，所以本用例显式删 env 再读。
    """
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)

    assert indexing.read_backend() == indexing.INDEX_BACKEND_DEFAULT == "chroma"
    assert indexing.pgvector_reads_enabled() is False
    assert pg_store.switched_corpus() is None
    assert pg_store.vector_corpus_diagnostics()["source"] == (
        pg_store.CORPUS_SOURCE_NOT_SWITCHED)


# ------------------------------------------------------------ 3 · 两本账分得开


def _row(vector_id, content, filename, department):
    """按 pg_store._READ_COLUMNS 加 distance 摆一行：(id, 正文, 文件名, 序号, 密级, 部门, 距离)。"""
    return (vector_id, content, filename, 0, 1, department, 1.0)


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


class _PgDouble:
    def __init__(self, rows=()):
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
    name = "enterprise_docs"

    LEGACY_TEXT = "遗留引擎那一份正文。"

    def __init__(self):
        self.queries = []
        self.gets = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {"ids": [["legacy.txt_0"]], "documents": [[self.LEGACY_TEXT]],
                "metadatas": [[{"filename": "legacy.txt", "chunk_index": 0,
                               "classification": 1, "department": "研发中心"}]]}

    def get(self, where=None):
        self.gets.append(where)
        return {"ids": [], "documents": [], "metadatas": []}


def test_the_two_legs_are_told_apart_in_one_process(tmp_path, monkeypatch):
    """判据④：同一进程里先后各走一条腿，两本账必须指名是谁答的。

    PG 腿那一问：answered_by 记 pgvector、vector_read_diagnostics 的 attempts 与 answered
    各 +1；遗留腿那一问：answered_by 记 chroma，而 vector_read_diagnostics 一个字都不许动
    —— 那本账只管 PG 那一腿，把回落也记成"PG 答过"就是把回滚凭据记成了切读成绩。
    """
    pg_text = "PG 镜像那一份正文。"
    double = _PgDouble(rows=[_row("pg.txt_0", pg_text, "pg.txt", "研发中心")])
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    pg_store.reset_vector_read_diagnostics()
    rt.reset_search_shape()

    handle = _Handle()
    instance = DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: [0.5] * 4)
    instance.collection = handle
    where = {"$and": [{"classification": {"$in": [1]}}, {"department": {"$in": ["研发中心"]}}]}

    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    pg_hits = instance.search("差旅标准", k=5, where=where)

    assert [hit["content"] for hit in pg_hits] == [pg_text]
    pg_ledger = pg_store.vector_read_diagnostics()
    assert (pg_ledger["attempts"], pg_ledger["answered"]) == (1, 1)
    assert pg_ledger["last_bypass"] is None

    baseline = pg_store.vector_read_diagnostics()
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)
    legacy_hits = instance.search("差旅标准", k=5, where=where)

    assert [hit["content"] for hit in legacy_hits] == [handle.LEGACY_TEXT]
    assert len(handle.queries) == 1, "遗留那一问必须真的问到那台 ANN"
    assert len(double.search_statements()) == 1, "拨回去以后又发了一条排名 SQL"
    after = pg_store.vector_read_diagnostics()
    same_pg_ledger = ((after["attempts"], after["answered"])
                      == (baseline["attempts"], baseline["answered"]))
    assert same_pg_ledger, "遗留腿被记进了 PG 那本账：两本账混成了一本"
    legs = rt.search_shape_diagnostics()["answered_by"]
    assert legs.get(rt.RETRIEVAL_SERVER_PGVECTOR) == 1
    assert legs.get(rt.RETRIEVAL_SERVER_CHROMA) == 1
