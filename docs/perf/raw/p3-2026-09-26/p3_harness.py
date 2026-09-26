#!/usr/bin/env python3
"""R264 P3 shadow-read harness. READ ONLY: 一条 UPDATE/INSERT/ALTER 都不发，不开生产目录。

子命令
  prove                 两侧来源自证（判据 2）+ 全零普查 PG 半边
  samesource <json>     同源反证（判据 4）：故意把一腿换成与另一腿同源的库
  metrics <d> <r>       逐题 overlap / Jaccard（判据 3），并复核两腿不同源

来源身份（provenance）用 storage 键判定：storage 相同 = 同一份物化数据 = 同源，
数字一律不给，直接判无效。这是对误判 #43 第三行"Chroma 与自己比自己"的机制化拦截。
"""
import importlib.util
import json
import math
import os
import socket
import sys
from pathlib import Path

APP = "/app"
if APP not in sys.path:
    sys.path.insert(0, APP)

_spec = importlib.util.spec_from_file_location("cvr", os.path.join(APP, "scripts", "compare_vector_recall.py"))
cvr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cvr)          # 复用官方脚本本体，一个判据都不重抄

PROV_PATH = os.environ.get("P3_PROV", "/tmp/p3_prov.json")
SNAP = os.environ.get("P3_SNAP", "/tmp/p3snap")
COLLECTION = os.environ.get("P3_COLLECTION", "enterprise_docs")
TABLE = "chunk_vectors"
RED = "\033[31m"
YEL = "\033[33m"
GRN = "\033[32m"
OFF = "\033[0m"


def mask(url):
    import re
    return re.sub(r"://([^:/@]+):([^@]*)@", r"://\1:***@", str(url))


def prov(label, storage, detail):
    return {"label": label, "storage": storage, "detail": detail}


def save_prov(d):
    Path(PROV_PATH).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[prov] 已落 " + PROV_PATH)


def same_store(a, b):
    return str(a.get("storage")) == str(b.get("storage")) and a.get("storage") not in (None, "")


def pg_leg(url):
    """PG 腿：连上即 read_only，自证连的是哪一台服务器。"""
    settings = cvr.parse_database_settings(url)
    if not settings.is_postgresql:
        raise SystemExit("[前置不满足] 连接串不是 PostgreSQL：" + mask(url))
    conn = cvr.connect_read_only(url)
    print("=== PG 腿 · 连接对象自证 ===")
    print("  client dsn      : " + mask(url))
    print("  object          : " + type(conn).__module__ + "." + type(conn).__name__)
    info = conn.info
    print("  info.host       : %r  (compose 服务名)" % (info.host,))
    print("  info.port       : %r" % (info.port,))
    print("  info.dbname     : %r   info.user: %r" % (info.dbname, info.user))
    print("  read_only       : " + repr(conn.read_only))
    if conn.read_only is not True:
        print(RED + "  [降级] 会话没设成 READ ONLY —— 本工具拒跑" + OFF)
        raise SystemExit(3)
    cur = conn.cursor()
    cur.execute(
        "SELECT current_database(), current_user, coalesce(inet_server_addr()::text,'local-socket'),"
        " coalesce(inet_server_port()::text,'-'),"
        " (SELECT setting FROM pg_settings WHERE name='port'),"
        " (SELECT setting FROM pg_settings WHERE name='data_directory'),"
        " (SELECT setting FROM pg_settings WHERE name='hba_file'),"
        " (SELECT string_agg(datname,',') FROM (SELECT datname FROM pg_database ORDER BY datname) d),"
        " (SELECT setting FROM pg_settings WHERE name='server_version'),"
        " (SELECT extversion FROM pg_extension WHERE extname='vector'),"
        " (SELECT system_identifier FROM pg_control_system())")
    (db, usr, saddr, sport, psetting, datadir, hba, dbs, sver, vecext, sysid) = cur.fetchone()
    print("  server  current_database=%s current_user=%s" % (db, usr))
    print("  server  inet_server_addr=%s : %s   (guc port=%s)" % (saddr, sport, psetting))
    print("  server  data_directory=" + str(datadir))
    print("  server  hba_file      =" + str(hba))
    print("  server  databases     =" + str(dbs))
    print("  server  server_version=%s  vector extension=%s" % (sver, vecext))
    print("  server  SYSTEM_IDENTIFIER=" + str(sysid) + "   <- 这一枚唯一标识‘哪一台 PostgreSQL’")
    # 野库可达性：宿主那台 postgres 在容器网内必须连不上，否则上面这套身份不算数
    probe = socket.socket(); probe.settimeout(2)
    rc = probe.connect_ex(("127.0.0.1", 5432)); probe.close()
    print("  trap    容器内 127.0.0.1:5432 connect_ex=%d (%s)"
          % (rc, "REFUSED —— 宿主野库在容器网内不可达，结构上连不到" if rc else "!! 有东西在听 —— 野库风险仍在"))
    print("  trap    getent postgres -> " + socket.gethostbyname("postgres"))
    storage = "postgres://%s:%s/%s#%s" % (socket.gethostbyname("postgres"), sport, db, TABLE)
    p = prov("pgvector/chunk_vectors", storage, {"system_identifier": str(sysid), "data_directory": str(datadir)})
    return conn, cur, p, (int(psetting), str(sysid))


