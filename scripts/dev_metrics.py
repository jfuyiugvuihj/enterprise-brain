#!/usr/bin/env python
"""dev_metrics.py -- 2026-10-06 改章后唯一的进度尺。

它替掉三样旧汇报物：凭据纸、并树枚数、门墙钟。四个数全部现取，谁都不许手抄：
  1 新增行数按桶分（产品码 / 测试 / 文档 / 脚本 / 前端 / 其他），并判「测试＋文档 <= 3x 产品码」那道上限；
  2 返工笔占比（提交标题含 订正/返工/作废/重锚/退回/纠错）；
  3 能演示几条 / 9：现取盘上最新一枚走查账本，并判它是否早于最新一枚 app 提交（早了＝读数过期，不许当今日读数）；
  4 AGENTS.md 作业规矩枚数对当日班前基线：只许删，加了必须写明省下多少验证预算。

跑法：
    python scripts/dev_metrics.py                    # 量今天 00:00 起（本地日）
    python scripts/dev_metrics.py --range a..b       # 量指定提交区间
    python scripts/dev_metrics.py --days 7           # 量最近 N 天
    python scripts/dev_metrics.py --strict           # 破了 3 倍上限就 exit=1
它只读 git、只读盘上账本，不起服务、不动容器、不打模型。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PASS = "达"
REWORK = re.compile("订正|返工|作废|重锚|退回|纠错|收订")
BUCKETS = [("产品码", "app/"), ("测试", "tests/"), ("文档", "docs/"),
           ("脚本", "scripts/"), ("前端", "frontend/")]


def git(*args: str) -> str:
    """跑一枚 git 并交回 stdout（UTF-8，路径不转八进制）。"""
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                          cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0:
        raise SystemExit("[dev_metrics] git " + " ".join(args) + " 交回 rc="
                         + str(proc.returncode) + "：" + (proc.stderr or "").strip()[:200])
    return proc.stdout or ""


def bucket_of(path: str) -> str:
    norm = path.replace("\\", "/")
    for name, prefix in BUCKETS:
        if norm.startswith(prefix):
            return name
    return "其他"


def commits(range_args):
    """把 numstat 输出还原成 [{sha, subject, added{桶}, touches_app}]。"""
    raw = git("log", *range_args, "--numstat", "--pretty=format:\x01%h\x1f%s")
    out = []
    cur = None
    for line in raw.splitlines():
        if line.startswith("\x01"):
            sha, _, subject = line[1:].partition("\x1f")
            cur = {"sha": sha, "subject": subject,
                   "added": {name: 0 for name, _ in BUCKETS}, "touches_app": False}
            for key in ("其他",):
                cur["added"][key] = 0
            out.append(cur)
            continue
        if cur is None:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add_s, _del_s, path = parts[0], parts[1], "/".join(parts[2:])
        if not add_s.isdigit():
            continue
        name = bucket_of(path)
        cur["added"][name] += int(add_s)
        if name == "产品码":
            cur["touches_app"] = True
    return out


#: 两张面各自的全集分母：V1 九条旅程（环 1–9）、V2 十二条（环 10–21）。
FAMILIES = (("V1", lambda n: n <= 9, 9), ("V2", lambda n: n > 9, 12))


def newest_ledgers():
    """两张验收面各找一本自己的账：V1 看环 1–9，V2 看环 10 起。

    以前只取盘上最新那一枚账本，于是刚跑完 V2 就报不出 V1、刚跑完 V1 就报不出 V2——
    同一班里换一张面，另一张面的读数就凭空消失（10-07 20:0x 实测：V1 报 9/9、V2 报
    「本轮账本里没有」，而 V2 那本账 19:56 才落盘）。各找各的最新一本，缺一张就说缺。
    """
    root = Path(tempfile.gettempdir()) / "evalrun"
    found = {label: None for label, _, _ in FAMILIES}
    if not root.is_dir():
        return found
    ledgers = []
    for cand in sorted(root.rglob("ledger.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            doc = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = doc.get("rings") or []
        if not (isinstance(rows, list) and rows
                and all(isinstance(r, dict) and "ring" in r for r in rows)):
            continue
        ledgers.append((cand, datetime.fromtimestamp(cand.stat().st_mtime), rows))
    # 一枚环取它自己最新那本账里的读数：跑过 12 环之后又单跑一枚环 10，环 10 用新的、
    # 其余 11 环仍算数——以前只认最新一本账，于是单跑一环把整张面报成 1/1。
    for label, pick, total in FAMILIES:
        taken = {}
        newest = None
        for cand, when, rows in ledgers:
            for row in rows:
                try:
                    ring = int(row.get("ring") or 0)
                except (TypeError, ValueError):
                    continue
                if not pick(ring) or ring in taken:
                    continue
                taken[ring] = row
                newest = when if newest is None else max(newest, when)
        if taken:
            ordered = [taken[key] for key in sorted(taken)]
            found[label] = (len(ordered), total, ordered, newest)
    return found


def app_commit_time():
    """最新一枚碰 app/ 的提交时刻；拿不到交回 None（别把它当零，也别说它绿）。"""
    raw = git("log", "-1", "--format=%cI", "--", "app")
    stamp = raw.strip().splitlines()[0] if raw.strip() else ""
    if not stamp:
        return None
    # 走查账本的 mtime 是本地无时区，这里换成同一个基准，否则比较当场炸。
    return datetime.fromisoformat(stamp).astimezone().replace(tzinfo=None)


def rules_count(text: str) -> int:
    """AGENTS.md「开发模式」一节里的作业规矩枚数（以 '- ' 起头的条目计）。"""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## 开发模式")), None)
    if start is None:
        return 0
    n = 0
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        if ln.startswith("- "):
            n += 1
    return n


def baseline_rules():
    """基线取 HEAD 里那一版 AGENTS.md：Δ 就是「这一轮加/删了几枚作业规矩」。

    当日首笔的父本不能当基线——那天「开发模式」一节还不存在，比出来的 Δ 是天量，
    尺子就废了（10-06 实测：拿 e84b07a^ 比交回 Δ21）。
    """
    return "HEAD", rules_count(git("show", "HEAD:AGENTS.md"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--range", default="", help="提交区间，如 a..b（给了它就不看 --days/--since）")
    ap.add_argument("--days", type=int, default=0, help="最近 N 天（含当日 00:00 起）")
    ap.add_argument("--strict", action="store_true", help="破 3 倍上限时 exit=1")
    args = ap.parse_args()

    if args.range:
        rng = [args.range]
        window = "区间 " + args.range
    elif args.days > 0:
        since = datetime.fromtimestamp(datetime.now().timestamp() - args.days * 86400)
        rng = ["--since=" + since.strftime("%Y-%m-%d 00:00")]
        window = "最近 " + str(args.days) + " 天"
    else:
        window = "当日 00:00 起"
        rng = ["--since=" + datetime.now().strftime("%Y-%m-%d") + " 00:00"]

    rows = commits(rng)
    sums = {name: 0 for name, _ in BUCKETS}
    sums["其他"] = 0
    for c in rows:
        for key, val in c["added"].items():
            sums[key] += val
    product = sums["产品码"]
    meta = sums["测试"] + sums["文档"]
    ratio = (meta / product) if product else float("inf")
    rework = [c for c in rows if REWORK.search(c["subject"])]
    feature = [c for c in rows if c["touches_app"]]

    print("[dev_metrics] 口径：" + window + "，共 " + str(len(rows)) + " 笔提交", flush=True)
    print("  1 元成本  产品码 " + str(product) + " 行 / 测试 " + str(sums["测试"])
          + " / 文档 " + str(sums["文档"]) + " / 脚本 " + str(sums["脚本"])
          + " / 前端 " + str(sums["前端"]) + " / 其他 " + str(sums["其他"]), flush=True)
    cap_line = "     测试＋文档 = " + ("inf" if not product else "{:.1f}".format(ratio)) + "x 产品码（上限 3x）"
    if product == 0 and meta > 0:
        cap_line += "  [破] 这段一行产品码都没新增"
    elif ratio > 3:
        cap_line += "  [破] 超出 " + "{:.0f}".format(meta - 3 * product) + " 行，须业主裁定"
    else:
        cap_line += "  [在预算内]"
    print(cap_line, flush=True)
    pct = (100.0 * len(rework) / len(rows)) if rows else 0.0
    print("  2 返工    " + str(len(rework)) + "/" + str(len(rows)) + " 笔（"
          + "{:.0f}".format(pct) + "%）＝标题含 订正/返工/作废/重锚/退回/纠错", flush=True)
    print("  3 功能    碰 app/ 的 " + str(len(feature)) + " 笔（能演示几条见下一行，笔数不是进度）", flush=True)

    lads = newest_ledgers()
    stamp = app_commit_time()
    if all(value is None for value in lads.values()):
        print("  4 演示    盘上没有走查账本＝现无可演示读数（先跑 python scripts/smoke_v1.py --suite v1）",
              flush=True)
    for label, value in lads.items():
        if value is None:
            print("  4 演示 " + label + "  盘上没有 " + label + " 那一套的读数（跑 python scripts/smoke_v1.py --suite "
                  + label.lower() + "）", flush=True)
            continue
        covered, total, rings, newest = value
        age = ""
        if stamp and newest and newest < stamp:
            age = "  [读数过期：早于最新一枚 app 提交 " + stamp.strftime("%m-%d %H:%M") + "]"
        ok = sum(1 for r in rings if r.get("status") == PASS)
        gap = "" if covered == total else ("（这一面共 " + str(total) + " 条，另有 "
                                        + str(total - covered) + " 条盘上没读数）")
        print("  4 演示 " + label + "  " + str(ok) + "/" + str(total) + " 条能演示，读数取自 "
              + str(covered) + " 本账里各环最新的一本（最新一刻 " + (newest.strftime("%m-%d %H:%M") if newest else "?")
              + "）" + gap + age, flush=True)
        for r in rings:
            if r.get("status") != PASS:
                note = re.sub(r"\s+", " ", str(r.get("note") or ""))[:90]
                print("       未达 " + str(r.get("ring")) + " " + str(r.get("title"))
                      + " :: " + note, flush=True)

    ref, base = baseline_rules()
    now_rules = rules_count((REPO / "AGENTS.md").read_text(encoding="utf-8"))
    delta = now_rules - base
    verdict = "只许删：这轮加了的，必须写明省下多少验证预算，否则回滚" if delta > 0 else "没加长（合规）"
    if base < 0:
        verdict = "拿不到班前基线，不判"
    print("  5 规矩    现读 " + str(now_rules) + " 枚 / 班前基线 " + str(base) + "（" + ref
          + "）＝Δ" + str(delta) + "，" + verdict, flush=True)

    violated = bool(product == 0 and meta > 0) or (product > 0 and ratio > 3)
    print("[dev_metrics] 每班只贴上面这几行；passed 枚数、并树枚数、门墙钟不再算进度。", flush=True)
    return 1 if (args.strict and violated) else 0


if __name__ == "__main__":
    raise SystemExit(main())
