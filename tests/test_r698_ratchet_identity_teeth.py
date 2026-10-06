# -*- coding: utf-8 -*-
"""R698 反证刀 —— r638 棘轮的方向格必须两张表都带，否则恒等式自断。

病形（工单 R698）：``scripts/r638_doc_pointer_ruler.py::ratchet_diff`` 落袋时 ``grew`` 只带
``added``、``shrank`` 只带 ``removed``，而同一枚函数末尾那条恒等式把两张表都算进右边。于是枚数既增
又删的一枚档（R693 交回的现场读数 before=75／after=77／added=31）让那枚 assert 当场自断——
这不是盘面脏，是尺在骗自己；门里那句「r638 需重取基线」因此是假话。

判据对号：
  ① 合成档面「既增又删」：``grew`` 那格必须同时带两张表，``removed`` 非空，恒等式对这一格成立。
  ② 同一形状的反面（枚数净减而身份又换）：``shrank`` 那格同样两张表都带，且一枚都不许进 ``grew``。
  ③ 基线里有、盘上没了的那枚档：``shrank`` 那格带一枚空 ``added``，恒等式同样成立。
  ④ 静态针：盘上那把尺里 ``grew``／``shrank``／``shifted`` 每一枚 ``append`` 的字典都必须同时出现
     两张表的键——谁把它改回去，这枚针当场红（正例对照是 ``shifted``，本来就一直带着两张表）。
  ⑤ 反证刀：把 ``grew.append`` 那一行改回只带 ``added``，同一副档面喂给这枚改过的影子尺必须炸；
     炸不出来＝本单那格是死牙。盘上那把真尺的字节动手前后逐枚相等。
  ⑥ 现读整册：盘上基线对尺的现取读数逐格复核恒等式，一枚数字都不抄（档面由真实名册扰动出来，
     所以这一格永远量得到东西，不随账面是否漂移）。

姿势（在册规矩）：影子刀全部落 ``tmp_path``。就地改被跟踪文件由
``tests/test_r253_no_test_rewrites_a_tracked_file.py::test_no_test_rewrites_a_tracked_file_in_place``
禁着，所以判据⑤ 的「盘上真改」改的是一枚真落盘的影子件，尺身与主树一个字节都不动。
🔴 本件不许把「此刻工作树脏不脏」当判据：只看尺的读数与影子件的字节。
🔴 零 import 产品码，零手抄坐标：坐标一律由下面的把手现场拼，源文里不出现「点 py 冒号 数字」那一形。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import itertools
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "r638_doc_pointer_ruler.py"
BASELINE_ARTIFACT = REPO / "docs" / "testing" / "r638-pointer-baseline.json"

#: 造坐标的把手：本件因此自己不带一枚在册形状的手抄坐标（棘轮预算不许被本单抬高）。
PY = ".py"
SEP = ":"
DOC_A = "ledger-a.md"
DOC_B = "ledger-b.md"
TABLES = ("added", "removed")

#: 判据⑤ 那两枚形状原文：修好的那一行与改回去的那一行，逐字节写在这里而不是抄行号。
FIXED_GREW_BRANCH = 'grew.append({**cell, "added": added, "removed": removed})'
BROKEN_GREW_BRANCH = 'grew.append({**cell, "added": added})'


def _load_ruler(name: str, path: Path):
    """按路径装载一把尺（先注册进 sys.modules：dataclass 要拿得到自己的模块）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ruler():
    name = "r638_doc_pointer_ruler"
    if name not in sys.modules:
        _load_ruler(name, SCRIPT)
    return sys.modules[name]


ruler = _ruler()


def coordinate(name: str, start: int) -> str:
    """现场拼一枚坐标：文件串 ＋ 点 py ＋ 冒号 ＋ 行号。"""
    return "%s%s%s%d" % (name, PY, SEP, start)


def body(names: list[str]) -> str:
    """把一组被引串写成一枚 .md 正文：一枚坐标一行，行文本互不相同＝身份互不相同。"""
    return "".join("见 %s 那一格。\n" % coordinate(name, index)
                   for index, name in enumerate(names, start=1))


def face(shadow_docs: Path, docs: dict[str, list[str]]) -> dict:
    """把一副合成档面落成影子根，再由尺自己现取读数：本件一枚数字都不抄。"""
    for rel, names in docs.items():
        path = shadow_docs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body(names), encoding="utf-8", newline="\n")
    for path in sorted(shadow_docs.rglob("*.md")):
        if path.relative_to(shadow_docs).as_posix() not in docs:
            path.unlink()
    return ruler.build_baseline(ruler.analyze(shadow_docs, REPO))


