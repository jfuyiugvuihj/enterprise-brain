"""
Day 2: RAG 检索引擎 — 本地 Ollama Embedding
文本分块 → Embedding 向量化 → Chroma 存储 → 检索
"""
import os
import hashlib
import json
import time
import threading
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

# ---- R58 双写镜像（Chroma ⇄ PGVector）稳定码 ----
#: 开关已开但镜像不可用：未跑 0010、连不上、psycopg 缺失。写库直接拒，
#: 不退化成"只写 Chroma 成功就算过"—— 那正是本单要消灭的半态。
REASON_VECTOR_MIRROR_UNAVAILABLE = "vector_mirror_unavailable"
#: 库里登记的维度/模型/距离函数与运行时口径不符（R22 禁止一个库存两套向量）。
REASON_VECTOR_MIRROR_SCOPE_MISMATCH = "vector_mirror_scope_mismatch"
#: PG 腿 upsert/delete/commit 执行失败：两腿一起回滚后抛原异常。
REASON_VECTOR_MIRROR_WRITE_FAILED = "vector_mirror_write_failed"

# ---- 检索腿稳定码（R21 判据④）：命中属于哪条腿、为什么退到那条腿 ----
RETRIEVAL_MODE_SEMANTIC = "semantic"
RETRIEVAL_MODE_KEYWORD = "keyword_fallback"

#: 🔴 R158 · 检索结局稳定码（跟进单 §80 一 判据③）。在此之前，"向量库里找不到邻居"与
#: "检索根本没跑成"在调用方是同一张脸：都是一个空列表。P3 那 24/135 题就是这个形状——客户
#: 看到"没有来源"，真相是图里问不出邻居，两者在界面上无法分辨。这几枚码只进
#: search_shape_diagnostics() 的读数，不改 search() 的返回形状、不新增任何吞异常的路径。
RETRIEVAL_OUTCOME_ANSWERED = "answered"
#: 走到的那条腿正常交回 0 行＝"这台机器的索引里查无此物"。不是故障。
RETRIEVAL_OUTCOME_ZERO_ROWS = "leg_returned_zero_rows"
#: 向量库明明交回了行，命中数却是 0＝行丢在我们这一侧（_hit_dicts 两列对不齐、或先验之前
#: 就被裁空）。这一枚必须与上一枚可分辨，否则"我们丢了数据"会永远冒充"索引里没有"。
RETRIEVAL_OUTCOME_ROWS_DROPPED = "rows_dropped_before_hits"
#: 向量库抛异常：读数记下异常类名之后**照旧往上抛**，本单不把它改成空列表。
RETRIEVAL_OUTCOME_STORE_FAILED = "vector_store_failed"

#: 这一问是谁答的。热集答的与外部向量库答的必须可分辨：R44 那层是加速缓存，它交回 0 行
#: 时外部向量库压根没被问过，把这种 0 记成"HNSW 找不到邻居"就是假账。
RETRIEVAL_SERVER_CHROMA = "chroma"
RETRIEVAL_SERVER_HOT_INDEX = "hot_index"
RETRIEVAL_SERVER_KEYWORD_STORE = "keyword_scan"
#: R59b：读路径切到 PGVector 之后，"谁答的"多一个合法答案。它不复用 chroma 那一枚：
#: 把 PG 的答复记成 Chroma 答的，正好抹掉这一单唯一想让人看见的那件事。
RETRIEVAL_SERVER_PGVECTOR = "pgvector"
#: 向量后端根本不存向量（离线 _JsonCollection）时的降级原因码
RETRIEVAL_REASON_STORE_OFFLINE = "vector_store_offline"
#: R59 块1 判据②(a)：切读态下 PGVector 腿正常答复、就是交回 0 行。这一枚与上一枚分家，
#: 是因为它们的成因与修法完全不同——"向量库后端没启用"是这台机器压根没有语义腿，
#: "读腿打空"是权限谓词落空 / 索引里没有邻居（R269 §3 那 21 题的形状）。把它们记成同一枚
#: 码，运维就分不清该去装 chromadb 还是该去查 where。与引擎无关：这条降级不是 Chroma 病，
#: 换到 PG 之后打空照样得降级，所以它必须是一枚独立的稳定码。
RETRIEVAL_REASON_PG_ZERO_ROWS = "pgvector_read_leg_zero_rows"

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
    REASON_VECTOR_MIRROR_UNAVAILABLE: "向量镜像（PostgreSQL）不可用，已拒绝写入",
    REASON_VECTOR_MIRROR_SCOPE_MISMATCH: "向量镜像的维度或模型口径与运行时不一致，已拒绝写入",
    REASON_VECTOR_MIRROR_WRITE_FAILED: "向量镜像写入失败，Chroma 与 PostgreSQL 已一并回滚",
    RETRIEVAL_REASON_STORE_OFFLINE: "向量库后端未启用，无语义检索能力",
    # R59 块1 判据②(a)：0 行降级必须说一句人话。答案侧只读这张表，不比对日志文案。
    RETRIEVAL_REASON_PG_ZERO_ROWS: "向量库按权限查无命中，本轮改由关键词召回作答",
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


#: 🔴 R158 · 最近一次检索的形状读数与累计计数（判据③要求的"具名读数"）。
#:
#: 为什么放在模块级而不是挂在 DocumentRetriever 实例上：chat.py 与评测每次问答都可能新建
#: 检索器，挂在实例上就等于把"上一问到底发生了什么"随对象一起扔了。与 _DIAGNOSTICS /
#: hot_index._DIAGNOSTICS / pg_store._DIAGNOSTICS 同一形状：模块级、加锁、只记账、不发 IO。
#:
#: 刻意不包含查询原文、命中内容与任何标识符，只有数字与稳定码：这张表会被健康面与测试读，
#: 把 query 抄进来就是 R46 隐私判据的反面教材。
_SEARCH_SHAPE_LOCK = threading.Lock()
_SEARCH_SHAPE: dict = {"last": None, "totals": {}, "legs": {}}


def search_shape_diagnostics() -> dict:
    """最近一问的形状读数 + 各结局/各答复方的累计次数。全程只读内存，不发请求。"""
    with _SEARCH_SHAPE_LOCK:
        last = _SEARCH_SHAPE["last"]
        return {
            "last": dict(last) if isinstance(last, dict) else None,
            "totals": dict(_SEARCH_SHAPE["totals"]),
            "answered_by": dict(_SEARCH_SHAPE["legs"]),
        }


def reset_search_shape() -> None:
    """清空形状读数。只给测试用，生产代码不得调用。"""
    with _SEARCH_SHAPE_LOCK:
        _SEARCH_SHAPE["last"] = None
        _SEARCH_SHAPE["totals"] = {}
        _SEARCH_SHAPE["legs"] = {}


def _record_search_shape(*, collection: str, answered_by: str, leg: str, reason: str,
                         n_results: int, rows_returned: int, hits_built: int,
                         outcome: str, store_error: str = "") -> None:
    """把一问的形状记下来，并累计两笔数：结局计数与答复方计数。

    读数里全是**具名数字与稳定码**，没有"是不是失败了"这种布尔量：判据③要的是能指名道姓
    读出"哪个 collection、要几行、回几行、谁答的、有没有走过降级腿"，布尔量答不了这些。
    """
    reading = {
        "collection": str(collection or ""),
        "answered_by": str(answered_by or ""),
        "leg": str(leg or ""),
        "degradation_reason": str(reason or ""),
        "n_results_requested": int(n_results),
        "rows_returned": int(rows_returned),
        "hits_built": int(hits_built),
        "rows_lost": int(rows_returned) - int(hits_built),
        "outcome": str(outcome or ""),
        "store_error": str(store_error or ""),
    }
    with _SEARCH_SHAPE_LOCK:
        _SEARCH_SHAPE["last"] = reading
        _SEARCH_SHAPE["totals"][reading["outcome"]] = \
            _SEARCH_SHAPE["totals"].get(reading["outcome"], 0) + 1
        _SEARCH_SHAPE["legs"][reading["answered_by"]] = \
            _SEARCH_SHAPE["legs"].get(reading["answered_by"], 0) + 1


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


# ==================== 元数据过滤匹配（全库唯一一份） ====================

def metadata_matches(metadata, where) -> bool:
    """一条 chunk 的元数据是否满足向量库的 where 子句。

    原先这份判定长在离线 _JsonCollection 里，只有降级态用得到。R44 的热集要在进程内回答同
    一个问题（"没常驻的那条 chunk 会不会被向量库召回"），两边各抄一份迟早分叉，所以抽成模块
    级函数，离线态与热集共用，判定逻辑一个字都没改。
    """
    metadata = metadata or {}
    if not where:
        return True
    if "$and" in where:
        return all(metadata_matches(metadata, item) for item in where["$and"])
    if "$or" in where:
        return any(metadata_matches(metadata, item) for item in where["$or"])
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


# ==================== 文档检索器 ====================

# ==================== R46 · 活动信号先验（采纳/驳回 → 相关度先验）====================
#
# 跟进单 §21 给 R46 的三条判据在这段代码里各有各的位置：① 排序真的会变
# （rank_hits_by_activity）；② 无信号时与现状逐字一致（同一个函数在无信号时把**同一个
# 列表对象**原样交回，不复制、不加键、不改序）；③ 只读计数不读内容（唯一的数据来源是
# 0011 那张计数表，本模块任何路径都不把 query 交给它，也不从它读回任何文本）。
#
# fail-open 是本单的裁定，不是疏忽：先验读不到（0011 没跑、连不上 PG、psycopg 缺失）时
# 排序退回"本单之前的顺序"。反过来选 fail-closed 只有两种写法，两种都更坏——要么让一次
# 数据库故障决定问答能不能作答（把一枚排序信号提权成了服务依赖），要么"读不到就换一种
# 排法"（那才是真的把现状改掉）。权限那一侧不受这里影响：可见性判定仍然只在下推与截断
# 之前发生（app/rag/filters.py 一处），先验只在**已经合法**的候选集内部挪名次，既不新增
# 候选也不删候选。判据②要能核对，"没读到"与"没有信号"必须可分辨：前者记在
# activity_prior_diagnostics()["reason"]，后者是读成功而零行。

