"""R439 拾取腿：内部交接标记永远不许成为交回客户的那一句终答；拾不到正文就走具名结局（判据②a）。

谁把那 16 个字当终答（本树现读的行号，改动前）：
1. ``app/agents/orchestrator.py:736``（改前行号）把子 Agent 正文包成
   ``AIMessage(content=f"【{name} Agent 返回】\\n{agent_result.answer}")``——正文为空时
   content 只剩标记加一个换行；
2. ``app/agents/nodes.py:2117-2121``（``synthesize`` 的 ``if not final`` 那一圈）在
   ``worker_results`` 全空时退回收尾消息本身，把那枚只剩标记的 content 原样写进
   ``final_answer``；
3. ``app/api/v1/chat.py:2968`` / ``:3537`` 那两处 ``continue`` 只守 **候选拾取**那一路
   （``answer_candidates`` / ``ai_reply``），守不到 ``final_answer`` 那一路：
   ``:2968`` 所在的那一圈只在 ``not pending`` 时跑，且它的产物是第三顺位；而
   ``:2873`` / ``:3521``（改前）的 ``latest_final_answer = str(data["final_answer"])`` 是
   **第二顺位**，比候选更先被 ``_select_final_answer`` 采纳——这一格就是那两发的漏点；
4. ``_select_final_answer`` 自己也没有摘标记这一层，于是 15 / 16 个字的标记顺流到
   ``:2763`` 的收尾 text 帧（``/ask``）与 ``:3373`` 的 text 帧（``/approve``），并写进会话历史。

本文件钉的是第 3、4 格补上之后的形状：``/ask`` 与 ``/approve`` **两路各自**都有牙（判据⑤e），
缓存命中腿不投毒（第 4 层），摘掉任一层守卫本文件当场红（第 2、3 层各有单元钉，判据⑤b），
正文正常时逐字零回归（判据⑤d）。

离线驱动沿用 ``tests/test_approve_canonical_events.py`` 那套假编排 + 临时会话注册表：
一发模型都不打、一个端口都不开、不碰真实 Chroma。
"""
import ast
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

import pytest

from tests.test_approve_canonical_events import (  # noqa: T401  共用同一套离线夹具，词表不外抄
    SESSION_ID,
    _drive,
    _patch_offline,
    events,
    payload_of,
)

DATA_MARKER = "【data Agent 返回】"
CHART_MARKER = "【chart Agent 返回】"
BODY = "第三季度营收 210 万元，是四个季度里最高的一档；环比第二季度增长 16.7%。"

#: ``/ask`` 空正文那条腿在改前就在册的人话（run9 的 metric-02 / scope-02 收到的正是它）。
#: 本单只许把这两族并进这枚**既有**结局，不许新造句子。
NAMED_OUTCOME_TEXT = "本轮未产出任何结论，请重试或补充数据范围。"

CHAT_SOURCE = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "chat.py").read_text(
    encoding="utf-8"
)


@pytest.fixture(autouse=True)
def memory_ledger(monkeypatch):
    """/approve 收尾会把那一行待批改成终态：账本必须走进程内，不许去连真库。

    与 ``tests/test_approve_canonical_events.py`` 同名夹具同一件事——autouse 夹具不跨文件
    生效，本文件自己装一次。
    """
    from app.storage import pending_approvals as store

    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)


def _dispatch_call(*workers):
    return {
        "name": "dispatch",
        "args": {"workers": list(workers)},
        "id": "supervisor-dispatch",
        "type": "tool_call",
    }


def _blank_body_chunk(worker: str, marker: str) -> dict:
    """run9 那两发的形状：worker 交回空正文，收尾消息只剩标记。"""
    return {
        "messages": [
            HumanMessage(content="哪个季度利润最高？"),
            AIMessage(content="", tool_calls=[_dispatch_call(worker)]),
            AIMessage(content=f"{marker}\n"),
        ],
        "worker_results": {worker: ""},
        "agent_results": {},
        "final_answer": f"{marker}\n",
    }


