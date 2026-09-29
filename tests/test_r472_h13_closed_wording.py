# -*- coding: utf-8 -*-
r"""R472：H13 已经结案，仓里那两处「还没裁」的假话必须绝迹——而登记表的牙一格都不许少。

依据（本单全部依据，不靠摘要）：`docs/handoff/2026-09-17-human-gates.md` 最后一节
「H13 结案 ＋ A1/A3 裁定」＝业主 2026-09-28 裁定甲（未标注密级的上传按 1 级入库＝契约口径，
不再是待裁项），口径已写进契约 `docs/api/contract-v1.md`「## R467」节。改前盘上现读：
`app/agents/tools.py` 里有三处、`tests/test_error_code_vocabulary.py` 里有七处仍把它写成
「H13 未裁／业主未定／等业主定」的形状，另两处是同族但不带 H13 字样的写法（「没裁的维度」
「口径没裁」）。那是假话，会诱导下一班把已结案的事再报一遍。

本件钉四格，每一格都能失败：
  甲 那一族字样在两枚被钉文件里命中为 0；
  乙 每一处改口都同时点名**裁定出处**与**契约出处**（缺一枚就红）；
  丙 欠账码仍是欠账码：键还在 DEFERRED、不许进 RATIFIED、不许进枚举，RATIFIED 键集与改前
     逐字相等，承担密级拒绝的两枚在册码还在裸码表里，且 `app/**` 任何位置都不许写出这枚
     码名——那枚 emit 点扫描器把注释也算成出处；
  丁 `department_column_missing` 那一支仍然不报因由、码仍然落 `no_visible_rows`
     （契约「## R467」节明写：换掉的只是理由，行为一个字没变）。
反证七刀一律落 `tests/_temp_edit_overlay.py` 的影子根或就地换函数，被跟踪文件全程只读。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents import tools
from tests import _temp_edit_overlay as overlay
from tests import test_error_code_vocabulary as vocab

REPO = overlay.REPO
TOOLS_REL = "app/agents/tools.py"
VOCAB_REL = "tests/test_error_code_vocabulary.py"
PENDING_CODE = "classification_blocked"

#: 「H13 还悬着」那一族字样（与在册钉 test_r467 的 OPEN_QUESTION_PATTERNS 同族再加宽）。
OPEN_H13_PATTERNS = (
    r"H13[^\n]{0,40}(未裁|未定|未决|待裁|待业主|还悬|尚未|裁完)",
    r"(业主|口径)[^\n]{0,12}(尚未裁|未裁|未定|未决|没裁|没定)[^\n]{0,12}H13",
    r"(等|待)\s*H13",
    r"H13\s*的裁定",
)
#: 同族但不带 H13 字样的两枚写法（tools.py 的码层注释、守卫自己的 docstring）。
OPEN_SHAPE_PATTERNS = (
    r"没裁的维度",
    r"口径没裁",
)
ALL_OPEN_PATTERNS = OPEN_H13_PATTERNS + OPEN_SHAPE_PATTERNS

#: 判据③的出处标记：一枚都不许少。
RULING_MARKS = ("2026-09-28", "human-gates", "H13 结案", "R467")

#: 改口位点：按锚文本点名（行号会漂，锚文本与符号不会）。
COMMENT_PLACES = (
    (TOOLS_REL, "密级这一维今天不是悬案", "映射表 _POLICY_DENIAL_CODES 上方注释块"),
    (TOOLS_REL, "但本层的计数器只有部门那一维", "R62 文案层头注释块"),
    (TOOLS_REL, "而本层只翻译部门维度的计数器", "_row_scope_reason 的 department_column_missing 支"),
    (TOOLS_REL, "不替本层没有计数器的维度下结论", "_ROW_SCOPE_PUBLIC_CODES 上方注释块"),
    (VOCAB_REL, "口径出处（R472 改口", "DEFERRED_CODES 上方注释块"),
)

#: 改前的 RATIFIED 键集：动了它就是有人顺手把欠账码洗成已追认。
RATIFIED_KEYS_BASELINE = (
    "chart_generation_failed",
    "context_limit_exceeded",
    "dataset_filename_conflict",
    "dataset_preview_failed",
    "department_scope_required",
    "invalid_filename",
    "no_answer_produced",
    "no_visible_rows",
    "row_scope_denied",
    "unsupported_chart_type",
    "unsupported_export_format",
    "validation_error",
)

#: 反证刀的弹药：锚＝改后盘上现读，替换＝改前现读过的原句（引文，不是断言）。
FAKE_OPEN_REASONS = {
    "vocab_reason": (
        VOCAB_REL,
        "# 2) 这一维的拒绝今天**已经有在册码承担**，再造一枚同义码就没有 emit 点可指：",
        "# 2) 业主尚未裁口径（H13）。",
    ),
    "tools_reason": (
        TOOLS_REL,
        "# 也不替它新增枚举成员。",
        "# 本单不许借映射表替它下结论：密级口径属 H13（业主未裁）。",
    ),
    "implemented": (
        VOCAB_REL,
        '    "classification_blocked": "零 emit 点：密级拒绝已由 clearance_insufficient / "',
        '    "classification_blocked": "已实现：检索闸门已经在吐这枚码，该移进 RATIFIED 了 / "',
    ),
    "unattributed": (
        TOOLS_REL,
        "# 「H13 结案 ＋ A1/A3 裁定」；口径已写进契约 docs/api/contract-v1.md 的「## R467」节），",
        "# 口径来源见当日跟进单，本单不再复述。",
    ),
}


def _text(rel: str) -> str:
    """当前该算数的那份字节：反证窗内读影子副本的变异版，窗外读盘上的被跟踪文件。"""
    return overlay.authoritative_text(rel).replace("\r\n", "\n")


def _open_hits(rel: str):
    hits = []
    for number, line in enumerate(_text(rel).split("\n"), 1):
        for pattern in ALL_OPEN_PATTERNS:
            found = re.search(pattern, line)
            if found:
                hits.append((number, pattern, found.group(0)))
                break
    return hits


def _comment_blocks(rel: str):
    """连续 # 行切成注释块，回 [块文本, ...]（每行去掉开头的 #）。"""
    blocks, buf = [], []
    for line in _text(rel).split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            buf.append(stripped[1:].strip())
        elif buf:
            blocks.append("\n".join(buf))
            buf = []
    if buf:
        blocks.append("\n".join(buf))
    return blocks


