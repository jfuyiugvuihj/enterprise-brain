"""Redis 缓存 + 限流。本地开发用 fakeredis，生产换 REDIS_URL 环境变量。"""
import os
import hashlib
import json
import time
from datetime import datetime
from app.common.logger import logger

try:
    import fakeredis
except ModuleNotFoundError:  # pragma: no cover
    fakeredis = None

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis = None

DEFAULT_ANSWER_CACHE_TTL_SECONDS = 1800
DEFAULT_MEMORY_CACHE_MAX_ENTRIES = 1024


def _positive_int_env(name: str, default: int) -> int:
    """读一个正整数环境变量：没配、配坏、配成 0 或负数一律退回默认值。"""
    raw = str(os.getenv(name, "") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def answer_cache_ttl_seconds() -> int:
    """答案缓存的存活时间，默认 30 分钟，可用 ANSWER_CACHE_TTL_SECONDS 收紧。"""
    return _positive_int_env("ANSWER_CACHE_TTL_SECONDS", DEFAULT_ANSWER_CACHE_TTL_SECONDS)


def get_redis():
    """获取 Redis 连接（单例）"""
    global _redis
    if _redis is None:
        if _REDIS_URL:
            import redis
            _redis = redis.from_url(_REDIS_URL)
            logger.info("使用外部 Redis: %s", _REDIS_URL)
        else:
            if fakeredis is not None:
                _redis = fakeredis.FakeRedis()
            else:
                _redis = _MemoryRedis()
            logger.info("使用 fakeredis（本地模拟）")
    return _redis


class _MemoryRedis:
    """没有 Redis 时的进程内回退实现。

    旧实现把 setex 的 TTL 参数直接丢掉、expire 是空操作，所以只要 REDIS_URL 没配，落在这
    条回退路径上的缓存就永不过期、也没有容量上限：一条带权限的旧答案会永久可读，进程内存
    随提问数单调上涨。私有化单机上这两件事都是硬伤，所以这里把过期和淘汰都做真：到期即视为
    不存在（惰性删除 + 写入时顺带清扫），超过 max_entries 按"最久没被碰"淘汰。
    """

    def __init__(self, max_entries: int | None = None):
        self._kv: dict[str, object] = {}
        self._expires_at: dict[str, float] = {}
        self._z: dict[str, list] = {}
        budget = max_entries if max_entries else _positive_int_env(
            "ANSWER_CACHE_MAX_ENTRIES", DEFAULT_MEMORY_CACHE_MAX_ENTRIES
        )
        self._max_entries = max(int(budget), 1)

    def delete(self, key):
        self._kv.pop(key, None)
        self._expires_at.pop(key, None)
        self._z.pop(key, None)

    def _is_expired(self, key: str) -> bool:
        expires_at = self._expires_at.get(key)
        if expires_at is None or expires_at > time.time():
            return False
        self.delete(key)
        return True

    def _sweep(self) -> None:
        now = time.time()
        for key, expires_at in list(self._expires_at.items()):
            if expires_at <= now:
                self.delete(key)

    def _touch(self, key: str) -> None:
        """把键挪到 dict 末尾：dict 保序，队首就是最久没被碰的那条。"""
        if key in self._kv:
            self._kv[key] = self._kv.pop(key)

    def setex(self, key, ttl, value):
        self._sweep()
        self._expires_at.pop(key, None)
        seconds = float(ttl or 0)
        if seconds > 0:
            self._expires_at[key] = time.time() + seconds
        self._kv.pop(key, None)
        self._kv[key] = value
        while len(self._kv) > self._max_entries:
            self.delete(next(iter(self._kv)))

    def get(self, key):
        if self._is_expired(key) or key not in self._kv:
            return None
        self._touch(key)
        return self._kv[key]

    def expire(self, key, ttl):
        seconds = float(ttl or 0)
        if seconds <= 0:
            return False
        self._expires_at[key] = time.time() + seconds
        return True

    def zremrangebyscore(self, key, _min, _max):
        if self._is_expired(key):
            return 0
        items = self._z.get(key, [])
        self._z[key] = [(m, s) for m, s in items if s > _max]
        return len(items) - len(self._z[key])

    def zcard(self, key):
        if self._is_expired(key):
            return 0
        return len(self._z.get(key, []))

    def zadd(self, key, mapping):
        self._is_expired(key)
        self._z.setdefault(key, [])
        for member, score in mapping.items():
            self._z[key].append((member, score))
        return len(mapping)


# ==================== 缓存 ====================

def _hash(question: str) -> str:
    return hashlib.md5(question.strip().encode()).hexdigest()[:12]


def answer_cache_scope(principal=None, username: str = "") -> str:
    """缓存作用域标识：只有作用域完全相同的调用者才允许回读同一条缓存。

    口径对齐 app/rag/filters.py:54 resolve_document_retrieval_scope 真正读进去的授权输入
    —— 用户身份、部门（含兼任部门）、密级、角色与权限、账号状态 —— 而不是只带一个用户号。
    判定"这两次调用能不能共用一条缓存"的标准是"当时那套授权输入能不能整体复现"，不是"是不
    是同一个人"：同一账号换了部门之后，问题文本一个字都没变，但他上一轮在旧部门拿到的答案里可能
    正引用着他现在已经无权检索的文档，按用户号命中就等于把越权内容回读给他。密级升降、
    administrator 与 staff（部门谓词不同）、权限集合变化、账号停用，都是同样的道理。

    仍然不做跨用户共享：共享要求两人授权输入完全等价，而文档归属（owner_id）无法由角色或部门
    推断出来。多带维度只会让缓存更窄、更不可能误命中。
    """
    if principal is None:
        identity = str(username or "")
        return f"user:{identity}" if identity else "user:anonymous"

    identity = str(getattr(principal, "user_id", "") or getattr(principal, "username", "") or "")
    user_part = f"user:{identity}" if identity else "user:anonymous"
    department = str(getattr(principal, "department", "") or "")
    departments = sorted({str(v) for v in (getattr(principal, "department_ids", None) or []) if str(v)})
    roles = sorted({str(v) for v in (getattr(principal, "roles", None) or []) if str(v)})
    if not roles:
        single_role = str(getattr(principal, "role", "") or "")
        roles = [single_role] if single_role else []
    permissions = sorted({str(v) for v in (getattr(principal, "permissions", None) or []) if str(v)})
    permissions_digest = hashlib.md5(",".join(permissions).encode()).hexdigest()[:12]
    clearance = getattr(principal, "clearance", "")
    clearance_label = str(getattr(principal, "clearance_label", "") or "")
    status = str(getattr(principal, "status", "") or "")
    return "|".join(
        [
            user_part,
            f"dept:{department}",
            f"depts:{'|'.join(departments)}",
            f"clr:{clearance}/{clearance_label}",
            f"roles:{'|'.join(roles)}",
            f"perms:{permissions_digest}",
            f"status:{status}",
        ]
    )


def _scope_part(scope: str) -> str:
    """作用域为空时沿用历史键，未升级的调用方不会落到另一份键空间。"""
    if not scope:
        return ""
    return f"{hashlib.md5(scope.encode()).hexdigest()[:12]}:"


def _answer_key(question: str, scope: str) -> str:
    return f"answer:{_scope_part(scope)}{_hash(question)}"


def cache_answer(question: str, answer: str, scope: str = "", ttl: int | None = None) -> None:
    """缓存最终回答，并把"这条答案是什么时候生成的"一起存进去。

    不许伪装成实时答案，所以命中时必须能报出出生时间，值里就得带 created_at。旧版本在同一
    个键上存过裸字符串：那种记录说不清生成时间、也就无法标注，一律当作不可信数据丢掉（宁可多
    算一次），不回读给任何人。
    """
    seconds = answer_cache_ttl_seconds() if ttl is None else max(int(ttl), 1)
    record = {"answer": answer, "created_at": int(time.time())}
    get_redis().setex(_answer_key(question, scope), seconds, json.dumps(record, ensure_ascii=False))


def get_cached_answer_record(question: str, scope: str = "") -> dict | None:
    """读一条答案缓存记录，返回 {"answer", "created_at"}；没有或不可信就返回 None。

    命中与否只由键决定（键里已经带了 scope），这里不再叠第二套判定：作用域口径只有
    answer_cache_scope 一个，两处判反而会让"键里漏了 scope"这种错法看不出来。
    """
    val = get_redis().get(_answer_key(question, scope))
    if not val:
        return None
    text = val.decode() if isinstance(val, bytes) else val
    try:
        record = json.loads(text)
    except (TypeError, ValueError):
        logger.warning("[Cache] 丢弃不可解析的答案缓存: %s", question[:30])
        return None
    if not isinstance(record, dict):
        return None
    answer = record.get("answer")
    created_at = record.get("created_at")
    if not isinstance(answer, str) or not answer:
        return None
    if not isinstance(created_at, (int, float)) or isinstance(created_at, bool) or created_at <= 0:
        return None
    return {"answer": answer, "created_at": float(created_at)}


def get_cached_answer(question: str, scope: str = "") -> str | None:
    """获取缓存的回答（签名保持不变：调用方和既有测试都桩这个函数）。"""
    record = get_cached_answer_record(question, scope=scope)
    return record["answer"] if record else None


def answer_cache_origin(question: str, scope: str = "") -> dict | None:
    """命中答案的出处，供响应体标注"缓存结果 · 生成于 …"。"""
    record = get_cached_answer_record(question, scope=scope)
    if record is None:
        return None
    created_at = record["created_at"]
    moment = datetime.fromtimestamp(created_at)
    return {
        "generated_at": created_at,
        "generated_at_iso": moment.astimezone().isoformat(timespec="seconds"),
        "generated_at_text": f"缓存结果 · 生成于 {moment.strftime('%Y-%m-%d %H:%M:%S')}",
    }


# 原来的"语义缓存"（cache_semantic_answer / get_semantic_cached_answer / clear_semantic_cache
# / _SEMANTIC_CACHE / _semantic_key）和 dispatch 决策缓存（cache_dispatch / get_cached_dispatch）
# 已在 R35 删除：app/** 零调用方，唯一"调用者"是单测，属生产死代码。其实现是字符集合 Jaccard
# + 进程内 dict + 无 TTL/无淘汰/无作用域，既不能跨 worker 共享，也没有可用的相似度语义。
# 按"Redis + 向量相似度 + scope 硬过滤"重建的前提是有一条可以不打模型的假 embedding 通道，
# 否则判据②（跨部门/跨密级 0 命中）无法离线取证，故本轮退回删除，不留半套实现。


# ==================== 限流 ====================

def check_rate_limit(username: str, max_per_minute: int = 10) -> tuple[bool, int]:
    """检查用户请求频率。返回 (是否允许, 剩余次数)"""
    r = get_redis()
    key = f"ratelimit:{username}"
    now = int(time.time())
    window = now - 60  # 60 秒窗口

    # 清理过期记录
    r.zremrangebyscore(key, 0, window)
    # 统计当前窗口内请求数
    count = r.zcard(key)
    remaining = max_per_minute - count

    if count >= max_per_minute:
        return False, 0

    # 记录本次请求
    r.zadd(key, {str(now): now})
    r.expire(key, 120)  # key 2 分钟后自动清理
    return True, remaining - 1