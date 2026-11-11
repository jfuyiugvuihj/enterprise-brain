# -*- coding: utf-8 -*-
"""R655 常驻牙：r643 那格升格之后不许退回去拿过期事实当判据，也不许被摸成永真。

对着的病（10-05 总控现取，非转述）：R647 并树 246efb7 把 scripts/r636_stage_coverage.py 的发级分母
改走 scripts/r631_stage_sum_delta.py 那条路之后，tests/test_r643_shot_denominator.py 里的
test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator 还钉着 R643 并树
那一刻的现场读数（「覆盖面那把尺自己也折了一枚 ⇒ 与 r631 分歧」）。那枚红不复存在 ⇒ 旧写法成了拿过期
事实当真理的假红（在册读数：Failed: DID NOT RAISE MismatchError），全量门固定红这一枚。

三层牙，全部对着「形状」而不是对着「此刻红不红」：
  形状闸 那格必须两半都在位：不带折返开关的 build_window 是裸调用（正形），只有带 fold_legacy=True
          的那一枚才准被 pytest.raises 包住（病形）。把裸调用套回 raises 就是旧写法，本件当场红。
  对账闸 正形那半枚必须与空列表比（不许自比、不许 assert 字面真值），两发互不相等的分母必须以数字
          面量在册，红句里那枚 trace 之外的两个数字也得点名。
  现读闸 数字从两把尺自己嘴里取：缺省那条路今天不许抛且逐枚对得上，折叠那条路今天必须抛；账面那两枚
          字面量若与今日现读分家，这枚闸先红并要人重算，不许那格烂成第二枚过期事实。
另有在册格名册、折返开关缺省、刀口锚点，以及「本域任何一枚牙都不许拿盘面状态当判据」共四道静态闸
（在册事故 #96／#107／#113 同族）。

五把刀（逐枚点名 victim；每把先跑正控：同一套影子机械、edits=() 必须先绿，红才算被咬中）：
  S1 把那格改回「拿旧红当判据」那种写法（raise 套回缺省那条路，折返开关摘掉）
     victim：test_the_honest_leg_is_not_wrapped_in_pytest_raises
  S2 正形断言被摸成永真（与空列表比 改成一枚自比）
     victim：test_the_positive_leg_compares_and_the_two_numbers_are_pinned
  K1 折返开关被摸成恒不折（r636 把 fold_legacy 一路压成 False）
     victim：在册那格 —— 病形当场 DID NOT RAISE，判据哑
  K2 缺省就把两发折成一枚分母（r636 把 fold_legacy 一路压成 True）
     victim：在册那格 —— 正形那半枚当场抛 MismatchError，绿不了
  K3 连对账基准也一起折（账面自洽、mismatches 交回空列表 ⇒ 只有逐枚数字能救）
     victim：在册那格 —— 两发落在同一枚分母上，逐枚读数当场红

影子纪律（照 tests/test_r545_counter_evidence_teeth.py 并树 48cc956 与
tests/test_r645_contract_difference_ledger.py 并树 28d1ea4）：源文从盘上读进字符串、归一 LF、改、
写进 pytest 的 tmp_path 留痕、compile 成另一枚模块，仓内一个字节都不动；影子的 __file__ 一律指回真仓
那枚源文 —— r636 的派生尺要 AST 扫 app/**，让它看不见仓就会红得没有道理。在册那格的命名空间只换
coverage 这一枚符号，monkeypatch 收刀自动还原。
全程零容器零连库零模型零端口零写入生产路径；真窗那几枚只读 %TEMP% 下 evalrun 那三本件，不在位即
skip，不改判语。

跑法：
    .venv/Scripts/python.exe -m pytest -p no:randomly -q tests/test_r655_no_stale_fact_teeth.py
"""
from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path

import pytest

import tests.test_r643_shot_denominator as nails

