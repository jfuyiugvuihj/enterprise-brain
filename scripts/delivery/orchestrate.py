#!/usr/bin/env python3
"""Plan and execute an explicitly scoped isolated Compose deployment."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def compose(install_path: str, project: str, env_file: str, *args: str,
            frontend_port: int, backend_port: int,
            backend_image: str, frontend_image: str, ollama_volume: str,
            check: bool = True) -> subprocess.CompletedProcess:
    root = Path(install_path).resolve()
    override = root / "deploy" / "delivery" / "compose.override.yml"
    environment = os.environ.copy()
    environment["COMPOSE_PROJECT_NAME"] = project
    environment["DELIVERY_FRONTEND_PORT"] = str(frontend_port)
    environment["DELIVERY_BACKEND_PORT"] = str(backend_port)
    environment["HTTP_PORT"] = str(frontend_port)
    environment["BACKEND_HOST_PORT"] = str(backend_port)
    environment["DELIVERY_BACKEND_IMAGE"] = backend_image
    environment["DELIVERY_FRONTEND_IMAGE"] = frontend_image
    environment["DELIVERY_OLLAMA_VOLUME"] = ollama_volume
    return subprocess.run(
        ["docker", "compose", "--project-directory", str(root), "--project-name", project,
         "--env-file", env_file, "-f", str(root / "docker-compose.yml"),
         "-f", str(override), *args],
        cwd=root, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=check, env=environment,
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
        "ollama_volume": args.ollama_volume,
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
        "optionally import the model archive into the named empty Ollama volume",
        "run one-time migrate service",
        "start backend, worker, scheduler, frontend",
        "check API health and record image IDs",
    ]
    return info


def import_models(volume: str, archive: str, backend_image: str) -> dict:
    """Create an empty model volume and unpack a verified model archive into it."""
    source = Path(archive).resolve()
    if not source.is_file():
        raise ValueError(f"model archive does not exist: {source}")
    subprocess.run(["docker", "volume", "create", volume], check=True,
                   capture_output=True, text=True, encoding="utf-8")
    probe = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{volume}:/models:ro",
            "--entrypoint", "sh", backend_image, "-c",
            "test -z \"$(find /models -mindepth 1 -print -quit)\"",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if probe.returncode != 0:
        raise ValueError(
            f"Ollama volume {volume!r} is not empty; refusing to overwrite model bytes"
        )
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{volume}:/models",
            "-v", f"{source.parent}:/bundle:ro",
            "--entrypoint", "tar", "redis:7-alpine",
            "-C", "/models", "-xf", f"/bundle/{source.name}",
        ],
        check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return {"status": "imported", "volume": volume,
            "archive": str(source), "bytes": source.stat().st_size}


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
    model_import = None
    if getattr(args, "model_archive", None):
        model_import = import_models(
            args.ollama_volume, args.model_archive, args.backend_image
        )
    compose(args.install_path, args.project, args.env_file, "config", "--quiet",
            frontend_port=args.frontend_port, backend_port=args.backend_port,
            backend_image=args.backend_image,
            frontend_image=args.frontend_image, ollama_volume=args.ollama_volume)
    compose(args.install_path, args.project, args.env_file, "up", "-d", "--no-build",
            "--pull", "never", "--wait",
            frontend_port=args.frontend_port, backend_port=args.backend_port,
            backend_image=args.backend_image,
            frontend_image=args.frontend_image, ollama_volume=args.ollama_volume)
    ps = compose(args.install_path, args.project, args.env_file, "ps", "--format", "json",
                 frontend_port=args.frontend_port, backend_port=args.backend_port,
                 backend_image=args.backend_image,
                 frontend_image=args.frontend_image, ollama_volume=args.ollama_volume)
    info.update(status="applied", readiness=readiness,
                compose_ps=ps.stdout.strip(), model_import=model_import)
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
        args_list = ["up", "-d", "--no-build", "--pull", "never", "--wait"]
    elif args.command == "rollback":
        if not args.backend_image or not args.frontend_image:
            raise ValueError("previous backend and frontend images are required for rollback")
        args_list = ["up", "-d", "--no-build", "--pull", "never", "--wait"]
    else:
        raise ValueError("unsupported action")
    result = compose(args.install_path, args.project, args.env_file, *args_list,
                     frontend_port=args.frontend_port, backend_port=args.backend_port,
                     backend_image=args.backend_image,
                     frontend_image=args.frontend_image, ollama_volume=args.ollama_volume)
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
        p.add_argument("--model-archive")
        p.add_argument("--backend-image", required=True)
        p.add_argument("--frontend-image", required=True)
        p.add_argument("--ollama-volume", required=True)
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
