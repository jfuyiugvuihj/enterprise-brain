"""
Multi-Agent: MainAgent (dispatch only) + Doc/Data/Chart/Export 子图
- MainAgent 只有一个工具 dispatch，判断派谁、派发、汇总
- 所有实际工作由 4 个专业 Worker 子图完成
- dispatch 被路由拦截 → Send 并行派发 Worker
- Chart/Export 带 Human-in-the-loop (interrupt_before)
- PostgresSaver 持久化会话
"""
import os
import asyncio
import selectors
import sys
import time
from typing import Annotated
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent, ToolNode
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Send, Command
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
import psycopg_pool

from app.agents.tools import search_docs, analyze_data, generate_chart, export_report
from app.common.logger import logger

# ==================== 持久化 ====================

_PG_URL = os.getenv("DATABASE_URL", "postgresql://fengx@localhost:5432/enterprise_brain")

_pool = psycopg_pool.ConnectionPool(_PG_URL, max_size=50, min_size=5, open=True)
_checkpointer = PostgresSaver(_pool)
try:
    _checkpointer.setup()
except Exception:
    pass

# ==================== 共享模型工厂 ====================

def _make_model(timeout: int = 60):
    return ChatOpenAI(
        base_url="https://api.deepseek.com",
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        model="deepseek-chat",
        temperature=0,
        max_retries=2,
        request_timeout=timeout,
    )

# ==================== Worker 子图 (create_react_agent) ====================

DOC_PROMPT = """你是文档搜索专家。搜公司知识库回答问题。一次想好几个搜索方向，同时搜多个关键词，避免来回。返回完整准确结果并引用来源文件名。"""

DATA_PROMPT = """你是数据分析专家。分析经营数据回答问题。一次想好几个分析角度，同时查多个维度。返回详细结论和关键数字。"""

CHART_PROMPT = """你是图表生成专家。用户要画图时，如果数据不明确，先用 analyze_data 取真实数据，再调用 generate_chart。labels 和 values 必须来自实际数据。"""

EXPORT_PROMPT = """你是报告导出专家。确认内容后直接调用 export_report。"""

doc_graph = create_react_agent(_make_model(), [search_docs], prompt=DOC_PROMPT)
data_graph = create_react_agent(_make_model(), [analyze_data], prompt=DATA_PROMPT)
chart_graph = create_react_agent(_make_model(), [analyze_data, generate_chart], prompt=CHART_PROMPT)
export_graph = create_react_agent(_make_model(), [export_report], prompt=EXPORT_PROMPT)

# ==================== MainAgent 的 dispatch 工具 ====================

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

    并行示例: dispatch(["doc","data"]) 同时搜文档+分析数据
    单一示例: dispatch(["doc"]) 只查文档

    子Agent返回结果后，你负责综合汇总成最终回答。不要重复派发同一个worker。
    """
    return f"已派发 {len(workers)} 个子Agent: {', '.join(workers)}"

main_model = _make_model().bind_tools([dispatch])

# ==================== State ====================

def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}

class AgentState(dict):
    messages: Annotated[list, add_messages]
    worker_results: Annotated[dict, _merge_dicts]

# ==================== MainAgent Node ====================

MAIN_SYSTEM = HumanMessage(content="""你是企业智脑调度中心。你只有一个工具: dispatch。

职责：理解用户问题 → dispatch 派发给专业子Agent → 汇总子Agent结果

派发规则:
- 查文档/制度/流程/案例 → dispatch(["doc"])
- 数据排名/统计/分析/计算 → dispatch(["data"])
- 同时查文档+分析数据 → dispatch(["doc","data"])
- 画图/图表/可视化/柱状图/折线图/饼图 → 只派 dispatch(["chart"])
- 导出PDF报告 → 只派 dispatch(["export"])

示例:
- "请假流程" → dispatch(["doc"])
- "哪个门店利润最高" → dispatch(["data"])
- "帮我画营收柱状图" → dispatch(["chart"])
- "安全制度有哪些，营收排名" → dispatch(["doc","data"])

