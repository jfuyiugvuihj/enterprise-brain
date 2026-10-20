# -*- coding: utf-8 -*-
"""R577 · 样本账号 + 告警闭环的种子必须「先拒后建、可重跑、不撒谎」。

病（凭据）：``docs/handoff/2026-09-30-v2-gap-recheck-3.md`` —— 演示库 ``users=3``、
``user_profiles=0``、``alerts=0``、``alert_rules=0``，四档权限与 ack→assign→close 至今是空集。
本单喂真数据，不新增业务码，所以钉的全部重量落在**这台喂数据的机器自己会不会撒谎**上。

| 判据 | 钉 |
|---|---|
| ① 干跑先行且零 socket | test_the_dry_run_opens_no_socket_and_prints_the_shape / test_a_short_sample_names_the_missing_tier |
| ② 样本形状四档齐、配对齐、不撞既有账号 | test_the_sample_covers_every_tier_and_pairing / test_roles_come_from_the_true_roster_not_a_copy / test_the_sample_keeps_two_finance_managers_for_the_loop / test_no_sample_username_can_reach_an_existing_account |
| ③ 逐档登录并回显 role/department | test_the_login_check_accepts_an_honest_profile / test_the_login_check_catches_a_profile_that_lies / test_a_missing_credential_is_named_instead_of_skipped |
| ④ 闭环只从带归属的行开始、只问真源状态机 | test_plan_rules_reaches_the_floor_and_names_its_owner / test_the_metric_list_is_read_not_invented / test_unattributed_alert_rows_are_refused / test_the_three_steps_come_out_of_the_shipped_state_machine / test_the_loop_drives_every_step_once_against_the_stub / test_the_loop_refuses_without_two_finance_managers |
| ⑤ 幂等：第二跑不涨 | test_the_second_run_creates_no_rules / test_a_replayed_row_owes_no_more_steps / test_the_second_run_creates_no_accounts_and_rechecks_nothing |
| ⑥ 不外泄口令 | test_the_admin_password_never_rides_the_command_line |

🔴 全程零真机建号、零 HTTP、零 DB：所有对外调用一律把 ``seed.bulk_tool`` 换成 monkeypatch 的桩；
另加一把 ``socket.socket`` 的雷，谁真去开 socket 当场炸（口径同
``tests/test_r417_bulk_role_mix.py`` / ``tests/test_r52_airgap_readiness.py:133``）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import sys
from urllib.parse import unquote
from argparse import Namespace
from pathlib import Path

import pytest
from app.common.permissions import CREATABLE_ROLES

ROOT = Path(__file__).resolve().parents[1]
SEED_REL = "scripts/r577_demo_sample_seed.py"
SEED_PATH = ROOT / SEED_REL
MODULE_NAME = "r577_demo_sample_seed"

#: 在册原件的基线 sha256：反证刀（test_r577_counter_evidence_teeth.py）逐把核它没被改。
SEED_BASELINE_SHA = hashlib.sha256(SEED_PATH.read_bytes()).hexdigest()

#: 演示库里现存的三枚账号（09-19 落的数据主账号与评测机器人）：样本一枚都不许撞上。
EXISTING_ACCOUNTS = ["admin", "dataowner", "evalbot"]


def _load_seed(name: str = MODULE_NAME, path: Path | None = None):
    spec = importlib.util.spec_from_file_location(name, path or SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_seed_copy(tmp_path: Path, name: str, anchor: str = "", replacement: str = ""):
    """把种子读进内存、（可选）按锚点改一处、写成 ``tmp_path`` 副本再单独加载一枚模块。

    锚点不唯一当场红：那把刀等于没动东西。原件永远只读。
    """
    source = SEED_PATH.read_text(encoding="utf-8")
    if anchor:
        hits = source.count(anchor)
        assert hits == 1, f"锚点在原件里出现 {hits} 次，不唯一：这把刀等于没动东西"
        source = source.replace(anchor, replacement)
    path = tmp_path / (name + ".py")
    path.write_text(source, encoding="utf-8")
    module = _load_seed("r577_copy_" + name, path)
    # 副本落在 tmp_path：不把它找邻居脚本的根改回真仓，刀还没落就先死在 import 上。
    module.ROOT = ROOT
    return module
    return _load_seed("r577_copy_" + name, path)


seed = _load_seed()


#: 裁定词表与逐枚裁定的唯一真源（R597 判据①）：本件要引用那一格的裁定词，只从这里现取。
TRIAGE_REL = "scripts/r483_empty_tables_triage.py"


def load_triage():
    """把在册裁定件读进内存（只读）：本件不抄第二份词表，也不改它一个字。"""
    spec = importlib.util.spec_from_file_location("r483_triage_for_r577", ROOT / TRIAGE_REL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TRIAGE = load_triage()


class LandmineSocket:
    """开 socket 就炸：干跑与所有打桩用例的正控都不该走到这里。"""

    def __init__(self, *args, **kwargs):
        raise AssertionError("a socket was opened -- this step must not touch the network")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", LandmineSocket)


def attributed_rows(count: int = 2) -> list[dict]:
    return [{"id": 10 + index, "status": "open", "department": seed.OWNER_DEPARTMENT,
             "assignee": "", "acknowledged_by": "", "closed_by": "", "assigned_by": ""}
            for index in range(1, count + 1)]


class StubBulk:
    """``provision_bulk_accounts`` 的桩：只认已点名的端点，多一枚就报错。

    ``profile="lie-role"`` 让 /api/v1/profile 把角色悄悄降回 staff；``existing_rules``
    决定 GET rules 先交回什么，于是「第二跑」能在同一枚桩上重放。
    """

    PLAN_ERROR_EXIT = 3

    def __init__(self, profile="honest", existing_rules=None, alerts=None):
        self.calls: list[tuple] = []
        self.timeouts: list[tuple] = []
        self.profile = profile
        self.existing_rules = list(existing_rules or [])
        self.created_rules: list[dict] = []
        self.alerts = list(alerts if alerts is not None else attributed_rows())
        self.checks = 0
        self.files = [{"filename": "报销明细表.csv",
                       "profile": {"numeric_columns": ["金额", "出差天数"]}}]
        self.provision_argv: list[list[str]] = []
        self.sample_names: list[str] = []
        self.roster: list[dict] = []
        self.by_name: dict[str, dict] = {}

    # --- 与在册件同名、同形状的那几个出口 -----------------------------------------
    def build_sample(self, count, prefix, departments, roles):
        return [{"username": prefix + "-" + str(index).zfill(3),
                 "department": departments[(index - 1) // len(roles) % len(departments)],
                 "role": roles[(index - 1) % len(roles)]} for index in range(1, count + 1)]

    def sample_shape(self, sample, roles, departments):
        pairs = {(a["role"], a["department"]) for a in sample}
        per = {"roles": {}, "departments": {}}
        for account in sample:
            for field, key in (("role", "roles"), ("department", "departments")):
                per[key][account[field]] = per[key].get(account[field], 0) + 1
        return {"accounts": len(sample), "rotation": "stub rotation", "roles": per["roles"],
                "departments": per["departments"], "pairings": len(pairs),
                "possible_pairings": len(roles) * len(departments)}

    def sample_shape_lines(self, shape):
        return ["", "sample shape -- stub: accounts=" + str(shape["accounts"])]

    def plan_errors(self, roles, departments):
        return [] if roles and departments else ["stub: one of the lists came out empty"]

    def load_credentials(self, path):
        return {name: {"password": "pw-" + name} for name in self.sample_names}

    def token_of(self, body):
        return body.get("token") or body.get("access_token") or ""

    def profile_echo(self, body):
        inner = body.get("profile")
        return inner if isinstance(inner, dict) else body

    def main(self, argv):
        self.provision_argv.append(list(argv))
        return 0

    def api(self, base_url, path, payload=None, token="", timeout: int = 30):
        self.calls.append((path, payload))
        self.timeouts.append((path, timeout))
        if path == "/api/v1/login":
            return 200, {"token": "t-" + str(payload.get("username"))}
        if path == "/api/v1/users":
            return 200, {"users": self.roster}
        if path == "/api/v1/data-files":
            return 200, {"files": [{"filename": row["filename"]} for row in self.files]}
        if path.startswith("/api/v1/data-files/") and path.endswith("/preview"):
            # 真路由会替我们解码路径段：桩照做，否则「带中文的文件名」这一格永远测不出来。
            name = unquote(path.split("/")[4])
            for row in self.files:
                if row["filename"] == name:
                    return 200, {"profile": row["profile"]}
            return 404, {}
        if path == "/api/v1/alerts/rules":
            if payload is None:
                return 200, {"rules": self.existing_rules + self.created_rules}
            self.created_rules.append(dict(payload))
            return 200, {"id": len(self.created_rules)}
        if path == "/api/v1/alerts/check":
            self.checks += 1
            return 200, {"triggered": [], "scan_scope": {}}
        if path == "/api/v1/alerts":
            return 200, {"alerts": self.alerts}
        if path == "/api/v1/profile":
            username = token[2:] if token.startswith("t-") else ""
            account = dict(self.by_name.get(username, {}))
            if self.profile == "lie-role":
                account["role"] = "staff"
            return 200, {"profile": account}
        if "/api/v1/alerts/" in path and path.rsplit("/", 1)[1] in ("ack", "assign", "close"):
            action = path.rsplit("/", 1)[1]
            actor = token[2:] if token.startswith("t-") else ""
            row = next((a for a in self.alerts if int(a.get("id") or 0) == int(path.split("/")[4])), None)
            if row is None:
                return 404, {}
            row = dict(row)
            if action == "ack":
                row.update(status="acknowledged", acknowledged_by=actor)
            elif action == "close":
                row.update(status="closed", closed_by=actor)
            else:
                row.update(assignee=str(payload.get("assignee")), assigned_by=actor)
            for index, stored in enumerate(self.alerts):
                if int(stored.get("id") or 0) == int(row.get("id") or 0):
                    self.alerts[index] = row
            return 200, {"alert": row}
        raise AssertionError("stub was asked for an endpoint it does not know: " + path)


def sample_of(seed_module, count=30, departments=None, roles=None):
    departments = departments or list(seed_module.DEFAULT_DEPARTMENTS)
    roles = roles or seed_module.sample_roles()
    return seed_module.build_sample(count, seed_module.DEFAULT_PREFIX, departments, roles)


def stub_for(sample, profile="honest", alerts=None):
    stub = StubBulk(profile=profile, alerts=alerts)
    stub.sample_names = [a["username"] for a in sample]
    stub.by_name = {a["username"]: {"username": a["username"], "role": a["role"],
                                    "department": a["department"]} for a in sample}
    stub.roster = list(stub.by_name.values())
    return stub


STUB_PREVIEWS = {"报销明细表.csv": {"profile": {"numeric_columns": ["金额", "出差天数"]}}}


class WholeReadingResponse:
    """一枚读到结尾为止的假响应：``read()`` 不带参数＝全量，正是本件要的那一条。"""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.status = 200
        self.read_amount = "never"

    def read(self, amount=None):
        self.read_amount = amount
        return self.payload if amount is None else self.payload[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def preview_opener(payloads: dict):
    """按路径交出画像，与真路由一样收 percent-encoded 那一段。"""
    def open_it(request, timeout=30):
        segments = [part for part in request.full_url.split("/") if part]
        name = unquote(segments[segments.index("data-files") + 1])
        return WholeReadingResponse(json.dumps(payloads.get(name, {})).encode("utf-8"))

    return open_it


def apply_args(sample, password=""):
    return Namespace(base_url="http://x", count=len(sample), prefix=seed.DEFAULT_PREFIX,
                     departments=list(seed.DEFAULT_DEPARTMENTS), roles=seed.sample_roles(),
                     credentials_file="r577-stub-credentials.json",
                     admin_username="admin", admin_password=password, admin_token="")


def json_object(text: str) -> dict:
    """从一段人读的输出里取出第一枚平衡的 JSON 对象（比按花括号切片稳）。"""
    start = text.index("{")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:index + 1])
    raise AssertionError("no balanced JSON object in the output")


# ------------------------------------------------------------------ 判据①：干跑先行且零 socket


def test_the_dry_run_opens_no_socket_and_prints_the_shape(monkeypatch, capsys):
    """autouse 那把雷在场：干跑一路走到 rc=0，一枚 socket 都没开，形状在屏上。"""
    monkeypatch.setattr(seed, "bulk_tool", StubBulk)
    assert seed.main([]) == 0
    printed = capsys.readouterr().out
    assert "DRY RUN" in printed and "no socket was opened" in printed
    plan = json_object(printed)
    assert plan["count"] == 30
    assert set(plan["sample_shape"]["roles"]) == set(CREATABLE_ROLES)
    assert "r577" in plan["credentials_file"]


def test_a_short_sample_names_the_missing_tier():
    """少给一档角色 ⇒ 形状断言先开口并点名缺的那一档（判据①；反证①的正控）。"""
    four_tiers = seed.sample_roles()
    three_tiers = four_tiers[:3]
    victim = four_tiers[3]
    shape = seed.shape_of(sample_of(seed, roles=three_tiers),
                          list(seed.DEFAULT_DEPARTMENTS), three_tiers)

    defects = seed.verify_sample_shape(shape, four_tiers)

    assert defects, "三档样本被当成四档放行了"
    assert victim in defects[0], defects




def test_three_tiers_on_the_command_line_are_refused_not_forgiven(monkeypatch, capsys):
    """`--roles` 少给一档是罪名，不是放行条件：默认拿真源那一整枚名单比（反证①的 CLI 形状）。

    这一格是本单一手量出来的缺陷：形状断言原先只拿「请求过的档位」自比，`--roles staff manager
    admin` 造出一枚四档里少 auditor 的样本，还一路报绿。
    """
    monkeypatch.setattr(seed, "bulk_tool", StubBulk)

    rc = seed.main(["--roles", "staff", "manager", "admin"])
    printed = capsys.readouterr().out

    assert rc == StubBulk.PLAN_ERROR_EXIT, printed
    assert "REFUSED" in printed and "auditor" in printed, printed
    assert "no socket was opened" in printed, printed


def test_the_partial_roster_flag_is_the_only_way_out(monkeypatch, capsys):
    """明知只要一部分档位必须显式给 --allow-partial-roster：放宽不能是一个拼错的默认值。"""
    monkeypatch.setattr(seed, "bulk_tool", StubBulk)

    assert seed.main(["--roles", "staff", "--allow-partial-roster"]) == 0
# ------------------------------------------------------------------ 判据②：样本形状



def test_the_sample_covers_every_tier_and_pairing():
    """30 枚必须四档都有、且 role×department 全覆盖——缺哪格就是那一格没量过。"""
    roles = seed.sample_roles()
    departments = list(seed.DEFAULT_DEPARTMENTS)
    shape = seed.shape_of(sample_of(seed, roles=roles, departments=departments), departments, roles)

    assert shape["accounts"] == seed.DEFAULT_COUNT
    assert set(shape["roles"]) == set(roles), shape["roles"]
    assert set(shape["departments"]) == set(departments), shape["departments"]
    assert shape["pairings"] == shape["possible_pairings"] == len(roles) * len(departments)
    assert seed.verify_sample_shape(shape, roles) == []


def test_roles_come_from_the_true_roster_not_a_copy():
    """角色一律现推自 CREATABLE_ROLES：``scripts/`` 里手抄第二份名单是 R357 判据⑪判红的病。"""
    assert seed.sample_roles() == sorted(CREATABLE_ROLES)
    source = SEED_PATH.read_text(encoding="utf-8")
    assert '"staff", "manager", "admin", "auditor"' not in source
    assert "'staff', 'manager', 'admin', 'auditor'" not in source


def test_the_sample_keeps_two_finance_managers_for_the_loop():
    """闭环要一枚处置人 + 一枚转派目标，且都得既管得了告警又读得到那一行（判据④的前置）。"""
    managers = [a for a in sample_of(seed)
                if a["role"] == "manager" and a["department"] == seed.OWNER_DEPARTMENT]
    assert len(managers) >= 2, managers


def test_no_sample_username_can_reach_an_existing_account():
    """既有三枚账号一枚都不许被样本撞上：撞上就是拿 POST /users 去动别人的字段（判据②）。"""
    names = {a["username"] for a in sample_of(seed)}

    assert names.isdisjoint(EXISTING_ACCOUNTS), sorted(names & set(EXISTING_ACCOUNTS))
    assert all(name.startswith(seed.DEFAULT_PREFIX + "-") for name in names)


# ------------------------------------------------------------------ 判据③：登录与回显


def test_the_login_check_accepts_an_honest_profile(capsys):
    """在册判据原文：profile 回显建号时的 role 与 department —— 一致就零失败，且逐档都点到。"""
    sample = sample_of(seed)
    stub = stub_for(sample)

    failures = seed.verify_logins(stub, "http://x", sample, stub.load_credentials(""))

    assert failures == []
    printed = capsys.readouterr().out
    assert printed.count("profile role/department 一致") == len(seed.sample_roles())


def test_the_login_check_catches_a_profile_that_lies():
    """服务器悄悄把角色降回 staff：混合样本就废了，这一格必须当场报（判据③的牙）。"""
    sample = sample_of(seed)
    stub = stub_for(sample, profile="lie-role")

    failures = seed.verify_logins(stub, "http://x", sample, stub.load_credentials(""))

    downgraded = [role for role in seed.sample_roles() if role != "staff"]
    assert len(failures) == len(downgraded), failures
    assert all("role='staff'" in line for line in failures), failures


def test_a_missing_credential_is_named_instead_of_skipped():
    """凭据文件里没有这一枚 ⇒ 具名失败，不许静默跳过这一档（判据③不许假绿）。"""
    sample = sample_of(seed)
    stub = stub_for(sample)
    credentials = stub.load_credentials("")
    victim = next(a["username"] for a in sample if a["role"] == "auditor")
    credentials.pop(victim)

    failures = seed.verify_logins(stub, "http://x", sample, credentials)

    assert any(victim in line for line in failures), failures


# ------------------------------------------------------------------ 判据④：规则、归属与闭环


def test_plan_rules_reaches_the_floor_and_names_its_owner():
    """规则数下限＝3，且名字里带部门：``alert_rules`` 没有归属列，owner 裁定只能落在名字上。"""
    planned = seed.plan_rules(["金额", "出差天数"])

    assert len(planned) >= seed.MIN_RULES
    assert all(rule["name"].startswith(seed.RULE_NAME_PREFIX) for rule in planned)
    assert all(seed.OWNER_DEPARTMENT in rule["name"] for rule in planned)
    assert all(rule["department"] == seed.OWNER_DEPARTMENT for rule in planned)


def test_the_metric_list_is_read_not_invented():
    """画像不答数值列就回空表：猜一枚指标名＝造一条永不命中的规则，比空集更难看。"""
    assert seed.numeric_columns({"profile": {"numeric_columns": ["金额"]}}) == ["金额"]
    assert seed.numeric_columns({}) == []
    assert seed.numeric_columns({"profile": {}}) == []
    assert seed.numeric_columns({"profile": {"numeric_columns": "金额"}}) == []


def test_unattributed_alert_rows_are_refused():
    """``alerts.department`` 为空的行就是「无归属」：拿它冒充闭环＝把那一格判绿（反证②正控）。

    🔴 R597 连名带断言改口（在册断言只加不减）：docstring 原先手抄了那一格的裁定词，而真源
    ``scripts/r483_empty_tables_triage.py`` 在 R593 已按现读把那一格改了判，那句手抄今天就是过期账。
    本枚钉现在认两件事：① 拒收消息点名的是**表名** ``seed.GUARDED_TABLE``；② 消息里那一枚裁定词与
    真源 ``TRIAGE.TRIAGE[表名]["verdict"]`` 现取的读数逐字相等。真源改口它跟着改口；真源被人删词，
    它跟着红（刀见 docs/testing/r597-*.md）。
    """
    rows = [{"id": 1, "department": ""}, {"id": 2, "department": ""},
            {"id": 3, "department": seed.OWNER_DEPARTMENT}]

    with pytest.raises(ValueError) as refused:
        seed.require_attributed_alerts(rows)
    assert "无归属" in str(refused.value)

    message = str(refused.value)
    verdict = str(TRIAGE.TRIAGE[seed.GUARDED_TABLE]["verdict"])
    assert verdict in TRIAGE.VERDICTS, (verdict, TRIAGE.VERDICTS)
    assert seed.GUARDED_TABLE + " 那一格判绿" in message, message
    assert "今天的裁定＝" + verdict in message, message

    attributed = [{"id": index, "department": seed.OWNER_DEPARTMENT} for index in (1, 2)]
    assert seed.require_attributed_alerts(attributed) == attributed


def test_the_three_steps_come_out_of_the_shipped_state_machine():
    """ack→assign→close 的合法性只问 app 的真源，本件不抄第二份跳转表（判据④）。"""
    steps = seed.pending_disposal_steps({"id": 7, "status": "open", "assignee": ""})

    assert steps == list(seed.DISPOSAL_CHAIN), steps


def test_a_replayed_row_owes_no_more_steps():
    """第二跑读回已关闭的行 ⇒ 一步都不欠；派过人的行不许再派（判据⑤在告警这一半的形状）。"""
    assert seed.pending_disposal_steps({"id": 7, "status": "closed", "assignee": ""}) == [], \
        "已关闭的行还欠步骤：重放不再是幂等"
    assert seed.pending_disposal_steps(
        {"id": 7, "status": "acknowledged", "assignee": "r577-011"}) == ["close"], \
        "派过人的行不许再派一次：那会把「谁接手」改成最后一次点击的人"


def test_the_loop_drives_every_step_once_against_the_stub():
    """真跑那半段的形状：三写各回一次 200，转派目标是另一枚财务部 manager。"""
    sample = sample_of(seed)
    finance = [a["username"] for a in sample
               if a["role"] == "manager" and a["department"] == seed.OWNER_DEPARTMENT]
    kept = attributed_rows()
    stub = stub_for(sample, alerts=kept)

    failures = seed.run_disposal_loop(stub, "http://x", stub.load_credentials(""), sample, kept)

    assert failures == []
    paths = [call[0] for call in stub.calls]
    assert paths == ["/api/v1/login", "/api/v1/alerts/11/ack", "/api/v1/alerts/11/assign",
                     "/api/v1/alerts/11/close", "/api/v1/alerts/12/ack", "/api/v1/alerts"], paths
    assign = next(payload for path, payload in stub.calls if path.endswith("/assign"))
    assert assign["assignee"] in finance and assign["assignee"] != finance[0]


def test_the_loop_refuses_without_two_finance_managers():
    """缺一枚处置人/转派目标就具名拒绝，不许退化成「用 admin 凑一下」——那是另一笔假账。"""
    sample = [a for a in sample_of(seed)
              if (a["role"], a["department"]) != ("manager", seed.OWNER_DEPARTMENT)]
    stub = stub_for(sample)

    failures = seed.run_disposal_loop(stub, "http://x", {}, sample, attributed_rows())

    assert len(failures) == 1 and "manager" in failures[0], failures
    assert stub.calls == [], "缺一枚 manager 还去开了写口"
    assert stub.calls == [], "缺一枚 manager 还去开了写口"


# ------------------------------------------------------------------ 判据⑤/⑥：幂等与口令去处


def test_the_preview_is_read_whole_beyond_the_bulk_helpers_cap():
    """在册件那把 20000 字节的剪刀会把画像剪成 ``(200, {})``：这一枚调用必须自己读完。

    现场实测（2026-10-03，docs/testing/r577-demo-sample-2026-10-03.md）：演示库唯一那份数据集
    ``报销明细表.csv`` 的画像有 **22999 字节**，而 ``provision_bulk_accounts.api`` 按
    ``response.read(20000)`` 取数 —— 截断后 ``json.loads`` 抛 ``JSONDecodeError``，它兜成 ``(200, {})``，
    本件的告警半边就此「读不到数值列」。这不是在册件的错（那是它的报告预算），是告警半边不能借它。
    """
    payload = json.dumps({"profile": {"numeric_columns": ["金额"], "pad": "x" * 30000}}).encode("utf-8")
    assert len(payload) > 20000
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload[:20000])

    seen = []

    def open_it(request, timeout=30):
        response = WholeReadingResponse(payload)
        seen.append(response)
        return response

    status, body = seed.read_json("http://x", "/api/v1/data-files/%E9%87%91%E9%A2%9D/preview",
                                  token="t-1", opener=open_it)

    assert status == 200
    assert seed.numeric_columns(body) == ["金额"], "画像被截断 ⇒ 数值列读不出"
    assert seen and seen[0].read_amount is None, "read() 被给了上限：又回到那把 20000 的剪刀"


def test_discover_metrics_survives_a_truncated_bulk_answer():
    """把 ``bulk.api`` 换成「按 20000 截断」的那副样子，指标名单仍要读得出来（接线那一方）。"""

    class TruncatingBulk(StubBulk):
        """在册件的行为复刻：预览体先垫到 20000 字节以上，再按它的方式截断。"""

        def api(self, base_url, path, payload=None, token="", timeout=30):
            status, body = super().api(base_url, path, payload=payload, token=token)
            if not path.endswith("/preview"):
                return status, body
            padded = dict(body)
            padded["rows"] = [{"pad": "x" * 300} for _ in range(120)]
            capped = json.dumps(padded, ensure_ascii=False).encode("utf-8")[:20000]
            try:
                return status, json.loads(capped or b"{}")
            except json.JSONDecodeError:
                return status, {}

    stub = TruncatingBulk(alerts=attributed_rows())

    metrics, source = seed.discover_metrics(stub, "http://x", "t", opener=preview_opener(STUB_PREVIEWS))

    assert metrics == ["金额", "出差天数"], (metrics, source)
    assert source == "报销明细表.csv"


def test_the_second_run_creates_no_rules():
    """同名的规则已经在了就不再建：规则枚数第二跑不涨（判据⑤的机器形状）。"""
    planned = seed.plan_rules(["金额", "出差天数"])

    assert [r["name"] for r in seed.missing_rules([], planned)] == [r["name"] for r in planned]
    assert seed.missing_rules(planned, planned) == [], "第二跑又要把同名规则建一遍"
    assert seed.missing_rules([{"name": planned[0]["name"]}], planned) == planned[1:]


def test_the_sweep_gets_a_budget_of_its_own(monkeypatch):
    """巡检那一发不许沿用 30 s：首跑就是那 30 s 把一条已经写成的台账读成了崩溃。"""
    sample = sample_of(seed)
    stub = stub_for(sample, alerts=[])
    monkeypatch.setattr(seed, "bulk_tool", lambda: stub)
    stub.files = [{"filename": "报销明细表.csv",
                   "profile": {"numeric_columns": ["金额", "出差天数"]}}]

    seed.run_apply(apply_args(sample), opener=preview_opener(STUB_PREVIEWS))

    sweep = [given for path, given in stub.timeouts if path == "/api/v1/alerts/check"]
    assert sweep == [seed.SWEEP_TIMEOUT], (sweep, seed.SWEEP_TIMEOUT)
    assert seed.SWEEP_TIMEOUT > 30


def test_a_silent_sweep_is_read_back_instead_of_reposted(monkeypatch, capsys):
    """服务端超时 ≠ 没做：本件不许当场补投，只按台账读回来的数判，并把这一格记成失败。"""
    sample = sample_of(seed)
    stub = stub_for(sample, alerts=[])

    original = stub.api

    def timing_out(base_url, path, payload=None, token="", timeout=30):
        if path == "/api/v1/alerts/check":
            stub.checks += 1
            raise TimeoutError("timed out")
        return original(base_url, path, payload=payload, token=token, timeout=timeout)

    stub.api = timing_out
    monkeypatch.setattr(seed, "bulk_tool", lambda: stub)

    rc = seed.run_apply(apply_args(sample), opener=preview_opener(STUB_PREVIEWS))

    printed = capsys.readouterr().out
    assert stub.checks == 1, "超时之后又补投了一次巡检"
    assert "没回话" in printed and "triggered=unknown" in printed
    assert rc == 1, printed


def test_the_second_run_creates_no_accounts_and_rechecks_nothing(monkeypatch, capsys):
    """整条 --apply 路在同一枚桩上重放：建号交回在册件，已有归属行就绝不再触发巡检。"""
    sample = sample_of(seed)
    stub = stub_for(sample, alerts=attributed_rows())
    monkeypatch.setattr(seed, "bulk_tool", lambda: stub)

    rc = seed.run_apply(apply_args(sample), opener=preview_opener(STUB_PREVIEWS))

    assert rc == 0, capsys.readouterr().out
    assert len(stub.provision_argv) == 1, stub.provision_argv
    assert stub.provision_argv[0][:2] == ["--base-url", "http://x"]
    assert stub.checks == 0, "第二跑又触发了一次巡检：alerts 行数会一直涨"
    assert stub.created_rules and all(
        rule["name"].startswith(seed.RULE_NAME_PREFIX) for rule in stub.created_rules)


def test_the_admin_password_never_rides_the_command_line(monkeypatch, capsys):
    """口令走环境变量交进在册件：argv 会被同机任何进程读到，stdout 会被抄进纸里。"""
    sample = sample_of(seed)
    stub = stub_for(sample)
    monkeypatch.setattr(seed, "bulk_tool", lambda: stub)
    monkeypatch.setenv("EB_ADMIN_PASSWORD", "sentinel-from-the-environment")

    seed.run_apply(apply_args(sample, password="sekrit-admin-password"),
                 opener=preview_opener(STUB_PREVIEWS))

    for argv in stub.provision_argv:
        assert "--password" not in argv, argv
        assert "sekrit-admin-password" not in argv, argv
    assert "--username" in stub.provision_argv[0]
    printed = capsys.readouterr().out
    assert "sekrit-admin-password" not in printed, "口令被打进输出了"
    assert os.environ["EB_ADMIN_PASSWORD"] == "sentinel-from-the-environment"


# ------------------------------------------------------------------ 原件账


def test_the_tracked_seed_file_is_read_only_here():
    """本文件全程只读原件：基线 sha 现取一致，反证刀才有「摘回原状」可比的那把尺。"""
    assert hashlib.sha256(SEED_PATH.read_bytes()).hexdigest() == SEED_BASELINE_SHA
