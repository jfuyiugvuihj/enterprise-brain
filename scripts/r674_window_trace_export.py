#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""R674 —— 真机窗「按题 trace 事件件」的导出器（治 R51② 那一格的**根本没有可测的输入**）。

## 本件补的是哪一格

判据原文（跟进单 R51）：① 分类/改写/检索/生成/反思各段 P50/P95 可查；② 端到端与分段加总误差
<1%。10-05 总控现取的病形：scripts/r631_stage_sum_delta.py 对 run22／run23 各交 rc=3＝量不到；
scripts/r636_stage_coverage.py 喂在册历史事件件虽取到 trace 与跨度，但五段全缺、可比 0 枚。
⇒ 判据 ② 不是「测出来不达标」，是**没有按题的输入**。本件先把输入落盘，再谈误差。

## 形状契约（一枚件三种身份，逐行自足）

    docs/perf/raw/<窗号>/<窗号>-traces.jsonl        （判据 1 点名的那一枚）

逐行 = 一**枚在册 trace 事件行**（键名见 app/trace/schema.py::TRACE_TABLE_COLUMNS 的 trace_events
那一格），再挂三件本单加的字段：question_id（按题归位）、stage_windows（五段各自的起止时刻）、
missing_stages（这一发缺哪几段）。r631 的 read_traces()／samples_from_events() 只认它自己那几个键，
多出来的键一律被忽略 ⇒ 同一枚件同时是：

    --traces 分段腿原料   ／   --join trace_id→题号 清单   ／   判据 1 的按题账

一件两种行形状（app/common/stage_timing.py::FINISHED_EVENTS 之外的 event_type 一律被 r631 跳过）：

    r674.shot.detail        一发一行凭据本体：整本跨度账（逐枚 started/completed/duration）
    r674.question.no_events 一题一枚事件都没落时的那点名行：五段一律 null，缺段照样进母集

🔴 **缺段一律交 None 并点名，绝不补 0、绝不补「估计值」**（判据 1 的红字）。抹掉某一段 ⇒ 本件非零
退出并点名那一段（反证牙的负向）；每一发五段齐 ⇒ rc=0。桥接不出任何题号 ⇒ rc=4 且**不写件**——
一枚没有题号的件冒充「按题件」比没有件更坏。

## 原料从哪来（默认全离线；连库那一腿出厂即关）

    --events PATH...        在册事件件（文件或目录），离线首选
    --journal PATH          遗留 fallback journal（app/trace/store.py 里 TRACE_STORE_PATH 那一格）
    --from-postgres         真窗的 trace 其实在 PG：只发 SELECT，且会话先
                            SET default_transaction_read_only = on，姿势照
                            scripts/audit_r160_department_columns.py::psql_readonly；
                            还要 R674_WINDOW_EXPORT_PG=on 才允许连——两枚闸缺一即拒绝连库

题号桥（trace_id → 题号）三级优先：--join 显式清单 ＞ 事件载荷里的 session_id ×
<窗号>-sidecar-frames.jsonl ＞ 交回 rc=4 点名缺哪一枚。端到端腿只从 <窗号>-sidecar.jsonl 的
wall_ms 取（一行一发，R643 口径），取不到即 None——**不拿服务端事件窗冒充客户钟**。

## 用法

    python scripts/r674_window_trace_export.py --window run30 --events <事件件>
    python scripts/r674_window_trace_export.py --window run30 --from-postgres
    python scripts/r674_window_trace_export.py --window run30 --dir <产物目录> --out <路径> --no-shadow

夜窗队列按 `--window <窗号>` 直呼本件（scripts/night1006_queue.py::readout 的 r674* 通配那一格），
所以缺省值必须能走：缺省产物目录 = %TEMP%\evalrun，缺省件位 = docs/perf/raw/<窗号>/<窗号>-traces.jsonl，
缺省还往产物目录投一枚**逐字节相同**的影子件——r631 的缺省 --dir 就在那儿找 <窗号>-traces.jsonl。

退出码（语义与印面同源）：
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文与箭头会当场炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
SCHEMA = "r674.window-trace/1"

#: 退出码语义写死（epilog 同文）。3 与 scripts/r631_stage_sum_delta.py 的 RC_NO_INPUT 同义：
#: 「量不到」在两把尺上是同一个数，账面不分裂。
RC_OK = 0
RC_IO = 1
RC_MISSING_STAGE = 3
RC_NO_INPUT = 4
RC_CONTRACT = 5

EXIT_CODE_MEANING = {
    RC_OK: "件已落盘，且每一发五段齐全（可直接喂 r631）",
    RC_IO: "写盘失败（目录不可建／路径不可写）",
    RC_MISSING_STAGE: "件已落盘，但逐枚点名了缺段／缺跨度时刻——判据① 的那一段今天没有货",
    RC_NO_INPUT: "量不到：原料读不到，或一枚题号都桥不出来 ⇒ 不写件（绝不写半枚假件）",
    RC_CONTRACT: "形状不合在册契约：事件行没有 trace_id／载荷不是对象／段窗没有跨度撑着",
}

#: 缺省产物目录＝夜窗采集器写字的那一格（与 r631／r636 同一处，不另立口径）。
DEFAULT_ARTIFACT_DIR = Path(os.getenv("EVALRUN_DIR") or (Path(tempfile.gettempdir()) / "evalrun"))
RAW_DIR = REPO / "docs" / "perf" / "raw"

#: 一题一枚事件都没有时写的那一行形状：r631 认不出它（正好——它不是跨度，是点名）。
NO_EVENTS_EVENT_TYPE = "r674.question.no_events"

