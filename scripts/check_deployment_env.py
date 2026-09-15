"""Report env-file values that Docker Compose would silently rewrite.

Compose performs variable substitution inside ``.env`` values, so a literal ``$``
(for example the one inside a bcrypt hash) is replaced by another variable and,
when that variable is unset, becomes an empty string. The application then receives
a corrupted credential with no error anywhere. This check runs on the host before
``docker compose up`` and never prints a value.
"""
from __future__ import annotations

import argparse
from pathlib import Path

# The container refuses to start a production instance without a durable user store,
# and ``app.common.auth`` creates the first administrator from exactly this pair, so an
# environment file that leaves them empty installs a system nobody can sign in to.
ADMIN_BOOTSTRAP_KEYS: tuple[tuple[str, ...], ...] = (
    ("AUTH_USERNAME",),
    ("AUTH_PASSWORD_HASH",),
)

PRODUCTION_ENVIRONMENTS = {"production", "prod"}

REQUIRED_KEYS: tuple[tuple[str, ...], ...] = (
    ("POSTGRES_USER",),
    ("POSTGRES_PASSWORD",),
    ("REDIS_PASSWORD",),
    ("CORS_ALLOW_ORIGINS",),
    ("JWT_SECRET", "JWT_SECRET_KEY"),
)


def parse_env_file(path: str | Path) -> list[tuple[str, str]]:
    """Return ``(key, raw_value)`` pairs for assignment lines only."""
    entries: list[tuple[str, str]] = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and key.replace(".", "_").replace("-", "_").isidentifier():
            entries.append((key, value))
    return entries


def single_dollar_offsets(value: str) -> list[int]:
    """Offsets of ``$`` characters that are not part of a ``$$`` escape."""
    offsets: list[int] = []
    index = 0
    while index < len(value):
        if value[index] != "$":
            index += 1
            continue
        if index + 1 < len(value) and value[index + 1] == "$":
            index += 2
            continue
        offsets.append(index)
        index += 1
    return offsets


def find_interpolation_hazards(entries: list[tuple[str, str]]) -> list[tuple[str, list[int]]]:
    return [(key, single_dollar_offsets(value)) for key, value in entries if single_dollar_offsets(value)]


def missing_required_keys(
    entries: list[tuple[str, str]],
    *,
    required: tuple[tuple[str, ...], ...] = REQUIRED_KEYS,
) -> list[str]:
    """Return the first accepted name of every required group with no value."""
    present = {key for key, value in entries if value.strip()}
    return [group[0] for group in required if not present.intersection(group)]


def needs_admin_bootstrap(entries: list[tuple[str, str]]) -> bool:
    """True when this file drives a production instance, which has no other first user."""
    app_env = dict(entries).get("APP_ENV", "").strip().lower()
    return app_env in PRODUCTION_ENVIRONMENTS


def check_env_file(path: str | Path, *, require_keys: bool = True) -> dict:
    entries = parse_env_file(path)
    missing: list[str] = []
    if require_keys:
        missing = missing_required_keys(entries)
        if needs_admin_bootstrap(entries):
            missing += missing_required_keys(entries, required=ADMIN_BOOTSTRAP_KEYS)
    return {
        "path": str(path),
        "hazards": find_interpolation_hazards(entries),
        "missing": missing,
    }


def format_report(result: dict) -> str:
    lines = [f"env file: {result['path']}"]
    for key, offsets in result["hazards"]:
        positions = ", ".join(str(offset + 1) for offset in offsets)
        lines.append(
            f"  hazard  {key}: contains an unescaped $ at column {positions}; "
            "Compose will substitute it. Write every literal $ as $$."
        )
    for key in result["missing"]:
        origin = (
            "required to create the first administrator (see deploy/README.server.md)"
            if key.startswith("AUTH_")
            else "required by docker-compose.yml"
        )
        lines.append(f"  missing {key}: {origin}")
    if not result["hazards"] and not result["missing"]:
        lines.append("  ok      no interpolation hazards, all required keys present")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", default=".env", help="env file to inspect")
    parser.add_argument(
        "--no-require-keys",
        dest="require_keys",
        action="store_false",
        help="only report Compose interpolation hazards, ignore required keys",
    )
    args = parser.parse_args(argv)
    if not Path(args.env_file).is_file():
        print(f"env file not found: {args.env_file}")
        return 2
    result = check_env_file(args.env_file, require_keys=args.require_keys)
    print(format_report(result))
    return 1 if result["hazards"] or result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
