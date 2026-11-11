"""night1006_watchdog.py -- keep the night queue alive without a heartbeat thread.

If the queue process is gone and DONE.txt is absent, relaunch it. The queue resumes from its
own ledger (rc=0 steps are skipped), so a reboot at 03:00 does not mean run30 burns the GPU
again. Restarts are capped by a number, not by mood.

Process scan uses Get-CimInstance (wmic is gone from recent builds -- a scan that always
returns empty would have made this watchdog fan out duplicates, which is worse than nothing).
"""
import argparse
import json
import os
import subprocess
import sys
import time

REPO = r"C:\Users\fengx\PycharmProjects\企业智脑"
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
TMP = os.path.join(os.environ["TEMP"], "evalrun")
#: The tag names the ledger/DONE/log trio, the queue names the process to supervise. Defaults
#: keep last night's invocation byte-for-byte working; tonight passes them explicitly, so one
#: watchdog serves both queues instead of a second copy that can disagree with the first.
_parser = argparse.ArgumentParser(description="keep a window queue alive without a heartbeat")
_parser.add_argument("--tag", default="night1006")
_parser.add_argument("--queue", default="night1006_queue.py")
_parser.add_argument("--max-relaunch", type=int, default=6)
_ARGS = _parser.parse_args()
QUEUE = os.path.join(REPO, "scripts", _ARGS.queue)
WDLOG = os.path.join(TMP, _ARGS.tag + ".watchdog.log")
DONE = os.path.join(TMP, _ARGS.tag + ".DONE.txt")
STATE = os.path.join(TMP, _ARGS.tag + ".watchdog.json")
MAX_RELAUNCH = int(os.environ.get("EB_WATCHDOG_MAX_RELAUNCH", str(_ARGS.max_relaunch)))
#: 🔴 The scan must not match the watchdog itself: passing --queue puts the queue filename
#: straight into this process's command line, so a naive -like match finds its own pid every
#: round, never accumulates a miss, and the "supervision" is fake-green. Both the pattern and
#: the pid list now exclude the supervisor (hardening the shape the night version got by luck).
PS = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
      "Where-Object { $_.CommandLine -like '*' + '%s' + '*' -and $_.CommandLine -notlike '*watchdog*' } | "
      "Select-Object -ExpandProperty ProcessId") % _ARGS.queue
CHILD_OUT = os.path.join(TMP, _ARGS.tag + ".child.out")
os.makedirs(TMP, exist_ok=True)


def wlog(msg):
    with open(WDLOG, "a", encoding="utf-8") as fh:
        fh.write(time.strftime("%m-%d %H:%M:%S ") + msg + "\n")


def queue_pids():
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", PS],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    except Exception as exc:
        wlog("scan raised " + repr(exc))
        return [-1]
    if res.returncode != 0:
        wlog("scan rc=%s err=%s -- treating as UNKNOWN, no relaunch" % (res.returncode, res.stderr[:200]))
        return [-1]
    pids = [int(x) for x in res.stdout.split() if x.strip().isdigit()]
    return [x for x in pids if x != os.getpid()]


def state():
    try:
        return json.loads(open(STATE, encoding="utf-8").read())
    except Exception:
        return {"relaunch": 0}


def save_state(data):
    json.dump(data, open(STATE, "w", encoding="utf-8"))


def launch():
    with open(CHILD_OUT, "ab") as out:
        proc = subprocess.Popen([PY, QUEUE], cwd=REPO, stdout=out, stderr=subprocess.STDOUT,
                                creationflags=0x00000008 if hasattr(subprocess, "DETACHED_PROCESS") else 0)
    return proc.pid


def main():
    wlog("==== watchdog up pid=%d max_relaunch=%d ====" % (os.getpid(), MAX_RELAUNCH))
    misses = 0
    while True:
        if os.path.exists(DONE):
            wlog("DONE present -- watchdog exits")
            return 0
        pids = queue_pids()
        if pids:
            misses = 0
            if -1 in pids:
                wlog("scan inconclusive -- skipping this round")
        else:
            misses += 1
            if misses >= 2:
                st = state()
                if st["relaunch"] >= MAX_RELAUNCH:
                    wlog("MAX_RELAUNCH=%d reached -- refusing to loop forever" % MAX_RELAUNCH)
                    return 1
                st["relaunch"] += 1
                save_state(st)
                wlog("RELAUNCHING queue attempt=%d (misses=%d)" % (st["relaunch"], misses))
                wlog("child pid=%s" % launch())
                misses = 0
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
