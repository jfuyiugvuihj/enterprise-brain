# -*- coding: utf-8 -*-
"""R455 · 缺口单里那三枚后端坐标改按**符号**现读：手抄一枚当场红，漂一枚也当场红。

病灶（工单 R455，本单基点 `c2e6546`）：`docs/handoff/2026-09-26-v1-frontend-gap-list.md`
里 T2／G04／G06／G08／§遗留 2 五枚行内引用抄的全是 `app/api/v1/chat.py:NNNN` 这种行号。
为这一族返工已经两笔：R387/R400 那本血缘账先漂一次，R404 并树又给 `chat.py` 的 import 块
净 +1、版本史那条腿净 +17，缺口单再漂一次。本单不做第三遍抄写 —— 抄来的数必被后续并树打红，
出路只有一条：**数字从来就不该由人来写**。

三枚锚（判据①，全部按符号定位，行号只是落点的读数）：

  upload_form     `classification: int = Form(1)` 所在**签名的行区间**（起点
                  `async def upload_document(...)`、终点 `request: FastAPIRequest = None):`），
                  缺口单那一格引的是区间里 Form 缺省自己；
  queue_cancel    `@router.post("/queue/{request_id}/cancel")` 那一行；
  sessions_route  `@router.get("/sessions")` 那一行。

🔴 派生道只此一份：本件 import `scripts/r387_label_lineage.py` 的 `_one_hit`/`anchor_lines`/
`_lines_of`（`rg -F` 语义：逐行 strip 之后连续固定串匹配；命中 0 枚＝锚已腐，命中 ≥2 枚＝
不再是唯一锚），自己**一枚正则都没写**，r387 的本体一个字没改。

🔴 写错层另有牙：每枚锚都带层判据 —— 路由那一枚必须落在 `@router.` 装饰器上、且下一行读得出
   端点定义；Form 那一枚必须落在签名区间之内。引 `_ensure_session` 冒充 `GET /sessions` 路由本体，
   就算数字凑得一模一样也红（§126 那句「写下时就查错了层」正是这个形状）。

🔴 历史不追改：文末「### 附：」往后是当年现读（`ac84f1a`／`4037868`／`4cd0a1c`），那两张表由
   `history_frozen_diff` 逐行钉死，改一个字都红；`chat.py:3933` 那枚反证钉继续留着替
   「这枚已经漂了」说话。缺口单里那些行内引用才是**今天的断言**，它们与现读逐字节等值。

用法::

    python scripts/r455_gapdoc_coordinates.py                  # 三枚锚的现读全貌 + 对账
    python scripts/r455_gapdoc_coordinates.py --emit-doc-cells # 缺口单那一格的成品串
    python scripts/r455_gapdoc_coordinates.py --check           # 等值 rc=0／锚腐 rc=3／漂了 rc=4
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import r387_label_lineage as lineage  # noqa: E402  —— 派生道只此一份：锚块走它那把尺

CHAT = "app/api/v1/chat.py"
GAPDOC = "docs/handoff/2026-09-26-v1-frontend-gap-list.md"
CELL_HEAD = "app/api/v1/chat.py:"
#: 红句里那条唯一的出路：重落地是跑量具，不是手改数字，也不是拿旧数加减行号。
EMIT_COMMAND = "python scripts/r455_gapdoc_coordinates.py --emit-doc-cells"
#: 坐标串的合法字符：只有 ASCII 字母数字与路径/行号分隔符，一个字节都不多拿。
COORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-:")

#: 文末这一族标题往后是**历史读数**：当年的现读，不与今天的现读对撞，也不许追改。
HISTORIC_HEADING = "### 附："
#: 两张在册历史表：逐行与并树那一版比对，改一个字都红（判据③）。
HISTORIC_TABLES: tuple = (
    {"label": "附·09-28 坐标对账（主树 `4037868`）",
     "heading": "### 附：09-28 坐标对账（总控收口，主树 `4037868`）"},
    {"label": "附·09-28 坐标对账·第二笔（基点 `4cd0a1c`）",
     "heading": "### 附：09-28 坐标对账·第二笔（R404 在途，本笔基点 `4cd0a1c`）"},
)
#: 这枚旧号替「`DocPanel.vue:103` 那行注释已经漂了」反证说话：继续留着，不改口。
STALE_PROOF_TOKEN = CELL_HEAD + "3933"
STALE_PROOF_SHORT = "chat.py:" + "3933"
#: 09-28 现取的**枚数**（不是行号）：§遗留 2 一枚 + 文末两节三枚。多一枚少一枚都红。
STALE_PROOF_OCCURRENCES = 4

class CoordinateUnavailable(RuntimeError):
    """锚读不出唯一落点、或落点不在断言那一层：这时候端出旧数就是撒谎。"""


class HistoryRewritten(RuntimeError):
    """历史表与并树那一版不符：当年现读被人追改（判据③）。"""


def _rows(file: str, root: Path) -> list:
    """逐行 strip 过的被引文件 —— 走 r387 那枚缓存，不另起一份读法。"""
    return lineage._lines_of(root / file)


#: 三枚锚。锚块沿用 r387 那一族的结构：(目标行在块里的下标, 连续行原文)；键值里一枚数字都没有。
#:   start / end —— 签名区间；cite —— 缺口单那一格引的具体行（不给就用 start 那一行）；
#:   must_start / handler_start / must_contain —— 层判据：落点必须在哪一层，说死在这一格。
GAPDOC_SITES: dict = {
    "upload_form": {
        "file": CHAT,
        "symbol": "classification: int = Form(1)",
        "start": (0, ["async def upload_document(file: UploadFile = File(...),"]),
        "end": (0, ["request: FastAPIRequest = None):"]),
        "cite": (0, ["classification: int = Form(1),"]),
        "must_contain": "Form(",
    },
    "queue_cancel": {
        "file": CHAT,
        "symbol": "POST /queue/{request_id}/cancel 路由本体",
        "start": (0, ['@router.post("/queue/{request_id}/cancel")']),
        "end": None,
        "cite": None,
        "must_start": "@router.",
        "handler_start": "async def ",
    },
    "sessions_route": {
        "file": CHAT,
        "symbol": "GET /sessions 路由本体",
        "start": (0, ['@router.get("/sessions")']),
        "end": None,
        "cite": None,
        "must_start": "@router.",
        "handler_start": "async def ",
    },
}

#: 缺口单里今天还宣称「现读」的五枚行内引用（病灶点名的就是这五处）。
#: `row` 认那一行，`before` 认坐标左侧那一串 —— 两枚都是固定串，各须恰一枚命中。
LIVE_CITES: tuple = (
    {"label": "T2", "key": "upload_form",
     "row": "| T2 | 上传文档 → 知道「多久能被问到」",
     "before": "后端 `Form(1)` 只是缺省（现读 `"},
    {"label": "G04", "key": "sessions_route",
     "row": "| **G04** |",
     "before": "msg_count`（`"},
    {"label": "G06", "key": "queue_cancel",
     "row": "| **G06** |",
     "before": "后端路由现读 `"},
    {"label": "G08", "key": "upload_form",
     "row": "| **G08** |",
     "before": "后端那枚 `Form(1)` 现读在 `"},
    {"label": "§遗留 2", "key": "upload_form",
     "row": "2. `frontend/src/components/DocPanel.vue:103`",
     "before": "`classification: int = Form(1)` 在 `"},
)


def resolve_site(key: str, root: Path = ROOT, sites: dict | None = None) -> dict:
    """把一枚锚解成「文件 + 签名区间 + 那一格的行号 + 落点原文」。读不出／不唯一／落错层都抛。"""
    spec = (sites or GAPDOC_SITES)[key]
    file = spec["file"]
    try:
        first = lineage._one_hit(key + " 起点", file, spec["start"], root)
        last = first if spec.get("end") is None else lineage._one_hit(key + " 终点", file, spec["end"], root)
        line = first if spec.get("cite") is None else lineage._one_hit(key + " 符号", file, spec["cite"], root)
    except lineage.AnchorNotUnique as exc:
        raise CoordinateUnavailable(str(exc)) from exc
    if last < first:
        raise CoordinateUnavailable("%s：终点锚（%d）落到起点锚（%d）之前，区间不成立" % (key, last, first))
    if spec.get("cite") is not None and not first <= line <= last:
        raise CoordinateUnavailable("%s：%s 那一格读在第 %d 行，落在签名区间 %d-%d 之外 —— 引错了层"
                                   % (key, spec["symbol"], line, first, last))
    rows = _rows(file, root)
    face = rows[line - 1]
    if spec.get("must_start") and not face.startswith(spec["must_start"]):
        raise CoordinateUnavailable("现读落在第 %d 行 %r，那不是「%s」所在的一层（要的是以 %r 起头的路由装饰器）"
                                    " —— 写错层" % (line, face, spec["symbol"], spec["must_start"]))
    handler = spec.get("handler_start")
    if handler and not (len(rows) > line and rows[line].startswith(handler)):
        raise CoordinateUnavailable("第 %d 行 %r 下面那行是 %r，端点定义读不出来 —— 这一格引的不是路由本体"
                                    % (line, face, rows[line] if len(rows) > line else "<文件尽头>"))
    contain = spec.get("must_contain")
    if contain and contain not in face:
        raise CoordinateUnavailable("第 %d 行 %r 里没有 %r —— 这不是缺口单点的那一格" % (line, face, contain))
    return {"key": key, "file": file, "line": line, "signature": (first, last),
            "face": face, "cell": "%s%d" % (CELL_HEAD, line), "symbol": spec["symbol"]}


def derived_cells(root: Path = ROOT, sites: dict | None = None) -> tuple:
    """现读三枚锚 -> (渲染好的那一格, 失败清单)。失败不抛：让判据红在具名那一格（照 r387 规矩）。"""
    cells, failures = {}, []
    for key in (sites or GAPDOC_SITES):
        try:
            cells[key] = resolve_site(key, root, sites)["cell"]
        except CoordinateUnavailable as exc:
            failures.append("%s：%s" % (key, exc))
    return cells, failures


def readings(root: Path = ROOT, sites: dict | None = None) -> list:
    """三枚锚的现场全貌（含签名区间与落点原文），给人也给出账用。"""
    return [resolve_site(key, root, sites) for key in (sites or GAPDOC_SITES)]

def gapdoc_text(root: Path = ROOT, rel: str = GAPDOC) -> str:
    return (root / rel).read_bytes().decode("utf-8")


def _coordinate_token(tail: str) -> str:
    """从锚右侧那串字里读出坐标本体（文件名 + 冒号 + 行号），遇到第一个不属于它的字符就停。"""
    taken = 0
    while taken < len(tail) and tail[taken] in COORD_CHARS:
        taken += 1
    token = tail[:taken]
    head, sep, digits = token.rpartition(":")
    return token if sep and head and digits.isdigit() else ""


def _row_of(text: str, needle: str, label: str) -> tuple:
    rows = text.splitlines()
    hits = [index for index, row in enumerate(rows) if needle in row]
    if len(hits) != 1:
        raise CoordinateUnavailable("缺口单里定位不到那一格：%r 命中 %d 枚（要恰一枚）—— %s 这枚行内锚先腐了"
                                    % (needle, len(hits), label))
    return hits[0], rows[hits[0]]


def read_cite_cell(text: str, cite: dict) -> str:
    """端出缺口单那一格**此刻印着**的坐标串（逐字节，不含包裹它的反引号）。"""
    _index, row = _row_of(text, cite["row"], cite["label"])
    if row.count(cite["before"]) != 1:
        raise CoordinateUnavailable("%s：锚 %r 在那一行里出现 %d 次，读不出唯一那一格"
                                    % (cite["label"], cite["before"], row.count(cite["before"])))
    token = _coordinate_token(row.split(cite["before"], 1)[1])
    if not token:
        raise CoordinateUnavailable("%s：锚 %r 后面没有坐标了 —— 那一格的形状被人改过" % (cite["label"], cite["before"]))
    return token


def land_cells(text: str, cells: dict) -> str:
    """把现读的那三枚坐标写回五枚行内引用：只动坐标那一串字，前后各一个字节都不碰。

    这枚函数存在的意义就是「重落地是机械动作」—— 下一班既不必手改数字，也不必做行号算术。
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = text.split(newline)
    for cite in LIVE_CITES:
        want = cells.get(cite["key"])
        if want is None:
            continue
        hits = [index for index, row in enumerate(rows) if cite["row"] in row]
        if len(hits) != 1:
            raise CoordinateUnavailable("重落地时定位不到 %s：%r 命中 %d 枚" % (cite["label"], cite["row"], len(hits)))
        row = rows[hits[0]]
        at = row.find(cite["before"])
        if at < 0:
            raise CoordinateUnavailable("重落地时读不到 %s 那一格的锚 %r" % (cite["label"], cite["before"]))
        tail = row[at + len(cite["before"]):]
        token = _coordinate_token(tail)
        if not token:
            raise CoordinateUnavailable("重落地时读不到 %s 那一格的坐标" % cite["label"])
        cut = at + len(cite["before"])
        rows[hits[0]] = row[:cut] + want + row[cut + len(token):]
    return newline.join(rows)


