"""
阶段 1 · 新 Multi-Agent 图

classify_intent(确定性) → [chat→respond] / [task→load_memory→plan]
→ supervisor(唯一dispatch) → Send 并行 worker(带thread_id) → supervisor 汇总
→ reflect(反思) → [redo→supervisor] / [synthesize→END]

保留旧公共 API：run_orchestrator / run_with_stream / run_interrupt_stream /
clear_session / check_interrupt / multi_agent_graph / queue_graph /
run_orchestrator_queue / dispatch / _merge_dicts
"""
import os
import re
import time
import json
from typing import Annotated
from uuid import uuid4
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent, ToolNode
from langgraph.types import Send, Command
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
try:
    import psycopg
    import psycopg_pool
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None
    psycopg_pool = None

from app.agents.contracts import ModelTier
from app.agents.state import AgentState, _merge_dicts
from app.approval.assistant import build_precheck
from app.agents.tools import search_docs, analyze_data, query_data, generate_chart, export_report
from app.agents.planner import build_task_plan
from app.agents.nodes import (
    DECLARED_LANE_KEY,
    LANE_QA,
    STREAM_PIECE_SINK_KEY,
    _make_model, classify_intent, classify_route, decide_workers, declared_lane_from_config,
    normalize_declared_lane, respond, load_memory, plan, reflect_node, resolve_turn_lane,
    route_probe_quiet, route_reflect, synthesize,
)
from app.agents.evidence import (
    aggregate_agent_result,
    build_agent_result,
    new_evidence_bag,
    summarize_agent_result,
)
from app.memory import compress_messages
from app.common.logger import logger
from app.common.monitoring import is_production_environment
from app.trace.store import TraceStore, default_trace_store

# ==================== 持久化 ====================

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")


#: 判据 2（跟进单 §41.1）要求"当前 checkpointer 后端"机器可查，所以每次决策都留一份状态，
#: 由 app/common/monitoring.py 挂到 /api/v1/health/details。形状照 monitoring.queue_storage_state()：
#: 五个子系统键 + backend。"uninitialised" 是一个真值而不是占位 —— orchestrator 是懒导入的
#: （app/api/v1/chat.py:1201），第一发请求之前根本没有"决定"可报。
_CHECKPOINT_STATE_SHAPES = {
    "postgres": {
        "storage_mode": "postgres",
        "durable": True,
        "shared_across_processes": True,
        "protection": "none",
        "backend": "postgres",
    },
    "memory": {
        "storage_mode": "memory",
        "durable": False,
        "shared_across_processes": False,
        "protection": "none",
        "backend": "memory",
    },
    "refused": {
        # 生产环境拒降级：没有可用的 checkpointer 可报，只能如实写"不可用 + 开机即拒"。
        "storage_mode": "unavailable",
        "durable": False,
        "shared_across_processes": False,
        "protection": "refuse_start",
        "backend": "none",
    },
    "uninitialised": {
        "storage_mode": "unavailable",
        "durable": False,
        "shared_across_processes": False,
        "protection": "disabled",
        "backend": "none",
    },
}

#: 图状态到底落在哪。进程刚起来时是 uninitialised，之后由 _make_checkpointer() 整体改写。
_CHECKPOINT_STATE = {
    **_CHECKPOINT_STATE_SHAPES["uninitialised"],
    "detail": "the orchestrator has not built a checkpointer yet",
}

#: 与 app/api/v1/alerts.py:62、app/api/v1/chat.py:520 同一口径的那句话。生产环境缺持久化
#: checkpointer 不是"降级一次就好"，是不通过。
CHECKPOINT_REQUIRED_IN_PRODUCTION = (
    "PostgresSaver checkpointer is required in production; run migrations first"
)


def checkpointer_storage_state() -> dict:
    """编译进图的那份状态实际存在哪里。只读内存，不连接、不建池、不开线程。"""
    return dict(_CHECKPOINT_STATE)


def _record_checkpointer(kind: str, detail: str) -> None:
    global _CHECKPOINT_STATE

    _CHECKPOINT_STATE = {**_CHECKPOINT_STATE_SHAPES[kind], "detail": detail}


