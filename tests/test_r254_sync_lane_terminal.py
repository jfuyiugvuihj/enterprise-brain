"""R254 · 同步道那六处 `done` 与队列道从此同一张脸（判据⑤）。

09-25 那扇窗的账（`docs/testing/run8-phase2-readout-2026-09-25.md`）说得很直白：
`app/api/v1/chat.py` 全文 `total_tokens` / `usage` 各 0 命中，`done` 载荷写死
`{"type": "done"}`。派工词按当时读到的一枚件写「两处」，今天逐字数出来是**六处**
（入队回执、答案缓存命中、`/ask` 无正文失败、`/ask` 正文道、`/approve` 无正文、
`/approve` 续跑）——落点写错了这件事记在交工报告里，六处一并改口。

判据 → 用例
⑤ 两道同形   test_the_done_frame_says_what_this_turn_actually_finished_as（参数化四道出口）
             test_the_two_lanes_share_one_readout_key_set
             test_the_usage_readout_is_the_same_shape_on_both_lanes
             test_a_parked_sync_turn_hands_back_the_same_handle_as_the_queue_lane
             test_the_done_frame_is_still_the_only_end_of_stream_signal
             test_no_bare_done_payload_is_left_anywhere
③ 同源       test_the_sync_lane_reads_the_same_ledger_as_the_queue_lane

同步道的驱动沿用 `tests/test_approve_canonical_events.py` 那套离线件（假编排 + 临时会话注册表
+ 进程内待批账本），一发模型都不打。
"""

import json

import pytest

from tests.test_approve_canonical_events import (
    BASELINE_APPROVE_EVENT_NAMES,
    PENDING_CHART,
    SESSION_ID,
    drive_approve,
    drive_ask,
    events,
    payload_of,
)

#: `done` 载荷上属于「这一轮到底怎么样了」的那七格——两道共有，一字不许差。
#: `sources_error` 在列内而不是队列道独有：缓存命中那一轮说不出自己有没有出处，
#: 同步道必须有同一格可说，否则「没有出处」与「没读到出处」只在一条道上可区分。
SHARED_READOUT_KEYS = {
    "terminal_state",
    "answer_present",
    "sources_present",
    "sources",
    "sources_error",
    "usage",
    "approval",
}


def _done_frame(body: str) -> dict:
    return payload_of(body, "done")


def _usage_rows(request_id, *, prompt=1_500, completion=250):
    return [{"request_id": request_id, "input_tokens": prompt, "output_tokens": completion}]


def _fake_ledger(monkeypatch):
    """同步道与队列道共用的一本账：谁去读，读到的必须是同一份。

    账里的行是**跑完这一轮才知道 request_id**，所以这里交出去的是那本账的活列表，
    用例在驱动之前把行补进去即可。
    """
    from types import SimpleNamespace

    from app.trace import store as trace_store

    class _Database:
        def __init__(self):
            self.rows = []
            self.asked = []

        def fetch_table(self, table, where, *params):
            self.asked.append((table, where, str(params[0]) if params else ""))
            return [dict(row) for row in self.rows]

    database = _Database()
    monkeypatch.setattr(
        trace_store,
        "default_trace_store",
        lambda: SimpleNamespace(database=database, persistence=None),
    )
    return database


# ==================== 判据⑤：每一处 done 出口都要自报家门 ====================


