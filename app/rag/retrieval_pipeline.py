"""
Agentic RAG 检索管线：
查询改写 → 多路召回(语义+BM25+子问题) → RRF 融合 → Cross-Encoder 重排
"""
import json
import os
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
            return np.zeros(len(self.corpus), dtype=float)
from app.common.model_handler import ModelHandler, ModelSource
from app.common.logger import logger

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
                source=ModelSource.DEEPSEEK,
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

class BM25Searcher:
    """BM25 关键词检索，jieba 中文分词"""

    def __init__(self):
        self.corpus = []          # token 列表
        self.documents = []       # 原始文档
        self.bm25: Optional[BM25Okapi] = None

    def build_index(self):
        """从 Chroma 读取所有文档构建 BM25 索引"""
        from app.rag.retriever import DocumentRetriever
        import jieba

        r = DocumentRetriever()
        all_data = r.collection.get()
        docs = all_data.get("documents", [])
        metadatas = all_data.get("metadatas", [])

        if not docs:
            logger.warning("BM25: 知识库为空")
            return

        self.corpus = []
        self.documents = []
        for doc, meta in zip(docs, metadatas):
            tokens = list(jieba.cut(doc))
            self.corpus.append(tokens)
            self.documents.append({
                "content": doc,
                "source": meta.get("filename", "unknown"),
                "chunk_index": meta.get("chunk_index", 0),
                "classification": meta.get("classification", 1),
                "department": meta.get("department", ""),
            })

        self.bm25 = BM25Okapi(self.corpus)
        logger.info(f"BM25 索引构建完成: {len(self.corpus)} 篇")

    def search(self, query: str, k: int = 10, pred=None) -> list[dict]:
        if not self.bm25:
            self.build_index()
        if not self.bm25:
            return []

        import jieba
        tokens = list(jieba.cut(query))
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
    """BAAI/bge-reranker-base 本地重排序"""

    def __init__(self, model_path: str = None):
        # 优先用本地 ModelScope 下载的模型
        if model_path is None:
            local = os.path.join(os.path.dirname(__file__), "..", "..", "models", "BAAI", "bge-reranker-base")
            if os.path.isdir(local):
                model_path = local
            else:
                model_path = "BAAI/bge-reranker-base"
        self.model_path = model_path
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"加载 Cross-Encoder: {self.model_path} ...")
            self._model = CrossEncoder(self.model_path, device="cpu")
            logger.info("Cross-Encoder 加载完成")

    def rerank(self, query: str, docs: list[dict], top_k: int = 5) -> list[dict]:
        """对检索结果重排序，返回 top_k。模型未就绪时直接返回 RRF 结果。"""
        if not docs:
            return docs

        try:
            self._load_model()
        except Exception as e:
            logger.warning(f"CrossEncoder 加载失败，退回 RRF 结果: {e}")
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
