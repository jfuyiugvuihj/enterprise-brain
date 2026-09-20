"""R100：兼容腿必须真的把思考关掉，而且只有一种拼法。

跟进单 §42 在同一台交付机、同一个容器、同一条 prompt 上跑了八个变体，两条事实把这一单钉住：
兼容腿不带 thinking 字段时，max_tokens=1536 全部花在隐藏思考链上，正文 0 字、
finish_reason=length（表 #5）；带上 "thinking": {"type": "disabled"} 之后同一发答出 93 字、
finish_reason=stop（表 #6）。而两个"看起来也该行"的拼法——兼容体顶层的 think:false（表 #7）
与原生体 options.thinking_disabled（表 #3）——实测都是 0 字。所以"关掉思考"在这条腿上不是一个
偏好，是一个有唯一正确写法的测量。

本文件是那些实机数字的离线镜像：它钉"请求里到底带没带那个字段、带的是不是唯一那种写法、
每条能走到真机的腿是不是都带上、值被写坏时会不会谎报"，一条真 socket 都不开。
判据出处：跟进单 §42.1。原生腿不归本单（R101 裁定本窗口留在兼容腿）。
"""

import logging
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agents import nodes
from app.agents.contracts import ModelTier
from app.common import model_budget
from app.common.model_budget import (
    DEFAULT_MIN_ANSWER_TOKENS,
    DEFAULT_MODEL_THINKING,
    MODEL_THINKING_ENV,
    MODEL_THINKING_MODES,
    THINKING_REQUEST_FIELD,
    THINKING_REQUEST_VALUE,
    budget_signal,
    min_answer_tokens,
    model_budget_readout,
    model_tier_budget,
    resolve_model_thinking,
    reset_thinking_warning,
    thinking_extra_body,
)

GREETING = [HumanMessage(content="你好")]
DISABLED_BODY = {THINKING_REQUEST_FIELD: {"type": "disabled"}}


@pytest.fixture(autouse=True)
def _clean_thinking_env(monkeypatch):
    """每个用例自己拥有 MODEL_THINKING，不继承宿主 shell 里恰好导出的那一个。"""
    monkeypatch.delenv(MODEL_THINKING_ENV, raising=False)
    reset_thinking_warning()
    #: A streaming call that never hands its slot back (跟进单 §43 / R102) would otherwise
    #: downgrade every later model call in this file to the offline path, and the failure would
    #: look like a missing thinking field instead of a leaked semaphore. Rebuild it per test.
    model_budget.reset_default_budget()
    yield
    reset_thinking_warning()
    model_budget.reset_default_budget()


class _RecordingModel:
    """Stand-in provider: records the wire arguments, opens no socket."""

    def __init__(self, chunks=None):
        self.calls: list[dict] = []
        self.chunks = chunks if chunks is not None else [AIMessageChunk(content="一段答案")]

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        return AIMessage(content="一段答案", response_metadata={"finish_reason": "stop"})

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        yield from self.chunks

    def bind_tools(self, tools):
        return self

    @property
    def last_body(self):
        return self.calls[-1].get("extra_body") or {}


def _resilient(primary, tier: ModelTier = ModelTier.ANALYSIS, *, budget="default"):
    """A model built the way _make_model builds one: with this tier budget, on the compat leg."""
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier) if budget == "default" else budget,
    )


# ==================== judgement 1: the switch exists, and defaults to off ====================


def test_the_shipped_default_turns_thinking_off_and_says_which_one_ran():
    policy = resolve_model_thinking()

    assert policy.mode == DEFAULT_MODEL_THINKING == "disabled"
    assert policy.wire == DISABLED_BODY
    assert policy.note == f"{MODEL_THINKING_ENV} unset"


def test_enabled_sends_no_field_at_all_which_is_the_pre_r100_request():
    """The point of "enabled" is that it is *nothing*, not a second spelling nobody measured."""
    policy = resolve_model_thinking("enabled")

    assert policy.mode == "enabled"
    assert policy.wire == {}
    assert thinking_extra_body("enabled") == {}


@pytest.mark.parametrize("raw", ["  DISABLED  ", "Disabled", "disabled"])
def test_a_written_value_is_honoured_across_case_and_space(raw):
    assert resolve_model_thinking(raw).mode == "disabled"


