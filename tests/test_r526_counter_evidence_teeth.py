# -*- coding: utf-8 -*-
"""R526 判据⑤ · 反证刀：每把先在影子副本上跑正控（确认改动真进了输入），再验它咬得住。

刀口与牙共用同一批纯函数（从 ``tests/test_r526_slot_caliber_closure.py`` 拉起来用），不存在
「刀有牙、钉没牙」。影子端＝tmp_path 上的契约副本（按 CRLF 落真字节再读回）或口径 dict 的深拷贝：
真盘面一个字都不动。

🔴 本文件里的伪造量级只是影子的弹药：不进契约纸、不进观测面、不进任何回执，也不是对上一窗读数
的复述（上一窗的分位另有件，本单一枚都不引）。

每把都点名 victim。上一班的教训（正则整枚永不匹配＝死牙）落地成两件事：动手之后先断言改动确实
在字节里，再断言违规清单非空且点到那一格；未动手时同一枚函数必须是绿的。
"""

import copy
import importlib.util
import io
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


T = _load("tests/test_r526_slot_caliber_closure.py", "r526_closure_for_teeth")
R453 = _load("scripts/eval_cloud_window_readout.py", "r526_roster_for_teeth")

# --- 伪造弹药（只喂影子的副本，永不落纸）---
FORGED_SECONDS = "90 s"
SECOND_RULER_SCRIPT = "scripts/eval_transport_ask_v3.py"
GHOST_RULER_SCRIPT = "scripts/eval_transport_ask_v9.py"
CLOUD_SHAPE_CELL = "frame_shape"
INVENTED_CELL = "p99_wall_ms"
SECOND_ARITHMETIC = "分位取线性插值，不看在册那枚件"
# --- 弹药结束 ---

VICTIM_A = "qa.end_to_end_p95_ms"
VICTIM_B = "qa.first_text_p95_ms"
VICTIM_E = "report.stage.generate.p95_ms"
QA_ROW_NEEDLE = "| `qa` | `end_to_end_p95_ms` 结论完成 |"


@pytest.fixture(scope="module")
def roster():
    return {row["cell"]: row for row in R453.CELLS}


@pytest.fixture()
def shadow(tmp_path):
    """契约纸的影子端：改动按 CRLF 落进真字节再原样读回，切空气的刀在这儿露馅。"""
    original = T.contract_text()
    path = tmp_path / "contract-v1.md"

    def materialize(text: str) -> str:
        path.write_text(text, encoding="utf-8", newline="\r\n")
        read_back = io.open(path, encoding="utf-8", newline="").read()
        assert read_back.count("\r\n") == text.count("\n"), "影子副本没按字节落回"
        assert read_back.replace("\r\n", "\n") == text
        return text

    materialize.original = original
    return materialize


def _one_line(text: str, needle: str, change) -> str:
    """只在含 needle 的那一行动手：改过头的刀量不出单枚 victim。"""
    lines = text.split("\n")
    hits = [index for index, line in enumerate(lines) if needle in line]
    assert len(hits) == 1, (needle, hits)
    before = lines[hits[0]]
    lines[hits[0]] = change(before)
    assert lines[hits[0]] != before, "改动是恒等：这把刀是死的"
    return "\n".join(lines)


def _sub(old: str, new: str):
    def change(line: str) -> str:
        assert old in line, old
        return line.replace(old, new, 1)

    return change


def _caliber_for(slot: str = None, **changes):
    """改影子口径 dict（只动点名的那一格），真盘面那本一个字不动。"""
    cal = copy.deepcopy(T.caliber())
    targets = [item for item in cal["slots"] if slot is None or item["slot"] == slot]
    assert targets, slot
    for item in targets:
        for key, value in changes.items():
            assert key in item, key
            item[key] = value
    return cal


def _bites(violations, victim, column=None):
    assert violations, "这把刀没咬：死牙"
    hits = [line for line in violations if victim in line]
    assert hits, (victim, violations)
    if column is not None:
        assert any(column in line for line in hits), hits
    return hits


# ==================== K1 目标格被偷填成秒数，又拿不出 docs/perf/raw/ 凭据 ====================


def test_k1_a_stolen_number_without_raw_evidence_turns_the_nail_red(shadow):
    assert T.check_targets_pending(shadow.original, T.caliber()) == []  # 正控

    mutated = shadow(_one_line(shadow.original, QA_ROW_NEEDLE, _sub(T.PENDING_TEXT, FORGED_SECONDS)))
    violations = T.check_targets_pending(mutated, T.caliber())
    _bites(violations, VICTIM_A, "凭据")
    assert not any(T.PENDING_TEXT in line for line in violations)


