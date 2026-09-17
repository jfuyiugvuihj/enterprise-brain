"""R45 Pre-filtering：权限/部门/密级必须在截断、向量打分与重排之前裁掉。

落点是两个已存在的缺陷（docs/handoff/2026-09-15-backend-followup-requests.md:510）：

- 缺陷① ``BM25Searcher.search`` 原先先按全局分数取 Top-k、再套谓词，无权限的 chunk
  白吃名额，受限部门的召回被饿死。本文件用同一份分数把新旧两种截断顺序并排跑出来。
- 缺陷②（纵深防御 + 两腿契约对称）语义腿只有 ``where`` 下推、从不本地复核。按
  2026-09-17 17:11 的更正裁定，这里不声称现行实现正在漏权：Chroma 主路径的下推发生在
  向量计算之前（app/rag/retriever.py:270-276），离线回退同样先裁再算（:165-168）。
  本文件注入一个故意忽略 ``where`` 的假库，断言修复后它的返回会被同一个谓词拦下，
  并断言真库路径的结果一字不变。

判定只有一处事实源：``app/rag/filters.py::DocumentRetrievalScope.allows``。本文件把它
换成带计数的代理，任何一次丢弃都必须能归因到这个谓词上。同时钉住三条不许动的口径：
``pred=None`` 时与改动前逐字一致、语义腿的去重不许丢、R17「空部门行仅
administrator_scope 可见」。全程不建 PersistentClient、不打 Ollama。
"""
import inspect

import numpy as np
import pytest

from app.agents.contracts import Principal
from app.rag import filters as filters_module
from app.rag import retrieval_pipeline
from app.rag.filters import DocumentRetrievalScope, resolve_document_retrieval_scope
from app.rag.retrieval_pipeline import (
    BM25Searcher,
    RetrievalPipeline,
    SemanticSearcher,
    _deduplicate,
    _retain_permitted,
)
from app.rag.retriever import DocumentRetriever

ORIGINAL_ALLOWS = DocumentRetrievalScope.allows


# ==================== 测试替身 ====================

def _chroma_matches(metadata, where):
    """假库里 ``where`` 的求值：复刻 chromadb 的 $and/$in/$eq 与「缺键不匹配」。

    这不是第二套权限规则。生产判定只有 ``DocumentRetrievalScope.allows`` 一处；这里只
    是让假库像真库一样「先按 where 裁候选、再算相似度、最后截 n_results」。
    """
    if not where:
        return True
    if "$and" in where:
        return all(_chroma_matches(metadata, clause) for clause in where["$and"])
    for key, condition in where.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            if "$in" in condition:
                if value not in condition["$in"]:
                    return False
            elif "$eq" in condition:
                if value != condition["$eq"]:
                    return False
        elif value != condition:
            return False
    return True


class _RecordingCollection:
    """Chroma collection 替身：rows 顺序＝相似度降序，并记录每次 query 的输入输出。"""

    ignores_where = False

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, query_embeddings=None, n_results=5, where=None, **kwargs):
        if self.ignores_where:
            scored = list(self.rows)  # 故意不执行下推：模拟会漏权的召回实现
        else:
            scored = [row for row in self.rows if _chroma_matches(row["metadata"], where)]
        self.calls.append(
            {"where": where, "n_results": n_results, "scored_ids": [row["id"] for row in scored]}
        )
        page = scored[:n_results]
        return {
            "documents": [[row["document"] for row in page]],
            "metadatas": [[dict(row["metadata"]) for row in page]],
        }


class _FailOpenCollection(_RecordingCollection):
    """不执行 where 的召回实现：缺陷② 的注入点。"""

    ignores_where = True


class _CountingEmbeddings:
    """只计数，不联网：向量往返次数就是本文件要钉的复杂度指标。"""

    def __init__(self):
        self.calls = 0

    def embed_query(self, text):
        self.calls += 1
        return [0.0] * 8


class _RecordingLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args, **kwargs):
        self.messages.append(str(message))

    def warning(self, message, *args, **kwargs):
        self.messages.append(str(message))

    def error(self, message, *args, **kwargs):
        self.messages.append(str(message))


class _NoKeywordRecall:
    """关键词腿置空，让只看语义腿的用例不被它稀释。"""

    def __init__(self):
        self.calls = []

    def search(self, query, k=10, pred=None):
        self.calls.append({"query": query, "k": k, "pred": pred})
        return []


