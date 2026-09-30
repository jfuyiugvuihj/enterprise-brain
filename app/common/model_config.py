"""Local model routing configuration: the endpoint, the model, and how long a
call asks the model server to hold that model in memory.

The first version only manages a model that lives on the customer's own machine. The
model name is either configured explicitly or discovered from the local Ollama registry;
it is never invented, because a fabricated name would advertise a model that may not be
installed.
"""
from dataclasses import dataclass
import json
import os
import re
import time
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

if TYPE_CHECKING:  # pragma: no cover - 只为类型与静态读数存在,运行时永不导入
    #: ``check_context_pairing`` 交回的那一枚读数对象。它在 app/agents/contracts.py,而本模块
    #: 是更早被导入的那一端,所以运行时的导入留在函数里(见下面的闸本体),这里只给类型与读数用。
    from app.agents.contracts import ContextPairing

_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_DISCOVERY_CACHE: tuple[float, str, str] | None = None
#: The last inference-compute verdict a probe produced, as a plain dict. Reading it back
#: never opens a socket, so /health/details can answer "gpu | cpu | unknown" cheaply.
_COMPUTE_CACHE: dict | None = None

#: Per-request model residency (R34). A cold load on the delivery machine measures ~6.1 s of
#: Ollama's own ``load_duration``, so every question that arrives after the model has been
#: dropped pays it again. This is the client half of the answer: the window a request asks
#: the server to keep the model warm for. An unset variable is deliberately *not* a feature
#: switch -- it spells Ollama's own default below, so "nobody said anything" and "the
#: default" cannot come to mean two different things on the wire.
KEEP_ALIVE_ENV = "LOCAL_MODEL_KEEP_ALIVE"
DEFAULT_KEEP_ALIVE_SECONDS = 5 * 60
#: The most residency this boundary will ask for, however the variable is written. One chat
#: model here holds ~5.3 GB of the customer's own memory (measured 09-19), and a private
#: deployment must not be left holding it because somebody typed a big number: a forgotten
#: browser tab is worth less than the machine. Tuning down is free, tuning up is free up to
#: this ceiling, and past it the request is clamped and says so out loud. Policy write-up:
#: docs/handoff/2026-09-19-r34-keep-alive-residency.md.
KEEP_ALIVE_CEILING_SECONDS = 30 * 60
#: Every way of saying "never give the memory back". Ollama's own spelling is ``-1``, which
#: pins the model until the server restarts, and that one request field is the difference
#: between a warm cache and a laptop out of memory at three in the morning.
NEVER_UNLOAD_SPELLINGS = frozenset({"infinite", "infinity", "never", "forever", "permanent"})
_KEEP_ALIVE_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
#: A duration is either a bare number -- seconds, which is how the server documents it -- or
#: one or more amount+unit pairs, so ``90s``, ``10m`` and ``1h30m`` all mean what they say.
#: Anything else is noise, and noise gets the default rather than a guess.
_KEEP_ALIVE_PART = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)")


@dataclass(frozen=True)
class KeepAlivePolicy:
    """The residency one call asks for, plus an honest note about how it got that number.

    ``note`` exists because a silent clamp is the worst kind of configuration: an operator
    who writes ``2h`` and gets thirty minutes has to be able to learn that from one log line,
    and the caller that logs it must not re-derive the reason.
    """

    seconds: int
    #: What the server receives: a canonical ``"<n>s"`` duration string, never a number of
    #: nanoseconds and never ``-1``.
    wire: str
    note: str = ""


def parse_keep_alive_seconds(value: str) -> float | None:
    """Seconds in a duration string; ``-1.0`` for a never-unload spelling; ``None`` for noise.

    A negative is not a smaller window, it is a different feature: Ollama reads ``-1`` as
    "never unload". Mapping every way of saying that onto ``-1.0`` keeps the refusal in one
    place instead of scattered through each caller's arithmetic.
    """
    text = (value or "").strip().lower()
    if not text:
        return None
    if text.startswith("-") or text in NEVER_UNLOAD_SPELLINGS:
        return -1.0
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    compact = text.replace(" ", "")
    parts = _KEEP_ALIVE_PART.findall(compact)
    if not parts or "".join(f"{amount}{unit}" for amount, unit in parts) != compact:
        return None
    return sum(float(amount) * _KEEP_ALIVE_UNITS[unit] for amount, unit in parts)


