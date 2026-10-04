# -*- coding: utf-8 -*-
r"""R631 —— G-R51-1 的尺子：端到端时长 对 分段加总 的逐题误差。只读、离线、零模型、零容器、零 PG。

===== 这一格欠的是什么 =====
跟进单 21 判据表第 522 行（按 LF 计数）R51 的第②格，原文逐字（本件启动时现读那一行，不抄纸面）：
    ② 端到端与分段加总误差 <1%（对齐 docs/perf/latency-budget-2026-09-16.md 的 0.03%）
插桩（app/common/stage_timing.py）与算术（aggregate_stage_latency）已在树，R51 的离线牙也已在树
（tests/test_r51_stage_latency.py 拿 latency-budget 那十行手摆的表证过 0.0299%）。欠的是**那一次
对照读数**：拿真窗的产物把两条腿摆到同一枚分母上逐题算误差。本件就是把那次对照做成一键复跑的尺子。

===== 三件事先现读再写死（本件不抄常数）=====
* 判据线：现读 CRITERION_DOC 第 CRITERION_LINE_LF 行里「端到端与分段加总误差 <x%」的 x。
* 对齐线：现读 ALIGN_DOC 那一格「日志自报 160.6s，我按毫秒时间戳拆出 160.552 s，误差 0.03%」，
  取印出来的那枚 0.03 作限，并用它自己的两枚数复算一遍；复算与印面差过 ALIGN_TOLERANCE 判漂移。
* 在册刀刃：行为探针现取 —— 0.99% 必须绿、1.01% 必须红，据此把 app 里那枚 literal 夹进
  (0.99, 1.01]；纸上读到的 x 落不进这区间即口径漂移。
⇒ 三处任一读不到／对不上，本件不出数，直接 RC_CALIBER 点名，不拿旧数冒充。

===== 两条腿的真源（谁都不许冒充谁）=====
分段腿 S（唯一真源，本件不自加）：
    app/common/stage_timing.py::samples_from_events() 从持久化的 *.finished 跨度事件取 duration_ms，
    再交 app/common/stage_timing.py::aggregate_stage_latency() 的**加总账**（嵌套跨度已剔）。
端到端腿 E（候选各自署名；不同源的钟才叫对照）：
    sidecar  = <window>-sidecar.jsonl 的 wall_ms —— 采集器钟（scripts/eval_transport_ask_v2.py:1278
               round((time.time() - started) * 1000.0, 1)），按题号 id 索引；连 trace 优先用 --join
               交来的清单，没有清单就从事件载荷里的 session_id 自己派生（app/agents/orchestrator.py:1502
               把 session_id 写进载荷，采集器一题一枚：eval_transport_ask_v2.py:864）。
    events   = request_windows_from_events() —— 服务端钟，同一本 trace 里 request.started →
               request.completed/failed/cancelled 的毫秒差。
    frames   = <window>-sidecar-frames.jsonl 里 request.started → request.completed 的 elapsed_ms 差 ——
               与 sidecar 同钟，只作互证，不是第二条独立腿。
    segments = 拿分段加总自己当端到端。这枚选项**故意留着**：它就是那条一行代码不改也永远绿的路，
               留着才能被驱动、被钉子钉住「选它必然判不可信」。

同源判死（本件存在的首要理由）：E 与 S 若出自同一枚数字，比值恒 0，那条 <1% 永远绿，
而这种绿不需要任何改动就能拿到。两条签名任一命中即判「不可信」，RC_UNTRUSTED 点名：
  ① 声明同源：E 的真源署名 == S 的真源署名（--e2e-from segments 走的正是这条）；
  ② 恒零差：所有可比题 |S-E| 逐位为 0。两种精度、两把钟同时逐位相等不是测量，是自我复述。
同本账但不同数（events 腿与 S 腿读同一枚文件：时间戳差 vs 单调钟跨度）不判死，只降格：
抬头明写「服务端内部对照 ⇒ 弱」；跨钟腿在位时 auto 优先跨钟。

===== 用法 =====
    python scripts/r631_stage_sum_delta.py --window run20k
    python scripts/r631_stage_sum_delta.py --window run18 --dir C:\path\to\evalrun
    python scripts/r631_stage_sum_delta.py --window run21 --traces run21-traces.jsonl --join by-trace.jsonl
分段腿今天只在持久化 trace 事件里（盘上三份 sidecar／frames／answers 一件都没有 duration_ms；
这条现读写在 docs/perf/r631-stage-sum-delta-2026-10-04.md）。没有分段腿本件不编数：
直接 RC_NO_INPUT 并写清缺哪一枚件。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文与箭头会当场炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.common.performance import PerformanceStats
from app.common.stage_timing import (
    CANONICAL_STAGES,
    StageSample,
    aggregate_stage_latency,
    request_windows_from_events,
    samples_from_events,
)

# ==================== 退出码（语义写死，epilog 同文） ====================

RC_OK = 0
RC_GATE = 1
RC_ALIGN = 2
RC_NO_INPUT = 3
RC_UNTRUSTED = 4
RC_CALIBER = 5

EXIT_CODE_MEANING = {
    RC_OK: "两条线都 PASS（且同源判器未命中）",
    RC_GATE: "跑通了，但存在 >= 判据线的题 —— <1% 那一格 FAIL",
    RC_ALIGN: "<1% 全 PASS，但对齐线（latency-budget 的 0.03%）FAIL",
    RC_NO_INPUT: "量不到：分段腿或端到端腿无货，或一题都对不上 —— 这不是 PASS",
    RC_UNTRUSTED: "判「不可信」：端到端与分段同源／恒零差 —— 比值是自我复述，不是测量",
    RC_CALIBER: "口径漂移：判据线、对齐锚或在册刀刃读不到／对不上 —— 不出数",
}

# ==================== 判据现读（三处真源，皆不抄常数） ====================

CRITERION_DOC = REPO / "docs" / "handoff" / "2026-09-15-backend-followup-requests.md"
CRITERION_LINE_LF = 522
CRITERION_RE = re.compile(r"端到端与分段加总误差\s*<\s*([0-9]+(?:\.[0-9]+)?)\s*%")

ALIGN_DOC = REPO / "docs" / "perf" / "latency-budget-2026-09-16.md"
#: 「日志自报 `160.6s`，我按毫秒时间戳拆出 **160.552 s**，误差 0.03%」
ALIGN_RE = re.compile(
    r"日志自报[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*s[^0-9]*?([0-9]+(?:\.[0-9]+)?)\s*s[^0-9]*?误差\s*([0-9]+(?:\.[0-9]+)?)\s*%"
)
ALIGN_TOLERANCE = 0.005

#: 刀刃探针的两枚夹点：0.99% 必须绿、1.01% 必须红，中间的 literal 才是真门槛。
KNIFE_PASS_PCT = 0.99
KNIFE_FAIL_PCT = 1.01


class CaliberError(RuntimeError):
    """纸上读不到／读出的与在册刀刃不一致 —— 本件拒绝出数。"""


class InputMissing(RuntimeError):
    """要用的件不在／读不通 —— 量不到，绝不编数。"""


def _read_lines(path: Path) -> list[str]:
    if not Path(path).exists():
        #: 判据件／对齐锚不在＝口径没处读，属漂移，不是“盘上没货”。
        raise CaliberError("判据件不存在：%s" % path)
    #: 逐行只按 LF 切，且**不翻译行尾**：跟进单那本件是 \r\r\n 结尾，机器尺切出「第 522 行
    #: （LF 计数）」用的就是这把尺；翻译一次行号就漂，判据线会读成空行（10-04 本席真炸过一回）。
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    return text.split("\n")


def read_criterion_pct(doc: Path = CRITERION_DOC, line_lf: int = CRITERION_LINE_LF) -> dict[str, Any]:
    """判据线（<1%）现读：按 LF 计数取那一行，再从行内抠出百分数。"""
    lines = _read_lines(doc)
    if line_lf > len(lines):
        raise CaliberError("%s 只有 %d 行（LF 计数），第 %d 行不存在" % (doc, len(lines), line_lf))
    raw = lines[line_lf - 1].strip()
    match = CRITERION_RE.search(raw)
    if not match:
        raise CaliberError(
            "第 %d 行里认不出「端到端与分段加总误差 <x%%」⇒ 判据文本改过，本件不猜新口径：%s"
            % (line_lf, raw[:160])
        )
    return {"threshold_pct": float(match.group(1)), "doc": str(doc), "line_lf": line_lf, "raw": raw}


def read_alignment_pct(doc: Path = ALIGN_DOC) -> dict[str, Any]:
    """对齐线（0.03%）现读：取印面的数，并用它自己的两枚数复算一遍。"""
    for position, raw in enumerate(_read_lines(doc), start=1):
        match = ALIGN_RE.search(raw)
        if not match:
            continue
        end_to_end_s, sum_s, printed = (float(match.group(i)) for i in (1, 2, 3))
        if end_to_end_s <= 0 or sum_s <= 0:
            continue
        computed = abs(end_to_end_s - sum_s) / end_to_end_s * 100.0
        if abs(computed - printed) > ALIGN_TOLERANCE:
            raise CaliberError(
                "%s:%d 印的误差 %s%% 与它自己两枚数的复算 %s%% 差过 %s ⇒ 对齐锚失焦，不出数"
                % (doc, position, printed, round(computed, 5), ALIGN_TOLERANCE)
            )
        return {
            "align_pct": printed,
            "computed_pct": round(computed, 5),
            "end_to_end_s": end_to_end_s,
            "sum_s": sum_s,
            "doc": str(doc),
            "line_lf": position,
            "raw": raw.strip(),
        }
    raise CaliberError("%s 里读不到「日志自报 … 拆出 … 误差 …%%」那一格 ⇒ 对齐锚失焦，不出数" % doc)


def probe_inbook_gate() -> dict[str, bool]:
    """行为探针：把 app 里那枚门槛 literal 夹出来，不抄它的源码字面。

    0.99% 绿、1.01% 红 ⇒ literal 落在 (0.99, 1.01]。任一反向即口径漂移：本件与纸上判据的
    对照失去意义，宁可 RC_CALIBER，也不拿一枚可能已经改过的 literal 继续算。
    """
    verdicts: dict[str, bool] = {}
    for trace_id, pct in (("r631-knife-pass", KNIFE_PASS_PCT), ("r631-knife-fail", KNIFE_FAIL_PCT)):
        duration_ms = 10_000.0 * (100.0 - pct) / 100.0
        report = aggregate_stage_latency(
            [StageSample("generate", duration_ms, trace_id=trace_id)],
            end_to_end_by_trace={trace_id: 10_000.0},
        )
        cell = report["coverage"]["per_request"].get(trace_id)
        if cell is None:
            raise CaliberError("在册算术对探针题 %s 交回空 ⇒ 刀刃无法现读" % trace_id)
        verdicts[trace_id] = bool(cell["within_one_percent"])
    if verdicts != {"r631-knife-pass": True, "r631-knife-fail": False}:
        raise CaliberError("在册刀刃不再是 (0.99, 1.01]：实测 %s ⇒ 判据线要重裁" % verdicts)
    return verdicts


# ==================== 两条腿的真源署名 ====================

SEG_PROVENANCE = "stage_ledger"
SEG_CLOCK = "server-monotonic"

E2E_SIDECAR = "sidecar_wall_ms"
E2E_EVENTS = "trace_event_window"
E2E_FRAMES = "frames_event_window"
E2E_SEGMENTS = "segment_sum"

LEG_NOTES = {
    SEG_PROVENANCE: "在册分段账：samples_from_events + aggregate_stage_latency（嵌套已剔）",
    E2E_SIDECAR: "采集器钟 wall_ms（跨钟 ⇒ 强：分段与端到端不同源）",
    E2E_EVENTS: "服务端 trace 事件窗 request.started→终事件（同本账两面 ⇒ 弱，但不同数）",
    E2E_FRAMES: "采集器帧账 request.started→request.completed（与 sidecar 同钟，只作互证）",
    E2E_SEGMENTS: "拿分段加总自己当端到端 —— 同源，比值恒 0，不是测量",
}


@dataclass(frozen=True)
class Leg:
    """一条腿：真源署名、用的时钟、读到的值（键＝trace_id）、实际打开的件。"""

    name: str = ""
    clock: str = ""
    values: Mapping[str, float] = field(default_factory=dict)
    paths: tuple[str, ...] = ()
    note: str = ""
    keyed: str = "trace"  # trace | question —— 键空间，题号索引的腿要 join 才能用
    #: 同题多枚（重试／attempt>1）不许悄悄折叠：读了几行、撞的是哪几枚，全部点名。
    rows_read: int = 0
    duplicates: tuple[str, ...] = ()


# ==================== 盘上产物的读法 ====================


def _json_rows(path: Path) -> list[dict[str, Any]]:
    """逐行 JSONL；整本是一枚 JSON 数组也收（PG 导出常是数组）。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        whole = json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(whole, list):
            return [row for row in whole if isinstance(row, dict)]
        if isinstance(whole, dict):
            return [whole]
    rows: list[dict[str, Any]] = []
    for position, raw in enumerate(text.split("\n"), start=1):
        item = raw.strip()
        if not item:
            continue
        try:
            loaded = json.loads(item)
        except json.JSONDecodeError as exc:
            raise InputMissing("%s 第 %d 行不是 JSON ⇒ %s" % (path, position, str(exc)[:120])) from exc
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def _positive(value: float | None) -> float | None:
    """只有正数才算一枚跨度：0 与负数不是「很快的题」，是没读通。"""
    return value if value is not None and value > 0 else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)



