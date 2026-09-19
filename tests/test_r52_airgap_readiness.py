"""R52 -- the air-gap claim has to be re-provable, not remembered.

Offline by design: no sockets, no containers. The live-tree scan is the regression gate
(a hard-coded CDN URL or a "quick" verify=False fails it), and the rest pins that the
detector still bites, that the TLS variant of the proxy keeps every security directive of
the plain one, and that the bulk-account tool cannot write by accident.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


air = _load("check_airgap_readiness")
bulk = _load("provision_bulk_accounts")

NGINX = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
HTTPS_EXAMPLE = (ROOT / "deploy" / "nginx.https.conf.example").read_text(encoding="utf-8")
BASE_COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
TLS_OVERLAY = (ROOT / "deploy" / "docker-compose.tls.yml").read_text(encoding="utf-8")


def test_the_shipped_tree_passes_the_air_gap_gate() -> None:
    rows, _pending = air.report()
    assert [name for state, name, _ in rows if state == "FAIL"] == [], (
        "the private-deployment claim regressed: "
        + "; ".join(name + " -> " + detail for state, name, detail in rows if state == "FAIL"))


@pytest.mark.parametrize("snippet", [
    'resp = requests.get(url, verify=False)',
    'ctx.options |= ssl.CERT_NONE',
    'ctx.check_hostname = False',
    'process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"',
    'tls: { rejectUnauthorized: false }',
    'RUN npm config set strict-ssl --insecure',
])
def test_the_detector_recognises_a_tls_shortcut(snippet: str) -> None:
    assert air.tls_bypass_hits(snippet), "pattern table went blind to: " + snippet


def test_clean_code_passes_the_detector() -> None:
    assert air.tls_bypass_hits('resp = requests.get(url, timeout=30)') == []


@pytest.mark.parametrize(("line", "external"), [
    ('BASE = "https://api.openai.com/v1"', True),
    ('url = "https://cdn.jsdelivr.net/chart.js"', True),
    ('set $api http://backend:8001;', False),
    ('health = "http://127.0.0.1:8001/api/v1/health"', False),
    ('upstream = "http://redis:6379"', False),
])
def test_only_public_hosts_count_as_an_exit(line: str, external: bool) -> None:
    assert bool(air.external_host_hits(line)) is external


def test_the_https_variant_keeps_every_security_directive() -> None:
    """A second proxy config is how /static leaks and runtime directories start serving."""
    security = ("proxy_pass", "limit_conn", "deny all", "return 404", "client_max_body_size",
                "proxy_buffering off", "proxy_cache off", "proxy_read_timeout", "access_log off",
                "resolver 127.0.0.11", "try_files")
    base = {key for key in security if key in NGINX}
    assert base, "the reference proxy config lost the directives this test compares"
    missing = {key for key in base if key not in HTTPS_EXAMPLE}
    assert not missing, "deploy/nginx.https.conf.example is missing " + ", ".join(sorted(missing))
    assert "listen 443 ssl" in HTTPS_EXAMPLE and "ssl_certificate " in HTTPS_EXAMPLE


def test_plain_http_stays_the_default_and_the_overlay_ships_no_shortcut() -> None:
    assert "listen 443" not in NGINX, "the base stack must keep working without a certificate"
    assert "TLS_CERT_FILE" not in BASE_COMPOSE, "TLS must not be required by the base stack"
    assert "read_only: true" in TLS_OVERLAY and "443" in TLS_OVERLAY
    assert not air.tls_bypass_hits(TLS_OVERLAY), "the TLS overlay must not weaken verification"


def test_the_gate_names_what_it_cannot_prove() -> None:
    """A green run must not read as "offline capability proven here"."""
    _rows, pending = air.report()
    assert len(pending) >= 3
    joined = " ".join(pending)
    for topic in ("断网", "证书", "批量账号"):
        assert topic in joined, "pending list stopped covering " + topic


def test_bulk_accounts_cannot_write_by_accident(monkeypatch, capsys) -> None:
    def _explode(*args, **kwargs):
        raise AssertionError("dry run opened a socket")

    monkeypatch.setattr(bulk.urllib.request, "urlopen", _explode)
    assert bulk.main(["--count", "50"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and '"count": 50' in out and "assert" in out.lower()
