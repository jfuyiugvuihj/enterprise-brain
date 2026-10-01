"""R552 的反证刀：把修好的那一格摘掉必须红；被跟踪件与在册钉按 sha256 自证一字节未动。

机械沿用 R524/R535：影子只在内存里（源文从盘上读进字符串、归一 LF、改、compile、exec 成另一枚
模块），影子源文只落 pytest 的 tmp_path 留痕，绝不写回仓内（末了总清那一格再扫一遍）；每把刀都
**先跑正控**（同一套影子机械、edits=()）必须先绿，victim 才准算被咬中；`_bite` 接 BaseException
（`Failed: DID NOT RAISE` 继承的是 BaseException，上一单就是靠这一点把「明明咬中」记成「没咬中」）。
影子模块的 ROOT 一律指回真仓：victim 里自己 set ROOT 的照旧自己设，没设的那几格（判据表）问的
必须和 shipped 模块同一套生效规则，否则红得没有道理。

四把刀（逐枚点名 victim）：
  K1 新件那一格退回「siblings 猜 blob 行尾」——今天真咬到人的那一形
     victim：test_r552_new_files_land_in_checkout_form.test_c_a_landed_new_file_is_exactly_what_checkout_would_give
  K2 把 core.autocrlf=true ⇒ crlf 那一格钝化成原样字节
     victim：…test_a_decision_equals_observed_checkout_in_every_shape
  K3 摘掉在册件「盘上那一版优先」那一格
     victim：在册钉本身 test_r531_worktree_merge_keeps_each_files_eol.test_e_a_tracked_file_keeps_the_eol_it_has_on_disk_not_the_blob
  K4 摘掉 asis 那一格（判出原样字节却硬去 normalize）
     victim：…test_d_binary_and_minus_text_new_files_land_verbatim
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

import test_r531_worktree_merge_keeps_each_files_eol as r531_nails
import test_r552_new_files_land_in_checkout_form as nails

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "scripts" / "r531_worktree_merge.py"

TRACKED = (
    TOOL,
    REPO / "tests/test_r531_worktree_merge_keeps_each_files_eol.py",
    REPO / "tests/test_r469_readout_is_generated.py",
    REPO / "tests/test_r552_new_files_land_in_checkout_form.py",
    REPO / "tests/test_r552_counter_evidence_teeth.py",
    REPO / "scripts/r455_gapdoc_coordinates.py",
    REPO / "tests/test_r547_coordinates_and_arms_are_derived.py",
    REPO / "tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py",
)

CUTS = {
    "K1": [("            conv, note = checkout_form(path, data)",
            "            conv, note = sibling_convention(path)")],
    "K2": [('        return "crlf", "检出形态=crlf（core.autocrlf=true 且无 text/eol 属性 ⇒ 检出补 CR）"',
            '        return "asis", "摘刀：autocrlf=true 那一格被钝化成原样字节"')],
    "K3": [("    if dst.is_file():", "    if False and dst.is_file():")],
    "K4": [("        out = data if asis else normalize(data, conv)",
            "        out = normalize(data, conv)")],
}

KNIVES = (
    ("K1", "test_r552_new_files_land_in_checkout_form",
     "test_c_a_landed_new_file_is_exactly_what_checkout_would_give"),
    ("K2", "test_r552_new_files_land_in_checkout_form",
     "test_a_decision_equals_observed_checkout_in_every_shape"),
    ("K3", "test_r531_worktree_merge_keeps_each_files_eol",
     "test_e_a_tracked_file_keeps_the_eol_it_has_on_disk_not_the_blob"),
    ("K4", "test_r552_new_files_land_in_checkout_form",
     "test_d_binary_and_minus_text_new_files_land_verbatim"),
)
HOSTS = {"test_r552_new_files_land_in_checkout_form": nails,
         "test_r531_worktree_merge_keeps_each_files_eol": r531_nails}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}


def _shadow(tag: str, edits, tmp_path: Path):
    """读盘上源文 → 归一 LF → 改 → compile → exec 成影子模块；盘上那枚文件一字节不动。"""
    original_lf = TOOL.read_bytes().decode("utf-8").replace("\r\n", "\n")
    shadow = original_lf
    for old, new in edits:
        hits = shadow.count(old)
        assert hits == 1, tag + "：锚点命中 " + str(hits) + " 次（要恰好一次）"
        shadow = shadow.replace(old, new, 1)
    if edits:
        assert shadow != original_lf, tag + "：改了个寂寞"
    assert "\r" not in shadow, tag + "：影子里混进裸 CR"
    leave = tmp_path / ("r552_shadow_" + tag + ".py")
    leave.write_bytes(shadow.encode("utf-8"))
    name = "r552_shadow_" + tag
    module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(name, str(leave)))
    sys.modules[name] = module
    exec(compile(shadow, str(leave), "exec"), module.__dict__)
    module.ROOT = REPO  # 影子问 git 的那枚仓，必须和 shipped 模块是同一枚
    return module


def _bite(victim, host_module, shadow, tmp_path: Path, tag: str):
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(host_module, "merger", shadow)
        scratch = tmp_path / ("run_" + tag)
        scratch.mkdir(parents=True, exist_ok=True)
        code = victim.__code__
        args = []
        for name in code.co_varnames[:code.co_argcount]:
            if name == "tmp_path":
                args.append(scratch)
            elif name == "monkeypatch":
                args.append(mp)
            else:
                raise AssertionError(tag + "：victim 需要没给的夹具 " + name)
        try:
            victim(*args)
        except BaseException as exc:  # noqa: BLE001 - Failed 继承的是 BaseException
            return exc
        return None
    finally:
        mp.undo()


def _pair(tag, tmp_path):
    """同一把刀跑两遍并自报读数：正控必须先绿，摘刀必须红，逐把再复验被跟踪件字节。"""
    host_name, victim_name = [(h, v) for k, h, v in KNIVES if k == tag][0]
    host_module = HOSTS[host_name]
    victim = getattr(host_module, victim_name)
    tool_before = _sha(TOOL)
    pos = _bite(victim, host_module, _shadow(tag + "pos", (), tmp_path), tmp_path, tag + "pos")
    assert pos is None, tag + "：正控（不摘刀）就红，这刀的结论不可用 —— " + repr(pos)
    red = _bite(victim, host_module, _shadow(tag, CUTS[tag], tmp_path), tmp_path, tag)
    assert red is not None, tag + "：没咬中——摘掉这一格，victim 还绿着"
    moved = [str(path.relative_to(REPO)) for path in TRACKED
             if _sha(path) != FINGERPRINT_AT_IMPORT[path]]
    assert not moved, tag + "：摘刀把盘上件改动了：" + ", ".join(moved)
    assert _sha(TOOL) == tool_before, tag + "：工具件被改动"
    head = (str(red).splitlines() or [""])[0][:96]
    print("KNIFE " + tag + " | 正控=绿 | victim=" + host_name + "." + victim_name
          + " | 摘刀=红(" + type(red).__name__ + "): " + head
          + " | sha复验=" + str(len(TRACKED)) + "/" + str(len(TRACKED)) + " 等值 | 工具=" + tool_before[:16])
    return True


def test_k1_the_siblings_guess_is_what_this_ticket_fixed(tmp_path):
    assert _pair("K1", tmp_path)


def test_k2_the_autocrlf_rung_is_load_bearing(tmp_path):
    assert _pair("K2", tmp_path)


def test_k3_the_disk_form_rung_for_tracked_files_still_wins(tmp_path):
    assert _pair("K3", tmp_path)


def test_k4_the_verbatim_rung_is_load_bearing(tmp_path):
    assert _pair("K4", tmp_path)


def test_z5_the_ledger_names_every_knife_and_every_victim():
    assert set(CUTS) == {tag for tag, _h, _v in KNIVES}, "台账与摘刀表不一致"
    collected = {name for name in globals() if name.startswith("test_k")}
    for tag, host_name, victim_name in KNIVES:
        host_module = HOSTS[host_name]
        assert hasattr(host_module, victim_name), victim_name + " 不在 " + host_name
        assert callable(getattr(host_module, victim_name)), victim_name
        assert any(n.lower().startswith("test_k" + tag[1:] + "_") for n in collected), tag
    assert any(host_name == "test_r531_worktree_merge_keeps_each_files_eol"
               for _t, host_name, _v in KNIVES), "至少一把刀的 victim 必须是在册钉本身"


def test_z6_the_tracked_files_are_byte_for_byte_untouched():
    moved = [str(path.relative_to(REPO)) for path in TRACKED if _sha(path) != FINGERPRINT_AT_IMPORT[path]]
    assert not moved, "被跟踪件被改动了：" + ", ".join(moved)
    strays = []
    for folder in (REPO, REPO / "tests", REPO / "scripts", REPO / "app"):
        if folder.is_dir():
            strays += list(folder.glob("r552_shadow_*.py"))
    assert not strays, "仓里落下了影子件：" + ", ".join(str(s) for s in strays)
