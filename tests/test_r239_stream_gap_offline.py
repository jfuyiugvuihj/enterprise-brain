# -*- coding: utf-8 -*-
"""R239 判据② 离线判器的钉子（2026-09-25，执行层）。

钉的对象只有一件事：**判器把「② 的原文两格」与「帧账里那枚 criterion_two_holds」分开读**
这件事，在 run7 的真读数上、在合成形状上、在改一把尺就变红的反证上，都成立。

取证件是**已并树的只读原件** ``docs/testing/sidecar-run7-frames.jsonl``（105 行，21 键，
sha256 全值钉在下面）：本文件一个字都不写它，谁动了证据谁当场红。
"""

import builtins
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAMES_RUN7 = REPO_ROOT / "docs" / "testing" / "sidecar-run7-frames.jsonl"
#: 09-25 在本树实取（与 ``docs/testing/r239-stream-gap-2026-09-25.md`` 同一枚）。
FRAMES_RUN7_SHA256 = ("fda8b7bf81569d8dc7261acf2f192079"
                      "c271d144ee4c8f06fbdb50c80ef85828")

_SPEC = importlib.util.spec_from_file_location(
    "r239_stream_gap_offline_audit", REPO_ROOT / "scripts" / "r239_stream_gap_offline_audit.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)

#: run7 里判器② 读红的九枚（``text_frames == 1``，逐字那一半全过）。
SINGLE_FRAME_IDS = {"doc-07", "chat-03", "chat-06", "chat-09", "chat-10",
                    "metric-17", "data-09", "approval-06", "scope-01"}
#: 账读 False 而② 原文读 True 的三枚分歧。
DISAGREEMENT_IDS = {"chart-01", "chart-03", "tool-04"}


def sha256_of(path):
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="module")
def rows():
    return audit.read_rows(FRAMES_RUN7)


@pytest.fixture(scope="module")
def judged(rows):
    return {item["id"]: item for item in (audit.judge_row(row) for row in rows)}


#: run8 相 2 才有的形状：R223 / R222 的七格落在同一行上（列名取自
#: ``tests/test_r181_text_frame_ruler.py:54 ARRIVAL_READING_KEYS``，逐字对）。
def run8_row(**over):
    row = {"id": "report-07", "kind": "queued_polled", "attempt": 1, "sentinel": False,
           "session_id": "deadbeef", "ts": "2026-09-26 09:00:00",
           "text_frames": 1, "prefix_breaks": 0, "corrective_replacements": 0,
           "uncorrected_breaks": 0, "missing_chars": 0, "extra_chars": 0,
           "last_frame_covers_answer": True, "last_frame_chars": 120,
           "last_frame_sha": "000000000000", "answer_chars": 120,
           "answer_sha": "000000000000", "streams": 1, "max_stream_frames": 1,
           "per_stream": [{"frames": 1, "breaks": 0, "first_break_at": 0}],
           "criterion_two_holds": False,
           "frames": [{"stream": 0, "at": 1, "arrival_at": 1000.0, "elapsed_ms": 0.0,
                       "chars": 1, "sha": "a", "prefix_break": False},
                      {"stream": 0, "at": 2, "arrival_at": 1000.2, "elapsed_ms": 200.0,
                       "chars": 60, "sha": "b", "prefix_break": False},
                      {"stream": 0, "at": 3, "arrival_at": 1010.5, "elapsed_ms": 10500.0,
                       "chars": 120, "sha": "c", "prefix_break": False}],
           "events": [{"stream": 0, "at": 1, "event": "status", "class": "note",
                       "arrival_at": 1000.4, "elapsed_ms": 400.0}],
           "stream_clock": [{"stream": 0, "request_sent_at": 1000.0,
                             "first_event_at": 1000.4, "elapsed_base": "request_sent_at"}],
           "queue": {"polls": 3, "blips": 0, "relogins": 0, "final": "done",
                     "last_status": "done", "wait_ms": 15230.0, "stall_ms": 300000,
                     "deadline_ms": 900000, "interval_ms": 3000},
           "first_visible_at": 1000.4, "first_visible_event": "status",
           "first_visible_ms": 400.0}
    row.update(over)
    return row


def _mutate(row, **over):
    """在内存里改一枚读数 —— 🔴 从不碰账件本身。"""
    return dict(row, **over)


