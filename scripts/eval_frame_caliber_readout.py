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

③ **A② 断裂分档层**（R619 乙案，归因见 ``docs/perf/r614-uncorrected-break-attribution-2026-10-03.md``）：
   ``uncorrected_breaks`` 那一格按行内既有的 ``streams``／``per_stream``／``frames[].stream`` 三列
   现场拆成两档——单流轮的断裂、多流轮·第④条件结构性够不到的断裂——外加一枚 ``not_applicable``
   逃生档（派生不出就点名够不到，不许当成 0）。🔴 **分档≠豁免**：落盘值与判定层
   （``scripts/eval_transport_ask_v2.py`` 的 ``_frame_readings``／``_corrective_readings``）一字不动，
   两档之和恒等于旧口径那枚数，只是读数不再混在一起冒充同一口径。

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
    # R471 的第七枚合取**不在这一列**：那枚证词不落成新列（丙案，总控 09-29 裁定一），
    # 由下面的 ``derived_repeats`` 从行内既有那一列 R223 逐帧指纹现场派生。
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


def _repeats_of_records(records: list[dict]) -> int | None:
    """从一行的 R223 逐帧指纹里数「后一条流把先前发过的那份正文又发一遍」有几枚。

    口径逐字同 ``scripts/eval_transport_ask_v2.py::_cross_stream_repeats``（🔴 以 R507 并树后的那一份
    为准，本件不自创第二套）：只算跨流（同一条流里末片帧与收尾帧同文**不算**出现两遍 —— 总控裁定），
    空帧不参与。

    🔴 R507 两形分开，R515 补的正是这枚同口径分身（``docs/testing/r507-blind-instrument-returns-none.md``
    §4.B 与 §6 第 4 条挂号的那半把没治的）：帧在而一枚逐帧指纹都拿不到（量具被摘瞎那一形）⇒ 回
    ``None``＝这一格在这一行**没量过**，不许报 0 冒充量过（事故 #73 那一族假零）；拿到了指纹且确实
    没有跨流重合 ⇒ 才回 0。入参不是帧表或枚数为零（空读那一形）照在册现状回 0，与
    ``_cross_stream_repeats:717-719`` 同脸 —— 那一形钉在
    ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``，不在本单写域。
    """
    records = list(records or [])
    if records and not any(str(record.get("sha") or "") for record in records):
        return None  # R507 两形分开（一）：帧在而无一枚指纹 ⇒ 未量，不许报 0 冒充量过
    earliest: dict[str, int] = {}
    repeats = 0
    for record in records:
        if int(record.get("chars") or 0) <= 0:
            continue
        sha = str(record.get("sha") or "")
        if not sha:
            continue
        stream = int(record.get("stream") or 0)
        if sha in earliest and stream > earliest[sha]:
            repeats += 1
        earliest[sha] = min(stream, earliest.get(sha, stream))
    return repeats


def account_fingerprints(rows: list[dict]) -> int:
    """整份账里现存的 R223 逐帧指纹枚数（``frames[].sha``）。本件**只数现成读数，一枚不另数**。"""
    return sum(1 for row in rows for record in (row.get("frames") or [])
               if str(record.get("sha") or ""))


def unmeasured_rows(rows: list[dict]) -> list[str]:
    """「帧在而这一行一枚逐帧指纹都拿不到」的题号（R515）：这些行压根没参与判定。"""
    return [str(row["id"]) for row in rows
            if _repeats_of_records(row.get("frames") or []) is None]


