from __future__ import annotations

import json
import shutil
import types

from scripts import check_host_readiness as readiness
from scripts.delivery import manifest


def _asset(tmp_path, *, size=True, digest=True):
    payload = tmp_path / "模型.bin"
    payload.write_bytes(b"model")
    asset = {"id": "model", "kind": "file", "path": payload.name}
    if size:
        asset["size_bytes"] = payload.stat().st_size
    if digest:
        asset["sha256"] = manifest.hashlib.sha256(b"model").hexdigest()
    path = tmp_path / "assets.json"
    path.write_text(json.dumps({"assets": [asset]}), encoding="utf-8")
    return path


def test_manifest_distinguishes_existence_from_hash_verification(tmp_path):
    path = _asset(tmp_path)
    exists = manifest.verify_assets(path)
    assert exists["checks"][0]["status"] == "warn"
    checked = manifest.verify_assets(path, verify_hashes=True)
    assert checked["checks"][0]["status"] == "pass"
    assert checked["declared_file_bytes"] == 5


def test_manifest_rejects_bad_size_and_bad_digest(tmp_path):
    path = _asset(tmp_path, size=False, digest=False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["assets"][0]["size_bytes"] = 99
    payload["assets"][0]["sha256"] = "not-a-digest"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        manifest.verify_assets(path)
    except ValueError as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("invalid digest was accepted")


def test_manifest_never_accepts_an_env_file_as_distributable(tmp_path):
    path = tmp_path / ".env"
    path.write_text("TOKEN=secret", encoding="utf-8")
    spec = tmp_path / "assets.json"
    spec.write_text(json.dumps({"assets": [
        {"id": "env", "kind": "file", "path": ".env"}
    ]}), encoding="utf-8")
    checked = manifest.verify_assets(spec)
    assert checked["checks"][0]["status"] == "fail"
    assert "secret" not in json.dumps(checked)


def test_port_probe_does_not_claim_an_occupied_port_is_free(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(readiness.socket, "create_connection", lambda *_a, **_k: Connection())
    row = readiness.check_port(18080, 1)
    assert row["status"] == "unknown"
    assert "owner" in row["summary"]


def test_collect_marks_missing_docker_and_config_unknown_or_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "_run", lambda *_a, **_k: (False, "missing"))
    monkeypatch.setattr(readiness.shutil, "disk_usage",
                        lambda _path: types.SimpleNamespace(free=10**12))
    report = readiness.collect(env_file=None, install_path=str(tmp_path), ports=[],
                               asset_manifest=None, verify_hashes=False, timeout=1)
    states = {row["id"]: row["status"] for row in report["checks"]}
    assert states["docker_cli"] == "fail"
    assert states["docker_daemon"] == "unknown"
    assert states["configuration"] == "unknown"
    assert states["assets"] == "unknown"


def test_json_output_contains_required_fields_and_no_secret_value(tmp_path, capsys):
    secret = tmp_path / "secret.env"
    secret.write_text("POSTGRES_PASSWORD=do-not-print\n", encoding="utf-8")
    rc = readiness.main(["--json", "--install-path", str(tmp_path),
                         "--env-file", str(secret), "--timeout", "1"])
    payload = json.loads(capsys.readouterr().out)
    assert rc in {1, 2}
    assert all({"id", "status", "summary", "next_action"} <= set(row)
               for row in payload["checks"])
    assert "do-not-print" not in json.dumps(payload)
