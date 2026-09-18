"""
Day 2: RAG 检索引擎 — 本地 Ollama Embedding
文本分块 → Embedding 向量化 → Chroma 存储 → 检索
"""
import os
import hashlib
import json
import time
import urllib.request
from urllib.error import HTTPError, URLError
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

#: 全仓唯一的向量维度声明（R21）。nomic-embed-text 输出 768 维，而全零向量的维度
#: 恰好也是 768，所以占位向量写进 Chroma 不报任何形状错误 —— 这正是它难被发现的
#: 原因。维度由此常量单一来源声明；R22 把 embedding_model + dimension 绑定进索引
#: 版本时，替换的应当是这个值，而不是再抄一份字面量。
EMBEDDING_DIM = 768

#: 模型冷加载/机器繁忙时 1 秒必然不够用（跟进单 §17 实测点），而过去超时和"模型没装"
#: 被同一个 except 吞成正常路径。默认值放宽到可覆盖的量级，仍可用 OLLAMA_EMBED_TIMEOUT
#: 显式调小；熔断冷却默认值同步显式化，冷却期内改为抛，不再批量发占位向量。
EMBED_TIMEOUT_DEFAULT_SECONDS = 30.0
EMBED_COOLDOWN_DEFAULT_SECONDS = 30.0

# ---- 失败原因稳定码：日志、健康探针、测试都比对这些字符串，不比对文案 ----
REASON_MODEL_MISSING = "model_missing"
REASON_TIMEOUT = "timeout"
REASON_CONNECTION_REFUSED = "connection_refused"
REASON_UNREACHABLE = "ollama_unreachable"
REASON_SERVER_ERROR = "server_error"
REASON_SERVER_REFUSED = "server_refused"
REASON_BAD_RESPONSE = "bad_response"
REASON_EMPTY_VECTOR = "empty_vector"
REASON_DIMENSION_MISMATCH = "dimension_mismatch"
REASON_COOLDOWN = "cooldown"
REASON_ALL_ZERO_VECTOR = "all_zero_vector"
REASON_NOT_A_VECTOR = "not_a_vector"
REASON_VECTOR_COUNT_MISMATCH = "vector_count_mismatch"

# ---- 检索腿稳定码（R21 判据④）：命中属于哪条腿、为什么退到那条腿 ----
RETRIEVAL_MODE_SEMANTIC = "semantic"
RETRIEVAL_MODE_KEYWORD = "keyword_fallback"
#: 向量后端根本不存向量（离线 _JsonCollection）时的降级原因码
RETRIEVAL_REASON_STORE_OFFLINE = "vector_store_offline"

#: 原因码 → 能直接拼进回答的一句话。答案侧读标签，不比对日志文案。
EMBEDDING_REASON_LABELS = {
    REASON_MODEL_MISSING: "本机 Ollama 未安装 embedding 模型",
    REASON_TIMEOUT: "embedding 请求超时",
    REASON_CONNECTION_REFUSED: "Ollama 服务未启动",
    REASON_UNREACHABLE: "Ollama 服务不可达",
    REASON_SERVER_ERROR: "Ollama 服务内部错误",
    REASON_SERVER_REFUSED: "Ollama 拒绝了该 embedding 请求",
    REASON_BAD_RESPONSE: "embedding 响应无法解析",
    REASON_EMPTY_VECTOR: "embedding 返回空向量",
    REASON_DIMENSION_MISMATCH: "embedding 返回的维度与声明不符",
    REASON_COOLDOWN: "embedding 连续失败，处于冷却中",
    REASON_ALL_ZERO_VECTOR: "候选向量是全零占位向量",
    REASON_NOT_A_VECTOR: "embedding 返回的不是向量",
    REASON_VECTOR_COUNT_MISMATCH: "向量条数与文本块数不符",
    RETRIEVAL_REASON_STORE_OFFLINE: "向量库后端未启用，无语义检索能力",
}

#: 降级提示模板。判据④要求"看得见"，所以这句话必须进回答，而不是只进日志。
RETRIEVAL_DEGRADATION_NOTICE = (
    "[检索降级] 本轮向量检索未参与（原因：{label}）。"
    "以下内容只来自关键词匹配，排序不代表语义相关度。"
)