def derived_repeats(rows: list[dict]):
    """R471 丙案：第七枚合取的证词在账里**不存在**，本件读数时从行内既有那一列现场派生。

    返回 ``None``＝这份账派生不出：没有 ``frames`` 那一列（R223 并树之前开的窗，run6/run7 即此形），
    或者那一列枚枚为空（量具被摘瞎那一形，run8p2 即此形），🔴 或者帧在、枚枚有字而整份账连一枚逐帧
    指纹都没参与（摘瞎的另一张脸，R515 起与前两形同权明写）⇒ 三形一律照实明写量不到，不许报 0
    冒充量过；
    返回 ``[(题号, 枚数)]``＝这份账量得出（至少一枚逐帧指纹参与了判定，🔴 干净才交 0 枚）。
    🔴 两样都不许拿去改写当年的 ``criterion_two_holds``
    （不重判，口径见 docs/testing/r471-verdict-caliber-2026-09-29.md）。
    """
    if not any(row.get("frames") for row in rows):
        return None
    if not account_fingerprints(rows):
        # R515（口径逐字同 R507 并树后的 ``_cross_stream_repeats:717-719``）：帧在而整份账无一枚指纹
        # ⇒ 这一格没量过。旧落码在这一形交回一张每行都是 0 的表，读的人把「没量过」当成「量过且干净」。
        return None
    counts = [_repeats_of_records(row.get("frames") or []) for row in rows]
    return [(str(row["id"]), value) for row, value in zip(rows, counts) if value]


def event_tally(rows: list[dict]) -> collections.Counter:
    tally = collections.Counter()
    for row in rows:
        names = {event.get("event") for event in (row.get("events") or [])}
        for name in names:
            tally[name] += 1
    return tally


# ==================== R619 乙案：A② 断裂读数的分档（只摊读数，不动判定）====================

#: 🔴 这一格拆的是**读数**，不是判定，也不是豁免。侧车与帧账的落盘值、
#: ``_frame_readings`` / ``_corrective_readings`` 的豁免账、``criterion_two_holds`` 一律一字不动；
#: 多流那一档照旧计入 ``uncorrected_breaks``、照旧让 A② 读 False。
#: 归因凭据＝``docs/perf/r614-uncorrected-break-attribution-2026-10-03.md``（量具口径缺陷，非产品缺陷）。
UNCORRECTED_CELL = "uncorrected_breaks"

#: 派生「这一轮一共几条流」只许用行内**既有**这三列（R614 §0 与 §1B 点名的就是它们），按次序试。
#: 🔴 三列都试不出 ⇒ 明写够不到并点名是哪一行（同总控 ``b9fd2fc`` 那条规矩），不许当成 0；
#: 也不许为这一档新造一枚列（``tests/test_r181_text_frame_ruler.py:50``／``:449`` 两道键集闸在场）。
STREAM_COLUMNS = ("streams", "per_stream", "frames")

TIER_SINGLE = "档① 单流轮（行内派生得出一枚流 streams=1）"
TIER_MULTI = "档② 多流轮·第④条件结构性够不到（streams>1）"
TIER_UNREACHABLE = "档③ not_applicable·这一行派生不出流数"
CELL_ABSENT_NOTE = ("  - 🔴 A② 断裂分档在这份账里同样记 not_applicable：上面那一格压根不存在，"
                    "不存在不等于零枚断裂，也不等于没有分档这回事")


