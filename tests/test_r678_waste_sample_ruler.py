# -*- coding: utf-8 -*-
r"""R678 判据② 的那枚离线牙：喂一份「没声明却指望入队」的桩 ⇒ 尺子非零并点名那一扇。

钉的是 scripts/r573_caliber_reconciliation.py 新加的那一格（--expect-lane-phase on）。
三扇在册废样本（run24s2／run24s2b／run24s2c）的形状就是这里这份桩：12 枚报告题正文全在、
六组数照样算得出来，但账上一枚 queued_* 都没有 ⇒ 它们说的是同步道，跟 D① 那句
「入队 → worker 跑完 → /queue/status 取回正文」一个字都没沾。从前这把尺只会对它们说
「分母对不上」，从今天起能说清为什么，并且归因写死是**量具缺陷**——不是产品没入队，
更不是「D 门量到了零」。

四格判据（全离线：tmp_path 桩件、零模型、零容器、零网络、零连库）：
① 缺省 off 时本件读数与今天逐字节相同（在册钉 test_r573_a2_three_calibres 不受影响）；
② 声称 on 相却零枚 queued_* ⇒ rc=2 当场拒，并点名那一扇（窗名逐字出现在拒判句里）；
③ 账上只要有一枚 queued_*（正控）⇒ 同一扇窗照旧出数，六组数与 off 时一字不差；
④ 反证牙：把 require_lane_leg 那枚腿在内存里摘掉 ⇒ 同一份桩必须翻回 rc=0——
   牙咬的就是这一枚腿，摘了它本件的红就没了（补回＝去掉 monkeypatch，下一枚用例照旧红）。
"""

from __future__ import annotations

import json

import pytest

from test_r573_a2_three_calibres import (  # noqa: F401  共用同一套桩件与在册件
    LF,
    groups_for,
    rec,
    row,
    synth_rows,
    write_window,
)

TAG = "r573win"
DENOMINATOR = 11
#: 与量具同源的那两枚键名：拒判句必须把修法一步写在盘面上，不然执行层只会再喊一次「量不到」。
TIER_ENV = "EVAL_DECLARE_LANE_TIER"
PER_TIER_ENV = "EVAL_DECLARE_LANE_PER_TIER"


def argv(root, *extra):
    return ["--evalrun", str(root), "--tag", TAG, "--expect-denominator", str(DENOMINATOR), *extra]


def report_with(tmp_path, rows, phase):
    """同一份桩按两种声称各跑一遍：新那把尺只许拦窗，不许挪六组数的分母分子。"""
    root, frames, sidecar, answers = write_window(tmp_path, rows, tag=TAG)
    return rec.build_report(TAG, root, {"frames": frames, "sidecar": sidecar,
                                    "answers": answers}, DENOMINATOR, phase)


def queue_leg_row(index):
    """把第 index 枚桩件改成「这一题真从队列道取回」：kind 一换，其余逐字不动。"""
    rows = synth_rows()
    name = str(rows[index]["id"])
    rows[index] = row(name, kind="queued_polled")
    return rows


# ==================== ① 缺省那一格：本件的读数今天不许漂 ====================


def test_the_default_phase_reads_the_same_numbers_as_today(tmp_path):
    groups, report = groups_for(tmp_path)
    assert sorted(groups) == sorted(rec.CALIBRE_LABELS)
    assert report["lane_leg"]["queue_leg_count"] == 0, "这套桩件本来就没有队列道"
    assert report["lane_leg"]["queue_leg_ids"] == []
    leg = rec.lane_leg_readout(report["records"])
    assert leg == report["lane_leg"], "读数换不来现取：账上的 kind 分布被人改写过"


def test_main_without_the_flag_is_unaffected_by_the_new_cell(tmp_path, capsys):
    root, _f, _s, _a = write_window(tmp_path, synth_rows(), tag=TAG)
    assert rec.main(argv(root)) == rec.RC_OK
    out = capsys.readouterr().out
    assert "- 队列道读数" in out, "新那一格必须写在纸上，不许只活在 json 里"
    assert "queued_* 枚数=0" in out


# ==================== ②「没声明却指望入队」：非零并点名那一扇 ====================


