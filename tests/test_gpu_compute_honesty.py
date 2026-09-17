"""R26「GPU 诚实」：算力三分、稳定码复用、容器设备声明。

每一个 transport 都是注入的假注册表：这里的 URL 域名不可解析，也没有任何一条用例
会去碰真 Ollama。三分必须各自独立成立 —— 探测不到就是 unknown，既不许被当成
「有 GPU」的通行证，也不许被当成「CPU 降级」的罪名。
"""

import logging
from pathlib import Path
from typing import get_args
import re

import pytest
import yaml

from app.agents import evidence
from app.agents.contracts import ErrorEnvelope
from app.common.model_capabilities import (
    COMPUTE_CPU,
    COMPUTE_GPU,
    COMPUTE_UNKNOWN,
    REQUIRE_GPU_ENV,
    classify_inference_compute,
    detect_inference_compute,
    discover_ollama_models,
    require_gpu_enabled,
)


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"

# 域名不可解析，transport 全部注入：这套用例不存在真网络调用的路径。
BASE_URL = "http://ollama.invalid"


STABLE_CODE = "model_unavailable"


TAGS = {"models": [{"name": "local-chat:latest"}, {"name": "company-embed"}]}
PS_GPU = {"models": [{"name": "local-chat:latest", "size": 4_700_000_000, "size_vram": 4_700_000_000}]}
PS_CPU = {"models": [{"name": "local-chat:latest", "size": 4_700_000_000, "size_vram": 0}]}
PS_BLANK = {"models": []}
PS_NO_EVIDENCE = {"models": [{"name": "local-chat:latest", "details": {"family": "llama"}}]}
VERSION_BARE = {"version": "0.12.0"}
VERSION_CPU = {
    "version": "0.12.0",
    "inference_compute": [{"id": "cpu", "library": "cpu", "device_id": "cpu", "total": "7.8 GiB"}],
}
VERSION_GPU = {
    "version": "0.12.0",
    "num_gpus": 1,
    "inference_compute": [{"id": "gpu0", "library": "cuda", "name": "AD107 [GeForce RTX 4060]"}],
}


class Boom(Exception):
    """一个死掉的 transport 该抛的东西：探测必须把它落成 unknown，而不是猜。"""


def make_fetch(routes):
    calls = []

    def fetch(url):
        calls.append(url)
        for path, payload in routes.items():
            if url.endswith(path):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError("unrouted url: " + url)

    fetch.calls = calls
    return fetch


def compute_routes(ps_payload, version_payload):
    return {"/api/ps": ps_payload, "/api/version": version_payload}


def _envelope_codes():
    return set(get_args(ErrorEnvelope.model_fields["code"].annotation))


def _inference_warnings(records):
    return [record.getMessage() for record in records if "inference" in record.getMessage()]


def test_a_resident_model_with_vram_is_honest_about_the_gpu():
    compute = classify_inference_compute(PS_GPU, VERSION_GPU)
    assert compute.kind == COMPUTE_GPU
    assert compute.on_gpu and not compute.degraded_to_cpu and not compute.undetermined
    assert compute.error_code is None
    assert compute.error_message is None
    assert compute.vram_bytes == 4_700_000_000


def test_a_resident_model_without_vram_is_a_cpu_fallback_with_the_stable_code():
    compute = classify_inference_compute(PS_CPU, VERSION_GPU)
    assert compute.kind == COMPUTE_CPU
    assert compute.error_code == STABLE_CODE
    assert "CPU" in compute.error_message
    assert "未使用 GPU" in compute.error_message
    # 复用而不是新造：这个码本来就在封闭枚举里，证据层也早已把它当可重试。
    assert STABLE_CODE in _envelope_codes()
    assert STABLE_CODE in evidence._RETRIABLE_CODES


def test_a_cpu_runtime_is_a_fallback_even_with_nothing_loaded():
    # 本机实测就是这个形状：inference compute id=cpu library=cpu。
    compute = classify_inference_compute(PS_BLANK, VERSION_CPU)
    assert compute.kind == COMPUTE_CPU
    assert compute.degraded_to_cpu is True
    assert compute.error_code == STABLE_CODE


def test_gpu_and_cpu_and_unknown_are_three_verdicts_not_two():
    cases = {
        COMPUTE_GPU: classify_inference_compute(PS_GPU, VERSION_GPU),
        COMPUTE_CPU: classify_inference_compute(PS_CPU, VERSION_GPU),
        COMPUTE_UNKNOWN: classify_inference_compute(PS_NO_EVIDENCE, VERSION_BARE),
    }
    assert len({compute.kind for compute in cases.values()}) == 3
    for expected, compute in cases.items():
        assert compute.kind == expected, expected
        flags = [compute.on_gpu, compute.degraded_to_cpu, compute.undetermined]
        assert flags.count(True) == 1, (expected, flags)
    unknown = cases[COMPUTE_UNKNOWN]
    assert unknown.error_code is None
    assert unknown.on_gpu is False
    assert unknown.degraded_to_cpu is False


def test_a_dead_transport_becomes_unknown_and_never_a_gpu_claim():
    fetch = make_fetch({"/api/ps": Boom("socket closed"), "/api/version": Boom("socket closed")})
    compute = detect_inference_compute(fetch, BASE_URL)
    assert compute.kind == COMPUTE_UNKNOWN
    assert compute.detail == "probe_failed"
    assert compute.on_gpu is False
    assert compute.error_code is None
    assert [url.rsplit("/", 1)[-1] for url in fetch.calls] == ["ps", "version"]


