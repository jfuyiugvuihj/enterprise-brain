# -*- coding: utf-8 -*-
"""R565 —— 把 V1 门 A② 那格的**分母**拆成可判的桶，逐题归账，只交数不交结论。

===== 这一格今天为什么读不动 =====

在册判器 ``scripts/r239_stream_gap_offline_audit.py``（符号 ``judge_row`` / ``summarize``）
对 run9 那 105 枚的②读数是一枚绿一枚红的合数（本件不把纸上那两个数抄进代码：甲口径与 ``r239.summarize`` 现算逐字可比）。
可那一格的红里混着四件完全不同的事：
天然短（一题的终答本来就短过尺寸闸，攒不出第二枚帧）、无逐片腿（那一枚帧与
``request.completed`` 同一毫秒到达 ⇒ 整段在收尾那一刻才发出来）、预制句（终答压根不是
产品吐的正文，是 ``no_answer_produced`` 那一族的占位串），以及「本轮确实该有逐片流却没做到」。
把这四件摊进同一个分母，A② 就永远读不干净：所以本件只改**分母的呈现**，
不改② 的判据一个字。

===== 本件不复制任何一把尺（逐条点名） =====

* ② 的两格与合取：``scripts/r239_stream_gap_offline_audit.py`` 的 ``event_count_gt_1`` /
  ``char_by_char_no_loss`` / ``judge_row``（写本件时现取分别在该文件 :174 / :179 / :273）。
  本件 ``import r239_stream_gap_offline_audit as audit`` 直接调用，**一个判据都不重写**。
* 帧账那七格与「同题多轮取最大 attempt」：``scripts/r518_a2_lane_attribution.py`` 的
  ``rows_by_id``（:136）与 ``_tool_calls_of``（:168）—— sidecar 优先、回退 answers、
  两处都没有 ⇒ ``None``（🔴 不是 0）。
* 尺寸闸 ``STREAM_PIECE_MIN_CHARS``：``r518.piece_size_gate()``（:124）从
  ``app/agents/nodes.py`` 现取（写本件时该行是 ``433:STREAM_PIECE_MIN_CHARS = 20``，
  但本件不落这个数——落进代码就成第二份）。取不到 ⇒ ``SizeGateError`` 当场抛。
* 短指纹口径：``scripts/eval_transport_ask_v2.py`` 的 ``_sha12``（:401）＝
  ``sha256(text.encode("utf-8")).hexdigest()[:12]``；``answer_sha`` 由同一文件的
  :774 那枚 ``"answer_sha": _sha12(answer)`` 落账。本件按同一式子算**串**，
  串本身从真源现取（下一条），并拿账上的逐字文本对质（口径漂移由 ``check_prefab_fingerprints`` 拦）。
* 预制句真源：``app/api/v1/chat.py`` 里赋给 ``failure_text`` 的那一枚字面（写本件时 :2937，
  符号 ``failure_text``；它的下一行 ``_save_message`` 把它写进会话历史，``sse_event("error", …)``
  把它发成 content ⇒ 它就是那两题的「终答」）；哨兵两枚取自采集器默认字面
  ``BLANK_SENTINEL``（:205）与 ``APPROVAL_FAILED_SENTINEL``（:222）。

===== 四桶（定义照 R506 的定性；互斥、守恒、逐枚带证词） =====

    B3 预制句    answer_sha ∈ 现取的预制串指纹集合
    B2 无逐片腿 text_frames == 1 ∧ 那一枚帧与 request.completed 同一毫秒到达
    B1 天然短   tool_calls == 0（真值 0；None 不算）∧ answer_chars < STREAM_PIECE_MIN_CHARS
    B0 其余     这一格才是「本轮应当有逐片流」的分母

🔴 优先级 B3 > B2 > B1 是**呈现顺序**，不是新判据：三格今天能同时命中同一题
（一枚 15 字的预制句既短又只一帧）。本件把每一枚命中过的格都留在 ``also_matched`` 里，
一格都不许蒸发；谁想改优先级，改的是这张表的归账，不是② 的读数。

===== 三口径（本件不替总控选，三档都交） =====

    甲 = 105 全分母            —— 与 r239 的在册读法逐字可比
    乙 = B0 作分母 + 三格并列报数 —— 拆完还看得见被拆出去的那几枚是谁
    丙 = 只报 B0，不提其余三格   —— 只许出数；据它宣布 A② 翻绿 ⇒ declare() 当场拒（见 CaliberError）

===== 纪律 =====

只读：本件对三本账一律以只读方式打开，一个字节都不写（常驻反证
``test_counter_evidence_*`` 里有一枚拿 ``open`` 记账验这件事）。不打模型、不开容器、不起服务。
"""