THIS = sys.modules[__name__]
REPO = Path(__file__).resolve().parents[1]
R643_REL = "tests/test_r643_shot_denominator.py"
R636_REL = "scripts/r636_stage_coverage.py"
CELL = "test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator"
WINDOW = "run20k"
QUESTION = "doc-04"
#: 在册读数（R643 现取、R647 并树 246efb7 复核）：同一题两发各自的端到端分母。
LOW_MS = 27244.6
HIGH_MS = 27490.9
#: 折叠那条路把两发一起押在 HIGH_MS 上，所以病形的红句里 mine 是它、r631 是 LOW_MS。
#: 在册 25 枚格名：少一枚本件当场红；加格只需把新名登记进来（不许删格）。
SHIPPED_CELLS = (
    "test_two_shots_of_one_question_get_two_denominators",
    "test_the_ledger_names_which_shot_each_row_is",
    "test_no_denominator_is_the_average_of_the_two_shots",
    "test_the_folded_view_would_have_lost_one_shot",
    "test_the_frames_leg_is_also_counted_per_shot",
    "test_knife_one_erasing_a_shots_identity_turns_the_ruler_red",
    "test_knife_one_fold_legacy_reproduces_the_disease_and_goes_red",
    "test_knife_five_folding_can_flip_a_fail_into_a_pass",
    "test_knife_two_deleting_a_trace_row_names_the_orphan_shot",
    "test_knife_two_orphan_question_row_is_named_not_dropped",
    "test_knife_three_the_one_percent_line_governs_the_shot_rows",
    "test_knife_three_hand_moving_the_paper_to_five_percent_is_refused",
    "test_knife_four_two_shots_with_identical_ms_are_not_folded",
    "test_knife_four_identical_content_shots_refuse_to_pick_one",
    "test_attribute_shots_never_overwrite_one_another",
    "test_shot_identities_do_not_depend_on_row_order",
    "test_knife_one_manifest_bridged_shots_beat_the_missing_frames",
    "test_knife_one_manifest_without_shot_identity_refuses_to_fold",
    "test_exit_code_contract_is_unchanged",
    "test_real_window_attributes_every_shot_on_the_books",
    "test_real_run20k_doc04_shots_are_each_measured_against_their_own_span",
    "test_real_single_shot_windows_are_byte_for_byte_unchanged",
    "test_real_no_denominator_family_is_still_named_item_by_item",
    "test_real_universe_reconciles_with_the_coverage_ledger",
    CELL,
)

#: 刀口（逐枚原文锚点；锚点漂了本件当场红，见 test_every_blade_anchor_hits_exactly_once）
CUT_S1 = ('        coverage.build_window("run20k", REAL_DIR, fold_legacy=True)\n',
          '        coverage.build_window("run20k", REAL_DIR)\n')
CUT_S2 = ('    built = coverage.build_window("run20k", REAL_DIR)\n'
          '    assert built["shot_ledger"]["fold_legacy"] is False\n'
          '    assert built["mismatches"] == []\n',
          '    built = coverage.build_window("run20k", REAL_DIR)\n'
          '    assert built["shot_ledger"]["fold_legacy"] is False\n'
          '    assert built["mismatches"] == built["mismatches"]  # 摘刀：永真\n')
CUT_K1 = ("allow_unjoined=not samples_by_trace, fold_legacy=fold_legacy)",
          "allow_unjoined=not samples_by_trace, fold_legacy=False)  # 摘刀：开关恒不折")
CUT_K2 = ("allow_unjoined=not samples_by_trace, fold_legacy=fold_legacy)",
          "allow_unjoined=not samples_by_trace, fold_legacy=True)  # 摘刀：缺省就把两发折成一枚分母")
CUT_K3 = ('reference = inputs["r631"].collect(window=window, directory=directory)',
          'reference = inputs["r631"].collect(window=window, directory=directory, fold_legacy=True)')

