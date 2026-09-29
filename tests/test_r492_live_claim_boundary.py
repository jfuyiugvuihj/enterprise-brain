# -*- coding: utf-8 -*-
"""R492 · 常驻钉：§1 那条自守改成可失败的边界——自称「现读」的坐标，必须有钉拿得住。

病根（工单 R492 病一）：血缘文档 §1 表旁那句自守原写「本表之下的正文（含 §2–§7）里的行号……属历史账」。
这句今天已经**不完全是真**：R490（并树 f2434f8）把 §3 方案 A 那一格与 §8.7 凭据那一格改成了当下声称
（句里带「现读」字样，值取自派生器成品串）。🔴 于是这句自守同时犯两头错：把两句当下声称说成历史账
（漏-covered），又成了下一班往正文里塞过期行号的挡箭牌（过-broad）。要改的是**口径边界**，不是删掉它。

新口径（正文已落 §1 表旁，说明见 `docs/testing/r492-caliber-2026-09-29.md`）分三格，逐枚当场可判：
  甲 **当下声称**＝同一行（或同一表格列的表头）带「现读」字样、说的是此刻盘上源码的坐标：值只许现场派生；
  乙 **成对叙述**＝同一句里「旧 ／ 新」两枚标号同时夹着坐标：按历史跳过（那一族由 R490 的「行内至少还剩
     一枚真核过的坐标」拦着，不许靠补标号把整行洗白）；
  丙 **历史操作账**＝当时那一次的读数与动作（重锚账、刀表里引的红句原文、已交回的旧读数）：不受对账。
钉进纸面的可失败形状：
  ① 甲类坐标的对账范围从 R490 的三枚被引件**放宽到取档函数管的每一枚文件**；落在有主区段的除外——
     §1 那张表＝teeth 独家管，§9.3 最后一列＝同族件 `test_r492_s93_column_matches_derived.py` 逐格管；
  ② 无主区段里对不上派生值的甲类坐标必须逐枚在册（`KNOWN_UNPINNED`，键＝节号 + 文件，🔴 不含坐标，
     所以值漂了也不会逼人手改账）：账外新长出的一律红，欠账治好只会让清单变短（不会反向逼人造假）；
  ③ 归属口径：表格逐行独立成句（只认本行自己写明的文件），正文才允许跨行沿用文件归属——
     §8.8 那把刀表里引着的红句原文因此不会被误算成本书的当下声称；
  ④ §1 表旁那句自守必须还在，且必须同时写明甲乙丙三格与每一格的钉；退回那句 blanket 自守即红；
  ⑤ 本件一枚坐标都不许抄（自扫：源码里读不出「冒号紧贴数字」的写法），也不许写过那支取档脚本一个字；扫描器 import R490 那一枚复用，
     不另抄一份（两本扫描器必然漂）。
全程只读盘上字节：零写口、不连库、不起服务、不打模型；五把牙只在内存的行列表里变异。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import test_r490_live_reads_match_derived as r490

REPO = r490.REPO
DOC = r490.DOCS[0]
LIVE_MARK = r490.LIVE_MARK

#: ① 有主区段：标题现读必须恰命中一枚，节号由标题本身派生（本件不写任何行号）。
OWNED = (("## 1. ", "test_r387_label_ruler_teeth.py"),
         ("### 9.3 ", "test_r492_s93_column_matches_derived.py"))

#: ② 在册欠账：自称现读、可那枚符号压根没有锚，所以无处对账。R493 起账面**零枚**——原先唯一在册那一枚
#:    （§9.6 的 `chat_ask_entry` 落空账）已按乙案降回丙类历史操作账（血缘纸 §9.8），纸上不再自称现读。
#:    清零是两头一起收的：账先清而纸没清、或纸先清而账没清，下面那枚对账牙都当场红。
KNOWN_UNPINNED: tuple = ()

#: ④ §1 表旁那句自守：三格身份 + 每一格谁来钉。
GUARD_HEAD = "本表之下的正文"
GUARD_CELLS = ("当下声称", "成对叙述", "历史操作账", "现读")
GUARD_OWNERS = ("teeth", "R490", "R492")
#: 退回到那句 blanket 自守的可辨形状（旧句的两段原文，都不含坐标）。
GUARD_REGRESSION = ("要现读只看本表", "里的行号是 R387/R390 当时那一次的读数")

HEADING = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)?)\b")
COPIED = re.compile(r":\d")
CLIP = 56


def read_doc():
    return r490.read_rows(DOC)


def section_ids(rows):
    """逐行现读它属于哪一节：按最近的标题派生。"""
    out = []
    current = ""
    for line in rows:
        match = HEADING.match(line)
        if match:
            current = match.group(1)
        out.append(current)
    return out


def owned_sections(rows):
    """① 有主区段的节号 -> 负责它的钉；标题读不出恰一枚就是本件自己失效。"""
    out = {}
    for prefix, owner in OWNED:
        hits = [i for i, line in enumerate(rows) if line.startswith(prefix)]
        assert len(hits) == 1, "有主区段的标题 " + prefix + " 命中 " + str(len(hits)) + " 枚，本该恰一枚"
        out[HEADING.match(rows[hits[0]]).group(1)] = owner
    return out


def is_table_row(text):
    return text.lstrip().startswith("|")


def scan(rows, ledger=KNOWN_UNPINNED):
    """对账一次：交回 (红清单, 核过的甲类坐标, 读出的欠账, 账外欠账)。"""
    spans, failures = r490.derived_spans()
    aliases = r490.alias_map(spans)
    ids = section_ids(rows)
    owned = owned_sections(rows)
    defects = list(failures)
    checked = []
    gaps = []
    carried = ""
    for index, line in enumerate(rows):
        text = line
        if not text.strip():
            carried = ""
            continue
        if is_table_row(text):
            found, _owner = r490.claims_in_line(text, "")
            carried = ""
        else:
            found, carried = r490.claims_in_line(text, carried)
        if LIVE_MARK not in text or ids[index] in owned:
            continue
        for owner, first, last, _where, history in found:
            path = r490.canonical(owner, aliases)
            pool = spans.get(path)
            if not pool or history:
                continue
            if r490.matches(pool, first, last):
                checked.append(ids[index] + "|" + path)
            else:
                gaps.append((ids[index], path))
    untracked = [item for item in gaps if item not in ledger]
    for section, path in untracked:
        defects.append("§" + section + " 里 " + path + " 有一枚自称现读却对不上派生值的坐标：无主区段的甲类坐标必须现场派生")
    return defects, checked, sorted(set(gaps)), untracked


def guard_defects(text):
    """④ 那句自守的形状检查（纯函数，牙可以直接喂变异后的文本）。"""
    missing = [word for word in GUARD_CELLS if word not in text]
    problems = []
    if missing:
        problems.append("自守句读不出甲乙丙三格，缺：" + " / ".join(missing))
    no_owner = [who for who in GUARD_OWNERS if who not in text]
    if no_owner:
        problems.append("自守句没写明每一格由哪枚钉负责，缺：" + " / ".join(no_owner))
    if "钉" not in text:
        problems.append("自守句没留下「自称现读必须有钉」这半条边界：挡箭牌又长回来了")
    backslide = [shape for shape in GUARD_REGRESSION if shape in text]
    if backslide:
        problems.append("自守句退回成 blanket 口径：" + " / ".join(backslide))
    return problems


def guard_paragraph(rows=None):
    """§1 表旁那句自守的正文：从它起，到下一枚空行为止（按内容现读定位）。"""
    rows = read_doc() if rows is None else rows
    hits = [i for i, line in enumerate(rows) if line.startswith(GUARD_HEAD)]
    assert len(hits) == 1, GUARD_HEAD + " 那句自守命中 " + str(len(hits)) + " 枚，本该恰一枚"
    body = [rows[hits[0]]]
    for line in rows[hits[0] + 1:]:
        if not line.strip():
            break
        body.append(line)
    return "\n".join(body)


def tool_bytes():
    return hashlib.sha256(r490.TOOL.read_bytes()).hexdigest()


def append_probe(rows, probe):
    """在内存里往书尾贴一枚孤立探针（前后各留空行，归属不靠上一行沿用）。"""
    out = list(rows)
    if out and out[-1].strip():
        out.append("")
    return out + ["", probe, ""]


def rendered(first, last):
    return str(first) if first == last else str(first) + "-" + str(last)


# ---------------------------------------------------------------------------
# ①② 甲类坐标：要么对得上派生值，要么在册
# ---------------------------------------------------------------------------

def test_live_claims_outside_owned_sections_reconcile_or_are_ledgered() -> None:
    defects, checked, _gaps, _untracked = scan(read_doc())
    assert checked, "整本纸一枚可对账的甲类坐标都没核到：本件今天没在量东西"
    assert defects == [], "有自称现读的坐标对不上现场派生值：\n  " + "\n  ".join(defects)


def test_the_ledger_matches_the_gaps_read_from_the_book() -> None:
    _defects, _checked, gaps, untracked = scan(read_doc())
    assert untracked == [], "账外又长出无主现读坐标：" + " / ".join(item[0] + "|" + item[1] for item in untracked)
    assert gaps == sorted(set(KNOWN_UNPINNED)), \
        "在册欠账与实际不符（实际读出 " + str(gaps) + "）：治好了要连本件与 §1 自守句一起收，不许只改账"


def test_the_guard_paragraph_carries_the_boundary() -> None:
    assert guard_defects(guard_paragraph()) == []


# ---------------------------------------------------------------------------
# ⑤ 本件自证：不带账，不碰量具
# ---------------------------------------------------------------------------

def test_this_pin_carries_no_copied_coordinates() -> None:
    source = Path(__file__).resolve().read_bytes().decode("utf-8")
    bad = [text.strip()[0:CLIP] for text in source.splitlines() if COPIED.search(text)]
    assert not bad, "本件里长出抄来的行号：" + " / ".join(bad)


def test_this_pin_writes_nothing_to_the_deriver() -> None:
    before = tool_bytes()
    scan(read_doc())
    assert tool_bytes() == before, "本件在取证时动了那支取档脚本"


# ---------------------------------------------------------------------------
# 牙：五把，各摘一样
# ---------------------------------------------------------------------------

def _pool(spans, path):
    assert path in spans, "这枚文件在取档函数里没有锚，本牙换一枚：" + path
    return spans[path]


def test_teeth_a_a_new_unpinned_live_claim_turns_red() -> None:
    spans, _failures = r490.derived_spans()
    path = "app/rag/indexing.py"
    ghost = 1 + max(high for _low, high in _pool(spans, path))
    probe = "另见 " + path + ":" + str(ghost) + " 那一格" + LIVE_MARK + "。"
    defects, _checked, _gaps, untracked = scan(append_probe(read_doc(), probe))
    assert any(path in item and "无主区段" in item for item in defects), "给无主区段编一枚自称现读的假坐标竟然不红"
    assert untracked, "红是红了，欠账清单却没读出来：这一格是撞红的"


def test_teeth_b_a_derived_live_claim_outside_owned_sections_passes() -> None:
    spans, _failures = r490.derived_spans()
    path = "app/rag/retriever.py"
    low, high = sorted(_pool(spans, path))[0]
    probe = "另见 " + path + ":" + rendered(low, high) + " 那一格" + LIVE_MARK + "。"
    _defects, checked, _gaps, untracked = scan(append_probe(read_doc(), probe))
    assert not untracked, "对得上派生值的甲类坐标被误报了：这一格不是值检查"
    assert any(item.endswith("|" + path) for item in checked), "新编那枚真坐标没进账：甲类闸没在扫书尾这一族"


def test_teeth_c_a_table_row_still_needs_its_own_file() -> None:
    """③ 的另一半：表格逐行独立成句只免掉「沿用」，不免掉本行自带的坐标。"""
    spans, _failures = r490.derived_spans()
    path = "app/rag/pg_store.py"
    ghost = 1 + max(high for _low, high in _pool(spans, path))
    probe = "| 假格子 | " + path + ":" + str(ghost) + " | " + LIVE_MARK + " |"
    defects, _checked, _gaps, _untracked = scan(append_probe(read_doc(), probe))
    assert any(path in item for item in defects), "表格行自带一枚假现读坐标竟然不红：③ 变成了豁免口"


def test_teeth_d_an_empty_ledger_exposes_the_debt() -> None:
    """收口之后重铸的牙：账面清零是真的清零，而那本名单仍然拦得住东西。

    旧形拿"纸上今天恰有一枚欠账"当量具，欠账一治好它必红——那是牙的形状跟着账走。两问现在各归各：
    ① 盘上这本书读得出零枚无主现读坐标，且名单也是空的，两边必须一起为零；② 在内存里造一枚对不上
    派生值的现读坐标，名单空着它必须红，给它记上名它必须只登记不红（名单是真豁免口，不是装饰）。
    """
    rows = read_doc()
    _defects, _checked, gaps, untracked = scan(rows)
    assert KNOWN_UNPINNED == (), "账面写着清零，可名单里还剩 " + str(KNOWN_UNPINNED)
    assert gaps == [], "名单说清零了，可纸上还读得出欠账：" + str(gaps)
    assert untracked == [], "账外长出无主现读坐标：" + str(untracked)
    spans, _failures = r490.derived_spans()
    path = "app/rag/indexing.py"
    ghost = 1 + max(high for _low, high in _pool(spans, path))
    probe = "另见 " + path + ":" + str(ghost) + " 那一格" + LIVE_MARK + "。"
    seeded = append_probe(rows, probe)
    _d, _c, seeded_gaps, seeded_untracked = scan(seeded)
    assert seeded_gaps and seeded_untracked, "造一枚无主现读坐标竟然不红：那本账是空转的"
    carried = tuple(seeded_untracked[0])
    _d2, _c2, _g2, tracked = scan(seeded, ledger=(carried,))
    assert tracked == [], "在册那一格根本没在拦东西：给它记上名竟然还红"


def test_teeth_e_backsliding_the_guard_is_caught() -> None:
    blanket = GUARD_HEAD + "（含 §2–§7）里的行号是 R387/R390 当时那一次的读数，属历史账，不随并树更新 ⇒ 要现读只看本表。"
    problems = guard_defects(blanket)
    assert problems, "退回 blanket 自守竟然读不出问题：那句边界是纸糊的"
    assert any("挡箭牌" in item or "blanket" in item for item in problems), "退步没被点名：" + " / ".join(problems)
    assert guard_defects(guard_paragraph()) == [], "现行口径反而读不过自己的形状检查"