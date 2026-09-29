# -*- coding: utf-8 -*-
"""R469 常驻钉：`docs/testing/` 那枚读数表必须由生成件出，且账面上的牙真咬得住。

为什么单独钉「生成」这件事（AGENTS.md 写域条款 + `tests/test_r454_readout_is_generated.py`
同一条纪律）：手写读数表会带上抄上一班的惯性，而本单交回的正是一堆数字。表文末那枚围栏
JSON 是唯一事实源，`render_readout()` 是唯一的出表口——盘上那份与再生件逐字节相同，
才谈得上「这些数是量出来的，不是写的」。

落在本件的三把反证钉（编号与 `scripts/r469_readout_lib.py::TEETH` 一一对上）：
* T5 手改表里任一枚读数（不动证据）⇒ 与再生件字节不符，`validate_readout` 拒。
* T4 存量六枚恒量任一枚前后不同 ⇒ 拒；T9 只把记录下来的 `match` 翻 bool ⇒ 也拒（恒量只信现场复算）。
* T6 把生产臂那一格写成「有牙读数」（§133 六实测生产标签全同值）⇒ 直接拒。
* T10 沙盒里残留一枚 `r59c-` 行没清 ⇒ 拒：没扫干净的库不许交回下一班。

外加两格名册机检：表 §六 那把「牙名册」必须与 `TEETH` 逐枚同序同文；`TEETH` 点名的每枚
测试函数必须真在 `tests/test_r469_*.py` 里（表里写一枚不存在的钉＝把没装的牙说成装了）；
反过来盘上任何一枚 `test_counter_evidence_*` 也必须在册——不许有没上账的牙。

全程离线：零真库、零容器、零模型，写盘只写 tmp_path。
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LIB_PATH = REPO_ROOT / "scripts" / "r469_readout_lib.py"
READOUT_PATH = REPO_ROOT / "docs" / "testing" / "r469-sandbox-scope-readout-2026-09-28.md"
LEDGER_FILES = sorted((REPO_ROOT / "tests").glob("test_r469_*.py"))


def _load(name: str, path: Path):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("r469_readout_lib", LIB_PATH)


@pytest.fixture(scope="module")
def markdown() -> str:
    return READOUT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def evidence(markdown: str) -> dict:
    return lib.extract_evidence(markdown)


def _validate_pair(mutated: dict):
    """让表格与证据自成一对再生一遍，再拿本单的闸去判它。

    刻意重新生成表格：否则第一道字节钉会先响，测不到「这一把牙盯的是语义」那一层。
    """
    return lib.validate_readout(lib.render_readout(mutated), mutated)


# ==================================================== 表由生成件出（判据本体）


def test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits(markdown: str,
                                                                evidence: dict) -> None:
    """T5 的正腿：盘上那份与 `render_readout(证据)` 逐字节相同——手写即假账。"""
    assert lib.render_readout(evidence) == markdown
    raw = READOUT_PATH.read_bytes()
    assert raw == markdown.encode("utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf"), "生成件不带 BOM，盘上那份也不许有"
    assert b"\r" not in raw, "生成件按 LF 落盘：混行尾会让字节钉天天误红"


def test_the_cli_is_the_only_way_that_produced_this_table(tmp_path, markdown: str) -> None:
    """走在册出表口（CLI render）再生一次：同一份证据必须出同一份表，且 rc＝0。"""
    evidence_path = tmp_path / "evidence.json"
    out_path = tmp_path / "regen.md"
    evidence_path.write_text(
        json.dumps(lib.extract_evidence(markdown), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(LIB_PATH), "render", "--evidence", str(evidence_path),
         "--out", str(out_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == lib.EXIT_OK, result.stderr[-800:]
    assert out_path.read_bytes() == READOUT_PATH.read_bytes(), "CLI 再生与盘上那份不同"


def test_the_in_tree_readout_passes_its_own_validator(markdown: str, evidence: dict) -> None:
    report = lib.validate_readout(markdown)
    tiers = sum(len(evidence["arms"][arm]["tiers"]) for arm in lib.ARMS)
    assert report["cells"] == tiers
    assert report["status"] == lib.STATUS_MEASURED
    assert report["measured_cells"] == len(evidence["arms"][lib.ARM_SANDBOX]["tiers"])
    verdict = lib.judge(evidence)
    assert verdict["arms"][lib.ARM_PRODUCTION]["status"] == lib.STATUS_NOT_MEASURED
    assert verdict["red_cells"] == [] and verdict["invariants_ok"] is True


def test_the_unmet_criteria_are_named_one_by_one_not_dropped(evidence: dict) -> None:
    """未过判据必须逐条点名：缺件由 validate 直接拒，「没写」与「没过」是两回事。"""
    unmet = lib.judge(evidence)["unmet_criteria"]
    pairs = {(item["arm"], item["criterion"]) for item in unmet}
    assert pairs == {(lib.ARM_PRODUCTION, key) for key in lib.CRITERIA_KEYS}
    for item in unmet:
        assert item["reading"], item
        assert item["verdict"] in (lib.FAIL, lib.UNVERIFIED), item


def test_the_evidence_block_is_unique_and_a_second_one_is_refused(markdown: str) -> None:
    """文末那枚围栏 JSON 必须唯一：两枚证据块＝拿哪一枚判要由人说。"""
    assert len(re.findall(r"^```json$", markdown, re.M)) == 1
    tail = markdown.split("```json", 1)[1]
    with pytest.raises(lib.ReadoutError, match="拿哪一枚判"):
        lib.extract_evidence(markdown + "\n```json" + tail)


# ================================================= 诚实边界（字面短语，不自反）


def test_the_table_carries_the_honest_boundary_in_literal_prose(markdown: str) -> None:
    """三句字面短语必须在表里；只与常量比是自反，证不了任何事。"""
    for phrase in ("不证客户隔离", "A3 已裁", "沙盒标签只证", "没过**的判据"):
        assert phrase in markdown, phrase
    for sentence in (lib.HONEST_BOUNDARY, lib.NOT_CELL3_GREEN):
        assert markdown.count(sentence) >= 2, sentence[:40]


def test_nobody_writes_that_cell3_is_green(markdown: str) -> None:
    """「格③ 已翻绿」只许出现在「这不等于」后面；词表本身没有绿。

    谁在这一格里写出绿，那一定是对着表动的笔——生成件里没有那个词。
    """
    needle = "格③ 已翻绿"
    guard = "这不等于"
    hits = [start for start in range(len(markdown)) if markdown.startswith(needle, start)]
    assert hits, "边界那句被删了"
    for start in hits:
        assert markdown.startswith(guard, start - len(guard)), markdown[start - 40:start + 20]
    words = (lib.CELL_MEASURED, lib.CELL_VACUOUS, lib.CELL_ZERO_RECALL, lib.CELL_RED_BREACH,
             lib.CELL_RED_CONTROL, lib.STATUS_MEASURED, lib.STATUS_RED, lib.STATUS_NOT_MEASURED)
    assert not [word for word in words if "GREEN" in word], words
    assert not [word for word in words if markdown.count(word) == 0], "词表里的判定词没一个上表"


# ================================================ 反证钉 T5：手改表格里的读数


def test_hand_editing_one_digit_in_the_table_is_refused(markdown: str) -> None:
    """T5：只动人看的那张表、不动文末证据 ⇒ 字节钉当场响。

    对照在上面那枚 `validate_readout(markdown)`：同一份证据再生出来的表过得去，
    所以红来自「表与证据脱开」这一条被测行为，不是来自整表结构。
    """
    rows = markdown.splitlines()
    edited = None
    for index, line in enumerate(rows):
        if not line.startswith("| "):
            continue
        flipped = re.sub(r"(?<=\D)1(?=\D)", "0", line, count=1)
        if flipped != line:
            edited = "\n".join(rows[:index] + [flipped] + rows[index + 1:]) + "\n"
            break
    assert edited is not None, "表里找不到一枚可改的数字，这钉没东西可咬"
    with pytest.raises(lib.ReadoutError, match="手改过表格"):
        lib.validate_readout(edited)


# ============================================== 反证钉 T4：存量六枚恒量不许漂


def test_counter_evidence_invariant_drift_is_refused(evidence: dict) -> None:
    """T4：跑后六枚任一枚与跑前不同（＝真数据被动过）⇒ 拒出表。"""
    drifted = copy.deepcopy(evidence)
    after = drifted["invariants"]["core_six"]["after"]
    victim = next(name for name in lib.CORE_INVARIANT_TABLES if after[name] > 0)
    after[victim] = after[victim] - 1
    with pytest.raises(lib.ReadoutError, match="存量六枚恒量前后不同"):
        _validate_pair(drifted)


def test_counter_evidence_a_recorded_match_flag_is_not_believed(evidence: dict) -> None:
    """记录下来的 `match` 不算数：现场复算才是准（这里前后相同却记 false ⇒ 也拒）。"""
    lying = copy.deepcopy(evidence)
    lying["invariants"]["core_six"]["match"] = False
    with pytest.raises(lib.ReadoutError, match="恒量复算不过关"):
        _validate_pair(lying)


def test_counter_evidence_the_leftover_sandbox_row_is_refused(evidence: dict) -> None:
    """清理不彻底（沙盒里还剩一枚 r59c 行）⇒ 拒：不许把没扫干净的库交给下一班。"""
    dirty = copy.deepcopy(evidence)
    dirty["cleanup"]["leftover_prefixed_rows"] = 1
    with pytest.raises(lib.ReadoutError, match="没清干净"):
        _validate_pair(dirty)


# ==================================== 反证钉 T6：生产那格不许写成「有牙读数」


def test_counter_evidence_a_fabricated_production_cell_is_refused(evidence: dict) -> None:
    """T6：把沙盒臂读数原样搬到生产臂 ⇒ 拒，并点名那句「生产臂声称拿到了有牙读数」。

    §133 六实测生产 `department` 全空、`classification` 全 = 1，这一臂今天只能是空集真。
    """
    faked = copy.deepcopy(evidence)
    donors = faked["arms"][lib.ARM_SANDBOX]["tiers"]
    for target, donor in zip(faked["arms"][lib.ARM_PRODUCTION]["tiers"], donors):
        target["admitted_total"] = donor["admitted_total"]
        target["reads"] = copy.deepcopy(donor["reads"])
        target["outside_sample"] = copy.deepcopy(donor["outside_sample"])
    cells = lib.judge(faked)["arms"][lib.ARM_PRODUCTION]["tiers"]
    assert any(cell["cell"] == lib.CELL_MEASURED for cell in cells), "伪造没造出读数，这钉空咬"
    with pytest.raises(lib.ReadoutError, match="生产臂声称拿到了"):
        _validate_pair(faked)


# ================================ 牙名册：表 §六 / `TEETH` / 盘上测试件三方对齐


def _defined_test_names() -> set:
    assert len(LEDGER_FILES) >= 3, "本单常驻件少于三枚，名册没法机检"
    names = set()
    for path in LEDGER_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names.update(node.name for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"))
    return names


def test_the_tooth_roster_is_unique_numbered_and_named_on_disk() -> None:
    ids = [item[0] for item in lib.TEETH]
    numbers = [int(item[1:]) for item in ids]
    assert numbers == list(range(1, len(numbers) + 1)), ids
    assert len(numbers) >= 8, "账上的牙少到 8 把以下，本单的判据就没东西咬了"
    assert len(set(ids)) == len(ids)
    names = _defined_test_names()
    missing = [item[2] for item in lib.TEETH if item[2] not in names]
    assert missing == [], "牙名册点了名，盘上却没有那枚测试：" + ",".join(missing)
    for item in lib.TEETH:
        assert len(item[1]) > 8, item


def test_no_counter_evidence_on_disk_is_missing_from_the_roster() -> None:
    booked = {item[2] for item in lib.TEETH}
    on_disk = {name for name in _defined_test_names()
               if name.startswith("test_counter_evidence_")}
    assert on_disk <= booked, "这几把牙没上账：" + ",".join(sorted(on_disk - booked))
    orphans = sorted(booked - _defined_test_names())
    assert orphans == [], "账上这两枚不在这三件里（挪了名或根本没装）：" + ",".join(orphans)


def test_the_roster_in_the_table_is_the_roster_in_the_lib(markdown: str) -> None:
    """表 §六 那张「编号/咬什么/落在哪枚测试」必须逐枚等于 `lib.TEETH`，同序同文。"""
    section = markdown.split("## 六、", 1)[1].split("## 七、", 1)[0]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("| ")
            and not set(line.strip()) <= set("|-: ")]
    body = [row for row in rows if row and row[0] in [item[0] for item in lib.TEETH]]
    assert [row[0] for row in body] == [item[0] for item in lib.TEETH]
    for row, tooth in zip(body, lib.TEETH):
        assert row[1] == tooth[1], tooth[0]
        assert row[2] == "`{0}`".format(tooth[2]), tooth[0]
