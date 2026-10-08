"""smoke_v1.py -- V1 的唯一验收门：九条用户旅程的端到端冒烟（2026-10-06 改章）。

跑法（缺省自带解释器：主树 .venv 没有 playwright 与 pillow，门自己用 uv 现拉）：

    python scripts/smoke_v1.py --env-file deploy/.env.server

要换解释器就 --python "...python"。走查件的第三方依赖只有 playwright 与 pillow 两枚，
缺任何一枚都是门红——10-06 首跑就是栽在 --with pillow 没写上（环 2 截图对撞要用 PIL）。

它只做一件事——把真容器·真模型·真浏览器里的九条旅程走一遍（复用 scripts/r694_walkthrough.py，
不另起第二套走查件），逐条给「能演示／不能演示／差在哪」，任一旅程不能演示就 exit=1。
账面坐标族不在这里（见 scripts/selfcheck_ledger.py，红只记账、不阻塞并树与发版）。
"""
import argparse
import json
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parents[1]
WALK = REPO / "scripts" / "r694_walkthrough.py"
WALK_PYTHON_DEFAULT = "uv run --no-project --with playwright==1.63.0 --with pillow python"
PASS = "达"
V1_RINGS = "1,2,3,4,5,6,7,8,9"
V2_RINGS = "10,11,12,13,14,15,16,17,18,19,20,21"


def preflight(base_url):
    """门红要能归因：前端与后端在不在位，先各探一枚。连不上就是环境没齐，别当产品红。"""
    bad = []
    for path in ("/", "/api/v1/health"):
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=5) as res:
                if res.status >= 400:
                    bad.append(path + " 交回 HTTP " + str(res.status))
        except Exception as exc:
            bad.append(path + " 连不上：" + str(exc)[:90])
    return bad


#: 端到端结论要落在真码上：每一族容器带的镜像必须不早于它那一路源码的最新一枚提交。
#: 两族分开量：backend/worker/scheduler 共用后端镜像（码源在 app/**），而 frontend/**
#: 是另一枚镜像（docker-compose.yml 的 frontend 格用 frontend/Dockerfile 自己
#: npm run build，不在 migrate 那条道上），改前端只有 docker compose build frontend
#: 才换码。以前这一族没人量：10-07 那笔前端修复 5c8cae5 全靠手工 build 加 recreate 才
#: 作数，屏上跑的前端比那笔新还是旧，当时量不出来（B22）。尺子与措辞同后端那一族逐字
#: 同形，拿不到读数照样门红。
CONTAINERS = ("backend", "worker", "scheduler")
FRONTEND_CONTAINERS = ("frontend",)

#: 三格一体：(源码路径, 容器名关键子串, 换码那一句)
FRESHNESS_TRACKS = (
    ("app", CONTAINERS,
     "重建后端镜像再 docker compose --env-file deploy/.env.server up -d --force-recreate "
     "backend worker scheduler"),
    ("frontend", FRONTEND_CONTAINERS,
     "docker compose --env-file deploy/.env.server build frontend 再 up -d --force-recreate "
     "frontend"),
)


