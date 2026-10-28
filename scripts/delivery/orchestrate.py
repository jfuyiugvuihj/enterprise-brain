#!/usr/bin/env python3
"""Plan and execute an explicitly scoped isolated Compose deployment."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

def compose(install_path: str, project: str, env_file: str, *args: str,
            frontend_port: int, backend_port: int,
            backend_image: str, frontend_image: str,
            check: bool = True) -> subprocess.CompletedProcess:
    root = Path(install_path).resolve()
    override = root / "deploy" / "delivery" / "compose.override.yml"
    environment = os.environ.copy()
    environment["COMPOSE_PROJECT_NAME"] = project
    environment["DELIVERY_FRONTEND_PORT"] = str(frontend_port)
    environment["DELIVERY_BACKEND_PORT"] = str(backend_port)
    environment["DELIVERY_BACKEND_IMAGE"] = backend_image
    environment["DELIVERY_FRONTEND_IMAGE"] = frontend_image
    return subprocess.run(
        ["docker", "compose", "--project-directory", str(root), "--project-name", project,
         "--env-file", env_file, "-f", str(root / "docker-compose.yml"),
         "-f", str(override), *args],
        cwd=root, text=True, capture_output=True, check=check, env=environment,
    )


def target(args) -> dict:
    install = Path(args.install_path).resolve()
    return {
        "project": args.project,
        "install_path": str(install),
        "env_file": str(Path(args.env_file).resolve()),
        "frontend_port": args.frontend_port,
        "backend_port": args.backend_port,
        "backend_image": args.backend_image,
        "frontend_image": args.frontend_image,
        "compose_files": [str(install / "docker-compose.yml"),
                          str(install / "deploy" / "delivery" / "compose.override.yml")],
    }


def plan(args) -> dict:
    info = target(args)
    info["status"] = "plan"
    info["actions"] = [
        "validate env and readiness",
        "require explicit confirmation token",
        "optionally docker load the offline image archive",
        "run one-time migrate service",
        "start backend, worker, scheduler, frontend",
        "check API health and record image IDs",
    ]
    return info


def apply(args) -> dict:
    info = target(args)
    expected = f"{args.project}:apply"
    if args.confirm != expected:
        raise ValueError(f"confirmation token must be {expected!r}")
    if not Path(info["env_file"]).is_file():
        raise ValueError("env file does not exist")
    if not Path(info["install_path"]).is_dir():
        raise ValueError("install path does not exist")
    from scripts.check_host_readiness import collect as collect_readiness
    readiness = collect_readiness(
        env_file=info["env_file"], install_path=info["install_path"],
        ports=[args.frontend_port, args.backend_port], asset_manifest=None,
        verify_hashes=False, timeout=15.0,
    )
    if readiness["overall"] == "fail":
        raise ValueError("host readiness has blocking failures")
    if args.images_archive:
        subprocess.run(["docker", "load", "-i", args.images_archive], check=True)
    compose(args.install_path, args.project, args.env_file, "config", "--quiet",
            frontend_port=args.frontend_port, backend_port=args.backend_port,
            backend_image=args.backend_image,
            frontend_image=args.frontend_image)
    compose(args.install_path, args.project, args.env_file, "up", "-d", "--no-build", "--wait",
            frontend_port=args.frontend_port, backend_port=args.backend_port,
            backend_image=args.backend_image,
            frontend_image=args.frontend_image)
    ps = compose(args.install_path, args.project, args.env_file, "ps", "--format", "json",
                 frontend_port=args.frontend_port, backend_port=args.backend_port,
                 backend_image=args.backend_image,
                 frontend_image=args.frontend_image)
    info.update(status="applied", readiness=readiness,
                compose_ps=ps.stdout.strip())
    return info


def simple_action(args) -> dict:
    expected = f"{args.project}:{args.command}"
    if args.confirm != expected:
        raise ValueError(f"confirmation token must be {expected!r}")
    if args.command == "restart":
        args_list = ["restart", "backend", "worker", "scheduler", "frontend"]
    elif args.command == "upgrade":
        if not args.backup_manifest or not Path(args.backup_manifest).is_file():
            raise ValueError("upgrade requires --backup-manifest from a completed recovery point")
        backup = json.loads(Path(args.backup_manifest).read_text(encoding="utf-8"))
        if backup.get("schema") != "enterprise-brain-recovery-point/v1":
            raise ValueError("backup manifest has the wrong schema")
        args_list = ["up", "-d", "--no-build", "--wait"]
    elif args.command == "rollback":
        if not args.backend_image or not args.frontend_image:
            raise ValueError("previous backend and frontend images are required for rollback")
        args_list = ["up", "-d", "--no-build", "--wait"]
    else:
        raise ValueError("unsupported action")
    result = compose(args.install_path, args.project, args.env_file, *args_list,
                     frontend_port=args.frontend_port, backend_port=args.backend_port,
                     backend_image=args.backend_image,
                     frontend_image=args.frontend_image)
    return {"status": args.command, "project": args.project,
            "command": [item for item in args_list], "stdout": result.stdout.strip(),
            "warning": ("Image rollback alone does not reverse schema migrations; restore the isolated backup when incompatible."
                        if args.command == "rollback" else "")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply", "restart", "upgrade", "rollback"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        p.add_argument("--env-file", required=True)
        p.add_argument("--install-path", required=True)
        p.add_argument("--frontend-port", type=int, required=True)
        p.add_argument("--backend-port", type=int, required=True)
        p.add_argument("--confirm")
        p.add_argument("--images-archive")
        p.add_argument("--backend-image", required=True)
        p.add_argument("--frontend-image", required=True)
        p.add_argument("--backup-manifest")
        p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            report = plan(args)
        elif args.command == "apply":
            report = apply(args)
        else:
            report = simple_action(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"deployment {args.command} failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
