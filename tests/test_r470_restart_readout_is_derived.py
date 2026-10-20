# -*- coding: utf-8 -*-
"""R470 · 重启演练读数必须由生成件出，且那把「只许 audit_events 长」的尺子真有牙。

为什么单独钉「生成」这件事（在册同族先例：tests/test_r454_readout_is_generated.py、
tests/test_r469_readout_is_generated.py）：本单交回的是一张「重启前后哪些数没变」的表，手写它
就会带上抄上一班的惯性；而这一格的价值全在「别的表一枚都不许动」那一句上——它一旦被谁手改成
"全等"，缺陷就被盖住了。所以盘上那段表必须与 render_readout() 逐字节相同，且四把反证刀各咬一处。

全程离线：只读 docs/perf/raw/r470-2026-09-29/ 那六份落盘读数，变异一律造在 tmp_path 的副本上，
零库、零容器、零模型，被跟踪文件一个字都不改（事故 #71 的入规）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "r470_restart_diff.py"
RAW_DIR = REPO_ROOT / "docs" / "perf" / "raw" / "r470-2026-09-29"
DOC_PATH = REPO_ROOT / "docs" / "testing" / "r470-restart-drill-2026-09-29.md"


def _mod():
    spec = importlib.util.spec_from_file_location("r470_diff", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _mod()


def _raw_copy(tmp_path):
    dst = tmp_path / "raw"
    dst.mkdir()
    for src in sorted(RAW_DIR.glob("*.json")):
        (dst / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _edit(dir_path, name, mutate):
    payload = json.loads((dir_path / name).read_text(encoding="utf-8"))
    mutate(payload)
    (dir_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# 甲 · 现场读数：这一格真的通过了，而且只有审计面在长


def test_both_forms_pass_and_only_audit_grew():
    report = M.run(RAW_DIR)
    assert M.validate(report) == [], M.validate(report)
    for form in ("stop_start", "force_recreate"):
        block = report[form]
        assert block["changed_tables"] == ["audit_events"], block["changed_tables"]
        assert block["grew"] == {"audit_events": 3}, block["grew"]
        assert block["shrank"] == {}
        assert block["pk_changed"] == []
        assert block["files_equal"] is True
    assert report["api"]["all_equal"] is True
    assert [n for _, n in report["api"]["readings"]] == [656, 656, 656]


def test_the_readout_dir_carries_six_raw_files():
    names = sorted(p.name for p in RAW_DIR.glob("*.json"))
    assert len(names) == 6, names
    assert set(names) == {M.BEFORE, M.AFTER_STOP_START, M.AFTER_RECREATE} | set(M.API_FILES)


# 乙 · 盘上那段表 == 再生件（逐字节，不是「差不多」）


def test_in_tree_table_is_byte_for_byte_what_the_lib_renders():
    doc = DOC_PATH.read_text(encoding="utf-8")
    assert doc.count(M.BEGIN) == 1, "BEGIN 哨兵必须恰好一枚"
    assert doc.count(M.END) == 1, (
        "END 哨兵必须恰好一枚——少了它就是 --sync 把生成表甩进正文，本单实测踩过：sync 成功之后"
        " check 反过来说「文档里没有哨兵区」。这一格就是钉那个 bug 的。"
    )
    body = doc.split(M.BEGIN, 1)[1].split(M.END, 1)[0].strip()
    assert body == M.render_readout(M.run(RAW_DIR), []).strip()


# 丙丁戊己 · 四把反证刀：尺子不许把缺陷读成通过


def test_blade_a_foreign_table_growth_is_refused(tmp_path):
    dir_path = _raw_copy(tmp_path)
    _edit(dir_path, M.AFTER_STOP_START,
          lambda p: p["db"]["artifacts"].__setitem__("rows", p["db"]["artifacts"]["rows"] + 1))
    problems = M.validate(M.run(dir_path))
    assert any("artifacts" in x for x in problems), problems


def test_blade_b_audit_shrink_is_refused(tmp_path):
    # 刀要造的是「重启后审计面比基线还少」——所以减的是基线那一枚数，不是 after 自己的数：
    # 基线 2426 / after 2429，只把 after 减到 2428 仍是增长，尺子不报才是对的（本单第一版就这么空转过）。
    dir_path = _raw_copy(tmp_path)
    base = json.loads((RAW_DIR / M.BEFORE).read_text(encoding="utf-8"))["db"]["audit_events"]["rows"]
    _edit(dir_path, M.AFTER_RECREATE,
          lambda p: p["db"]["audit_events"].__setitem__("rows", base - 1))
    problems = M.validate(M.run(dir_path))
    assert any("audit_events" in x and "少了" in x for x in problems), problems


def test_blade_c_session_leg_divergence_is_refused(tmp_path):
    dir_path = _raw_copy(tmp_path)
    _edit(dir_path, "api-after-force-recreate.json", lambda p: p["sessions"].__setitem__("n", 655))
    problems = M.validate(M.run(dir_path))
    assert any("会话读腿" in x for x in problems), problems


def test_blade_d_lost_table_is_refused(tmp_path):
    dir_path = _raw_copy(tmp_path)
    _edit(dir_path, M.AFTER_STOP_START, lambda p: p["db"].pop("sessions"))
    problems = M.validate(M.run(dir_path))
    assert any("sessions" in x for x in problems), problems


# 庚 · 白名单只有一枚，谁也不许偷偷加宽它


def test_the_allowed_growth_whitelist_is_exactly_audit_events():
    assert M.ALLOWED_GROWTH == frozenset({"audit_events"}), sorted(M.ALLOWED_GROWTH)


def test_sync_shape_is_idempotent_on_a_temp_copy(tmp_path):
    table = M.render_readout(M.run(RAW_DIR), [])
    doc = DOC_PATH.read_text(encoding="utf-8")
    head, rest = doc.split(M.BEGIN, 1)
    _old, tail = rest.split(M.END, 1)
    out = tmp_path / "doc.md"
    for _ in range(2):
        out.write_text(head + M.BEGIN + chr(10) + table.rstrip(chr(10)) + chr(10) + M.END + chr(10) + tail,
                       encoding="utf-8", newline=chr(10))
    after = out.read_text(encoding="utf-8")
    assert after.count(M.END) == 1, "sync 两遍之后 END 还得在"
    assert after.split(M.BEGIN, 1)[1].split(M.END, 1)[0].strip() == table.strip()

