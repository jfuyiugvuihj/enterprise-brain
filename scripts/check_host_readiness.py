#!/usr/bin/env python3
"""Read-only host readiness checks for an Enterprise Brain installation."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_deployment_env import check_env_file
from scripts.delivery.manifest import result, verify_assets


def _run(command: list[str], timeout: float) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, type(exc).__name__
    text = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, text[:160]


def check_port(port: int, timeout: float) -> dict:
    end = str(port)
    if not 1 <= port <= 65535:
        return result(f"port:{end}", "fail", "port is outside 1..65535",
                      "Choose a valid local TCP port.")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=min(timeout, 2.0)):
            return result(f"port:{end}", "unknown",
                          "a local listener accepts connections; its owner was not identified",
                          "Confirm which program owns the port; an Enterprise Brain service may be expected.")
    except ConnectionRefusedError:
        return result(f"port:{end}", "pass", "no local TCP listener was reachable")
    except (TimeoutError, socket.timeout):
        return result(f"port:{end}", "unknown", "local port probe timed out",
                      "Check the port manually; do not treat this as free.")
    except OSError as exc:
        return result(f"port:{end}", "unknown", f"port state could not be read: {exc.errno}",
                      "Inspect local listeners manually.")


def collect(*, env_file: str | None, install_path: str, ports: list[int],
            asset_manifest: str | None, verify_hashes: bool, timeout: float) -> dict:
    checks: list[dict] = []
    system = platform.system() or "unknown"
    machine = (platform.machine() or platform.processor()
               or os.environ.get("PROCESSOR_ARCHITEW6432")
               or os.environ.get("PROCESSOR_ARCHITECTURE") or "unknown")
    checks.append(result("os", "pass", f"{system} {platform.release()}"))
    checks.append(result("architecture", "pass" if machine != "unknown" else "unknown", machine,
                         "Report the target architecture manually." if machine == "unknown" else ""))

    version = sys.version_info
    py_status = "pass" if (3, 11) <= version[:2] < (3, 14) else "fail"
    checks.append(result("python", py_status, f"{version.major}.{version.minor}.{version.micro}",
                         "Install Python 3.11, 3.12 or 3.13." if py_status == "fail" else ""))

    docker_ok, docker_detail = _run(["docker", "--version"], timeout)
    checks.append(result("docker_cli", "pass" if docker_ok else "fail", docker_detail,
                         "" if docker_ok else "Install Docker Engine or Docker Desktop."))
    compose_ok, compose_detail = _run(["docker", "compose", "version"], timeout)
    checks.append(result("compose", "pass" if compose_ok else "fail", compose_detail,
                         "" if compose_ok else "Install Docker Compose v2."))
    daemon_ok, daemon_detail = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout)
    checks.append(result("docker_daemon", "pass" if daemon_ok else "unknown", daemon_detail,
                         "" if daemon_ok else "Start the Docker daemon and rerun; availability is unknown."))

    target = Path(install_path).expanduser().resolve()
    if not target.exists():
        checks.append(result("install_path", "fail", f"path does not exist: {target}",
                             "Create the approved installation directory, then rerun."))
    elif not target.is_dir():
        checks.append(result("install_path", "fail", f"path is not a directory: {target}",
                             "Select an installation directory."))
    elif os.access(target, os.R_OK | os.W_OK | os.X_OK):
        checks.append(result("install_path", "pass", f"read/write/execute access: {target}"))
    else:
        checks.append(result("install_path", "fail", f"insufficient access: {target}",
                             "Grant the deployment account access without using a write probe."))

    asset_result = None
    if asset_manifest:
        try:
            asset_result = verify_assets(asset_manifest, verify_hashes=verify_hashes, timeout=timeout)
        except ValueError as exc:
            checks.append(result("assets", "fail", str(exc), "Correct the asset manifest."))

    try:
        usage = shutil.disk_usage(target if target.exists() else target.parent)
        if asset_result:
            required = int(asset_result["declared_file_bytes"])
        else:
            required = 0
        disk_status = "fail" if required and usage.free < required else "pass"
        checks.append(result(
            "disk", disk_status,
            f"{usage.free} bytes free; manifest declares {required} bytes to read"
            if asset_manifest else f"{usage.free} bytes free; no minimum threshold was supplied",
            "Free at least the declared asset bytes." if disk_status == "fail" else ""))
    except OSError as exc:
        checks.append(result("disk", "unknown", f"disk usage could not be read: {exc.errno}",
                             "Check free space manually."))

    if env_file:
        env_path = Path(env_file).resolve()
        if not env_path.is_file():
            checks.append(result("configuration", "fail", f"env file not found: {env_path}",
                                 "Provide the deployment env file."))
        else:
            env = check_env_file(env_path)
            if env["hazards"] or env["missing"]:
                checks.append(result(
                    "configuration", "fail",
                    f"interpolation hazards={len(env['hazards'])}, missing keys={len(env['missing'])}",
                    "Run scripts/check_deployment_env.py for key-only diagnostics."))
            elif env.get("warnings"):
                checks.append(result("configuration", "warn", f"{len(env['warnings'])} warning(s)",
                                     "Review the key-only warnings before install."))
            else:
                checks.append(result("configuration", "pass",
                                     "required keys present; no interpolation hazards"))
    else:
        checks.append(result("configuration", "unknown", "no env file was supplied",
                             "Pass --env-file before claiming configuration readiness."))

    for port in ports:
        checks.append(check_port(port, timeout))

    if asset_result:
        checks.extend(asset_result["checks"])
    else:
        checks.append(result("assets", "unknown", "no asset manifest was supplied",
                             "Pass --asset-manifest for delivery readiness."))

    counts = {name: sum(row["status"] == name for row in checks)
              for name in ("pass", "warn", "fail", "unknown")}
    overall = "fail" if counts["fail"] else "warn" if counts["warn"] or counts["unknown"] else "pass"
    return {"overall": overall, "counts": counts, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--install-path", default=".")
    parser.add_argument("--port", action="append", type=int, default=[])
    parser.add_argument("--asset-manifest")
    parser.add_argument("--verify-hashes", action="store_true")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 120:
        parser.error("--timeout must be greater than 0 and at most 120 seconds")
    try:
        report = collect(env_file=args.env_file, install_path=args.install_path,
                         ports=args.port, asset_manifest=args.asset_manifest,
                         verify_hashes=args.verify_hashes, timeout=args.timeout)
    except ValueError as exc:
        print(f"readiness invocation invalid: {exc}", file=sys.stderr)
        return 64
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["checks"]:
            print(f"{row['status'].upper():7} {row['id']}: {row['summary']}")
            if row.get("next_action"):
                print(f"        next: {row['next_action']}")
        print(f"overall: {report['overall']} ({report['counts']})")
    return 2 if report["overall"] == "fail" else 1 if report["overall"] == "warn" else 0


if __name__ == "__main__":
    raise SystemExit(main())