def _collect_by_key(rows, key_of, value_of, attempt_of) -> tuple[dict[str, float], int, list[str]]:
    """按题号收读数：同题多枚取 attempt 最大的那枚，并**记下撞过名的题号**。

    run20k 的 sidecar 实测 106 行 105 枚题号（一枚题有两行），静默取最后一行会把「重试过」
    这件事擦掉；取 attempt 最大且点名，才是把折叠摆在纸上。
    """
    best: dict[str, tuple[float, int]] = {}
    seen: dict[str, int] = {}
    for row in rows:
        key = key_of(row)
        value = value_of(row)
        if not key or value is None:
            continue
        attempt = attempt_of(row)
        seen[key] = seen.get(key, 0) + 1
        if key not in best or attempt >= best[key][1]:
            best[key] = (value, attempt)
    values = {key: cell[0] for key, cell in best.items()}
    duplicates = sorted(key for key, hits in seen.items() if hits > 1)
    return values, sum(seen.values()), duplicates


def read_sidecar(path: Path) -> Leg:
    """端到端腿（采集器钟）：wall_ms 按题号索引。诚实跨度只认这一枚，latency_ms 不收。"""
    values, rows_read, duplicates = _collect_by_key(
        _json_rows(path),
        lambda row: str(row.get("id") or "").strip(),
        lambda row: _positive(_number(row.get("wall_ms"))),
        lambda row: int(_number(row.get("attempt")) or 0),
    )
    if not values:
        raise InputMissing("%s 里没有一枚正的 wall_ms ⇒ 端到端腿空" % path)
    return Leg(E2E_SIDECAR, "client", values, (str(Path(path).resolve()),), LEG_NOTES[E2E_SIDECAR],
               "question", rows_read, tuple(duplicates))


