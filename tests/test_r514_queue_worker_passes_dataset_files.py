"""R514 · 队列道那三处 `build_queue_terminal` 现在把 dataset 账交进去。

来历：R504（并树 60a801）把 `app/api/v1/chat.py::build_queue_terminal` 改成收一枚
`dataset_files`，并在读数件 §9 判据①明写「三处调用方 `deploy/queue_worker.py:695 / :740 /
:897` 都还没把 `_collect_dataset_filenames` 的 sink 交进来」——本单治的就是那一格。

口径与 R504 同一条，一个字都不放宽：**只有正好一枚才给名字，零枚与多枚一律不传**（= 队列终态
载荷里整格缺席），绝不补造，也不拿请求方向那枚 `AskRequest.data_filename` 顶响应方向的读数。
取数只走 `chat` 在册的那一枚唯一收集器，本文件不新增第二份收集器、也不拼第二份名字。

全程离线：`FakeRedis` 加真 `StateGraph`，一发模型都不打、一个端口都不开、一行生产 redis 都不写。
"""

import ast
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import evidence as evidence_module
from app.agents import orchestrator
from app.agents.contracts import AgentResult
from app.agents.state import AgentState
from deploy import queue_worker
from tests.test_r254_queue_terminal_honesty import _pg_ledger, _queue_principal
from tests.test_r37_report_lane_worker import (
    BACKGROUND_ANSWER,
    _FakeStream,
    _SinkWorker,
    _install_worker,
    _payload,
    _request_id,
    _state,
)
from tests.test_r414_b_terminal_data_filename import (
    DATASET,
    OTHER_DATASET,
    dataset_agent_result,
)

WORKER_PY = Path("deploy/queue_worker.py")
NO_CELL = object()
USAGE_ROWS = [{"input_tokens": 120, "output_tokens": 40}]


def _terminal(ctx):
    """这一轮发布出去的队列终态载荷：客户端从 `/queue/status` 读的就是这一份。"""
    read = ctx.queue.terminal(_request_id(ctx))
    assert read["state"] == "ok", read
    return read["payload"]


def _cell(payload):
    """那一格在不在位——用哨兵分清「没有这一格」与「这一格是空串」。"""
    return payload.get("data_filename", NO_CELL)


def _bag(filenames, evidence):
    """`filenames` 就是这一轮真算过的数据文件；`evidence=False` 说这一轮压根没有证据袋。"""
    if not evidence:
        return {}
    return {"data": dataset_agent_result(*filenames)}


def _report_turn(monkeypatch, tmp_path, *, name, filenames=(), evidence=True, payload=None):
    """报告档跑完并交回正文的一轮（打的是正文腿那处调用点）。"""
    _pg_ledger(monkeypatch, USAGE_ROWS)
    return _install_worker(
        monkeypatch,
        tmp_path,
        name=name,
        payload=_payload(session_id="r514-" + name, principal=_queue_principal(), **(payload or {})),
        stream=_FakeStream([_state(BACKGROUND_ANSWER, _bag(filenames, evidence))]),
    )


class _DatasetWorker:
    """data 子图替身：名字只经工具边界唯一的写入口 `record_dataset` 落进证据袋。"""

    def __init__(self, *filenames):
        self.filenames = filenames

    def invoke(self, _state, config=None):
        bag = ((config or {}).get("configurable") or {}).get("evidence_bag")
        for name in self.filenames:
            evidence_module.record_dataset(
                bag, filename=name, dataset_id="ds-" + name, rows=12
            )
        return {"messages": [AIMessage(content=BACKGROUND_ANSWER)]}


def _parked_graph_after_data(sink, *filenames):
    """先真跑一枚 data 节点、再停在 export 之前：挂起的那一轮手里已经有一份数据账。"""
    builder = StateGraph(AgentState)
    builder.add_node("data", orchestrator._make_worker_wrapper(_DatasetWorker(*filenames), "data"))
    builder.add_node("export", orchestrator._make_worker_wrapper(_SinkWorker(sink), "export"))
    builder.add_edge(START, "data")
    builder.add_edge("data", "export")
    builder.add_edge("export", END)
    return builder.compile(checkpointer=MemorySaver(), interrupt_before=["export"])


