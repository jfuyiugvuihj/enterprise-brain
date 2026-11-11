"""
部署用的独立调度器进程

告警巡检和日报是有外部副作用的定时任务。一个部署里只允许一个进程拥有它们，
所以 API 副本不再内嵌调度器，改由本进程统一执行。

用法:
  python deploy/scheduler.py

环境变量:
  APP_ENV           — production 时禁止 API 进程内调度
  SCHEDULER_ENABLED — 仅作用于 API 进程，与本文件无关
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.common.logger import logger, setup_logging
from app.scheduler.jobs import run_forever

setup_logging()


def main() -> int:
    logger.info("[Scheduler] 独立调度进程启动")
    try:
        return run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Scheduler] 已停止")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())