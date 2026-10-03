# -*- coding: utf-8 -*-
"""R577 判据⑤ —— 反证刀：五把，每一把先在影子端（未变异的副本）跑正控确认它会咬。

## 口径

🔴 全程只在 ``tmp_path`` 的副本上动手：把 ``scripts/r577_demo_sample_seed.py`` 读进内存、
按锚点改一处、写成副本、按副本单独加载一枚模块，再在**同一枚加载路径**上把主件那枚在册钉
（``tests/test_r577_demo_sample_seed.py``）指到副本上跑一遍。跟踪里的原件每把刀前后各核一次
sha256（最后一枚用例总清点）。锚点不唯一当场红——那把刀等于没动东西。

## 为什么必须有这四把

本单的性质是「喂真数据」，它唯一的价值全押在这台喂数据的机器会不会撒谎上：形状少了档位没人报、
无归属的告警行被拿来冒充闭环、第二跑把规则与告警越喂越多——这三种「量了但量的是假的」都长得
跟达标一模一样。主件那 20 枚钉只证「装着牙的时候它咬」，这四把刀证的是「牙掉了它就不咬」，
少一把就有一格退化成假绿。
"""
from __future__ import annotations

import hashlib
import socket

import pytest

import test_r577_demo_sample_seed as pins
from test_r577_demo_sample_seed import SEED_BASELINE_SHA, SEED_PATH, load_seed_copy

#: 刀下那枚钉子的两种红法：自己那句 assert（AssertionError），或 pytest 自己报的「DID NOT RAISE」
#: （``pytest.fail.Exception``）。两者都算「这枚钉跟着哑了」，只认前者会把刀漏成假绿。
PIN_FAILURE = (AssertionError, pytest.fail.Exception)

#: 五把刀的锚点全部现取唯一。victim 一栏写的是「摘掉它，主件里哪一枚钉会跟着变哑」。
KNIVES = {
    "K1_tier_check_blinded": {
        "anchor": '    missing = sorted(set(roles) - set(shape.get("roles") or {}))\n    if missing:',
        "replace": '    missing = sorted(set(roles) - set(shape.get("roles") or {}))\n    if False:',
        "victim": "判据①②（少一档角色必须具名拒绝）—— 主件 test_a_short_sample_names_the_missing_tier",
    },
    "K2_attribution_filter_dropped": {
        "anchor": '    return [row for row in rows if department in str(row.get("department") or "")]',
        "replace": "    return list(rows)",
        "victim": "判据④（无归属行不许冒充闭环）—— 主件 test_unattributed_alert_rows_are_refused",
    },
    "K3_rule_dedup_dropped": {
        "anchor": '    return [rule for rule in planned if str(rule.get("name") or "") not in have]',
        "replace": "    return list(planned)",
        "victim": "判据⑤（第二跑规则枚数不涨）—— 主件 test_the_second_run_creates_no_rules",
    },
    "K4_reassign_guard_gone": {
        "anchor": '        if action == "assign" and str(row.get("assignee") or "").strip():',
        "replace": '        if action == "assign" and False:',
        "victim": "判据⑤（重放不重派、已关闭不再动）—— 主件 test_a_replayed_row_owes_no_more_steps",
    },
    "K5_roster_demand_replaced_by_the_request": {
        "anchor": "    required = args.roles if args.allow_partial_roster else sample_roles()",
        "replace": "    required = args.roles",
        "victim": "判据①（CLI 上少一档必须整单拒）—— 主件 test_three_tiers_on_the_command_line_are_refused_not_forgiven",
    },
}

#: 每把刀对应的主件在册钉，按名字点，不复制第二份断言。
PINS = {
    "K1_tier_check_blinded": "test_a_short_sample_names_the_missing_tier",
    "K2_attribution_filter_dropped": "test_unattributed_alert_rows_are_refused",
    "K3_rule_dedup_dropped": "test_the_second_run_creates_no_rules",
    "K4_reassign_guard_gone": "test_a_replayed_row_owes_no_more_steps",
    "K5_roster_demand_replaced_by_the_request": "test_three_tiers_on_the_command_line_are_refused_not_forgiven",
}


def knife(name: str) -> tuple[str, str]:
    spec = KNIVES[name]
    return spec["anchor"], spec["replace"]


def run_pin(name: str):
    """按名字跑主件那一枚在册钉（此刻 ``pins.seed`` 指向谁就跑在谁身上）。"""
    getattr(pins, PINS[name])()


