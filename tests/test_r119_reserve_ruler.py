# -*- coding: utf-8 -*-
"""R119 · 把量"上下文预留"的那两把假尺换成实测尺，并按实测重排两枚预留常数。

跟进单 §55 的原始指控是：``CONTEXT_HISTORY_RESERVE_TOKENS = 322`` 只够 0.75 轮真问答，而
量它的那把夹具尺是假的。本文件先把尺钉回真机，再记下重排后的净效果。全部离线：不连模型、
不起服务、不动数据；真机数一律取自 ``scripts/perf_probe_run5_ledger.py`` 烘进仓库的实测表。

量出来的三件事（口径与样本 n 全写在这里，回执同稿）：

1. **历史侧尺是假的**：老夹具 ``("上一轮的结论：…" * 6)[:400]`` 实际只有 **132 字**
   （那句 22 字 × 6），``[:400]`` 是空操作——132 字冒称 400 字。真机 run5 全部 105 题
   ``answer_chars`` 的中位是 **424 字**。同一条组装路径上：132 字量出每轮 161 枚，
   400 字量出 **429 枚**（与跟进单 §55 记的 403~429 逐字对上），424 字量出 **453 枚**。
   两轮 ⇒ 322 枚其实是 906 枚。
2. **壳侧尺也是假的（虚高方向）**：探针表的题面是 10/64/90/800 字合成长度（注释写"≤400
   字"，实际那格 800 字），而 run5 真题面只有 **8~20 字**（n=105，中位 12 字）。只换题面、
   规划文字与 1~3 轮工具调用一格不动，四条腿 × 八形态的最大值从 632 掉到 **456**。真机侧
   独立复算："本轮第一发装箱"（``packs == 1``，n=37）的固定壳是 **90~163** 枚。
3. **净效果是房变小了**：预留 954 -> 1362（壳 -176、历史 +584），本轮 room 1606 -> **1198**
   （-408 枚，-25.4%）。按这把新尺正向复算 run5 那 89 发台账：有料的发 55 -> 37，送出的料
   200 条 -> 128 条，枚数 53023 -> 37675。R116 那句"17 枚 refused 全部变实料"是**实测壳
   口径**的命题（与预留常数无关，仍成立），不是"新预留下也装得下"——后者是 0/17。
"""
from __future__ import annotations

import ast
import io
import math
import os
import sys

from app.rag.retrieval_pipeline import (
    CONTEXT_HISTORY_RESERVE_TOKENS,
    CONTEXT_PACK_TIER,
    CONTEXT_SHELL_RESERVE_TOKENS,
    DOC_HIT_CONTENT_CHARS,
    context_pack_capacity,
    context_pack_room,
)
from scripts import perf_probe_run5_ledger as run5

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import tests.test_r112_prompt_packing as t112  # noqa: E402

RESERVE = CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS

#: 判据 2 要的"量出来的算式 + 样本 n"，全部是复算结果，抄在这里只为让失败信息能报数。
RUN5_SAMPLE_QUESTIONS = 105          # 答案长度与题面长度的样本量
RUN5_SAMPLE_PACKS = 89               # 台账行数（每腿每发）
RUN5_SAMPLE_FIRST_PACKS = 37         # 其中"本轮第一发装箱"的行数
MEDIAN_ANSWER_CHARS = 424            # run5 答案长度中位（历史夹具的尺子）
MEDIAN_QUESTION_CHARS = 12           # run5 题面中位
LONGEST_QUESTION_CHARS = 20          # run5 题面最长
REAL_UNIT_TOKENS_PER_TURN = 453      # 424 字答案：每轮"上一问 + 上一答"实测单价
FAKE_UNIT_TOKENS_PER_TURN = 161      # 132 字那把短尺量出来的单价（本文件不许它回来）
FIRST_PACK_SHELL_MAX = 163           # 真机第一发固定壳实测上界
RUN5_LEGACY_SHELL = 632              # R112 当时的壳预留（虚高，已换）
RUN5_LEGACY_HISTORY = 322            # R112 当时的历史预留（短尺量出来的，已换）


def _ledger_rows():
    return run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)


def _refused_rows():
    return run5.records(run5.MEASURED_REFUSED_RUN5, run5.REFUSED_FIELDS)