def _fail_checkpointer_loudly(reason: str, *, database_reachable: bool):
    """把降级说明白，再按环境决定"退"还是"拒"。

    旧实现把 psycopg 的事务块报错谎报成「Postgres 不可用」（跟进单 §41.1 实证那行 WARNING，
    同刻 postgres 容器 healthy），所以这里唯一的撒谎豁免是探活真失败：只有它才有资格说数据库
    不可达。开发态退 MemorySaver；生产态不退，因为 backend / worker / scheduler 是三个进程，
    各持一份进程内 MemorySaver 等于 HITL 挂起之后没人接得住。
    """
    reachable = "数据库可达" if database_reachable else "数据库不可达"
    logger.error(f"[Orchestrator] checkpointer 未能用上 PostgresSaver（{reachable}）: {reason}")
    if is_production_environment():
        logger.error(
            "[Orchestrator] 生产环境不接受 MemorySaver 降级："
            f"{CHECKPOINT_REQUIRED_IN_PRODUCTION}（原因见上一行）"
        )
        _record_checkpointer(
            "refused", f"{reason} ({reachable}); {CHECKPOINT_REQUIRED_IN_PRODUCTION}"
        )
        raise RuntimeError(f"{CHECKPOINT_REQUIRED_IN_PRODUCTION} ({reason})")
    logger.error("[Orchestrator] 已降级 MemorySaver：图状态只活在本进程，重启即丢")
    _record_checkpointer("memory", f"{reason} ({reachable})")
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def _make_checkpointer():
    """Postgres 可用 → PostgresSaver 持久化；否则开发态降级 MemorySaver、生产态拒绝启动。
    导入时不硬依赖数据库（快速探活 2s），保证无库也能导入/跑逻辑测试。

    判据 1（跟进单 §41.1）：连接池必须 autocommit。PostgresSaver.setup() 跑的是它自带的
    MIGRATIONS，其中 checkpoint_*_thread_id_idx 三枚是 CREATE INDEX CONCURRENTLY（实测 .venv 的
    langgraph/checkpoint/postgres/__init__.py MIGRATIONS[6]/[7]/[8]），而 psycopg 默认把每条语句
    包进事务块 ⇒ 非 autocommit 的池每次启动都必抛，与数据库在不在线无关。这条不改 migrations/**、
    也不新增建表 SQL —— 那三枚 CONCURRENTLY 是 langgraph 自己的账。
    """
    if psycopg is None or psycopg_pool is None:
        return _fail_checkpointer_loudly(
            "psycopg / psycopg_pool 未安装，无法使用 PostgresSaver",
            database_reachable=False,
        )
    try:
        psycopg.connect(_PG_URL, connect_timeout=2).close()
    except Exception as e:  # noqa: BLE001 - 探活失败是唯一可以说"数据库不可达"的分支
        return _fail_checkpointer_loudly(
            f"Postgres 探活失败: {type(e).__name__}: {e}", database_reachable=False
        )
    pool = None
    try:
        pool = psycopg_pool.ConnectionPool(
            _PG_URL,
            max_size=50,
            min_size=5,
            open=True,
            # autocommit 是给 setup() 的 CREATE INDEX CONCURRENTLY 让路；prepare_threshold=0
            # 是 langgraph 对 PostgresSaver + 连接池的既定配置（预编译语句在池里会串味）。
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        from langgraph.checkpoint.postgres import PostgresSaver as _PostgresSaver

        cp = _PostgresSaver(pool)
        cp.setup()
    except Exception as e:  # noqa: BLE001 - 这里绝不能再写成"Postgres 不可用"
        if pool is not None:
            try:
                pool.close()
            except Exception:  # noqa: BLE001 - 收尾失败不该盖住真正的原因
                pass
        return _fail_checkpointer_loudly(
            "Postgres 可连，但 PostgresSaver.setup() 失败（这不是数据库不可用）: "
            f"{type(e).__name__}: {e}",
            database_reachable=True,
        )
    _record_checkpointer("postgres", "PostgresSaver 正在持久化图状态（跨进程共享，重启不丢）")
    logger.info("[Orchestrator] 使用 PostgresSaver 持久化")
    return cp


_checkpointer = _make_checkpointer()
_trace_store = default_trace_store()

# ============ Worker 子图（带 checkpointer，仅本轮内可持久化；跨轮不回读：checkpoint_ns 每轮换 uuid · R118/R127） ============

DOC_PROMPT = """你是文档搜索专家。搜公司知识库回答问题。一次想好几个搜索方向，同时搜多个关键词，避免来回。返回完整准确结果并引用来源文件名。"""
DATA_PROMPT = """你是数据分析专家。分析经营数据回答问题。一次想好几个分析角度，同时查多个维度。返回详细结论和关键数字。
简单排名/统计用 analyze_data；组合条件/复杂计算用 query_data（LLM生成pandas+沙箱执行）。"""
CHART_PROMPT = """你是图表生成专家。用户要画图时，如果数据不明确，先用 analyze_data 取真实数据，再调用 generate_chart。labels 和 values 必须来自实际数据。"""
EXPORT_PROMPT = """你是报告导出专家。确认内容后直接调用 export_report。"""

# The four worker graphs write prose answers, so they are the analysis tier: the largest
# output cap and the longest clock. Named explicitly, because a bare _make_model() reads
# as "the default" and the whole point of the tier is that it is a decision.
doc_graph = create_react_agent(_make_model(ModelTier.ANALYSIS), [search_docs], prompt=DOC_PROMPT, checkpointer=_checkpointer)
data_graph = create_react_agent(_make_model(ModelTier.ANALYSIS), [analyze_data, query_data], prompt=DATA_PROMPT, checkpointer=_checkpointer)
chart_graph = create_react_agent(_make_model(ModelTier.ANALYSIS), [analyze_data, generate_chart], prompt=CHART_PROMPT, checkpointer=_checkpointer)
export_graph = create_react_agent(_make_model(ModelTier.ANALYSIS), [export_report], prompt=EXPORT_PROMPT, checkpointer=_checkpointer)


def _fallback_export_result(user_message: str, model_result: str, config=None) -> str:
    """Ensure an export request produces a usable artifact when the model omits tool args."""
    if "/api/v1/artifacts/" in model_result:
        return model_result
    title = "企业经营分析报告"
    sections = json.dumps(
        [
            {"type": "heading", "content": title},
            {"type": "text", "content": f"用户导出要求：{user_message}"},
            {"type": "text", "content": model_result or "已完成当前会话分析。"},
        ],
        ensure_ascii=False,
    )
    payload = {
        "report_title": title,
        "sections_json": sections,
        "include_charts": "",
    }
    if hasattr(export_report, "invoke"):
        return export_report.invoke(payload, config=config)
    return export_report(**payload, config=config)

# ==================== dispatch 工具 ====================

class DispatchInput(BaseModel):
    workers: list[str]

@tool(args_schema=DispatchInput)
def dispatch(workers: list[str]) -> str:
    """派发任务给专业子Agent并行处理。

    workers可选值:
    - "doc": 文档搜索（查制度/流程/案例/知识库）
    - "data": 数据分析（Excel/CSV经营数据）
    - "chart": 图表生成（已有数据→可视化图表）
    - "export": 报告导出（素材→PDF报告）

    子Agent返回结果后，你负责综合汇总成最终回答。不要重复派发同一个worker。
    """
    return f"已派发 {len(workers)} 个子Agent: {', '.join(workers)}"

main_model = _make_model(ModelTier.ANALYSIS).bind_tools([dispatch])

# ==================== supervisor 节点 ====================

MAIN_SYSTEM = HumanMessage(content="""你是企业智脑调度中心。你只有一个工具: dispatch。

职责：理解用户问题 → dispatch 派发给专业子Agent → 汇总子Agent结果

派发规则:
- 查文档/制度/流程/案例 → dispatch(["doc"])
- 数据排名/统计/分析/计算 → dispatch(["data"])
- 同时查文档+分析数据 → dispatch(["doc","data"])
- 画图/图表/可视化/柱状图/折线图/饼图 → 只派 dispatch(["chart"])
- 导出PDF报告 → 只派 dispatch(["export"])

关键:
- 数字/排名/统计=数据分析=data，不是文档搜索！
- 画图=chart，不要同时派doc或data！
- 子Agent返回后，汇总成本轮最终回答。图表Agent结果中如果有图片链接(![xxx](...))，务必在汇总中保留
- 不重复对话历史中的旧回答""")


# ==================== R27 · 确定性计划命中不再发第二发 ====================
#
# 判据①：第二发是图结构必然结果，不是模型选择。route_main 在 :332 返回
# ["main_tools", Send(worker)...]，而 _builder 上 main_tools 与每个 worker 都挂着无条件
# 回到 supervisor 的硬边（:688-:693），所以本轮只要派发过就必然再进一次
# main_agent_node；:201 那一发的 prompt 只有 [sys_msg, current_user_msg]，worker 结果
# 一个字都不进上下文，temperature=0 之下第 2 发只能把第 1 发的决策原样复读一遍，
# route_main 再按 worker_results 把它判成 remaining=[] → reflect。实测 15.931 s 买了
# 一个被代码丢掉的决策（docs/perf/latency-budget-2026-09-16.md §3.3）。
#
# 短路三条件缺一不可：① 本轮 plan 逐 worker 等于确定性计划器的输出；② 本轮已经有
# dispatch 决策可复读；③ reflect 没有判 redo（复审回炉是模型唯一的二次纠正面）。
# 未命中时一行都不多走，路径与今天逐字一致；route_main 的关键词/计划兜底
# （:285-305）原样保留，仍是命中轮次的实际决策者。


def _current_turn(state: AgentState) -> tuple[str, list]:
    """本轮的用户问题，以及这条问题之后新增的消息（第 1 发进 supervisor 时为空）。"""
    msgs = state.get("messages") or []
    for i in range(len(msgs) - 1, -1, -1):
        if type(msgs[i]).__name__ == "HumanMessage":
            return str(msgs[i].content or ""), msgs[i + 1:]
    return "", list(msgs)


def _deterministic_plan_hit(state: AgentState, question: str) -> bool:
    """state["plan"] 是否就是 planner.build_task_plan 的确定性输出。"""
    planned = [
        task.get("worker")
        for task in (state.get("plan") or [])
        if isinstance(task, dict)
    ]
    if not planned:
        return False
    try:
        expected = [task["worker"] for task in build_task_plan(question)]
    except Exception as exc:  # pragma: no cover - 纯规则函数，异常一律按未命中处理
        logger.warning(f"[Supervisor] 确定性计划比对失败，按未命中处理: {exc}")
        return False
    return planned == expected


def _prior_dispatch_decision(turn_messages: list):
    """本轮 supervisor 已经做出的那次 dispatch 决策，没有则 None。"""
    for msg in reversed(turn_messages):
        if type(msg).__name__ != "AIMessage":
            continue
        for call in getattr(msg, "tool_calls", None) or []:
            if call.get("name") == "dispatch":
                return msg
    return None


def main_agent_node(state: AgentState) -> dict:
    all_msgs = state.get("messages", [])

    # 短期记忆：R33 起确定性裁剪，零模型。旧写法在这里多发一发 COMPRESS 往返，让本机模型
    # 把旧历史写成一句摘要，而这条线上唯一消费 all_msgs 的地方是下面“取本轮最后一条
    # HumanMessage”那一圈：supervisor 真正发出的 prompt 只有 [sys_msg, current_user_msg]
    # （tests/test_supervisor_roundtrip.py:7-9 早就把这一点当既成事实钉着），摘要串与 worker
    # 结果一个字都不进上下文 —— 那一发买回来的东西当场被丢掉，是纯开销。
    # 预算也不再由裁剪自己猜：交给真正吃这份历史的 supervisor 那一档（:259 main_model 用的
    # ModelTier.ANALYSIS）的 input_budget_tokens。ModelTier.COMPRESS 这一档**保留**，档位预算
    # 校准用例 tests/test_r30_timeout_budget.py 仍按它量表；生产路径自 R33 起不再调用它。
    all_msgs = compress_messages(all_msgs, tier=ModelTier.ANALYSIS)

    # 长期记忆注入
    mem = state.get("memory") or {}
    long_mem = mem.get("long") or []
    profile_ctx = mem.get("profile_context") or ""
    mem_ctx = ""
    if long_mem:
        mem_ctx = "\n\n【用户历史记忆】\n" + "\n".join(f"- {m}" for m in long_mem)
    if profile_ctx:
        mem_ctx += "\n\n【用户画像】\n" + profile_ctx

    current_user_msg = None
    for m in reversed(all_msgs):
        if type(m).__name__ == "HumanMessage":
            current_user_msg = m
            break
    if current_user_msg is None:
        current_user_msg = HumanMessage(content="请完成你的专业工作。")

    last_user_idx = -1
    for i in range(len(all_msgs) - 1, -1, -1):
        if type(all_msgs[i]).__name__ == "HumanMessage":
            last_user_idx = i
            break

    filtered = []
    for i, m in enumerate(all_msgs):
        mtype = type(m).__name__
        if mtype == "HumanMessage":
            filtered.append(m)
        elif mtype == "AIMessage":
            if getattr(m, "tool_calls", None):
                filtered.append(m)
            elif i > last_user_idx and getattr(m, "content", ""):
                filtered.append(m)
        else:
            filtered.append(m)

    sys_msg = MAIN_SYSTEM
    if mem_ctx:
        sys_msg = HumanMessage(content=MAIN_SYSTEM.content + mem_ctx)

    # R27：确定性计划命中时把第 1 发的决策原样补回消息尾部（换一个新 id，让
    # add_messages 是追加而不是就地覆盖），交给同一条 route_main 收敛：分层派发、
    # HITL 挂起、已完成 worker 的过滤全部不变，与"模型再复读一遍决策"逐字同形，
    # 只是不再花一次模型往返。
    if not state.get("redo"):
        turn_question, turn_messages = _current_turn(state)
        prior = _prior_dispatch_decision(turn_messages)
        if prior is not None and _deterministic_plan_hit(state, turn_question):
            replay = prior.model_copy(update={"id": f"supervisor-replay-{uuid4().hex}"})
            logger.info("[Supervisor] 确定性计划命中 → 复读第 1 发 dispatch，跳过第二发模型往返")
            return {"messages": [replay]}

    resp = main_model.invoke([sys_msg, current_user_msg])

    tools = getattr(resp, "tool_calls", None) or []
    if tools:
        workers = tools[0].get("args", {}).get("workers", [])
        logger.info(f"[Supervisor] → dispatch({workers})")
    else:
        logger.info(f"[Supervisor] → 最终回答 ({len(resp.content or '')}字)")

    return {"messages": [resp]}

# 图在编译时带 interrupt_before=["chart", "export"]，并行派发含这两个节点的
# 超步骤会在执行前整体中断，同批 doc/data 的结果一起丢失。图表和导出又必须读取
# 分析结果才能产出真实来源，所以每轮只放行依赖已就绪的一层。
_UPSTREAM = {
    "chart": ("doc", "data"),
    "export": ("doc", "data", "chart"),
    "approval": ("doc", "data"),
}

# 这些节点在编译时带 interrupt_before，因此只能单独占一个 superstep；编译、路由和
# check_interrupt 共用同一个常量，避免三处定义各自漂移。
_HITL_PARKED = ("chart", "export")

_HITL_LABELS = {"chart": "📈 生成图表", "export": "📋 导出报告"}

# 用户问题里的《xxx.pdf》、report.xlsx 描述的是被提问的对象，不是“导出 PDF”这个
# 动作。旧版本正是被文件名里的 .pdf 触发了 export 关键词分支。
_DOC_REFERENCE = re.compile(
    r"《[^》]*》|\S+\.(?:pdf|docx?|xlsx?|csv|md|pptx?|txt)\b",
    re.IGNORECASE,
)


def _intent_text(user_message: str) -> str:
    """剥离文档引用后的意图文本，供关键词兜底使用。"""
    return _DOC_REFERENCE.sub(" ", user_message or "")


# ==================== 路由 ====================

def route_main(state: AgentState, config=None):
    """决定这一轮派谁出门。

    ``config`` 只为一件事存在：读出调用方声明的档位（R141）。不传时（全部既有单参数
    直调，含 tests/test_r42_zero_model_calls.py 的 105 题全量）本函数与改动前逐字节相同。
    """
    last = state["messages"][-1]
    tools = getattr(last, "tool_calls", None) or []

    dispatches = []
    for tc in tools:
        if tc["name"] == "dispatch":
            dispatches.extend(tc["args"].get("workers", []))

    valid = {"doc", "data", "chart", "export", "approval"}
    workers = []
    seen = set()
    for w in dispatches:
        if w in valid and w not in seen:
            workers.append(w)
            seen.add(w)

    user_msg = ""
    for m in reversed(state.get("messages", [])):
        if type(m).__name__ == "HumanMessage":
            user_msg = getattr(m, "content", "") or ""
            break

    planned_workers = []
    for task in state.get("plan") or []:
        worker = task.get("worker") if isinstance(task, dict) else None
        if worker in valid and worker not in planned_workers:
            planned_workers.append(worker)

    # 保留关键词兜底纠正（与 LLM 决策互为保险）
    chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]
    data_kw = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]
    export_kw = ["导出", "PDF", "pdf", "报告", "下载"]
    doc_kw = [
        "制度", "流程", "报销", "审批", "住宿费", "差旅", "员工手册",
        "入职", "安全", "规定", "标准", "谁审批", "审批人",
    ]
    intent_text = _intent_text(user_msg)
    ai_answer_text = str(getattr(last, "content", "") or "").strip()
    # supervisor 既没派发也没给出正文时，确定性计划就是本轮契约。旧版本只在
    # len(planned_workers) > 1 时才尊重计划，单步计划被关键词规则整组覆盖。
    abstained = not workers and not ai_answer_text

    if planned_workers and (len(planned_workers) > 1 or abstained):
        workers = list(planned_workers)
        # planner 从不排 export，图表/导出这类副作用步骤只能追加，
        # 顺序交由下面的分层派发决定，不再取代检索与分析。
        if "chart" not in workers and any(kw in intent_text for kw in chart_kw):
            workers.append("chart")
        elif "export" not in workers and any(kw in intent_text for kw in export_kw):
            workers.append("export")
    else:
        # 保留关键词兜底纠正（与 LLM 决策互为保险），但只作用在剥离文档引用后的文本上
        if any(kw in intent_text for kw in chart_kw):
            if workers != ["chart"]:
                workers = ["chart"]
        elif any(kw in intent_text for kw in export_kw) and not any(kw in intent_text for kw in chart_kw):
            if workers != ["export"]:
                workers = ["export"]
        elif any(kw in intent_text for kw in doc_kw) and not any(kw in intent_text for kw in data_kw):
            # 制度、报销、差旅等事实性问题必须优先检索知识库，
            # 避免 supervisor 将政策问题误派给数据分析 Agent。
            if workers != ["doc"]:
                workers = ["doc"]
        elif any(kw in intent_text for kw in data_kw) and "chart" not in workers:
            if "data" not in workers:
                workers = ["data"]
        if workers and all(worker in ("chart", "export") for worker in workers):
            # 图表和报告不能凭空产生：把计划里尚未完成的分析型 worker 补在前面。
            for worker in planned_workers:
                if worker not in workers and worker not in ("chart", "export"):
                    workers.insert(0, worker)

    # R42 判别器只接管一种局面：supervisor 弃权、计划为空、关键词一条不命中，
    # 也就是 route_main 收尾那句 `if not workers: return "reflect"`——派发列表为空
    # 却已经进了 reflect 的死轮。
    # 今天这一轮以空答案收尾 ⇒ reflect 判 redo ⇒ 再花一发 supervisor 往返。
    # 判别器在这里只允许**补一次读操作**（doc 检索）：分析/报告道的弃权轮原样交给
    # reflect，因为 chart/export 是 HITL 挂起的副作用节点，不该由便宜规则代发。
    # 反过来，命中 chart_kw/export_kw/data_kw 的题早在上面就被兜底升档了，
    # 这条永远抢不过它——判据②"兜底仍能升档"正是靠这个先后顺序成立。
    if not workers and abstained and classify_route(intent_text).lane == LANE_QA:
        workers = ["doc"]
        if not route_probe_quiet():
            logger.info("[R42] 弃权轮判为问答档 → 补派 doc，不再空转一轮")

    # R141 判据①：显式声明的档位在这一格落地成"腿的有无"。上面那句 R42 补派一个字不动
    # —— 它管的是"系统判出来的问答档不许空转"，本节管的是"人明确点了问答档不许跑重活"。
    # 只在真有了声明时才多算一次规则判别（resolve_turn_lane 不打 [R42] 日志，锚点频次不变）。
    declared = declared_lane_from_config(config)
    if declared:
        turn = resolve_turn_lane(intent_text, declared)
        kept, cut, added = decide_workers(
            turn,
            workers,
            has_data=bool(((config or {}).get("configurable") or {}).get("data_filename")),
            abstained=abstained,
        )
        if cut or added:
            workers = list(kept)
            if not route_probe_quiet():
                logger.info(
                    f"[R141] 声明档 {turn.lane}（系统判 {turn.rules_lane}）"
                    f" → 派 {workers or '-'} | 砍 {','.join(cut) or '-'}"
                    f" | 补 {','.join(added) or '-'}"
                )

    completed_workers = set((state.get("worker_results") or {}).keys())
    remaining = [worker for worker in workers if worker not in completed_workers]
    ready = [
        worker
        for worker in remaining
        if not any(upstream in remaining for upstream in _UPSTREAM.get(worker, ()))
    ]
    # 待确认节点只能自己一轮：它会把整个 superstep 停在执行之前，同批真实工作会一起消失。
    work = [worker for worker in ready if worker not in _HITL_PARKED]
    if work and any(worker in _HITL_PARKED for worker in ready):
        ready = work
    # ready 为空但 remaining 非空只能是循环依赖，此时照旧派发，不允许静默丢任务。
    workers = ready or remaining
    if not workers:
        return "reflect"

    if not route_probe_quiet():
        logger.info(f"[Route] dispatch → {workers}")
    return ["main_tools"] + [Send(w, state) for w in workers]