#: 每一发一行的凭据本体（逐枚跨度的 record 级账挂在这里）。判据 1 要求「逐行至少含
#: question_id／trace_id／五段各自的起止时刻」——那是十枚时刻，不是整本跨度账；把跨度账
#: 抄到每一行会让一扇窗的件胀到几十 MB 再压进 git。所以一枚件两种行形状：
#: 事件行＝在册事件本体 + 十枚起止时刻；这一枚＝该发的完整凭据。
#: r631 对认不出的 event_type 一律跳过（FINISHED_EVENTS 那一格），两种行都不会污染它的分子。
SHOT_DETAIL_EVENT_TYPE = "r674.shot.detail"

#: PG 那一腿的两枚闸：开关 + 显式旗标，缺一即拒绝连库（出厂即关，同 scripts/r648_real_pg_gauge.py）。
PG_OPT_IN_ENV = "R674_WINDOW_EXPORT_PG"
TRUE_VALUES = {"1", "true", "yes", "on"}
READ_ONLY_SQL_PREFIX = "SET default_transaction_read_only = on"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
WINDOW_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class NoInput(RuntimeError):
    """原料读不到／桥不出题号 —— 量不到，绝不编数，也绝不写半枚件。"""


class ContractError(RuntimeError):
    """递进来的东西形状不对 —— 本件拒绝出数。"""


@dataclass
class Shot:
    """一发＝一题的一次尝试，握着自己的 trace、事件、端到端与五段窗。

    R643 的教训写在这枚形状里：分母是**这一发**的，同题多发不许折叠成一枚。
    """

    question_id: str
    trace_id: str
    session_id: str = ""
    attempt: int = 1
    ts: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    end_to_end_ms: float | None = None
    end_to_end_source: str = ""
    stage_windows: dict[str, Any] = field(default_factory=dict)
    missing_stages: list[str] = field(default_factory=list)
    unattributed_samples: int = 0

    def minimal_windows(self) -> dict[str, Any]:
        """逐行自足的那份拷贝：每段只留起止时刻（判据 1 的字面要求），缺的段一律 None。"""
        minimal: dict[str, Any] = {}
        for name, window in self.stage_windows.items():
            if not window:
                minimal[str(name)] = None
                continue
            minimal[str(name)] = {"started_at": window.get("started_at"),
                                  "completed_at": window.get("completed_at")}
        return minimal

    def as_fields(self) -> dict[str, Any]:
        """事件行与点名行共用的头部：十枚起止时刻在这里，整本跨度账在 detail 行。"""
        return {
            "schema": SCHEMA,
            "question_id": self.question_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "attempt": self.attempt,
            "ts": self.ts,
            "end_to_end_ms": self.end_to_end_ms,
            "end_to_end_source": self.end_to_end_source,
            "stage_windows": self.minimal_windows(),
            "missing_stages": list(self.missing_stages),
            "unattributed_samples": self.unattributed_samples,
        }

# ==================== 原料：事件行 ====================


