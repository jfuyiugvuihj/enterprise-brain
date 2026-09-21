"""Machine-wide budget for the single local model server.

A private deployment runs one local model on the customer machine. Every boundary
that invokes that model must share one budget so a 14B model cannot be called
without limit. ``wait_seconds`` keeps legitimate parallel workers queueing instead
of stampeding the model; a zero wait preserves the previous non-blocking behavior.

The other half of that budget is tokens and clock, and it is per tier: a greeting, a
memory summary and a long analysis answer must not share one output cap or one timeout.
``tier_profile`` / ``model_tier_budget`` below read that configuration, and
``app/agents/contracts.py:ModelBudget`` is the object they fill in.

When the two halves contradict each other -- a tier whose declared output cannot be written
inside ``MODEL_REQUEST_TIMEOUT`` at the calibrated rates -- the rule is to shorten the
**answer**, never to let the request hang until the client gives up. An expired clock does
not protect the machine: it hands the caller an offline sentence dressed up as a reply, which
is the one outcome ``app/agents/nodes.py`` already refuses to produce for a context collision.
``max_tokens_verdict`` performs that arithmetic, ``authorize`` applies it to one call, and
every number behind the decision is logged next to the final value, so a clamp can never be
mistaken for a choice an operator made.
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from app.agents.contracts import (
    CONTEXT_LIMIT_CODE,
    MODEL_BUDGET_MARKER,
    OUTPUT_TRUNCATED_CODE,
    ModelBudget,
    ModelTier,
)

from app.common.logger import logger

#: Slots on the one local model server. It was spelled twice in this file and once in
#: each shipped env sample; the number lives here now so ``tests/test_r30_config_defaults.py``
#: can check the documentation against it instead of against a copy. Same value, same
#: variable, same ``_env_int``: the concurrency semantics are untouched.
DEFAULT_MAX_CONCURRENCY = 1


class ModelBudgetExhausted(RuntimeError):
    """The local model is busy and no slot became available in time."""

    code = "rate_limited"

    def __init__(self, wait_ms: int):
        super().__init__(
            "Local model capacity is exhausted "
            f"(error_code={self.code}); no business conclusion was generated."
        )
        self.wait_ms = wait_ms


class ModelContextLimitExceeded(RuntimeError):
    """The prompt plus this tier's declared output cannot fit the local ``n_ctx``.

    Before this existed the collision had two outcomes, neither of which left a code
    behind: the server refused the request and the caller saw a bare provider error, or
    the server answered with a completion cut off mid-sentence. Both are refused here,
    in favour of not sending a request the window demonstrably cannot hold.
    """

    code = CONTEXT_LIMIT_CODE

    def __init__(self, budget, prompt_tokens: int):
        super().__init__(
            "Local model context window cannot hold this request "
            f"(error_code={self.code}): prompt_tokens={prompt_tokens} and "
            f"max_tokens={budget.max_tokens} do not fit n_ctx={budget.context_limit_tokens}; "
            "no business conclusion was generated."
        )
        self.prompt_tokens = int(prompt_tokens)
        self.max_tokens = int(budget.max_tokens)
        self.context_limit_tokens = int(budget.context_limit_tokens)
        self.tier = budget.tier


@dataclass
class _ModelSlot:
    """A held budget slot. Release is idempotent so streaming paths cannot leak capacity."""

    _budget: "LocalModelBudget"
    wait_ms: int = 0
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._budget._semaphore.release()

    def __enter__(self) -> "_ModelSlot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class LocalModelBudget:
    def __init__(self, max_concurrency: int | None = None, wait_seconds: float | None = None):
        configured = max_concurrency if max_concurrency is not None else _env_int(
            "MODEL_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY
        )
        self.max_concurrency = max(1, configured)
        self.default_wait_seconds = (
            self._configured_wait() if wait_seconds is None else float(wait_seconds)
        )
        self._semaphore = threading.Semaphore(self.max_concurrency)

    @staticmethod
    def _configured_wait() -> float:
        raw = os.getenv("MODEL_CONCURRENCY_WAIT_SECONDS", "").strip()
        if not raw:
            return 60.0
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 60.0

    def acquire(self, *, wait_seconds: float | None = None) -> _ModelSlot:
        """Take a model slot, waiting up to ``wait_seconds`` for free capacity."""
        budget_wait = self.default_wait_seconds if wait_seconds is None else float(wait_seconds)
        started = time.monotonic()
        acquired = (
            self._semaphore.acquire(blocking=False)
            if budget_wait == 0
            else self._semaphore.acquire(timeout=budget_wait)
        )
        wait_ms = int((time.monotonic() - started) * 1000)
        if not acquired:
            raise ModelBudgetExhausted(wait_ms)
        return _ModelSlot(self, wait_ms=wait_ms)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


_default: LocalModelBudget | None = None
_default_size: int | None = None
_default_lock = threading.Lock()


def default_model_budget() -> LocalModelBudget:
    """Process-wide budget shared by every model boundary."""
    global _default, _default_size
    configured = _env_int("MODEL_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)
    with _default_lock:
        if _default is None or _default_size != max(1, configured):
            _default = LocalModelBudget(max_concurrency=configured)
            _default_size = max(1, configured)
        return _default


def reset_default_budget() -> None:
    """Drop the cached budget so configuration changes take effect."""
    global _default, _default_size
    with _default_lock:
        _default = None
        _default_size = None


# ==================== per-tier token and timeout budget ====================

#: Output cap per tier, in tokens. These are the defaults ``.env.example`` documents;
#: ``MODEL_TIER_<TIER>_MAX_TOKENS`` overrides one of them for a machine that is faster or
#: slower than the measured baseline.
TIER_MAX_TOKEN_DEFAULTS: dict[ModelTier, int] = {
    ModelTier.CHAT: 256,
    ModelTier.PLAN: 256,
    ModelTier.REWRITE: 256,
    ModelTier.ALERT: 384,
    ModelTier.COMPRESS: 512,
    ModelTier.CODE: 512,
    ModelTier.ANALYSIS: 1536,
}

#: CALIBRATED MEASUREMENTS, NOT PREFERENCES. Both numbers are the CPU-only floor measured on
#: the delivery baseline (qwen3.5:9b through Ollama, CPU-only, 2026-09-16): prefill 35.2
#: tok/s, decode 8.18 tok/s, rounded down to the pessimistic integer, because a rate that is
#: too optimistic is exactly the cut-off-mid-answer bug this section removes. Re-measure with
#: ``python scripts/bench_model_throughput.py`` and override the two variables below; never
#: edit a default to match a wish.
#:
#: R99 records the question and the answer the container gave. Three candidates were open on
#: 2026-09-19 for "the model answered in 4 s while our client spent the whole 120 s ceiling",
#: and the 22:3x measurement inside the shipping container (image ``78b8507``, 100% GPU,
#: ~37 tok/s) settles two of them:
#:
#:   (a) TRUE, and it is the whole cause of the timeout half: the rates below are a CPU-only
#:       calibration, so the tier's own worst case is 192 s against a 120 s ceiling.
#:   (b) TRUE, and it is the cause of the other half, which the clock never explained: the
#:       same model spends a 1024 or 1536 token cap entirely on hidden reasoning and returns
#:       zero visible characters (see MODEL_MIN_ANSWER_TOKENS below).
#:   (c) NOT SUPPORTED: 1024-1536 output tokens cost 28 s on the native ``/api/chat`` leg and
#:       38 s on the compatible ``/v1/chat/completions`` leg of the same machine -- inside one
#:       order of magnitude. Nothing here is designed around the transport, and the earlier
#:       reading that ``/api/chat`` was simply faster is retired. Its scope, though, is one
#:       specific configuration: both legs were generating hidden reasoning when it was taken.
#:       Since R100 the compatible leg asks for ``thinking: {"type": "disabled"}``, so this pair
#:       of numbers no longer describes the two legs as they run today -- re-measure before
#:       citing it (R101 audit, 09-20).
#:
#: These stay the only rates with a recorded provenance, so they remain -- and shortening the
#: answer, never the deadline, is what makes trusting a pessimistic rate survivable.
DEFAULT_PREFILL_TOKENS_PER_SECOND = 35.0
DEFAULT_DECODE_TOKENS_PER_SECOND = 8.0
DEFAULT_TIMEOUT_MARGIN = 1.15
DEFAULT_TIMEOUT_FLOOR_SECONDS = 10.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
#: ``MODEL_REQUEST_TIMEOUT`` is the ceiling for one request. Read it only through
#: :func:`request_timeout_ceiling_seconds`, so no second module can keep its own default.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_CONTEXT_TOKENS = 4096

#: The ``MODEL_MIN_ANSWER_TOKENS`` default: the output cap below which this model has not been
#: observed to answer at all, so an answer cap may never be clamped past it.
#:
#: RE-CALIBRATED FOR THE LINK THAT SHIPS NOW. The previous value, 1537, measured the hidden
#: chain of a model that was *thinking*: the 2026-09-19 22:3x container runs (board §4BE.3)
#: got 0 visible characters at ``num_predict``/``max_tokens`` 1024 and 1536, both with
#: ``finish=length``, and 439 characters at 4096. R100 asks the compatible leg to stop
#: thinking (``MODEL_THINKING`` below), so the floor has to be measured on the thinking-free
#: link -- carrying a thinking-on number over would keep a limit nobody asked for again.
#:
#: Measured on that link by 总控 2026-09-19 23:4x, same container, same prompt, compat
#: ``/v1/chat/completions`` with ``thinking:{"type":"disabled"}`` (跟进单 §42 rows #6 and #8):
#:
#:   max_tokens 1536 -> 93 visible chars, finish_reason=stop, completion_tokens=1328
#:   max_tokens 4096 -> 82 visible chars, finish_reason=stop, completion_tokens=1640
#:
#: 1536 is the smallest cap with a recorded non-empty, self-terminated answer on the request
#: the product actually sends, and this default is that cap. It is deliberately not lower:
#: nothing under 1536 has ever been tried in this spelling, and §42 conclusion 2 records that
#: the switch moves the reasoning out of ``content`` **without saving a billed token** (1328
#: of them for 93 characters), so nothing supports the floor having collapsed towards the 46
#: tokens the native leg spends on a top-level ``think:false``. A smaller number here would be
#: exactly the invention this constant exists to make impossible.
#:
#: 待真机标定 (below 1536): run ``python scripts/bench_model_throughput.py --caps 256 512
#: 1024`` inside the shipping container *after* its compatible arm learns to send
#: ``thinking:{"type":"disabled"}`` -- as landed in R99 it sends only ``think:false`` at the
#: top level there, which §42 row #7 measures as 0 characters, so the script as it stands
#: cannot produce this bracket. Write what a rerun prints into the environment variable;
#: ``scripts/bench_model_throughput.py`` stays the only command allowed to move this number.
DEFAULT_MIN_ANSWER_TOKENS = 1536

#: Framing around each message: the estimate is of a request, not of a bare string.
MESSAGE_OVERHEAD_TOKENS = 4

_CJK_RANGES = (
    (0x2E80, 0x2EFF),
    (0x3000, 0x303F),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
    (0x20000, 0x2A6DF),
)

#: The code for "this call ran out of clock". Reused from the closed enum in
#: app/agents/contracts.py:ErrorEnvelope instead of being invented here, so a timeout is
#: counted with the same vocabulary that counts every other terminal verdict.
TIMEOUT_ERROR_CODE = "task_timeout"

#: Exception class names that mean a timeout at this boundary. Matched by name because the
#: provider layer wraps: what reaches ``app/agents/nodes.py`` is an ``openai`` client error
#: around an ``httpx`` one, and neither is a builtin ``TimeoutError``, which is exactly why
#: ``app/trace/spans.py:error_code_for`` files both as ``internal_error``.
TIMEOUT_ERROR_TYPE_NAMES = (
    "APITimeoutError",
    "APIConnectionTimeoutError",
    "TimeoutException",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "TimeoutError",
    "ReadTimeoutError",
    "ConnectTimeoutError",
)

TIMEOUT_ERROR_FRAGMENTS = (
    "request timed out",
    "timed out",
    "deadline exceeded",
)

#: Fragments a local server uses when it refuses a request for being too long.
CONTEXT_ERROR_FRAGMENTS = (
    "context length",
    "context_length",
    "maximum context",
    "n_ctx",
    "too many tokens",
    "prompt is too long",
)


def _env_set(name: str) -> bool:
    """Whether an operator wrote this variable at all, which is a rate's provenance."""
    return bool(str(os.getenv(name, "") or "").strip())


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "") or "").strip()
    try:
        value = float(raw) if raw else float(default)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