def cited(keys: list[str]) -> list[str]:
    """从身份串里剥出被引坐标串（第三段起），逐枚点得出名。"""
    return sorted(str(key).split("::", 2)[2] for key in keys)


def identity_ok(cell: dict) -> bool:
    """恒等式：枚数差 ＝ 添上的枚数 − 掉的那枚数（两张表都在才算得出）。"""
    return cell["after"] - cell["before"] == len(cell["added"]) - len(cell["removed"])


def shadow_root(tmp_path: Path) -> Path:
    return tmp_path / "shadow" / "docs"


# ==================== 判据①：既增又删的一枚档必须报 grew 且两张表都带 ====================


def test_a_cell_that_both_gains_and_loses_ships_both_tables(tmp_path) -> None:
    """主牙：修尺之前这一枚当场自断（尺身末尾那条 assert），修尺之后必须读出 grew 带两张表。"""
    shadow = shadow_root(tmp_path)
    kept = ["synth-keep-one", "synth-keep-two"]
    dropped = ["synth-drop-one", "synth-drop-two"]
    gained = ["synth-new-one", "synth-new-two", "synth-new-three"]

    stored = face(shadow, {DOC_A: kept + dropped})
    live = face(shadow, {DOC_A: kept + gained})

    diff = ruler.ratchet_diff(stored, live)
    assert diff["forged"] == [], diff["forged"]
    assert [cell["doc"] for cell in diff["grew"]] == ["docs/" + DOC_A], diff["grew"]
    cell = diff["grew"][0]
    assert set(TABLES) <= set(cell), cell
    assert cell["removed"], "grew 那格丢了 removed：恒等式的减数被扔了"
    assert cell["added"], cell
    assert identity_ok(cell), cell
    assert cell["before"] == 4 and cell["after"] == 5, cell
    assert cited(cell["removed"]) == sorted(coordinate(name, index)
                                         for index, name in enumerate(dropped, start=3))
    assert cited(cell["added"]) == sorted(coordinate(name, index)
                                        for index, name in enumerate(gained, start=3))


# ==================== 判据②：枚数净减而身份又换——shrank 同样两张表都带 ====================


def test_a_cell_that_shrinks_by_replacement_ships_both_tables(tmp_path) -> None:
    """方向不许装反：净减一枚进 shrank，而 shrank 那格不许只带减数。"""
    shadow = shadow_root(tmp_path)
    kept = ["synth-hold-one", "synth-hold-two"]
    dropped = ["synth-gone-one", "synth-gone-two", "synth-gone-three"]
    gained = ["synth-come-one", "synth-come-two"]

    stored = face(shadow, {DOC_A: kept + dropped})
    live = face(shadow, {DOC_A: kept + gained})

    diff = ruler.ratchet_diff(stored, live)
    assert diff["grew"] == [], "枚数下降被报成 grew：方向又装反了"
    assert diff["offenders"] == [], diff["offenders"]
    assert [cell["doc"] for cell in diff["shrank"]] == ["docs/" + DOC_A], diff["shrank"]
    cell = diff["shrank"][0]
    assert set(TABLES) <= set(cell), cell
    assert cell["added"] and cell["removed"], cell
    assert identity_ok(cell), cell
    assert len(cell["removed"]) == 3 and len(cell["added"]) == 2, cell


# ==================== 判据③：基线里有、盘上没了的那枚档 ====================


def test_a_vanished_doc_reports_shrank_with_an_empty_added(tmp_path) -> None:
    """整枚档从盘上消失：shrank 那格的 added 是一枚空表，恒等式仍然算得出。"""
    shadow = shadow_root(tmp_path)
    stored = face(shadow, {DOC_A: ["synth-left-one", "synth-left-two", "synth-left-three"],
                           DOC_B: ["synth-stayed-one", "synth-stayed-two"]})
    live = face(shadow, {DOC_B: ["synth-stayed-one", "synth-stayed-two"]})

    diff = ruler.ratchet_diff(stored, live)
    cells = {cell["doc"]: cell for cell in diff["shrank"]}
    assert "docs/" + DOC_A in cells, diff["shrank"]
    cell = cells["docs/" + DOC_A]
    assert cell["added"] == [], cell
    assert cell["before"] == 3 and cell["after"] == 0, cell
    assert identity_ok(cell), cell
    assert diff["grew"] == [], diff["grew"]


# ==================== 判据④：静态针——盘上那把尺的每一枚方向格都带两张表 ====================