KNIVES = {
    "S1": {"mode": "shape", "target": R643_REL, "edits": (CUT_S1,),
           "victim": "test_the_honest_leg_is_not_wrapped_in_pytest_raises"},
    "S2": {"mode": "shape", "target": R643_REL, "edits": (CUT_S2,),
           "victim": "test_the_positive_leg_compares_and_the_two_numbers_are_pinned"},
    "K1": {"mode": "ruler", "target": R636_REL, "edits": (CUT_K1,), "victim": CELL},
    "K2": {"mode": "ruler", "target": R636_REL, "edits": (CUT_K2,), "victim": CELL},
    "K3": {"mode": "ruler", "target": R636_REL, "edits": (CUT_K2, CUT_K3), "victim": CELL},
}
SHAPE_KNIVES = sorted(name for name, spec in KNIVES.items() if spec["mode"] == "shape")
RULER_KNIVES = sorted(name for name, spec in KNIVES.items() if spec["mode"] == "ruler")
#: 本域里可能被拿来当判据的盘面探针（在册事故 #96／#107／#113 同族病的入口）
STATE_NEEDLES = ("porcelain", "rev-parse", "ls-files", "numstat", "MERGE_HEAD")
STATE_SCAN = (R643_REL, R636_REL, "tests/test_r636_stage_coverage.py",
              "tests/test_r647_shot_denominators_are_per_shot.py")


# ==================== 取材与影子机械 ====================


def _text(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _shipped_denominator_text() -> str:
    """在册那格唯一的取材口：形状刀就落在这枚函数的返回值上，仓内字节一个都不动。"""
    return _text(R643_REL)


def _apply(text: str, edits) -> str:
    out = text
    for old, new in edits:
        if out.count(old) != 1:
            raise AssertionError("刀口没落在唯一一处：%r（命中 %d 枚）" % (old[:48], out.count(old)))
        out = out.replace(old, new, 1)
    return out


def _shadow_r636(source_text: str, where: Path, knife: str) -> types.ModuleType:
    """影子源码落 tmp_path 留痕 → compile → exec 成另一枚模块；__file__ 指回真仓那枚源文。"""
    where.mkdir(parents=True, exist_ok=True)
    path = where / ("r636_shadow_%s.py" % knife)
    assert REPO not in path.resolve().parents, "影子不落 tmp_path 就要写回仓了"
    path.write_text(source_text, encoding="utf-8")
    name = "r655_mutant_r636_" + knife
    module = types.ModuleType(name)
    module.__file__ = str(REPO / R636_REL)  # 派生尺要读 app/**，影子不许看不见真仓
    sys.modules[name] = module  # 先登记再 exec：dataclass 要能从 sys.modules 找回本模块
    exec(compile(source_text, str(path), "exec"), module.__dict__)
    return module


def _arm(knife: str, tmp_path: Path, monkeypatch, *, bite: bool) -> None:
    """装刀：形状刀换取材口，量具刀换 r643 那格的 coverage 符号；bite=False 就是正控。"""
    spec = KNIVES[knife]
    edits = spec["edits"] if bite else ()
    if spec["mode"] == "shape":
        mutated = _apply(_text(spec["target"]), edits)
        monkeypatch.setattr(THIS, "_shipped_denominator_text", lambda: mutated)
        return
    shadow = _shadow_r636(_apply(_text(R636_REL), edits), tmp_path, knife)
    monkeypatch.setattr(nails, "coverage", shadow)


def _victim(knife: str):
    spec = KNIVES[knife]
    home = THIS if spec["mode"] == "shape" else nails
    return getattr(home, spec["victim"])


def _run_victim(knife: str, tmp_path: Path) -> None:
    victim = _victim(knife)
    signature = victim.__code__.co_varnames[:victim.__code__.co_argcount]
    assert not signature, "%s 需要夹具，本件的机械喂不出来" % knife
    victim()


def _bite(knife: str, tmp_path: Path, monkeypatch) -> bool:
    _arm(knife, tmp_path, monkeypatch, bite=True)
    try:
        _run_victim(knife, tmp_path / "bite")
    except BaseException:  # noqa: BLE001 - Failed: DID NOT RAISE 继承的是 BaseException
        return True
    return False


# ==================== AST 读形状（不看盘面状态，不数行号）====================


def _cell_node(text: str) -> ast.FunctionDef:
    cells = [node for node in ast.parse(text).body
             if isinstance(node, ast.FunctionDef) and node.name == CELL]
    assert len(cells) == 1, "在册那格不在位或重复定义（命中 %d 枚）" % len(cells)
    return cells[0]


def _is_pytest_raises(node: ast.expr) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "raises" and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "pytest")


