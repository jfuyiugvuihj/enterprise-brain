#!/usr/bin/env python3
"""Container-side backup/restore worker used only by an isolated delivery target."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from app.common.backup import create_backup, restore_backup
from scripts.backup_database import backup_database, pair_globals_with_backup
from scripts.restore_database import restore_backup_with_globals


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def backup(output_dir: Path) -> dict:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "database.dump"
    backup_database(
        database_url, database,
        required_tables=("chunks", "chunk_vectors"),
    )
    globals_pair = pair_globals_with_backup(database_url, database)
    workspace = output_dir / "workspace.zip"
    workspace_manifest = create_backup("/app", workspace)
    manifest = {
        "schema": "enterprise-brain-recovery-point/v1",
        "database": {"path": database.name, "bytes": database.stat().st_size,
                     "sha256": digest(database)},
        "globals": {name: {"path": Path(path).name, "sha256": digest(Path(path))}
                    for name, path in (("json", globals_pair["json"]),
                                       ("sql", globals_pair["sql"]))},
        "workspace": {"path": workspace.name, "bytes": workspace.stat().st_size,
                      "sha256": digest(workspace),
                      "files": workspace_manifest["files"]},
        "redis": {
            "included": False,
            "policy": "Do not restore live queue bytes. Quarantine pending work, start with a fresh Redis volume, "
                      "then reconcile task identities against PostgreSQL and audit before accepting work.",
        },
    }
    (output_dir / "recovery-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def restore(directory: Path, target_root: Path, database_url: str) -> dict:
    manifest = json.loads((directory / "recovery-manifest.json").read_text(encoding="utf-8"))
    workspace = directory / manifest["workspace"]["path"]
    if digest(workspace) != manifest["workspace"]["sha256"]:
        raise ValueError("workspace backup hash mismatch")
    database = directory / manifest["database"]["path"]
    if digest(database) != manifest["database"]["sha256"]:
        raise ValueError("database backup hash mismatch")
    restored_workspace = restore_backup(workspace, target_root)
    restored_database = restore_backup_with_globals(database, database_url)
    return {"schema": "enterprise-brain-restore-result/v1",
            "workspace": {"files": restored_workspace["files"]},
            "database": restored_database}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--directory", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--directory", required=True)
    r.add_argument("--target-root", required=True)
    r.add_argument("--database-url", default="")
    args = parser.parse_args(argv)
    if args.command == "backup":
        report = backup(Path(args.directory))
    else:
        database_url = args.database_url or os.environ.get("TARGET_DATABASE_URL", "")
        if not database_url:
            raise ValueError("--database-url or TARGET_DATABASE_URL is required")
        report = restore(Path(args.directory), Path(args.target_root), database_url)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
