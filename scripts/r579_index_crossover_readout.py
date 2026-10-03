# -*- coding: utf-8 -*-
"""R579 驱动：PG 读腿「索引拐点」——在合成规模上量规划器选哪条腿、索引腿与暴力精确解的名次差、两侧延迟。

跑法（在册口径 = compose 网络里的真库；宿主 5432 没映射，宿主直连＝全绿也是假绿，同
`scripts/r469_sandbox_scope_readout.py:6` 那条家规）：

    # 0) 只在宿主上算数据（零 DB、零模型）：把最大档的 COPY 数据流落到仓外目录并交回 sha256
    python scripts/r579_index_crossover_readout.py --action emit-data `
        --data-dir C:/Users/fengx/PycharmProjects/r579-drill

    # 1) 建沙盒 + 量数（驱动在后端容器内，用产品自己的 psycopg 与产品自己的宽度真源）
    docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python - --action build `
        --tree-base <rev> < scripts/r579_index_crossover_readout.py
    docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python - --action measure ... < 本文件

    # 2) 出表/出 JSON：report 只读回 measure 落盘的原始读数，不连库（离线可复算）
    python scripts/r579_index_crossover_readout.py --action report --from-results <json>

四条硬边界（本件自己拦，不靠人记）
----------------------------------
* 生产库那条连接一开就把会话设成 READ ONLY，且**证明先于任何一条语句**；任何非只读语句打到
  受保护库名上 = `WriteRefusedOnProduction`，一条字节都不出站（`--action guard-proof` 现场演一遍）。
* 沙盒库名必须命中 `--db-prefix` 且不在受保护库名集合里；每条连接建好后先 `current_database()`
  对账，对不上立刻断开——库名是守卫的唯一凭据，所以它必须是**现场读回来的**，不是传进来的。
* 零模型：一条 embed 都不发，不碰 11434。语料与查询向量都是确定性 LCG 合成（几何夹具），
  🔴 它只用来让规划器和 HNSW 图有东西可跑，**不代表客户语料分布**——见凭据纸「不可外推声明」。
* 候选宽度（HNSW `ef_search`）一律现场向唯一真源 `app.rag.pg_store.configured_hnsw_ef_search()`
  取，本文件**一个候选宽度数字都不许出现，注释也不例外**（R393 那笔账的纪律，
  `docs/perf/r393-tool-width-drift-2026-09-27.md`）。索引参数、维度、算符、谓词同样派生：
  DDL 抄生产 `pg_indexes.indexdef` 原文、谓词走产品自己的 `sql_scope_filter`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time

TOOL = "scripts/r579_index_crossover_readout.py"
EXIT_OK = 0
EXIT_RED = 1                 # 自检/判据红
EXIT_PRECONDITION = 2        # 前置不满足（含 --expect-ef-search 对账不上）
EXIT_REFUSED = 3             # 写域/库名守卫拒了
EXIT_MISSING_SIZE = 4        # 指定规模没有读数（必须点名是哪一档）

PROTECTED_DBS = frozenset({"enterprise_brain", "postgres", "template0", "template1"})

#: psycopg3 在同一枚连接上把语句 prepare 之后会**复用旧计划**：本单实测，同连接换
#: `SET LOCAL enable_seqscan/enable_sort` 会被旧计划吃掉——"逼迫走索引"那一臂实际跑成了全表。
#: 所以本件把 prepare 阈值做成显式旋钮（缺省 none = 永不 prepare），并把
#: "墙钟 vs 本臂自己的 EXPLAIN"当成一枚可失败的牙（见 arm_consistency）。
KEEP_PSYCOPG_DEFAULT = object()
SANDBOX_DB_PREFIX_DEFAULT = "eb_r579_probe"
DEFAULT_SIZES = "1008,5000,20000,50000"
MAINTENANCE_DB = "postgres"          # 只为 CREATE/DROP DATABASE 用；它是受保护库名 ⇒ 只读
STATES = ("as_loaded", "analyzed")
ARMS = ("natural", "index", "exact")
#: 三臂在表里的短名，只用于把"哪一臂的腿名不可信"写成一格。
ARM_SHORT = {"natural": "nat", "index": "idx", "exact": "exa"}
#: 端到端 p50 / 本臂 EXPLAIN p50 的比值门：超了就不许拿这条臂的腿名说事。
LEG_CONSISTENCY_RATIO = 3.0
STATE_AS_LOADED = "as_loaded"
PLAN_TEXT_KEEP_DEFAULT = 2
PLAN_SAMPLES_DEFAULT = 3
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

#: 每臂拧哪些规划器开关（SET LOCAL，只在事务内）。exact 臂关掉的正是索引侧的所有入口，
#: 留下 Seq Scan + top-N heapsort = 暴力精确解；index 臂与派工词那条复现语句同姿势。
ARM_KNOBS = {
    "natural": (),
    "index": ("enable_seqscan = off", "enable_sort = off"),
    "exact": ("enable_indexscan = off", "enable_bitmapscan = off",
              "enable_indexonlyscan = off"),
}

#: ---------------------------------------------------------------- 确定性合成向量
#:
#: 公式与在册件 `scripts/r59c_sandbox_corpus.py:105-127` 逐枚同源（同一枚 LCG、同一轮
#: 归一化、同一位小数）。这里复刻一份是因为驱动要在后端容器里跑，而"复刻有没有漂"不由
#: 本件自说：`tests/test_r579_synthetic.py` 离线把两枚函数逐枚向量对过，漂了就红。
#: 🔴 它是**几何夹具**：单位球面上的均匀伪随机点，没有真实嵌入的近重复簇结构。
CORPUS_SEED_BASE = 1000
CORPUS_SEED_STRIDE = 7919
QUERY_SEED_BASE = 5000003           # 与语料 seed 空间不相交，由 corpus_seed_collisions() 现场证明
QUERY_SEED_STRIDE = 104729
VECTOR_TEXT_PRECISION = 6


def corpus_seed(index: int) -> int:
    return CORPUS_SEED_BASE + index * CORPUS_SEED_STRIDE


def query_seed(index: int) -> int:
    return QUERY_SEED_BASE + index * QUERY_SEED_STRIDE


def corpus_seed_collisions(query_index: int, rows: int) -> list:
    """查询 seed 是否正好落在语料 seed 序列上（落上就等于"题目本身在库里"，召回会虚高）。"""
    wanted = query_seed(query_index)
    hit = []
    for row in range(rows):
        if corpus_seed(row) == wanted:
            hit.append(row)
    return hit


def synth_vector(seed: int, dimension: int) -> list:
    """一枚确定性单位向量（LCG，零依赖、跨机可复算）。

    🔴 与在册 `scripts/r59c_sandbox_corpus.py:116` 逐枚同源：同一枚 LCG 链、同一个
    `raw/scale - 0.5` 的取值域、**同一个按取值域（不是按原始整数）算出来的模长**、同一位
    小数。归一化量选错就会得到一批长度不为 1 的"单位向量"，而 l2 名次会因此整体平移——
    由 `tests/test_r579_synthetic_provenance.py` 逐枚对过，漂了就红。
    """
    state = seed & 0xFFFFFFFF
    scale = 0x7FFFFFFF
    values = []
    for _ in range(dimension):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        values.append(state / scale - 0.5)
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, VECTOR_TEXT_PRECISION) for value in values]


def vector_literal(vector: list) -> str:
    # 说明符先拼完整再交给 format：`".." + x + "f}".format(v)` 会把 `.format` 绑到
    # "f}" 上（它比 `+` 先结合），那是一枚撕开的格式串，当场 ValueError。
    spec = "{0:." + str(VECTOR_TEXT_PRECISION) + "f}"
    return "[" + ",".join(spec.format(value) for value in vector) + "]"


#: 一枚定长伪随机 CJK 垫片：3 字节/字，逐行按 seed 偏移切一段——行与行不同（免得 pglz
#: 把整列压成一枚指针），又不必逐字构造。🔴 它是**存储夹具**：内容没有任何语义。
FILLER = "".join(chr(0x4e00 + (1103515245 * (index + 1) + 12345) % 2000)
                 for index in range(4096))
CONTENT_PREFIX = "r579synth"
CJK_BYTES_PER_CHAR = 3


def row_content(ordinal: int, content_bytes: int) -> str:
    """按**字节**凑出 content_bytes 长的正文（前缀 ASCII，其余 CJK，允许 1~2 字节舍入）。

    生产 `avg(octet_length(content))` 是现读的（见 build 产物里那枚 content_bytes_prod）：
    行宽决定 Seq Scan 要扫多少页，凑不满就是把拐点往右推，凑过头就是把拐点往左推。
    """
    if content_bytes <= len(CONTENT_PREFIX):
        return CONTENT_PREFIX[:content_bytes]
    chars = int((content_bytes - len(CONTENT_PREFIX)) / CJK_BYTES_PER_CHAR)
    offset = (ordinal * 7919) % len(FILLER)
    window = FILLER[offset:] + FILLER[:offset]
    return CONTENT_PREFIX + window[:chars]


def row_line(ordinal: int, *, dimension: int, classification, content_bytes: int,
             embedding_model: str, distance_function: str) -> str:
    """一行的 COPY text 格式载荷（列顺序由 COPY_COLUMN_ORDER 定，逐列 \t 分隔）。"""
    vector_id = "r579-{0:08d}".format(ordinal)
    filename = "r579-synth-{0:06d}.md".format(ordinal // 8)
    digest = hashlib.sha256(vector_id.encode("utf-8")).hexdigest()
    content = row_content(ordinal, content_bytes)
    fields = [vector_id, filename, str(ordinal % 8), content, str(classification), "",
              digest, "r579-v1",
              vector_literal(synth_vector(corpus_seed(ordinal), dimension)),
              embedding_model, str(dimension), distance_function,
              "2026-10-03 00:00:00+08", "2026-10-03 00:00:00+08"]
    return "\t".join(fields) + "\n"


#: 与生产 chunk_vectors 的列顺序一致（列清单本身由目录表现读派生，见 load_prod_shape）
COPY_COLUMN_ORDER = ("vector_id", "filename", "chunk_index", "content", "classification",
                     "department", "content_sha256", "index_version_id", "embedding",
                     "embedding_model", "embedding_dimension", "distance_function",
                     "created_at", "updated_at")


def data_stream(*, rows: int, dimension: int, classification, content_bytes: int,
                embedding_model: str, distance_function: str):
    """逐行交回 COPY 载荷；同时把 sha256 算出来（宿主落盘与容器灌库走同一枚生成器）。"""
    digest = hashlib.sha256()
    for ordinal in range(rows):
        line = row_line(ordinal, dimension=dimension, classification=classification,
                        content_bytes=content_bytes, embedding_model=embedding_model,
                        distance_function=distance_function)
        blob = line.encode("utf-8")
        digest.update(blob)
        yield blob, digest.hexdigest()


def data_sha(*, rows: int, dimension: int, classification, content_bytes: int,
             embedding_model: str, distance_function: str) -> str:
    last = ""
    for _chunk, running in data_stream(rows=rows, dimension=dimension,
                                       classification=classification,
                                       content_bytes=content_bytes,
                                       embedding_model=embedding_model,
                                       distance_function=distance_function):
        last = running
    return last


#: ---------------------------------------------------------------- 读数与判据
def percentile(samples: list, q: float):
    """最近秩法（ceil(q*n)，1 基）：样本少的时候不插值，免得造出一个不存在的数。"""
    values = sorted(float(x) for x in samples)
    if not values:
        return None
    rank = max(1, min(len(values), int(math.ceil(q * len(values)))))
    return round(values[rank - 1], 3)


def latency_summary(samples: list) -> dict:
    values = [float(x) for x in samples]
    return {"n": len(values),
            "p50_ms": percentile(values, 0.50), "p95_ms": percentile(values, 0.95),
            "min_ms": round(min(values), 3) if values else None,
            "max_ms": round(max(values), 3) if values else None,
            "mean_ms": round(sum(values) / len(values), 3) if values else None}


def rank_metrics(exact_ids: list, index_ids: list, *, k: int,
                 drop_only_in_compare: bool = False,
                 drop_order_compare: bool = False) -> dict:
    """同一道题目上，索引腿交回的名次与暴力精确解差多少。

    🔴 「全等」不是硬编码，而且**两项互相独立**，摘掉任何一项都必有一枚自检夹具逃掉：
      * `members_agree` 只看集合差（`only_in_*`）：谁多出来、谁掉了，与名次无关；
      * `relative_order_agree` 只看公共成员在两边的**先后**是否一致，与谁缺席无关；
      * `displacements` 是公共成员的名次距离，全零时 `any()` 说假——不许拿"列表非空"当差异。
    逐位相等另记一枚 `identical`（它同时需要上面两项，所以不许拿来当独立判据）。
    """
    exact = list(exact_ids[:k])
    got = list(index_ids[:k])
    n_exact, n_got = len(exact), len(got)
    shared = set(exact) & set(got)
    pos_exact = {value: index for index, value in enumerate(exact)}
    pos_index = {value: index for index, value in enumerate(got)}
    order_in_exact = [value for value in exact if value in shared]
    order_in_index = [value for value in got if value in shared]
    displacements = [abs(pos_exact[value] - pos_index[value]) for value in sorted(shared)]
    only_in_exact = n_exact - len(shared)
    only_in_index = n_got - len(shared)
    members_agree = (only_in_exact == 0 and only_in_index == 0 and n_exact == n_got)
    relative_order_agree = order_in_exact == order_in_index
    if drop_only_in_compare:
        members_agree = True
        only_in_exact = 0
        only_in_index = 0
    if drop_order_compare:
        relative_order_agree = True
        displacements = [0] * len(displacements)
    return {"k": k, "n_exact": n_exact, "n_index": n_got,
            "overlap_ratio": round(len(shared) / k, 4) if k else None,
            "mean_abs_displacement": (round(sum(displacements) / len(displacements), 3)
                                      if displacements else 0.0),
            "max_abs_displacement": max(displacements) if displacements else 0,
            "only_in_exact": only_in_exact, "only_in_index": only_in_index,
            "members_agree": members_agree,
            "relative_order_agree": relative_order_agree,
            "identical": exact == got,
            "mismatch": ((not members_agree) or (not relative_order_agree)
                         or any(displacements))}


def self_check(*, drop_only_in_compare: bool = False,
               drop_order_compare: bool = False) -> dict:
    """两枚已知答案的夹具，各自由**不同**那一项判出来。摘一项就有一枚逃掉。"""
    fixtures = (("同成员乱序", ["a", "b", "c", "d"], ["b", "a", "c", "d"],
                 "relative_order_agree"),
                ("一名之差", ["a", "b", "c", "d"], ["a", "b", "c", "x"],
                 "members_agree"))
    pins = []
    for label, exact, got, term in fixtures:
        metrics = rank_metrics(exact, got, k=4,
                               drop_only_in_compare=drop_only_in_compare,
                               drop_order_compare=drop_order_compare)
        pins.append({"fixture": label, "term": term,
                     "caught": bool(metrics["mismatch"] and not metrics[term]),
                     "metrics": metrics})
    control = rank_metrics(["a", "b", "c", "d"], ["a", "b", "c", "d"], k=4)
    pins.append({"fixture": "全等对照", "term": "mismatch",
                 "caught": control["mismatch"] is False and control["identical"] is True,
                 "metrics": control})
    return {"ok": all(pin["caught"] for pin in pins), "pins": pins}


#: ---------------------------------------------------------------- 计划文本解析
_SCAN_RE = re.compile(r"(Parallel )?(Seq Scan|Index Scan using (\w+)|Bitmap Heap Scan|"
                      r"Index Only Scan using (\w+))( on (\w+))?")
_ACTUAL_RE = re.compile(r"actual time=([\d.]+)\.\.([\d.]+) rows=(\d+) loops=(\d+)")
_EST_RE = re.compile(r"cost=[\d.]+\.\.[\d.]+ rows=(\d+) width=(\d+)")
_EXECTIME_RE = re.compile(r"Execution Time: ([\d.]+) ms")
_PLANTIME_RE = re.compile(r"Planning Time: ([\d.]+) ms")
_SORT_RE = re.compile(r"Sort Method: (.*?)  Memory: (\S+)")
_BUF_RE = re.compile(r"Buffers: shared hit=(\d+)(?: read=(\d+))?")
_LOOPS_TOP_RE = re.compile(r"^\s*->\s")


def parse_plan(lines: list) -> dict:
    """从 EXPLAIN 文本里点名规划器到底选了哪条腿，以及那一行的 actual time。"""
    text = [str(line).rstrip() for line in lines]
    joined = "\n".join(text)
    leg = None
    index_name = None
    parallel = bool(re.search(r"\bGather\b|\bParallel\b", joined))
    scan_row = None
    for line in text:
        found = _SCAN_RE.search(line)
        if not found:
            continue
        if found.group(4):
            index_name = found.group(4)
            leg = "index_only_scan"
        elif found.group(3):
            index_name = found.group(3)
            leg = "index_scan"
        elif found.group(2) == "Bitmap Heap Scan":
            leg = "bitmap_heap_scan"
            if index_name is None:
                bitmap = re.search(r"Bitmap Index Scan on (\w+)", joined)
                index_name = bitmap.group(1) if bitmap else None
                if index_name:
                    leg = "bitmap_index_scan+heap"
        else:
            leg = "parallel_seq_scan" if found.group(1) else "seq_scan"
        scan_row = line
        break
    actual = _ACTUAL_RE.search(scan_row or joined)
    est = _EST_RE.search(scan_row or "") if scan_row else None
    buffers = _BUF_RE.search(joined)
    sort_method = _SORT_RE.search(joined)
    top_actual = _ACTUAL_RE.search(text[0]) if text else None
    return {"leg": leg, "index_name": index_name, "parallel": parallel,
            "scan_line": (scan_row or "").strip() or None,
            "est_rows": int(est.group(1)) if est else None,
            "est_width": int(est.group(2)) if est else None,
            "scan_actual_first_ms": float(actual.group(1)) if actual else None,
            "scan_actual_last_ms": float(actual.group(2)) if actual else None,
            "scan_rows": int(actual.group(3)) if actual else None,
            "top_actual_last_ms": float(top_actual.group(2)) if top_actual else None,
            "execution_time_ms": float(_EXECTIME_RE.search(joined).group(1))
            if _EXECTIME_RE.search(joined) else None,
            "planning_time_ms": float(_PLANTIME_RE.search(joined).group(1))
            if _PLANTIME_RE.search(joined) else None,
            "sort_method": sort_method.group(1) if sort_method else None,
            "shared_hit": int(buffers.group(1)) if buffers else None,
            "shared_read": int(buffers.group(2)) if buffers and buffers.group(2) else 0,
            "plan_head": text[0] if text else None,
            "plan_text": text}

#: ---------------------------------------------------------------- 写域守卫
WRITE_KEYWORD_RE = re.compile(
    r"\b(insert|update|delete|merge|create|alter|drop|truncate|grant|revoke|deny|"
    r"copy|vacuum|reindex|cluster|refresh|comment|lock|prepare|deallocate|call|"
    r"do|analyze|discard|set\s+constraints|lock\s+table|into)\b")
HEAD_READ_RE = re.compile(
    r"^(select|with|show|set|reset|begin|start|rollback|commit|savepoint|explain|"
    r"values|table)\b")
HEAD_EXPLAIN_RE = re.compile(r"^explain(\s*\([^)]*\))?\s+", re.I)
EXPLAIN_READ_PAYLOAD_RE = re.compile(r"^(select|with|values|table|analyze\s+select)\b", re.I)


class WriteRefusedOnProduction(RuntimeError):
    """往受保护库名上打非只读语句：拒绝，且一条字节都不出站。"""


class SandboxTargetRefused(RuntimeError):
    """沙盒落点不是本席的库名：拒绝。"""


def normalize_statement(sql: str) -> str:
    text = re.sub(r"--[^\n]*", " ", str(sql))
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return " ".join(text.split()).strip().rstrip(";").strip().lower()


def classify_statement(sql: str) -> str:
    """只读交回 "read"，其余一律 "write"（默认拒绝，不默认放行）。"""
    text = normalize_statement(sql)
    if not text:
        return "read"
    head = text.split(" ", 1)[0]
    if head not in {"select", "with", "show", "set", "reset", "begin", "start",
                    "rollback", "commit", "savepoint", "explain", "values", "table"}:
        return "write"
    payload = text
    if head == "explain":
        payload = HEAD_EXPLAIN_RE.sub("", text, count=1)
        if not EXPLAIN_READ_PAYLOAD_RE.match(payload):
            return "write"
    if WRITE_KEYWORD_RE.search(payload):
        return "write"
    if head in {"select", "with", "values", "table", "explain"} and \
            re.search(r"\bfor\s+(update|no key update|share|key share)\b", payload):
        return "write"
    return "read"


def guard_statement(database: str, sql: str) -> str:
    """受保护库名上只允许只读语句；越界就抛，且抛在发出去之前。"""
    if str(database or "") in PROTECTED_DBS and classify_statement(sql) != "read":
        raise WriteRefusedOnProduction(
            "受保护库 {0} 上只允许只读语句，这条被判为写：{1}".format(
                database, " ".join(str(sql).split())[:160]))
    return sql


def assert_sandbox_db(database: str, prefix: str) -> str:
    name = str(database or "").strip()
    if not name:
        raise SandboxTargetRefused("沙盒库名不能为空")
    if name in PROTECTED_DBS:
        raise SandboxTargetRefused("{0} 是受保护库名，本席一个字节都不许动".format(name))
    if not (name == prefix or name.startswith(prefix + "_")):
        raise SandboxTargetRefused(
            "沙盒库名必须命中 --db-prefix {0!r}（或其 '_后缀'），拿到 {1!r}".format(prefix, name))
    return name


def swap_dbname(url: str, database: str) -> str:
    """就地换库名得到沙盒连接串：口令留在进程内，账上只以 mask 形状出现。"""
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.netloc, "/" + str(database).lstrip("/"),
                       parts.query, parts.fragment))


def mask_url(url: str) -> str:
    if "@" not in str(url):
        return "<unset>"
    head, tail = str(url).split("@", 1)
    scheme, sep, credential = head.partition("://")
    user = credential.split(":", 1)[0] if sep else credential
    return "{0}{1}{2}:***@{3}".format(scheme, sep or "//", user, tail)


class Db:
    """一条带守卫的连接：库名现场对账 + 受保护库上逐条语句过写域守卫。"""

    def __init__(self, *, url: str, database: str, read_only: bool, label: str,
                 prepare_threshold=KEEP_PSYCOPG_DEFAULT):
        self.url = url
        self.database = database
        self.read_only = read_only
        self.label = label
        self.connection = None
        self.sent = 0
        self.refused = 0
        self.prepare_threshold = prepare_threshold

    def open(self, *, expect_database=None):
        from app.db.connection import connect_with_policy

        kwargs = {}
        if self.prepare_threshold is not KEEP_PSYCOPG_DEFAULT:
            kwargs["prepare_threshold"] = self.prepare_threshold
        # 边界把驱动参数原样转发给驱动（R602 起）：autocommit 与 prepare_threshold 一枚都不能掉。
        self.connection = connect_with_policy(self.url, autocommit=True, **kwargs)
        if self.read_only:
            self._raw("SET default_transaction_read_only = on")
            got = self._raw("SHOW default_transaction_read_only").fetchone()[0]
            if str(got).lower() not in {"on", "true", "1"}:
                raise WriteRefusedOnProduction(
                    "{0} 会话没能设成 READ ONLY（读到 {1!r}）：宁可不跑".format(self.label, got))
        got = str(self._raw("SELECT current_database()").fetchone()[0])
        want = expect_database or self.database
        if got != want:
            raise SandboxTargetRefused(
                "{0} 现场对账失败：连上的库是 {1!r}，本席要的库是 {2!r}".format(
                    self.label, got, want))
        self.database = got
        return self

    def _raw(self, sql, params=None):
        self.sent += 1
        return self.connection.execute(sql, params) if params is not None \
            else self.connection.execute(sql)

    def cursor(self):
        return GuardedCursorContext(self)

    def execute(self, sql, params=None):
        try:
            guard_statement(self.database, sql)
        except WriteRefusedOnProduction:
            self.refused += 1
            raise
        return self._raw(sql, params)

    def rows(self, sql, params=None):
        return list(self.execute(sql, params).fetchall())

    def one(self, sql, params=None):
        return self.execute(sql, params).fetchone()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class GuardedCursor:
    """游标的每一句都先过 `guard_statement`：产品读腿经由它，也就必须经由它。"""

    def __init__(self, database, cursor):
        self.database = database
        self.cursor = cursor

    def execute(self, sql, params=None):
        guard_statement(self.database, sql)
        return (self.cursor.execute(sql, params) if params is not None
                else self.cursor.execute(sql))

    def copy(self, sql):
        guard_statement(self.database, sql)
        return self.cursor.copy(sql)

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchone(self):
        return self.cursor.fetchone()

    def __iter__(self):
        return iter(self.cursor)

    def close(self):
        self.cursor.close()


class GuardedCursorContext:
    """`with db.cursor() as cur:` —— 拿到的是守卫游标，不是裸连接。"""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self._cursor = GuardedCursor(self.db.database, self.db.connection.cursor())
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        self._cursor.close()
        return False


#: ---------------------------------------------------------------- 生产形状（全部 SELECT 派生）
SHAPE_SQL = {
    "scope": ("SELECT schema_version, embedding_model, dimension, distance_function, "
              "hnsw_m, hnsw_ef_construction FROM vector_scope ORDER BY schema_version"),
    "rows": "SELECT count(*) FROM {tbl}",
    "vectors": "SELECT count(embedding) FROM {tbl}",
    "dims": "SELECT min(array_length(embedding::real[],1)), max(array_length(embedding::real[],1)) "
            "FROM {tbl}",
    "dominant": "SELECT classification, count(*) FROM {tbl} GROUP BY 1 ORDER BY 2 DESC LIMIT 1",
    "content": "SELECT coalesce(avg(octet_length(content)),0)::int FROM {tbl}",
    "heap": ("SELECT c.relpages, c.reltuples, pg_relation_size(c.oid), "
             "coalesce(pg_relation_size(c.reltoastrelid),0) FROM pg_class c "
             "WHERE c.oid = '{tbl}'::regclass"),
    "columns": ("SELECT a.attnum, a.attname, format_type(a.atttypid, a.atttypmod) AS typtype, "
                "a.attnotnull, coalesce(pg_get_expr(d.adbin, d.adrelid), '') AS adsrc, "
                "a.attstorage "
                "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid "
                "AND d.adnum = a.attnum WHERE a.attrelid = '{tbl}'::regclass "
                "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"),
    "indexes": ("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = '{tblt}' "
                "ORDER BY indexname"),
    "migrations": ("SELECT count(*), coalesce(md5(string_agg(version || ':' || checksum, "
                   "',' ORDER BY version)),'-') FROM schema_migrations"),
    # pg_statistic 里有没有活统计：as_loaded 这一态的成立前提之一。
    # 不靠 last_analyze 单独作证——本班实测生产 last_analyze/last_autoanalyze 双双为 NULL，
    # 却仍有 14 行活统计；只看时间戳会读出一个假的「没人分析过」。
    "statistic": ("SELECT count(*), count(DISTINCT staattnum) FROM pg_statistic "
                  "WHERE starelid = '{tbl}'::regclass"),
}


def load_shape(db: Db, table: str) -> dict:
    """从生产库**只读**派生这一格需要的所有口径：维度、算符、索引参数、DDL 原文、行宽。"""
    if not IDENT_RE.match(str(table)):
        raise SandboxTargetRefused("表名不是安全形状，不进任何一条语句：{0!r}".format(table))
    sql = {key: text.format(tbl=table, tblt=table) for key, text in SHAPE_SQL.items()}
    shape = {"table": table}
    scope_rows = db.rows(sql["scope"])
    shape["scope_rows"] = len(scope_rows)
    shape["scope_records"] = [tuple(str(value) for value in row)
                               for row in scope_rows]
    if len(scope_rows) != 1:
        raise SystemExit("[前置不满足] vector_scope 期望 1 行，实到 {0} 行：口径不可知".format(
            len(scope_rows)))
    (schema_version, model, dimension, distance, hnsw_m, hnsw_efc) = scope_rows[0]
    shape.update({"schema_version": schema_version, "embedding_model": model,
                  "dimension": int(dimension), "distance_function": str(distance),
                  "hnsw_m": hnsw_m, "hnsw_ef_construction": hnsw_efc})
    shape["rows"] = int(db.one(sql["rows"])[0])
    shape["vector_count"] = int(db.one(sql["vectors"])[0])
    low, high = db.one(sql["dims"])
    shape["dim_min"], shape["dim_max"] = low, high
    level, at_rows = db.one(sql["dominant"])
    shape["dominant_classification"] = level
    shape["dominant_classification_rows"] = int(at_rows)
    shape["avg_content_bytes"] = int(db.one(sql["content"])[0])
    pages, tuples_, heap, toast = db.one(sql["heap"])
    shape.update({"relpages": int(pages), "reltuples": float(tuples_),
                  "heap_bytes": int(heap), "toast_bytes": int(toast),
                  "bytes_per_row": round(int(heap) / max(1, shape["rows"]), 1),
                  "toast_bytes_per_row": round(int(toast) / max(1, shape["rows"]), 1)})
    shape["columns"] = [
        {"attnum": int(n), "name": str(name), "type": str(typtype),
         "notnull": bool(nn), "default": str(dflt), "storage": str(storage)}
        for (n, name, typtype, nn, dflt, storage) in db.rows(sql["columns"])]
    shape["indexes"] = [{"name": str(n), "def": str(d)}
                        for (n, d) in db.rows(sql["indexes"])]
    count, digest = db.one(sql["migrations"])
    shape["migrations"] = {"count": int(count), "digest": str(digest)}
    stat_rows, stat_attrs = db.one(sql["statistic"])
    shape["statistic_rows"] = int(stat_rows)
    shape["statistic_attr_columns"] = int(stat_attrs)
    shape["stats_present"] = int(stat_rows) > 0
    return shape


def build_create_table(schema: str, table: str, columns: list) -> str:
    """列定义逐枚照抄目录表读回来的类型/非空/缺省；不另起一套平行 schema。"""
    if not IDENT_RE.match(schema) or not IDENT_RE.match(table):
        raise SandboxTargetRefused("建表标识符不是安全形状：{0!r}/{1!r}".format(schema, table))
    parts = []
    for column in columns:
        piece = '    "{0}" {1}'.format(column["name"], column["type"])
        if column["notnull"]:
            piece += " NOT NULL"
        if column["default"]:
            piece += " DEFAULT " + column["default"]
        parts.append(piece)
    return 'CREATE TABLE IF NOT EXISTS "{0}"."{1}" (\n{2}\n);'.format(
        schema, table, ",\n".join(parts))


def build_index_ddls(schema: str, table: str, indexes: list) -> list:
    """把生产 `pg_indexes.indexdef` 原文重定向到本席的 schema：索引参数不是抄的，是抄来的原文。

    只接受形状为 `... ON public.<table> ...` 且不带 schema 外引用的定义；形状不对就拒，
    不去猜第二个 schema 前缀该往哪儿替换。
    """
    out = []
    for item in indexes:
        text = item["def"]
        needle = "ON public.{0} ".format(table)
        if text.count(needle) != 1 or re.search(r"ON\s+\w+\.\w+", text).group(0) != \
                ("ON public.{0}".format(table)):
            raise SandboxTargetRefused(
                "索引定义形状不在预期内，拒绝改写：{0}".format(text[:160]))
        rewritten = text.replace(needle, 'ON "{0}"."{1}" '.format(schema, table), 1)
        out.append({"name": item["name"], "def": rewritten})
    return out

#: ---------------------------------------------------------------- 与产品同一句话
class RecordingConnection:
    """把 `pg_store.search_vectors` 交给连接的语句原样录下来。

    本件不重写那条 SQL：重写一次就漂一次（R393 同族）。录制之后，计时跑与 EXPLAIN 跑用的
    都是产品自己拼出来的那一串，包括它自己那枚 `set_config`。
    """

    def __init__(self, cursor):
        self.cursor = cursor
        self.calls = []

    def execute(self, sql, params=None):
        result = (self.cursor.execute(sql, params) if params is not None
                  else self.cursor.execute(sql))
        self.calls.append((sql, params))
        return result

    def captured_read(self):
        for sql, params in reversed(self.calls):
            if str(sql).strip().lower().startswith("select") and "limit" in str(sql).lower():
                return sql, params
        raise SystemExit("[前置不满足] 没录到读腿语句：search_vectors 的形状改了，本件不许猜")


def row_id(row):
    """一行读数里的 vector_id：产品读腿交回字典，裸游标交回元组，两边都认。"""
    if isinstance(row, dict):
        return row["vector_id"]
    return row[0]


def capture_read_statement(pg_store, *, cursor, distance_function, query_vector, k,
                           where, table):
    recorder = RecordingConnection(cursor)
    rows = pg_store.search_vectors(connection=recorder, vector_table=table,
                                   distance_function=distance_function,
                                   query_vector=query_vector, k=k, where=where)
    sql, params = recorder.captured_read()
    width_call = next((call for call in recorder.calls
                       if "set_config" in str(call[0])), None)
    return {"sql": sql, "params": params, "width_call": width_call,
            "ids": [row_id(row) for row in rows]}


#: ---------------------------------------------------------------- 单臂取数
def make_reader(pg_store, *, cursor, shape, where, sample_vector, k):
    """把产品读腿那句话拆成可复用零件：语句原文、它的 set_config 调用、逐题参数装配。

    🔴 语句原文不是本件写的：`capture_read_statement` 让 `pg_store.search_vectors` 自己把
    交给连接的那一串录下来。参数装配则用产品自己的编码器（`_vector_literal` +
    `sql_scope_filter`）重建，并**当场与录到的那枚逐元素对账**——对不上就是产品改了形状，
    本件宁可红，不猜。
    """
    capture = capture_read_statement(
        pg_store, cursor=cursor, distance_function=shape["distance_function"],
        query_vector=sample_vector, k=k, where=where,
        table=pg_store.DEFAULT_VECTOR_TABLE)
    clause, scope_params = pg_store.sql_scope_filter(where)
    literal_of = getattr(pg_store, "_vector_literal", None)
    if literal_of is None:
        raise SystemExit("[前置不满足] 产品没有 _vector_literal：本件不许自带向量编码")

    def params_for(vector, limit):
        literal = literal_of(vector)
        return (literal, *scope_params, literal, int(limit))

    rebuilt = params_for(sample_vector, k)
    if tuple(capture["params"]) != tuple(rebuilt):
        raise SystemExit(
            "[前置不满足] 重建的产品参数与录到的不一致（{0} vs {1}）：读腿形状已改，"
            "本件不许猜".format(str(capture["params"])[:120], str(rebuilt)[:120]))
    if clause and clause.lower() not in capture["sql"].lower():
        raise SystemExit("[前置不满足] 录到的语句里没有产品自己拼的谓词：{0}".format(clause[:120]))
    return {"sql": capture["sql"], "width_call": capture["width_call"],
            "params_for": params_for, "where": where, "clause": clause,
            "scope_params": list(scope_params), "answer_ids": capture["ids"]}


def run_reader(db: Db, reader: dict, *, knobs, vectors, k, plan_samples, warm_rounds,
               plan_text_keep=PLAN_TEXT_KEEP_DEFAULT):
    """一臂一档一题，三相位各自独立：热身 / 计时 / 取计划。

    🔴 本单一手实测抓到的仪器缺陷（不是一次测量误差，是协议写错）：早先的 `warmup`
    只在事务里发 BEGIN/ROLLBACK，**一条读语句都不执行**，所谓"热身"是假的。后果是
    第一枚 `EXPLAIN (ANALYZE)` 把 HNSW 图的页从盘上拽进来，交回 169 ms（生产 1008 枚
    上现取，shared read = 428），而同一笔事务里紧随其后的那条真执行只要 1.3 ms。
    派工词里那句「逼它走索引 = 44.5 ms、比全表慢 18 倍」读的正是这一枚冷数，不是稳态；
    把冷启动写进稳态结论，就会得出"索引腿在客户尺寸上更慢"的反向判断。

    现在的三相位：
      相位 W（热身，`warm_rounds` 轮，每轮把全部向量真执行一遍，读数丢弃）；
      相位 T（计时，每枚向量执行一次并计时、收名次，事务里不夹 EXPLAIN）；
      相位 P（取计划，对前 `plan_samples` 枚向量各打**两次** `EXPLAIN (ANALYZE, BUFFERS)`，
              第一次只为把这条腿的页拽热，留第二次的计划）。
    所以端到端那本账与服务端那本账各自代表稳态，两本账不许互抄。每一枚事务都在事务内
    按产品同一姿势 `set_config` 钉候选宽度（宽度只从真源派生，见 `make_reader`）。
    """
    out = {"latency_samples_ms": [], "ids": [], "plans": [], "knobs": list(knobs),
           "warm_rounds": int(warm_rounds), "phases": {"warm": 0, "timed": 0, "plan": 0},
           "plan_phase_executions_per_sample": 2 if plan_samples else 0}
    params_for = reader["params_for"]
    sql = reader["sql"]
    width_call = reader["width_call"]
    explain_sql = "EXPLAIN (ANALYZE, BUFFERS, TIMING, FORMAT TEXT) " + sql

    def open_txn(cur, vector):
        cur.execute("BEGIN")
        for knob in knobs:
            cur.execute("SET LOCAL " + knob)
        if width_call is not None:
            cur.execute(width_call[0], width_call[1])
        return params_for(vector, k)

    with db.cursor() as cur:
        for _ in range(max(0, int(warm_rounds))):
            for vector in vectors:
                open_txn(cur, vector)
                cur.execute(sql, params_for(vector, k)).fetchall()
                cur.execute("ROLLBACK")
                out["phases"]["warm"] += 1
        for vector in vectors:
            params = open_txn(cur, vector)
            started = time.perf_counter()
            got = cur.execute(sql, params).fetchall()
            out["latency_samples_ms"].append(
                round((time.perf_counter() - started) * 1000.0, 3))
            out["ids"].append([row_id(row) for row in got])
            cur.execute("ROLLBACK")
            out["phases"]["timed"] += 1
        for vector in vectors[:max(0, int(plan_samples))]:
            params = open_txn(cur, vector)
            rows = []
            for _ in range(2):
                rows = cur.execute(explain_sql, params).fetchall()
            plan = parse_plan([row[0] for row in rows])
            if len(out["plans"]) >= plan_text_keep:
                plan["plan_text"] = [plan["plan_head"]] if plan["plan_head"] else []
            out["plans"].append(plan)
            cur.execute("ROLLBACK")
            out["phases"]["plan"] += 1
    out["latency"] = latency_summary(out["latency_samples_ms"])
    out["queries"] = len(out["ids"])
    out["first_sample_ms"] = out["latency_samples_ms"][0] if out["latency_samples_ms"] else None
    return out


def measure_protocol_floor(db: Db, reader: dict, *, samples: int) -> dict:
    """量的是**协议往返本身**：事务形状、拧开关、钉宽度一律同姿势，只把读语句换成 SELECT 1。

    端到端墙钟减去这一枚才约等于服务端时间；三臂开关枚数不同，所以逐臂各量一次，
    不许拿一臂的往返去抵另一臂的账。
    """
    out = {}
    for arm in ARMS:
        values = []
        with db.cursor() as cur:
            for _ in range(int(samples)):
                cur.execute("BEGIN")
                for knob in ARM_KNOBS[arm]:
                    cur.execute("SET LOCAL " + knob)
                if reader["width_call"] is not None:
                    cur.execute(reader["width_call"][0], reader["width_call"][1])
                started = time.perf_counter()
                cur.execute("SELECT 1")
                values.append(round((time.perf_counter() - started) * 1000.0, 3))
                cur.execute("ROLLBACK")
        summary = latency_summary(values)
        summary["round_trips_in_timed_region"] = 1
        summary["statements_per_txn"] = 3 + len(ARM_KNOBS[arm]) + (
            1 if reader["width_call"] is not None else 0)
        out[arm] = summary
    return out



def measure_all_arms(db: Db, reader: dict, *, vectors, k, args) -> dict:
    return {arm: run_reader(db, reader, knobs=ARM_KNOBS[arm], vectors=vectors, k=k,
                            plan_samples=args.plan_samples,
                            warm_rounds=args.warm_rounds,
                            plan_text_keep=args.plan_text_keep)
            for arm in ARMS}


#: ---------------------------------------------------------------- 目录事实
def qualified(schema: str, table: str) -> str:
    """DDL/COPY/ANALYZE 要的是**关系名**，不是一枚表达式：这里只出 `"schema"."table"`。"""
    if not IDENT_RE.match(schema) or not IDENT_RE.match(table):
        raise SandboxTargetRefused("标识符不是安全形状：{0!r}/{1!r}".format(schema, table))
    return '"{0}"."{1}"'.format(schema, table)


def regclass(schema: str, table: str) -> str:
    """目录查询里用的 `'...'::regclass` 字面量：只有这一种形状能进 `pg_class.oid` 比较。"""
    return "'{0}'::regclass".format(qualified(schema, table))


def catalog_facts(db: Db, schema: str, table: str) -> dict:
    rows = db.rows(
        "SELECT c.relpages, c.reltuples, coalesce(pg_relation_size(c.oid),0), "
        "coalesce(pg_relation_size(c.reltoastrelid),0), s.last_analyze, "
        "s.last_autoanalyze, s.seq_scan, s.idx_scan, s.n_dead_tup, s.autovacuum_count, "
        "s.n_mod_since_analyze FROM pg_class c "
        "LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid WHERE c.oid = {0}".format(
            regclass(schema, table)))
    if not rows:
        return {"exists": False, "schema": schema, "table": table}
    (pages, tuples_, heap, toast, last_analyze, last_auto, seq_scan, idx_scan, dead,
     av_count, mod_since) = rows[0]
    count = int(db.one("SELECT count(*) FROM {0}".format(qualified(schema, table)))[0])
    stat_rows = int(db.one("SELECT count(*) FROM pg_statistic WHERE starelid = {0}".format(
        regclass(schema, table)))[0])
    return {"exists": True, "schema": schema, "table": table, "rows": count,
            "statistic_rows": stat_rows, "stats_present": stat_rows > 0,
            "relpages": int(pages), "reltuples": float(tuples_),
            "heap_bytes": int(heap), "toast_bytes": int(toast),
            "bytes_per_row": round(int(heap) / max(1, count), 1),
            "toast_bytes_per_row": round(int(toast) / max(1, count), 1),
            "last_analyze": str(last_analyze) if last_analyze else None,
            "last_autoanalyze": str(last_auto) if last_auto else None,
            "analyzed": bool(last_analyze or last_auto),
            "n_mod_since_analyze": int(mod_since or 0),
            "autovacuum_count": int(av_count or 0),
            "seq_scan": int(seq_scan or 0), "idx_scan": int(idx_scan or 0),
            "dead_tuples": int(dead or 0)}


def schema_name(size: int) -> str:
    return "sz_{0:07d}".format(int(size))


def state_flags(state, catalog):
    """统计态的现场体检：as_loaded 不许有活统计，analyzed 必须有。

    违反就把这一档标脏：读数照交，但纸里必须按它实际站在的那一态理解——
    不许把被分析过的表当成「生产刚灌完的样子」，也不许把没分析的当成 analyzed。
    """
    present = bool(catalog.get("stats_present"))
    rows = int(catalog.get("statistic_rows") or 0)
    if state == STATE_AS_LOADED:
        if present:
            return {"contaminated": True,
                    "reason": ("as_loaded 档现场读到 pg_statistic {0} 行（last_analyze={1}）："
                               "这一档的规划器读数只能按 analyzed 态理解".format(
                                   rows, catalog.get("last_analyze")))}
        return {"contaminated": False, "reason": ""}
    if not present:
        return {"contaminated": True,
                "reason": ("analyzed 档读不到 pg_statistic：ANALYZE 没落住，"
                           "这一档的选腿读数不可用，不许当已分析态交回")}
    return {"contaminated": False, "reason": ""}


#: ---------------------------------------------------------------- 生产：快照 / 复现
def open_prod(args) -> Db:
    url = os.environ.get("DATABASE_URL", "")
    if not str(url).strip():
        raise SystemExit("[前置不满足] DATABASE_URL 未设：本件不许自造 DSN（r469 同规）")
    return Db(url=url, database=args.prod_db, read_only=True,
              label="prod/" + args.prod_db,
              prepare_threshold=args.prepared).open()


def prod_snapshot(db: Db, table: str) -> dict:
    """判据 6 的「逐枚同数」：生产库存量恒量，全部只读，前后各一遍必须逐枚全等。"""
    shape = load_shape(db, table)
    index_digest = hashlib.md5(
        "|".join(item["def"] for item in shape["indexes"]).encode("utf-8")).hexdigest()
    scope_digest = hashlib.md5(
        "|".join(",".join(str(value) for value in record)
                 for record in shape["scope_records"]).encode("utf-8")).hexdigest()
    counters = db.rows("SELECT indexrelname, idx_scan FROM pg_stat_user_indexes "
                       "WHERE schemaname='public' ORDER BY indexrelname")
    return {
        "items": {
            "chunk_vectors_rows": shape["rows"],
            "vector_count": shape["vector_count"],
            "dimension_prod_min_max": [shape["dim_min"], shape["dim_max"]],
            "dimension_declared": shape["dimension"],
            "vector_scope_rows": shape["scope_rows"],
            "vector_scope_digest": scope_digest,
            "migrations": shape["migrations"],
            "index_set_digest": index_digest,
            "index_names": [item["name"] for item in shape["indexes"]],
            "heap_bytes": shape["heap_bytes"],
            "toast_bytes": shape["toast_bytes"],
        },
        "scope": {key: shape[key] for key in
                  ("schema_version", "embedding_model", "dimension", "distance_function",
                   "hnsw_m", "hnsw_ef_construction", "dominant_classification",
                   "dominant_classification_rows", "avg_content_bytes", "bytes_per_row",
                   "toast_bytes_per_row", "relpages", "reltuples",
                   "statistic_rows", "statistic_attr_columns",
                   "stats_present")},
        "columns_digest": hashlib.md5(json.dumps(
            shape["columns"], sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "server": shape.get("_server"),
        "stat_counters_at_snapshot": {str(name): int(count) for name, count in counters},
        "note": ("pg_stat_* 的 seq_scan/idx_scan 不是存量恒量：本班自己的探针就会抬它，"
                 "所以它不进判据 6 的前后对账，只作旁证逐枚列出。"),
    }


def repro_on_prod(args, pg_store, shape: dict) -> dict:
    """派工词第 1 步：在生产库上复现那三行读数（默认代价模型 / 逼迫走索引 / 算符对得上）。"""
    where = {"classification": {"$in": [shape["dominant_classification"]]}}
    vectors = [synth_vector(query_seed(i), shape["dimension"])
               for i in range(args.queries)]
    db = open_prod(args)
    try:
        with db.cursor() as raw:
            reader = make_reader(pg_store, cursor=raw, shape=shape, where=where,
                                sample_vector=vectors[0], k=args.repro_k)
        arms = measure_all_arms(db, reader, vectors=vectors, k=args.repro_k, args=args)
        width = pg_store.configured_hnsw_ef_search()
        confirmed = pin_width_and_read(db, pg_store)
        return {"database": db.database, "table": pg_store.DEFAULT_VECTOR_TABLE,
                "product_sql": reader["sql"], "clause": reader["clause"],
                "operator": pg_store.DISTANCE_OPERATORS[shape["distance_function"]],
                "operator_source": "app.rag.pg_store.DISTANCE_OPERATORS["
                                   "vector_scope.distance_function]",
                "hnsw_index_def": [item["def"] for item in shape["indexes"]
                                   if "hnsw" in item["def"].lower()],
                "width_from_true_source": width, "width_server_confirmed": confirmed,
                "k": args.repro_k, "queries": len(vectors), "arms": arms,
                "system": system_context(),
                "stat_after": {str(n): int(c) for (n, c) in db.rows(
                    "SELECT indexrelname, idx_scan FROM pg_stat_user_indexes "
                    "WHERE indexrelname='chunk_vectors_embedding_idx'")}}
    finally:
        db.close()

def confirmed_width(db: Db, pg_store) -> str:
    """把真源钉下去的那一档从服务端读回来：宽度只有一个来历，复核也只有一处写法。"""
    row = db.execute("SELECT current_setting(%s)",
                     (getattr(pg_store, "HNSW_EF_SEARCH_GUC"),)).fetchone()
    value = row[0]
    return str(value)


def pin_width_and_read(db: Db, pg_store) -> str:
    """与产品同一枚 `set_config(..., TRUE)` 钉一次再读回来：只在事务里活着，跑完不残留。"""
    width = pg_store.configured_hnsw_ef_search()
    db.execute("BEGIN")
    db.execute(pg_store._APPLY_HNSW_EF_SEARCH_SQL,
               (getattr(pg_store, "HNSW_EF_SEARCH_GUC"), str(width)))
    read = confirmed_width(db, pg_store)
    db.execute("ROLLBACK")
    return read


#: ---------------------------------------------------------------- 沙盒：建表灌数
def ensure_vector_extension(db: Db, expected_version) -> str:
    """沙盒库自己也要有 pgvector，而且**必须与生产同一枚版本**：换了算符实现，
    量到的拐点就不是这台机器的那一格了。"""
    db.execute("CREATE EXTENSION IF NOT EXISTS vector")
    row = db.one("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    got = str(row[0]) if row else None
    if got != str(expected_version):
        raise SystemExit("[前置不满足] 沙盒库 pgvector = {0!r}，生产 = {1!r}：不同版本的"
                         "代价模型与图算法不是同一枚东西，本单不量".format(
                             got, expected_version))
    return got


def load_table(db: Db, schema: str, table: str, shape: dict, *, rows: int,
               content_bytes: int, maintenance_work_mem: str,
               parallel_maintenance_workers=0) -> dict:
    """在沙盒 schema 里建一张**与生产同定义、同索引原文**的表，灌入前 N 行合成向量。"""
    columns = shape["columns"]
    names = ", ".join('"{0}"'.format(column["name"]) for column in columns)
    db.execute('CREATE SCHEMA IF NOT EXISTS "{0}"'.format(schema))
    db.execute('CREATE TABLE "{0}"."{1}" (\n{2}\n)'.format(
        schema, table, ",\n".join(
            '    "{0}" {1}{2}{3}'.format(
                column["name"], column["type"],
                " NOT NULL" if column["notnull"] else "",
                " DEFAULT " + column["default"] if column["default"] else "")
            for column in columns)))
    # 关掉本席沙盒表的 autovacuum：as_loaded 那一档必须是"真没人分析过"，
    # 否则后台一分析，这一档就读到 analyzed 态去了（生产 last_analyze 现读为空）。
    db.execute('ALTER TABLE {0} SET (autovacuum_enabled = false)'.format(
        qualified(schema, table)))
    digest = hashlib.sha256()
    count = 0
    last_sha = digest.hexdigest()
    with db.cursor() as cur:
        with cur.copy('COPY {0} ({1}) FROM STDIN WITH (FORMAT text)'.format(
                qualified(schema, table), names)) as copy:
            for blob, running in data_stream(
                    rows=rows, dimension=shape["dimension"],
                    classification=shape["dominant_classification"],
                    content_bytes=content_bytes,
                    embedding_model=shape["embedding_model"],
                    distance_function=shape["distance_function"]):
                copy.write(blob)      # psycopg3 原样发出：行尾由 row_line 自带
                digest.update(blob)
                last_sha = running
                count += 1
    # 索引怎么建出来的不进本单判据（查询期计划不看它），但并行建索引要在 /dev/shm
    # 里开 DSM：这台机的容器 shm 只有 64 MB，实测 20000 档并行建索引直接 DiskFull。
    # 所以建索引按口令拧成串行（0 = 串行），并行只留给查询期。
    db.execute("SET max_parallel_maintenance_workers = {0}".format(
        _safe_workers(parallel_maintenance_workers)))
    built = []
    for item in build_index_ddls(schema, table, shape["indexes"]):
        started = time.perf_counter()
        db.execute("SET maintenance_work_mem = '{0}'".format(
            _safe_size(maintenance_work_mem)))
        db.execute(item["def"])
        built.append({"name": item["name"], "def": item["def"],
                      "build_seconds": round(time.perf_counter() - started, 2)})
    live = db.rows("SELECT attnum, attname, format_type(atttypid,atttypmod), attnotnull, "
                   "attstorage FROM pg_attribute WHERE attrelid = {0} "
                   "AND attnum > 0 AND NOT attisdropped ORDER BY attnum".format(
                       regclass(schema, table)))
    expected = [(column["attnum"], column["name"], column["type"], bool(column["notnull"]),
                 column["storage"]) for column in columns]
    actual = [(int(n), str(a), str(t), bool(nn), str(s)) for (n, a, t, nn, s) in live]
    return {"rows_loaded": count, "data_sha256": last_sha, "indexes_built": built,
            "columns_match_prod": actual == expected,
            "prod_columns": expected, "sandbox_columns": actual,
            "catalog": catalog_facts(db, schema, table)}


WORKERS_RE = re.compile(
    r"^(0|[1-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-6])$")

SIZE_RE = re.compile(r"^\d+(\s?(kB|MB|GB|TB))?$", re.I)


def _safe_workers(value) -> int:
    """并行度只收 0..256 的**纯数字原文**：它要进 SET 语句，所以不先 int() 再验。

    先 int() 会把 " 1 "、"1_0" 这类形状放过一遍，而那正是拼进语句的原文。
    """
    text = str(value)
    if not WORKERS_RE.match(text):
        raise SandboxTargetRefused(
            "并行度必须是 0..256 的纯数字原文：{0!r}".format(value))
    return int(text)



def _safe_size(value: str) -> str:
    text = str(value).strip()
    if not SIZE_RE.match(text):
        raise SandboxTargetRefused("maintenance_work_mem 不是安全形状：{0!r}".format(value))
    return text.replace(" ", "")


def load_shape_prod(args, pg_store) -> dict:
    db = open_prod(args)
    try:
        shape = load_shape(db, pg_store.DEFAULT_VECTOR_TABLE)
        shape["_server"] = {
            "pg_version": str(db.one("SELECT version()")[0]),
            "pgvector": str(db.one(
                "SELECT extversion FROM pg_extension WHERE extname='vector'")[0]),
            "settings": {name: str(value) for name, value in db.rows(
                "SELECT name, setting FROM pg_settings WHERE name IN "
                "('shared_buffers','effective_cache_size','work_mem',"
                "'maintenance_work_mem','random_page_cost','cpu_tuple_cost',"
                "'max_parallel_workers_per_gather','max_parallel_maintenance_workers',"
                "'jit','enable_seqscan','enable_indexscan','enable_sort') ORDER BY name")},
            "db_set": sorted(str(row[0]) for row in db.rows(
                "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1")),
            "database_read_only": str(db.one(
                "SHOW default_transaction_read_only")[0]),
        }
        shape["_table"] = pg_store.DEFAULT_VECTOR_TABLE
        return shape
    finally:
        db.close()


def open_sandbox(args) -> Db:
    url = os.environ.get("DATABASE_URL", "")
    if not str(url).strip():
        raise SystemExit("[前置不满足] DATABASE_URL 未设：本件不许自造 DSN（r469 同规）")
    name = assert_sandbox_db(args.sandbox_db, args.db_prefix)
    return Db(url=swap_dbname(url, name), database=name, read_only=False,
              label="sandbox/" + name,
              prepare_threshold=args.prepared).open(expect_database=name)


def action_build(args, pg_store, out):
    shape = load_shape_prod(args, pg_store)
    table = pg_store.DEFAULT_VECTOR_TABLE
    content_bytes = args.content_bytes_override or max(args.min_content_bytes,
                                                       shape["avg_content_bytes"])
    sandbox = open_sandbox(args)
    sandbox_pgvector = ensure_vector_extension(sandbox, shape["_server"]["pgvector"])
    payload = {"action": "build", "sandbox_db": sandbox.database, "sizes": args.sizes,
               "pgvector_prod": shape["_server"]["pgvector"],
               "pgvector_sandbox": sandbox_pgvector,
               "content_bytes": content_bytes,
               "content_bytes_source": ("--content-bytes-override（人工校准行宽）"
                                        if args.content_bytes_override else
                                        "生产 avg(octet_length(content)) 现读"),
               "content_bytes_prod": shape["avg_content_bytes"],
               "content_bytes_floor": args.min_content_bytes,
               "prod_shape": {key: shape[key] for key in (
                   "dimension", "distance_function", "embedding_model", "hnsw_m",
                   "hnsw_ef_construction", "rows", "avg_content_bytes", "bytes_per_row",
                   "toast_bytes_per_row", "dominant_classification")},
               "hnsw_index_def_prod": [item["def"] for item in shape["indexes"]
                                       if "hnsw" in item["def"].lower()],
               "built": {}, "errors": {}}
    rc = EXIT_OK
    try:
        for size in args.sizes:
            schema = schema_name(size)
            if size < 1:
                raise SystemExit("[前置不满足] --sizes 里有非正规模：{0}".format(size))
            if db_schema_exists(sandbox, schema, table):
                if not args.replace:
                    payload["errors"][str(size)] = "schema 已存在，未加 --replace：跳过"
                    rc = EXIT_RED
                    continue
                sandbox.execute('DROP SCHEMA "{0}" CASCADE'.format(schema))
            try:
                sandbox.execute("SELECT set_config('search_path', %s, false)",
                                ("{0}, public".format(schema),))
                payload["built"][str(size)] = load_table(
                    sandbox, schema, table, shape, rows=size,
                    content_bytes=content_bytes,
                    maintenance_work_mem=args.maintenance_work_mem,
                    parallel_maintenance_workers=args.parallel_maintenance_workers)
            except Exception as exc:            # 灌不动就停在能灌成的最大档，并写清楚为什么
                payload["errors"][str(size)] = "{0}: {1}".format(
                    type(exc).__name__, str(exc)[:400])
                rc = EXIT_RED
    finally:
        sandbox.close()
    out.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
    return rc


def db_schema_exists(db: Db, schema: str, table: str) -> bool:
    return bool(db.one("SELECT to_regclass(%s) IS NOT NULL",
                       ('{0}."{1}"'.format(schema, table),))[0])


#: ---------------------------------------------------------------- 量：四档 × 两态 × 三臂 × k
def system_context() -> dict:
    """延迟读数的环境上下文：本机当时是不是安静机器，纸上要能自证。"""
    context = {"hostname": os.environ.get("HOSTNAME", ""), "python": sys.version.split()[0]}
    try:
        context["loadavg_1_5_15"] = [round(float(x), 2)
                                     for x in open("/proc/loadavg").read().split()[:3]]
    except Exception as exc:
        context["loadavg_error"] = type(exc).__name__
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            key, _, value = line.partition(":")
            if key in ("MemTotal", "MemAvailable", "Dirty", "Writeback"):
                mem[key] = value.strip()
        context["meminfo"] = mem
    except Exception as exc:
        context["meminfo_error"] = type(exc).__name__
    try:
        context["cpu_count"] = len(os.sched_getaffinity(0))
    except Exception:
        context["cpu_count"] = None
    return context


def action_measure(args, pg_store, out):
    shape = load_shape_prod(args, pg_store)
    table = pg_store.DEFAULT_VECTOR_TABLE
    width = pg_store.configured_hnsw_ef_search()
    if args.expect_ef_search is not None and int(args.expect_ef_search) != int(width):
        out.write("[对账不上] 唯一真源现场交回的候选宽度 = {0}，口令里期望 = {1}："
                  "整单不量，先回总控\n".format(width, args.expect_ef_search))
        return EXIT_PRECONDITION
    vectors = [synth_vector(query_seed(i), shape["dimension"])
               for i in range(args.queries)]
    collisions = [(index, corpus_seed_collisions(index, max(args.sizes)))
                  for index in range(args.queries)
                  if corpus_seed_collisions(index, max(args.sizes))]
    sandbox = open_sandbox(args)
    protocol_floor = None
    records = []
    errors = {}
    rc = EXIT_OK
    try:
        for size in args.sizes:
            schema = schema_name(size)
            if not db_schema_exists(sandbox, schema, table):
                errors[str(size)] = ("该档沙盒表 {0}.{1} 不存在：没有读数可交，"
                                     "不许拿上一档外推".format(schema, table))
                continue
            sandbox.execute("SELECT set_config('search_path', %s, false)",
                            ("{0}, public".format(schema),))
            where = {"classification": {"$in": [shape["dominant_classification"]]}}
            for state in args.states:
                if state == "analyzed":
                    sandbox.execute("ANALYZE {0}".format(qualified(schema, table)))
                with sandbox.cursor() as cur:
                    reader = make_reader(pg_store, cursor=cur, shape=shape, where=where,
                                         sample_vector=vectors[0], k=min(args.ks))
                if protocol_floor is None and args.floor_samples > 0:
                    protocol_floor = measure_protocol_floor(
                        sandbox, reader, samples=args.floor_samples)
                catalog = catalog_facts(sandbox, schema, table)
                entry = {"size": size, "state": state, "schema": schema,
                         "catalog": catalog, "state_flags": state_flags(state, catalog),
                         "width_from_true_source": width,
                         "width_guc": pg_store.HNSW_EF_SEARCH_GUC,
                         "product_sql": reader["sql"], "clause": reader["clause"],
                         "ks": {}}
                for k in args.ks:
                    arms = measure_all_arms(sandbox, reader, vectors=vectors, k=k,
                                            args=args)
                    entry["ks"][str(k)] = {
                        arm: {"ids": arms[arm]["ids"], "plans": arms[arm]["plans"],
                              "knobs": arms[arm]["knobs"],
                              "latency_samples_ms": arms[arm]["latency_samples_ms"]}
                        for arm in ARMS}
                entry["width_server_confirmed"] = pin_width_and_read(sandbox, pg_store)
                records.append(entry)
    finally:
        sandbox.close()
    payload = {"action": "measure", "tool": TOOL, "sandbox_db": sandbox.database,
               "started_at": args.started_at, "finished_at": _now(),
               "requested_sizes": args.sizes, "ks": args.ks,
               "queries": args.queries, "warm_rounds": args.warm_rounds,
               "plan_samples": args.plan_samples, "states": list(args.states),
               "prepare_threshold": describe_prepare_threshold(args.prepared),
               "width_source_attr": "app.rag.pg_store.configured_hnsw_ef_search",
               "width_from_true_source": width,
               "query_vector_seeds": {"base": QUERY_SEED_BASE, "stride": QUERY_SEED_STRIDE,
                                      "count": args.queries},
               "corpus_seed_collisions": collisions,
               "prod_shape": {key: shape[key] for key in (
                   "dimension", "distance_function", "embedding_model", "hnsw_m",
                   "hnsw_ef_construction", "rows", "avg_content_bytes", "bytes_per_row",
                   "toast_bytes_per_row", "dominant_classification",
                   "dominant_classification_rows", "statistic_rows",
                   "statistic_attr_columns", "stats_present")},
               "server": shape["_server"], "system": system_context(),
               "protocol_floor_ms": protocol_floor,
               "protocol_floor_note": ("SELECT 1 在同一事务形状下的往返本身：端到端读数减去它"
                                           "约等于服务端时间；三臂开关枚数不同，逐臂各量"),
               "records": records, "errors": errors}
    out.write(json.dumps(payload, ensure_ascii=False, indent=args.indent,
                         default=str) + "\n")
    if errors:
        rc = EXIT_MISSING_SIZE
    return rc


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

#: ---------------------------------------------------------------- 汇总 / 拐点 / 对账
SEQ_LEGS = {"seq_scan", "parallel_seq_scan"}
INDEX_LEGS = {"index_scan", "index_only_scan", "bitmap_index_scan+heap",
              "bitmap_heap_scan", "gather_index_scan"}


def leg_family(leg):
    if leg is None:
        return None
    if leg in SEQ_LEGS:
        return "seq"
    if leg in INDEX_LEGS or str(leg).endswith("index_scan"):
        return "index"
    if leg == "mixed":
        return "mixed"
    return "other"


def arm_legs(arm_result: dict) -> dict:
    legs = [plan.get("leg") for plan in arm_result.get("plans", [])]
    distinct = sorted({str(leg) for leg in legs if leg})
    return {"legs": legs, "leg": distinct[0] if len(distinct) == 1 else
            ("mixed" if distinct else None),
            "index_names": sorted({str(plan.get("index_name"))
                                   for plan in arm_result.get("plans", [])
                                   if plan.get("index_name")}),
            "est_rows": [plan.get("est_rows") for plan in arm_result.get("plans", [])],
            "execution_time_ms": [plan.get("execution_time_ms")
                                  for plan in arm_result.get("plans", [])],
            "sort_method": [plan.get("sort_method") for plan in arm_result.get("plans", [])],
            "shared_hit": [plan.get("shared_hit") for plan in arm_result.get("plans", [])],
            "shared_read": [plan.get("shared_read") for plan in arm_result.get("plans", [])],
            "scan_actual_last_ms": [plan.get("scan_actual_last_ms")
                                    for plan in arm_result.get("plans", [])],
            "execution_latency": latency_summary(
                [plan["execution_time_ms"] for plan in arm_result.get("plans", [])
                 if plan.get("execution_time_ms") is not None]),
            "top_actual_latency": latency_summary(
                [plan["top_actual_last_ms"] for plan in arm_result.get("plans", [])
                 if plan.get("top_actual_last_ms") is not None]),
            "shared_read_max": max([int(plan.get("shared_read") or 0)
                                    for plan in arm_result.get("plans", [])] or [0]),
            "shared_hit_min": min([int(plan.get("shared_hit") or 0)
                                   for plan in arm_result.get("plans", [])] or [0])}


def aggregate_k(entry: dict, k: int, *, drop_only_in_compare: bool = False,
                drop_order_compare: bool = False, floor: dict = None) -> dict:
    arms = entry["ks"][str(k)]
    exact = arms["exact"]["ids"]
    index = arms["index"]["ids"]
    natural = arms["natural"]["ids"]
    metrics = [rank_metrics(e, i, k=k, drop_only_in_compare=drop_only_in_compare,
                            drop_order_compare=drop_order_compare)
               for e, i in zip(exact, index)]
    overlap = [item["overlap_ratio"] for item in metrics if item["overlap_ratio"] is not None]
    displacements = [item["mean_abs_displacement"] for item in metrics]
    only_index = [item["only_in_index"] for item in metrics]
    only_exact = [item["only_in_exact"] for item in metrics]
    max_disp = [item["max_abs_displacement"] for item in metrics]
    natural_vs_index = sum(1 for n, i in zip(natural, index) if n[:k] == i[:k])
    out = {"size": entry["size"], "state": entry["state"], "k": k,
           "queries": len(metrics),
           "ranks": {
               "overlap_mean": round(sum(overlap) / len(overlap), 4) if overlap else None,
               "overlap_min": min(overlap) if overlap else None,
               "queries_with_full_set": sum(1 for item in metrics if item["members_agree"]),
               "queries_with_relative_order_agree": sum(
                   1 for item in metrics if item["relative_order_agree"]),
               "queries_with_identical_list": sum(1 for item in metrics
                                                  if item["identical"]),
               "mismatch_queries": sum(1 for item in metrics if item["mismatch"]),
               "mean_abs_displacement_avg": (round(sum(displacements) / len(displacements), 4)
                                             if displacements else None),
               "max_abs_displacement_overall": max(max_disp) if max_disp else None,
               "only_in_index_total": sum(only_index), "only_in_index_max": (max(only_index)
                                                                             if only_index else None),
               "only_in_exact_total": sum(only_exact), "only_in_exact_max": (max(only_exact)
                                                                             if only_exact else None),
               "natural_equals_index": natural_vs_index},
           "arms": {arm: dict(arm_legs(arms[arm]),
                              latency=latency_summary(arms[arm]["latency_samples_ms"]),
                              knobs=arms[arm]["knobs"]) for arm in ARMS},
           "catalog": entry["catalog"],
           "state_flags": entry.get("state_flags") or {"contaminated": False, "reason": ""},
           "width_from_true_source": entry.get("width_from_true_source"),
           "width_server_confirmed": entry.get("width_server_confirmed")}
    # 向量索引的名字只认一个来历：被 enable_seqscan/enable_sort 逼出来的那一臂点了谁。
    # bitmap_index_scan 点的也是"索引"，但那是 classification 的 btree，不是 HNSW，
    # 所以"自然腿选没选向量索引"必须由名字派生，不许由腿名猜。
    vector_names = set(out["arms"]["index"]["index_names"])
    for arm in ARMS:
        names = set(out["arms"][arm]["index_names"])
        out["arms"][arm]["on_vector_index"] = bool(names & vector_names)
        out["arms"][arm]["vector_index_names"] = sorted(names & vector_names)
    out["natural_on_vector_index"] = out["arms"]["natural"]["on_vector_index"]

    out["consistency"] = arm_consistency(out, floor=floor)
    out["natural_leg_family"] = leg_family(out["arms"]["natural"]["leg"])
    out["exact_leg_family"] = leg_family(out["arms"]["exact"]["leg"])
    out["index_leg_family"] = leg_family(out["arms"]["index"]["leg"])
    return out


def arm_consistency(item: dict, floor: dict = None,
                    limit: float = LEG_CONSISTENCY_RATIO) -> dict:
    """一臂一判：本臂的端到端墙钟与它自己的 EXPLAIN Execution Time 差几倍。

    比值超 `limit` 就说明这一臂**没在跑它宣称的那条腿**——本单就是这么抓到 psycopg3
    复用旧计划的：`index` 臂的 EXPLAIN 交回 2 ms，墙钟却贴着全表腿的 18 ms。
    协议往返地板值只作扣减展示，不参与判倍（否则一臂的开关枚数会混进比值）。
    """
    out = {}
    for arm in ARMS:
        wall = (item["arms"][arm].get("latency") or {}).get("p50_ms")
        server = (item["arms"][arm].get("execution_latency") or {}).get("p50_ms")
        base = ((floor or {}).get(arm) or {}).get("p50_ms") or 0.0
        ratio = None if (wall is None or not server) else round(wall / server, 3)
        out[arm] = {"wall_p50_ms": wall, "explain_p50_ms": server,
                    "floor_p50_ms": base,
                    "wall_minus_floor_ms": None if wall is None else round(
                        max(0.0, wall - base), 4),
                    "wall_over_explain": ratio,
                    "leg_attribution_suspect": bool(ratio is not None and ratio > limit)}
    out["limit_ratio"] = limit
    out["note"] = ("比值 = 端到端 p50 / 本臂自己的 EXPLAIN Execution Time p50；超阈值即该臂"
                   "的腿名不可信。EXPLAIN 只采样前若干题，所以这是旁证，不是逐题证明")
    return out


def suspect_marks(consistency: dict) -> str:
    """把"哪一臂的腿名不可信"压成一格读数：ok / nat! / idx!exa! 之类。"""
    if not consistency:
        return "-"
    flags = [ARM_SHORT.get(arm, arm) for arm in ARMS
             if (consistency.get(arm) or {}).get("leg_attribution_suspect")]
    return "ok" if not flags else "-".join(flags) + "!"


def ratio_cells(consistency: dict) -> str:
    """逐臂比值（端到端 p50 / 本臂 EXPLAIN p50），星号标出超门的那一臂。"""
    if not consistency:
        return "-"
    cells = []
    for arm in ARMS:
        data = consistency.get(arm) or {}
        ratio = data.get("wall_over_explain")
        text = "-" if ratio is None else str(ratio)
        cells.append("{0}={1}{2}".format(ARM_SHORT.get(arm, arm), text,
                                        "*" if data.get("leg_attribution_suspect") else ""))
    return " ".join(cells)


def crossover_brackets(aggregate: list) -> dict:
    """拐点**区间**：只按实测到的档位说"在 X 与 Y 之间换了腿"，不给单点。"""
    out = {}
    for state in STATES:
        for key in {item["k"] for item in aggregate}:
            rows = sorted([item for item in aggregate
                           if item["state"] == state and item["k"] == key],
                          key=lambda item: item["size"])
            legs = {item["size"]: item["natural_leg_family"] for item in rows}
            seq_sizes = [size for size, family in legs.items() if family == "seq"]
            index_sizes = [size for size, family in legs.items() if family == "index"]
            bracket = None
            if seq_sizes and index_sizes and min(index_sizes) > max(seq_sizes):
                bracket = [max(seq_sizes), min(index_sizes)]
            elif index_sizes and not seq_sizes:
                bracket = [None, min(index_sizes)]
            elif seq_sizes and not index_sizes:
                bracket = [max(seq_sizes), None]
            vector_on = {item["size"]: bool(item.get("natural_on_vector_index"))
                                   for item in rows}
            hnsw_sizes = sorted(size for size, flag in vector_on.items() if flag)
            plain_sizes = sorted(size for size, flag in vector_on.items() if not flag)
            vector_bracket = None
            if hnsw_sizes and plain_sizes and min(hnsw_sizes) > max(plain_sizes):
                vector_bracket = [max(plain_sizes), min(hnsw_sizes)]
            elif hnsw_sizes and not plain_sizes:
                vector_bracket = [None, min(hnsw_sizes)]
            elif plain_sizes and not hnsw_sizes:
                vector_bracket = [max(plain_sizes), None]

            out["{0}|k={1}".format(state, key)] = {
                "legs_by_size": legs,
                "transition_between": bracket,
                "statement": ("在 {0} 与 {1} 之间从全表换成索引腿".format(*bracket)
                              if bracket and bracket[0] and bracket[1] else
                              "未量到拐点：四档里没有出现"
                              "「小的走全表、大的走索引」这一对，见 legs_by_size"),
                "vector_leg_by_size": vector_on,
                "vector_leg_transition_between": vector_bracket,
                "vector_leg_statement": (
                    "在 {0} 与 {1} 之间，自然腿第一次踩上向量索引".format(*vector_bracket)
                    if vector_bracket and vector_bracket[0] and vector_bracket[1] else
                    "未量到：四档里自然腿没有从「不踩向量索引」翻成「踩向量索引」"),
                "all_index": bool(index_sizes) and not seq_sizes,
                "all_seq": bool(seq_sizes) and not index_sizes}
    return out


def check_size_coverage(requested: list, records: list, errors: dict) -> dict:
    """判据 2 的牙：缺哪一档必须点名，且 rc≠0。"""
    have = sorted({int(item["size"]) for item in records})
    missing = [size for size in requested if size not in have]
    return {"requested": list(requested), "measured": have, "missing": missing,
            "reasons": {str(size): errors.get(str(size), "没有任何该档读数")
                        for size in missing},
            "no_extrapolation": "缺档一律写「未量到 + 为什么」，不许拿上一档外推"}


def snapshot_diff(before: dict, after: dict) -> dict:
    """判据 6 的前后对账：六项存量恒量必须逐枚同数。"""
    items = {}
    for key in sorted(set(before["items"]) | set(after["items"])):
        left, right = before["items"].get(key), after["items"].get(key)
        items[key] = {"before": left, "after": right, "equal": left == right}
    return {"items": items,
            "all_equal": all(item["equal"] for item in items.values()),
            "unequal": [key for key, item in items.items() if not item["equal"]]}


def db_set_diff(before: list, after: list) -> dict:
    return {"before": before, "after": after,
            "added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "restored": sorted(set(before) - set(before)) == [] and
            set(after) == set(before)}


#: ---------------------------------------------------------------- 出表
def _fmt_ms(value):
    return "-" if value is None else "{0:.3f}".format(float(value))


def render_server_table(aggregate: list, floor: dict = None) -> str:
    """服务端那本账：EXPLAIN (ANALYZE) 的 Execution Time 与 BUFFERS，不含协议往返。

    与上面那张端到端表分开列，是因为三臂在计时区之外的语句枚数不同：把两本账混进
    同一列读，就会把网络与事务形状的成本算到规划器头上。
    """
    header = ("{:>7} {:>10} {:>4} | {:>9} {:>8} {:>8} {:>6} | {:>9} {:>8} {:>8} {:>6} "
              "| {:>9} {:>8} {:>8} {:>6}").format(
        "size", "state", "k",
        "nat.leg", "srvP50", "srvP95", "rdMax",
        "idx.leg", "srvP50", "srvP95", "rdMax",
        "exa.leg", "srvP50", "srvP95", "rdMax")
    out = [header, "-" * len(header)]
    for item in aggregate:
        cells = [item["size"], item["state"], item["k"]]
        for arm in ARMS:
            data = item["arms"][arm]
            server = data.get("execution_latency") or {}
            cells.extend([data.get("leg"), _fmt_ms(server.get("p50_ms")),
                          _fmt_ms(server.get("p95_ms")),
                          "{0}/{1}".format(server.get("n", 0),
                                           data.get("shared_read_max", "-"))])
        out.append("{0:>7} {1:>10} {2:>4} | {3:>9} {4:>8} {5:>8} {6:>6} | {7:>9} "
                   "{8:>8} {9:>8} {10:>6} | {11:>9} {12:>8} {13:>8} {14:>6}".format(*cells))
    out.append("")
    out.append("srvP50/srvP95 = EXPLAIN (ANALYZE) 交回的 Execution Time；"
               "rdMax = 该臂采样里 shared read 的最大值（读盘枚数）")
    if floor:
        for arm in ARMS:
            value = floor.get(arm) or {}
            out.append("协议往返本身 arm={0} p50={1} p95={2} n={3} 事务内语句枚数={4}".format(
                arm, _fmt_ms(value.get("p50_ms")), _fmt_ms(value.get("p95_ms")),
                value.get("n"), value.get("statements_per_txn")))
    else:
        out.append("协议往返本身：本轮没量（--floor-samples 0）——端到端读数不许当服务端时间用")
    out.append("")
    out.append("腿名可信度 = 端到端 p50 / 本臂自己的 EXPLAIN Execution Time p50"
               "（比值门 {0}，超门标 *：这一臂没在跑它宣称的那条腿，腿名不许写进结论）".format(
                   LEG_CONSISTENCY_RATIO))
    for item in aggregate:
        cons = item.get("consistency") or {}
        out.append("  {0:>7} {1:>10} k={2:<3} {3}".format(
            item["size"], item["state"], item["k"], ratio_cells(cons)))
    return "\n".join(out)



def render_table(aggregate: list, brackets: dict) -> str:
    header = ("{0:>7} {1:>10} {2:>4} {3:>9} {4:>9} {5:>9} {6:>7} {7:>6} {8:>5} "
              "{9:>6} {10:>6} {11:>8} {12:>8} {13:>8} {14:>8} {15:>8} {16:>8} "
              "{17:>6} {18:>6} {19:>6} {20:>9}".format(
                  "size", "state", "k", "nat.leg", "idx.leg", "exa.leg", "overlap",
                  "meanΔ", "maxΔ", "onlyIx", "onlyEx", "p50nat", "p50idx", "p50exa",
                  "p95nat", "p95idx", "p95exa", "eqIdx", "stat", "onHNSW", "legTrust"))
    lines = [header, "-" * len(header)]
    for item in aggregate:
        arms = item["arms"]

        def short(arm):
            leg = arms[arm]["leg"]
            return {"seq_scan": "seq", "parallel_seq_scan": "pseq", "index_scan": "idx",
                    "mixed": "mixed"}.get(leg, str(leg)[:9])

        def lat(arm, key):
            value = arms[arm]["latency"].get(key)
            return "{0:.1f}".format(value) if value is not None else "-"

        ranks = item["ranks"]
        lines.append("{0:>7} {1:>10} {2:>4} {3:>9} {4:>9} {5:>9} {6:>7} {7:>6} {8:>5} "
                     "{9:>6} {10:>6} {11:>8} {12:>8} {13:>8} {14:>8} {15:>8} {16:>8} "
                     "{17:>6} {18:>6} {19:>6} {20:>9}".format(
                         item["size"], item["state"], item["k"],
                         short("natural"), short("index"), short("exact"),
                         "-" if ranks["overlap_mean"] is None else
                         "{0:.4f}".format(ranks["overlap_mean"]),
                         "-" if ranks["mean_abs_displacement_avg"] is None else
                         "{0:.3f}".format(ranks["mean_abs_displacement_avg"]),
                         ranks["max_abs_displacement_overall"],
                         ranks["only_in_index_total"], ranks["only_in_exact_total"],
                         lat("natural", "p50_ms"), lat("index", "p50_ms"),
                         lat("exact", "p50_ms"), lat("natural", "p95_ms"),
                         lat("index", "p95_ms"), lat("exact", "p95_ms"),
                         "{0}/{1}".format(ranks["natural_equals_index"],
                                          item["queries"]),
                         "DIRTY" if (item.get("state_flags") or {}).get("contaminated")
                         else "clean",
                         "yes" if item.get("natural_on_vector_index") else "no",
                         suspect_marks(item.get("consistency") or {})))
    lines.append("")
    for item in aggregate:
        flags = item.get("state_flags") or {}
        if flags.get("contaminated"):
            lines.append("\u26a0 档位 {0} 态 {1} k={2}：{3}".format(
                item["size"], item["state"], item["k"], flags.get("reason")))
    for key, value in sorted(brackets.items()):
        lines.append("拐点 {0}: {1}｜legs={2}".format(
            key, value["statement"],
            {size: family for size, family in value["legs_by_size"].items()}))
        lines.append("   向量索引那本账 {0}: {1}｜natural_on_hnsw={2}".format(
            key, value.get("vector_leg_statement"),
            value.get("vector_leg_by_size")))
    return "\n".join(lines)

#: ---------------------------------------------------------------- 收尾 / 自证 / 出料
WRITE_SHAPES = (
    "INSERT INTO chunk_vectors (vector_id, filename, chunk_index, content, embedding, "
    "embedding_model, embedding_dimension, distance_function) VALUES "
    "('r579-x','r579.md',0,'x','[0]','m',1,'l2')",
    "UPDATE chunk_vectors SET department = 'r579' WHERE vector_id = 'nope'",
    "DELETE FROM chunk_vectors WHERE vector_id = 'nope'",
    "CREATE INDEX r579_bad_idx ON chunk_vectors (department)",
    "DROP TABLE chunk_vectors",
    "COPY chunk_vectors (vector_id) FROM STDIN",
    "EXPLAIN (ANALYZE) INSERT INTO chunk_vectors (vector_id) VALUES ('r579-y')",
    "WITH gone AS (DELETE FROM chunk_vectors WHERE vector_id = 'r579-z' RETURNING *) "
    "SELECT count(*) FROM gone",
    "TRUNCATE chunk_vectors",
    "VACUUM FULL chunk_vectors",
    "DO $$ BEGIN INSERT INTO chunk_vectors (vector_id) VALUES ('r579-w'); END $$;",
    "SELECT pg_sleep(0) INTO r579_sink",
)


def action_guard_proof(args, out) -> int:
    """判据 5 第③把：往生产库打写语句，必须**在出站之前**被拦。一条字节都不发。"""
    db = open_prod(args)
    proof = {"database": db.database, "attempts": [], "session_read_only": None,
             "transaction_read_only": None, "statements_sent_before_proof": db.sent}
    rc = EXIT_OK
    try:
        db.execute("BEGIN")
        proof["transaction_read_only"] = str(db.execute(
            "SHOW transaction_read_only").fetchone()[0])
        db.execute("ROLLBACK")
        proof["session_read_only"] = str(db.execute(
            "SHOW default_transaction_read_only").fetchone()[0])
        for text in WRITE_SHAPES:
            try:
                db.execute(text)
                proof["attempts"].append({"sql": text[:80], "refused": False,
                                          "note": "句子已经出站——这是缺陷"})
                rc = EXIT_RED
            except WriteRefusedOnProduction as exc:
                proof["attempts"].append({"sql": text[:80], "refused": True,
                                          "reason": str(exc)[:140]})
        proof["classification"] = [{"sql": text[:60],
                                    "class": classify_statement(text)}
                                   for text in WRITE_SHAPES]
        proof["reads_still_allowed"] = [
            {"sql": text[:60], "class": classify_statement(text)} for text in (
                "SELECT count(*) FROM chunk_vectors",
                "EXPLAIN (ANALYZE, BUFFERS) SELECT vector_id FROM chunk_vectors LIMIT 1",
                "SET LOCAL enable_seqscan = off", "SHOW hnsw.ef_search", "BEGIN",
                "ROLLBACK")]
    finally:
        db.close()
    proof["verdict"] = "牙在：{0} 枚写形状全部拦在出站之前".format(
        len(WRITE_SHAPES)) if rc == EXIT_OK else "牙不在：有写形状穿过守卫"
    out.write(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    return rc


def action_cleanup(args, out) -> int:
    """删本席建的 schema（只删 sz_*），并把收尾那条 dropdb 原话交回宿主去执行。"""
    sandbox = open_sandbox(args)
    dropped = []
    try:
        rows = sandbox.rows("SELECT nspname FROM pg_namespace "
                            "WHERE nspname LIKE 'sz\\_%' ORDER BY nspname")
        for (name,) in rows:
            if not IDENT_RE.match(str(name)) or not str(name).startswith("sz_"):
                raise SandboxTargetRefused("要删的 schema 不是本席的形状：{0!r}".format(name))
            sandbox.execute('DROP SCHEMA IF EXISTS "{0}" CASCADE'.format(name))
            dropped.append(str(name))
        left = [str(row[0]) for row in sandbox.rows(
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'sz\\_%' ORDER BY 1")]
    finally:
        sandbox.close()
    out.write(json.dumps({
        "action": "cleanup", "sandbox_db": sandbox.database, "dropped_schemas": dropped,
        "schemas_left": left,
        "host_command": "docker exec enterprise-brain-postgres-1 dropdb -U {0} {1}".format(
            args.db_user, sandbox.database),
        "db_set_check": "docker exec enterprise-brain-postgres-1 psql -U {0} -d postgres "
                        "-At -c \"select datname from pg_database order by 1\"".format(
                            args.db_user)}, ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK if not left else EXIT_RED


def action_db_set(args, out) -> int:
    db = open_prod(args)
    try:
        names = sorted(str(row[0]) for row in db.rows(
            "SELECT datname FROM pg_database ORDER BY 1"))
    finally:
        db.close()
    out.write(json.dumps({"databases": names, "count": len(names),
                          "non_template": [n for n in names if not n.startswith("template")]},
                         ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK


def action_emit_data(args, out) -> int:
    """宿主角色：把最大档的 COPY 载荷落到仓外目录，并交回逐档 sha256（零 DB、零模型）。"""
    os.makedirs(args.data_dir, exist_ok=True)
    biggest = max(args.sizes)
    path = os.path.join(args.data_dir, "r579_corpus_{0}.tsv".format(biggest))
    digest = hashlib.sha256()
    per_size = {}
    wanted = {size: size for size in args.sizes}
    written = 0
    with open(path, "wb") as handle:
        for blob, running in data_stream(
                rows=biggest, dimension=args.dimension,
                classification=args.classification, content_bytes=args.content_bytes,
                embedding_model=args.embedding_model,
                distance_function=args.distance_function):
            handle.write(blob)
            written += 1
            digest.update(blob)
            if written in wanted:
                per_size[str(written)] = running
    out.write(json.dumps({
        "action": "emit-data", "path": path, "rows": written, "bytes": os.path.getsize(path),
        "sha256": digest.hexdigest(), "sha256_by_prefix_rows": per_size,
        "line_shape": "14 列 \\t 分隔，顺序 = 生产 chunk_vectors 的 attnum 序",
        "note": "前缀即小档：第 N 行之前的字节流就是 N 档语料本身（同一枚 seed 序列）"
        }, ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK


def action_plan(args, out) -> int:
    """默认动作：只把「打算发什么」打出来，一条语句都不出站。"""
    out.write(json.dumps({
        "action": "plan", "tool": TOOL, "would_connect": {
            "prod": {"database": args.prod_db, "read_only": True},
            "sandbox": {"database": args.sandbox_db, "prefix": args.db_prefix,
                        "guard": "assert_sandbox_db + 现场 current_database() 对账"}},
        "sizes": args.sizes, "ks": args.ks, "queries": args.queries,
        "warm_rounds": args.warm_rounds, "plan_samples": args.plan_samples,
        "states": list(args.states),
        "arms": {arm: list(ARM_KNOBS[arm]) for arm in ARMS},
        "width_note": ("候选宽度不在本文件里：量之前现场调用 "
                       "app.rag.pg_store.configured_hnsw_ef_search()，"
                       "跑完再用 current_setting(guc) 服务端复核一次"),
        "width_importable_now": _width_probe(),
        "sql_sketch": ("SELECT <产品 _READ_COLUMNS>, embedding <算符> %s::vector AS distance "
                       "FROM chunk_vectors WHERE <产品 sql_scope_filter> "
                       "ORDER BY embedding <算符> %s::vector LIMIT %s  —— 语句原文由 "
                       "RecordingConnection 从 pg_store.search_vectors 录下，本件不重写"),
        "forbidden_on_prod": list(WRITE_SHAPES)[:3],
        "host_side": {"createdb": "docker exec enterprise-brain-postgres-1 createdb -U {0} {1}"
                      .format(args.db_user, args.sandbox_db),
                      "dropdb": "docker exec enterprise-brain-postgres-1 dropdb -U {0} {1}"
                      .format(args.db_user, args.sandbox_db)},
        "touching_database": False}, ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK


def _width_probe():
    try:
        from app.rag import pg_store
    except Exception as exc:
        return {"available": False, "error": "{0}: {1}".format(type(exc).__name__,
                                                               str(exc)[:160])}
    return {"available": True, "value": pg_store.configured_hnsw_ef_search(),
            "guc": getattr(pg_store, "HNSW_EF_SEARCH_GUC", None),
            "source": "app.rag.pg_store.configured_hnsw_ef_search"}


def answer_tally(ids_list: list) -> dict:
    """把同一枚问题连打多次交回的名次列逐枚归堆：出现几种答案、各几次。

    本单实测逼出来的量具：同一张表、同一枚查询向量、同一候选宽度，
    跨跑次交回过不同的 top-k，所以"名次差"必须先证明自己可复现，才谈得上是一个数。
    """
    piles = {}
    for ids in ids_list:
        # 逐枚 json.dumps（不是 str()）：None 与 "None" 是两回事，不许归成一堆
        key = json.dumps(list(ids), ensure_ascii=False, default=repr)
        piles[key] = piles.get(key, 0) + 1
    return {"repeats": len(ids_list), "distinct_answers": len(piles),
            "pile_sizes": sorted(piles.values(), reverse=True),
            "answers": {key: count for key, count in sorted(
                piles.items(), key=lambda item: -item[1])}}


def action_repeat_probe(args, pg_store, out) -> int:
    """判据 2 的复现探针：同题连打 N 次，逐臂点名交回了几个不同的 top-k。"""
    shape = load_shape_prod(args, pg_store)
    table = pg_store.DEFAULT_VECTOR_TABLE
    width = pg_store.configured_hnsw_ef_search()
    if args.expect_ef_search is not None and int(args.expect_ef_search) != int(width):
        out.write("[对账不上] 真源现场交回 {0}，口令期望 {1}：不跑\n".format(
            width, args.expect_ef_search))
        return EXIT_PRECONDITION
    vector = synth_vector(query_seed(args.query_index), shape["dimension"])
    sandbox = open_sandbox(args)
    payload = {"action": "repeat-probe", "sandbox_db": sandbox.database,
               "query_index": args.query_index, "repeats": args.repeats,
               "k": args.repro_k, "width_from_true_source": width,
               "arms": list(ARMS), "probes": [], "errors": {}}
    rc = EXIT_OK
    try:
        for size in args.sizes:
            schema = schema_name(size)
            if not db_schema_exists(sandbox, schema, table):
                payload["errors"][str(size)] = "该档沙盒表不存在：没有读数可交，不许外推"
                continue
            sandbox.execute("SELECT set_config('search_path', %s, false)",
                            ("{0}, public".format(schema),))
            where = {"classification": {"$in": [shape["dominant_classification"]]}}
            with sandbox.cursor() as cur:
                reader = make_reader(pg_store, cursor=cur, shape=shape, where=where,
                                     sample_vector=vector, k=args.repro_k)
            facts = catalog_facts(sandbox, schema, table)
            entry = {"size": size,
                     "stats_present_at_probe": facts.get("stats_present"),
                     "arms": {}}
            for arm in payload["arms"]:
                got = run_reader(sandbox, reader, knobs=ARM_KNOBS[arm],
                                 vectors=[vector] * args.repeats, k=args.repro_k,
                                 plan_samples=0, warm_rounds=0)
                entry["arms"][arm] = answer_tally(got["ids"])
            entry["width_server_confirmed"] = pin_width_and_read(sandbox, pg_store)
            payload["probes"].append(entry)
    finally:
        sandbox.close()
    out.write(json.dumps(payload, ensure_ascii=False, indent=args.indent,
                         default=str) + "\n")
    if payload["errors"]:
        rc = EXIT_MISSING_SIZE
    return rc



def action_report(args, out) -> int:
    payload = json.load(open(args.from_results, encoding="utf-8"))
    records = payload.get("records", [])
    if payload.get("action") != "measure":
        out.write("[前置不满足] --from-results 指的不是一份 measure 产物：{0}\n".format(
            payload.get("action")))
        return EXIT_PRECONDITION
    drop_only = args.tamper == "drop-only-in-compare"
    drop_order = args.tamper == "drop-order-compare"
    check = self_check(drop_only_in_compare=drop_only, drop_order_compare=drop_order)
    floor = payload.get("protocol_floor_ms")
    aggregate = [aggregate_k(entry, int(k), drop_only_in_compare=drop_only,
                            drop_order_compare=drop_order, floor=floor)
                 for entry in records for k in entry["ks"]]
    aggregate.sort(key=lambda item: (item["size"], item["state"], item["k"]))
    brackets = crossover_brackets(aggregate)
    # 只有口令里点名的 --sizes 才算判据 2 的清单；缺省那串是默认档，不许拿它判缺档
    requested = list(args.sizes) if args.sizes_explicit else payload.get(
        "requested_sizes", [])
    coverage = check_size_coverage(list(requested), records, payload.get("errors", {}))
    rc = EXIT_OK
    if not check["ok"]:
        rc = EXIT_RED
    if coverage["missing"]:
        rc = EXIT_MISSING_SIZE
    result = {"action": "report", "tool": TOOL, "from": args.from_results,
              "self_check": check, "tamper": args.tamper,
              "requested_sizes": list(requested), "coverage": coverage,
              "crossover": brackets, "aggregate": aggregate,
              "prepare_threshold": payload.get("prepare_threshold"),
              "protocol_floor_ms": floor,
              "width_from_true_source": payload.get("width_from_true_source"),
              "server": payload.get("server"), "system": payload.get("system"),
              "prod_shape": payload.get("prod_shape"),
              "queries": payload.get("queries"), "rc": rc}
    if args.format == "json":
        out.write(json.dumps(result, ensure_ascii=False, indent=args.indent) + "\n")
    else:
        out.write(render_table(aggregate, brackets) + "\n")
        out.write("\n服务端那本账（不含协议往返）:\n")
        out.write(render_server_table(aggregate,
                                payload.get("protocol_floor_ms")) + "\n")
        out.write("\n自检: {0}｜拐点: {1}\n".format(
            "达" if check["ok"] else "红（判据 5 第①把的牙不在了）",
            "; ".join("{0} -> {1}".format(key, value["statement"])
                      for key, value in sorted(brackets.items()))))
        if coverage["missing"]:
            out.write("🔴 缺档（不许外推）: {0}\n".format(
                json.dumps(coverage["reasons"], ensure_ascii=False)))
    for pin in check["pins"]:
        if not pin["caught"]:
            out.write("🔴 自检夹具逃掉：{0}（term={1}）——「全等」是硬编码，本件红\n".format(
                pin["fixture"], pin["term"]))
    for size in coverage["missing"]:
        out.write("🔴 档位 {0} 没有读数：{1}\n".format(
            size, coverage["reasons"][str(size)]))
    return rc


#: ---------------------------------------------------------------- CLI
def describe_prepare_threshold(value) -> str:
    """把连接上真正生效的 prepare 阈值写成一句话——计划复用会改规划器开关的效果，
    所以每一轮量测都必须自报这一项，不许靠人回忆口令。"""
    if value is KEEP_PSYCOPG_DEFAULT:
        return "psycopg-default"
    if value is None:
        return "none"
    return str(int(value))


def parse_prepare_threshold(raw):
    """none = 永不 prepare（本单默认）；psycopg = 不干预；其余收非负整数。"""
    text = str(raw).strip().lower()
    if text in ("none", "null", "off"):
        return None
    if text in ("psycopg", "default", "keep"):
        return KEEP_PSYCOPG_DEFAULT
    try:
        value = int(text)
    except ValueError:
        raise SystemExit("[前置不满足] --prepare-threshold 只收 none/psycopg/非负整数，"
                         "拿到 {0!r}".format(raw))
    if value < 0:
        raise SystemExit("[前置不满足] --prepare-threshold 不许是负数：{0}".format(value))
    return value


def parse_sizes(raw: str) -> list:
    values = [int(piece) for piece in str(raw).split(",") if piece.strip()]
    if not values:
        raise SystemExit("[前置不满足] --sizes 是空的")
    if min(values) < 1:
        raise SystemExit("[前置不满足] --sizes 每一档必须是正整数：{0}".format(raw))
    if sorted(values) != values or len(set(values)) != len(values):
        raise SystemExit("[前置不满足] --sizes 必须严格递增且不重复：{0}".format(raw))
    return values


def parse_ks(raw: str) -> list:
    values = [int(piece) for piece in str(raw).split(",") if piece.strip()]
    if not values or min(values) < 1:
        raise SystemExit("[前置不满足] --k 至少一枚且必须是正整数：{0}".format(raw))
    return sorted(set(values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=TOOL, description="R579 索引拐点探针")
    parser.add_argument("--action", default="plan",
                        choices=["plan", "snapshot", "repro", "build", "measure", "report",
                                 "cleanup", "db-set", "guard-proof", "emit-data", "repeat-probe"])
    parser.add_argument("--sizes", default=None,
                        help="逗号分隔、严格递增；缺省即 DEFAULT_SIZES。"                             "只有口令里点名的那一串才算判据 2 的清单")
    parser.add_argument("--k", dest="k", default="5,20")
    parser.add_argument("--queries", type=int, default=40)
    parser.add_argument("--warm-rounds", dest="warm_rounds", type=int, default=1,
                        help="计时之前把全部向量真执行几遍（0 = 不热身，读数会含冷启动）")
    parser.add_argument("--plan-samples", dest="plan_samples", type=int, default=3)
    parser.add_argument("--plan-text-keep", dest="plan_text_keep", type=int,
                        default=PLAN_TEXT_KEEP_DEFAULT,
                        help="前 N 枚 EXPLAIN 留全文，其余只留计划头")
    parser.add_argument("--floor-samples", dest="floor_samples", type=int, default=25,
                        help="协议往返本身的取样枚数；0 = 不量")
    parser.add_argument("--db-prefix", dest="db_prefix", default=SANDBOX_DB_PREFIX_DEFAULT)
    parser.add_argument("--sandbox-db", dest="sandbox_db", default=SANDBOX_DB_PREFIX_DEFAULT)
    parser.add_argument("--prod-db", dest="prod_db", default="enterprise_brain")
    parser.add_argument("--db-user", dest="db_user", default="enterprise_brain")
    parser.add_argument("--states", default=",".join(STATES))
    parser.add_argument("--expect-ef-search", dest="expect_ef_search", type=int, default=None)
    parser.add_argument("--prepare-threshold", dest="prepare_threshold", default="none",
                        help="同连接复用计划的阈值；none = 永不 prepare（本单默认），"
                             "psycopg = 不干预（沿用 psycopg3 缺省 5）")
    parser.add_argument("--repeats", type=int, default=8,
                       help="repeat-probe：同一枚问题连打几次")
    parser.add_argument("--query-index", dest="query_index", type=int, default=5,
                       help="repeat-probe 用的是第几枚查询向量（缺省 5 = measure 的第一枚计时样本）")
    parser.add_argument("--repro-k", dest="repro_k", type=int, default=5,
                        help="第 1 步复现派工词那条 limit 5")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--parallel-maintenance-workers",
                        dest="parallel_maintenance_workers", default="0",
                        help="建索引的并行度；0=串行（容器 /dev/shm 只有 64 MB）")
    parser.add_argument("--maintenance-work-mem", dest="maintenance_work_mem",
                        default="512MB")
    parser.add_argument("--min-content-bytes", dest="min_content_bytes", type=int, default=0)
    parser.add_argument("--content-bytes-override", dest="content_bytes_override",
                        type=int, default=None,
                        help="把合成正文钉到这一枚字节数（行宽校准用）；不给就用生产现读")
    parser.add_argument("--from-results", dest="from_results", default=None)
    parser.add_argument("--before", default=None)
    parser.add_argument("--after", default=None)
    parser.add_argument("--tamper", default="none",
                        choices=["none", "drop-only-in-compare", "drop-order-compare"])
    parser.add_argument("--data-dir", dest="data_dir", default="r579-drill")
    parser.add_argument("--dimension", type=int, default=768)
    parser.add_argument("--classification", type=int, default=1)
    parser.add_argument("--content-bytes", dest="content_bytes", type=int, default=782)
    parser.add_argument("--embedding-model", dest="embedding_model",
                        default="nomic-embed-text")
    parser.add_argument("--distance-function", dest="distance_function", default="l2")
    parser.add_argument("--tree-base", dest="tree_base", default="")
    parser.add_argument("--started-at", dest="started_at", default="")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.sizes_explicit = args.sizes is not None
    args.sizes = parse_sizes(args.sizes if args.sizes is not None else DEFAULT_SIZES)
    args.ks = parse_ks(args.k)
    args.prepared = parse_prepare_threshold(args.prepare_threshold)
    args.states = tuple(piece.strip() for piece in str(args.states).split(",")
                        if piece.strip())
    for state in args.states:
        if state not in STATES:
            raise SystemExit("[前置不满足] --states 不认识这一态：{0}".format(state))
    if str(args.prod_db) not in PROTECTED_DBS:
        raise SystemExit("[前置不满足] --prod-db 必须是受保护库名之一 {0}，拿到 {1!r}："
                         "不受保护的库名会让写域守卫失去凭据".format(
                             sorted(PROTECTED_DBS), args.prod_db))
    if args.queries < 1:
        raise SystemExit("[前置不满足] --queries 至少 1")
    out = sys.stdout
    if args.action in ("snapshot", "repro", "build", "measure", "cleanup", "db-set",
                       "guard-proof", "repeat-probe"):
        from app.rag import pg_store                      # 唯一真源在这里落地
        if getattr(pg_store, "configured_hnsw_ef_search", None) is None:
            out.write("[前置不满足] 这棵树里没有 configured_hnsw_ef_search：宽度无真源可读\n")
            return EXIT_PRECONDITION
        width = pg_store.configured_hnsw_ef_search()
        if args.expect_ef_search is not None and int(args.expect_ef_search) != int(width):
            out.write("[对账不上] 真源现场交回 {0}，--expect-ef-search 期望 {1}：整单不跑\n"
                      .format(width, args.expect_ef_search))
            return EXIT_PRECONDITION
        if not args.started_at:
            args.started_at = _now()
    if args.action == "plan":
        return action_plan(args, out)
    if args.action == "emit-data":
        return action_emit_data(args, out)
    if args.action == "report":
        if not args.from_results:
            out.write("[前置不满足] report 需要 --from-results 指一份 measure 产物\n")
            return EXIT_PRECONDITION
        return action_report(args, out)
    if args.action == "snapshot":
        db = open_prod(args)
        try:
            from app.rag import pg_store as _pg
            out.write(json.dumps(prod_snapshot(db, _pg.DEFAULT_VECTOR_TABLE),
                                 ensure_ascii=False,
                                 indent=args.indent, default=str) + "\n")
        finally:
            db.close()
        return EXIT_OK
    if args.action == "db-set":
        return action_db_set(args, out)
    if args.action == "guard-proof":
        return action_guard_proof(args, out)
    if args.action == "repeat-probe":
        return action_repeat_probe(args, pg_store, out)
    if args.action == "cleanup":
        return action_cleanup(args, out)
    from app.rag import pg_store
    shape = load_shape_prod(args, pg_store)
    if args.action == "repro":
        db = open_prod(args)
        try:
            out.write(json.dumps(repro_on_prod(args, pg_store, shape), ensure_ascii=False,
                                 indent=args.indent, default=str) + "\n")
        finally:
            db.close()
        return EXIT_OK
    if args.action == "build":
        return action_build(args, pg_store, out)
    if args.action == "measure":
        return action_measure(args, pg_store, out)
    out.write("[前置不满足] 没有这个动作：{0}\n".format(args.action))
    return EXIT_PRECONDITION


if __name__ == "__main__":
    sys.exit(main())