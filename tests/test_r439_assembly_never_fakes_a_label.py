"""R439 拼装腿：子 Agent 交回空正文时，装配口不许造一句「只剩标签」的 message（判据②b）。

病灶读数（`docs/testing/sidecar-run9-frames.jsonl`，09-28 并树的 run9 真机原件，本文件逐字取用）：
- data-09 ``kind=ok``：``streams=1``、``text_frames=1``、``max_stream_frames=1``，那一发
  ``chars=15`` / ``sha=eda463204b54``；``answer_chars=15`` / ``answer_sha`` 同一枚，
  ``last_frame_covers_answer=True`` ⇒ 客户屏上那 15 个字就是终答本身。
- chart-01 ``kind=approved_ok``：``streams=2``、``text_frames=2``、``max_stream_frames=1``，
  批准前那道流 ``chars=37``（挂起文案），批准后那道流只有 ``at=1`` 一枚 ``chars=16`` /
  ``sha=b74bee4f3746``，``answer_sha`` 与它同一枚 ⇒ 批准之后正文没接回来。
15 / 16 不是巧合：``len("【data Agent 返回】")==15``、``len("【chart Agent 返回】")==16``。
本文件把这两枚尺寸钉成断言，谁改坏标记或改坏尺寸都会当场红。

判据对应：
②b 拼装侧不许再造「只剩标签」的 message → ``test_a_worker_that_hands_back_a_blank_body_...``
    / ``test_the_approval_leg_shares_the_same_assembly_gate``
②b 后半「正文为空就是空，``status`` 与结局码原样」→ 同上两枚的 ``worker_results`` /
    ``agent_results`` 断言：键还在、值还是空串、``status=failed`` 与 ``error.code`` 一格不改
④ 在册面不许改 → ``test_the_marker_format_itself_is_unchanged`` 与
    ``test_a_worker_answer_that_has_a_body_is_still_wrapped_byte_for_byte``
⑤b 摘掉本层守卫就红 → 全部用例走真节点（``_make_worker_wrapper`` / ``_approval_worker_node``
    / ``_final_of``），不读替身返回值
⑤d 正文正常时零回归 → 逐字同形那枚

全进程内：子图是替身、检索腿 monkeypatch，一发模型都不打、一个端口都不开。
"""
import logging

from langchain_core.messages import AIMessage, HumanMessage

from app.agents import orchestrator
from app.agents.contracts import AgentResult, ErrorEnvelope, Principal

#: run9 那两发的终答原文（逐字取自 docs/testing/answers-run9.jsonl 的 answer 字段）。
DATA_MARKER = "【data Agent 返回】"
CHART_MARKER = "【chart Agent 返回】"
BODY = "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；二三线城市每晚 350 元。"


class _StubChild:
    """子图替身：把 ``_make_worker_wrapper`` 交回来的 messages 换成任意形状。"""

    def __init__(self, messages):
        self.messages = list(messages)

    def invoke(self, _payload, config=None):
        return {"messages": self.messages}


def _config(thread_id: str = "r439-assembly") -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "request_id": "req-r439",
            "trace_id": "trace-r439",
            "task_id": "task-r439",
        }
    }


def _run_data_leg(*messages):
    node = orchestrator._make_worker_wrapper(_StubChild(messages), "data")
    return node(
        {"messages": [HumanMessage(content="哪个季度利润最高？")], "worker_results": {}, "agent_results": {}},
        _config(),
    )


def _contents(update) -> str:
    return "\n".join(str(getattr(m, "content", "")) for m in update.get("messages") or [])


def _patch_retrieval(monkeypatch, hits):
    class _Pipeline:
        def search_for_principal(self, query, principal, top_k=5):
            return hits, []

    import app.agents.tools as tools

    monkeypatch.setattr(tools, "_get_pipeline", lambda: _Pipeline())


# ---------------------------------------------------- 判据④ · 标记本身与 run9 的尺寸账


def test_the_marker_format_itself_is_unchanged():
    """内部标记的格式在册：改一个字，run9 那两发的尺寸账就对不上了。"""
    assert orchestrator.AGENT_RETURN_MARKER_TAIL == "Agent 返回】"
    assert orchestrator.agent_return_marker("data") == DATA_MARKER
    assert orchestrator.agent_return_marker("chart") == CHART_MARKER
    # run9 真机窗的 answer_chars 读数：15 与 16 就是这枚标记逐字本身。
    assert len(DATA_MARKER) == 15
    assert len(CHART_MARKER) == 16
    # 只剩标记的那一发没有正文；带正文的那一发摘掉标记就是正文。
    assert orchestrator.agent_answer_body(CHART_MARKER + "\n") == ""
    assert orchestrator.agent_answer_body(f"{DATA_MARKER}\n{BODY}") == BODY
    # 不带标记的文字一个字都不许多丢。
    assert orchestrator.agent_answer_body("  " + BODY + "  ") == BODY
    assert orchestrator.agent_answer_body("【结论】本题按一般条款作答") == "【结论】本题按一般条款作答"


# ---------------------------------------------------- 判据②b · 空正文不造标签消息


