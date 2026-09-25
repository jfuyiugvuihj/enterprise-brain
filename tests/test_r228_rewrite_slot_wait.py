"""R228 · 后台报告档的检索静默降级（改写腿零耐心抢槽）。

病（总控在现网日志拓的，本件复核）：``app/common/model_handler.py`` 的非流式腿写死了
``acquire(wait_seconds=0)``，抢不到槽就当场 ``_rate_limited_response``。而 ``route_main`` 是用
``Send`` 把 worker 腿并行派出去的（app/agents/orchestrator.py:614），本机
``MODEL_MAX_CONCURRENCY=1``，所以一轮报告题里 doc 腿的改写与兄弟腿的 ANALYSIS 轮**同时**存在：
兄弟腿持槽，改写以 0 秒耐心问闸，逢撞必输。输掉的后果不是一句报错，是
``QueryRewriter.rewrite`` 回落到原始问题 + 一行 WARNING，召回被静默压低而 correctness 照算。

判据 3 的反证钉形状：外层持槽 → 内层改写仍拿到模型写的正文。把修法摘掉（恢复
``wait_seconds=0``）时，红的必须是这一格：下面两条正文断言（``reply.error_code == ""`` 与
``result["rewrites"] != [原问题]``），不是日志文本、不是槽数、不是计时。

全程假 transport：不打真模型、不发 /api/v1/ask、不起服务、不动容器。
"""
import json
import logging
import threading
import time
from pathlib import Path

import pytest

from app.common import model_handler as mh
from app.common.model_budget import DEFAULT_MAX_CONCURRENCY, default_model_budget
from app.common.model_handler import (
    RATE_LIMITED_CODE,
    ModelHandler,
    ModelSource,
    rewrite_slot_readout,
    reset_rewrite_slot_counts,
)

#: 外层那一轮的持槽时长。它只要明显小于 ``REWRITE_SLOT_WAIT_SECONDS`` 就能证明"等得到"，
#: 又要明显大于线程调度抖动，0.4 s 是两头都留余量的取值。
HOLD_SECONDS = 0.4

REWRITE_JSON = json.dumps(
    {
        "rewrites": ["2024 年各部门预算总额", "各部门预算占全年比例", "预算执行进度"],
        "sub_questions": ["哪个部门预算最高", "预算同比变化"],
    },
    ensure_ascii=False,
)
ORIGINAL_QUESTION = "2024年各部门预算情况怎么样？"


class _Chunk:
    def __init__(self, content):
        delta = type("Delta", (), {"content": content})()
        self.choices = [type("Choice", (), {"delta": delta})()]


class _FakeCompletions:
    """兼容腿的替身：流式给两帧，非流式给一枚带 finish_reason 的正文。

    ``stream=True`` 返回的是普通 iterator，所以 ``ModelHandler._release_after_stream`` 会
    停在 yield 上——那正是"外层那一轮持有槽"的形状，持有多久由消费者决定。
    """

    def __init__(self, content=REWRITE_JSON):
        self.content = content
        self.calls = []

    def create(self, model, messages, stream=True, **kwargs):
        self.calls.append({"stream": stream, "model": model})
        if stream:
            return iter([_Chunk("外层"), _Chunk("答案")])
        message = type("Msg", (), {"content": self.content})()
        choice = type("Choice", (), {"message": message, "finish_reason": "stop"})()
        usage = type("Usage", (), {"prompt_tokens": 120, "completion_tokens": 64})()
        return type("Resp", (), {"choices": [choice], "usage": usage})()


class _FakeClient:
    """只实现 chat.completions 的替身：原生腿认它是"别人家的 transport"，一律不发第二请求。"""

    def __init__(self, content=REWRITE_JSON):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(content)})()


def _handler(content=REWRITE_JSON):
    handler = ModelHandler()
    handler.ollama_client = _FakeClient(content)
    handler.local_client = handler.ollama_client
    return handler


def _rewrite(handler):
    return handler.chat(
        [{"role": "user", "content": "把问题改写成三个检索角度"}],
        source=ModelSource.LOCAL,
        stream=False,
    )


@pytest.fixture(autouse=True)
def _clean_ledger():
    """计数是进程级的，用例之间必须各清各的。"""
    reset_rewrite_slot_counts()
    yield
    reset_rewrite_slot_counts()


def _hold_one_slot(handler, ready, release):
    """另一枚线程里跑"外层那一轮"：拿槽 → 报 ready → 停在 yield 上 → 收到 release 才收工。"""
    stream = handler.chat(
        [{"role": "user", "content": "外层那一轮"}], source=ModelSource.LOCAL, stream=True
    )
    next(stream)
    ready.set()
    release.wait(10)
    list(stream)  # 生成器跑完，_release_after_stream 的 finally 把槽交还


# ==================== 判据 3：反证钉（外层持槽 → 改写仍拿到正文） ====================


def test_outer_round_holding_the_slot_no_longer_starves_the_rewrite():
    handler = _handler()
    ready, release = threading.Event(), threading.Event()
    outer = threading.Thread(target=_hold_one_slot, args=(handler, ready, release), daemon=True)
    outer.start()
    assert ready.wait(5), "外层没能持住槽，本件就成了自证"
    threading.Timer(HOLD_SECONDS, release.set).start()

    reply = _rewrite(handler)

    outer.join(5)
    assert reply.error_code == "", f"改写仍然没拿到正文: error_code={reply.error_code}"
    assert json.loads(str(reply))["rewrites"], "正文里没有模型写的改写版本"
    assert RATE_LIMITED_CODE not in str(reply)
    # 同一格里钉住"它是等来的，不是插队的"：没有等待记账就说明两发的顺序倒了。
    counts = rewrite_slot_readout()
    assert counts["grants_after_wait"] == 1, counts
    assert counts["queue_ms_max"] >= int(HOLD_SECONDS * 500), counts