def _body_chunk(worker: str) -> dict:
    return {
        "messages": [
            HumanMessage(content="哪个季度利润最高？"),
            AIMessage(content="", tool_calls=[_dispatch_call(worker)]),
            AIMessage(content=f"{DATA_MARKER}\n{BODY}"),
        ],
        "worker_results": {worker: BODY},
        "agent_results": {},
        "final_answer": BODY,
    }


def blank_data_stream(*_args, **_kwargs):
    yield _blank_body_chunk("data", DATA_MARKER)


def blank_chart_stream(*_args, **_kwargs):
    yield _blank_body_chunk("chart", CHART_MARKER)


def body_stream(*_args, **_kwargs):
    yield _body_chunk("data")


def _drive_endpoint(monkeypatch, tmp_path, stream, endpoint, *, cached=None):
    chat_module = _patch_offline(monkeypatch, tmp_path, stream, None)
    if cached is not None:
        # 命中腿的读数：桩位与被测函数同一个（app.common.cache.get_cached_answer）。
        monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: cached)
    return _drive(monkeypatch, tmp_path, chat_module, endpoint)


def _frames(body: str, name: str) -> list[dict]:
    return [data for event, data in events(body) if event == name]


# ---------------------------------------------------- 判据⑤a/b · 第二层：拾取口本身


def test_the_pick_drops_a_marker_only_final_answer():
    """反证：``_select_final_answer`` 里那一层摘标记被拆掉，本用例当场红。"""
    from app.api.v1.chat import _select_final_answer

    assert _select_final_answer(final_answer=f"{CHART_MARKER}\n") == ""
    assert _select_final_answer(candidates=[DATA_MARKER, ""]) == ""
    assert _select_final_answer(worker_results={"data": CHART_MARKER}) == ""


def test_the_pick_unwraps_a_marker_that_does_carry_a_body():
    from app.api.v1.chat import _select_final_answer

    assert _select_final_answer(final_answer=f"{DATA_MARKER}\n{BODY}") == BODY
    assert _select_final_answer(candidates=[f"{DATA_MARKER}\n{BODY}"]) == BODY


def test_the_pick_still_prefers_worker_results_byte_for_byte():
    """判据⑤d：正文正常时，拾取口径与改前逐字相同（``tests/test_orchestrator.py`` 那一枚也钉着）。"""
    from app.api.v1.chat import _select_final_answer

    assert _select_final_answer(
        final_answer="另一句",
        worker_results={"doc": "  " + BODY + "  ", "chart": ""},
        candidates=["闲聊"],
    ) == BODY
    assert _select_final_answer(
        worker_results={"doc": "甲", "data": "乙"}
    ) == "甲\n\n乙"


# ---------------------------------------------------- 判据⑤b · 第三层：本轮读数那一格


def test_recording_a_marker_does_not_enter_the_turn_readout():
    """``latest_final_answer`` 这一格是第二顺位；不收标签才算守住 run9 那两发的路。"""
    from app.api.v1.chat import _recorded_final_answer

    assert _recorded_final_answer("", f"{CHART_MARKER}\n") == ""
    assert _recorded_final_answer("上一发", DATA_MARKER) == "上一发"
    assert _recorded_final_answer("", "   ") == ""
    assert _recorded_final_answer("", BODY) == BODY


