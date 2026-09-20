"""R117 · 装箱账按轮记，不许跨轮扣房（跟进单 §55，源自 R114 复测交回）。

全离线：不连模型、不起服务、不动数据。检索腿一律 ``monkeypatch`` 掉 ``_get_pipeline``，
一次 socket 都不开、`chroma_db/**` 一个字节都不碰；"模型"是脚本化假 model。

判据 a/b 都走**真装配形状**：`app/agents/orchestrator.py` 的 ``_make_worker_wrapper`` +
真 ``search_docs`` + 子图 checkpointer + 子线程 ``{父会话}:{worker}``。这条路径是 §55 认定
"子图每轮冷启动、上一轮的检索串这一轮不在 prompt 里"的那条，所以跨轮账必须跟着轮走。
"""
import logging
import os
import re

import pytest

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from app.agents import orchestrator, tools
from app.agents.state import AgentState
from app.common.model_budget import estimate_text_tokens
from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS, context_pack_room

#: 一份资料里的关键数字：判据 a 用它钉"第 4 轮仍然读得到本轮那份料"。
KEY_FIGURE = "600"

#: ``[PromptPack]`` 那一行的字段名（判据 c）：一枚不许改名，run3/run4 的日志口径要连续。
PACK_FIELDS = (
    "leg",
    "tier",
    "room_total",
    "room_left",
    "candidates",
    "fitted",
    "dropped",
    "truncated",
    "stub",  # R122 判据 ③：台账唯一的新增枚，插在 truncated 之后，旧字段一枚没动
    "packed_tokens",
    "ledger_packed_tokens",
    "prompt_estimate_tokens",
    "ledger",
    "dropped_labels",
)


def _hits(count):
    """每条命中都装到工具允许的最大正文（``DOC_HIT_CONTENT_CHARS``），一发的串就有 ~500 枚。"""
    filler = (
        "差旅报销制度条款：住宿费限额按职级分档，部门负责人标准每日 %s 元，"
        "超标须事前审批，发票在三十日内提交财务部复核后打款。" % KEY_FIGURE
    ) * 20
    return [
        {
            "source": "差旅报销制度_%d.pdf" % (index + 1),
            "chunk_index": index,
            "_score": round(0.93 - 0.07 * index, 2),
            "content": (filler + str(index))[:DOC_HIT_CONTENT_CHARS],
        }
        for index in range(count)
    ]


class FakePipeline:
    def __init__(self, hits):
        self._hits = hits

    def search_for_principal(self, query, principal, top_k, **kwargs):
        return list(self._hits), ["住宿费限额"]


@pytest.fixture(autouse=True)
def _clean_pack_ledger(request, monkeypatch):
    """装箱账是进程内的：用例之间必须清干净，否则上一条的账会吃掉下一条的 room。"""
    hits = getattr(request, "param", None) or _hits(1)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(hits))
    ledger = getattr(tools, "_pack_ledger", None)
    for book in (ledger, getattr(tools, "_retrieval_pack_support", None)):
        if book is not None:
            book.clear()
    yield
    for book in (ledger, getattr(tools, "_retrieval_pack_support", None)):
        if book is not None:
            book.clear()


@pytest.fixture
def pack_lines(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


def _fields(line):
    return dict(re.findall(r"([a-z_]+)=(\S+)", line))


def _doc_pack_lines(caplog):
    return [
        _fields(record.getMessage())
        for record in caplog.records
        if "[PromptPack]" in record.getMessage() and "leg=doc" in record.getMessage()
    ]


class DocLegModel(BaseChatModel):
    """脚本化假模型：一轮并发 ``calls_per_turn`` 发 ``search_docs``，答案只从 prompt 里活着的料抄。"""

    seen: list = []
    calls_per_turn: int = 1
    issued: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        if isinstance(messages[-1], ToolMessage):
            bodies = "\n".join(
                str(message.content) for message in messages if isinstance(message, ToolMessage)
            )
            read = KEY_FIGURE if re.search(r"每日 \d+ 元", bodies) else "NONE"
            answer = "限额读数=%s｜本轮可见串%d字" % (read, len(bodies))
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])
        calls = []
        for _ in range(self.calls_per_turn):
            self.issued += 1
            calls.append(
                {"name": "search_docs", "args": {"query": "住宿费限额"}, "id": "call%d" % self.issued}
            )
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="我先查制度原文。", tool_calls=calls))]
        )

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "r117-doc-leg"