import argparse
import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import r239_stream_gap_offline_audit as audit  # noqa: E402  ② 的两格唯一出处，本件不复制
import r518_a2_lane_attribution as lane  # noqa: E402  尺寸闸现取 + 读账把手，本件不复制

#: 默认靶 = run9（在册 ② 读数出处的那一窗，三本账都在仓内）。那两枚数本件不抄进代码：
#: 甲口径与 ``r239.summarize`` 现算逐字可比，钉里同样不落任何一枚数字。
DEFAULT_FRAMES = REPO_ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
DEFAULT_SIDECAR = REPO_ROOT / "docs" / "testing" / "sidecar-run9.jsonl"
DEFAULT_ANSWERS = REPO_ROOT / "docs" / "testing" / "answers-run9.jsonl"
CHAT_SOURCE = REPO_ROOT / "app" / "api" / "v1" / "chat.py"
HARNESS_SOURCE = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"

#: 在册分母：105 题（run9 起判据范围＝全 105 枚，见 docs/testing/run9-readout-2026-09-28.md 的
#: 「A② 的判据范围 = 全 105 枚」那一格；本件把它当**对账尺**而不是当结论）。
DENOMINATOR_IN_BOOK = 105

B0, B1, B2, B3 = "B0", "B1", "B2", "B3"
BUCKET_NAMES = {
    B0: "B0 其余（本轮应当有逐片流：分母）",
    B1: "B1 天然短（tool_calls==0 且终答短过尺寸闸）",
    B2: "B2 无逐片腿（text_frames==1 且与 request.completed 同毫秒）",
    B3: "B3 预制句（answer_sha 命中现取的预制串指纹）",
}
BUCKET_ORDER = (B0, B1, B2, B3)
#: 归账顺序（呈现用）；🔴 不是判据，命中过的格全部留在 also_matched。
BUCKET_PRIORITY = (B3, B2, B1)

CALIBER_A = "甲"
CALIBER_B = "乙"
CALIBER_C = "丙"
CALIBERS = (CALIBER_A, CALIBER_B, CALIBER_C)

#: 逐题表要落进「依据读数」的原始键（一枚都不新造，全是帧账/sidecar 今天已有的键）。
FRAME_KEYS_USED = ("id", "kind", "attempt", "text_frames", "answer_chars", "answer_sha",
                   "frames", "events", "streams", "max_stream_frames")
SIDECAR_KEYS_USED = ("id", "tool_calls", "answer_chars", "sentinel")

class PrefabSourceError(ValueError):
    """预制串真源里读不出那几枚字面 —— 宁可拒绝出数，不拿一枚手抄的指纹冒充在册。"""


class FingerprintDriftError(ValueError):
    """现算的短指纹与账上 ``answer_sha`` 对不上 ⇒ 本件的口径与落账那把尺不同代。"""


class CaliberError(ValueError):
    """口径不许这么用：拿丙口径宣布翻绿、乙口径不交三格、或分母里还红着几枚。"""


def _read_source(path):
    """按只读把一份源码读成 ``\n`` 口径的文本（``git show`` 是 LF、盘上是 CRLF，这里统一）。"""
    with io.open(str(path), encoding="utf-8") as handle:
        return handle.read().replace("\r\n", "\n")


