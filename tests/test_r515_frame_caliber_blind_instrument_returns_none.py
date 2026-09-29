# -*- coding: utf-8 -*-
"""R515 假零钉：量具同口径分身（``scripts/eval_frame_caliber_readout.py``）被摘瞎那一形必须回 ``None``。

病（本单唯一的对象是**读数件**，不是产品、不是帧账那一行、不是判定取值）：R507 把
``scripts/eval_transport_ask_v2.py::_cross_stream_repeats`` 治成「帧在而一枚逐帧指纹都拿不到 ⇒ 回
``None``（未量），不报 0」（``docs/testing/r507-blind-instrument-returns-none.md``），但它的同口径分身
留在本件没治 —— ``_repeats_of_records:61`` 与 ``derived_repeats:82``：:70-74 对 ``chars<=0`` 与 ``sha``
为空两形各自 ``continue``，于是「``frames`` 列在、枚枚有字而无一枚指纹」这份账照样摇回一张全零表，
纸面读成「量得出且 0 枚重合」＝把「没量过」当成「量过且干净」（事故 #73 那一族，P-18）。
``derived_repeats`` 原来那道 ``any(row.get("frames"))`` 只挡得住 ``frames`` 整列缺席或枚枚空表。

今天两形分开，口径以 R507 **并树后**那一份为准，本件不自创第二套：
  * 帧在而一枚逐帧指纹都没参与判定 ⇒ ``None``（未量）；
  * 拿到了指纹且确实没有跨流重合 ⇒ 才回 0。
🔴 入参不是帧表／枚数为零（空读那一形）照在册现状回 0，与 ``_cross_stream_repeats:717-719`` 同脸 ——
那一形钉在 ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``，不在本单写域。
🔴 派生得出与派生不出都不许拿去改写当年的 ``criterion_two_holds``（不重判，口径见
``docs/testing/r471-verdict-caliber-2026-09-29.md``）：本件逐枚钉住「在册四份真账纸面读数一枚不漂」。

全程离线：合成帧直接喂函数本体，importlib 单独加载；真账只读不写。不打模型、不起服务、不动容器。
"""

import copy
import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: 本单的靶件（R443 落仓的口径读出）。
readout = _load("r515_frame_caliber_readout", "scripts/eval_frame_caliber_readout.py")
#: 口径唯一真源：R507 并树后的那把尺（本件逐形与它对判，不许自创第二套）。
ruler = _load("r515_transport_ruler", "scripts/eval_transport_ask_v2.py")

RUN9_FRAMES = REPO_ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
OLD_RUN9_IDS = ["insight-07", "chart-04", "tool-04"]      # 改前改后同一枚（不重判）
OLD_RUN9_HOLDS = (91, 105)                                 # criterion_two_holds=True 枚数/总数
OLD_NON_REPORT_HOLDS = (80, 93)

SHA_A, SHA_B, SHA_C = "a" * 12, "b" * 12, "c" * 12

#: 🔴 量具被摘瞎那一形：帧在、正文也在，逐帧一枚 ``sha`` 都没有（改前在这里交回 0）。
BLIND = [{"stream": 0, "at": 1, "chars": 20},
         {"stream": 0, "at": 2, "chars": 40},
         {"stream": 1, "at": 3, "chars": 40}]
#: ``sha`` 键在而是空串/``None``：与整列缺席同一张脸。
BLANK_SHA = [{"stream": 0, "chars": 20, "sha": ""}, {"stream": 1, "chars": 20, "sha": None}]
#: 拿到了指纹且确实没重合（两条流交的是不同的字）：这一形才许读 0。
WITNESSED_NO_OVERLAP = [{"stream": 0, "chars": 20, "sha": SHA_A},
                        {"stream": 0, "chars": 40, "sha": SHA_B},
                        {"stream": 1, "chars": 33, "sha": SHA_C}]
#: 病形：后一条流把前一条流已上屏的那份字又发一遍（R464 的批准腿病）。
RESEND = [{"stream": 0, "chars": 20, "sha": SHA_A},
          {"stream": 0, "chars": 40, "sha": SHA_B},
          {"stream": 1, "chars": 40, "sha": SHA_B}]
