#!/usr/bin/env python
"""R58 判据④：Chroma 召回 vs PGVector 召回的逐题只读对比脚本。

本脚本一行都不写：连上 PostgreSQL 后立刻把会话设成 READ ONLY，Chroma 侧只调 get / query。
它回答的是"镜像能不能当读路径"（R59 的前置），不在本机证明任何事。

跑法（业主真机；已跑 migrations/0010_pgvector_chunks.sql，且双写开关开过一整轮重建）：

    python scripts/compare_vector_recall.py --k 5 --out /tmp/r58_recall_diff.json

    # 只看语料级差集、不给题目算向量（不需要 Ollama 在场）：
    python scripts/compare_vector_recall.py --skip-questions

前置（缺一条就别读结论）：
  1. 应用侧停写，或两侧都指只读副本 / 目录快照：Chroma 的 PersistentClient 对同一目录是
     单写者锁，服务在跑时这里要么报锁错误、要么读到半写状态。
  2. 已跑 0010：vector_scope 里有 schema_version=1 那一行，且列宽等于声明维度。
  3. VECTOR_DUAL_WRITE=on 之下完整重建过一次索引，否则两边数量天然不等，差异表读出来的
     是"没同步过"而不是"两个引擎不同"。
  4. 算逐题召回时本机 Ollama 在位、模型与 EMBEDDING_MODEL 一致：题向量必须由生产侧同一
     模型产出，否则比的不是同一件事（R22 口径）。本脚本不改模型、不改维度、不加重排。

退出码：0 = 逐题 top-k 全一致且两侧无集合差；1 = 有差异（正常结论，交人判读）；
2 = 前置不满足（未迁移 / 距离函数不一致 / 目录缺失 / 口径漂移），此时不输出召回结论。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.connection import open_connection, parse_database_settings  # noqa: E402
from app.rag import pg_store  # noqa: E402

DESCRIPTION = "R58 双写镜像逐题召回对比（只读，不写一行业务数据）"

#: 本脚本只发 SELECT。读 vector_scope 的语句在这里重写一遍而不复用镜像的探测常量，是因为
#: 那些常量属于写路径；一个承诺只读的工具不该依赖写路径的内部形状。表名、schema_version、
#: 口径判定仍然 import 复用，一个数字都不重抄。
_READ_SCOPE_SQL = (
    "SELECT embedding_model, dimension, distance_function "
    "FROM vector_scope WHERE schema_version = %s"
)
_READ_COLUMN_TYPE_SQL = (
    "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
    "WHERE attrelid = %s::regclass AND attname = 'embedding' "
    "AND attnum > 0 AND NOT attisdropped"
)
_READ_VECTOR_ROWS_SQL = "SELECT vector_id, index_version_id, vector_dims(embedding) AS dims FROM "
_COUNT_ALL_ZERO_SQL = "SELECT count(*) FROM "
_COUNT_CHUNK_ROWS_SQL = "SELECT count(*) FROM chunks"
_COUNT_CHUNK_EMBEDDED_SQL = "SELECT count(embedding) FROM chunks"

#: 与 0010 建向量索引时用的距离一一对应，不靠猜
DISTANCE_OPERATORS = {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}
_CHROMA_SPACES = {"l2": "l2", "euclidean": "l2", "cosine": "cosine", "ip": "inner_product"}
_TABLE_NAME = re.compile(r"[a-z_][a-z0-9_]*\Z")

DEFAULT_FIXTURES = (
    "tests/fixtures/business_evaluation_30.jsonl",
    "tests/fixtures/business_evaluation_100.jsonl",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "") or None)
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "./chroma_db"))
    parser.add_argument("--collection",
                        default=os.getenv("CHROMA_COLLECTION", "enterprise_brain"))
    parser.add_argument("--vector-table", default=pg_store.DEFAULT_VECTOR_TABLE)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--fixture", action="append", default=None,
                        help="逐题对比的题集 jsonl，可重复；默认用仓内两份评测集")
    parser.add_argument("--skip-questions", action="store_true",
                        help="只做语料级差集，不算逐题召回（不需要 embedding 模型在场）")
    parser.add_argument("--all", action="store_true", help="打印每一题，而不只打印有差异的题")
    parser.add_argument("--out", default=None, help="把结论写成 JSON，便于贴进交付说明")
    return parser.parse_args(argv)


def _safe_table(name: str) -> str:
    """表名进 SQL 之前先过白名单：这是给业主用的工具，不接受手滑带进来的引号。"""
    if not _TABLE_NAME.match(str(name)) or str(name) not in {pg_store.DEFAULT_VECTOR_TABLE,
                                                                 "chunks"}:
        raise SystemExit("[前置不满足] 不接受的表名：" + str(name))
    return str(name)


def _row(row, key: str, index: int):
    """dict_row 与裸 tuple 两种行形状都要能读：生产走前者，测试假连接走后者。"""
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _scalar(row):
    if row is None:
        return 0
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _zero_literal(dimension: int) -> str:
    return "[" + ",".join(["0.0"] * int(dimension)) + "]"


def _first_difference(left, right):
    for position in range(max(len(left), len(right))):
        left_value = left[position] if position < len(left) else None
        right_value = right[position] if position < len(right) else None
        if left_value != right_value:
            return position
    return None


def connect_read_only(url: str):
    settings = parse_database_settings(url)
    if not settings.is_postgresql:
        raise SystemExit("[前置不满足] 连接串不是 PostgreSQL：" + url)
    connection = open_connection(settings)
    try:
        connection.read_only = True  # psycopg3：会话事务只读，误写当场报错
    except Exception as exc:  # pragma: no cover - 驱动不支持时至少说清楚
        print("[warn] 无法设成 READ ONLY（" + str(exc) + "）；本脚本仍然只发 SELECT")
    return connection


def read_scope(connection, vector_table: str) -> dict:
    """读 0010 登记的口径，并确认它和运行时一致；不一致就是前置不满足。"""
    row = connection.execute(_READ_SCOPE_SQL, (pg_store.VECTOR_SCHEMA_VERSION,)).fetchone()
    if row is None:
        raise SystemExit(
            "[前置不满足] vector_scope 里没有 schema_version="
            + str(pg_store.VECTOR_SCHEMA_VERSION)
            + " 这一行：先跑 0010_pgvector_chunks.sql")
    dimension = int(_row(row, "dimension", 1) or 0)
    type_row = connection.execute(_READ_COLUMN_TYPE_SQL, (vector_table,)).fetchone()
    column_type = str(_row(type_row, "format_type", 0) or "") if type_row is not None else ""
    if column_type != "vector(" + str(dimension) + ")":
        raise SystemExit(
            "[前置不满足] " + vector_table + ".embedding 实际类型 "
            + (column_type or "不存在") + "，与声明的 vector(" + str(dimension) + ") 不符")
    stored = pg_store.VectorScope(
        embedding_model=str(_row(row, "embedding_model", 0) or ""),
        dimension=dimension,
        distance_function=str(_row(row, "distance_function", 2) or ""),
    )
    disagreements = pg_store.scope_disagreements(pg_store.configured_embedding_scope(), stored)
    if disagreements:
        raise SystemExit(
            "[前置不满足] 库里口径 model=" + stored.embedding_model
            + " dimension=" + str(stored.dimension)
            + " 与运行时不一致（" + ", ".join(disagreements) + "）：先按 R22 重建索引")
    return {
        "embedding_model": stored.embedding_model,
        "dimension": stored.dimension,
        "distance_function": stored.distance_function,
        "column_type": column_type,
    }


def open_chroma(chroma_dir: str, collection_name: str):
    directory = Path(chroma_dir)
    if not directory.exists():
        raise SystemExit("[前置不满足] Chroma 目录不存在：" + str(directory) + "（不要新建）")
    try:
        import chromadb
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("[前置不满足] chromadb 不可用：" + str(exc))
    client = chromadb.PersistentClient(path=str(directory))
    try:
        return client.get_collection(name=collection_name)
    except Exception as exc:
        raise SystemExit(
            "[前置不满足] 取不到 collection " + repr(collection_name) + "：" + str(exc))


def chroma_distance(collection) -> str:
    """collection 自己记的相似度函数；没记就返回空串，由调用方判前置。"""
    metadata = getattr(collection, "metadata", None) or {}
    space = str(metadata.get("hnsw:space", "") or "").lower()
    return _CHROMA_SPACES.get(space, "")


def chroma_all_ids(collection) -> list:
    try:
        page = collection.get(include=[])
    except Exception:
        page = collection.get()
    return sorted(str(item) for item in ((page or {}).get("ids") or []))


def corpus_drift(connection, collection, *, vector_table: str, scope: dict) -> dict:
    """语料级差集：不比分数，只比"同一批向量在不在两边"，先把镜像覆盖率钉住。

    index_version_id_null 是本单故意留的 NULL（retriever 不知道索引版本，编一个就是
    R22 的静默错位），所以它是"待发布回填"的计数，不是故障计数，读表时要分清。
    """
    pg_ids = set()
    wrong_width = []
    unversioned = 0
    for row in connection.execute(_READ_VECTOR_ROWS_SQL + vector_table).fetchall():
        vector_id = str(_row(row, "vector_id", 0))
        pg_ids.add(vector_id)
        if int(_row(row, "dims", 2) or 0) != scope["dimension"]:
            wrong_width.append(vector_id)
        if _row(row, "index_version_id", 1) is None:
            unversioned += 1
    chroma_ids = set(chroma_all_ids(collection))
    zero_row = connection.execute(
        _COUNT_ALL_ZERO_SQL + vector_table + " WHERE embedding = %s::vector",
        (_zero_literal(scope["dimension"]),),
    ).fetchone()
    return {
        "pg_vectors": len(pg_ids),
        "chroma_vectors": len(chroma_ids),
        "only_in_pg": sorted(pg_ids - chroma_ids),
        "only_in_chroma": sorted(chroma_ids - pg_ids),
        "wrong_width": wrong_width,
        "all_zero_rows": int(_scalar(zero_row) or 0),
        "index_version_id_null": unversioned,
        "chunks_rows": int(_scalar(connection.execute(_COUNT_CHUNK_ROWS_SQL).fetchone()) or 0),
        "chunks_with_backfilled_embedding": int(
            _scalar(connection.execute(_COUNT_CHUNK_EMBEDDED_SQL).fetchone()) or 0
        ),
    }


def load_questions(paths) -> list:
    questions = []
    for path in paths:
        file_path = ROOT / path if not Path(path).is_absolute() else Path(path)
        if not file_path.exists():
            raise SystemExit("[前置不满足] 题集不存在：" + str(file_path))
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            question = str(item.get("question", "")).strip()
            if question:
                questions.append((file_path.name, str(item.get("id", "")), question))
    return questions


def pg_recall(connection, *, vector_table: str, operator: str, literal: str, k: int) -> list:
    rows = connection.execute(
        "SELECT vector_id, embedding " + operator + " %s::vector AS distance"
        " FROM " + vector_table +
        " ORDER BY embedding " + operator + " %s::vector LIMIT %s",
        (literal, literal, k),
    ).fetchall()
    return [str(_row(row, "vector_id", 0)) for row in rows]


def _print_drift(drift: dict) -> None:
    for key in ("pg_vectors", "chroma_vectors", "chunks_rows",
                "chunks_with_backfilled_embedding", "index_version_id_null",
                "all_zero_rows"):
        print("%-32s %s" % (key, drift[key]))
    for key in ("only_in_pg", "only_in_chroma", "wrong_width"):
        print("%-32s %s" % (key, len(drift[key])))
        for vector_id in drift[key][:20]:
            print("    " + vector_id)


def _write_out(args, result: dict) -> None:
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("结论已写出：" + args.out)


def main(argv=None) -> int:
    args = parse_args(argv)
    vector_table = _safe_table(args.vector_table)
    connection = connect_read_only(args.database_url or pg_store.resolve_database_url())
    try:
        scope = read_scope(connection, vector_table)
        collection = open_chroma(args.chroma_dir, args.collection)
        space = chroma_distance(collection)
        if space != scope["distance_function"]:
            print("[前置不满足] collection 距离=" + (space or "未记录")
                  + "，vector_scope 声明=" + scope["distance_function"])
            print("两边排序天然不同，不出召回结论；先核对 0010 的 app.vector_distance_function")
            return 2
        drift = corpus_drift(connection, collection, vector_table=vector_table, scope=scope)
        result = {"scope": scope, "k": args.k, "drift": drift, "questions": [], "summary": {}}
        print("-- 口径：" + scope["embedding_model"] + " / "
              + str(scope["dimension"]) + " 维 / " + scope["distance_function"] + " --")
        _print_drift(drift)
        gap = bool(drift["only_in_pg"] or drift["only_in_chroma"])

        if args.skip_questions:
            print("-- 逐题对比已跳过（--skip-questions）--")
            result["summary"] = {"skipped_questions": True, "corpus_gap": gap}
            _write_out(args, result)
            return 1 if gap else 0

        from app.rag.retriever import OllamaEmbeddings  # 要发 embedding：延后 import

        embedder = OllamaEmbeddings()
        questions = load_questions(args.fixture or list(DEFAULT_FIXTURES))
        differing = 0
        print("-- 逐题 top-%d（共 %d 题）--" % (args.k, len(questions)))
        for source, question_id, question in questions:
            vector = list(embedder.embed_query(question))
            literal = "[" + ",".join(repr(float(value)) for value in vector) + "]"
            pg_ids = pg_recall(connection, vector_table=vector_table,
                               operator=DISTANCE_OPERATORS[space], literal=literal, k=args.k)
            hit = collection.query(query_embeddings=[vector], n_results=args.k)
            chroma_ids = [str(item) for item in ((hit.get("ids") or [[]])[0] or [])]
            same = pg_ids == chroma_ids
            first_diff = _first_difference(chroma_ids, pg_ids)
            differing += 0 if same else 1
            if args.all or not same:
                print("%s %s %s first_diff_rank=%s" % (
                    source, question_id, "OK  " if same else "DIFF", first_diff))
                print("    chroma: " + repr(chroma_ids))
                print("    pg    : " + repr(pg_ids))
            result["questions"].append({
                "source": source, "id": question_id, "question": question,
                "chroma": chroma_ids, "pg": pg_ids, "same": same,
                "first_diff_rank": first_diff,
            })
        result["summary"] = {"questions": len(questions), "differing": differing,
                             "corpus_gap": gap}
        print("-- 汇总：%d/%d 题 top-%d 不一致%s --" % (
            differing, len(questions), args.k, "（另有语料级差集）" if gap else ""))
        _write_out(args, result)
        return 1 if differing or gap else 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
