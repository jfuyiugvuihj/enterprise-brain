#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R59c 判据 ①②③ · 服务内端到端召回对照量具（计划书 §9.3 的读数能力）。

跑法（仓库根、项目 venv 解释器；产物一律落仓外，别落进 scripts/）：

    python scripts/r59c_recall_compare.py selfcheck --verbose
    python scripts/r59c_recall_compare.py census    --out %TEMP%/r59c_census.json
    python scripts/r59c_recall_compare.py collect --arm chroma-hot  --out %TEMP%/r59c_hot.jsonl
    python scripts/r59c_recall_compare.py collect --arm chroma-cold --out %TEMP%/r59c_cold.jsonl
    python scripts/r59c_recall_compare.py collect --arm pgvector    --out %TEMP%/r59c_pg.jsonl
    python scripts/r59c_recall_compare.py compare   %TEMP%/r59c_chroma_hot.jsonl \
        %TEMP%/r59c_chroma_cold.jsonl %TEMP%/r59c_pgvector.jsonl --base chroma-hot \
        --jsonl %TEMP%/r59c_pairs.jsonl --csv %TEMP%/r59c_pairs.csv \
        --summary %TEMP%/r59c_summary.json

它量什么（一句话）
------------------
同一批题、同一枚服务入口 POST /api/v1/observability/retrieval/debug
（app/api/v1/observability.py:481，docstring 原话 "Run one permission-scoped retrieval and
return a bounded, replayable report"），在读后端开关的两侧各跑一遍，产出可入档的逐题对照
读数，外加一句硬判定：§9.3 的 ①②③ 这三格今天到底量到了没有。
为什么这一回改走服务、不再直连向量库（= 误判 #43 的结构性免疫）
------------------------------------------------------------
上一班那份读数整体作废，根因不是算错，是两侧样本都取错了对象（跟进单 §93.12、看板 §4BT 三）：
PG 腿连到宿主机 5432 上那台没有 vector_scope 的野 PostgreSQL，Chroma 腿读到 %TEMP% 下 401 枚
的沙盒，而生产读路径是 docker 卷 enterprise-brain_vectordb -> 容器内 /app/chroma_db 的 1008 枚。
计划书 §9.4 因此写下"别在宿主机上跑这组对比"。

本件换一条路，把这一类错变成结构上不可能：它不连库、不开 Chroma、不拼 DSN、不猜目录，只发 HTTP。
"读的是哪一库"不再由量具声称，而由服务自己的行为作证 —— 每发前后各读一次
GET /api/v1/health/details，取 search_shape.answered_by 的**增量**；那三枚答复方码
（chroma / hot_index / pgvector，app/rag/retriever.py:82-87）就是"这一问的语义腿是谁答的"。
声明 --arm pgvector 而增量里只有 chroma ⇒ 整臂判为**身份未证实**（退出码 3），不许它带着
"两侧一致"的字样进档案。配置字符串不算证据，答复方才算。

三条继承纪律（出处钉死）
----------------------
1. 两个空集合不等于一致（docs/testing/r59-recall-reading-2026-09-24.md 作废理由 2）。两侧都交
   0 行的题：jaccard 一律 null、both_empty 记 true、单独计数，永不进"一致"那一栏。R158 那
   24/135 题正是会被粗心工具印成"两侧一致"的形状。
2. 集合与名次的算法不另立一份：rank_map / kendall_tau / first_difference 三枚与
   scripts/r59_recall_compare.py:375-409 **逐字同值**（共有元素少于两枚不算 tau；
   first_diff_rank 是 1 基；空并集的 jaccard 交回 None）；一题一行的键名（jaccard /
   same_set / same_order / first_diff_rank / mean_abs_rank_shift / max_abs_rank_shift /
   kendall_tau / overlap_ratio）沿用那一份 compare_question（:412-465）的形状，好让 R59b
   的 135 题旧读数能与本件新读数逐列对差。本件的 compare_pair 只是"多臂两两配对"的薄组合，
   不改动上面任何一枚的语义 —— 另立一份算法就是再造一次"两份会过期的数字"。
3. 口径常数不手抄：DEFAULT_TOP_K / MAX_TOP_K / MAX_QUERY_CHARS / MAX_EXCERPT_CHARS 用 ast 从
   app/api/v1/observability.py 现读（server_limits）；题集用常驻件
   scripts/check_eval_evidence_coverage.py:load_rows 现装载 —— 那枚函数自带"105 行 / id 唯一 /
   must_contain 非空 / 词条总数"四道 StructureDrift 闸。题目从 105 题评测集**只读引用**，
   改一个字它自己就红，本件不另造一套题集读法。
与 R59b 那 135 题读数的区别（两格各归各，不许混用）
--------------------------------------------------
R59b 比的是两条**向量腿各自交回的 id 列表**（库层，含 --where-json 下推，两侧各 1008 枚）。
本件比的是**服务交回的最终结果集**：里面还过着 BM25 多路召回、_deduplicate、rrf_fusion、
_apply_activity_prior、装箱与 MAX_TOP_K 截断。所以"R59b 两侧一致"推不出"服务输出一致"，反之
亦然 —— §9.3 第 ① 格要的就是后者，而它至今没有读数。谁也不许拿自己那半替对方翻绿。

三臂设计与 ②「热集让路代价」
--------------------------
_hot_hits（app/rag/retriever.py:1118，让路判定在 :1129-1133）常驻的是 **Chroma 那一份向量**；一旦
pgvector_reads_enabled() 为真，整层立刻让路并记原因码 hot_index_read_backend_switched。
于是"切读"一次改了两件事：换引擎 + 撤加速层。两件事混在一个差里就量不出代价，本件因此要三臂
（缺一臂就少一项，产物里如实写 null，不许拿两臂硬凑三项）：

    A2  chroma-hot    读后端=chroma   HOT_INDEX_ENABLED=on    （要量它得先翻这枚 env）
    A1  chroma-cold   读后端=chroma   HOT_INDEX_ENABLED 未设   （**今天生产的形状**：外部向量库裸奔）
    B   pgvector      读后端=pgvector 热集必然让路             （见下面「B 臂今天翻不出来」）

    🔴 三臂怎么落到进程上（在 4e29141 上复核，别照抄旧假设）：
      * HOT_INDEX_ENABLED 是**真 env 开关**（app/rag/hot_index.py:45,151-154：未设置、空、
        不认识的值一律算关），而 deploy/.env.server 今天没有这一行 ⇒ **生产现状 = A1
        chroma-cold**；要量 A2 才需要加行 + recreate backend。
      * INDEX_BACKEND **不是 env**：app/rag/indexing.py:47 是模块级字面量
        （INDEX_BACKEND = INDEX_BACKEND_DEFAULT），read_backend() 读的就是那枚常量。本单在
        零写入条件下实测：把 INDEX_BACKEND=pgvector 塞进环境再 import，read_backend() 仍回
        'chroma'、pgvector_reads_enabled() 仍 False。⇒ **B 臂今天翻不出来**，除非有人改代码
        （tests/test_r59b_pg_read_switch.py:154 还专门钉着「字面量改掉这条立刻红」）。
        翻法见 docs/testing/r59c-window-ops-2026-09-25.md §1.1，还原见同文 §7。
      * ⇒ 臂身份检查因此不是形式主义：往 env 里加一行 INDEX_BACKEND=pgvector 再 recreate，
        服务照旧由 chroma 答复，本件当场退出码 3 判整臂作废 —— 那正是「假合闸」的形状。

    热集收益   hot_gain_ms        = paired(A1 - A2)  —— 让路之前热集原本省下多少
    切读裸代价 switch_cost_ms    = paired(B  - A1)  —— 只换引擎、两侧都没有热集
    净让路代价 net_yield_cost_ms = paired(B  - A2)  = switch_cost_ms + hot_gain_ms
      （符号：三项都是「减数臂 - 被减臂」的有符号差，热集更快时 hot_gain 为正，所以净代价
        是裸代价与热集收益之**和**；selfcheck 的 P11 钉的就是这条恒等式）
    噪声地板   noise_floor_ms     = 同臂同题 --repeats 组内散布的 p95（不给重发就是 null）
    代价与地板同量级即判"量不出"：|代价| <= noise_floor_ms 时本件把 verdict 写成
    NOT_RESOLVED，绝不把那一格的小数当代价进档案（§9.3 ② 要的是代价，不是方向）。
    命中分布侧同时给：热集实际服务占比、让路影响题数、其中名次变了/集合变了几题。
第 ③ 格（选择性权限过滤）在本件里的位置
--------------------------------------
本件**能**量 ③，但**不能凭空造出可选性**：谓词由 principal 决定（app/rag/filters.py:141 起 ——
管理员只带 classification $in [1..clearance]，普通人再加 department $in [...]），而现库
classification 全 = 1、department 全 = ""。所以本件对 ③ 只交付两样，不多不少：

  * 逐题影子权限复算（shadow_permission_check）：拿响应自带的 permission_filter 与逐条命中的
    classification / department 独立再判一次，越权行 = 硬红。这不是产品判定的第二份实现 ——
    它不决定谁能看什么，只对"已经交出来的东西"提异议；审计面本来就该有一只不相干的哨子。
    响应里那枚恒真的 permission_checked: True 是服务端自述，本件不采信。
  * 可选性硬闸（census 子命令 + 汇总里的 selectivity_screen）：普查
    GET /api/v1/documents/catalog 里 distinct department / classification 的分布，配合逐题
    scope_reason。判据：谓词放行的块数必须落在 (0, 全库) 开区间且 department 至少两个取值；
    不满足就整格 NOT_MEASURED 并写明"是语料没有可选性"，不是"入口跑过了"。
    沙盒语料怎么造、要业主批哪些 DDL/DML，见 scripts/r59c_sandbox_corpus.py 与
    docs/testing/r59c-method-2026-09-25.md。

零写入承诺的真实边界（不掩饰）
------------------------------
不发答案、不进 pandas、不出图，但每一发 retrieval/debug 在服务侧留下两笔账：
run_retrieval_debug 走 trace_store.record_event（app/rag/debug.py:66）写一条
retrieval.completed，路由收尾再记一条 retrieval/debug 的 allowed 审计
（app/api/v1/observability.py:541），而 administrator_scope 每一发都会经 record_retrieval_scope
落一行。所以"只读"对业务数据成立，对 trace / audit 台账**不成立**。本件的处置是让这些账
可辨认、可清点：request_id / trace_id 一律以 r59c-<arm>- 开头，事后
grep -c "r59c-" data/traces/events.jsonl 就能对上数。要真零写入得另立单改服务端，不在本单写域。

每发仍打模型（别以为它便宜）
----------------------------
入口内部走 pipeline.search_for_principal → 一发查询改写（现值 4.08 s/发）+ 每枚召回问一发
embedding，MAX_RECALL_QUERIES = 5（app/rag/retrieval_pipeline.py:276）⇒ 一题最多 5 发 embedding。
预算闸 --max-requests（默认 260）超限即停并可 --resume 续跑；--dry-run 一发都不发，并当场把
出站 socket 换成会抛的桩自证零网络。
退出码（不可合并，合并就是说谎）
--------------------------------
    0 正常出数。collect：全部题收完且臂身份均成立；compare：两臂逐题集合一致且各臂身份均成立。
    1 compare：至少一题不一致 —— 这是**正常结论**，交人判读，不是失败。
    2 前置不满足（题集漂移 / 凭据缺失 / 服务不可达 / 命中身份键不可用 / 连续失败触顶），
      这种退出**不出任何召回结论**。
    3 臂身份未证实：某一臂声明的后端与 answered_by 增量不符 ⇒ 这份读数只有半张脸。
    4 collect：有题失败或触发预算闸，但仍有可用读数（配 --resume 续跑；计数在产物头与逐行输出）。
  130 收到 Ctrl-C：已发的读数留在盘上，用 --resume 接着跑。

自检（判据 ④：零容器、零模型、零网络条件下真跑一遍）
--------------------------------------------------
    python scripts/r59c_recall_compare.py selfcheck --verbose
它用假 Transport（不开 socket）走完 collect -> read -> compare -> 三份产物 全链路，再逐条落
反证钉（教训 #46：钉下去红的必须是**那一格的列**，不是全局由绿变红）：P1 解析、P2 集合/名次、
P3 写表回读、P4 臂身份、P5 单题集合抽错、P6 越权行、P7 可选性、P8 噪声地板、P9 空集不等于一致。
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 题集与常驻装载件（判据原话："题目从 105 题评测集只读引用"）。
COVERAGE_REL = Path("scripts/check_eval_evidence_coverage.py")
DEFAULT_FIXTURE = Path("tests/fixtures/business_evaluation_100.jsonl")
OBSERVABILITY_REL = Path("app/api/v1/observability.py")

SCHEMA = "r59c-recall-run-2"
TOOL = "scripts/r59c_recall_compare.py"

ROUTE_LOGIN = "/api/v1/login"
ROUTE_HEALTH = "/api/v1/health/details"
ROUTE_DEBUG = "/api/v1/observability/retrieval/debug"
ROUTE_CATALOG = "/api/v1/documents/catalog"

