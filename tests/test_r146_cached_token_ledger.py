# -*- coding: utf-8 -*-
"""R146 · cached-token 论述与记账归真。

三枚真机事实（都在别人已并树的东西里，本件只引用、不复制）：

1. 原生 ``/api/chat`` 的 done 帧**报** cached：``prompt_eval_cached_count``，逐字帧在
   ``tests/test_r29_thinking_tax.py`` 的 D 段；
2. 兼容腿**非流式**报 cached：``usage.prompt_tokens_details.cached_tokens``，实读在
   ``docs/perf/raw/think_off.jsonl``（9 枚报 usage 的行全部报 cached）与
   ``docs/perf/raw/prodpath.jsonl``（两枚非零、一枚诚实的 0）；本件的夹具数字一律
   从这两份落盘现读，不抄字面量；
3. 兼容腿**流式**根本不带 ``usage`` 对象 ⇒ 答案腿的 token 三枚（input/output/cached）
   今天从流里量不到（``app/common/model_budget.py:377-379`` 的四行真机复测同此）。

所以 R38 写下的「本机不报 cached」两句是错的、第三句是对的。本件钉的就是这个区分：
报的形状必须落到账上，量不到的形状必须写成量不到，**两头都不许造数**。

全程离线：不连模型、不起服务、不开 socket、不碰数据库；B 段的账落在 ``tmp_path`` 的
TraceStore 上（与 ``tests/test_r38_native_input_tokens.py`` 同一套写链）。
"""

import json
import re
from pathlib import Path

import pytest

from app.common.model_handler import ModelReply
from app.trace import spans
from app.trace.spans import (
    REFUTED_CACHED_TOKEN_CLAIM,
    model_token_counts,
    start_model_call,
)

REPO = Path(__file__).resolve().parents[1]
SPANS_SRC = REPO / "app" / "trace" / "spans.py"
THINK_OFF = REPO / "docs" / "perf" / "raw" / "think_off.jsonl"
PRODPATH = REPO / "docs" / "perf" / "raw" / "prodpath.jsonl"
#: R29 已注入的逐字帧：本件**唯一**的帧证据来源（判据 ⑤：禁止第二份逐字帧）。
from tests.test_r29_thinking_tax import (  # noqa: E402
    DATA_SIMPLE_COMPAT,
    DATA_SIMPLE_NATIVE,
    DATA_TOOL200_COMPAT,
    DATA_TOOL200_NATIVE,
)

#: R38 当年写进 spans.py、今天已被真机推翻的原话（小写比较 + 折叠空白：换行重排不许成为一句
#: 错话的藏身处）。判据①要的是这些句子不再作为事实存在。
REFUTED_SENTENCES = (
    "no cached-token field at all",
    "this deployment has no measured source for it",
    "there is deliberately no third key",
    "no third measured pair to add",
    "measured 0 on product traffic because every round rewrites its prefix",
)


def _payload(line: str) -> dict:
    return json.loads(line.split("data: ", 1)[-1] if line.startswith("data:") else line)


def _native_done_frames() -> list[dict]:
    frames = [_payload(line) for line in DATA_SIMPLE_NATIVE + DATA_TOOL200_NATIVE]
    return [frame for frame in frames if frame.get("done") is True]


def _compat_stream_frames() -> list[dict]:
    return [_payload(line) for line in DATA_SIMPLE_COMPAT + DATA_TOOL200_COMPAT]


def _ledger_rows(path: Path) -> list[dict]:
    """把实测原始文件里带 usage 的行读出来：数字**不手抄**，只从机器自己的落盘里取。"""
    rows = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        start = raw.find("{")
        if start < 0:
            continue
        try:
            rows.append(json.loads(raw[start:]))
        except json.JSONDecodeError:
            continue
    return rows


