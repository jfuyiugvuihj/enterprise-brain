"""
Day 2: RAG 检索引擎 — 本地 Ollama Embedding
文本分块 → Embedding 向量化 → Chroma 存储 → 检索
"""
import os
import hashlib
import json
import time
import urllib.request
from dotenv import load_dotenv
try:
    import chromadb
    from chromadb.config import Settings
except ModuleNotFoundError:  # pragma: no cover
    chromadb = None
    Settings = None

load_dotenv()
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.common.logger import logger

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"


def _tokenize_for_fallback(text: str) -> list[str]:
    normalized = str(text or "").lower()
    if any("\u4e00" <= char <= "\u9fff" for char in normalized):
        return [char for char in normalized if not char.isspace()]
    return normalized.split()


# ==================== 本地 Ollama Embedding ====================

class OllamaEmbeddings:
    """调用 Ollama 本地 Embedding API，数据不出机器"""

    def __init__(self, model: str = EMBED_MODEL, base_url: str = OLLAMA_BASE):
        self.model = model
        self.api_url = f"{base_url}/api/embeddings"
        self.timeout = float(os.getenv("OLLAMA_EMBED_TIMEOUT", "1"))
        self.cooldown_seconds = float(os.getenv("OLLAMA_EMBED_COOLDOWN", "30"))
        self._disabled_until = 0.0

    def _fallback_embedding(self) -> list[float]:
        return [0.0] * 768

    def _is_disabled(self) -> bool:
        return time.time() < self._disabled_until

    def _call_api(self, text: str) -> list[float]:
        """单条文本 → embedding 向量"""
        if self._is_disabled():
            return self._fallback_embedding()
        try:
            data = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
            req = urllib.request.Request(self.api_url, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["embedding"]
        except Exception as exc:
            logger.warning(f"Ollama embedding fallback: {exc}")
            self._disabled_until = time.time() + self.cooldown_seconds
            return self._fallback_embedding()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → embedding 向量"""
        embeddings = []
        for i, text in enumerate(texts):
            try:
                emb = self._call_api(text)
                embeddings.append(emb)
            except Exception as e:
                logger.error(f"Embedding 失败 [{i}]: {e}")
                embeddings.append(self._fallback_embedding())
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """查询文本 → embedding 向量"""
        return self._call_api(text)


# ==================== 文档检索器 ====================

class DocumentRetriever:
    """文档检索引擎：管理 Chroma 向量库"""

    def __init__(self, chroma_dir: str = "./chroma_db"):
        os.makedirs(chroma_dir, exist_ok=True)
        self.chroma_dir = chroma_dir
        if chromadb is None:
            class _JsonCollection:
                def __init__(self, path):
                    self.path = path
                    self.records = self._load()

                def _load(self):
                    if not os.path.isfile(self.path):
                        return []
                    try:
                        with open(self.path, "r", encoding="utf-8") as handle:
                            return json.load(handle)
                    except (OSError, ValueError):
                        return []

                def _save(self):
                    with open(self.path, "w", encoding="utf-8") as handle:
                        json.dump(self.records, handle, ensure_ascii=False)

                @staticmethod
                def _matches(metadata, where):
                    if not where:
                        return True
                    if "$and" in where:
                        return all(_JsonCollection._matches(metadata, item) for item in where["$and"])
                    if "$or" in where:
                        return any(_JsonCollection._matches(metadata, item) for item in where["$or"])
                    for key, condition in where.items():
                        value = metadata.get(key)
                        if isinstance(condition, dict) and "$in" in condition:
                            if value not in condition["$in"]:
                                return False
                        elif isinstance(condition, dict) and "$eq" in condition:
                            if value != condition["$eq"]:
                                return False
                        elif value != condition:
                            return False
                    return True

                def get(self, where=None):
                    records = [
                        item for item in self.records
                        if self._matches(item["metadata"], where)
                    ]
                    return {
                        "ids": [item["id"] for item in records],
                        "documents": [item["document"] for item in records],
                        "metadatas": [item["metadata"] for item in records],
                    }

                def add(self, ids, documents, metadatas, **kwargs):
                    self.records = [
                        item for item in self.records
                        if item["id"] not in set(ids)
                    ]
                    self.records.extend(
                        {
                            "id": item_id,
                            "document": document,
                            "metadata": metadata,
                        }
                        for item_id, document, metadata in zip(ids, documents, metadatas)
                    )
                    self._save()

                def delete(self, ids, **kwargs):
                    ids_to_delete = set(ids)
                    self.records = [
                        item for item in self.records
                        if item["id"] not in ids_to_delete
                    ]
                    self._save()

                def query(self, n_results=5, where=None, **kwargs):
                    records = [
                        item for item in self.records
                        if self._matches(item["metadata"], where)
                    ]
                    query_text = str(kwargs.get("query_text", "")).lower()
                    if query_text:
                        query_tokens = set(_tokenize_for_fallback(query_text))
                        records.sort(
                            key=lambda item: len(
                                query_tokens.intersection(
                                    set(_tokenize_for_fallback(item["document"]))
                                )
                            ),
                            reverse=True,
                        )
                    records = records[:n_results]
                    return {
                        "documents": [[item["document"] for item in records]],
                        "metadatas": [[item["metadata"] for item in records]],
                    }

            self.client = None
            self.collection = _JsonCollection(os.path.join(chroma_dir, "offline_collection.json"))
        else:
            self.client = chromadb.PersistentClient(
                path=chroma_dir,
                settings=Settings(anonymized_telemetry=False)
            )
            self.collection = self.client.get_or_create_collection("enterprise_docs")
        self.embedding = OllamaEmbeddings()

        # 中文友好的分块策略
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", "　", " ", ""]
        )

    # ==================== 文档管理 ====================

    def _file_hash(self, content: str) -> str:
        """计算文本 MD5，判断文档是否更新"""
        return hashlib.md5(content.encode()).hexdigest()

    @staticmethod
    def _batch_ranges(total: int, batch_size: int):
        for start in range(0, total, batch_size):
            yield start, min(start + batch_size, total)

    def add_document(self, filename: str, content: str,
                     classification: int = 1, department: str | None = None) -> tuple[bool, str]:
        """
        添加文档到向量库。
        返回 (是否成功, 消息)
        · 同文件内容未变 → 跳过
        · 同文件名内容变了 → 删旧加新
        · 新文件 → 直接加
        """
        new_hash = self._file_hash(content)

        # 检查是否已存在同名文件
        existing = self.collection.get(where={"filename": filename})
        if existing["ids"]:
            old_hash = existing["metadatas"][0].get("hash", "")
            if old_hash == new_hash:
                logger.info(f"文件未变化，跳过: {filename}")
                return False, "文件内容未变化，已跳过"

            # 删除旧版本
            self.collection.delete(ids=existing["ids"])
            logger.info(f"已删除旧版本: {filename}")

        # 分块
        chunks = self.splitter.split_text(content)
        if not chunks:
            return False, "文档内容为空"

        logger.info(f"分块完成: {filename} → {len(chunks)} 块")

        # 向量化
        embeddings = self.embedding.embed_documents(chunks)

        # 存入 Chroma
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        # 阶段 2：每个 chunk 带密级/部门元数据，供检索层过滤
        metadatas = [
            {"filename": filename, "chunk_index": i, "hash": new_hash,
             "classification": int(classification), "department": department or ""}
            for i in range(len(chunks))
        ]
        batch_size = 2000
        for start, end in self._batch_ranges(len(chunks), batch_size):
            self.collection.add(
                ids=ids[start:end],
                documents=chunks[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info(f"入库完成: {filename} → {len(chunks)} 块")
        return True, f"已添加 {len(chunks)} 个文本块"

    # ==================== 检索 ====================

    def search(self, query: str, k: int = 5, where: dict | None = None) -> list[dict]:
        """语义检索。where 为权限过滤（下推到向量库），None 不过滤"""
        query_embedding = self.embedding.embed_query(query)
        kwargs = {"query_embeddings": [query_embedding], "n_results": k}
        if where:
            kwargs["where"] = where
        results = self.collection.query(**kwargs)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        return [
            {
                "content": doc,
                "source": meta.get("filename", "unknown"),
                "chunk_index": meta.get("chunk_index", 0),
                "classification": meta.get("classification", 1),
                "department": meta.get("department", ""),
            }
            for doc, meta in zip(documents, metadatas)
        ]

    # ==================== 辅助 ====================

    def list_documents(self) -> list[str]:
        """列出已索引的文档名"""
        all_data = self.collection.get()
        seen = set()
        for meta in all_data.get("metadatas", []):
            fname = meta.get("filename", "")
            if fname and fname not in seen:
                seen.add(fname)
        return sorted(seen)

    def delete_document(self, filename: str):
        """删除指定文档的所有向量"""
        existing = self.collection.get(where={"filename": filename})
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            logger.info(f"已删除文档: {filename}")
