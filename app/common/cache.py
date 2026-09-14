"""Redis 缓存 + 限流。本地开发用 fakeredis，生产换 REDIS_URL 环境变量。"""
import os
import hashlib
import json
import time
from app.common.logger import logger

try:
    import fakeredis
except ModuleNotFoundError:  # pragma: no cover
    fakeredis = None

_REDIS_URL = os.getenv("REDIS_URL", "")
_redis = None


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
    def __init__(self):
        self._kv = {}
        self._z = {}

    def setex(self, key, _ttl, value):
        self._kv[key] = value

    def get(self, key):
        return self._kv.get(key)

    def zremrangebyscore(self, key, _min, _max):
        items = self._z.get(key, [])
        self._z[key] = [(m, s) for m, s in items if s > _max]

    def zcard(self, key):
        return len(self._z.get(key, []))

    def zadd(self, key, mapping):
        self._z.setdefault(key, [])
        for member, score in mapping.items():
            self._z[key].append((member, score))

    def expire(self, key, _ttl):
        return None


# ==================== 缓存 ====================

def _hash(question: str) -> str:
    return hashlib.md5(question.strip().encode()).hexdigest()[:12]


def answer_cache_scope(principal=None, username: str = "") -> str:
    """缓存作用域标识：只有作用域完全相同的调用者才允许回读同一条缓存。

    答案和调度决策的内容取决于调用者的授权输入（可读文档、可读数据集、密级），
    所以缓存键必须带上调用者身份。此前键里只有问题文本，一次带权限的检索结果会
    被回读给没有同等权限的人。作用域按用户隔离，不做跨用户共享：共享要求“两人
    授权输入完全等价”，而文档归属（owner_id）无法由角色或部门推断出来。
    """
    if principal is not None:
        identity = str(getattr(principal, "user_id", "") or getattr(principal, "username", "") or "")
    else:
        identity = str(username or "")
    return f"user:{identity}" if identity else "user:anonymous"


def _scope_part(scope: str) -> str:
    """作用域为空时沿用历史键，未升级的调用方不会落到另一份键空间。"""
    if not scope:
        return ""
    return f"{hashlib.md5(scope.encode()).hexdigest()[:12]}:"


def cache_dispatch(question: str, workers: list[str], scope: str = "") -> None:
    """缓存 dispatch 决策：问题 → 该派哪些 worker"""
    r = get_redis()
    key = f"dispatch:{_scope_part(scope)}{_hash(question)}"
    r.setex(key, 3600, json.dumps(workers))  # 1 小时过期


def get_cached_dispatch(question: str, scope: str = "") -> list[str] | None:
    """获取缓存的 dispatch 决策，命中返回 workers 列表，未命中返回 None"""
    r = get_redis()
    key = f"dispatch:{_scope_part(scope)}{_hash(question)}"
    val = r.get(key)
    if val:
        workers = json.loads(val)
        logger.info("[Cache] dispatch 命中: %s → %s", question[:30], workers)
        return workers
    return None


def cache_answer(question: str, answer: str, scope: str = "") -> None:
    """缓存最终回答"""
    r = get_redis()
    key = f"answer:{_scope_part(scope)}{_hash(question)}"
    r.setex(key, 1800, answer)  # 30 分钟


def get_cached_answer(question: str, scope: str = "") -> str | None:
    """获取缓存的回答"""
    r = get_redis()
    key = f"answer:{_scope_part(scope)}{_hash(question)}"
    val = r.get(key)
    if val:
        logger.info("[Cache] answer 命中: %s", question[:30])
        return val.decode() if isinstance(val, bytes) else val
    return None


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


_SEMANTIC_CACHE = {}


def _semantic_key(question: str) -> str:
    return "".join(sorted(question.strip()))


def cache_semantic_answer(question: str, answer: str) -> None:
    _SEMANTIC_CACHE[_semantic_key(question)] = answer


def get_semantic_cached_answer(question: str) -> str | None:
    if not question:
        return None
    qset = set(question.strip())
    best_score = 0.0
    best_answer = None
    for key, answer in _SEMANTIC_CACHE.items():
        kset = set(key)
        score = len(qset & kset) / max(len(qset | kset), 1)
        if score > best_score:
            best_score = score
            best_answer = answer
    return best_answer if best_score >= 0.35 else None


def clear_semantic_cache() -> None:
    _SEMANTIC_CACHE.clear()