#: 灰度开关与 app/common/rbac.py 的 R17 那条同口径：默认生效，退回必须写成一次显式的
#: ``RAG_ACTIVITY_PRIOR=off``。拼错的值不算退回——把"没人配置"读成"配置成了关"，
#: 判据②那句"与现状一致"就会被读成"先验生效了但没人打过点"，那种误读比 bug 本身贵。
ACTIVITY_PRIOR_ENV = "RAG_ACTIVITY_PRIOR"
ACTIVITY_PRIOR_OFF_VALUES = frozenset({"off", "0", "false", "no"})

#: 🔴 R153 · 先验的单位从「分值」换成了「名次」，换的理由是量级，不是措辞。
#: 旧写法（ACTIVITY_PRIOR_WEIGHT=0.01 乘净值再加进 1/(60+rank)）里说话的是「值多少分」，
#: 而它能挪几个名次取决于加进去那一带有多挤：榜首附近一名只值 2.6e-4，一枚净采纳值 0.0025。
#: 总控在跟进单 §78 二量出「等效 11 个名次」，本单在同一把形状上现量的更难看——一条 5 名
#: 的腿一枚采纳就从第 5 名顶到第 1 名，一条 40 名的腿从第 40 名顶到第 21 名。一句话点一次
#: 就能决定这一腿的第一名，那句「不至于让谁点得多盖过谁更相关」就是这么不成立的。
#:
#: 现在界写成 ACTIVITY_PRIOR_MAX_SHIFT_RANKS = 1 枚名次（正负两侧同一个数）。为什么不继续
#: 走判据④那条「分值相加、把 weight 调小」的路：要把位移钉成 ≤1 名，最大调整值必须不超过
#: 本腿里最挤那一档的分差，而第 r 名与第 r+1 名差 1/((60+r)(61+r)) 随名次变深（r=1 是
#: 2.6e-4，r=40 只剩 9.9e-5）；照最深处取上界，浅处的调整就小到谁也挪不动，一枚净采纳连一
#: 档都过不去，特性当场死掉；何况「要多小」仍然同时取决于 rank_base 和候选条数——那正是本
#: 单要修的漂移。名次空间里这根界是个常数，与两者都无关。
#:
#: 而界不随候选宽度漂的真正理由是结构而不是算术：位移由 rank_hits_by_activity 里「一条命中
#: 每轮至多参与一次相邻交换、交换轮数＝这根界」给出，那段代码从头到尾没读 k、没读
#: len(hits)、也没读 rank_base。腿 5 / 12 / 40 三种的实测读数都是「最远一名」。
ACTIVITY_PRIOR_MAX_SHIFT_RANKS = 1
#: 证据强度折进 ±1 名：净采纳数除以「总票数 + 平滑」再乘增益，最后夹进上面那根界。一枚净采
#: 纳＝0.5（半格），两枚＝0.8，三枚到顶＝满格。到顶之后再点**不多挪**——多出来的强度只买到
#: 「两个候选抢同一次交换名额时谁赢」。强度不再兑换位移枚数，这就是校准本身。
ACTIVITY_PRIOR_SIGNAL_GAIN = 2.0
#: 平滑＝分母上先垫三张空票：一枚采纳只值半格而不是满格，样本小的文档先验就该弱，
#: 否则第一个点的人替整篇定了序。
ACTIVITY_PRIOR_SMOOTHING = 3.0
#: 名次分形状（retrieval_pipeline.rrf_fusion 的 1/(k+rank)，k 默认 60）。R153 之后先验不再
#: 往这枚分值里加东西：它只留在注记里当「这条命中本来排第几」的可读数，排序本身用不到它。
ACTIVITY_PRIOR_RANK_BASE = 60

#: 整表快照的进程内 TTL。排序每次问答都要走，为它开一趟 PG 往返而不缓存不划算；这张表
#: 至多"打过点的文档"每篇一行，整表读一次比按 filename 逐篇点查便宜得多。
ACTIVITY_PRIOR_TTL_SECONDS = 30.0

#: 读失败之后的退避窗口。不缓存失败＝每次问答都重付一趟连接超时（实测宿主对
#: 127.0.0.1:1 的探测每次 2.03s），那等于把一枚排序信号提权成全站延迟：fail-open
#: 必须是**便宜**的 open，一次库故障最多拖慢一个窗口，而不是拖慢每一问。
ACTIVITY_PRIOR_RETRY_SECONDS = 10.0
#: 本模块自己连库时的超时上界。只在调用方没写 connect_timeout 时才补：业主写的数字优先。
ACTIVITY_PRIOR_CONNECT_TIMEOUT_SECONDS = 2
#: 哪些来源的结果在窗口内值得复用。读成功与读失败都要复用，后者就是上一条的理由。
ACTIVITY_PRIOR_CACHED_SOURCES = frozenset({"store", "error"})

#: 观测面（判据②的可核对性）：先验这次读成了没有、读到几行、上一次为什么没读到。
#: "没有信号"与"没读到信号"在排序上的表现完全相同，只能靠这份计数分开。
_ACTIVITY_PRIOR_STATE: dict = {
    "loaded_at": 0.0,
    "expires_at": 0.0,
    "documents": 0,
    "source": "never",
    "reason": "",
}

#: TTL 内的整表快照，与 _ACTIVITY_PRIOR_STATE 同生命周期（reset 一起清）。
_CACHED_ACTIVITY_PRIORS: dict = {}


def activity_prior_enabled() -> bool:
    """本次排序要不要用先验：默认要，``RAG_ACTIVITY_PRIOR=off`` 是显式退回。"""
    try:
        raw = str(os.getenv(ACTIVITY_PRIOR_ENV, "") or "").strip().lower().replace("_", "-")
    except Exception:  # pragma: no cover - 配置值连字符串都读不出来时按默认那一档
        return True
    return raw not in ACTIVITY_PRIOR_OFF_VALUES


def _read_activity_signal_rows() -> list[tuple]:
    """整表读计数，交回 (filename, accepted, rejected) 元组列表。读不成一律往外抛。

    SELECT 的列名写死在这里，与本模块唯一的数据来源 0011 同生死：那张表里没有文本列，
    所以这条语句**结构上不可能**把用户问题原文读进排序路径（判据③）。
    """
    import psycopg

    # 函数内 import：app.rag.pg_store 反向 import 本模块的稳定码（见 _open_vector_mirror
    # 的注释），提到模块级会绕成环。DATABASE_URL 的口径也只认 pg_store 那一处，不重抄。
    from app.rag import pg_store

    url = pg_store.resolve_database_url()
    if "connect_timeout=" not in url:
        # 超时随 conninfo 走（与 pg_store._with_connect_timeout 同一个口径）：调用方写了
        # 就用他的，没写才补上界，别让一次排序探测挂到操作系统的 TCP 超时上。
        url = url + ("&" if "?" in url else "?") + (
            "connect_timeout=" + str(ACTIVITY_PRIOR_CONNECT_TIMEOUT_SECONDS)
        )
    with psycopg.connect(url) as connection:
        rows = connection.execute(
            "SELECT filename, accepted_count, rejected_count FROM document_activity_signals"
        ).fetchall()
    return [
        (str(row[0]), int(row[1]), int(row[2]))
        for row in rows
        if str(row[0] or "").strip()
    ]


def activity_priors(*, now: float | None = None, row_reader=None) -> dict[str, dict]:
    """filename -> {"accepted", "rejected"}：带 TTL 缓存，**fail-open**。

    读不到就是空字典，等于没有先验，排序退回现状，而不是把问答问失败。row_reader 是给
    测试留的注入口（不连库也能验排序）；它抛错同样退化成空字典，但原因会留在观测面里。
    注入 reader 的调用恒真跑（不享退避），生产那条路才按窗口复用上一次的结果。
    """
    import time as _time

    clock = _time.monotonic if now is None else (lambda: float(now))
    if row_reader is None:
        if not activity_prior_enabled():
            _ACTIVITY_PRIOR_STATE.update(
                {"source": "disabled", "reason": "disabled_by_configuration", "documents": 0}
            )
            return {}
        if (
            _ACTIVITY_PRIOR_STATE["source"] in ACTIVITY_PRIOR_CACHED_SOURCES
            and clock() < _ACTIVITY_PRIOR_STATE["expires_at"]
        ):
            # 窗口内的连续问答只读一趟库；命中不改 reason，失败态也照这条退避。
            return dict(_CACHED_ACTIVITY_PRIORS)
        row_reader = _read_activity_signal_rows
    try:
        rows = list(row_reader() or [])
    except Exception as exc:
        _CACHED_ACTIVITY_PRIORS.clear()
        _ACTIVITY_PRIOR_STATE.update(
            {
                "source": "error",
                "reason": type(exc).__name__,
                "documents": 0,
                "loaded_at": clock(),
                # 失败也占一个窗口：见 ACTIVITY_PRIOR_RETRY_SECONDS 那条注释。
                "expires_at": clock() + ACTIVITY_PRIOR_RETRY_SECONDS,
            }
        )
        logger.warning(f"活动信号计数读不到，本次排序不动用先验: {exc}")
        return {}
    priors = {
        str(name): {"accepted": int(accepted), "rejected": int(rejected)}
        for name, accepted, rejected in rows
    }
    _CACHED_ACTIVITY_PRIORS.clear()
    _CACHED_ACTIVITY_PRIORS.update(priors)
    _ACTIVITY_PRIOR_STATE.update(
        {
            "loaded_at": clock(),
            # 空表也算读成功：读通而零行是"没有信号"，读不通是"error"，两者必须分得开。
            "expires_at": clock() + ACTIVITY_PRIOR_TTL_SECONDS,
            "documents": len(priors),
            "source": "store",
            "reason": "",
        }
    )
    return dict(priors)


