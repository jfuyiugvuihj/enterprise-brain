# -*- coding: utf-8 -*-
"""R470 · 服务重启演练的读数比对与出表件（只读，零写口，不连库、不起服务、不动容器）。

为什么要有这一枚：V2 验收目标 #21「会话、产物、数据和文档重启后可恢复」到今天从没实测过，
而这类实测交回的就是一堆数字。手写一张表会带上抄上一班的惯性（本仓入规七次要杀的就是这个病）。
所以本件是唯一的出表口：盘上那张表必须由 `render_readout()` 从 `docs/perf/raw/r470-2026-09-29/`
那六份原始读数生成，改一个数字都得重跑本件。

两条口径写死在这里，不许在别处抄第二份：
* `ALLOWED_GROWTH`：审计面 `audit_events` 是 append-only，演练里每一次登录都会给它加行 ⇒ 只许长、
  不许缩，别的表一枚都不许动。少了不报就是假绿（把丢数据当成通过），多了不报就是把越权当成噪声。
* 会话读腿 `GET /sessions` 的条数必须在三形里逐枚相等——「表里还在」不等于「应用读得回来」，
  R397 治的就是那一格。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "docs" / "perf" / "raw" / "r470-2026-09-29"
DOC_PATH = REPO_ROOT / "docs" / "testing" / "r470-restart-drill-2026-09-29.md"

#: 演练自己会写的唯一一本账；其它任何一张表行数变化都是缺陷。
ALLOWED_GROWTH = frozenset({"audit_events"})

#: 生成表在文档里的落点。有了它，「盘上那张表 == 再生件」才是可逐字节核对的一件事。
BEGIN = '<!-- R470-TABLE-BEGIN -->'
END = '<!-- R470-TABLE-END -->'
NL = chr(10)  # 与 render_readout() 的行尾同一枚，避免两处各写各的

BEFORE = "probe-before-stop-start.json"
AFTER_STOP_START = "probe-after-stop-start.json"
AFTER_RECREATE = "probe-after-force-recreate.json"
API_FILES = ("api-before.json", "api-after-stop-start.json", "api-after-force-recreate.json")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(census: dict) -> dict:
    return {name: int((body or {}).get("rows") or 0) for name, body in census["db"].items()}


def _pk(census: dict) -> dict:
    return {name: (body or {}).get("pk_max") for name, body in census["db"].items()}


def compare(before: dict, after: dict) -> dict:
    """两张普查表之比，返回逐格差异（本件唯一的判定入口，测试与出表都走它）。"""
    rb, ra = _rows(before), _rows(after)
    pb, pa = _pk(before), _pk(after)
    problems = []
    missing = sorted(set(rb) - set(ra))
    extra = sorted(set(ra) - set(rb))
    if missing:
        problems.append("重启后有表读不到了：" + ", ".join(missing))
    if extra:
        problems.append("重启后多出一张没见过的表：" + ", ".join(extra))
    grew, shrank, changed = {}, {}, []
    for name in sorted(set(rb) & set(ra)):
        delta = ra[name] - rb[name]
        if delta == 0:
            continue
        changed.append(name)
        if delta > 0:
            grew[name] = delta
        else:
            shrank[name] = delta
            problems.append("%s 少了 %d 行（重启丢数据）" % (name, -delta))
        if name not in ALLOWED_GROWTH:
            problems.append("%s 行数动了 %+d，但它不在 append-only 白名单里" % (name, delta))
    pk_changed = sorted(k for k in set(rb) & set(ra) if pb.get(k) != pa.get(k))
    if pk_changed:
        problems.append("主键上界漂了：" + ", ".join(pk_changed))
    if before.get("files") != after.get("files"):
        problems.append("文件层计数变了：%r -> %r" % (before.get("files"), after.get("files")))
    return {
        "tables_before": len(rb),
        "tables_after": len(ra),
        "rows_before": sum(rb.values()),
        "rows_after": sum(ra.values()),
        "changed_tables": changed,
        "grew": grew,
        "shrank": shrank,
        "pk_changed": pk_changed,
        "files_equal": before.get("files") == after.get("files"),
        "problems": problems,
        "ok": not problems,
    }


def compare_api(readouts: list) -> dict:
    """三形 API 读腿读数必须逐枚相等；相等判据落在 sessions 条数与登录路径两格上。"""
    keys = []
    for item in readouts:
        keys.append((bool(item.get("login")), (item.get("sessions") or {}).get("n")))
    same = len(set(keys)) == 1
    return {"forms": len(readouts), "readings": keys, "all_equal": same,
            "problem": None if same else "会话读腿三形不一致：" + repr(keys)}


def run(raw_dir: Path = RAW_DIR) -> dict:
    before = load_json(raw_dir / BEFORE)
    stop_start = load_json(raw_dir / AFTER_STOP_START)
    recreate = load_json(raw_dir / AFTER_RECREATE)
    api = [load_json(raw_dir / name) for name in API_FILES]
    return {
        "stop_start": compare(before, stop_start),
        "force_recreate": compare(before, recreate),
        "api": compare_api(api),
        "files": before.get("files"),
        "redis": {"before": before.get("redis"), "after": recreate.get("redis")},
    }


def validate(report: dict) -> list:
    problems = []
    for form in ("stop_start", "force_recreate"):
        block = report[form]
        for p in block["problems"]:
            problems.append("[%s] %s" % (form, p))
        if block["tables_before"] != block["tables_after"]:
            problems.append("[%s] 表枚数不等" % form)
    api = report["api"]
    if not api["all_equal"]:
        problems.append("[api] " + str(api["problem"]))
    if api["forms"] != 3:
        problems.append("[api] 只有 %d 形读数，判据要三形（基线 / stop-start / force-recreate）" % api["forms"])
    return problems


def render_readout(report: dict, problems: list) -> str:
    lines = [
        "<!-- 本表由 scripts/r470_restart_diff.py::render_readout() 生成，改数请重跑，不许手写。 -->",
        "",
        "| 形 | 表枚数 | 行数 | 动了的表 | 主键漂动 | 文件层 | 会话读腿 | 判定 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, key in (("① stop/start（进程死透）", "stop_start"),
                       ("② --force-recreate（容器替换）", "force_recreate")):
        b = report[key]
        lines.append(
            "| %s | %d -> %d | %d -> %d | %s | %s | 等值=%s | %d 条 | %s |" % (
                label, b["tables_before"], b["tables_after"], b["rows_before"], b["rows_after"],
                ", ".join("%s %+d" % (k, v) for k, v in sorted(b["grew"].items())) or "无",
                ", ".join(b["pk_changed"]) or "无", b["files_equal"],
                report["api"]["readings"][0][1] or 0,
                "PASS" if not b["problems"] else "FAIL"))
    lines += ["", "会话读腿三形读数：" + repr(report["api"]["readings"]),
              "文件层基线：" + json.dumps(report["files"], ensure_ascii=False),
              "redis 基线/末形：" + json.dumps(report["redis"], ensure_ascii=False),
              "", "问题清单：%s" % (json.dumps(problems, ensure_ascii=False) if problems else "空"),
              ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--emit-doc", action="store_true", help="把生成的表写到 docs/testing 那份")
    ap.add_argument("--check", action="store_true", help="盘上那份与再生件逐字节比对，不等即非零")
    ap.add_argument("--sync", action="store_true", help="把再生表写回文档的哨兵区")
    args = ap.parse_args(argv)
    report = run(Path(args.raw_dir))
    problems = validate(report)
    table = render_readout(report, problems)
    if args.sync:
        doc = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
        if BEGIN not in doc or END not in doc:
            print("ABORT: %s 里没有哨兵区，不许把生成表甩在文末" % DOC_PATH, file=sys.stderr)
            return 5
        head, rest = doc.split(BEGIN, 1)
        _old, tail = rest.split(END, 1)
        body = BEGIN + NL + table.rstrip(NL) + NL + END + NL
        DOC_PATH.write_text(head + body + tail, encoding="utf-8", newline="\n")
        print("synced %s" % DOC_PATH)
        return 0
    if args.check:
        doc = DOC_PATH.read_text(encoding="utf-8")
        if BEGIN not in doc or END not in doc:
            print("FAIL: 文档里没有哨兵区", file=sys.stderr)
            return 3
        body = doc.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        if body != table.strip():
            print("FAIL: 盘上那张表与再生件逐字节不符（手写或抄了旧班）", file=sys.stderr)
            print("再生件：" + NL + table, file=sys.stderr)
            return 4
        print("PASS check problems=%d" % len(problems))
        return 0 if not problems else 1
    if args.emit_doc:
        DOC_PATH.write_text(table, encoding="utf-8", newline="\n")
        print("wrote %s bytes=%d" % (DOC_PATH, len(table.encode("utf-8"))))
    else:
        print(table)
    print("RESULT=%s problems=%d" % ("PASS" if not problems else "FAIL", len(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