def resolve_keep_alive(raw: str | None = None) -> KeepAlivePolicy:
    """The bounded residency window to ask the local model server for, resolved once.

    Three inputs are refused and each one keeps serving instead of failing the request: a
    value that is not a duration, a value above the ceiling, and any value that means
    "unload only when the server restarts". The last is a red line rather than a preference
    -- this is a machine the customer owns, and the memory behind one chat model is not ours
    to reserve indefinitely.

    ``raw`` is the test seam: with no argument the value comes from the environment. Whatever
    comes back satisfies ``0 <= seconds <= KEEP_ALIVE_CEILING_SECONDS``.
    """
    value = ((os.environ.get(KEEP_ALIVE_ENV) if raw is None else raw) or "").strip()
    seconds = parse_keep_alive_seconds(value)
    if seconds is None:
        note = f"忽略无法识别的 {KEEP_ALIVE_ENV}={value!r}，按默认值常驻" if value else ""
        return KeepAlivePolicy(DEFAULT_KEEP_ALIVE_SECONDS, f"{DEFAULT_KEEP_ALIVE_SECONDS}s", note)
    if seconds < 0:
        return KeepAlivePolicy(
            KEEP_ALIVE_CEILING_SECONDS,
            f"{KEEP_ALIVE_CEILING_SECONDS}s",
            f"拒绝永不卸载的 {KEEP_ALIVE_ENV}={value!r}，按上限 {KEEP_ALIVE_CEILING_SECONDS}s 常驻",
        )
    asked = int(seconds)
    bounded = min(asked, KEEP_ALIVE_CEILING_SECONDS)
    note = (
        ""
        if bounded == asked
        else f"{KEEP_ALIVE_ENV}={value!r} 超过上限，按 {KEEP_ALIVE_CEILING_SECONDS}s 截断"
    )
    return KeepAlivePolicy(bounded, f"{bounded}s", note)


@dataclass(frozen=True)
class LocalModelSettings:
    base_url: str
    model_name: str
    api_key: str
    model_source: str = "none"


def _normalize_base_url(value: str) -> str:
    base_url = (value or "").strip().rstrip("/")
    if not base_url:
        base_url = _DEFAULT_OLLAMA_BASE_URL

    parsed = urlsplit(base_url)
    if parsed.hostname in {"localhost", "::1"}:
        netloc = f"127.0.0.1:{parsed.port}" if parsed.port else "127.0.0.1"
        base_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    if not base_url.endswith("/v1"):
        base_url += "/v1"
    return base_url


def _native_base_url(base_url: str) -> str:
    """Ollama's registry API is served without the OpenAI-compatible /v1 suffix."""
    trimmed = (base_url or "").strip().rstrip("/")
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return trimmed or _DEFAULT_OLLAMA_BASE_URL


def _fetch_registry(url: str) -> dict:
    timeout = float(os.getenv("OLLAMA_DISCOVERY_TIMEOUT_SECONDS", "1.5"))
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_chat_model(
    base_url: str,
    *,
    fetch: Callable[[str], dict] | None = None,
    compute_fetch: Callable[[str], dict] | None = None,
) -> str:
    """Return the first chat-capable model registered locally, or an empty string.

    ``compute_fetch`` opts this call into the R26 inference-compute probe. Left as
    ``None`` the request set stays exactly ``/api/tags``, which is what the discovery
    tests pin; production passes the same registry transport (see ``_cached_discovery``)
    so a machine that is not using its GPU becomes observable. ``OLLAMA_REQUIRE_GPU``
    decides whether a *confirmed* CPU fallback refuses to serve; unset keeps today.
    """
    from app.common.model_capabilities import discover_ollama_models

    result = discover_ollama_models(
        fetch or _fetch_registry,
        base_url,
        compute_fetch=compute_fetch,
    )
    _record_inference_compute(base_url, result)
    if not result.available:
        return ""
    try:
        candidates = result.for_purpose("chat")
    except ValueError:
        return ""
    return candidates[0].name if candidates else ""


