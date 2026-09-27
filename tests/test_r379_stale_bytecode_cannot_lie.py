# -*- coding: utf-8 -*-
r"""R379 格四：``scripts/__pycache__`` 里那枚过期 .pyc 不许再有机会替现场说话。

事由：R361 施工方一手复现过——现场文本是 ``VALUE = 2``，``spec.loader.exec_module`` 读回来是
``1``。Windows 的 mtime 只到秒，反证刀改版前后又常常同尺寸，于是过期字节码能通过 pyc 头里那
(mtime, size) 两项校验。任何 ``from scripts.rehearse_eval_window import …`` 的钉子都走这条路：
刀版本能被还成假绿，干净文件也能被读成假红。本件的修法只有一种——**现读源文本 compile**。

四格：
  ① 机制取证（合成小模块，两个加载器同场对跑）：``compile()`` 读到新值、``exec_module`` 读到
     旧值。🔴 本件的判定断言一律站在 ``compile()`` 那一侧——谁把 ``load_script`` 换回
     ``exec_module``，①与②当场红。
  ② 真件取证：把预演件本体复制进 tmp、按它自己写出 pyc、再以同尺寸改文本 + 还原 mtime，
     证明那枚缓存"今天确实会被解释器接受"，而缓存里的常量是旧的那一枚。
  ③ 全仓点名：扫出所有引用这枚预演件的件，逐件分类它怎么加载；走字节码缓存的一律红
     （写域外的登记在 ALLOWED 里，只报不改，随写域收敛而自动失效）。
  ④ 预演件自己去读 R94 常驻件时也不许走缓存（同一族雷，就在本件里，已按现读改）。
"""
from __future__ import annotations

import ast
import importlib.util
import marshal
import os
import py_compile
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/rehearse_eval_window.py"
RULER_NAMES = ("rehearse_eval_window",)

#: 🔴 只准缩不许涨：这些件在字节码缓存上读预演件，写域归别人（见交回单"只报不改"）。
#: R378 Helmholtz 正在 tests/test_r218_egress_gate_placement.py 施工，本单一枚都不碰它。
ALLOWED_STALE_LOADERS = {"tests/test_r218_egress_gate_placement.py"}


def load_by_source_text(module_name: str, path: Path):
    """现场派生的加载法：读文本 -> compile -> exec。判定站在这一侧。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(Path(path).read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


def load_by_bytecode_cache(module_name: str, path: Path):
    """被禁的那条路：它先认 __pycache__。本件留着它只为把陷阱跑给人看。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def all_consts(code):
    for item in code.co_consts:
        if isinstance(item, type(code)):
            yield from all_consts(item)
        else:
            yield item


def hold_mtime(path: Path):
    stat = path.stat()
    return stat.st_mtime


def restore_mtime(path: Path, stamp) -> None:
    os.utime(path, (stamp, stamp))


# ==================== ① 机制：缓存能赢过盘上文本，而 compile 不会 ====================


def test_a_same_size_edit_with_the_clock_put_back_fools_the_cache(tmp_path):
    """一手复现 R361 报的那件事：文本已经是 2，exec_module 仍交回 1。"""
    source = tmp_path / "probe_value.py"
    source.write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    stamp = hold_mtime(source)
    assert load_by_bytecode_cache("r379_probe_first", source).VALUE == 1
    pyc = Path(importlib.util.cache_from_source(str(source)))
    assert pyc.is_file(), "解释器没写出字节码缓存，这枚陷阱不成立（那要重新取证）"
    # 同尺寸改文本 + 把 mtime 还原到缓存记账的那一秒：校验项 (mtime, size) 双双对上
    source.write_text("VALUE = 2\n", encoding="utf-8", newline="\n")
    restore_mtime(source, stamp)
    header = pyc.read_bytes()[:16]
    cached_mtime, cached_size = int.from_bytes(header[8:12], "little"), int.from_bytes(header[12:16], "little")
    stat = source.stat()
    assert cached_mtime == int(stat.st_mtime) and cached_size == stat.st_size, (
        f"缓存校验项已经不等了（{cached_mtime}/{cached_size} vs "
        f"{int(stat.st_mtime)}/{stat.st_size}）：这枚刀今天不钝，重取证据")
    stale = load_by_bytecode_cache("r379_probe_stale", source)
    fresh = load_by_source_text("r379_probe_fresh", source)
    assert stale.VALUE == 1, "过期字节码今天读不到旧值：①的取证前提没了"
    assert fresh.VALUE == 2, "🔴 现读源文本也读不到新值：加载法被换回字节码缓存了"


