"""
Layer 5 — 队列后台 Worker
启动后循环从 Redis 队列取请求，调用 Multi-Agent 处理，存储结果。

用法:
  python deploy/queue_worker.py

环境变量:
  REDIS_URL     — Redis 连接地址 (默认 localhost:6379)
  DATABASE_URL  — PostgreSQL 连接地址

R37：载荷自己声明了 report 档的那一轮走**能挂起**的图，跑完把结论补写回会话历史
（见 _process_report_lane_turn）；没声明档位的存量任务与本单之前逐字节相同。
"""

import os
import sys
import time
import signal
from uuid import uuid4

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


# ==================== R37：报告档在后台跑完这一轮 ====================

# 档位名在队列这一侧的声明。取值必须与 app/api/v1/chat.py 的 LANE_REPORT、
# app/agents/nodes.py 的 LANE_REPORT 同为同一个字符串，由
# tests/test_r37_report_lane_worker.py::test_the_lane_name_has_one_source_of_truth 钉住。
# 为什么不干脆 import chat：本文件现在 0.5 秒起得来，而 app.api.v1.chat 一被 import
# 就要把整条 API/RAG 链拉起来（本机实测 17 秒，并且会改写 chroma_db/chroma.sqlite3），
# 用例又在模块层 import 本文件——等于每次全量测试都付这笔钱并顺手写一次向量库。
# 挂起文案与会话回写仍旧用 chat 里那三个与同步路径同源的共用件，只是延后到真跑到
# 报告档时才 import，和下面 run_orchestrator_result 的按需 import 同一个理由。
REPORT_LANE = "report"

# 后台这一轮彻底失败时写给用户看的那一句，措辞与同步路径 app/api/v1/chat.py 里
# "本轮未产出任何结论" 同一句。稳定码只进队列的 last_error 与日志，不进正文（R16）。
REPORT_TURN_FAILURE_TEXT = "本轮未产出任何结论，请重试或补充数据范围。"


def _report_lane_requested(payload) -> bool:
    """判据②：worker 侧定档是载荷的纯读——不调模型、不读会话、不碰队列。

    只认载荷里显式写着的档位字符串，和 chat._queue_lane 同一套苛刻：REPORT 不是任何
    人声明过的档位，而队列这一侧压根没有第二次判别的机会，模糊匹配等于猜心思。
    """
    if not isinstance(payload, dict):
        return False
    lane = payload.get("lane")
    return isinstance(lane, str) and lane.strip() == REPORT_LANE


def _stream_snapshot(event):
    """把流里的一枚事件拆成顶层状态快照；不是快照就返回 None。

    能挂起的在场流产的是 (namespace, state) 元组，编排自己吐的失败事件是一枚裸 dict，
    两种形状都得认，否则一次失败会被读成空快照。子图快照里没有顶层结论，读它等于拿
    半成品冒充最终答案。
    """
    namespace = ()
    data = event
    if isinstance(event, tuple):
        namespace = event[0] if len(event) > 1 else ()
        data = event[1] if len(event) > 1 else event[0]
    if not isinstance(data, dict):
        return None
    if data.get("error") or (namespace and namespace != ("",)):
        return None
    return data


def _drain_report_stream(user_message, *, thread_id, principal, request_id, trace_id, task_id):
    """跑完这一轮，收回顶层结论、契约记录，以及编排自己报的那句错。

    读法与同步路径一致：只认顶层命名空间的快照，final_answer 取最后一次非空值。
    """
    from app.agents.orchestrator import run_with_stream

    final_answer = ""
    agent_results: dict = {}
    stream_error = ""
    for event in run_with_stream(
        user_message,
        thread_id=thread_id,
        user={"principal": principal},
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
    ):
        if isinstance(event, dict) and event.get("error"):
            # 编排把异常收成一枚 error 事件而不是抛出来：这一轮到此为止。
            stream_error = str(event["error"])
            continue
        state = _stream_snapshot(event)
        if state is None:
            continue
        if state.get("final_answer"):
            final_answer = str(state["final_answer"])
        if isinstance(state.get("agent_results"), dict):
            agent_results = dict(state["agent_results"])
    return final_answer, agent_results, stream_error


def _save_background_turn(session_id: str, content: str) -> None:
    """把后台这一轮补写进会话历史（判据⑤）。写不成就明着留话，不许假装写了。

    共用件返回 False 就是真没写成：纯内存会话的部署里，worker 往自己进程的内存补一行
    等于没写，用户在 API 进程的历史里一个字也看不见。
    """
    from app.api.v1 import chat

    if not session_id:
        logger.warning("[QueueWorker] 后台轮次缺少 session_id，历史回写跳过")
        return
    try:
        written = chat.save_session_turn(session_id, content)
    except Exception as exc:
        # 答案已经发布，回写失败绝不能把这一轮升级成"再跑一次"——那会变成两个答案。
        logger.error(f"[QueueWorker] 后台轮次写回会话历史失败 session={session_id}: {exc}")
        return
    if not written:
        logger.warning(
            f"[QueueWorker] 后台轮次没能写回会话历史 session={session_id}：会话库不可用"
        )