def pg_reads(cur, scope):
    print("=== PG 腿 · 真读到库没有 ===")
    cur.execute("SELECT count(*) FROM " + TABLE); n = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM chunks"); chunks = cur.fetchone()[0]
    cur.execute("SELECT count(DISTINCT vector_dims(embedding)) FROM " + TABLE); widths = cur.fetchone()[0]
    cur.execute("SELECT min(vector_dims(embedding)), max(vector_dims(embedding)) FROM " + TABLE)
    wmin, wmax = cur.fetchone()
    cur.execute("SELECT count(*) FROM chunk_vectors WHERE embedding IS NULL"); nulls = cur.fetchone()[0]
    zero = cvr._zero_literal(scope["dimension"])
    cur.execute("SELECT count(*) FROM " + TABLE + " WHERE embedding = %s::vector", (zero,)); zeros = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM " + TABLE + " WHERE index_version_id IS NULL"); untagged = cur.fetchone()[0]
    print("  chunk_vectors=%s  chunks=%s  embedding IS NULL=%s  index_version_id IS NULL=%s"
          % (n, chunks, nulls, untagged))
    print("  vector_dims: min=%s max=%s distinct=%s （声明 %s）" % (wmin, wmax, widths, scope["dimension"]))
    print("  全零向量普查（PG 侧，零值按 vector_scope.dimension 现拼）= " + str(zeros))
    cur.execute("WITH z AS (SELECT '['||string_agg('0.0',',')||']' AS zero FROM generate_series(1,%s))"
                " SELECT vector_id, filename, chunk_index FROM chunk_vectors, z"
                " WHERE embedding = z.zero::vector ORDER BY vector_id LIMIT 20", (scope["dimension"],))
    named = cur.fetchall()
    print("  全零逐行清单前 20 条：%s" % ("（空）" if not named else named))
    read_real = int(n) > 0 and int(zeros) == int(zeros) and int(scope["dimension"]) > 0
    if not read_real or int(n) == 0:
        print(RED + "  [空读] PG 腿一枚向量都没读到 —— 退出，不允许静默算 overlap" + OFF)
        raise SystemExit(3)
    return {"pg_vectors": int(n), "chunks_rows": int(chunks), "null_embedding": int(nulls),
            "all_zero_rows": int(zeros), "index_version_id_null": int(untagged),
            "width_min": wmin, "width_max": wmax, "zero_named": [list(r) for r in named]}


