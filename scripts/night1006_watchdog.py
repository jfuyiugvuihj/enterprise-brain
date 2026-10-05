"""night1006_watchdog.py -- keep the night queue alive without a heartbeat thread.

If the queue process is gone and DONE.txt is absent, relaunch it. The queue resumes from its
own ledger (rc=0 steps are skipped), so a reboot at 03:00 does not mean run30 burns the GPU
again. Restarts are capped by a number, not by mood.

Process scan uses Get-CimInstance (wmic is gone from recent builds -- a scan that always
returns empty would have made this watchdog fan out duplicates, which is worse than nothing).
"""
import json
import os
import subprocess
import sys
import time

REPO = r"C:\Users\fengx\PycharmProjects\企业智脑"
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
QUEUE = os.path.join(REPO, "scripts", "night1006_queue.py")
TMP = os.path.join(os.environ["TEMP"], "evalrun")
WDLOG = os.path.join(TMP, "night1006.watchdog.log")
DONE = os.path.join(TMP, "night1006.DONE.txt")
STATE = os.path.join(TMP, "night1006.watchdog.json")
MAX_RELAUNCH = int(os.environ.get("NIGHT1006_MAX_RELAUNCH", "6"))
PS = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
      "Where-Object { $_.CommandLine -like '*night1006_queue.py*' } | "
      "Select-Object -ExpandProperty ProcessId")
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
    return [int(x) for x in res.stdout.split() if x.strip().isdigit()]


def state():
    try:
        return json.loads(open(STATE, encoding="utf-8").read())
    except Exception:
        return {"relaunch": 0}


def save_state(data):
    json.dump(data, open(STATE, "w", encoding="utf-8"))


def launch():
    with open(os.path.join(TMP, "night1006.child.out"), "ab") as out:
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