def _cached_discovery(base_url: str) -> str:
    """Cache discovery so repeated graph construction cannot stampede the local model."""
    global _DISCOVERY_CACHE
    ttl = float(os.getenv("OLLAMA_DISCOVERY_TTL_SECONDS", "60"))
    now = time.monotonic()
    cache = _DISCOVERY_CACHE
    if cache is not None and cache[2] == base_url and now - cache[0] < ttl:
        return cache[1]
    discovered = discover_chat_model(base_url, compute_fetch=_fetch_registry)
    _DISCOVERY_CACHE = (now, discovered, base_url)
    return discovered


def reset_model_discovery_cache() -> None:
    global _DISCOVERY_CACHE
    _DISCOVERY_CACHE = None


def _record_inference_compute(base_url: str, result) -> None:
    """Remember the verdict a probe produced; a call without a probe records nothing."""
    global _COMPUTE_CACHE
    compute = result.inference
    if compute is None:
        return
    _COMPUTE_CACHE = {
        "kind": compute.kind,
        "detail": compute.detail,
        "error_code": compute.error_code,
        "observed_at": time.time(),
        "observed_from": base_url,
    }


def reset_inference_compute_cache() -> None:
    global _COMPUTE_CACHE
    _COMPUTE_CACHE = None


def inference_compute_state(now: float | None = None) -> dict:
    """The last observed verdict, or ``unknown`` when nobody has looked yet.

    Reading never opens a socket, and "not probed" is reported as ``unknown`` instead of
    either end of the GPU/CPU claim.
    """
    from app.common.model_capabilities import COMPUTE_UNKNOWN

    if _COMPUTE_CACHE is None:
        return {
            "kind": COMPUTE_UNKNOWN,
            "detail": "not_probed",
            "error_code": None,
            "observed_at": None,
            "age_seconds": None,
        }
    state = dict(_COMPUTE_CACHE)
    observed = state.get("observed_at")
    state["age_seconds"] = (
        round(max(0.0, (time.time() if now is None else now) - float(observed)), 3)
        if observed
        else None
    )
    return state


#: ==================== R535: the runtime half of the context-window pair ==================
#:
#: The declared half of this pair is already read in exactly one place
#: (``MODEL_CONTEXT_TOKENS`` through ``app.common.model_budget.context_limit_tokens``). The
#: other half belongs to the model server, and three facts decide how it can be read here:
#:
#: * This product puts no ``num_ctx`` in any request payload -- the native leg sends
#:   ``options.num_predict`` (``app/common/model_handler.py``) and the compatible leg sends
#:   ``max_tokens`` (``app/agents/nodes.py``) -- so the window a request is served inside is
#:   the server's own default, and no client-side edit of ours changes it.
#: * A resident model reports the window it was loaded with. ``/api/ps`` carries
#:   ``context_length``, measured on this host at ``docs/perf/raw/rate_all.jsonl`` line 2:
#:   ``{"ollama": "0.34.0", "loaded": [{"name": "qwen3.5:9b", "context_length": 4096,
#:   "size_vram": 0}]}`` -- read the same way by ``scripts/perf_probe_rate.py``.
#: * When the pair disagrees hard enough to matter the server says its number out loud:
#:   ``request (4402 tokens) exceeds the available context size (4096 tokens)``
#:   (``docs/perf/raw/rate_prefill.jsonl``). Harvesting that costs no extra request, because
#:   the collision is already on the wire.
#:
#: The shape follows the compute verdict above: an observation is *recorded* on a path that
#: already talks to the registry and *read* from a cache, so a health poll never stampedes the
#: model server. Absence stays absence -- ``/api/ps`` with nothing resident is "not observed",
#: never zero, and never agreement.
RUNTIME_WINDOW_PROBE_SUFFIX = "/api/ps"
#: How stale one resident reading may get before another request is worth sending. Deliberately
#: a constant and not an environment variable: R535 judgement (4) forbids this ticket from
#: minting a knob, and the discovery path this rides already throttles at
#: ``OLLAMA_DISCOVERY_TTL_SECONDS``.
RUNTIME_WINDOW_TTL_SECONDS = 60.0
_RUNTIME_WINDOW_CACHE: dict | None = None
#: Wall-clock half of the record (for the log), and the monotonic half (for the throttle): the
#: two keep the same clocks the discovery and compute caches above already keep.
_RUNTIME_WINDOW_PROBE_AT: float | None = None