def _nested_session(calls_per_turn=1, rounds=4):
    """真装配跑几轮：同一 thread、每轮换 trace/request/task（生产就是每请求新生成）。"""
    model = DocLegModel(seen=[], calls_per_turn=calls_per_turn, issued=0)
    child = create_react_agent(
        model, [tools.search_docs], prompt=orchestrator.DOC_PROMPT, checkpointer=MemorySaver()
    )
    builder = StateGraph(AgentState)
    builder.add_node("doc", orchestrator._make_worker_wrapper(child, "doc"))
    builder.add_edge(START, "doc")
    builder.add_edge("doc", END)
    parent = builder.compile(checkpointer=MemorySaver())
    thread_id = "r117-" + os.urandom(5).hex()
    records = []
    for turn in range(1, rounds + 1):
        config = {
            "configurable": {
                "thread_id": thread_id,
                "username": "r117",
                "role": "staff",
                "request_id": "req-%s-%d" % (thread_id, turn),
                "trace_id": "trace-%s-%d" % (thread_id, turn),
                "task_id": "task-%s-%d" % (thread_id, turn),
                "principal": {
                    "user_id": "u-r117",
                    "username": "r117",
                    "roles": ["staff"],
                    "department": "财务部",
                    "status": "active",
                },
            }
        }
        state = parent.invoke(
            {"messages": [HumanMessage(content="住宿费限额是多少（第 %d 问）" % turn)]},
            config=config,
        )
        records.append(
            {
                "turn": turn,
                "answer": str((state.get("worker_results") or {}).get("doc", "")),
                "step_id": "%s:worker:doc" % config["configurable"]["trace_id"],
            }
        )
    return records, thread_id


# ==================== 判据 a：连问 4 轮，第 4 轮的 room 余额＝第 1 轮 ====================


def test_four_rounds_in_one_thread_keep_the_first_round_room_balance(pack_lines, monkeypatch):
    """一轮 3 条命中（≈1450 枚）连问四轮：跨轮不扣房，四轮都得拿到一样的余额。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(3)))
    records, _ = _nested_session(rounds=4)

    lines = _doc_pack_lines(pack_lines)
    assert len(lines) == 4, "四轮各一发装箱账：" + repr(lines)
    assert int(lines[0]["room_left"]) == context_pack_room(), "第 1 轮余额就不该是满 room"
    assert int(lines[-1]["room_left"]) == int(lines[0]["room_left"]), (
        "第 4 轮 room 余额 %s ≠ 第 1 轮 %s：装箱账还在跨轮累加"
        % (lines[-1]["room_left"], lines[0]["room_left"])
    )
    packed = [int(line["packed_tokens"]) for line in lines]
    assert min(packed) > 0, "有轮次批发空了：" + repr(packed)
    assert len(set(packed)) == 1, "四轮装进来的料必须一样多，实测：" + repr(packed)
    assert all(KEY_FIGURE in record["answer"] for record in records), [
        record["answer"] for record in records
    ]


def test_ledger_keys_are_per_turn_and_never_the_session_thread():
    """机制账：四轮各留一本 step 账，谁都不许挂在 thread 上。"""
    records, _ = _nested_session(rounds=4)
    keys = list(tools._pack_ledger)
    assert len(keys) == 4, keys
    assert all(key.startswith("step:") for key in keys), keys
    assert not any(key.startswith("thread:") for key in keys), keys
    for record in records:
        assert "step:" + record["step_id"] in keys, (record["step_id"], keys)


def _tool_config(**overrides):
    conf = {
        "username": "r117",
        "role": "staff",
        "department": "财务部",
        "principal": {
            "user_id": "u-r117",
            "username": "r117",
            "roles": ["staff"],
            "department": "财务部",
            "status": "active",
        },
        "worker": "doc",
    }
    conf.update(overrides)
    return {"configurable": conf}


# ==================== 判据 b：同一轮内并发多发照旧互相扣房 ====================


def test_two_concurrent_calls_in_one_turn_still_deduct_each_other(pack_lines, monkeypatch):
    """一次 react 决策并发两发（DOC_PROMPT 自己就这么写着）：第二发只许拿剩下的 room。

    这条防的是回归到真机 doc-12 的形状——两发各自装满＝合计 3897 枚照样撞墙。
    """
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(3)))
    _nested_session(calls_per_turn=2, rounds=1)

    lines = _doc_pack_lines(pack_lines)
    assert len(lines) == 2, lines
    room = context_pack_room()
    assert int(lines[0]["room_left"]) == room
    assert int(lines[1]["room_left"]) == room - int(lines[0]["packed_tokens"]), (
        "同轮第二发的余额不是第一发剩下的：" + repr(lines)
    )
    assert int(lines[1]["ledger_packed_tokens"]) == sum(
        int(line["packed_tokens"]) for line in lines
    ), "两发的账要累得平"
    assert {line["ledger"] for line in lines} == {"step"}, lines
    assert int(lines[1]["room_left"]) < room, "并发第二发拿到了整只 room＝各吃满"


# ==================== 判据 c：``[PromptPack]`` 台账字段一枚不许改名 ====================


def test_prompt_pack_account_keeps_every_field_name(pack_lines, monkeypatch):
    """run3/run4 的日志口径要连续：字段名与顺序原样，本单只动"这行账记在谁头上"。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(1)))
    _nested_session(rounds=1)

    messages = [
        record.getMessage()
        for record in pack_lines.records
        if "[PromptPack]" in record.getMessage() and "leg=doc" in record.getMessage()
    ]
    assert messages, "一行装箱账都没有，这条用例就成了空响"
    assert tuple(re.findall(r"([a-z_]+)=", messages[0])) == PACK_FIELDS, messages[0]


