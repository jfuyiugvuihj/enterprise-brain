"""R682 · KPI 量具自己的牙（全离线，只用 ``ast``／``re``／``pathlib``，不 import ``app``）。

判据第 3 条点名的三枚：
  (a) 缺列即红 —— 少一枚量具，报告必须当场点名并判红；
  (b) 造数即红 —— 把 ② 写成常量的桩必须被点名（复算不等、出处找不到、无出处、NOT_MEASURED 里夹数字，四种形状都炸）；
  (c) 分母为零 —— 不许打印百分比，只许打 ``NOT_MEASURED``。

另加自守的两枚：本尺不 import ``app``、源码里一枚 ``文件:数字`` 坐标都不许有；
外加一枚**正控**，证明 ② 的 MEASURED 分支不是死码（拿账面里真在的那枚门读数喂它）。
"""

import ast
import importlib.util
import re
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RULER = REPO / "scripts" / "meta_health.py"

COLUMN_KEYS = (
    "product_face",
    "validation_wallclock",
    "ledger_bytes",
    "merges_per_day",
    "markdown_share",
)
ALLOWED_TOP_LEVEL_IMPORTS = {
    "__future__",
    "argparse",
    "ast",
    "dataclasses",
    "datetime",
    "pathlib",
    "re",
    "subprocess",
    "sys",
    "time",
    "typing",
    "warnings",
}


def _load_ruler():
    spec = importlib.util.spec_from_file_location("r682_meta_health_under_test", RULER)
    assert spec is not None and spec.loader is not None, f"{RULER.name} 加载不了"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ruler():
    return _load_ruler()


@pytest.fixture(scope="module")
def real_run(ruler):
    """现跑整把尺（含验伪复算），秒数按 ``elapsed`` 口径交回。"""
    started = time.perf_counter()
    readings = ruler.build_readings(ruler.REPO)
    lines, exit_code = ruler.render_report(
        readings,
        repo=ruler.REPO,
        head=ruler._head_sha(ruler.REPO),
        generated_at="static-for-test",
        elapsed=lambda: time.perf_counter() - started,
    )
    return {"lines": lines, "text": "\n".join(lines), "exit": exit_code, "readings": readings}


def _stub(ruler, key, values, **kwargs):
    coordinates = kwargs.pop("coordinates", ("fs::stub_probe",))
    excerpts = kwargs.pop("excerpts", ("stub excerpt",))
    kind = kwargs.pop("kind", "fs")
    recheck = kwargs.pop("recheck", None)
    return ruler.Reading(
        key=key,
        label=f"stub::{key}",
        values=dict(values),
        provenance=ruler.Provenance(
            kind=kind,
            coordinates=tuple(coordinates),
            excerpts=tuple(excerpts),
            recheck=recheck if recheck is not None else (lambda: dict(values)),
        ),
        status=kwargs.pop("status", ruler.MEASURED),
        reason=kwargs.pop("reason", ""),
    )


def _full_set(ruler, **overrides):
    readings = {key: _stub(ruler, key, {"marker": "1"}) for key in COLUMN_KEYS}
    for key, reading in overrides.items():
        assert key in readings, f"越权列名 {key}"
        readings[key] = reading
    return readings


def _render(ruler, readings):
    lines, exit_code = ruler.render_report(
        readings,
        repo=REPO,
        head="0" * 40,
        generated_at="static-for-test",
        elapsed=lambda: 0.0,
    )
    return "\n".join(lines), exit_code, lines


def _row_for(lines, index):
    return next(line for line in lines if line.startswith(f"[{index}/5]"))


# ==================== 判据 3(a) 缺列即红 ====================

def test_a_missing_column_is_red_and_names_the_column(ruler):
    """少一枚量具就判负，且要点名是哪一枚——四数一红线是「缺一枚判负」。"""
    readings = _full_set(ruler)
    del readings["merges_per_day"]
    text, exit_code, lines = _render(ruler, readings)

    assert exit_code == ruler.EXIT_RED
    assert "MISSING_COLUMN::merges_per_day" in text
    assert "= RED :: MISSING_COLUMN::merges_per_day" in _row_for(lines, 4)
    assert "[1/5]" in text and "[2/5]" in text and "[3/5]" in text and "[5/5]" in text
    assert any(line.startswith("merges_per_day.status=MISSING_COLUMN") for line in lines)


def test_an_undeclared_column_is_also_red(ruler):
    """多出来的列同样判负——账面只许长回这四数一红线那五枚。"""
    readings = _full_set(ruler)
    readings["lines_of_prose_per_shift"] = _stub(ruler, "lines_of_prose_per_shift", {"marker": "9"})
    text, exit_code, _lines = _render(ruler, readings)

    assert exit_code == ruler.EXIT_RED
    assert "UNDECLARED_COLUMN::lines_of_prose_per_shift" in text


