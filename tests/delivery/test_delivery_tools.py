from __future__ import annotations

import json
from pathlib import Path

from scripts.delivery import bundle, longrun, orchestrate, recovery


def test_bundle_plan_reports_destination_without_writing(tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"abc")
    spec = tmp_path / "manifest.json"
    spec.write_text(json.dumps({"assets": [
        {"id": "model", "kind": "file", "path": "model.bin", "size_bytes": 3}
    ]}), encoding="utf-8")
    destination = tmp_path / "bundle"
    report = bundle.plan(spec, destination)
    assert report["declared_file_bytes"] == 3
    assert not destination.exists()


def test_bundle_apply_requires_confirmation_and_refuses_nonempty_target(tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"abc")
    spec = tmp_path / "manifest.json"
    spec.write_text(json.dumps({"assets": [
        {"id": "model", "kind": "file", "path": "model.bin", "size_bytes": 3}
    ]}), encoding="utf-8")
    destination = tmp_path / "bundle"
    try:
        bundle.apply(spec, destination, confirm="wrong")
    except ValueError as exc:
        assert "confirmation" in str(exc)
    else:
        raise AssertionError("wrong token was accepted")
    destination.mkdir()
    (destination / "unknown.txt").write_text("keep", encoding="utf-8")
    try:
        bundle.apply(spec, destination, confirm=f"bundle:{destination.resolve()}")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("nonempty destination was overwritten")
    assert (destination / "unknown.txt").read_text(encoding="utf-8") == "keep"


def test_longrun_state_is_resumable_and_does_not_shorten_window(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    args = type("Args", (), {"project": "eb-test", "health_url": "local://health",
                            "interval": 300, "version": "test",
                            "hardware": "synthetic", "load": "none"})()
    state = longrun.start(state_path, args, spawn=False)
    original_start = float(state["deadline_epoch"]) - longrun.WINDOW_SECONDS
    monkeypatch.setattr(longrun, "check_health",
                        lambda *_a, **_k: {"ok": True, "summary": "synthetic"})
    monkeypatch.setattr(longrun, "now", lambda: original_start + 60)
    ticked = longrun.tick(state_path, 1)
    assert ticked["status"] == "running"
    monkeypatch.setattr(longrun, "now", lambda: original_start + longrun.WINDOW_SECONDS - 1)
    assert longrun.tick(state_path, 1)["status"] == "running"
    monkeypatch.setattr(longrun, "now", lambda: original_start + longrun.WINDOW_SECONDS)
    assert longrun.tick(state_path, 1)["status"] == "passed"


def test_interrupted_longrun_restarts_a_new_continuous_window(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "schema": "enterprise-brain-longrun/v1",
        "status": "interrupted",
        "deadline_epoch": 10,
        "checks": [],
    }), encoding="utf-8")
    resumed = longrun.resume(state_path)
    assert resumed["status"] == "running"
    assert resumed["deadline_epoch"] > 10
    assert resumed["interruptions"][0]["previous_deadline_epoch"] == 10


def test_orchestration_plan_and_recovery_refuse_wrong_confirmation():
    args = type("Args", (), {
        "project": "eb-plan", "install_path": "/tmp/eb-plan",
        "env_file": "/tmp/private.env", "frontend_port": 18090,
        "backend_port": 18091, "backend_image": "backend:new",
        "frontend_image": "frontend:new",
    })()
    report = orchestrate.plan(args)
    assert report["project"] == "eb-plan"
    assert report["frontend_port"] == 18090
    try:
        recovery.backup("eb-plan", "/tmp/private.env", "/secure/backup",
                        "wrong", 18090, 18091)
    except ValueError as exc:
        assert "confirmation" in str(exc)
    else:
        raise AssertionError("wrong recovery token was accepted")