def _env_positive_int(name: str, default: int) -> int:
    """Read a positive integer knob: unset, broken, zero or negative all mean the default.

    ``_env_int`` above is deliberately not reused: it accepts 0, which for the concurrency
    slots is then floored to 1, and for an answer floor would silently delete the floor.
    """
    raw = str(os.getenv(name, "") or "").strip()
    try:
        value = int(raw) if raw else int(default)
    except ValueError:
        return int(default)
    return value if value > 0 else int(default)


def min_answer_tokens() -> int:
    """The cap below which this model has been measured to answer with nothing at all."""
    return _env_positive_int("MODEL_MIN_ANSWER_TOKENS", DEFAULT_MIN_ANSWER_TOKENS)


# ==================== the thinking switch (R100) ====================

#: ``MODEL_THINKING``: does this deployment ask the local server to spend its output budget on
#: a hidden chain of thought before it answers?
#:
#: The question is not academic on the machine that ships. 跟进单 §42 ran one prompt eight
#: ways on the live container: the compatible leg with no thinking field at all spent
#: ``max_tokens=1536`` entirely on hidden reasoning and returned **zero visible characters**
#: with ``finish_reason=length`` (row #5), while the same request carrying
#: ``thinking:{"type":"disabled"}`` returned 93 characters and ``finish_reason=stop`` (row #6).
#: The near-miss spellings return nothing too -- top-level ``think:false`` on the compat body
#: (row #7) and ``options.thinking_disabled`` on the native body (row #3) are both measured at
#: 0 characters -- so an operator who copies one of those concludes the model cannot be
#: switched off. It can, in exactly one spelling per leg: native takes ``think`` at the request
#: top level, compat takes ``thinking`` in the body.
#:
#: RE-MEASURED ON THE SHIPPING HOST BY R29 (2026-09-21, qwen3:4b, host Ollama, streaming -- which
#: is the shape the answer leg actually uses), and the sentence above needs its second half
#: spelled out, because "switched off" is a claim about the *field*, not about the cost:
#:
#:   compat  thinking:{"type":"disabled"}   reasoning 613 chars, content 26, 5.40 s
#:   compat  no thinking field at all       reasoning 613 chars, content 26, 5.35 s
#:   native  think:false                    thinking    0 chars, content 577, 5.10 s  (369 tok)
#:   native  think absent                   thinking  613 chars, content 26, 5.39 s  (415 tok)
#:
#: So on the compatible streaming leg this field changes **nothing measurable** -- it is the
#: non-streaming (rewrite) shape that §42 row #6 measured, and R100 landed the spelling, not a
#: saving. And ``think:false`` on the native leg answers 判据① literally (0 ``thinking`` chars)
#: while doing nothing for 判据②: the same text arrives in ``content`` instead, at the same
#: token cost, so an answer leg moved there would stream the model's monologue to the customer.
#: Two further host facts belong with them: at the CHAT tier's measured cap of 256 output tokens
#: *both* legs return zero visible characters (the reasoning eats the whole cap either way), and
#: streamed ``/v1`` frames carry no ``usage`` object at all, so the answer leg cannot be metered
#: from a stream -- which is also why ``model_calls.input_tokens``/``output_tokens`` stay NULL for
#: streamed rounds whatever this switch says.
#:
#: This boundary owns the compatible leg (``app/agents/nodes.py:_make_model``), so it sends
#: that one spelling and no other. ``disabled`` is the default because the measured
#: alternative answers with nothing: R99 made an empty body an honest failure, and an honest
#: failure is better than a fake answer, but it is still not an answer.
MODEL_THINKING_ENV = "MODEL_THINKING"
#: The only two values that mean something. Anything else is a misconfiguration, not a mode.
THINKING_DISABLED = "disabled"
THINKING_ENABLED = "enabled"
MODEL_THINKING_MODES = (THINKING_DISABLED, THINKING_ENABLED)
DEFAULT_MODEL_THINKING = THINKING_DISABLED
#: The request field Ollama's OpenAI-compatible ``/v1/chat/completions`` body reads, and the
#: value §42 row #6 measured on it. A wire object rather than a boolean because that is the
#: shape that was measured; the field is not offered as a knob to tune.
THINKING_REQUEST_FIELD = "thinking"
THINKING_REQUEST_VALUE = {"type": "disabled"}


