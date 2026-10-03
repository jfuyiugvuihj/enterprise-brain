# -*- coding: utf-8 -*-
"""R483 · 八枚「当时 0 行」的表必须由生成件出，五把刀各有牙，两处总控裁定钉得住。

🔴 R593（2026-10-03）改形：演示窗与评测窗跑过之后三枚表已经有行，本件里两枚钉把自己变成了
永久红——一枚把「在册目标表此刻全 0 行」当常驻不变量（blade_c），一枚把「0 行」这个词本身
当成判据（retrieval_traces 那一格）。刀口一律从「读数」改回「判据」：判据是裁定用词与现读
行数互为牙齿，两个方向都咬，因此它随真库走，不随日历红。

为什么单独钉「派生」这件事（在册同族先例：tests/test_r470_restart_readout_is_derived.py、
tests/test_r454_readout_is_generated.py、tests/test_r469_readout_is_generated.py）：本单交回的
是一张「这八枚各空在哪一类」的表，手写它就带上抄上一班的惯性；而这一格全部价值在
「裁定与现扫互为牙齿」那一句——裁定一旦被改回好看的词，缺陷就被盖住了。所以本件既核盘上那张表
与再生件逐字节等值，又把「改一个词就红」的五把刀逐枚钉住（判据⑤：刀照基线造，不照 after 自己造）。

全程离线：读数只取盘上文档第五节那份原始读数（与生成器的 --live-from-doc 同一口径），
零库、零容器、零模型；变异一律造在 tmp_path 的副本上，被跟踪文件一个字都不改（事故 #71 的入规）。
🔴 本件不抄任何一枚读数与行号：数字只从「盘上文档 / 探针原件 / 现扫」三处现取，坐标一律运行时定位。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "r483_empty_tables_triage.py"
DOC_PATH = REPO_ROOT / "docs" / "testing" / "r483-empty-tables-2026-09-29.md"
PROBE_PATH = (REPO_ROOT / "docs" / "perf" / "raw" / "r470-2026-09-29"
              / "probe-before-stop-start.json")
BQ = chr(96)  # 文档里的表名与坐标都裹着它；本件不抄行号，只抄这一枚字符


def _mod():
    spec = importlib.util.spec_from_file_location("r483_triage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _mod()
DOC = DOC_PATH.read_text(encoding="utf-8")
PAYLOAD = M.extract_payload(DOC)
PROBE = json.loads(PROBE_PATH.read_text(encoding="utf-8"))["db"]
INDEX = M.SourceIndex(REPO_ROOT)
READINGS = M.build_readings(PAYLOAD, INDEX, M.baseline_from_probe(PROBE_PATH))

#: 巡检 job 名取自生成器常量：本件不另抄一份口径（抄了就是第二个真相）。
SWEEP = M.SWEEP_JOB


def _fresh(index=None, payload=None, probe=PROBE_PATH):
    return M.build_readings(payload if payload is not None else PAYLOAD,
                            index if index is not None else INDEX,
                            M.baseline_from_probe(Path(probe)))


def _table_rows(readings):
    return [line for line in M.render_readout_table(readings) if line.startswith("| " + BQ)]


def _copy(path, text):
    target = Path(path)
    target.write_text(text, encoding="utf-8", newline=M.NL)
    return str(target)


def _payload_with_rows(table, rows):
    """把读数件里某一枚表的现读改成另一个数——变异只做在内存里，盘上一枚字都不改。"""
    cut = json.loads(json.dumps(PAYLOAD))
    assert table in cut["readout"], table
    cut["readout"][table]["rows"] = rows
    return cut


def _contradicting_rows(verdict):
    """与裁定用词相反的那一面读数：预设 0 行的词配一枚非 0，说「有行」的词配一枚 0。"""
    return 0 if verdict == M.NONZERO_ROW_VERDICT else 7


def _row_naming(problems, table):
    """只取 validator 里「裁定用词 vs 现读行数」那一腿对本表的点名，钥匙串是生成器常量。"""
    return [item for item in problems
            if item.startswith(table + " ") and M.ROW_MISMATCH_PHRASE in item]


# ---------------------------------------------------------------- 派生自证（判据②与⑥要的正面）
def test_the_in_tree_document_is_the_regenerated_one_byte_for_byte():
    assert M.render_document(READINGS) == DOC, (
        "盘上这份与再生件不等值：要么有人手写了表格/文案，要么改了生成器没重跑 --sync")


def test_both_sentinels_are_exactly_one_each():
    assert DOC.count(M.BEGIN) == 1, "BEGIN 哨兵必须恰好一枚"
    assert DOC.count(M.END) == 1, (
        "END 哨兵必须恰好一枚——少了它就是 --sync 把生成表甩进正文（事故 #83），"
        "sync 报成功而 check 反过来说没有哨兵区")


def test_every_number_in_the_table_is_reproducible_from_its_own_source():
    """今日现读取自读数件，昨日底取自探针原件——两列各有各的出处，本件一枚数字都不抄。"""
    for line in _table_rows(READINGS):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        name = cells[0].strip(BQ)
        assert int(cells[1]) == PAYLOAD["readout"][name]["rows"], line
        assert int(cells[2]) == PROBE[name]["rows"], line


def test_the_coordinates_printed_in_the_document_are_the_ones_the_scanner_finds_now():
    for table in M.TARGET_TABLES:
        analysis = READINGS["analysis"][table]
        assert analysis["ddl_home"] in DOC, (table, analysis["ddl_home"])
        for hit in [item for item in analysis["hits"] if item.kind != "ddl"][:2]:
            assert hit.location() in DOC, (table, hit.location())


def test_the_scanner_never_counts_itself_as_a_write_point():
    for table in M.READ_TABLES:
        for hit in INDEX.write_hits(table):
            assert "r483" not in hit.file, hit.location()
        for rel, _count in INDEX.references(table)["files"]:
            assert "r483" not in rel, rel


def test_the_reader_only_emits_select_statements():
    for table in M.READ_TABLES:
        assert M.assert_select_only(M.pk_sql(table)).lower().startswith("select")
        assert M.assert_select_only(M.census_sql(table, "id")).lower().startswith("select")
    assert M.assert_select_only(M.EVENT_SQL).lower().startswith("select")
    for write in ("DELETE FROM alerts",
                  "INSERT INTO alert_rules (name, metric) VALUES ('x', 'y')",
                  "UPDATE metric_definitions SET status = 'active'",
                  "CREATE TABLE calculation_runs (id int)",
                  "SELECT 1; DROP TABLE user_profiles",
                  "TRUNCATE retrieval_traces"):
        with pytest.raises(ValueError):
            M.assert_select_only(write)


# ---------------------------------------------------------------- 五把反证刀，各咬一格
def test_blade_a_one_hand_changed_digit_on_disk_is_refused(tmp_path, capsys):
    table = M.TARGET_TABLES[0]
    live = M.rows_of(READINGS, table)["rows"]
    marker = "| " + BQ + table + BQ + " | " + str(live) + " |"
    assert DOC.count(marker) == 1, marker
    tampered = DOC.replace(marker, "| " + BQ + table + BQ + " | " + str(live + 1) + " |", 1)
    assert tampered != DOC
    assert M.main(["--check", "--doc", _copy(tmp_path / "blade_a.md", tampered)]) == 4
    assert "逐字节不符" in capsys.readouterr().err


def test_blade_b_a_lost_end_sentinel_reports_the_pair_not_a_zero(tmp_path, capsys):
    tampered = DOC.replace(M.END, "<!-- eaten -->", 1)
    assert M.main(["--check", "--doc", _copy(tmp_path / "blade_b.md", tampered)]) == 3
    err = capsys.readouterr().err
    assert "不成对" in err, err
    assert "END=0" in err, err
    assert "PASS" not in err, "哨兵被吃掉却报通过，就是事故 #83 原样重演"


def test_blade_c_an_empty_scan_root_names_every_table_that_lost_its_basis(tmp_path, capsys):
    """扫描根空 ⇒ 每张失去依据的表都要被点名；而「点名」本身必须随真库走（R593 判据②）。

    🔴 改前这枚钉的最后一行是 `assert not any(M.rows_of(READINGS, t)["rows"] for t in
    M.TARGET_TABLES)`：它把「在册目标表此刻全 0 行」当成了常驻不变量，于是这台机器只要真被
    用过一次就永久红——10-03 总控在主树现场复现（1 failed / 19 passed，75.96 s），一枚反证钉
    把自己的历史读数当成判据，挡死 R582 并树。本钉要量的一直是「依据没了必须点名」，
    不是「这些表现在是空的」。最后一行换成两面对着打的派生断言：

    * 面 A：把任一表的现读翻到与裁定相反的一面 → validator 必须点名这张表（摘掉
      validator 里那一腿它就红，这就是判据④的 K1）；
    * 面 B：翻回与裁定相合的一面 → 同一张表必须不再被点名（不许永红）。

    两面都不引用「今天的数是多少」，所以库长到多少行、被谁清过，这枚钉都还在量同一件事。
    """
    empty = tmp_path / "no_sources_here"
    empty.mkdir()
    assert M.main(["--json", "--scan-root", str(empty)]) == 1
    problems = json.loads(capsys.readouterr().out)["problems"]
    for table in M.TARGET_TABLES:
        if M.TRIAGE[table]["hit_kinds"]:
            assert any(table in item and "写入点扫描空了" in item for item in problems), (table, problems)
        if M.TRIAGE[table]["verdict"] != "no_seed_path":
            assert any(table in item and "应改判 no_seed_path" in item for item in problems), table
    #: —— 取代旧「全零」断言的派生腿 ——
    for table in M.TARGET_TABLES:
        verdict = M.TRIAGE[table]["verdict"]
        against = _contradicting_rows(verdict)
        named = _row_naming(M.validate(_fresh(payload=_payload_with_rows(table, against))), table)
        assert named, (table, verdict, against, M.validate(_fresh(payload=_payload_with_rows(table, against))))
        agreed = 0 if verdict in M.ZERO_ROW_VERDICTS else 1
        quiet = _row_naming(M.validate(_fresh(payload=_payload_with_rows(table, agreed))), table)
        assert quiet == [], (table, verdict, agreed, quiet)


def test_blade_d_a_zeroed_control_table_must_scream_about_the_ruler():
    control = M.CONTROL_TABLES[0]
    assert M.rows_of(READINGS, control)["rows"] > 0, "对照表本来就空，这把尺子无从自证"
    cut = json.loads(json.dumps(PAYLOAD))
    cut["readout"][control]["rows"] = 0
    problems = [item for item in M.validate(_fresh(payload=cut)) if control in item]
    assert problems, control
    assert all("尺子空转" in item for item in problems), problems
    assert any("本单所有 0 行都不作数" in item for item in problems), problems


def test_blade_e_moving_only_the_baseline_is_enough_to_go_red(tmp_path):
    table = M.TARGET_TABLES[0]
    shifted_probe = dict(PROBE)
    shifted_probe[table] = {"rows": PROBE[table]["rows"] + 3, "pk_max": PROBE[table]["pk_max"]}
    probe_copy = tmp_path / "probe_baseline_shifted.json"
    probe_copy.write_text(json.dumps({"db": shifted_probe}, ensure_ascii=False),
                          encoding="utf-8", newline=M.NL)
    shifted = _fresh(probe=probe_copy)
    disk_row = [line for line in _table_rows(READINGS) if line.startswith("| " + BQ + table + BQ)]
    moved_row = [line for line in _table_rows(shifted) if line.startswith("| " + BQ + table + BQ)]
    assert disk_row and disk_row != moved_row
    assert "| " + str(shifted_probe[table]["rows"]) + " |" in moved_row[0], moved_row[0]
    assert M.render_document(shifted) != DOC


# ---------------------------------------------------------------- 裁定 vs 现读（R593 判据①的正面）
def test_a_verdict_word_must_match_whether_that_table_has_rows_today():
    """每一格的裁定词，必须与这一格今天的现读行数同面（R593 判据①）。

    旧盘面上这件事没有钉：「0 行」只是写在裁定词里的假设，而唯一碰它的检查（blade_c 最后一行）
    把假设当成了「此刻全零」的常驻不变量——机器一被用过就永久红，词与数到底对不对得上反倒没人量。
    现在按两个方向各钉一手：预设 0 行的词只许用在读出 0 行的格上，说「有行」的词只许用在读出非 0 的格上。
    """
    for table in M.TARGET_TABLES:
        rows = M.rows_of(READINGS, table)["rows"]
        verdict = M.TRIAGE[table]["verdict"]
        assert (rows == 0) == (verdict in M.ZERO_ROW_VERDICTS), (table, rows, verdict)
        assert (rows > 0) == (verdict == M.NONZERO_ROW_VERDICT), (table, rows, verdict)


def test_every_re_ruled_cell_carries_the_problems_line_that_forced_it():
    """改判不许是任何人宣布的：每一格得带着把它逼出来的那行 problems 原话（R593 判据①）。

    🔴 凭据里的数字只算历史引用——本席复跑同一枚命令时，同一格里已经长出更多行——
    今天的事实由渲染件现取。所以本钉同时要求凭据那一行挨着「本格今日现读 N 行」渲染，
    数字出自读数件，不在裁定的散文里过夜。
    """
    for table in M.TARGET_TABLES:
        spec = M.TRIAGE[table]
        if spec["verdict"] != M.NONZERO_ROW_VERDICT:
            assert not spec.get("re_ruling"), (table, "没改判就别留改判凭据")
            continue
        ruling = spec.get("re_ruling") or ""
        assert "R593" in ruling and "0 行定性过期" in ruling, (table, ruling)
        printed = [item for item in DOC.splitlines() if item.startswith("- " + ruling)]
        assert len(printed) == 1, (table, len(printed))
        assert "本格今日现读 " + str(M.rows_of(READINGS, table)["rows"]) + " 行" in printed[0], printed[0]


# ---------------------------------------------------------------- 两处总控裁定的形状
def test_the_rulings_are_recorded_with_their_author():
    for table in M.TARGET_TABLES:
        spec = M.TRIAGE[table]
        assert spec["verdict"] in M.VERDICTS, (table, spec["verdict"])
        if spec.get("owner_ruling"):
            assert "总控 2026-09-29 裁定" in spec["owner_ruling"], table
            assert spec["owner_ruling"] in DOC, table


def test_retrieval_traces_still_owes_its_lane_to_the_event_hop():
    """R550 定形 + R593 摘掉「此刻 0 行」那一手。

    改前原文：`git show 4572aa8:tests/test_r483_empty_table_triage_is_derived.py`（R550 那次改口）
    与 `git show 6fcea4f:tests/test_r483_empty_table_triage_is_derived.py`（本件改名前的第一行）。

    这枚钉一直要量的是「retrieval_traces 那条道靠事件标签撑着」：产品面必须真在、跨过来的道必须
    带事件标签、调试面照旧不许冒充产品道、豁免必须用得上、09-29 那句「正常问答链一枚都不发」必须
    被点名作废。🔴 改前它第一行顺手钉了 `spec["verdict"] == "legitimately_empty"`——那是把 09-30
    的读数（0 行）当常驻判据，与 blade_c 最后一行同一枚病：10-03 问答窗跑过、库里有了行，这个词
    就得由现读翻面，而翻面的凭据是 validator，不是谁的嘴。今天不钉行数，改钉「把现读翻到与裁定
    相反的一面，validator 必须当场点名」——与真库同长，不随日历红。
    🔴「摘掉发射腿就重新报过期」那把刀照旧不在本件，它跑在影子树上，见
    tests/test_r550_counter_evidence_teeth.py；本件不许拿散文宣布那把刀存在。
    """
    spec = M.TRIAGE["retrieval_traces"]
    assert spec["verdict"] in M.VERDICTS, (spec["verdict"], M.VERDICTS)
    assert "已经过期" in spec["owner_ruling"], (
        "owner_ruling 里那句「正常问答链一枚都不发」必须被点名作废；留着它就是本表在册的第二句假话")
    product = READINGS["analysis"]["retrieval_traces"]["product"]
    assert product["routes"], "现扫爬不到任何产品面，本裁定就该改回 no_seed_path"
    assert all(route["event"] for route in product["routes"]), (
        "跨过来的道必须带着事件标签——无主借道不算产品道")
    assert product["debug_only"], "豁免声明没扫到调试面，就成了后门"
    assert not product["unused_exemptions"], product["unused_exemptions"]
    against = _contradicting_rows(spec["verdict"])
    assert _row_naming(M.validate(_fresh(payload=_payload_with_rows("retrieval_traces", against))),
                       "retrieval_traces"), (spec["verdict"], against)
def test_an_exemption_that_no_longer_matches_a_route_is_reported_as_a_back_door():
    """R550 改口（改前原文同上）。

    改前这枚咬的是「摘掉 debug_only_surface 声明 => 裁定过期」；在产品面真在的新形状下，摘声明
    只是少一格豁免、裁定不再过期，那枚牙就成了死牙。豁免这一格今天该咬的是「声明了却用不上」：
    把豁免换成一枚现扫爬不到的路由，validate() 必须当场报后门，不许静默通过（判据③）。
    """
    original = M.TRIAGE["retrieval_traces"]["debug_only_surface"]
    M.TRIAGE["retrieval_traces"]["debug_only_surface"] = ("/retrieval/never-scanned",)
    try:
        problems = M.validate(_fresh())
        assert any("retrieval_traces" in item and "豁免成了后门" in item for item in problems), problems
    finally:
        M.TRIAGE["retrieval_traces"]["debug_only_surface"] = original
def test_metric_definitions_stays_blocked_at_the_promotion_exit():
    spec = M.TRIAGE["metric_definitions"]
    assert spec["verdict"] == "no_seed_path"
    blocked = spec["blocked_at"]
    location = INDEX.definition(blocked)
    assert location is not None and location.location() in DOC, blocked
    assert INDEX.callers(blocked) == [], "promotion 出口一旦接上调用者，「道断在」那一句就得改"
    assert not READINGS["analysis"]["metric_definitions"]["product"]["routes"]


def test_a_blocked_at_that_gains_a_caller_is_reported_as_overturned():
    original = M.TRIAGE["metric_definitions"]["blocked_at"]
    M.TRIAGE["metric_definitions"]["blocked_at"] = "evaluate_all"  # 这枚在册有调用者
    try:
        problems = M.validate(_fresh())
        assert any("已被推翻" in item for item in problems), problems
    finally:
        M.TRIAGE["metric_definitions"]["blocked_at"] = original


def test_the_verdict_vocabulary_is_closed_and_every_word_has_an_instance():
    """R593 改名（原名 …all_three_words…）：词表照样封闭、每词照样有实例，一条没放宽。

    加词之后还要钉的是「新旧词分得很干净」：no_longer_empty 不属于预设 0 行的那一堆，
    词表恰好等于「三词 + 那一词」——谁把两堆并成一堆，这枚钉就红。
    """
    assert set(M.TRIAGE) == set(M.TARGET_TABLES)
    verdicts = [M.TRIAGE[table]["verdict"] for table in M.TARGET_TABLES]
    assert set(verdicts) == set(M.VERDICTS), verdicts
    assert M.NONZERO_ROW_VERDICT not in M.ZERO_ROW_VERDICTS, M.ZERO_ROW_VERDICTS
    assert set(M.VERDICTS) == set(M.ZERO_ROW_VERDICTS) | {M.NONZERO_ROW_VERDICT}, M.VERDICTS


# ---------------------------------------------------------------- V2 那三句明话（判据④）
def test_the_three_v2_sentences_say_plainly_what_is_missing():
    """三句各点名自己的表并把行数写进句子；句子结构由 V2_CHAINS 现取，措辞不在本件里过夜。

    🔴 R593：空与非空的话术也归现读管。改前这枚钉死一句 `assert "没有一行" in line`，
    那是 09-29 的读数而不是判据——告警两枚表与 retrieval_traces 长出行之后的文档若还这么写，
    就是台账里的第四句假话。现在断言的是「这句话什么时候许说『没有一行』」。"""
    for chain in M.V2_CHAINS:
        marker = "- **" + chain["goal"].split(" ")[0]
        matched = [line for line in DOC.splitlines() if line.startswith(marker)]
        assert len(matched) == 1, (chain["goal"], matched)
        line = matched[0]
        #: 空话术只许出现在本 chain 点名的目标表全为 0 行时（context 表是旁证，从不被断言为空）。
        claim = [table for table in chain["tables"] if table in M.TARGET_TABLES]
        assert claim, chain["goal"]
        empty = all(M.rows_of(READINGS, table)["rows"] == 0 for table in claim)
        assert ("没有一行" in line) == empty, (chain["goal"], claim, empty, line)
        for table in chain["tables"]:
            assert table in line, (table, line)
            assert inline(table) in line, (table, line)
            assert str(M.rows_of(READINGS, table)["rows"]) + " 行" in line, (table, line)


def test_the_alert_sentence_carries_its_own_running_proof():
    """#11 那句不许只说空：巡检真在跑的两格证据（现扫 add_job + 日志成功行）得同句出现。"""
    line = [item for item in DOC.splitlines() if item.startswith("- **#11")][0]
    assert SWEEP in line and "executed successfully" in line, line
    assert "add_job" in line, line


def test_the_notification_sentence_still_bows_to_yi():
    """#17 端到端只到 (乙)：那句得自己承认这条边界，不许被后人顺手改绿。"""
    line = [item for item in DOC.splitlines() if item.startswith("- **#17")][0]
    assert "(乙)" in line, line


def inline(text):
    return chr(96) + text + chr(96)