def test_the_cache_path_would_also_beat_a_real_edit(tmp_path):
    """反证的反证：把源文本改回去（仍同尺寸），缓存那侧一个字都没动。"""
    source = tmp_path / "probe_flip.py"
    source.write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    stamp = hold_mtime(source)
    load_by_bytecode_cache("r379_flip_first", source)
    for text, expect in (("VALUE = 2\n", 1), ("VALUE = 1\n", 1)):
        source.write_text(text, encoding="utf-8", newline="\n")
        restore_mtime(source, stamp)
    assert load_by_bytecode_cache("r379_flip_stale", source).VALUE == 1
    assert load_by_source_text("r379_flip_fresh", source).VALUE == 1
    source.write_text("VALUE = 2\n", encoding="utf-8", newline="\n")
    restore_mtime(source, stamp)
    assert load_by_source_text("r379_flip_fresh2", source).VALUE == 2


# ==================== ② 真件：预演文本改了，缓存里的常量还是旧的 ====================


def test_the_ruler_edits_invisibly_to_its_own_cached_bytecode(tmp_path):
    """对真预演件做一次同尺寸改版：缓存里的常量是 37.3，盘上文本已经是 37.4。"""
    copy = tmp_path / "scripts" / "rehearse_eval_window.py"
    copy.parent.mkdir(parents=True)
    original = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    anchor = "MEASURED_SECONDS_PER_CALL = 37.3"
    assert original.count(anchor) == 1, "预演件里那枚标定常数的形状变了，取证据要重排"
    copy.write_text(original, encoding="utf-8", newline="\n")
    pyc = Path(importlib.util.cache_from_source(str(copy)))
    py_compile.compile(str(copy), cfile=str(pyc), dfile=str(copy), doraise=True)
    assert pyc.is_file()
    stamp = hold_mtime(copy)
    edited = original.replace(anchor, "MEASURED_SECONDS_PER_CALL = 37.4")
    assert len(edited) == len(original), "改版前后不同尺寸：那两项校验里少了一项，取证据失效"
    copy.write_text(edited, encoding="utf-8", newline="\n")
    restore_mtime(copy, stamp)
    header = pyc.read_bytes()[:16]
    stat = copy.stat()
    assert int.from_bytes(header[8:12], "little") == int(stat.st_mtime)
    assert int.from_bytes(header[12:16], "little") == stat.st_size
    cached = marshal.loads(pyc.read_bytes()[16:])
    consts = set(all_consts(cached))
    assert 37.3 in consts and 37.4 not in consts, (
        "缓存里那枚常量跟着盘上文本走了：这一族雷的取证前提今天没了")
    fresh = set(all_consts(compile(edited, str(copy), "exec")))
    assert 37.4 in fresh and 37.3 not in fresh, "现读源文本读到的还是旧常量：加载法不对"


# ==================== ③ 全仓点名：谁在字节码缓存上读这枚预演件 ====================


def _string_constants(tree) -> dict:
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _mentions_ruler(node, consts) -> bool:
    """把这个表达式里的模块级字符串常量解一层引用，再看它指没指着预演件。"""
    text = ast.unparse(node)
    for name, value in consts.items():
        text = text.replace(name, value)
    return any(token in text for token in RULER_NAMES)


def _reads_text(node) -> bool:
    """``compile(<某文件>.read_text(...), ...)`` 的那个第一参：现读源文本的形状。"""
    return any(isinstance(call, ast.Call)
               and getattr(call.func, "attr", "") == "read_text"
               for call in ast.walk(node))


