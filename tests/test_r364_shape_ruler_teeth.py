"""R364 · 两枚"手抄账"现场的常驻牙：尺子必须比它守的东西强。

本仓这族病有五个同族现场，形状都是「把当时读到的东西抄进测试」：抄行号（test_r238）、
抄迁移尾号（test_r251）、抄一行源文本（test_r298 抄 chat.py）、抄一枚十六进制指纹
（test_r304 抄 tables.py 的 sha256），以及本单这两枚：

* **现场 A** = `tests/test_document_upload_resilience.py:123`（基点 dbb8ba4）把 chat.py 上传腿
  的一行原文抄进测试。R306 第二棒（6d00d70）给同一处加了 `display_name=` 就是这种钉红给合法
  演进的那一次。改成 R298 那把形状尺之后，本文件负责证明它**不是把钉拔松**：摘掉
  `asyncio.to_thread(`（退回在事件循环里同步解析）、把被调符号换成 loader 以外的东西、多长一枚
  第二处调用，三样都得当场红；而加一枚新 kwarg、换掉那枚路径变量名，本件一枚都不许多红。
* **现场 B** = `tests/test_r300_tables.py` docstring 那句「跑完即还原，并核对源文件 sha256 回到
  7acaa33c0568e8ee...」。它自 58111c9（R331 动过 tables.py）起就是假话，而它写在散文里不是断言，
  所以永远不会红 —— 只会骗下一位照抄的人。改派生之后，本文件钉住：那串 hex 不许以任何形式回来、
  锚点得是提交名不是指纹、四枚派生钉的名字必须还在。

全部只在内存里变异、只读 git 历史：零写盘、零改 app/**、不造提交。盘上真刀（改真文件、跑真用例、
逐把红数）走影子副本道，见 `tests/fixtures/r364_refutation_driver.py`。
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_FILE = REPO_ROOT / "tests" / "test_document_upload_resilience.py"
R300_FILE = REPO_ROOT / "tests" / "test_r300_tables.py"

# 现场 A 用 R298 自己那把尺子（不另造第二把）；现场 B 用 R304/R352 那把派生尺的账本名。
from test_r298_ocr_channel import (  # noqa: E402
    CHAT_SOURCE,
    LOADER_SYMBOL,
    _upload_routes,
    assert_upload_leg_parses_off_the_event_loop,
    upload_leg_assign,
)

#: 现场 A 那枚件里今天允许留下的「字面文本 in *_SOURCE」钉：只准降，不许升。
#: 唯一那枚 = 「await asyncio.to_thread(」——它不指名任何被调符号，因此不随参数表演进。
LITERAL_SOURCE_PIN_RATCHET = 1
LITERAL_SOURCE_PIN_ALLOWED = frozenset({"await asyncio.to_thread("})

#: 现场 B 换派生以后必须留在 r300 里的四枚钉（少一枚就是有人把账搬回散文里了）。
R300_NAILS = (
    "test_the_restored_bytes_are_the_ones_the_named_anchor_shipped",
    "test_the_anchor_of_the_restoration_claim_passes_its_three_self_check_nails",
    "test_a_commit_with_identical_bytes_does_not_qualify_as_the_anchor",
    "test_the_derived_nail_measures_the_file_the_prose_names",
)

#: 一把"loader 以外"的真符号：chat.py 模块级从 app.documents.preview 引进来的（不是同名顶包）。
OUTSIDE_LOADER_SYMBOL = "build_document_preview"


# ---------------------------------------------------------------- 变异机（只在内存里）


def _thread_call(assign):
    """``content = await asyncio.to_thread(load_document, ...)`` 里那枚 to_thread 调用。"""
    return assign.value.value


def _mutate_upload_leg(transform):
    """在 chat.py 的树上就地做变异，交回**整份**源码文本（不写盘）。"""
    tree, assign = upload_leg_assign(CHAT_SOURCE)
    transform(tree, assign)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _parsed_on_the_loop(_tree, assign):
    """刀1：摘掉 `asyncio.to_thread(` —— 解析退回事件循环上同步跑。"""
    call = _thread_call(assign)
    assign.value = ast.Await(value=ast.Call(func=call.args[0], args=call.args[1:], keywords=call.keywords))


def _callee_from_outside_the_loader(_tree, assign):
    """刀2：被调符号换成 loader 以外的东西（同形状、同参数，只换身份）。"""
    _thread_call(assign).args[0] = ast.Name(id=OUTSIDE_LOADER_SYMBOL, ctx=ast.Load())


def _second_parse_handoff(tree, assign):
    """刀3：多长一枚第二处 `await asyncio.to_thread(load_document, ...)`（"恰好一枚"失效）。"""
    duplicate = copy.deepcopy(assign)
    duplicate.targets = [ast.Name(id="content_again", ctx=ast.Store())]
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and any(stmt is assign for stmt in block):
                block.insert(block.index(assign) + 1, duplicate)
                return
    raise AssertionError("上传腿那枚赋值不在任何语句块里：变异机的前提没了")


def _extra_keyword(_tree, assign):
    """合法演进：给那一行再加一枚关键字实参（R306 的 display_name= 是同一形状的第一例）。"""
    _thread_call(assign).keywords.append(ast.keyword(arg="ocr", value=ast.Constant(value=True)))


class _PathVarRenamer(ast.NodeTransformer):
    def __init__(self, old, new):
        self.old = old
        self.new = new

    def visit_Name(self, node):
        if node.id == self.old:
            node.id = self.new
        return node


def _rename_path_variable(tree, assign):
    """合法演进：换掉持有落盘路径的变量名（连 str(...) 那枚绑定一起换，函数名不写死）。"""
    var = _thread_call(assign).args[1]
    assert isinstance(var, ast.Name), "路径实参不是局部变量名，这枚演进无从演起"
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    hop = parents.get(assign)
    while hop is not None and not isinstance(hop, (ast.AsyncFunctionDef, ast.FunctionDef)):
        hop = parents.get(hop)
    assert hop is not None, "上传腿那枚赋值没有宿主函数"
    _PathVarRenamer(var.id, var.id + "_renamed").visit(hop)


def _asserts_raises(transform):
    mutant = _mutate_upload_leg(transform)
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(mutant)
    return mutant


# ---------------------------------------------------------------- 现场 A：尺子的落点


def test_the_upload_resilience_file_calls_the_shared_ruler():
    """判据①的凭据：那一格现在真在调用 R298 的形状尺，而不是自己抄一份。"""
    tree = ast.parse(UPLOAD_FILE.read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_upload_moves_blocking_parsing_and_indexing_off_the_event_loop"
    )
    body = ast.unparse(fn)
    assert "assert_upload_leg_parses_off_the_event_loop(CHAT_SOURCE)" in body, "形状尺没被调用"
    assert "read_text(" not in body, "又开始现读 chat.py 并往本文件里抄了"


def test_no_pin_copies_a_line_of_the_upload_route():
    """判据①：任何「字面量里点名 load_document 还去 in 某份源码」的抄写都不许回来。"""
    offenders = []
    for path in (UPLOAD_FILE, R300_FILE):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Constant):
                continue
            if not isinstance(node.left.value, str) or LOADER_SYMBOL not in node.left.value:
                continue
            if any(isinstance(op, ast.In) for op in node.ops):
                offenders.append("%s:%d %s" % (path.name, node.lineno, node.left.value[:48]))
    assert not offenders, "抄进去的那行原文回来了：" + " / ".join(offenders)


def test_the_copying_ruler_measures_something():
    """反例刀（常驻）：上面那枚棘轮不是空转 —— 把旧形状喂给它，它必须抓到。"""
    forged = 'assert "await asyncio.to_thread(load_document, file_path)" in CHAT_SOURCE\n'
    hits = [
        node.lineno
        for node in ast.walk(ast.parse(forged))
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Constant)
        and isinstance(node.left.value, str)
        and LOADER_SYMBOL in node.left.value
        and any(isinstance(op, ast.In) for op in node.ops)
    ]
    assert hits == [1], "棘轮对旧形状免疫：它已经不再量任何东西了"


# ---------------------------------------------------------------- 现场 A：三把必须红的刀


def test_the_ruler_rejects_a_parse_that_stays_on_the_event_loop():
    """刀1：`asyncio.to_thread(` 摘掉（退回同步解析）⇒ 当场红。"""
    mutant = _asserts_raises(_parsed_on_the_loop)
    assert LOADER_SYMBOL not in _thread_callees(mutant), "变异机没把解析退回事件循环，这枚红是别处红起来的"
    assert LOADER_SYMBOL in _thread_callees(CHAT_SOURCE), "今天的落点没了：前提变了，本单判据要重读"


def test_the_ruler_rejects_a_callee_that_is_not_from_the_loader():
    """刀2：被调符号换成 loader 以外的东西 ⇒ 当场红（同名顶包也一样，见 _loader_imports）。"""
    mutant = _mutate_upload_leg(_callee_from_outside_the_loader)
    assert _thread_callees(mutant) != _thread_callees(CHAT_SOURCE), "刀2 没真换掉被调符号"
    assert LOADER_SYMBOL not in _thread_callees(mutant), "被调符号还留在原位"
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(mutant)


def test_the_ruler_rejects_a_second_parse_handoff():
    """刀3：多长一枚第二处线程解析 ⇒ "恰好一枚"那格当场红。"""
    _asserts_raises(_second_parse_handoff)


def test_a_bare_substring_pin_would_be_blind_to_knife_one():
    """判据③：把尺子放宽成 `assert "load_document" in source`，刀1 就不红了 —— 所以不许放宽。"""
    mutant = _mutate_upload_leg(_parsed_on_the_loop)
    assert LOADER_SYMBOL in mutant, "前提没了：连提到都没提到，反例刀不成立"
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(mutant)


def test_the_old_copied_line_would_break_on_a_legal_evolution():
    """这一格说明"就地重录字面量"为什么不算修好：抄来的原文在合法演进上必红。"""
    _tree, base_assign = upload_leg_assign(CHAT_SOURCE)
    exact = ast.unparse(base_assign)
    assert exact in ast.unparse(ast.parse(CHAT_SOURCE))
    assert exact not in _mutate_upload_leg(_extra_keyword), "抄原文那把尺子居然还认这次演进"


# ---------------------------------------------------------------- 现场 A：两枚必须绿的演进


def test_the_ruler_lets_a_new_keyword_argument_through():
    """判据①：给那一行加一枚新 kwarg ⇒ 本件不许多红一枚。"""
    assert_upload_leg_parses_off_the_event_loop(_mutate_upload_leg(_extra_keyword))


def test_the_ruler_lets_the_path_variable_be_renamed():
    """判据①：换掉持有落盘路径的变量名（连同 str(...) 绑定）⇒ 同样不许红。"""
    mutant = _mutate_upload_leg(_rename_path_variable)
    assert "_renamed = str(" in mutant, "变异机没真换到名字，这枚放行是假的"
    assert_upload_leg_parses_off_the_event_loop(mutant)


# ---------------------------------------------------------------- 现场 B：散文里那串指纹不许回来


def _string_constants(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node


def test_no_hand_copied_digest_literal_survives_in_the_three_files():
    """判据④：三枚件里不许再出现 32 位以上的 hex 字符串常量（docstring 也算，它就是常量）。"""
    offenders = []
    for path in (UPLOAD_FILE, R300_FILE, Path(__file__)):
        for node in _string_constants(path):
            stripped = node.value.strip()
            if len(stripped) >= 32 and all(ch in "0123456789abcdef" for ch in stripped.lower()):
                offenders.append("%s:%d %s…" % (path.name, node.lineno, stripped[:12]))
    assert not offenders, "手抄指纹回来了：" + " / ".join(offenders)


def test_the_r300_prose_points_at_a_derivable_ruler():
    """判据④：docstring 那句不再"回到某串数字"，而是指向记名锚点与四枚派生钉。"""
    text = R300_FILE.read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(text), clean=True) or ""
    assert "sha256 回到" not in doc, "那句假散文回来了"
    assert "记名锚点" in doc and "blob" in doc, "散文没改成可派生的措辞：" + doc[:120]
    names = {node.name for node in ast.walk(ast.parse(text)) if isinstance(node, ast.FunctionDef)}
    missing = [name for name in R300_NAILS if name not in names]
    assert not missing, "r300 的派生钉缺了：" + " / ".join(missing)


def test_the_r300_anchor_is_a_commit_name_shared_with_r304():
    """判据⑤：r300 不许自己再定一条锚 —— 它 import R304 那枚具名常量，两枚件读同一条锚。

    形状也要钉死：锚点得是**提交名**（7-40 位 hex）。64 位那就是指纹，是指纹就得有人重抄，
    而"没人欠你一次重抄"正是本族病第一次复发时抄的东西。
    """
    r300 = ast.parse(R300_FILE.read_text(encoding="utf-8"))
    imported = {
        alias.asname or alias.name
        for node in ast.walk(r300)
        if isinstance(node, ast.ImportFrom) and node.module == "test_r304_table_wiring"
        for alias in node.names
    }
    assert "TABLES_ANCHOR_SHA" in imported, "r300 没从 r304 引锚点：它要么自己另定了一条，要么根本没读"
    assert "TABLES_SHA256" not in imported, "r300 里出现了手抄指纹的形"
    value = None
    for node in ast.walk(ast.parse((REPO_ROOT / "tests" / "test_r304_table_wiring.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "TABLES_ANCHOR_SHA" for target in node.targets
        ):
            value = node.value.value if isinstance(node.value, ast.Constant) else None
    assert isinstance(value, str), "r304 里读不到 TABLES_ANCHOR_SHA：两枚件共用的那把尺子没源头了"
    assert 7 <= len(value) <= 40, "锚点写成了指纹而不是提交名：%s" % value


def test_copying_a_line_of_source_text_into_a_pin_does_not_grow():
    """棘轮：两枚件里「字面文本 in *_SOURCE」这种形状只剩账上那一枚，不许再长。"""
    found = _literal_source_pins(UPLOAD_FILE) + _literal_source_pins(R300_FILE)
    assert len(found) <= LITERAL_SOURCE_PIN_RATCHET, "多长了一枚抄源文本的判据：" + repr(found)
    assert {lit for _name, _line, lit in found} <= LITERAL_SOURCE_PIN_ALLOWED, (
        "这一格不在已登记的残留名单里：" + repr(found)
    )


def _literal_source_pins(path):
    """扫一件：找出所有「字面文本 in 某枚 *_SOURCE」形状的断言（与 R351 同一把尺）。"""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Constant):
            continue
        if not isinstance(node.left.value, str):
            continue
        if not any(isinstance(op, ast.In) for op in node.ops):
            continue
        if not any(isinstance(c, ast.Name) and c.id.endswith("_SOURCE") for c in node.comparators):
            continue
        found.append((path.name, node.lineno, node.left.value))
    return found


def test_the_three_self_check_nails_are_one_reusable_ruler():
    """判据⑤：三枚自校钉做成一把可复用的尺子，正锚与冒牌两枚钉共用它（不许各抄一份）。

    把腿拆进某枚 test 体内就演不动冒牌提交了 —— 那正是"派生"退化成同义反复的入口。
    """
    tree = ast.parse(R300_FILE.read_text(encoding="utf-8"))
    tops = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "_anchor_disqualified_reasons" in tops, "三枚自校钉没做成一个顶层函数：反证钉无从复用"
    merged = ast.unparse(tops["_anchor_disqualified_reasons"])
    for name in ("_commit_touches_tables", "_identical_impostor_rev"):
        if name in tops:
            merged += ast.unparse(tops[name])
    for token in ("merge-base", "--is-ancestor", "--name-only", "^"):
        assert token in merged, "自校钉少了腿（或腿被拆进 test 体里了）：" + token
    sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_anchor_disqualified_reasons"
    ]
    assert len(sites) == 2, "共用这把尺子的调用点应有两枚（正锚 + 冒牌），实测 %d 枚" % len(sites)


def _thread_callees(source):
    """上传路由里那些 ``await asyncio.to_thread(<符号>, ...)`` 的被调符号名（不预设是哪一枚）。

    断言取真值一律走这里，不抄行原文：尺子不许比它守的东西更弱，也不许比它更脆。
    """
    names = []
    for route in _upload_routes(ast.parse(source)):
        for node in ast.walk(route):
            if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "to_thread"
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
                and node.value.args
            ):
                names.append(ast.unparse(node.value.args[0]))
    return names
