"""R573 A 判据② 三口径对账（run13／run14 两窗）。只读、离线、零网络、零模型、零容器。

为什么要这件：看板 5949 那行把 A② 判成「不能翻绿，需业主三口径裁定」，而当时只有 run9 一扇窗；
run13／run14 是第一次两窗各 105 枚齐、且都带 R223 逐帧到达坐标的账（run6 那遍「逐帧到达可判行=0」
＝不可判，抄成绿是旧账）。本件把三档裁定各自要的分母/分子**当场算出来**，只交数、不选口径。

🔴 本件不复制任何判则。所有数都从三枚在册件现场调用派生（行号会漂，符号名不会）：
  * `scripts/eval_frame_caliber_readout.py` —— `load_rows` / `caliber_block` / `main`（主口径逐字引用）
  * `scripts/r239_stream_gap_offline_audit.py` —— `read_rows` / `judge_row` / `recomputed_ledger` /
    `extra_red_conditions` / `schedule_check`（②-a／②-b 两格与七枚合取的在册复算）
  * `scripts/r565_a2_denominator_buckets.py` —— `read_round` / `prefab_fingerprints` / `bucket_of_row`
    （B1 天然短／B2 无逐片腿／B3 预制句 三格归账，含现取预制指纹与尺寸闸）

三档裁定各自的问题（原话见看板 5949 行）：
  甲 逐片腿适用范围 —— 分母该不该只留「本轮应当有逐片流」的题。两读：甲-1 按在册桶（剔 B1∪B2），
      甲-2 按逐帧那一列到底有没有（剔 text_frames==0，即②-a 在这些行压根不可判）。
  乙 no_answer 挪出分母另立格 —— 两读：乙-1 只挪 family=no_answer_produced 那一族，
      乙-2 连采集器哨兵（approval-failed 那一族）一起挪；🔴 被挪走的每一枚逐题点名，不许蒸发。
  丙 max_stream_frames>1 算不算 A② —— 同一分母两个分子：丙-算＝在册七枚合取（recomputed_ledger），
      丙-不算＝把这一枚合取对每一行走一遍反事实探针（抬高 max_stream_frames 再叫在册尺复算），
      翻动的题号逐枚点名。探针只改内存里的那一行影子，盘上一字节不动。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import eval_frame_caliber_readout as readout  # noqa: E402  在册主口径
import r239_stream_gap_offline_audit as audit  # noqa: E402  在册判器
import r565_a2_denominator_buckets as buckets  # noqa: E402  在册四桶归账

DEFAULT_EVALRUN = Path(os.environ.get("TEMP", ".")) / "evalrun"
DEFAULT_TAGS = ("run13", "run14")
EXPECTED_DENOMINATOR = 105  # 在册分母（本件当对账尺，不当结论）
NO_ANSWER_FAMILY = "no_answer_produced"  # 族名从现取指纹的 family 字段读，不手抄 sha

RC_OK = 0
RC_REFUSE = 2
RC_GREEN = 3

CALIBRE_LABELS = ("甲-1", "甲-2", "乙-1", "乙-2", "丙-算", "丙-不算")


class RefuseError(Exception):
    """问不到就是问不到：拒绝出数，不许退化成半套读数，也不许把「没量过」读成「量过且干净」。"""


def sha12(path) -> str:
    """盘上取证用：本件全程只读，任何一枚输入件/在册件的 sha 都只读不写。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def ledger_paths(evalrun: Path, tag: str, overrides: dict) -> dict:
    paths = {
        "frames": Path(overrides.get("frames") or (evalrun / (tag + "-sidecar-frames.jsonl"))),
        "sidecar": Path(overrides.get("sidecar") or (evalrun / (tag + "-sidecar.jsonl"))),
        "answers": Path(overrides.get("answers") or (evalrun / (tag + "-answers.jsonl"))),
    }
    for key, path in paths.items():
        if not path.is_file():
            raise RefuseError("输入件读不到：" + key + "=" + str(path)
                              + " ⇒ 这一窗不出数（本件不补造账、不写盘，先确认收窗件在不在）")
        if path.stat().st_size == 0:
            raise RefuseError("输入件零字节：" + key + "=" + str(path) + " ⇒ 不可判，拒绝出数")
    return paths


