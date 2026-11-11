# -*- coding: utf-8 -*-
"""R676 判据 ①（业主 10-06 裁**乙案**口径）· 同义词那一族题的 top-5 变化率量具。

零模型 · 零网络 · 零向量库 · 零写仓内盘。跑法（仓库根，工作树解释器）::

    python scripts/r676_synonym_top5_delta.py
    python scripts/r676_synonym_top5_delta.py --json
    python scripts/r676_synonym_top5_delta.py --selfcheck
    python scripts/r676_synonym_top5_delta.py --selfcheck --mutate swap-rate
    python scripts/r676_synonym_top5_delta.py --selfcheck --mutate drop-leg
    python scripts/r676_synonym_top5_delta.py --selfcheck --json --out %TEMP%/evalrun/r676/run.json

判据口径（乙案原文见 ``docs/tickets/R676-synonym-rewrite-no-roundtrip.md`` 文末派工段）
--------------------------------------------------------------------------------
R47 判据 ①「同义词题命中改进」**不按 105 题评测集的 ``must_contain`` 命中判**（夹具一字节
不许动，它归 ``tests/test_evaluation_report.py`` 钉），改按**同义词腿开／关两臂的 top-5
变化率**判：

    变化率 = 挤进 top-5 的新块数 ÷ top_k

分母恒为生产 doc 腿那一枚 ``top_k``（两枚出处各读一次并互证，见 ``read_top_k``），
**不是候选数、不是召回条数**。分子分母对调是判据 ② 点名的反证形，``validate_report``
与 ``tests/test_r676_top5_delta_gauge_shape.py`` 各拦一道。

族成员由产品规则现定，本件不手写题号：同一份进程状态下（fast 档，模型改写不发生），
产品自己的 ``app.rag.retrieval_pipeline.expand_query_synonyms`` 对那道题交回非空 ⇒ 该题属
「同义词那一族」。

量什么、不量什么（每一格都进读数，不留在感想里）
----------------------------------------------
- 两臂跑的都是**生产 ``RetrievalPipeline.search()`` 本体**（含 ``should_rewrite_query``、
  ``MAX_RECALL_QUERIES`` 截断、两条腿、``_deduplicate``、``rrf_fusion``、装箱前的名次）。
  臂与臂之间只许有一个变量：同义词腿开还是关（关＝把 ``expand_query_synonyms`` 摘成恒回空）。
- 🔴 语义腿需要 embedding 模型调用，落在本单禁止面上 ⇒ 用在册替身 ``RecordingSemantic``
  恒回 0 行，读数标 ``legs=keyword-only``；重排钉成 ``RankPreservingReranker``（真
  Cross-Encoder 一上就变成第二次变量）。**词腿单腿的 top-5 不是生产 top-5**，两腿真值待窗。
- 🔴 生产两条腿并发提交、``as_completed`` 完成顺序不固定（在册缺口见量具
  ``scripts/r219_rewrite_tier_compare.py`` 模块头「已知缺口」：同臂连跑两次 top-k 会漂）。
  本件把到达顺序钉死：主读数 = **提交顺序**（原题在前、扩展词在后）——这对规则腿是**最不利**
  顺序，所以 ``mean_rate_primary`` 读作**下界**；另出 ``mean_rate_reverse``（扩展词在前，
  对规则腿最有利）当**上界口径**，它不是生产顺序，只用来把量级框住。
- 权限口径不在射程：离线 ``pred=None``（与 R219 同一取舍），密级/部门只由
  ``app/rag/filters.py`` 那一处判定，本件不复制。
- 语料口径：``documents/`` 的 git 跟踪篇目经 R94 常驻件读入，按现网分块常数本地重建，
  枚数与生产卷**不同口径**，读数一律标 ``corpus=local-rebuild``，不得当生产召回读数引用。
- 术语目录取仓内出厂词表（``registry._database_available`` 钉 False）：客户库里的目录行
  与出厂词表的差异不在本件射程 ⇒ 那一格同样待窗。

复用，不复制
------------
题集／语料读法、离线闸门、名次保持替身全部取自在册件 ``scripts/r219_rewrite_tier_compare.py``
（它又复用 ``scripts/check_eval_evidence_coverage.py`` 的 R94 读法）。本件不另造一套题集读法，
也不第二次换进程级 socket 闸门。
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.util
import json
import os
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

R219_REL = Path("scripts/r219_rewrite_tier_compare.py")
FIXTURE_REL = Path("tests/fixtures/business_evaluation_100.jsonl")
PIPELINE_REL = Path("app/rag/retrieval_pipeline.py")
TOOLS_REL = Path("app/agents/tools.py")

#: 反证形（判据 ② 点名的两枚突变），由 ``--mutate`` 施加，只活在本次进程里。
MUTATE_NONE = "none"
MUTATE_SWAP_RATE = "swap-rate"
MUTATE_DROP_LEG = "drop-leg"
MUTATES = (MUTATE_NONE, MUTATE_SWAP_RATE, MUTATE_DROP_LEG)


def load_r219():
    """按文件路径装载在册量具（装载法照抄 R219 装载 R94 常驻件那一形）。"""
    spec = importlib.util.spec_from_file_location("r676_r219", REPO_ROOT / R219_REL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# top_k 的出处：两枚独立读法互证，谁都不许手抄
# ---------------------------------------------------------------------------

def defaults_by_name(args: ast.arguments) -> dict:
    """形参名对默认值 ast（``args.defaults`` 是从右往左对齐的那一段）。"""
    positional = list(args.args)
    defaults = list(args.defaults)
    if not defaults:
        return {}
    start = len(positional) - len(defaults)
    return {positional[index + start].arg: default for index, default in enumerate(defaults)}


def pipeline_search_top_k(tree: ast.AST) -> int:
    """``app/rag/retrieval_pipeline.py::RetrievalPipeline.search`` 的 ``top_k`` 缺省值。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RetrievalPipeline":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "search":
                    default = defaults_by_name(item.args).get("top_k")
                    if isinstance(default, ast.Constant) and isinstance(default.value, int):
                        return int(default.value)
    raise AssertionError(f"没在 {PIPELINE_REL} 读到 RetrievalPipeline.search 的 top_k 缺省值")