#: 语义腿的三枚答复方码，逐字取自 app/rag/retriever.py:82-87。keyword_scan 不算：它是向量腿
#: 整个下线时的关键词退化，落在哪一臂都不代表"这一臂的引擎答了"，混进凭证就会造出假一致。
LEG_CHROMA = "chroma"
LEG_HOT = "hot_index"
LEG_PGVECTOR = "pgvector"
SEMANTIC_LEGS = frozenset({LEG_CHROMA, LEG_HOT, LEG_PGVECTOR})

#: 臂声明 -> 允许的语义腿答复方。多一枚即身份未证实。
ARMS = {
    "chroma-hot": frozenset({LEG_CHROMA, LEG_HOT}),
    "chroma-cold": frozenset({LEG_CHROMA}),
    "pgvector": frozenset({LEG_PGVECTOR}),
}
#: 臂的**开关声明**，只进产物头与 dry-run 提示，不当证据用（证据是 answered_by）。
#: 写成「怎么落到进程」而不是「env 里写什么」：INDEX_BACKEND 今天不是 env（app/rag/indexing.py:47
#: 是模块级字面量），拿它当环境变量设一遍就是假合闸 —— 详见 docs/testing/r59c-window-ops-2026-09-25.md §1。
ARM_SWITCHES = {
    "chroma-hot": "读后端=chroma(默认字面量) + HOT_INDEX_ENABLED=on(env)",
    "chroma-cold": "读后端=chroma(默认字面量) + HOT_INDEX_ENABLED 未设/关(env) = 今天生产",
    "pgvector": "读后端=pgvector(需改代码字面量,非 env) + 热集必然让路",
}
#: 该臂对热集开关的期望：True 必须开、False 必须关、None 不作要求（让路态）。
HOT_EXPECTED = {"chroma-hot": True, "chroma-cold": False, "pgvector": None}

EXIT_OK = 0
EXIT_DIFFERS = 1
EXIT_PRECONDITION = 2
EXIT_ARM_UNVERIFIED = 3
EXIT_PARTIAL = 4
EXIT_INTERRUPTED = 130

FILTER_KEY_CLASSIFICATION = "classification"
FILTER_KEY_DEPARTMENT = "department"

# --------------------------------------------------------------- 口径常数（现读，不抄第二份）

def _module_literal(path: Path, name: str) -> int:
    """从产品源码里 ast 取一枚整型常数；取不到就抛。抄一份常数就是养一份会过期的假数。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = node.value
                if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
                    value = value.operand
                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    return int(value.value)
    raise RuntimeError(f"{path.name} 里读不到整型常数 {name}：产品改了形状，本件要跟改")


def server_limits() -> dict:
    """observability 的现役上限（app/api/v1/observability.py:39-41、:53）。"""
    path = REPO_ROOT / OBSERVABILITY_REL
    if not path.is_file():
        raise RuntimeError(f"找不到 {path}，服务端口径无从校对")
    return {
        "source": str(OBSERVABILITY_REL),
        "default_top_k": _module_literal(path, "DEFAULT_TOP_K"),
        "max_top_k": _module_literal(path, "MAX_TOP_K"),
        "max_query_chars": _module_literal(path, "MAX_QUERY_CHARS"),
        "max_excerpt_chars": _module_literal(path, "MAX_EXCERPT_CHARS"),
        "max_rewrites": _module_literal(path, "MAX_REWRITES"),
    }


def git_revision() -> str:
    explicit = str(os.getenv("R59C_REVISION", "")).strip()
    if explicit:
        return explicit[:40]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001 - 拿不到 revision 不该炸掉一次测量，但也不能编一个
        return "unknown"
    return (out.stdout or "").strip()[:40] or "unknown"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_questions(fixture: Path, limit: int = 0) -> list:
    """用常驻件装载 105 题（四道 StructureDrift 闸一起生效），只取本件要用的字段。"""
    loader = REPO_ROOT / COVERAGE_REL
    if not loader.is_file():
        raise RuntimeError(f"找不到常驻装载件 {loader}")
    spec = importlib.util.spec_from_file_location("r59c_coverage_loader", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rows = module.load_rows(fixture if fixture.is_absolute() else REPO_ROOT / fixture)
    out = [{"id": str(row.get("id") or ""), "question": str(row.get("question") or ""),
            "category": str(row.get("category") or ""), "tier": str(row.get("tier") or ""),
            "must_contain": [str(term) for term in (row.get("must_contain") or [])]}
           for row in rows]
    if not out:
        raise RuntimeError("题集装载成 0 题：没有题就没有读数")
    return out[:limit] if limit else out

# ---------------------------------------------------------------------------- HTTP 通路
#
# 代理：宿主上挂着 Clash 会劫 127.0.0.1（docs/handoff/2026-09-17-eval-real-run-runbook.md §6），
# 所以这里与 scripts/eval_transport_ask_v2.py:120 同一招 —— 空 ProxyHandler，等价 curl --noproxy "*"。
# 凭据只从环境变量取，代码里零硬编；token 只在内存，永不进产物。

class Transport:
    """只讲四条路由的瘦客户端：login / health / catalog / debug。"""

    def __init__(self, base_url, username, password, *, timeout=90.0, opener=None):
        self.base_url = str(base_url).rstrip("/")
        self.username = str(username or "")
        self.password = str(password or "")
        self.timeout = float(timeout)
        self._opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.token = ""

    def _request(self, path, payload=None, method="POST"):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=body,
                                         headers=headers, method=method)
        with self._opener.open(request, timeout=self.timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8", "replace"))

    def login(self) -> str:
        if not self.token:
            body = self._request(ROUTE_LOGIN, {"username": self.username,
                                           "password": self.password})
            self.token = str(body.get("token") or "")
        if not self.token:
            raise RuntimeError("login 响应里没有 token 键（app/api/v1/auth.py:60-66）")
        return self.token

    def health(self) -> dict:
        return self._request(ROUTE_HEALTH, None, method="GET")

    def catalog(self) -> dict:
        return self._request(ROUTE_CATALOG, None, method="GET")

    def debug(self, query, top_k, request_id, trace_id) -> dict:
        return self._request(ROUTE_DEBUG, {"query": query, "top_k": int(top_k),
                                           "request_id": request_id, "trace_id": trace_id})


def credentials_from_env() -> tuple:
    base = (os.getenv("R59C_BASE_URL") or os.getenv("EVAL_BASE_URL") or "http://127.0.0.1:8001")
    user = os.getenv("R59C_USERNAME") or os.getenv("EVAL_USERNAME") or ""
    password = (os.getenv("R59C_PASSWORD") or os.getenv("EVAL_PASSWORD")
                or os.getenv("EB_EVAL_PASSWORD") or "")
    return base.rstrip("/"), user, password


def _as_int(value):
    """服务端 _bounded_value 把所有数字过成 float（observability.py:231），chunk_index=3 到手里
    就是 3.0。不在这里归一，两侧集合就永远"不一致" —— 这一格由 selfcheck 的 P1 钉着。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(round(number))


def _is_finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False

# ------------------------------------------------------------- 响应解析（判据 ④ 的第一路）

def normalize_hits(report: dict) -> list:
    """响应里的 results -> 名次化命中。命中身份 = "source#chunk_index"。

    为什么用这对而不是 excerpt 前缀：chunk_vectors 的主键就是 Chroma id，而 id 的键空间是
    (filename, ordinal)（migrations/0010_pgvector_chunks.sql:153 那条 UNIQUE），所以
    (source, chunk_index) 是两侧同源的身份；excerpt 会被服务端截到 MAX_EXCERPT_CHARS，
    拿它当身份会制造假一致。
    """
    hits = []
    for position, item in enumerate(report.get("results") or [], start=1):
        if not isinstance(item, dict):
            item = {"source": str(item)}
        source = str(item.get("source") or "")
        index = _as_int(item.get("chunk_index"))
        score = item.get("score")
        hits.append({
            "rank": position,
            "key": (f"{source}#{index}" if source and index is not None else ""),
            "source": source,
            "chunk_index": index,
            "classification": _as_int(item.get("classification")),
            "department": str(item.get("department") or ""),
            "score": (float(score) if _is_finite(score) else None),
            "excerpt": str(item.get("excerpt") or ""),
        })
    return hits


def parse_scope_filter(where) -> dict:
    """谓词拆成"放行的密级集合 + 部门集合"。看不懂就交回 parsed=False，绝不猜成放行全部。"""
    levels = None
    departments = None
    keys = []
    stack = [where]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            return {"parsed": False, "levels": None, "departments": None,
                    "shape": "not-dict:" + type(node).__name__}
        for key, value in node.items():
            if key == "$and":
                if not isinstance(value, list) or not value:
                    return {"parsed": False, "levels": None, "departments": None,
                            "shape": "$and-not-list"}
                stack.extend(value)
                continue
            keys.append(str(key))
            if key not in (FILTER_KEY_CLASSIFICATION, FILTER_KEY_DEPARTMENT):
                return {"parsed": False, "levels": None, "departments": None,
                        "shape": "unknown-key:" + str(key)}
            if not isinstance(value, dict) or list(value) != ["$in"]:
                return {"parsed": False, "levels": None, "departments": None,
                        "shape": str(key) + "-op"}
            values = value["$in"]
            if not isinstance(values, list):
                return {"parsed": False, "levels": None, "departments": None,
                        "shape": str(key) + "-in-not-list"}
            if key == FILTER_KEY_CLASSIFICATION:
                levels = frozenset(item for item in (_as_int(each) for each in values)
                                   if item is not None)
            else:
                departments = frozenset(str(item) for item in values)
    if len(keys) != len(set(keys)):
        return {"parsed": False, "levels": None, "departments": None, "shape": "duplicate-key"}
    return {"parsed": True, "levels": levels, "departments": departments,
            "shape": "+".join(sorted(set(keys))) or "empty"}

def shadow_permission_check(report: dict, hits: list) -> dict:
    """拿响应自带的 permission_filter 独立复算一遍已交出的命中（判据 ③ 的越权哨）。

    判序照抄 DocumentRetrievalScope.allows（app/rag/filters.py:46-57）：密级读不出来 = 不可见，
    密级不在集合 = 不可见，departments 为 None（管理员）= 放行，否则部门必须在集合内。
    谓词看不懂时 verdict 交回 unknown —— 这一格宁可不判，也不许判成"干净"。
    """
    parsed = parse_scope_filter(report.get("permission_filter"))
    if not parsed["parsed"]:
        return {"verdict": "unknown", "reason": "filter-unparsable:" + parsed["shape"],
                "leaks": [], "checked": len(hits), "levels": None, "departments": None}
    levels, departments = parsed["levels"], parsed["departments"]
    leaks = []
    for hit in hits:
        if levels is not None and hit["classification"] not in levels:
            why = "clearance_insufficient"
        elif departments is not None and hit["department"] not in departments:
            why = "department_scope_denied"
        else:
            continue
        leaks.append({"rank": hit["rank"], "key": hit["key"], "why": why,
                      "classification": hit["classification"], "department": hit["department"]})
    return {"verdict": "clean" if not leaks else "leak", "reason": "",
            "leaks": leaks, "checked": len(hits),
            "levels": sorted(levels) if levels is not None else None,
            "departments": sorted(departments) if departments is not None else None}


def evidence_proxy(row: dict, hits: list) -> dict:
    """must_contain 词条在命中摘录里的字面覆盖度 —— 服务面唯一量得到的证据代理。

    它是代理不是判据：摘录被服务端截到 MAX_EXCERPT_CHARS，所以只会少报不会多报；真判分仍归
    scripts/run_quality_evaluation.py 那把尺。列名一律带 proxy_ 前缀，免得被当成引证覆盖率。
    """
    terms = [term for term in (row.get("must_contain") or []) if term]
    haystack = " \n ".join(hit["excerpt"] for hit in hits)
    hit_terms = [term for term in terms if term in haystack]
    return {"proxy_terms_total": len(terms), "proxy_terms_hit": len(hit_terms),
            "proxy_any_hit": bool(hit_terms),
            "proxy_all_hit": bool(terms) and len(hit_terms) == len(terms)}


# ------------------------------------------------------------- 腿凭证（误判 #43 的闸）

def _block(health: dict, name: str) -> dict:
    node = (health or {}).get(name)
    return node if isinstance(node, dict) else {}


