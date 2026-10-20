# -*- coding: utf-8 -*-
"""R595 —— A① 时延的机器读数：三组数（问答类／分析·报告类／整表）＋ 停表帽命中单列。只读、离线、零模型。

===== 这一格为什么要立单 =====
``docs/handoff/2026-09-17-perf-architecture-plan.md:383-384`` 钉着两枚口径（作者署「R440 口径裁定·总控代业主裁定·可推翻」）：
① A① 的 V1 时延门槛**只认问答类那一格**（≤90 s／p95／n 必带），分析·报告类阈值随阶段 B 另立、V1 内不判；
   整表 p95 从今天起只作**每轮必须公布的读数**，不作门槛。
② 🔴 **命中停表帽（``EVAL_QUEUE_STALL_SECONDS``，默认 300 s）的题必须单列一格报数**——既不许从 p95 里悄悄摘掉，
   也不许混进「正常慢答」当成模型的问题；每轮跑分的抬头必须写「停表帽命中 N 枚」。
而本席 10-03 11:5x 现取：``rg -ln 'EVAL_QUEUE_STALL_SECONDS' scripts app tests`` 只命中
``scripts/eval_transport_ask_v2.py`` 与 ``tests/test_r222_queue_terminal_stopwatch.py``；
``scripts/run_quality_evaluation.py:25`` 只打整表 ``p95_ms=``；``scripts/r580_per_class_attribution.py`` 零命中 ``wall_ms``/``p95``。
⇒ 那两格今天没有任何一件脚本产出，每班纸上的「问答类 n=64 avg 30.1／p50 25.8／p95 61.0 s」全是现场手推。
本件把那两格变成机器读数：**同一 HEAD 复跑逐字节相同，判词不再依赖某个班的手工分群**。

===== 分群派生规则（判据②：不许靠猜，从夹具自己的字段现读）=====
在册唯一事实源 = 计划书 ``:352`` 那格 09-20 21:3x 裁定原文（R440 在 ``:383`` 明写「这是 09-20 那格口径的延续，不是新口径」）：
90 s 只约束**问答类** = ``文档问答 + 多轮对话 + 口径冲突 + 无证据问题 + 工具调用 + 跨部门权限``（run4 n=64）；
**分析/报告类** = ``Excel计算 + 报告生成 + 图表生成 + 主动洞察``（n=35）；``审批判断`` n=6 **不入任一群**。
⇒ 分群键是夹具的 ``category`` 字段，**不是** ``tier``：拿 ``tests/fixtures/business_evaluation_100.jsonl`` 现算，
   问答类 64／分析·报告类 35／未入群（审批判断）6，加总正好 105 ⇒ 看板 ``:3480`` 那格「问答类 n=64／分析·报告 n=35」逐字复现。
🔴 而 ``tier`` 那一维今天给出的是另一个母集：问答 50／分析 35／报告 20（同样加总 105）。
   看板 ``:3993`` 那格「问答 n=64／分析 n=35／报告 n=20」把两维**并排印在同一句话里**（加总 119 ≠ 105），
   跟进单 ``:4176``（R440 立单原文）已经把这两句判成「不同母集，谁都不许抄谁」。
   ⇒ 本件因此同时交两维：``category`` 维是判据口径（三组数），``tier`` 维只作**对照**并明写它不是门槛口径，
     「6 枚去哪了」这一格读法是 ``审批判断``——它由 :352 白纸黑字排除，不是漏计。
   夹具里出现任何一份没被 :352 三份名单覆盖的 ``category`` ⇒ 本件 rc=3 并逐名点名，不自创一群、不静默并入。

===== 跨度口径（判据③：诚实跨度只认 sidecar 的 wall_ms）=====
跟进单 §21 R205a／看板 §4BV：真实适配器故意不自报 ``latency_ms``（``scripts/eval_transport_ask_v2.py:1407``），
采集器旧行为曾把 ``perf_counter`` 的**整调用**跨度顶上去（重试、重试 sleep、排队轮询观测窗、8 h 6 min 整机待机全在里面），
R205a 之后「越出一发量级上限的跨度记 null、原始观测留在 ``latency_suspect``，诚实跨度只认帧账 sidecar 的 ``wall_ms``」。
⇒ 本件**拒收** ``latency_ms`` 当跨度：聚合只用 ``wall_ms``；``latency_ms`` 只被读来**点名**与 ``wall_ms`` 差出一发量级的题
   （容忍带用在册那两枚常数 ``LATENCY_LEDGER_RATIO_TOLERANCE``／``LATENCY_LEDGER_SLACK_MS``，不另存一份数字）。

===== 停表帽（判据①后半格：帽值现读不写死）=====
帽值不抄常数：``ast`` 解析 ``scripts/eval_transport_ask_v2.py`` 里 ``QUEUE_STALL_SECONDS = float(os.getenv(...))`` 那一行，
取它自己的 env 名与字面默认，再按当前环境算生效值；抬头「停表帽命中 N 枚」就写在第一行。
命中判据两条，一条都不省：
* ``kind == "queued_stalled"`` —— 量具自己说它停表了（``eval_transport_ask_v2.py:1200``）。
* ``wall_ms`` 落进 ``[cap_ms, cap_ms + 一枚轮询间隔]`` —— ``:199-200`` 原话「代价是至多一枚轮询间隔（3 s）」；
  这条是**必须**的：R440 的凭据 ``run9 / chat-11 / wall_ms=300108.2`` 那枚的 ``kind`` 是 ``ok``，只认 kind 会把它漏掉。
超帽带（``wall_ms > cap_ms + 轮询间隔`` 而 kind 又不是 ``queued_stalled``）另立一格点名：它**不摘**，照旧进 p95，
由总控判它是不是别的原因的慢答——「不许悄悄摘掉」与「不许混进正常慢答」在这里同时成立：
判据口径 p95 剔的是**已确认**命中（逐枚点名过），含帽的 p95 也一并印出，两枚数都摆在纸上。

===== 纪律 =====
只读：三本件一律只读打开，本件一个字节都不往输入里写；不打模型、不开容器、不动 PG、不起服务。
不判绿：本格不判 A① 绿不绿，只把数摆出来；判绿权在总控（带噪窗的时延读数按「通过可信／不合格不作结论」处理）。
尺不另造：p95 最近秩那一版与在册 ``app/quality/eval.py::build_latency_cell`` 同源，本件逐群自证两枚读数相等。
🔴 但只自证**非空**那几格：空集上在册那把尺交回 ``p95=0``、本件交回 ``None`` ⇒ 两把尺是「都说不出数」，
   这一格明写说不出数，不拿「相等」冒充「同数」（``scale[群]["empty"]`` 为真时 ``agree`` 必为假，钉子在案）。

用法：
    python scripts/r595_latency_readout.py --answers <path> --fixture <path> [--sidecar <path>] [--label run13]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import math
import os
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文与箭头会当场炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: 帽值与轮询间隔的唯一来源（判据①：现读不写死）。
DEFAULT_TRANSPORT_SOURCE = REPO / "scripts" / "eval_transport_ask_v2.py"

#: 计划书 :352 白纸黑字的三份名单（R440 :383 延续，不是新口径）。
GROUP_QA = "问答类"
GROUP_ANALYSIS_REPORT = "分析·报告类"
GROUP_ALL = "整表"
GROUPS = (GROUP_QA, GROUP_ANALYSIS_REPORT, GROUP_ALL)
QA_CATEGORIES = ("文档问答", "多轮对话", "口径冲突", "无证据问题", "工具调用", "跨部门权限")
ANALYSIS_REPORT_CATEGORIES = ("Excel计算", "报告生成", "图表生成", "主动洞察")
UNGROUPED_CATEGORIES = ("审批判断",)
CATEGORY_TO_GROUP = {}
for _name in QA_CATEGORIES:
    CATEGORY_TO_GROUP[_name] = GROUP_QA
for _name in ANALYSIS_REPORT_CATEGORIES:
    CATEGORY_TO_GROUP[_name] = GROUP_ANALYSIS_REPORT
for _name in UNGROUPED_CATEGORIES:
    CATEGORY_TO_GROUP[_name] = None          # :352 明写「不入任一群」，不是漏计

#: 量具自己宣告停表的那枚 kind（eval_transport_ask_v2.py:1200 _stop("queued_stalled", ...)）。
STALL_KIND = "queued_stalled"

RC_OK = 0
RC_INPUT = 2
RC_CALIBER = 3
#: 在册自洽闸（guard_latency_cell）当场炸 ⇒ 这一窗的读数根本不可用。
RC_LEDGER = 4


class ReadoutError(RuntimeError):
    """件取不到、读不通、或夹具里长出 :352 没覆盖的类别 ⇒ 宁可拒判，不静默补数。"""




def sha12(path: Path) -> str:
    """件名的指纹：复算对账要能证明读的是同一份字节。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def read_jsonl(path: Path, what: str) -> list[dict]:
    """只读打开一本 jsonl。读不通就是 ReadoutError —— 不跳行、不补零、不当没看见。"""
    path = Path(path)
    if not path.is_file():
        raise ReadoutError("取不到件：%s（%s）—— 明写取不到，不编数" % (path, what))
    rows: list[dict] = []
    with io.open(str(path), encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ReadoutError("%s（%s）第 %d 行读不成 JSON：%s" % (path, what, number, exc)) from exc
            if not isinstance(row, dict):
                raise ReadoutError("%s（%s）第 %d 行不是对象 ⇒ 读不了" % (path, what, number))
            rows.append(row)
    return rows


def fold_latest(rows: list[dict], what: str) -> tuple[dict, int]:
    """题号 → 行：同题多轮取 attempt 最大的那一行（与 scripts/eval_lane_readout.py:47 同一规则）。"""
    folded: dict[str, dict] = {}
    collisions = 0
    for row in rows:
        key = str(row.get("id"))
        previous = folded.get(key)
        if previous is None:
            folded[key] = row
            continue
        collisions += 1
        if int(row.get("attempt") or 0) >= int(previous.get("attempt") or 0):
            folded[key] = row
    return folded, collisions


def read_env_constant(source: Path, name: str) -> tuple[str, str, int, str]:
    """从量具源码里现读一枚 ``NAME = float(os.getenv("ENV", "默认"))``。

    判据① 要的「帽值现读不写死」＝ 本件不存这份数字，只从唯一写点把它拆出来：
    交回 env 名、字面默认、行号、那一行原文（原文进纸面当凭据）。
    """
    text = Path(source).read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        value = node.value
        while (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
               and value.func.id in ("float", "int")):
            value = value.args[0] if value.args else value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and value.func.attr == "getenv" and len(value.args) >= 2):
            raise ReadoutError("%s:%d 的 %s 不是 os.getenv(名, 默认) 的形状 ⇒ 本件不敢现读"
                               % (source, node.lineno, name))
        env_name = value.args[0]
        default = value.args[1]
        if not (isinstance(env_name, ast.Constant) and isinstance(default, ast.Constant)):
            raise ReadoutError("%s:%d 的 %s 里 env 名或默认不是字面量" % (source, node.lineno, name))
        return str(env_name.value), str(default.value), node.lineno, lines[node.lineno - 1].strip()
    raise ReadoutError("%s 里找不到 %s 的赋值 ⇒ 帽值无从现读" % (source, name))


