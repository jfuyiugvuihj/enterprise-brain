# -*- coding: utf-8 -*-
"""R460 · 常驻账件：run9 读数本那五枚「判据出处」后端坐标只许是**符号派生**的读数（补令后四枚锚）。

病灶（工单 R460 + R460 补令，基点 `49555eb`）：`docs/testing/run9-readout-2026-09-28.md` 里
:105／:107／:115／:182（两枚）五处行内引用抄的全是后端行号，并树把文件撑长之后一枚枚打漂，
而没有任何一枚门喊过。本件不再抄第二遍：量具 `scripts/r460_run9_coordinates.py` 按符号现读，
本件把「文档那一格 == 现读」逐枚钉死，另配四族牙 —— 口径不许动、历史不许追改、在册与冻结
互斥、量具自己不许长出第二把尺。

本件钉什么：
  ① 四枚锚在干净树上逐枚唯一命中，落点各在自己那一层（三枚 eval.py 的格必须读在
     `evaluate_evaluation_set` 那一层，不能被函数体内嵌套的 `def ratio(values):` 顶掉；
     缓存那枚必须读在 `def transport(row)` 里、下一行是 `raise RuntimeError(`、消息含
     「命中答案缓存」）；
  ② 五枚行内引用与派生读数**逐字节等值**（判据①那句等值要求就钉在这里），且 `compare()`
     那条路自己也必须会在漂移上喊 —— 🔴 补令判据④点名的那枚盲区在这里合口：本件最后一节
     有一枚「拿漂移的书喂 compare()」的用例，它不依赖逐枚等值那把独立的尺，摘掉 compare 的
     等值守卫它就红；
  ③ 口径一字不许动：坐标两侧那句话逐句回读；
  ④ 历史不追改：其余当年现取的格子原样在册（含 :182 那行右侧两枚短写坐标），
     `:21`／`:101`／`:188`／`:250` 那几枚本笔未落地、也**未复验成判据**（量具的模块 docstring
     里 09-28 现取顺手看到的四枚也已漂，只作交代），本件只钉「不许改口」，不替它们担保今天还对；
  ⑤ 同一枚坐标不许同时躺在在册表与冻结表里（补令判据③），且那把互斥的牙不在
     `frozen_missing()` 里面 —— 摘掉冻结格守卫不会顺手把互斥也摘掉；
  ⑥ 量具自己不许夹带抄来的行号、不许另起第二把匹配器，r455／r387 的本体一个字没动。

🔴 效力边界：本件只读源码文本与文档字节，不写生产码、不起服务、不连库、不打模型；变异一律落在
   tmp 影子树、进程内锚表或内存字符串上（`tests/test_r253_no_test_rewrites_a_tracked_file.py` 盯这一形）。
   它证的是「读数本那些格指的坐标与现场同序、手抄进不了这本账」，不证 run9 那轮读数本身对不对。
🔴 摘守卫的门：环境变量 `R460_RUN9_TOOL` 指到一枚改过的量具副本，本件与两枚牙件都从那里加载。
   这不是豁免名单 —— 它是「摘掉哪一把牙、红几枚」能被复跑的那条路。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "读不到量具：" + str(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOL_PATH = Path(os.getenv("R460_RUN9_TOOL") or (REPO / "scripts" / "r460_run9_coordinates.py"))
TOOL = _load(TOOL_PATH, "r460_run9_coordinates")

TOOL_REL = "scripts/r460_run9_coordinates.py"
R387_REL = "scripts/r387_label_lineage.py"
R455_REL = "scripts/r455_gapdoc_coordinates.py"
READOUT_REL = TOOL.READOUT
EVAL = TOOL.RUN9_SITES["eval_denominator"]["file"]
TRANSPORT = TOOL.RUN9_SITES["cache_guard"]["file"]
SITE_KEYS = tuple(TOOL.RUN9_SITES)
LIVE_LABELS = tuple(item["label"] for item in TOOL.READOUT_CITES)
#: 读数本落地那一笔（run9 收窗）。这是一枚**提交名**，不是行号：本件用它只问「同一截码在不在」，
#: 从不问「它在第几行」—— 那一问的答案由锚现读给出。
RUN9_MERGE = "2154318"
#: 🔴 本单落地**之前**那一版的基点。旧抄数必须从这里现取，不许从 `HEAD` 取：`HEAD` 会随并树前移，
#: 而并树之后的 `HEAD` 里那本已经写着改后的坐标 —— 拿它当「改前」，本件就在自己落地那一刻自毁
#: （09-28 全量门实测 11 枚红就是这么来的，事故 #77：施工态与并树前的复跑都读不到这一红，因为那时
#: `HEAD` 恰好还是基点，前提成立；前提一过期，红的不是产品，是这枚件选错了落脚点）。
PRE_LANDING_REV = "49555eb"
#: 影子树里插的那一行：它只活在 tmp_path 里，盘上那一棵一个字没动。
PAD_LINE = ""


def readout_text(root: Path = REPO) -> str:
    return TOOL.readout_text(root)


def tool_text() -> str:
    return (REPO / TOOL_REL).read_bytes().decode("utf-8")


def derived(root: Path = REPO, sites: dict | None = None) -> dict:
    cells, failures = TOOL.derived_cells(root, sites)
    assert not failures, "锚读不出来，先修锚再谈落地：" + "；".join(failures)
    return cells


def cite(label: str) -> dict:
    return next(item for item in TOOL.READOUT_CITES if item["label"] == label)


def row_of(text: str, needle: str) -> str:
    hits = [row for row in text.splitlines() if needle in row]
    assert len(hits) == 1, "行锚 %r 命中 %d 枚（要恰一枚）" % (needle, len(hits))
    return hits[0]


def block_of(key: str, root: Path = REPO) -> str:
    """现读那一块的原文（strip 过，逐行）—— 语义判据都读它，不读行号。"""
    read = TOOL.resolve_site(key, root)
    first, last = read["block"]
    return "\n".join(TOOL._rows(read["file"], root)[first - 1:last])


def numbers(cell: str) -> tuple:
    tail = cell.rpartition(":")[2]
    first, dash, last = tail.partition("-")
    return (int(first), int(first)) if not dash else (int(first), int(last))


def mutate_cell(text: str, label: str, cell: str) -> str:
    """在内存里把某一枚行内引用的坐标换成另一串字：盘上那本读数一个字不动。"""
    item = cite(label)
    rows = text.split("\r\n")
    hits = [index for index, row in enumerate(rows) if item["row"] in row]
    assert len(hits) == 1, label + " 的行锚命中 " + str(len(hits)) + " 枚"
    row = rows[hits[0]]
    at = row.find(item["before"])
    assert at >= 0, label + " 的坐标左锚读不到了"
    cut = at + len(item["before"])
    token = TOOL._token_at(row[cut:])
    assert token, label + " 那一格读不出坐标"
    rows[hits[0]] = row[:cut] + cell + rows[hits[0]][cut + len(token):]
    return "\r\n".join(rows)


def shift(cell: str, step: int = 1) -> str:
    head, _sep, tail = cell.rpartition(":")
    first, dash, last = tail.partition("-")
    return head + ":" + str(int(first) + step) + (dash + str(int(last) + step) if dash else "")


def shadow_root(tmp_path: Path, pad_eval: int = 0, pad_transport: int = 0,
                doc_text: str | None = None) -> Path:
    """把被引的两枚后端文件按字节搬进 tmp 再叠变异：这是 R253 之后唯一允许的变异形状。"""
    root = tmp_path / "shadow"
    for rel, pad in ((EVAL, pad_eval), (TRANSPORT, pad_transport)):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        body = (REPO / rel).read_bytes().decode("utf-8")
        if pad:
            body = (PAD_LINE + "\r\n") * pad + body
        target.write_bytes(body.encode("utf-8"))
    doc = root / READOUT_REL
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_bytes((readout_text() if doc_text is None else doc_text).encode("utf-8"))
    return root


def masked(text: str, placeholder: str = "<MASK>") -> str:
    """把每一枚在册坐标换成占位符：剩下的每一枚字节都得与另一版逐字节相同（判据⑤的具像）。

    🔴 先逐枚读数、再一次性替换：同一行上挂着多枚格时，替换会连行锚一起吃掉（行锚是那一格的左邻），
    边读边换就读不出后面那枚 —— 读与写分成两段，这一枚才既是账也是自证。
    """
    needles = []
    for item in TOOL.READOUT_CITES:
        needle = item["before"] + TOOL.read_cell(text, item)
        assert text.count(needle) == 1, needle
        needles.append(needle)
    body = text
    for needle in needles:
        assert body.count(needle) == 1, needle
        body = body.replace(needle, placeholder)
    return body



# ------------------------------------------------------------------ ① 锚与层


def test_the_four_anchors_hit_exactly_once_on_the_pristine_tree() -> None:
    """四枚锚逐枚唯一命中：命中 0 枚＝锚已腐，≥2 枚＝不再是唯一锚（取第一次就是猜）。"""
    cells, failures = TOOL.derived_cells(REPO)
    assert not failures, str(failures)
    assert tuple(cells) == SITE_KEYS and len(SITE_KEYS) == 4, str(cells)
    for key in SITE_KEYS:
        spec = TOOL.RUN9_SITES[key]
        cell = cells[key]
        assert cell.startswith(spec["file"] + ":"), key + " 那一格的形状不对：" + cell
        first, last = numbers(cell)
        assert first > 0 and last >= first, key + " 那一格读不出行号区间：" + cell


def test_the_bare_cache_line_is_not_a_unique_anchor() -> None:
    """`if out["cached"]:` 单行在采集器里命中两枚（ask 主流程与 `/approve` 恢复流）：
    所以本件的锚必须是**连续块**，手抄的人只抄一行就必然抄错层 —— 这正是 :105 那一格的病。"""
    hits = TOOL.lineage.anchor_lines(TRANSPORT, (0, ['if out["cached"]:']), REPO)
    assert len(hits) == 2, "单行锚的命中数今天变了，本件那句断言要跟着现读：" + str(hits)
    assert len(TOOL.lineage.anchor_lines(TRANSPORT, TOOL.RUN9_SITES["cache_guard"]["start"], REPO)) == 1


def test_the_denominator_anchor_lands_on_the_ruler_4_line_inside_the_entry_point() -> None:
    """判据①第一枚锚：那句「分母恒按全部题数算」必须在 `evaluate_evaluation_set` 的 docstring 里。"""
    read = TOOL.resolve_site("eval_denominator", REPO)
    assert read["face"].startswith("🔴 分母不因为甲案而变"), read["face"]
    assert "恒按全部题数算" in read["face"], read["face"]
    assert "拿真终答进分母" in block_of("eval_denominator"), "块尾那半句读不出来"
    def_line, def_face = TOOL.enclosing_def(EVAL, read["line"], REPO)
    assert def_face.startswith("def evaluate_evaluation_set("), "落点不在那枚入口函数里：" + str((def_line, def_face))


def test_the_report_denominator_cell_is_the_two_lines_the_book_quotes() -> None:
    """补令判据②：:182 左格写的是「`total=len(rows)`、`answer_correctness=ratio(correct)`」——
    现读那块必须逐字把这两行端出来，而不是另挑一枚看着像分母的数。"""
    block = block_of("report_denominator_code")
    assert '"total": len(rows),' in block, block
    assert '"answer_correctness": ratio([item["correct"] for item in results]),' in block, block
    def_line, def_face = TOOL.enclosing_def(EVAL, TOOL.resolve_site("report_denominator_code", REPO)["line"], REPO)
    assert def_face.startswith("def evaluate_evaluation_set("), str((def_line, def_face))


def test_the_unsupported_claim_cell_is_the_rate_algorithm_not_the_latency_constants() -> None:
    """🔴 补令判据②那问「反向结论」的路：:107 那格措辞若其实指时延那一族，原引就该判不错。

    现读判决：不是。那一格写的是「unsupported_claim_rate 键；算法」，而
      · 现读那块里同时读得出分子 `unsupported_claims` 与分母 `/ len(results),` ⇒ 它就是那把率；
      · 而被引过的那几行今天躺着 `LATENCY_LEDGER_RATIO_TOLERANCE`／`LATENCY_LEDGER_SLACK_MS`
        —— 时延容忍带常量，读不出这个键名、也读不出任何分母。
    所以「照语义落在原位、宣布原引不错」这一支在现读面前不成立，本笔据实改口。
    """
    block = block_of("unsupported_claim_rate")
    assert '"unsupported_claim_rate": round(' in block, block
    assert "unsupported_claims" in block and "/ len(results)," in block, block
    cited = "\n".join(TOOL._rows(EVAL, REPO)[470:477])
    assert "unsupported_claim_rate" not in cited, "那一族今天还在那几行上：本笔就不该改口"
    assert "LATENCY_LEDGER" in cited, cited
    assert "LATENCY_LEDGER" not in block, block


def test_the_cache_anchor_lands_on_the_ask_path_guard_not_the_approve_one() -> None:
    """判据①第二枚锚：那枚 raise 必须是 ask 主流程上「命中答案缓存」那一格，不是 `/approve` 那格。"""
    read = TOOL.resolve_site("cache_guard", REPO)
    assert read["face"].startswith('if out["cached"]:'), read["face"]
    rows = TOOL._rows(TRANSPORT, REPO)
    assert rows[read["line"]].startswith("raise RuntimeError("), rows[read["line"]]
    block = block_of("cache_guard")
    assert "命中答案缓存" in block and "/approve 之后出现缓存命中" not in block, block
    def_line, def_face = TOOL.enclosing_def(TRANSPORT, read["line"], REPO)
    assert def_face.startswith("def transport(row)"), "落点不在 transport 那一层：" + str((def_line, def_face))


def test_a_nested_helper_def_does_not_masquerade_as_the_entry_point() -> None:
    """🔴 补令现读的坑（本件把它钉成牙）：报告 dict 上方最近的一枚 def 是**函数体内**嵌套的
    `def ratio(values):`。层判据若只看 strip 过的行，就会把顶层入口读成那枚 helper —— 数没错、
    层读错。`enclosing_def` 只认顶格那一枚，本件两头都验。"""
    read = TOOL.resolve_site("report_denominator_code", REPO)
    stripped = TOOL._rows(EVAL, REPO)
    naive = next(stripped[index] for index in range(read["line"] - 1, -1, -1)
                 if stripped[index].startswith("def "))
    assert naive.startswith("def ratio(values):"), "嵌套那枚今天不在这儿了，本件的这行断言要跟着现读：" + naive
    def_line, def_face = TOOL.enclosing_def(EVAL, read["line"], REPO)
    assert def_face.startswith("def evaluate_evaluation_set("), "层判据被嵌套 helper 顶掉了：" + str((def_line, def_face))


# ------------------------------------------------------------------ ② 逐字节等值（两条路）


def test_the_marker_registry_locates_every_live_cite_uniquely() -> None:
    """五枚行内引用的锚（行锚 + 坐标左锚）各须恰一枚命中：锚腐了要先知道，不许读成旧数。"""
    text = readout_text()
    assert len(LIVE_LABELS) == len(TOOL.READOUT_CITES) == 5, "行内引用比病灶点名的少：" + str(len(LIVE_LABELS))
    assert len(set(LIVE_LABELS)) == len(LIVE_LABELS), "两枚格同名，红清单会互相顶包：" + str(LIVE_LABELS)
    for item in TOOL.READOUT_CITES:
        assert text.count(item["row"]) == 1, item["label"] + " 的行锚命中 " + str(text.count(item["row"])) + " 枚"
        assert row_of(text, item["row"]).count(item["before"]) == 1, item["label"] + " 的坐标左锚不唯一"


@pytest.mark.parametrize("item", TOOL.READOUT_CITES, ids=lambda item: item["label"])
def test_every_live_coordinate_cell_in_the_readout_equals_the_derived_reading(item: dict) -> None:
    """🔴 判据①那句「逐字节等值」（第一条路：那一格此刻印的 vs 按符号现读的，一枚都不许多不许少）。"""
    printed = TOOL.read_cell(readout_text(), item)
    want = derived()[item["key"]]
    assert printed == want, (
        item["label"] + "（锚 " + item["key"] + "）：那一格印 " + printed + "、按符号现读 " + want
        + " ⇒ 这一格只有一条路：跑 `" + TOOL.EMIT_COMMAND + "` 重落地，不许手改数字，也不许拿旧数加减行号")


@pytest.mark.parametrize("label", LIVE_LABELS)
def test_the_compare_leg_arms_on_the_same_drift(label: str) -> None:
    """🔴 补令判据④点名的那枚盲区，在这里合口：漂移喂给 `compare()` 那条路也必须喊。

    第一笔交回时自述过一句「常驻账件在等值守卫摘掉后仍绿」—— 那时本件只走 `read_cell` vs
    `derived_cells` 这条独立路。今天这条用例改走 `compare()`：摘掉 compare 的等值守卫，
    这一枚立刻红（`gut_equality_off` 实测已复跑）。
    """
    drifted = mutate_cell(readout_text(), label, shift(derived()[cite(label)["key"]], 1))
    assert TOOL.read_cell(drifted, cite(label)) != derived()[cite(label)["key"]], "第一条路没看见漂移"
    report = TOOL.compare(root=REPO, text=drifted)
    red = [item for item in report["red"] if label in item]
    assert len(red) == 1, "compare 那条路对同一枚漂移一声不吭：" + str(report["red"])
    assert TOOL.EMIT_COMMAND in red[0] and "不许手改数字" in red[0], red[0]


def test_the_book_is_green_today() -> None:
    """整本对账：现读、等值（两条路）、历史、互斥四族同时为空红 —— 本笔交付态的总闸。"""
    text = readout_text()
    report = TOOL.compare(root=REPO, text=text)
    assert report["red"] == [], str(report["red"])
    assert len(report["matched"]) == len(TOOL.READOUT_CITES), str(report["matched"])
    assert report["failures"] == [], str(report["failures"])
    assert TOOL.registered_conflicts(text, report["cells"]) == [], "在册与冻结互斥那条路红了"


# ------------------------------------------------------------------ ③ 口径


def test_the_caliber_around_the_coordinates_says_what_run9_said() -> None:
    """🔴 口径一字不许动：本笔只搬坐标，那几格讲的事实必须原样躺在同一行里。"""
    text = readout_text()
    assert "kind 含 cache 的计数=0（应为 0）" in row_of(text, "- C1 缓存命中：kind 含 cache 的计数=0")
    assert "（命中即 raise 停窗，正常读数就是「一份都不存在」）" in row_of(text, "- C1 缓存命中：kind 含 cache")
    c2 = row_of(text, "- C2 unsupported_claim_rate=0.0")
    assert "C2 unsupported_claim_rate=0.0（评分件 evaluation-report-run9.json 的 unsupported_claim_rate 键；" in c2, c2
    hitl = row_of(text, "- 没答完却占 correctness 分母（分母恒=105，见 ")
    for phrase in ("分母恒=105", "sentinel=True 0 题 + kind 属未答完族 2 题",
                   "并集 2/105 题号=['metric-02', 'scope-02']"):
        assert phrase in hitl, phrase + " 不在那一格里：" + hitl
    mouth = row_of(text, "- 🔴 correctness 分母的口径（不靠形容词）：")
    for phrase in ("的 `total=len(rows)`、`answer_correctness=ratio(correct)` 分母恒为全部 105 题",
                   "原话「分母不因为甲案而变：卡闸的题现在拿真终答进分母」",
                   "**没有任何一枚 kind 被从分母里剔除**",
                   "只能判错不能判对"):
        assert phrase in mouth, phrase + " 不在那一格里：" + mouth




# ------------------------------------------------------------------ ④ 历史不追改
#
# 这一节只干一件事：说清「漂」是怎么发生的 —— 当年现取的坐标与同一截码在那一笔里的行号
# 逐枚对得上，是后续并树把文件撑长把它打漂的。对得上的凭据走 `git`，不靠任何人记忆。


def blob_at(rev: str, rel: str) -> str:
    out = subprocess.run(["git", "show", rev + ":" + rel], cwd=str(REPO), capture_output=True)
    assert out.returncode == 0, rev + ":" + rel + " 取不出来 —— " + out.stderr.decode("utf-8", "replace")
    return out.stdout.decode("utf-8")


def pre_landing_book() -> str:
    """本单落地**之前**那一版的读数本：旧抄数从这里现取，本件不手打，也不问 `HEAD`。

    🔴 `git show` 端出来的是 blob（LF 切口），工作树那本是 CRLF：这里只把切口对齐成工作树的形状，
    行数与每一行的字节都不受影响 —— 判据⑤那笔字节账读的是这本 CRLF 的。
    """
    return blob_at(PRE_LANDING_REV, READOUT_REL).replace("\r\n", "\n").replace("\n", "\r\n")


def printed_before_landing(label: str) -> str:
    return TOOL.read_cell(pre_landing_book(), cite(label))


def test_the_run9_window_merge_is_a_real_commit_on_this_tree() -> None:
    """`2154318` 是 run9 收窗那一笔，且已在这棵树上：历史对照的落脚点本身要先在册。"""
    kind = subprocess.run(["git", "cat-file", "-t", RUN9_MERGE], cwd=str(REPO), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    assert kind.returncode == 0 and kind.stdout.strip() == "commit", kind.stdout + kind.stderr
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", RUN9_MERGE, "HEAD"],
                              cwd=str(REPO), capture_output=True, text=True, errors="replace")
    assert ancestor.returncode == 0, RUN9_MERGE + " 不在本树的祖先里：" + ancestor.stderr


def test_the_pre_landing_book_is_pinned_and_is_not_the_head_book() -> None:
    """🔴 这枚牙钉的是「对照本的落脚点」本身：基点必须在祖先链上，且那一本必须与 `HEAD` 那本不同。

    为什么要有这一枚：上一版把「改前」写成 `HEAD`，于是它只在自己未落地时成立 —— 并树那一刻 `HEAD`
    前移，「改前」与「改后」变成同一本，判据④⑤ 与那枚互斥钉一起自毁（门实测 11 枚红）。这一枚把那个
    前提变成可失败的断言：谁再把落脚点挪回 `HEAD`，或者这一格哪天被回退成同一本，当场红。
    """
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", PRE_LANDING_REV, "HEAD"],
                              cwd=str(REPO), capture_output=True, text=True, errors="replace")
    assert ancestor.returncode == 0, PRE_LANDING_REV + " 不在本树的祖先里：" + ancestor.stderr
    assert blob_at(PRE_LANDING_REV, READOUT_REL) != blob_at("HEAD", READOUT_REL), (
        "「改前」那一本与 HEAD 那一本逐字节相同 —— 落脚点已经跟着并树前移了，"
        "拿它当改前就是让本件在落地那一刻自毁（事故 #77）"
    )


@pytest.mark.parametrize("key", SITE_KEYS)
def test_each_anchor_block_is_the_same_code_the_run9_merge_carried(key: str, tmp_path: Path) -> None:
    """🔴 判据④的凭据：同一枚锚在 `2154318` 那两枚后端文件里读得出，行号正等于当年手抄的那个数，
    块内逐字与今天相同，而今天它已不在那几行上 —— 「当初没抄错、是并树撑长打漂」这句话就此落地。

    影子树在 tmp_path 里：历史那版只落临时目录，盘上被跟踪的文件一枚字节不动（R253 在册那一形）。
    """
    rel = TOOL.RUN9_SITES[key]["file"]
    body = blob_at(RUN9_MERGE, rel)
    shadow = tmp_path / "run9"
    target = shadow / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body.encode("utf-8"))

    then = TOOL.resolve_site(key, shadow)
    quoted = {printed_before_landing(item["label"]) for item in TOOL.READOUT_CITES if item["key"] == key}
    assert quoted == {then["cell"]}, key + " 那枚锚在收窗那一笔里读不出当年抄的数：" + str((then["cell"], quoted))
    assert block_of(key, shadow) == block_of(key), key + " 那块码在两版之间字不同：这不属于「文件被撑长」那一族"
    now = TOOL.resolve_site(key, REPO)
    assert now["cell"] != then["cell"], key + " 今天还在当年那几行上：这一枚就不该被改口"
    assert now["block"][1] - now["block"][0] == then["block"][1] - then["block"][0], "块形变了，行号算术就不成立"
    assert now["line"] > then["line"], "今天读得比当年靠上：撑长那一族在这枚锚上不成立，本件的措辞要改"


def test_the_landing_moved_no_byte_but_the_five_coordinate_tokens() -> None:
    """🔴 判据⑤的落地账：与并树那一版比，只有那几枚在册行锚所在行改了，而且改的只有坐标那一串字。

    行数一枚不许变、其余各行的字节一枚不许动 —— 这一枚是「只搬坐标、不搬事实」的机器读法。
    """
    then_rows, now_rows = pre_landing_book().split("\r\n"), readout_text().split("\r\n")
    assert len(then_rows) == len(now_rows), "落地改了行数：本单只许改那一串字"
    anchors = sorted({index for index, row in enumerate(now_rows)
                      for item in TOOL.READOUT_CITES if item["row"] in row})
    moved = [index for index, (before, after) in enumerate(zip(then_rows, now_rows)) if before != after]
    assert moved == anchors, "改了行：改的 " + str(moved) + " 与在册行锚 " + str(anchors) + " 不同序"
    assert masked(pre_landing_book()) == masked(readout_text()), "动的不止坐标那一串字"


def test_the_live_book_is_already_at_the_derived_state() -> None:
    """重落地是幂等的：拿现读再写一遍，那一本一个字都不该变（否则交付态没落在派生道上）。"""
    text = readout_text()
    assert TOOL.land_cells(text, derived()) == text, "那一格还没落在现读上：跑 `--land`，别手改数字"


@pytest.mark.parametrize("item", TOOL.FROZEN_CELLS, ids=lambda item: item["label"])
def test_retouching_any_history_cell_is_red_and_moves_no_live_claim(item: dict) -> None:
    """判据④那把牙逐枚咬：冻结名单里任何一枚被人「统一改口」，`frozen_missing` 点它的名，
    而在册那几枚断言一行都不许跟着红（两族该分开红）。"""
    text = readout_text()
    assert text.count(item["cell"]) >= 1, item["label"] + " 登记的那枚坐标今天在读数本里读不到"
    retouched = text.replace(item["cell"], shift(item["cell"], 1))
    assert retouched != text, item["label"] + "：那枚坐标在书里换不动，本刀白磨"
    assert TOOL.frozen_missing(text) == []
    red = TOOL.frozen_missing(retouched)
    assert len(red) == 1 and item["label"] in red[0] and "追改" in red[0], str(red)
    report = TOOL.compare(root=REPO, text=retouched)
    assert not [entry for entry in report["red"] if "重落地" in entry], str(report["red"])


def test_the_registered_history_cells_are_verbatim_quotes_from_the_book() -> None:
    """历史表里那几枚坐标是从读数本抄来的在册事实，不是量具自己发明的数：逐枚回读一遍。"""
    text = readout_text()
    for item in TOOL.FROZEN_CELLS:
        assert item["cell"] in row_of(text, item["row"]), item["label"] + " 登记的坐标不在它那一格里：" + item["cell"]


# ------------------------------------------------------------------ ⑤ 在册与冻结互斥


def test_no_live_coordinate_is_double_registered_as_history() -> None:
    """🔴 补令判据③：本笔按现读落地的每一枚都不许同时躺在冻结名单里；改口前的旧抄数也不许留名。

    两把尺对同一枚坐标各说各话＝这本账自相矛盾：跟着现读走的就从历史里摘登记，留在历史里的
    就从在册表里摘格。今天五枚在册、八枚冻结，交集为空 —— 这一枚钉的是交集，不是某一枚数。
    """
    text, cells = readout_text(), derived()
    frozen = {item["cell"] for item in TOOL.FROZEN_CELLS}
    slots = {TOOL.read_cell(text, item) for item in TOOL.READOUT_CITES}
    assert frozen & (set(cells.values()) | slots) == set(), "同一枚坐标躺在两张表里（判据③）"
    assert TOOL.registered_conflicts(text, cells) == []
    for label in LIVE_LABELS:
        stale = printed_before_landing(label)
        assert stale not in frozen, label + " 改口前那枚旧抄数还被登记成历史：" + stale
        assert stale not in readout_text(), label + " 的旧抄数今天还印在书上：那一格没落地"


def test_the_row_the_book_rewords_keeps_its_other_legs_frozen() -> None:
    """同一行里「跟着现读走的」与「留在历史里的」并存时，登记必须切得开：:182 那一格三条腿。"""
    mouth_row = cite("分母口径·代码腿")["row"]
    legs = [item for item in TOOL.FROZEN_CELLS if item["row"] == mouth_row]
    live = [item for item in TOOL.READOUT_CITES if item["row"] == mouth_row]
    assert (len(legs), len(live)) == (2, 2), "那一行的腿数今天变了，本件的账要跟着现读：" + str((len(legs), len(live)))
    cells = derived()
    for item in legs:
        assert item["cell"] not in set(cells.values()), item["label"] + " 既冻结又现读：判据③不许"


def test_the_mutex_tooth_fires_on_a_double_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 这枚牙自己咬得住，而且不在 `frozen_missing()` 里面：把一枚在册现读追加登记成历史 ——
    历史那把尺一声不吭（那一串字确实还在它那一格里），互斥那把尺点名「两把尺各说各话」。"""
    text, cells = readout_text(), derived()
    entry = {"label": "误登记成历史的活口", "row": cite("分母口径·代码腿")["row"],
             "cell": cells["report_denominator_code"]}
    monkeypatch.setattr(TOOL, "FROZEN_CELLS", TOOL.FROZEN_CELLS + (entry,))
    red = TOOL.registered_conflicts(text, cells)
    assert len(red) == 1, str(red)
    assert entry["label"] in red[0] and "两把尺" in red[0], red[0]
    assert "等于某一枚在册现读" in red[0] and "等于某一枚在册格此刻印的数" in red[0], red[0]
    assert TOOL.frozen_missing(text) == [], "互斥那把牙长进了 frozen_missing：摘冻结守卫会连它一起摘掉"


def test_the_mutex_tooth_names_the_printed_slot_when_the_two_legs_diverge(monkeypatch: pytest.MonkeyPatch) -> None:
    """漂移态下两形分得开：那一格印的是漂了的数，冻结登记占住的正是「此刻印的数」那一形。"""
    cells = derived()
    label, key = "C2 算法", "unsupported_claim_rate"
    drifted_cell = shift(cells[key], 1)
    drifted = mutate_cell(readout_text(), label, drifted_cell)
    entry = {"label": "占住活口的历史登记", "row": cite(label)["row"], "cell": drifted_cell}
    monkeypatch.setattr(TOOL, "FROZEN_CELLS", TOOL.FROZEN_CELLS + (entry,))
    red = TOOL.registered_conflicts(drifted, cells)
    assert len(red) == 1 and "等于某一枚在册格此刻印的数" in red[0], str(red)
    assert "等于某一枚在册现读" not in red[0], red[0]