def _fit_under(base_room: int, rows) -> tuple:
    """把台账每行的"本轮已装"还原成 run5 当时的口径，再用 ``base_room`` 重放装箱。

    ``room_left`` 是 ``RUN5_ESTIMATED_ROOM - 本轮已装`` 的结果，所以本轮已装必须从**历史**
    锚点还原，换口径重放时才不会被今天的预留二次计价。
    """
    fitted = conditions = 0
    for row in rows:
        used_before = run5.RUN5_ESTIMATED_ROOM - int(row["room_left"])
        got, dropped, used = run5.fit_prices(run5.replay_prices(row), max(0, base_room - used_before))
        fitted += 1 if got else 0
        conditions += got
    return fitted, conditions, sum(
        run5.fit_prices(run5.replay_prices(row),
                        max(0, base_room - (run5.RUN5_ESTIMATED_ROOM - int(row["room_left"]))))[2]
        for row in rows
    )


def _measured_room_replay(rows) -> tuple:
    """判据 2 那套"按真机实测壳"的复算：容量与壳都取自真机，与预留常数无关。"""
    lines = 0
    conditions = 0
    tokens = 0
    for row in rows:
        room = max(0, run5.measured_room(row, run5.RUN5_CAPACITY)
                    - (run5.RUN5_ESTIMATED_ROOM - int(row["room_left"])))
        got, dropped, used = run5.fit_prices(run5.replay_prices(row), room)
        lines += 1 if got else 0
        conditions += got
        tokens += used
    return lines, conditions, tokens


# ==================== 判据 1：先把尺修对 ====================


def test_history_ruler_is_the_measured_answer_length_not_a_hand_copy():
    """夹具的"上一答"字数必须等于 run5 实测中位，且这枚数来自台账而不是手抄。"""
    stats = run5.answer_char_stats()
    assert stats["n"] == RUN5_SAMPLE_QUESTIONS, stats
    assert stats["median"] == MEDIAN_ANSWER_CHARS, stats
    assert t112.HISTORY_ANSWER_CHARS == stats["median"], (
        f"历史夹具标称 {t112.HISTORY_ANSWER_CHARS} 字，台账实测中位 {stats['median']} 字：字数被手抄了"
    )
    text = t112._history_answer_text()
    assert len(text) == MEDIAN_ANSWER_CHARS, f"标称 {MEDIAN_ANSWER_CHARS} 字，实得 {len(text)} 字"


def test_the_132_char_fake_ruler_cannot_come_back():
    """老夹具那把 132 字短尺必须绝迹：往 prompt 里塞上一答的那一行必须走实测尺函数。

    用 ast 看结构而不是 grep 文本——本文件与夹具的注释里都得把老写法引出来当靶子，拿全文
    grep 会打在自家写的说明上，那种守法是假守。
    """
    tree = ast.parse(io.open(os.path.join(REPO, "tests", "test_r112_prompt_packing.py"),
                             encoding="utf-8").read())
    assemble = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "_assemble_and_measure")
    def _content(node):
        if node.args:
            return node.args[0]
        for keyword in node.keywords:
            if keyword.arg == "content":
                return keyword.value
        raise AssertionError("AIMessage 没有 content 实参，锚点失效")

    ai_calls = [
        _content(node) for node in ast.walk(assemble)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "AIMessage"
    ]
    measured = [
        node for node in ai_calls
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_history_answer_text"
    ]
    def _name_of(node):
        target = node.func if isinstance(node, ast.Call) else node
        return getattr(target, "id", type(node).__name__)

    contents = [_name_of(node) for node in ai_calls]
    assert "_history_answer_text" in contents, (
        "夹具的上一答不再由那把实测尺函数交出：132 字冒称 400 字那把短尺可能回来了"
    )
    assert contents.count("_history_answer_text") == 1, contents
    assert all(name in {"_history_answer_text", "prose"} for name in contents), contents
    assert not any(isinstance(node, (ast.Subscript, ast.BinOp, ast.Constant)) for node in ai_calls), (
        "夹具里又出现就地拼字数或就地截断的字面量：尺子必须走 HISTORY_ANSWER_CHARS 那一条路"
    )