def resolve_env(env_name: str, default: str) -> float:
    """按当前环境算生效值：环境里有就用环境的，没有才落回量具自己的字面默认。"""
    raw = os.environ.get(env_name, default)
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ReadoutError("环境变量 %s=%r 读不成数字" % (env_name, raw)) from exc


def stall_cap(source: Path = DEFAULT_TRANSPORT_SOURCE) -> dict:
    """停表帽与轮询间隔（帽带的宽度）全部现读，含出处行号与原文。"""
    cap_env, cap_default, cap_line, cap_text = read_env_constant(source, "QUEUE_STALL_SECONDS")
    poll_env, poll_default, poll_line, poll_text = read_env_constant(source, "QUEUE_POLL_INTERVAL")
    cap_ms = resolve_env(cap_env, cap_default) * 1000.0
    poll_ms = resolve_env(poll_env, poll_default) * 1000.0
    if cap_ms <= 0:
        raise ReadoutError("现读出来的帽值 %s ms 不是正数 ⇒ 判据不可用" % cap_ms)
    return {"cap_ms": cap_ms, "poll_ms": poll_ms, "cap_env": cap_env, "cap_default": cap_default,
            "cap_line": cap_line, "cap_text": cap_text, "poll_env": poll_env,
            "poll_default": poll_default, "poll_line": poll_line, "poll_text": poll_text,
            "cap_from_env": cap_env in os.environ, "source": str(source)}


