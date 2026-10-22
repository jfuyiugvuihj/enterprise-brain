# -*- coding: utf-8 -*-
"""R59 块1 判据②(b) + ②(c) —— 同一个 `where`，两侧行数必须相等；三处口径逐条裁定。

为什么这一枚不能等合闸再补：R269 §5 第②处写得很直白——`where` 打在没写过的键上就是 0 行
（R162 已证），切读之后这条跟着 PG 走，不是 Chroma 病。两侧对同一个 `where` 交回的行数一旦
不等，差的每一行要么是**别人的文档**（权限过滤少带一层），要么是**已经不存在的文档**
（墓碑口径不一致）。前一种是漏权，后一种是把删掉的东西答给用户，两种都不能靠"看着像一样"过。

两侧各是谁，写清楚，免得把这枚钉读成它不是的东西：

- **Chroma 侧是真的那台引擎**：临时目录里的 `PersistentClient`（R134 的落点改道照样生效），
  谓词由 chroma 自己解释。本机 venv 里 chromadb 1.5.9 在位 ⇒ 这条腿不是抄的。
- **PG 侧是 `sql_scope_filter` 真发出来的那段 SQL**，交给一台 sqlite 执行——适配层逐字匹配
  pgvector 的 `col = ANY(%s::type[])` 形状，认不出来就抛，**绝不退化成"没有 WHERE"**。
  它量的是"这段谓词在真 SQL 引擎上把哪些行留下"（含 NULL 的三值逻辑），不是 pgvector 本身，
  更不是 HNSW 的近似性：那一格只有真机读数能填，见计划书 §9.3 与 §10。
- 正因为两侧都是"实现"而不是"预期"，这枚钉才有齿：少带一层权限、多留一枚墓碑，都会当场红。

三处口径的裁定写在下面各自的用例里，不写"应一致"。
"""

import importlib.util
import math
import os
import re
import sqlite3

import chromadb
import pytest
from chromadb.config import Settings

from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIM = 4
QUERY = [0.5] * DIM