def doc_leg_top_k(tree: ast.AST) -> tuple:
    """``app/agents/tools.py`` 里调用 ``search_for_principal`` 的那个函数交回的 ``top_k``。

    只认「函数体内确实调了 ``search_for_principal``」的那几枚函数，别处的 ``top_k`` 不算。
    读空或读出多于一枚取值都当场炸——本件的分母全靠这一个数。
    """
    values: set[int] = set()
    carriers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = [call for call in ast.walk(node)
                 if isinstance(call, ast.Call)
                 and getattr(call.func, "attr", "") == "search_for_principal"]
        if not calls:
            continue
        carriers.add(node.name)
        for sub in ast.walk(node):
            if isinstance(sub, ast.Dict):
                for key, value in zip(sub.keys, sub.values):
                    if (isinstance(key, ast.Constant) and key.value == "top_k"
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, int)):
                        values.add(int(value.value))
            if isinstance(sub, ast.Call):
                for keyword in sub.keywords:
                    if (keyword.arg == "top_k" and isinstance(keyword.value, ast.Constant)
                            and isinstance(keyword.value.value, int)):
                        values.add(int(keyword.value.value))
    if len(values) != 1:
        raise AssertionError(
            f"{TOOLS_REL} 里 search_for_principal 的 top_k 读不出唯一取值："
            f"现取 {sorted(values)}（承载函数 {sorted(carriers)}）")
    return (values.pop(), sorted(carriers))


def read_top_k() -> dict:
    pipeline_tree = ast.parse((REPO_ROOT / PIPELINE_REL).read_bytes().decode("utf-8"))
    tools_tree = ast.parse((REPO_ROOT / TOOLS_REL).read_bytes().decode("utf-8"))
    from_default = pipeline_search_top_k(pipeline_tree)
    from_tool, carriers = doc_leg_top_k(tools_tree)
    return {
        "value": from_tool,
        "pipeline_search_default": from_default,
        "doc_leg_tool_value": from_tool,
        "doc_leg_carriers": carriers,
        "two_reads_agree": from_default == from_tool,
        "provenance": [f"{PIPELINE_REL.as_posix()}::RetrievalPipeline.search",
                       f"{TOOLS_REL.as_posix()}::" + "、".join(carriers)],
    }


