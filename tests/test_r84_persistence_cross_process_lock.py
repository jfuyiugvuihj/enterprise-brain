"""R84: ``JsonPersistenceAdapter.upsert()`` erased other processes' records.

``upsert`` is a read-modify-write of one JSON document: ``_read()`` the whole file, mutate
one record in memory, ``_write()`` the whole document back through ``os.replace``. The only
guard was ``self._lock``, a ``threading.RLock`` (app/storage/persistence.py:47), which
serializes threads inside one process and nothing at all between processes. A second API
process that read the file before the first one replaced it wrote a stale view back and
silently dropped the record the first one had just landed.

Reachability was measured, not assumed: ``PERSISTENCE_BACKEND`` defaults to ``json``
(app/storage/persistence.py:417) and the shipped launcher starts several API processes by
default (``deploy/start_workers.ps1:3`` -> ``-Workers 3``).

RED-WHY-PROCESSES: an ``RLock`` already stops two *threads* from interleaving, so a
threaded case is green both before and after the fix and proves nothing about the shipped
multi-process topology. Every behavioural case below runs the real adapter inside
``sys.executable`` children.

RED-WHY-DETERMINISTIC: the lost-update window is milliseconds wide, so the reproduction
does not spin a hundred attempts and hope. Process A wraps its own ``_read`` and refuses to
leave the window until the *test* releases it. The test spawns B only after A has read, and
releases A once either (a) B has completed a whole upsert inside that window -- possible
only when nothing keeps B out of the file, i.e. the bug -- or (b) B entered ``upsert`` and
then made no progress for ``WINDOW_GRACE_SECONDS``, which means something is keeping it
out. Under working exclusion only (b) can happen; without it (a) is certain, because B
needs microseconds to get from entering ``upsert`` to rewriting the file.

Criterion map (docs/handoff/2026-09-15-backend-followup-requests.md 31.2):
  1 red-then-green across processes -> test_two_processes_sharing_one_window_both_keep_their_record
  2 where the lock lives, stdlib only -> test_lock_file_lives_beside_the_persistence_file,
     test_module_locks_with_stdlib_only_on_both_platform_legs,
     test_read_only_paths_do_not_take_the_cross_process_lock
  3 bounded wait then the existing error -> test_busy_lock_times_out_as_the_existing_persistence_error
  4 no zombie lock after a kill -> test_killed_lock_holder_does_not_leave_a_zombie_lock
  5 honest residual limit in the docstring -> test_module_docstring_declares_the_shared_filesystem_limit
  6 on-disk format untouched -> test_upsert_still_writes_the_same_bytes_to_disk
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from app.storage.persistence import JsonPersistenceAdapter, PersistenceWriteError

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "storage" / "persistence.py"

#: How long the test waits, once B has entered ``upsert``, for B to finish a whole
#: read-modify-write. Measured enter -> write on this machine is well under 10 ms, so this
#: is a wide margin and not a coin flip.
WINDOW_GRACE_SECONDS = 1.5
#: Budget for waiting on a child marker (interpreter start-up included).
STARTUP_BUDGET_SECONDS = 40.0
#: How long process A holds its window before giving up on the test.
RELEASE_BUDGET_SECONDS = 90.0

SEED_COLLECTION = "kg_edges"
SEED_RECORD_ID = "seed-edge"

CHILD_SCRIPT = r'''
import json
import os
import sys
import time

(
    role,
    journal,
    markers,
    repo_root,
    collection,
    record_id,
    lock_timeout,
    hold_seconds,
    release_budget,
) = sys.argv[1:10]

sys.path.insert(0, repo_root)

from app.storage.persistence import JsonPersistenceAdapter

notes = {}


def publish(name, **payload):
    # Harness telemetry only; the judged marker names are unchanged. The scratch name has
    # to be unique per process and the rename retried: six children publish "W.enter" before
    # any lock exists, and on Windows replacing onto a file another child still has open
    # fails outright, which would be a false red about the harness, not about the adapter.
    temporary = os.path.join(markers, name + "." + str(os.getpid()) + ".tmp")
    final = os.path.join(markers, name)
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"name": name, "at": time.time(), **payload}, handle)
    deadline = time.time() + 10.0
    while True:
        try:
            os.replace(temporary, final)
            return
        except OSError:
            if time.time() >= deadline:
                raise
            time.sleep(0.02)


def observe(name, budget):
    path = os.path.join(markers, name)
    deadline = time.time() + budget
    while time.time() < deadline:
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            time.sleep(0.01)
    return None


def snapshot_of(payload):
    return {
        name: sorted(bucket)
        for name, bucket in payload.items()
        if isinstance(bucket, dict)
    }


def build_adapter():
    try:
        return JsonPersistenceAdapter(journal, lock_timeout_seconds=float(lock_timeout))
    except TypeError:
        # The pre-fix adapter has no cross-process lock and therefore no knob either, so
        # the red below bites the lost update instead of the test's own API.
        return JsonPersistenceAdapter(journal)


def hold_the_lock():
    """Sit inside the file lock for ``hold_seconds`` so a writer has to queue or fail.

    ``locked`` reports honestly whether a lock was taken at all: before the fix there is
    nothing to take, and the cases that need a real holder go red on that fact rather than
    passing vacuously.
    """
    path = getattr(adapter, "lock_path", None)
    lock = None
    if path is not None:
        try:
            from app.storage.persistence import _AdvisoryFileLock
        except ImportError:
            _AdvisoryFileLock = None
        if _AdvisoryFileLock is not None:
            lock = _AdvisoryFileLock(path)
            lock.acquire()
    publish("held", locked=lock is not None, lock_path=str(path) if path else None)
    try:
        time.sleep(float(hold_seconds))
    finally:
        if lock is not None:
            lock.release()
            publish("holder_released")


adapter = build_adapter()
_real_read = JsonPersistenceAdapter._read
_real_write = JsonPersistenceAdapter._write


def watched_read():
    payload = _real_read(adapter)
    notes["snapshot"] = snapshot_of(payload)
    publish(role + ".read_done", snapshot=notes["snapshot"])
    if role == "A":
        notes["released"] = observe("release", float(release_budget)) is not None
    return payload


def watched_write(payload):
    publish(role + ".write_start", snapshot=snapshot_of(payload))
    _real_write(adapter, payload)
    publish(role + ".write_done", snapshot=snapshot_of(payload))


adapter._read = watched_read
adapter._write = watched_write

report = {"role": role, "collection": collection, "record_id": record_id, "ok": False}
try:
    if role in {"A", "B", "W"}:
        publish(role + ".enter")
        adapter.upsert(collection, record_id, {"owner_id": "r84", "written_by": role})
        report["ok"] = True
    elif role in {"H", "K"}:
        hold_the_lock()
        report["ok"] = True
    else:
        raise AssertionError("unknown role " + role)
except Exception as exc:
    report["error"] = type(exc).__name__ + ": " + str(exc)
report.update(notes)
print(json.dumps(report))
'''


def _marker_dir(tmp_path: Path) -> Path:
    markers = tmp_path / "markers"
    markers.mkdir(parents=True, exist_ok=True)
    (markers / "r84_child.py").write_text(CHILD_SCRIPT, encoding="utf-8")
    return markers


def _launch(
    markers: Path,
    journal: Path,
    role: str,
    *,
    collection: str = "datasets",
    record_id: str | None = None,
    lock_timeout: float = 30.0,
    hold_seconds: float = 0.0,
) -> subprocess.Popen:
    argv = [
        sys.executable,
        str(markers / "r84_child.py"),
        role,
        str(journal),
        str(markers),
        str(ROOT),
        collection,
        record_id or f"{role.lower()}-record",
        str(lock_timeout),
        str(hold_seconds),
        str(RELEASE_BUDGET_SECONDS),
    ]
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PERSISTENCE_BACKEND": "json",
        "PERSISTENCE_FALLBACK_PATH": str(journal),
    }
    return subprocess.Popen(
        argv,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _read_marker(markers: Path, name: str, budget: float) -> dict | None:
    path = markers / name
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.01)
    return None


def _wait_marker(markers: Path, name: str, budget: float = STARTUP_BUDGET_SECONDS) -> dict:
    marker = _read_marker(markers, name, budget)
    assert marker is not None, f"child marker {name!r} never appeared within {budget}s"
    return marker


def _release_window(markers: Path) -> dict:
    marker = {"name": "release", "at": time.time()}
    temporary = markers / "release.tmp"
    temporary.write_text(json.dumps(marker), encoding="utf-8")
    os.replace(temporary, markers / "release")
    return marker


def _harvest(process: subprocess.Popen, role: str, timeout: float = 120.0) -> dict:
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError(f"child {role} did not finish within {timeout}s") from None
    assert process.returncode == 0, f"child {role} exited {process.returncode}: {stderr}"
    lines = [line for line in stdout.strip().splitlines() if line.startswith("{")]
    assert lines, f"child {role} printed no report: {stdout!r} / {stderr!r}"
    report = json.loads(lines[-1])
    assert report["ok"], f"child {role} failed: {report.get('error')}"
    return report


def _kill_quietly(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    process.communicate()


def _document(journal: Path) -> dict:
    return json.loads(journal.read_text(encoding="utf-8"))


def _seed(journal: Path) -> None:
    """Put an unrelated collection on disk first: a stale rewrite drops that too."""
    JsonPersistenceAdapter(journal).upsert(
        SEED_COLLECTION, SEED_RECORD_ID, {"edge": "a->b", "owner_id": "r84"}
    )


def _collections_on_disk(journal: Path) -> dict:
    return {name: sorted(bucket) for name, bucket in _document(journal).items()}


def test_two_processes_sharing_one_window_both_keep_their_record(tmp_path):
    """Judgment 1: A lands first, B lands second, and neither record may vanish.

    Before the fix B's document-wide rewrite was built from a view that predated A, so A's
    record disappeared even though every individual write was atomic.
    """
    journal = tmp_path / "persistence.json"
    markers = _marker_dir(tmp_path)
    _seed(journal)

    first = _launch(markers, journal, "A", collection="artifacts", record_id="rec-A")
    second = None
    try:
        a_read = _wait_marker(markers, "A.read_done")
        second = _launch(markers, journal, "B", collection="datasets", record_id="rec-B")
        b_enter = _wait_marker(markers, "B.enter")
        b_wrote_in_window = _read_marker(markers, "B.write_done", WINDOW_GRACE_SECONDS) is not None
        release = _release_window(markers)
        a_report = _harvest(first, "A")
        b_report = _harvest(second, "B")

        # Everything from here down is fix-independent: it proves the injection was live,
        # so the outcome cannot be explained by lucky scheduling.
        a_write = _wait_marker(markers, "A.write_start")
        assert a_read["at"] < b_enter["at"], "B never entered upsert while A was mid-window"
        assert b_enter["at"] < release["at"] < a_write["at"], (
            "A wrote without waiting for the injected window, so no interleaving was forced"
        )
        assert a_report["released"] is True, "A gave up waiting for the release signal"
        assert a_read["snapshot"] == {SEED_COLLECTION: [SEED_RECORD_ID]}, a_read["snapshot"]

        on_disk = _collections_on_disk(journal)
        assert on_disk.get("artifacts") == ["rec-A"], (
            "A's record vanished from the file although its own upsert reported success: "
            + repr(on_disk)
        )
        assert on_disk.get("datasets") == ["rec-B"], on_disk
        assert on_disk.get(SEED_COLLECTION) == [SEED_RECORD_ID], (
            "an untouched collection went missing too, which is the blast radius of one "
            "stale whole-document rewrite: " + repr(on_disk)
        )

        # Mechanism: under working exclusion B cannot finish inside the window, and the
        # view it eventually reads already carries A's record.
        assert not b_wrote_in_window, (
            "B completed a whole upsert while A was still inside its read-modify-write "
            "window, i.e. nothing kept B out of the file: the lost update itself"
        )
        assert "rec-A" in b_report["snapshot"].get("artifacts", []), (
            "B read a view of the file that did not contain A's record, so B's rewrite "
            "was stale by construction: " + repr(b_report["snapshot"])
        )
    finally:
        _kill_quietly(first)
        if second is not None:
            _kill_quietly(second)


def test_a_burst_of_processes_each_keeps_its_record(tmp_path):
    """Judgment 1, supplement: six real processes, no injection, nothing lost after the fix.

    Honest about its own strength: without the injected window the pre-fix loss is only
    likely, not certain, so this case is not the reproduction. After the fix it must hold
    every run, because the read-modify-write is serialized.
    """
    journal = tmp_path / "persistence.json"
    markers = _marker_dir(tmp_path)
    processes = [
        _launch(
            markers,
            journal,
            "W",
            collection="tool_calls",
            record_id=f"burst-{index}",
            lock_timeout=60.0,
        )
        for index in range(6)
    ]
    try:
        for index, process in enumerate(processes):
            _harvest(process, f"W{index}")
    finally:
        for process in processes:
            _kill_quietly(process)

    assert _collections_on_disk(journal) == {"tool_calls": [f"burst-{index}" for index in range(6)]}


def test_busy_lock_times_out_as_the_existing_persistence_error(tmp_path):
    """Judgment 3: a writer that cannot get the lock fails loudly, in bounded time."""
    journal = tmp_path / "persistence.json"
    markers = _marker_dir(tmp_path)
    _seed(journal)
    holder = _launch(markers, journal, "H", hold_seconds=5.0)
    try:
        held = _wait_marker(markers, "held")
        assert held["locked"] is True, (
            "the holder process could not take a cross-process lock, so nothing was "
            "contending: " + repr(held)
        )
        adapter = JsonPersistenceAdapter(journal, lock_timeout_seconds=0.25)
        started = time.monotonic()
        with pytest.raises(PersistenceWriteError) as raised:
            adapter.upsert("datasets", "rec-timeout", {"owner_id": "r84"})
        waited = time.monotonic() - started

        assert type(raised.value) is PersistenceWriteError, type(raised.value)
        assert isinstance(raised.value, RuntimeError), "keep the existing error vocabulary"
        assert "another process" in str(raised.value).lower(), str(raised.value)
        assert 0.2 <= waited < 5.0, f"the wait must be bounded, not silent: {waited:.3f}s"
        assert "datasets" not in _collections_on_disk(journal), "a rejected write must not land"
    finally:
        _kill_quietly(holder)


def test_killed_lock_holder_does_not_leave_a_zombie_lock(tmp_path):
    """Judgment 4: killing one side must not wedge the file for everybody else.

    This is why the exclusion is an OS advisory lock and not an ``O_EXCL`` sentinel file:
    no process has to reap a lock its owner never lived to release.
    """
    journal = tmp_path / "persistence.json"
    markers = _marker_dir(tmp_path)
    _seed(journal)
    holder = _launch(markers, journal, "K", hold_seconds=120.0)
    successor = None
    try:
        held = _wait_marker(markers, "held")
        assert held["locked"] is True, repr(held)
        assert held["lock_path"], "the holder did not report which file it locked"
        holder.kill()
        holder.communicate()
        assert holder.poll() is not None, "the holder process is somehow still alive"

        successor = _launch(
            markers, journal, "W", collection="artifacts", record_id="rec-after-kill"
        )
        _harvest(successor, "W-after-kill", timeout=30.0)
        assert _collections_on_disk(journal) == {
            "artifacts": ["rec-after-kill"],
            SEED_COLLECTION: [SEED_RECORD_ID],
        }
    finally:
        _kill_quietly(holder)
        if successor is not None:
            _kill_quietly(successor)


def test_lock_file_lives_beside_the_persistence_file(tmp_path):
    """Judgment 2: the sidecar lock sits in the directory of the file it protects."""
    journal = tmp_path / "nested" / "records.json"
    adapter = JsonPersistenceAdapter(journal)
    adapter.upsert("datasets", "rec-1", {"owner_id": "r84"})

    names = sorted(child.name for child in journal.parent.iterdir())
    assert adapter.lock_path.parent == adapter.path.parent
    assert adapter.lock_path.name == ".records.json.lock", adapter.lock_path
    assert adapter.lock_path.is_file(), "upsert must have gone through this lock file"
    assert names == [".records.json.lock", "records.json"], names


def test_read_only_paths_do_not_take_the_cross_process_lock(tmp_path):
    """Judgment 2, scope: only ``upsert`` changes the disk, so only it is serialized."""
    journal = tmp_path / "records.json"
    adapter = JsonPersistenceAdapter(journal)
    adapter.upsert("datasets", "rec-1", {"owner_id": "r84"})
    adapter.lock_path.unlink()

    assert adapter.get("datasets", "rec-1") == {"owner_id": "r84"}
    assert [row["owner_id"] for row in adapter.list("datasets")] == ["r84"]
    assert not adapter.lock_path.exists(), "a read must not create a lock sidecar"


def test_upsert_still_writes_the_same_bytes_to_disk(tmp_path):
    """Judgment 6: the on-disk format is untouched - compact, sorted, no new whitespace."""
    journal = tmp_path / "records.json"
    adapter = JsonPersistenceAdapter(journal)
    adapter.upsert("datasets", "b-record", {"owner_id": "u", "zeta": 1})
    adapter.upsert("datasets", "a-record", {"owner_id": "u", "alpha": 2})

    expected = json.dumps(
        {
            "datasets": {
                "a-record": {"alpha": 2, "owner_id": "u"},
                "b-record": {"owner_id": "u", "zeta": 1},
            }
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert journal.read_text(encoding="utf-8") == expected


def test_module_locks_with_stdlib_only_on_both_platform_legs():
    """Judgment 2: no third-party locking library, and both platform legs really written."""
    source = MODULE.read_text(encoding="utf-8-sig")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    stdlib = {
        "__future__",
        "collections",
        "contextlib",
        "dataclasses",
        "datetime",
        "json",
        "os",
        "pathlib",
        "tempfile",
        "threading",
        "time",
        "typing",
    }
    extra = sorted(imported - stdlib)
    assert set(extra) <= {"fcntl", "msvcrt", "psycopg"}, extra
    assert "fcntl" in extra and "msvcrt" in extra, "both legs must be written, not one"
    assert "fcntl.flock" in source and "fcntl.LOCK_EX" in source, "POSIX leg missing"
    assert "msvcrt.locking" in source and "msvcrt.LK_NBLCK" in source, "Windows leg missing"


def test_module_docstring_declares_the_shared_filesystem_limit():
    """Judgment 5: say the residual risk out loud, and do not oversell the lock."""
    from app.storage import persistence as module

    combined = " ".join(
        part for part in (module.__doc__, JsonPersistenceAdapter.__doc__, module._AdvisoryFileLock.__doc__) if part
    )
    for needle in ("NFS", "SMB"):
        assert needle in combined, f"{needle} is not declared anywhere in the docstrings"
    assert "unreliable" in combined.lower(), "the limitation must be stated, not hinted at"
    for overclaim in ("absolutely safe", "always safe", "fully safe", "guaranteed safe"):
        assert overclaim not in combined.lower(), overclaim
    assert "绝对安全" not in combined


def test_a_second_writer_in_the_same_process_waits_for_the_lock_too(tmp_path):
    """The gate is per file, not per instance: two adapters, one lock, no silent write."""
    from app.storage.persistence import _AdvisoryFileLock

    journal = tmp_path / "records.json"
    holder = _AdvisoryFileLock(JsonPersistenceAdapter(journal).lock_path)
    holder.acquire()
    try:
        with pytest.raises(PersistenceWriteError):
            JsonPersistenceAdapter(journal, lock_timeout_seconds=0.2).upsert(
                "datasets", "rec-2", {"owner_id": "r84"}
            )
    finally:
        holder.release()

    JsonPersistenceAdapter(journal, lock_timeout_seconds=3.0).upsert(
        "datasets", "rec-2", {"owner_id": "r84"}
    )
    assert _collections_on_disk(journal) == {"datasets": ["rec-2"]}
