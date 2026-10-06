# -*- coding: utf-8 -*-
"""R674 常驻牙：按题 trace 事件件真能落盘、真能喂回 r631，而且缺段时必点名（全离线）。

对着的病：判据 R51②「端到端与分段加总误差 <1%」到今天不是「测出来不达标」，是**没有可测的输入**
——10-05 总控现取：scripts/r631_stage_sum_delta.py 对 run22／run23 各交 rc=3＝量不到。
这把尺有五种死法，本文件一枚一枚对着：
① 静默补 0：某段没货也写一枚 0 ms 的窗 ⇒ r631 照样出数，账面看着像量到了；
② 悄悄摘题：一题没落事件就当它不存在 ⇒ 母集变小，覆盖率看着升高；
③ 件喂不回去：导出的形状 r631 读不懂 ⇒ 落了一枚没用的件；
④ 反证牙单向：抹掉某一段尺子不红 ⇒ 它其实没在读段；
⑤ 桥不出题号还照样写件 ⇒ 一枚没有题号的件冒充「按题件」。

纪律：零服务、零模型、零容器、零连库、不跑全量门。本文件自己一行 app 都不 import；
唯一的 app 依赖是导出器懒读的在册识别器 app/common/stage_timing（它只靠 stdlib 与
app/common/performance），r631 那一腿一律走子进程，绝不在本进程里拖产品 import 图。
合成载荷刻意不带 payload.question：带着它 samples_from_span_payload 会去问 R42 判别器
（同形状的先例见 tests/test_r636_stage_coverage.py）。
"""

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import pytest

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "r674_window_trace_export", REPO / "scripts" / "r674_window_trace_export.py")
exporter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exporter  # dataclass 要能从 sys.modules 找回本模块，否则当场炸
SPEC.loader.exec_module(exporter)

R631 = REPO / "scripts" / "r631_stage_sum_delta.py"
#: r631 自己的退出码表（scripts/r631_stage_sum_delta.py::EXIT_CODE_MEANING）里「量不到」＝3。
#: 本件不 import 那枚文件（它拖着 app 的 import 图），所以在这里按在册语义写死这一枚数，
#: 由下面三枚 r631 子进程用例当场验它——尺改了码，用例就红，不会悄悄对不上。
R631_NO_INPUT = 3
CANONICAL = ("classify", "rewrite", "retrieve", "generate", "reflect")
BASE = datetime(2026, 10, 5, tzinfo=timezone.utc)
WINDOW = "runz"


def _iso(ms: float) -> str:
    return (BASE + timedelta(milliseconds=ms)).isoformat()


def _started(trace_id: str, session_id: str, offset_ms: float = 0.0) -> dict:
    return {"trace_id": trace_id, "request_id": "req-" + trace_id[-6:], "task_id": "task-" + trace_id[-6:],
            "sequence": 1, "timestamp": _iso(offset_ms), "event_type": "request.started",
            "status": "running", "owner_id": "evalbot",
            "payload": {"session_id": session_id, "lane": "qa", "tier": "chat", "owner_id": "evalbot"}}


def _terminal(trace_id: str, offset_ms: float) -> dict:
    return {"trace_id": trace_id, "request_id": "req-" + trace_id[-6:], "task_id": "task-" + trace_id[-6:],
            "sequence": 90, "timestamp": _iso(offset_ms), "event_type": "request.completed",
            "status": "completed", "owner_id": "evalbot", "payload": {"session_id": ""}}


def _span(trace_id: str, event_type: str, record_id: str, *, stage: str = "", tool: str = "",
          tier: str = "", worker: str = "", duration_ms: int, start_ms: float, sequence: int) -> dict:
    """一枚真发过的跨度：payload 的形状照 app/trace/spans.py::record_stage_event 与在册事件件。"""
    payload = {"record_id": record_id, "record_kind": "stage_windows" if stage else "model_calls",
               "status": "completed", "duration_ms": int(duration_ms),
               "started_at": _iso(start_ms), "completed_at": _iso(start_ms + int(duration_ms))}
    if stage:
        payload["stage"] = stage
    if tool:
        payload["tool_name"] = tool
    if tier:
        payload["model_tier"] = tier
    if worker:
        payload["worker"] = worker
    return {"trace_id": trace_id, "request_id": "req-" + trace_id[-6:], "task_id": "task-" + trace_id[-6:],
            "sequence": sequence, "timestamp": _iso(start_ms + int(duration_ms)),
            "event_type": event_type, "status": "completed", "owner_id": "evalbot", "payload": payload}


