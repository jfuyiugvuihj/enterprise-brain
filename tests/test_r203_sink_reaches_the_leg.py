"""R203 判据① 的接线取证：注册在 SSE 那道的 sink，怎么一路走到 react agent 的那一发。

这里钉的是**结构**。orchestrator 交给子图的那本 config 是一张白名单
（app/agents/orchestrator.py::_make_worker_wrapper 里的 for k in (...)），名单里没有
stream_piece_sink。子图仍然看得见它，靠的是 langgraph 把父运行的 configurable 并进嵌套
调用——这条依据一旦断掉，本单的生产者半边就全是空转，所以它必须有用例钉着，而不是有注释
写着。test_the_worker_whitelist_never_mentioned_the_sink 钉的就是"白名单确实没抄这一格"，
于是上面那枚用例绿着的时候，剩下的唯一解释就只有嵌套合并。

两枚用例对着钉：注册了 sink 的那一轮必须流起来；没注册的（队列道、审批道、离线直调）请求体
一个字都不许多。

后半部分是交回单里的**待证②**：approval 这条腿到底接不接得到出口。三枚结构钉把话说死——
挂起那一轮它接得到（child_conf 整本拷贝父 configurable）却没有字可流，续跑那一道它结构上
接不到；于是"审批腿没有逐字"是既定结论而不是漏网，写在这里而不是藏在注释里。
"""

import ast
import inspect
import json
import re
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from typing_extensions import Annotated, TypedDict

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier
from app.api.v1 import chat
from app.approval import assistant as approval_assistant
from app.common import model_budget
from app.common.model_budget import model_tier_budget

ANSWER = "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；二三线城市住宿为每晚 350 元。"
USAGE = {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}
CHUNK_SIZE = 18
QUESTION = "住宿费标准"


@pytest.fixture(autouse=True)
def _offline_budget(tmp_path, monkeypatch):
    from app.trace import spans
    from app.trace.store import TraceStore

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    store = TraceStore(tmp_path / "r203-nested.jsonl")
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    yield
    model_budget.reset_default_budget()


@tool
def search_docs(query: str) -> str:
    """Search the knowledge base."""
    return "制度与口径登记表：一线城市住宿费 500 元/晚。"


def _chunk(delta, finish=None, usage=None):
    body = {
        "id": "cmpl-1",
        "model": "fake",
        "object": "chat.completion.chunk",
        "created": 1,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage is not None:
        body["usage"] = usage
        body["choices"] = []
    return body


def _answer_frames():
    frames = [_chunk({"role": "assistant", "content": ""})]
    starts = list(range(0, len(ANSWER), CHUNK_SIZE))
    for position, start in enumerate(starts):
        last = position == len(starts) - 1
        piece = ANSWER[start:start + CHUNK_SIZE]
        frames.append(_chunk({"content": piece}, finish="stop" if last else None))
    frames.append(_chunk({}, usage=USAGE))
    return frames


def _tool_call_frames():
    return [
        _chunk({"role": "assistant", "content": ""}),
        _chunk({
            "tool_calls": [{
                "index": 0,
                "id": "call-1",
                "type": "function",
                "function": {"name": "search_docs", "arguments": '{"query": "差旅"}'},
            }]
        }),
        _chunk({}, finish="tool_calls"),
    ]


class Wire:
    """每一发请求体进这里：测试据此判这一发改没改走流式，并数 react 的轮次。"""

    def __init__(self):
        self.streams = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        self.streams.append(bool(body.get("stream")))
        if not body.get("stream"):
            # 今天的样子：非流式请求回整段 JSON。分流不是为了省事，是为了让"没注册 sink
            # 的那一发与今天逐字节相同"这枚断言真的能被证伪。
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "id": "cmpl-1",
                    "model": "fake",
                    "object": "chat.completion",
                    "created": 1,
                    "choices": [
                        {
                            "index": 0,
                            "message": _json_message(len(self.streams) > 1),
                            "finish_reason": "stop" if len(self.streams) > 1 else "tool_calls",
                        }
                    ],
                    "usage": USAGE,
                },
            )
        frames = _answer_frames() if len(self.streams) > 1 else _tool_call_frames()
        payload = "".join("data: " + json.dumps(f, ensure_ascii=False) + "\n\n" for f in frames)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(payload + "data: [DONE]\n\n").encode("utf-8"),
        )


def _json_message(is_final):
    """非流式那一发今天长什么样：第一发要工具，第二发给正文。"""
    if is_final:
        return {"role": "assistant", "content": ANSWER}
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "search_docs",
                    "arguments": json.dumps({"query": "差旅"}, ensure_ascii=False),
                },
            }
        ],
    }


class State(TypedDict):
    messages: Annotated[list, add_messages]


def _worker_graph(wire):
    """照抄生产拓扑：父节点用白名单子 config 调子 react agent，白名单里没有 sink 那一格。"""
    transport = httpx.MockTransport(wire.handler)
    primary = ChatOpenAI(
        base_url="http://127.0.0.1:9/v1",
        api_key="x",
        model="fake",
        temperature=0,
        max_retries=0,
        http_socket_options=(),
        http_client=httpx.Client(transport=transport),
        http_async_client=httpx.AsyncClient(transport=transport),
    )
    model = nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="fake",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )
    child = create_react_agent(model, [search_docs])

    def node(state):
        child_conf = {"thread_id": "session-r203:doc", "worker": "doc"}
        return child.invoke(
            {"messages": state["messages"]},
            config={"configurable": child_conf},
        )

    builder = StateGraph(State)
    builder.add_node("worker", node)
    builder.add_edge(START, "worker")
    builder.add_edge("worker", END)
    return builder.compile()


