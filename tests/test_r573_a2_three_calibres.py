"""R573 的钉：A② 三口径对账件 `scripts/r573_caliber_reconciliation.py`。

逐格对应判据（合窗 11 题，全内存/tmp_path，零模型、零容器、零网络）：
  ① 三档各两读的分母/分子/被扣题号逐枚钉死（真窗 12 组的数在凭据纸里，本件钉形状与算术）；
  ② 不重抄在册尺：三把刀分别摘在册件的刀（`r239.event_count_gt_1`／`r239.recomputed_ledger`／
     `r565.BUCKET_PRIORITY`）⇒ 对账件真在调用它们，数就必须跟着动，硬编码的数不会动；
  ③ 不可判 ≠ 绿：逐帧那一列为空的题必须落在「不可判」名单里，且一枚都不许出现在任何分子里；
  ④ 件缺／零字节／截断 ⇒ 一律 REFUSE（rc≠0），不许报「无缺字」，更不许裸 traceback；
  ⑤ 拿单档宣布翻绿 ⇒ rc=3 当场拒。
🔴 摘刀全走内存与 tmp_path 副本：在册件盘上一字节不动，每把刀都成对交「摘前读数／摘刀红／复原复验」。
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import r239_stream_gap_offline_audit as audit  # noqa: E402
import r565_a2_denominator_buckets as buckets  # noqa: E402
import r573_caliber_reconciliation as rec  # noqa: E402

LF = chr(10)
CRLF = chr(13) + chr(10)
PREFAB = buckets.prefab_fingerprints()
NO_ANSWER_SHA = next(sha for sha, entry in PREFAB.items() if entry["family"] == rec.NO_ANSWER_FAMILY)
NO_ANSWER_TEXT = PREFAB[NO_ANSWER_SHA]["text"]
SENTINEL_SHA = next(sha for sha, entry in PREFAB.items()
                    if entry["family"] == "collector_sentinel"
                    and entry["symbol"] == "APPROVAL_FAILED_SENTINEL")
SENTINEL_TEXT = PREFAB[SENTINEL_SHA]["text"]


def frame_records(count, start=1790000000.0, chars=40, step=20, shas=None, stream=0):
    records = []
    for index in range(count):
        records.append({"stream": stream, "at": index + 1,
                        "arrival_at": start + index * 0.5,
                        "elapsed_ms": 100.0 + index * 50.0,
                        "chars": chars + index * step,
                        "sha": (shas[index] if shas else "sha" + str(index)),
                        "prefix_break": False})
    return records


def event_records(records, completed_at):
    events = [{"stream": item["stream"], "at": item["at"], "event": "text",
               "arrival_at": item["arrival_at"], "elapsed_ms": item["elapsed_ms"]}
              for item in records]
    events.append({"stream": 0, "at": len(events) + 1, "event": "request.completed",
                   "arrival_at": completed_at, "elapsed_ms": 900.0})
    return events


def row(rid, kind="ok", text_frames=3, max_stream_frames=None, streams=1, missing=0, extra=0,
        covers=True, uncorrected=0, ledger=True, answer_chars=120, answer_sha="notaprefabshaa",
        records=None, completed_at=None, per_stream=None):
    if records is None:
        records = frame_records(text_frames)
    if max_stream_frames is None:
        max_stream_frames = text_frames
    if per_stream is None:
        per_stream = [{"frames": text_frames, "breaks": 0, "first_break_at": 0}]
    completed = completed_at if completed_at is not None else (
        records[-1]["arrival_at"] + 1.0 if records else 1790000099.0)
    return {"id": rid, "kind": kind, "attempt": 1, "sentinel": False,
            "session_id": "s-" + rid, "ts": "2026-10-03 00:00:00",
            "frames": records, "events": event_records(records, completed),
            "stream_clock": [{"stream": 0, "request_sent_at": 1790000000.0,
                              "first_event_at": 1790000000.5, "elapsed_base": "request_sent_at"}],
            "queue": {}, "first_visible_at": 1790000000.5, "first_visible_event": "text",
            "first_visible_ms": 500.0, "text_frames": text_frames, "prefix_breaks": 0,
            "corrective_replacements": 0, "uncorrected_breaks": uncorrected,
            "missing_chars": missing, "extra_chars": extra, "last_frame_covers_answer": covers,
            "last_frame_chars": (records[-1]["chars"] if records else 0),
            "last_frame_sha": (records[-1]["sha"] if records else ""),
            "answer_chars": answer_chars, "answer_sha": answer_sha, "streams": streams,
            "max_stream_frames": max_stream_frames, "per_stream": per_stream,
            "criterion_two_holds": ledger}


def synth_rows():
    """11 题：把三档裁定各自的靶子都摆进同一扇窗（每一枚都在某一档里被点名一次）。"""
    single = frame_records(1)
    return [
        row("ok-01"),
        row("ok-02", text_frames=5, max_stream_frames=5),
        row("msf-01", text_frames=2, max_stream_frames=1, streams=2, ledger=False,
            records=frame_records(2, shas=["aaa", "bbb"]),
            per_stream=[{"frames": 1, "breaks": 0, "first_break_at": 0},
                        {"frames": 1, "breaks": 0, "first_break_at": 0}]),
        row("brk-01", text_frames=4, max_stream_frames=4, uncorrected=1, ledger=False),
        row("na-01", kind="error_event", text_frames=0, max_stream_frames=0, extra=21,
            covers=False, ledger=False, answer_chars=len(NO_ANSWER_TEXT), answer_sha=NO_ANSWER_SHA,
            records=[], per_stream=[{"frames": 0, "breaks": 0, "first_break_at": 0}]),
        row("na-02", kind="error_event", text_frames=0, max_stream_frames=0, extra=21,
            covers=False, ledger=False, answer_chars=len(NO_ANSWER_TEXT), answer_sha=NO_ANSWER_SHA,
            records=[], per_stream=[{"frames": 0, "breaks": 0, "first_break_at": 0}]),
        row("sent-01", kind="approval_failed", text_frames=2, max_stream_frames=2, missing=5,
            extra=36, covers=False, ledger=False, answer_chars=len(SENTINEL_TEXT),
            answer_sha=SENTINEL_SHA),
        row("short-01", text_frames=2, max_stream_frames=2, answer_chars=10),
        row("single-01", text_frames=1, max_stream_frames=1, ledger=False, records=single,
            completed_at=single[0]["arrival_at"],
            per_stream=[{"frames": 1, "breaks": 0, "first_break_at": 0}]),
        row("blank-01", kind="error_event", text_frames=0, max_stream_frames=0, covers=False,
            ledger=False, records=[], per_stream=[{"frames": 0, "breaks": 0, "first_break_at": 0}]),
        row("blind-01", records=frame_records(2, shas=["", ""])),
    ]


def tool_calls_by_id():
    return {"ok-01": 2, "ok-02": 2, "msf-01": 2, "brk-01": 2, "na-01": 2, "na-02": 2,
            "sent-01": 2, "short-01": 0, "single-01": 2, "blank-01": 2, "blind-01": 2}


def answer_text(rid):
    if rid in ("na-01", "na-02"):
        return NO_ANSWER_TEXT
    if rid == "sent-01":
        return SENTINEL_TEXT
    return "正文" + rid


def write_window(tmp_path, rows, tag="r573win"):
    root = tmp_path / "evalrun"
    root.mkdir(parents=True, exist_ok=True)
    frames = root / (tag + "-sidecar-frames.jsonl")
    sidecar = root / (tag + "-sidecar.jsonl")
    answers = root / (tag + "-answers.jsonl")
    frames.write_text(LF.join(json.dumps(item, ensure_ascii=False) for item in rows) + LF,
                      encoding="utf-8")
    sidecar.write_text(LF.join(json.dumps({"id": item["id"],
                                           "tool_calls": tool_calls_by_id()[item["id"]],
                                           "answer_chars": item["answer_chars"],
                                           "sentinel": bool(item["sentinel"])}) for item in rows) + LF,
                       encoding="utf-8")
    answers.write_text(LF.join(json.dumps({"id": item["id"], "answer": answer_text(item["id"]),
                                           "tool_calls": tool_calls_by_id()[item["id"]],
                                           "answer_sha": item["answer_sha"]}) for item in rows) + LF,
                       encoding="utf-8")
    return root, frames, sidecar, answers


def groups_for(tmp_path, rows=None, expect=11, tag="r573win"):
    root, frames, sidecar, answers = write_window(tmp_path, rows or synth_rows(), tag=tag)
    report = rec.build_report(tag, root, {"frames": frames, "sidecar": sidecar, "answers": answers},
                              expect)
    return {item["label"]: item for item in report["groups"]}, report


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_six_groups_exist_and_conserve_every_row(tmp_path):
    """判据①：三档 × 各两读＝六组数齐；每组分母＋被扣＝全窗题数，红绿并集不漏一题。"""
    groups, report = groups_for(tmp_path)
    assert sorted(groups) == sorted(rec.CALIBRE_LABELS), sorted(groups)
    total = len(report["records"])
    assert total == 11
    for label, group in groups.items():
        assert group["total_rows"] == total, label
        assert group["denominator"] + group["deducted_count"] == total, label
        assert set(group["red_ids_ledger"]) | set(group["green_ids_ledger"]) == set(
            item["id"] for item in report["records"] if item["id"] not in group["deducted_ids"]), label
        assert not (set(group["red_ids_ledger"]) & set(group["green_ids_ledger"])), label


def test_jia_deducts_by_bucket_in_one_reading_and_by_missing_leg_in_the_other(tmp_path):
    """甲档两读不是同义反复：在册桶剔 B1∪B2，逐帧列空剔 text_frames==0 —— 两批题号不同。"""
    groups, _ = groups_for(tmp_path)
    assert groups["甲-1"]["deducted_ids"] == ["short-01", "single-01"]
    assert groups["甲-2"]["deducted_ids"] == ["blank-01", "na-01", "na-02"]
    assert groups["甲-1"]["denominator"] == 9
    assert groups["甲-2"]["denominator"] == 8


def test_yi_moves_the_prefab_out_and_still_names_every_one_of_it(tmp_path):
    """判据③ 后半边＋判据①：预制句挪出分母必须另立格逐题点名，一枚都不许蒸发。"""
    groups, _ = groups_for(tmp_path)
    assert groups["乙-1"]["deducted_ids"] == ["na-01", "na-02"]
    assert groups["乙-2"]["deducted_ids"] == ["na-01", "na-02", "sent-01"]
    cells = groups["乙-1"]["cells"]
    assert sorted(cells[rec.NO_ANSWER_FAMILY]["ids"]) == ["na-01", "na-02"]
    assert cells[rec.NO_ANSWER_FAMILY]["count"] == 2
    assert cells["collector_sentinel"]["count"] == 1
    disclosed = set(cells[rec.NO_ANSWER_FAMILY]["ids"]) | set(cells["collector_sentinel"]["ids"])
    assert disclosed == {"na-01", "na-02", "sent-01"}, disclosed


def test_bing_numbers_differ_by_exactly_the_max_stream_conjunct(tmp_path):
    """丙档：同一分母两个分子，差的那一枚必须当场点名（探针只走内存影子，盘上一字节不动）。"""
    groups, _ = groups_for(tmp_path)
    assert groups["丙-算"]["denominator"] == 11
    assert groups["丙-算"]["primary_green"] == 4
    assert groups["丙-不算"]["primary_green"] == 5
    assert groups["丙-算"]["flipped_by_msf_ids"] == ["msf-01"]
    assert sorted(set(groups["丙-不算"]["green_ids_without_msf"]) - set(groups["丙-算"]["green_ids_recomputed"])) == ["msf-01"]
    assert set(groups["丙-算"]["green_ids_recomputed"]) <= set(groups["丙-不算"]["green_ids_without_msf"])


def test_unmeasurable_rows_are_listed_and_never_counted_green(tmp_path):
    """判据③：拿不到逐帧到达坐标的行（run6 那一族）必须明写「不可判」＋枚数，且不进任何分子。"""
    groups, report = groups_for(tmp_path)
    empty_frames = sorted(item["id"] for item in report["records"] if not item["measurable"])
    assert empty_frames == ["blank-01", "na-01", "na-02"]
    for label in ("甲-1", "丙-算", "丙-不算"):
        group = groups[label]
        assert group["unmeasurable_ids"] == empty_frames, label
        assert group["unmeasurable_count"] == 3, label
        for green_key in ("green_ids_ledger", "green_ids_recomputed",
                          "green_ids_without_msf", "green_ids_literal"):
            assert not (set(group[green_key]) & set(empty_frames)), (label, green_key)


def test_missing_empty_and_truncated_ledgers_all_refuse(tmp_path, capsys):
    """判据④③：件缺／零字节／末行截断 ⇒ 一律 rc≠0 REFUSE，不许报「无缺字」，不许裸 traceback。"""
    root, frames, sidecar, answers = write_window(tmp_path, synth_rows())
    capsys.readouterr()
    argv = ["--evalrun", str(root), "--tag", "r573win", "--expect-denominator", "11"]
    missing = root.parent / "nowhere"
    assert rec.main(["--evalrun", str(missing), "--tag", "r573win"]) == rec.RC_REFUSE
    assert "读不到" in capsys.readouterr().err
    good = frames.read_text(encoding="utf-8")
    assert good.strip(), "夹具本身没写进去，后面的截断取证就成假证据"
    frames.write_text("", encoding="utf-8")
    assert rec.main(argv) == rec.RC_REFUSE
    assert "零字节" in capsys.readouterr().err
    frames.write_text(good + good[:40], encoding="utf-8")  # 末行截断在半枚 JSON 上
    out = rec.main(argv)
    err = capsys.readouterr().err
    assert out == rec.RC_REFUSE, (out, err)
    assert "读不动" in err, err
    assert "Traceback" not in err, err
    frames.write_text(good, encoding="utf-8")
    assert rec.main(argv) == rec.RC_OK


def test_a_quietly_smaller_window_is_refused_unless_the_denominator_says_so(tmp_path, capsys):
    """判据④ 边界不许静默：11 枚的账拿 105 对账必须拒；显式改分母才放行（不留「关闸」这条路）。"""
    root, frames, sidecar, answers = write_window(tmp_path, synth_rows())
    capsys.readouterr()
    argv = ["--evalrun", str(root), "--tag", "r573win", "--expect-denominator", "105"]
    assert rec.main(argv) == rec.RC_REFUSE
    assert "分母对不上" in capsys.readouterr().err
    assert rec.main(["--evalrun", str(root), "--tag", "r573win",
                     "--expect-denominator", "0"]) == rec.RC_REFUSE
    assert rec.main(["--evalrun", str(root), "--tag", "r573win",
                     "--expect-denominator", "11"]) == rec.RC_OK


def test_declaring_green_with_one_calibre_is_refused(tmp_path, capsys):
    """判据① 后半：本件不选口径 —— 拿任何一档单独宣布翻绿一律 rc=3 当场拒。"""
    capsys.readouterr()
    for label in rec.CALIBRE_LABELS:
        assert rec.main(["--declare-green", label]) == rec.RC_GREEN, label
        assert "不选口径" in capsys.readouterr().err, label


def test_this_file_carries_no_downgrade_marker():
    """自证：本件一枚降级记号都不许有（跳过／放宽／独占／try 吞）。"""
    text = Path(__file__).read_text(encoding="utf-8")
    for marker in ("pytest.mark." + "skip", "pytest.mark." + "xfail", "pytest.mark." + "skipif",
                   "pytest." + "skip(", "pytest." + "xfail(", ".only" + "(", "except " + "Exception"): 
        # 最后一枚按同款拼接写：字面量直接落在本件里会叫这枚自证钉自己红（假红不是牙）
        assert marker not in text, "本件里出现了降级记号：" + marker


IN_BOOK_TOOLS = {
    "r239_stream_gap_offline_audit.py": SCRIPTS / "r239_stream_gap_offline_audit.py",
    "r565_a2_denominator_buckets.py": SCRIPTS / "r565_a2_denominator_buckets.py",
    "eval_frame_caliber_readout.py": SCRIPTS / "eval_frame_caliber_readout.py",
}


def tool_shas():
    return {name: sha256(path) for name, path in IN_BOOK_TOOLS.items()}


def test_counter_evidence_1_blinding_the_in_book_second_a_leg_moves_the_jia_numbers(tmp_path, monkeypatch):
    """刀①（判据④ 第①把）：摘掉在册 ②-a 那一路 ⇒ 甲档的数必须跟着动。

    victim＝在册件 `scripts/r239_stream_gap_offline_audit.py::event_count_gt_1`（内存影子摘刀，
    盘上一字节不动；摘前摘后逐字节 sha256 复验）。
    """
    before = groups_for(tmp_path)[0]
    sha_before = tool_shas()
    assert before["甲-1"]["green_literal"] == 5, before["甲-1"]["green_literal"]  # 甲-1 已把 short-01 扣在门外
    monkeypatch.setattr(audit, "event_count_gt_1", lambda row: False)
    blinded = groups_for(tmp_path)[0]
    assert blinded["甲-1"]["green_literal"] == 0, blinded["甲-1"]["green_literal"]
    assert blinded["甲-2"]["green_literal"] == 0
    assert blinded["丙-算"]["green_ledger"] == before["丙-算"]["green_ledger"], "账上那一格不该被 ②-a 带着走"
    monkeypatch.undo()
    restored = groups_for(tmp_path)[0]
    assert restored["甲-1"]["green_literal"] == before["甲-1"]["green_literal"]
    assert tool_shas() == sha_before, "摘刀过程写了盘：在册件 sha 变了"


def test_counter_evidence_2_blinding_the_in_book_recompute_moves_bing(tmp_path, monkeypatch):
    """刀②：把在册七枚合取的复算函数摘成恒真 ⇒ 丙-算 的分子必须变成整窗，硬编码不会跟。"""
    before = groups_for(tmp_path)[0]
    sha_before = tool_shas()
    assert before["丙-算"]["primary_green"] == 4
    monkeypatch.setattr(audit, "recomputed_ledger", lambda row: True)
    blinded = groups_for(tmp_path)[0]
    assert blinded["丙-算"]["primary_green"] == 11, blinded["丙-算"]["primary_green"]
    assert blinded["丙-算"]["red_ids_recomputed"] == []
    assert blinded["丙-算"]["flipped_by_msf_ids"] == [], "恒真之后没有一枚是被那一枚合取翻动的"
    monkeypatch.undo()
    assert groups_for(tmp_path)[0]["丙-算"]["primary_green"] == 4
    assert tool_shas() == sha_before


def test_counter_evidence_3_blinding_the_bucket_moves_yi_minus_two_but_not_yi_minus_one(tmp_path, monkeypatch):
    """刀③：把在册归账优先级摘空 ⇒ 乙-2（按桶挪）必须整格塌掉，乙-1（按现取指纹挪）不许跟着塌。

    这一把同时证两件事：乙档的数真从在册桶来；而「预制句」那一族的认定不靠桶名、靠现取指纹。
    """
    before = groups_for(tmp_path)[0]
    sha_before = tool_shas()
    assert before["乙-2"]["denominator"] == 8
    assert before["乙-1"]["denominator"] == 9
    monkeypatch.setattr(buckets, "BUCKET_PRIORITY", ())
    blinded = groups_for(tmp_path)[0]
    assert blinded["乙-2"]["denominator"] == 11, blinded["乙-2"]["denominator"]
    assert blinded["乙-2"]["deducted_ids"] == []
    assert (sorted(blinded["乙-2"]["cells"][rec.NO_ANSWER_FAMILY]["ids"])
            == ["na-01", "na-02"]), "桶被摘空也不能让预制句那一格蒸发"
    assert blinded["乙-1"]["deducted_ids"] == ["na-01", "na-02"], "乙-1 不该跟着桶名走（它走现取指纹）"
    monkeypatch.undo()
    restored = groups_for(tmp_path)[0]
    assert restored["乙-2"]["denominator"] == 8 and restored["乙-1"]["denominator"] == 9
    assert tool_shas() == sha_before


def test_counter_evidence_4_flipping_one_ledger_flag_moves_exactly_one_number(tmp_path):
    """刀④（判据④ 第②把）：把某一枚 `criterion_two_holds` 手动翻转 ⇒ 分子/红题清单必须逐枚跟着改。

    victim＝本单点名的在册读数形状（帧账那一格），改的是 tmp_path 里的副本，原账 sha 复验不变。
    """
    root, frames, _sidecar, _answers = write_window(tmp_path, synth_rows())
    sha_before = sha256(frames)
    base = rec.build_report("r573win", root, {"frames": frames}, 11)
    base_groups = {item["label"]: item for item in base["groups"]}
    assert "ok-02" in base_groups["甲-1"]["green_ids_ledger"]
    rows = synth_rows()
    flipped = []
    for item in rows:
        if item["id"] == "ok-02":
            item = dict(item)
            item["criterion_two_holds"] = False
        flipped.append(item)
    copy = root / "mutated-frames.jsonl"
    copy.write_text(LF.join(json.dumps(item, ensure_ascii=False) for item in flipped) + LF,
                    encoding="utf-8")
    mutant = rec.build_report("r573win", root, {"frames": copy}, 11)
    mutant_groups = {item["label"]: item for item in mutant["groups"]}
    assert mutant_groups["甲-1"]["green_ledger"] == base_groups["甲-1"]["green_ledger"] - 1
    assert "ok-02" in mutant_groups["甲-1"]["red_ids_ledger"]
    assert mutant_groups["丙-算"]["green_ledger"] == base_groups["丙-算"]["green_ledger"] - 1
    assert sha256(frames) == sha_before, "取证过程写了原账"


def test_counter_evidence_5_the_instrument_itself_never_writes_its_inputs(tmp_path):
    """刀⑤：整轮跑完，三本账逐枚 sha 与在册三件逐枚 sha 必须全等（量具自己不落笔）。"""
    root, frames, sidecar, answers = write_window(tmp_path, synth_rows())
    ledgers_before = {path.name: sha256(path) for path in (frames, sidecar, answers)}
    tools_before = tool_shas()
    assert rec.build_report("r573win", root, {"frames": frames, "sidecar": sidecar,
                                              "answers": answers}, 11)
    assert {path.name: sha256(path) for path in (frames, sidecar, answers)} == ledgers_before
    assert tool_shas() == tools_before