def _raises_wrapped_ids(node: ast.FunctionDef) -> set:
    inside: set[int] = set()
    for with_node in ast.walk(node):
        if isinstance(with_node, ast.With) and any(_is_pytest_raises(item.context_expr)
                                                   for item in with_node.items):
            inside.update(id(child) for child in ast.walk(with_node))
    return inside


def _build_window_calls(node: ast.AST) -> list[ast.Call]:
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute) and call.func.attr == "build_window"]


def _folds(call: ast.Call) -> bool:
    return any(kw.arg == "fold_legacy" and isinstance(kw.value, ast.Constant)
               and kw.value.value is True for kw in call.keywords)


def _string_constants(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _number_constants(node: ast.AST) -> set:
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))}


def _eq_empty_list_on_mismatches(test: ast.expr) -> bool:
    """``built["mismatches"] == []``：右边必须是空容器字面量，自比或永真都不算这一判。"""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    right = test.comparators[0]
    if not isinstance(right, (ast.List, ast.Tuple, ast.Set)) or right.elts:
        return False
    left = test.left
    return (isinstance(left, ast.Subscript) and isinstance(left.slice, ast.Constant)
            and left.slice.value == "mismatches")


def _is_self_comparison(test: ast.expr) -> bool:
    return (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], (ast.Eq, ast.Is))
            and ast.dump(test.left) == ast.dump(test.comparators[0]))


def _pins_both_shot_numbers(node: ast.AST) -> bool:
    """必须有一枚恰好装着两发分母的容器字面量：那是「不许平均、不许取最大」的锚。"""
    for child in ast.walk(node):
        if isinstance(child, (ast.List, ast.Tuple, ast.Set)) and len(child.elts) == 2:
            values = {element.value for element in child.elts
                      if isinstance(element, ast.Constant) and isinstance(element.value, float)}
            if values == {LOW_MS, HIGH_MS}:
                return True
    return False


def _default_of(node: ast.FunctionDef, name: str):
    args = node.args
    pairs = list(zip([a.arg for a in reversed(args.args)], reversed(args.defaults)))
    pairs += [(arg.arg, default) for arg, default in zip(args.kwonlyargs, args.kw_defaults)]
    for arg, default in pairs:
        if arg == name:
            return default.value if isinstance(default, ast.Constant) else "非字面量"
    return None


# ==================== 形状闸：正形不许再套回 pytest.raises ====================


def test_the_honest_leg_is_not_wrapped_in_pytest_raises() -> None:
    """两半都在位：缺省那条路是裸调用，只有折返那条路准被 raise 钉住。"""
    node = _cell_node(_shipped_denominator_text())
    calls = _build_window_calls(node)
    honest = [call for call in calls if not _folds(call)]
    folded = [call for call in calls if _folds(call)]
    assert honest and folded, (
        "那格两半都要在位：不带折返开关 %d 枚、带 fold_legacy=True %d 枚" % (len(honest), len(folded)))

    wrapped = _raises_wrapped_ids(node)
    stale = [call for call in honest if id(call) in wrapped]
    assert not stale, ("缺省那条路被 pytest.raises 包住了 —— 这正是「r636 仍然折分母」那枚过期事实的写法，"
                       "R647 并树 246efb7 之后它今天不会抛")
    stray = [call for call in folded if id(call) not in wrapped]
    assert not stray, "折叠那条路没被 pytest.raises 钉住 ⇒ 病形失牙"


def test_the_positive_leg_compares_and_the_two_numbers_are_pinned() -> None:
    """正形是真对账；两发的分母与红句里的两个数字逐枚在册。"""
    node = _cell_node(_shipped_denominator_text())
    asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]

    assert any(_eq_empty_list_on_mismatches(item.test) for item in asserts), (
        "正形那半枚不再与空列表比 ⇒ 对账被摸成了永真")
    selfish = [item for item in asserts if _is_self_comparison(item.test)]
    assert not selfish, "那格里出现自比（同一枚表达式 == 自己）：那是永真，不是牙"
    tautology = [item for item in asserts
                 if isinstance(item.test, ast.Constant) and bool(item.test.value)]
    assert not tautology, "那格里出现 assert 字面真值"
    assert _pins_both_shot_numbers(node), (
        "两发互不相等的分母没有以容器字面量在册 ⇒ 折成一枚分母也能判绿")
    assert {LOW_MS, HIGH_MS} <= _number_constants(node), "在册读数缺枚"
    strings = _string_constants(node)
    assert str(LOW_MS) in strings and str(HIGH_MS) in strings, (
        "红句必须点名那两枚数字，不许只点名题号")