#: 五段各自的形状：段名 → (事件名, 载荷关键字)。名单真源＝app/common/stage_timing.py::CANONICAL_STAGES。
STAGE_SHAPES = {
    "classify": ("model.finished", {"tier": "analysis"}),
    "rewrite": ("model.finished", {"tier": "rewrite"}),
    "retrieve": ("tool_call.finished", {"tool": "search_docs", "worker": "doc"}),
    "generate": ("model.finished", {"tier": "analysis", "worker": "doc"}),
    "reflect": ("stage.finished", {"stage": "reflect"}),
}
STAGE_OFFSETS = {"classify": (100.0, 2000), "rewrite": (2200.0, 2000), "retrieve": (4300.0, 6000),
                 "generate": (11000.0, 4000), "reflect": (15100.0, 300)}


def _question_events(trace_id: str, session_id: str, *, drop: Sequence = ()) -> list[dict]:
    events = [_started(trace_id, session_id)]
    sequence = 2
    for name in CANONICAL:
        if name in tuple(drop):
            continue
        event_type, kwargs = STAGE_SHAPES[name]
        start_ms, duration = STAGE_OFFSETS[name]
        events.append(_span(trace_id, event_type, "%s:%s" % (session_id, name),
                            duration_ms=duration, start_ms=start_ms, sequence=sequence, **kwargs))
        sequence += 1
    events.append(_terminal(trace_id, 20000.0))
    return events


def synth_window(directory: Path, *, questions=("doc-01", "doc-03"), dropped: Sequence = (),
                 extra_events: Sequence[dict] = ()) -> dict[str, Path]:
    """造一扇合成的窗：事件件 + sidecar（一行一发）+ frames（session_id ↔ 题号）。"""
    directory.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    frames: list[dict] = []
    sidecar: list[dict] = []
    for position, question in enumerate(questions):
        trace_id = "trace-%s" % question.replace("-", "")
        session_id = "sess-%s" % question
        events.extend(_question_events(trace_id, session_id, drop=dropped))
        frames.append({"id": question, "session_id": session_id, "attempt": 1, "kind": "ok",
                       "ts": "2026-10-05 20:0%d:00" % position})
        total = sum(STAGE_OFFSETS[name][1] for name in CANONICAL if name not in tuple(dropped))
        sidecar.append({"id": question, "kind": "ok", "attempt": 1,
                        "wall_ms": round(total * 1.18 + 137.0, 1), "ts": "2026-10-05 20:0%d:00" % position,
                        "answer_chars": 400})
    events.extend(list(extra_events))
    paths = {
        "events": directory / ("%s-events.jsonl" % WINDOW),
        "sidecar": directory / ("%s-sidecar.jsonl" % WINDOW),
        "frames": directory / ("%s-sidecar-frames.jsonl" % WINDOW),
    }
    _write_jsonl(paths["events"], events)
    _write_jsonl(directory / ("%s-sidecar.jsonl" % WINDOW), sidecar)
    _write_jsonl(directory / ("%s-sidecar-frames.jsonl" % WINDOW), frames)
    return paths


def _write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _r631_json(stdout: str) -> dict[str, Any]:
    """r631 的 --json 后面还跟着末行「退出码：n」⇒ 只解第一枚 JSON 本体，不倒掉读数的牙。"""
    value, _consumed = json.JSONDecoder().raw_decode(stdout.lstrip())
    return value


def _r631(argv: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(R631), *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300, check=False)


def _run_export(directory: Path, events: Path, *, out: Path | None = None, shadow: bool = True,
                questions_file: Path | None = None, extra: Sequence[str] = ()) -> int:
    argv = ["--window", WINDOW, "--dir", str(directory), "--events", str(events),
            "--out", str(out or (directory / "export" / ("%s-traces.jsonl" % WINDOW)))]
    if questions_file is not None:
        argv += ["--questions", str(questions_file)]
    if not shadow:
        argv.append("--no-shadow")
    return exporter.main(argv + list(extra))

# ==================== 判据 1：件的形状与「不许补 0」 ====================


