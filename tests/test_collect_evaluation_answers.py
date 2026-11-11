"""R54: the answer collector must never let a collection gap look like a quality drop.

The checks below are pinned to the reader it feeds, app/quality/runner.py:
  * :7-13   parses a line and indexes it by str(item["id"]);
  * :23-27  answers an unknown id with {"answer": "", "evidence": [], "latency_ms": None}.
That fallback is the failure mode this collector exists to prevent, so the tests assert it
can never fire for a row the collector was asked to collect.

Sample containment is pinned as well: app/quality/eval.py:63-66 scores must_contain and falls
back to row["answer"] in text, so a dry-run file would read as a near-100% baseline while no
reader checks answer_source. Writing one therefore costs both --allow-sample and an explicit
--output, and it can never reach DEFAULT_OUTPUT.
"""
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

# app/quality/runner.py:24-27, copied literally: if a collected row ever equals this, the
# reporter cannot tell "not collected" from "collected and terrible".
RUNNER_FALLBACK = {"answer": "", "evidence": [], "latency_ms": None}
RUNNER_REQUIRED_KEYS = ("id", "answer", "evidence", "latency_ms")
TRACE_KEYS = ("first_token_at", "thinking_chars", "tool_calls")


@pytest.fixture(scope="module")
def collector():
    spec = importlib.util.spec_from_file_location("collect_evaluation_answers", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def no_network(monkeypatch):
    """Offline is a claim, so it gets asserted: any socket attempt is a test failure."""

    def _boom(*args, **kwargs):
        raise AssertionError("the collector must not touch the network without --transport")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)


def _fixture_ids(path):
    return [str(row["id"]) for row in _rows(path)]


def _rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _read_answers(path):
    return _rows(path)