# ==================== 判据 ④：取不到轮身份时＝照旧按 thread 累加（钉住，不许偷偷放行） ====================


def test_without_turn_identity_the_ledger_still_accumulates_by_thread(pack_lines, monkeypatch):
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(3)))
    config = _tool_config(thread_id="r117-fallback-thread")

    tools.search_docs.invoke({"query": "住宿费限额"}, config=config)
    tools.search_docs.invoke({"query": "住宿费限额 换个词"}, config=config)

    lines = _doc_pack_lines(pack_lines)
    assert [line["ledger"] for line in lines] == ["thread", "thread"], lines
    room = context_pack_room()
    assert int(lines[0]["room_left"]) == room
    assert int(lines[1]["room_left"]) == room - int(lines[0]["packed_tokens"]), (
        "回落口径必须照旧累加：宁可少装，也不许把并发多发放回各自的满 room"
    )


def test_no_identity_at_all_is_billed_off(pack_lines, monkeypatch):
    """连 thread 都没有（直连工具、MCP 单发）：不假装同一条会话，账记 ``ledger=off``。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(3)))
    config = _tool_config()

    tools.search_docs.invoke({"query": "住宿费限额"}, config=config)
    tools.search_docs.invoke({"query": "住宿费限额"}, config=config)

    lines = _doc_pack_lines(pack_lines)
    assert [line["ledger"] for line in lines] == ["off", "off"], lines
    assert all(int(line["room_left"]) == context_pack_room() for line in lines), lines


# ==================== 轮身份取自既有字段：优先级与 worker 隔离 ====================


def test_turn_identity_falls_back_to_request_id_and_resets_next_turn(pack_lines, monkeypatch):
    """step_id 造不出来时（父层没给 trace 的入口）用 request_id 当轮身份：换轮不累加。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(3)))
    for request_id in ("req-r117-1", "req-r117-1", "req-r117-2"):
        tools.search_docs.invoke(
            {"query": "住宿费限额"},
            config=_tool_config(request_id=request_id, thread_id="r117-sess"),
        )

    lines = _doc_pack_lines(pack_lines)
    room = context_pack_room()
    assert [line["ledger"] for line in lines] == ["request", "request", "request"], lines
    assert [int(line["room_left"]) for line in lines] == [
        room,
        room - int(lines[0]["packed_tokens"]),
        room,
    ], "第三发是新的一轮：不许接着吃上一轮的账"


def test_parallel_workers_in_one_turn_keep_separate_accounts(monkeypatch):
    """同一轮里并行的 doc 与 data 不互相扣房（worker 必须进键）。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(3)))
    room = context_pack_room()

    tools.search_docs.invoke(
        {"query": "住宿费限额"}, config=_tool_config(request_id="req-shared", worker="doc")
    )
    tools.search_docs.invoke(
        {"query": "住宿费限额"}, config=_tool_config(request_id="req-shared", worker="data")
    )

    keys = sorted(tools._pack_ledger)
    assert len(keys) == 2, keys
    assert all(key.startswith("request:req-shared:") for key in keys), keys
    assert {key.rsplit(":", 1)[1] for key in keys} == {"doc", "data"}, keys
    assert max(tools._pack_ledger.values()) <= room


def test_turn_key_priority_is_step_then_request_then_task_then_trace():
    assert tools._pack_ledger_key({"configurable": {"step_id": "s", "request_id": "r", "worker": "doc"}}) == "step:s"
    assert tools._pack_ledger_key({"configurable": {"request_id": "r", "task_id": "t", "trace_id": "x", "worker": "doc"}}) == "request:r:doc"
    assert tools._pack_ledger_key({"configurable": {"task_id": "t", "trace_id": "x", "worker": "doc"}}) == "task:t:doc"
    assert tools._pack_ledger_key({"configurable": {"trace_id": "x", "worker": "doc"}}) == "trace:x:doc"
    assert tools._pack_ledger_key({"configurable": {"thread_id": "h", "worker": "doc"}}) == "thread:h:doc"
    assert tools._pack_ledger_key({"configurable": {}}) == ""
    assert tools._pack_ledger_key(None) == ""