@dataclass(frozen=True)
class ThinkingPolicy:
    """What this process asks the model about thinking, and how it arrived at that.

    ``note`` rides along for the reason ``KeepAlivePolicy`` has one: the resolved value alone
    cannot tell an operator whether it was configured, defaulted, or rescued from a typo, and
    the last of the three is the one that will be searched for at three in the morning.
    """

    mode: str
    #: The request-body fragment this boundary adds: ``{"thinking": {...}}``, or empty when
    #: thinking is left alone. An ``enabled`` call has to be the exact body this product sent
    #: before R100, so switching thinking back on is a no-op on the wire rather than a second
    #: spelling nobody measured.
    wire: dict[str, Any]
    note: str


#: Whether the "your value was unusable" warning has already been said this process lifetime.
#: ``_make_model`` runs once per graph at import time and every call re-reads the environment,
#: so without a latch one typo prints a dozen identical lines and buries the one finding that
#: explains the others.
_THINKING_WARNING_SHOWN = False


def reset_thinking_warning() -> None:
    """Allow the next misconfiguration to warn. A test seam, and the reason the latch is named.

    It is also what an operator gets from one grep: the count of this line in a log is either
    zero or one, which is what makes it usable as a signal rather than noise.
    """
    global _THINKING_WARNING_SHOWN
    _THINKING_WARNING_SHOWN = False