def replay_one_knife(tmp_path, name):
    """同一枚加载路径上跑两遍：影子端原件会咬（正控），刀下必须变哑。"""
    anchor, replacement = knife(name)
    original_source = SEED_PATH.read_text(encoding="utf-8")
    assert original_source.count(anchor) == 1, (
        "锚点在原件里不唯一（" + str(original_source.count(anchor)) + " 处）：这把刀等于没动东西")

    pristine = load_seed_copy(tmp_path, name + "-control")
    with pytest.MonkeyPatch.context() as tape:
        tape.setattr(pins, "seed", pristine)
        run_pin(name)                       # 正控：装在原件上的这枚牙会咬

    mutant = load_seed_copy(tmp_path, name, anchor=anchor, replacement=replacement)
    with pytest.MonkeyPatch.context() as tape:
        tape.setattr(pins, "seed", mutant)
        # 摘牙之后钉子里那句 assert 会红；pytest 自己那句 "DID NOT RAISE" 是 Failed。
        with pytest.raises(PIN_FAILURE):  # 刀下：牙掉了，钉必须跟着红
            run_pin(name)
    return mutant


def test_the_five_knives_each_have_a_unique_anchor():
    """反空转的第一格：四把锚点都得在原件里唯一，否则「摘了牙」这句话是空的。"""
    source = SEED_PATH.read_text(encoding="utf-8")

    assert set(KNIVES) == set(PINS)
    for name, spec in KNIVES.items():
        assert source.count(spec["anchor"]) == 1, name
        assert spec["anchor"] != spec["replace"], name


def test_k1_blinding_the_tier_check_silences_the_shape_pin(tmp_path):
    """三档样本在刀下悄悄放行：四档权限矩阵少了那一行，却读起来像量过了。"""
    replay_one_knife(tmp_path, "K1_tier_check_blinded")


def test_k2_dropping_the_attribution_filter_admits_unowned_rows(tmp_path):
    """``alerts.department`` 为空的行被收下：0012 那格归属从「必须非空」退回「有没有都无所谓」。"""
    replay_one_knife(tmp_path, "K2_attribution_filter_dropped")


def test_k3_dropping_the_rule_dedup_lets_the_ledger_grow(tmp_path):
    """第二跑把同名规则再建一遍：规则枚数随每次重跑上涨，判据⑤当场失效。"""
    replay_one_knife(tmp_path, "K3_rule_dedup_dropped")


def test_k4_dropping_the_reassign_guard_replays_a_handoff(tmp_path):
    """已派过人的行再派一次：台账上「谁接手」被最后一次点击改写，重放不再是幂等。"""
    replay_one_knife(tmp_path, "K4_reassign_guard_gone")


def test_the_tracked_seed_survives_every_knife_unchanged():
    """五把刀走完，原件 sha256 与基线逐字节一致：摘过的东西都摘回去了。"""
    assert hashlib.sha256(SEED_PATH.read_bytes()).hexdigest() == SEED_BASELINE_SHA




@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """五把刀全程离线：副本里那些纯判定函数一枚都不该走到 socket。"""
    monkeypatch.setattr(socket, "socket", pins.LandmineSocket)


def main_rc(module, argv):
    """在（可能是变异的）那一枚种子上跑一遍 CLI，只取退出码。"""
    with pytest.MonkeyPatch.context() as tape:
        tape.setattr(module, "bulk_tool", pins.StubBulk)
        return module.main(argv)


def test_k5_forcing_the_demand_to_follow_the_request_forgives_a_missing_tier(tmp_path, capsys):
    """正控：原件在 CLI 上把三档样本按 ``PLAN_ERROR_EXIT`` 拒了。刀下：同样的命令一路放行。

    这一把摘的不是 ``verify_sample_shape`` 那句判据（那是 K1），是「拿真源四档比」这接线本身：
    ``required`` 一旦退回 ``args.roles``，形状断言就变成「样本跟请求自比」，永远自洽、永远不咬。
    """
    anchor, replacement = knife("K5_roster_demand_replaced_by_the_request")
    argv = ["--roles", "staff", "manager", "admin"]

    pristine = load_seed_copy(tmp_path, "k5-control")
    assert main_rc(pristine, argv) == pins.StubBulk.PLAN_ERROR_EXIT
    assert "auditor" in capsys.readouterr().out

    mutant = load_seed_copy(tmp_path, "k5", anchor=anchor, replacement=replacement)
    capsys.readouterr()
    assert main_rc(mutant, argv) == 0, "刀下这枚钉哑了：三档样本被当成四档放行"
    assert "auditor" not in capsys.readouterr().out
