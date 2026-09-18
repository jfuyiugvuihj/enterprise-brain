"""Machine-wide budget for the single local model server.

A private deployment runs one local model on the customer machine. Every boundary
that invokes that model must share one budget so a 14B model cannot be called
without limit. ``wait_seconds`` keeps legitimate parallel workers queueing instead
of stampeding the model; a zero wait preserves the previous non-blocking behavior.

The other half of that budget is tokens and clock, and it is per tier: a greeting, a
memory summary and a long analysis answer must not share one output cap or one timeout.
``tier_profile`` / ``model_tier_budget`` below read that configuration, and
``app/agents/contracts.py:ModelBudget`` is the object they fill in.
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

#: Measured on the delivery baseline (CPU-only qwen3.5:9b through Ollama, 2026-09-16):
#: prefill 35.2 tok/s, decode 8.18 tok/s. The defaults round down to the pessimistic
#: integer, because a rate that is too optimistic is exactly the cut-off-mid-answer bug
#: this section exists to remove.
DEFAULT_PREFILL_TOKENS_PER_SECOND = 35.0
DEFAULT_DECODE_TOKENS_PER_SECOND = 8.0
DEFAULT_TIMEOUT_MARGIN = 1.15
DEFAULT_TIMEOUT_FLOOR_SECONDS = 10.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
#: ``MODEL_REQUEST_TIMEOUT`` is the ceiling for one request. Read it only through
#: :func:`request_timeout_ceiling_seconds`, so no second module can keep its own default.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_CONTEXT_TOKENS = 4096

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

#: Fragments a local server uses when it refuses a request for being too long.
CONTEXT_ERROR_FRAGMENTS = (
    "context length",
    "context_length",
    "maximum context",
    "n_ctx",
    "too many tokens",
    "prompt is too long",
)


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "") or "").strip()
    try:
        value = float(raw) if raw else float(default)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


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
) -> str:
    """The one line format every budget verdict is logged as, marker included.

    One formatter keeps ``[ModelBudget]`` and ``error_code=`` stable, so the guard is
    findable in a customer log by one grep and assertable in a test by one literal.
    """
    parts = [
        MODEL_BUDGET_MARKER,
        f"tier={ModelTier(tier).value}",
        f"prompt_tokens={prompt_tokens if prompt_tokens is not None else 'unknown'}",
        f"read_seconds={read_seconds:.1f}",
    ]
    if stream is not None:
        parts.append(f"stream={'yes' if stream else 'no'}")
    if clamped is not None:
        parts.append(f"clamped={'yes' if clamped else 'no'}")
    if code:
        parts.append(f"error_code={code}")
    return " ".join(parts)


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


def report_budget(budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False) -> str | None:
    """Log one verdict line when this call is already outside its own budget, else stay quiet.

    Two separate reasons get the same marker: the window cannot hold the request
    (``context_limit_exceeded``) and the ceiling had to shorten the tier's own honest
    estimate (``clamped=yes``). The first is a customer-facing truncation; the second says
    the machine is too slow for the tier as configured, which is an operator finding.
    """
    code = budget.context_window_code(prompt_tokens)
    # ``prompt_tokens is None`` means nobody measured it, which is a fact about the call
    # site, not about the machine: the clock for an unknown prompt is deliberately the
    # tier's worst case, so declaring it clamped on every construction would warn five
    # times at import and tell an operator nothing. Only a measured prompt can prove the
    # ceiling is what binds.
    clamped = prompt_tokens is not None and not budget.fits_within_timeout(
        prompt_tokens, stream=stream
    )
    if code or clamped:
        logger.warning(
            budget_signal(
                budget.tier,
                prompt_tokens=prompt_tokens,
                read_seconds=budget.read_timeout_seconds(prompt_tokens, stream=stream),
                code=code,
                clamped=clamped,
                stream=stream,
            )
        )
    return code


def authorize_call(budget: ModelBudget, prompt_tokens: int | None, *, stream: bool = False) -> float:
    """Log this call's budget verdict, then refuse it when ``n_ctx`` cannot hold it.

    Returning the read budget rather than a bool keeps the call sites honest: they get the
    number they are about to spend and nothing else. The refusal happens before the request
    leaves the machine, which is the difference between a stable code and a completion that
    stops in the middle of a sentence and is still presented as an answer.
    """
    code = report_budget(budget, prompt_tokens, stream=stream)
    if code:
        raise ModelContextLimitExceeded(budget, prompt_tokens or 0)
    return budget.read_timeout_seconds(prompt_tokens, stream=stream)
