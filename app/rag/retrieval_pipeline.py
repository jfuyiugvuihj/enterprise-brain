"""
Agentic RAG 检索管线：
查询改写/词表扩展 → 多路召回(语义+BM25+子问题) → 权限预过滤 → RRF 融合 → Cross-Encoder 重排
"""
import json
import os
import re
import threading
import urllib.request
import hashlib
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
import numpy as np
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from rank_bm25 import BM25Okapi
except ModuleNotFoundError:  # pragma: no cover
    class BM25Okapi:
        def __init__(self, corpus):
            self.corpus = corpus

        def get_scores(self, tokens):
            query_tokens = set(tokens)
            return np.array(
                [sum(token in query_tokens for token in document) for document in self.corpus],
                dtype=float,
            )
try:
    from sentence_transformers import CrossEncoder
except ModuleNotFoundError:  # pragma: no cover
    CrossEncoder = None
from app.common.model_budget import OUTPUT_TRUNCATED_CODE
from app.common.model_handler import ModelHandler, ModelSource, RESPONSE_EMPTY_CODE
from app.common.logger import logger
from app.common.identity import Principal
from app.rag.filters import record_retrieval_scope, resolve_document_retrieval_scope

model = ModelHandler()

# ==================== 查询改写 ====================

#: 可变内容后置（R43a，跟进单 §81 三）。改前 ``{question}`` 夹在两段固定指令**中间**，两次改写
#: 之间字节相同的只有最前面那一句，服务端可复用的前缀短到没有意义。现在固定指令全部在前、
#: 问题本身是整段的最后一枚字节，前缀里既没有时间戳也没有身份。
#: 🔴 JSON 契约一字未动：仍是 3 枚 rewrites、2-3 枚 sub_questions，``{{ }}`` 转义原样保留；
#: 本常量也仍是一枚单独的字符串字面量，``scripts/perf_probe_rounds.py`` 与
#: ``scripts/perf_probe_prodpath.py`` 按 AST 取字面量的读法不受影响。
REWRITE_PROMPT = """你是检索专家。对用户问题生成 3 个不同角度的改写版本，并拆成 2-3 个子问题。

返回 JSON（不要其他内容）：
{{"rewrites":["改写1","改写2","改写3"],"sub_questions":["子问题1","子问题2","子问题3"]}}

用户问题: {question}"""


# ==================== 查询改写档位 ====================

TIER_ENV = "RETRIEVAL_TIER"
TIER_FAST = "fast"
TIER_ADAPTIVE = "adaptive"
TIER_FULL = "full"
DEFAULT_TIER = TIER_FULL
REWRITE_TIERS = (TIER_FAST, TIER_ADAPTIVE, TIER_FULL)

# 现场只会写档位名，因此容错少量同义写法；其余拼法一律当作"不认识"处理。
TIER_ALIASES = {
    "off": TIER_FAST,
    "lean": TIER_FAST,
    "on": TIER_FULL,
    "standard": TIER_FULL,
    "default": TIER_FULL,
}


# adaptive 档的触发门槛：问题看得出含多个意图，才值得为改写付一次阻塞往返。
ADAPTIVE_REWRITE_MIN_CHARS = 24
ADAPTIVE_REWRITE_MIN_CLAUSES = 2
_CLAUSE_SEPARATORS = "，,；;、？?"


def resolve_rewrite_tier(tier: str | None = None) -> str:
    """把显式档位或环境变量归一化成 fast / adaptive / full。

    默认档必须是"保持现状"：环境变量未设、值为空、拼写写错、值本身连字符串都读不出来，
    全部落到 ``full``。少做一次改写是检索质量上的行为变化，不能被一个打错的配置值静默
    开启。
    """
    raw = tier if tier is not None else os.getenv(TIER_ENV, "")
    try:
        normalized = str(raw or "").strip().lower().replace("_", "-")
    except Exception:  # pragma: no cover - 防御 __str__ 自己抛错的对象
        normalized = ""
    if not normalized:
        return DEFAULT_TIER
    if normalized in REWRITE_TIERS:
        return normalized
    aliased = TIER_ALIASES.get(normalized)
    if aliased:
        return aliased
    logger.warning(f"未知检索档位 {raw!r}：回退到 {DEFAULT_TIER}（保持改写）")
    return DEFAULT_TIER


def should_rewrite_query(query: str, tier: str | None = None) -> bool:
    """本次检索要不要付出一次阻塞的查询改写往返。"""
    resolved = resolve_rewrite_tier(tier)
    if resolved == TIER_FAST:
        return False
    if resolved == TIER_ADAPTIVE:
        return _looks_multi_intent(query)
    return True


def _looks_multi_intent(query: str) -> bool:
    """粗略判断问题是否含多个意图：够长，或带两个以上子句/问号分隔符。"""
    text = str(query or "").strip()
    if not text:
        return False
    if len(text) >= ADAPTIVE_REWRITE_MIN_CHARS:
        return True
    return sum(text.count(ch) for ch in _CLAUSE_SEPARATORS) >= ADAPTIVE_REWRITE_MIN_CLAUSES


#: 正文里有 JSON 读不出来的稳定码。它必须与下面两枚「没有正文」的码分得开：2026-09-18 晚
#: 现网每一条提问都刷同一句「查询改写失败，返回原始问题」，而「模型没吐出正文」（思维链
#: 吃掉预算）与「模型吐了正文但读不懂」（提示词或模型的问题）是两个完全不同的现场。
REWRITE_PAYLOAD_UNPARSEABLE_CODE = "rewrite_payload_unparseable"

#: 可能裹住 JSON 的外壳。取值顺序就是历史顺序：先按改动前的写法剥一次，所以改动前能解析的
#: 正文在这里走的还是同一条分支；多出来的只有「围栏没写语言名」这一种。
REWRITE_PAYLOAD_FENCE_PREFIXES = ("```json", "```")

#: 「没有可用正文」的两枚码，按 ERROR 记账。改前它们是 WARNING 一句带过，于是「改写从来没
#: 生效过」和「改写被档位关掉」在看板上长得一模一样——这正是本单要断掉的静默。
REWRITE_EMPTY_ANSWER_CODES = frozenset({OUTPUT_TRUNCATED_CODE, RESPONSE_EMPTY_CODE})


def _strip_rewrite_fence(cleaned: str) -> str:
    """剥掉 markdown 围栏，剥不动就原样返回（改动前的行为）。"""
    for marker in REWRITE_PAYLOAD_FENCE_PREFIXES:
        if cleaned.startswith(marker):
            cleaned = cleaned[len(marker):]
            break
    return cleaned.removesuffix("```").strip()


def _rewrite_payload_candidates(text: str) -> list[str]:
    """这份接口见过的全部正文形状，从最字面到最宽容。

    第 1 条就是改动前那一行的结果；第 2 条只放宽「JSON 前后被塞了一句话」这一种，因为本地
    模型确实会把 JSON 夹在客套话中间回出来，而那不该算一次改写失败。
    """
    cleaned = _strip_rewrite_fence(str(text or "").strip())
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if 0 <= start < end:
        candidates.append(cleaned[start : end + 1])
    return [item for item in candidates if item]


