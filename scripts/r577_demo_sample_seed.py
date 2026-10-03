"""R577 · 把两格「空集」变成「有牙」：四档权限的 30 枚样本账号 + 告警闭环的第一行真数据。

病（凭据）：``docs/handoff/2026-09-30-v2-gap-recheck-3.md`` 现取 —— 演示库里 ``users=3``、
``user_profiles=0``、``alerts=0``、``alert_rules=0``。四档权限（``app/common/rbac.py`` 的
``ROLE_CLEARANCE``，auditor 已随 H13 结案补到第 3 档）从没被一个 10~30 人的样本试过，
ack->assign->close 这条链没有一行真数据 ⇒ V1 的 B 门与 V2 的告警面至今是空集，测不出真假。
本件不新增一行业务码（工单写域：``app/**`` 禁改），只做「把真数据喂进去」这一件事。

**建号这一半直接调用在册量具** ``scripts/provision_bulk_accounts.py``：轮换规则、干跑先行、
凭据文件、四档准入的拒绝支路全在它那一处，本件一枚都不复制（``tests/test_r357_single_role_roster.py``
判据⑪把 ``scripts/`` 里手抄的第二份角色名单判红，所以角色一律现推自
``app.common.permissions.CREATABLE_ROLES``）。

总控裁定（2026-10-03 R577 工单原文，本件照此执行、不当自己的发明）：

- ``alert_rules`` 的 owner = 演示库既有数据主账号 ``dataowner``（``users`` 表里 ``role=staff``、
  ``department=财务部`` 那一枚）。``alert_rules`` 现读没有 owner/department 列（0003 只有
  id/name/metric/op/threshold/enabled），所以这句「归属」只能落在**告警行**上：本件只采纳
  ``alerts.department`` 非空且等于 ``财务部`` 的行做闭环，``migrations/0012`` 那枚归属列空着的行拒收。
- 不给 ``admin`` / ``evalbot`` 加部门（09-28 已裁的 A1 口径，
  ``docs/handoff/2026-09-17-human-gates.md:373``），也不动这两枚既有账号的任何字段。``dataowner``
  的角色同样不改 —— staff 没有 ``alerts:manage``，把它改成 manager 是替别人重写身份，不是补归属。
  闭环里的处置人因此是**新建样本里的财务部 manager**，而不是 admin。
- 口令只写进仓外凭据文件（``--credentials-file``，默认落在 ``%TEMP%``），永不进 git、永不打印。

用法（默认干跑，一次 socket 都不开）：

    python scripts/r577_demo_sample_seed.py
    python scripts/r577_demo_sample_seed.py --base-url http://localhost:8000 --apply

退出码与在册件同一套读法：``0`` 干跑/全部达标；``1`` 真跑有失败；``2`` argparse 用法错；
``3``（``PLAN_ERROR_EXIT``）形状本身不合法 ⇒ 一次请求都不发就退出。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 角色准入的唯一真源，本处只 import（口径同 scripts/provision_bulk_accounts.py）。
from app.common.permissions import CREATABLE_ROLES  # noqa: E402

#: 工单判据②要的形状：30 枚、四档都有。部门名一律演示用名，不碰客户数据。
DEFAULT_COUNT = 30
DEFAULT_PREFIX = "r577"
DEFAULT_DEPARTMENTS = ["研发部", "市场部", "财务部", "法务部"]
#: 总控裁定里 ``dataowner`` 的部门：闭环只认盖了这一枚章的告警行。
OWNER_DEPARTMENT = "财务部"
#: 判据④的下界：规则三条、告警两行，少一条就不是「第一行真数据」而是又一次空集。
MIN_RULES = 3
MIN_ALERTS = 2
#: 巡检那一发的预算。它在服务端要「每条命中问一次模型」（app/api/v1/alerts.py::_ai_analysis），
#: 在册件那 30 s 的默认是它的报告预算，不是这一路的。R577 首跑就在这里 TimeoutError 崩掉，
#: 而服务端其实已经把 4 行都写完了 —— 客户端的等待上限不该决定台账读数的真假。
SWEEP_TIMEOUT = 240
#: 告警闭环的那一条链，顺序即工单原文的 ack -> assign -> close。
DISPOSAL_CHAIN = ("ack", "assign", "close")

#: 计划中的规则名一律带这个前缀：幂等就靠它——第二跑读到同名规则就不再建。
RULE_NAME_PREFIX = "r577-sample"


def sample_roles() -> list[str]:
    """样本要覆盖的角色：真源现推，本件不抄第二份名单（R357 判据⑪）。"""
    return sorted(CREATABLE_ROLES)


def bulk_tool():
    """加载在册量具本身（不是它的副本）：建号、HTTP、凭据文件都走它那一处。"""
    spec = importlib.util.spec_from_file_location(
        "provision_bulk_accounts", ROOT / "scripts" / "provision_bulk_accounts.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - 文件不在树上才是真出事
        raise RuntimeError("cannot load scripts/provision_bulk_accounts.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_sample(count: int, prefix: str, departments: list[str], roles: list[str]) -> list[dict]:
    """样本形状直接问在册件的 ``build_sample`` —— 轮换规则全仓只许有一份。"""
    return bulk_tool().build_sample(count, prefix, departments, roles)


def shape_of(sample: list[dict], departments: list[str], roles: list[str]) -> dict:
    return bulk_tool().sample_shape(sample, roles, departments)


# ------------------------------------------------------------------ 判据①/②：形状（纯函数，可失败）


def verify_sample_shape(shape: dict, roles: list[str]) -> list[str]:
    """样本是否真的四档齐、真的每个 role x department 配对都覆盖到。回的不是布尔，是具名缺陷。

    这一枚是判据①与反证①的落点：三档样本读起来像四档样本，比不测更糟（口径同在册件对
    「降级成 staff」的拒绝）。它只判形状，不建任何东西。
    """
    defects: list[str] = []
    missing = sorted(set(roles) - set(shape.get("roles") or {}))
    if missing:
        defects.append("角色档位缺失: " + ", ".join(missing) + " —— 样本里一枚都没有，四档权限矩阵就缺"
                       "这一行；不许拿三档的读数当四档交回")
    if not shape.get("departments"):
        defects.append("部门一枚都没有: 无部门的账号在检索口径里是隐形的（app/rag/filters.py），"
                       "拿它做样本测不出隔离")
    if shape.get("accounts", 0) <= 0:
        defects.append("样本枚数为 0: --count 要给得出人")
    if shape.get("pairings", 0) != shape.get("possible_pairings", 0):
        defects.append("role x department 覆盖 " + str(shape.get("pairings")) + "/"
                       + str(shape.get("possible_pairings")) + " 对: 越权矩阵要的是每一对都碰过，"
                       "缺一对就是那一对没量过")
    return defects


# ------------------------------------------------------------------ 判据④：规则与告警行（纯函数）


def plan_rules(metrics: list[str], department: str = OWNER_DEPARTMENT,
               min_rules: int = MIN_RULES) -> list[dict]:
    """把可读到的数值列变成计划中的规则，凑够 ``min_rules`` 条为止。

    规则名里带部门：``alert_rules`` 没有归属列，工单的 owner 裁定（dataowner = 财务部）只能落在
    名字与**产出的告警行**上，不许在这里给规则伪造一列。阈值取「一定命中」的两向（gt 极小值 /
    lt 极大值）：本单要的是闭环的第一行真数据，不是又一次零告警。
    """
    planned: list[dict] = []
    for metric in metrics:
        for op, threshold in (("gt", 1.0), ("lt", 1000000000.0)):
            planned.append({
                "name": RULE_NAME_PREFIX + "-" + department + "-" + metric + "-" + op,
                "metric": metric,
                "op": op,
                "threshold": threshold,
                "department": department,
            })
        if len(planned) >= min_rules:
            break
    return planned


def numeric_columns(preview: dict) -> list[str]:
    """从数据画像里取数值列名；画像不答就回空表，不猜（口径同 ``_dataset_department_index``）。"""
    profile = preview.get("profile") or {}
    numeric = profile.get("numeric_columns")
    if isinstance(numeric, list):
        return [str(name) for name in numeric if str(name).strip()]
    return []


def missing_rules(existing: list[dict], planned: list[dict]) -> list[dict]:
    """第二跑该建的那几条：同名规则已存在就不再建（幂等靠名字，不靠自增 id）。"""
    have = {str(rule.get("name") or "") for rule in existing}
    return [rule for rule in planned if str(rule.get("name") or "") not in have]


def attributed_alerts(rows: list[dict], department: str = OWNER_DEPARTMENT) -> list[dict]:
    """只采纳盖了部门章的行；``alerts.department`` 空着的行在这里就是「没归因」。

    这一枚是反证②的牙：needs_owner 那一格真正要拦的是「拿一行无归属的告警冒充闭环」。
    """
    return [row for row in rows if department in str(row.get("department") or "")]


def require_attributed_alerts(rows: list[dict], department: str = OWNER_DEPARTMENT) -> list[dict]:
    """够不够 ``MIN_ALERTS`` 枚带归属的行；不够 ⇒ 具名拒绝，而不是降级去用 ``''`` 行。"""
    kept = attributed_alerts(rows, department)
    if len(kept) < MIN_ALERTS:
        raise ValueError("带部门归因的告警行不足 " + str(MIN_ALERTS) + " 枚（现 " + str(len(kept))
                         + " 枚，总行数 " + str(len(rows)) + "）: alerts.department 为空的行是「无归属」，"
                         "拿它走闭环等于把 needs_owner 那一格判绿 —— 拒收，不是放宽")
    return kept


def _disposal_guard(action: str, current_status: str) -> bool:
    """状态机只问真源（app/api/v1/alerts.py::alert_disposal_guard），本件不抄第二份跳转表。"""
    from app.api.v1.alerts import alert_disposal_guard

    return alert_disposal_guard(action, current_status)


def pending_disposal_steps(row: dict, guard=None) -> list[str]:
    """这一行还欠闭环链里的哪几步：已派过的不重派，非法跳转由真源裁。

    幂等靠它：第二跑读回 ``closed`` 行 ⇒ 回空表，一条 UPDATE 都不发。
    """
    guard = _disposal_guard if guard is None else guard
    status = str(row.get("status") or "open")
    pending: list[str] = []
    for action in DISPOSAL_CHAIN:
        if action == "assign" and str(row.get("assignee") or "").strip():
            continue
        if guard(action, status):
            pending.append(action)
    return pending


# ------------------------------------------------------------------ 真跑（只在 --apply 下开口）


def admin_token(bulk, base_url: str, username: str, password: str) -> str:
    status, body = bulk.api(base_url, "/api/v1/login", {"username": username, "password": password})
    if status != 200 or not bulk.token_of(body):
        raise RuntimeError("administrator login did not yield a token (status " + str(status) + ")")
    return bulk.token_of(body)


def tier_representatives(sample: list[dict]) -> dict[str, dict]:
    """逐档各点一枚：取该档在样本里的第一枚。"""
    chosen: dict[str, dict] = {}
    for account in sample:
        chosen.setdefault(account["role"], account)
    return chosen


def verify_logins(bulk, base_url: str, sample: list[dict], credentials: dict) -> list[str]:
    """登录取 token，再现读 /api/v1/profile 回显的 role/department 与建号时是否一致。

    在册判据原文是 "GET /api/v1/profile echoes the role and department it was created with"，
    回显的读法沿用 ``bulk.profile_echo``（嵌套两层都认），本件不另写一套。
    """
    failures: list[str] = []
    for role, account in sorted(tier_representatives(sample).items()):
        name = account["username"]
        password = str((credentials.get(name) or {}).get("password") or "")
        if not password:
            failures.append(role + ": 凭据文件里没有 " + name + " 的口令，登录无从谈起")
            continue
        status, body = bulk.api(base_url, "/api/v1/login", {"username": name, "password": password})
        token = bulk.token_of(body)
        if status != 200 or not token:
            failures.append(role + ": " + name + " 登录不成（status " + str(status) + "）")
            continue
        profile_status, profile = bulk.api(base_url, "/api/v1/profile", token=token)
        echo = bulk.profile_echo(profile)
        if profile_status != 200:
            failures.append(role + ": " + name + " 读 profile 回了 " + str(profile_status))
            continue
        mismatches = [field + "=" + repr(str(echo.get(field) or "")) + "（建号时要的是 "
                      + repr(expected) + "）"
                      for field, expected in (("role", account["role"]),
                                              ("department", account["department"]))
                      if str(echo.get(field) or "") != expected]
        if mismatches:
            failures.append(role + ": " + name + " 的 profile 不回原样: " + ", ".join(mismatches))
        else:
            print("LOGIN   " + role + " " + name + " -> profile role/department 一致")
    return failures


def read_roster(bulk, base_url: str, token: str) -> list[dict]:
    status, body = bulk.api(base_url, "/api/v1/users", token=token)
    if status != 200:
        raise RuntimeError("GET /api/v1/users answered " + str(status))
    return list(body.get("users") or [])


def roster_tally(rows: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "(null)")
        counts[key] = counts.get(key, 0) + 1
    return counts


def alert_reading(row: dict) -> str:
    """一行告警的读数，进纸用：状态、归属、处置三组人。不含正文。"""
    return ("id=" + str(row.get("id")) + " status=" + str(row.get("status") or "open")
            + " department=" + repr(str(row.get("department") or ""))
            + " acknowledged_by=" + repr(str(row.get("acknowledged_by") or ""))
            + " assignee=" + repr(str(row.get("assignee") or ""))
            + " assigned_by=" + repr(str(row.get("assigned_by") or ""))
            + " closed_by=" + repr(str(row.get("closed_by") or "")))


def read_json(base_url: str, path: str, token: str = "", timeout: int = 30,
              opener=None) -> tuple[int, dict]:
    """整份读完再解析。**只有这一枚调用不走在册件的 ``api()``**，理由是一枚实测数字。

    ``provision_bulk_accounts.api`` 把响应截到 20000 字节（那是它自己的报告预算，不是接口契约），
    而演示库里唯一那份数据集的画像有 22999 字节：截断 ⇒ ``json.loads`` 抛 ``JSONDecodeError`` ⇒
    它按 ``(200, {})`` 交回，本件的告警半边就此读不出数值列（R577 首跑现场量出来的，
    凭据见 ``docs/testing/r577-demo-sample-2026-10-03.md``）。要的是列名，不是摘要，所以自己读完。
    """
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base_url.rstrip("/") + path, headers=headers)
    open_it = urllib.request.urlopen if opener is None else opener
    try:
        with open_it(request, timeout=timeout) as response:
            body = response.read()
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except urllib.error.URLError as exc:
        raise SystemExit("cannot reach " + base_url + ": " + str(exc.reason)) from exc
    try:
        return status, json.loads(body or b"{}")
    except json.JSONDecodeError:
        return status, {}


def discover_metrics(bulk, base_url: str, token: str, opener=None) -> tuple[list[str], str]:
    """从真数据集里现读一枚可用的数值列名单；读不到就回空表并说清是哪一份。"""
    status, body = bulk.api(base_url, "/api/v1/data-files", token=token)
    if status != 200:
        raise RuntimeError("GET /api/v1/data-files answered " + str(status))
    for row in list(body.get("files") or []):
        name = str(row.get("filename") or "")
        if not name:
            continue
        # 文件名可以带中文：路径段必须转义，否则 urllib 在 _encode_request 里直接 ASCII 崩。
        preview_status, preview = read_json(
            base_url, "/api/v1/data-files/" + quote(name, safe="") + "/preview",
            token=token, opener=opener)
        if preview_status != 200:
            continue
        metrics = numeric_columns(preview)
        if metrics:
            return metrics, name
    return [], ""


def run_disposal_loop(bulk, base_url: str, credentials: dict, sample: list[dict],
                      kept: list[dict]) -> list[str]:
    """处置人 = 新建样本里财务部的一枚 manager；目标行按 id 升序取前两枚。"""
    failures: list[str] = []
    handlers = [a for a in sample
                if a["role"] == "manager" and a["department"] == OWNER_DEPARTMENT]
    if len(handlers) < 2:
        return ["样本里没有两枚 " + OWNER_DEPARTMENT + " manager: 闭环缺一枚当处置人、一枚当转派目标"]
    handler, assignee = handlers[0], handlers[1]["username"]
    password = str((credentials.get(handler["username"]) or {}).get("password") or "")
    status, login_body = bulk.api(base_url, "/api/v1/login",
                                  {"username": handler["username"], "password": password})
    handler_token = bulk.token_of(login_body)
    if status != 200 or not handler_token:
        return ["处置人 " + handler["username"] + " 登录不成（status " + str(status) + "）"]

    ordered = sorted(kept, key=lambda row: int(row.get("id") or 0))
    target, witness = ordered[0], ordered[1]
    print("[r577] 闭环目标行 处置前: " + alert_reading(target))
    for action in pending_disposal_steps(target):
        path = "/api/v1/alerts/" + str(target["id"]) + "/" + action
        payload = {"assignee": assignee} if action == "assign" else {}
        action_status, action_body = bulk.api(base_url, path, payload, token=handler_token)
        print("[r577] " + action + " 退出码 = " + str(action_status))
        if action_status != 200:
            failures.append(action + " 回了 " + str(action_status))
            break
        target = dict((action_body or {}).get("alert") or {})
        print("[r577] " + action + " 之后: " + alert_reading(target))
    witness_status, _ = bulk.api(base_url, "/api/v1/alerts/" + str(witness["id"]) + "/ack",
                                 {}, token=handler_token)
    print("[r577] 第二行 id=" + str(witness["id"]) + " ack 退出码 = " + str(witness_status))
    if witness_status != 200:
        failures.append("第二行 ack 回了 " + str(witness_status))
    status, body = bulk.api(base_url, "/api/v1/alerts", token=handler_token)
    wanted = {int(target.get("id") or 0), int(witness.get("id") or 0)}
    for row in list((body or {}).get("alerts") or []):
        if int(row.get("id") or 0) in wanted:
            print("[r577] 终态读数: " + alert_reading(row))
    return failures


def run_apply(args, opener=None) -> int:
    bulk = bulk_tool()
    base_url = args.base_url
    sample = build_sample(args.count, args.prefix, args.departments, args.roles)
    failures: list[str] = []

    argv = ["--base-url", base_url, "--count", str(args.count), "--prefix", args.prefix,
            "--departments", *args.departments, "--roles", *args.roles,
            "--credentials-file", args.credentials_file, "--apply"]
    if args.admin_token:
        argv += ["--token", args.admin_token]
    else:
        argv += ["--username", args.admin_username]
    # 口令走环境变量交进在册件，不进 argv（argv 会被同机的别的进程读到），也不进任何输出。
    previous = os.environ.get("EB_ADMIN_PASSWORD")
    os.environ["EB_ADMIN_PASSWORD"] = args.admin_password
    try:
        rc = bulk.main(argv)
    finally:
        if previous is None:
            os.environ.pop("EB_ADMIN_PASSWORD", None)
        else:
            os.environ["EB_ADMIN_PASSWORD"] = previous
    print("[r577] provision_bulk_accounts 退出码 = " + str(rc))
    credentials = bulk.load_credentials(args.credentials_file)

    token = args.admin_token or admin_token(bulk, base_url, args.admin_username, args.admin_password)

    roster = read_roster(bulk, base_url, token)
    print("[r577] 库内 role 分布: " + ", ".join(
        f"{key}={roster_tally(roster, 'role')[key]}" for key in sorted(roster_tally(roster, 'role'))))
    print("[r577] 库内 department 分布: " + ", ".join(
        f"{key}={roster_tally(roster, 'department')[key]}"
        for key in sorted(roster_tally(roster, 'department'))))

    # 存量账号不是失败：在册件对已存在的用户名答 POST /users 400，第二跑必然非零退出。
    # 这里按名册逐字段核对来裁定「幂等命中」还是「真没建成」，不拿 rc 当唯一读数，也不拿它当免死金牌。
    present = {str(row.get("username") or ""): row for row in roster}
    absent = [a["username"] for a in sample if a["username"] not in present]
    diverged = [a["username"] + " role=" + repr(str(present[a["username"]].get("role") or ""))
                + " department=" + repr(str(present[a["username"]].get("department") or ""))
                for a in sample
                if a["username"] in present
                and (str(present[a["username"]].get("role") or "") != a["role"]
                     or str(present[a["username"]].get("department") or "") != a["department"])]
    print("[r577] 样本在册核对: " + str(len(sample) - len(absent)) + "/" + str(len(sample))
          + " 枚已在名册里, 角色或部门对不上的 " + str(len(diverged)) + " 枚")
    if absent:
        failures.append("样本里有 " + str(len(absent)) + " 枚没进名册: " + ", ".join(absent[:5])
                        + ("..." if len(absent) > 5 else ""))
    failures.extend("样本 " + item + " 与名册不一致" for item in diverged)
    if rc != 0 and not absent and not diverged:
        print("[r577] 在册件退出码非零但 30 枚逐字段都在册：按幂等命中处理（存量账号答 400 是它的原样）")

    failures += verify_logins(bulk, base_url, sample, credentials)

    status, body = bulk.api(base_url, "/api/v1/alerts/rules", token=token)
    if status != 200:
        raise RuntimeError("GET /api/v1/alerts/rules answered " + str(status))
    existing_rules = list(body.get("rules") or [])
    metrics, metric_source = discover_metrics(bulk, base_url, token, opener=opener)
    if metrics:
        print("[r577] 指标取自数据集 " + metric_source + ": " + ", ".join(metrics))
    else:
        failures.append("没有从任何数据集读到数值列: 规则建不出指标，告警面这一半就没喂进数据")
    planned = plan_rules(metrics)
    to_create = missing_rules(existing_rules, planned)
    for rule in to_create:
        created_status, _ = bulk.api(base_url, "/api/v1/alerts/rules", {
            "name": rule["name"], "metric": rule["metric"], "op": rule["op"],
            "threshold": rule["threshold"]}, token=token)
        if created_status not in (200, 201):
            failures.append("建规则 " + rule["name"] + " 回了 " + str(created_status))
    print("[r577] 规则: 计划 " + str(len(planned)) + " 条, 已存在 "
          + str(len(planned) - len(to_create)) + " 条, 本轮新建 " + str(len(to_create)) + " 条")

    status, body = bulk.api(base_url, "/api/v1/alerts/rules", token=token)
    all_rules = list((body or {}).get("rules") or [])
    mine = [r for r in all_rules if str(r.get("name") or "").startswith(RULE_NAME_PREFIX)]
    print("[r577] 带 " + RULE_NAME_PREFIX + " 前缀的规则数 = " + str(len(mine)))
    if len(mine) < MIN_RULES:
        failures.append("带 " + RULE_NAME_PREFIX + " 前缀的规则只有 " + str(len(mine)) + " 条，不足 "
                        + str(MIN_RULES) + " 条")

    status, body = bulk.api(base_url, "/api/v1/alerts", token=token)
    if status != 200:
        raise RuntimeError("GET /api/v1/alerts answered " + str(status))
    alert_rows = list(body.get("alerts") or [])
    before_check = len(alert_rows)
    if len(attributed_alerts(alert_rows)) < MIN_ALERTS:
        # 超时不当崩，也不当场补投：服务端可能已经写完这一批，那就按台账读回来的数判。
        try:
            check_status, check_body = bulk.api(base_url, "/api/v1/alerts/check", {}, token=token,
                                                timeout=SWEEP_TIMEOUT)
            triggered = str(len(list((check_body or {}).get("triggered") or [])))
        except (TimeoutError, OSError) as exc:
            check_status, triggered = 0, "unknown"
            failures.append("POST /api/v1/alerts/check 在 " + str(SWEEP_TIMEOUT)
                            + " s 内没回话（" + type(exc).__name__ + "）：不重发，下面按台账读数判")
        print("[r577] POST /api/v1/alerts/check 退出码 = " + str(check_status)
              + " triggered=" + triggered + " (timeout=" + str(SWEEP_TIMEOUT) + "s)")
        status, body = bulk.api(base_url, "/api/v1/alerts", token=token, timeout=60)
        alert_rows = list((body or {}).get("alerts") or [])
    else:
        print("[r577] 已有带归属的告警行，本轮不再触发巡检（幂等）")
    print("[r577] alerts 行数: 巡检前 " + str(before_check) + " -> 现 " + str(len(alert_rows)))

    try:
        kept = require_attributed_alerts(alert_rows)
    except ValueError as exc:
        failures.append(str(exc))
        kept = []
    if kept:
        failures += run_disposal_loop(bulk, base_url, credentials, sample, kept)

    for line in failures:
        print("FAIL    " + line)
    print("\nr577 demo sample: " + ("PASS" if not failures else str(len(failures)) + " failed"))
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("EB_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--departments", nargs="*", default=list(DEFAULT_DEPARTMENTS))
    parser.add_argument("--roles", nargs="*", default=None,
                        help="默认现推自 CREATABLE_ROLES（四档全要）；本件不抄第二份角色名单")
    parser.add_argument("--credentials-file", default=os.path.join(
        os.environ.get("TEMP", "."), "r577-demo-sample-credentials.json"))
    parser.add_argument("--admin-username", default=os.environ.get("AUTH_USERNAME", "admin"))
    parser.add_argument("--admin-password", default=os.environ.get("DEMO_ADMIN_PASSWORD", ""))
    parser.add_argument("--admin-token", default=os.environ.get("EB_ADMIN_TOKEN", ""))
    parser.add_argument("--apply", action="store_true", help="真建号、真造规则、真走闭环")
    parser.add_argument("--allow-partial-roster", action="store_true",
                        help="明知只要一部分档位时才给。默认要求样本覆盖 CREATABLE_ROLES 的每一档，"
                             "少一档就按 PLAN_ERROR_EXIT 拒（判据①的反证①）")
    args = parser.parse_args(argv)
    if args.roles is None:
        args.roles = sample_roles()

    bulk = bulk_tool()
    refusals = bulk.plan_errors(args.roles, args.departments)
    if refusals:
        print("REFUSED -- the sample was rejected before anything was sent; no socket was opened.")
        for line in refusals:
            print("REFUSED " + line)
        print("\nr577 demo sample: NOT MEASURED (exit " + str(bulk.PLAN_ERROR_EXIT) + ")")
        return bulk.PLAN_ERROR_EXIT

    sample = build_sample(args.count, args.prefix, args.departments, args.roles)
    shape = shape_of(sample, args.departments, args.roles)
    # 「少给一档角色」不能既是罪名又是放行条件：默认拿真源那一整枚名单比，
    # 否则 `--roles staff manager admin` 会造出一枚「四档里少一档」的样本还报绿（反证①）。
    required = args.roles if args.allow_partial_roster else sample_roles()
    defects = verify_sample_shape(shape, required)
    if defects:
        print("REFUSED -- the sample shape itself is short; no socket was opened.")
        for line in defects:
            print("REFUSED " + line)
        print("\nr577 demo sample: NOT MEASURED (exit " + str(bulk.PLAN_ERROR_EXIT) + ")")
        return bulk.PLAN_ERROR_EXIT

    plan = {"base_url": args.base_url, "count": args.count, "prefix": args.prefix,
            "departments": args.departments, "roles": args.roles, "required_roles": required,
            "sample_shape": shape,
            "owner_department": OWNER_DEPARTMENT, "min_rules": MIN_RULES, "min_alerts": MIN_ALERTS,
            "disposal_chain": list(DISPOSAL_CHAIN), "credentials_file": args.credentials_file,
            "reused_from_instrument": "scripts/provision_bulk_accounts.py",
            "endpoints": ["POST /api/v1/users", "POST /api/v1/login", "GET /api/v1/profile",
                          "GET /api/v1/users", "GET /api/v1/data-files",
                          "GET /api/v1/data-files/{name}/preview", "POST /api/v1/alerts/rules",
                          "GET /api/v1/alerts/rules", "POST /api/v1/alerts/check",
                          "GET /api/v1/alerts", "POST /api/v1/alerts/{id}/ack",
                          "POST /api/v1/alerts/{id}/assign", "POST /api/v1/alerts/{id}/close"]}
    if not args.apply:
        print("DRY RUN -- nothing was created, no socket was opened.")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        for line in bulk.sample_shape_lines(shape):
            print(line)
        print("\nwhat this seed asserts before it calls anything done:")
        for line in [
            "  - every tier of CREATABLE_ROLES shows up in the sample (a missing tier refuses"
            " the plan)",
            "  - role x department pairings are all covered",
            "  - one account per tier logs in and /api/v1/profile echoes role + department",
            "  - at least " + str(MIN_RULES) + " rules named " + RULE_NAME_PREFIX + "* exist",
            "  - at least " + str(MIN_ALERTS) + " alert rows carry a non-empty "
            + OWNER_DEPARTMENT + " attribution (migrations/0012 department column)",
            "  - " + " -> ".join(DISPOSAL_CHAIN) + " replays through the shipped state machine"
            " (app/api/v1/alerts.py::alert_disposal_guard)",
            "  - a second run creates neither accounts nor rules",
        ]:
            print(line)
        print("\nrun with --apply against the demo stack; credentials land in "
              + args.credentials_file + " (outside the repository).")
        return 0

    return run_apply(args)


if __name__ == "__main__":
    sys.exit(main())
