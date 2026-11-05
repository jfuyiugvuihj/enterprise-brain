"""Validate delivery asset manifests without downloading or starting services."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

STATUSES = {"pass", "warn", "fail", "unknown"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_NAMES = {".env", ".env.local", "id_rsa", "id_ed25519"}
SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".dump", ".sqlite", ".db"}


def result(check_id: str, status: str, summary: str, next_action: str = "") -> dict:
    if status not in STATUSES:
        raise ValueError(f"invalid status {status!r}")
    return {"id": check_id, "status": status, "summary": summary, "next_action": next_action}


def load_manifest(path: str | Path) -> tuple[dict, list[dict]]:
    source = Path(path).resolve()
    if not source.is_file():
        raise ValueError(f"asset manifest not found: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"asset manifest is unreadable: {exc}") from exc
    assets = payload.get("assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list):
        raise ValueError("asset manifest must contain an assets array")
    rows = []
    seen = set()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise ValueError(f"asset {index} must be an object")
        asset_id = str(asset.get("id") or "").strip()
        kind = str(asset.get("kind") or "").strip()
        if not asset_id or asset_id in seen:
            raise ValueError(f"asset {index} has an empty or duplicate id")
        seen.add(asset_id)
        if kind not in {"file", "docker-image"}:
            raise ValueError(f"asset {asset_id} has unsupported kind {kind!r}")
        row = {**asset, "id": asset_id, "kind": kind}
        if "size_bytes" in row and (not isinstance(row["size_bytes"], int) or row["size_bytes"] < 0):
            raise ValueError(f"asset {asset_id} size_bytes must be a non-negative integer")
        if "sha256" in row and not SHA256_RE.fullmatch(str(row["sha256"])):
            raise ValueError(f"asset {asset_id} sha256 must be 64 lowercase hex characters")
        if kind == "file":
            relative = Path(str(row.get("path") or ""))
            if not str(relative) or relative.is_absolute():
                raise ValueError(f"asset {asset_id} path must be relative to the manifest")
            file_path = (source.parent / relative).resolve()
            if not file_path.is_relative_to(source.parent):
                raise ValueError(f"asset {asset_id} path escapes the manifest directory")
            row["_file"] = file_path
        else:
            if not str(row.get("reference") or "").strip():
                raise ValueError(f"asset {asset_id} image reference is required")
            if not str(row.get("platform") or "").strip():
                raise ValueError(f"asset {asset_id} image platform is required")
        rows.append(row)
    return payload, rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_assets(path: str | Path, *, verify_hashes: bool = False,
                  timeout: float = 20.0) -> dict:
    payload, assets = load_manifest(path)
    checks = []
    file_bytes = 0
    docker_visible = []
    for asset in assets:
        asset_id = asset["id"]
        if asset["kind"] == "docker-image":
            ref = str(asset["reference"])
            try:
                proc = subprocess.run(
                    ["docker", "image", "inspect", ref, "--format",
                     "{{.Id}}|{{.Os}}|{{.Architecture}}|{{json .RepoDigests}}"],
                    capture_output=True, text=True, timeout=timeout, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                checks.append(result(f"asset:{asset_id}", "unknown",
                                     f"Docker image visibility could not be read: {type(exc).__name__}",
                                     "Run on the target Docker daemon with the image imported."))
                continue
            if proc.returncode != 0:
                checks.append(result(f"asset:{asset_id}", "fail",
                                     "Docker image is not visible in the local daemon",
                                     "Import the recorded image archive or provide the correct reference."))
                continue
            fields = proc.stdout.strip().split("|")
            visible_platform = "/".join(fields[1:3])
            expected = str(asset["platform"])
            if visible_platform and visible_platform != expected:
                checks.append(result(f"asset:{asset_id}", "fail",
                                     f"image platform {visible_platform} != {expected}",
                                     "Import the linux/amd64 image for the target."))
            else:
                expected_digest = str(asset.get("digest") or "").strip()
                digests = json.loads(fields[3]) if len(fields) > 3 else []
                actual_digests = {item.split("@", 1)[-1] for item in digests if "@" in item}
                if expected_digest and expected_digest not in actual_digests:
                    checks.append(result(
                        f"asset:{asset_id}", "fail",
                        f"image digest does not match; recorded={expected_digest}, local={sorted(actual_digests) or 'none'}",
                        "Import the exact recorded image digest."))
                elif expected_digest:
                    checks.append(result(f"asset:{asset_id}", "pass",
                                         f"image visible at {visible_platform}/{expected_digest}"))
                else:
                    checks.append(result(f"asset:{asset_id}", "warn",
                                         f"image visible at {visible_platform}; no expected digest recorded",
                                         "Record the image digest before delivery."))
                docker_visible.append(ref)
            continue

        file_path = asset["_file"]
        if not file_path.is_file():
            checks.append(result(f"asset:{asset_id}", "fail",
                                 "file is missing", "Provide the recorded delivery asset."))
            continue
        if file_path.name.lower() in SECRET_NAMES or file_path.suffix.lower() in SECRET_SUFFIXES:
            checks.append(result(f"asset:{asset_id}", "fail",
                                 "asset name is not permitted in a distributable bundle",
                                 "Remove credentials, databases or private keys from the manifest."))
            continue
        size = file_path.stat().st_size
        if "size_bytes" in asset and size != asset["size_bytes"]:
            checks.append(result(f"asset:{asset_id}", "fail",
                                 f"size {size} != recorded {asset['size_bytes']}",
                                 "Re-export the asset or correct the manifest."))
            continue
        if "sha256" not in asset:
            checks.append(result(f"asset:{asset_id}", "warn",
                                 f"file exists ({size} bytes) but has no expected sha256",
                                 "Record a sha256 before claiming byte-level integrity."))
            continue
        if not verify_hashes:
            checks.append(result(f"asset:{asset_id}", "warn",
                                 f"file exists ({size} bytes); hash not read",
                                 "Repeat with --verify-hashes before delivery."))
            continue
        file_bytes += size
        actual = _sha256(file_path)
        if actual != asset["sha256"]:
            checks.append(result(f"asset:{asset_id}", "fail",
                                 "sha256 does not match the manifest",
                                 "Re-export the asset or correct the manifest."))
        else:
            checks.append(result(f"asset:{asset_id}", "pass",
                                 f"file and sha256 verified ({size} bytes)"))
    return {
        "manifest": str(Path(path).resolve()),
        "asset_count": len(assets),
        "declared_file_bytes": file_bytes,
        "docker_images_visible": docker_visible,
        "checks": checks,
        "assets": payload.get("assets", []),
    }