# ---------------------------------------------------------------------------
# 变化率：分子／分母只住在这里（判据 ② 的反证就打在这一格）
# ---------------------------------------------------------------------------

def top5_change_rate(entered_top5: int, denominator: int) -> float:
    """挤进 top-5 的**新块数** ÷ ``top_k``。

    分子＝新进入 top-5 的块数，分母＝``top_k`` 枚 ⇒ 取值域必然落在 ``[0, 1]``。
    把两枚对调（``top_k ÷ 新块数``）就是判据 ② 点名的反证形：它要么越出 [0, 1]，
    要么与「率＝新块数 ÷ 分母」这一格自证不合，两处各拦一道。
    """
    if denominator <= 0:
        raise AssertionError(f"变化率的分母必须是正整数枚数，现取 {denominator}")
    return entered_top5 / denominator


def swapped_change_rate(entered_top5: int, denominator: int) -> float:
    """反证形：分子分母对调。只由 ``--mutate swap-rate`` 或反证牙绑上去，正常路径永不调到。"""
    if entered_top5 <= 0:
        return 0.0
    return denominator / entered_top5


# ---------------------------------------------------------------------------
# 顺序钉：把生产的并发完成顺序换成提交顺序（可反序）
# ---------------------------------------------------------------------------

class DeferredFuture:
    """一枚「被迭代到才执行」的 future：腿的执行顺序因此完全由 ``as_completed`` 的交出顺序定。"""

    def __init__(self, thunk):
        self._thunk = thunk
        self._settled = False
        self._value = None
        self._error = None

    def result(self, timeout=None):
        if not self._settled:
            try:
                self._value = self._thunk()
            except BaseException as exc:  # noqa: BLE001 - 原样交给生产的那处 try
                self._error = exc
            self._settled = True
        if self._error is not None:
            raise self._error
        return self._value


class SequentialExecutor:
    """``ThreadPoolExecutor`` 的形状替身：不起线程、不并发，只攒任务并按时序交出。"""

    def __init__(self, max_workers=None, *args, **kwargs):
        self.max_workers = max_workers

    def submit(self, fn, *args, **kwargs):
        return DeferredFuture(lambda: fn(*args, **kwargs))

    def map(self, fn, iterable, *args, **kwargs):
        return [fn(item, *args, **kwargs) for item in iterable]

    def shutdown(self, *args, **kwargs):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@contextlib.contextmanager
def pinned_arrival_order(module, *, reverse: bool):
    """把 ``search()`` 里两条腿的到达顺序钉成提交顺序（``reverse=True`` 时整序倒过来）。

    还原是硬要求：换的是 ``app.rag.retrieval_pipeline`` 的模块属性，同进程邻居也看得见。
    """
    original_executor = module.ThreadPoolExecutor
    original_as_completed = module.as_completed
    module.ThreadPoolExecutor = SequentialExecutor

    def ordered(futures, *args, **kwargs):
        items = list(futures)
        return list(reversed(items)) if reverse else items

    module.as_completed = ordered
    try:
        yield
    finally:
        module.ThreadPoolExecutor = original_executor
        module.as_completed = original_as_completed


@contextlib.contextmanager
def synonym_leg_disabled(module, *, disabled: bool):
    """摘掉同义词腿：把 ``expand_query_synonyms`` 换成恒回空（判据 ② 的另一枚反证形）。"""
    if not disabled:
        yield
        return
    original = module.expand_query_synonyms
    module.expand_query_synonyms = lambda *args, **kwargs: []
    try:
        yield
    finally:
        module.expand_query_synonyms = original


class CountingModel:
    """``retrieval_pipeline.model`` 的绊线：任何一发模型往返都当场炸，并留下枚数。"""

    def __init__(self):
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError(f"R676 量具不许发模型往返：第 {self.calls} 发 model.chat 被调到")

    def __getattr__(self, name):
        raise AssertionError(f"R676 量具不许碰模型面：被要到属性 {name}")