class _StubRewriter:
    def __init__(self, payload=None):
        self.payload = payload or {"rewrites": [], "sub_questions": []}

    def rewrite(self, question):
        return dict(self.payload)


class _CapturingReranker:
    """记录进 Cross-Encoder 的候选集合：判据要的"重排输入里无权限条目恒为 0"就在这儿看。"""

    def __init__(self):
        self.inputs = []

    def rerank(self, query, docs, top_k=5):
        self.inputs.append(list(docs))
        return docs[:top_k]


class _StubScorer:
    """替掉真的 BM25Okapi：分数由用例给定，被测对象是排序与截断的顺序。"""

    def __init__(self, scores):
        self.scores = np.asarray(scores, dtype=float)

    def get_scores(self, tokens):
        return self.scores


# ==================== 语料与装配 ====================

def _row(row_id, department, classification, filename):
    return {
        "id": row_id,
        "document": f"[{row_id}] 制度正文",
        "metadata": {
            "filename": filename,
            "chunk_index": 0,
            "classification": classification,
            "department": department,
        },
    }


def _library():
    """11 条按相似度降序排列的 chunk。

    前 8 条属于 hr：对 finance / 2 级账号无权限，却恰好占满全局 Top-8；第 9、10 条才是
    它能读的；第 11 条是空部门行（R17 fail-closed 的钉子户）。
    """
    rows = [_row(f"hr-{i}", "hr", 1, "hr-policy.txt") for i in range(8)]
    rows.append(_row("fin-1", "finance", 1, "finance-policy.txt"))
    rows.append(_row("fin-2", "finance", 2, "finance-secret.txt"))
    rows.append(_row("nodept", "", 1, "legacy-policy.txt"))
    return rows


def _descending_scores(count):
    return [float(count - index) for index in range(count)]


def _staff(department="finance", clearance=2, **extra):
    return Principal(
        user_id="u-r45",
        username="r45-staff",
        permissions=["document.read"],
        department=department,
        clearance=clearance,
        **extra,
    )


def _admin():
    return Principal.from_user({"id": "u-r45-admin", "username": "r45-admin", "role": "admin"})


def _wire(rows, *, collection_cls=_RecordingCollection, keyword=None, rewriter=None, **collection_kwargs):
    """真 ``DocumentRetriever.search`` + 真 ``SemanticSearcher`` + 真 ``RetrievalPipeline.search``。

    只换掉向量库与 embedding：``DocumentRetriever.__new__`` 不跑 ``__init__``，因此既不
    ``os.makedirs("./chroma_db")`` 也不建 ``PersistentClient``，更不打 Ollama。
    """
    retriever = DocumentRetriever.__new__(DocumentRetriever)
    collection = collection_cls(rows, **collection_kwargs)
    retriever.collection = collection
    retriever.embedding = _CountingEmbeddings()

    semantic = SemanticSearcher.__new__(SemanticSearcher)
    semantic.retriever = retriever

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.semantic = semantic
    pipeline.bm25 = keyword or _NoKeywordRecall()
    pipeline.rewriter = rewriter or _StubRewriter()
    pipeline.reranker = _CapturingReranker()
    return pipeline, collection


def _keyword_leg(rows, scores=None):
    """把同一份语料喂给真 ``BM25Searcher.search``，分数默认按 rows 顺序严格降序。"""
    rows = list(rows)
    searcher = BM25Searcher()
    searcher.bm25 = _StubScorer(scores or _descending_scores(len(rows)))
    searcher.documents = [
        {
            "content": row["document"],
            "source": row["metadata"]["filename"],
            "chunk_index": row["metadata"]["chunk_index"],
            "classification": row["metadata"]["classification"],
            "department": row["metadata"]["department"],
        }
        for row in rows
    ]
    return searcher


def _reference_bm25_search(scores, documents, k, pred=None):
    """改动前的截断顺序，逐字搬来当对照：先取全局 Top-k，再套谓词。"""
    top_indices = np.argsort(scores)[::-1][:k]
    hits = [documents[i] for i in top_indices if scores[i] > 0]
    if pred:
        hits = [d for d in hits if pred(d)]
    return hits


def _foreign(scope, hits):
    """用事实源自己的谓词回查：应当被拦下却活下来的条目。"""
    return [hit for hit in hits if not ORIGINAL_ALLOWS(scope, hit)]


def _ids_of(hits, rows):
    by_content = {row["document"]: row["id"] for row in rows}
    return [by_content.get(hit["content"], "?") for hit in hits]