# ==================== Worker Wrapper（传 thread_id） ====================

def _make_worker_wrapper(graph, name: str):
    def node(state: AgentState, config) -> dict:
        parent_conf = (config or {}).get("configurable", {}) or {}
        # 取消检查点 2（即将开工）：并行 worker 可能共享同一次流边界，边界检查只
        # 拦得住第一个，故逐节点再查一遍。放在 trace 与 invoke 之前，取消时不会留下
        # 半截 step.started。
        _raise_if_cancelled(parent_conf.get("cancel_event"))
        parent = parent_conf.get("thread_id", "default")
        request_id = str(parent_conf.get("request_id") or "")
        trace_id = str(parent_conf.get("trace_id") or "")
        task_id = str(parent_conf.get("task_id") or "")
        step_id = f"{trace_id}:worker:{name}" if trace_id else ""
        evidence_bag = new_evidence_bag()
        # R127（= R118 乙案·乙-1）：下面这枚子线程号本身是稳定的（同一会话内跨轮恒定），
        # 但线程号恒定不等于子图能回读上一轮——langgraph 给父节点内的嵌套 invoke 注入的
        # checkpoint_ns 每轮换一枚新 uuid，于是这四张子图是每轮都写、永不回读：子图每轮进
        # 模型的 prompt 恒等于 [system, 本轮那条 HumanMessage]。别把建图那几行的 checkpointer=
        # 当跨轮记忆用；撤不撤它是 R128 的决策，形状钉在 tests/test_r118_subgraph_memory.py。
        child_conf = {"thread_id": f"{parent}:{name}"}
        # 阶段 2：把调用者身份传给子图，工具可据此做权限过滤
        for k in (
            "username",
            "role",
            "department",
            "data_filename",
            "principal",
            "request_id",
            "trace_id",
            "task_id",
            # 取消标记必须一路传到子图：工具（chart/export）在子图里执行，只改父层的
            # 话子图看不到标记，检查点 2/3 就等于恒不触发。
            "cancel_event",
        ):
            if k in parent_conf:
                child_conf[k] = parent_conf[k]
        child_conf["worker"] = name
        child_conf["evidence_bag"] = evidence_bag
        if step_id:
            child_conf["step_id"] = step_id
        child_cfg = {"configurable": child_conf}

        msgs = state.get("messages", [])
        user_msg = None
        for m in reversed(msgs):
            if isinstance(m, HumanMessage):
                user_msg = m
                break
        if user_msg is None:
            user_msg = HumanMessage(content="请完成你的专业工作。")

        owner_id = _owner_id_from(parent_conf)
        started = time.monotonic()
        _record_trace(
            _trace_store,
            trace_id=trace_id,
            request_id=request_id,
            task_id=task_id,
            event_type="step.started",
            status="running",
            payload={
                "step_id": step_id,
                "worker": name,
                "sequence": _step_sequence(state, name),
                "input_summary": {"question_length": len(str(user_msg.content or ""))},
            },
            owner_id=owner_id,
        )
        logger.info(f"[{name}] 开始执行...")
        result = graph.invoke({"messages": [user_msg]}, config=child_cfg)
        out_msgs = result.get("messages", [])
        final = ""
        for m in reversed(out_msgs):
            if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
                final = m.content
                break
        if name == "export":
            # 取消检查点 3（即将落盘）：_fallback_export_result 自己会生成 PDF，所以
            # 即使图已经跑到这里，仍然拦得住最后一个副作用。
            _raise_if_cancelled(parent_conf.get("cancel_event"))
            final = _fallback_export_result(user_msg.content, final, config=child_cfg)

        duration_ms = int((time.monotonic() - started) * 1000)
        agent_result = build_agent_result(
            worker=name,
            answer=final,
            bag=evidence_bag,
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
            session_id=str(parent_conf.get("thread_id") or ""),
            duration_ms=duration_ms,
        )
        summary = summarize_agent_result(agent_result)
        logger.info(f"[{name}] 完成 status={agent_result.status} 结果 {len(agent_result.answer)} 字")
        _record_trace(
            _trace_store,
            trace_id=trace_id,
            request_id=request_id,
            task_id=task_id,
            event_type="step.finished",
            status="completed" if agent_result.status in {"success", "partial"} else agent_result.status,
            payload={"step_id": step_id, "worker": name, "summary": summary},
            owner_id=owner_id,
        )
        return {
            "worker_results": {**state.get("worker_results", {}), name: agent_result.answer},
            "agent_results": {**state.get("agent_results", {}), name: agent_result.model_dump(mode="json")},
            "messages": [AIMessage(content=f"【{name} Agent 返回】\n{agent_result.answer}")],
        }
    return node


