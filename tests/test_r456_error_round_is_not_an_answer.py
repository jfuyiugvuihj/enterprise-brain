"""R456 判据①(c) ＋ 判据②(c)：``kind=error_event`` 那一枚形状不许被读成「答完 21 字」。

run9 里有两枚连一片 text 都没有（``metric-02`` 119.6 s／``scope-02`` 125.2 s 收窗，落在
``error`` ＋ ``request.failed``），而交回评分器的正文取到的是那 21 字兜底句
「本轮未产出任何结论，请重试或补充数据范围。」。本文件钉的是**形状**这一件事：

1. 那一句在流里走的是 ``event: error``，不是 ``event: text``。用同一把在册尺量，这一轮
   ``text_frames == 0``、末帧指纹是空串的指纹、``last_frame_covers_answer is False``，
   而 ``answer`` 在观测桶里仍是空串、只有 ``error_text`` 装着那 21 个字。
   ⇒「答完 21 字」在这一层没有任何依据，它只能是「具名结局的一句人话」。
2. 那一句后面的**码**要具体：``request.failed`` 的 canonical 载荷里 ``error_code`` 逐枚点名。
   ``/ask`` 今天有三条失败出口（空正文具名结局／编排线程抛错／超过处理时限），三枚的
   事件先后、码、legacy 文字两两不同，本文件把它们钉成可分辨的三张脸，
   于是「落在 error＋request.failed」这句读数才真的等于「``error_code=no_answer_produced``」。
3. 把兜底句当终答**发出去**的那一枚洗白形状与在册读数不同形：它有 ``request.completed``、
   有一枚 text 帧、没有 ``request.failed``。拿它当反证，本文件的判别断言当场红。

🔴 分母口径不归本单动（``app/quality/eval.py`` 那两把尺与「分母恒=105」那句都在 R438／R401
名下）：本文件只钉「不许把 error 形状读成答案」，不碰任何计数与评分。
"""
import importlib.util
import json
import time
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.storage import pending_approvals as store
from app.storage.sessions import SessionRegistry
from tests.test_approve_canonical_events import _patch_offline

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r456_error_ruler", _ROOT / "scripts" / "eval_transport_ask_v2.py"
)
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

SESSION_ID = "r456-error-round"
QUESTION = "退款是否计入费用？"  # run9 metric-02 的原题
FALLBACK_TEXT = "本轮未产出任何结论，请重试或补充数据范围。"
TIMEOUT_TEXT = "请求超过系统处理时限"
NAMED_OUTCOME_CODE = "no_answer_produced"


@pytest.fixture(autouse=True)
def memory_ledger(monkeypatch):
    """失败腿会去闭合待批那一行账：账本必须走进程内，不许去连真库（与 R439 同一招）。"""
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)


# ------------------------------------------------------------------ 四枚假流驱动器


def _dispatch_call(*workers):
    return {"name": "dispatch", "args": {"workers": list(workers)},
            "id": "supervisor-dispatch", "type": "tool_call"}


def named_outcome_stream(*_args, **_kwargs):
    """run9 两枚的形状：派发过一发 worker（收端数到两枚 step），图跑完既没正文也没挂起。"""
    yield {
        "messages": [HumanMessage(content=QUESTION),
                     AIMessage(content="", tool_calls=[_dispatch_call("data")])],
        "worker_results": {},
        "final_answer": "",
    }


def washed_outcome_stream(*_args, **_kwargs):
    """洗白形状（反证用）：同一句人话被当成**终答**交回来，收尾照发一枚 text 帧。"""
    yield {
        "messages": [HumanMessage(content=QUESTION),
                     AIMessage(content="", tool_calls=[_dispatch_call("data")])],
        "worker_results": {"data": FALLBACK_TEXT},
        "final_answer": FALLBACK_TEXT,
    }


def raised_leg_stream(*_args, **_kwargs):
    """编排线程抛错那一条出口：``run_with_stream`` 直接 raise，由 ``_run`` 接住塞进队列。"""
    raise RuntimeError("provider refused the request: context_limit_exceeded")
    yield {}  # pragma: no cover —— 让这一枚成为生成器


def stalled_leg_stream(*_args, **_kwargs):
    """超过处理时限那一条出口：谁都不交回来，让 ``RequestBudget`` 自己到点。"""
    time.sleep(0.5)
    yield {}  # pragma: no cover


# ------------------------------------------------------------------ TestClient 真路由


