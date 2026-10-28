#!/usr/bin/env python3
"""Coordinate existing backup/restore CLIs on an explicitly named Compose project."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def compose(install_path: str, project: str, env_file: str, *args: str,
            frontend_port: int, backend_port: int,
            ollama_volume: str) -> subprocess.CompletedProcess:
    root = Path(install_path).resolve()
    override = root / "deploy" / "delivery" / "compose.override.yml"
    environment = os.environ.copy()
    environment["COMPOSE_PROJECT_NAME"] = project
    environment["DELIVERY_FRONTEND_PORT"] = str(frontend_port)
    environment["DELIVERY_BACKEND_PORT"] = str(backend_port)
    environment["DELIVERY_BACKEND_IMAGE"] = os.environ.get(
        "DELIVERY_BACKEND_IMAGE", "enterprise-brain:local")
    environment["DELIVERY_FRONTEND_IMAGE"] = os.environ.get(
        "DELIVERY_FRONTEND_IMAGE", "enterprise-brain-frontend:local")
    environment["DELIVERY_OLLAMA_VOLUME"] = ollama_volume
    return subprocess.run(
        ["docker", "compose", "--project-directory", str(root), "--project-name", project,
         "--env-file", env_file, "-f", str(root / "docker-compose.yml"),
         "-f", str(override), *args],
        cwd=root, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=True, env=environment)


def plan(project: str, backup_dir: str) -> dict:
    return {
        "status": "plan",
        "target_project": project,
        "backup_dir": str(Path(backup_dir).resolve()),
        "steps": [
            "quiesce admission and record current queue depth",
            "dump PostgreSQL with paired globals",
            "archive documents, data, static and logs",
            "hash every artifact and write recovery-manifest.json",
            "restore into a different directory, database and Compose project",
            "start a fresh Redis volume and reconcile queue identities",
            "verify authorization, hashes, sessions, calculations and PDF bytes",
        ],
        "redis_policy": "never copy live queue bytes as a recovery point",
    }


def backup(project: str, env_file: str, directory: str, confirm: str,
           frontend_port: int, backend_port: int, ollama_volume: str,
           install_path: str = str(DEFAULT_ROOT)) -> dict:
    expected = f"{project}:backup"
    if confirm != expected:
        raise ValueError(f"confirmation token must be {expected!r}")
    root = Path(install_path).resolve()
    host_directory = Path(directory).resolve()
    compose(root, project, env_file, "stop", "backend", "worker", "scheduler",
            frontend_port=frontend_port, backend_port=backend_port,
            ollama_volume=ollama_volume)
    try:
        proc = compose(root, project, env_file, "run", "--rm", "--no-deps", "-T",
                       "--volume", f"{root / 'scripts'}:/app/delivery-scripts:ro",
                       "--volume", f"{host_directory}:/backup",
                       "backend",
                       "python", "/app/delivery-scripts/delivery/recovery_worker.py", "backup",
                       "--directory", "/backup", frontend_port=frontend_port,
                       backend_port=backend_port, ollama_volume=ollama_volume)
    finally:
        compose(root, project, env_file, "start", "backend", "worker", "scheduler",
                frontend_port=frontend_port, backend_port=backend_port,
                ollama_volume=ollama_volume)
    return {"status": "backup_complete", "project": project,
            "result": proc.stdout.strip()}


def restore(project: str, env_file: str, directory: str, target_root: str,
            target_database_url_env: str, confirm: str,
            frontend_port: int, backend_port: int, ollama_volume: str,
            install_path: str = str(DEFAULT_ROOT)) -> dict:
    expected = f"{project}:restore"
    if confirm != expected:
        raise ValueError(f"confirmation token must be {expected!r}")
    if target_database_url_env != "TARGET_DATABASE_URL":
        raise ValueError("restore credentials must be supplied through TARGET_DATABASE_URL")
    root = Path(install_path).resolve()
    host_directory = Path(directory).resolve()
    compose(root, project, env_file, "stop", "backend", "worker", "scheduler", "frontend",
            frontend_port=frontend_port, backend_port=backend_port,
            ollama_volume=ollama_volume)
    completed = False
    try:
        proc = compose(root, project, env_file, "run", "--rm", "--no-deps", "-T",
                       "--volume", f"{root / 'scripts'}:/app/delivery-scripts:ro",
                       "--volume", f"{host_directory}:/backup:ro",
                       "-e", "TARGET_DATABASE_URL",
                       "backend",
                       "python", "/app/delivery-scripts/delivery/recovery_worker.py", "restore",
                       "--directory", "/backup", "--target-root", target_root,
                       frontend_port=frontend_port, backend_port=backend_port,
                       ollama_volume=ollama_volume)
        completed = True
    finally:
        if completed:
            compose(root, project, env_file, "start", "backend", "worker", "scheduler", "frontend",
                    frontend_port=frontend_port, backend_port=backend_port,
                    ollama_volume=ollama_volume)
    return {"status": "restore_complete", "project": project,
            "result": proc.stdout.strip(),
            "warning": "Redis queue bytes were intentionally not restored; reconcile before admitting work.",
            "services_left_stopped_on_failure": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--project", required=True)
    p.add_argument("--backup-dir", required=True)
    for name in ("backup", "restore"):
        child = sub.add_parser(name)
        child.add_argument("--project", required=True)
        child.add_argument("--env-file", required=True)
        child.add_argument("--directory", required=True)
        child.add_argument("--confirm")
        child.add_argument("--frontend-port", type=int, required=True)
        child.add_argument("--backend-port", type=int, required=True)
        child.add_argument("--ollama-volume", required=True)
        child.add_argument("--install-path", default=str(DEFAULT_ROOT))
        if name == "restore":
            child.add_argument("--target-root", required=True)
            child.add_argument("--database-url-env", default="TARGET_DATABASE_URL")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            report = plan(args.project, args.backup_dir)
        elif args.command == "backup":
            report = backup(args.project, args.env_file, args.directory, args.confirm,
                            args.frontend_port, args.backend_port, args.ollama_volume,
                            args.install_path)
        else:
            report = restore(args.project, args.env_file, args.directory,
                             args.target_root, args.database_url_env, args.confirm,
                             args.frontend_port, args.backend_port, args.ollama_volume,
                             args.install_path)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"recovery {args.command} failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
