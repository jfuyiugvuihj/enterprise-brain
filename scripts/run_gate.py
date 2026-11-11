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
#: --continue-on-collection-errors（10-07 回滚演练挖出来的形状）：码与测试一旦脱节，
#: 贴错那一侧的文件会在 import 期就炸，pytest 默认把整批中止——门交回一个 rc=2 而不是
#: 逐枚点名的红，等于把「坏在哪一枚」这条信息吃掉。演练实测：退掉 200e47f 的产品码后，
#: 一枚牙正红（14 failed／1 passed），另一枚牙直接 collection error 并把整批打断。
BASE_ARGS = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header",
             "--continue-on-collection-errors"]

#: 2026-10-06 改章：账面坐标族永久退出全量门。名册的唯一真源是
#: ``scripts/selfcheck_ledger.py::FAMILIES``，这里只做减法、禁止再抄一份名单——
#: 抄一次就多一本账，而多一本账正是这把刀要砍掉的东西。
SELFCHECK = ROOT / "scripts" / "selfcheck_ledger.py"


def ledger_family_paths():
    """账面族里此刻真在盘上的文件（不在的一律不传，免得把改名当成出门）。"""
    spec = importlib.util.spec_from_file_location("_selfcheck_ledger", SELFCHECK)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [str(ROOT / name) for name in getattr(module, "FAMILIES", []) if (ROOT / name).is_file()]


class MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory_headroom_gb() -> tuple[float, float]:
    """(free physical, free page-file) in GiB; -1.0 for either when it cannot be asked.

    The second figure is the commit-charge headroom. It is not a nicer spelling of the first:
    a process can hold several GB of committed memory that is not resident, so free physical RAM
    can look healthy while the commit limit is already spent.
    """
    try:
        stat = MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return -1.0, -1.0
        return stat.ullAvailPhys / 1024 ** 3, stat.ullAvailPageFile / 1024 ** 3
    except Exception:
        return -1.0, -1.0


def free_memory_gb() -> float:
    """Available physical memory, or -1.0 when the question cannot be asked."""
    return memory_headroom_gb()[0]


def fit_workers() -> tuple[int, str]:
    """Worker count from the *smaller* of free physical RAM and commit-charge headroom.

    One worker of this suite costs about 2 GB of committed memory (torch + pandas per
    interpreter). Asking only free physical RAM is the wrong single question: on 09-30 08:10 the
    gate picked -n 6 from a healthy-looking physical figure, an outside CUDA trainer then spent
    the commit charge while it was already running, and the workers died of 0xe0000008 with an
    error cascade at 88-89% -- a charge-exhaustion shape that free physical memory cannot see.
    Nothing here may fall back silently, so the reason string goes out on the [run_gate] line.
    """
    free_phys, free_page = memory_headroom_gb()
    if free_phys < 0 or free_page < 0:
        return 4, ("GlobalMemoryStatusEx gave no answer "
                   f"(phys={free_phys:.1f} GB, commit={free_page:.1f} GB), defaulting to -n 4")
    headroom = min(free_phys, free_page)
    limiter = "commit charge" if free_page < free_phys else "free physical"
    readings = f"phys {free_phys:.1f} GB, commit {free_page:.1f} GB"
    if headroom < 4:
        return 1, f"serial: headroom {headroom:.1f} GB is under one worker's 4 GB (limiter: {limiter}; {readings})"
    return max(2, min(8, int(headroom // 2))), (
        f"headroom {headroom:.1f} GB, 2 GB per worker (limiter: {limiter}; {readings})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--workers", type=int, default=0,
                        help="xdist workers (default 0 = pick from free memory; 8 needs ~16 GB free)")
    parser.add_argument("--serial", action="store_true", help="force the serial gate")
    parser.add_argument("--include-ledger", action="store_true",
                        help="把账面坐标族一起跑（默认减掉它们；那一族的红走 scripts/selfcheck_ledger.py）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将要执行的命令与被减掉的名册，不落一次测试")
    # Anything argparse does not own (paths, -k, -m, --lf, ...) goes straight to pytest, in order.
    opts, extra = parser.parse_known_args()
    if opts.workers <= 0:
        opts.workers, why = fit_workers()
    else:
        why = f"explicit -n {opts.workers}"

    cmd = [sys.executable, *BASE_ARGS, *extra]
    dropped = [] if opts.include_ledger else ledger_family_paths()
    for path in dropped:
        cmd += ["--ignore", path]
    parallel = importlib.util.find_spec("xdist") is not None and not opts.serial and opts.workers > 1
    if parallel:
        cmd += ["-n", str(opts.workers), "--dist", "loadfile"]
        mode = f"xdist -n {opts.workers} --dist loadfile"
    else:
        reason = "forced" if opts.serial else ("pytest-xdist is not installed" if opts.workers > 1 else "1 worker")
        mode = f"serial ({reason})"

    print(f"[run_gate] {mode} [{why}]", flush=True)
    print(f"[run_gate] $ {' '.join(cmd)}", flush=True)
    print(f"[run_gate] 账面族出门 {len(dropped)} 枚（2026-10-06 改章：这一族不阻塞并树与发版，"
          "红走 scripts/selfcheck_ledger.py；要连它一起跑用 --include-ledger）", flush=True)
    if opts.dry_run:
        for path in dropped:
            print(f"[run_gate]   减掉 {Path(path).relative_to(ROOT)}", flush=True)
        print("[run_gate] dry-run：没跑任何测试", flush=True)
        return 0
    started = time.time()
    code = subprocess.call(cmd, cwd=ROOT)
    print(f"[run_gate] {mode}: {time.time() - started:.1f} s, exit={code}", flush=True)
    if not parallel and not opts.serial and opts.workers > 1:
        print("[run_gate] hint: uv pip install --python .venv/Scripts/python.exe pytest-xdist", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
