# -*- coding: utf-8 -*-
"""R490 · 常驻钉：纸面上自称「现读」的坐标，只许是取档函数现场交回的那一枚。

病灶（工单 R490，本单基点 a0ec662）：血缘文档 `docs/perf/r387-label-lineage-2026-09-27.md` §1 那张表
今天已按锚重落地，但表外的正文里还留着两枚主张当下形状的旧坐标 —— §3 方案 A 那句「`department` 早就
在参数链上」，与 §8.7 那句「凭据 `INSERT INTO document_versions` 现读在 …」。表跟着派生走、正文不跟着
走，同一本纸上就并排摆着两把尺：照正文派工的人拿到的是过期行号。R490 把那两处换成派生值，本件负责让
它们换了之后漂不了。

本件钉什么（全程只读盘上字节：零写口、不连库、不起服务、不打模型）：
  ① 逐行扫在册纸面，凡该行带「现读」字样、且坐标落在取档函数管辖的文件上，就与 `resolve_site` 现场
     交回的值对账，不等即红。§1 那张表由 `tests/test_r387_label_ruler_teeth.py` 逐跳钉着（它那枚
     表下正文闸只管到 §1 标题与下一枚二级标题之间），本件不重复钉表，只补它管不到的表外正文；
  ② 「旧 X / 新 Y」那种成对叙述是历史账（§8.7 那次重锚留下的），不是现读声称：一枚坐标只有当同一行
     同时挂着「旧」与「新」两枚标号、且标号就贴在这枚坐标前面，才许跳过；跳行之余这一行必须还剩
     至少一枚真被核过的坐标 —— 想补一枚标号把整行洗成历史，本件当场红；
  ③ 台账不许空转：那本血缘纸今天必须至少端出一枚对得上账的现读坐标，一枚都没有就是这格没在量东西；
  ④ 本件一枚坐标都不许抄：数一律 import `scripts/r387_label_lineage.py` 的取档函数现场拿（自扫：
     源码里读不出「冒号紧贴数字」的写法），那支脚本本身也不许被本件写过一笔；
  ⑤ 牙（只在内存里改，盘上一字不写）：把一枚真现读坐标挪一行、把「现读」字样全删、编一枚越界坐标
     冒充现读、把成对叙述那枚真坐标贴成历史、给没有锚的文件编一枚坐标 —— 各红各的。

🔴 行号一律运行时派生：本件不出现任何写死的坐标，只有 `+ 1`、下标这类算绪，没有第二本账。
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


def _load_tool():
    spec = importlib.util.spec_from_file_location("r387_label_lineage", TOOL)
    assert spec and spec.loader, "加载不到取档函数：" + str(TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL_MODULE = _load_tool()

#: 只有自称现读的坐标才受本件对账；历史读数按 §8.7 那条自守原样留档。
LIVE_MARK = "现读"

#: 派工词点的三枚被引件。取档函数管不到的文件一旦被人写成现读，本件照样红着要锚。
TARGET_FILES = ("app/documents/catalog.py", "app/common/rbac.py", "app/agents/contracts.py")

#: 被钉的纸面：血缘文档，加上同一条链上另两本会引它的纸（本件对它们只读不写）。
DOCS = ("docs/perf/r387-label-lineage-2026-09-27.md",
        "docs/handoff/2026-09-23-v1-acceptance-record.md",
        "docs/handoff/2026-09-17-pgvector-adoption-plan.md")

#: ③ 这本纸今天必须至少对上一枚现读坐标，否则本件是在空转。
LEDGER_DOCS = ("docs/perf/r387-label-lineage-2026-09-27.md",)

#: ② 成对叙述的两枚标号，以及「标号贴着坐标」的分句边界。
HISTORY_MARKS = ("旧", "新")
CLAUSE_CUTS = "`（）()，、；;:："

CITE = re.compile(
    r"(?P<file>[A-Za-z0-9_./-]+[.](?:py|vue|sql|md|toml|json))"
    r"(?::(?P<fstart>\d+)(?:-(?P<fstop>\d+))?)?"
    r"|:(?P<bstart>\d+)(?:-(?P<bstop>\d+))?"
)
CLAUSE = re.compile("[" + re.escape(CLAUSE_CUTS) + "]")
LABEL = re.compile(r"(?P<rel>\S+) 第 (?P<no>\d+) 行 (?P<site>\S+)")
COPIED = re.compile(r":\d")
#: 红句里每枚条目只端出行首那一截，免得整本纸糊满屏（与坐标无关的字面量）。
CLIP = 72


def read_rows(rel):
    """现读盘上那一本：先证明换行符仍成对，再按行切开。行号 = 下标 + 1。"""
    raw = (REPO / rel).read_bytes().decode("utf-8")
    assert raw.count("\r") == raw.count("\n"), rel + " 的换行符不再成对"
    return raw.splitlines()


def tool_bytes():
    return hashlib.sha256(TOOL.read_bytes()).hexdigest()


def derived_spans():
    """每枚被引文件的派生区间 + 锚失效清单：数全部由取档函数现场交回，本件不抄。"""
    spans, failures = {}, []
    for key, (file, _start, _end) in TOOL_MODULE.LINEAGE_SITES.items():
        try:
            _name, first, last = TOOL_MODULE.resolve_site(key, REPO)
        except (TOOL_MODULE.AnchorNotUnique, OSError) as exc:
            failures.append("锚 " + key + " 解不出来：" + str(exc))
            continue
        spans.setdefault(file, set()).add((first, last))
    return spans, failures


def alias_map(spans):
    """裸文件名 -> 全路径：只在这本账里唯一才认，撞名就不认（宁可红，不许指错文件）。"""
    seen = {}
    for file in spans:
        seen.setdefault(file.rsplit("/", 1)[-1], set()).add(file)
    return {base: next(iter(paths)) for base, paths in seen.items() if len(paths) == 1}


def canonical(path, aliases):
    return path if "/" in path else aliases.get(path, path)


def reads_as_history(line, before):
    """②：整行同时挂着「旧」与「新」，且标号就贴在这枚坐标前 —— 才算成对叙述。"""
    if not all(mark in line for mark in HISTORY_MARKS):
        return False
    pieces = [piece for piece in CLAUSE.split(before) if piece.strip()]
    clause = pieces[-1] if pieces else ""
    return any(mark in clause for mark in HISTORY_MARKS)


def claims_in_line(line, carried):
    """一行之内的坐标主张 [(文件, 起, 止, 行内位置, 算不算历史)]，文件沿用最近一次出现的那枚。"""
    found = []
    owner = carried
    tail = 0
    for match in CITE.finditer(line):
        path = match.group("file")
        which = "fstart" if match.group("fstart") else "bstart"
        if which == "bstart" and not match.group("bstart"):
            if path:
                owner = path
            continue
        stop_group = "fstop" if which == "fstart" else "bstop"
        stop = match.group(stop_group)
        first = int(match.group(which))
        last = int(stop) if stop else first
        where = (match.start(which), match.end(stop_group) if stop else match.end(which))
        before = line[tail:where[0]]
        tail = where[1]
        if path:
            owner = path
        found.append((owner, first, last, where, reads_as_history(line, before)))
    return found, owner


def matches(pool, first, last):
    """单值坐标认区间端点，区间坐标认整枚区间 —— 两样都只与派生值比。"""
    if first == last:
        return any(first in (low, high) for low, high in pool)
    return (first, last) in pool


def rendered(first, last):
    return str(first) if first == last else str(first) + "-" + str(last)


def scan_doc(rel, rows, spans, aliases):
    """对账一本：交回红清单、核过的坐标、按行号跳过的历史坐标。"""
    defects, checked, historical = [], [], []
    carried = ""
    for no, line in enumerate(rows, 1):
        if not line.strip():
            carried = ""
            continue
        found, carried = claims_in_line(line, carried)
        if LIVE_MARK not in line:
            continue
        live = 0
        settled = 0
        for owner, first, last, _where, history in found:
            path = canonical(owner, aliases)
            if path not in TARGET_FILES:
                continue
            live += 1
            label = rel + " 第 " + str(no) + " 行 " + path + ":" + rendered(first, last)
            pool = spans.get(path)
            if not pool:
                defects.append(label + "：这枚文件在取档函数里没有锚，现读坐标无处对账")
                settled += 1
                continue
            if history:
                historical.append(label)
                continue
            if not matches(pool, first, last):
                defects.append(label + " 不是派生值（现读只有 "
                               + "、".join(sorted(rendered(low, high) for low, high in pool)) + "）")
                settled += 1
                continue
            checked.append(label)
            settled += 1
        if live and not settled:
            defects.append(rel + " 第 " + str(no) + " 行挂着 " + str(live)
                           + " 枚目标文件的现读坐标，却一枚都没核 —— 全被历史标号吃掉了")
    if rel in LEDGER_DOCS and not checked:
        defects.append(rel + " 里读不到任何对得上账的现读坐标：这一格今天没在量东西")
    return defects, checked, historical


def ledger(rel, rows=None):
    spans, failures = derived_spans()
    aliases = alias_map(spans)
    defects, checked, historical = scan_doc(
        rel, rows if rows is not None else read_rows(rel), spans, aliases)
    return defects + list(failures), checked, historical


def whole_book():
    defects, checked, historical = [], [], []
    for rel in DOCS:
        _defects, _checked, _historical = ledger(rel)
        defects += _defects
        checked += _checked
        historical += _historical
    return defects, checked, historical


def first_live_claim(rel):
    """台账里第一枚对得上账的单行现读坐标：(行号, 行原文, 行内位置, 值)。"""
    rows = read_rows(rel)
    _defects, checked, _historical = ledger(rel, rows)
    assert checked, "找不到可对账的现读坐标，牙咬不动"
    parts = LABEL.match(checked[0])
    assert parts, "台账标签读不回来自派生的形状：" + checked[0]
    no = int(parts.group("no"))
    digits = parts.group("site").rpartition(":")[2]
    line = rows[no - 1]
    for _owner, first, last, where, history in claims_in_line(line, "")[0]:
        if first == last and not history and str(first) == digits:
            return no, line, where, first
    raise AssertionError("台账里那枚坐标回到行内找不到：" + checked[0])


def test_live_reads_in_the_books_match_the_deriver():
    defects, _checked, _historical = whole_book()
    assert defects == []


def test_the_live_read_ledger_is_not_vacuous():
    _defects, checked, _historical = whole_book()
    assert checked, "整轮扫描一枚现读坐标都没核到：本件今天没在量东西"
    for rel in LEDGER_DOCS:
        assert any(item.startswith(rel) for item in checked), rel + " 一枚现读坐标都没进账"


def test_the_skipped_ones_really_are_paired_narrative():
    """② 的另一半：确实在跳，但跳掉的必须是被 旧/新 两枚标号同时夹着的那几枚。"""
    _defects, _checked, historical = whole_book()
    assert historical, "成对叙述那几枚今天没被读出来：跳过规则已经形同虚设"
    for item in historical:
        parts = LABEL.match(item)
        assert parts, "历史账标签形状不对：" + item
        line = read_rows(parts.group("rel"))[int(parts.group("no")) - 1]
        assert all(mark in line for mark in HISTORY_MARKS), "跳过的坐标不在成对叙述里：" + item


def test_this_pin_carries_no_copied_coordinates():
    source = Path(__file__).resolve().read_bytes().decode("utf-8")
    bad = [(no, text.strip()[0:CLIP]) for no, text in enumerate(source.splitlines(), 1) if COPIED.search(text)]
    assert not bad, "本件里长出抄来的行号：" + " / ".join(text for _no, text in bad)


def test_this_pin_writes_nothing_to_the_deriver():
    before = tool_bytes()
    whole_book()
    assert tool_bytes() == before, "本件在取证时动了那支取档脚本"


def test_teeth_a_bumping_a_live_coordinate_turns_red():
    rel = LEDGER_DOCS[0]
    no, line, where, value = first_live_claim(rel)
    moved = list(read_rows(rel))
    moved[no - 1] = line[:where[0]] + ":" + str(value + 1) + line[where[1]:]
    assert moved[no - 1] != line, "变异没落地"
    defects, _checked, _historical = ledger(rel, moved)
    assert any(" 第 " + str(no) + " 行 " in item for item in defects), "把现读坐标挪一行竟然不红"


def test_teeth_b_erasing_the_live_wording_empties_the_ledger():
    rel = LEDGER_DOCS[0]
    rows = [text.replace(LIVE_MARK, "当时") for text in read_rows(rel)]
    defects, checked, historical = ledger(rel, rows)
    assert not checked, "抹掉「现读」字样之后竟然还核得到坐标：字样根本不是入口"
    assert not historical, "抹掉字样之后成对叙述那几枚竟然还算数"
    assert defects, "台账被抹空竟然不红：这一格会静默失效"


def test_teeth_c_a_fabricated_live_coordinate_is_caught():
    spans, _failures = derived_spans()
    ghost = 1 + max(high for pool in spans.values() for _low, high in pool)
    probe = "见 `app/documents/catalog.py:" + str(ghost) + "` " + LIVE_MARK
    defects, checked, _historical = ledger(LEDGER_DOCS[0], read_rows(LEDGER_DOCS[0]) + [probe])
    assert any("catalog.py" in item and "不是派生值" in item for item in defects), \
        "编一枚越界坐标冒充现读竟然不红"


def test_teeth_d_laundering_a_live_claim_as_history_is_caught():
    spans, _failures = derived_spans()
    ghost = 1 + max(high for pool in spans.values() for _low, high in pool)
    probe = ("见 `app/documents/catalog.py` 的旧 `:" + str(ghost) + "` / 新 `:"
             + str(ghost + 1) + "` " + LIVE_MARK)
    defects, _checked, _historical = ledger(LEDGER_DOCS[0], read_rows(LEDGER_DOCS[0]) + [probe])
    assert any("全被历史标号吃掉了" in item for item in defects), \
        "两枚坐标全贴成历史竟然不红：跳过规则可以被人洗白"
    assert not any("不是派生值" in item and str(ghost) in item for item in defects), \
        "成对叙述那两枚本该按历史跳过，不该报值错"


def test_teeth_e_an_unanchored_file_cannot_pass_as_a_live_read():
    spans, _failures = derived_spans()
    ghost = 1 + max(high for pool in spans.values() for _low, high in pool)
    probe = "见 `app/common/rbac.py:" + str(ghost) + "` " + LIVE_MARK
    defects, _checked, _historical = ledger(LEDGER_DOCS[0], read_rows(LEDGER_DOCS[0]) + [probe])
    assert any("rbac.py" in item and "没有锚" in item for item in defects), \
        "给没有锚的文件编一枚现读坐标竟然不红"