@pytest.mark.parametrize("raw", ["", "   ", "off", "on", "true", "TRUE", "0", "1", "no-think"])
def test_an_unusable_value_costs_a_warning_but_never_a_request(raw, caplog):
    """A typo must not throw away an answer that would have been produced anyway."""
    with caplog.at_level(logging.WARNING):
        policy = resolve_model_thinking(raw)

    assert policy.mode == "disabled"
    assert policy.wire == DISABLED_BODY
    assert "is not one of" in policy.note
    assert "disabled|enabled" in policy.note
    assert any("thinking=disabled" in rec.message for rec in caplog.records), caplog.text


def test_the_absent_value_stays_silent_because_the_samples_ship_it(monkeypatch, caplog):
    """Both shipped env samples write the default, so "nobody said anything" must not shout."""
    monkeypatch.delenv(MODEL_THINKING_ENV, raising=False)
    with caplog.at_level(logging.WARNING):
        assert resolve_model_thinking().mode == "disabled"

    assert caplog.records == []


def test_a_misconfiguration_warns_once_per_process_and_only_the_seam_arms_it_again(caplog):
    with caplog.at_level(logging.WARNING):
        for _ in range(6):
            resolve_model_thinking("off")
        warned = len(caplog.records)
        assert warned == 1, caplog.text

        reset_thinking_warning()
        resolve_model_thinking("off")

    assert len(caplog.records) == 2


def test_the_environment_variable_is_read_on_every_call_not_once_at_import(monkeypatch):
    """_make_model runs at import time; an operator flips a value in a running process too."""
    assert resolve_model_thinking().mode == "disabled"

    monkeypatch.setenv(MODEL_THINKING_ENV, "enabled")
    assert resolve_model_thinking().mode == "enabled"
    assert thinking_extra_body() == {}

    monkeypatch.setenv(MODEL_THINKING_ENV, "disabled")
    assert thinking_extra_body() == DISABLED_BODY


def test_only_the_measured_spelling_goes_on_the_wire():
    """§42 rows #3 and #7: the two near-miss spellings answer with nothing, so they never appear."""
    body = thinking_extra_body()

    assert list(body) == ["thinking"]
    assert body["thinking"] == {"type": "disabled"}
    assert "think" not in body
    assert "thinking_disabled" not in body
    assert body is not model_budget.THINKING_REQUEST_VALUE, "the wire fragment must be a copy"


# ==================== judgement 2: every leg that can reach a model carries it ====================


def test_a_plain_analysis_request_carries_the_field_next_to_its_output_cap():
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)

    body = primary.last_body
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == model_tier_budget(ModelTier.ANALYSIS).max_tokens


def test_a_caller_that_brings_its_own_extra_body_cannot_delete_the_field():
    """langchain_openai merges call kwargs over client defaults without deep-merging extra_body.

    This is the one hole that would have made the whole ticket a no-op on the busiest path:
    a caller that only meant to shorten the answer would silently switch thinking back on.
    """
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING, extra_body={"max_tokens": 64})

    body = primary.last_body
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 64, "the caller cap still wins, as R30 pinned"


def test_a_caller_that_names_thinking_itself_is_obeyed_not_overridden():
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING, extra_body={"thinking": {"type": "enabled"}})

    assert primary.last_body["thinking"] == {"type": "enabled"}


def test_a_model_without_a_budget_still_asks_for_the_field():
    """The reachability check: _budget_kwargs returns nothing when budget is None.

    An env switch that only worked on budgeted calls would look green in a tier test and still
    ship thinking on every unbudgeted one, so this is asserted with no budget object at all.
    """
    primary = _RecordingModel()
    _resilient(primary, budget=None).invoke(GREETING)

    assert primary.last_body["thinking"] == {"type": "disabled"}


def test_the_streaming_leg_carries_the_same_field_as_the_blocking_one():
    primary = _RecordingModel()
    list(_resilient(primary).stream(GREETING))

    assert primary.last_body["thinking"] == {"type": "disabled"}


def test_the_tool_bound_leg_carries_the_same_field():
    """bind_tools rebuilds the wrapper; a field added only in one constructor would be lost here."""
    primary = _RecordingModel()
    bound = _resilient(primary).bind_tools([SimpleNamespace(name="probe")])
    bound.invoke(GREETING)

    assert primary.last_body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("send", ["invoke", "stream"])