def _json_rows(path: Path) -> list[dict[str, Any]]:
    """一枚件里的 JSON 行（.jsonl 逐行／.json 允许整本数组）；读不通即点名，不静默跳行。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise NoInput("%s 是空件 ⇒ 分段腿无货" % path)
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NoInput("%s 自称 JSON 数组但读不通：%s" % (path, exc)) from exc
        if not isinstance(loaded, list):
            raise ContractError("%s 的顶层不是数组 ⇒ 事件件形状不合契约" % path)
        rows = [row for row in loaded if isinstance(row, dict)]
        if not rows:
            raise NoInput("%s 的数组里没有一枚对象 ⇒ 分段腿无货" % path)
        return rows
    rows = []
    for position, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise NoInput("%s 第 %d 行读不通：%s" % (path, position, exc)) from exc
        if isinstance(row, dict):
            rows.append(row)
    if not rows:
        raise NoInput("%s 里没有一枚可读的 JSON 行 ⇒ 分段腿无货" % path)
    return rows


def event_files(target: Path) -> list[Path]:
    """目录＝逐枚 .jsonl/.json 合并；文件＝它自己。与 r631 的 _event_files 同语义。"""
    target = Path(target)
    if target.is_dir():
        found = sorted(item for item in target.rglob("*") if item.suffix in {".jsonl", ".json"} and item.is_file())
        if not found:
            raise NoInput("%s 目录下没有 .jsonl/.json 可当 trace 事件" % target)
        return found
    if not target.exists():
        raise NoInput("trace 事件件不存在：%s" % target)
    return [target]


def normalize_event_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """把 trace_events 行／journal 行归一成 r631 replay() 交回的那本形状（键名一字不差）。

    在册地址：app/trace/run_reader.py::TraceDatabase._as_event。本件不另立契约：
    created_at 只当 timestamp 的别名收，payload 是字符串时解一次。
    """
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ContractError("事件行的 payload 不是对象：%r" % (payload,))
    stamp = row.get("timestamp")
    if stamp in (None, ""):
        stamp = row.get("created_at")
    trace_id = str(row.get("trace_id") or "").strip()
    if not trace_id:
        raise ContractError("事件行没有 trace_id ⇒ 分段腿无从归位：%s" % (json.dumps(row, ensure_ascii=False)[:160],))
    return {
        "trace_id": trace_id,
        "request_id": str(row.get("request_id") or ""),
        "task_id": str(row.get("task_id") or ""),
        "sequence": row.get("sequence"),
        "timestamp": stamp,
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or ""),
        "owner_id": str(row.get("owner_id") or ""),
        "payload": payload,
    }


def read_event_rows(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    used: list[str] = []
    for target in paths:
        for path in event_files(Path(target)):
            rows = _json_rows(path)
            events.extend(normalize_event_row(row) for row in rows)
            used.append(str(Path(path).resolve()))
    if not events:
        raise NoInput("一枚事件都没读到 ⇒ 分段腿无货")
    return events, used


# ==================== 在册识别器（懒 import，零产品路由面） ====================

_RECOGNIZER: Any = None


def load_recognizer() -> Any:
    """现读 app/common/stage_timing 那一枚模块对象：五段名单与跨度识别器都在它身上。

    为什么懒：本件的模块级不许把产品 import 图拖进来（离线牙的形状照
    tests/test_r132_contract_followup_sync.py）。为什么不手抄名单：CANONICAL_STAGES 改一次
    本件就得跟着改一次，抄一份等于再埋一枚同形状的雷。
    """
    global _RECOGNIZER
    if _RECOGNIZER is not None:
        return _RECOGNIZER
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        import app.common.stage_timing as stage_timing  # 只读：stdlib + app/common/performance
    except Exception as exc:  # pragma: no cover - 环境坏了要说出来，不许静默交空表
        raise ContractError("读不到 app/common/stage_timing ⇒ 五段名单没有真源：%s" % exc) from exc
    _RECOGNIZER = stage_timing
    return stage_timing


def canonical_stages() -> tuple[str, ...]:
    return tuple(load_recognizer().CANONICAL_STAGES)


def samples_for(events: Sequence[Mapping[str, Any]]) -> list[Any]:
    """把这一发的事件折成在册跨度样本：与 r631 的分子同一道算法，不另立识别器。"""
    return list(load_recognizer().samples_from_events(list(events)))


def to_epoch_ms(value: Any) -> float | None:
    return load_recognizer().to_epoch_ms(value)


def _iso(ms: float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, timezone.utc).isoformat()


# ==================== 原料：窗产物（题号桥 + 端到端腿） ====================


def artifact_names(artifact_dir: Path, window: str) -> dict[str, Path]:
    """窗号→四枚路径的唯一口径：正部件、影子件、sidecar、frames。"""
    directory = Path(artifact_dir)
    return {
        "sidecar": directory / ("%s-sidecar.jsonl" % window),
        "frames": directory / ("%s-sidecar-frames.jsonl" % window),
        "shadow": directory / ("%s-traces.jsonl" % window),
        "out": RAW_DIR / window / ("%s-traces.jsonl" % window),
    }


def read_frames_rows(path: Path) -> list[dict[str, Any]]:
    """<窗>-sidecar-frames.jsonl：一行一发，握 {id, session_id, attempt, ts}。"""
    bridges: list[dict[str, Any]] = []
    for row in _json_rows(path):
        key = str(row.get("id") or row.get("question_id") or "").strip()
        if not key:
            continue
        bridges.append({"question_id": key, "session_id": str(row.get("session_id") or "").strip(),
                        "attempt": _attempt_of(row), "ts": str(row.get("ts") or "").strip()})
    return bridges


def read_join_manifest(path: Path) -> dict[str, str]:
    """显式 trace_id→题号 清单（键名次序与 r631::read_join 一致：id／question_id／eval_id）。"""
    mapping: dict[str, str] = {}
    for row in _json_rows(path):
        trace_id = str(row.get("trace_id") or "").strip()
        key = str(row.get("id") or row.get("question_id") or row.get("eval_id") or "").strip()
        if trace_id and key:
            mapping[trace_id] = key
    if not mapping:
        raise NoInput("%s 里没有一枚 {trace_id, 题号} ⇒ join 清单是空的" % path)
    return mapping


def read_sidecar_shots_index(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    """客户钟逐发索引：按 (题号, 第几发) 收 wall_ms 与它自己的 ts，绝不按题号折叠（R643 教训）。

    行照收哪怕 wall_ms 缺失或非正 —— 那一行仍然带着这一发的 ts 身份，摘掉它就等于
    悄悄把一发从母集里删了；缺读数的发在件里交回 None 并点名，不补 0。
    """
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for row in _json_rows(path):
        key = str(row.get("id") or row.get("question_id") or "").strip()
        if not key:
            continue
        wall = row.get("wall_ms")
        value = None
        if not isinstance(wall, bool) and isinstance(wall, (int, float)) and float(wall) > 0:
            value = round(float(wall), 6)
        index[(key, _attempt_of(row))] = {"wall_ms": value, "ts": str(row.get("ts") or "").strip()}
    return index


def _attempt_of(row: Mapping[str, Any]) -> int:
    raw = row.get("attempt")
    try:
        value = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        return 1
    return value if value > 0 else 1


def trace_sessions(events: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], list[str]]:
    """trace_id → session_id：只认载荷里那一枚 session_id（request.started 就带着它）。"""
    mapping: dict[str, str] = {}
    ambiguous: list[str] = []
    for row in events:
        trace_id = str(row.get("trace_id") or "")
        session = str((row.get("payload") or {}).get("session_id") or "").strip()
        if not trace_id or not session:
            continue
        known = mapping.get(trace_id)
        if known is None:
            mapping[trace_id] = session
        elif known != session and trace_id not in ambiguous:
            ambiguous.append(trace_id)
    return mapping, ambiguous

# ==================== 五段窗 ====================


def stage_windows_from_samples(samples: Sequence[Any], canonical: Sequence[str]) -> tuple[dict[str, Any], list[str], int]:
    """逐段交回「起止时刻＋它自己的凭据」，缺的段交 None 并点名。

    🔴 这里没有一寸估算：段窗只由该段**真发过的跨度**的 started_at/completed_at 取外沿；
    一枚跨度只要缺任一枚时刻就不参与外沿，并进 samples_without_timings —— 宁可乐成 null，
    也不把「没量到」写成 0 ms。samples 逐枚原样带出，读数对不上时可以一路追到那一枚事件。
    """
    windows: dict[str, Any] = {}
    missing: list[str] = []
    unattributed = 0
    for name in canonical:
        members = [sample for sample in samples if str(getattr(sample, "stage", "") or "") == name]
        if not members:
            windows[name] = None
            missing.append(str(name))
            continue
        pairs = [(to_epoch_ms(getattr(sample, "started_at", None)),
                  to_epoch_ms(getattr(sample, "completed_at", None))) for sample in members]
        timed = [(start, end) for start, end in pairs if start is not None and end is not None]
        durations = [float(sample.duration_ms) for sample in members
                     if isinstance(getattr(sample, "duration_ms", None), (int, float))
                     and not isinstance(getattr(sample, "duration_ms", None), bool)]
        windows[name] = {
            "started_at": _iso(min(value[0] for value in timed)) if timed else None,
            "completed_at": _iso(max(value[1] for value in timed)) if timed else None,
            "span_ms": round(max(value[1] for value in timed) - min(value[0] for value in timed), 6) if timed else None,
            "sum_duration_ms": round(sum(durations), 6) if durations else None,
            "sample_count": len(members),
            "samples_without_timings": len(members) - len(timed),
            "window_basis": "outermost_of_samples" if timed else "no_timing_on_any_sample",
            "samples": [{
                "started_at": getattr(sample, "started_at", None),
                "completed_at": getattr(sample, "completed_at", None),
                "duration_ms": getattr(sample, "duration_ms", None),
                "source": getattr(sample, "source", ""),
                "tool_name": getattr(sample, "tool_name", ""),
                "label": getattr(sample, "label", ""),
                "worker": getattr(sample, "worker", ""),
            } for sample in members],
        }
    for sample in samples:
        if str(getattr(sample, "stage", "") or "") not in canonical:
            unattributed += 1
    return windows, missing, unattributed


# ==================== 组一发一题 ====================


def _sole_or_indexed(index: Mapping[tuple[str, int], Mapping[str, Any]], question: str,
                     pair: tuple[str, int]) -> dict[str, Any] | None:
    """先按 (题号, 第几发) 直取；取不到且**该题只有这一发**才用那一发。

    同题多发时绝不挑一枚装作看见——那是 R643 治过的折叠病，本件宁可交 None 并点名。
    """
    row = index.get(pair)
    if row is not None:
        return dict(row)
    members = [value for (name, _attempt), value in index.items() if name == question]
    return dict(members[0]) if len(members) == 1 else None


def plan_shots(events: Sequence[Mapping[str, Any]], *, artifact_dir: Path, window: str,
               join: Path | None = None, canonical: Sequence[str] = (),
               questions: Sequence[str] = ()) -> dict[str, Any]:
    """把事件按题归位：显式清单 ＞ 载荷 session_id × frames 件 ＞ 交回「桥不出来」（不写件）。"""
    names = artifact_names(Path(artifact_dir), window)
    trace_to_key: dict[str, str] = {}
    attempts_by_trace: dict[str, int] = {}
    bridge_source = ""
    sessions: dict[str, str] = {}
    ambiguous_sessions: list[str] = []

    if join is not None:
        trace_to_key = read_join_manifest(Path(join))
        bridge_source = "manifest"
    if not trace_to_key:
        sessions, ambiguous_sessions = trace_sessions(events)
        if names["frames"].exists() and sessions:
            by_session: dict[str, dict[str, Any]] = {}
            for row in read_frames_rows(names["frames"]):
                if row["session_id"]:
                    by_session.setdefault(row["session_id"], row)
            for trace_id, session in sessions.items():
                row = by_session.get(session)
                if row:
                    trace_to_key[trace_id] = row["question_id"]
                    attempts_by_trace[trace_id] = int(row["attempt"])
            if trace_to_key:
                bridge_source = "payload.session_id+frames"

    sidecar_present = names["sidecar"].exists()
    sidecar_index: dict[tuple[str, int], dict[str, Any]] = {}
    if sidecar_present:
        sidecar_index = read_sidecar_shots_index(names["sidecar"])
    frames_index: dict[tuple[str, int], dict[str, Any]] = {}
    if names["frames"].exists():
        for row in read_frames_rows(names["frames"]):
            frames_index.setdefault((row["question_id"], int(row["attempt"])), row)

    by_trace: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        by_trace.setdefault(str(row["trace_id"]), []).append(dict(row))
    for members in by_trace.values():
        members.sort(key=lambda item: (str(item.get("timestamp") or ""), int(item.get("sequence") or 0)))

    wanted = sorted({str(item).strip() for item in questions if str(item).strip()})
    known = sorted(set(trace_to_key.values()) | set(wanted))
    if not known:
        raise NoInput(
            "桥不出任何题号 ⇒ 不写件。窗 %s 缺的是这几枚原料：frames 件 %s（在位=%s）、"
            "sidecar 件 %s（在位=%s）；事件里带 session_id 的 trace 共 %d 枚，一件都没桥到题号上。"
            "也可用 --join <trace_id→题号清单> 直接交名单。"
            % (window, names["frames"], names["frames"].exists(), names["sidecar"], sidecar_present,
               len(sessions)))

    session_by_question: dict[str, str] = {}
    for trace_id, session in sessions.items():
        question = trace_to_key.get(trace_id)
        if question:
            session_by_question.setdefault(question, session)

    shots: list[Shot] = []
    for question in known:
        traces = sorted(trace_id for trace_id, key in trace_to_key.items() if key == question)
        if not traces:
            absent = Shot(question_id=question, trace_id="",
                          session_id=session_by_question.get(question, ""), attempt=1)
            absent.stage_windows = {str(name): None for name in canonical}
            absent.missing_stages = [str(name) for name in canonical]
            absent.end_to_end_source = "absent"
            shots.append(absent)
            continue
        for trace_id in traces:
            members = by_trace.get(trace_id, [])
            shot = Shot(question_id=question, trace_id=trace_id,
                        session_id=sessions.get(trace_id, ""),
                        attempt=attempts_by_trace.get(trace_id, 1), events=members)
            windows, missing, unattributed = stage_windows_from_samples(samples_for(members), canonical)
            shot.stage_windows = windows
            shot.missing_stages = missing
            shot.unattributed_samples = unattributed
            pair = (question, shot.attempt)
            side = _sole_or_indexed(sidecar_index, question, pair)
            frame = _sole_or_indexed(frames_index, question, pair)
            #: ts 带上件本体：r631 的 read_join_identities 就认这一格（发级身份的第三条桥），
            #: 不带它，同题多发就只能靠 session 或「该题只有一发」认领，多发那一格今天会退成不可信。
            shot.ts = str((side or {}).get("ts") or (frame or {}).get("ts") or "")
            wall = (side or {}).get("wall_ms")
            if wall is not None:
                shot.end_to_end_ms = float(wall)
                shot.end_to_end_source = "sidecar_wall_ms"
            elif not sidecar_present:
                shot.end_to_end_source = "sidecar_absent"
            else:
                shot.end_to_end_source = "wall_ms_absent_or_nonpositive"
            shots.append(shot)

    return {
        "shots": shots,
        "bridge_source": bridge_source,
        "denominator_source": "sidecar_wall_ms" if sidecar_present else "sidecar_absent",
        "traces_with_events": len(by_trace),
        "traces_attributed": len(trace_to_key),
        "unattributed_traces": sorted(trace_id for trace_id in by_trace if trace_id not in trace_to_key),
        "ambiguous_sessions": ambiguous_sessions,
        "names": names,
        "question_names": known,
    }

# ==================== 覆盖面账 ====================


def coverage_of(shots: Sequence[Shot], canonical: Sequence[str]) -> dict[str, Any]:
    """逐段读数：几题几发带着这一段，加上该段跨度的 P50/P95（判据① 点名的就是这两枚）。

    P50/P95 用在册那一把最近秩尺（app/common/performance.py::PerformanceStats，经
    app/common/stage_timing 转交），不自立秩规；缺段的题号逐枚点名，上限 20 枚。
    """
    recognizer = load_recognizer()
    questions = {shot.question_id for shot in shots if shot.question_id}
    per_stage: dict[str, Any] = {}
    for name in canonical:
        durations: list[float] = []
        for shot in shots:
            window = (shot.stage_windows or {}).get(name)
            if not window:
                continue
            for sample in window.get("samples") or []:
                value = sample.get("duration_ms")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    durations.append(float(value))
        holder = recognizer.PerformanceStats()
        for value in durations:
            holder.observe(value)
        missing_questions = sorted({shot.question_id for shot in shots
                                    if not (shot.stage_windows or {}).get(name)})
        per_stage[str(name)] = {
            "questions_present": len(questions) - len(missing_questions),
            "questions_total": len(questions),
            "shots_present": sum(1 for shot in shots if (shot.stage_windows or {}).get(name)),
            "shots_total": len(shots),
            "samples": len(durations),
            "p50_ms": round(holder.percentile(0.50), 2) if durations else None,
            "p95_ms": round(holder.percentile(0.95), 2) if durations else None,
            "missing_questions": missing_questions[:20],
        }
    return {
        "questions": len(questions),
        "shots": len(shots),
        "stages": per_stage,
        "stages_absent_window_wide": [str(name) for name in canonical
                                      if not per_stage[str(name)]["shots_present"]],
        "end_to_end_missing": sorted({shot.question_id for shot in shots
                                      if shot.end_to_end_ms is None})[:20],
    }


def assert_no_invented_timings(rows: Sequence[Mapping[str, Any]], canonical: Sequence[str]) -> None:
    """自检（判据 1 红字反着钉）：段窗非空却没有一枚跨度撑着 ⇒ 那是编出来的 ⇒ 当场拒写。"""
    for row in rows:
        if row.get("event_type") not in (SHOT_DETAIL_EVENT_TYPE, NO_EVENTS_EVENT_TYPE):
            continue  # 事件行只带十枚起止时刻，凭据本体在 detail 行——自检只认凭据本体
        windows = row.get("stage_window_details") or {}
        for name in canonical:
            window = windows.get(str(name))
            if window is None:
                continue
            if not isinstance(window, dict):
                raise ContractError("%s 段窗不是对象：%r" % (name, window))
            if int(window.get("sample_count") or 0) <= 0:
                raise ContractError("题 %s 的 %s 段窗带着读数却没有一枚跨度（sample_count=%s）⇒ 拒绝写件"
                                    % (row.get("question_id"), name, window.get("sample_count")))
            if window.get("sum_duration_ms") is None:
                raise ContractError("题 %s 的 %s 段窗没有加总读数 ⇒ 这是半枚数，拒绝写件"
                                    % (row.get("question_id"), name))


# ==================== 落件 ====================


def shot_ledger_row(shot: Shot, window: str) -> dict[str, Any]:
    """一发一行凭据本体：整本跨度账（含逐枚起止与时长）挂在这一枚上。

    一题一枚事件都没落时，同一枚形状改成点名行（NO_EVENTS_EVENT_TYPE）：五段一律 None，
    缺哪几段照旧逐枚点名——它仍在母集里，不被摘掉（同 r636 的「母集＝账本」纪律）。
    """
    fields = shot.as_fields()
    fields["window"] = window
    absent = not shot.events
    return {
        **fields,
        "request_id": "", "task_id": "", "sequence": 0, "timestamp": None,
        "event_type": NO_EVENTS_EVENT_TYPE if absent else SHOT_DETAIL_EVENT_TYPE,
        "status": "absent" if absent else "ledger",
        "owner_id": "", "payload": {},
        "stage_window_details": shot.stage_windows,
        "sample_count": sum(int((value or {}).get("sample_count") or 0)
                            for value in shot.stage_windows.values()),
        "events": len(shot.events),
        "reason": ("本窗没有一枚事件落在这道题的 trace 上（五段一律 null，不补 0，也不补估计值）"
                   if absent else ""),
    }


def export_rows(shots: Sequence[Shot], window: str) -> list[dict[str, Any]]:
    """一发一行凭据 + 该发逐枚事件各一行（事件行自带十枚起止时刻，逐行自足）。"""
    rows: list[dict[str, Any]] = []
    for shot in shots:
        rows.append(shot_ledger_row(shot, window))
        fields = shot.as_fields()
        fields["window"] = window
        for event in shot.events:
            rows.append({**fields, **event})
    return rows


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    payload = text.encode("utf-8")
    path.write_bytes(payload)
    return len(payload)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def write_export(out: Path, rows: Sequence[Mapping[str, Any]], *, shadow: Path | None) -> dict[str, Any]:
    """正本落 docs/perf/raw/<窗号>/；影子件落窗产物目录（r631 的缺省 --dir 在那儿找件）。"""
    try:
        payload_bytes = write_jsonl(Path(out), rows)
    except OSError as exc:
        raise SystemExit("%d 写盘失败：%s（%s）" % (RC_IO, out, exc))
    readout = {
        "path": str(Path(out).resolve()),
        "rows": len(rows),
        "bytes": payload_bytes,
        "sha256": sha256_of(Path(out)),
    }
    if shadow is not None:
        try:
            write_jsonl(Path(shadow), rows)
        except OSError as exc:
            raise SystemExit("%d 写盘失败：%s（%s）" % (RC_IO, shadow, exc))
        readout["shadow_path"] = str(Path(shadow).resolve())
        readout["shadow_sha256"] = sha256_of(Path(shadow))
        readout["shadow_identical"] = readout["shadow_sha256"] == readout["sha256"]
        if not readout["shadow_identical"]:
            raise ContractError("影子件与正本逐字节不同 ⇒ 两把尺会读两本账，拒绝交件")
    return readout


# ==================== PG 腿（出厂即关，两枚闸） ====================


def psql_jsonl(docker_bin: str, container: str, user: str, database: str, sql: str) -> str:
    """只读 psql：会话先 default_transaction_read_only = on，再发 SELECT。

    姿势的在册真源＝scripts/audit_r160_department_columns.py::psql_readonly（同一道命令形状）。

    🔴 R721：psql 会把 -c SET 的命令标签 SET 打到标准输出，混进这一腿的逐行 JSON 读数面，
    本件按契约逐行 json.loads ⇒ 第一行就撞墙（现取 rc=5）。-q 只关命令标签，一条 SELECT 的口径没动。
    """
    argv = [docker_bin, "exec", container, "psql", "-U", user, "-d", database, "-At", "-q",
            "-v", "ON_ERROR_STOP=1", "-c", READ_ONLY_SQL_PREFIX, "-c", sql]
    completed = subprocess.run(argv, capture_output=True, check=False)
    if completed.returncode != 0:
        raise NoInput("psql 只读腿失败 rc=%s：%s" % (completed.returncode,
                                                    completed.stderr.decode("utf-8", "replace")[:300]))
    return completed.stdout.decode("utf-8", "replace")


def select_for_sessions(sessions: Sequence[str]) -> str:
    """按窗产物的 session 名单取该窗全部事件；每一枚先过形状闸，绝不把任意串拼进语句。"""
    cleaned: list[str] = []
    for session in sessions:
        text = str(session or "").strip()
        if not text:
            continue
        if not SESSION_ID_RE.match(text):
            raise ContractError("session_id 形状不合契约，拒绝进 SQL：%r" % session)
        if text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        raise NoInput("窗产物的 frames 件里一枚 session_id 都没有 ⇒ PG 腿无从过滤")
    quoted = ", ".join("'%s'" % item for item in cleaned)
    return (
        "SELECT row_to_json(t)::text FROM ("
        " SELECT e.trace_id, e.request_id, e.task_id, e.sequence, e.event_type, e.status,"
        " e.owner_id, e.payload, e.created_at"
        " FROM trace_events e WHERE e.trace_id IN"
        " (SELECT a.trace_id FROM agent_runs a WHERE a.session_id IN (%s))"
        " ORDER BY e.trace_id, e.sequence) t" % quoted
    )


def read_events_from_postgres(*, artifact_dir: Path, window: str, docker_bin: str,
                              container: str, user: str, database: str,
                              opt_in: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    declared = (opt_in if opt_in is not None else os.getenv(PG_OPT_IN_ENV, "")).strip().lower()
    if declared not in TRUE_VALUES:
        raise NoInput("PG 腿出厂即关：连真库须同时给 --from-postgres 与 %s=on（现读 %s=%r）"
                      % (PG_OPT_IN_ENV, PG_OPT_IN_ENV, declared))
    frames = artifact_names(Path(artifact_dir), window)["frames"]
    if not frames.exists():
        raise NoInput("PG 腿要按 session 名单过滤，但 frames 件不在位：%s" % frames)
    sessions = [str(row["session_id"]) for row in read_frames_rows(frames) if row["session_id"]]
    output = psql_jsonl(docker_bin, container, user, database, select_for_sessions(sessions))
    rows: list[dict[str, Any]] = []
    for position, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ContractError("psql 第 %d 行不是 JSON（只读腿交回的不是件本体）：%s" % (position, line[:120])) from exc
    if not rows:
        raise NoInput("PG 腿对这扇窗交回 0 枚事件（session 名单 %d 枚）⇒ 量不到" % len(sessions))
    return [normalize_event_row(row) for row in rows], ["postgres:%s:trace_events" % container]

# ==================== 组装 ====================


def collect(window: str, *, artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
            event_paths: Sequence[Path] = (), join: Path | None = None,
            journal: Path | None = None, from_postgres: bool = False,
            docker_bin: str = "docker", container: str = "enterprise-brain-postgres-1",
            user: str = "postgres", database: str = "enterprise_brain",
            questions_file: Path | None = None, pg_opt_in: str | None = None) -> dict[str, Any]:
    """读原料 → 按题归位 → 逐段读数 → 交回一枚可复算的读数结构（读不到就抛，绝不返回半个数）。"""
    if not WINDOW_NAME_RE.match(str(window or "")):
        raise ContractError("窗号形状不合契约（不许路径分隔符与空白）：%r" % window)
    canonical = canonical_stages()
    used: list[str] = []
    events: list[dict[str, Any]] = []
    sources = [Path(item) for item in event_paths]
    if journal is not None:
        sources.append(Path(journal))
    if from_postgres:
        rows, paths = read_events_from_postgres(artifact_dir=Path(artifact_dir), window=window,
                                                docker_bin=docker_bin, container=container,
                                                user=user, database=database, opt_in=pg_opt_in)
        events.extend(rows)
        used.extend(paths)
    if sources:
        rows, paths = read_event_rows(sources)
        events.extend(rows)
        used.extend(paths)
    if not events:
        raise NoInput("分段腿无货：既没有 --events/--journal 件，也没开 PG 腿（窗 %s）" % window)

    questions: list[str] = []
    if questions_file is not None:
        questions = [str(row.get("id") or row.get("question_id") or "").strip()
                     for row in _json_rows(Path(questions_file))]
        questions = [item for item in questions if item]

    planned = plan_shots(events, artifact_dir=Path(artifact_dir), window=window, join=join,
                         canonical=canonical, questions=questions)
    shots: list[Shot] = planned["shots"]
    rows = export_rows(shots, window)
    assert_no_invented_timings(rows, canonical)
    coverage = coverage_of(shots, canonical)
    return {
        "schema": SCHEMA,
        "window": window,
        "canonical_stages": [str(name) for name in canonical],
        "recognizer": "app/common/stage_timing.py::samples_from_events",
        "event_sources": used,
        "events": len(events),
        "bridge_source": planned["bridge_source"],
        "denominator_source": planned["denominator_source"],
        "traces_with_events": planned["traces_with_events"],
        "traces_attributed": planned["traces_attributed"],
        "unattributed_traces": planned["unattributed_traces"],
        "ambiguous_sessions": planned["ambiguous_sessions"],
        "shots": len(shots),
        "shots_complete": sum(1 for shot in shots if not shot.missing_stages),
        "questions": coverage["questions"],
        "rows": len(rows),
        "missing_by_stage": {name: cell["missing_questions"] for name, cell in coverage["stages"].items()
                             if cell["shots_present"] < cell["shots_total"]},
        "coverage": coverage,
        "fully_covered": bool(shots) and not any(shot.missing_stages for shot in shots),
        "export_rows": rows,
        "default_out": str(planned["names"]["out"]),
        "shadow_out": str(planned["names"]["shadow"]),
    }


# ==================== 印面 ====================


def readout_lines(data: Mapping[str, Any], written: Mapping[str, Any] | None, rc: int) -> list[str]:
    out = ["# R674 —— 按题 trace 事件件导出（窗：%s）" % data["window"], ""]
    out.append("- 五段名单真源：%s ⇒ %s" % (data["recognizer"], ", ".join(data["canonical_stages"])))
    out.append("- 事件原料：%s（读到 %d 枚事件，覆盖 %d 枚 trace，桥到题号 %d 枚 trace）" % (
        ", ".join(data["event_sources"]) or "（无）", data["events"],
        data["traces_with_events"], data["traces_attributed"]))
    out.append("- 题号桥：%s ｜ 端到端腿：%s ｜ 母集 %d 题 / %d 发 ｜ 五段齐的发数 %d ｜ 行数 %d" % (
        data["bridge_source"] or "🔴 桥不出来", data["denominator_source"],
        data["questions"], data["shots"], data["shots_complete"], data["rows"]))
    if data["unattributed_traces"]:
        out.append("- 🔴 没归到题号的 trace（逐枚点名，上限 20）：%s" % ", ".join(
            trace[:18] for trace in data["unattributed_traces"][:20]))
    if data["ambiguous_sessions"]:
        out.append("- 🔴 一枚 trace 挂着多枚 session：%s" % ", ".join(
            trace[:18] for trace in data["ambiguous_sessions"][:20]))
    out.append("")
    out.append("## 五段覆盖率逐段读数（缺的段一律 null——本件不补 0，也不补估计值）")
    out.append("| 段 | 题 present/total | 发 present/total | 跨度枚数 | P50 ms | P95 ms | 缺段题号（上限 10） |")
    out.append("|---|---|---|---|---|---|---|")
    for name in data["canonical_stages"]:
        cell = data["coverage"]["stages"][name]
        out.append("| %s | %d/%d | %d/%d | %s | %s | %s | %s |" % (
            name, cell["questions_present"], cell["questions_total"],
            cell["shots_present"], cell["shots_total"], cell["samples"],
            "—" if cell["p50_ms"] is None else cell["p50_ms"],
            "—" if cell["p95_ms"] is None else cell["p95_ms"],
            ", ".join(cell["missing_questions"][:10]) or "无"))
    out.append("")
    if written:
        out.append("- 落件：%s ｜ %d 行 ｜ %d 字节 ｜ sha256=%s" % (
            written["path"], written["rows"], written["bytes"], written["sha256"][:16]))
        if written.get("shadow_path"):
            out.append("- 影子件：%s ｜ 与正本逐字节相同（sha256=%s）" % (
                written["shadow_path"], written.get("shadow_sha256", "")[:16]))
        out.append("- 喂回 r631（同一枚件两用）：`python scripts/r631_stage_sum_delta.py --window %s "
                   "--traces %s --join %s`" % (data["window"], written["path"], written["path"]))
    else:
        out.append("- 本轮未落件（--dry-run）")
    out.append("")
    if data["fully_covered"]:
        out.append("- ✅ 每一发五段齐全 —— 判据① 点名的段名单今天全有货")
    else:
        out.append("- 🔴 缺段点名（判据① 今天量不到的就是这些）：%s" % ", ".join(
            "%s（缺 %d 发）" % (name, data["shots"] - data["coverage"]["stages"][name]["shots_present"])
            for name in data["canonical_stages"]
            if data["coverage"]["stages"][name]["shots_present"] < data["shots"]))
        absent = data["coverage"]["stages_absent_window_wide"]
        if absent:
            out.append("- 🔴 整窗零货的段：%s" % ", ".join(absent))
    if data["coverage"]["end_to_end_missing"]:
        out.append("- 🔴 端到端腿缺读数的题（上限 10，wall_ms 没进件 ⇒ 不拿服务端窗冒充）：%s" % ", ".join(
            data["coverage"]["end_to_end_missing"][:10]))
    out.append("")
    out.append("> 🔴 本件只落原料与覆盖面点名；判 G-R51-1 绿不绿的权在总控（口径同 r631／r636）。")
    out.append("退出码：%d ｜ %s" % (rc, EXIT_CODE_MEANING[rc]))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R674：真机窗按题 trace 事件导出器（离线为主，连库那一腿出厂即关）",
        epilog="退出码语义：\n" + "\n".join("  %d = %s" % (code, EXIT_CODE_MEANING[code])
                                           for code in sorted(EXIT_CODE_MEANING)),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--window", required=True, help="窗名，例：run30")
    parser.add_argument("--dir", default=str(DEFAULT_ARTIFACT_DIR),
                        help="窗产物目录（缺省 %%TEMP%%\\evalrun，与 r631／r636 同一处）")
    parser.add_argument("--events", action="append", default=[], help="事件原料件或目录（可多枚）")
    parser.add_argument("--journal", default="", help="遗留 fallback journal 件（只读取用）")
    parser.add_argument("--join", default="", help="trace_id→题号 显式清单；不给就自己派生")
    parser.add_argument("--questions", default="", help="本窗题号名单件（点名「一题都没落」的那几枚）")
    parser.add_argument("--out", default="", help="落件位（缺省 docs/perf/raw/<窗号>/<窗号>-traces.jsonl）")
    parser.add_argument("--no-shadow", dest="shadow", action="store_false",
                        help="不往窗产物目录投影子件（投了 r631 的缺省 --window 才找得到件）")
    parser.add_argument("--from-postgres", action="store_true",
                        help="走 PG 只读腿取真窗事件；还须 %s=on，两枚闸缺一即拒绝连库" % PG_OPT_IN_ENV)
    parser.add_argument("--docker-bin", default="docker")
    parser.add_argument("--container", default="enterprise-brain-postgres-1")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--database", default="enterprise_brain")
    parser.add_argument("--dry-run", action="store_true", help="只出读数与点名，不落件")
    parser.add_argument("--json", action="store_true", help="把读数倒成 JSON（不含逐行件本体）")
    args = parser.parse_args(argv)

    try:
        data = collect(
            args.window,
            artifact_dir=Path(args.dir),
            event_paths=[Path(item) for item in args.events],
            join=Path(args.join) if args.join else None,
            journal=Path(args.journal) if args.journal else None,
            from_postgres=args.from_postgres,
            docker_bin=args.docker_bin, container=args.container,
            user=args.user, database=args.database,
            questions_file=Path(args.questions) if args.questions else None,
        )
    except NoInput as exc:
        print("🔴 量不到（RC=%d）：%s" % (RC_NO_INPUT, exc))
        return RC_NO_INPUT
    except ContractError as exc:
        print("🔴 形状不合契约（RC=%d）：%s" % (RC_CONTRACT, exc))
        return RC_CONTRACT

    rows = data.pop("export_rows")
    rc = RC_OK if data["fully_covered"] else RC_MISSING_STAGE
    written = None
    if not args.dry_run:
        out = Path(args.out) if args.out else Path(data["default_out"])
        written = write_export(out, rows, shadow=Path(data["shadow_out"]) if args.shadow else None)

    if args.json:
        payload = dict(data)
        payload["written"] = written
        payload["exit_code"] = rc
        payload["exit_code_meaning"] = EXIT_CODE_MEANING[rc]
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in readout_lines(data, written, rc):
            print(line)
    return rc


__all__ = [
    "ContractError", "NoInput", "Shot", "artifact_names", "assert_no_invented_timings",
    "canonical_stages", "collect", "coverage_of", "event_files", "export_rows",
    "load_recognizer", "main", "normalize_event_row", "plan_shots", "psql_jsonl",
    "read_event_rows", "read_events_from_postgres", "read_frames_rows",
    "read_join_manifest", "read_sidecar_shots_index", "readout_lines", "samples_for",
    "select_for_sessions", "shot_ledger_row", "stage_windows_from_samples", "trace_sessions",
    "write_export", "write_jsonl",
]


if __name__ == "__main__":
    raise SystemExit(main())