def _classify(path: Path) -> dict:
    """分类一枚件对预演件的读法：plain_import / exec_module / compile_text / no_load。"""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    consts = _string_constants(tree)
    forms, lines = set(), {}

    def mark(form, node):
        forms.add(form)
        lines.setdefault(form, []).append(node.lineno)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if any(name and _mentions_ruler(ast.Constant(name), consts) for name in names):
                mark("plain_import", node)
            continue
        if not isinstance(node, ast.Call):
            continue
        func = ast.unparse(node.func)
        if func.endswith("spec_from_file_location"):
            if len(node.args) > 1 and _mentions_ruler(node.args[1], consts):
                mark("ruler_spec", node)
        elif func.endswith("exec_module"):
            mark("exec_module", node)
        elif func.rsplit(".", 1)[-1] == "compile" and node.args and _reads_text(node.args[0]):
            mark("compile_text", node)
        elif func.endswith(("import_module", "__import__")) and node.args \
                and _mentions_ruler(node.args[0], consts):
            mark("plain_import", node)
    return {"path": path, "forms": forms, "lines": lines}


def _ruler_files() -> list:
    files = [REPO / "conftest.py", REPO / "main.py"]
    for sub in ("tests", "scripts", "app"):
        files += sorted((REPO / sub).glob("*.py"))
    return [path for path in files if path.is_file()
            and any(token in path.read_text(encoding="utf-8-sig") for token in RULER_NAMES)]


def test_every_reader_of_the_ruler_compiles_the_source_text(capsys):
    """名单与判法一起给：谁在字节码缓存上读这枚件，具名具行号。"""
    report = [_classify(path) for path in _ruler_files()]
    readers = [item for item in report
               if item["forms"] & {"plain_import", "ruler_spec", "compile_text"}]
    offenders = []
    for item in readers:
        rel = str(item["path"].relative_to(REPO)).replace("\\", "/")
        cached = "plain_import" in item["forms"] or (
            "ruler_spec" in item["forms"] and "exec_module" in item["forms"]
            and "compile_text" not in item["forms"])
        if cached and rel not in ALLOWED_STALE_LOADERS:
            offenders.append((rel, sorted(item["forms"]), item["lines"]))
    print("\nR379 格四名单（现场扫出）：")
    for item in sorted(report, key=lambda one: str(one["path"])):
        rel = str(item["path"].relative_to(REPO)).replace("\\", "/")
        print(f"  {rel}: {sorted(item['forms']) or ['no_load']} {item['lines'] or ''}")
    assert readers, "一枚读者都没扫到：名单本身失效了，别把空跑当绿"
    assert not offenders, "又回到字节码缓存上读预演件的件：" + repr(offenders)


def test_the_r217_importer_now_reads_source_text():
    """这一件从前是 ``from scripts.rehearse_eval_window import budget_table``：整句换掉取证。"""
    rel = REPO / "tests/test_r217_strict_unaffordable_form.py"
    tree = ast.parse(rel.read_text(encoding="utf-8-sig"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
    assert not any("rehearse" in (name or "") for name in imported), sorted(imported)
    compiled = _classify(rel)
    assert "compile_text" in compiled["forms"], compiled
    assert "exec_module" not in compiled["forms"], compiled


# ==================== ④ 预演件自己读别的项目件时也不许走缓存 ====================


def test_the_ruler_never_uses_exec_module_itself():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8-sig"))
    cached = [node.lineno for node in ast.walk(tree)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute) and node.func.attr == "exec_module"]
    assert not cached, f"预演件又用回 importlib 的字节码缓存加载项目件（行 {cached}）"
    host = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "load_checker")
    assert any(ast.unparse(node.func) == "compile" for node in ast.walk(host)
               if isinstance(node, ast.Call)), "load_checker 不再现读 R94 常驻件的源文本"


def test_the_loader_stays_correct_when_the_clock_does_not_move(tmp_path):
    """同秒内连续改两次：mtime 一秒都没走，读到的必须是最后一次那份文本。"""
    source = tmp_path / "probe_same_second.py"
    source.write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    stamp = hold_mtime(source)
    load_by_bytecode_cache("r379_clock_first", source)
    for value in (2, 3, 4):
        text = f"VALUE = {value}\n"
        assert len(text) == len("VALUE = 1\n")
        source.write_text(text, encoding="utf-8", newline="\n")
        restore_mtime(source, stamp)
        assert load_by_source_text(f"r379_clock_{value}", source).VALUE == value
    time.sleep(0)