def _parent_config(sink=None):
    configurable = {
        "thread_id": "session-r203",
        "request_id": "request-r203",
        "trace_id": "trace-r203",
    }
    if sink is not None:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return {"configurable": configurable}


def _run_round(sink):
    wire = Wire()
    graph = _worker_graph(wire)
    out = graph.invoke(
        {"messages": [HumanMessage(content=QUESTION)]},
        config=_parent_config(sink),
    )
    return wire, out


def test_a_round_that_registered_a_sink_streams_its_answer_leg():
    seen = []
    wire, out = _run_round(seen.append)

    # 两发都改走了流式：准入只看腿，"这一发是不是终答"由 tap 的 T1 判——工具轮那一发
    # 一个字都不许进出口，所以下面 pieces 只认得出第二发。
    assert wire.streams == [True, True], wire.streams
    assert seen, "注册了 sink 而出口一个字都没收到：那枚 sink 到不了生成腿，本单没落地"
    assert "".join(piece.text for piece in seen) == ANSWER
    assert {piece.worker for piece in seen} == {"doc"}
    assert "" not in {piece.call_id for piece in seen}
    assert len({piece.call_id for piece in seen}) == 1, "工具轮那一发不许有片进出口"
    assert out["messages"][-1].content == ANSWER


def test_a_round_without_a_sink_sends_exactly_todays_request():
    seen = []
    wire, out = _run_round(None)

    assert wire.streams == [False, False], "没注册 sink 的这一发改走流式了"
    assert seen == []
    assert out["messages"][-1].content == ANSWER


def test_the_worker_whitelist_never_mentioned_the_sink():
    """承重的依据：白名单确实没抄这一格，所以上面那枚用例绿了就只剩嵌套合并这一种解释。"""
    source = inspect.getsource(orchestrator._make_worker_wrapper)
    assert "stream_piece_sink" not in source
    assert nodes.STREAM_PIECE_SINK_KEY == "stream_piece_sink"

# ==================== 待证②：approval 这条腿接不接得到出口 ====================


def _function_source(module, name: str) -> str:
    """按名字取模块里某枚函数的源码，**嵌套定义也算**（``_approve_stream`` 藏在路由里面）。"""
    path = Path(inspect.getsourcefile(module))
    text = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{module.__name__} 里找不到 {name}，这条钉的前提变了")


def test_the_resume_runway_has_no_place_to_register_a_sink():
    """挂起之后从 ``/approve`` 续的那一跑道**结构上**接不到出口：签名不收、config 不塞。

    三条各钉一段路，缺一条都不算证过：入口签名没有这一格 → 那本 config 不会塞它 →
    审批道的队列词汇表里根本没有 piece 这一种件。三条同时成立，"审批续跑没有逐字"就不是
    哪里漏了一行，而是这条路上没有可漏的格子；本单因此明写不判它为缺陷。
    """
    params = inspect.signature(orchestrator.run_interrupt_stream).parameters
    assert "stream_piece_sink" not in params, list(params)
    assert nodes.STREAM_PIECE_SINK_KEY not in inspect.getsource(orchestrator.run_interrupt_stream)

    resume = _function_source(chat, "_approve_stream")
    assert nodes.STREAM_PIECE_SINK_KEY not in resume, "审批道自己注册了出口：这条结论要重写"
    kinds = sorted(set(re.findall(r"result_queue\.put\(\(\"(\w+)\"", resume)))
    assert kinds == ["done", "error", "event"], f"审批道长出了第四种件：{kinds}"


def test_the_approval_leg_has_no_model_call_to_stream():
    """审批腿**没有一发模型调用可流**：正文是确定性拼出来的散文，不是模型那一发的 content。

    与 ``test_r203_answer_leg_streams`` 里 ``[approval]`` 那枚的分工：那一枚钉行为（名单挡住它
    ⇒ stream 仍为假、出口零片），本枚钉理由（挡住是对的）：它的 answer 出自 f-string，
    把"每枚帧都是终答的单调前缀"这条硬红线放在它身上无从谈起 —— 与 export 同族。
    """
    source = inspect.getsource(orchestrator._approval_worker_node)
    assert "build_precheck(" in source and "extract_standard(" in source
    assert "answer = (" in source, "正文不再由 f-string 拼出：本枚钉的前提变了，重审名单"
    assert "_ResilientModel" not in source and ".invoke(" not in source

    graph = Path(inspect.getsourcefile(orchestrator)).read_text(encoding="utf-8")
    # 四张工作腿走 react 子图（里面才有模型循环），审批腿挂的是普通节点
    assert '_builder.add_node("approval", _approval_worker_node)' in graph
    for leg in ("doc", "data", "chart", "export"):
        assert f'_builder.add_node("{leg}", _make_worker_wrapper(' in graph, leg

    assistant = Path(inspect.getsourcefile(approval_assistant)).read_text(encoding="utf-8")
    assert "model" not in assistant.lower(), "预审模块里冒出了模型调用：本枚钉要重审"


def test_the_approval_node_would_have_carried_a_registered_sink():
    """它不是"因为接不到所以没做"：审批节点的 child_conf 是父 configurable 的**整本拷贝**。

    与 :func:`orchestrator._make_worker_wrapper` 那张白名单正好相反。所以挡在名单上的是
    准入条件而不是 plumbing 缺失 —— 把它写进名单，它照样一个字也发不出来（上一条已证）。
    """
    source = inspect.getsource(orchestrator._approval_worker_node)
    assert "**configurable" in source, "不再整本拷贝父 config：本枚钉要重审"
    assert '"worker": "approval"' in source

