# -*- coding: utf-8 -*-
"""R548 —— 队列道报告腿补上 ``stream_piece_sink`` 的可注册点（判据①②③ 的凭据）。

背景：R524（并树 ``05bec06``）把 R31 的片段汇接进 ``/ask`` 与批准腿两条跑道，队列道那一格按实
交回 ``not_applicable``——那一道只发 ``queued`` + ``done`` 两枚帧、``text`` 恒 0、模型 0 次调用，
而真注册点 ``deploy/queue_worker.py::_drain_report_stream`` 落在它自己的写域外。本单补的就是
那一半：**worker 进程里真有一枚收端交给编排入口**，图内那枚唯一的盖章点
``nodes.publish_stream_pieces`` 能把逐字片段按到达顺序交到它手上。

🔴 本单**不做投递面**。入队那条 SSE 仍旧在两枚帧之后就结束，轮询面要不要长出增量读数、或新起
一条 tail SSE，都得先改 ``docs/api/contract-v1.md``（在途 R523/Kuhn 写域）。所以 R524 交工纸的
``queue_lane=not_applicable`` 那一格**一字不改**——把"注册上了"写成"接上了"正是 R545 那行明令
禁止的洗绿。"注册点已存在"与"投递面仍欠着"在同一棵树上同时可测：前者由本件钉，后者由
``tests/test_r524_queue_lane_sends_no_second_character.py``（本单按判据② 改口的那枚负向钉）钉。

全程离线：不打模型、不起服务、不动容器、不碰真 Redis（沿用 R37 的 FakeRedis 夹具）。真机那一格
按判据⑤ 原样交回「欠一次队列道真读数」，读点是 ``[QueueWorker][R548]`` 那一行日志。
"""

import ast
import logging
import re
from pathlib import Path

from app.agents import nodes, orchestrator
from deploy import queue_worker
from tests.test_r203_sse_progressive_frames import CHUNK_SIZE
from tests.test_r81_queue_terminal_retry import ENUM_CODES
from tests.test_r37_report_lane_worker import (
    MESSAGE,
    _install_worker,
    _request_id,
    _state,
)

import test_r524_queue_lane_sends_no_second_character as queue_lane

REPO = Path(__file__).resolve().parents[1]
WORKER_PATH = REPO / "deploy" / "queue_worker.py"

#: 报告档那一轮假想交回的正文（152 字）。逐 chunk 喂进去才像模型一个字一个字吐出来的样子；
#: 尺寸闸（20 字）、空档闸（100 ms）、地板（4 字）三把尺一格没动，枚数由它们自己算出来。
ANSWER = (
    "上季度华东区营业收入 1,240 万元，同比增长 8.6%，毛利率 34.2%，比上季度提高 1.1 个百分点。"
    "销售费用占收入 12.4%，环比基本持平；库存周转天数从 41 天降到 36 天，回款周期仍是 62 天。"
    "结论：增长主要来自主力产品的渠道下沉，费用与毛利同步改善，建议下季度优先复制这套打法。"
)
LEG = "export"
CALL_ID = "r548-call"
READOUT_PREFIX = "[QueueWorker][R548]"

#: ``record`` 里每轮必然不同的三格（时长与两枚本轮 id）；零外溢对判把它们摘掉再比，
#: 键集本身不摘——多一格少一格都当场红。
VOLATILE_RECORD_KEYS = ("duration_ms", "trace_id", "task_id", "request_id")

#: R524 那枚负向钉的夹具，本件按同名同形借过来（``lane = queue_lane.lane`` 是 pytest 认的再导出）。
lane = queue_lane.lane  # noqa: F841


# ==================== 读数工具：源文只从这一处进，摘刀才有唯一落点 ====================


