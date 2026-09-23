"""R54: produce the recorded-answers file the quality runner consumes.

app/quality/runner.py only *reads* answers; nothing in the repo ever wrote them, so
the 105-question set could not be scored. This is that missing producer: it drives a
fixture through an injected transport and emits the JSONL the runner reads.

Output contract, verbatim against the reader:
  * app/quality/runner.py:22-28 parses each line and indexes it by str(item["id"]),
    so id/answer/evidence/latency_ms must be top-level keys;
  * app/quality/runner.py:44-48 answers any id it never saw with
    {"answer": "", "evidence": [], "latency_ms": None}. That turns "we never collected
    this" into "the model answered badly", so it must never fire for a real gap: the
    coverage gate below fails loudly instead of leaving holes to be filled in silently.
  * first_token_at / thinking_chars / tool_calls ride along for the R29 thinking tax and
    the R38 usage audit. Unknown is recorded as null; nothing is ever estimated.

R181 (2026-09-23) - where acceptance 2 (`text` frames) is persisted, and where it is not.
  The real-run transport measures every `event: text` frame it receives: a per-question frame
  count, the count of adjacent-frame prefix monotonicity breaks (cumulative semantics), and the
  missing/extra character counts between the last frame and the terminal answer. Consistency is
  judged with **covering** semantics (last frame startswith the answer), never strict equality.
  Readings ride one row per question into `<sidecar stem>-frames.jsonl` (`EVAL_FRAME_LEDGER`,
  scripts/eval_transport_ask_v2.py), joined by `id`, written in the same per-question step that
  writes the sidecar. They deliberately do NOT extend the answers lines below, nor the sidecar
  row: the payload key set is pinned by tests/test_r123_hitl_approval.py:205 and the sidecar
  extras by :243 - both outside R181's write domain - and run2..run5 answers files must stay
  question-for-question comparable. Observation only: `answer`, `APPROVAL_FAILED_SENTINEL`,
  `cached`, `first_token_at` and `steps` keep the exact values they had before R181.
  Criteria, the cache-hit single-frame reading and the two standing counter-proofs:
  docs/testing/r181-text-frame-readings.md.

Offline by construction: there is no built-in network transport. A real run must name one
with --transport module:callable; --dry-run supplies a fake transport instead. That fake
answers every question with the fixture gold text, and app/quality/eval.py:63-66 scores
must_contain (falling back to row["answer"] in text), so a sample file reads as a near
100% run - while neither app/quality/runner.py nor app/quality/eval.py ever looks at
answer_source. Hence --dry-run is fail-closed: it writes only when --allow-sample is set
together with an explicit --output, and it can never reach DEFAULT_OUTPUT. What a run
leaves behind for R36 is the report under docs/testing/, never an answers file.

    cd C:/Users/fengx/PycharmProjects/perf-lab
    python scripts/collect_evaluation_answers.py --dry-run --allow-sample --output $env:TEMP/answers.jsonl
    python scripts/run_quality_evaluation.py --fixture tests/fixtures/business_evaluation_100.jsonl --answers $env:TEMP/answers.jsonl --output docs/testing/evaluation-report.json
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
# Outside the repo on purpose: artifacts/ is not gitignored, .gitignore is frozen until H5
# closes, and a tracked answers blob would dirty every worktree and invite a stray git add.
DEFAULT_OUTPUT = Path(tempfile.gettempdir()) / "enterprise-brain-evaluation-answers.jsonl"

# The four keys app/quality/runner.py reads; a line without one of them is a broken
# product, not a scored answer.
RUNNER_REQUIRED_KEYS = ("id", "answer", "evidence", "latency_ms")
# R29 (thinking tax) and R38 (usage verification) need these per question.
TRACE_KEYS = ("first_token_at", "thinking_chars", "tool_calls")


class CollectionError(RuntimeError):
    """A transport result that cannot be trusted as a measured answer."""


class CoverageError(CollectionError):
    """The fixture ids and the collected ids do not line up."""

    def __init__(self, missing: list[str], unexpected: list[str]) -> None:
        self.missing = list(missing)
        self.unexpected = list(unexpected)
        parts = []
        if self.missing:
            parts.append(f"missing {len(self.missing)} fixture id(s): {', '.join(self.missing)}")
        if self.unexpected:
            parts.append(
                f"{len(self.unexpected)} collected id(s) not in the fixture: {', '.join(self.unexpected)}"
            )
        super().__init__("; ".join(parts) or "coverage gate failed")


def load_fixture_rows(path: str | Path) -> list[dict]:
    """Read an evaluation fixture the way app/quality/eval.py:69-74 does."""
    rows: list[dict] = []
    seen: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row_id = str(row.get("id", "")).strip()
        if not row_id:
            raise CollectionError(f"{path}: fixture row without an id at line {len(rows) + 1}")
        if row_id in seen:
            raise CollectionError(f"{path}: duplicate fixture id {row_id!r}")
        seen.add(row_id)
        rows.append(row)
    if not rows:
        raise CollectionError(f"{path}: fixture holds no rows")
    return rows

def _evidence(payload: dict, row_id: str) -> list:
    value = payload.get("evidence")
    if value is None:
        return []
    if not isinstance(value, list):
        raise CollectionError(f"{row_id}: evidence must be a list, got {type(value).__name__}")
    return value


def _counter(payload: dict, key: str, row_id: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CollectionError(f"{row_id}: {key} must be an integer or null, got {value!r}")
    if value < 0:
        raise CollectionError(f"{row_id}: {key} must not be negative, got {value}")
    return value


def _latency_ms(payload: dict, measured_ms: float, row_id: str) -> float:
    value = payload.get("latency_ms")
    if value is None:
        return round(measured_ms, 3)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CollectionError(f"{row_id}: latency_ms must be a number or null, got {value!r}")
    if value < 0:
        raise CollectionError(f"{row_id}: latency_ms must not be negative, got {value}")
    return float(value)


def _first_token_at(payload: dict, row_id: str) -> float | str | None:
    value = payload.get("first_token_at")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise CollectionError(f"{row_id}: first_token_at must be a timestamp or null, got {value!r}")
    return value


def build_answer(row: dict, payload: Any, *, measured_ms: float, answer_source: str) -> dict:
    """Normalise one transport result into a runner-readable answers line."""
    row_id = str(row["id"])
    if isinstance(payload, str):
        payload = {"answer": payload}
    if not isinstance(payload, dict):
        raise CollectionError(
            f"{row_id}: transport returned {type(payload).__name__}, expected a dict or a string"
        )
    answer: dict = {
        "id": row_id,
        "answer": str(payload.get("answer", "")),
        "evidence": _evidence(payload, row_id),
        "latency_ms": _latency_ms(payload, measured_ms, row_id),
        "first_token_at": _first_token_at(payload, row_id),
        "thinking_chars": _counter(payload, "thinking_chars", row_id),
        "tool_calls": _counter(payload, "tool_calls", row_id),
        # Which transport produced this line: a dry-run sample must never be mistaken for
        # a baseline, and app/quality/runner.py ignores keys it does not read.
        "answer_source": answer_source,
    }
    for optional in ("claims", "confidence", "confidence_label"):
        if optional in payload:
            answer[optional] = payload[optional]
    assert_line_contract(answer)
    return answer


def assert_line_contract(answer: dict) -> None:
    missing = [key for key in RUNNER_REQUIRED_KEYS if key not in answer]
    if missing:
        raise CollectionError(
            f"answer row {answer.get('id')!r} is missing key(s): {', '.join(missing)}"
        )
    if not isinstance(answer["evidence"], list):
        raise CollectionError(f"answer row {answer.get('id')!r} has non-list evidence")
    for key in TRACE_KEYS:
        if key not in answer:
            raise CollectionError(f"answer row {answer.get('id')!r} is missing trace key {key}")


def collect_answers(
    rows: list[dict],
    transport: Callable[[dict], Any],
    *,
    answer_source: str,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[list[dict], list[dict]]:
    """Run every fixture row through transport; never invent a substitute answer."""
    answers: list[dict] = []
    failures: list[dict] = []
    for row in rows:
        row_id = str(row["id"])
        started = clock()
        try:
            payload = transport(row)
        except Exception as exc:  # a lost question is a gap to report, not a reason to stop
            failures.append({"id": row_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        measured_ms = max(0.0, (clock() - started) * 1000.0)
        try:
            answer = build_answer(row, payload, measured_ms=measured_ms, answer_source=answer_source)
        except CollectionError as exc:
            failures.append({"id": row_id, "error": str(exc)})
            continue
        if not answer["answer"].strip():
            # An empty answer is exactly what app/quality/runner.py:23-27 synthesises for a
            # question nobody asked, so writing one would hide a gap behind a bad score.
            failures.append({"id": row_id, "error": "transport returned an empty answer"})
            continue
        answers.append(answer)
    return answers, failures

def assert_coverage(rows: list[dict], answers: list[dict]) -> None:
    """Completeness gate: the answers must cover the fixture, all of it."""
    expected = [str(row["id"]) for row in rows]
    produced = [answer["id"] for answer in answers]
    collected = set(produced)
    missing = [row_id for row_id in expected if row_id not in collected]
    unexpected = sorted(collected - set(expected))
    if len(produced) != len(collected):
        unexpected.append("<duplicate collected ids>")
    if missing or unexpected:
        raise CoverageError(missing, unexpected)


def write_answers(path: str | Path, answers: list[dict]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(answer, ensure_ascii=False) + "\n" for answer in answers)
    target.write_text(body, encoding="utf-8")
    return target


def build_dry_run_transport() -> Callable[[dict], Any]:
    """Fake transport: structurally complete sample answers, zero model calls."""

    def transport(row: dict) -> dict:
        gold = str(row.get("answer", ""))
        return {
            "answer": gold,
            "evidence": [
                {
                    "source_type": "dry_run",
                    "source_name": f"dry-run://{row['id']}",
                    "locator": None,
                    "excerpt": gold,
                }
            ],
            # This transport neither streams nor thinks, so the trace fields are unknown
            # rather than 0: a placeholder must not read as a measurement in R29/R38.
            "first_token_at": None,
            "thinking_chars": None,
            "tool_calls": None,
        }

    return transport


def load_transport(spec: str) -> Callable[[dict], Any]:
    """Resolve module:callable - the only way a real model ever gets called."""
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise CollectionError(f"--transport wants 'module:callable', got {spec!r}")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        target: Any = importlib.import_module(module_name)
    except Exception as exc:  # a bad spec is a usage error, not a traceback
        raise CollectionError(f"--transport {spec}: cannot import {module_name!r}") from exc
    for part in attribute.split("."):
        target = getattr(target, part, None)
        if target is None:
            raise CollectionError(f"--transport {spec}: no attribute {part!r}")
    if not callable(target):
        raise CollectionError(f"--transport {spec} is not callable")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect evaluation answers for app/quality/runner.py.",
    )
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument(
        "--output",
        help=f"answers JSONL to write (default: {DEFAULT_OUTPUT}, outside the repo)",
    )
    parser.add_argument(
        "--transport",
        help="dotted module:callable taking a fixture row, returning answer/evidence/trace fields",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="use a fake transport; writes sample answers only"
    )
    parser.add_argument(
        "--allow-sample",
        action="store_true",
        help="with an explicit --output, permit writing --dry-run sample answers",
    )
    args = parser.parse_args(argv)

    if args.dry_run and args.transport:
        parser.error("--dry-run already supplies a fake transport; drop --transport")
    if args.allow_sample and not args.dry_run:
        parser.error("--allow-sample only means something next to --dry-run")
    if not args.dry_run and not args.transport:
        # No implicit network: naming a transport is the opt-in.
        parser.error("pass --dry-run, or --transport module:callable for a real run")
    if args.dry_run and not (args.allow_sample and args.output):
        # Fail closed. A sample echoes the fixture gold answers, so a sample that reaches
        # the default path would be scored as a real baseline even though nothing in
        # app/quality/runner.py or app/quality/eval.py reads answer_source. Both switches
        # are the price of writing one anywhere.
        print(
            f"REFUSED: --dry-run needs --allow-sample and an explicit --output; sample"
            f" answers score ~100% and no reader checks answer_source, so {DEFAULT_OUTPUT}"
            " is never writable by a dry run",
            file=sys.stderr,
        )
        return 2

    output = Path(args.output) if args.output else DEFAULT_OUTPUT
    failures: list[dict] = []
    try:
        rows = load_fixture_rows(args.fixture)
        if args.dry_run:
            transport = build_dry_run_transport()
            answer_source = "dry-run"
        else:
            transport = load_transport(args.transport)
            answer_source = args.transport
        answers, failures = collect_answers(rows, transport, answer_source=answer_source)
        assert_coverage(rows, answers)
    except CoverageError as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        for failure in failures:
            print(f"  unanswered {failure['id']}: {failure['error']}", file=sys.stderr)
        print(f"nothing written to {output}", file=sys.stderr)
        return 1
    except CollectionError as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"GATE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    written = write_answers(output, answers)
    print(f"collected={len(answers)} of {len(rows)} wrote={written}")
    if args.dry_run:
        print("dry-run sample answers: structure only, NOT a quality baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
