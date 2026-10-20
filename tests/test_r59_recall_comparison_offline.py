# -*- coding: utf-8 -*-
"""R59 块1 判据③ —— 逐题召回对比：一副**离线可跑**的量具，口径与 §10 那份真机读数逐字同。

为什么要另交一副离线件：真机那一遍（`scripts/r59_recall_compare.py` 在 backend 容器里跑
135 题）要独占 Ollama 与 Chroma 目录，是跑分窗的活，不是本块的活。但"切过去之后逐题召回
不退化"这句话不能等到合闸那天才有工具可以跑，所以这里交的是：

1. **同一套字段与同一个算法**——比较函数直接复用 `scripts/r59_recall_compare.py`
   （`compare_question` / `summarize` / `exact_knn_topk` / `to_comparable`），本块一个字不改
   那枚脚本，也不复制一份平行实现；并树后总控换真机跑，报的是同一栏字段、同一套 tie-break。
2. **同一批题号**——题面取自计划书 §10 那份已并树的只读原件
   （`docs/testing/r59b-recall-comparison-2026-09-24.json`），并按 §10 的口径把"交回 0 行的
   题"去重成 21 枚清单钉死。清单对不上就是口径漂了，本块不许自造一批题。
3. **两条腿都是真跑的读**：Chroma 侧是临时目录里的真 `PersistentClient`（不是抄的应答），
   PG 侧是 `pg_store.read_topk` 真发出来的那条 SQL，交给一台 sqlite 执行（向量距离由注册的
   确定性函数算）。零真库、零 Ollama、零服务。

它证明不了的两件事也写明白：HNSW 的近似性（sqlite 那腿是精确扫，所以
`index_vs_exact_same_set` 在离线件里恒真是**结构使然**，不是读数），以及真实 embedding 的
语义质量（离线题向量由题面 sha256 导出，钉的是管道与口径，不是答案好不好）。这两格只有
真机能填，见计划书 §9.3 与 §10。
"""

import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3

import chromadb
import pytest
from chromadb.config import Settings

from app.rag import indexing
from app.rag import pg_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVED = os.path.join(ROOT, "docs", "testing",
                        "r59b-recall-comparison-2026-09-24.json")
PLAN_DOC = os.path.join(ROOT, "docs", "handoff", "2026-09-17-pgvector-adoption-plan.md")
DIM = 16

#: 计划书 §10 那条题号清单（按 id 去重后 21 枚）。抄在这里不是装饰：它把"离线件与真机读数
#: 说的是同一批题"变成一枚可红的断言，将来谁换评测集或改去重口径，这枚先红。
SECTION_TEN_ZERO_ROW_IDS = (
    "metric-04", "metric-05", "metric-10", "metric-11", "metric-13", "metric-18",
    "metric-19", "scope-01", "scope-03", "scope-05", "scope-06", "insight-02",
    "insight-06", "tool-01", "tool-04", "doc-09", "doc-13", "chart-04", "data-08",
    "approval-06", "report-12",
)


