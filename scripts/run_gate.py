#!/usr/bin/env python
"""Run the repository's full regression gate, parallel when xdist is available.

Measured on this box (32 logical cores, 274 test files, 4101 passed / 39 skipped):

    serial                     246.9 s  (second run; first run 255.7 s -- no cold-start tax)
    -n 8  --dist loadfile       83.0 s / 90.0 s over two repeats, same 4101/39, zero failures
    -n 16 --dist loadfile       99.0 s  (worse: oversubscription, so 8 is the knee)

``loadfile`` is not a style choice. Six files drive a nested pytest run and 29 spawn a
subprocess, a container or a git call; ``--dist load`` would split one file's tests across
workers and turn those into false reds. ``worksteal`` was not measured.

Worker count is memory-bound here, not core-bound, and this box has already died once from
getting it wrong: on 09-24 at 10:18 the Resource-Exhaustion-Detector logged three python.exe
processes at ~2 GB each while a ``-n 16`` gate was running next to five agents' own test runs,
and at 10:20 the host rebooted dirty (Kernel-Power 41) and killed four in-flight agents. Every
worker of this suite imports torch/pandas, so budget ~2 GB per worker and read the free-memory
figure before trusting ``-n``. The default below throttles itself for that reason.

The flags deliberately do NOT live in ``pyproject.toml`` as ``addopts``: the nested pytest
invocations above inherit ``addopts``, so a global ``-n 8`` fans out recursively, and a
three-test file would still pay for eight interpreters. Opt in here, not globally.

pytest-xdist is an undeclared environment package on this box (so is pytest itself -- neither
is in ``pyproject.toml``), so this script falls back to a serial run instead of pretending the
gate got slower. Install it with:

    uv pip install --python .venv/Scripts/python.exe pytest-xdist
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path
import ctypes
import ctypes.wintypes as wt

ROOT = Path(__file__).resolve().parents[1]
BASE_ARGS = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header"]


class MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def free_memory_gb() -> float:
    """Available physical memory, or -1.0 when the question cannot be asked."""
    try:
        stat = MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return -1.0
        return stat.ullAvailPhys / 1024 ** 3
    except Exception:
        return -1.0


def fit_workers() -> int:
    """One worker of this suite costs about 2 GB (torch + pandas per interpreter)."""
    free = free_memory_gb()
    if free < 0:
        return 4
    if free < 4:
        return 1
    return max(2, min(8, int(free // 2)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--workers", type=int, default=0,
                        help="xdist workers (default 0 = pick from free memory; 8 needs ~16 GB free)")
    parser.add_argument("--serial", action="store_true", help="force the serial gate")
    # Anything argparse does not own (paths, -k, -m, --lf, ...) goes straight to pytest, in order.
    opts, extra = parser.parse_known_args()
    if opts.workers <= 0:
        opts.workers = fit_workers()

    cmd = [sys.executable, *BASE_ARGS, *extra]
    parallel = importlib.util.find_spec("xdist") is not None and not opts.serial and opts.workers > 1
    if parallel:
        cmd += ["-n", str(opts.workers), "--dist", "loadfile"]
        mode = f"xdist -n {opts.workers} --dist loadfile"
    else:
        reason = "forced" if opts.serial else ("pytest-xdist is not installed" if opts.workers > 1 else "1 worker")
        mode = f"serial ({reason})"

    print(f"[run_gate] {mode}", flush=True)
    print(f"[run_gate] $ {' '.join(cmd)}", flush=True)
    started = time.time()
    code = subprocess.call(cmd, cwd=ROOT)
    print(f"[run_gate] {mode}: {time.time() - started:.1f} s, exit={code}", flush=True)
    if not parallel and not opts.serial and opts.workers > 1:
        print("[run_gate] hint: uv pip install --python .venv/Scripts/python.exe pytest-xdist", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
