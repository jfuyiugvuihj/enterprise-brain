"""Name-level corpus parity: repository, seed manifest, and the live knowledge base.

The run used to build the repository side of this check from ``glob("*.txt")``, so every
non-txt file under documents/ sat outside it by construction: two PDFs were tracked by git
for weeks and one of them could never be seeded, and nobody saw it. Here the repository
side is ``git ls-files``, so the choice of suffix cannot hide anything again.

Exit 0 says the corpus a clean install will rebuild is the corpus this machine is
answering from. Any other exit names the disagreement instead of leaving it to be
counted around.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path("deploy") / "workspace-seed.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"
API_PREFIX = "/api/v1"

BUCKETS = (
    "absent_everywhere",
    "server_only",
    "never_seedable",
    "unexplained_live",
    "non_corpus_still_live",
)
#: The buckets that stop a measurement window; server_only is a risk to report, not a gate.
BLOCKING = ("absent_everywhere", "never_seedable", "unexplained_live", "non_corpus_still_live")


class ParityError(RuntimeError):
    """The comparison could not be made, which is not the same as it having failed."""


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ParityError(f"seed manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def tracked_names(root: Path, directory: str) -> set[str]:
    """Names git tracks under the corpus directory: every suffix, no glob involved."""
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "--", directory],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if out.returncode != 0:
        raise ParityError(f"git ls-files failed: {out.stderr.strip()}")
    return {Path(line).name for line in out.stdout.splitlines() if line.strip()}


def compare(
    manifest: dict,
    disk: set[str],
    tracked: set[str],
    live: set[str] | None,
) -> dict:
    """Bucket every disagreement between the manifest, the disk, git, and the index.

    ``live`` is ``None`` when the server leg was skipped: three of the five buckets need it,
    and reporting them as empty would be a lie of the kind that passes checks.

    Two buckets are accepted states of the world rather than failures. ``server_only`` rows
    are demanded by the manifest but exist only inside the volume, so no seed run can
    rebuild them: they are reported as a standing risk, not as a passing grade.
    ``non_corpus`` is the mirror image -- tracked by git and deliberately kept out of the
    knowledge base, with the reason written beside the name in the manifest.
    """
    wanted = {str(name) for name in manifest["documents"]["files"]}
    non_corpus = {str(name) for name in manifest.get("non_corpus", {})}
    have_live = live is not None
    live = live or set()
    return {
        "have_live": have_live,
        "counts": {
            "manifest": len(wanted),
            "disk": len(disk),
            "tracked": len(tracked),
            "live": len(live) if have_live else "n/a",
            "non_corpus": len(non_corpus),
        },
        "absent_everywhere": sorted(wanted - disk - live) if have_live else [],
        "server_only": sorted(wanted - disk) if have_live else [],
        "never_seedable": sorted(tracked - wanted - non_corpus),
        "unexplained_live": sorted(live - tracked - wanted) if have_live else [],
        "non_corpus_still_live": sorted(non_corpus & live) if have_live else [],
        "blocking": BLOCKING,
    }


def label(key: str) -> str:
    return {
        "absent_everywhere": "manifest names with neither a file nor an index row",
        "server_only": "rows only the volume holds, so a reinstall loses them",
        "never_seedable": "tracked in the corpus dir but neither seeded nor declared non-corpus",
        "unexplained_live": "live rows no repo file and no manifest entry accounts for",
        "non_corpus_still_live": "declared non-corpus and still retrievable",
    }[key]


def report(result: dict, not_indexed: list[str] | None) -> list[str]:
    empty: list[str] = []
    lines = ["  counts: " + "  ".join(f"{k}={v}" for k, v in sorted(result["counts"].items()))]
    for key in BUCKETS:
        rows = result[key]
        if not result["have_live"] and key != "never_seedable":
            mark = "n/a "
        elif key in BLOCKING:
            mark = "FAIL" if rows else "ok  "
        else:
            mark = "WARN" if rows else "ok  "
        lines.append(f"  [{mark}] {label(key)}: {rows or empty}")
    if not_indexed is not None:
        mark = "FAIL" if not_indexed else "ok  "
        lines.append(f"  [{mark}] catalog rows that are not indexed: {not_indexed or empty}")
    return lines


def failed(result: dict, not_indexed: list[str] | None) -> bool:
    return any(result[key] for key in result["blocking"]) or bool(not_indexed)


def _env_file_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _login(base_url: str, username: str, password: str) -> str:
    import requests

    session = requests.Session()
    session.trust_env = False
    response = session.post(
        f"{base_url}{API_PREFIX}/login",
        json={"username": username, "password": password},
        timeout=60.0,
    )
    if response.status_code != 200:
        raise ParityError(f"login as {username!r} failed: HTTP {response.status_code} {response.text[:200]}")
    token = str(response.json().get("token") or "")
    if not token:
        raise ParityError(f"the login response for {username!r} carried no token key")
    return token


def _rows(payload: dict) -> list:
    return list(payload.get("documents") or [])


def _live_names(base_url: str, token: str) -> tuple[set[str], list[str]]:
    import requests

    session = requests.Session()
    session.trust_env = False
    session.headers["Authorization"] = f"Bearer {token}"
    response = session.get(
        f"{base_url}{API_PREFIX}/documents",
        params={"page": 1, "page_size": 500},
        timeout=120.0,
    )
    response.raise_for_status()
    # /documents answers with bare filenames while /documents/catalog answers with records,
    # so accept both shapes instead of making every caller remember which is which.
    names = {
        str(row["filename"]) if isinstance(row, dict) else str(row) for row in _rows(response.json())
    }
    catalog = session.get(
        f"{base_url}{API_PREFIX}/documents/catalog",
        params={"page": 1, "page_size": 500},
        timeout=120.0,
    )
    catalog.raise_for_status()
    not_indexed = sorted(
        str(row["filename"])
        for row in _rows(catalog.json())
        if isinstance(row, dict) and row.get("index_status") != "indexed"
    )
    return names, not_indexed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_corpus_parity.py",
        description="Compare corpus names across git, the seed manifest, disk, and the live index.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token-file", default=None)
    parser.add_argument("--token-env", default="EB_SEED_ADMIN_TOKEN")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-env", default="DEMO_ADMIN_PASSWORD")
    parser.add_argument("--env-file", default="deploy/.env.server", help="fallback source for the password")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the server leg, so only the repository-side buckets are judged",
    )
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    manifest_path = args.manifest or (root / DEFAULT_MANIFEST)
    try:
        manifest = load_manifest(manifest_path)
        directory = str(manifest.get("corpus_directory") or "documents")
        tracked = tracked_names(root, directory)
        disk = {path.name for path in (root / directory).iterdir() if path.is_file()}
        live: set[str] | None = None
        not_indexed: list[str] | None = None
        if not args.offline:
            base_url = args.base_url.rstrip("/")
            token = ""
            if args.token_file:
                token = Path(args.token_file).read_text(encoding="utf-8").strip()
            elif os.getenv(args.token_env or "", "").strip():
                token = os.environ[args.token_env].strip()
            else:
                password = os.getenv(args.password_env or "", "")
                if not password:
                    password = _env_file_values(root / args.env_file).get(args.password_env, "")
                if not password:
                    raise ParityError(
                        "no administrator credential: set "
                        f"{args.password_env}, pass --token-file, or use --offline"
                    )
                token = _login(base_url, args.username, password)
            live, not_indexed = _live_names(base_url, token)
    except ParityError as error:
        print(f"corpus parity could not be checked: {error}", file=sys.stderr)
        return 2

    result = compare(manifest, disk, tracked, live)
    for line in report(result, not_indexed):
        print(line)
    verdict = "FAIL" if failed(result, not_indexed) else "PASS"
    print(f"  verdict: {verdict}")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
