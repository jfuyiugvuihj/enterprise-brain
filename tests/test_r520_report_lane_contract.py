# -*- coding: utf-8 -*-
"""R520 判据④ 与「发出去那一枚字到底有没有人认」——量具与产品之间的同源契约。

## 为什么需要这一枚（现取凭据）

相 2 的开关有两半：量具那一半（EVAL_DECLARE_LANE_TIER 决定发不发 lane）由
tests/test_r520_declare_lane_env_leg.py 钉；产品那一半是 app/api/v1/chat.py 里
"if lane == LANE_REPORT and _report_lane_via_queue_enabled()" 那一道闸 —— 它只认
LANE_REPORT 那一枚字面。两半之间**从前没有任何钉**：量具的 LANE_BY_TIER 里那三个
lane 字面在 tests/ 里零命中（rg -n "LANE_BY_TIER" tests 实取为空），也就是说
把 "报告": "report" 改成 "reports"，采集器照样发、服务端照样按闭集回 400，
而整轮跑分只会表现为「报告档一题都没进队列道」。本件钉的就是这条接缝。

产品侧只**读源码**（ast），不 import app.api.v1.chat：实测一次 import 要约十秒，
还会真去连 127.0.0.1:5432 打 Postgres 探针（本单一行都不许碰库、也不给今晚的真机窗添争用）。

## 判据④ 复验：派工词的读数要更正一格

派工词写「现取 105 行、report-* 12 行、tier 全「报告」」。一手复取（本件逐枚点名）：

- 105 行 —— 对（文件名写的是 100，实取 105，run9 之后就是这个数）。
- id 前缀 report-* 共 12 行，且这 12 行的 tier 全是「报告」 —— 对。
- 但**全库 tier == 报告 的行是 20 枚，不是 12 枚**：除 report-01..12 之外还有
  metric-16..19（口径冲突 4 枚）与 tool-01..04（工具调用 4 枚）。

⇒ 直接后果：把 EVAL_DECLARE_LANE_TIER 设成「报告」开相 2，进队列道的是 **20 题**，
其中 8 题不带 report- 前缀。凡按「12 道报告题入队」去核 run10 相 2 的账，都会对不上，
这一格由本件钉成机器事实（名字见下），派工词按上面这句更正读。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from test_r520_declare_lane_env_leg import (  # noqa: T401  共用同一套离线假出口，不另起现场
    REPORT_LANE,
    REPORT_TIER,
    SCRIPT_PATH,
    fixture_rows,
    lanes_sent,
    ruler,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAT_PATH = REPO_ROOT / "app" / "api" / "v1" / "chat.py"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 相 2 声明的那一枚档位名，与全库 105 题里 tier 的取值闭集同源（本件第一条形状钉钉住它）。
TIER_VOCABULARY = ("报告", "分析", "问答")
#: 判据④ 一手复取的三个数：行数、report-* 行数、全库 tier == 报告 的行数。
CORPUS_ROWS = 105
REPORT_PREFIX_ROWS = 12
REPORT_TIER_ROWS = 20
#: 不带 report- 前缀却坐在报告档的那 8 枚（派工词那格更正的落点）。
OFF_PREFIX_REPORT_ROWS = ("metric-16", "metric-17", "metric-18", "metric-19",
                          "tool-01", "tool-02", "tool-03", "tool-04")


def module_level_literals(path):
    """交回模块级「名字 -> 字面量」那张表（只收能 literal_eval 的赋值，函数体一律不收）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return _literals_from(tree), tree


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return _Unset


class _Unset:
    """「这一枚赋值不是字面量」的哨兵：它存在的意义就是不许本件靠 except 静默放过。"""


def _literals_from(tree):
    """收模块级赋值。🔴 连 "x: tuple[str, ...] = (...)" 那种带注解的赋值一起收 ——
    ASK_LANE_VALUES 就是这么写的，只认 ast.Assign 会把整枚闭集漏掉（本件第一版栽在这里）。"""
    table = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            target, value_node = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value_node = node.target, node.value
        else:
            continue
        if value_node is None:  # 只声明不赋值（x: str）：这一格里没有字面量可读
            continue
        value = _literal(value_node)
        if value is not _Unset:
            table[target.id] = value
        elif isinstance(value_node, ast.Tuple):
            # ASK_LANE_VALUES = (LANE_QA, LANE_ANALYSIS, LANE_REPORT, "")：元素一半是名字、
            # 一半是字面量，两种都要落成果，不然闭集会整枚读不出来。
            resolved = []
            for element in value_node.elts:
                if isinstance(element, ast.Name):
                    if element.id not in table:
                        resolved = None
                        break
                    resolved.append(table[element.id])
                else:
                    value = _literal(element)
                    if value is _Unset:
                        resolved = None
                        break
                    resolved.append(value)
            if resolved is not None:
                table[target.id] = tuple(resolved)
    return table


