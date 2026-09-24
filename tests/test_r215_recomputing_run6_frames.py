# -*- coding: utf-8 -*-
"""R215 判据①：原始账不许漂 —— 拿 run6 那 105 行只读原件复算一遍，逐格逐位相同。

取证对象是**已并树的只读原件**（``docs/testing/sidecar-run6-frames.jsonl``，2026-09-24 由
总控抢救并树，本机崩过一次之后只剩仓库里这一份）：一题一行，13 格读数。本件一个字都不写它，
只把它当证据读；它的 sha256 钉在本文件里，谁动了原件，本件当场红（动了证据就别谈复算）。

复算的构造（每条流的帧序列怎么从行上复原）：

  * run6 是 R203 之前那一轮，生成腿还没接上真流式，所以**每条流至多一枚帧**：
    ``streams`` 1 或 2，``per_stream[i]["frames"]`` 恒为 1（``text_frames`` 0 的那行除外）；
  * ``streams == 1``：那一枚帧的正文就是交付的终答（``last_frame_sha == answer_sha`` 且
    ``missing_chars == extra_chars == 0`` 三格同时成立 ⇒ 末帧与终答同一份字）；
  * ``streams == 2``：第一条流是挂起轮那一帧（正文取 sidecar 的 ``pre_answer``，当天真到的
    那枚），第二条流是批准之后交付的终答；
  * ``text_frames == 0``：那条流一枚 text 都没到，终答是 error 事件里的字。

这层构造**不是本件的断言**，断言是「按它喂出来的 13 格读数与原件逐位相同」：105 行 × 13 格
= 1365 格，其中 210 格是 sha 指纹、其余是整数与布尔。复原错了就比不上，比得上就证明
``_count_text_frame`` / ``_fold_frames`` / ``_frame_readings`` / ``_frame_verdict`` 这四件
在 R215 之后仍然吐出当年的数 —— 包括 ``prefix_breaks``、``first_break_at``（在 ``per_stream``
里）、``missing_chars``、``extra_chars``、``answer_sha``。

另加两格（``corrective_replacements`` / ``uncorrected_breaks``）在老数据上的读法：老行里
没有线上证词（豁免判据要吃 ``step`` 事件，而帧账那一行根本不存 ``step``），所以 105 行一律
读 0 枚豁免、``uncorrected_breaks == prefix_breaks``。**这是本件最要紧的一格**：换读法之后
「回头重算老结果」这条路绝不能把当年的红字洗白。
"""

import hashlib
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAMES_ORIGINAL = REPO_ROOT / "docs" / "testing" / "sidecar-run6-frames.jsonl"
ANSWERS_ORIGINAL = REPO_ROOT / "docs" / "testing" / "answers-run6.jsonl"
SIDECAR_ORIGINAL = REPO_ROOT / "docs" / "testing" / "sidecar-run6.jsonl"

_SPEC = importlib.util.spec_from_file_location(
    "r215_frame_ruler", REPO_ROOT / "scripts" / "eval_transport_ask_v2.py")
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

#: 原件的指纹（09-24 在本树实取）。原件被改过 ⇒ 复算无从谈起，先红给你看。
FRAMES_ORIGINAL_SHA256 = "0991bff1dc6c7b32594248fe5c0d55a0d298e0ec08a92fd5548a8838623b27cd"
RUN6_ROWS = 105

#: 判据① 点名的那几格原始账（``first_break_at`` 只活在 ``per_stream`` 那一格里）。
RAW_CELLS = ("text_frames", "prefix_breaks", "missing_chars", "extra_chars", "answer_sha",
             "last_frame_covers_answer", "last_frame_chars", "last_frame_sha", "answer_chars",
             "streams", "max_stream_frames", "per_stream")
#: R215 新增的两格。
NEW_CELLS = ("corrective_replacements", "uncorrected_breaks")


