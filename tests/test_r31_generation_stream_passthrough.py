"""R31 判据①④：生成轮流式透传的接线处，与 legacy 全量重发的共存契约。

这个文件钉两件事。

一是**出口那一侧**（`_ResilientModel.stream`）：注册了 sink 才发片，发的片必须满足
判据②③；交回给消费者的 chunk 必须还是原来那枚对象——R31 只许在边上取样，不许改写正文。
以及一条反"冒充"的纪律：provider 中途失败时**收尾那片不许发**，因为那时候流出去的字不
是答案的结尾，把半截缓冲当成最后一块推给出口，判据③ 明确不许。

二是**图的形状**（判据④）：`stream_mode="values"` + `subgraphs=True` 是 legacy 全量重发
的地基，本单不许动，也不许因为多了一根 sink 就往事件流里塞新事件。这两枚在这儿之前
`tests/` 里没有任何用例直接钉过（`rg -l stream_mode tests` = 0 命中），所以判据④ 的
反证靶子由这一份补上。

全程离线：桩图、桩 provider、tmp 里的 trace，不开 socket，不碰模型端口。
"""

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier, Principal
from app.common import model_budget
from app.common.model_budget import model_tier_budget

ANSWER_60 = "".join(f"第{i}句答案内容写得足够长以便跨过二十个字的闸。" for i in range(6))
OFFLINE_PARTS = ["离线第一段", "离线第二段"]
GREETING = [HumanMessage(content="你好")]


@pytest.fixture(autouse=True)
def _one_slot(tmp_path, monkeypatch):
    """一发一个并发额度 + trace 落在 tmp：测试既不打模型，也不往仓库里写东西。"""
    from app.trace import spans
    from app.trace.store import TraceStore

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    store = TraceStore(tmp_path / "r31-events.jsonl")
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    yield store
    model_budget.reset_default_budget()


def _config(sink=None):
    configurable = {
        "principal": Principal(user_id="u-r31", username="staff-r31", roles=["staff"]),
        "request_id": "request-r31",
        "trace_id": "trace-r31",
        "worker": "doc",
    }
    if sink is not None:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return {"configurable": configurable}


class _Provider:
    """假 provider：按给定节拍一次吐一片，不开 socket。"""

    def __init__(self, parts, fail_after=None):
        self.parts = list(parts)
        self.fail_after = fail_after
        self.calls = []

    def stream(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        for index, part in enumerate(self.parts):
            if self.fail_after is not None and index >= self.fail_after:
                raise RuntimeError("provider died mid-stream")
            yield AIMessageChunk(content=part)

    def bind_tools(self, tools):
        return self

    def invoke(self, *args, **kwargs):
        return AIMessageChunk(content="".join(self.parts))


class _OfflineReply:
    def stream(self, *args, **kwargs):
        for part in OFFLINE_PARTS:
            yield AIMessageChunk(content=part)

    def invoke(self, *args, **kwargs):
        return AIMessageChunk(content=OFFLINE_PARTS[0])

    def bind_tools(self, tools):
        return self


def _model(parts, fail_after=None):
    return nodes._ResilientModel(
        _Provider(parts, fail_after=fail_after),
        _OfflineReply(),
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.CHAT),
    )


def _single_char_source(total=60):
    return ["字" for _ in range(total)]


# ==================== 出口：注册 sink 才发片，且发的片合格 ====================


def test_the_generation_leg_publishes_merged_pieces_when_a_sink_is_registered():
    """逐字流的 60 枚增量，出口处必须只剩几片合格的片，而且拼回去一个字不少。"""
    seen = []
    model = _model(_single_char_source(60))
    delivered = list(model.stream(GREETING, config=_config(seen.append)))
    assert "".join(piece.text for piece in seen) == "字" * 60
    assert len(seen) > 1, "判据① 要的正是多发片；这里一片都不发就是没接上"
    assert len(seen) == 3, [piece.chars for piece in seen]
    for piece in seen:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS
    for previous, current in zip(seen, seen[1:]):
        assert previous.end_at <= current.start_at
    assert len(delivered) == 60


def test_the_sink_gets_nothing_when_nobody_registers_one():
    """默认（没有 sink）时这一路必须完全静默——判据④ 的"共存"就是从这儿开始保证的。"""
    model = _model(_single_char_source(30))
    delivered = list(model.stream(GREETING, config=_config()))
    assert "".join(nodes.visible_chunk_text(chunk) for chunk in delivered) == "字" * 30


def test_the_consumer_still_receives_every_original_chunk_object_in_order():
    """R31 只在边上取样：交出去的必须是 provider 给的那枚对象本身，顺序与内容都不许变。"""
    parts = _single_char_source(25)
    provider = _Provider(parts)
    model = nodes._ResilientModel(
        provider, _OfflineReply(), provider="local-openai-compatible",
        model_name="test-model", capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.CHAT),
    )
    seen = []
    delivered = list(model.stream(GREETING, config=_config(seen.append)))
    expected = [AIMessageChunk(content=part) for part in parts]
    assert len(delivered) == len(parts)
    assert [chunk.content for chunk in delivered] == [part for part in parts]
    assert "".join(piece.text for piece in seen) == "".join(parts)
    assert provider.calls, "provider 的 stream 根本没被走到"


