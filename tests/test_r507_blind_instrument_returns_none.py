# -*- coding: utf-8 -*-
"""R507 假零钉：量具被摘瞎那一窗必须回 ``None``（未量），不许回 0（量过了且没重合）。

病（本单唯一的对象是**读数件**，不是产品，也不是帧账那一行）：``scripts/eval_transport_ask_v2.py`` 的
``_cross_stream_repeats`` 在自己的 docstring 里承论「派生不出＝这一格今天没量过，调用方按
``REPEAT_DELIVERY_UNMEASURED`` 读，🔴 不重判当年的读数」，落码却把每一形都折成一个整数：帧在、逐帧一枚
``sha`` 都拿不到（**量具被摘瞎**那一窗，同 ``docs/testing/r506-a2-reading-2026-09-29.md`` §5 第 5
条给复算件记的那一笔）照样交回 0。0 与「确实没重合」并脸 ⇒ 摘瞎窗口读成「量过了且没重
合」，正是事故 #73 那一族假零（P-18 量具第二次以假零骄过操作员）。

本单把两形分开：
  * 帧在而一枚指纹都拿不到 ⇒ ``None``（未量）；
  * 拿到了指纹且确实没有跨流重合 ⇒ 才回 0（量过了）。
🔴 入参不是帧表或枚数为零（空读那一形）**不在本单范围**：那一形钉在
``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``（``_cross_stream_repeats([]) ==
  0``），
那枚文件不在本单写域，改它要总控同笔改口。两形分家后的语义、调用点与残余分歧见
``docs/testing/r507-blind-instrument-returns-none.md``。

🔴 离本单一字之遥的第二份复算件 ``scripts/r239_stream_gap_offline_audit.py::cross_stream_repeat_frames``
有同一枚缺陷（它的 docstring 明写「或有这一列却一枚逐帧指纹都不带 ⇒ 回 ``None``」），但工单禁碰那枚件，
所以它的现状钉 ``tests/test_r506_a2_ledger_required_keys.py:162`` 今天仍钉「读 0」。那一半的改口不是本单能交的活，
本件只把**写域内**那一半钉死，并把分歧写在纸上。

全程离线：合成帧直接喂函数本体，importlib 单独加载。不打模型、不起服务、不动容器、不写仓内产物。
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r507_blind_instrument_ruler", REPO_ROOT / "scripts" / "eval_transport_ask_v2.py")
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

#: 第七枚合取那枚证词的名字（判定视图里的派生读数，不是帧账的一格）。
CELL = "cross_stream_repeat_frames"

#: 🔴 量具被摘瞎那一形：帧在、正文也在，逐帧却一枚 ``sha`` 都没有（旧落码在这里交回 0）。
BLIND = [{"stream": 0, "at": 1, "chars": 20, "elapsed_ms": 12.0},
         {"stream": 0, "at": 2, "chars": 40, "elapsed_ms": 40.0},
         {"stream": 1, "at": 3, "chars": 40, "elapsed_ms": 71.0}]

#: 拿到了指纹且确实没重合：两条流交的是不同的字（换源），这一形才许读 0。
WITNESSED_NO_OVERLAP = [{"stream": 0, "chars": 20, "sha": "aaaaaaaaaaaa"},
                        {"stream": 0, "chars": 40, "sha": "bbbbbbbbbbbb"},
                        {"stream": 1, "chars": 33, "sha": "cccccccccccc"}]

#: 病形：后一条流把前一条流已上屏的那份字又发一遍（R464 拟的批准腿病）。
RESEND = [{"stream": 0, "chars": 20, "sha": "aaaaaaaaaaaa"},
          {"stream": 0, "chars": 40, "sha": "bbbbbbbbbbbb"},
          {"stream": 1, "chars": 40, "sha": "bbbbbbbbbbbb"}]

#: 总控裁定的那一形：同一条流里末片帧与收尾帧同文，不算「出现两遍」。
SAME_LEG = [{"stream": 0, "chars": 20, "sha": "aaaaaaaaaaaa"},
            {"stream": 0, "chars": 20, "sha": "aaaaaaaaaaaa"}]


def _green_readings(**over):
    """六枚合取全绿的一份读数，再把第七枚证词按入参换掉（钉尺子对 ``None`` 的读法）。"""
    readings = {"text_frames": 3, "max_stream_frames": 2, "uncorrected_breaks": 0,
                "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answer": True}
    readings.update(over)
    return readings


def test_a1_the_blind_window_is_unmeasured_not_a_clean_zero():
    """🔴 本单的牙：帧在而一枚指纹都拿不到 ⇒ ``None``（未量），不再是 0。

    旧落码在这一形交回 0（``if not sha: continue`` 跳完之后直接 ``return repeats``），于是摘瞎窗口读成
    「量过了且没重合」；钉死它，听不见的量具就不许冒弹成一枚绿。
    """
    assert ruler._cross_stream_repeats(BLIND) is None


def test_a2_a_witnessed_window_with_no_overlap_is_a_real_zero():
    """反向的同一条纪律：拿到了指纹且确实没重合 ⇒ 才允许是 0，不许倒打一蝶回 ``None``。

    把这一形也成 ``None`` 等于把「量过了」说成「没量过」，那是把本单的论据提反。
    """
    reading = ruler._cross_stream_repeats(WITNESSED_NO_OVERLAP)
    assert reading == 0, reading
    assert reading is not None, "量过了且没重合不许伪装成未量"


def test_a3_the_two_shapes_are_never_the_same_face():
    """两形必须分家（本单判据的正面写法）：同一把尺在两份账上交回两个不同的东西。

    摘瞎窗 ⇒ ``None``，量过且干净 ⇒ 0；两者在这里永远不相等。不许并脸、不许用包含式把它们拼成一格。
    """
    blind = ruler._cross_stream_repeats(BLIND)
    clean = ruler._cross_stream_repeats(WITNESSED_NO_OVERLAP)
    assert blind is None and clean == 0, (blind, clean)
    assert blind != clean, "未量与零枚重合是两句不同的话"


def test_a4_a_cross_stream_resend_is_still_counted():
    """修完不许把真病一起摘聋：后一条流重发前一条流的正文 ⇒ 照日一枚（本单只改摘瞎形）。"""
    assert ruler._cross_stream_repeats(RESEND) == 1
    assert ruler._cross_stream_repeats(RESEND) is not None


def test_a5_same_leg_identical_closing_frame_is_still_not_a_repeat():
    """总控裁定不许被本单顺手推翻：同一条流内末片帧与收尾帧同文 ⇒ 仍读 0（不是出现两遍）。"""
    assert ruler._cross_stream_repeats(SAME_LEG) == 0


def test_a6_the_ruler_neither_convicts_nor_whitewashes_an_unmeasured_cell():
    """``None`` 在尺子里与 0 同权：不追加定罪， 也不洗白；而真重发照旧把它判红。

    本单改的是**纸面上的可分辨度**，不是判定的取值：``_frame_verdict`` 把 ``None`` 与 0 都读作不再定罪
    （缺省 ``REPEAT_DELIVERY_UNMEASURED``），所以在册读数一枚不漂。
    """
    assert ruler._frame_verdict(_green_readings()) is True
    assert ruler._frame_verdict(_green_readings(**{CELL: None})) is True
    assert ruler._frame_verdict(_green_readings(**{CELL: 0})) is True
    assert ruler._frame_verdict(_green_readings(**{CELL: 1})) is False


def test_a7_the_absent_or_empty_frames_column_keeps_its_recorded_zero():
    """🔴 本单不越界：入参不是帧表 / 枚数为零仍照在册现状回 0（那一形不在本单写域）。

    它钉在 ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``；要把这一形也改成
    未量，必须总控同笔改口那钉与复算件，口径分歧已写进 ``docs/testing/r507-blind-instrument-returns-none.md``。
    """
    assert ruler._cross_stream_repeats([]) == 0
    assert ruler._cross_stream_repeats(None) == 0
    assert ruler.REPEAT_DELIVERY_UNMEASURED == 0


def test_a8_the_docstring_promise_and_the_code_now_agree():
    """纸与尺对齐（本单的真正病因）：docstring 承论的「派生不出=未量」必须真的写在落码里。

    两把反证刀都落在这里：把新分支改回旧形（摘瞎回 0）或者把干净形改成 ``None``，本件必红。
    """
    doc = ruler._cross_stream_repeats.__doc__ or ""
    assert "回 ``None``" in doc, "docstring 不再承论摘瞎形回 None"
    source = (REPO_ROOT / "scripts" / "eval_transport_ask_v2.py").read_text(encoding="utf-8")
    body = source.split("def _cross_stream_repeats(")[1].split("\ndef ")[0]
    assert "return None" in body, "摘瞎形的 None 分支被摸走了"