def product_lane_literals():
    """产品那一侧的 lane 口径：三枚档位字面 + 服务端认的闭集。缺一枚就是本件该红的时候。"""
    table, _ = module_level_literals(CHAT_PATH)
    missing = [key for key in ("LANE_REPORT", "LANE_QA", "LANE_ANALYSIS", "ASK_LANE_VALUES")
               if key not in table]
    assert not missing, "产品侧 lane 口径改名或挪窝了，本件的接缝钉要先复验：" + repr(missing)
    return table


def queue_gate_lines():
    """app/api/v1/chat.py 里「lane == LANE_REPORT 而且队列开关开着」那道闸的行号（运行时派生）。

    🔴 不写死行号（R400 那三处行号改运行时派生的教训）：本件要的是「这道闸今天长这样、
    且全文件只长这一个样」，行号只用来在报错时点名。
    """
    tree = ast.parse(CHAT_PATH.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.BoolOp):
            continue
        if not isinstance(node.test.op, ast.And):
            continue
        conjuncts = list(node.test.values)
        has_eq_against_report = any(
            isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.ops[0], ast.Eq)
            and any(isinstance(o, ast.Name) and o.id == "LANE_REPORT"
                    for o in [c.left] + list(c.comparators))
            for c in conjuncts)
        has_switch = any(
            isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_report_lane_via_queue_enabled"
            for c in conjuncts)
        if has_eq_against_report and has_switch:
            hits.append(node.lineno)
    return hits


def lane_word_violations(lane_table, literals):
    """把「采集器可能发出去的 lane 字面」交给产品口径判一遍，交回违规清单（空表 = 合格）。

    本件与 tests/test_r520_counter_evidence_teeth.py 共用这一个判据函数：真树走一遍必须为空，
    临时根副本走一遍必须非空 —— 两边读的都是这同一段代码，不存在「teeth 自己另写一套宽口径」。
    """
    accepted = literals["ASK_LANE_VALUES"]
    violations = []
    if not isinstance(lane_table, dict) or not lane_table:
        return ["采集器的档位->lane 表不是一枚非空字典：" + repr(lane_table)]
    for tier, lane in sorted(lane_table.items()):
        if not isinstance(lane, str) or not lane:
            violations.append(repr(tier) + " 的 lane 字面是空形：" + repr(lane))
        elif lane not in accepted:
            violations.append(repr(tier) + " -> " + repr(lane) + " 不在服务端认的闭集 "
                              + repr(accepted) + " 里（这一发 /ask 会被当场 400）")
    counts = {}
    for lane in lane_table.values():
        counts[lane] = counts.get(lane, 0) + 1
    for lane, times in sorted(counts.items(), key=lambda kv: str(kv[0])):
        if times > 1:
            violations.append("两枚档位共用同一枚 lane " + repr(lane) + " ⇒ 声明档位与入队判定不再一一对应")
    if lane_table.get(REPORT_TIER) != literals["LANE_REPORT"]:
        violations.append("报告档发的 lane " + repr(lane_table.get(REPORT_TIER))
                          + " 不是队列闸认的那一枚 " + repr(literals["LANE_REPORT"])
                          + " ⇒ 相 2 的开关拨了也不入队")
    return violations


# ==================== 产品侧那道闸的形状 ====================

def test_the_queue_gate_is_lane_equals_report_and_the_switch():
    """相 2 的唯一开关在产品这一侧只有一道闸，形状就是「lane == LANE_REPORT 且 队列开关开着」。"""
    hits = queue_gate_lines()
    assert len(hits) == 1, "这道闸的形状变了或长了第二道（行号 " + repr(hits) + "）" \
                           "⇒ run10 相 2 的前提要复验，本件的接缝判定不再等价"
    literals = product_lane_literals()
    assert literals["LANE_REPORT"] == REPORT_LANE
    assert literals["REPORT_LANE_QUEUE_ENV"] == "REPORT_LANE_VIA_QUEUE"


