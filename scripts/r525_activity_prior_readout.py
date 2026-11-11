#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R525 · 活动先验「真库强度」取证量具（全单只读，零产品码改动）.

## 它量什么

R46 差格 b 要的是「先验在真库上到底还剩不剩」，不是「先验的算术对不对」（那一格
``tests/test_r153_prior_shift_is_bounded.py`` 早就钉住了）。所以本件只交回四类读数：

1. ``store``  —— 真库面清点：0011 有没有跑、表里几行、非零计数怎么分布、能命中语料里哪几篇，
   以及语料那一侧的**真实数据形状**（filename 作为连接键干不干净）。
2. ``reader`` —— 产品自己的读取器 ``app/rag/retriever.py::activity_priors`` 在真 DSN 上的读数：
   「读成功而零行」与「读不通」必须分得开（判据⑤「不许冒充」全靠这一格）。
3. ``ann``   —— 真库 ANN 名次回放：候选是真库已经在位的 1008 枚 embedding，发一条与
   ``pg_store.search_vectors`` 同形的只读 SELECT，取回真实名次。查询向量用定种子随机数，
   因为**本单不许打模型**——这一点在产物里明写，不遮掩。
4. ``gauge`` —— 把那份真库名次送进 ``rank_hits_by_activity``，在 5 / 12 / 40 三种腿宽 ×
   有信号 / 无信号两态下逐枚点名次与 ``places_moved``，位移越界当场抛。

## 两枚「真库」是两枚不同的东西（本件不混着说）

* **面 A = 部署库**（容器 ``enterprise-brain-postgres-1`` / 库 ``enterprise_brain``）：17 枚迁移
  全在台账里，``chunk_vectors`` 1008 枚。宿主 psycopg **够不到它**——compose 没给 postgres 发布
  宿主端口，``tests/conftest.py`` 的注释与此同口径。本件走在册的只读出口
  ``docker exec ... psql -c "SET default_transaction_read_only = on" -c "<SELECT>"``，
  与 ``scripts/r483_empty_tables_triage.py`` 同一把闸。
* **面 B = 宿主 PG**（``.env`` 里那枚 ``DATABASE_URL``）：计划书 §9.3 点名的「5432 上那台野
  PostgreSQL」。它连 ``schema_migrations`` 都没有 ⇒ 0011 的表也不存在 ⇒ 它就是判据⑤要的
  「没跑 0011 的库」，真库真连接真报错，不是夹具。

## 硬边界

* **只读**：``assert_select_only()`` 是唯一发 SQL 出口；写句与 DDL/DCL 一律抛。不跑迁移、
  不动容器、不起服务、不打模型。
* **凭据一个字都不出纸**：DSN 只以 ``mask_dsn()`` 的形状进产物。
* **不许冒充客户尺寸**：面 A 那份 1008 枚 / 100 篇是演示语料，产物里每格都带
  ``corpus_is_demo_corpus: true`` 这枚旗。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: 在册只读出口（面 A）：与 scripts/r483_empty_tables_triage.py 同一容器、用户、库。
CONTAINER = "enterprise-brain-postgres-1"
PG_USER = "enterprise_brain"
PG_DB = "enterprise_brain"

#: 每条 psql 调用前面都挂这一句；它本身不是 SELECT，所以按整串白名单放行。
READ_ONLY_PRAGMA = "SET default_transaction_read_only = on"

#: 腿宽：派工词点名 5 / 12 / 40 各测一次。
LEG_WIDTHS = (5, 12, 40)

_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|create|alter|drop|truncate|grant|revoke|copy|vacuum|"
    r"reindex|cluster|refresh|call|do|prepare|deallocate|lock|notify|listen)\b",
    re.IGNORECASE,
)
_SQL_ALLOWED_HEADS = ("select", "with", "begin", "commit", "rollback")


def assert_select_only(sql: str) -> str:
    """唯一发 SQL 闸门：不是只读语句就抛，命中禁词也抛（「零写」的机器证明）。"""
    text = str(sql).strip().rstrip(";").strip()
    head = text.split(None, 1)[0].lower() if text else ""
    if head not in _SQL_ALLOWED_HEADS:
        raise RuntimeError("R525 只读取证：非只读语句 " + text[:80])
    hit = _SQL_FORBIDDEN.search(text)
    if hit:
        raise RuntimeError(f"R525 只读取证：语句命中禁词 {hit.group(0)!r} => {text[:80]}")
    return text