def _rewrite_string_list(value) -> list[str]:
    """把 payload 的一个字段读成「非空字符串列表」。

    钉住的是另一条静默链路：模型把 ``"rewrites"`` 回成一个字符串时，原样交给 ``search`` 就是
    ``[query] + "住宿费"`` 当场抛错——一次看起来成功的改写反而把整条检索拖下水。所以单个字符串
    按一项收进列表，其它非列表形状（含 dict、数字、None）丢掉，列表里的非字符串与空串丢掉，
    缺字段变空列表。
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = []
    terms = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            terms.append(text)
    return terms


def _parse_rewrite_payload(text: str) -> dict:
    """约定契约 {"rewrites", "sub_questions"}；读不出来就抛 ValueError，并带上是哪一种读不出来。

    「为什么」是异常的一部分而不是一个 bool：正文里没有 JSON 与 JSON 不是约定形状，是两个
    不同的现场，混成一句就没法查。
    """
    payload = None
    for candidate in _rewrite_payload_candidates(text):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        break
    if payload is None:
        raise ValueError("no_json_object")
    if not isinstance(payload, dict):
        raise ValueError("payload_not_object")
    return {
        "rewrites": _rewrite_string_list(payload.get("rewrites")),
        "sub_questions": _rewrite_string_list(payload.get("sub_questions")),
    }


class QueryRewriter:
    """查询改写 + 子问题拆分"""

    @staticmethod
    def rewrite(question: str) -> dict:
        """返回 {"rewrites": [...], "sub_questions": [...]}

        失败照旧回退成原始问题：改写挂了不许把检索一起拖崩。但两类失败不再共用一句话——
        空正文与被长度上限截断走 ``error_code=model_response_empty`` /
        ``model_output_truncated`` 并以 ERROR 记账（静默回退正是本单的缺陷本体），
        只有「模型回了正文、我们读不懂」才是 ``error_code=rewrite_payload_unparseable``。
        """
        prompt = REWRITE_PROMPT.format(question=question)
        fallback = {"rewrites": [question], "sub_questions": []}
        try:
            resp = model.chat(
                messages=[{"role": "user", "content": prompt}],
                source=ModelSource.LOCAL,
                stream=False
            )
            text = str(resp)
            verdict = str(getattr(resp, "error_code", "") or "")
            finish_reason = str(getattr(resp, "finish_reason", "") or "")
            transport = str(getattr(resp, "transport", "") or "")
        except Exception as e:
            logger.warning(f"查询改写失败，返回原始问题: {e}")
            return fallback

        if not verdict and not text.strip():
            # 出口只承诺 str，桩与旧 handler 就不带判定；缺判定的空正文仍然按「没有正文」记，
            # 不许因为它少了一个属性而降级成「解析失败」。
            verdict = RESPONSE_EMPTY_CODE
        if verdict:
            report = logger.error if verdict in REWRITE_EMPTY_ANSWER_CODES else logger.warning
            report(
                f"查询改写没有可用正文: error_code={verdict} "
                f"finish_reason={finish_reason or 'none'} transport={transport or 'unknown'} "
                f"正文字数={len(text)}，已回退为原始问题（本次检索只用原问题）"
            )
            return fallback

        try:
            result = _parse_rewrite_payload(text)
        except ValueError as reason:
            logger.warning(
                f"查询改写正文解析失败: error_code={REWRITE_PAYLOAD_UNPARSEABLE_CODE} "
                f"reason={reason} 正文字数={len(text)} 前 80 字={text[:80]!r}，"
                f"已回退为原始问题（本次检索只用原问题）"
            )
            return fallback
        logger.info(f"查询改写: {len(result.get('rewrites',[]))} 个版本, {len(result.get('sub_questions',[]))} 个子问题")
        return result


# ==================== 术语/同义词扩展（R47，纯规则） ====================

# 一条指标定义通常带 5-6 个 match_terms。全并进检索会把 BM25 与向量两条腿的候选炸开，
# 还会让 RRF 名次变成"谁的词表长谁赢"，所以扩展条数单独设上限。
SYNONYM_EXPANSION_MAX_QUERIES = 3

# 问题字面达到这个长度就不做词表扩展；取值 0 表示关掉这道门槛。用的是 R28 判定"多意图"
# 的同一把尺 ``ADAPTIVE_REWRITE_MIN_CHARS``：写得这么长的问题，字面本身已经带够检索词，
# 而 R28 早已把这类问题判给模型改写去宽化——规则扩展补的是模型没参与的那一段。
# 这道门槛同时是对 R28 交付的兼容边界：tests/test_retrieval_rewrite_tier.py:102-110 钉死
# 了"fast 档两条腿只跑原问题"，而那道题 26 字且命中词表里的 ``住宿``。把本常量改成 0 就
# 会让那条断言变红；改它的断言不在本单写域内，要动请先由 R28 持有者收口。
SYNONYM_EXPANSION_MAX_QUERY_CHARS = ADAPTIVE_REWRITE_MIN_CHARS

# 两条腿各自的 query 上限。原本在 search 里是字面量 5，抽成常量只为让扩展看得见"还剩
# 几个槽位"，取值一字未改。
MAX_RECALL_QUERIES = 5

# 短于这个词长的词不值得单独发一条检索 query：单字在中文里几乎总是噪声级候选。
SYNONYM_EXPANSION_MIN_TERM_CHARS = 2


def _matched_definition(query: str, owner_id: str | None = None):
    """问题命中的那个指标定义；命不中、或语义目录读不动时返回 None。

    出口取 ``registry.match_definition`` 而不是 ``match_metric_context``：后者返回的是
    ``MetricContext``，而 ``MetricDefinition.to_context``（app/semantics/registry.py:166-182）
    根本没有带出 ``match_terms`` 字段——词表只在 ``MetricDefinition`` 这个 dataclass 出口上。
    命中口径（最长命中优先、owner 命名空间）整体复用 registry，本模块不自己认词。
    """
    try:
        from app.semantics.registry import match_definition

        return match_definition(query, owner_id)
    except Exception as exc:  # noqa: BLE001 - 词表读不到时原题照跑，不许把召回带崩
        logger.warning(f"同义词扩展：术语目录读取失败，本次跳过扩展: {exc}")
        return None


def expand_query_synonyms(query: str, base_queries: list[str] | None = None,
                          owner_id: str | None = None) -> list[str]:
    """用命中定义的 ``match_terms`` 给检索追加几条纯规则的改写 query。

    零模型往返、零网络、零新依赖：词表来自本机指标目录，本函数只做筛选与排序。丢掉三类词：
    与原题同形的（词面本来就是原题的子串，等于把同一条 query 再问一遍）、第 ① 步已经跑过
    的词形（模型改写可能正好改出了同一个词）、太短的。剩下的按"能给两条腿带来多少原题没
    见过的字"从多到少排，取前 ``SYNONYM_EXPANSION_MAX_QUERIES`` 条，并且只填
    ``MAX_RECALL_QUERIES`` 剩下的槽位——槽位已被原题与模型改写占满时直接返回空，连词表都
    不读，不为一次注定不生效的扩展付目录查询的往返。

    原问题始终是调用方 ``all_queries`` 的第 1 条，扩展词只往后追加，挤不掉它。
    命不中任何定义时返回 ``[]``：检索行为与扩展落地前一字不差。

    ``owner_id`` 只决定读哪一份术语目录（``registry._owner_ids``：调用者自己的行 + 共享的
    system 行），不参与权限判定，也不会把别人的租户词表带进来。传 None 即只看共享目录。
    """
    text = str(query or "").strip()
    if not text:
        return []
    queued = [str(item or "").strip() for item in (base_queries or [])]
    slots = MAX_RECALL_QUERIES - len([item for item in queued if item])
    if slots <= 0:
        return []
    if (
        SYNONYM_EXPANSION_MAX_QUERY_CHARS > 0
        and len(text) >= SYNONYM_EXPANSION_MAX_QUERY_CHARS
    ):
        logger.debug(f"同义词扩展：问题字面已达 {len(text)} 字，跳过扩展")
        return []

    definition = _matched_definition(text, owner_id)
    terms = tuple(getattr(definition, "match_terms", ()) or ())
    if not terms:
        return []

    haystack = text.lower()
    haystack_chars = set(haystack)
    seen = {item.lower() for item in queued if item}
    candidates: list[tuple[int, int, str]] = []
    for position, term in enumerate(terms):
        value = str(term or "").strip()
        key = value.lower()
        if not value or key in seen or len(value) < SYNONYM_EXPANSION_MIN_TERM_CHARS:
            continue
        if key in haystack:
            # 词面已经原样出现在问题里，两条腿都在它上头算过分了，再发一条只是重复。
            continue
        seen.add(key)
        novel_chars = len({char for char in key if char not in haystack_chars})
        candidates.append((-novel_chars, position, value))

    limit = min(slots, SYNONYM_EXPANSION_MAX_QUERIES)
    expanded = [value for _, _, value in sorted(candidates)[:limit]]
    if expanded:
        logger.info(
            f"同义词扩展: 命中 {getattr(definition, 'metric_id', '')} → "
            f"追加 {len(expanded)} 条检索 query: {expanded}"
        )
    return expanded


# ==================== 语义检索（Ollama Embedding + Chroma） ====================

class SemanticSearcher:
    """Ollama 本地 Embedding → Chroma 语义检索"""

    def __init__(self):
        from app.rag.retriever import DocumentRetriever
        self.retriever = DocumentRetriever()

    def search(self, query: str, k: int = 10, where: dict | None = None) -> list[dict]:
        return self.retriever.search(query, k=k, where=where)


# ==================== BM25 关键词检索 ====================

def _tokenize_text(text: str) -> list[str]:
    try:
        import jieba
    except ImportError:
        # 不只是 ModuleNotFoundError：jieba 装不上、装坏、或被 sys.modules 占位时
        # 抛的是父类 ImportError，回退分支必须同样生效，否则关键词检索直接返回空。
        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return [char for char in text if not char.isspace()]
        return text.split()
    return list(jieba.cut(text))

class BM25Searcher:
    """BM25 关键词检索，优先使用 jieba，缺失时回退到基础分词。"""

    def __init__(self):
        self.corpus = []          # token 列表
        self.documents = []       # 原始文档
        self.bm25: Optional[BM25Okapi] = None
        self._lock = threading.RLock()

    def build_index(self):
        """构建 BM25 语料：默认取遗留向量库，切读态取 PGVector（R59 块1 判据①）。

        两条腿取的是同一批内容（双写逐枚相等，计划书 §9.1），但"切了读"这句话如果只管
        语义腿就是半切：每次建语料仍然朝那台要退役的引擎开一次全库 ``get()``。
        ``switched_corpus()`` 交回 None 只说"这一腿没答"（没切 / 双写没开 / 连不上），
        前两种都原路退回遗留腿，与切读之前逐字一致；它不会用空列表冒充"库是空的"。
        开关默认不翻 ⇒ 这条分支在今天的默认态里一次都不生效（有一枚钉专管这件事）。
        """
        with self._lock:
            from app.rag import pg_store
            all_data = pg_store.switched_corpus()
            if all_data is None:
                from app.rag.retriever import DocumentRetriever
                r = DocumentRetriever()
                all_data = r.collection.get()
            docs = all_data.get("documents", [])
            metadatas = all_data.get("metadatas", [])

            if not docs:
                logger.warning("BM25: 知识库为空")
                return

            corpus = []
            documents = []
            for doc, meta in zip(docs, metadatas):
                tokens = _tokenize_text(doc)
                corpus.append(tokens)
                documents.append({
                    "content": doc,
                    "source": meta.get("filename", "unknown"),
                    "chunk_index": meta.get("chunk_index", 0),
                    # R57 fail-closed。此行原为 meta.get("classification", 1)：build_index 在
                    # :175 用的是不带 where 的 collection.get()，全库行都进这个本地索引，于是
                    # 缺 classification 键的遗留行被凭空补成 1 级，随后 BM25Searcher.search 用
                    # pred（app/rag/filters.py 的 DocumentRetrievalScope.allows）本地复核时，
                    # int(1) 命中密级档位表 —— 造出来的密级骗过了唯一的权限判定。
                    # 修法取「缺键即显式 None」：allows 的 int(None) 落到它自己的 except
                    # TypeError 返回 False，与 allows docstring「没有可用元数据的 chunk 永远
                    # 不可见」同义，本模块不另写任何密级/部门规则。保留键而不是删键，是为了
                    # 命中字典形状稳定，也为了让 meta.get("classification", 1) 这类写法
                    # （正是本缺陷的成因）无法再把缺键行洗回 1 级。
                    # 定性：现行入库路径 app/rag/indexing.py 的 scope_metadata 对每条 chunk 都
                    # 写入具体密级，所以本缺陷只影响遗留/外部直写的行，属纵深防御，不是现行漏权。
                    "classification": meta.get("classification"),
                    "department": meta.get("department", ""),
                })

            self.corpus = corpus
            self.documents = documents
            self.bm25 = BM25Okapi(corpus)
            logger.info(f"BM25 索引构建完成: {len(corpus)} 篇")

    def search(self, query: str, k: int = 10, pred=None) -> list[dict]:
        with self._lock:
            if not self.bm25:
                self.build_index()
            if not self.bm25:
                return []
            if k <= 0:  # 与旧实现的 [:0] 切片逐字一致
                return []

            tokens = _tokenize_text(query)
            scores = self.bm25.get_scores(tokens)
            # R45 缺陷①：权限判定必须发生在 Top-k 截断之前（先筛后取）。
            # 旧写法先按全局分数取前 k 条、再套 pred，于是无权限的 chunk 只要挤进全局
            # 前 k 就白吃一个名额：受限部门的用户可能一条都召回不到（召回饥饿）——被丢掉的
            # 名额数取决于被拦下的候选数，与合法候选数无关。现在按分数降序遍历，
            # pred 不认的条目直接跳过、不占名额，截断只作用在合法候选上。
            # pred 为 None 时与旧实现逐字一致：降序遍历遇到非正分即停（旧实现是截断后
            # 用 > 0 丢掉尾部的非正分），取满 k 条即停。
            # 判定复用 app/rag/filters.py 的 scope.allows，本模块不另写部门/密级规则。
            hits = []
            for index in np.argsort(scores)[::-1]:
                if scores[index] <= 0:
                    break
                document = self.documents[index]
                if pred and not pred(document):
                    continue
                hits.append(document)
                if len(hits) >= k:
                    break
            return hits


# ==================== RRF 融合 ====================

def rrf_fusion(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion: 合并多路检索结果
    ranked_lists: 多个排序好的结果列表
    k: RRF 平滑参数（默认 60）
    """
    scores = {}
    docs_map = {}

    for lst in ranked_lists:
        for rank, doc in enumerate(lst, start=1):
            key = doc["content"][:120]  # 去重键
            rrf_score = 1.0 / (k + rank)
            scores[key] = scores.get(key, 0) + rrf_score
            docs_map[key] = doc

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [docs_map[key] for key, _ in sorted_items]