def leg_evidence(pre: dict, post: dict) -> dict:
    """两拍 /health/details 之间：语义腿到底是谁答的、热集有没有服务、语料动没动。

    取增量而不是取 last：一发 debug 内部会问 MAX_RECALL_QUERIES 次（多路改写），last 那一枚
    只反映最末一问；增量能把"这一发里有没有混着两条腿"照出来（半切态就长这样）。
    """
    pre_legs = _block(pre, "search_shape").get("answered_by") or {}
    post_legs = _block(post, "search_shape").get("answered_by") or {}
    delta = {}
    for key in sorted(set(pre_legs) | set(post_legs)):
        step = int(post_legs.get(key, 0) or 0) - int(pre_legs.get(key, 0) or 0)
        if step:
            delta[str(key)] = step
    semantic = {key: step for key, step in delta.items() if key in SEMANTIC_LEGS}
    hot_pre, hot_post = _block(pre, "hot_index"), _block(post, "hot_index")
    hot_delta = {}
    for key in ("hits", "misses", "invalidations"):
        step = int(hot_post.get(key, 0) or 0) - int(hot_pre.get(key, 0) or 0)
        if step:
            hot_delta[key] = step
    observed = sorted(semantic)
    return {"legs_delta_all": delta, "legs_delta_semantic": semantic,
            "semantic_legs_observed": observed,
            "uniform_semantic_leg": (observed[0] if len(observed) == 1 else ""),
            "mixed_semantic_leg": len(observed) > 1,
            "semantic_answers": sum(semantic.values()),
            "keyword_fallbacks": int(delta.get("keyword_scan", 0) or 0),
            "hot_enabled": hot_post.get("enabled"),
            "hot_resident_chunks": _as_int(hot_post.get("resident_chunks")),
            "hot_roster_fresh": hot_post.get("roster_fresh"),
            "hot_max_chunks": _as_int(hot_post.get("max_chunks")),
            "hot_delta": hot_delta,
            "hot_last_bypass_reason": str(hot_post.get("last_bypass_reason") or ""),
            "health_status": str((post or {}).get("status") or (pre or {}).get("status") or ""),
            "health_problems": [str(item) for item in _block(post, "problems")][:10],
            "invalidations_during_request": int(hot_delta.get("invalidations", 0) or 0)}


def verify_arm(arm: str, evidence: dict) -> dict:
    """这一发的答复方增量配不配得上 --arm 的声明。不配 ⇒ 整臂不许进对照结论。"""
    observed = set(evidence["semantic_legs_observed"])
    if not observed:
        return {"ok": False, "reason": "no-semantic-answer-recorded", "observed": []}
    unexpected = sorted(observed - ARMS[arm])
    if unexpected:
        return {"ok": False, "observed": sorted(observed),
                "reason": "answered-by-unexpected:" + ",".join(unexpected)}
    expected_hot = HOT_EXPECTED[arm]
    if expected_hot is True and evidence.get("hot_enabled") is False:
        return {"ok": False, "observed": sorted(observed),
                "reason": "hot-index-switch-off-while-arm-claims-hot"}
    if expected_hot is False and evidence.get("hot_enabled") is True:
        return {"ok": False, "observed": sorted(observed),
                "reason": "hot-index-switch-on-while-arm-claims-cold"}
    return {"ok": True, "reason": "", "observed": sorted(observed)}

# --------------------------------------------------------------------- collect（判据 ① 主体）

def debug_request_ids(arm: str, question_id: str, top_k: int, rep: int) -> tuple:
    """可辨认的 request/trace id：事后能在 trace / audit 台账里把自己这一窗的账点清。"""
    stamp = f"r59c-{arm}-{question_id}-k{top_k}-r{rep}-{uuid.uuid4().hex[:8]}"
    return stamp, stamp + ":t"


def build_record(*, arm: str, row: dict, top_k: int, rep: int, report: dict,
                 pre: dict, post: dict, client_ms: float, attempts: int,
                 limits: dict) -> dict:
    hits = normalize_hits(report)
    evidence = leg_evidence(pre, post)
    shadow = shadow_permission_check(report, hits)
    check = verify_arm(arm, evidence)
    bounds = report.get("bounds") or {}
    return {"kind": "request", "schema": SCHEMA, "arm": arm,
            "qid": row["id"], "category": row["category"], "tier": row["tier"],
            "top_k": int(top_k), "rep": int(rep),
            "query_chars": len(row["question"]), "query_sha": sha12(row["question"]),
            "status": "ok", "http_status": 200, "attempts": int(attempts), "error": "",
            "recorded_at": now_iso(), "client_ms": round(client_ms, 2),
            "server_duration_ms": (_as_ms(report.get("duration_ms"))),
            "rewrites_count": len(report.get("rewrites") or []),
            "rewrites_sha": sha12(json.dumps(report.get("rewrites") or [], ensure_ascii=False)),
            "scope_reason": str(report.get("scope_reason") or ""),
            "permission_filter": report.get("permission_filter") or {},
            "shadow_verdict": shadow["verdict"], "shadow_reason": shadow["reason"],
            "admitted_levels": shadow["levels"], "admitted_departments": shadow["departments"],
            "permission_leaks": shadow["leaks"],
            "bounds_truncated": bool(bounds.get("truncated")),
            "results_total": _as_int(bounds.get("results_total")),
            "hits": [{key: hit[key] for key in ("rank", "key", "source", "chunk_index",
                                                "classification", "department", "score")}
                     for hit in hits],
            "hits_unnamed": [hit["rank"] for hit in hits if not hit["key"]],
            "excerpt_cap": limits.get("max_excerpt_chars"),
            "arm_ok": check["ok"], "arm_reason": check["reason"],
            **evidence, **evidence_proxy(row, hits)}


def _as_ms(value):
    if isinstance(value, bool) or not _is_finite(value):
        return None
    return round(float(value), 2)


def failure_record(*, arm: str, row: dict, top_k: int, rep: int, error: str,
                   attempts: int, client_ms: float) -> dict:
    return {"kind": "request", "schema": SCHEMA, "arm": arm,
            "qid": row["id"], "category": row["category"], "tier": row["tier"],
            "top_k": int(top_k), "rep": int(rep),
            "query_chars": len(row["question"]), "query_sha": sha12(row["question"]),
            "status": "failed", "http_status": 0, "attempts": int(attempts),
            "error": str(error)[:400], "recorded_at": now_iso(),
            "client_ms": round(client_ms, 2), "arm_ok": None}


def retry_call(fn, *, attempts: int, sleep_seconds: float, log=print, sleep=time.sleep):
    """失败重跑：只重同一发，线性退避。返回 (value, used_attempts, last_error)。"""
    last = ""
    total = max(1, int(attempts))
    for step in range(total):
        try:
            return fn(), step + 1, ""
        except Exception as exc:  # noqa: BLE001 - 网络/服务怎么抛都要留下原题，不许静默丢题
            last = f"{type(exc).__name__}: {exc}"
            if step + 1 < total:
                log(f"    retry {step + 2}/{total} after {last[:160]}")
                sleep(sleep_seconds * (step + 1))
    return None, total, last


def _jsonl_lines(path: Path) -> list:
    if not Path(path).is_file():
        raise RuntimeError(f"读不到产物：{path}")
    out = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError as exc:
            raise RuntimeError(f"{path}:{number} 不是合法 JSON —— 产物被截断或有人在改它：{exc}") from exc
    return out


def read_run(path: Path) -> tuple:
    """一份 run 产物 -> (header, records)。缺 header 就是前置不满足，不猜。"""
    header, records = None, []
    for item in _jsonl_lines(Path(path)):
        if item.get("kind") == "header" and header is None:
            header = item
        elif item.get("kind") == "request":
            records.append(item)
    if header is None:
        raise RuntimeError(f"{path} 里没有 header 行：这份产物不是本件写的，或者被截断了")
    if header.get("schema") != SCHEMA:
        raise RuntimeError(f"{path} 的 schema={header.get('schema')!r}，本件只认 {SCHEMA!r}")
    return header, records


def done_keys(path: Path) -> set:
    """续跑用：只有 status=ok 的 (qid, top_k, rep) 算完成。失败题必须重跑，不许当已交。"""
    if not Path(path).is_file():
        return set()
    return {(item.get("qid"), _as_int(item.get("top_k")), _as_int(item.get("rep")),)
            for item in read_run(Path(path))[1] if item.get("status") == "ok"}