class RewriteTripwire:
    """顶在 ``QueryRewriter`` 位置上的绊线：判据 ②「改写仍走规则」的运行时装闸。"""

    def __init__(self):
        self.hits = 0

    def rewrite(self, question, *args, **kwargs):
        self.hits += 1
        raise AssertionError(
            f"R676 量具不许付查询改写往返：QueryRewriter.rewrite 被调到（题面 {question!r}）")


class CollectingBm25:
    """在册 ``RecordingBm25`` 的同一形状，多记一行返回的候选块。

    🔴 评分、截断、``pred`` 路径一字不改：本件只在这一层看一眼生产真正拿到的候选集，
    用来交「同义词腿补回了原题词面召不回的块」那一格（它不是 top-5 变化率，是它的因由）。
    """

    def __init__(self, inner):
        self.inner = inner
        self.queries: list[str] = []
        self.rows: list[dict] = []

    def search(self, query, k=10, pred=None):
        hits = self.inner.search(query, k=k, pred=pred)
        self.queries.append(str(query))
        self.rows.extend(hits)
        return hits

    def reset(self) -> None:
        self.queries.clear()
        self.rows.clear()


def chunk_id(row: dict) -> str:
    return f"{row.get('source')}#{row.get('chunk_index')}"


def build_pipeline(module, r219, documents: list[dict], tripwire: RewriteTripwire):
    """生产管线本体 + 替身腿（语料从仓内文件重建，绕开 ``build_index`` 的向量库读法）。"""
    pipeline = module.RetrievalPipeline.__new__(module.RetrievalPipeline)
    searcher = module.BM25Searcher()
    corpus = [module._tokenize_text(row["content"]) for row in documents]
    searcher.corpus = corpus
    searcher.documents = documents
    searcher.bm25 = module.BM25Okapi(corpus)
    pipeline.bm25 = CollectingBm25(searcher)
    pipeline.semantic = r219.RecordingSemantic()
    pipeline.reranker = r219.RankPreservingReranker()
    pipeline.rewriter = tripwire
    return pipeline


def run_arm(pipeline, module, question: str, *, top_k: int, reverse: bool,
            leg_off: bool) -> dict:
    """跑一臂：生产 ``search()``，``tier=fast``（不发模型改写），唯一变量是同义词腿开／关。"""
    pipeline.bm25.reset()
    pipeline.semantic.queries.clear()
    with synonym_leg_disabled(module, disabled=leg_off):
        with pinned_arrival_order(module, reverse=reverse):
            ranked, rewrites = pipeline.search(question, top_k=top_k, tier="fast")
    return {
        "hits": [chunk_id(row) for row in ranked],
        "queries": list(pipeline.bm25.queries),
        "candidates": [chunk_id(row) for row in module._deduplicate(list(pipeline.bm25.rows))],
        "returned_rewrites": list(rewrites or []),
    }


# ---------------------------------------------------------------------------
# 主测量
# ---------------------------------------------------------------------------

def collect_expansions(module, question: str, *, drop_leg: bool) -> list:
    """族成员判定用的那一发扩展词：走产品函数本体；``drop_leg`` 是判据 ② 的反证施加口。"""
    if drop_leg:
        return []
    return [str(item) for item in (module.expand_query_synonyms(question, [question]) or [])]


def blocked_in_full_tier(module, question: str) -> bool:
    """生产 full 档改写正常返回那一形下，规则腿还剩几个槽（排满 ⇒ 扩展自己交回空）。

    ``base_queries`` 摆成 ``MAX_RECALL_QUERIES`` 加一行的长度：改写正常返回时原题＋3 枚
    rewrites＋2-3 枚 sub_questions 必然排满那几枚槽。占位串的词形不参与判定，
    判的是 ``MAX_RECALL_QUERIES`` 那一格算术。
    """
    queued = [question] + [f"改写占位{index}" for index in
                           range(1, module.MAX_RECALL_QUERIES + 1)]
    return module.expand_query_synonyms(question, queued) == []


def direction_hint(entered: list, documents: list[dict], spec: dict, coverage) -> bool:
    """新进入 top-5 的那几枚块里有没有整段答案的字面（**非判据**，只是方向参考）。"""
    if not entered:
        return False
    answer = coverage.normalize(str(spec.get("answer") or ""))
    if len(answer) < 2:
        return False
    by_id = {chunk_id(row): row for row in documents}
    for hit in entered:
        row = by_id.get(hit)
        if row is not None and answer in coverage.normalize(row["content"]):
            return True
    return False