def resolve_model_thinking(raw: str | None = None) -> ThinkingPolicy:
    """Read ``MODEL_THINKING`` defensively: a wrong value changes nothing except the log line.

    ``raw`` is the test seam, mirroring :func:`resolve_keep_alive`. One rule and three cases:
    a written value is honoured, an absent value takes the shipped default quietly, and every
    other input takes the default *loudly*. Nothing here raises -- a request that would have
    been answered is never thrown away because a configuration line has a typo in it, and the
    failure this ticket exists to prevent is a silent one, so the loud half is the warning.

    Absent stays silent on purpose: both shipped env samples write the default, so "nobody
    said anything" and "the default" must not come to mean two different things. Present and
    unusable -- empty, whitespace, ``off``, ``TRUE``, a number, any other string -- is the case
    that has to leave exactly one warning behind.
    """
    global _THINKING_WARNING_SHOWN
    if raw is None:
        raw = os.environ.get(MODEL_THINKING_ENV)
        if raw is None:
            note = f"{MODEL_THINKING_ENV} unset"
            value = DEFAULT_MODEL_THINKING
        else:
            value = raw.strip()
            note = f"{MODEL_THINKING_ENV}={value!r}"
    else:
        value = str(raw).strip()
        note = f"{MODEL_THINKING_ENV}={value!r} (given)"
    value = value.lower()
    if value in MODEL_THINKING_MODES:
        mode = value
    else:
        mode = DEFAULT_MODEL_THINKING
        note = f"{note} is not one of {'|'.join(MODEL_THINKING_MODES)}; using {mode}"
        if not _THINKING_WARNING_SHOWN:
            _THINKING_WARNING_SHOWN = True
            logger.warning(
                f"[ModelBudget] {note}. The request is still sent, sized by this default, "
                "and every later line says "
                f"thinking={mode}."
            )
    wire = (
        {THINKING_REQUEST_FIELD: dict(THINKING_REQUEST_VALUE)}
        if mode == THINKING_DISABLED
        else {}
    )
    return ThinkingPolicy(mode=mode, wire=wire, note=note)


def thinking_extra_body(raw: str | None = None) -> dict[str, Any]:
    """The body fragment one call adds for its thinking mode, or ``{}`` when it adds none."""
    return {key: dict(value) if isinstance(value, dict) else value for key, value in resolve_model_thinking(raw).wire.items()}


def model_thinking_mode(raw: str | None = None) -> str:
    """The mode one call runs in, for a log line that has to say which one it was."""
    return resolve_model_thinking(raw).mode