def _parked_turn(monkeypatch, tmp_path, *, name, filenames=(DATASET,)):
    """报告档在队列里挂起的一轮（打的是挂起腿那处调用点），挂起之前 data 已经算过文件。"""
    _pg_ledger(monkeypatch, USAGE_ROWS)
    sink = tmp_path / (name + "-artifact-must-not-exist")
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name=name,
        payload=_payload(session_id="r514-" + name, principal=_queue_principal()),
        graph=_parked_graph_after_data(sink, *filenames),
    )
    ctx.sink = sink
    return ctx


def _legacy_turn(monkeypatch, tmp_path, *, name, filenames=()):
    """没声明档位的老腿（打的是第三处调用点）：走无 interrupt 的 queue_graph。"""
    _pg_ledger(monkeypatch, USAGE_ROWS)
    record = AgentResult.model_validate(dataset_agent_result(*filenames))
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name=name,
        payload=_payload(
            session_id="r514-" + name,
            principal=_queue_principal(),
            lane="",
            write_back_session=False,
        ),
    )
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda *args, **kwargs: record,
    )
    return ctx


# ==================== 判据②形一：真跑出数据的那一腿，队列终态必须点名 ====================


def test_the_answered_report_lane_names_the_one_file_it_computed_from(monkeypatch, tmp_path):
    """正文腿：一轮一份 ⇒ 队列终态带名字。"""
    ctx = _report_turn(monkeypatch, tmp_path, name="answered-one", filenames=(DATASET,))

    assert ctx.worker.process_one() is True

    assert _cell(_terminal(ctx)) == DATASET, _terminal(ctx)


def test_the_parked_report_lane_names_the_file_it_read_before_parking(monkeypatch, tmp_path):
    """挂起腿：挂着的一轮没有正文，但它确实算过那份文件——这两件事不许混成一格。

    R254 判据①那句「挂起这一轮没有正文」管的是 `result` 与 `sources`，不是这一格。
    """
    ctx = _parked_turn(monkeypatch, tmp_path, name="parked-one")

    assert ctx.worker.process_one() is True

    assert ctx.sink.exists() is False, "挂起没保住就等于自动批准"
    payload = _terminal(ctx)
    assert payload["terminal_state"] == "awaiting_approval", payload
    assert payload["answer_present"] is False, payload
    assert payload["sources"] == [], payload
    assert _cell(payload) == DATASET, payload


@pytest.mark.parametrize(
    ("slug", "filenames"),
    [("parked-zero", ()), ("parked-two", (DATASET, OTHER_DATASET))],
)
def test_a_parked_round_that_cannot_single_out_one_file_omits_the_cell(
    monkeypatch, tmp_path, slug, filenames
):
    """挂起腿同样只许「正好一枚才点名」：挂起不是补造那一个名字的口子。"""
    ctx = _parked_turn(monkeypatch, tmp_path, name=slug, filenames=filenames)

    assert ctx.worker.process_one() is True

    payload = _terminal(ctx)
    assert payload["terminal_state"] == "awaiting_approval", payload
    assert _cell(payload) is NO_CELL, "挂着的一轮凭空多了一格读数：" + repr(
        payload.get("data_filename")
    )


def test_the_legacy_lane_names_the_one_file_it_computed_from(monkeypatch, tmp_path):
    """老腿：canonical 记录里的 dataset 证据也要说得出用的哪份文件。"""
    ctx = _legacy_turn(monkeypatch, tmp_path, name="legacy-one", filenames=(DATASET,))

    assert ctx.worker.process_one() is True

    payload = _terminal(ctx)
    assert payload["terminal_state"] == "answered", payload
    assert _cell(payload) == DATASET, payload


# ==================== 判据②形二与形三：零枚、多枚一律整格缺席 ====================


