#!/usr/bin/env python
"""R59 判据①：把 P3 影子读对比做成**可机读的读数**。

从头到尾只读：连上 PostgreSQL 第一件事是把会话设成只读；Chroma 侧只 get / query；
本脚本不写一行业务数据、不跑一枚迁移、不建一枚索引、不动一个 collection。

为什么躺在 scripts/compare_vector_recall.py 旁边而不是改它（那张单子把它划成禁碰件）：
它已经回答"两侧排序合不合"，但逐题只印一行，而且它没有能力说出本单最需要的那句话——
"PG 腿今天到底读没读到"。这里补的正是两样：

  1. 能拿去对差的数：逐题集合重合度、名次位移、两侧各走多远才拿到第一名；
  2. 🔴 "PG 交回 0 条" 与 "PG 根本没读到" 分家：产物里两个字段、退出码两个值。
     R158 那 24/135 题就是会被粗心工具印成"两侧一致"的形状——两个空列表相等。

--pg-mode：
  live        SELECT ... ORDER BY embedding <op> %s::vector，打真库 chunk_vectors。
  exact-knn   同一套算式在 Chroma 快照那批向量上暴力全扫描。这是 PG 腿的**估算**，
              产物里 state 字段就地写着它是估算。凭据只有一条且是量出来的：跟进单 80 节
              记 pgvector 的 top-5 与 numpy 全库暴力算逐位相同。用它判方向，
              不许拿它翻默认值。
  auto        库答得上来走 live，答不上来走 exact-knn，走哪条写进产物。
              默认值不再是它：默认 live，见 parse_args 里 --pg-mode 那段注释。
  off         只读 Chroma 腿。

退出码（不可合并，合并就是说谎）：
  0 PG 腿真读到了（live），且逐题 top-k 集合全一致
  1 PG 腿真读到了（live），且至少一题不一致 —— 这是正常结论，交人判读
  2 前置不满足，不出任何召回结论
  3 PG 腿没读到（连不上 / 没迁移 / 只走了估算腿）：这份读数只有半张脸
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SIBLING = ROOT / "scripts" / "compare_vector_recall.py"
DEFAULT_FIXTURES = (
    "tests/fixtures/business_evaluation_30.jsonl",
    "tests/fixtures/business_evaluation_100.jsonl",
)
#: 两侧对同一个几何量给的不是同一个数：R157 实测 Chroma 对 l2 交回**平方**欧氏距离，
#: pgvector 的 <-> 交回欧氏距离。换算只影响"走了多远"那一栏，不影响名次。
CHROMA_L2_IS_SQUARED = True
EXIT_MATCHED = 0
EXIT_DIFFERS = 1
EXIT_PRECONDITION = 2
EXIT_PG_NOT_ASKED = 3


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="R59 判据①：Chroma vs PGVector 逐题召回读数（只读，不写一行业务数据）")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "") or None)
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "./chroma_db"))
    parser.add_argument("--collection",
                        default=os.getenv("CHROMA_COLLECTION", "enterprise_docs"))
    parser.add_argument("--vector-table", default="chunk_vectors")
    parser.add_argument("--k", type=int, default=5)
    #: 默认值从 auto 改成 live（fail closed）。这条默认就是上一份读数作废的根因之一：
    #: 真库连不上时它不报错，而是把 PG 腿悄悄换成估算腿，产物看着一应俱全、其实只有一条腿，
    #: 而那个退出的 3 号码很容易被读成"跑完了"。估算腿仍然保留，但必须显式要。
    parser.add_argument("--pg-mode", choices=("auto", "live", "exact-knn", "off"),
                        default="live")
    parser.add_argument("--no-pg-exact", dest="pg_exact", action="store_false",
                        help="不跑真库精确 top-k（判据③量 HNSW 近似性用；默认跑）")
    parser.add_argument("--pg-ef-search", type=int, default=0,
                        help="把 hnsw.ef_search 设成这个值再跑 live 腿；0 = 用库里的默认")
    parser.add_argument("--no-chroma-exact", dest="chroma_exact", action="store_false",
                        help="不在 Chroma 快照上算精确 top-k（判据②的归因腿；默认跑）")
    #: 生产读路径恒带权限谓词（app/rag/filters.py 那两份形状）。不带 where 的读数只能证明
    #: "不过滤时两侧一致"，切读要落地的那一条是带过滤的，所以这一格必须能量。
    parser.add_argument("--where-json", default="",
                        help='下推给两侧向量库的权限谓词，Chroma 形状 JSON；空 = 不过滤')
    parser.add_argument("--fixture", action="append", default=None,
                        help="题集 jsonl，可重复；默认用仓内两份评测集")
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 题；0 = 全部")
    parser.add_argument("--out", default=None, help="机读产物（JSON）落这里")
    parser.add_argument("--md", default=None, help="人读表（Markdown）落这里")
    return parser.parse_args(argv)


def load_sibling():
    """按路径 import compare_vector_recall：距离算符口径全仓只允许存在一份。"""
    if not SIBLING.exists():
        raise SystemExit("[前置不满足] 找不到 " + str(SIBLING))
    spec = importlib.util.spec_from_file_location("r59_compare_vector_recall", SIBLING)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git_revision() -> str:
    #: 容器里没有 .git，读数照样要钉得住 revision：由调用方用 R59_REVISION 带进来。
    explicit = os.getenv("R59_REVISION", "").strip()
    if explicit:
        return explicit[:40]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=20)
    except Exception:
        return "unknown"
    return (out.stdout or "").strip()[:40] or "unknown"


# ------------------------------------------------------------------ 只读：把向量读齐

def read_metadatas(collection, *, page_size: int = 200):
    """整库元数据读进内存，给"带过滤"那一腿在快照上算精确 top-k 时当掩码用。只 get。"""
    total = int(collection.count())
    out, offset = {}, 0
    while offset < total:
        page = collection.get(limit=page_size, offset=offset, include=["metadatas"])
        page_ids = [str(item) for item in ((page or {}).get("ids") or [])]
        page_meta = (page or {}).get("metadatas") or [None] * len(page_ids)
        if not page_ids:
            return {}
        out.update({vector_id: (meta or {})
                    for vector_id, meta in zip(page_ids, page_meta)})
        offset += len(page_ids)
    return out if len(out) == total else {}


def read_matrix(collection, *, page_size: int = 200):
    """整库向量 + id 读进内存，给 exact-knn 那一腿。只 get，不 query，不写。

    分页读满是要对数的：读回来的人数与 collection.count() 不等就直接判前置不满足，
    而不是悄悄少几行继续算。返回 (ids, matrix, 空串) 或 ([], [], 原因)。
    """
    total = int(collection.count())
    ids, rows, offset = [], [], 0
    while offset < total:
        page = collection.get(limit=page_size, offset=offset, include=["embeddings"])
        page_ids = [str(item) for item in ((page or {}).get("ids") or [])]
        page_rows = (page or {}).get("embeddings")
        page_rows = [] if page_rows is None else [[float(v) for v in r] for r in page_rows]
        if not page_ids:
            return [], [], "第 %d 页起读不到任何行，分页没读满" % offset
        if len(page_ids) != len(page_rows):
            return [], [], "id 数与向量行数不等（%d / %d）" % (len(page_ids), len(page_rows))
        ids.extend(page_ids)
        rows.extend(page_rows)
        offset += len(page_ids)
    if len(ids) != total:
        return [], [], "读到 %d 枚，count() 说 %d 枚" % (len(ids), total)
    if len(set(ids) if ids else set()) != len(ids):
        return [], [], "读回来的 id 有重复"
    widths = {len(row) for row in rows}
    if len(widths) != 1 or 0 in widths:
        return [], [], "宽度不齐：%s" % sorted(widths)
    return ids, rows, ""


def pg_live_topk(connection, *, vector_table: str, operator: str, literal: str, k: int,
                 clause: str = "", clause_params=()):
    """live 腿：真库 chunk_vectors 上的 top-k。表名与算符都过白名单，不做字符串注入。

    ``clause`` 只允许由 app/rag/pg_store.sql_scope_filter 交回 —— 也就是生产读腿将要发的那
    同一段 SQL。在这里另抄一份"看着一样的 WHERE"就是量具与实现两套口径，白测。
    """
    rows = connection.execute(
        "SELECT vector_id, embedding " + operator + " %s::vector AS distance"
        " FROM " + vector_table +
        (" WHERE " + clause if clause else "") +
        " ORDER BY embedding " + operator + " %s::vector LIMIT %s",
        (literal, *clause_params, literal, k),
    ).fetchall()
    out = []
    for row in rows:
        vector_id = row["vector_id"] if isinstance(row, dict) else row[0]
        distance = row["distance"] if isinstance(row, dict) else row[1]
        out.append((str(vector_id), float(distance)))
    return out


def pg_exact_topk(connection, *, vector_table: str, operator: str, literal: str, k: int,
                  clause: str = "", clause_params=()):
    """真库上的**精确** top-k：临时关掉索引扫描，让 pgvector 走全表顺序扫。

    这一腿只为判据③存在：同一条连接、同一批向量、同一个算符，只把 HNSW 挪开，量出来的
    就是「近似索引会不会改名次」这一格本身，不用拿别的工具的身份来替它作证。
    进出都显式复位，不给下一题留脏设置。
    """
    connection.execute("SET enable_indexscan = off")
    connection.execute("SET enable_indexonlyscan = off")
    try:
        return pg_live_topk(connection, vector_table=vector_table, operator=operator,
                            literal=literal, k=k, clause=clause,
                            clause_params=clause_params)
    finally:
        connection.execute("SET enable_indexscan = default")
        connection.execute("SET enable_indexonlyscan = default")


def pg_vector_map(connection, *, vector_table: str) -> dict:
    """把真库全量向量读进内存，只为逐位对一次「两侧存的是不是同一批数」。

    只 SELECT 两列。镜像里没装 pgvector 的 Python 编解码包，embedding 以文本回来，
    就按文本解；解不动的行记进 unreadable，不蒙过去。
    """
    rows = connection.execute(
        "SELECT vector_id, embedding FROM " + vector_table).fetchall()
    out, unreadable = {}, []
    for row in rows:
        vector_id = str(row["vector_id"] if isinstance(row, dict) else row[0])
        raw = row["embedding"] if isinstance(row, dict) else row[1]
        try:
            out[vector_id] = (json.loads(raw) if isinstance(raw, str)
                              else [float(value) for value in raw])
        except Exception as exc:
            unreadable.append({"id": vector_id,
                               "reason": type(exc).__name__ + " " + str(exc)[:120]})
    return {"vectors": out, "unreadable": unreadable[:10],
            "unreadable_count": len(unreadable)}


def compare_vector_bodies(chroma_ids, chroma_matrix, pg_map: dict) -> dict:
    """逐位比两侧存下来的向量：同一批数就该完全相等，差一个 float 也要写进报告。"""
    facts = {"compared": 0, "identical": 0, "max_abs_diff": 0.0, "mean_abs_diff": None,
             "differing_ids": [], "missing_in_pg": [],
             "unreadable_in_pg": pg_map.get("unreadable_count", 0),
             "chroma_total": len(chroma_ids)}
    diff_sum = 0.0
    stored = pg_map["vectors"]
    for position, vector_id in enumerate(chroma_ids):
        left = chroma_matrix[position]
        right = stored.get(vector_id)
        if right is None:
            facts["missing_in_pg"].append(vector_id)
            continue
        if len(left) != len(right):
            facts["differing_ids"].append(vector_id)
            continue
        facts["compared"] += 1
        diff = max(abs(float(a) - float(b)) for a, b in zip(left, right))
        diff_sum += sum(abs(float(a) - float(b)) for a, b in zip(left, right))
        if diff == 0.0:
            facts["identical"] += 1
        else:
            facts["max_abs_diff"] = max(facts["max_abs_diff"], diff)
            if len(facts["differing_ids"]) < 20:
                facts["differing_ids"].append(vector_id)
    facts["mean_abs_diff"] = (None if not facts["compared"]
                              else round(diff_sum / (facts["compared"] * len(left)), 12))
    facts["all_identical"] = bool(facts["identical"] == len(chroma_ids)
                                  and facts["compared"] == len(chroma_ids))
    facts["missing_in_pg"] = facts["missing_in_pg"][:20]
    return facts


def masked_view(ids, array, metadatas, where):
    """按元数据谓词裁一份 (ids, array) 视图：让"快照上的精确 top-k"也带上同一份过滤。

    谓词判定用的是 app/rag/retriever.metadata_matches —— 热集那条腿今天就是拿它裁的，
    量具不另写一份匹配规则。元数据读不全就交回 None：宁可这一腿空着，也不用一份
    悄悄少了几百行的掩码去算"两侧一致"。
    """
    if where is None:
        return ids, array
    from app.rag.retriever import metadata_matches

    if not metadatas or len(metadatas) != len(ids):
        return None, None
    import numpy

    keep = [position for position, vector_id in enumerate(ids)
            if metadata_matches(metadatas[vector_id], where)]
    if not keep:
        return [], numpy.empty((0, array.shape[1]), dtype=array.dtype)
    picked = numpy.asarray(keep, dtype=numpy.int64)
    return [ids[position] for position in keep], array[picked]


def array_topk(ids, array, query, *, k: int):
    """numpy 在内存快照上精确算 top-k（l2 平方距离；比名次时平方不改顺序）。

    array 为 None（numpy 取不到或显式关掉）就交回 None：这一腿是归因用的，
    取不到就明写取不到，不退纯 Python 全库慢慢磨。
    """
    if array is None or query is None:
        return None
    import numpy
    #: 差值按 float32 取（与两侧存储位宽一致），但平方和用 float64 累加：768 维在 float32
    #: 下累加会引入 ~1e-6 的相对误差，比这轮要量的语料差（2e-7）还大，会把归因腿自己搞脏。
    deltas = (array - query).astype(numpy.float64)
    squared = (deltas * deltas).sum(axis=1)
    order = sorted(range(len(ids)),
                   key=lambda position: (float(squared[position]), ids[position]))
    return [(ids[position], float(squared[position])) for position in order[:k]]


def pg_engine_facts(connection, *, tool, vector_table: str) -> dict:
    """把「这一腿踩在哪套口径上」照抄成真库原文：判据③要的是取证，不是转述。"""
    facts = {"scope_row": None, "indexes": [], "hnsw_ef_search": "", "errors": {}}
    try:
        cursor = connection.execute(
            "SELECT schema_version, embedding_model, dimension, distance_function,"
            " hnsw_m, hnsw_ef_construction FROM vector_scope WHERE schema_version = %s",
            (tool.pg_store.VECTOR_SCHEMA_VERSION,))
        row = cursor.fetchone()
        #: 按列名取，不用 dict(row)：这条连接回来的行是元组，dict() 会把整行当成
        #: 键值对序列去解，当场 TypeError —— 取证格坏掉的时候读的人以为口径没了。
        names = [getattr(item, "name", item[0]) for item in (cursor.description or [])]
        facts["scope_row"] = ({name: tool._row(row, name, position)
                              for position, name in enumerate(names)}
                              if row is not None else None)
    except Exception as exc:
        facts["errors"]["scope_row"] = type(exc).__name__ + " " + str(exc)[:160]
    try:
        rows = connection.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s ORDER BY 1",
            (vector_table,)).fetchall()
        facts["indexes"] = [str(row["indexdef"] if isinstance(row, dict) else row[1])
                            for row in rows]
    except Exception as exc:
        facts["errors"]["indexes"] = type(exc).__name__ + " " + str(exc)[:160]
    try:
        facts["hnsw_ef_search"] = str(tool._scalar(
            connection.execute("SHOW hnsw.ef_search").fetchone()))
    except Exception as exc:
        facts["errors"]["hnsw_ef_search"] = type(exc).__name__ + " " + str(exc)[:160]
    return facts


def exact_knn_topk(ids, matrix, query, *, metric: str, k: int):
    """估算腿：同一套算式在全库向量上暴力算 top-k。

    排序键 (距离, id) 把并列钉死成可复现顺序：pgvector 遇同距不保证稳定序，而这一栏要
    拿去对差，不许每跑一次换一个样。
    """
    query_norm = math.sqrt(sum(value * value for value in query))
    scored = []
    for vector_id, row in zip(ids, matrix):
        if metric == "cosine":
            norm = math.sqrt(sum(value * value for value in row))
            if not norm or not query_norm:
                continue
            distance = 1.0 - sum(a * b for a, b in zip(query, row)) / (norm * query_norm)
        elif metric == "inner_product":
            distance = -sum(a * b for a, b in zip(query, row))
        else:
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(query, row)))
        scored.append((distance, vector_id))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [(vector_id, distance) for distance, vector_id in scored[:k]]



# ------------------------------------------------------------- 名次与距离怎么比

def to_comparable(metric: str, side: str, value):
    """把一侧的距离换算到另一侧的口径，只为"走了多远"那一栏可读。"""
    if value is None:
        return None
    value = float(value)
    if metric == "l2" and side == "chroma" and CHROMA_L2_IS_SQUARED:
        value = math.sqrt(max(value, 0.0))
    return round(value, 6)


def rank_map(ids):
    return {vector_id: position + 1 for position, vector_id in enumerate(ids)}


def kendall_tau(left, right):
    """共有元素上的 Kendall tau（1 = 同序）。共有少于两枚时不算，交回 None。"""
    shared = set(left) & set(right)
    ordered = [item for item in left if item in shared]
    if len(ordered) < 2:
        return None
    right_rank = rank_map([item for item in right if item in shared])
    concordant = discordant = 0
    for a_index in range(len(ordered)):
        for b_index in range(a_index + 1, len(ordered)):
            delta = right_rank[ordered[a_index]] - right_rank[ordered[b_index]]
            if delta == 0:
                continue
            #: 左序里 a 在 b 前，右序里也在前才算同序对，即 right_rank[a] < right_rank[b]。
            #: 判反会让两列完全相同时交回 -1.0，而那一格本该是 1.0。
            if delta < 0:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return None if not total else round((concordant - discordant) / total, 4)


def first_difference(left, right):
    """第一处名次不同的**1 基**名次；两侧逐位相同才返回 None。"""
    for position in range(max(len(left), len(right))):
        a = left[position] if position < len(left) else None
        b = right[position] if position < len(right) else None
        if a != b:
            return position + 1
    return None


def compare_question(*, source, question_id, question, chroma, pg, k, metric,
                     pg_exact=None, chroma_exact=None, query_sha="") -> dict:
    """一题两腿 -> 一行可机读读数：集合重合度、名次位移、两侧各走多远。"""
    chroma_ids = [item[0] for item in chroma]
    pg_ids = [item[0] for item in pg]
    #: pg_exact=None 意思是这一腿根本没跑，读数里就留 None；拿空列表冒充「一致」是说谎。
    pg_exact_ids = None if pg_exact is None else [item[0] for item in pg_exact]
    chroma_exact_ids = (None if chroma_exact is None
                        else [item[0] for item in chroma_exact])
    chroma_set, pg_set = set(chroma_ids), set(pg_ids)
    union, shared = chroma_set | pg_set, chroma_set & pg_set
    chroma_rank, pg_rank = rank_map(chroma_ids), rank_map(pg_ids)
    shifts = [abs(chroma_rank[item] - pg_rank[item]) for item in sorted(shared)]
    return {
        "source": source,
        "id": question_id,
        "question": question,
        #: 题向量指纹：跨次复跑先对这一栏，才知道答案变化来自引擎还是来自 embedding。
        "query_sha": query_sha,
        "k": k,
        "chroma_ids": chroma_ids,
        "pg_ids": pg_ids,
        "pg_exact_ids": pg_exact_ids,
        "index_vs_exact_same_set": (None if pg_exact_ids is None
                                    else set(pg_exact_ids) == set(pg_ids)),
        "index_vs_exact_first_diff_rank": (None if pg_exact_ids is None
                                           else first_difference(pg_ids, pg_exact_ids)),
        "chroma_exact_ids": chroma_exact_ids,
        "chroma_index_vs_exact_same_set": (None if chroma_exact_ids is None
                                           else set(chroma_exact_ids) == set(chroma_ids)),
        "exact_sides_same_set": (None if (chroma_exact_ids is None or pg_exact_ids is None)
                                 else set(chroma_exact_ids) == set(pg_exact_ids)),
        "exact_sides_first_diff_rank": (None if (chroma_exact_ids is None
                                                 or pg_exact_ids is None)
                                        else first_difference(chroma_exact_ids,
                                                              pg_exact_ids)),
        "chroma_rows": len(chroma_ids),
        "pg_rows": len(pg_ids),
        "overlap": len(shared),
        "overlap_ratio": round(len(shared) / k, 4),
        "jaccard": round(len(shared) / len(union), 4) if union else None,
        "same_set": bool(chroma_set == pg_set),
        "same_order": bool(chroma_ids == pg_ids),
        "first_diff_rank": first_difference(chroma_ids, pg_ids),
        "mean_abs_rank_shift": round(statistics.fmean(shifts), 4) if shifts else None,
        "max_abs_rank_shift": max(shifts) if shifts else None,
        "kendall_tau": kendall_tau(chroma_ids, pg_ids),
        "chroma_only_ids": sorted(chroma_set - pg_set),
        "pg_only_ids": sorted(pg_set - chroma_set),
        "chroma_top1_comparable": to_comparable(metric, "chroma",
                                                chroma[0][1] if chroma else None),
        "pg_top1_comparable": to_comparable(metric, "pg", pg[0][1] if pg else None),
        "chroma_farthest_comparable": to_comparable(metric, "chroma",
                                                    chroma[-1][1] if chroma else None),
        "pg_farthest_comparable": to_comparable(metric, "pg",
                                                pg[-1][1] if pg else None),
        #: 两枚 0 是不同的两件事，分开存字段，不许共用一个"0 命中"。
        "chroma_zero_rows": not chroma_ids,
        "pg_zero_rows": not pg_ids,
    }


def summarize(rows: list) -> dict:
    """把逐题读数聚成几个能一眼判方向的数。"""
    if not rows:
        return {"questions": 0}
    k = rows[0]["k"]
    overlaps = [item["overlap"] for item in rows]
    jaccards = [item["jaccard"] for item in rows if item["jaccard"] is not None]
    shifts = [item["mean_abs_rank_shift"] for item in rows
              if item["mean_abs_rank_shift"] is not None]
    worst = [item["max_abs_rank_shift"] for item in rows
             if item["max_abs_rank_shift"] is not None]
    taus = [item["kendall_tau"] for item in rows if item["kendall_tau"] is not None]
    return {
        "questions": len(rows),
        "same_set": sum(1 for item in rows if item["same_set"]),
        "same_order": sum(1 for item in rows if item["same_order"]),
        "differing_set": sum(1 for item in rows if not item["same_set"]),
        "mean_overlap": round(statistics.fmean(overlaps), 4),
        "mean_overlap_ratio": round(statistics.fmean(overlaps) / k, 4),
        "mean_jaccard": round(statistics.fmean(jaccards), 4) if jaccards else None,
        "median_jaccard": round(statistics.median(jaccards), 4) if jaccards else None,
        "questions_full_overlap": sum(1 for item in overlaps if item == k),
        "questions_zero_overlap": sum(1 for item in overlaps if item == 0),
        "mean_abs_rank_shift": round(statistics.fmean(shifts), 4) if shifts else None,
        "max_abs_rank_shift": max(worst) if worst else None,
        "mean_kendall_tau": round(statistics.fmean(taus), 4) if taus else None,
        "chroma_zero_rows": sum(1 for item in rows if item["chroma_zero_rows"]),
        "pg_zero_rows": sum(1 for item in rows if item["pg_zero_rows"]),
        #: 只有一腿交回 0 条的题。R158 那 24/135 就是其中第一格，也是 H20 的来由。
        "chroma_only_zero": sum(1 for item in rows
                                if item["chroma_zero_rows"] and not item["pg_zero_rows"]),
        "pg_only_zero": sum(1 for item in rows
                            if item["pg_zero_rows"] and not item["chroma_zero_rows"]),
        #: HNSW 索引腿 vs 同库精确腿。这一格与「两个引擎不同」无关，只回答近似性改不改名次。
        "pg_exact_leg": bool(rows and rows[0].get("pg_exact_ids") is not None),
        "pg_index_vs_exact_same_set": sum(1 for item in rows
                                          if item.get("index_vs_exact_same_set")),
        "pg_index_vs_exact_mismatch_ids": [item["id"] for item in rows
                                           if item.get("index_vs_exact_same_set") is False][:50],
        "chroma_exact_leg": bool(rows and rows[0].get("chroma_exact_ids") is not None),
        "chroma_index_vs_exact_same_set": sum(1 for item in rows
                                              if item.get("chroma_index_vs_exact_same_set")),
        "chroma_index_vs_exact_mismatch_ids": [
            item["id"] for item in rows
            if item.get("chroma_index_vs_exact_same_set") is False][:50],
        "exact_sides_same_set": sum(1 for item in rows if item.get("exact_sides_same_set")),
        "exact_sides_mismatch_ids": [item["id"] for item in rows
                                     if item.get("exact_sides_same_set") is False][:50],
    }



# ------------------------------------------- PG 腿状态：先问它到底答不答得上来

def probe_pg(*, tool, database_url, vector_table, chroma_space):
    """连库 + 读 0010 登记的口径。任何一步不成都不抛，交回 status 由调用方分流。

    status["state"] 四值：
      read_live        真库读到了，可以出召回结论
      cannot_ask       连不上 / 没迁移 / 表不在 —— 这不是"0 条"，是"没读到"
      scope_mismatch   读到了但两侧算符不同，排序天然不可比，不出召回结论
    原因里只放异常类名与截断后的消息；连接串一个字符都不进产物。
    """
    status = {"state": "cannot_ask", "reason": "", "dimension": None,
              "embedding_model": "", "distance_function": "", "column_type": "",
              "drift": {}}
    if not database_url:
        status["reason"] = "DATABASE_URL 未设置，PG 腿无从可问"
        return status, None, None
    try:
        connection = tool.connect_read_only(database_url)
    except SystemExit as exc:
        status["reason"] = "连接被拒（前置不满足）：" + str(exc)[:200]
        return status, None, None
    except Exception as exc:
        status["reason"] = "连不上：" + type(exc).__name__ + " " + str(exc)[:160]
        return status, None, None
    try:
        scope = tool.read_scope(connection, vector_table)
    except SystemExit as exc:
        status["reason"] = "口径前置不满足：" + str(exc)[:200]
        connection.close()
        return status, None, None
    except Exception as exc:
        status["reason"] = "口径读不出：" + type(exc).__name__ + " " + str(exc)[:160]
        connection.close()
        return status, None, None
    status["dimension"] = scope["dimension"]
    status["embedding_model"] = scope["embedding_model"]
    status["distance_function"] = scope["distance_function"]
    status["column_type"] = scope["column_type"]
    if tool.canonical_distance(scope["distance_function"]) != chroma_space:
        status["state"] = "scope_mismatch"
        status["reason"] = ("vector_scope 记的距离=" + scope["distance_function"]
                            + "，Chroma 实测=" + chroma_space + "，两侧排序天然不同")
        connection.close()
        return status, None, None
    status["state"] = "read_live"
    return status, connection, scope


def pg_drift(*, tool, connection, collection, vector_table, scope) -> dict:
    """语料级差集：镜像覆盖率先钉住，不然逐题读数量出来的是"没同步"而不是"两库不同"。"""
    try:
        drift = tool.corpus_drift(connection, collection, vector_table=vector_table,
                                  scope=scope)
    except Exception as exc:
        return {"readable": False,
                "reason": type(exc).__name__ + " " + str(exc)[:160]}
    return {
        "readable": True,
        "pg_vectors": drift["pg_vectors"],
        "chroma_vectors": drift["chroma_vectors"],
        "only_in_pg": len(drift["only_in_pg"]),
        "only_in_chroma": len(drift["only_in_chroma"]),
        "only_in_pg_ids": sorted(drift["only_in_pg"])[:50],
        "only_in_chroma_ids": sorted(drift["only_in_chroma"])[:50],
        "wrong_width": len(drift["wrong_width"]),
        "all_zero_rows": drift["all_zero_rows"],
        "index_version_id_null": drift["index_version_id_null"],
        "chunks_rows": drift["chunks_rows"],
        "chunks_with_backfilled_embedding": drift["chunks_with_backfilled_embedding"],
    }



# --------------------------------------------------------------- 主流程

def build_result(args) -> tuple:
    """跑一遍，交回 (result, exit_code)。本函数一行都不写库。"""
    tool = load_sibling()
    vector_table = tool._safe_table(args.vector_table)
    k = int(args.k)
    if k <= 0:
        raise SystemExit("[前置不满足] --k 必须是正整数，拿到 " + str(args.k))

    collection = tool.open_chroma(args.chroma_dir, args.collection)
    space, u1 = tool.resolve_chroma_distance(collection)
    if not space:
        print("[前置不满足] Chroma 侧距离算符测不出来：" + str(u1.get("reason", "")))
        return None, EXIT_PRECONDITION

    chroma_ids, chroma_matrix, matrix_error = read_matrix(collection)
    if matrix_error:
        raise SystemExit("[前置不满足] Chroma 向量读不齐：" + matrix_error)

    questions = tool.load_questions(args.fixture or list(DEFAULT_FIXTURES))
    if args.limit:
        questions = questions[:args.limit]
    if not questions:
        raise SystemExit("[前置不满足] 题集是空的")

    # 前置第 4 条：题向量必须由生产侧同一枚 embedding 模型产出（R22 口径）。
    from app.rag.retriever import OllamaEmbeddings
    embedder = OllamaEmbeddings()

    pg_status, connection, scope = ({"state": "off", "reason": "--pg-mode=off"}, None, None)
    if args.pg_mode != "off":
        pg_status, connection, scope = probe_pg(
            tool=tool, database_url=args.database_url or os.getenv("DATABASE_URL", ""),
            vector_table=vector_table, chroma_space=space)
        if pg_status["state"] == "scope_mismatch":
            return {"meta": {"distance": {"chroma_space": space}, "pg_leg": pg_status},
                    "error": pg_status["reason"]}, EXIT_PRECONDITION
        if pg_status["state"] != "read_live":
            if args.pg_mode == "live":
                return {"meta": {"pg_leg": pg_status}, "error": pg_status["reason"]}, \
                    EXIT_PG_NOT_ASKED
            # auto / exact-knn：估一条腿出来，并在产物里写明它是估算。
            pg_status["state"] = "estimated_exact_knn"
            pg_status["estimate_warrant"] = (
                "跟进单 80 节实测：pgvector 的 top-5 与 numpy 全库暴力算逐位相同；"
                "本读数用它代替真库读，只用于判方向。")
    elif args.pg_mode == "off":
        pass

    corpus_before = {}
    if pg_status["state"] == "read_live":
        pg_status["drift"] = pg_drift(tool=tool, connection=connection,
                                      collection=collection, vector_table=vector_table,
                                      scope=scope)
        pg_status["engine"] = pg_engine_facts(connection, tool=tool,
                                              vector_table=vector_table)
        if args.pg_ef_search:
            connection.execute("SET hnsw.ef_search = %s", (int(args.pg_ef_search),))
            pg_status["engine"]["hnsw_ef_search_applied"] = str(int(args.pg_ef_search))
        if pg_status["drift"].get("only_in_pg") or pg_status["drift"].get("only_in_chroma"):
            print("[警告] 镜像有差集，逐题读数量到的是\"没同步\"与\"两库不同\"的混合体")

    corpus_before["chroma_vectors"] = len(chroma_ids)
    corpus_before["pg_vectors"] = (pg_status.get("drift") or {}).get("pg_vectors")

    operator = tool.DISTANCE_OPERATORS[space]
    #: 归因腿：在 Chroma 快照上精确算一遍 top-k，才分得清不一致是「Chroma 自己的近似索引」
    #: 还是「两侧存的数本来就不一样」。少了这一腿，下面那些分歧题就只能猜，不许猜。
    chroma_array = None
    try:
        import numpy
        if args.chroma_exact:
            chroma_array = numpy.asarray(chroma_matrix, dtype=numpy.float32)
    except Exception as exc:
        print("[归因腿缺失] Chroma 精确腿取不到（" + type(exc).__name__ + " "
              + str(exc)[:120] + "）")
    raw_where = str(args.where_json or "").strip()
    #: 谓词里带着会被 shell 吃掉的字符（$in），所以允许 @文件 这一种写法：量具在容器
    #: 里跑，送一份谓词不该再靠一层引号转念。
    if raw_where.startswith("@"):
        raw_where = Path(raw_where[1:]).read_text(encoding="utf-8").strip()
    where = json.loads(raw_where) if raw_where else None
    filter_clause, filter_params = "", []
    if where is not None:
        from app.rag import pg_store

        filter_clause, filter_params = pg_store.sql_scope_filter(where)
    chroma_metadatas = read_metadatas(collection) if where is not None else {}
    mask_ids, mask_array = masked_view(chroma_ids, chroma_array, chroma_metadatas, where)
    if where is not None and mask_ids is None:
        raise SystemExit("[前置不满足] 掩码腿取不到整库元数据，带过滤的精确 top-k 量不了")
    vector_bodies = {}
    if pg_status["state"] == "read_live":
        vector_bodies = compare_vector_bodies(
            chroma_ids, chroma_matrix,
            pg_vector_map(connection, vector_table=vector_table))
    rows, embed_failures, scale_probes = [], [], []
    first_vector = None
    for source, question_id, question in questions:
        try:
            vector = [float(value) for value in embedder.embed_query(question)]
        except Exception as exc:
            #: 打不出题向量就别继续算——拿上一题的向量问两库会造出假的一致。
            embed_failures.append({"id": question_id,
                                   "reason": type(exc).__name__ + " " + str(exc)[:160]})
            continue
        if first_vector is None:
            #: 留给下面的可达性探针用。必须是同一枚进程里的同一个向量：换进程去问
            #: "这库能捞出多少枚"量的是另一份索引状态，不是产生这批读数的那一份。
            first_vector = list(vector)
        literal = "[" + ",".join(repr(value) for value in vector) + "]"
        hit = collection.query(query_embeddings=[vector], n_results=k,
                               **({"where": where} if where else {})) or {}
        chroma_hit_ids = [str(item) for item in ((hit.get("ids") or [[]])[0] or [])]
        chroma_dists = [float(item) for item in ((hit.get("distances") or [[]])[0] or [])]
        chroma = list(zip(chroma_hit_ids, chroma_dists))
        pg_exact = None
        if pg_status["state"] == "read_live":
            pg = pg_live_topk(connection, vector_table=vector_table, operator=operator,
                              literal=literal, k=k, clause=filter_clause,
                              clause_params=filter_params)
            if args.pg_exact:
                pg_exact = pg_exact_topk(connection, vector_table=vector_table,
                                         operator=operator, literal=literal, k=k,
                                         clause=filter_clause,
                                         clause_params=filter_params)
        elif pg_status["state"] == "estimated_exact_knn":
            pg = exact_knn_topk(chroma_ids, chroma_matrix, vector, metric=space, k=k)
        else:
            pg = []
        query_sha = hashlib.sha256(literal.encode("utf-8")).hexdigest()[:16]
        chroma_exact = array_topk(
            mask_ids if mask_ids is not None else chroma_ids,
            mask_array if mask_array is not None else chroma_array,
            None if chroma_array is None else numpy.asarray(vector, dtype=numpy.float32),
            k=k)
        if chroma_exact is not None and chroma:
            #: 把 CHROMA_L2_IS_SQUARED 从「继承来的断言」变成「这一轮量出来的数」：只看
            #: Chroma 自己一侧，它交回的平方欧氏开根号应当等于快照上精确算出的欧氏距离。
            scale_probes.append({
                "kind": "chroma_self",
                "same_top1": bool(chroma[0][0] == chroma_exact[0][0]),
                "error": (None if chroma[0][0] != chroma_exact[0][0] else abs(
                    math.sqrt(max(float(chroma[0][1]), 0.0))
                    - math.sqrt(float(chroma_exact[0][1])))),
            })
        if chroma and pg and chroma[0][0] == pg[0][0]:
            #: 判据③的距离口径：同一枚 query、同一枚命中向量，两侧交回的数应当只差
            #: 「Chroma 报平方」这一层。开根号后仍不等就是口径没对齐，不许往下算。
            scale_probes.append({
                "kind": "cross_engine",
                "same_top1": True,
                "error": abs(math.sqrt(max(float(chroma[0][1]), 0.0)) - float(pg[0][1])),
            })
        rows.append(compare_question(source=source, question_id=question_id,
                                     question=question, chroma=chroma, pg=pg,
                                     k=k, metric=space, pg_exact=pg_exact,
                                     chroma_exact=chroma_exact, query_sha=query_sha))
    #: 可达性探针：向这库一次要回全部行，量它自己的 HNSW 究竟能捞出几枚。这一格与
    #: same_set 同进程共生，是因为 2026-09-24 出现过同一谓词两遍读数 68/92 的分叉——
    #: 分叉要说清是"索引里有多少枚"变了，还是别的东西变了。
    reachability = {}
    try:
        if first_vector is not None:
            scan = collection.query(query_embeddings=[first_vector],
                                   n_results=len(chroma_ids)) or {}
            scanned = [str(item) for item in ((scan.get("ids") or [[]])[0] or [])]
            reachability = {"corpus_rows": len(chroma_ids),
                            "full_scan_rows": len(scanned),
                            "full_scan_unique": len(set(scanned)),
                            "probe": "n_results=count()，第一题的向量"}
    except Exception as exc:
        reachability = {"error": type(exc).__name__ + " " + str(exc)[:160]}

    #: 读期间两侧语料有没有动：先 commit 换新鲜快照再数一遍。同一事务里数两次永远相等，
    #: 那一格就成了假保险。
    pg_after = None
    if connection is not None:
        connection.commit()
        pg_after = connection.execute("SELECT count(*) FROM " + vector_table).fetchone()
        connection.close()
    corpus_after = {"chroma_vectors": int(collection.count()),
                    "pg_vectors": (None if pg_after is None
                                   else int(tool._scalar(pg_after) or 0))}
    corpus_stability = {"before": corpus_before, "after": corpus_after,
                        "stable": corpus_before == corpus_after}

    result = {
        "meta": {
            "tool": "scripts/r59_recall_compare.py",
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "commit": git_revision(),
            "k": k,
            "metric": space,
            "distance": {"chroma_space": space, "u1": u1},
            "chroma_dir": str(Path(args.chroma_dir).resolve()),
            "collection": str(args.collection),
            "chroma_vectors": len(chroma_ids),
            "chroma_dimension": len(chroma_matrix[0]) if chroma_matrix else 0,
            "fixtures": list(args.fixture or list(DEFAULT_FIXTURES)),
            "questions_loaded": len(questions),
            "questions_compared": len(rows),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            "pg_leg": pg_status,
            "vector_table": vector_table,
            "scope_filter": {
                "where": where,
                "sql_clause": filter_clause,
                "sql_params": [repr(item) for item in filter_params],
                "chroma_metadata_rows": len(chroma_metadatas),
                "chroma_exact_masked_rows": (None if mask_ids is None else len(mask_ids)),
            },
            "chroma_reachability": reachability,
            "corpus_stability": corpus_stability,
            "vector_bodies": vector_bodies,
            #: l2 口径探针：0 = 两侧同一个几何量，只是 Chroma 报平方；非 0 说明这格没对上。
            "chroma_l2_scale_probes": len(scale_probes),
            #: 分开聚合：第一名不是同一枚的那些行不算口径误差——把它们混进去，量出来的
            #: 既不是口径也不是近似性，而是第三种没名字的数。
            "chroma_l2_scale_checked": sum(1 for item in scale_probes if item["same_top1"]),
            "chroma_l2_scale_max_error": (
                None if not any(item["same_top1"] for item in scale_probes) else round(
                    max(item["error"] for item in scale_probes if item["same_top1"]), 9)),
            "chroma_l2_scale_by_kind": {
                kind: {
                    "probes": sum(1 for item in scale_probes if item["kind"] == kind),
                    "checked": sum(1 for item in scale_probes
                                   if item["kind"] == kind and item["same_top1"]),
                    "max_error": (None if not any(item["kind"] == kind and item["same_top1"]
                                                  for item in scale_probes) else round(
                        max(item["error"] for item in scale_probes
                            if item["kind"] == kind and item["same_top1"]), 9)),
                } for kind in ("chroma_self", "cross_engine")
            },
        },
        "questions": rows,
        "summary": summarize(rows),
    }
    if embed_failures:
        result["meta"]["embedding_failures"] = embed_failures

    if pg_status["state"] != "read_live":
        return result, EXIT_PG_NOT_ASKED
    return result, (EXIT_MATCHED if result["summary"]["differing_set"] == 0
                    else EXIT_DIFFERS)



# --------------------------------------------------------------- 交回给总控的三样东西

def disagreement_list(result: dict, *, limit: int = 0) -> list:
    """分歧题清单：只列两腿集合不等的题，带上判读要用的那几个数。"""
    out = []
    for item in result["questions"]:
        if item["same_set"]:
            continue
        out.append({
            "source": item["source"], "id": item["id"], "question": item["question"],
            "overlap": item["overlap"], "jaccard": item["jaccard"],
            "first_diff_rank": item["first_diff_rank"],
            "mean_abs_rank_shift": item["mean_abs_rank_shift"],
            "max_abs_rank_shift": item["max_abs_rank_shift"],
            "kendall_tau": item["kendall_tau"],
            "chroma_rows": item["chroma_rows"], "pg_rows": item["pg_rows"],
            "chroma_only": item["chroma_only_ids"], "pg_only": item["pg_only_ids"],
            "chroma_top1": item["chroma_top1_comparable"],
            "pg_top1": item["pg_top1_comparable"],
            "pg_farthest": item["pg_farthest_comparable"],
        })
    return out[:limit] if limit else out


def render_markdown(result: dict) -> str:
    """人读的表从同一份数据里长出来，不另算一遍数——两处算就会两处骗人。"""
    meta, summary, pg = result["meta"], result["summary"], result["meta"]["pg_leg"]
    lines = ["## 两侧口径", ""]
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append("| revision | `%s` |" % meta["commit"])
    lines.append("| 生成时刻 | %s |" % meta["generated_at"])
    lines.append("| k | %s |" % meta["k"])
    lines.append("| 题集 | %s（读到 %d 题，比了 %d 题） |"
                 % ("、".join("`%s`" % item for item in meta["fixtures"]),
                    meta["questions_loaded"], meta["questions_compared"]))
    lines.append("| Chroma 侧 | `%s` / collection `%s` / %d 枚 %d 维 |"
                 % (meta["chroma_dir"], meta["collection"], meta["chroma_vectors"],
                    meta["chroma_dimension"]))
    lines.append("| 距离算符 | %s（U1 来源=%s，样本=%s 枚，探针=%s 枚） |"
                 % (meta["metric"], meta["distance"]["u1"].get("source"),
                    meta["distance"]["u1"].get("sampled"),
                    meta["distance"]["u1"].get("probes")))
    lines.append("| embedding 模型 | %s |" % meta["embedding_model"])
    lines.append("| 🔴 PG 腿状态 | **%s** |" % pg.get("state"))
    if pg.get("reason"):
        lines.append("| PG 腿交不回数的原因 | %s |" % pg["reason"])
    if pg.get("estimate_warrant"):
        lines.append("| 估算腿的凭据 | %s |" % pg["estimate_warrant"])
    if pg.get("dimension"):
        lines.append("| vector_scope | %s / %s 维 / %s / 列型 %s |"
                     % (pg["embedding_model"], pg["dimension"],
                        pg["distance_function"], pg["column_type"]))
    if pg.get("drift"):
        lines.append("| 镜像差集 | %s |" % json.dumps(pg["drift"], ensure_ascii=False))
    if pg.get("engine"):
        lines.append("| 真库口径原文 | %s |" % json.dumps(pg["engine"], ensure_ascii=False))
    if meta.get("corpus_stability"):
        lines.append("| 语料稳定 | %s |"
                     % json.dumps(meta["corpus_stability"], ensure_ascii=False))
    if meta.get("vector_bodies"):
        lines.append("| 两侧向量逐位 | %s |"
                     % json.dumps(meta["vector_bodies"], ensure_ascii=False))
    lines.append("| Chroma 距离口径 | 继承断言=平方欧氏；可核算 %s/%s 枚，最大误差 %s |"
                 % (meta.get("chroma_l2_scale_checked"), meta.get("chroma_l2_scale_probes"),
                    meta.get("chroma_l2_scale_max_error")))
    lines.append("| 距离口径分腿 | %s |"
                 % json.dumps(meta.get("chroma_l2_scale_by_kind"), ensure_ascii=False))
    lines += ["", "## 重合度与排名差", "", "| 指标 | 值 |", "|---|---|"]
    for key in ("questions", "same_set", "same_order", "differing_set", "mean_overlap",
                "mean_overlap_ratio", "mean_jaccard", "median_jaccard",
                "questions_full_overlap", "questions_zero_overlap",
                "mean_abs_rank_shift", "max_abs_rank_shift", "mean_kendall_tau",
                "chroma_zero_rows", "pg_zero_rows", "chroma_only_zero", "pg_only_zero",
                "pg_exact_leg", "pg_index_vs_exact_same_set",
                "pg_index_vs_exact_mismatch_ids", "chroma_exact_leg",
                "chroma_index_vs_exact_same_set", "chroma_index_vs_exact_mismatch_ids",
                "exact_sides_same_set", "exact_sides_mismatch_ids"):
        lines.append("| `%s` | %s |" % (key, summary.get(key)))
    diverging = disagreement_list(result)
    lines += ["", "## 分歧题清单（共 %d 题）" % len(diverging), ""]
    if not diverging:
        lines.append("逐题 top-k 集合两侧完全一致，没有分歧题。")
    else:
        lines.append("| 题号（题集 · 题 id） | 重合 | Jaccard | 首个不同名次 | 平均位移 |"
                     " 最大位移 | τ | 两侧第一名距离 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for item in diverging:
            lines.append("| `%s` | %s/%s | %s | %s | %s | %s | %s | %s vs %s |" % (
                item["source"] + " · " + item["id"], item["overlap"],
                result["meta"]["k"], item["jaccard"],
                item["first_diff_rank"], item["mean_abs_rank_shift"],
                item["max_abs_rank_shift"], item["kendall_tau"],
                item["chroma_top1"], item["pg_top1"]))
    if result["meta"].get("embedding_failures"):
        lines += ["", "## 打不出题向量的题（不算进重合度）", ""]
        for item in result["meta"]["embedding_failures"]:
            lines.append("- `%s`：%s" % (item["id"], item["reason"]))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        result, code = build_result(args)
    except SystemExit as exc:
        print(str(exc))
        return EXIT_PRECONDITION
    if result is None:
        return code
    if "error" in result:
        #: 上一版只在 code==2 时走这条，于是 live 腿交不回来（code==3）时会继续往下打印并
        #: 去摘 result["summary"] —— 那份产物里根本没有 summary，直接 KeyError 崩在打印里，
        #: "读数只有一条腿"看着像脚本坏了，而不是像它本来就该被丢掉。
        print(("[前置不满足] " if code == EXIT_PRECONDITION else "[PG 腿未交付] ")
              + result["error"])
        return code
    print("-- PG 腿状态：%s --" % result["meta"]["pg_leg"].get("state"))
    summary = result["summary"]
    print("-- %d 题：%d 题集合一致 / %d 题不一致；平均重合 %.2f/%d，平均 Jaccard %s --" % (
        summary.get("questions", 0), summary.get("same_set", 0),
        summary.get("differing_set", 0), summary.get("mean_overlap", 0.0),
        result["meta"]["k"], summary.get("mean_jaccard")))
    print("-- 名次：平均绝对位移 %s，最大 %s，平均 Kendall tau %s --" % (
        summary.get("mean_abs_rank_shift"), summary.get("max_abs_rank_shift"),
        summary.get("mean_kendall_tau")))
    print("-- 单腿 0 条：Chroma 交 0 条 %d 题，PG 交 0 条 %d 题 --" % (
        summary.get("chroma_zero_rows"), summary.get("pg_zero_rows")))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print("机读产物已写出：" + args.out)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(render_markdown(result), encoding="utf-8")
        print("人读表已写出：" + args.md)
    if code == EXIT_PG_NOT_ASKED:
        print("🔴 这份读数只有一条腿是真读到的，另一条是估的或压根没读到。"
              "它不能当\"切过去不会变差\"的证据。")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

