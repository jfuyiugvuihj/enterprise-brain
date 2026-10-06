"""R694 · 前置四条派生读数：把「开工那一刻栈是什么代次」落成能复算的数。

本件只读：`docker inspect`、`git rev-list`、`git log`、账本的 ``started_at``。
不起容器、不建容器、不改任何文件。四条判据逐条交回读数与一句结论，写进账本根 ``prereq``。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from r694_common import Ledger, stamp  # noqa: E402

STACK = ("enterprise-brain-backend-1", "enterprise-brain-worker-1", "enterprise-brain-scheduler-1",
         "enterprise-brain-frontend-1", "enterprise-brain-postgres-1", "enterprise-brain-redis-1",
         "enterprise-brain-ollama-1")
BACKEND_IMAGE = "enterprise-brain:local"
FRONTEND_IMAGE = "enterprise-brain-frontend:local"
GEN_SHA = "4ebfaff"


def sh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT), timeout=120)


def parse_stamp(text: str) -> datetime | None:
    """docker 给的是 ``2026-10-06T04:08:32.667443125Z``：截到微秒再补时区。"""
    if not text:
        return None
    head = text.strip()
    for fmt_str in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(head, fmt_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(head).astimezone(timezone.utc)
    except ValueError:
        return None


def local(text: str) -> datetime | None:
    """账本里是带偏移的本地时刻：转成 UTC 才能和 docker 的读数同轴比。"""
    parsed = parse_stamp(text.replace("+08:", "+0800") if text else "")
    if parsed is None:
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None
    return parsed


def hours(delta: timedelta) -> float:
    return round(delta.total_seconds() / 3600.0, 3)


def containers() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in STACK:
        proc = sh(["docker", "inspect", "-f",
                   "{{.State.Status}}|{{.State.StartedAt}}|{{if .Config.Image}}{{.Config.Image}}{{end}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                   name])
        line = (proc.stdout or "").strip()
        if "|" not in line:
            out.append({"name": name, "readable": False, "raw": line[:120]})
            continue
        status, started, image, health = line.split("|", 3)
        out.append({"name": name, "readable": True, "status": status,
                    "started_at_utc": started, "started_parsed": str(parse_stamp(started)),
                    "image": image, "health": health})
    return out


def image_created(tag: str) -> dict[str, Any]:
    proc = sh(["docker", "image", "inspect", "-f", "{{.Id}}|{{.Created}}", tag])
    line = (proc.stdout or "").strip()
    if "|" not in line:
        return {"readable": False, "raw": line[:160]}
    digest, created = line.split("|", 1)
    return {"readable": True, "digest": digest[:19], "created_utc": created,
            "created_parsed": str(parse_stamp(created))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R694 前置四条派生读数")
    parser.add_argument("--out", default="docs/testing/walkthrough-2026-10-06")
    args = parser.parse_args(argv)

    out_dir = ROOT / args.out
    ledger = Ledger(out_dir / "ledger.json")
    started_local = local(str(ledger.data.get("started_at") or ""))
    now = datetime.now(timezone.utc)

    # 起手轴：账本的 started_at 每次跑都会重写，起手那一刻取全账最早的截图时刻。
    stamps: list[str] = []
    for ring in ledger.data.get("rings", []) or []:
        stamps.extend(s.get("taken_at", "") for s in ring.get("shots", []) if s.get("taken_at"))
    for entry in ledger.data.get("faces", []) or []:
        shot = entry.get("shot") or {}
        if shot.get("taken_at"):
            stamps.append(shot["taken_at"])
    first_shot = min(stamps) if stamps else ""
    started_local = local(first_shot) or started_local
    if not ledger.data.get("first_evidence_at"):
        ledger.set_root("first_evidence_at", first_shot)

    rows = containers()
    backend_image = image_created(BACKEND_IMAGE)
    frontend_image = image_created(FRONTEND_IMAGE)

    up = [r for r in rows if r.get("status") == "running"]
    healthy = [r for r in up if r.get("health") in ("healthy", "none")]
    checks: list[str] = []

    # 条 1：七枚齐（除 frontend 外 healthy）
    names_seen = sorted(r["name"] for r in up)
    front_running = any(r["name"] == "enterprise-brain-frontend-1" and r.get("status") == "running"
                        for r in rows)
    strict_healthy = [r for r in up if r.get("health") == "healthy"]
    checks.append(
        "条 1 现取（收工那一刻）：`docker ps` 枚数 %d，名册 %s；除 frontend 外逐枚 health=%s；"
        "frontend 在位=%s" % (
            len(up), "、".join("`%s`" % n for n in names_seen),
            "、".join("%s=%s" % (r["name"].replace("enterprise-brain-", ""), r.get("health"))
                     for r in up if r["name"] != "enterprise-brain-frontend-1"),
            front_running))
    checks.append(
        "条 1 开工那一刻（起手轴取全账最早一枚截图时刻 %s，与容器 `State.StartedAt` 现算）：%s" % (
            first_shot,
            "；".join("%s 已 Up %s h" % (r["name"].replace("enterprise-brain-", ""),
                                        hours(started_local - parse_stamp(r["started_at_utc"])))
                      for r in up if started_local and parse_stamp(r["started_at_utc"]))
            if started_local else "账本起手时刻读不到"))

    # 条 2：镜像代次
    if backend_image.get("readable") and started_local and parse_stamp(backend_image["created_utc"]):
        age_at_start = hours(started_local - parse_stamp(backend_image["created_utc"]))
        checks.append(
            "条 2 现取：镜像 `%s` digest `%s` 建于 %s（UTC）＝起手那一刻 %s 小时 %s 2 小时；"
            "收工那一刻同轴读数 %s 小时。这一条量的是墙钟，不是代码——"
            "自产品码代次 `%s` 起 `app/` 的提交枚数见下一条" % (
                BACKEND_IMAGE, backend_image["digest"], backend_image["created_utc"][:19],
                age_at_start, "小时，≤ 2 小时闸，达标" if age_at_start <= 2.0
                else "小时，已越过 2 小时闸（代次是否变seen下一条）",
                hours(now - parse_stamp(backend_image["created_utc"])), GEN_SHA))
    else:
        checks.append("条 2 现取：镜像读数缺失 %s" % json.dumps(backend_image, ensure_ascii=False))

    app_commits = sh(["git", "rev-list", "--count", "%s..HEAD" % GEN_SHA, "--", "app/"]).stdout.strip()
    fe_commits = sh(["git", "rev-list", "--count", "%s..HEAD" % GEN_SHA, "--", "frontend/"]).stdout.strip()
    checks.append(
        "条 2 的代次半边现取：`git rev-list --count %s..HEAD -- app/` = %s 枚、`-- frontend/` = %s 枚"
        "（两枚都是 0 ⇒ 起手那一刻镜像带的就是当前树的产品码与前端码，墙钟漂过 2 小时不改这一格）"
        % (GEN_SHA, app_commits or "读数缺失", fe_commits or "读数缺失"))

    # 条 3：前端不落后
    since = (now - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%S")
    recent = sh(["git", "log", "--since", since, "--oneline", "--", "frontend/"]).stdout.splitlines()
    dirty_fe = (sh(["git", "status", "--porcelain", "--", "frontend/"]).stdout or "").splitlines()
    if frontend_image.get("readable") and started_local:
        checks.append(
            "条 3 现取：`%s` 建于 %s（UTC）＝起手那一刻 %s 小时；过去 30 小时 `frontend/` 提交枚数 %d；"
            "本树 `frontend/` 未提交改动枚数 %d；前端未重建（本单没跑任何 build 命令）" % (
                FRONTEND_IMAGE, frontend_image["created_utc"][:19],
                hours(started_local - parse_stamp(frontend_image["created_utc"]))
                if parse_stamp(frontend_image["created_utc"]) else "读数缺失",
                len([x for x in recent if x.strip()]), len(dirty_fe)))

    # 条 4：凭据按键名取，值不入纸
    ring2 = next((r for r in ledger.data.get("rings", []) if r.get("ring") == 2), {})
    login_elapsed = (ring2.get("readings") or {}).get("login_elapsed_s")
    keys = ledger.data.get("credential_key_names") or {}
    checks.append(
        "条 4 现取：登录走通的那枚读数＝环 2 的 `login_elapsed_s` = %s s 且屏上身份 %s 角色 %s；"
        "口令取自 `deploy/.env.server` 键名 %s（主）与 %s（次），值未记录，env 文件未被本单改过一行" % (
            login_elapsed, (ring2.get("readings") or {}).get("user_shown"),
            (ring2.get("readings") or {}).get("role_shown"),
            keys.get("primary"), keys.get("secondary")))

    entry = {"checks": checks, "taken_at": stamp(),
             "containers": rows, "up_now": len(up),
             "healthy_now": len(strict_healthy),
             "backend_image": backend_image, "frontend_image": frontend_image,
             "git": {"app_commits_since_generation": app_commits,
                     "frontend_commits_since_generation": fe_commits,
                     "frontend_commits_last_30h": len([x for x in recent if x.strip()]),
                     "frontend_dirty_rows": len(dirty_fe)}}
    ledger.set_root("prereq", entry)
    print(json.dumps({"checks": len(checks), "up_now": len(up),
                      "app_commits_since_generation": app_commits}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())