def load_window(paths: dict, expect: int) -> dict:
    """三本账现场调用在册件读进来；任何一枚问不到 ⇒ RefuseError（不许半套出数）。"""
    try:
        rows = audit.read_rows(paths["frames"])  # 在册判器：非对象/缺判② 必读键当场 LedgerSchemaError
    except (ValueError, OSError) as exc:
        raise RefuseError("帧账读不动（截断或形状不对）：" + str(exc)) from exc
    if not rows:
        raise RefuseError("帧账读出行数=0：" + str(paths["frames"]) + " ⇒ 不可判，拒绝出数")
    try:
        dedup = readout.load_rows(str(paths["frames"]))  # 在册主口径取行法（同题多轮取 attempt 最大那一行）
    except (ValueError, OSError) as exc:
        raise RefuseError("主口径取行失败：" + str(exc)) from exc
    if len(dedup) != expect:
        raise RefuseError("分母对不上在册分母：主口径去重后题数=" + str(len(dedup))
                          + " 而要求=" + str(expect) + " ⇒ 拒绝按半套窗出数（要出小窗就显式改 --expect-denominator）")
    try:
        result = buckets.read_round(frames=paths["frames"], sidecar=paths["sidecar"],
                                    answers=paths["answers"])
    except (ValueError, OSError) as exc:
        raise RefuseError("在册四桶归账读不动：" + str(exc)) from exc
    return {"rows": rows, "dedup_count": len(dedup), "buckets": result,
            "frames_collapsed": result["frames_collapsed"]}


def build_records(rows: list, result: dict) -> list:
    """逐题一条记录：桶、②-a/②-b 两格、账上 criterion_two_holds、在册复算、丙档反事实探针、可判性。"""
    by_id = {str(item["id"]): item for item in result["rows"]}
    prefab = result["prefab"]
    records = []
    for row in rows:
        rid = str(row["id"])
        entry = by_id[rid]
        judged = audit.judge_row(row)
        msf = int(row.get("max_stream_frames") or 0)
        shadow = dict(row)
        shadow["max_stream_frames"] = max(msf, 2)  # 🔴 只改内存里的这一枚影子，盘上不动
        with_conjunct = bool(audit.recomputed_ledger(row))
        without_conjunct = bool(audit.recomputed_ledger(shadow))
        answer_sha = str(row.get("answer_sha", ""))
        family = str((prefab.get(answer_sha) or {}).get("family") or "")
        schedule = judged["schedule_check"]
        records.append({
            "id": rid,
            "kind": str(row.get("kind", "")),
            "bucket": entry["bucket"],
            "also_matched": list(entry["also_matched"]),
            "text_frames": int(row.get("text_frames") or 0),
            "max_stream_frames": msf,
            "streams": int(row.get("streams") or 0),
            "answer_chars": int(row.get("answer_chars") or 0),
            "answer_sha": answer_sha,
            "prefab_family": family,
            "tool_calls": entry["tool_calls"],
            "ledger": bool(row.get("criterion_two_holds")),
            "recomputed": with_conjunct,
            "without_msf": without_conjunct,
            "flipped_by_msf": bool(without_conjunct and not with_conjunct),
            "literal": bool(judged["verdict"]),
            "cell_2a": bool(judged["event_count_gt_1"]),
            "cell_2b": bool(judged["char_by_char_no_loss"]),
            "extra_reds": list(judged["extra_red_conditions"]),
            "event_form": judged["event_form"],
            "measurable": schedule["status"] == "measured",
            "unmeasurable_reason": str(schedule.get("reason") or ""),
            "arrival_keys": list(judged["arrival_keys_present"]),
            "drift": bool(judged["ledger_drift"]),
        })
    return records


def group(records: list, deducted: set, label: str, note: str, primary: str, cells: dict = None) -> dict:
    """一档一数：分母/三种分子/被扣题号/档内 criterion_two_holds/不可判枚数。🔴 只做算术，不判口径。"""
    keep = [item for item in records if item["id"] not in deducted]
    out = {
        "label": label,
        "note": note,
        "primary_green_key": primary,
        "total_rows": len(records),
        "deducted_ids": sorted(deducted),
        "deducted_count": len(deducted),
        "denominator": len(keep),
        "green_ledger": sum(1 for item in keep if item["ledger"]),
        "green_recomputed": sum(1 for item in keep if item["recomputed"]),
        "green_without_msf": sum(1 for item in keep if item["without_msf"]),
        "green_literal": sum(1 for item in keep if item["literal"]),
        "green_ids_ledger": sorted(item["id"] for item in keep if item["ledger"]),
        "green_ids_recomputed": sorted(item["id"] for item in keep if item["recomputed"]),
        "green_ids_without_msf": sorted(item["id"] for item in keep if item["without_msf"]),
        "green_ids_literal": sorted(item["id"] for item in keep if item["literal"]),
        "red_ids_ledger": sorted(item["id"] for item in keep if not item["ledger"]),
        "red_ids_recomputed": sorted(item["id"] for item in keep if not item["recomputed"]),
        "flipped_by_msf_ids": sorted(item["id"] for item in keep if item["flipped_by_msf"]),
        "drift_ids": sorted(item["id"] for item in keep if item["drift"]),
        "unmeasurable_ids": sorted(item["id"] for item in keep if not item["measurable"]),
        "unmeasurable_count": sum(1 for item in keep if not item["measurable"]),
        "cells": cells or {},
    }
    out["primary_green"] = out["green_" + primary]
    out["ratio"] = ("n/a（分母为 0）" if not out["denominator"]
                    else "%.4f" % (float(out["primary_green"]) / float(out["denominator"])))
    return out


