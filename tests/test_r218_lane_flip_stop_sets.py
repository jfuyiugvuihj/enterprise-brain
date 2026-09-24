# -*- coding: utf-8 -*-
"""R218 判据 ②-D（三格之一）+ 判据 ④ 反证钉：报告档翻开关与两族轮询停表。

对判据的哪一条：单号 R218 判据 ② 第一格（``REPORT_LANE_VIA_QUEUE`` 从默认 off 翻 on 之后，
入队/轮询/取回链路离线判得动的部分 + ``QUEUE_POLL_STOPPERS`` 那族停轮子收不收得住每个终态）。

形状：正例读「翻开关成立 + 后端答得出的终态里有前端停不住的」；反例把前端名单里的一枚摘掉，
红色必须落在本格的 ``frontend_unhandled_final`` 上，另两格一个字不动（上一班那枚
「摘判据① 没红、其实是被判据④ 顺手拦住」的假钉，本单不再犯）。
🔴 反证只加不减：既有断言一枚不删、不放宽。
"""
import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _rehearsal():
    spec = importlib.util.spec_from_file_location(
        "r218_switch_rehearsal_mod", REPO / "scripts" / "r218_switch_rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _rehearsal()

PIN_FILES = R.rehearsal_inputs()  # 由 _CITATIONS 与三格读取点长出，不手抄


def _tree_sha(relatives=PIN_FILES) -> dict:
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in relatives}


def _overlay(tmp_path: Path) -> Path:
    """把本格读到的那几枚文件复制进临时根：反证只作用在副本上，跟踪里的原件一枚不碰。"""
    root = tmp_path / "overlay"
    for rel in PIN_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    return root


def test_cell_reads_the_flip_and_the_stop_sets():
    cell = R.cell_lane_flip(REPO)
    readings = cell["readings"]
    # 判据 ②-D 的前半：默认关，翻 on 才进队列道（读的是产品谓词本体）
    assert readings["lane_flip"]["default_off"] is True
    assert readings["lane_flip"]["flip_on"] is True
    assert readings["lane_flip"]["flip_off_literal"] is True
    assert readings["lane_flip"]["lane_predicate"] == {
        "report": "report", "REPORT": "", "qa": "", "analysis": "", "": ""}
    # 后半：状态字面与两族停表都从代码里抽出来，不是手抄清单
    assert "dead" in readings["backend_answers"]
    assert readings["final_statuses"] == list(R.FINAL_QUEUE_STATUSES)
    assert set(readings["frontend_http_stoppers"]) == {
        "401:authentication_required", "403:authorization_unavailable",
        "403:permission_denied", "404:resource_not_found"}
    assert readings["citation_drift"] == []


def test_cell_is_red_because_a_final_status_is_never_stopped():
    """本格今天真读出的红：dead 是终态，而前端那族轮子没有截止，只能靠名单停。"""
    cell = R.cell_lane_flip(REPO)
    assert cell["verdict"] == R.RED
    assert cell["readings"]["frontend_unhandled_final"] == ["dead"]
    assert "frontend_never_stops_on=dead" in cell["problems"]
    # 适配器那族有截止 ⇒ 不算"永不停"，但每条未终结的轮询各白等一整段 deadline。
    # 🔴 R218 返工订正：上一班这里把 900 × 105 当成代价交出去（那枚乘法的前提是"105 题全部
    # 撞上未终结态"），本件从今天起只交两枚**各自有名**的量：单条白等时长 / 全体撞上的天花板。
    # 天花板是上界不是期望值，所以另钉一枚 flag 与现读题数，谁都别想再把它读成预计代价。
    assert cell["readings"]["adapter_unhandled_final"] == ["cancelled", "dead"]
    assert cell["readings"]["adapter_waste_per_stalled_watch_seconds"] == 900.0
    assert cell["readings"]["adapter_deadline_seconds"] == 900.0
    assert cell["readings"]["adapter_deadline_env"] == "EVAL_QUEUE_POLL_SECONDS"
    assert cell["readings"]["question_count_read_from_fixture"] == 105
    assert cell["readings"]["adapter_worst_case_minutes_if_every_question_stalls"] == pytest.approx(1575.0)
    assert cell["readings"]["worst_case_is_upper_bound_not_expectation"] is True
    # 前端那一族的代价不是一个秒数：watchQueueTurn 里没有第三枚到点自停
    assert cell["readings"]["frontend_watch_has_no_deadline"] is True
    # 只有两枚停表动作，且按**原文**钉（行号只用来证先后，不用来证内容）：
    # 命中名单停表 + 到点再打一次的 setInterval；没有第三枚"到点自停"。
    actions = cell["readings"]["frontend_stop_actions"]
    assert [x[1] for x in actions] == [
        "if (QUEUE_SETTLED.includes(read.status)) stop()",
        "entry.timer = setInterval(tick, QUEUE_POLL_MS)"]
    assert actions[0][0] < actions[1][0]
    # 上一班那枚假口径必须已经消失：仓里不许同时存在两份互相矛盾的代价说法
    assert "adapter_deadline_cost_105q_minutes" not in cell["readings"]


