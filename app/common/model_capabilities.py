"""Offline-testable Ollama model discovery and conservative capability inference."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import os

from app.common.logger import logger


@dataclass(frozen=True)
class ModelCapabilities:
    name: str
    chat: bool = False
    embedding: bool = False
    tags: tuple[str, ...] = ()
    size_bytes: int | None = None
    parameter_size: str | None = None
    available: bool = True
    error_code: str | None = None
    error_message: str | None = None


def normalize_model_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("model name is required")
    return value


def infer_capabilities(model: dict[str, Any]) -> ModelCapabilities:
    name = normalize_model_name(str(model.get("name") or model.get("model") or ""))
    details = model.get("details") or {}
    family = " ".join(
        str(value).lower()
        for value in (name, details.get("family"), details.get("families"), details.get("format"))
        if value
    )
    embedding = any(token in family for token in ("embed", "bge", "e5", "gte"))
    chat = not embedding
    tags = tuple(str(tag) for tag in (model.get("tags") or details.get("families") or ()) if tag)
    return ModelCapabilities(
        name=name,
        chat=chat,
        embedding=embedding,
        tags=tags,
        size_bytes=model.get("size"),
        parameter_size=details.get("parameter_size"),
    )


@dataclass
class DiscoveryResult:
    models: list[ModelCapabilities] = field(default_factory=list)
    available: bool = True
    error_code: str | None = None
    error_message: str | None = None
    inference: InferenceCompute | None = None

    @property
    def compute(self) -> InferenceCompute:
        """An un-probed result is undetermined, which is deliberately not "on GPU"."""
        return self.inference if self.inference is not None else UNDETERMINED_COMPUTE

    @property
    def degraded_to_cpu(self) -> bool:
        return self.compute.degraded_to_cpu

    def for_purpose(self, purpose: str) -> list[ModelCapabilities]:
        if purpose == "chat":
            return [model for model in self.models if model.chat and model.available]
        if purpose in {"embedding", "embeddings"}:
            return [model for model in self.models if model.embedding and model.available]
        raise ValueError("unsupported model purpose")


def discover_ollama_models(
    fetch: Callable[[str], dict[str, Any]],
    base_url: str,
    *,
    compute_fetch: Callable[[str], dict[str, Any]] | None = None,
    require_gpu: bool | None = None,
) -> DiscoveryResult:
    """Discover from an injected transport; tests never contact a real Ollama server.

    ``compute_fetch`` opts into the inference-compute probe (``/api/ps`` plus
    ``/api/version``, both on the same injected transport). Left unset, discovery keeps
    its single original request, so no existing caller changes behaviour.
    """
    url = (base_url or "").rstrip("/") + "/api/tags"
    try:
        payload = fetch(url)
        models = [infer_capabilities(item) for item in (payload.get("models") or [])]
        result = DiscoveryResult(models=models)
    except Exception as exc:
        return DiscoveryResult(
            available=False,
            error_code="model_unavailable",
            error_message=str(exc),
        )
    if compute_fetch is None:
        return result
    return annotate_inference_compute(
        result,
        compute_fetch,
        base_url,
        require_gpu=require_gpu,
    )


# ---------------------------------------------------------------------------
# R26 - "GPU honesty": on what compute does inference actually run?
#
# Three verdicts, never two. A probe that cannot see the device answers
# ``unknown``; that answer is never laundered into "the GPU is in use" and never
# prosecuted as "CPU fallback". Only a confirmed CPU fallback carries a stable
# error code, and that code is an existing member of the closed vocabulary in
# app/agents/contracts.py -- this module does not get to invent new ones.
# ---------------------------------------------------------------------------

COMPUTE_GPU = "gpu"
COMPUTE_CPU = "cpu"
COMPUTE_UNKNOWN = "unknown"

#: Reused, not invented: contracts.py already enumerates ``model_unavailable`` and
#: evidence.py already treats it as retriable.
COMPUTE_DEGRADED_CODE = "model_unavailable"

#: Fail-open by default so today's behaviour cannot drift. When it is on, a confirmed
#: CPU fallback turns discovery into an unavailable result. See README.md.
REQUIRE_GPU_ENV = "OLLAMA_REQUIRE_GPU"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

# Keys Ollama uses to name the compute device. ``name`` is deliberately absent: in
# /api/ps that is the *model* name, and a model called "cpu-bench" must not be able
# to forge a verdict about the hardware.
_DEVICE_KEYS = ("device_type", "library", "processor", "provider", "compute", "device_id")
_VRAM_KEYS = ("size_vram", "vram_bytes")
_GPU_COUNT_KEYS = ("num_gpus", "gpu_count")
_GPU_TOKENS = ("gpu", "cuda", "nvidia", "rocm", "metal", "vulkan", "tpu")
_CPU_TOKENS = ("cpu",)

CPU_FALLBACK_MESSAGE = (
    "推理实际跑在 CPU 上，Ollama 未使用 GPU：容器已声明 NVIDIA 设备，但运行时没有拿到卡"
    "（驱动、nvidia-container-toolkit 或显存不足）。修好设备直通后重启 ollama 容器；"
    "确认接受 CPU 降级继续跑就把 OLLAMA_REQUIRE_GPU 设为 false。"
)

UNDETERMINED_MESSAGE = (
    "无法判定推理算力：Ollama 没有给出可用的设备信息。"
    "这个结论既不按「有 GPU」上报，也不按「CPU 降级」定罪。"
)


@dataclass(frozen=True)
class InferenceCompute:
    """One of exactly three verdicts about where Ollama runs inference."""

    kind: str = COMPUTE_UNKNOWN
    detail: str | None = None
    loaded_models: int = 0
    vram_bytes: int = 0
    error_code: str | None = None
    error_message: str | None = None

    @property
    def on_gpu(self) -> bool:
        return self.kind == COMPUTE_GPU

    @property
    def degraded_to_cpu(self) -> bool:
        return self.kind == COMPUTE_CPU

    @property
    def undetermined(self) -> bool:
        return self.kind == COMPUTE_UNKNOWN


UNDETERMINED_COMPUTE = InferenceCompute(detail="not_probed", error_message=UNDETERMINED_MESSAGE)


def require_gpu_enabled(explicit: bool | None = None) -> bool:
    """Resolve the hard-fail switch. Unset keeps today's warning-only behaviour."""
    if explicit is not None:
        return explicit
    return (os.getenv(REQUIRE_GPU_ENV) or "").strip().lower() in _TRUE_VALUES