def _identity(hit):
    return (hit.get("source"), hit.get("chunk_index"))

def _row_hit(row):
    """把一行语料变成 ``DocumentRetriever.search`` 出口那种命中字典。"""
    metadata = row["metadata"]
    return {
        "content": row["document"],
        "source": metadata["filename"],
        "chunk_index": metadata["chunk_index"],
        "classification": metadata["classification"],
        "department": metadata["department"],
    }


def _where_values(where, field):
    """摊开 $and 取某个字段的 $in 取值：断言"谓词里到底写了哪些部门/密级"。"""
    values = []
    for key, condition in (where or {}).items():
        if key == "$and":
            for clause in condition:
                values += _where_values(clause, field)
        elif key == field and isinstance(condition, dict):
            values += list(condition.get("$in") or [])
    return values


def _where_fields(where):
    fields = set()
    if not isinstance(where, dict):
        return fields
    for key, condition in where.items():
        if key.startswith("$"):
            if isinstance(condition, list):
                for item in condition:
                    fields |= _where_fields(item)
            continue
        fields.add(key)
    return fields


# ============ 判据①(a)：谓词在向量计算之前下推，越权条目不入候选 ============

def test_scope_predicate_reaches_the_store_before_vectors_are_scored():
    rows = _library()
    pipeline, collection = _wire(rows)
    scope = resolve_document_retrieval_scope(_staff())

    docs, rewrites = pipeline.search_for_principal("制度", _staff(), top_k=5, tier="fast")

    assert rewrites == []
    assert len(collection.calls) == 1
    call = collection.calls[0]
    assert call["where"] == scope.filters, "下推的谓词必须就是 scope 自己那份，不得另造"
    assert call["where"], "权限谓词不许丢，否则退化成召回之后再筛"
    assert _where_fields(call["where"]) >= {"classification", "department"}
    # 真正参与向量相似度计算的候选：无权限条目一条都不在其中
    assert call["scored_ids"] == ["fin-1", "fin-2"]
    assert call["n_results"] == 8, "不得靠多扫向量换安全"
    assert _ids_of(docs, rows) == ["fin-1", "fin-2"]
    assert _foreign(scope, pipeline.reranker.inputs[0]) == []


def test_the_real_store_path_loses_nothing_to_the_local_recheck(monkeypatch):
    """真库路径一字不变：下推已生效，本地复核一步都不许多裁、也不多打日志。"""
    logger = _RecordingLogger()
    monkeypatch.setattr(retrieval_pipeline, "logger", logger)
    rows = _library()
    pipeline, collection = _wire(rows)

    docs, _ = pipeline.search_for_principal("制度", _staff(), top_k=5, tier="fast")

    assert [call["scored_ids"] for call in collection.calls] == [["fin-1", "fin-2"]]
    assert _ids_of(docs, rows) == ["fin-1", "fin-2"]
    assert [message for message in logger.messages if "权限预过滤" in message] == []


# ============ 判据①(b)／缺陷②：不执行 where 的召回实现被同一谓词拦在融合前 ============

def test_a_store_that_ignores_where_cannot_reach_the_fusion_or_the_reranker(monkeypatch):
    rows = _library()
    logger = _RecordingLogger()
    monkeypatch.setattr(retrieval_pipeline, "logger", logger)
    pipeline, collection = _wire(rows, collection_cls=_FailOpenCollection)
    scope = resolve_document_retrieval_scope(_staff())

    docs, _ = pipeline.search_for_principal("制度", _staff(), top_k=5, tier="fast")

    assert collection.calls[0]["scored_ids"][:8] == [f"hr-{i}" for i in range(8)]
    assert pipeline.reranker.inputs == [[]], "无权限候选不得进入融合与重排"
    assert docs == []
    assert [message for message in logger.messages if "权限预过滤" in message], "裁掉必须留痕"
    assert _foreign(scope, pipeline.reranker.inputs[0]) == []


def test_the_local_recheck_is_a_no_op_without_a_predicate():
    """pred=None 时原样返回同一个列表对象：无权限上下文的调用方行为逐字不变。"""
    hits = [{"content": "a", "classification": 3, "department": "hr"}]
    assert _retain_permitted(hits, None) is hits
    assert _retain_permitted(hits, False) is hits


# ============ 判据① 补条（验收意见）：语义腿的去重不许丢 ============

