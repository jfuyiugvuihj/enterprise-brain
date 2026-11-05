#!/usr/bin/env python3
"""Emit a whitelisted, local-only deployment diagnostic."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def _run(argv: list[str], timeout: float = 15.0,
         limit: int = 4000) -> tuple[str, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "unknown", type(exc).__name__
    if proc.returncode:
        return "unavailable", f"exit={proc.returncode}"
    return "ok", (proc.stdout or "").strip()[:limit]


def _compose(project: str, env_file: str, install_path: str, *args: str,
             timeout: float = 15.0) -> tuple[str, str]:
    return _run([
        "docker", "compose", "--project-name", project, "--env-file", env_file,
        "--project-directory", str(Path(install_path).resolve()), *args,
    ], timeout=timeout, limit=40000)


def _rows(detail: str) -> list[dict]:
    rows = []
    for line in detail.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if fields and any(fields):
            rows.append({"fields": fields[:8]})
    return rows


def _json_rows(detail: str) -> list[dict]:
    """Parse Compose's JSON array or its line-delimited JSON output."""
    try:
        parsed = json.loads(detail)
        candidates = parsed if isinstance(parsed, list) else [parsed]
    except ValueError:
        candidates = []
        for line in detail.splitlines():
            if not line.strip():
                continue
            try:
                candidates.append(json.loads(line))
            except ValueError:
                continue
    return [row for row in candidates if isinstance(row, dict)]


def collect(project: str, env_file: str, install_path: str = ".") -> dict:
    docker_state, docker_detail = _run(["docker", "info", "--format",
                                        "{{.ServerVersion}}|{{.Architecture}}"])
    compose_state, compose_detail = _compose(
        project, env_file, install_path, "ps", "--format", "json")
    services = []
    if compose_state == "ok":
        for row in _json_rows(compose_detail):
            services.append({
                "name": str(row.get("Name") or row.get("name") or "")[:120],
                "service": str(row.get("Service") or row.get("service") or "")[:80],
                "state": str(row.get("State") or row.get("state") or "unknown")[:40],
                "health": str(row.get("Health") or row.get("health") or "unknown")[:40],
                "image": str(row.get("Image") or row.get("image") or "")[:160],
            })
    docker_fields = docker_detail.split("|")
    migration_state, migration_detail = _compose(
        project, env_file, install_path, "exec", "-T", "postgres", "sh", "-c",
        "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atc "
        "\"SELECT count(*) || '|' || coalesce(max(version), '') || '|' || "
        "coalesce(md5(string_agg(version || ':' || checksum, '|' ORDER BY version)), '') "
        "FROM schema_migrations;\"",
    )
    migrations = {"status": migration_state}
    if migration_state == "ok":
        fields = migration_detail.split("|")
        migrations.update({
            "count": int(fields[0]) if fields[0].isdigit() else None,
            "latest": fields[1] if len(fields) > 1 else "unknown",
            "digest": fields[2] if len(fields) > 2 else "unknown",
        })

    dependency_state, dependency_detail = _compose(
        project, env_file, install_path, "exec", "-T", "backend", "python", "-c",
        "import fastapi,psycopg,redis;"
        "print(f'fastapi={fastapi.__version__}|psycopg={psycopg.__version__}|redis={redis.__version__}')",
    )
    model_state, model_detail = _compose(
        project, env_file, install_path, "exec", "-T", "ollama", "ollama", "list",
        timeout=30.0,
    )
    error_state, error_detail = _compose(
        project, env_file, install_path, "exec", "-T", "postgres", "sh", "-c",
        "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atc "
        "\"SELECT coalesce(status, 'unknown') || '|' || coalesce(error_code, '') || "
        "'|' || count(*) FROM agent_runs GROUP BY status, error_code "
        "ORDER BY status, error_code;\"",
    )
    approval_state, approval_detail = _compose(
        project, env_file, install_path, "exec", "-T", "postgres", "sh", "-c",
        "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atc "
        "\"SELECT status || '|' || count(*) FROM pending_approvals "
        "GROUP BY status ORDER BY status;\"",
    )
    service_names = [row["name"] for row in services if row.get("name")]
    stats_state, stats_detail = (
        _run(["docker", "stats", "--no-stream", "--format",
              "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}", *service_names], timeout=30.0)
        if service_names else ("unknown", "no_services")
    )
    disk = shutil.disk_usage(Path(install_path).resolve())
    report = {
        "schema": "enterprise-brain-diagnostic/v2",
        "host": {"os": platform.system(),
                 "architecture": platform.machine() or "unknown"},
        "python": platform.python_version(),
        "docker": {"status": docker_state,
                   "summary": "|".join(docker_fields[:2]) if docker_state == "ok" else docker_detail},
        "compose_project": project,
        "compose": {"status": compose_state, "services": services},
        "migrations": migrations,
        "dependencies": {
            "status": dependency_state,
            "versions": _rows(dependency_detail) if dependency_state == "ok" else [],
        },
        "models": {
            "status": model_state,
            "registered": _rows(model_detail) if model_state == "ok" else [],
        },
        "resources": {
            "status": stats_state,
            "container_stats": _rows(stats_detail) if stats_state == "ok" else [],
            "install_filesystem": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
            },
        },
        "business_failures": {
            "agent_runs": _rows(error_detail) if error_state == "ok" else [],
            "agent_runs_read_status": error_state,
            "pending_approvals": _rows(approval_detail) if approval_state == "ok" else [],
            "pending_approvals_read_status": approval_state,
        },
        "limitations": [
            "Environment values are intentionally not printed.",
            "Service process state does not prove business usability.",
            "Model registration does not prove model inference or answer quality.",
        ],
    }
    section_statuses = [
        report["docker"]["status"],
        report["compose"]["status"],
        report["migrations"]["status"],
        report["dependencies"]["status"],
        report["models"]["status"],
        report["resources"]["status"],
        report["business_failures"]["agent_runs_read_status"],
        report["business_failures"]["pending_approvals_read_status"],
    ]
    report["overall"] = "pass" if all(status == "ok" for status in section_statuses) else "unknown"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--install-path", default=".")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = collect(args.project, args.env_file, args.install_path)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report.get("overall") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
