# -*- coding: utf-8 -*-
r"""R353 判据①②③ · 每页原因都不同时，退化说明也必须有可证的长度界。

病灶（基点 `a7ac040` 现取，`app/api/v1/chat.py::_receipt_degradation_note`）：R347（`5084fdf`）把
「同一枚 reason 复述 300 遍」折成一句，但**没有同因复述**那一支走的是恒等路径 —— 尺子句
（``loader.PdfExtractionReport.degradation_sentence``）原样搬。400 枚**各不相同**的 reason 每堆
恰好只有一枚页，全落在那一支上：页码上限一个字都不咬，长度仍然跟着原因类数线性涨。R347 交付时
自己登记了这一格，本单收它。

三条判据逐枚对位：

  · 判据①：上限是 ``chat.PDF_DEGRADATION_REASON_GROUP_CAP`` 这枚**具名模块级常量**，与 R347 那枚
    页码上限并排在同一处；本件另拿 AST 量「回执层里没有第二枚裸写的数字」。
  · 判据②：超限那一格说实话 —— 「另有 N 类原因未逐条列出」，N 是**真剩余数**；省略号不许冒充
    说完了；「这一格有退化」不许跟着一起省略。页级明细（loader 逐页账 + 回执里
    ``ocr_degraded_page_numbers``）一枚不少，「哪几页坏了」照样问得出来。
  · 判据③：界必须是**算出来的**：``_note_char_bound()`` 按「句头 + ： + M 段 + (M-1) 枚分号 +
    收口那一句」相加，其中每段 = 「第」+ cap 枚页码（每枚 ``page_digits`` 位）+ (cap-1) 枚顿号 +
    「页」+「，另有 」+ 剩余页数的位数 +「 页未列出」+「：」+ 该类 reason 原文。M 与 cap 都从
    被测模块现取，件里零枚观测数当上界。为什么它对任意输入成立：回执能画出的段**不超过 M 段**，
    每段的长度**逐项不超过上式**（页码位数被 ``page_digits`` 界住、页码枚数被 cap 界住、reason 长度
    被全账最长那枚界住），唯一随类数增长的量是「另有 N 类」里 N 的十进制位数 —— 另有一枚钉子
    专量这一句，还有一枚钉子量「式子里的格式碎片确实是代码在用的那几枚」，防公式悄悄失效。

四把反证（只落 ``tests/_temp_edit_overlay.py`` 的影子根，盘上 ``chat.py`` 全程只读，进出各取一次
sha256）：刀1 摘封顶（恒等搬尺子句）；刀2 把「另有 N 类」换成省略号；刀3 把上限调到 1 而不动页级
账；刀4 在刀3 之上把「有退化」整个省略。每把逐枚报红名与绿名，不报总数。
"""
from __future__ import annotations

import ast
import hashlib
import re
from contextlib import contextmanager
from pathlib import Path

