"""
阶段 4 · APScheduler 定时任务

- 每 5 分钟巡检告警规则（evaluate_all）
- 每天 8:00 生成日报（daily_report）
- 低峰重建窗口（offpeak_rebuild_window）：R425 挂进来的第三枚 job，缺省不排；开关、预算、
  时刻三枚旋钮的唯一事实源在 app/scheduler/index_rebuild_config.py，本文件不抄第二份。
  到点它只报"窗口到、本进程不动手写库"，因为应用侧触发重建被 R22 判据 3 钉死（见那枚回调）。
daemon=True，随主进程退出。
"""
from apscheduler.schedulers.background import BackgroundScheduler
from app.common.logger import logger
from app.scheduler.index_rebuild_config import (
    REBUILD_JOB_ID,
    resolve_index_rebuild_window,
)

scheduler = BackgroundScheduler(daemon=True)


def register_jobs(scheduler) -> None:
    """Declare the scheduled jobs once so every host shares one definition."""
    from app.api.v1.alerts import evaluate_all, daily_report
    scheduler.add_job(evaluate_all, "interval", minutes=5,
                      id="alert_check", replace_existing=True)
    scheduler.add_job(daily_report, "cron", hour=8, minute=0,
                      id="daily_report", replace_existing=True)
    # 🔴 R425 判据②: the switch is decided HERE, at the add_job call, not inside the callback.
    # A job that is on the calendar and returns early is still on the calendar; a private box
    # that nobody told to rebuild must not have a rebuild wake-up written on its schedule.
    window = resolve_index_rebuild_window()
    for note in window.notes:
        logger.warning(f"[Scheduler] 低峰重建配置: {note}")
    if window.schedulable:
        hour, minute = window.clock
        scheduler.add_job(offpeak_rebuild_window, "cron", hour=hour, minute=minute,
                          kwargs={"time_budget_seconds": window.budget_seconds},
                          id=REBUILD_JOB_ID, replace_existing=True,
                          max_instances=1, coalesce=True)
        logger.info(f"[Scheduler] 低峰重建窗口已排程: 每日 {hour:02d}:{minute:02d}, "
                    f"预算 {window.budget_seconds}s, 同一时刻不叠跑")
    else:
        logger.info(f"[Scheduler] 低峰重建窗口不排程: {window.unschedulable_reason()}")


def offpeak_rebuild_window(time_budget_seconds=None) -> dict:
    """Report the off-peak window at its moment, and do not touch the knowledge base.

    这不是半途而废的形状，是这棵树今天唯一被允许的形状。R22 判据 3 把"应用侧能不能自己起重建"
    钉成一枚硬钉：no startup hook, no upload hook, no scheduler job may import or call the
    rebuild（tests/test_r22_rebuild_cli.py），且 R242 之后那第二遍扫描读的是解析出的语法，
    argv 列表形状一样命中——那正是它自己注释里写明的存在理由。所以低峰的**排程**能落（开关、
    预算、时刻、日历位），**执行腿**不能落进 app/ 任何一个字节里，把命令名拆成碎片绕过它更不行：
    那枚钉的 docstring 自己把这个局限写在纸上，并拒绝替它遮丑。改那枚钉是业主的决定，本回调
    不许替那个决定先斩后奏，于是它到点只说一句话。

    两枚拒绝在前，因为最贵的失败是一枚会猜的 job：

    * 开关在到点时再读一遍。这是纵深，不是那枚闸：判据② 在上面 `add_job` 那一刻就定了，
      把闸挪进这里并无条件注册，tests/test_r425_offpeak_index_rebuild.py 当场红。
    * 预算不许为空或为零：无预算＝整库一口气重嵌，正是这枚旋钮存在的理由，所以 schedulable
      在注册前与到点后都重新确认它是正数。
    """
    window = resolve_index_rebuild_window()
    if not window.schedulable:
        reason = window.unschedulable_reason()
        logger.error(f"[Scheduler] 低峰重建窗口跳过: {reason}")
        return {"status": "skipped", "reason": reason}
    budget = window.budget_seconds if time_budget_seconds is None else int(time_budget_seconds)
    hour, minute = window.clock
    reason = (
        f"应用侧不许触发索引重建（R22 判据 3，tests/test_r22_rebuild_cli.py 逐字钉住），所以这台机器"
        f"到了排好的低峰窗口 {hour:02d}:{minute:02d} 也不会自己重嵌；要重建请人工跑 scripts 下那枚"
        f"重建命令，带 --incremental 与 --time-budget-seconds {budget}s，跑完看 remaining 是否归零"
    )
    logger.error(f"[Scheduler] 低峰重建窗口到点，未执行: {reason}")
    return {"status": "refused", "reason": reason, "budget_seconds": budget,
            "window": f"{hour:02d}:{minute:02d}"}


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