def test_a_worker_that_hands_back_a_blank_body_fabricates_no_message(caplog):
    """反证：把 ``_worker_handoff_messages`` 换回「无条件包一条」，本用例当场红。"""
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        update = _run_data_leg()                     # 子图一条消息都没交回

    assert update["messages"] == [], "空正文不许披上内部标记交回父图"
    assert "Agent 返回】" not in _contents(update)
    # 判据②b 后半：正文为空就是空，账面一格不改。
    assert update["worker_results"] == {"data": ""}
    record = update["agent_results"]["data"]
    assert record["status"] == "failed"
    assert record["error"]["code"] == "internal_error"
    # 不许静默：这一发要在日志里留得下名字。
    assert any("[R439]" in line and "data" in line for line in caplog.messages), caplog.messages


def test_a_whitespace_only_body_is_treated_as_blank_too():
    """只有空白与只有换行都不算正文：改前那一发交回来的正是「标签 + 一个换行」。"""
    update = _run_data_leg(AIMessage(content="   \n  "))

    assert update["messages"] == []
    assert update["worker_results"]["data"] == "   \n  ", "摘掉伪造消息不等于把子图交回的值改掉"


def test_a_tool_call_only_worker_turn_leaves_no_handoff_message():
    """子图只吐工具轮（带 tool_calls、无正文）时同样不许长出标签。"""
    call = {"name": "search_docs", "args": {"query": "住宿费"}, "id": "c-1", "type": "tool_call"}
    update = _run_data_leg(AIMessage(content="", tool_calls=[call]))

    assert update["messages"] == []
    assert "Agent 返回】" not in _contents(update)


# ---------------------------------------------------- 判据⑤d · 有正文时逐字零回归


def test_a_worker_answer_that_has_a_body_is_still_wrapped_byte_for_byte():
    """在册形状：``【<worker> Agent 返回】\\n<正文>``，本单一个字没动它。"""
    update = _run_data_leg(AIMessage(content=BODY))

    assert [m.content for m in update["messages"]] == [f"{DATA_MARKER}\n{BODY}"]
    assert update["worker_results"]["data"] == BODY


# ---------------------------------------------------- 判据②b · approval 腿共用同一道闸


def _approval_state():
    principal = Principal(
        user_id="u-r439",
        username="staff-r439",
        roles=["staff"],
        permissions=["resource:view"],
        department="finance",
        clearance=2,
    )
    return {"messages": [HumanMessage(content="住宿发票 20000 元，超过标准了吗？")], "department": "finance"}, principal


def _stub_build_agent_result(monkeypatch, answer: str):
    """把 approval 腿的落账换成指定正文：今天这一腿两条分支都交回非空正文，
    所以这道闸只能这样证明它真的在闸上，而不是在赌某条分支走到（判据①：分支可达性查调用点）。
    """
    record = AgentResult(
        worker="approval",
        status="failed" if not answer.strip() else "success",
        answer=answer,
        error=ErrorEnvelope(code="internal_error", message="stubbed for R439") if not answer.strip() else None,
    )
    monkeypatch.setattr(orchestrator, "build_agent_result", lambda **_kwargs: record)
    return record


def test_the_approval_leg_shares_the_same_assembly_gate(monkeypatch):
    """反证：把 :1018 那一格改回无条件包装，本用例当场红。"""
    _patch_retrieval(monkeypatch, [])
    _stub_build_agent_result(monkeypatch, "")
    state, principal = _approval_state()
    config = {"configurable": {"thread_id": "r439-approval", "principal": principal}}

    update = orchestrator._approval_worker_node(state, config)

    assert update["messages"] == []
    assert "Agent 返回】" not in _contents(update)
    assert update["worker_results"]["approval"] == ""
    assert update["agent_results"]["approval"]["status"] == "failed"


def test_the_approval_leg_keeps_the_registered_marker_when_it_has_a_body(monkeypatch):
    _patch_retrieval(monkeypatch, [])
    _stub_build_agent_result(monkeypatch, BODY)
    state, principal = _approval_state()
    config = {"configurable": {"thread_id": "r439-approval-2", "principal": principal}}

    update = orchestrator._approval_worker_node(state, config)

    assert [m.content for m in update["messages"]] == [f"【approval Agent 返回】\n{BODY}"]


# ---------------------------------------------------- 队列道 / 旧公共 API 的同一格


def test_the_queue_pick_never_hands_the_marker_to_the_report_lane():
    """``_final_of`` 是 ``run_orchestrator_queue`` 交回报告档的那只手（REPORT_LANE_VIA_QUEUE=on）。

    run9 窗里报告档 12 枚的 ``text_frames`` 全在 15..50、``answer_chars`` 都在 120 字以上，
    没有一枚落在标签上 ⇒ 这一格是**结构同源、今天没有真机读数**，不是已发生的事故。
    """
    assert orchestrator._final_of({"final_answer": CHART_MARKER + "\n", "messages": []}) == "处理失败"
    assert "Agent 返回】" not in orchestrator._final_of(
        {"final_answer": "", "messages": [AIMessage(content=DATA_MARKER)]}
    )
    assert orchestrator._final_of({"final_answer": f"{DATA_MARKER}\n{BODY}", "messages": []}) == BODY
    assert orchestrator._final_of({"final_answer": "", "messages": [AIMessage(content=BODY)]}) == BODY