def test_the_probe_touches_exactly_the_two_registry_routes():
    fetch = make_fetch(compute_routes(PS_GPU, VERSION_GPU))
    detect_inference_compute(fetch, BASE_URL)
    assert fetch.calls == [BASE_URL + "/api/ps", BASE_URL + "/api/version"]


def test_a_partially_offloaded_model_still_counts_as_gpu():
    mixed = {"models": [{"name": "local-chat:latest", "size": 4_700_000_000, "size_vram": 2_100_000_000}]}
    compute = classify_inference_compute(mixed, VERSION_CPU)
    assert compute.kind == COMPUTE_GPU
    assert compute.vram_bytes == 2_100_000_000


def test_discovery_without_a_compute_transport_is_unchanged(monkeypatch):
    monkeypatch.delenv(REQUIRE_GPU_ENV, raising=False)
    tags = make_fetch({"/api/tags": TAGS})
    probe = make_fetch(compute_routes(PS_CPU, VERSION_CPU))
    result = discover_ollama_models(tags, BASE_URL)
    assert tags.calls == [BASE_URL + "/api/tags"]
    assert probe.calls == []
    assert result.available is True
    assert result.error_code is None
    # 没探测过 = 判定不了，不是「有 GPU」。
    assert result.compute.kind == COMPUTE_UNKNOWN
    assert result.degraded_to_cpu is False


def test_cpu_fallback_warns_but_keeps_running_by_default(monkeypatch, caplog):
    monkeypatch.delenv(REQUIRE_GPU_ENV, raising=False)
    tags = make_fetch({"/api/tags": TAGS})
    probe = make_fetch(compute_routes(PS_CPU, VERSION_CPU))
    with caplog.at_level(logging.WARNING):
        result = discover_ollama_models(tags, BASE_URL, compute_fetch=probe)
    assert result.degraded_to_cpu is True
    assert result.available is True
    assert result.error_code is None
    assert result.compute.error_code == STABLE_CODE
    warnings = _inference_warnings(caplog.records)
    assert warnings and all("CPU" in message for message in warnings)


def test_gpu_reports_no_degradation_and_no_warning(monkeypatch, caplog):
    monkeypatch.delenv(REQUIRE_GPU_ENV, raising=False)
    tags = make_fetch({"/api/tags": TAGS})
    probe = make_fetch(compute_routes(PS_GPU, VERSION_GPU))
    with caplog.at_level(logging.WARNING):
        result = discover_ollama_models(tags, BASE_URL, compute_fetch=probe)
    assert result.compute.kind == COMPUTE_GPU
    assert result.degraded_to_cpu is False
    assert result.available is True
    assert _inference_warnings(caplog.records) == []


def test_the_switch_is_off_when_unset_and_an_argument_wins(monkeypatch):
    monkeypatch.delenv(REQUIRE_GPU_ENV, raising=False)
    assert require_gpu_enabled() is False
    for value in ("true", "TRUE", "1", "yes", "on", " yes "):
        monkeypatch.setenv(REQUIRE_GPU_ENV, value)
        assert require_gpu_enabled() is True, value
    for value in ("false", "0", "", "maybe"):
        monkeypatch.setenv(REQUIRE_GPU_ENV, value)
        assert require_gpu_enabled() is False, value
    monkeypatch.setenv(REQUIRE_GPU_ENV, "false")
    assert require_gpu_enabled(True) is True


def test_require_gpu_hard_fails_a_confirmed_cpu_fallback(monkeypatch):
    monkeypatch.setenv(REQUIRE_GPU_ENV, "true")
    tags = make_fetch({"/api/tags": TAGS})
    probe = make_fetch(compute_routes(PS_CPU, VERSION_CPU))
    result = discover_ollama_models(tags, BASE_URL, compute_fetch=probe)
    assert result.available is False
    assert result.error_code == STABLE_CODE
    assert "CPU" in result.error_message


def test_require_gpu_neither_punishes_nor_promotes_unknown(monkeypatch):
    monkeypatch.setenv(REQUIRE_GPU_ENV, "true")
    tags = make_fetch({"/api/tags": TAGS})
    probe = make_fetch({"/api/ps": Boom("down"), "/api/version": Boom("down")})
    result = discover_ollama_models(tags, BASE_URL, compute_fetch=probe)
    assert result.compute.kind == COMPUTE_UNKNOWN
    assert result.available is True
    assert result.error_code is None


def test_compose_declares_the_gpu_for_the_ollama_service():
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig"))
    service = document["services"]["ollama"]
    devices = service["deploy"]["resources"]["reservations"]["devices"]
    assert len(devices) == 1
    assert devices[0]["driver"] == "nvidia"
    assert devices[0]["count"] == "all"
    assert "gpu" in devices[0]["capabilities"]
    assert service["environment"]["NVIDIA_DRIVER_CAPABILITIES"] == "compute,utility"


def test_the_gpu_block_adds_no_new_required_compose_variable():
    # 声明 GPU 不许顺手要求新的密钥：两个 env 模板此刻归另一个 Agent 所有。
    text = COMPOSE.read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", text))
    assert required == {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "CORS_ALLOW_ORIGINS",
    }