def collect(arm: str, questions: list, *, transport, top_ks: list, repeats: int, out_path: Path,
            resume: bool, attempts: int, retry_sleep: float, max_requests: int,
            gap_seconds: float, health_probe: bool, limits: dict, dry_run: bool,
            log=print, sleep=time.sleep) -> int:
    """一臂的采集。产物是 append-only JSONL + 逐行 flush/fsync：中断了接着跑（长跑件必读纪律）。"""
    planned = len(questions) * len(top_ks) * max(1, int(repeats))
    if dry_run:
        first = questions[0]
        request_id, trace_id = debug_request_ids(arm, first["id"], top_ks[0], 0)
        log(f"[dry-run] arm={arm} 开关声明={ARM_SWITCHES[arm]}")
        qsha = sha12("|".join(sorted(item["id"] for item in questions)))
        log(f"[dry-run] 题集 {len(questions)} 题 题号sha={qsha}")
        log(f"[dry-run] 档位 top_k={list(top_ks)} 重发={repeats} => 将发 {planned} 发 {ROUTE_DEBUG}")
        log(f"[dry-run] 每发另配 2 拍 {ROUTE_HEALTH}（--no-health-probe 可关，但臂身份就无从证实）")
        log("[dry-run] 预算闸 --max-requests={0}；样例载荷（零网络）：{1}".format(
            max_requests, json.dumps({"query": first["question"], "top_k": top_ks[0],
                                      "request_id": request_id, "trace_id": trace_id},
                                     ensure_ascii=False)))
        log("[dry-run] 未发任何请求，未打开任何 socket。")
        return EXIT_OK
    if planned > max_requests:
        log(f"[提示] 计划 {planned} 发 > --max-requests={max_requests}：触顶即停，用 --resume 续跑。")

    header, records = (None, [])
    if out_path.is_file():
        header, records = read_run(out_path)
        if header.get("arm") != arm:
            log(f"[前置不满足] {out_path} 的产物头写着 arm={header.get('arm')!r}，"
                f"不接受 --arm {arm} 往里续写（两臂混进一份文件就是假对照）")
            return EXIT_PRECONDITION
    if header is None:
        header = {"kind": "header", "schema": SCHEMA, "tool": TOOL, "arm": arm,
                  "switch_declared": ARM_SWITCHES[arm], "revision": git_revision(),
                  "base_url": transport.base_url, "username": transport.username,
                  "top_ks": list(top_ks), "repeats": int(repeats),
                  "fixture_rows": len(questions),
                  "questions_sha": sha12("|".join(sorted(f"{item['id']}::{item['question']}"
                                                         for item in questions))),
                  "limits": limits, "health_probe": bool(health_probe),
                  "started_at": now_iso()}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(header, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    completed = done_keys(out_path) if resume else set()
    if completed:
        log(f"[resume] {out_path.name} 已有 {len(completed)} 枚可用读数，只补缺")

    sent = failed = consecutive = 0
    try:
        transport.login()
        with out_path.open("a", encoding="utf-8", newline="\n") as handle:
            for row in questions:
                for top_k in top_ks:
                    for rep in range(max(1, int(repeats))):
                        key = (row["id"], int(top_k), int(rep))
                        if key in completed:
                            continue
                        if sent >= max_requests:
                            log(f"[预算闸] 已发 {sent} 发，触顶 --max-requests={max_requests}；"
                                f"续跑：collect --arm {arm} --out {out_path} --resume")
                            return EXIT_PARTIAL
                        if gap_seconds:
                            sleep(gap_seconds)
                        request_id, trace_id = debug_request_ids(arm, *key)
                        pre = transport.health() if health_probe else {}
                        started = time.perf_counter()
                        report, used, error = retry_call(
                            lambda: transport.debug(row["question"], top_k, request_id, trace_id),
                            attempts=attempts, sleep_seconds=retry_sleep, log=log, sleep=sleep)
                        client_ms = (time.perf_counter() - started) * 1000.0
                        post = transport.health() if health_probe else {}
                        sent += 1
                        if report is None:
                            record = failure_record(arm=arm, row=row, top_k=top_k, rep=rep,
                                                    error=error, attempts=used,
                                                    client_ms=client_ms)
                            failed += 1
                            consecutive += 1
                        else:
                            record = build_record(arm=arm, row=row, top_k=top_k, rep=rep,
                                                  report=report, pre=pre, post=post,
                                                  client_ms=client_ms, attempts=used,
                                                  limits=limits)
                            consecutive = 0
                        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                        log("  [{arm}] {qid:>10} k={k} r={rep} {status} legs={legs} "
                            "n={n} hot+{hot} dur={dur}ms".format(
                                arm=arm, qid=row["id"], k=top_k, rep=rep,
                                status=record["status"],
                                legs=",".join(record.get("semantic_legs_observed") or ["-"]),
                                n=len(record.get("hits") or []),
                                hot=(record.get("hot_delta") or {}).get("hits", 0),
                                dur=record.get("server_duration_ms")))
                        if record["status"] == "ok":
                            completed.add(key)
                        if consecutive >= 5:
                            log(f"[前置不满足] 连续 {consecutive} 发失败，当场停手：剩下的一发都没必要发。"
                                f"已落盘部分可 --resume 续跑：{out_path}")
                            return EXIT_PRECONDITION
    except KeyboardInterrupt:
        log(f"[中断] 已发 {sent} 发已落盘；续跑：collect --arm {arm} --out {out_path} --resume")
        return EXIT_INTERRUPTED
    except RuntimeError as exc:
        log(f"[前置不满足] {exc}")
        return EXIT_PRECONDITION
    except urllib.error.URLError as exc:
        log(f"[前置不满足] 服务不可达 {transport.base_url}：{exc}")
        return EXIT_PRECONDITION
    unverified = [item for item in read_run(out_path)[1]
                  if item.get("status") == "ok" and item.get("arm_ok") is False]
    if unverified:
        log(f"[臂身份未证实] {len(unverified)}/{sent} 发的答复方与 --arm {arm} 的声明不符"
            f"（例：{unverified[0].get('arm_reason')}）⇒ 这一臂不许进对照结论")
        return EXIT_ARM_UNVERIFIED
    log(f"[collect] arm={arm} 发 {sent} 失败 {failed}，产物：{out_path}")
    return EXIT_PARTIAL if failed else EXIT_OK

# ------------------------------------------------------------- compare（判据 ①②③ 的读数）
#
# 下面四枚函数的语义与 scripts/r59_recall_compare.py:370-465 逐字同值，键名也沿用那一份，
# 为的是 R59b 的 135 题旧读数能与本件新读数逐列对差；这里不重抄注释，只写差异。

def rank_map(ids: list) -> dict:
    return {vector_id: position + 1 for position, vector_id in enumerate(ids)}


def kendall_tau(left: list, right: list):
    """共有元素上的 Kendall tau（1 = 同序）。共有少于两枚不算，交回 None。"""
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
            if delta < 0:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return None if not total else round((concordant - discordant) / total, 4)


def first_difference(left: list, right: list):
    """第一处名次不同的 1 基名次；逐位相同才返回 None。"""
    for position in range(max(len(left), len(right))):
        a = left[position] if position < len(left) else None
        b = right[position] if position < len(right) else None
        if a != b:
            return position + 1
    return None


def compare_pair(base_ids: list, target_ids: list, *, k: int) -> dict:
    """一题两臂 -> 一行可机读读数。两臂都空时 jaccard 交回 None，绝不交回 1.0。"""
    base_set, target_set = set(base_ids), set(target_ids)
    union, shared = base_set | target_set, base_set & target_set
    base_rank, target_rank = rank_map(base_ids), rank_map(target_ids)
    shifts = [abs(base_rank[item] - target_rank[item]) for item in sorted(shared)]
    return {
        "k": int(k),
        "base_rows": len(base_ids), "target_rows": len(target_ids),
        "overlap": len(shared),
        "overlap_ratio": (round(len(shared) / k, 4) if k else None),
        "jaccard": (round(len(shared) / len(union), 4) if union else None),
        "same_set": bool(base_set == target_set),
        "same_order": bool(base_ids == target_ids),
        "both_empty": not base_ids and not target_ids,
        "first_diff_rank": first_difference(base_ids, target_ids),
        "mean_abs_rank_shift": (round(statistics.fmean(shifts), 4) if shifts else None),
        "max_abs_rank_shift": (max(shifts) if shifts else None),
        "kendall_tau": kendall_tau(base_ids, target_ids),
        "base_only_keys": sorted(base_set - target_set),
        "target_only_keys": sorted(target_set - base_set),
        "top1_base": (base_ids[0] if base_ids else None),
        "top1_target": (target_ids[0] if target_ids else None),
        "top1_changed": bool((base_ids[:1] != target_ids[:1])),
        "base_zero_rows": not base_ids, "target_zero_rows": not target_ids,
        "zero_rows_on_one_side": bool(bool(base_ids) != bool(target_ids)),
    }


def _index(records: list) -> dict:
    """(qid, top_k, rep) -> 该格读数。续跑/重发都落在这里，键相同即同一格。"""
    out = {}
    for item in records:
        out.setdefault((item.get("qid"), _as_int(item.get("top_k")),
                        _as_int(item.get("rep"))), []).append(item)
    return out


def _cells(records: list) -> dict:
    """(qid, top_k) -> 该题该档的**全部重发**读数。重发不是重复题，是噪声地板的样本。"""
    out = {}
    for item in records:
        out.setdefault((item.get("qid"), _as_int(item.get("top_k"))), []).append(item)
    return out


def _cell_durations(records: list) -> dict:
    return {key: sorted(item["server_duration_ms"] for item in recs
                        if item.get("server_duration_ms") is not None)
            for key, recs in _cells(records).items()}


def _median(values):
    # 同格多发的代表值取中位数：模型抖动是长尾的。
    return round(statistics.median(list(values)), 2) if values else None


def _paired_delta_ms(base_records: list, target_records: list) -> dict:
    """同题配对的服务端耗时差（重发取中位数）。拿不到两发就没资格进这张表。"""
    left = {key: _median(values) for key, values in _cell_durations(base_records).items()}
    right = {key: _median(values) for key, values in _cell_durations(target_records).items()}
    steps = [right[key] - left[key] for key in sorted(set(left) & set(right))
             if left[key] is not None and right[key] is not None]
    if not steps:
        return {"paired_questions": 0, "median_delta_ms": None, "p95_delta_ms": None}
    ordered = sorted(steps)
    return {"paired_questions": len(steps),
            "median_delta_ms": round(ordered[len(ordered) // 2], 2),
            "p95_delta_ms": round(ordered[min(len(ordered) - 1,
                                              int(math.ceil(0.95 * len(ordered)) - 1))], 2)}


def noise_floor_ms(records: list) -> dict:
    """同臂同题重发的组内散布：代价读数的小数点能不能信，全看这一格。"""
    spreads = []
    for values in _cell_durations(records).values():
        if len(values) >= 2:
            spreads.append(round(values[-1] - values[0], 2))
    if not spreads:
        return {"repeated_cells": 0, "noise_floor_ms_p95": None,
                "note": "没有 --repeats>=2，代价与噪声同量级时本件无法分辨"}
    ordered = sorted(spreads)
    return {"repeated_cells": len(ordered),
            "noise_floor_ms_p95": ordered[min(len(ordered) - 1,
                                              int(math.ceil(0.95 * len(ordered)) - 1))]}

def selectivity_screen(records: list, census: dict | None) -> dict:
    """谓词到底有没有"选择性"—— 没有它就别说 ③ 量过了（§9.3 ③ 的原话是要沙盒语料）。"""
    reasons = []
    shapes = {}
    scope_reasons = {}
    levels_seen = set()
    departments_seen = set()
    for record in records:
        scope_reasons[str(record.get("scope_reason") or "")] = \
            scope_reasons.get(str(record.get("scope_reason") or ""), 0) + 1
        parsed = parse_scope_filter(record.get("permission_filter"))
        shapes[parsed["shape"]] = shapes.get(parsed["shape"], 0) + 1
        if parsed["levels"] is not None:
            levels_seen.update(parsed["levels"])
        if parsed["departments"] is not None:
            departments_seen.update(parsed["departments"])
    for hit in [hit for record in records for hit in (record.get("hits") or [])]:
        if hit.get("classification") is not None:
            levels_seen.add(hit["classification"])
        departments_seen.add(str(hit.get("department") or ""))
    if set(scope_reasons) == {"administrator_scope"}:
        reasons.append("principal 走的是 administrator_scope（app/rag/filters.py 里它不带部门谓词）")
    admitted_departments = departments_seen & {item for item in departments_seen if item}
    if len(admitted_departments) < 2:
        reasons.append("命中里出现的非空 department 取值 < 2：" + repr(sorted(admitted_departments)))
    if len(levels_seen) < 2:
        reasons.append("命中里出现的 classification 取值 < 2：" + repr(sorted(levels_seen)))
    if census:
        distinct = {str(item) for item in (census.get("departments") or []) if str(item)}
        if len(distinct) < 2:
            reasons.append("语料普查里非空 department < 2 个取值（census.departments="
                           + repr(sorted(distinct)) + "）")
        if len(set(census.get("classifications") or [])) < 2:
            reasons.append("语料普查里 classification 只有 1 个取值")
    return {"selective": not reasons, "reasons": reasons, "scope_reasons": scope_reasons,
            "filter_shapes": shapes, "levels_in_play": sorted(levels_seen),
            "departments_in_play": sorted(departments_seen)}


def compare(runs: list, *, base_arm: str, census: dict | None = None,
            log=print) -> tuple:
    """多臂对差 -> (逐题配对行, 汇总)。退出码由 decide_exit 依汇总判定。

    runs = [(header, records), ...]；base_arm 是延迟差与名次差的参照臂。
    两臂同一格取**最高 rep** 那一发（重发是噪声地板的样本，不是第二道题）。
    """
    by_arm = {}
    for header, records in runs:
        arm = str(header.get("arm") or "")
        if arm in by_arm:
            raise RuntimeError(f"同一臂 {arm} 交进来两份产物：先决定哪一份算数")
        by_arm[arm] = (header, records)
    if base_arm not in by_arm:
        raise RuntimeError(f"--base {base_arm} 不在传入的产物里：{sorted(by_arm)}")
    if len(by_arm) < 2:
        raise RuntimeError("只有一臂不叫对照：至少要两臂才能出集合差")
    for arm in sorted(by_arm):
        _, records = by_arm[arm]
        ok = [item for item in records if item.get("status") == "ok"]
        if not ok:
            raise RuntimeError(f"臂 {arm} 没有一枚 status=ok 的读数，无从对照")
        unverified = [item for item in ok if item.get("arm_ok") is False]
        if unverified:
            raise RuntimeError(
                f"臂 {arm} 有 {len(unverified)}/{len(ok)} 枚读数的答复方与声明不符"
                f"（例：{unverified[0].get('arm_reason')}）—— 臂身份未证实，拒绝出对照")
    base_header, base_records = by_arm[base_arm]

    def chosen_by_cell(records: list) -> dict:
        return {key: max(recs, key=lambda item: (_as_int(item.get("rep")) or 0))
                for key, recs in _index([item for item in records
                                         if item.get("status") == "ok"]).items()}

    base_index = chosen_by_cell(base_records)
    rows = []
    for arm in sorted(by_arm):
        if arm == base_arm:
            continue
        header, records = by_arm[arm]
        target_index = chosen_by_cell(records)
        for key in sorted(set(base_index) & set(target_index)):
            qid, top_k, _rep = key
            left, right = base_index[key], target_index[key]
            if left.get("query_sha") != right.get("query_sha"):
                raise RuntimeError(f"{qid} 两臂题面指纹不一致（{left.get('query_sha')} != "
                                   f"{right.get('query_sha')}）：两臂量的不是同一道题")
            base_ids = [hit["key"] for hit in (left.get("hits") or []) if hit.get("key")]
            target_ids = [hit["key"] for hit in (right.get("hits") or []) if hit.get("key")]
            unnamed = (len(left.get("hits_unnamed") or []) + len(right.get("hits_unnamed") or []))
            pair = compare_pair(base_ids, target_ids, k=top_k or 0)
            leaks = (left.get("permission_leaks") or []) + (right.get("permission_leaks") or [])
            rows.append({
                "id": qid, "category": left.get("category", ""), "tier": left.get("tier", ""),
                "k": top_k, "rep": _rep, "base_arm": base_arm, "target_arm": arm,
                "query_sha": left.get("query_sha"),
                "base_ids": base_ids, "target_ids": target_ids,
                "unnamed_hits": unnamed,
                "identity_usable": unnamed == 0,
                "base_leg": ",".join(left.get("semantic_legs_observed") or []),
                "target_leg": ",".join(right.get("semantic_legs_observed") or []),
                "base_hot_hits": (left.get("hot_delta") or {}).get("hits", 0),
                "base_hot_misses": (left.get("hot_delta") or {}).get("misses", 0),
                "target_hot_hits": (right.get("hot_delta") or {}).get("hits", 0),
                "base_duration_ms": left.get("server_duration_ms"),
                "target_duration_ms": right.get("server_duration_ms"),
                "delta_ms": (None if left.get("server_duration_ms") is None
                             or right.get("server_duration_ms") is None else
                             round(right["server_duration_ms"] - left["server_duration_ms"], 2)),
                "scope_reason_base": left.get("scope_reason"),
                "scope_reason_target": right.get("scope_reason"),
                "shadow_verdict_base": left.get("shadow_verdict"),
                "shadow_verdict_target": right.get("shadow_verdict"),
                "permission_leak_rows": len(leaks),
                "permission_leak_detail": leaks[:5],
                "proxy_any_hit_base": left.get("proxy_any_hit"),
                "proxy_any_hit_target": right.get("proxy_any_hit"),
                "proxy_all_hit_base": left.get("proxy_all_hit"),
                "proxy_all_hit_target": right.get("proxy_all_hit"),
                "corpus_mutated": bool((left.get("invalidations_during_request") or 0)
                                       or (right.get("invalidations_during_request") or 0)),
                **pair,
            })
    return rows, summarize(rows, by_arm, base_arm, base_header, census=census, log=log)

def _quantiles(values: list) -> dict:
    if not values:
        return {"count": 0, "p50": None, "p95": None, "mean": None, "max": None}
    ordered = sorted(values)

    def at(fraction: float):
        index = min(len(ordered) - 1, max(0, int(math.ceil(fraction * len(ordered)) - 1)))
        return ordered[index]

    return {"count": len(ordered), "p50": at(0.50), "p95": at(0.95),
            "mean": round(statistics.fmean(ordered), 4), "max": ordered[-1]}


def summarize(rows: list, by_arm: dict, base_arm: str, base_header: dict, *,
              census: dict | None = None, log=print) -> dict:
    """汇总 = 判据逐格的"量到没量到"。🔴 这里每一格都必须能拒绝说"量到了"。"""
    usable = [row for row in rows if row.get("identity_usable")]
    unusable = [row for row in rows if not row.get("identity_usable")]
    both_empty = [row for row in usable if row.get("both_empty")]
    comparable = [row for row in usable if not row.get("both_empty")]
    jac = [row["jaccard"] for row in comparable if row.get("jaccard") is not None]
    shifts = [row["mean_abs_rank_shift"] for row in comparable
              if row.get("mean_abs_rank_shift") is not None]
    taus = [row["kendall_tau"] for row in comparable if row.get("kendall_tau") is not None]
    legs_by_arm = {}
    for arm in sorted(by_arm):
        _, records = by_arm[arm]
        ok = [item for item in records if item.get("status") == "ok"]
        tally = {}
        for item in ok:
            for leg in item.get("semantic_legs_observed") or []:
                tally[leg] = tally.get(leg, 0) + 1
        hot_served = [item for item in ok if LEG_HOT in (item.get("semantic_legs_observed") or [])]
        legs_by_arm[arm] = {
            "records_ok": len(ok),
            "records_failed": sum(1 for item in records if item.get("status") == "failed"),
            "legs": tally,
            "uniform_legs": sorted({",".join(item.get("semantic_legs_observed") or [])
                                    for item in ok}),
            "mixed_leg_records": sum(1 for item in ok if item.get("mixed_semantic_leg")),
            "arm_ok_all": all(item.get("arm_ok") for item in ok),
            "hot_served_records": len(hot_served),
            "hot_served_share": (round(len(hot_served) / len(ok), 4) if ok else None),
            "hot_enabled": (ok[0].get("hot_enabled") if ok else None),
            "hot_resident_chunks": (ok[0].get("hot_resident_chunks") if ok else None),
            "duration_ms": _quantiles([item.get("server_duration_ms") for item in ok
                                       if item.get("server_duration_ms") is not None]),
            "noise_floor": noise_floor_ms(ok),
            "keyword_fallback_records": sum(1 for item in ok if item.get("keyword_fallbacks")),
            "leak_records": sum(1 for item in ok if (item.get("permission_leaks") or [])),
            "leak_rows": sum(len(item.get("permission_leaks") or []) for item in ok),
            "shadow_unknown_records": sum(1 for item in ok
                                          if item.get("shadow_verdict") == "unknown"),
            "scope_reasons": sorted({str(item.get("scope_reason") or "") for item in ok}),
        }
    deltas = {}
    for arm in sorted(by_arm):
        if arm == base_arm:
            continue
        header, records = by_arm[arm]
        base_records = by_arm[base_arm][1]
        table = _paired_delta_ms(base_records, [item for item in records
                                                if item.get("status") == "ok"])
        noise = legs_by_arm[arm]["noise_floor"]["noise_floor_ms_p95"]
        floor = max((noise or 0.0), (legs_by_arm[base_arm]["noise_floor"]["noise_floor_ms_p95"]
                                     or 0.0))
        verdict = "NOT_RESOLVED"
        if table["median_delta_ms"] is not None:
            verdict = ("RESOLVED" if floor and abs(table["median_delta_ms"]) > floor
                       else ("NOT_RESOLVED" if floor else "NO_NOISE_FLOOR"))
        deltas[arm] = dict(table)
        deltas[arm]["noise_floor_ms_p95"] = floor or None
        deltas[arm]["verdict"] = verdict
    yield_cost = {}
    if set(ARMS) <= set(by_arm):
        durations = {arm: _cell_durations([item for item in by_arm[arm][1]
                                           if item.get("status") == "ok"])
                     for arm in ARMS}

        def paired(target: str, reference: str):
            left = durations[reference]
            right = durations[target]
            steps = [statistics.median(right[key]) - statistics.median(left[key])
                     for key in sorted(set(left) & set(right)) if left[key] and right[key]]
            return round(statistics.median(steps), 2) if steps else None

        hot_gain = paired("chroma-cold", "chroma-hot")
        switch_cost = paired("pgvector", "chroma-cold")
        net = paired("pgvector", "chroma-hot")
        floors = [legs_by_arm[arm]["noise_floor"]["noise_floor_ms_p95"] or 0.0
                  for arm in sorted(legs_by_arm)]
        floor = max(floors)
        yield_cost = {
            "formula": "hot_gain = paired(chroma-cold - chroma-hot)；"
                       "switch_cost = paired(pgvector - chroma-cold)；"
                       "net_yield_cost = paired(pgvector - chroma-hot) = switch_cost + hot_gain",
            "hot_gain_ms": hot_gain, "switch_cost_ms": switch_cost, "net_yield_cost_ms": net,
            "noise_floor_ms_p95": floor or None,
            "verdict": ("NOT_RESOLVED" if net is None
                        else ("RESOLVED" if floor and abs(net) > floor
                              else ("NOISE_FLOOR_MISSING" if not floor else "NOT_RESOLVED"))),
            "note": "三项都要读：净代价 = 切读裸代价 - 热集收益；|净代价| <= 噪声地板就不算量出来"}
        if net is not None and hot_gain is not None and switch_cost is not None:
            yield_cost["identity_error_ms"] = round(net - (switch_cost + hot_gain), 2)
    screen = selectivity_screen([rec for arm in sorted(by_arm)
                                 for rec in by_arm[arm][1] if rec.get("status") == "ok"], census)
    differing = [row for row in comparable if not row.get("same_set")]
    cells = {
        "9.3-1_service_end_to_end": {
            "status": ("SUPPLIED" if len(rows) else "NOT_SUPPLIED"),
            "reads": len(rows), "arms": sorted(by_arm),
            "note": "服务入口逐题对照读数已在位；库层那格（R59b）与这格各归各，不许互相翻绿"},
        "9.3-2_hot_yield_cost": {
            "status": ("SUPPLIED" if len(by_arm) >= 3 else
                       ("PARTIAL" if len(by_arm) == 2 else "NOT_SUPPLIED")),
            "arms_present": sorted(by_arm),
            "arms_required": sorted(ARMS),
            "paired_latency_ms": deltas, "cost_decomposition": yield_cost or None,
            "note": "三臂缺一即只能给两两差；|代价|<=噪声地板判 NOT_RESOLVED"},
        "9.3-3_selective_permission": {
            "status": ("SUPPLIED" if screen["selective"] else "NOT_MEASURED"),
            "screen": screen,
            "over_permission_rows": sum(arm["leak_rows"] for arm in legs_by_arm.values()),
            "note": "谓词没有可选性就整格 NOT_MEASURED：这是语料的性质，不是入口跑没跑过"},
    }
    summary = {
        "tool": TOOL, "schema": SCHEMA, "generated_at": now_iso(),
        "base_arm": base_arm, "arms": sorted(by_arm),
        "revision_base": base_header.get("revision"),
        "questions_sha_per_arm": {arm: by_arm[arm][0].get("questions_sha")
                                  for arm in sorted(by_arm)},
        "pairs": len(rows), "pairs_identity_usable": len(usable),
        "pairs_identity_unusable": [{"id": row["id"], "k": row["k"],
                                     "target_arm": row["target_arm"],
                                     "unnamed_hits": row["unnamed_hits"]} for row in unusable],
        "same_set": sum(1 for row in comparable if row.get("same_set")),
        "differing_set": len(differing),
        "differing_ids": [row["id"] for row in differing],
        "same_order": sum(1 for row in comparable if row.get("same_order")),
        "both_empty": len(both_empty), "both_empty_ids": [row["id"] for row in both_empty],
        "zero_rows_on_one_side": sum(1 for row in comparable if row.get("zero_rows_on_one_side")),
        "zero_rows_on_one_side_ids": [row["id"] for row in comparable
                                      if row.get("zero_rows_on_one_side")],
        "mean_jaccard": (round(statistics.fmean(jac), 4) if jac else None),
        "median_jaccard": (round(statistics.median(jac), 4) if jac else None),
        "mean_abs_rank_shift": (round(statistics.fmean(shifts), 4) if shifts else None),
        "max_abs_rank_shift": (max(shifts) if shifts else None),
        "mean_kendall_tau": (round(statistics.fmean(taus), 4) if taus else None),
        "top1_changed": sum(1 for row in comparable if row.get("top1_changed")),
        "corpus_mutated_rows": sum(1 for row in rows if row.get("corpus_mutated")),
        "proxy_any_hit_base": sum(1 for row in usable if row.get("proxy_any_hit_base")),
        "proxy_any_hit_target": sum(1 for row in usable if row.get("proxy_any_hit_target")),
        "proxy_note": "摘录被服务端截到 MAX_EXCERPT_CHARS，代理只会少报；真判分归 run_quality_evaluation",
        "per_arm": legs_by_arm, "paired_latency_ms": deltas,
        "hot_yield": yield_cost or None, "selectivity_screen": screen, "cells": cells,
    }
    summary["headline_pass"] = bool(rows) and not differing and not both_empty
    summary["must_judge_in_window"] = [
        "两侧一致率不等于答案质量：本件不生成答案，判分仍归评测腿",
        "corpus_mutated_rows > 0 时这一窗的读数不可比（语料在测量期间被写过）",
        "9.3-3 只有在沙盒语料 + 业主批准的 DDL/DML 落地后才可能变 SUPPLIED",
    ]
    log("[compare] 题对 {0}（可比 {1}，双空 {2}，身份不可用 {3}）不一致 {4} 臂 {5}".format(
        len(rows), len(comparable), len(both_empty), len(unusable), len(differing), sorted(by_arm)))
    return summary


def decide_exit(rows: list, summary: dict) -> int:
    if not rows:
        return EXIT_PRECONDITION
    if summary.get("differing_set"):
        return EXIT_DIFFERS
    return EXIT_OK

def read_arm(path: Path) -> tuple:
    """读一臂产物，并把来源路径写进 header（读数必须能追到它是哪个文件）。"""
    header, records = read_run(Path(path))
    if header.get("arm") not in ARMS:
        raise RuntimeError(f"{path} 的臂标签 {header.get('arm')!r} 不认识：{sorted(ARMS)}")
    return dict(header, source_path=str(path)), records


def write_products(rows: list, summary: dict, *, jsonl: Path | None, csv_path: Path | None,
                   md: Path | None, json_path: Path | None) -> None:
    """三路写表（判据 ④ 的第三路）：JSONL 逐题、CSV 给人排序、JSON 给机读汇总。"""
    if jsonl:
        Path(jsonl).parent.mkdir(parents=True, exist_ok=True)
        with Path(jsonl).open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"kind": "summary", "schema": SCHEMA, **summary},
                                    ensure_ascii=False) + "\n")
            for row in rows:
                handle.write(json.dumps(dict(row, kind="pair"), ensure_ascii=False) + "\n")
    columns = PAIR_COLUMNS
    if csv_path:
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(csv_path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore",
                                    lineterminator="\r\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: _cell(row.get(name)) for name in columns})
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                   encoding="utf-8", newline="\n")
    if md:
        Path(md).parent.mkdir(parents=True, exist_ok=True)
        Path(md).write_text(render_markdown(rows, summary), encoding="utf-8", newline="\n")


