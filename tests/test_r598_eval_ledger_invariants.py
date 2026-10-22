"""R598 · 台账不变式：🔴 全件不写死任何一枚数，枚数一律从题源与语料**现读**长出来。

【为什么另开一枚，而不是复用 R401 那枚】
`tests/test_r401_unscorable_rows_are_named_not_dropped.py` 把「丙案 19 枚 / 分母 86」硬编码进
10 处断言（:95 :96 :140 :150 :151 :154 :165 :184 :299 :306）。本单 10-03 用 `scripts/r598_out_of_domain_forensics.py`
实调取证（对照=盘面行全绿，实验=把 `doc-17` 换成甲的影子行）：**6 枚函数先红**（:95 :140 :150 :119 :249 :299），
同一批函数里还有 :151/:154/:165/:184/:306 五处同种硬编码被先红遮蔽（跑不到，但重录时必须一并改）。
那枚件在 R598 写域外（判据⑤只许动 `tests/test_evaluation_report.py` 与
`tests/test_r94_eval_evidence_coverage.py`），执行层不越界改它，也不许为了让它绿而半落半不落。
本件因此把**同一批不变式**按「关系而非数字」重钉一遍：

  ① 查无出处的行数 == 丙案点名枚数 == 丙案词条数（判据⑥的式子，两边都是现读）
  ② 「行数 == 词条数」的口径指纹不破
  ③ correctness 分母 = 现读全部题数 − 现读丙案枚数（三数算式由 `derive_scorability` 自证）
  ④ 逐枚处置名册与现读缺口名册**相等**（判据①一枚不落；归桶是本单新增的分析）
  ⑤ 盘面题源相对基点 b78ecd8 **零改题落地**（本单的处置结论就是「不落地」，这也要能被复跑）
  ⑥ 待授权那枚甲的影子根全套数（19→18、指纹不破、守恒不违规、判分器反证不命中）

摘刀的账在 `tests/test_r598_ledger_teeth.py`；三片完整性那族在
`tests/test_r598_r97_shards_are_derived.py`。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_SCRIPT = REPO_ROOT / "scripts" / "r598_disposition_ledger.py"
PENDING_SCRIPT = REPO_ROOT / "scripts" / "r598_pending_jia.py"
MASTER_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger():
    return _load("r598_ledger_t1", LEDGER_SCRIPT)


@pytest.fixture(scope="module")
def pending():
    return _load("r598_pending_t1", PENDING_SCRIPT)


# ---------------------------------------------------------------------------
# ①②③ 三把尺互比：行数 / 词条数 / 丙案枚数 / 分母
# ---------------------------------------------------------------------------

def test_missing_rows_equal_named_unscorable_and_the_fingerprint_holds(ledger):
    reading = ledger.coverage_reading(REPO_ROOT)
    assert reading["missing_rows"] == reading["missing_terms"], (
        "口径指纹破了（查无出处的行数 != 词条数）：判据⑥不许破")
    assert reading["missing_ids"] == reading["unscorable_ids"], (
        "覆盖度件算出的缺口名册与丙案点名名册不等：{0} vs {1}".format(
            reading["missing_ids"], reading["unscorable_ids"]))
    assert reading["unscorable_n"] == reading["missing_rows"]


def test_denominator_is_two_readings_apart_not_a_hand_written_literal(ledger):
    deps = ledger.load_deps()
    rows = ledger.read_rows(REPO_ROOT)
    derived = deps["ev"].derive_scorability(rows)
    total = derived["total_rows"]
    deducted = derived["deducted_n"]
    denominator = derived["denominator_rows"]
    assert total == len(rows), "全部题数读歪"
    assert deducted == ledger.coverage_reading(REPO_ROOT)["unscorable_n"]
    assert denominator == total - deducted, "三数算式破了：分母必须是现读两数之差"
    assert denominator > 0 and deducted > 0, "读出了 0，等于没量"


# ---------------------------------------------------------------------------
# ④ 逐枚处置：一枚不落、归桶全覆盖、理由与去向逐枚齐全（理由从题源现读，不另写一套）
# ---------------------------------------------------------------------------

def test_disposition_table_partitions_the_derived_roster_with_no_leftover(ledger):
    table = ledger.disposition_table(REPO_ROOT)
    derived = ledger.coverage_reading(REPO_ROOT)["missing_ids"]
    assert [item["id"] for item in table] == derived, (
        "处置表与现读缺口名册不同代：处置账会随题源漂移，本件不许")
    assert all(item["disposition"] == "丙" for item in table), (
        "本单的处置结论是「全丙不落地」，表里出现了别的处置就是假话")
    assert all(item["bucket"] for item in table), "有一枚没归桶：判据①要求一枚不落"
    assert all(item["reason_in_fixture"].strip() and item["pool"].startswith("待派池")
               for item in table), "丙案的理由/去向必须逐枚齐全（缺一枚 unscorable_records 当场抛）"
    buckets = {}
    for item in table:
        buckets[item["bucket"]] = buckets.get(item["bucket"], 0) + 1
    assert sum(buckets.values()) == len(derived), "归桶加总 != 现读枚数"
    assert len(buckets) >= 5, "本单的分析把缺口分成了 {0} 桶，比预期的还粗".format(len(buckets))


def test_the_third_conflict_group_is_located_and_named(ledger):
    """§3 第一小节要现查的「住宿超标 需审批 vs 自理」：它在不在 19 枚里，逐字答。"""
    chat10 = ledger.chat10_reading(REPO_ROOT)
    assert chat10["in_the_unscorable_19"] is False, (
        "第三组现读进了丙案名册，本单 §3 那条「不在 19 枚里」的结论要重写")
    assert chat10["carries_r401_marker"] is False, "它带着丙案标记就不是「得分侧」那一格了"
    anchors = chat10["must_contain"]
    assert anchors, "chat-10 的锚词读空了：这一枚的账没法算"
    hits = chat10["anchor_provenance_documents"][anchors[0]]
    assert hits, "锚词派生出处读空了：说明覆盖度件那把尺没咬住语料"
    assert any(path.endswith("差旅费报销细则_2026版.txt") for path, _lines in hits), (
        "「部门负责人」在细则里没出处？那 chat-10 的处置账要重算")


# ---------------------------------------------------------------------------
# ⑤ 盘面：本单零改题落地（这也是结论，得能被复跑）
# ---------------------------------------------------------------------------

def test_the_shipped_fixture_carries_zero_retitled_rows_against_the_base(ledger):
    report = ledger.conservation(REPO_ROOT)
    assert report["base_blob_readable"] is True, "基点 blob 读不出来，守恒无法判"
    assert report["violations"] == [], "守恒破了：{0}".format(report["violations"])
    assert report["retitled_ids"] == [], (
        "盘面出现了改题落地的枚 {0}，但本单的处置是「不落地」——要么总控已授权并须同步重录"
        "域外件，要么这枚改动是绕开本单来的".format(report["retitled_ids"]))
    import hashlib
    import subprocess

    master = (REPO_ROOT / MASTER_REL).read_bytes()
    blob = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show",
         "{0}:{1}".format(ledger.BASE_REV, MASTER_REL.as_posix())],
        capture_output=True).stdout
    #: 🔴 这台机 core.autocrlf=true：blob 里是 LF、checkout 出来是 CRLF，所以字节比对必须先归一行尾，
    #: 否则这枚钉会因为「用哪种方式检出」而红——那不是判据。归行尾之后仍是逐字节比。
    assert master.replace(b"\r\n", b"\n") == blob, (
        "题源字节与基点 b78ecd8 不等（行尾归一后仍不等）而字段级改题账却读出来没变——"
        "两级凭据必须同向，先查是谁绕开本单写了题源")
    print("盘面题源 sha256[:16] {0} / 基点归行尾后 sha256[:16] {1}".format(
        hashlib.sha256(master.replace(b"\r\n", b"\n")).hexdigest()[:16],
        hashlib.sha256(blob).hexdigest()[:16]))


# ---------------------------------------------------------------------------
# ⑥ 待授权那枚甲：备而不落的凭据 + 影子根全套数
# ---------------------------------------------------------------------------

def test_the_pending_jia_row_is_still_declared_unscorable_on_disk(ledger, pending):
    rows = {str(row["id"]): row for row in ledger.read_rows(REPO_ROOT)}
    for row_id, plan in pending.PENDING_JIA.items():
        row = rows[row_id]
        marker = row.get("r401") or {}
        assert marker.get("disposition") == "丙", (
            "{0} 在盘面上已不是丙案，待授权账要重新归桶".format(row_id))
        assert plan["replaced_term"] in [str(t) for t in row["must_contain"]], (
            "{0} 的「被替换词」不在盘面锚词里：手抄账与派生账分叉".format(row_id))
        assert "anchor_provenance" not in row, (
            "{0} 判丙却带着派生出处：丙案铁规（题保留、锚词不动）".format(row_id))


def test_replaced_term_ledger_is_derived_not_hand_copied(pending):
    assert pending.check_replaced_terms(REPO_ROOT)["doc-17"]["derived_missing_terms"] == [
        pending.PENDING_JIA["doc-17"]["replaced_term"]]


def test_shadow_proof_lands_the_jia_without_touching_the_shipped_tree(pending, tmp_path):
    disk_before = (REPO_ROOT / MASTER_REL).read_bytes()
    report = pending.proof(REPO_ROOT, tmp_path)
    assert report["before"]["missing_rows"] > report["after"]["missing_rows"], (
        "影子根上的甲没有让缺口变小：那它就不是救援，只是换了个形状")
    assert report["after"]["fingerprint_rows_equals_terms"] is True
    assert report["after"]["missing_equals_unscorable"] is True
    assert report["conservation_drift"] == [], report["conservation_drift"]
    assert report["conservation_now_vs_base"]["unscorable_touched_ids"] == [], (
        "影子根里还有丙案行被改：甲只许动它自己那一枚")
    for row_id, judge in report["judge_counter_evidence"].items():
        assert judge["gold_passes"] is True, "{0} 连自己的金标都判不过".format(row_id)
        for item in judge["samples"]:
            assert item["hit"] is False, "{0} 的锚词被错答 {1!r} 命中".format(row_id, item["sample"])
    for row_id, info in report["derived_provenance"].items():
        for record in info["derived_records"]:
            path_name, line_number = info["claimed_sources"][record["anchor"]]
            assert record["file_name"] == path_name and record["raw_line_number"] == line_number, (
                "{0} 的派生出处与账上指针不符：出处是抄的不是派的".format(row_id))
    #: 影子根的全部意义：数在影子里动，盘面一个字节不动。这里用**前后各读一次**证它。
    disk_after = (REPO_ROOT / MASTER_REL).read_bytes()
    assert disk_after == disk_before, (
        "跑影子根把盘面题源改了：那本件的读数就不能算「备而不落」")
    assert not (tmp_path / "probe").exists(), "影子根没清干净，会污染下一枚件的语料计数"