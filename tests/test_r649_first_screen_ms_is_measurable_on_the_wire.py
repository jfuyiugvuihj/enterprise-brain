# -*- coding: utf-8 -*-
r"""R649 · 把「首屏 X ms」从"只有口径"做成"线上量得到"：可见 text 帧落进 trace 账，读数由账派生。

判据逐条对应（派工词 R649 第二节）：
  ① 记录点＝**屏上看得见的第一枚 text 帧**，账＝已在册那本（``app/trace/store.py::TraceStore.record_event``），
     读数＝由那两枚已在册的戳派生（``app/api/v1/observability.py::wire_first_text_from_events``）——
     正控见 ``test_the_positive_control_...`` 与 ``test_a_streamed_round_...``；
  ② blocker 的账：``wire_first_text_not_recorded`` 已摘，``lane_attribution_absent`` 与
     ``first_token_not_a_stage_sample`` 如实留着（``test_the_blocker_book_...``）；
  ③ 不承诺、不填数、不翻绿（``test_the_slot_still_...``、``test_no_promise_survives_...``）；
  ④ 在册那两枚件一字不动：本件不碰 ``per_stream`` 与 ``prefix_breaks``，只钉「线上多出的键只有
     ``first_text`` 一枚」与「wire 帧一枚都没多」（``test_the_wire_shape_gained_no_frame``）；
  ⑤ 三把反证刀在 ``tests/test_r649_counter_evidence_teeth.py``，与本件共用同一枚读尺；
  ⑥ 线上形状新增的键（``first_text`` 那一格）逐枚点名在 ``test_the_readback_key_roster_is_exact``，
     契约文末追加的逐字文本交回总控，本件不写契约。

纪律：不打模型（真腿只跑在 ``httpx.MockTransport`` 上，与 ``tests/test_r203_sse_progressive_frames.py``
同一形状）、不起服务、不连库、不动容器。假的只有 orchestrator 那一层——夹具照借
``tests/test_sse_sources.py`` 与 ``tests/test_r48_headline_card_lands_on_the_wire.py``，不造第二份。
"""
import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.api.v1 import chat, observability
from app.common.stage_timing import (
    REQUEST_TERMINAL_EVENTS,
    request_windows_from_events,
    to_epoch_ms,
)
from app.trace.store import default_trace_store, reset_default_trace_store

from tests.test_r48_headline_card_lands_on_the_wire import (  # noqa: F401  -- 同批夹具，不造第二份
    cards,
    names,
    wire,
)
from tests.test_r48_headline_never_enters_the_text_ledger import _streamed_round  # noqa: F401
from tests.test_sse_sources import (  # noqa: F401
    doc_state,
    drive,
    fake_retriever_hits,
    finance_principal,
)

EVENT_TYPE = observability.WIRE_FIRST_TEXT_EVENT_TYPE
OPEN_EVENT = observability.WIRE_FIRST_TEXT_OPEN_EVENT
#: 起点与终点两枚戳：线上由 ``app/agents/orchestrator.py::run_with_stream`` 经 ``_record_trace``
#: 落进同一本账；本件假的就是那一层，所以按名册补戳。名册 import 不重抄。
MIRROR_EVENTS = (OPEN_EVENT,) + tuple(sorted(REQUEST_TERMINAL_EVENTS))
#: 只有真发了屏的那三条腿才配记账（与 ``app/api/v1/chat.py`` 三处 ``note`` 调用同源）。
VISIBLE_LEGS = ("approved", "piece", "terminal")
#: 读回那一格的键名册：文末追加要写的就是这一串，多一枚少一枚都算形状变了。
READBACK_KEYS = (
    "event_type",
    "first_text_at",
    "first_text_ms",
    "first_text_sequence",
    "leg",
    "measured_from",
    "reason",
    "request_started_at",
    "status",
    "trace_id",
    "visible_chars",
)
#: canonical 信封那七枚键（R501 钉的就是这一串，本单一个字不动）。
ENVELOPE_KEYS = {"request_id", "trace_id", "task_id", "sequence", "timestamp", "status", "data"}
#: text 帧的载荷闭集（R154/R149 那两件的口径，本单不新开侧门）。
TEXT_PAYLOAD_KEYS = {"type", "content", "cached", "cache_generated_at", "cache_note"}


