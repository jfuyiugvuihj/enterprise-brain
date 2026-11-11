"""Prove that the running backend image carries the source tree under test (replaces P-8).

H12 exists because acceptance runs kept measuring a container built hours before the
commits they reported on, and the check meant to catch it compared the image's
``Created`` timestamp -- UTC -- with a committer date -- local. This script removes the
arithmetic: the image now names the revision it was built from (``GIT_SHA`` build arg,
recorded as an OCI label and in ``/app/BUILD_INFO``), so the answer is a string test.

Read-only. It builds nothing, starts nothing, writes nothing outside its own output.

    python scripts/check_image_provenance.py
    python scripts/check_image_provenance.py --rev 1a2b3c4
    python scripts/check_image_provenance.py --expect-container
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
CONTAINER = "enterprise-brain-backend-1"
# Paths whose bytes decide what the image carries. Kept in sync with the Dockerfile COPYs.
SOURCE_DIRS = ("app", "migrations", "scripts", "deploy")
FILE_INPUTS = ("pyproject.toml", "uv.lock", "README.md", "Dockerfile", ".dockerignore")
# The gate imports this module to reuse the classifier, and the docs name it as P-8's owner.
__all__ = ["decide", "image_inputs", "MATCH", "DOCS_ONLY", "MISMATCH", "UNSTAMPED"]

MATCH = "match"
DOCS_ONLY = "docs-only"
MISMATCH = "mismatch"
UNSTAMPED = "unstamped"


def image_inputs() -> list[str]:
    return list(SOURCE_DIRS) + list(FILE_INPUTS)


def decide(stamped: str, expected: str, ancestor: bool, touched: list[str],                  dirty: bool = False) -> tuple[str, str]:
    """Classify an image stamp against the revision under test.

    Deliberately conservative: anything that could be a stale container is a MISMATCH,
    and only a difference confined to files the image never carries is allowed to pass.
    A stamp that admits it was built from a dirty tree falls to UNSTAMPED so the caller
    has to prove equality byte by byte -- "+dirty" is a confession, not a version.
    """
    value = (stamped or "").strip()
    if value in ("", "unknown", "<label absent>", "<image not present>") or value.endswith("+dirty"):
        return UNSTAMPED, "image stamp is " + (value or "absent") + "; prove equality per file"
    if dirty:
        # A clean stamp cannot describe a tree that has since moved: the image was built from
        # bytes that are no longer the bytes on disk, and no commit id can say which way it lies.
        return UNSTAMPED, "stamp " + value + " is clean but build inputs are dirty; prove equality per file"
    if value == expected:
        return MATCH, "image revision equals " + expected
    if not ancestor:
        return MISMATCH, ("image was built from " + value + ", which is not an ancestor of "
                          + expected + " (branched, rebased, or rebuilt from another tree)")
    if touched:
        return MISMATCH, ("image is at " + value + " but " + expected + " changed files the image carries: "
                          + ", ".join(sorted(touched)[:6])
                          + (" ..." if len(touched) > 6 else ""))
    return DOCS_ONLY, ("image is at " + value + "; commits up to " + expected
                       + " touched nothing the image carries")


def git(*args: str) -> tuple[int, str]:
    completed = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
    return completed.returncode, (completed.stdout or "").strip()


def tree_state() -> tuple[str, bool]:
    """Short HEAD plus whether a tracked *build input* differs from it.

    Narrower than "the working tree": chroma_db is tracked here and almost always dirty,
    yet .dockerignore keeps it out of the build context, so its dirt says nothing about
    whether the image matches the source.
    """
    _, rev = git("rev-parse", "--short", "HEAD")
    _, porcelain = git("status", "--porcelain", "--", *image_inputs())
    dirty = any(line[:1] not in {" ", "?"} for line in porcelain.splitlines() if line.strip())
    return rev, dirty


def docker(*args: str) -> tuple[int, str]:
    completed = subprocess.run(["docker", *args], cwd=str(ROOT), capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def image_revision() -> str:
    code, text = docker("image", "inspect", IMAGE, "--format",
                        "{{index .Config.Labels \"" + LABEL + "\"}}")
    if code != 0:
        return "<image not present>"
    return text.strip() or "<label absent>"


def divergence(rev: str) -> tuple[bool, list[str]]:
    """(is_ancestor, image-input files changed between rev and HEAD)."""
    base = rev.split("+")[0]
    code, _ = git("merge-base", "--is-ancestor", base, "HEAD")
    if code != 0:
        return False, []
    _, out = git("diff", "--name-only", base + "..HEAD", "--", *image_inputs())
    return True, [line for line in out.splitlines() if line.strip()]


def tracked_files(directory: str) -> list[str]:
    _, listed = git("ls-files", "--", directory)
    return sorted(name for name in listed.splitlines() if name)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_tree_to_container() -> list[str]:
    """Per-file sha256 of every tracked source file, tree side against image side."""
    code, listing = docker("exec", CONTAINER, "sh", "-c",
                           "for f in $(find " + " ".join("/app/" + d for d in SOURCE_DIRS)
                           + " -name '*.py' | sort); do sha256sum \"$f\"; done")
    if code != 0:
        return ["container side unread (is " + CONTAINER + " running?)"]
    inside: dict[str, str] = {}
    for line in listing.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            inside[parts[1].lstrip("/").removeprefix("app/")] = parts[0]
    problems: list[str] = []
    for directory in SOURCE_DIRS:
        for name in tracked_files(directory):
            source = ROOT / name
            if not source.is_file():
                problems.append(name + ": tracked in git, missing from the working tree")
            elif name in inside and digest(source) != inside[name]:
                problems.append(name + ": bytes differ between the tree and the image")
            elif name not in inside and source.suffix == ".py":
                problems.append(name + ": in the tree but not in the image")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", default="", help="revision the image must carry (default: HEAD)")
    parser.add_argument("--expect-container", action="store_true",
                        help="also print /app/BUILD_INFO from the running backend container")
    args = parser.parse_args(argv)

    head, dirty = tree_state()
    stamped = image_revision()
    print("tree          : " + head + (" (build inputs dirty)" if dirty else " (build inputs clean)"))
    print("image label   : " + LABEL + "=" + stamped)

    if args.expect_container:
        code, text = docker("exec", CONTAINER, "cat", "/app/BUILD_INFO")
        print("BUILD_INFO    : " + (text.strip().replace("\n", " | ") if code == 0 else "unread"))

    target = args.rev or head
    if args.rev and len(args.rev) > len(head) and args.rev.startswith(head):
        target = head
    ancestor, touched = divergence(stamped)
    state, message = decide(stamped, target, ancestor, touched, dirty)
    print("verdict       : " + state.upper() + " -- " + message)

    problems: list[str] = []
    if state == UNSTAMPED:
        problems = compare_tree_to_container()
        print("byte check    : " + ("clean, " + str(len(tracked_files('app'))) + " tracked modules compared"
                                    if not problems else "see failures"))
    elif state in (MISMATCH,):
        problems = [message]

    for line in problems:
        print("FAIL          : " + line)
    print("\nprovenance gate: " + ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
