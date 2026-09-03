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
import time
from typing import Annotated
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
from app.agents.tools import search_docs, analyze_data, query_data, generate_chart, export_report
from app.agents.nodes import (
    _make_model, classify_intent, respond, load_memory, plan,
    reflect_node, route_reflect, synthesize,
)
from app.memory import compress_messages
from app.common.logger import logger

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

    resp = main_model.invoke([sys_msg, *filtered])

    tools = getattr(resp, "tool_calls", None) or []
    if tools:
        workers = tools[0].get("args", {}).get("workers", [])
        logger.info(f"[Supervisor] → dispatch({workers})")
    else:
        logger.info(f"[Supervisor] → 最终回答 ({len(resp.content or '')}字)")

    return {"messages": [resp]}

# ==================== 路由 ====================

def route_main(state: AgentState):
    last = state["messages"][-1]
    tools = getattr(last, "tool_calls", None) or []

    if not tools:
        return "reflect"   # 产出最终回答 → 反思

    dispatches = []
    for tc in tools:
        if tc["name"] == "dispatch":
            dispatches.extend(tc["args"].get("workers", []))

    if not dispatches:
        return "reflect"

    valid = {"doc", "data", "chart", "export"}
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

    # 保留关键词兜底纠正（与 LLM 决策互为保险）
    chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]
    data_kw = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]
    export_kw = ["导出", "PDF", "pdf", "报告", "下载"]
    if any(kw in user_msg for kw in chart_kw):
        if workers != ["chart"]:
            workers = ["chart"]
    elif any(kw in user_msg for kw in export_kw) and not any(kw in user_msg for kw in chart_kw):
        if workers != ["export"]:
            workers = ["export"]
    elif any(kw in user_msg for kw in data_kw) and "chart" not in workers:
        if "data" not in workers:
            workers = ["data"]

    if not workers:
        return "reflect"

    logger.info(f"[Route] dispatch → {workers}")
    return ["main_tools"] + [Send(w, state) for w in workers]

# ==================== Worker Wrapper（传 thread_id） ====================

def _make_worker_wrapper(graph, name: str):
    def node(state: AgentState, config) -> dict:
        parent_conf = (config or {}).get("configurable", {})
        parent = parent_conf.get("thread_id", "default")
        child_conf = {"thread_id": f"{parent}:{name}"}
        # 阶段 2：把调用者身份传给子图，工具可据此做权限过滤
        for k in ("username", "role", "department"):
            if k in parent_conf:
                child_conf[k] = parent_conf[k]
        child_cfg = {"configurable": child_conf}

        msgs = state.get("messages", [])
        user_msg = None
        for m in reversed(msgs):
            if isinstance(m, HumanMessage):
                user_msg = m
                break
        if user_msg is None:
            user_msg = HumanMessage(content="请完成你的专业工作。")

        logger.info(f"[{name}] 开始执行...")
        result = graph.invoke({"messages": [user_msg]}, config=child_cfg)
        out_msgs = result.get("messages", [])
        final = ""
        for m in reversed(out_msgs):
            if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
                final = m.content
                break
        logger.info(f"[{name}] 完成, 结果 {len(final)} 字")
        return {
            "worker_results": {**state.get("worker_results", {}), name: final},
            "messages": [AIMessage(content=f"【{name} Agent 返回】\n{final}")],
        }
    return node

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
_builder.add_conditional_edges("reflect", route_reflect, ["supervisor", "synthesize"])
_builder.add_edge("synthesize", END)

multi_agent_graph = _builder.compile(
    checkpointer=_checkpointer,
    interrupt_before=["chart", "export"],
)

# 队列专用图：无人工确认
queue_graph = _builder.compile(checkpointer=_checkpointer)

# ==================== 公开 API ====================

def run_orchestrator(user_message: str, thread_id: str = "default") -> str:
    config = {"configurable": {"thread_id": thread_id}}
    result = multi_agent_graph.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config,
    )
    return _final_of(result)


def run_orchestrator_queue(user_message: str, thread_id: str = "default") -> str:
    config = {"configurable": {"thread_id": thread_id}}
    result = queue_graph.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config,
    )
    return _final_of(result)


def _final_of(result) -> str:
    msgs = result.get("messages", [])
    if msgs:
        last = msgs[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "处理失败"


def run_with_stream(user_message: str, thread_id: str = "default", user: dict | None = None):
    config = {"configurable": {"thread_id": thread_id, **(user or {})}}
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            for event in multi_agent_graph.stream(
                {"messages": [HumanMessage(content=user_message)]},
                config,
                stream_mode="values",
                subgraphs=True,
            ):
                yield event
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
            yield {"error": str(e)}
            return


def run_interrupt_stream(thread_id: str, approved: bool):
    config = {"configurable": {"thread_id": thread_id}}
    if approved:
        for event in multi_agent_graph.stream(
            Command(resume={"approved": True}),
            config,
            stream_mode="values",
            subgraphs=True,
        ):
            yield event
    else:
        multi_agent_graph.update_state(
            config,
            {"messages": [AIMessage(content="用户取消了此操作。")]},
        )
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
        pending = [n for n in state.next if n in ("chart", "export")]
        if pending:
            labels = {"chart": "📈 生成图表", "export": "📋 导出报告"}
            return {
                "pending": pending,
                "labels": [labels.get(p, p) for p in pending],
            }
    return None
