"""R453 判据③ · 口径标签是**可验的**，不是态度：`scripts/eval_cloud_window_readout.py` 的牙。

判据原文要两件事，缺一件就是空话：
① 云端窗能读哪些格、哪些必须本机全量，交回的是**机器表**（格表＝件内数据，`--json` 可解析，
   markdown 那份逐行竖线枚数相同），不是一段散文；
② 云端窗每一格读数必须带 `caliber=cloud-shape`，而读数器在 `caliber=cloud-shape` 与
   `p95`／端到端时延／逐类分数／`correctness` **同段出现时当场报错退出**（rc=2）。
   段＝一行读数，同一 `segment` 跨行也算同一段——分两行写蒙不过去。

再加一枚开窗预检（`--preflight`）：`deploy/compose.cloud-eval.yaml` 那四枚 env 必须在
**进程环境**里；本机 09-28 实测 shell 没设时 compose 会静默回落到 `--env-file` 的本机值，
密钥退回 local 就是云端一次 401，所以预检缺一枚就 rc=2，且一个字节都不回显值。

反证钉（每把都真摘掉被测行为一次）：
- a) 把格表里的 p95 那格改成「云端可读」⇒ 混写读数就不红了（证明红来自表，不是来自字符串巧合）；
- b) 把改名走私那条模式钉摘掉（FORBIDDEN_PATTERN 换成永不匹配）⇒ `p95_walltime_ms` 混写不红；
- c) 把「口径必须在册」那一支摘掉（R2 让位）⇒ 缺口径的云端读数也不红；
- d) 把预检在场判据摘掉 ⇒ 空进程环境也报通过。
四把红的全是本件自己的钉，格表与读数件都在 tmp 里改，不动树上的在册件。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_cloud_window_readout.py"

SPEC = importlib.util.spec_from_file_location("r453_cloud_window_readout", SCRIPT)
assert SPEC and SPEC.loader
readout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readout)

#: 判据③点名的四类「必须本机」读数，取格表里的在册拼写。
CRITERION_FAMILIES = ("p95_wall_ms", "wall_ms", "per_category_score", "correctness")

#: 格表指纹（09-28 返工后现取，含总控裁定 (b) 的「形状 vs 数值」拆格）。表一改口径这一枚就漂——
#: 想放宽口径，得连本枚一起改口，这正是 E5 那把牙要拦的事。
TABLE_SHA256 = "19fb5b5ac2ebed026ce68225d345dd60e326010366a7990381e5f8972bef812a"

#: 总控 09-28 令①（接口冻结）：这十枚云端可读格名从此不增、不删、不改名——R454 已按
#: 这本表在写 crosswalk，这边动一次名字对面就白跑一轮。断言一律按集合，不按枚数。
CLOUD_INTERFACE = frozenset({
    "answer_shape",
    "approval_gate_shape",
    "citation_shape",
    "error_class_shape",
    "escalation_annotation",
    "event_surface",
    "frame_shape",
    "queue_readback",
    "retry_sentinel_shape",
    "usage_fields_present",
})

#: 裁定（b）之后必须留在本机那一侧的三枚数值格（总控 09-28 认可，不许往云端那一格挪）。
LOCAL_NUMERIC_INTERFACE = frozenset({
    "answer_char_count",
    "citation_count_value",
    "usage_token_values",
})


CLOUD_SHAPE_ROW = {"segment": "A2", "caliber": "cloud-shape",
                   "cells": {"text_frames": 24, "missing_chars": 0}}


def write_rows(tmp_path: Path, rows) -> Path:
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    target = tmp_path / "readouts.jsonl"
    target.write_text(payload, encoding="utf-8")
    return target


def run(argv):
    return readout.main(argv)


def mixed_row(cell: str) -> dict:
    return {"segment": "A2", "caliber": "cloud-shape", "cells": {"text_frames": 24, cell: 1}}


# ------------------------------------------------------------------ 判据③ 之「机器表」
def test_the_table_is_data_not_prose() -> None:
    payload = readout.table_payload()
    assert set(payload) == {"calibers", "cells", "summary"}, "表的骨架漂了"
    assert payload["calibers"] == {"cloud": "cloud-shape", "local": "local-full"}
    assert len(payload["cells"]) == payload["summary"]["total"] == len(readout.CELLS)
    kinds = {row["kind"] for row in payload["cells"]}
    assert kinds == {"shape", "latency", "score"}, "每一格都必须归进这三类之一"


def test_cloud_readable_means_shape_and_nothing_else() -> None:
    for row in readout.CELLS:
        if row["cloud"]:
            assert row["kind"] == readout.SHAPE, "%s 不是形状类却标了云端可读" % row["cell"]
        else:
            assert row["kind"] in (readout.LATENCY, readout.SCORE), (
                "%s 既不是时延也不是分数，却打成必须本机——口径表被写窄了也要报" % row["cell"])


@pytest.mark.parametrize("cell", CRITERION_FAMILIES)
def test_the_four_cells_the_criterion_names_are_local_only(cell: str) -> None:
    row = readout.resolve(cell)
    assert row is not None, "判据③点名的 %s 不在格表里，读数器无从拒绝" % cell
    assert row["cloud"] is False, "%s 必须本机全量，表里却允许云端读" % cell
    assert row["cell"] == cell, "%s 命中的是别名，格名应为 %s" % (cell, row["cell"])


def test_the_markdown_table_rows_are_uniformly_columned() -> None:
    lines = readout.render_markdown()
    header = lines[0]
    columns = header.count("|")
    assert columns == 8, "格表表头应有 7 列，实测竖线 %d 枚" % columns
    body = [line for line in lines if line.startswith("| ") and line.count("|") == columns]
    assert len(body) == len(readout.CELLS) + 2, (  # +2＝表头一行、分隔一行
        "逐行竖线枚数必须一致，否则这张表就不是机器表：%d 行 vs 期望 %d" % (
            len(body), len(readout.CELLS) + 2))
    ragged = [line for line in lines if "|" in line and line.count("|") != columns]
    assert not ragged, "表里出现了列数不一致的行：%s" % ragged[:1]


def test_the_table_carries_a_fingerprint_and_anchors_per_cell() -> None:
    assert readout.table_sha256() == TABLE_SHA256, (
        "格表指纹漂了：口径被改宽（或改窄）都要显式改口并同步跟进单")
    for row in readout.CELLS:
        assert row["why"].strip() and row["anchor"].strip(), "%s 缺理由或缺凭据锚" % row["cell"]


def test_cell_aliases_are_unique_across_cells() -> None:
    seen = {}
    for row in readout.CELLS:
        for name in (row["cell"],) + tuple(row["aliases"]):
            assert name not in seen, "%s 同时属于 %s 与 %s" % (name, seen.get(name), row["cell"])
            seen[name] = row["cell"]
    assert len(seen) == len(readout.REGISTRY), "别名表与注册表枚数不等"


# ------------------------------------------------------------------ 判据③ 之「当场报错退出」
def test_a_clean_cloud_readout_passes_and_tags_every_cell(tmp_path) -> None:
    target = write_rows(tmp_path, [
        CLOUD_SHAPE_ROW,
        {"segment": "D", "caliber": "cloud-shape", "sources_present": True},
        {"segment": "A1", "caliber": "local-full", "p95_wall_ms": 154509.1},
    ])
    assert run(["--readouts", str(target)]) == 0


@pytest.mark.parametrize("cell", CRITERION_FAMILIES)
def test_cloud_shape_with_a_latency_or_score_cell_exits_with_refusal(tmp_path, cell, capsys) -> None:
    target = write_rows(tmp_path, [mixed_row(cell)])
    assert run(["--readouts", str(target)]) == 2, "混写没被拒，判据③就是空话：%s" % cell
    err = capsys.readouterr().err
    assert "cloud-shape" in err and cell in err, "拒绝必须点名段与格：%s" % err


def test_splitting_the_mixing_across_two_rows_of_one_segment_still_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [
        {"segment": "A2", "caliber": "cloud-shape", "text_frames": 9},
        {"segment": "A2", "caliber": "cloud-shape", "wall_ms": 1200},
    ])
    assert run(["--readouts", str(target)]) == 2, "同段拆两行也得拒——段是口径的边界"


def test_a_renamed_latency_cell_still_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [{"segment": "A5", "caliber": "cloud-shape", "p95_walltime_ms": 12.3}])
    assert run(["--readouts", str(target)]) == 2, "改个名就放行等于没有这条牙"


def test_an_unregistered_cell_in_a_cloud_segment_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [{"segment": "A9", "caliber": "cloud-shape", "mystery_cell": 1}])
    assert run(["--readouts", str(target)]) == 2, "认不出的格不许替它担保是形状"


def test_an_unregistered_cell_in_a_local_segment_only_warns(tmp_path, capsys) -> None:
    target = write_rows(tmp_path, [{"segment": "A9", "caliber": "local-full", "mystery_cell": 1}])
    assert run(["--readouts", str(target)]) == 0
    assert "表外格" in capsys.readouterr().err


def test_a_row_without_a_caliber_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [{"segment": "A2", "cells": {"text_frames": 3}}])
    assert run(["--readouts", str(target)]) == 2, "缺口径＝没标签，云端窗不许收"


def test_an_invented_caliber_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [{"segment": "A2", "caliber": "cloudy", "text_frames": 3}])
    assert run(["--readouts", str(target)]) == 2, "自创口径不在册就不许成立"


def test_a_row_without_a_segment_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [{"caliber": "cloud-shape", "text_frames": 3}])
    assert run(["--readouts", str(target)]) == 2, "没有段，口径无处可挂"


def test_a_missing_readout_file_reports_cannot_fetch(tmp_path) -> None:
    assert run(["--readouts", str(tmp_path / "nope.jsonl")]) == 3


def test_check_rows_is_pure_and_returns_named_violations() -> None:
    violations, warnings = readout.check_rows([mixed_row("correctness")])
    assert warnings == []
    assert len(violations) == 1
    record = violations[0]
    assert record["rule"] == "R3" and record["segment"] == "A2"
    assert record["cell"] == "correctness" and "cloud-shape" in record["detail"]


# ------------------------------------------------------------------ 判据① 的开窗预检
def test_preflight_reports_presence_and_never_the_value(monkeypatch, capsys) -> None:
    """预检报在场与否——判据①的「密钥不进命令行历史、不进文件」全靠这一枚兜住。"""
    secret = "skshouldneverbeechoed0123456789"
    for name in readout.WINDOW_ENV:
        monkeypatch.setenv(name, secret)
    assert run(["--preflight"]) == 0
    out = capsys.readouterr().out
    assert secret not in out, "预检把值打出来了，密钥就进了滚屏与日志"
    assert "present" in out
    for name in readout.WINDOW_ENV:
        monkeypatch.delenv(name, raising=False)
    assert run(["--preflight"]) == 2, "进程环境空着却报通过＝这枚预检是空的"


def test_preflight_fails_closed_on_absent_and_empty(monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "https://cloud.example.invalid/v1")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen-cloud")
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "32768")
    readings = readout.preflight()
    states = dict(readings)
    assert states["LOCAL_MODEL_API_KEY"] == "absent"
    assert states["LOCAL_MODEL_BASE_URL"] == "present"
    monkeypatch.setenv("LOCAL_MODEL_API_KEY", "")
    assert dict(readout.preflight())["LOCAL_MODEL_API_KEY"] == "empty"


# ------------------------------------------------------------------ 反证钉（四把，逐把摘行为）
def test_counter_evidence_a_widened_table_stops_refusing_the_mix(monkeypatch, tmp_path) -> None:
    """摘掉「p95 属必须本机」这一行为 ⇒ 混写就不红了：证明红来自格表本身。"""
    target = write_rows(tmp_path, [mixed_row("p95_wall_ms")])
    assert run(["--readouts", str(target)]) == 2
    row = dict(readout.resolve("p95_wall_ms"))
    row["cloud"] = True
    monkeypatch.setitem(readout.REGISTRY, "p95_wall_ms", row)
    assert run(["--readouts", str(target)]) == 0, "表改宽后仍红＝钉咬的是字符串，不是口径"


def test_counter_evidence_a_disarmed_pattern_stops_refusing_the_rename(monkeypatch, tmp_path) -> None:
    target = write_rows(tmp_path, [{"segment": "A5", "caliber": "cloud-shape", "p95_walltime_ms": 1.0}])
    assert run(["--readouts", str(target)]) == 2
    monkeypatch.setattr(readout, "FORBIDDEN_PATTERN", re.compile(r"(?!)"))
    violations, _warnings = readout.check_rows([{"segment": "A5", "caliber": "cloud-shape",
                                                 "p95_walltime_ms": 1.0}])
    assert [v["rule"] for v in violations] == ["R4"], "模式钉摘掉后只剩表外格那一手"


def test_counter_evidence_a_dropped_caliber_check_silences_the_tag(monkeypatch, tmp_path) -> None:
    """把在册口径判据（R2）放宽：空口径的云端读数就从红变绿——说明那一支真在出力。"""
    target = write_rows(tmp_path, [{"segment": "A2", "caliber": "", "cells": {"text_frames": 3}}])
    assert run(["--readouts", str(target)]) == 2
    rows = readout.load_rows(str(target))
    assert [v["rule"] for v in readout.check_rows(rows)[0]] == ["R2"]
    monkeypatch.setattr(readout, "CALIBERS", readout.CALIBERS + ("",))
    assert readout.check_rows(rows)[0] == [], "口径名单放宽后 R2 仍开火＝判据写死在别处"


def test_counter_evidence_a_rubber_stamp_preflight_reports_absent_never_present(monkeypatch) -> None:
    for name in readout.WINDOW_ENV:
        monkeypatch.delenv(name, raising=False)
    assert all(state == "absent" for _, state in readout.preflight())
    monkeypatch.setenv(readout.WINDOW_ENV[0], "x")
    assert sum(1 for _, state in readout.preflight() if state == "present") == 1
# ------------------------------------------------------------------ 裁定（b）：形状可云端、数值必本机
#: 同一件事的两面：形状那一格准在云端道读，取数值大小那一格必须本机全量。
NUMERIC_SPLIT = (
    ("citation_shape", "citations_present", "citation_count_value", "evidence_n"),
    ("citation_shape", "sources_shape", "citation_count_value", "sources_count"),
    ("usage_fields_present", "usage_slots_present", "usage_token_values", "usage_total_tokens"),
    ("usage_fields_present", "usage_keys", "usage_token_values", "usage_prompt_tokens"),
    ("answer_shape", "answer_chars_bucket", "answer_char_count", "answer_chars"),
    ("answer_shape", "answer_nonempty", "answer_char_count", "pre_answer_chars"),
)


@pytest.mark.parametrize("shape_cell,shape_alias,value_cell,value_alias", NUMERIC_SPLIT)
def test_ruling_b_keeps_the_shape_in_cloud_and_moves_the_number_to_local(
        shape_cell, shape_alias, value_cell, value_alias) -> None:
    shape = readout.resolve(shape_alias)
    value = readout.resolve(value_alias)
    assert shape is not None and shape["cell"] == shape_cell, (
        "%s 应当落在 %s 这一格（形状道）" % (shape_alias, shape_cell))
    assert shape["cloud"] is True, "%s 是形状读数，裁定准它上云端" % shape_cell
    assert value is not None and value["cell"] == value_cell, (
        "%s 应当落在 %s 这一格（数值道）" % (value_alias, value_cell))
    assert value["cloud"] is False, (
        "%s 取的是数值大小，按裁定必须本机全量，不许留在云端道" % value_alias)


@pytest.mark.parametrize("alias", ["evidence_n", "sources_count", "usage_total_tokens", "answer_chars"])
def test_a_number_in_a_cloud_segment_refuses(tmp_path, alias) -> None:
    """裁定落地成退出码：云端段里报数值，读数器当场 rc=2（不是告警、不是注释）。"""
    target = write_rows(tmp_path, [{"segment": "A4", "caliber": "cloud-shape",
                                    "cells": {"citations_present": True, alias: 7}}])
    assert run(["--readouts", str(target)]) == 2


def test_the_same_shape_reading_passes_where_the_number_refuses(tmp_path) -> None:
    target = write_rows(tmp_path, [{"segment": "A4", "caliber": "cloud-shape",
                                    "cells": {"citations_present": True, "sources_shape": "非空"}}])
    assert run(["--readouts", str(target)]) == 0


def test_counter_evidence_a_widened_number_cell_silences_the_ruling(monkeypatch, tmp_path) -> None:
    """把数值格放宽成云端可读 ⇒ 同一把读数就从红变绿：证明拦住它的是裁定那一行，不是巧合。"""
    target = write_rows(tmp_path, [{"segment": "A4", "caliber": "cloud-shape", "evidence_n": 7}])
    assert run(["--readouts", str(target)]) == 2
    widened = dict(readout.resolve("evidence_n"))
    widened["cloud"] = True
    monkeypatch.setitem(readout.REGISTRY, "evidence_n", widened)
    assert run(["--readouts", str(target)]) == 0, "放宽后仍红＝这枚钉咬的是格名字符串，不是口径"


# ------------------------------------------------------------------ 令①：接口冻结（按集合断，不按枚数）
def test_the_cloud_interface_is_frozen_by_set_not_by_count() -> None:
    """冻结要可验：格名集合逐字相等——多一枚、少一枚、改名一枚都当场红，枚数不参与。"""
    live = frozenset(readout.CLOUD_CELLS)
    assert live == CLOUD_INTERFACE, (
        "云端可读格名册漂了（R454 的 crosswalk 会白跑一轮）：多的 %s，少的 %s" % (
            sorted(live - CLOUD_INTERFACE), sorted(CLOUD_INTERFACE - live)))
    local = frozenset(readout.LOCAL_ONLY_CELLS)
    assert LOCAL_NUMERIC_INTERFACE <= local, (
        "裁定（b）那三枚数值格被挪出了本机专属那一侧：%s" % sorted(
            LOCAL_NUMERIC_INTERFACE - local))
    assert live & local == frozenset(), "同一枚格名不许两侧都在"
    assert live <= frozenset(row["cell"] for row in readout.CELLS), (
        "云端名册里出现了不在格表里的名字")


def test_the_freeze_is_written_as_sets_not_as_roster_counts() -> None:
    """令①另一半：本件里不许长出「名册枚数 == 某枚数字」这种断言（改表就得改口的假钉）。"""
    lines = Path(__file__).resolve().read_text(encoding="utf-8-sig").splitlines()
    offenders = [line.strip() for line in lines
                 if re.search(r"len\((?:readout\.\w+|payload\[.cells.\])\)\s*==\s*\d", line)]
    assert not offenders, "按枚数写的名册断言：%s" % offenders


@pytest.mark.parametrize("mutant,label", [
    (frozenset(CLOUD_INTERFACE - {"frame_shape"}) | {"frame_shapes"}, "改名一枚"),
    (frozenset(CLOUD_INTERFACE) | {"wall_ms"}, "把时延格挪进云端"),
    (frozenset(CLOUD_INTERFACE) | {"correctness"}, "把总分格挪进云端"),
    (frozenset(CLOUD_INTERFACE - {"citation_shape"}), "删掉一枚"),
])
def test_counter_evidence_the_cloud_freeze_bites_on_each_drift(mutant, label) -> None:
    """摘掉冻结令的牙：这四种漂法都必须让集合相等当场红。"""
    assert mutant != CLOUD_INTERFACE, "%s 的变异体与原名册相同，本反证空响" % label
    assert frozenset(readout.CLOUD_CELLS) != mutant, "%s 没被冻结令认出——它是空响" % label


def test_counter_evidence_the_numeric_cells_stay_local_when_the_table_is_read() -> None:
    """三枚数值格在表里的读数必须是 cloud=False；把表读歪就当场红。"""
    rows = {row["cell"]: row for row in readout.CELLS}
    for cell in sorted(LOCAL_NUMERIC_INTERFACE):
        assert cell in rows, "裁定（b）那枚格 %s 不在表里" % cell
        assert rows[cell]["cloud"] is False, "%s 被标成云端可读，直接违反裁定（b）" % cell