def worker_source() -> str:
    """读 worker 源文的唯一入口。

    反证刀把这枚函数的读数换成内存影子（仓里一字节不动），所以每一枚读源文的钉都会跟着翻面——
    摘刀咬的是钉本身，不是钉旁边的注释。
    """
    return WORKER_PATH.read_text(encoding="utf-8")


def _callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def sink_handoffs(source: str | None = None) -> list:
    """AST 现取每一枚把 ``stream_piece_sink`` 交给**某次调用**的关键字（形参定义天然不算）。"""
    text = worker_source() if source is None else source
    out = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "stream_piece_sink":
                out.append({
                    "line": node.lineno,
                    "callee": _callee_name(node),
                    "value": getattr(keyword.value, "id", ""),
                })
    return out


def registration_points(source: str | None = None) -> list:
    """""注册点"的口径：把出口交给编排入口 ``run_with_stream`` 的那一枚关键字。

    只有这一枚关键字能决定 ``configurable`` 里长不长出键；``_process_report_lane_turn`` 那一枚
    是把账本往下递的搬运，它进不了 config，所以由另一枚钉单独钉死"恰一枚、且只能是它"。
    """
    return [p for p in sink_handoffs(source) if p["callee"] == "run_with_stream"]


def enclosing_function(line: int, source: str | None = None) -> str:
    """现取某一枚行号落在哪函数里（取最内层），不抄行号、也不信注释。"""
    text = worker_source() if source is None else source
    owners = [
        node for node in ast.walk(ast.parse(text))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= line <= node.end_lineno
    ]
    assert owners, f"第 {line} 行不在任何函数体内"
    owners.sort(key=lambda node: node.lineno)
    return owners[-1].name


def _merger_pieces(answer: str, chunk: int) -> list:
    """按在册口径把正文逐 chunk 喂进**真** merger，交回它自己切出来的片。"""
    merger = nodes.StreamPieceMerger()
    pieces: list = []
    for start in range(0, len(answer), chunk):
        pieces.extend(merger.feed(answer[start:start + chunk]))
    pieces.extend(merger.finish())
    return pieces


def _sink_config(ledger) -> dict:
    """造一枚与编排同形的 config：``configurable`` 里那枚键就是节点认的那一枚。"""
    return {"configurable": {nodes.STREAM_PIECE_SINK_KEY: ledger}}


def _publish(ledger, answer: str, chunk: int) -> list:
    """走**在册那唯一一枚盖章点**把片交出去（``call_id``/``worker`` 也由它盖）。"""
    pieces = _merger_pieces(answer, chunk)
    for piece in pieces:
        nodes.publish_stream_pieces(
            _sink_config(ledger), [piece], call_id=CALL_ID, worker=LEG
        )
    return pieces


def _install_graph_stream(monkeypatch, box: dict, *, answer: str = "", publish: bool = False):
    """把 ``_cancellable_stream`` 顶成"记 config、按真生产者的写法交片"那一层。

    🔴 只顶这一层：``run_with_stream``（把出口塞进 ``configurable`` 的那一手）与
    ``nodes.publish_stream_pieces``（盖章并调用出口的那一手）都是**在册原件**。本单要证的
    正是这两手在队列道上第一次接得起来，所以桩绝不允许自己再叫一次 sink。
    """

    def _stub(graph, payload, config, *, cancel_event=None):
        box["config"] = config
        box["sinks"] = box.get("sinks", []) + [
            (config.get("configurable") or {}).get(nodes.STREAM_PIECE_SINK_KEY)
        ]
        if publish:
            box["pieces"] = _publish(box["sinks"][-1], answer, CHUNK_SIZE)
        yield (("",), _state(answer))

    monkeypatch.setattr(orchestrator, "_cancellable_stream", _stub)
    return box