# ==================== 现读闸：数字从两把尺自己嘴里取 ====================


@nails.real_inputs
def test_the_denominator_claim_is_today_s_live_fact() -> None:
    """判据再换，这枚先红并且要人重算：它不抄账面，所以不会烂成第二枚过期事实。"""
    honest = nails.ruler.collect(window=WINDOW, directory=nails.REAL_DIR)
    per_shot = {str(row["trace_id"]): round(float(row["end_to_end_ms"]), 1)
                for row in honest["rows"] if row["key"] == QUESTION}
    assert len(per_shot) > 1, "真窗里 %s 不再多发 ⇒ 这格的判据要重算" % QUESTION
    assert len(set(per_shot.values())) == len(per_shot), (
        "%s 各发的分母不再互不相等 ⇒ 折返开关被摸过了，这格要重算" % QUESTION)
    #: 账面那两枚字面量必须还是今天的现读；分家了就在这里红，别留到下一班当旧红
    assert set(per_shot.values()) == {LOW_MS, HIGH_MS}, (
        "在册读数 %s／%s 与现读 %s 分家 ⇒ 重算 tests 里那格的字面量，不许顺手改成跑通就行"
        % (LOW_MS, HIGH_MS, sorted(per_shot.values())))

    built = nails.coverage.build_window(WINDOW, nails.REAL_DIR)  # 正形：今天不许抛
    assert built["mismatches"] == []
    assert {str(row["trace_id"]): round(float(row["end_to_end_ms"]), 1)
            for row in built["questions"] if row["key"] == QUESTION} == per_shot

    with pytest.raises(nails.coverage.MismatchError) as excinfo:  # 病形：折叠那条路今天必须抛
        nails.coverage.build_window(WINDOW, nails.REAL_DIR, fold_legacy=True)
    hits = json.loads(str(excinfo.value).split("前若干枚：", 1)[1])
    stolen = [item for item in hits if item["field"] == "end_to_end_ms"]
    assert stolen, "折叠没借走任何一枚端到端分母 ⇒ 病形没复现，本件要重算"
    assert all(str(item["trace_id"]) in per_shot for item in stolen)
    assert any(float(item["mine"]) != float(item["r631"]) for item in stolen)
    assert {round(float(item["r631"]), 1) for item in stolen} <= set(per_shot.values())


def test_the_fold_switch_is_off_by_default_in_the_shipped_ruler() -> None:
    """折返开关在册缺省仍是「不折」：被摸成恒不折或缺省就折，本闸与刀 K1／K2 一起红。"""
    tree = ast.parse(_text(R636_REL))
    for name in ("read_inputs", "build_window"):
        node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
        assert node is not None, "r636 里那枚 %s 不在位" % name
        assert _default_of(node, "fold_legacy") is False, "%s 的 fold_legacy 缺省不再是 False" % name


# ==================== 名册与卫生闸 ====================


def test_the_denominator_file_ships_every_named_cell_unmarked() -> None:
    """25 枚在册格名一枚不少，那格的标记只剩真窗 skipif；不许 skip／xfail 把判据糊过去。"""
    text = _text(R643_REL)
    defined = {node.name for node in ast.parse(text).body
               if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}
    assert len(SHIPPED_CELLS) == len(set(SHIPPED_CELLS)) == 25
    missing = [name for name in SHIPPED_CELLS if name not in defined]
    assert not missing, "在册格少了：%s（加格可以，删格不行）" % ", ".join(missing)
    assert CELL in nails.__dict__, "那格在 %s 里改名或删掉了" % R643_REL
    assert "xfail" not in text and "pytest.skip(" not in text, (
        "r643 里冒出 skip／xfail：判据可以换，不许摘")
    node = _cell_node(text)
    marks = node.decorator_list
    assert len(marks) == 1 and isinstance(marks[0], ast.Name) and marks[0].id == "real_inputs", (
        "那格的标记不再是唯一一枚真窗 skipif ⇒ 它可能被豁免了")