# ==================== Cross-Encoder 重排序 ====================

class CrossEncoderReranker:
    """BAAI/bge-reranker-base 本地重排序。

    客户机器通常没有外网：默认只用本地模型，缺了就退回 RRF，绝不为了预热去访问
    huggingface.co。确实需要在线拉取时必须显式开启 ``RERANKER_ALLOW_DOWNLOAD``，
    与"远程回退默认关闭"的部署约定一致。模型目录可用 ``RERANKER_MODEL_DIR`` 指到
    挂载卷上。
    """

    def __init__(self, model_path: str = None):
        configured = os.getenv("RERANKER_MODEL_DIR", "").strip()
        if model_path is None:
            local = configured or os.path.join(
                os.path.dirname(__file__), "..", "..", "models", "BAAI", "bge-reranker-base"
            )
            model_path = local if os.path.isdir(local) else configured or "BAAI/bge-reranker-base"
        self.model_path = model_path
        self._model = None
        self.unavailable_reason = ""

    @property
    def is_local_model(self) -> bool:
        return os.path.isdir(self.model_path)

    @staticmethod
    def _download_allowed() -> bool:
        return os.getenv("RERANKER_ALLOW_DOWNLOAD", "").strip().lower() in {"1", "true", "yes", "on"}

    def _load_model(self):
        """加载失败只降级、不抛错：重排序是可选增强，不能让它决定服务能否启动。"""
        if self._model is not None or self.unavailable_reason:
            return
        if CrossEncoder is None:
            self.unavailable_reason = "sentence_transformers_not_installed"
            logger.warning("CrossEncoder 不可用，跳过预加载并回退到 RRF")
            return
        if not self.is_local_model and not self._download_allowed():
            self.unavailable_reason = "reranker_model_not_local"
            logger.warning(
                "本地找不到重排序模型目录 %s，回退到 RRF 排序；离线部署不要开启 RERANKER_ALLOW_DOWNLOAD",
                self.model_path,
            )
            return
        try:
            logger.info(f"加载 Cross-Encoder: {self.model_path} ...")
            self._model = CrossEncoder(self.model_path, device="cpu")
            logger.info("Cross-Encoder 加载完成")
        except Exception as exc:  # noqa: BLE001 - 预加载与请求路径都必须降级而不是崩溃
            self._model = None
            self.unavailable_reason = f"reranker_load_failed:{type(exc).__name__}"
            logger.warning("Cross-Encoder 加载失败，本次进程回退到 RRF 排序: %s", exc)

    def rerank(self, query: str, docs: list[dict], top_k: int = 5) -> list[dict]:
        """对检索结果重排序，返回 top_k。模型未就绪时直接返回 RRF 结果。"""
        if not docs:
            return docs

        self._load_model()
        if self._model is None:
            return docs[:top_k]

        pairs = [(query, d["content"]) for d in docs]
        scores = self._model.predict(pairs)

        for i, doc in enumerate(docs):
            doc["_score"] = float(scores[i])

        ranked = sorted(docs, key=lambda d: d["_score"], reverse=True)
        return ranked[:top_k]


