# -*- coding: utf-8 -*-
"""R619 乙案 · A② 那把尺的分档读数：多流那一族单列一档，🔴 分档不等于豁免。

病根（一手归因＝R614，凭证 ``docs/perf/r614-uncorrected-break-attribution-2026-10-03.md``）：
验收门 A② 今晚两窗第一次拿到读数，run18 ``uncorrected_breaks=0``、run19 ``=2``
（``report-09``／``tool-02``）。R614 定性＝**量具口径缺陷**，不是产品缺陷：R215 豁免四条件的
第④条（``scripts/eval_transport_ask_v2.py:676``）拿**轮级**交付文本比**流内**末帧，而
``approved_ok`` 那一族有两条流（stream 0＝挂起轮、stream 1＝批准腿），挂起轮里的受控整段替换
结构性不可能等于批准腿交回的终答（两窗 19/19 终答严格长于 ``pre_answer``、0/19 逐字相同）
⇒ 只要挂起轮里换了源，这把尺必然判红。

本单**不修那把尺**（甲案要动落盘键集，会撞 ``tests/test_r181_text_frame_ruler.py:50``／``:449``
两道键集闸，另有单），只做**读数诚实化**：``scripts/eval_frame_caliber_readout.py::caliber_block``
把「断裂住在多流轮里」那一族单独列一档、逐枚点名，不再和单流轮的真断裂混在同一枚数字里
冒充同一口径。三条边界一条比一条硬，本件逐条有牙：

  1. 🔴 **分档≠豁免**：多流那一档的行照旧计入 ``uncorrected_breaks``、照旧让 A② 读 False，
     一克都不许并入 ``granted``（违例即整单退回）——本件用 D 组与 F 组两头钉。
  2. 🔴 **零新列、零改写落盘值**：``streams`` 与断裂所在流序号一律从行内既有三列
     （``streams``／``per_stream``／``frames[].stream``）现场派生；派生不出 ⇒ 记 ``not_applicable``
     并点名是哪一行（同总控 ``b9fd2fc`` 那条规矩），够不到就说够不到，不许当成 0。
  3. 🔴 **恒等式**：档① ＋ 档② ＋ 档③ ＝ 旧口径 ``uncorrected_breaks>0`` 那枚总数
     （题数与断裂枚数两路都对），旧读数不许被新读数顶掉。

真账那一半（run18／run19）落在窗产物 ``%TEMP%\\evalrun\\`` 里，不在仓内、不可常驻，改派工单也
带不走；本件把 R614 §1 那张表的形状照成合成账（形②＝run19 report-09 逐格抄），另拿仓内在册
四本老帧账（run6／run7／run8p2／run9）做常驻复算 —— 那四本里 run7／run9 的断裂同属
``streams>1`` 那一族，形状与今晚那两枚一字不差。

全程离线：合成帧账写进 ``tmp_path``，在册真账只读（读出件写账由 sha 当场抓着）。
不起子进程、不打模型、不动容器、不跑门。
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: 本单的靶件：R443 落仓、R619 只改了它**读数呈现**那一层。
readout = _load("r619_frame_caliber_readout", "scripts/eval_frame_caliber_readout.py")

FRAMES_DIR = REPO_ROOT / "docs" / "testing"
RUN6_FRAMES = FRAMES_DIR / "sidecar-run6-frames.jsonl"
RUN7_FRAMES = FRAMES_DIR / "sidecar-run7-frames.jsonl"
RUN8P2_FRAMES = FRAMES_DIR / "sidecar-run8p2-frames.jsonl"
RUN9_FRAMES = FRAMES_DIR / "sidecar-run9-frames.jsonl"

#: 🔴 键集闸同族规矩（``tests/test_r181_text_frame_ruler.py:50``／``:449``）：分档不许变成新列。
#: 这枚名册改前改后同一份，多一枚少一枚都当场红。
RAW_CELLS_AS_RECORDED = ("text_frames", "max_stream_frames", "prefix_breaks",
                         "uncorrected_breaks", "missing_chars", "extra_chars")


def _frame(stream, at, chars, sha, *, broken=False):
    return {"stream": stream, "at": at, "chars": chars, "sha": sha, "prefix_break": broken}


def _cell(frames, breaks, first_break_at):
    return {"frames": frames, "breaks": breaks, "first_break_at": first_break_at}


def _row(identifier, *, streams=None, per_stream=None, frames=None,
         prefix_breaks=0, corrective=0, uncorrected=0, holds=False):
    """照帧账的行形状搭一行合成账：键名一律用盘上那几枚，一枚都不许多。"""
    cells = per_stream if isinstance(per_stream, list) else []
    return {
        "id": identifier, "attempt": 1, "kind": "approved_ok",
        "text_frames": sum(int(cell.get("frames") or 0) for cell in cells) or len(frames or []),
        "max_stream_frames": max([int(cell.get("frames") or 0) for cell in cells] or [0]),
        "prefix_breaks": prefix_breaks,
        "corrective_replacements": corrective,
        "uncorrected_breaks": uncorrected,
        "missing_chars": 0, "extra_chars": 0,
        "criterion_two_holds": holds,
        "events": [{"stream": 0, "at": 1, "event": "done"}],
        **({"streams": streams} if streams is not None else {}),
        **({"per_stream": per_stream} if per_stream is not None else {}),
        **({"frames": frames} if frames is not None else {}),
    }


# 形①（判据④ 第①形）：单流轮里的真断裂 —— 它不许与多流那一族混成同一枚数。
PLAIN = _row("plain-01", streams=1, per_stream=[_cell(5, 1, 5)],
             frames=[_frame(0, 1, 20, "a" * 12), _frame(0, 2, 40, "b" * 12),
                     _frame(0, 3, 60, "c" * 12), _frame(0, 4, 80, "d" * 12),
                     _frame(0, 5, 90, "e" * 12, broken=True)],
             prefix_breaks=1, uncorrected=1)
# 形②（判据④ 第②形）：多流轮、断裂在 stream 0 ＝ run19 report-09 那一形（4/1 帧、at=4 照抄）。
PARK = _row("park-02", streams=2, per_stream=[_cell(4, 1, 4), _cell(1, 0, 0)],
            frames=[_frame(0, 1, 20, "35b31b5cc689"), _frame(0, 2, 40, "55f997632d5e"),
                    _frame(0, 3, 60, "3f4c5575a86b"),
                    _frame(0, 4, 636, "3d572eff169a", broken=True),
                    _frame(1, 1, 689, "9a52943ae2d8")],
            prefix_breaks=1, uncorrected=1)
# 形③（判据④ 第③形）：多流轮、断裂在 stream 1＝末流（run9 tool-04 那一形），位次须与形②分得开。
TAIL = _row("tail-03", streams=2, per_stream=[_cell(1, 0, 0), _cell(2, 1, 2)],
            frames=[_frame(0, 1, 20, "1" * 12), _frame(1, 1, 40, "2" * 12),
                    _frame(1, 2, 30, "3" * 12, broken=True)],
            prefix_breaks=1, uncorrected=1)
# 形④（判据④ 第④形）：streams／per_stream／frames 三列一枚都不在 ⇒ 只能记 not_applicable。
BLIND = _row("blind-04", prefix_breaks=1, uncorrected=1)
# 形⑤（加严）：流数派生得出、断裂位次派生不出 ⇒ 留在它自己那一档，只在证词里点名够不到。
NOSEAT = _row("noseat-05", streams=2, per_stream=[_cell(3, 0, 0), _cell(2, 0, 0)],
              frames=[_frame(0, 1, 20, "4" * 12), _frame(0, 2, 30, "5" * 12),
                      _frame(0, 3, 40, "6" * 12), _frame(1, 1, 50, "7" * 12),
                      _frame(1, 2, 60, "8" * 12)],
              prefix_breaks=1, uncorrected=1)
# 形⑥（加严）：同轮既豁免过一枚又有未豁免 —— 盘上不分哪一枚，位次只能读作候选。
MIXED = _row("mixed-06", streams=2, per_stream=[_cell(4, 1, 4), _cell(3, 1, 3)],
             frames=[_frame(0, 1, 20, "9" * 12), _frame(0, 2, 40, "0" * 12),
                     _frame(0, 3, 60, "a" * 12), _frame(0, 4, 80, "b" * 12, broken=True),
                     _frame(1, 1, 90, "c" * 12), _frame(1, 2, 100, "d" * 12),
                     _frame(1, 3, 60, "e" * 12, broken=True)],
             prefix_breaks=2, corrective=1, uncorrected=1)
# 形⑦（加严）：streams=0 与 uncorrected>0 互相矛盾 ⇒ 流数不可信，逃进档③，不许并进档①。
ZERO = _row("zero-07", streams=0, per_stream=[], frames=[], prefix_breaks=1, uncorrected=1)

SHAPES = [PLAIN, PARK, TAIL, BLIND, NOSEAT, MIXED, ZERO]
QUIET = _row("quiet-00", streams=1, per_stream=[_cell(3, 0, 0)],
             frames=[_frame(0, 1, 20, "a" * 12), _frame(0, 2, 30, "b" * 12),
                     _frame(0, 3, 40, "c" * 12)], holds=True)


def _write_ledger(tmp_path, rows, name="r619-frames.jsonl"):
    path = tmp_path / name
    with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _entry(buckets, identifier):
    """按题号取那一枚档里的行（结构体保持账上原序，纸面才排序，两头不许互抄）。"""
    hits = [entry for bucket in buckets.values() for entry in bucket if entry["id"] == identifier]
    assert len(hits) == 1, (identifier, hits)
    return hits[0]


def _tier_lines(output: str):
    return [line for line in output.splitlines() if line.lstrip().startswith("- 档")]


def _ids_in(line: str):
    """从「题号=[...]」那一格现读题号（纸面与结构体两头对判，不许只信一头）。"""
    return [token.strip("'") for token in line.split("题号=", 1)[1].strip("[]").split(", ") if token]


def _counts(rows):
    tiers = readout.break_tiers(rows)
    legacy = [row for row in rows if int(row.get("uncorrected_breaks") or 0) > 0]
    return {"row_sum": sum(len(bucket) for bucket in tiers.values()),
            "legacy_rows": len(legacy),
            "break_sum": sum(entry["uncorrected_breaks"]
                              for bucket in tiers.values() for entry in bucket),
            "legacy_breaks": sum(int(row.get("uncorrected_breaks") or 0) for row in legacy)}


# ==================== A：四形各归各档，题号逐枚点得出（判据①②④）====================


def test_a1_the_shapes_land_in_their_own_tiers():
    tiers = readout.break_tiers(SHAPES)
    assert [entry["id"] for entry in tiers["single"]] == ["plain-01"], tiers["single"]
    assert [entry["id"] for entry in tiers["multi"]] == ["park-02", "tail-03", "noseat-05",
                                                         "mixed-06"], tiers["multi"]
    assert [entry["id"] for entry in tiers["unreachable"]] == ["blind-04", "zero-07"], tiers


def test_a2_a_parked_round_names_the_stream_the_break_lives_in():
    entry = readout.break_tiers([PARK])["multi"][0]
    assert entry["streams"] == 2 and entry["streams_from"] == "streams", entry
    assert entry["positions_from"] == "frames[].prefix_break", entry
    assert entry["positions"] == [{"stream": 0, "at": 4, "stream_frames": 4,
                                   "breaks_in_stream": 1}], entry["positions"]
    assert "非末流" in readout._describe_break_entry(entry)


def test_a3_a_last_stream_break_is_a_different_seat():
    entry = readout.break_tiers([TAIL])["multi"][0]
    assert entry["positions"] == [{"stream": 1, "at": 2, "stream_frames": 2,
                                   "breaks_in_stream": 1}], entry["positions"]
    assert "非末流" not in readout._describe_break_entry(entry)


def test_a4_the_no_evidence_shape_is_not_applicable_not_a_zero():
    tiers = readout.break_tiers([BLIND])
    assert tiers["single"] == [] and tiers["multi"] == [], tiers
    entry = tiers["unreachable"][0]
    assert entry["id"] == "blind-04" and "流数派生不出" in entry["reason"], entry
    for column in ("streams", "per_stream", "frames"):
        assert column in entry["streams_from"], (column, entry["streams_from"])


def test_a5_the_seat_can_be_blind_while_the_stream_count_is_not():
    entry = readout.break_tiers([NOSEAT])["multi"][0]
    assert entry["positions"] is None, entry
    assert "断裂位次派生不出" in entry["positions_from"], entry
    assert "派生不出" in readout._describe_break_entry(entry), entry


def test_a6_a_round_with_both_faces_marks_the_seat_as_candidate():
    entry = readout.break_tiers([MIXED])["multi"][0]
    assert entry["candidate_positions"] is True, entry
    assert [position["stream"] for position in entry["positions"]] == [0, 1], entry["positions"]
    assert "候选" in readout._describe_break_entry(entry)


def test_a7_a_contradictory_zero_stream_count_escapes_instead_of_joining_tier_one():
    entry = readout.break_tiers([ZERO])["unreachable"][0]
    assert entry["streams"] == 0 and "矛盾" in entry["reason"], entry


# ==================== B：恒等式（判据⑤ 那枚钉的本体）====================


def test_b1_the_two_tiers_plus_the_escape_hatch_equal_the_old_number():
    reading = _counts(SHAPES)
    assert reading["row_sum"] == reading["legacy_rows"] == 7, reading
    assert reading["break_sum"] == reading["legacy_breaks"] == 7, reading


def test_b2_a_clean_ledger_still_sums_to_zero():
    reading = _counts([QUIET])
    assert reading["row_sum"] == reading["legacy_rows"] == 0, reading
    assert readout.break_tiers([QUIET]) == {"single": [], "multi": [], "unreachable": []}


# ==================== C：纸面（旧读数不许被顶掉，判据①③）====================


def test_c1_the_paper_keeps_the_old_line_and_adds_the_tiers(tmp_path, capsys):
    ledger = _write_ledger(tmp_path, SHAPES)
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    legacy_line = "- uncorrected_breaks >0 枚数=7 题号=%s" % sorted(str(row["id"]) for row in SHAPES)
    assert legacy_line in out.splitlines(), legacy_line
    lines = _tier_lines(out)
    assert len(lines) == 6, lines                                   # 两套范围 × 三档
    joined = "\n".join(lines)
    for identifier in ("plain-01", "park-02", "tail-03", "blind-04", "zero-07"):
        assert identifier in joined, identifier
    identities = [line for line in out.splitlines() if line.lstrip().startswith("- 恒等式")]
    assert len(identities) == 4, identities                          # 两套范围 × 两路（题数/枚数）
    for line in identities:
        assert "⇒ 成立" in line, line
    assert "⇒ 不成立" not in out


def test_c2_the_multi_tier_uses_the_recorded_caliber_and_says_it_is_not_a_pass(tmp_path, capsys):
    assert "结构性够不到" in readout.TIER_MULTI, readout.TIER_MULTI
    for banned in ("可忽略", "豁免", "免责", "不算断裂", "已纠正", "通过"):
        assert banned not in readout.TIER_MULTI, banned
    ledger = _write_ledger(tmp_path, [PARK])
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    multi = [line for line in out.splitlines() if readout.TIER_MULTI in line]
    assert len(multi) == 2, multi                                   # 全量／剔报告档各一行
    assert "park-02" in multi[0]
    assert "不是豁免" in out and "不算通过" in out and "读 False" in out, out


def test_c3_the_paper_names_which_row_could_not_be_derived(tmp_path, capsys):
    ledger = _write_ledger(tmp_path, [BLIND, PARK])
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    unreachable = [line for line in out.splitlines() if readout.TIER_UNREACHABLE in line]
    assert len(unreachable) == 2, unreachable
    assert _ids_in(unreachable[0]) == ["blind-04"], unreachable[0]
    assert "not_applicable" in out and "不许当成 0" in out


def test_c4_an_account_without_the_cell_says_absent_not_zero(tmp_path, capsys):
    rows = [copy.deepcopy(PLAIN)]
    for row in rows:
        row.pop("uncorrected_breaks", None)
    ledger = _write_ledger(tmp_path, rows, "r619-absent.jsonl")
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    assert "这一格在这份账里不存在" in out
    assert readout.CELL_ABSENT_NOTE in out
    assert _tier_lines(out) == [], _tier_lines(out)


# ==================== D：零副作用（判据②③，分档≠豁免）====================


def test_d1_the_derivation_never_writes_a_row_or_adds_a_key():
    snapshot = copy.deepcopy(SHAPES)
    keys_before = [sorted(row.keys()) for row in SHAPES]
    tiers = readout.break_tiers(SHAPES)
    for entry in (item for bucket in tiers.values() for item in bucket):
        readout._describe_break_entry(entry)
    assert SHAPES == snapshot, "派生那一只手动了账上的行"
    assert [sorted(row.keys()) for row in SHAPES] == keys_before


def test_d2_the_raw_cells_gained_no_column():
    assert readout.RAW_CELLS == RAW_CELLS_AS_RECORDED, readout.RAW_CELLS
    assert readout.UNCORRECTED_CELL == "uncorrected_breaks"
    assert readout.STREAM_COLUMNS == ("streams", "per_stream", "frames"), readout.STREAM_COLUMNS


def test_d3_the_readout_stays_read_only_by_construction():
    source = (REPO_ROOT / "scripts" / "eval_frame_caliber_readout.py").read_text(encoding="utf-8")
    for banned in ("json.dump", '"w"', "'w'", ".write_text", "open(", "newline="):
        if banned == "open(":
            assert banned in source, banned                          # 只读那一枚 open 必须还在
            continue
        assert banned not in source, banned


def test_d4_tiering_never_touches_the_exemption_ledger():
    """🔴 分档≠豁免：同一批行在分档前后，corrective_replacements／criterion_two_holds 一枚不动。"""
    before = {str(row["id"]): (row.get("corrective_replacements"), row.get("criterion_two_holds"),
                               row.get("uncorrected_breaks")) for row in SHAPES}
    readout.break_tiers(SHAPES)
    after = {str(row["id"]): (row.get("corrective_replacements"), row.get("criterion_two_holds"),
                              row.get("uncorrected_breaks")) for row in SHAPES}
    assert after == before
    assert before["park-02"] == (0, False, 1), before["park-02"]
    assert before["mixed-06"] == (1, False, 1), before["mixed-06"]


def test_d5_the_paper_still_calls_every_offender_row_red(tmp_path, capsys):
    ledger = _write_ledger(tmp_path, SHAPES)
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    failing = [line for line in out.splitlines() if line.startswith("- criterion_two_holds=False")]
    assert len(failing) == 2, failing
    assert _ids_in(failing[0]) == sorted(str(row["id"]) for row in SHAPES), failing[0]


def test_d6_the_sidecar_ledger_is_not_rewritten_by_the_readout(tmp_path, capsys):
    ledger = _write_ledger(tmp_path, SHAPES, "r619-hash.jsonl")
    digest = hashlib.sha256(ledger.read_bytes()).hexdigest()
    assert readout.main(["--frames", str(ledger)]) == 0
    capsys.readouterr()
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == digest, "读出件写了帧账一个字节"


# ==================== E：在册真账常驻复算（run18/run19 的形状由形②＋run7/run9 代持）====================


def test_e1_run7_falls_back_to_per_stream_seats():
    rows = readout.load_rows(str(RUN7_FRAMES))
    tiers = readout.break_tiers(rows)
    assert sorted(entry["id"] for entry in tiers["multi"]) == ["chart-03", "tool-04"], tiers["multi"]
    assert tiers["single"] == [] and tiers["unreachable"] == []
    chart = _entry(tiers, "chart-03")
    assert chart["positions_from"] == "per_stream[].breaks", chart
    assert [position["stream"] for position in chart["positions"]] == [1], chart
    assert _entry(tiers, "tool-04")["positions"][0]["stream_frames"] == 2, tiers["multi"]
    reading = _counts(rows)
    assert reading["row_sum"] == reading["legacy_rows"] == 2, reading


def test_e2_run9_offenders_sit_on_the_last_stream():
    rows = readout.load_rows(str(RUN9_FRAMES))
    tiers = readout.break_tiers(rows)
    assert sorted(entry["id"] for entry in tiers["multi"]) == ["report-02", "tool-04"], tiers["multi"]
    for entry in tiers["multi"]:
        assert entry["positions"][0]["stream"] == 1, entry
    reading = _counts(rows)
    assert reading["break_sum"] == reading["legacy_breaks"] == 2, reading


def test_e3_run6_and_run8p2_read_their_own_face():
    absent = readout.load_rows(str(RUN6_FRAMES))
    assert readout.break_tiers(absent) == {"single": [], "multi": [], "unreachable": []}
    assert all("uncorrected_breaks" not in row for row in absent)
    quiet = readout.load_rows(str(RUN8P2_FRAMES))
    assert readout.break_tiers(quiet) == {"single": [], "multi": [], "unreachable": []}


def test_e4_in_book_ledgers_never_lose_a_break_to_the_tiers():
    for path in (RUN6_FRAMES, RUN7_FRAMES, RUN8P2_FRAMES, RUN9_FRAMES):
        reading = _counts(readout.load_rows(str(path)))
        assert reading["row_sum"] == reading["legacy_rows"], path
        assert reading["break_sum"] == reading["legacy_breaks"], path


# ==================== F：反证（摘掉分档逻辑必须至少一枚红，判据④）====================


def test_f1_the_wiring_lives_inside_caliber_block():
    """刀①（纸与码对齐）：两处调用必须钉在 ``caliber_block`` 里，从函数体里摸走即红。"""
    source = (REPO_ROOT / "scripts" / "eval_frame_caliber_readout.py").read_text(encoding="utf-8")
    block = source.split("def caliber_block(")[1].split("\n\ndef main(")[0]
    assert "print_break_tiers(rows, offenders)" in block, "分档调用被从 caliber_block 里摸走了"
    assert "print(CELL_ABSENT_NOTE)" in block, "格缺席那一形的不许冒充 0 被摸走了"
    assert "cell == UNCORRECTED_CELL" in block


def test_f2_blinding_the_call_site_blanks_the_paper(tmp_path, capsys, monkeypatch):
    """刀②：把分档呈现摘成哑（内存影子，盘上一字节不动）⇒ 三档行必须整片消失、旧行必须留下。"""
    ledger = _write_ledger(tmp_path, SHAPES, "r619-blind.jsonl")
    assert readout.main(["--frames", str(ledger)]) == 0
    before = _tier_lines(capsys.readouterr().out)
    assert len(before) == 6, before

    monkeypatch.setattr(readout, "print_break_tiers", lambda rows, offenders: None)
    assert readout.main(["--frames", str(ledger)]) == 0
    blinded = capsys.readouterr().out
    assert _tier_lines(blinded) == []
    assert "- uncorrected_breaks >0 枚数=7" in blinded          # 旧读数不是分档撑起来的

    monkeypatch.undo()
    assert readout.main(["--frames", str(ledger)]) == 0
    restored = _tier_lines(capsys.readouterr().out)
    assert restored == before, restored


def test_f3_blinding_the_stream_derivation_moves_the_numbers(tmp_path, capsys, monkeypatch):
    """刀③：把 ``derive_streams`` 摘成恒 1（＝假装行内永远没有多流证据）⇒ 档② 必须空掉、题号必须搬走。"""
    ledger = _write_ledger(tmp_path, SHAPES, "r619-blind2.jsonl")
    assert readout.main(["--frames", str(ledger)]) == 0
    assert len(_tier_lines(capsys.readouterr().out)) == 6

    monkeypatch.setattr(readout, "derive_streams", lambda row: (1, "blinded"))
    tiers = readout.break_tiers(SHAPES)
    assert tiers["multi"] == [] and tiers["unreachable"] == [], tiers
    assert len(tiers["single"]) == 7, tiers["single"]
    assert readout.main(["--frames", str(ledger)]) == 0
    out = capsys.readouterr().out
    unreachable = [line for line in out.splitlines() if readout.TIER_UNREACHABLE in line]
    assert "blind-04" not in "".join(unreachable), unreachable    # 假零那一路正是本钉要拦的


def test_f4_blinding_the_seat_derivation_loses_the_parked_round(tmp_path, monkeypatch):
    """刀④：把 ``derive_break_positions`` 摘成恒指 stream 0 ⇒ 形③ 的末流证词必须丢。"""
    truth = readout.break_tiers([TAIL])["multi"][0]["positions"]
    assert truth[0]["stream"] == 1, truth
    monkeypatch.setattr(readout, "derive_break_positions",
                        lambda row: ([{"stream": 0, "at": 0, "stream_frames": None,
                                       "breaks_in_stream": None}], "blinded"))
    blinded = readout.break_tiers([TAIL])["multi"][0]
    assert blinded["positions"][0]["stream"] == 0, blinded
    assert "非末流" in readout._describe_break_entry(blinded)
    monkeypatch.undo()
    assert readout.break_tiers([TAIL])["multi"][0]["positions"] == truth