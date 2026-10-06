"""day1006_queue.py -- 10-06 daytime self-advancing queue for the V1 acceptance cells.

Why this file exists: the night queue closed at 01:20:22 and nothing ran until 09:52, because
every following step was waiting for the control thread to speak. Deterministic steps must not
live in a chat thread. Here one step finishing starts the next one immediately; a relaunch
resumes from the ledger and skips steps that already returned rc=0, so a dropped network or a
reboot never re-burns the GPU.

It reuses the night module's primitives (sh/led/log/drv/readout/full_window/set_switch/
recreate/p18/fresh_tag) and only redirects the artifacts to day1006 paths, so there is one
implementation of the window mechanics, not two that can disagree.

Bands (order matters):
  band 0  docker up; image provenance; rebuild + recreate only when the image is behind HEAD
  band 1  run32  -- full 105 questions, sync phase declared out loud (EVAL_DECLARE_LANE_TIER=sync)
                   cells: A2 streaming, A4 per-category vs run30/run31, R26 GPU attribution,
                          R38 usage rows (R670), R51 per-question traces (R674 exporter)
  band 2  run32d -- 33-line shape subset with REPORT_LANE_VIA_QUEUE=on and the report tier
                   declared => the D gate's three cells. The night run passed an env name the
                   tool never reads, so run30d was a dud; see night1006_queue.py::LANE_ENV.
  band 3  run33  -- second full window in the same generation (A4 needs a pair)
  band 4  pairing readouts: r634 over the counterpart windows that still exist on disk
          (run22/run23 were destroyed by accident #124; the band names every skip)
  close   restore switches, p18 gate, container ps, DONE summary

Nothing here needs the internet: ollama/postgres/redis live inside the compose network and the
model is reached by container name. Only `git push` needs a wire, and that stays outside this file.
"""
import json
import os
import subprocess
import sys
import time

REPO = r"C:\Users\fengx\PycharmProjects\企业智脑"
sys.path.insert(0, os.path.join(REPO, "scripts"))
import night1006_queue as Q  # noqa: E402  (the shared window primitives)

TMP = Q.TMP
Q.WORK = os.path.join(TMP, "day1006")
Q.LOG = os.path.join(TMP, "day1006.log")
Q.LEDGER = os.path.join(TMP, "day1006.ledger.jsonl")
Q.DONE = os.path.join(TMP, "day1006.DONE.txt")
PY, sh, log, led = Q.PY, Q.sh, Q.log, Q.led
COMPOSE = Q.COMPOSE
FIXTURE, SUBSET = Q.FIXTURE, Q.SUBSET
PREV_WANTED = ("run22", "run23", "run30", "run31")
#: A window is only pairable when its five readout files survived on disk. Two of the
#: wanted ones were eaten by accident #124 (an agent's rmtree over %TEMP%), so the
#: pairing band names what it skipped instead of silently returning a red rc.
MINE = ("run32", "run32d", "run33")
PAIRABLE = ("run32", "run33")


def readable(tag):
    return os.path.exists(os.path.join(TMP, tag + "-report.json"))


def prev_windows():
    keep = [w for w in PREV_WANTED if readable(w)]
    for w in PREV_WANTED:
        if w not in keep:
            led("pair-skip-" + w, 0, 0.0, "MISSING on disk (accident #124) -- not a red")
    return tuple(keep)



def head_sha():
    return subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def ensure_generation(step):
    """Make the container carry the code under test, then prove it.

    check_image_provenance compares the image label with the build inputs; when the tree moved
    ahead of the image the only honest fix is a rebuild plus a recreate. Skipping this is how a
    window ends up measuring last night's code and calling it today's.
    """
    if sh([PY, os.path.join("scripts", "check_image_provenance.py")], 300, step + "-prov") == 0:
        led(step + "-no-rebuild", 0, 0.0, "image already carries HEAD=" + head_sha()[:7])
        return 0
    env = {"GIT_SHA": head_sha()}
    rc = sh(COMPOSE + ["build", "migrate"], 3600, step + "-build", extra_env=env, fatal=True)
    if rc != 0:
        return rc
    rc = sh(COMPOSE + ["up", "-d", "--force-recreate", "backend", "worker", "scheduler"],
            900, step + "-recreate", fatal=True)
    Q.wait_backend(step + "-recreate-ready")
    return sh([PY, os.path.join("scripts", "check_image_provenance.py")], 300, step + "-prov2",
              fatal=True)


def claims(tag):
    """C 门第四格的分母在不在：0＝MEASURED，3＝NOT_MEASURED（行在而 claims 全空），2＝窗件没跑到。

    这一枚不是牙，是把「unsupported_claim_rate=0.0」那两种成因分开的读数口；
    rc=3 不许当失败炸掉夜窗，也不许当达标写进账——它写的是「没有分母的 0」。
    """
    rc = sh([PY, os.path.join("scripts", "r704_claims_coverage_readout.py"), "--window", tag],
            300, tag + "-r704-claims")
    led(tag + "-r704-verdict", 0 if rc == 0 else 1, 0.0,
        "denominator=" + {0: "MEASURED", 3: "NOT_MEASURED", 2: "WINDOW-MISSING"}.get(rc, "rc=" + str(rc)))
    return rc


def pairing():
    prev = prev_windows()
    if not prev:
        led("a4-pairing-nothing-to-pair", 1, 0.0,
            "no surviving counterpart window -- A4 stays unproven, say so in the book")
        return
    for a in prev:
        for b in MINE:
            sh([PY, os.path.join("scripts", "r634_category_delta.py"), "--window", a,
                "--window", b], 300, "a4-" + a + "-" + b)
    if readable("run32") and readable("run33"):
        sh([PY, os.path.join("scripts", "r634_category_delta.py"), "--window", "run32",
            "--window", "run33"], 300, "a4-same-generation-run32-run33")


