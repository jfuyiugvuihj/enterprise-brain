"""R632 · 契约家族 A 那一格的读数件：`wall_ms` × 服务端生效档 join 之后出分位。

契约（docs/api/contract-v1.md 家族 A）把这一格交给一枚在册读数件，名字写作
`scripts/eval_slo_lane_readout.py`。本席 10-04 现取：该件在**任何 ref 里都不存在**
（`git log --all -- scripts/eval_slo_lane_readout.py` 空输出），树里只有另一件事的尺
`scripts/eval_lane_readout.py`（R443 落的队列道 D 三格，全文一个字节都不读档位名）。
所以这一格不是「改过名而契约没跟」，是**件从来没落** ⇒ 按契约那一格的口径把它补出来。
契约文本本件作者一个字不动，交回总控裁定并树。

三条口径，一条都不许松（照抄 R259 / R443 / R592 的纪律）：

① **档位名只认服务端说了什么**，不认评测夹具的 `tier` 列 —— 那一列是**声明档**，
   多轮改写会把声明与生效分开（契约原话）。读数两条来源，逐行点名落在哪一条：
   `header` = 采集器第三份件里从 `/ask` 响应头抄回来的 `x-effective-lane`
   （app/api/v1/chat.py 的 `_lane_readout_headers`；量具那半张由 R632 补，默认关）；
   `r42_log` = 后端 `[R42]` 日志行经 app/common/stage_timing.py::parse_r42_log_line 读回，
   join 键是那行自己抄的题面前缀（nodes.py::classify_route 抄 text[:30]）。
   前缀不唯一、同一题读出两枚档位名、题面被改写对不上 —— 三种一律判**取不到**，不挑一枚。
   两条都读不到就是读不到：明写题号，不折算成零枚，不拿声明档冒充生效档。
② **分位只许出自产品那一把尺**：app/common/performance.py::PerformanceStats
   （nearest rank：取 ceil(n * q) 那一枚，1-based）。本件不写第二套排名、不手算；
   空表不调那把尺 —— 它回 0，而一枚 0 是最会骗人的假 p95（observability 自己就这么判的）。
③ **阈值与档位名现场派生，一个都不手抄**：样本下限现读 app/api/v1/observability.py 的
   `MIN_SLO_SAMPLES`，三枚档位名现读 app/agents/nodes.py 的 LANE_QA / LANE_ANALYSIS /
   LANE_REPORT（AST 取字面，不 import：import 那一枚要十秒且真去戳 127.0.0.1:5432）。
   派生不到就是取不到，本件当场 rc=2，绝不退回落成手抄的 qa/analysis/report 或 100。

口径标签：本件交回的读数行挂 `caliber=local-full`（时延与分位必须本机，R453 裁定（b）），
收窗照 `python scripts/eval_cloud_window_readout.py --readouts <件>` 复验退出码。

用法（零服务 / 零模型 / 零容器 / 零连库，全程只读盘上件）：

    python scripts/eval_slo_lane_readout.py --window run10
    python scripts/eval_slo_lane_readout.py --window run21b --dir D:\\somewhere
    python scripts/eval_slo_lane_readout.py --window run10 --r42-log backend-run10.log
    python scripts/eval_slo_lane_readout.py --window run10 --emit-readouts readouts-run10.jsonl
"""
from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import io
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文与箭头会当场炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 本件要从产品那两枚真源读字面量与那把尺；按仓内惯例脚本可以从根目录 import app.**，
#: 但直接 `python scripts/xxx.py` 起时 sys.path[0] 是 scripts/，app 就找不着 ⇒ 自己补根目录。
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
NODES_PATH = os.path.join(REPO_ROOT, "app", "agents", "nodes.py")
OBSERVABILITY_PATH = os.path.join(REPO_ROOT, "app", "api", "v1", "observability.py")
DEFAULT_FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "business_evaluation_100.jsonl")

