"""R51 judgement 3 and 5: observation must not change behaviour, and must stay offline.

The claim being tested is narrow and absolute: with the collector on, off, broken, or
without a store, the persisted trace events are the same bytes, the answer is the same
bytes, and the duration attributed to a segment is the same number. Freezing the span
clock is what makes "same bytes" checkable rather than "same shape".
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import socket
import subprocess
import time as _real_time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.common import stage_timing
from app.common.stage_timing import (
    CANONICAL_STAGES,
    aggregate_stage_latency,
    default_stage_ledger,
    record_stage_sample,
    reset_stage_ledger,
    stage_latency_readout,
    stage_timing_enabled,
    stage_window,
    with_stage_latency,
)

OWNER = "u-r51"
TRACE_ID = "trace-passive"
REQUEST_ID = "request-passive"


def reset_clock() -> None:
    """Rewind both clocks, so two runs of the same call produce the same bytes."""
    _FakeDateTime._cursor = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    _FakeUuid.reset()


class _Frozen:
    """What the fixture hands out, so a test can pin one span to the fake clock."""

    def __init__(self, time, step_ms: float):
        self._time = time
        self.step_ms = step_ms
        self.stamp = "2026-09-18T06:00:00+00:00"

    def freeze(self, span):
        """Pin a freshly opened span so ``finish`` reports exactly ``step_ms``."""
        span.monotonic_start = self._time.next_value() - self.step_ms / 1000.0
        span.started_at = self.stamp
        return span


class _FakeTime:
    """A monotonic clock the tests can step.

    It starts above the real clock because ``ExecutionSpan`` takes its start time from a
    dataclass default factory, which no monkeypatch can reach: a span opened by code this
    test does not control still gets a plausible positive duration, while a frozen span
    gets exactly ``step_ms``.
    """

    def __init__(self, step_ms: float = 250.0):
        self._now = math.floor(_real_time.monotonic()) + 10_000.0
        self._step = step_ms / 1000.0

    def next_value(self) -> float:
        return self._now

    def monotonic(self) -> float:
        value = self._now
        self._now += self._step
        return value

    def time(self) -> float:
        return self.monotonic()


class _FakeDateTime:
    """Wall clock for spans and the store, advancing one second per reading."""

    _cursor = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    _step = timedelta(seconds=1)

    @classmethod
    def now(cls, tz=None):
        value = cls._cursor
        cls._cursor = cls._cursor + cls._step
        return value

    @classmethod
    def fromisoformat(cls, text):
        return datetime.fromisoformat(text)


class _FakeUuid:
    _n = 0

    @classmethod
    def reset(cls):
        cls._n = 0

    def __call__(self):
        _FakeUuid._n += 1
        return type("_Id", (), {"hex": "id%04d" % self._n})()


@pytest.fixture
def frozen_clock(monkeypatch):
    from app.trace import spans, store as store_module

    fake_time = _FakeTime()
    reset_clock()
    monkeypatch.setattr(spans, "time", fake_time)
    monkeypatch.setattr(spans, "_utc_now", lambda: "2026-09-18T06:00:00+00:00")
    monkeypatch.setattr(spans, "uuid4", _FakeUuid())
    monkeypatch.setattr(store_module, "datetime", _FakeDateTime)
    return _Frozen(fake_time, 250.0)


@pytest.fixture
def store(tmp_path, monkeypatch, frozen_clock):
    from app.trace.store import TraceStore

    instance = TraceStore(tmp_path / "events.jsonl")
    from app.trace import spans

    monkeypatch.setattr(spans, "default_trace_store", lambda: instance)
    return instance


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    reset_stage_ledger()
    yield
    reset_stage_ledger()


def _config(worker: str = ""):
    from app.agents.contracts import Principal

    configurable = {
        "principal": Principal(user_id=OWNER, username="staff1", roles=["staff"], department="研发部"),
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }
    if worker:
        configurable["worker"] = worker
    return {"configurable": configurable}


def _one_model_call(stage_tier: str = "plan", frozen=None):
    from app.trace.spans import start_model_call

    span = start_model_call(
        _config(), provider="ollama", model_name="qwen3.5:9b", model_tier=stage_tier
    )
    if frozen is not None:
        frozen.freeze(span)
    return span.finish("completed")


#: The three fields a span legitimately stamps from the wall clock. Everything else an
#: event carries is a value the business path chose, so it must survive unchanged.
VOLATILE = ("timestamp", "started_at", "completed_at")


def _normalized_lines(path) -> list[str]:
    """Every event of one run, with only the clock fields set aside."""
    lines = []
    for line in io.open(path, encoding="utf-8").read().splitlines():
        event = json.loads(line)
        for key in VOLATILE:
            event.pop(key, None)
            (event.get("payload") or {}).pop(key, None)
        lines.append(json.dumps(event, sort_keys=True, ensure_ascii=False))
    return lines


# ==================== judgement 3: the same bytes either way ====================


def _one_span_per_mode(tmp_path, monkeypatch, frozen, enabled: bool):
    """Write the same span twice, once with the collector on and once off.

    The clock and the identifiers are frozen, so the two files are comparable byte for
    byte: any difference the collector makes -- a key added, a duration nudged, an event
    reordered -- shows up as a hash mismatch instead of a judgement call.
    """
    from app.trace.store import TraceStore

    reset_stage_ledger()
    reset_clock()
    if enabled:
        monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    else:
        monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")
    name = "on.jsonl" if enabled else "off.jsonl"
    instance = TraceStore(tmp_path / name)
    from app.trace import spans

    monkeypatch.setattr(spans, "default_trace_store", lambda: instance)
    payload = _one_model_call(frozen=frozen)
    return instance, payload


def test_a_finished_span_writes_the_same_events_with_the_collector_on_and_off(
    tmp_path, monkeypatch, frozen_clock
) -> None:
    on_store, on_payload = _one_span_per_mode(tmp_path, monkeypatch, frozen_clock, True)
    on_samples = len(default_stage_ledger().samples())
    on_lines = _normalized_lines(on_store.path)
    off_store, off_payload = _one_span_per_mode(tmp_path, monkeypatch, frozen_clock, False)
    off_samples = len(default_stage_ledger().samples())
    off_lines = _normalized_lines(off_store.path)

    assert on_samples == 1
    assert off_samples == 0
    # Same events, same order, same bytes once the three clock fields are set aside: the
    # collector added no key and changed no value on the way past.
    assert on_lines == off_lines
    assert hashlib.sha256("\n".join(on_lines).encode("utf-8")).hexdigest() == hashlib.sha256(
        "\n".join(off_lines).encode("utf-8")
    ).hexdigest()
    # The timing attribution is the number an operator reads, so it is compared exactly.
    assert on_payload == off_payload
    assert on_payload["duration_ms"] == 250


def test_the_new_segment_keys_are_written_only_when_a_caller_supplies_them(store, frozen_clock) -> None:
    """An unstamped call keeps the payload it always had; a stamped one adds, never renames."""
    from app.trace.spans import start_model_call

    plain = start_model_call(_config(), provider="ollama", model_name="m")
    frozen_clock.freeze(plain).finish("completed")
    stamped = start_model_call(
        _config(), provider="ollama", model_name="m", model_tier="rewrite", stage="rewrite"
    )
    frozen_clock.freeze(stamped).finish("completed")

    finished = [
        event
        for event in store.replay(TRACE_ID)
        if event["event_type"] == "model.finished"
    ]
    old, new = finished[0]["payload"], finished[1]["payload"]

    assert "stage" not in old and "model_tier" not in old
    assert new["stage"] == "rewrite" and new["model_tier"] == "rewrite"
    assert set(old) < set(new)


def test_a_collector_that_raises_cannot_break_the_span_or_the_event(
    store, monkeypatch, frozen_clock
) -> None:
    def explode(**kwargs):
        raise RuntimeError("collector is on fire")

    monkeypatch.setattr(stage_timing, "record_stage_sample", explode)

    payload = _one_model_call(frozen=frozen_clock)

    assert payload["status"] == "completed"
    assert payload["duration_ms"] == 250
    assert len([event for event in store.replay(TRACE_ID) if event["event_type"] == "model.finished"]) == 1
    assert len(default_stage_ledger().samples()) == 0


def test_a_store_that_is_unavailable_still_lets_the_span_finish(
    store, monkeypatch, frozen_clock
) -> None:
    from app.trace import spans

    def broken():
        raise OSError("trace volume is gone")

    monkeypatch.setattr(spans, "default_trace_store", broken)

    payload = _one_model_call(frozen=frozen_clock)

    assert payload["status"] == "completed"
    assert payload["duration_ms"] == 250
    assert not store.path.exists()


def test_the_model_answer_is_the_same_bytes_with_observation_on_and_off(store, monkeypatch) -> None:
    """The judgement in the only place a customer feels it: the answer text."""
    from langchain_core.messages import AIMessage, HumanMessage

    import app.agents.nodes as nodes
    from app.common.model_budget import model_tier_budget

    class _Primary:
        model_name = "qwen3.5:9b"

        def invoke(self, messages, config=None, **kwargs):
            return AIMessage(content="标准回款周期是 30 天。")

        def bind_tools(self, tools):
            return self

    def _answer() -> str:
        model = nodes._ResilientModel(
            _Primary(), provider="ollama", model_name="qwen3.5:9b", budget=model_tier_budget("analysis")
        )
        response = model.invoke([HumanMessage(content="回款周期")], config=_config(worker="doc"))
        return str(response.content)

    monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    on = _answer()
    on_samples = len(default_stage_ledger().samples())
    reset_stage_ledger()
    monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")
    off = _answer()

    assert on_samples == 1
    assert len(default_stage_ledger().samples()) == 0
    assert on.encode("utf-8") == off.encode("utf-8")
    # Each call writes a started and a finished event; observation adds neither.
    assert [event["event_type"] for event in store.replay(TRACE_ID)] == [
        "model.started",
        "model.finished",
        "model.started",
        "model.finished",
    ]


def test_an_anonymous_span_is_not_attributed_to_any_segment(store, monkeypatch) -> None:
    from app.trace.spans import start_model_call

    monkeypatch.setitem(_config()["configurable"], "principal", None)
    span = start_model_call({"configurable": {"request_id": REQUEST_ID}}, provider="ollama", model_name="m")
    span.finish("completed")

    assert default_stage_ledger().samples() == []
    assert store.replay("") == []
    assert not store.path.exists()


def _two_lifecycle_events(tmp_path, name: str) -> bytes:
    from app.trace.store import TraceStore

    reset_clock()
    instance = TraceStore(tmp_path / name)
    instance.record_event(
        trace_id=TRACE_ID,
        request_id=REQUEST_ID,
        event_type="request.started",
        status="running",
        payload={},
    )
    instance.record_event(
        trace_id=TRACE_ID,
        request_id=REQUEST_ID,
        event_type="request.completed",
        status="completed",
        payload={},
    )
    return io.open(instance.path, "rb").read()


def test_the_request_window_is_counted_without_changing_the_events(monkeypatch, tmp_path) -> None:
    """The window is a memory of two timestamps the store already wrote."""
    from app.trace import store as store_module

    monkeypatch.setattr(store_module, "datetime", _FakeDateTime)
    reset_stage_ledger()
    on_bytes = _two_lifecycle_events(tmp_path, "window-on.jsonl")
    on_windows = dict(default_stage_ledger().request_windows())

    monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")
    reset_stage_ledger()
    off_bytes = _two_lifecycle_events(tmp_path, "window-off.jsonl")

    assert on_windows[TRACE_ID] == pytest.approx(1000.0, abs=1.0)
    assert default_stage_ledger().request_windows() == {}
    assert on_bytes == off_bytes




def test_a_full_run_of_segments_reproduces_the_latency_budget_shape(store, frozen_clock) -> None:
    """End to end against the sum, on spans produced by the real boundary code."""
    from app.trace.spans import record_stage_event, start_model_call, start_tool_call

    events = [
        ("classify", "plan", 81.0),
        ("classify", "analysis", 27_797.0),
    ]
    for stage, tier, _ in events:
        span = start_model_call(_config(), provider="ollama", model_name="m", model_tier=tier)
        frozen_clock.freeze(span).finish("completed")
    with start_tool_call(_config(), tool_name="search_docs", arguments={"query": "回款"}) as span:
        frozen_clock.freeze(span).finish("completed", summary={"hit_count": 1})
    worker = start_model_call(
        _config(worker="doc"), provider="ollama", model_name="m", model_tier="analysis"
    )
    frozen_clock.freeze(worker).finish("completed")
    reflect = record_stage_event(_config(), stage="reflect", duration_ms=33)

    samples = stage_timing.samples_from_events(store.replay(TRACE_ID))
    total = sum(sample.duration_ms for sample in samples if sample.source != "model_calls")
    report = aggregate_stage_latency(samples, end_to_end_ms=total + 33)

    assert reflect["duration_ms"] == 33
    assert [sample.stage for sample in samples].count("classify") == 2
    assert report["stages"]["reflect"]["count"] == 1
    assert report["stages"]["retrieve"]["count"] == 1
    assert report["stages"]["generate"]["count"] == 1
    assert report["coverage"]["requests"] == 0


def test_record_stage_event_writes_one_event_and_one_sample(store, frozen_clock) -> None:
    from app.trace.spans import record_stage_event

    payload = record_stage_event(_config(), stage="reflect", duration_ms=42, tier="chat")

    finished = [event for event in store.replay(TRACE_ID) if event["event_type"] == "stage.finished"]

    assert payload["duration_ms"] == 42
    assert len(finished) == 1
    assert finished[0]["payload"]["stage"] == "reflect"
    assert finished[0]["payload"]["record_kind"] == "stage_windows"
    assert default_stage_ledger().samples()[0].stage == "reflect"
    assert default_stage_ledger().samples()[0].tier == "chat"


def test_a_window_that_raises_still_records_and_still_propagates_the_error() -> None:
    with pytest.raises(ValueError):
        with stage_window("reflect", trace_id=TRACE_ID):
            raise ValueError("the segment itself failed")

    assert default_stage_ledger().samples()[0].stage == "reflect"


def test_a_window_does_not_record_when_observation_is_off(monkeypatch) -> None:
    monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")

    with stage_window("reflect", trace_id=TRACE_ID):
        pass

    assert default_stage_ledger().samples() == []


def test_the_health_block_adds_keys_and_keeps_the_old_ones() -> None:
    record_stage_sample(stage="classify", duration_ms=10.0, trace_id="a")

    block = with_stage_latency({"count": 1, "average_ms": 12.0, "p95_ms": 12.0, "error_rate": 0.0})

    assert block["count"] == 1
    assert block["average_ms"] == 12.0
    assert block["p95_ms"] == 12.0
    assert block["error_rate"] == 0.0
    assert block["stages"]["classify"]["p95_ms"] == 10.0
    assert set(CANONICAL_STAGES) <= set(block["stages"])


def test_a_broken_ledger_cannot_break_the_health_block(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("ledger is gone")

    monkeypatch.setattr(stage_timing.default_stage_ledger(), "report", explode)

    block = with_stage_latency({"count": 1})

    assert block["count"] == 1
    assert block["stage_latency_error"] == "RuntimeError"


# ==================== judgement 5: offline, no new dependency, no forbidden reach ====================


def test_the_stage_module_imports_only_the_standard_library_and_this_project() -> None:
    """Judgement 5, read off the import statements rather than off a belief."""
    source = io.open("app/common/stage_timing.py", encoding="utf-8").read()
    tree = ast.parse(source)
    imported = set()
    deep = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
            deep.add(node.module)

    assert imported <= {"__future__", "contextlib", "dataclasses", "datetime", "os", "re", "threading", "time", "typing", "app"}, imported
    engines = {
        "chromadb", "httpx", "requests", "socket", "sqlite3", "pandas",
        "numpy", "matplotlib", "sqlalchemy", "redis", "langchain", "langgraph", "ollama",
    }
    assert not (imported & engines), sorted(imported & engines)
    # And it stays inside its own layer: no retrieval engine, no route, no agent graph.
    assert not [
        name for name in deep if name.startswith(("app.rag", "app.api", "app.agents.orchestrator"))
    ], sorted(deep)


def test_the_readout_opens_no_socket_and_imports_no_engine(monkeypatch) -> None:
    def refuse(*args, **kwargs):
        raise AssertionError("observation must not open a socket")

    monkeypatch.setattr(socket.socket, "__init__", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    record_stage_sample(stage="generate", duration_ms=5.0, trace_id="t")

    report = stage_latency_readout()
    block = with_stage_latency({})

    assert report["stages"]["generate"]["count"] == 1
    assert block["stages"]["generate"]["count"] == 1
TRUNK_CANDIDATES = ("codex/data-file-catalog", "origin/codex/data-file-catalog", "master", "origin/master", "trunk")
FORBIDDEN_PREFIXES = ("pyproject.toml", "uv.lock", "migrations/", "frontend/", "app/rag/", "docs/", "tests/conftest.py")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def _current_branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def _branch_point(repo: Path) -> str:
    """Where this branch left the trunk; the only baseline that can attribute a path to a ticket."""
    for ref in TRUNK_CANDIDATES:
        try:
            base = _git(repo, "merge-base", "HEAD", ref).strip()
        except subprocess.CalledProcessError:
            continue
        if base:
            return base
    return _head(repo)


def _worktree_diff(repo: Path) -> list[str]:
    """The pre-R87 view: tracked changes only, whole worktree, branch point ignored."""
    return [line.strip() for line in _git(repo, "diff", "--name-only", "HEAD").splitlines() if line.strip()]


def _ticket_scope(repo: Path) -> tuple[list[str], str]:
    """What the ticket is answerable for: its own commits, plus its own untracked files.

    R87 replaced a worktree-wide ``git diff --name-only HEAD``. That view reds for another
    ticket's uncommitted work in a shared tree and, worse, is blind to untracked files, so a new
    ``docs/`` file could sit there invisible. The branch point is the baseline for the committed
    half, and untracked files count on any non-trunk branch. The trunk is named, not inferred
    from ``base != head``: a ticket branch that has not committed yet has both equal, and it
    still owes an accounting for what it dropped into the tree. On the trunk itself the committed
    scope is empty by construction and the untracked leftovers there belong to no ticket.
    """
    base = _branch_point(repo)
    listing = _git(repo, "diff", "--name-only", base, "HEAD")
    paths = [line.strip() for line in listing.splitlines() if line.strip()]
    if _current_branch(repo) not in TRUNK_CANDIDATES:
        others = _git(repo, "ls-files", "--others", "--exclude-standard")
        paths += [line.strip() for line in others.splitlines() if line.strip()]
    return paths, base


def _write(repo: Path, rel: str, text: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c", "user.name=t",
        "-c", "user.email=t@example.invalid",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", message,
    )


def _ticket_repo(tmp_path: Path) -> Path:
    """A throwaway repo (never the real tree) with a trunk commit and a ticket branch off it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet", "-b", "trunk")
    for rel in ("app/models/x.py", "docs/note.md", "frontend/app.js", "pyproject.toml"):
        _write(repo, rel, f"{rel}\n")
    _commit(repo, "trunk")
    _git(repo, "checkout", "-q", "-b", "ticket")
    return repo


