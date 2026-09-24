# -*- coding: utf-8 -*-
"""R210 判据 1：断流轮在**帧账**上到底读成什么。这一格本单没做到，理由钉在这里。

判据 1 要的是「provider 中途死掉且已发 >=1 片」这一形状下 ``prefix_breaks == 0``。实测：
**带着 R210 的守卫它仍然是 1** —— 守卫改的是「屏上怎么显示」，改不了「线上曾经发过什么」，
而评分器那把尺（``scripts/eval_transport_ask_v2.py::_count_text_frame``）量的就是后者。

为什么在「不改量具、不改前端、断流轮线上必有 >=1 枚半截帧」这三条约束下它不可能成立：
设这一轮线上的 text 帧为 ``F1..Fk``（``k >= 2``，判据形状就是「已发 >=1 片」）。

1. 尺那一头：``_count_text_frame`` 逐枚比相邻两帧，要求 ``Fi.startswith(F(i-1))``，
   否则 ``prefix_breaks += 1``。要 0 坏形，必须 ``F(k-1)`` 是 ``Fk`` 的前缀。
2. 屏那一头：``sessions.js`` 三条把字弄上屏的分支里，``_correcting``(:482) 与
   covering(:490) 都是把 ``msg.content`` **整段置成** chunk，追加(:491) 是在已有正文后面
   拼接。判据 2 要求屏上恰等于离线话术，而屏上最后落的正是末帧的 chunk —— ``Fk`` 必须
   恰等于离线话术本身（不能带半截真话的脑袋，也不能指望别的帧替它说话）。
3. 两式相抵 —— ``F(k-1)`` 必须是离线话术的前缀。而 ``F(k-1)`` 是模型真写出去的半截正文
   （``_AnswerPieceStream.frame_for`` 只在正文非空时才出帧），预制话术与它只在空串处相交
   —— 只有 ``k == 1``（这一轮一枚半截帧都没发）才可能两头同时成立，而那正是改前
   pieces 恒 0 的形状，见本文件倒数第二枚用例。

要判据 1 与判据 2 一起成立，只有三条路，三条都在本单写域之外：
  (a) 不发半截帧 —— 收端没有预知这一发会不会死的本事；把帧改成「腿落定才发」确实能把尺
      读绿，但那正是看板 §4 记名的「把判据② 从诚实的红翻成假绿」那一坑：逐字交付当场
      变成收尾一次爆发，``first_token_at`` 也跟着变假。
  (b) 收尾不发 ``text`` 帧 —— 屏上留着半截真话冒充答案，判据 2 当场死。
  (c) 让量具认得「纠正帧」（改 ``scripts/eval_transport_ask_v2.py`` = 改量具，须业主裁定）。

所以本文件钉的是**读数本身 + 可归因性**：坏形恰一枚，且恰指到守卫当作纠正替换发出去的
那一枚末帧；中途的累计帧一枚都没坏。摘掉守卫之后，``prefix_breaks`` 一格都不会变好，
而「这枚坏形是那次纠正替换」这一格当场红 —— 那才是守卫在帧账这一侧真正做到的事。
"""

import pytest

from app.agents import nodes
from app.api.v1 import chat

from tests.test_r210_break_replaces_the_screen import (  # noqa: F401  -- 同一条链，不造第二份
    DIE_AFTER_FRAMES,
    _readings,
    _round,
    _text_contents,
    _wire,
    ruler,
)


# ==================== 判据 1 的实测读数（守卫带着，仍然是 1）====================


def test_the_frame_ledger_of_a_broken_round_still_counts_one_break(monkeypatch, tmp_path):
    """没做到：判据 1 要 0，实测 1。这一枚钉的是**真读数**，不是愿望。

    同时钉住另外三格：末帧就是交付的那份字（``extra_chars``/``missing_chars`` 恒 0），
    以及坏形只有一枚、不早不晚正好落在末帧。
    """
    ask = _round(monkeypatch, tmp_path, [("doc", None)], die_after=DIE_AFTER_FRAMES)
    body = ask()
    contents = _text_contents(body)
    readings = _readings(body)

    assert len(contents) >= 2, "断流形状没构造成功：一枚半截帧都没发出去"
    assert readings["text_frames"] == len(contents), readings
    assert readings["prefix_breaks"] == 1, f"读数与交回单不符，先重测再来判：{readings}"
    assert readings["extra_chars"] == 0, readings
    assert readings["missing_chars"] == 0, readings
    # 评分器自己折出来的那一格判据② —— 断流轮今天就是 False，红得诚实。
    assert ruler._frame_verdict(readings) is False, readings