def _iso(stamp):
    stamp = (stamp or "").strip()
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _track_freshness(source, keys, listed_names, listed_rc, rebuild_hint):
    """一族容器 vs 它那一路源码的最新提交：尺子只有一把，两族共用。"""
    bad = []
    proc = subprocess.run(["git", "log", "-1", "--format=%cI", "--", source],
                          cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    code_at = _iso(proc.stdout)
    if code_at is None:
        bad.append("问不到最新 " + source + " 提交时刻（git rc=" + str(proc.returncode)
                   + "）＝不判新鲜度也别宣布绿")
        return bad
    names = [n for n in listed_names if any(k in n for k in keys)]
    if not names:
        bad.append("容器名单里没有 " + "/".join(keys) + "（docker rc=" + str(listed_rc)
                   + "），拿不到启动时刻")
        return bad
    for name in names:
        insp = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", name],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        started = _iso(insp.stdout)
        if started is None:
            bad.append(name + " 问不到启动时刻：" + (insp.stderr or "").strip()[:80])
        elif started < code_at:
            bad.append(name + " 启动于 " + started.strftime("%m-%d %H:%M")
                       + "，早于最新 " + source + " 提交 " + code_at.strftime("%m-%d %H:%M")
                       + "＝容器带的是旧码，这轮端到端读数不清（换码：" + rebuild_hint + "）")
    return bad


def code_freshness():
    """两族容器的启动时刻 vs 各自那一路源码的最新提交时刻。

    拿不到读数不沉默——照样交回门红。后端那一族与前端那一族各判各的，两行的红都交出去：
    以前前端没重建时走查跑在旧页面上照样能报绿，那一格根本不在门上（B22）。
    """
    listed = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    listed_names = (listed.stdout or "").split()
    bad = []
    for source, keys, rebuild_hint in FRESHNESS_TRACKS:
        bad += _track_freshness(source, keys, listed_names, listed.returncode, rebuild_hint)
    return bad


def run_walk(out, env_file, base_url, rings, python_opt):
    argv = shlex.split(python_opt or WALK_PYTHON_DEFAULT) + [str(WALK)]
    cmd = argv + ["--env-file", env_file, "--base-url", base_url, "--rings", rings, "--out", str(out)]
    cmd += ["--fresh"]
    print("[smoke_v1] $ " + " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


def report(out, started, walk_rc, label=""):
    led = out / "ledger.json"
    if not led.exists():
        print("[smoke_v1] 走查件没交回账本（walk_rc=" + str(walk_rc) + "）：" + str(led) + " 不在盘上", flush=True)
        return 1, []
    doc = json.loads(led.read_text(encoding="utf-8"))
    rows = doc.get("rings") or []
    bad = [r for r in rows if r.get("status") != PASS]
    print("", flush=True)
    print("旅程 | 标题 | 结论 | 差在哪", flush=True)
    print("--- | --- | --- | ---", flush=True)
    for r in rows:
        note = str(r.get("note") or "").replace("\n", " ")
        verdict = "能演示" if r.get("status") == PASS else "不能演示"
        print(str(r.get("ring")) + " | " + str(r.get("title")) + " | " + verdict + " | " + note[:140], flush=True)
    print("", flush=True)
    print("[smoke_v1] " + str(len(rows) - len(bad)) + "/" + str(len(rows))
          + " 条能演示" + label + "（分母＝本轮真跑的 " + str(len(rows)) + " 条）；墙钟 "
          + str(round(time.time() - started, 1)) + " s；账本 " + str(led), flush=True)
    if walk_rc != 0:
        print("[smoke_v1] 走查件退出码 " + str(walk_rc) + "（环境/登录/容器问题同样算门红，不许推给非产品原因）", flush=True)
    return (1 if (bad or walk_rc != 0 or not rows) else 0), rows


def aggregate(out, rowsets, passes):
    """连续测试：同一套连跑 N 遍，逐环统计绿遍数。

    一遍绿不算稳。任一环没有遍遍绿就交回「抖动」并 exit=1——
    业主 2026-10-07 要的就是这个数：这功能到底是不是每回都演示得出来。
    """
    by_ring = {}
    for rows in rowsets:
        for row in rows:
            key = row.get("ring")
            hit = by_ring.setdefault(key, {"title": row.get("title"), "greens": 0, "runs": 0, "notes": []})
            hit["runs"] += 1
            if row.get("status") == PASS:
                hit["greens"] += 1
            else:
                hit["notes"].append(str(row.get("note") or "").replace("\n", " ")[:110])
    print("", flush=True)
    print("[smoke_v1] 连续测试：同一套连跑 " + str(passes) + " 遍，逐环统计（绿遍数＝几遍演示得出来）", flush=True)
    print("环 | 标题 | 绿遍数 | 不稳的差在哪", flush=True)
    print("--- | --- | --- | ---", flush=True)
    unstable = 0
    for key in sorted(by_ring, key=lambda x: (x is None, x)):
        hit = by_ring[key]
        shake = "" if hit["greens"] == hit["runs"] else " ←抖动"
        unstable += 0 if hit["greens"] == hit["runs"] else 1
        print(str(key) + " | " + str(hit["title"]) + " | " + str(hit["greens"]) + "/" + str(hit["runs"]) + shake
              + " | " + " ;; ".join(hit["notes"])[:150], flush=True)
    print("", flush=True)
    print("[smoke_v1] 连跑 " + str(passes) + " 遍：稳定 " + str(len(by_ring) - unstable) + "/" + str(len(by_ring))
          + " 环；账本 " + str(out) + "\pass1 … pass" + str(passes), flush=True)
    return 1 if unstable else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env-file", default=str(REPO / "deploy" / ".env.server"))
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--suite", choices=("v1", "v2"), default="v1",
                    help="v1＝九条旅程（缺省）；v2＝环 10–21 那张 V2 演示面（十二环，全 13 屏都走到）。两张分母分开报，别拿一张盖另一张")
    ap.add_argument("--repeat", type=int, default=1,
                    help="同一套连跑几遍（连续测试）。任一环没遍遍绿就报抖动并 exit=1")
    ap.add_argument("--rings", default="", help="点名要跑的环号；不给就按 --suite 的那一套全跑")
    ap.add_argument("--out", default="", help="走查产物落点，缺省 TEMP 下 evalrun/smoke-v1")
    ap.add_argument("--python", default=WALK_PYTHON_DEFAULT,
                    help="走查件的解释器命令。主树 .venv 里没有 playwright 与 pillow，缺省用 uv 现拉一枚（走查件的全部第三方依赖就这两件，其余是标准库与 docker CLI）")
    ap.add_argument("--no-preflight", action="store_true", help="跳过环境自检（明知环境齐时用）")
    ap.add_argument("--allow-stale", action="store_true",
                        help="明知容器已带最新码时跳过新鲜度检查")
    args = ap.parse_args()
    if not args.rings:
        args.rings = V2_RINGS if args.suite == "v2" else V1_RINGS
    if not args.no_preflight:
        bad = preflight(args.base_url)
        if bad:
            for line in bad:
                print("[preflight] " + line, flush=True)
                print("[preflight] 环境不齐＝门红：先 docker compose up -d --force-recreate（起不来用 scripts/docker_up.ps1）再重跑本门。", flush=True)
            return 1
    if not args.allow_stale:
        stale = code_freshness()
        if stale:
            for line in stale:
                print("[freshness] " + line, flush=True)
            print("[freshness] 容器带旧码＝门红：按上面每一行点名的那一族换码——后端三枚重建镜像"
                  "再 up -d --force-recreate，前端要 docker compose build frontend 再 recreate"
                  "（Docker 起不来用 scripts/docker_up.ps1）；明知已对齐时用 --allow-stale", flush=True)
            return 1
        print("[freshness] 后端三枚带 app 那一路的码、前端一枚带 frontend 那一路的码，"
              "都不早于各自最新提交，端到端读数可作数", flush=True)
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "evalrun" / ("smoke-" + args.suite)
    passes = max(1, args.repeat)
    rowsets = []
    rc = 0
    for index in range(passes):
        target = out if passes == 1 else out / ("pass" + str(index + 1))
        target.mkdir(parents=True, exist_ok=True)
        label = "" if passes == 1 else "（第 " + str(index + 1) + "/" + str(passes) + " 遍）"
        started = time.time()
        walk_rc = run_walk(target, args.env_file, args.base_url, args.rings, args.python)
        one_rc, rows = report(target, started, walk_rc, label)
        rc = max(rc, one_rc)
        rowsets.append(rows)
    if passes > 1:
        rc = max(rc, aggregate(out, rowsets, passes))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
