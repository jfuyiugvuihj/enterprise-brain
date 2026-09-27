"""R382: render the reading tables from the JSON each measurement script left behind.

The doc that carries these tables must not contain a number typed by hand, so the tables
come out of the artifacts. Run it after the measurement scripts and paste the result.
"""
from __future__ import annotations

import json
import os
import sys

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."


def load(name):
    path = os.path.join(OUT_DIR, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def cell(items, key="id", score=None):
    if not items:
        return "∅"
    if score:
        return " · ".join(f"{item[key]}@{item[score]}" for item in items)
    return " · ".join(str(item[key]) if isinstance(item, dict) else str(item)
                      for item in items)


def ids_cell(items):
    return " · ".join(items) if items else "∅"


def main() -> int:
    matched = load("r382_matched.json")
    compare = load("r382_compare.json")
    parity = load("r382_parity.json")
    metric = load("r382_metric.json")
    legs = load("r382_legs.json")
    lines = []
    add = lines.append

    if matched:
        add("### T2 端到端 top-5（元数据同形后，两侧同一题面、同一 principal、同一 k）")
        add("")
        add("| 账号 | 题面 | pgvector 腿 top-5 | chroma 腿 top-5 | 重合 | 同位 | 秒(pg/chroma) |")
        add("|---|---|---|---|---|---|---|")
        for name, table in matched["tables"].items():
            for row in table:
                add(f"| {name} | {row['query']} | {ids_cell(row['pg_ids'])} | "
                    f"{ids_cell(row['chroma_ids'])} | {row['shared']}/"
                    f"{max(1, len(set(row['pg_ids']) | set(row['chroma_ids'])))} | "
                    f"{row['position_match']} | {row['seconds_pg']}/{row['seconds_chroma']} |")
        add("")
        add("### T3 端到端差集逐条（两侧名次不一致的那些格）")
        add("")
        add("| 账号 | 题面 | 只在 pgvector | 只在 chroma |")
        add("|---|---|---|---|")
        empty = True
        for name, table in matched["tables"].items():
            for row in table:
                if row["pg_only"] or row["chroma_only"]:
                    empty = False
                    add(f"| {name} | {row['query']} | {ids_cell(row['pg_only'])} | "
                        f"{ids_cell(row['chroma_only'])} |")
        if empty:
            add("| — | 60 格全部零差集 | — | — |")
        add("")
        add("### T4 腿级 top-k 带分数（同一权限谓词、同一查询向量，数字为各自引擎报告的距离）")
        add("")
        add("| 账号 | 题面 | pgvector id@distance | chroma id@distance | 重合 | 越权行 |")
        add("|---|---|---|---|---|---|")
        for name, block in matched["scoped_store"].items():
            for row in block["rows"]:
                add(f"| {name} | {row['query']} | {cell(row['pg'], score='distance')} | "
                    f"{cell(row['chroma'], score='distance')} | {row['shared']} | "
                    f"pg={len(row['pg_out_of_scope'])}/chroma={len(row['chroma_out_of_scope'])} |")
        add("")
        add("### T5 腿级差集逐条（带两侧距离）")
        add("")
        add("| 账号 | 题面 | 侧 | chunk id | 该侧距离 | 对侧是否给出 |")
        add("|---|---|---|---|---|---|")
        found = False
        for name, block in matched["scoped_store"].items():
            for row in block["rows"]:
                for item in row["pg_only"]:
                    found = True
                    add(f"| {name} | {row['query']} | 仅 pgvector | {item['id']} | "
                        f"{item.get('pg_distance', '?')} | "
                        f"{item.get('chroma_distance', '未给出')} |")
                for item in row["chroma_only"]:
                    found = True
                    add(f"| {name} | {row['query']} | 仅 chroma | {item['id']} | "
                        f"{item.get('chroma_distance', '?')} | "
                        f"{item.get('pg_distance', '未给出')} |")
        if not found:
            add("| — | 零差集 | — | — | — | — |")
        add("")
        add("### T8 权限矩阵（元数据同形后）")
        add("")
        add("| 账号 | department | clearance | 谓词 | pg 命中 | chroma 命中 | 越权 | 空题面 | 均值重合 |")
        add("|---|---|---|---|---|---|---|---|---|")
        for name, item in matched["permission"].items():
            add(f"| {name} | {item['department']} | {item['clearance']} | "
                f"`{json.dumps(matched['scoped_store'][name]['filters'], ensure_ascii=False)}` | "
                f"{item['pg_hits']} | {item['chroma_hits']} | "
                f"pg={item['pg_violations']}/chroma={item['chroma_violations']} | "
                f"pg={item['pg_empty_queries']}/chroma={item['chroma_empty_queries']} | "
                f"{item['mean_overlap']} |")
        add("")

    if compare:
        add("### T6a 无谓词腿级对照（引擎单独比试，真实查询向量）")
        add("")
        add("| # | 题面 | pgvector id@L2 | chroma id@平方L2 | 重合 | 差集(仅一侧) |")
        add("|---|---|---|---|---|---|")
        for row in compare["rows"]:
            diff = row["pg_vs_chroma"]
            only = " + ".join(
                [f"pg:{item['id']}@{item.get('pg_distance', '?')}" for item in diff["pg_only"]]
                + [f"chroma:{item['id']}@{item.get('chroma_distance', '?')}"
                   for item in diff["chroma_only"]]) or "—"
            add(f"| {row['n']} | {row['query']} | {cell(row['pg_hnsw'], score='distance')} | "
                f"{cell(row['chroma'], score='distance')} | {diff['shared']} | {only} |")
        add("")
        add("### T6b 三方名次（HNSW vs 精确 KNN，同一份向量）")
        add("")
        add("| # | 题面 | pg ANN=精确 | chroma ANN=精确 | pg ANN | chroma ANN | 精确(pg) |")
        add("|---|---|---|---|---|---|---|")
        for row in compare["rows"]:
            add(f"| {row['n']} | {row['query']} | "
                f"{row['pg_hnsw_vs_exact']['shared']}/5 | {row['chroma_vs_exact']['shared']}/5 | "
                f"{ids_cell([item['id'] for item in row['pg_hnsw']])} | "
                f"{ids_cell([item['id'] for item in row['chroma']])} | "
                f"{ids_cell([item['id'] for item in row['pg_exact']])} |")
        add("")

    if parity:
        add("### T6c 两库向量是否同一份（决定 T6 归因能不能算指标差异）")
        add("")
        add("```json")
        add(json.dumps({"corpus": parity["corpus"], "vector_parity": parity["vector_parity"],
                        "recall": parity["recall"], "ann_latency_ms": parity["ann_latency_ms"]},
                       ensure_ascii=False, indent=2))
        add("```")
        add("")
        add("### T7 热集那一腿：切读前后（HOT_INDEX_ENABLED=on，谓词换成两侧都满足的形状）")
        add("")
        add("| 状态 | 首次暖机 ms | 之后每次 ms（12 次） | 中位 | 最大 | 交回命中 | 计数 |")
        add("|---|---|---|---|---|---|---|")
        for backend, block in parity["hot_leg"].items():
            add(f"| `{backend}` | {block['warm_call_ms']} | "
                f"{', '.join(str(v) for v in block['per_call_ms'])} | {block['median_ms']} | "
                f"{block['max_ms']} | {cell([{'id': str(v)} for v in block['served_hits']])} | "
                f"hits={block['diagnostics_after']['hits']} "
                f"misses={block['diagnostics_after']['misses']} "
                f"reason={block['diagnostics_after']['last_bypass_reason'] or '—'} |")
        add("")

    if metric:
        add("### T6d 距离算子归因（chroma 名次 vs 三种算子的精确 KNN）")
        add("")
        add("```json")
        add(json.dumps({"agreement": metric["agreement"],
                        "stored_vector_norms": metric["stored_vector_norms"],
                        "query_vector_norms": metric["query_vector_norms"]},
                       ensure_ascii=False, indent=2))
        add("```")
        add("")

    if legs:
        add("### T9 生产元数据形态下的对照（未同形：这就是第一遍读到的东西）")
        add("")
        add("| 腿 | 12 题端到端命中数 | 语义腿答复方 | 语料腿来源 | PG 读腿计数 | 越权 |")
        add("|---|---|---|---|---|---|")
        for name, block in legs["legs"].items():
            hits = [row["hits"] for row in block["end_to_end"]]
            servers = sorted({str(row["answered_by"]) for row in block["end_to_end"]})
            corpus = block["corpus_diagnostics"]
            read = block["read_diagnostics"]
            violations = sum(len(item["pg_store_level"]["violations"])
                             + len(item["chroma_store_level"]["violations"])
                             for item in block["permission"])
            add(f"| `{name}` | {hits} | {servers} | {corpus['source']}"
                f"(rows={corpus['rows']}) | attempts={read['attempts']} "
                f"answered={read['answered']} rows={read['rows']} "
                f"bypass={read['bypasses'] or '{}'} | {violations} |")
        add("")
        add("| 账号 | 谓词 | pg 腿交回行 | chroma 腿交回行 | 越权 |")
        add("|---|---|---|---|---|")
        for item in legs["legs"]["pgvector"]["permission"]:
            add(f"| {item['name']} | `{json.dumps(item['filters'], ensure_ascii=False)}` | "
                f"{item['pg_store_level']['returned']} | "
                f"{item['chroma_store_level']['returned']} | "
                f"{len(item['pg_store_level']['violations'])}/"
                f"{len(item['chroma_store_level']['violations'])} |")
        add("")
        add("```json")
        add(json.dumps({"embedding": legs["embedding"], "env": legs["env"],
                        "database_identity": legs["database_identity"]},
                       ensure_ascii=False, indent=2))
        add("```")
    empties = {}
    for label, filename in (("生产副本（未改元数据）", "r382_empty_chroma_orig.json"),
                            ("同形副本（只换标签）", "r382_empty_chroma_matched.json")):
        data = load(filename)
        if data:
            empties[label] = data
    if empties:
        add("### T10 遗留引擎空腿复现表（同一枚查询向量，问 k=1/3/5/10/50）")
        add("")
        add("| 副本 | # | 题面 | k=1 | k=3 | k=5 | k=10 | k=50 | 复问三次 | 向量微扰后 |")
        add("|---|---|---|---|---|---|---|---|---|---|")
        for label, data in empties.items():
            for row in data["rows"]:
                by_k = row["by_k"]
                add(f"| {label} | {row['n']} | {row['query']} | "
                    + " | ".join(str(by_k[k]["returned"]) for k in
                                 ("1", "3", "5", "10", "50"))
                    + f" | {row['repeat']} | {json.dumps(row['perturbed'])} |")
        add("")
    scope = load("r382_index_scope.json")
    if scope:
        def field(node, *keys):
            for key in keys:
                value = node.get(key)
                if value not in (None, "", []):
                    return value
            return "—"
        add("### T11 三方排序口径现读（切读会不会改变“最近”的定义，看这张表）")
        add("")
        add("| 引擎 | 连的库/卷 | 只读事务 | 枚数 | 距离 | HNSW m | ef_construction | 运行时 ef_search | 算子类 / 段类型 | pgvector |")
        add("|---|---|---|---|---|---|---|---|---|---|")
        for key, label, target in (
            ("sandbox", "pgvector 沙盒（本班全部读数所用）", "eb_r59_sandbox"),
            ("production", "pgvector 生产（仅现读口径，未写一字）", "enterprise_brain"),
        ):
            node = scope.get(key) or {}
            if node.get("error"):
                add(f"| {label} | {target} | — | — | — | — | — | — | — | {node['error']} |")
                continue
            add("| {} | `{}` | {} | {} | **{}** | {} | {} | **{}** | `{}` | {} |".format(
                label, target,
                field(node, "transaction_read_only"),
                field(node, "vectors"),
                (node.get("scope") or [{}])[0].get("distance_function", "—"),
                field(node, "m"), field(node, "ef_construction"),
                field(node, "ef_search_runtime"),
                field(node, "operator_class"),
                field(node, "vector_version")))
        node = scope.get("chroma") or {}
        add("| Chroma（退役中的遗留引擎，卷的临时副本） | `{}` | 只读靠副本，未碰真卷 | {} | **{}** | {} | {} | **{}** | `{}` | — |".format(
            field(node, "chroma_dir"),
            field(node, "vectors"),
            field(node, "distance_function"),
            field(node, "m"), field(node, "ef_construction"),
            field(node, "ef_search"),
            "hnsw-local-persisted"))
        add("")
    text = "\n".join(lines)
    destination = os.getenv("R382_TABLES_OUT", os.path.join(OUT_DIR, "r382_tables.md"))
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"{len(text)} chars -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())