def _is_frame_yield(statement) -> bool:
    """下一格必须是 ``yield text_sse_frame(...)``：异步生成器里这一行是 ``Expr(value=Yield(...))``。"""
    value = getattr(statement, "value", None)
    return isinstance(value, ast.Yield) and "text_sse_frame" in ast.unparse(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==================== 夹具：账本落点 + 起点/终点补戳 ====================


@pytest.fixture()
def trace_book(tmp_path, monkeypatch):
    """把 trace 那本账改道到 tmp：盘面 ``data/traces/`` 一字节都不许多出来。"""
    monkeypatch.setenv("TRACE_STORE_PATH", str(tmp_path / "events.jsonl"))
    reset_default_trace_store()
    store = default_trace_store()
    yield store
    reset_default_trace_store()


@pytest.fixture()
def mirrored_lifecycle(monkeypatch):
    r"""补上 orchestrator 在这一轮本来就会记的那两枚戳：起点与终点。

    🔴 这不是把首屏"算出来"的手续：``wire.first_text`` 那一枚必须由 ``app/api/v1/chat.py``
    真发帧时落下，本件一枚都不替它落。这里补的只有 ``request.started`` 与终态两枚，且时刻
    一律由**同一枚既有出口**（``app/trace/store.py::TraceStore.record_event``）现盖，纸上与
    码里都不许手填任何一枚时刻。
    """
    real = chat.canonical_sse_event
    mirrored: list[str] = []

    def wrapped(event_name, **kwargs):
        frame = real(event_name, **kwargs)
        if event_name in MIRROR_EVENTS:
            data = kwargs.get("data") or {}
            payload = {"session_id": str(data.get("session_id") or "")}
            default_trace_store().record_event(
                trace_id=kwargs["trace_id"],
                request_id=kwargs["request_id"],
                task_id=kwargs["task_id"],
                event_type=event_name,
                status=kwargs["status"],
                payload=payload,
            )
            mirrored.append(event_name)
        return frame

    monkeypatch.setattr(chat, "canonical_sse_event", wrapped)
    return mirrored


# ==================== 现读取数：走产品自己的回放口，不自己攒事件 ====================


def trace_id_of(body: str) -> str:
    found = {payload["trace_id"] for _name, payload in wire(body) if "trace_id" in payload}
    assert found, "这一轮一枚 canonical 信封都没有，trace_id 无从谈起"
    assert len(found) == 1, found
    return found.pop()


def text_frames(body: str) -> list[str]:
    return [str(payload.get("content") or "") for name, payload in wire(body) if name == "text"]


def readback(store, body: str) -> dict:
    trace_id = trace_id_of(body)
    return observability.wire_first_text_row(store.replay(trace_id), trace_id)



def visible_frame_problems(store, body: str) -> list[str]:
    r"""把「首屏那一枚＝屏上第一枚正文帧」拆成一串可点名的读数：空清单才算对上了。

    绿色用例与 ``tests/test_r649_counter_evidence_teeth.py`` 里那三把刀共用这一枚函数
    （``tests/test_r48_headline_never_enters_the_text_ledger.py`` 同一条路子）：刀下去红的必须
    是**读数本身**，不是另一枚守卫——否则「反证跑了却没红」就换成了「反证红在无关的地方」。
    """
    block = readback(store, body)
    if block["status"] != "measured":
        return ["读回的是 %s（不是 measured）：%s" % (
            block["status"], block["reason"])]
    frames = text_frames(body)
    problems: list[str] = []
    if block["leg"] not in VISIBLE_LEGS:
        problems.append("记账的腿不是发了屏那一族：%r（允许 %s）" % (
            block["leg"], list(VISIBLE_LEGS)))
    if not frames:
        problems.append("这一轮屏上一枚正文帧都没有，首屏无从谈起")
    elif block["visible_chars"] != len(frames[0]):
        problems.append(
            "记的不是屏上第一枚正文帧：账上 visible_chars=%r，屏上第一枚 %r 字"
            % (block["visible_chars"], len(frames[0])))
    if block["first_text_ms"] is None:
        problems.append("没有读数")
    return problems


# ==================== 正控：真发一帧，当场读得到非 None，且对得上发送时刻 ====================


def test_the_positive_control_reads_a_non_none_first_screen_off_a_real_frame(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    """判据① 的正身：驱动一轮真发帧，数由账上那两枚戳派生，且排在帧交出去那一刻之前。"""
    emit_after: list[str] = []
    real_frame = chat.text_sse_frame

    def stamped_frame(content, cache_fields=None):
        frame = real_frame(content, cache_fields)
        emit_after.append(_now())
        return frame

    monkeypatch.setattr(chat, "text_sse_frame", stamped_frame)

    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    frames = text_frames(body)
    assert frames, "这一轮一枚正文帧都没发，正控就是空的"
    assert OPEN_EVENT in mirrored_lifecycle, mirrored_lifecycle

    assert visible_frame_problems(trace_book, body) == [], visible_frame_problems(trace_book, body)
    block = readback(trace_book, body)
    assert block["status"] == "measured", block
    assert block["measured_from"] == observability.SLO_SOURCE_TRACE
    assert block["first_text_ms"] is not None and block["first_text_ms"] >= 0.0
    # 记的是**这一枚帧**：字符数与屏上第一枚正文逐位相同。
    assert block["visible_chars"] == len(frames[0]), (block["visible_chars"], len(frames[0]))
    assert block["leg"] in VISIBLE_LEGS, block
    # 「对得上发送时刻」：戳由账盖，盖在帧交出去之前、本轮起点之后。
    started = to_epoch_ms(block["request_started_at"])
    stamped = to_epoch_ms(block["first_text_at"])
    assert started <= stamped <= to_epoch_ms(emit_after[0]), (started, stamped, emit_after[:1])
    # 数与戳同源：读数就是这两枚戳之差，不是别处搬来的。
    assert block["first_text_ms"] == pytest.approx(stamped - started, abs=1e-6), block
    # 首屏排在端到端之内：同一本账的另一枚差值兜着它，两形不可能各说一套。
    windows = request_windows_from_events(trace_book.replay(trace_id_of(body)))
    assert windows, "终态戳没落进账，端到端无从对判"
    assert block["first_text_ms"] <= windows[trace_id_of(body)]
    print("[R649 凭据] 真发帧一轮的首屏读回=%r 端到端=%r" % (
        block, windows[trace_id_of(body)]))


def test_a_streamed_round_stamps_the_first_frame_only_and_reads_the_piece_leg(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    """逐片轮：一帧都不许多记账；首屏只认**最早**那一枚，不是末帧。"""
    body = _streamed_round(monkeypatch, tmp_path)
    frames = text_frames(body)
    assert len(frames) >= 2 and len(frames[0]) < len(frames[-1]), "这一轮没逐片，本例前提变了"

    events = trace_book.replay(trace_id_of(body))
    rows = [event for event in events if event.get("event_type") == EVENT_TYPE]
    assert len(rows) == 1, [event.get("event_type") for event in events]

    assert visible_frame_problems(trace_book, body) == [], visible_frame_problems(trace_book, body)
    block = readback(trace_book, body)
    assert block["leg"] == "piece", block
    assert to_epoch_ms(block["first_text_at"]) == to_epoch_ms(rows[0]["timestamp"])
    opened = [event["sequence"] for event in events if event.get("event_type") == OPEN_EVENT]
    assert opened and rows[0]["sequence"] > min(opened), (
        "首屏没排在起点之后：窗口没开就先落账，这一枚不能算数")


def test_the_card_is_not_the_first_screen_and_the_two_records_stay_apart(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    """R48 的线索卡与 R649 的首屏是两件事：卡片发了不等于屏上有了正文。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    assert cards(body), "这一轮没发卡，对照无从谈起"
    block = readback(trace_book, body)
    assert block["leg"] == "terminal", block
    assert block["visible_chars"] == len(text_frames(body)[0])
    #: 两本数不能混：trace 那本账的 ``sequence`` 与 SSE 信封的 ``sequence`` 是两枚戳，
    #: 这里只比同一枚墙上的两件事——卡片先上屏、首屏那一枚戳必须排在它之后。
    card = cards(body)[0]
    assert to_epoch_ms(block["first_text_at"]) >= to_epoch_ms(card["timestamp"]), (
        block["first_text_at"], card["timestamp"])
    events = trace_book.replay(trace_id_of(body))
    assert [event for event in events if event.get("event_type") == EVENT_TYPE], events
    assert visible_frame_problems(trace_book, body) == [], visible_frame_problems(trace_book, body)


# ==================== 三态读回：数、没帧、有帧没窗 ====================


def test_the_readback_distinguishes_no_frame_from_no_window(trace_book):
    """``None`` 有两张脸：这一轮没发正文，与发了正文但这本账没开过窗（缓存腿那一形）。"""
    default_trace_store().record_event(
        trace_id="trace-r649-quiet", request_id="req-r649-quiet", event_type=OPEN_EVENT,
        status="started", payload={"owner_id": "r649"},
    )
    block = observability.wire_first_text_readout("trace-r649-quiet")
    assert block["status"] == observability.WIRE_FIRST_TEXT_NO_EVENT, block
    assert block["first_text_ms"] is None and block["visible_chars"] is None

    default_trace_store().record_event(
        trace_id="trace-r649-orphan", request_id="req-r649-orphan", event_type=EVENT_TYPE,
        status="running", payload={"owner_id": "r649", "leg": "terminal", "visible_chars": 12},
    )
    block = observability.wire_first_text_readout("trace-r649-orphan")
    assert block["status"] == observability.WIRE_FIRST_TEXT_NO_WINDOW, block
    assert block["first_text_ms"] is None, "窗口都没开还敢交时长"
    assert block["leg"] == "terminal" and block["visible_chars"] == 12


def test_the_readback_never_folds_absence_into_zero_or_borrows_a_number():
    """一枚事件都没有的空账：``None`` 加具名原因。``0`` 与借来的数都算本仓记过一整族的空绿。"""
    block = observability.wire_first_text_row([], "trace-none")
    assert block["first_text_ms"] is None
    assert block["status"] == observability.WIRE_FIRST_TEXT_NO_EVENT
    assert block["reason"], "空绿那一族：没有 blocker 也没有读数，还一句原因都不写"
    assert observability.wire_first_text_from_events([]) == {}


# ==================== 闸门本体：一轮一枚、空正文不吃闸门 ====================


def test_the_gate_records_once_per_round_and_empty_text_does_not_burn_it(monkeypatch):
    """``app/api/v1/chat.py::_FirstVisibleTextMark`` 的两条规矩，逐枚现读。"""
    seen: list[dict] = []
    monkeypatch.setattr(chat, "_record_wire_first_text", lambda **kwargs: seen.append(kwargs))
    mark = chat._FirstVisibleTextMark(
        request_id="r", trace_id="t", task_id="k", session_id="s", owner_id="o"
    )
    mark.note("", leg="piece")
    assert seen == [], "空正文被记成了首屏"
    assert not mark.recorded, "空正文吃掉了闸门"
    mark.note("   ", leg="piece")
    assert seen == [] and not mark.recorded
    mark.note("财务部差旅上限 2000 元。", leg="piece")
    mark.note("财务部差旅上限 2000 元。还有第二帧。", leg="terminal")
    assert len(seen) == 1, seen
    assert seen[0]["visible_chars"] == len("财务部差旅上限 2000 元。")
    assert seen[0]["leg"] == "piece" and seen[0]["trace_id"] == "t" and seen[0]["owner_id"] == "o"


# ==================== blocker 与回执：摘了哪一枚、还挡着哪两枚 ====================


def _first_text_metric():
    return next(
        item
        for tier in observability.slo_tiers()
        for item in tier.metrics
        if item.name == "first_text_p95_ms"
    )


def test_the_blocker_book_drops_only_the_cell_this_ticket_closed() -> None:
    assert "wire_first_text_not_recorded" not in observability.SLO_BLOCKERS
    metric = _first_text_metric()
    assert metric.blockers == (
        "lane_attribution_absent",
        "first_token_not_a_stage_sample",
    ), metric.blockers
    for code in metric.blockers:
        assert observability.SLO_BLOCKERS[code], code


def test_the_slot_still_answers_not_measurable_and_keeps_policy_target() -> None:
    """判据③：这一格仍不可测、没有实测百分位，但保留 policy A 的目标上限。"""
    report = observability.slo_readout()
    tier = next(row for row in report["tiers"] if row["lane"] == "qa")
    block = tier["numbers"]["first_text_p95_ms"]
    assert block["status"] == observability.SLO_NOT_MEASURABLE, block
    assert block["p50_ms"] is None and block["p95_ms"] is None
    assert block["target"] == observability.SLO_TARGET_QA_FIRST_TEXT_MS
    assert block["target_status"] == observability.SLO_TARGET_SET
    codes = [item["code"] for item in block["blockers"]]
    assert codes == list(metric_blocker_codes()), codes
    assert "wire_first_text_not_recorded" not in json.dumps(report, ensure_ascii=False)


def metric_blocker_codes() -> list[str]:
    """回执那一格的 blocker 名单必须与契约对象那一格逐位同源，不是第二本账。"""
    return list(_first_text_metric().blockers)


def test_no_measured_promise_survives_anywhere_on_the_new_surface() -> None:
    """目标是内部 policy；未经目标机器实测，不能把它写成外部实测承诺。"""
    probe = json.dumps(
        {
            "constants": [
                observability.WIRE_FIRST_TEXT_EVENT_TYPE,
                observability.WIRE_FIRST_TEXT_OPEN_EVENT,
                observability.WIRE_FIRST_TEXT_REASONS,
            ],
            "readout": observability.wire_first_text_readout.__doc__,
            "fold": observability.wire_first_text_from_events.__doc__,
            "row": observability.wire_first_text_row.__doc__,
        },
        ensure_ascii=False,
    )
    for needle in ("≤", "<=", "1 s", "p95 = ", "target"):
        assert needle not in probe, needle


# ==================== 形状：wire 一枚帧都不许多；读回键名册逐枚点名 ====================


def test_the_wire_shape_gained_no_frame(trace_book, mirrored_lifecycle, monkeypatch, tmp_path):
    """判据④：本单只多一本账里的一行，客户端看到的帧名与载荷一枚没变。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    assert EVENT_TYPE not in names(body), names(body)
    frames = [payload for name, payload in wire(body) if name == "text"]
    assert frames, "这一轮一枚正文帧都没有"
    for payload in frames:
        assert set(payload) <= TEXT_PAYLOAD_KEYS, payload
    envelopes = [payload for _name, payload in wire(body) if "trace_id" in payload]
    assert envelopes and set(envelopes[0]) == ENVELOPE_KEYS, envelopes[:1]


def test_the_readback_key_roster_is_exact(trace_book):
    """文末追加要落的那串键名：多一枚少一枚都算形状变了，逐枚点名。"""
    block = observability.wire_first_text_readout("trace-r649-absent")
    assert tuple(sorted(block)) == READBACK_KEYS, sorted(block)


def test_the_stage_latency_trace_report_gained_exactly_one_key(trace_book, tmp_path):
    """在册那枚按 trace 折叠的报告只多 ``first_text`` 一格，别的一律不许动。"""
    trace_id = "trace-r649-shape"
    default_trace_store().record_event(
        trace_id=trace_id, request_id="req-r649-shape", event_type=EVENT_TYPE,
        status="running", payload={"owner_id": "r649", "leg": "piece", "visible_chars": 7},
    )
    report = observability._stage_report_from_trace(trace_id)
    assert "first_text" in report, sorted(report)
    assert report["first_text"]["status"] == observability.WIRE_FIRST_TEXT_NO_WINDOW
    assert report["first_text"]["first_text_ms"] is None


# ==================== 派生只读不写：不许另开一本账 ====================


def _called_names(tree, function: str) -> set[str]:
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function
    )
    found: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name):
            found.add(call.func.id)
        elif isinstance(call.func, ast.Attribute):
            found.add(call.func.attr)
    return found


def test_the_reader_holds_the_book_open_only_for_reading() -> None:
    """派生只读不写：读侧任何一枚函数都不许往账里落东西，也不许另开一本。"""
    tree = ast.parse(Path(observability.__file__).read_text(encoding="utf-8"))
    forbidden = {
        "record_event", "add_request_window", "add", "open", "upsert", "write_text", "dump",
        "cache_answer",
    }
    for name in ("wire_first_text_from_events", "wire_first_text_row"):
        called = _called_names(tree, name)
        assert not (called & forbidden), (name, sorted(called & forbidden))


# ==================== 记账点必须站在"发了屏"那一侧（结构面）====================


def frame_yield_record_points(source: str) -> tuple[list[tuple[int, str]], list[str]]:
    r"""扫一份 chat 源文，交回（每一枚记账点的 (行号, 腿名)，没站在发帧前一格的问题清单）。

    🔴 判据⑤ 那把刀要读的是**变异版源文**，所以这一手必须是普通函数而不是用例：绿色用例与
    ``tests/test_r649_counter_evidence_teeth.py`` 共用**同一枚**尺子，刀那边不许另抄一套 AST 走法
    （本仓铁规：不为同一事实开平行实现）。口径只有一句——``first_text_mark.note(...)`` 的下一格
    必须是 ``yield text_sse_frame(...)``。记账点搬到 token 那一侧（折帧闸之前、
    ``app/api/v1/chat.py::_AnswerPieceStream.frame_for`` 交回 ``None`` 也照样记）时，
    问题清单必须非空并且点名那一枚。
    """
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []
    problems: list[str] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            statements = getattr(node, field, None)
            if not isinstance(statements, list):
                continue
            for index, statement in enumerate(statements):
                if not (isinstance(statement, ast.Expr)
                        and isinstance(statement.value, ast.Call)):
                    continue
                call = statement.value
                if not (isinstance(call.func, ast.Attribute) and call.func.attr == "note"):
                    continue
                legs = [getattr(keyword.value, "value", None) for keyword in call.keywords
                        if keyword.arg == "leg"]
                if not legs:
                    problems.append("记账点没带字面腿名：%s" % ast.unparse(statement))
                    continue
                following = statements[index + 1] if index + 1 < len(statements) else None
                if not _is_frame_yield(following):
                    problems.append(
                        "记账点没紧跟在发帧那一格之前：%s -> %s" % (
                            ast.unparse(statement),
                            ast.unparse(following) if following is not None else None))
                found.append((statement.lineno, str(legs[0])))
    return found, problems


def test_every_record_point_sits_directly_before_a_frame_yield() -> None:
    """记录点只准站在 ``yield text_sse_frame(...)`` 前一格：搬到 token 那一侧就当场点名。

    这枚是判据⑤ 那把刀的结构面靠山：token 到了不代表帧发出去了 ——
    ``app/api/v1/chat.py::_AnswerPieceStream.frame_for`` 交回 ``None`` 时那一片压根没上屏，
    ``app/api/v1/chat.py::_ApprovedAnswerStream.decide`` 判 ``skip`` 时那一枚正文被拦下。
    """
    found, problems = frame_yield_record_points(Path(chat.__file__).read_text(encoding="utf-8"))
    assert problems == [], problems
    assert found, "一枚记账点都没扫到：这枚结构钉是空的"
    assert sorted({leg for _line, leg in found}) == list(VISIBLE_LEGS), found