def _jsonl(path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _run6():
    """读三份只读原件，按 id 配好（不写盘、不复制进夹具）。"""
    rows = _jsonl(FRAMES_ORIGINAL)
    answers = {str(row["id"]): str(row["answer"]) for row in _jsonl(ANSWERS_ORIGINAL)}
    sidecar = {}
    for row in _jsonl(SIDECAR_ORIGINAL):
        sidecar.setdefault(str(row["id"]), row)
    return rows, answers, sidecar


def _streams_of(row, sidecar_row, answer):
    """按上面那段构造，复原这一题每条流的帧正文列表。

    构造的每一条前提都当场钉住：前提没了（比如将来有人拿 run7 换掉这份文件）就直接失败，
    不许悄悄退回「大概一样」。
    """
    per_stream = row["per_stream"]
    assert len(per_stream) == row["streams"], row["id"]
    assert all(entry["frames"] <= 1 for entry in per_stream), (
        "run6 的构造前提破了：出现了单流多帧，%s" % row["id"])
    if row["streams"] == 2:
        parked = str(sidecar_row["pre_answer"])
        return [[parked], [answer]]
    if row["text_frames"] == 1:
        return [[answer]]
    assert row["text_frames"] == 0, row
    return [[]]


def _replay(row, answers, sidecar):
    """把复原出来的帧序列喂**真的**收端函数，取回这一题的读数。"""
    answer = answers[row["id"]]
    ledger = ruler._new_frame_ledger()
    for contents in _streams_of(row, sidecar.get(row["id"], {}), answer):
        out = ruler._blank_observation(row["session_id"])
        for content in contents:
            ruler._count_text_frame(out, content)
            if content:
                out["answer"] = content
        ruler._fold_frames(ledger, out)
    readings = ruler._frame_readings(ledger, answer)
    readings["criterion_two_holds"] = ruler._frame_verdict(readings)
    return readings


def test_the_run6_frame_original_is_the_frozen_readonly_evidence():
    """证据本体先钉住：105 行、键集是当年那一份、文件一个字节都没被动过。"""
    assert hashlib.sha256(FRAMES_ORIGINAL.read_bytes()).hexdigest() == FRAMES_ORIGINAL_SHA256
    rows = _jsonl(FRAMES_ORIGINAL)
    assert len(rows) == RUN6_ROWS
    join = {"id", "kind", "attempt", "sentinel", "session_id", "ts"}
    assert all(set(row) == join | set(RAW_CELLS) | {"criterion_two_holds"} for row in rows)
    # 判据① 点名的六格一枚都不许从原件里消失（新量具也不许把它们换掉）。
    for cell in ("text_frames", "prefix_breaks", "missing_chars", "extra_chars", "answer_sha"):
        assert all(cell in row for row in rows), cell
    assert all("first_break_at" in entry for row in rows for entry in row["per_stream"])


def test_replaying_run6_through_the_r215_ruler_reproduces_every_cell():
    """判据① 的主钉：105 行 × 13 格，逐格逐位等于原件（含两枚 sha 指纹列）。"""
    rows, answers, sidecar = _run6()
    diffs = []
    for row in rows:
        recomputed = _replay(row, answers, sidecar)
        for cell in list(RAW_CELLS) + ["criterion_two_holds"]:
            if recomputed[cell] != row[cell]:
                diffs.append((row["id"], cell, row[cell], recomputed[cell]))
    assert diffs == [], "原始账漂了：%s" % diffs[:5]


def test_the_two_new_cells_never_exempt_old_data_that_carries_no_wire_testimony():
    """老帧账里没有 step 事件 ⇒ 一枚都不许豁免，``uncorrected_breaks`` 逐题等于原始账。"""
    rows, answers, sidecar = _run6()
    checked = 0
    for row in rows:
        recomputed = _replay(row, answers, sidecar)
        assert recomputed["corrective_replacements"] == 0, row["id"]
        assert recomputed["uncorrected_breaks"] == row["prefix_breaks"], row["id"]
        # 恒等式：豁免只能把坏形分家，不能凭空吞掉一枚。
        assert (recomputed["prefix_breaks"]
                == recomputed["corrective_replacements"]
                + recomputed["uncorrected_breaks"]), row["id"]
        checked += 1
    assert checked == RUN6_ROWS
    assert sum(row["prefix_breaks"] for row in rows) == 0  # run6 当年就是零坏形


def test_the_verdict_of_every_run6_row_stays_false_under_the_new_reading():
    """换读法不许把当年读绿的题翻绿、也不许把当年读红的翻没：105 行逐题仍是 False。"""
    rows, answers, sidecar = _run6()
    greens = [row["id"] for row in rows
              if ruler._frame_verdict(_replay(row, answers, sidecar))]
    assert greens == [], "run6 是 R203 之前那一轮，一题只有一枚整段帧，判据② 不可能成立"