def _usage_triplets(path: Path) -> list[tuple[int, int, int]]:
    """``(prompt, completion, cached)``：原始台账里每一枚**报了**的读数，两种形状都认。

    ``think_off.jsonl`` 把三枚数平铺在行里，``prodpath.jsonl`` 把它们塞在 ``usage`` 底下（正
    是 OpenAI 应答的原形状）。本件的夹具数字只从这两份真机落盘里取，一个字面量都不抄。
    """
    triplets = []
    for row in _ledger_rows(path):
        usage = row.get("usage") if isinstance(row.get("usage"), dict) else row
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        details = usage.get("prompt_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else usage.get("cached_tokens")
        if isinstance(prompt, int) and isinstance(completion, int) and isinstance(cached, int):
            triplets.append((prompt, completion, cached))
    return triplets


def _compat_usage_from_think_off() -> tuple[int, int, int]:
    """取真机 think_off.jsonl 的第一枚非零 cached 读数：(prompt, completion, cached)。"""
    for triplet in _usage_triplets(THINK_OFF):
        if triplet[2] > 0:
            return triplet
    raise AssertionError("think_off.jsonl 里没有非零 cached 读数：前提变了，本件要重读")


def _measured_zero_from_prodpath() -> tuple[int, int]:
    """prodpath.jsonl 里那枚**报了 0** 的读数：(prompt, completion)，0 由台账自己报。"""
    for prompt, completion, cached in _usage_triplets(PRODPATH):
        if cached == 0:
            return prompt, completion
    raise AssertionError("prodpath.jsonl 里没有报 0 的那一枚：前提变了，本件要重读")


def _langchain_reply(prompt: int, completion: int, cached: int | None, *, details_key: str = "cache_read"):
    """按 **langchain 自己的映射**造一枚兼容腿应答，而不是按本件想象的键名造。

    ``_create_usage_metadata`` 才是那台把 ``prompt_tokens_details.cached_tokens`` 改写成
    ``input_token_details.cache_read`` 的机器；用它，本件才是在测真链，而不是在测我的猜想。
    """
    from langchain_core.messages import AIMessage
    from langchain_openai.chat_models.base import _create_usage_metadata

    oai_usage = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if cached is not None:
        oai_usage["prompt_tokens_details"] = {"cached_tokens": cached}
    return AIMessage(content="好的", usage_metadata=dict(_create_usage_metadata(oai_usage, None)))


# ==================== A 段：论述归真（判据 ①③） ====================


def test_the_three_refuted_sentences_are_gone_from_the_metering_boundary():
    """R38 的原话一句都不许留下来当事实；比对时折叠空白，重排不算改掉。"""
    flat = " ".join(SPANS_SRC.read_text(encoding="utf-8").split()).lower()
    for sentence in REFUTED_SENTENCES:
        assert sentence.lower() not in flat, f"被推翻的原话还在 spans.py 里：{sentence}"


def test_the_frame_evidence_says_the_native_leg_does_report_a_cached_count():
    """判据①的第一枚：谁报——原生 done 帧报，报在 ``prompt_eval_cached_count`` 这一格。"""
    frames = _native_done_frames()
    assert len(frames) >= 2, frames
    for frame in frames:
        assert "prompt_eval_cached_count" in frame, frame
        assert isinstance(frame["prompt_eval_cached_count"], int), frame
    #: R29 那两枚 done 帧的具体值（148 与 1）——值也来自帧本身，不手抄成字面量。
    assert {frame["prompt_eval_cached_count"] for frame in frames} >= {1, 148}


def test_the_streamed_compat_frames_still_carry_no_usage_at_all():
    """判据①的第二枚：在哪个形状下报——流式形状**不报**，这仍是事实，不许改口成"到处都报"。"""
    for frame in _compat_stream_frames():
        assert "usage" not in frame, frame
    prompt, completion, cached = _compat_usage_from_think_off()
    counts = model_token_counts(_langchain_reply(prompt, completion, None))
    assert counts == {"input_tokens": prompt, "output_tokens": completion}, counts
    assert cached > 0, "同一条链报了 cached 的那一枚是另一枚夹具，别把两者混成一句"
    assert "cached_tokens" not in counts, "没报 usage 就是没报：不许长出第三枚"


def test_the_prose_states_who_reports_on_which_shape_and_where():
    """论述必须把三枚形状各自的"报不报、报在哪一格"写全，缺一种就是没归真。"""
    doc = spans.model_token_counts.__doc__ or ""
    helper = spans._cached_token_count.__doc__ or ""
    blob = doc + helper
    for field in (
        "prompt_eval_cached_count",
        "prompt_tokens_details.cached_tokens",
        "input_token_details",
    ):
        assert field in blob, field
    assert "non-streaming" in doc and "streaming" in doc, "两形状必须分开写"


def test_the_stream_blindness_is_written_so_nobody_reads_it_as_a_cache_miss():
    """判据③：不可测要写成"流说不出来"，不许读成"缓存没生效"。"""
    doc = spans.model_token_counts.__doc__ or ""
    assert "never" in doc and "did not hit" in doc, doc[-1600:]
    assert "could not say" in doc, "要有一句明写：缺键＝流式说不出来"
    assert "warm" in doc, "要有一句明写：缓存可以是热的"


def test_r38s_pinned_marker_survives_as_a_labelled_historical_name():
    """那枚字面量被 R38 的用例钉在 spans.py 里，本单不许为了让论述好看就把它删掉。"""
    assert REFUTED_CACHED_TOKEN_CLAIM == "native_leg_reports_no_cached_tokens"
    source = SPANS_SRC.read_text(encoding="utf-8")
    assert REFUTED_CACHED_TOKEN_CLAIM in source, "R38 的钉子会红"
    line = [l for l in source.splitlines() if REFUTED_CACHED_TOKEN_CLAIM in l and "=" in l][0]
    assert "REFUTED" in line, "留着可以，但必须站在被推翻这一侧留着"


def test_the_real_machine_log_is_the_source_of_the_fixture_numbers():
    """夹具的 257 必须来自机器自己的落盘，而不是本文件抄来的字面量。"""
    prompt, completion, cached = _compat_usage_from_think_off()
    assert cached > 0, (prompt, cached)
    blob = Path(__file__).read_text(encoding="utf-8")
    head = blob.split("# ==================== A 段")[0]
    assert not re.search(r"cached_tokens.{0,4}\b\d{2,3}\b", head), "文件头不许把实测数抄成字面量"


# ==================== B 段：记账面（判据②） ====================


def test_a_reported_cached_count_is_metered_on_the_compat_shape():
    """think_off.jsonl 那枚 cached 必须落进账；今天它是**能取到却没记**的那一格。"""
    prompt, completion, cached = _compat_usage_from_think_off()
    counts = model_token_counts(_langchain_reply(prompt, completion, cached))
    assert counts == {"input_tokens": prompt, "output_tokens": completion, "cached_tokens": cached}


def test_the_prodpath_zero_is_recorded_as_a_measured_zero():
    """非流式报了 0 就记 0：那枚 0 是实测，不是"没读到"。"""
    prompt, completion = _measured_zero_from_prodpath()
    counts = model_token_counts(_langchain_reply(prompt, completion, 0))
    assert counts.get("cached_tokens") == 0, counts
    assert "cached_tokens" in counts, "报了 0 与没报必须分得开"
    assert (prompt, completion) == (116, 300), (prompt, completion)


def test_an_unreported_cached_count_grows_no_key_and_never_a_zero():
    """🔴 判据②的红线：不许为凑数写 0。没报 ⇒ 键根本不存在，而不是键在值为 0。"""
    prompt, completion, _ = _compat_usage_from_think_off()
    counts = model_token_counts(_langchain_reply(prompt, completion, None))
    assert "cached_tokens" not in counts, counts
    assert counts["input_tokens"] == prompt, "前两枚照旧，本单不是换尺子"


def test_nothing_is_derived_by_subtracting_a_cached_count_from_the_prompt():
    """``prompt_eval_count - cached`` 之类算式不是读数，一条都不许进账。"""
    prompt, completion, _ = _compat_usage_from_think_off()
    reply = ModelReply("好的", finish_reason="stop", input_tokens=prompt, output_tokens=completion)
    counts = model_token_counts(reply)
    assert "cached_tokens" not in counts, counts
    assert counts["input_tokens"] - counts["output_tokens"] == prompt - completion, "差值算得出，但它不是账"


def test_this_boundary_is_ready_for_the_native_frame_the_moment_the_copy_is_widened():
    """spans 这一侧不是缺口的证据：给一枚带 cached 的原生应答，它当场就能记。

    今天带不出来是因为 ``app/common/model_handler.py:394-395`` 只抄两枚计数——那一格不在
    本单写域，回执里作为"要动哪一格"交回总控。
    """
    reply = ModelReply("好的", finish_reason="stop", input_tokens=149, output_tokens=200)
    reply.cached_tokens = 148
    counts = model_token_counts(reply)
    assert counts == {"input_tokens": 149, "output_tokens": 200, "cached_tokens": 148}, counts


def test_the_metered_cached_count_reaches_the_persisted_event(tmp_path, monkeypatch):
    """「取回来并记账」的落点：账落在 ``trace_events`` 的事件 payload 里。"""
    from app.agents.contracts import Principal
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "spans.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "spans.json"),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    config = {
        "configurable": {
            "principal": Principal(user_id="u-146", username="staff146", roles=["staff"]),
            "request_id": "req-146",
            "trace_id": "trace-146",
            "task_id": "task-146",
            "worker": "doc",
            "step_id": "trace-146:worker:doc",
        }
    }
    prompt, completion, cached = _compat_usage_from_think_off()
    span = start_model_call(config, provider="ollama", model_name="qwen3:4b")
    span.finish("completed", summary=model_token_counts(_langchain_reply(prompt, completion, cached)))

    events = [json.loads(line) for line in (tmp_path / "spans.jsonl").read_text(encoding="utf-8").splitlines()]
    finished = [e for e in events if e["event_type"] == "model.finished"][-1]
    assert finished["payload"]["summary"]["cached_tokens"] == cached, finished["payload"]
    rows = store.persistence.list("trace_events")
    booked = [r for r in rows if r["payload"].get("summary", {}).get("cached_tokens") == cached]
    assert booked, "事件行里也得有这枚数，否则只是内存里过了个手"


