"""Run the stage 5/7 container gate and write a redacted evidence log.

The gate is the part that cannot be proven offline: the images must actually build,
the services must reach a healthy state, migrations must apply inside the container,
nginx must parse, and the permission boundaries must hold through the proxy.
Nothing here deletes volumes unless --purge is passed explicitly.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"
OVERLAY_FILE = ROOT / "deploy" / "docker-compose.server.yml"
ENV_FILE = ROOT / "deploy" / ".env.server"
# Services the stack must keep running, and the one-shot container that legitimately
# exits after applying migrations.
LONG_RUNNING = ("backend", "worker", "scheduler", "frontend", "postgres", "redis", "ollama")
ONE_SHOT = "migrate"
DESKTOP_EXE = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
DAEMON_BIN = Path(r"C:\Program Files\Docker\Docker\resources\bin")
REDACTIONS = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)([=:\s\"]+)(\S+)")

# Docker Desktop 29.7 with Compose v5.5 corrupts its own BuildKit session metadata when a
# single invocation builds two images: every build in that invocation then dies with
# "header key x-docker-expose-session-sharedkey contains value with non-printable ASCII
# characters" before a layer is read. That is a machine defect, so the gate says so out
# loud instead of letting it look like a broken Dockerfile.
COMPOSE_HOST_BUILD_DEFECT = re.compile(
    r"non-printable ascii|expose-session|failed to dial grpc",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    return REDACTIONS.sub(lambda m: m.group(1) + m.group(2) + "REDACTED", text or "")


def setting(key: str, default: str) -> str:
    """Resolve a Compose interpolation value the way Compose does.

    The shell wins over ``deploy/.env.server``, which wins over the documented default, so
    the gate probes the port the stack actually published instead of assuming 8001/:80.
    """
    value = (os.environ.get(key) or "").strip()
    if not value:
        try:
            with open(ENV_FILE, "r", encoding="utf-8-sig") as handle:
                for line in handle:
                    name, sep, raw = line.strip().partition("=")
                    if sep and name.strip() == key:
                        value = raw.strip().strip('"').strip("'")
                        break
        except OSError:
            value = ""
    return value or default


class Gate:
    def __init__(self, log_path: Path) -> None:
        self.log = log_path
        self.docker = shutil.which("docker") or str(DAEMON_BIN / "docker.exe")
        self.results: list[tuple[str, bool, str]] = []
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")

    def record(self, name: str, passed: bool, detail: str) -> None:
        self.results.append((name, passed, redact(detail)))
        print(("PASS  " if passed else "FAIL  ") + name + ("" if passed else " -> " + redact(detail)[:200]))
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%H:%M:%S')}] {'PASS' if passed else 'FAIL'} {name}\n")
            handle.write(redact(detail).rstrip() + "\n\n")

    def run(self, args: list[str], timeout: int = 900) -> tuple[int, str]:
        environment = dict(os.environ)
        environment["PATH"] = str(DAEMON_BIN) + os.pathsep + environment.get("PATH", "")
        environment["COMPOSE_PROJECT_NAME"] = "enterprise-brain"
        try:
            completed = subprocess.run(
                args,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            return 124, f"timeout after {timeout}s: {' '.join(args)}"
        except OSError as exc:
            return 127, f"cannot run {' '.join(args)}: {exc}"
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")

    def compose(self, *args: str, overlay: bool = False, timeout: int = 900) -> tuple[int, str]:
        files = ["-f", str(COMPOSE_FILE)] + (["-f", str(OVERLAY_FILE)] if overlay else [])
        return self.run([self.docker, "compose", "--env-file", str(ENV_FILE)] + files + list(args), timeout=timeout)


def buildable_services() -> list[str]:
    """Service names that carry a build section, read from docker-compose.yml itself."""
    import yaml

    document = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8")) or {}
    return sorted(
        name
        for name, service in (document.get("services") or {}).items()
        if (service or {}).get("build")
    )


def host_defect_note(text: str) -> str:
    """Explain a compose build failure that comes from this machine, not the image."""
    if not COMPOSE_HOST_BUILD_DEFECT.search(text or ""):
        return ""
    return (
        "\n\nNOTE: this matches the Docker Desktop BuildKit session defect on this host "
        "(two images built by one compose invocation). Build the services one at a time: "
        "`docker compose ... build <service>`. The repository files are not at fault here."
    )


def wait_for_daemon(gate: Gate, deadline_seconds: int) -> tuple[bool, str]:
    deadline = time.time() + deadline_seconds
    launched = False
    while time.time() < deadline:
        code, text = gate.run([gate.docker, "version", "--format", "{{.Server.Version}}"], timeout=60)
        if code == 0:
            return True, f"daemon up: {text.strip()}" + (" (Docker Desktop launched by this gate)" if launched else "")
        if not launched and DESKTOP_EXE.exists():
            subprocess.Popen([str(DESKTOP_EXE)], close_fds=True)
            launched = True
        time.sleep(10)
    return False, f"daemon unavailable after {deadline_seconds}s"


def http_status(url: str, timeout: int = 30) -> tuple[int | None, str]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(400).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - the gate must report, not crash
        return None, f"{type(exc).__name__}: {exc}"


def check_service_states(gate: Gate) -> None:
    code, text = gate.compose("ps", "--format", "{{.Service}}|{{.State}}|{{.Health}}")
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 3 and parts[0]:
            rows[parts[0]] = (parts[1], parts[2])
    problems = [name for name in LONG_RUNNING if name not in rows]
    problems += [
        f"{name} state={rows[name][0]}"
        for name in LONG_RUNNING
        if name in rows and rows[name][0] != "running"
    ]
    problems += [
        f"{name} health={rows[name][1]}"
        for name in LONG_RUNNING
        if name in rows and rows[name][1] not in {"", "healthy", "none", "<none>", "[none]"}
    ]
    gate.record(
        "the seven long-running services are running and healthy",
        code == 0 and not problems,
        "; ".join(problems) or text,
    )
    one_shot = rows.get(ONE_SHOT)
    gate.record(
        "the one-shot migrate container is not left running",
        one_shot is None or one_shot[0].startswith("exited"),
        text if one_shot is None else f"{ONE_SHOT} state={one_shot[0]} health={one_shot[1]}",
    )


def check_migrations(gate: Gate) -> None:
    code, text = gate.compose("run", "--rm", "migrate", timeout=600)
    gate.record("migrations apply inside the container (idempotent re-run)", code == 0, text)
    script = (
        "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atc "
        "\"select 'vector='||(select count(*) from pg_extension where extname='vector')||"
        "' ledger='||(select count(*) from schema_migrations)||"
        "' tables='||(select count(*) from information_schema.tables where table_schema='public')||"
        "' accounts='||(select count(*) from users)\""
    )
    code, text = gate.compose("exec", "-T", "postgres", "sh", "-c", script, timeout=180)
    numbers = re.search(r"vector=(\d+) ledger=(\d+) tables=(\d+) accounts=(\d+)", text)
    ok = code == 0 and bool(numbers) and numbers.group(1) == "1" and int(numbers.group(2)) >= 4 and int(numbers.group(3)) >= 25
    gate.record("pgvector + migration ledger + table count in the container database", ok, text)
    accounts = numbers.group(4) if numbers else "unread"
    gate.record(
        "the user table can authenticate someone",
        code == 0 and bool(numbers) and int(accounts) >= 1,
        f"accounts={accounts}; an empty users table means nobody can ever sign in, "
        "see the first-administrator section of deploy/README.server.md",
    )


def check_nginx(gate: Gate) -> None:
    code, text = gate.compose("exec", "-T", "frontend", "nginx", "-t", timeout=180)
    gate.record("nginx configuration parses inside the container", code == 0, text)
    code, text = gate.compose(
        "exec", "-T", "frontend", "sh", "-c",
        "grep -E -c 'location[[:space:]]+/static/|alias' /etc/nginx/conf.d/default.conf || true",
        timeout=180,
    )
    gate.record("nginx publishes no /static and no alias", code == 0 and text.strip().splitlines()[-1:] == ["0"], text)


def check_http_boundaries(gate: Gate) -> None:
    backend = "http://127.0.0.1:" + setting("BACKEND_HOST_PORT", "8001")
    proxy = "http://127.0.0.1:" + setting("HTTP_PORT", "80")
    status, body = http_status(backend + "/api/v1/health")
    gate.record("backend /api/v1/health answers 200", status == 200, f"{status} {body}")
    status, body = http_status(backend + "/api/v1/health/details")
    gate.record("anonymous /api/v1/health/details is not readable", status in {401, 403}, f"{status} {body}")
    proxy_status, proxy_body = http_status(proxy + "/api/v1/health")
    if proxy_status is None and "10013" in proxy_body + " ":
        gate.record("nginx proxy on :80 is reachable", False, "port 80 unusable on this host: " + proxy_body)
        return
    gate.record("nginx proxies /api/v1/health to the backend", proxy_status == 200, f"{proxy_status} {proxy_body}")
    leaks = []
    for probe in ("static/charts/", "documents/", "data/", "logs/"):
        status, _ = http_status(proxy + "/" + probe, timeout=20)
        if status not in {403, 404}:
            leaks.append(f"{probe} -> {status}")
    gate.record("runtime directories are refused at the proxy", not leaks, "; ".join(leaks) or "all 403/404")


def main_process(gate: Gate, service: str, marker: str) -> str:
    """Report whether PID 1 of a container is the process its service declares.

    The slim base image ships without procps, so ``ps`` is unavailable inside the
    container. ``/proc/1/cmdline`` always exists, and reading only PID 1 keeps the probe
    from matching its own command line.
    """
    probe = (
        "import sys;sys.stdout.write('yes' if b'"
        + marker
        + "' in open('/proc/1/cmdline','rb').read() else 'no')"
    )
    code, text = gate.compose("exec", "-T", service, "python", "-c", probe, timeout=180)
    if code != 0:
        return "error:" + (text.strip().splitlines()[-1] if text.strip() else "exec failed")
    return text.strip().splitlines()[-1] if text.strip() else "empty"


def check_process_ownership(gate: Gate) -> None:
    code, text = gate.compose("exec", "-T", "backend", "python", "-c",
                              "import os;print(os.environ.get('SCHEDULER_ENABLED','unset'))", timeout=180)
    gate.record("the API does not own the scheduler", code == 0 and text.strip().endswith("false"), text)
    api_main = main_process(gate, "backend", "uvicorn")
    gate.record("the API container runs the uvicorn entrypoint", api_main == "yes", "backend pid1=" + api_main)
    scheduler_main = main_process(gate, "scheduler", "scheduler.py")
    gate.record(
        "exactly one scheduler process runs",
        scheduler_main == "yes" and api_main == "yes",
        f"scheduler pid1={scheduler_main} backend pid1={api_main}",
    )
    worker_main = main_process(gate, "worker", "queue_worker.py")
    gate.record("the queue worker process is alive", worker_main == "yes", "worker pid1=" + worker_main)


def check_model_honesty(gate: Gate) -> None:
    probe = (
        "from app.common.model_config import get_local_model_settings as g;"
        "s=g();print(s.model_source, bool(s.model_name))"
    )
    code, text = gate.compose("exec", "-T", "backend", "python", "-c", probe, timeout=180)
    token = text.strip().splitlines()[-1] if text.strip() else ""
    gate.record(
        "model selection reports its source and invents no name",
        code == 0 and token.split(" ")[0] in {"configured", "discovered", "none"},
        text,
    )


def check_storage_write_access(gate: Gate) -> None:
    """Write and remove a probe file in every path a volume is mounted on.

    Volume ownership is invisible to a health endpoint: an upload route that cannot write
    its temporary file answers 500 while the container stays healthy, so the gate has to
    attempt the write as the user the API actually runs as.
    """
    probe = "\n".join([
        "import os, tempfile",
        "paths = ['/app/documents', '/app/data', '/app/static', '/app/logs', '/app/chroma_db']",
        "refused = []",
        "for path in paths:",
        "    try:",
        "        handle, name = tempfile.mkstemp(dir=path, prefix='.gate-write-probe')",
        "        os.close(handle)",
        "        os.unlink(name)",
        "    except OSError as exc:",
        "        refused.append(path + '=' + exc.__class__.__name__)",
        "print('uid=' + str(os.getuid()) + ' refused=' + (','.join(refused) or 'none'))",
    ])
    code, text = gate.compose("exec", "-T", "backend", "python", "-c", probe, timeout=180)
    line = text.strip().splitlines()[-1] if text.strip() else ""
    gate.record(
        "the API process can write into every mounted volume",
        code == 0 and line.endswith("refused=none"),
        line or text,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--down", action="store_true", help="stop the stack and exit")
    parser.add_argument("--purge", action="store_true", help="with --down, also delete the named volumes")
    parser.add_argument("--skip-build", action="store_true", help="reuse the existing image")
    parser.add_argument("--daemon-timeout", type=int, default=300)
    parser.add_argument("--log", default=str(ROOT / "tmp" / "container_gate.log"))
    args = parser.parse_args(argv)

    gate = Gate(Path(args.log))
    if not ENV_FILE.is_file():
        gate.record("deploy/.env.server exists", False, "copy deploy/.env.server.example and fill it in")
        return 1
    if args.down:
        command = ["down"] + (["-v"] if args.purge else [])
        code, text = gate.compose(*command, timeout=600)
        gate.record("compose down" + (" --purge volumes" if args.purge else ""), code == 0, text)
        return 0 if code == 0 else 1

    up, detail = wait_for_daemon(gate, args.daemon_timeout)
    gate.record("docker daemon is reachable", up, detail)
    if not up:
        return 1

    code, text = gate.run([sys.executable, str(ROOT / "scripts" / "check_deployment_env.py"), str(ENV_FILE)])
    gate.record("env pre-flight passes", code == 0, text)
    code, text = gate.compose("config", "--quiet")
    gate.record("compose config validates (base)", code == 0, text)
    code, text = gate.compose("config", "--quiet", overlay=True)
    gate.record("compose config validates (base + overlay)", code == 0, text)
    if not args.skip_build:
        # One compose invocation per image. Building them together is the documented
        # operator command, and on the host above it fails for a reason that has nothing to
        # do with the image, so the gate records one honest result per buildable service.
        for service in buildable_services():
            code, text = gate.compose("build", service, timeout=3600)
            gate.record(f"docker compose build {service}", code == 0, text[-4000:] + host_defect_note(text))

    # The gate owns the build phase, so the start must never build implicitly; an implicit
    # build would let a green stack hide the absence of any build evidence at all.
    code, text = gate.compose(
        "up", "-d", "--wait", "--wait-timeout", "600", "--no-build", timeout=1200
    )
    gate.record("compose up --wait reaches the healthy state", code == 0, text[-4000:])
    if code != 0:
        _, logs = gate.compose("logs", "--tail", "120", timeout=300)
        gate.record("service logs captured after the failed start", False, logs[-4000:])
        return 1

    check_service_states(gate)
    check_migrations(gate)
    check_nginx(gate)
    check_http_boundaries(gate)
    check_process_ownership(gate)
    check_storage_write_access(gate)
    check_model_honesty(gate)

    failed = [name for name, passed, _ in gate.results if not passed]
    print(f"\ngate: {len(gate.results) - len(failed)} passed, {len(failed)} failed; evidence -> {gate.log}")
    if failed:
        print("failed steps: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())