def _write_fixture(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


def test_default_fixture_is_the_105_question_set(collector):
    assert Path(collector.DEFAULT_FIXTURE) == FIXTURE_105
    assert FIXTURE_105.exists()
    assert len(_fixture_ids(FIXTURE_105)) == 105


def test_dry_run_emits_the_four_runner_keys_for_every_fixture_id(collector, tmp_path, no_network):
    output = tmp_path / "answers.jsonl"

    code = collector.main(
        ["--dry-run", "--allow-sample", "--fixture", str(FIXTURE_105), "--output", str(output)]
    )

    assert code == 0
    answers = _read_answers(output)
    ids = _fixture_ids(FIXTURE_105)
    assert [answer["id"] for answer in answers] == ids, "coverage must be complete and in fixture order"
    for answer in answers:
        for key in RUNNER_REQUIRED_KEYS + TRACE_KEYS:
            assert key in answer, f"{answer['id']} is missing {key}"
        assert answer["answer"].strip(), "a blank answer is what the runner fallback invents"
        assert isinstance(answer["evidence"], list) and answer["evidence"]
        assert isinstance(answer["latency_ms"], (int, float))
        # R29/R38: a sample run measured nothing, so nothing may look like a measurement.
        for key in TRACE_KEYS:
            assert answer[key] is None, f"dry run fabricated {key}"
        assert answer["answer_source"] == "dry-run"


def test_dry_run_answers_drive_the_reporter_without_the_empty_answer_fallback(collector, tmp_path, no_network):
    from app.quality import runner

    output = tmp_path / "answers.jsonl"
    report_path = tmp_path / "report.json"
    assert collector.main(
        ["--dry-run", "--allow-sample", "--fixture", str(FIXTURE_105), "--output", str(output)]
    ) == 0

    # Re-read exactly the way app/quality/runner.py:7-13 does, then replay its lookup at
    # :24-27 and prove the fallback branch is unreachable for every fixture id.
    loaded = runner._load_answers(output)
    for row in _rows(FIXTURE_105):
        picked = loaded.get(str(row["id"]), RUNNER_FALLBACK)
        assert picked != RUNNER_FALLBACK, f"{row['id']} would score through the silent fallback"
        assert picked["answer"] and "evidence" in picked and "latency_ms" in picked

    report = runner.run_recorded_evaluation(FIXTURE_105, output, report_path)
    assert report["total"] == 105
    assert report["latency_ms"]["count"] == 105, "every row must carry a real measured latency"
    assert report["evidence_coverage"] == 1.0
    # insight-02 is the fixture's one known gold/must_contain inconsistency, already pinned
    # in tests/test_evaluation_report.py, so a sample run must land on exactly 104/105.
    assert report["answer_correctness"] == round(104 / 105, 4)
    assert Path(report_path).exists()


def _small_fixture(tmp_path, count=3):
    rows = [
        {
            "id": chr(ord("a") + index),
            "tier": "问答",
            "category": "文档问答",
            "question": f"问题 {index}？",
            "answer": f"答案 {index}",
            "must_contain": [f"答案 {index}"],
            "requires_evidence": False,
        }
        for index in range(count)
    ]
    return _write_fixture(tmp_path / "fixture.jsonl", rows)


def _transport_module(tmp_path, name, body):
    path = tmp_path / f"{name}.py"
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def test_coverage_gate_fails_loudly_and_writes_nothing(collector, tmp_path, monkeypatch, capsys):
    fixture = _small_fixture(tmp_path)
    _transport_module(
        tmp_path,
        "r54_flaky_transport",
        """
        def transport(row):
            if row["id"] == "b":
                raise RuntimeError("model unavailable")
            if row["id"] == "c":
                return {"answer": "   "}
            return {"answer": "答案 0", "evidence": [], "latency_ms": 12}
        """,
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "answers.jsonl"

    code = collector.main(
        ["--fixture", str(fixture), "--transport", "r54_flaky_transport:transport", "--output", str(output)]
    )

    stderr = capsys.readouterr().err
    assert code == 1, "a gap must exit non-zero, not lean on the runner fallback"
    assert "missing 2 fixture id(s): b, c" in stderr
    assert "model unavailable" in stderr and "empty answer" in stderr
    assert not output.exists(), "a partial answers file is how silent gaps get created"


def test_measured_transport_fields_are_carried_through(collector, tmp_path, monkeypatch):
    fixture = _small_fixture(tmp_path, count=1)
    _transport_module(
        tmp_path,
        "r54_measured_transport",
        """
        def transport(row):
            return {
                "answer": "答案 0",
                "evidence": [{"source_name": "制度.pdf", "locator": "第1页"}],
                "first_token_at": 1777000000.5,
                "thinking_chars": 612,
                "tool_calls": 2,
                "latency_ms": 4810.5,
                "claims": [{"text": "答案 0", "supported": True}],
                "confidence_label": "high",
            }
        """,
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    output = tmp_path / "answers.jsonl"

    assert collector.main(
        ["--fixture", str(fixture), "--transport", "r54_measured_transport:transport", "--output", str(output)]
    ) == 0

    answer = _read_answers(output)[0]
    assert answer["first_token_at"] == 1777000000.5
    assert answer["thinking_chars"] == 612
    assert answer["tool_calls"] == 2
    assert answer["latency_ms"] == 4810.5, "a transport-measured latency beats the collector's wall clock"
    assert answer["confidence_label"] == "high"
    assert answer["claims"] == [{"text": "答案 0", "supported": True}]
    assert answer["answer_source"] == "r54_measured_transport:transport"


def test_string_transport_results_are_accepted(collector):
    rows = [{"id": "a", "question": "?", "answer": "答案"}]

    answers, failures = collector.collect_answers(rows, lambda row: "答案", answer_source="str")

    assert failures == []
    assert answers[0]["answer"] == "答案"
    assert answers[0]["evidence"] == []
    assert all(answers[0][key] is None for key in TRACE_KEYS), "unmeasured trace fields stay null"
    assert answers[0]["latency_ms"] >= 0


def test_transport_latency_is_measured_not_fabricated(collector):
    rows = [{"id": "a", "question": "?", "answer": "答案"}]
    ticks = iter([0.0, 1.5])

    answers, failures = collector.collect_answers(
        rows,
        lambda row: {"answer": "答案"},
        answer_source="clock",
        clock=lambda: next(ticks),
    )
    assert failures == []

    assert answers[0]["latency_ms"] == 1500.0


def test_untrustworthy_transport_fields_are_rejected(collector):
    rows = [{"id": "a", "question": "?", "answer": "答案"}]

    for payload in (
        {"answer": "答案", "tool_calls": -1},
        {"answer": "答案", "thinking_chars": "12"},
        {"answer": "答案", "latency_ms": -5},
        {"answer": "答案", "evidence": "制度.pdf"},
        None,
    ):
        answers, failures = collector.collect_answers(rows, lambda row, p=payload: p, answer_source="bad")
        assert answers == [] and len(failures) == 1, payload


def test_bare_run_refuses_to_pick_a_transport(collector, tmp_path, capsys):
    with pytest.raises(SystemExit) as raised:
        collector.main(["--output", str(tmp_path / "answers.jsonl")])
    assert raised.value.code == 2
    assert "--dry-run" in capsys.readouterr().err

    with pytest.raises(SystemExit) as raised:
        collector.main(["--dry-run", "--transport", "whatever:fn", "--output", str(tmp_path / "a.jsonl")])
    assert raised.value.code == 2


def test_duplicate_fixture_ids_are_rejected(collector, tmp_path):
    fixture = tmp_path / "fixture.jsonl"
    fixture.write_text(
        json.dumps({"id": "a", "answer": "x"}, ensure_ascii=False) + "\n"
        + json.dumps({"id": "a", "answer": "y"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(collector.CollectionError):
        collector.load_fixture_rows(fixture)


def test_default_output_is_outside_the_repo_and_a_dry_run_cannot_reach_it(collector, capsys):
    default_output = Path(collector.DEFAULT_OUTPUT).resolve()
    assert REPO_ROOT not in default_output.parents, (
        "the default answers path must stay outside the repo: .gitignore is frozen and an"
        " untracked artifact would leave every worktree dirty"
    )
    existed_before = default_output.exists()

    code = collector.main(["--dry-run", "--fixture", str(FIXTURE_105)])

    assert code == 2, "a sample must not be able to land on the baseline path"
    assert "REFUSED" in capsys.readouterr().err
    assert Path(collector.DEFAULT_OUTPUT).exists() == existed_before, "the default path stayed untouched"


def test_sample_answers_need_both_allow_sample_and_an_explicit_output(collector, tmp_path, capsys):
    output = tmp_path / "answers.jsonl"
    fixture_args = ["--dry-run", "--fixture", str(FIXTURE_105)]

    assert collector.main(fixture_args) == 2
    assert collector.main(fixture_args + ["--output", str(output)]) == 2, "no --allow-sample"
    assert collector.main(fixture_args + ["--allow-sample"]) == 2, "no explicit --output"
    stderr = capsys.readouterr().err
    assert stderr.count("REFUSED") == 3
    assert "--allow-sample" in stderr and "answer_source" in stderr
    assert not output.exists(), "a half-enabled sample must not be written at all"

    assert collector.main(fixture_args + ["--allow-sample", "--output", str(output)]) == 0
    answers = _read_answers(output)
    assert len(answers) == 105
    assert {answer["answer_source"] for answer in answers} == {"dry-run"}

    with pytest.raises(SystemExit) as raised:
        collector.main(["--allow-sample", "--transport", "anything:fn", "--output", str(output)])
    assert raised.value.code == 2, "--allow-sample without --dry-run is a misuse, not a pass"