def activity_prior_diagnostics() -> dict:
    """先验这一路的可读数：开关、读没读成、几篇、为什么。"""
    return {
        "enabled": activity_prior_enabled(),
        "source": _ACTIVITY_PRIOR_STATE["source"],
        "reason": _ACTIVITY_PRIOR_STATE["reason"],
        "documents": int(_ACTIVITY_PRIOR_STATE["documents"]),
        "max_shift_ranks": ACTIVITY_PRIOR_MAX_SHIFT_RANKS,
        "gain_per_signal": ACTIVITY_PRIOR_SIGNAL_GAIN,
        "smoothing": ACTIVITY_PRIOR_SMOOTHING,
    }


def reset_activity_priors() -> None:
    """清掉缓存与观测面（测试用，以及"刚跑完 0011"之后想让下一问立刻读到新账）。"""
    _CACHED_ACTIVITY_PRIORS.clear()
    _ACTIVITY_PRIOR_STATE.update(
        {"loaded_at": 0.0, "expires_at": 0.0, "documents": 0, "source": "never", "reason": ""}
    )


def activity_prior_value(counts) -> float:
    """一篇文档的先验强度，单位是**名次**；没打过点＝0.0＝不动名次。

    净值除以「总票数 + 平滑」再乘增益，最后夹进 ±ACTIVITY_PRIOR_MAX_SHIFT_RANKS。0/0 与
    5/5 同样给 0.0：分开记两列买到的是「可分辨」，不是「另一档权重」。
    这枚数值只用来决定「谁更值得用掉那一次相邻交换」；位移枚数由 rank_hits_by_activity 的
    结构封顶（至多一根界的长度）。所以把 20 枚采纳降成 3 枚不会少挪一名，把界改成 2 名才会。
    """
    if not isinstance(counts, dict):
        return 0.0
    try:
        accepted = int(counts.get("accepted") or 0)
        rejected = int(counts.get("rejected") or 0)
    except (TypeError, ValueError):
        return 0.0
    total = accepted + rejected
    if total <= 0:
        return 0.0
    cap = float(ACTIVITY_PRIOR_MAX_SHIFT_RANKS)
    raw = ACTIVITY_PRIOR_SIGNAL_GAIN * (accepted - rejected) / (total + ACTIVITY_PRIOR_SMOOTHING)
    return max(-cap, min(cap, raw))


# ==================== R46 差格 a · 点击/浏览先验（出处被真看过 → 相关度先验）====================
#
# 跟进单 §21 那句「采纳/驳回/点击 → 相关度先验」里的第三枚信号，落在 migrations/0019 那张
# 事件表上，本段是它的**读腿**。它刻意长成上面那段采纳/驳回先验的形状——同一套 TTL、同一套
# 退避、同一套 fail-open、同一套观测面，最后与那一合成**一枚**先验。两套各长一套兜底逻辑的
# 下场是没人说得清这一次排序到底听谁的，而判据②那句「没信号时与现状一致」也就没了尺。
#
# 🔴 两路信号合成一个数，位移界**不因此变宽**：ACTIVITY_PRIOR_MAX_SHIFT_RANKS 说的从来不是
# 「采纳这一路最多挪几名」，而是「先验这一手最多挪几名」（R153 的原话）。所以合并值夹回同
# 一根 ±1 名，而不是 1+1=2。点击证据再厚也只买到「在同一次交换名额里赢过隔壁」，买不到第二格
# 位移——这条由 tests/test_r46c_engagement_prior.py 拿腿宽 5/12/40 各量一遍钉住。
#
# 冷启动（判据②）：这一路没有「分数」这回事，0.0 的含义是**不动名次**，不是「这篇值零分」。
# 从没人点过的文档与刚入库的新文档在这一路拿同一个中性值，排序退回名次分本身，于是新文档永远
# 靠相关性还有上位的机会，不会被「历史点击多」那一族永久压住。反过来样本太少时先验按
# confidence = 样本数 / ENGAGEMENT_MIN_SAMPLES 往中性收缩，「第一个点的人替整篇定序」不发生。

#: 整表快照的进程内 TTL 与读失败退避：与 ACTIVITY_PRIOR_* 同值同理由（一次库故障最多拖慢一个
#: 窗口，而不是拖慢每一问），但**各自一份状态**——一路读到、一路读不通是两种真实，合成一个
#: "读不到"就把可核对性丢了。
ENGAGEMENT_PRIOR_TTL_SECONDS = 30.0
ENGAGEMENT_PRIOR_RETRY_SECONDS = 10.0
ENGAGEMENT_PRIOR_CACHED_SOURCES = frozenset({"store", "error"})

#: 证据权重：把一条出处**点开**比**展开看了一眼**更强，所以一枚 click 记一份、一枚 view 记
#: 半份。这枚比值是口径，不是校准结果——真库强度欠一台安静机器量（见交工纸「未验的格子」）。
ENGAGEMENT_CLICK_WEIGHT = 1.0
ENGAGEMENT_VIEW_WEIGHT = 0.5
#: 分母上先垫的五次空看：与 ACTIVITY_PRIOR_SMOOTHING 同一个理由——第一枚证据不该替整篇定序。
ENGAGEMENT_PRIOR_SMOOTHING = 5.0
#: 样本数下限：攒够这么多枚动作之前，先验按 support / 本数 往中性收缩；不足一枚都不给满格。
ENGAGEMENT_MIN_SAMPLES = 5
#: 🔴 与采纳/驳回共用同一根界：合并后仍是一枚名次，本单一秒都不放宽。
ENGAGEMENT_PRIOR_MAX_SHIFT_RANKS = ACTIVITY_PRIOR_MAX_SHIFT_RANKS

#: 观测面：与 _ACTIVITY_PRIOR_STATE 同形状，两路各自记自己读没读到（判据⑤那句「读不到」与
#: 「没信号」必须分得开，在两路上都得分得开）。
_ENGAGEMENT_PRIOR_STATE: dict = {
    "loaded_at": 0.0,
    "expires_at": 0.0,
    "documents": 0,
    "source": "never",
    "reason": "",
}
_CACHED_ENGAGEMENT_PRIORS: dict = {}


def _read_engagement_rows() -> list[tuple]:
    """整表聚合读动作，交回 (filename, clicks, views) 元组列表。读不成一律往外抛。

    🔴 列清单只有文档标识与两枚 COUNT：username 在这一条语句里**连出现的位置都没有**，所以
    「谁点的」进不了排序，只进得了审计与本表。想按人加权就得改这条字面量，而那一步会先被
    tests/test_r46c_engagement_prior.py 的列名清单拦下。表还没建（业主未跑 0019）与库连不上都
    照样抛出去，由 engagement_priors() 那层退化成"没有先验"。
    """
    from app.db.connection import open_connection, parse_database_settings
    # 函数内 import：与 _read_activity_signal_rows 同一条理由（pg_store 反向 import 本模块）。
    from app.rag import pg_store

    url = pg_store.resolve_database_url()
    if "connect_timeout=" not in url:
        url = url + ("&" if "?" in url else "?") + (
            "connect_timeout=" + str(ACTIVITY_PRIOR_CONNECT_TIMEOUT_SECONDS)
        )
    # 边界只转发 conninfo，所以超时随 DSN 走；行工厂不动，仍是驱动自己的元组缺省。
    with open_connection(parse_database_settings(url)) as connection:
        rows = connection.execute(
            "SELECT filename, "
            "COUNT(*) FILTER (WHERE event_type = 'click') AS clicks, "
            "COUNT(*) FILTER (WHERE event_type = 'view') AS views "
            "FROM document_engagement_events GROUP BY filename"
        ).fetchall()
    return [
        (str(row[0]), int(row[1]), int(row[2]))
        for row in rows
        if str(row[0] or "").strip()
    ]


def engagement_priors(*, now: float | None = None, row_reader=None) -> dict[str, dict]:
    """filename -> {"clicks", "views"}：带 TTL 缓存，**fail-open**（与 activity_priors 同一套）。"""
    import time as _time

    clock = _time.monotonic if now is None else (lambda: float(now))
    if row_reader is None:
        if (
            _ENGAGEMENT_PRIOR_STATE["source"] in ENGAGEMENT_PRIOR_CACHED_SOURCES
            and clock() < _ENGAGEMENT_PRIOR_STATE["expires_at"]
        ):
            return dict(_CACHED_ENGAGEMENT_PRIORS)
        row_reader = _read_engagement_rows
    try:
        rows = list(row_reader() or [])
    except Exception as exc:
        # 异常名走 __class__.__name__ 而不是 type(exc).__name__：两枚读数同值，但后者那行字面量
        # 是 tests/test_r525_counter_evidence_teeth.py 里 K6 那把反证刀的锚点，锚点要求**全文件
        # 唯一**（不唯一的刀等于没动东西）。新读腿不能把别人那把刀磨钝——措辞换形，语义一字不漂。
        _CACHED_ENGAGEMENT_PRIORS.clear()
        _ENGAGEMENT_PRIOR_STATE.update(
            {
                "source": "error",
                "reason": exc.__class__.__name__,
                "documents": 0,
                "loaded_at": clock(),
                "expires_at": clock() + ENGAGEMENT_PRIOR_RETRY_SECONDS,
            }
        )
        logger.warning(f"点击/浏览事件读不到，本次排序不动用这一路先验: {exc}")
        return {}
    priors = {
        str(name): {"clicks": int(clicks), "views": int(views)}
        for name, clicks, views in rows
    }
    _CACHED_ENGAGEMENT_PRIORS.clear()
    _CACHED_ENGAGEMENT_PRIORS.update(priors)
    _ENGAGEMENT_PRIOR_STATE.update(
        {
            "loaded_at": clock(),
            "expires_at": clock() + ENGAGEMENT_PRIOR_TTL_SECONDS,
            "documents": len(priors),
            "source": "store",
            "reason": "",
        }
    )
    return dict(priors)