def test_a_window_claiming_queue_with_no_queued_rows_is_refused(tmp_path, capsys):
    root, _f, _s, _a = write_window(tmp_path, synth_rows(), tag=TAG)
    rc = rec.main(argv(root, "--expect-lane-phase", "on"))
    err = capsys.readouterr().err
    assert rc == rec.RC_REFUSE == 2, repr((rc, err))
    assert TAG in err, "判据② 要的是点名那一扇：" + err
    assert "量具缺陷" in err, "归因被改口了：" + err
    assert TIER_ENV in err and PER_TIER_ENV in err, "拒判句没给出修法一步：" + err
    assert "--lane-preflight" in err, "拒判句没把开窗那一步指出来：" + err
    assert "报告档" in err


def test_the_refusal_names_the_kind_distribution_it_actually_read(tmp_path, capsys):
    rows = synth_rows()
    root, _f, _s, _a = write_window(tmp_path, rows, tag=TAG)
    assert rec.main(argv(root, "--expect-lane-phase", "on")) == rec.RC_REFUSE
    err = capsys.readouterr().err
    for kind in {str(item["kind"]) for item in rows}:
        assert kind in err, "拒判句里的 kind 分布没把这一枚点名：" + kind


def test_blinding_the_new_leg_turns_this_tooth_red(tmp_path, monkeypatch):
    """反证牙（判据③ 的摘牙方向）：腿一摘，同一份桩立刻翻回 rc=0——红就红在这枚腿上。"""
    root, _f, _s, _a = write_window(tmp_path, synth_rows(), tag=TAG)
    assert rec.main(argv(root, "--expect-lane-phase", "on")) == rec.RC_REFUSE
    monkeypatch.setattr(rec, "require_lane_leg", lambda *args, **kwargs: None)
    assert rec.main(argv(root, "--expect-lane-phase", "on")) == rec.RC_OK


def test_the_refuse_leg_and_the_call_site_each_have_one_home():
    from pathlib import Path
    source = Path(rec.__file__).read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))
    for anchor in ("def require_lane_leg(", "def lane_leg_readout(",
                   "    lane_leg = lane_leg_readout(records)",
                   "    require_lane_leg(tag, lane_leg, expect_lane_phase)",
                   '"--expect-lane-phase", choices=EXPECT_LANE_PHASES'):
        assert source.count(anchor) == 1, anchor + " 出现 " + str(source.count(anchor)) + " 次"


# ==================== ③ 正控：账上真有一枚队列道 ⇒ 照旧出数、六组数一字不差 ==============


def test_one_queued_row_satisfies_the_gate_and_moves_no_other_number(tmp_path):
    rows = queue_leg_row(0)
    root, _f, _s, _a = write_window(tmp_path, rows, tag=TAG)
    assert rec.main(argv(root, "--expect-lane-phase", "on")) == rec.RC_OK
    off = report_with(tmp_path / "off", rows, "off")
    on = report_with(tmp_path / "on", rows, "on")
    assert json.dumps(off["groups"], ensure_ascii=False, sort_keys=True) == \
        json.dumps(on["groups"], ensure_ascii=False, sort_keys=True), "这把新尺动了六组数的口径"
    assert on["lane_leg"]["queue_leg_count"] == 1, on["lane_leg"]
    assert on["lane_leg"]["queue_leg_ids"] == [str(rows[0]["id"])], on["lane_leg"]


# ==================== ④ 单元格：读数与判据各自可失败 ====================


def test_lane_leg_readout_counts_every_queued_shape():
    records = [{"id": "d-01", "kind": "ok"},
               {"id": "d-02", "kind": "queued_polled"},
               {"id": "d-03", "kind": "queued_approved"},
               {"id": "d-04", "kind": "queued_stalled"},
               {"id": "d-05", "kind": ""}]
    leg = rec.lane_leg_readout(records)
    assert leg["queue_leg_count"] == 3, leg
    assert leg["queue_leg_ids"] == ["d-02", "d-03", "d-04"], leg
    assert leg["kind_counts"]["ok"] == 1 and leg["kind_counts"][""] == 1, leg


def test_off_expect_never_refuses_even_with_zero_queue_rows():
    zero = {"queue_leg_count": 0, "queue_leg_ids": [], "kind_counts": {"ok": 3}}
    assert rec.require_lane_leg("any-tag", zero, "off") is None


def test_the_refusal_is_a_refuse_not_a_green(tmp_path):
    """拒判走本件既有那一族异常：rc 必须是 2（量不到＝拒），不许是新造的第三种绿。"""
    zero = {"queue_leg_count": 0, "queue_leg_ids": [], "kind_counts": {"ok": 3}}
    with pytest.raises(rec.RefuseError) as caught:
        rec.require_lane_leg("run24s2", zero, "on")
    assert "run24s2" in str(caught.value)