def test_history_unit_price_is_measured_on_the_real_ruler():
    """同一条组装路径：真尺单价 453 枚/轮，且远高于 132 字那把短尺量出的 161 枚。"""
    unit = t112._measured_history_unit_price()
    assert unit == REAL_UNIT_TOKENS_PER_TURN, f"每轮历史实测 {unit} 枚，与回执算式不符"
    assert unit > FAKE_UNIT_TOKENS_PER_TURN * 2.5, (
        f"每轮只有 {unit} 枚：夹具又缩回 132 字那把短尺（它量出 {FAKE_UNIT_TOKENS_PER_TURN} 枚）"
    )


def test_question_ruler_is_the_real_bank_length_not_synthetic():
    """探针表的题面必须来自真机评测集：中位 12 字、最长 20 字，不许再喂 800 字合成题面。"""
    assert len(t112.Q_MEDIAN) == MEDIAN_QUESTION_CHARS, len(t112.Q_MEDIAN)
    assert len(t112.Q_LONGEST) == LONGEST_QUESTION_CHARS, len(t112.Q_LONGEST)
    assert len(t112.Q_LONGEST) < 40, "壳探针表的题面又长回合成尺寸了：那正是 632 虚高的来源"


# ==================== 判据 2：两枚常数按实侧重填 ====================


def test_shell_reserve_is_the_measured_ceiling_with_real_machine_crosscheck():
    """壳预留＝换尺后的合成上界 456，并且盖得住真机第一发实测壳上界 163（n=37）。"""
    assert CONTEXT_SHELL_RESERVE_TOKENS == t112._measured_shell_ceiling() == 456
    stats = run5.first_pack_shell_stats()
    assert stats["n"] == RUN5_SAMPLE_FIRST_PACKS and stats["max"] == FIRST_PACK_SHELL_MAX, stats
    assert stats["min"] == 90, stats
    assert CONTEXT_SHELL_RESERVE_TOKENS > FIRST_PACK_SHELL_MAX, (
        f"壳预留 {CONTEXT_SHELL_RESERVE_TOKENS} 连真机第一发实测上界 {FIRST_PACK_SHELL_MAX} 都盖不住"
    )
    assert CONTEXT_SHELL_RESERVE_TOKENS < RUN5_LEGACY_SHELL, (
        f"壳预留 {CONTEXT_SHELL_RESERVE_TOKENS} 没降下来：虚高的 {RUN5_LEGACY_SHELL} 枚还在"
    )
    assert CONTEXT_SHELL_RESERVE_TOKENS - stats["max"] == 293, (
        f"壳预留比真机上界多留 {CONTEXT_SHELL_RESERVE_TOKENS - stats['max']} 枚："
        "这笔余量是留给同轮第 2~3 发重复规划文字的，数目变了要说清为什么"
    )


def test_history_reserve_is_unit_price_times_covered_turns():
    """历史预留＝实测单价 453 × 覆盖轮数 2 = 906，算式当场复算一遍。"""
    unit = t112._measured_history_unit_price()
    needed = math.ceil(unit) * t112.COVERED_HISTORY_TURNS
    assert CONTEXT_HISTORY_RESERVE_TOKENS == needed == 906, (unit, needed)
    assert CONTEXT_HISTORY_RESERVE_TOKENS > RUN5_LEGACY_HISTORY, (
        f"历史预留还是 {RUN5_LEGACY_HISTORY} 枚：0.75 轮真问答那个欠账没还"
    )


def test_both_reserves_are_measured_odd_numbers_not_round_guesses():
    """两枚都必须是量出来的怪数：整十整百在这里就是拍脑袋的证据（R112 立的规矩继续管）。"""
    assert CONTEXT_SHELL_RESERVE_TOKENS % 10 != 0, CONTEXT_SHELL_RESERVE_TOKENS
    assert CONTEXT_HISTORY_RESERVE_TOKENS % 10 != 0, CONTEXT_HISTORY_RESERVE_TOKENS
    assert RESERVE % 10 != 0, RESERVE


# ==================== 判据 4：净效果与方向 ====================


def test_reserve_total_stays_strictly_inside_capacity():
    """重排之后总量不许撑爆：0 < 预留 < 容量，还留得出可装箱的房。"""
    capacity = context_pack_capacity()
    assert 0 < RESERVE < capacity, (RESERVE, capacity)
    assert context_pack_room() == capacity - RESERVE > 0
    assert capacity - RESERVE == 1198, capacity - RESERVE