#: 总控裁定的那一形：同一条流内末片帧与收尾帧同文，不算「出现两遍」。
SAME_LEG = [{"stream": 0, "chars": 20, "sha": SHA_A}, {"stream": 0, "chars": 20, "sha": SHA_A}]


def _row(identifier, frames, *, with_frames=True):
    row = {"id": identifier, "attempt": 1, "kind": "问答",
           "text_frames": 3, "max_stream_frames": 2, "prefix_breaks": 0,
           "uncorrected_breaks": 0, "missing_chars": 0, "extra_chars": 0,
           "criterion_two_holds": True, "events": [{"event": "sources"}]}
    if with_frames:
        row["frames"] = frames
    return row


def _write_ledger(tmp_path, rows, name="r515-frames.jsonl"):
    path = tmp_path / name
    with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _repeat_lines(captured):
    """只取纸面上那一格的话（其余行也带「枚数=0」，混在一起就读不出两形了）。"""
    return [line for line in captured.out.splitlines()
            if line.startswith("- cross_stream_repeat_frames")]


# ==================== 行内那一只手：摘瞎形 vs 干净形 ====================


def test_a1_the_blind_row_is_unmeasured_not_a_clean_zero():
    """🔴 本单的牙（行内层）：帧在而一枚逐帧指纹都拿不到 ⇒ ``None``，不再是 0。

    改前 ``if not sha: continue`` 跳完逐枚直接 ``return repeats``（此时恒为 0），摘瞎那一行于是读成
    「量过了且没重合」；刀一把 sha 全清就必须翻成 ``None``，翻回 0 本钉当场红。
    """
    assert readout._repeats_of_records(BLIND) is None


def test_a2_blank_sha_is_the_same_blind_face():
    """``sha`` 键在而是空串/``None`` ⇒ 与整列缺席同一张脸（都算一枚指纹都没参与）。"""
    assert readout._repeats_of_records(BLANK_SHA) is None


def test_a3_a_witnessed_row_with_no_overlap_is_a_real_zero():
    """反向的同一条纪律：拿到了指纹且确实没重合 ⇒ 才允许是 0，不许倒打一耙回 ``None``。"""
    reading = readout._repeats_of_records(WITNESSED_NO_OVERLAP)
    assert reading == 0, reading
    assert reading is not None, "量过了且没重合不许伪装成未量"


def test_a4_two_shapes_never_share_one_face():
    """两形必须分家（判据的正面写法）：同一只手在两份账上交回两个不同的东西。"""
    blind = readout._repeats_of_records(BLIND)
    clean = readout._repeats_of_records(WITNESSED_NO_OVERLAP)
    assert blind is None and clean == 0, (blind, clean)
    assert blind != clean, "未量与零枚重合是两句不同的话"


def test_a5_a_cross_stream_resend_is_still_counted():
    """修完不许把真病一起摘聋：后一条流重发前一条流的正文 ⇒ 照旧一枚。"""
    assert readout._repeats_of_records(RESEND) == 1
    assert readout._repeats_of_records(RESEND) is not None


def test_a6_same_leg_identical_closing_frame_is_still_not_a_repeat():
    """总控裁定不许被本单顺手推翻：同一条流内末片帧与收尾帧同文 ⇒ 仍读 0。"""
    assert readout._repeats_of_records(SAME_LEG) == 0


def test_a7_the_absent_or_empty_frames_column_keeps_its_recorded_zero():
    """🔴 本单不越界：枚数为零／入参不是帧表（空读那一形）仍照在册现状回 0。

    那一形钉在 ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``，
    改它要总控同笔改口（残余分歧见 ``docs/testing/r507-blind-instrument-returns-none.md`` §6 第 3 条）。
    """
    assert readout._repeats_of_records([]) == 0
    assert readout._repeats_of_records(None) == 0


@pytest.mark.parametrize("shape", [BLIND, BLANK_SHA, WITNESSED_NO_OVERLAP, RESEND, SAME_LEG,
                                   [], None],
                         ids=["blind", "blank_sha", "witnessed_clean", "resend", "same_leg",
                              "empty_list", "none_input"])