# ==================== R112 · 上下文装箱：容量取真源，预留取实测 ====================
#
# 真机 2026-09-20 那扇窗（跟进单 §52/§53）撞出来的事实：analysis 档在本机
# （``n_ctx=4096``、该档声明输出 ``max_tokens=1536``）能送进模型的**题面**只有 2560 枚
# token，而这个数的真源是 ``app/agents/contracts.py`` 里 ``ModelBudget.input_budget_tokens``
# ——全仓此前只有算超时那一处在读它，没有任何一处组装上下文时读它。检索料不占房就整段拼进
# prompt，于是 prompt_tokens=3897 / 4610 那两题在 ``context_window_code()`` 当场判拒
# （``authorize()`` 直接 raise），客户看到的是一枚与"模型坏了"同色的短句，evidence_n=0。
#
# 装箱的三条规矩钉在这里，别处不许抄第二份：
#   ① 总容量 = 该档 ``input_budget_tokens``（= ``n_ctx`` − 该档声明的 ``max_tokens``）。
#      本模块既不写 2560 也不写 4096：配置一改，装箱自己跟着变。
#   ② 预留 = 下面两枚**实测**常数（system 段 + 本题题面 + 模型自己写的规划文字 +
#      tool_calls/ToolMessage 壳，以及最多两轮同会话历史的问答文字），不许拍脑袋。
#   ③ 装不下丢名次最低的整条，且不静默：丢几条、装进几条、装箱后多少 token 都进
#      ``[PromptPack]`` 那一行账，能 grep、能事后核。
PROMPT_PACK_MARKER = "[PromptPack]"

#: 实测预留（不是偏好）。**R119 把量它的尺子修对了**：旧尺的题面是 10/64/90/800 字的合成
#: 长度（注释里还写着"题面 ≤400 字"，实际那一格是 800 字），而 run5 真题面只有 **8~20 字**
#: （n=105，中位 12 字）。题面虚高几十倍，壳就被抬虚：632 里一大半是根本不会这么长的题面撑
#: 起来的。把题面换成真机实测长度（中位/最长各一条）、规划文字与 1~3 轮工具调用一格不动之后
#: 重量，四条腿 × 八种形态的最大值是 **456**（出自带 114 字规划文字 ×3 轮的 doc 腿）。
#:   真机侧独立复算同一笔：run5"本轮第一发装箱"（``packs == 1``，n=37）的实测固定壳是
#: **90~163** 枚，456 盖得住；多出的 293 枚是留给同轮第 2~3 发重复规划文字的，不是留白。
#: 同轮累加的料不在这里兜——装箱台账 ``room_left`` 自己扣，两笔不重复计。复测：
#: ``test_shell_reserve_covers_the_measured_assembly_shell``（合成壳涨过它→红）、
#: ``test_shell_reserve_is_not_inflated_above_the_measured_ceiling``（虚高多留→也红；R116 量到的
#: 正是"预留虚高 ⇒ 白白拒发"那笔账，所以多留同样是缺陷）与
#: ``test_shell_reserve_also_covers_the_real_machine_first_pack``（真机那把尺两头都夹）。
CONTEXT_SHELL_RESERVE_TOKENS = 456
#: 同一把尺实测，但 R119 之前这把尺是假的：旧夹具写 ``("上一轮的结论：…" * 6)[:400]``，那句
#: 22 字 × 6 = **132 字**，``[:400]`` 是个空操作——132 字冒称 400 字，于是量出每轮 161 枚、两轮
#: 322 枚。夹具改喂 run5 实测答案长度**中位 424 字**（n=105；尺子取自
#: ``scripts/perf_probe_run5_ledger.py`` 的 ``RUN5_ANSWER_CHARS``，字数不手抄）之后，同口径每轮
#: **453 枚**，两轮 **906** 枚（400 字那一档是 429 枚，与跟进单 §55 记的 403~429 逐字对得上，
#: 互相印证）。复测：``test_history_reserve_covers_the_pinned_number_of_turns``。上一轮**检索串**这一笔既不靠这个数兜，
#: 也不再靠跨轮累加兜：R117 实测 worker 子图在真装配下**每轮冷启动**（langgraph 给嵌套子图注入的
#: ``checkpoint_ns`` 逐轮换 uuid），上一轮的检索串这一轮并不在 prompt 里；装箱账因此改挂**轮身份**
#: （见 ``app/agents/tools.py`` 的 ``_pack_ledger_key``，跟进单 §55），同轮并发多发仍互相扣房。
#: 「该不该让子图跨轮 resume」是产品级取舍（已立案 R118，交回总控裁定），不在本单写域。
CONTEXT_HISTORY_RESERVE_TOKENS = 906

#: 装箱服务的是哪一档：doc/data/chart/export 四条 worker 腿跑的都是 analysis 档
#: （``app/agents/orchestrator.py`` 建图那几行），所以容量只问这一档的真源。
CONTEXT_PACK_TIER = "analysis"

#: 一条命中最多能进 prompt 的正文长度。截断它的工具和计量它的装箱必须是同一个数，否则
#: 最终 top-k 会按"整条原文多长"决定丢谁，而 prompt 里其实是裁过的那一份——装得下的
#: 名次被白白丢掉。以前这个数只写在 ``app/agents/tools.py`` 的 ``[:500]`` 上，现在住在
#: 这里，由那一处引用；``app/mcp_server.py`` 与 ``scripts/perf_probe_rounds.py`` 两处手抄已由 R115 改成引用本常量，全仓不再有第二把尺。
DOC_HIT_CONTENT_CHARS = 500