def mask_dsn(url: str) -> str:
    """把 DSN 收成「认得出是哪枚库、但读不出凭据」的形状。"""
    return re.sub(r"://[^@]*@", "://***@", str(url or ""))


def psql(sql: str, *, container: str = CONTAINER, user: str = PG_USER,
         database: str = PG_DB, docker_bin: str = "docker", timeout: int = 60) -> list:
    """进容器发一条只读 SELECT，交回数据行（psql 回显的 SET 不是数据，剔掉）。"""
    argv = [docker_bin, "exec", container, "psql", "-U", user, "-d", database, "-At",
            "-v", "ON_ERROR_STOP=1", "-c", READ_ONLY_PRAGMA, "-c", assert_select_only(sql)]
    proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("psql 读数失败 rc=%d: %s" % (
            proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[:400]))
    text = proc.stdout.decode("utf-8", "replace")
    return [line for line in text.splitlines() if line.strip() and line.strip() != "SET"]


def psql_rows(inner_sql: str, **kwargs) -> list:
    """把子查询逐行编成 JSON 再取回（一行一枚对象）。

    🔴 现量到的形状：``json_agg`` 在多行时会在行间插换行（本库 PG 16.15 实测
    ``[{"a":"x"}, `` 换行 ``{"a":"y"}]``），所以行协议不靠整包 JSON，靠逐行 ``row_to_json``；
    正文里的换行由 JSON 转义，打断不了行协议。
    """
    lines = psql("SELECT row_to_json(t) FROM (" + assert_select_only(inner_sql) + ") t", **kwargs)
    return [json.loads(line) for line in lines if line.strip()]


def command_of(sql: str, *, container: str = CONTAINER, user: str = PG_USER,
               database: str = PG_DB) -> str:
    """读数纸要的「命令原文」在这里生成，不在纸里手抄第二份。"""
    return ("docker exec " + container + " psql -U " + user + " -d " + database
            + ' -At -v ON_ERROR_STOP=1 -c "' + READ_ONLY_PRAGMA + '" -c "'
            + " ".join(assert_select_only(sql).split()) + '"')


def read_product_select_text() -> str:
    """从产品源码里**现读**它打给 0011 的那条 SELECT 原文（连接键口径以产品为准，不重抄）。"""
    import ast

    source = (REPO / "app" / "rag" / "retriever.py").read_text(encoding="utf-8-sig")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "execute":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and "document_activity_signals" in arg.value:
                    return assert_select_only(arg.value)
    raise RuntimeError("app/rag/retriever.py 里找不到那条 0011 的 SELECT：口径变了，本件一起改")


def rows_to_priors(lines: list) -> dict:
    """把产品那条 SELECT 的行（filename|accepted|rejected）折成 activity_priors 的形状。"""
    priors = {}
    for line in lines:
        parts = line.split("|")
        if len(parts) == 3:
            priors[parts[0]] = {"accepted": int(parts[1]), "rejected": int(parts[2])}
    return priors


# ==================== 1) store：真库面清点 ====================