def test_the_model_calls_row_still_has_no_column_for_it(tmp_path, monkeypatch):
    """把交回的那半笔钉成事实：``model_calls`` 表没有 cached 列，所以那一行仍然只有两枚计数。

    这不是"没做到"的遮羞布，是**下一名单据以动工**的钉子：谁给 ``model_calls`` 加了列，
    这条用例就该红，届时把这条用例一起改掉，而不是让它悄悄过期。
    """
    from app.agents.contracts import Principal
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "spans.jsonl", persistence=JsonPersistenceAdapter(tmp_path / "spans.json"))
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    config = {
        "configurable": {
            "principal": Principal(user_id="u-146b", username="staff146b", roles=["staff"]),
            "request_id": "req-146b",
            "trace_id": "trace-146b",
            "worker": "doc",
            "step_id": "trace-146b:worker:doc",
        }
    }
    prompt, completion, cached = _compat_usage_from_think_off()
    span = start_model_call(config, provider="ollama", model_name="qwen3:4b")
    span.finish("completed", summary=model_token_counts(_langchain_reply(prompt, completion, cached)))
    row = store.persistence.list("model_calls")[0]
    assert cached not in (None, -1)
    assert row["input_tokens"] == prompt and row["output_tokens"] == completion, row
    assert "cached_tokens" not in row, "列还没有：这一格要动 migrations 与 store.py，本单写域外"
    assert "cached_tokens" not in json.dumps(row.get("metadata") or {}), row