# ---------------------------------------------------------------------------
# R673 - the fail-open default has to carry its own name on the log
#
# R26 ② says a machine that cannot get its card must say so with a stable code. That
# sentence is only judgeable in one of the two postures below, so the posture itself
# gets announced the first time a probe runs: an unset switch is a decision, not an
# absence. A latency number taken while the box answers from the CPU leg must never be
# readable afterwards as a GPU number, and neither announcement may launder the other.
# ---------------------------------------------------------------------------

POSTURE_FAIL_OPEN = "fail_open"
POSTURE_REQUIRE_GPU = "require_gpu"

#: One of these two lines is logged the first time a posture is seen by this process.
POSTURE_DECLARATION_FAIL_OPEN = (
    "R673 GPU 姿势声明：posture=fail_open（缺省放行）。"
    "这一形态不拦 CPU 腿：探测确证推理跑在 CPU 上时也只写一条告警、发现结果照旧可用，"
    "所以屏上那句答复可能是 CPU 腿给的。"
    "R26②「拿不到卡必须显式报错 + 稳定码」这一类判据在这种形态下不可判。"
)
POSTURE_DECLARATION_REQUIRE_GPU = (
    "R673 GPU 姿势声明：posture=require_gpu（硬门在位）。"
    "探测确证推理跑在 CPU 上时，发现结果就地 available=false 并带稳定码 "
    + COMPUTE_DEGRADED_CODE
    + "，不静默降级继续跑。R26② 类判据只在这种形态下可判。"
)