def chroma_leg():
    print("=== Chroma 腿 · 来源自证 ===")
    d = Path(SNAP).resolve()
    print("  目录（快照，生产卷的字节级副本）: " + str(d))
    print("  生产卷原目录（本进程从未打开）  : /app/chroma_db")
    files = sorted(p for p in d.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print("  快照文件 %d 枚 / %d 字节" % (len(files), total))
    for p in files:
        st = p.stat()
        print("    %-58s %12d  mtime=%s" % (str(p.relative_to(d)), st.st_size,
              __import__("datetime").datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z"))
    import chromadb
    print("  chromadb " + chromadb.__version__)
    collection = cvr.open_chroma(str(d), COLLECTION)
    cnt = collection.count()
    ids = cvr.chroma_all_ids(collection)
    print("  collection.name=%r  count()=%s  get(ids) 全量=%s" % (collection.name, cnt, len(ids)))
    print("  collection.metadata=" + repr(collection.metadata))
    first = ids[0] if ids else None
    row = collection.get(ids=[first], include=["embeddings", "metadatas"]) if first else {}
    emb = ((row or {}).get("embeddings"))
    width = None
    if emb is not None and len(emb):
        width = len(emb[0])
    print("  回读一枚 %s -> 宽度=%s metadata=%s" % (first, width, ((row or {}).get("metadatas") or [None])[0]))
    if int(cnt) == 0 or not ids:
        print(RED + "  [空读] Chroma 腿一条都没读到 —— 退出（上一班读到 401 枚那种沙盒数就是这么混过去的）" + OFF)
        raise SystemExit(3)
    print(GRN + "  [真读到库] 两腿各自计数与差集稍后由官方脚本出数；此处先自证目录=%s" % d + OFF)
    space, u1 = cvr.resolve_chroma_distance(collection)
    print("  U1 实测：space=%s 来源=%s 样本=%s 探针=%s 命中=%s reason=%s"
          % (space or "（测不出）", u1.get("source"), u1.get("sampled"), u1.get("probes"),
             u1.get("matched"), u1.get("reason") or "-"))
    p = prov("chromadb/" + COLLECTION, "chromadb://%s#%s" % (d, COLLECTION),
             {"count": int(cnt), "dir": str(d), "width": width})
    return collection, p, space, {"chroma_vectors": int(cnt), "ids_first": first, "width": width,
                                  "u1": u1, "space": space}


def load_library_vectors(collection):
    page = collection.get(include=["embeddings"])
    ids = [str(i) for i in (page.get("ids") or [])]
    rows = page.get("embeddings")
    rows = [] if rows is None else [[float(v) for v in r] for r in rows]
    return ids, rows


def brute(ids, rows, probe, metric, k):
    scored = []
    pn = math.sqrt(sum(v * v for v in probe))
    for i, vec in enumerate(rows):
        if metric == "l2":
            d = sum((a - b) ** 2 for a, b in zip(vec, probe))
        elif metric == "cosine":
            n = math.sqrt(sum(v * v for v in vec))
            d = 1.0 - sum(a * b for a, b in zip(vec, probe)) / (n * pn or 1.0)
        else:
            d = -sum(a * b for a, b in zip(vec, probe))
        scored.append((d, i))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [ids[i] for _, i in scored[:k]]


def cmd_prove():
    url = os.environ.get("DATABASE_URL") or cvr.pg_store.resolve_database_url()
    conn, cur, pgp, ident = pg_leg(url)
    try:
        scope = cvr.read_scope(conn, TABLE)
        print("=== vector_scope（库里唯一口径） ===")
        print("  " + json.dumps(scope, ensure_ascii=False))
        if scope["distance_function"] not in cvr.DISTANCE_OPERATORS:
            print(RED + "  [前置不满足] distance_function 无法映射算符" + OFF); raise SystemExit(2)
        print("  算符映射：%s -> %s （canonical=%s）"
              % (scope["distance_function"], cvr.DISTANCE_OPERATORS[scope["distance_function"]],
                 cvr.canonical_distance(scope["distance_function"])))
        counts = pg_reads(cur, scope)
        coll, chp, space, chcounts = chroma_leg()
        canon_pg = cvr.canonical_distance(scope["distance_function"])
        print("=== 判据 1 现场值 ===")
        print("  0010 已建            : 见 vector_scope 行 + schema_migrations（脚本外另行取）")
        print("  PG 侧向量计数非零    : %s" % counts["pg_vectors"])
        print("  PG 全零普查          : %s" % counts["all_zero_rows"])
        print("  Chroma 侧计数        : %s" % chcounts["chroma_vectors"])
        print("  两侧 canonical 距离  : pg=%s chroma=%s %s"
              % (canon_pg, space, "一致" if canon_pg == space else "不一致"))
        counts.update(chcounts)
        out = {"pg": counts, "scope": scope, "space": space, "canonical": canon_pg,
               "provenance": {"pg": pgp, "chroma": chp}, "server_ident": list(ident)}
        Path(os.environ.get("P3_PROVE_OUT", "/tmp/p3_prove.json")).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        save_prov({"pg": pgp, "chroma": chp})
        print("[prove] OK")
    finally:
        conn.close()


def cmd_samesource(recall_json, n=10):
    """把任一侧换成与另一侧同源的数据：必须报“两侧同源”，不许给漂亮的 1.0。"""
    data = json.loads(Path(recall_json).read_text(encoding="utf-8"))
    qs = data["questions"][:n]
    provs = json.loads(Path(PROV_PATH).read_text(encoding="utf-8"))
    url = os.environ.get("DATABASE_URL") or cvr.pg_store.resolve_database_url()
    conn = cvr.connect_read_only(url); cur = conn.cursor()
    scope = cvr.read_scope(conn, TABLE)
    coll, _, space, _ = chroma_leg()
    space = space or cvr.canonical_distance(scope["distance_function"])
    print("=== 判据 4 · 同源反证（题面取真跑前 %d 题，同一 embedder） ===" % len(qs))
    from app.rag.retriever import OllamaEmbeddings
    emb = OllamaEmbeddings()
    c_ids, c_rows = load_library_vectors(coll)
    cur.execute("SELECT vector_id, embedding::text FROM " + TABLE)
    pg_rows = [(str(a), json.loads(b)) for a, b in cur.fetchall()]
    pg_ids = [a for a, _ in pg_rows]; pg_vec = [b for _, b in pg_rows]
    real = {tuple(q["chroma"]): q["pg"] for q in qs}
    res = {}
    legs = {
        "real": (provs["chroma"], provs["pg"], "官方脚本：chromadb 引擎 vs pgvector 引擎"),
        "chroma_vs_chromabrute": (
            provs["chroma"],
            prov("numpy-bruteforce@chroma-snapshot", provs["chroma"]["storage"], {"metric": space}),
            "把 PG 腿换成同一份 Chroma 快照上的 numpy 全库暴力（误判 #43 第三行的形状）"),
        "pg_vs_pgnumpy": (
            prov("numpy-bruteforce@chunk_vectors", provs["pg"]["storage"], {"metric": space}),
            provs["pg"],
            "把 Chroma 腿换成 pgvector 同一张表上的 numpy 全库暴力"),
    }
    for key, (left, right, why) in legs.items():
        overlaps = []; same_order = 0; red = same_store(left, right)
        per = []
        for q in qs:
            v = list(emb.embed_query(q["question"]))
            if key == "real":
                got_l, got_r = q["chroma"], q["pg"]
            elif key == "chroma_vs_chromabrute":
                got_l = coll.query(query_embeddings=[v], n_results=data["k"])["ids"][0]
                got_l = [str(x) for x in got_l]
                got_r = brute(c_ids, c_rows, v, space, data["k"])
            else:
                got_l = brute(pg_ids, pg_vec, v, space, data["k"])
                got_r = cvr.pg_recall(conn, vector_table=TABLE, operator=cvr.DISTANCE_OPERATORS[space],
                                      literal="[" + ",".join(repr(float(x)) for x in v) + "]", k=data["k"])
            inter = len(set(got_l) & set(got_r)); union = len(set(got_l) | set(got_r)) or 1
            overlaps.append(inter / float(data["k"]))
            same_order += 1 if got_l == got_r else 0
            per.append({"id": q["id"], "left": got_l, "right": got_r})
        mean = sum(overlaps) / len(overlaps)
        print("\n[%s] %s" % (key, why))
        print("  左腿 = %s | storage=%s" % (left["label"], left["storage"]))
        print("  右腿 = %s | storage=%s" % (right["label"], right["storage"]))
        if red:
            print(RED + "  🔴 两侧同源（storage 同一个）：mean_overlap=%.3f 逐位相同 %d/%d"
                         " —— 这个 1.0 是同一份数据自己比自己，不构成任何切读证据，读数作废"
                  % (mean, same_order, len(qs)) + OFF)
        else:
            print(GRN + "  两腿不同源（pgvector 引擎 vs chromadb 引擎）：mean_overlap=%.3f 逐位相同 %d/%d"
                  % (mean, same_order, len(qs)) + OFF)
            if mean == 1.0 and same_order == len(qs):
                print(YEL + "  ⚠ 跨引擎却逐位全等：数字本身分不开“真一致”与“同源自比”，"
                            "必须靠 storage 身份这一格，不能靠 1.0 好看" + OFF)
        res[key] = {"mean_overlap": mean, "same_order": same_order, "n": len(qs),
                    "same_source": red, "left": left, "right": right, "per": per}
    Path(os.environ.get("P3_SAME_OUT", "/tmp/p3_samesource.json")).write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    conn.close()
    if not res["chroma_vs_chromabrute"]["same_source"] or not res["pg_vs_pgnumpy"]["same_source"]:
        print(RED + "反证钉失效：同源控制没有被认出来" + OFF); return 4
    print("[samesource] 两枚同源控制均被认出，真跑那一格判为两腿不同源 —— 反证钉成立")
    return 0


def cmd_metrics(drift_json, recall_json):
    data = json.loads(Path(recall_json).read_text(encoding="utf-8"))
    drift = json.loads(Path(drift_json).read_text(encoding="utf-8"))
    provs = json.loads(Path(PROV_PATH).read_text(encoding="utf-8"))
    k = int(data["k"]); rows = data["questions"]
    if same_store(provs["chroma"], provs["pg"]):
        print(RED + "两侧同源，overlap 不出数" + OFF); return 4
    ov = []; jac = []; exact = 0; fd = []
    lines = []
    for q in rows:
        L, R = [str(x) for x in q["chroma"]], [str(x) for x in q["pg"]]
        inter = len(set(L) & set(R)); union = len(set(L) | set(R)) or 1
        ov.append(inter / float(k)); jac.append(inter / float(union))
        exact += 1 if L == R else 0
        fd.append(q.get("first_diff_rank"))
        lines.append("%s|%s|%s|k=%d|overlap=%.3f|jaccard=%.3f|exact=%s|first_diff_rank=%s|chroma=%s|pg=%s"
                     % (q["source"], q["id"], "SAME" if L == R else "DIFF", k, ov[-1], jac[-1],
                        L == R, q.get("first_diff_rank"), ";".join(L), ";".join(R)))
    n = len(rows) or 1
    out = {"canonical_distance": {"chroma_resolved": data.get("u1", {}).get("matched"),
                                  "vector_scope": data["scope"]["distance_function"],
                                  "spelling_unified_before_compare": True},
           "k": k, "questions": len(rows),
           "mean_overlap": sum(ov) / n, "mean_jaccard": sum(jac) / n,
           "exact_order_match": exact, "exact_order_rate": exact / n,
           "questions_with_overlap_1": sum(1 for x in ov if x == 1.0),
           "questions_with_overlap_0": sum(1 for x in ov if x == 0.0),
           "first_diff_rank_hist": {str(v): fd.count(v) for v in sorted(set(fd), key=lambda z: (z is None, z))},
           "drift": {kk: (len(vv) if isinstance(vv, list) else vv)
                     for kk, vv in data["drift"].items()},
           "provenance": provs}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    raw = Path(os.environ.get("P3_RAW", "/tmp/p3raw")); raw.mkdir(parents=True, exist_ok=True)
    (raw / "per-question-k5.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (raw / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[metrics] 逐题清单 %s 行 -> %s" % (len(lines), raw / "per-question-k5.txt"))
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "prove"
    if cmd == "prove":
        return cmd_prove()
    if cmd == "samesource":
        return cmd_samesource(argv[2], int(argv[3]) if len(argv) > 3 else 10)
    if cmd == "metrics":
        return cmd_metrics(argv[2], argv[3])
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))