def test_every_blade_anchor_hits_exactly_once_in_the_shipped_bytes() -> None:
    """锚点在册：每处刀口在源文里仍旧只命中一枚，漂了就红，不许默默失刀。"""
    for knife, spec in sorted(KNIVES.items()):
        text = _text(spec["target"])
        for old, _new in spec["edits"]:
            assert text.count(old) == 1, "刀 %s 的锚点在 %s 里命中 %d 枚" % (
                knife, spec["target"], text.count(old))


def test_no_tooth_in_this_domain_gates_on_the_checkout_state() -> None:
    """反同族病（#96／#107／#113）：本域的钉一律不看「此刻盘面脏不脏／盘上字节等不等于 HEAD blob」。"""
    for rel in STATE_SCAN:
        tree = ast.parse(_text(rel))
        imported = {alias.name.split(".")[0]
                    for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert "subprocess" not in imported, "%s 起了子进程：盘面状态判据的常见入口" % rel
        haystack = _string_constants(tree)
        for needle in STATE_NEEDLES:
            assert not any(needle in text for text in haystack), (
                "%s 里出现盘面探针 %r" % (rel, needle))
    assert "subprocess" not in THIS.__dict__, "本件自己也不许起子进程去摸盘面"


# ==================== 五把刀：逐枚点名 victim，正控先绿 ====================


@pytest.mark.parametrize("knife", SHAPE_KNIVES)
def test_the_shape_control_stays_green(knife, tmp_path, monkeypatch):
    """同一套取材机械、刀口不落（edits=()）：victim 必须先绿，后面的红才有道理。"""
    _arm(knife, tmp_path / "control", monkeypatch, bite=False)
    _run_victim(knife, tmp_path / "control")


@pytest.mark.parametrize("knife", SHAPE_KNIVES)
def test_each_shape_knife_reddens_its_named_victim(knife, tmp_path, monkeypatch):
    assert _bite(knife, tmp_path, monkeypatch), (
        "刀 %s 没咬中 %s：那半枚判据其实没有牙" % (knife, KNIVES[knife]["victim"]))


@nails.real_inputs
@pytest.mark.parametrize("knife", RULER_KNIVES)
def test_the_ruler_control_stays_green(knife, tmp_path, monkeypatch):
    """影子端与真料同读数：把 r636 换成一枚没动过源文的影子，那格必须照旧绿。"""
    _arm(knife, tmp_path / "control", monkeypatch, bite=False)
    _run_victim(knife, tmp_path / "control")


@nails.real_inputs
@pytest.mark.parametrize("knife", RULER_KNIVES)
def test_each_ruler_knife_reddens_its_named_victim(knife, tmp_path, monkeypatch):
    assert _bite(knife, tmp_path, monkeypatch), (
        "刀 %s 没咬中 %s：那一半其实没有牙" % (knife, KNIVES[knife]["victim"]))


def test_the_shadow_machinery_leaves_its_tracks_under_tmp_only(tmp_path) -> None:
    """影子只落 tmp_path：跑完之后仓内两枚源文一字节未动，也不在仓里留下影子文件。"""
    before = {rel: _text(rel) for rel in (R643_REL, R636_REL)}
    shadow = _shadow_r636(_text(R636_REL), tmp_path / "tracks", "probe")
    assert Path(shadow.__file__).resolve() == (REPO / R636_REL).resolve()
    assert {rel: _text(rel) for rel in (R643_REL, R636_REL)} == before, "影子把仓改了"
    strays = [path for path in (REPO / "scripts").glob("*shadow*") if "r636_shadow_" in path.name]
    assert not strays, "影子落进仓内：%s" % [str(path) for path in strays]