def census_surface_a(**kwargs) -> dict:
    """面 A（部署库）：台账 / 0011 存不存在 / 几行 / 非零分布 / 命中语料几篇 / 语料形状。"""
    readings: dict = {}

    def note(key: str, sql: str, value) -> None:
        readings[key] = {"sql": " ".join(sql.split()),
                         "command": command_of(sql, **kwargs), "value": value}

    out: dict = {"surface": "A-deployed-container-pg", "reachable_by": "docker exec psql",
                 "read_only_statement": True}

    ledger_sql = "SELECT version FROM schema_migrations ORDER BY version"
    ledger = psql(ledger_sql, **kwargs)
    note("migration_ledger", ledger_sql, ledger)
    out["migration_count"] = len(ledger)
    out["migration_0011_in_ledger"] = "0011" in ledger

    regclass_sql = "SELECT to_regclass('public.document_activity_signals')::text"
    regclass = psql(regclass_sql, **kwargs)
    relation = regclass[0] if regclass else ""
    note("regclass", regclass_sql, relation)
    out["relation"] = relation or None

    if relation != "document_activity_signals":
        out["rows"] = None
        out["note"] = "面 A 上 0011 的表不存在（与面 B 同格）"
        out["readings"] = readings
        return out

    rows_sql = "SELECT count(*)::int FROM document_activity_signals"
    out["rows"] = int(psql(rows_sql, **kwargs)[0])
    note("rows", rows_sql, out["rows"])

    dist_sql = ("SELECT bucket, count(*)::int AS "
                "documents, coalesce(sum(accepted_count),0)::int AS accepted, "
                "coalesce(sum(rejected_count),0)::int AS rejected FROM (SELECT CASE WHEN "
                "accepted_count > 0 AND rejected_count = 0 THEN 'accepted_only' WHEN "
                "accepted_count = 0 AND rejected_count > 0 THEN 'rejected_only' WHEN "
                "accepted_count > 0 THEN 'both' ELSE 'impossible_by_check_constraint' END AS "
                "bucket, accepted_count, rejected_count FROM document_activity_signals) s "
                "GROUP BY bucket ORDER BY bucket")
    out["non_zero_distribution"] = psql_rows(dist_sql, **kwargs)
    note("non_zero_distribution", dist_sql, out["non_zero_distribution"])

    join_sql = ("SELECT count(*)::int FROM document_activity_signals s WHERE EXISTS "
                "(SELECT 1 FROM chunk_vectors v WHERE v.filename = s.filename)")
    out["signals_hitting_corpus"] = int(psql(join_sql, **kwargs)[0])
    note("signals_hitting_corpus", join_sql, out["signals_hitting_corpus"])

    top_sql = ("SELECT filename, accepted_count, rejected_count FROM document_activity_signals "
               "ORDER BY filename LIMIT 10")
    out["top_signals"] = psql_rows(top_sql, **kwargs)
    note("top_signals", top_sql, out["top_signals"])

    shape_sql = ("SELECT count(*)::int, count(DISTINCT filename)::int, count(*) FILTER "
                 "(WHERE filename <> btrim(filename))::int, count(*) FILTER (WHERE length("
                 "filename) > 512)::int, max(length(filename))::int, count(DISTINCT lower("
                 "filename))::int FROM chunk_vectors")
    line = psql(shape_sql, **kwargs)[0].split("|")
    out["corpus_shape"] = {"vector_rows": int(line[0]), "distinct_filenames": int(line[1]),
                           "whitespace_padded_rows": int(line[2]), "over_512_rows": int(line[3]),
                           "max_filename_len": int(line[4]), "distinct_casefolded": int(line[5])}
    out["case_collisions"] = (out["corpus_shape"]["distinct_filenames"]
                              - out["corpus_shape"]["distinct_casefolded"])
    note("corpus_shape", shape_sql, out["corpus_shape"])
    #: 🔴 演示语料旗：不许拿这一档冒充客户尺寸（判据⑥）。
    out["corpus_is_demo_corpus"] = True

    spread_sql = ("SELECT max(n)::int AS widest, "
                  "min(n)::int AS narrowest, round(avg(n)::numeric, 2)::float AS average, "
                  "count(*) FILTER (WHERE n >= 5)::int AS docs_with_5plus_chunks FROM "
                  "(SELECT count(*) AS n FROM chunk_vectors GROUP BY filename) s")
    spread_rows = psql_rows(spread_sql, **kwargs)
    #: 这条聚合没有 GROUP BY，真库上恒回一行：钉住发形，别让下游把单元素列表当 dict 用。
    assert len(spread_rows) == 1, f"每篇枚数分布应当只回一行，实回 {len(spread_rows)} 行"
    out["chunks_per_document"] = spread_rows[0]
    note("chunks_per_document", spread_sql, out["chunks_per_document"])

    scope_sql = ("SELECT schema_version, embedding_model, dimension, distance_function, hnsw_m, "
                 "hnsw_ef_construction FROM vector_scope ORDER BY schema_version")
    out["vector_scope"] = psql(scope_sql, **kwargs)
    note("vector_scope", scope_sql, out["vector_scope"])

    srv_sql = "SELECT version() || ' / ' || current_database() || ' / ' || current_user"
    out["server"] = psql(srv_sql, **kwargs)[0]
    note("server", srv_sql, out["server"])

    out["readings"] = readings
    return out