def _run_round(monkeypatch, tmp_path, *, name: str, publish: bool) -> dict:
    """真跑一轮报告档后台执行（``process_one``），把发布面读数与日志一并交回来。"""
    box: dict = {}
    ctx = _install_worker(monkeypatch, tmp_path, name=name)
    _install_graph_stream(monkeypatch, box, answer=ANSWER, publish=publish)
    records: list = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger("enterprise_brain")
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        finished = ctx.worker.process_one()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    ledger = box["sinks"][0]
    return {
        "ctx": ctx,
        "box": box,
        "ledger": ledger,
        "finished": finished,
        "request_id": _request_id(ctx),
        "status": ctx.queue.status(_request_id(ctx)),
        "result": ctx.queue.result(_request_id(ctx)),
        "terminal": ctx.queue.terminal(_request_id(ctx)),
        "records": list(ctx.recorded),
        "history": list(ctx.history),
        "log_lines": [record.getMessage() for record in records],
    }


def _real_round_identity(monkeypatch, tmp_path, *, name: str) -> tuple:
    """从真跑的那一轮里取回生产形状的 ``(principal, provenance)``——直调的钉子不自己编身份。"""
    box: dict = {}
    ctx = _install_worker(monkeypatch, tmp_path, name=name)
    _install_graph_stream(monkeypatch, box, answer=ANSWER, publish=False)
    assert ctx.worker.process_one() is True, "夹具没把这一轮跑完，后面的直调没有主语"
    configurable = box["config"]["configurable"]
    return ctx, configurable["principal"], configurable[queue_worker.PRINCIPAL_PROVENANCE_KEY]


def _readout_lines(lines) -> list:
    return [line for line in lines if line.startswith(READOUT_PREFIX)]


#: 每轮必变的 id 以裸值出现在日志行里（`request_id=<uuid4().hex>` 那一形）。零外溢对判先把它们
#: 归一再逐字比：文案与枚数一格都不许多，但"本轮是哪一枚请求"本来就不许当判据。
_VOLATILE_ID = re.compile(r"\b[0-9a-f]{32}\b")


def _normalized_log_lines(lines) -> list:
    """摘掉本单那枚读点前缀，再把每轮必变的 id 归一：剩下的两族必须逐字相等。"""
    return [
        _VOLATILE_ID.sub("<id>", line)
        for line in lines
        if not line.startswith(READOUT_PREFIX)
    ]


def _strip_volatile(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in VOLATILE_RECORD_KEYS}


# ==================== 判据①：注册点恰一枚，坐标现取 ====================


def test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call():
    """第二枚 ``run_with_stream`` 注册点一起就红：那是第二套口径，不是补格。"""
    points = registration_points()
    assert len(points) == 1, points
    only = points[0]
    assert only["value"] == "stream_piece_sink", only
    assert enclosing_function(only["line"]) == "_drain_report_stream", only


def test_the_drain_is_the_only_place_the_queue_lane_touches_the_graph():
    """R524 点名的真接点没换地方：``run_with_stream(`` 在该文件里仍旧只有一枚调用点。"""
    source = worker_source()
    call_sites = [n for n, line in enumerate(source.splitlines(), 1) if "run_with_stream(" in line]
    assert len(call_sites) == 1, call_sites
    assert enclosing_function(call_sites[0], source) == "_drain_report_stream", call_sites


def test_the_only_other_handoff_carries_the_round_ledger_down():
    """文件里另一枚同名关键字只能是账本往下递那一手；出现第三种就是有人又注册了一遍。"""
    handoffs = sink_handoffs()
    assert sorted(item["callee"] for item in handoffs) == [
        "_drain_report_stream", "run_with_stream",
    ], handoffs
    down = next(item for item in handoffs if item["callee"] == "_drain_report_stream")
    assert down["value"] == "piece_ledger", down
    assert enclosing_function(down["line"]) == "_process_report_lane_turn", down


# ==================== 判据①：交下去的收端真能收到片（不是"调用发生过"） ====================


