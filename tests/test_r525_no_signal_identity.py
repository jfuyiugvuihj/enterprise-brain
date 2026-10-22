# -*- coding: utf-8 -*-
"""R525 判据③ —— 无信号时开 / 关两态**逐字相等**，并且交回的是同一个对象（``is`` 比较）。

在册那枚 ``test_r153_prior_shift_is_bounded.py::test_no_signal_still_comes_back_as_the_very_same_list_object``
钉的是 ``rank_hits_by_activity`` 这一层；本件往上钉两格它没覆盖的：

1. **真库那一份无信号**：面 A 的 0011 读成功而零行 ⇒ 先验是空字典 ⇒ 真库名次原样回来。
2. **开关这一跳**：``RAG_ACTIVITY_PRIOR`` 开与关两态，对**同一个对象同一份输入**跑
   ``DocumentRetriever._apply_activity_prior``，快照 JSON 逐字相等、两态都交回同一对象。
   这一跳在册只钉过属性态（直接调函数），环境那一跳今天由本件补上（与 R520 补
   ``EVAL_DECLARE_LANE_TIER`` 环境腿同一族做法）。

🔴 「不许把读不到冒充成没有信号」那一格在 ``tests/test_r525_missing_0011_fail_open.py``，
本件只管：两种零在**排序上**表现相同，在**观测面**上必须能分开。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from test_r525_real_store_readings import ann_rows, product_hit_dicts, signal_on

ACTIVITY_PRIOR_ENV = "RAG_ACTIVITY_PRIOR"
#: 面 A 的真库读数：0011 读成功而零行 ⇒ 产品读取器交回空字典（快照出处见读数纸）。
REAL_STORE_EMPTY_PRIORS = {}


def snapshot(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def apply_prior(hits, *, loader, monkeypatch, env_value=None):
    """走产品自己的 ``_apply_activity_prior``，只把读取方换成一枚返回真库读数的桩。"""
    from app.rag.retriever import DocumentRetriever

    if env_value is None:
        monkeypatch.delenv(ACTIVITY_PRIOR_ENV, raising=False)
    else:
        monkeypatch.setenv(ACTIVITY_PRIOR_ENV, env_value)
    carrier = SimpleNamespace(_activity_prior_loader=loader)
    return DocumentRetriever._apply_activity_prior(carrier, hits)


def real_hits():
    return product_hit_dicts(ann_rows(40))


# ==================== 真库那一份无信号 ====================

def test_the_real_zero_row_store_returns_the_very_same_list_object():
    """判据③ 本体：空先验 + 开关开着 ⇒ ``ranked is hits``，不是「内容相等的另一份拷贝」。"""
    from app.rag import retriever as rt

    hits = real_hits()
    ranked = rt.rank_hits_by_activity(hits, REAL_STORE_EMPTY_PRIORS, enabled=True)
    assert ranked is hits, "无信号必须交回同一个列表对象，否则判据③是假的"
    assert snapshot(ranked) == snapshot(hits)


def test_no_hit_carries_an_activity_prior_annotation_when_the_store_is_empty():
    """NULL 语义：无信号时命中字典上压根不出现 ``activity_prior`` 键（不是补一枚零）。"""
    from app.rag import retriever as rt

    hits = real_hits()
    keys_before = [sorted(hit) for hit in hits]
    ranked = rt.rank_hits_by_activity(hits, REAL_STORE_EMPTY_PRIORS)
    assert [sorted(hit) for hit in ranked] == keys_before, "注记键不许在无信号时被凭空加上"
    assert all("activity_prior" not in hit for hit in ranked)


@pytest.mark.parametrize("env_value", [None, "on", "off", "OFF", "0", "false", "no"])
def test_the_on_and_off_states_snapshot_identical_with_no_signals(monkeypatch, env_value):
    """同一对象同一份输入：开 / 关两态的快照逐字相等（派工词判据③的字面要求）。

    拼错的值按在册口径**不算退回**（``ACTIVITY_PRIOR_OFF_VALUES`` 之外），所以这里连
    ``"on"`` 与几枚显式关法一起测：无信号时它们给出的必须是同一份东西。
    """
    hits = real_hits()
    before = snapshot(hits)
    ranked = apply_prior(hits, loader=lambda: dict(REAL_STORE_EMPTY_PRIORS),
                         monkeypatch=monkeypatch, env_value=env_value)
    assert ranked is hits, (env_value, "开关态下不再交回同一个对象")
    assert snapshot(ranked) == before, (env_value, snapshot(ranked)[:200])


def test_the_switch_is_not_a_no_op_when_there_is_a_signal(monkeypatch):
    """对照：有信号时开与关必须真的不一样，否则上面那枚「逐字相等」是自证。

    信号键取自真库真 filename，值明写是合成（真库 0 行，本单不许伪造真库有信号）。
    """
    rows = ann_rows(40)
    from test_r525_displacement_on_real_ranks import single_carrier_index

    index = single_carrier_index(rows)
    priors = signal_on(rows, index)

    off_hits = product_hit_dicts(rows)
    off = apply_prior(off_hits, loader=lambda: dict(priors), monkeypatch=monkeypatch,
                      env_value="off")
    assert off is off_hits and snapshot(off) == snapshot(product_hit_dicts(rows))

    on_hits = product_hit_dicts(rows)
    on = apply_prior(on_hits, loader=lambda: dict(priors), monkeypatch=monkeypatch,
                     env_value=None)
    assert on is not on_hits, "有信号时应当复制注记"
    assert [hit["source"] for hit in on] != [hit["source"] for hit in off], (
        "开关两态给出同一份次序 ⇒ 这一跳压根没接线")
    assert on[index - 1]["activity_prior"]["places_moved"] == 1


def test_both_kinds_of_zero_come_back_untouched_but_say_different_things(monkeypatch):
    """「读成功而零行」与「读不通」在排序上同形、在观测面上必须异形（判据⑤的牙齿）。"""
    from app.rag import retriever as rt

    monkeypatch.delenv(ACTIVITY_PRIOR_ENV, raising=False)

    def raiser():
        raise RuntimeError("relation document_activity_signals does not exist")

    rt.reset_activity_priors()
    empty = rt.activity_priors(row_reader=lambda: [])
    empty_diagnostics = dict(rt.activity_prior_diagnostics())

    rt.reset_activity_priors()
    broken = rt.activity_priors(row_reader=raiser)
    broken_diagnostics = dict(rt.activity_prior_diagnostics())
    rt.reset_activity_priors()

    assert empty == broken == {}, "两种零在排序上都必须是空先验"
    assert (empty_diagnostics["source"], empty_diagnostics["reason"]) == ("store", "")
    assert broken_diagnostics["source"] == "error"
    assert broken_diagnostics["reason"] == "RuntimeError"
    assert empty_diagnostics != broken_diagnostics


@pytest.mark.parametrize("not_signals", [{}, None])
def test_an_absent_snapshot_is_the_same_no_signal_as_an_empty_one(monkeypatch, not_signals):
    """读取器交回 ``None``（压根没读）与交回 ``{}``（读到零行）都必须原样不动。"""
    hits = real_hits()
    ranked = apply_prior(hits, loader=lambda: not_signals, monkeypatch=monkeypatch)
    assert ranked is hits
    assert snapshot(ranked) == snapshot(hits)


def test_the_default_loader_is_the_product_one_and_not_a_test_double():
    """本件注入的桩只顶替读取方；开关与排序本体一律用产品码，防止钉在自家里空转。"""
    from app.rag.retriever import DocumentRetriever

    instance_keys = DocumentRetriever.__init__.__code__.co_varnames
    assert "activity_prior" in instance_keys, "注入点漂了：本件的桩没有可注的地方"
    assert "RAG_ACTIVITY_PRIOR" in ACTIVITY_PRIOR_ENV