def ensure_baseline_switch_off(step):
    """每一轮开局先把 sync 相钉死，再动 band 1。

    band 2 会把 REPORT_LANE_VIA_QUEUE 拧到 on（D 相），跑完才拧回来。若两轮之间进程死在 band 2
    里、或机器重启，盘上留下的就是 on--那一轮 band 1 的 105 题全窗就量在错的相态上，
    而 r573 的 --expect-lane-phase off 会把它当红拒收。开窗条件不能指望上一轮的收尾：
    跟 ensure_generation 一样现读现校。
    """
    raw = open(Q.ENVF, "rb").read().decode("utf-8", "replace")
    if "REPORT_LANE_VIA_QUEUE=off" in raw:
        led(step, 0, 0.0, "switch already off")
        log("baseline switch already off")
        return 0
    log("baseline switch NOT off -- forcing off + recreate")
    if Q.set_switch("REPORT_LANE_VIA_QUEUE", "off") != 0:
        led(step, 1, 0.0, "set_switch failed")
        return 1
    return Q.recreate(step + "-recreate")


def main():
    os.makedirs(Q.WORK, exist_ok=True)
    Q.load_done()
    log("==== day1006 queue up pid=" + str(os.getpid()) + " head=" + head_sha()[:7] + " ====")
    keep = subprocess.Popen([PY, os.path.join("scripts", "window_keep_awake.py"), "--loop"],
                            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("keep_awake loop pid=" + str(keep.pid))
    ps = os.path.join(REPO, "scripts", "docker_up.ps1")
    sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps], 420,
       "docker-up", fatal=True)

    if ensure_generation("gen") != 0:
        log("ABORT: the container does not carry the code under test")
        with open(Q.DONE, "w", encoding="utf-8") as fh:
            fh.write("ABORTED image-generation head=" + head_sha()[:7] + "\n")
        keep.kill()
        return 2

    if ensure_baseline_switch_off("baseline-switch-off") != 0:
        log("ABORT: cannot put the sync-phase switch back to off")
        keep.kill()
        return 2

    Q.full_window("run32", env=Q.SYNC_ENV)
    sh([PY, os.path.join("scripts", "r631_stage_sum_delta.py"), "--window", "run32"], 600,
       "run32-r631-lane-off", extra_env=Q.SYNC_ENV)
    claims("run32")

    # D gate: the report tier through the queue lane, declared explicitly on both sides.
    Q.set_switch("REPORT_LANE_VIA_QUEUE", "on")
    Q.recreate("recreate-d-on")
    Q.full_window("run32d", fixture=SUBSET, env=Q.LANE_ENV)
    Q.set_switch("REPORT_LANE_VIA_QUEUE", "off")
    Q.recreate("recreate-d-off")

    # band 3: a second full window in the same generation, so A4 gets a pair that is not
    # measured against last night's code. Same switches, same declared sync phase.
    Q.full_window("run33", env=Q.SYNC_ENV)
    sh([PY, os.path.join("scripts", "r631_stage_sum_delta.py"), "--window", "run33"], 600,
       "run33-r631-lane-off", extra_env=Q.SYNC_ENV)
    claims("run33")

    # band 5: R44 格一（覆盖 95% 查询的热集常驻）——在册覆盖率量具当场取数，要现读建库，
    # 所以排在两扇全窗之后：这时机器只余队列自己，量到的才是安静机器上的数。
    sh([PY, os.path.join("scripts", "r677_hot_set_yield.py"), "--json", "--coverage",
        "--timeout-seconds", "900",
        "--out", os.path.join(Q.TMP, "r677-coverage-day1006.json")], 1200, "r44-coverage-r677")

    pairing()
    Q.p18("p18-close")
    tail = open(Q.ENVF, "rb").read().decode("utf-8", "replace")
    led("close-out", 0 if "REPORT_LANE_VIA_QUEUE=off" in tail else 1, 0.0,
        "lane switch off=" + str("REPORT_LANE_VIA_QUEUE=off" in tail))
    sh(COMPOSE + ["ps", "--format", "{{.Name}}\t{{.Status}}"], 120, "containers-final")

    rows = [json.loads(l) for l in open(Q.LEDGER, encoding="utf-8") if l.strip()]
    summary = ("steps=%d rc0=%d fail=%d wall=%.1f min head=%s\n" % (
        len(rows), sum(1 for r in rows if r["rc"] == 0),
        sum(1 for r in rows if r["rc"] != 0), sum(r["secs"] for r in rows) / 60.0,
        head_sha()[:7]))
    #: 同一枚步骤在多轮里只认最新那一笔（早先的红已经被后面那轮治掉的不算红）。
    latest = {}
    for r in rows:
        latest[str(r.get("step"))] = r.get("rc")
    #: DONE 让看门狗退场，所以它只许在「采窗真落地」之后才写：三扇窗的 -run/-commit 一枚不绿
    #: 就不写 DONE，让看门狗按账本跳过 rc=0 的步骤重投一轮。旧写法是无条件写 DONE，于是
    #: band 1 空跑 rc=2 的 run32 永远不会被再试一次--机器天亮前就闲下来了（在册病根 ⑪）。
    collecting = [s for tag in MINE for s in (tag + "-run", tag + "-commit")]
    uncollected = [s for s in collecting if latest.get(s, 1) != 0]
    log("==== " + summary)
    keep.kill()
    if uncollected:
        log("NOT-DONE: window collection still red: " + ",".join(uncollected) +
            " -- watchdog will relaunch from the ledger")
        return 3
    with open(Q.DONE, "w", encoding="utf-8") as fh:
        fh.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())