# ==================== 取消协同退出（R12） ====================


class RequestCancelled(RuntimeError):
    """调用方已不再接收本轮结果——注意它**不是**拒绝。

    用户按「停止」只表示"这一轮我不看了"。它既不该把挂起的 HITL 动作判成 refused
    （那是 ``approved=False`` 分支的语义，r8 修过"拒绝必须真的拒绝"，不许回退），
    也不该让被停掉的动作继续跑完并落盘。所以本异常只在三个"即将产生新副作用"的
    检查点抛出：

    1. 每次准备向 langgraph 拉下一个 superstep 之前（``_cancellable_stream``）；
    2. 每个 worker 节点准备开工之前（``_make_worker_wrapper.node``）；
    3. export 兜底准备写 PDF 之前。

    抛出时不写 ``worker_results``、不调 ``update_state``，checkpoint 里的 ``next``
    原样留着：会话仍是挂起态，等 R13 的待办端点把它列出来。
    """


def _is_cancelled(cancel_event) -> bool:
    """把 ``cancel_event`` 当"可选取消标记"读：None / 无 is_set 一律算未取消。

    标记走 ``config["configurable"]``，和 ``principal`` 同一条通道，不引入进程级可变
    全局——线程池里并发跑多个请求时，全局标记会互相误伤。R18 之后调用方给的是
    ``chat.CancelGeneration``（``Event`` 的子类，自带 ``(session_id, epoch)`` 身份），
    所以这里每个检查点读到的对象就是"本次运行那一代"本身：标记不可共享、不可复用，
    跨代泄漏在传参这一步就已经堵死，比按会话名回查登记表更强。
    """
    checker = getattr(cancel_event, "is_set", None)
    return bool(checker()) if callable(checker) else False


