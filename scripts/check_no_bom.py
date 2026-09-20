#!/usr/bin/env python3
"""Tripwire (R108): no tracked source/doc/script file may carry a UTF-8 BOM.

A BOM makes the first character U+FEFF for every tool that reads a file as
plain "utf-8" instead of "utf-8-sig", which breaks ast.parse on the source
text and any regex anchored on the first line. This repo has two
cross-language channels that read source as text, so the BOM is a real
defect, not a style preference.

Read-only: it names offenders, writes nothing, uses no network.
Exit code: 0 clean, 1 BOM found, 2 could not enumerate tracked files.

Whitelisted (BOM kept on purpose -- do not "clean" these):
  docs/handoff/2026-09-15-orchestration-board.md
      Dispatch board and single source of truth for assignment. The
      orchestrator rewrites it every round as "BOM + pure LF", so the BOM is
      part of that write-back contract.
  scripts/run_backend_tests.ps1
      Windows PowerShell 5.1 decodes BOM-less .ps1 as ANSI. The script holds
      Chinese text, so removing the BOM garbles it on the customer machine.
"""

import subprocess
import sys
from pathlib import Path, PurePosixPath

BOM = b"\xef\xbb\xbf"

WHITELIST = frozenset(
    {
        "docs/handoff/2026-09-15-orchestration-board.md",
        "scripts/run_backend_tests.ps1",
    }
)

TEXT_SUFFIXES = frozenset(
    {
        ".bash", ".bat", ".cfg", ".cjs", ".cmd", ".css", ".env", ".html",
        ".ini", ".js", ".json", ".jsx", ".markdown", ".md", ".mjs", ".ps1",
        ".py", ".pyi", ".sh", ".toml", ".ts", ".tsx", ".txt", ".vue",
        ".yaml", ".yml",
    }
)


def tracked_files(repo_root):
    """Return every tracked path, as forward-slash relative strings."""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
    )
    return sorted(name.decode("utf-8") for name in result.stdout.split(b"\x00") if name)


def in_scope(rel_path):
    """Tracked .py / markdown / text files, plus everything under scripts/."""
    if rel_path in WHITELIST:
        return False
    path = PurePosixPath(rel_path)
    if path.parts and path.parts[0] == "scripts":
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def has_bom(absolute_path):
    with open(absolute_path, "rb") as handle:
        return handle.read(len(BOM)) == BOM


def main(argv=None):
    repo_root = Path(__file__).resolve().parent.parent
    try:
        names = tracked_files(repo_root)
    except Exception as error:  # git missing, not a repo, ...
        print("check_no_bom: ERROR cannot list tracked files: %s" % error)
        return 2

    checked = 0
    offenders = []
    for rel_path in names:
        if not in_scope(rel_path):
            continue
        checked += 1
        if has_bom(repo_root / rel_path):
            offenders.append(rel_path)

    print(
        "check_no_bom: scanned %d tracked text file(s); %d whitelisted: %s"
        % (checked, len(WHITELIST), ", ".join(sorted(WHITELIST)))
    )
    for rel_path in offenders:
        print("BOM %s" % rel_path)
    if offenders:
        print("FAIL %d tracked file(s) carry a UTF-8 BOM" % len(offenders))
        return 1
    print("OK no tracked source/doc/script file carries a UTF-8 BOM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
