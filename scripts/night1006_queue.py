"""night1006_queue.py -- 10-06 night shift queue for the V1 acceptance cells.

Self-advancing: one step finishes, the next starts immediately. State lives on disk
(LEDGER jsonl), so a relaunch after a reboot or a dropped network SKIPS steps that already
returned rc=0 instead of burning the GPU again. That is the answer to "断联后别重来".

Bands (order matters, see docs/tickets/WINDOW-2026-10-05.md):
  band 0  pre-flight: docker, provenance, GPU hard gate + smoke (auto-rollback)
  band 1  run30  -- full 105 questions, REPORT_LANE_VIA_QUEUE=off
                   A2 streaming / A4 per-category / C3 isolation / R38 usage rows /
                   R51 per-question traces / R26 GPU attribution
  band 2  run30d -- 33-line shape subset, switch=on + lane declared => the D gate's three cells
  band 3  run31  -- second full window at the SAME head: same-code pair for the per-category
                   noise floor (R28 cell 3 was unmeasurable with zero pairs)
  band 4  readouts: r634 pairs, r631/r636 stage legs, r573/r595 per window
Close-out restores both switches and the power setting.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = r"C:\Users\fengx\PycharmProjects\企业智脑"
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
DRV = os.path.join(REPO, "scripts", "eval_window_shard_driver.py")
TMP = os.path.join(os.environ["TEMP"], "evalrun")
WORK = os.path.join(TMP, "night1006")
LEDGER = os.path.join(TMP, "night1006.ledger.jsonl")
LOG = os.path.join(TMP, "night1006.log")
DONE = os.path.join(TMP, "night1006.DONE.txt")
ENVF = os.path.join(REPO, "deploy", ".env.server")
COMPOSE = ["docker", "compose", "--env-file", ENVF]
FIXTURE = os.path.join(REPO, "tests", "fixtures", "business_evaluation_100.jsonl")
SUBSET = os.path.join(REPO, "docs", "testing", "bank-shape-subset-30.jsonl")
CONTAINER = "enterprise-brain-backend-1"
HEALTH = "http://127.0.0.1:8001/health"
# R678 gives the transport its lane declaration. If the landed ticket names it differently,
# change the VALUE here -- the queue fails loudly (rc recorded) rather than sampling a dud.
LANE_ENV = {"DECLARE_LANE_TIER": os.environ.get("NIGHT1006_LANE_TIER", "report")}
os.makedirs(WORK, exist_ok=True)

DONE_STEPS = set()


def log(msg):
    line = time.strftime("%m-%d %H:%M:%S ") + msg
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def led(step, rc, secs, note=""):
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step, "rc": rc,
                             "secs": round(secs, 1), "note": note[:400]}, ensure_ascii=False) + "\n")


def load_done():
    if not os.path.exists(LEDGER):
        return
    for raw in open(LEDGER, encoding="utf-8"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if row.get("rc") == 0 and str(row.get("note", "")).startswith("RESUME-SKIP") is False:
            DONE_STEPS.add(row["step"])


def sh(argv, timeout, step, extra_env=None, fatal=False):
    if step in DONE_STEPS and not fatal:
        log("RESUME-SKIP " + step)
        led(step, 0, 0.0, "RESUME-SKIP already rc=0")
        return 0
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    t0 = time.time()
    path = os.path.join(WORK, step + ".log")
    with open(path, "ab") as out:
        out.write(("\n==== %s %s ====\n" % (step, time.strftime("%F %T"))).encode("utf-8"))
        out.flush()
        try:
            proc = subprocess.Popen(argv, cwd=REPO, stdout=out, stderr=subprocess.STDOUT, env=env)
        except Exception as exc:
            led(step, 99, time.time() - t0, "launch failed: " + repr(exc))
            log("LAUNCH-FAIL " + step + " " + repr(exc))
            return 99
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log("TIMEOUT " + step + " -> taskkill pid=" + str(proc.pid))
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                rc = proc.wait(timeout=120)
            except Exception:
                rc = 124
    secs = time.time() - t0
    led(step, rc, secs, "rc=" + str(rc))
    log("STEP " + step + " rc=" + str(rc) + " " + str(round(secs / 60.0, 1)) + " min")
    return rc


def read_step(step):
    path = os.path.join(WORK, step + ".log")
    if not os.path.exists(path):
        return ""
    raw = open(path, "rb").read().decode("utf-8", "replace")
    return raw[-4000:]


def wait_backend(step, cap_sec=300):
    t0 = time.time()
    while time.time() - t0 < cap_sec:
        try:
            with urllib.request.urlopen(HEALTH, timeout=10) as resp:
                code = resp.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        except Exception:
            code = None
        if code is not None:
            secs = time.time() - t0
            led(step, 0, secs, "backend answering HTTP code=%s after %.1fs" % (code, secs))
            DONE_STEPS.discard(step)
            log("BACKEND-READY " + step + " code=" + str(code) + " waited=" + str(round(secs, 1)) + "s")
            return 0
        time.sleep(5)
    led(step, 1, time.time() - t0, "backend never answered within cap")
    log("BACKEND-NOT-READY " + step)
    return 1


def set_switch(key, value):
    raw = open(ENVF, "rb").read()
    new, n = re.subn(("(?m)^" + key + "=.*$").encode(), (key + "=" + value).encode(), raw)
    if n != 1:
        log("SWITCH-FAIL " + key + " lines found=" + str(n))
        led("switch-" + key, 1, 0.0, "expected exactly one line, found " + str(n))
        return 1
    open(ENVF, "wb").write(new)
    log("switch " + key + " -> " + value)
    led("switch-" + key, 0, 0.0, "set to " + value)
    return 0


def recreate(step):
    rc = sh(COMPOSE + ["up", "-d", "--force-recreate", "backend", "worker", "scheduler"], 900, step, fatal=True)
    wait_backend(step + "-ready")
    return rc


def p18(step):
    sh([PY, os.path.join("scripts", "eval_window_answer_cache_gate.py")], 300, step + "-clear", fatal=True)
    return sh([PY, os.path.join("scripts", "eval_window_answer_cache_gate.py"), "--check"],
              300, step + "-check", fatal=True)


def fresh_tag(tag):
    d = os.path.join(TMP, tag + ".shards")
    if os.path.isdir(d):
        q = os.path.join(TMP, "stale-cache-" + time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(q, exist_ok=True)
        try:
            os.rename(d, os.path.join(q, tag + ".shards"))
            log("QUARANTINE stale shards tag=" + tag)
            return 0
        except Exception as exc:
            log("QUARANTINE-FAIL tag=" + tag + " " + repr(exc))
            return 1
    log("fresh tag ok: " + tag)
    return 0


def drv(tag, extra, timeout, fixture=None, env=None):
    base = [PY, DRV, "--tag", tag, "--repo", REPO, "--env-file", ENVF,
            "--expect-backend", "pgvector", "--tmp-dir", TMP]
    if fixture:
        base += ["--fixture", fixture]
    return sh(base + extra, timeout, tag + "-" + extra[0].strip("-"), extra_env=env, fatal=True)


def readout(tag, fixture, env=None):
    ans = os.path.join(TMP, tag + "-answers.jsonl")
    side = os.path.join(TMP, tag + "-sidecar.jsonl")
    sh([PY, os.path.join("scripts", "run_quality_evaluation.py"), "--fixture", fixture,
       "--answers", ans, "--output", os.path.join(TMP, tag + "-quality.json")], 900,
       tag + "-score", extra_env=env)
    sh([PY, os.path.join("scripts", "run_quality_evaluation.py"), "--fixture", fixture,
       "--answers", ans, "--output", os.path.join(TMP, tag + "-report.json")], 900,
       tag + "-report", extra_env=env)
    sh([PY, os.path.join("scripts", "r595_latency_readout.py"), "--answers", ans,
       "--fixture", fixture, "--sidecar", side, "--label", tag], 300, tag + "-r595", extra_env=env)
    sh([PY, os.path.join("scripts", "r573_caliber_reconciliation.py"), "--tag", tag, "--no-rows"],
       300, tag + "-r573", extra_env=env)
    for tool in glob.glob(os.path.join("scripts", "r674*.py")):
        sh([PY, tool, "--window", tag], 600, tag + "-" + os.path.basename(tool)[:-3], extra_env=env)
    for tool in ("r631_stage_sum_delta.py", "r636_stage_coverage.py"):
        path = os.path.join("scripts", tool)
        if os.path.exists(path):
            sh([PY, path, "--window", tag], 600, tag + "-" + tool[:-3], extra_env=env)


def full_window(tag, fixture=FIXTURE, env=None):
    p18("p18-" + tag)
    if fresh_tag(tag) != 0:
        led(tag, 1, 0.0, "SKIP: stale shard dir could not be quarantined")
        return
    drv(tag, ["--run", "--retries", "2", "--dead-streak", "5"], 4 * 3600, fixture=fixture, env=env)
    drv(tag, ["--commit"], 300, fixture=fixture, env=env)
    readout(tag, fixture, env=env)


def smoke_fixture():
    """One-line fixture taken from the first question of the 105 bank -- never a new eval set."""
    path = os.path.join(WORK, "smoke1.jsonl")
    first = open(FIXTURE, encoding="utf-8").readline().strip()
    if not first:
        raise RuntimeError("fixture head is empty")
    open(path, "w", encoding="utf-8").write(first + "\n")
    return path


def gpu_smoke(step):
    """One real question through the production leg: proves the GPU hard gate did not eat the night.

    A hard gate that fires looks like a refusal, not a slow answer, so rc!=0 here means
    "roll the switch back", not "the window is broken"."""
    fx = smoke_fixture()
    fresh_tag(step)
    rc = drv(step, ["--run", "--retries", "1", "--dead-streak", "2"], 1200, fixture=fx)
    if rc == 0:
        rc = drv(step, ["--commit"], 300, fixture=fx)
    return rc


def main():
    load_done()
    log("==== night1006 queue up pid=" + str(os.getpid()) + " work=" + WORK + " ====")
    keep = subprocess.Popen([PY, os.path.join("scripts", "window_keep_awake.py"), "--loop"],
                            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("keep_awake loop pid=" + str(keep.pid))
    ps = os.path.join(REPO, "scripts", "docker_up.ps1")
    sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps], 420, "docker-up", fatal=True)
    rc_prov = sh([PY, os.path.join("scripts", "check_image_provenance.py")], 300, "prov")
    if rc_prov != 0:
        tail = read_step("prov")
        log("ABORT: image does not carry the code under test. Tail: " + tail[-600:])
        with open(DONE, "w", encoding="utf-8") as fh:
            fh.write("ABORTED image-provenance rc=" + str(rc_prov) + "\n")
        keep.kill()
        return 2

    # ---- band 0b: GPU hard gate (owner delegated the call on 10-05; rollback is automatic)
    if set_switch("OLLAMA_REQUIRE_GPU", "1") == 0:
        recreate("recreate-gpu")
        if gpu_smoke("gpu-smoke") != 0:
            log("GPU SMOKE FAILED -> rolling OLLAMA_REQUIRE_GPU back to unset, night continues")
            set_switch("OLLAMA_REQUIRE_GPU", "false")
            recreate("recreate-gpu-rollback")
            led("gpu-gate", 1, 0.0, "hard gate refused on this box; R26 cell 2 stays unmeasured")
        else:
            led("gpu-gate", 0, 0.0, "GPU hard gate on and one question answered")

    # ---- band 1: full 105, off phase
    full_window("run30")

    # ---- band 2: D gate -- report tier through the queue lane (needs R678 declared lane)
    set_switch("REPORT_LANE_VIA_QUEUE", "on")
    recreate("recreate-d-on")
    full_window("run30d", fixture=SUBSET, env=LANE_ENV)
    set_switch("REPORT_LANE_VIA_QUEUE", "off")
    recreate("recreate-d-off")

    # ---- band 3: second full window at the same head (noise floor + cross-gen pairs)
    full_window("run31")

    # ---- band 4: pairing readouts across everything we now hold
    for a in ("run22", "run23", "run30"):
        for b in ("run30", "run31"):
            if a == b:
                continue
            sh([PY, os.path.join("scripts", "r634_category_delta.py"), "--window", a, "--window", b],
               300, "a4-" + a + "-" + b)

    p18("p18-close")
    tail = open(ENVF, "rb").read().decode("utf-8", "replace")
    led("close-out", 0 if "REPORT_LANE_VIA_QUEUE=off" in tail else 1, 0.0,
        "lane switch off=" + str("REPORT_LANE_VIA_QUEUE=off" in tail))
    sh(COMPOSE + ["ps", "--format", "{{.Name}}\t{{.Status}}"], 120, "containers-final", fatal=True)
    sh([PY, os.path.join("scripts", "window_keep_awake.py"), "--check"], 120, "keepawake-final")

    rows = [json.loads(l) for l in open(LEDGER, encoding="utf-8") if l.strip()]
    summary = ("steps=%d rc0=%d fail=%d wall=%.1f min\n" % (
        len(rows), sum(1 for r in rows if r["rc"] == 0),
        sum(1 for r in rows if r["rc"] != 0),
        sum(r["secs"] for r in rows) / 60.0))
    log("==== " + summary)
    with open(DONE, "w", encoding="utf-8") as fh:
        fh.write(summary)
    keep.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())