def context_pack_capacity(tier: str | None = None) -> int:
    """装箱总容量：该档 ``input_budget_tokens``。全仓唯一出处，这里不抄第二枚数。"""
    from app.agents.contracts import ModelTier
    from app.common.model_budget import model_tier_budget

    return int(model_tier_budget(ModelTier(tier or CONTEXT_PACK_TIER)).input_budget_tokens)


def context_pack_room(tier: str | None = None) -> int:
    """本轮还能给工具串用多少 token：总容量再扣掉两枚实测预留，扣穿了就是 0。"""
    return max(
        0,
        context_pack_capacity(tier) - CONTEXT_SHELL_RESERVE_TOKENS - CONTEXT_HISTORY_RESERVE_TOKENS,
    )


def text_pack_tokens(text: str) -> int:
    """与窗口守卫同一把尺：装箱按 ``estimate_text_tokens`` 量，判拒也按它量，两边不各说各话。"""
    from app.common.model_budget import estimate_text_tokens

    return int(estimate_text_tokens(text or ""))


def pack_prefix_by_rank(unit_texts: list, room_tokens: int, *, token_of=text_pack_tokens):
    """按名次装箱：从最高名的开始装，第一枚装不下就把它连同它后面整段丢掉。

    返回 ``(kept, dropped, kept_tokens)``。丢的是后缀，所以编号不会打洞，也不会出现
    "第 5 名进来了第 3 名反而没进来"。room=0 就是全丢——由调用方把这件事说成人话，不静默。
    """
    units = list(unit_texts)
    room = max(0, int(room_tokens))
    kept: list = []
    used = 0
    for unit in units:
        cost = int(token_of(unit))
        if used + cost > room:
            break
        kept.append(unit)
        used += cost
    return kept, units[len(kept):], used


def pack_hit_list(hits: list[dict], room_tokens: int):
    """检索结果最终 top-k 的装箱：按"真正会进 prompt 的那一份正文"计量，丢名次最低的整条。"""
    return pack_prefix_by_rank(
        list(hits),
        room_tokens,
        token_of=lambda hit: text_pack_tokens(str(hit.get("content") or "")[:DOC_HIT_CONTENT_CHARS]),
    )


def _pack_source_labels(hits: list[dict], limit: int = 3) -> str:
    """装箱账里那几条被丢掉的来源名：逐条截到 40 字，最多列 ``limit`` 条，后面折叠计数。"""
    labels = [str(hit.get("source") or "unknown")[:40] for hit in hits[:limit]]
    if len(hits) > limit:
        labels.append("…+" + str(len(hits) - limit))
    return ",".join(labels) or "-"


# ==================== R206：口径原话随引证片段进正文 ====================
#
# A④ 判据④里那枚真退化（口径冲突族 correctness 0.4211 → 0.3158）实测形状是：
# **那一句登记口径已经作为引证片段进了 prompt，模型却把它改写成同义句再交出去**
# （run6 metric-10 交回的是「费用以**入账月归属**」——粗体插进原话中间；metric-05
# 丢了主语；metric-18 同理）。逐字判分之下，同义改写就是错答。所以本节的规矩只有一条：
# **本题所问的那句口径原话，必须逐字出现在正文里**，改写不算。
#
# 为什么这套判据住在装箱模块而不是 ``app/agents/nodes.py``：装箱定的就是「哪些字会随
# 片段一起进模型」，「哪一句才算这道题的口径原话」是同一件事的另一面，抄第二份迟早漂移。
# 执法点在 ``synthesize`` 腿（那里才是终答成文的地方），本模块只出判据与原文，不碰名次、
# 不碰召回，一行现网装箱逻辑都不改。
#
# 选句**只按字面重合**，不做同义匹配——判据①要求「费用以发生月归属」与「费用以入账月
# 归属」这对互斥口径各命中各自的那句，靠语义相似去选就会两边都够。

#: 候选句的最短长度：短于此的多半是表头、条号列或一句引述，不是一条口径。
CALIBER_MIN_STATEMENT_CHARS = 12

#: 与题面至少要共有几枚双字组才算「本题所问的那一句」。这枚数是拿 run6 全 105 题的**记录
#: 证据**标定的，不是拍的：门槛 2 时全库有 19 题会被追加（含「住宿费平均值」这种算数题被
#: 拽去一句合并开票条款），改成 3 之后收到 13 题，而本单要救的三题（metric-05/10/18）
#: 逐字命中数一枚不少——cp-04 财务部那一行与题面重合 3 枚（财务/务部/费用），与它互斥的
#: 市场部那一行只有 1 枚，所以 3 这一刀同时切掉了「另一侧串味」和不相干的登记行。
#: 复测：``test_the_conflicting_pair_each_lands_on_its_own_wording``——两侧各断言一次「有自己、无对方」。
CALIBER_MIN_MATCH_BIGRAMS = 3

#: 一发最多补几句：主口径一句，与它同分的对侧至多再一句（制度 §〇.2 本就要求两侧都说明）。
CALIBER_MAX_QUOTES = 2

#: 补进正文的那一段的标题。判分器读的是整段正文，标题写清楚「逐字引自」是诚实性边界：
#: 这一段不是模型的话，是出处的原话。
CALIBER_QUOTE_LABEL = "口径原文（逐字引自出处）"

#: 题面里不参与重合度计算的标点：留着它们，「？」这种字也能凑出一枚双字组。
_CALIBER_QUESTION_PUNCTUATION = "？?。，,、；;：:（）()「」“”‘’"

#: **只有带条号的登记行才算「口径原话」**（``| cp-04 | …`` / ``| t-02 | …``）。两条例子写在
#: 这里而不是写进 ``synthesize``：① 语料自己就是这么规定的——《制度与口径登记表》§三.3
#: 「本表的任何一条被引用时，回答中必须给出条号」，条号就是可核验引用的形态；② 散文句子
#: 不是「登记」，把任意一行当原话补进正文，守卫就退化成复读机（R206 交回里明写了这条边界：
#: 本单只保登记条线，不保散文复述）。表格分隔行 ``|---|---|`` 同一条正则就挡掉了。
_CALIBER_REGISTERED_ROW = re.compile(r"^\|?\s*[A-Za-z]{1,6}-\d{1,4}\s*\|")

#: 一句登记行的收尾字符。行尾没有收尾符＝这一行是被谁裁断的（证据摘录有 400 字上限，
#: 表格行落在边界上就会被切一半），半行不许当「原话」补进正文——那正是本单要修的形状，
#: 不能再由修法自己制造一遍。
_CALIBER_LINE_ENDINGS = ("|", "。")


def caliber_question_bigrams(question: str) -> frozenset:
    """题面的双字组（空白与标点剔除）。中文没有词边界，双字组是不引分词依赖的最小重合单位。"""
    cleaned = "".join(
        ch for ch in str(question or "")
        if not ch.isspace() and ch not in _CALIBER_QUESTION_PUNCTUATION
    )
    if len(cleaned) < 2:
        return frozenset({cleaned} if cleaned else set())
    return frozenset(cleaned[i:i + 2] for i in range(len(cleaned) - 1))


def caliber_candidate_lines(text: str) -> list:
    """片段正文里所有「可能是一句口径登记」的整行，按原文顺序，逐字不改。

    只按行切，不做任何改写：交出去的字符串必须与片段里那一行**逐字相同**，否则判分器
    照样判错，而「原话」二字也就没有意义了。表格行按整行留（条号与部门都在同一行里，
    制度 §三.3 要求被引用时给出条号）。
    """
    found = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if len(line) < CALIBER_MIN_STATEMENT_CHARS or line.startswith("#"):
            continue
        if not _CALIBER_REGISTERED_ROW.match(line):
            continue
        if not line.endswith(_CALIBER_LINE_ENDINGS):
            continue
        found.append(line)
    return found


