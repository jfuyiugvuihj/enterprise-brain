"""C18 must expose the running case even when the suite cannot finish."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def _load(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(nodeid, when, outcome):
    return SimpleNamespace(nodeid=nodeid, when=when, outcome=outcome, duration=0.25)


def test_running_case_and_teardown_error_are_retained(tmp_path):
    module = _load("c18_progress")
    journal = module.ProgressJournal(tmp_path, "gw0", 2)
    journal.pytest_runtest_logstart("tests/test_example.py::test_slow", None)
    progress = module.read_progress(tmp_path)
    assert progress["completed"] == 0
    assert progress["active"][0]["nodeid"] == "tests/test_example.py::test_slow"
    journal.pytest_runtest_logreport(_report("tests/test_example.py::test_slow", "call", "passed"))
    journal.pytest_runtest_logreport(_report("tests/test_example.py::test_slow", "teardown", "failed"))
    journal.pytest_runtest_logfinish("tests/test_example.py::test_slow", None)
    progress = module.read_progress(tmp_path)
    assert progress["completed"] == 1 and not progress["active"]
    assert progress["outcomes"] == {"error": 1}
    events = [json.loads(line) for line in next(tmp_path.glob("events-*.jsonl")).read_text().splitlines()]
    assert [event["event"] for event in events] == ["start", "report", "report", "finish"]


def test_workers_do_not_count_the_collection_twice(tmp_path):
    module = _load("c18_progress")
    for worker, nodeid, outcome in [("gw0", "a", "passed"), ("gw1", "b", "skipped")]:
        journal = module.ProgressJournal(tmp_path, worker, 2)
        journal.pytest_runtest_logstart(nodeid, None)
        journal.pytest_runtest_logreport(_report(nodeid, "call", outcome))
        journal.pytest_runtest_logfinish(nodeid, None)
    progress = module.read_progress(tmp_path)
    assert progress["collected"] == 2
    assert progress["completed"] == 2
    assert progress["outcomes"] == {"passed": 1, "skipped": 1}


def test_partially_written_worker_snapshot_is_reported(tmp_path):
    module = _load("c18_progress")
    (tmp_path / "progress-gw0.json").write_text('{"completed":', encoding="utf-8")
    progress = module.read_progress(tmp_path)
    assert progress["unreadable"] == ["progress-gw0.json"]


def test_locked_windows_snapshot_does_not_abort_test_execution(tmp_path):
    if os.name != 'nt':
        return
    module = _load('c18_progress')
    journal = module.ProgressJournal(tmp_path, 'main', 1)
    journal.save()
    with (tmp_path / 'progress-main.json').open(encoding='utf-8'):
        journal.pytest_runtest_logstart('tests/example.py::test_read', None)
    journal.pytest_runtest_logreport(_report('tests/example.py::test_read', 'call', 'passed'))
    journal.pytest_runtest_logfinish('tests/example.py::test_read', None)
    assert module.read_progress(tmp_path)['outcomes'] == {'passed': 1}


def test_evidence_fingerprint_includes_uncommitted_and_untracked_code(tmp_path, monkeypatch):
    runner = _load("run_c18_once")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "git_head", lambda: "same-head")
    (tmp_path / "scripts").mkdir()
    source = tmp_path / "scripts" / "new.py"
    source.write_text("value = 1\n", encoding="utf-8")
    diff = b"first diff"

    def git(args):
        if args[0] == "diff":
            return diff
        if args[0] == "ls-files":
            return b"scripts/new.py\0"
        return b""

    monkeypatch.setattr(runner, "git_output", git)
    first = runner.source_fingerprint()
    source.write_text("value = 2\n", encoding="utf-8")
    assert runner.source_fingerprint() != first
    second = runner.source_fingerprint()
    diff = b"second diff"
    assert runner.source_fingerprint() != second


def test_real_pytest_records_failures_and_collection_errors(tmp_path):
    module = _load("c18_progress")
    (tmp_path / "test_cases.py").write_text(
        "def test_ok(): pass\ndef test_bad(): assert False\n", encoding="utf-8")
    (tmp_path / "test_collection.py").write_text("raise RuntimeError('collection problem')\n", encoding="utf-8")
    progress_dir = tmp_path / "journal"
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "c18_progress", "--continue-on-collection-errors", "-q"],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(scripts), "EB_C18_PROGRESS_DIR": str(progress_dir)},
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    progress = module.read_progress(progress_dir)
    assert progress["collected"] == 2 and progress["completed"] == 2
    assert progress["outcomes"] == {"passed": 1, "failed": 1}
    assert progress["collection_errors"] == ["test_collection.py"]


def test_fingerprint_tracks_migrations_and_frontend_entry_in_real_git(tmp_path, monkeypatch):
    runner = _load("run_c18_once")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    paths = ["migrations/001.sql", "frontend/index.html", "frontend/Dockerfile"]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", *paths], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    baseline = runner.source_fingerprint()
    for name in paths:
        path = tmp_path / name
        path.write_text("changed\n", encoding="utf-8")
        assert runner.source_fingerprint() != baseline, name
        path.write_text("original\n", encoding="utf-8")


def test_real_xdist_crash_is_failed_and_not_still_active(tmp_path):
    module = _load("c18_progress")
    (tmp_path / "test_crash.py").write_text(
        "import os\ndef test_crash(): os._exit(19)\n", encoding="utf-8")
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    progress_dir = tmp_path / "journal"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "xdist.plugin", "-p", "c18_progress",
         "-n", "1", "--max-worker-restart=0", "-q"],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(scripts), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
             "EB_C18_PROGRESS_DIR": str(progress_dir)}, timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    progress = module.read_progress(progress_dir)
    assert not progress["active"]
    assert progress["outcomes"] == {"failed": 1}
    assert progress["completed"] == 1
    assert progress["interrupted"][0]["nodeid"] == "test_crash.py::test_crash"