def _raise_if_cancelled(cancel_event) -> None:
    if _is_cancelled(cancel_event):
        raise RequestCancelled("request cancelled by the caller")


def _cancellable_stream(graph, payload, config, *, cancel_event=None):
    """``graph.stream(...)`` 的协同退出包装：每次 pull 之前复查取消标记。

    langgraph 的 generator 是惰性的——下一个 superstep 只在 ``next()`` 被调用时才
    执行，所以"pull 之前检查"能保证未开工的节点永不开工，包括即将写盘的
    chart/export。已经在执行的那一个节点不能被中断（Python 线程无法安全强杀），
    这条限制写进了未验证清单。

    ``finally`` 关的是内层 generator：调用方提前 break 时也要把图关掉，不能等 GC。
    """
    stream = graph.stream(payload, config, stream_mode="values", subgraphs=True)
    try:
        while True:
            _raise_if_cancelled(cancel_event)
            try:
                event = next(stream)
            except StopIteration:
                return
            yield event
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


def _owner_id_from(configurable: dict) -> str:
    principal = (configurable or {}).get("principal")
    if principal is None:
        return ""
    user_id = getattr(principal, "user_id", None)
    if user_id is None and isinstance(principal, dict):
        user_id = principal.get("user_id")
    return str(user_id or "")


def _step_sequence(state: AgentState, name: str) -> int:
    completed = len(state.get("agent_results") or {}) or len(state.get("worker_results") or {})
    return max(1, completed + 1)


