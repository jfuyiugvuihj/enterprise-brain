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
    REASON_VECTOR_MIRROR_UNAVAILABLE: "向量镜像（PostgreSQL）不可用，已拒绝写入",
    REASON_VECTOR_MIRROR_SCOPE_MISMATCH: "向量镜像的维度或模型口径与运行时不一致，已拒绝写入",
    REASON_VECTOR_MIRROR_WRITE_FAILED: "向量镜像写入失败，Chroma 与 PostgreSQL 已一并回滚",
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
    """
    if not enabled or not isinstance(hits, list) or not hits:
        return hits
    lookup = priors or {}
    strengths = [activity_prior_value(lookup.get(_hit_source(hit))) for hit in hits]
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

    def __init__(self, chroma_dir: str = "./chroma_db", *, activity_prior=None):
        os.makedirs(chroma_dir, exist_ok=True)
        self.chroma_dir = chroma_dir
        # R46：计数表的读取方可注入（测试不连库也能验排序），默认走进程内缓存的
        # 整表快照。注入一个返回 {} 的 callable 就等于关掉先验，不改排序语义。
        self._activity_prior_loader = activity_prior or activity_priors
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

    def _hot_hits(self, query_embedding, k: int, where: dict | None, pred):
        """热集那一腿：能服务就交回命中字典，不能服务返回 None，调用方原路走外部向量库。

        pre-filter 在这里、并且只在截断之前生效（判据③）：命中的字典仍由 _hit_dicts 生成，与
        向量腿同一个形状定义，检索模式也仍是 semantic —— 热集命中不是降级，它给的就是语义腿
        本该给的那份结果。本方法不发任何新日志：日志语义与 R44 之前逐字一致（判据⑤⑥），观测
        走 hot_index_diagnostics()。
        """
        from app.rag import hot_index

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
        return self._hit_dicts(
            [item[2] for item in ranked],
            [item[3] for item in ranked],
            self.MODE_SEMANTIC,
            "",
        )

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
            if written_ids:
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

        # R58：镜像腿在"先验后删"之后才开。开关关闭（默认）时 mirror 是 None，从这里
        # 往下发出的调用序列与本文件在 R58 之前逐条一致：一次 delete、若干次 add、没有
        # commit，也没有一条 SQL。
        mirror = self._open_vector_mirror()
        snapshot = None
        written_ids = []
        stale_deleted = False
        try:
            if mirror is not None and stale_ids:
                # 删之前先留快照：PG 侧的回滚是事务级的，Chroma 侧只能靠它逆序放回。
                snapshot = self._vector_snapshot(stale_ids)
                if snapshot is None:
                    raise VectorWriteRejectedError(
                        f"拒绝写入向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]: 双写已开启，"
                        f"但 {filename} 的旧向量读不出快照，删掉就无法忠实还原",
                        reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
                    )
            if stale_ids:
                if mirror is not None:
                    mirror.delete(ids=list(stale_ids))
                self.collection.delete(ids=stale_ids)
                stale_deleted = True
                logger.info(f"已删除旧版本: {filename}")
                # R44：删掉的旧向量在热集里也不能留下（判据④同名重传那一半）。
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
                return self._apply_activity_prior(self._keyword_hits(query, k, where, exc.reason))
            hot_hits = self._hot_hits(query_embedding, k, where, pred)
            if hot_hits is not None:
                return self._apply_activity_prior(hot_hits)
            kwargs = {"query_embeddings": [query_embedding], "n_results": k}
            if where:
                kwargs["where"] = where
            results = self.collection.query(**kwargs) or {}
            self._note_search(self.MODE_SEMANTIC, "")
            # R46：先验只在这条腿自己排好的候选集内部挪名次。n_results 一个字没改——多要
            # 几行才能让低于第 k 名的文档上位，但那会改掉 R44 明确钉住的"外部向量库那条路径
            # 的调用序列与本单之前逐字一致"，本单不碰（要放宽得另立单，已写进回执）。所以
            # R46 的"回填"目前只作用于召回窗口之内，窗口外的先验等 next-result 那一单。
            return self._apply_activity_prior(
                self._hit_dicts(
                    (results.get("documents") or [[]])[0],
                    (results.get("metadatas") or [[]])[0],
                    self.MODE_SEMANTIC,
                    "",
                )
            )
        return self._apply_activity_prior(self._keyword_hits(query, k, where, self.REASON_STORE_OFFLINE))

    def _apply_activity_prior(self, hits):
        """R46：把采纳/驳回计数施加在这条腿刚排好的候选集上（四条腿共用这一处）。

        读不到计数＝没有先验＝把**同一个列表对象**原序交回（fail-open，裁定理由见模块里
        R46 那段注释）。判定可见性的仍是 filters.py 那一处，本方法一个候选都不增减。
        """
        try:
            priors = self._activity_prior_loader() or {}
        except Exception as exc:  # pragma: no cover - 默认 loader 已自兜底，只防注入的 loader 抛错
            logger.warning(f"活动信号先验不可用，本次排序不动: {type(exc).__name__}")
            return hits
        return rank_hits_by_activity(hits, priors, enabled=activity_prior_enabled())

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
        """删除指定文档的所有向量

        R58：开关开启时两腿同事务双删 —— PG 先删、Chroma 后删、最后 commit，任一侧失败
        就回滚 PG 事务并原样抛出，不留"PG 无向量 ⇔ Chroma 仍可检索"的半态。开关关闭
        （默认）时这里仍然只有一次 get 与一次 delete，行为与本单之前一致。
        """
        existing = self.collection.get(where={"filename": filename})
        if not existing["ids"]:
            return
        mirror = self._open_vector_mirror()
        snapshot = None
        stale_deleted = False
        try:
            if mirror is not None:
                # 同 add_document：读得出旧向量才敢删，否则回滚时无货可放回。
                snapshot = self._vector_snapshot(existing["ids"])
                if snapshot is None:
                    raise VectorWriteRejectedError(
                        f"拒绝删除向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]: 双写已开启，"
                        f"但 {filename} 的旧向量读不出快照，删掉就无法忠实还原",
                        reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
                    )
                mirror.delete(ids=list(existing["ids"]))
            self.collection.delete(ids=existing["ids"])
            stale_deleted = True
            # R44：文档删除 ⇒ 热集对应条目必须失效（判据④）。
            self._note_hot_delete(existing["ids"])
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
