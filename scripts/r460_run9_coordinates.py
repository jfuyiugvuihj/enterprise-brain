# -*- coding: utf-8 -*-
"""R460 · run9 读数本里那几枚「判据出处」后端坐标改按**符号**现读：抄错一枚当场红，漂一枚也当场红。

第一笔（工单 R460，基点 `49555eb`）治 :105／:115 两格；第二笔（R460 补令，同具身体）把
:107 与 :182 那格里同类的手抄坐标一并纳入派生道 —— 现在这本账里**在册断言共五枚**、锚共四枚。

病灶：`docs/testing/run9-readout-2026-09-28.md` 引的后端行号全是手抄的，并被后续并树打漂。
逐枚现读（在 `49555eb` 那棵树上，全部用符号锚取回）：

  :105 「…判据出处 `scripts/eval_transport_ask_v2.py:1106-1109`（命中即 raise 停窗）」
        → 那枚 raise 今天在 :1205-1208；:1106-1109 是队列轮询的 blip 记账（`book["last_blip"]`）。
  :115 「…（分母恒=105，见 `app/quality/eval.py:401-402`）」
        → 那句判据 4 今天在 :681-682；:401-402 躺的是**第二把尺越出 [0,1] 的 raise 校验**。
  :107 「C2 unsupported_claim_rate=0.0（…；算法 `app/quality/eval.py:471-477`）」
        → 那一格算法今天在 :761-767；:471-477 躺的是 `LATENCY_LEDGER_RATIO_TOLERANCE` /
          `LATENCY_LEDGER_SLACK_MS` 那两枚**时延容忍带常量** —— 与 unsupported_claim_rate 不同族，
          所以「措辞其实指时延」那枚反向结论在这里**不成立**（补令判据②问过这条路，答案是：
          那一格的措辞写死了「unsupported_claim_rate 键；算法」，而现读 :471-477 读不出这个键名、
          也读不出 `/ len(results)` 那把分母）。
  :182 「`app/quality/eval.py:468-469` 的 `total=len(rows)`、`answer_correctness=ratio(correct)`…
        `app/quality/eval.py:401-402` 原话『分母不因为甲案而变：卡闸的题现在拿真终答进分母』」
        → 那两行代码今天在 :757-758；那句原话今天在 :681-682（与 :115 同一枚锚，两处各一枚格）。

四枚锚**当初都没抄错**：`git show 2154318`（run9 收窗那一笔）里这四段逐字就在被引的那几行上，
是后续并树把文件撑长（eval.py +280／+290 行级偏移、采集器 +99 行）把手抄的数打漂了 ——
与 §129 三给缺口单定性的同一族，只是这次落在读数本上。

🔴 口径一字不动：本件只搬坐标，不搬事实。五枚格子里讲的读数（C1 缓存命中=0、C2 rate=0.0、
   分母恒=105 与并集 2/105＝metric-02／scope-02、kind 的差别只在分子上）由正文承担，
   本件不读也不写它们；`test_r460_*` 里那枚「措辞逐句回读」的钉反过来替它们说话。

四枚锚（判据①，全部按符号定位，行号只是落点的读数；块尾另有一枚锚，锚腐即拒发读数）：

  eval_denominator        `evaluate_evaluation_set` docstring 里那句「🔴 分母不因为甲案而变
                          （判据 4）：`total` 与 `answer_correctness` 恒按全部题数算，」，
                          块尾认「卡闸的题现在拿真终答进分母…」；
  report_denominator_code 报告 dict 的 `"total": len(rows),` 那一行，块尾认
                          `"answer_correctness": ratio([item["correct"] for item in results]),`；
  unsupported_claim_rate  报告 dict 的 `"unsupported_claim_rate": round(` 起头四行，块尾认
                          `)` + `if results` + `else 0.0,`；块内必须同时读得出
                          `unsupported_claims`（分子）与 `/ len(results),`（分母）；
  cache_guard             采集器 ask 主流程上 `if out["cached"]:` + `raise RuntimeError(` +
                          消息含「命中答案缓存」，块尾认「整 shard 停下重跑…（runbook §10 I-3）。」。

形状：坐标按**整块**落地（`<file>:<起>-<止>`，与读数本今天印的形状一致）—— 改的只有数字，
散文、括号、range 形状一枚字节都不动。

🔴 派生道只此一份：锚走 `scripts/r387_label_lineage.py` 的 `_one_hit`/`anchor_lines`/`_lines_of`
   （`rg -F` 语义：逐行 strip 之后连续固定串匹配；命中 0 枚＝锚已腐，≥2 枚＝不再是唯一锚），
   文档那一串字的坐标读法走 `scripts/r455_gapdoc_coordinates.py` 的 `_coordinate_token`/`_row_of`，
   异常与坐标字母表也取自那里。本件**一枚正则都没写**，r455／r387 的本体一个字没改。
   唯一一处加宽：读数本这些格是 `file:NNNN-NNNN` 形状，r455 那把尺只认单行 `file:NNNN`，
   `_token_at()` 先请它读数、它认不出时按**同一张字母表**（`gapdoc.COORD_CHARS`）切出 range，
   再用同一个 `str.isdigit()` 谓词逐段验数 —— 加宽的是切口的长度，不是第二把匹配器。

🔴 写错层另有牙：每枚锚带层判据 —— 起点固定串、块内必含的措辞（可给一组）、下一行的形状、
   往上读到的那枚函数。四枚里最阴的一形是本单补令亲自走过的那条：`_is_correct`／`pre_approval_ruler`
   里同样躺着 `total = len(results)` 这种「分母」字样，数字看着也对、层完全错（甲案那把尺的分母
   不是报告 dict 的总题数）；`inside_def` 专治它。同理拿「分子踩在了全部题数上」那枚 raise
   冒充分母读点、拿 `LATENCY_LEDGER_*` 常量冒充 unsupported_claim_rate 算法，各有一把咬得住。

🔴 在册 vs 冻结互斥（补令判据③）：同一枚坐标不许同时躺在 `READOUT_CITES`（跟着现读走）
   与 `FROZEN_CELLS`（当年现取、不许动）两张表里 —— `registered_conflicts()` 是独立的一把牙，
   它**不在** `frozen_missing()` 里面：摘掉冻结格守卫不会顺手把这条互斥也摘掉（那正是
   登记表互相打脸时最需要的读数）。规则只一条：**本笔按现读落地的坐标一枚都不留在冻结名单里**
   （留着＝两把尺对同一格各说各话）；本笔**不落地**的历史格逐枚留在名单里。名单今天现取 8 枚，
   枚数由 `FROZEN_CELLS` 与 `READOUT_CITES` 自己算（`test_no_live_coordinate_is_double_registered_as_history`
   与 `test_the_row_the_book_rewords_keeps_its_other_legs_frozen`），纸上不写死历史枚数。

🔴 等值那把尺有两条路，摘掉任一条都得有人喊（补令判据④点名的那枚盲区）：
   `read_cell` vs `derived_cells` 是「那一格此刻印的」与「按符号现读的」直接对撞，
   `compare()` 里那句 `if cell != want` 是账本自己出红清单走的那条路 —— 两条形似而实异。
   第一笔交回时自述过「常驻账件在等值守卫摘掉后仍绿」，那话当时**成立**：账件只走第一条路。
   今天第二条路另有牙：`tests/test_r460_run9_coordinates_are_derived.py` 里
   `test_the_compare_leg_arms_on_the_same_drift` 逐枚把漂移喂给 `compare()`，摘掉那句守卫
   （`gut_equality_off`）它当场红 5 枚 —— 盲区不再是一句自述，是一条能被复跑的红。

🔴 历史不追改（判据④）：这本账是 run9 收窗那一次的现读读数本，除五枚在册断言之外的坐标
   都是**当年现取**的历史，本件**不设** r455 那种「正文不许长出手抄坐标」的全域扫描（那会把
   整本历史一起喊红，等于逼下一班追改）。这里只设 `FROZEN_CELLS`：那几枚历史坐标被人顺手
   「统一改口」才红。诚实交代复验范围：八枚冻结登记里只有 :182 那一行右侧两枚短写坐标
   （`eval.py:67-73`／`:117-148`）本笔逐枚现取过、仍在原位；其余六枚**没有复验成判据**，
   本笔顺手看到的（09-28 现取，只作交代、不作担保）：`:21` 那枚 `eval.py:348-352` 今天躺着
   判据⑨的键名规则（最近秩 `rank=max(1,ceil(n*q))` 今天在第 628 行）、`:101`／`:250` 那两枚
   `transport:827-833`／`:803-831` 今天是批准恢复流的出口那几行、`:188` 那枚
   `transport:1139-1140` 今天是 terminal 读数记账（零字节置哨兵那一格今天在第 1251-1252 行）
   —— 这四枚也已漂；另两枚（`:60` 的 `retrieval_pipeline.py:224`、`:101` 的 `chat.py:1957`）
   本笔不判它对不对。它们都不在补令点名的两格里，按判据④原样留着：不替它们改口，也不冒充它们还对。

用法::

    python scripts/r460_run9_coordinates.py                  # 四枚锚的现读全貌 + 五格对账
    python scripts/r460_run9_coordinates.py --emit-doc-cells # 在册那几格的成品串
    python scripts/r460_run9_coordinates.py --check          # 等值 rc=0／锚腐 rc=3／漂了或改了历史 rc=4
    python scripts/r460_run9_coordinates.py --land           # 按现读机械重写那几格（只动坐标那一串字）
    python scripts/r460_run9_coordinates.py --bytes          # 判据⑤那六项字节体检（只读）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import r387_label_lineage as lineage  # noqa: E402  —— 锚：唯一那把匹配器
from scripts import r455_gapdoc_coordinates as gapdoc  # noqa: E402  —— 文档那一串字的读法

READOUT = "docs/testing/run9-readout-2026-09-28.md"
#: 红句里那条唯一的出路：重落地是跑量具，不是手改数字，也不是拿旧数加减行号。
EMIT_COMMAND = "python scripts/r460_run9_coordinates.py --emit-doc-cells"
#: 异常沿用 r455 那一族：不另立第二族红。
CoordinateUnavailable = gapdoc.CoordinateUnavailable
#: 坐标字母表同样沿用 r455：本件只把切口放宽到 range 形状。
COORD_CHARS = gapdoc.COORD_CHARS

#: 四枚锚（判据①）。锚块沿用 r387 那一族的结构：(目标行在块里的下标, 连续行原文)；键值里一枚行号都没有。
#:   start / end —— 块的起止行（end 缺省即单行块）；
#:   must_start / must_contain（可给一组）/ next_start / inside_def —— 层判据：落点必须在哪一层，说死在这一格。
RUN9_SITES: dict = {
    "eval_denominator": {
        "file": "app/quality/eval.py",
        "symbol": "evaluate_evaluation_set 那句判据 4「分母恒按全部题数算」",
        "start": (0, ["🔴 分母不因为甲案而变（判据 4）：`total` 与 `answer_correctness` 恒按全部题数算，"]),
        "end": (0, ["卡闸的题现在拿真终答进分母，旧口径要的那个数在 `pre_approval_ruler` 里。"]),
        "must_start": "🔴 分母不因为甲案而变",
        "must_contain": "恒按全部题数算",
        "inside_def": "def evaluate_evaluation_set(",
    },
    "report_denominator_code": {
        "file": "app/quality/eval.py",
        "symbol": "报告 dict 的 `total=len(rows)` 与 `answer_correctness=ratio(correct)` 那两行",
        "start": (0, ['"total": len(rows),']),
        "end": (0, ['"answer_correctness": ratio([item["correct"] for item in results]),']),
        "must_start": '"total": len(rows),',
        "must_contain": ('answer_correctness', 'ratio('),
        "inside_def": "def evaluate_evaluation_set(",
    },
    "unsupported_claim_rate": {
        "file": "app/quality/eval.py",
        "symbol": "报告里 unsupported_claim_rate 那一格（分子逐题读 provenance 的 unsupported_claims，分母 len(results)）",
        "start": (0, ['"unsupported_claim_rate": round(',
                      'sum(bool(item["provenance"]["unsupported_claims"]) for item in results)',
                      '/ len(results),',
                      '4,']),
        #: 终点锚给偏移 2：块尾要报的是那三行里的**最后一行**（`else 0.0,`），与被引的 7 行块同形。
        "end": (2, [")", "if results", "else 0.0,"]),
        "must_start": '"unsupported_claim_rate": round(',
        "must_contain": ('unsupported_claims', '/ len(results),'),
        "inside_def": "def evaluate_evaluation_set(",
    },
    "cache_guard": {
        "file": "scripts/eval_transport_ask_v2.py",
        "symbol": "采集器 ask 主流程上「命中答案缓存即 raise 停窗」那一格",
        "start": (0, ['if out["cached"]:',
                      "raise RuntimeError(",
                      'row_id + ": 命中答案缓存 ⇒ 开窗纪律破了（P-18 要求开窗前 flush Redis 的 answer:*）。"']),
        "end": (0, ['"整 shard 停下重跑，不许让假时延进 P95（runbook §10 I-3）。")']),
        "must_start": 'if out["cached"]:',
        "must_contain": "命中答案缓存",
        "next_start": "raise RuntimeError(",
        "inside_def": "def transport(row)",
    },
}

#: 读数本里今天还宣称「判据出处 / 算法 / 原话」的五枚行内引用（病灶点名的就是这五处）。
#: `row` 认那一行，`before` 认坐标左侧那一串 —— 两枚都是固定串，各须恰一枚命中，且都不含坐标。
#: 🔴 同一行允许多枚（:182 那行左中右三处，本笔落地其中两枚，另一枚按判据④留在冻结名单里）。
READOUT_CITES: tuple = (
    {"label": "C1 缓存命中", "key": "cache_guard",
     "row": "- C1 缓存命中：kind 含 cache 的计数=0（应为 0）；判据出处 ",
     "before": "判据出处 "},
    {"label": "hitl 分母恒=105", "key": "eval_denominator",
     "row": "- 没答完却占 correctness 分母（分母恒=105，见 ",
     "before": "分母恒=105，见 "},
    {"label": "C2 算法", "key": "unsupported_claim_rate",
     "row": "- C2 unsupported_claim_rate=0.0",
     "before": "算法 "},
    {"label": "分母口径·代码腿", "key": "report_denominator_code",
     "row": "- 🔴 correctness 分母的口径（不靠形容词）：",
     "before": "（不靠形容词）：`"},
    {"label": "分母口径·原话腿", "key": "eval_denominator",
     "row": "- 🔴 correctness 分母的口径（不靠形容词）：",
     "before": "分母恒为全部 105 题，`"},
)

#: 判据④：这些格子是当年现取的历史读数，一枚字节都不许跟着本单改口。
#: 🔴 规则：本笔按现读落地的三枚坐标（改口前分别印 `eval.py:471-477`／`:468-469`／`:401-402`）
#:    一枚都不留在名单里 —— 留着＝同一枚坐标两把尺各说各话（`registered_conflicts` 当场红）。
#: 🔴 :182 那一行右侧两枚短写坐标（`eval.py:67-73`＝`_is_correct`、`eval.py:117-148`＝
#:    `pre_approval_ruler`）本笔不落地，逐枚原样钉住：现读复核它们今天仍在原位 —— 改口就红。
FROZEN_CELLS: tuple = (
    {"label": "排名口径同规则", "row": "- 排名口径：最近秩", "cell": "app/quality/eval.py:348-352"},
    {"label": "P-15 日志点", "row": "- P-15 口径出处：", "cell": "app/rag/retrieval_pipeline.py:224"},
    {"label": "终端读数槽", "row": "- 出处：终端读数槽", "cell": "scripts/eval_transport_ask_v2.py:827-833"},
    {"label": "usage 交回", "row": "- 出处：终端读数槽", "cell": "app/api/v1/chat.py:1957"},
    #: 那一行右侧还有两枚**短写形式**的坐标（`eval.py:NNNN-NNNN`，不带目录前缀）：本笔不落地它们，
    #: 逐枚原样钉住。现读复核过：`:67-73` 仍是 `_is_correct`、`:117-148` 仍是 `pre_approval_ruler`。
    {"label": "分母口径·分子腿", "row": "- 🔴 correctness 分母的口径（不靠形容词）：",
     "cell": "eval.py:67-73"},
    {"label": "分母口径·甲案尺腿", "row": "- 🔴 correctness 分母的口径（不靠形容词）：",
     "cell": "eval.py:117-148"},
    {"label": "先扣哨兵", "row": "- 🔴 先扣哨兵：", "cell": "scripts/eval_transport_ask_v2.py:1139-1140"},
    {"label": "队列可读面", "row": "- **队列可读面层**", "cell": "scripts/eval_transport_ask_v2.py:803-831"},
)


def _rows(file: str, root: Path) -> list:
    """逐行 strip 过的被引文件 —— 走 r387 那枚缓存，不另起一份读法。"""
    return lineage._lines_of(root / file)


def enclosing_def(file: str, line: int, root: Path = ROOT) -> tuple:
    """落点往上第一枚**顶层** `def`/`async def`（顶格那一枚）：层判据用它证明「这一格站在哪一层」。

    🔴 为什么不能只看 strip 过的行：报告 dict 那几枚格（`total`／`answer_correctness`／
    `unsupported_claim_rate`）上方最近的一枚 def 是**函数体内**嵌套的 `def ratio(values):` ——
    按 strip 走就把顶层入口读成那枚 helper，正是一形「数没错、层读错了」。这里多读一次原文
    只为判缩进（顶格＝顶层），一枚行号都不从这里诞生：块与落点的行号全部出自 r387 那把锚。
    """
    body = (root / file).read_text(encoding="utf-8", errors="replace").splitlines()
    for index in range(line - 1, -1, -1):
        face = body[index]
        if face.startswith("def ") or face.startswith("async def "):
            return index + 1, face.rstrip()
    return 0, ""


def _cell(file: str, first: int, last: int) -> str:
    return "%s:%d-%d" % (file, first, last) if last != first else "%s:%d" % (file, first)


def resolve_site(key: str, root: Path = ROOT, sites: dict | None = None) -> dict:
    """把一枚锚解成「文件 + 块的起止行 + 落点原文」。读不出／不唯一／落错层都抛。"""
    spec = (sites or RUN9_SITES)[key]
    file = spec["file"]
    try:
        first = lineage._one_hit(key + " 起点", file, spec["start"], root)
        last = first if spec.get("end") is None else lineage._one_hit(key + " 终点", file, spec["end"], root)
    except lineage.AnchorNotUnique as exc:
        raise CoordinateUnavailable(str(exc)) from exc
    if last < first:
        raise CoordinateUnavailable("%s：终点锚（%d）落到起点锚（%d）之前，块不成立" % (key, last, first))
    rows = _rows(file, root)
    face = rows[first - 1]
    block = "\n".join(rows[first - 1:last])
    must_start = spec.get("must_start")
    if must_start and not face.startswith(must_start):
        raise CoordinateUnavailable("现读落在第 %d 行 %r，那不是「%s」所在的一层（要的是以 %r 起头的那一行）"
                                    " —— 写错层" % (first, face, spec["symbol"], must_start))
    contain = spec.get("must_contain")
    for want in ([contain] if isinstance(contain, str) else list(contain or ())):
        if want not in block:
            raise CoordinateUnavailable("第 %d-%d 行里读不出 %r —— 这不是「%s」那一格，写错层"
                                        % (first, last, want, spec["symbol"]))
    nxt = spec.get("next_start")
    if nxt and not (len(rows) > first and rows[first].startswith(nxt)):
        raise CoordinateUnavailable("第 %d 行 %r 下面那行是 %r，%r 读不出来 —— 这一格引的不是那道闸"
                                    % (first, face, rows[first] if len(rows) > first else "<文件尽头>", nxt))
    inside = spec.get("inside_def")
    if inside:
        def_line, def_face = enclosing_def(file, first, root)
        if not def_face.startswith(inside):
            raise CoordinateUnavailable("第 %d 行往上读到的函数是第 %d 行 %r，不是 %r —— 「%s」这一格"
                                        "引错了层：写错层" % (first, def_line, def_face, inside, spec["symbol"]))
    return {"key": key, "file": file, "symbol": spec["symbol"], "block": (first, last),
            "line": first, "face": face, "cell": _cell(file, first, last)}


def derived_cells(root: Path = ROOT, sites: dict | None = None) -> tuple:
    """现读四枚锚 -> (渲染好的那一格, 失败清单)。失败不抛：让判据红在具名那一格（照 r387 规矩）。"""
    cells, failures = {}, []
    for key in (sites or RUN9_SITES):
        try:
            cells[key] = resolve_site(key, root, sites)["cell"]
        except CoordinateUnavailable as exc:
            failures.append("%s：%s" % (key, exc))
    return cells, failures


def readings(root: Path = ROOT, sites: dict | None = None) -> list:
    """四枚锚的现场全貌（含块的起止与落点原文），给人也给出账用。"""
    return [resolve_site(key, root, sites) for key in (sites or RUN9_SITES)]


def readout_text(root: Path = ROOT, rel: str = READOUT) -> str:
    return (root / rel).read_bytes().decode("utf-8")


def _token_at(tail: str) -> str:
    """先请 r455 那把尺读数（单行形状）；它认不出时，按同一张字母表切出 range 那一串并逐段验数。"""
    token = gapdoc._coordinate_token(tail)
    if token:
        return token
    taken = 0
    while taken < len(tail) and tail[taken] in COORD_CHARS:
        taken += 1
    raw = tail[:taken]
    head, sep, digits = raw.rpartition(":")
    if not (sep and head):
        return ""
    start, dash, stop = digits.partition("-")
    return raw if (dash and start.isdigit() and stop.isdigit()) else ""


def read_cell(text: str, cite: dict) -> str:
    """端出读数本那一格**此刻印着**的坐标串（逐字节，不含包裹它的反引号）。"""
    try:
        _index, row = gapdoc._row_of(text, cite["row"], cite["label"])
    except gapdoc.CoordinateUnavailable as exc:
        raise CoordinateUnavailable("读数本那一格定位不到（%s）：%s" % (cite["label"], exc)) from exc
    if row.count(cite["before"]) != 1:
        raise CoordinateUnavailable("%s：锚 %r 在那一行里出现 %d 次，读不出唯一那一格"
                                    % (cite["label"], cite["before"], row.count(cite["before"])))
    token = _token_at(row.split(cite["before"], 1)[1])
    if not token:
        raise CoordinateUnavailable("%s：锚 %r 后面读不出一格坐标 —— 那一串字的形状被人改过"
                                    % (cite["label"], cite["before"]))
    return token


def land_cells(text: str, cells: dict) -> str:
    """把现读的那几枚坐标写回读数本：只动坐标那一串字，前后各一个字节都不碰。

    这枚函数存在的意义就是「重落地是机械动作」—— 下一班既不必手改数字，也不必做行号算术。
    同一行多枚格按登记顺序逐枚改写：行锚不含坐标，落完一枚后其余各枚照样读得出唯一那一格。
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = text.split(newline)
    for cite in READOUT_CITES:
        want = cells.get(cite["key"])
        if want is None:
            continue
        hits = [index for index, row in enumerate(rows) if cite["row"] in row]
        if len(hits) != 1:
            raise CoordinateUnavailable("重落地时定位不到 %s：%r 命中 %d 枚"
                                        % (cite["label"], cite["row"], len(hits)))
        row = rows[hits[0]]
        at = row.find(cite["before"])
        if at < 0:
            raise CoordinateUnavailable("重落地时读不到 %s 那一格的锚 %r" % (cite["label"], cite["before"]))
        cut = at + len(cite["before"])
        token = _token_at(row[cut:])
        if not token:
            raise CoordinateUnavailable("重落地时读不到 %s 那一格的坐标" % cite["label"])
        rows[hits[0]] = row[:cut] + want + row[cut + len(token):]
    return newline.join(rows)


