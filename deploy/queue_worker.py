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

from app.common.queue import dequeue_request, store_result, queue_length, processing_count
from app.common.logger import logger, setup_logging

setup_logging()

running = True


def shutdown(signum, frame):
    global running
    logger.info(f"[QueueWorker] 收到信号 {signum}，正在退出...")
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def process_one():
    """处理一个队列请求"""
    data = dequeue_request(timeout=10)
    if data is None:
        return False  # 队列为空

    request_id = data["request_id"]
    user_message = data["user_message"]
    session_id = data.get("session_id", "default")

    logger.info(f"[QueueWorker] 处理中 request_id={request_id}: {user_message[:60]}")

    try:
        # C2: 队列走无 interrupt 的图，chart/export 自动执行不卡审批
        from app.agents.orchestrator import run_orchestrator_queue

        result = run_orchestrator_queue(user_message, thread_id=session_id)
        store_result(request_id, result if isinstance(result, str) else str(result))
        logger.info(f"[QueueWorker] 完成 request_id={request_id} ({len(result)}字)")

    except Exception as e:
        logger.error(f"[QueueWorker] 失败 request_id={request_id}: {e}")
        store_result(request_id, f"[处理失败] {str(e)}")

    return True


def main():
    logger.info("[QueueWorker] 启动 — 等待队列请求...")
    idle_count = 0

    while running:
        try:
            has_work = process_one()
            if has_work:
                idle_count = 0
            else:
                idle_count += 1
                if idle_count % 30 == 0:  # 每 5 分钟报告一次
                    logger.debug(f"[QueueWorker] 空闲中... 队列={queue_length()} 处理中={processing_count()}")
        except Exception as e:
            logger.error(f"[QueueWorker] 异常: {e}")
            time.sleep(5)

    logger.info("[QueueWorker] 已停止")


if __name__ == "__main__":
    main()