def test_a_mid_stream_provider_failure_does_not_publish_a_final_piece():
    """反"冒充"钉：流断在半路时，收尾那片不许发。

    假 provider 在第 20 字之后又挤了 3 个字才死掉：那 3 字属于**没跑完**的那一发，真正的
    答复是随后那发离线回复。把残余缓冲的末片推给出口，等于告诉消费者"答案到此为止"，
    而它并没有到此为止。判据③ 不许拿半截文本冒充终答，这一枚就是那条纪律在 R31 的落点。
    """
    seen = []
    # 取样刻意落在"攒了残余"的那一刻：23 字已到达（20 字已过尺寸闸，3 字还在缓冲里），
    # 第 24 字才炸。第一版把取样写成 20/23，缓冲恰好是空的，反证 F4 当场判不出来——
    # 一枚永远为绿的钉子等于没有钉子。
    model = _model(_single_char_source(26), fail_after=23)
    delivered = list(model.stream(GREETING, config=_config(seen.append)))
    assert [piece.chars for piece in seen] == [20], (
        f"发出去的片是 {[piece.text for piece in seen]}，把没跑完的残余当末片发了"
    )
    assert seen[0].text == "字" * 20
    assert [nodes.visible_chunk_text(chunk) for chunk in delivered[-2:]] == OFFLINE_PARTS


def test_pieces_carry_their_own_arrival_window():
    """判据② 的两枚读数必须都在：起点＝首字到达，终点＝成片时刻，且不早于起点。"""
    seen = []
    model = _model(_single_char_source(41))
    list(model.stream(GREETING, config=_config(seen.append)))
    assert [piece.chars for piece in seen] == [20, 20, 1]
    for piece in seen:
        assert piece.end_at >= piece.start_at
    assert seen[0].source_fragments == 20


# ==================== 判据④：values 全量重发的形状一条不许改 ====================


class _StubGraph:
    """替编译好的图：记下 stream 的关键字参数，并原样吐出生产形状的事件。"""

    def __init__(self, events=None):
        self.events = events if events is not None else [
            ((), {"worker_results": {"doc": "found"}, "final_answer": "found"}),
        ]
        self.stream_kwargs = []
        self.configs = []

    def stream(self, state, config, **kwargs):
        self.stream_kwargs.append(kwargs)
        self.configs.append(config)
        for event in self.events:
            yield event

    def invoke(self, state, config=None, **kwargs):
        return {"final_answer": "found"}


def _collect(monkeypatch, graph, **kwargs):
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)
    return list(
        orchestrator.run_with_stream(
            "差旅住宿标准是多少", thread_id="session-r31", user={"username": "staff1"},
            trace_id="trace-r31-stream", **kwargs,
        )
    )


def test_the_graph_is_still_streamed_in_values_mode_with_subgraphs(monkeypatch):
    """判据④ 的地基，也是本仓第一枚直接钉 `stream_mode="values"` 的用例。

    反证③ 的靶子：把 `_cancellable_stream` 里的 `stream_mode="values"` 摘掉（回到
    langgraph 默认的 `"updates"`）或把 `subgraphs=True` 关掉，这一枚立刻红。
    """
    graph = _StubGraph()
    _collect(monkeypatch, graph)
    assert graph.stream_kwargs == [{"stream_mode": "values", "subgraphs": True}]


def test_no_sink_registered_adds_no_configurable_key_and_no_extra_event(monkeypatch):
    """默认调用点：config 里不多一个键，事件流里不多一枚事件（legacy 逐字节不变）。"""
    graph = _StubGraph()
    events = _collect(monkeypatch, graph)
    assert [event for event in events] == graph.events
    assert nodes.STREAM_PIECE_SINK_KEY not in graph.configs[0]["configurable"]


def test_registering_a_sink_still_leaves_the_event_stream_byte_identical(monkeypatch):
    """接上出口也不许改事件流：sink 是旁路，不是新的事件种类。"""
    seen = []

    def sink(piece):
        seen.append(piece)

    graph = _StubGraph()
    events = _collect(monkeypatch, graph, stream_piece_sink=sink)
    assert events == graph.events
    assert graph.configs[0]["configurable"][nodes.STREAM_PIECE_SINK_KEY] is sink
    assert seen == [], "桩图不发模型增量，出口就不该收到任何片"


@pytest.mark.parametrize(
    "event",
    [
        (("doc:abc",), {"messages": [], "worker_results": {}}),   # 子图命名空间：消费者按 ns 过滤
        ((), "not-a-dict"),                                        # 载荷不是 dict：被 continue 掉
        "plain-string-event",                                      # 整个事件不是 tuple
        ((),),                                                     # 空 tuple
    ],
    ids=["subgraph-namespace", "non-dict-payload", "not-a-tuple", "empty-tuple"],
)
def test_the_shapes_the_sse_consumer_already_tolerates_still_pass_straight_through(monkeypatch, event):
    """与 legacy 全量重发共存：这些怪形状本来就被 `_ask_stream` 忽略，本单一个都不改。"""
    graph = _StubGraph(events=[event])
    seen = []
    events = _collect(monkeypatch, graph, stream_piece_sink=seen.append)
    assert events == [event]
    assert seen == []


def test_cancellation_still_wins_over_the_new_sink(monkeypatch):
    """取消语义没被出口改动：被取消的一轮不许多吐事件，也不许补发末片。"""
    import threading

    flag = threading.Event()
    graph = _StubGraph(events=[((), {"final_answer": "x"}), ((), {"final_answer": "y"})])
    seen = []
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)
    collected = []
    for event in orchestrator.run_with_stream(
        "差旅住宿标准是多少", thread_id="session-r31-cancel", user={"username": "staff1"},
        trace_id="trace-r31-cancel", cancel_event=flag, stream_piece_sink=seen.append,
    ):
        collected.append(event)
        flag.set()
    assert collected == graph.events[:1]
    assert seen == []