def _recording_opens(monkeypatch):
    """把 open 换成记录器：判器要是敢用写模式打开东西，这枚钉子当场咬。"""
    seen = []
    real = io.open

    def spy(file, mode="r", *args, **kwargs):
        seen.append(str(mode))
        return real(file, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", spy)
    monkeypatch.setattr(builtins, "open", spy)
    return seen


# ===== 一、run7 真读数：② 原文 vs 帧账那枚 criterion_two_holds =====

def test_the_evidence_file_is_the_one_this_ticket_read(rows):
    assert sha256_of(FRAMES_RUN7) == FRAMES_RUN7_SHA256
    assert len(rows) == 105
    assert all(len(row) == 21 for row in rows)          # run7 的键集：21 枚，R223 七格一枚都没有
    assert all(not audit.ARRIVAL_KEYS_SET & set(row) for row in rows)


def test_run7_literal_two_reads_96_green_and_the_red_is_exactly_the_single_frame_nine(rows):
    judged = [audit.judge_row(row) for row in rows]
    green = [item for item in judged if item["verdict"]]
    assert len(green) == 96
    assert {item["id"] for item in judged if not item["verdict"]} == SINGLE_FRAME_IDS
    assert sum(1 for item in judged if item["event_count_gt_1"]) == 96
    assert sum(1 for item in judged if item["char_by_char_no_loss"]) == 105


def test_run7_ledger_reads_93_green_and_names_three_disagreements(rows):
    judged = [audit.judge_row(row) for row in rows]
    assert sum(1 for item in judged if item["ledger_criterion_two_holds"]) == 93
    assert {item["id"] for item in judged if item["disagreement"]} == DISAGREEMENT_IDS


def test_chart_01_holds_the_literal_two_and_is_red_only_on_the_rulers_third_condition(judged):
    item = judged["chart-01"]
    assert (item["text_frames"], item["max_stream_frames"], item["streams"]) == (2, 1, 2)
    assert item["event_count_gt_1"] is True              # ②-a 原文：2 > 1
    assert item["char_by_char_no_loss"] is True          # ②-b 原文：四枚计数全 0 + covering
    assert item["verdict"] is True                       # ⇒ 判据② 原文这一格读真
    assert item["ledger_criterion_two_holds"] is False   # 账读假
    assert item["extra_red_conditions"] == ["max_stream_frames>1"]
    assert item["event_form"] == "one_frame_per_stream"  # 挂起轮 + 批准轮各一枚整段帧


def test_the_two_break_rows_are_red_on_breaks_not_on_chars(judged):
    for row_id in ("chart-03", "tool-04"):
        item = judged[row_id]
        assert item["char_by_char_no_loss"] is True
        assert item["verdict"] is True
        assert item["extra_red_conditions"] == ["uncorrected_breaks==0"]
        assert item["event_form"] == "incremental_within_one_stream"


def test_reading_the_char_half_as_including_screen_continuity_moves_only_chart_01(rows):
    judged = [audit.judge_row(row, breaks_count_as_loss=True) for row in rows]
    assert sum(1 for item in judged if item["verdict"]) == 94
    assert {item["id"] for item in judged if item["disagreement"]} == {"chart-01"}


def test_the_independent_recompute_matches_every_stored_ledger_value(rows):
    judged = [audit.judge_row(row) for row in rows]
    assert [item["id"] for item in judged if item["ledger_drift"]] == []


def test_the_nine_single_frame_rows_are_recorded_byte_identical_to_the_answer(rows):
    nine = [row for row in rows if int(row["text_frames"]) == 1]
    assert {row["id"] for row in nine} == SINGLE_FRAME_IDS
    for row in nine:
        assert int(row["streams"]) == 1
        assert int(row["max_stream_frames"]) == 1
        assert [item["frames"] for item in row["per_stream"]] == [1]
        assert int(row["prefix_breaks"]) == 0
        assert (int(row["missing_chars"]), int(row["extra_chars"])) == (0, 0)
        assert row["last_frame_covers_answer"] is True
        # 尺子唯一存下的那一枚帧，逐字等于交付的终答：末帧就是整段答案，不是半截。
        assert row["last_frame_sha"] == row["answer_sha"]
        assert int(row["last_frame_chars"]) == int(row["answer_chars"])
    # 同一把尺在同一个窗里对另外 96 题数出 2..113 帧 ⇒ 计数没有被整批折成一帧。
    assert max(int(row["text_frames"]) for row in rows) == 113


def test_run7_cannot_judge_the_small_buffer_clause(rows):
    judged = [audit.judge_row(row) for row in rows]
    assert all(item["arrival_keys_present"] == [] for item in judged)
    assert all(item["schedule_check"]["status"] == "unmeasurable" for item in judged)
    summary = audit.summarize(judged)
    assert summary["rows_with_arrival_keys"] == 0
    assert summary["schedule_measurable_rows"] == 0

# ===== 二、三枚常驻反证（本仓命名法：counter_evidence 走函数名，没有 marker） =====

def test_counter_evidence_a_one_text_frame_turns_the_event_cell_red(rows):
    """反证 a：把某题的 ``text_frames`` 改成 1 ⇒ ②-a 必须红，逐字那一半照旧绿。

    这钉住的是「红在哪一格」：判器不许把单帧读成缺字，也不许让单帧蒙过事件数那一格。
    """
    green = next(row for row in rows if int(row["text_frames"]) > 1
                 and audit.judge_row(row)["verdict"])
    assert audit.judge_row(green)["event_count_gt_1"] is True      # 改之前：绿
    collapsed = audit.judge_row(_mutate(green, text_frames=1, max_stream_frames=1,
                                        streams=1, per_stream=[{"frames": 1}]))
    assert collapsed["event_count_gt_1"] is False
    assert collapsed["char_by_char_no_loss"] is True
    assert collapsed["verdict"] is False
    assert collapsed["event_form"] == "single_frame"
    # 反向的一半：把单帧题凑成 2 帧、但两条流各一枚 —— ②-a 会转绿，形状仍然露馅。
    padded = audit.judge_row(_mutate(green, text_frames=2, max_stream_frames=1, streams=2,
                                     per_stream=[{"frames": 1}, {"frames": 1}]))
    assert padded["event_count_gt_1"] is True and padded["event_form"] == "one_frame_per_stream"
    assert padded["extra_red_conditions"] == ["max_stream_frames>1"]


def test_counter_evidence_b_a_missing_char_reading_turns_the_char_cell_red(rows):
    """反证 b：造一枚缺字读数 ⇒ 逐字那一半必须红（事件数那一半照旧绿）。"""
    green = next(row for row in rows if int(row["text_frames"]) > 1
                 and audit.judge_row(row)["verdict"])
    for over in ({"missing_chars": 3}, {"extra_chars": 2},
                 {"last_frame_covers_answer": False}):
        item = audit.judge_row(_mutate(green, **over))
        assert item["event_count_gt_1"] is True
        assert item["char_by_char_no_loss"] is False, over
        assert item["verdict"] is False, over
    # 坏形单独进不了②-b（默认口径）：它只许被点名成「账比② 多要求的那一枚」。
    breaks_only = audit.judge_row(_mutate(green, uncorrected_breaks=1))
    assert breaks_only["char_by_char_no_loss"] is True
    assert breaks_only["verdict"] is True
    assert breaks_only["extra_red_conditions"] == ["uncorrected_breaks==0"]


def test_counter_evidence_c_the_audit_never_writes_its_input(tmp_path, monkeypatch, capsys):
    """反证 c：判器是只读的 —— 跑完 sha256 自证不变，open 只许以读模式发生。"""
    ledger = tmp_path / "run7-copy-frames.jsonl"
    ledger.write_bytes(FRAMES_RUN7.read_bytes())
    before = sha256_of(ledger)
    assert sha256_of(FRAMES_RUN7) == FRAMES_RUN7_SHA256
    seen = _recording_opens(monkeypatch)
    listing_before = sorted(path.name for path in tmp_path.iterdir())

    assert audit.main(["--frames", str(ledger), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert seen, "探针没接上：这枚反证会退化成空钉"
    assert [mode for mode in seen if not mode.startswith("r")] == []
    assert sha256_of(ledger) == before
    assert sha256_of(FRAMES_RUN7) == FRAMES_RUN7_SHA256
    assert sorted(path.name for path in tmp_path.iterdir()) == listing_before
    assert payload["summary"]["input_unchanged"] is True
    assert payload["summary"]["input_sha256_before"] == before


def test_counter_evidence_d_per_frame_arrivals_make_the_clause_measurable():
    """反证 d：run8 那七格一到，:87 那条「小缓冲发片 / 禁单字碎片」就从「判不动」变成「能判」。

    合成一题带 ``frames[]``（逐帧 chars 与 elapsed_ms）：第一枚帧只带 1 字 ⇒ 必须被点数出来。
    这钉住的是判器不是只会对 run7 喊「没有量具」，它接得住 run8 的量具。
    """
    item = audit.judge_row(run8_row())
    assert len(item["arrival_keys_present"]) == 7
    check = item["schedule_check"]
    assert check["status"] == "measured"
    assert check["frame_count_with_arrival"] == 3
    assert check["single_char_fragments"] == 1
    assert check["min_increment_chars"] == 1
    assert check["max_gap_ms"] == 10300.0
    assert item["verdict"] is False                      # 这一枚 text_frames 仍是 1
    streamed = audit.judge_row(run8_row(text_frames=3, max_stream_frames=3,
                                        criterion_two_holds=True,
                                        per_stream=[{"frames": 3, "breaks": 0,
                                                     "first_break_at": 0}]))
    assert (streamed["event_count_gt_1"], streamed["verdict"],
            streamed["event_form"]) == (True, True, "incremental_within_one_stream")


def test_a_ledger_missing_a_required_key_is_rejected_not_zero_filled(tmp_path):
    ledger = tmp_path / "thin-frames.jsonl"
    thin = _mutate(run8_row())
    thin.pop("text_frames")
    ledger.write_text(json.dumps(thin, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(audit.LedgerSchemaError) as caught:
        audit.read_rows(ledger)
    assert "text_frames" in str(caught.value)