def measure(r219, limit: int | None = None, mutate: str = MUTATE_NONE) -> dict:
    """量整族两臂。离线承诺（零模型·零网络·零向量库·不读客户目录行）落在这枚函数里。

    闸门的落点有先后：重依赖 import（``app.rag.retrieval_pipeline`` 与 langchain 的分块器）
    必须在**装闸之前**跑完——pydantic／langchain 在 import 期就要拿 socket 的类与函数，
    先把它们换掉会把 import 链本身炸断（R219 在册实测）。
    """
    from app.rag import retrieval_pipeline as module
    from app.semantics import registry as semantics_registry

    coverage = r219.load_coverage()
    rows_spec = coverage.load_rows(REPO_ROOT / FIXTURE_REL)
    documents, corpus_meta = r219.build_index(coverage)
    top_k_read = read_top_k()
    top_k = top_k_read["value"]

    model_tripwire = CountingModel()
    rewrite_tripwire = RewriteTripwire()
    original_model = module.model
    original_database_available = semantics_registry._database_available
    attempts_before = len(r219.BLOCKED_SOCKET_ATTEMPTS)
    module.model = model_tripwire
    # 术语目录钉成仓内出厂词表：本机有没有 PostgreSQL、客户库里有没有目录行，都不许改这张表。
    semantics_registry._database_available = lambda: False
    r219.install_offline_guard()
    drop_leg = mutate == MUTATE_DROP_LEG

    rows: list[dict] = []
    rerun_identical = True
    rerun_sampled = 0
    try:
        pipeline_off = build_pipeline(module, r219, r219.clone_documents(documents),
                                      rewrite_tripwire)
        pipeline_on = build_pipeline(module, r219, r219.clone_documents(documents),
                                     rewrite_tripwire)
        pipeline_rev = build_pipeline(module, r219, r219.clone_documents(documents),
                                      rewrite_tripwire)
        for spec in rows_spec:
            question = str(spec["question"])
            expansions = collect_expansions(module, question, drop_leg=drop_leg)
            if not expansions:
                continue
            if limit is not None and len(rows) >= limit:
                break
            arm_off = run_arm(pipeline_off, module, question, top_k=top_k,
                              reverse=False, leg_off=True)
            arm_on = run_arm(pipeline_on, module, question, top_k=top_k,
                             reverse=False, leg_off=False)
            arm_rev = run_arm(pipeline_rev, module, question, top_k=top_k,
                              reverse=True, leg_off=False)
            # 自校：同一臂、同一管线对象连跑第二次（状态累积就露在这一格）
            again = run_arm(pipeline_on, module, question, top_k=top_k,
                            reverse=False, leg_off=False)
            rerun_sampled += 1
            rerun_identical &= (again["hits"] == arm_on["hits"])

            off_top5 = set(arm_off["hits"])
            off_candidates = set(arm_off["candidates"])
            entered = [hit for hit in arm_on["hits"] if hit not in off_top5]
            entered_rev = [hit for hit in arm_rev["hits"] if hit not in off_top5]
            new_candidates = [hit for hit in arm_on["candidates"]
                              if hit not in off_candidates]
            by_id = {chunk_id(row): row for row in documents}
            new_with_term = sum(
                1 for hit in new_candidates
                if any(term in by_id[hit]["content"] for term in expansions if hit in by_id))
            rows.append({
                "id": str(spec["id"]),
                "question": question,
                "expansions": expansions,
                "n_expansions": len(expansions),
                "blocked_in_full_tier": blocked_in_full_tier(module, question),
                "queries_off": arm_off["queries"],
                "queries_on": arm_on["queries"],
                "returned_rewrites": arm_on["returned_rewrites"],
                "candidates_off": len(arm_off["candidates"]),
                "candidates_on": len(arm_on["candidates"]),
                "new_candidates": len(new_candidates),
                "new_candidates_with_term": new_with_term,
                "top5_off": arm_off["hits"],
                "top5_on": arm_on["hits"],
                "top5_reverse": arm_rev["hits"],
                "entered_top5": len(entered),
                "entered_top5_reverse": len(entered_rev),
                "rate_denominator": top_k,
                "rate_primary": top5_change_rate(len(entered), top_k),
                "rate_reverse": top5_change_rate(len(entered_rev), top_k),
                "literal_recall_short": len(arm_off["hits"]) < top_k,
                "direction_hint_new_block_has_answer": direction_hint(
                    entered, documents, spec, coverage),
                "direction_note": "非判据·方向参考（乙案不用 must_contain 命中判）",
            })
        rates = [row["rate_primary"] for row in rows]
        rates_rev = [row["rate_reverse"] for row in rows]
        summary = {
            "criterion": "top5_change_rate",
            "ruling": "业主 10-06 裁乙案：不动 105 题夹具，按 top-5 变化率判命中改进",
            "must_contain_used": False,
            "fixture_rows": len(rows_spec),
            "family_questions": len(rows),
            "family_ratio_of_fixture": (len(rows) / len(rows_spec)) if rows_spec else 0.0,
            "blocked_in_full_tier": sum(1 for row in rows if row["blocked_in_full_tier"]),
            "questions_with_nonzero_primary": sum(1 for row in rows if row["entered_top5"]),
            "questions_with_nonzero_reverse": sum(1 for row in rows if row["entered_top5_reverse"]),
            "total_entered_top5": sum(row["entered_top5"] for row in rows),
            "mean_rate_primary": statistics.fmean(rates) if rates else 0.0,
            "mean_rate_reverse": statistics.fmean(rates_rev) if rates_rev else 0.0,
            "max_rate_primary": max(rates) if rates else 0.0,
            "max_rate_reverse": max(rates_rev) if rates_rev else 0.0,
            "total_new_candidates": sum(row["new_candidates"] for row in rows),
            "total_new_candidates_with_term": sum(row["new_candidates_with_term"] for row in rows),
            "questions_with_answer_in_new_block": sum(
                1 for row in rows if row["direction_hint_new_block_has_answer"]),
            "literal_recall_short": sum(1 for row in rows if row["literal_recall_short"]),
            "top_k": top_k_read,
            "recall_slots": module.MAX_RECALL_QUERIES,
            "synonym_max_queries": module.SYNONYM_EXPANSION_MAX_QUERIES,
            "synonym_max_query_chars": module.SYNONYM_EXPANSION_MAX_QUERY_CHARS,
            "model_roundtrips": model_tripwire.calls,
            "rewrite_tripwire_hits": rewrite_tripwire.hits,
            "legs": "keyword-only",
            "assembly": "生产 RetrievalPipeline.search 本体；到达顺序钉成提交顺序",
            "catalog": "出厂词表（测量期内把 registry._database_available 钉 False，不读客户目录行）",
            "determinism": {"primary_rerun_identical": bool(rerun_identical),
                            "sampled": rerun_sampled},
            "guard": {
                "blocked_socket_attempts": len(r219.BLOCKED_SOCKET_ATTEMPTS) - attempts_before,
                "chromadb_imported": r219.chromadb_loaded(),
            },
            "catalog_pinned": semantics_registry._database_available() is False,
            "corpus": corpus_meta,
            "sample": {"fixture": FIXTURE_REL.as_posix(), "rows": len(rows_spec), "used": len(rows)},
            "mutation": mutate,
        }
        return {"summary": summary, "rows": rows}
    finally:
        r219.uninstall_offline_guard()
        semantics_registry._database_available = original_database_available
        module.model = original_model


