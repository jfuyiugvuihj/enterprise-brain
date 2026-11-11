# -*- coding: utf-8 -*-
r"""R518（2026-09-29，执行层）：A② 甲案的**机械落地** —— 让尺子自己说清「这一轮到底有没有逐片腿」。

只读，零网络、零模型、零容器、零写库；🔴 不落任何新键、不改任何在册原件。

## 为什么要这件

计划书 ``docs/handoff/2026-09-17-perf-architecture-plan.md`` §6 追加节（09-29 总控裁定）采**甲案**：
「②只适用于**确有逐片腿的轮**，无 sink 腿的轮记 ``not_applicable``，且必须另立一格可见」。
可那份裁定落地到今天**全靠人对着** ``docs/testing/r506-a2-reading-2026-09-29.md`` §4 那张三堆分诊表
逐枚归因 —— 那是手工账，不是尺子，下一班一抄就漂。本件把那一步变成**派生**：

* 分母不是抄来的名单，是从帧账既有键算出来的；
* 每一枚落格都带**证词**（哪一枚键、哪一个取值把它送进这一格）；
* 派生不出的形状明写「派生不出」，🔴 既不折成 0 也不折成 ``True``（R507/R515 刚治过的那族假零病）。

## 三态（``lane_state``）与格子（``bucket``）

``lane_state`` 只三枚取值：``has_piece_leg`` / ``no_piece_leg`` / ``undecidable``。
判「有腿」只认一枚**正面证词**：``max_stream_frames > 1`` —— 某一条流自己攒出了第二枚文本帧，
且这枚证词必须先过一道**对质**：拿同在一行的 R223 逐帧列 ``frames`` 自己重算流数与单流最大帧数，
与汇总格对不上 ⇒ 落 ``undecidable``（改一枚汇总格是两个字的事，改一串逐帧记录不是）。
这件事只有 sink 在逐片喂它才做得到（口径出处同 ``scripts/r239_stream_gap_offline_audit.py`` 的
``incremental_within_one_stream``）。判「无腿」只认结构性证词，且**一枚都不许多**：
``text_frames == 1`` 而 sidecar 既有键 ``tool_calls == 0``、帧账 ``events`` 里一枚 ``step`` 都没有
（⇒ 本轮根本没有工作腿跑过工具，终答由无 sink 路径一次性交付）；或队列道（``queue`` 格非空 /
``kind`` 以 ``queued`` 起 —— 队列道明文没有 sink）。另有一格**天然短**：有腿证据在位，但终答
短过尺寸闸 ``STREAM_PIECE_MIN_CHARS``（数值从 ``app/agents/nodes.py`` 现取，不在本件抄第二份）
⇒ 按 §2.7「≥20 字或 100 ms 合并」结构上最多一枚帧，红在②-a 属两条规则打架，不是丢字。

其余一切落 ``undecidable``：帧账不带 R223 到达坐标（run6/run7 即此形 —— ``step`` 证词根本不存在，
🔴 拿「列里没有 events」当「本轮没跑腿」就是用缺证词当证据，本件禁止这一读）、无可 join 的
``tool_calls``、以及「腿跑过却只到一枚帧」（`dropped>0` 那一族：片到过收端却被
``_AnswerPieceStream.frame_for`` 折掉，SSE 上不留证词 —— 与「零片」离线不可分，见 r506 §2.A 第 8 条）。

## 两读并列（计划书 §6 追加节：不许只印其中一格）

* **读 1 · ②原文全分母**：run9 = ``94/105``。本件**不自己实现②**，逐行调
  ``audit.judge_row``，所以这一读与 ``scripts/r239_stream_gap_offline_audit.py`` 逐字同代同数；
  合格线 ``text_frames > 1`` 也在 ``audit.event_count_gt_1`` 里，本件一枚键都没添。
* **读 2 · 甲案分腿读**：分母 = 机械派生出「确有逐片腿」的行，另给两枚分子（②原文两格 / ②原文 ∧
  账上 ``criterion_two_holds``），并把 ``not_applicable`` / ``no_answer`` / ``self_added_cell_only`` /
  ``undecidable`` 四格逐枚点名。

用法：
    python scripts/r518_a2_lane_attribution.py
    python scripts/r518_a2_lane_attribution.py --frames docs/testing/sidecar-run7-frames.jsonl ^
        --sidecar docs/testing/sidecar-run7.jsonl --answers docs/testing/answers-run7.jsonl
    python scripts/r518_a2_lane_attribution.py --format json
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import r239_stream_gap_offline_audit as audit  # noqa: E402  ②的两格与红因名单的唯一出处，本件不复制

DEFAULT_FRAMES = REPO_ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
DEFAULT_SIDECAR = REPO_ROOT / "docs" / "testing" / "sidecar-run9.jsonl"
DEFAULT_ANSWERS = REPO_ROOT / "docs" / "testing" / "answers-run9.jsonl"
NODES_SOURCE = REPO_ROOT / "app" / "agents" / "nodes.py"

#: 真尺替② 自加、而 A② 原文里没有的那一枚格（``extra_red_conditions`` 的点名串）。
#: 总控裁定：「不算进②原文，也不得据它宣布②红或②绿」⇒ 它单独占一格。
SELF_ADDED_CELL = "max_stream_frames>1"

#: 三态分明。🔴 没有第四枚取值，也没有「派生不出就当有腿」这一读。
#: 「天然短」（``REASON_BELOW_SIZE_GATE``）落 ``undecidable`` 而**不**落 ``no_piece_leg``：
#: 那一格说的是「这一轮攒不出第二枚帧」，不是「这一轮没有腿」——腿名今天仍派生不出。
HAS_PIECE_LEG = "has_piece_leg"
NO_PIECE_LEG = "no_piece_leg"
UNDECIDABLE = "undecidable"
LANE_STATES = (HAS_PIECE_LEG, NO_PIECE_LEG, UNDECIDABLE)

#: 甲案读的格子（每枚行只落一格，五格互斥且守恒）。
BUCKET_IN_SCOPE = "in_scope_has_leg"
BUCKET_NOT_APPLICABLE = "not_applicable"
BUCKET_NO_ANSWER = "no_answer"
BUCKET_SELF_ADDED = "self_added_cell_only"
BUCKET_UNDECIDABLE = "undecidable"
ALL_BUCKETS = (BUCKET_IN_SCOPE, BUCKET_NOT_APPLICABLE, BUCKET_NO_ANSWER,
               BUCKET_SELF_ADDED, BUCKET_UNDECIDABLE)

#: 落格理由（``reason``）的在册名单：读表的人靠它区分「无腿」与「天然短」，不许并脸。
REASON_NO_PIECE_LEG = "no_piece_leg_witness"
REASON_BELOW_SIZE_GATE = "below_size_gate"
REASON_QUEUE_PATH = "queue_path_no_sink"
REASON_NO_ANSWER = "no_text_frame_at_all"
REASON_NO_ARRIVAL = "no_arrival_coordinates"
REASON_NO_TOOL_CALLS = "no_tool_calls_join"
REASON_DROP_OR_ZERO_PIECE = "piece_or_drop_indistinguishable"
REASON_FRAMES_NO_ACCUMULATION = "frames_without_per_stream_accumulation"
#: R223 逐帧那一列（``frames``）自己重算出来的流数/最大帧数与账上汇总格**对不上**：
#: 汇总格被改过（或两列不同代）。⇒ 有腿证词不成立，落「派生不出」并当场点名。
REASON_WITNESS_CONFLICT = "witness_conflict_on_frames"
ALL_REASONS = (REASON_NO_PIECE_LEG, REASON_BELOW_SIZE_GATE, REASON_QUEUE_PATH,
               REASON_NO_ANSWER, REASON_NO_ARRIVAL, REASON_NO_TOOL_CALLS,
               REASON_DROP_OR_ZERO_PIECE, REASON_FRAMES_NO_ACCUMULATION,
               REASON_WITNESS_CONFLICT)

#: 本件读到的键 —— 🔴 一枚都不是新键（帧账/sidecar 今天就有），名单在册钉在
#: ``tests/test_r518_a2_lane_attribution.py``，防的就是「为了派生去给帧账加一格」。
FRAME_KEYS_USED = ("id", "kind", "text_frames", "max_stream_frames", "streams",
                   "per_stream", "answer_chars", "events", "queue", "attempt",
                   "criterion_two_holds", "frames")
SIDECAR_KEYS_USED = ("id", "tool_calls", "attempt")

#: 帧账里那枚「有没有工作腿跑过工具」的证词事件名（R223 起 ``events`` 才在账上）。
STEP_EVENT = "step"


class SizeGateError(ValueError):
    """尺寸闸的数值从真源读不出来 —— 宁可拒绝出数，不拿一个手抄的 20 冒充在册。"""


def piece_size_gate(path=NODES_SOURCE):
    """``STREAM_PIECE_MIN_CHARS`` —— 从 ``app/agents/nodes.py`` 现取，不抄第二份。"""
    try:
        text = io.open(str(path), encoding="utf-8").read()
    except OSError as error:
        raise SizeGateError("尺寸闸真源读不到：" + str(path) + "（" + str(error) + "）")
    match = re.search(r"^STREAM_PIECE_MIN_CHARS\s*=\s*(\d+)", text, re.MULTILINE)
    if match is None:
        raise SizeGateError("尺寸闸真源里取不到 STREAM_PIECE_MIN_CHARS：" + str(path))
    return int(match.group(1))


def rows_by_id(path, required=()):
    """读一本 jsonl 账，按题号收行；同题多轮取 ``attempt`` 最大的那一行。

    🔴 帧账走 ``audit.read_rows``：它缺判② 必读键就 raise（判器宁可拒判，不静默补零），
    本件不绕这道闸。
    """
    path = Path(path)
    if not path.is_file():
        return None, 0
    if required:
        raw = audit.read_rows(path)
    else:
        raw = []
        with io.open(str(path), encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    raw.append(json.loads(line))
    best = {}
    collapsed = 0
    for row in raw:
        key = str(row.get("id", ""))
        previous = best.get(key)
        if previous is None:
            best[key] = row
            continue
        collapsed += 1
        if int(row.get("attempt") or 0) >= int(previous.get("attempt") or 0):
            best[key] = row
    return best, collapsed


def _tool_calls_of(frame_row, sidecar, answers):
    """``tool_calls`` 的取法：sidecar 优先，回退 answers；两处都没有 ⇒ ``None``（不是 0）。"""
    for book in (sidecar, answers):
        if not book:
            continue
        row = book.get(str(frame_row.get("id", "")))
        if row is not None and "tool_calls" in row:
            value = row.get("tool_calls")
            if value is None:
                return None, None
            return int(value), ("sidecar" if book is sidecar else "answers")
    return None, None


def _is_queue_path(row):
    if str(row.get("kind", "")).startswith("queued"):
        return True
    queue = row.get("queue")
    return isinstance(queue, dict) and bool(queue)


def _event_names(row):
    events = row.get("events")
    if not isinstance(events, list):
        return None
    return set(str(item.get("event")) for item in events if isinstance(item, dict))


def _stream_frame_max(row):
    per_stream = row.get("per_stream") or []
    frames = [int(item.get("frames") or 0) for item in per_stream if isinstance(item, dict)]
    return max(frames) if frames else 0


def frames_recount(row):
    """从 R223 逐帧那一列自己重算 (流数, 单流最大帧数)；那一列缺失或为空 ⇒ 交回 ``None``。

    🔴 这是「有腿」那枚正面证词的**对质件**：``max_stream_frames`` 是一枚汇总格，谁都能改一个
    数字；逐帧那一列要改就得连改一串带 ``at``/``stream``/``chars``/``sha`` 的记录。两列对不上
    ⇒ 汇总格的证词不算数（本件不据它宣布有腿）。
    """
    records = row.get("frames")
    if not isinstance(records, list) or not records:
        return None
    per_stream = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        stream = int(record.get("stream") or 0)
        per_stream[stream] = per_stream.get(stream, 0) + 1
    if not per_stream:
        return None
    return len(per_stream), max(per_stream.values())


def witness_conflict(row):
    """汇总格与逐帧列对质：对得上交回 ``None``，对不上交回一句证词。"""
    recounted = frames_recount(row)
    if recounted is None:
        return None
    streams, max_frames = recounted
    booked_streams = int(row.get("streams") or 0)
    booked_max = int(row.get("max_stream_frames") or 0)
    if max_frames == booked_max and streams == booked_streams:
        return None
    return ("frames 列重算=(streams=" + str(streams) + ", max_stream_frames=" + str(max_frames)
            + ") 而账上汇总格=(streams=" + str(booked_streams) + ", max_stream_frames="
            + str(booked_max) + ") ⇒ 两列不同代或汇总格被改过，有腿证词不算数")


def derive_lane_state(row, tool_calls, min_chars, tool_calls_book=None):
    """从**既有键**派生这一轮的腿状态。交回三态 + 理由 + 证词（哪一枚键的哪个取值）。"""
    text_frames = int(row.get("text_frames") or 0)
    max_stream_frames = int(row.get("max_stream_frames") or 0)
    answer_chars = int(row.get("answer_chars") or 0)
    names = _event_names(row)
    keys = ["text_frames=" + str(text_frames), "max_stream_frames=" + str(max_stream_frames)]

    if text_frames == 0:
        if _is_queue_path(row):
            return {
                "lane_state": NO_PIECE_LEG, "reason": REASON_QUEUE_PATH,
                "evidence": ["kind=" + str(row.get("kind")) + "，queue 格非空"
                             " ⇒ 本轮终答不走 SSE 文本帧，队列道明文没有 sink"],
                "keys_used": keys + ["kind", "queue"]}
        return {
            "lane_state": UNDECIDABLE, "reason": REASON_NO_ANSWER,
            "evidence": ["text_frames==0 ⇒ 一帧文本都没发过，腿之有无无从谈起（本轮没交付终答）"],
            "keys_used": keys}

    # 正面证词先过一道对质：汇总格与逐帧列必须同代同数。
    conflict = witness_conflict(row)
    if conflict:
        return {
            "lane_state": UNDECIDABLE, "reason": REASON_WITNESS_CONFLICT,
            "evidence": [conflict, "text_frames=" + str(text_frames)
                         + "：本件不据一枚对不上账的汇总格宣布有腿，也不据它宣布无腿"],
            "keys_used": keys + ["frames", "streams"]}
    if max_stream_frames > 1:
        return {
            "lane_state": HAS_PIECE_LEG, "reason": "",
            "evidence": ["max_stream_frames=" + str(max_stream_frames)
                         + " > 1 ⇒ 有一条流自己攒出第二枚文本帧，只有 sink 在逐片喂它才做得到"
                         "（per_stream 最大帧数=" + str(_stream_frame_max(row)) + "）"],
            "keys_used": keys + ["per_stream", "streams"]}

    if text_frames > 1:
        return {
            "lane_state": UNDECIDABLE, "reason": REASON_FRAMES_NO_ACCUMULATION,
            "evidence": ["text_frames=" + str(text_frames) + " 而 max_stream_frames="
                         + str(max_stream_frames) + " ⇒ 多枚帧分属多条流，没有任何一条流在逐片累计"
                         "：既没有有腿证词，也不足以断言无腿"],
            "keys_used": keys + ["per_stream", "streams"]}

    # text_frames == 1：一帧到位。先问结构性证词，再问尺寸闸。
    if _is_queue_path(row):
        return {
            "lane_state": NO_PIECE_LEG, "reason": REASON_QUEUE_PATH,
            "evidence": ["text_frames==1 且走队列道（kind=" + str(row.get("kind"))
                         + " / queue 格非空）⇒ 队列道明文无 sink"],
            "keys_used": keys + ["kind", "queue"]}
    if names is None:
        return {
            "lane_state": UNDECIDABLE, "reason": REASON_NO_ARRIVAL,
            "evidence": ["帧账不带 events 列（R223 并树之前的账）⇒ 「有没有跑过腿」这件事"
                         "在这扇窗里从没记过；🔴 拿「列不存在」当「没跑腿」就是用缺证词当证据"],
            "keys_used": keys + ["events(缺)"]}
    if tool_calls is None:
        return {
            "lane_state": UNDECIDABLE, "reason": REASON_NO_TOOL_CALLS,
            "evidence": ["sidecar／answers 两本账都 join 不到 tool_calls ⇒ 无腿判据的正面证词"
                         "缺一枚，本件不猜（🔴 也不当 0）"],
            "keys_used": keys + ["events", "tool_calls(缺)"]}
    if int(tool_calls) == 0 and STEP_EVENT not in names:
        return {
            "lane_state": NO_PIECE_LEG, "reason": REASON_NO_PIECE_LEG,
            "evidence": ["text_frames==1 ∧ " + str(tool_calls_book) + ".tool_calls==0 ∧ events 一枚 "
                         + STEP_EVENT + " 都没有 ⇒ 本轮没有工作腿跑过工具，终答由无 sink 路径"
                         "一次性交付（answer_chars=" + str(answer_chars) + "）"],
            "keys_used": keys + ["events", "tool_calls", "answer_chars"]}
    if answer_chars < min_chars:
        return {
            # 这一格问的不是「有没有腿」，而是「这一轮可能长出第二枚帧吗」：
            # 尺寸闸这一路不可能（攒不到 20 字就不成片），只剩空档闸那一条（模型中途停手
            # >=100 ms 且过 4 字地板）能出第二枚 —— 腿名照旧派生不出，所以三态里落 undecidable。
            "lane_state": UNDECIDABLE, "reason": REASON_BELOW_SIZE_GATE,
            "evidence": ["answer_chars=" + str(answer_chars) + " < 尺寸闸 " + str(min_chars)
                         + "（STREAM_PIECE_MIN_CHARS）⇒ 按 §2.7「>=20 字或 100 ms 合并」，"
                           "尺寸闸这一路出不了第二片；只剩空档闸（停手 >=100 ms 且过 "
                           "STREAM_PIECE_STALL_FLOOR_CHARS 地板）这一条，那是契约不是丢字"
                         + "（腿是否白名单腿仍派生不出：tool_calls=" + str(tool_calls)
                         + " 来自 " + str(tool_calls_book) + "，events 含 step=" + str(STEP_EVENT in names) + "）"],
            "keys_used": keys + ["events", "tool_calls", "answer_chars"]}
    return {
        "lane_state": UNDECIDABLE, "reason": REASON_DROP_OR_ZERO_PIECE,
        "evidence": ["腿跑过（tool_calls=" + str(tool_calls) + "，events 含 " + STEP_EVENT
                     + "）却只到一枚文本帧，且 answer_chars=" + str(answer_chars)
                     + " ≥ 尺寸闸 ⇒ 「非白名单腿」与「片到过收端被 frame_for 折掉（dropped>0）」"
                     "在 SSE 账上不可分（r506 §2.A 第 8 条），本件不替产品挑一枚"],
        "keys_used": keys + ["events", "tool_calls", "answer_chars"]}


#: 落 ``not_applicable`` 的理由（A② 的分母之外，但必须另立一格可见）。
NOT_APPLICABLE_REASONS = (REASON_NO_PIECE_LEG, REASON_BELOW_SIZE_GATE, REASON_QUEUE_PATH)


def _bucket_of(row, lane, judged, min_chars):
    """落格：五格互斥、守恒。顺序写死，🔴 改序就是把某一格抹进另一格的读法。"""
    text_frames = int(row.get("text_frames") or 0)
    reason = lane["reason"]
    if reason in NOT_APPLICABLE_REASONS:
        return BUCKET_NOT_APPLICABLE
    if text_frames == 0:
        return BUCKET_NO_ANSWER
    if lane["lane_state"] == HAS_PIECE_LEG:
        return BUCKET_IN_SCOPE
    if (text_frames > 1
            and set(judged["extra_red_conditions"]) <= {SELF_ADDED_CELL}):
        # chart-01 那一族：严读只红在量具自加的格 ⇒ 单列，不参红绿。
        return BUCKET_SELF_ADDED
    return BUCKET_UNDECIDABLE


def attribute(frames_path, sidecar_path=None, answers_path=None, min_chars=None):
    """主流程：读三本账 ⇒ 逐枚派生腿状态 ⇒ 出两读并列的读数。只读，读完复核 sha256。"""
    frames_path = Path(frames_path)
    sidecar_path = None if sidecar_path is None else Path(sidecar_path)
    answers_path = None if answers_path is None else Path(answers_path)
    if min_chars is None:
        min_chars = piece_size_gate()

    digests = {str(p): (audit.sha256_of(p) if p and p.is_file() else None)
               for p in (frames_path, sidecar_path, answers_path)}
    frames, frames_collapsed = rows_by_id(frames_path, required=True)
    sidecar, _ = rows_by_id(sidecar_path) if sidecar_path else (None, 0)
    answers, _ = rows_by_id(answers_path) if answers_path else (None, 0)

    rows = []
    for row_id in sorted(frames):
        row = frames[row_id]
        judged = audit.judge_row(row)
        tool_calls, book = _tool_calls_of(row, sidecar, answers)
        lane = derive_lane_state(row, tool_calls, min_chars, tool_calls_book=book)
        bucket = _bucket_of(row, lane, judged, min_chars)
        literal = bool(judged["verdict"])
        archived = bool(judged["ledger_criterion_two_holds"])
        rows.append({
            "id": row_id, "kind": str(row.get("kind", "")),
            "bucket": bucket, "lane_state": lane["lane_state"], "reason": lane["reason"],
            "evidence": lane["evidence"], "keys_used": lane["keys_used"],
            "text_frames": judged["text_frames"],
            "max_stream_frames": judged["max_stream_frames"],
            "streams": judged["streams"],
            "answer_chars": judged["answer_chars"],
            "tool_calls": tool_calls, "tool_calls_book": book,
            "criterion_two_literal": literal,
            "criterion_two_holds_archived": archived,
            "recomputed_ledger": judged["recomputed_ledger"],
            "ledger_drift": bool(judged["ledger_drift"]),
            "extra_red_conditions": judged["extra_red_conditions"],
            "event_form": judged["event_form"],
            "in_scope_strict_red": (bucket == BUCKET_IN_SCOPE and not (literal and archived)),
            "not_rejudged": (bucket == BUCKET_IN_SCOPE and bool(judged["ledger_drift"])),
        })

    # 逐枚点名用的两枚小工具（分格、分格再分理由）。
    def bucketed(bucket, reason=None):
        return sorted(item["id"] for item in rows
                      if item["bucket"] == bucket
                      and (reason is None or item["reason"] == reason))

    total = len(rows)
    literal_green = sum(1 for item in rows if item["criterion_two_literal"])
    in_scope = [item for item in rows if item["bucket"] == BUCKET_IN_SCOPE]
    undecidable_literal_red = sorted(item["id"] for item in rows
                                     if item["bucket"] == BUCKET_UNDECIDABLE
                                     and not item["criterion_two_literal"])
    self_added = bucketed(BUCKET_SELF_ADDED)
    not_applicable = bucketed(BUCKET_NOT_APPLICABLE)
    no_answer = bucketed(BUCKET_NO_ANSWER)
    undecidable = bucketed(BUCKET_UNDECIDABLE)
    conserved = (len(in_scope) + len(not_applicable) + len(no_answer)
                 + len(self_added) + len(undecidable) == total)

    after = {str(p): (audit.sha256_of(p) if p and p.is_file() else None)
             for p in (frames_path, sidecar_path, answers_path)}
    return {
        "inputs": {"frames": str(frames_path), "sidecar": str(sidecar_path or ""),
                   "answers": str(answers_path or ""),
                   "sha256_before": digests, "sha256_after": after,
                   "inputs_unchanged": digests == after,
                   "rows": total, "attempts_collapsed": frames_collapsed,
                   "sidecar_rows": 0 if not sidecar else len(sidecar),
                   "answers_rows": 0 if not answers else len(answers),
                   "rows_with_tool_calls": sum(1 for item in rows
                                               if item["tool_calls"] is not None)},
        "size_gate": {"stream_piece_min_chars": min_chars,
                      "source": str(NODES_SOURCE.relative_to(REPO_ROOT)).replace("\\", "/")},
        "literal_read": {
            "denominator": total,
            "green": literal_green,
            "red": sorted(item["id"] for item in rows if not item["criterion_two_literal"]),
            "gate": "②-a text_frames > 1（audit.event_count_gt_1）∧ ②-b 逐字无缺",
            "authority": "scripts/r239_stream_gap_offline_audit.py::judge_row",
        },
        "plan_a_read": {
            "denominator": len(in_scope),
            "green_literal_two_cells": sum(1 for item in in_scope if item["criterion_two_literal"]),
            "green_literal_two_cells_ids": sorted(item["id"] for item in in_scope
                                                  if item["criterion_two_literal"]),
            "red_literal_two_cells": sorted(item["id"] for item in in_scope
                                            if not item["criterion_two_literal"]),
            "green_strict": sum(1 for item in in_scope
                                if item["criterion_two_literal"]
                                and item["criterion_two_holds_archived"]),
            "green_strict_ids": sorted(item["id"] for item in in_scope
                                       if item["criterion_two_literal"]
                                       and item["criterion_two_holds_archived"]),
            "red_strict": sorted(item["id"] for item in in_scope
                                 if not (item["criterion_two_literal"]
                                         and item["criterion_two_holds_archived"])),
            "buckets": {
                BUCKET_IN_SCOPE: sorted(item["id"] for item in in_scope),
                BUCKET_NOT_APPLICABLE: {
                    "total": len(not_applicable), "ids": not_applicable,
                    REASON_NO_PIECE_LEG: bucketed(BUCKET_NOT_APPLICABLE, REASON_NO_PIECE_LEG),
                    REASON_BELOW_SIZE_GATE: bucketed(BUCKET_NOT_APPLICABLE, REASON_BELOW_SIZE_GATE),
                    REASON_QUEUE_PATH: bucketed(BUCKET_NOT_APPLICABLE, REASON_QUEUE_PATH)},
                BUCKET_NO_ANSWER: {"ids": no_answer},
                BUCKET_SELF_ADDED: {"ids": self_added},
                BUCKET_UNDECIDABLE: {"ids": undecidable, "literal_red": undecidable_literal_red},
            },
            "conservation": {
                "equation": "rows = in_scope + not_applicable + no_answer + self_added + undecidable",
                "rows": total, BUCKET_IN_SCOPE: len(in_scope),
                BUCKET_NOT_APPLICABLE: len(not_applicable), BUCKET_NO_ANSWER: len(no_answer),
                BUCKET_SELF_ADDED: len(self_added), BUCKET_UNDECIDABLE: len(undecidable),
                "holds": conserved},
            "not_rejudged": {"ids": sorted(item["id"] for item in rows if item["not_rejudged"]),
                             "rule": "账与尺不同代（R471 在册纪律）：不追加定罪也不裁绿"},
            "witness_conflict": {
                "ids": sorted(item["id"] for item in rows
                              if item["reason"] == REASON_WITNESS_CONFLICT),
                "rule": "max_stream_frames 与 frames 逐帧列对不上 ⇒ 不据汇总格宣布有腿"},
            "leg_names": {"derivable_rows": 0, "rows": total,
                          "note": "帧账一行没有 worker/腿名列（eval_transport_ask_v2._frame_readings "
                                  "的返回值里没有）⇒ 腿名派生不出，本件只断言 sink 腿之有无"},
        },
        "rows": rows,
    }


def _fmt_ids(ids, limit=16):
    ids = list(ids)
    if not ids:
        return "—"
    if len(ids) <= limit:
        return ",".join(ids)
    return ",".join(ids[:limit]) + ",…(共 " + str(len(ids)) + " 枚)"


def render(result, verbose_rows=False):
    lines = []
    inputs = result["inputs"]
    lines.append("帧账：" + inputs["frames"] + "  sidecar=" + (inputs["sidecar"] or "无")
                 + "  answers=" + (inputs["answers"] or "无"))
    lines.append("sha256 读前=" + json.dumps(inputs["sha256_before"], ensure_ascii=False)
                 + " 读后=" + json.dumps(inputs["sha256_after"], ensure_ascii=False)
                 + " 未改动=" + str(inputs["inputs_unchanged"]))
    lines.append("行数=" + str(inputs["rows"]) + "（重试折叠 "
                 + str(inputs["attempts_collapsed"]) + "）｜ tool_calls 可判行="
                 + str(inputs["rows_with_tool_calls"]) + "｜尺寸闸="
                 + str(result["size_gate"]["stream_piece_min_chars"])
                 + "（" + result["size_gate"]["source"] + "）")
    lines.append("")

    literal = result["literal_read"]
    lines.append("== 读 1 · ②原文全分母（历史可比那把尺；件=" + literal["authority"] + "）")
    lines.append("   绿 " + str(literal["green"]) + "/" + str(literal["denominator"])
                 + "  红 " + str(len(literal["red"])) + " 枚：" + _fmt_ids(literal["red"]))
    lines.append("   合格线：" + literal["gate"])
    lines.append("")

    plan = result["plan_a_read"]
    cons = plan["conservation"]
    lines.append("== 读 2 · 甲案分腿读（计划书 §6 追加节 09-29 裁定：②只适用于确有逐片腿的轮）")
    lines.append("   分母算式：" + cons["equation"])
    lines.append("   " + str(cons["rows"]) + " = " + BUCKET_IN_SCOPE + " "
                 + str(cons[BUCKET_IN_SCOPE]) + " + " + BUCKET_NOT_APPLICABLE + " "
                 + str(cons[BUCKET_NOT_APPLICABLE]) + " + " + BUCKET_NO_ANSWER + " "
                 + str(cons[BUCKET_NO_ANSWER]) + " + " + BUCKET_SELF_ADDED + " "
                 + str(cons[BUCKET_SELF_ADDED]) + " + " + BUCKET_UNDECIDABLE + " "
                 + str(cons[BUCKET_UNDECIDABLE]) + "  守恒=" + str(cons["holds"]))
    lines.append("   · 甲案②原文两格读：" + str(plan["green_literal_two_cells"]) + "/"
                 + str(plan["denominator"]) + "  红=" + (_fmt_ids(plan["red_literal_two_cells"])))
    lines.append("   · 甲案严读（②原文 ∧ 账上 criterion_two_holds）：" + str(plan["green_strict"])
                 + "/" + str(plan["denominator"]) + "  红="
                 + (_fmt_ids(plan["red_strict"]) or "无"))
    buckets = plan["buckets"]
    na = buckets[BUCKET_NOT_APPLICABLE]
    lines.append("   格子逐枚点名：")
    lines.append("   [" + BUCKET_NOT_APPLICABLE + "/无逐片腿] " + str(len(na[REASON_NO_PIECE_LEG]))
                 + " 枚：" + _fmt_ids(na[REASON_NO_PIECE_LEG]))
    lines.append("   [" + BUCKET_NOT_APPLICABLE + "/短过尺寸闸] "
                 + str(len(na[REASON_BELOW_SIZE_GATE])) + " 枚："
                 + _fmt_ids(na[REASON_BELOW_SIZE_GATE]))
    lines.append("   [" + BUCKET_NOT_APPLICABLE + "/队列道] "
                 + str(len(na[REASON_QUEUE_PATH])) + " 枚：" + _fmt_ids(na[REASON_QUEUE_PATH]))
    lines.append("   [" + BUCKET_NO_ANSWER + "] " + str(len(buckets[BUCKET_NO_ANSWER]["ids"]))
                 + " 枚：" + _fmt_ids(buckets[BUCKET_NO_ANSWER]["ids"]))
    lines.append("   [" + BUCKET_SELF_ADDED + "] " + str(len(buckets[BUCKET_SELF_ADDED]["ids"]))
                 + " 枚：" + _fmt_ids(buckets[BUCKET_SELF_ADDED]["ids"])
                 + "  （" + SELF_ADDED_CELL + " 是量具自加的格，不参红绿）")
    und = buckets[BUCKET_UNDECIDABLE]
    lines.append("   [" + BUCKET_UNDECIDABLE + "] " + str(len(und["ids"])) + " 枚："
                 + _fmt_ids(und["ids"]))
    conflict_ids = plan["witness_conflict"]["ids"]
    lines.append("   [有腿证词与逐帧列对质不上] " + str(len(conflict_ids)) + " 枚："
                 + _fmt_ids(conflict_ids) + " —— " + plan["witness_conflict"]["rule"])
    if und["literal_red"]:
        lines.append("   🔴 派生不出而②原文仍红：" + str(len(und["literal_red"])) + " 枚："
                     + _fmt_ids(und["literal_red"]) + " ⇒ 本件不裁绿，这些行照旧占在册红账")
    lines.append("   不重判（" + plan["not_rejudged"]["rule"] + "）：" + _fmt_ids(plan["not_rejudged"]["ids"]))
    lines.append("   腿名可派生行数：" + str(plan["leg_names"]["derivable_rows"]) + "/"
                 + str(plan["leg_names"]["rows"]) + " —— " + plan["leg_names"]["note"])
    lines.append("   （与读 1 的差别只在不适用/无答/单列/派生不出那几格；🔴 两读并列，不许只印一格）")

    if verbose_rows:
        lines.append("")
        lines.append("== 逐枚派生（id / bucket / lane / reason / 证词）")
        for item in result["rows"]:
            lines.append("%-14s %-20s %-13s %-38s %s" % (
                item["id"], item["bucket"], item["lane_state"], item["reason"] or "-",
                " ｜ ".join(item["evidence"])))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="R518 A② 甲案的机械落地（只读；有逐片腿/无逐片腿/派生不出 三态分明）")
    parser.add_argument("--frames", default=str(DEFAULT_FRAMES))
    parser.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    parser.add_argument("--answers", default=str(DEFAULT_ANSWERS))
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--rows", action="store_true", help="连逐枚派生一起打")
    parser.add_argument("--fail-on-unchanged", action="store_true",
                        help="输入账本读完被改动就 exit 2（在册原件自证）")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        result = attribute(args.frames, args.sidecar, args.answers)
    except (audit.LedgerSchemaError, SizeGateError) as error:
        print("REJECTED " + str(error), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result, verbose_rows=args.rows))
    if args.fail_on_unchanged and not result["inputs"]["inputs_unchanged"]:
        return 2
    if not result["inputs"]["inputs_unchanged"]:
        print("🔴 输入账本字节在读取前后不一致 —— 本件应当零写入", file=sys.stderr)
        return 2
    if not result["plan_a_read"]["conservation"]["holds"]:
        print("🔴 五格不守恒：有行没落格或有行落了两格", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
