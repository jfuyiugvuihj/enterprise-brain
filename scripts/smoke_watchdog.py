#!/usr/bin/env python
"""smoke_watchdog.py -- 把「等机器安静下来再重跑冒烟」落成队列，不靠总控记性（10-07 决定）。

三道闸，缺一不跑：
  1 阻塞等训练收工（Wait-Process，不轮询；到 --max-hours 就放弃并留话）；
  2 代次闸：跑之前现取 HEAD，与排队时那枚 sha 不符＝代码又动了，本代次作废，不跑旧账；
  3 账本跳过：每一步在 queue.log 里留 rc，rc=0 的步骤重启不重跑（不重烧 GPU、不重复重建镜像）。

动作只有四件：等 → 重建镜像 → recreate 三枚容器 → 跑九条旅程冒烟。
它不 commit、不改文件、不删任何东西，产物只落在 --out 指名的目录里。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def now():
    return datetime.now().strftime("%m-%d %H:%M:%S")


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def rc_of(self, step: str):
        if not self.path.is_file():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            parts = line.split("|")
            if len(parts) >= 3 and parts[0] == step and parts[1] == "0":
                return 0
        return None

    def note(self, step: str, rc, msg: str = "") -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(step + "|" + str(rc) + "|" + now() + "|" + msg + "\n")
        print("[" + now() + "] " + step + " rc=" + str(rc) + (" " + msg if msg else ""), flush=True)


def training_pids(pattern="train.py"):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                          "Where-Object { $_.CommandLine -match 'train.py' } | ForEach-Object { $_.ProcessId }"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def wait_for_exit(pids, timeout_s):
    if not pids:
        return 0
    for pid in pids:
        rc = subprocess.call(["powershell", "-NoProfile", "-Command",
                              "Wait-Process -Id " + str(pid) + " -Timeout " + str(timeout_s)])
        if rc != 0:
            return rc
    return 0


def wait_healthy(led, cap_s=300):
    """三枚容器都报 healthy 才放行冒烟——第一跑就是栽在 backend 还在 starting 时开跑，9 秒假门红。"""
    names = ["enterprise-brain-backend-1", "enterprise-brain-worker-1", "enterprise-brain-scheduler-1"]
    deadline = time.time() + cap_s
    states = []
    while time.time() < deadline:
        states = []
        for name in names:
            proc = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", name],
                                  capture_output=True, text=True)
            states.append(name + "=" + (proc.stdout.strip() or "unknown"))
        if all(s.endswith("=healthy") for s in states):
            led.note("wait-healthy", 0, " ".join(states))
            return 0
        time.sleep(5)
    led.note("wait-healthy", 1, "等不到齐：" + " ".join(states))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="本次代次的产物目录（%TEMP% 下 evalrun 内）")
    ap.add_argument("--expect-head", required=True, help="排队时的 HEAD sha")
    ap.add_argument("--max-hours", type=float, default=8.0)
    ap.add_argument("--rings", default="1,2,3,4,5,6,7,8,9")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    led = Ledger(out / "queue.log")
    raw = out / "raw.log"
    led.note("queued", 0, "expect HEAD " + args.expect_head + "；训练 pid " + ",".join(str(p) for p in training_pids()))

    budget = int(args.max_hours * 3600)
    for attempt in range(1, 4):
        pids = training_pids()
        if not pids:
            led.note("gate1-quiet", 0, "第 " + str(attempt) + " 轮：问不到训练进程")
            break
        led.note("gate1-wait", 0, "阻塞等 pid " + ",".join(str(p) for p in pids))
        rc = wait_for_exit(pids, budget)
        if rc != 0:
            led.note("gate1-wait", rc, "等到超时，放弃本代次")
            return 2
        time.sleep(60)
    else:
        led.note("gate1-quiet", 1, "三轮问下来还有训练进程，放弃")
        return 2

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                          capture_output=True, text=True).stdout.strip()
    if head[:len(args.expect_head)] != args.expect_head:
        led.note("gate2-generation", 1, "HEAD 已变成 " + head[:10] + "，与排队时不符，本代次作废")
        return 3
    led.note("gate2-generation", 0, "HEAD 仍是 " + head[:10])

    compose = [str(REPO / "docker-compose.yml")]
    steps = [
        ("build-image", ["docker", "compose", "-f", compose[0], "--env-file", str(REPO / "deploy" / ".env.server"),
                         "build", "migrate"], 0),
        ("recreate", ["docker", "compose", "-f", compose[0], "--env-file", str(REPO / "deploy" / ".env.server"),
                      "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "300",
                      "backend", "worker", "scheduler"], 0),
        ("smoke-v1", [sys.executable, str(REPO / "scripts" / "smoke_v1.py"),
                      "--env-file", str(REPO / "deploy" / ".env.server"),
                      "--rings", args.rings, "--out", str(out / "smoke")], 0),
    ]
    last_rc = None
    if wait_healthy(led) != 0:
        return 4

    for step, cmd, _ in steps:
        if led.rc_of(step) == 0:
            led.note(step, 0, "账本跳过（已 rc=0）")
            if step == "smoke-v1":
                last_rc = 0
            continue
        led.note("begin:" + step, 0, " ".join(cmd)[:200])
        with raw.open("a", encoding="utf-8", newline="\n") as fh:
            proc = subprocess.Popen(cmd, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT)
            rc = proc.wait()
        led.note(step, rc)
        if step == "smoke-v1":
            last_rc = rc
        if rc != 0 and step != "smoke-v1":
            led.note("abort", rc, step + " 失败，不再往下跑")
            return 1
    print("[" + now() + "] 全部步骤跑完，产物在 " + str(out) + "；冒烟 rc=" + str(last_rc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