def test_k1b_the_same_number_is_admissible_once_every_leg_is_real(shadow):
    """反向对照：K1 不是「凡有数字就红」的假牙——三件齐了就该放行。"""
    cal = _caliber_for(
        VICTIM_A, reader_landed=True, prerequisite="", raw_readout="docs/testing/sidecar-run9.jsonl"
    )
    assert T.fillable(next(i for i in cal["slots"] if i["slot"] == VICTIM_A))
    mutated = shadow(_one_line(shadow.original, QA_ROW_NEEDLE, _sub(T.PENDING_TEXT, FORGED_SECONDS)))
    assert T.check_targets_pending(mutated, cal) == []

# ==================== K2 观测面与契约散文分家（散文抄了第二套 / 观测面自己跑了） ============


def test_k2a_a_second_ruler_copied_into_the_prose_turns_the_nail_red(shadow):
    assert T.check_doc_agreement(shadow.original, T.caliber()) == []  # 正控

    row_needle = "| `%s` |" % VICTIM_A
    mutated = shadow(
        _one_line(shadow.original, row_needle, _sub("scripts/eval_transport_ask_v2.py", SECOND_RULER_SCRIPT))
    )
    _bites(T.check_doc_agreement(mutated, T.caliber()), VICTIM_A, "量具")


def test_k2b_the_module_drifting_away_from_the_prose_turns_the_same_nail_red(shadow):
    """同一枚分家从另一边进：改观测面、不动散文，也要咬。"""
    cal = _caliber_for(VICTIM_A, instrument=SECOND_RULER_SCRIPT)
    _bites(T.check_doc_agreement(shadow.original, cal), VICTIM_A, "量具")


# ==================== K3 三件里摘掉一件 ====================


@pytest.mark.parametrize(
    "column,victim",
    [
        ("instrument", VICTIM_A),
        ("raw_readout", VICTIM_B),
        ("raw_field", VICTIM_B),
        ("condition", VICTIM_E),
        ("prerequisite", VICTIM_A),
    ],
)
def test_k3_removing_one_leg_turns_the_closure_red(column, victim) -> None:
    """判据①的牙：缺一件就红（prerequisite 那一枚是对照——它不是腿，摘掉它不该红）。"""
    assert T.check_legs(T.caliber()) == []  # 正控
    cal = _caliber_for(victim, **{column: "" if column != "prerequisite" else ""})
    violations = T.check_legs(cal)
    if column == "prerequisite":
        assert violations == [], "落数前欠不是腿：摘掉它不该把闭环判红"
        return
    hits = [line for line in violations if victim in line]
    assert hits, (victim, violations)


def test_k3b_an_unaddressed_slot_and_an_orphan_caliber_both_bite() -> None:
    """两头的改名都要露出来：格子没口径 / 口径挂在已不存在的格子上。"""
    cal = copy.deepcopy(T.caliber())
    dropped = cal["slots"].pop()
    _bites(T.check_legs(cal), dropped["slot"], "没口径")
    ghost = copy.deepcopy(T.caliber())
    ghost["orphan"] = ["analysis.end_to_end_p95_ms"]
    _bites(T.check_legs(ghost), "analysis.end_to_end_p95_ms", "已不存在")


# ==================== K4/K5 在册格名走私：拿云端形状格或名册外的枚名顶 ====================


def test_k4_a_cloud_shape_cell_on_a_number_slot_turns_the_mapping_red(roster) -> None:
    assert T.check_roster_cells(T.caliber(), roster) == []  # 正控
    cal = _caliber_for(VICTIM_A, roster_cell=CLOUD_SHAPE_CELL)
    _bites(T.check_roster_cells(cal, roster), VICTIM_A, "时延族")


def test_k5_a_cell_name_that_the_roster_does_not_have_turns_the_mapping_red(roster) -> None:
    cal = _caliber_for(VICTIM_A, roster_cell=INVENTED_CELL)
    _bites(T.check_roster_cells(cal, roster), VICTIM_A, "名册里不存在")


# ==================== K6 某一格另写一套算术 ====================