from app.api.v1 import chat
from app.rag import loader
from app.rag import ocr as ocr_channel
from app.rag.loader import PAGE_SOURCE_TEXT_LAYER
from tests import _temp_edit_overlay as overlay
from tests.test_r347_degradation_note_merges_by_reason import (
    _cell,
    _degraded,
    _head,
    _note,
    _omitted,
    _page,
    _report,
    _segments,
    _shown_pages,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAT_PY = REPO_ROOT / "app" / "api" / "v1" / "chat.py"
CHAT_REL = "app/api/v1/chat.py"
LOADER_PY = REPO_ROOT / "app" / "rag" / "loader.py"
LOADER_SOURCE = LOADER_PY.read_text(encoding="utf-8")
CONTRACT = REPO_ROOT / "docs" / "api" / "contract-v1.md"

GROUP_CAP_NAME = "PDF_DEGRADATION_REASON_GROUP_CAP"
PAGE_CAP_NAME = "PDF_DEGRADATION_PAGE_LIST_CAP"

#: 超限那一句的形状（判据② 唯一的取样器）：只有真剩余数，没有修辞。
GROUP_OMIT = re.compile(r"；另有 (\d+) 类原因未逐条列出$")
FAKE_DONE = ("…", "...", "……", "等等", "以此类推")


def _group_cap() -> int:
    """上限**现取**：反证刀把那枚常量调成 1，本件的期望值必须跟着走，不然量的是回忆。"""
    return getattr(chat, GROUP_CAP_NAME)


def _page_cap() -> int:
    return getattr(chat, PAGE_CAP_NAME)


def _groups_of(report) -> list:
    return chat._degradation_reason_groups(report)


def _chat_source() -> str:
    """**当前该算数的那份** ``chat.py``：窗外是盘上的被跟踪文件，窗内是影子根里的变异体。

    AST 那三枚钉必须读这一枚，否则反证刀改的是影子副本、钉却在看盘上的字 —— 那正是
    「变异跑了、判据没跟上」的假绿（``tests/test_r303_pg_upsert_leg.py`` 同一手法）。
    """
    return overlay.authoritative_text(CHAT_REL)


def _function_source(name: str) -> str:
    """从 ``_chat_source()`` 里取一枚函数的原文（比 ``inspect.getsource`` 诚实：它跟着窗走）。"""
    text = _chat_source()
    node = next(
        (item for item in ast.parse(text).body if isinstance(item, ast.FunctionDef) and item.name == name),
        None,
    )
    assert node is not None, "chat.py 里找不到 %s：这把尺子当场失效" % name
    return ast.get_source_segment(text, node) or ""


# ------------------------------------------------------------------ 造账：每类一枚页、reason 定宽


def _reason(index: int) -> str:
    """定宽 reason（含全角冒号，与 loader 真会产出的那几句同形）：宽度恒定，长度差才只随位数走。"""
    return f"降级原因 {index:04d}：栅格化失败 RuntimeError({index:04d})"


def _classes(count: int, *, start_page: int = 100, **kwargs):
    """``count`` 枚互不相同的 reason，每枚只命中一页（页号三位，界的位数项可隔离）。"""
    pages = [_degraded(start_page + index, _reason(index)) for index in range(count)]
    return _report(pages, **kwargs)


def _group_omitted(note: str):
    """回执里没逐条列出的类数；这一格压根没写就是 ``None``（不许当成 0）。"""
    match = GROUP_OMIT.search(note)
    return int(match.group(1)) if match else None


def _listed(note: str, report) -> list:
    """逐条列出的那几段（超限那一句不是段，不许混进来）。"""
    return _segments(GROUP_OMIT.sub("", note), _head(report))


# ------------------------------------------------------------------ 判据③ 的尺子：可算的上界


def _note_char_bound(report, *, group_cap=None, page_cap=None, head=None) -> int:
    """「最多 M 类 × 每类最长可能句」那枚上界，逐项相加，不掺观测数。"""
    groups = _groups_of(report)
    assert groups, "空账没有界可算：先造有降级的账再叫这枚尺子"
    group_cap = _group_cap() if group_cap is None else group_cap
    page_cap = _page_cap() if page_cap is None else page_cap
    head = _head(report) if head is None else head
    page_digits = max(len(str(number)) for _text, numbers in groups for number in numbers)
    omitted_page_digits = max(len(str(max(0, len(numbers) - page_cap))) for _r, numbers in groups)
    reason_chars = max(len(reason) for reason, _numbers in groups)
    segment = (
        len("第")
        + page_cap * page_digits + (page_cap - 1) * len("、")
        + len("页")
        + len("，另有 ") + omitted_page_digits + len(" 页未列出")
        + len("：")
        + reason_chars
    )
    omitted_groups = max(0, len(groups) - group_cap)
    tail = 0 if not omitted_groups else (
        len("；另有 ") + len(str(omitted_groups)) + len(" 类原因未逐条列出")
    )
    return len(head) + len("：") + group_cap * segment + max(0, group_cap - 1) * len("；") + tail


# ------------------------------------------------------------------ 判据①：具名常量，不是散落数字


def test_the_reason_cap_is_a_named_module_constant():
    """判据①：上限是模块级具名常量（与 R347 那枚页码上限同写法），不是就地抄的数字。"""
    tree = ast.parse(_chat_source())
    module_targets = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert GROUP_CAP_NAME in module_targets
    assert _group_cap() == getattr(chat, GROUP_CAP_NAME), "上限不活在模块上：本件量的就是别处的一枚数"
    declared = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == GROUP_CAP_NAME for target in node.targets)
    )
    assert isinstance(declared.value, ast.Constant) and isinstance(declared.value.value, int), (
        "上限必须是服务端自己立的整数常量，不许从配置或环境里读"
    )
    assert 0 < _group_cap() < 20, "这一格是给人扫读的散文：上限不许放宽成一屏放不下的一串"


