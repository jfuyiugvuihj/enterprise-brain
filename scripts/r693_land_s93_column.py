# -*- coding: utf-8 -*-
"""R693 —— §9.3 那一列的机械写回口（数字一律现场派生，人手一个都不抄）。

病形（工单 R693 现取）：在册血缘文档 §9.3 的最后一列自称「本班现读」，可盘上那几格冻在上一班的
偏移上；在册牙件 tests/test_r492_s93_column_matches_derived.py 逐格拿 resolve_site 复算，当场把
那九格一起点名。在册写回口 scripts/r387_label_lineage.py --land 只覆盖 §1 那张表与正文里那些派生
数，§9.3 这一列今天没有写回口——本件补的就是那一格，纪律与 §1 同源：
  ① 值只从派生器取（resolve_site(key, root)），本件源码里一枚行号数字都没有；
  ② 逐格按序对：行左列点名的锚 key 与最后一列的坐标枚数不等 ⇒ 整本拒写，一枚字节都不落；
  ③ 文件归属对不上（裸坐标沿用的那枚文件与锚所在文件不同）⇒ 拒写并点名；
  ④ 锚腐（派生器自报 LINEAGE_ANCHOR_FAILURES）⇒ 拒写 rc=3，绝不带腐锚出账；
  ⑤ 行尾照盘上那本还原：成对 CRLF 还 CRLF，纯 LF 还 LF——混行尾会让逐字节钉天天误红；
  ⑥ 只动数字那一段，行里其它字节（反引号、箭头、括号、对齐空格）一枚不重排。

只读产品码：不碰 app／不连库／不起服务／不打模型。唯一写口是 --doc 指名的那本 .md。
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DERIVER = ROOT / "scripts" / "r387_label_lineage.py"
DOC_REL = "docs/perf/r387-label-lineage-2026-09-27.md"
SECTION_MARK = "### " + "9.3"

#: 与在册牙件同一形状：左列的锚 key，与最后一列的坐标（冒号紧贴数字，可带区间）。
KEY = re.compile(r"\bhop[0-9]+[a-z]?\b")
COLON = ":"
CITE = re.compile(
    r"(?P<file>[A-Za-z0-9_./-]+[.](?:py|vue|sql))?"
    + COLON
    + r"(?P<start>[0-9]+)(?:-(?P<stop>[0-9]+))?",
)

RC_CLEAN = 0
RC_DRIFT = 5
RC_NOT_FOUND = 2
RC_ANCHOR_ROTTEN = 3
RC_REFUSED = 4


def load_deriver(path: Path = DERIVER):
    """把取档函数请进来：行号的唯一来源，本件自己不解释锚。"""
    spec = importlib.util.spec_from_file_location("r387_for_r693", path)
    assert spec and spec.loader, "加载不到取档函数：" + str(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def render(first: int, last: int) -> str:
    return str(first) if first == last else "%d-%d" % (first, last)


def cells_of(line: str) -> list:
    return [piece.strip() for piece in line.strip().strip("|").split("|")]


def row_keys(row: list) -> list:
    keys: list = []
    for cell in row[:-1]:
        for match in KEY.finditer(cell):
            if match.group(0) not in keys:
                keys.append(match.group(0))
    return keys


def claims_of(cell: str, carried: str) -> tuple:
    """最后一列里的坐标 [(文件, 起, 止, 自带文件, 数字段位置)]；文件沿用列内最近一次显式声明。"""
    found = []
    owner = carried
    for match in CITE.finditer(cell):
        declared = match.group("file")
        first = int(match.group("start"))
        stop = match.group("stop")
        last = int(stop) if stop else first
        where = (match.start("start"), match.end("stop") if stop else match.end("start"))
        if declared:
            owner = declared
        found.append((owner, first, last, bool(declared), where))
    return found, owner


def last_cell_span(line: str):
    """交回最后一列文本在整行里的 (起, 止)：只认竖线，不重排任何字节。"""
    bars = [index for index, char in enumerate(line) if char == "|"]
    if len(bars) < 2:
        return None
    return bars[-2] + 1, bars[-1]


def table_data_rows(rows: list) -> list:
    """定位 §9.3 第一张表的数据行下标（表头行与分隔行之后的连续竖线行）。"""
    hits = [index for index, line in enumerate(rows) if line.startswith(SECTION_MARK)]
    if len(hits) != 1:
        raise RuntimeError("文档里 §9.3 那一节命中 " + str(len(hits)) + " 枚，本该恰一枚，拒绝落地")
    body_end = len(rows)
    for index in range(hits[0] + 1, len(rows)):
        if rows[index].startswith("## ") or rows[index].startswith("### "):
            body_end = index
            break
    starts = [index for index in range(hits[0] + 1, body_end) if rows[index].startswith("| ")]
    if not starts:
        raise RuntimeError("§9.3 那一节里读不出表格：这一节改形状了，拒绝落地")
    table = []
    for index in range(starts[0], body_end):
        if not rows[index].startswith("|"):
            break
        table.append(index)
    if len(table) < 3:
        raise RuntimeError("§9.3 那张表只切出 " + str(len(table)) + " 行：连表头带数据都不成立")
    return table[2:]


def land(text: str, resolve, root: Path = ROOT) -> tuple:
    """交回 (新正文, 改动枚数, 拒写清单)。拒写清单非空时调用方一枚字节都不许写盘。"""
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = text.split(newline)
    refusals: list = []
    changed = 0
    carried = ""
    for index in table_data_rows(rows):
        line = rows[index]
        span = last_cell_span(line)
        if span is None:
            refusals.append("第 " + str(index + 1) + " 行切不出最后一列：这一行形状不可信")
            continue
        cell_start, cell_stop = span
        original = line[cell_start:cell_stop]
        keys = row_keys(cells_of(line))
        claims, carried = claims_of(original, carried)
        if not keys:
            if claims:
                refusals.append("第 " + str(index + 1) + " 行点不出一枚锚 key，最后一列却有 "
                                + str(len(claims)) + " 枚坐标：无处派生，本件拒绝替它编数")
            continue
        if len(claims) != len(keys):
            refusals.append("第 " + str(index + 1) + " 行点了 " + str(len(keys)) + " 枚锚 key，"
                            + "最后一列却有 " + str(len(claims)) + " 枚坐标：逐格对不上，拒绝半落地")
            continue
        edits = []
        rejected = False
        for key, (owner, first, last, _explicit, where) in zip(keys, claims):
            want_file, want_first, want_last = resolve(key, root)
            label = "第 " + str(index + 1) + " 行 " + key + " 那一格"
            if owner != want_file:
                refusals.append(label + " 文件归属不对（列内沿用 " + (owner or "无主")
                                + "、锚在 " + want_file + "）：不敢替别的文件认领坐标")
                rejected = True
                break
            if (first, last) == (want_first, want_last):
                continue
            edits.append((where, render(want_first, want_last)))
        if rejected:
            continue
        cell = original
        for (start, stop), payload in sorted(edits, key=lambda item: -item[0][0]):
            cell = cell[:start] + payload + cell[stop:]
        if cell != original:
            rows[index] = line[:cell_start] + cell + line[cell_stop:]
            changed += len(edits)
    return newline.join(rows), changed, refusals


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="§9.3 最后一列机械写回（数字全部现场派生）")
    parser.add_argument("--doc", default=DOC_REL, help="要写回的那本（默认在册血缘文档）")
    parser.add_argument("--repo-root", default="", help="锚按哪棵树解析；缺省为本件所在树")
    parser.add_argument("--check", action="store_true",
                        help="只报会改几格，一枚字节都不写；盘上已漂时 rc=" + str(RC_DRIFT))
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve() if args.repo_root else ROOT
    doc = Path(args.doc) if Path(args.doc).is_absolute() else root / args.doc
    if not doc.is_file():
        print("ABORT: 读不到要写回的文档 " + str(doc), file=sys.stderr)
        return RC_NOT_FOUND
    deriver = load_deriver()
    failures = list(getattr(deriver, "LINEAGE_ANCHOR_FAILURES", []))
    if failures:
        print("ABORT: 血缘锚不再是唯一锚，带腐锚落地＝把假行号交给下游：", file=sys.stderr)
        for item in failures:
            print("  - " + item, file=sys.stderr)
        return RC_ANCHOR_ROTTEN
    text = doc.read_bytes().decode("utf-8")
    landed, changed, refusals = land(text, deriver.resolve_site, root)
    if refusals:
        for item in refusals:
            print("REFUSE: " + item, file=sys.stderr)
        print("ABORT: 本次一枚字节都没写盘（拒绝半落地）。", file=sys.stderr)
        return RC_REFUSED
    if args.check:
        print("现读对账：" + args.doc + " 会改写 " + str(changed) + " 格")
        return RC_CLEAN if changed == 0 else RC_DRIFT
    if changed == 0:
        print("那一列已经是现场派生读数，一枚字节都不必动：" + args.doc)
        return RC_CLEAN
    doc.write_bytes(landed.encode("utf-8"))
    print("已按现读机械改写 " + str(changed) + " 格：" + args.doc)
    return RC_CLEAN


if __name__ == "__main__":
    sys.exit(main())