def frozen_missing(text: str) -> list:
    """判据④的牙：历史格子里那几枚当年现取的坐标被人「统一改口」时点名。缺谁红谁。"""
    red: list = []
    rows = text.splitlines()
    for item in FROZEN_CELLS:
        hits = [index for index, row in enumerate(rows) if item["row"] in row]
        if len(hits) != 1:
            red.append("历史格子 %s 的行锚 %r 命中 %d 枚（要恰一枚）—— 那一行被人改过形状"
                       % (item["label"], item["row"], len(hits)))
            continue
        if rows[hits[0]].count(item["cell"]) < 1:
            red.append("历史格子 %s 里那枚当年现取的 `%s` 不见了 ⇒ 判据④不许追改历史读数："
                       "本单只搬在册那几枚坐标，其余原样留着" % (item["label"], item["cell"]))
    return red


def registered_conflicts(text: str, cells: dict) -> list:
    """补令判据③的牙：同一枚坐标同时躺在「跟现读走」与「不许动」两张表里 —— 两把尺自相矛盾。

    🔴 这把牙**不在** `frozen_missing()` 里面：摘掉冻结格守卫不会顺手把互斥也摘掉（那正是
    登记表互相打脸时最需要的读数）。判两形：冻结名单里的串等于某一枚在册现读，或等于某一枚
    在册格此刻印着的串 —— 前形是「本笔要落地的数被人登记成历史」，后形是「历史登记占住了活口」。
    """
    live = {cells.get(item["key"]) for item in READOUT_CITES} - {None}
    slots = set()
    for item in READOUT_CITES:
        try:
            slots.add(read_cell(text, item))
        except CoordinateUnavailable:
            continue
    red: list = []
    for entry in FROZEN_CELLS:
        where = []
        if entry["cell"] in live:
            where.append("等于某一枚在册现读")
        if entry["cell"] in slots:
            where.append("等于某一枚在册格此刻印的数")
        if where:
            red.append("冻结名单里的 %s（`%s`，行锚 %r）同时是在册断言的落点：%s ⇒ 两把尺对同一枚"
                       "坐标各说各话（判据③）—— 要么跟着现读走（从 FROZEN_CELLS 摘掉登记），"
                       "要么留在历史里（从 READOUT_CITES 摘掉那一枚格）"
                       % (entry["label"], entry["cell"], entry["row"], "、".join(where)))
    return red