def test_the_two_caps_are_written_the_same_way_in_the_same_place():
    """判据①「照 ``PDF_DEGRADATION_PAGE_LIST_CAP`` 的写法与位置」：两枚赋值在模块顶层并排。"""
    tree = ast.parse(_chat_source())
    statements = list(tree.body)

    def index_of(name):
        return next(
            position
            for position, node in enumerate(statements)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
        )

    page_at = index_of(PAGE_CAP_NAME)
    reason_at = index_of(GROUP_CAP_NAME)
    first_def_at = next(
        position
        for position, node in enumerate(statements)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and position > page_at
    )

    assert reason_at == page_at + 1, "两枚上限不并排：后来人会往别处再立一枚第二套数"
    assert reason_at < first_def_at, "上限必须活在模块顶层，不许沉进函数体里"


def test_no_cap_is_written_as_a_bare_literal_in_the_note_layer():
    """判据① 的下半句：回执层那三枚函数里一枚裸写的数字都没有，切片一律拿具名常量。"""
    tree = ast.parse(_chat_source())
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    note = functions["_receipt_degradation_note"]

    slices = [node for node in ast.walk(note) if isinstance(node, ast.Slice)]
    assert slices, "回执层没有切片了：封顶不在这层落地（那就是把尺子句恒等搬回去）"
    named = {slice_node.upper.id for slice_node in slices if isinstance(slice_node.upper, ast.Name)}
    assert named == {GROUP_CAP_NAME}, "切片不是拿具名常量收口的：%s" % sorted(named)
    assert not [
        slice_node for slice_node in slices if not isinstance(slice_node.upper, ast.Name)
    ], "切片的上界出现了非具名常量：上限又被就地写死了"

    segment = functions["_degradation_segment"]
    segment_slices = [node for node in ast.walk(segment) if isinstance(node, ast.Slice)]
    assert {item.upper.id for item in segment_slices if isinstance(item.upper, ast.Name)} == {PAGE_CAP_NAME}, (
        "页码那一档的上限不再拿具名常量收口"
    )

    for name in ("_degradation_segment", "_degradation_groups_tail"):
        bare = [
            node.value
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool)
        ]
        assert not bare, "%s 里裸写了数字 %s：上限必须是具名常量" % (name, bare)

    singles = [
        node.value
        for node in ast.walk(note)
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool)
    ]
    assert singles == [1], "这一层唯一的整数应当是「每堆一枚页」那枚 1，实取 %s" % singles
    holder = next(
        node
        for node in ast.walk(note)
        if isinstance(node, ast.Compare)
        and any(isinstance(item, ast.Constant) and item.value == 1 for item in node.comparators)
    )
    assert ast.unparse(holder) == "len(numbers) == 1", "那枚 1 不再是为「每堆一枚页」说话：本钉要重看"


# ------------------------------------------------------------------ 判据②：超限那张脸说实话


