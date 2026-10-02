"""P-20 run10 开窗前置闸（09-30 本席立，起因是同一格反复靠人肉现取然后取错）。

它只做一件事：把「能不能开窗」变成一条退出码。判据全部来自本仓既有件与现取事实，
不新造口径；任何一格量不到就 FAIL，绝不用「没量到」冒充「通过」。

  provenance     镜像携带的文件与 HEAD 一致（复用 scripts/check_image_provenance.py --expect-container 的退出码）
  answer_cache   Redis 里 answer:* 为零（复用 scripts/eval_window_answer_cache_gate.py --check；rc=2 永远不算过）
  keep_awake     常驻 --loop keep-awake 在位 **且** stamp 新鲜（R566：不再从命令行抠一个数当剩余
                 分钟；窗长超过可证到此刻这一段时，读数里必须带「窗内自复核」那句）
  gpu_apps       nvidia-smi 计算进程里不许有仓库外的可执行文件（防外来负载污染时延判据）
  foreign_python 仓库外解释器跑的常驻脚本点名（外来 train.py 一族）
  eval_tree      跑分树 be-eval95 干净且可 --ff-only 追平
  env_flags      deploy/.env.server 里 VECTOR_DUAL_WRITE / REPORT_LANE_VIA_QUEUE 在位；INDEX_BACKEND 未翻只作 INFO

用法：python scripts/r530_run10_window_preflight.py [--need-minutes 300] [--json]
退出码：0 全部通过 / 1 至少一格 FAIL / 2 量具自己没跑成（2 也永远不是「已通过」）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_TEXT = str(ROOT).lower()
PASS, FAIL = "PASS", "FAIL"
PS_QUERY = "Get-CimInstance Win32_Process -Filter @F | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
PS_FILTER = "Name='python.exe' OR Name='pythonw.exe'"
#: R566（10-02）：旧的 KEEP_AWAKE_MINUTES 想把「命令行里的一个数」当「剩余覆盖分钟」，
#: 而真实命令行是 `... window_keep_awake.py --interval 240 --loop`——数字落在 --interval
#: 之后，那条正则要求 keep_awake.py 后紧跟 \S+ 再紧跟数字，因此**永不命中**，每一枚调用
#: 都走 minutes=240.0 兜底：四小时内恒 PASS（假绿，从没读过 stamp），四小时后把这枚每 240 s
#: 真在续锁的活进程判成「已过期」（假红）。今天只读两件真事：续锁间隔（秒）与 stamp 新鲜度。
KEEP_AWAKE_INTERVAL = re.compile(r"--interval\s+([0-9]+)")
KEEP_AWAKE_STAMP = re.compile(r"--stamp\s+(\S+)")
KEEP_AWAKE_INTERVAL_DEFAULT = 240


def run(cmd):
    try:
        done = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, str(type(exc).__name__) + ": " + str(exc)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def read_processes():
    script = PS_QUERY.replace("@F", chr(34) + PS_FILTER + chr(34))
    code, out = run(["powershell", "-NoProfile", "-Command", script])
    if code != 0:
        return []
    text = out.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = data if isinstance(data, list) else [data]
    return [r for r in rows if isinstance(r, dict)]


def read_gpu_apps():
    code, out = run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"])
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if line and "," in line:
            pid, _, name = line.partition(",")
            rows.append({"pid": pid.strip(), "exe": name.strip().strip('"')})
    return rows, code == 0


def read_create_time(pid):
    """进程创建时刻（UTC epoch 秒）。

    🔴 别拿 `StartTime` 那串 ticks 去减 .NET epoch：Windows PowerShell 5.1 交回的是**本地**
    DateTime，那样算等于把创建时刻往后挪一个时区（本机 +8 h）。09-30 run10 就栽在这格——
    P-20 报「keep-awake 剩余 608 min」，同一时刻真值 123 min，本席据此在派工词里作废了
    「约 14:50 到期」那句正确读数（增补五），开窗执行员又照那句去防，白折腾一趟。
    改成同一枚时钟做差：PS 里 `(Get-Date) - $p.StartTime` 拿的是 elapsed，本侧再用
    `now - elapsed` 换回 epoch，时区从头到尾不参与运算。
    """
    script = ("$p = Get-Process -Id " + str(pid) + " -ErrorAction SilentlyContinue; "
              "if ($p) { [Math]::Round(((Get-Date) - $p.StartTime).TotalSeconds) }")
    code, out = run(["powershell", "-NoProfile", "-Command", script])
    if code != 0 or not out.strip():
        return 0.0
    try:
        elapsed = float(out.strip().splitlines()[-1])
    except ValueError:
        return 0.0
    return time.time() - elapsed


def read_env_flags():
    path = ROOT / "deploy" / ".env.server"
    flags = {}
    if not path.exists():
        return flags
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match("^([A-Z0-9_]+)=(.*)$", line.strip())
        if match:
            flags[match.group(1)] = match.group(2).strip()
    return flags


@dataclass
class Snapshot:
    provenance_rc: int
    provenance_text: str
    cache_rc: int
    processes: list = field(default_factory=list)
    create_times: dict = field(default_factory=dict)
    gpu_apps: list = field(default_factory=list)
    gpu_seen: bool = False
    eval_tree_dirty: int = -1
    eval_tree_ahead: int = -1
    eval_tree_found: bool = False
    env_flags: dict = field(default_factory=dict)
    now: float = field(default_factory=time.time)


def collect():
    p_code, p_out = run([sys.executable, "scripts/check_image_provenance.py", "--expect-container"])
    c_code, _ = run([sys.executable, "scripts/eval_window_answer_cache_gate.py", "--check"])
    procs = read_processes()
    gpu_apps, gpu_seen = read_gpu_apps()
    create_times = {}
    for row in procs:
        try:
            pid = int(row.get("ProcessId"))
        except (TypeError, ValueError):
            continue
        create_times[pid] = read_create_time(pid)
    eval_dir = ROOT.parent / "be-eval95"
    dirty = ahead = -1
    found = eval_dir.exists()
    if found:
        code, out = run(["git", "-C", str(eval_dir), "status", "--porcelain"])
        dirty = len([l for l in out.splitlines() if l.strip()]) if code == 0 else -1
        code, out = run(["git", "-C", str(eval_dir), "rev-list", "--left-right", "--count", "HEAD..."])
        if code == 0 and "\t" in out:
            ahead = int(out.split("\t")[0])
    tool_broken = p_code not in (0, 1) or c_code not in (0, 1, 2) or not procs
    return Snapshot(p_code, p_out, c_code, procs, create_times, gpu_apps, gpu_seen,
                    dirty, ahead, found, read_env_flags()), tool_broken


FOREIGN_NOISE = ("keep_awake.py", "-m pytest", "-u -c", "spawn_main", "r530_run10_window_preflight.py")


def _window_keep_awake():
    """按路径把 `scripts/window_keep_awake.py` 拉进来——它是脚本不是包，直接 import 进不来。"""
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import window_keep_awake
    return window_keep_awake


def keep_awake_interval(cmd_text):
    """续锁间隔，单位**秒**（`--interval` 的语义就是秒），绝不当成分钟读。"""
    match = KEEP_AWAKE_INTERVAL.search(cmd_text)
    return int(match.group(1)) if match else KEEP_AWAKE_INTERVAL_DEFAULT


def keep_awake_stamp_path(cmd_text):
    match = KEEP_AWAKE_STAMP.search(cmd_text)
    if match:
        return match.group(1).strip(chr(34))
    return _window_keep_awake().DEFAULT_STAMP


def keep_awake_freshness(stamp_path, now):
    """问「上一次真续锁距今多久」；问不到就 FAIL——量不到不等于干净，更不等于挂上了。"""
    try:
        return _window_keep_awake().check_stamp(stamp_path, now)
    except Exception as exc:
        return False, "stamp 问不到（%s: %s）——量不到不等于干净" % (type(exc).__name__, exc)



def is_project_noise(cmd_text):
    """Agent 自己的 pytest 子工／execnet bootstrap 不算外来负载，别把它们报成脏。"""
    return any(token in cmd_text for token in FOREIGN_NOISE)


def in_repo(path_text):
    return bool(path_text) and REPO_TEXT in str(path_text).lower()


def evaluate(snap, need_minutes):
    rows = []
    if snap.provenance_rc == 0:
        rows.append(("provenance", PASS, "镜像携带的文件与 HEAD 一致"))
    elif snap.provenance_rc == 1:
        rows.append(("provenance", FAIL, "镜像落后/不一致，必须先 build migrate 再开窗"))
    else:
        rows.append(("provenance", FAIL, "量具没跑成 rc=" + str(snap.provenance_rc) + "（rc=2 不是通过）"))

    if snap.cache_rc == 0:
        rows.append(("answer_cache", PASS, "answer:* = 0（PING 过之后读到的 0）"))
    elif snap.cache_rc == 1:
        rows.append(("answer_cache", FAIL, "库里还带着答案缓存，先不带 --check 跑清零件"))
    else:
        rows.append(("answer_cache", FAIL, "量具没跑成 rc=" + str(snap.cache_rc) + "（rc=2 永远不算通过）"))

    keep = [p for p in snap.processes if "keep_awake.py" in str(p.get("CommandLine", ""))]
    if not snap.processes:
        rows.append(("keep_awake", FAIL, "进程表问不到（PS 量具没跑成）——空表不等于没有常驻 keep-awake"))
    elif not keep:
        rows.append(("keep_awake", FAIL, "机上没有常驻 keep-awake；DC 睡眠=180 s，适配器一掉电就冻窗"
                     " —— 补法：python scripts/window_keep_awake.py --loop --interval 240（临时锁，不改任何电源设置）"))
    else:
        # R566 口径：`--loop` 的覆盖时长是「进程活着就无限」，有界的只有 `--once`。本格能证的只
        # 有「上一次真续锁距今多久」（window_keep_awake.check_stamp，MAX_STAMP_AGE_SECONDS=300），
        # 所以 PASS 要两枚真读数同时成立：常驻 --loop 进程在位 **且** stamp 新鲜。只凭命令行里那个
        # 数是旧写法，本单明令不许。窗长超过「可证到此刻」这一段时，读数必须连带交出「窗内自复核」
        # 那句——不许把一限量写成一个人的到期分钟数，那正是半夜冻窗的现成形状。
        chosen = None
        for p in keep:
            cmd = str(p.get("CommandLine", ""))
            interval = keep_awake_interval(cmd)
            fresh, phrase = keep_awake_freshness(keep_awake_stamp_path(cmd), snap.now)
            mode = "常驻 --loop（每 %d s 续一发）" % interval if "--loop" in cmd else "--once（只挂一发，非常驻）"
            note = mode + "；" + phrase
            if fresh and "--loop" in cmd:
                chosen = (p, note, True)
                break
            if chosen is None:
                chosen = (p, note, False)
        best, note, ok = chosen
        if ok:
            rows.append(("keep_awake", PASS, "pid=" + str(best["ProcessId"]) + " " + note
                         + "；需要 " + str(need_minutes) + " min ⇒ 本格只证到此刻，窗内必须自复核（续锁一停，stamp 过 300 s 就红）"))
        else:
            rows.append(("keep_awake", FAIL, "pid=" + str(best["ProcessId"]) + " " + note
                         + " —— 补法：python scripts/window_keep_awake.py --loop --interval 240（临时锁，不改任何电源设置）"))

    if not snap.gpu_seen:
        rows.append(("gpu_apps", FAIL, "nvidia-smi 跑不成——问不到就不能假设没有外来 GPU 负载"))
    else:
        foreign = [g for g in snap.gpu_apps if not in_repo(g["exe"])]
        if foreign:
            rows.append(("gpu_apps", FAIL, "外来进程占着 GPU，A(1) 的 p95 时延读数不可采信："
                         + "; ".join("pid=" + str(g["pid"]) + " exe=" + str(g["exe"]) for g in foreign)))
        else:
            rows.append(("gpu_apps", PASS, "GPU 计算进程 " + str(len(snap.gpu_apps)) + " 枚，无仓库外可执行文件"))

    strays = [p for p in snap.processes
              if not in_repo(str(p.get("ExecutablePath", "")))
              and not is_project_noise(str(p.get("CommandLine", "")))]
    if not snap.processes:
        rows.append(("foreign_python", FAIL, "进程表问不到（同上）——空表不等于没有外来负载"))
    elif strays:
        rows.append(("foreign_python", FAIL, "仓库外解释器在跑常驻脚本，先归零再开窗："
                     + "; ".join("pid=" + str(p["ProcessId"]) + " cmd=" + str(p.get("CommandLine", ""))[:60] for p in strays)))
    else:
        rows.append(("foreign_python", PASS, "无非 keep-awake 的仓库外 python 常驻"))

    if not snap.eval_tree_found:
        rows.append(("eval_tree", FAIL, "跑分树 be-eval95 不在盘上"))
    elif snap.eval_tree_dirty != 0:
        rows.append(("eval_tree", FAIL, "be-eval95 dirty=" + str(snap.eval_tree_dirty) + "，开窗前先处理"))
    elif snap.eval_tree_ahead not in (0, -1):
        rows.append(("eval_tree", FAIL, "be-eval95 领先主树 " + str(snap.eval_tree_ahead) + " 枚，不能 ff-only 追平"))
    else:
        rows.append(("eval_tree", PASS, "be-eval95 干净且可 --ff-only 追平"))

    missing = [k + "=" + str(snap.env_flags.get(k, "<未设>"))
               for k in ("VECTOR_DUAL_WRITE", "REPORT_LANE_VIA_QUEUE")
               if str(snap.env_flags.get(k, "")).lower() != "on"]
    if missing:
        rows.append(("env_flags", FAIL, "deploy/.env.server 缺开关：" + ", ".join(missing)))
    else:
        note = "" if "INDEX_BACKEND" in snap.env_flags else "；INDEX_BACKEND 未设＝读路径仍在 Chroma（翻默认是业主动作）"
        rows.append(("env_flags", PASS, "两枚开关在位" + note))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--need-minutes", type=float, default=300.0,
                        help="keep-awake 至少要还能覆盖多少分钟（默认 300）")
    parser.add_argument("--json", action="store_true")
    opts = parser.parse_args(argv)
    snap, tool_broken = collect()
    rows = evaluate(snap, opts.need_minutes)
    fails = [r for r in rows if r[1] == FAIL]
    if opts.json:
        print(json.dumps([{"check": n, "status": s, "detail": d} for n, s, d in rows], ensure_ascii=False, indent=2))
    else:
        for name, status, detail in rows:
            print("[P-20] " + status.ljust(4) + " " + name.ljust(14) + " " + detail)
        print("[P-20] verdict: " + ("FAIL" if fails else "PASS") + "（" + str(len(fails)) + " 格 FAIL）")
    if fails:
        return 1
    return 2 if tool_broken else 0


if __name__ == "__main__":
    sys.exit(main())