def test_an_enabled_process_sends_exactly_the_body_it_sent_before_this_ticket(monkeypatch, send):
    """Switching thinking back on must be a no-op on the wire, not a new field."""
    monkeypatch.setenv(MODEL_THINKING_ENV, "enabled")
    primary = _RecordingModel()
    model = _resilient(primary)
    result = getattr(model, send)(GREETING)
    if send == "stream":
        #: stream is a generator: nothing reaches the provider until it is drained, and a
        #: request that was never made proves nothing about the bytes of that request.
        list(result)

    body = primary.last_body
    assert "thinking" not in body
    assert set(body) == {"max_tokens"}


# ==================== judgement 3: a log can tell the two failures apart ====================


def test_every_budget_line_says_which_mode_ran_not_only_a_clamped_one():
    plain = budget_signal(tier=ModelTier.ANALYSIS, prompt_tokens=100, read_seconds=1.0)
    clamped = budget_signal(
        tier=ModelTier.ANALYSIS,
        prompt_tokens=100,
        read_seconds=1.0,
        clamped=True,
        declared_max_tokens=4096,
        max_tokens=2048,
    )

    assert "thinking=disabled" in plain, plain
    assert "thinking=disabled" in clamped, clamped


def test_the_mode_word_follows_the_setting(monkeypatch):
    monkeypatch.setenv(MODEL_THINKING_ENV, "enabled")
    line = budget_signal(tier=ModelTier.CHAT, prompt_tokens=10, read_seconds=0.5)

    assert "thinking=enabled" in line
    assert "thinking=disabled" not in line


def test_the_process_announces_its_mode_once_and_the_seam_arms_it_again(caplog):
    nodes.reset_thinking_mode_log()
    with caplog.at_level(logging.INFO):
        nodes._log_thinking_mode("http://model.internal:11434/v1")
        nodes._log_thinking_mode("http://model.internal:11434/v1")
    said = [rec.message for rec in caplog.records if "thinking=" in rec.message]

    assert len(said) == 1, said
    assert "兼容腿 thinking=disabled" in said[0]

    nodes.reset_thinking_mode_log()
    with caplog.at_level(logging.INFO):
        nodes._log_thinking_mode("http://model.internal:11434/v1")

    assert len([rec for rec in caplog.records if "thinking=" in rec.message]) == 2


def test_the_readout_carries_the_mode_for_a_health_surface_to_embed():
    thinking = model_budget_readout()["thinking"]

    assert thinking["mode"] == "disabled"
    assert thinking["request_field_sent"] is True
    assert thinking["request_field"] == "thinking"
    assert thinking["accepted_values"] == list(MODEL_THINKING_MODES)
    assert thinking["provenance"] == "calibrated-default"


def test_the_readout_provenance_flips_when_an_operator_speaks(monkeypatch):
    monkeypatch.setenv(MODEL_THINKING_ENV, "enabled")
    thinking = model_budget_readout()["thinking"]

    assert thinking["mode"] == "enabled"
    assert thinking["request_field_sent"] is False
    assert thinking["request_field"] == ""
    assert thinking["provenance"] == "env"


# ==================== judgement 4: the floor moved with the measurement it describes ==========


def test_the_answer_floor_is_the_smallest_cap_with_a_recorded_nonempty_answer():
    """1537 was the low end of a bracket measured on a THINKING model; 1536 is a cap that was

    actually answered on the request this client now sends (§42 row #6: 93 characters,
    finish_reason=stop). The value is a measurement, not a guess, and it is deliberately not
    lower: nothing under it has been tried in this spelling.
    """
    assert DEFAULT_MIN_ANSWER_TOKENS == 1536
    assert min_answer_tokens() == 1536


def test_the_floor_still_honours_an_operator_who_measured_something_else(monkeypatch):
    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", "2048")
    assert min_answer_tokens() == 2048


@pytest.mark.parametrize("sample", [".env.example", "deploy/.env.server.example"])
def test_both_shipped_samples_ask_for_the_mode_the_code_defaults_to(sample):
    """A default that the samples contradict is how a deployment ends up thinking by accident."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / sample).read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if not line.strip().startswith("#")]

    assert f"{MODEL_THINKING_ENV}={DEFAULT_MODEL_THINKING}" in lines, sample
    assert f"MODEL_MIN_ANSWER_TOKENS={DEFAULT_MIN_ANSWER_TOKENS}" in lines, sample