def test_classes_over_the_cap_are_cut_and_the_rest_is_counted_for_real():
    """判据②：超过上限只逐条列前 M 类，其余报**真**剩余类数。"""
    cap = _group_cap()
    total = cap + 7
    report = _classes(total)
    note = _note(report)

    assert len(_listed(note, report)) == cap
    assert _group_omitted(note) == total - cap, "N 必须是真剩余类数"


def test_the_omitted_class_count_is_never_the_number_of_classes_listed():
    """判据② 的反面：N 拿「画下来的类数」冒充（= M）当场红。"""
    cap = _group_cap()
    total = cap * 3
    note = _note(_classes(total))

    assert _group_omitted(note) == total - cap
    assert _group_omitted(note) != cap, "「另有 N 类」说的是没列出的那些，不是列出的这些"


def test_the_capped_note_never_pretends_to_be_finished_with_an_ellipsis():
    """判据②：省略号是「装作说完了」，这里只许出现带数的收口句。"""
    note = _note(_classes(_group_cap() + 2))

    for fake in FAKE_DONE:
        assert fake not in note, "回执用 %r 冒充说完了：%s" % (fake, note)
    assert GROUP_OMIT.search(note), "超限却没有「另有 N 类原因未逐条列出」：%s" % note


def test_the_capped_note_still_claims_the_degradation_it_truncated():
    """判据②：封顶只截句子，不许把「这一格有退化」整个省略掉。"""
    report = _classes(_group_cap() + 2)
    note = _note(report)

    assert note, "超限那一格变成空串 = 回执不再声称有退化，那正是判据点名要禁的形状"
    assert note.startswith("%s：" % _head(report)), note
    assert _group_omitted(note) == 2


def test_at_exactly_the_cap_the_ruler_still_ships_verbatim():
    """判据② 的另一半（R347 恒等那支没被削）：类数不超上限时尺子那句原样搬。"""
    report = _classes(_group_cap())
    note = _note(report)

    assert note == report.degradation_sentence
    assert _group_omitted(note) is None, "一枚都没省略，不许造「另有 0 类」"


def test_one_class_over_the_cap_switches_to_the_capped_face():
    """边界：刚好超一枚就得换脸（恒等那支只在类数不超上限时走）。"""
    cap = _group_cap()
    report = _classes(cap + 1)
    note = _note(report)

    assert _group_omitted(note) == 1
    assert len(_listed(note, report)) == cap
    assert note != report.degradation_sentence


def test_the_listed_classes_are_the_first_ones_in_page_order_with_verbatim_reasons():
    """判据②④：列出来的是「从前往后」前 M 类，reason 原文一个字不改。"""
    cap = _group_cap()
    report = _classes(cap + 5)
    segments = _listed(_note(report), report)

    assert [reason for _label, reason in segments] == [_reason(index) for index in range(cap)]
    assert [_shown_pages(label) for label, _text in segments] == [[100 + index] for index in range(cap)]


def test_a_class_that_also_overflows_pages_reports_both_remainders():
    """两枚上限同时生效：页码那一档与原因类数那一档各报各的真剩余数，互不冒充。"""
    page_cap = _page_cap()
    heavy = [_degraded(100 + index, _reason(0)) for index in range(page_cap + 20)]
    others = [_degraded(200 + index, _reason(index + 1)) for index in range(_group_cap() + 3)]
    report = _report(heavy + others)
    note = _note(report)

    segments = _listed(note, report)
    assert _omitted(segments[0][0]) == 20, "页码那一档的 N 要还是真剩余数"
    assert _group_omitted(note) == 4, "类数那一档只报没列出的那四类"


def test_the_capped_note_keeps_the_tier_head_it_owes():
    """判据③（R347）不许被封顶削回去：引擎不可用那一档还是自己的句头。"""
    report = _classes(_group_cap() + 2, ocr_available=False)
    note = _note(report)

    assert note.startswith(ocr_channel.ENGINE_UNAVAILABLE_NOTE)
    assert loader.DEGRADATION_NOTE_PREFIX not in note