def test_semantic_recall_is_still_deduplicated_before_the_reranker():
    """多路查询召回到同一 chunk 时，融合之前的语义列表必须已去过重（验收意见补条）。

    语义腿是 1 个原查询 + 最多 4 个改写/子问题（retrieval_pipeline.py:351），路与路之间
    高度重叠。丢掉去重不会让 fused 变长（RRF 自己按 content 前 120 字符聚合），但它会让
    同一条 chunk 在同一列表里占多个位次、反复累加 reciprocal-rank，把只被关键词腿召回的
    来源压到后面。这里用一次可观察的名次翻转钉住：去过重时 E 排第二，丢掉去重时 X 反超。
    """
    semantic_rows = [_row("D", "finance", 1, "d.txt"), _row("X", "finance", 1, "x.txt")]
    keyword_rows = [_row("E", "finance", 1, "e.txt")]
    all_rows = semantic_rows + keyword_rows
    rewriter = _StubRewriter({"rewrites": ["改写一"], "sub_questions": []})
    pipeline, collection = _wire(semantic_rows, keyword=_keyword_leg(keyword_rows), rewriter=rewriter)

    docs, _ = pipeline.search_for_principal("制度", _staff(), top_k=2, tier="full")

    assert len(collection.calls) == 2, "本用例要的就是两路查询召回同一批 chunk"
    rerank_input = pipeline.reranker.inputs[0]
    # 护栏断言（非承重：fused 是 dict 键序列，恒无重复）\n    assert len({_identity(hit) for hit in rerank_input}) == len(rerank_input)
    # D 被两路查询召回、X 也是，E 只有关键词腿给过：去过重后 D 与 E 同分、按插入序排在前二
    assert _ids_of(rerank_input, all_rows) == ["D", "E", "X"]
    assert _ids_of(docs, all_rows) == ["D", "E"]


class _PagedCollection(_FailOpenCollection):
    """按调用次序交出预置页，并且不执行 where：用来造"召回路径交回 store 没裁掉的 chunk"。"""

    def __init__(self, rows, pages):
        super().__init__(rows)
        self.pages = list(pages)

    def query(self, query_embeddings=None, n_results=5, where=None, **kwargs):
        page = self.pages[len(self.calls) % len(self.pages)]
        self.calls.append(
            {"where": where, "n_results": n_results, "scored_ids": [row["id"] for row in page]}
        )
        return {
            "documents": [[row["document"] for row in page]],
            "metadatas": [[dict(row["metadata"]) for row in page]],
        }


def _fuse_without_deduplication(*argument_lists):
    """主树 :375 的语义基线：先 _deduplicate 再进 rrf_fusion。"""
    return [list(_deduplicate(items)) for items in argument_lists]


def test_the_semantic_list_entering_rrf_carries_no_repeated_keys(monkeypatch):
    """结构断言（最硬、不依赖浮点）：进 rrf_fusion 的语义列表内 content[:120] 不许重复。

    语义腿最多 5 路查询（retrieval_pipeline.py:351），路与路之间高度重叠；rrf_fusion 以
    content[:120] 为键累加 1/(k+rank)，同一列表里出现 n 次就累加 n 次（不当提权），而且
    重复条目照样占 rank 序号，把其后唯一条目的名次推大（名次污染）。输出长度与重复无关，
    所以只能这样直接看传进去的实参。
    """
    captured = []
    real_fusion = retrieval_pipeline.rrf_fusion

    def spy(ranked_lists, k=60):
        captured.append([list(items) for items in ranked_lists])
        return real_fusion(ranked_lists, k)

    monkeypatch.setattr(retrieval_pipeline, "rrf_fusion", spy)
    semantic_rows = [_row("D", "finance", 1, "d.txt"), _row("X", "finance", 1, "x.txt")]
    keyword_rows = [_row("E", "finance", 1, "e.txt")]
    rewriter = _StubRewriter({"rewrites": ["改写一"], "sub_questions": []})
    pipeline, collection = _wire(semantic_rows, keyword=_keyword_leg(keyword_rows), rewriter=rewriter)

    pipeline.search_for_principal("制度", _staff(), top_k=2, tier="full")

    assert len(collection.calls) == 2, "本用例要的就是两路查询召回同一批 chunk"
    semantic_list, keyword_list = captured[0]
    assert len(semantic_list) == 2, "两路查询各召回 2 条，去过重之后只剩 2 条"
    assert len({_identity(hit) for hit in semantic_list}) == len(semantic_list)
    assert len(keyword_list) == 1