def test_the_gate_reads_the_constant_and_not_a_retyped_literal():
    """那道闸比的是 LANE_REPORT 这枚常量，不是谁重新手打的一枚字面 —— 不然本件的同源钉就白钉。"""
    source = CHAT_PATH.read_text(encoding="utf-8")
    line = next(iter(queue_gate_lines()))
    text = source.splitlines()[line - 1]
    assert re.search(r"\blane\s*==\s*LANE_REPORT\b", text), text
    assert '"report"' not in text and "'report'" not in text, text


# ==================== 接缝：量具发的字 == 产品认的字 ====================

def test_every_lane_word_the_ruler_can_send_is_one_the_server_accepts():
    """采集器发出去的每一枚 lane 字面都必须在服务端认的闭集里，且三档各发各的。"""
    table = _literals_from(ast.parse(SCRIPT_PATH.read_text(encoding="utf-8")))
    violations = lane_word_violations(table["LANE_BY_TIER"], product_lane_literals())
    assert violations == [], "；".join(violations)


def test_the_report_tier_sends_the_very_string_the_queue_gate_reads(tmp_path):
    """判据② 的产品侧那一半：设「报告」之后逐题发出去的那枚字，就是那道闸拿去比较的字面。

    这里读的是采集器**真的写进 /ask 载荷**的字段（离线假出口），不是它肚子里的常量 ——
    字面在载荷里，闸才认得到；两者任一边漂了本枚都红。
    """
    literals = product_lane_literals()
    with ruler(tmp_path, env=REPORT_TIER, tag="contract") as module:
        lanes = lanes_sent(module, fixture_rows())
    report_ids = sorted(rid for rid, tier in ((r["id"], r.get("tier")) for r in fixture_rows())
                        if tier == REPORT_TIER)
    assert len(report_ids) == REPORT_TIER_ROWS, "判据④ 那格读数漂了，见本件抬头"
    for row_id in report_ids:
        assert lanes[row_id] == literals["LANE_REPORT"] == REPORT_LANE, row_id
    for row_id, lane in lanes.items():
        if row_id not in report_ids:
            assert lane is None, row_id + "：不该发 lane 的题发了 " + repr(lane)


# ==================== 判据④：夹具形状（一手复取，与派工词不符处照实更正） ====================

def _rows():
    rows = []
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_the_corpus_shape_is_the_one_this_order_measured():
    """判据④：105 行、题号唯一、每行都有非空 tier；tier 取值闭集就是那三档。"""
    rows = _rows()
    assert len(rows) == CORPUS_ROWS, "实取 " + str(len(rows))
    ids = [str(row["id"]) for row in rows]
    assert len(set(ids)) == len(ids), "题号撞了，逐题读数会互相盖掉"
    tiers = {}
    for row in rows:
        tier = row.get("tier")
        assert isinstance(tier, str) and tier == tier.strip() and tier, repr(row.get("id")) + "：" + repr(tier)
        tiers[tier] = tiers.get(tier, 0) + 1
    assert set(tiers) == set(TIER_VOCABULARY), repr(tiers)
    assert tiers[REPORT_TIER] == REPORT_TIER_ROWS, repr(tiers)
    assert sum(tiers.values()) == CORPUS_ROWS


def test_the_report_prefixed_rows_are_all_report_tier():
    """report-01..12 逐枚都在报告档（派工词这一格对）；报告档另有 8 枚不带这个前缀（那一格要更正）。"""
    rows = _rows()
    prefixed = [str(row["id"]) for row in rows if str(row["id"]).startswith("report-")]
    assert prefixed == ["report-%02d" % index for index in range(1, REPORT_PREFIX_ROWS + 1)]
    assert all(row.get("tier") == REPORT_TIER for row in rows
               if str(row["id"]).startswith("report-"))
    on_report_tier = {str(row["id"]) for row in rows if row.get("tier") == REPORT_TIER}
    assert sorted(on_report_tier - set(prefixed)) == sorted(OFF_PREFIX_REPORT_ROWS), repr(
        sorted(on_report_tier - set(prefixed)))


def test_the_tier_names_the_ruler_can_declare_are_the_ones_the_corpus_uses():
    """量具能声明的档位名，必须恰好是名册里真在用的那三档：名册改口 ⇒ 开关会当场失灵。"""
    table = _literals_from(ast.parse(SCRIPT_PATH.read_text(encoding="utf-8")))
    tiers_in_corpus = {str(row.get("tier")) for row in _rows()}
    assert set(table["LANE_BY_TIER"]) == tiers_in_corpus == set(TIER_VOCABULARY), \
        repr((sorted(table["LANE_BY_TIER"]), sorted(tiers_in_corpus)))