#: Emitted per detection, because the two postures conclude different things about
#: the same confirmed CPU leg. Both carry the probe reading that decided it.
CPU_LEG_DECLARATION = (
    "R673 确证 CPU 腿（fail_open）：此刻走的是 CPU 腿，硬门未架所以照旧服务，只是慢。"
    "本形态下测出的延迟数不得用于 R26②。"
)
HARD_REFUSAL_DECLARATION = (
    "R673 硬门触发（require_gpu）：确证 CPU 腿，发现结果就地不可用并带稳定码 "
    + COMPUTE_DEGRADED_CODE
    + "，不降级、不静默继续跑。"
)

#: Which posture this process announced last; the announcement is once per posture.
_declared_posture: str | None = None


def gpu_posture(armed: bool | None = None) -> str:
    """Name the effective posture for this call: the hard gate, or fail-open."""
    return POSTURE_REQUIRE_GPU if require_gpu_enabled(armed) else POSTURE_FAIL_OPEN


def posture_basis(armed: bool | None = None) -> str:
    """Say what the posture was resolved from; a forced caller hides behind no env."""
    if armed is None:
        raw = (os.getenv(REQUIRE_GPU_ENV) or "").strip()
        return REQUIRE_GPU_ENV + " 现值=" + (raw or "<未设>")
    return REQUIRE_GPU_ENV + " 由调用方显式指定 require_gpu=" + str(armed)


def declare_gpu_posture(armed: bool | None = None) -> str:
    """Log one named line per posture so the default is never anonymous.

    R673 ① wants the unset switch named and saying out loud that R26②-type criteria
    cannot be judged in that shape; R673 ② wants the armed switch named as well. The
    two bodies are different strings, so a reader can tell which shape produced a
    number, and a test can fail when either shape stops announcing itself.
    """
    global _declared_posture
    posture = gpu_posture(armed)
    if _declared_posture == posture:
        return posture
    _declared_posture = posture
    body = (
        POSTURE_DECLARATION_REQUIRE_GPU
        if posture == POSTURE_REQUIRE_GPU
        else POSTURE_DECLARATION_FAIL_OPEN
    )
    logger.warning("%s 依据：%s", body, posture_basis(armed))
    return posture


def reset_gpu_posture_declaration() -> None:
    """Forget the announced posture so the next detection announces it again."""
    global _declared_posture
    _declared_posture = None

def _matches(tokens: list[str], needles: tuple[str, ...]) -> bool:
    return any(needle in token for token in tokens for needle in needles)


def _walk(payload: Any, depth: int = 0):
    """Yield ``(key, value)`` for every mapping entry at any nesting depth."""
    if depth > 5 or payload is None:
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield str(key).lower(), value
            yield from _walk(value, depth + 1)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _walk(item, depth + 1)


def _device_tokens(payload: Any) -> list[str]:
    return sorted(
        {
            value.strip().lower()
            for key, value in _walk(payload)
            if key in _DEVICE_KEYS and isinstance(value, str) and value.strip()
        }
    )