def test_net_effect_direction_and_magnitude_are_recorded():
    """把"哪一侧降、哪一侧升、净下来多少房"三笔一次摊清（回执 ④ 同稿）。"""
    shell_delta = CONTEXT_SHELL_RESERVE_TOKENS - RUN5_LEGACY_SHELL
    history_delta = CONTEXT_HISTORY_RESERVE_TOKENS - RUN5_LEGACY_HISTORY
    legacy_reserve = RUN5_LEGACY_SHELL + RUN5_LEGACY_HISTORY
    assert (shell_delta, history_delta) == (-176, 584), (shell_delta, history_delta)
    assert RESERVE - legacy_reserve == 408, RESERVE - legacy_reserve
    room_before = run5.RUN5_CAPACITY - legacy_reserve
    room_after = context_pack_room()
    assert (room_before, room_after) == (1606, 1198)
    assert room_after - room_before == -408
    assert round(100.0 * (room_after - room_before) / room_before, 1) == -25.4
    assert history_delta > abs(shell_delta), (
        "净效果是房变小：因为历史欠账（+584）大于壳侧挤出来的余量（-176），"
        "这是把 0.75 轮的假账还成真账的必然结果，不许倒过来用虚高预留粉饰房"
    )


def test_the_untouchable_levers_are_untouched():
    """本单只动"预留"这两个数：档位与单条料长度一格没动。"""
    assert CONTEXT_PACK_TIER == "analysis", CONTEXT_PACK_TIER
    assert DOC_HIT_CONTENT_CHARS == 500, DOC_HIT_CONTENT_CHARS
    assert t112.COVERED_HISTORY_TURNS == 2, t112.COVERED_HISTORY_TURNS


# ==================== 判据 3：尺一动，R116 那本账必须重算 ====================


def test_criterion_two_answer_is_a_measured_shell_statement_and_still_17_of_17():
    """判据 2 那句"17 枚全部变实料"是**实测壳**口径：与预留无关，换尺之后仍然成立。"""
    assert _measured_room_replay(_refused_rows()) == (17, 31, 8961)
    assert _measured_room_replay(_ledger_rows()) == (85, 306, 83948)


def test_under_the_rearranged_reserve_run5_refused_packs_still_refuse():
    """换到新预留口径下正向复算：那 17 枚一枚都变不成实料——这是必须重算出来的新数。"""
    assert _fit_under(context_pack_room(), _refused_rows()) == (0, 0, 0)
    assert _fit_under(run5.RUN5_ESTIMATED_ROOM, _refused_rows()) == (0, 0, 0), "run5 当时也是整条拒发"
    lines, conditions, tokens = _fit_under(context_pack_room(), _ledger_rows())
    assert (lines, conditions, tokens) == (37, 128, 37675), (lines, conditions, tokens)
    legacy = _fit_under(run5.RUN5_ESTIMATED_ROOM, _ledger_rows())
    assert legacy == (55, 200, 53023), legacy
    assert lines < legacy[0] and conditions < legacy[1] and tokens < legacy[2], (
        "换尺之后台账反而装得更多：说明预留没按实测重排，是给分数放水的"
    )


def test_over_reserve_table_is_invalid_until_the_ledger_is_re_emitted():
    """今天的房去反推 run5 的估窄会虚增 408 枚：不 ``--emit-table`` 重烘就不许引用。"""
    rows = _ledger_rows()
    anchored = [run5.measured_room(r, run5.RUN5_CAPACITY) - run5.RUN5_ESTIMATED_ROOM for r in rows]
    polluted = [run5.measured_room(r, run5.RUN5_CAPACITY) - context_pack_room() for r in rows]
    assert max(anchored) == 864 and min(anchored) == -200, (min(anchored), max(anchored))
    drift = run5.RUN5_ESTIMATED_ROOM - context_pack_room()
    assert drift == 408 and [a + drift for a in anchored] == polluted, (
        f"两副口径的差不是 {RESERVE - run5.RUN5_RESERVE} 枚：锚点用法有第三处在混账"
    )
    assert run5.RUN5_RESERVE == 954 and RESERVE != run5.RUN5_RESERVE, (run5.RUN5_RESERVE, RESERVE)