# ==================== C 段：只读与离线（判据⑤） ====================


def test_reading_the_counts_opens_no_socket_and_never_calls_the_model(monkeypatch):
    import httpx

    def _boom(*args, **kwargs):
        raise AssertionError("cached-token 归真不许产生任何模型往返或 socket：判据 ⑤")

    for target in ("Client", "AsyncClient"):
        monkeypatch.setattr(getattr(httpx, target), "request", _boom)
    for target in ("get", "post", "head", "options"):
        monkeypatch.setattr(httpx, target, _boom)
    prompt, completion, cached = _compat_usage_from_think_off()
    assert model_token_counts(_langchain_reply(prompt, completion, cached))["cached_tokens"] == cached


def test_no_new_file_writes_anywhere_outside_the_ledger(tmp_path, monkeypatch):
    """C 段第二枚：读数路径只写 trace 的那一个文件，不碰 .env、不碰 deploy。"""
    from app.agents.contracts import Principal
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "only" / "spans.jsonl", persistence=JsonPersistenceAdapter(tmp_path / "only" / "spans.json"))
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    config = {
        "configurable": {
            "principal": Principal(user_id="u-146c", username="staff146c", roles=["staff"]),
            "request_id": "req-146c",
            "trace_id": "trace-146c",
            "worker": "doc",
            "step_id": "trace-146c:worker:doc",
        }
    }
    span = start_model_call(config, provider="ollama", model_name="qwen3:4b")
    prompt, completion, cached = _compat_usage_from_think_off()
    span.finish("completed", summary=model_token_counts(_langchain_reply(prompt, completion, cached)))

    written = sorted(
        p.relative_to(tmp_path).as_posix()
        for p in tmp_path.rglob("*")
        if p.is_file() and p.suffix == ".json" or p.is_file() and p.suffix == ".jsonl"
    )
    assert written == ["only/spans.json", "only/spans.jsonl"], written
    assert (tmp_path / "only" / ".spans.json.lock").exists(), "写链自己的锁，不是本单新开的口子"
