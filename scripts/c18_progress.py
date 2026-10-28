"""Explicit pytest plugin: one durable journal per C18 worker, no test execution."""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ProgressJournal:
    def __init__(self, folder: Path, worker: str, collected: int = 0):
        self.folder, self.worker = folder, worker
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state = {"worker": worker, "pid": os.getpid(), "collected": collected,
                      "completed": 0, "outcomes": {}, "active": None,
                      "collection_errors": [], "last_finished_at": None}
        self.outcome = None
        self.snapshot_name = f"progress-{worker}.json"

    def save(self):
        target = self.folder / self.snapshot_name
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        for attempt in range(4):
            try:
                os.replace(temporary, target)
                return
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.01 * (attempt + 1))

    def event(self, event, **data):
        self.state["updated_at"] = timestamp()
        try:
            with (self.folder / f"events-{self.worker}.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"at": self.state["updated_at"], "event": event,
                                         "worker": self.worker, **data}, ensure_ascii=False) + "\n")
            self.save()
        except OSError as exc:
            # Observing a test must never turn its outcome into pytest INTERNALERROR.
            sys.stderr.write(f'C18_PROGRESS_WRITE_FAILED worker={self.worker} error={type(exc).__name__}\n')

    def pytest_collection_finish(self, session):
        self.state["collected"] = len(session.items)
        self.event("collected", count=len(session.items))

    def pytest_collectreport(self, report):
        if report.failed:
            self.state["collection_errors"].append(report.nodeid)
            self.event("collection_error", nodeid=report.nodeid)

    def pytest_runtest_logstart(self, nodeid, location):
        self.outcome = None
        self.state["active"] = {"nodeid": nodeid, "started_at": timestamp()}
        self.event("start", nodeid=nodeid)

    def pytest_runtest_logreport(self, report):
        outcome = "error" if report.outcome == "failed" and report.when != "call" else report.outcome
        rank = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}
        if self.outcome is None or rank.get(outcome, 3) > rank.get(self.outcome, 3):
            self.outcome = outcome
        self.event("report", nodeid=report.nodeid, phase=report.when,
                   outcome=outcome, duration=report.duration)

    def pytest_runtest_logfinish(self, nodeid, location):
        outcome = self.outcome or "unknown"
        self.state["completed"] += 1
        counts = self.state["outcomes"]
        counts[outcome] = counts.get(outcome, 0) + 1
        self.state["active"] = None
        self.state["last_finished_at"] = timestamp()
        self.event("finish", nodeid=nodeid, outcome=outcome)

    def pytest_sessionfinish(self, session, exitstatus):
        self.state["exit_code"] = int(exitstatus)
        self.event("session_finish", exit_code=int(exitstatus))


class ControllerJournal(ProgressJournal):
    """Only worker exits and crashes are counted here, never normal worker reports."""
    def __init__(self, folder):
        super().__init__(folder, "controller")
        self.snapshot_name = "controller.json"
        self.state.update(exited_workers={}, crashes={})

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error):
        worker = node.gateway.id
        self.state["exited_workers"][worker] = str(error) if error is not None else None
        self.event("worker_exit", exited_worker=worker, error=self.state["exited_workers"][worker])

    @pytest.hookimpl(optionalhook=True)
    def pytest_handlecrashitem(self, crashitem, report, sched):
        worker = report.node.gateway.id
        self.state["crashes"][worker] = crashitem
        self.event("worker_crash", exited_worker=worker, nodeid=crashitem)


def pytest_configure(config):
    folder = os.environ.get("EB_C18_PROGRESS_DIR")
    if not folder:
        return
    # The xdist controller receives worker reports too; counting them duplicates results.
    if not hasattr(config, "workerinput") and config.getoption("numprocesses", default=0):
        config.pluginmanager.register(ControllerJournal(Path(folder)), "c18-controller-journal")
        return
    worker = getattr(config, "workerinput", {}).get("workerid", "main")
    config.pluginmanager.register(ProgressJournal(Path(folder), worker), "c18-case-journal")


def read_progress(folder: Path) -> dict:
    states, unreadable = [], []
    controller = {}
    if (folder / "controller.json").exists():
        try:
            controller = json.loads((folder / "controller.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append("controller.json")
    for path in sorted(folder.glob("progress-*.json")):
        try:
            states.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            unreadable.append(path.name)
    counts = Counter()
    active, interrupted = [], []
    for state in states:
        counts.update(state.get("outcomes", {}))
        if state.get("active"):
            item = dict(state["active"], worker=state["worker"])
            item["elapsed_seconds"] = round((datetime.now().astimezone() -
                datetime.fromisoformat(item["started_at"])).total_seconds(), 1)
            if state["worker"] in controller.get("exited_workers", {}) or state.get('exit_code') is not None:
                item["error"] = controller.get("exited_workers", {}).get(state["worker"], 'session_finished')
                interrupted.append(item)
            else:
                active.append(item)
    crashed = len(controller.get("crashes", {}))
    if crashed:
        counts["failed"] += crashed
    totals = sorted({state.get("collected", 0) for state in states})
    last_finished = max((state["last_finished_at"] for state in states
                         if state.get("last_finished_at")), default=None)
    return {"collected": totals[0] if len(totals) == 1 else None,
            "collection_consistent": len(totals) <= 1,
            "completed": sum(state.get("completed", 0) for state in states) + crashed,
            "outcomes": dict(counts), "active": active, "interrupted": interrupted,
            "last_finished_at": last_finished,
            "collection_errors": sorted({item for state in states
                                          for item in state.get("collection_errors", [])}),
            "workers_recorded": len(states), "unreadable": unreadable}
