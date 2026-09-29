# -*- coding: utf-8 -*-
"""R239 判据② 离线判器（2026-09-25）：只读，零网络、零模型、零容器、零写库。

它只回答一件事：**阶段 A 判据② 那句原文，今天能不能拿已有帧账判成可复核的形式**，
以及帧账里那枚 ``criterion_two_holds`` 到底是不是② 的等价物。本件不产生新读数，
它把 ``docs/testing/sidecar-runN-frames.jsonl`` 已有的键**按② 的原文重新折一遍**。

===== 判据② 的完整条件集合（本件据此判，逐字对计划书） =====

计划书 ``docs/handoff/2026-09-17-perf-architecture-plan.md`` 里与② 有关的三句：

* :21 裁定表第 3 行（四条判据的原始表述）：「总时长 ≤90 s / ``text`` 事件数 >1 且无缺字 /
  容器内 ``nvidia-smi`` 可见卡且拿不到卡必须报错 / 30 题评测不退化」。
* §6 A 行第②格（本单靶心，逐字）：「``text`` 事件数 >1 且逐字比对无缺字」。
* :87 §2.7 结论（② 这一格的设计约束来源，同一份文档）：「后端必须按小缓冲发片
  （≥20 字或 100 ms 合并），**禁单字碎片**；这三条写进 R31 判据」。

⇒ **② 的原文只有两格，没有第三格**，本件就按这两格判：

    ②-a event_count_gt_1      =  text_frames > 1
    ②-b char_by_char_no_loss  =  missing_chars == 0 且 extra_chars == 0 且 last_frame_covers_answer
    ②   verdict               =  ②-a 且 ②-b

②-b 的三枚合取不是新增条件，而是「逐字比对无缺字」在收端的既有操作化：``missing_chars`` /
``extra_chars`` 是终答相对末帧的缺字与多字，``last_frame_covers_answer`` 是 covering 一致性
（口径出处 ``docs/testing/r181-text-frame-readings.md`` §二 + R215 的两处变严）。
要按「屏上连续性也算逐字」那一读判，加 ``--breaks-count-as-loss``，它把
``uncorrected_breaks == 0`` 并进②-b —— 两种读法都出数，口径冲突因此摆到明面上而不是各自解释。

===== 帧账那枚 criterion_two_holds 不是② 的等价物 =====

真尺在 ``scripts/eval_transport_ask_v2.py`` 的 ``_frame_verdict``（行号随改动漂移，本件按函数名取坐标），
它今天合取**七枚**（R215 换掉坏形那一枚的读法，R471 再加逐帧重合那一枚）：
    text_frames > 1 且 max_stream_frames > 1 且 uncorrected_breaks == 0
    且 missing_chars == 0 且 extra_chars == 0 且 last_frame_covers_answer
    且 cross_stream_repeat_frames == 0（R471 第七枚：正文在同一轮里出现两遍）


比② 原文多出三枚：``max_stream_frames > 1``（R181 自加，理由写在真源的 ``_frame_readings``
「判据② 要的是后者」）、``uncorrected_breaks == 0``（R215 的「无坏形」）、
``cross_stream_repeat_frames == 0``（R471 的「正文没在同一轮里出现两遍」）。**这三枚都不在 §6 A②
那句话里**，:87 那句的落点明文是 R31 判据。所以本件对每题同时输出：

* ``event_count_gt_1`` / ``char_by_char_no_loss`` / ``verdict``：② 原文的两格与合取；
* ``ledger_criterion_two_holds``：账上写的那一格（真尺合取的存档值）；
* ``recomputed_ledger``：本件按同样七枚**独立复算**的值 —— 两者不符 ⇒ 账与尺不同代，当场点名；
* ``cross_stream_repeat_frames``：R471 第七枚合取的证词。🔴 帧账里**没有这一格**（丙案，总控
  09-29 裁定一：那一列不许开），本件从行内既有那一列 R223 逐帧指纹 ``frames`` 现场派生；账里连
  逐帧指纹都没有（R223 并树之前的窗，run7 即此形）⇒ 派生不出，读 ``null``，按当年的读数放行，
  **不重判**；
* ``extra_red_conditions``：② 之外哪几枚红（只可能是 ``max_stream_frames>1`` 与
  ``uncorrected_breaks==0`` 那两枚；R471 第七枚另有一格 ``cross_stream_repeat_frames``，不混进这里）；
* ``disagreement``：② 与账读得不一致；
* ``event_form``：把形状分四档，见 ``classify_event_form``；
* ``schedule_check``：:87 那条「≥20 字或 100 ms 合并 / 禁单字碎片」判不判得动 ——
  run7 那 21 键里逐帧到达与逐帧字数都不存在，本件对它诚实回 ``unmeasurable``。

===== 这一套口径下 chart-01 读成什么 =====

run7 的 ``chart-01``：``text_frames=2``、``streams=2``、``max_stream_frames=1``、
``missing_chars=extra_chars=uncorrected_breaks=0``、``last_frame_covers_answer=true``、
``per_stream=[{"frames":1},{"frames":1}]``、``criterion_two_holds=false``。

⇒ ②-a 真（2>1）、②-b 真（三格全过）⇒ **② 原文读 True**；账读 False 的唯一原因是
``max_stream_frames == 1``：那两枚帧分属两条流（挂起轮一帧 + 批准恢复轮一帧），每条流各自
只有一枚整段帧，没有任何一条流在逐片累计。所以 chart-01 的红**既不是缺字，也不是事件数不够**，
是量具替② 加的第三条要求 —— 它读的是 :87 的意图，不是 A② 的字面。
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRAMES = REPO_ROOT / "docs" / "testing" / "sidecar-run7-frames.jsonl"

#: 判② 必读的键：少任何一枚就不是「没量到」而是「这份账不是一张帧账」，直接 raise。
REQUIRED_KEYS = ("text_frames", "missing_chars", "extra_chars",
                 "last_frame_covers_answer", "criterion_two_holds")
#: 真尺 ``_frame_verdict`` 的七枚合数（独立复算用），顺序与源码一致。R471 起第七枚
#: ``cross_stream_repeat_frames`` 是从 ``frames`` 那一列**现场派生**的读数 —— 帧账里没有它本身。
LEDGER_CONJUNCTS = ("text_frames", "max_stream_frames", "uncorrected_breaks",
                    "missing_chars", "extra_chars", "last_frame_covers_answer",
                    "cross_stream_repeat_frames", "criterion_two_holds")
#: R223 / R222 新开在**落盘这一层**的七格。run7 一枚都没有：那一窗开在 R223 并树之前。
ARRIVAL_KEYS = ("frames", "events", "stream_clock", "queue",
                "first_visible_at", "first_visible_event", "first_visible_ms")

#: 同一份名单的集合形：判「这一轮的账到没到 R223」时一句话取证用。
ARRIVAL_KEYS_SET = frozenset(ARRIVAL_KEYS)


class LedgerSchemaError(ValueError):
    """账件形状不对（缺键 / 非 JSON 对象 / 行数读不动）—— 判器宁可拒判，不可静默补零。"""


def sha256_of(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path):
    path = Path(path)
    if not path.is_file():
        raise LedgerSchemaError("帧账读不到：" + str(path))
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise LedgerSchemaError(str(path) + ":" + str(lineno) + " 不是 JSON 对象")
            missing = [key for key in REQUIRED_KEYS if key not in row]
            if missing:
                raise LedgerSchemaError(
                    str(path) + ":" + str(lineno) + " 缺判② 必读的键 " + ",".join(missing))
            rows.append(row)
    return rows


def _uncorrected_breaks(row):
    """R215 之前的老账没有这一格：按当年口径退回 ``prefix_breaks``（0 枚豁免）。

    与 ``tests/test_r215_recomputing_run6_frames.py`` 同一条纪律 —— 换读法绝不能把当年的红字洗白。
    """
    if "uncorrected_breaks" in row:
        return int(row["uncorrected_breaks"])
    return int(row.get("prefix_breaks") or 0)


def cross_stream_repeat_frames(row):
    """R471 第七枚合取：同一轮里有几枚正文是「后一条流把先前发过的那份字又发一遍」。

    🔴 帧账里**没有这一格**（丙案，总控 09-29 裁定一：那一列不许开），本件从行内既有那一列 R223
    逐帧指纹 ``frames`` 现场派生。口径与 ``scripts/eval_transport_ask_v2.py`` 的
    ``_cross_stream_repeats`` 逐字同：只算跨流（同一条流里末片帧与收尾帧同文不算出现两遍 ——
    **总控裁定**，原话与署名见 ``docs/testing/r471-verdict-caliber-2026-09-29.md``）、空帧不参与、
    没有指纹不参与（不许拿缺证词当证据，与 R215 判据① 同一条纪律）。

    账里连 ``frames`` 都没有、或有这一列却一枚逐帧指纹都不带（量具被摘瞎那一形，同 ``schedule_check``
    对 ``per_frame`` 的处理）⇒ 回 ``None``：这一格在那扇窗里从没量过，本件按当年的读数放行，
    🔴 既不追加定罪也不洗白，也不许报 0 冒充量过 —— 与 ``_uncorrected_breaks`` 拿老账退回
    ``prefix_breaks`` 同一条纪律。
    """
    records = row.get("frames")
    if not isinstance(records, list) or not records:
        return None
    earliest = {}
    repeats = 0
    for record in records:
        if int(record.get("chars") or 0) <= 0:
            continue  # 空帧没有正文，谈不上「出现两遍」
        sha = str(record.get("sha") or "")
        if not sha:
            continue  # 没指纹就没证词
        stream = int(record.get("stream") or 0)
        if sha in earliest and stream > earliest[sha]:
            repeats += 1  # 同一份字在更早的一条流里已经上过屏：本轮第二次送达
        earliest[sha] = min(stream, earliest.get(sha, stream))
    return repeats


def event_count_gt_1(row):
    """②-a：``text`` 事件数 >1 —— 只读 ``text_frames``，不掺任何本件自己的要求。"""
    return int(row["text_frames"]) > 1


def char_by_char_no_loss(row, breaks_count_as_loss=False):
    """②-b：逐字比对无缺字 = 不缺字、不多字、covering 一致。

    ``breaks_count_as_loss`` 是给口径冲突留的开关：把 ``uncorrected_breaks == 0``（屏上
    连续性/无坏形）也算进「逐字」那一半。两种读法都出数，谁在解释② 就一目了然。
    """
    holds = (int(row["missing_chars"]) == 0 and int(row["extra_chars"]) == 0
             and bool(row["last_frame_covers_answer"]))
    if breaks_count_as_loss:
        holds = holds and _uncorrected_breaks(row) == 0
    return holds


def recomputed_ledger(row):
    """独立复算真尺那七枚合取（真源 = ``scripts/eval_transport_ask_v2.py`` 的 ``_frame_verdict``；
    行号随改动漂移，故按函数名取坐标，不抄一份会过期的行号）。

    与账上存档的 ``criterion_two_holds`` 不符 ⇒ 这份账与当前这把尺不同代，本件把它列进
    ``ledger_drift`` 而不是替它改写。
    """
    return bool(int(row["text_frames"]) > 1
                and int(row.get("max_stream_frames") or 0) > 1
                and _uncorrected_breaks(row) == 0
                and int(row["missing_chars"]) == 0
                and int(row["extra_chars"]) == 0
                and bool(row["last_frame_covers_answer"])
                # R471 第七枚：证词不落账，从行内那一列逐帧指纹现场派生；派生不出（None）⇒ 不重判。
                and cross_stream_repeat_frames(row) in (None, 0))


def extra_red_conditions(row):
    """② 原文之外、真尺还要求而这一题没做到的条件，逐枚点名。"""
    reds = []
    if int(row.get("max_stream_frames") or 0) <= 1 and int(row["text_frames"]) > 1:
        reds.append("max_stream_frames>1")
    if _uncorrected_breaks(row) != 0:
        reds.append("uncorrected_breaks==0")
    return reds


def classify_event_form(row):
    """把「>1 帧」这件事分成三种完全不同的形状，供逐题解释（不新判任何东西）。"""
    frames = int(row["text_frames"])
    streams = int(row.get("streams") or 0)
    per_stream = row.get("per_stream") or []
    stream_frames = [int(item.get("frames") or 0) for item in per_stream] or [0]
    if frames == 0:
        return "no_text_frame"
    if frames == 1:
        return "single_frame" if streams <= 1 else "single_frame_across_" + str(streams) + "_streams"
    if max(stream_frames) > 1:
        return "incremental_within_one_stream"
    return "one_frame_per_stream"  # chart-01 那一族：凑够 2 帧，但没有一条流在逐片累计


def schedule_check(row):
    """:87 那条「≥20 字或 100 ms 合并 / 禁单字碎片」今天判不判得动。

    判它需要**逐帧**的到达时刻与字数（run8 起才有：``frames[]`` 每枚带
    ``at`` / ``stream`` / ``arrival_at`` / ``elapsed_ms`` / ``chars``）。缺任何一件就回
    ``unmeasurable`` —— 不许拿 ``last_frame_chars`` 冒充逐帧分布。
    """
    per_frame = row.get("frames")
    if not isinstance(per_frame, list) or not per_frame:
        return {"status": "unmeasurable",
                "reason": "帧账无逐帧到达/逐帧字数（R223 并树之前的账，run7 即此形）",
                "frame_count_with_arrival": 0, "single_char_fragments": None,
                "min_increment_chars": None, "max_gap_ms": None}
    by_stream = {}
    for item in per_frame:
        by_stream.setdefault(int(item.get("stream") or 0), []).append(item)
    increments, gaps, fragments = [], [], 0
    for items in by_stream.values():
        items.sort(key=lambda item: int(item.get("at") or 0))
        previous_chars = 0
        previous_ms = None
        for item in items:
            chars = int(item.get("chars") or 0)
            increments.append(chars - previous_chars)
            if chars - previous_chars <= 1:
                fragments += 1
            elapsed = item.get("elapsed_ms")
            if elapsed is not None and previous_ms is not None:
                gaps.append(round(float(elapsed) - float(previous_ms), 1))
            if elapsed is not None:
                previous_ms = float(elapsed)
            previous_chars = chars
    return {"status": "measured", "reason": "",
            "frame_count_with_arrival": len(per_frame),
            "single_char_fragments": fragments,
            "min_increment_chars": min(increments) if increments else None,
            "max_gap_ms": max(gaps) if gaps else None}


def judge_row(row, breaks_count_as_loss=False):
    event_ok = event_count_gt_1(row)
    char_ok = char_by_char_no_loss(row, breaks_count_as_loss)
    ledger = bool(row["criterion_two_holds"])
    verdict = bool(event_ok and char_ok)
    return {"id": str(row.get("id", "")), "kind": str(row.get("kind", "")),
            "text_frames": int(row["text_frames"]),
            "max_stream_frames": int(row.get("max_stream_frames") or 0),
            "streams": int(row.get("streams") or 0),
            "event_count_gt_1": event_ok,
            "char_by_char_no_loss": char_ok,
            "verdict": verdict,
            "ledger_criterion_two_holds": ledger,
            "cross_stream_repeat_frames": cross_stream_repeat_frames(row),
            "recomputed_ledger": recomputed_ledger(row),
            "ledger_drift": recomputed_ledger(row) != ledger,
            "extra_red_conditions": extra_red_conditions(row),
            "event_form": classify_event_form(row),
            "answer_chars": int(row.get("answer_chars") or 0),
            #: R223 / R222 那七格在这行上到底有没有（run7 一枚都没有 ⇒ :87 那条约束无从核对）。
            "arrival_keys_present": [key for key in ARRIVAL_KEYS if key in row],
            "schedule_check": schedule_check(row),
            "disagreement": verdict != ledger}


def summarize(judged):
    def count(flag):
        return sum(1 for item in judged if item[flag])
    forms = {}
    for item in judged:
        forms[item["event_form"]] = forms.get(item["event_form"], 0) + 1
    return {"rows": len(judged),
            "criterion_two_holds_literal": count("verdict"),
            "criterion_two_fails_literal": len(judged) - count("verdict"),
            "cell_event_count_gt_1_true": count("event_count_gt_1"),
            "cell_char_by_char_no_loss_true": count("char_by_char_no_loss"),
            "ledger_criterion_two_holds_true": count("ledger_criterion_two_holds"),
            "disagreements": [item["id"] for item in judged if item["disagreement"]],
            "ledger_drift": [item["id"] for item in judged if item["ledger_drift"]],
            # R471：逐帧指纹重合的题号（``None``＝那扇窗没量过，不进这一格；本件不据它改判当年读数）。
            "cross_stream_repeat_ids": [item["id"] for item in judged
                                        if (item["cross_stream_repeat_frames"] or 0) > 0],
            "cross_stream_repeat_unmeasurable": sum(1 for item in judged
                                                    if item["cross_stream_repeat_frames"] is None),
            "event_forms": forms,
            "rows_with_arrival_keys": sum(1 for item in judged if item["arrival_keys_present"]),
            "schedule_measurable_rows": sum(1 for item in judged
                                           if item["schedule_check"]["status"] == "measured")}


def render_table(judged, summary):
    header = "{0:<14} {1:<13} {2:>4} {3:>4} {4:>3}  {5:<5} {6:<5} {7:<5} {8:<5} {9:<32} {10}"
    lines = [header.format("id", "kind", "tf", "msf", "st", "2a", "2b", "2", "led",
                           "form", "extra_reds(②之外)")]
    for item in judged:
        lines.append(header.format(
            item["id"], item["kind"], item["text_frames"], item["max_stream_frames"],
            item["streams"], "TRUE" if item["event_count_gt_1"] else "red",
            "TRUE" if item["char_by_char_no_loss"] else "red",
            "TRUE" if item["verdict"] else "red",
            "TRUE" if item["ledger_criterion_two_holds"] else "red",
            item["event_form"], ",".join(item["extra_red_conditions"]) or "-"))
    lines.append("")
    lines.append("rows={rows}  ②真={c2t} ②红={c2f}  账真={lt}  分歧={dis}  复算漂={drift}  "
                 "逐帧到达可判行={sch} 带R223到达键行={ak} R471重合行={rep} 重合量不出={repn}".format(
                     rows=summary["rows"], c2t=summary["criterion_two_holds_literal"],
                     c2f=summary["criterion_two_fails_literal"],
                     lt=summary["ledger_criterion_two_holds_true"],
                     dis=",".join(summary["disagreements"]) or "-",
                     drift=",".join(summary["ledger_drift"]) or "-",
                     sch=summary["schedule_measurable_rows"], ak=summary["rows_with_arrival_keys"],
                     rep=",".join(summary["cross_stream_repeat_ids"]) or "-",
                     repn=summary["cross_stream_repeat_unmeasurable"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="R239 判据② 离线判器（只读；②原文两格 vs 帧账 criterion_two_holds）")
    parser.add_argument("--frames", default=str(DEFAULT_FRAMES),
                        help="帧账 jsonl（默认 run7；任意同 schema 帧账皆可指）")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--id", action="append", default=[], help="只看这些题（可重复）")
    parser.add_argument("--red-only", action="store_true",
                        help="只列 ② 红、账红、或两把读数不一致的行")
    parser.add_argument("--breaks-count-as-loss", action="store_true",
                        help="把 uncorrected_breaks==0 也算进②-b（屏上连续性口径）")
    parser.add_argument("--fail-on-disagreement", action="store_true",
                        help="② 与 criterion_two_holds 有分歧就 exit 1")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    frames_path = Path(args.frames)
    sha_before = sha256_of(frames_path)
    rows = read_rows(frames_path)
    judged = [judge_row(row, args.breaks_count_as_loss) for row in rows]
    if args.id:
        wanted = set(args.id)
        judged = [item for item in judged if item["id"] in wanted]
    if args.red_only:
        judged = [item for item in judged if (not item["verdict"]
                                              or not item["ledger_criterion_two_holds"]
                                              or item["disagreement"])]
    summary = summarize(judged)
    # 🔴 只读取证：读完再取一次 sha256，两枚相同才叫「本件一行都没写」。
    sha_after = sha256_of(frames_path)
    summary["input_sha256_before"] = sha_before
    summary["input_sha256_after"] = sha_after
    summary["input_unchanged"] = sha_before == sha_after

    if args.format == "json":
        print(json.dumps({"summary": summary, "rows": judged}, ensure_ascii=False, indent=2))
    else:
        print("帧账：" + str(frames_path) + "  sha256=" + sha_before
              + "  读完再取=" + sha_after + "  未改动=" + str(summary["input_unchanged"]))
        print(render_table(judged, summary))
    if not summary["input_unchanged"]:
        return 2
    if args.fail_on_disagreement and summary["disagreements"]:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LedgerSchemaError as error:
        print("REJECTED " + str(error), file=sys.stderr)
        sys.exit(2)
