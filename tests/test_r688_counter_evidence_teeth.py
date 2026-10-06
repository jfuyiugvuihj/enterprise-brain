# -*- coding: utf-8 -*-
"""R688 反证牙：摘掉任意一段的生产发点，判据① 的那枚钉必须**点名那一段**红。

判据② 原文：「把其中一段的发点摘掉 ⇒ 判据 1 的钉当场红并点名那一段；这条是防『只补了三段
也算过』」。所以刀全落在**发点**上，钉与轮次用的仍是
``tests/test_r688_stage_accounts_are_landed.py`` 那一套（真图、真节点、真 trace 件、脚本化
模型），一字节都不另起 —— 另起一套的牙只证明那套夹具会红。

四把刀 + 两枚静态反控：
  K1/K2/K3 逐枚摘掉 classify / generate / reflect 的发点（把 ``app/agents/nodes.py::_stage_account``
      换成一枚对受害段空转的包装）⇒ 必须红，且红句只点名受害段。
  K4 把 ``app/common/stage_timing.py::CANONICAL_STAGES`` 里的 reflect 摘掉 ⇒ 写入口必须当场
      拒发（闸读的是那张表，不是发点旁抄的第二套名单）⇒ 同一个受害段红。
  静态反控 A：派生发点表在影子树里必须真能检出「自造段名」的种点（读空 = 尺坏了）。
  静态反控 B：「没落地的两段必须零枚」那一格是真牙，不是永真句。
"""
from __future__ import annotations

import contextlib

import pytest
from langchain_core.messages import AIMessage

from app.agents import nodes
from app.common import stage_timing as stage_timing_module

from test_r688_stage_accounts_are_landed import (
    LANDED_STAGES,
    QA_QUESTION,
    STAGE_EVENT,
    assert_stage_accounts,
    run_production_round,
    stage_emit_points,
)

REPLY = AIMessage(content="上周销售环比上周持平，明细见知识库。")


def _blunted_account(victim: str):
    """一枚对受害段空转的记账包装：发点还在原地，但那一段不再落件。

    这是「摘掉发点」的最小实现：只掐受害段的名字，其余段照旧，所以红句必须只点名受害段 ——
    如果它把别的段也判红，说明钉在数「有没有跑过」而不是「有没有落件」。
    """
    original = nodes._stage_account

    def _account(config, *, stage, tier="", summary=None):
        if stage == victim:
            return contextlib.nullcontext()
        return original(config, stage=stage, tier=tier, summary=summary)

    return _account


def _round(tmp_path, monkeypatch, offline_ollama_embeddings):
    return run_production_round(tmp_path, monkeypatch, QA_QUESTION, replies=[REPLY])


# ==================== 正控：没有刀的时候必须绿 ====================


def test_the_positive_control_round_passes_the_criterion(tmp_path, monkeypatch, offline_ollama_embeddings):
    round_ = _round(tmp_path, monkeypatch, offline_ollama_embeddings)
    counts = assert_stage_accounts(round_["events"], trace_id=round_["trace_id"])
    assert all(counts.get(stage, 0) >= 1 for stage in LANDED_STAGES), counts


# ==================== K1/K2/K3：逐枚摘发点 ====================


@pytest.mark.parametrize("victim", LANDED_STAGES)
def test_each_knife_reddens_the_named_victim_stage(
    tmp_path, monkeypatch, offline_ollama_embeddings, victim: str
):
    monkeypatch.setattr(nodes, "_stage_account", _blunted_account(victim))
    round_ = _round(tmp_path, monkeypatch, offline_ollama_embeddings)
    with pytest.raises(AssertionError) as caught:
        assert_stage_accounts(round_["events"], trace_id=round_["trace_id"])
    message = str(caught.value)
    assert "段 %s " % victim in message, (victim, message)
    for other in [stage for stage in LANDED_STAGES if stage != victim]:
        assert "段 %s " % other not in message, (victim, other, message)


# ==================== K4：闸读的是在册表，不是旁抄的名单 ====================


def test_dropping_a_stage_from_the_canonical_table_reopens_the_gate(
    tmp_path, monkeypatch, offline_ollama_embeddings
):
    shrunken = tuple(name for name in stage_timing_module.CANONICAL_STAGES if name != "reflect")
    assert len(shrunken) == len(stage_timing_module.CANONICAL_STAGES) - 1
    monkeypatch.setattr(stage_timing_module, "CANONICAL_STAGES", shrunken)
    round_ = _round(tmp_path, monkeypatch, offline_ollama_embeddings)
    with pytest.raises(AssertionError) as caught:
        assert_stage_accounts(round_["events"], trace_id=round_["trace_id"])
    assert "段 reflect " in str(caught.value), str(caught.value)


# ==================== 静态反控 ====================


def test_the_derived_emit_table_detects_a_planted_invented_name(tmp_path):
    """影子端正控：派生表读的不是「今天恰好只有五段」，而是真能检出种下去的自造段名。"""
    shadow = tmp_path / "app" / "pkg"
    shadow.mkdir(parents=True)
    (shadow / "mod.py").write_text(
        "def adopt(config):\n"
        "    from app.agents.nodes import _stage_account\n"
        "    with _stage_account(config, stage='thinking'):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    planted = stage_emit_points(tmp_path / "app")
    assert planted == {"thinking": ["app/pkg/mod.py::adopt"]}, planted
    # 反控：真实的 app/** 只交回在册字面（尺读空 = 上一句已经红）
    real = stage_emit_points()
    assert real and set(real) <= set(stage_timing_module.CANONICAL_STAGES), real


def test_the_unlanded_boundary_pin_is_a_real_tooth():
    """retrieve 一旦落进件里，「没落地的两段必须零枚」那一格必须红，不许永真。"""
    events = [{
        "event_type": STAGE_EVENT,
        "trace_id": "trace-knife",
        "payload": {"stage": "retrieve", "record_kind": "stage_windows", "duration_ms": 7},
    }]
    with pytest.raises(AssertionError) as caught:
        assert_stage_accounts(events, trace_id="trace-knife")
    assert "retrieve" in str(caught.value), str(caught.value)