def historic_cut(text: str) -> int:
    """第一枚「### 附：」的偏移：那往后是历史读数，本件只逐行钉它没被人追改，不比等值。"""
    index = text.find(HISTORIC_HEADING)
    return len(text) if index < 0 else index


def stray_coordinates(text: str, cells: dict, known=()) -> list:
    """历史区之外，本文每一枚 `app/api/v1/chat.py:NNNN` 都必须是派生读数（或那枚反证钉）。

    这一格才是「结构性关掉手抄」的落点：谁再往这本账里抄一枚新行号，本件当场红。
    `known` 是给行内引用登记在册的那几枚用的 —— 它们漂了由逐枚等值那把牙去喊，
    不在这里报第二遍（一次漂移报两种红，下一班就分不清该修锚还是该改格）。
    """
    body = text[:historic_cut(text)]
    derived = set(cells.values()) | set(known)
    out: list = []
    index = 0
    while True:
        found = body.find(CELL_HEAD, index)
        if found < 0:
            return out
        token = _coordinate_token(body[found:])
        if not token:
            index = found + len(CELL_HEAD)
            continue
        if token not in derived and token != STALE_PROOF_TOKEN:
            out.append(token)
        index = found + len(token)


def historic_region(text: str, heading: str) -> list:
    """这枚标题到下一枚标题之间的那一段（历史表本体，逐行）。"""
    rows = text.splitlines()
    hits = [index for index, row in enumerate(rows) if row.strip() == heading]
    if len(hits) != 1:
        raise HistoryRewritten("历史表标题 %r 命中 %d 枚（要恰一枚）" % (heading, len(hits)))
    region: list = []
    for row in rows[hits[0] + 1:]:
        if row.startswith("#"):
            break
        region.append(row)
    return region


