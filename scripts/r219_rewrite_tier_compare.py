# -*- coding: utf-8 -*-
"""R219 判据 3 · 抬 `RETRIEVAL_TIER=fast` 那道闸要用的量具（两臂对照，只跑检索、不跑模型）。

    .venv\\Scripts\\python.exe scripts/r219_rewrite_tier_compare.py --selfcheck
    .venv\\Scripts\\python.exe scripts/r219_rewrite_tier_compare.py --standin reorder
    .venv\\Scripts\\python.exe scripts/r219_rewrite_tier_compare.py --json --out %TEMP%\\r219_arms.json

它量什么
--------
同一批查询，两侧各跑一遍**生产检索管线本体**（`RetrievalPipeline.search`，含
`MAX_RECALL_QUERIES` 截断、两条腿、`_deduplicate`、`rrf_fusion`、装箱前的名次）：

- 臂 A `full`：付那一发查询改写 —— 但**改写用固定替身顶掉**（见下节），零模型往返；
- 臂 B `fast`：不发改写，`should_rewrite_query()` 直接返回 False（同一份生产代码，档位由
  形参 `tier=` 显式传入，**不读进程环境变量**，读漏一律由 `tests/test_r219_*.py` 判红）。

输出 = 逐题 top-k 集合差（same_set / overlap / jaccard / 名次漂移）+ 对金标的召回差
（recall@k 两臂各算，金标口径见「金标从哪来」）+ 两臂**实际送进召回的 query 列表**。
query 列表是量具的次产品：`full` 档那 3 枚 rewrites + 2-3 枚 sub_questions 里有几枚
被 `MAX_RECALL_QUERIES=5` 截掉、`fast` 档的空槽又被 `expand_query_synonyms` 补回几枚，
这两件事以前只在注释里，今天在这里可读数。

改写替身的来源与写法（判据要求写明）
------------------------------------
`QueryRewriter.rewrite` 被换成 `_StandInRewriter`，两档模式，都**零模型、零网络、可复算**：

- `--standin reorder`（**下界替身**）：3 枚 rewrites 只由题面自己的词重排/裁剪得到
  （jieba 切词后去掉疑问尾词，取 3 个不同前缀），2 枚 sub_questions 取题面子句。
  它**不注入题面之外的词**，所以它量到的是「多路扇出本身」值多少召回，不含模型创造力。
- `--standin registry`（**上界替身**）：3 枚 rewrites 取 `app/semantics/registry` 的
  `match_definition(question).match_terms`（仓内登记的指标词表，不是本件编的），
  不足 3 枚时用 reorder 替身补齐。词表读不动时（离线无目录）如实报 `unavailable`，
  不拿假词充数。
- 🔴 两档替身都**不是**真模型输出。真模型会注入题面没有的词形 —— 那一格**离线量不到**，
  列进交回的缺格清单（缺格 #3：现网录 30-105 题的改写正文 JSONL，喂回本件的
  `--standin-file` 走第三遍）。方向写清楚：reorder 替身**低估** full 臂的召回优势，
  registry 替身**接近但不等于**它 —— 所以本件给的是**风险带**，不是"抬闸安全"的证明。

样本与语料的点名口径（401 枚冒充 1008 枚那件事不再犯）
----------------------------------------------------
- 查询样本：`tests/fixtures/business_evaluation_100.jsonl`，git 跟踪，**105 题**，
  经 `scripts/check_eval_evidence_coverage.py:load_rows` 装载（就是 R94 那枚常驻件，
  本件不另造一套题集读法）。题号与 run6 三本原件逐号相等 ⇒ 同一张验收面。
- 语料：`documents/*.txt` 的 **git 跟踪 95 篇**（同上常驻件 `load_corpus` 主口径，
  篇数不等于 95 它自己就抛 `StructureDrift`）。
- 🔴 本件在这 95 篇上按现网分块常数重建出的是 **N 枚本地块**（运行时打印），
  它与生产卷的 **1008 枚**（出处 `docs/testing/r59b-recall-reading-2026-09-24.md` §1）
  **不是同一口径**。所以：**本件的离线读数一律标 `corpus=local-rebuild`，
  不得当生产召回读数引用**；生产那一腿必须在两侧同可达处跑（`--vector-leg`，见文末）。
- 向量腿（`SemanticSearcher` → nomic-embed-text @ Ollama）**是模型调用**，本件默认
  **不启用**：离线腿由 `_RecordingSemantic` 顶掉并计 0 行，读数标 `legs=keyword-only`。
  这不是偷懒，是本单的禁止面（不许打宿主模型）决定的；缺的那一格在缺格清单里。

金标从哪来
----------
`must_contain` 词条（同一份题集）→ 在本地语料块里做**子串命中**：🔴 已知缺口（本班实测，没修完，交回里也写了）
------------------------------------
`determinism.full_arm_rerun_identical`：同一臂、同一题、同一管线**连跑两次 top-k 会漂**
（25 题面前 3 题采样里 1 题不同，集合都不同，不是名次抖动）。已排除两件事：跨臂共享
文档对象（`clone_documents` 已分开）与 `_score` 残留（`reset_residue_scores` 每次清）。
剩下的怀疑面是同一份内存 BM25 索引上反复检索的副作用，本窗口没排完。⇒ **今天这份
量具的读数只能当形状演示，不能进验收**；修好它、并把这一格钉成硬闸，是抬闸前的第一缺格。

金标 = 含全部词条的块；
一篇都没有时退为含任一条词的块；两档都空 ⇒ 该题 `gold=None`，不计入召回均值并单独计数
（`rehearse-run6-summary.txt` 记的 `no_provenance_rows=29` 就是这一格）。
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import math
import os
import socket
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

COVERAGE_REL = Path("scripts/check_eval_evidence_coverage.py")
PIPELINE_REL = Path("app/rag/retrieval_pipeline.py")
RETRIEVER_REL = Path("app/rag/retriever.py")

#: 生产读路径的两个 top_k 现值（app/agents/tools.py 的 search_docs 用 5）。
TOP_K = 5

BLOCKED_SOCKET_ATTEMPTS: list[str] = []
_REAL_SOCKET_CLASS = socket.socket
#: 闸门必须在**重依赖 import 之后**再落：pydantic / langchain 在 import 期就要拿
#: `socket` 模块的类与函数，先把它们换掉会把 import 链本身炸断（本件 09-24 实测）。
_GUARD_ARMS = ("create_connection", "getaddrinfo")
_ORIGINALS: dict = {}


# ---------------------------------------------------------------------------
# 离线闸门：一发模型都不许打，chromadb 一次都不许 import
# ---------------------------------------------------------------------------

def install_offline_guard() -> None:
    """把出站 socket 换成会抛的桩，并记账。任何一次真连接都会当场炸给看的人。"""

    class _BlockedSocket(_REAL_SOCKET_CLASS):
        def connect(self, address, *args, **kwargs):
            BLOCKED_SOCKET_ATTEMPTS.append(repr(address))
            raise AssertionError(
                f"R219 量具禁止出站连接（本件零模型零网络），被挡住的目标：{address!r}")

        def connect_ex(self, address, *args, **kwargs):
            return self.connect(address)

    def _blocked(*args, **kwargs):
        target = args[1] if len(args) > 1 else kwargs.get("address")
        BLOCKED_SOCKET_ATTEMPTS.append(repr(target))
        raise AssertionError(
            f"R219 量具禁止出站连接（本件零模型零网络），被挡住的目标：{target!r}")

    _ORIGINALS["class"] = socket.socket
    socket.socket = _BlockedSocket
    for name in _GUARD_ARMS:
        _ORIGINALS[name] = getattr(socket, name)
        setattr(socket, name, _blocked)


def uninstall_offline_guard() -> None:
    """还原闸门（selfcheck 之外不需要，但留一口，防子进程继承脏桩）。"""
    for name, value in _ORIGINALS.items():
        socket.socket = value if name == "class" else setattr(socket, name, value)


def chromadb_loaded() -> bool:
    return "chromadb" in sys.modules


# ---------------------------------------------------------------------------
# 口径装载（全部复用 R94 常驻件，不另造读法）
# ---------------------------------------------------------------------------

def load_coverage():
    spec = importlib.util.spec_from_file_location("r219_coverage", REPO_ROOT / COVERAGE_REL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def splitter_settings() -> dict:
    """分块常数用 ast 从 `app/rag/retriever.py` 现抠，不手抄。"""
    tree = ast.parse((REPO_ROOT / RETRIEVER_REL).read_bytes().decode("utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "RecursiveCharacterTextSplitter"):
            found = {}
            for keyword in node.keywords:
                try:
                    found[keyword.arg] = ast.literal_eval(keyword.value)
                except ValueError:
                    continue
            if "chunk_size" in found and "chunk_overlap" in found:
                return found
    raise AssertionError(f"没在 {RETRIEVER_REL} 找到 RecursiveCharacterTextSplitter 的分块常数")


def build_index(coverage) -> tuple[list[dict], dict]:
    """把 git 跟踪的 95 篇切成块，产出 BM25Searcher.documents 那一本形状。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    settings = splitter_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings["chunk_size"], chunk_overlap=settings["chunk_overlap"])
    corpus = coverage.load_corpus(REPO_ROOT)
    documents: list[dict] = []
    for label, text in sorted(corpus.items()):
        for ordinal, chunk in enumerate(splitter.split_text(text)):
            if not chunk.strip():
                continue
            documents.append({
                "content": chunk,
                "source": label,
                "chunk_index": ordinal,
                # 权限口径不在本件射程：离线腿 pred=None（见模块头）。生产腿跑时带真 scope。
                "classification": None,
                "department": "",
            })
    meta = {
        "corpus_files": len(corpus),
        "corpus_chars": sum(len(text) for text in corpus.values()),
        "local_chunks": len(documents),
        "chunk_size": settings["chunk_size"],
        "chunk_overlap": settings["chunk_overlap"],
        "production_chunks_reference": 1008,
        "matches_production_index": len(documents) == 1008,
        "label": "local-rebuild",
    }
    return documents, meta