def retrieval_degradation_notice(hits) -> str:
    """命中里只要有一条来自关键词腿，就返回一句必须拼进回答的降级提示。

    没有降级时返回空串，调用方据此决定要不要加提示。原因取第一条关键词命中带的
    retrieval_reason，保证提示说的是这一轮真实发生的失败，而不是历史状态。
    """
    for hit in hits or []:
        if hit.get("retrieval_mode") == RETRIEVAL_MODE_KEYWORD:
            reason = str(hit.get("retrieval_reason") or "")
            label = EMBEDDING_REASON_LABELS.get(reason, "未记录原因")
            return RETRIEVAL_DEGRADATION_NOTICE.format(label=label)
    return ""


class EmbeddingError(RuntimeError):
    """embedding 相关错误的基类；reason 是稳定码，供机器读取。"""

    def __init__(self, message: str, *, reason: str, model: str = EMBED_MODEL):
        super().__init__(message)
        self.reason = reason
        self.model = model


class EmbeddingUnavailableError(EmbeddingError):
    """模型不可用：没装 / 超时 / 拒绝服务 / 熔断冷却中 / 响应不成形。R21 判据①。"""


class VectorWriteRejectedError(EmbeddingError):
    """不合格向量被拒绝写入向量库（全零、维度不符、条数不齐）。R21 判据②。"""


#: 进程内的可观测落点：日志之外的第二个证据源，答案侧标注与健康报告都能读它，
#: 读取过程不联网、不触发任何探测。
_DIAGNOSTICS: dict = {
    "last_failure": None,
    "degraded_searches": 0,
    "rejected_writes": 0,
}


def embedding_diagnostics() -> dict:
    """最近一次 embedding 失败原因 + 降级检索次数 + 拒写次数。"""
    last = _DIAGNOSTICS["last_failure"]
    return {
        "last_failure": dict(last) if last else None,
        "degraded_searches": _DIAGNOSTICS["degraded_searches"],
        "rejected_writes": _DIAGNOSTICS["rejected_writes"],
    }


def reset_embedding_diagnostics() -> None:
    """清空进程内状态。只给测试用，生产代码不得调用。"""
    _DIAGNOSTICS["last_failure"] = None
    _DIAGNOSTICS["degraded_searches"] = 0
    _DIAGNOSTICS["rejected_writes"] = 0


def _record_failure_diagnostic(reason: str, model: str, detail: str) -> None:
    _DIAGNOSTICS["last_failure"] = {
        "reason": reason,
        "model": model,
        "detail": detail,
        "at": time.time(),
    }


def _classify_http_error(exc: HTTPError) -> str:
    """把 HTTP 状态翻译成稳定码。404 与超时绝不能落进同一个分支。"""
    code = int(getattr(exc, "code", 0) or 0)
    if code == 404:
        # ollama 对未拉取的模型返回 404，本机 nomic-embed-text 就是这个形态
        return REASON_MODEL_MISSING
    if code in (401, 403):
        return REASON_SERVER_REFUSED
    if 500 <= code < 600:
        return REASON_SERVER_ERROR
    return REASON_SERVER_REFUSED if code else REASON_BAD_RESPONSE


def _classify_url_error(exc: URLError) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError) or type(reason).__name__ in {"timeout", "TimeoutError"}:
        return REASON_TIMEOUT
    if isinstance(reason, ConnectionRefusedError):
        return REASON_CONNECTION_REFUSED
    return REASON_UNREACHABLE


def _error_detail(exc: BaseException) -> str:
    """尽量带上服务端原文（ollama 的 404 正文会直接写 model not found），读不到就算了。"""
    reader = getattr(exc, "read", None)
    body = ""
    if callable(reader):
        try:
            body = bytes(reader(400) or b"").decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - 正文只是辅助信息，不能因为它再抛一次
            body = ""
    return (body or str(exc)).strip()[:400]


def _is_zero_vector(vector) -> bool:
    """全零判定。NaN 视为非零，只有整条向量没有任何分量才算占位向量。"""
    try:
        return not any(float(value) != 0.0 for value in vector)
    except (TypeError, ValueError):
        return False