def _int_or_none(value):
    """把账上那一格折成整数；折不出（缺格／空串／非数字／布尔）交回 ``None``。🔴 不折成 0。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _shown(value):
    """纸面用：读不出的那一格明写「不可证」，既不留空也不冒充数字。"""
    return "不可证" if value is None else value


def _per_stream_cell(per_stream, index):
    """取 ``per_stream[流号]`` 那一格；越界／非表 ⇒ ``None``（够不到就说够不到，不编数）。"""
    if not isinstance(per_stream, list) or index is None or index < 0 or index >= len(per_stream):
        return None
    cell = per_stream[index]
    return cell if isinstance(cell, dict) else None


def derive_streams(row):
    """从行内既有列现场派生「这一轮一共几条流」，交回 ``(枚数, 出处或派生不出的原因)``。

    次序＝``STREAM_COLUMNS``：``streams`` 那一格是正源（``_fold_frames`` 每折一条流加一枚），
    它缺席或折不出整数才退到 ``per_stream`` 的长度，最后退到 ``frames[].stream`` 的最大流序号加一。
    🔴 三列都读不出 ⇒ 交回 ``(None, 逐列点名的原因)``：这一行的断裂不许并进档①／档②，也不许读成 0。
    """
    notes = []
    for column in STREAM_COLUMNS:
        if column not in row:
            notes.append("%s 缺格" % column)
            continue
        value = row[column]
        if column == "streams":
            streams = _int_or_none(value)
            if streams is None:
                notes.append("streams 折不出整数（%r）" % (value,))
                continue
            return streams, "streams"
        if column == "per_stream":
            if isinstance(value, list) and value:
                return len(value), "per_stream"
            notes.append("per_stream 空表或非表")
            continue
        records = value if isinstance(value, list) else []
        indices = [index for index in (_int_or_none(record.get("stream"))
                                       for record in records if isinstance(record, dict))
                   if index is not None]
        if indices:
            return max(indices) + 1, "frames[].stream"
        notes.append("frames %s" % ("非表" if not isinstance(value, list) else "无一枚带可读 stream"))
    return None, "｜".join(notes)


def derive_break_positions(row):
    """断裂住在第几条流、那一流一共几帧：全部从行内既有列现取，一枚新列都不造。

    两路（🔴 两路都读不出 ⇒ 交回 ``(None, 逐列点名的原因)``，不许读成「这一行没有断裂」）：
      ① ``frames[]`` 里 ``prefix_break`` 为真的那几枚 —— 一手给出流号与 ``at``，再用
         ``per_stream[流号]`` 补那一流的总帧数与断裂枚数；
      ② 退路＝``per_stream[]`` 里 ``breaks>0`` 的那几格（``frames`` 整列缺席的老窗，run6/run7 即此形），
         只有流号、总帧数、``first_break_at`` 三格。
    每枚元素＝``{"stream", "at", "stream_frames", "breaks_in_stream"}``，读不出的那一格为 ``None``。
    """
    frames = row.get("frames")
    frames = frames if isinstance(frames, list) else []
    per_stream = row.get("per_stream")
    per_stream = per_stream if isinstance(per_stream, list) else []

    flagged = [record for record in frames
               if isinstance(record, dict) and record.get("prefix_break")]
    positions = []
    provenance = ""
    if flagged:
        provenance = "frames[].prefix_break"
        positions = [{"stream": _int_or_none(record.get("stream")),
                      "at": _int_or_none(record.get("at"))} for record in flagged]
    else:
        for number in range(len(per_stream)):
            cell = _per_stream_cell(per_stream, number)
            if cell is not None and (_int_or_none(cell.get("breaks")) or 0) > 0:
                positions.append({"stream": number,
                                  "at": _int_or_none(cell.get("first_break_at"))})
        if positions:
            provenance = "per_stream[].breaks"
    if not positions:
        reason = ("断裂位次派生不出：frames 列%s且 prefix_break 无一枚为真；per_stream 列%s且 breaks 无一格 >0"
                  % ("缺席" if "frames" not in row else "在位",
                     "缺席" if "per_stream" not in row else "在位"))
        return None, reason
    for position in positions:
        cell = _per_stream_cell(per_stream, position["stream"])
        position["stream_frames"] = _int_or_none(cell.get("frames")) if cell else None
        position["breaks_in_stream"] = _int_or_none(cell.get("breaks")) if cell else None
    return positions, provenance


def break_tiers(rows):
    """把 ``uncorrected_breaks>0`` 的行拆成两档 + 一枚够不到的逃生档（🔴 只读，一行都不改写）。

    分档谓词与 ``caliber_block`` 上面那一行**逐字同**（``int(row.get(cell) or 0) > 0``），
    所以「档① + 档② + 档③ ＝ 旧口径总数」是恒等式而不是巧合。
    🔴 分档≠豁免：本件不把多流那一档并入 ``granted``，也不改写当年任何一枚落盘读数。
    位次派生不出（流数派生得出）那一形**留在它自己那一档**，只在证词里点名够不到，
    不许因为它就整行逃进档③——那是拿一格的够不到去洗另一格的读数。
    """
    tiers = {"single": [], "multi": [], "unreachable": []}
    for row in rows:
        uncorrected = int(row.get(UNCORRECTED_CELL) or 0)
        if uncorrected <= 0:
            continue
        streams, streams_from = derive_streams(row)
        positions, positions_from = derive_break_positions(row)
        entry = {"id": str(row["id"]),
                 "uncorrected_breaks": uncorrected,
                 "streams": streams,
                 "streams_from": streams_from,
                 "positions": positions,
                 "positions_from": positions_from,
                 # 🔴 同轮既豁免过一枚又有未豁免：盘上不分哪一枚是谁（break_frames 不落帧账），
                 # 那一行的流序号只能读作候选，纸面必须明写。
                 "candidate_positions": (_int_or_none(row.get("corrective_replacements")) or 0) > 0}
        reasons = []
        if streams is None:
            reasons.append("流数派生不出（%s）" % streams_from)
        elif streams < 1:
            reasons.append("streams=%r 与 uncorrected_breaks>0 矛盾 ⇒ 流数不可信" % streams)
        if positions is None:
            reasons.append(positions_from)
        entry["reason"] = "；".join(reasons)
        if streams is None or streams < 1:
            tiers["unreachable"].append(entry)
        elif streams > 1:
            tiers["multi"].append(entry)
        else:
            tiers["single"].append(entry)
    return tiers


def _describe_break_entry(entry):
    """一行断裂的纸面证词：题号／流数（含出处）／断裂住在第几条流、该流几帧、第几枚上断。"""
    bits = ["%s uncorrected_breaks=%d" % (entry["id"], entry["uncorrected_breaks"]),
            "streams=%s（派生自 %s）" % (_shown(entry["streams"]), entry["streams_from"])]
    if entry["positions"] is None:
        bits.append("断裂所在流=🔴 %s" % entry["positions_from"])
    else:
        for position in entry["positions"]:
            stream, streams = position["stream"], entry["streams"]
            tail = "流序不可证"
            if isinstance(stream, int) and isinstance(streams, int) and streams >= 1:
                tail = "非末流＝挂起轮那一族" if stream < streams - 1 else "末流"
            if entry["candidate_positions"]:
                tail += "｜候选：同轮另有已豁免的断裂，盘上不分哪一枚"
            bits.append("断裂在 stream %s（该流 %s 帧，第 %s 枚上断，该流断裂 %s 枚，%s）" % (
                _shown(stream), _shown(position["stream_frames"]), _shown(position["at"]),
                _shown(position["breaks_in_stream"]), tail))
    if entry.get("reason") and entry["positions"] is not None:
        bits.append("🔴 %s" % entry["reason"])
    return " ".join(bits)


def print_break_tiers(rows, offenders):
    """把 ``uncorrected_breaks`` 那一格摊成两档：🔴 只加读数，上面那行旧口径一字不动、不被顶掉。"""
    tiers = break_tiers(rows)
    for bucket in tiers.values():
        bucket.sort(key=lambda entry: entry["id"])
    legacy = len(offenders)
    legacy_total = sum(int(row.get(UNCORRECTED_CELL) or 0) for row in rows
                       if int(row.get(UNCORRECTED_CELL) or 0) > 0)
    counts = {key: len(value) for key, value in tiers.items()}
    totals = {key: sum(entry["uncorrected_breaks"] for entry in value) for key, value in tiers.items()}
    for key, title in (("single", TIER_SINGLE), ("multi", TIER_MULTI), ("unreachable", TIER_UNREACHABLE)):
        ids = [entry["id"] for entry in tiers[key]]
        print("  - %s：题数=%d/%d 断裂枚数=%d/%d 题号=%s" % (
            title, counts[key], legacy, totals[key], legacy_total, ids or "无"))
        for entry in tiers[key]:
            print("    · %s" % _describe_break_entry(entry))
    if tiers["multi"]:
        print("  - 🔴 档②**不是豁免**，也不是「可忽略」那一类的词：分档只改读数，这一 %d 枚照旧计入 "
              "uncorrected_breaks、照旧让 A② 读 False ⇒ **这一档不算通过**，落盘值一枚都不改写。它只说清断裂住在多流轮里——"
              "R215 豁免第④条（scripts/eval_transport_ask_v2.py:676）拿**轮级**交付文本比**流内**末帧，"
              "挂起轮里那次受控整段替换结构性不可能等于批准腿交回的终答（两窗 19/19 终答严格长于 "
              "pre_answer、0/19 逐字相同）⇒ 只要挂起轮里换了源，这把尺必然判红。修尺本身归甲案，另有单。"
              % counts["multi"])
    if tiers["unreachable"]:
        print("  - 🔴 档③＝not_applicable：题号=%s ⇒ 这些行的流数在这份账里够不到；够不到就说够不到，"
              "不许当成 0，不许并进档①或档②（同 b9fd2fc 口径）"
              % [entry["id"] for entry in tiers["unreachable"]])
    row_sum = counts["single"] + counts["multi"] + counts["unreachable"]
    break_sum = totals["single"] + totals["multi"] + totals["unreachable"]
    print("  - 恒等式（题数）：%d(单流)+%d(多流)+%d(够不到)=%d ｜ 旧口径 uncorrected_breaks>0 枚数=%d ⇒ %s" % (
        counts["single"], counts["multi"], counts["unreachable"], row_sum, legacy,
        "成立" if row_sum == legacy else "🔴 不成立（本件的 bug，不许放行）"))
    print("  - 恒等式（断裂枚数）：%d+%d+%d=%d ｜ 旧口径合计=%d ⇒ %s" % (
        totals["single"], totals["multi"], totals["unreachable"], break_sum, legacy_total,
        "成立" if break_sum == legacy_total else "🔴 不成立（本件的 bug，不许放行）"))


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
        elif not any(cell in row for row in rows):
            # 🔴 R471 之前开的窗不存这格证词：读不到就明写读不到，不许报 0 冒充量过
            # （在册尺对老账同样不重判，口径见 docs/testing/r471-verdict-caliber-2026-09-29.md）。
            print("- %s 这一格在这份账里不存在（R471 之前的窗）⇒ 不重判当年读数" % cell)
            if cell == UNCORRECTED_CELL:
                print(CELL_ABSENT_NOTE)
        else:
            print("- %s >0 枚数=%d 题号=%s" % (cell, len(offenders), offenders or "无"))
            if cell == UNCORRECTED_CELL:
                print_break_tiers(rows, offenders)
    repeats = derived_repeats(rows)
    if repeats is None:
        # 🔴 账里没有一枚参与判定的逐帧指纹（R223 并树之前的窗，或量具被摘瞎那一形）：读不到就明写
        # 读不到，不许报 0 冒充量过（R507/R515 两形分开）。
        print("- cross_stream_repeat_frames（R471 第七枚，派生格）这份账连一枚 R223 逐帧指纹都没参与"
              " ⇒ 这一格在这份账里派生不出（R223 并树之前的窗，或量具被摘瞎那一形）⇒ 不重判当年读数")
    else:
        print("- cross_stream_repeat_frames（R471 第七枚，🔴 派生自 frames 列，不落成新列）"
              " >0 枚数=%d 题号=%s" % (len(repeats), repeats or "无"))
        print("  - 逐枚重合数=%s ｜ 本件不据此改写 criterion_two_holds（当年读数不重判）" % repeats)
        blind = unmeasured_rows(rows)
        if blind:
            # R515：混合账（有的行有指纹、有的行被摘瞎）不许把上面那枚 0 读成全账干净。
            print("  - 🔴 行内未量（帧在而无一枚逐帧指纹）题数=%d 题号=%s ⇒ 这些行没参与判定，"
                  "上面那枚枚数只属于有指纹的行" % (len(blind), blind))
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