@pytest.mark.parametrize(
    ("endpoint", "scenario", "state", "answer_present", "sources_present"),
    [
        ("ask", "completed_with_sources", "answered", True, True),
        ("ask", "completed_without_evidence", "answered", True, False),
        ("ask", "unproductive", "no_answer", False, False),
        ("ask", "hitl_repark", "awaiting_approval", True, True),
        ("approve", "completed_with_sources", "answered", True, True),
        ("approve", "unproductive", "no_answer", False, False),
        ("approve", "hitl_repark", "awaiting_approval", True, True),
        ("approve", "hitl_repark_no_text", "awaiting_approval", False, False),
    ],
)
def test_the_done_frame_says_what_this_turn_actually_finished_as(
    monkeypatch, tmp_path, endpoint, scenario, state, answer_present, sources_present
):
    """反证：把 `app/api/v1/chat.py::done_frame_for_turn` 退回 `done_sse_frame(terminal_state="answered")`，
    `no_answer` 与 `awaiting_approval` 那四枚参数化立刻红。"""
    drive = drive_ask if endpoint == "ask" else drive_approve
    body = drive(monkeypatch, tmp_path, scenario)

    frame = _done_frame(body)
    assert frame["type"] == "done", "帧名与 `type` 键是契约冻结规则 1，一个字不许动"
    assert frame["terminal_state"] == state
    assert frame["answer_present"] is answer_present
    assert frame["sources_present"] is sources_present
    assert len(frame["sources"]) is (1 if sources_present else 0)
    if state == "awaiting_approval":
        assert frame["approval"] is not None
    else:
        assert frame["approval"] is None


def test_a_parked_turn_offers_the_notice_without_passing_it_off_as_the_answer(
    monkeypatch, tmp_path
):
    """同步道那 37 个字的归宿是 `approval.notice`，不是正文、也不再是唯一的读数。"""
    from app.api.v1 import chat

    body = drive_ask(monkeypatch, tmp_path, "hitl_repark")
    frame = _done_frame(body)
    notice = chat.hitl_park_text(PENDING_CHART)

    assert frame["approval"]["notice"] == notice
    assert frame["approval"]["pending_steps"] == PENDING_CHART["pending"]
    assert frame["approval"]["labels"] == PENDING_CHART["labels"]
    assert frame["approval"]["session_id"] == SESSION_ID
    assert chat.is_hitl_park_notice(frame["approval"]["decide_body"]["session_id"]) is False


@pytest.mark.parametrize(
    "state", ["answered", "awaiting_approval", "no_answer", "queued", "legacy_row"]
)
def test_the_done_frame_never_leaves_a_key_off(state):
    """七格永远齐全：不许有的出口带 usage、有的出口干脆没这个键。"""
    from app.api.v1 import chat

    frame = json.loads(_done_frame_literal(chat.done_sse_frame(
        terminal_state=state,
        answer_present=False,
        sources_present=False,
    )))
    assert set(frame) == {"type"} | SHARED_READOUT_KEYS
    assert frame["usage"] is None and frame["approval"] is None and frame["sources"] == []


def _done_frame_literal(frame: str) -> str:
    return frame.split("data: ", 1)[1].strip()


# ==================== 判据⑤：两道共用的键集合与子形状 ====================


def test_the_two_lanes_share_one_readout_key_set(monkeypatch, tmp_path):
    """同名的那七格在两道都在，且队列道只是多了它自己那三格（status / request_id / failure）。"""
    from app.api.v1 import chat
    from app.common import reliable_queue

    frame = _done_frame(drive_ask(monkeypatch, tmp_path, "completed_with_sources"))
    payload = chat.build_queue_terminal(
        terminal_state=reliable_queue.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        sources=[{"source": "经营月报.pdf"}],
    )
    assert SHARED_READOUT_KEYS <= set(frame)
    assert SHARED_READOUT_KEYS <= set(payload)
    assert set(payload) - SHARED_READOUT_KEYS == {"schema", "worker_status", "scope_reason_code"}


def test_the_usage_readout_is_the_same_shape_on_both_lanes(monkeypatch, tmp_path):
    """token 读数的键集合只有一份定义：两道的 done / 终态都从 `read_model_call_usage` 出来。"""
    from app.api.v1 import chat

    database = _fake_ledger(monkeypatch)
    database.rows.extend(_usage_rows("req-r254-any"))
    frame = _done_frame(drive_ask(monkeypatch, tmp_path, "completed_with_sources"))
    usage = chat.read_model_call_usage("req-r254-any")
    assert frame["usage"] == usage
    assert usage["model_calls"] == 1
    assert set(usage) == {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "model_calls",
        "calls_with_token_readout",
        "calls_missing_token_readout",
        "token_readout_complete",
        "authoritative",
        "ledger",
    }