#: 与 scripts/eval_cloud_window_readout.py 那本格表同源的两个格名（A1 时延分位）。
#: 这里是对账用的字面，同源关系由 tests/test_r632_slo_lane_readout.py 现读卡表钉死。
CALIBER_LOCAL = "local-full"
CELL_P50 = "p50_wall_ms"
CELL_P95 = "p95_wall_ms"

#: 档位名的读回来源。`none` 不是「读到了空档」，是「这一行说不出自己是什么档」。
ORIGIN_HEADER = "header"
ORIGIN_LOG = "r42_log"
ORIGIN_NONE = "none"

R42_MARKER = "[R42]"

#: 抬头里要点名的四枚开窗开关（契约家族 A 的证据行写了这四枚）。
HEAD_ENV_KEYS = ("MODEL_MAX_CONCURRENCY", "VECTOR_DUAL_WRITE", "REPORT_LANE_VIA_QUEUE",
                 "INDEX_BACKEND")


class CaliberError(RuntimeError):
    """派生不到就是取不到。这枚异常存在的意义：不许本件退落成手抄数。"""


def module_literals(path, names):
    """从模块级赋值里现读那几枚字面量。读不到就抛，不静默给默认值。"""
    if not os.path.exists(path):
        raise CaliberError("派生用的源件不在：" + path)
    tree = ast.parse(io.open(path, encoding="utf-8").read(), filename=path)
    wanted = set(names)
    table = {}
    for node in tree.body:
        target, value = None, None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        if target in wanted and value is not None:
            try:
                table[target] = ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError):
                raise CaliberError("%s 里 %s 不是枚字面量 ⇒ 派生失败" % (path, target))
    missing = sorted(wanted - set(table))
    if missing:
        raise CaliberError("%s 里读不到 %s ⇒ 派生失败（改名或挪窝了，先复验口径再谈落数）"
                           % (path, "、".join(missing)))
    return table


def derive_lane_names(path=NODES_PATH):
    """档位名从产品那三枚常量现读；本件不写死 qa / analysis / report。

    🔴 路径做成入参不是为了让读数可变，是为了让**反证能进刀**：临时根上把 LANE_QA 改一枚字面，
    本件必须当场读不到或判成闭集不成 —— 那才是「派生」而非「抄」。真树调用一律走缺省路径。
    """
    table = module_literals(path, ("LANE_QA", "LANE_ANALYSIS", "LANE_REPORT"))
    names = (table["LANE_QA"], table["LANE_ANALYSIS"], table["LANE_REPORT"])
    if len(set(names)) != 3 or not all(isinstance(name, str) and name for name in names):
        raise CaliberError("nodes.py 的三枚档位名不成闭集：" + repr(names))
    return names


