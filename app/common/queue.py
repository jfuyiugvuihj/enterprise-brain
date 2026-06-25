"""
Layer 5 — Redis 队列削峰
当瞬时请求超过处理能力时，入队等待而非直接拒绝。

架构:
  请求 → rate_limit_check
         ├─ 未超限 → 直接处理
         └─ 超限 → enqueue → 返回队列位置
                         └─ 后台 worker 取出处理 → 缓存结果
"""

import json
import time
import uuid
from app.common.cache import get_redis
from app.common.logger import logger


# 队列 Key 前缀
_QUEUE_KEY = "ezn:request_queue"       # Redis List — 待处理请求
_PROCESSING_KEY = "ezn:processing"     # Redis Set — 正在处理的 request_id
_RESULT_PREFIX = "ezn:result:"         # Redis String — 处理结果 (前缀 + request_id)
_QUEUE_TIMEOUT = 300                   # 队列中最大等待时间 (秒)


def enqueue_request(user_message: str, session_id: str, username: str = "anonymous") -> dict:
    """
    将请求加入队列。

    Returns:
        {
            "queued": True,
            "request_id": "xxx",
            "position": 3,        # 前面还有几个在排队
            "estimated_wait": 15  # 预估等待秒数
        }
    """
    r = get_redis()
    request_id = uuid.uuid4().hex[:16]

    payload = json.dumps({
        "request_id": request_id,
        "user_message": user_message,
        "session_id": session_id,
        "username": username,
        "enqueued_at": time.time(),
    }, ensure_ascii=False)

    # 入队 (RPUSH — 队尾加入)
    r.rpush(_QUEUE_KEY, payload)

    # 计算队列位置 (前面有多少个)
    position = r.llen(_QUEUE_KEY)

    # 估算等待时间 (假设每个请求平均 10 秒)
    estimated_wait = position * 10

    logger.info(f"[Queue] 入队 request_id={request_id} pos={position} wait~{estimated_wait}s")

    return {
        "queued": True,
        "request_id": request_id,
        "position": position,
        "estimated_wait": estimated_wait,
    }


def dequeue_request(timeout: float = 300.0) -> dict | None:
    """
    从队列取出一个请求 (BLPOP 阻塞式，超时返回 None)。

    用于后台 worker: 启动后循环调用此函数，有请求就处理。

    Returns:
        None  — 超时，队列为空
        dict  — {"request_id", "user_message", "session_id", "username", "enqueued_at"}
    """
    r = get_redis()
    result = r.blpop(_QUEUE_KEY, timeout=timeout)
    if result is None:
        return None

    _, payload = result
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning(f"[Queue] 无法解析队列消息: {payload[:100]}")
        return None

    # 检查是否超时 (在队列中等待太久)
    wait_time = time.time() - data.get("enqueued_at", time.time())
    if wait_time > _QUEUE_TIMEOUT:
        logger.info(f"[Queue] 请求 {data['request_id']} 在队列中等待 {wait_time:.0f}s，超时丢弃")
        return None

    # 标记为处理中
    r.sadd(_PROCESSING_KEY, data["request_id"])
    r.expire(_PROCESSING_KEY, 600)

    logger.info(f"[Queue] 出队 request_id={data['request_id']} (等待 {wait_time:.0f}s)")
    return data


def store_result(request_id: str, result_text: str, ttl: int = 1800):
    """存储处理结果 (供客户端轮询获取)"""
    r = get_redis()
    key = _RESULT_PREFIX + request_id
    r.set(key, result_text, ex=ttl)
    r.srem(_PROCESSING_KEY, request_id)
    logger.info(f"[Queue] 结果已存储 request_id={request_id} ({len(result_text)}字)")


def get_result(request_id: str) -> str | None:
    """客户端轮询获取结果"""
    r = get_redis()
    key = _RESULT_PREFIX + request_id
    result = r.get(key)
    if result:
        return result.decode("utf-8") if isinstance(result, bytes) else result
    return None


def get_queue_status(request_id: str) -> dict | None:
    """
    查询请求当前状态。

    Returns:
        None         — 请求不存在 (可能已过期)
        {"status": "queued", "position": N, "estimated_wait": S}
        {"status": "processing"}
        {"status": "done", "result": "..."}
    """
    r = get_redis()

    # 检查是否已有结果
    result = get_result(request_id)
    if result:
        return {"status": "done", "result": result}

    # 检查是否在处理中
    if r.sismember(_PROCESSING_KEY, request_id):
        return {"status": "processing"}

    # 检查是否还在队列中
    all_items = r.lrange(_QUEUE_KEY, 0, -1)
    for idx, item in enumerate(all_items):
        try:
            data = json.loads(item)
            if data.get("request_id") == request_id:
                return {
                    "status": "queued",
                    "position": idx + 1,
                    "estimated_wait": (idx + 1) * 10,
                }
        except json.JSONDecodeError:
            continue

    # 不在队列、不在处理中、没有结果 → 可能已过期
    return None


def queue_length() -> int:
    """当前队列长度"""
    r = get_redis()
    return r.llen(_QUEUE_KEY)


def processing_count() -> int:
    """正在处理的请求数"""
    r = get_redis()
    return r.scard(_PROCESSING_KEY)


def is_overloaded(threshold: int = 5) -> bool:
    """判断系统是否超载 (队列长度 > 阈值)"""
    return queue_length() > threshold
