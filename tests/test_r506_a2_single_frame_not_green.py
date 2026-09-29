# -*- coding: utf-8 -*-
"""R506 钉①（2026-09-29，执行层 Feynman）：``single_frame`` 那一形**不许被读成判据② 绿**。

背景：A②「``text`` 事件数 >1 且逐字比对无缺字」至今没宣布验过，run9 帧账上②原文红 11 枚，
其中 9 枚是 ``event_form == "single_frame"``（读数见 ``docs/testing/r506-a2-reading-2026-09-29.md``）。
这一族的病形是「本轮一帧到位」：逐字那一半（②-b）全绿，红只在②-a。危险的读法不是把它判红，
而是**拿账上那枚 ``criterion_two_holds`` 或拿「字没丢」把它洗成绿**。本钉封四件事：

1. ``text_frames == 1`` 且逐字三格全过 ⇒ ②-a 必红、②原文 verdict 必红、形必是 ``single_frame``；
2. 🔴 账上伪造一枚 ``criterion_two_holds=true`` **带不动**②原文绿（两把尺各读各的），
   且这一行必须落进 ``disagreements`` 而不是悄悄从分母里消失；
3. ``text_frames == 0`` 的 ``error_event``/``no_answer`` 形（``metric-02``/``scope-02`` 那一族）
   必须**继续占住分母**并记在 ``criterion_two_fails_literal`` 里，不许被静默摘掉；
4. ``one_frame_per_stream``（``chart-01`` 那一族）必须同时报「②原文绿」与「②之外还红在
   ``max_stream_frames>1``」，绿与红的归因不许混。

夹具是**当场构造的合成小片帧账**（几行 JSON，落在 ``tmp_path``）：🔴 本文件不读
``docs/testing/sidecar-run9-frames.jsonl``（903 KB 在册全量原件），零网络、零容器、零模型。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "r239_stream_gap_offline_audit", REPO_ROOT / "scripts" / "r239_stream_gap_offline_audit.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def ledger_row(row_id="synthetic-01", **overrides):
    """一枚「逐字那一半全过、只到了一帧」的合成帧账行。

    形状照 run9 那 9 枚 ``single_frame`` 的最小充分集抄：一帧整段到位、不缺字不多字、
    末帧覆盖终答、无未受控坏形、账上 ``criterion_two_holds`` 诚实记 False。
    """
    row = {
        "id": row_id,
        "kind": "ok",
        "text_frames": 1,
        "max_stream_frames": 1,
        "streams": 1,
        "per_stream": [{"frames": 1, "breaks": 0, "first_break_at": 0}],
        "missing_chars": 0,
        "extra_chars": 0,
        "last_frame_covers_answer": True,
        "uncorrected_breaks": 0,
        "answer_chars": 69,
        "criterion_two_holds": False,
    }
    row.update(overrides)
    return row


def write_ledger(path, rows):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                    encoding="utf-8")
    return path


def test_a1_single_frame_is_red_on_the_event_count_even_when_every_char_arrived():
    """②-a 只问「>1 枚事件」：一帧到位就是红，逐字三格全绿也救不回来。"""
    judged = audit.judge_row(ledger_row())

    assert judged["event_count_gt_1"] is False, "text_frames==1 不许读成 ②-a 真"
    assert judged["char_by_char_no_loss"] is True, "夹具的逐字那一半本来就该是绿的"
    assert judged["verdict"] is False, "②-a 红 ⇒ ② 原文合取必红"
    assert judged["event_form"] == "single_frame"
    assert judged["extra_red_conditions"] == [], "红因只许记在 ②-a，不许伪造 ② 之外的红"


def test_a2_a_forged_ledger_green_cannot_turn_the_literal_two_green():
    """🔴 核心那一枚：账上写 true 也带不动②原文 —— 两把尺各读各的，且当场记成分歧。

    run9 真账没有这一形，它是本件构造的「谁想拿存档格洗绿」的反证：判器若哪天改成
    ``verdict = ledger``，这一枚立刻红。
    """
    judged = audit.judge_row(ledger_row("synthetic-forged", criterion_two_holds=True))

    assert judged["ledger_criterion_two_holds"] is True, "夹具确实伪造了一枚账上绿"
    assert judged["verdict"] is False, "②原文绿不许跟着账走"
    assert judged["disagreement"] is True

    summary = audit.summarize([judged])
    assert summary["criterion_two_holds_literal"] == 0, "洗绿：这条必红"
    assert summary["criterion_two_fails_literal"] == 1, "该行必须还占着分母"
    assert summary["disagreements"] == ["synthetic-forged"], "分歧必须点名，不许静默"


def test_a3_zero_text_frame_error_row_stays_in_the_denominator():
    """``metric-02``/``scope-02`` 那一族：``text_frames==0`` 的 ``error_event`` 不许被摘出②分母。

    读数件 §2.B 建议把它挪出 A② 的分母并另立 ``no_answer`` 计数 —— 那要由**口径裁定 + 判器改动**
    一起做。判器今天还是按②原文判它红，本钉封的就是「**在裁定落地之前，一枚都不许从分母里蒸发**」：
    否则翻绿可以是靠删行翻的。
    """
    row = ledger_row("synthetic-no-answer", kind="error_event", text_frames=0,
                     max_stream_frames=0, per_stream=[{"frames": 0, "breaks": 0,
                                                       "first_break_at": 0}],
                     extra_chars=21, last_frame_covers_answer=False,
                     last_text_frame=None, last_frame_chars=0)
    judged = audit.judge_row(row)
    summary = audit.summarize([judged])

    assert judged["event_form"] == "no_text_frame"
    assert judged["verdict"] is False
    assert summary["rows"] == 1, "零文本帧行不许掉出分母"
    assert summary["criterion_two_fails_literal"] == 1
    assert summary["event_forms"] == {"no_text_frame": 1}


def test_a4_one_frame_per_stream_is_green_on_two_but_red_on_the_extra_conjunct():
    """``chart-01`` 那一族：②原文 TRUE 而账 FALSE，红因必须是自加的 ``max_stream_frames>1``。

    这条封的是「口径分歧」与「丢帧」不许混读：两帧分属两条流、每条各一枚整段帧时，
    ②原文两格全过，而真尺多要的那枚「有一条流在逐片累计」不成立。
    """
    row = ledger_row("synthetic-two-single-flush-streams", kind="approved_ok",
                     text_frames=2, max_stream_frames=1, streams=2,
                     per_stream=[{"frames": 1, "breaks": 0, "first_break_at": 0},
                                 {"frames": 1, "breaks": 0, "first_break_at": 0}],
                     answer_chars=16)
    judged = audit.judge_row(row)

    assert judged["event_form"] == "one_frame_per_stream"
    assert judged["verdict"] is True, "②原文两格都过：这一枚不是丢字"
    assert judged["ledger_criterion_two_holds"] is False
    assert judged["extra_red_conditions"] == ["max_stream_frames>1"], \
        "②之外的红因必须逐枚点名，只可能是真尺自加的那几枚"


def test_a5_single_frame_row_shows_up_in_the_red_only_view(tmp_path, capsys):
    """``--red-only`` 必须把单帧行列出来：红不许因为「账和②都同意红」以外的事被过滤掉。"""
    ledger = write_ledger(tmp_path / "tiny-frames.jsonl", [ledger_row("synthetic-01")])

    rc = audit.main(["--frames", str(ledger), "--red-only"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "synthetic-01" in out, "唯一一枚红行必须出现在 red-only 视图"
    assert "single_frame" in out
    assert "②红=1" in out


@pytest.mark.parametrize("form,expected_two", [
    ({"text_frames": 1, "max_stream_frames": 1, "streams": 1,
      "per_stream": [{"frames": 1}]}, False),
    ({"text_frames": 2, "max_stream_frames": 2, "streams": 1,
      "per_stream": [{"frames": 2}]}, True),
])
def test_a6_the_gate_is_the_per_stream_cumulation_not_the_total_frame_count(form, expected_two):
    """同一份逐字读数下，只有「有一条流自己累计出 >1 帧」才读得出②绿。

    ``incremental_within_one_stream`` 问的就是这一格（判据
    ``scripts/r239_stream_gap_offline_audit.py:215``），它不是②绿的同义词，但**总数凑够而无人累计**
    那一形（上面 test_a4）与**一帧到位**那一形都必须红/分歧，各自红因不同名。
    """
    judged = audit.judge_row(ledger_row(**form))

    assert judged["verdict"] is expected_two
    if expected_two:
        assert judged["event_form"] == "incremental_within_one_stream"
        assert judged["extra_red_conditions"] == []
    else:
        assert judged["event_form"] == "single_frame"