def test_export_line_carries_question_trace_and_all_five_stage_windows(tmp_path):
    """逐行自足：每一行都带着 question_id／trace_id／五段各自的起止时刻（判据 1 的字面要求）。"""
    paths = synth_window(tmp_path)
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    assert _run_export(tmp_path, paths["events"], out=out, shadow=False) == exporter.RC_OK
    lines = _lines(out)
    events = _lines(paths["events"])
    assert len(lines) == len(events) + 2  # 一发一行凭据本体 + 该发逐枚事件各一行
    names = set(CANONICAL)
    for line in lines:
        assert line["question_id"] in {"doc-01", "doc-03"}
        assert line["trace_id"]
        assert line["window"] == WINDOW
        assert line["schema"] == exporter.SCHEMA
        assert set(line["stage_windows"]) == names
        assert line["missing_stages"] == []
        for name in names:
            window = line["stage_windows"][name]
            assert window is not None, name
            assert window["started_at"] and window["completed_at"], name
    ledgers = [line for line in lines if line["event_type"] == exporter.SHOT_DETAIL_EVENT_TYPE]
    assert len(ledgers) == 2 and all(line["sample_count"] == 5 for line in ledgers)
    for ledger in ledgers:
        details = ledger["stage_window_details"]
        assert set(details) == names
        for name in names:
            cell = details[name]
            assert cell["sample_count"] == 1 and cell["sum_duration_ms"] > 0, name
            assert cell["span_ms"] > 0 and cell["window_basis"] == "outermost_of_samples", name
            assert cell["samples"][0]["started_at"] and cell["samples"][0]["completed_at"], name
        assert ledger["end_to_end_ms"] and ledger["end_to_end_source"] == "sidecar_wall_ms"
        assert ledger["ts"]
    # 事件行本体不被本单的字段污染：载荷照原样带着 r631 认得的那几个键
    spans = [line for line in lines if line["event_type"].endswith(".finished")]
    assert len(spans) == 10
    assert all(line["payload"]["started_at"] and line["payload"]["duration_ms"] >= 0 for line in spans)


def test_r631_reads_the_same_artifact_as_its_segment_leg(tmp_path):
    """判据 2 的正向：喂这份件给 r631 必须交回可比枚数 ≥1，不再是 rc=3＝量不到。"""
    paths = synth_window(tmp_path)
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    assert _run_export(tmp_path, paths["events"], out=out, shadow=False) == exporter.RC_OK
    completed = _r631(["--window", WINDOW, "--dir", str(tmp_path),
                       "--traces", str(out), "--join", str(out), "--json"])
    assert completed.returncode != R631_NO_INPUT, completed.stdout[-2000:]
    data = _r631_json(completed.stdout)
    assert data["status"] == "measured"
    assert len(data["rows"]) >= 1
    assert data["quantiles"]["count"] >= 1
    assert sorted(data["ledger_view"]["missing_stages"]) == []
    assert set(data["ledger_view"]["stages"]) == set(CANONICAL)


def test_shadow_copy_lets_r631_find_the_artifact_with_bare_window(tmp_path):
    """夜窗队列那一格：r631 只带 --window 也能找到件——影子件与正本必须逐字节相同。"""
    paths = synth_window(tmp_path)
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    assert _run_export(tmp_path, paths["events"], out=out, shadow=True) == exporter.RC_OK
    shadow = tmp_path / ("%s-traces.jsonl" % WINDOW)
    assert exporter.sha256_of(shadow) == exporter.sha256_of(out)
    completed = _r631(["--window", WINDOW, "--dir", str(tmp_path), "--json"])
    assert completed.returncode != R631_NO_INPUT, completed.stdout[-2000:]
    data = _r631_json(completed.stdout)
    assert data["segment_leg"]["traces"] >= 1
    assert len(data["rows"]) >= 1


# ==================== 判据 1 的红字：缺段必须点名，且非零退出 ====================


@pytest.mark.parametrize("erased", CANONICAL)
def test_erasing_a_stage_names_it_and_exits_three(tmp_path, capsys, erased):
    """反证牙（负向·逐段各咬一次）：抹掉某一段 ⇒ 尺子 rc=3 并点名那一段，件里那格是 null 不是 0。"""
    paths = synth_window(tmp_path, dropped=(erased,))
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    rc = _run_export(tmp_path, paths["events"], out=out, shadow=False)
    assert rc == exporter.RC_MISSING_STAGE
    printed = capsys.readouterr().out
    assert erased in printed
    assert exporter.EXIT_CODE_MEANING[exporter.RC_MISSING_STAGE] in printed
    lines = _lines(out)
    for line in lines:
        assert line["stage_windows"][erased] is None
        assert erased in line["missing_stages"]
        assert line["stage_windows"][erased] != 0
    summary = exporter.collect(WINDOW, artifact_dir=tmp_path, event_paths=[paths["events"]])
    assert summary["coverage"]["stages"][erased]["shots_present"] == 0
    assert erased in summary["coverage"]["stages_absent_window_wide"]