# ------------------------------------------------------------------ 判据② 的下半句：页级账一枚不少


def test_the_per_page_book_still_answers_which_pages_are_broken():
    """判据②：封顶截的是那句话，不是那本账 —— 「哪几页坏了」照样问得出来。"""
    total = 400
    report = _classes(total)
    cell = _cell(report)

    assert cell["ocr_degraded_page_numbers"] == [100 + index for index in range(total)]
    assert len(cell["ocr_degraded_page_numbers"]) > 3 * _group_cap(), "句里只列 M 类，账里一枚不少"
    assert report.degradation_notes == tuple(
        "第%d页：%s" % (100 + index, _reason(index)) for index in range(total)
    )


def test_the_loader_page_book_is_still_per_page_and_untouched():
    """判据② 点名 ``app/rag/loader.py`` 一行不许动：逐页那本账仍然是逐页的。"""
    report = _classes(3)

    assert len(report.degradation_notes) == 3
    assert 'f"第{page.page_number}页：{page.note}"' in LOADER_SOURCE
    assert "return f\"{head}：{'；'.join(notes)}\"" in LOADER_SOURCE


def test_no_degraded_page_is_still_an_empty_string_with_the_cap_in_place():
    """判据② 不许伤到「没有退化」那一格：仍是空串，不是 ``None``、不是新造的客气话。"""
    report = _report([_page(1, PAGE_SOURCE_TEXT_LAYER), _page(2, PAGE_SOURCE_TEXT_LAYER)])

    assert _note(report) == ""
    assert _group_omitted(_note(report)) is None


# ------------------------------------------------------------------ 判据③：界是算出来的


def test_the_note_length_is_bounded_by_the_formula():
    """判据③：任意输入下 ``len(note) <= 界``，界只由具名常量与这本账自己的参数决定。"""
    for total in (_group_cap() + 1, 2 * _group_cap(), 60, 400):
        report = _classes(total)
        bound = _note_char_bound(report)
        assert len(_note(report)) <= bound, "%d 类：%d > 界 %d" % (total, len(_note(report)), bound)


def test_the_uncapped_ruler_sentence_breaks_that_bound():
    """判据③ 的另一半：不封顶那一形确实越界 —— 封顶在咬，不是摆设。"""
    report = _classes(400)
    bound = _note_char_bound(report)

    assert len(report.degradation_sentence) > bound, "尺子句不越界，这单就没有可证的界可收"
    assert len(_note(report)) <= bound < len(report.degradation_sentence)


def test_the_bound_and_the_note_grow_only_with_the_remainder_digits():
    """判据③：类数从 cap+1 涨到 400，界与实句都只随「剩余数的位数」涨，不随类数线性涨。"""
    cap = _group_cap()
    small, big = _classes(cap + 1), _classes(400)
    bound_small, bound_big = _note_char_bound(small), _note_char_bound(big)
    digits_delta = len(str(400 - cap)) - len(str(1))

    assert bound_big - bound_small == digits_delta, "界随类数线性涨：%d -> %d" % (bound_small, bound_big)
    assert len(_note(big)) - len(_note(small)) == digits_delta
    assert len(_note(big)) <= bound_big and len(_note(small)) <= bound_small


def test_the_ruler_itself_has_teeth():
    """判据③ 的自检：M 与 cap 真在式子里 —— 放大它们界就放大，式子也盖得住不封顶那一形。"""
    report = _classes(_group_cap() * 4)
    groups = len(_groups_of(report))
    bound_live = _note_char_bound(report)
    bound_all = _note_char_bound(report, group_cap=groups)

    assert bound_all > bound_live, "把 M 放大到类数而界不动：说明 M 根本没进式子"
    assert bound_all >= len(report.degradation_sentence), "公式盖不住不封顶那一形：它不是那件东西的界"
    assert _note_char_bound(report, group_cap=1) <= bound_live
    assert _note_char_bound(report, page_cap=_page_cap() + 5) > bound_live, "页码上限同理必须活在式子里"


