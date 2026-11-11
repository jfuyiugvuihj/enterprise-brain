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
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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
#: R678 reads the declaration through EVAL_DECLARE_LANE_TIER (see
#: scripts/eval_transport_ask_v2.py::DECLARE_LANE_TIER), and the tier roster is
#: scripts/eval_transport_ask_v2.py::LANE_BY_TIER, whose keys are the Chinese tier names.
#: The night run passed DECLARE_LANE_TIER=report, which the tool never reads: a silent dud.
LANE_ENV = {
    "EVAL_DECLARE_LANE_TIER": os.environ.get("NIGHT1006_LANE_TIER", "\u62a5\u544a"),
    "EVAL_POST_APPROVAL_READBACK": "on",
    "REPORT_LANE_VIA_QUEUE": "on",
}
#: Sync-phase windows must say so out loud instead of leaving the key absent.
SYNC_ENV = {"EVAL_DECLARE_LANE_TIER": "sync"}
os.makedirs(WORK, exist_ok=True)

#: The subset window is only a D-gate sample if the ruler is told the real
#: denominator; 105 was hard-wired into run30d and made rc=2 on a healthy window.
def count_fixture_rows(path):
    with io.open(path, encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


#: Which windows claim the queue lane. Keep this in step with the bands in main().
LANE_PHASE_BY_TAG = {"run30d": "on", "run32d": "on"}


def lane_phase_for(tag):
    return LANE_PHASE_BY_TAG.get(tag, "off")


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
    """Rewrite one key in deploy/.env.server, appending it when the file has no such line.

    OLLAMA_REQUIRE_GPU is *absent* on this box (that is the fail-open state), so a subn that
    demands exactly one hit would report SWITCH-FAIL and the GPU gate would never run at all.
    """
    raw = open(ENVF, "rb").read()
    new, n = re.subn(("(?m)^" + key + "=.*$").encode(), (key + "=" + value).encode(), raw)
    if n == 0:
        sep = b"" if raw.endswith(b"\n") or not raw else b"\n"
        raw = raw + sep + (key + "=" + value).encode() + b"\n"
        new, n = raw, 1
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


def r674_pg_gate_name():
    """PG 腿那枚环境变量名从量具自己那一行取，本件不抄第二份（R720 判据①）。"""
    src = open(os.path.join("scripts", "r674_window_trace_export.py"), encoding="utf-8").read()
    m = re.search(r'^PG_OPT_IN_ENV = "(.+?)"', src, re.M)
    return m.group(1) if m else ""



def r674_pg_user():
    """PG 腿的用户名向 compose 的 postgres 服务现取：量具缺省 postgres 在这台机上不存在（R720）。

    取不到就交回空串 —— 调用侧宁可退回旧行为，也不在这里手抄第二份部署事实。
    """
    try:
        completed = subprocess.run(
            COMPOSE + ['exec', '-T', 'postgres', 'printenv', 'POSTGRES_USER'],
            capture_output=True, text=True, timeout=60)
    except Exception:
        return ''
    value = (completed.stdout or '').strip()
    if completed.returncode != 0 or not re.fullmatch('[A-Za-z0-9_]+', value):
        return ''
    return value


def readout_artifacts(tag):
    """读数落点名的唯一出处：-quality.json / -report.json（fresh_tag 与 readout 共用一份）。"""
    return [os.path.join(TMP, tag + suffix) for suffix in ("-quality.json", "-report.json")]


def window_artifacts(tag):
    """一扇窗在盘上的全部落点。文件名一律从量具自己的 paths() 派生，本件不抄第二份。"""
    spec = importlib.util.spec_from_file_location("eval_window_shard_driver", DRV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    listed = mod.paths(tag, Path(TMP))
    paths = [listed[key] for key in ("root", "window", "shards", "sidecar", "frames", "answers", "log")]
    paths += [Path(path) for path in readout_artifacts(tag)]
    return [path for path in paths if path.exists()]


def fresh_tag(tag):
    """开窗前整体清场：这一 tag 的盘上落点全部搬进隔离目录，只搬不删。

    必须**整体**搬。<tag>.window.json 是这扇窗五枚指纹的唯一记录，量具每次动手都先比它；
    旧写法只搬 <tag>.shards 而把指纹记留在盘上，于是重开同一扇窗时量具按「半窗混库比丢一窗
    更坏」当场 REFUSE。10-06 18:0x 实测：run32-run 0.5 秒 rc=2，一扇 105 题的全窗就这样空跑，
    而下游 11 枚读数全部跟着变红--账面看着像「窗跑过了」，其实一格都没量。
    """
    artifacts = window_artifacts(tag)
    if not artifacts:
        log("fresh tag ok: " + tag)
        return 0
    q = os.path.join(TMP, "stale-cache-" + time.strftime("%Y%m%d-%H%M%S") + "-" + tag)
    try:
        os.makedirs(q, exist_ok=True)
        moved = []
        for src in artifacts:
            dst = os.path.join(q, src.name)
            os.rename(str(src), dst)
            moved.append(src.name)
        log("QUARANTINE stale tag=" + tag + " moved=" + str(len(moved)) +
            " into " + q + " names=" + ",".join(moved))
        return 0
    except Exception as exc:
        log("QUARANTINE-FAIL tag=" + tag + " " + repr(exc))
        return 1


def drv(tag, extra, timeout, fixture=None, env=None):
    base = [PY, DRV, "--tag", tag, "--repo", REPO, "--env-file", ENVF,
            "--expect-backend", "pgvector", "--tmp-dir", TMP]
    if fixture:
        base += ["--fixture", fixture]
    return sh(base + extra, timeout, tag + "-" + extra[0].strip("-"), extra_env=env, fatal=True)


def readout(tag, fixture=FIXTURE, env=None):
    ans = os.path.join(TMP, tag + "-answers.jsonl")
    side = os.path.join(TMP, tag + "-sidecar.jsonl")
    quality, report = readout_artifacts(tag)
    sh([PY, os.path.join("scripts", "run_quality_evaluation.py"), "--fixture", fixture,
       "--answers", ans, "--output", quality], 900, tag + "-score", extra_env=env)
    sh([PY, os.path.join("scripts", "run_quality_evaluation.py"), "--fixture", fixture,
       "--answers", ans, "--output", report], 900, tag + "-report", extra_env=env)
    sh([PY, os.path.join("scripts", "r595_latency_readout.py"), "--answers", ans,
       "--fixture", fixture, "--sidecar", side, "--label", tag], 300, tag + "-r595", extra_env=env)
    n_rows = count_fixture_rows(fixture)
    r573 = [PY, os.path.join("scripts", "r573_caliber_reconciliation.py"), "--tag", tag,
            "--no-rows", "--expect-denominator", str(n_rows),
            "--expect-lane-phase", lane_phase_for(tag)]
    sh(r573, 300, tag + "-r573", extra_env=env)
    #: R720：真窗的分段腿在 PG 里，而 r674 出厂即关两枚闸、缺省落件位又落在仓内 ⇒ r631/r636
    #: 在 evalrun 目录永远找不到件、恒 rc=3/4。两枚闸一起递，out 直接落在窗的产物目录；
    #: 取不到常量名就退回旧行为（绝不让读数腿把窗带崩）。
    pg_gate = r674_pg_gate_name()
    pg_user = r674_pg_user()
    for tool in glob.glob(os.path.join("scripts", "r674*.py")):
        extra, env2 = [], dict(env or {})
        if pg_gate and os.path.basename(tool).startswith("r674_window_trace_export"):
            extra = ["--from-postgres", "--out", os.path.join(TMP, tag + "-traces.jsonl")]
            env2[pg_gate] = "on"
            if pg_user:
                extra += ["--user", pg_user]
        sh([PY, tool, "--window", tag] + extra, 900,
           tag + "-" + os.path.basename(tool)[:-3], extra_env=env2)
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