def history_frozen_diff(text: str, base: str) -> list:
    """两张历史表逐行对账：当年现读被追改 ⇒ 红（判据③）。比的行内容，不比换行风格。"""
    red: list = []
    for table in HISTORIC_TABLES:
        try:
            now = historic_region(text, table["heading"])
            then = historic_region(base, table["heading"])
        except HistoryRewritten as exc:
            red.append("%s：%s" % (table["label"], exc))
            continue
        if now == then:
            continue
        for offset in range(max(len(now), len(then))):
            left = now[offset] if offset < len(now) else "<这一版少了这一行>"
            right = then[offset] if offset < len(then) else "<这一版多了这一行>"
            if left != right:
                red.append("%s：历史表第 %d 行被追改 —— 并树那一版是 %r，现在这版是 %r。"
                           "当年现读原样不追改（判据③）：要记今天的数就另起一笔，别改旧表"
                           % (table["label"], offset + 1, right, left))
    return red


def head_gapdoc(root: Path = ROOT) -> str:
    """并树那一版的缺口单（git 内存 LF、工作树是 CRLF，所以两边都按行内容比）。"""
    out = subprocess.run(["git", "show", "HEAD:" + GAPDOC], cwd=str(root), capture_output=True)
    if out.returncode != 0:
        raise CoordinateUnavailable("读不到 HEAD 里那版缺口单（`git show HEAD:%s` rc=%d）：%s"
                                    % (GAPDOC, out.returncode, out.stderr.decode("utf-8", "replace").strip()))
    return out.stdout.decode("utf-8")

