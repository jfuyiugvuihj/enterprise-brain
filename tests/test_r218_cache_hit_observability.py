# -*- coding: utf-8 -*-
"""R218 判据 ②-C（三格之二）+ 判据 ④ 反证钉：缓存命中腿在采集器里可不可观测。

对判据的哪一条：单号 R218 判据 ② 第二格 —— 离线用同一题打两遍，第二遍必须能读出
「这一发是命中腿」；读不出来就当场写清不可测（判据 ③），不许假装绿。

形状：四种腿（两枚证词都在 / 只在帧上 / 只在 status 文案上 / 冷腿）各读一次；
反证把产品那句命中文案改掉（不再含「缓存命中」）⇒ 采集器读不到第二遍 ⇒ 本格变红。
🔴 反证只加不减：既有断言一枚不删、不放宽。
"""
import hashlib
import importlib.util
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _rehearsal():
    spec = importlib.util.spec_from_file_location(
        "r218_switch_rehearsal_mod", REPO / "scripts" / "r218_switch_rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _rehearsal()

PIN_FILES = R.rehearsal_inputs()  # 由 _CITATIONS 与三格读取点长出，不手抄


def _tree_sha() -> dict:
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in PIN_FILES}


def _overlay(tmp_path: Path) -> Path:
    root = tmp_path / "overlay"
    for rel in PIN_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    return root


def test_hit_leg_is_observable_on_both_marker_paths():
    """判据 ②-C 的正例：第二遍那一发读得出「是命中腿」，冷腿不许误报。"""
    adapter = R._load_adapter(REPO)
    chat = R._load_chat()
    literal = R.hit_leg_literals(REPO)
    assert literal["detects_status_literal"] is True
    assert literal["cache_field_keys"] == ["cache_generated_at", "cache_note", "cached"]
    observed = R.cache_leg_observations(adapter, chat, literal)
    assert observed == {"both_markers": True, "frame_only": True,
                        "status_only": True, "cold_leg": False}


def test_cell_reports_observable_and_the_unmeasurable_part_by_name():
    cell = R.cell_cache_hit(REPO)
    assert cell["verdict"] == R.GREEN, cell["problems"]
    assert cell["readings"]["mismatched_legs"] == []
    markers = cell["readings"]["answer_record_keys"]
    # 🔴 可观测 ≠ 可标注：answers/sidecar 里没有命中那一列，命中在 transport 里是硬抛停整 shard。
    # 所以「缓存命中显式标注」这一格在报告里读不出来 —— 本格把它写成 NOT_COVERED 而不是绿。
    assert markers["hit_marker_in_payload"] is False
    assert markers["hit_marker_in_sidecar"] is False
    assert any("显式标注" in item for item in cell["not_covered_offline"])
    assert any("真 Redis" in item for item in cell["not_covered_offline"])


def test_counter_proof_renaming_the_hit_copywrites_goes_red_here(tmp_path):
    """反证钉（判据 ④）：产品把命中文案改到不含「缓存命中」⇒ 采集器读不到命中腿 ⇒ 本格红。"""
    overlay = _overlay(tmp_path)
    chat_py = overlay / "app/api/v1/chat.py"
    original = chat_py.read_text(encoding="utf-8")
    mutated = original.replace("'content': '📋 缓存命中，直接返回'", "'content': '📋 已复用先前结果'")
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    chat_py.write_text(mutated, encoding="utf-8")

    before = _tree_sha()
    cell = R.cell_cache_hit(overlay)
    assert cell["verdict"] == R.RED
    assert any(p.startswith("hit_leg_literals_drift") for p in cell["problems"])
    # 红必须落在本格的判定链上（status 文案是两枚证词之一 ⇒ 只靠它的那条腿也一起读不到）
    assert cell["readings"]["collector_reads_hit_leg"]["status_only"] is False
    assert "status_only" in cell["readings"]["mismatched_legs"]

    # 另两格不许顺手拦住这枚钉
    assert R.cell_lane_flip(overlay)["readings"]["lane_flip"]["flip_on"] is True
    assert R.cell_ruler(overlay)["readings"]["unparsed_shapes"] == []

    shutil.rmtree(tmp_path)
    assert _tree_sha() == before
    assert (REPO / "app/api/v1/chat.py").read_text(encoding="utf-8") == original