def _cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return value


#: CSV 列序：先身份、再集合/名次、再延迟、最后权限。红要落在被点名的那一列（教训 #46）。
PAIR_COLUMNS = [
    "id", "category", "tier", "k", "rep", "base_arm", "target_arm",
    "identity_usable", "unnamed_hits", "same_set", "same_order", "both_empty",
    "jaccard", "overlap", "overlap_ratio", "first_diff_rank",
    "mean_abs_rank_shift", "max_abs_rank_shift", "kendall_tau", "top1_changed",
    "base_zero_rows", "target_zero_rows", "zero_rows_on_one_side",
    "base_rows", "target_rows", "base_duration_ms", "target_duration_ms", "delta_ms",
    "base_leg", "target_leg", "base_hot_hits", "target_hot_hits",
    "scope_reason_base", "scope_reason_target", "shadow_verdict_base",
    "shadow_verdict_target", "permission_leak_rows",
    "proxy_any_hit_base", "proxy_any_hit_target", "proxy_all_hit_base",
    "proxy_all_hit_target", "corpus_mutated", "base_only_keys", "target_only_keys",
    "base_ids", "target_ids",
]


def render_markdown(rows: list, summary: dict) -> str:
    lines = [f"# R59c 服务内端到端召回对照（{summary['generated_at']}）", ""]
    lines += [f"- 臂：{', '.join(summary['arms'])}（base = `{summary['base_arm']}`）",
              f"- 题对 {summary['pairs']}：一致 {summary['same_set']} / 不一致 "
              f"{summary['differing_set']} / 双空 {summary['both_empty']} / 身份不可用 "
              f"{summary['pairs_identity_unusable']}",
              f"- mean_jaccard={summary['mean_jaccard']} median_jaccard={summary['median_jaccard']} "
              f"mean|Δrank|={summary['mean_abs_rank_shift']} "
              f"mean_kendall_tau={summary['mean_kendall_tau']}",
              f"- headline_pass={summary['headline_pass']}（🔴 它只对『集合是否逐题相等』负责，"
              f"不对答案质量负责）", ""]
    lines += ["## §9.3 逐格状态", "", "| 格 | 状态 | 关键读数 |", "|---|---|---|"]
    for cell_id in sorted(summary["cells"]):
        cell = summary["cells"][cell_id]
        lines.append(f"| `{cell_id}` | **{cell['status']}** | "
                     f"{_cell({k: v for k, v in cell.items() if k != 'note'})[:400]} |")
    lines += ["", "## 每臂腿凭证（谁答的这一问）", "",
              "| 臂 | ok | 答复方计数 | hot 服务占比 | dur p50/p95 (ms) | 噪声地板 |",
              "|---|---|---|---|---|---|"]
    for arm, block in sorted(summary["per_arm"].items()):
        duration = block["duration_ms"]
        lines.append("| {0} | {1} | {2} | {3} | {4}/{5} | {6} |".format(
            arm, block["records_ok"], _cell(block["legs"]),
            block["hot_served_share"], duration["p50"], duration["p95"],
            block["noise_floor"]["noise_floor_ms_p95"]))
    yield_block = summary.get("hot_yield") or {}
    lines += ["", "## ② 热集让路代价（三臂分解）", ""]
    if yield_block:
        lines += ["- 公式：`{0}`".format(yield_block.get("formula", "")),
                  "- hot_gain_ms = {0}（热集原本省下的）".format(yield_block.get("hot_gain_ms")),
                  "- switch_cost_ms = {0}（只换引擎的裸代价）".format(yield_block.get("switch_cost_ms")),
                  "- net_yield_cost_ms = {1}（净让路代价，identity_error={2} ms）".format(
                      "", yield_block.get("net_yield_cost_ms"),
                      yield_block.get("identity_error_ms")),
                  "- 噪声地板 noise_floor_ms_p95 = {0} ⇒ verdict = **{1}**".format(
                      yield_block.get("noise_floor_ms_p95"), yield_block.get("verdict")),
                  "- " + str(yield_block.get("note", ""))]
    else:
        lines += ["- 三臂不齐（需要 chroma-hot + chroma-cold + pgvector），这一格只给两两差"]
    lines += ["", "## 配对延迟差（相对 base）", "",
              "| target | paired | median Δms | p95 Δms | 噪声地板 | verdict |",
              "|---|---|---|---|---|---|"]
    for arm, block in sorted(summary["paired_latency_ms"].items()):
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            arm, block["paired_questions"], block["median_delta_ms"], block["p95_delta_ms"],
            block["noise_floor_ms_p95"], block["verdict"]))
    lines += ["", "## 不一致题清单（逐题明细在 JSONL/CSV）", ""]
    for row in [item for item in rows if not item.get("same_set")][:60]:
        lines.append("- `{id}` k={k} jaccard={jaccard} Δrank_max={max_abs_rank_shift} "
                     "base_only={base_only_keys} target_only={target_only_keys}".format(**row))
    if summary["both_empty_ids"]:
        lines += ["", "🔴 双空题（两侧都交 0 行 —— 这一格**不计入一致**，见作废理由 2）：",
                  "", ", ".join(f"`{item}`" for item in summary["both_empty_ids"])]
    if summary.get("corpus_mutated_rows"):
        lines += ["", f"🔴 测量期间语料被写过的题对：{summary['corpus_mutated_rows']} 枚 ⇒ 这些读数不可比。"]
    lines += ["", "## 本窗必须现场判读的点", ""] + [f"- {item}" for item in summary["must_judge_in_window"]]
    return "\n".join(lines) + "\n"

