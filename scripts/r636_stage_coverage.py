# -*- coding: utf-8 -*-
r"""R636 —— G-R51-1 第四格的**覆盖面账**：逐枚点名「哪一段今天进得来、哪一段进不来、进不来是哪一型」。

只读、离线、零模型、零容器、零 PG、零连库。原料 = R631 同一本三件（只读，不重导）：
    分段腿    %TEMP%\evalrun\<window>-traces.jsonl
    端到端腿  %TEMP%\evalrun\<window>-sidecar.jsonl（wall_ms，按题号索引）
    桥        %TEMP%\evalrun\<window>-sidecar-frames.jsonl（session_id ↔ 题号）

===== 这单欠的从来不是「再量一次误差」=====
R631 已把误差量出来了（三窗 status=measured、rc=1、<1% 与 <0.03% 两条线全 FAIL，
failing_1pct 枚数 = 母集枚数）。账面见 docs/perf/r631-stage-sum-delta-2026-10-04.md §11。
本件要交的是**为什么 FAIL** 的逐枚账：每题每一段，缺的那段属于哪一型，凭据是谁。

===== 三型（判据②要的正是这三型，且每型必须有凭据）=====
    A no_event            该题这枚 trace 里，一个能名这段的事件都没发
    B unrecognized_event  事件发了，但 app/common/stage_timing.py::samples_from_events() 不认它
    C nested_excluded     认了，却被嵌套/重叠判定剔出加总，这一题该段进账 0 ms
A 型再分四形（明写，不许含糊）：
    a0 path_not_taken        这道腿这一题根本没跑
    a1 call_site_no_identity 调用点不带 config ⇒ 跨度没身份 ⇒ 一个字节都不落
    a2 leg_has_no_span       这条腿的码里压根没有跨度这回事
    a3 event_on_sibling_trace 事件确实发了，但发在**另一枚 trace_id** 上（孤儿 trace）

===== 三条纪律长在这件里=====
① 与 R631 逐枚对账：本件的每题「端到端 ms／分段进账 ms／段数／缺段清单／未决重叠」必须与
   scripts/r631_stage_sum_delta.py 现跑读数逐枚相等；对不上即 RC_MISMATCH 点名，不静默差。
   为此本件只读地 import 那件（不改它一个字）。
② 母集＝账本：窗里每一枚 trace_id 都必须落进四组之一（有分母有跨度／有跨度无分母／
   有分母无跨度／两者都无），少点名一枚即 RC_UNIVERSE。no_denominator 不许悄悄摘掉。
③ 凭据承重：每一条归因都带 evidence（文件::符号 ＋ 现读取数）。型 C 尤其——要写「被剔除」
   就必须拿得出该题自己那份报告里的 excluded_count/pairs；拿不出即 RC_EVIDENCE。

===== 反证刀怎么咬（tests/test_r636_stage_coverage.py 逐枚驱动）=====
    (a) recognizer 注入一枚「把某段认成不认」的假尺 → 本件复算的分段加总必与 R631 现跑数对不上
        → RC_MISMATCH；
    (b) omit_groups 里摘掉 no_denominator → 母集与账本枚数当场不相等 → RC_UNIVERSE；
    (c) 把一道「没发事件」的缺失手写成型 C 且不附剔除凭据 → validate_claims 必拒 → RC_EVIDENCE。

===== 用法 =====
    python scripts/r636_stage_coverage.py --window run18
    python scripts/r636_stage_coverage.py --window run18 --window run19 --window run20k --json
    python scripts/r636_stage_coverage.py --window r636demo --dir C:\path\to\synth --json
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文与箭头会当场炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.common.stage_timing import (  # noqa: E402  —— 纯算术件，零 PG 探针（与 R631 同口径）
    CANONICAL_STAGES,
    REQUEST_TERMINAL_EVENTS,
    StageSample,
    aggregate_stage_latency,
    samples_from_events,
)

R631_FILE = REPO / "scripts" / "r631_stage_sum_delta.py"
APP_ROOT = REPO / "app"

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_UNIVERSE = 2
EXIT_NO_INPUT = 3
EXIT_EVIDENCE = 4
EXIT_DERIVED = 5

EXIT_CODE_MEANING = {
    EXIT_OK: "账全：逐枚与 R631 对得上、母集＝账本、每条归因有凭据（这不等于判据②翻绿）",
    EXIT_MISMATCH: "与 R631 现跑读数对不上（本件的复算不成立）",
    EXIT_UNIVERSE: "母集不诚实：有 trace 没进账，或账里多/少了组",
    EXIT_NO_INPUT: "量不到：原料缺失或读不通，绝不编数",
    EXIT_EVIDENCE: "归因没凭据（含把缺失手写成型 C 而拿不出剔除读数）",
    EXIT_DERIVED: "派生尺自证失败：AST 读不到在册形状，或 AST 与在册常量分家",
}

TYPE_IN_LEDGER = "in_ledger"
TYPE_NO_EVENT = "no_event"
TYPE_UNRECOGNIZED = "unrecognized_event"
TYPE_NESTED_OUT = "nested_excluded"
MISSING_TYPES = (TYPE_NO_EVENT, TYPE_UNRECOGNIZED, TYPE_NESTED_OUT)

SHAPE_PATH_NOT_TAKEN = "a0_path_not_taken"
SHAPE_NO_IDENTITY = "a1_call_site_no_identity"
SHAPE_NO_SPAN = "a2_leg_has_no_span"
SHAPE_SIBLING_TRACE = "a3_event_on_sibling_trace"
NO_EVENT_SHAPES = (SHAPE_PATH_NOT_TAKEN, SHAPE_NO_IDENTITY, SHAPE_NO_SPAN, SHAPE_SIBLING_TRACE)

#: 四组母集（判据③：一枚都不许掉）。
GROUP_ASKED = "asked"                  # 有分母 + 有跨度 → R631 的 rows
GROUP_NO_DENOM = "no_denominator"      # 有跨度、无分母 → R631 的 skipped
GROUP_RESUMED_HEAD = "resumed_head"    # 有分母、零跨度 → R631 既不列 rows 也不列 skipped
GROUP_BARE = "bare_trace"              # 两者都无
UNIVERSE_GROUPS = (GROUP_ASKED, GROUP_NO_DENOM, GROUP_RESUMED_HEAD, GROUP_BARE)

#: 未登记而带时长的两本账（型 B 的形状来源）。事件名不在硬编码清单里凭空写：
#: 发射点由 source_facts/AST 现证，证不到就当这条形状不存在（宁缺不编）。
LEG_ACCOUNT_SPECS = (
    {"event_type": "retrieval.completed", "stage": "retrieve", "duration_path": "duration_ms",
     "witness": {"key": "rewrite_count", "stage": "rewrite"}},
    {"event_type": "step.finished", "stage": "generate", "duration_path": "summary.duration_ms"},
)


class MismatchError(RuntimeError):
    """本件的复算与 R631 现跑读数对不上。"""


class UniverseError(RuntimeError):
    """母集与账本枚数不相等 —— 有人被悄悄摘掉或多点。"""


class EvidenceError(RuntimeError):
    """归因没凭据，或凭据现读不到它声称的那一笔读数。"""


class DerivedError(RuntimeError):
    """派生尺读不到在册形状（AST 层面），或与 import 进来的常量分家。"""


class InputMissing(RuntimeError):
    """原料不在／读不通。"""

# ==================== 派生尺：从源码 AST 读在册形状（零 import 产品路由面） ====================


def _parse(path: Path) -> ast.Module:
    if not Path(path).exists():
        raise DerivedError("派生尺要读的源码件不存在：%s" % path)
    try:
        return ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        raise DerivedError("%s 解析失败 ⇒ %s" % (path, exc)) from exc


def _module_constants(path: Path, names: Iterable[str]) -> dict[str, Any]:
    """只读模块顶层赋值里的字面常量（literal_eval）。不 import，因此零 Postgres 探针。

    ``app/common/stage_timing.py`` 那几枚常量是**带注解的赋值**（AnnAssign），
    两种赋值节点都得读，否则派生尺会以为在册没有这枚常量。
    """
    wanted = set(names)
    found: dict[str, Any] = {}
    for node in _parse(path).body:
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError) as exc:
                    raise DerivedError("%s::%s 不是字面量，派生尺不猜（%s）" % (path, target.id, exc))
    missing = sorted(wanted - set(found))
    if missing:
        raise DerivedError("%s 里读不到常量：%s" % (path, ", ".join(missing)))
    return found


def _symbol_index(tree: ast.Module) -> list[tuple[int, int, str]]:
    """(起始行, 结束行, 函数名) 升序表：给任意 lineno 找回它所属的文件内符号。"""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.lineno, getattr(node, "end_lineno", node.lineno), node.name))
    return sorted(out)


def _symbol_at(index: list[tuple[int, int, str]], lineno: int) -> str:
    best = None
    for start, end, name in index:
        if start <= lineno <= end:
            if best is None or (end - start) <= (best[1] - best[0]):
                best = (start, end, name)
    return best[2] if best else "<module>"


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in Path(root).rglob("*.py") if p.is_file())


def identityless_model_sites(app_root: Path = APP_ROOT) -> list[dict[str, str]]:
    """``_make_model(档位).invoke/stream(...)`` 里**不带 config** 的调用点，逐枚点名。

    在册因果链（这就是「该段永远不产分段账」的机器可判定形状）：
    ``app/agents/nodes.py::_ResilientModel._span`` 把 config 交给 ``app/trace/spans.py::span_identity``
    → ``app/trace/spans.py::ExecutionSpan.active`` 要 owner_id 与 trace_id 同时非空
    → ``ExecutionSpan.record`` 与 ``ExecutionSpan._observe_stage`` 都在 ``not self.active`` 时直接 return。
    ⇒ 调用点不传 config 的那一发，``*.finished`` 事件与 R51 分段样本**一个字节都不落**。
    """
    sites: list[dict[str, str]] = []
    for path in _py_files(app_root):
        tree = _parse(path)
        index = _symbol_index(tree)
        rel = path.relative_to(app_root.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in {"invoke", "stream"}):
                continue
            inner = func.value
            if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                    and inner.func.id == "_make_model"):
                continue
            has_config = any(keyword.arg == "config" for keyword in node.keywords)
            if has_config:
                continue
            sites.append({
                "file_symbol": "%s::%s" % (rel, _symbol_at(index, node.lineno)),
                "tier": ast.unparse(inner.args[0]) if inner.args else "?",
                "method": func.attr,
                "passes_config": "False",
            })
    return sorted(sites, key=lambda row: row["file_symbol"])


def call_sites_of(name: str, root: Path = APP_ROOT) -> list[str]:
    """``app/**`` 里以 ``name(...)`` 出现的调用点（函数名或属性名都算），返回 文件::符号 清单。

    只扫 ``app/**``：tests／scripts 里的调用点不算产品道 —— 「record_stage_event 有没有人用」
    这一问，问的是产品码。
    """
    hits: list[str] = []
    for path in _py_files(root):
        tree = _parse(path)
        index = _symbol_index(tree)
        rel = path.relative_to(root.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else "")
            if called == name:
                hits.append("%s::%s" % (rel, _symbol_at(index, node.lineno)))
    return sorted(set(hits))


def module_uses_symbols(module_file: str, symbols: Sequence[str], repo: Path = REPO) -> dict[str, bool]:
    """一个模块是否碰过这些符号（import 名／属性名／裸文本都算），用于证「这条腿没有跨度」。"""
    path = repo / module_file
    tree = _parse(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {alias.name for alias in node.names}
            if node.module:
                names.add(node.module)
        elif isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return {symbol: (symbol in names or symbol in text) for symbol in symbols}


def _imported_tables() -> dict[str, Any]:
    from app.common import stage_timing as _timing  # 纯算术件；本件用它只做「AST 没抄错」的对照

    return {
        "CANONICAL_STAGES": tuple(_timing.CANONICAL_STAGES),
        "FINISHED_EVENTS": dict(_timing.FINISHED_EVENTS),
        "REQUEST_TERMINAL_EVENTS": set(_timing.REQUEST_TERMINAL_EVENTS),
        "TIER_TO_STAGE": dict(_timing.TIER_TO_STAGE),
        "TOOL_TO_STAGE": dict(_timing.TOOL_TO_STAGE),
        "WORKER_TO_STAGE": dict(_timing.WORKER_TO_STAGE),
        "SUPERVISOR_STAGE": _timing.SUPERVISOR_STAGE,
    }


def source_facts(app_root: Path = APP_ROOT, stage_timing_file: Path | None = None) -> dict[str, Any]:
    """带记忆化的入口：同一枚 app_root 的 AST 扫描只做一次（见 _source_facts_uncached）。"""
    key = (str(Path(app_root).resolve()), None if stage_timing_file is None else str(Path(stage_timing_file).resolve()))
    if key in _FACTS_CACHE:
        return _FACTS_CACHE[key]
    facts = _source_facts_uncached(app_root, stage_timing_file)
    _FACTS_CACHE[key] = facts
    return dict(facts)


_FACTS_CACHE: dict[tuple[str, str | None], dict[str, Any]] = {}


def _source_facts_uncached(app_root: Path = APP_ROOT, stage_timing_file: Path | None = None) -> dict[str, Any]:
    """把在册形状一次读全：五段、认账的事件名、三张映射表，外加三条「不产账」的现证。

    两处对照任一失配即 DerivedError：派生尺与在册常量分家时，本件所有归因都失去意义。
    """
    timing_file = stage_timing_file or (app_root / "common" / "stage_timing.py")
    constants = _module_constants(
        timing_file,
        ("CANONICAL_STAGES", "FINISHED_EVENTS", "REQUEST_TERMINAL_EVENTS", "TIER_TO_STAGE",
         "TOOL_TO_STAGE", "WORKER_TO_STAGE", "SUPERVISOR_STAGE"),
    )
    imported = _imported_tables()
    drift = sorted(key for key, value in constants.items()
                   if (set(value) if isinstance(value, (dict, tuple, list)) else value)
                   != (set(imported[key]) if isinstance(imported[key], (dict, tuple, list, set)) else imported[key]))
    if drift:
        raise DerivedError("AST 读到的常量与 import 进来的在册常量分家：%s" % ", ".join(drift))
    emitters = {spec["event_type"]: emitter_symbols_for_event(spec["event_type"], app_root)
                for spec in LEG_ACCOUNT_SPECS}
    return {
        "canonical_stages": tuple(constants["CANONICAL_STAGES"]),
        "finished_events": dict(constants["FINISHED_EVENTS"]),
        "tier_to_stage": dict(constants["TIER_TO_STAGE"]),
        "tool_to_stage": dict(constants["TOOL_TO_STAGE"]),
        "worker_to_stage": dict(constants["WORKER_TO_STAGE"]),
        "supervisor_stage": constants["SUPERVISOR_STAGE"],
        "identityless_model_sites": identityless_model_sites(app_root),
        "record_stage_event_call_sites": call_sites_of("record_stage_event", app_root.parent / "app"),
        "model_handler_span_symbols": module_uses_symbols(
            "app/common/model_handler.py",
            ("start_model_call", "start_tool_call", "ExecutionSpan", "record_stage_event",
             "app.trace.spans"),
        ),
        "leg_account_emitters": emitters,
    }


def stage_of_unregistered_payload(payload: Mapping[str, Any], facts: Mapping[str, Any]) -> str:
    """一枚**未被在册尺认账**的事件载荷，按在册三张表该归到哪一段（归不出交空串）。

    顺序照抄 app/common/stage_timing.py::classify_stage 的规则（显式 label → tool → tier → worker），
    表体本身来自 source_facts 的 AST 读数，不在本件里重造第二套映射。
    """
    body = payload or {}
    label = str(body.get("stage") or "").strip().lower()
    if label in facts["canonical_stages"]:
        return label
    tool = str(body.get("tool_name") or "").strip()
    if tool:
        return facts["tool_to_stage"].get(tool, "")
    tier_key = str(body.get("model_tier") or "").strip().lower().removeprefix("modeltier.")
    if tier_key:
        worker = str(body.get("worker") or "").strip()
        if tier_key == "analysis" and not worker:
            return facts["supervisor_stage"]
        return facts["tier_to_stage"].get(tier_key, "")
    return facts["worker_to_stage"].get(str(body.get("worker") or "").strip(), "")


def unregistered_stage_of(row: Mapping[str, Any], facts: Mapping[str, Any]) -> tuple[str, float | None]:
    """一枚**不在 FINISHED_EVENTS 里**的事件：它归哪一段、带不带时长。归不出交 ("", None)。

    两条路：注册在 LEG_ACCOUNT_SPECS 的账型（retrieval.completed＝检索腿、step.finished＝worker 腿）
    优先，其余按在册三张表（tool/tier/worker）现读。都不命中就不许硬派一段。
    """
    event_type = str(row.get("event_type") or "")
    payload = row.get("payload") or {}
    for spec in LEG_ACCOUNT_SPECS:
        if event_type == spec["event_type"]:
            stage = spec["stage"]
            duration = duration_from_payload(payload, spec["duration_path"])
            if duration is None:
                for path in ("duration_ms", "summary.duration_ms"):
                    duration = duration_from_payload(payload, path)
                    if duration is not None:
                        break
            return stage, duration
    if event_type in facts["finished_events"] or event_type in facts_request_terminals(facts):
        return "", None
    stage = stage_of_unregistered_payload(payload, facts)
    duration = duration_from_payload(payload, "duration_ms") or duration_from_payload(
        payload, "summary.duration_ms")
    return stage, duration


def unregistered_accounts(trace_rows: Sequence[Mapping[str, Any]],
                          facts: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """按段汇总「发了但在册尺不认」的账：枚数、ms、事件名。空账不entry。"""
    accounts: dict[str, dict[str, Any]] = {}
    for row in trace_rows:
        event_type = str(row.get("event_type") or "")
        if event_type in facts["finished_events"]:
            continue
        stage, duration = unregistered_stage_of(row, facts)
        if not stage or duration is None:
            continue
        cell = accounts.setdefault(stage, {"events": {}, "count": 0, "total_ms": 0.0})
        cell["events"][event_type] = cell["events"].get(event_type, 0) + 1
        cell["count"] += 1
        cell["total_ms"] = round(cell["total_ms"] + float(duration), 1)
    return accounts


def duration_from_payload(payload: Mapping[str, Any], dotted: str) -> float | None:
    """按点路径从载荷里取一枚正时长；取不到就交 None（不许当 0 用）。"""
    cursor: Any = payload or {}
    for part in str(dotted).split("."):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(part)
    if isinstance(cursor, bool) or not isinstance(cursor, (int, float)):
        return None
    value = float(cursor)
    return value if value > 0 else None

# ==================== 只读引用 R631（不改它一个字） ====================


def load_r631():
    """按路径装载在册那把尺，用来现跑它的 collect() 做逐枚对账。"""
    if not R631_FILE.exists():
        raise InputMissing("对账基准不在：%s" % R631_FILE)
    spec = importlib.util.spec_from_file_location("r631_stage_sum_delta_ref", R631_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 要能从 sys.modules 找回本模块
    spec.loader.exec_module(module)
    return module


def emitter_symbols_for_event(event_type: str, root: Path = APP_ROOT) -> list[str]:
    """``app/**`` 里把这枚事件名写进 record_event 的发射点（AST，不 import）。"""
    hits: list[str] = []
    for path in _py_files(root):
        tree = _parse(path)
        index = _symbol_index(tree)
        rel = path.relative_to(root.parent).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == event_type:
                parent = _nearest_call(tree, node)
                if parent is not None:
                    hits.append("%s::%s" % (rel, _symbol_at(index, node.lineno)))
    return sorted(set(hits))


def _nearest_call(tree: ast.Module, target: ast.AST) -> ast.Call | None:
    """向上找最近的 Call 节点：常量单独出现不算发射点，得是 record_event(...) 的参数。"""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    node: ast.AST | None = target
    while node is not None:
        if isinstance(node, ast.Call):
            return node
        node = parents.get(id(node))
    return None


def default_directory() -> Path:
    return Path(tempfile.gettempdir()) / "evalrun"


def read_inputs(window: str, directory: Path) -> dict[str, Any]:
    """读三本原料，并顺手把「窗里有哪几枚 trace、各自事件清单」摊平交回。"""
    r631 = load_r631()
    traces_path = Path(directory) / ("%s-traces.jsonl" % window)
    sidecar_path = Path(directory) / ("%s-sidecar.jsonl" % window)
    frames_path = Path(directory) / ("%s-sidecar-frames.jsonl" % window)
    missing = [str(path) for path in (traces_path, sidecar_path, frames_path) if not Path(path).exists()]
    if missing:
        raise InputMissing("原料缺失：%s" % ", ".join(missing))
    events, used = r631.read_traces([traces_path])
    rows = _raw_rows(traces_path)
    sessions = r631.read_frames_sessions(frames_path)
    trace_to_key = r631.trace_keys_from_events(events, sessions)
    sidecar_leg = r631.read_sidecar(sidecar_path)
    denominators = {trace: float(sidecar_leg.values[key])
                    for trace, key in trace_to_key.items() if key in sidecar_leg.values}
    by_trace: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_trace.setdefault(str(row.get("trace_id") or ""), []).append(row)
    return {
        "window": window,
        "paths": {"traces": str(traces_path), "sidecar": str(sidecar_path), "frames": str(frames_path)},
        "used_paths": list(used),
        "events": events,
        "raw_rows": rows,
        "rows_by_trace": by_trace,
        "trace_to_key": trace_to_key,
        "sessions": dict(sessions),
        "denominators": denominators,
        "sidecar_values": dict(sidecar_leg.values),
        "sidecar_rows_read": sidecar_leg.rows_read,
        "sidecar_duplicates": list(sidecar_leg.duplicates),
        "r631": r631,
    }


def _raw_rows(path: Path) -> list[dict[str, Any]]:
    """原始 trace 行（payload 解一次）：事件名册、sequence、created_at 都在这里，认账之外还要用。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    for position, raw in enumerate(text.split("\n"), start=1):
        item = raw.strip()
        if not item:
            continue
        try:
            row = json.loads(item)
        except json.JSONDecodeError as exc:
            raise InputMissing("%s 第 %d 行不是 JSON ⇒ %s" % (path, position, str(exc)[:120])) from exc
        if not isinstance(row, dict):
            continue
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        row["payload"] = payload if isinstance(payload, dict) else {}
        out.append(row)
    if not out:
        raise InputMissing("%s 里没有可读的 JSON 行" % path)
    return out


def _stamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)  # 一律剥时区：created_at 无偏移、载荷 started_at 带 +00:00，同为 UTC


def _first_last_stamp(rows: Sequence[Mapping[str, Any]]) -> tuple[datetime | None, datetime | None]:
    stamps = [stamp for stamp in (_stamp(row.get("created_at") or row.get("timestamp")) for row in rows) if stamp]
    if not stamps:
        return (None, None)
    return (min(stamps), max(stamps))


def request_started_row(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("event_type") or "") == "request.started":
            return row
    return None

# ==================== 覆盖面账 ====================


@dataclass
class Claim:
    """一道「某题某段没进账」的归因。型别 + 形 + 凭据，三件齐了才算一条账。"""

    key: str
    trace_id: str
    stage: str
    type: str
    shape: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "trace_id": self.trace_id, "stage": self.stage, "type": self.type,
                "shape": self.shape, "evidence": self.evidence, "note": self.note}


def _evidence(symbol: str, reading: str, kind: str = "source_shape") -> dict[str, Any]:
    return {"kind": kind, "symbol": symbol, "reading": reading}


def identityless_site_for_tier(facts: Mapping[str, Any], fragment: str) -> dict[str, str] | None:
    for site in facts["identityless_model_sites"]:
        if fragment in site["tier"]:
            return site
    return None


def classify_missing(
    *,
    key: str,
    trace_id: str,
    stage: str,
    trace_rows: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
    facts: Mapping[str, Any],
    report: Mapping[str, Any],
    orphans_for_question: Sequence[Mapping[str, Any]],
) -> Claim:
    """把一道缺失归到三型之一，并把凭据配齐（判据②的门就在这枚函数里）。

    判定顺序即证据强度顺序，一枚都不许含糊：
      1. 本题整段被剔（型 C）——凭该题自己那份报告的 count/ledger_count/excluded_count；
      2. 账在姊妹 trace 上（型 A/a3）——凭配对孤儿的现读跨度；
      3. rewrite 段（型 A/a2）——凭 retrieval.completed 的 rewrite_count 现读 + 该腿无跨度符号；
      4. reflect 段（型 A/a2）——凭 record_stage_event 在 app/** 的调用点枚数；
      5. 本题带了带时长的未登记事件（型 B）——凭事件名不在 FINISHED_EVENTS 的现读对照；
      6. 调用点天生不落（型 A/a1）——凭 AST 现读的无身份调用点；
      7. 都没有 ⇒ 型 A/a0，这道腿这一题根本没跑。
    """
    cell = (report.get("stages") or {}).get(stage) or {}
    measured_count = int(cell.get("count") or 0)
    ledger_count = int(cell.get("ledger_count") or 0)
    excluded_count = int(cell.get("excluded_count") or 0)
    if measured_count and not ledger_count:
        overlap = report.get("overlap") or {}
        return Claim(key, trace_id, stage, TYPE_NESTED_OUT, evidence=[
            _evidence("app/common/stage_timing.py::aggregate_stage_latency",
                      "该题自己那份报告：%s 段 count=%s ／ ledger_count=%s ／ excluded_count=%s ／ excluded_ms=%s"
                      % (stage, measured_count, ledger_count, excluded_count, cell.get("excluded_ms")),
                      "report_reading"),
            _evidence("app/common/stage_timing.py::aggregate_stage_latency",
                      "同题重叠 pairs=%s ／ nested_ms=%s ／ 未决=%s（在册只把严格包含的一侧剔出加总）"
                      % (overlap.get("pairs"), overlap.get("nested_ms"), overlap.get("unresolved_pairs")),
                      "report_reading"),
        ], note="发了、认了，但整段被嵌套判定剔掉，加总里 0 ms")

    sibling = [orphan for orphan in orphans_for_question if orphan["stage_counts"].get(stage)]
    if sibling:
        chosen = sibling[0]
        return Claim(key, trace_id, stage, TYPE_NO_EVENT, SHAPE_SIBLING_TRACE, evidence=[
            _evidence("app/agents/orchestrator.py::run_interrupt_stream",
                      "本题配对孤儿 trace %s 带 %s 段跨度 %s 枚、合计 %s ms；该 trace 无 request.started"
                      % (chosen["trace_id"], stage, chosen["stage_counts"][stage], chosen["stage_ms"][stage]),
                      "sibling_trace"),
            _evidence("app/api/v1/chat.py::_approve_stream",
                      "AST／源码现读：批准续跑那一处调用 run_interrupt_stream 不传 request_id/trace_id/task_id，"
                      "orchestrator 侧 _execution_ids() 另铸一枚 trace_id ⇒ 工作腿的跨度落在另一枚 trace 上",
                      "source_shape"),
        ], note="该题这枚 trace 里确实一个都没有；账在另一枚 trace_id 上")

    if stage == "rewrite":
        witness = _rewrite_witness(trace_rows, facts)
        if witness is not None:
            return Claim(key, trace_id, stage, TYPE_NO_EVENT, SHAPE_NO_SPAN, evidence=[
                witness,
                _evidence("app/common/model_handler.py::ModelHandler._call_budget",
                          "非流式那一发才是 rewrite 档；本件 AST 现读该模块的跨度符号引用：%s"
                          "（一枚都没命中 ⇒ 这条腿没有跨度这回事）"
                          % json.dumps(facts["model_handler_span_symbols"], ensure_ascii=False),
                          "source_shape"),
            ], note="改写真的跑了（rewrite_count 在册），但它不发任何事件")

    if stage == "reflect":
        callers = facts["record_stage_event_call_sites"]
        return Claim(key, trace_id, stage, TYPE_NO_EVENT, SHAPE_NO_SPAN, evidence=[
            _evidence("app/trace/spans.py::record_stage_event",
                      "app/** 现读调用点 %d 枚：%s ⇒ 这枚为 reflect 准备的入口没人用"
                      % (len(callers), ", ".join(callers) or "（零枚）"), "source_shape"),
            _evidence("app/agents/nodes.py::reflect_node",
                      "复审是规则过（review_agent_results），不发 model／tool 跨度；"
                      "STAGE_DESCRIPTIONS 自己就写着「当前为纯规则」", "source_shape"),
        ], note="reflect 全线不产：入口在，调用点零；正因为这条腿根本没插桩，"
               "本件无法从 trace 判它这一题跑没跑过 —— 这是覆盖面缺口，不是路径差异")

    accounts = unregistered_accounts(trace_rows, facts)
    account = accounts.get(stage)
    if account:
        named = json.dumps(account["events"], ensure_ascii=False)
        return Claim(key, trace_id, stage, TYPE_UNRECOGNIZED, evidence=[
            _evidence("app/common/stage_timing.py::FINISHED_EVENTS",
                      "本题 %s 段有未登记而有时长的事件 %s 枚合计 %s ms；在册 FINISHED_EVENTS 现读 = %s"
                      "⇒ 这些事件名不在册（%s 段的归段凭据见 app/trace/spans.py::record_stage_event 那枚入口的缺位）"
                      % (stage, named, account["count"], account["total_ms"],
                         json.dumps(sorted(facts["finished_events"]), ensure_ascii=False)), "event_shape"),
            _evidence("app/common/stage_timing.py::samples_from_events",
                      "kind = FINISHED_EVENTS.get(event_type) 为 None 即 continue ⇒ 一字节都不进样本",
                      "source_shape"),
        ], note="发了，但 samples_from_events() 不认它")

    site = _identityless_site_for_stage(stage, trace_rows, facts)
    if site is not None:
        return Claim(key, trace_id, stage, TYPE_NO_EVENT, SHAPE_NO_IDENTITY, evidence=[
            _evidence(site["file_symbol"],
                      "AST 现读：_make_model(%s).%s(...) 不带 config ⇒ ExecutionSpan.active 为假，"
                      "record() 与 _observe_stage() 双双直接 return（app/trace/spans.py::ExecutionSpan.record）"
                      % (site["tier"], site["method"]), "source_shape"),
        ], note="这一发跑了，但它那一枚跨度天生不落盘")

    inventory = sorted({str(row.get("event_type")) for row in trace_rows})
    return Claim(key, trace_id, stage, TYPE_NO_EVENT, SHAPE_PATH_NOT_TAKEN, evidence=[
        _evidence("app/common/stage_timing.py::samples_from_events",
                  "本题事件名册 %s 里没有任何能名 %s 段的记录（含未登记时长件在内）"
                  % (json.dumps(inventory, ensure_ascii=False), stage), "event_shape"),
    ], note="这道腿这一题根本没跑（不产账不是缺陷，是覆盖面的边界）")


def facts_request_terminals(facts: Mapping[str, Any]) -> list[str]:
    """终事件不叫「未登记的时长账」：它们是端到端腿自己的读数，别混进型 B。"""
    return sorted(REQUEST_TERMINAL_EVENTS)


def sample_stage_from_samples(samples: Iterable[Any]) -> set[str]:
    return {str(getattr(sample, "stage", "") or "") for sample in samples}


def _rewrite_witness(trace_rows: Sequence[Mapping[str, Any]], facts: Mapping[str, Any]) -> dict[str, Any] | None:
    """检索留痕里的 rewrite_count：改写这一发确实跑了的唯一现读凭据。"""
    best = 0
    where = ""
    for row in trace_rows:
        if str(row.get("event_type") or "") != "retrieval.completed":
            continue
        count = (row.get("payload") or {}).get("rewrite_count")
        if isinstance(count, int) and count > best:
            best = count
            where = str(row.get("trace_id") or "")
    if not best:
        return None
    emitters = facts["leg_account_emitters"].get("retrieval.completed") or []
    return _evidence(emitters[0] if emitters else "app/rag/retrieval_pipeline.py",
                     "本题 retrieval.completed 载荷现读 rewrite_count=%s（trace %s）⇒ 改写跑了 %s 发，"
                     "分段账里 0 枚" % (best, where, best), "event_witness")


def _identityless_site_for_stage(stage: str, trace_rows: Sequence[Mapping[str, Any]],
                                  facts: Mapping[str, Any]) -> dict[str, str] | None:
    """把「这一段本来该由哪一档那一发产出」对上 AST 现读的无身份调用点。

    顺序照本题真出现过的痕迹来：数据腿的工具有在 ⇒ 指向 pandas 代码那一发（CODE）；
    闲聊直答 ⇒ 指向 CHAT 那一发；拆题 ⇒ PLAN 那一发。选错档，凭据就指错调用点。
    """
    tools = {str((row.get("payload") or {}).get("tool_name") or "") for row in trace_rows}
    if stage == "generate" and tools & {"analyze_data", "query_data", "generate_chart"}:
        order = ("CODE", "CHAT")
    else:
        order = {"classify": ("PLAN",), "generate": ("CHAT", "CODE")}.get(stage, ())
    for fragment in order:
        for site in facts["identityless_model_sites"]:
            if fragment in site["tier"]:
                return site
    return None

# ==================== 组装一窗的账 ====================


def _orphan_reason(trace_rows: Sequence[Mapping[str, Any]], sessions: Mapping[str, str]) -> str:
    started = request_started_row(trace_rows)
    if started is None:
        return "no_request_started"
    session = str((started.get("payload") or {}).get("session_id") or "").strip()
    if not session:
        return "request_started_without_session_id"
    if session not in sessions:
        return "session_absent_from_frames"
    return "question_absent_from_sidecar"


def orphan_profile(trace_id: str, samples: Sequence[StageSample], trace_rows: Sequence[Mapping[str, Any]],
                   reason: str) -> dict[str, Any]:
    stage_counts: dict[str, int] = {}
    stage_ms: dict[str, float] = {}
    for sample in samples:
        name = sample.label_or_stage
        stage_counts[name] = stage_counts.get(name, 0) + 1
        stage_ms[name] = round(stage_ms.get(name, 0.0) + float(sample.duration_ms), 1)
    first, last = _first_last_stamp(trace_rows)
    return {
        "trace_id": trace_id,
        "reason": reason,
        "samples": list(samples),
        "sample_count": len(samples),
        "total_ms": round(sum(float(sample.duration_ms) for sample in samples), 1),
        "stage_counts": stage_counts,
        "stage_ms": stage_ms,
        "workers": sorted({str((row.get("payload") or {}).get("worker") or "") for row in trace_rows
                           if str(row.get("event_type") or "").endswith(".started")}),
        "event_types": sorted({str(row.get("event_type")) for row in trace_rows}),
        "has_request_started": request_started_row(trace_rows) is not None,
        "min_sequence": min((int(row.get("sequence") or 0) for row in trace_rows), default=0),
        "first_event": first.isoformat(timespec="milliseconds") if first else "",
        "last_event": last.isoformat(timespec="milliseconds") if last else "",
    }


def pair_orphans(groups: Mapping[str, Any], trace_to_key: Mapping[str, str],
                 tolerance_seconds: float = 2.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """孤儿 trace 归题：只走「同一枚 resumed 头（同题号、时间相邻 ≤tolerance）」这一条桥。

    不许按时序猜配对（R631 在册纪律）：没有 lane_source=resumed 那枚头当凭据的孤儿，
    一律留在未归名列，不冒充成某一题的账。
    """
    heads: dict[str, list[tuple[str, datetime]]] = {}
    for item in groups[GROUP_RESUMED_HEAD]:
        started = request_started_row(item["rows"])
        stamp = _stamp((started or {}).get("created_at") or (started or {}).get("timestamp")) if started else None
        if stamp is None:
            continue
        heads.setdefault(str(item["key"]), []).append((item["trace_id"], stamp))
    paired: list[dict[str, Any]] = []
    unpaired: list[dict[str, Any]] = []
    for orphan in groups[GROUP_NO_DENOM]:
        first = _stamp(orphan["first_event"]) if orphan["first_event"] else None
        match = None
        if first is not None:
            for key, entries in heads.items():
                for head_trace, stamp in entries:
                    if 0 <= (first - stamp).total_seconds() <= tolerance_seconds:
                        match = {"key": key, "head_trace_id": head_trace,
                                 "lag_ms": round((first - stamp).total_seconds() * 1000.0, 1)}
                        break
                if match:
                    break
        row = {name: value for name, value in orphan.items() if name != "samples"}
        row["paired"] = match
        (paired if match else unpaired).append(row)
    return sorted(paired, key=lambda row: row["trace_id"]), sorted(unpaired, key=lambda row: row["trace_id"])


def lane_matrix(items: Sequence[Mapping[str, Any]], canonical: Sequence[str]) -> dict[str, Any]:
    view: dict[str, Any] = {}
    for item in items:
        lane = str(item.get("lane") or "unknown")
        cell = view.setdefault(lane, {"questions": 0, "lanes": set(), "stages": {
            stage: {"producing": 0, "missing": 0, "ledger_ms": 0.0, "measured_ms": 0.0,
                    "excluded_count": 0, "types": {}} for stage in canonical}})
        cell["questions"] += 1
        cell["lanes"].add(str(item.get("lane") or ""))
        for stage in canonical:
            detail = item["stages"][stage]
            entry = cell["stages"][stage]
            if detail["measured_count"]:
                entry["producing"] += 1
                entry["ledger_ms"] = round(entry["ledger_ms"] + float(detail["ledger_ms"]), 1)
                entry["measured_ms"] = round(entry["measured_ms"] + float(detail["measured_ms"]), 1)
                entry["excluded_count"] += int(detail["excluded_count"])
            else:
                entry["missing"] += 1
                claim = detail["claim"] or {}
                tag = "%s/%s" % (claim.get("type", "unclassified"), claim.get("shape") or "-")
                entry["types"][tag] = entry["types"].get(tag, 0) + 1
    for lane, cell in view.items():
        cell["lanes"] = sorted(cell["lanes"])
        for stage, entry in cell["stages"].items():
            entry["share_producing_pct"] = round(entry["producing"] / cell["questions"] * 100.0, 2) if cell["questions"] else 0.0
    return view


def build_window(window: str, directory: Path | str = None, *,
                 recognizer: Callable[[Iterable[Mapping[str, Any]]], Sequence[StageSample]] | None = None,
                 omit_groups: Sequence[str] = (), facts: Mapping[str, Any] | None = None,
                 tolerance_seconds: float = 2.0) -> dict[str, Any]:
    """一窗的覆盖面账。任何一条自证不过，当场抛，不交半个数冒充测量。"""
    directory = Path(directory or default_directory())
    inputs = read_inputs(window, directory)
    facts = facts or source_facts()
    canonical = facts["canonical_stages"]
    recognise = recognizer or samples_from_events

    events = inputs["events"]
    samples_all = list(recognise(events))
    by_trace: dict[str, list[StageSample]] = {}
    for sample in samples_all:
        if sample.trace_id:
            by_trace.setdefault(sample.trace_id, []).append(sample)

    denominators = inputs["denominators"]
    rows_by_trace = inputs["rows_by_trace"]
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in UNIVERSE_GROUPS}
    for trace_id in sorted(rows_by_trace):
        has_denominator = trace_id in denominators
        has_samples = bool(by_trace.get(trace_id))
        started = request_started_row(rows_by_trace[trace_id])
        payload = (started or {}).get("payload") or {}
        item = {
            "trace_id": trace_id,
            "key": str(inputs["trace_to_key"].get(trace_id) or trace_id),
            "lane": str(payload.get("lane") or ""),
            "tier": str(payload.get("tier") or ""),
            "lane_source": str(payload.get("lane_source") or ""),
            "rows": rows_by_trace[trace_id],
            "samples": by_trace.get(trace_id, []),
            "end_to_end_ms": denominators.get(trace_id),
        }
        if has_denominator and has_samples:
            groups[GROUP_ASKED].append(item)
        elif has_samples:
            groups[GROUP_NO_DENOM].append(item)
        elif has_denominator:
            groups[GROUP_RESUMED_HEAD].append(item)
        else:
            groups[GROUP_BARE].append(item)

    reference = inputs["r631"].collect(window=window, directory=directory)
    reference_rows = {str(row["trace_id"]): row for row in reference.get("rows") or []}
    reference_skipped = {str(row["trace_id"]): row for row in reference.get("skipped") or []}

    orphans_source = [
        orphan_profile(item["trace_id"], item["samples"], item["rows"],
                       _orphan_reason(item["rows"], inputs["sessions"]))
        for item in groups[GROUP_NO_DENOM]
    ]
    paired_orphans, unpaired_orphans = pair_orphans(
        {**groups, GROUP_NO_DENOM: orphans_source}, inputs["trace_to_key"], tolerance_seconds)
    orphans_by_key: dict[str, list[dict[str, Any]]] = {}
    for orphan in paired_orphans:
        orphans_by_key.setdefault(orphan["paired"]["key"], []).append(orphan)

    questions: list[dict[str, Any]] = []
    claims: list[Claim] = []
    mismatches: list[dict[str, Any]] = []
    for item in groups[GROUP_ASKED]:
        trace_id = item["trace_id"]
        key = item["key"]
        e2e = float(item["end_to_end_ms"])
        members = item["samples"]
        report = aggregate_stage_latency(members, end_to_end_by_trace={trace_id: e2e})
        cell = (report.get("coverage") or {}).get("per_request", {}).get(trace_id)
        if cell is None:
            mismatches.append({"key": key, "trace_id": trace_id, "field": "per_request",
                               "mine": "缺格", "r631": reference_rows.get(trace_id, {}).get("error_pct")})
            continue
        ledger_stages = report.get("stages") or {}
        segments = sum(int((ledger_stages.get(stage) or {}).get("ledger_count") or 0) for stage in canonical)
        missing = [stage for stage in canonical if not int((ledger_stages.get(stage) or {}).get("count") or 0)]
        stage_view: dict[str, dict[str, Any]] = {}
        for stage in canonical:
            entry = ledger_stages.get(stage) or {}
            detail = {
                "measured_count": int(entry.get("count") or 0),
                "ledger_count": int(entry.get("ledger_count") or 0),
                "excluded_count": int(entry.get("excluded_count") or 0),
                "measured_ms": round(sum(float(sample.duration_ms)
                                    for sample in members if sample.stage == stage), 1),
                "ledger_ms": round(float(entry.get("total_ms") or 0.0), 1),
                "excluded_ms": round(float(entry.get("excluded_ms") or 0.0), 1),
                "missing": stage in missing,
                "claim": None,
            }
            if not detail["missing"]:
                detail["status"] = TYPE_IN_LEDGER if detail["ledger_count"] else TYPE_NESTED_OUT
                if detail["status"] == TYPE_NESTED_OUT:
                    claim = Claim(key, trace_id, stage, TYPE_NESTED_OUT, evidence=[
                        _evidence("app/common/stage_timing.py::aggregate_stage_latency",
                                  "该题自己那份报告：count=%s ledger_count=%s excluded_count=%s excluded_ms=%s"
                                  % (detail["measured_count"], detail["ledger_count"],
                                     detail["excluded_count"], detail["excluded_ms"]), "report_reading")])
                    detail["claim"] = claim.as_dict()
                    claims.append(claim)
            else:
                claim = classify_missing(key=key, trace_id=trace_id, stage=stage,
                                         trace_rows=item["rows"], inputs=inputs, facts=facts,
                                         report=report, orphans_for_question=orphans_by_key.get(key, []))
                detail["status"] = claim.type
                detail["claim"] = claim.as_dict()
                claims.append(claim)
            stage_view[stage] = detail
        row = {
            "key": key, "trace_id": trace_id, "lane": item["lane"] or "unknown", "tier": item["tier"],
            "lane_source": item["lane_source"], "end_to_end_ms": round(float(cell["end_to_end_ms"]), 1),
            "segment_sum_ms": round(float(cell["segment_sum_ms"]), 1),
            "gap_ms": round(float(cell["gap_ms"]), 1),
            "error_pct": float(cell["coverage_error_pct"]),
            "segments": segments, "missing_stages": missing,
            "unresolved_pairs": int(cell["unresolved_overlap_pairs"]),
            "truncation_bound_ms": round(segments * 1.0, 1),
            "stages": stage_view,
            "worker_leg_wall_ms": round(sum(
                duration_from_payload(row_.get("payload") or {}, "summary.duration_ms") or 0.0
                for row_ in item["rows"] if str(row_.get("event_type")) == "step.finished"), 1),
            "retrieval_leg_ms": round(sum(
                duration_from_payload(row_.get("payload") or {}, "duration_ms") or 0.0
                for row_ in item["rows"] if str(row_.get("event_type")) == "retrieval.completed"), 1),
            "unregistered_accounts": unregistered_accounts(item["rows"], facts),
            "orphan_ms": round(sum(orphan["total_ms"] for orphan in orphans_by_key.get(key, [])), 1),
            "orphan_traces": [orphan["trace_id"] for orphan in orphans_by_key.get(key, [])],
        }
        expected = reference_rows.get(trace_id)
        if expected is not None:
            for field_name, mine, theirs in (
                ("end_to_end_ms", row["end_to_end_ms"], round(float(expected["end_to_end_ms"]), 1)),
                ("segment_sum_ms", row["segment_sum_ms"], round(float(expected["segment_sum_ms"]), 1)),
                ("segments", row["segments"], int(expected["segments"])),
                ("missing_stages", row["missing_stages"], list(expected["missing_stages"])),
                ("unresolved_pairs", row["unresolved_pairs"], int(expected["unresolved_pairs"])),
                ("error_pct", row["error_pct"], float(expected["error_pct"])),
            ):
                if mine != theirs:
                    mismatches.append({"key": key, "trace_id": trace_id, "field": field_name,
                                       "mine": mine, "r631": theirs})
        questions.append(row)

    universe = {"declared_distinct_traces": len(rows_by_trace),
                "counts": {name: len(groups[name]) for name in UNIVERSE_GROUPS},
                "named_items": sum(len(groups[name]) for name in UNIVERSE_GROUPS if name not in omit_groups)}
    named = sum(len(groups[name]) for name in UNIVERSE_GROUPS if name not in omit_groups)
    omitted = [name for name in UNIVERSE_GROUPS if name in omit_groups]
    if omitted or named != universe["declared_distinct_traces"]:
        raise UniverseError(
            "母集 %d 枚 vs 账本点名 %d 枚（摘掉的组：%s）⇒ 有人被悄悄摘掉，本件不出数"
            % (universe["declared_distinct_traces"], named, ", ".join(omitted) or "无"))
    reference_gap = {
        "rows": len(reference_rows), "skipped": len(reference_skipped),
        "skipped_reasons": sorted({str(row.get("reason")) for row in reference_skipped.values()}),
        "asked_minus_rows": len(groups[GROUP_ASKED]) - len(reference_rows),
        "no_denom_minus_skipped": len(groups[GROUP_NO_DENOM]) - len(reference_skipped),
    }
    if reference_gap["asked_minus_rows"] or reference_gap["no_denom_minus_skipped"]:
        raise MismatchError("与 R631 的母集切分对不上：%s" % json.dumps(reference_gap, ensure_ascii=False))

    stage_rollup = {}
    for stage in canonical:
        producing = sum(1 for row in questions if row["stages"][stage]["measured_count"])
        rolled_ms = round(sum(row["stages"][stage]["ledger_ms"] for row in questions), 1)
        types: dict[str, int] = {}
        for row in questions:
            detail = row["stages"][stage]
            if detail["measured_count"]:
                continue
            claim = detail["claim"]
            tag = "%s/%s" % (claim["type"], claim["shape"] or "-")
            types[tag] = types.get(tag, 0) + 1
        stage_rollup[stage] = {"producing_questions": producing, "missing_questions": len(questions) - producing,
                              "ledger_ms": rolled_ms,
                              "excluded_ms": round(sum(row["stages"][stage]["excluded_ms"] for row in questions), 1),
                              "missing_types": types}
    totals = {
        "questions": len(questions),
        "end_to_end_ms": round(sum(row["end_to_end_ms"] for row in questions), 1),
        "segment_sum_ms": round(sum(row["segment_sum_ms"] for row in questions), 1),
        "gap_ms": round(sum(row["gap_ms"] for row in questions), 1),
        "orphan_ms": round(sum(row["orphan_ms"] for row in questions), 1),
        "worker_leg_wall_ms": round(sum(row["worker_leg_wall_ms"] for row in questions), 1),
        "retrieval_leg_ms": round(sum(row["retrieval_leg_ms"] for row in questions), 1),
        "truncation_bound_ms": round(sum(row["truncation_bound_ms"] for row in questions), 1),
        "unresolved_pairs": sum(row["unresolved_pairs"] for row in questions),
    }
    totals["gap_pct"] = round(totals["gap_ms"] / totals["end_to_end_ms"] * 100.0, 2) if totals["end_to_end_ms"] else 0.0
    totals["gap_after_orphan_ms"] = round(totals["gap_ms"] - totals["orphan_ms"], 1)
    #: 残差 = 缺口 −（加得进的孤儿账）−（int() 地板界）。这笔没有任何在册账可归，
    #: 想量它只能靠新插桩，本件不拿它冒充已有的读数。
    totals["residual_ms"] = round(totals["gap_after_orphan_ms"] - totals["truncation_bound_ms"], 1)
    totals["residual_pct_of_end_to_end"] = round(
        totals["residual_ms"] / totals["end_to_end_ms"] * 100.0, 2) if totals["end_to_end_ms"] else 0.0

    nonproducing = nonproducing_lanes(groups, questions, facts, canonical)
    data = {
        "schema": "r636.stage-coverage/1",
        "window": window,
        "directory": str(directory),
        "inputs": inputs["paths"],
        "criterion": {"threshold_pct": reference["threshold_pct"], "align_pct": reference["align_pct"],
                      "r631_status": reference["status"]},
        "universe": universe,
        "named": {
            GROUP_ASKED: [{"key": item["key"], "trace_id": item["trace_id"]} for item in groups[GROUP_ASKED]],
            GROUP_NO_DENOM: orphans_source_named(orphans_source, paired_orphans),
            GROUP_RESUMED_HEAD: [{"key": item["key"], "trace_id": item["trace_id"],
                                  "lane": item["lane"], "lane_source": item["lane_source"],
                                  "event_types": sorted({str(row.get("event_type")) for row in item["rows"]})}
                                 for item in groups[GROUP_RESUMED_HEAD]],
            GROUP_BARE: [{"key": item["key"], "trace_id": item["trace_id"],
                          "event_types": sorted({str(row.get("event_type")) for row in item["rows"]})}
                         for item in groups[GROUP_BARE]],
        },
        "reference_gap": reference_gap,
        "questions": questions,
        "claims": [claim.as_dict() for claim in claims],
        "stage_rollup": stage_rollup,
        "lane_matrix": lane_matrix(questions, canonical),
        "nonproducing_lanes": nonproducing,
        "orphans": {"paired": [drop_samples(row) for row in paired_orphans],
                    "unpaired": [drop_samples(row) for row in unpaired_orphans],
                    "reasons": {reason: sum(1 for row in orphans_source if row["reason"] == reason)
                                for reason in sorted({row["reason"] for row in orphans_source})}},
        "totals": totals,
        "source_facts": facts,
        "mismatches": mismatches,
        "recognizer": getattr(recognise, "__name__", repr(recognise)),
    }
    validate_claims(data["claims"], {row["trace_id"]: row for row in questions}, canonical)
    if mismatches:
        raise MismatchError("与 R631 现跑读数对不上 %d 处，前若干枚：%s"
                            % (len(mismatches), json.dumps(mismatches[:6], ensure_ascii=False)[:600]))
    return data

def drop_samples(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "samples"}


def orphans_source_named(orphans: Sequence[Mapping[str, Any]], paired: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    paired_by_trace = {row["trace_id"]: row.get("paired") for row in paired}
    out = []
    for orphan in orphans:
        match = paired_by_trace.get(orphan["trace_id"])
        out.append({
            "trace_id": orphan["trace_id"],
            "reason": orphan["reason"],
            "sample_count": orphan["sample_count"],
            "total_ms": orphan["total_ms"],
            "stage_counts": orphan["stage_counts"],
            "workers": orphan["workers"],
            "has_request_started": orphan["has_request_started"],
            "first_event": orphan["first_event"],
            "paired_to": (match or {}).get("key") if match else None,
            "paired_head_trace": (match or {}).get("head_trace_id") if match else None,
        })
    return sorted(out, key=lambda row: row["trace_id"])


def nonproducing_lanes(groups: Mapping[str, list[dict[str, Any]]], questions: Sequence[Mapping[str, Any]],
                        facts: Mapping[str, Any], canonical: Sequence[str]) -> list[dict[str, Any]]:
    """「哪些车道今天压根不产分段账」——每条都必须带一枚可执行的谓词与现读命中数。"""
    out: list[dict[str, Any]] = []
    handler_clean = not any(facts["model_handler_span_symbols"].values())
    if handler_clean:
        out.append({
            "scope": "全线（所有车道的所有题）", "stages": ["rewrite"],
            "predicate": "app/common/model_handler.py 的 AST 引用读数里，跨度符号一枚都没有",
            "questions": len(questions),
            "evidence": [
                _evidence("app/common/model_handler.py::ModelHandler._call_budget",
                          "非流式 = ModelTier.REWRITE（AST 现读引用：%s）" % dict(facts["model_handler_span_symbols"])),
                _evidence("app/common/stage_timing.py::TIER_TO_STAGE",
                          "在册映射把 rewrite 档记成 rewrite 段：%s" % facts["tier_to_stage"].get("rewrite")),
            ],
        })
    reflect_callers = facts["record_stage_event_call_sites"]
    out.append({
        "scope": "全线（reflect 段在任何车道都不产）", "stages": ["reflect"],
        "predicate": "app/** 里 record_stage_event 的调用点枚数 == 0",
        "questions": len(questions),
        "evidence": [_evidence("app/trace/spans.py::record_stage_event",
                               "现读调用点 %d 枚：%s" % (len(reflect_callers), ", ".join(reflect_callers) or "（零枚）")),
                     _evidence("app/agents/nodes.py::reflect_node",
                               "复审是规则过，不发 model／tool 跨度；STAGE_DESCRIPTIONS 自己就写着「当前为纯规则」")],
    })
    heads = groups[GROUP_RESUMED_HEAD]
    if heads:
        out.append({
            "scope": "车道：批准续跑的头（lane_source=resumed）", "stages": list(canonical),
            "predicate": "该 trace 只有 1 枚 request.started，且 payload.lane == \"\" 且 payload.lane_source == \"resumed\"",
            "questions": len(heads),
            "evidence": [_evidence("app/api/v1/chat.py::_record_resumed_lane_trace",
                                   "现读命中 %d 枚：%s" % (len(heads), ", ".join(sorted(item["key"] for item in heads)))),
                         _evidence("app/common/stage_timing.py::samples_from_events",
                                   "trace 里没有任何 *.finished ⇒ 分段腿对这一枚题交回空")],
        })
    orphans = groups[GROUP_NO_DENOM]
    if orphans:
        out.append({
            "scope": "车道：批准续跑的工作腿（孤儿 trace）", "stages": list(canonical),
            "predicate": "该 trace 的跨度样本 > 0，但窗内既无 request.started 也无本窗帧账认得的 session_id",
            "questions": len(orphans),
            "evidence": [_evidence("app/agents/orchestrator.py::run_interrupt_stream",
                                   "签名收 request_id/trace_id/task_id（关键字参数），但 app/api/v1/chat.py 那一处调用一个都不传 ⇒ "
                                   "_execution_ids() 另铸一枚 trace_id"),
                         _evidence("app/common/stage_timing.py::CANONICAL_STAGES",
                                   "现读孤儿 %d 枚、跨度合计 %s ms（reason 分布见 orphans.reasons）"
                                   % (len(orphans), round(sum(
                                       float(sample.duration_ms)
                                       for item in orphans for sample in item["samples"]), 1)))],
        })
    no_generate = [row for row in questions
                   if not row["stages"]["generate"]["measured_count"]
                   and not any(str(event.get("event_type")) == "step.started" for event in _events_of(row, groups))]
    direct = [row for row in no_generate if not row.get("orphan_traces")]
    sibling = [row for row in no_generate if row.get("orphan_traces")]
    if direct:
        site = next((item for item in facts["identityless_model_sites"] if "CHAT" in item["tier"]), None)
        out.append({
            "scope": "车道：闲聊直答（无 worker 腿、也无同胞账）", "stages": ["generate"],
            "predicate": "该题 generate 段 measured_count == 0 且 trace 内没有 step.started 且 orphan_traces 为空",
            "questions": len(direct),
            "keys": sorted(str(row["key"]) for row in direct),
            "evidence": [_evidence(site["file_symbol"] if site else "app/agents/nodes.py::respond",
                                   "AST 现读：_make_model(%s).%s(...) 不带 config ⇒ 那一发天生不落"
                                   % (site["tier"] if site else "?", site["method"] if site else "invoke"))],
        })
    if sibling:
        out.append({
            "scope": "车道：批准续跑（generate 的账在同胞 trace 上，本题 trace 不产）", "stages": ["generate"],
            "predicate": "该题 generate 段 measured_count == 0 且 trace 内没有 step.started 且 orphan_traces 非空",
            "questions": len(sibling),
            "keys": sorted(str(row["key"]) for row in sibling),
            "evidence": [_evidence("app/agents/orchestrator.py::run_interrupt_stream",
                                   "本题 trace 交回空，但配对孤儿 trace %s 里确有跨度 ⇒ 这一枚不许叫「直答」"
                                   % ", ".join(sorted(t for row in sibling for t in row["orphan_traces"]))),
                         _evidence("app/common/stage_timing.py::samples_from_events",
                                   "跨度挂在另一枚 trace_id 上，本题事件名册里自然没有 generate")],
        })
    unregistered = []
    for spec in LEG_ACCOUNT_SPECS:
        hits = sum(1 for row in questions
                   if (row.get("unregistered_accounts") or {}).get(spec["stage"], {}).get("events", {}).get(
                       spec["event_type"]))
        if hits:
            unregistered.append({"event_type": spec["event_type"], "stage": spec["stage"],
                                 "duration_path": spec["duration_path"], "questions": hits,
                                 "emitters": facts["leg_account_emitters"].get(spec["event_type"], [])})
    if unregistered:
        questions_with_account = sum(1 for row in questions if row.get("unregistered_accounts"))
        out.append({
            "scope": "并行账（发了但在册尺不认）", "stages": sorted({row["stage"] for row in unregistered}),
            "predicate": "事件名不在 FINISHED_EVENTS（AST 现读 = %s）而载荷带 duration"
                         % sorted(facts["finished_events"]),
            "questions": questions_with_account,
            "detail": unregistered,
            "evidence": [_evidence("app/common/stage_timing.py::FINISHED_EVENTS",
                                   "只认 model.finished / tool_call.finished / stage.finished 三枚事件名")],
        })
    return out


def _events_of(row: Mapping[str, Any], groups: Mapping[str, list[dict[str, Any]]]) -> list[Mapping[str, Any]]:
    for item in groups[GROUP_ASKED]:
        if item["trace_id"] == row["trace_id"]:
            return item["rows"]
    return []


def validate_claims(claims: Sequence[Mapping[str, Any]], rows_by_trace: Mapping[str, Mapping[str, Any]],
                    canonical: Sequence[str]) -> dict[str, int]:
    """每条归因都必须承重：没凭据、型别不在三型内、或型 C 拿不出该题自己的剔除读数 —— 当场拒。"""
    tally = {name: 0 for name in MISSING_TYPES}
    for claim in claims:
        stage = str(claim.get("stage") or "")
        if stage not in canonical:
            raise EvidenceError("归因点到一段不在册的 %s（在册：%s）" % (stage, ", ".join(canonical)))
        kind = str(claim.get("type") or "")
        if kind not in MISSING_TYPES:
            raise EvidenceError("%s/%s 的型别 %s 不在三型之内" % (claim.get("key"), stage, kind))
        evidence = list(claim.get("evidence") or [])
        if not evidence:
            raise EvidenceError("%s 的 %s 段写成 %s，但一枚凭据都没有 ⇒ 不许上账"
                                % (claim.get("key"), stage, kind))
        for item in evidence:
            if not str(item.get("symbol") or "") or not str(item.get("reading") or ""):
                raise EvidenceError("%s/%s 的凭据缺 symbol 或现读取数：%s" % (claim.get("key"), stage, item))
        if kind == TYPE_NO_EVENT and str(claim.get("shape") or "") not in NO_EVENT_SHAPES:
            raise EvidenceError("%s/%s 写成 no_event 却没有四形之一的形：%s" % (claim.get("key"), stage, claim.get("shape")))
        if kind == TYPE_NESTED_OUT:
            row = rows_by_trace.get(str(claim.get("trace_id") or ""))
            detail = ((row or {}).get("stages") or {}).get(stage) or {}
            if not int(detail.get("excluded_count") or 0):
                raise EvidenceError(
                    "%s/%s 声称「被嵌套/重叠剔除」，但该题自己那份报告 excluded_count=%s、measured_count=%s "
                    "⇒ 没有剔除这回事，改回它该有的型别" % (claim.get("key"), stage,
                        detail.get("excluded_count"), detail.get("measured_count")))
            if not str(detail.get("claim", {}).get("evidence", [{}])[0].get("reading") or ""):
                raise EvidenceError("%s/%s 的剔除凭据没有现读取数" % (claim.get("key"), stage))
        tally[kind] += 1
    return tally


# ==================== 多窗与印面 ====================


def collect_many(windows: Sequence[str], directory: Path | str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    return [build_window(window, directory, **kwargs) for window in windows]


def _word(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render(data: Mapping[str, Any], max_rows: int = 200) -> list[str]:
    canonical = tuple(data["source_facts"]["canonical_stages"])
    totals = data["totals"]
    out: list[str] = []
    out.append("# R636 覆盖面账 —— 窗 %s（目录 %s）" % (data["window"], data["directory"]))
    out.append("")
    out.append("## 抬头（这格欠的不是再量一次误差，是覆盖面）")
    out.append("- R631 现跑：%s ｜ 判据线 < %s%% ｜ 对齐线 < %s%%" % (
        data["criterion"]["r631_status"], data["criterion"]["threshold_pct"], data["criterion"]["align_pct"]))
    out.append("- 母集＝账本：%d 枚 trace 全部点名（asked %d ／ no_denominator %d ／ resumed_head %d ／ bare %d）"
               "｜ 与 R631 切分差 = %s" % (
                   data["universe"]["declared_distinct_traces"],
                   data["universe"]["counts"][GROUP_ASKED], data["universe"]["counts"][GROUP_NO_DENOM],
                   data["universe"]["counts"][GROUP_RESUMED_HEAD], data["universe"]["counts"][GROUP_BARE],
                   json.dumps(data["reference_gap"], ensure_ascii=False)))
    out.append("- Σ端到端 %s ms ｜ Σ分段进账 %s ms ｜ Σ缺口 %s ms（%s%%）" % (
        totals["end_to_end_ms"], totals["segment_sum_ms"], totals["gap_ms"], totals["gap_pct"]))
    out.append("- 缺口拆账：配对孤儿 trace %s ms（加得进）｜ int() 地板界 %s ms ｜ 残差 %s ms（占端到端 %s%%，"
               "这笔没有任何在册账可归）｜ 未登记并行账 worker 腿 %s ms、检索腿 %s ms（与在册跨度**重叠**，不许相加）" % (
                   totals["orphan_ms"], totals["truncation_bound_ms"], totals["residual_ms"],
                   totals["residual_pct_of_end_to_end"], totals["worker_leg_wall_ms"], totals["retrieval_leg_ms"]))
    out.append("")
    out.append("## 逐段覆盖面（题数按母集 %d 枚）" % totals["questions"])
    for stage in canonical:
        cell = data["stage_rollup"][stage]
        out.append("- %s：产账题数=%s ／ 缺账题数=%s ｜ 进账 %s ms ｜ 被剔 %s ms ｜ 缺账型别=%s" % (
            stage, cell["producing_questions"], cell["missing_questions"], cell["ledger_ms"],
            cell["excluded_ms"], json.dumps(cell["missing_types"], ensure_ascii=False)))
    out.append("")
    out.append("## 今天不产分段账的车道（每条都带谓词与现读命中数）")
    for entry in data["nonproducing_lanes"]:
        out.append("- 【%s】段=%s ｜ 命中 %s 枚 ｜ 谓词：%s" % (
            entry["scope"], ",".join(entry["stages"]), entry["questions"], entry["predicate"]))
    out.append("")
    out.append("## 逐枚账（车道 × 题号）")
    out.append("  题号          车道        端到端ms     进账ms     缺口ms    段数  缺段(型/形)                                  未决  配对孤儿ms")
    for row in data["questions"][:max_rows]:
        missing = " ".join("%s[%s%s]" % (
            stage, row["stages"][stage]["claim"]["type"][:3],
            ("/" + row["stages"][stage]["claim"]["shape"][:2]) if row["stages"][stage]["claim"]["shape"] else "")
            for stage in row["missing_stages"]) or "—"
        out.append("  %-13s %-11s %11s %10s %10s %5s  %-48s %5s %10s" % (
            row["key"], row["lane"], row["end_to_end_ms"], row["segment_sum_ms"], row["gap_ms"],
            row["segments"], missing, row["unresolved_pairs"], row["orphan_ms"]))
    if len(data["questions"]) > max_rows:
        out.append("  （表格截断：印面只摆前 %d 枚，判语按全量；全量见 --json）" % max_rows)
    out.append("")
    out.append("## no_denominator 逐枚点名（明账，一枚不摘）")
    for item in data["named"][GROUP_NO_DENOM]:
        out.append("- %s ｜ 原因码 %s ｜ 跨度 %s 枚合计 %s ms ｜ worker=%s ｜ 归题=%s（头 %s）" % (
            item["trace_id"], item["reason"], item["sample_count"], item["total_ms"],
            ",".join(w for w in item["workers"] if w), item["paired_to"] or "未归名",
            (item["paired_head_trace"] or "—")[:22]))
    out.append("- 未归名列数 = %d；原因分布 = %s" % (
        len(data["orphans"]["unpaired"]), json.dumps(data["orphans"]["reasons"], ensure_ascii=False)))
    out.append("")
    out.append("## 有分母却零跨度（R631 既不列 rows 也不列 skipped 的那一组）")
    for item in data["named"][GROUP_RESUMED_HEAD]:
        out.append("- %s ｜ 题号 %s ｜ lane=%r lane_source=%s ｜ 事件名册=%s" % (
            item["trace_id"], item["key"], item["lane"], item["lane_source"], ",".join(item["event_types"])))
    out.append("")
    out.append("> 本格只摆覆盖面与型别，不判 G-R51-1 绿不绿；判语权在总控。修复单的判据草案见 "
               "docs/testing/r636-stage-coverage-2026-10-04.md。")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R636：分段账覆盖面尺（只读、离线、零模型、零容器、零 PG、零连库）",
        epilog="退出码语义：\n" + "\n".join("  %d = %s" % (code, EXIT_CODE_MEANING[code])
                                           for code in sorted(EXIT_CODE_MEANING)))
    parser.add_argument("--window", action="append", required=True,
                        help="窗名，可多枚：--window run18 --window run19 --window run20k")
    parser.add_argument("--dir", default=str(default_directory()), help="仓外产物目录（默认 %%TEMP%%\\evalrun）")
    parser.add_argument("--json", action="store_true", help="整个读数倒成 JSON")
    parser.add_argument("--max-rows", type=int, default=200, help="印面表格最多摆几枚（判语按全量）")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    try:
        data = [build_window(window, directory) for window in args.window]
    except InputMissing as exc:
        print("🔴 量不到（RC=%d）：%s" % (EXIT_NO_INPUT, exc))
        return EXIT_NO_INPUT
    except DerivedError as exc:
        print("🔴 派生尺自证失败（RC=%d）：%s" % (EXIT_DERIVED, exc))
        return EXIT_DERIVED
    except UniverseError as exc:
        print("🔴 母集不诚实（RC=%d）：%s" % (EXIT_UNIVERSE, exc))
        return EXIT_UNIVERSE
    except EvidenceError as exc:
        print("🔴 归因没凭据（RC=%d）：%s" % (EXIT_EVIDENCE, exc))
        return EXIT_EVIDENCE
    except MismatchError as exc:
        print("🔴 与 R631 对不上（RC=%d）：%s" % (EXIT_MISMATCH, exc))
        return EXIT_MISMATCH
    if args.json:
        print(json.dumps(data if len(data) > 1 else data[0], ensure_ascii=False, indent=2, sort_keys=True,
                         default=lambda item: list(item) if isinstance(item, set) else str(item)))
    else:
        for window_data in data:
            out = render(window_data, max_rows=args.max_rows)
            tally = validate_claims(window_data["claims"],
                                    {row["trace_id"]: row for row in window_data["questions"]},
                                    tuple(window_data["source_facts"]["canonical_stages"]))
            out.append("")
            out.append("## 凭据校验（validate_claims 现读）：归因 %d 条，型别分布 %s ⇒ %s" % (
                len(window_data["claims"]), json.dumps(tally, ensure_ascii=False), _word(True)))
            for line in out:
                print(line)
            print("")
    print("退出码：0 ｜ %s" % EXIT_CODE_MEANING[EXIT_OK])
    return EXIT_OK


__all__ = [
    "Claim", "DerivedError", "EvidenceError", "EXIT_CODE_MEANING", "InputMissing",
    "EXIT_DERIVED", "EXIT_EVIDENCE", "EXIT_MISMATCH", "EXIT_NO_INPUT", "EXIT_OK", "EXIT_UNIVERSE",
    "MISSING_TYPES", "MismatchError", "NO_EVENT_SHAPES", "StageSample", "TYPE_IN_LEDGER",
    "TYPE_NESTED_OUT", "TYPE_NO_EVENT", "TYPE_UNRECOGNIZED", "UNIVERSE_GROUPS", "UniverseError",
    "aggregate_stage_latency", "build_window", "call_sites_of", "classify_missing",
    "collect_many", "default_directory", "duration_from_payload", "emitter_symbols_for_event",
    "facts_request_terminals", "identityless_model_sites", "load_r631", "main",
    "unregistered_accounts", "unregistered_stage_of",
    "module_uses_symbols", "nonproducing_lanes", "orphan_profile", "pair_orphans", "read_inputs",
    "render", "request_started_row", "sample_stage_from_samples", "source_facts",
    "stage_of_unregistered_payload", "validate_claims",
]


if __name__ == "__main__":
    raise SystemExit(main())