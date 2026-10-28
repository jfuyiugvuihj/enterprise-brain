#!/usr/bin/env python3
"""Emit a whitelisted, local-only deployment diagnostic."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path


def _run(argv: list[str], timeout: float = 15.0) -> tuple[str, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "unknown", type(exc).__name__
    if proc.returncode:
        return "unavailable", f"exit={proc.returncode}"
    return "ok", (proc.stdout or "").strip()[:4000]


def collect(project: str, env_file: str) -> dict:
    docker_state, docker_detail = _run(["docker", "info", "--format",
                                        "{{.ServerVersion}}|{{.Architecture}}"])
    compose_state, compose_detail = _run([
        "docker", "compose", "--project-name", project, "--env-file", env_file,
        "--project-directory", str(Path.cwd()), "ps", "--format", "json"])
    services = []
    if compose_state == "ok":
        try:
            parsed = json.loads(compose_detail)
            for row in parsed if isinstance(parsed, list) else [parsed]:
                if isinstance(row, dict):
                    services.append({
                        "name": str(row.get("Name") or row.get("name") or "")[:120],
                        "service": str(row.get("Service") or row.get("service") or "")[:80],
                        "state": str(row.get("State") or row.get("state") or "unknown")[:40],
                        "health": str(row.get("Health") or row.get("health") or "unknown")[:40],
                        "image": str(row.get("Image") or row.get("image") or "")[:160],
                    })
        except ValueError:
            services = []
    docker_fields = docker_detail.split("|")
    return {
        "schema": "enterprise-brain-diagnostic/v1",
        "host": {"os": platform.system(),
                 "architecture": platform.machine() or "unknown"},
        "python": platform.python_version(),
        "docker": {"status": docker_state,
                   "summary": "|".join(docker_fields[:2]) if docker_state == "ok" else docker_detail},
        "compose_project": project,
        "compose": {"status": compose_state, "services": services},
        "limitations": [
            "Environment values are intentionally not printed.",
            "Service process state does not prove business usability.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = collect(args.project, args.env_file)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["docker"]["status"] == "ok" and report["compose"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