def compare(root: Path = ROOT, sites: dict | None = None, text: str | None = None) -> dict:
    """把「缺口单那一格」与「按符号现读」逐枚对撞，端出读数与红清单。

    红清单为空才算这本账今天说得出现场。漂了一格的红句只指一条路：跑 `--emit-doc-cells` 重落地。
    """
    cells, failures = derived_cells(root, sites)
    body = gapdoc_text(root) if text is None else text
    broken = {item.partition("：")[0]: item for item in failures}
    covered = {item["key"] for item in LIVE_CITES}
    red: list = ["锚读不出来，先修锚再谈落地：" + item for item in failures
                 if item.partition("：")[0] not in covered]
    matched: list = []
    printed: list = []
    for cite in LIVE_CITES:
        want = cells.get(cite["key"])
        try:
            cell = read_cite_cell(body, cite)
        except CoordinateUnavailable as exc:
            red.append("%s：%s" % (cite["label"], exc))
            continue
        if want is None:
            red.append("%s（锚 %s）：现读这一步就断了，先修锚再谈落地，别顺手去改那一格的数字 —— %s（跑 `%s`）"
                       % (cite["label"], cite["key"], broken.get(cite["key"], "锚读不出来"), EMIT_COMMAND))
            continue
        printed.append(cell)
        if cell != want:
            red.append("%s（锚 %s）：那一格印 %s、按符号现读 %s ⇒ 这一格只有一条路：跑 `%s` 重落地，"
                       "不许手改数字，也不许拿旧数加减行号" % (cite["label"], cite["key"], cell, want, EMIT_COMMAND))
        else:
            matched.append("%s=%s" % (cite["label"], cell))
    stray = stray_coordinates(body, cells, printed)
    if stray:
        red.append("历史区之外多出来手抄的后端坐标（这一族只许出现派生读数）：" + "、".join(stray))
    stale = body.count(STALE_PROOF_SHORT)
    if stale != STALE_PROOF_OCCURRENCES:
        red.append("那枚替「已经漂了」反证说话的 `%s` 今天有 %d 枚、记账 %d 枚 —— "
                   "把它追改成今天的数就是抹掉那句反证（判据③）"
                   % (STALE_PROOF_SHORT, stale, STALE_PROOF_OCCURRENCES))
    return {"cells": cells, "matched": matched, "red": red, "failures": failures, "stray": stray,
            "stale_proof": stale}