def assert_writable_embeddings(embeddings, expected_count: int, *, cause: str = "") -> None:
    """R21 判据②：任何要进向量库的向量先过这道闸，不合格就抛，绝不悄悄替换成别的值。

    挡三种情况：条数与文本块数不符、维度不等于 EMBEDDING_DIM、整条全零。全零是这里
    最要紧的一条 —— 它的维度与真向量相同，形状检查挡不住它，只有取值本身能挡住。
    """
    vectors = list(embeddings)
    reason = ""
    detail = ""
    if len(vectors) != expected_count:
        reason = REASON_VECTOR_COUNT_MISMATCH
        detail = f"向量 {len(vectors)} 条，文本块 {expected_count} 条"
    else:
        for position, vector in enumerate(vectors):
            if vector is None or isinstance(vector, (str, bytes)) or isinstance(vector, dict):
                reason = REASON_NOT_A_VECTOR
                detail = f"第 {position} 条不是数值向量：{type(vector).__name__}"
                break
            if len(vector) != EMBEDDING_DIM:
                reason = REASON_DIMENSION_MISMATCH
                detail = f"第 {position} 条长度 {len(vector)}，声明维度 {EMBEDDING_DIM}"
                break
            if _is_zero_vector(vector):
                reason = REASON_ALL_ZERO_VECTOR
                detail = f"第 {position} 条为全零向量"
                break
    if reason:
        origin = f"，最近一次 embedding 失败原因={cause}" if cause else ""
        message = f"拒绝写入向量库 [{reason}]: {detail}{origin}"
        _DIAGNOSTICS["rejected_writes"] += 1
        logger.error(message)
        raise VectorWriteRejectedError(message, reason=reason)


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
        self.timeout = float(os.getenv("OLLAMA_EMBED_TIMEOUT", str(EMBED_TIMEOUT_DEFAULT_SECONDS)))
        self.cooldown_seconds = float(
            os.getenv("OLLAMA_EMBED_COOLDOWN", str(EMBED_COOLDOWN_DEFAULT_SECONDS))
        )
        self._disabled_until = 0.0
        #: 最近一次失败：{"reason": 稳定码, "detail": 服务端原文, "at": 时间戳}
        self.last_error: dict | None = None

    def _fallback_embedding(self) -> list[float]:
        """占位向量，只服务于不写库的兼容路径，见 embed_documents 的说明。

        它不得进入向量库：DocumentRetriever._write_batch 会先用
        assert_writable_embeddings 把它挡下来（R21 判据②）。
        """
        return [0.0] * EMBEDDING_DIM

    def _is_disabled(self) -> bool:
        return time.time() < self._disabled_until

    def _fail(self, reason: str, detail: object) -> EmbeddingUnavailableError:
        """记原因 + 开熔断，把带稳定码的异常交给调用方（R21 判据①）。"""
        text = _error_detail(detail) if isinstance(detail, BaseException) else str(detail)
        self.last_error = {"reason": reason, "detail": text, "at": time.time()}
        self._disabled_until = time.time() + self.cooldown_seconds
        _record_failure_diagnostic(reason, self.model, text)
        message = f"Ollama embedding 失败 [{reason}] model={self.model}: {text}"
        logger.error(message)
        return EmbeddingUnavailableError(message, reason=reason, model=self.model)

    def _call_api(self, text: str) -> list[float]:
        """单条文本 → embedding 向量。

        R21 判据①：任何失败都抛出 EmbeddingUnavailableError，异常文本里带稳定原因码，
        能区分「模型没装」「超时」「服务拒绝」；不再返回占位向量。
        """
        if self._is_disabled():
            raise self._cooldown_error()
        try:
            data = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
            req = urllib.request.Request(self.api_url, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._fail(_classify_http_error(exc), exc) from exc
        except TimeoutError as exc:
            raise self._fail(REASON_TIMEOUT, exc) from exc
        except URLError as exc:
            raise self._fail(_classify_url_error(exc), exc) from exc
        except Exception as exc:
            # 兜底分支仍要分类：响应不是 JSON、连接被半路掐断等都得留下原因码
            raise self._fail(REASON_BAD_RESPONSE, exc) from exc
        vector = result.get("embedding") if isinstance(result, dict) else None
        if not vector:
            raise self._fail(REASON_EMPTY_VECTOR, f"响应缺少 embedding 字段：{str(result)[:200]}")
        if len(vector) != EMBEDDING_DIM:
            raise self._fail(
                REASON_DIMENSION_MISMATCH,
                f"服务端返回 {len(vector)} 维，声明维度 {EMBEDDING_DIM}",
            )
        return vector

    def _cooldown_error(self) -> EmbeddingUnavailableError:
        """熔断期内连请求都不发，但必须把「为什么不发」说清楚（R21 判据①）。"""
        last = self.last_error or {}
        cause = last.get("reason") or "unknown"
        message = (
            f"Ollama embedding 处于熔断冷却期，未发起请求 model={self.model}"
            f"，上次失败原因=[{cause}] {last.get('detail', '')}".rstrip()
        )
        logger.warning(message)
        return EmbeddingUnavailableError(message, reason=REASON_COOLDOWN, model=self.model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → embedding 向量（兼容旧契约：失败位置回填占位向量）

        保留这个形状只为不改既有非写库调用方：app/memory/long_term.py 的 _embed 把
        embedding 当可选增强，拿不到就退回关键词匹配，占位向量在它那里会被 _has_embedding
        按模长为零裁掉。写库路径不适用这条契约 —— DocumentRetriever._write_batch 会先把
        返回值交给 assert_writable_embeddings 过闸，全零向量一律拒收并抛出原因。
        """
        embeddings = []
        for i, text in enumerate(texts):
            try:
                emb = self._call_api(text)
                embeddings.append(emb)
            except EmbeddingError as e:
                logger.error(f"Embedding 失败 [{i}]: {e}")
                embeddings.append(self._fallback_embedding())
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """查询文本 → embedding 向量。失败即抛，检索层的降级见 DocumentRetriever.search。"""
        return self._call_api(text)


# ==================== 文档检索器 ====================

class DocumentRetriever:
    """文档检索引擎：管理 Chroma 向量库

    两条检索腿的语义（R21）：MODE_SEMANTIC 是 embedding + 向量库那一路；
    MODE_KEYWORD 是 embedding 不可用时的降级召回，命中里带原因码，答案侧必须据此标注
    降级，不许把它当语义命中呈现。
    """

    #: 检索模式稳定码，写进每条命中的 retrieval_mode / retrieval_reason 键。
    #: 值来自模块常量，类属性名保留给既有调用方与测试。
    MODE_SEMANTIC = RETRIEVAL_MODE_SEMANTIC
    MODE_KEYWORD = RETRIEVAL_MODE_KEYWORD
    REASON_STORE_OFFLINE = RETRIEVAL_REASON_STORE_OFFLINE

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
        #: 上一次检索实际走的腿与降级原因，见 last_search_mode / last_search_reason
        self._last_search_mode = self.MODE_SEMANTIC
        self._last_search_reason = ""

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

    # ==================== 向量库读写闸门（R21） ====================

    @property
    def stores_vectors(self) -> bool:
        """当前后端是否真的存向量。

        chromadb 缺失时 __init__ 退到 _JsonCollection，它只有文本与元数据、没有向量列，
        所以那里不可能写出零向量，但也不能假装自己是语义库。形态判断只在这里问一次。
        """
        return chromadb is not None

    @property
    def last_search_mode(self) -> str:
        """上一次 search 走的腿：MODE_SEMANTIC 或 MODE_KEYWORD。"""
        return getattr(self, "_last_search_mode", self.MODE_SEMANTIC)

    @property
    def last_search_reason(self) -> str:
        """上一次 search 的降级原因稳定码；未降级时是空串。"""
        return getattr(self, "_last_search_reason", "")

    def _embedding_failure_reason(self) -> str:
        """最近一次 embedding 失败原因码，供写库前的预检与写闸门共用。

        只读内存里的 last_error，不发请求、不开 socket。
        """
        return (getattr(self.embedding, "last_error", None) or {}).get("reason", "")

    def _write_batch(self, ids, documents, metadatas, embeddings):
        """全库唯一允许把向量交给向量库的入口（R21 判据②）。

        不合格向量在这里抛，写不进去就是写不进去，不做任何"悄悄换成别的值"的处理。
        未来的双写/迁移路径也应当走这里，而不是各自再抄一份 collection.add。
        """
        if not self.stores_vectors:
            logger.warning("向量库后端不存向量：本次只写入文本与元数据，检索按关键词降级")
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            return
        assert_writable_embeddings(
            embeddings, len(documents), cause=self._embedding_failure_reason()
        )
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=list(embeddings),
            metadatas=metadatas,
        )

    def add_document(self, filename: str, content: str,
                     classification: int = 1, department: str | None = None) -> tuple[bool, str]:
        """
        添加文档到向量库。
        返回 (是否成功, 消息)
        · 同文件内容未变 → 跳过
        · 同文件名内容变了 → 删旧加新
        · 新文件 → 直接加

        R21：embedding 不可用时抛 EmbeddingError（原因码可区分模型没装/超时/拒绝服务），
        交给调用方处理 —— app/api/v1/chat.py 的上传端点已把它转成 500 +
        document_index_failed。过去这里返回"已添加 N 个文本块"而向量全是零，属静默失败。
        """
        new_hash = self._file_hash(content)

        # 检查是否已存在同名文件。这里只记下旧 id，删除动作推迟到向量合格之后。
        existing = self.collection.get(where={"filename": filename})
        stale_ids = list(existing["ids"])
        if stale_ids:
            old_hash = existing["metadatas"][0].get("hash", "")
            if old_hash == new_hash:
                logger.info(f"文件未变化，跳过: {filename}")
                return False, "文件内容未变化，已跳过"

        # 分块
        chunks = self.splitter.split_text(content)
        if not chunks:
            return False, "文档内容为空"

        logger.info(f"分块完成: {filename} → {len(chunks)} 块")

        # 向量化。后端不存向量时一个向量都不问：过去的无条件 embed_documents 会在离线
        # _JsonCollection 上为每个 chunk 白付一次注定失败的 embedding 往返（R56 端口闸门
        # 实测命中），而它的返回值在 _write_batch 里又被整个丢掉。search 与 _write_batch
        # 都已按 stores_vectors 收口，写库这条是漏网的那一处。
        embeddings = self.embedding.embed_documents(chunks) if self.stores_vectors else []

        # 存入 Chroma
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        # 阶段 2：每个 chunk 带密级/部门元数据，供检索层过滤
        metadatas = [
            {"filename": filename, "chunk_index": i, "hash": new_hash,
             "classification": int(classification), "department": department or ""}
            for i in range(len(chunks))
        ]
        # R21：先验后删。向量不合格就在这里抛，一行业务数据都不动。
        # 过去的顺序是"删旧版本 → 向量化 → 写库"，embedding 挂掉时旧向量已被删、
        # 新向量又写不进，重传同名文档等于把它从索引里删掉。预检与 _write_batch
        # 调的是同一个 assert_writable_embeddings，不存在两套标准。
        if self.stores_vectors:
            assert_writable_embeddings(
                embeddings, len(chunks), cause=self._embedding_failure_reason()
            )

        if stale_ids:
            self.collection.delete(ids=stale_ids)
            logger.info(f"已删除旧版本: {filename}")

        batch_size = 2000
        for start, end in self._batch_ranges(len(chunks), batch_size):
            self._write_batch(
                ids=ids[start:end],
                documents=chunks[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info(f"入库完成: {filename} → {len(chunks)} 块")
        return True, f"已添加 {len(chunks)} 个文本块"

    # ==================== 检索 ====================

    def _hit_dicts(self, documents: list, metadatas: list, mode: str,
                   reason: str = "") -> list[dict]:
        """命中字典：两条腿共用，字典形状与降级标注只在这里定义一次。

        reason 是这条命中为什么来自降级腿的稳定码；语义腿传空串。
        """
        return [
            {
                "content": doc,
                "source": meta.get("filename", "unknown"),
                "chunk_index": meta.get("chunk_index", 0),
                # R57 fail-closed。此行原为 meta.get("classification", 1)。本方法的命中字典
                # 会被直接喂进权限判定：app/api/v1/chat.py 的 scope.allows(source)，以及
                # app/rag/retrieval_pipeline.py 语义腿上的 _retain_permitted(pred=
                # DocumentRetrievalScope.allows)。缺键行在这里被补成 1 级，等于在判定的输入
                # 端伪造密级。定性：Chroma 主路径下 where 已在向量计算之前排除缺键行，本行
                # 今天裁不到东西；_retain_permitted 存在的理由正是"召回实现可能不执行 where"，
                # 那时这里是最后一道伪造点，故与 BM25 腿一并按纵深防御收紧。缺键 ⇒ None ⇒
                # allows 走 except TypeError 返回 False；本模块不写密级规则。
                "classification": meta.get("classification"),
                "department": meta.get("department", ""),
                # R21：每条命中都带它实际走的检索腿。keyword_fallback 即降级标注，
                # 答案侧与评测靠它把"语义命中"和"embedding 挂了、这是词法兜底"分开。
                "retrieval_mode": mode,
                # R21 判据④：降级腿的命中额外带原因码，答案侧据此拼可见提示；
                # 语义腿恒为空串。用 retrieval_degradation_notice(hits) 取成句话。
                "retrieval_reason": reason,
            }
            for doc, meta in zip(documents, metadatas)
        ]

    def search(self, query: str, k: int = 5, where: dict | None = None) -> list[dict]:
        """语义检索。where 为权限过滤（下推到向量库），None 不过滤

        R21：embedding 不可用时不再拿占位零向量去问向量库（那等于问不出任何排序信息，
        却装作问过），而是把这一路退化成关键词召回，并把原因码写进命中与
        last_search_reason。两条腿的权限过滤都发生在截断之前。
        """
        if self.stores_vectors:
            try:
                query_embedding = self.embedding.embed_query(query)
            except EmbeddingError as exc:
                logger.error(f"向量腿下线，本次检索退化为关键词召回: {exc}")
                return self._keyword_hits(query, k, where, exc.reason)
            kwargs = {"query_embeddings": [query_embedding], "n_results": k}
            if where:
                kwargs["where"] = where
            results = self.collection.query(**kwargs) or {}
            self._note_search(self.MODE_SEMANTIC, "")
            return self._hit_dicts(
                (results.get("documents") or [[]])[0],
                (results.get("metadatas") or [[]])[0],
                self.MODE_SEMANTIC,
                "",
            )
        return self._keyword_hits(query, k, where, self.REASON_STORE_OFFLINE)

    def _note_search(self, mode: str, reason: str) -> None:
        """记录本次检索走的腿；降级计入进程内可观测计数。"""
        if mode == self.MODE_KEYWORD:
            _DIAGNOSTICS["degraded_searches"] += 1
        self._last_search_mode = mode
        self._last_search_reason = reason or ""

    def _keyword_hits(self, query: str, k: int, where: dict | None, reason: str) -> list[dict]:
        """降级腿：在同一个 store 上做词法交集排序。

        复用 _tokenize_for_fallback —— 与离线 _JsonCollection.query 同一套分词，本文件
        不新造排序器；真正的 BM25 腿在 app/rag/retrieval_pipeline.py，R21 不去碰它。
        代价是全量扫描，单机小语料下可接受（已知限制见 R21 回报）。
        """
        self._note_search(self.MODE_KEYWORD, reason)
        if k <= 0:
            return []
        stored = (self.collection.get(where=where) if where else self.collection.get()) or {}
        documents = stored.get("documents") or []
        metadatas = stored.get("metadatas") or []
        query_tokens = set(_tokenize_for_fallback(query))
        if not query_tokens:
            return []
        ranked = []
        for position, document in enumerate(documents):
            metadata = (
                metadatas[position]
                if position < len(metadatas) and metadatas[position]
                else {}
            )
            overlap = query_tokens.intersection(set(_tokenize_for_fallback(document)))
            if not overlap:
                continue
            ranked.append((-len(overlap), position, str(document), metadata))
        ranked.sort()
        picked = ranked[:k]
        return self._hit_dicts(
            [item[2] for item in picked],
            [item[3] for item in picked],
            self.MODE_KEYWORD,
            reason,
        )

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

    def document_chunks(self, filename: str) -> list[dict]:
        """Enumerate the chunks the vector store actually holds for one document.

        Read-back, not a re-split: the published record has to describe the index that
        exists. Rows come back ordered by the stored chunk index and carry the vector
        store id, which is the only link from a chunk row to its embeddings. This slice
        never reads or writes embeddings here; Chroma stays the retrieval path.
        """
        stored = self.collection.get(where={"filename": filename}) or {}
        documents = stored.get("documents") or []
        metadatas = stored.get("metadatas") or []
        ids = stored.get("ids") or []
        rows = []
        for position, document in enumerate(documents):
            metadata = metadatas[position] if position < len(metadatas) and metadatas[position] else {}
            rows.append(
                {
                    "vector_id": str(ids[position]) if position < len(ids) else "",
                    "content": str(document),
                    "chunk_index": int(metadata.get("chunk_index", position) or 0),
                    # R57 §1 判定：此处**不改**。document_chunks 是读回（见本函数 docstring），
                    # 唯一消费方 app/api/v1/chat.py 的 _document_publication 只取 content /
                    # vector_id / hash 三个键，发布记录的密级来自函数入参 classification
                    # （→ app/rag/indexing.py 的 resource_version 写入与 scope_metadata），
                    # 不来自本行；全仓再无其它调用方。因此这个默认值不到达任何权限判定，
                    # 按判据「不到达的一律只报告不改」原样保留，论证见 R57 报告站点③。
                    "classification": metadata.get("classification", 1),
                    "department": metadata.get("department", ""),
                    "hash": str(metadata.get("hash", "")),
                }
            )
        rows.sort(key=lambda row: row["chunk_index"])
        return rows

    def delete_document(self, filename: str):
        """删除指定文档的所有向量"""
        existing = self.collection.get(where={"filename": filename})
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            logger.info(f"已删除文档: {filename}")
