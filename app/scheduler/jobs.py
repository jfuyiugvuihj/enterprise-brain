"""
阶段 4 · APScheduler 定时任务

- 每 5 分钟巡检告警规则（evaluate_all）
- 每天 8:00 生成日报（daily_report）
- 低峰重建窗口（offpeak_rebuild_window）：R425 挂进来的第三枚 job，缺省不排；开关、预算、
  时刻三枚旋钮的唯一事实源在 app/scheduler/index_rebuild_config.py，本文件不抄第二份。
  到点它只报"窗口到、本进程不动手写库"，因为应用侧触发重建被 R22 判据 3 钉死（见那枚回调）。
- 审计留存清扫（audit_retention_sweep）：R457 给台账那枚 `expires_at` 装上的执行腿，每日凌晨
  一格。它不挂在 register_jobs() 的名册上，理由写在 register_audit_sweep() 的 docstring 里。
daemon=True，随主进程退出。
"""
from apscheduler.schedulers.background import BackgroundScheduler
from app.common.logger import logger
from app.scheduler.index_rebuild_config import (
    REBUILD_JOB_ID,
    resolve_index_rebuild_window,
)

scheduler = BackgroundScheduler(daemon=True)

#: 🔴 R457 · 审计留存的执行腿。台账每一笔事件都 stamped `expires_at`，而在这笔单之前全仓没有
#: 一枚生产调用点读那枚字段（`purge_expired_audit_events` 只被 tests 点过名）⇒ 留存是纸上的，
#: 台账行数只增不减。这枚 job id 就是那笔债的还款位。
AUDIT_SWEEP_JOB_ID = "audit_retention_sweep"
#: 时刻：每日凌晨一格，落在低峰重建窗口（`DEFAULT_AT`，本文件不抄它的数字）与日报（8:00）之外。
#: 选「每日」而不是「每周」：过期那笔在被清掉之前仍然会被 hydrate 回视图，一天的粒度是那笔
#: `DEFAULT_RETENTION_DAYS` 承诺能兑现的上界。清扫是幂等的（tombstone 把 `expires_at` 置空），
#: 所以进程内调度与独立调度进程同时挂着也不会重复清账。
AUDIT_SWEEP_HOUR = 2
AUDIT_SWEEP_MINUTE = 30


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


def audit_retention_sweep() -> dict:
    """到点就把台账自己 stamped 的留存窗口执行一遍。

    清的是**内容**，不是行：共享适配器只暴露 upsert，所以过期那笔被改写成一枚 tombstone——
    留下 `event_id`/`action`/`outcome`/`created_at`/`purged_at`，抹掉正文与操作人。台账的行数
    仍然随写入增长，真正的 DELETE 属部署 runbook，本文件不许把它说成「台账不再变长」。
    判断全在 `app/common/audit.py` 那一枚函数里，这里不复制第二份：连保留期多少天、无效值
    怎么退，都由那边的 `AUDIT_RETENTION_DAYS` 与 `DEFAULT_RETENTION_DAYS` 说。

    失败不装成功：`unavailable`（没有可久读的落点）记 warning，`error`（读不动台账）记 error；
    交回的读数就是那边给的读数，本文件不加第二个词表。
    """
    from app.common.audit import purge_expired_audit_events

    result = purge_expired_audit_events()
    counts = (
        f"checked={result.get('checked')} expired={result.get('expired')} "
        f"purged={result.get('purged')}"
    )
    status = str(result.get("status") or "")
    if status == "ok":
        logger.info(f"[Scheduler] 审计留存清扫已执行: {counts}")
    elif status == "unavailable":
        logger.warning(f"[Scheduler] 审计留存清扫跳过: {result.get('reason')} ({counts})")
    else:
        logger.error(f"[Scheduler] 审计留存清扫失败: {result.get('reason')} ({counts})")
    return result


def register_audit_sweep(scheduler) -> None:
    """把留存清扫挂上一枚调度器 host：声明一次，两枚 host 共用。

    🔴 为什么这枚 `add_job` 不在 `register_jobs()` 里：那枚函数的名册被 R425 判据② 那族在册钉
    按「缺省恰两枚」逐字钉死——`tests/test_r425_offpeak_index_rebuild.py` 的
    `test_the_shipped_default_registers_two_jobs_only`、
    `test_an_unset_or_unreadable_switch_still_registers_nothing`、
    `test_a_switched_on_box_registers_a_third_job` 三枚都断 `ids(fake)` 与一枚列表**全等**。那本账
    不在 R457 的写域里，一笔单不许改另一笔单的断言（搬进去就红，本件 TOOTH 3 量的就是这一格）。
    所以挂在两枚 host 的公共把手上：`start_scheduler()`（进程内，开发形态）与 `run_forever()`
    （独立进程，生产形态，`python deploy/scheduler.py`）。
    缺省即开，没有第二枚开关：把清扫藏在一枚默认关闭的开关后面，等于让那枚字段继续没人读；
    业主要的旋钮是那边那枚 `AUDIT_RETENTION_DAYS`，不在这里再造第二枚。
    「第三枚 host 漏挂」那一格由 `tests/test_r457_audit_retention_execution_leg.py` 的 AST 钉堵死。
    """
    scheduler.add_job(audit_retention_sweep, "cron",
                      hour=AUDIT_SWEEP_HOUR, minute=AUDIT_SWEEP_MINUTE,
                      id=AUDIT_SWEEP_JOB_ID, replace_existing=True,
                      max_instances=1, coalesce=True)
    logger.info(f"[Scheduler] 审计留存清扫已排程: 每日 {AUDIT_SWEEP_HOUR:02d}:"
                f"{AUDIT_SWEEP_MINUTE:02d}, 同一时刻不叠跑")


def start_scheduler():
    if scheduler.running:
        return
    register_jobs(scheduler)
    register_audit_sweep(scheduler)
    scheduler.start()
    logger.info("[Scheduler] 已启动: 每5分钟巡检 + 每日8:00日报 + 每日留存清扫")


def run_forever() -> int:
    """Run the schedule inside a dedicated process until the operator stops it."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    standalone = BlockingScheduler()
    register_jobs(standalone)
    register_audit_sweep(standalone)
    logger.info("[Scheduler] 独立进程已启动: 每5分钟巡检 + 每日8:00日报 + 每日留存清扫")
    standalone.start()
    return 0