def ask_body(monkeypatch, tmp_path, stream, *, session_id: str = SESSION_ID,
             request_timeout: str = "") -> str:
    from fastapi.testclient import TestClient

    from app.agents.contracts import Principal
    from app.common.auth import create_token, get_user
    from app.main import app

    chat = _patch_offline(monkeypatch, tmp_path, stream, None)
    registry = SessionRegistry(tmp_path / "r456-sessions.json")
    registry.bind(session_id, Principal.from_user(get_user("admin")))
    chat.session_registry = registry
    if request_timeout:
        monkeypatch.setenv("CHAT_REQUEST_TIMEOUT", request_timeout)

    client = TestClient(app)
    response = client.post(
        "/api/v1/ask",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={"message": QUESTION, "session_id": session_id},
    )
    assert response.status_code == 200, response.text
    return response.text


def _event_names(body: str) -> list[str]:
    return [
        frame.split("\n", 1)[0].removeprefix("event: ")
        for frame in body.split("\n\n")
        if frame
    ]


def _payload_of(body: str, name: str) -> dict:
    matches = []
    for frame in body.split("\n\n"):
        if frame.split("\n", 1)[0].removeprefix("event: ").strip() == name:
            data_line = [line for line in frame.split("\n") if line.startswith("data: ")]
            matches.append(json.loads(data_line[0][6:]))
    assert len(matches) == 1, f"{name} 事件应有且只有一枚，实际 {len(matches)}"
    return matches[0]


def read_with_registered_ruler(body: str, answer=None) -> tuple[dict, dict]:
    """同一把在册尺（从 ``_consume`` 起）：不复算第二套口径。

    ``answer`` 交给 ``_frame_readings`` 的那一份正文。留 ``None`` 用的是**观测桶**里那一格
    （``out["answer"]``，只由 ``event: text`` 填）；显式传值是复刻 ``transport()`` 已经写在纸上的
    那一步替换（无正文时把 ``error`` 那一帧的文字顶成交回评分器的答案），🔴 不改它一个字、
    也不在这里重写那条判据，只是把同一把尺架到在册件那一行的位置上。
    """
    out = ruler._blank_observation(SESSION_ID)
    lines = iter([chunk.encode("utf-8") for chunk in body.splitlines(keepends=True)])
    ruler._consume(lines, out)
    ledger = ruler._fold_frames(ruler._new_frame_ledger(), out)
    return out, ruler._frame_readings(ledger, out["answer"] if answer is None else answer)


# ------------------------------------------------------------------ 判据①(c)：码要具体


def test_the_empty_round_names_its_outcome_with_a_specific_code(monkeypatch, tmp_path):
    """``request.failed`` 的 canonical 载荷里那格 ``error_code`` 就是 ``no_answer_produced``。"""
    body = ask_body(monkeypatch, tmp_path, named_outcome_stream)
    failed = _payload_of(body, "request.failed")

    assert failed["status"] == "failed", failed
    assert failed["data"]["error_code"] == NAMED_OUTCOME_CODE, failed
    assert failed["data"]["worker_count"] == 0, failed
    assert _payload_of(body, "error")["content"] == FALLBACK_TEXT
    assert "request.completed" not in _event_names(body), _event_names(body)


def test_the_failure_legs_are_tellable_apart_by_order_code_and_words(monkeypatch, tmp_path):
    """三条失败出口三张脸：先 legacy error 还是先 canonical、码、legacy 文字，两两不同。

    这一枚是「落在 error＋request.failed」这句读数能落成具体码的依据——只看事件名序列
    分不开空正文与线程抛错，加上先后与文字才分得开。
    """
    named = ask_body(monkeypatch, tmp_path, named_outcome_stream, session_id=SESSION_ID + "-named")
    raised = ask_body(monkeypatch, tmp_path, raised_leg_stream, session_id=SESSION_ID + "-raised")
    stalled = ask_body(monkeypatch, tmp_path, stalled_leg_stream,
                       session_id=SESSION_ID + "-stalled", request_timeout="0.05")

    named_names, raised_names, stalled_names = (_event_names(x) for x in (named, raised, stalled))
    assert "error" in named_names and "request.failed" in named_names
    # 空正文那一腿：legacy error **先**，canonical request.failed 后
    assert named_names.index("error") < named_names.index("request.failed"), named_names
    # 另两腿相反：canonical 先，legacy error 后
    assert raised_names.index("request.failed") < raised_names.index("error"), raised_names
    assert stalled_names.index("request.failed") < stalled_names.index("error"), stalled_names

    assert _payload_of(named, "request.failed")["data"]["error_code"] == NAMED_OUTCOME_CODE
    assert _payload_of(raised, "request.failed")["data"]["error_code"] == "internal_error"
    assert _payload_of(stalled, "request.failed")["data"]["error_code"] == "task_timeout"

    assert _payload_of(named, "error")["content"] == FALLBACK_TEXT
    assert _payload_of(stalled, "error")["content"] == TIMEOUT_TEXT
    assert "context_limit_exceeded" in _payload_of(raised, "error")["content"]
    # 具名结局那一腿的终态帧自己承认没交回答案（另两腿不发这一帧，本单不去替它们编）
    assert _payload_of(named, "done")["terminal_state"] == "no_answer"
    assert _payload_of(named, "done")["answer_present"] is False


