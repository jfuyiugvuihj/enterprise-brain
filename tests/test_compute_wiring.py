"""R26b：算力探测接进生产发现路径，并在 /health/details 暴露三分。

三条纪律各自都有对应用例：默认不改行为（未设 OLLAMA_REQUIRE_GPU 时 CPU 降级照样服务）、
确证降级才用既有稳定码拒绝、探测不到一律 unknown。transport 全部注入，域名不可解析，
这套用例不存在打真机 Ollama 的路径。
"""

import re
from pathlib import Path

import pytest

from app.common import model_config, monitoring
from app.common.model_capabilities import (
    COMPUTE_CPU,
    COMPUTE_GPU,
    COMPUTE_UNKNOWN,
    REQUIRE_GPU_ENV,
    discover_ollama_models,
)

ROOT = Path(__file__).resolve().parents[1]
HEALTH_ROUTE = ROOT / "app" / "api" / "v1" / "auth.py"

STABLE_CODE = "model_unavailable"
BASE_URL = "http://ollama.invalid"

TAGS = {"models": [{"name": "board-chat:latest"}]}
PS_GPU = {"models": [{"name": "board-chat:latest", "size": 4_000_000_000, "size_vram": 4_000_000_000}]}
PS_CPU = {"models": [{"name": "board-chat:latest", "size": 4_000_000_000, "size_vram": 0}]}
VERSION_GPU = {"version": "0.12.0", "num_gpus": 1, "inference_compute": [{"library": "cuda"}]}
VERSION_CPU = {"version": "0.12.0", "inference_compute": [{"id": "cpu", "library": "cpu"}]}


class Boom(Exception):
    """探测端点挂了：结论必须是 unknown，而不是随便挑一端。"""


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


@pytest.fixture(autouse=True)
def _isolate_caches_and_env(monkeypatch):
    for name in ("LOCAL_MODEL_NAME", "OLLAMA_MODEL", REQUIRE_GPU_ENV):
        monkeypatch.delenv(name, raising=False)
    model_config.reset_model_discovery_cache()
    model_config.reset_inference_compute_cache()
    yield
    model_config.reset_model_discovery_cache()
    model_config.reset_inference_compute_cache()


def _run_discovery(compute_routes):
    tags = make_fetch({"/api/tags": TAGS})
    probe = make_fetch(compute_routes)
    name = model_config.discover_chat_model(BASE_URL, fetch=tags, compute_fetch=probe)
    return name, tags, probe


def _result(compute_routes):
    return discover_ollama_models(
        make_fetch({"/api/tags": TAGS}),
        BASE_URL,
        compute_fetch=make_fetch(compute_routes),
    )


def test_production_discovery_probes_and_records_the_gpu():
    name, tags, probe = _run_discovery({"/api/ps": PS_GPU, "/api/version": VERSION_GPU})
    assert name == "board-chat:latest"
    assert tags.calls == [BASE_URL + "/api/tags"]
    assert probe.calls == [BASE_URL + "/api/ps", BASE_URL + "/api/version"]
    state = model_config.inference_compute_state()
    assert state["kind"] == COMPUTE_GPU
    assert state["error_code"] is None
    assert state["age_seconds"] is not None


def test_cpu_fallback_keeps_serving_when_the_switch_is_unset():
    cpu = {"/api/ps": PS_CPU, "/api/version": VERSION_CPU}
    name, _tags, _probe = _run_discovery(cpu)
    result = _result(cpu)
    assert name == "board-chat:latest"
    assert result.available is True
    assert result.error_code is None
    assert result.degraded_to_cpu is True
    state = model_config.inference_compute_state()
    assert state["kind"] == COMPUTE_CPU
    assert state["error_code"] == STABLE_CODE


def test_require_gpu_makes_a_confirmed_cpu_fallback_unavailable(monkeypatch):
    monkeypatch.setenv(REQUIRE_GPU_ENV, "true")
    cpu = {"/api/ps": PS_CPU, "/api/version": VERSION_CPU}
    name, _tags, _probe = _run_discovery(cpu)
    result = _result(cpu)
    assert result.available is False
    assert result.error_code == STABLE_CODE
    assert "CPU" in result.error_message
    assert name == ""


def test_an_unreachable_probe_stays_unknown_even_when_gpu_is_required(monkeypatch):
    monkeypatch.setenv(REQUIRE_GPU_ENV, "true")
    dead = {"/api/ps": Boom("down"), "/api/version": Boom("down")}
    name, _tags, _probe = _run_discovery(dead)
    result = _result(dead)
    assert result.available is True
    assert result.error_code is None
    assert result.degraded_to_cpu is False
    assert name == "board-chat:latest"
    state = model_config.inference_compute_state()
    assert state["kind"] == COMPUTE_UNKNOWN
    assert state["error_code"] is None


def test_the_three_verdicts_are_mutually_exclusive_through_the_production_path():
    seen = {}
    for label, routes in (
        ("gpu", {"/api/ps": PS_GPU, "/api/version": VERSION_GPU}),
        ("cpu", {"/api/ps": PS_CPU, "/api/version": VERSION_CPU}),
        ("dead", {"/api/ps": Boom("down"), "/api/version": Boom("down")}),
    ):
        model_config.reset_inference_compute_cache()
        _run_discovery(routes)
        seen[label] = model_config.inference_compute_state()
    kinds = {item["kind"] for item in seen.values()}
    assert kinds == {COMPUTE_GPU, COMPUTE_CPU, COMPUTE_UNKNOWN}
    assert seen["gpu"]["error_code"] is None
    assert seen["cpu"]["error_code"] == STABLE_CODE
    assert seen["dead"]["error_code"] is None
    assert seen["dead"]["kind"] != COMPUTE_GPU
    assert seen["dead"]["kind"] != COMPUTE_CPU


def test_health_model_block_reports_unknown_before_any_probe(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_NAME", "board-chat")
    snapshot = monitoring._model_snapshot()
    assert snapshot["inference_compute"] == COMPUTE_UNKNOWN
    assert snapshot["inference_compute_detail"] == "not_probed"
    assert snapshot["inference_compute_error_code"] is None
    assert snapshot["inference_compute_age_seconds"] is None


def test_health_model_block_carries_a_cpu_fallback_with_the_stable_code(monkeypatch):
    _run_discovery({"/api/ps": PS_CPU, "/api/version": VERSION_CPU})
    monkeypatch.setenv("LOCAL_MODEL_NAME", "board-chat")
    snapshot = monitoring._model_snapshot()
    assert snapshot["inference_compute"] == COMPUTE_CPU
    assert snapshot["inference_compute_error_code"] == STABLE_CODE


def test_the_route_delegates_its_body_to_the_snapshot_builder():
    source = HEALTH_ROUTE.read_text(encoding="utf-8-sig")
    assert re.search(
        r'@router\.get\("/health/details"\)[\s\S]{0,240}return build_health_snapshot\(',
        source,
    ), "/health/details must keep answering from build_health_snapshot"


def test_the_http_route_answers_with_the_tri_state(monkeypatch):
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})
    monkeypatch.setenv("LOCAL_MODEL_NAME", "board-chat")
    _run_discovery({"/api/ps": PS_GPU, "/api/version": VERSION_GPU})
    client = TestClient(app)
    response = client.get(
        "/api/v1/health/details",
        headers={"Authorization": f"Bearer {auth.create_token('admin')}"},
    )
    assert response.status_code == 200
    assert response.json()["model"]["inference_compute"] == COMPUTE_GPU