# ------------------------------------------------------------------- census（③ 的前置取证）

def census_from_catalog(catalog: dict) -> dict:
    """把 GET /api/v1/documents/catalog 的可见行折成"语料到底有没有可选性"一张表。

    🔴 这是**判据 ③ 的前置取证**，不是判据 ③ 本身：它只回答"能不能量"，不回答"量出来多少"。
    现库（classification 全 1、department 全 ""）跑出来就是 selective=False，于是本件把 ③ 判成
    NOT_MEASURED 并指名原因 —— 这正是上一格 §9.3 ③ 的原话，只是今天它有机器读数背书。
    """
    rows = [item for item in (catalog.get("documents") or []) if isinstance(item, dict)]
    departments = {}
    classifications = {}
    for row in rows:
        department = str(row.get("department") or "")
        level = _as_int(row.get("classification"))
        departments[department] = departments.get(department, 0) + 1
        key = "" if level is None else str(level)
        classifications[key] = classifications.get(key, 0) + 1
    non_empty = sorted(item for item in departments if item)
    levels = sorted(int(item) for item in classifications if item.strip("-").isdigit())
    out = {"documents_visible": len(rows),
           "departments": sorted(departments), "department_counts": departments,
           "classifications": levels, "classification_counts": classifications,
           "restricted": catalog.get("restricted"),
           "selective_department": len(non_empty) >= 2,
           "selective_classification": len(levels) >= 2}
    out["verdict"] = ("CORPUS_IS_SELECTIVE"
                      if out["selective_department"] and out["selective_classification"]
                      else "CORPUS_HAS_NO_SELECTIVITY")
    out["meaning"] = ("语料可以拿来量选择性权限过滤" if out["verdict"] == "CORPUS_IS_SELECTIVE"
                      else "语料只有一种取值：谓词要么全命中要么全不命中，③ 量不到（需沙盒语料，"
                           "见 scripts/r59c_sandbox_corpus.py 与 docs/testing/r59c-method-2026-09-25.md）")
    return out


def census(transport, out_path: Path | None, *, dry_run: bool, log=print) -> int:
    if dry_run:
        log(f"[dry-run] 将发 GET {ROUTE_CATALOG} 一发（零模型、零写库），不打开 socket。")
        return EXIT_OK
    try:
        transport.login()
        payload = transport.catalog()
    except Exception as exc:  # noqa: BLE001
        log(f"[前置不满足] 普查失败：{type(exc).__name__}: {exc}")
        return EXIT_PRECONDITION
    report = census_from_catalog(payload)
    log(json.dumps(report, ensure_ascii=False, indent=2))
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(dict(report, tool=TOOL, generated_at=now_iso()),
                                             ensure_ascii=False, indent=2),
                                  encoding="utf-8", newline="\n")
        log(f"[census] 产物：{out_path}")
    return EXIT_OK if report["verdict"] == "CORPUS_IS_SELECTIVE" else EXIT_DIFFERS


# --------------------------------------------------------------- 出站闸门（零网络自证）

_REAL_SOCKET = __import__("socket").socket
_REAL_ATTRS = {}
_BLOCKED = []


def install_offline_guard() -> None:
    """把出站路径换成会抛的桩：dry-run 与 selfcheck 用它自证"这一遍一发都没发"。"""
    import socket

    class _BlockedSocket(_REAL_SOCKET):
        def connect(self, address, *args, **kwargs):
            _BLOCKED.append(repr(address))
            raise AssertionError(f"本件在离线模式被禁止出站：{address!r}")

        def connect_ex(self, address, *args, **kwargs):
            return self.connect(address)

    socket.socket = _BlockedSocket
    _REAL_ATTRS["socket"] = _REAL_SOCKET
    for name in ("create_connection", "getaddrinfo", "gethostbyname"):
        original = getattr(socket, name)
        _REAL_ATTRS.setdefault(name, original)

        def blocked(*args, _original=original, **kwargs):
            _BLOCKED.append(repr(args[:2]))
            raise AssertionError(f"本件在离线模式被禁止出站：{args[:2]!r}")
        setattr(socket, name, blocked)


def remove_offline_guard() -> None:
    """摘桩：逐路还原。留着半截桩会让下一次真跑分在看不见的地方炸。"""
    import socket
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
        if name in _REAL_ATTRS:
            setattr(socket, name, _REAL_ATTRS.pop(name))

# ------------------------------------------------------- 假服务与离线自校（判据 ④ 全路）

class SyntheticService:
    """一台只够量具自校用的假服务：确定性、零网络、零模型，形状逐字段照抄真响应。

    字段来源（逐条对得上的抄本，不是想象）：results 的键来自 app/rag/debug.py:_debug_result，
    外层键与 bounds/limits 来自 app/api/v1/observability.py:481-565，
    search_shape / hot_index 两块来自 app/common/monitoring.py:build_health_snapshot。
    数字一律被"服务端过成 float"（_bounded_value），所以 chunk_index/classification 在这里
    就是浮点 —— 解析那一路要是不归一，P1 立刻红。
    """

    def __init__(self, *, arm_leg=LEG_CHROMA, hot_enabled=False, departments=("",),
                 classifications=(1,), leak_on=(), swap_on=(), empty_on=(),
                 duration_base=4100.0, duration_jitter=0.0):
        self.arm_leg = arm_leg
        self.hot_enabled = hot_enabled
        self.departments = list(departments)
        self.classifications = list(classifications)
        self.leak_on = set(leak_on)
        self.swap_on = set(swap_on)
        self.empty_on = set(empty_on)
        self.duration_base = float(duration_base)
        self.duration_jitter = float(duration_jitter)
        self.legs = {}
        self.hot_hits = 0
        self.hot_misses = 0
        self.invalidations = 0
        self.token = "fake-token"
        self.username = "selfcheck"
        self.base_url = "http://selfcheck.invalid"
        self.login_calls = 0
        self.debug_calls = 0

    # -- Transport 的那四条 ----
    def login(self):
        self.login_calls += 1
        return self.token

    def catalog(self):
        rows = []
        for level in self.classifications:
            for department in self.departments:
                for ordinal in range(3):
                    rows.append({"filename": "doc-{0}-{1}-{2}.txt".format(
                        level, department or "nodept", ordinal),
                        "classification": level, "department": department})
        return {"documents": rows}

    def health(self):
        return {"status": "ok", "problems": [],
                "search_shape": {"last": None, "totals": {}, "answered_by": dict(self.legs)},
                "hot_index": {"enabled": self.hot_enabled, "hits": self.hot_hits,
                              "misses": self.hot_misses, "invalidations": self.invalidations,
                              "resident_chunks": (1008 if self.hot_enabled else 0),
                              "roster_fresh": self.hot_enabled, "max_chunks": 20000,
                              "last_bypass_reason": ("" if self.hot_enabled else
                                                     "hot_index_read_backend_switched"
                                                     if self.arm_leg == LEG_PGVECTOR
                                                     else "hot_index_disabled")}}

    def debug(self, query, top_k, request_id, trace_id):
        self.debug_calls += 1
        marker = sha12(query)
        seed = int(hashlib.sha256(query.encode("utf-8")).hexdigest()[:6], 16)
        empty = query in self.empty_on or marker in self.empty_on
        count = 0 if empty else max(1, min(int(top_k), 3 + seed % 3))
        hits = []
        for position in range(count):
            index = (seed + position * 7 + (1 if query in self.swap_on else 0)) % 1008
            department = self.departments[(seed + position) % len(self.departments)]
            classification = self.classifications[(seed + position) % len(self.classifications)]
            if query in self.leak_on and position == 0:
                classification = max(self.classifications) + 5
                department = "\u8d8a\u6743\u90e8\u95e8"
            hits.append({"source": f"doc-{(seed + position) % 40}.txt",
                         "chunk_index": float(index),
                         "classification": float(classification),
                         "department": department,
                         "score": round(1.0 - position * 0.1, 4),
                         "excerpt": query[:24] + " 的摘录",
                         "permission_checked": True})
        self.legs[self.arm_leg] = self.legs.get(self.arm_leg, 0) + 1
        if self.hot_enabled:
            self.hot_hits += 1
        else:
            self.hot_misses += 1
        # 抖动同时取决于题面与"第几发"：真机上重发就是会抖，假服务不许把它抹平
        jitter = (((seed + 13 * self.debug_calls) % 7) - 3) * self.duration_jitter
        return {"index_version_id": "", "strategy_version": "",
                "permission_filter": ({"$and": [{"classification": {"$in": [float(level) for level
                                                                          in self.classifications]}}]}
                                      if len(self.departments) == 1 and not self.departments[0]
                                      else {"$and": [
                                          {"classification": {"$in": [float(level) for level
                                                                     in self.classifications]}},
                                          {"department": {"$in": [self.departments[0]]}}]}),
                "scope_reason": ("administrator_scope"
                                 if len(self.departments) == 1 and not self.departments[0]
                                 else "department_scope"),
                "rewrites": [query, query + "?"] if seed % 2 else [query],
                "stages": [{"name": "permission_filter", "candidate_count": float(count)},
                           {"name": "reranked", "candidate_count": float(count)}],
                "results": hits, "duration_ms": round(self.duration_base + jitter, 2),
                "trace_id": trace_id, "request_id": request_id,
                "replay_path": "/api/v1/traces/" + trace_id,
                "bounds": {"rewrites_total": 1.0, "rewrites_returned": 1.0,
                           "results_total": float(count), "results_returned": float(count),
                           "excerpt_max_chars": 240.0, "string_max_chars": 2000.0,
                           "truncated": False},
                "limits": {"default_top_k": 5, "max_top_k": 20, "requested_top_k": float(top_k),
                           "applied_top_k": float(top_k), "clamped": False}}

