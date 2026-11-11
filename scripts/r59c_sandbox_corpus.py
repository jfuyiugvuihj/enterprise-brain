#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R59c 判据 ③ · 选择性权限过滤的沙盒语料构造器 + 谓词对照判据 + 业主批单（只出料，不动库）。

    python scripts/r59c_sandbox_corpus.py plan     --out %TEMP%/r59c-sandbox --chunks 60
    python scripts/r59c_sandbox_corpus.py verify --matrix %TEMP%/r59c-sandbox/matrix.jsonl \
        --run chroma-hot=%TEMP%/r59c_sandbox_chroma_hot.jsonl \
        --run pgvector=%TEMP%/r59c_sandbox_pgvector.jsonl \
        --json %TEMP%/r59c-sandbox/verdict.json
    python scripts/r59c_sandbox_corpus.py selfcheck --verbose

为什么这一格非要有这个文件
------------------------
计划书 §9.3 第 ③ 格的原话：现库 ``classification`` 全 = 1、``department`` 全 = ``''``，
所以谓词只能"全命中"或"全不命中"，**选择性强过滤下的召回差根本没量过**。
上一格 R59b 的补记把这条钉得很死（跟进单 §93.12 / 看板 §4BT 三，误判 #43）：
"入口能跑"不等于"这一格量过了"。所以本件不产读数，它产**三样能落地的料**：

