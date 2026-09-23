

#!/usr/bin/env python
"""R162 判据① 备选支：Chroma「query 交回 0 条 ids 而 get 读得到这一枚向量」的只读诊断件。

来历（跟进单 §80 一 / §84 三）：P3 逐题对比里 24/135 题 Chroma 交回 0 条、同一枚向量 PG 交回
精确前 5；生产面 DocumentRetriever.search() 对此返回空列表，用户看到「没有来源」，真相是
「图里问不出邻居」。判据② 的三条候选因里 (a) 段状态 与 (c) 索引覆盖 都只能在**那枚真库的字节**上
量，离线播种库证不了；判据① 的离线扫参（见 tests/test_r162_chroma_zero_row_shape.py）没能复现
无过滤那一支，所以本件是交付的那一支。

本件一个字节都不写目标库。理由不是洁癖：chromadb 的 PersistentClient 对目录是就地读的
——本仓 tests/_chroma_sandbox.py 已经记过实测指纹：把被跟踪的 chroma_db/chroma.sqlite3
「就地打开一次再关」，尺寸 6 262 784 一字不变，sha256 由 0b8cb318a0e0ba18 变成
c43c3e8a950a64b1。所以本件对源目录只做**只读字节复制**，PersistentClient 一律开在仓外副本上，
并在收尾时复比源目录清单：任一文件的 sha256 变了就打印 RED 并以退出码 2 结束。

跑法（不需要 Ollama、不需要 PostgreSQL、不需要 Docker）：

    python scripts/diag_r162_chroma_zero_rows.py                 # 默认读本树 ./chroma_db
    python scripts/diag_r162_chroma_zero_rows.py --probe-limit 80
    python scripts/diag_r162_chroma_zero_rows.py --query-vectors q.jsonl --all
    python scripts/diag_r162_chroma_zero_rows.py --out %TEMP%/r162.json   # 拒绝写进仓内

q.jsonl 每行一枚：{"id": "...", "question": "...", "vector": [768 个 float]}
——那是复核「24」这一枚数唯一诚实的路：题向量必须由生产侧同一枚模型产出（R22 口径），
而本件禁打 Ollama，所以它只消费题向量，不自造。

退出码：0 = 探针里没有出现过 0 行；1 = 出现过 0 行（形状在场，逐条已打印，交人判读）；
2 = 前置不满足（目录缺失 / chromadb 不可用 / 索引字节解析不成立 / 源目录被写脏）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DESCRIPTION = "R162 Chroma 零行形状只读诊断（不写目标库一个字节）"
EXIT_NO_ZERO = 0
EXIT_ZERO_SEEN = 1
EXIT_PRECONDITION = 2

#: 生产 scope 过滤器的两枚形状，照 app/rag/filters.py:84 与 :108 的拼法在这里重写一份。
#: 不复用是因为那两枚常量属于读路径的内部形状，一枚承诺只读的诊断件不该 import 它，
#: 而 app.rag.filters 一旦牵进 app.*，就带上了 .env 与 DocumentRetriever 的建目录副作用。
SCOPE_WHERE_CLASSIFICATION = {"classification": {"$in": [1, 2, 3]}}
SCOPE_WHERE_AND = {"$and": [{"classification": {"$in": [1]}},
                            {"department": {"$in": ["研发中心"]}}]}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", str(ROOT / "chroma_db")))
    parser.add_argument("--collection", default=os.getenv("CHROMA_COLLECTION", "enterprise_docs"))
    parser.add_argument("--scratch-dir", default=None,
                        help="仓外副本落点；默认系统临时目录下的 r162-diag-<随机>")
    parser.add_argument("--k", type=int, default=5, help="探针请求行数，与 P3 同为 5")
    parser.add_argument("--probe-limit", type=int, default=60,
                        help="逐枚存储向量探针最多问几枚（0 = 全问）")
    parser.add_argument("--query-vectors", default=None, help="逐题向量 jsonl，用于复核「24」")
    parser.add_argument("--all", action="store_true", help="逐题打印，而不只打印有 0 行的题")
    parser.add_argument("--skip-index-bytes", action="store_true",
                        help="只走 get/query 与 sqlite，不解析 HNSW 落盘字节")
    parser.add_argument("--out", default=None, help="JSON 读数落点，必须在本仓之外")
    parser.add_argument("--ghost-nn", action="store_true",
                        help="额外算孤儿向量对最近存活向量的余弦分布（只吃落盘字节）")
    return parser.parse_args(argv)


def _fail(msg: str) -> "SystemExit":
    print("[前置不满足] " + msg)
    return SystemExit(EXIT_PRECONDITION)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest(directory: Path) -> dict:
    """源目录清单：文件名 → (字节数, sha256 前 16 位)。只 read，不 write。"""
    out = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(directory))] = (path.stat().st_size, _sha(path)[:16])
    return out


def copy_out_read_only(source: Path, scratch: Path) -> Path:
    """把整枚库按字节复制到仓外。PersistentClient 从此只碰副本，永不碰源目录。"""
    # 本件不删任何文件，连自己上一轮的副本也不删：每次落到带序号的新子目录，
    # 有冲突就让 copytree 自己报错，而不是先清掉别人的东西。
    index = 0
    while (scratch / ("%s-%d" % (source.name, index))).exists():
        index += 1
    target = scratch / ("%s-%d" % (source.name, index))
    shutil.copytree(source, target)
    return target


def open_ro_sqlite(db: Path) -> sqlite3.Connection:
    uri = "file:" + str(db).replace("\\", "/") + "?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


# ==================== sqlite 侧的段账 ====================

def sqlite_census(db: Path) -> dict:
    """段、检查点、元数据键、WAL 残留、HNSW 配置——全是从库自己的表里读的。"""
    out: dict = {"ok": False}
    try:
        con = open_ro_sqlite(db)
    except sqlite3.Error as exc:
        out["error"] = type(exc).__name__ + ": " + str(exc)
        return out
    cur = con.cursor()
    try:
        row = cur.execute("SELECT id, name, dimension FROM collections").fetchall()
        out["collections"] = [{"id": r[0], "name": r[1], "dimension": r[2]} for r in row]
        out["segments"] = cur.execute(
            "SELECT id, type, scope FROM segments ORDER BY scope").fetchall()
        out["max_seq_id"] = dict(cur.execute("SELECT * FROM max_seq_id").fetchall())
        out["embedding_rows"] = cur.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        out["seq_span"] = cur.execute(
            "SELECT min(seq_id), max(seq_id) FROM embeddings").fetchone()
        out["rows_by_segment"] = cur.execute(
            "SELECT segment_id, count(*) FROM embeddings GROUP BY segment_id").fetchall()
        out["metadata_keys"] = cur.execute(
            "SELECT key, count(*) FROM embedding_metadata GROUP BY key ORDER BY 2 DESC"
        ).fetchall()
        out["created_at_days"] = cur.execute(
            "SELECT substr(created_at, 1, 10) AS day, count(*) FROM embeddings"
            " GROUP BY day ORDER BY day").fetchall()
        out["wal_rows"] = cur.execute("SELECT count(*) FROM embeddings_queue").fetchone()[0]
        out["wal_tail"] = cur.execute(
            "SELECT seq_id, operation, id, CASE WHEN vector IS NULL THEN 'NULL'"
            " ELSE 'present' END FROM embeddings_queue ORDER BY seq_id DESC LIMIT 5"
        ).fetchall()
        cfg = cur.execute("SELECT config_json_str, schema_str FROM collections").fetchone()
        out["hnsw_config"] = _hnsw_config(cfg)
        out["ok"] = True
    except sqlite3.Error as exc:
        out["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        con.close()
    return out


def _hnsw_config(row) -> dict:
    """从 collections 的 config/schema JSON 里取 hnsw 那一段，取不到就报缺，不猜默认值。"""
    found: dict = {}
    for blob in (row or ()):
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except (TypeError, ValueError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "hnsw" and isinstance(value, dict):
                        found.update(value)
                    else:
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return found


# ==================== HNSW 落盘字节的覆盖账 ====================

def read_hnsw_segment(seg_dir: Path, declared_dim: int) -> dict:
    """解析 chroma-rs 落盘的 HNSW，交回「图里有几枚、每枚的 label、向量本体」。

    字段名不硬贴（版本间顺序动过、header 也不是整齐宽度——本机的 header.bin 是 100 字节，
    u64 对齐直接抛 struct.error）。改成**用算术反证**：对 header 里出现的每一个候选「链路字节数」
    L，若 L + 4*dim + 8 恰好整除 data_level0.bin，商就是图内元素数；每元素末尾 8 字节是
    label（u64），中间 L 字节是 0 层链路，其余是 f32 向量本体。再拿 index_metadata.pickle
    里的 total_elements_added / label_to_id 复比一次。任一条不自洽就报 parse=unverified，
    绝不交出一个猜出来的数。
    """
    out: dict = {"parse": "unverified", "dir": seg_dir.name}
    data = seg_dir / "data_level0.bin"
    header = seg_dir / "header.bin"
    if not data.exists() or not header.exists():
        out["error"] = "缺 data_level0.bin 或 header.bin"
        return out
    raw = data.read_bytes()
    blob = header.read_bytes()
    fields = set(struct.unpack("<%dI" % (len(blob) // 4), blob[:len(blob) // 4 * 4]))
    fields |= set(struct.unpack("<%dQ" % (len(blob) // 8), blob[:len(blob) // 8 * 8]))
    fields = {int(value) for value in fields if 0 < int(value) < 1 << 31}
    out["header_bytes"] = len(blob)
    out["header_fields"] = sorted(fields)[:24]
    pickle_info = _read_index_pickle(seg_dir)
    out["index_pickle"] = pickle_info
    for links in sorted(fields):
        if links % 4:
            continue
        spe = links + 4 * int(declared_dim) + 8
        if not spe or len(raw) % spe:
            continue
        entries = len(raw) // spe
        if not 1 <= entries <= 10_000_000:
            continue
        labels, vectors = [], []
        for index in range(entries):
            record = raw[index * spe:(index + 1) * spe]
            labels.append(struct.unpack("<Q", record[-8:])[0])
            vectors.append(struct.unpack("<%df" % declared_dim,
                                         record[links:links + int(declared_dim) * 4]))
        if len(set(labels)) != entries:
            continue
        declared_entries = pickle_info.get("total_elements_added")
        out.update(parse="ok" if (declared_entries in (None, entries)) else "arithmetic-only",
                   size_per_element=spe, entries=entries, dim=int(declared_dim),
                   links_level0=links, m0=links // 4 - 1, labels=labels, vectors=vectors)
        return out
    return out


def _read_index_pickle(seg_dir: Path) -> dict:
    """读 index_metadata.pickle 里那三枚能对账的数，读不到就交回空 dict。"""
    path = seg_dir / "index_metadata.pickle"
    if not path.exists():
        return {}
    try:
        import pickle
        with path.open("rb") as handle:
            data = pickle.load(handle)
    except Exception as exc:  # noqa: BLE001 - 落盘格式随版本变，读不动就照实说
        return {"error": type(exc).__name__ + ": " + str(exc)[:120]}
    if not isinstance(data, dict):
        return {"shape": type(data).__name__}
    labels = data.get("label_to_id") or {}
    return {"total_elements_added": data.get("total_elements_added"),
            "dimensionality": data.get("dimensionality"),
            "label_to_id_rows": len(labels),
            "label_to_id_seq_min": min(labels) if labels else None,
            "label_to_id_seq_max": max(labels) if labels else None}


def coverage_account(seg_info: dict, store_ids: dict, verify_vectors) -> dict:
    """两向覆盖账：库里有行而图里没有（正向缺口）/ 图里有节点而库里查无此 id（孤儿）。

    判据② (c) 说的「被 get 读得到而未被索引覆盖」是**正向**那一支，必须与孤儿分开数；
    两向都用同一枚 label↔seq_id 对照算，谁也不许靠对方兜底。
    """
    if seg_info.get("parse") != "ok":
        return {"parse": "unverified"}
    labels = [int(x) for x in seg_info["labels"]]
    in_index = set(labels)
    in_store = set(int(seq) for seq in store_ids)
    forward = sorted(in_store - in_index)
    orphans = sorted(in_index - in_store)
    return {
        "index_entries": len(labels),
        "store_rows": len(in_store),
        "covered": len(in_store & in_index),
        "forward_hole": len(forward),
        "forward_hole_runs": _runs(forward),
        "forward_hole_sample": forward[:20],
        "index_orphans": len(orphans),
        "index_orphan_runs": _runs(orphans),
        "index_orphan_sample": orphans[:20],
        "vector_parse_verified": verify_vectors(seg_info, store_ids),
    }


def _runs(values) -> list:
    out = []
    for value in sorted(values):
        if out and value == out[-1][1] + 1:
            out[-1][1] = value
        else:
            out.append([value, value])
    return [[a, b, b - a + 1] for a, b in out]


# ==================== 探针 ====================

def probe_line(collection, *, name: str, vector, k: int, where=None, where_document=None) -> dict:
    """问一次，打印「collection / 请求行数 / 实际行数 / 距离 / where 形状」。

    这就是判据① 备选支要求的那几列。距离取库自己报的那一枚，不归一、不换算。
    """
    kwargs = {"query_embeddings": [list(vector)], "n_results": k}
    if where:
        kwargs["where"] = where
    if where_document:
        kwargs["where_document"] = where_document
    line = {"probe": name, "collection": str(getattr(collection, "name", "") or ""),
            "requested_rows": k, "actual_rows": None, "distances": [],
            "where": where or {}, "where_document": where_document or {},
            "ids_outer_len": None, "ids_shape": "", "error": ""}
    try:
        got = collection.query(**kwargs) or {}
        # 外层空与内层空是两笔不同的账：库交回 ids=[]（外层就没这一列）与交回 [[]]
        # （这一列里没邻居）在生产读数里会被同一枚 0 混掉，本件把它们分开记。
        outer = got.get("ids")
        line["ids_shape"] = type(outer).__name__
        line["ids_outer_len"] = len(outer) if isinstance(outer, (list, tuple)) else -1
        ids = (outer or [[]])[0] or []
        line["actual_rows"] = len(ids)
        line["hit_ids"] = [str(x) for x in ids][:3]
        dist = (got.get("distances") or [[]])[0] or []
        line["distances"] = [round(float(x), 6) for x in dist]
    except Exception as exc:  # noqa: BLE001 - 探针要把异常形状照实打印，不吞
        line["error"] = type(exc).__name__ + ": " + str(exc)[:160]
    return line


def load_query_vectors(path: str) -> list:
    items = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            vector = item.get("vector")
            if isinstance(vector, str):
                vector = json.loads(vector)
            if vector:
                items.append((str(item.get("id") or ""), str(item.get("question") or ""), vector))
    return items


# ==================== 分布表（判据② 那张表的原料）====================

def cohort_table(db: Path) -> dict:
    """按 created_at 日 / 按 document_id 前缀 / seq 连段与洞，三张切片一起交。

    为什么要 seq 洞：重灌的形状会在 seq_id 轴上留下痕迹——「一段连续的号发出去了
    却没有落库」就是当时被打断的那一批。判据② (a) 问「24 题是不是集中在同一批重灌
    向量」，只有 created_at 分层 + seq 连段两把尺子一起看才答得出来。
    """
    con = open_ro_sqlite(db)
    try:
        rows = con.execute("SELECT embedding_id, seq_id, created_at FROM embeddings"
                           " ORDER BY seq_id").fetchall()
    finally:
        con.close()
    days = {}
    docs = {}
    for ident, seq, created in rows:
        days[str(created)[:10]] = days.get(str(created)[:10], 0) + 1
        docs.setdefault(str(ident).rsplit("_", 1)[0], []).append(int(seq))
    seqs = sorted(int(seq) for _i, seq, _c in rows)
    span = range(seqs[0], seqs[-1] + 1) if seqs else range(0, 0)
    holes = [value for value in span if value not in set(seqs)]
    return {
        "rows": len(rows),
        "days": sorted(days.items()),
        "docs": sorted(([name, len(lst), min(lst), max(lst)] for name, lst in docs.items()),
                       key=lambda item: -item[1]),
        "seq_min": seqs[0] if seqs else None,
        "seq_max": seqs[-1] if seqs else None,
        "seq_holes": len(holes),
        "seq_hole_runs": _runs(holes),
    }


def orphan_split(seg_info: dict, store_ids: dict, seq_max) -> dict:
    """图内孤儿节点分两堆：落在 seq 洞里的 / 高于库内最大 seq 的。

    这两堆的成因不一样：前者是「发过号又被丢下」，后者是「号从未来得及发给库」。
    混在一起数就会把 (a) 与 (c) 两笔账记串。
    """
    if seg_info.get("parse") != "ok":
        return {"parse": "unverified"}
    labels = sorted(int(x) for x in seg_info["labels"])
    in_store = set(int(seq) for seq in store_ids)
    orphans = [label for label in labels if label not in in_store]
    holes = [label for label in orphans if seq_max is not None and label <= seq_max]
    above = [label for label in orphans if seq_max is not None and label > seq_max]
    return {"orphans": len(orphans), "in_seq_holes": len(holes),
            "hole_runs": _runs(holes), "above_seq_max": len(above),
            "above_runs": _runs(above)}


def ghost_nearest_live(seg_info: dict, store_ids: dict) -> object:
    """孤儿向量对最近存活向量的余弦距离分布 + 按所属文件归组（判据② (a) 的重跑量法）。

    用法：如果孤儿们是「同一批内容重灌了一遍」，它们与某个存活向量的余弦距离应当≈0。
    离得远就说明它们是**另一批内容**留下的图节点，与「重灌」这一支无关。
    只吃已经落盘的字节与库自报的 id，不发任何请求。numpy 不在场就交回不可用。
    """
    try:
        import numpy as np
    except ImportError:
        return "numpy 不可用，未算"
    if seg_info.get("parse") != "ok":
        return "索引字节未证成，未算"
    vectors = np.asarray(seg_info["vectors"], dtype="float64")
    labels = [int(x) for x in seg_info["labels"]]
    live = [i for i, label in enumerate(labels) if label in store_ids]
    ghost = [i for i, label in enumerate(labels) if label not in store_ids]
    if not live or not ghost:
        return "没有孤儿节点可归组（live=%d ghost=%d）" % (len(live), len(ghost))
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = vectors / norms
    dist = 1.0 - unit[ghost] @ unit[live].T
    nearest = dist.argmin(axis=1)
    low = dist.min(axis=1)
    by_doc = {}
    for order, picked in enumerate(nearest):
        ident = str(store_ids[labels[live[int(picked)]]])
        doc = ident.rsplit("_", 1)[0]
        by_doc[doc] = by_doc.get(doc, 0) + 1
    return {
        "ghosts": len(ghost),
        "cos_dist_min": round(float(low.min()), 5),
        "cos_dist_median": round(float(np.median(low)), 5),
        "cos_dist_max": round(float(low.max()), 5),
        "within_1e_minus4": int((low < 1e-4).sum()),
        "within_0.01": int((low < 0.01).sum()),
        "by_nearest_live_doc": sorted(by_doc.items(), key=lambda item: -item[1])[:12],
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    source = Path(args.chroma_dir).resolve()
    if not source.is_dir():
        raise _fail("目录不存在（不要新建）：" + str(source))
    named = source / "chroma.sqlite3"
    if named.exists():
        db = named
    else:
        found = sorted(p for p in source.glob("*.sqlite3"))
        if len(found) != 1:
            raise _fail("取不到唯一的 *.sqlite3（找到 %d 枚）：%s"
                        % (len(found), [p.name for p in found]))
        db = found[0]
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        raise _fail("chromadb 不可用：" + exc.name)
    if args.out and _inside_repo(Path(args.out).resolve()):
        raise _fail("--out 不许落在仓内（诊断输出不落仓）：" + args.out)

    scratch = Path(args.scratch_dir or tempfile.mkdtemp(prefix="r162-diag-"))
    scratch.mkdir(parents=True, exist_ok=True)
    print("== R162 只读诊断 ==")
    print("源目录            : %s" % source)
    before = manifest(source)
    print("源目录文件数      : %d（清单已取，收尾复比）" % len(before))
    copy = copy_out_read_only(source, scratch)
    print("仓外副本          : %s" % copy)

    sql = sqlite_census(db)
    if not sql.get("ok"):
        raise _fail("sqlite 读不到：" + str(sql.get("error")))
    declared_dim = (sql["collections"] or [{}])[0].get("dimension")
    print("collection 列表   : %s" % [(c["name"], c["dimension"]) for c in sql["collections"]])
    print("段               : %s" % (sql["segments"],))
    print("max_seq_id       : %s" % (sql["max_seq_id"],))
    print("embeddings 行数  : %d  seq 跨度 %s" % (sql["embedding_rows"], sql["seq_span"]))
    print("元数据键×行数    : %s" % (sql["metadata_keys"],))
    print("行数按 segment_id: %s" % (sql["rows_by_segment"],))
    print("   本 collection 的段：%s" % ([(s[0], s[1].rsplit("/", 1)[-1])
                                        for s in sql["segments"]],))
    print("created_at 按日  : %s" % (sql["created_at_days"],))
    print("hnsw 配置(JSON)  : %s" % (sql["hnsw_config"] or "未记录"))
    print("WAL 残留行数     : %d" % sql["wal_rows"])
    for seq, op, ident, vec in sql["wal_tail"]:
        print("   WAL seq=%s op=%s id=%s vector=%s" % (seq, op, ident, vec))

    cohorts = cohort_table(db)
    print("== 分布表：created_at 按日 / document_id 按文件 / seq 洞 ==")
    print("   按日：%s" % (cohorts["days"],))
    print("   seq %s..%s，区间内缺号 %d 枚，连段 %s"
          % (cohorts["seq_min"], cohorts["seq_max"], cohorts["seq_holes"],
             cohorts["seq_hole_runs"][:12]))
    print("   %-52s %-6s %s" % ("document_id", "行数", "seq 跨度"))
    for name, count, low, high in cohorts["docs"]:
        print("   %-52s %-6d %d..%d" % (name[:52], count, low, high))

    client = chromadb.PersistentClient(path=str(copy),
                                       settings=Settings(anonymized_telemetry=False))
    try:
        collection = client.get_collection(args.collection)
    except Exception as exc:
        raise _fail("取不到 collection %r（%s）" % (args.collection, type(exc).__name__))
    print("打开副本后 count(): %d   get(include=[]) 行数: %d"
          % (collection.count(), len(collection.get(include=[])["ids"])))

    store_ids: dict = {}
    try:
        con = open_ro_sqlite(copy / "chroma.sqlite3")
        store_ids = {row[0]: row[1] for row in
                     con.execute("SELECT seq_id, embedding_id FROM embeddings")}
        con.close()
    except sqlite3.Error:
        pass

    seg_info: dict = {"parse": "skipped"}
    account: dict = {}
    if not args.skip_index_bytes and declared_dim:
        vector_segment = next((s for s in sql["segments"] if s[1].startswith(
            "urn:chroma:segment/vector")), None)
        seg_dir = copy / vector_segment[0] if vector_segment else None
        if seg_dir and seg_dir.is_dir():
            try:
                seg_info = read_hnsw_segment(seg_dir, int(declared_dim))
            except Exception as exc:  # noqa: BLE001 - 解析不成立是读数，不是崩溃理由
                seg_info = {"parse": "unverified", "error": type(exc).__name__ + ": "
                            + str(exc)[:160]}
            account = coverage_account(seg_info, store_ids, _verify_vectors_with_chroma(collection))
            print("== HNSW 落盘覆盖账（判据② (c) 的量法）==")
            print("   header=%s 字节 pickle=%s"
                  % (seg_info.get("header_bytes"), seg_info.get("index_pickle")))
            print("   parse=%s 图内元素=%s 库内行=%s 被索引覆盖=%s 正向缺口=%s 孤儿节点=%s"
                  % (seg_info.get("parse"), account.get("index_entries"),
                     account.get("store_rows"), account.get("covered"),
                     account.get("forward_hole"), account.get("index_orphans")))
            print("   正向缺口连段=%s" % (account.get("forward_hole_runs"),))
            print("   孤儿节点连段=%s" % (account.get("index_orphan_runs"),))
            print("   向量本体解析与库自报比对：%s" % account.get("vector_parse_verified"))
            if account.get("index_orphans"):
                print("   孤儿节点的 label 全表（前 20）：%s"
                      % account.get("index_orphan_sample", []))
            if seg_info.get("parse") != "ok":
                print("   索引字节解析不成立：%s" % seg_info.get("error", "算术反证未通过"))
            split = orphan_split(seg_info, store_ids, cohorts["seq_max"])
            print("   孤儿分堆：总数=%s 落在 seq 洞里=%s 高于库内 max seq=%s"
                  % (split.get("orphans"), split.get("in_seq_holes"),
                     split.get("above_seq_max")))
            print("      洞内连段=%s 洞外连段=%s"
                  % (split.get("hole_runs"), split.get("above_runs")))
            if args.ghost_nn:
                print("   孤儿→最近存活余弦分布：%s"
                      % json.dumps(ghost_nearest_live(seg_info, store_ids),
                                   ensure_ascii=False, default=str))

    lines = []
    vectors = _stored_vectors(collection, args.probe_limit)
    print("== 无过滤探针（存储向量自身当查询，共 %d 枚）==" % len(vectors))
    zero_seen = 0
    for ident, vector in vectors:
        line = probe_line(collection, name="stored:" + ident, vector=vector, k=args.k)
        if line["actual_rows"] == 0:
            zero_seen += 1
            lines.append(line)
            print("   ZERO %s" % json.dumps(line, ensure_ascii=False))
    print("   无过滤探针里 0 行的枚数：%d / %d" % (zero_seen, len(vectors)))

    print("== 形状探针（同一枚查询向量，换 where 形状）==")
    if vectors:
        sample_id, sample_vector = vectors[0]
        shapes = [
            ("no where", None, None),
            ("scope classification $in", SCOPE_WHERE_CLASSIFICATION, None),
            ("scope $and classification+department", SCOPE_WHERE_AND, None),
            ("filename $in [real file]",
             {"filename": {"$in": [sample_id.rsplit("_", 1)[0]]}}, None),
            ("chunk_index $in [0,1]", {"chunk_index": {"$in": [0, 1]}}, None),
            ("$in on a key the store never wrote", {"document_id": {"$in": [sample_id]}}, None),
        ]
        for name, where, where_document in shapes:
            line = probe_line(collection, name=name, vector=sample_vector, k=args.k,
                              where=where, where_document=where_document)
            got = collection.get(where=where, include=[])["ids"] if where \
                else collection.get(include=[])["ids"]
            line["get_where_rows"] = len(got)
            g1 = collection.get(ids=[sample_id], include=["embeddings"])
            line["get_by_id_rows"] = len(g1["ids"])
            lines.append(line)
            print("   %-38s requested=%s actual=%s get(where)=%s get(ids=[本枚])=%s 距离=%s"
                  % (name, line["requested_rows"], line["actual_rows"], line["get_where_rows"],
                     line["get_by_id_rows"], line["distances"][:2]))
            if line["actual_rows"] == 0 and line["get_by_id_rows"] > 0:
                zero_seen += 1
                print("   ^^^ 这就是 R158 那一双脸：query 交回 0 条 ids，而 get 读得到这一枚向量")

    if args.query_vectors:
        items = load_query_vectors(args.query_vectors)
        print("== 逐题探针（题向量由外部喂入，共 %d 题；这是复核「24」的那一支）==" % len(items))
        zero_questions = []
        for qid, question, vector in items:
            line = probe_line(collection, name="question:" + qid, vector=vector, k=args.k)
            line["question"] = question
            lines.append(line)
            if line["actual_rows"] == 0:
                zero_questions.append(qid)
            if args.all or line["actual_rows"] == 0:
                print("   %-14s requested=%s actual=%s 距离=%s" % (
                    qid, line["requested_rows"], line["actual_rows"], line["distances"]))
        print("   交回 0 行的题数：%d / %d" % (len(zero_questions), len(items)))
        print("   题号：%s" % (zero_questions[:40],))

    after = manifest(source)
    dirty = {k: (before.get(k), v) for k, v in after.items() if before.get(k) != v}
    print("== 源目录复比 ==")
    print("   写脏文件数：%d %s" % (len(dirty),
          ("RED " + str(dirty)) if dirty else "(源目录逐字节未变)"))

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"sqlite": {k: v for k, v in sql.items() if k != "ok"},
             "index": {k: v for k, v in account.items() if k != "vectors"}
             if seg_info.get("parse") == "ok" else seg_info,
             "cohorts": cohorts,
             "orphan_split": orphan_split(seg_info, store_ids, cohorts["seq_max"]),
             "probes": lines}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("读数已写出（仓外）：" + args.out)
    return EXIT_ZERO_SEEN if zero_seen else EXIT_NO_ZERO


def _inside_repo(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def _stored_vectors(collection, limit: int) -> list:
    """从库里读「已经存着的向量」当查询用：不需要 embedding 模型，也就一次都不打 Ollama。"""
    page = collection.get(include=["embeddings"], limit=limit or None)
    out = []
    ids = page.get("ids") or []
    vectors = page.get("embeddings")
    if vectors is None:
        return out
    for ident, vector in zip(ids, vectors):
        out.append((str(ident), [float(x) for x in vector]))
    return out


def _verify_vectors_with_chroma(collection):
    """返回一枚校验函数：字节解析出的向量必须与库自报的向量逐位相同，否则覆盖账不算证成。"""
    def verify(seg_info, store_ids):
        try:
            import numpy as np
        except ImportError:
            return "numpy 不可用，未校验"
        labels = {int(label): index for index, label in enumerate(seg_info["labels"])}
        sample = list(store_ids.items())[:5]
        got = collection.get(ids=[ident for _seq, ident in sample], include=["embeddings"])
        by_id = dict(zip(got["ids"], got["embeddings"]))
        worst = 0.0
        for seq, ident in sample:
            if seq not in labels or ident not in by_id:
                continue
            mine = np.asarray(seg_info["vectors"][labels[seq]], dtype="float64")
            theirs = np.asarray(by_id[ident], dtype="float64")
            if mine.shape != theirs.shape:
                return "形状不符 %s vs %s" % (mine.shape, theirs.shape)
            worst = max(worst, float(np.abs(mine - theirs).max()))
        return "抽样 %d 枚，逐位最大差 %.3e" % (len(sample), worst)
    return verify


if __name__ == "__main__":
    sys.exit(main())