def test_the_fused_order_matches_the_unscoped_baseline_when_queries_overlap():
    """排序断言：pred=None 时融合顺序必须等于主树基线，重复命中不许把谁抬上去。

    D、X 被两路查询各召回一次，E 只被关键词召回一次。去过重时 D 与 E 同分（都是某个列表
    的第 1 名），按插入序排成 D, E, X；丢掉去重时 D、X 各自累加两次，E 被挤到最后。
    """
    semantic_rows = [_row("D", "finance", 1, "d.txt"), _row("X", "finance", 1, "x.txt")]
    keyword_rows = [_row("E", "finance", 1, "e.txt")]
    all_rows = semantic_rows + keyword_rows
    rewriter = _StubRewriter({"rewrites": ["改写一"], "sub_questions": []})
    pipeline, collection = _wire(semantic_rows, keyword=_keyword_leg(keyword_rows), rewriter=rewriter)

    docs, _ = pipeline.search("制度", top_k=3, where=None, pred=None, tier="full")

    assert len(collection.calls) == 2
    baseline = retrieval_pipeline.rrf_fusion(
        _fuse_without_deduplication(
            [_row_hit(semantic_rows[0]), _row_hit(semantic_rows[1])] * 2,
            [_row_hit(keyword_rows[0])],
        )
    )
    assert _ids_of(pipeline.reranker.inputs[0], all_rows) == _ids_of(baseline, all_rows)
    assert _ids_of(docs, all_rows) == ["D", "E", "X"]


def _shared_prefix_content(tail):
    """两条 chunk 的前 120 个字符完全相同、正文其余部分不同。

    这不是边角构造：_deduplicate 与 rrf_fusion 用的是同一个键 content[:120]
    （retrieval_pipeline.py:455 对 :246），长文档同开头（同一份制度总则挂不同部门后缀）
    在真实语料里就是常态，于是它们会撞在同一个去重键上。
    """
    return "财务制度总则" + ("补" * 200) + tail


def test_the_predicate_runs_before_deduplication_so_a_valid_copy_is_not_lost():
    """顺序断言：先过滤、后去重。反序会误拒——合法文档凭空消失。

    (a) 挡误拒：同一个去重键下两份拷贝，首份缺 classification 键、次份齐键且合法。
        _deduplicate 保留的是**首次出现**那一份（:455），allows 对缺 classification 直接
        False（filters.py:44-46，int(None) 抛 TypeError 被 except 掉）。所以"先去重"会把
        合法那份连同它的键一起丢掉，剩下的缺键份再被裁 => 整条消失。先过滤没这个问题。
    (b) 挡放行：过滤之后不许有任何 allows 判 False 的条目活着进融合。
    选型还顺带对齐了 BM25 腿既有顺序：search 内部过 pred，:402 再去重，两腿契约对称。
    """
    rows = _library()
    scope = resolve_document_retrieval_scope(_staff("finance", 2))
    broken = {"content": _shared_prefix_content("（无密级遗留份）"),
              "source": "a.txt", "chunk_index": 0, "department": "finance"}
    good = {"content": _shared_prefix_content("（有密级新份）"), "source": "b.txt",
            "chunk_index": 1, "classification": 1, "department": "finance"}
    copies = [broken, good]

    assert broken["content"][:120] == good["content"][:120], "两份必须撞在同一个去重键上"
    assert ORIGINAL_ALLOWS(scope, broken) is False
    assert ORIGINAL_ALLOWS(scope, good) is True
    # 先过滤后去重：合法那份存活；反序：合法那份连同键一起消失
    assert _deduplicate(_retain_permitted(copies, scope.allows)) == [good]
    assert _retain_permitted(_deduplicate(copies), scope.allows) == [], "反序即误拒，这条锁住选型"
    # (b) 两个方向都不许放行越权条目
    assert _foreign(scope, _deduplicate(_retain_permitted(copies, scope.allows))) == []
    assert _foreign(scope, _retain_permitted(_deduplicate(copies), scope.allows)) == []

    broken_page = {"id": "broken", "document": broken["content"],
                   "metadata": {"filename": "a.txt", "chunk_index": 0, "department": "finance"}}
    good_page = {"id": "good", "document": good["content"],
                 "metadata": {"filename": "b.txt", "chunk_index": 1,
                              "classification": 1, "department": "finance"}}
    rewriter = _StubRewriter({"rewrites": ["改写一"], "sub_questions": []})
    pipeline, collection = _wire(
        rows, collection_cls=_PagedCollection, pages=[[broken_page], [good_page]],
        keyword=_NoKeywordRecall(), rewriter=rewriter,
    )

    docs, _ = pipeline.search_for_principal("制度", _staff("finance", 2), top_k=5, tier="full")

    assert len(collection.calls) == 2, "两份拷贝分别由两路查询交回"
    assert len(docs) == 1, "同一个去重键下只许活一份"
    # 先过滤：缺键那份先出局，轮到齐键的 b.txt。若换成先去重，占住键位的是 a.txt——它在
    # 向量库出口被 app/rag/retriever.py:286 补成 classification=1，反而蒙混过关：这就是
    # 顺序选错时"合法那份消失、被补过键的那份留下"的具体形态。
    assert docs[0]["source"] == "b.txt", "反序会让缺键那份占住键位"
    assert _foreign(scope, docs) == []