def byte_footprint(raw: bytes) -> dict:
    """判据⑤那六项：size / CRLF / 裸 LF / 孤独 CR / U+FFFD / 文件尾有无 newline（只读现取）。"""
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    cr = raw.count(b"\r")
    return {"size": len(raw), "crlf": crlf, "bare_lf": lf - crlf, "lone_cr": cr - crlf,
            "replacement_char": raw.decode("utf-8", "replace").count("\ufffd"),
            "trailing_newline": raw.endswith(b"\n")}


def compare(root: Path = ROOT, sites: dict | None = None, text: str | None = None) -> dict:
    """把「读数本那一格」与「按符号现读」逐枚对撞，端出读数与红清单。

    红清单为空才算这本账今天说得出现场。漂了一格的红句只指一条路：跑 `--emit-doc-cells` 重落地。
    """
    cells, failures = derived_cells(root, sites)
    body = readout_text(root) if text is None else text
    covered = {item["key"] for item in READOUT_CITES}
    red: list = ["锚读不出来，先修锚再谈落地：" + item for item in failures
                 if item.partition("：")[0] not in covered]
    broken = {item.partition("：")[0]: item for item in failures}
    matched: list = []
    printed: dict = {}
    for cite in READOUT_CITES:
        want = cells.get(cite["key"])
        try:
            cell = read_cell(body, cite)
        except CoordinateUnavailable as exc:
            red.append("%s：%s" % (cite["label"], exc))
            continue
        printed[cite["label"]] = cell
        if want is None:
            red.append("%s（锚 %s）：现读这一步就断了，先修锚再谈落地，别顺手去改那一格的数字 —— %s（跑 `%s`）"
                       % (cite["label"], cite["key"], broken.get(cite["key"], "锚读不出来"), EMIT_COMMAND))
            continue
        if cell != want:
            red.append("%s（锚 %s）：那一格印 %s、按符号现读 %s ⇒ 这一格只有一条路：跑 `%s` 重落地，"
                       "不许手改数字，也不许拿旧数加减行号"
                       % (cite["label"], cite["key"], cell, want, EMIT_COMMAND))
        else:
            matched.append("%s=%s" % (cite["label"], cell))
    red.extend(frozen_missing(body))
    red.extend(registered_conflicts(body, cells))
    return {"cells": cells, "matched": matched, "red": red, "failures": failures, "printed": printed}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R460 读数本后端坐标派生（默认只读，--land 才动那一串字）")
    parser.add_argument("--emit-doc-cells", action="store_true",
                        help="把在册那几格的成品串按「锚名<TAB>格」打出来（行号是派生的，表不许手改）")
    parser.add_argument("--check", action="store_true",
                        help="那一格 vs 按符号现读：等值 rc=0；锚腐 rc=3；漂了或改了历史或多登记 rc=4")
    parser.add_argument("--land", action="store_true", help="按现读机械重写那几格（锚腐时拒写）")
    parser.add_argument("--bytes", action="store_true", help="判据⑤那六项字节体检（只读）")
    parser.add_argument("--json", dest="out", default="", help="把全貌写成 JSON 文件（只写点名那一枚）")
    args = parser.parse_args(argv)

    cells, failures = derived_cells()
    if args.out:
        Path(args.out).write_text(json.dumps({"cells": cells, "failures": failures, "readings": readings()},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
    if args.bytes:
        print(json.dumps(byte_footprint((ROOT / READOUT).read_bytes()), ensure_ascii=False, sort_keys=True))
        return 3 if failures else 0
    if args.emit_doc_cells:
        for key in RUN9_SITES:
            print("%s\t%s" % (key, cells.get(key, "<锚失效:%s>" % key)))
        for item in failures:
            print("ABORT: 锚不再是唯一锚 -> " + item, file=sys.stderr)
        return 3 if failures else 0

    body = readout_text()
    if args.land:
        if failures:
            print("ABORT: 锚读不出来，拒绝落地：" + "；".join(failures), file=sys.stderr)
            return 3
        landed = land_cells(body, cells)
        if landed == body:
            print("那几格已经是现读，一枚字节都不必动：" + json.dumps(cells, ensure_ascii=False))
        else:
            (ROOT / READOUT).write_bytes(landed.encode("utf-8"))
            print("已按现读机械重写那几格（只动坐标那一串字）：" + json.dumps(cells, ensure_ascii=False))
        body = readout_text()
    report = compare(text=body)
    for key in RUN9_SITES:
        print("%-25s 现读 %-46s %s" % (key, cells.get(key, "<锚失效>"), RUN9_SITES[key]["symbol"]))
    for cite in READOUT_CITES:
        print("%-25s 那一格此刻印着 %s" % (cite["label"], report["printed"].get(cite["label"], "<读不出>")))
    if args.check:
        for item in report["red"]:
            print("RED: " + item, file=sys.stderr)
        return 3 if failures else (0 if not report["red"] else 4)
    print("matched: " + json.dumps(report["matched"], ensure_ascii=False))
    print("red: " + json.dumps(report["red"], ensure_ascii=False))
    return 3 if failures else (0 if not report["red"] else 4)


if __name__ == "__main__":
    sys.exit(main())
