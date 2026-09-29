# -*- coding: utf-8 -*-
"""R481 · 常驻钉：验收记录里那两句越权口径只许读成「未验」。

病根（工单 R481，本单基点 e03babb）：两本纸互相矛盾。
`docs/handoff/2026-09-23-v1-acceptance-record.md` 的 C 行原本写着「越权格 ✅」、
§6 那句写着「越权已结清」，而 `docs/handoff/2026-09-17-pgvector-adoption-plan.md` §13
已把这条判据改写成四件可失败判据，原句是「任一不满足即记「未验」，不得记通过」。
下一班照验收记录派工就会把 C 门当成已绿，所以把口径钉回盘上。

本件钉什么（全程只读盘上字节，零写口、不连库、不起服务、不打模型）：
  ① C 行与 §6 那句都必须含「未验」，且都不许挂着通过标记（✅／已结清）；
  ② 全文件扫描：凡提到「越权」的行都不许同时挂着通过标记；
  ③ C 行必须把判据出处指回计划书 §13，并端出**从计划书现读回来**的那句判据原句；
  ④ C 行那句理由的几枚关键措辞必须是计划书 §13 里就有的原话，不许是自己编的口径；
  ⑤ 计划书 §13 那句判据原句仍在盘上，且那一节的标题就写着改记「未验」；
  ⑥ 牙（只在内存里变异，盘上一字不写）：改回 ✅、改回「已结清」、摘掉出处、
     抹掉理由措辞、把 §13 那句判据摘掉 —— 各红各的，不许陪红。

🔴 R490 把上面 ② 那把窄牙升成整本扫描（本单只加不减：①–⑥ 的 test 与 assert 一枚未删、一条未放宽）。
   上游判据（`docs/handoff/2026-09-29-v2-gap-recheck-3.md` 里 R481 那格的②）要的是「凡出现『越权』
   且不带『未验』即红」，本件作者当年**故意没照写实现**——那会在 `B / E` 那一格假红（它当时还写着
   「其越权格已由 C 覆盖」）。R490 已把那一格改成与 §13 同口径，借口就此消失，于是补上三格：
   ⑦ 整本「越权 ⇒ 未验」配对：凡提到「越权」的段（表格一行算一格，正文按空行／列表项分段）必须自带「未验」；
   ⑧ 同一格里的通过口径一律算红：✅、「已结清」，外加「覆盖」——越权格只能被验掉，不能被别人的格子
      「覆盖」掉（那正是 R490 从 `B / E` 那一格摘掉的句子）；
   ⑨ `B / E` 那一格的越权腿与 C 同判据：必须写明出处是那本计划书、必须指回 §13、必须端得出**从 §13
      现读回来**的那句判据原句（与 ③ 同源，不抄数）。
   新增牙：抹掉 B / E 的「未验」、把它改回「已由 C 覆盖」、给它挂上 ✅ —— 各红各的，C 行的钉不许陪红。

🔴 行号一律运行时派生（同族先例：R400 把三处行号账改成运行时派生）：本件不出现任何
   写死的行号，全部按锚点／标题位置现读；读数与措辞一律从计划书现读回来比对，不手抄。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECORD_REL = "docs/handoff/2026-09-23-v1-acceptance-record.md"
PLAN_REL = "docs/handoff/2026-09-17-pgvector-adoption-plan.md"

C_ROW_PREFIX = "| **C** 检索与缓存 |"
#: R490：越权口径的第二处引用就在 B / E 那一格 —— 行号同样按前缀现读派生，不写死。
E_ROW_PREFIX = "| **B / E** |"
CONCLUSION_HEADING = "## 6. 一句话结论"
PLAN_HEADING_PREFIX = "## 13."
OVERREACH = "越权"
UNVERIFIED = "未验"
SETTLED = "已结清"
CHECKMARK = chr(0x2705)
SECTION_MARK = "§" + "13"
CR_HEAD = "任一不满足即记"
CR_TAIL = "，不得记通过"
CR = chr(13)
LF = chr(10)

#: ④ 那把同源牙：C 行的理由必须说清「空集」与「不构成通过证据」，而这两句本来就是
#    §13 的原话 —— 列在这里只是提出候选，真正的同源判定是「§13 正文里读得到」那一条。
REASON_ECHOES = ("空集", "不构成通过证据", "沙盒", "客户隔离")

#: ⑧ 通过口径的三种写法：✅ 与「已结清」是 R481 立的旧账，「覆盖」是 R490 补的那一形 ——
#: 「其越权格已由 C 覆盖」读起来就是「已覆盖」，而 C 那一格今天已经不绿了。
CLOSURE_WORDS = (CHECKMARK, SETTLED, "覆盖")

#: 「段」的边界：markdown 表格行每行自成一格；列表项与标题各起一段，段内续行算同一句主张。
LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*+\u2022])\s+")
HEADING = re.compile(r"^#+\s")


def read(rel):
    """现读盘上那一本：先证明换行符仍成对，再按行切开。行号 = 下标 + 1。"""
    raw = (REPO / rel).read_bytes().decode("utf-8")
    assert raw.count(CR) == raw.count(LF), rel + " 的换行符不再成对"
    return raw.splitlines()


def one_hit(rows, matcher, what, offset=0):
    hits = [(offset + no, text) for no, text in enumerate(rows, 1) if matcher(text)]
    assert len(hits) == 1, what + " 现读命中 " + str(len(hits)) + " 枚，定位不唯一就没法派生行号"
    return hits[0]


def c_row(rows):
    return one_hit(rows, lambda t: t.startswith(C_ROW_PREFIX), "C 行")


def e_row(rows):
    return one_hit(rows, lambda t: t.startswith(E_ROW_PREFIX), "B / E 行")


def segments(rows):
    """把整本切成「段」并派生每段的起始行号（本件不写死任何坐标）。"""
    out, index = [], 0
    while index < len(rows):
        if not rows[index].strip():
            index += 1
            continue
        start = index
        index += 1
        if rows[start].lstrip().startswith("|"):
            out.append((start + 1, rows[start]))
            continue
        while index < len(rows) and rows[index].strip() \
                and not rows[index].lstrip().startswith("|") \
                and not LIST_ITEM.match(rows[index]) and not HEADING.match(rows[index]):
            index += 1
        out.append((start + 1, "\n".join(rows[start:index])))
    return out


def book_defects(rows):
    """⑦⑧：整本「越权 ⇒ 未验」配对；越权那一格里的任何通过口径都算红。"""
    out = []
    for no, text in segments(rows):
        if OVERREACH not in text:
            continue
        if UNVERIFIED not in text:
            out.append("第 " + str(no) + " 行起的那一段提到越权却没带「" + UNVERIFIED + "」")
        for word in CLOSURE_WORDS:
            if word in text:
                out.append("第 " + str(no) + " 行起的那一段把越权与「" + word + "」写在了一起")
    return out


def conclusion_line(rows):
    """§6 标题之后第一段非空正文：位置由标题派生，不抄行号。"""
    head, _ = one_hit(rows, lambda t: t.strip() == CONCLUSION_HEADING, "§6 标题")
    for no in range(head + 1, len(rows) + 1):
        text = rows[no - 1]
        if text.strip():
            return no, text
    raise AssertionError("§6 标题下面读不到正文")


def plan_section():
    """§13 那一节：标题按前缀现读，正文取到下一枚二级标题为止。"""
    rows = read(PLAN_REL)
    head, title = one_hit(rows, lambda t: t.startswith(PLAN_HEADING_PREFIX), "§13 节标题")
    rest = [no for no in range(head + 1, len(rows) + 1) if rows[no - 1].startswith("## ")]
    stop = min(rest) if rest else len(rows) + 1
    return head, title, LF.join(rows[head:stop - 1])


def plan_criterion(section_body=None):
    """判据原句从 §13 正文里现读；本件自己不抄那一句。"""
    if section_body is None:
        section_body = plan_section()[2]
    _no, line = one_hit(section_body.splitlines(),
                       lambda t: CR_HEAD in t and CR_TAIL in t, "§13 判据原句")
    match = re.search(CR_HEAD + "[^" + LF + "]*?" + CR_TAIL, line)
    assert match, "§13 那句判据读不出可对照的片段"
    return match.group(0)


def cell_defects(label, text):
    out = []
    if OVERREACH not in text:
        out.append(label + " 读不出越权口径")
    if CHECKMARK in text:
        out.append(label + " 还挂着 ✅")
    if SETTLED in text:
        out.append(label + " 还写着「已结清」")
    if UNVERIFIED not in text:
        out.append(label + " 没写「未验」")
    return out


def wording_defects(rows):
    """①②：两格各自的措辞 + 全文件的「越权 × 通过标记」同形。"""
    out = []
    for label, (no, text) in (("C 行", c_row(rows)), ("§6 那句", conclusion_line(rows))):
        for item in cell_defects(label, text):
            out.append(item + "（第 " + str(no) + " 行）")
    out += ["第 " + str(no) + " 行把越权与通过标记写进了同一行"
            for no, text in enumerate(rows, 1)
            if OVERREACH in text and (CHECKMARK in text or SETTLED in text)]
    return out


def provenance_defects(rows):
    """③：出处断了，或端不出那句从计划书现读回来的判据原句。"""
    _no, text = c_row(rows)
    out = []
    if PLAN_REL not in text:
        out.append("C 行没写明依据是哪本纸")
    if SECTION_MARK not in text:
        out.append("C 行没把判据出处指回计划书 " + SECTION_MARK)
    if plan_criterion() not in text:
        out.append("C 行端不出从计划书现读回来的那句判据原句")
    return out


def reason_defects(rows):
    """④：理由里的措辞必须与 §13 同源，两本纸各说各话同样是一种假话。"""
    _no, text = c_row(rows)
    _head, _title, body = plan_section()
    out = []
    for phrase in REASON_ECHOES:
        if phrase not in text:
            out.append("C 行那句理由里读不到「" + phrase + "」，理由被抽空了")
        elif phrase not in body:
            out.append("「" + phrase + "」不再是计划书 §13 的原话，口径同源断了")
    return out


def swap_in_cell(new_fragment, old_fragment=UNVERIFIED, count=1):
    """牙的公共道：只在内存里换 C 行那一格，盘上那一本一个字都不写。"""
    rows = read(RECORD_REL)
    no, text = c_row(rows)
    assert old_fragment in text, "变异落不了地：C 行读不到片段 " + old_fragment
    patched = list(rows)
    patched[no - 1] = text.replace(old_fragment, new_fragment) if count == 0 else text.replace(old_fragment, new_fragment, 1)
    assert patched[no - 1] != text, "变异没改动 C 行"
    return patched


def test_overreach_cells_read_unverified():
    assert wording_defects(read(RECORD_REL)) == []


def swap_prefixed_cell(prefix, new_fragment, old_fragment=UNVERIFIED, count=1):
    """牙的公共道（R490）：按行前缀定位那一格，只在内存里换片段，盘上一字不写。"""
    rows = read(RECORD_REL)
    no, text = one_hit(rows, lambda t: t.startswith(prefix), prefix)
    assert old_fragment in text, "变异落不了地：" + prefix + " 读不到片段 " + old_fragment
    patched = list(rows)
    patched[no - 1] = text.replace(old_fragment, new_fragment) if count == 0 else text.replace(old_fragment, new_fragment, 1)
    assert patched[no - 1] != text, "变异没改动那一格"
    return patched


def e_row_defects(rows):
    """⑨：B / E 的越权格必须与 C 端同一句判据；引用别人的格子不能替它翻绿。"""
    no, text = e_row(rows)
    out = []
    if PLAN_REL not in text:
        out.append("B / E 行没写明越权格的判据出自哪本纸（第 " + str(no) + " 行）")
    if SECTION_MARK not in text:
        out.append("B / E 行没把越权格指回计划书 " + SECTION_MARK + "（第 " + str(no) + " 行）")
    if plan_criterion() not in text:
        out.append("B / E 行端不出从计划书现读回来的那句判据原句（第 " + str(no) + " 行）")
    return out


def test_the_whole_book_pairs_overreach_with_unverified():
    """⑦⑧（R490 升级）：不再是「同行同标记」那把窄牙，而是整本配对。"""
    rows = read(RECORD_REL)
    assert book_defects(rows) == []
    assert any(OVERREACH in text for _no, text in segments(rows)), \
        "整本扫描读不到任何越权口径：这一格今天没在量东西"


def test_the_b_e_row_carries_the_same_verdict_as_the_c_row():
    assert e_row_defects(read(RECORD_REL)) == []


def test_teeth_f_the_e_row_losing_unverified_goes_red_alone():
    rows = swap_prefixed_cell(E_ROW_PREFIX, "已核", count=0)
    assert book_defects(rows), "把 B / E 行的「未验」全抹掉竟然不红"
    assert e_row_defects(rows), "B / E 行丢了「未验」竟然没被点名"
    assert provenance_defects(rows) == [], "B / E 行变异把 C 行出处钉也打红了（陪红＝信号作废）"
    assert reason_defects(rows) == [], "B / E 行变异把 C 行理由同源钉也打红了"


def test_teeth_g_the_covered_by_c_sentence_goes_red():
    rows = swap_prefixed_cell(E_ROW_PREFIX, "已由 C 覆盖",
                              old_fragment="随 C 一起记「未验」**，不替它翻绿")
    assert any("覆盖" in item for item in book_defects(rows)), \
        "把 B / E 那一格改回「已由 C 覆盖」竟然不红"
    assert provenance_defects(rows) == [], "「已由 C 覆盖」变异把 C 行出处钉打红了"
    assert reason_defects(rows) == [], "「已由 C 覆盖」变异把 C 行理由同源钉打红了"


def test_teeth_h_a_green_mark_on_the_e_row_is_caught_twice():
    rows = swap_prefixed_cell(E_ROW_PREFIX, CHECKMARK, old_fragment="\u26aa", count=0)
    assert any(CHECKMARK in item for item in book_defects(rows)), "B / E 行挂上 ✅ 竟然不红（整本那把）"
    assert any("越权与通过标记" in item for item in wording_defects(rows)), \
        "B / E 行挂上 ✅ 竟然不红（窄牙那把；红句只报行号与形状，不回显标记）"
    assert e_row_defects(rows) == [], "✅ 变异把 B / E 的出处钉也打红了（陪红＝信号作废）"


def test_the_cell_points_back_at_plan_section_13():
    assert provenance_defects(read(RECORD_REL)) == []


def test_the_reason_wording_is_shared_with_the_plan():
    assert reason_defects(read(RECORD_REL)) == []


def test_the_plan_criterion_is_still_in_force():
    head, title, body = plan_section()
    assert UNVERIFIED in title, "§13 标题不再写着改记「未验」（第 " + str(head) + " 行）"
    assert CR_HEAD in body and CR_TAIL in body, "§13 正文里那句判据不见了"
    assert plan_criterion().startswith(CR_HEAD), "判据原句读回来的是别的东西"


def test_teeth_a_checkmark_put_back_goes_red_without_company():
    rows = swap_in_cell(CHECKMARK)
    hits = wording_defects(rows)
    assert any("✅" in item for item in hits), "把 C 行改回 ✅ 竟然不红"
    assert provenance_defects(rows) == [], "✅ 变异把出处钉也打红了（陪红＝信号作废）"
    assert reason_defects(rows) == [], "✅ 变异把理由同源钉也打红了"


def test_teeth_b_settled_claim_put_back_goes_red():
    hits = wording_defects(swap_in_cell(SETTLED))
    assert any(SETTLED in item for item in hits), "把口径改回已结清竟然不红"


def test_teeth_c_losing_the_provenance_goes_red_alone():
    rows = swap_in_cell("", old_fragment=SECTION_MARK, count=0)
    assert provenance_defects(rows), "摘掉出处竟然不红"
    assert wording_defects(rows) == [], "出处变异把措辞钉打红了"


def test_teeth_d_an_emptied_reason_goes_red():
    hits = reason_defects(swap_in_cell("", old_fragment=REASON_ECHOES[0], count=0))
    assert any(REASON_ECHOES[0] in item for item in hits), "把理由里的空集口径抹掉竟然不红"


def test_teeth_e_a_missing_plan_criterion_is_caught():
    _head, _title, body = plan_section()
    try:
        plan_criterion(body.replace(CR_TAIL, "", 1))
    except AssertionError:
        return
    raise AssertionError("把 §13 那句判据摘掉，现读道竟然还端得出原句")