def _approval_worker_node(state: AgentState, config) -> dict:
    """审批预审：金额来自申请人，标准来自可检索的制度证据。

    缺少任一输入时返回明确的失败记录，不用任何默认金额冒充业务结论。
    """
    configurable = (config or {}).get("configurable", {}) or {}
    request_id = str(configurable.get("request_id") or "")
    trace_id = str(configurable.get("trace_id") or "")
    task_id = str(configurable.get("task_id") or "")
    step_id = f"{trace_id}:worker:approval" if trace_id else ""
    evidence_bag = new_evidence_bag()
    child_conf = {**configurable, "worker": "approval", "evidence_bag": evidence_bag}
    if step_id:
        child_conf["step_id"] = step_id
    child_cfg = {"configurable": child_conf}
    owner_id = _owner_id_from(configurable)

    question = ""
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            question = str(getattr(message, "content", "") or "")
            break

    started = time.monotonic()
    _record_trace(
        _trace_store,
        trace_id=trace_id,
        request_id=request_id,
        task_id=task_id,
        event_type="step.started",
        status="running",
        payload={"step_id": step_id, "worker": "approval", "sequence": 1},
        owner_id=owner_id,
    )

    from app.approval.assistant import build_precheck, extract_standard, parse_expense_request
    from app.agents import tools as agent_tools
    from app.agents.evidence import record_document_hits, record_metric, record_tool_status
    from app.semantics.registry import match_metric_context
    from app.trace.spans import start_tool_call

    parsed = parse_expense_request(question)
    amount = parsed["amount"]
    expense_type = parsed["expense_type"]
    metric = match_metric_context(question)
    if metric is not None:
        record_metric(evidence_bag, metric)

    hits: list[dict] = []
    try:
        principal = agent_tools._tool_principal(child_cfg)
    except PermissionError:
        record_tool_status(
            evidence_bag, tool="approval_precheck", status="rejected", error_code="authorization_required"
        )
    else:
        with start_tool_call(
            child_cfg,
            tool_name="approval_precheck",
            arguments={"expense_type": expense_type, "has_amount": amount is not None},
        ) as span:
            try:
                hits, _ = agent_tools._get_pipeline().search_for_principal(
                    f"{expense_type or '费用'} 标准 上限 限额",
                    principal,
                    top_k=3,
                )
            except Exception as exc:
                code = getattr(exc, "code", "retrieval_unavailable")
                logger.warning(f"[Approval] 制度检索不可用: {exc}")
                span.finish("retrieval_unavailable", error_code=code)
            else:
                record_document_hits(evidence_bag, query=expense_type or "费用标准", hits=hits)
                span.finish("completed", summary={"hit_count": len(hits)})

    standard = extract_standard([str(hit.get("content") or "") for hit in hits])
    evidence_sources = [
        f"{hit.get('source', 'unknown')} chunk={hit.get('chunk_index', '')}".strip()
        for hit in hits
    ]

    missing = []
    if amount is None:
        missing.append("申请金额")
    if standard is None:
        missing.append("可核对的制度标准")
    if missing:
        record_tool_status(
            evidence_bag, tool="approval_precheck", status="failed", error_code="validation_error"
        )
        answer = (
            f"无法给出审批预审结论：缺少{'、'.join(missing)}"
            "（error_code=validation_error），本轮未生成业务结论。"
        )
    else:
        department = str(state.get("department") or getattr(principal, "department", "") or "")
        precheck = build_precheck(
            amount,
            standard,
            department,
            expense_type or "费用",
            evidence_sources,
            currency=metric.currency if metric is not None else None,
        )
        answer = (
            f"审批预审结论：{precheck['status']}。"
            f"申请金额 {precheck['amount']} {precheck['currency']}，"
            f"制度标准 {precheck['standard']} {precheck['currency']}，"
            f"超出 {precheck['excess_amount']} {precheck['currency']}，"
            f"风险等级 {precheck['risk_level']}。建议：{precheck['recommendation']}。"
            f"来源：{'、'.join(evidence_sources)}"
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    agent_result = build_agent_result(
        worker="approval",
        answer=answer,
        bag=evidence_bag,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
        session_id=str(configurable.get("thread_id") or ""),
        duration_ms=duration_ms,
    )
    _record_trace(
        _trace_store,
        trace_id=trace_id,
        request_id=request_id,
        task_id=task_id,
        event_type="step.finished",
        status="completed" if agent_result.status in {"success", "partial"} else agent_result.status,
        payload={"step_id": step_id, "worker": "approval", "summary": summarize_agent_result(agent_result)},
        owner_id=owner_id,
    )
    return {
        "worker_results": {**state.get("worker_results", {}), "approval": agent_result.answer},
        "agent_results": {**state.get("agent_results", {}), "approval": agent_result.model_dump(mode="json")},
        "messages": [AIMessage(content=f"【approval Agent 返回】\n{agent_result.answer}")],
    }


# ==================== 图构建 ====================

main_tool_node = ToolNode([dispatch], handle_tool_errors=True)

_builder = StateGraph(AgentState)

_builder.add_node("classify_intent", classify_intent)
_builder.add_node("respond", respond)
_builder.add_node("load_memory", load_memory)
_builder.add_node("plan", plan)
_builder.add_node("supervisor", main_agent_node)
_builder.add_node("main_tools", main_tool_node)
_builder.add_node("doc", _make_worker_wrapper(doc_graph, "doc"))
_builder.add_node("data", _make_worker_wrapper(data_graph, "data"))
_builder.add_node("chart", _make_worker_wrapper(chart_graph, "chart"))
_builder.add_node("export", _make_worker_wrapper(export_graph, "export"))
_builder.add_node("approval", _approval_worker_node)
_builder.add_node("reflect", reflect_node)
_builder.add_node("synthesize", synthesize)

_builder.add_edge(START, "classify_intent")
_builder.add_conditional_edges("classify_intent", lambda s: "respond" if s.get("intent") == "chat" else "load_memory", ["respond", "load_memory"])
_builder.add_edge("respond", END)
_builder.add_edge("load_memory", "plan")
_builder.add_edge("plan", "supervisor")
_builder.add_conditional_edges("supervisor", route_main)
_builder.add_edge("main_tools", "supervisor")
_builder.add_edge("doc", "supervisor")
_builder.add_edge("data", "supervisor")
_builder.add_edge("chart", "supervisor")
_builder.add_edge("export", "supervisor")
_builder.add_edge("approval", "supervisor")
_builder.add_conditional_edges("reflect", route_reflect, ["supervisor", "synthesize"])
_builder.add_edge("synthesize", END)

multi_agent_graph = _builder.compile(
    checkpointer=_checkpointer,
    interrupt_before=list(_HITL_PARKED),
)

# 队列专用图：无人工确认
queue_graph = _builder.compile(checkpointer=_checkpointer)

# ==================== 公开 API ====================

def run_orchestrator(user_message: str, thread_id: str = "default") -> str:
    config = {"configurable": {"thread_id": thread_id}}
    result = multi_agent_graph.invoke(
        {
            "messages": [HumanMessage(content=user_message)],
            "worker_results": {"__reset__": {}},
            "agent_results": {"__reset__": {}},
            "final_answer": "",
            "reflect_count": 0,
            "redo": False,
            "retry_count": 0,
            "trace_events": [],
        },
        config,
    )
    return _final_of(result)


def run_orchestrator_queue(user_message: str, thread_id: str = "default", *, user: dict | None = None):
    """Queue entry point returning one canonical ``AgentResult`` record."""
    request_id, trace_id, task_id = _execution_ids()
    configurable = {
        "thread_id": thread_id,
        "request_id": request_id,
        "trace_id": trace_id,
        "task_id": task_id,
        **(user or {}),
    }
    initial_state = _initial_execution_state(
        user_message,
        thread_id=thread_id,
        user=user,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
    )
    owner_id = _owner_id_from(configurable)
    started = time.monotonic()
    _record_trace(
        _trace_store,
        trace_id=trace_id,
        request_id=request_id,
        task_id=task_id,
        event_type="request.started",
        status="running",
        payload={"session_id": thread_id, "entry_point": "queue"},
        owner_id=owner_id,
    )
    try:
        result = queue_graph.invoke(initial_state, {"configurable": configurable})
    except Exception as exc:
        _record_trace(
            _trace_store,
            trace_id=trace_id,
            request_id=request_id,
            task_id=task_id,
            event_type="request.failed",
            status="failed",
            payload={"error": str(exc), "entry_point": "queue"},
            owner_id=owner_id,
        )
        raise
    duration_ms = int((time.monotonic() - started) * 1000)
    record = aggregate_agent_result(
        result.get("agent_results") or {},
        answer=_final_of(result),
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
        session_id=thread_id,
        duration_ms=duration_ms,
    )
    terminal = "completed" if record.status in {"success", "partial"} else record.status
    _record_trace(
        _trace_store,
        trace_id=trace_id,
        request_id=request_id,
        task_id=task_id,
        event_type="request.completed",
        status=terminal,
        payload={
            "worker_count": len(result.get("worker_results") or {}),
            "has_final_answer": bool(record.answer),
            "entry_point": "queue",
            "agent_result": summarize_agent_result(record),
        },
        owner_id=owner_id,
    )
    return record


def run_orchestrator_result(user_message: str, thread_id: str = "default", *, user: dict | None = None):
    """Alias kept for the queue worker: the canonical record is the return value."""
    return run_orchestrator_queue(user_message, thread_id=thread_id, user=user)


def _final_of(result) -> str:
    final_answer = str(result.get("final_answer") or "").strip()
    if final_answer:
        return final_answer
    msgs = result.get("messages", [])
    if msgs:
        last = msgs[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "处理失败"


def _execution_ids(
    request_id: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
) -> tuple[str, str, str]:
    request_id = str(request_id or "").strip() or f"req-{uuid4().hex}"
    trace_id = str(trace_id or "").strip() or f"trace-{uuid4().hex}"
    task_id = str(task_id or "").strip() or f"task-{uuid4().hex}"
    return request_id, trace_id, task_id


def _initial_execution_state(
    user_message: str,
    *,
    thread_id: str,
    user: dict | None,
    request_id: str,
    trace_id: str,
    task_id: str,
) -> dict:
    user = user or {}
    state = {
        "messages": [HumanMessage(content=user_message)],
        "worker_results": {"__reset__": {}},
        "agent_results": {"__reset__": {}},
        "final_answer": "",
        "reflect_count": 0,
        "redo": False,
        "retry_count": 0,
        "trace_events": [],
        "session_id": thread_id,
        "request_id": request_id,
        "trace_id": trace_id,
        "task_id": task_id,
    }
    if user.get("principal") is not None:
        state["principal"] = user["principal"]
    return state


def _record_trace(
    store: TraceStore,
    *,
    trace_id: str,
    request_id: str,
    task_id: str,
    event_type: str,
    status: str,
    payload: dict | None = None,
    owner_id: str | None = None,
) -> None:
    try:
        trace_payload = dict(payload or {})
        if owner_id and not trace_payload.get("owner_id"):
            trace_payload["owner_id"] = owner_id
        store.record_event(
            trace_id=trace_id,
            request_id=request_id,
            task_id=task_id,
            event_type=event_type,
            status=status,
            payload=trace_payload,
        )
    except Exception as exc:
        logger.warning("[Trace] event persistence failed: %s", exc)


def _stream_state(event):
    if isinstance(event, tuple):
        event = event[-1] if event else None
    return event if isinstance(event, dict) else None


def run_with_stream(
    user_message: str,
    thread_id: str = "default",
    user: dict | None = None,
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    trace_store: TraceStore | None = None,
    cancel_event=None,
    stream_piece_sink=None,
    declared_lane: str = "",
):
    """流式跑一轮编排。

    ``declared_lane``（R141）是调用方**显式声明**的档位，三值之一或空串。空串＝没声明，
    本轮的道由 R42 判别器按题面判：configurable 里连键都不加，图的形状与 R141 之前逐字节
    相同。非空时它进 ``configurable[DECLARED_LANE_KEY]``，由 route_main 落地成腿的有无、由
    plan() 落地成拆题那一发付不付。未知值在 ``normalize_declared_lane`` 里当场炸：这一层
    是图内守门，不替调用方把拼错的档位猜成"没声明"。

    ``cancel_event`` 是调用方（SSE 生成器）持有的 ``threading.Event``，语义上只表示
    "我不再接收本轮回答"，**不等于拒绝**（详见 ``RequestCancelled``）。不传时为 None，
    排队任务与全部既有调用点行为逐字节不变。

    ``stream_piece_sink`` 是 R31 的片段出口：一个可调用对象，收到模型的每一片
    :class:`app.agents.nodes.StreamPiece`（已按判据③ 合并、按判据② 时间戳不重叠）。
    默认 None 时本函数**不产生任何新事件**——图仍只按 ``stream_mode="values"`` 吐整份
    state 快照，legacy 全量重发一条不改（判据④）。出口之所以挂在这里而不是直接 yield
    进事件流：SSE 的 ``text`` 由 ``app/api/v1/chat.py`` 的 ``_ask_stream`` 在 done 分支
    单发，那枚文件本单禁碰（详见交付说明的符号锚与受阻条目）。
    """
    request_id, trace_id, task_id = _execution_ids(request_id, trace_id, task_id)
    trace_store = trace_store or _trace_store
    # The live chat path puts a Principal model into ``user`` while a queued task puts a
    # serialized dict there, so the owner has to be resolved through the same helper the
    # worker wrappers use. Calling ``.get`` on a Principal aborted every authenticated
    # stream before the graph was reached.
    context = user if isinstance(user, dict) else {}
    owner_id = str(
        context.get("owner_id")
        or _owner_id_from({"principal": context.get("principal")})
        or context.get("user_id")
        or context.get("username")
        or ""
    ).strip()
    config = {
        "configurable": {
            "thread_id": thread_id,
            **(user or {}),
            "request_id": request_id,
            "trace_id": trace_id,
            "task_id": task_id,
        }
    }
    if cancel_event is not None:
        # 取消标记的写入点。它进 configurable 而不是 state：state 要被 checkpointer
        # 序列化（PG 路径下 threading.Event 不可 JSON 化），configurable 才是本次运行
        # 的只读上下文——principal 走的就是同一条通道。
        config["configurable"]["cancel_event"] = cancel_event
    if stream_piece_sink is not None:
        # R31 的入口，和 cancel_event 走同一条通道，理由是同一个：回调不可序列化，
        # 进 state 就会在 PG checkpointer 路径上炸。不注册时这里一个键都不多加，
        # 图的形状与之前逐字节相同（判据④）。
        config["configurable"][STREAM_PIECE_SINK_KEY] = stream_piece_sink
    declared = normalize_declared_lane(declared_lane)
    if declared:
        # 与上面两枚同一个理由：能进 state 的东西才进 state，声明只是一个字符串，但它要影响
        # 的是**图内**派发，跨不过节点的只有 config，所以走同一条 configurable 通道。
        config["configurable"][DECLARED_LANE_KEY] = declared
    initial_state = _initial_execution_state(
        user_message,
        thread_id=thread_id,
        user=user,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
    )
    # 本轮档位读数：与图内 plan()/route_main 读的是同一份规则本体（resolve_turn_lane 不打
    # [R42] 锚点，频次一字不动），user_message 就是 plan() 拿到的那枚文本 ⇒ 读数与生效路径同源。
    turn = resolve_turn_lane(user_message, declared)
    max_attempts = 3
    last_worker_results: dict = {}
    last_state: dict = {}
    _record_trace(
        trace_store,
        trace_id=trace_id,
        request_id=request_id,
        task_id=task_id,
        event_type="request.started",
        status="running",
        # R141 判据① 的第二处出口：不看日志、不猜请求体也能读到"这轮按哪条道走的、
        # 是谁定的"。GET /api/v1/traces/{trace_id} 直接把这一格吐出来。
        payload={"session_id": thread_id, **turn.as_dict()},
        owner_id=owner_id,
    )
    for attempt in range(1, max_attempts + 1):
        try:
            for event in _cancellable_stream(
                multi_agent_graph,
                initial_state,
                config,
                cancel_event=cancel_event,
            ):
                state = _stream_state(event)
                if state is not None:
                    last_state = state
                    worker_results = state.get("worker_results") or {}
                    _record_trace(
                        trace_store,
                        trace_id=trace_id,
                        request_id=request_id,
                        task_id=task_id,
                        event_type="step.progress",
                        status="running",
                        payload={
                            "worker_count": len(worker_results),
                            "has_final_answer": bool(state.get("final_answer")),
                        },
                        owner_id=owner_id,
                    )
                    for worker, result in worker_results.items():
                        if last_worker_results.get(worker) == result:
                            continue
                        _record_trace(
                            trace_store,
                            trace_id=trace_id,
                            request_id=request_id,
                            task_id=task_id,
                            event_type="tool.completed",
                            status="completed",
                            payload={
                                "worker": str(worker),
                                "result_length": len(str(result or "")),
                            },
                            owner_id=owner_id,
                        )
                    last_worker_results = dict(worker_results)
                yield event
            _record_trace(
                trace_store,
                trace_id=trace_id,
                request_id=request_id,
                task_id=task_id,
                event_type="request.completed",
                status="completed",
                payload={
                    "worker_count": len(last_worker_results),
                    "has_final_answer": bool(last_state.get("final_answer")),
                },
                owner_id=owner_id,
            )
            return
        except RequestCancelled:
            # 「停止」是业务动作，既不是 failed 也不是 refused，所以走 request.cancelled
            # 而不是 request.failed。app/trace/store.py:96 早就把它列为终态事件，但全仓
            # 从来没有人 emit 过——补上的正是这个空位。不写 worker_results、不
            # update_state，checkpoint 里的 next 原样保留，parked 会话仍是挂起态。
            _record_trace(
                trace_store,
                trace_id=trace_id,
                request_id=request_id,
                task_id=task_id,
                event_type="request.cancelled",
                status="cancelled",
                payload={"session_id": thread_id, "stage": "step_boundary"},
                owner_id=owner_id,
            )
            logger.info(f"[Orchestrator] 本轮按调用方要求停止 session={thread_id}")
            return
        except Exception as e:
            if _is_cancelled(cancel_event):
                # langgraph 可能把节点抛出的 RequestCancelled 再包一层，marker 才是真相。
                # 不先判它，一次「停止」会被下面的关键词分支当成模型故障去重试。
                _record_trace(
                    trace_store,
                    trace_id=trace_id,
                    request_id=request_id,
                    task_id=task_id,
                    event_type="request.cancelled",
                    status="cancelled",
                    payload={"session_id": thread_id, "stage": "worker_node"},
                    owner_id=owner_id,
                )
                logger.info(f"[Orchestrator] 本轮已停止（节点内取消）session={thread_id}")
                return
            err = str(e).lower()
            if attempt < max_attempts and any(kw in err for kw in (
                "timeout", "connection", "rate limit", "server error"
            )):
                delay = 2 ** (attempt - 1)
                logger.warning(f"重试({attempt}/{max_attempts}), {delay}s后...")
                time.sleep(delay)
                continue
            logger.error(f"执行失败: {e}")
            _record_trace(
                trace_store,
                trace_id=trace_id,
                request_id=request_id,
                task_id=task_id,
                event_type="request.failed",
                status="failed",
                payload={"error": str(e), "attempt": attempt},
                owner_id=owner_id,
            )
            yield {"error": str(e)}
            return


def run_interrupt_stream(
    thread_id: str,
    approved: bool,
    user: dict | None = None,
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    cancel_event=None,
):
    """Resume a parked thread as the caller who owns it.

    A resumed turn executes the same tools as the original one, and those tools take
    their scope from ``configurable``. Resuming with only a thread id made every
    approved action fail closed with ``authorization_required``, so the graph kept
    running with no subject at all.
    """
    request_id, trace_id, task_id = _execution_ids(request_id, trace_id, task_id)
    config = {
        "configurable": {
            "thread_id": thread_id,
            **(user or {}),
            "request_id": request_id,
            "trace_id": trace_id,
            "task_id": task_id,
        }
    }
    if cancel_event is not None:
        # 同上：标记只进本次运行的 configurable，不进要被 checkpoint 序列化的 state。
        config["configurable"]["cancel_event"] = cancel_event
    if approved:
        if _is_cancelled(cancel_event):
            # 连 resume 都不发起：被批准的节点从未获得开工授权，checkpoint 里的 next
            # 原样保留，会话仍是挂起态。停止 ≠ 拒绝，所以这里绝不能落到下面的 else
            # 分支去把动作记成 refused。
            logger.info(f"[Orchestrator] 已停止，未发起 resume session={thread_id}")
            return
        try:
            for event in _cancellable_stream(
                multi_agent_graph,
                Command(resume={"approved": True}),
                config,
                cancel_event=cancel_event,
            ):
                yield event
        except RequestCancelled:
            logger.info(f"[Orchestrator] resume 中途按调用方要求停止 session={thread_id}")
            return
    else:
        # A refusal has to be recorded as that worker's result. Skipping the node alone
        # left it in the plan, so supervisor dispatched it again: the action the user
        # just declined ran anyway, and the turn parked a second time.
        declined = [node for node in (check_interrupt(thread_id) or {}).get("pending") or []]
        note = (
            "已取消，未执行：" + "、".join(_HITL_LABELS.get(node, node) for node in declined)
            if declined
            else "用户取消了此操作。"
        )
        update: dict = {"messages": [AIMessage(content=note)]}
        if declined:
            update["worker_results"] = {node: note for node in declined}
        multi_agent_graph.update_state(config, update)
        # 顺序不能反：refused 必须先落账（84af113 "拒绝必须真的拒绝"），此后的收尾流才
        # 允许被停止打断。把 update_state 挪到流后面，一次取消就会把 refused 变成
        # "什么都没发生"，supervisor 会把刚被拒绝的动作再派一次。
        try:
            for event in _cancellable_stream(
                multi_agent_graph,
                Command(goto="supervisor"),
                config,
                cancel_event=cancel_event,
            ):
                yield event
        except RequestCancelled:
            logger.info(f"[Orchestrator] 拒绝收尾流已停止 session={thread_id}")
            return


def clear_session(thread_id: str):
    try:
        _checkpointer.put(
            {"configurable": {"thread_id": thread_id}},
            {"messages": []},
            {},
        )
    except Exception:
        pass


def check_interrupt(thread_id: str) -> dict | None:
    config = {"configurable": {"thread_id": thread_id}}
    state = multi_agent_graph.get_state(config)
    if state.next:
        pending = [n for n in state.next if n in _HITL_PARKED]
        if pending:
            return {
                "pending": pending,
                "labels": [_HITL_LABELS.get(p, p) for p in pending],
            }
    return None