def _mutant_or_red(text: str) -> str:
    """变异产物必须先能编译：SyntaxError 会在 ``__enter__`` 里抛，把窗漏进 ``_WINDOWS``，
    还会让「红」来自语法坏而不是来自判据——那不是反证，是自伤。
    """
    try:
        compile(text, "<r472-counter-evidence>", "exec")
    except SyntaxError as exc:
        raise AssertionError("反证刀的产物编译不过（它红的是语法而不是判据）：%s" % exc) from exc
    return text


def _block_holding(rel: str, anchor: str) -> str:
    for block in _comment_blocks(rel):
        if anchor in block:
            return block
    raise AssertionError("锚文本不在注释块里了（改口被删或被搬走）：%s :: %r" % (rel, anchor))


class _ShadowWordEdit(overlay.ShadowEdit):
    """一扇反证窗：把一处改口换回盘上曾经写过的假话，变异只落影子根。"""

    tag = "r472"
    #: 词表件的键与值是模块级数据：要连数据一起变才量得到丙格。
    execs_module = True

    def __init__(self, knife: str) -> None:
        rel, old, new = FAKE_OPEN_REASONS[knife]
        super().__init__(REPO / rel)
        self._old = old
        self._new = new

    def mutate(self, text: str) -> str:
        count = text.count(self._old)
        if count != 1:
            raise AssertionError("反证刀的锚不唯一（%d 处）：%r" % (count, self._old[:50]))
        return _mutant_or_red(text.replace(self._old, self._new))


