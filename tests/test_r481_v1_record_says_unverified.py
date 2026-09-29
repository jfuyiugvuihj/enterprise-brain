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