关键:
- 数字/排名/统计=数据分析=data，不是文档搜索！
- 画图=chart，不要同时派doc或data！
- 子Agent返回后，汇总成本轮最终回答。图表Agent结果中如果有图片链接(![xxx](...))，务必在汇总中保留
- 不重复对话历史中的旧回答""")

def main_agent_node(state: AgentState) -> dict:
    all_msgs = state.get("messages", [])
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

    msgs = [MAIN_SYSTEM, *filtered]
    resp = main_model.invoke(msgs)

    tools = getattr(resp, "tool_calls", None) or []
    if tools:
        workers = tools[0].get("args", {}).get("workers", []) if tools else []
        logger.info(f"[MainAgent] → dispatch({workers})")
    else:
        logger.info(f"[MainAgent] → 最终回答 ({len(resp.content or '')}字)")

    return {"messages": [resp]}

# ==================== 路由 ====================

def route_main(state: AgentState) -> str | list[Send]:
    last = state["messages"][-1]
    tools = getattr(last, "tool_calls", None) or []

    if not tools:
        return END

    dispatches = []
    for tc in tools:
        if tc["name"] == "dispatch":
            dispatches.extend(tc["args"].get("workers", []))

    if not dispatches:
        return END

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

    logger.info(f"[Route] 用户问题: {user_msg[:60]}, LLM派发: {workers}")

    chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]
    data_kw = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]
    export_kw = ["导出", "PDF", "pdf", "报告", "下载"]

    if any(kw in user_msg for kw in chart_kw):
        if workers != ["chart"]:
            logger.info(f"[Route] 硬纠正: {workers} → ['chart']")
            workers = ["chart"]
    elif any(kw in user_msg for kw in export_kw) and not any(kw in user_msg for kw in chart_kw):
        if workers != ["export"]:
            logger.info(f"[Route] 硬纠正: {workers} → ['export']")
            workers = ["export"]
    elif any(kw in user_msg for kw in data_kw) and "chart" not in workers:
        if "data" not in workers:
            logger.info(f"[Route] 硬纠正: {workers} → ['data']")
            workers = ["data"]

    if not workers:
        return END

    logger.info(f"[Route] dispatch → {workers}")
    return ["main_tools"] + [Send(w, state) for w in workers]

# ==================== Worker Wrapper ====================

def _make_worker_wrapper(graph, name: str):
    def node(state: AgentState) -> dict:
        msgs = state.get("messages", [])
        user_msg = None
        for m in reversed(msgs):
            if isinstance(m, HumanMessage):
                user_msg = m
                break
        if user_msg is None:
            user_msg = HumanMessage(content="请完成你的专业工作。")
        logger.info(f"[{name}] 开始执行...")
        result = graph.invoke({"messages": [user_msg]})
        out_msgs = result.get("messages", [])
        final = ""
        for m in reversed(out_msgs):
            if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
                final = m.content
                break
        logger.info(f"[{name}] 完成, 结果 {len(final)} 字")
        return {
            f"worker_{name}": final,
            "worker_results": {**state.get("worker_results", {}), name: final},
            "messages": [AIMessage(content=f"【{name} Agent 返回】\n{final}")],
        }
    return node

# ==================== ToolNode ====================

main_tool_node = ToolNode([dispatch], handle_tool_errors=True)

# ==================== Graph 构建 ====================

_builder = StateGraph(AgentState)

_builder.add_node("main_agent", main_agent_node)
_builder.add_node("main_tools", main_tool_node)
_builder.add_node("doc", _make_worker_wrapper(doc_graph, "doc"))
_builder.add_node("data", _make_worker_wrapper(data_graph, "data"))
_builder.add_node("chart", _make_worker_wrapper(chart_graph, "chart"))
_builder.add_node("export", _make_worker_wrapper(export_graph, "export"))

_builder.add_edge(START, "main_agent")
_builder.add_conditional_edges("main_agent", route_main)
_builder.add_edge("main_tools", "main_agent")
_builder.add_edge("doc", "main_agent")
_builder.add_edge("data", "main_agent")
_builder.add_edge("chart", "main_agent")
_builder.add_edge("export", "main_agent")

multi_agent_graph = _builder.compile(
    checkpointer=_checkpointer,
    interrupt_before=["chart", "export"],
)

# ==================== 公开 API ====================

def run_orchestrator(user_message: str, thread_id: str = "default") -> str:
    config = {"configurable": {"thread_id": thread_id}}
    result = multi_agent_graph.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config,
    )
    msgs = result.get("messages", [])
    if msgs:
        last = msgs[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "处理失败"


def run_with_stream(user_message: str, thread_id: str = "default"):
    config = {"configurable": {"thread_id": thread_id}}
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
            Command(goto="main_agent"),
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
