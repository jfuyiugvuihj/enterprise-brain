"""R454 判据③的常驻钉：读数表由 planner 生成，没拿到的格一律写「未验」。

为什么要钉"生成"这件事本身（跟进单 §128 二节判据③原文：「由 planner 生成骨架，
不是手写」）：手写读数表会带上抄上一班的惯性——计划书 §6 那句「别再抄上一班逐类不退化」
就是为这个写的。本班零模型、零容器，一格真读数都没拿到，所以这张表**每一枚格的
读数列都必须是「未验」**；谁在表里写出「过／应该没问题／0 枚」，谁就是在造凭据。

反证钉（第四把）：把一枚未验格的读数改成「过」⇒ validate_readout 当场红；
而改另一列（格名称）它无异议 ⇒ 证明红来自"盯住读数列"这一被测行为，不是来自整表结构。

全程离线：只读仓内文本文件＋跑一次本件自己的 planner（写盘只写 tmp_path）。
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_window_planner.py"
BANK_PATH = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
SUBSET_PATH = REPO_ROOT / "docs" / "testing" / "bank-shape-subset-30.jsonl"
EVIDENCE_PATH = REPO_ROOT / "docs" / "testing" / "sidecar-run9.jsonl"
READOUT_PATH = REPO_ROOT / "docs" / "testing" / "shape-window-readout-2026-09-28.md"


def _load_planner():
    name = "eval_window_planner"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


planner = _load_planner()


def _plan():
    bank_lines = [line for line in BANK_PATH.read_bytes().splitlines(keepends=True) if line.strip()]
    return planner.plan_window(
        list(planner.SHAPE_CELLS),
        bank_lines=bank_lines,
        subset_raw=SUBSET_PATH.read_bytes(),
        evidence=planner.load_approval_evidence(EVIDENCE_PATH),
        profile=planner.MachineProfile(),
    )


def _reading_rows(markdown):
    rows = {}
    for line in markdown.splitlines():
        if not line.startswith("| "):
            continue
        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cols) == 6 and cols[0] in planner.CELLS:
            rows[cols[0]] = cols
    return rows


def _mutate_one_reading(markdown, cell_id, replacement):
    """只改一枚格的最后一列（读数列），其余一个字不动。"""
    out = []
    hit = 0
    for line in markdown.splitlines():
        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cols) == 6 and cols[0] == cell_id:
            cols[-1] = replacement
            line = "| " + " | ".join(cols) + " |"
            hit += 1
        out.append(line)
    assert hit == 1, (cell_id, hit)
    return "\n".join(out) + "\n"


# ==================== 判据③主断言 ====================


def test_the_in_tree_readout_is_byte_for_byte_what_the_planner_emits(tmp_path):
    """读数表不是手抄的：CLI 再生一次，与盘上那件逐字节相同。"""
    target = tmp_path / "regen.md"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--out", str(target)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr[-800:]
    assert target.read_bytes() == READOUT_PATH.read_bytes(), "盘上那件与 planner 再生不同 ⇒ 有人手改过读数表"


def test_the_generated_skeleton_passes_its_own_validator():
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    verdict = planner.validate_readout(markdown, plan)
    assert verdict["rows"] == verdict["cells"] == len(plan["cells"])


def test_every_cell_row_reads_unverified_because_nothing_was_measured():
    plan = _plan()
    rows = _reading_rows(READOUT_PATH.read_text(encoding="utf-8"))
    assert sorted(rows) == sorted(plan["cells"])
    for cell_id, cols in rows.items():
        assert cols[-1] == planner.UNVERIFIED, (cell_id, cols[-1])


def test_readings_never_contain_numbers_or_borrowed_totals():
    """不写 0、不写 0/30、不抄上一班的读数：读数列里连数字都不许出现。

    注意口径：只查读数列。整表里"时延类格"的名字本来就带 p95／≤90 s 这种字样，
    那是被点名出局的那一栏，不是本班拿到的数——把它们一起禁掉就是替判据找茬。
    """
    rows = _reading_rows(READOUT_PATH.read_text(encoding="utf-8"))
    assert rows, "读数表里一枚格都没有"
    for cell_id, cols in rows.items():
        assert not any(char.isdigit() for char in cols[-1]), (cell_id, cols[-1])
        for banned in ("111.2", "31.0", "0.9378", "18 枚"):
            assert banned not in cols[-1], (cell_id, cols[-1], banned)


def test_readout_names_the_scope_rule_and_the_approve_boundary():
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    assert planner.SCOPE_SENTENCE in markdown
    assert planner.AUTO_APPROVE_SENTENCE in markdown
    for cell_id in planner.OUT_OF_SCOPE_CELLS:
        assert cell_id in markdown, cell_id


def test_readout_reports_the_row_by_row_comparison_and_the_family_ledger():
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    size = str(planner.SUBSET_SIZE)
    verdict = f"{size}/{size}"
    assert verdict in markdown, ("判据①要求把逐行比对结果写进报告", verdict)
    comparison = re.search(r"字节级等值\*\*：(\d+)/(\d+)", markdown)
    assert comparison and comparison.group(1) == comparison.group(2) == size, markdown[:400]
    for family in planner.FAMILIES:
        assert re.search(r"\| " + family + r" \| \d+ \| \d+ \| \d+ \|", markdown), family


def test_readout_carries_the_window_plan_numbers_the_planner_computed():
    plan = _plan()
    window = plan["windows"][0]
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    assert "窗数：**1**" in markdown
    assert str(window["approvals_planned_total"]) in markdown
    assert str(window["question_plays"]) in markdown
    # 拿不了的格必须点名，且带着原因而不是态度。
    for cell_id, reason in plan["unattainable_here"].items():
        assert cell_id in markdown
        assert reason[:12] in markdown, cell_id


def test_readout_embeds_the_plan_as_machine_readable_json():
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)\n```", markdown, re.S)
    assert block, "读数表里没有机器可读的计划块：validate_readout 就没法自我核对"
    payload = json.loads(block.group(1))
    assert len(payload["windows"]) == 1
    assert payload["out_of_scope_statement"] == planner.SCOPE_SENTENCE


# ==================== 反证钉 4：把一枚未验格写成过 ⇒ 红 ====================


@pytest.mark.parametrize("cell_id", list(planner.SHAPE_CELLS))
def test_counter_evidence_a_passing_reading_on_an_unverified_cell_turns_red(cell_id):
    markdown = _mutate_one_reading(READOUT_PATH.read_text(encoding="utf-8"), cell_id, "过")
    plan = _plan()
    with pytest.raises(planner.ReadoutError) as caught:
        planner.validate_readout(markdown, plan)
    message = str(caught.value)
    assert cell_id in message, message
    assert planner.UNVERIFIED in message, message


def test_counter_evidence_a_borrowed_number_and_a_soft_phrase_both_turn_red():
    """判据③点名要拦的两种写法：抄来的数字、和「应该没问题」这种态度。"""
    plan = _plan()
    for fake in ("0.9378", "应该没问题", "✅", "14 分"):
        markdown = _mutate_one_reading(
            READOUT_PATH.read_text(encoding="utf-8"), "A2-stream-verbatim", fake)
        with pytest.raises(planner.ReadoutError):
            planner.validate_readout(markdown, plan)


def test_counter_evidence_the_guard_watches_the_reading_column_not_the_whole_row():
    """摘掉"盯读数列"这件事的对照：改名称列、改取数面列，校验都无异议。

    于是上一枚用例的红只来自读数列这一位，不是来自"整行随便动都红"。
    """
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    line = next(l for l in markdown.splitlines() if l.startswith("| A2-stream-verbatim |"))
    cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert cols[0] == "A2-stream-verbatim", cols
    # 名称列（第二列）写上"显然过了"这种话，校验不动它——红不来自这一位。
    name_row = [cols[0], "A② 显然过了", cols[2], cols[3], cols[4], cols[5]]
    swapped = markdown.replace(line, "| " + " | ".join(name_row) + " |", 1)
    planner.validate_readout(swapped, plan)  # 不抛＝牙只咬读数列
    tampered_surface_cols = [cols[0], cols[1], cols[2], "取数面写着玩", cols[4], cols[5]]
    swapped_surface = markdown.replace(
        line, "| " + " | ".join(tampered_surface_cols) + " |", 1)
    planner.validate_readout(swapped_surface, plan)
    # 而读数列一动就红。
    with pytest.raises(planner.ReadoutError):
        planner.validate_readout(
            _mutate_one_reading(markdown, "A2-stream-verbatim", "过"), plan)


def test_counter_evidence_dropping_a_cell_row_turns_red():
    """少一行＝藏格：判据③不许把没拿到的格从表里删掉让它消失。"""
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    dropped = "\n".join(
        line for line in markdown.splitlines()
        if not line.startswith("| D-usage-nonzero |")) + "\n"
    with pytest.raises(planner.ReadoutError) as caught:
        planner.validate_readout(dropped, plan)
    assert "D-usage-nonzero" in str(caught.value), str(caught.value)


# ==================== 返工令：读数表里的名册接口 ====================


def _binding_rows(markdown):
    """§六 那张接口表是五列：判据格/名称/绑到名册哪几格/读数位/锚。"""
    rows = {}
    for line in markdown.splitlines():
        if not line.startswith("| "):
            continue
        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cols) == 5 and cols[0] in planner.CELLS:
            rows[cols[0]] = cols
    return rows


def test_readout_carries_the_roster_interface_for_every_requested_cell():
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    rows = _binding_rows(markdown)
    assert sorted(rows) == sorted(plan["cells"]), sorted(rows ^ set(plan["cells"]))
    for cell_id in plan["cells"]:
        for name in plan["r453_binding"][cell_id]:
            assert name in rows[cell_id][2], (cell_id, name)
            assert name in planner.R453_CLOUD_CELLS, name


def test_readout_names_the_roster_only_where_the_plan_claims_it():
    """反"第二本账"钉：读数表里出现的名册格名，必须等于计划自己认领的那批（全部现读 import）。

    谁手抄一批名册名进表（哪怕抄的是对的），这个集合就会多出成员，当场红。
    """
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    found = {name for name in planner.r453_cell_names() if name in markdown}
    expected = {name for names in plan["r453_binding"].values() for name in names}
    expected |= set(plan["r453_cloud_unreferenced"])
    expected |= set(plan["r453_local_only_out_of_scope"])
    owner = plan["r453_ledger_binding"][planner.LEDGER_FIELD]
    if owner:
        expected |= {owner}
    assert found == expected, sorted(found ^ expected)


def test_readout_reports_reverse_coverage_and_the_snapshot_identity():
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    snapshot = plan["r453_roster_snapshot"]
    assert snapshot["path"] in markdown
    assert snapshot["sha16"] in markdown, snapshot
    assert str(snapshot["cells_total"]) in markdown and str(snapshot["cloud_readable"]) in markdown
    for name in plan["r453_cloud_unreferenced"]:
        assert name in markdown, name


def test_readout_records_whether_the_roster_can_prove_every_shape_cell():
    """第 3 条的账面：能证就写「无」，不能证就把缺的读数点名——两形都得是可追的。"""
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    if plan["r453_unproven_shape_cells"]:
        for cell_id in plan["r453_unproven_shape_cells"]:
            assert cell_id in markdown
            assert planner.UNVERIFIED not in plan["unattainable_here"][cell_id]
    else:
        assert "名册证不了的格：**无**" in markdown


def test_counter_evidence_a_reading_with_no_forbidden_token_still_turns_red():
    """摘掉「读数列必须等于未验」这一层守卫的对照：
    一枚既不含禁用词、也不含数字的读写（「已核」），
    它的红只能来自「没拿到的格必须写未验」这一条，
    不是来自禁用词表，也不是来自数字检测。
    """
    plan = _plan()
    for token in planner.FORBIDDEN_READING_TOKENS:
        assert token not in "已核", token
    assert not any(ch.isdigit() for ch in "已核")
    markdown = _mutate_one_reading(
        READOUT_PATH.read_text(encoding="utf-8"), "A2-stream-verbatim", "已核")
    with pytest.raises(planner.ReadoutError) as caught:
        planner.validate_readout(markdown, plan)
    message = str(caught.value)
    assert "A2-stream-verbatim" in message, message
    assert planner.UNVERIFIED in message, message


def test_counter_evidence_dropping_the_interface_table_turns_red():
    """把 §六 的接口表整张抹掉＝两单接口又脱开：validate_readout 必须拦。"""
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    rows = _binding_rows(markdown)
    stripped = markdown
    for cols in rows.values():
        stripped = stripped.replace("| " + " | ".join(cols) + " |\n", "", 1)
    with pytest.raises(planner.ReadoutError) as caught:
        planner.validate_readout(stripped, plan)
    assert "接口表" in str(caught.value), str(caught.value)


def test_readout_carries_the_payload_coverage_line():
    """§六 必须有一行把「在场≠非空」的读数位覆盖落账，账上的名与位都来自计划现算。"""
    plan = _plan()
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    assert plan["r453_payload_coverage"], plan
    for cell_id, coverage in plan["r453_payload_coverage"].items():
        rows = [line for line in markdown.splitlines()
                if line.startswith("- " + planner.COVERAGE_MARKER) and cell_id in line]
        assert len(rows) == 1, (cell_id, rows)
        for field in coverage["fields"]:
            assert field in rows[0], (cell_id, field, rows[0])
        for names in coverage["suppliers"].values():
            for name in names:
                assert name in rows[0], (cell_id, name, rows[0])


def test_counter_evidence_stripping_the_coverage_line_turns_red():
    """把那一行整条抹掉＝假绿没人记账：validate_readout 必须拦。"""
    plan = _plan()
    markdown = "\n".join(
        line for line in READOUT_PATH.read_text(encoding="utf-8").splitlines()
        if not line.startswith("- " + planner.COVERAGE_MARKER)) + "\n"
    with pytest.raises(planner.ReadoutError) as caught:
        planner.validate_readout(markdown, plan)
    assert planner.COVERAGE_MARKER in str(caught.value), str(caught.value)