def _append_targets_in(function: ast.FunctionDef) -> list[tuple[str, set[str]]]:
    """交回 ``<列表名>.append({...})`` 的 (列表名, 字典里的字符串键集合)。"""
    out: list[tuple[str, set[str]]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "append"
                and isinstance(func.value, ast.Name) and func.value.id in {"grew", "shrank", "shifted"}):
            continue
        keys: set[str] = set()
        for arg in node.args:
            if isinstance(arg, ast.Dict):
                keys |= {item.value for item in arg.keys
                         if isinstance(item, ast.Constant) and isinstance(item.value, str)}
        out.append((func.value.id, keys))
    return out


def test_the_shipped_ruler_appends_both_tables_in_every_branch() -> None:
    """盘上那把尺的源码形状：三支方向格逐枚点名，缺一张表就红——这一格不靠盘面漂移吃饭。"""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    fn = next(node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "ratchet_diff")
    targets = _append_targets_in(fn)
    assert {name for name, _keys in targets} == {"grew", "shrank", "shifted"}, targets
    offenders = [(name, sorted(set(TABLES) - keys)) for name, keys in targets
                 if not set(TABLES) <= keys]
    assert offenders == [], "这一行又只剩一张表了：%s" % offenders


# ==================== 判据⑤：反证刀——把那一行改回去，恒等式必须炸 ====================


def test_dropping_the_other_table_makes_the_ruler_break(tmp_path) -> None:
    """真落盘的影子尺（改的是那一行字节）喂同一副档面必须炸；正控是真尺同一副档面读得出来。"""
    source = SCRIPT.read_text(encoding="utf-8")
    digest_before = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert source.count(FIXED_GREW_BRANCH) == 1, "尺身那一行的形状变了：反证刀找不到把手"
    mutated = source.replace(FIXED_GREW_BRANCH, BROKEN_GREW_BRANCH, 1)
    assert mutated != source

    mutant_path = tmp_path / "mutant" / "r638_doc_pointer_ruler.py"
    mutant_path.parent.mkdir(parents=True, exist_ok=True)
    mutant_path.write_text(mutated, encoding="utf-8", newline="\n")
    mutant = _load_ruler("r638_doc_pointer_ruler_mutant_for_r698", mutant_path)

    shadow = shadow_root(tmp_path)
    stored = face(shadow, {DOC_A: ["synth-keep-one", "synth-keep-two",
                                   "synth-drop-one", "synth-drop-two"]})
    live = face(shadow, {DOC_A: ["synth-keep-one", "synth-keep-two",
                                 "synth-new-one", "synth-new-two", "synth-new-three"]})

    with pytest.raises(AssertionError):
        mutant.ratchet_diff(stored, live)
    control = ruler.ratchet_diff(stored, live)
    assert control["grew"] and control["grew"][0]["removed"], control["grew"]
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == digest_before, "反证刀不许动盘上那把尺"


# ==================== 判据⑥：现读整册——每一枚方向格都复核恒等式 ====================


def test_the_identity_holds_over_the_live_ledger(tmp_path) -> None:
    """真实名册扰动出一副既增又删的档面：这一格永远量得到东西，且不抄任何一枚数字。"""
    stored = json.loads(BASELINE_ARTIFACT.read_text(encoding="utf-8"))
    assert ruler.validate_baseline(stored) == [], "盘上基线自证不过：那是 R693 的写域，本单不碰"
    live = ruler.build_baseline(ruler.analyze(REPO / "docs", REPO))

    doc, entry = max(sorted(live["files"].items()), key=lambda item: len(item[1]["pointers"]))
    assert len(entry["pointers"]) >= 3, doc
    victims = list(entry["pointers"][:2])
    gained = ["%s::%s::%s" % (doc, ruler.line_digest("扰动行 %d" % index),
                              coordinate("synth-r698", index)) for index in range(1, 4)]
    entry["pointers"] = sorted(entry["pointers"][2:] + gained)
    entry["count"] = len(entry["pointers"])
    entry["digest"] = ruler.content_digest("扰动档面：" + doc)

    diff = ruler.ratchet_diff(stored, live)
    cells = list(itertools.chain(diff["grew"], diff["shrank"], diff["shifted"]))
    assert cells, "整册一枚方向格都没有：这枚针空过等于没钉"
    for cell in cells:
        assert set(TABLES) <= set(cell), cell
        assert identity_ok(cell), cell
    perturbed = [cell for cell in cells if cell["doc"] == doc]
    assert len(perturbed) == 1, cells
    cell = perturbed[0]
    assert cell["added"] and cell["removed"], cell
    for key in victims:
        assert key in cell["removed"], (key, cell)
    for key in gained:
        assert key in cell["added"], (key, cell)