def test_a8_the_twin_and_the_ruler_return_the_same_face_per_shape(shape):
    """同口径＝逐形对判同脸（本件不许自创第二套）：与 R507 并树后的尺子一枚一格比。"""
    assert readout._repeats_of_records(shape) == ruler._cross_stream_repeats(shape), shape
    assert (readout._repeats_of_records(shape) is None) == (
        ruler._cross_stream_repeats(shape) is None), shape


# ==================== 整份账那一只手：派生得出 vs 派生不出 ====================


@pytest.mark.parametrize("identifier,rows,expected", [
    # 在册两形（R515 一个字未改）：整列缺席／枚枚空表 ⇒ 派生不出
    ("S1_frames_column_absent", [_row("q1", None, with_frames=False)], None),
    ("S2_every_frames_empty", [_row("q1", []), _row("q2", [])], None),
    # 🔴 病灶那一形（改前交回一张全零表）：帧在、枚枚有字、无一枚指纹
    ("S3_blind_with_text", [_row("q1", BLIND), _row("q2", BLIND)], None),
    ("S3b_blind_mixed_with_empty", [_row("q1", BLIND), _row("q2", [])], None),
    ("S8_blank_sha", [_row("q1", BLANK_SHA)], None),
    ("S9_empty_ledger", [], None),
    # 量得出：有指纹参与，干净交 0 枚、病形交枚数（这两形不许被本单倒向 None）
    ("S4_same_leg_green", [_row("q1", SAME_LEG)], []),
    ("S5_witnessed_clean", [_row("q1", WITNESSED_NO_OVERLAP)], []),
    ("S6_cross_stream_resend", [_row("q1", RESEND)], [("q1", 1)]),
], ids=lambda value: value if isinstance(value, str) else "")
def test_b1_account_shapes_split_into_two_faces(identifier, rows, expected):
    """探针落钉：逐形点名这份账交回什么（``None``＝派生不出；``[...]``＝量得出）。"""
    assert readout.derived_repeats(rows) == expected, identifier


def test_b2_the_mixed_ledger_names_its_unmeasured_rows():
    """混合账不许读成全干净：摘瞎那一行没参与判定，``unmeasured_rows`` 必须把它点名出来。"""
    rows = [_row("q1", BLIND), _row("q2", WITNESSED_NO_OVERLAP)]

    assert readout.derived_repeats(rows) == []          # 整份账有指纹参与 ⇒ 量得出
    assert readout.unmeasured_rows(rows) == ["q1"], readout.unmeasured_rows(rows)
    assert readout.account_fingerprints(rows) == 3      # 只数现成读数，一枚不另数


def test_b3_account_fingerprint_count_is_the_only_gate():
    """闸门只看「有没有一枚现成的逐帧指纹」：摘瞎账枚数为 0，真账 run9 一枚不少。"""
    assert readout.account_fingerprints([_row("q1", BLIND), _row("q2", [])]) == 0
    run9 = readout.load_rows(str(RUN9_FRAMES))
    assert readout.account_fingerprints(run9) == 2533, readout.account_fingerprints(run9)
    assert readout.unmeasured_rows(run9) == []


# ==================== 纸面层：读的人看见的那一行 ====================


def test_c1_the_blind_ledger_prints_unmeasured_not_a_zero(tmp_path, capsys):
    """刀一把纸面版：把 run9 的逐帧指纹全清，纸面必须读「派生不出」，不许读「枚数=0」。"""
    rows = copy.deepcopy(readout.load_rows(str(RUN9_FRAMES)))
    for row in rows:
        for record in row.get("frames") or []:
            record.pop("sha", None)
    ledger = _write_ledger(tmp_path, rows, "r515-blind-run9.jsonl")

    assert readout.main(["--frames", str(ledger)]) == 0
    lines = _repeat_lines(capsys.readouterr())
    assert lines, "纸面上那一格一枚都没有"
    for line in lines:
        assert "派生不出" in line, line
        assert "枚数=0" not in line, "摘瞎账又冒充量过了"


def test_c2_a_witnessed_clean_ledger_still_prints_a_real_zero(tmp_path, capsys):
    """反向纸面：有指纹参与且确实没重合 ⇒ 纸面照旧读 0 枚，不许伪装成派生不出。"""
    ledger = _write_ledger(tmp_path, [_row("q1", WITNESSED_NO_OVERLAP), _row("q2", SAME_LEG)])

    assert readout.main(["--frames", str(ledger)]) == 0
    lines = _repeat_lines(capsys.readouterr())
    assert len(lines) == 2, lines                       # 全量／剔报告档各一行
    for line in lines:
        assert "枚数=0" in line and "派生不出" not in line, line