def test_the_bound_formula_tracks_the_code_it_bounds():
    """判据③ 的反漂移钉：式子里那些格式碎片，必须真是代码在用的那几枚。"""
    segment_src = _function_source("_degradation_segment")
    tail_src = _function_source("_degradation_groups_tail")
    note_src = _function_source("_receipt_degradation_note")

    assert 'f"第{label}页{tail}：{reason}"' in segment_src
    assert 'f"，另有 {omitted} 页未列出"' in segment_src
    assert '"、".join(' in segment_src
    assert 'f"；另有 {omitted_groups} 类原因未逐条列出"' in tail_src
    assert 'f"{head}：{body}' in note_src
    assert '"；".join(' in note_src


# ------------------------------------------------------------------ 判据② 的契约半边


def test_the_contract_names_the_class_cap_and_the_honest_tail():
    """契约必须写清第二枚上限与超限那张脸（与 R347 同一口径，历史节一字未动）。"""
    text = CONTRACT.read_text(encoding="utf-8")

    assert GROUP_CAP_NAME in text
    assert "%s = " % GROUP_CAP_NAME in text
    assert "类原因未逐条列出" in text
    assert "ocr_degraded_page_numbers" in text


# ------------------------------------------------------------------ 反证窗：变异只落影子根

CAP_ASSIGN = "%s = 10" % GROUP_CAP_NAME
CAP_AS_ONE = "%s = 1" % GROUP_CAP_NAME
SLICE_ANCHOR = "    shown_groups = groups[:%s]" % GROUP_CAP_NAME
SLICE_REMOVED = "    shown_groups = groups"
TAIL_RETURN = '    return f"；另有 {omitted_groups} 类原因未逐条列出" if omitted_groups else ""'
TAIL_AS_ELLIPSIS = '    return "…" if omitted_groups else ""'
IDENTITY_IF = "    if not omitted_groups and all(len(numbers) == 1 for _reason, numbers in groups):"
OVER_CAP_GOES_SILENT = '    if omitted_groups:\n        return ""\n' + IDENTITY_IF