def derive_min_samples(path=OBSERVABILITY_PATH):
    """样本下限从 observability 现读（契约那一格判据写的是枚名，不是数）。"""
    value = module_literals(path, ("MIN_SLO_SAMPLES",))["MIN_SLO_SAMPLES"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CaliberError("MIN_SLO_SAMPLES 不是一枚正整数：" + repr(value))
    return value


# ==================== 件 ====================

def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def latest_by(rows, key):
    """按 key 收敛到 attempt 最大那一行（与同僚件 eval_lane_readout.py 同口径）。

    🔴 撞 key 且 attempt 也相同 ⇒ 交回后写的那一枚，但调用者必须看见这件事：
    `count_by` 把每一枚 key 的行数一起交回来，本件用它点「会话键撞行」名册，不静默挑一枚。
    """
    table = {}
    counts = collections.Counter()
    for row in rows:
        name = str(row.get(key, ""))
        if not name:
            continue
        counts[name] += 1
        previous = table.get(name)
        if previous is not None and int(row.get("attempt") or 0) < int(previous.get("attempt") or 0):
            continue
        table[name] = row
    return table, counts


def numeric(value):
    """wall_ms 只认 int / float（bool 不算数）。不是数就交 None ⇒ 进「取不到」名册。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def percentile_pair(values):
    """② 唯一的分位出处：产品那一把尺。空表不叫尺，交 None 而不是它那个会骗人的 0。"""
    if not values:
        return None
    from app.common.performance import PerformanceStats

    stats = PerformanceStats()
    for value in values:
        stats.observe(value)
    report = stats.report()
    return {"n": int(report["count"]), "p50_ms": float(report["p50_ms"]),
            "p95_ms": float(report["p95_ms"]), "max_ms": float(report["max_ms"]),
            "min_ms": float(min(values))}


def artifact_candidates(window, dirn, kind):
    """一扇窗的件有两种在册命名：驱动写 `{window}-sidecar.jsonl`，同僚件写 `sidecar-{window}.jsonl`。

    🔴 两种都试、抬头点名真用了哪一条；本件不猜第三种命名，也不静默造路径。
    """
    patterns = {"sidecar": ("sidecar-%s.jsonl", "%s-sidecar.jsonl"),
                "frames": ("sidecar-%s-frames.jsonl", "%s-sidecar-frames.jsonl"),
                "lane": ("sidecar-%s-lane.jsonl", "%s-sidecar-lane.jsonl")}.get(kind)
    if patterns is None:
        raise CaliberError("不认的件类别：" + str(kind))
    return [os.path.join(dirn, pattern % window) for pattern in patterns]


def resolve_path(explicit, window, dirn, kind):
    """交回 (真存在的那一枚路径 or 空串, 试过的候选清单)。"""
    if explicit:
        return (explicit if os.path.exists(explicit) else ""), [explicit]
    candidates = artifact_candidates(window, dirn, kind)
    for path in candidates:
        if os.path.exists(path):
            return path, candidates
    return "", candidates


# ==================== 第二读回源：后端 [R42] 日志 ====================

def read_log_text(path):
    """日志一律先探 BOM 再解码（跟进单 §62 的教训：PowerShell `>` 交的是 UTF-16 LE）。

    按 utf-8 硬读 UTF-16 会得到「零枚 [R42]」的全零假阴性 —— 那种读法在 run5 那窗真发生过。
    """
    raw = open(path, "rb").read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8", "replace")


def r42_log_lanes(log_path, fixture_by_id):
    """从日志里把每题的生效档名读回来（① 的第二条腿），并逐格交代判不了的题。

    档位名一律走产品那把尺（parse_r42_log_line），本件只自己取 join 键（那行抄的题面前缀）。
    """
    from app.common.stage_timing import R42_LOG_PATTERN, parse_r42_log_line

    lines = read_log_text(log_path).splitlines()
    prefix_to_ids = {}
    for row_id, question in fixture_by_id.items():
        prefix_to_ids.setdefault(str(question)[:30], []).append(row_id)

    lanes = {}
    conflicts = set()
    ambiguous = set()
    r42_lines = 0
    for line in lines:
        if R42_MARKER not in line:
            continue
        parsed = parse_r42_log_line(line)
        match = R42_LOG_PATTERN.search(line)
        if not parsed.lane or not match:
            continue
        r42_lines += 1
        prefix = str(match.group("question"))[:30]
        ids = prefix_to_ids.get(prefix) or []
        if len(ids) != 1:
            ambiguous.add(prefix or "（空前缀）")
            continue
        row_id = ids[0]
        if row_id in lanes and lanes[row_id] != parsed.lane:
            conflicts.add(row_id)
            lanes.pop(row_id, None)  # 同一题读出两枚档位名 ⇒ 这一题取不到，不挑一枚
            continue
        lanes.setdefault(row_id, parsed.lane)
    return {"lanes": {row_id: lane for row_id, lane in lanes.items() if row_id not in conflicts},
            "conflicts": sorted(conflicts), "ambiguous_prefixes": sorted(ambiguous),
            "r42_lines": r42_lines, "log_lines": len(lines)}


# ==================== join（①）====================

def build_lane_table(sidecar_rows, frames_rows, lane_rows, log_readout, lane_names):
    """逐题交回档位名读数。每条读数都带来源，`none` 那一格永远不冒充「读到了空档」。

    join 三跳全是精确键，不靠顺序也不靠题面：侧车 `id` →（帧账 `id`→`session_id`）→ 档位件
    `session_id`。题面那条腿只有 `[R42]` 日志用得到，而且它只在响应头那一条读不回来时才补。
    """
    by_id, sidecar_counts = latest_by(sidecar_rows, "id")
    frames_by_id, _frames_counts = latest_by(frames_rows, "id")
    lane_by_session, lane_counts = latest_by(lane_rows, "session_id")

    readings = {}
    for row_id in sorted(by_id):
        record = {"wall_ms": numeric(by_id[row_id].get("wall_ms")),
                  "kind": str(by_id[row_id].get("kind") or ""),
                  "sentinel": bool(by_id[row_id].get("sentinel")),
                  "sidecar_rows": sidecar_counts.get(row_id, 0),
                  "session_id": str((frames_by_id.get(row_id) or {}).get("session_id") or ""),
                  "lane": None, "origin": ORIGIN_NONE,
                  "sent_lane": None, "server_declared_lane": None, "lane_source": None,
                  "headers_readable": None, "note": ""}
        ledger_row = None
        if record["session_id"]:
            if lane_counts.get(record["session_id"], 0) > 1:
                record["note"] = ("档位件里这一枚会话键撞了 %d 行 ⇒ 不挑一枚"
                                  % lane_counts[record["session_id"]])
            else:
                ledger_row = lane_by_session.get(record["session_id"])
        elif lane_rows:
            record["note"] = "帧账里读不到 session_id ⇒ 档位件 join 不上"
        if ledger_row is not None:
            record["sent_lane"] = ledger_row.get("sent_lane")
            record["server_declared_lane"] = ledger_row.get("server_declared_lane")
            record["lane_source"] = ledger_row.get("lane_source")
            record["headers_readable"] = bool(ledger_row.get("headers_readable"))
            effective = ledger_row.get("effective_lane")
            if isinstance(effective, str) and effective.strip():
                record["lane"] = effective.strip()
                record["origin"] = ORIGIN_HEADER
            elif not record["note"]:
                record["note"] = ("响应头读不到档位名（headers_readable=%s）⇒ 这一题取不到"
                                  % record["headers_readable"])
        if record["lane"] is None and log_readout:
            from_log = log_readout["lanes"].get(row_id)
            if from_log:
                record["lane"] = from_log
                record["origin"] = ORIGIN_LOG
                record["note"] = ""
        if record["lane"] is not None and record["lane"] not in lane_names:
            record["note"] = ((record["note"] + " ｜") if record["note"] else "") + \
                ("读回的档位名 %r 不在派生闭集里 ⇒ 本件不认它" % record["lane"])
            record["lane"] = None
            record["origin"] = ORIGIN_NONE
        readings[row_id] = record
    return readings


# ==================== 出数 ====================

def print_ledger(readings, args, artifacts, log_readout, lane_names, min_samples, log_note=None):
    print("## 家族 A 逐档端到端分位（window=%s，caliber=%s）" % (args.window, CALIBER_LOCAL))
    print("- 件（路径 + sha256）：")
    for item in artifacts:
        if item["path"]:
            print("  - %s ｜ %s ｜ 行数=%s ｜ sha256=%s" % (
                item["kind"], item["path"], item["rows"], item["sha256"]))
        else:
            print("  - %s ｜ 🔴 取不到（试过的路径见下）" % item["kind"])
            for candidate in item["candidates"]:
                print("      · candidate=%s 存在=False" % candidate)
    print("- 派生：档位名=%s（出自 %s）｜ 样本下限=%d（出自 %s 的 MIN_SLO_SAMPLES）" % (
        "/".join(lane_names), os.path.relpath(NODES_PATH, REPO_ROOT), min_samples,
        os.path.relpath(OBSERVABILITY_PATH, REPO_ROOT)))
    print("- 档位名读回源：响应头件=%d 行 ｜ [R42] 日志=%s" % (
        sum(1 for row in readings.values() if row["origin"] == ORIGIN_HEADER),
        log_note or ("%d 枚 [R42] 行 / 日志共 %d 行" % (log_readout["r42_lines"],
                                                       log_readout["log_lines"]))))
    print("- 抬头四枚开关在**本件进程**的读数（🔴 只证宿主盘面，不证容器；容器侧另取）：%s" % (
        " ".join("%s=%s" % (key, os.environ.get(key) or "未设") for key in HEAD_ENV_KEYS)))
    print()

    origins = collections.Counter(row["origin"] for row in readings.values())
    sources = collections.Counter(str(row["lane_source"]) for row in readings.values()
                                  if row["lane_source"])
    print("### 读回账")
    print("- 侧车题数=%d ｜ 档位名读回=%d（逐源 %s）｜ 取不到=%d" % (
        len(readings), sum(count for origin, count in origins.items() if origin != ORIGIN_NONE),
        dict((origin, count) for origin, count in sorted(origins.items())
             if origin != ORIGIN_NONE) or "无",
        origins.get(ORIGIN_NONE, 0)))
    print("- lane_source 直方图=%s" % (dict(sources) or "（一条都没读回）"))
    unmeasured = sorted(row_id for row_id, row in readings.items() if row["lane"] is None)
    print("- 取不到档位名的题号=%s" % (", ".join(unmeasured) or "无"))
    for row_id in unmeasured:
        if readings[row_id]["note"]:
            print("  - %s：%s" % (row_id, readings[row_id]["note"]))
    if log_readout:
        if log_readout["conflicts"]:
            print("- 🔴 [R42] 日志里同一题读出两枚档位名（判取不到）：%s"
                  % ", ".join(log_readout["conflicts"]))
        if log_readout["ambiguous_prefixes"]:
            print("- 🔴 [R42] 日志的题面前缀不唯一或对不上夹具（判取不到）：%s"
                  % ", ".join(log_readout["ambiguous_prefixes"]))
    print()


def per_lane_cells(readings, lane_names, min_samples):
    """逐生效档出一格：n / 分位 / 够不够 / kind 直方图 / 哨兵枚数 / 掉出去的题号。"""
    cells = {}
    for lane in lane_names:
        members = [row for row in readings.values() if row["lane"] == lane]
        values = [row["wall_ms"] for row in members if row["wall_ms"] is not None]
        dropped = sorted(row_id for row_id, row in readings.items()
                         if row["lane"] == lane and row["wall_ms"] is None)
        pair = percentile_pair(values)
        cells[lane] = {"lane": lane, "pair": pair,
                       "enough": bool(pair) and pair["n"] >= min_samples,
                       "kinds": dict(collections.Counter(row["kind"] for row in members)),
                       "sentinels": sum(1 for row in members if row["sentinel"]),
                       "dropped_wall_ms": dropped}
    return cells


def print_table(cells, lane_names, min_samples):
    print("### 逐生效档分位（分位只出自 app/common/performance.py::PerformanceStats，nearest rank）")
    print("| 生效档 | n | 下限 | 够不够 | p50_ms | p95_ms | max_ms | 哨兵枚数 | kind 直方图 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for lane in lane_names:
        cell = cells[lane]
        pair = cell["pair"]
        print("| %s | %s | %d | %s | %s | %s | %s | %d | %s |" % (
            lane, pair["n"] if pair else 0, min_samples,
            "够" if cell["enough"] else "🔴 样本不足（照实报 n，不拿分位当结论）",
            pair["p50_ms"] if pair else "-", pair["p95_ms"] if pair else "-",
            pair["max_ms"] if pair else "-", cell["sentinels"], cell["kinds"] or "无"))
        if cell["dropped_wall_ms"]:
            print("  · %s 档里 wall_ms 读不到的题号=%s" % (lane, ", ".join(cell["dropped_wall_ms"])))
    print()


def print_divergence(readings):
    """契约那句「声明档与生效档会被多轮改写分开」在这一窗的读数 —— 两件事分开数。"""
    diverged = sorted(row_id for row_id, row in readings.items()
                      if row["lane"] and row["sent_lane"] and row["sent_lane"] != row["lane"])
    print("### 声明档 vs 生效档")
    print("- 量具发出去的 lane 与服务端读回的档位名不一致的题数=%d 题号=%s" % (
        len(diverged), ", ".join(diverged) or "无"))
    for row_id in diverged:
        row = readings[row_id]
        print("  - %s：sent=%s effective=%s server_declared=%s source=%s" % (
            row_id, row["sent_lane"], row["lane"], row["server_declared_lane"], row["lane_source"]))
    print("- 一题 lane 都没发的题数=%d（这格说的是量具发没发，不替服务端判档）" % sum(
        1 for row in readings.values() if not row["sent_lane"]))
    print("- 响应头不可读的题数=%d（假出口/旧件才有这一格；它不等于「服务端说没档位」）" % sum(
        1 for row in readings.values() if row["headers_readable"] is False))
    return diverged


def emit_readouts(path, cells, lane_names, artifacts, min_samples):
    """一行 = 一段（一档），交回 eval_cloud_window_readout.py --readouts 校验口径。"""
    lines = []
    for lane in lane_names:
        cell = cells[lane]
        pair = cell["pair"]
        if pair is None:
            continue
        lines.append({"segment": lane, "caliber": CALIBER_LOCAL,
                      "cells": {CELL_P50: pair["p50_ms"], CELL_P95: pair["p95_ms"]},
                      "n": pair["n"], "sample_floor": min_samples,
                      "note": "够" if cell["enough"] else "样本不足（照实报 n）",
                      "source": [item["path"] for item in artifacts if item["path"]],
                      "attempt": 1})
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for line in lines:
            print(json.dumps(line, ensure_ascii=False), file=handle)
    return len(lines)


# ==================== main ====================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", default="run10", help="窗名（契约点名的下一扇缺省 run10）")
    ap.add_argument("--dir", default="",
                    help="件所在目录，缺省 %%TEMP%%\\evalrun（与同僚件 eval_lane_readout.py 同一路径纪律）")
    ap.add_argument("--sidecar", default="", help="侧车件路径；给了就不再按窗名猜")
    ap.add_argument("--frames", default="", help="帧证件路径（session_id 的出处）")
    ap.add_argument("--lane-ledger", default="", help="R632 档位名读数件路径")
    ap.add_argument("--r42-log", default="", help="后端日志件（第二读回源，按题面前缀 join）")
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE,
                    help="题面名册，只给 [R42] 日志那条腿当 join 键用，绝不当档位用")
    ap.add_argument("--surface", choices=("e2e", "stage"), default="e2e",
                   help="e2e＝家族 A 三格；stage＝家族 E 分段格（那条道的窗内驱动还没落，本件会明写取不到）")
    ap.add_argument("--emit-readouts", default="",
                    help="把逐档读数写成 JSONL（caliber=local-full），交 eval_cloud_window_readout.py 复验")
    args = ap.parse_args(argv)

    if args.surface == "stage":
        print("🔴 家族 E 那一格本件交不出数：窗内驱动还没把逐 trace 的 /stage-latency 读数落成件。")
        print("   契约行 E 的前置① 与 observability 里那三行 prerequisite 今天都还挂着；")
        print("   本件不许拿端到端那三格冒充分段格，也不手算 —— 跑不起来就是「取不到」。")
        return 2

    try:
        lane_names = derive_lane_names()
        min_samples = derive_min_samples()
    except CaliberError as exc:
        print("🔴 派生失败：%s —— 明写取不到，不退回手抄数" % exc)
        return 2
    except Exception as exc:  # AST/编码/权限任何一手读不到都算取不到，不编数
        print("🔴 派生失败：%s：%s —— 明写取不到，不退回手抄数" % (type(exc).__name__, exc))
        return 2

    base = args.dir or os.path.join(os.environ.get("TEMP", "/tmp"), "evalrun")
    resolved = {kind: resolve_path(explicit, args.window, base, kind)
                for kind, explicit in (("sidecar", args.sidecar), ("frames", args.frames),
                                       ("lane", args.lane_ledger))}

    artifacts, missing = [], []
    for kind in ("sidecar", "frames", "lane"):
        path, candidates = resolved[kind]
        if not path:
            missing.append(kind)
        artifacts.append({"kind": kind, "path": path, "candidates": candidates})
    if missing:
        for item in artifacts:
            if not item["path"]:
                print("🔴 取不到件：kind=%s —— 明写取不到，不编数" % item["kind"])
                for candidate in item["candidates"]:
                    print("   · 试过的路径：%s" % candidate)
        print("   档位名读数件由量具的记账腿落：开窗设 EVAL_RECORD_LANE_READOUT=on 才有，"
              "没设的窗一件都不落 ⇒ 这一格本就该读作取不到（这正是「0/105」那一格）。")
        return 2

    sidecar_rows = load_jsonl(resolved["sidecar"][0])
    frames_rows = load_jsonl(resolved["frames"][0])
    lane_rows = load_jsonl(resolved["lane"][0])
    counts = {"sidecar": len(sidecar_rows), "frames": len(frames_rows), "lane": len(lane_rows)}
    for item in artifacts:
        item["rows"] = counts[item["kind"]]
        item["sha256"] = sha256_of(item["path"])

    log_readout = None
    #: 三态分开交代：没给／给了但件不在／给了但零枚。最后一格不许被写成「没给」——
    #: 那等于把「压根没打算读日志」和「日志里真的没有判别行」混成同一句话。
    log_note = "未指定（--r42-log 没给）"
    if args.r42_log:
        if not os.path.exists(args.r42_log):
            log_note = "🔴 件不在（--r42-log=%s）⇒ 这条腿不用（响应头那条腿不受影响）" % args.r42_log
            print("🔴 取不到件：--r42-log=%s ⇒ 这一条腿本窗不用（不影响响应头那条腿）" % args.r42_log)
        else:
            try:
                fixture_by_id = {str(row.get("id")): str(row.get("question") or "")
                                 for row in load_jsonl(args.fixture) if row.get("id")}
                log_readout = r42_log_lanes(args.r42_log, fixture_by_id)
            except CaliberError as exc:
                print("🔴 [R42] 日志这一条腿取不到：%s" % exc)
                log_note = "🔴 取不到：%s" % exc
            except Exception as exc:
                print("🔴 [R42] 日志这一条腿取不到：%s：%s" % (type(exc).__name__, exc))
                log_note = "🔴 取不到：%s：%s" % (type(exc).__name__, exc)
            else:
                if log_readout["r42_lines"] == 0:
                    print("🔴 日志里零枚 [R42] —— 判硬失败（编码猜错或件不对），不当成「今天没判别」")
                    log_note = ("🔴 指定了但零枚 [R42]（日志共 %d 行）⇒ 这条腿作废，"
                                "判硬失败，不写成「没给」" % log_readout["log_lines"])
                    log_readout = None

    readings = build_lane_table(sidecar_rows, frames_rows, lane_rows, log_readout, lane_names)
    print_ledger(readings, args, artifacts, log_readout, lane_names, min_samples, log_note)
    cells = per_lane_cells(readings, lane_names, min_samples)
    print_table(cells, lane_names, min_samples)
    print_divergence(readings)

    if args.emit_readouts:
        written = emit_readouts(args.emit_readouts, cells, lane_names, artifacts, min_samples)
        print("- 读数件已写：%s（%d 行）｜ 复验命令：python scripts/eval_cloud_window_readout.py "
              "--readouts %s" % (args.emit_readouts, written, args.emit_readouts))

    measured = [lane for lane in lane_names if cells[lane]["pair"] is not None]
    if not measured:
        print("🔴 三档一枚分位都没算出来（档位名或 wall_ms 全部取不到）⇒ rc=2，不交假数")
        return 2
    print("- 出了读数的档=%s ｜ 样本不足仍如实报 n 的档=%s" % (
        ", ".join(measured),
        ", ".join(lane for lane in measured if not cells[lane]["enough"]) or "无"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