def audit(root: Path = ROOT, sites: dict | None = None, text: str | None = None,
          base_text: str | None = None) -> dict:
    """compare 之外再补一刀历史表对账：追改历史与漂坐标分成两族红，各说各的话。"""
    body = gapdoc_text(root) if text is None else text
    report = compare(root, sites, body)
    report["history"] = history_frozen_diff(body, head_gapdoc(root) if base_text is None else base_text)
    report["red"].extend(report["history"])
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R455 缺口单后端坐标派生（只读，不改任何文件）")
    parser.add_argument("--emit-doc-cells", action="store_true",
                        help="把缺口单那一格的成品串按「锚名<TAB>格」打出来（行号是派生的，表不许手改）")
    parser.add_argument("--check", action="store_true",
                        help="那一格 vs 按符号现读：等值 rc=0；锚腐 rc=3；漂了或多手抄 rc=4")
    parser.add_argument("--no-history", action="store_true", help="不对历史表那两节（影子树里没有 git 时用）")
    parser.add_argument("--json", dest="out", default="", help="把全貌写成 JSON 文件（只写点名那一枚）")
    args = parser.parse_args(argv)

    cells, failures = derived_cells()
    if args.emit_doc_cells:
        for key in GAPDOC_SITES:
            print("%s\t%s" % (key, cells.get(key, "<锚失效:%s>" % key)))
        for item in failures:
            print("ABORT: 锚不再是唯一锚 -> " + item, file=sys.stderr)
        return 3 if failures else 0

    try:
        body = gapdoc_text()
        report = compare(text=body)
        if not args.no_history:
            report["history"] = history_frozen_diff(body, head_gapdoc())
            report["red"].extend(report["history"])
    except CoordinateUnavailable as exc:
        print("ABORT: " + str(exc), file=sys.stderr)
        return 3
    if failures:
        for item in failures:
            print("ABORT: " + item, file=sys.stderr)
        return 3
    if args.out:
        payload = {"cells": cells, "readings": readings(), "matched": report["matched"],
                   "red": report["red"], "stray": report["stray"],
                   "history": report.get("history", [])}
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                                   encoding="utf-8")
    for item in report["red"]:
        print("RED: " + item)
    print("现读：" + "、".join("%s=%s" % (key, cells[key]) for key in GAPDOC_SITES))
    print("缺口单行内引用逐字节等值 %d／%d 枚" % (len(report["matched"]), len(LIVE_CITES)))
    if args.out:
        print("全貌 -> " + args.out)
    return 4 if report["red"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
