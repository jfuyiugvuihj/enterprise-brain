#!/usr/bin/env python3
"""Build and inspect an offline delivery bundle from an explicit asset manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from scripts.delivery.manifest import load_manifest, verify_assets

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_BASELINE = "910d7a13f93740aed66b0359c6a10f746dcea399"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _code_evidence(product_baseline: str) -> dict:
    evidence = {"code_version": product_baseline,
                "code_version_source": "declared-product-baseline",
                "migration_manifest_sha256": "unknown",
                "migration_count": None, "uv_lock_sha256": "unknown",
                "frontend_lock_sha256": "unknown"}
    try:
        evidence["code_version"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
            timeout=10, check=True).stdout.strip()
        evidence["code_version_source"] = "git-head"
    except (OSError, subprocess.SubprocessError):
        pass
    manifest = ROOT / "migrations" / "manifest.json"
    if manifest.is_file():
        try:
            rows = json.loads(manifest.read_text(encoding="utf-8"))
            evidence["migration_count"] = len(rows)
        except (OSError, ValueError):
            pass
        evidence["migration_manifest_sha256"] = _sha256(manifest)
    for key, relative in (
        ("uv_lock_sha256", "uv.lock"),
        ("frontend_lock_sha256", "frontend/package-lock.json"),
    ):
        path = ROOT / relative
        if path.is_file():
            evidence[key] = _sha256(path)
    return evidence


def _image_evidence(reference: str) -> dict:
    proc = subprocess.run(
        ["docker", "image", "inspect", reference, "--format",
         "{{.Id}}|{{.Os}}|{{.Architecture}}|{{.Size}}|{{json .RepoDigests}}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=20, check=True,
    )
    image_id, operating_system, architecture, size_bytes, raw_digests = (
        proc.stdout.strip().split("|", 4)
    )
    return {
        "image_id": image_id,
        "platform": f"{operating_system}/{architecture}",
        "size_bytes": int(size_bytes),
        "digests": json.loads(raw_digests or "[]"),
    }


def _free_space(destination: Path) -> int:
    candidate = destination
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return shutil.disk_usage(candidate).free


def plan(manifest: str | Path, output: str | Path,
         product_baseline: str = PRODUCT_BASELINE) -> dict:
    _, assets = load_manifest(manifest)
    destination = Path(output).resolve()
    files = [{"id": row["id"], "source": str(row["_file"]),
              "bytes": row["_file"].stat().st_size if row["_file"].is_file() else 0}
             for row in assets if row["kind"] == "file"]
    images = [str(row["reference"]) for row in assets if row["kind"] == "docker-image"]
    image_evidence = [_image_evidence(reference) for reference in images]
    declared_file_bytes = sum(row["bytes"] for row in files)
    declared_image_bytes = sum(row["size_bytes"] for row in image_evidence)
    return {
        "status": "plan",
        "destination": str(destination),
        "destination_exists": destination.exists(),
        "files": files,
        "images": images,
        "image_evidence": image_evidence,
        "code_evidence": _code_evidence(product_baseline),
        "product_baseline": product_baseline,
        "assets_without_license": [row["id"] for row in assets if not row.get("license")],
        "declared_file_bytes": declared_file_bytes,
        "declared_image_bytes": declared_image_bytes,
        "declared_total_bytes": declared_file_bytes + declared_image_bytes,
        "free_space_bytes": _free_space(destination),
        "next_action": "Run apply with the same manifest and an explicit confirmation token.",
    }


def apply(manifest: str | Path, output: str | Path, *, confirm: str,
          verify_hashes: bool = False,
          product_baseline: str = PRODUCT_BASELINE) -> dict:
    destination = Path(output).resolve()
    expected = f"bundle:{destination}"
    if confirm != expected:
        raise ValueError(f"confirmation token must be {expected!r}")
    verification = verify_assets(manifest, verify_hashes=verify_hashes)
    failures = [row for row in verification["checks"] if row["status"] == "fail"]
    if failures:
        raise ValueError("asset verification failed; no bundle was written")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("bundle destination must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    files_dir = destination / "files"
    files_dir.mkdir()
    copied = []
    for asset in verification["assets"]:
        if asset.get("kind") != "file":
            continue
        source = (Path(manifest).resolve().parent / asset["path"]).resolve()
        target = files_dir / source.name
        if target.exists():
            raise ValueError(f"duplicate bundle filename: {source.name}")
        storage = "copy"
        try:
            os.link(source, target)
            storage = "hardlink"
        except OSError:
            shutil.copy2(source, target)
        copied.append({"id": asset["id"], "name": source.name,
                       "bytes": target.stat().st_size, "sha256": _sha256(target),
                       "storage": storage})
    images = [asset for asset in verification["assets"] if asset.get("kind") == "docker-image"]
    image_archive = None
    if images:
        archive = destination / "images.tar"
        subprocess.run(["docker", "save", "-o", str(archive),
                        *[item["reference"] for item in images]], check=True)
        image_archive = {"name": archive.name, "bytes": archive.stat().st_size,
                         "sha256": _sha256(archive)}
    record = {
        "status": "applied",
        "created_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "manifest": verification["manifest"],
        "product_baseline": product_baseline,
        "files": copied,
        "images": [
            {
                "id": row["id"],
                "reference": row["reference"],
                "platform": row["platform"],
                **_image_evidence(row["reference"]),
            }
            for row in images
        ],
        "image_archive": image_archive,
        "code_evidence": _code_evidence(product_baseline),
        "license_summary": [
            {"id": row["id"], "license": row.get("license") or "unknown"}
            for row in verification["assets"]
        ],
        "artifact_verified": verify_hashes,
        "limitations": [
            "A complete manifest does not prove offline installation.",
            "Image visibility does not prove model registration or business usability.",
        ],
    }
    (destination / "bundle-manifest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        child = sub.add_parser(name)
        child.add_argument("--manifest", required=True)
        child.add_argument("--output", required=True)
        child.add_argument("--verify-hashes", action="store_true")
        child.add_argument("--json", action="store_true")
        child.add_argument("--product-baseline", default=PRODUCT_BASELINE)
        if name == "apply":
            child.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    try:
        report = (plan(args.manifest, args.output, args.product_baseline) if args.command == "plan" else
                  apply(args.manifest, args.output, confirm=args.confirm,
                        verify_hashes=args.verify_hashes,
                        product_baseline=args.product_baseline))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"bundle {args.command} failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
