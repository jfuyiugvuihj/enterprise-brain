"""
阶段 4 · APScheduler 定时任务

- 每 5 分钟巡检告警规则（evaluate_all）
- 每天 8:00 生成日报（daily_report）
daemon=True，随主进程退出。
"""
from apscheduler.schedulers.background import BackgroundScheduler
from app.common.logger import logger

scheduler = BackgroundScheduler(daemon=True)


def register_jobs(scheduler) -> None:
    """Declare the scheduled jobs once so every host shares one definition."""
    from app.api.v1.alerts import evaluate_all, daily_report
    scheduler.add_job(evaluate_all, "interval", minutes=5,
                      id="alert_check", replace_existing=True)
    scheduler.add_job(daily_report, "cron", hour=8, minute=0,
                      id="daily_report", replace_existing=True)


def start_scheduler():
    if scheduler.running:
        return
    register_jobs(scheduler)
    scheduler.start()
    logger.info("[Scheduler] 已启动: 每5分钟巡检 + 每日8:00日报")


def run_forever() -> int:
    """Run the schedule inside a dedicated process until the operator stops it."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    standalone = BlockingScheduler()
    register_jobs(standalone)
    logger.info("[Scheduler] 独立进程已启动: 每5分钟巡检 + 每日8:00日报")
    standalone.start()
    return 0
