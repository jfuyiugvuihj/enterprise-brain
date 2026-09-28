"""A ② 与 D 流内格的口径读出（R443）。只读、离线、零网络、零模型、零容器。

为什么要这件（病根，不是锦上添花）：
上一班判读件（`%TEMP%\\evalrun\\r9_readout.py`）的抬头写着「两套范围都给」，实际只给了
剔除 `report-01..12` 之后那 93 枚一套（它 :133 `elig = [i for i in fx if i not in REPORT_IDS]`）。
而那句排除理由——「报告题因 `REPORT_LANE_VIA_QUEUE=on` 走队列道，所以没有增量流」——
被同一节自己的数据否掉：12 枚报告题的队列键数全为 0、帧账全在位、`text_frames` 15..50。
⇒ 判据范围应当是 105，排除条件不成立。件口径躺在 TEMP 里不可钉、机器一崩就没，本件落仓。

顺带分开两层读数（前一班把两层混成一层，于是把「查错了层」报成「量不到」）：
① **流内层**：`sources` / `answer.headline` / 终止帧这些事件本身在不在 SSE 流里，读 `events`。
② **队列可读面层**：`GET /queue/{id}` 响应体里的 `sources_present` / `usage`，读 `queue` 格。
两格判据原文各指各的层，谁也不覆盖谁。

用法：
    python scripts/eval_frame_caliber_readout.py
    python scripts/eval_frame_caliber_readout.py --frames docs/testing/sidecar-run9-frames.jsonl
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import os
import sys

DEFAULT_FRAMES = os.path.join("docs", "testing", "sidecar-run9-frames.jsonl")
REPORT_PREFIX = "report-"

#: 判据② 的在册合取口径出处：`app/quality` 之外，唯一实现是
#: `scripts/eval_transport_ask_v2.py` 的 `_frame_verdict`。本件不复制那套条件，
#: 只把每一格**原始计数**摊开，`criterion_two_holds` 用收窗时已落盘的那一格。
RAW_CELLS = (
    "text_frames",
    "max_stream_frames",
    "prefix_breaks",
    "uncorrected_breaks",
    "missing_chars",
    "extra_chars",
)


def load_rows(path: str) -> list[dict]:
    rows: dict[str, dict] = {}
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            previous = rows.get(row["id"])
            # 同题多轮（重试）时取 attempt 最大的那一行，并把取了几行留在账上。
            if previous is None or int(row.get("attempt") or 0) >= int(previous.get("attempt") or 0):
                rows[row["id"]] = row
    return list(rows.values())


def event_tally(rows: list[dict]) -> collections.Counter:
    tally = collections.Counter()
    for row in rows:
        names = {event.get("event") for event in (row.get("events") or [])}
        for name in names:
            tally[name] += 1
    return tally


def caliber_block(title: str, rows: list[dict]) -> None:
    total = len(rows)
    print("### %s（n=%d）" % (title, total))
    graded = [row for row in rows if isinstance(row.get("criterion_two_holds"), bool)]
    for cell in RAW_CELLS:
        offenders = sorted(
            row["id"] for row in rows if int(row.get(cell) or 0) > 0
        ) if cell != "text_frames" and cell != "max_stream_frames" else []
        if cell in ("text_frames", "max_stream_frames"):
            over_one = sum(1 for row in rows if int(row.get(cell) or 0) > 1)
            zero = sum(1 for row in rows if int(row.get(cell) or 0) == 0)
            print("- %s >1 枚数=%d/%d ｜ =0（空读）枚数=%d" % (cell, over_one, total, zero))
        else:
            print("- %s >0 枚数=%d 题号=%s" % (cell, len(offenders), offenders or "无"))
    holds = sum(1 for row in graded if row["criterion_two_holds"])
    failing = sorted(row["id"] for row in graded if row["criterion_two_holds"] is False)
    print("- criterion_two_holds=True 枚数=%d/%d（在册合取口径=_frame_verdict）" % (holds, total))
    print("- criterion_two_holds=False 题号=%s" % (failing or "无"))
    missing_any = sum(1 for row in rows if int(row.get("missing_chars") or 0) > 0)
    print("- 判据② 原文两格：`text 事件数 >1` 与 `逐字比对无缺字`（缺字=missing_chars）⇒ 缺字枚数=%d" % missing_any)
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", default=DEFAULT_FRAMES, help="帧账 jsonl（一题一行）")
    args = parser.parse_args(argv)

    if not os.path.exists(args.frames):
        print("取不到读数件：%s —— 明写取不到，不编数" % args.frames, file=sys.stderr)
        return 2

    rows = load_rows(args.frames)
    by_id = {row["id"]: row for row in rows}
    report_ids = sorted(i for i in by_id if i.startswith(REPORT_PREFIX))
    non_report = [row for row in rows if not row["id"].startswith(REPORT_PREFIX)]

    print("## 帧账口径读出（件=%s）" % args.frames)
    print("- 行数=%d ｜ 唯一题号=%d" % (len(rows), len(by_id)))
    print()

    print("### 排除条件的凭据（报告档 12 枚到底走了哪条道）")
    print("- 逐枚 (kind, text_frames, max_stream_frames, 队列格键数)：")
    queue_cells = 0
    one_one = 0
    for identifier in report_ids:
        row = by_id[identifier]
        queue = row.get("queue")
        keys = len(queue) if isinstance(queue, dict) else -1
        queue_cells += 1 if keys > 0 else 0
        one_one += 1 if (int(row.get("text_frames") or 0) == 1 and int(row.get("max_stream_frames") or 0) == 1) else 0
        print("  - %s kind=%s tf=%d max_stream=%d queue_keys=%d" % (
            identifier, row.get("kind"), int(row.get("text_frames") or 0),
            int(row.get("max_stream_frames") or 0), keys))
    print("- 队列格非空的报告题数=%d/%d ｜ (text_frames,max_stream_frames)=(1,1) 枚数=%d/%d" % (
        queue_cells, len(report_ids), one_one, len(report_ids)))
    verdict = ("排除理由成立：报告题确实没走同步流式道" if queue_cells == len(report_ids) and one_one == len(report_ids)
               else "🔴 排除理由不成立：报告题走的是同步流式道，A② 范围必须含它们")
    print("- ⇒ %s" % verdict)
    print()

    caliber_block("A② 全量范围（105 枚）", rows)
    caliber_block("A② 剔报告档范围（上一班实际只给了这一套）", non_report)

    print("### 流内层 vs 队列可读面层（D 行三格分家）")
    for title, subset in (("全量", rows), ("报告档", [by_id[i] for i in report_ids])):
        tally = event_tally(subset)
        print("- %s（n=%d）流内出现过的枚数：sources=%d ｜ answer.headline=%d ｜ request.completed=%d ｜ done=%d ｜ request.failed=%d ｜ hitl=%d" % (
            title, len(subset), tally.get("sources", 0), tally.get("answer.headline", 0),
            tally.get("request.completed", 0), tally.get("done", 0),
            tally.get("request.failed", 0), tally.get("hitl", 0)))
    print("- 队列可读面层（usage / sources_present 的正解落点）：本报告里逐枚 queue 键数已在上面给出，键数为 0 ⇒ 这一层今天**没被测过**，不是**测了不过**。")
    print("- 🔴 两层不许互抄：`usage` 六枚槽只在队列可读面响应体里（`scripts/eval_transport_ask_v2.py:803-831`），帧账的 `events` 只存事件名不存载荷，所以流内读不到 usage 属**量具不采载荷**，不许读成「模型没报 usage」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())