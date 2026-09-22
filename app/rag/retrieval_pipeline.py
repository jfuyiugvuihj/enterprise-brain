"""
Agentic RAG 检索管线：
查询改写/词表扩展 → 多路召回(语义+BM25+子问题) → 权限预过滤 → RRF 融合 → Cross-Encoder 重排
"""
import json
import os
import threading
import urllib.request
import numpy as np
from typing import Optional
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
        """从 Chroma 读取所有文档构建 BM25 索引"""
        with self._lock:
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
        """
        scope = resolve_document_retrieval_scope(principal)
        # tier 不传时由 search() 读环境变量决定：调用方一行不改也能整条链路分档。
        # owner_id 与 app/agents/orchestrator.py 的 _owner_id_from 同一个口径（principal.user_id），
        # 决定的是"读哪一份术语目录"，不是"能看哪些文档"：registry 只允许调用者自己的行加
        # system 的共享行，principal 为 None 时退回只读共享行。
        owner_id = str(getattr(principal, "user_id", "") or "").strip() or None
        found = self.search(
            query, top_k=top_k, where=scope.filters, pred=scope.allows, tier=tier,
            owner_id=owner_id, context_pack=context_pack,
        )
        record_retrieval_scope(principal, scope, hit_count=len(found[0]))
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