def short_sha(text):
    """与 ``scripts/eval_transport_ask_v2.py`` 的 ``_sha12`` 同式：sha256 前 12 位。

    🔴 本件算的是**串**的指纹，串从真源现取；式子若与落账那把尺漂移，
    ``check_prefab_fingerprints`` 会拿账上的逐字文本对质并抛 ``FingerprintDriftError``。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def chat_prefab_texts(path=CHAT_SOURCE):
    """``app/api/v1/chat.py`` 里赋给 ``failure_text`` 的字面，逐枚现取（一枚都读不到就抛）。"""
    text = _read_source(path)
    found = re.findall(r"^[ \t]*failure_text[ \t]*=[ \t]*(['\"])(.*?)\1", text, re.MULTILINE)
    texts = [item[1] for item in found]
    if not texts:
        raise PrefabSourceError("在 " + str(path) + " 里认不出任何一枚 failure_text 字面："
                                "预制句这一格必须重新取证，不许拿历史指纹凑")
    return texts


def harness_sentinel_texts(path=HARNESS_SOURCE):
    """采集器两枚哨兵的**默认字面**（env 没覆时产品侧看到的就是它），按符号名现取。

    ``BLANK_SENTINEL`` = 零字节题的占位串；``APPROVAL_FAILED_SENTINEL`` = 批准没被接受/
    批准后仍无终答时的占位串。两枚都不是产品正文，所以都属「预制句」这一族。
    """
    text = _read_source(path)
    out = {}
    for symbol in ("BLANK_SENTINEL", "APPROVAL_FAILED_SENTINEL"):
        pattern = (r"^" + symbol + r"[ \t]*=[ \t]*os\.getenv\([ \t\n]*"
                   r'"([A-Z_]+)"[ \t\n]*,[ \t\n]*"([^"]*)"[ \t\n]*\)')
        match = re.search(pattern, text, re.MULTILINE)
        if match is None:
            raise PrefabSourceError("在 " + str(path) + " 里认不出 " + symbol +
                                    " 的 os.getenv(名, 默认字面) 形状：哨兵串这一格要重新取证")
        out[symbol] = match.group(2)
    return out


def prefab_fingerprints(chat_source=CHAT_SOURCE, harness_source=HARNESS_SOURCE):
    """现取的预制串指纹表：``sha12 -> {串, 出处符号, 族}``。集合为空 ⇒ 直接抛。"""
    table = {}
    for literal in chat_prefab_texts(chat_source):
        table[short_sha(literal)] = {"text": literal, "family": "no_answer_produced",
                                     "source": str(chat_source), "symbol": "failure_text"}
    for symbol, literal in harness_sentinel_texts(harness_source).items():
        table[short_sha(literal)] = {"text": literal, "family": "collector_sentinel",
                                     "source": str(harness_source), "symbol": symbol}
    if not table:
        raise PrefabSourceError("预制串指纹集合为空：这一格不许静默吞掉")
    return table


def check_prefab_fingerprints(rows_by_id, answers, fingerprints):
    """拿账上的逐字文本对质现算指纹：文本相等而指纹不等 ⇒ 口径不同代，当场抛。

    这一道闸保证「B3 靠 answer_sha 判」不是一句空话：指纹算错了不是少归几枚，而是拒绝出数。
    """
    confirmed = []
    for key, row in rows_by_id.items():
        answer_row = answers.get(key) if answers else None
        if answer_row is None:
            continue
        answer = answer_row.get("answer")
        if not isinstance(answer, str):
            continue
        for sha, entry in fingerprints.items():
            if answer != entry["text"]:
                continue
            booked = str(row.get("answer_sha", ""))
            if booked != sha:
                raise FingerprintDriftError(
                    key + " 的终答逐字等于现取的预制串（" + entry["symbol"] + "），但账上 "
                    "answer_sha=" + booked + " 而本件现算=" + sha +
                    " ⇒ 短指纹口径与落账那把尺不同代，本件拒绝出数")
            confirmed.append({"id": key, "sha": sha, "symbol": entry["symbol"],
                              "family": entry["family"]})
    return confirmed


def _arrival_ms(value):
    """到达时刻（``arrival_at``，秒）换算成整数毫秒格 —— 「同毫秒」的格就落在这里。"""
    return int(math.floor(float(value) * 1000.0))


def single_frame_witness(row):
    """``text_frames == 1`` 那一题的到达证词：那一枚帧与终局 ``request.completed`` 差多少。

    🔴 三种「读不出」分明，一律不许当成「不是 B2」蒙过去：
    * ``unmeasurable`` —— 这扇窗的账里没有 ``frames``/``events`` 两列（R223 并树之前的账，run6/run7 即此形）；
    * ``no_completed_event`` —— 有到达坐标但没有 ``request.completed`` 那一枚事件；
    * ``witness_conflict`` —— ``text_frames==1`` 而逐帧那一列的记录数不是 1 ⇒ 两列不同代。
    """
    frames = row.get("frames")
    events = row.get("events")
    if not isinstance(frames, list) or not isinstance(events, list) or not frames:
        return {"status": "unmeasurable", "delta_ms": None, "same_ms": None,
                "within_one_ms": None, "frame_arrival": None, "completed_arrival": None,
                "completed_events": (len(events) if isinstance(events, list) else None)}
    completed = [item for item in events
                 if isinstance(item, dict) and str(item.get("event")) == "request.completed"]
    if not completed:
        return {"status": "no_completed_event", "delta_ms": None, "same_ms": None,
                "within_one_ms": None, "frame_arrival": None, "completed_arrival": None,
                "completed_events": 0}
    if len(frames) != 1:
        return {"status": "witness_conflict", "delta_ms": None, "same_ms": None,
                "within_one_ms": None, "frame_arrival": None, "completed_arrival": None,
                "completed_events": len(completed), "frame_records": len(frames)}
    frame_at = frames[0].get("arrival_at")
    terminal = max((item for item in completed if item.get("arrival_at") is not None),
                   key=lambda item: float(item["arrival_at"]), default=None)
    if frame_at is None or terminal is None:
        return {"status": "unmeasurable", "delta_ms": None, "same_ms": None,
                "within_one_ms": None, "frame_arrival": frame_at,
                "completed_arrival": None, "completed_events": len(completed)}
    delta = float(frame_at) - float(terminal["arrival_at"])
    return {"status": "measured",
            "delta_ms": round(delta * 1000.0, 3),
            "same_ms": _arrival_ms(frame_at) == _arrival_ms(terminal["arrival_at"]),
            "within_one_ms": abs(delta) < 0.001,
            "frame_arrival": frame_at,
            "completed_arrival": terminal["arrival_at"],
            "completed_events": len(completed),
            "frame_record": {"at": frames[0].get("at"), "stream": frames[0].get("stream"),
                             "chars": frames[0].get("chars")}}

def tool_calls_of(frame_row, sidecar_rows, answer_rows):
    """``tool_calls`` 的取法整枚交给 ``r518._tool_calls_of``（sidecar 优先→answers→None）。

    本件不复制那三行判读：两处都没有就是 ``None``，🔴 不许当成 0（当成 0 就等于凭空多归 B1 几枚）。
    """
    return lane._tool_calls_of(frame_row, sidecar_rows, answer_rows)  # noqa: SLF001  同仓复用，不复制第二份


def bucket_of_row(row, tool_calls, gate, fingerprints, tool_calls_book=None):
    """这一题落哪一桶：三格逐枚现判，命中过的格全留下，最后按呈现优先级归账。"""
    text_frames = int(row.get("text_frames") or 0)
    answer_chars = int(row.get("answer_chars") or 0)
    answer_sha = str(row.get("answer_sha", ""))
    matched = []
    evidence = []

    prefab = fingerprints.get(answer_sha)
    if prefab is not None:
        matched.append(B3)
        evidence.append("B3 命中：answer_sha=" + answer_sha + " == 现取预制串指纹（族="
                        + prefab["family"] + "，出处=" + prefab["symbol"] + " @ "
                        + prefab["source"] + "，串长=" + str(len(prefab["text"])) + "）")
    else:
        evidence.append("B3 不命中：answer_sha=" + answer_sha + " 不在现取的 "
                        + str(len(fingerprints)) + " 枚预制指纹里")

    witness = single_frame_witness(row)
    if text_frames == 1:
        evidence.append("B2 读法：text_frames=1，帧到达=" + str(witness["frame_arrival"])
                        + "，request.completed 到达=" + str(witness["completed_arrival"])
                        + "，Δ=" + str(witness["delta_ms"]) + " ms，差<1ms="
                        + str(witness["within_one_ms"]) + "，ms 格相等=" + str(witness["same_ms"])
                        + "，该题 completed 事件枚数=" + str(witness["completed_events"])
                        + "（证词状态=" + witness["status"] + "）")
        if witness["within_one_ms"] is True:
            matched.append(B2)
    else:
        evidence.append("B2 不适用：text_frames=" + str(text_frames) + "（那一格要求恰为 1）")

    if tool_calls is None:
        evidence.append("B1 不可判：sidecar／answers 两本账都 join 不到 tool_calls ⇒ 缺不是 0；"
                        "answer_chars=" + str(answer_chars) + "，尺寸闸=" + str(gate))
    else:
        short = int(tool_calls) == 0 and answer_chars < gate
        evidence.append("B1 读法：tool_calls=" + str(tool_calls) + "（出自 " + str(tool_calls_book)
                        + "）∧ answer_chars=" + str(answer_chars) + " < 尺寸闸 " + str(gate)
                        + "（STREAM_PIECE_MIN_CHARS 现取）⇒ " + str(short))
        if short:
            matched.append(B1)

    bucket = next((item for item in BUCKET_PRIORITY if item in matched), B0)
    return {"id": str(row.get("id", "")), "kind": str(row.get("kind", "")),
            "attempt": int(row.get("attempt") or 0), "text_frames": text_frames,
            "answer_chars": answer_chars, "answer_sha": answer_sha,
            "tool_calls": tool_calls, "tool_calls_book": tool_calls_book,
            "gate": gate, "bucket": bucket, "also_matched": matched,
            "witness": witness, "evidence": evidence}


def _ratio(green, denominator):
    return "n/a（分母为 0）" if not denominator else ("%.4f" % (float(green) / float(denominator)))


def _calibers(rows):
    """甲／乙／丙 三个口径各自的 A② 数。🔴 三档一起交，本件不替总控选。"""
    def subset(items):
        green = sum(1 for item in items if item["verdict"])
        return {"denominator": len(items), "green": green, "red": len(items) - green,
                "ratio": _ratio(green, len(items)),
                "red_ids": [item["id"] for item in items if not item["verdict"]]}

    by_bucket = {name: [item for item in rows if item["bucket"] == name] for name in BUCKET_ORDER}
    literal = subset(rows)
    b0 = subset(by_bucket[B0])
    cells = {name: {"count": len(by_bucket[name]),
                    "green": sum(1 for item in by_bucket[name] if item["verdict"]),
                    "red": sum(1 for item in by_bucket[name] if not item["verdict"]),
                    "ids": [item["id"] for item in by_bucket[name]]}
               for name in (B1, B2, B3)}
    return {
        CALIBER_A: {"name": CALIBER_A + "＝105 全分母（与 r239 在册读数逐字可比）",
                    "discloses_excluded_cells": True, **literal},
        CALIBER_B: {"name": CALIBER_B + "＝B0 作分母，B1/B2/B3 三格单独报数（不许蒸发）",
                    "discloses_excluded_cells": True, "excluded_cells": cells, **b0},
        CALIBER_C: {"name": CALIBER_C + "＝只报 B0，不提其余三格（只许出数，不许据此宣布翻绿）",
                    "discloses_excluded_cells": False, **b0},
    }


def _diagnostics(result):
    """留痕（不许静默）：前七格逐格点名到题号，一枚都不许悄悄消失；第八格是同题多轮的折叠枚数。"""
    rows = result["rows"]
    def ids(where):
        return [item["id"] for item in rows if where(item)]
    sensitivity = ids(lambda item: item["text_frames"] == 1 and item["witness"]["same_ms"] is not None
                      and item["witness"]["same_ms"] != item["witness"]["within_one_ms"])
    return {
        "tool_calls_unjoinable": ids(lambda item: item["tool_calls"] is None),
        "single_frame_without_arrival_coordinates": ids(
            lambda item: item["text_frames"] == 1 and item["witness"]["status"] != "measured"),
        "ms_reading_sensitivity_rows": sensitivity,
        "b0_rows_with_no_text_frame": ids(lambda item: item["bucket"] == B0 and item["text_frames"] == 0),
        "frames_column_conflicts_summary": ids(lambda item: item.get("witness_conflict")),
        "sentinel_rows_outside_prefab_set": ids(
            lambda item: item.get("sentinel") and item["answer_sha"] not in result["prefab"]),
        "ledger_vs_literal_disagreements": ids(lambda item: item["disagreement"]),
        "attempts_collapsed": result["frames_collapsed"],
    }


def read_round(frames=DEFAULT_FRAMES, sidecar=DEFAULT_SIDECAR, answers=DEFAULT_ANSWERS,
               nodes_source=None, chat_source=CHAT_SOURCE, harness_source=HARNESS_SOURCE,
               breaks_count_as_loss=False):
    """把一轮的三本账读成一张归账表。只读；任何一枚键取不到都当场抛，不静默补零。"""
    gate = lane.piece_size_gate(nodes_source) if nodes_source else lane.piece_size_gate()
    fingerprints = prefab_fingerprints(chat_source, harness_source)
    frame_rows, frames_collapsed = lane.rows_by_id(frames, required=audit.REQUIRED_KEYS)
    if not frame_rows:
        raise audit.LedgerSchemaError("帧账读不到任何一行：" + str(frames))
    sidecar_rows, _ = lane.rows_by_id(sidecar)
    answer_rows, _ = lane.rows_by_id(answers)
    confirmed = check_prefab_fingerprints(frame_rows, answer_rows, fingerprints)
    rows = []
    for key, row in frame_rows.items():
        tool_calls, book = tool_calls_of(row, sidecar_rows, answer_rows)
        judged = audit.judge_row(row, breaks_count_as_loss)
        entry = bucket_of_row(row, tool_calls, gate, fingerprints, tool_calls_book=book)
        entry.update({"verdict": judged["verdict"], "cell_2a": judged["event_count_gt_1"],
                      "cell_2b": judged["char_by_char_no_loss"],
                      "ledger_criterion_two_holds": judged["ledger_criterion_two_holds"],
                      "disagreement": judged["disagreement"],
                      "event_form": judged["event_form"],
                      "sentinel": bool(row.get("sentinel")),
                      "witness_conflict": lane.witness_conflict(row)})
        rows.append(entry)
    result = {"inputs": {"frames": str(frames), "sidecar": str(sidecar), "answers": str(answers),
                         "nodes_source": str(nodes_source or lane.NODES_SOURCE),
                         "chat_source": str(chat_source), "harness_source": str(harness_source),
                         "breaks_count_as_loss": bool(breaks_count_as_loss)},
              "gate": gate,
              "prefab": {sha: {"family": item["family"], "symbol": item["symbol"],
                               "source": item["source"], "chars": len(item["text"])}
                         for sha, item in fingerprints.items()},
              "prefab_confirmed": confirmed,
              "frames_collapsed": frames_collapsed,
              "rows": rows,
              "bucket_counts": {name: sum(1 for item in rows if item["bucket"] == name)
                                for name in BUCKET_ORDER},
              "also_matched_counts": {name: sum(1 for item in rows if name in item["also_matched"])
                                      for name in (B1, B2, B3)}}
    result["calibers"] = _calibers(rows)
    result["diagnostics"] = _diagnostics(result)
    conserved = sum(result["bucket_counts"].values())
    if conserved != len(rows):
        raise CaliberError("四桶不守恒：桶计数合计 " + str(conserved) + " 而题数 = " + str(len(rows)))
    return result


def declare(result, caliber, green=False, disclosed=False):
    """把某一口径的 A② 数念成一句话。🔴 要拿它宣布「翻绿」，本件有权当场拒。

    * 丙口径（不提 B1/B2/B3）⇒ 一律拒绝：它换小的分母正是被这三格腾出来的，
      不点名那三格就说「翻绿」，等于把红题藏进分母的调整里。
    * 乙口径 ⇒ 必须 ``disclosed=True``（三格一起交），否则同样拒绝。
    * 甲／乙（已披露）⇒ 还要求该口径分母里一枚都不红，红着就拒绝并点名。
    """
    if not green:
        cell = result["calibers"][caliber]
        return (caliber + " 口径 A② = " + str(cell["green"]) + "/" + str(cell["denominator"])
                + " = " + cell["ratio"])
    if caliber not in result["calibers"]:
        raise CaliberError("认不出口径：" + str(caliber))
    cell = result["calibers"][caliber]
    if caliber == CALIBER_C:
        counts = result["calibers"][CALIBER_B]["excluded_cells"]
        raise CaliberError("丙口径只交 B0 那一格，不提 B1=" + str(counts[B1]["count"])
                           + "／B2=" + str(counts[B2]["count"]) + "／B3=" + str(counts[B3]["count"])
                           + " 三格 ⇒ 不许据它宣布 A② 翻绿（被这三格腾出分母的题号："
                           + "、".join(sorted(item for name in (B1, B2, B3)
                                              for item in counts[name]["ids"])) + "）")
    if caliber == CALIBER_B and not disclosed:
        raise CaliberError("乙口径的三格（B1/B2/B3）没一起交 ⇒ 这一读不许单独宣布翻绿")
    if cell["red"]:
        raise CaliberError(caliber + " 口径里还红着 " + str(cell["red"]) + " 枚："
                           + "、".join(cell["red_ids"]))
    return caliber + " 口径：分母 " + str(cell["denominator"]) + " 枚全绿 ⇒ 可以宣布 A② 翻绿"

def render(result, show_rows=True):
    """一张可读的交回：逐题表（默认全交）＋每桶计数＋甲乙丙三个数＋七格点名留痕。"""
    lines = ["[r565] 帧账=" + result["inputs"]["frames"],
             "[r565] sidecar=" + result["inputs"]["sidecar"],
             "[r565] answers=" + result["inputs"]["answers"],
             "[r565] ② 的判据出处=r239.event_count_gt_1 ∧ r239.char_by_char_no_loss（本件一字不重写）"
             + ("｜breaks 也算缺字" if result["inputs"]["breaks_count_as_loss"] else ""),
             "[r565] 尺寸闸现取 STREAM_PIECE_MIN_CHARS=" + str(result["gate"]) + "（"
             + result["inputs"]["nodes_source"] + "，经 r518.piece_size_gate，本件不抄第二份）",
             "[r565] 预制串指纹现取 " + str(len(result["prefab"])) + " 枚："]
    for sha, entry in sorted(result["prefab"].items(), key=lambda kv: kv[1]["symbol"]):
        lines.append("        " + sha + " ← " + entry["symbol"] + "（" + entry["family"] + "，"
                     + str(entry["chars"]) + " 字，" + entry["source"] + "）")
    lines.append("[r565] 逐字对质：账上文本 == 现取串 ⇒ 指纹校验通过 "
                 + str(len(result["prefab_confirmed"])) + " 枚（0 枚＝这一窗没有预制句，不等于判据失效）")
    lines.append("[r565] 同题多轮折叠（取 attempt 最大）=" + str(result["frames_collapsed"]) + " 枚")
    if show_rows:
        lines.append("")
        lines.append("{0:<13} {1:<3} {2:<4} {3:<4} {4:<4} {5:<4} {6:<5} {7:>3}  {8}".format(
            "id", "桶", "kind", "2a", "2b", "②", "led", "tf",
            "依据读数原文（命中过的格全留）"))
        for item in result["rows"]:
            lines.append("{0:<13} {1:<3} {2:<4} {3:<4} {4:<4} {5:<4} {6:<5} {7:>3}  {8}".format(
                item["id"], item["bucket"], item["kind"][:4],
                "T" if item["cell_2a"] else "F", "T" if item["cell_2b"] else "F",
                "T" if item["verdict"] else "F",
                "T" if item["ledger_criterion_two_holds"] else "F",
                item["text_frames"], " ｜ ".join(item["evidence"])))
    counts = result["bucket_counts"]
    lines.append("")
    lines.append("[r565] 桶计数：" + "  ".join(
        name + "=" + str(counts[name]) for name in BUCKET_ORDER)
        + "  合计=" + str(sum(counts.values())) + "（题数=" + str(len(result["rows"])) + "）")
    lines.append("[r565] 三格另计（also_matched，含被呈现优先级抢走的枚）：" + "  ".join(
        name + "=" + str(result["also_matched_counts"][name]) for name in (B1, B2, B3)))
    for caliber in CALIBERS:
        cell = result["calibers"][caliber]
        lines.append("[r565] " + caliber + " A② = " + str(cell["green"]) + "/"
                     + str(cell["denominator"]) + " = " + cell["ratio"] + "  红=" + str(cell["red"])
                     + "  红题号=" + ("、".join(cell["red_ids"]) if cell["red_ids"] else "无"))
        if caliber == CALIBER_B:
            for name in (B1, B2, B3):
                sub = cell["excluded_cells"][name]
                lines.append("        " + BUCKET_NAMES[name] + "：" + str(sub["count"]) + " 枚"
                             "（②真=" + str(sub["green"]) + " ②红=" + str(sub["red"]) + "）"
                             " 题号=" + ("、".join(sub["ids"]) if sub["ids"] else "无"))
    diagnostics = result["diagnostics"]
    lines.append("[r565] 留痕（七格点名，一枚都不许悄悄消失；折叠枚数见上方）：")
    for key in ("tool_calls_unjoinable", "single_frame_without_arrival_coordinates",
                "ms_reading_sensitivity_rows", "b0_rows_with_no_text_frame",
                "frames_column_conflicts_summary", "sentinel_rows_outside_prefab_set",
                "ledger_vs_literal_disagreements"):
        lines.append("        " + key + "=" + str(len(diagnostics[key]))
                     + ("  " + "、".join(diagnostics[key]) if diagnostics[key] else ""))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="R565：把 A② 的分母拆成 B0/B1/B2/B3 四桶并交甲乙丙三口径（只读、离线）")
    parser.add_argument("--frames", default=str(DEFAULT_FRAMES))
    parser.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    parser.add_argument("--answers", default=str(DEFAULT_ANSWERS))
    parser.add_argument("--nodes-source", default=None,
                        help="尺寸闸真源（默认 app/agents/nodes.py；反证用影子件指到这里）")
    parser.add_argument("--chat-source", default=str(CHAT_SOURCE))
    parser.add_argument("--harness-source", default=str(HARNESS_SOURCE))
    parser.add_argument("--breaks-count-as-loss", action="store_true",
                        help="透传给 r239：把屏上连续性也算进②-b（两种读法都出数）")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--no-rows", action="store_true", help="只交计数与三口径，不交逐题表")
    parser.add_argument("--expect-denominator", type=int, default=DENOMINATOR_IN_BOOK,
                        help="与在册分母对账（0＝不对账；对不上出 rc=2 并点名）")
    parser.add_argument("--claim-green", choices=CALIBERS, default=None,
                        help="演示用：拿这口径宣布翻绿。丙口径一律当场拒绝（rc=3）")
    parser.add_argument("--disclosed", action="store_true",
                        help="宣布乙口径时声明三格已一起交")
    args = parser.parse_args(argv)

    result = read_round(frames=args.frames, sidecar=args.sidecar, answers=args.answers,
                        nodes_source=args.nodes_source, chat_source=args.chat_source,
                        harness_source=args.harness_source,
                        breaks_count_as_loss=args.breaks_count_as_loss)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=1))
    else:
        for line in render(result, show_rows=not args.no_rows):
            print(line)

    code = 0
    if args.expect_denominator and len(result["rows"]) != args.expect_denominator:
        print("[r565][对账不上] 在册分母=" + str(args.expect_denominator) + " 而这一窗题数="
              + str(len(result["rows"])) + "（" + result["inputs"]["frames"] + "）")
        code = 2
    if args.claim_green:
        try:
            print("[r565] " + declare(result, args.claim_green, green=True,
                                      disclosed=args.disclosed))
        except CaliberError as error:
            print("[r565][当场拒绝] " + str(error))
            code = 3
    return code


if __name__ == "__main__":
    sys.exit(main())