# ==================== 判据 3(b) 造数即红 ====================

def test_b_hardcoded_wallclock_constant_is_named_and_rejected(ruler):
    """把 ② 写成常量：复算不等＋出处找不到＋列名点名，三条一起炸。"""
    stub = _stub(
        ruler,
        "validation_wallclock",
        {"wallclock_s": "507.9", "passed": "8479"},
        kind="doc",
        coordinates=("docs/testing/r660-gate-reanchor-2026-10-05.md::gate_readings",),
        excerpts=("这枚 507.9 s exit=0 是手抄的假账",),
        recheck=lambda: {"wallclock_s": "1.0", "passed": "1"},
    )
    text, exit_code, lines = _render(ruler, _full_set(ruler, validation_wallclock=stub))
    row = _row_for(lines, 2)

    assert exit_code == ruler.EXIT_RED
    assert "validation_wallclock = RED" in row
    assert "DRIFT::validation_wallclock.wallclock_s::507.9!=1.0" in row
    assert "EXCERPT_NOT_IN_CITED_FILE" in row
    assert "wallclock_s=507.9" not in row.split("RED")[0]


def test_a_constant_without_provenance_is_rejected(ruler):
    """无出处的读数连资格都没有：点名 UNPROVEN_READING。"""
    unproven = ruler.Reading(
        key="validation_wallclock",
        label="② 验证墙钟",
        values={"wallclock_s": "507.9"},
        provenance=None,
    )
    text, exit_code, _lines = _render(ruler, _full_set(ruler, validation_wallclock=unproven))

    assert exit_code == ruler.EXIT_RED
    assert "UNPROVEN_READING::validation_wallclock" in text


def test_not_measured_row_cannot_smuggle_numbers(ruler):
    """写着 NOT_MEASURED 却夹了数字＝造数的第二种形状，同样点名。"""
    smuggled = ruler.Reading(
        key="validation_wallclock",
        label="② 验证墙钟",
        values={"wallclock_s": "507.9", "passed": "8479"},
        status=ruler.NOT_MEASURED,
        reason="NO_SAME_HEAD_RERUN",
    )
    text, exit_code, _lines = _render(ruler, _full_set(ruler, validation_wallclock=smuggled))

    assert exit_code == ruler.EXIT_RED
    assert "NUMBERS_UNDER_NOT_MEASURED::validation_wallclock" in text


def test_unreasoned_not_measured_is_red(ruler):
    """空手报「没量到」却不写为什么，同样判负——不许留空。"""
    blank = ruler.Reading(
        key="validation_wallclock",
        label="② 验证墙钟",
        values={"wallclock_s": ruler.NOT_MEASURED},
        status=ruler.NOT_MEASURED,
        reason="",
    )
    text, exit_code, _lines = _render(ruler, _full_set(ruler, validation_wallclock=blank))

    assert exit_code == ruler.EXIT_RED
    assert "UNREASONED_NOT_MEASURED::validation_wallclock" in text


# ==================== 判据 3(c) 分母为零 ====================

def test_c_zero_denominator_prints_not_measured_and_no_percent(ruler):
    """分母为零时分子分母都不许变成百分比——只许打 NOT_MEASURED，一枚 % 都不许出现。"""
    counts = ruler.ShareCounts(
        denominator=0, direct_numerator=0, helper_numerator=0, upper_bound_numerator=0
    )
    reading = ruler.build_share_reading(
        counts,
        coordinates=("ast::tests_markdown_reader_scan",),
        excerpts=("stub excerpt",),
        recheck=lambda: {},
    )
    assert reading.status == ruler.NOT_MEASURED
    assert reading.reason.startswith("ZERO_DENOMINATOR")
    assert set(reading.values.values()) == {ruler.NOT_MEASURED}

    text, exit_code, lines = _render(ruler, _full_set(ruler, markdown_share=reading))
    row = _row_for(lines, 5)
    kv = [line for line in lines if line.startswith("markdown_share.")]

    assert ruler.NOT_MEASURED in row
    assert "%" not in row
    assert not any("%" in line for line in kv)
    assert exit_code == ruler.EXIT_GREEN
    assert "markdown_share.status=NOT_MEASURED" in text