def engagement_prior_diagnostics() -> dict:
    """这一路的可读数：读没读成、几篇、为什么（开关沿用 activity 那一枚，见下面注释）。"""
    return {
        "enabled": activity_prior_enabled(),
        "source": _ENGAGEMENT_PRIOR_STATE["source"],
        "reason": _ENGAGEMENT_PRIOR_STATE["reason"],
        "documents": int(_ENGAGEMENT_PRIOR_STATE["documents"]),
        "max_shift_ranks": ENGAGEMENT_PRIOR_MAX_SHIFT_RANKS,
        "click_weight": ENGAGEMENT_CLICK_WEIGHT,
        "view_weight": ENGAGEMENT_VIEW_WEIGHT,
        "smoothing": ENGAGEMENT_PRIOR_SMOOTHING,
        "min_samples": ENGAGEMENT_MIN_SAMPLES,
    }


def reset_engagement_priors() -> None:
    """清掉这一路的缓存与观测面。"""
    _CACHED_ENGAGEMENT_PRIORS.clear()
    _ENGAGEMENT_PRIOR_STATE.update(
        {"loaded_at": 0.0, "expires_at": 0.0, "documents": 0, "source": "never", "reason": ""}
    )


def reset_signal_priors() -> None:
    """两本账一起清：写成功之后调用，免得「回执说点过、排序还按没点过排」。

    排序一次读两路，快照就必须同生同死；只清一路等于让另一路带着旧账参加下一次比较。
    """
    reset_activity_priors()
    reset_engagement_priors()


def engagement_prior_value(counts) -> float:
    """一篇文档靠点击/浏览挣到的先验，单位是**名次**；没动作＝0.0＝不动名次。

    🔴 这一路**只抬不压**：返回值恒在 [0, 界]。没人点过不等于不好，可能是刚入库、可能是这道题
    本来就没人往下翻——把「零证据」读成负分，新文档就永久翻不了身，那正是判据②点名要拦的读法。
    两列计数都是 0 与「这一篇压根不在表里」在这里给出同一个 0.0，而两者与「读不通」在观测面上
    分得开（source 为 store / error）。
    """
    if not isinstance(counts, dict):
        return 0.0
    try:
        clicks = int(counts.get("clicks") or 0)
        views = int(counts.get("views") or 0)
    except (TypeError, ValueError):
        return 0.0
    if clicks < 0 or views < 0:
        return 0.0
    support = clicks + views
    if support <= 0:
        return 0.0
    cap = float(ENGAGEMENT_PRIOR_MAX_SHIFT_RANKS)
    evidence = ENGAGEMENT_CLICK_WEIGHT * clicks + ENGAGEMENT_VIEW_WEIGHT * views
    # 冷启动收缩：证据不足下限就按比例往中性拉，攒够之后 confidence 恒为 1，不再随样本变。
    confidence = min(1.0, support / float(ENGAGEMENT_MIN_SAMPLES))
    raw = cap * evidence / (evidence + ENGAGEMENT_PRIOR_SMOOTHING) * confidence
    return max(0.0, min(cap, raw))


def merge_signal_priors(activity, engagement) -> dict[str, dict]:
    """把两路计数并成排序吃的那一份：一路缺席不抹掉另一路。"""
    merged: dict[str, dict] = {}
    for table in (activity, engagement):
        for source, counts in (table or {}).items():
            name = str(source or "")
            if not name:
                continue
            row = merged.setdefault(name, {})
            if isinstance(counts, dict):
                row.update(counts)
    return merged


def signal_prior_value(counts) -> float:
    """一次比较用的合并不值：两路各自算，再夹回**同一根**界。

    夹界而不是相加后就交出去，是判据②「位移界不许放宽」的落点：采纳与点击各自顶满时，简单
    相加会给出 2 枚名次，而名次空间的交换轮数仍是一轮——那一轮至多换一名，多出来的 1 既量不到
    也说不清，只留下"常数写 1、实际行为像 2"的口径漂移。夹回 ±1 名之后，两路信号买到的是
    「在同一次交换名额里谁赢」，买不到第二格位移。
    """
    cap = float(ACTIVITY_PRIOR_MAX_SHIFT_RANKS)
    total = activity_prior_value(counts) + engagement_prior_value(counts)
    return max(-cap, min(cap, total))


def _hit_source(hit) -> str:
    """命中里那个文档标识；不是字典、或没带 source，一律读成空串（＝这一条拿不到先验）。

    🔴 两遍循环必须共用这一把尺：第一遍算调整值时用 isinstance 挡过非字典命中，第二遍复制
    命中时若忘了挡，一条畸形命中就能在排序里抛 AttributeError——而 rank_hits_by_activity
    是在 _apply_activity_prior 那个 try **之外**调用的。那等于让一枚畸形命中把整条检索打挂，
    比先验失效严重得多，也与本模块 fail-open 的承诺相反。
    """
    if not isinstance(hit, dict):
        return ""
    return str(hit.get("source") or "")


def _one_round_of_bounded_transpositions(order, strengths) -> bool:
    """跑一轮互不相交的相邻交换，交回这一轮到底换没换过（换过才值得再来一轮）。

    判据①那根界的落点就在这里：一轮内每条命中至多参与一次交换，而一次相邻交换只把它的
    下标挪一格，没参与交换的条目下标一个都不变 ⇒ **一轮至多一名**，跑几轮就是几名，而
    这件事与列表有多长无关。同一轮里两个候选抢同一个空位时，把名额给 shift 更大的一枚
    （同 shift 取位置靠前的），于是「20 枚采纳」与「1 枚采纳」争同一位时永远是前者拿到。
    """
    exchanged = False
    used = set()
    while True:
        pick = -1
        pick_shift = None
        for position in range(len(order) - 1):
            upper, lower = order[position], order[position + 1]
            if upper in used or lower in used:
                continue  # 换过的一轮里不再换第二次：这正是「每轮至多一名」的由来
            if strengths[lower] <= strengths[upper]:
                continue  # 证据不比上位者强就一次都不换，并列永远保持原序
            if pick < 0 or strengths[lower] > pick_shift:
                pick, pick_shift = position, strengths[lower]
        if pick < 0:
            return exchanged
        used.add(order[pick])
        used.add(order[pick + 1])
        order[pick], order[pick + 1] = order[pick + 1], order[pick]
        exchanged = True


