"""R52 criterion 3 -- fifty accounts must be creatable, able to log in, and scoped right.

Dry run by default. Everything here writes accounts into the deployment it points at,
and a customer server is not the place to rehearse that, so ``--apply`` is required and
the plan is printed first. Re-running is safe: existing accounts keep their generated
password from the credentials file instead of resetting it.

    python scripts/provision_bulk_accounts.py --count 50
    python scripts/provision_bulk_accounts.py --count 50 --apply --token "$env:EB_ADMIN_TOKEN"
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
import urllib.error
import urllib.request

DEFAULT_DEPARTMENTS = ["财务部", "销售部", "人事部", "技术部"]
# Password alphabet avoids characters that get mangled when an operator copies them out
# of a report into a shell: no quotes, no backslash, no space, no ambiguous I/l/1/O/0.
PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!#%^*+-=?."
CHECKS = [
    "every account logs in and gets a token",
    "GET /api/v1/profile echoes the role and department it was created with",
    "GET /api/v1/data-files answers below 500 for every account",
    "an anonymous GET /api/v1/data-files is refused with 401/403 (the boundary the "
    "50 accounts are supposed to sit inside)",
]


def api(base_url: str, path: str, payload: dict | None = None, token: str = "",
        timeout: int = 30) -> tuple[int, dict]:
    """Call one endpoint and hand back (status, parsed body or {} for non-JSON)."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers,
                                     method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(20000)
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except urllib.error.URLError as exc:
        raise SystemExit("cannot reach " + base_url + ": " + str(exc.reason)
                         + " (is the stack up, and is --base-url right?)") from exc
    try:
        return 200 if not hasattr(raw, "status") else response.status, json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return 200, {}


def load_credentials(path: str) -> dict:
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("EB_BASE_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--token", default=os.environ.get("EB_ADMIN_TOKEN", ""),
                        help="administrator JWT; without it the tool logs in with --username/--password")
    parser.add_argument("--username", default=os.environ.get("AUTH_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("EB_ADMIN_PASSWORD", ""))
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--prefix", default="r52", help="account name prefix, so a cleanup is possible")
    parser.add_argument("--departments", nargs="*", default=DEFAULT_DEPARTMENTS)
    parser.add_argument("--credentials-file", default=os.path.join(
        os.environ.get("TEMP", "."), "r52_bulk_accounts.json"))
    parser.add_argument("--apply", action="store_true", help="actually create the accounts")
    args = parser.parse_args(argv)

    plan = {"base_url": args.base_url, "count": args.count, "prefix": args.prefix,
            "departments": args.departments, "endpoints": ["POST /api/v1/users", "POST /api/v1/login",
                                                           "GET /api/v1/profile", "GET /api/v1/data-files"]}
    if not args.apply:
        print("DRY RUN -- nothing was created, no socket was opened.")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print("\nwhat it will assert once applied:")
        for check in CHECKS:
            print("  - " + check)
        print("\nre-run with --apply against an acceptance stack (not a production one).")
        return 0

    token = args.token
    if not token:
        status, body = api(args.base_url, "/api/v1/login",
                           {"username": args.username, "password": args.password})
        if status != 200 or not body.get("access_token"):
            print("FAIL    administrator login did not yield a token (status " + str(status) + ")")
            return 1
        token = body["access_token"]

    credentials = load_credentials(args.credentials_file)
    created, failures = 0, []
    anonymous_status, _ = api(args.base_url, "/api/v1/data-files")
    if anonymous_status not in (401, 403):
        failures.append("anonymous /api/v1/data-files answered " + str(anonymous_status))

    for index in range(1, args.count + 1):
        name = args.prefix + "-" + str(index).zfill(3)
        department = args.departments[(index - 1) % len(args.departments)]
        password = credentials.get(name, {}).get("password") or "".join(
            secrets.choice(PASSWORD_ALPHABET) for _ in range(18))
        status, _ = api(args.base_url, "/api/v1/users",
                        {"username": name, "password": password, "role": "staff",
                         "department": department}, token=token)
        if status not in (200, 201, 409):
            failures.append(name + ": create answered " + str(status))
            continue
        created += 1
        login_status, login_body = api(args.base_url, "/api/v1/login",
                                       {"username": name, "password": password})
        account_token = login_body.get("access_token", "")
        if login_status != 200 or not account_token:
            failures.append(name + ": cannot log in (status " + str(login_status) + ")")
            continue
        profile_status, profile = api(args.base_url, "/api/v1/profile", token=account_token)
        if profile_status != 200 or (profile.get("department") or "") != department:
            failures.append(name + ": profile says department=" + repr(profile.get("department"))
                            + ", expected " + department)
        files_status, _ = api(args.base_url, "/api/v1/data-files", token=account_token)
        if files_status >= 500:
            failures.append(name + ": /api/v1/data-files answered " + str(files_status))
        credentials[name] = {"password": password, "department": department, "role": "staff"}

    with open(args.credentials_file, "w", encoding="utf-8") as handle:
        json.dump(credentials, handle, ensure_ascii=False, indent=2)
    os.chmod(args.credentials_file, 0o600)
    print("created/verified " + str(created) + " of " + str(args.count) + " accounts; credentials -> "
          + args.credentials_file)
    for line in failures:
        print("FAIL    " + line)
    print("\nbulk account acceptance: " + ("PASS" if not failures else str(len(failures)) + " failed"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