def silent(*args, **kwargs):
    return None


def selfcheck_questions() -> list:
    """自校题集：真读 105 题题集的**前 8 题**（只读），拿真题面做形状，不另编一套题。"""
    try:
        rows = load_questions(REPO_ROOT / DEFAULT_FIXTURE, limit=8)
        return rows, "fixture:" + str(DEFAULT_FIXTURE)
    except Exception as exc:  # noqa: BLE001 - 自校不许被题集闸拖住，但必须如实标注来源
        rows = [{"id": f"synthetic-{index:02d}", "question": f"自校问题 {index} 的口径是什么？",
                 "category": "selfcheck", "tier": "问答",
                 "must_contain": [f"口径{index}"]} for index in range(1, 9)]
        return rows, "synthetic:" + type(exc).__name__


def silent(*args, **kwargs):
    return None


def selfcheck_questions() -> tuple:
    """自校题集：只读真评测集的前 8 题（判据：题目只读引用）；读不动就退成合成题并如实标注。"""
    try:
        return (load_questions(REPO_ROOT / DEFAULT_FIXTURE, limit=8),
                "fixture:" + str(DEFAULT_FIXTURE))
    except Exception as exc:  # noqa: BLE001 - 自校不许被题集闸拖死，但来源必须可辨
        rows = [{"id": "synthetic-{0:02d}".format(index),
                 "question": "自校问题 {0} 的口径是什么？".format(index),
                 "category": "selfcheck", "tier": "问答",
                 "must_contain": ["口径{0}".format(index)]} for index in range(1, 9)]
        return rows, "synthetic:" + type(exc).__name__


def _collect_arm(arm: str, service, path: Path, questions: list, limits: dict, *,
                 repeats: int = 1, top_k: int = 5) -> int:
    return collect(arm, questions, transport=service, top_ks=[top_k], repeats=repeats,
                   out_path=Path(path), resume=False, attempts=2, retry_sleep=0.0,
                   max_requests=10_000, gap_seconds=0.0, health_probe=True, limits=limits,
                   dry_run=False, log=silent, sleep=silent)


def _rewrite_hits(path: Path, qid: str, mutate) -> int:
    """就地改一臂产物里某一题的命中集合（反证钉用）。返回被改的发数。"""
    header, records = read_run(Path(path))
    touched = 0
    lines = [json.dumps(header, ensure_ascii=False)]
    for record in records:
        if record.get("qid") == qid and record.get("status") == "ok":
            record = dict(record)
            record["hits"] = mutate(list(record.get("hits") or []))
            touched += 1
        lines.append(json.dumps(record, ensure_ascii=False))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return touched


def _pin(pins: list, name: str, ok: bool, detail: str = "") -> bool:
    pins.append({"pin": ("PASS " if ok else "FAIL ") + name, "ok": bool(ok), "detail": detail})
    return ok


def run_selfcheck(*, verbose: bool = False, workdir: Path | None = None) -> int:
    """离线自校：解析 / 比集合 / 写表三路真跑，再逐条落反证钉（教训 #46）。

    纪律：先证"干净基线不红"，再逐条**只**抽错一格，要求红恰好落在那一格的列上。
    反过来说：任何一枚钉如果全局变红，那它就是废钉（它没有指着那一格）。
    """
    install_offline_guard()
    pins: list = []
    source = ""
    try:
        limits = server_limits()
        questions, source = selfcheck_questions()
        top_k = int(limits["default_top_k"])
        root = Path(workdir) if workdir else Path(os.getenv("TEMP") or "/tmp") / "r59c-selfcheck"
        root.mkdir(parents=True, exist_ok=True)
        for stale in sorted(root.glob("*.jsonl")) + sorted(root.glob("*.csv")) \
                + sorted(root.glob("*.json")) + sorted(root.glob("*.md")):
            stale.unlink()

        services = {
            "chroma-hot": SyntheticService(arm_leg=LEG_CHROMA, hot_enabled=True,
                                           duration_base=4100.0, duration_jitter=3.0),
            "chroma-cold": SyntheticService(arm_leg=LEG_CHROMA, duration_base=4300.0,
                                            duration_jitter=3.0),
            "pgvector": SyntheticService(arm_leg=LEG_PGVECTOR, duration_base=4200.0,
                                         duration_jitter=3.0),
        }
        files = {}
        codes = {}
        for arm, service in services.items():
            files[arm] = root / ("clean_" + arm + ".jsonl")
            codes[arm] = _collect_arm(arm, service, files[arm], questions, limits,
                                      repeats=(3 if arm == "chroma-hot" else 1), top_k=top_k)
        _pin(pins, "P0 三臂 collect 正常退出（干净基线不许是红的）",
             all(value == EXIT_OK for value in codes.values()),
             "codes=" + json.dumps(codes))
        _pin(pins, "P10 零网络：假服务没开过一次 socket", not _BLOCKED,
             "blocked_attempts=" + json.dumps(_BLOCKED[:3]))

        header, records = read_run(files["chroma-hot"])
        sample = max(records, key=lambda item: len(item.get("hits") or []))
        _pin(pins, "P1 解析路：服务端 float 形状 -> int 且 key 同源",
             all(isinstance(hit["chunk_index"], int) for hit in sample["hits"])
             and all(hit["key"] == hit["source"] + "#" + str(hit["chunk_index"])
                     for hit in sample["hits"]),
             sample["qid"] + " hits=" + str(len(sample["hits"])))
        _pin(pins, "P1b 解析路：腿凭证按 answered_by 增量归一",
             sample["legs_delta_semantic"] == {LEG_CHROMA: 1} and sample["arm_ok"] is True,
             json.dumps({"legs": sample["legs_delta_semantic"],
                         "hot": sample["hot_delta"], "bypass": sample["hot_last_bypass_reason"]}))

        manual = compare_pair(["a#1", "a#2", "a#3"], ["a#2", "a#3", "b#9"], k=5)
        _pin(pins, "P2 集合/名次路：手算五行逐值相等",
             manual["jaccard"] == 0.5 and manual["overlap"] == 2 and manual["same_set"] is False
             and manual["first_diff_rank"] == 1 and manual["max_abs_rank_shift"] == 1
             and manual["kendall_tau"] == 1.0
             and manual["base_only_keys"] == ["a#1"] and manual["target_only_keys"] == ["b#9"],
             json.dumps(manual))
        empty = compare_pair([], [], k=5)
        _pin(pins, "P9 空集不等于一致：双空题 jaccard=None 且单独计数",
             empty["jaccard"] is None and empty["both_empty"] is True, json.dumps(empty))

        clean_rows, clean_summary = compare_arm_files(
            [files[arm] for arm in ("chroma-hot", "chroma-cold", "pgvector")],
            base_arm="chroma-hot", census=census_from_catalog(services["chroma-hot"].catalog()))
        _pin(pins, "P3 写表路：三臂两两配对且干净基线零不一致",
             clean_summary["pairs"] == 16 and clean_summary["differing_set"] == 0
             and clean_summary["both_empty"] == 0,
             "pairs={0} differing={1} both_empty={2}".format(
                 clean_summary["pairs"], clean_summary["differing_set"],
                 clean_summary["both_empty"]))
        _pin(pins, "P8 噪声地板：--repeats>=2 才给得出地板",
             clean_summary["per_arm"]["chroma-hot"]["noise_floor"]["noise_floor_ms_p95"] not in
             (None, 0) and clean_summary["per_arm"]["pgvector"]["noise_floor"][
                 "noise_floor_ms_p95"] is None,
             json.dumps({arm: block["noise_floor"]
                         for arm, block in clean_summary["per_arm"].items()}))
        yield_block = clean_summary["hot_yield"]
        hot_gain = yield_block["hot_gain_ms"]
        net = yield_block["net_yield_cost_ms"]
        switch_cost = yield_block["switch_cost_ms"]
        # 假服务里注进去的真值是 hot_gain=+200 / switch_cost=-100 / net=+100（每发再叠 <=9ms 抖动）。
        # 这一枚钉同时问两件事：分解能不能**取回**注进去的代价，以及三项相加对不对得上（恒等式）。
        tolerance = 25.0
        _pin(pins, "P11 三臂分解取回注入真值 + 恒等式 net = switch_cost + hot_gain",
             abs(hot_gain - 200.0) <= tolerance and abs(switch_cost + 100.0) <= tolerance
             and abs(net - 100.0) <= tolerance
             and abs(yield_block["identity_error_ms"]) <= tolerance,
             json.dumps({key: yield_block[key] for key in
                         ("hot_gain_ms", "switch_cost_ms", "net_yield_cost_ms",
                          "identity_error_ms", "noise_floor_ms_p95", "verdict")}))
        # ---- P4 臂身份：声明 pgvector 而服务用 chroma 答 ⇒ 整臂拒收 ------------------
        liar_service = SyntheticService(arm_leg=LEG_CHROMA, duration_base=4150.0)
        liar_path = root / "liar_pgvector.jsonl"
        liar_code = _collect_arm("pgvector", liar_service, liar_path, questions, limits)
        _pin(pins, "P4 臂身份：答腿与声明不符即整臂作废（退出码 3）",
             liar_code == EXIT_ARM_UNVERIFIED,
             "exit={0} 例因={1}".format(liar_code, read_run(liar_path)[1][0].get("arm_reason")))
        refused = ""
        try:
            compare_arm_files([liar_path, files["chroma-cold"]], base_arm="chroma-cold")
        except RuntimeError as exc:
            refused = str(exc)
        _pin(pins, "P4b 臂身份未证实的产物不许进对照（拒绝出数，不是降级出数）",
             "身份未证实" in refused, refused[:160])

        # ---- P5 反证钉：只把一题的集合抽错，红必须落在那一题的那几列 ----------------
        target = questions[3]["id"]
        sabotage_path = root / "sabotage_pgvector.jsonl"
        sabotage_path.write_bytes(files["pgvector"].read_bytes())

        def _drop_top1(hits):
            """把这一题的 top-1 抽掉、补一枚外来的块：集合与名次同时变，别的都不许变。"""
            if len(hits) < 2:
                return hits
            foreign = dict(hits[0])
            foreign["source"] = "sabotaged-doc.txt"
            foreign["chunk_index"] = 999999
            foreign["key"] = "sabotaged-doc.txt#999999"
            return hits[1:] + [foreign]

        touched = _rewrite_hits(sabotage_path, target, _drop_top1)
        rows5, summary5 = compare_arm_files(
            [files["chroma-hot"], files["chroma-cold"], sabotage_path], base_arm="chroma-hot",
            census=census_from_catalog(services["chroma-hot"].catalog()))
        red_rows = [row for row in rows5
                    if row["target_arm"] == "pgvector" and not row["same_set"]]
        red_ids = [row["id"] for row in red_rows]
        _pin(pins, "P5 反证钉：抽错一题 ⇒ 红的恰是那一题（且只有那一题）",
             touched == 1 and red_ids == [target] and summary5["differing_set"] == 1,
             "touched={0} red={1} differing={2}".format(touched, red_ids,
                                                        summary5["differing_set"]))
        _pin(pins, "P5b 红落在集合列而不是别处：那一题 jaccard<1 且 top1_changed",
             red_rows and all(row["jaccard"] is not None and row["jaccard"] < 1.0
                              and row["top1_changed"] and row["first_diff_rank"] == 1
                              for row in red_rows),
             json.dumps([{ "id": row["id"], "jaccard": row["jaccard"],
                          "first_diff_rank": row["first_diff_rank"]} for row in red_rows]))

        # ---- P6 反证钉：两臂集合完全相同，只把权限抽错 ⇒ 只有权限列红 ----------------
        leak_path_hot = root / "leak_chroma_hot.jsonl"
        leak_path_pg = root / "leak_pgvector.jsonl"
        leak_questions = questions[:4]
        hot_leak = SyntheticService(arm_leg=LEG_CHROMA, hot_enabled=True,
                                    classifications=(1,), departments=("",),
                                    leak_on=(leak_questions[1]["question"],))
        pg_leak = SyntheticService(arm_leg=LEG_PGVECTOR, classifications=(1,), departments=("",),
                                   leak_on=(leak_questions[1]["question"],))
        _collect_arm("chroma-hot", hot_leak, leak_path_hot, leak_questions, limits)
        _collect_arm("pgvector", pg_leak, leak_path_pg, leak_questions, limits)
        rows6, summary6 = compare_arm_files([leak_path_hot, leak_path_pg], base_arm="chroma-hot")
        leaked = [row for row in rows6 if row["permission_leak_rows"]]
        _pin(pins, "P6 反证钉：越权行只在权限列红，集合列仍全绿",
             summary6["differing_set"] == 0 and len(leaked) == 1
             and leaked[0]["id"] == leak_questions[1]["id"]
             and leaked[0]["same_set"] is True and leaked[0]["jaccard"] == 1.0,
             "differing={0} leaked_rows={1}".format(
                 summary6["differing_set"], json.dumps(leaked[:1], ensure_ascii=False)[:180]))
        _pin(pins, "P6b 越权逐格计数进汇总：cells.9.3-3.over_permission_rows",
             summary6["cells"]["9.3-3_selective_permission"]["over_permission_rows"] >= 2,
             json.dumps(summary6["cells"]["9.3-3_selective_permission"]["over_permission_rows"]))

        # ---- P7 可选性硬闸：语料没有可选性就不许说 ③ 量到了 -------------------------
        _pin(pins, "P7 现库形状（class 全 1 / dept 全空）⇒ ③ 判 NOT_MEASURED 并指名原因",
             summary6["cells"]["9.3-3_selective_permission"]["status"] == "NOT_MEASURED"
             and summary6["selectivity_screen"]["reasons"],
             json.dumps(summary6["selectivity_screen"]["reasons"], ensure_ascii=False)[:220])
        selective_hot = SyntheticService(arm_leg=LEG_CHROMA, hot_enabled=True,
                                         classifications=(1, 2, 3), departments=("fin", "hr"))
        selective_pg = SyntheticService(arm_leg=LEG_PGVECTOR,
                                        classifications=(1, 2, 3), departments=("fin", "hr"))
        sel_hot = root / "selective_chroma_hot.jsonl"
        sel_pg = root / "selective_pgvector.jsonl"
        _collect_arm("chroma-hot", selective_hot, sel_hot, leak_questions, limits)
        _collect_arm("pgvector", selective_pg, sel_pg, leak_questions, limits)
        _, summary7 = compare_arm_files([sel_hot, sel_pg], base_arm="chroma-hot",
                                        census=census_from_catalog(selective_hot.catalog()))
        _pin(pins, "P7b 反证钉的正面：换成跨部门跨密级语料，③ 就变 SUPPLIED",
             summary7["cells"]["9.3-3_selective_permission"]["status"] == "SUPPLIED"
             and summary7["selectivity_screen"]["selective"] is True
             and census_from_catalog(selective_hot.catalog())["verdict"] == "CORPUS_IS_SELECTIVE",
             json.dumps({"status": summary7["cells"]["9.3-3_selective_permission"]["status"],
                         "levels": summary7["selectivity_screen"]["levels_in_play"],
                         "departments": summary7["selectivity_screen"]["departments_in_play"]}))

        # ---- P3b 写表路：三份产物落盘后逐字回读，红格必须还在 CSV 的那一行 ----------
        products = {"jsonl": root / "pairs.jsonl", "csv_path": root / "pairs.csv",
                    "md": root / "pairs.md", "json_path": root / "summary.json"}
        write_products(rows5, summary5, **products)
        with products["csv_path"].open(encoding="utf-8-sig", newline="") as handle:
            table = list(csv.DictReader(handle))
        header_line = products["csv_path"].read_text(encoding="utf-8-sig").splitlines()[0]
        back = json.loads(products["jsonl"].read_text(encoding="utf-8").splitlines()[0])
        _pin(pins, "P3b 写表路：CSV 列序=PAIR_COLUMNS 且回读题对数相等",
             header_line == ",".join(PAIR_COLUMNS) and len(table) == len(rows5)
             and back["kind"] == "summary" and back["pairs"] == summary5["pairs"],
             "csv_rows={0} jsonl_summary_kind={1}".format(len(table), back.get("kind")))
        red_in_csv = [row for row in table if row["same_set"] == "False"]
        _pin(pins, "P3c 反证钉进得了表：CSV 里恰有一行 same_set=False 且是那一个题号",
             [row["id"] for row in red_in_csv] == [target]
             and red_in_csv and red_in_csv[0]["jaccard"] not in ("", "1.0"),
             json.dumps([{ "id": row["id"], "jaccard": row["jaccard"],
                           "target_arm": row["target_arm"]} for row in red_in_csv]))
        markdown = products["md"].read_text(encoding="utf-8")
        _pin(pins, "P3d 人读表含三格状态与三臂代价分解",
             "9.3-2_hot_yield_cost" in markdown and "net_yield_cost_ms" in markdown
             and "噪声地板" in markdown, markdown.splitlines()[0][:80])
    finally:
        remove_offline_guard()

    red = [item for item in pins if not item["ok"]]
    for item in pins:
        print("[{0}] {1}".format(item["pin"],
                                 item["detail"][:240] if verbose else item["detail"][:80]))
    print(json.dumps({"tool": TOOL, "mode": "selfcheck", "offline": True,
                      "questions_source": source, "pins_total": len(pins),
                      "pins_red": [item["pin"] for item in red],
                      "blocked_socket_attempts": _BLOCKED[:3],
                      "verdict": "SELF_CHECK_OK" if not red else "SELF_CHECK_RED"},
                     ensure_ascii=False, indent=2))
    return EXIT_OK if not red else 1