def census_surface_b(dsn: str) -> dict:
    """面 B（宿主 PG / 那台野库）：它没跑 0011，是判据⑤的天然样本，走 psycopg 真连接。"""
    out = {"surface": "B-host-postgres", "dsn": mask_dsn(dsn), "reachable_by": "psycopg",
           "corpus_is_demo_corpus": False}
    try:
        with _connect(dsn) as connection:
            out["schema_migrations_present"] = bool(connection.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = "
                "'schema_migrations'").fetchone()[0])
            out["relation"] = connection.execute(
                "SELECT to_regclass('public.document_activity_signals')").fetchone()[0]
            out["chunk_vectors_present"] = bool(connection.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = "
                "'chunk_vectors'").fetchone()[0])
            out["public_tables"] = len(connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                "ORDER BY 1").fetchall())
            out["server"] = connection.execute(
                "SELECT version() || ' / ' || current_database() || ' / ' || current_user"
            ).fetchone()[0]
    except Exception as exc:
        out["connect_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


def _connect(dsn: str):
    """走 `app/db/connection.py` 那枚边界，不在读数件里再盖一间小房子。

    R238 的裸 connect 棘轮只准降不准升（`tests/test_r238_bare_connect_ratchet.py`：
    「边界之外裸 connect 从 15 枚涨到 16 枚」就是本件并树后点着的第一枚红）。两条出路里
    「向总控申请入册」要把这枚永久记进账本，而本件要的只是「带 3 s 上限地开一条连接」——
    边界已经供了这个能力，所以走迁移：`connect_timeout` 随 conninfo 一起交给边界，
    行为与改前逐字相同（同一枚 psycopg 驱动、同一份超时），红面少一枚、账本不涨一格。
    """
    from app.db import connection as db_conn

    sep = "&" if "?" in dsn else "?"
    return db_conn.open_connection(db_conn.parse_database_settings(f"{dsn}{sep}connect_timeout=3"))


# ==================== 2) reader：产品读取器在两枚真库上 ====================

def reader_readings(dsn: str, product_select: str, **kwargs) -> dict:
    """``activity_priors()`` 的观测面：面 B 真 psycopg，面 A 真 SELECT 原文经 psql 取回。"""
    from app.rag import retriever as rt

    out = {"product_select": product_select}

    rt.reset_activity_priors()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = dsn
    try:
        priors_b = rt.activity_priors()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    out["surface_b"] = {"dsn": mask_dsn(dsn), "priors": dict(priors_b),
                        "diagnostics": rt.activity_prior_diagnostics(),
                        "note": "产品自己的 _read_activity_signal_rows + 真 psycopg + 真缺表"}

    lines = psql(product_select, **kwargs)
    parsed = [tuple(line.split("|")) for line in lines if line.strip()]
    rt.reset_activity_priors()
    priors_a = rt.activity_priors(row_reader=lambda: parsed)
    out["surface_a"] = {
        "command": command_of(product_select, **kwargs),
        "rows_returned_by_the_product_select": len(parsed),
        "priors": dict(priors_a),
        "diagnostics": rt.activity_prior_diagnostics(),
        "psycopg_reachable_from_host": False,
        "note": "面 A 宿主够不到端口，被验的是产品那条 SELECT 原文与它的聚合/观测面，不是网络",
    }
    rt.reset_activity_priors()
    return out


# ==================== 3) ann：真库 ANN 名次回放 ====================

#: 与 app/rag/pg_store.DISTANCE_OPERATORS 同一张表（本件现读 vector_scope 再选算符）。
DISTANCE_OPERATORS = {"l2": "<->", "cosine": "<=>", "ip": "<#>"}


def real_ann_topk(*, query_literal: str, limit: int, ef_search: int, scope: str = "l2",
                  columns=None, **kwargs) -> list:
    """与 pg_store.search_vectors 同形：同算符、事务内 set_config(hnsw.ef_search, local)。"""
    columns = columns or ("vector_id, filename, chunk_index, classification, department, "
                          "left(content, 24) AS content_head")
    operator = DISTANCE_OPERATORS[scope]
    vector = "'" + query_literal + "'::vector"
    inner = ("SELECT set_config('hnsw.ef_search', '" + str(int(ef_search)) + "', TRUE) AS "
             "ef_search_applied, " + columns + ", embedding " + operator + " " + vector
             + " AS distance FROM chunk_vectors ORDER BY embedding " + operator + " " + vector
             + " LIMIT " + str(int(limit)))
    return psql_rows(inner, **kwargs)


def stored_vector_literal(**kwargs) -> str:
    """真库里已经在位的一枚 embedding 的文本形式（本件因此一次模型都不用打）。"""
    return psql("SELECT embedding::text FROM chunk_vectors ORDER BY vector_id LIMIT 1", **kwargs)[0]


def random_vector_literal(*, dimension: int, seed: int) -> str:
    rng = random.Random(seed)
    return "[" + ",".join("%.6f" % rng.uniform(-1.0, 1.0) for _ in range(dimension)) + "]"


# ==================== 4) gauge：真库名次 × 先验 ====================

def synthetic_priors_for(names, *, seed: int = 20260930) -> dict:
    """合成计数：键是真库真 filename，值明写是合成。

    🔴 真库 0 行 ⇒ 本单不许伪造「真库有信号」，这一枚只服务位移判据，产物里 state 名字就带
    ``synthetic_`` 前缀。
    """
    rng = random.Random(seed)
    picked = list(dict.fromkeys(names))[:3]
    priors = {}
    for index, name in enumerate(picked):
        priors[name] = ({"accepted": 3, "rejected": 0} if index == 0 else
                        {"accepted": rng.randint(0, 2), "rejected": rng.randint(0, 3)})
    return priors


def gauge(hits, *, real_priors: dict, widths=LEG_WIDTHS) -> dict:
    """逐档点名次与 places_moved；越界当场抛，不留无声读数。"""
    from app.rag import retriever as rt

    out = {"corpus_is_demo_corpus": True, "bound": int(rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS),
           "widths": list(widths), "cells": []}
    for width in widths:
        pool = [dict(hit) for hit in hits[:width]]
        for state, priors in (("real_store_counts", real_priors),
                              ("synthetic_counts_on_real_filenames",
                               synthetic_priors_for([hit["source"] for hit in pool]))):
            hits_in = [dict(hit) for hit in pool]
            before = [hit["source"] for hit in hits_in]
            snapshot_before = json.dumps(hits_in, ensure_ascii=False, sort_keys=True)
            ranked = rt.rank_hits_by_activity(hits_in, priors, enabled=True)
            after = [hit["source"] for hit in ranked]
            moves = [int((hit.get("activity_prior") or {}).get("places_moved", 0))
                     for hit in ranked]
            worst = max((abs(move) for move in moves), default=0)
            if worst > out["bound"]:
                raise RuntimeError(f"位移越界：width={width} state={state} moves={moves}")
            annotated = [hit for hit in ranked if isinstance(hit, dict) and "activity_prior" in hit]
            out["cells"].append({
                "width": width, "state": state, "prior_documents": len(priors),
                "order_before": before, "order_after": after, "changed": before != after,
                "same_object_returned": ranked is hits_in,
                "annotated_hits": len(annotated),
                "places_moved": moves, "worst_abs_move": worst,
                "rank_bookkeeping_consistent": all(
                    int(hit["activity_prior"]["previous_rank"]) - position
                    == int(hit["activity_prior"]["places_moved"])
                    for position, hit in enumerate(annotated, start=1)
                    if hit["activity_prior"].get("new_rank") == position),
                "snapshot_identical_when_no_signal": (
                    ranked is hits_in
                    and snapshot_before == json.dumps(ranked, ensure_ascii=False, sort_keys=True)),
            })
    return out


# ==================== 汇总 ====================

def collect(args) -> dict:
    container_kwargs = {"container": args.container, "user": args.pg_user,
                        "database": args.pg_db}
    from app.rag import pg_store

    dsn = args.database_url
    if not dsn and args.dotenv:
        from dotenv import dotenv_values

        dsn = str(dotenv_values(args.dotenv).get("DATABASE_URL", "") or "").strip()
    dsn = dsn or pg_store.resolve_database_url()
    ef = args.ef_search or pg_store.configured_hnsw_ef_search()
    product_select = read_product_select_text()

    report = {"ticket": "R525",
              "taken_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
              "read_only": True, "ef_search_used_for_replay": ef,
              "product_select": product_select, "database_url_b": mask_dsn(dsn)}

    surface_a = census_surface_a(**container_kwargs)
    surface_b = census_surface_b(dsn)
    if args.section in ("all", "store", "reader", "gauge"):
        report["surface_a"] = surface_a
        report["surface_b"] = surface_b
    if args.section in ("all", "reader"):
        report["reader"] = reader_readings(dsn, product_select, **container_kwargs)

    ann_rows = []
    if args.section in ("all", "ann", "gauge"):
        scope_lines = surface_a.get("vector_scope") or []
        scope = str(scope_lines[0].split("|")[3]).strip() if scope_lines and len(
            scope_lines[0].split("|")) > 3 else "l2"
        dimension = int(scope_lines[0].split("|")[2]) if scope_lines else 768
        ann_rows = real_ann_topk(query_literal=random_vector_literal(dimension=dimension,
                                                                    seed=args.query_seed),
                                 limit=max(LEG_WIDTHS), ef_search=ef, scope=scope,
                                 **container_kwargs)
        report["ann"] = {"scope": scope, "dimension": dimension, "ef_search": ef,
                         "query_vector_origin": "seeded random（本单不许打模型）",
                         "rows": ann_rows}
        report["ann_selfquery"] = {
            "query_vector_origin": "真库第一枚已在位的 embedding：自证这回放真的在算名次",
            "rows": real_ann_topk(query_literal=stored_vector_literal(**container_kwargs),
                                  limit=5, ef_search=ef, scope=scope, **container_kwargs)}

    if args.section in ("all", "gauge"):
        import tempfile

        from app.rag.retriever import DocumentRetriever

        instance = DocumentRetriever(chroma_dir=tempfile.mkdtemp(prefix="r525-gauge-"),
                                     activity_prior=lambda: {})
        metadatas = [{"filename": row["filename"], "chunk_index": row["chunk_index"],
                      "classification": row["classification"],
                      "department": row["department"]} for row in ann_rows]
        hits = instance._hit_dicts([row["content_head"] for row in ann_rows], metadatas,
                                   instance.MODE_SEMANTIC, "")
        report["gauge"] = gauge(hits, real_priors=rows_to_priors(
            psql(product_select, **container_kwargs)))

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R525 活动先验真库取证（只读）")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "") or "",
                        help="面 B（宿主 PG）的 DSN；凭据不落纸")
    parser.add_argument("--dotenv", default="",
                        help="从这里现取 DATABASE_URL（命令行里因此不出现凭据）")
    parser.add_argument("--container", default=CONTAINER)
    parser.add_argument("--pg-user", default=PG_USER)
    parser.add_argument("--pg-db", default=PG_DB)
    parser.add_argument("--ef-search", type=int, default=0,
                        help="ANN 回放问的那一档；0＝现读产品真源 configured_hnsw_ef_search()")
    parser.add_argument("--query-seed", type=int, default=20260930)
    parser.add_argument("--section", default="all",
                        choices=["all", "store", "reader", "ann", "gauge"])
    parser.add_argument("--out", default="", help="JSON 产物路径；缺省写 %TEMP%")
    args = parser.parse_args(argv)

    payload = json.dumps(collect(args), ensure_ascii=False, indent=2)
    out_path = args.out or str(Path(os.getenv("TEMP") or "/tmp")
                               / "r525-activity-prior-readout.json")
    Path(out_path).write_text(payload, encoding="utf-8", newline="\n")
    print("R525 取证产物（只读）：" + out_path)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