def compute_groups(records: list) -> list:
    """三档裁定 × 每档两读 = 六组数（再乘两窗 = 纸上的 12 组）。🔴 六组全交，本件不挑一组。"""
    b1_b2 = set(item["id"] for item in records if item["bucket"] in (buckets.B1, buckets.B2))
    no_leg = set(item["id"] for item in records if item["text_frames"] == 0)
    b3_all = set(item["id"] for item in records if item["bucket"] == buckets.B3)
    by_family = {}
    for item in records:
        if item["prefab_family"]:
            # 🔴 预制句族按**现取指纹**认，不靠归账桶名：桶名被人摘掉时这一族也不许蒸发
            by_family.setdefault(item["prefab_family"], []).append(item)
    no_answer = set(item["id"] for item in by_family.get(NO_ANSWER_FAMILY, []))
    cells_all = {family: {"count": len(items),
                          "ids": sorted(item["id"] for item in items),
                          "ledger_green": sum(1 for item in items if item["ledger"]),
                          "shas": sorted(set(item["answer_sha"] for item in items)),
                          "text_frames_each": {item["id"]: item["text_frames"] for item in items}}
                 for family, items in sorted(by_family.items())}
    return [
        group(records, b1_b2, "甲-1", "在册桶口径：剔 B1 天然短 ∪ B2 无逐片腿", "ledger"),
        group(records, no_leg, "甲-2", "逐帧那一列到底有没有：剔 text_frames==0（②-a 在这些行不可判）",
              "ledger"),
        group(records, no_answer, "乙-1", "只把 family=" + NO_ANSWER_FAMILY + " 那一族挪出分母，另立格"
              "（认定走现取预制指纹，与归账桶名无关）", "ledger", cells_all),
        group(records, b3_all, "乙-2", "连采集器哨兵那一族一起挪出（B3 全体），另立格", "ledger", cells_all),
        group(records, set(), "丙-算", "分母不动；分子＝在册七枚合取（含 max_stream_frames>1）",
              "recomputed"),
        group(records, set(), "丙-不算", "分母不动；分子＝把 max_stream_frames>1 那一枚对每题走反事实探针",
              "without_msf"),
    ]


def read_window_provenance(evalrun: Path, tag: str) -> dict:
    """收窗时落盘的这一窗出处（镜像 revision／读后端／题集 sha）。读不到就明写读不到，不补造。"""
    path = evalrun / (tag + ".window.json")
    if not path.is_file():
        return {"path": str(path), "status": "读不到 ⇒ 本窗镜像/后端/题集 sha 未经本件现取"}
    try:
        payload = json.loads(io.open(path, encoding="utf-8").read())
    except (ValueError, OSError) as exc:
        return {"path": str(path), "status": "读不动：" + str(exc)}
    return {"path": str(path), "status": "ok", "revision": payload.get("revision"),
            "index_backend": payload.get("index_backend"), "fixture_sha256": payload.get("fixture_sha256"),
            "transport": payload.get("transport"), "shard_size": payload.get("shard_size")}


def in_book_readout(paths: dict) -> dict:
    """主口径＝现场调用在册 `eval_frame_caliber_readout.main()`，逐字收下它打的每一个数。"""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rc = readout.main(["--frames", str(paths["frames"])])
    if rc != RC_OK:
        raise RefuseError("在册主口径当场拒判：eval_frame_caliber_readout rc=" + str(rc))
    return {"rc": rc, "text": buffer.getvalue()}


