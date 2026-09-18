"""R44 热集进程内检索索引：一层可丢弃的加速缓存，不是第二个事实源。

计划书 §5.2 的立论是"进程内 HNSW ≈0.0015 ms，穿到外部向量库要 1–5 ms"。本模块把覆盖绝大
多数查询的热集合常驻进程内，省掉那几毫秒的往返。边界钉死成三条：

1. **权威永远在向量库**。向量唯一的入库入口是 DocumentRetriever._write_batch()（R21
   判据②），本模块不写库、不删库、不做第三条写腿，只在写成功之后*被告知*新增了什么、
   删掉了什么。热集里不允许存在"只有这里知道"的事实。
2. **pre-filter 先于热集**（R45/R57 口径）。权限判定发生在热集给出结果之前：候选按分数
   降序逐条过谓词，不认的条目连名次都不占，截断只作用在合法候选上。任何跨部门/超密级内容
   不会因为"先在热集里命中"而短暂可见。
3. **能不能服务是可判定的**。热集只有在"没常驻的那批 chunk 在本次过滤条件下一条都不会被
   向量库召回"时才允许给出结果；判不定就整体不用，绝不返回一个"少了冷条目"的近似结果集。
   这条让判据②（同序同 id）在语义上是恒等而不是近似。

缓存条目一律带 R22 的 embedding scope 标识（backend + 模型 + 维度 + 索引版本），跨版本永不
复用；换模型/换维度等于全量作废。本模块绝不缓存 query → 结果集，否则一次权限口径变化就会
把上一个 principal 的答案泄漏给下一个。

默认关闭（HOT_INDEX_ENABLED 未设置即关，不认识的值也算关），关闭时本模块一个字节的状态都
不留、一次 embedding 请求都不多发。

R79 在这层补了两样不改变检索语义的东西：常驻向量下沉成 float32 缓冲（判据③，省内存而
名次逐位不变），以及 hot_index_snapshot() 这个独立观测出口（判据①）。后者不是重复造轮子：
hot_index_diagnostics() 的形状被 tests/test_r44_hot_index_chroma.py 用精确相等钉成五个键，
配置态与实例态塞不进去，只能另开一个出口给 /health/details 读。
"""

from __future__ import annotations

import os
import threading
import time
from array import array
from dataclasses import dataclass

try:  # numpy 缺席时退回纯 python 距离：热集只是加速器，装不上就整体不用，绝不影响主路径
    import numpy as _NP
except ImportError:  # pragma: no cover - 取决于环境
    _NP = None

TRUE_VALUES = {"1", "true", "yes", "on"}

#: 开关与容量。默认关，行为与 R44 之前逐字一致；容量单位是 chunk 数。
HOT_INDEX_ENV = "HOT_INDEX_ENABLED"
HOT_INDEX_MAX_CHUNKS_ENV = "HOT_INDEX_MAX_CHUNKS"
DEFAULT_MAX_CHUNKS = 20_000

#: 花名册可信时长。跨进程写入在本进程内不可见（单机单 worker 时不存在，多 worker 时是已
#: 知限制），所以超时后强制重读向量库，而不是永远信任内存。
HOT_INDEX_MAX_AGE_SECONDS_ENV = "HOT_INDEX_ROSTER_TTL_SECONDS"
DEFAULT_ROSTER_TTL_SECONDS = 300.0

#: 暖机回读的分页大小。向量库把 id 逐个绑进 SQL，一次取的条数超过 SQLite 的 32 766
#: 变量上限会直接报错（实测 37 483 chunk 的库整库 get 报 "too many SQL variables"），
#: 所以花名册与常驻子集只能分页读，任何一次 get 的条数都不超过它。
HOT_INDEX_ROSTER_PAGE_ENV = "HOT_INDEX_ROSTER_PAGE"
DEFAULT_ROSTER_PAGE = 1_000

#: 分页扫描的行数上限，只为止步用，不是容量承诺。
ROSTER_SCAN_ROW_CEILING = 2_000_000

#: 暖机失败之后的重试冷却（秒）。不冷却 = 每一次检索都重跑一遍注定失败的整库回读，
#: 加速层反过来把检索拖慢；冷却期内直接走外部向量库，结果与不开热集逐条一致。
HOT_INDEX_WARM_RETRY_SECONDS_ENV = "HOT_INDEX_WARM_RETRY_SECONDS"
DEFAULT_WARM_RETRY_SECONDS = 60.0