# ---------------------------------------------------------------------------
# 自校验（反证就红在这一格）
# ---------------------------------------------------------------------------

def validate_report(report: dict) -> None:
    """账面自证：任何一格算术不合就点名那一格并抛错。"""
    summary = report["summary"]
    rows = report["rows"]
    top_k = summary["top_k"]["value"]

    if not rows:
        raise AssertionError("validate：族为空——同义词腿一格都没生效，读数作废（摘腿反证形）")
    if summary["top_k"]["two_reads_agree"] is not True:
        raise AssertionError(f"validate：top_k 两枚出处对不上 {summary['top_k']['provenance']}")
    for row in rows:
        if row["rate_denominator"] != top_k:
            raise AssertionError(f"validate：{row['id']} 的分母不是 top_k 枚数")
        expected = top5_change_rate(row["entered_top5"], row["rate_denominator"])
        if row["rate_primary"] != expected:
            raise AssertionError(
                f"validate：{row['id']} 的变化率不是「新块数 ÷ top_k」"
                f"（现取 {row['rate_primary']}，应为 {expected}）")
        if not 0.0 <= row["rate_primary"] <= 1.0:
            raise AssertionError(
                f"validate：{row['id']} 的变化率越出 [0, 1]：{row['rate_primary']}"
                "（分子分母对调形）")
        if not 1 <= row["n_expansions"] <= summary["synonym_max_queries"]:
            raise AssertionError(
                f"validate：{row['id']} 的扩展词条数不在 1..SYNONYM_EXPANSION_MAX_QUERIES")
        if row["entered_top5"] > row["entered_top5_reverse"]:
            raise AssertionError(
                f"validate：{row['id']} 的下界读数高过了上界口径，顺序钉是坏的")
    if summary["model_roundtrips"] != 0:
        raise AssertionError(f"validate：模型往返 {summary['model_roundtrips']} 发")
    if summary["rewrite_tripwire_hits"] != 0:
        raise AssertionError(f"validate：改写绊线响 {summary['rewrite_tripwire_hits']} 次")
    if summary["guard"]["blocked_socket_attempts"] != 0:
        raise AssertionError("validate：闸门挡到过站连接，本件承诺零网络")
    if summary["determinism"]["primary_rerun_identical"] is not True:
        raise AssertionError("validate：同臂连跑两次 top-5 会漂，读数不能进验收")
    if summary["legs"] != "keyword-only":
        raise AssertionError("validate：本件只能以词腿单腿口径出数")
    if summary["catalog_pinned"] is not True:
        raise AssertionError("validate：术语目录没钉在出厂词表上，读数随本机库走")
    if summary["must_contain_used"] is not False:
        raise AssertionError("validate：乙案明令不按 must_contain 命中判")


