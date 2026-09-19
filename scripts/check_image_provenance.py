"""Prove that the running backend image carries the source tree under test (replaces P-8).

H12 exists because acceptance runs kept measuring a container built hours before the
commits they were reporting on, and the check that was supposed to catch it compared the
image's ``Created`` timestamp -- which is UTC -- against a committer date -- which is
local. This script removes the arithmetic: the image now carries the revision it was
built from, and the answer is a string comparison.

Read-only. It builds nothing, starts nothing and writes nothing outside its own log.

    python scripts/check_image_provenance.py                 # compare against HEAD
    python scripts/check_image_provenance.py --rev 1a2b3c4   # compare against a given rev
    python scripts/check_image_provenance.py --expect-container  # also read BUILD_INFO live
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "enterprise-brain:local"
LABEL = "org.opencontainers.image.revision"
# Directories the Dockerfile copies into the image as application source. `deploy` is
# included because deploy/queue_worker.py and deploy/scheduler.py are entrypoints.
SOURCE_DIRS = ("app", "migrations", "scripts", "deploy")
CONTAINER = "enterprise-brain-backend-1"


def git(*args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return completed.returncode, (completed.stdout or "").strip()


def image_inputs() -> list[str]:
    """Paths whose bytes decide what the image contains.

    Deliberately narrower than "the whole working tree": chroma_db is tracked in this
    repository and is almost always dirty, yet .dockerignore keeps it out of the build
    context, so its dirt says nothing about whether the image matches the tree. Scoping
    the dirty flag to real build inputs is what keeps the stamp readable.
    """
    return list(SOURCE_DIRS) + ["pyproject.toml", "uv.lock", "README.md", "Dockerfile", ".dockerignore"]


def tree_state() -> tuple[str, bool]:
    """Short HEAD plus whether any tracked *build input* differs from it."""
    _, rev = git("rev-parse", "--short", "HEAD")
    _, porcelain = git("status", "--porcelain", "--", *image_inputs())
    dirty = any(line[:1] not in {" ", "?"} for line in porcelain.splitlines() if line.strip())
    return rev, dirty


def docker(*args: str) -> tuple[int, str]:
    completed = subprocess.run(["docker", *args], cwd=str(ROOT), capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def image_revision() -> str:
    code, text = docker("image", "inspect", IMAGE, "--format", "{{index .Config.Labels \"" + LABEL + "\"}}")
    if code != 0:
        return "<image not present>"
    value = text.strip()
    return value or "<label absent>"


def tracked_files(directory: str) -> list[str]:
    _, listed = git("ls-files", "--", directory)
    return sorted(name for name in listed.splitlines() if name)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_tree_to_container() -> list[str]:
    """Per-file sha256 of every tracked source file, tree side vs image side.

    This is the fallback for an image built before the revision stamp existed, or by an
    operator who forgot to pass GIT_SHA. It answers the same question without trusting a
    timestamp: is the code inside the container byte-for-byte the code on disk.
    """
    code, listing = docker(
        "exec", CONTAINER, "sh", "-c",
        "for f in $(find " + " ".join("/app/" + d for d in SOURCE_DIRS) + " -name '*.py' | sort); do "
        "sha256sum \"$f\"; done",
    )
    if code != 0:
        return ["container side unread (is " + CONTAINER + " running?): " + listing.strip().splitlines()[-1:][0]
                if listing.strip() else "container side unread"]
    inside = {}
    for line in listing.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            inside[parts[1].lstrip("/").removeprefix("app/")] = parts[0]
    mismatched: list[str] = []
    for directory in SOURCE_DIRS:
        for name in tracked_files(directory):
            source = ROOT / name
            if not source.is_file():
                mismatched.append(name + ": tracked in git, missing from the working tree")
            elif name in inside and digest(source) != inside[name]:
                mismatched.append(name + ": bytes differ between tree and image")
            elif name not in inside and source.suffix == ".py":
                mismatched.append(name + ": in the tree but not in the image")
    return mismatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", default="", help="revision the image is supposed to carry (default: HEAD)")
    parser.add_argument("--expect-container", action="store_true",
                        help="also read /app/BUILD_INFO from the running backend container")
    args = parser.parse_args(argv)

    head, dirty = tree_state()
    expected = args.rev or head
    if args.rev and len(args.rev) != len(head) and args.rev.startswith(head):
        expected = head
    stamped = image_revision()
    built = "dirty" if dirty else "clean"

    print("tree        : " + head + " (" + built + " tracked files)")
    print("image label : " + LABEL + "=" + stamped)

    problems: list[str] = []
    if stamped == "<image not present>":
        problems.append("no " + IMAGE + " image on this host")
    elif stamped in {"", "<label absent>", "unknown"}:
        print("verdict     : INCONCLUSIVE -- the image carries no revision stamp, falling back to")
        print("              a byte-for-byte comparison of tracked sources against the container")
        problems.extend(compare_tree_to_container())
    else:
        want = expected + ("+dirty" if dirty else "")
        if stamped != want:
            problems.append(
                "image was built from " + stamped + ", the tree under test is " + want
                + " (rebuild with GIT_SHA set, or re-check the tree)"
            )
        else:
            print("verdict     : MATCH -- image revision label equals " + want)

    if args.expect_container:
        code, text = docker("exec", CONTAINER, "cat", "/app/BUILD_INFO")
        print("BUILD_INFO  : " + (text.strip().replace("\n", " | ") if code == 0 else "unread (container down?)"))

    if problems:
        for line in problems:
            print("FAIL        : " + line)
        print("\nprovenance gate: FAIL")
        return 1
    print("\nprovenance gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