# ---------------------------------------------------------------------------- CLI

def compare_arm_files(paths: list, *, base_arm: str, census: dict | None = None) -> tuple:
    """CLI 与自校共用的一条门：读臂 -> 配对 -> 汇总。"""
    return compare([read_arm(Path(path)) for path in paths],
                   base_arm=base_arm, census=census)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL, description="R59c：服务内端到端召回对照量具（只发 HTTP，零连库）")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE),
                        help="题集 jsonl（默认 105 题评测集，只读引用）")
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 题；0 = 全部")
    sub = parser.add_subparsers(dest="command")

    probe = sub.add_parser("preflight", help="登录 + 读一发健康面，确认服务可达（零模型）")
    probe.add_argument("--timeout", type=float, default=15.0)

    cen = sub.add_parser("census", help="语料普查：可选性在不在（③ 的前置取证，零模型）")
    cen.add_argument("--out", default=None)
    cen.add_argument("--dry-run", action="store_true")
    cen.add_argument("--timeout", type=float, default=60.0)

    col = sub.add_parser("collect", help="一臂一遍：逐题打 retrieval/debug")
    col.add_argument("--arm", required=True, choices=sorted(ARMS))
    col.add_argument("--out", required=True, help="本臂 JSONL（append-only）")
    col.add_argument("--top-k", default="", help="逗号分隔档位；空 = 用服务默认值。"
                                                 "每一档都是**独立重发**，不是截前缀")
    col.add_argument("--repeats", type=int, default=1,
                     help="同题重发次数（噪声地板唯一来源；1 = 代价只能给方向）")
    col.add_argument("--attempts", type=int, default=3, help="单发失败重跑次数")
    col.add_argument("--retry-sleep", type=float, default=10.0)
    col.add_argument("--gap-seconds", type=float, default=0.0)
    col.add_argument("--max-requests", type=int, default=260, help="预算闸（每发都打模型）")
    col.add_argument("--resume", action="store_true", help="跳过本文件里已 ok 的格")
    col.add_argument("--no-health-probe", dest="health_probe", action="store_false",
                     help="不配读健康面 —— 臂身份就无从证实，只在探索时用")
    col.add_argument("--dry-run", action="store_true", help="只打印将发的请求，零 socket")

    cmpar = sub.add_parser("compare", help="多臂对差：JSONL / CSV / JSON / Markdown")
    cmpar.add_argument("runs", nargs="+", help="collect 产物，至少两份")
    cmpar.add_argument("--base", required=True, choices=sorted(ARMS),
                       help="延迟差与名次差的参照臂")
    cmpar.add_argument("--census", default=None, help="census 的 JSON 产物（判 ③ 用）")
    cmpar.add_argument("--jsonl", default=None)
    cmpar.add_argument("--csv", default=None)
    cmpar.add_argument("--md", default=None)
    cmpar.add_argument("--summary", dest="json_path", default=None)
    cmpar.add_argument("--show-red", type=int, default=20)

    check = sub.add_parser("selfcheck", help="离线自校（判据 ④）：假服务跑通三路 + 反证钉")
    check.add_argument("--verbose", action="store_true")
    check.add_argument("--workdir", default=None)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_PRECONDITION
    try:
        limits = server_limits()
    except Exception as exc:  # noqa: BLE001
        print(f"[前置不满足] {exc}")
        return EXIT_PRECONDITION
    if args.command == "selfcheck":
        return run_selfcheck(verbose=args.verbose,
                             workdir=Path(args.workdir) if args.workdir else None)
    base_url, username, password = credentials_from_env()
    transport = Transport(base_url, username, password, timeout=getattr(args, "timeout", 120.0))
    if args.command == "preflight":
        try:
            transport.login()
            health = transport.health()
        except Exception as exc:  # noqa: BLE001
            print(f"[前置不满足] {type(exc).__name__}: {exc}")
            return EXIT_PRECONDITION
        print(json.dumps({"base_url": transport.base_url, "username": transport.username,
                          "status": health.get("status"), "problems": health.get("problems"),
                          "search_shape": (health.get("search_shape") or {}).get("answered_by"),
                          "hot_index": {key: value for key, value in
                                        (health.get("hot_index") or {}).items()
                                        if key in ("enabled", "hits", "misses", "resident_chunks",
                                                   "max_chunks", "last_bypass_reason",
                                                   "roster_fresh")},
                          "next": "census -> collect --arm ... -> compare"},
                         ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.command == "census":
        if not args.dry_run and not transport.username:
            print("[前置不满足] census 要读目录面，凭据缺失：R59C_USERNAME/R59C_PASSWORD 必须显式给")
            return EXIT_PRECONDITION
        return census(transport, Path(args.out) if args.out else None,
                      dry_run=args.dry_run, log=print)
    try:
        questions = load_questions(Path(args.fixture), args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[前置不满足] 题集装载失败：{exc}")
        return EXIT_PRECONDITION
    if args.command == "collect":
        # dry-run 连一发都不发，所以它**不该**要凭据：判据 ① 要求它能离线跑通
        if not args.dry_run and (
                not (os.getenv("R59C_USERNAME") or os.getenv("EVAL_USERNAME"))
                or not (os.getenv("R59C_PASSWORD") or os.getenv("EVAL_PASSWORD")
                        or os.getenv("EB_EVAL_PASSWORD"))):
            print("[前置不满足] 凭据缺失：R59C_USERNAME/R59C_PASSWORD（或 EVAL_*）必须显式给，"
                  "本件不猜账号")
            return EXIT_PRECONDITION
        top_ks = [int(item) for item in str(args.top_k).split(",") if item.strip()] \
            or [limits["default_top_k"]]
        over = [item for item in top_ks if item > limits["max_top_k"]]
        if over:
            print(f"[用法] top_k {over} 超 MAX_TOP_K={limits['max_top_k']}，服务端会 clamp，"
                  f"读数里那一档就不是你要的档；改成 <= {limits['max_top_k']} 再来")
            return EXIT_PRECONDITION
        return collect(args.arm, questions, transport=transport, top_ks=top_ks,
                       repeats=args.repeats, out_path=Path(args.out), resume=args.resume,
                       attempts=args.attempts, retry_sleep=args.retry_sleep,
                       max_requests=args.max_requests, gap_seconds=args.gap_seconds,
                       health_probe=args.health_probe, limits=limits, dry_run=args.dry_run,
                       log=print)
    if args.command == "compare":
        census_payload = None
        if args.census:
            try:
                census_payload = json.loads(Path(args.census).read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                print(f"[前置不满足] census 产物读不动（{args.census}）：{exc}")
                return EXIT_PRECONDITION
        try:
            rows, summary = compare_arm_files([Path(item) for item in args.runs],
                                              base_arm=args.base, census=census_payload)
        except Exception as exc:  # noqa: BLE001 - 身份未证实/前置不满足都从这里出去
            print(f"[拒收] {exc}")
            return (EXIT_ARM_UNVERIFIED if "身份未证实" in str(exc) else EXIT_PRECONDITION)
        write_products(rows, summary,
                       jsonl=Path(args.jsonl) if args.jsonl else None,
                       csv_path=Path(args.csv) if args.csv else None,
                       md=Path(args.md) if args.md else None,
                       json_path=Path(args.json_path) if args.json_path else None)
        print(json.dumps({key: summary[key] for key in
                          ("base_arm", "arms", "pairs", "same_set", "differing_set", "both_empty",
                           "mean_jaccard", "median_jaccard", "mean_abs_rank_shift",
                           "mean_kendall_tau", "top1_changed", "corpus_mutated_rows",
                           "headline_pass", "cells")}, ensure_ascii=False, indent=2))
        for row in [item for item in rows if not item.get("same_set")][:args.show_red]:
            print("  RED {id} k={k} jaccard={jaccard} first_diff_rank={first_diff_rank} "
                  "base_only={base_only_keys} target_only={target_only_keys}".format(**row))
        return decide_exit(rows, summary)
    return EXIT_PRECONDITION


if __name__ == "__main__":
    sys.exit(main())