def test_the_registered_sink_reaches_the_graph_configuration(monkeypatch, tmp_path):
    """真 ``run_with_stream`` 把 worker 交下去的账本塞进 ``configurable``，且只塞这一枚形状。"""
    box = _install_graph_stream(monkeypatch, {}, answer="", publish=False)
    ctx = _install_worker(monkeypatch, tmp_path, name="r548-config")
    assert ctx.worker.process_one() is True

    configurable = box["config"]["configurable"]
    ledger = configurable[nodes.STREAM_PIECE_SINK_KEY]
    assert isinstance(ledger, queue_worker.ReportLanePieceLedger), ledger
    assert ledger.request_id == _request_id(ctx), (ledger.request_id, _request_id(ctx))
    assert ledger is box["sinks"][0]


def test_the_pieces_the_producer_stamps_and_publishes_arrive_in_order(monkeypatch, tmp_path):
    """片一到收端就是"一串"，不是"一坨"：枚数、顺序、身份、时间戳四格同读。"""
    box = _install_graph_stream(monkeypatch, {}, answer=ANSWER, publish=True)
    ctx = _install_worker(monkeypatch, tmp_path, name="r548-sequence")
    assert ctx.worker.process_one() is True

    ledger = box["sinks"][0]
    pieces = box["pieces"]
    assert ledger.count > 1, ledger.count
    assert len(ledger.pieces) == ledger.count == len(pieces), (ledger.count, len(pieces))
    assert ledger.joined_text() == ANSWER
    assert ledger.chars == len(ANSWER)
    assert [piece.text for piece in ledger.pieces] == [piece.text for piece in pieces]
    assert all(isinstance(piece, nodes.StreamPiece) for piece in ledger.pieces)
    assert {piece.call_id for piece in ledger.pieces} == {CALL_ID}
    assert ledger.legs == (LEG,)
    for previous, following in zip(ledger.pieces, ledger.pieces[1:]):
        assert previous.end_at <= following.start_at, (previous, following)


def test_a_whole_dump_is_distinguishable_from_the_piece_run():
    """判据① 的字面要求：拼起来等值、分片数不等值——"一次投喂一整篇"必须长得不一样。"""
    piece_run = queue_worker.ReportLanePieceLedger("r548-piece-run")
    whole_dump = queue_worker.ReportLanePieceLedger("r548-whole-dump")

    merger = nodes.StreamPieceMerger()
    lump = merger.feed(ANSWER) + merger.finish()
    for piece in lump:
        nodes.publish_stream_pieces(_sink_config(whole_dump), [piece], call_id=CALL_ID, worker=LEG)
    _publish(piece_run, ANSWER, CHUNK_SIZE)

    assert whole_dump.count == 1, whole_dump.count
    assert piece_run.count > 1, piece_run.count
    assert whole_dump.joined_text() == piece_run.joined_text() == ANSWER
    assert len(piece_run.pieces) != len(whole_dump.pieces)


def test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key(monkeypatch, tmp_path):
    """零外溢第一格：没交收端（全部既有直调）时，本轮 config 的键集一格不加。"""
    _ctx, principal, provenance = _real_round_identity(monkeypatch, tmp_path, name="r548-baseline")

    plain = _install_graph_stream(monkeypatch, {}, answer=ANSWER, publish=False)
    final_answer, agent_results, stream_error = queue_worker._drain_report_stream(
        MESSAGE,
        thread_id="r548-direct",
        principal=principal,
        provenance=provenance,
        request_id="req-r548-direct",
        trace_id="trace-r548-direct",
        task_id="task-r548-direct",
    )
    assert nodes.STREAM_PIECE_SINK_KEY not in plain["config"]["configurable"]
    assert (final_answer, agent_results, stream_error) == (ANSWER, {}, "")