def test_unscoped_semantic_recall_is_byte_for_byte_the_mainline_behaviour():
    """pred=None 时 _retain_permitted 原样返回同一个列表，整步逐字等价于主树 :375。"""
    rows = _library()
    recalled = [_row_hit(row) for row in rows]
    duplicated = recalled + recalled

    assert _retain_permitted(duplicated, None) is duplicated
    assert _deduplicate(_retain_permitted(duplicated, None)) == _deduplicate(duplicated)
    assert _deduplicate(_retain_permitted(duplicated, False)) == _deduplicate(duplicated)

    pipeline, collection = _wire(rows)
    scoped, _ = pipeline.search_for_principal("制度", _staff(), top_k=5, tier="fast")
    pipeline2, _ = _wire(rows)
    unscoped, _ = pipeline2.search("制度", top_k=5, where=None, pred=None, tier="fast")

    assert len(collection.calls) == 1
    assert scoped, "带 scope 的召回不为空"
    # 无权限上下文时：取数宽度、进融合的候选集合、最终 top_k 全部与改动前一致
    assert len(pipeline2.reranker.inputs[0]) == 8, "全局 Top-8 一条不少地进融合"
    assert len(unscoped) == 5
    assert _ids_of(pipeline2.reranker.inputs[0], rows) == [f"hr-{i}" for i in range(8)]


# ============ 判据②：BM25 先筛后取（召回饥饿的新旧对照） ============

def test_blocked_candidates_no_longer_eat_the_top_k_slots():
    rows = _library()
    documents = _keyword_leg(rows).documents
    scores = _descending_scores(len(rows))
    scope = resolve_document_retrieval_scope(_staff("finance", 2))

    # 前提：全局前 8 名全是 hr，finance 账号一条都读不到
    assert [_identity(hit) for hit in documents[:8]][0] == ("hr-policy.txt", 0)
    assert _reference_bm25_search(scores, documents, 8, scope.allows) == [], "旧口径被饿死"

    hits = _keyword_leg(rows).search("制度", k=8, pred=scope.allows)

    assert [hit["content"] for hit in hits] == ["[fin-1] 制度正文", "[fin-2] 制度正文"]
    assert _foreign(scope, hits) == []


def test_strict_scope_still_recalls_something_through_both_legs():
    """严格权限下召回不为空（计划书 R45 判据②），且两腿结果都干净。"""
    rows = _library()
    pipeline, collection = _wire(
        rows, keyword=_keyword_leg(rows, scores=_descending_scores(len(rows)))
    )
    scope = resolve_document_retrieval_scope(_staff("finance", 1))

    docs, _ = pipeline.search_for_principal("制度", _staff("finance", 1), top_k=5, tier="fast")

    assert docs, "先裁再算不能让受限账号一条都检不到"
    assert _ids_of(docs, rows) == ["fin-1"]
    assert _foreign(scope, pipeline.reranker.inputs[0]) == []


@pytest.mark.parametrize("k", [0, 1, 2, 3, 8, 10, 11, 20])
def test_bm25_matches_the_old_implementation_when_no_predicate_is_given(k):
    """无权限谓词时新实现与改动前逐字一致（含并列分、负分、全 0 分、k 越界）。"""
    rows = _library()
    searcher = _keyword_leg(rows)
    for scores in (
        _descending_scores(len(rows)),
        [1.0] * len(rows),
        [0.0] * len(rows),
        [-1.0, 2.0, 0.0, 5.0, -3.0, 1.0, 0.0, 4.0, 0.5, -0.5, 3.0],
        list(reversed(_descending_scores(len(rows)))),
    ):
        searcher.bm25 = _StubScorer(scores)
        assert searcher.search("制度", k=k) == _reference_bm25_search(
            np.asarray(scores, dtype=float), searcher.documents, k
        )