#: The server's own words for "larger than what I loaded". Both ``n_ctx`` spellings require the
#: colon form on purpose: this product writes its own refusal as ``n_ctx=<required>``
#: (``app/common/model_budget.py``), so a pattern that accepted ``n_ctx=`` would read our own
#: claim back as the server's answer and poison the pairing with the very number that caused
#: the collision.
_RUNTIME_WINDOW_PATTERNS = (
    re.compile(r"available context size \(?(\d+)", re.IGNORECASE),
    re.compile(r'n_ctx\\?"\s*:\s*(\d+)'),
)


def runtime_window_from_ps_payload(payload: dict | None) -> int | None:
    """The widest window any resident model reports, or ``None`` when none does.

    The widest, not the first: with two models loaded the guard's claim has to hold for the
    leg that could actually serve it, and reporting a narrower window than the server holds
    would dress up an ``env_above_runtime`` verdict that does not exist. An empty list is
    "nothing resident", not "the server has no window", so it returns ``None``.
    """
    if not isinstance(payload, dict):
        return None
    widths = []
    for model in payload.get("models") or []:
        if not isinstance(model, dict):
            continue
        value = model.get("context_length")
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value > 0:
            widths.append(value)
    return max(widths) if widths else None


def runtime_window_from_refusal(text: str) -> int | None:
    """The number the server named when it refused a request for being too long.

    Takes the provider's own answer and returns only the integer in it. That filter is also
    the reason this may run on a path that must never copy a customer document into a log: an
    int cannot carry content, and nothing here keeps the string it read.
    """
    if not text:
        return None
    for pattern in _RUNTIME_WINDOW_PATTERNS:
        found = pattern.search(text)
        if found:
            value = int(found.group(1))
            if value > 0:
                return value
    return None


def record_runtime_context_window(tokens: int | None, *, source: str, observed_from: str = "") -> None:
    """Remember one observation of the served window. Fresh evidence wins; absence is recorded
    as absence, which the pairing gate then refuses to read as agreement."""
    global _RUNTIME_WINDOW_CACHE
    _RUNTIME_WINDOW_CACHE = {
        "tokens": int(tokens) if tokens else None,
        "source": source,
        "observed_from": observed_from,
        "observed_at": time.time(),
    }


def reset_runtime_context_window() -> None:
    """Forget every observation of the served window: the test seam, and the operator's way to
    make the process look again without restarting it."""
    global _RUNTIME_WINDOW_CACHE, _RUNTIME_WINDOW_PROBE_AT
    _RUNTIME_WINDOW_CACHE = None
    _RUNTIME_WINDOW_PROBE_AT = None


def runtime_context_window_state(now: float | None = None) -> dict:
    """The last observed served window. Reading this never opens a socket.

    Mirrors :func:`inference_compute_state` on purpose: "not probed" is reported as its own
    shape rather than borrowed from either end of the claim, because a deployment that has not
    looked yet is not a deployment whose server is narrow.
    """
    if _RUNTIME_WINDOW_CACHE is None:
        return {
            "tokens": None,
            "source": "",
            "observed_from": "",
            "observed_at": None,
            "age_seconds": None,
            "detail": "not_probed",
        }
    state = dict(_RUNTIME_WINDOW_CACHE)
    observed = state.get("observed_at")
    state["age_seconds"] = (
        round(max(0.0, (time.time() if now is None else float(now)) - float(observed)), 3)
        if observed
        else None
    )
    state.setdefault("detail", "observed" if state.get("tokens") else "unobserved")
    return state


