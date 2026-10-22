# -*- coding: utf-8 -*-
"""R695 反证牙：把「送身份」那一行摘掉 ⇒ 判据② 的钉必须红，并点名是 rewrite 段没主。

判据① 原文带着这条刀：「把传参那一行摘掉 ⇒ 判据 2 的钉必须红并点名是哪一段没主」。刀全落在
**接线与发点**上，读数用的尺仍是 ``tests/test_r695_rewrite_stage_accounts.py`` 那一套（真路由、
真改写腿、脚本化模型、事件件改道），另起一套牙只证明那套夹具会红。

四枚刀 + 两枚正控：
  K1 运行期把 ``app/trace/spans.py::arm_turn_identity`` 换成对任何轮次都拒挂的包装（＝摘掉挂载
      那一行的效果）⇒ 真 ``/ask`` 路由一枚 rewrite 件都不落，红句点名 rewrite 段没主。
  K2 影子树里删掉 ``chat.ask`` 的 ``arm_turn_identity(`` 那一枚挂载 ⇒ 接线尺当场读不到。
  K3 影子树里删掉 ``search_for_principal`` 交下去的 ``config=retrieval_turn_config(principal)``
      那一行 ⇒ 检索腿的接线尺读成假。
  K4 影子树里把 ``RetrievalPipeline.search`` 的 ``stage_account`` 包住改成直发 ⇒ rewrite 的
      发点少一枚，且 retrieve 段仍然一枚都不许有（不许拿别的段冒充）。
  K5 影子树里把 chat 腿的字面段名换成转发（``stage=某常量``）⇒ 派生表读不到它，发点表只剩一枚。
  正控 A：不动刀时两枚接线尺都为真、派生表两枚发点都在。
  正控 B：每一枚刀的原文都必须现读得到（删不存在的行＝永真的刀）。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.trace import spans

from test_r688_stage_accounts_are_landed import _config, _redirected_journal, stage_emit_points
from test_r126_rewrite_prev_turn import FIRST_TURN, SECOND_TURN, install_ask_route

from test_r695_rewrite_stage_accounts import (
    CHAT_FILE,
    PIPELINE_FILE,
    REWRITE,
    assert_rewrite_account_landed,
    chat_route_arms_the_leg,
    rewrite_emit_sites,
    pipeline_call_site_hands_identity_down,
    rewrite_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 每一枚刀的原文（现读得到才允许下刀；正控 B 逐枚点名）。
CHAT_ARM_LINE = (
    "    turn_identity_token = arm_turn_identity({\n"
    '        "configurable": {\n'
    '            "principal": request_principal,\n'
    '            "thread_id": thread_id,\n'
    '            "request_id": request_id,\n'
    '            "trace_id": trace_id,\n'
    '            "task_id": task_id,\n'
    "        }\n"
    "    })\n"
    "    try:\n"
    "        rewritten_msg = _rewrite_followup(thread_id, orchestration_msg)\n"
    "    finally:\n"
    "        reset_turn_identity(turn_identity_token)\n")
CHAT_LEG_CALL = "    rewritten_msg = _rewrite_followup(thread_id, orchestration_msg)\n"
PIPELINE_PASS_LINE = "            config=retrieval_turn_config(principal),\n"
PIPELINE_ACCOUNT_BLOCK = (
    "            with stage_account(config, stage=\"rewrite\", tier=\"rewrite\"):\n"
    "                rewritten = self.rewriter.rewrite(query)\n")
PIPELINE_BLUNT_BLOCK = "            rewritten = self.rewriter.rewrite(query)\n"
CHAT_LITERAL_ACCOUNT = "    with stage_account(identity, stage=\"rewrite\", tier=\"rewrite\"):\n"
CHAT_FORWARDED_ACCOUNT = "    with stage_account(identity, stage=TURN_STAGE_LITERAL, tier=\"rewrite\"):\n"


def shadow_tree(tmp_path: Path, relative: str, mutate) -> Path:
    """把一枚源文件搬进影子根并就地开刀；根目录形状与仓库一致，尺才用得动。"""
    source = REPO_ROOT / relative
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_bytes().decode("utf-8").replace("\r\n", "\n")
    mutated = mutate(text)
    assert mutated != text, "刀没落下（%s）：那枚原文今天就不在位，读数作废" % relative
    compile(mutated, relative, "exec")
    target.write_bytes(mutated.replace("\n", "\r\n").encode("utf-8"))
    return tmp_path


def cut_line(text: str, line: str) -> str:
    assert text.count(line) == 1, "原文不唯一（出现 %d 次），本刀拒绝猜" % text.count(line)
    return text.replace(line, "")


def replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, "原文不唯一（出现 %d 次），本刀拒绝猜" % text.count(old)
    return text.replace(old, new)



# ==================== 正控：不动刀时两枚接线与两枚发点都在位 ====================


def test_positive_control_the_wiring_and_the_emit_table_are_both_real():
    assert chat_route_arms_the_leg(), "正控失败：ask 路由今天就没挂身份，后面四枚刀都在判空气"
    assert pipeline_call_site_hands_identity_down(), "正控失败：检索腿今天就没被交身份"
    sites = rewrite_emit_sites()
    assert len(sites) >= 2, sites


# ==================== K1：运行期摘掉挂载 ====================


def _refuse_every_round(config):
    """与「摘掉挂载那一行」等效：身份never进得来，腿只能退回无主。"""
    return None


def test_knife_k1_blunting_the_arm_leaves_the_rewrite_segment_ownerless(tmp_path, monkeypatch):
    ask_once, prompts, _graph = install_ask_route(monkeypatch, tmp_path)
    monkeypatch.setattr(spans, "arm_turn_identity", _refuse_every_round)
    session_id = "r695-k1-" + uuid4().hex

    with _redirected_journal(tmp_path, monkeypatch) as journal:
        ask_once(FIRST_TURN, session_id)
        ask_once(SECOND_TURN, session_id)
        assert rewrite_rows(journal) == [], rewrite_rows(journal)
        with pytest.raises(AssertionError) as caught:
            assert_rewrite_account_landed(journal)
    message = str(caught.value)
    assert REWRITE in message and "没主" in message, message
    assert len(prompts) == 1, "改写腿本身照跑：摘掉身份只该少账，不该少动作"


# ==================== K2／K3：影子树里摘接线 ====================


def test_knife_k2_removing_the_arm_line_breaks_the_chat_wiring(tmp_path):
    def unarm(text):
        text = replace_once(text, CHAT_ARM_LINE, CHAT_LEG_CALL)
        return cut_line(text, "    from app.trace.spans import arm_turn_identity, reset_turn_identity\n")
    root = shadow_tree(tmp_path, CHAT_FILE, unarm)
    assert chat_route_arms_the_leg(), "正控：不动刀时 chat 腿的接线必须为真"
    assert not chat_route_arms_the_leg(root), (
        "摘掉 arm_turn_identity 那一枚挂载，接线尺仍读真 ⇒ 这枚刀是永真的")


def test_knife_k3_removing_the_config_argument_breaks_the_pipeline_wiring(tmp_path):
    root = shadow_tree(tmp_path, PIPELINE_FILE, lambda text: cut_line(text, PIPELINE_PASS_LINE))
    assert pipeline_call_site_hands_identity_down(), "正控：不动刀时检索腿的接线必须为真"
    assert not pipeline_call_site_hands_identity_down(root), (
        "摘掉 config=retrieval_turn_config(principal) 那一行，接线尺仍读真 ⇒ 这枚刀是永真的")


# ==================== K4／K5：影子树里摘发点 ====================


def test_knife_k4_unmetering_the_pipeline_leg_loses_one_rewrite_emit_point(tmp_path):
    root = shadow_tree(tmp_path, PIPELINE_FILE,
                       lambda text: replace_once(text, PIPELINE_ACCOUNT_BLOCK, PIPELINE_BLUNT_BLOCK))
    with pytest.raises(AssertionError) as caught:
        rewrite_emit_sites(root / "app")
    assert REWRITE in str(caught.value), str(caught.value)


def test_knife_k5_a_forwarded_stage_name_is_not_an_emit_point(tmp_path):
    """发点要能被指认，就得写下一枚字面段名：换成转发常量 ⇒ 派生表当场读不到这一枚。"""
    root = shadow_tree(tmp_path, CHAT_FILE,
                       lambda text: replace_once(text, CHAT_LITERAL_ACCOUNT, CHAT_FORWARDED_ACCOUNT))
    with pytest.raises(AssertionError) as caught:
        rewrite_emit_sites(root / "app")
    assert REWRITE in str(caught.value), str(caught.value)


def test_the_ruler_can_see_a_second_meter_on_the_same_segment(tmp_path):
    """双记的形状必须指认得出来：影子树里给同一段种第二枚尺 ⇒ 表里两枚发点逐枚点名。

    正控的下半句是本单实际交出去的形状：每一枚腿各一把尺，一枚都不许多。retrieve 那一族差点
    双记的教训（等长区间进 ``unresolved_pairs``，``within_one_percent`` 从此永闭）读的正是这张表。
    """
    shadow = tmp_path / "app"
    (shadow / "rag").mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / PIPELINE_FILE, shadow / "rag" / "retrieval_pipeline.py")
    (shadow / "rag" / "duplicate_leg.py").write_text(
        "def second_meter(config):\n"
        "    from app.trace.spans import stage_account\n"
        "    with stage_account(config, stage=\"rewrite\", tier=\"rewrite\"):\n"
        "        return 1\n",
        encoding="utf-8")
    planted = stage_emit_points(shadow).get(REWRITE) or []
    assert "app/rag/duplicate_leg.py::second_meter" in planted, planted
    assert PIPELINE_FILE + "::RetrievalPipeline.search" in planted, planted

    sites = rewrite_emit_sites()
    per_leg = {}
    for site in sites:
        per_leg[site.partition("::")[0]] = per_leg.get(site.partition("::")[0], 0) + 1
    assert per_leg == {CHAT_FILE: 1, PIPELINE_FILE: 1}, per_leg
