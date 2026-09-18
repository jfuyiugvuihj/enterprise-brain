"""
Layer 5 — 队列后台 Worker
启动后循环从 Redis 队列取请求，调用 Multi-Agent 处理，存储结果。

用法:
  python deploy/queue_worker.py

环境变量:
  REDIS_URL     — Redis 连接地址 (默认 localhost:6379)
  DATABASE_URL  — PostgreSQL 连接地址
"""

import os
import sys
import time
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.common.reliable_queue import QueueConnectionError, ReliableQueue, connect_reliable_queue
from app.common.logger import logger, setup_logging
from app.trace.records import record_agent_result

setup_logging()

running = True
_queue: ReliableQueue | None = None


def _get_queue() -> ReliableQueue:
    global _queue
    if _queue is None:
        _queue = connect_reliable_queue()
    return _queue


def shutdown(signum, frame):
    global running
    logger.info(f"[QueueWorker] 收到信号 {signum}，正在退出...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def _owner_from(payload: dict) -> str:
    principal = payload.get("principal") or {}
    if not isinstance(principal, dict):
        return ""
    return str(principal.get("user_id") or "").strip()


NON_RETRYABLE_DEAD_REASON = "non_retryable_terminal"


def is_non_retryable_error(record: object) -> bool:
    """True 只在记录自己声明了"重试也不会变"的时候成立。

    判定收成一个不碰 Redis 的纯函数，是为了能被单独钉住（deploy/ 不在包里，
    本文件此前也不在任何用例覆盖内）。它刻意只认 error["retryable"] is False
    这一种形状：状态闸门不在这里，success/partial 由下面那条一字未改的判断挡住，
    所以"partial 带一枚不可重试错误"仍旧照常发布；error 不是 dict、缺 retryable
    字段、字段值不是 False（None/0/"False"/"false" 等异形）一律 False，
    调用方仍旧照改前的路走 fail_or_retry。

    字段缺失为什么默认重试：ErrorEnvelope.retryable 的出厂值是 False，而
    AgentResult.model_dump() 一定带这个字段，所以看不见它只可能是这条记录压根
    没走过契约。队列层没资格替契约宣布终局，更不能把一次形状异常升级成不重投的
    dead —— 那是把"还能救"变成"必然丢"，而盲重试的代价本来有 max_attempts 兜着。
    """
    if not isinstance(record, dict):
        return False
    error = record.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("retryable") is False


def process_one():
    """处理一个队列请求，并把结果收敛为一条 canonical AgentResult 记录"""
    queue = _get_queue()
    message = queue.reserve(timeout=10)
    if message is None:
        return False  # 队列为空

    request_id = message.request_id
    payload = message.payload or {}
    user_message = str(payload.get("message") or "")
    session_id = str(payload.get("session_id") or "")
    owner_id = _owner_from(payload)

    logger.info(f"[QueueWorker] 处理中 request_id={request_id}: {user_message[:60]}")

    if not owner_id:
        # A queued task without an owning Principal must not run under a shared identity.
        logger.error(f"[QueueWorker] 拒绝执行 request_id={request_id}: 缺少授权主体")
        queue.fail_or_retry(request_id, "authorization_required")
        return True

    # 缺少 session_id 时使用请求级线程，避免不同用户共享同一个 checkpointer 线程
    thread_id = session_id or f"queue:{request_id}"

    try:
        # C2: 队列走无 interrupt 的图，chart/export 自动执行不卡审批
        from app.agents.orchestrator import run_orchestrator_result

        agent_result = run_orchestrator_result(
            user_message,
            thread_id=thread_id,
            user={"principal": payload.get("principal")},
        )
        record = agent_result.model_dump() if hasattr(agent_result, "model_dump") else dict(agent_result or {})
        record_agent_result(record, owner_id=owner_id, session_id=session_id, entry_point="queue")

        if record.get("status") not in {"success", "partial"}:
            code = str((record.get("error") or {}).get("code") or record.get("status") or "internal_error")
            if is_non_retryable_error(record):
                # R81：契约已经判定"重试也不会变"的终态（R64/R65 的两枚授权拒绝码）
                # 不再占用重试名额，直接落 dead。原因码单独进日志：前者是授权设计的正常
                # 后果，后者是故障，混在一行里运维会查错地方。
                terminal_status = queue.fail_or_retry(request_id, code, retryable=False)
                bookkeeping = queue.failure(request_id)
                logger.error(
                    f"[QueueWorker] request_id={request_id} 终态不可重试，不再重投 -> {terminal_status}: {code} "
                    f"(reason={NON_RETRYABLE_DEAD_REASON} "
                    f"attempts={bookkeeping.get('attempts')} max_attempts={bookkeeping.get('max_attempts')})"
                )
                return True
            logger.error(f"[QueueWorker] request_id={request_id} 未产生业务结论: {code}")
            queue.fail_or_retry(request_id, code)
            return True

        if not queue.complete(request_id, str(record.get("answer") or "")):
            logger.info(
                "request_id={rid} 结果已丢弃：运行途中被取消或租约已丢失 terminal_status={state}".format(
                    rid=request_id,
                    state=queue.status(request_id),
                )
            )
            return True
        logger.info(
            "request_id={rid} 完成 status={status} evidence={ev}".format(
                rid=request_id,
                status=record.get("status"),
                ev=len(record.get("evidence") or []),
            )
        )

    except Exception as e:
        logger.error(f"[QueueWorker] 失败 request_id={request_id}: {e}")
        terminal_status = queue.fail_or_retry(request_id, str(e))
        logger.info(f"[QueueWorker] request_id={request_id} -> {terminal_status}")

    return True


def main():
    logger.info("[QueueWorker] 启动 — 等待队列请求...")
    try:
        queue = _get_queue()
    except QueueConnectionError as exc:
        logger.error(f"[QueueWorker] 可靠队列不可用: {exc}")
        return
    idle_count = 0

    while running:
        try:
            queue.requeue_expired()
            has_work = process_one()
            if has_work:
                idle_count = 0
            else:
                idle_count += 1
                if idle_count % 30 == 0:  # 每 5 分钟报告一次
                    pending = queue.redis.lrange(queue.pending_key, 0, -1)
                    processing = queue.redis.lrange(queue.processing_key, 0, -1)
                    logger.debug(
                        f"[QueueWorker] 空闲中... 队列={len(pending)} 处理中={len(processing)}"
                    )
        except Exception as e:
            logger.error(f"[QueueWorker] 异常: {e}")
            time.sleep(5)

    logger.info("[QueueWorker] 已停止")


if __name__ == "__main__":
    main()