def test_the_drain_still_returns_exactly_the_same_three_values(monkeypatch, tmp_path):
    """返回值 arity 与语义一格没动：加第四枚就是改终态那一层的接口，本单不许。"""
    _ctx, principal, provenance = _real_round_identity(monkeypatch, tmp_path, name="r548-arity")
    box = _install_graph_stream(monkeypatch, {}, answer=ANSWER, publish=True)
    ledger = queue_worker.ReportLanePieceLedger("r548-arity")
    results = queue_worker._drain_report_stream(
        MESSAGE,
        thread_id="r548-arity",
        principal=principal,
        provenance=provenance,
        request_id="req-r548-arity",
        trace_id="trace-r548-arity",
        task_id="task-r548-arity",
        stream_piece_sink=ledger,
    )
    assert len(results) == 3, results
    assert results[0] == ANSWER
    assert results[1] == {} and results[2] == ""
    assert ledger.count > 1 and ledger.joined_text() == ANSWER
    assert box["config"]["configurable"][nodes.STREAM_PIECE_SINK_KEY] is ledger


# ==================== 判据③：零行为外溢（读数一字节不动，日志只多该多的那一行） ====================


def test_a_quiet_round_adds_not_a_single_readout_line(monkeypatch, tmp_path):
    """provider 一枚字都没流 ⇒ 一行都不留：既有日志面因此逐字不变。"""
    round_ = _run_round(monkeypatch, tmp_path, name="r548-quiet", publish=False)
    assert round_["finished"] is True
    assert round_["ledger"].count == 0
    assert _readout_lines(round_["log_lines"]) == []


def test_a_round_that_flowed_pieces_leaves_exactly_one_readout_line(monkeypatch, tmp_path):
    """真流到字 ⇒ 恰一行读数，三个计数都在这行里（这一行就是交回真机窗的读点）。"""
    round_ = _run_round(monkeypatch, tmp_path, name="r548-readout", publish=True)
    lines = _readout_lines(round_["log_lines"])
    assert len(lines) == 1, lines
    only = lines[0]
    assert f"request_id={round_['request_id']}" in only, only
    assert f"{round_['ledger'].count} 枚" in only, only
    assert f"{round_['ledger'].chars} 字" in only, only
    assert LEG in only, only
    assert "超上限丢弃" not in only, only


def test_the_published_readings_do_not_move_when_pieces_flow(monkeypatch, tmp_path):
    """判据③ 的主格：片流没流，终态帧 / 答案 / 记录键集 / 会话历史 / 日志面逐字相等。

    🔴 日志面这格的口径：先跑一枚**丢弃轮**把进程内一次性告警榨干（`[ASK] 来源事件缺少可用检索
    范围` 之类只在本进程头一轮吐），再把两族各自的 `request_id` 等裸值归一——剩下的是文案与枚数，
    一格都不许多。凭据与第一手红因见 ``docs/testing/r548-queue-lane-piece-sink-registration.md`` §9。
    """
    _run_round(monkeypatch, tmp_path, name="r548-spill-warmup", publish=True)
    quiet = _run_round(monkeypatch, tmp_path, name="r548-spill-quiet", publish=False)
    flowed = _run_round(monkeypatch, tmp_path, name="r548-spill-flowed", publish=True)

    assert flowed["ledger"].count > 1 and quiet["ledger"].count == 0
    assert flowed["status"] == quiet["status"] == "done"
    assert flowed["result"] == quiet["result"] == ANSWER
    assert flowed["terminal"] == quiet["terminal"], (flowed["terminal"], quiet["terminal"])
    assert [sorted(rec.keys()) for rec in flowed["records"]] == [
        sorted(rec.keys()) for rec in quiet["records"]
    ]
    assert len(flowed["records"]) == len(quiet["records"]) == 1
    assert _strip_volatile(flowed["records"][0]) == _strip_volatile(quiet["records"][0])
    assert flowed["history"] == quiet["history"]
    quiet_lines = _normalized_log_lines(quiet["log_lines"])
    flowed_lines = _normalized_log_lines(flowed["log_lines"])
    assert len(quiet_lines) == len(flowed_lines), (len(quiet_lines), len(flowed_lines))
    assert quiet_lines == flowed_lines, (quiet_lines, flowed_lines)