1. ``corpus.json`` + ``documents/*.txt``：一份确定性的跨部门 x 跨密级语料（含 768 维向量），
   元数据分布刻意做成"每个谓词只放行一部分" —— 这才是 §9.3 ③ 要的"选择性"。
2. ``matrix.jsonl``：谓词对照判据。逐条principal 用**产品自己的**作用域函数算出下推谓词
   （app/rag/filters.py:resolve_document_retrieval_scope，本件不另立第二套权限口径），
   再离线算出该谓词下的精确 top-k（暴力扫，口径同 scripts/r59_recall_compare.py 的 exact-knn 腿）。
   有了它，"PG 侧交回 3 条"才第一次有了对错的标准答案。
3. ``sql/*.sql`` + ``BATCH.md``：**要业主拍板的 DDL/DML 批单**。本件一枚字节都不执行 ——
   它只做一件事：把"必须批什么、批在哪个库、错了怎么退"写清，并把落点钉死成独立沙盒库。

🔴 三条硬边界（写代码之前先钉）
--------------------------------
* **只建在独立沙盒库**：产出的每条 SQL 都以 ``SET search_path`` + 库名守卫开头，
  库名必须匹配 ``--sandbox-db``（默认 ``enterprise_brain_r59c``）；
  出现生产库名（``enterprise_brain`` 精确相等）本件直接拒绝出料。
* **本班不执行 DDL/DML**：本文件里没有一行动库的代码 —— 不 import psycopg、不连 DSN、
  不起容器。它写的是 .sql 文本与 JSON，跑不跑由业主拍板、由总控排窗。
* **合成向量 = 只测谓词算术，不测语义质量**：向量由 seeded LCG 生成，
  它证明的是"下推过滤 + 索引扫描在选择性子集上有没有少给/多给"，
  **不许**被引用成"PG 的语义召回比 Chroma 好/差"。那一格要真嵌入，见批单 B-6。

判据（本件对 ③ 的判定口径，与 verify 子命令同源）
------------------------------------------------
J-1 **可选性成立**：每个谓词放行的块数必须落在 (0, N) 开区间。全命中或全不命中的谓词
    不进这一格（今天的现库就是这个形状 ⇒ 整格 NOT_MEASURED）。
J-2 **不越权**：任何一侧交回的命中，其 (classification, department) 必须逐条落在该 principal
    的允许集合里。出现 1 条即整格红（这条与 R57 的 fail-closed 同口径）。
J-3 **与精确解一致**：该臂交回的 top-k 与本件离线算的**精确** top-k 比集合。
    PG 侧不一致 = HNSW 在选择性预过滤下漏给（这是切读要新增的风险面，正是要量的东西）；
    Chroma 侧不一致 = 遗留腿自身的已知缺陷（R158 那 24 题那一类），只记账不当作切读阻塞。
J-4 **两侧同题一致**：两臂在同一 principal 下的集合 Jaccard。这一条才是 §9.3 ③ 的字面对象。
J-5 **降级不算通过**：PG 腿若整个拒答退回 Chroma（app/rag/pg_store.py 里谓词翻译不出来
    ``ScopeFilterUntranslatable`` -> ``_pgvector_hits`` 交回 None），读数必须显式标
    ``fell_back``，并按"这一臂没量到"处理 —— 拿退回 Chroma 的读数冒充 PG 侧，就是误判 #43 重演。
    腿凭证取自 scripts/r59c_recall_compare.py 的 ``answered_by`` 增量，同一条纪律。

    R393（候选宽度口径）：本件生成的探针批不再自带宽度数字 —— 缺省现场向生产读腿那一枚
    唯一真源取，且只在事务内生效。经本件在 2026-09-27 之前取过的探针读数站在哪一档不可知，
    引用它们必须带 docs/perf/r393-tool-width-drift-2026-09-27.md 里那句限定。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TOOL = "scripts/r59c_sandbox_corpus.py"
SCHEMA = "r59c-sandbox-3"
EXIT_OK = 0
EXIT_RED = 1
EXIT_PRECONDITION = 2
EXIT_REFUSED = 3

#: 作用域两维的取值域。刻意做成叉乘：这样任何单维谓词都只放行一部分（J-1 的前提）。
DEPARTMENTS = ("fin", "hr", "ops", "exec")
CLASSIFICATIONS = (1, 2, 3)
#: 跑分账号的形状：role/clearance/department 三件决定谓词。admin 一档是**对照臂**（它不带
#: 部门谓词，等价于今天的现库形状），三档部门号才是 ③ 要的那一格。
PRINCIPALS = (
    {"label": "staff-fin-l1", "username": "r59c_staff_fin", "role": "staff",
     "department": "fin", "clearance": 1, "expect": "department+level"},
    {"label": "manager-hr-l2", "username": "r59c_manager_hr", "role": "manager",
     "department": "hr", "clearance": 2, "expect": "department+level"},
    {"label": "manager-ops-l2", "username": "r59c_manager_ops", "role": "manager",
     "department": "ops", "clearance": 2, "expect": "department+level"},
    {"label": "exec-l3", "username": "r59c_exec", "role": "manager",
     "department": "exec", "clearance": 3, "expect": "department+level"},
    {"label": "admin-l3", "username": "r59c_admin", "role": "admin",
     "department": "", "clearance": 3, "expect": "level-only"},
)
VECTOR_DIMENSION = 768
EMBEDDING_MODEL_LABEL = "r59c-synthetic-lcg"
DISTANCE_FUNCTION = "l2"
SANDBOX_DB_DEFAULT = "enterprise_brain_r59c"
PRODUCTION_DB_NAMES = frozenset({"enterprise_brain", "postgres", "template1"})
TABLE = "chunk_vectors"

# ------------------------------------------------------------------ 确定性合成语料

def _lcg(seed: int):
    state = seed & 0xFFFFFFFF

    def nxt():
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state

    return nxt


def synth_vector(seed: int, dimension: int = VECTOR_DIMENSION) -> list:
    """一枚确定性的单位向量（LCG，零依赖、跨机可复算）。

    🔴 它是**几何夹具**不是嵌入：它只保证"每个谓词下的 top-k 有一个可复算的正确答案"，
    不保证任何语义相关性。判据 J-1〜J-5 量的全是谓词算术，所以够用；引它当语义质量结论就是越界。
    """
    rnd = _lcg(seed)
    values = [rnd() / 0x7FFFFFFF - 0.5 for _ in range(dimension)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 6) for value in values]


def anchor_term(department: str, level: int, ordinal: int) -> str:
    return "r59cx{0}{1}{2:03d}".format(department[0], level, ordinal)


def build_corpus(chunks: int, *, dimension: int = VECTOR_DIMENSION) -> dict:
    """跨部门 x 跨密级的块表。刻意均匀铺：让每一档 principal 都只看得见一部分（J-1）。"""
    if chunks < len(DEPARTMENTS) * len(CLASSIFICATIONS) * 2:
        raise SystemExit(f"[前置不满足] --chunks={chunks} 太小：至少需要 "
                         f"{len(DEPARTMENTS) * len(CLASSIFICATIONS) * 2} 枚才谈得上选择性")
    cells = []
    for department in DEPARTMENTS:
        for level in CLASSIFICATIONS:
            cells.append((department, level))
    rows = []
    for index in range(chunks):
        department, level = cells[index % len(cells)]
        ordinal = index // len(cells)
        vector_id = "r59c-{0}-l{1}-{2:03d}".format(department, level, ordinal)
        term = anchor_term(department, level, ordinal)
        rows.append({"vector_id": vector_id, "filename": vector_id + ".txt",
                     "chunk_index": 0, "classification": level, "department": department,
                     "anchor": term,
                     "content": ("{0} 部门的第 {1} 级台账片段 {2}。关键字 {3}，"
                                 "用于确定性谓词对照，不承载业务语义。").format(
                                     department, level, ordinal, term),
                     "embedding": synth_vector(1000 + index * 7919, dimension)})
    return {"schema": SCHEMA, "tool": TOOL, "dimension": dimension,
            "distance_function": DISTANCE_FUNCTION, "embedding_model": EMBEDDING_MODEL_LABEL,
            "chunks": rows}


# ------------------------------------------------- 谓词矩阵（权限口径全部调产品本体）

def load_scope_resolver():
    """取产品的作用域函数本体。本件不复制第二套权限规则（AGENTS.md：不平行实现）。"""
    from app.agents.contracts import Principal
    from app.rag.filters import resolve_document_retrieval_scope

    def resolve(spec: dict) -> tuple:
        principal = Principal(user_id=spec["username"], username=spec["username"],
                              roles=[spec["role"]], permissions=[],
                              department=spec["department"], department_ids=[],
                              clearance=int(spec["clearance"]), status="active")
        scope = resolve_document_retrieval_scope(principal)
        return dict(scope.filters), scope.reason_code

    return resolve


def admits(scope: dict, row: dict) -> bool:
    """离线复算一条块在给定谓词下进不进得来（与 DocumentRetrievalScope.allows 同判序）。"""
    parsed = _parse_filter(scope)
    if parsed is None:
        return False
    levels, departments = parsed
    if levels is not None and row["classification"] not in levels:
        return False
    if departments is not None and str(row["department"] or "") not in departments:
        return False
    return True


def _parse_filter(where):
    levels = departments = None
    stack = [where]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            return None
        for key, value in node.items():
            if key == "$and":
                if not isinstance(value, list):
                    return None
                stack.extend(value)
                continue
            if key not in ("classification", "department"):
                return None
            if not isinstance(value, dict) or list(value) != ["$in"]:
                return None
            items = value["$in"]
            if not isinstance(items, list):
                return None
            if key == "classification":
                levels = frozenset(int(item) for item in items)
            else:
                departments = frozenset(str(item) for item in items)
    return levels, departments


def squared_l2(left: list, right: list) -> float:
    return sum((a - b) * (a - b) for a, b in zip(left, right))


def exact_topk(query_vector: list, pool: list, k: int) -> list:
    """在给定块集上暴力精确 top-k（升序；同距离按 vector_id 定序，两侧同一条 tie-break）。"""
    scored = sorted(((squared_l2(query_vector, row["embedding"]), row["vector_id"])
                     for row in pool), key=lambda item: (item[0], item[1]))
    return [vector_id for _distance, vector_id in scored[:k]]

def build_matrix(corpus: dict, *, top_k: int, queries: int = 12) -> dict:
    """逐 principal x 逐题，把"谓词放行了谁 + 精确 top-k 是谁"算成判据表。"""
    resolve = load_scope_resolver()
    rows = corpus["chunks"]
    probes = []
    for index in range(queries):
        seed_row = rows[(index * 7) % len(rows)]
        probes.append({"qid": "sbx-{0:02d}".format(index + 1),
                       "question": seed_row["anchor"] + " 的片段讲了什么？",
                       "query_vector": synth_vector(5000 + index * 104729,
                                                    corpus["dimension"]),
                       "nearest_unfiltered": None})
    cells = []
    for spec in PRINCIPALS:
        filters, reason = resolve(spec)
        pool = [row for row in rows if admits(filters, row)]
        share = round(len(pool) / len(rows), 4)
        cells.append({
            "principal": spec["label"], "username": spec["username"], "role": spec["role"],
            "department": spec["department"], "clearance": spec["clearance"],
            "scope_reason": reason, "filters": filters,
            "admitted_chunks": len(pool), "corpus_chunks": len(rows), "admitted_share": share,
            "j1_selective": 0 < len(pool) < len(rows),
            "expected": [{"qid": probe["qid"], "query": probe["question"],
                          "top_k": int(top_k),
                          "exact_ids": exact_topk(probe["query_vector"], pool, top_k)}
                         for probe in probes],
        })
    return {"schema": SCHEMA, "tool": TOOL, "mode": "matrix", "top_k": int(top_k),
            "dimension": corpus["dimension"], "distance_function": corpus["distance_function"],
            "embedding_model": corpus["embedding_model"], "corpus_sha": corpus_sha(corpus),
            "queries": [probe["qid"] for probe in probes], "cells": cells}


def corpus_sha(corpus: dict) -> str:
    joined = "|".join("{0}:{1}:{2}".format(row["vector_id"], row["classification"],
                                           row["department"]) for row in corpus["chunks"])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def write_documents(corpus: dict, documents_dir: Path) -> int:
    """把语料落成可上传的 .txt（生产入口 POST /api/v1/upload 收的就是这种文件）。"""
    documents_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in corpus["chunks"]:
        body = ("#{0} {1}\n\n密级 {2} / 部门 {3}\n\n{4}\n".format(
            row["anchor"], row["filename"], row["classification"], row["department"],
            row["content"]))
        (documents_dir / row["filename"]).write_text(body, encoding="utf-8", newline="\n")
        written += 1
    return written


# ------------------------------------------------------- SQL 批单（只写文件，绝不连库）

def _sql_literal(vector: list) -> str:
    return "[" + ",".join("{0:.6f}".format(value) for value in vector) + "]"


def assert_sandbox_target(database: str) -> None:
    """库名守卫：命中生产库名就拒出料。这道闸在本件里是**硬**的，不靠人记。"""
    name = str(database or "").strip()
    if not name:
        raise SystemExit(f"[拒绝出料] --sandbox-db 不能为空：没有落点的批单迟早会打在错库上")
    if name in PRODUCTION_DB_NAMES or not name.startswith(SANDBOX_DB_DEFAULT):
        print("[拒绝出料] 沙盒库名必须以 {0!r} 前缀开头且不等于生产库名，拿到 {1!r}"
              "（生产库一枚字节不许动）".format(SANDBOX_DB_DEFAULT, name))
        raise SystemExit(EXIT_REFUSED)


def emit_sql(corpus: dict, matrix: dict, *, database: str, table: str) -> dict:
    """产出四段 SQL 文本 + 一段回滚。返回 {文件名: 正文}，由人工过目后才轮到执行。"""
    assert_sandbox_target(database)
    head = ("-- R59c §9.3 ③ 沙盒批单（生成件，未执行）\n"
            "-- tool: {0}\n-- corpus_sha: {1}\n"
            "-- 🔴 落库：{2}（独立沙盒）。这段 SQL 一旦打到生产库就是越权改数据，"
            "本件的守卫只在校验库名，执行前必须再核一次 current_database()。\n"
            "-- 🔴 本班不执行：这一段是**批单**，业主拍板 + 总控排窗之后才有人按它动手。\n"
            "SET statement_timeout = '120s';\nSET lock_timeout = '5s';\n"
            .format(TOOL, matrix["corpus_sha"], database))
    guard = ("DO $$\nBEGIN\n  IF current_database() <> {0!r} THEN\n"
             "    RAISE EXCEPTION 'r59c 沙盒批单落错库，当前库 %', current_database();\n"
             "  END IF;\nEND\n$$;\n".format(database))
    ddl = head + guard + (
        "CREATE EXTENSION IF NOT EXISTS vector;\n"
        "CREATE SCHEMA IF NOT EXISTS public;\n"
        "CREATE TABLE IF NOT EXISTS {tbl} (\n"
        "    vector_id TEXT PRIMARY KEY,\n"
        "    filename TEXT NOT NULL,\n"
        "    chunk_index INTEGER NOT NULL,\n"
        "    content TEXT NOT NULL,\n"
        "    classification INTEGER,\n"
        "    department TEXT NOT NULL DEFAULT '',\n"
        "    content_sha256 TEXT,\n"
        "    index_version_id TEXT,\n"
        "    embedding vector({dim}) NOT NULL,\n"
        "    embedding_model TEXT NOT NULL,\n"
        "    embedding_dimension INTEGER NOT NULL,\n"
        "    distance_function TEXT NOT NULL,\n"
        "    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n"
        "    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n"
        "    CONSTRAINT {tbl}_document_chunk_unique UNIQUE (filename, chunk_index)\n"
        ");\n").format(tbl=table, dim=corpus["dimension"])
    scope = head + guard + (
        "CREATE TABLE IF NOT EXISTS vector_scope (\n"
        "    scope_key TEXT PRIMARY KEY,\n"
        "    embedding_model TEXT NOT NULL,\n"
        "    dimension INTEGER NOT NULL,\n"
        "    distance_function TEXT NOT NULL\n"
        ");\n"
        "INSERT INTO vector_scope (scope_key, embedding_model, dimension, distance_function)\n"
        "VALUES ('r59c-sandbox', {model!r}, {dim}, {dist!r})\n"
        "ON CONFLICT (scope_key) DO UPDATE SET embedding_model = EXCLUDED.embedding_model,\n"
        "    dimension = EXCLUDED.dimension, distance_function = EXCLUDED.distance_function;\n"
        .format(model=EMBEDDING_MODEL_LABEL, dim=corpus["dimension"], dist=DISTANCE_FUNCTION))
    inserts = [head + guard]
    for row in corpus["chunks"]:
        inserts.append(
            "INSERT INTO {tbl} (vector_id, filename, chunk_index, content, classification,\n"
            "    department, embedding, embedding_model, embedding_dimension, distance_function)\n"
            "VALUES ({vid!r}, {fn!r}, 0, {content!r}, {level}, {dept!r},\n"
            "    {vec}::vector, {model!r}, {dim}, {dist!r})\n"
            "ON CONFLICT (vector_id) DO UPDATE SET classification = EXCLUDED.classification,\n"
            "    department = EXCLUDED.department, embedding = EXCLUDED.embedding,\n"
            "    content = EXCLUDED.content, updated_at = NOW();\n".format(
                tbl=table, vid=row["vector_id"], fn=row["filename"],
                content=row["content"], level=row["classification"],
                dept=row["department"], vec=_sql_literal(row["embedding"]),
                model=EMBEDDING_MODEL_LABEL, dim=corpus["dimension"], dist=DISTANCE_FUNCTION))
    index = head + guard + (
        "-- HNSW 是这一格的**被测对象**：选择性预过滤下的召回差就长在它身上，必须建。\n"
        "-- 参数与生产同一份读数（docs/testing/r59b-recall-reading-2026-09-24.md：m=16、"
        "ef_construction=100、opclass vector_l2_ops）。\n"
        "CREATE INDEX IF NOT EXISTS {tbl}_embedding_hnsw_idx ON {tbl}\n"
        "    USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 100);\n"
        "CREATE INDEX IF NOT EXISTS {tbl}_department_idx ON {tbl} (department);\n"
        "CREATE INDEX IF NOT EXISTS {tbl}_classification_idx ON {tbl} (classification);\n"
        .format(tbl=table))
    rollback = (head + guard +
                "-- 回滚只删本件建的沙盒表；生产库不适用这一段。\n"
                "DROP TABLE IF EXISTS {tbl};\nDROP TABLE IF EXISTS vector_scope;\n"
                .format(tbl=table))
    return {"00_guard_note.sql": head, "01_scope.sql": scope, "02_table.sql": ddl,
            "03_chunks.sql": "".join(inserts), "04_indexes.sql": index,
            "99_rollback.sql": rollback}

#: ------------------------------------------------------------------ 候选宽度（R393）
#:
#: 这批探针踩在哪一档 HNSW 候选宽度上，过去由本件自带的一个数字决定，而那个数字不等于
#: 生产读腿钉下去的那一档。现在缺省现场向唯一真源取（app.rag.pg_store
#: .configured_hnsw_ef_search()，R386 立的读取点）：本文件一个候选宽度数字都不许出现，
#: 注释也不例外 —— 数字抄进第二处就一定会漂，而漂了没人量得到。两档各是多少、哪些历史
#: 读数因此站不上生产口径，见 docs/perf/r393-tool-width-drift-2026-09-27.md。
TRUE_SOURCE = "app.rag.pg_store.configured_hnsw_ef_search"
#: pgvector 的 GUC 只在库被这条会话用过之后才存在于这条会话（实测：全新会话读它当场
#: unrecognized）。整批探针跑在 BEGIN ... ROLLBACK 之间，设定只在事务内生效，跑完不残留。
LOAD_VECTOR_PROBE_SQL = "SELECT NULL::vector IS NULL"


def probe_ef_source():
    """取候选宽度的唯一真源模块；取不到就明确报错退出，绝不退回一个自定的数。"""
    try:
        from app.rag import pg_store
    except Exception as exc:
        raise SystemExit(
            "[前置不满足] 探针的候选宽度取不到唯一真源 " + TRUE_SOURCE + "（import 失败："
            + type(exc).__name__ + " " + str(exc)[:160] + "）—— 本件不许自带宽度，拒出料")
    if getattr(pg_store, "configured_hnsw_ef_search", None) is None:
        raise SystemExit("[前置不满足] 这棵树里没有 " + TRUE_SOURCE
                         + "：候选宽度没有真源可读，本件不许自带宽度，拒出料")
    return pg_store


def resolve_probe_ef_search(explicit=None):
    """定这批探针踩哪一档：显式给了用给的那一档，没给就现场向唯一真源取。交回 (值, 来历)。"""
    if explicit is not None:
        return int(explicit), "CLI --ef-search（人为指定，非生产口径）"
    value = probe_ef_source().configured_hnsw_ef_search()
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit("[前置不满足] 唯一真源 " + TRUE_SOURCE + " 交回的不是整数（"
                         + type(value).__name__ + "）：候选宽度不可知，拒出料")
    return int(value), TRUE_SOURCE + "（现场取，与生产读腿同一次调用）"


def render_apply_width_sql(width) -> str:
    """把真源那条参数化 SQL 落成批单里的字面语句：形状来自真源，本件只填两枚参数。

    本件不自己写设定函数那一串，也不自己写那个局部标记：真源哪天改口（换函数、换作用域），
    这里的占位符对不上就当场炸，而不是安静地生成一批站在别的档上的探针。
    """
    pg_store = probe_ef_source()
    sql = str(pg_store._APPLY_HNSW_EF_SEARCH_SQL)
    if sql.count("%s") != 2:
        raise SystemExit("[前置不满足] 真源的设定语句不再是两枚参数（" + sql[:160]
                         + "）：本件不许猜它的形状，拒出料")
    return sql.replace("%s", "'{}'", 1).replace("%s", "'{}'", 1).format(
        pg_store.HNSW_EF_SEARCH_GUC, int(width))


def emit_probe_queries(corpus: dict, matrix: dict, *, table: str, ef_search=None) -> str:
    """只读探针：把产品读腿那条 SQL 逐 principal 逐题打一遍，交回 vector_id 顺序。

    这**不是**批单的一部分（不建不改），但它是 ③ 的取数口：总控在沙盒库上跑这一段，
    把结果按 cell 存成 JSON，再交给本件 verify 判 J-1〜J-5。SQL 形状照抄
    app/rag/pg_store.py:search_vectors（算符由 distance_function 决定，不猜）。

    🔴 这一批踩在哪一档候选宽度上（R393）：缺省跟随唯一真源，并且只在**一笔事务内**生效
    —— 整批 BEGIN ... ROLLBACK，设定走 set_config(..., TRUE)。会话级 SET 不在此列：它会
    一直留在这条连接上，把后面每一次读数都染成同一档。开头那条 vector 类型探测不是装饰：
    库没被这条会话用过之前，下面那条设定只会立一枚 pgvector 根本不读的占位参数（实测：它
    照样念回那个数），等库被别的语句带起来时占位值又被出厂档顶掉。探测在前，设定才有见证。
    """
    width, width_source = resolve_probe_ef_search(ef_search)
    lines = ["-- R59c 沙盒只读探针（零写入；生成件）corpus_sha=" + matrix["corpus_sha"],
             "-- HNSW 候选宽度 = {0}；来历 = {1}".format(width, width_source),
             "-- 作用域 = 事务内：整批 BEGIN ... ROLLBACK，设定只在笔内有效，跑完不残留",
             "BEGIN;",
             LOAD_VECTOR_PROBE_SQL + ";",
             "-- 先让库存在于这条会话：没加载时下面那条设定只会立一枚 pgvector 不读的占位参数",
             render_apply_width_sql(width) + ";",
             ""]
    for cell in matrix["cells"]:
        levels, departments = _parse_filter(cell["filters"])
        clause = []
        if levels:
            clause.append("classification = ANY('{["
                          + ",".join(str(item) for item in sorted(levels)) + "]}'::integer[])")
        if departments:
            clause.append("department = ANY('{["
                          + ",".join(sorted(departments)) + "]}'::text[])")
        where = (" WHERE " + " AND ".join(clause)) if clause else ""
        for expected in cell["expected"]:
            ordinal = int(expected["qid"].split("-")[1]) - 1
            probe_vector = synth_vector(5000 + ordinal * 104729, VECTOR_DIMENSION)
            lines.append("-- cell={0} qid={1} exact_ids={2}".format(
                cell["principal"], expected["qid"], ",".join(expected["exact_ids"])))
            lines.append("SELECT '{0}' AS cell, '{1}' AS qid, vector_id, classification, "
                         "department FROM {2}{3} ORDER BY embedding <-> '{4}'::vector "
                         "LIMIT {5};".format(cell["principal"], expected["qid"], table, where,
                                              _sql_literal(probe_vector), expected["top_k"]))
        lines.append("")
    lines.append("-- 收尾：结束这笔事务，事务内的候选宽度设定随之消失（本批零写入，回滚即可）")
    lines.append("ROLLBACK;")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ verify（判 J-1〜J-5）

def jaccard(left: list, right: list):
    a, b = set(left), set(right)
    union = a | b
    if not union:
        return None
    return round(len(a & b) / len(union), 4)


def verify_matrix(corpus: dict, matrix: dict, readings: dict) -> dict:
    """readings = {arm: {principal: {qid: [vector_id...]}}}。缺任何一格都如实报缺。"""
    by_id = {row["vector_id"]: row for row in corpus["chunks"]}
    arms = sorted(readings)
    verdicts = []
    for cell in matrix["cells"]:
        principal = cell["principal"]
        per_arm = {}
        for arm in arms:
            rows = readings[arm].get(principal) or {}
            over_permission = 0
            mismatches = []
            missing = []
            for expected in cell["expected"]:
                got = rows.get(expected["qid"])
                if got is None:
                    missing.append(expected["qid"])
                    continue
                for vector_id in got:
                    row = by_id.get(vector_id)
                    if row is None or not admits(cell["filters"], row):
                        over_permission += 1
                if list(got) != list(expected["exact_ids"]):
                    mismatches.append({"qid": expected["qid"], "got": list(got),
                                       "exact": list(expected["exact_ids"]),
                                       "jaccard": jaccard(got, expected["exact_ids"])})
            per_arm[arm] = {
                "cells_expected": len(cell["expected"]), "cells_present": len(rows),
                "cells_missing": len(missing), "missing_qids": missing[:10],
                "over_permission_rows": over_permission,
                "index_vs_exact_mismatch": len(mismatches),
                "mismatch_qids": [item["qid"] for item in mismatches]}
        pair = []
        if len(arms) >= 2:
            for expected in cell["expected"]:
                left = readings[arms[0]].get(principal, {}).get(expected["qid"])
                right = readings[arms[1]].get(principal, {}).get(expected["qid"])
                if left is not None and right is not None:
                    step = jaccard(left, right)
                    if step is not None:
                        pair.append(step)
        selective_cells = [item for item in (per_arm.get(arm) for arm in arms) if item]
        verdicts.append({
            "principal": principal, "scope_reason": cell["scope_reason"],
            "admitted_chunks": cell["admitted_chunks"], "corpus_chunks": cell["corpus_chunks"],
            "admitted_share": cell["admitted_share"], "j1_selective": cell["j1_selective"],
            "j2_no_over_permission": bool(selective_cells) and all(
                item["over_permission_rows"] == 0 for item in selective_cells),
            "j3_matches_exact": bool(selective_cells) and all(
                item["index_vs_exact_mismatch"] == 0 and item["cells_missing"] == 0
                for item in selective_cells),
            "j4_cross_arm_jaccard": (round(sum(pair) / len(pair), 4) if pair else None),
            "j5_all_arms_answered": bool(arms) and all(
                (readings[arm].get(principal) or {}).get("__answered__", True) for arm in arms),
            "per_arm": per_arm})
    selective = [item for item in verdicts if item["j1_selective"]]
    if not readings:
        status, why = "NOT_MEASURED", "没有读数：③ 需要 --run 指到两侧各自的产物"
    elif not selective:
        status, why = "NOT_MEASURED", "谓词没有选择性：全部 principal 都全命中或全不命中"
    elif all(item["j2_no_over_permission"] and item["j3_matches_exact"]
             and item["j4_cross_arm_jaccard"] == 1.0 for item in selective):
        status, why = "GREEN", "选择性谓词下两侧一致且都等于精确解"
    else:
        status, why = "RED", "至少一格不达标，见 cells 明细"
    return {"schema": SCHEMA, "tool": TOOL, "mode": "verdict",
            "corpus_sha": matrix["corpus_sha"], "arms": arms,
            "principals_total": len(verdicts), "principals_selective": len(selective),
            "status": status, "why": why, "cells": verdicts}

def principal_for_record(record: dict, matrix: dict) -> str:
    """按谓词签名反查这一发是谁问的（不靠猜：拿 filters 逐格比）。"""
    levels = record.get("admitted_levels")
    departments = record.get("admitted_departments")
    reason = record.get("scope_reason")
    for cell in matrix["cells"]:
        if cell["scope_reason"] != reason:
            continue
        parsed = _parse_filter(cell["filters"])
        cell_levels = sorted(parsed[0]) if parsed[0] is not None else None
        cell_departments = sorted(parsed[1]) if parsed[1] is not None else None
        if cell_levels == (sorted(levels) if levels else None) \
                and cell_departments == (sorted(departments) if departments else None):
            return cell["principal"]
    return "unknown-principal"


def read_service_run(path: Path, arm: str, matrix: dict) -> dict:
    """把 scripts/r59c_recall_compare.py 的 run 产物折成 verify 要的 {principal: {qid: [ids]}}。

    🔴 腿凭证未证实的读数直接拒收：拿"其实是 Chroma 答的"那一份冒充 PG 侧，就是误判 #43 重演。
    """
    buckets = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("kind") != "request":
            continue
        if record.get("arm") != arm:
            raise SystemExit("[拒绝读数] {0}:{1} 的 arm={2!r} != 声明的 {3!r}".format(
                path, number, record.get("arm"), arm))
        if record.get("status") != "ok":
            continue
        if record.get("arm_ok") is not True:
            raise SystemExit("[拒绝读数] {0}:{1} 臂身份未证实（{2}）：这一臂不许进 ③ 的判据"
                             .format(path, number, record.get("arm_reason")))
        principal = principal_for_record(record, matrix)
        if principal == "unknown-principal":
            continue
        ids = []
        for hit in record.get("hits") or []:
            source = (hit.get("key") or hit.get("source") or "").split("#")[0]
            ids.append(source[:-4] if source.endswith(".txt") else source)
        buckets.setdefault(principal, {})[record.get("qid")] = ids
    return buckets


def read_probe_csv_run(path: Path, matrix: dict) -> dict:
    """读 psql --csv 探针结果成 verify 要的 {principal: {qid: [vector_id...]}}。

    🔴 不按「第一行就是表头」读（R393）。这一批在排名 SELECT 之前还排着 BEGIN、库探测、
    事务内设定三句，`psql --csv` 会把命令标签和它们的单列输出一起打进来（实测顺序：
    `BEGIN` / `?column?` / `t` / `set_config` / `<那一档的值>` / 表头 / 数据行 / ... /
    `ROLLBACK`），而且每回一条排名 SELECT 都会再打一遍自己的表头。拿第一行当表头，
    `row.get("cell")` 就永远是 None，每一条真读数都会被读没 —— 而「零读数」在 verify
    里长得和「没跑」一模一样，这条腿从生下来就没被真读数喂过。
    认行的唯一凭据是矩阵自己：第一列是该 principal 的字面标签、第二列是它名下的 qid，
    其余行（标签、单列值、表头）一律跳过。一条都没认出来就当场报错，不许交回空桶。
    """
    import csv
    known = {}
    for cell in matrix["cells"]:
        known[str(cell["principal"])] = {str(item["qid"]) for item in cell["expected"]}
    buckets = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 3:
                continue
            cell, qid = str(row[0]), str(row[1])
            if cell not in known or qid not in known[cell]:
                continue
            buckets.setdefault(cell, {}).setdefault(qid, []).append(str(row[2]))
    if not buckets:
        raise SystemExit("[前置不满足] 探针读数文件里一条真读数都没认出来：" + str(path)
                         + " —— 这一臂没有读数，判不了（不许当成零命中）")
    return buckets


def emit_batch(matrix: dict, sql_files: dict, corpus: dict, *, database: str) -> str:
    """业主批单：一页纸看清"批什么、打在哪个库、多大、怎么退、不批会怎样"。"""
    lines = ["# R59c §9.3 ③ 沙盒批单（待业主拍板 · 本班未执行）", "",
             "- 生成件：" + TOOL, "- 目标库：`{0}`（🔴 独立沙盒，生产库不在本批单范围内）".format(database),
             "- 语料指纹：`corpus_sha={0}`，块数 {1}，维度 {2}，距离 `{3}`".format(
                 matrix["corpus_sha"], len(corpus["chunks"]), corpus["dimension"],
                 corpus["distance_function"]),
             "- 向量：**LCG 合成**。这一批量的是谓词算术与选择性预过滤，**不是**语义质量。", "",
             "## 批单条目", "", "| 文件 | 性质 | 幂等 | 回滚 | 不批的后果 |", "|---|---|---|---|---|"]
    table = {"00_guard_note.sql": ("注释", "-", "-", "-"),
             "01_scope.sql": ("DDL+DML", "ON CONFLICT DO UPDATE", "99_rollback.sql",
                              "vector_scope 缺行 -> 读腿 vector_mirror 直接判前置不满足"),
             "02_table.sql": ("DDL", "CREATE TABLE IF NOT EXISTS", "99_rollback.sql",
                              "没有 chunk_vectors -> 沙盒里两侧都没东西可读"),
             "03_chunks.sql": ("DML x{0}".format(len(corpus["chunks"])),
                               "ON CONFLICT (vector_id) DO UPDATE",
                               "DELETE FROM chunk_vectors WHERE vector_id LIKE 'r59c-%'",
                               "§9.3 ③ 整格继续 NOT_MEASURED（现库谓词只能全命中/全不命中）"),
             "04_indexes.sql": ("DDL", "CREATE INDEX IF NOT EXISTS",
                                "DROP INDEX 同名", "没有 HNSW -> J-3 只能量精确解，量不到索引腿"),
             "99_rollback.sql": ("DDL", "-", "-", "-")}
    for name in sorted(sql_files):
        kind, idempotent, rollback, blocked = table.get(name, ("-", "-", "-", "-"))
        lines.append("| `{0}` | {1} | {2} | {3} | {4} |".format(
            name, kind, idempotent, rollback, blocked))
    lines += ["", "## 逐格谓词（放行比例就是选择性本身）", "",
              "| principal | role | dept | clearance | scope_reason | 放行块数 | 占比 | J-1 可选 |",
              "|---|---|---|---|---|---|---|---|"]
    for cell in matrix["cells"]:
        lines.append("| `{0}` | {1} | {2} | {3} | `{4}` | {5} | {6} | {7} |".format(
            cell["principal"], cell["role"], cell["department"] or "-", cell["clearance"],
            cell["scope_reason"], cell["admitted_chunks"], cell["admitted_share"],
            "是" if cell["j1_selective"] else "否"))
    lines += ["", "## 执行序（业主批准后，由总控在沙盒窗内按序执行）", "",
              "1. `createdb {0}`（或 docker 起一枚独立 pgvector 容器；**不许**指向生产实例）".format(database),
              "2. `psql -d {0} -f sql/01_scope.sql`、`02_table.sql`、`03_chunks.sql`、"
              "`04_indexes.sql`（按此序）".format(database),
              "3. `psql -d {0} -f sql/99_rollback.sql` 先在**另一份**同名沙盒上演练一遍回滚".format(database),
              "4. 跑只读探针 `sql/probes.sql` -> `--probe-csv` 交给 `verify`：这一批踩在哪一档"
              "HNSW 候选宽度上写在文件头注释里，来历是生产读腿的唯一真源；整批跑在一笔事务内，"
              "跑完不残留在连接上（要换档就显式给 `--ef-search`，批头会写明那是人为指定的）",
              "5. 若要在服务层量（含 Chroma 侧），走 `documents/*.txt` + `POST /api/v1/upload`，"
              "上传账号必须是本批单列出的 principal —— 生产读路径的 department 来自 **principal**"
              "（app/api/v1/chat.py:3445 那一行 `department = principal.department`），"
              "表单里那个 department 参数会被覆盖，所以跨部门语料必须先有跨部门账号", "",
              "## 需要业主拍板的三件事", "",
              "1. 允许新建独立沙盒库 `{0}`（不碰生产；含 CREATE EXTENSION vector）".format(database),
              "2. 允许在沙盒里建 5 个合成 principal（口令不进版本库，只在窗内注入）",
              "3. 确认「合成向量沙盒」这一格的结论只用于谓词算术，不写进语义质量的任何结论", ""]
    return "\n".join(lines) + "\n"

# ----------------------------------------------------------- 离线自校（含反证钉，教训 #46）

def _pin(pins: list, name: str, ok: bool, detail: str = "") -> None:
    pins.append({"pin": ("PASS " if ok else "FAIL ") + name, "ok": bool(ok),
                 "detail": detail[:220]})


def run_selfcheck(*, verbose: bool = False) -> int:
    """零容器、零模型、零网络：证明谓词矩阵、J-1〜J-5 判定、批单守卫三路都算得对且有牙。"""
    pins: list = []
    corpus = build_corpus(len(DEPARTMENTS) * len(CLASSIFICATIONS) * 3)
    matrix = build_matrix(corpus, top_k=3, queries=4)
    by_id = {row["vector_id"]: row for row in corpus["chunks"]}

    # S1 语料形状：四部门 x 三密级均匀铺，每档 principal 都只看得见一部分
    cells = {cell["principal"]: cell for cell in matrix["cells"]}
    department_cells = [cell for cell in matrix["cells"]
                        if cell["scope_reason"] == "department_scope"]
    _pin(pins, "S1 沙盒语料有选择性（J-1：每一档部门号都只放行一部分）",
         bool(department_cells) and all(0 < cell["admitted_share"] < 1.0
                                        for cell in department_cells)
         and len(department_cells) == len(PRINCIPALS) - 1
         and all(row["department"] in DEPARTMENTS and row["classification"] in CLASSIFICATIONS
                 for row in corpus["chunks"]),
         json.dumps({cell["principal"]: cell["admitted_share"] for cell in matrix["cells"]}))
    staff = cells["staff-fin-l1"]
    _pin(pins, "S2 谓词取自产品本体且形状正确（fin / <=1）",
         staff["scope_reason"] == "department_scope"
         and _parse_filter(staff["filters"]) == (frozenset({1}), frozenset({"fin"}))
         and all(row["department"] == "fin" and row["classification"] <= 1
                 for row in corpus["chunks"]
                 if row["vector_id"] in [item for item in
                                         [c["vector_id"] for c in corpus["chunks"]]
                                         if admits(staff["filters"], by_id[item])]),
         json.dumps(staff["filters"]))
    _pin(pins, "S2b admin 一档退化成全命中（这条就是现库的病，写进判据免得被当成通过）",
         cells["admin-l3"]["scope_reason"] == "administrator_scope"
         and cells["admin-l3"]["admitted_share"] == 1.0
         and cells["admin-l3"]["j1_selective"] is False,
         json.dumps({"share": cells["admin-l3"]["admitted_share"],
                     "j1": cells["admin-l3"]["j1_selective"]}))

    # S3 精确 top-k 可复算：同一枚 query 重跑逐位相同；且放行集外的块一枚都不许出现
    first = cells["manager-hr-l2"]["expected"][0]
    probe_vector = synth_vector(5000 + 0 * 104729, corpus["dimension"])
    pool = [row for row in corpus["chunks"] if admits(cells["manager-hr-l2"]["filters"], row)]
    again = exact_topk(probe_vector, pool, 3)
    _pin(pins, "S3 精确 top-k 可复算且在允许集内",
         again == list(first["exact_ids"])
         and all(by_id[item]["department"] == "hr" and by_id[item]["classification"] <= 2
                 for item in first["exact_ids"]),
         json.dumps({"ids": first["exact_ids"], "recomputed": again}))

    # S4 完美读数必须全绿（先钉"不抽错时不许红"，反证才有意义）
    perfect = {"pgvector": {cell["principal"]: {item["qid"]: list(item["exact_ids"])
                                                for item in cell["expected"]}
                            for cell in matrix["cells"]},
               "chroma-hot": {cell["principal"]: {item["qid"]: list(item["exact_ids"])
                                                  for item in cell["expected"]}
                              for cell in matrix["cells"]}}
    verdict_ok = verify_matrix(corpus, matrix, perfect)
    _pin(pins, "S4 完美读数 -> 两侧一致且等于精确解（GREEN）",
         verdict_ok["status"] == "GREEN" and verdict_ok["principals_selective"] == 4,
         json.dumps({"status": verdict_ok["status"],
                     "selective": verdict_ok["principals_selective"]}))

    # S5 反证钉 ①：只抽错 manager-hr-l2 的一题 -> 红必须只落在那一格的 qid 上
    sabotage = json.loads(json.dumps(perfect))
    victim = cells["manager-hr-l2"]["expected"][1]
    sabotage["pgvector"][cells["manager-hr-l2"]["principal"]][victim["qid"]] = \
        [victim["exact_ids"][1], victim["exact_ids"][0]] + victim["exact_ids"][2:]
    verdict5 = verify_matrix(corpus, matrix, sabotage)
    red_cells = [item for item in verdict5["cells"]
                 if item["j1_selective"] and not item["j3_matches_exact"]]
    _pin(pins, "S5 反证钉：抽错一题的**顺序** -> 红只落在那一格那一题（J-3）",
         len(red_cells) == 1 and red_cells[0]["principal"] == cells["manager-hr-l2"]["principal"]
         and red_cells[0]["per_arm"]["pgvector"]["mismatch_qids"] == [victim["qid"]]
         and red_cells[0]["per_arm"]["chroma-hot"]["index_vs_exact_mismatch"] == 0,
         json.dumps({"red": [item["principal"] for item in red_cells],
                     "qids": red_cells[0]["per_arm"]["pgvector"]["mismatch_qids"]
                     if red_cells else []}))

    # S6 反证钉 ②：漏给（少一条）要红；顺序变而集合不变 => J-4 仍算一致（口径要能自己说清）
    drop = json.loads(json.dumps(perfect))
    target = cells["exec-l3"]["expected"][0]
    drop["pgvector"][cells["exec-l3"]["principal"]][target["qid"]] = list(target["exact_ids"][1:])
    verdict6 = verify_matrix(corpus, matrix, drop)
    cell6 = next(item for item in verdict6["cells"]
                 if item["principal"] == cells["exec-l3"]["principal"])
    _pin(pins, "S6 反证钉：HNSW 少给一条 -> J-3 红且点名那一题",
         cell6["j3_matches_exact"] is False
         and cell6["per_arm"]["pgvector"]["mismatch_qids"] == [target["qid"]],
         json.dumps({"mismatch": cell6["per_arm"]["pgvector"]["mismatch_qids"]}))

    # S7 反证钉 ③：交回允许集外的块 => J-2 越权红，比 J-3 更早炸
    leak = json.loads(json.dumps(perfect))
    foreign = next(row["vector_id"] for row in corpus["chunks"]
                   if not admits(cells["staff-fin-l1"]["filters"], row))
    first_q = cells["staff-fin-l1"]["expected"][0]["qid"]
    leak["pgvector"][cells["staff-fin-l1"]["principal"]][first_q] = \
        [foreign] + cells["staff-fin-l1"]["expected"][0]["exact_ids"][:2]
    verdict7 = verify_matrix(corpus, matrix, leak)
    cell7 = next(item for item in verdict7["cells"]
                 if item["principal"] == cells["staff-fin-l1"]["principal"])
    _pin(pins, "S7 反证钉：一条越权块 -> J-2 直接红（fail-closed 优先于召回）",
         cell7["j2_no_over_permission"] is False
         and cell7["per_arm"]["pgvector"]["over_permission_rows"] == 1
         and verdict7["status"] == "RED",
         json.dumps({"over": cell7["per_arm"]["pgvector"]["over_permission_rows"],
                     "status": verdict7["status"]}))

    # S8 缺读数不许判通过；全不命中谓词不配进这一格
    verdict8 = verify_matrix(corpus, matrix, {})
    verdict9 = verify_matrix(corpus, {"corpus_sha": matrix["corpus_sha"], "top_k": 3,
                                      "chunks": None,
                                      "cells": [dict(cells["admin-l3"], j1_selective=False)]},
                             perfect)
    _pin(pins, "S8 缺读数 -> NOT_MEASURED（不许把空表印成通过）",
         verdict8["status"] == "NOT_MEASURED", verdict8["why"]),
    _pin(pins, "S9 只有全命中谓词 -> NOT_MEASURED（这就是 §9.3 ③ 今天的形状）",
         verdict9["status"] == "NOT_MEASURED" and verdict9["principals_selective"] == 0,
         verdict9["why"])

    # S10 批单守卫：生产库名必须拒
    import contextlib
    import io
    refused = io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(refused):
            emit_sql(corpus, matrix, database="enterprise_brain", table=TABLE)
    except SystemExit as exc:
        code = exc.code
    _pin(pins, "S10 批单守卫：库名撞上生产就拒出料（退出码 3，且不产任何文件）",
         code == EXIT_REFUSED and "拒绝出料" in refused.getvalue(),
         "exit={0} msg={1}".format(code, refused.getvalue()[:90]))

    # S11 SQL 文本可解析性：每条 INSERT 都自带守卫与幂等子句，且没有一句 DROP 混在正向批单里
    sql_files = emit_sql(corpus, matrix, database=SANDBOX_DB_DEFAULT, table=TABLE)
    forward = "".join(value for key, value in sql_files.items() if key != "99_rollback.sql")
    _pin(pins, "S11 正向批单里不许出现 DROP，且每条都过 current_database() 守卫",
         "DROP TABLE" not in forward and forward.count("current_database()") >= 5
         and forward.count("ON CONFLICT") >= len(corpus["chunks"]),
         "guard_hits={0} inserts={1}".format(forward.count("current_database()"),
                                             forward.count("ON CONFLICT")))
    import re
    probes = emit_probe_queries(corpus, matrix, table=TABLE)
    ranking = [line for line in probes.splitlines() if line.startswith("SELECT '")]
    width_now = resolve_probe_ef_search()[0]
    head = probes.splitlines()
    _pin(pins, "S12 只读探针零写入：只有排名 SELECT 每回一条，设定只活在事务内",
         all(token not in probes for token in ("INSERT", "CREATE ", "DROP"))
         and len(ranking) == sum(len(cell["expected"]) for cell in matrix["cells"])
         and "\nBEGIN;\n" in probes and probes.rstrip().endswith("ROLLBACK;")
         and "set_config(" in probes and not re.search(r"SET\s+hnsw", probes, re.I)
         and head[0].startswith("-- R59c") and LOAD_VECTOR_PROBE_SQL in probes,
         "selects={0} head={1}".format(len(ranking), head[3][:40]))
    _pin(pins, "S12b 探针宽度只有一个真源：批里那一档 == 现场向真源取的那一档",
         ("HNSW 候选宽度 = {0}；".format(width_now)) in probes
         and TRUE_SOURCE in probes
         and ("HNSW 候选宽度 = {0}；".format(width_now + 1)) not in probes
         and resolve_probe_ef_search(width_now + 1)[0] == width_now + 1,
         "width={0}".format(width_now))

    # S13〜S15 跨件接口：拿 scripts/r59c_recall_compare.py 的**真实产物形状**喂进 verify
    import importlib.util
    sibling = REPO_ROOT / "scripts" / "r59c_recall_compare.py"
    spec = importlib.util.spec_from_file_location("r59c_compare_reader", sibling)
    A = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = A
    spec.loader.exec_module(A)
    limits = {"max_excerpt_chars": 240}

    def fake_run(path: Path, arm: str, leg: str, *, break_arm_ok: bool = False) -> None:
        lines = [json.dumps({"kind": "header", "schema": A.SCHEMA, "arm": arm,
                             "top_ks": [3], "repeats": 1, "fixture_rows": 4,
                             "revision": "selfcheck", "username": "selfcheck",
                             "limits": {}, "health_probe": True,
                             "questions_sha": "x", "switch_declared": "",
                             "started_at": "", "base_url": "http://selfcheck.invalid"},
                            ensure_ascii=False)]
        for cell in matrix["cells"]:
            for expected in cell["expected"]:
                hits = []
                for rank, vector_id in enumerate(expected["exact_ids"], start=1):
                    row = by_id[vector_id]
                    hits.append({"source": row["filename"], "chunk_index": float(row["chunk_index"]),
                                 "classification": float(row["classification"]),
                                 "department": row["department"], "score": 1.0 - rank * 0.1,
                                 "excerpt": row["content"][:240], "permission_checked": True})
                report = {"results": hits, "rewrites": [expected["query"]],
                          "permission_filter": cell["filters"],
                          "scope_reason": cell["scope_reason"], "stages": [],
                          "duration_ms": 4080.0 + rank_of(expected["qid"]),
                          "bounds": {"results_total": len(hits), "results_returned": len(hits),
                                     "truncated": False}}
                pre = {"search_shape": {"answered_by": {}}, "hot_index": {"enabled": False}}
                post = {"search_shape": {"answered_by": {leg: 1}},
                        "hot_index": {"enabled": (leg == A.LEG_HOT)}, "problems": [],
                        "status": "ok"}
                record = A.build_record(
                    arm=arm, row={"id": expected["qid"], "question": expected["query"],
                                  "category": "sandbox", "tier": "问答",
                                  "must_contain": [by_id[expected["exact_ids"][0]]["anchor"]]},
                    top_k=3, rep=0, report=report, pre=pre, post=post, client_ms=4100.0,
                    attempts=1, limits=limits)
                if break_arm_ok:
                    record["arm_ok"] = False
                    record["arm_reason"] = "answered-by-unexpected:chroma"
                lines.append(json.dumps(record, ensure_ascii=False))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def rank_of(qid: str) -> float:
        return float(int(qid.split("-")[1]))

    run_dir = Path(os.getenv("TEMP") or "/tmp") / "r59c-sandbox-selfcheck"
    hot_run = run_dir / "sandbox_chroma_hot.jsonl"
    pg_run = run_dir / "sandbox_pgvector.jsonl"
    # 臂标签与答复方必须自洽（chroma-hot 这一臂就是热集答的），否则 S13 会被自己的守卫挡掉
    fake_run(hot_run, "chroma-hot", A.LEG_HOT)
    fake_run(pg_run, "pgvector", A.LEG_PGVECTOR)
    read_hot = read_service_run(hot_run, "chroma-hot", matrix)
    read_pg = read_service_run(pg_run, "pgvector", matrix)
    verdict13 = verify_matrix(corpus, matrix, {"chroma-hot": read_hot, "pgvector": read_pg})
    _pin(pins, "S13 跨件接口：r59c_recall_compare 的产物能直接被 verify 判（两侧 GREEN）",
         verdict13["status"] == "GREEN" and set(read_hot) == set(read_pg)
         and len(read_hot) == len(matrix["cells"]),
         json.dumps({"status": verdict13["status"], "principals": sorted(read_hot)}))

    bad_run = run_dir / "sandbox_bad_arm.jsonl"
    fake_run(bad_run, "pgvector", A.LEG_PGVECTOR, break_arm_ok=True)
    refused14 = ""
    try:
        read_service_run(bad_run, "pgvector", matrix)
    except SystemExit as exc:
        refused14 = str(exc)
    _pin(pins, "S14 跨件接口：臂身份未证实的产物被 verify 拒收（误判 #43 不重演）",
         "臂身份未证实" in refused14, refused14[:120])

    swap_run = run_dir / "sandbox_swapped.jsonl"
    fake_run(swap_run, "pgvector", A.LEG_PGVECTOR)
    swapped = swap_run.read_text(encoding="utf-8").splitlines()
    record = json.loads(swapped[1])
    record["hits"][0]["source"] = "r59c-ops-l3-099.txt"
    record["hits"][0]["key"] = "r59c-ops-l3-099.txt#0"
    record["hits"][0]["classification"] = 3.0
    record["hits"][0]["department"] = "ops"
    swapped[1] = json.dumps(record, ensure_ascii=False)
    swap_run.write_text("\n".join(swapped) + "\n", encoding="utf-8", newline="\n")
    read_swapped = read_service_run(swap_run, "pgvector", matrix)
    verdict15 = verify_matrix(corpus, matrix, {"chroma-hot": read_hot, "pgvector": read_swapped})
    red15 = [item["principal"] for item in verdict15["cells"]
             if not item["j2_no_over_permission"] or not item["j3_matches_exact"]]
    _pin(pins, "S15 跨件反证钉：换掉一发的 top-1 -> 红落在那一档 principal 的 J-2/J-3",
         red15 == [matrix["cells"][0]["principal"]] and verdict15["status"] == "RED",
         json.dumps({"red": red15, "status": verdict15["status"]}))

    # S16/S17 是把一枚真实缺陷逼出来的钉：早先版本在这里直接抛 FileNotFoundError 栈，
    # 于是"上一窗被 Ctrl-C 打断、产物只剩半行"看起来像"工具坏了"，方向差一整条。
    # 现在两样都必须是**点名拒判**（退出码 2），并且**不许有栈**。
    import argparse
    import contextlib
    import io

    def _dump_pair(tag: str) -> tuple:
        matrix_path = run_dir / ("sandbox_matrix_" + tag + ".json")
        corpus_path = run_dir / ("sandbox_corpus_" + tag + ".json")
        _write(matrix_path, json.dumps(matrix, ensure_ascii=False))
        _write(corpus_path, json.dumps(corpus, ensure_ascii=False))
        return matrix_path, corpus_path

    def _run_verify(run_spec: str, tag: str) -> tuple:
        matrix_path, corpus_path = _dump_pair(tag)
        stream = io.StringIO()
        try:
            with contextlib.redirect_stdout(stream):
                code = cmd_verify(argparse.Namespace(
                    matrix=str(matrix_path), corpus=str(corpus_path),
                    run=[run_spec], json=None))
        except BaseException as exc:  # noqa: BLE001 —— 抛出栈就是这两枚钉要抓的红
            return -1, stream.getvalue(), "{0}: {1}".format(type(exc).__name__, exc)
        return code, stream.getvalue(), ""

    missing_run = run_dir / "sandbox_missing.jsonl"
    if missing_run.exists():
        missing_run.unlink()
    code16, out16, stack16 = _run_verify("pgvector=" + str(missing_run), "s16")
    _pin(pins, "S16 读数件不存在 -> 点名哪一臂哪条路径并拒判（退出码 2，不许有栈）",
         code16 == EXIT_PRECONDITION and "pgvector" in out16 and "不存在" in out16 and not stack16,
         json.dumps({"exit": code16, "stack": stack16[:140]}, ensure_ascii=False))

    truncated_run = run_dir / "sandbox_truncated.jsonl"
    # 半行 JSON 这条分支根本走不到 —— 那是一枚**无齿的钉**，教训 #46 正是骂这个。
    good_lines = pg_run.read_text(encoding="utf-8").splitlines()
    last = good_lines[-1]
    _write(truncated_run, "\n".join(good_lines[:-1] + [last[: max(1, len(last) // 3)]]) + "\n")
    code17, out17, stack17 = _run_verify("pgvector=" + str(truncated_run), "s17")
    _pin(pins, "S17 末行只剩半截 JSON -> 拒判 + 给出 --resume 续跑提示（不许有栈）",
         code17 == EXIT_PRECONDITION and "resume" in out17 and not stack17,
         json.dumps({"exit": code17, "stack": stack17[:140]}, ensure_ascii=False))

    red = [item for item in pins if not item["ok"]]
    for item in pins:
        print("[{0}]{1}".format(item["pin"], "  " + item["detail"] if verbose else ""))
    print(json.dumps({"tool": TOOL, "mode": "selfcheck", "offline": True,
                      "corpus_chunks": len(corpus["chunks"]), "pins_total": len(pins),
                      "pins_red": [item["pin"] for item in red],
                      "verdict": "SELF_CHECK_OK" if not red else "SELF_CHECK_RED"},
                     ensure_ascii=False, indent=2))
    return EXIT_OK if not red else EXIT_RED

# ------------------------------------------------------------------------------- CLI

def _write(path: Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def _load_matrix(path: Path) -> dict:
    """矩阵两份形态同源同名：.json 是整块，.jsonl 是逐 principal 一行（便于 diff/grep）。"""
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() == ".jsonl":
        cells = [json.loads(line) for line in text.splitlines() if line.strip()]
        payload = {"schema": (cells[0].get("schema") if cells else None),
                   "corpus_sha": (cells[0].get("corpus_sha") if cells else ""),
                   "cells": cells}
    else:
        payload = json.loads(text)
    if payload.get("schema") != SCHEMA or not payload.get("cells"):
        raise SystemExit("[前置不满足] {0} 的 schema={1!r} 或 cells 为空，本件只认 {2!r}".format(
            path, payload.get("schema"), SCHEMA))
    return payload


def cmd_plan(args) -> int:
    out = Path(args.out)
    corpus = build_corpus(args.chunks, dimension=args.dimension)
    matrix = build_matrix(corpus, top_k=args.top_k, queries=args.queries)
    sql_files = emit_sql(corpus, matrix, database=args.sandbox_db, table=args.table)
    sql_files["probes.sql"] = emit_probe_queries(corpus, matrix, table=args.table,
                                                 ef_search=args.ef_search)
    documents = write_documents(corpus, out / "documents")
    for name, text in sql_files.items():
        _write(out / "sql" / name, text)
    _write(out / "corpus.json", json.dumps(corpus, ensure_ascii=False))
    _write(out / "matrix.jsonl", "\n".join(
        json.dumps(dict(cell, schema=SCHEMA, corpus_sha=matrix["corpus_sha"]),
                   ensure_ascii=False) for cell in matrix["cells"]) + "\n")
    _write(out / "matrix.json", json.dumps(matrix, ensure_ascii=False, indent=2))
    _write(out / "BATCH.md", emit_batch(matrix, sql_files, corpus, database=args.sandbox_db))
    _write(out / "accounts.json", json.dumps(
        {"principals": [dict(spec, password_env="R59C_SANDBOX_PASSWORD_"
                             + spec["label"].upper().replace("-", "_"))
                        for spec in PRINCIPALS],
         "note": "口令只在窗内注入，永不进版本库；department 决定谓词（生产读路径不接表单值）"},
        ensure_ascii=False, indent=2))
    print(json.dumps({"out": str(out), "chunks": len(corpus["chunks"]), "documents": documents,
                      "corpus_sha": matrix["corpus_sha"], "top_k": args.top_k,
                      "queries": args.queries, "sandbox_db": args.sandbox_db,
                      "selective_principals": sum(1 for cell in matrix["cells"]
                                                  if cell["j1_selective"]),
                      "sql_files": sorted(sql_files),
                      "executed": "NOTHING（本件只出料；DDL/DML 需业主批准）"},
                     ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_verify(args) -> int:
    matrix_path = Path(args.matrix)
    # 与 --run 同一枚纪律：料件不在 = 前置不满足，点名路径拒判，不许抛栈。
    # （plan 被沙盒守卫拒出料时目录里就是空的，这一支迟早会有人撞上。）
    if not matrix_path.is_file():
        print("[前置不满足] 判据表不存在：{0} —— 先跑 plan 出料（守卫拒出料时目录里就是没有）".format(matrix_path))
        return EXIT_PRECONDITION
    try:
        matrix = _load_matrix(matrix_path)
    except (OSError, ValueError) as exc:  # 含 JSONDecodeError
        print("[前置不满足] 判据表读不动（{0}: {1}）：{2}".format(type(exc).__name__, exc, matrix_path))
        return EXIT_PRECONDITION
    corpus_path = Path(args.corpus) if args.corpus else matrix_path.with_name("corpus.json")
    if not corpus_path.is_file():
        print("[前置不满足] 找不到语料件 {0}（verify 要知道每块的 class/dept 才能判越权）".format(corpus_path))
        return EXIT_PRECONDITION
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("schema") != SCHEMA:
        print("[前置不满足] {0} 的 schema 不对".format(corpus_path))
        return EXIT_PRECONDITION
    if corpus_sha(corpus) != matrix.get("corpus_sha"):
        print("[前置不满足] 语料指纹与矩阵不符（{0} != {1}）：判据表量的不是这份语料，拒判"
              .format(corpus_sha(corpus), matrix.get("corpus_sha")))
        return EXIT_PRECONDITION
    readings = {}
    for spec in args.run or []:
        if "=" not in spec:
            print("[用法] --run 的形状是 arm=path（例：--run pgvector=%TEMP%/r59c_pg.jsonl）")
            return EXIT_PRECONDITION
        arm, path = spec.split("=", 1)
        # 读数文件缺失/半行不是"零读数"，是前置不满足：点名的那一句必须说清是哪一臂哪个路径，
        # 更不能抛栈 —— 上一窗 Ctrl-C 之后这里多半只剩半行 JSON，栈会把人带去查错方向。
        if not Path(path).is_file():
            print("[前置不满足] 臂 {0} 的读数文件不存在：{1} —— 这一臂没有读数，判不了"
                  .format(arm, path))
            return EXIT_PRECONDITION
        try:
            if Path(path).suffix.lower() == ".csv":
                readings[arm] = read_probe_csv_run(Path(path), matrix)
            else:
                readings[arm] = read_service_run(Path(path), arm, matrix)
        except SystemExit as exc:
            print(str(exc))
            return EXIT_PRECONDITION
        except (OSError, ValueError) as exc:  # 含 json.JSONDecodeError（ValueError 的子类）
            print("[前置不满足] 臂 {0} 的读数读不动（{1}: {2}）：{3}"
                  .format(arm, type(exc).__name__, exc, path))
            print("              若这一窗是被 Ctrl-C 中断的，产物是 append-only，用 "
                  "r59c_recall_compare.py collect --arm {0} --out {1} --resume 续跑完再判"
                  .format(arm, path))
            return EXIT_PRECONDITION
    verdict = verify_matrix(corpus, matrix, readings)
    if args.json:
        _write(Path(args.json), json.dumps(verdict, ensure_ascii=False, indent=2))
    print(json.dumps({key: verdict[key] for key in
                      ("status", "why", "arms", "principals_total", "principals_selective",
                       "corpus_sha")}, ensure_ascii=False, indent=2))
    for cell in verdict["cells"]:
        print("  {principal:<16} j1_selective={j1_selective} j2_no_over={j2_no_over_permission} "
              "j3_exact={j3_matches_exact} j4_cross={j4_cross_arm_jaccard} share={admitted_share}"
              .format(**cell))
    if verdict["status"] == "GREEN":
        return EXIT_OK
    return EXIT_PRECONDITION if verdict["status"] == "NOT_MEASURED" else EXIT_RED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=TOOL, description="R59c 判据 ③：沙盒语料 + 谓词判据 + 批单")
    sub = parser.add_subparsers(dest="command")
    plan = sub.add_parser("plan", help="出料：语料/矩阵/SQL 批单/探针（零执行）")
    plan.add_argument("--out", required=True)
    plan.add_argument("--chunks", type=int, default=72)
    plan.add_argument("--dimension", type=int, default=VECTOR_DIMENSION)
    plan.add_argument("--top-k", type=int, default=5)
    plan.add_argument("--queries", type=int, default=12)
    plan.add_argument("--sandbox-db", default=SANDBOX_DB_DEFAULT)
    plan.add_argument("--table", default=TABLE)
    #: 缺省不再是本件自带的那一档，而是现场跟随生产读腿的唯一真源（R393 判据①）：
    #: 自带的那一档是 pgvector 的出厂档，量出来的不是生产那一档。
    plan.add_argument("--ef-search", type=int, default=None,
                      help="显式把探针批的 HNSW 候选宽度钉成这一档，批头会写明它是人为"
                           "指定的，不可与生产口径混读；不填 = 现场跟随 " + TRUE_SOURCE)
    plan.set_defaults(func=cmd_plan)
    check = sub.add_parser("verify", help="判 J-1〜J-5：两侧读数 vs 精确解 vs 允许集")
    check.add_argument("--matrix", required=True)
    check.add_argument("--corpus", default=None)
    check.add_argument("--run", action="append",
                       help="arm=path；path 可以是 r59c_recall_compare 的 JSONL 或 psql 探针 CSV")
    check.add_argument("--json", default=None)
    check.set_defaults(func=cmd_verify)
    self_ = sub.add_parser("selfcheck", help="离线自校（零库、零容器、零模型）")
    self_.add_argument("--verbose", action="store_true")
    self_.set_defaults(func=lambda args: run_selfcheck(verbose=args.verbose))
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_PRECONDITION
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())