def test_control_overlay_reproduces_the_real_verdict(tmp_path):
    """对照：原样复制的临时根必须复现同一判定，否则下面的红色是复制造出来的假红。"""
    overlay = _overlay(tmp_path)
    assert R.frontend_stop_vocabulary(overlay) == R.frontend_stop_vocabulary(REPO)
    assert R.stop_set_gap(R.frontend_stop_vocabulary(overlay)["settled"],
                          R.adapter_stop_vocabulary(overlay)["stops"]) == (["dead"],
                                                                           ["cancelled", "dead"])


def test_counter_proof_dropping_one_settled_status_goes_red_here(tmp_path):
    """反证钉（判据 ④）：把前端名单里的一枚终态摘掉 ⇒ 本格必须变红，且红在摘掉的那一枚上。"""
    overlay = _overlay(tmp_path)
    panel = overlay / "frontend/src/components/ChatPanel.vue"
    original = panel.read_text(encoding="utf-8")
    mutated = original.replace("const QUEUE_SETTLED = ['done', 'cancelled', 'failed', 'expired']",
                              "const QUEUE_SETTLED = ['done', 'cancelled', 'failed']")
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    panel.write_text(mutated, encoding="utf-8")

    before = _tree_sha()
    cell = R.cell_lane_flip(overlay)
    assert cell["verdict"] == R.RED
    assert "expired" in cell["readings"]["frontend_unhandled_final"]
    assert any(p.startswith("frontend_never_stops_on=") for p in cell["problems"])

    # 红色只能落在本格：另两格对着同一枚临时根判，必须维持原判
    other = R.cell_cache_hit(overlay)
    assert other["verdict"] == R.GREEN, f"别格顺手拦住了本钉：{other['problems']}"
    assert R.cell_ruler(overlay)["readings"]["unparsed_shapes"] == []

    # 还原核对：临时根删掉，跟踪里的原件 sha256 逐字不变
    shutil.rmtree(tmp_path)
    assert _tree_sha() == before
    assert (REPO / "frontend/src/components/ChatPanel.vue").read_text(
        encoding="utf-8") == original


def test_the_pin_has_teeth_in_the_other_direction_too(tmp_path):
    """反证钉要能钉回绿：补齐 dead 之后本格必须不再因停表变红（不许靠放宽判据变绿）。"""
    overlay = _overlay(tmp_path)
    panel = overlay / "frontend/src/components/ChatPanel.vue"
    original = panel.read_text(encoding="utf-8")
    panel.write_text(original.replace("['done', 'cancelled', 'failed', 'expired']",
                                     "['done', 'cancelled', 'failed', 'expired', 'dead']"),
                     encoding="utf-8")
    cell = R.cell_lane_flip(overlay)
    assert cell["readings"]["frontend_unhandled_final"] == []
    assert "frontend_never_stops_on=dead" not in cell["problems"]
    assert cell["verdict"] == R.GREEN
    shutil.rmtree(tmp_path)
