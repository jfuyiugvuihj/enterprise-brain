# -*- coding: utf-8 -*-
"""R493 · 常驻钉：§9.6 那枚「结构上无法核对的当下声称」降成丙类历史账之后，形状必须还锁得住。

病灶（工单 R493 账①）：血缘纸 `docs/perf/r387-label-lineage-2026-09-27.md` §9.6 的 `chat_ask_entry` 那一格
原文写「该符号今天现读在 ……」，而按 §1 表旁那条自守的定义，没有任何钉拿得住它——那枚 token 不在
`LINEAGE_SITES` 里 ⇒ 无处对账 ⇒ 下一次并树把被引文件挪了，它也不会红。R492 已把它钉成在册唯一一枚
欠账（键＝节号＋文件，不含坐标）。本单按**乙案**收口：那一格降为丙类历史操作账，只记 R400 在基点
`6a8063a` 上那一次的读数，并写明此数不再随并树核对；欠账名单随之清零，与 §1 那句自守一起改到自洽。

为什么不是甲案（把那枚 token 收进 `LINEAGE_SITES`，46→47）：本件那枚死锚牙把答案钉成可复跑的形——
在册互覆闸 `test_the_anchor_table_and_the_templates_share_one_ledger` 只许「有模板引用的锚」存在，而本单
授权只许动 `LINEAGE_SITES` 一处；另两条是「那枚 token 是问答主入口、不在 12 跳血缘上」与「46→47 会打翻
§8.5 与 §8.8 那两格原样留档的历史账」。全文见血缘纸 §9.8 第 ① 格。

本件钉什么（全程只读盘上字节与只读 git 对象：零写口、不连库、不起服务、不打模型，变异只在内存里）：
  ① 那一格不再自称现读，且行内一枚坐标主张都没有（甲类闸读不出东西，才算真的把它降下来）；
  ② 那一格记的基点读数可复现：纸面的数 == 那枚基点的 blob 里同一 token 的行位（只读 `git show`）；
  ③ 那枚数确实已经过期（今天的行位与它不等，也不是任何一枚锚的端点）——「当初不该写成当下声称」的实证；
  ④ 纸面关于锚枚数的每一处声称 == `len(LINEAGE_SITES)`：枚数不手抄，由钉 import 真源对账；
  ⑤ 欠账名单两头一起清零：名单为空、纸上读不出无主现读坐标、且仍核得到真坐标（不是把闸拆了）；
  ⑥ 甲案反证：把那枚锚塞进锚表，在册互覆闸当场红并点名它；
  ⑦ 乙案反证：把当下声称的字样塞回那一格，边界闸当场红（倒退也拦得住）；
  ⑧ 本件自证：一枚坐标都不抄，也不许写过那支取档脚本一个字。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import test_r387_label_ruler_teeth as teeth
import test_r490_live_reads_match_derived as r490
import test_r492_live_claim_boundary as boundary

REPO = r490.REPO
DOC = boundary.DOC
TOOL = r490.TOOL_MODULE

#: 派工词那一格点名的符号名（它在本仓从来不存在）与它真正对应的那枚 token。
ROW_MARK = "chat_ask_entry"
TOKEN = chr(64) + "router.post(" + chr(34) + "/ask" + chr(34) + ")"
CHAT = "app/api/v1/chat.py"
SECTION = "9.6"

#: 那一格里要现场读回来的三样：基点、被引文件、那一次的行位。
BASE = re.compile("`([0-9a-f]{7,40})`")
PATH = re.compile("`((?:app|scripts|migrations)/[A-Za-z0-9_./-]+[.]py)`")
PLACED = re.compile(r"第 (\d+) 行")
COUNT = re.compile(r"(\d+) 枚锚(?:里|是在)")
LIVE_WORD = boundary.LIVE_MARK
HISTORY_MARK = "丙类历史操作账"
UNLOCKED = "不再随并树核对"
#: 图例那一句写的是节级口径，比行级少一个「再」字，这里按实物取。
UNLOCK_SECTION = "不随并树核对"
COPIED = re.compile(r":\d")
CLIP = 72


def doc_rows():
    return r490.read_rows(DOC)


def ask_row(rows=None):
    """§9.6 表里那一行：按具名符号现读，必须恰一枚。"""
    rows = doc_rows() if rows is None else rows
    hits = [line for line in rows if line.startswith("|") and ROW_MARK in line]
    assert len(hits) == 1, ROW_MARK + " 那一格命中 " + str(len(hits)) + " 枚，本该恰一枚"
    return hits[0]


def row_parts(row):
    """(基点, 被引文件, 纸面记的那一次行位)：三样全部从那一行现读，本件一枚都不抄。"""
    base, path, placed = BASE.search(row), PATH.search(row), PLACED.search(row)
    assert base and path and placed, "那一格读不出基点、被引文件与行位三样：" + row[:CLIP]
    return base.group(1), path.group(1), int(placed.group(1))


def positions(lines, token):
    """与锚块同一套语义：逐行 strip 之后固定串相等才算命中（不是正则，也不是子串）。"""
    return [index + 1 for index, line in enumerate(lines) if line.strip() == token]


def blob_lines(base, rel):
    """只读 git 对象：那一枚基点上那枚文件的原文（git show 不做工作树的换行换算）。"""
    shown = subprocess.run(["git", "show", base + ":" + rel], cwd=str(REPO), capture_output=True)
    assert shown.returncode == 0, "读不到基点 " + base + " 的 " + rel
    return shown.stdout.decode("utf-8", "replace").splitlines()


def chat_endpoints():
    """被引文件上每一枚锚的现读端点：用来证明那枚 token 至今没有钉拿得住。"""
    out = set()
    for key, (rel, _start, _stop) in TOOL.LINEAGE_SITES.items():
        _file, first, last = TOOL.resolve_site(key, REPO)
        if rel == CHAT:
            out.update((first, last))
    return out


# ---------------------------------------------------------------------------
# ① 那一格：不再自称现读，且行内一枚坐标主张都没有
# ---------------------------------------------------------------------------

def test_the_ask_row_no_longer_claims_a_live_read() -> None:
    row = ask_row()
    assert LIVE_WORD not in row, "那一格还带着自称现读的字样，乙案没落地：" + row[:CLIP]
    found, _owner = r490.claims_in_line(row, "")
    assert not found, "那一格还端得出坐标主张：" + str([item[1] for item in found])
    assert HISTORY_MARK in row, "那一格没写明它现在属丙类历史操作账"
    assert UNLOCKED in row, "那一格没写明此数不再随并树核对"


# ---------------------------------------------------------------------------
# ②③ 历史账可复现，而它确实已经过期（这就是「当初不该写成当下声称」的实证）
# ---------------------------------------------------------------------------

def test_the_historical_read_reproduces_on_the_base_blob() -> None:
    base, rel, stated = row_parts(ask_row())
    hits = positions(blob_lines(base, rel), TOKEN)
    assert len(hits) == 1, "token 在基点 " + base + " 的 blob 里命中 " + str(len(hits)) + " 枚，历史账无所指"
    assert hits[0] == stated, "纸面记第 " + str(stated) + " 行，blob 复现出第 " + str(hits[0]) + " 行"


def test_that_historical_read_is_already_stale_on_today() -> None:
    _base, _rel, stated = row_parts(ask_row())
    today = TOOL.anchor_lines(CHAT, (0, [TOKEN]), REPO)
    assert len(today) == 1, "那枚 token 今天命中 " + str(len(today)) + " 枚：唯一命中这条前提变了"
    assert today[0] != stated, "今天又落回历史那一行了：历史账与当下声称该分开重记，不许混写"
    endpoints = chat_endpoints()
    assert today[0] not in endpoints, "它已经有锚了：本件「无处对账」的前提不成立，该改走甲案"
    assert stated not in endpoints, "历史那一格反倒落在锚的端点上：乙案的理由不成立"


# ---------------------------------------------------------------------------
# ④ 纸面的锚枚数一律由派生值对账（枚数不许手改）
# ---------------------------------------------------------------------------

def test_the_anchor_counts_on_the_paper_are_the_derived_ones() -> None:
    derived = len(TOOL.LINEAGE_SITES)
    stated = [int(match.group(1)) for line in doc_rows() for match in COUNT.finditer(line)]
    assert stated, "纸上一枚锚枚数声称都读不出：这一格今天没在量东西"
    assert len(stated) >= 3, "只认出 " + str(len(stated)) + " 处锚枚数声称：闸没在扫全书"
    assert set(stated) == {derived}, (
        "纸面锚枚数 " + str(sorted(set(stated))) + " 与派生值 " + str(derived) + " 不等：枚数不许手抄")


# ---------------------------------------------------------------------------
# ⑤ 收口：名单与纸面两头一起为零，而闸仍在核东西
# ---------------------------------------------------------------------------

def test_the_debt_ledger_is_closed_at_both_ends() -> None:
    assert boundary.KNOWN_UNPINNED == (), "在册名单还挂着欠账：" + str(boundary.KNOWN_UNPINNED)
    defects, checked, gaps, untracked = boundary.scan(boundary.read_doc())
    assert not defects, "边界闸读出问题：" + str(defects)
    assert not gaps, "名单说清零了，可纸上还读得出欠账：" + str(gaps)
    assert not untracked, "账外长出无主现读坐标：" + str(untracked)
    assert checked, "全书一枚对得上账的甲类坐标都没核到：闸被拆成了空转"


def test_the_section_is_declared_history_before_its_table() -> None:
    rows = doc_rows()
    start = [i for i, line in enumerate(rows) if line.startswith("### " + SECTION)]
    assert len(start) == 1, "§" + SECTION + " 的标题命中 " + str(len(start)) + " 枚，本该恰一枚"
    legend = []
    for line in rows[start[0] + 1:]:
        if line.startswith("|"):
            break
        legend.append(line)
    prose = "\n".join(legend)
    assert HISTORY_MARK in prose, "§" + SECTION + " 表前没有那纸图例：列头自称现读、列值却是历史账"
    assert UNLOCK_SECTION in prose, "图例没写明本节不随并树核对"
    assert "§9.3 最后一列" in prose, "图例没把要今天坐标的人指向真有钉的那两格"
    assert len([line for line in rows if line.startswith("### 9.3")]) == 1, "§9.3 标题读不出恰一枚"
    header = [line for line in rows if line.startswith("| 派工词点的病 |")]
    assert len(header) == 1, "§9.3 的表头读不出恰一枚"
    assert LIVE_WORD in header[0], "§9.3 那一列被降级成历史账：R492 的派生闸就没有了名字"


# ---------------------------------------------------------------------------
# ⑥⑦ 两把常驻反证刀：甲案塞锚即红、乙案倒退即红
# ---------------------------------------------------------------------------

def test_backfilling_that_anchor_would_trip_the_registered_ledger_gate() -> None:
    """甲案反证：锚解得出来不等于锚进得来——在册互覆闸只许有模板引用的锚存在。"""
    sites = teeth.R387.LINEAGE_SITES
    original = dict(sites)
    key = "askentry"
    assert key not in original, "锚表里已经有这枚 key：本件的甲案反证要换成实际那一枚"
    sites[key] = (CHAT, (0, [TOKEN]), None)
    try:
        raised = None
        try:
            teeth.test_the_anchor_table_and_the_templates_share_one_ledger()
        except AssertionError as error:
            raised = str(error)
    finally:
        sites.clear()
        sites.update(original)
    assert raised is not None, "补一枚没人引用的锚，互覆闸竟然不红：本单走乙案的理由要重查"
    assert key in raised, "红是红了，可它没点名这枚新锚：" + raised[:CLIP]


def test_a_live_claim_stuffed_back_into_that_row_turns_red() -> None:
    """乙案反证：把当下声称塞回那一格，边界闸必须当场点名——值编得对不对都一样红。"""
    rows = list(boundary.read_doc())
    row = ask_row(rows)
    _base, _rel, stated = row_parts(row)
    quote = chr(96) + CHAT + ":" + str(stated) + chr(96)
    injected = row.replace(HISTORY_MARK, LIVE_WORD + "在 " + quote + "，它属" + HISTORY_MARK, 1)
    assert injected != row, "注入失败：那一格读不出历史账的标号"
    swapped = [injected if line == row else line for line in rows]
    defects, _checked, gaps, untracked = boundary.scan(swapped)
    assert (SECTION, CHAT) in gaps, "塞回当下声称竟然读不出欠账：那一格根本没在被扫"
    assert untracked, "欠账读出来了却没算账外：名单清零是假的"
    assert defects, "账外无主坐标竟然不出红判据：" + str(untracked)


# ---------------------------------------------------------------------------
# ⑧ 本件自证
# ---------------------------------------------------------------------------

def test_this_pin_carries_no_copied_coordinates() -> None:
    source = Path(__file__).resolve().read_bytes().decode("utf-8")
    bad = [line.strip()[:CLIP] for line in source.splitlines() if COPIED.search(line)]
    assert not bad, "本件里长出抄来的行号：" + " / ".join(bad)


def test_this_pin_writes_nothing_to_the_deriver() -> None:
    before = r490.tool_bytes()
    TOOL.resolve_cites(REPO)
    chat_endpoints()
    assert r490.tool_bytes() == before, "本件在取证时动了那支取档脚本"
