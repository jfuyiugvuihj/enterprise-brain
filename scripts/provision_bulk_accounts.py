"""R52 criterion 3 -- fifty accounts must be creatable, able to log in, and scoped right.

Dry run by default. Everything here writes accounts into the deployment it points at,
and a customer server is not the place to rehearse that, so ``--apply`` is required and
the plan is printed first. Re-running is safe: existing accounts keep their generated
password from the credentials file instead of resetting it.

    python scripts/provision_bulk_accounts.py --count 50
    python scripts/provision_bulk_accounts.py --count 50 --apply --token "$env:EB_ADMIN_TOKEN"
    python scripts/provision_bulk_accounts.py --count 30 --roles staff manager admin

--roles rotates over the sample the way --departments does, with one difference: the role
cycles on every account and a department only advances once a whole round of roles is done,
so len(roles) x len(departments) consecutive accounts cover every pairing instead of welding
"manager" to one department forever. Without --roles every account is "staff", which is byte
for byte what this tool sent before the flag existed.

A role the deployment cannot create -- "auditor" today -- is refused in the dry run with exit
code 3 (PLAN_ERROR_EXIT) and not one request sent. This tool does not invent the classification
tier such a role is missing (that is H13, undecided by the owner), does not widen
CREATABLE_ROLES, and does not quietly build the account as staff instead: a sample where three
of four tiers are really one tier is worse than not measuring, because it reads like four tiers
were measured.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 「这一档角色建不建得出来」全仓只有一枚真源，本处只 import（口径同 app/common/sso.py）。
# tests/test_r357_single_role_roster.py 会把 scripts/ 里手抄的角色名单判红，而这里最省事的
# 作弊恰恰是「本地抄一份名单，少一次 import」——那正是 R357 收过的病根。
from app.common.permissions import CREATABLE_ROLES, ROLE_PERMISSIONS  # noqa: E402

DEFAULT_DEPARTMENTS = ["财务部", "销售部", "人事部", "技术部"]
#: 不给 --roles 时的样本：单角色 = 这台量具从 R52 到今天的建号载荷，一字不变（R417 判据①）。
DEFAULT_ROLES = ["staff"]
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

#: 轮换规则一句话：干跑把它打印出来，真跑照着它走。
ROTATION_RULE = ("role cycles every account; a department advances once a full round of roles is "
                 "done, so role x department pairs rotate instead of staying welded together")
#: 样本形状本身不合法（角色建不出、名单为空）⇒ 一次请求都不发就退出。与 1（建号有失败）、
#: 2（argparse 用法错）分家：这台量具的三种"没量成"必须是三个可判定的读数。
PLAN_ERROR_EXIT = 3


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


def build_sample(count: int, prefix: str, departments: list[str], roles: list[str]) -> list[dict]:
    """The whole sample -- username / department / role per account -- computed without any I/O.

    The dry run prints this list and --apply walks it, so the shape on screen cannot disagree with
    the requests that go out. One role collapses the department formula to
    "(index - 1) % len(departments)", i.e. exactly what this tool did before --roles existed.
    """
    return [{"username": prefix + "-" + str(index).zfill(3),
             "department": departments[(index - 1) // len(roles) % len(departments)],
             "role": roles[(index - 1) % len(roles)]}
            for index in range(1, count + 1)]


def tally(sample: list[dict], field: str) -> dict[str, int]:
    """How many accounts carry each value of one field, in first-seen order."""
    counts: dict[str, int] = {}
    for account in sample:
        counts[account[field]] = counts.get(account[field], 0) + 1
    return counts


def sample_shape(sample: list[dict], roles: list[str], departments: list[str]) -> dict:
    """The sample shape as data: counts per role, per department, and how many pairs got covered."""
    pairs = {(account["role"], account["department"]) for account in sample}
    return {"accounts": len(sample), "rotation": ROTATION_RULE,
            "roles": tally(sample, "role"), "departments": tally(sample, "department"),
            "pairings": len(pairs), "possible_pairings": len(roles) * len(departments)}


def _tally_text(counts: dict[str, int]) -> str:
    return ", ".join(name + "=" + str(count) for name, count in counts.items()) or "(none)"


def sample_shape_lines(shape: dict) -> list[str]:
    """The same shape in words, printed while nobody has been asked for a token yet."""
    pairing = "every pairing is covered" if shape["pairings"] == shape["possible_pairings"] else (
        "raise --count to " + str(shape["possible_pairings"]) + " to cover every pairing")
    return ["",
            "sample shape -- computed here, without opening a socket:",
            "  rotation:            " + shape["rotation"],
            "  accounts:            " + str(shape["accounts"]),
            "  per role:            " + _tally_text(shape["roles"]),
            "  per department:      " + _tally_text(shape["departments"]),
            "  role x department:   " + str(shape["pairings"]) + " of " + str(shape["possible_pairings"])
            + " pairs -- " + pairing]


def plan_errors(roles: list[str], departments: list[str], creatable=None, known=None) -> list[str]:
    """Every reason this sample must never go out, in words. An empty list means "carry on".

    creatable/known are parameters only so a test can watch the tool follow its truth source
    instead of a copy of it; the defaults are the real ones, and R413 (with H13) owns whether
    auditor is inside them. This tool answers to that roster, it does not amend it.
    """
    creatable = CREATABLE_ROLES if creatable is None else frozenset(creatable)
    known = ROLE_PERMISSIONS if known is None else known
    errors: list[str] = []
    if not roles:
        errors.append("--roles came out empty: pass at least one role, or leave the flag off and get"
                      " the staff-only sample this tool has produced since R52.")
    if not departments:
        errors.append("--departments came out empty: an account with no department is invisible to"
                      " the retrieval scope (app/rag/filters.py), so rotating over nothing would trade"
                      " a known gap for a fake red instead of measuring anything.")
    stuck = sorted(set(known) - set(creatable))
    for role in list(dict.fromkeys(roles)):
        if role in creatable:
            continue
        if role in known:
            errors.append("role " + repr(role) + " has a permission set but is not in"
                          " CREATABLE_ROLES (app/common/permissions.py), so POST /api/v1/users would"
                          " refuse it and this tool will not paper over that answer. Roles standing in"
                          " that gap today: " + (", ".join(stuck) or "(none)") + ". They stand there"
                          " because a role with no tier in ROLE_CLEARANCE (app/common/rbac.py) can be"
                          " created but cannot be resolved to a classification level, and the"
                          " classification policy is H13: the owner has not decided it. So no tier gets"
                          " invented here, no admission roster gets widened here, and no account gets"
                          " quietly created as staff instead -- a sample that lies about who is who is"
                          " worse than no sample.")
        else:
            errors.append("role " + repr(role) + " is not a role this product knows at all"
                          " (app/common/permissions.py::ROLE_PERMISSIONS). Creatable today: "
                          + (", ".join(sorted(creatable)) or "(none)") + ".")
    return errors


def token_of(login_body: dict) -> str:
    """The JWT out of a /api/v1/login answer.

    app/api/v1/auth.py:83-89 answers under "token" (pinned by tests/test_auth.py:129, and read that
    same way by scripts/eval_transport_ask_v2.py:215). "access_token" stays as the alias for stacks
    built before that shape, never as the first choice: read on its own it always came back empty,
    which made every single account look like it "cannot log in".
    """
    return login_body.get("token") or login_body.get("access_token") or ""


def profile_echo(body: dict) -> dict:
    """The user row behind GET /api/v1/profile, which answers {"profile": {...}}.

    Both levels are read on purpose: app/api/v1/auth.py:249-254 nests the row, so a caller looking
    for "department" on the outer body always got "" back and reported every real account as a
    department mismatch. A flat answer still reads, so this can only ever un-hide the truth.
    """
    inner = body.get("profile")
    return inner if isinstance(inner, dict) else body


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
    parser.add_argument("--roles", nargs="*", default=DEFAULT_ROLES,
                        help="roles to rotate the sample over; every one of them has to be inside"
                             " CREATABLE_ROLES (app/common/permissions.py) or the plan is refused with"
                             " exit code " + str(PLAN_ERROR_EXIT) + " before a single request goes out."
                             " Default: staff only, which is what every account got before this flag.")
    parser.add_argument("--credentials-file", default=os.path.join(
        os.environ.get("TEMP", "."), "r52_bulk_accounts.json"))
    parser.add_argument("--apply", action="store_true", help="actually create the accounts")
    args = parser.parse_args(argv)

    # 先判样本，再谈计划，最后才谈 socket：auditor 这种建不出的角色必须在干跑就撞墙，不许跑到
    # 第 37 枚账号才喊，更不许降级成 staff 继续跑（R417 判据②）。
    refusals = plan_errors(args.roles, args.departments)
    if refusals:
        print("REFUSED -- the sample was rejected before anything was sent; no socket was opened.")
        for line in refusals:
            print("REFUSED " + line)
        print("\nbulk account acceptance: NOT MEASURED (exit " + str(PLAN_ERROR_EXIT) + ")")
        return PLAN_ERROR_EXIT

    sample = build_sample(args.count, args.prefix, args.departments, args.roles)
    shape = sample_shape(sample, args.roles, args.departments)
    # 新键排在 endpoints 之前：干跑那张计划里 endpoints 那一块（连同 "  ]}" 这一行收尾）就此
    # 一字不动，"只增不改"才问得出来（tests/test_r417_bulk_role_mix.py 逐行比对旧输出）。
    plan = {"base_url": args.base_url, "count": args.count, "prefix": args.prefix,
            "departments": args.departments, "roles": args.roles, "sample_shape": shape,
            "endpoints": ["POST /api/v1/users", "POST /api/v1/login",
                          "GET /api/v1/profile", "GET /api/v1/data-files"]}
    if not args.apply:
        print("DRY RUN -- nothing was created, no socket was opened.")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        for line in sample_shape_lines(shape):
            print(line)
        print("\nwhat it will assert once applied:")
        for check in CHECKS:
            print("  - " + check)
        print("\nre-run with --apply against an acceptance stack (not a production one).")
        return 0

    token = args.token
    if not token:
        status, body = api(args.base_url, "/api/v1/login",
                           {"username": args.username, "password": args.password})
        if status != 200 or not token_of(body):
            print("FAIL    administrator login did not yield a token (status " + str(status) + ")")
            return 1
        token = token_of(body)

    credentials = load_credentials(args.credentials_file)
    created, failures = 0, []
    anonymous_status, _ = api(args.base_url, "/api/v1/data-files")
    if anonymous_status not in (401, 403):
        failures.append("anonymous /api/v1/data-files answered " + str(anonymous_status))

    for account in sample:
        name, department, role = account["username"], account["department"], account["role"]
        password = credentials.get(name, {}).get("password") or "".join(
            secrets.choice(PASSWORD_ALPHABET) for _ in range(18))
        status, _ = api(args.base_url, "/api/v1/users",
                        {"username": name, "password": password, "role": role,
                         "department": department}, token=token)
        if status not in (200, 201, 409):
            failures.append(name + ": create answered " + str(status))
            continue
        created += 1
        login_status, login_body = api(args.base_url, "/api/v1/login",
                                       {"username": name, "password": password})
        account_token = token_of(login_body)
        if login_status != 200 or not account_token:
            failures.append(name + ": cannot log in (status " + str(login_status) + ")")
            continue
        profile_status, profile = api(args.base_url, "/api/v1/profile", token=account_token)
        echo = profile_echo(profile)
        if profile_status != 200 or (echo.get("department") or "") != department:
            failures.append(name + ": profile says department=" + repr(echo.get("department"))
                            + ", expected " + department)
        if profile_status == 200 and (echo.get("role") or "staff") != role:
            # 混合角色样本没有这一句就等于没量：越权矩阵要复盘的是"这枚账号到底拿到了哪一档"，
            # 不是"我们请求过哪一档"。CHECKS 第二条早就写着要回显 role，码却一直只看了部门。
            failures.append(name + ": profile says role=" + repr(echo.get("role"))
                            + ", expected " + role)
        files_status, _ = api(args.base_url, "/api/v1/data-files", token=account_token)
        if files_status >= 500:
            failures.append(name + ": /api/v1/data-files answered " + str(files_status))
        credentials[name] = {"password": password, "department": department, "role": role}

    with open(args.credentials_file, "w", encoding="utf-8") as handle:
        json.dump(credentials, handle, ensure_ascii=False, indent=2)
    os.chmod(args.credentials_file, 0o600)
    print("created/verified " + str(created) + " of " + str(args.count) + " accounts; credentials -> "
          + args.credentials_file)
    print("sample was: " + _tally_text(tally(sample, "role")) + " (roles), "
          + _tally_text(tally(sample, "department")) + " (departments)")
    for line in failures:
        print("FAIL    " + line)
    print("\nbulk account acceptance: " + ("PASS" if not failures else str(len(failures)) + " failed"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