def collect(tag: str, paths: dict, expect: int) -> dict:
    window = load_window(paths, expect)
    records = build_records(window["rows"], window["buckets"])
    return {"tag": tag, "paths": {key: str(value) for key, value in paths.items()},
            "sha12": {key: sha12(value) for key, value in paths.items()},
            "frames_rows": len(window["rows"]), "dedup_rows": window["dedup_count"],
            "attempts_collapsed": window["frames_collapsed"],
            "gate": window["buckets"]["gate"], "bucket_counts": window["buckets"]["bucket_counts"],
            "also_matched_counts": window["buckets"]["also_matched_counts"],
            "prefab_fingerprints": window["buckets"]["prefab"],
            "diagnostics": window["buckets"]["diagnostics"],
            "records": records, "groups": compute_groups(records),
            "in_book_readout": in_book_readout(paths)}


def render_rows(report: dict, handle) -> None:
    handle.write("### 逐题表（" + report["tag"] + "）" + chr(10))
    handle.write("%-14s %-16s %-4s %-8s %-4s %-4s %-6s %-7s %-20s %-6s %-6s %-6s %-6s %-5s %s" % (
        "id", "kind", "bkt", "also", "tf", "msf", "toolc", "achar", "family", "ledg", "recomp",
        "woMSF", "lit2ab", "meas", "extra_reds") + chr(10))
    for item in report["records"]:
        handle.write("%-14s %-16s %-4s %-8s %-4d %-4d %-6s %-7d %-20s %-6s %-6s %-6s %-6s %-5s %s" % (
            item["id"], item["kind"], item["bucket"], ",".join(item["also_matched"]) or "-",
            item["text_frames"], item["max_stream_frames"], str(item["tool_calls"]),
            item["answer_chars"], item["prefab_family"] or "-", str(item["ledger"]),
            str(item["recomputed"]), str(item["without_msf"]), str(item["literal"]),
            "meas" if item["measurable"] else "不可判", ",".join(item["extra_reds"]) or "-") + chr(10))


def render_group(g: dict, handle) -> None:
    handle.write("- **%s**｜%s" % (g["label"], g["note"]) + chr(10))
    handle.write("    分母=%d/%d（扣 %d 枚）｜分子（primary=%s）=%d｜比值=%s" % (
        g["denominator"], g["total_rows"], g["deducted_count"], g["primary_green_key"],
        g["primary_green"], g["ratio"]) + chr(10))
    handle.write("    三种分子并列：账上 criterion_two_holds=%d ｜ 在册七枚复算=%d ｜ 摘掉 max_stream_frames 那枚=%d ｜ ② 原文两格（②-a∧②-b）=%d"
                 % (g["green_ledger"], g["green_recomputed"], g["green_without_msf"], g["green_literal"]) + chr(10))
    handle.write("    被扣题号=%s" % (g["deducted_ids"] or "无") + chr(10))
    handle.write("    档内红题（账上）=%s" % (g["red_ids_ledger"] or "无") + chr(10))
    handle.write("    档内不可判枚数=%d 题号=%s ｜ 账与复算不同代=%s ｜ 丙档翻动题号=%s" % (
        g["unmeasurable_count"], g["unmeasurable_ids"] or "无", g["drift_ids"] or "无",
        g["flipped_by_msf_ids"] or "无") + chr(10))
    for family, cell in g["cells"].items():
        if not (isinstance(cell, dict) and "count" in cell):
            continue  # cells 里只放族格；别的键不许冒充一格（甲-2 的明细就是「被扣题号」）
        handle.write("    另立格 %s：枚数=%d 题号=%s（其中账上绿=%d，text_frames=%s）" % (
            family, cell["count"], cell["ids"], cell["ledger_green"],
            json.dumps(cell["text_frames_each"], ensure_ascii=False)) + chr(10))