def test_this_ticket_writes_no_dependency_manifest_no_migration_and_no_frontend() -> None:
    repo = Path(__file__).resolve().parents[1]
    try:
        changed, base = _ticket_scope(repo)
    except Exception:  # no git in the environment is not a judgement failure
        pytest.skip("git is unavailable")

    violations = sorted(path for path in changed if path.startswith(FORBIDDEN_PREFIXES))
    assert not violations, f"分支点 {base[:7]} 之后本单的提交与未跟踪件里不许出现越界路径：{violations}"


def test_another_tickets_uncommitted_change_cannot_turn_this_guard_red(tmp_path) -> None:
    """False-positive direction: shared-tree noise from someone else must not redden this guard."""
    repo = _ticket_repo(tmp_path)
    _write(repo, "tests/test_own.py", "def test_own():\n    assert True\n")
    _commit(repo, "own work")
    _write(repo, "docs/note.md", "somebody else's uncommitted work\n")

    assert "docs/note.md" in _worktree_diff(repo), "前提不成立：旧口径根本没被这次改动触发"
    changed, base = _ticket_scope(repo)
    assert base and base != _head(repo)
    assert not [path for path in changed if path.startswith(FORBIDDEN_PREFIXES)], changed


def test_this_tickets_own_untracked_file_cannot_hide_from_the_guard(tmp_path) -> None:
    """False-negative direction: an untracked docs/ file is invisible to git diff, not to this."""
    repo = _ticket_repo(tmp_path)
    _write(repo, "docs/sneaky.md", "never committed\n")

    assert _worktree_diff(repo) == [], "前提不成立：旧口径居然看得见未跟踪文件"
    changed, _ = _ticket_scope(repo)
    assert [path for path in changed if path.startswith(FORBIDDEN_PREFIXES)] == ["docs/sneaky.md"]


def test_a_committed_overreach_still_bites_after_narrowing(tmp_path) -> None:
    """Narrowing must not cost strength: the ticket's own commit set is still checked."""
    repo = _ticket_repo(tmp_path)
    _write(repo, "migrations/0002_extra.py", "def upgrade():\n    pass\n")
    _write(repo, "app/rag/sneak.py", "x = 1\n")
    _commit(repo, "overreach")

    changed, _ = _ticket_scope(repo)
    assert sorted(path for path in changed if path.startswith(FORBIDDEN_PREFIXES)) == [
        "app/rag/sneak.py",
        "migrations/0002_extra.py",
    ]


def test_the_trunk_keeps_the_guard_green_over_untracked_leftovers(tmp_path) -> None:
    """The trunk half of the asymmetry: untracked leftovers on the trunk are not this ticket's."""
    repo = _ticket_repo(tmp_path)
    _git(repo, "checkout", "-q", "trunk")
    _write(repo, "docs/trunk_leftover.md", "nobody owns this yet\n")

    changed, base = _ticket_scope(repo)
    assert base == _head(repo)
    assert [path for path in changed if path.startswith(FORBIDDEN_PREFIXES)] == []