def caliber_match_score(line: str, bigrams: frozenset) -> int:
    """这一行与题面共有多少枚双字组。枚数就是重合度，不引入第二把尺。"""
    if not bigrams:
        return 0
    text = "".join(ch for ch in line if not ch.isspace())
    return sum(1 for pair in bigrams if pair in text)


def select_caliber_quotes(fragments, question: str) -> list:
    """从被引证的片段里挑出回答这道题的那几句口径原话。

    ``fragments`` 是 ``[{"text": 片段正文, "source": 来源名}]``（顺序即引证名次）。返回
    ``[{"line", "source", "score"}]``：先取全库最高分，再按名次收，同分的对侧最多收到
    ``CALIBER_MAX_QUOTES`` 句；一句都够不上门槛时返回空表——宁可不补，也不许把不相干的
    制度行糊进客户看到的答案里。
    """
    bigrams = caliber_question_bigrams(question)
    if not bigrams:
        return []
    ranked = []
    for position, fragment in enumerate(fragments or []):
        text = str((fragment or {}).get("text") or "")
        source = str((fragment or {}).get("source") or "")
        for line in caliber_candidate_lines(text):
            score = caliber_match_score(line, bigrams)
            if score >= CALIBER_MIN_MATCH_BIGRAMS:
                ranked.append((score, -position, line, source))
    if not ranked:
        return []
    top = max(item[0] for item in ranked)
    picked = []
    seen = set()
    for score, neg_position, line, source in sorted(ranked, reverse=True):
        if score < top or line in seen:
            continue
        seen.add(line)
        picked.append({"line": line, "source": source, "score": score})
        if len(picked) >= CALIBER_MAX_QUOTES:
            break
    return picked


def render_caliber_quotes(quotes, answer: str) -> str:
    """把还缺的那几句原话补成正文末尾的一段；正文里已经逐字有的句子不重复补。

    只做两件事：挑出缺失的句子、按固定格式落在正文末尾。**不改写、不截断、不同义替换**——
    补进去的每一行都能在其来源片段里逐字找到。答案为空时不补（没答案就没资格带出处）。
    返回要追加的那段文字（含前导空行），一句都不缺时返回空串。
    """
    body = str(answer or "")
    if not body.strip():
        return ""
    missing = [item for item in (quotes or []) if str(item.get("line") or "") not in body]
    if not missing:
        return ""
    # 出处名进标题，引证行本身保持片段的那一份字节原样：这样「补进去的每一行都能在出处里
    # 逐字找到」是一眼可核的机械事实，而不是要靠去掉尾巴才成立的说法。
    sources = []
    for item in missing:
        source = str(item.get("source") or "").strip()[:40]
        if source and source not in sources:
            sources.append(source)
    title = CALIBER_QUOTE_LABEL + "："
    if sources:
        title += "、".join(sources)
    quoted = ["> " + str(item["line"]) for item in missing]
    return "\n\n" + "\n".join([title] + quoted) + "\n"


# ==================== 统一检索入口 ====================

class RetrievalPipeline:
    """Agentic RAG 统一检索管线"""

    def __init__(self):
        self.semantic = SemanticSearcher()
        self.bm25 = BM25Searcher()
        self.reranker = CrossEncoderReranker()
        self.rewriter = QueryRewriter()

    def preload(self):
        """预加载：构建 BM25 索引 + 预热 CrossEncoder（避免首个请求等待 10s+）"""
        logger.info("[预加载] 构建 BM25 索引...")
        self.bm25.build_index()
        logger.info("[预加载] 预热 Cross-Encoder...")
        self.reranker._load_model()
        logger.info("[预加载] Pipeline 就绪")

    def search(self, query: str, top_k: int = 5,
               where: dict | None = None, pred=None,
               tier: str | None = None,
               owner_id: str | None = None,
               context_pack: bool = False) -> tuple[list[dict], list[str]]:
        """
        执行完整检索管线。
        返回 (重排后的文档列表, 改写版本列表)

        档位只作用在第 1 步：显式传入 ``tier`` 优先，否则读环境变量
        ``RETRIEVAL_TIER``，两者都没给就是 ``full``，与改动前完全一致。Embedding
        召回与本地 Cross-Encoder 重排都不受档位影响。

        ``owner_id`` 只给第 ①' 步的术语扩展当目录命名空间用：它决定读哪一份术语目录，
        不参与权限判定，也不进返回值。不传就是只看共享的那一份。

        ``context_pack``（R112）只作用在最后一步：True 时按本机上下文剩余 room 从尾部裁掉
        名次最低的整条，并打一行 ``[PromptPack]`` 账。默认 False —— 审批预审与检索调试视图
        要看的是"检索究竟找回了什么"，不该被装箱遮住。
        """
        # ① 查询改写 + 拆分
        tier = resolve_rewrite_tier(tier)
        if should_rewrite_query(query, tier):
            rewritten = self.rewriter.rewrite(query)
        else:
            # 省掉的就是这一发阻塞的 chat 往返：它曾是整条检索链路里最慢的一步。
            rewritten = {}
            logger.info(f"检索档位 {tier}: 跳过查询改写，本次检索 0 次大模型往返")
        all_queries = [query] + rewritten.get("rewrites", []) + rewritten.get("sub_questions", [])

        # ①' 术语/同义词扩展：问题命中的指标定义自带词表，把其中与原题不同形的词也拿去
        # 召回。纯规则，一次模型往返都不加；放在 ① 之后追加，是为了让它只填模型没花掉的
        # 召回槽位，full 档改写正常返回时扩展会被上限挡在外面，两条腿的候选数一字不变。
        # 权限口径不受影响：扩展出来的 query 走的还是下面同一个 where/pred。
        all_queries += expand_query_synonyms(query, all_queries, owner_id=owner_id)

        # ② 多路并行召回（语义+BM25 对每个 query 同时跑）
        queries = all_queries[:MAX_RECALL_QUERIES]  # 最多 5 个查询
        all_semantic = []
        all_bm25 = []
        with ThreadPoolExecutor(max_workers=len(queries)) as ex:
            futures = {}
            for q in queries:
                futures[ex.submit(self.semantic.search, q, 8, where)] = ("sem", q)
                futures[ex.submit(self.bm25.search, q, 8, pred)] = ("bm25", q)
            for f in as_completed(futures):
                kind, q = futures[f]
                try:
                    results = f.result()
                except Exception as e:
                    logger.warning(f"召回失败 [{kind}] '{q[:20]}': {e}")
                    continue
                if kind == "sem":
                    all_semantic.extend(results)
                else:
                    all_bm25.extend(results)

        # 去重
        # R45 缺陷②（纵深防御 + 两腿契约对称）：语义腿只有 where 下推，BM25 腿则一直在
        # 本地过 pred。search_for_principal 的注释本就写明"召回路径可能交回 store 没有
        # 过滤掉的 chunk"，所以两条腿都要在进 RRF 与重排之前用同一个 scope.allows 复核。
        # Chroma 主路径下这一步裁不掉任何东西（下推已在向量计算之前生效），它挡的是不执行
        # where 的召回实现；pred 为 None 时原样返回同一个列表，整步逐字等价于去重本身。
        #
        # 顺序必须是"先过滤、后去重"：_deduplicate 保留首次出现的那一份，若同一
        # content[:120] 的多份拷贝里第一份恰好缺 classification，先去重会把合法那份的键
        # 一起丢掉、剩下的缺键份再被 allows 按 fail-closed 裁掉，等于凭空误拒一条合法
        # 文档。而去重本身也不能丢：重复命中会在 rrf_fusion 里反复累加 reciprocal-rank，
        # 把只被单腿召回的来源压到后面（融合输出长度与重复无关，偏的是名次）。
        # 这个顺序也与 BM25 腿既有顺序一致：search 内部过 pred，这里再去重。
        all_semantic = _deduplicate(_retain_permitted(all_semantic, pred))
        all_bm25 = _deduplicate(all_bm25)

        # ③ RRF 融合
        fused = rrf_fusion([all_semantic, all_bm25])

        # ④ Cross-Encoder 重排
        ranked = self.reranker.rerank(query, fused, top_k=top_k)

        # ⑤ R112：只有会把结果拼进 prompt 的调用方才装箱。重排回来的顺序就是分数从高到低
        # （rerank 按 ``_score`` 降序，重排不可用时是 RRF 名次），装箱只从这个顺序的尾部裁，
        # 不在这里发明第二次排序。
        if context_pack:
            room = context_pack_room()
            packed, dropped, packed_tokens = pack_hit_list(ranked, room)
            if dropped:
                logger.info(
                    f"{PROMPT_PACK_MARKER} leg=retrieval tier={CONTEXT_PACK_TIER} "
                    f"room={room} candidates={len(ranked)} fitted={len(packed)} "
                    f"dropped={len(dropped)} packed_tokens={packed_tokens} "
                    f"dropped_sources={_pack_source_labels(dropped)}"
                )
            ranked = packed

        logger.info(f"检索完成: 语义{len(all_semantic)} + BM25{len(all_bm25)} → RRF{len(fused)} → Top{len(ranked)}")
        return ranked, rewritten.get("rewrites", [])

    def search_for_principal(
        self,
        query: str,
        principal: Principal | None,
        top_k: int = 5,
        tier: str | None = None,
        context_pack: bool = False,
    ) -> tuple[list[dict], list[str]]:
        """Retrieve only chunks permitted for the supplied Principal.

        The pushed-down ``where`` and this local predicate are the same decision
        expressed twice, because a recall path can hand back a chunk the store did not
        filter; both now come from one scope object so they cannot disagree about what
        an administrator may see.

        ``context_pack`` 原样转给 :meth:`search`：装不装箱由调用方（结果会不会进 prompt）
        决定，本层不替它判断。

        这一层还是产品问答道**唯一**的检索留痕发射点（R536）：每一发按 Principal 权限跑完的
        检索交出一枚 ``retrieval.completed``，``retrieval_traces`` 因此才有产品数据可查。
        发射实现在本文件末节，判据与口径全在那里。
        """
        scope = resolve_document_retrieval_scope(principal)
        # tier 不传时由 search() 读环境变量决定：调用方一行不改也能整条链路分档。
        # owner_id 与 app/agents/orchestrator.py 的 _owner_id_from 同一个口径（principal.user_id），
        # 决定的是"读哪一份术语目录"，不是"能看哪些文档"：registry 只允许调用者自己的行加
        # system 的共享行，principal 为 None 时退回只读共享行。
        owner_id = str(getattr(principal, "user_id", "") or "").strip() or None
        started = perf_counter()
        found = self.search(
            query, top_k=top_k, where=scope.filters, pred=scope.allows, tier=tier,
            owner_id=owner_id, context_pack=context_pack,
        )
        duration_ms = round((perf_counter() - started) * 1000, 2)
        record_retrieval_scope(principal, scope, hit_count=len(found[0]))
        # R536：全仓唯一的产品道发射调用点（判据②由 tests/test_r536_single_emission_point.py 钉）。
        # 函数自己判断这一发检索当时挂没挂问答身份：没挂就一个字都不写，所以挂在 RAG 调试面
        # 那一腿上的在册发射器（app/rag/debug.py）不会因为这里多了一行而变成两行留痕。
        record_retrieval_completed(
            query=query,
            hits=found[0],
            scope=scope,
            principal=principal,
            top_k=top_k,
            rewrites=found[1],
            duration_ms=duration_ms,
        )
        return found