def test_r631_still_says_no_input_when_every_segment_is_erased(tmp_path):
    """反证牙（双向的另一半）：分段腿整条抹光 ⇒ 同一把 r631 退回 rc=3，而不是拿空账出数。"""
    paths = synth_window(tmp_path, dropped=CANONICAL)
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    assert _run_export(tmp_path, paths["events"], out=out, shadow=False) == exporter.RC_MISSING_STAGE
    completed = _r631(["--window", WINDOW, "--dir", str(tmp_path),
                       "--traces", str(out), "--join", str(out), "--json"])
    assert completed.returncode == R631_NO_INPUT
    data = _r631_json(completed.stdout)
    assert data["status"] == "no_segments"
    assert data["segment_leg"]["samples"] == 0


def test_missing_stage_is_never_written_as_zero(tmp_path):
    """🔴 不许静默补 0／补估计值：缺的段一律 null，且件里一个「段的 0 ms 读数」都不许出现。"""
    paths = synth_window(tmp_path, dropped=("reflect",))
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    assert _run_export(tmp_path, paths["events"], out=out, shadow=False) == exporter.RC_MISSING_STAGE
    for line in _lines(out):
        window = line["stage_windows"]["reflect"]
        assert window is None
        if line["event_type"] not in (exporter.SHOT_DETAIL_EVENT_TYPE, exporter.NO_EVENTS_EVENT_TYPE):
            assert "duration_ms" not in line
            assert line["payload"].get("stage") != "reflect"
    assert [row for row in _lines(out) if isinstance(row["stage_windows"].get("reflect"), dict)] == []


def test_absent_question_is_named_not_dropped(tmp_path):
    """反证牙②：sidecar 里有题号、事件里一枚都没落 ⇒ 逐枚点名，母集不许缩水。"""
    paths = synth_window(tmp_path, questions=("doc-01",))
    extra = tmp_path / ("questions-%s.jsonl" % WINDOW)
    _write_jsonl(extra, [{"id": "doc-99"}, {"id": "doc-01"}])
    out = tmp_path / "export" / ("%s-traces.jsonl" % WINDOW)
    assert _run_export(tmp_path, paths["events"], out=out, shadow=False,
                       questions_file=extra) == exporter.RC_MISSING_STAGE
    lines = _lines(out)
    absent = [line for line in lines if line["event_type"] == exporter.NO_EVENTS_EVENT_TYPE]
    assert [line["question_id"] for line in absent] == ["doc-99"]
    assert all(value is None for value in absent[0]["stage_windows"].values())
    assert all(value is None for value in absent[0]["stage_window_details"].values())
    assert absent[0]["sample_count"] == 0 and absent[0]["events"] == 0
    assert absent[0]["missing_stages"] == list(CANONICAL)


def test_no_bridge_writes_no_artifact(tmp_path, capsys):
    """反证牙⑤：桥不出题号 ⇒ rc=4 且不写件——一枚没题号的件比没件更坏。"""
    directory = tmp_path / "bare"
    paths = synth_window(directory)
    orphan = [{"trace_id": "trace-orphan", "request_id": "req-o", "task_id": "task-o", "sequence": 1,
               "timestamp": _iso(0.0), "event_type": "model.finished", "status": "completed",
               "owner_id": "evalbot", "payload": {"record_id": "o", "duration_ms": 10,
                                                  "model_tier": "chat"}}]
    events = directory / "orphans.jsonl"
    _write_jsonl(events, orphan)
    out = directory / "export" / ("%s-traces.jsonl" % WINDOW)
    rc = exporter.main(["--window", WINDOW, "--dir", str(directory), "--events", str(events),
                        "--out", str(out)])
    assert rc == exporter.RC_NO_INPUT
    assert not out.exists()
    assert "桥不出任何题号" in capsys.readouterr().out