def test_the_ledger_counts_pieces_it_cannot_keep():
    """截断要如实报数：静默吞片等于把"收端收到了什么"重新变成看不见的东西。"""
    ledger = queue_worker.ReportLanePieceLedger("r548-overflow", limit=2)
    pieces = _merger_pieces(ANSWER, CHUNK_SIZE)
    assert len(pieces) > 2, len(pieces)
    for piece in pieces:
        nodes.publish_stream_pieces(_sink_config(ledger), [piece], call_id=CALL_ID, worker=LEG)

    assert len(ledger.pieces) == 2
    assert ledger.overflow == len(pieces) - 2
    assert ledger.count == len(pieces)
    assert ledger.chars == len(ANSWER)
    assert ledger.joined_text() == "".join(piece.text for piece in pieces[:2])


def test_the_ledger_limit_is_the_same_number_on_disk_and_in_memory():
    """上限是纸上一枚写得出来的数：源文字面与运行时读数漂开就红（不靠记忆读它）。"""
    match = re.search(r"^QUEUE_PIECE_LEDGER_LIMIT = (\d+)$", worker_source(), re.M)
    assert match, "源文里找不到那枚字面上限"
    assert int(match.group(1)) == queue_worker.QUEUE_PIECE_LEDGER_LIMIT
    assert queue_worker.ReportLanePieceLedger("x").limit == queue_worker.QUEUE_PIECE_LEDGER_LIMIT


def test_the_worker_still_hands_over_no_new_stable_code():
    """R81 那把尺原样量过来：本单往 worker 里加的只有中文读数，一枚稳定码都没多。

    词表不复制——``ENUM_CODES`` 直接从在册件 ``tests/test_r81_queue_terminal_retry.py`` 借，
    表达式与它 ``:355`` 那行逐字同形；红的是同一格，不是本单自造的第二套判据。
    """
    codes_in_worker = set(re.findall(r'"([a-z][a-z_]+)"', worker_source())) & ENUM_CODES
    assert codes_in_worker == {"internal_error"}, codes_in_worker
    assert '"authorization_required"' in worker_source()


# ==================== 判据②：不许把"注册上了"写成"接上了" ====================


def test_a_dead_registration_alone_does_not_read_as_connected_on_the_enqueue_lane(lane):
    """两向都钉：注册点必须已存在（退回就红），但投递面没裁 ⇒ 纸上那一格仍旧 ``not_applicable``。

    这一枚是本单与 R545 那行「不许把这格洗绿」共同的牙：盘面既有注册点、客户端又收不到字，
    判定词就必须停在 ``not_applicable``；谁把 R524 交工纸改成 ``connected``，在册对判钉当场红。
    """
    facts = queue_lane.queue_lane_facts(lane)
    assert facts["text_frames"] == 0 and facts["model_calls"] == 0, facts
    assert [hit for hit in facts["sink_points"] if hit.startswith("deploy/")], facts["sink_points"]
    assert not [hit for hit in facts["sink_points"] if hit.startswith("app/")], facts["sink_points"]
    assert queue_lane.verdict_for(facts) == "not_applicable", facts
    assert queue_lane.paper_verdict() == "not_applicable"


def test_the_report_lane_still_never_runs_the_graph_on_the_enqueue_side(lane):
    """入队那一段一格没动：两枚帧、零枚在场执行——队列道"接上"的仍是 worker 进程里那一手。"""
    assert lane.queue.calls == []
    facts = queue_lane.queue_lane_facts(lane)
    assert facts["graph_runs"] == 0, facts
    assert facts["event_names"] == ["queued", "done"], facts
    assert facts["done_payload"].get("terminal_state") == queue_lane.chat.TERMINAL_STATE_QUEUED
