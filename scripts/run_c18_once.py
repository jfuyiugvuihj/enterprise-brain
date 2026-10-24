#!/usr/bin/env python
"""Run the C18 regression once in a detached local process, without auto-retry.

Usage: python scripts/run_c18_once.py plan|start|status|stop|unlock|extend
The full gate is never started by plan/status/stop/unlock/extend.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
RUNS = ROOT / "output" / "c18-local-runs"
STATE = RUNS / "state.json"
LOCK = RUNS / "active.lock"
MAX_MINUTES = 60
EXTENDED_MAX_MINUTES = 120
WORKERS = 2
HEARTBEAT_SECONDS = 5


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def write_state(state: dict) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    temporary = RUNS / f"state.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATE)


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.GetExitCodeProcess.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def plan() -> None:
    print("C18 全仓回归没有可靠的完成时间预估：上次 2 worker 运行 120 分钟仍在 99% 超时。")
    print(f"本脚本默认硬上限 {MAX_MINUTES} 分钟、固定 {WORKERS} 个 worker；运行前应先决定是否需要全仓回归。")
    print("start 只启动一次，不会在失败、超时或 Codex 会话结束后自动重跑。")


def start() -> int:
    plan()
    if not PYTHON.is_file():
        print(f"缺少项目解释器：{PYTHON}", file=sys.stderr)
        return 2
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    try:
        descriptor = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print("已有一次运行或待处理的中断；先用 status 查看。不会自动重跑。", file=sys.stderr)
        return 2
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
        lock.write(run_id)
    folder = RUNS / run_id
    state = {
        "run_id": run_id,
        "status": "launching",
        "started_at": now(),
        "heartbeat_at": now(),
        "head_before": git_head(),
        "head_after": None,
        "head_unchanged": None,
        "workers": WORKERS,
        "max_minutes": MAX_MINUTES,
        "worker_pid": None,
        "gate_pid": None,
        "exit_code": None,
        "ended_at": None,
        "elapsed_seconds": None,
        "log": str(folder / "gate.log"),
    }
    try:
        folder.mkdir()
        write_state(state)
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        worker = subprocess.Popen(
            [str(PYTHON), str(Path(__file__).resolve()), "_worker", run_id],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        state["worker_pid"] = worker.pid
        write_state(state)
    except Exception as exc:
        state.update(status="launch_failed", ended_at=now(), runner_error=type(exc).__name__)
        if folder.is_dir():
            (folder / "runner-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            write_state(state)
        if LOCK.exists() and LOCK.read_text(encoding="utf-8") == run_id:
            LOCK.unlink()
        raise
    print(f"已交给本机后台：run_id={run_id}，PID={worker.pid}")
    print(f"状态：{STATE}\n日志：{state['log']}")
    return 0


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
    else:
        try:
            os.killpg(pid, 15)
        except ProcessLookupError:
            pass


def kill_process_only(pid: int) -> None:
    """Stop the old watchdog without killing its still-running gate child."""
    if os.name != "nt":
        raise RuntimeError("Live takeover is supported only on Windows")
    result = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
    if result.returncode != 0 and alive(pid):
        raise RuntimeError(f"Cannot stop watchdog PID {pid}: {result.returncode}")


def extend() -> int:
    state = read_state()
    if state.get("status") == "extended_running":
        print("本次运行已经延长，无需重复操作。")
        return 0
    if state.get("status") != "running" or not alive(state.get("worker_pid")) or not alive(state.get("gate_pid")):
        print("当前没有可接管的运行中回归。", file=sys.stderr)
        return 2
    if not LOCK.exists() or LOCK.read_text(encoding="utf-8") != state["run_id"]:
        print("运行锁不匹配，拒绝接管。", file=sys.stderr)
        return 2
    folder = Path(state["log"]).parent
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    with (folder / "guardian.log").open("a", encoding="utf-8") as log:
        guardian = subprocess.Popen(
            [str(PYTHON), str(Path(__file__).resolve()), "_guardian", state["run_id"]],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            close_fds=True, creationflags=flags,
        )
    for _ in range(150):
        time.sleep(0.1)
        current = read_state()
        if current.get("run_id") == state["run_id"] and current.get("guardian_pid") == guardian.pid:
            print(f"已接管正在运行的回归；新上限 {EXTENDED_MAX_MINUTES} 分钟，guardian PID={guardian.pid}。")
            return 0
        if guardian.poll() is not None:
            break
    current = read_state()
    if current.get("run_id") == state["run_id"] and current.get("guardian_pid") == guardian.pid:
        print(f"已接管正在运行的回归；新上限 {EXTENDED_MAX_MINUTES} 分钟，guardian PID={guardian.pid}。")
        return 0
    print(f"接管未确认，请检查 {folder / 'guardian.log'}；不会再次启动回归。", file=sys.stderr)
    return 2


def guardian_main(run_id: str) -> int:
    state = read_state()
    if state.get("run_id") != run_id or state.get("status") != "running":
        return 2
    gate_pid = state["gate_pid"]
    worker_pid = state["worker_pid"]
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x101000, False, gate_pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
    if not handle:
        raise RuntimeError(f"Cannot open gate PID {gate_pid}")
    try:
        kill_process_only(worker_pid)
        state.update(status="extended_running", guardian_pid=os.getpid(),
                     max_minutes=EXTENDED_MAX_MINUTES, heartbeat_at=now())
        write_state(state)
        reason = "finished"
        stop_request = Path(state["log"]).parent / "stop.request"
        while kernel.WaitForSingleObject(handle, 1000) == 0x102:  # WAIT_TIMEOUT
            elapsed = (datetime.now().astimezone() - datetime.fromisoformat(state["started_at"])).total_seconds()
            if stop_request.exists():
                reason = "stopped"
                kill_tree(gate_pid)
                break
            if elapsed >= EXTENDED_MAX_MINUTES * 60:
                reason = "timed_out"
                kill_tree(gate_pid)
                break
            state["heartbeat_at"] = now()
            write_state(state)
        kernel.WaitForSingleObject(handle, 10000)
        code = ctypes.c_ulong()
        exit_code = code.value if kernel.GetExitCodeProcess(handle, ctypes.byref(code)) else None
        if exit_code == 259:
            exit_code = None
        final_status = ("passed" if exit_code == 0 else "failed") if reason == "finished" else reason
        ended = now()
        state.update(status=final_status, exit_code=exit_code, ended_at=ended,
                     heartbeat_at=ended, head_after=git_head(),
                     elapsed_seconds=round((datetime.fromisoformat(ended) - datetime.fromisoformat(state["started_at"])).total_seconds(), 1))
        state["head_unchanged"] = state["head_before"] == state["head_after"]
        write_state(state)
        with Path(state["log"]).open("a", encoding="utf-8") as log:
            log.write(f"\nLOCAL_RUN_FINISHED reason={reason} exit={exit_code} elapsed_s={state['elapsed_seconds']}\n")
        if LOCK.exists() and LOCK.read_text(encoding="utf-8") == run_id:
            LOCK.unlink()
        return 0
    finally:
        kernel.CloseHandle(handle)


def worker_main(run_id: str) -> int:
    # Parent writes the detached PID before this process touches the state file.
    for _ in range(50):
        state = read_state()
        if state.get("run_id") == run_id and state.get("worker_pid"):
            break
        time.sleep(0.1)
    else:
        return 2
    log_path = Path(state["log"])
    stop_request = log_path.parent / "stop.request"
    command = [str(PYTHON), "-u", str(ROOT / "scripts" / "run_gate.py"), "-n", str(WORKERS), "--tb=short"]
    begun = time.monotonic()
    reason = "finished"
    gate = None
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            log.write(f"run_id={run_id} started={now()} head={state['head_before']}\n")
            log.write("command=" + " ".join(command) + "\n")
            log.flush()
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            gate = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, creationflags=flags,
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                    start_new_session=os.name != "nt")
            state.update(status="running", gate_pid=gate.pid, heartbeat_at=now())
            write_state(state)
            while gate.poll() is None:
                if stop_request.exists():
                    reason = "stopped"
                    kill_tree(gate.pid)
                    break
                if time.monotonic() - begun >= MAX_MINUTES * 60:
                    reason = "timed_out"
                    kill_tree(gate.pid)
                    break
                state["heartbeat_at"] = now()
                write_state(state)
                time.sleep(HEARTBEAT_SECONDS)
            try:
                exit_code = gate.wait(timeout=10)
            except subprocess.TimeoutExpired:
                kill_tree(gate.pid)
                exit_code = gate.wait(timeout=10)
            elapsed = round(time.monotonic() - begun, 1)
            log.write(f"\nLOCAL_RUN_FINISHED reason={reason} exit={exit_code} elapsed_s={elapsed}\n")
            log.flush()
        final_status = ("passed" if exit_code == 0 else "failed") if reason == "finished" else reason
        state.update(status=final_status, exit_code=exit_code, ended_at=now(),
                     elapsed_seconds=elapsed, heartbeat_at=now(), head_after=git_head())
        state["head_unchanged"] = state["head_before"] == state["head_after"]
        write_state(state)
        return 0
    except BaseException as exc:
        if gate is not None and gate.poll() is None:
            kill_tree(gate.pid)
        (log_path.parent / "runner-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        state.update(status="runner_error", ended_at=now(), heartbeat_at=now(),
                     elapsed_seconds=round(time.monotonic() - begun, 1), runner_error=type(exc).__name__,
                     head_after=git_head())
        state["head_unchanged"] = state["head_before"] == state["head_after"]
        write_state(state)
        return 1
    finally:
        if LOCK.exists() and LOCK.read_text(encoding="utf-8") == run_id:
            LOCK.unlink()


def status() -> int:
    state = read_state()
    if not state:
        print("尚未启动本机 C18 回归；先运行 plan 查看预计时间。")
        return 0
    label = state["status"]
    if label == "extended_running" and not alive(state.get("guardian_pid")):
        label = "orphaned_gate" if alive(state.get("gate_pid")) else "interrupted"
    if label in {"launching", "running"} and not alive(state.get("worker_pid")):
        label = "orphaned_gate" if alive(state.get("gate_pid")) else "interrupted"
    log_path = Path(state["log"])
    elapsed = state["elapsed_seconds"]
    if elapsed is None:
        elapsed = round((datetime.now().astimezone() - datetime.fromisoformat(state["started_at"])).total_seconds(), 1)
    progress = None
    if log_path.is_file():
        with log_path.open("rb") as log:
            log.seek(max(0, log_path.stat().st_size - 8192))
            tail = log.read().decode("utf-8", errors="replace")
        found = re.findall(r"\[\s*(\d+)%\]", tail)
        progress = f"{found[-1]}%" if found else None
    print(json.dumps({
        "run_id": state["run_id"], "status": label, "progress": progress,
        "started_at": state["started_at"], "heartbeat_at": state["heartbeat_at"],
        "ended_at": state["ended_at"], "elapsed_seconds": elapsed,
        "exit_code": state["exit_code"], "head_unchanged": state["head_unchanged"],
        "worker_pid": state["worker_pid"], "gate_pid": state["gate_pid"],
        "guardian_pid": state.get("guardian_pid"), "max_minutes": state["max_minutes"], "log": state["log"],
    }, ensure_ascii=False, indent=2))
    return 0


def stop() -> int:
    state = read_state()
    if state.get("status") not in {"launching", "running", "extended_running"}:
        print("没有运行中的回归。")
        return 0
    if state["status"] == "extended_running":
        request = Path(state["log"]).parent / "stop.request"
        request.write_text(state["run_id"], encoding="utf-8")
        print("已请求延长后的 guardian 停止；用 status 查看最终状态。")
        return 0
    if not alive(state.get("worker_pid")):
        if alive(state.get("gate_pid")):
            kill_tree(state["gate_pid"])
            if alive(state["gate_pid"]):
                print("后台 runner 已退出，但回归进程仍在；停止失败，请检查进程。", file=sys.stderr)
                return 2
            state["status"] = "stopped"
            print("已停止失去 runner 管理的回归进程。")
        else:
            state["status"] = "interrupted"
            print("两个后台进程均已退出，记录为中断。")
        state.update(ended_at=now(), head_after=git_head())
        state["head_unchanged"] = state["head_before"] == state["head_after"]
        write_state(state)
        if LOCK.exists() and LOCK.read_text(encoding="utf-8") == state["run_id"]:
            LOCK.unlink()
        return 0
    request = Path(state["log"]).parent / "stop.request"
    request.write_text(state["run_id"], encoding="utf-8")
    print("已请求本机 runner 停止；用 status 查看最终状态。不会自动重启。")
    return 0


def unlock() -> int:
    if not LOCK.exists():
        print("没有遗留运行锁。")
        return 0
    state = read_state()
    if LOCK.read_text(encoding="utf-8") != state.get("run_id"):
        print("运行锁与状态不一致，可能正在启动；拒绝清锁。", file=sys.stderr)
        return 2
    if alive(state.get("worker_pid")) or alive(state.get("guardian_pid")) or alive(state.get("gate_pid")):
        print("进程仍在运行，拒绝清锁；先用 stop。", file=sys.stderr)
        return 2
    state.update(status="interrupted", ended_at=now())
    write_state(state)
    LOCK.unlink()
    print("已确认两个进程均已退出，清除遗留锁；不会自动重跑。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "start", "status", "stop", "unlock", "extend", "_worker", "_guardian"])
    parser.add_argument("run_id", nargs="?")
    args = parser.parse_args()
    if args.action == "plan":
        plan()
        return 0
    if args.action == "start":
        return start()
    if args.action == "status":
        return status()
    if args.action == "stop":
        return stop()
    if args.action == "unlock":
        return unlock()
    if args.action == "extend":
        return extend()
    if args.action == "_guardian":
        return guardian_main(args.run_id or "")
    return worker_main(args.run_id or "")


if __name__ == "__main__":
    raise SystemExit(main())