@pytest.mark.parametrize(
    ("slug", "filenames"),
    [("report-zero", ()), ("report-two", (DATASET, OTHER_DATASET))],
)
def test_a_report_round_that_cannot_single_out_one_file_omits_the_cell(
    monkeypatch, tmp_path, slug, filenames
):
    """零枚（没跑数据）与多枚（说不清是哪一份）都不许被一枚标量冒充：整格不发。"""
    ctx = _report_turn(
        monkeypatch, tmp_path, name=slug, filenames=filenames, evidence=bool(filenames)
    )

    assert ctx.worker.process_one() is True

    payload = _terminal(ctx)
    assert _cell(payload) is NO_CELL, "说不清的一轮凭空多了一格读数：" + repr(
        payload.get("data_filename")
    )
    assert "data_filename" not in payload, sorted(payload)


def test_a_legacy_round_that_read_two_files_omits_the_cell(monkeypatch, tmp_path):
    ctx = _legacy_turn(monkeypatch, tmp_path, name="legacy-two", filenames=(DATASET, OTHER_DATASET))

    assert ctx.worker.process_one() is True

    assert _cell(_terminal(ctx)) is NO_CELL, _terminal(ctx)


def test_the_zero_file_leg_still_publishes_a_terminal_and_an_answer(monkeypatch, tmp_path):
    """缺席说的是那一格，不是整轮：这一腿照样要交得出答案与终态形状。"""
    ctx = _report_turn(monkeypatch, tmp_path, name="zero-shape", filenames=(), evidence=False)

    assert ctx.worker.process_one() is True

    payload = _terminal(ctx)
    assert payload["terminal_state"] == "answered"
    assert payload["answer_present"] is True
    assert ctx.queue.result(_request_id(ctx)) == BACKGROUND_ANSWER
    assert _cell(payload) is NO_CELL


# ==================== 判据②形四：绝不回显请求方向那枚声明值 ====================


def test_a_declared_filename_in_the_payload_never_becomes_the_terminal_cell(monkeypatch, tmp_path):
    """载荷写着 `data_filename` 而本轮压根没跑数据 ⇒ 那一格仍不许出现。

    `AskRequest.data_filename` 说的是「调用方点了哪份」，终态那一格说的是「服务端真算了哪份」，
    两枚同名不同义（契约 R414 节）。worker 今天也不该去读载荷里那一格。
    """
    ctx = _report_turn(
        monkeypatch,
        tmp_path,
        name="no-echo",
        filenames=(),
        evidence=False,
        payload={"data_filename": DATASET},
    )

    assert ctx.worker.process_one() is True

    assert _cell(_terminal(ctx)) is NO_CELL, "请求方向的声明值被抄成了响应方向的读数"
    assert 'payload.get("data_filename")' not in WORKER_PY.read_text(encoding="utf-8"), (
        "worker 开始从载荷里取声明值了：那正是回显的起点"
    )


# ==================== 判据①：三处调用点一枚都不许多拿、一枚都不许漏 ====================


def _terminal_calls():
    tree = ast.parse(WORKER_PY.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") == "build_queue_terminal"
    ]


def test_the_worker_builds_three_terminals_and_all_three_take_the_sink():
    """反证刀一的家：把任何一处 `dataset_files=` 摘掉，本枚当场红。"""
    calls = _terminal_calls()

    assert len(calls) == 3, "队列终态构造点仍是三处，一枚不多一枚不少：" + repr(
        [node.lineno for node in calls]
    )
    for node in calls:
        given = [kw.arg for kw in node.keywords]
        assert "dataset_files" in given, "第 " + str(node.lineno) + " 行又不传读数了：" + repr(given)


def test_the_worker_feeds_the_sink_only_from_the_registered_collector():
    """不新增第二份收集器、不在 worker 里拼名字：取证只许走 chat 那枚在册件。"""
    text = WORKER_PY.read_text(encoding="utf-8")

    assert text.count("chat._collect_dataset_filenames(") == 2, (
        "在册那枚收集器在 worker 里仍是两枚取数点（报告档一枚、老腿一枚）"
    )
    assert text.count("dataset_files=dataset_files,") == 3, (
        "三处调用点各递一枚读数，一处不多一处不少"
    )
    for forbidden in ("terminal_data_filename", "attach_terminal_data_filename"):
        assert forbidden not in text, forbidden + "：worker 里长出了第二处拼名字"
    assert "def _collect" not in text, "worker 里长出了第二份收集器"