def rank_hits_by_activity(hits, priors, *, enabled: bool = True, rank_base: int = ACTIVITY_PRIOR_RANK_BASE):
    """在同一个候选集内部按活动信号重排；候选的进出一个都不动。

    🔴 判据②的口径写在这条返回上，R153 一个字没松：开关关着、输入不是列表、为空、或者
    **没有任何一条命中带先验**时，交回的是同一个对象——不是「内容恰好相同的另一份拷贝」。
    于是「无信号 ⇒ 与现状逐字一致」是可证的，不依赖浮点比较。只有真有信号时才复制字典，
    并给每条命中补一枚 ``activity_prior``（accepted / rejected / shift_ranks / rank_score /
    previous_rank / new_rank / places_moved），让「这篇凭什么排上来」在答案侧看得见：计数、
    强度、本来第几名、现在第几名、挪了几名，一个都不缺；那枚字典里只有计数与名次，没有内容。

    位移上界（判据①）＝ ACTIVITY_PRIOR_MAX_SHIFT_RANKS 枚名次，正负两侧同一个数，且与腿宽
    无关。实现是「相邻交换」而不是「按分值重排」，理由见 _one_round_of_bounded_transpositions
    与上面那段常量注释：分值相加时一枚采纳能值几个名次取决于那一带多挤，界就会随 rank_base
    和候选条数漂。同一批输入永远同一批输出，不靠排序算法的运气。

    列表里混进非字典条目时，那些条目按 _hit_source 的口径拿不到先验、也不被注记，只按原名次
    参与交换：本函数对畸形输入交回的是排好序的原条目，不是异常。

    R46 差格 a 在本函数上只动了一处：算 strength 的那一枚函数从 activity_prior_value 换成
    signal_prior_value（采纳/驳回 + 点击/浏览，夹回同一根界）。注记的键清单一个字都不加——
    它是答案侧的契约（tests/test_r153_prior_shift_is_bounded.py::NOTE_KEYS 判等），要加长它
    得先改判据。点击那一路的证据由 GET /api/v1/feedback/engagement 现读，不塞进这枚注记。
    """
    if not enabled or not isinstance(hits, list) or not hits:
        return hits
    lookup = priors or {}
    strengths = [signal_prior_value(lookup.get(_hit_source(hit))) for hit in hits]
    if not any(strengths):
        return hits
    carriers = []
    for rank, hit in enumerate(hits, start=1):
        counts = lookup.get(_hit_source(hit)) or {}
        if isinstance(hit, dict):
            carrier = dict(hit)
            carrier["activity_prior"] = {
                "accepted": int(counts.get("accepted") or 0),
                "rejected": int(counts.get("rejected") or 0),
                "shift_ranks": strengths[rank - 1],
                "rank_score": 1.0 / (rank_base + rank),
                "previous_rank": rank,
            }
        else:
            carrier = hit  # 畸形命中：原样带着走，一个键都不注记，只按自己的名次参与排序
        carriers.append(carrier)
    order = list(range(len(carriers)))
    for _ in range(int(ACTIVITY_PRIOR_MAX_SHIFT_RANKS)):
        if not _one_round_of_bounded_transpositions(order, strengths):
            break
    ranked = []
    for new_rank, index in enumerate(order, start=1):
        carrier = carriers[index]
        if isinstance(carrier, dict):
            carrier["activity_prior"]["new_rank"] = new_rank
            carrier["activity_prior"]["places_moved"] = index + 1 - new_rank
        ranked.append(carrier)
    return ranked


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
    #: R59 块1 判据②(a)：切读态下 PG 腿打空时，命中带上的降级码（与上一枚分家，见模块注释）
    REASON_PG_ZERO_ROWS = RETRIEVAL_REASON_PG_ZERO_ROWS

    def __init__(self, chroma_dir: str = "./chroma_db", *, activity_prior=None, engagement_prior=None):
        os.makedirs(chroma_dir, exist_ok=True)
        self.chroma_dir = chroma_dir
        # R46：计数表的读取方可注入（测试不连库也能验排序），默认走进程内缓存的
        # 整表快照。注入一个返回 {} 的 callable 就等于关掉先验，不改排序语义。
        self._activity_prior_loader = activity_prior or activity_priors
        # R46 差格 a：点击/浏览那一路的读取方同一形状、同一注入位。两路各自一份快照，一路
        # 读不通只让那一路退化成"没有先验"，不抹掉另一路挣来的证据。
        self._engagement_prior_loader = engagement_prior or engagement_priors
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
                    # R44：判定本体已抽到模块级 metadata_matches，离线态与热集共用一份。
                    return metadata_matches(metadata, where)

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

    # ==================== R44 热集钩子（默认关；一层可丢弃的加速缓存，不是第二事实源） ====================

    def _hot_scope_key(self) -> tuple:
        """本次读写所属的索引口径：backend + 模型 + 维度（R22 的同一个口径源）。

        app.rag.hot_index 一律在函数内 import：它反过来要用本模块的 metadata_matches，模块级
        互引会成循环 import —— 与 R58 的 _open_vector_mirror 同一个处理方式。
        """
        from app.rag import hot_index

        return hot_index.current_scope_key()

    def _note_hot_write(self, ids, documents, metadatas, embeddings) -> None:
        """向量已经落库之后被告知一次热集（判据④的失效来源）。开关关闭时直接返回。"""
        if not ids:
            return
        from app.rag import hot_index

        if not hot_index.hot_index_enabled():
            return
        hot_index.get_hot_index().note_write(
            ids=ids, documents=documents, metadatas=metadatas,
            embeddings=embeddings, scope_key=self._hot_scope_key(),
        )

    def _note_hot_delete(self, ids) -> None:
        """文档删除、同名重传的删旧：热集对应条目必须跟着走（判据④）。"""
        if not ids:
            return
        from app.rag import hot_index

        if not hot_index.hot_index_enabled():
            return
        hot_index.get_hot_index().note_delete(ids, scope_key=self._hot_scope_key())

    def _note_hot_reset(self, reason: str) -> None:
        """双写补偿回滚之后整体作废：库里被逆序放回了旧向量，内存那本账就不敢再信。"""
        from app.rag import hot_index

        if not hot_index.hot_index_enabled():
            return
        hot_index.get_hot_index().reset(reason=reason)

    def _read_hot_roster(self, index):
        """分页读花名册，返回 (chunk_id 列表, 同序元数据列表)，与整库一次读逐条等价。

        整库一次 get 在大库上是直接报错：向量库把 id 逐个绑进 SQL，条数超过 SQLite
        的 32 766 变量上限就返回 "too many SQL variables"（37 483 chunk 的库实测必炸），
        热集把它当成"不能服务"，于是每次检索都重跑一遍注定失败的整库回读。
        """
        from app.rag import hot_index

        page = index.roster_page
        ids: list[str] = []
        metadatas: list = []
        seen: set[str] = set()
        offset = 0
        # 止步用常数上限，不用 collection.count()：为算一个循环边界多发一次读库调用，
        # 就把"暖机只读两笔"这条既存判据改写成三笔（tests/test_r44_hot_index_chroma.py
        # 的 test_open_index_reads_the_store_once_then_not_at_all 钉的正是这个次数）。
        while offset < hot_index.ROSTER_SCAN_ROW_CEILING:
            batch = self.collection.get(limit=page, offset=offset,
                                        include=["metadatas"]) or {}
            page_ids = [str(item) for item in (batch.get("ids") or [])]
            page_metas = list(batch.get("metadatas") or [])
            if not page_ids:
                break
            fresh = 0
            for position, chunk_id in enumerate(page_ids):
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                ids.append(chunk_id)
                metadatas.append(page_metas[position]
                                 if position < len(page_metas) else None)
                fresh += 1
            if fresh == 0 or len(page_ids) < page:
                # 不满一页 = 已到末尾；一页没带来新 id = 后端忽略了 offset，别再转圈。
                break
            offset += page
        return ids, metadatas

    def _warm_hot_index(self, index, scope_key: tuple) -> str:
        """读一次向量库，把花名册与常驻子集建起来。返回空串表示建成，否则是原因码。

        只读不写，而且一次 embedding 都不多发：读回来的向量就是库里那一份。花名册一次
        get(ids+metadatas)，热子集再一次带 embeddings 的 get，且只读预算内的那批 —— 语料超出
        内存预算时宁可整体不用，也不返回一个"少了冷条目"的结果集。
        """
        from app.rag import hot_index

        if not self.stores_vectors:
            return hot_index.REASON_NO_VECTORS
        try:
            ids, roster_metadatas = self._read_hot_roster(index)
        except Exception as exc:
            logger.warning(f"热集读不到向量库花名册，本次退回外部检索: {exc}")
            index.note_warm_failure()
            return hot_index.REASON_COLD
        cold_metadata = {
            chunk_id: (roster_metadatas[position]
                       if position < len(roster_metadatas) and roster_metadatas[position] else {})
            for position, chunk_id in enumerate(ids)
        }
        budget = index.max_chunks
        hot_ids = ids[-budget:] if len(ids) > budget else list(ids)
        resident = {}
        for start, end in self._batch_ranges(len(hot_ids), index.roster_page):
            try:
                loaded = self.collection.get(
                    ids=hot_ids[start:end],
                    include=["documents", "metadatas", "embeddings"]) or {}
            except Exception as exc:
                logger.warning(f"热集读不到向量，本次退回外部检索: {exc}")
                index.note_warm_failure()
                return hot_index.REASON_COLD
            loaded_ids = [str(item) for item in (loaded.get("ids") or [])]
            documents = list(loaded.get("documents") or [])
            metadatas = list(loaded.get("metadatas") or [])
            embeddings = loaded.get("embeddings")
            for position, chunk_id in enumerate(loaded_ids):
                vector = (embeddings[position]
                          if embeddings is not None and position < len(embeddings) else None)
                resident[chunk_id] = (
                    documents[position] if position < len(documents) else None,
                    metadatas[position] if position < len(metadatas) else None,
                    list(vector) if vector is not None else None,
                )
        rows = []
        for chunk_id in ids:
            if chunk_id in resident:
                document, metadata, vector = resident[chunk_id]
                rows.append((chunk_id, document,
                             metadata if metadata else (cold_metadata.get(chunk_id) or {}),
                             vector))
            else:
                rows.append((chunk_id, None, cold_metadata.get(chunk_id) or {}, None))
        index.populate(rows, scope_key=scope_key)
        return ""

    def _pgvector_hits(self, query_embedding, k: int, where: dict | None, *,
                       query: str = ""):
        """R59b：把语义腿问到 PostgreSQL + PGVector。开关关着就一条 SQL 都不发。

        交回 None ＝ 这一腿没答（开关关 / 双写没开 / 连不上 / 过滤器翻译不出来），
        调用方原路退回遗留的 Chroma 腿。退回不等于少一道闸门：Chroma 那条本来就把同一份
        ``where`` 下推给向量库，两条腿都是先过滤再截名次，越权行在名次里压根不占位。

        🔴 R59 块1 判据②(a)：**PG 腿交回 0 行不是合法的"库说没有"**。R269 §5 第①处点名的
        正是这一格——旧写法把 0 行原样交回，用户于是拿到一份空上下文，而整条降级分支只挂在
        "embedding 挂掉"那一支上。这条语义与引擎无关（切读治不到它），所以降级在这里发生：
        交回关键词腿的命中并带稳定码，一问仍只记一笔 search_shape（与 R158 同规）。
        降级走的是 ``_keyword_hits`` 的内容扫描，它不问 ANN——切读之后 Chroma 那条向量索引
        在任何分支上都不再是答复来源，唯一还会问它的是"读腿拒答"那一支（见 search()）。

        答出行时命中的字典仍由 ``_hit_dicts`` 生成（R44 钉的形状），检索腿标注也仍是
        semantic —— 换引擎不是降级。密级为 NULL 的行原样交回 None：R57 的 fail-closed 由
        _hit_dicts 那一处守，本方法不许在这里替它把缺密级补成 1 级。
        """
        from app.rag import indexing as indexing_module
        from app.rag import pg_store

        if not indexing_module.pgvector_reads_enabled():
            return None
        try:
            rows = pg_store.read_topk(query_vector=query_embedding, k=k, where=where)
        except Exception as exc:
            reason = str(getattr(exc, "reason", "") or pg_store.REASON_VECTOR_READ_FAILED)
            logger.warning(f"PGVector 读腿拒答，本次退回遗留 Chroma 腿（{reason}）：{exc}")
            pg_store.note_read_bypass(reason, f"{type(exc).__name__}: {exc}")
            return None
        pg_store.note_read_answered(len(rows))
        if not rows:
            # 判据②(a) 的正身。日志只报形状不报值：where 里是别人的部门名与密级档位，
            # 而这一行随时可能被捞进工单，R158 那条"读数不带正文"的隐私口径同样管日志。
            logger.warning(
                f"PGVector 读腿交回 0 行（请求 {k} 名，"
                f"{'带' if where else '不带'}权限谓词），本次退化为关键词召回"
            )
            degraded = self._keyword_hits(query, k, where,
                                          RETRIEVAL_REASON_PG_ZERO_ROWS)
            self._note_search_shape(
                answered_by=RETRIEVAL_SERVER_KEYWORD_STORE,
                leg=self.MODE_KEYWORD,
                reason=RETRIEVAL_REASON_PG_ZERO_ROWS,
                n_results=k,
                rows_returned=len(degraded),
                hits_built=len(degraded),
                outcome=self._outcome_for(len(degraded), len(degraded)),
            )
            return degraded
        metadatas = [{
            "filename": row.get("filename") or "unknown",
            "chunk_index": row.get("chunk_index"),
            "classification": row.get("classification"),
            "department": row.get("department") or "",
        } for row in rows]
        hits = self._hit_dicts([row.get("content") for row in rows], metadatas,
                               self.MODE_SEMANTIC, "")
        self._note_search(self.MODE_SEMANTIC, "")
        self._note_search_shape(
            answered_by=RETRIEVAL_SERVER_PGVECTOR,
            leg=self.MODE_SEMANTIC,
            reason="",
            n_results=k,
            rows_returned=len(rows),
            hits_built=len(hits),
            outcome=self._outcome_for(len(rows), len(hits)),
        )
        return hits

    def _hot_hits(self, query_embedding, k: int, where: dict | None, pred):
        """热集那一腿：能服务就交回命中字典，不能服务返回 None，调用方原路走外部向量库。

        pre-filter 在这里、并且只在截断之前生效（判据③）：命中的字典仍由 _hit_dicts 生成，与
        向量腿同一个形状定义，检索模式也仍是 semantic —— 热集命中不是降级，它给的就是语义腿
        本该给的那份结果。本方法不发任何新日志：日志语义与 R44 之前逐字一致（判据⑤⑥），观测
        走 hot_index_diagnostics()。
        """
        from app.rag import hot_index
        from app.rag import indexing as indexing_module

        if indexing_module.pgvector_reads_enabled():
            # R59b：热集常驻的是 Chroma 那一份向量。读路径切到 PG 之后它不许再抢答，否则
            # "切了读"只对热集问不出的那部分生效，剩下的大半流量仍在读旧引擎——半切比不切
            # 更难查，因为诊断里它长得像已经切完了。让路不是故障，单独一枚原因码。
            hot_index.note_bypass(hot_index.REASON_READ_BACKEND_SWITCHED)
            return None
        if not hot_index.hot_index_enabled():
            return None
        if k <= 0:
            # k<=0 的既有语义不归本单改，原样交给外部向量库。
            return None
        try:
            index = hot_index.get_hot_index()
            scope_key = self._hot_scope_key()
            index.adopt_scope(scope_key)
            if not index.populated:
                if index.warm_retry_blocked():
                    # 刚失败过：这次直接走外部向量库，不再重跑整库回读。结果与不开
                    # 热集逐条一致，只是照旧记一个 bypass 原因，运维看得见它在退回。
                    hot_index.note_bypass(hot_index.REASON_COLD)
                    return None
                self._warm_hot_index(index, scope_key)
            ranked = index.rank(query_embedding, k, where=where, pred=pred,
                                scope_key=scope_key, stores_vectors=self.stores_vectors)
        except Exception as exc:
            # 一层可丢弃的加速缓存不许把检索问出异常：这里整体退回外部向量库，
            # 结果与不开热集逐条一致，只多一条 warning 与一个稳定原因码（判据⑤的回滚面）。
            logger.warning(f"热集检索异常，本次退回外部向量库: {exc}")
            hot_index.note_bypass(hot_index.REASON_ERROR)
            return None
        if ranked is None:
            return None
        # 热集命中不是降级：检索腿标注与外部向量库那条完全同值（R21 判据④的口径），
        # 所以这里照样过一遍 _note_search，last_search_mode/reason 不会停在上一问的关键词腿。
        self._note_search(self.MODE_SEMANTIC, "")
        hits = self._hit_dicts(
            [item[2] for item in ranked],
            [item[3] for item in ranked],
            self.MODE_SEMANTIC,
            "",
        )
        # R158：热集交回 0 行时外部向量库压根没被问过。把这种 0 记成"HNSW 找不到邻居"就是
        # 假账，所以 answered_by 明确写 hot_index——读数的价值就在于能指名是谁答的。
        self._note_search_shape(
            answered_by=RETRIEVAL_SERVER_HOT_INDEX,
            leg=self.MODE_SEMANTIC,
            reason="",
            n_results=k,
            rows_returned=len(ranked),
            hits_built=len(hits),
            outcome=self._outcome_for(len(ranked), len(hits)),
        )
        return hits

    def _write_batch(self, ids, documents, metadatas, embeddings, *, mirror=None):
        """全库唯一允许把向量交给向量库的入口（R21 判据②）。

        不合格向量在这里抛，写不进去就是写不进去，不做任何"悄悄换成别的值"的处理。
        未来的双写/迁移路径也应当走这里，而不是各自再抄一份 collection.add。

        R58：mirror 是 app/rag/pg_store.py 的 VectorMirror，默认 None。传进来时写序是
        "PG 先、Chroma 次"，commit 由调用方在两腿都写完之后发起 —— 两腿共用调用方那一个
        PG 事务，任何一侧失败都在那里整体回滚。不传（开关关闭，默认）时本函数发出的语句
        与 R58 之前逐条一致，一条新 SQL 都没有。
        """
        if not self.stores_vectors:
            logger.warning("向量库后端不存向量：本次只写入文本与元数据，检索按关键词降级")
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            return
        assert_writable_embeddings(
            embeddings, len(documents), cause=self._embedding_failure_reason()
        )
        if mirror is not None:
            # PG 腿先写：它失败时 Chroma 一个字都没动，调用方回滚一个空事务即可。
            mirror.add(
                ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
            )
            if self._writes_go_to_pgvector():
                # R60 判据①：INDEX_BACKEND=pgvector 时写路径唯一化 —— 这一腿到此为止，
                # 新行只落 PG。代码留在原地不删（判据②）：开关退回 chroma 它就照常接行，
                # 而这一支判定被摘掉之后，第④格那对现取读数当场红。
                # 注意这一支必须排在 mirror 非 None 之内：没有 PG 腿时它一个字节都不许拦，
                # 否则「关遗留腿 + 没开 PG 腿」= 零写。
                logger.info(f"[R60] 停写生效：本批 {len(ids)} 行只落 PostgreSQL，Chroma 不接新行")
                return
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=list(embeddings),
            metadatas=metadatas,
        )

    # ==================== R58 双写镜像钩子 ====================

    def _open_vector_mirror(self):
        """按开关开一条 PGVector 镜像腿；开关关闭（默认）时返回 None。

        返回 None 就是"不装 pgvector 也能跑"的全部机制：本方法一不建连接、二不发 SQL。
        app.rag.pg_store 在函数内 import，因为 pg_store 反过来 import 本模块的稳定码与
        闸门，模块级互引会成循环 import。
        """
        if not self.stores_vectors:
            # 离线 _JsonCollection 后端根本不存向量，没有东西可镜像。
            return None
        from app.rag import pg_store

        return pg_store.vector_mirror()

    def _writes_go_to_pgvector(self) -> bool:
        """R60 判据①②③：这一笔写入/删除里，PostgreSQL 是不是新行的住所。

        三枚条件，一枚比一枚贵，而且本函数一不发 SQL、二不开连接：

        * ``stores_vectors`` —— 离线 ``_JsonCollection`` 没有向量列，没有东西可镜像，那枚
          JSON 文件就是唯一的库；
        * ``pg_store.dual_write_enabled()`` —— 双写关着就没有 PG 腿可交行。那时把遗留腿
          一起关掉不是「停写」，是**零写**：文档上传之后哪一库里都没有它的向量。判据②
          第二把反证刀钉的就是这一格；
        * ``indexing.pgvector_writes_are_primary()`` —— 拨的是``INDEX_BACKEND``那一把既有
          开关，与读路径同一枚调用点、同一处解析（``app/rag/indexing.py`` 的
          ``read_backend()``）。这里不许长出第二把名字里带 BACKEND 的环境变量：两把开关的
          形状不是多一行代码，而是两台机器各拨一把，然后诊断里看着像切完了。

        读部署不等于改部署：本函数只问两枚在册判定，用例用 ``monkeypatch.setenv`` 就能
        把答复翻过来，正反两挡都量得到。
        """
        from app.rag import indexing as indexing_module
        from app.rag import pg_store

        if not self.stores_vectors:
            return False
        return bool(pg_store.dual_write_enabled()
                    and indexing_module.pgvector_writes_are_primary())

    def _document_rows_by_leg(self, filename: str):
        """一份文档的行到底住在哪一库：返回 (遗留腿 ids, 遗留腿 metadatas, PG 行)。

        R60 判据③。遗留腿还接新行的时候，问它「这个文件名有哪些行」就是在问两腿；停写
        之后不成立了 —— 切换之后写的行只存在于 PostgreSQL，还只问遗留腿的删除会一无所获，
        于是它不报错、原样返回，而那份"已删除"的文档继续被检索出来。这一格只能修在**问句**
        那一层：开关停在 ``chroma`` 时本函数照旧只发一次 ``collection.get(where=...)``，
        一条 SQL 都不多问（判据①「行为一字不改」）；开关停在 ``pgvector`` 时它必须也问
        PostgreSQL 一次。

        PG 问不出来是**拒答**，不是退回遗留腿。退回就是拿"遗留腿知道的那些"冒充"这份文档
        的全部"，报出去的是一次没 locating 成功的删除 —— 上传侧的镜像闸门同口径
        （``REASON_VECTOR_MIRROR_UNAVAILABLE``），这里不新造码。
        """
        stored = self.collection.get(where={"filename": filename}) or {}
        legacy_ids = [str(item) for item in (stored.get("ids") or [])]
        legacy_metadatas = list(stored.get("metadatas") or [])
        if not self._writes_go_to_pgvector():
            return legacy_ids, legacy_metadatas, []
        from app.rag import pg_store

        try:
            rows = pg_store.document_vector_rows(filename=filename)
        except Exception as exc:
            raise VectorWriteRejectedError(
                f"拒绝写删向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]: 停写已生效，新行只落 "
                f"PostgreSQL，但 {filename} 的行在 PostgreSQL 那一腿问不出来"
                f"（{type(exc).__name__}: {exc}）—— 问不全的删除只能拒答，不能报成功",
                reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
            ) from exc
        return legacy_ids, legacy_metadatas, rows

    def _vector_snapshot(self, ids):
        """删旧向量前把旧行原样读出，供两腿回滚时逐字放回。

        必须带 embeddings 一起读：不带的话放回时 Chroma 会用默认 embedding function 重算，
        那正是 R22 要挡的"一个库里两套向量"。读不到向量就返回 None，调用方据此放弃这次
        双写（宁可上传失败，也不留下一个无法忠实还原的中间态）。
        """
        try:
            snapshot = self.collection.get(
                ids=list(ids), include=["documents", "metadatas", "embeddings"]
            )
        except Exception as exc:
            logger.warning(f"读取旧向量快照失败，双写无法回滚: {exc}")
            return None
        existing_ids = list(snapshot.get("ids") or [])
        if not existing_ids:
            return {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        vectors = snapshot.get("embeddings")
        if vectors is None or len(vectors) != len(existing_ids):
            logger.warning(f"旧向量快照缺少 embeddings（{len(existing_ids)} 条），放弃双写")
            return None
        return {
            "ids": existing_ids,
            "documents": list(snapshot.get("documents") or []),
            "metadatas": list(snapshot.get("metadatas") or []),
            "embeddings": [list(vector) for vector in vectors],
        }

    def _undo_vector_write(self, mirror, written_ids, snapshot, *, stale_deleted=True):
        """两腿一起退回本次写入之前：PG 回滚事务，Chroma 撤掉新写、放回旧行。

        mirror.rollback() 是硬要求：PG 侧的失败定义就是"这个事务一个向量都不留"。Chroma
        侧是 best-effort（撤不动就记日志，业务异常照样往上抛），因为 Chroma 没有事务，能
        做的只有逆序补偿；补偿失败的窗口写进交付说明的"必须业主真机"清单。

        stale_deleted 必须是 Chroma 那一次 delete 真的成功之后才为真：没删过就不能凭空
        add 一遍，否则"回滚"本身会变成一次写入。
        """
        try:
            mirror.rollback()
        except Exception as exc:
            logger.error(f"向量镜像回滚失败，PG 事务状态未知: {exc}")
        try:
            if written_ids and not self._writes_go_to_pgvector():
                # R60 判据③：停写态里这批 id 从没进过遗留腿，撤它们就等于删掉上一版
                # 还留在 Chroma 里的那些行 —— 补偿只能撤"本次真写过的"，没写过就不许动手。
                self.collection.delete(ids=list(written_ids))
            if stale_deleted and snapshot and snapshot.get("ids"):
                self.collection.add(
                    ids=snapshot["ids"],
                    documents=snapshot["documents"],
                    metadatas=snapshot["metadatas"],
                    embeddings=snapshot["embeddings"],
                )
        except Exception as exc:
            logger.error(f"Chroma 腿补偿回滚未完成，需人工核对双写状态: {exc}")
        # R44：无论补偿成没成，这次写入都不算数了，热集整体作废，下一次检索重读向量库。
        self._note_hot_reset("vector_write_rolled_back")

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
        # 检查是否已存在同名文件。这里只记下旧 id，删除动作推迟到向量合格之后。
        # R60 判据③：这一个问题现在必须由两腿各自回答，见 _document_rows_by_leg。
        legacy_ids, legacy_metadatas, pg_rows = self._document_rows_by_leg(filename)
        pg_ids = [str(row.get("vector_id")) for row in pg_rows if row.get("vector_id")]
        stale_ids = list(dict.fromkeys(pg_ids + legacy_ids))
        if stale_ids:
            old_hash = (legacy_metadatas[0].get("hash", "") if legacy_metadatas
                        else str(pg_rows[0].get("hash") or ""))
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

        # R58：镜像腿在"先验后删"之后才开。开关关闭（默认）时 mirror 是 None，从这里
        # 往下发出的调用序列与本文件在 R58 之前逐条一致：一次 delete、若干次 add、没有
        # commit，也没有一条 SQL。
        mirror = self._open_vector_mirror()
        snapshot = None
        written_ids = []
        stale_deleted = False
        try:
            if mirror is not None and legacy_ids:
                # 删之前先留快照：PG 侧的回滚是事务级的，Chroma 侧只能靠它逆序放回。
                # R60 判据③：快照只读遗留腿**真正持有**的那批 id。只住在 PG 的行没有 Chroma
                # 副本可放回，硬读一份空快照再把 stale_deleted 记成真，等于把"放不回去"
                # 写成"放得回去"。开关在 chroma 时 legacy_ids == stale_ids，与今天逐字同形。
                snapshot = self._vector_snapshot(legacy_ids)
                if snapshot is None:
                    raise VectorWriteRejectedError(
                        f"拒绝写入向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]: 双写已开启，"
                        f"但 {filename} 的旧向量读不出快照，删掉就无法忠实还原",
                        reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
                    )
            if stale_ids:
                if mirror is not None:
                    # PG 那一腿删的是并集全量：它持有的行必须一次删干净。
                    mirror.delete(ids=list(stale_ids))
                if legacy_ids:
                    # R60 判据③：遗留腿只删它自己持有的那些。删 PG 而把同名旧行留在
                    # Chroma 里，就是本判据点名的孤儿形状 —— 回滚到 chroma 那一档时，
                    # 客户已删的文档会自己活回来。
                    self.collection.delete(ids=legacy_ids)
                    stale_deleted = True
                logger.info(f"已删除旧版本: {filename}")
                # R44：删掉的旧向量在热集里也不能留下（判据④同名重传那一半）。
                # R60 判据③：交回的是两腿并起来的全集 —— 热集是进程内的账，它不认识
                # "行住在哪一库"，只认"这些 id 不再有效"。
                self._note_hot_delete(stale_ids)

            batch_size = 2000
            for start, end in self._batch_ranges(len(chunks), batch_size):
                self._write_batch(
                    ids=ids[start:end],
                    documents=chunks[start:end],
                    embeddings=embeddings[start:end],
                    metadatas=metadatas[start:end],
                    mirror=mirror,
                )
                written_ids.extend(ids[start:end])
            if mirror is not None:
                # 两腿都写完才 commit：这个 PG 事务里躺着本次全部删与写，提交失败就整体退回。
                mirror.commit()
        except Exception:
            if mirror is not None:
                self._undo_vector_write(mirror, written_ids, snapshot,
                                        stale_deleted=stale_deleted)
            raise
        finally:
            if mirror is not None:
                mirror.close()

        # R44：两腿都写完、mirror 也已 close 之后才告知热集，用的就是刚写进库的那批向量，
        # 所以热集与库同源，不会再算一遍 embedding。开关关闭时这个调用一个字节都不写。
        self._note_hot_write(written_ids, chunks, metadatas, embeddings)

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

    def search(self, query: str, k: int = 5, where: dict | None = None,
               pred=None) -> list[dict]:
        """语义检索。where 为权限过滤（下推到向量库），None 不过滤

        R21：embedding 不可用时不再拿占位零向量去问向量库（那等于问不出任何排序信息，
        却装作问过），而是把这一路退化成关键词召回，并把原因码写进命中与
        last_search_reason。两条腿的权限过滤都发生在截断之前。

        R44：新增的 pred 只被热集那一腿消费（不传就是 None，热集仍按 where 逐条预过滤），
        外部向量库那条路径的调用序列与本单之前逐字一致。把同一个权限谓词在热集截断之前再过
        一遍，是因为热集是进程内的本地扫描：它没有"下推"这回事，不显式过滤就会把别人的高分
        chunk 排进名次里再丢掉，那正是 R45 裁掉的召回饥饿形态。
        """
        if self.stores_vectors:
            try:
                query_embedding = self.embedding.embed_query(query)
            except EmbeddingError as exc:
                logger.error(f"向量腿下线，本次检索退化为关键词召回: {exc}")
                degraded = self._keyword_hits(query, k, where, exc.reason)
                self._note_search_shape(
                    answered_by=RETRIEVAL_SERVER_KEYWORD_STORE,
                    leg=self.MODE_KEYWORD,
                    reason=exc.reason,
                    n_results=k,
                    rows_returned=len(degraded),
                    hits_built=len(degraded),
                    outcome=self._outcome_for(len(degraded), len(degraded)),
                )
                return self._apply_activity_prior(degraded)
            hot_hits = self._hot_hits(query_embedding, k, where, pred)
            if hot_hits is not None:
                return self._apply_activity_prior(hot_hits)
            # R59b：开关在 pgvector 时这一腿答；开关在 chroma 时它一个调用都不发，
            # 下面的遗留腿与切读之前逐字一致（同 R44 给热集那条立的规矩）。
            # R59 块1 判据②(a)：这一腿交回 0 行时它自己降级，交回来的永远是"可以直接用的
            # 命中"，所以 None 只可能意味着"这一腿没答"，不再意味着"PG 库里没有"。
            pg_hits = self._pgvector_hits(query_embedding, k, where, query=query)
            if pg_hits is not None:
                return self._apply_activity_prior(pg_hits)
            kwargs = {"query_embeddings": [query_embedding], "n_results": k}
            if where:
                kwargs["where"] = where
            # 🔴 R158 判据②(d)：这一步此前**没有** try/except，向量库抛异常就一路抛出
            # search()，不存在"我们把异常吞成空列表"。本单把它改成"先记下形状、再原样上抛"，
            # 语义一个字没变（调用方看到的仍然是异常），变的只是事后读得到是谁、要了几行。
            try:
                results = self.collection.query(**kwargs) or {}
            except Exception as exc:
                self._note_search_shape(
                    answered_by=RETRIEVAL_SERVER_CHROMA,
                    leg=self.MODE_SEMANTIC,
                    reason="",
                    n_results=k,
                    rows_returned=0,
                    hits_built=0,
                    outcome=RETRIEVAL_OUTCOME_STORE_FAILED,
                    store_error=type(exc).__name__,
                )
                raise
            self._note_search(self.MODE_SEMANTIC, "")
            # R46：先验只在这条腿自己排好的候选集内部挪名次。n_results 一个字没改——多要
            # 几行才能让低于第 k 名的文档上位，但那会改掉 R44 明确钉住的"外部向量库那条路径
            # 的调用序列与本单之前逐字一致"，本单不碰（要放宽得另立单，已写进回执）。所以
            # R46 的"回填"目前只作用于召回窗口之内，窗口外的先验等 next-result 那一单。
            documents = (results.get("documents") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            hits = self._hit_dicts(documents, metadatas, self.MODE_SEMANTIC, "")
            # 行数取三列里最宽的那个：ids 才是"库给了几行"的本体，而 documents/metadatas
            # 可能因 include 形状缺列。只数 documents 会把"给了 5 行、建出 0 条命中"记成
            # "库里没邻居"——那正是判据③要分开的两种 0。
            rows_returned = max(
                self._store_row_count(results, "ids"),
                self._store_row_count(results, "documents"),
                self._store_row_count(results, "metadatas"),
            )
            self._note_search_shape(
                answered_by=RETRIEVAL_SERVER_CHROMA,
                leg=self.MODE_SEMANTIC,
                reason="",
                n_results=k,
                rows_returned=rows_returned,
                hits_built=len(hits),
                outcome=self._outcome_for(rows_returned, len(hits)),
            )
            return self._apply_activity_prior(hits)
        offline_hits = self._keyword_hits(query, k, where, self.REASON_STORE_OFFLINE)
        self._note_search_shape(
            answered_by=RETRIEVAL_SERVER_KEYWORD_STORE,
            leg=self.MODE_KEYWORD,
            reason=self.REASON_STORE_OFFLINE,
            n_results=k,
            rows_returned=len(offline_hits),
            hits_built=len(offline_hits),
            outcome=self._outcome_for(len(offline_hits), len(offline_hits)),
        )
        return self._apply_activity_prior(offline_hits)

    def _apply_activity_prior(self, hits):
        """R46：把采纳/驳回计数施加在这条腿刚排好的候选集上（四条腿共用这一处）。

        读不到计数＝没有先验＝把**同一个列表对象**原序交回（fail-open，裁定理由见模块里
        R46 那段注释）。判定可见性的仍是 filters.py 那一处，本方法一个候选都不增减：两路先验
        都只在**已经合法**的候选集内部挪名次，且共用同一根位移界（signal_prior_value）。
        """
        try:
            priors = self._activity_prior_loader() or {}
        except Exception as exc:  # pragma: no cover - 默认 loader 已自兜底，只防注入的 loader 抛错
            logger.warning(f"活动信号先验不可用，本次排序不动: {type(exc).__name__}")
            return hits
        # R46 差格 a：点击/浏览并进来。🔴 getattr 守卫不是防御性冗余——tests/test_r525_* 拿
        # SimpleNamespace(_activity_prior_loader=...) 直呼本方法，那些载体上没有第二路读取方；
        # 缺属性就只用采纳/驳回，这正是"一路缺席不抹掉另一路"的口径。
        engagement_loader = getattr(self, "_engagement_prior_loader", None)
        if engagement_loader is not None:
            try:
                priors = merge_signal_priors(priors, engagement_loader() or {})
            except Exception as exc:  # pragma: no cover - 默认 loader 已自兜底，只防注入的抛错
                logger.warning(f"点击/浏览先验不可用，本次只用采纳/驳回: {type(exc).__name__}")
        return rank_hits_by_activity(hits, priors, enabled=activity_prior_enabled())

    def _collection_name(self) -> str:
        """这一问打的是哪个 collection。离线态没有名字，交回空串而不是猜一个。"""
        return str(getattr(self.collection, "name", "") or "")

    @staticmethod
    def _store_row_count(results, key: str) -> int:
        """数向量库原始应答里某一列的行数：只认 list/tuple，其它一律 0。

        为什么要单独数 ids：query 交回的 documents/metadatas 可能因为 include 的形状而比 ids
        少（甚至缺列），只数 documents 会把"库给了 5 行、我们建成了 0 条命中"误记成"库里
        就没邻居"——那正是 R158 要能分辨的两种 0。
        """
        rows = (results or {}).get(key)
        if not isinstance(rows, (list, tuple)) or not rows:
            return 0
        first = rows[0]
        return len(first) if isinstance(first, (list, tuple)) else 0

    def _note_search_shape(self, *, answered_by: str, leg: str, reason: str, n_results: int,
                           rows_returned: int, hits_built: int, outcome: str,
                           store_error: str = "") -> None:
        """把这一问的形状记进模块级读数（判据③）。不发 IO、不改返回形状。"""
        _record_search_shape(
            collection=self._collection_name(),
            answered_by=answered_by,
            leg=leg,
            reason=reason,
            n_results=n_results,
            rows_returned=rows_returned,
            hits_built=hits_built,
            outcome=outcome,
            store_error=store_error,
        )

    @staticmethod
    def _outcome_for(rows_returned: int, hits_built: int) -> str:
        """结局码：0 命中时，"库本来就没给行"与"给了行却在我们将要交回前丢了"必须分家。"""
        if hits_built > 0:
            return RETRIEVAL_OUTCOME_ANSWERED
        return (RETRIEVAL_OUTCOME_ROWS_DROPPED if rows_returned > 0
                else RETRIEVAL_OUTCOME_ZERO_ROWS)

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
        """列出已索引的文档名。

        R60 判据③：「已索引」这份名单由持有行的那一库回答。停写之后还只问遗留腿，名单会
        停在切换那一刻 —— 之后上传的每一枚文档都不在名单里，而它明明能被供应商检索出来，
        端点 app/api/v1/chat.py:4786 拿的就是这份名单去过滤可见文档。
        """
        if self._writes_go_to_pgvector():
            from app.rag import pg_store

            return pg_store.indexed_document_names()
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
        never reads or writes embeddings here.

        R60 判据③ changes which store it asks: while the legacy leg still accepts new
        rows it is the only complete answer, and after the write-stop the rows are in
        PostgreSQL. Reading them from the legacy directory instead would publish a
        retirement record for a document that has none -- or, on a same-name re-upload,
        publish the *previous* version's chunks as the current ones, which is worse than
        the empty answer.
        """
        if self._writes_go_to_pgvector():
            from app.rag import pg_store

            return [
                {
                    "vector_id": str(row.get("vector_id") or ""),
                    "content": str(row.get("content") or ""),
                    "chunk_index": int(row.get("chunk_index") or 0),
                    # NULL 原样交回 None，不补 1：R57 的 fail-closed 对两条腿是同一条规则。
                    # 下面遗留腿那一行还留着的默认值不归本单改，判定见本函数 docstring 与
                    # R57 §1 站点③（消费方只读 content / vector_id / hash 三键）。
                    "classification": row.get("classification"),
                    "department": row.get("department") or "",
                    "hash": str(row.get("hash") or ""),
                }
                for row in pg_store.document_vector_rows(filename=filename)
            ]
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
        """删除指定文档的所有向量

        R58：开关开启时两腿同事务双删 —— PG 先删、Chroma 后删、最后 commit，任一侧失败
        就回滚 PG 事务并原样抛出，不留"PG 无向量 ⇔ Chroma 仍可检索"的半态。开关关闭
        （默认）时这里仍然只有一次 get 与一次 delete，行为与本单之前一致。
        """
        # R60 判据③：这一问句是整条删除链的要害。停写之后新行只住 PostgreSQL，
        # 只问遗留腿就在这里一无所获 —— 它会静悄悄地 return，端点报删除成功，而那份文档
        # 的每一行还留在 chunk_vectors 里继续被检索。两腿各问各的，谁持有谁被删。
        legacy_ids, _legacy_metadatas, pg_rows = self._document_rows_by_leg(filename)
        pg_ids = [str(row.get("vector_id")) for row in pg_rows if row.get("vector_id")]
        stored_ids = list(dict.fromkeys(pg_ids + legacy_ids))
        if not stored_ids:
            return
        mirror = self._open_vector_mirror()
        snapshot = None
        stale_deleted = False
        try:
            if mirror is not None:
                if legacy_ids:
                    # 同 add_document：读得出旧向量才敢删，否则回滚时无货可放回。
                    snapshot = self._vector_snapshot(legacy_ids)
                    if snapshot is None:
                        raise VectorWriteRejectedError(
                            f"拒绝删除向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]: 双写已开启，"
                            f"但 {filename} 的旧向量读不出快照，删掉就无法忠实还原",
                            reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
                        )
                # PG 删全集（它持有的那些行一枚都不许留下），Chroma 只删它自己持有的那些。
                mirror.delete(ids=list(stored_ids))
            if legacy_ids:
                self.collection.delete(ids=legacy_ids)
                stale_deleted = True
            # R44：文档删除 ⇒ 热集对应条目必须失效（判据④）。R60 判据③：全集交回。
            self._note_hot_delete(stored_ids)
            if mirror is not None:
                mirror.commit()
        except Exception:
            if mirror is not None:
                self._undo_vector_write(mirror, [], snapshot, stale_deleted=stale_deleted)
            raise
        finally:
            if mirror is not None:
                mirror.close()
        logger.info(f"已删除文档: {filename}")