def test_invented_stage_window_is_refused(tmp_path):
    """反证牙①的形状自检：段窗非空却没有一枚跨度撑着 ⇒ ContractError，本件拒绝写出去。"""
    forged = [{"question_id": "doc-01", "event_type": exporter.SHOT_DETAIL_EVENT_TYPE,
               "stage_window_details": {
                   "classify": {"sample_count": 0, "sum_duration_ms": 12.0,
                                "started_at": _iso(0.0), "completed_at": _iso(12.0)}}}]
    with pytest.raises(exporter.ContractError):
        exporter.assert_no_invented_timings(forged, CANONICAL)
    half = [{"question_id": "doc-01", "event_type": exporter.SHOT_DETAIL_EVENT_TYPE,
             "stage_window_details": {
                 "classify": {"sample_count": 1, "sum_duration_ms": None,
                              "started_at": None, "completed_at": None}}}]
    with pytest.raises(exporter.ContractError):
        exporter.assert_no_invented_timings(half, CANONICAL)


# ==================== 坐标与出厂闸门 ====================


def test_default_artifact_paths_are_the_shape_the_ticket_names():
    """判据 1 点名的件位：docs/perf/raw/<窗号>/<窗号>-traces.jsonl；影子件落窗产物目录。"""
    names = exporter.artifact_names(Path("C:/somewhere/evalrun"), "run30")
    primary = names["out"]
    assert primary.suffix == ".jsonl"
    assert primary.name == "run30-traces.jsonl"
    assert primary.parent.name == "run30"
    assert str(exporter.RAW_DIR) in str(primary)
    assert names["shadow"].name == "run30-traces.jsonl"
    assert names["sidecar"].name == "run30-sidecar.jsonl"
    assert names["frames"].name == "run30-sidecar-frames.jsonl"


def test_postgres_leg_refuses_without_both_gates(tmp_path):
    """连库那一腿出厂即关：只给旗标不给开关 ⇒ 拒绝连库（零 docker 调用）。"""
    paths = synth_window(tmp_path)
    with pytest.raises(exporter.NoInput) as refused:
        exporter.read_events_from_postgres(artifact_dir=tmp_path, window=WINDOW,
                                           docker_bin="definitely-not-docker",
                                           container="c", user="u", database="d", opt_in="")
    assert exporter.PG_OPT_IN_ENV in str(refused.value)
    assert not paths["sidecar"].name.endswith(".json")  # 合成件在位，但腿根本没被调用


def test_session_list_is_shape_checked_before_it_reaches_sql():
    """PG 腿的语句由常量拼：session 名单先过形状闸，带引号或空格的串一律拒。"""
    sql = exporter.select_for_sessions(["sess-doc01", "sess-doc01", "sess_doc.02"])
    assert sql.count("SELECT") == 3  # 外层 + 事件 + agent_runs 桥
    assert "'sess-doc01'" in sql and sql.count("'sess-doc01'") == 1
    with pytest.raises(exporter.ContractError):
        exporter.select_for_sessions(["sess'; DROP TABLE trace_events; --"])
    with pytest.raises(exporter.NoInput):
        exporter.select_for_sessions([""])


def test_normalize_rejects_rows_without_identity():
    """事件行没有 trace_id ⇒ 分段腿无从归位：点名而不是静默丢掉一枚跨度。"""
    with pytest.raises(exporter.ContractError):
        exporter.normalize_event_row({"event_type": "model.finished", "payload": {}})
    with pytest.raises(exporter.ContractError):
        exporter.normalize_event_row({"trace_id": "trace-a", "payload": [1, 2]})


def test_collect_is_reusable_by_the_night_queue_without_writing(tmp_path):
    """collect() 只出读数不落盘：队列要在窗后先看读数再决定写不写件（--dry-run 同一道代码）。"""
    paths = synth_window(tmp_path)
    data: dict[str, Any] = exporter.collect(WINDOW, artifact_dir=tmp_path, event_paths=[paths["events"]])
    assert data["fully_covered"] is True
    assert data["shots"] == 2 and data["questions"] == 2
    assert data["bridge_source"] == "payload.session_id+frames"
    assert data["denominator_source"] == "sidecar_wall_ms"
    assert not (tmp_path / ("%s-traces.jsonl" % WINDOW)).exists()
    assert sorted(data["canonical_stages"]) == sorted(CANONICAL)