def apply_mutation(gauge_module, mutate: str) -> None:
    """把反证形绑到盘上这一枚进程里的量具（不落文件、不改仓内任何一个字节）。"""
    if mutate == MUTATE_SWAP_RATE:
        gauge_module.top5_change_rate = swapped_change_rate


# ---------------------------------------------------------------------------
# 出数
# ---------------------------------------------------------------------------

def render(report: dict) -> str:
    summary = report["summary"]
    out: list[str] = []
    push = out.append
    push("=== R676 判据 ① · 同义词那一族题的 top-5 变化率（零模型·零网络·词腿单腿）===")
    push(f"口径 = {summary['ruling']}")
    push(f"变化率 = 挤进 top-5 的新块数 ÷ top_k；top_k = {summary['top_k']['value']}"
         f"（两枚出处互证 = {summary['top_k']['two_reads_agree']}，"
         f"{summary['top_k']['provenance']}）")
    push(f"题集 = {summary['sample']['fixture']} 共 {summary['fixture_rows']} 题"
         f"（一字节未动；must_contain_used={summary['must_contain_used']}）")
    corpus = summary["corpus"]
    push(f"语料 = documents 跟踪 {corpus['corpus_files']} 篇 / {corpus['corpus_chars']} 字"
         f" → 本地重建 {corpus['local_chunks']} 枚块（corpus={corpus['label']}；"
         f"生产卷参照 {corpus['production_chunks_reference']} 枚，同口径={corpus['matches_production_index']}）")
    push(f"腿 = {summary['legs']}   装配 = {summary['assembly']}   目录 = {summary['catalog']}")
    push(f"闸门 = 出站尝试 {summary['guard']['blocked_socket_attempts']} 次"
         f"   模型往返 {summary['model_roundtrips']} 发"
         f"   改写绊线 {summary['rewrite_tripwire_hits']} 次"
         f"   自校 = {summary['determinism']}")
    push("")
    push("[合计]")
    for key in ("family_questions", "family_ratio_of_fixture", "blocked_in_full_tier",
                "questions_with_nonzero_primary", "questions_with_nonzero_reverse",
                "total_entered_top5", "total_new_candidates", "mean_rate_primary",
                "mean_rate_reverse", "max_rate_primary", "max_rate_reverse",
                "literal_recall_short", "recall_slots", "synonym_max_queries",
                "synonym_max_query_chars", "model_roundtrips", "mutation"):
        value = summary[key]
        push(f"  {key} = {value:.4f}" if isinstance(value, float) else f"  {key} = {value}")
    push("")
    push("[逐题]")
    push("  id            扩展词                    候选补回  新块含词  进入top5  变化率  反序进入  反序变化率  短召回")
    for row in report["rows"]:
        push("  {id:<14}{exp:<24}{new:>9}{newt:>11}{ent:>10} {rate:>7.2f} "
             "{entrev:>9} {revrate:>11.2f} {short:>7}".format(
                 id=row["id"], exp="、".join(row["expansions"])[:22],
                 new=row["new_candidates"], newt=row["new_candidates_with_term"],
                 ent=row["entered_top5"], rate=row["rate_primary"],
                 entrev=row["entered_top5_reverse"], revrate=row["rate_reverse"],
                 short=row["literal_recall_short"]))
    push("")
    push("[结构因由（这一格是读数）]")
    push(f"  原题词腿召回不足 top_k 枚的族题 = {summary['literal_recall_short']} 枚"
         "：生产 RRF 的名次取拼接后腿内的到达位置，词腿单腿时扩展腿只能排在原题之后 ⇒"
         " 只有原题召回短于 top_k 那一形能把新块送进 top-5。")
    push(f"  同义词腿补回的候选块合计 = {summary['total_new_candidates']} 枚"
         "（候选面在动、top-5 面几乎不动，这两件事不矛盾）。")
    push(f"  满档挡槽：full 档改写正常返回时规则腿被挡在门外的族题 = "
         f"{summary['blocked_in_full_tier']}/{summary['family_questions']} 枚。")
    push("  两腿真值（语义腿在场）与真机命中改进 = 待窗，本件零模型量不到。")
    return "\n".join(out)