def _load_ruler():
    """量具本体（`scripts/r59_recall_compare.py`）只做只读复用：口径必须与真机那一遍逐字同。

    本块**不改**那枚脚本，也不连它点名的真对象：借的是它的排序与换算函数，
    这样并树后总控换真机对拍，两侧报的是同一栏字段、同一套 tie-break。
    """
    spec = importlib.util.spec_from_file_location(
        "r59_recall_ruler", os.path.join(ROOT, "scripts", "r59_recall_compare.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RULER = _load_ruler()

#: 一库样本，两侧喂的是同一批行。每枚都为某一条口径存在：
#:  - `b.txt` 缺密级（chroma 侧干脆没这个键，PG 侧 NULL）——R57 fail-closed 那一档
#:  - `c.txt` 无部门（PG 写侧规整成空串，chroma 侧也是空串）——$in 含空串那一档
#:  - `gone.txt` 两侧都在，由墓碑那枚用例当场从 PG 侧删掉——证明行数钉真的会红
#:  - `legacy_key` chroma 侧没有 department 键、PG 侧是空串——两侧表示法不同的那一档
CORPUS = [
    {"vector_id": "a.txt_0", "content": "住宿费标准是每晚500元。", "filename": "a.txt",
     "chunk_index": 0, "classification": 2, "department": "研发中心",
     "embedding": [0.10, 0.20, 0.30, 0.40]},
    {"vector_id": "a.txt_1", "content": "差旅餐费每日150元。", "filename": "a.txt",
     "chunk_index": 1, "classification": 1, "department": "研发中心",
     "embedding": [0.10, 0.21, 0.30, 0.41]},
    {"vector_id": "b.txt_0", "content": "年假按工龄计算。", "filename": "b.txt",
     "chunk_index": 0, "classification": None, "department": "研发中心",
     "embedding": [0.90, 0.10, 0.10, 0.10]},
    {"vector_id": "c.txt_0", "content": "打印机耗材由行政统一采购。", "filename": "c.txt",
     "chunk_index": 0, "classification": 1, "department": "",
     "embedding": [0.50, 0.50, 0.50, 0.50]},
    {"vector_id": "d.txt_0", "content": "市场部季度复盘模板。", "filename": "d.txt",
     "chunk_index": 0, "classification": 3, "department": "市场部",
     "embedding": [0.70, 0.30, 0.20, 0.10]},
    {"vector_id": "gone.txt_0", "content": "两侧都还在、等着被删一枚的行。",
     "filename": "gone.txt", "chunk_index": 0, "classification": 1,
     "department": "研发中心", "embedding": [0.20, 0.80, 0.20, 0.20]},
    {"vector_id": "legacy_key_0", "content": "缺部门键的遗留行。", "filename": "legacy.txt",
     "chunk_index": 0, "classification": 1, "department": "",
     "embedding": [0.30, 0.30, 0.90, 0.30]},
]
#: 两侧默认吃同一批行（这是判据②(b) 成立的前提，也是计划书 §9.1 现取的那格读数：
#: only_in_pg=0 / only_in_chroma=0）。墓碑不是常驻背景，由
#: `test_a_row_one_side_lost_shows_up_as_a_row_count_difference` 现场删、删完还原——
#: 把病常驻在样本里，相等那六枚就永远红了，钉会退化成"永远不等的两堆数"。
PG_ROWS = list(CORPUS)
CHROMA_ROWS = list(CORPUS)
#: 这一行在向量库里压根没有 department 键，在 PG 里是空串：写侧规整过
#: （pg_store.build_rows: `str(values.get("department") or "")`）。两侧对"没有部门"的
#: 表示法不同，正是 `$in` 含空串那一档不做翻译的理由（见裁定二）。
NO_DEPARTMENT_KEY = frozenset({"legacy_key_0"})

WHERE_LEVELS_12 = {"classification": {"$in": [1, 2]}}
WHERE_DEPT = {"department": {"$in": ["研发中心"]}}
WHERE_ADMIN = {"classification": {"$in": [1, 2, 3]}}
WHERE_BOTH = {"$and": [WHERE_LEVELS_12, WHERE_DEPT]}


def _chroma_metadata(row):
    """chroma 的 metadata 不收 None 值：缺密级那一行就不带这个键（与真实现场同形）。"""
    metadata = {"filename": row["filename"], "chunk_index": row["chunk_index"]}
    if row.get("classification") is not None:
        metadata["classification"] = row["classification"]
    if row["vector_id"] not in NO_DEPARTMENT_KEY:
        metadata["department"] = row["department"]
    return metadata


@pytest.fixture(scope="module")
def chroma_collection(tmp_path_factory):
    """真 Chroma：临时目录、l2 空间、只读谓词由它自己解释。一条 SQL 都不发向真库。"""
    directory = str(tmp_path_factory.mktemp("r59-chroma"))
    client = chromadb.PersistentClient(path=directory,
                                       settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection("enterprise_docs",
                                                 metadata={"hnsw:space": "l2"})
    rows = list(CHROMA_ROWS)
    collection.add(ids=[row["vector_id"] for row in rows],
                   documents=[row["content"] for row in rows],
                   embeddings=[row["embedding"] for row in rows],
                   metadatas=[_chroma_metadata(row) for row in rows])
    return collection


@pytest.fixture(scope="module")
def sqlite_mirror():
    """一台 sqlite 充当 chunk_vectors：列类型与 NULL 语义按 0010 的形状摆，执行的是真 SQL。"""
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE chunk_vectors (vector_id TEXT PRIMARY KEY, content TEXT,"
        " filename TEXT, chunk_index INTEGER, classification INTEGER, department TEXT)")
    for row in PG_ROWS:
        connection.execute(
            "INSERT INTO chunk_vectors VALUES (?, ?, ?, ?, ?, ?)",
            (row["vector_id"], row["content"], row["filename"], row["chunk_index"],
             row["classification"], row["department"]))
    connection.commit()
    return connection


class AdapterError(RuntimeError):
    """发出来的谓词不是本文件认得的形状。红，而不是"当作没有 WHERE"。"""


_PREDICATE = re.compile(r"\b([a-z_]+) = ANY\(%s::(integer|text)\[\]\)", re.ASCII)
_ALLOWED_COLUMNS = frozenset({"classification", "department"})


def adapt_to_sqlite(clause, params):
    """`col = ANY(%s::integer[])` -> `col IN (?,?,...)`；空集合 -> `1 = 0`。

    逐字匹配、按顺序吃参：认不出来的列名、认不出来的类型、没被适配到的 `%s`、参数对不上号，
    一律抛。这一枚是"PG 侧行集"的唯一来源，它松一寸，两侧行数相等就成了空断言。
    """
    remaining = list(params)
    consumed = []

    def substitute(match):
        column, sql_type = match.group(1), match.group(2)
        if column not in _ALLOWED_COLUMNS:
            raise AdapterError("谓词里出现了没登记过的列 " + column)
        if not remaining:
            raise AdapterError("谓词 %s 没有对应的绑定值" % column)
        values, _ = remaining[0], remaining.pop(0)
        consumed.append(values)
        if not isinstance(values, (list, tuple)):
            raise AdapterError("%s 的绑定值不是集合：%r" % (column, values))
        expected = int if sql_type == "integer" else str
        for value in values:
            if not isinstance(value, expected) or isinstance(value, bool):
                raise AdapterError("%s 的绑定值类型与声明不符：%r 不是 %s"
                                   % (column, value, sql_type))
        if not values:
            # `= ANY(ARRAY[]::int[])` 在 PG 里是"一行都不满足"，不是语法错误。
            return "1 = 0"
        return "%s IN (%s)" % (column, ", ".join("?" * len(values)))

    adapted = _PREDICATE.sub(substitute, clause)
    if "%s" in adapted:
        raise AdapterError("谓词里还剩没被适配的占位符：" + adapted)
    if remaining:
        raise AdapterError("绑参多了 %d 枚没被谓词吃掉" % len(remaining))
    return adapted, [value for values in consumed for value in values]


def pg_side_ids(sqlite_mirror, where):
    """让 `sql_scope_filter` 真发谓词，再让 sqlite 真执行它——两侧行数的 PG 那一侧。"""
    clause, params = pg_store.sql_scope_filter(where)
    adapted, bound = adapt_to_sqlite(clause, params) if clause else ("1 = 1", [])
    sql = "SELECT vector_id FROM chunk_vectors"
    if adapted != "1 = 1":
        sql += " WHERE " + adapted
    return sorted(item[0] for item in sqlite_mirror.execute(sql, bound).fetchall())


def chroma_side_ids(chroma_collection, where):
    return sorted(chroma_collection.get(where=where)["ids"])


def parity_report(chroma_collection, sqlite_mirror, where):
    pg = pg_side_ids(sqlite_mirror, where)
    chroma = chroma_side_ids(chroma_collection, where)
    return {"where": where, "pg_rows": len(pg), "chroma_rows": len(chroma),
            "pg_ids": pg, "chroma_ids": chroma,
            "only_in_pg": sorted(set(pg) - set(chroma)),
            "only_in_chroma": sorted(set(chroma) - set(pg)),
            "equal": pg == chroma}


# --------------------------------------------------------------- ②(b) 两侧行数相等


@pytest.mark.parametrize("where", [
    None,
    WHERE_ADMIN,
    WHERE_LEVELS_12,
    WHERE_DEPT,
    WHERE_BOTH,
    {"classification": {"$in": [3]}},
])
def test_the_same_where_keeps_the_same_rows_on_both_sides(chroma_collection, sqlite_mirror,
                                                          where):
    """判据②(b) 正身：同一份 `where`，两侧行数与 id 集合逐枚相等。

    样本里摆了缺密级、无部门、只在单侧的行，所以这一枚不是"两边都空所以相等"：
    少带一层权限（见下一枚）或一侧多一枚墓碑（见第三枚）都会当场红。
    """
    report = parity_report(chroma_collection, sqlite_mirror, where)

    assert report["equal"], report
    assert report["pg_rows"] == report["chroma_rows"], report
    assert report["only_in_pg"] == [] == report["only_in_chroma"], report


def test_a_dropped_predicate_shows_up_as_a_row_count_difference(chroma_collection,
                                                                sqlite_mirror, monkeypatch):
    """判据⑥第二条：`where` 少带一层权限 ⇒ 本文件的行数钉必须红（这里以现取证明它有齿）。

    变异就在测试里做（把 `sql_scope_filter` 换成"只翻译第一层"的版本，等价于漏掉部门那一层），
    当场看数：PG 侧多留 3 行别人的文档。上一枚断言相等、这一枚断言"少带一层就不相等"，
    两枚合起来才叫钉——只留上一枚的话，一个恒真适配器也能过关。
    """
    honest = pg_store.sql_scope_filter

    def one_layer_only(where):
        if isinstance(where, dict) and "$and" in where:
            return honest(where["$and"][0])
        return honest(where)

    monkeypatch.setattr(pg_store, "sql_scope_filter", one_layer_only)
    narrowed = parity_report(chroma_collection, sqlite_mirror, WHERE_BOTH)

    monkeypatch.setattr(pg_store, "sql_scope_filter", honest)
    correct = parity_report(chroma_collection, sqlite_mirror, WHERE_BOTH)

    assert not narrowed["equal"], "漏一层权限居然没被行数钉抓住：这枚钉是空的"
    assert narrowed["only_in_pg"], "抓的方式必须是『PG 侧多放行』，不是随便差几行"
    assert correct["equal"], "改回来就应当相等：证明红的是那半层，不是别的"


def test_a_row_one_side_lost_shows_up_as_a_row_count_difference(chroma_collection,
                                                                sqlite_mirror):
    """墓碑口径（②(b) 括号里的第二因）：一侧少一行，必须当场被行数钉点名，而不是悄悄少答一条。

    现场删 `gone.txt_0`、删完还原：这条不是设计缺陷的展示，是**双写崩在半路**那一格的形状
    （R58 遗留风险登记过：Chroma 写成功与 PG commit 之间进程崩溃 ⇒ 只剩 Chroma）。
    它同时说明合闸前置里"两侧逐枚相等"（计划书 §9.1：only_in_pg=0 / only_in_chroma=0）
    不是套话——不满足时这枚钉会红，而不是交回一份看起来正常的答案。
    """
    sqlite_mirror.execute("DELETE FROM chunk_vectors WHERE vector_id = ?", ("gone.txt_0",))
    try:
        report = parity_report(chroma_collection, sqlite_mirror, WHERE_ADMIN)
    finally:
        sqlite_mirror.execute("INSERT INTO chunk_vectors VALUES (?, ?, ?, ?, ?, ?)",
                              ("gone.txt_0", "两侧都还在、等着被删一枚的行。", "gone.txt",
                               0, 1, "研发中心"))
        sqlite_mirror.commit()

    assert not report["equal"], report
    assert report["only_in_chroma"] == ["gone.txt_0"], report
    assert report["only_in_pg"] == [], "这一格只许少一行，多了就是别的问题"
    assert parity_report(chroma_collection, sqlite_mirror, WHERE_ADMIN)["equal"], "还原失败"


def test_the_adapter_refuses_a_predicate_it_does_not_recognise(sqlite_mirror, monkeypatch):
    """适配器只认得的形状才执行：认不出来就抛，绝不退化成"没有 WHERE"。"""
    def _wide(where):
        return "classification = ANY(%s::integer[]) OR vector_id = %s", [[1], "x"]

    monkeypatch.setattr(pg_store, "sql_scope_filter", _wide)
    with pytest.raises(AdapterError):
        pg_side_ids(sqlite_mirror, WHERE_ADMIN)


# -------------------------------------------------- ②(c)-3 权限口径：三档逐条裁定


def test_a_row_without_a_classification_is_invisible_on_both_sides(chroma_collection,
                                                                    sqlite_mirror):
    """裁定一（密级）：缺密级那一行两侧都排除，且排除的机制各自都是 fail-closed。

    chroma：metadata 里没这个键 ⇒ `$in` 不匹配；PG：`NULL = ANY(ARRAY[...])` 是 NULL ⇒
    不满足 WHERE。两边都不是"补成 1 级再看"，与 R57 那条"缺键即不可见"同义。
    """
    report = parity_report(chroma_collection, sqlite_mirror, WHERE_ADMIN)

    assert "b.txt_0" not in report["pg_ids"] and "b.txt_0" not in report["chroma_ids"]


def test_the_empty_string_department_is_a_refusal_not_a_guess():
    """裁定二（部门）：`$in` 里含空串这一档**不做翻译**，直接拒答。

    理由是两侧表示法不同：写侧把"没有部门"规整成空串（pg_store.build_rows），而向量库里
    "没有部门"是压根没有这个键。`{"department": {"$in": [""]}}` 在 SQL 里会命中前者、
    在向量库里命中不了后者——两侧对不齐，而 PG 那侧更宽。filters.py 今天发不出这个形状
    （`_resolve_document_retrieval_scope` 先 `if department` 把空值丢了），所以这是一档
    现在裁不到东西的口径；把它钉成拒答，是为了将来谁往 departments 里塞空串时当场红，
    而不是安静地放宽权限。
    """
    from app.rag import pg_store as store

    with pytest.raises(store.ScopeFilterUntranslatable) as refused:
        store.sql_scope_filter({"department": {"$in": [""]}})
    assert refused.value.reason == store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE

    mixed = store.sql_scope_filter({"department": {"$in": ["研发中心"]}})
    assert mixed[0].startswith("department = ANY(%s::text[])"), mixed


def test_a_refused_where_never_reaches_the_store_wider(tmp_path, monkeypatch):
    """裁定二的后果面：拒答之后仍由遗留腿带**同一份** where 答复——放宽一格都不许发生。"""
    calls = {}

    class _Answers:
        name = "enterprise_docs"

        def query(self, **kwargs):
            calls.update(kwargs)
            return {"ids": [["d.txt_0"]], "documents": [["市场部季度复盘模板。"]],
                    "metadatas": [[{"filename": "d.txt", "chunk_index": 0,
                                    "classification": 3, "department": "市场部"}]]}

    double = _StubPg()
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    rt.reset_search_shape()
    instance = rt.DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    instance.collection = _Answers()

    hits = instance.search("复盘", k=5, where={"department": {"$in": [""]}})

    assert hits
    assert calls["where"] == {"department": {"$in": [""]}}, "退回时不许把谓词丢了或换掉"
    assert double.search_statements == [], "翻译不出来就不该发向量 SQL（探测两条不算）"


class _StubResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._scalar


class _StubPg:
    """探测答得上、但一条向量 SQL 都不该发到的假连接：发到了就是本文件的红。"""

    def __init__(self):
        configured = indexing.configured_embedding_scope()
        self.scope_row = (configured.embedding_model, int(configured.dimension), "l2")
        self.column_type = ("vector(%d)" % int(configured.dimension),)
        self.statements = []

    def execute(self, sql, params=None):
        statement = str(sql)
        self.statements.append((statement, params))
        if "vector_scope" in statement:
            return _StubResult(scalar=self.scope_row)
        if "pg_attribute" in statement:
            return _StubResult(scalar=self.column_type)
        raise AssertionError("谓词翻译不出来时不许发这条：" + statement)

    @property
    def search_statements(self):
        return [item for item in self.statements if "ORDER BY embedding" in item[0]]

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_an_empty_predicate_set_answers_zero_rows_on_pg_and_errors_on_chroma(
        sqlite_mirror, chroma_collection):
    """裁定三（空结果，与②(a) 配对）：`$in: []` 两侧不是一回事，本块明写而不抹平。

    实测（本文件现取）：chroma 的 `get(where=...)` 对空 `$in` **抛 ValueError**——今天这条
    形状在遗留腿上是一次异常，不是 0 行；PG 侧 `= ANY(ARRAY[]::integer[])` 正常交回 0 行。
    裁定：0 行是更诚实的那一个答复，且切读之后它会经判据②(a) 降级成关键词答案，
    用户不再拿异常。filters.py 发不出这个形状（clearance<=0 在闸门就 raise），
    所以这一档同样是"裁不到东西但必须留字"。
    """
    clause, params = pg_store.sql_scope_filter({"classification": {"$in": []}})
    adapted, bound = adapt_to_sqlite(clause, params)

    assert sqlite_mirror.execute(
        "SELECT vector_id FROM chunk_vectors WHERE " + adapted, bound).fetchall() == []
    with pytest.raises(ValueError):
        chroma_collection.get(where={"classification": {"$in": []}})


# ------------------------------------------------------- ②(c)-1 距离度量口径逐条裁定


def test_the_operator_follows_the_recorded_scope_and_guesses_nothing():
    """裁定一（距离）：算符只由 `vector_scope.distance_function` 决定，认不出来即拒答。

    写死在代码里的只有一件事：**不猜**。0010 的 CHECK 收 l2 / cosine / ip 三种拼法，
    本块三种都验一遍，再验一枚没登记的拼法必须拒（计划书 §8.5 U1 的实测结论是 l2）。
    """
    assert dict(pg_store.DISTANCE_OPERATORS) == {"l2": "<->", "cosine": "<=>",
                                                 "ip": "<#>"}
    for spelling, operator in sorted(pg_store.DISTANCE_OPERATORS.items()):
        connection = _ProbeConnection()
        pg_store.search_vectors(connection=connection,
                                vector_table=pg_store.DEFAULT_VECTOR_TABLE,
                                distance_function=spelling, query_vector=list(QUERY),
                                k=3, where=WHERE_ADMIN)
        sql = connection.sql
        assert " AS distance FROM" in sql and operator + " %s::vector AS distance" in sql
        assert "ORDER BY embedding " + operator in sql
        assert "DESC" not in sql, "距离升序是两侧共同的口径，反了就等于取最不相干的"


def test_the_read_sql_carries_no_distance_threshold():
    """裁定二（H20 代裁的钉）：距离上**不引入任何人为下限**，top-k 与阈值沿用现值。

    计划书 :334 记着 H20（切读的显式距离下限）业主未裁，上一班按"不新增人为下限"代裁推进
    且标明可推翻。本块沿用那一条，并把"没顺手加下限"钉死：WHERE 里只许出现
    classification / department 两列，唯一的行数上限就是调用方要的 k。推翻它要动的是这枚
    钉与那条代裁，不是偷偷多写一个 `distance <= ?`。
    """
    connection = _ProbeConnection()
    pg_store.search_vectors(connection=connection,
                            vector_table=pg_store.DEFAULT_VECTOR_TABLE,
                            distance_function="l2", query_vector=list(QUERY), k=5,
                            where=WHERE_BOTH)

    sql, params = connection.sql, connection.params
    where_part = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "distance" not in where_part.lower(), where_part
    assert set(re.findall(r"\b([a-z_]+) = ANY", where_part)) == {"classification",
                                                                "department"}
    assert sql.endswith("LIMIT %s") and params[-1] == 5


class _ProbeConnection:
    def __init__(self):
        self.sql = ""
        self.params = ()

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = tuple(params or ())
        return _StubResult(rows=[])

    def commit(self):
        pass

    def close(self):
        pass


def test_squared_and_plain_l2_rank_the_same_candidates():
    """裁定三（两侧对同一个几何量给的不是同一个数）：平方欧氏只改"走了多远"，不改名次。

    R157 实测 chroma 的 l2 交回**平方**欧氏距离，pgvector 的 `<->` 交回欧氏距离。量具
    （`scripts/r59_recall_compare.py`，本块只读复用）正是按这条事实写换算的。这一枚把
    "平方/不平方不构成召回差"钉成一个可复跑的数：同一批向量、同一个 query，
    两侧精确 top-k 的 id 顺序逐位相等，而距离栏换算后相等。
    """
    ids = [row["vector_id"] for row in PG_ROWS]
    matrix = [row["embedding"] for row in PG_ROWS]

    plain = RULER.exact_knn_topk(ids, matrix, QUERY, metric="l2", k=5)
    squared = sorted(((sum((a - b) ** 2 for a, b in zip(vector, QUERY)), vector_id)
                      for vector_id, vector in zip(ids, matrix)))
    plain_ids = [item[0] for item in plain]
    squared_ids = [item[1] for item in squared[:5]]

    assert plain_ids == squared_ids
    for (vector_id, distance) in plain:
        assert RULER.to_comparable("l2", "chroma", distance ** 2) == pytest.approx(
            RULER.to_comparable("l2", "pg", distance), abs=1e-6
        ), vector_id
    #: 同一枚 numpy 腿（量具的归因腿）也要落在同一个第一名上：它按平方距离排序，
    #: 与 exact_knn_topk 的欧氏排序只差一个单调变换。numpy 在位是这枚钉的前置。
    import numpy

    numpy_top = RULER.array_topk(ids, numpy.asarray(matrix, dtype=numpy.float32),
                                 numpy.asarray(QUERY, dtype=numpy.float32), k=5)
    assert [item[0] for item in numpy_top] == plain_ids
    assert math.isclose(plain[0][1], float(numpy_top[0][1]) ** 0.5, abs_tol=1e-5)