def test_the_single_break_is_the_corrective_replacement_itself(monkeypatch, tmp_path):
    """守卫做到的那一格：那枚坏形**就是**那次纠正替换，中途的累计帧一枚没坏。

    ``first_break_at`` 记的是坏形那一枚帧的序号（1 起）。它等于总帧数 —— 前面每一枚相邻
    帧都仍满足累计语义，坏的只有收尾那一枚换源帧。这一格是守卫在帧账这一侧唯一能给的
    东西：红，但是红得可归因，run7 当场读得出「这是断流轮的替换」而不是「流被截断了」。

    反证（交回单里现场施加过）：摘掉守卫 —— ``prefix_breaks`` 一格都不会变好，而本枚当场
    红 —— 末帧前面那枚武装替换的 ``step`` 不在了，坏形再也指不回那次纠正替换。
    """
    ask = _round(monkeypatch, tmp_path, [("doc", None)], die_after=DIE_AFTER_FRAMES)
    body = ask()
    readings = _readings(body)

    per_stream = readings["per_stream"][0]
    assert per_stream["frames"] == readings["text_frames"], per_stream
    assert per_stream["breaks"] == 1, per_stream
    assert per_stream["first_break_at"] == readings["text_frames"], (
        f"坏形不在末帧，中途的累计帧也坏了：{per_stream}"
    )
    assert readings["max_stream_frames"] == readings["text_frames"], readings

    wire = _wire(body)
    last_text_at = max(index for index, (name, _p) in enumerate(wire) if name == "text")
    arm = wire[last_text_at - 1]
    assert arm[0] == "step", f"末帧前一枚不是 step：{arm}"
    assert arm[1].get("tool") == chat.CORRECTION_STEP_TOOL, arm
    assert arm[1].get("status") == "running", arm


# ==================== 边界：没流起来的那一格，尺本来就是 0 ====================


@pytest.mark.parametrize("die_after", [2, 3, 4])
def test_a_break_before_the_first_frame_reads_zero_breaks(monkeypatch, tmp_path, die_after):
    """``k == 1`` 那一格：provider 死在第一枚帧之前，线上只有离线话术一枚帧。

    这一格 ``prefix_breaks`` 本来就是 0，屏上也本来就只有离线话术 —— 判据 1 与判据 2 在
    这里**同时成立**，正因为这里没有半截真话。它把上面那段证明摆成了事实：尺要回到 0，
    缺的不是守卫，是「别把会换源的那半截字发出去」，而那一步收端做不到。
    """
    ask = _round(monkeypatch, tmp_path, [("doc", None)], die_after=die_after)
    body = ask()
    contents = _text_contents(body)
    readings = _readings(body)

    assert readings["prefix_breaks"] == 0, readings
    assert len(contents) == 1, f"{die_after} 枚流帧之后居然还出了帧：{contents}"
    assert nodes.is_offline_reply_text(contents[0]), "末帧不是离线话术：这一格形状换了，先取证再说"


# ==================== 判据 1 的目标：明写没做到 ====================


@pytest.mark.skip(
    reason=(
        "判据 1 没做到：断流轮的 prefix_breaks 实测 1（见上面两枚）。守卫改的是屏上显示，"
        "改不了线上发过什么；要它读 0 只能不发半截帧（收端无预知能力）或改量具"
        "（越界，须业主裁定）。证明与本文件的实测读数一起写在交回单。"
    )
)
def test_judgment_one_prefix_breaks_back_to_zero():
    """占位：判据 1 原文「帧账口径下断流轮的 prefix_breaks 回到 0」。

    留着这枚 skip 而不是悄悄不写，是为了让它在每次跑分抬头里都被数到一次。谁真做到了，
    把上面那枚 ``..._still_counts_one_break`` 一起改绿 —— 两枚是对着钉的，改不动就跳不过。
    """