def read_frames(path: Path) -> Leg:
    """端到端腿（互证用）：帧账里 request.started→request.completed 的 elapsed_ms 差。"""
    values: dict[str, float] = {}
    seen: dict[str, int] = {}
    for row in _json_rows(path):
        key = str(row.get("id") or "").strip()
        if not key:
            continue
        started = completed = None
        for event in row.get("events") or []:
            name = str(event.get("event") or "")
            stamp = _number(event.get("elapsed_ms"))
            if stamp is None:
                continue
            if name == "request.started" and started is None:
                started = stamp
            elif name in ("request.completed", "request.failed", "request.cancelled"):
                completed = stamp
        if started is not None and completed is not None and completed > started:
            values[key] = round(completed - started, 6)
            seen[key] = seen.get(key, 0) + 1
    if not values:
        raise InputMissing("%s 里凑不出一枚 request.started→终事件的窗" % path)
    return Leg(E2E_FRAMES, "client", values, (str(Path(path).resolve()),), LEG_NOTES[E2E_FRAMES],
               "question", len(seen), tuple(sorted(k for k, hits in seen.items() if hits > 1)))


def _as_event(row: Mapping[str, Any]) -> dict[str, Any]:
    """把 trace_events 行或 journal 行归一成 replay() 交回的那本形状。

    地址：app/trace/run_reader.py::TraceDatabase._as_event —— replay 的消费方读的就是那几个键，
    本件不另立契约；created_at 只在这里当 timestamp 的别名收，payload 是字符串时解一次。
    """
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    stamp = row.get("timestamp")
    if stamp in (None, ""):
        stamp = row.get("created_at")
    return {
        "trace_id": str(row.get("trace_id") or ""),
        "request_id": str(row.get("request_id") or ""),
        "task_id": str(row.get("task_id") or ""),
        "sequence": row.get("sequence"),
        "timestamp": stamp,
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or ""),
        "payload": payload,
    }


def _event_files(target: Path) -> list[Path]:
    target = Path(target)
    if target.is_dir():
        found = sorted(p for p in target.rglob("*") if p.suffix in {".jsonl", ".json"} and p.is_file())
        if not found:
            raise InputMissing("%s 目录下没有 .jsonl/.json 可当 trace 事件" % target)
        return found
    if not target.exists():
        raise InputMissing("trace 事件件不存在：%s" % target)
    return [target]