def render_text(reports: list, handle, show_rows: bool) -> None:
    handle.write("# R573 A② 三口径对账（run13／run14）" + chr(10) + chr(10))
    handle.write("🔴 本件只出数：三档 × 两窗的数全交，一档都不替总控挑，也不许拿它宣布翻绿。" + chr(10) + chr(10))
    for report in reports:
        handle.write("## " + report["tag"] + chr(10))
        prov = report["provenance"]
        handle.write("- 出处：" + json.dumps(prov, ensure_ascii=False) + chr(10))
        handle.write("- 输入件 sha12=" + json.dumps(report["sha12"], ensure_ascii=False)
                     + " ｜ 帧账行数=" + str(report["frames_rows"]) + "（去重后=" + str(report["dedup_rows"])
                     + "，同题多轮折叠=" + str(report["attempts_collapsed"]) + "）" + chr(10))
        handle.write("- 尺寸闸现取=" + str(report["gate"]) + " ｜ 四桶=" + json.dumps(report["bucket_counts"], ensure_ascii=False)
                     + " ｜ also=" + json.dumps(report["also_matched_counts"], ensure_ascii=False) + chr(10))
        handle.write("- 在册预制指纹（现取，非手抄）=" + json.dumps(report["prefab_fingerprints"], ensure_ascii=False) + chr(10))
        handle.write("- 在册量具留痕 diagnostics=" + json.dumps(report["diagnostics"], ensure_ascii=False) + chr(10) + chr(10))
        handle.write("### 在册主口径现场调用输出（rc=" + str(report["in_book"]["rc"]) + "，逐字不改一个数）" + chr(10))
        handle.write(report["in_book"]["text"] + chr(10))
        handle.write("### 六组数（三档 × 每档两读）" + chr(10))
        for g in report["groups"]:
            render_group(g, handle)
        handle.write(chr(10))
        if show_rows:
            render_rows(report, handle)
            handle.write(chr(10))


class GreenClaimError(Exception):
    """想拿某一档单独宣布 A② 翻绿：本件有权当场拒（分母被人挪过的那一种绿，比红更坏）。"""


def build_report(tag: str, evalrun: Path, overrides: dict, expect: int) -> dict:
    report = collect(tag, ledger_paths(evalrun, tag, overrides), expect)
    report["provenance"] = read_window_provenance(evalrun, tag)
    report["in_book"] = report.pop("in_book_readout")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="R573：A② 三口径对账（只读、离线、零模型、零容器；三档全交、本件不选口径）")
    parser.add_argument("--evalrun", default=str(DEFAULT_EVALRUN), help="三本账所在目录（默认为当前用户临时目录下的 evalrun）")
    parser.add_argument("--tag", nargs="+", default=list(DEFAULT_TAGS), help="窗名，可多枚（默认 run13 run14）")
    parser.add_argument("--frames", default=None, help="单窗取证：帧账件（只配一枚 --tag 用）")
    parser.add_argument("--sidecar", default=None, help="单窗取证：侧车件")
    parser.add_argument("--answers", default=None, help="单窗取证：终答件")
    parser.add_argument("--expect-denominator", type=int, default=EXPECTED_DENOMINATOR,
                        help="在册分母对账（0 或负数一律拒：不许静默关闸按半套窗出数）")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--no-rows", action="store_true", help="只交六组数，不交逐题表")
    parser.add_argument("--declare-green", default=None,
                        help="演示用：拿这一档宣布翻绿 ⇒ 本件一律当场拒（rc=3）")
    return parser


def main(argv: list = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.declare_green:
            raise GreenClaimError("本件不选口径：甲／乙／丙 三档 × 两窗必须一起交。单独拿「"
                                  + str(args.declare_green) + "」宣布 A② 翻绿＝分母被人挪过 ⇒ 拒。"
                                  "要裁定请由总控拿着六组数下条，记进看板。")
        if args.expect_denominator <= 0:
            raise RefuseError("--expect-denominator 给了 " + str(args.expect_denominator)
                              + "：本件要求显式对账，不许把对账闸关掉之后按小窗出数")
        overrides = {key: getattr(args, key) for key in ("frames", "sidecar", "answers")}
        if any(overrides.values()) and len(args.tag) != 1:
            raise RefuseError("显式指了单窗账件却给了 " + str(len(args.tag))
                              + " 枚 --tag：这会拿同一套账冒充两窗的数 ⇒ 拒")
        evalrun = Path(args.evalrun)
        reports = [build_report(tag, evalrun, overrides, args.expect_denominator) for tag in args.tag]
    except GreenClaimError as exc:
        print("[r573][拒宣布] " + str(exc), file=sys.stderr)
        return RC_GREEN
    except RefuseError as exc:
        print("[r573][REFUSE] " + str(exc), file=sys.stderr)
        return RC_REFUSE
    if args.format == "json":
        print(json.dumps({"instrument": "r573_caliber_reconciliation",
                          "in_book_callers": {
                              "readout": readout.__file__, "audit": audit.__file__,
                              "buckets": buckets.__file__},
                          "reports": reports}, ensure_ascii=False, indent=2))
    else:
        render_text(reports, sys.stdout, not args.no_rows)
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
