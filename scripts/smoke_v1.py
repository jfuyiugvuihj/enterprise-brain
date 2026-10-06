"""smoke_v1.py -- V1 的唯一验收门：九条用户旅程的端到端冒烟（2026-10-06 改章）。

跑法（这台机上主树 .venv 没有 playwright，所以走查件的解释器要能换）：

    python scripts/smoke_v1.py --env-file deploy/.env.server ^
        --python "uv run --no-project --with playwright==1.63.0 python"

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

REPO = Path(__file__).resolve().parents[1]
WALK = REPO / "scripts" / "r694_walkthrough.py"
PASS = "达"


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


def run_walk(out, env_file, base_url, rings, python_opt):
    argv = (shlex.split(python_opt) if python_opt else [sys.executable]) + [str(WALK)]
    cmd = argv + ["--env-file", env_file, "--base-url", base_url, "--rings", rings, "--out", str(out)]
    print("[smoke_v1] $ " + " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


def report(out, started, walk_rc):
    led = out / "ledger.json"
    if not led.exists():
        print("[smoke_v1] 走查件没交回账本（walk_rc=" + str(walk_rc) + "）：" + str(led) + " 不在盘上", flush=True)
        return 1
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
    print("[smoke_v1] " + str(len(rows) - len(bad)) + "/" + str(len(rows)) + " 条能演示；墙钟 "
          + str(round(time.time() - started, 1)) + " s；账本 " + str(led), flush=True)
    if walk_rc != 0:
        print("[smoke_v1] 走查件退出码 " + str(walk_rc) + "（环境/登录/容器问题同样算门红，不许推给非产品原因）", flush=True)
    return 1 if (bad or walk_rc != 0 or not rows) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env-file", default=str(REPO / "deploy" / ".env.server"))
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--rings", default="1,2,3,4,5,6,7,8,9")
    ap.add_argument("--out", default="", help="走查产物落点，缺省 TEMP 下 evalrun/smoke-v1")
    ap.add_argument("--python", default="", help="走查件的解释器命令，例：uv run --no-project --with playwright==1.63.0 python")
    ap.add_argument("--no-preflight", action="store_true", help="跳过环境自检（明知环境齐时用）")
    args = ap.parse_args()
    if not args.no_preflight:
        bad = preflight(args.base_url)
        if bad:
            for line in bad:
                print("[preflight] " + line, flush=True)
                print("[preflight] 环境不齐＝门红：先 docker compose up -d --force-recreate（起不来用 scripts/docker_up.ps1）再重跑本门。", flush=True)
            return 1
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "evalrun" / "smoke-v1"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    walk_rc = run_walk(out, args.env_file, args.base_url, args.rings, args.python)
    return report(out, started, walk_rc)


if __name__ == "__main__":
    raise SystemExit(main())