def test_the_pipeline_reaches_the_model_wording_instead_of_the_raw_question(monkeypatch):
    """病的本体在管线出口：改写拿到正文，检索才不会"只用原问题"。

    这条比上一条更靠外一层，所以摘掉修法时它红的是 ``result["rewrites"]`` 那一格——回落形状
    恰好是 ``{"rewrites": [原始问题], "sub_questions": []}``，一眼可辨。
    """
    from app.rag import retrieval_pipeline

    handler = _handler()
    monkeypatch.setattr(retrieval_pipeline, "model", handler)
    ready, release = threading.Event(), threading.Event()
    outer = threading.Thread(target=_hold_one_slot, args=(handler, ready, release), daemon=True)
    outer.start()
    assert ready.wait(5), "外层没能持住槽，本件就成了自证"
    threading.Timer(HOLD_SECONDS, release.set).start()

    result = retrieval_pipeline.QueryRewriter.rewrite(ORIGINAL_QUESTION)

    outer.join(5)
    assert result["rewrites"] != [ORIGINAL_QUESTION], (
        "改写回落到原始问题：这一轮检索只用原问题，召回被容量闸压低"
    )
    assert result["sub_questions"], "子问题拆分同样没能拿到模型正文"


# ==================== 判据 2：上限之外仍降级，但降级可观测、可计数 ====================


def test_bound_expiry_still_degrades_with_the_unchanged_public_reply(monkeypatch, caplog):
    holder = default_model_budget().acquire(wait_seconds=0)
    monkeypatch.setattr(mh, "REWRITE_SLOT_WAIT_SECONDS", 0.2)
    handler = _handler()

    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        started = time.monotonic()
        reply = _rewrite(handler)
        waited = time.monotonic() - started
    holder.release()

    # 判据 4：对外语义一字不改——正文仍是那串容量罐头，码仍是 rate_limited。
    assert reply.error_code == RATE_LIMITED_CODE
    assert str(reply) == (
        "Local model capacity is exhausted (error_code=rate_limited); "
        "no business conclusion was generated."
    )
    assert 0.2 <= waited < 5, f"降级既没有付出上限的等待，也没有马上回来：{waited:.2f}s"

    loud = [
        r for r in caplog.records if "local model concurrency budget exhausted" in r.getMessage()
    ]
    assert [r.levelname for r in loud] == ["ERROR"], "静默降级改成可计数，日志必须升格"
    line = loud[0].getMessage()
    assert "leg=rewrite" in line and "slot_wait_seconds=0.2" in line, line
    assert "waited_ms=" in line, line
    counts = rewrite_slot_readout()
    assert counts["refusals"] == 1, counts
    assert counts["refusal_wait_ms_max"] >= 150, counts


def test_a_rewrite_that_never_queued_is_not_counted_as_either_outcome():
    handler = _handler()

    assert _rewrite(handler).error_code == ""
    assert rewrite_slot_readout() == {
        "grants_after_wait": 0,
        "refusals": 0,
        "queue_ms_total": 0,
        "queue_ms_max": 0,
        "refusal_wait_ms_max": 0,
    }, "空载的一发不许进任何一格，否则读数就说不清今天到底撞了几次"


# ==================== 判据 4：流式那一半的争用形状一字不动 ====================


def test_streaming_leg_keeps_zero_patience():
    """在场那条腿照旧当场回绝：把一句话换成 15 秒静默之后的同一句话，是更差的产品。"""
    holder = default_model_budget().acquire(wait_seconds=0)
    handler = _handler()
    assert mh.REWRITE_SLOT_WAIT_SECONDS > 1, "本件要的是上限没被顺手加到流式腿上"

    started = time.monotonic()
    stream = handler.chat(
        [{"role": "user", "content": "在场提问"}], source=ModelSource.LOCAL, stream=True
    )
    elapsed = time.monotonic() - started
    chunks = [chunk.choices[0].delta.content for chunk in stream]
    holder.release()

    assert elapsed < 1.0, f"流式腿开始等位了（{elapsed:.2f}s），这不是本单授权的改动"
    assert "error_code=rate_limited" in chunks[0]


# ==================== 判据 1：谁持有槽（容量事实 + 本修法不动容量） ====================


def test_the_single_slot_is_a_capacity_fact_this_fix_does_not_touch(monkeypatch):
    """一槽是代码默认 + 两份 env 样例 + compose 的一致读数，本单一处都没改它。

    文档与代码的等价本身由 ``tests/test_r30_config_defaults.py`` 按 ``budget_env_defaults()``
    通盘钉着；这里只钉 R228 需要的两件事：槽数仍是 1，而上限只是一枚耐心，不是容量。
    """
    monkeypatch.delenv("MODEL_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("MODEL_CONCURRENCY_WAIT_SECONDS", raising=False)

    gate = default_model_budget()
    assert DEFAULT_MAX_CONCURRENCY == 1
    assert gate.max_concurrency == 1, "本修法不许以调大槽位为代价"

    root = Path(__file__).resolve().parents[1]
    shipped = {}
    for name in (".env.example", "deploy/.env.server.example"):
        text = (root / name).read_text(encoding="utf-8")
        lines = [
            line.split("=", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("MODEL_MAX_CONCURRENCY=")
        ]
        assert lines == ["1"], (name, lines)
        shipped[name] = lines[0]
    assert set(shipped.values()) == {str(DEFAULT_MAX_CONCURRENCY)}

    # 耐心上限严格小于本进程已经允许的排队时长：它不可能比别的路更让人等。
    assert 0 < mh.REWRITE_SLOT_WAIT_SECONDS < gate.default_wait_seconds
