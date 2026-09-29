# -*- coding: utf-8 -*-
"""R492 · 常驻钉：血缘文档 §9.3 最后一列自称「本班现读」，就只许是锚现场派生的那一枚。

病灶（工单 R492，本单基点 f2434f8）：`docs/perf/r387-label-lineage-2026-09-27.md` §9.3 那张表回答的是
「三处手抄行号账现在各由哪一枚锚负责」，它最后一列的表头写着「本班现读」，可那一列的格是 R387/R390
当时手抄进去的一次读数。左列早就明写了每一格由哪枚锚 key 负责 —— 锚一直在，值没人回来跟。本席 09-29
现取：左列 `hop1` 那一格派生已在第 4363 行起，纸面那一格还印着第 4070 行起，差了近三百行。同一本纸上
并排摆着两把尺：§1 那张表跟着派生走，§9.3 这一列挂着「现读」的名字给旧坐标 —— 就是 #82/#88/#90/#91
那一族假事实供给器。

🔴 收口不是「把数字换成今天的新数字」（那只是重新埋一颗雷），本件钉的是**派生化**这一条形：
  ① 那一列的值取自派生器成品串（本次由 `--emit-doc-cells` 现取重落地）；
  ② 每一格由**同一行左列点名的锚 key** 现场 `resolve_site` 复算，逐格·按序·带文件归属对账，不等即红；
  ③ 表头必须继续自称「现读」并写明值来自 `resolve_site`：想把它降级成历史账又不改口径＝红（防洗白）；
  ④ 左列点不出锚 key 的那一行（§9.6 落空账那一格）最后一列只许是占位符，长出坐标即红；
  ⑤ 数量闸：这一列今天至少要点核到 FLOOR 枚坐标，删行缩表就是「这格没在量东西」；
  ⑥ 本件一枚坐标都不许抄：数一律 import `scripts/r387_label_lineage.py` 的取档函数现场拿（自扫：源码里
     读不出「冒号紧贴数字」的写法），那支脚本本身也不许被本件写过一笔。
全程只读盘上字节：零写口、不连库、不起服务、不打模型；六把牙只在内存的行列表里变异。
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: 派生值的唯一之家。与同族件同名挂钩：变异检验时把量具指到副本上。
TOOL = Path(os.getenv("R387_LABEL_TOOL") or (REPO / "scripts" / "r387_label_lineage.py"))

DOC_REL = "docs/perf/r387-label-lineage-2026-09-27.md"
SECTION_MARK = "### 9.3"
LIVE_MARK = "现读"
PROVENANCE = "resolve_site"
FLOOR = 12

#: 左列点名的锚 key（同一行内按出现顺序逐格对账）。
KEY = re.compile(r"\bhop[0-9]+[a-z]?\b")
#: 列内坐标：文件可省（沿用本列最近一次显式声明），冒号紧贴数字，可带区间。
CITE = re.compile(
    r"(?P<file>[A-Za-z0-9_./-]+[.](?:py|vue|sql))?"
    r":(?P<start>\d+)(?:-(?P<stop>\d+))?"
)
COPIED = re.compile(r":\d")
CLIP = 56


def _load_tool():
    spec = importlib.util.spec_from_file_location("r387_label_lineage_r492", TOOL)
    assert spec and spec.loader, "加载不到取档函数：" + str(TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL_MODULE = _load_tool()


def read_rows(rel=DOC_REL):
    """现读盘上那一本：先证明换行符仍成对，再按行切开。行号 = 下标加一。"""
    raw = (REPO / rel).read_bytes().decode("utf-8")
    assert raw.count("\r") == raw.count("\n"), rel + " 的换行符不再成对"
    return raw.splitlines()


def section_body(rows, mark=SECTION_MARK):
    """§9.3 那一节的行：标题行之下、下一枚二或三级标题之前。标题位置按现读定位。"""
    hits = [i for i, line in enumerate(rows) if line.startswith(mark)]
    assert len(hits) == 1, "文档里 " + mark + " 命中 " + str(len(hits)) + " 枚，本该恰一枚"
    body = []
    for offset in range(hits[0] + 1, len(rows)):
        line = rows[offset]
        if line.startswith("## ") or line.startswith("### "):
            break
        body.append((offset + 1, line))
    return body


def table_of(section):
    """该节第一张表：表头行 + 分隔行 + 逐行数据，遇非表格行即止。"""
    starts = [i for i, (_no, text) in enumerate(section) if text.startswith("| ")]
    assert starts, "§9.3 那一节里读不出表格：这一节改形状了"
    rows = []
    for i in range(starts[0], len(section)):
        no, text = section[i]
        if not text.startswith("|"):
            break
        rows.append((no, text))
    assert len(rows) >= 3, "§9.3 那张表只切出 " + str(len(rows)) + " 行：连表头带数据都不成立"
    return rows


def cells_of(text):
    body = text.strip()
    assert body.startswith("|") and body.endswith("|"), "表格行首尾不齐，切不出列：" + body[0:CLIP]
    return [piece.strip() for piece in body.strip("|").split("|")]


def derive(key):
    assert key in TOOL_MODULE.LINEAGE_SITES, "那一行点名的锚 key 不在册：" + key
    return TOOL_MODULE.resolve_site(key, REPO)


def rendered(first, last):
    return str(first) if first == last else str(first) + "-" + str(last)


def claims_of(cell, carried):
    """最后一列里的坐标 [(文件, 起, 止, 自带文件, 数字段位置)]；文件沿用列内最近一次显式声明。"""
    found = []
    owner = carried
    for match in CITE.finditer(cell):
        path = match.group("file")
        first = int(match.group("start"))
        stop = match.group("stop")
        last = int(stop) if stop else first
        where = (match.start("start"), match.end("stop") if stop else match.end("start"))
        if path:
            owner = path
        found.append((owner, first, last, bool(path), where))
    return found, owner


def row_keys(row):
    """这一行点名的锚 key（按出现顺序，去重）。"""
    keys = []
    for cell in row[:-1]:
        for match in KEY.finditer(cell):
            if match.group(0) not in keys:
                keys.append(match.group(0))
    return keys


def check(rows):
    """对账一次：交回 (红清单, 核过的坐标枚数, 无锚 key 的行数)。"""
    defects = []
    table = table_of(section_body(rows))
    header = cells_of(table[0][1])
    tail = header[-1]
    if LIVE_MARK not in tail:
        defects.append("表头：§9.3 最后一列不再自称「现读」—— 口径变了要连 §1 自守句与本件一起改，不许只改纸面")
    if PROVENANCE not in tail:
        defects.append("表头：§9.3 最后一列没写明值来自 " + PROVENANCE + "，读者无从判断这一格能不能查")
    checked = 0
    anchorless = 0
    carried = ""
    for no, text in table[2:]:
        row = cells_of(text)
        if len(row) != len(header):
            defects.append("第 " + str(no) + " 行列数与表头不等（" + str(len(row)) + " 对 " + str(len(header)) + "）：这一行切不出可信的列")
            continue
        keys = row_keys(row)
        claims, carried = claims_of(row[-1], carried)
        if not keys:
            anchorless += 1
            if claims:
                defects.append("第 " + str(no) + " 行点不出一枚锚 key，最后一列却端出 " + str(len(claims)) + " 枚坐标：无处派生，只能算手抄")
            continue
        if len(claims) != len(keys):
            defects.append("第 " + str(no) + " 行点了 " + str(len(keys)) + " 枚锚 key，最后一列却有 " + str(len(claims)) + " 枚坐标：不是逐格一一对上")
            continue
        for key, (file, first, last, _explicit, _where) in zip(keys, claims):
            want_file, want_first, want_last = derive(key)
            label = "第 " + str(no) + " 行 " + key + " 那一格 "
            if file != want_file:
                defects.append(label + "文件归属不对（裸坐标没有本列可沿用的显式文件，或指错了文件）：这枚锚在 " + want_file)
                continue
            if (first, last) != (want_first, want_last):
                defects.append(label + "表里印 " + rendered(first, last) + "、现读 " + rendered(want_first, want_last)
                               + "（" + want_file + "）—— 这一列只许 " + PROVENANCE + " 现场派生")
                continue
            checked += 1
    return defects, checked, anchorless


def tool_bytes():
    return hashlib.sha256(TOOL.read_bytes()).hexdigest()


def replace_cell(rows, key_want, builder):
    """把某一行的最后一列换成 builder 造出的新串（只在内存里，盘上一字不写）。"""
    out = list(rows)
    touched = 0
    for no, text in table_of(section_body(rows))[2:]:
        row = cells_of(text)
        if row_keys(row) != key_want:
            continue
        claims, _carried = claims_of(row[-1], "")
        out[no - 1] = "| " + " | ".join(row[:-1]) + " | " + builder(row[-1], claims) + " |"
        touched += 1
    assert touched == 1, "变异目标不唯一：那一行在表里出现 " + str(touched) + " 次"
    return out


# ---------------------------------------------------------------------------
# ①② 那一列的每一格 == 同行锚 key 的现场派生读数
# ---------------------------------------------------------------------------

def test_s9_3_coordinate_column_equals_the_derived_readings() -> None:
    defects, checked, _anchorless = check(read_rows())
    assert defects == [], "§9.3 最后一列与现场派生读数不等：\n  " + "\n  ".join(defects)
    assert checked >= FLOOR, "这一列今天只核到 " + str(checked) + " 枚坐标，不到 " + str(FLOOR) + " 枚：这格没在量东西"


def test_s9_3_header_still_owns_the_live_claim() -> None:
    defects, _checked, _anchorless = check(read_rows())
    assert [item for item in defects if item.startswith("表头")] == [], \
        "§9.3 最后一列的表头不再是「自称现读 + 写明派生来源」：这一列的口径被人动了"


def test_the_no_anchor_row_stays_an_honest_placeholder() -> None:
    _defects, _checked, anchorless = check(read_rows())
    assert anchorless >= 1, "§9.3 那张表里连一行「本单没有这枚锚」的诚实占位都没有了：落空账不许被悄悄抹平"


# ---------------------------------------------------------------------------
# ⑥ 本件自己不许带账，也不许碰量具
# ---------------------------------------------------------------------------

def test_this_pin_carries_no_copied_coordinates() -> None:
    source = Path(__file__).resolve().read_bytes().decode("utf-8")
    bad = [text.strip()[0:CLIP] for text in source.splitlines() if COPIED.search(text)]
    assert not bad, "本件里长出抄来的行号：" + " / ".join(bad)


def test_this_pin_writes_nothing_to_the_deriver() -> None:
    before = tool_bytes()
    check(read_rows())
    assert tool_bytes() == before, "本件在取证时动了那支取档脚本"


# ---------------------------------------------------------------------------
# 牙：每把摘掉一样东西，必须红，且红在它那一样上
# ---------------------------------------------------------------------------

def test_teeth_a_bumping_one_cell_turns_red() -> None:
    want_file, want_first, _want_last = derive("hop2")
    rows = replace_cell(read_rows(), ["hop2"],
                        lambda cell, claims: cell.replace(rendered(claims[0][1], claims[0][2]),
                                       rendered(want_first + 1, want_first + 1)))
    defects, _checked, _anchorless = check(rows)
    assert any("hop2" in item and "表里印" in item for item in defects), "把那一格挪一行竟然不红"


def test_teeth_b_swapping_two_cells_turns_red() -> None:
    keys = ["hop5f", "hop5g", "hop5h", "hop5i", "hop5j"]
    low, high = derive(keys[0])[1], derive(keys[1])[1]

    def swap(cell, claims):
        first = rendered(claims[0][1], claims[0][2])
        second = rendered(claims[1][1], claims[1][2])
        assert first != second, "前提不成立：这两格本来就同值，换序量不出东西"
        out = cell.replace(first, "\0", 1).replace(second, first, 1).replace("\0", second, 1)
        return out

    rows = replace_cell(read_rows(), keys, swap)
    defects, _checked, _anchorless = check(rows)
    assert len([item for item in defects if "表里印" in item]) == 2, "换序没被逐格对账抓住：这一列其实只认集合不认序"


def test_teeth_c_renaming_the_header_washes_the_column() -> None:
    rows = list(read_rows())
    header_no = table_of(section_body(rows))[0][0]
    rows[header_no - 1] = rows[header_no - 1].replace(LIVE_MARK, "当时")
    defects, _checked, _anchorless = check(rows)
    assert any(item.startswith("表头") for item in defects), "把表头洗成历史账竟然不红：降级可以悄悄发生"


def test_teeth_d_a_coordinate_on_the_anchorless_row_is_caught() -> None:
    rows = list(read_rows())
    target = None
    for no, text in table_of(section_body(rows))[2:]:
        row = cells_of(text)
        if not row_keys(row):
            target = no
            break
    assert target, "表里没有无锚 key 的那一行了：这一把牙量不到东西"
    ghost = derive("hop2")[1] + 7
    planted = ("| " + " | ".join(cells_of(rows[target - 1])[:-1]) + " | "
               + derive("hop2")[0] + ":" + rendered(ghost, ghost) + " |")
    rows[target - 1] = planted
    defects, _checked, _anchorless = check(rows)
    assert any("无处派生" in item for item in defects), "给没有锚的那一行编一枚坐标竟然不红"


def test_teeth_e_dropping_the_file_prefix_loses_attribution() -> None:
    prefix = derive("hop2")[0]
    rows = replace_cell(read_rows(), ["hop2"], lambda cell, claims: cell.replace(prefix + ":", ""))
    defects, _checked, _anchorless = check(rows)
    assert any("文件归属不对" in item for item in defects), "摘掉本列唯一的显式文件竟然不红：裸坐标可以无人认领"


def test_teeth_f_dropping_a_row_empties_the_coverage() -> None:
    keys = ["hop5f", "hop5g", "hop5h", "hop5i", "hop5j"]
    rows = list(read_rows())
    victim = [no for no, text in table_of(section_body(rows))[2:] if cells_of(text) and row_keys(cells_of(text)) == keys]
    assert len(victim) == 1, "删行的靶子不唯一"
    del rows[victim[0] - 1]
    defects, checked, _anchorless = check(rows)
    assert checked < FLOOR, "删掉五行坐标那一格，覆盖数竟然还够：" + str(checked)
    assert checked < 1 + len(keys) + 1 + 1 + 4, "数量闸读不出这张表被削了一整行"