class _R353Edit(overlay.ShadowEdit):
    """一扇 R353 的反证窗：锚点命中不是恰好一处，变异整片不落影子；文本先过 compile()。"""

    tag = "r353"
    execs_module = True

    def __init__(self, path: Path, edits) -> None:
        super().__init__(path)
        self.edits = [(old, new) for old, new in edits]

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        mutated = text
        for old, new in self.edits:
            needle = old.replace(chr(10), newline)
            hits = mutated.count(needle)
            assert hits == 1, "%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落盘" % (
                self.path.name, hits, old[:60])
            mutated = mutated.replace(needle, new.replace(chr(10), newline), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _window(edits):
    """开一扇窗，把变异 exec 进 ``app.api.v1.chat``，出门由基类逐字节还原视图。"""
    module = overlay.module_of(CHAT_REL)
    assert module is not None, "app.api.v1.chat 还没被导入，exec 无处可落"
    with _R353Edit(CHAT_PY, edits) as info:
        yield info


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: 判据正文（反证刀要在窗内逐枚复跑它们，报哪几枚红、哪几枚绿）。
PINS = (
    test_the_reason_cap_is_a_named_module_constant,
    test_the_two_caps_are_written_the_same_way_in_the_same_place,
    test_no_cap_is_written_as_a_bare_literal_in_the_note_layer,
    test_classes_over_the_cap_are_cut_and_the_rest_is_counted_for_real,
    test_the_omitted_class_count_is_never_the_number_of_classes_listed,
    test_the_capped_note_never_pretends_to_be_finished_with_an_ellipsis,
    test_the_capped_note_still_claims_the_degradation_it_truncated,
    test_at_exactly_the_cap_the_ruler_still_ships_verbatim,
    test_one_class_over_the_cap_switches_to_the_capped_face,
    test_the_listed_classes_are_the_first_ones_in_page_order_with_verbatim_reasons,
    test_a_class_that_also_overflows_pages_reports_both_remainders,
    test_the_capped_note_keeps_the_tier_head_it_owes,
    test_the_per_page_book_still_answers_which_pages_are_broken,
    test_the_loader_page_book_is_still_per_page_and_untouched,
    test_no_degraded_page_is_still_an_empty_string_with_the_cap_in_place,
    test_the_note_length_is_bounded_by_the_formula,
    test_the_uncapped_ruler_sentence_breaks_that_bound,
    test_the_bound_and_the_note_grow_only_with_the_remainder_digits,
    test_the_ruler_itself_has_teeth,
    test_the_bound_formula_tracks_the_code_it_bounds,
)


def _tally():
    """把每一枚判据在**当前该算数的那份代码**上跑一遍，逐枚记红名与绿名（不报总数）。"""
    red, green = [], []
    for pin in PINS:
        try:
            pin()
        except AssertionError:
            red.append(pin.__name__)
        else:
            green.append(pin.__name__)
    return red, green


def _print_tally(knife: str, red: list, green: list) -> None:
    print("[r353] %s 红 %d 枚：%s" % (knife, len(red), sorted(red)))
    print("[r353] %s 绿 %d 枚：%s" % (knife, len(green), sorted(green)))


def test_counter_evidence_1_removing_the_class_cap_goes_red():
    """刀1：把封顶摘掉（恒等搬尺子句）⇒ 界与「只列 M 类」双双红，页级账仍绿。"""
    tracked = _sha(CHAT_PY)
    with _window([(SLICE_ANCHOR, SLICE_REMOVED)]) as info:
        red, green = _tally()
        report = _classes(400)
        assert len(_note(report)) == len(report.degradation_sentence), "刀1 没走恒等路径，反证无从谈起"
        must_red = (
            "test_the_note_length_is_bounded_by_the_formula",
            "test_the_bound_and_the_note_grow_only_with_the_remainder_digits",
            "test_classes_over_the_cap_are_cut_and_the_rest_is_counted_for_real",
            "test_no_cap_is_written_as_a_bare_literal_in_the_note_layer",
        )
        missing = [name for name in must_red if name not in red]
        assert not missing, "刀1 少红：%s" % missing
        assert "test_the_per_page_book_still_answers_which_pages_are_broken" in green
        assert _sha(CHAT_PY) == tracked, "被跟踪的 chat.py 在反证窗里被改过"
        _print_tally("刀1 摘封顶", red, green)
    assert info["restored"], "刀1 没还原"
    print("[r353] 刀1 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_counter_evidence_2_an_ellipsis_that_pretends_to_be_done_goes_red():
    """刀2：把「另有 N 类」换成省略号 ⇒ 红在说实话那几枚；界那几枚照旧绿（它量长度不量诚实）。"""
    tracked = _sha(CHAT_PY)
    with _window([(TAIL_RETURN, TAIL_AS_ELLIPSIS)]) as info:
        red, green = _tally()
        must_red = (
            "test_the_capped_note_never_pretends_to_be_finished_with_an_ellipsis",
            "test_classes_over_the_cap_are_cut_and_the_rest_is_counted_for_real",
            "test_the_omitted_class_count_is_never_the_number_of_classes_listed",
            "test_the_capped_note_still_claims_the_degradation_it_truncated",
            "test_the_bound_formula_tracks_the_code_it_bounds",
        )
        missing = [name for name in must_red if name not in red]
        assert not missing, "刀2 少红：%s" % missing
        must_green = (
            "test_the_note_length_is_bounded_by_the_formula",
            "test_the_per_page_book_still_answers_which_pages_are_broken",
        )
        hurt = [name for name in must_green if name not in green]
        assert not hurt, "界与页级账不该被这刀伤到：%s" % hurt
        assert _sha(CHAT_PY) == tracked
        _print_tally("刀2 省略号冒充", red, green)
    assert info["restored"], "刀2 没还原"
    print("[r353] 刀2 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_counter_evidence_3_a_cap_of_one_still_leaves_the_page_book_answerable():
    """刀3：上限调到 1 且不动页级账 ⇒ 判据**零红**，「哪几页坏了」仍然一枚不少地答得出来。"""
    tracked_chat, tracked_loader = _sha(CHAT_PY), _sha(LOADER_PY)
    with _window([(CAP_ASSIGN, CAP_AS_ONE)]) as info:
        red, green = _tally()
        assert red == [], "上限调到 1 就红，说明判据抄的是今天那枚数而不是式子：%s" % red
        report = _classes(400)
        cell = _cell(report)
        note = _note(report)
        assert cell["ocr_degraded_page_numbers"] == [100 + index for index in range(400)], "页级账被削了"
        assert len(_listed(note, report)) == 1 and _group_omitted(note) == 399
        assert _sha(CHAT_PY) == tracked_chat and _sha(LOADER_PY) == tracked_loader
        _print_tally("刀3 上限=1", red, green)
    assert info["restored"], "刀3 没还原"
    print("[r353] 刀3 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_counter_evidence_4_a_capped_note_that_stops_claiming_degradation_goes_red():
    """刀4：在刀3 之上让超限那一格直接答空 ⇒ 红在「回执仍须声称有退化」，页级账照旧绿。"""
    tracked_loader = _sha(LOADER_PY)
    with _window([(CAP_ASSIGN, CAP_AS_ONE), (IDENTITY_IF, OVER_CAP_GOES_SILENT)]) as info:
        red, green = _tally()
        must_red = (
            "test_the_capped_note_still_claims_the_degradation_it_truncated",
            "test_classes_over_the_cap_are_cut_and_the_rest_is_counted_for_real",
            "test_the_capped_note_never_pretends_to_be_finished_with_an_ellipsis",
        )
        missing = [name for name in must_red if name not in red]
        assert not missing, "刀4 少红：%s" % missing
        assert "test_the_per_page_book_still_answers_which_pages_are_broken" in green, (
            "页级账跟着红：那一本不是本刀动的")
        assert _sha(LOADER_PY) == tracked_loader, "反证刀碰到了 loader：判据② 点名的禁区"
        _print_tally("刀4 超限答空", red, green)
    assert info["restored"], "刀4 没还原"
    print("[r353] 刀4 RESTORED=%s sha=%s" % (info["restored"], info["after"]))


def test_the_counter_evidence_windows_touch_no_tracked_file():
    """反证窗自己的纪律：``chat.py`` / ``loader.py`` / 契约的 sha256 全程恒定，窗里只许有 chat.py 一枚。"""
    targets = (CHAT_PY, LOADER_PY, CONTRACT)
    digests = {path: _sha(path) for path in targets}

    assert overlay.open_windows() == (), "窗外还有开着的反证窗：上一把没关"
    with _window([(SLICE_ANCHOR, SLICE_REMOVED)]) as info:
        assert overlay.open_windows() == (CHAT_REL,), overlay.open_windows()
        assert _sha(CHAT_PY) == digests[CHAT_PY], "窗里盘上那枚被改过：影子根没接住"
    assert info["restored"] and info["shadow_clean"]
    assert overlay.open_windows() == ()
    for path, digest in digests.items():
        assert _sha(path) == digest, "%s 被反证窗碰过" % path.name
    print("[r353] 窗纪律 RESTORED=%s sha=%s" % (info["restored"], info["after"]))