# ==================== 甲 · 「H13 未决」的字样在两枚被钉文件里必须绝迹 ====================

def test_no_open_question_wording_survives_in_the_two_files():
    """判据①：那一族字样命中为 0；同族但不带 H13 字样的写法一起量。"""
    bad = {rel: _open_hits(rel) for rel in (TOOLS_REL, VOCAB_REL)}
    bad = {rel: hits for rel, hits in bad.items() if hits}
    assert bad == {}, "还把 H13 写成未决：" + "; ".join(
        "%s -> %s" % (rel, [hit[2] for hit in hits]) for rel, hits in bad.items()
    )


def test_the_open_question_patterns_are_not_blind():
    """正则不许是装饰：改前的每一枚原句都得被它自己量到（以下是引文，不是断言）。"""
    samples = (
        "密级口径属 H13（业主未裁），",
        "密级维度属 H13（业主未裁口径）",
        "那个维度的口径属 H13（业主未裁）",
        "# 2) 业主尚未裁口径（H13）。",
        "等 H13 裁完、app/** 里真出现吐这个码的",
        '"H13（密级口径未裁）+ R78①（max_clearance 只存不用）"',
        "H13 未裁之前它连语义边界都还是旧的",
        "口径仍待 H13 裁定",
        "按 H13 的裁定评审",
        "登记不是注释：口径没裁、出处没有",
        "不替没裁的维度下结论",
    )
    blind = [s for s in samples if not any(re.search(p, s) for p in ALL_OPEN_PATTERNS)]
    assert blind == [], "那一族正则瞎了，量不到旧话：" + repr(blind)


# ==================== 乙 · 每一处改口都要点名两枚出处 ====================

def test_every_rewritten_comment_names_both_sources():
    """判据③：注释块里必须同时带着裁定出处与契约出处，缺一枚就红。"""
    thin = []
    for rel, anchor, where in COMMENT_PLACES:
        block = _block_holding(rel, anchor)
        lost = [mark for mark in RULING_MARKS if mark not in block]
        if lost:
            thin.append((rel, where, lost))
    assert thin == [], "改口没点名出处（裁定出处＝human-gates「H13 结案」／契约出处＝R467）：" + repr(thin)


def test_the_register_value_and_the_guard_docstring_name_both_sources():
    """登记值、承担码的 why、守卫的 docstring 也是改口位点：三处都得带着出处。"""
    targets = {
        "DEFERRED_CODES 的登记值": vocab.DEFERRED_CODES[PENDING_CODE],
        "clearance_insufficient 的 why":
            vocab.BARE_CODES_OUTSIDE_THE_ENUM["clearance_insufficient"]["why"],
        "守卫的 docstring":
            vocab.test_a_deferred_code_stays_out_of_the_enum_until_it_has_an_emit_point.__doc__ or "",
    }
    thin = {name: [m for m in RULING_MARKS if m not in text] for name, text in targets.items()}
    thin = {name: lost for name, lost in thin.items() if lost}
    assert thin == {}, "这三处改口丢了出处标记：" + repr(thin)


# ==================== 丙 · 登记表的牙：欠账码仍是欠账码 ====================

def test_the_pending_code_is_still_pending_not_implemented():
    """判据②：不许把「还没有 emit 点」写成「已实现」——值与理由两头都钉。"""
    assert list(vocab.DEFERRED_CODES) == [PENDING_CODE], "DEFERRED_CODES 的键集被改动"
    value = vocab.DEFERRED_CODES[PENDING_CODE]
    assert "emit 点" in value, "登记值不再说清「今天没有 emit 点」：" + value
    for claim in ("已实现", "已经在吐", "已落地", "已建 emit 点"):
        assert claim not in value, "登记值把它说成已实现（%r）：%s" % (claim, value)
    assert PENDING_CODE not in vocab.RATIFIED, "欠账码被塞进了追认表"
    assert PENDING_CODE not in vocab._enum_codes(), "欠账码被塞进了封闭枚举"