def test_c3_the_mixed_ledger_says_which_rows_never_participated(tmp_path, capsys):
    """混合账的纸面：那一格读 0 枚的同时，必须另起一行点名没参与判定的行。"""
    ledger = _write_ledger(tmp_path, [_row("q1", BLIND), _row("q2", WITNESSED_NO_OVERLAP)])

    assert readout.main(["--frames", str(ledger)]) == 0
    capsys.readouterr()
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    unmeasured = [line for line in out.splitlines() if "行内未量" in line]
    assert len(unmeasured) == 2, unmeasured              # 两套范围各一行
    assert all("q1" in line for line in unmeasured), unmeasured


def test_c4_the_registered_ledgers_paper_is_byte_stable(tmp_path, capsys):
    """🔴 在册真账一枚读数不漂：run9 派生 3 枚、run6/run7/run8p2 派生不出，改前改后同一张脸。"""
    for name, expected in (("sidecar-run6-frames.jsonl", None),
                           ("sidecar-run7-frames.jsonl", None),
                           ("sidecar-run8p2-frames.jsonl", None)):
        rows = readout.load_rows(str(REPO_ROOT / "docs" / "testing" / name))
        assert readout.derived_repeats(rows) is expected, name
        assert readout.unmeasured_rows(rows) == [], name  # 老账是整列缺席/空表，不是混合形

    rows = readout.load_rows(str(RUN9_FRAMES))
    derived = readout.derived_repeats(rows)
    assert [identifier for identifier, _ in derived] == OLD_RUN9_IDS, derived
    assert [count for _, count in derived] == [1, 1, 1], derived


def test_c5_the_derivation_never_rewrites_the_old_verdict(tmp_path, capsys):
    """🔴 不重判那条边界一枚不漂：派生过程不写行、``criterion_two_holds`` 只从账上读。"""
    rows = copy.deepcopy(readout.load_rows(str(RUN9_FRAMES)))
    snapshot = copy.deepcopy(rows)

    readout.derived_repeats(rows)
    readout.unmeasured_rows(rows)
    assert rows == snapshot, "派生那两只手动了账上的行"

    ledger = _write_ledger(tmp_path, rows, "r515-run9.jsonl")
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    holds = [line for line in out.splitlines() if line.startswith("- criterion_two_holds=True")]
    assert len(holds) == 2, holds
    assert "枚数=%d/%d" % OLD_RUN9_HOLDS in holds[0], holds[0]
    assert "枚数=%d/%d" % OLD_NON_REPORT_HOLDS in holds[1], holds[1]
    assert readout.RAW_CELLS and "cross_stream_repeat_frames" not in readout.RAW_CELLS


# ==================== 纸与尺对齐（刀二的落点）====================


def test_d1_the_docstring_promise_and_the_code_now_agree():
    """本单真正的病因：承论写了「没有指纹不参与」，落码就得真交回 ``None``。

    刀二（把 ``None`` 强改成 0）在这里与 ``test_a1``/``test_c1`` 同时咬人：摘掉那两枚 ``return None``
    分支，本件当场红。
    """
    source = (REPO_ROOT / "scripts" / "eval_frame_caliber_readout.py").read_text(encoding="utf-8")

    blind_body = source.split("def _repeats_of_records(")[1].split("\n\ndef ")[0]
    derived_body = source.split("def derived_repeats(")[1].split("\n\ndef ")[0]
    assert "return None" in blind_body, "行内摘瞎形的 None 分支被摸走了"
    assert "return None" in derived_body, "整份账无指纹那一形的 None 分支被摸走了"
    for marker in ("R507", "没量过"):
        assert marker in blind_body, marker              # 口径出处写在尺子上，不只写在纸上
    assert "int | None" in blind_body, "行内那一只手的签名还写着恒为整数"
    assert "criterion_two_holds" in derived_body, "不重判那条边界仍在派生件的承论里"