def test_the_sync_lane_reads_the_same_ledger_as_the_queue_lane(monkeypatch, tmp_path):
    """同源：那一轮的 request_id 就是它去台账里问的那一枚，两道的数加自同一本账。"""
    requested = []

    def _capture(frame):
        requested.append(payload_of(frame, "request.started")["request_id"])
        return frame

    database = _fake_ledger(monkeypatch)
    first = _done_frame(_capture(drive_ask(monkeypatch, tmp_path, "completed_with_sources")))
    assert first["usage"]["model_calls"] == 0, "账上还没行的那一轮，读数为零而不是 null"

    request_id = payload_of(
        drive_ask(monkeypatch, tmp_path, "completed_with_sources"), "request.started"
    )["request_id"]
    database.rows.extend(_usage_rows(request_id, prompt=2_010, completion=190))
    second = _done_frame(drive_ask(monkeypatch, tmp_path, "completed_with_sources"))

    assert second["usage"]["prompt_tokens"] == 2_010
    assert second["usage"]["completion_tokens"] == 190
    assert second["usage"]["total_tokens"] == 2_200
    assert second["usage"]["authoritative"] is True
    # 同一本账、同一个谓词、就是这一轮自己的 request_id：一道读另一道的数，这形状就红了。
    assert ("model_calls", "request_id = %s", request_id) in database.asked


def test_a_parked_sync_turn_hands_back_the_same_handle_as_the_queue_lane(monkeypatch, tmp_path):
    """同一枚挂起在两道交出的批准把手逐字相同，队列道只多一枚轮询时读到的 `ledger_status`。"""
    from app.api.v1 import chat

    frame = _done_frame(drive_ask(monkeypatch, tmp_path, "hitl_repark"))
    handle = chat.hitl_approval_handle(session_id=SESSION_ID, parked=PENDING_CHART)
    assert frame["approval"] == handle

    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_AWAITING_APPROVAL,
        answer_present=False,
        approval=handle,
    )
    assert terminal["approval"] == handle


# ==================== 契约冻结规则 1：帧还在、还在最后、还在说同一句话 ====================


def test_the_done_frame_is_still_the_only_end_of_stream_signal(monkeypatch, tmp_path):
    names = [name for name, _ in events(drive_ask(monkeypatch, tmp_path, "completed_with_sources"))]
    assert names[-1] == "done"
    assert names.count("done") == 1


@pytest.mark.parametrize("scenario", sorted(BASELINE_APPROVE_EVENT_NAMES))
def test_the_legacy_channels_keep_every_event_the_baseline_had(
    monkeypatch, tmp_path, scenario
):
    """只加载荷键，不减事件：与 R55 记下的那份 legacy 基线逐枚比对重数。

    一枚 scenario 一枚参数化，不许图省事写成循环：`worker_error` / `timeout` 两支会
    `monkeypatch.setenv(CHAT_REQUEST_TIMEOUT, ...)`，同一个用例里循环八支会让后面那几支
    带着前一枚的超时上限跑——实测红在 `unproductive 的 legacy 事件 done 少了`。
    """
    from collections import Counter

    from tests.test_approve_canonical_events import BASELINE_APPROVE_EVENT_NAMES, event_names

    names = Counter(event_names(drive_approve(monkeypatch, tmp_path, scenario)))
    for name, count in Counter(BASELINE_APPROVE_EVENT_NAMES[scenario]).items():
        assert names[name] >= count, f"{scenario} 的 legacy 事件 {name} 少了"


def test_no_bare_done_payload_is_left_anywhere():
    """`{"type": "done"}` 只许出现在唯一构造点里。

    反证：把六处出口中的任何一处改回 `json.dumps({'type': 'done'})`，本枚红在计数上。
    """
    from pathlib import Path

    text = Path("app/api/v1/chat.py").read_text(encoding="utf-8")
    assert text.count('"type": "done"') == 1, "done 载荷的键只许在唯一构造点里写一遍"
    # 六处出口：三处由本轮现报（正文道、缓存命中、批准续跑），三处只能说「没有正文」。
    assert text.count("yield done_sse_frame(") == 3
    assert text.count("yield done_frame_for_turn(") == 3