def observe_runtime_context_window(
    base_url: str,
    *,
    fetch=None,
    now: float | None = None,
    force: bool = False,
) -> dict:
    """Ask the model server what window it is serving, through the transport already here.

    Never raises. This rides the startup path, and a self-check that can stop the service from
    building its own graph would be a second bug, not a fix; an unreachable or unresponsive
    registry leaves the reading absent, which the gate below reports as ``runtime_unread``.
    """
    global _RUNTIME_WINDOW_PROBE_AT
    moment = time.monotonic() if now is None else float(now)
    if not force and _RUNTIME_WINDOW_PROBE_AT is not None:
        if moment - _RUNTIME_WINDOW_PROBE_AT < RUNTIME_WINDOW_TTL_SECONDS:
            return runtime_context_window_state()
    _RUNTIME_WINDOW_PROBE_AT = moment
    url = _native_base_url(base_url) + RUNTIME_WINDOW_PROBE_SUFFIX
    try:
        payload = (fetch or _fetch_registry)(url)
    except Exception as exc:  # noqa: BLE001 - absent beats wrong, and beats taking the service down
        record_runtime_context_window(None, source=f"probe_failed:{type(exc).__name__}")
        return runtime_context_window_state()
    tokens = runtime_window_from_ps_payload(payload)
    if tokens is None:
        cached = _RUNTIME_WINDOW_CACHE or {}
        if cached.get("tokens"):
            # Nothing resident right now does not invalidate a window this process already saw.
            # The alternative is a gate that forgets the server's number the moment its
            # keep_alive window closes -- which is exactly when an operator is reading the log.
            return runtime_context_window_state()
        record_runtime_context_window(None, source="no_resident_model")
        return runtime_context_window_state()
    record_runtime_context_window(tokens, source=RUNTIME_WINDOW_PROBE_SUFFIX.lstrip("/"))
    return runtime_context_window_state()


def check_context_pairing(*, tier=None, budget=None, now: float | None = None) -> "ContextPairing":
    """THE pairing gate (R535 judgement 2): both window readings in one call, one verdict.

    The declared half comes from ``window_plan``, which is already the one object reading the
    window, the clock and the queue together -- this gate quotes it rather than keeping a
    second copy of any of those numbers. The served half comes from
    :func:`runtime_context_window_state`, which opens no socket, so anything on a readiness
    path can call this as often as it likes.

    It answers both directions the ticket asks about: a claim wider than the server can hold
    (``env_above_runtime`` -- 不配套, and the side that turns a free refusal into a burned
    round trip) and a claim far narrower than the server (``runtime_above_env`` -- 白留着容量,
    the side a customer with real-sized documents actually hits). Neither reading is a
    judgement about which number an operator should pick; raising a default is a deployment
    decision, and this ticket changes none of them.
    """
    from app.agents.contracts import evaluate_context_pairing
    from app.common.model_budget import window_plan

    plan = window_plan(budget if budget is not None else tier)
    state = runtime_context_window_state(now=now)
    return evaluate_context_pairing(
        declared_window_tokens=plan.context_limit_tokens,
        runtime_window_tokens=state.get("tokens"),
        declared_window_source=plan.context_limit_source,
        runtime_window_source=state.get("source") or state.get("detail") or "not_probed",
        tier=str(getattr(plan.tier, "value", plan.tier)),
        declared_max_tokens=plan.declared_max_tokens,
        min_answer_tokens=plan.min_answer_tokens,
        coherent_ceiling_tokens=plan.maximum_coherent_context_tokens,
    )


def get_local_model_settings(
    *,
    model_name: str | None = None,
    discover: Callable[[str], str] | None = None,
) -> LocalModelSettings:
    """Resolve the internal OpenAI-compatible endpoint and the model to use on it."""
    base_url = _normalize_base_url(
        os.getenv("LOCAL_MODEL_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or _DEFAULT_OLLAMA_BASE_URL
    )
    configured = (
        (os.getenv("LOCAL_MODEL_NAME") or "").strip() or (os.getenv("OLLAMA_MODEL") or "").strip()
    )
    if model_name is not None:
        resolved = model_name.strip()
        source = "configured" if resolved else "none"
    elif configured:
        resolved, source = configured, "configured"
    else:
        resolved = ((discover or _cached_discovery)(_native_base_url(base_url)) or "").strip()
        source = "discovered" if resolved else "none"
    return LocalModelSettings(
        base_url=base_url,
        model_name=resolved,
        api_key=os.getenv("LOCAL_MODEL_API_KEY", "local"),
        model_source=source,
    )