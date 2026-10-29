#!/usr/bin/env python3
"""Persistent 72-hour observation state machine, independent of an Agent session."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WINDOW_SECONDS = 72 * 60 * 60


def now() -> float:
    return time.time()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def check_health(url: str, timeout: float) -> dict:
    try:
        proc = subprocess.run(["curl", "-fsS", "--max-time", str(timeout), url],
                              capture_output=True, text=True, timeout=timeout + 1, check=False)
        return {"ok": proc.returncode == 0, "summary": f"http_exit={proc.returncode}"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "summary": type(exc).__name__}


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, int(pid)
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def start(state_file: Path, args, *, spawn: bool = True) -> dict:
    if state_file.exists():
        raise ValueError("state file already exists; use status or resume")
    started = now()
    state = {
        "schema": "enterprise-brain-longrun/v1",
        "status": "running",
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "deadline_epoch": started + WINDOW_SECONDS,
        "project": args.project,
        "health_url": args.health_url,
        "interval_seconds": args.interval,
        "version": args.version,
        "hardware": args.hardware,
        "load": args.load,
        "checks": [],
        "worker_pid": None,
    }
    save(state_file, state)
    if spawn:
        log_path = state_file.with_suffix(".log")
        command = [sys.executable, str(Path(__file__).resolve()),
                   "--state-file", str(state_file), "resume",
                   "--interval", str(args.interval), "--timeout", "10"]
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0)
        with log_path.open("ab") as log:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log,
                                       start_new_session=True, creationflags=flags)
        state["worker_pid"] = process.pid
        save(state_file, state)
    return state


def tick(state_file: Path, timeout: float) -> dict:
    state = load(state_file)
    if state["status"] != "running":
        return state
    state["worker_pid"] = os.getpid()
    checked = now()
    health = check_health(state["health_url"], timeout)
    state["checks"].append({"epoch": checked, "utc": datetime.fromtimestamp(
        checked, timezone.utc).isoformat(), **health})
    if checked >= float(state["deadline_epoch"]):
        state["status"] = "passed" if all(row["ok"] for row in state["checks"]) else "failed"
        state["ended_at"] = datetime.fromtimestamp(checked, timezone.utc).isoformat()
    save(state_file, state)
    return state


def resume(state_file: Path) -> dict:
    state = load(state_file)
    if state.get("status") == "interrupted":
        restarted = now()
        state.setdefault("interruptions", []).append({
            "detected_at": datetime.fromtimestamp(restarted, timezone.utc).isoformat(),
            "previous_deadline_epoch": state["deadline_epoch"],
        })
        state.update(status="running", deadline_epoch=restarted + WINDOW_SECONDS,
                     resumed_at=datetime.fromtimestamp(restarted, timezone.utc).isoformat())
        save(state_file, state)
    if state.get("status") not in {"running"}:
        raise ValueError(f"state cannot resume from {state.get('status')}")
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    start_p = sub.add_parser("start")
    start_p.add_argument("--project", required=True)
    start_p.add_argument("--health-url", required=True)
    start_p.add_argument("--interval", type=int, default=300)
    start_p.add_argument("--version", required=True)
    start_p.add_argument("--hardware", required=True)
    start_p.add_argument("--load", required=True)
    sub.add_parser("status")
    resume_p = sub.add_parser("resume")
    resume_p.add_argument("--interval", type=int, default=300)
    resume_p.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    path = Path(args.state_file).resolve()
    if args.command == "start":
        report = start(path, args)
    elif args.command == "status":
        report = load(path)
        if report.get("status") == "running" and not _pid_alive(report.get("worker_pid")):
            report["status"] = "interrupted"
            report["next_action"] = "Run resume with the same state file; the interrupted interval is not counted."
            save(path, report)
    else:
        report = resume(path)
        while True:
            report = tick(path, args.timeout)
            if report["status"] != "running":
                break
            time.sleep(max(1, args.interval))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"running", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