def _gate_calls_per_route() -> dict:
    """``/ask`` 与 ``/approve`` 两条腿各自过没过这道闸（按 AST 数，不按文件里出现几次）。

    两枚端点里各嵌一枚生成器（``generate`` / ``_approve_stream``），所以必须连嵌套函数一起
    数：``ast.walk`` 从端点函数往下遍历，嵌套定义里的调用同样收进来。
    """
    gates = {}
    for node in ast.walk(ast.parse(CHAT_SOURCE)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in ("ask", "approve"):
            gates[node.name] = sum(
                1
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and getattr(call.func, "id", "") == "_recorded_final_answer"
            )
    return gates


def test_both_routes_record_the_final_answer_through_the_gate():
    """判据⑤e：两条腿**各自**都得有这道闸，只装一路就红。"""
    assert _gate_calls_per_route() == {"ask": 1, "approve": 1}
    assert CHAT_SOURCE.count("latest_final_answer = _recorded_final_answer(") == 2
    assert 'latest_final_answer = str(data["final_answer"])' not in CHAT_SOURCE
    assert 'if data.get("final_answer"):' not in CHAT_SOURCE
    # 判据④：两处既有的候选守卫一个字没动。
    assert CHAT_SOURCE.count('if content.startswith("【") and "Agent 返回】" in content[:50]:') == 2


# ---------------------------------------------------- 判据②a · 两路各自的真牙


def test_ask_never_delivers_the_marker_and_names_the_empty_outcome(monkeypatch, tmp_path):
    body = _drive_endpoint(monkeypatch, tmp_path, blank_data_stream, "ask")

    assert "Agent 返回】" not in body, "内部交接标记出现在客户读到的任何一个字节里"
    assert _frames(body, "text") == [], "空正文这一轮不许发 text 帧"
    failed = payload_of(body, "request.failed")
    assert failed["data"]["error_code"] == "no_answer_produced", "拾不到正文必须走具名结局"
    assert [frame["content"] for frame in _frames(body, "error")] == [NAMED_OUTCOME_TEXT]
    done = payload_of(body, "done")
    assert done["terminal_state"] == "no_answer"
    assert done["answer_present"] is False
    assert "request.completed" not in [name for name, _ in events(body)]


def test_approve_never_delivers_the_marker_and_names_the_empty_outcome(monkeypatch, tmp_path):
    """chart-01 那一发走的就是这条腿：批准之后正文没接回来。"""
    body = _drive_endpoint(monkeypatch, tmp_path, blank_chart_stream, "approve")

    assert "Agent 返回】" not in body
    assert _frames(body, "text") == []
    failed = payload_of(body, "request.failed")
    assert failed["data"]["error_code"] == "no_answer_produced"
    done = payload_of(body, "done")
    assert done["terminal_state"] == "no_answer"
    assert done["answer_present"] is False


# ---------------------------------------------------- 第四层 · 缓存命中腿不投毒


def test_a_poisoned_cache_entry_is_never_served_as_an_answer(monkeypatch, tmp_path):
    """改前的树把 15 个字的标记当终答写进过 ``cache_answer``：那种条目今天当未命中。

    反证：摘掉 ``cached`` 那一格的判定，这条腿会把标记顶着「📋 缓存命中」发出去，当场红。
    """
    body = _drive_endpoint(
        monkeypatch, tmp_path, blank_data_stream, "ask", cached=DATA_MARKER
    )

    assert "Agent 返回】" not in body
    assert "缓存命中" not in body, "只剩标记的缓存条目不许被当命中"
    assert payload_of(body, "request.failed")["data"]["error_code"] == "no_answer_produced"


def test_a_normal_cache_entry_still_lands_on_the_screen(monkeypatch, tmp_path):
    """判据⑤d：命中腿零回归——正文正常时缓存那张脸一个字都不许变。"""
    body = _drive_endpoint(
        monkeypatch, tmp_path, blank_data_stream, "ask", cached=BODY
    )

    assert "缓存命中" in body
    assert [frame["content"] for frame in _frames(body, "text")] == [BODY]
    assert _frames(body, "text")[0]["cached"] is True


# ---------------------------------------------------- 判据⑤d · 两路正文正常时零回归


def test_ask_still_delivers_a_normal_worker_answer(monkeypatch, tmp_path):
    body = _drive_endpoint(monkeypatch, tmp_path, body_stream, "ask")

    assert "Agent 返回】" not in body
    assert [frame["content"] for frame in _frames(body, "text")] == [BODY]
    completed = payload_of(body, "request.completed")
    assert completed["data"]["answer_length"] == len(BODY)
    assert payload_of(body, "done")["terminal_state"] == "answered"


def test_approve_still_delivers_a_normal_worker_answer(monkeypatch, tmp_path):
    body = _drive_endpoint(monkeypatch, tmp_path, body_stream, "approve")

    assert "Agent 返回】" not in body
    assert [frame["content"] for frame in _frames(body, "text")] == [BODY]
    completed = payload_of(body, "request.completed")
    assert completed["data"]["answer_length"] == len(BODY)
