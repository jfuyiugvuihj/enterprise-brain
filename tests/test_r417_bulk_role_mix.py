"""R417 · 批量建号量具要造得出混合角色样本，而 auditor 那一档必须诚实失败。

病（凭据）：docs/version-roadmap-and-next-week-plan-2026-09-22.md:277-278 要「10～30 名内部
用户」与「跨部门和跨密级越权命中为 0」，而 scripts/provision_bulk_accounts.py 唯一的建号点把
角色写死成 staff（部门可轮换、角色不可轮换）⇒ 四档权限里只有一档造得出来，这一条因此判「未落」
（docs/handoff/2026-09-27-v2-gap-recheck-2.md §2.3 第 19 行）。

钉与判据对照：

| 判据 | 钉 |
|---|---|
| ① 默认路径逐字节不变 | test_without_the_flag_keeps_the_original_rotation / test_default_apply_requests_match_the_pre_flag_tool |
| ② 轮换规则有牙（不许把角色与部门绑死） | test_roles_and_departments_are_not_welded_together / test_the_same_arguments_always_produce_the_same_sample |
| ③ auditor 当场拒、零请求 | test_auditor_is_refused_without_a_single_request / test_auditor_refusal_holds_under_apply / test_the_refusal_asks_the_true_roster_not_a_copy |
| ④ 干跑零 socket | autouse 把 urlopen 打雷 + test_dry_run_opens_no_socket_and_sends_nothing |
| ⑤ 凭证带真角色 | test_credentials_file_records_the_real_role |
| ⑥ 动手前看得清形状 | test_plan_output_shows_the_sample_shape / test_the_plan_cannot_lie_about_the_sample |

🔴 全程零真机建号：--apply 的用例一律把 bulk.api 换成桩，桩只认已点名的四枚端点（多一枚就报错）；
那把雷保证有人真去开 socket 时当场炸（口径同 tests/test_r52_airgap_readiness.py:133）。角色名单一律
问真源，本文件不抄第二份（tests/test_r357_single_role_roster.py 的判据⑪把 scripts/ 里的手抄名单判红，
tests/** 是用例矩阵不在它射程内）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from app.common.permissions import CREATABLE_ROLES

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bulk = _load("provision_bulk_accounts")

#: 今天建得出的三档（auditor 归 R413 与 H13，本文件不替它编档位）。
THREE_TIERS = ["staff", "manager", "admin"]


class StubApi:
    """Stand-in for bulk.api: records every request and answers the way the real routes answer.

    profile_shape="nested" is the real shape (app/api/v1/auth.py:249-254 answers {"profile": {...}});
    "flat" is the shape the tool used to assume, kept so the readback pin says which one it survived.
    login_key picks the spelling a /api/v1/login answer carries; None means it carries neither.
    role_lie makes the server quietly downgrade the admission it was asked for -- exactly what the
    role readback has to catch, because a mixed sample nobody verified is not a mixed sample.
    """

    def __init__(self, profile_shape="nested", login_key="token", role_lie=False, anonymous=403):
        self.profile_shape = profile_shape
        self.login_key = login_key
        self.role_lie = role_lie
        self.anonymous = anonymous
        self.calls = []
        self.rows = {}

    def __call__(self, base_url, path, payload=None, token="", timeout=30):
        self.calls.append({"path": path, "payload": payload, "token": token})
        if path == "/api/v1/users":
            row = dict(payload or {})
            if self.role_lie:
                row["role"] = "staff"
            self.rows[row.get("username", "")] = row
            return 201, {"status": "ok"}
        if path == "/api/v1/login":
            username = (payload or {}).get("username", "")
            if not self.login_key:
                return 200, {}
            return 200, {self.login_key: "jwt-" + username}
        if path == "/api/v1/profile":
            username = token[4:] if token.startswith("jwt-") else ""
            row = dict(self.rows.get(username, {}))
            row.setdefault("username", username)
            return 200, {"profile": row} if self.profile_shape == "nested" else row
        if path == "/api/v1/data-files":
            return (self.anonymous, {}) if not token else (200, {})
        raise AssertionError("this tool called an endpoint no pin covers: " + path)


@pytest.fixture(autouse=True)
def _never_open_a_real_socket(monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("provision_bulk_accounts opened a socket")

    monkeypatch.setattr(bulk.urllib.request, "urlopen", _explode)


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    for name in ("EB_ADMIN_TOKEN", "EB_BASE_URL", "AUTH_USERNAME", "EB_ADMIN_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def install(monkeypatch):
    """Put the stub in place of bulk.api and hand it back, so counts are readable."""
    def _install(**kwargs):
        stub = StubApi(**kwargs)
        monkeypatch.setattr(bulk, "api", stub)
        return stub

    return _install


def _credentials(tmp_path, name="r417_credentials.json") -> str:
    return str(tmp_path / name)


def _apply(tmp_path, extra, name="r417_credentials.json") -> list[str]:
    return ["--apply", "--base-url", "http://stack.test", "--token", "ADMIN",
            "--credentials-file", _credentials(tmp_path, name)] + extra


def _dry(tmp_path, extra=(), name="r417_dry.json") -> list[str]:
    return ["--credentials-file", _credentials(tmp_path, name)] + list(extra)


def _plan(stdout: str) -> dict:
    """The plan the dry run printed, as data (its first line is the DRY RUN promise)."""
    return json.loads(stdout.split("\n", 1)[1].split("\nsample shape", 1)[0])


def _saved(tmp_path, name="r417_credentials.json") -> dict:
    return json.loads(Path(_credentials(tmp_path, name)).read_text(encoding="utf-8"))


# ------------------------------------------------------------ 判据①：默认路径一字不变


def test_without_the_flag_keeps_the_original_rotation():
    """不给 --roles：单角色 + 部门按下标取模 = 这台量具从 R52 到今天的样子。"""
    assert bulk.DEFAULT_ROLES == ["staff"]
    sample = bulk.build_sample(50, "r52", bulk.DEFAULT_DEPARTMENTS, bulk.DEFAULT_ROLES)
    for index, account in enumerate(sample, start=1):
        assert account["role"] == "staff"
        assert account["department"] == bulk.DEFAULT_DEPARTMENTS[(index - 1) % 4]


def test_default_apply_requests_match_the_pre_flag_tool(tmp_path, install):
    """默认路径的请求：载荷键序、role=staff、部门公式、请求次数、退出码，全部照旧。"""
    stub = install()
    assert bulk.main(_apply(tmp_path, ["--count", "9"])) == 0

    creates = [call for call in stub.calls if call["path"] == "/api/v1/users"]
    assert len(creates) == 9, "一枚账号一次建号请求，不多不少"
    assert len(stub.calls) == 1 + 9 * 4, "匿名巡检 1 次 + 逐号（建号/登录/画像/数据文件）4 次"
    assert stub.calls[0]["path"] == "/api/v1/data-files" and stub.calls[0]["token"] == ""
    for index, call in enumerate(creates, start=1):
        payload = call["payload"]
        assert list(payload) == ["username", "password", "role", "department"]
        assert payload["username"] == "r52-" + str(index).zfill(3)
        assert payload["role"] == "staff"
        assert payload["department"] == bulk.DEFAULT_DEPARTMENTS[(index - 1) % 4]
        assert len(payload["password"]) == 18
        assert set(payload["password"]) <= set(bulk.PASSWORD_ALPHABET)
        assert call["token"] == "ADMIN"


def test_default_credentials_file_keeps_the_old_shape(tmp_path, install):
    """凭证的键序与内容也不许漂：重跑不重置口令这条 R52 约定同样在这里。"""
    install()
    assert bulk.main(_apply(tmp_path, ["--count", "2"])) == 0
    saved = _saved(tmp_path)
    assert list(saved) == ["r52-001", "r52-002"]
    for account in saved.values():
        assert list(account) == ["password", "department", "role"]
        assert account["role"] == "staff"
        assert account["department"] in bulk.DEFAULT_DEPARTMENTS


def test_the_dry_run_head_tail_and_plan_values_are_untouched(tmp_path, install, capsys):
    """干跑只许长新行，不许改旧行：首行、承诺清单、旧五枚键的值一律照旧。"""
    install()
    assert bulk.main(_dry(tmp_path, ["--count", "3"])) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "DRY RUN -- nothing was created, no socket was opened."
    assert out.rstrip().endswith("re-run with --apply against an acceptance stack (not a production one).")
    for check in bulk.CHECKS:
        assert "  - " + check in out, "承诺清单改了词: " + check

    plan = _plan(out)
    assert plan["base_url"] == "http://127.0.0.1:8001"
    assert plan["count"] == 3 and plan["prefix"] == "r52"
    assert plan["departments"] == bulk.DEFAULT_DEPARTMENTS
    assert plan["endpoints"] == ["POST /api/v1/users", "POST /api/v1/login",
                                 "GET /api/v1/profile", "GET /api/v1/data-files"]
    assert plan["roles"] == ["staff"], "缺省角色集是历史那一枚，不是脚本里新抄的一份"


# ---------------------------------------------------------- 判据②：轮换规则（牙检①）


def test_roles_and_departments_are_not_welded_together():
    """牙：把角色与部门写成同一个下标（manager 永远配技术部那种）⇒ 这一枚当场红。"""
    departments = bulk.DEFAULT_DEPARTMENTS
    sample = bulk.build_sample(12, "r417", departments, THREE_TIERS)
    assert {(a["role"], a["department"]) for a in sample} == {
        (role, department) for role in THREE_TIERS for department in departments}

    for role in THREE_TIERS:
        seen = {a["department"] for a in sample if a["role"] == role}
        assert len(seen) == len(departments), role + " 被绑死在一枚部门上"


def test_a_role_list_that_divides_the_department_list_still_rotates():
    """同一枚尺子的死角：3 角色 × 4 部门互质，连"两枚下标写成同一个取模"都能凑满 12 对。
    2 角色 × 4 部门才量得出来——真按同一个下标取模，manager 只会落在销售/技术两枚部门上。
    """
    departments = bulk.DEFAULT_DEPARTMENTS
    two_tiers = ["staff", "manager"]
    sample = bulk.build_sample(8, "r417", departments, two_tiers)
    assert {(a["role"], a["department"]) for a in sample} == {
        (role, department) for role in two_tiers for department in departments}


def test_the_department_advances_only_after_a_full_round_of_roles():
    """把写进计划里的那条规则本身钉住：一枚部门要被整轮角色走完之后才换。

    上面两枚钉量的是"配对覆盖"，3 角色 × 4 部门互质，同一个下标取模也能凑满 12 对；这一枚量的是
    规则的形狀，绑死写法（两枚下标同步）在这里当场红，不管长度互不互质。
    """
    departments = bulk.DEFAULT_DEPARTMENTS
    sample = bulk.build_sample(12, "r417", departments, THREE_TIERS)
    for block in range(len(departments)):
        chunk = sample[block * len(THREE_TIERS):(block + 1) * len(THREE_TIERS)]
        assert [a["role"] for a in chunk] == THREE_TIERS
        assert len({a["department"] for a in chunk}) == 1, (
            "第 " + str(block + 1) + " 轮里部门就换了，角色与部门的下标被绑在一起了")


def test_the_sample_is_deterministic_for_the_same_arguments():
    """同一组 --count/--prefix/--roles 必然得到同一张样本表（没有随机、没有时钟、没有环境）。"""
    first = bulk.build_sample(30, "r417", bulk.DEFAULT_DEPARTMENTS, THREE_TIERS)
    second = bulk.build_sample(30, "r417", bulk.DEFAULT_DEPARTMENTS, THREE_TIERS)
    assert first == second
    assert [a["username"] for a in first] == ["r417-" + str(i).zfill(3) for i in range(1, 31)]


def test_every_requested_tier_shows_up_and_the_counts_stay_even():
    sample = bulk.build_sample(50, "r417", bulk.DEFAULT_DEPARTMENTS, THREE_TIERS)
    counts = bulk.tally(sample, "role")
    assert set(counts) == set(THREE_TIERS), "V2 要的是跨档样本，缺任何一档都量不到越权矩阵"
    assert max(counts.values()) - min(counts.values()) <= 1
    assert sum(bulk.tally(sample, "department").values()) == 50


def test_the_tool_asks_the_roster_instead_of_having_one_of_its_own():
    """写域纪律 + 病根本身：建号载荷不再写死 staff，可创建名单也不许在脚本里长第二份。"""
    source = (ROOT / "scripts" / "provision_bulk_accounts.py").read_text(encoding="utf-8")
    assert "from app.common.permissions import CREATABLE_ROLES" in source
    assert '"role": "staff"' not in source, "建号那一格又变回常数了"
    assert 'DEFAULT_ROLES = ["staff"]' in source, "缺省值要留在点名的地方，且只有这一枚"


# ------------------------------------------- 判据③：auditor 那一档必须诚实失败（牙检②）


def test_auditor_is_refused_without_a_single_request(tmp_path, install, capsys):
    stub = install()
    code = bulk.main(_dry(tmp_path, ["--count", "30", "--roles", "staff", "manager", "admin", "auditor"]))
    out = capsys.readouterr().out

    assert code == bulk.PLAN_ERROR_EXIT == 3, "退出码要可判定，且与建号失败(1)、argparse 用法错(2)分家"
    assert stub.calls == [], "拒样本之前一次请求都不许发出去"
    assert not Path(_credentials(tmp_path)).exists(), "被拒的样本不许留下凭证文件"
    assert "REFUSED" in out and "auditor" in out
    assert "CREATABLE_ROLES" in out, "原因必须点名它撞的是哪一枚真源"
    assert "H13" in out, "原因必须写明密级口径是业主未裁的 H13，不是本单偷懒"
    assert "no socket was opened" in out


def test_auditor_refusal_holds_under_apply(tmp_path, install):
    """牙：干跑就该拒，不许打到第 37 枚账号才喊。"""
    stub = install()
    assert bulk.main(_apply(tmp_path, ["--count", "50", "--roles", "auditor"])) == bulk.PLAN_ERROR_EXIT
    assert stub.calls == []
    assert not Path(_credentials(tmp_path)).exists()


def test_a_silent_downgrade_to_staff_is_not_a_way_out(tmp_path, install, capsys):
    """不许把建不出的那一档悄悄降级成 staff 继续跑：那是一份"看着四档、其实三档"的假样本。"""
    stub = install()
    assert bulk.main(_apply(tmp_path, ["--count", "6", "--roles"] + THREE_TIERS + ["auditor"])) \
        == bulk.PLAN_ERROR_EXIT
    assert [c["payload"]["role"] for c in stub.calls if c["path"] == "/api/v1/users"] == []
    assert "staff=6" not in capsys.readouterr().out


def test_the_refusal_asks_the_true_roster_not_a_copy(monkeypatch):
    """真源漂了量具就跟着漂：R413（H13 一裁）把 auditor 放进 CREATABLE_ROLES，这里当场放行。"""
    monkeypatch.setattr(bulk, "CREATABLE_ROLES", frozenset(CREATABLE_ROLES | {"auditor"}))
    assert bulk.plan_errors(["auditor"], bulk.DEFAULT_DEPARTMENTS) == []

    monkeypatch.setattr(bulk, "CREATABLE_ROLES", frozenset({"staff"}))
    assert bulk.plan_errors(["staff"], bulk.DEFAULT_DEPARTMENTS) == []
    errors = bulk.plan_errors(["manager"], bulk.DEFAULT_DEPARTMENTS)
    assert len(errors) == 1 and "manager" in errors[0]


def test_an_unknown_role_is_refused_and_names_what_is_creatable(tmp_path, install, capsys):
    stub = install()
    assert bulk.main(_dry(tmp_path, ["--roles", "developer"])) == bulk.PLAN_ERROR_EXIT
    out = capsys.readouterr().out
    assert stub.calls == [] and "developer" in out
    for role in sorted(CREATABLE_ROLES):
        assert role in out, "拒绝的话要顺手把建得出的名单报出来"


@pytest.mark.parametrize("extra", [["--roles"], ["--departments"], ["--roles", "--departments"]])
def test_an_empty_rotation_list_is_a_refusal_not_a_traceback(extra, tmp_path, install, capsys):
    """旧现场：--departments 不给值会在建号循环里 ZeroDivisionError；现在是可判定的退出码。"""
    stub = install()
    assert bulk.main(_dry(tmp_path, ["--count", "6"] + extra)) == bulk.PLAN_ERROR_EXIT
    assert stub.calls == []
    assert "Traceback" not in capsys.readouterr().out


# ------------------------------------------------ 判据④：干跑一个 socket 都不开（牙检③）


def test_dry_run_opens_no_socket_and_sends_nothing(tmp_path, install, capsys):
    """autouse 那把雷盯着 urlopen：干跑一旦真去开 socket，当场炸红。"""
    stub = install()
    assert bulk.main(_dry(tmp_path, ["--count", "50", "--roles"] + THREE_TIERS)) == 0
    assert stub.calls == [], "干跑不许发请求"
    assert not Path(_credentials(tmp_path)).exists(), "干跑不许留凭证"
    assert "DRY RUN" in capsys.readouterr().out


# -------------------------------------- 判据⑤⑥：凭证与计划要能当验收材料（牙检④）


def test_credentials_file_records_the_real_role(tmp_path, install):
    """牙：把凭证里角色那一格去掉 ⇒ 这一枚必红；跑完之后没人知道哪枚是 manager 就是没量。"""
    install()
    assert bulk.main(_apply(tmp_path, ["--count", "12", "--roles"] + THREE_TIERS)) == 0
    saved = _saved(tmp_path)
    expected = bulk.build_sample(12, "r52", bulk.DEFAULT_DEPARTMENTS, THREE_TIERS)
    assert list(saved) == [a["username"] for a in expected]
    for a in expected:
        row = saved[a["username"]]
        assert row["role"] == a["role"], a["username"] + " 的档案里没记真角色"
        assert row["department"] == a["department"]
        assert row["password"]
    assert set(bulk.tally(expected, "role")) == set(THREE_TIERS)


def test_a_rerun_keeps_passwords_and_follows_the_new_roles(tmp_path, install):
    install()
    assert bulk.main(_apply(tmp_path, ["--count", "3"])) == 0
    before = _saved(tmp_path)

    install()
    assert bulk.main(_apply(tmp_path, ["--count", "3", "--roles", "manager"])) == 0
    after = _saved(tmp_path)
    for name in ("r52-001", "r52-002", "r52-003"):
        assert after[name]["password"] == before[name]["password"], "重跑不重置口令（R52 的约定）"
        assert after[name]["role"] == "manager", "样本换了形状，档案就得跟着说实话"


def test_apply_flags_an_account_whose_role_came_back_wrong(tmp_path, install, capsys):
    """服务器把 manager 悄悄降成 staff ⇒ 必须报出来；CHECKS 第二条早就写着要回显 role。"""
    install(role_lie=True)
    assert bulk.main(_apply(tmp_path, ["--count", "3", "--roles"] + THREE_TIERS)) == 1
    out = capsys.readouterr().out
    assert "profile says role='staff', expected manager" in out
    assert "profile says role='staff', expected admin" in out
    assert "expected staff" not in out, "本来就建对的那一枚不许被报成失败"


def test_the_profile_readback_survives_both_answer_shapes(tmp_path, install):
    """真路由答 {"profile": {...}}（app/api/v1/auth.py:254）；旧写法在上一层找 department，
    于是每一枚账号都被报成部门不符。两枚形状今天都必须干净通过：只认一层就是假红或假绿。"""
    for shape in ("nested", "flat"):
        stub = install(profile_shape=shape)
        assert bulk.main(_apply(tmp_path, ["--count", "4", "--roles"] + THREE_TIERS,
                                name="r417_" + shape + ".json")) == 0, shape
        assert len([c for c in stub.calls if c["path"] == "/api/v1/users"]) == 4


def test_the_plan_cannot_lie_about_the_sample_it_sends(tmp_path, install, capsys):
    """干跑那张表与 --apply 真发出去的表必须同源（同一枚 build_sample），不许两份答案。"""
    args = ["--count", "14", "--roles"] + THREE_TIERS
    install()
    assert bulk.main(_dry(tmp_path, args)) == 0
    planned = _plan(capsys.readouterr().out)["sample_shape"]

    stub = install()
    assert bulk.main(_apply(tmp_path, args)) == 0
    sent = [c["payload"] for c in stub.calls if c["path"] == "/api/v1/users"]
    assert bulk.tally(sent, "role") == planned["roles"]
    assert bulk.tally(sent, "department") == planned["departments"]
    assert len({(p["role"], p["department"]) for p in sent}) == planned["pairings"]


def test_plan_output_shows_the_sample_shape_before_anything_is_sent(tmp_path, install, capsys):
    install()
    assert bulk.main(_dry(tmp_path, ["--count", "50", "--roles"] + THREE_TIERS)) == 0
    out = capsys.readouterr().out
    shape = _plan(out)["sample_shape"]

    assert sum(shape["roles"].values()) == 50 and sum(shape["departments"].values()) == 50
    assert sorted(shape["roles"]) == sorted(THREE_TIERS)
    assert shape["pairings"] == shape["possible_pairings"] == 12
    assert shape["rotation"] == bulk.ROTATION_RULE

    human = out.split("sample shape", 1)[1]
    for field in ("roles", "departments"):
        for name, count in shape[field].items():
            assert name + "=" + str(count) in human, field + " 的计数只活在 JSON 里，人读不到"
    assert str(shape["pairings"]) + " of " + str(shape["possible_pairings"]) in human


def test_a_sample_too_small_to_cover_every_pairing_says_so(tmp_path, install, capsys):
    install()
    assert bulk.main(_dry(tmp_path, ["--count", "5", "--roles"] + THREE_TIERS)) == 0
    assert "raise --count to 12" in capsys.readouterr().out


def test_the_anonymous_boundary_sentinel_still_bites(tmp_path, install, capsys):
    """那枚前置巡检不许为了让测试好写就弱化：匿名 /data-files 开了门就是失败。"""
    install(anonymous=200)
    assert bulk.main(_apply(tmp_path, ["--count", "2"])) == 1
    assert "anonymous /api/v1/data-files answered 200" in capsys.readouterr().out


def test_admin_login_reads_the_token_the_route_answers_with(tmp_path, install):
    """登录在 app/api/v1/auth.py:83-89 答的是 token；access_token 只当旧别名留着，不当首选。"""
    for key, name in (("token", "r417_token.json"), ("access_token", "r417_legacy.json")):
        stub = install(login_key=key)
        assert bulk.main(["--apply", "--base-url", "http://stack.test", "--username", "boss",
                          "--password", "pw", "--count", "1",
                          "--credentials-file", _credentials(tmp_path, name)]) == 0, key
        assert stub.calls[0]["path"] == "/api/v1/login", "不带 --token 时先用口令换 token"
        assert stub.calls[1]["path"] == "/api/v1/data-files", "匿名巡检仍然在逐号之前"


def test_a_login_that_answers_no_token_is_reported_not_swallowed(tmp_path, install, capsys):
    stub = install(login_key=None)
    assert bulk.main(["--apply", "--base-url", "http://stack.test", "--username", "boss",
                      "--password", "pw", "--count", "1",
                      "--credentials-file", _credentials(tmp_path, "r417_none.json")]) == 1
    assert "administrator login did not yield a token" in capsys.readouterr().out
    assert [c for c in stub.calls if c["path"] == "/api/v1/users"] == []