def test_the_codes_actually_carrying_classification_refusals_are_still_registered():
    """今天的真理由：拒由这两枚在册码承担（`app/rag/filters.py::allows` / `refusal_code`）。"""
    for carried in ("clearance_insufficient", "resource_scope_missing"):
        entry = vocab.BARE_CODES_OUTSIDE_THE_ENUM.get(carried)
        assert entry is not None, "承担密级拒绝的码不在裸码表里：%s" % carried
        assert entry["emitter"] == "app/common/policy.py::authorization_decision", entry


def test_the_ratified_keyset_did_not_move():
    """RATIFIED 键集与改前逐字相等：这条与上面那格把「改成已实现」两头夹死。"""
    assert sorted(vocab.RATIFIED) == sorted(RATIFIED_KEYS_BASELINE)


def test_the_pending_code_name_is_never_written_inside_app():
    """纪律：`app/**` 任何位置写出这枚码名（注释也算），扫描器就会替它造假出处。"""
    offenders = {}
    for path in (Path(REPO) / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if PENDING_CODE in text:
            offenders[path.as_posix()] = text.count(PENDING_CODE)
    assert offenders == {}, "app/** 里出现了欠账码名，会被 emit 点扫描器当成出处：" + repr(offenders)


# ==================== 丁 · 这一支仍然不报因由 ====================

_MISSING_COLUMN = {
    "reason_code": "department_column_missing",
    "rows_in": 7,
    "rows_hidden_by_department": 0,
    "rows_hidden_blank_department": 0,
    "rows_hidden_account_department": 0,
    "account_department": "财务",
}


def test_the_missing_department_column_branch_still_reports_no_reason():
    """契约「## R467」节退役原句 ① 那一格：仍然只报 no_visible_rows、仍然不报因由。"""
    assert tools._row_scope_reason(dict(_MISSING_COLUMN)) == "", "这一支开始替别的维度报因由了"
    assert tools._row_scope_code(dict(_MISSING_COLUMN)) == "no_visible_rows"
    line = tools._row_scope_line("经营.xlsx", dict(_MISSING_COLUMN))
    assert line.endswith(tools._NO_VISIBLE_ROWS), line


# ==================== 戊 · 反证七刀 ====================

def test_counter_evidence_1_fake_reason_back_in_the_vocabulary_goes_red():
    """刀①：词表件的理由换回「业主尚未裁口径（H13）」——甲格必须红。"""
    with _ShadowWordEdit("vocab_reason"):
        assert _open_hits(VOCAB_REL), "假理由回插了而甲格量不到：正则族瞎了"
        with pytest.raises(AssertionError) as caught:
            test_no_open_question_wording_survives_in_the_two_files()
        assert "业主尚未裁口径" in str(caught.value), str(caught.value)


def test_counter_evidence_2_fake_reason_back_in_tools_goes_red():
    """刀②：tools.py 的理由换回「密级口径属 H13（业主未裁）」——甲格必须红。"""
    with _ShadowWordEdit("tools_reason"):
        assert _open_hits(TOOLS_REL), "假理由回插了而甲格量不到"
        with pytest.raises(AssertionError) as caught:
            test_no_open_question_wording_survives_in_the_two_files()
        assert "H13（业主未裁" in str(caught.value), str(caught.value)


def test_counter_evidence_3_claiming_it_is_implemented_goes_red():
    """刀③：登记值改写成「已实现」——丙格红（键没动也红，不靠一句注释）。"""
    with _ShadowWordEdit("implemented"):
        assert vocab.DEFERRED_CODES[PENDING_CODE].startswith("已实现"), "影子根没生效"
        with pytest.raises(AssertionError) as caught:
            test_the_pending_code_is_still_pending_not_implemented()
        assert "已实现" in str(caught.value), str(caught.value)


def test_counter_evidence_4_dropping_the_attribution_goes_red():
    """刀④：删掉一处改口的两枚出处——乙格红。"""
    with _ShadowWordEdit("unattributed"):
        with pytest.raises(AssertionError) as caught:
            test_every_rewritten_comment_names_both_sources()
        assert "出处" in str(caught.value), str(caught.value)


def test_counter_evidence_5_pending_code_entering_the_enum_goes_red():
    """刀⑤：把欠账码塞进封闭枚举——在册守卫自己会红，且红话点名契约出处。"""
    original = vocab._enum_codes

    def _widened():
        return frozenset(set(original()) | {PENDING_CODE})

    vocab._enum_codes = _widened
    try:
        with pytest.raises(AssertionError) as caught:
            vocab.test_a_deferred_code_stays_out_of_the_enum_until_it_has_an_emit_point(PENDING_CODE)
        message = str(caught.value)
        assert "还没有 emit 点" in message, message
        assert "R467" in message, "红话不再点名契约出处：" + message
        with pytest.raises(AssertionError):
            test_the_pending_code_is_still_pending_not_implemented()
    finally:
        vocab._enum_codes = original


def test_counter_evidence_6_a_fake_emit_point_in_the_shadow_app_goes_red():
    """刀⑥：影子根里假造一处 emit 点——守卫第二头会红（盘上 app/** 一个字没动）。"""
    fake_rel = "app/agents/_r472_counter_evidence_emitter.py"
    shadow = overlay.SHADOW
    planted = shadow.root / fake_rel
    planted.write_text("CODE = " + repr(PENDING_CODE) + "\n", encoding="utf-8")
    original = vocab._REPOSITORY
    vocab._REPOSITORY = shadow.root
    try:
        with pytest.raises(AssertionError) as caught:
            vocab.test_a_deferred_code_stays_out_of_the_enum_until_it_has_an_emit_point(PENDING_CODE)
        message = str(caught.value)
        assert "已经有出处了" in message, message
        assert "R467" in message, "红话不再点名契约出处：" + message
    finally:
        vocab._REPOSITORY = original
        planted.unlink()


def test_counter_evidence_7_reporting_a_reason_for_that_branch_goes_red():
    """刀⑦：让 `department_column_missing` 那一支真报出因由——丁格红（行为的牙还在）。"""
    anchor = (
        "        # 本层自己在 department_scope 分支立的同一规矩（部门维度没藏过就不下结论）"
        "不许在这里绕过。\r\n        return \"\""
    )

    class _ReportsAReason(overlay.ShadowEdit):
        tag = "r472-ding"
        execs_module = True

        def mutate(self, text: str) -> str:
            count = text.count(anchor)
            if count != 1:
                raise AssertionError("丁格反证的锚不唯一（%d 处）" % count)
            return _mutant_or_red(
                text.replace(anchor, anchor.replace('return ""', 'return "本表没有部门列，过滤后一行不剩"'))
            )

    with _ReportsAReason(REPO / TOOLS_REL):
        assert tools._row_scope_reason(dict(_MISSING_COLUMN)) != "", "影子根没生效"
        with pytest.raises(AssertionError) as caught:
            test_the_missing_department_column_branch_still_reports_no_reason()
        assert "开始替别的维度报因由" in str(caught.value), str(caught.value)


def test_the_tracked_files_survive_every_knife_untouched():
    """七刀全程只读：被跟踪文件进出逐字节相等，且窗外甲乙丙丁自己都是绿的。"""
    for knife in sorted(FAKE_OPEN_REASONS):
        before = {rel: (REPO / rel).read_bytes() for rel in (TOOLS_REL, VOCAB_REL)}
        with _ShadowWordEdit(knife):
            pass
        for rel, raw in before.items():
            assert (REPO / rel).read_bytes() == raw, "反证刀写进了被跟踪文件：%s" % rel
        assert overlay.open_windows() == (), "反证窗漏了：%s" % (overlay.open_windows(),)
    test_no_open_question_wording_survives_in_the_two_files()
    test_every_rewritten_comment_names_both_sources()
    test_the_register_value_and_the_guard_docstring_name_both_sources()
    test_the_pending_code_is_still_pending_not_implemented()
    test_the_missing_department_column_branch_still_reports_no_reason()