def read_traces(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """分段腿的原料：持久化 trace 事件。目录＝逐枚件合并；一件都读不通才算无货。"""
    events: list[dict[str, Any]] = []
    used: list[str] = []
    for target in paths:
        for path in _event_files(target):
            rows = _json_rows(path)
            if not rows:
                raise InputMissing("%s 里没有可读的 JSON 行 ⇒ 分段腿无货" % path)
            events.extend(_as_event(row) for row in rows)
            used.append(str(Path(target).resolve()))
    return events, tuple(sorted(set(used)))


def read_join(path: Path) -> dict[str, str]:
    """trace_id → 题号。题号不进 trace 事件是在册事实（app/api/v1/observability.py 的
    SLO_BLOCKERS「no request event carries the question」），所以这枚清单只能由握着题号的一方交。"""
    mapping: dict[str, str] = {}
    for row in _json_rows(path):
        trace_id = str(row.get("trace_id") or "").strip()
        key = str(row.get("id") or row.get("question_id") or row.get("eval_id") or "").strip()
        if trace_id and key:
            mapping[trace_id] = key
    if not mapping:
        raise InputMissing("%s 里没有一枚 {trace_id, id} ⇒ join 清单空" % path)
    return mapping



def read_frames_sessions(path: Path) -> dict[str, str]:
    """题号 ↔ session_id：采集器一题一枚 session（eval_transport_ask_v2.py:864 发进请求体）。"""
    mapping: dict[str, str] = {}
    for row in _json_rows(path):
        session = str(row.get("session_id") or "").strip()
        key = str(row.get("id") or "").strip()
        if session and key:
            mapping[session] = key
    return mapping


def trace_keys_from_events(events: Iterable[Mapping[str, Any]], session_to_key: Mapping[str, str]) -> dict[str, str]:
    """trace_id → 题号，从事件载荷自己派生，零改产品码。

    在册事实：app/agents/orchestrator.py:1193/1430/1502/1518 把 ``session_id`` 写进事件载荷，
    app/trace/projections.py:160 再把它折进 ``agent_runs.session_id``；题号本身不进 trace
    （app/api/v1/observability.py SLO_BLOCKERS），但 session 进。所以只要同一窗的事件被导出，
    跨钟那条腿的桥就在导出件里自带 —— 本件优先用 --join 交来的清单，没有才自己派生。
    """
    if not session_to_key:
        return {}
    mapping: dict[str, str] = {}
    for row in events:
        trace_id = str((row or {}).get("trace_id") or "").strip()
        payload = (row or {}).get("payload") or {}
        session = str(payload.get("session_id") or "").strip()
        if trace_id and session and session in session_to_key:
            mapping.setdefault(trace_id, session_to_key[session])
    return mapping


def default_trace_candidates(directory: Path, window: str) -> list[Path]:
    return [
        Path(directory) / ("%s-traces.jsonl" % window),
        Path(directory) / ("%s-trace-events.jsonl" % window),
        Path(directory) / ("%s.traces" % window),
    ]


# ==================== 逐题对照 ====================


@dataclass
class RequestRow:
    """一题一行：分子分母都是**这一题**的，绝不用整窗加总除整窗加总。"""

    key: str
    trace_id: str
    end_to_end_ms: float
    segment_sum_ms: float
    delta_ms: float
    error_pct: float
    gap_ms: float
    segments: int = 0
    missing_stages: list[str] = field(default_factory=list)
    unresolved_pairs: int = 0
    in_book_within: bool = False
    truncation_bound_ms: float = 0.0
    within_threshold: bool = False
    within_align: bool = False


def build_rows(
    samples_by_trace: Mapping[str, list[StageSample]],
    leg: Leg,
    trace_to_key: Mapping[str, str],
    threshold_pct: float,
    align_pct: float,
) -> tuple[list[RequestRow], list[dict[str, str]], list[dict[str, Any]]]:
    """一题一题算：分母是该题的端到端，分子是同一题的分段加总（嵌套剔除后的加总账）。

    算术不另造：每题都走 ``aggregate_stage_latency(samples, end_to_end_by_trace={trace: e2e})``
    再读它自己的 ``coverage.per_request``，与 ``app/api/v1/observability.py`` 的
    ``_stage_report_from_trace`` 同一道算法 ⇒ 本件的数能与 ``/stage-latency?trace_id=`` 逐枚对账。
    """
    rows: list[RequestRow] = []
    skipped: list[dict[str, str]] = []
    reports: list[dict[str, Any]] = []  # 逐题那份在册报告，合并台账只认它
    for trace_id in sorted(samples_by_trace):
        key = str(trace_to_key.get(trace_id) or trace_id)
        if leg.keyed != "trace":
            skipped.append({"key": key, "trace_id": trace_id, "reason": "leg_not_joinable"})
            continue
        if trace_id not in leg.values:
            skipped.append({"key": key, "trace_id": trace_id, "reason": "no_denominator"})
            continue
        e2e = float(leg.values[trace_id])
        report = aggregate_stage_latency(samples_by_trace[trace_id], end_to_end_by_trace={trace_id: e2e})
        reports.append(report)
        cell = report["coverage"]["per_request"].get(trace_id)
        if cell is None:  # 在册把 <=0 的窗跳过；跟着跳过，但逐枚点名，不静默摘题
            skipped.append({"key": key, "trace_id": trace_id, "reason": "denominator<=0"})
            continue
        ledger_count = sum(int(entry["ledger_count"]) for entry in report["stages"].values())
        unresolved = int(cell["unresolved_overlap_pairs"])
        error_pct = float(cell["coverage_error_pct"])
        rows.append(
            RequestRow(
                key=key,
                trace_id=trace_id,
                end_to_end_ms=float(cell["end_to_end_ms"]),
                segment_sum_ms=float(cell["segment_sum_ms"]),
                delta_ms=round(float(cell["segment_sum_ms"]) - float(cell["end_to_end_ms"]), 6),
                error_pct=error_pct,
                gap_ms=float(cell["gap_ms"]),
                segments=ledger_count,
                missing_stages=list(report["missing_stages"]),
                unresolved_pairs=unresolved,
                in_book_within=bool(cell["within_one_percent"]),
                within_threshold=bool(error_pct < threshold_pct and not unresolved),
                within_align=bool(error_pct < align_pct and not unresolved),
                #: 每枚跨度在 app/trace/spans.py:168 被 int() 地板一次（record_stage_event
                #: :261 同样 int()）：分段系统性偏小，上界＝段数×1 ms，均值约段数×0.5 ms。
                #: 写出来才不会把残差全推给「漏了一段」。
                truncation_bound_ms=round(ledger_count * 1.0, 6),
            )
        )
    return rows, skipped, reports



def merge_ledger(reports: list[dict[str, Any]],
                 samples_by_trace: Mapping[str, list[StageSample]]) -> dict[str, Any]:
    """把逐题报告合成整窗台账：数相加，**时间戳不再跨题比**。

    在册 aggregate_stage_latency 的嵌套剔除是在同一批样本里比区间；把一窗的题全倒进
    同一次调用，并发请求的两枚跨度会因墙上时钟重叠而被当成「嵌套」剔出加总，未决重叠
    也会凭空多出来（10-04 合成样机实测：pooled 一遍 pairs=13／未决=9，逐题相加 0）。
    判据②本来就是逐题主张（见 app/common/stage_timing.py:690 那段注释），所以台账只能
    由逐题报告相加；分位数按整窗每枚样本重算，那是判据①的口径，与区间无关。
    """
    names = sorted({stage for report in reports for stage in report["stages"]})
    stages: dict[str, Any] = {}
    for name in names:
        cells = [report["stages"][name] for report in reports if name in report["stages"]]
        stats = PerformanceStats()
        for members in samples_by_trace.values():
            for sample in members:
                if sample.label_or_stage == name:
                    stats.observe(sample.duration_ms)
        count = sum(int(cell["count"]) for cell in cells)
        stages[name] = {
            "total_ms": round(sum(float(cell["total_ms"]) for cell in cells), 6),
            "ledger_count": sum(int(cell["ledger_count"]) for cell in cells),
            "count": count,
            "excluded_ms": round(sum(float(cell["excluded_ms"]) for cell in cells), 6),
            "p50_ms": round(stats.percentile(0.50), 2) if count else 0,
            "p95_ms": round(stats.percentile(0.95), 2) if count else 0,
        }
    labels: dict[str, int] = {}
    for report in reports:
        for label, hits in (report["unattributed"].get("labels") or {}).items():
            labels[label] = labels.get(label, 0) + int(hits)
    overlap = {
        "pairs": sum(int(report["overlap"]["pairs"]) for report in reports),
        "unresolved_pairs": sum(int(report["overlap"]["unresolved_pairs"]) for report in reports),
        "nested_ms": round(sum(float(report["overlap"]["nested_ms"]) for report in reports), 6),
        "untimed_samples": sum(int(report["overlap"]["untimed_samples"]) for report in reports),
        "measurable": bool(reports) and all(bool(report["overlap"]["measurable"]) for report in reports),
    }
    return {
        "stages": stages,
        "missing_stages": [stage for stage in CANONICAL_STAGES
                           if not stages.get(stage, {}).get("count")],
        "overlap": overlap,
        "unattributed": {
            "count": sum(int(report["unattributed"]["count"]) for report in reports),
            "total_ms": round(sum(float(report["unattributed"]["total_ms"]) for report in reports), 6),
            "labels": labels,
        },
    }


def same_source_verdict(rows: list[RequestRow], e2e: Leg, seg: Leg) -> list[str]:
    """同源判死的两条签名。命中任一 ⇒ 这一窗的比值不可信，本件拒绝给绿灯。"""
    reasons: list[str] = []
    if e2e.name == seg.name or e2e.name == E2E_SEGMENTS:
        reasons.append(
            "声明同源：端到端腿署名 %s，分段腿署名 %s ⇒ 分子就是分母拆出来的一部分，比值恒 0"
            % (e2e.name, seg.name)
        )
    if rows and all(abs(row.delta_ms) < 1e-9 for row in rows):
        reasons.append(
            "恒零差：%d 枚可比题的 |分段加总 - 端到端| 逐位为 0 ⇒ 两把独立的钟不会同时逐位相等，"
            "这是自我复述不是测量" % len(rows)
        )
    return reasons


def client_clock_agreement(primary: Mapping[str, float], other: Mapping[str, float]) -> dict[str, Any]:
    """采集器两本件（wall_ms 与帧账窗）的互证。同一枚钟，只自证一致，不构成第二条独立腿。"""
    common = sorted(set(primary) & set(other))
    diffs = [
        abs(primary[key] - other[key]) / primary[key] * 100.0
        for key in common
        if primary[key] > 0
    ]
    if not diffs:
        return {"common": 0}
    stats = PerformanceStats()
    for value in diffs:
        stats.observe(value)
    return {
        "common": len(common),
        "p50_diff_pct": round(stats.percentile(0.50), 4),
        "p95_diff_pct": round(stats.percentile(0.95), 4),
        "max_diff_pct": round(max(diffs), 4),
    }


# ==================== 读数 ====================


def _load_question_leg(
    kind: str,
    path: Path,
    trace_to_key: Mapping[str, str],
    allow_unjoined: bool,
) -> tuple[Leg, Mapping[str, float]]:
    """按题号索引的腿：读完立刻用 join 换成按 trace_id 索引，换不动就当场说清为什么。"""
    loaded = read_sidecar(path) if kind == E2E_SIDECAR else read_frames(path)
    if not trace_to_key:
        if allow_unjoined:
            return loaded, loaded.values
        raise InputMissing(
            "%s 按题号 id 索引、trace 按 trace_id 索引，而题号不进 trace 事件是在册事实"
            "（app/api/v1/observability.py SLO_BLOCKERS: no request event carries the question）"
            "⇒ 跨钟那条腿要 --join <trace_id,id> 清单；本件不按时序猜配对" % loaded.name
        )
    remapped = {trace: float(loaded.values[key]) for trace, key in trace_to_key.items() if key in loaded.values}
    if not remapped:
        raise InputMissing(
            "join 清单 %d 枚与 %s 的 %d 枚题号交集 0 ⇒ 两条腿连不上，不猜"
            % (len(trace_to_key), loaded.name, len(loaded.values))
        )
    return (
        Leg(loaded.name, loaded.clock, remapped, loaded.paths, loaded.note, "trace",
            loaded.rows_read, loaded.duplicates),
        loaded.values,
    )


def default_names(directory: Path, window: str) -> dict[str, Path]:
    return {
        "sidecar": Path(directory) / ("%s-sidecar.jsonl" % window),
        "frames": Path(directory) / ("%s-sidecar-frames.jsonl" % window),
    }


def collect(
    window: str,
    directory: Path,
    e2e_from: str = "auto",
    traces: Iterable[Path] = (),
    join: Path | None = None,
    sidecar: Path | None = None,
    frames: Path | None = None,
) -> dict[str, Any]:
    """把两条腿摆成一枚可复算的读数结构。读不到就抛，绝不返回半个数冒充测量。"""
    criterion = read_criterion_pct()
    alignment = read_alignment_pct()
    probe_inbook_gate()
    threshold_pct = float(criterion["threshold_pct"])
    align_pct = float(alignment["align_pct"])
    #: 纸上判据与在册刀刃必须重合：探针只能把 app 里那枚 literal 夹进 (0.99, 1.01]，
    #: 纸面若改成 5%% 或 0.1%%，两条判据就分家了 —— 那是口径要重裁，不由本件自取一枚。
    if not KNIFE_PASS_PCT < threshold_pct <= KNIFE_FAIL_PCT:
        raise CaliberError(
            "纸上判据 %s%% 落不进在册刀刃 (0.99, 1.01] ⇒ 跟进单与 app 的门已分家，"
            "本件不自取口径，等总控重裁" % threshold_pct
        )

    names = default_names(directory, window)
    if sidecar is not None:
        names["sidecar"] = Path(sidecar)
    if frames is not None:
        names["frames"] = Path(frames)
    trace_list = [Path(p) for p in traces]
    trace_paths = trace_list or [p for p in default_trace_candidates(Path(directory), window) if p.exists()]

    seg = Leg(SEG_PROVENANCE, SEG_CLOCK, (), (), LEG_NOTES[SEG_PROVENANCE])
    samples_by_trace: dict[str, list[StageSample]] = {}
    windows_from_events: dict[str, float] = {}
    if trace_paths:
        events, used = read_traces(trace_paths)
        seg = Leg(SEG_PROVENANCE, SEG_CLOCK, (), used, LEG_NOTES[SEG_PROVENANCE])
        for sample in samples_from_events(events):
            if sample.trace_id:
                samples_by_trace.setdefault(sample.trace_id, []).append(sample)
        windows_from_events = request_windows_from_events(events)
    trace_to_key = read_join(Path(join)) if join is not None else {}
    join_source = "manifest" if trace_to_key else ""
    if not trace_to_key and trace_paths and Path(names["frames"]).exists():
        #: 没交清单才自己派生，且 frames 件必须在位。派生不出来就退回「要清单」那条判语，
        #: 绝不在这里抛：量不到要说不到（RC_NO_INPUT），不许变成一件没读通的件。
        try:
            trace_to_key = trace_keys_from_events(events, read_frames_sessions(names["frames"]))
        except (InputMissing, OSError):
            trace_to_key = {}
        join_source = "payload.session_id" if trace_to_key else ""

    wanted = e2e_from or "auto"
    if wanted == "auto":
        if names["sidecar"].exists() and trace_to_key:
            wanted = E2E_SIDECAR
        elif windows_from_events:
            wanted = E2E_EVENTS
        elif names["sidecar"].exists():
            wanted = E2E_SIDECAR
        else:
            wanted = E2E_EVENTS

    question_values: Mapping[str, float] = {}
    if wanted == E2E_SEGMENTS:
        leg = Leg(
            E2E_SEGMENTS,
            SEG_CLOCK,
            {trace: round(sum(sample.duration_ms for sample in members), 6)
             for trace, members in samples_by_trace.items()},
            seg.paths,
            LEG_NOTES[E2E_SEGMENTS],
            "trace",
        )
    elif wanted == E2E_SIDECAR:
        leg, question_values = _load_question_leg(
            E2E_SIDECAR, names["sidecar"], trace_to_key, allow_unjoined=not samples_by_trace
        )
    elif wanted == E2E_FRAMES:
        leg, question_values = _load_question_leg(
            E2E_FRAMES, names["frames"], trace_to_key, allow_unjoined=not samples_by_trace
        )
    elif wanted == E2E_EVENTS:
        leg = Leg(E2E_EVENTS, "server", windows_from_events, seg.paths, LEG_NOTES[E2E_EVENTS], "trace")
    else:
        raise InputMissing(
            "认不出的端到端腿：%s（可选 auto / %s / %s / %s / %s）"
            % (wanted, E2E_SIDECAR, E2E_EVENTS, E2E_FRAMES, E2E_SEGMENTS)
        )

    cross = None
    if question_values:
        other_path = names["frames"] if leg.name == E2E_SIDECAR else names["sidecar"]
        other_read = read_frames if leg.name == E2E_SIDECAR else read_sidecar
        try:
            cross = client_clock_agreement(question_values, other_read(other_path).values)
        except (InputMissing, OSError):
            cross = None

    rows, skipped, reports = build_rows(samples_by_trace, leg, trace_to_key, threshold_pct, align_pct)
    untrusted = same_source_verdict(rows, leg, seg)
    all_samples = [sample for members in samples_by_trace.values() for sample in members]

    if not samples_by_trace:
        status = "no_segments"
    elif untrusted:
        status = "untrusted"
    elif not rows:
        status = "no_comparable_request"
    else:
        status = "measured"
    comparable = bool(rows) and not untrusted

    return {
        "schema": "r631.stage-sum-delta/1",
        "window": window,
        "directory": str(directory),
        "status": status,
        "criterion": criterion,
        "alignment": alignment,
        "threshold_pct": threshold_pct,
        "align_pct": align_pct,
        "segment_leg": {
            "name": seg.name,
            "clock": seg.clock,
            "note": seg.note,
            "paths": list(seg.paths),
            "traces": len(samples_by_trace),
            "samples": len(all_samples),
        },
        "e2e_leg": {
            "name": leg.name,
            "clock": leg.clock,
            "note": leg.note,
            "paths": list(leg.paths),
            "requests": len(leg.values),
            "keyed": leg.keyed,
            "rows_read": leg.rows_read,
            "duplicates": list(leg.duplicates),
        },
        "traces_side_windows": len(windows_from_events),
        "trace_files": [str(p) for p in trace_paths],
        "trace_candidates_checked": [str(p) for p in default_trace_candidates(Path(directory), window)],
        "inputs": {name: str(path) for name, path in names.items()},
        "join_size": len(trace_to_key),
        "join_source": join_source,
        "client_clock_agreement": cross,
        "rows": [row.__dict__ for row in sorted(rows, key=lambda item: item.error_pct, reverse=True)],
        "skipped": skipped,
        "untrusted_reasons": untrusted,
        "quantiles": _quantiles(rows) if rows else None,
        "verdict": {
            "gate_pct": threshold_pct,
            "gate_pass": None if not comparable else all(row.within_threshold for row in rows),
            "align_pct": align_pct,
            "align_pass": None if not comparable else all(row.within_align for row in rows),
            "failing_1pct": [row.key for row in rows if not row.within_threshold],
            "failing_align": [row.key for row in rows if not row.within_align],
        },
        "ledger_view": merge_ledger(reports, samples_by_trace),
    }


def _quantiles(rows: list[RequestRow]) -> dict[str, Any]:
    """误差与残差的分位数：用在册同一把最近秩尺（app/common/performance.py），不自立秩规。"""
    errors = PerformanceStats()
    deltas = PerformanceStats()
    for row in rows:
        errors.observe(row.error_pct)
        deltas.observe(abs(row.delta_ms))
    return {
        "count": len(rows),
        "error_p50_pct": round(errors.percentile(0.50), 4),
        "error_p95_pct": round(errors.percentile(0.95), 4),
        "error_p99_pct": round(errors.percentile(0.99), 4),
        "error_average_pct": round(errors.report()["average_ms"], 4),
        "error_max_pct": round(errors.report()["max_ms"], 4),
        "delta_average_ms": round(deltas.report()["average_ms"], 3),
        "delta_max_abs_ms": round(deltas.report()["max_ms"], 3),
    }


def decide_rc(data: dict[str, Any]) -> int:
    """退出码优先级：漂移 > 不可信 > 无货 > <1% FAIL > 对齐 FAIL > 全绿。"""
    if data["untrusted_reasons"]:
        return RC_UNTRUSTED
    if data["status"] in ("no_segments", "no_comparable_request"):
        return RC_NO_INPUT
    verdict = data["verdict"]
    if verdict["gate_pass"] is not True:
        return RC_GATE
    if verdict["align_pass"] is not True:
        return RC_ALIGN
    return RC_OK


# ==================== 印面 ====================


def render(data: dict[str, Any], max_rows: int = 25) -> list[str]:
    #: 印面不硬写退出码：小标题里的数必须与末行同源（同一优先级算出来）。
    rc = decide_rc(data)
    out = ["# R631 —— 端到端 对 分段加总 的逐题误差（窗：%s）" % data["window"], ""]
    out.append("- 判据线：现读 %s 第 %d 行（LF）⇒ < %s%%。原文：%s" % (
        Path(data["criterion"]["doc"]).name, data["criterion"]["line_lf"],
        data["threshold_pct"], data["criterion"]["raw"][:120]))
    align = data["alignment"]
    out.append("- 对齐线：现读 %s 第 %d 行 ⇒ %s%%（它自己两枚数复算 %s%%：%ss vs %ss）" % (
        Path(align["doc"]).name, align["line_lf"], align["align_pct"], align["computed_pct"],
        align["end_to_end_s"], align["sum_s"]))
    segment = data["segment_leg"]
    e2e = data["e2e_leg"]
    out.append("- 分段腿真源：%s ｜ 钟 %s ｜ trace %d 枚 / 跨度 %d 枚 ｜ 件：%s" % (
        segment["name"], segment["clock"], segment["traces"], segment["samples"],
        ", ".join(segment["paths"]) or "（无）"))
    out.append("- 端到端腿真源：%s ｜ 钟 %s ｜ 读数 %d 枚（按 %s 索引）｜ 件：%s" % (
        e2e["name"], e2e["clock"], e2e["requests"], e2e["keyed"], ", ".join(e2e["paths"]) or "（无）"))
    out.append("- 这条对照的强度：%s" % e2e["note"])
    if e2e.get("duplicates"):
        out.append("- 🔴 同题多枚（取 attempt 最大那枚，其余不静默丢）：题号 %d 枚已点名 ⇒ %s" % (
            len(e2e["duplicates"]), ", ".join(e2e["duplicates"][:20])))
        out.append("  （这件读了 %d 行、连出 %d 枚题号；行数与枚数不等就是这一格）" % (
            e2e["rows_read"], e2e["requests"]))
    if data["join_size"]:
        out.append("- join 来源：%s ｜ %d 枚 trace_id→题号（题号进不了 trace 是在册事实；session_id 进，orchestrator.py:1502 那几枚载荷带着它）" % (
            data["join_source"] or "?", data["join_size"]))
    if data["client_clock_agreement"] and data["client_clock_agreement"].get("common"):
        cell = data["client_clock_agreement"]
        out.append("- 采集器两本件互证（同钟，不作第二条腿）：共 %d 题 ｜ wall_ms 对帧账窗 p50=%s%% p95=%s%% 最大=%s%%" % (
            cell["common"], cell["p50_diff_pct"], cell["p95_diff_pct"], cell["max_diff_pct"]))
    out.append("")

    if data["untrusted_reasons"]:
        out.append("## 🔴 判「不可信」（退出码 %d）" % RC_UNTRUSTED)
        for reason in data["untrusted_reasons"]:
            out.append("- %s" % reason)
        out.append("- 本件不给 PASS／FAIL：这种绿不需要改一行代码就能永远拿到。")
        out.append("")

    if data["status"] == "no_segments":
        out.append("## 量不到：分段腿无货（退出码 %d —— 这不是 PASS）" % rc)
        out.append("- 分段跨度只在持久化 trace 事件里（``*.finished`` 的 ``payload.duration_ms``）；")
        out.append("  盘上三份产物一件都没有这枚字段（现读取证纸：docs/perf/r631-stage-sum-delta-2026-10-04.md）。")
        out.append("- 本件在 %s 找过这些分段腿件名：%s" % (
            data["directory"], ", ".join(data["trace_candidates_checked"])))
        out.append("- 端到端腿（%s）读数 %d 枚在位 —— 有分母没分子，比值算不出来。" % (
            e2e["name"], e2e["requests"]))
        out.append("- 要出数需要：① 一枚窗的 trace 事件导出（``--traces``）；② 要跨钟那条还要 ``--join``。")
        out.append("")
        return out

    if data["status"] == "no_comparable_request":
        out.append("## 量不到：一题都对不上（退出码 %d）" % rc)
        out.append("- 分段 trace %d 枚 ｜ 端到端读数 %d 枚 ｜ 可比 0 枚。逐枚原因（上限 20）：%s" % (
            segment["traces"], e2e["requests"],
            ", ".join("%s(%s)" % (item["key"], item["reason"]) for item in data["skipped"][:20])))
        out.append("")
    else:
        quantiles = data["quantiles"]
        rows = data["rows"]
        out.append("## 逐题误差（n=%d，分子＝该题分段加总，分母＝该题端到端）" % quantiles["count"])
        out.append("- 误差分位数：p50=%s%% ｜ p95=%s%% ｜ p99=%s%% ｜ 最大=%s%% ｜ 均值=%s%%" % (
            quantiles["error_p50_pct"], quantiles["error_p95_pct"], quantiles["error_p99_pct"],
            quantiles["error_max_pct"], quantiles["error_average_pct"]))
        out.append("- 残差绝对值：均值=%s ms ｜ 最大=%s ms（gap_ms 为正＝分段没吃满端到端，为负＝分段超出）" % (
            quantiles["delta_average_ms"], quantiles["delta_max_abs_ms"]))
        out.append("")
        out.append("| 题号 | trace | 端到端 ms | 分段加总 ms | 误差 % | 残差 ms | 加总段数 | int 地板界 ms | 该题未现段 |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for row in rows[:max_rows]:
            out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                row["key"], (row["trace_id"] or "-")[:12], row["end_to_end_ms"], row["segment_sum_ms"],
                row["error_pct"], row["gap_ms"], row["segments"], row["truncation_bound_ms"],
                ",".join(row["missing_stages"]) or "-"))
        if len(rows) > max_rows:
            out.append("| …另 %d 枚（--max-rows 或 --json 全倒） | | | | | | | | |" % (len(rows) - max_rows))
        out.append("")
        worst = rows[0]
        out.append("- 最大误差题逐枚点名（前 %d）：%s" % (
            min(10, len(rows)), ", ".join("%s=%s%%" % (row["key"], row["error_pct"]) for row in rows[:10])))
        out.append("- 最大一枚 = %s ｜ 端到端 %s ms ｜ 分段加总 %s ms ｜ 误差 %s%% ｜ 该题 int 地板界 %s ms" % (
            worst["key"], worst["end_to_end_ms"], worst["segment_sum_ms"], worst["error_pct"],
            worst["truncation_bound_ms"]))
        if data["skipped"]:
            out.append("- 🔴 未参与对照（逐枚点名，上限 20）：%s" % ", ".join(
                "%s(%s)" % (item["key"], item["reason"]) for item in data["skipped"][:20]))
        out.append("")

    verdict = data["verdict"]
    out.append("## 两条线各判一次")

    def word(flag: Any) -> str:
        return "PASS" if flag is True else ("FAIL" if flag is False else "不判（无可用读数）")

    out.append("- < %s%%（跟进单在册判据，另需该题零未决重叠）：%s" % (verdict["gate_pct"], word(verdict["gate_pass"])))
    if verdict["failing_1pct"]:
        out.append("  - FAIL 题号逐枚点名（上限 20）：%s" % ", ".join(verdict["failing_1pct"][:20]))
    out.append("- < %s%%（对齐 latency-budget 那格的 0.03%%）：%s" % (
        verdict["align_pct"], word(verdict["align_pass"])))
    if verdict["failing_align"]:
        out.append("  - FAIL 题号逐枚点名（上限 20）：%s" % ", ".join(verdict["failing_align"][:20]))
    out.append("")

    ledger = data["ledger_view"]
    out.append("## 分段账（在册加总口径，嵌套已剔）")
    for name, cell in sorted(ledger["stages"].items()):
        out.append("- %s：total=%s ms ｜ 加总段数=%s ｜ 剔除嵌套=%s ms ｜ p50=%s ｜ p95=%s" % (
            name, cell["total_ms"], cell["ledger_count"], cell["excluded_ms"], cell["p50_ms"], cell["p95_ms"]))
    out.append("- 整窗未出现的段：%s" % (", ".join(ledger["missing_stages"]) or "无"))
    overlap = ledger["overlap"]
    out.append("- 重叠：pairs=%s ｜ 未决=%s ｜ 嵌套剔除=%s ms ｜ 无时间戳样本=%s ｜ 逐题均可量=%s" % (
        overlap["pairs"], overlap["unresolved_pairs"], overlap["nested_ms"],
        overlap["untimed_samples"], overlap["measurable"]))
    out.append("- 未归段：count=%s ｜ total=%s ms ｜ 标签=%s" % (
        ledger["unattributed"]["count"], ledger["unattributed"]["total_ms"],
        json.dumps(ledger["unattributed"]["labels"], ensure_ascii=False)[:160]))
    out.append("")
    out.append("> 🔴 本格只摆数并宣告可信／不可信；判 G-R51-1 绿不绿的权在总控。")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R631：端到端 对 分段加总 的逐题误差尺（只读、离线、零模型、零容器、零 PG）",
        epilog="退出码语义：\n" + "\n".join("  %d = %s" % (code, EXIT_CODE_MEANING[code])
                                           for code in sorted(EXIT_CODE_MEANING))
                + "\n优先级：漂移(5) > 不可信(4) > 无货(3) > <判据线(1) > 对齐线(2) > 全绿(0)。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--window", required=True, help="窗名，例：run18 / run20k")
    parser.add_argument("--dir", default=os.path.join(tempfile.gettempdir(), "evalrun"),
                        help="仓外产物目录（默认 %%TEMP%%%%evalrun）")
    parser.add_argument("--e2e-from", default="auto",
                        choices=["auto", E2E_SIDECAR, E2E_EVENTS, E2E_FRAMES, E2E_SEGMENTS],
                        help="端到端腿真源；segments 是故意留的同源自证枚（选它必然判不可信）")
    parser.add_argument("--traces", action="append", default=[],
                        help="分段腿原料：trace 事件件或目录（可多枚）；缺省按 <window>-traces.jsonl 找")
    parser.add_argument("--join", default="", help="trace_id→题号 清单（JSONL/JSON 数组）；跨钟那条腿要用")
    parser.add_argument("--sidecar", default="", help="覆盖 sidecar 件路径")
    parser.add_argument("--frames", default="", help="覆盖 frames 件路径")
    parser.add_argument("--max-rows", type=int, default=25, help="表格里最多摆几枚（判语仍按全量）")
    parser.add_argument("--json", action="store_true", help="整个读数倒成 JSON")
    args = parser.parse_args(argv)

    try:
        data = collect(
            window=args.window,
            directory=Path(args.dir),
            e2e_from=args.e2e_from,
            traces=args.traces,
            join=Path(args.join) if args.join else None,
            sidecar=Path(args.sidecar) if args.sidecar else None,
            frames=Path(args.frames) if args.frames else None,
        )
    except CaliberError as exc:
        print("🔴 口径漂移（RC=%d）：%s" % (RC_CALIBER, exc))
        return RC_CALIBER
    except InputMissing as exc:
        print("🔴 量不到（RC=%d）：%s" % (RC_NO_INPUT, exc))
        return RC_NO_INPUT

    rc = decide_rc(data)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in render(data, max_rows=args.max_rows):
            print(line)
    print("\n退出码：%d ｜ %s" % (rc, EXIT_CODE_MEANING[rc]))
    return rc


__all__ = [
    "CaliberError",
    "InputMissing",
    "RequestRow",
    "build_rows",
    "client_clock_agreement",
    "collect",
    "decide_rc",
    "default_trace_candidates",
    "main",
    "probe_inbook_gate",
    "read_alignment_pct",
    "read_criterion_pct",
    "read_frames",
    "_collect_by_key",
    "read_join",
    "read_sidecar",
    "read_traces",
    "render",
    "merge_ledger",
    "read_frames_sessions",
    "same_source_verdict",
    "trace_keys_from_events",
]


if __name__ == "__main__":
    raise SystemExit(main())