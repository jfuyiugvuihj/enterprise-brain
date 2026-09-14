"""
Agentic RAG 检索管线：
查询改写 → 多路召回(语义+BM25+子问题) → RRF 融合 → Cross-Encoder 重排
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
from app.common.model_handler import ModelHandler, ModelSource
from app.common.logger import logger
from app.common.identity import Principal
from app.rag.filters import build_document_retrieval_filter

model = ModelHandler()

# ==================== 查询改写 ====================

REWRITE_PROMPT = """你是检索专家。对用户问题生成 3 个不同角度的改写版本，并拆成 2-3 个子问题。

用户问题: {question}

返回 JSON（不要其他内容）：
{{"rewrites":["改写1","改写2","改写3"],"sub_questions":["子问题1","子问题2","子问题3"]}}"""


class QueryRewriter:
    """查询改写 + 子问题拆分"""

    @staticmethod
    def rewrite(question: str) -> dict:
        """返回 {"rewrites": [...], "sub_questions": [...]}"""
        prompt = REWRITE_PROMPT.format(question=question)
        try:
            resp = model.chat(
                messages=[{"role": "user", "content": prompt}],
                source=ModelSource.LOCAL,
                stream=False
            )
            result = json.loads(str(resp).strip().removeprefix("```json").removesuffix("```"))
            logger.info(f"查询改写: {len(result.get('rewrites',[]))} 个版本, {len(result.get('sub_questions',[]))} 个子问题")
            return result
        except Exception as e:
            logger.warning(f"查询改写失败，返回原始问题: {e}")
            return {"rewrites": [question], "sub_questions": []}


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
    except ModuleNotFoundError:
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
                    "classification": meta.get("classification", 1),
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

            tokens = _tokenize_text(query)
            scores = self.bm25.get_scores(tokens)
            top_indices = np.argsort(scores)[::-1][:k]

            hits = [self.documents[i] for i in top_indices if scores[i] > 0]
            if pred:
                hits = [d for d in hits if pred(d)]  # 权限过滤
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
               where: dict | None = None, pred=None) -> tuple[list[dict], list[str]]:
        """
        执行完整检索管线。
        返回 (重排后的文档列表, 改写版本列表)
        """
        # ① 查询改写 + 拆分
        rewritten = self.rewriter.rewrite(query)
        all_queries = [query] + rewritten.get("rewrites", []) + rewritten.get("sub_questions", [])

        # ② 多路并行召回（语义+BM25 对每个 query 同时跑）
        queries = all_queries[:5]  # 最多 5 个查询
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
        all_semantic = _deduplicate(all_semantic)
        all_bm25 = _deduplicate(all_bm25)

        # ③ RRF 融合
        fused = rrf_fusion([all_semantic, all_bm25])

        # ④ Cross-Encoder 重排
        ranked = self.reranker.rerank(query, fused, top_k=top_k)

        logger.info(f"检索完成: 语义{len(all_semantic)} + BM25{len(all_bm25)} → RRF{len(fused)} → Top{len(ranked)}")
        return ranked, rewritten.get("rewrites", [])

    def search_for_principal(
        self,
        query: str,
        principal: Principal | None,
        top_k: int = 5,
    ) -> tuple[list[dict], list[str]]:
        """Retrieve only chunks permitted for the supplied Principal."""
        where = build_document_retrieval_filter(principal)
        classification_values = set(where["$and"][0]["classification"]["$in"])
        department_values = set(where["$and"][1]["department"]["$in"])

        def is_permitted(document: dict) -> bool:
            try:
                classification = int(document.get("classification"))
            except (TypeError, ValueError):
                return False
            return (
                classification in classification_values
                and str(document.get("department") or "") in department_values
            )

        return self.search(query, top_k=top_k, where=where, pred=is_permitted)


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