def request_timeout_ceiling_seconds() -> float:
    """``MODEL_REQUEST_TIMEOUT``: one variable, one default, read in one place."""
    return _env_float("MODEL_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT_SECONDS)


def context_limit_tokens() -> int:
    """The ``n_ctx`` that every tier's prompt plus output has to fit inside."""
    return int(_env_float("MODEL_CONTEXT_TOKENS", float(DEFAULT_CONTEXT_TOKENS)))


def tier_max_tokens_env_name(tier: ModelTier | str) -> str:
    """The one spelling of a tier's override variable: ``MODEL_TIER_<TIER>_MAX_TOKENS``."""
    return f"MODEL_TIER_{ModelTier(tier).value.upper()}_MAX_TOKENS"


def tier_max_tokens(tier: ModelTier | str) -> int:
    resolved = ModelTier(tier)
    configured = _env_int(tier_max_tokens_env_name(resolved), TIER_MAX_TOKEN_DEFAULTS[resolved])
    return max(1, min(int(configured), context_limit_tokens() - 1))


def tier_profile(tier: ModelTier | str) -> dict[str, float | int]:
    """Every configured number behind one tier, keyed by ``ModelBudget`` field name.

    ``max_tokens`` is never ``None`` here: a tier that cannot say how much it is allowed to
    write is the dead contract this section replaces.
    """
    return {
        "max_tokens": tier_max_tokens(tier),
        "context_limit_tokens": context_limit_tokens(),
        "prefill_tokens_per_second": _env_float(
            "MODEL_PREFILL_TOKENS_PER_SECOND", DEFAULT_PREFILL_TOKENS_PER_SECOND
        ),
        "decode_tokens_per_second": _env_float(
            "MODEL_DECODE_TOKENS_PER_SECOND", DEFAULT_DECODE_TOKENS_PER_SECOND
        ),
        "timeout_margin": _env_float("MODEL_TIMEOUT_MARGIN", DEFAULT_TIMEOUT_MARGIN),
        "timeout_floor_seconds": _env_float("MODEL_TIMEOUT_FLOOR_SECONDS", DEFAULT_TIMEOUT_FLOOR_SECONDS),
        "timeout_ceiling_seconds": request_timeout_ceiling_seconds(),
        "connect_timeout_seconds": _env_float("MODEL_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS),
    }


def budget_env_defaults() -> dict[str, float | int]:
    """Every model-budget variable the code reads, with the default it uses when unset.

    Slots, caps, rates and the window: one mapping for the whole budget, because a
    documented number that is not in here is a number nothing checks.

    Criterion (3) of this ticket is "the code default and ``.env.example`` agree", which is
    only checkable if one object holds both sides of the claim. This is that object: the
    reader above produces these numbers and ``tests/test_r30_config_defaults.py`` compares
    them against the two shipped env files, so neither file can drift again the way
    ``MODEL_REQUEST_TIMEOUT`` did (60 in code, 120 documented).
    """
    defaults: dict[str, float | int] = {
        "MODEL_MAX_CONCURRENCY": DEFAULT_MAX_CONCURRENCY,
        "MODEL_REQUEST_TIMEOUT": DEFAULT_REQUEST_TIMEOUT_SECONDS,
        "MODEL_CONTEXT_TOKENS": DEFAULT_CONTEXT_TOKENS,
        "MODEL_PREFILL_TOKENS_PER_SECOND": DEFAULT_PREFILL_TOKENS_PER_SECOND,
        "MODEL_DECODE_TOKENS_PER_SECOND": DEFAULT_DECODE_TOKENS_PER_SECOND,
        "MODEL_TIMEOUT_MARGIN": DEFAULT_TIMEOUT_MARGIN,
        "MODEL_MIN_ANSWER_TOKENS": DEFAULT_MIN_ANSWER_TOKENS,
        "MODEL_TIMEOUT_FLOOR_SECONDS": DEFAULT_TIMEOUT_FLOOR_SECONDS,
        "MODEL_CONNECT_TIMEOUT_SECONDS": DEFAULT_CONNECT_TIMEOUT_SECONDS,
    }
    for tier, tokens in TIER_MAX_TOKEN_DEFAULTS.items():
        defaults[tier_max_tokens_env_name(tier)] = tokens
    return defaults


def model_tier_budget(tier: ModelTier | str) -> ModelBudget:
    """Resolve one tier into the budget object every call site consumes."""
    return ModelBudget(tier=ModelTier(tier))


def _text_of(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        return str(part.get("content") or part.get("text") or "")
    content = getattr(part, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        return " ".join(_text_of(item) for item in content)
    return str(content)


def estimate_text_tokens(text: str) -> int:
    """Deterministic estimate: one token per CJK character, one per four latin characters.

    Deliberately not a real tokenizer -- the local server owns the true count, and a
    private deployment must not spend a model round trip to size a timeout. The rule is
    pinned by a test, because changing it silently would change every budget at once.
    """
    if not text:
        return 0
    cjk = sum(1 for char in text if any(low <= ord(char) <= high for low, high in _CJK_RANGES))
    return int(math.ceil(cjk + (len(text) - cjk) / 4.0))


def estimate_prompt_tokens(prompt: Any) -> int | None:
    """Prompt size in tokens, or ``None`` when the caller has no prompt yet.

    ``None`` is a real answer: it means "size unknown", and the budget then plans against
    that tier's largest permitted prompt rather than pretending the call is cheap.
    """
    if prompt is None:
        return None
    if isinstance(prompt, str):
        return estimate_text_tokens(prompt)
    if isinstance(prompt, dict):
        return estimate_text_tokens(_text_of(prompt)) + MESSAGE_OVERHEAD_TOKENS
    total = 0
    for message in prompt:
        total += estimate_text_tokens(_text_of(message)) + MESSAGE_OVERHEAD_TOKENS
    return total


def _finish_reason(response: Any) -> str:
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        for key in ("finish_reason", "done_reason"):
            value = str(metadata.get(key) or "").strip().lower()
            if value:
                return value
    choices = getattr(response, "choices", None)
    for choice in choices or []:
        if isinstance(choice, dict):
            return str(choice.get("finish_reason") or "").strip().lower()
        return str(getattr(choice, "finish_reason", "") or "").strip().lower()
    return ""


def detect_output_truncation(response: Any) -> str | None:
    """Stable code for "the answer stopped at its length cap", or None when it did not.

    ``finish_reason == "length"`` is the only honest evidence available without a
    tokenizer: it says the server stopped writing because of a limit, which is what an
    ``n_ctx`` collision looks like from the client side.
    """
    if _finish_reason(response) == "length":
        return OUTPUT_TRUNCATED_CODE
    return None


def context_error_code(exc: BaseException) -> str | None:
    """Stable code when the provider itself refused the request for being too long."""
    text = str(exc).lower()
    return CONTEXT_LIMIT_CODE if any(fragment in text for fragment in CONTEXT_ERROR_FRAGMENTS) else None


def budget_signal(
    tier: ModelTier | str,
    *,
    prompt_tokens: int | None,
    read_seconds: float,
    code: str | None = None,
    clamped: bool | None = None,
    stream: bool | None = None,
    max_tokens: int | None = None,
    declared_max_tokens: int | None = None,
    affordable_max_tokens: int | None = None,
    min_answer_tokens: int | None = None,
    clamp_basis: str = "",
    verdict: str = "",
) -> str:
    """The one line format every budget verdict is logged as, marker included.

    One formatter keeps ``[ModelBudget]`` and ``error_code=`` stable, so the guard is
    findable in a customer log by one grep and assertable in a test by one literal.

    The four token fields appear only on a clock verdict, and they answer the question an
    operator actually has after ``clamped=yes``: what was asked, what is being sent, what the
    clock could pay for, and which configured numbers made that decision. Without them a
    clamp is indistinguishable from a tier cap someone chose on purpose.

    ``clamped=`` means one thing only: this call is writing less than its tier asked. The
    companion ``budget_verdict=`` names which finding a line is, because the two families the
    marker covers used to share the word -- a ceiling that shortened an answer and a ceiling
    that cannot be honoured at any cap worth answering with are different incidents, and an
    operator greps ``clamped=yes`` to find the first one.

    ``thinking=`` rides on every line, not only on a clamp, because on the compatible leg it
    decides what an output cap buys at all: §42 measured the same prompt at the same
    ``max_tokens=1536`` returning 0 characters with ``finish_reason=length`` with thinking on
    and 93 characters with ``finish_reason=stop`` with it off. An operator reading
    ``empty_answer_rejected`` therefore has to be able to tell "we asked it to think and it
    starved" from "we asked it not to and it still starved" without opening an env file, and
    the two must not be able to share a count without saying which one is being counted.
    """
    parts = [
        MODEL_BUDGET_MARKER,
        f"tier={ModelTier(tier).value}",
        f"thinking={model_thinking_mode()}",
        f"prompt_tokens={prompt_tokens if prompt_tokens is not None else 'unknown'}",
        f"read_seconds={read_seconds:.1f}",
    ]
    if stream is not None:
        parts.append(f"stream={'yes' if stream else 'no'}")
    if clamped is not None:
        parts.append(f"clamped={'yes' if clamped else 'no'}")
    if verdict:
        parts.append(f"budget_verdict={verdict}")
    if declared_max_tokens is not None:
        parts.append(f"declared_max_tokens={declared_max_tokens}")
    if max_tokens is not None:
        parts.append(f"max_tokens={max_tokens}")
    if affordable_max_tokens is not None:
        parts.append(f"affordable_max_tokens={affordable_max_tokens}")
    if min_answer_tokens is not None:
        parts.append(f"min_answer_tokens={min_answer_tokens}")
    if clamp_basis:
        parts.append(f"clamp_basis={clamp_basis}")
    if code:
        parts.append(f"error_code={code}")
    return " ".join(parts)


@dataclass(frozen=True)
class MaxTokensVerdict:
    """What one call may write, and the arithmetic that says so.

    Carried alongside the effective budget so a shortened answer can never be confused with
    a configured one: ``declared_max_tokens`` is what the tier asked for, ``max_tokens`` is
    what this call is actually allowed, and ``basis`` names the variables that decided it.
    """

    tier: ModelTier
    prompt_tokens: int | None
    stream: bool
    declared_max_tokens: int
    max_tokens: int
    affordable_max_tokens: int
    min_answer_tokens: int
    basis: str

    @property
    def clamped(self) -> bool:
        """True when this call writes less than its tier asked to."""
        return self.max_tokens < self.declared_max_tokens

    @property
    def unaffordable(self) -> bool:
        """True when the only clamp available would go below the floor, so there is none.

        This is the finding R99 was written for: on a machine calibrated to 8 tok/s the
        analysis tier needs 192 s for its own 1536 tokens, and shortening the answer to fit
        the 120 s ceiling is not a fix, because every cap under the measured thinking floor
        returns an empty body. The honest verdict is "this budget cannot hold this tier",
        said out loud -- not a smaller number that is known to produce nothing.
        """
        return (
            self.affordable_max_tokens < self.declared_max_tokens
            and self.affordable_max_tokens < self.min_answer_tokens
        )

    @property
    def verdict_word(self) -> str:
        """The one token that says which of the two clock findings this is."""
        if self.clamped:
            return "clamped"
        if self.unaffordable:
            return "budget_unaffordable"
        return "fits"

    def apply_to(self, budget: ModelBudget) -> ModelBudget:
        """Return the budget this call must actually be sized by; the same object if unchanged.

        A copy, never a write-back: ``app/agents/orchestrator.py`` builds one model object per
        graph at import time and shares it across every request, so a budget mutated in place
        would carry one question's clamp into the next, and two concurrent requests would
        clamp each other's baseline.
        """
        if self.max_tokens == int(budget.max_tokens):
            return budget
        sized = budget.model_copy(
            update={"max_tokens": self.max_tokens, "timeout_seconds": 0.0}
        )
        return sized.model_copy(
            update={
                "timeout_seconds": sized.read_timeout_seconds(
                    self.prompt_tokens, stream=self.stream
                )
            }
        )


def clamp_basis(budget: ModelBudget) -> str:
    """Every knob behind a clamp in one space-free field, with where each one came from.

    ``clamp_basis=MODEL_DECODE_TOKENS_PER_SECOND=8tok/s(calibrated-default)|...`` is what lets
    an operator tell "this machine is slow" from "someone set a number", which is the
    difference between recalibrating and arguing.
    """
    def part(name: str, value: float, unit: str = "") -> str:
        origin = "env" if _env_set(name) else "calibrated-default"
        return f"{name}={value:g}{unit}({origin})"

    return "|".join(
        [
            part("MODEL_DECODE_TOKENS_PER_SECOND", budget.decode_tokens_per_second, "tok/s"),
            part("MODEL_PREFILL_TOKENS_PER_SECOND", budget.prefill_tokens_per_second, "tok/s"),
            part("MODEL_REQUEST_TIMEOUT", budget.timeout_ceiling_seconds, "s"),
            part("MODEL_TIMEOUT_MARGIN", budget.timeout_margin),
            f"MODEL_MIN_ANSWER_TOKENS={min_answer_tokens()}tok"
            f"({'env' if _env_set('MODEL_MIN_ANSWER_TOKENS') else 'calibrated-default'})",
        ]
    )


def clock_affordable_tokens(
    budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False
) -> int:
    """How many output tokens the ceiling can pay for, given this prompt and these rates."""
    ceiling = float(budget.timeout_ceiling_seconds)
    margin = max(1.0, float(budget.timeout_margin))
    rate = max(0.1, float(budget.decode_tokens_per_second))
    if stream or prompt_tokens is None:
        # A stream is billed for a stall between chunks, not for the whole answer (see
        # contracts.py:STREAM_STALL_TOKENS), so the ceiling is not what binds it; and an
        # unmeasured prompt is a fact about the call site, not about the machine, which is
        # the same reasoning report_budget uses before it dares to say "clamped".
        return int(budget.max_tokens)
    spare_seconds = ceiling / margin - budget.prefill_seconds(prompt_tokens)
    return int(spare_seconds * rate)


def max_tokens_verdict(
    budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False
) -> MaxTokensVerdict:
    """Decide this call's output cap: shorten the answer to fit the clock, never below the floor."""
    declared = int(budget.max_tokens)
    affordable = clock_affordable_tokens(budget, prompt_tokens, stream=stream)
    floor = min_answer_tokens()
    if affordable >= declared:
        resolved = declared
    elif affordable < floor:
        # Refusing to shrink is the correct answer here, and it is not a silent one:
        # ``unaffordable`` is on the log line, on the span, and in the counter.
        resolved = declared
    else:
        resolved = max(affordable, floor)
    return MaxTokensVerdict(
        tier=ModelTier(budget.tier),
        prompt_tokens=prompt_tokens,
        stream=stream,
        declared_max_tokens=declared,
        max_tokens=int(min(resolved, declared)),
        affordable_max_tokens=affordable,
        min_answer_tokens=floor,
        basis=clamp_basis(budget),
    )


@dataclass(frozen=True)
class AuthorizedCall:
    """One call's sized budget plus the verdict that produced it, so a caller spends both."""

    budget: ModelBudget
    verdict: MaxTokensVerdict


def authorize(
    budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False
) -> AuthorizedCall:
    """Size one call: refuse what ``n_ctx`` cannot hold, then shorten what the clock cannot.

    The order is the whole judgement. The context check runs against the tier's *declared*
    cap, exactly as it always has, so clamping can never rescue a prompt that used to be
    refused -- the existing limit is not relaxed by one token. Only after that does the
    clock get its say, and it gets it about the answer, not about the deadline.
    """
    code = budget.context_window_code(prompt_tokens)
    if code:
        # One line, then the refusal: report_budget is the only formatter of this marker, and
        # a call that is about to be refused must not also be told to be clamped.
        report_budget(budget, prompt_tokens, stream=stream)
        raise ModelContextLimitExceeded(budget, prompt_tokens or 0)
    verdict = max_tokens_verdict(budget, prompt_tokens, stream=stream)
    effective = verdict.apply_to(budget)
    if verdict.clamped or verdict.unaffordable:
        record_budget_event("max_tokens_clamped" if verdict.clamped else "budget_unaffordable")
    report_budget(effective, prompt_tokens, stream=stream, verdict=verdict)
    return AuthorizedCall(budget=effective, verdict=verdict)


def authorize_budget(
    budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False
) -> ModelBudget:
    """``authorize`` for a caller that only needs the sized budget."""
    return authorize(budget, prompt_tokens, stream=stream).budget


def http_timeout(
    budget: ModelBudget, prompt_tokens: int | None = None, *, stream: bool = False
) -> httpx.Timeout:
    """Split the clock into the four things it actually measures.

    Only ``read`` waits for the model; connect/write/pool wait for a socket on a machine
    that is loopback by definition, so they stay short and constant. Handing httpx a scalar
    instead is what made every phase share the model's budget, which is the bug.
    """
    read = budget.read_timeout_seconds(prompt_tokens, stream=stream)
    return httpx.Timeout(
        read,
        connect=budget.connect_timeout_seconds,
        write=budget.connect_timeout_seconds,
        pool=budget.timeout_floor_seconds,
    )


def report_budget(
    budget: ModelBudget,
    prompt_tokens: int | None,
    *,
    stream: bool = False,
    verdict: MaxTokensVerdict | None = None,
) -> str | None:
    """Log one verdict line when this call is already outside its own budget, else stay quiet.

    Three separate reasons get the same marker, and each says which one it is. The window
    cannot hold the request (``error_code=context_limit_exceeded``); the ceiling shortened
    the tier's own answer (``clamped=yes budget_verdict=clamped``); or the ceiling cannot be
    honoured at any cap the model would answer with at all (``clamped=no
    budget_verdict=budget_unaffordable``, with ``max_tokens == declared_max_tokens`` -- the
    finding this function exists to make visible). The first is a customer-facing
    truncation, the second is a machine that is too slow for the tier as configured, and the
    third is a configuration that contradicts itself: analysis on a CPU-calibrated budget is
    exactly that case, and it announced itself as a clamp on every single call while sending
    the uncut cap anyway.
    """
    code = budget.context_window_code(prompt_tokens)
    # ``prompt_tokens is None`` means nobody measured it, which is a fact about the call
    # site, not about the machine: the clock for an unknown prompt is deliberately the
    # tier's worst case, so declaring it clamped on every construction would warn five
    # times at import and tell an operator nothing. Only a measured prompt can prove the
    # ceiling is what binds.
    ceiling_binds = prompt_tokens is not None and not budget.fits_within_timeout(
        prompt_tokens, stream=stream
    )
    clamped = bool(verdict.clamped) if verdict is not None else ceiling_binds
    verdict_word = ""
    if code:
        # A refusal on the window is its own finding and carries no clamp verdict: the
        # request never got as far as being sized, and this line keeps the exact shape it had
        # before the output cap was ever negotiated.
        clamped = ceiling_binds
    elif verdict is not None:
        if verdict.clamped:
            verdict_word = "clamped"
        elif verdict.unaffordable:
            verdict_word = "budget_unaffordable"
        elif ceiling_binds:
            verdict_word = "ceiling_binds"
    if not (code or clamped or verdict_word):
        return code
    logger.warning(
        budget_signal(
            budget.tier,
            prompt_tokens=prompt_tokens,
            read_seconds=budget.read_timeout_seconds(prompt_tokens, stream=stream),
            code=code,
            clamped=clamped,
            stream=stream,
            max_tokens=verdict.max_tokens if verdict else None,
            declared_max_tokens=verdict.declared_max_tokens if verdict else None,
            affordable_max_tokens=verdict.affordable_max_tokens if verdict else None,
            min_answer_tokens=verdict.min_answer_tokens if verdict else None,
            clamp_basis=verdict.basis if verdict else "",
            verdict=verdict_word,
        )
    )
    return code


def authorize_call(budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False) -> float:
    """Log this call's budget verdict, refuse it when ``n_ctx`` cannot hold it, return the clock.

    Returning the read budget rather than a bool keeps the call sites honest: they get the
    number they are about to spend and nothing else. The refusal happens before the request
    leaves the machine, which is the difference between a stable code and a completion that
    stops in the middle of a sentence and is still presented as an answer.

    A call site that also spends the *output cap* has to take :func:`authorize` (or
    :func:`authorize_budget`) instead: the cap this call is allowed may be shorter than the
    tier's, and reading it off ``budget`` after this function returns would read the
    un-clamped number.
    """
    authorized = authorize(budget, prompt_tokens, stream=stream)
    return authorized.budget.read_timeout_seconds(prompt_tokens, stream=stream)


def model_timeout_code(exc: BaseException | None) -> str | None:
    """``TIMEOUT_ERROR_CODE`` when this exception means the clock ran out, else ``None``.

    The chain is walked because the boundary sees the wrapper, not the cause: what
    ``app/agents/nodes.py`` catches around a provider call is an openai client error whose
    message is "Request timed out." around an httpx read timeout. Neither is a builtin
    ``TimeoutError``, so ``app/trace/spans.py:error_code_for`` files the whole family as
    ``internal_error`` and a 120-second outage becomes indistinguishable from a typo in a
    prompt template. Class names are matched over the cause chain; message fragments are
    matched over the whole chain in one pass, because the useful text is often one up.
    """
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and len(chain) < 10:
        if type(current).__name__ in TIMEOUT_ERROR_TYPE_NAMES:
            return TIMEOUT_ERROR_CODE
        chain.append(current)
        current = current.__cause__ or current.__context__
    text = " ".join(str(item).lower() for item in chain)
    return TIMEOUT_ERROR_CODE if any(fragment in text for fragment in TIMEOUT_ERROR_FRAGMENTS) else None


def answer_text(response: Any) -> str:
    """The visible text of a completion, with no reasoning content and no whitespace padding.

    Deliberately *visible* text only. A thinking model that spent its whole cap on a hidden
    chain of thought has an answer of zero characters here even though the server counts
    hundreds of generated tokens, and that is the case this function exists to catch.
    """
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(part for part in (_text_of(item) for item in content) if part).strip()
    return _text_of(content).strip()


def produced_a_tool_call(response: Any) -> bool:
    """True when a response with no visible text still did something: it asked for a tool.

    Without this the emptiness guard would fire on every react-agent dispatch, because a tool
    call is exactly that -- no characters, plenty of intent -- and a signal that screams at
    every step of a worker graph is a signal that gets muted.
    """
    if getattr(response, "tool_calls", None) or getattr(response, "tool_call_chunks", None):
        return True
    content = getattr(response, "content", None)
    if isinstance(content, list):
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if str(kind or "") in {"tool_use", "server_tool_use", "tool_call", "tool_result"}:
                return True
    return False


def detect_empty_answer(response: Any) -> str | None:
    """Stable code for "the model answered, and the answer is nothing", or ``None``.

    ``no_answer_produced`` is the ratified code for exactly this, and it is already what
    ``app/api/v1/chat.py`` emits when a round produces no text at all -- this only makes the
    model boundary say it *first*, at the moment it knows, instead of letting an empty
    completion travel onwards as if it were a reply.
    """
    if produced_a_tool_call(response):
        return None
    return NO_ANSWER_CODE if not answer_text(response) else None


# ==================== what this boundary has had to say about itself ====================

#: Ratified in app/agents/contracts.py:ErrorEnvelope and already emitted by
#: app/api/v1/chat.py for the same fact one layer up: this round produced no conclusion.
NO_ANSWER_CODE = "no_answer_produced"

#: Every countable verdict the budget boundary records. The names are the report keys, so a
#: new one has to be written down here before it can be counted, and cannot be invented at a
#: call site.
BUDGET_EVENT_NAMES = (
    "max_tokens_clamped",
    "budget_unaffordable",
    "timeout_offline_reply",
    "empty_answer_rejected",
)

_budget_events: dict[str, int] = {name: 0 for name in BUDGET_EVENT_NAMES}
_budget_event_lock = threading.Lock()


def record_budget_event(name: str) -> int:
    """Count one budget verdict and return the new total for that name.

    Counting is not logging: a warning line proves one call, while a counter is what an
    operator needs to answer "how many of today's requests were this?". The lock is cheap
    and unconditional because the process-wide model budget already allows several slots.
    An unknown name is a programming error and raises, so a typo cannot create a counter
    nobody declared.
    """
    if name not in _budget_events:
        raise KeyError(f"undeclared budget event: {name}")
    with _budget_event_lock:
        _budget_events[name] += 1
        return _budget_events[name]


def budget_event_counts() -> dict[str, int]:
    """A copy of the counts, so a reader cannot mutate the ledger it is looking at."""
    with _budget_event_lock:
        return dict(_budget_events)


def reset_budget_events() -> None:
    """Zero every count. Test seam, and the reason the ledger is a dict of names."""
    with _budget_event_lock:
        for name in BUDGET_EVENT_NAMES:
            _budget_events[name] = 0


def model_budget_readout() -> dict[str, Any]:
    """The budget boundary's own in-process state, ready for a health surface to embed.

    Shaped like ``app/rag/hot_index.py:hot_index_snapshot`` on purpose: read-only, in-memory,
    opens no socket, never reads the vector store, and returns a dict a caller can embed
    verbatim. It is embedded: ``app/common/monitoring.py:build_health_snapshot`` publishes
    it as the ``model_budget`` key next to ``hot_index``, through the same
    ``_subsystem_state`` accessor the storage subsystems use -- so there is no second copy
    of these numbers for an operator to be misled by, and a failing probe degrades to
    ``unavailable`` instead of breaking the health request. R99 判据 4 asked for the readout
    to be reachable from a health response rather than only from a log line; that wiring
    landed after R100 (跟进单 §42.3) and is pinned by
    tests/test_r99_budget_selfconsistency.py.
    

"""
    profile = tier_profile(ModelTier.ANALYSIS)
    thinking = resolve_model_thinking()
    return {
        "events": budget_event_counts(),
        "thinking": {
            "mode": thinking.mode,
            #: Whether a ``thinking`` field is going on the wire at all. ``enabled`` sends no
            #: field, which is the pre-R100 body, so "not sent" is a fact an operator needs
            #: separately from the mode word.
            "request_field_sent": bool(thinking.wire),
            "request_field": THINKING_REQUEST_FIELD if thinking.wire else "",
            "accepted_values": list(MODEL_THINKING_MODES),
            "provenance": "env"
            if os.environ.get(MODEL_THINKING_ENV) is not None
            else "calibrated-default",
            "note": thinking.note,
        },
        "throughput_tokens_per_second": {
            "prefill": profile["prefill_tokens_per_second"],
            "decode": profile["decode_tokens_per_second"],
        },
        "throughput_provenance": {
            "MODEL_PREFILL_TOKENS_PER_SECOND": "env"
            if _env_set("MODEL_PREFILL_TOKENS_PER_SECOND")
            else "calibrated-default",
            "MODEL_DECODE_TOKENS_PER_SECOND": "env"
            if _env_set("MODEL_DECODE_TOKENS_PER_SECOND")
            else "calibrated-default",
            "MODEL_MIN_ANSWER_TOKENS": "env"
            if _env_set("MODEL_MIN_ANSWER_TOKENS")
            else "calibrated-default",
        },
        "request_timeout_ceiling_seconds": profile["timeout_ceiling_seconds"],
        "context_limit_tokens": profile["context_limit_tokens"],
        "min_answer_tokens": min_answer_tokens(),
        "tiers": {
            tier.value: {
                "declared_max_tokens": int(budget.max_tokens),
                "fits_ceiling": budget.fits_within_timeout(0, stream=False),
                "affordable_max_tokens": clock_affordable_tokens(budget, 0),
            }
            for tier, budget in ((tier, model_tier_budget(tier)) for tier in ModelTier)
        },
    }