def test_bm25_k_zero_still_returns_nothing():
    searcher = _keyword_leg(_library())
    assert searcher.search("制度", k=0) == []
    assert searcher.search("制度", k=0, pred=lambda hit: True) == []


# ============ 判据②：跨部门/跨密级 principal 下无权限条目恒为 0 ============

@pytest.mark.parametrize(
    "principal_factory, expected_ids",
    [
        (lambda: _staff("finance", 1), ["fin-1"]),
        (lambda: _staff("finance", 2), ["fin-1", "fin-2"]),
        (lambda: _staff("hr", 2), [f"hr-{i}" for i in range(8)]),
        (lambda: _staff("finance", 2, department_ids=["shared-services"]), ["fin-1", "fin-2"]),
        (_admin, [f"hr-{i}" for i in range(8)]),
    ],
)
def test_no_unauthorized_document_survives_either_leg(principal_factory, expected_ids, monkeypatch):
    rows = _library()
    principal = principal_factory()
    scope = resolve_document_retrieval_scope(principal)
    pipeline, collection = _wire(
        rows, keyword=_keyword_leg(rows, scores=_descending_scores(len(rows)))
    )
    audit_calls = _capture_audit(monkeypatch)

    docs, _ = pipeline.search_for_principal("制度", principal, top_k=5, tier="fast")

    assert [call[0][3:5] for call in audit_calls] == (
        [("document_retrieval", "administrator_scope")]
        if scope.departments is None
        else []
    ), "只有管理员越部门读取才留审计，且这条链不受预过滤影响"
    rerank_input = pipeline.reranker.inputs[0]
    assert _foreign(scope, rerank_input) == []
    assert _foreign(scope, docs) == []
    permitted = set(expected_ids)
    assert {hit_id for hit_id in _ids_of(rerank_input, rows)} <= permitted
    assert _ids_of(docs, rows) == expected_ids[: len(docs)]
    assert set(_ids_of(docs, rows)) <= permitted


def _capture_audit(monkeypatch):
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(filters_module, "record_audit", capture)
    return calls


def test_the_only_judgment_is_the_scope_predicate_itself(monkeypatch):
    """每一次接受/拒绝都必须能归因到 filters.py 的那个谓词上（单一事实源）。"""
    seen = []

    def spy(self, hit):
        verdict = ORIGINAL_ALLOWS(self, hit)
        seen.append((hit.get("source"), hit.get("classification"), verdict))
        return verdict

    monkeypatch.setattr(DocumentRetrievalScope, "allows", spy)
    rows = _library()
    pipeline, _collection = _wire(
        rows, keyword=_keyword_leg(rows, scores=_descending_scores(len(rows)))
    )
    scope = resolve_document_retrieval_scope(_staff("finance", 2))

    docs, _ = pipeline.search_for_principal("制度", _staff("finance", 2), top_k=5, tier="fast")

    assert seen, "两腿的候选都要经过 allows"
    assert {row[0] for row in seen if row[2] is False} == {"hr-policy.txt", "legacy-policy.txt"}
    assert {row[0] for row in seen if row[2] is True} == {"finance-policy.txt", "finance-secret.txt"}
    assert _foreign(scope, docs) == []
    assert _ids_of(docs, rows) == ["fin-1", "fin-2"]


def test_the_pipeline_holds_no_second_scope_rule():
    """管线里不许出现第二个部门/密级判定：它只许调用注入进来的谓词。"""
    source = inspect.getsource(retrieval_pipeline)

    for token in (
        "clearance",
        "is_administrator",
        "ROLE_CLEARANCE",
        "classification_levels",
        "administrator_scope",
        "$in",
    ):
        assert token not in source, f"retrieval_pipeline.py 里出现了 {token!r}：判定必须留在 filters.py"


# ============ 判据④：fail-closed 口径不许松动 ============

