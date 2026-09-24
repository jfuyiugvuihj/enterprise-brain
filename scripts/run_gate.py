#!/usr/bin/env python
"""Run the repository's full regression gate, parallel when xdist is available.

Measured on this box (32 logical cores, 274 test files, 4101 passed / 39 skipped):

    serial                     246.9 s  (second run; first run 255.7 s -- no cold-start tax)
    -n 8  --dist loadfile       83.0 s / 90.0 s over two repeats, same 4101/39, zero failures
    -n 16 --dist loadfile       99.0 s  (worse: oversubscription, so 8 is the knee)

``loadfile`` is not a style choice. Six files drive a nested pytest run and 29 spawn a
subprocess, a container or a git call; ``--dist load`` would split one file's tests across
workers and turn those into false reds. ``worksteal`` was not measured.

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

ROOT = Path(__file__).resolve().parents[1]
BASE_ARGS = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--workers", type=int, default=8,
                        help="xdist workers for --dist loadfile (default 8; 16 measured slower)")
    parser.add_argument("--serial", action="store_true", help="force the serial gate")
    parser.add_argument("args", nargs="*", help="extra pytest arguments (files, -k, -m, ...)")
    opts = parser.parse_args()

    cmd = [sys.executable, *BASE_ARGS, *opts.args]
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