def _fail_report_turn(queue, request_id, record, *, session_id, write_back) -> bool:
    """这一轮没产出业务结论：终态与原因码仍旧走队列原有的那套，历史只在真终态补一行。"""
    code = str((record.get("error") or {}).get("code") or record.get("status") or "internal_error")
    if is_non_retryable_error(record):
        # 与 R81 同一条闸门：契约判定"重试也不会变"的直接落 dead，一个名额不占。
        terminal_status = queue.fail_or_retry(request_id, code, retryable=False)
        bookkeeping = queue.failure(request_id)
        logger.error(
            f"[QueueWorker] request_id={request_id} 报告档终态不可重试，不再重投 -> {terminal_status}: {code} "
            f"(reason={NON_RETRYABLE_DEAD_REASON} "
            f"attempts={bookkeeping.get('attempts')} max_attempts={bookkeeping.get('max_attempts')})"
        )
    else:
        logger.error(f"[QueueWorker] request_id={request_id} 报告档未产生业务结论: {code}")
        terminal_status = queue.fail_or_retry(request_id, code)

    if terminal_status == "dead" and write_back:
        # 还要重试的这一轮不是终态，一个字都不许写；落到 dead 才补一句，否则会话里
        # 永远留着半句没人回答的问话（判据③加④）。
        _save_background_turn(session_id, REPORT_TURN_FAILURE_TEXT)
    return True


def _process_report_lane_turn(
    queue, request_id, payload, *, user_message, session_id, owner_id, thread_id
) -> bool:
    """报告档的后台执行：结果查得回、挂起留待办、历史不留空洞。

    挂起文案、待办记账、会话回写三件都用 app/api/v1/chat.py 里与同步路径同源的那三个
    共用件，两条道说的是同一句话。判据⑧：本函数不带任何开关，也不默认开启任何路径——
    进不进来看的是载荷自己有没有声明档位，而那由入队侧的 REPORT_LANE_VIA_QUEUE 决定。
    """
    from app.agents.evidence import aggregate_agent_result
    from app.agents.orchestrator import check_interrupt
    from app.api.v1 import chat

    write_back = bool(payload.get("write_back_session"))
    trace_id = f"trace-{uuid4().hex}"
    task_id = f"task-{uuid4().hex}"
    started = time.monotonic()

    try:
        final_answer, agent_results, stream_error = _drain_report_stream(
            user_message,
            thread_id=thread_id,
            principal=payload.get("principal"),
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
        )
    except Exception as exc:
        logger.error(f"[QueueWorker] request_id={request_id} 报告档后台执行异常: {exc}")
        return _fail_report_turn(
            queue,
            request_id,
            {"status": "failed", "error": {"code": "internal_error", "message": str(exc)}},
            session_id=session_id,
            write_back=write_back,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    if stream_error:
        # 这枚 error 事件不带契约的 retryable 判定，队列没资格替契约宣布终局：
        # 交回 fail_or_retry 按名额判，重试用完才 dead（与 R81 同一口径）。
        logger.error(f"[QueueWorker] request_id={request_id} 报告档后台报错: {stream_error}")
        return _fail_report_turn(
            queue,
            request_id,
            {"status": "failed", "error": {"code": "internal_error", "message": stream_error}},
            session_id=session_id,
            write_back=write_back,
        )

    # 先查挂起再判成败：图停在 interrupt_before 之前时这一轮既没有答案也不是失败，它是
    # 在等人。顺序反了就把"等你确认"记成队列失败，审批面板还少一条待办。
    try:
        parked = check_interrupt(thread_id)
    except Exception as exc:
        logger.warning(
            f"[QueueWorker] request_id={request_id} 挂起节点查不到，按未挂起处理: {exc}"
        )
        parked = None

    answer = chat.hitl_park_text(parked) if parked else final_answer
    record = aggregate_agent_result(
        agent_results,
        answer=answer,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
        session_id=session_id,
        duration_ms=duration_ms,
    ).model_dump()
    record_agent_result(record, owner_id=owner_id, session_id=session_id, entry_point="queue")

    if parked:
        # 挂起记三笔账：审批面板一行待办、队列一个终态、会话历史一句话，缺一笔用户就
        # 找不到这一轮。归属人只认载荷里解析出的 user_id——上面没有 owner 就已经拒执行，
        # 这里更不许退回共享身份。
        if not chat.record_hitl_awaiting(
            session_id or thread_id,
            owner_id,
            parked,
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
        ):
            logger.error(
                f"[QueueWorker] request_id={request_id} 待办没能开成 session={session_id}："
                "审批面板看不见这一轮后台挂起"
            )
    elif record.get("status") not in {"success", "partial"}:
        return _fail_report_turn(
            queue, request_id, record, session_id=session_id, write_back=write_back
        )

    if not queue.complete(request_id, answer):
        logger.info(
            "request_id={rid} 报告档结果已丢弃：运行途中被取消或租约已丢失 terminal_status={state}".format(
                rid=request_id,
                state=queue.status(request_id),
            )
        )
        return True
    if write_back:
        _save_background_turn(session_id, answer)
    logger.info(
        "request_id={rid} 报告档跑完 status={status} awaiting_hitl={awaiting}".format(
            rid=request_id,
            status=record.get("status"),
            awaiting=bool(parked),
        )
    )
    return True


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

    if _report_lane_requested(payload):
        # R37：报告档走**能挂起**的那张图，跑完再补写会话历史。判据⑦的护栏就在这两行：
        # 只有载荷自己声明了档位才进这个分支，没声明的一律走下面那条一字未动的老路。
        return _process_report_lane_turn(
            queue,
            request_id,
            payload,
            user_message=user_message,
            session_id=session_id,
            owner_id=owner_id,
            thread_id=thread_id,
        )

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