#: 不可服务的稳定原因码。观测只读这些码，不读日志。
REASON_DISABLED = "hot_index_disabled"
REASON_COLD = "hot_index_cold"
REASON_STALE_ROSTER = "hot_index_roster_stale"
REASON_SCOPE_MISMATCH = "hot_index_scope_mismatch"
REASON_INCOMPLETE = "hot_index_incomplete"
REASON_NO_VECTORS = "hot_index_store_without_vectors"
REASON_NO_QUERY_VECTOR = "hot_index_no_query_vector"
#: 热集自己出了任何意外（读回的形状不对、谓词抛错……）都算"不能服务"，绝不让一层缓存
#: 把检索问出异常来。原因码单独一个，运维看得到，不会被误读成"缓存没命中"。
REASON_ERROR = "hot_index_error"

_DIAGNOSTICS: dict = {
    "hits": 0,
    "misses": 0,
    "invalidations": 0,
    "resident_chunks": 0,
    "last_bypass_reason": "",
}
_DIAGNOSTICS_LOCK = threading.Lock()


def hot_index_diagnostics() -> dict:
    """进程内只记账的观测出口，形状对齐 embedding_diagnostics / vector_mirror_diagnostics。

    只读内存计数，不发请求、不读文件、不改变任何检索行为（判据⑥）。

    ⚠️ 这五个键的形状是钉死的：tests/test_r44_hot_index_chroma.py 既断言"读一眼前后
    全等"，又断言全等字典就是这五项，加键必红。要往运维面上添东西请走
    hot_index_snapshot()（R79 判据①），别改这里。
    """
    with _DIAGNOSTICS_LOCK:
        return {
            "hits": _DIAGNOSTICS["hits"],
            "misses": _DIAGNOSTICS["misses"],
            "invalidations": _DIAGNOSTICS["invalidations"],
            "resident_chunks": _DIAGNOSTICS["resident_chunks"],
            "last_bypass_reason": _DIAGNOSTICS["last_bypass_reason"],
        }


def reset_hot_index_diagnostics() -> None:
    """测试与进程启动用的计数归零；不触碰索引内容。"""
    with _DIAGNOSTICS_LOCK:
        _DIAGNOSTICS["hits"] = 0
        _DIAGNOSTICS["misses"] = 0
        _DIAGNOSTICS["invalidations"] = 0
        _DIAGNOSTICS["resident_chunks"] = 0
        _DIAGNOSTICS["last_bypass_reason"] = ""


def _note_hit() -> None:
    with _DIAGNOSTICS_LOCK:
        _DIAGNOSTICS["hits"] += 1
        _DIAGNOSTICS["last_bypass_reason"] = ""


def _note_bypass(reason: str) -> None:
    with _DIAGNOSTICS_LOCK:
        _DIAGNOSTICS["misses"] += 1
        _DIAGNOSTICS["last_bypass_reason"] = reason


def note_bypass(reason: str) -> None:
    """公开的稳定码记账入口：调用方（retriever）自己判定不服务时也走同一个计数器。"""
    _note_bypass(reason)


def _note_invalidations(count: int) -> None:
    if count <= 0:
        return
    with _DIAGNOSTICS_LOCK:
        _DIAGNOSTICS["invalidations"] += count


def _note_resident(count: int) -> None:
    with _DIAGNOSTICS_LOCK:
        _DIAGNOSTICS["resident_chunks"] = count


def hot_index_enabled() -> bool:
    """开关：未设置、空、或任何不认识的值都算关闭（与 R58 dual_write_enabled 同一口径）。"""
    raw = str(os.getenv(HOT_INDEX_ENV, "") or "").strip().lower()
    return raw in TRUE_VALUES


