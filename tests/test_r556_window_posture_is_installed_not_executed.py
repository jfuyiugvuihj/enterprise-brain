r"""R556 的进度尺之二：在册窗的姿势必须是「装进去的」，不是「exec 出来的」。

为什么还要第二枚钉（`tests/test_r466_...` 已有一枚名册钉）：那枚只认**它自己那张 `WINDOWS` 表**——
有人在表外新开一扇 `execs_module = True` 的窗，它一辈子看不见（本仓教训原话：「没这条，八枚影子窗
一辈子没被量过」）。本件换一把尺子：**全 `tests/` 逐枚 AST 扫赋值**，把「此刻还有谁在 exec 活模块」
钉成一枚闭合名单。名单之外多一枚 ⇒ 红（反弹即红）；名单里少一枚而码还开着 ⇒ 同样红。

判据出处＝跟进单 §141 第三节 R556 判据③ 与 ④。两枚界外窗今天仍在案、且**明写不许迁**：
`test_r482_registered_ceiling_is_the_ceiling.py::_ClampEdit`（越界不迁，坐标交回）、
`test_r553_counter_evidence_teeth.py::_Probe`（它量的就是 exec 姿势本身，迁了就没牙）。
豁免只登记这两枚，别的一律算新罪。

尺子必须是 AST 而不是字样：`tests/` 里「旧姿势是 ``execs_module = True``」这类**散文**有九处
（r303/r310/r337/r353/r354/r373/r381/r388/r466 的 docstring），拿正则扫全文会把它们全数成窗，
豁免名单当场被撑爆——那正是判据④ 要防的「刀迁成空转」的另一种形状。
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

#: 今天在册的两枚界外 exec 窗，逐枚点名。（文件名, 类名）
EXEC_WINDOWS_ALLOWED = {
    ("test_r482_registered_ceiling_is_the_ceiling.py", "_ClampEdit"),
    ("test_r553_counter_evidence_teeth.py", "_Probe"),
}

#: 本单迁完的四扇（r472 两件共用一扇另计）：它们现在只准「装绑定」，不准 exec 活模块。
MIGRATED_FILES = (
    "test_r472_h13_closed_wording.py",
    "test_r478_no_closed_gate_as_placeholder.py",
    "test_r48_headline_card_lands_on_the_wire.py",
    "test_r495_session_owner_namespace_is_declared.py",
)


def _exec_module_classes(path: Path) -> set:
    """这枚件里**真的**把 execs_module 赋成 True 的类名。只认类体内的赋值语句，不认注释与 docstring。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "execs_module":
                    if isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                        found.add(node.name)
    return found


def _scan_repo() -> set:
    out = set()
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        for cls in _exec_module_classes(path):
            out.add((path.name, cls))
    return out


def test_the_closed_list_is_exactly_the_two_out_of_scope_windows():
    """全仓现扫：还在 exec 活模块的窗，名单必须闭合。"""
    live = _scan_repo()
    extra = sorted(live - EXEC_WINDOWS_ALLOWED)
    gone = sorted(EXEC_WINDOWS_ALLOWED - live)
    assert not extra, (
        "R556 之后只准 r482::_ClampEdit 与 r553::_Probe 两枚还开着 execs_module；"
        "现在多出 %d 枚：%s —— 要么把它迁进 install_mutation，要么明写越界并由总控登记，不许静默多开"
        % (len(extra), extra)
    )
    assert not gone, "豁免名单里有 %s 已经不在盘上了：删登记，别留一枚空豁免" % (gone,)


def test_migrated_files_install_bindings_instead_of_executing_the_live_module():
    """四扇迁完的姿势：类体里不许再有 execs_module=True，且必须真用上新的那把把手。"""
    for name in MIGRATED_FILES:
        path = TESTS_DIR / name
        assert path.is_file(), "本单写域里的 %s 不见了" % name
        assert not _exec_module_classes(path), (
            "%s 仍有一枚类把 execs_module 赋成 True——这扇没迁完" % name
        )
        text = path.read_text(encoding="utf-8")
        used = ("install_mutation" in text) or ("isolated_module" in text)
        assert used, (
            "%s 既没 exec 整片码体、也没用 install_mutation/isolated_module 装绑定，"
            "那是把变异迁成了空转刀（判据④），比不迁更坏" % name
        )


def test_the_scanner_sees_a_real_assignment_and_ignores_prose():
    """反证①：把真赋值写进临时件必须被咬；只把同一句话写进 docstring 必须不被咬。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        real = root / "test_zz_real_window.py"
        real.write_text(
            "import ast\n\n\n"
            "class _FakeEdit:\n"
            "    execs_module = True\n\n\n"
            'def test_x():\n    assert True\n',
            encoding="utf-8",
        )
        prose = root / "test_zz_prose_only.py"
        prose.write_text(
            '"""旧姿势是 execs_module = True，本件已迁完。"""\n\n\n'
            "class _QuietEdit:\n"
            "    execs_module = False\n\n\n"
            'def test_y():\n    assert True\n',
            encoding="utf-8",
        )
        hit_real = {p.name for p in (real,) if _exec_module_classes(p)}
        hit_prose = _exec_module_classes(prose)
    assert hit_real == {"test_zz_real_window.py"}, "尺子不认真赋值＝整枚钉是摆设"
    assert hit_prose == set(), "尺子把 docstring 里的字样当成窗＝豁免名单会被散文撑爆"


def test_the_allow_list_is_not_a_funny_number():
    """反证②：豁免必须恰为两枚。有人往名单里加第三枚又想同时不删码，本件与上一格同时红。"""
    assert len(EXEC_WINDOWS_ALLOWED) == 2, (
        "豁免名单被改动过（现取 %d 枚）。加豁免必须同时有越界理由与总控登记，不许在这儿顺手加"
        % len(EXEC_WINDOWS_ALLOWED)
    )
    assert _scan_repo() == EXEC_WINDOWS_ALLOWED, "现扫与豁免不一致，逐枚看上一格的原证"