def test_a_measured_share_does_print_percent(ruler):
    """分母在位时正面走一遍：分子分母同栏，百分比照打。"""
    counts = ruler.ShareCounts(
        denominator=200, direct_numerator=40, helper_numerator=60, upper_bound_numerator=90
    )
    reading = ruler.build_share_reading(
        counts,
        coordinates=("ast::tests_markdown_reader_scan",),
        excerpts=("stub excerpt",),
        recheck=lambda: dict(reading.values),
    )
    _text, exit_code, lines = _render(ruler, _full_set(ruler, markdown_share=reading))
    row = _row_for(lines, 5)

    assert exit_code == ruler.EXIT_GREEN
    assert "direct_numerator=40" in row
    assert "denominator=200" in row
    assert "direct_percent=20.00%" in row


# ==================== 正控：② 的 MEASURED 分支不是死码 ====================

def test_wallclock_positive_path_reads_a_real_ledger_record(ruler):
    """拿账面里真在的那枚门读数当同 HEAD 复跑——MEASURED 那支必须能过验伪。"""
    files = ruler._gate_doc_files(ruler.REPO)
    records = ruler._gate_records(files, ruler.REPO)
    known = ruler._known_commits(
        ruler.REPO, [sha for record in records for sha in ruler._record_shas(record)]
    )
    live = [record for record in records if ruler._record_is_real(record, known)]
    assert live, "docs/testing 与看板里一枚带真 sha 的门读数都没有"
    record = live[-1]
    head = ruler._record_shas(record)[0]
    collected = {
        "files": files,
        "records": records,
        "live": live,
        "same_head": [record],
        "head": [head],
    }
    reading = ruler.assemble_wallclock_reading(
        collected, recheck=lambda: ruler.wallclock_values(collected)
    )

    assert reading.status == ruler.MEASURED
    assert reading.values["wallclock_s"] == record["wallclock_s"]
    assert reading.values["rerun_sha"] == head
    assert ruler.verify_reading(ruler.REPO, reading) == []


# ==================== 判据 2 的形状自守 ====================

def test_ruler_is_offline_and_holds_no_line_coordinates():
    """本尺零 import ``app``、零联网库，且源码里一枚 ``文件:数字`` 坐标都不许有。"""
    source = RULER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "app" not in imported
    assert imported <= ALLOWED_TOP_LEVEL_IMPORTS, f"越界依赖：{sorted(imported - ALLOWED_TOP_LEVEL_IMPORTS)}"
    ruler_module = _load_ruler()
    assert ruler_module.LINE_COORDINATE.search(source) is None


# ==================== 整把尺现跑 ====================

def test_real_run_is_green_and_within_sixty_seconds(ruler, real_run):
    lines = real_run["lines"]
    rows = [line for line in lines if re.match(r"^\[\d/5\]", line)]

    assert real_run["exit"] == ruler.EXIT_GREEN, "\n".join(lines)
    assert len(rows) == len(COLUMN_KEYS)
    assert all("出处" in row for row in rows)
    header = next(line for line in lines if "self_runtime_s=" in line)
    runtime = float(header.split("self_runtime_s=")[1].split()[0])
    assert runtime <= ruler.SELF_RUNTIME_LIMIT_S, f"整把尺跑了 {runtime} s，超线"
    assert lines[-1] == "GREEN"


def test_machine_rows_cover_every_field(ruler, real_run):
    lines = real_run["lines"]
    kv = {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("[")}

    for key in COLUMN_KEYS:
        assert f"{key}.status" in kv, f"{key} 没有机器可读行"
        reading = real_run["readings"][key]
        for field in reading.values:
            assert f"{key}.{field}" in kv, f"{key}.{field} 没落进对账行"
    for meta_key in ("meta.schema", "meta.head", "meta.self_runtime_s", "meta.exit"):
        assert meta_key in kv


def test_wallclock_is_either_same_head_or_not_measured(ruler, real_run):
    """现跑的 ② 只能是两种形状之一，且不许有第三种含糊写法。"""
    reading = real_run["readings"]["validation_wallclock"]
    head = ruler._head_sha(ruler.REPO)

    if reading.status == ruler.MEASURED:
        assert head.startswith(reading.values["rerun_sha"])
        assert float(reading.values["wallclock_s"]) > 0
    else:
        assert reading.status == ruler.NOT_MEASURED
        assert reading.reason.startswith("NO_SAME_HEAD_RERUN")
        assert set(reading.values.values()) == {ruler.NOT_MEASURED}


def test_redline_carries_numerator_and_denominator(ruler, real_run):
    """红线那一枚必须同时交出分子与分母——只给百分比不给分母就是假账。"""
    reading = real_run["readings"]["markdown_share"]

    if reading.status == ruler.MEASURED:
        assert int(reading.values["denominator"]) > 0
        assert int(reading.values["direct_numerator"]) <= int(reading.values["denominator"])
        assert reading.values["direct_percent"].endswith("%")
    else:
        assert reading.reason.startswith("ZERO_DENOMINATOR")
        assert "%" not in " ".join(reading.values.values())