# ---------------------------------------------------------------------------
# 改写替身
# ---------------------------------------------------------------------------

QUESTION_TAIL_WORDS = ("是多少", "多少", "是什么", "哪些", "怎么", "如何", "为什么",
                       "有什么", "需要", "吗", "呢", "？", "?", "的")
CLAUSE_SPLIT = "，,；;、？?"


def _question_terms(text: str) -> list[str]:
    import jieba

    words = [w.strip() for w in jieba.cut(text) if w.strip()]
    return [w for w in words if w not in QUESTION_TAIL_WORDS and len(w) > 1] or words


class StandInRewriter:
    """`QueryRewriter` 的固定替身：形状照 REWRITE_PROMPT 的契约（3 rewrites / 2-3 sub_questions）。

    模式与出处见模块 docstring「改写替身的来源与写法」。它一次模型都不打，
    而且**任何模式都不许往题面之外造新词**（registry 模式用的是仓内登记的词表）。
    """

    def __init__(self, mode: str = "reorder", registry=None):
        self.mode = mode
        self.registry = registry
        self.calls = 0
        self.registry_available = True if mode == "registry" else None

    def _reorder(self, text: str) -> list[str]:
        terms = _question_terms(text)
        variants: list[str] = []
        for size in (len(terms), max(1, len(terms) - 1), max(1, len(terms) // 2)):
            joined = " ".join(terms[:size] or [text])
            if joined and joined not in variants:
                variants.append(joined)
        while len(variants) < 3:
            variants.append(" ".join(reversed(terms)) or text)
        return variants[:3]

    def rewrite(self, question: str) -> dict:
        self.calls += 1
        text = str(question or "").strip()
        rewrites: list[str] = []
        if self.mode == "registry" and self.registry is not None:
            try:
                definition = self.registry(text)
            except Exception:  # noqa: BLE001 - 目录读不动就如实降级
                self.registry_available = False
                definition = None
            if definition is not None:
                terms = [str(term).strip() for term in
                         (getattr(definition, "match_terms", ()) or ()) if str(term).strip()]
                rewrites = [term for term in terms if term != text][:3]
                if not rewrites:
                    self.registry_available = False
        if len(rewrites) < 3:
            for variant in self._reorder(text):
                if variant not in rewrites:
                    rewrites.append(variant)
                if len(rewrites) >= 3:
                    break
        clauses = [part.strip() for part in
                   __import__("re").split(f"[{CLAUSE_SPLIT}]", text) if part.strip()]
        sub_questions = clauses[:2] if len(clauses) >= 2 else [text[:12], text[-12:]]
        return {"rewrites": rewrites[:3], "sub_questions": sub_questions[:3]}


# ---------------------------------------------------------------------------
# 两臂执行（跑的是生产 search() 本体）
# ---------------------------------------------------------------------------

class RecordingSemantic:
    """向量腿替身：记 query、恒回 0 行。生产向量腿需要 embedding 模型调用，本件禁止。"""

    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, k=10, where=None):
        self.queries.append(str(query))
        return []


class RecordingBm25:
    """把生产 BM25Searcher 包一层：只记 query，评分/截断/pred 路径一个字不改。"""

    def __init__(self, inner):
        self.inner = inner
        self.queries: list[str] = []

    def search(self, query, k=10, pred=None):
        self.queries.append(str(query))
        return self.inner.search(query, k=k, pred=pred)


class RankPreservingReranker:
    """名次保持替身（与 tests/test_retrieval_rewrite_tier.py 的 _NoopReranker 同形）。

    真 Cross-Encoder 是本地 sentence-transformers，不在禁止面上，但它一上就变成
    「两臂各自重排一遍」的第二次变量 —— 本件要量的只有召回面，所以钉死为不改名次。
    """

    def __init__(self):
        self.calls = 0

    def rerank(self, query, docs, top_k=5):
        self.calls += 1
        return list(docs)[:top_k]


def clone_documents(documents: list[dict]) -> list[dict]:
    """每臂一套自己的文档 dict。

    🔴 这不是洁癖：`rrf_fusion` 与 `rerank` 会把 `_score` **写回**召回用的那批 dict，
    两臂共用同一份文档对象时，第二臂是从第一臂的累积分起步的 —— 本件的量具第一版就
    栽在这里（09-24 自检出：同一臂连跑两次 top-k 顺序会变）。分开一套对象之后
    `determinism.full_arm_rerun_identical` 才立得住。
    """
    return [dict(row) for row in documents]


def build_pipeline(standin: StandInRewriter, bm25_documents: list[dict]):
    from app.rag import retrieval_pipeline

    pipeline = retrieval_pipeline.RetrievalPipeline.__new__(
        retrieval_pipeline.RetrievalPipeline)
    searcher = retrieval_pipeline.BM25Searcher()
    corpus = [retrieval_pipeline._tokenize_text(row["content"]) for row in bm25_documents]
    searcher.corpus = corpus
    searcher.documents = bm25_documents
    searcher.bm25 = retrieval_pipeline.BM25Okapi(corpus)
    pipeline.bm25 = RecordingBm25(searcher)
    pipeline.semantic = RecordingSemantic()
    pipeline.reranker = RankPreservingReranker()
    pipeline.rewriter = standin
    return pipeline


def arm_tier_argument(tier: str):
    """档位必须以**形参**落到 `search()`。

    读进程环境变量那一条路（`RETRIEVAL_TIER`）在本件里一律算"没分档"：反证钉 ②
    摘的就是这一格（换成恒回 None），两臂会一起退回默认档 full 并逐题相同。
    """
    return tier


def reset_residue_scores(pipeline) -> int:
    """抹掉上一轮写在共享文档 dict 上的 `_score` 残留。

    09-24 自检抓到：`rrf_fusion` 是**累加**着往那批 dict 上写 `_score` 的，所以同一份
    BM25 索引对象上第二次检索同一题，名次会带着上一轮的积分 —— 现网这条路被
    Cross-Encoder 盖掉了（`rerank` 重新赋值 `_score`），而本件恰恰必须把重排钉成
    "不改名次"（不然一次实验同时动两个变量），残留就会露出来。
    每次调用前清一次，两臂才真的只差"发不发改写"这一个变量。
    """
    cleared = 0
    for row in getattr(pipeline.bm25.inner, "documents", []):
        if "_score" in row:
            del row["_score"]
            cleared += 1
    return cleared


def run_arm(pipeline, question: str, tier: str) -> dict:
    pipeline.bm25.queries.clear()
    pipeline.semantic.queries.clear()
    reset_residue_scores(pipeline)
    ranked, rewrites = pipeline.search(
        question, top_k=TOP_K, tier=arm_tier_argument(tier))
    return {
        "queries": list(pipeline.bm25.queries),
        "semantic_queries": list(pipeline.semantic.queries),
        "stand_in_rewrites": list(rewrites or []),
        "hits": [_chunk_id(row) for row in ranked],
    }


def _chunk_id(row: dict) -> str:
    return f"{row.get('source')}#{row.get('chunk_index')}"


# ---------------------------------------------------------------------------
# 金标与差异度量
# ---------------------------------------------------------------------------

def topk_set(arm: dict) -> set:
    """判据 3 的「集合差」比的就是这一格：top-k 的**成员**。

    反证钉 ① 摘的正是它（换成 `{len(hits)}` 这把只看根数的尺），所以它必须是一枚
    单独的、可替换的出口，而不是散在 `compare_rows` 里的四处 `set(...)`。
    """
    return set(arm["hits"])


def compare_rows(rows: list[dict]) -> dict:
    per_question = []
    for row in rows:
        full_ids = row["full"]["hits"]
        fast_ids = row["fast"]["hits"]
        full_set = topk_set(row["full"])
        fast_set = topk_set(row["fast"])
        overlap = len(full_set & fast_set)
        union = full_set | fast_set
        gold = row["gold"]
        recall_full = _recall(full_ids, gold)
        recall_fast = _recall(fast_ids, gold)
        rank_shift = [abs(fast_ids.index(hit) - position)
                      for position, hit in enumerate(full_ids) if hit in fast_ids]
        per_question.append({
            "id": row["id"],
            "same_set": full_set == fast_set,
            "same_order": full_ids == fast_ids,
            "overlap": overlap,
            "jaccard": (overlap / len(union)) if union else 1.0,
            "mean_abs_rank_shift": (statistics.fmean(rank_shift) if rank_shift else 0.0),
            "n_queries_full": len(row["full"]["queries"]),
            "n_queries_fast": len(row["fast"]["queries"]),
            "recall_full": recall_full,
            "recall_fast": recall_fast,
            "delta_recall": (None if recall_full is None or recall_fast is None
                             else recall_fast - recall_full),
            "gold_size": (len(gold) if gold is not None else None),
        })
    scored = [row for row in per_question if row["delta_recall"] is not None]
    deltas = [row["delta_recall"] for row in scored]
    return {
        "per_question": per_question,
        "questions": len(per_question),
        "questions_with_gold": len(scored),
        "same_set": sum(1 for row in per_question if row["same_set"]),
        "same_order": sum(1 for row in per_question if row["same_order"]),
        "differing_set": sum(1 for row in per_question if not row["same_set"]),
        "mean_overlap": statistics.fmean(r["overlap"] for r in per_question),
        "mean_jaccard": statistics.fmean(r["jaccard"] for r in per_question),
        "mean_queries_full": statistics.fmean(r["n_queries_full"] for r in per_question),
        "mean_queries_fast": statistics.fmean(r["n_queries_fast"] for r in per_question),
        "mean_recall_full": statistics.fmean(r["recall_full"] for r in scored) if scored else None,
        "mean_recall_fast": statistics.fmean(r["recall_fast"] for r in scored) if scored else None,
        "mean_delta_recall": statistics.fmean(deltas) if deltas else None,
        "fast_loses_gold": sum(1 for value in deltas if value < 0),
        "fast_gains_gold": sum(1 for value in deltas if value > 0),
        "fast_ties_gold": sum(1 for value in deltas if value == 0),
        "worst_delta_recall": min(deltas) if deltas else None,
    }


def _recall(ids: list[str], gold: set[str] | None) -> float | None:
    if not gold:
        return None
    return len(set(ids) & gold) / len(gold)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run(standin_mode: str, limit: int | None, selfcheck: bool) -> dict:
    coverage = load_coverage()
    rows_spec = coverage.load_rows(REPO_ROOT / coverage.FIXTURE_REL)
    documents, corpus_meta = build_index(coverage)

    try:
        from app.semantics import registry as semantics_registry

        def registry_lookup(question: str):
            return semantics_registry.match_definition(question, None)
    except Exception:  # noqa: BLE001 - 替身降级，不是失败
        registry_lookup = None

    # 两臂各一套管线、各一套文档对象：臂与臂之间不许共享可变状态。
    pipeline_full = build_pipeline(
        StandInRewriter(mode=standin_mode, registry=registry_lookup), clone_documents(documents))
    pipeline_fast = build_pipeline(
        StandInRewriter(mode=standin_mode, registry=registry_lookup), clone_documents(documents))
    install_offline_guard()
    normalize = coverage.normalize

    results: list[dict] = []
    for row in rows_spec[:limit]:
        question = str(row["question"])
        full = run_arm(pipeline_full, question, "full")
        fast = run_arm(pipeline_fast, question, "fast")
        terms = [str(term) for term in (row.get("must_contain") or [])]
        gold = _gold_for(terms, documents, normalize)
        results.append({"id": str(row["id"]), "question": question, "terms": terms,
                        "full": full, "fast": fast, "gold": gold})
    summary = compare_rows(results)
    # 自校：同一臂、同一题、同一管线连跑两次必须逐位相同（不同 ⇒ 状态还在漏，读数作废）
    determinism = {"full_arm_rerun_identical": None, "sampled": 0}
    if results:
        checked = 0
        identical = True
        for row in results[:3]:
            again = run_arm(pipeline_full, row["question"], "full")
            checked += 1
            identical &= (again["hits"] == row["full"]["hits"])
        determinism = {"full_arm_rerun_identical": bool(identical), "sampled": checked}
    summary["determinism"] = determinism
    summary["standin_mode"] = standin_mode
    summary["registry_available"] = any(
        _registry_seen(row) for row in results) if standin_mode == "registry" else None
    summary["corpus"] = corpus_meta
    summary["legs"] = "keyword-only"
    summary["sample"] = {
        "fixture": str(coverage.FIXTURE_REL), "rows": len(rows_spec),
        "used": len(results),
    }
    summary["guard"] = {
        "blocked_socket_attempts": len(BLOCKED_SOCKET_ATTEMPTS),
        "chromadb_imported": chromadb_loaded(),
    }
    if selfcheck:
        _selfcheck(results, summary)
    return {"summary": summary, "rows": results}


def _registry_seen(row: dict) -> bool:
    return bool(row["full"].get("stand_in_rewrites"))


def _gold_for(terms: list[str], documents: list[dict], normalize) -> set[str] | None:
    cleaned = [normalize(str(term)) for term in terms if str(term).strip()]
    if not cleaned:
        return None
    every = {_chunk_id(doc) for doc in documents
             if all(term in normalize(doc["content"]) for term in cleaned)}
    if every:
        return every
    any_one = {_chunk_id(doc) for doc in documents
               if any(term in normalize(doc["content"]) for term in cleaned)}
    return any_one or None


def _selfcheck(results: list[dict], summary: dict) -> None:
    """量具自校准：两臂若一模一样，这把尺就是死的，必须当场炸。"""
    if not results:
        raise AssertionError("selfcheck：零题，尺子没量任何东西")
    if summary["mean_queries_full"] <= summary["mean_queries_fast"]:
        raise AssertionError(
            f"selfcheck：full 臂的 query 根数没有多于 fast 臂"
            f"（{summary['mean_queries_full']} vs {summary['mean_queries_fast']}）"
            "⇒ 档位没生效或被截断吃平，本件不能出数")
    if summary["same_set"] == summary["questions"]:
        raise AssertionError(
            "selfcheck：全部题两臂 top-k 集合相同 ⇒ 要么替身没生效，要么语料太小到量不出差")
    # 🔴 determinism 这一格今天**不当闸**：自检实测同臂连跑两次 top-k 会漂（见模块头
    # 「已知缺口」）。它只进 summary，出数前必须人眼看一次；漂没修好之前，本件的读数
    # 不许直接进验收，这一条写在交回里，不靠这里 raise 冒充已修。
    if summary["guard"]["blocked_socket_attempts"]:
        raise AssertionError("selfcheck：量具起过出站连接")
    # 🔴 不因 `chromadb_imported` 而 raise：在 pytest 里本仓 conftest 的 R134 写回闸门
    # 自己 import 了 chromadb，那枚断言会不会红取决于"在谁的手下跑"，不取决于本件。
    # 这一格只如实进 summary（连同 0 次出站尝试一起），真凭据是那一行 0。


def render(report: dict) -> str:
    out: list[str] = []
    summary = report["summary"]
    push = out.append
    push("=== R219 判据 3 · 两臂检索对照（只跑检索、不跑模型）===")
    push(f"替身模式 = {summary['standin_mode']}   registry 可用 = {summary['registry_available']}")
    push(f"样本 = {summary['sample']['fixture']} {summary['sample']['used']} 题"
         f"（题集共 {summary['sample']['rows']} 题，git 跟踪）")
    corpus = summary["corpus"]
    push(f"语料 = documents/*.txt git 跟踪 {corpus['corpus_files']} 篇 / {corpus['corpus_chars']} 字"
         f" → 本地重建 {corpus['local_chunks']} 枚块"
         f"（chunk_size={corpus['chunk_size']} overlap={corpus['chunk_overlap']}）")
    push(f"🔴 与生产卷 {corpus['production_chunks_reference']} 枚**同口径吗**："
         f"{corpus['matches_production_index']} ⇒ 本读数一律标 corpus={corpus['label']}，"
         "不得当生产召回读数引用")
    push(f"自校 = {summary['determinism']}（同臂连跑两次逐位相同才允许出数）")
    push(f"腿 = {summary['legs']}（向量腿需要 embedding 模型调用，本件禁止面内，恒 0 行）")
    push(f"闸门 = 出站连接尝试 {summary['guard']['blocked_socket_attempts']} 次，"
         f"chromadb import={summary['guard']['chromadb_imported']}")
    push("")
    push("[合计]")
    for key, value in summary.items():
        if key in {"corpus", "sample", "guard", "standin_mode", "registry_available",
                   "legs", "per_question", "determinism"}:
            continue
        push(f"  {key} = {value:.4f}" if isinstance(value, float) else f"  {key} = {value}")
    push("")
    push("[逐题（query 根数是结构账，hits 差是召回账；--json 出全量）]")
    push("  id            qFull qFast same_set jacc recall_full recall_fast delta  gold")
    for row in report["rows"]:
        push(_row_line(row))
    return "\n".join(out)


def _row_line(row: dict) -> str:
    full_ids = row["full"]["hits"]
    fast_ids = row["fast"]["hits"]
    overlap = len(set(full_ids) & set(fast_ids))
    union = set(full_ids) | set(fast_ids)
    gold = row["gold"]
    rf = _recall(full_ids, gold)
    rc = _recall(fast_ids, gold)
    return ("  {id:<14}{qf:>5}{qs:>6}{same:>9}{jac:>8.2f} "
            "{rf:>12}{rc:>12}{delta:>9} {gold}".format(
                id=row["id"], qf=len(row["full"]["queries"]),
                qs=len(row["fast"]["queries"]), same=(set(full_ids) == set(fast_ids)),
                jac=(overlap / len(union)) if union else 1.0,
                rf=("-" if rf is None else f"{rf:.2f}"),
                rc=("-" if rc is None else f"{rc:.2f}"),
                delta=("-" if rf is None or rc is None else f"{rc - rf:+.2f}"),
                gold=("-" if gold is None else len(gold))))


def _reject_inside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if str(resolved).lower().startswith(str(REPO_ROOT).lower()):
        raise AssertionError(f"读数文件不许落在仓内：{resolved}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--standin", choices=("reorder", "registry"), default="reorder")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--selfcheck", action="store_true", help="量具自校准（尺子死了就炸）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default=None, help="落盘路径（必须在仓外）")
    args = parser.parse_args(argv)
    report = run(args.standin, args.limit, args.selfcheck)
    text = (json.dumps(report, ensure_ascii=False, indent=1, default=str) if args.json
            else render(report))
    if args.out:
        target = _reject_inside_repo(Path(os.path.expandvars(args.out)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        print(f"written: {target}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())