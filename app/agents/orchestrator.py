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

from app.agents.state import AgentState, _merge_dicts
from app.approval.assistant import build_precheck
from app.agents.tools import search_docs, analyze_data, query_data, generate_chart, export_report
from app.agents.nodes import (
    _make_model, classify_intent, respond, load_memory, plan,
    reflect_node, route_reflect, synthesize,
)
from app.agents.evidence import (
    aggregate_agent_result,
    build_agent_result,
    new_evidence_bag,
    summarize_agent_result,
)
from app.memory import compress_messages
from app.common.logger import logger
from app.trace.store import TraceStore, default_trace_store

# ==================== 持久化 ====================

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")


def _make_checkpointer():
    """Postgres 可用 → PostgresSaver 持久化；不可用 → 降级 MemorySaver。
    导入时不硬依赖数据库（快速探活 2s），保证无库也能导入/跑逻辑测试。"""
    try:
        psycopg.connect(_PG_URL, connect_timeout=2).close()
        pool = psycopg_pool.ConnectionPool(_PG_URL, max_size=50, min_size=5, open=True)
        from langgraph.checkpoint.postgres import PostgresSaver as _PostgresSaver
        cp = _PostgresSaver(pool)
        cp.setup()
        logger.info("[Orchestrator] 使用 PostgresSaver 持久化")
        return cp
    except Exception as e:
        logger.warning(f"[Orchestrator] Postgres 不可用，降级 MemorySaver: {e}")
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()


_checkpointer = _make_checkpointer()
_trace_store = default_trace_store()

# ==================== Worker 子图（带 checkpointer，可持久化） ====================

DOC_PROMPT = """你是文档搜索专家。搜公司知识库回答问题。一次想好几个搜索方向，同时搜多个关键词，避免来回。返回完整准确结果并引用来源文件名。"""
DATA_PROMPT = """你是数据分析专家。分析经营数据回答问题。一次想好几个分析角度，同时查多个维度。返回详细结论和关键数字。
简单排名/统计用 analyze_data；组合条件/复杂计算用 query_data（LLM生成pandas+沙箱执行）。"""
CHART_PROMPT = """你是图表生成专家。用户要画图时，如果数据不明确，先用 analyze_data 取真实数据，再调用 generate_chart。labels 和 values 必须来自实际数据。"""
EXPORT_PROMPT = """你是报告导出专家。确认内容后直接调用 export_report。"""

doc_graph = create_react_agent(_make_model(), [search_docs], prompt=DOC_PROMPT, checkpointer=_checkpointer)
data_graph = create_react_agent(_make_model(), [analyze_data, query_data], prompt=DATA_PROMPT, checkpointer=_checkpointer)
chart_graph = create_react_agent(_make_model(), [analyze_data, generate_chart], prompt=CHART_PROMPT, checkpointer=_checkpointer)
export_graph = create_react_agent(_make_model(), [export_report], prompt=EXPORT_PROMPT, checkpointer=_checkpointer)


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

main_model = _make_model().bind_tools([dispatch])

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


def main_agent_node(state: AgentState) -> dict:
    all_msgs = state.get("messages", [])

    # 短期记忆：超阈值自动压缩
    all_msgs = compress_messages(all_msgs, _make_model(timeout=30))

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

def route_main(state: AgentState):
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

    logger.info(f"[Route] dispatch → {workers}")
    return ["main_tools"] + [Send(w, state) for w in workers]

# ==================== Worker Wrapper（传 thread_id） ====================

def _make_worker_wrapper(graph, name: str):
    def node(state: AgentState, config) -> dict:
        parent_conf = (config or {}).get("configurable", {}) or {}
        parent = parent_conf.get("thread_id", "default")
        request_id = str(parent_conf.get("request_id") or "")
        trace_id = str(parent_conf.get("trace_id") or "")
        task_id = str(parent_conf.get("task_id") or "")
        step_id = f"{trace_id}:worker:{name}" if trace_id else ""
        evidence_bag = new_evidence_bag()
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
):
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
    initial_state = _initial_execution_state(
        user_message,
        thread_id=thread_id,
        user=user,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
    )
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
        payload={"session_id": thread_id},
        owner_id=owner_id,
    )
    for attempt in range(1, max_attempts + 1):
        try:
            for event in multi_agent_graph.stream(
                initial_state,
                config,
                stream_mode="values",
                subgraphs=True,
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
        except Exception as e:
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
    if approved:
        for event in multi_agent_graph.stream(
            Command(resume={"approved": True}),
            config,
            stream_mode="values",
            subgraphs=True,
        ):
            yield event
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
        for event in multi_agent_graph.stream(
            Command(goto="supervisor"),
            config,
            stream_mode="values",
            subgraphs=True,
        ):
            yield event


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