def format_relevance(hit: dict) -> str:
    """Relevance text for one hit, or an explicit not-scored when nothing ranked it.

    A missing ``_score`` used to render as ``?`` in the chat answer and as ``0.00`` in
    the MCP answer. Neither is true: the first says nothing, the second invents a
    relevance of zero for a document that was just retrieved.
    """
    try:
        return f"{float(hit.get('_score')):.2f}"
    except (TypeError, ValueError):
        return "未评分"


def _deduplicate(docs: list[dict]) -> list[dict]:
    """去重（按内容前 120 字符）"""
    seen = set()
    result = []
    for d in docs:
        key = d["content"][:120]
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def _retain_permitted(hits: list[dict], pred) -> list[dict]:
    """丢掉谓词不认的召回候选；没有谓词时原样返回同一个列表对象，不改任何行为。

    pred 就是 app/rag/filters.py 里的 DocumentRetrievalScope.allows：一条候选能不能进
    融合与重排只由那一处判定决定，本模块不复制部门/密级规则。
    """
    if not pred:
        return hits
    permitted = [hit for hit in hits if pred(hit)]
    if len(permitted) != len(hits):
        logger.info(f"权限预过滤: 召回 {len(hits)} 条 → 保留 {len(permitted)} 条")
    return permitted

# ==================== 产品问答道的检索留痕（R536） ====================
#
# 症状（docs/handoff/2026-09-30-v2-gap-recheck-3.md §3 丙组 D 行与 §6 R536 行）：全仓发
# ``retrieval.completed`` 的只有 ``app/rag/debug.py`` 那一枚 RAG 调试面，正常问答链一枚都不发
# ⇒ ``retrieval_traces`` 永远 0 行，V2 第 12 句「每轮问答可回查检索」没有数据，C 门「检索留痕」
# 那半格也永远从沙盒读数升级到不了生产读数。裁定原文在
# scripts/r483_empty_tables_triage.py::TRIAGE["retrieval_traces"]（裁定词唯一真源，现取用它的 --json；「永远 0 行」是 09-30 陈述）；
# 同一条裁定还钉着口径：🔴 不许拿 ``POST /retrieval/debug`` 那一腿冒充产品道。
#
# 这一节是全仓**唯一**的产品道发射实现，形状由 tests/test_r536_single_emission_point.py 钉死：
#  ① 全仓 ``app/**`` 里发这枚事件的写法只许有两处 —— 本模块末节那一处，与在册遗留的
#     ``app/rag/debug.py`` 那一处（那枚调试面不在本单写域，本模块不碰它）；
#  ② 调用点只许有 ``RetrievalPipeline.search_for_principal`` 一处（本文件上面那一行）；
#  ③ ``app/api/v1/chat.py`` 里不许长出第二套发射手，它只负责把身份挂上（见下）。
# 事件名刻意写成字面量而不是常量：``scripts/r483_empty_tables_triage.py`` 那把现扫尺是按
# ``event_type="<名字>"`` 的字面形状找发射点的，藏进常量就等于把新发射点对在册台账抹掉。
#
# 为什么要「先挂身份才发」：``retrieval_traces`` 的每一行都必须挂在某一轮问答的 trace 上，而
# ``TraceStore.record_event`` 缺 ``trace_id`` 或 ``request_id`` 当场抛 ``validation_error``
# （app/trace/store.py 那处入参校验）。检索发生在 ``app/agents/tools.py::search_docs`` 里 ——
# 那一层的 ``config.configurable`` 带着三个 id，本层的函数拿不到，而 ``app/agents/**`` 不在本单
# 写域。所以身份由持有问答请求的那一层（``app/api/v1/chat.py`` 的两枚 ``_run``）挂进来。
# 为什么必须挂在工作线程里、而不是挂在端点函数里：chat.py 把图跑在
# ``loop.run_in_executor(_executor, _run)``，那枚普通 ``ThreadPoolExecutor`` **不复制**调用方的
# contextvar，在 ``ask()`` 里挂的值到不了工作线程；而 langgraph 自己的同步执行器会把上下文复制
# 进节点线程（``langgraph/pregel/_executor.py`` 的 ``ctx = copy_context()`` 与
# ``langchain_core`` 的 ``get_executor_for_config`` → langsmith ``ContextThreadPoolExecutor``），
# 所以在 ``_run`` 函数体内挂，图里那条检索腿一定看得见。
# 为什么用 contextvar 而不是 ``threading.local``：executor 的线程会被复用，一枚裸的线程局部值
# 在「上一轮没走到收尾就被取消」时会把身份漏给下一个跑在同一枚线程上的请求；``Token`` 交回是
# 结构性的，摘掉那一行就红（tests/test_r536_retrieval_completed_on_product_lane.py 的漏钉）。


