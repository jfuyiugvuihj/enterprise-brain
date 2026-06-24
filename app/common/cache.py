"""Redis 缓存 + 限流。本地开发用 fakeredis，生产换 REDIS_URL 环境变量。"""
import os
import hashlib
import json
import time
from app.common.logger import logger

# fakeredis 是 Redis 的纯 Python 实现，API 完全兼容
import fakeredis

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
            _redis = fakeredis.FakeRedis()
            logger.info("使用 fakeredis（本地模拟）")
    return _redis


# ==================== 缓存 ====================

def _hash(question: str) -> str:
    return hashlib.md5(question.strip().encode()).hexdigest()[:12]


def cache_dispatch(question: str, workers: list[str]) -> None:
    """缓存 dispatch 决策：问题 → 该派哪些 worker"""
    r = get_redis()
    key = f"dispatch:{_hash(question)}"
    r.setex(key, 3600, json.dumps(workers))  # 1 小时过期


def get_cached_dispatch(question: str) -> list[str] | None:
    """获取缓存的 dispatch 决策，命中返回 workers 列表，未命中返回 None"""
    r = get_redis()
    key = f"dispatch:{_hash(question)}"
    val = r.get(key)
    if val:
        workers = json.loads(val)
        logger.info("[Cache] dispatch 命中: %s → %s", question[:30], workers)
        return workers
    return None


def cache_answer(question: str, answer: str) -> None:
    """缓存最终回答"""
    r = get_redis()
    key = f"answer:{_hash(question)}"
    r.setex(key, 1800, answer)  # 30 分钟


def get_cached_answer(question: str) -> str | None:
    """获取缓存的回答"""
    r = get_redis()
    key = f"answer:{_hash(question)}"
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