def _int_env(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name, "") or "").strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    try:
        value = float(str(os.getenv(name, "") or "").strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _ttl_env() -> float:
    try:
        value = float(str(os.getenv(HOT_INDEX_MAX_AGE_SECONDS_ENV, "") or "").strip())
    except (TypeError, ValueError):
        return DEFAULT_ROSTER_TTL_SECONDS
    return value if value > 0 else DEFAULT_ROSTER_TTL_SECONDS


@dataclass(frozen=True)
class HotChunk:
    """一条常驻 chunk：文本、元数据、向量，外加它属于哪个索引口径。

    scope_key 是 R22 门禁的缓存版：条目自报它是在哪一套（backend, 模型, 维度, 索引版本）下
    算出来的，与当前口径不一致的条目既不会被检索，也不算有效。

    vector 是 R79 判据③下沉出来的紧凑形态：array('f')，每维 4 字节。原先这里是
    tuple(float, ...)，768 维就是 768 个 24 字节的 Python float 对象挂在 6 字节的
    指针数组上 —— 语料到了 37 483 chunk 量级，这笔差额才是热集真正的大头。存进来的
    向量本来就源于向量库落盘的那份 float32，换成 float32 缓冲不丢分量；距离照旧在
    float64 上累加（_squared_l2），名次与下沉前逐位一致。
    """

    chunk_id: str
    document: str
    metadata: dict
    vector: array
    scope_key: tuple


def _compact_vector(values) -> array:
    """把一条向量落成 float32 缓冲（R79 判据③）。

    这里只做一次窄化：float64 → float32 最近舍入。落进向量库的那一份同样是 float32，
    所以这一舍让热集与外部库更同源，不是更远；形状与取值仍然不在这里检查 ——
    不合格向量在 _write_batch 就进不了库，本模块不抄第二份校验。
    """
    return array("f", values)


def _matches_metadata(metadata: dict, where) -> bool:
    """向量库 where 子句在进程内的等价判定，实现只在 app/rag/retriever.py 有一份。

    这里不抄第二份：离线 _JsonCollection 与热集共用同一个匹配器，两处语义不可能分叉。
    """
    from app.rag.retriever import metadata_matches  # 延迟导入，避开 retriever 与本模块成环

    return metadata_matches(metadata, where)


def _float64_view(values):
    """按需把一条向量摊成 float64 缓冲；numpy 缺席时原样交回，纯 python 路径自己逐项 float()。

    查询向量在 rank() 里过一次这里（每个候选都重新转换一遍查询是白干的活），常驻向量每个
    候选过一次。float32 → float64 是精确升位，所以下沉存储之后这里得到的数与下沉前
    从 tuple 转换出来的逐位相同。
    """
    if _NP is None:
        return values
    return _NP.asarray(values, dtype="float64")


def _squared_l2(vector, query_vector) -> float:
    """与 Chroma 默认 l2 距离同序的平方欧氏距离（开方单调，不影响名次）。

    累加精度是 R79 判据③的硬约束：常驻侧存 float32，这一句照样升到 float64 再算，
    所以下沉存储只改了内存账，没改任何一个距离数值。想改成 float32 累加之前，
    先想想 tests/test_r79_vector_store.py 那批对照用例。
    """
    if _NP is not None:
        diff = _NP.asarray(vector, dtype="float64") - _NP.asarray(query_vector, dtype="float64")
        return float(diff @ diff)
    return sum((float(a) - float(b)) ** 2 for a, b in zip(vector, query_vector))


def _doc_key(chunk_id: str, metadata: dict) -> str:
    """一条 chunk 属于哪篇文档：元数据里有 filename 就用它，否则退回 id 的前缀。"""
    return str((metadata or {}).get("filename") or chunk_id.rsplit("_", 1)[0])


class HotSetIndex:
    """进程内热集：花名册 + 常驻子集 + 逐条 pre-filter 的精确扫描。

    实例不判断"该不该用"，它只回答"这批常驻条目能不能覆盖本次过滤条件"；覆盖不了就返回
    None，让调用方原路回到向量库。
    """

    def __init__(self, *, max_chunks: int | None = None,
                 roster_ttl_seconds: float | None = None,
                 roster_page: int | None = None,
                 warm_retry_seconds: float | None = None,
                 clock=time.monotonic):
        self._lock = threading.RLock()
        #: 常驻条目（含向量与文本）
        self._entries: dict[str, HotChunk] = {}
        #: 已知存在于向量库、但没常驻的 chunk id → 元数据（只用于"会不会被召回"判定）
        self._cold: dict[str, dict] = {}
        #: 插入序，决定淘汰顺序（写序是热度的近似）
        self._order: list[str] = []
        self._heat: dict[str, float] = {}
        self._scope_key: tuple | None = None
        self._populated = False
        self._built_at = 0.0
        self._last_reset_reason = ""
        self._clock = clock
        self._max_chunks = (max_chunks if max_chunks is not None
                           else _int_env(HOT_INDEX_MAX_CHUNKS_ENV, DEFAULT_MAX_CHUNKS))
        self._roster_ttl = (roster_ttl_seconds if roster_ttl_seconds is not None
                           else _ttl_env())
        self._roster_page = (roster_page if roster_page is not None
                             else _int_env(HOT_INDEX_ROSTER_PAGE_ENV, DEFAULT_ROSTER_PAGE))
        self._warm_retry_seconds = (warm_retry_seconds
                                    if warm_retry_seconds is not None
                                    else _float_env(HOT_INDEX_WARM_RETRY_SECONDS_ENV,
                                                    DEFAULT_WARM_RETRY_SECONDS))
        #: 上一次暖机失败之后，到这个时刻（monotonic）之前不再重试
        self._warm_retry_after = 0.0

    # ---------- 生命周期 ----------

    def _clear_locked(self, *, reason: str = "") -> int:
        dropped = len(self._entries)
        self._entries.clear()
        self._cold.clear()
        self._order.clear()
        self._heat.clear()
        self._populated = False
        self._built_at = 0.0
        self._last_reset_reason = reason
        #: 作废说明库里的内容或口径变了，下一次允许再试一次暖机
        self._warm_retry_after = 0.0
        _note_invalidations(dropped)
        _note_resident(0)
        return dropped

    def reset(self, *, reason: str = "") -> int:
        """全量作废（索引版本切换、后端不存向量、冷启动）。返回丢掉的常驻条目数。"""
        with self._lock:
            return self._clear_locked(reason=reason)

    def adopt_scope(self, scope_key: tuple) -> str:
        """把当前口径记在索引上；口径变了 ⇒ 旧条目一条都不留（R22 的缓存版）。"""
        with self._lock:
            previous = self._scope_key
            if previous is not None and previous != scope_key:
                if self._populated or self._entries:
                    self._clear_locked(reason=REASON_SCOPE_MISMATCH)
                else:
                    self._last_reset_reason = REASON_SCOPE_MISMATCH
                self._scope_key = scope_key
                return "reset"
            self._scope_key = scope_key
            return "kept"

    @property
    def scope_key(self):
        with self._lock:
            return self._scope_key

    @property
    def resident_chunks(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def cold_chunks(self) -> int:
        with self._lock:
            return len(self._cold)

    @property
    def max_chunks(self) -> int:
        """常驻预算（单位 chunk）。暖机按它决定从向量库回读多少条，本方法不改预算。"""
        with self._lock:
            return self._max_chunks

    @property
    def last_reset_reason(self) -> str:
        """最近一次"整批作废"的原因码，粘住不清：重建本身不该抹掉"上一次为什么全丢"。"""
        with self._lock:
            return self._last_reset_reason

    @property
    def roster_page(self) -> int:
        """一次从向量库最多回读多少条：调用方必须按它分页，不许整库一次读。"""
        with self._lock:
            return self._roster_page

    def warm_retry_blocked(self) -> bool:
        """暖机刚失败过 ⇒ 冷却期内不再重跑整库回读（每次检索都失败一遍是负收益）。"""
        with self._lock:
            return self._warm_retry_after > self._clock()

    def note_warm_failure(self) -> None:
        """记一次暖机失败：冷却到 _clock() + 退避秒数。成功 populate 会清掉它。"""
        with self._lock:
            self._warm_retry_after = self._clock() + self._warm_retry_seconds

    def _fresh_locked(self) -> bool:
        """花名册是否可信：只有刚整批读过向量库、且没超过 TTL 时才是。"""
        if not self._populated:
            return False
        if self._roster_ttl <= 0:
            return True
        return (self._clock() - self._built_at) <= self._roster_ttl

    @property
    def populated(self) -> bool:
        with self._lock:
            return self._fresh_locked()

    def state(self) -> dict:
        """只读实例态（R79 判据①）：不发请求、不读库、不改任何检索行为。

        这里给的是"这一本索引现在到底是什么样子"：预算、TTL、页大小是构造时按环境变量
        解析出来的那一份，花名册新鲜度与冷却态是当下时刻的那一份。运维要靠它们区分
        "预算装不下语料"与"刚暖机失败在冷却"，光看 bypass 原因码分不出来。
        """
        with self._lock:
            now = self._clock()
            return {
                "max_chunks": self._max_chunks,
                "roster_ttl_seconds": self._roster_ttl,
                "roster_page": self._roster_page,
                "warm_retry_seconds": self._warm_retry_seconds,
                "resident_chunks": len(self._entries),
                "cold_chunks": len(self._cold),
                "roster_built": self._populated,
                "roster_fresh": self._fresh_locked(),
                "roster_age_seconds": (round(now - self._built_at, 3)
                                       if self._populated else None),
                "warm_retry_blocked": self._warm_retry_after > now,
                "last_reset_reason": self._last_reset_reason,
                "scope_key": (list(self._scope_key) if self._scope_key else None),
            }

    # ---------- 维护：只被写路径告知，永不主动写库 ----------

    def populate(self, rows, *, scope_key: tuple) -> dict:
        """用向量库读回的一批 (chunk_id, document, metadata, vector) 重建热集。

        vector 为 None 的行进冷表：它们确实存在于库里，只是没向量可用，所以只能挡覆盖
        判定，绝不能被当成"没有这一条"。
        """
        admitted = 0
        cold = 0
        with self._lock:
            if self._scope_key is not None and self._scope_key != scope_key:
                self._clear_locked(reason=REASON_SCOPE_MISMATCH)
            self._scope_key = scope_key
            self._entries.clear()
            self._cold.clear()
            self._order.clear()
            self._heat.clear()
            for chunk_id, document, metadata, vector in rows:
                chunk_id = str(chunk_id)
                metadata = dict(metadata or {})
                if vector is None or document is None or len(self._entries) >= self._max_chunks:
                    # 预算耗尽时新行进冷表，已常驻的一条都不动：宁可整体不用，不可少给结果。
                    self._cold[chunk_id] = metadata
                    cold += 1
                    continue
                self._entries[chunk_id] = HotChunk(
                    chunk_id=chunk_id, document=str(document), metadata=metadata,
                    vector=_compact_vector(vector), scope_key=scope_key)
                self._order.append(chunk_id)
                self._heat.setdefault(_doc_key(chunk_id, metadata), self._clock())
                admitted += 1
            self._populated = True
            self._built_at = self._clock()
            self._warm_retry_after = 0.0
            _note_resident(len(self._entries))
        return {"resident": admitted, "cold": cold}

    def note_write(self, *, ids, documents, metadatas, embeddings, scope_key: tuple) -> None:
        """向量已经写进库之后被告知一次：这些行按新向量入热集，旧的同名行作废。

        同名重传由 note_delete(旧 id) + note_write(新 id) 同一条路径覆盖；传进来的向量与
        库里的完全同源，所以这里一次 embedding 都不多发。
        """
        ids = list(ids)
        metadatas = list(metadatas or [])
        documents = list(documents or [])
        embeddings = list(embeddings or [])
        with self._lock:
            if not self._populated:
                return
            if self._scope_key is not None and self._scope_key != scope_key:
                self._clear_locked(reason=REASON_SCOPE_MISMATCH)
                return
            self._scope_key = scope_key
            for position, chunk_id in enumerate(ids):
                chunk_id = str(chunk_id)
                metadata = (dict(metadatas[position])
                            if position < len(metadatas) and metadatas[position] else {})
                self._entries.pop(chunk_id, None)
                self._cold.pop(chunk_id, None)
                if chunk_id in self._order:
                    self._order.remove(chunk_id)
                vector = (embeddings[position]
                          if position < len(embeddings) and embeddings[position] is not None else None)
                document = documents[position] if position < len(documents) else None
                if vector is None or document is None:
                    self._cold[chunk_id] = metadata
                    continue
                self._entries[chunk_id] = HotChunk(
                    chunk_id=chunk_id, document=str(document), metadata=metadata,
                    vector=_compact_vector(vector), scope_key=scope_key)
                self._order.append(chunk_id)
                # 刚写进库的文档就是当下最热的：不登记 heat 的话它排在淘汰序最前，
                # 一次上传换来的是"马上被挤出去"，热集就白暖了。
                self._heat[_doc_key(chunk_id, metadata)] = self._clock()
            self._evict_locked()
            _note_resident(len(self._entries))

    def note_delete(self, ids, *, scope_key: tuple | None = None) -> int:
        """文档删除：热集条目与冷表条目都必须走，一个都不留。"""
        ids = [str(chunk_id) for chunk_id in (ids or [])]
        with self._lock:
            if not self._populated:
                return 0
            if (scope_key is not None and self._scope_key is not None
                    and scope_key != self._scope_key):
                self._clear_locked(reason=REASON_SCOPE_MISMATCH)
                return 0
            dropped = 0
            for chunk_id in ids:
                if self._entries.pop(chunk_id, None) is not None:
                    dropped += 1
                    if chunk_id in self._order:
                        self._order.remove(chunk_id)
                self._cold.pop(chunk_id, None)
            _note_invalidations(dropped)
            _note_resident(len(self._entries))
            return dropped

    def _evict_locked(self) -> None:
        """超预算时按"最久没被查到"的整篇文档淘汰到冷表。

        淘汰只搬走向量与文本，元数据留在冷表里，覆盖判定才做得下去；被淘汰的文档只能等
        下一次 populate() 回来——查询路径上绝不为了召回一条冷条目去读库，那正是本单要省
        掉的那几毫秒。
        """
        overflow = len(self._entries) - self._max_chunks
        if overflow <= 0:
            return
        by_document: dict[str, list[str]] = {}
        for chunk_id in self._order:
            entry = self._entries.get(chunk_id)
            if entry is not None:
                by_document.setdefault(_doc_key(chunk_id, entry.metadata), []).append(chunk_id)
        for filename in sorted(by_document, key=lambda name: self._heat.get(name, 0.0)):
            if overflow <= 0:
                break
            for chunk_id in by_document[filename]:
                entry = self._entries.pop(chunk_id, None)
                if entry is None:
                    continue
                self._cold[chunk_id] = dict(entry.metadata)
                self._order.remove(chunk_id)
                overflow -= 1
            self._heat.pop(filename, None)

    # ---------- 服务判定 ----------

    def _bypass_locked(self, *, scope_key, where, pred, stores_vectors, query_vector) -> str:
        if not hot_index_enabled():
            return REASON_DISABLED
        if not stores_vectors:
            return REASON_NO_VECTORS
        if query_vector is None:
            return REASON_NO_QUERY_VECTOR
        if scope_key is not None and self._scope_key is not None and scope_key != self._scope_key:
            return REASON_SCOPE_MISMATCH
        if not self._populated or not self._entries:
            return REASON_COLD
        if not self._fresh_locked():
            return REASON_STALE_ROSTER
        for metadata in self._cold.values():
            if self._could_be_recalled_locked(metadata, where, pred):
                return REASON_INCOMPLETE
        return ""

    def bypass_reason(self, *, scope_key: tuple | None = None, where: dict | None = None,
                      pred=None, stores_vectors: bool = True, query_vector=None) -> str:
        """本次能不能用热集：空串是能，否则是稳定原因码（判据⑤的回滚面）。"""
        with self._lock:
            return self._bypass_locked(scope_key=scope_key, where=where, pred=pred,
                                        stores_vectors=stores_vectors, query_vector=query_vector)

    def _could_be_recalled_locked(self, metadata: dict, where, pred) -> bool:
        """冷条目会不会被向量库召回：where 与权限谓词都得过，才算"会"。

        元数据缺键时按 None 交给谓词（fail-closed，与 app/rag/filters.py 的 allows 同义），
        不补 1 级、不补空串，避免 R57 那类"凭空造密级"。
        """
        if not _matches_metadata(metadata, where):
            return False
        if pred is None:
            return True
        return bool(pred({
            "classification": metadata.get("classification"),
            "department": metadata.get("department"),
        }))

    def rank(self, query_vector, k: int, *, where: dict | None = None, pred=None,
             scope_key: tuple | None = None, stores_vectors: bool = True):
        """在常驻条目上按平方 L2 升序取前 k 条；不能服务时返回 None。

        pre-filter 逐条发生在截断之前（判据③，与 R45 的 BM25"先筛后取"同构）：不认的条目
        连名次都不占，所以受限用户不会因为热集里躺着别人的高分文档而饿死，跨部门内容也不
        会先被"命中"再被丢掉。
        """
        with self._lock:
            reason = self._bypass_locked(scope_key=scope_key, where=where, pred=pred,
                                          stores_vectors=stores_vectors, query_vector=query_vector)
            if reason:
                _note_bypass(reason)
                return None
            scored = []
            #: 查询向量每个查询只升位一次：逐候选再转一遍是白干的活（R79 判据③）。
            #: _float64_view 交回的值与在 _squared_l2 里就地转换完全同值，名次不受影响。
            query = _float64_view(query_vector)
            for chunk_id, entry in self._entries.items():
                if not _matches_metadata(entry.metadata, where):
                    continue
                if pred is not None and not bool(pred({
                        "classification": entry.metadata.get("classification"),
                        "department": entry.metadata.get("department")})):
                    continue
                scored.append((_squared_l2(entry.vector, query), chunk_id, entry))
            scored.sort(key=lambda item: (item[0], item[1]))
            picked = scored[:k] if k > 0 else []
            now = self._clock()
            for _distance, chunk_id, entry in picked:
                self._heat[_doc_key(chunk_id, entry.metadata)] = now
        _note_hit()
        return [(distance, chunk_id, entry.document, dict(entry.metadata))
                for distance, chunk_id, entry in picked]


#: 进程内唯一实例。DocumentRetriever 每次检索都可能新建，所以状态不能挂在实例上（与
#: retriever._DIAGNOSTICS / pg_store._DIAGNOSTICS 同一形状：模块级、加锁、只记账）。
_HOT_INDEX = HotSetIndex()


def get_hot_index() -> HotSetIndex:
    """进程内热集单例。"""
    return _HOT_INDEX


def reset_hot_index(*, reason: str = "") -> int:
    """测试与口径切换用的全量作废；返回丢掉的常驻条目数。"""
    return _HOT_INDEX.reset(reason=reason)


def hot_index_config() -> dict:
    """配置态：把 HOT_INDEX_* 按真实解析口径过一遍，与实例无关。

    这里读的是 `_int_env` / `_ttl_env` / `_float_env` 本身，不是抄一份默认值，所以
    "环境变量没生效"和"出厂默认值被改了"在这一块里都会照实显形。
    """
    return {
        "enabled": hot_index_enabled(),
        "max_chunks": _int_env(HOT_INDEX_MAX_CHUNKS_ENV, DEFAULT_MAX_CHUNKS),
        "roster_ttl_seconds": _ttl_env(),
        "roster_page": _int_env(HOT_INDEX_ROSTER_PAGE_ENV, DEFAULT_ROSTER_PAGE),
        "warm_retry_seconds": _float_env(HOT_INDEX_WARM_RETRY_SECONDS_ENV,
                                         DEFAULT_WARM_RETRY_SECONDS),
    }


def hot_index_snapshot() -> dict:
    """R79 判据①：给 /health/details 用的完整观测出口。

    与 hot_index_diagnostics() 分家是逼出来的，也是该的：那份账的形状被 R44 用例用
    精确相等钉死（五个键），本出口则一次给全"关没关、按什么配置在跑、常驻多少、
    上一次为什么绕行"。三块拼出来的顺序有意义：

    * 先取那本五个键的旧账，保证 hits / misses / invalidations / last_bypass_reason
      与进程内计数器同源同名；
    * 再盖实例态：resident_chunks 以 len(entries) 为准（旧账里那个数是写路径登记的副本，
      两者必须相等 —— 相等这件事由用例钉，不在这里自我修饰），max_chunks /
      roster_ttl_seconds 这些也是**实例真正在用的那一份**，运维要看的就是它；
    * 最后并列一份 env_config：环境变量此刻解析成什么。单例是 import 时建的，那之后
      改环境变量不会回头改它，两个数并排放才看得出"改了没生效"。enabled 单独提到顶层，
      因为它只有"此刻"这个口径 —— 没有一个开关态会随实例定格在半路。

    开关关闭时本函数照样返回完整一块并如实标 enabled=False：运维要分得清"没装这层"
    与"装了但关了"，靠的就是这一块在场而 enabled 为假。
    """
    snapshot = hot_index_diagnostics()
    snapshot.update(_HOT_INDEX.state())
    snapshot["env_config"] = hot_index_config()
    snapshot["enabled"] = hot_index_enabled()
    return snapshot


def current_scope_key(*, index_version_id: str = "") -> tuple:
    """热集条目所属口径：(backend, 模型, 维度, 索引版本 id)。

    模型与维度直接取 app/rag/indexing.py 的 configured_embedding_scope()，也就是 R22 门禁
    用的同一个口径源，本模块不自成一套；不缓存，因为测试与运维都会就地改这些值。
    """
    from app.rag.indexing import INDEX_BACKEND, configured_embedding_scope

    scope = configured_embedding_scope()
    return (INDEX_BACKEND, scope.embedding_model, scope.dimension, str(index_version_id or ""))
