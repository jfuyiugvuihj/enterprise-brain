"""R351 / R352 同族病共用一把尺子：账不许手抄，尺子也不许比它守的东西更弱。

这族病在本仓的形状是「把当时的账抄进测试」——第一次抄行号（test_r238 抄 monitoring.py 的行）、
第二次抄迁移尾号（test_r251 抄 0015）、这第三次抄**源文件里的一行原文**（R298 抄 chat.py）、
第四次抄**一枚十六进制指纹**（R304 抄 tables.py 的 sha256）。现实一动，钉就把别人的合法改动
判成事故，全量门当场红。两枚件各修自己那一格，本文件管三件事：

① 牙（常驻，全部在内存里变异，零写盘、零改 app/**）：R351 那把形状尺必须按住三种真缺陷——
   摘掉解析调用 / 改成在事件循环里同步解析 / 换成直接读文本绕过解析；同时放行参数表的演进
   （R306 给同一处加 display_name= 就是已经发生过的那次演进）。
② 反例刀：把尺子放宽成「文件里提到 load_document 就算绿」，那把"同步解析"的刀当场不红——
   用它证明原尺子确实比它强，也就证明"就地放宽/就地重录"不是修法。
③ 一把尺子扫两枚件：不许再长出手抄的指纹（≥32 位 hex 字符串常量），"抄一句源文本当判据"的
   枚数走棘轮；顺带钉住这两枚件没被 skip/xfail 静掉、R352 的五条腿一枚都不能少。

盘上变异的逐把红数（判据④那四把真刀）不在这里跑：它要改真文件、要造真提交，属影子副本道
（手法见 tests/fixtures/r305_refutation_driver.py），读数记在 R351/R352 回执里。
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
R298 = REPO_ROOT / "tests" / "test_r298_ocr_channel.py"
R304 = REPO_ROOT / "tests" / "test_r304_table_wiring.py"

# 共用两枚件**自己那把**尺子，不另造第二把（否则这枚"防手抄"的件自己就在抄一套判据）。
# 按顶层名 import 与 pytest 的 prepend 导入同名，复用已加载的那份模块对象，不跑第二遍。
from test_r298_ocr_channel import (  # noqa: E402
    CHAT_SOURCE,
    assert_upload_leg_parses_off_the_event_loop,
    test_counter_evidence_a_pure_image_pdf_without_ocr_is_a_failed_parse as counter_a,
    upload_leg_assign,
)
from test_r304_table_wiring import (  # noqa: E402
    TABLES_ANCHOR_SHA,
    TABLES_PRE_ANCHOR_SHA,
    r304_git_blob,
    r304_tables_digest_at,
    r304_tables_digest_on_disk,
)

#: R352 甲案落地的五条腿（少一枚就是有人偷偷删件或并腿）。
R352_NAILS = (
    "test_the_tables_module_is_still_the_bytes_the_anchor_shipped",
    "test_no_commit_after_the_anchor_has_touched_the_tables_module",
    "test_the_anchor_is_read_not_decorated",
    "test_the_anchor_commit_really_is_the_one_that_changed_the_file",
    "test_the_ruler_measures_the_git_blob_layer_not_the_checkout",
)


# ---------------------------------------------------------------- 变异机（只在内存里）


def _mutate_upload_leg(transform):
    """把上传腿那枚赋值表达式换成 transform 的产物，交回**整份** chat.py 文本（不写盘）。"""
    tree, assign = upload_leg_assign(CHAT_SOURCE)
    assign.value = transform(assign.value)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _thread_call(await_node):
    return await_node.value


def _call_removed(await_node):
    """刀1：摘掉这枚调用的整个表达式（解析根本没发生）。"""
    return ast.Constant(value="")


def _parsed_on_the_loop(await_node):
    """刀2：改成 await load_document(...) —— 在事件循环上同步解析。"""
    call = _thread_call(await_node)
    return ast.Await(value=ast.Call(func=call.args[0], args=call.args[1:], keywords=call.keywords))


def _parse_bypassed_by_reading_text(await_node):
    """刀3：换成 Path(...).read_text() —— 绕过解析器，直接把落盘字节当正文。"""
    path_arg = _thread_call(await_node).args[1]
    return ast.Call(
        func=ast.Attribute(
            value=ast.Call(func=ast.Name(id="Path"), args=[path_arg], keywords=[]),
            attr="read_text",
        ),
        args=[],
        keywords=[ast.keyword(arg="encoding", value=ast.Constant(value="utf-8"))],
    )


def _parameter_list_evolved(await_node):
    """合法演进：参数表再加一枚关键字实参（R306 的 display_name= 是同一形状的第一例）。"""
    call = _thread_call(await_node)
    call.keywords.append(ast.keyword(arg="ocr", value=ast.Constant(value=True)))
    return await_node


# ---------------------------------------------------------------- ① R351 的牙


def test_the_shape_ruler_rejects_a_removed_parse_call():
    """刀1：把上传腿那枚解析调用摘掉 ⇒ 形状尺必须红（这一格不许变哑）。"""
    mutant = _mutate_upload_leg(_call_removed)
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(mutant)


def test_the_shape_ruler_rejects_parsing_on_the_event_loop():
    """刀2：改成 await load_document(...)（不走线程）⇒ 必须红。"""
    mutant = _mutate_upload_leg(_parsed_on_the_loop)
    assert "asyncio.to_thread(load_document" not in mutant
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(mutant)


def test_the_shape_ruler_rejects_a_bypassed_parse():
    """刀3：直接读文本绕过解析 ⇒ 必须红（不许"上传有正文"就当"解析过了"）。"""
    mutant = _mutate_upload_leg(_parse_bypassed_by_reading_text)
    assert "read_text" in mutant
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(mutant)


def test_the_shape_ruler_lets_the_parameter_list_evolve():
    """这一格不许红：参数表演进是合法改动，上一班就是被这条红误伤的。"""
    assert_upload_leg_parses_off_the_event_loop(_mutate_upload_leg(_parameter_list_evolved))


def test_the_naive_substring_ruler_is_weaker_than_the_shape_ruler():
    """判据④的反例刀（常驻版）：放宽成「提到 load_document 就算绿」以后，刀2 就不红了。

    这一枚不是给产品代码上锁，是给**下一班改这枚钉的人**上锁：想把它削成字符串包含，
    先看看这枚钉红成什么样。
    """
    sync_parse = _mutate_upload_leg(_parsed_on_the_loop)
    assert "load_document" in sync_parse, "前提没了：连提到都没提到，反例刀不成立"
    assert "asyncio.to_thread" in sync_parse  # 别的地方还在用线程，放宽的尺子看不见这一格
    with pytest.raises(AssertionError):
        assert_upload_leg_parses_off_the_event_loop(sync_parse)
    # 旧式「抄一行原文」在合法演进上必红：期望值从今天的树里现算，不手抄
    _, base_assign = upload_leg_assign(CHAT_SOURCE)
    exact = ast.unparse(base_assign)
    assert exact in ast.unparse(ast.parse(CHAT_SOURCE))
    assert exact not in _mutate_upload_leg(_parameter_list_evolved), (
        "抄原文那把尺子居然还认这次演进：说明形状尺的落点被改窄成了字面文本"
    )


# ---------------------------------------------------------------- ② R352 的派生腿


def test_the_r352_expectation_is_derived_from_a_named_commit():
    """两枚件共用的那把尺：期望值必须**读得出来**，而且不同提交读出不同数。"""
    anchor = r304_tables_digest_at(TABLES_ANCHOR_SHA)
    assert anchor == r304_tables_digest_on_disk(), "派生腿与盘上那份脱钩了"
    assert anchor != r304_tables_digest_at(TABLES_PRE_ANCHOR_SHA), (
        "锚点与对照提交读出同一个数：派生没在读提交，判据⑦ 已成同义反复"
    )
    assert re.fullmatch(r"[0-9a-f]{7,40}", TABLES_ANCHOR_SHA), TABLES_ANCHOR_SHA
    assert b"\r" not in r304_git_blob(TABLES_ANCHOR_SHA), "git blob 层应当恒 LF：层口径变了"


# ---------------------------------------------------------------- ③ 一把尺子扫两枚件


_HEXISH = re.compile(r"[0-9a-f]{32,}")


def test_no_hand_copied_digest_literal_survives_in_either_file():
    """这族病第二次复发时抄的就是一串 hex：两枚件里不许再有 32 位以上的 hex 字符串常量。

    只管**会执行的那一层**（字符串常量，含 docstring）；注释里留旧账原文是给下一班对账用的
    （判据②要的"为什么原来是红的"凭据），不在这枚棘轮的射程里。
    """
    offenders = []
    for path in (R298, R304):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _HEXISH.fullmatch(node.value.strip()):
                    offenders.append("%s:%d %s…" % (path.name, node.lineno, node.value[:12]))
    assert not offenders, "手抄指纹回来了：" + " / ".join(offenders)


#: 今天仍留在两枚件里的「抄一句源文本当判据」枚数：只准降，不许升。
LITERAL_SOURCE_PIN_RATCHET = 1
#: 唯一那枚残留 = R298 判据⑥(a) 里 parse_status 那一格。它与本单同族，但靶不在 R351 的刀口上
#: （削它会把「no_text_content ⇒ failed」这条映射一起削掉），已按"只报不改"回报总控。
LITERAL_SOURCE_PIN_ALLOWED = frozenset(
    {'parse_status="failed" if eligibility.reason == REASON_NO_TEXT else "ready",'}
)


def _literal_source_pins(path):
    """扫一件：找出所有「字面文本 in 某枚 *_SOURCE」形状的断言。"""
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


def test_copying_a_line_of_source_text_into_a_pin_does_not_come_back():
    """棘轮：R351 把那一格换掉之后，两枚件里这种形状只剩账上那一枚，不许再长。"""
    found = _literal_source_pins(R298) + _literal_source_pins(R304)
    assert len(found) <= LITERAL_SOURCE_PIN_RATCHET, "多长了一枚抄源文本的判据：" + repr(found)
    assert {lit for _name, _line, lit in found} <= LITERAL_SOURCE_PIN_ALLOWED, (
        "这一格不在已登记的残留名单里：" + repr(found)
    )


def test_neither_file_was_quietened_with_a_skip_or_an_xfail():
    """本单明令不许 skip / xfail / 删件：这两枚件的钉必须真的会被跑到。"""
    for path in (R298, R304):
        text = path.read_text(encoding="utf-8")
        for needle in ("xfail", "skipif", "@pytest.mark.skip", "pytest.skip("):
            assert needle not in text, "%s 里出现了 %s" % (path.name, needle)
    names = {
        node.name
        for node in ast.walk(ast.parse(R304.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
    }
    missing = [name for name in R352_NAILS if name not in names]
    assert not missing, "R352 的腿缺了：" + " / ".join(missing)


def test_the_r298_leg_reads_the_ruler_not_the_old_copy():
    """判据②的凭据（常驻）：那一格里旧钉原文不许以任何形式回来，形状尺必须真在被调用。"""
    body = inspect.getsource(counter_a)
    assert "assert_upload_leg_parses_off_the_event_loop(CHAT_SOURCE)" in body
    assert 'assert "content = await asyncio.to_thread' not in body, "旧钉（抄 chat.py 字面文本）回来了"
    assert "parse_status=" in body, "同一枚件里那条映射的核对被顺手削了"
