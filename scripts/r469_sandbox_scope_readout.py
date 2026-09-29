# -*- coding: utf-8 -*-
"""R469 驱动：在 compose 网络里的真 PostgreSQL 上，把 C 门检索侧那格从「空集」量成「有牙读数」。

跑法（在册口径＝容器里的真库；宿主 5432 上挂着野 PG，宿主直连＝全绿也是假绿，计划书 §9.4）：

    docker exec -e INDEX_BACKEND=pgvector -i enterprise-brain-backend-1 `
        /app/.venv/bin/python - < scripts/r469_sandbox_scope_readout.py

🔴 09-28 现读订正纸上那条解释器：本镜像里 `/usr/local/bin/python` **没有项目依赖**——它 import
`app.rag.pg_store` 会在 `app/rag/retriever.py` 那句 `from dotenv import load_dotenv` 当场
`ModuleNotFoundError: No module named 'dotenv'`。带依赖的是 `/app/.venv/bin/python`
（`/app/BUILD_INFO` 记的 revision 与本树基点同一枚）。照抄纸上那条只会得到一条与召回无关的红。

这一格怎么才有牙：生产/演示库 1008 枚向量 `department` 全空、`classification` 全 = 1（§133 六），
谓词只能全挡死或全放行 ⇒ 「越权 0 条」是空集真。本件把用在册 `scripts/r59c_sandbox_corpus.py`
造的 72 枚带标签合成向量（`vector_id` 前缀 `r59c-`）写进**在册沙盒库** `eb_r59_sandbox`
（R382 那批件用的同一枚），用产品自己的作用域函数下推谓词、走产品自己的 pgvector 读腿取读数，
每一档同时取一臂**不带谓词**的对照——那臂里被 `allows()` 判为越界的条数，就是"这格有东西可判"的证明。
量完按点名 id 删除，前后各取一次存量恒量。

三条硬边界（本件自己拦，不靠人记）
--------------------------------
* 生产库那枚连接一开就把会话设成 READ ONLY，且证明先于任何一条语句；写只可能落在沙盒库。
* 沙盒库名必须逐字等于 `eb_r59_sandbox`，且开跑前 `vector_id LIKE 'r59c%'` 必须为 0 枚——
  不为 0 就是上一班漏了，本件拒跑（不是"先清一清再说"）。
* 零模型：查询向量一律取 r59c 语料自身的确定性向量（LCG 几何夹具），一条 embed 都不发。

口令不进任何输出：`DATABASE_URL` 只以 mask 形状出现；沙盒库连接串由生产串就地换库名得到，
口令留在进程内。stdout 只交回一份 JSON 证据，交总控用 `scripts/r469_readout_lib.py render` 出表。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

SANDBOX_DB = "eb_r59_sandbox"          # 在册沙盒库（scripts/r382_*.py 那批件用的同一枚）
PRODUCTION_DB = "enterprise_brain"      # docker-compose.yml x-runtime 里的缺省库名
EXIT_OK = 0
EXIT_RED = 1
EXIT_PRECONDITION = 2
EXIT_REFUSED = 3

TOOL = "scripts/r469_sandbox_scope_readout.py"
CORE_TABLES = ("chunk_vectors", "documents", "document_versions",
               "dataset_versions", "resource_versions", "users")


def mask_url(url: str) -> str:
    """把口令换成 *** ，其余照原样——账上要看得见连的是哪台哪库哪口。"""
    if "@" not in url:
        return "<unset>"
    head, tail = url.split("@", 1)
    scheme, sep, credential = head.partition("://")
    user = credential.split(":", 1)[0] if sep else credential
    return "{0}{1}{2}:***@{3}".format(scheme, sep or "//", user, tail)


def swap_database(url: str, database: str) -> str:
    """只换库名，其余一字不动（口令不进输出，也不落盘）。"""
    query = ""
    base = url
    if "?" in base:
        base, _, query = base.partition("?")
        query = "?" + query
    head, sep, _tail = base.rpartition("/")
    if not sep or not head:
        raise SystemExit("[前置不满足] DATABASE_URL 形状不认识，无法就地换库名：" +
                         mask_url(base))
    return head + "/" + database + query


def open_connection(url: str):
    """唯一连接入口＝`app.db.connection`（R238 的边界；本件不许裸 psycopg.connect）。"""
    from app.db.connection import open_connection as boundary_open, parse_database_settings

    return boundary_open(parse_database_settings(url))


def server_identity(connection) -> dict:
    """连的是哪台哪库哪口，现场取。宿主 5432 上那台野 PG 就是靠这一格对出来的。"""
    row = connection.execute(
        "SELECT current_database(), current_user, inet_server_addr()::text, "
        "inet_server_port(), version()").fetchone()
    return {"database": str(row[0]), "user": str(row[1]), "server_addr": str(row[2]),
            "server_port": int(row[3]) if row[3] is not None else None,
            "version": str(row[4]),
            "transaction_read_only": str(
                connection.execute("SHOW transaction_read_only").fetchone()[0]).lower()}


def prove_read_only(connection) -> dict:
    """把会话钉成只读，再把证明取回来——SET 必须排在任何一条取数语句之前。"""
    connection.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    connection.commit()
    return server_identity(connection)


def counts(connection) -> dict:
    return {table: int(connection.execute("SELECT count(*) FROM " + table).fetchone()[0])
            for table in CORE_TABLES}


def label_block(connection, prefix: str) -> dict:
    """标签分布现场读数。注意 `classification` 是 integer，判空一律用 IS NULL / <> ''，
    拿空串判 integer 那三张表会 `invalid input syntax for type integer: ""` 当场炸（§133 六）。"""
    row = connection.execute(
        "SELECT count(*) AS rows_total, "
        "count(*) FILTER (WHERE department <> '') AS dept_nonempty, "
        "count(*) FILTER (WHERE department = '') AS dept_empty, "
        "count(DISTINCT department) AS distinct_departments, "
        "count(DISTINCT classification) AS distinct_classifications, "
        "count(DISTINCT (department, classification)) AS distinct_pairs, "
        "count(*) FILTER (WHERE vector_id LIKE %s) AS prefixed_rows "
        "FROM chunk_vectors", (prefix + "%",)).fetchone()
    dist = {str(key): int(value) for key, value in connection.execute(
        "SELECT classification, count(*) FROM chunk_vectors "
        "GROUP BY classification ORDER BY classification").fetchall()}
    departments = [str(item[0]) for item in connection.execute(
        "SELECT DISTINCT department FROM chunk_vectors ORDER BY department").fetchall()]
    classifications = [str(item[0]) for item in connection.execute(
        "SELECT DISTINCT classification FROM chunk_vectors ORDER BY classification").fetchall()]
    return {"rows_total": int(row[0]), "nonempty_department": int(row[1]),
            "dept_empty": int(row[2]), "distinct_departments_all": int(row[3]),
            "distinct_classifications_all": int(row[4]), "distinct_pairs": int(row[5]),
            "prefixed_rows": int(row[6]),
            "classification_distribution": dist,
            "departments": departments, "classifications": classifications,
            "r59c_rows": int(row[6])}


def labelled_block(connection, prefix: str) -> dict:
    """四件判据里 (b) 要的那本账：非空部门、部门档、密级档、叉乘格；r59c 那批单列。"""
    block = label_block(connection, prefix)
    pairs = connection.execute(
        "SELECT DISTINCT department, classification FROM chunk_vectors "
        "WHERE vector_id LIKE %s ORDER BY department, classification",
        (prefix + "%",)).fetchall()
    r59c_depts = sorted({str(dept) for dept, _level in pairs})
    r59c_levels = sorted({str(level) for _dept, level in pairs})
    return {
        "rows_total": block["rows_total"],
        "nonempty_department": block["nonempty_department"],
        "dept_empty": block["dept_empty"],
        "distinct_departments": block["departments"],
        "distinct_classifications": block["classifications"],
        "distinct_pairs": block["distinct_pairs"],
        "classification_distribution": block["classification_distribution"],
        "r59c_rows": block["prefixed_rows"],
        "r59c_distinct_pairs": len(pairs),
        "r59c_departments": r59c_depts,
        "r59c_classifications": r59c_levels,
    }


def pool_rows(connection) -> list:
    rows = connection.execute(
        "SELECT vector_id, department, classification FROM chunk_vectors "
        "ORDER BY vector_id").fetchall()
    return [{"id": str(vector_id), "department": str(department or ""),
             "classification": classification}
            for vector_id, department, classification in rows]


def pool_embeddings(connection) -> dict:
    """暴力精确解要的向量：一次全量读，只读 `vector_id` 与 `embedding` 两列。"""
    rows = connection.execute(
        "SELECT vector_id, embedding::text FROM chunk_vectors ORDER BY vector_id").fetchall()
    return {str(vector_id): json.loads(text) for vector_id, text in rows}


def accounts_block(connection) -> dict:
    row = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE COALESCE(department, '') <> ''), "
        "count(*) FILTER (WHERE COALESCE(department, '') <> '' AND role <> 'admin') "
        "FROM users").fetchone()
    named = connection.execute(
        "SELECT username, COALESCE(department, '<NULL>'), role FROM users "
        "ORDER BY username").fetchall()
    return {"users_total": int(row[0]), "users_with_department": int(row[1]),
            "non_admin_accounts_with_department": int(row[2]),
            "rows": [{"username": str(username), "department": str(department),
                      "role": str(role)} for username, department, role in named]}


def refuse(code: int, message: str, *connections) -> int:
    """退出前把连接一律收掉：被拒的一趟不许在库里留一条悬着的会话。"""
    print(message, file=sys.stderr)
    for connection in connections:
        if connection is None:
            continue
        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass
    return code


def hit_shape(row: dict) -> dict:
    """读腿交回的一行，压成判据要的形状（只留 id 与两维标签，正文一个字都不进证据）。"""
    return {"id": str(row.get("vector_id")),
            "department": str(row.get("department") or ""),
            "classification": row.get("classification")}


def make_principal(spec: dict):
    """主体形状照抄在册件 `scripts/r59c_sandbox_corpus.py:161-174` 的 load_scope_resolver，
    role/clearance/department 三件决定谓词，本件不自立第四种主体形状。"""
    from app.agents.contracts import Principal

    return Principal(user_id=spec["username"], username=spec["username"],
                     roles=[spec["role"]], permissions=[],
                     department=spec["department"], department_ids=[],
                     clearance=int(spec["clearance"]), status="active")


def measure_arm(*, url: str, prefix: str, anchors: list, anchor_vectors: dict, k: int,
                exact_pool: bool, r59c) -> dict:
    """一臂的逐档读数：谓词由产品本体下推，命中由产品本体 `allows()` 逐条复核。"""
    from app.rag import pg_store
    from app.rag.filters import resolve_document_retrieval_scope

    conn = open_connection(url)
    try:
        rows = pool_rows(conn)
        labels = labelled_block(conn, prefix)
        embeddings = pool_embeddings(conn) if exact_pool else {}
    finally:
        conn.rollback()
        conn.close()

    tiers = []
    breaches_live = 0
    for spec in r59c.PRINCIPALS:
        scope = resolve_document_retrieval_scope(make_principal(spec))
        admitted = [row for row in rows if scope.allows(row)]
        outside = [row for row in rows if not scope.allows(row)]
        embedded = ([{"vector_id": row["id"], "embedding": embeddings[row["id"]]}
                    for row in admitted] if exact_pool else None)
        reads = []
        for anchor in anchors:
            query_vector = anchor_vectors[anchor]
            scoped = pg_store.read_topk(query_vector=query_vector, k=k,
                                        where=scope.filters, url=url)
            unscoped = pg_store.read_topk(query_vector=query_vector, k=k,
                                          where=None, url=url)
            for hit in scoped:
                if not scope.allows(hit_shape(hit)):
                    breaches_live += 1
            reads.append({
                "anchor": anchor, "k": int(k),
                "scoped": [hit_shape(hit) for hit in scoped],
                "unscoped": [hit_shape(hit) for hit in unscoped],
                "exact": (r59c.exact_topk(query_vector, embedded, k) if embedded else None),
            })
        tiers.append({
            "label": spec["label"], "username": spec["username"], "role": spec["role"],
            "department": spec["department"], "clearance": int(spec["clearance"]),
            "expect": spec["expect"], "scope_reason": scope.reason_code,
            "filters": dict(scope.filters),
            "levels": sorted(scope.classification_levels),
            "departments": None if scope.departments is None else sorted(scope.departments),
            "pool_total": len(rows), "admitted_total": len(admitted),
            "outside_sample": outside[0] if outside else None,
            "r59c_admitted_ids": sorted(row["id"] for row in admitted
                                        if row["id"].startswith(prefix)),
            "reads": reads,
        })
    return {"tiers": tiers, "pool_rows": len(rows), "pool_labels": labels,
            "live_breaches": breaches_live}


def write_sandbox_rows(connection, corpus: dict, prefix: str, columns: set,
                       provenance: dict) -> int:
    """唯一写点：只写 r59c 自己造的、`vector_id` 带在册前缀的合成行。

    用裸 INSERT（不带 ON CONFLICT）是刻意的：撞键就整笔回滚，而不是把别人那一行覆盖掉。
    列集合先与 information_schema 现读对一遍——schema 漂了要在这里响，不要在库里响。
    """
    wanted = {"vector_id", "filename", "chunk_index", "content", "classification",
              "department", "content_sha256", "index_version_id", "embedding",
              "embedding_model", "embedding_dimension", "distance_function"}
    missing = sorted(wanted - columns)
    if missing:
        raise SystemExit("[前置不满足] 目标表没有这些列，本件不许猜 schema：" +
                         ",".join(missing))
    from app.rag import pg_store

    rows = []
    for chunk in corpus["chunks"]:
        if not chunk["vector_id"].startswith(prefix):
            raise SystemExit("[拒绝写入] 语料里出现不带在册前缀的 vector_id：" +
                             chunk["vector_id"])
        rows.append((
            chunk["vector_id"], chunk["filename"], int(chunk["chunk_index"]),
            chunk["content"], int(chunk["classification"]), chunk["department"],
            hashlib.sha256(chunk["content"].encode("utf-8")).hexdigest(), None,
            pg_store._vector_literal(chunk["embedding"]),
            provenance["embedding_model"], corpus["dimension"],
            provenance["distance_function"]))
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO chunk_vectors (vector_id, filename, chunk_index, content, "
            "classification, department, content_sha256, index_version_id, embedding, "
            "embedding_model, embedding_dimension, distance_function) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s)", rows)
    connection.commit()
    return len(rows)


def r59c_provenance(r59c) -> dict:
    """合成行的来历标签取自在册件本体，本文件一枚字面量都不抄（R393 同一条纪律）。

    前缀也不抄：它由该件自己的 `vector_id` 现生（`r59c_sandbox_corpus.py:145` 那串形状）取公共前缀，
    抄成第二份 `"r59c-"` 就等于给下一班留一枚会漂的数。
    """
    sample = r59c.build_corpus(len(r59c.DEPARTMENTS) * len(r59c.CLASSIFICATIONS) * 2,
                               dimension=r59c.VECTOR_DIMENSION)
    prefix = os.path.commonprefix([row["vector_id"] for row in sample["chunks"]])
    if not prefix or not prefix.endswith("-"):
        raise SystemExit("[前置不满足] 取不到在册前缀（拿到 {0!r}）：本件不许自定前缀".format(prefix))
    return {"embedding_model": r59c.EMBEDDING_MODEL_LABEL,
            "distance_function": r59c.DISTANCE_FUNCTION,
            "prefix": prefix, "tool": r59c.TOOL, "schema": r59c.SCHEMA}


def delete_sandbox_rows(connection, ids: list) -> int:
    """清理用产品自己的那条删除语句（`app.rag.pg_store._DELETE_VECTOR_SQL`），点名删。"""
    from app.rag import pg_store

    with connection.cursor() as cursor:
        cursor.execute(pg_store._DELETE_VECTOR_SQL, (list(ids),))
        deleted = int(cursor.rowcount or 0)
    connection.commit()
    return deleted


def derive_anchors(corpus: dict) -> list:
    """锚点＝每个 (部门,密级) 叉乘格里 id 最小那一枚，查询向量取该行自己的 embedding（自探针）。

    为什么不用 r59c 那批 `sbx-NN` 探针：它的 seed 算式（`5000 + i * 104729`）在那件里已经写了
    两遍（`:236` 与 `:460`），本件再写就是第三遍——R393 那条「数抄进第二处就一定会漂」同样管算式。
    锚点枚数也不抄题数：它等于该件自己的取值域叉乘 `DEPARTMENTS × CLASSIFICATIONS`。
    """
    first: dict = {}
    for chunk in corpus["chunks"]:
        key = (chunk["department"], chunk["classification"])
        current = first.get(key)
        if current is None or chunk["vector_id"] < current["vector_id"]:
            first[key] = chunk
    return [first[key]["vector_id"] for key in sorted(first)]


def r59c_module_sha(r59c) -> str:
    path = Path(getattr(r59c, "__file__", "") or "")
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("full", "preflight"), default="full",
                        help="preflight＝零写入，只取证与自证（开窗前跑一遍用）")
    parser.add_argument("--ordinals", type=int, default=6,
                        help="每枚 (部门,密级) 格造几行；本单规模参数，非真源常量")
    parser.add_argument("--top-k", type=int, default=5,
                        help="每读取几名；与计划书 §9.2 那轮同档，本单参数")
    parser.add_argument("--base-commit", default="", help="施工树基点，只作账面留痕")
    args = parser.parse_args(argv)

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        import scripts.r59c_sandbox_corpus as r59c
    except Exception as exc:
        print("[前置不满足] 取不到在册件 scripts/r59c_sandbox_corpus.py："
              "{0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return EXIT_PRECONDITION

    from app.rag import pg_store

    provenance = r59c_provenance(r59c)
    prefix = provenance["prefix"]
    if r59c.TABLE != pg_store.DEFAULT_VECTOR_TABLE:
        print("[前置不满足] 两本在册账对不上表名：{0} 说 {1!r}，{2} 说 {3!r}".format(
            r59c.TOOL, r59c.TABLE, "app.rag.pg_store", pg_store.DEFAULT_VECTOR_TABLE),
            file=sys.stderr)
        return EXIT_PRECONDITION
    url = str(os.getenv("DATABASE_URL", "") or "").strip()
    if not url:
        print("[前置不满足] DATABASE_URL 未设：本件不许自造 DSN", file=sys.stderr)
        return EXIT_PRECONDITION
    sandbox_url = swap_database(url, SANDBOX_DB)

    # ---- 生产库：先钉只读，再取存量恒量（这一枚会话上不可能出现写句） ----------------
    production = open_connection(url)
    production_identity = prove_read_only(production)
    if (production_identity["database"] != PRODUCTION_DB
            or PRODUCTION_DB not in r59c.PRODUCTION_DB_NAMES
            or PRODUCTION_DB == SANDBOX_DB):
        return refuse(EXIT_REFUSED, "[拒绝] 生产侧连到的是 {0!r}，不是 {1!r}".format(
            production_identity["database"], PRODUCTION_DB), production)
    if production_identity["transaction_read_only"] != "on":
        return refuse(EXIT_REFUSED, "[拒绝] 生产会话没能自证只读（{0}）".format(
            production_identity["transaction_read_only"]), production)
    core_before = counts(production)
    labels_before = production_snapshot(production, prefix)
    accounts = accounts_block(production)

    # ---- 沙盒库：库名逐字相等 + 在册前缀零枚残留，两枚守卫都硬拦 ----------------------
    sandbox = open_connection(sandbox_url)
    sandbox_identity = server_identity(sandbox)          # 这枚是写入目标，不设只读
    if sandbox_identity["database"] != SANDBOX_DB:
        return refuse(EXIT_REFUSED, "[拒绝] 写入目标连到的是 {0!r}，不是沙盒库 {1!r}".format(
            sandbox_identity["database"], SANDBOX_DB), production, sandbox)
    try:
        mirror = pg_store.vector_mirror(url=sandbox_url)
    except Exception as exc:
        return refuse(EXIT_PRECONDITION, "[前置不满足] 沙盒库过不了产品自己的镜像闸："
                      "{0}: {1}".format(type(exc).__name__, str(exc)[:200]),
                      production, sandbox)
    if mirror is None:
        return refuse(EXIT_PRECONDITION, "[前置不满足] {0} 没开：读腿自己会拒答，本班不测".format(
            pg_store.DUAL_WRITE_ENV), production, sandbox)
    scope_row = mirror.scope.as_dict()
    mirror.close()
    if scope_row["distance_function"] != provenance["distance_function"]:
        return refuse(EXIT_PRECONDITION, "[前置不满足] 沙盒库距离算符是 {0!r}，r59c 语料按 "
                      "{1!r} 造，不匹配就不测".format(scope_row["distance_function"],
                                          provenance["distance_function"]),
                      production, sandbox)
    columns = {str(row[0]) for row in sandbox.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (r59c.TABLE,)).fetchall()}
    sandbox_before = sandbox_snapshot(sandbox, prefix)
    if int(sandbox_before["prefixed_rows"]) != 0:
        return refuse(EXIT_PRECONDITION, "[前置不满足] 沙盒库里已有 {0} 枚 {1} 行——"
                      "上一班漏了，本班拒跑（不是先清一清再说）".format(
                          sandbox_before["prefixed_rows"], prefix), production, sandbox)

    corpus = r59c.build_corpus(len(r59c.DEPARTMENTS) * len(r59c.CLASSIFICATIONS) *
                               args.ordinals, dimension=scope_row["dimension"])
    anchors = derive_anchors(corpus)
    anchor_vectors = {chunk["vector_id"]: chunk["embedding"] for chunk in corpus["chunks"]}
    read_backend = read_backend_default()
    ef_search = pg_store.configured_hnsw_ef_search()

    if args.mode == "preflight":
        print(json.dumps({"mode": "preflight", "production_identity": production_identity,
                          "sandbox_identity": sandbox_identity, "core_six": core_before,
                          "production_labels": labels_before, "accounts": accounts,
                          "sandbox": sandbox_before, "vector_scope": scope_row,
                          "read_backend_default": read_backend, "hnsw_ef_search": ef_search,
                          "hnsw_ef_search_source": r59c.TRUE_SOURCE,
                          "database_url_masked": {"production": mask_url(url),
                                                  "sandbox": mask_url(sandbox_url)}},
                         ensure_ascii=False, sort_keys=True))
        return refuse(EXIT_OK, "[preflight] 零写入：两枚会话都已收掉", production, sandbox)

    # ---- 唯一写点：沙盒库里的 r59c 合成行 -------------------------------------------
    inserted = write_sandbox_rows(sandbox, corpus, prefix, columns, provenance)
    try:
        sandbox_arm = measure_arm(url=sandbox_url, prefix=prefix, anchors=anchors,
                                  anchor_vectors=anchor_vectors, k=args.top_k,
                                  exact_pool=True, r59c=r59c)
        production_arm = measure_arm(url=url, prefix=prefix, anchors=anchors,
                                     anchor_vectors=anchor_vectors, k=args.top_k,
                                     exact_pool=False, r59c=r59c)
        deleted = delete_sandbox_rows(sandbox, [chunk["vector_id"]
                                                for chunk in corpus["chunks"]])
        sandbox_after = sandbox_snapshot(sandbox, prefix)
        core_after = counts(production)
        labels_after = production_snapshot(production, prefix)
        production_final_identity = server_identity(production)
    finally:
        for connection in (sandbox, production):
            try:
                connection.rollback()
                connection.close()
            except Exception:
                pass

    leftover = int(sandbox_after["prefixed_rows"])
    if leftover != 0 or deleted != inserted:
        print("[红] 清理不彻底：删了 {0} 枚、应有 {1} 枚、残留 {2} 枚".format(
            deleted, inserted, leftover), file=sys.stderr)
        return EXIT_RED
    if core_before != core_after or production_final_identity["transaction_read_only"] != "on":
        print("[红] 生产侧恒量或只读自证不过关", file=sys.stderr)
        return EXIT_RED

    evidence = build_evidence(
        started_at=started_at, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        args=args, r59c=r59c, corpus=corpus, anchors=anchors, prefix=prefix, url=url,
        sandbox_url=sandbox_url, production_identity=production_identity,
        production_final_identity=production_final_identity,
        sandbox_identity=sandbox_identity, scope_row=scope_row, read_backend=read_backend,
        ef_search=ef_search, core_before=core_before, core_after=core_after,
        labels_before=labels_before, labels_after=labels_after, accounts=accounts,
        sandbox_before=sandbox_before, sandbox_after=sandbox_after,
        inserted=inserted, deleted=deleted, leftover=leftover,
        production_arm=production_arm, sandbox_arm=sandbox_arm, pg_store=pg_store)
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    if evidence["arms"]["sandbox"]["live_breaches"]:
        print("[红] 下推谓词漏放行 {0} 条".format(
            evidence["arms"]["sandbox"]["live_breaches"]), file=sys.stderr)
        return EXIT_RED
    return EXIT_OK


def read_backend_default() -> dict:
    """默认读后端翻没翻：先报这条进程拿到的 env，再把 env 摘掉读一次镜像里的缺省。

    `docker exec -e INDEX_BACKEND=pgvector` 是给本班这条读腿用的，不等于客户机器上翻了默认；
    两枚数分开记，才读得出「翻默认仍是业主动作」那句在册口径。
    """
    from app.rag import indexing

    this_process = str(indexing.read_backend())
    env_name = indexing.INDEX_BACKEND_ENV
    saved = os.environ.pop(env_name, None)
    try:
        shipped = str(indexing.read_backend())
    finally:
        if saved is not None:
            os.environ[env_name] = saved
    return {"this_process": this_process, "env_name": env_name, "shipped_default": shipped}


def production_snapshot(connection, prefix: str) -> dict:
    """生产侧的标签账：四件判据里 (b) 要的读数 + users 那枚 (a) 的事实。"""
    block = labelled_block(connection, prefix)
    block["users_with_department"] = accounts_block(connection)["users_with_department"]
    return block


def sandbox_snapshot(connection, prefix: str) -> dict:
    """沙盒侧的恒量：行数、标签分布、在册前缀残留枚数。"""
    block = label_block(connection, prefix)
    return {"rows_total": block["rows_total"], "dept_empty": block["dept_empty"],
            "nonempty_department": block["nonempty_department"],
            "classification_distribution": block["classification_distribution"],
            "distinct_pairs": block["distinct_pairs"],
            "prefixed_rows": block["prefixed_rows"]}


def build_revision() -> str:
    """镜像里 BUILD_INFO 记的那枚 revision：对上一遍「读的就是这棵树」的账。"""
    for candidate in (Path("/app/BUILD_INFO"), Path("BUILD_INFO")):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("revision="):
                    return line.split("=", 1)[1].strip()
    return ""


def build_evidence(**parts) -> dict:
    """把两臂读数、六枚恒量、清理账拼成一份证据；表怎么读由 r469_readout_lib 判。"""
    args = parts["args"]
    r59c = parts["r59c"]
    corpus = parts["corpus"]
    production_arm = parts["production_arm"]
    sandbox_arm = parts["sandbox_arm"]
    prefix = parts["prefix"]
    url = parts["url"]
    sandbox_url = parts["sandbox_url"]
    pg_store = parts["pg_store"]
    return {
        "schema": "r469-scope-readout-1", "ticket": "R469", "generated_by": TOOL,
        "renderer": "scripts/r469_readout_lib.py",
        "run": {
            "started_at": parts["started_at"], "finished_at": parts["finished_at"],
            "container": os.getenv("HOSTNAME", ""), "python": sys.executable,
            "cwd": os.getcwd(), "mode": args.mode, "base_commit": args.base_commit,
            "image_revision": build_revision(),
            "r59c_path": str(getattr(r59c, "__file__", "")),
            "r59c_sha256": r59c_module_sha(r59c),
            "hnsw_ef_search": parts["ef_search"],
            "hnsw_ef_search_source": r59c.TRUE_SOURCE,
            "read_backend": parts["read_backend"],
            "dual_write": os.getenv(pg_store.DUAL_WRITE_ENV, "<unset>"),
            "embedding_model_env": os.getenv("EMBEDDING_MODEL", "<unset>"),
            "vector_scope": parts["scope_row"],
            "database_url_masked": {"production": mask_url(url),
                                    "sandbox": mask_url(sandbox_url)},
            "production_identity": parts["production_identity"],
            "production_identity_after": parts["production_final_identity"],
            "sandbox_identity": parts["sandbox_identity"],
            "production_read_leg_note": (
                "生产侧取证与读数都只 SELECT：取证走本件那枚会话级 READ ONLY；读腿自己的"
                "连接由 pg_store.read_topk 管，它 finally 里 close 且从不 commit"
                "（那件里 Reads never commit 那句在册注释就是这件事的凭据）"),
        },
        "corpus": {
            "schema": corpus["schema"], "tool": corpus["tool"],
            "chunks": len(corpus["chunks"]), "dimension": corpus["dimension"],
            "distance_function": corpus["distance_function"],
            "embedding_model": corpus["embedding_model"],
            "corpus_sha": r59c.corpus_sha(corpus),
            "departments": list(r59c.DEPARTMENTS),
            "classifications": list(r59c.CLASSIFICATIONS),
            "vector_id_prefix": prefix, "top_k": int(args.top_k),
            "ordinals_per_cell": int(args.ordinals), "anchors": parts["anchors"],
        },
        "invariants": {
            "core_six": {"tables": list(CORE_TABLES), "before": parts["core_before"],
                         "after": parts["core_after"],
                         "match": parts["core_before"] == parts["core_after"]},
            "production_labels": {"before": parts["labels_before"],
                                  "after": parts["labels_after"],
                                  "match": parts["labels_before"] == parts["labels_after"]},
            "production_accounts": parts["accounts"],
            "sandbox": {"before": parts["sandbox_before"], "after": parts["sandbox_after"],
                        "match": parts["sandbox_before"] == parts["sandbox_after"]},
        },
        "arms": {
            "production": {"database": parts["production_identity"]["database"],
                           "pool_total": production_arm["pool_rows"], "writes": 0,
                           "pool_labels": production_arm["pool_labels"],
                           "tiers": production_arm["tiers"],
                           "live_breaches": production_arm["live_breaches"]},
            "sandbox": {"database": parts["sandbox_identity"]["database"],
                        "pool_total": sandbox_arm["pool_rows"],
                        "writes": parts["inserted"],
                        "pool_labels": sandbox_arm["pool_labels"],
                        "tiers": sandbox_arm["tiers"],
                        "live_breaches": sandbox_arm["live_breaches"]},
        },
        "cleanup": {
            "write_shape": "INSERT INTO chunk_vectors（唯一写点，只写 {0} 前缀行，"
                           "不带 ON CONFLICT：撞键整笔回滚，不覆盖别人那一行）".format(prefix),
            "inserted": parts["inserted"],
            "delete_sql_source": "app.rag.pg_store._DELETE_VECTOR_SQL",
            "deleted": parts["deleted"],
            "leftover_prefixed_rows": parts["leftover"],
            "vacuum_or_reindex": False,
        },
    }


if __name__ == "__main__":
    sys.exit(main())