def _vram_values(payload: Any) -> list[int]:
    numbers = (
        int(value)
        for key, value in _walk(payload)
        if key in _VRAM_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    return list(numbers)


def _gpu_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in _GPU_COUNT_KEYS:
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return 0


def _detail(tokens: list[str]) -> str | None:
    return ", ".join(tokens[:6]) if tokens else None


def _verdict_gpu(detail: str | None, loaded_models: int, vram_bytes: int) -> InferenceCompute:
    return InferenceCompute(
        kind=COMPUTE_GPU,
        detail=detail,
        loaded_models=loaded_models,
        vram_bytes=vram_bytes,
    )


def _verdict_cpu(detail: str | None, loaded_models: int) -> InferenceCompute:
    return InferenceCompute(
        kind=COMPUTE_CPU,
        detail=detail,
        loaded_models=loaded_models,
        error_code=COMPUTE_DEGRADED_CODE,
        error_message=CPU_FALLBACK_MESSAGE,
    )


def _verdict_unknown(
    detail: str | None,
    loaded_models: int,
    probe_errors: tuple[str, ...],
) -> InferenceCompute:
    message = UNDETERMINED_MESSAGE
    if probe_errors:
        message = message + " 探测失败：" + "；".join(probe_errors)
    return InferenceCompute(
        kind=COMPUTE_UNKNOWN,
        detail=detail,
        loaded_models=loaded_models,
        error_message=message,
    )


def classify_inference_compute(
    ps_payload: dict[str, Any] | None,
    version_payload: dict[str, Any] | None,
    *,
    probe_errors: tuple[str, ...] = (),
) -> InferenceCompute:
    """Turn raw Ollama payloads into one of exactly three verdicts.

    Pure: no transport, no clock, no environment. ``/api/ps`` outranks the start-up
    answer in ``/api/version`` while a model is resident, because a running model is
    direct evidence about the hardware it is using right now.
    """
    ps = ps_payload if isinstance(ps_payload, dict) else {}
    version = version_payload if isinstance(version_payload, dict) else {}
    loaded_models = len(list(ps.get("models") or []))
    vram = _vram_values(ps)
    resident = max(vram) if vram else 0
    ps_tokens = _device_tokens(ps)
    if loaded_models and (resident > 0 or _matches(ps_tokens, _GPU_TOKENS)):
        return _verdict_gpu(_detail(ps_tokens), loaded_models, resident)
    if loaded_models and (bool(vram) or _matches(ps_tokens, _CPU_TOKENS)):
        return _verdict_cpu(_detail(ps_tokens), loaded_models)
    version_tokens = _device_tokens(version)
    runtime_gpu = _gpu_count(version) > 0 or _matches(version_tokens, _GPU_TOKENS)
    if runtime_gpu:
        return _verdict_gpu(_detail(version_tokens), loaded_models, resident)
    if _matches(version_tokens, _CPU_TOKENS):
        return _verdict_cpu(_detail(version_tokens), loaded_models)
    unknown_detail = _detail(ps_tokens + version_tokens) or "no_compute_evidence"
    return _verdict_unknown(unknown_detail, loaded_models, probe_errors)


def detect_inference_compute(
    fetch: Callable[[str], dict[str, Any]],
    base_url: str,
) -> InferenceCompute:
    """Ask Ollama where inference runs, through the injected transport only.

    Nothing in here opens a socket on its own: callers pass the same fetch they gave
    ``discover_ollama_models``, so the tests never contact a real registry.
    """
    root = (base_url or "").rstrip("/")
    payloads: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in ("/api/ps", "/api/version"):
        try:
            payload = fetch(root + path)
        except Exception as exc:
            errors.append(f"{path} {type(exc).__name__}: {exc}")
            continue
        if isinstance(payload, dict):
            payloads[path] = payload
    if not payloads:
        return _verdict_unknown("probe_failed", 0, tuple(errors))
    return classify_inference_compute(
        payloads.get("/api/ps"),
        payloads.get("/api/version"),
        probe_errors=tuple(errors),
    )


def annotate_inference_compute(
    result: DiscoveryResult,
    fetch: Callable[[str], dict[str, Any]],
    base_url: str,
    *,
    require_gpu: bool | None = None,
) -> DiscoveryResult:
    """Attach the compute verdict; hard-fail only a *confirmed* CPU fallback.

    ``unknown`` changes nothing but the log line: it is neither a passport ("clearly
    on the card") nor a crime ("degraded"). ``require_gpu`` overrides the environment
    switch for callers that already know their own policy.

    The posture that produced this answer is announced once per process by
    ``declare_gpu_posture`` (R673) before the probe runs.
    """
    declare_gpu_posture(require_gpu)
    compute = detect_inference_compute(fetch, base_url)
    result.inference = compute
    if compute.on_gpu:
        return result
    if compute.undetermined:
        logger.warning("ollama inference compute undetermined: %s", compute.detail)
        return result
    logger.warning("ollama inference is running on CPU, not GPU: %s", compute.detail or "")
    if require_gpu_enabled(require_gpu):
        logger.warning("%s 探测读数：%s", HARD_REFUSAL_DECLARATION, compute.detail or "")
        result.available = False
        result.error_code = compute.error_code
        result.error_message = compute.error_message
        return result
    logger.warning("%s 探测读数：%s", CPU_LEG_DECLARATION, compute.detail or "")
    return result