def test_empty_department_rows_stay_visible_only_to_the_administrator_scope():
    staff_scope = resolve_document_retrieval_scope(_staff("finance", 2))
    admin_scope = resolve_document_retrieval_scope(_admin())
    legacy = {"content": "遗留正文", "source": "legacy.txt", "chunk_index": 0,
              "classification": 1, "department": ""}

    assert staff_scope.allows(legacy) is False
    assert admin_scope.allows(legacy) is True
    # 预过滤只是"同一个判定作用于列表"，不许改变空部门行的可见性
    assert _retain_permitted([legacy], staff_scope.allows) == []
    assert _retain_permitted([legacy], admin_scope.allows) == [legacy]
    assert _retain_permitted([legacy], None) is not None
    # 下推给向量库的谓词里也不许出现空部门：口径必须是"只列有名字的部门"
    assert "" not in staff_scope.departments
    assert "" not in _where_values(staff_scope.filters, "department")
    assert set(_where_values(staff_scope.filters, "classification")) == {1, 2}
    assert _where_values(admin_scope.filters, "department") == []


def test_a_chunk_without_usable_classification_is_never_visible():
    staff_scope = resolve_document_retrieval_scope(_staff("finance", 2))
    admin_scope = resolve_document_retrieval_scope(_admin())
    for hit in (
        {"content": "x", "department": "finance"},
        {"content": "x", "department": "finance", "classification": None},
        {"content": "x", "department": "finance", "classification": "绝密"},
    ):
        assert ORIGINAL_ALLOWS(staff_scope, hit) is False
        assert ORIGINAL_ALLOWS(admin_scope, hit) is False
        assert _retain_permitted([hit], staff_scope.allows) == []


# ============ 判据⑤：纯内存谓词、零额外向量往返、候选量只减不增 ============

def test_prefiltering_adds_no_vector_roundtrips():
    """谓词在内存里跑：向量往返次数只跟查询数走，与候选条数无关（不是 N+1）。"""
    small = _library()
    large = _library() * 4
    rewriter = _StubRewriter(
        {"rewrites": ["改写一", "改写二", "改写三"], "sub_questions": ["子问题一"]}
    )

    observed = []
    for rows in (small, large):
        pipeline, collection = _wire(rows, rewriter=_StubRewriter(rewriter.payload))
        docs, _ = pipeline.search_for_principal("制度", _staff(), top_k=5, tier="full")
        embeddings = pipeline.semantic.retriever.embedding
        observed.append(
            {
                "rows": len(rows),
                "store_queries": len(collection.calls),
                "embeddings": embeddings.calls,
                "n_results": {call["n_results"] for call in collection.calls},
                "keyword_searches": len(pipeline.bm25.calls) if hasattr(pipeline.bm25, "calls") else 0,
                "rerank_calls": len(pipeline.reranker.inputs),
            }
        )
        assert docs

    assert [case["store_queries"] for case in observed] == [5, 5], "候选翻 4 倍，向量检索次数不变"
    assert [case["embeddings"] for case in observed] == [5, 5], "每发查询一次 embedding，不多不少"
    assert all(case["n_results"] == {8} for case in observed), "取数宽度没有为安全放大"
    assert all(case["rerank_calls"] == 1 for case in observed), "重排只被调用一次"


def test_the_prefilter_shrinks_the_rerank_candidate_set():
    """过滤是减少候选：同一条查询，带 scope 时进重排的更少，取数宽度不变。"""
    rows = _library()

    unscoped, unscoped_collection = _wire(rows)
    unscoped.search("制度", top_k=5, where=None, pred=None, tier="fast")

    scoped, scoped_collection = _wire(rows)
    scoped.search_for_principal("制度", _staff(), top_k=5, tier="fast")

    assert len(unscoped.reranker.inputs[0]) == 8
    assert len(scoped.reranker.inputs[0]) == 2
    assert scoped_collection.calls[0]["n_results"] == unscoped_collection.calls[0]["n_results"] == 8


def test_the_recheck_runs_in_memory_only(monkeypatch):
    """谓词判定过程中一次库调用都不许发生：逐条判定＝纯内存。"""
    rows = _library()
    pipeline, collection = _wire(rows, collection_cls=_FailOpenCollection)

    def explode(*args, **kwargs):
        raise AssertionError("预过滤不许逐条回查向量库（N+1）")

    monkeypatch.setattr(type(collection), "query", explode)
    scope = resolve_document_retrieval_scope(_staff())
    candidates = [
        {"content": row["document"], "source": row["metadata"]["filename"], "chunk_index": 0,
         "classification": row["metadata"]["classification"],
         "department": row["metadata"]["department"]}
        for row in rows
    ]

    assert _ids_of(_retain_permitted(candidates, scope.allows), rows) == ["fin-1", "fin-2"]