def resolve_out_path(raw: str) -> Path:
    """把 --out 里的 %TEMP%／~ 形态展成绝对路径，再交给 reject_inside_repo 把关。

    死枝补记（10-06 本席在 HEAD 上复跑量具时抓到）：早先 ``main`` 里那一行写的是
    ``Path(args.out).expandvars()``，而 Path 根本没有 expandvars，所以 --out 一用就炸
    AttributeError；旧的牙只直接测 ``reject_inside_repo``，没走 CLI 这条分支，死枝就一直躺着。
    判据要求「离线可跑并把读数落到仓外」，这条分支属于交付面，故补两枚走 CLI 本体的牙：
    ``tests/test_r676_top5_delta_gauge_shape.py``。
    """
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def reject_inside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if str(resolved).lower().startswith(str(REPO_ROOT).lower()):
        raise AssertionError(f"读数文件不许落在仓内：{resolved}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R676 判据 ①：同义词族 top-5 变化率（离线）")
    parser.add_argument("--limit", type=int, default=None, help="只量前 N 枚族题")
    parser.add_argument("--json", action="store_true", help="机器可读（仍只走 stdout）")
    parser.add_argument("--selfcheck", action="store_true", help="出数前跑 validate_report")
    parser.add_argument("--mutate", choices=MUTATES, default=MUTATE_NONE,
                        help="反证施加形：swap-rate＝分子分母对调，drop-leg＝摘掉同义词腿")
    parser.add_argument("--out", default=None, help="落盘路径（必须在仓外）")
    args = parser.parse_args(argv)

    r219 = load_r219()
    if args.mutate != MUTATE_NONE:
        apply_mutation(sys.modules[__name__], args.mutate)
    # 闸门与还原都住在 measure() 里：进程内调用方（测试）与命令行走同一套承诺。
    report = measure(r219, args.limit, args.mutate)
    if args.selfcheck:
        validate_report(report)
    text = (json.dumps(report, ensure_ascii=False, indent=1, default=str)
            if args.json else render(report))
    if args.out:
        target = reject_inside_repo(resolve_out_path(args.out))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        print(f"written: {target}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())