def _load_ruler():
    spec = importlib.util.spec_from_file_location(
        "r59_recall_ruler", os.path.join(ROOT, "scripts", "r59_recall_compare.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RULER = _load_ruler()


# ------------------------------------------------- 与 §10 对表：口径先钉死，再谈跑数


def _archived_reading():
    return json.load(open(ARCHIVED, encoding="utf-8"))


def test_the_archived_reading_still_says_what_section_ten_counted():
    """§10 是总控亲算的读数，本块的对比口径必须与它同：这几枚数抄进测试，改了就红。

    只读原件、不复算真库：这里对的是"那份产物长什么样"，不是"今天库里有多少枚向量"。
    """
    reading = _archived_reading()
    questions = reading["questions"]
    summary = reading["summary"]

    assert reading["meta"]["k"] == 5
    assert summary["questions"] == 135
    assert summary["chroma_zero_rows"] == 24
    assert summary["pg_zero_rows"] == 0
    assert summary["pg_index_vs_exact_same_set"] == 135
    assert summary["mean_kendall_tau"] == 1.0
    assert summary["exact_sides_same_set"] == 135
    #: 分母钉（R59c 复核，看板 `d13201f`）：那 135 行里有 30 枚 id 被数了两遍，按题号·题面
    #: 去重都是 105 枚。任何按 135 算的百分比都得按 105 重读——本块只借 §10 的**题号清单**
    #: （交回 0 行的 24 行按 id 去重 = 21 枚），不借 135 当分母。
    assert len({item["id"] for item in questions}) == 105
    assert len({item["question"] for item in questions}) == 105


def test_the_deduped_zero_row_question_list_matches_the_plan_document():
    """交回 0 行的题按 id 去重 = 21 枚，且与计划书 §10 写下的那份清单逐枚相等。

    这条是判据③"同一批题号"的可执行形式：清单来自只读原件现取，字面值来自 §10。
    任何一边漂了（评测集被改、去重口径被换、文档被重写），这里当场对不上。
    """
    questions = _archived_reading()["questions"]
    zero_rows = [item for item in questions if item["chroma_rows"] == 0]
    deduped = sorted({item["id"] for item in zero_rows})

    assert len(zero_rows) == 24, "0 行按行是 24 行（含重复题），这一格不许与 21 混用"
    assert deduped == sorted(SECTION_TEN_ZERO_ROW_IDS)
    plan = open(PLAN_DOC, encoding="utf-8").read()
    for question_id in deduped:
        assert question_id in plan, "§10 的题号清单里找不到这一枚：" + question_id
    #: 每一题的精确腿都有货：0 行出在它的 ANN，不在数据（R211 裁定的题号级凭据）。
    assert all(item["chroma_exact_ids"] for item in zero_rows)


def test_the_questions_we_compare_are_the_ones_the_plan_names():
    """离线件吃的题面 = §10 那 21 枚 + 一批"两侧本来就一致"的对照题，一起进同一次跑。"""
    questions = _archived_reading()["questions"]
    wanted = set(SECTION_TEN_ZERO_ROW_IDS)
    picked = {item["id"]: item["question"] for item in questions if item["id"] in wanted}

    assert set(picked) == wanted
    assert all(str(text).strip() for text in picked.values())


# ------------------------------------------------ 离线件的两条腿：真 chroma + 真 SQL


def _vector_for(text):
    """题面 -> 确定性向量。合成向量只量管道与口径，不声称有语义（文件头写明了）。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [(digest[index % len(digest)] / 127.5) - 1.0 for index in range(DIM)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


#: 语料：三对近重复（chunk_overlap=50 造出来的那个形状）+ 正常行。近重复是给"候选预算被吃光"
#: 这一族准备的形状——离线件的正常腿答得出，被饿的那条腿答不出，才有正控制可看。
CORPUS = (
    ("差旅费报销细则_2026版.txt_0", "住宿费标准是每晚500元，超标需审批。", "研发中心", 2),
    ("差旅费报销细则_2026版.txt_1", "住宿费标准是每晚500元超标需审批。", "研发中心", 2),
    ("差旅费报销细则_2026版.txt_2", "住宿费 标准 是 每晚 500 元，超标 需 审批", "研发中心", 2),
    ("年假管理办法.txt_0", "年假按工龄计算，满一年五天。", "研发中心", 1),
    ("年假管理办法.txt_1", "年假按工龄计算满一年五天。", "市场部", 1),
    ("耗材采购制度.txt_0", "打印机耗材由行政统一采购。", "", 1),
    ("季度复盘模板.txt_0", "市场部季度复盘模板与要点。", "市场部", 3),
    ("等保要求.txt_0", "等保三级要求日志留存一百八十天。", "研发中心", 3),
    ("回款确认.txt_0", "回款以银行到账确认，未到账不计入。", "财务部", 2),
    ("年会流程.txt_0", "公司年会流程与座位安排。", "", 1),
    ("深度学习入门_436.txt_0", "反向传播的链式求导法则。", "研发中心", 1),
    ("深度学习入门_510.txt_0", "卷积神经网络感受野。", "研发中心", 1),
)
VECTOR_IDS = [row[0] for row in CORPUS]


def _corpus_vectors():
    """语料向量：同一枚 sha 派生，近重复那几行只在末尾一位上分开——距离近到抢同一批槽位。"""
    vectors = []
    for position, (vector_id, body, _dept, _level) in enumerate(CORPUS):
        base = _vector_for(body)
        if position % 3 == 1:
            base[-1] += 0.01
        elif position % 3 == 2:
            base[-1] -= 0.01
        vectors.append(base)
    return dict(zip(VECTOR_IDS, vectors))


CORPUS_VECTORS = _corpus_vectors()


class _SqlitePg:
    """执行 `search_vectors` 真发出来的那条 SQL：逐字匹配形状，认不出来即抛。

    三件事按 pgvector 的形状做：`<->` / `<=>` / `<#>` 各对应一枚注册函数；`%s::vector`
    走文本形式（与写侧同一个编码路径）；`= ANY(%s::integer[])` 展开成 `IN (...)`。
    距离与 id 一起做排序键，是为了让并列可复现（真 pgvector 遇同距不保证稳定序，量具
    `exact_knn_topk` 的注释写的正是这一格）。
    """

    OPERATORS = {"<->": "l2_distance", "<=>": "cosine_distance",
                 "<#>": "negative_inner_product"}

    def __init__(self, rows, *, dimension=DIM, distance_function="l2"):
        #: 探测两条语句的答卷在这里摆好：vector_scope 那一行与 embedding 列的实际类型。
        #: 二者必须与运行时的 EMBEDDING_DIMENSION 同一口径，否则 vector_mirror 拒开——
        #: 那不是本件的失败，那是 R22 的闸门在正常工作。
        self.dimension = int(dimension)
        self.scope_row = (indexing.DEFAULT_EMBEDDING_MODEL, self.dimension,
                          distance_function)
        self.column_type = ("vector(%d)" % self.dimension,)
        self.connection = sqlite3.connect(":memory:")
        for name, formula in (("l2_distance", _l2), ("cosine_distance", _cosine),
                              ("negative_inner_product", _negative_inner_product)):
            self.connection.create_function(
                name, 2,
                lambda left, right, _f=formula: _f(_parse(left), _parse(right)),
                deterministic=True)
        self.connection.execute(
            "CREATE TABLE chunk_vectors (vector_id TEXT PRIMARY KEY, content TEXT,"
            " filename TEXT, chunk_index INTEGER, classification INTEGER, department TEXT,"
            " embedding TEXT)")
        for row in rows:
            self.connection.execute("INSERT INTO chunk_vectors VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (row["vector_id"], row["content"], row["filename"],
                                     row["chunk_index"], row["classification"],
                                     row["department"], row["embedding"]))
        self.connection.commit()
        self.statements = []

    def execute(self, sql, params=None):
        statement = str(sql)
        bound = tuple(params or ())
        if "vector_scope" in statement:
            return _OneRow(self.scope_row)
        if "pg_attribute" in statement:
            return _OneRow(self.column_type)
        if statement == pg_store._APPLY_HNSW_EF_SEARCH_SQL:
            # R386：读腿在排名 SQL 之前定一次 HNSW 候选宽度。sqlite 没有 set_config，本离线件也
            # 不该有自己的宽度口径，所以这句照单收下、且不记进 statements——记进去就会被 _search
            # 的"这是不是那条排名 SQL"判定读成一条没认得的语句。管它该不该发的钉在
            # tests/test_r386_hnsw_ef_search_is_set_before_the_ranking_sql.py。
            return _Rows([])
        self.statements.append((statement, bound))
        return _Rows(self._search(statement, bound))

    # -- the search statement -------------------------------------------------
    def _search(self, statement, bound):
        if statement.count("%s") != len(bound):
            raise AssertionError("占位符 %d 个、绑定值 %d 个：%s"
                                 % (statement.count("%s"), len(bound), statement))
        operators = set(re.findall(r"embedding (<->|<=>|<#>) %s::vector", statement))
        if len(operators) != 1:
            raise AssertionError("距离算符不止一种或一种都没有：" + statement)
        operator = operators.pop()
        match = re.match(r"^SELECT (.+?), embedding (<->|<=>|<#>) %s::vector AS distance"
                         r" FROM chunk_vectors(?: WHERE (.+?)?)? ORDER BY embedding"
                         r" \2 %s::vector LIMIT %s$", statement)
        if match is None:
            raise AssertionError("发出的 SQL 不是本件认得的形状：" + statement)
        columns, _op, where = match.group(1), match.group(2), match.group(3)
        # 绑参的到达顺序就是 SQL 的书写顺序：向量文本、谓词 binds（每枚 %s 一枚，值是列表）、
        # 向量文本再一次、LIMIT。数量对不上即抛——这枚假件无视参数就答，等于给一条少带绑参的
        # SQL 发通行证（上一班的假件正是这样，被"占位符数 != 绑参数"那枚钉补掉了）。
        literal, rest = bound[0], list(bound[1:])
        expected_filters = where.count("%s") if where else 0
        if len(rest) != expected_filters + 2:
            raise AssertionError("参数对不上：谓词 %d 枚，余下 %d 枚"
                                 % (expected_filters, len(rest)))
        filter_params, literal_again, limit = (rest[:expected_filters],
                                               rest[expected_filters],
                                               rest[expected_filters + 1])
        if literal_again != literal:
            raise AssertionError("ORDER BY 用的不是同一个查询向量")
        adapted, filters = _adapt_where(where, filter_params) if where else ("1 = 1", [])
        sql = ("SELECT " + columns + ", " + self.OPERATORS[operator]
               + "(embedding, ?) AS distance FROM chunk_vectors"
               + ("" if adapted == "1 = 1" else " WHERE " + adapted)
               + " ORDER BY distance, vector_id LIMIT ?")
        rows = self.connection.execute(sql, [literal] + filters + [int(limit)]).fetchall()
        return rows

    def commit(self):
        raise AssertionError("只读腿不许 commit")

    def rollback(self):
        pass

    def close(self):
        pass


class _OneRow:
    """探测语句的应答：一行 tuple，与 psycopg 的 `fetchone()` 同形。"""

    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row]


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _parse(text):
    return [float(item) for item in str(text).strip().lstrip("[").rstrip("]").split(",")]


def _dot(left, right):
    return sum(x * y for x, y in zip(left, right))


def _norm(values):
    return math.sqrt(sum(value * value for value in values))


def _l2(left, right):
    """pgvector 的 <->：欧氏距离（不是平方，R157 那条两侧差异正记在这里）。"""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(left, right)))


def _cosine(left, right):
    return 1.0 - _dot(left, right) / ((_norm(left) * _norm(right)) or 1.0)


def _negative_inner_product(left, right):
    return -_dot(left, right)


_PREDICATE = re.compile(r"\b([a-z_]+) = ANY\(%s::(integer|text)\[\]\)", re.ASCII)
_ALLOWED_COLUMNS = frozenset({"classification", "department"})


def _adapt_where(clause, filter_params):
    """`col = ANY(%s::type[])` -> `col IN (?,...)`；认不出来即抛，绝不退化成没有 WHERE。

    空集合折成 `1 = 0`：PG 里 `= ANY(ARRAY[]::int[])` 是"一行都不满足"而不是语法错误，
    这一档的口径见 test_r59_where_parity.py 的裁定三。
    """
    queue = list(filter_params)

    def substitute(match):
        column, sql_type = match.group(1), match.group(2)
        if column not in _ALLOWED_COLUMNS:
            raise AssertionError("谓词里出现了没登记过的列 " + column)
        if not queue:
            raise AssertionError("谓词 %s 没有对应的绑定值" % column)
        values = queue.pop(0)
        if not isinstance(values, (list, tuple)):
            raise AssertionError("%s 的绑定值不是集合：%r" % (column, values))
        expected = int if sql_type == "integer" else str
        for value in values:
            if isinstance(value, bool) or not isinstance(value, expected):
                raise AssertionError("%s 的绑定值类型与声明不符：%r" % (column, value))
        if not values:
            return "1 = 0"
        return "%s IN (%s)" % (column, ", ".join("?" * len(values)))

    adapted = _PREDICATE.sub(substitute, clause)
    if "%s" in adapted or queue:
        raise AssertionError("谓词里有没被适配的形状：" + adapted)
    return adapted, [value for values in filter_params for value in values]


@pytest.fixture
def offline_legs(tmp_path, monkeypatch):
    """两条腿 + 精确对照。PG 侧走的是 `connection_factory` 那枚**生产接缝**：
    不改 `_connect`、不代理、不 patch 判定，所以总控换成真 DSN 时只需要不传这个工厂，
    其余一行都不用动。"""
    directory = str(tmp_path / "chroma")
    client = chromadb.PersistentClient(path=directory,
                                       settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection("enterprise_docs",
                                                 metadata={"hnsw:space": "l2"})
    rows = []
    prepared = []
    for position, (vector_id, body, department, level) in enumerate(CORPUS):
        filename = vector_id.rsplit("_", 1)[0]
        metadata = {"filename": filename, "chunk_index": position,
                    "classification": level, "department": department}
        rows.append({"vector_id": vector_id, "content": body, "filename": filename,
                     "chunk_index": position, "classification": level,
                     "department": department,
                     "embedding": "[" + ",".join(repr(value) for value
                                                 in CORPUS_VECTORS[vector_id]) + "]"})
        prepared.append((vector_id, body, CORPUS_VECTORS[vector_id], metadata))
    if prepared:
        collection.add(ids=[item[0] for item in prepared],
                       documents=[item[1] for item in prepared],
                       embeddings=[item[2] for item in prepared],
                       metadatas=[item[3] for item in prepared])

    double = _SqlitePg(rows)
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(DIM))
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    return {"collection": collection, "double": double,
            "ids": [row["vector_id"] for row in rows],
            "matrix": [CORPUS_VECTORS[row["vector_id"]] for row in rows]}


def chroma_topk(collection, query, *, k, where=None):
    kwargs = {"query_embeddings": [query], "n_results": k}
    if where:
        kwargs["where"] = where
    answer = collection.query(**kwargs)
    ids = (answer.get("ids") or [[]])[0]
    distances = (answer.get("distances") or [[]])[0]
    return list(zip(ids, distances))


def pg_topk(double, query, *, k, where=None):
    rows = pg_store.read_topk(query_vector=list(query), k=k, where=where,
                              connection_factory=lambda: double)
    return [(row["vector_id"], row["distance"]) for row in rows]


def run_offline_comparison(legs, questions, *, k=5, where=None, starved=None):
    """离线件本体：逐题两腿 -> `compare_question` 的一行读数，再聚成 §10 那几枚数。

    `starved` 是给正控制留的口子：交回一个 `ids -> ids` 的裁剪函数，就把某一条腿换成
    "候选预算被吃光"的形状（R269 症状 A/B 的形状），量具必须看得见它。
    """
    ids, matrix = legs["ids"], legs["matrix"]
    readings = []
    for question_id, text in questions:
        query = _vector_for(text)
        chroma = chroma_topk(legs["collection"], query, k=k, where=where)
        if starved is not None:
            chroma = [item for item in chroma if item[0] in set(starved(ids))]
        pg = pg_topk(legs["double"], query, k=k, where=where)
        readings.append(RULER.compare_question(
            source="r59-offline", question_id=question_id, question=text,
            chroma=chroma, pg=pg,
            pg_exact=RULER.exact_knn_topk(ids, matrix, query, metric="l2", k=k),
            chroma_exact=RULER.exact_knn_topk(ids, matrix, query, metric="l2", k=k),
            k=k, metric="l2", query_sha=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]))
    return readings


def _questions(count=None):
    archived = {item["id"]: item["question"]
                for item in _archived_reading()["questions"]}
    ordered = [(question_id, archived[question_id])
               for question_id in SECTION_TEN_ZERO_ROW_IDS]
    return ordered[:count] if count else ordered


# ------------------------------------------------------------------- 读数与正控制


def test_the_offline_pg_leg_never_answers_zero_rows(offline_legs):
    """离线件跑 §10 那 21 枚题号：PG 腿每题都答满 k 行，且与同库精确扫逐题相等。

    这正好是 §10 对真机那 21 枚的期望（"若切读 on 之后这 21 枚里有谁仍交空集，R211 的
    裁定当场作废"）。离线件先把**形状**钉住：题号、字段、k、两侧同库，全部同规格。
    """
    readings = run_offline_comparison(offline_legs, _questions(), k=5)

    assert len(readings) == 21
    assert sum(1 for item in readings if item["pg_zero_rows"]) == 0
    assert all(item["pg_rows"] == 5 for item in readings), [
        (item["id"], item["pg_rows"]) for item in readings if item["pg_rows"] != 5]
    assert all(item["index_vs_exact_same_set"] for item in readings)
    assert all(item["exact_sides_same_set"] for item in readings)


def test_the_offline_summary_carries_the_same_fields_as_the_real_reading(offline_legs):
    """聚合栏必须与 §10 复算用的那些名字同名，否则并树后两遍读数对不上账。"""
    summary = RULER.summarize(run_offline_comparison(offline_legs, _questions(), k=5))

    for field in ("questions", "same_set", "differing_set", "mean_overlap", "mean_jaccard",
                  "mean_kendall_tau", "chroma_zero_rows", "pg_zero_rows",
                  "chroma_only_zero", "pg_only_zero", "pg_index_vs_exact_same_set",
                  "exact_sides_same_set"):
        assert field in summary, field
    assert summary["questions"] == 21
    assert summary["pg_zero_rows"] == 0
    assert summary["pg_index_vs_exact_same_set"] == 21


def test_the_ruler_sees_a_starved_leg_for_what_it_is(offline_legs):
    """反证③的一半（正控制）：把某一条腿裁成"候选预算被吃光"，量具必须当场报出来。

    没有这一枚，上面那两枚只是"两侧都还行"的空话——一个恒真的比较器也能过。这里从
    chroma 的 top-k 里挖掉三枚近重复，看 summary 的 `differing_set` 与
    `chroma_index_vs_exact_same_set` 是否跟着变红。
    """
    honest = RULER.summarize(run_offline_comparison(offline_legs, _questions(), k=5))
    victims = [VECTOR_IDS[index] for index in (0, 1, 2)]
    starved = RULER.summarize(run_offline_comparison(
        offline_legs, _questions(), k=5,
        starved=lambda ids: [item for item in ids if item not in victims]))

    assert starved["differing_set"] > honest["differing_set"]
    assert starved["chroma_index_vs_exact_same_set"] < 21
    assert starved["pg_index_vs_exact_same_set"] == 21, "被裁的只许是 chroma 那条腿"


def test_a_pushed_down_scope_keeps_the_pg_leg_narrow(offline_legs):
    """离线件的权限腿：谓词进去之后 PG 侧只剩该看的行，且精确腿与索引腿同一批。

    这一枚不属于召回对比本身，属于"切读之后谓词仍然生效"——它挡的是那种"把 WHERE 去掉
    就跑得快一点"的顺手改动。语料里没有市场级的越权行会被这条 $in 放进来。
    """
    where = {"$and": [{"classification": {"$in": [1, 2]}},
                      {"department": {"$in": ["研发中心"]}}]}
    readings = run_offline_comparison(offline_legs, _questions(4), k=5, where=where)

    permitted = {row[0] for row in CORPUS if row[2] == "研发中心" and row[3] <= 2}
    assert len(permitted) == 6 and len(permitted) > 5, "样本要让谓词与 k 各管一摊"

    for item in readings:
        #: 谓词管"谁能进候选"，LIMIT 管"交回几行"：六枚该看的行被裁到五名，
        #: 而五名里一枚越权的都不许有。两侧同一口径（chroma 那腿也带着同一份 where）。
        assert set(item["pg_ids"]) <= permitted, item["id"]
        assert item["pg_rows"] == 5, item["id"]
        assert set(RULER.rank_map(item["pg_ids"]).values()) == {1, 2, 3, 4, 5}