def nearest_rank(values: list[float], q: float) -> float | None:
    """判据口径那一把：与 app/quality/eval.py:628 的 rank = max(1, ceil(n*q)) 逐字同规则。"""
    v = sorted(values)
    if not v:
        return None
    return v[min(len(v) - 1, max(1, math.ceil(len(v) * q)) - 1)]


def linear_rank(values: list[float], q: float) -> float | None:
    """线性插值那一版（在册 eval_lane_readout.py:63 rank() 同规则），只作对照印出，不是判据口径。"""
    v = sorted(values)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def span_ms(value) -> float | None:
    """把一格跨度读成非负毫秒；读不出来就是 None —— 不猜、不补、不当 0 用。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def honest_span(row_id: str, sidecar_row: dict | None, envelope_ms: float) -> tuple[float | None, str | None]:
    """这一发的诚实跨度：只认帧账 sidecar 的 wall_ms（R205a），``latency_ms`` 在本件里永不参与聚合。"""
    if sidecar_row is None:
        return None, "帧账 sidecar 没有这一题 ⇒ 没有诚实跨度（answers.latency_ms 不许顶替）"
    raw = sidecar_row.get("wall_ms")
    span = span_ms(raw)
    if span is None:
        return None, "帧账 wall_ms=%r 读不成非负毫秒 ⇒ 这一题不计入聚合" % (raw,)
    if span > envelope_ms:
        return None, ("帧账 wall_ms=%s ms 自己越出一发量级上限 %s ms ⇒ 连帧账都不像一发尝试，"
                      "不计入聚合" % (round(span, 1), round(envelope_ms, 1)))
    return span, None




def derive_groups(fixture: dict[str, dict]) -> dict:
    """三群成员 = 夹具自己的 ``category`` 落在 :352 哪一份名单里；一枚都不靠猜、不靠题号前缀。

    同时交 ``tier`` 维的成员（问答／分析／报告），它只作对照：两维今天不是同一个母集。
    """
    groups: dict[str, list[str]] = {name: [] for name in GROUPS}
    tiers: dict[str, list[str]] = {}
    category_counts: dict[str, int] = {}
    uncovered: dict[str, list[str]] = {}
    for row_id, row in sorted(fixture.items()):
        category = str(row.get("category") or "")
        tier = str(row.get("tier") or "")
        category_counts[category] = category_counts.get(category, 0) + 1
        groups[GROUP_ALL].append(row_id)
        if category in CATEGORY_TO_GROUP:
            target = CATEGORY_TO_GROUP[category]
            if target is not None:
                groups[target].append(row_id)
        else:
            uncovered.setdefault(category, []).append(row_id)
        tiers.setdefault(tier or "（夹具没这一格）", []).append(row_id)
    return {"groups": groups, "tiers": tiers, "category_counts": category_counts,
            "uncovered": uncovered,
            "ungrouped": [i for i in groups[GROUP_ALL] if CATEGORY_TO_GROUP.get(str(fixture[i].get("category") or "")) is None]}


def cap_judgement(span: float | None, kind: str, cap: dict) -> tuple[str | None, str | None]:
    """这一发是不是停表帽那一枚：量具自己说停表，或 wall_ms 落进帽带（cap ~ cap+一枚轮询间隔）。

    返回 (verdict, via)：verdict 取 ``hit`` / ``above`` / None；``above`` 不摘，只点名。
    """
    if span is None:
        return None, None
    if kind == STALL_KIND:
        return "hit", "kind=queued_stalled（量具自己宣告停表）"
    if cap["cap_ms"] <= span <= cap["cap_ms"] + cap["poll_ms"]:
        return "hit", "wall_ms 落进帽带 [%s, %s]（eval_transport_ask_v2.py:199-200 那枚「至多一枚轮询间隔」）" % (
            round(cap["cap_ms"], 1), round(cap["cap_ms"] + cap["poll_ms"], 1))
    if span > cap["cap_ms"] + cap["poll_ms"]:
        return "above", "wall_ms 越出帽带上沿 %s ms，而 kind=%s 不是停表 ⇒ 不摘，请总控判它慢在哪" % (
            round(cap["cap_ms"] + cap["poll_ms"], 1), kind or "（侧车没 kind）")
    return None, None


def cell_for(member_ids: list[str], spans: dict[str, float], hit_ids: set[str]) -> dict:
    """一群的读数：n 必带（母集／有跨度／进 p95 三枚都写），p95 判据口径 = 剔已确认命中后的最近秩。"""
    measured = [i for i in member_ids if i in spans]
    # 命中只在**本群成员**里数：拿全局命中数当本群读数会把零命中的群印成「帽命中 1 枚」。
    hits_here = [i for i in measured if i in hit_ids]
    used = [spans[i] for i in measured if i not in hit_ids]
    inclusive = [spans[i] for i in measured]
    return {
        "n": len(member_ids), "n_measured": len(measured), "n_used": len(used), "n_hits": len(hits_here),
        "avg": round(statistics.mean(used), 1) if used else None,
        "p50_rank": nearest_rank(used, 0.5), "p50_linear": linear_rank(used, 0.5),
        "p95_rank": nearest_rank(used, 0.95), "p95_linear": linear_rank(used, 0.95),
        "max": max(used) if used else None, "min": min(used) if used else None,
        "p95_rank_inclusive": nearest_rank(inclusive, 0.95),
        "p95_linear_inclusive": linear_rank(inclusive, 0.95),
        "n_inclusive": len(inclusive),
    }


def collect(answers_path: Path, fixture_path: Path, sidecar_path: Path,
            transport_source: Path = DEFAULT_TRANSPORT_SOURCE, label: str = "") -> dict:
    """读三本件、按在册口径算出纸面上要摆的每一格。全程只读。"""
    from app.quality.eval import (LATENCY_LEDGER_RATIO_TOLERANCE, LATENCY_LEDGER_SLACK_MS,
                                  build_latency_cell, classify_latency_span, latency_envelope_ms)

    answers_rows = read_jsonl(answers_path, "answers")
    fixture_rows = read_jsonl(fixture_path, "fixture")
    sidecar_rows = read_jsonl(sidecar_path, "sidecar")
    answers, a_collisions = fold_latest(answers_rows, "answers")
    fixture, f_collisions = fold_latest(fixture_rows, "fixture")
    sidecar, s_collisions = fold_latest(sidecar_rows, "sidecar")

    cap = stall_cap(transport_source)
    envelope_ms = latency_envelope_ms()
    derived = derive_groups(fixture)

    spans: dict[str, float] = {}
    rejects: list[dict] = []
    hits: list[dict] = []
    above: list[dict] = []
    drift: list[dict] = []
    for row_id in sorted(fixture):
        sidecar_row = sidecar.get(row_id)
        span, reason = honest_span(row_id, sidecar_row, envelope_ms)
        kind = str((sidecar_row or {}).get("kind") or "")
        if span is None:
            rejects.append({"id": row_id, "reason": reason,
                            "category": str((fixture[row_id] or {}).get("category") or "")})
            continue
        spans[row_id] = span
        verdict, via = cap_judgement(span, kind, cap)
        if verdict == "hit":
            hits.append({"id": row_id, "wall_ms": span, "kind": kind, "via": via,
                         "category": str(fixture[row_id].get("category") or ""),
                         "tier": str(fixture[row_id].get("tier") or "")})
        elif verdict == "above":
            above.append({"id": row_id, "wall_ms": span, "kind": kind, "via": via,
                          "category": str(fixture[row_id].get("category") or ""),
                          "tier": str(fixture[row_id].get("tier") or "")})
        # 判据③：latency_ms 只被读来点名，不参与聚合。
        reported = answers.get(row_id, {}).get("latency_ms")
        reported_ms = span_ms(reported)
        if reported_ms is not None:
            limit = round(span * LATENCY_LEDGER_RATIO_TOLERANCE + LATENCY_LEDGER_SLACK_MS, 2)
            if reported_ms > limit or span > round(reported_ms * LATENCY_LEDGER_RATIO_TOLERANCE
                                                   + LATENCY_LEDGER_SLACK_MS, 2):
                drift.append({"id": row_id, "latency_ms": reported_ms, "wall_ms": span,
                              "ratio": round(reported_ms / span, 4) if span else None,
                              "tolerance_ms": limit,
                              "action": classify_latency_span(row_id, reported_ms, span,
                                                              envelope_ms=envelope_ms)["action"]})

    hit_ids = {h["id"] for h in hits}
    cells: dict[str, dict] = {}
    scale: dict[str, dict] = {}
    ledger_error = None
    for name in GROUPS:
        member_ids = derived["groups"][name]
        cells[name] = cell_for(member_ids, spans, hit_ids)
        used = [spans[i] for i in member_ids if i in spans and i not in hit_ids]
        try:
            inbook = build_latency_cell(used)
            scale[name] = {"inbook_p95": inbook["p95"], "local_p95": cells[name]["p95_rank"],
                           "agree": inbook["p95"] == cells[name]["p95_rank"],
                           "empty": not used}
        except Exception as exc:  # 在册自洽闸（平均值大于逐题最大值这类不可能形状）
            ledger_error = "%s：%s" % (type(exc).__name__, exc)
            scale[name] = {"inbook_p95": None, "local_p95": cells[name]["p95_rank"],
                           "agree": False, "empty": not used}

    tier_cells = {name: cell_for(member_ids, spans, hit_ids)
                  for name, member_ids in sorted(derived["tiers"].items())}

    return {
        "label": label, "cap": cap, "envelope_ms": envelope_ms,
        "files": {"answers": str(answers_path), "fixture": str(fixture_path), "sidecar": str(sidecar_path)},
        "sha": {"answers": sha12(answers_path), "fixture": sha12(fixture_path), "sidecar": sha12(sidecar_path)},
        "counts": {"answers_raw": len(answers_rows), "answers": len(answers), "a_collisions": a_collisions,
                   "fixture_raw": len(fixture_rows), "fixture": len(fixture), "f_collisions": f_collisions,
                   "sidecar_raw": len(sidecar_rows), "sidecar": len(sidecar), "s_collisions": s_collisions},
        "join": {"fixture_no_sidecar": sorted(set(fixture) - set(sidecar)),
                 "fixture_no_answers": sorted(set(fixture) - set(answers)),
                 "sidecar_not_in_fixture": sorted(set(sidecar) - set(fixture)),
                 "answers_not_in_fixture": sorted(set(answers) - set(fixture))},
        "derived": derived, "cells": cells, "tiers": tier_cells, "scale": scale,
        "hits": hits, "above": above, "rejects": rejects, "drift": drift,
        "answers_latency_rows": sum(1 for row in answers.values()
                              if span_ms(row.get("latency_ms")) is not None),
        "ledger_error": ledger_error,
    }




def fmt(value) -> str:
    """毫秒读数同时交 ms 与 s（板上历史那几格都写在 s，复算对账要能一眼比）。"""
    if value is None:
        return "—"
    return "%.1f ms (%.1f s)" % (value, value / 1000.0)


def stat_line(name: str, cell: dict, inclusive_note: str) -> list[str]:
    if not cell["n_used"]:
        return ["- %s：n=%d（母集）／%d（有诚实跨度）／0（进 p95）｜帽命中 %d 枚 ⇒ 🔴 无量可算（该群这一格空）"
                % (name, cell["n"], cell["n_measured"], cell["n_hits"])]
    lines = ["- %s：n=%d（母集）／%d（有诚实跨度）／%d（进 p95）｜帽命中 %d 枚"
             % (name, cell["n"], cell["n_measured"], cell["n_used"], cell["n_hits"]),
             "    avg=%s ｜ p50(最近秩)=%s ｜ **p95(最近秩·判据口径)=%s** ｜ p95(线性插值·对照)=%s"
             % (fmt(cell["avg"]), fmt(cell["p50_rank"]), fmt(cell["p95_rank"]), fmt(cell["p95_linear"])),
             "    max=%s ｜ min=%s" % (fmt(cell["max"]), fmt(cell["min"]))]
    if inclusive_note:
        lines.append("    " + inclusive_note)
    return lines


def inclusive_note(cell: dict) -> str:
    if not cell["n_inclusive"]:
        return ""
    if cell["n_used"] == cell["n_inclusive"]:
        return ("含停表帽命中那一格（一枚都不摘）：n=%d p95(最近秩)=%s ⇒ 与判据口径同一枚数（本群零命中）"
                % (cell["n_inclusive"], fmt(cell["p95_rank_inclusive"])))
    return ("含停表帽命中那一格（一枚都不摘）：n=%d p95(最近秩)=%s p95(线性插值)=%s ｜ 两枚数的差 = 摘掉 %d 枚命中所致，"
            "命中逐枚点名见下" % (cell["n_inclusive"], fmt(cell["p95_rank_inclusive"]),
                                 fmt(cell["p95_linear_inclusive"]), cell["n_hits"]))


def render(data: dict) -> list[str]:
    cap = data["cap"]
    out: list[str] = []
    out.append("停表帽命中 %d 枚（帽值 %s，现读自 %s:%d）" % (
        len(data["hits"]), fmt(cap["cap_ms"]), Path(cap["source"]).name, cap["cap_line"]))
    out.append("")
    out.append("## R595 时延读出（label=%s）｜ A① 三组数 + 停表帽单列｜只读、离线、零模型"
               % (data["label"] or "（未取名）"))
    out.append("- 件：answers=%s [%s] ｜ fixture=%s [%s] ｜ sidecar=%s [%s]" % (
        Path(data["files"]["answers"]).name, data["sha"]["answers"],
        Path(data["files"]["fixture"]).name, data["sha"]["fixture"],
        Path(data["files"]["sidecar"]).name, data["sha"]["sidecar"]))
    counts = data["counts"]
    out.append("- 行数：answers 原始 %d → 折叠 %d（同题多轮 %d 次）｜ fixture 原始 %d → 折叠 %d ｜ sidecar 原始 %d → 折叠 %d"
               % (counts["answers_raw"], counts["answers"], counts["a_collisions"],
                  counts["fixture_raw"], counts["fixture"], counts["sidecar_raw"], counts["sidecar"]))
    join = data["join"]
    out.append("- join：夹具无 sidecar=%s ｜ 夹具无 answers=%s ｜ sidecar 不在夹具=%s ｜ answers 不在夹具=%s" % (
        join["fixture_no_sidecar"] or "无", join["fixture_no_answers"] or "无",
        join["sidecar_not_in_fixture"] or "无", join["answers_not_in_fixture"] or "无"))
    out.append("")

    out.append("### 帽值现读（判据①：不写死）")
    out.append("- 源码行：%s:%d → ``%s``" % (Path(cap["source"]).name, cap["cap_line"], cap["cap_text"]))
    out.append("- 环境变量 ``%s`` 现场%s ⇒ 生效 %s；带宽 = 一枚轮询间隔（``%s`` 缺省 %s ⇒ %s）" % (
        cap["cap_env"], "被设成了 " + repr(os.environ.get(cap["cap_env"])) if cap["cap_from_env"] else "未设，落回字面默认 " + repr(cap["cap_default"]),
        fmt(cap["cap_ms"]), cap["poll_env"], cap["poll_default"], fmt(cap["poll_ms"])))
    out.append("- 一发量级上限（诚实跨度还要过的第二道闸）：现读 app/quality/eval.py 的 latency_envelope_ms() = %s"
               % fmt(data["envelope_ms"]))
    out.append("")

    derived = data["derived"]
    out.append("### 分群派生（判据②：从夹具 category 现读，规则钉在计划书 :352）")
    out.append("- 问答类 = %s" % " + ".join(QA_CATEGORIES))
    out.append("- 分析·报告类 = %s" % " + ".join(ANALYSIS_REPORT_CATEGORIES))
    out.append("- 不入任一群（:352 白纸黑字排除，不是漏计）= %s ⇒ 实际未入群 %d 枚：%s" % (
        " + ".join(UNGROUPED_CATEGORIES), len(derived["ungrouped"]),
        sorted(derived["ungrouped"])[:8] if len(derived["ungrouped"]) <= 8
        else "%s …（共 %d 枚，全名见 --json）" % (sorted(derived["ungrouped"])[:8], len(derived["ungrouped"]))))
    out.append("- category 直方图（夹具现算）：%s" % dict(sorted(derived["category_counts"].items(),
                                                             key=lambda kv: (-kv[1], kv[0]))))
    if derived["uncovered"]:
        out.append("- 🔴 口径未覆盖的 category（:352 三份名单之外，本件不自创群、不静默并入）：%s"
                   % {k: v for k, v in sorted(derived["uncovered"].items())})
    else:
        out.append("- 口径未覆盖的 category：零枚（夹具里每一枚 category 都在 :352 的名单上）")
    out.append("")

    out.append("### 三组数（判据口径：p95 取最近秩，与 app/quality/eval.py:628 同一把；母集里剔**已确认**停表帽命中）")
    for name in GROUPS:
        out.extend(stat_line(name, data["cells"][name], inclusive_note(data["cells"][name])))
    out.append("")

    out.append("### 停表帽命中（判据①后半格：单列一格，逐枚点名）")
    if data["hits"]:
        for hit in data["hits"]:
            out.append("- %s ｜ wall_ms=%s ｜ kind=%s ｜ 入群=%s ｜ category=%s ｜ tier=%s ｜ 判据=%s" % (
                hit["id"], fmt(hit["wall_ms"]), hit["kind"] or "—",
                CATEGORY_TO_GROUP.get(hit["category"], "（口径未覆盖）") or "不入群",
                hit["category"], hit["tier"], hit["via"]))
    else:
        out.append("- 零枚：本窗没有任何一发落在停表帽上（判据口径与含帽两枚数因此同一枚数，见上一节）")
    out.append("- 超帽带（wall_ms 越过帽值＋一枚轮询间隔而 kind 不是 queued_stalled）⇒ 🔴 **不摘**，照旧进 p95，请总控判它慢在哪：%d 枚"
               % len(data["above"]))
    for row in data["above"]:
        out.append("  - %s ｜ wall_ms=%s ｜ kind=%s ｜ category=%s ｜ tier=%s ｜ %s" % (
            row["id"], fmt(row["wall_ms"]), row["kind"] or "—", row["category"], row["tier"], row["via"]))
    out.append("")

    out.append("### 诚实跨度口径（判据③：只认 sidecar.wall_ms，latency_ms 一律拒收当跨度）")
    out.append("- answers 里带可用 latency_ms 的枚数=%d，本件**一枚都没拿来聚合**（R205a：诚实跨度只认帧账 sidecar 的 wall_ms）"
               % data["answers_latency_rows"])

    if data["drift"]:
        out.append("- 🔴 latency_ms 与 wall_ms 差出容忍带（1.25×＋2000 ms，用在册那两枚常数，不另存数字）=%d 枚："
                   % len(data["drift"]))
        for row in data["drift"]:
            out.append("  - %s ｜ latency_ms=%s ｜ wall_ms=%s ｜ 倍差=%s ｜ 容忍上沿=%s ms ｜ 在册判器 action=%s" % (
                row["id"], fmt(row["latency_ms"]), fmt(row["wall_ms"]), row["ratio"],
                row["tolerance_ms"], row["action"]))
    else:
        out.append("- latency_ms 与 wall_ms 差出容忍带：零枚（两列本窗互证，但聚合用的仍只有 wall_ms）")
    if data["rejects"]:
        out.append("- 🔴 拿不出诚实跨度（不计入聚合，逐枚点名）=%d 枚：" % len(data["rejects"]))
        for row in data["rejects"]:
            out.append("  - %s ｜ category=%s ｜ %s" % (row["id"], row["category"], row["reason"]))
    else:
        out.append("- 拿不出诚实跨度：零枚")
    out.append("")

    out.append("### 尺一致性自证（判据口径那把 p95 是否与在册 build_latency_cell 同一枚数）")
    for name in GROUPS:
        check = data["scale"][name]
        if check.get("empty"):
            out.append("- %s：这一格空群（进 p95 的枚数 = 0）⇒ 两把尺都说不出数：local(最近秩)=%s ｜ "
                       "inbook build_latency_cell.p95=%s（在册那把尺对空集交回 0，不是测到的跨度）"
                       " ⇒ 不拿「相等」冒充「同数」，也不算 agree" % (
                           name, fmt(check["local_p95"]), fmt(check["inbook_p95"])))
            continue
        out.append("- %s：local(最近秩)=%s ｜ inbook build_latency_cell.p95=%s ｜ agree=%s%s" % (
            name, fmt(check["local_p95"]), fmt(check["inbook_p95"]), check["agree"],
            "" if check["agree"] else " 🔴"))
    if data["ledger_error"]:
        out.append("- 🔴 在册自洽闸（guard_latency_cell）当场炸：%s ⇒ 本窗读数不可用" % data["ledger_error"])
    out.append("")

    out.append("### tier 维对照（🔴 非门槛口径，只为把「n=64 还是 n=50」这笔账摆成机器读数）")
    for name, cell in sorted(data["tiers"].items()):
        out.extend(stat_line("tier=%s" % name, cell, inclusive_note(cell)))
    out.append("")
    out.append("> 🔴 本格不判 A① 绿不绿，只把数摆出来；判绿权在总控。"
               "带噪窗（同机多枚执行层在跑）的时延读数按「通过可信／不合格不作结论」处理。")
    return out


def default_sidecar_for(answers_path: Path) -> Path:
    """件名同规律：answers-X.jsonl → sidecar-X.jsonl（与在册 eval_lane_readout.py:102 的命名同源）。"""
    name = Path(answers_path).name
    if "answers" not in name:
        raise ReadoutError("answers 件名里认不出 'answers'，不敢猜 sidecar ⇒ 请显式 --sidecar")
    return Path(answers_path).with_name(name.replace("answers", "sidecar", 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R595：A① 三组时延读数 + 停表帽命中单列（只读、离线）")
    ap.add_argument("--answers", required=True, help="采集器交回的答案件（只读）")
    ap.add_argument("--fixture", required=True, help="题集件（只读）：category/tier 是分群依据")
    ap.add_argument("--sidecar", default="", help="帧账 sidecar（只读）：wall_ms 是唯一诚实跨度；缺省按件名推")
    ap.add_argument("--label", default="", help="窗名，只写进抬头")
    ap.add_argument("--transport-source", default=str(DEFAULT_TRANSPORT_SOURCE),
                    help="帽值与轮询间隔的唯一来源件（现读不写死）")
    ap.add_argument("--json", action="store_true", help="把整个读数倒成 JSON（复算对账用）")
    args = ap.parse_args(argv)

    answers_path = Path(args.answers)
    fixture_path = Path(args.fixture)
    try:
        sidecar_path = Path(args.sidecar) if args.sidecar else default_sidecar_for(answers_path)
        data = collect(answers_path, fixture_path, sidecar_path,
                       transport_source=Path(args.transport_source), label=args.label)
    except ReadoutError as exc:
        print("🔴 取不到／读不通：%s" % exc)
        return RC_INPUT
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in render(data):
            print(line)
    if data["ledger_error"]:
        return RC_LEDGER
    if data["derived"]["uncovered"]:
        print("🔴 夹具里有 %d 族 category 落在计划书 :352 名单之外 ⇒ 分群口径要改纸面，不由本件自创"
              % len(data["derived"]["uncovered"]))
        return RC_CALIBER
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