def test_k6_a_slot_with_its_own_rank_rule_turns_the_spine_red() -> None:
    assert T.check_spine_is_one(T.caliber()) == []  # 正控
    cal = _caliber_for(VICTIM_B, condition=SECOND_ARITHMETIC)
    _bites(T.check_spine_is_one(cal), VICTIM_B, "脊柱")


def test_k6b_a_second_copy_of_the_sample_floor_turns_the_spine_red() -> None:
    """样本门只许以名字出现一次：谁再抄一遍（哪怕抄的是同一枚名字），也当第二套算术。"""
    cal = _caliber_for(VICTIM_B)
    item = next(entry for entry in cal["slots"] if entry["slot"] == VICTIM_B)
    item["condition"] = item["condition"] + "；再说一次 MIN_SLO_SAMPLES"
    _bites(T.check_spine_is_one(cal), VICTIM_B, "样本门")


# ==================== K7 量具指向仓里没有的件 ====================


def test_k7_a_ruler_that_is_not_in_the_repository_turns_the_nail_red() -> None:
    assert T.check_instruments_on_disk(T.caliber()) == []  # 正控
    cal = _caliber_for(VICTIM_E, instrument_paths=[GHOST_RULER_SCRIPT])
    _bites(T.check_instruments_on_disk(cal), VICTIM_E, "不在仓内")


def test_k7b_a_prose_path_that_does_not_exist_turns_the_nail_red() -> None:
    """量具名写在散文里也一样要落仓：只改 instrument 那枚字符串。"""
    cal = _caliber_for(VICTIM_A, instrument="读数件 scripts/eval_transport_ask_v9.py 的 wall_ms")
    _bites(T.check_instruments_on_disk(cal), VICTIM_A, "仓外/不存在")


def test_k7c_a_field_the_instrument_does_not_emit_turns_the_nail_red() -> None:
    """字段名空头支票：说「取这一格」，上一窗的真件里就得逐行有它。"""
    cal = _caliber_for(VICTIM_A, reference_field="not_emitted_by_the_ruler")
    _bites(T.check_reference_fields(cal), VICTIM_A, "并不产出")


# ==================== K8 run10 交接表被糊：少一行 / 命令格变散文 ====================


def test_k8_a_missing_handoff_row_turns_the_closure_red(shadow) -> None:
    needle = "| D | `qa.cache_hit_p95_ms` |"
    lines = shadow.original.split("\n")
    hits = [index for index, line in enumerate(lines) if needle in line]
    assert len(hits) == 1, hits  # 正控：这一行今天在，删它才叫删它
    assert T.check_handoff(shadow.original, T.caliber()) == []
    mutated = shadow("\n".join(lines[: hits[0]] + lines[hits[0] + 1 :]))
    _bites(T.check_handoff(mutated, T.caliber()), "D")


def test_k8b_a_handoff_row_without_a_runnable_command_turns_the_closure_red(shadow) -> None:
    needle = "| E | 每档每段两枚分段格"
    mutated = shadow(
        _one_line(shadow.original, needle, _sub("python scripts/eval_slo_lane_readout.py", "找运维手跑一次"))
    )
    _bites(T.check_handoff(mutated, T.caliber()), "E")


# ==================== K9 整轮自证：干净盘面零违规，动过的每一把都有名字 ====================


def test_k9_the_untouched_shadow_is_clean_and_the_parser_is_alive(shadow, roster) -> None:
    """死牙总闸：解析器必须真解析到东西，未动手的盘面必须零违规。"""
    cal = T.caliber()
    section = T.caliber_section(shadow.original)
    rows, mapped, collisions = T.map_rows_to_slots(section, cal["slots"])
    assert rows, "§4b 一行都没解析出来"
    assert collisions == []
    assert set(mapped) == {item["slot"] for item in cal["slots"]}
    assert all(len(cells) == T.CALIBER_CELLS - 1 for cells in mapped.values())
    assert T.check_caliber(shadow.original, cal, roster) == []


def test_k9b_the_forgeries_stay_out_of_the_shipped_pages() -> None:
    """弹药只准待在影子里：契约纸、观测面、脊柱三处都不许出现伪造串。"""
    shipped = T.contract_text() + io.open(
        REPO / "app/api/v1/observability.py", encoding="utf-8", newline=""
    ).read()
    for forgery in (FORGED_SECONDS, SECOND_RULER_SCRIPT, GHOST_RULER_SCRIPT, INVENTED_CELL, SECOND_ARITHMETIC):
        assert forgery not in shipped, forgery
    assert T.find_magnitudes(T.caliber_section(T.contract_text())) == []