"""
阶段 4 · APScheduler 定时任务

- 每 5 分钟巡检告警规则（evaluate_all）
- 每天 8:00 生成日报（daily_report）
daemon=True，随主进程退出。
"""
from apscheduler.schedulers.background import BackgroundScheduler
from app.common.logger import logger

scheduler = BackgroundScheduler(daemon=True)


def start_scheduler():
    if scheduler.running:
        return
    from app.api.v1.alerts import evaluate_all, daily_report
    scheduler.add_job(evaluate_all, "interval", minutes=5,
                      id="alert_check", replace_existing=True)
    scheduler.add_job(daily_report, "cron", hour=8, minute=0,
                      id="daily_report", replace_existing=True)
    scheduler.start()
    logger.info("[Scheduler] 已启动: 每5分钟巡检 + 每日8:00日报")