def test_the_named_outcome_round_has_no_text_frame_under_the_registered_ruler(monkeypatch, tmp_path):
    """形状钉本体：这一轮 ``text_frames==0``，``answer`` 是空串，那 21 个字只在 ``error_text``。"""
    body = ask_body(monkeypatch, tmp_path, named_outcome_stream)
    out, readings = read_with_registered_ruler(body)

    assert "text" not in _event_names(body), _event_names(body)
    assert readings["text_frames"] == 0, readings
    assert readings["max_stream_frames"] == 0, readings
    assert readings["last_frame_chars"] == 0, readings
    assert readings["last_frame_sha"] == ruler._sha12(""), readings
    assert out["answer"] == "", repr(out["answer"])
    assert out["error_text"] == FALLBACK_TEXT, repr(out["error_text"])
    assert out["first_token_at"] is None, out["first_token_at"]

    # 🔴 观测桶里「答案」是空串：那 21 个字只在 error_text 那一格。下面换成在册件的位置——
    # 把 error 那一帧的文字顶成交回评分器的答案之后，同一把尺读出来的是「末帧盖不住答案」。
    _bucket, recorded = read_with_registered_ruler(body, answer=out["error_text"])
    assert recorded["text_frames"] == 0, recorded
    assert recorded["missing_chars"] == 0, recorded
    assert recorded["extra_chars"] == len(FALLBACK_TEXT), recorded
    assert recorded["last_frame_covers_answer"] is False, recorded
    assert recorded["answer_chars"] == len(FALLBACK_TEXT), recorded
    assert ruler._frame_verdict(recorded) is False, recorded


def test_the_done_frame_of_a_named_outcome_round_says_no_answer(monkeypatch, tmp_path):
    """终态那一帧自己承认「这一轮没交回答案」：``terminal_state=no_answer``／``answer_present=false``。"""
    body = ask_body(monkeypatch, tmp_path, named_outcome_stream)
    done = _payload_of(body, "done")

    assert done["terminal_state"] == "no_answer", done
    assert done["answer_present"] is False, done
    assert done["sources_present"] is False, done


def test_the_washed_shape_is_not_the_recorded_shape(monkeypatch, tmp_path):
    """反证（洗白形状）：把那句当终答发出去就有一枚 text 帧、有 request.completed、没有码。

    在册两枚读的是前者那一侧，所以本文件的判别式不是空转：把驱动器换成这一枚，
    上面那枚「没有 request.completed」的断言当场红。
    """
    washed = ask_body(monkeypatch, tmp_path, washed_outcome_stream, session_id=SESSION_ID + "-washed")
    names = _event_names(washed)
    _out, readings = read_with_registered_ruler(washed)

    assert names.count("text") == 1, names
    assert "request.completed" in names and "request.failed" not in names, names
    assert readings["text_frames"] == 1, readings
    assert readings["answer_sha"] == ruler._sha12(FALLBACK_TEXT), readings
    assert readings["last_frame_covers_answer"] is True, readings
    with pytest.raises(AssertionError):
        _payload_of(washed, "request.failed")


def test_the_recorded_two_rows_match_the_named_leg_and_not_the_other_two():
    """把在册两枚读数与上面三张脸对上：run9 那两枚走的是**具名结局**那一腿。

    查的是 ``docs/testing/sidecar-run9-frames.jsonl`` 的 ``events`` 序列这一层（只读），
    不是日志、不是库。
    """
    ledger = _ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
    rows = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row

    for row_id in ("metric-02", "scope-02"):
        names = [event["event"] for event in rows[row_id]["events"]]
        row = rows[row_id]
        assert row["kind"] == "error_event", row_id
        assert names.index("error") < names.index("request.failed"), (row_id, names)
        assert "request.completed" not in names and "sources" not in names, (row_id, names)
        assert "text" not in names, (row_id, names)
        assert row["text_frames"] == 0 and row["extra_chars"] == len(FALLBACK_TEXT), row_id
        assert row["answer_sha"] == ruler._sha12(FALLBACK_TEXT), row_id
        assert row["answer_sha"] != ruler._sha12(TIMEOUT_TEXT), row_id