@dataclass(frozen=True)
class RetrievalTraceContext:
    """一轮问答交给检索留痕的三个 id。

    只有 ``trace_id`` 与 ``request_id`` 是硬的（``record_event`` 收的那两格），``task_id``
    可空 —— 与 ``app/agents/orchestrator.py`` 发 canonical 事件时用的三个 id 同一套形状。
    """

    trace_id: str
    request_id: str
    task_id: str = ""


_RETRIEVAL_TRACE_CONTEXT: ContextVar[RetrievalTraceContext | None] = ContextVar(
    "enterprise_brain_retrieval_trace_context", default=None
)

#: 一条检索留痕最多记几枚命中。产品道 top_k 远小于它，这道闸只挡未来把 top_k 放宽到几十的
#: 调用方 —— 检索留痕不该把整份候选表抄进 ``trace_events`` 的 JSONB。
TRACE_HIT_CAP = 20


def current_retrieval_trace_context() -> RetrievalTraceContext | None:
    """这一条执行上下文里挂着的问答身份；没有问答在跑就是 ``None``。"""
    return _RETRIEVAL_TRACE_CONTEXT.get()


def arm_retrieval_trace(
    *, trace_id: str, request_id: str, task_id: str = ""
) -> Token[RetrievalTraceContext | None] | None:
    """把这一轮问答的身份挂进当前执行上下文，交回一枚可用于 :func:`reset_retrieval_trace` 的 token。

    两枚硬身份缺任何一枚都**不挂**并交回 ``None``：留痕宁可不发，也不许把一轮问答挂到一枚
    编出来的 trace 上，更不许在 ``record_event`` 里炸穿已经跑到手的检索结果。
    """
    resolved_trace = str(trace_id or "").strip()
    resolved_request = str(request_id or "").strip()
    if not resolved_trace or not resolved_request:
        return None
    return _RETRIEVAL_TRACE_CONTEXT.set(
        RetrievalTraceContext(
            trace_id=resolved_trace,
            request_id=resolved_request,
            task_id=str(task_id or "").strip(),
        )
    )


def reset_retrieval_trace(token: Token[RetrievalTraceContext | None] | None) -> None:
    """交回 :func:`arm_retrieval_trace` 的 token。没挂过就什么都不做。"""
    if token is not None:
        _RETRIEVAL_TRACE_CONTEXT.reset(token)


def _retrieval_query_digest(query: str) -> str:
    """``retrieval_traces.query_hash`` 是 ``CHAR(64) NOT NULL``（migrations/0002 那张表），
    消费方 ``app/trace/projections.py::project_retrieval`` 把这格原样搬过去。

    存摘要不存原文是有意的：题面是客户的业务话语，它不该因为「留一条检索痕」就被抄进另外两枚
    表里；而回查要答的问题是「这一轮按哪一发查询检索的」，64 位摘要配上 trace 与命中清单就答得出。
    """
    return hashlib.sha256(str(query or "").encode("utf-8")).hexdigest()


def _retrieval_hit_ledger(hits) -> list[dict]:
    """命中清单的留痕形状：来源、块号、分数、密级、部门。

    🔴 正文字符一个都不进。本轮证据袋已经带着 400 字摘录走 SSE 的 ``sources`` 帧
    （``app/api/v1/chat.py::_document_source_row``），把正文再抄一份进 trace 只是同一份资料多存一处。
    """
    ledger = []
    for hit in (hits or [])[:TRACE_HIT_CAP]:
        if not isinstance(hit, dict):
            continue
        ledger.append(
            {
                "source": str(hit.get("source", "")),
                "chunk_index": hit.get("chunk_index"),
                "score": hit.get("_score"),
                "classification": hit.get("classification"),
                "department": str(hit.get("department", "") or ""),
            }
        )
    return ledger


def _product_trace_store() -> Any:
    """懒取进程级 ``TraceStore``：与 ``app/agents/orchestrator.py`` 用的是同一枚单例
    （``app/trace/store.py::default_trace_store``），所以检索留痕与 canonical 事件落在同一套表上。

    懒 import 有两层理由：本模块的导入期不牵进 trace/store 那一串；测试可以就地换掉 store。
    """
    from app.trace.store import default_trace_store

    return default_trace_store()


def record_retrieval_completed(
    *,
    query: str,
    hits: list[dict],
    scope,
    principal: Principal | None = None,
    top_k: int | None = None,
    rewrites: list[str] | None = None,
    duration_ms: float | None = None,
    trace_context: RetrievalTraceContext | None = None,
    trace_store: Any = None,
) -> dict | None:
    """发一枚 ``retrieval.completed``，把它交回的全部入参对齐消费方 ``project_retrieval`` 现读的那几格。

    返回交出的事件；**没挂身份就直接返回 ``None``**（离线脚本、裸调用、以及挂在
    ``app/rag/debug.py`` 那枚调试面上的调用都属这一支），记账失败也返回 ``None`` 并留一行
    WARNING —— 留痕哑了不许把已经答到手的轮次打断（``_record_trace`` 同一裁定），但也不许哑得
    没人知道。

    ``owner_id`` 走 ``principal.user_id``（与 ``search_for_principal`` 里术语目录命名空间、
    ``app/agents/orchestrator.py`` 的 ``_owner_id_from`` 同一个口径），不是走挂上来的身份：
    这行留痕回答的是「谁的检索」，主体换了 trace 也不能跟着换。缺主体时照发 —— ``TraceStore``
    会以 ``REASON_OWNER_MISSING`` 拒绝并把它记进 fallback journal（R263 之后那本账只躺被拒的
    行），所以「没有主体」是一条看得见的痕迹，不是一次静默的跳过。
    """
    context = trace_context if trace_context is not None else current_retrieval_trace_context()
    if context is None:
        return None
    payload = {
        "owner_id": str(getattr(principal, "user_id", "") or "").strip(),
        "query_hash": _retrieval_query_digest(query),
        "filters": dict(getattr(scope, "filters", None) or {}),
        "hits": _retrieval_hit_ledger(hits),
        # 这两格是「为什么这一发看得见这些」的因由，与 record_retrieval_scope 那条审计同源。
        "scope_reason": str(getattr(scope, "reason_code", "") or ""),
        "top_k": top_k,
        "rewrite_count": len(rewrites or []),
        "duration_ms": duration_ms,
    }
    store = trace_store if trace_store is not None else _product_trace_store()
    try:
        return store.record_event(
            trace_id=context.trace_id,
            request_id=context.request_id,
            task_id=context.task_id,
            event_type="retrieval.completed",
            status="completed",
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001 - 留痕是遥测，遥测不决定一轮问答的成败
        logger.warning(f"[R536][Trace] 检索留痕没发出去: {type(exc).__name__}: {exc}")
        return None
