r"""R116 · 真机 backend 日志 → 逐发装箱台账 → **按实测 prompt_tokens 复算 room**。

跟进单 §54 立 R116 的原话是"那 46 枚钉桩用的是夹具题面 + 桩检索料，不是真机当时的 prompt
尺寸"。本模块就是那把缺的真尺子：只读 run5 保全的 backend 日志，把每一发 ``[PromptPack]``
与它**后面第一发** ``[ModelBudget]``（＝真机读这份料的那一发模型调用）配成一对，于是

    实测壳（非料部分到底花了多少枚）＝ prompt_tokens − ledger_packed_tokens
    实测 room ＝ context_pack_capacity() − 实测壳
    room 估窄了多少 ＝ 实测 room − context_pack_room()

三个数全是真机数：``prompt_tokens`` 由被测代码自己的 ``estimate_prompt_tokens`` 产出，
``ledger_packed_tokens`` 由被测装箱函数自己记账，本模块不重算、不估算、不抄常数。

🔴 日志一律先探 BOM 再解码（跟进单 §62 的教训）：``backend-run5.log`` 是 PowerShell ``>``
重定向产出的 **UTF-16 LE**，按 utf-8 硬读会得到 0 枚 ``[PromptPack]`` 的全零假阴性。本模块
把"解出来 0 枚装箱账"判成**硬失败**，不当成"今天没装箱"。

复算口径（改口径必须同时改这段说明）：

* 一问一段：``[Classify]`` 是每题第一行，两段之间就是这一题的全部日志；段与 ``id`` 按
  **顺序**对应（run5 全程 ``MODEL_MAX_CONCURRENCY=1``、``attempt=1``、0 枚 sentinel ⇒ 105 段
  对 105 行侧车）。105 段里 101 段的 ``[Classify]`` 原文与夹具题面一字不差，另 4 段
  （``chat-02 chat-07 chat-12 insight-04``）量到的是多轮改写后的题面，顺序仍成立。
* 只认带 ``ledger_packed_tokens=`` 的装箱行（doc / data 两条腿）。``leg=retrieval`` 那行没有
  这枚字段、也没有 ``stub=``，是判据 6 的取证对象，不在复算范围内。
* 反事实复算要"一条候选值多少枚"，而日志不逐条记价、只记 ``packed_tokens``/``fitted``：取该题
  该腿**整条送出**（``truncated=0`` 且 ``fitted>0``）那一发的**最贵**均价并上取整——宁可高估料价，
  也不给装箱放水。

用法（仓外只读，零模型、零容器、零服务）::

    python scripts/perf_probe_run5_ledger.py --format refused
    python scripts/perf_probe_run5_ledger.py --format cost
    python scripts/perf_probe_run5_ledger.py --emit-table   # 重出 tests 里那张实测表
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime

#: run5 保全件（跟进单 §62 二 · 看板 §4BH.12）。日志与侧车都在仓库外，本模块只读。
DEFAULT_LOG = os.path.join(os.environ.get("TEMP", "/tmp"), "evalrun", "backend-run5.log")
DEFAULT_SIDECAR = os.path.join(os.environ.get("TEMP", "/tmp"), "evalrun", "sidecar-run5.jsonl")

PACK_MARKER = "[PromptPack]"
#: 字段名过滤器：只认 ASCII 标识符，正文里出现的 金额=... 一类不算字段。
_ASCII_FIELD = re.compile(r"[a-z_]+")
#: 证据袋那句「装箱未送出，证据袋不记」（leg=data dataset=... recorded=false）。
EVIDENCE_BAG_MARK = "recorded=false"
BUDGET_MARKER = "[ModelBudget]"
CLASSIFY_MARKER = "[Classify]"
#: 有这一枚字段＝这一发真记在轮账上（doc / data 腿）；retrieval 腿那行没有它。
LEDGER_FIELD = "ledger_packed_tokens"

_PREFIX = re.compile(r"^\s*[\w.-]+\s+\|\s*")
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) ")
_MODEL_RESPONSE = re.compile(r"HTTP Request: POST \S*(/v1/chat/completions|/api/chat)")
#: 真机上"料已经备好，下一步就是装箱"的那几行：拿它们当装箱窗口的起点。
_MATERIAL_READY = ("检索完成:", "CSV 编码检测:")


class LogFormatError(RuntimeError):
    """日志读不出任何装箱账：编码猜错或被读的文件不对，绝不当成"今天没装箱"。"""


@dataclass(frozen=True)
class Stamp:
    """一行日志：时间戳（可空）+ 去掉容器前缀与级别前缀后的正文。"""

    at: "datetime | None"
    body: str


def read_backend_log(path: str) -> list:
    """探过 BOM 再解码，并把"零枚装箱账"判成硬失败。"""
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw[:3] == b"\xef\xbb\xbf":
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8", "replace")
    if PACK_MARKER not in text:
        raise LogFormatError(
            "%s 里 0 枚 %s：编码或文件选错了（run5 是 UTF-16 LE），按 utf-8 硬读得到的就是这个全零假阴性"
            % (path, PACK_MARKER)
        )
    return parse_lines(text)


def parse_lines(text: str) -> list:
    out = []
    for line in text.splitlines():
        line = _PREFIX.sub("", line.replace("\r", "")).strip()
        if not line:
            continue
        match = _STAMP.match(line)
        out.append(Stamp(
            datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f") if match else None,
            line,
        ))
    return out


def fields_of(body: str) -> dict:
    return dict(re.findall(r"(\w+)=([^\s]+)", body))


def segments(rows: list) -> list:
    """一问一段：``[Classify]`` 到下一枚 ``[Classify]``。返回 ``(起, 止)`` 下标对。"""
    marks = [i for i, row in enumerate(rows) if CLASSIFY_MARKER in row.body]
    return [(start, marks[n + 1] if n + 1 < len(marks) else len(rows)) for n, start in enumerate(marks)]


def pack_lines(rows: list, start: int, end: int, leg: str | None = None) -> list:
    out = []
    for index in range(start, end):
        body = rows[index].body
        if PACK_MARKER not in body or LEDGER_FIELD not in body:
            continue
        data = fields_of(body)
        if leg is None or data.get("leg") == leg:
            out.append((index, data))
    return out


def budget_after(rows: list, index: int, end: int, tier: str = "analysis") -> "int | None":
    """这一发装箱之后**第一发**该档模型调用的实测 ``prompt_tokens``。"""
    for cursor in range(index + 1, end):
        if BUDGET_MARKER not in rows[cursor].body:
            continue
        data = fields_of(rows[cursor].body)
        if data.get("tier") != tier:
            continue
        value = data.get("prompt_tokens", "")
        if value.isdigit():
            return int(value)
    return None


def whole_unit_price(packs: list) -> "int | None":
    """该腿整条送出那一发的最贵均价（上取整）＝复算用的料价。"""
    prices = [
        math.ceil(int(data["packed_tokens"]) / int(data["fitted"]))
        for _index, data in packs
        if int(data.get("fitted") or 0) > 0
        and int(data.get("truncated") or 0) == 0
        and int(data.get("packed_tokens") or 0) > 0
    ]
    return max(prices) if prices else None


def pack_record(row_id: str, index: int, data: dict, rows: list, end: int, packs: list) -> dict:
    """把一枚 ``[PromptPack]`` 行还原成复算所需的全部事实（doc / data 两条腿同一读法）。"""
    packed = int(data["packed_tokens"])
    return {
        "row_id": row_id,
        "leg": data["leg"],
        "room_total": int(data["room_total"]),
        "room_left": int(data["room_left"]),
        "candidates": int(data["candidates"]),
        "fitted": int(data["fitted"]),
        "dropped": int(data["dropped"]),
        "truncated": int(data["truncated"]),
        "stub": data["stub"],
        "packed_tokens": packed,
        # ``ledger_packed_tokens`` 含本发自己送出的那几枚，所以"这一发之前"要减回去：
        # 复算要预扣的正是这个数，减错了 room_left 就对不上真机那一发。
        "delivered_before_tokens": int(data[LEDGER_FIELD]) - packed,
        "delivered_tokens": int(data[LEDGER_FIELD]),
        # 这一发**之后**第一发 analysis 档调用的实测 prompt_tokens＝模型真读这份料时花掉的枚数。
        "measured_prompt_tokens": budget_after(rows, index, end),
        "unit_price_tokens": whole_unit_price(packs),
        "packs": len(packs),
    }


def ledger(rows: list, sidecar: list) -> list:
    """逐题逐腿的实测账：每题取该腿**最后一发**（room 被吃到贴地的那一发）。"""
    out = []
    for position, (start, end) in enumerate(segments(rows)):
        if position >= len(sidecar):
            break
        for leg in ("doc", "data"):
            chosen = pack_lines(rows, start, end, leg=leg)
            if not chosen:
                continue
            index, data = chosen[-1]
            out.append(pack_record(str(sidecar[position]["id"]), index, data, rows, end, chosen))
    return out


def refused_records(rows: list, sidecar: list) -> list:
    """全部 ``stub=refused`` 的发（run5：17 枚），逐枚带实测复算所需的全部事实。

    同一轮同一腿可以连着拒两发（拒了不记账 ⇒ room_left 一字不变），所以那两行的账面数字
    完全相同：多带一枚 ``refused_seq``（该腿第几发拒发）让 17 枚彼此可辨，测试才能逐枚点名。
    """
    out = []
    for position, (start, end) in enumerate(segments(rows)):
        if position >= len(sidecar):
            break
        for leg in ("doc", "data"):
            chosen = pack_lines(rows, start, end, leg=leg)
            refused = 0
            for index, data in chosen:
                if data["stub"] != "refused":
                    continue
                refused += 1
                record = pack_record(str(sidecar[position]["id"]), index, data, rows, end, chosen)
                record["refused_seq"] = refused
                out.append(record)
    return out


# ==================== 复算：room / 实得料 / 拒发 ====================


def measured_shell(record: dict) -> int:
    """非料部分（system 段 + 题面 + 规划文字 + 消息壳）真机到底花了多少枚。"""
    return int(record["measured_prompt_tokens"]) - int(record["delivered_tokens"])


def measured_room(record: dict, capacity: int) -> int:
    """按实测壳复算的 room：容量真源不减拍脑袋预留，减真机量到的那一笔。"""
    return int(capacity) - measured_shell(record)


def over_reserve(record: dict, capacity: int, estimated_room: int) -> int:
    """装箱按估算预留扣掉的 room，有多少是真机根本没花的。"""
    return measured_room(record, capacity) - int(estimated_room)


def even_split(total: int, count: int) -> list:
    """把真机量到的 ``packed_tokens`` 均摊回 ``fitted`` 条候选：整数、总和不变、大的在前。"""
    total, count = int(total), int(count)
    if count <= 0 or total < count:
        raise ValueError("even_split 需要 total>=count>0（真机送出过料才会有这种行）")
    base, extra = divmod(total, count)
    return [base + 1] * extra + [base] * (count - extra)


def replay_prices(record: dict) -> list:
    """这一发真机装箱行 -> 逐条候选的枚数表（复算用的"料价"），只用这一行里的事实。

    日志不逐条记价，只记 ``packed_tokens`` / ``fitted`` / ``dropped`` / ``room_left``，所以逐条
    价格必须从这四枚数里**反推**出来，且要满足两条互相拉扯的规矩：

    1. 复算要在估算 room 上一字不差地重演出真机那一发 => 被丢的那几条**至少**要比剩下的
       room 贵一枚（裁尾那条至少比整个 room 贵一枚）：``floor``。
    2. 反事实"按实测 room 能装几条"不许给装箱放水 => 同一批料价取该腿**整条送出**那几发里
       最贵的均价（``unit_price_tokens``）作为下限，宁可高估料价。

    取两者的较大值就是同时满足两件事的唯一口径。送出的那几条按真机均价均摊（这是硬事实：
    它们加起来正好等于 ``packed_tokens``）。
    """
    candidates = int(record["candidates"])
    fitted = int(record["fitted"])
    packed = int(record["packed_tokens"])
    room_left = int(record["room_left"])
    price = record["unit_price_tokens"]
    if price is None:
        raise ValueError("%s/%s：该腿没有任何整条送出的发，无实测料价可复算" % (record["row_id"], record["leg"]))
    if record["truncated"] or int(room_left) < packed:
        # 裁尾那一发送出的正是整个 room（``_fit_unit_to_room`` 二分裁到装得下的最大值）：
        # 这条候选的真实价只知道"比 room 贵"，取 floor。
        kept: list = []
        floor = room_left + 1
    else:
        kept = even_split(packed, fitted) if fitted else []
        floor = room_left - packed + 1
    prices = kept + [max(floor, int(price))] * (candidates - len(kept))
    if len(prices) != candidates or min(prices) <= 0:
        raise ValueError("%s/%s：反推的候选价表不自洽 %r" % (record["row_id"], record["leg"], prices))
    return prices


def fit_prices(prices: list, room_left: int) -> tuple:
    """逐条价表上的整条装箱复算：与 ``pack_prefix_by_rank`` 同一算法，只裁尾巴不重排。"""
    room = max(0, int(room_left))
    used = 0
    fitted = 0
    for price in prices:
        if used + int(price) > room:
            break
        used += int(price)
        fitted += 1
    return fitted, len(prices) - fitted, used


def counterfactual(record: dict, capacity: int, estimated_room: int) -> dict:
    """同一发候选、同一"本轮已装"，只差 room 口径：估算口径 vs 实测口径各装几条、拒几条。"""
    extra = over_reserve(record, capacity, estimated_room)
    price = record["unit_price_tokens"]
    prices = replay_prices(record)
    est_fitted, est_dropped, est_used = fit_prices(prices, record["room_left"])
    got_fitted, got_dropped, got_used = fit_prices(prices, record["room_left"] + extra)
    return {
        "row_id": record["row_id"],
        "leg": record["leg"],
        "measured_shell": measured_shell(record),
        "measured_room": measured_room(record, capacity),
        "over_reserve": extra,
        "unit_price_tokens": price,
        "estimated": {"fitted": est_fitted, "dropped": est_dropped, "used": est_used},
        "measured": {"fitted": got_fitted, "dropped": got_dropped, "used": got_used},
        "turns_into_material": got_fitted > 0,
    }


def pin_account(record: dict, capacity: int, estimated_room: int) -> dict:
    """一枚钉桩在该发真机装箱账上的三个答案：room 多少、实得料多少、拒发多少（两个口径各一组）。

    甲＝按估算预留的 room（真机当时就是它，``room_total`` 与 ``room_left`` 都在表里）；
    乙＝按实测 ``prompt_tokens`` 反推的 room。两口径都只答**整条送出**的料——裁尾桩不算实料，
    免得"变出料了"这句话被一枚三个字的空桩蒙过去。被测自己怎么走这两档由测试钉，这里只出算式。
    """
    prices = replay_prices(record)
    extra = over_reserve(record, capacity, estimated_room)
    room_b = max(0, int(record["room_left"]) + extra)
    est_fitted, est_dropped, est_used = fit_prices(prices, record["room_left"])
    got_fitted, got_dropped, got_used = fit_prices(prices, room_b)
    return {
        "row_id": record["row_id"],
        "leg": record["leg"],
        "room_estimated": int(record["room_left"]),
        "room_measured": room_b,
        "room_overestimate": extra,
        "measured_shell": measured_shell(record),
        "candidates": int(record["candidates"]),
        "whole_material_estimated": est_fitted,
        "refused_estimated": est_dropped,
        "tokens_estimated": est_used,
        "whole_material_measured": got_fitted,
        "refused_measured": got_dropped,
        "tokens_measured": got_used,
        "gained_material": got_fitted - est_fitted,
        "refused_on_machine": record["stub"] == "refused",
    }


def source_room() -> tuple:
    """从被测真源取 ``(容量, 估算 room)``：取不到就返回 ``None``，绝不回退抄来的常数。"""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from app.rag.retrieval_pipeline import context_pack_capacity, context_pack_room
    except Exception:  # noqa: BLE001 - 环境里没装 app（探针可以脱离产品跑），交回调用方判
        return None, None
    return context_pack_capacity(), context_pack_room()


# ==================== 判据 3：打包耗时 vs 生成长度 ====================


def cost_ledger(rows: list, sidecar: list) -> list:
    """每题墙钟拆三档：模型往返 / 装箱可见占用 / 其它（工具·编排·落盘）。

    归类按"这一段时间差落在哪一行"：落在 httpx 的模型响应行＝那一发模型往返；落在
    ``[PromptPack]`` 行＝装箱（连它前面那一步拼串一起算，所以是**上界**）；其余＝其它。

    另给两枚收窄口径：``pack_ready_s`` 只取"料已就绪那一行 → 装箱行"这一档（真机
    ``检索完成`` / ``CSV 编码检测`` 之后就是装箱，这一档才是装箱自己那段），
    ``native_*`` 只统计走 Ollama 原生 ``/api/chat`` 的那几发——全仓只有那条腿把
    ``eval_count``（真机生成 token）打进日志，兼容端点 ``/v1`` 一个字节的 usage 都没落
    （run5 实测：``eval_count`` 只出现在 91 枚原生应答行里，``completion_tokens`` 0 命中）。
    """
    out = []
    for position, (start, end) in enumerate(segments(rows)):
        if position >= len(sidecar):
            break
        model = pack_s = pack_ready = other = 0.0
        native_s = 0.0
        native_tokens = 0
        model_calls = pack_calls = ready_calls = 0
        previous: Stamp | None = None
        for index in range(start, end):
            row = rows[index]
            if row.at is None:
                continue
            gap = (row.at - previous.at).total_seconds() if previous else 0.0
            if _MODEL_RESPONSE.search(row.body):
                model += gap
                model_calls += 1
            elif PACK_MARKER in row.body:
                pack_s += gap
                pack_calls += 1
                if previous is not None and any(mark in previous.body for mark in _MATERIAL_READY):
                    pack_ready += gap
                    ready_calls += 1
            else:
                other += gap
            if "ollama-native" in row.body:
                data = fields_of(row.body)
                if data.get("seconds", "").replace(".", "").isdigit():
                    native_s += float(data["seconds"])
                if data.get("eval_count", "").isdigit():
                    native_tokens += int(data["eval_count"])
            previous = row
        out.append({
            "row_id": str(sidecar[position]["id"]),
            "wall_s": round(float(sidecar[position]["wall_ms"]) / 1000.0, 1),
            "model_s": round(model, 2),
            "pack_s": round(pack_s, 3),
            "pack_ready_s": round(pack_ready, 3),
            "other_s": round(other, 2),
            "model_calls": model_calls,
            "pack_calls": pack_calls,
            "pack_ready_calls": ready_calls,
            "native_seconds": round(native_s, 2),
            "native_tokens": native_tokens,
            # 第四档：侧车计时从进接口就起算，这一段的第一枚带时间戳日志要等 supervisor 落笔，
            # 中间那截（外加少数没有毫秒戳的行）不属于任何一档，照实记账而不硬塞进"其它"。
            "unattributed_s": round(
                float(sidecar[position]["wall_ms"]) / 1000.0 - model - pack_s - other, 2
            ),
            "answer_chars": int(sidecar[position]["answer_chars"]),
            "evidence_n": int(sidecar[position]["evidence_n"]),
        })
    return out


def cost_aggregate(rows: list, sidecar: list) -> dict:
    """``cost_ledger`` 的全量汇总：拆账四档 + 装箱占比 + 最慢那一题的装箱占用。

    第四档 ``unattributed_s_total`` 是**故意**留在账外的：侧车的 ``wall_ms`` 从进接口就起算，
    而这一段的第一枚带时间戳日志要等 supervisor 落笔；中间那段（以及少数没有毫秒戳的行）
    不属于"模型往返/装箱/其它"任何一档，硬塞进去就是把拆账做成闭环。
    """
    ledger_rows = cost_ledger(rows, sidecar)
    wall = sum(row["wall_s"] for row in ledger_rows)
    model = sum(row["model_s"] for row in ledger_rows)
    pack = sum(row["pack_s"] for row in ledger_rows)
    other = sum(row["other_s"] for row in ledger_rows)
    return {
        "questions": len(ledger_rows),
        "pack_lines": sum(row["pack_calls"] for row in ledger_rows),
        "model_calls_total": sum(row["model_calls"] for row in ledger_rows),
        "wall_s_total": round(wall, 1),
        "model_s_total": round(model, 2),
        "pack_s_total": round(pack, 2),
        "pack_ready_s_total": round(sum(row["pack_ready_s"] for row in ledger_rows), 2),
        "other_s_total": round(other, 2),
        "unattributed_s_total": round(wall - model - pack - other, 2),
        "pack_share_of_wall_pct": round(100.0 * pack / wall, 3),
        "max_pack_s_one_question": max(row["pack_s"] for row in ledger_rows),
        "slowest_pack_question": max(ledger_rows, key=lambda row: row["pack_s"])["row_id"],
        # 拒发枚数与耗时同表出：判据 3 要说的是"慢与装箱无关"，那就得同时给出装箱拒了多少。
        "refused_total": len(refused_records(rows, sidecar)),
    }

def load_sidecar(path: str) -> list:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


TABLE_FIELDS = (
    "row_id", "leg", "room_total", "room_left", "candidates", "fitted", "dropped",
    "truncated", "stub", "packed_tokens", "delivered_before_tokens", "delivered_tokens",
    "measured_prompt_tokens", "unit_price_tokens", "packs",
)
REFUSED_FIELDS = TABLE_FIELDS + ("refused_seq",)
COST_FIELDS = (
    "row_id", "wall_s", "model_s", "pack_s", "pack_ready_s", "other_s", "model_calls",
    "pack_calls", "pack_ready_calls", "native_seconds", "native_tokens", "unattributed_s",
    "answer_chars", "evidence_n",
)


# ==================== 烘进仓库的 run5 实测表 ====================
#
# 出处：``%TEMP%\evalrun\backend-run5.log``（1 429 500 B，sha256 前 16 位
# ``d3e7e2b08900aed2``，UTF-16 LE）与 ``sidecar-run5.jsonl``（18 032 B，
# ``9ad2340f9826c7d9``），被测 rev ``27c676f``（跟进单 §62 二 · 看板 §4BH.12）。
# 逐行由本模块自己产出：``python scripts/perf_probe_run5_ledger.py --emit-table``
# 重跑一次就能比对；换日志重跑（run6…）就换这张表，别在测试里另算一套。
# 🔴 这四枚表只是"真机量到的数"，任何 room/实得/拒发都必须由被测函数现算，
#    测试里不许出现第二份 1606 / 954 / 2560。

MEASURED_PACKS_RUN5 = (
    ('doc-01', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1348, 0, 1348, 1440, 270, 1),
    ('doc-02', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1317, 0, 1317, 1412, 264, 1),
    ('doc-03', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1437, 0, 1437, 1531, 288, 1),
    ('doc-04', 'doc', 1606, 1606, 5, 4, 1, 0, 'none', 1278, 0, 1278, 1372, 320, 1),
    ('doc-05', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1152, 0, 1152, 1245, 231, 1),
    ('doc-06', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1223, 0, 1223, 1318, 245, 1),
    ('doc-07', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1595, 0, 1595, 1694, 319, 1),
    ('doc-08', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1479, 0, 1479, 1578, 296, 1),
    ('doc-09', 'doc', 1606, 1606, 5, 4, 1, 0, 'none', 1287, 0, 1287, 1382, 322, 1),
    ('doc-10', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1279, 0, 1279, 1372, 256, 1),
    ('doc-11', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1502, 0, 1502, 1596, 301, 1),
    ('doc-12', 'doc', 1606, 31, 5, 0, 5, 0, 'refused', 0, 1575, 1575, 1783, 246, 3),
    ('doc-13', 'doc', 1606, 775, 4, 2, 2, 0, 'none', 744, 831, 1575, 1681, 372, 2),
    ('doc-14', 'doc', 1606, 106, 5, 1, 4, 1, 'kept', 106, 1500, 1606, 1711, 252, 3),
    ('doc-15', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1583, 0, 1583, 1677, 317, 1),
    ('doc-16', 'doc', 1606, 42, 5, 0, 5, 0, 'refused', 0, 1564, 1564, 1883, 313, 3),
    ('doc-17', 'doc', 1606, 83, 5, 0, 5, 0, 'refused', 0, 1523, 1523, 1839, 381, 3),
    ('doc-18', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1498, 0, 1498, 1599, 300, 1),
    ('doc-19', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1440, 0, 1440, 1539, 288, 1),
    ('chat-01', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1437, 0, 1437, 1533, 288, 1),
    ('chat-02', 'doc', 1606, 1606, 4, 4, 0, 0, 'none', 1510, 0, 1510, 1619, 378, 1),
    ('chat-04', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1227, 0, 1227, 1321, 246, 1),
    ('chat-05', 'doc', 1606, 208, 5, 1, 4, 1, 'kept', 208, 1398, 1606, 1707, 350, 2),
    ('chat-07', 'doc', 1606, 97, 5, 1, 4, 1, 'kept', 97, 1509, 1606, 1719, 349, 3),
    ('chat-08', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1224, 0, 1224, 1324, 245, 1),
    ('chat-11', 'doc', 1606, 0, 4, 0, 4, 0, 'none', 0, 1606, 1606, 2050, 425, 6),
    ('metric-01', 'doc', 1606, 385, 4, 1, 3, 1, 'kept', 385, 1221, 1606, 1705, 407, 2),
    ('metric-02', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1370, 313, 1),
    ('metric-03', 'doc', 1606, 1606, 4, 4, 0, 0, 'none', 1321, 0, 1321, 1413, 331, 1),
    ('metric-04', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1162, 0, 1162, 1288, 291, 1),
    ('metric-05', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1162, 0, 1162, 1288, 291, 1),
    ('metric-06', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1377, 313, 1),
    ('metric-07', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1377, 313, 1),
    ('metric-08', 'doc', 1606, 55, 5, 0, 5, 0, 'refused', 0, 1551, 1551, 1770, 226, 3),
    ('metric-08', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1381, 313, 1),
    ('metric-09', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1247, 0, 1247, 1351, 250, 1),
    ('metric-10', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1414, 313, 1),
    ('metric-11', 'data', 1606, 11, 4, 0, 4, 0, 'refused', 0, 1595, 1595, 2012, 313, 4),
    ('metric-15', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1379, 313, 1),
    ('metric-16', 'doc', 1606, 82, 5, 0, 5, 0, 'refused', 0, 1524, 1524, 1846, 381, 3),
    ('metric-18', 'doc', 1606, 0, 5, 0, 5, 0, 'none', 0, 1606, 1606, 1801, 277, 3),
    ('metric-19', 'doc', 1606, 70, 5, 0, 5, 0, 'refused', 0, 1536, 1536, 1757, 276, 3),
    ('data-01', 'data', 1606, 7, 5, 0, 5, 0, 'none', 0, 1599, 1599, 2209, 221, 6),
    ('data-02', 'data', 1606, 13, 5, 0, 5, 0, 'refused', 0, 1593, 1593, 1928, 313, 4),
    ('data-03', 'data', 1606, 355, 4, 3, 1, 0, 'none', 132, 1251, 1383, 1553, 313, 2),
    ('data-04', 'doc', 1606, 346, 5, 1, 4, 0, 'none', 106, 1260, 1366, 1468, 315, 2),
    ('data-05', 'doc', 1606, 0, 4, 0, 4, 0, 'none', 0, 1606, 1606, 1787, 380, 3),
    ('data-06', 'doc', 1606, 0, 4, 0, 4, 0, 'none', 0, 1606, 1606, 1791, 291, 3),
    ('data-07', 'doc', 1606, 1606, 4, 4, 0, 0, 'none', 1512, 0, 1512, 1608, 378, 1),
    ('data-07', 'data', 1606, 26, 5, 0, 5, 0, 'refused', 0, 1580, 1580, 2044, 295, 5),
    ('data-08', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1476, 0, 1476, 1572, 296, 1),
    ('data-09', 'data', 1606, 312, 4, 3, 1, 0, 'none', 132, 1294, 1426, 1649, 291, 3),
    ('data-10', 'data', 1606, 444, 4, 3, 1, 0, 'none', 132, 1162, 1294, 1468, 291, 2),
    ('data-12', 'data', 1606, 155, 5, 2, 3, 0, 'none', 123, 1451, 1574, 1840, 246, 3),
    ('insight-01', 'data', 1606, 180, 4, 3, 1, 0, 'none', 132, 1426, 1558, 1791, 291, 4),
    ('insight-02', 'data', 1606, 31, 4, 0, 4, 0, 'refused', 0, 1575, 1575, 1924, 313, 5),
    ('insight-03', 'doc', 1606, 239, 5, 1, 4, 0, 'none', 198, 1367, 1565, 1668, 198, 3),
    ('insight-04', 'data', 1606, 412, 4, 3, 1, 0, 'none', 132, 1194, 1326, 1694, 299, 2),
    ('insight-05', 'doc', 1606, 217, 5, 1, 4, 0, 'none', 159, 1389, 1548, 1656, 259, 3),
    ('insight-06', 'data', 1606, 14, 5, 0, 5, 0, 'refused', 0, 1592, 1592, 1944, 313, 5),
    ('insight-07', 'data', 1606, 4, 4, 0, 4, 0, 'none', 0, 1602, 1602, 2418, 313, 9),
    ('chart-02', 'data', 1606, 223, 4, 3, 1, 0, 'none', 132, 1383, 1515, 1699, 313, 3),
    ('chart-04', 'data', 1606, 5, 4, 0, 4, 0, 'none', 0, 1601, 1601, 2327, 313, 8),
    ('approval-01', 'doc', 1606, 1606, 5, 5, 0, 0, 'none', 1296, 0, 1296, 1390, 260, 1),
    ('approval-02', 'doc', 1606, 337, 5, 1, 4, 0, 'none', 159, 1269, 1428, 1523, 318, 2),
    ('approval-03', 'doc', 1606, 103, 5, 1, 4, 1, 'kept', 103, 1503, 1606, 1711, 280, 3),
    ('approval-04', 'doc', 1606, 57, 4, 0, 4, 0, 'refused', 0, 1549, 1549, 1757, 297, 3),
    ('approval-05', 'doc', 1606, 158, 5, 1, 4, 1, 'kept', 158, 1448, 1606, 1708, 290, 2),
    ('approval-06', 'doc', 1606, 0, 4, 0, 4, 0, 'none', 0, 1606, 1606, 1791, 426, 3),
    ('scope-01', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1372, 313, 1),
    ('scope-02', 'doc', 1606, 100, 5, 1, 4, 1, 'kept', 100, 1506, 1606, 1705, 335, 3),
    ('scope-03', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1373, 313, 1),
    ('scope-06', 'doc', 1606, 15, 5, 0, 5, 0, 'refused', 0, 1591, 1591, 1805, 359, 3),
    ('unsupported-01', 'doc', 1606, 1606, 3, 3, 0, 0, 'none', 1293, 0, 1293, 1383, 431, 1),
    ('unsupported-02', 'doc', 1606, 352, 5, 1, 4, 0, 'none', 155, 1254, 1409, 1513, 251, 2),
    ('unsupported-03', 'data', 1606, 1606, 4, 4, 0, 0, 'none', 1251, 0, 1251, 1371, 313, 1),
    ('unsupported-04', 'doc', 1606, 1606, 5, 4, 1, 0, 'none', 1289, 0, 1289, 1380, 323, 1),
    ('tool-03', 'doc', 1606, 0, 5, 0, 5, 0, 'none', 0, 1606, 1606, 2760, 190, 15),
    ('report-01', 'doc', 1606, 341, 5, 1, 4, 0, 'none', 116, 1265, 1381, 1484, 230, 3),
    ('report-02', 'doc', 1606, 519, 5, 2, 3, 0, 'none', 418, 1087, 1505, 1608, 218, 2),
    ('report-04', 'doc', 1606, 0, 5, 0, 5, 0, 'none', 0, 1606, 1606, 2757, 316, 15),
    ('report-05', 'doc', 1606, 173, 5, 1, 4, 1, 'kept', 173, 1433, 1606, 1702, 359, 2),
    ('report-06', 'data', 1606, 1606, 5, 5, 0, 0, 'none', 1344, 0, 1344, 1466, 269, 1),
    ('report-07', 'doc', 1606, 675, 5, 2, 3, 0, 'none', 627, 931, 1558, 1661, 314, 2),
    ('report-08', 'doc', 1606, 205, 4, 1, 3, 0, 'none', 189, 1401, 1590, 1694, 281, 2),
    ('report-09', 'doc', 1606, 0, 5, 0, 5, 0, 'none', 0, 1606, 1606, 2068, 324, 6),
    ('report-10', 'doc', 1606, 272, 5, 1, 4, 1, 'kept', 272, 1334, 1606, 1710, 247, 3),
    ('report-11', 'data', 1606, 62, 5, 1, 4, 0, 'none', 60, 1544, 1604, 1882, 299, 4),
    ('report-12', 'doc', 1606, 47, 5, 0, 5, 0, 'refused', 0, 1559, 1559, 1778, 183, 3),
)

MEASURED_REFUSED_RUN5 = (
    ('doc-12', 'doc', 1606, 31, 5, 0, 5, 0, 'refused', 0, 1575, 1575, 1783, 246, 3, 1),
    ('doc-16', 'doc', 1606, 42, 5, 0, 5, 0, 'refused', 0, 1564, 1564, 1883, 313, 3, 1),
    ('doc-16', 'doc', 1606, 42, 5, 0, 5, 0, 'refused', 0, 1564, 1564, 1883, 313, 3, 2),
    ('doc-17', 'doc', 1606, 83, 5, 0, 5, 0, 'refused', 0, 1523, 1523, 1839, 381, 3, 1),
    ('doc-17', 'doc', 1606, 83, 5, 0, 5, 0, 'refused', 0, 1523, 1523, 1839, 381, 3, 2),
    ('metric-08', 'doc', 1606, 55, 5, 0, 5, 0, 'refused', 0, 1551, 1551, 1770, 226, 3, 1),
    ('metric-11', 'data', 1606, 11, 4, 0, 4, 0, 'refused', 0, 1595, 1595, 2012, 313, 4, 1),
    ('metric-16', 'doc', 1606, 82, 5, 0, 5, 0, 'refused', 0, 1524, 1524, 1846, 381, 3, 1),
    ('metric-16', 'doc', 1606, 82, 5, 0, 5, 0, 'refused', 0, 1524, 1524, 1846, 381, 3, 2),
    ('metric-19', 'doc', 1606, 70, 5, 0, 5, 0, 'refused', 0, 1536, 1536, 1757, 276, 3, 1),
    ('data-02', 'data', 1606, 13, 5, 0, 5, 0, 'refused', 0, 1593, 1593, 1928, 313, 4, 1),
    ('data-07', 'data', 1606, 26, 5, 0, 5, 0, 'refused', 0, 1580, 1580, 2044, 295, 5, 1),
    ('insight-02', 'data', 1606, 31, 4, 0, 4, 0, 'refused', 0, 1575, 1575, 1924, 313, 5, 1),
    ('insight-06', 'data', 1606, 14, 5, 0, 5, 0, 'refused', 0, 1592, 1592, 1944, 313, 5, 1),
    ('approval-04', 'doc', 1606, 57, 4, 0, 4, 0, 'refused', 0, 1549, 1549, 1757, 297, 3, 1),
    ('scope-06', 'doc', 1606, 15, 5, 0, 5, 0, 'refused', 0, 1591, 1591, 1805, 359, 3, 1),
    ('report-12', 'doc', 1606, 47, 5, 0, 5, 0, 'refused', 0, 1559, 1559, 1778, 183, 3, 1),
)

#: run5 里**整题没走到装箱**的撞墙题号：supervisor 直接终答 ⇒ ``[ASK] steps=0``、侧车
#: ``tool_calls=0``。没有实测 ``prompt_tokens`` 可复算就照实记账，别拿别的题的数顶替。
#: ``(题号, 侧车 tool_calls, [ASK] steps, answer_chars, wall_s)``
MEASURED_NOT_PACKED_RUN5 = (
    ('metric-17', 0, 0, 160, 9.1),
)
MEASURED_NOT_PACKED_IDS = tuple(row[0] for row in MEASURED_NOT_PACKED_RUN5)

#: run5 全部实测行（105 题 90 发）与 46 枚子集各自的壳中位数＝"装箱按估算多扣了房"的总尺子。
RUN5_SHELL_MEDIAN = 119
RUN5_SHELL_MEDIAN_PACKS = 185

MEASURED_COST_LONG_TAIL_RUN5 = (
    ('data-10', 177.8, 165.63, 0.018, 0.018, 11.82, 20, 2, 2, 0.0, 0, 0.36, 393, 0),
    ('insight-04', 160.3, 148.7, 0.185, 0.185, 10.32, 17, 2, 2, 0.0, 0, 1.09, 809, 0),
)

MEASURED_COST_RUN5_AGGREGATE = {'questions': 105, 'pack_lines': 282, 'model_calls_total': 593, 'wall_s_total': 4378.6, 'model_s_total': 3775.34, 'pack_s_total': 9.43, 'pack_ready_s_total': 4.87, 'other_s_total': 546.54, 'unattributed_s_total': 47.29, 'pack_share_of_wall_pct': 0.215, 'max_pack_s_one_question': 1.38, 'slowest_pack_question': 'chat-11', 'refused_total': 17}


# ==================== 判据 6：stub 台账三条腿的取证 ====================
#
# 出处：``python scripts/perf_probe_run5_ledger.py --format census``。这一张表只回答一件事：
# ``stub=`` 那套字段在真机上到底铺到了哪几条腿。定性（设计如此还是漏接）写在交付说明里，
# 本模块不修任何产品代码——补字段要动的文件不在本单写域内。

#: run5 全部 [PromptPack] 行按腿点名的行数与字段集（总账 282 枚）。
RUN5_PROMPT_PACK_CENSUS = {
    "doc": {"lines": 152, "stub_lines": 152, "ledger_lines": 152,
            "fields": ["candidates", "dropped", "dropped_labels", "fitted", "ledger",
                       "ledger_packed_tokens", "leg", "packed_tokens",
                       "prompt_estimate_tokens", "room_left", "room_total", "stub",
                       "tier", "truncated"]},
    "data": {"lines": 101, "stub_lines": 81, "ledger_lines": 81,
             "fields": ["candidates", "dataset", "dropped", "dropped_labels", "fitted",
                        "ledger", "ledger_packed_tokens", "leg", "packed_tokens",
                        "prompt_estimate_tokens", "recorded", "room_left", "room_total",
                        "stub", "tier", "truncated"]},
    "retrieval": {"lines": 29, "stub_lines": 0, "ledger_lines": 0,
                  "fields": ["candidates", "dropped", "dropped_sources", "fitted", "leg",
                             "packed_tokens", "room", "tier"]},
}
#: 装箱未送出时证据袋那一行的形状（recorded=false），它是另一种行，不是缺字段的装箱账。
RUN5_EVIDENCE_BAG_RECORD_LINES = 20
RUN5_EVIDENCE_BAG_FIELDS = ["dataset", "leg", "recorded"]


def pack_line_leg(body: str) -> str:
    """这一行 [PromptPack] 属于哪条腿（认 leg= 字段，不认就返回空串）。"""
    return fields_of(body).get("leg") or ""


def prompt_pack_census(rows: list) -> dict:
    """按腿点名：这一腿的 [PromptPack] 有几行、其中几行带 stub=、字段集是什么。"""
    out: dict = {}
    lines = [row for row in rows if PACK_MARKER in row.body]
    for row in lines:
        leg = pack_line_leg(row.body)
        if not leg:
            continue
        bucket = out.setdefault(leg, {"lines": 0, "stub_lines": 0, "ledger_lines": 0, "fields": set()})
        bucket["lines"] += 1
        bucket["stub_lines"] += 1 if "stub=" in row.body else 0
        bucket["ledger_lines"] += 1 if LEDGER_FIELD in row.body else 0
        bucket["fields"] |= {k for k in fields_of(row.body) if _ASCII_FIELD.fullmatch(k)}
    for bucket in out.values():
        bucket["fields"] = sorted(bucket["fields"])
    bag = [row for row in rows if EVIDENCE_BAG_MARK in row.body]
    out["_total_pack_lines"] = len(lines)
    out["_evidence_bag_lines"] = len(bag)
    out["_evidence_bag_fields"] = sorted({
        key for row in bag for key in fields_of(row.body) if _ASCII_FIELD.fullmatch(key)
    })
    return out

# ==================== 判据 5：合成料 vs 真机料（今天重量的倍率） ====================
#
# 出处：``python scripts/perf_probe_run5_ledger.py --format hits``（读 run5 保全日志）＋
# ``text_pack_tokens(探针自己的单条合成料)``。09-19 当晚写在 ``perf_probe_rounds.py`` 里的
# "~4x" 是拿 500 字符合成料去比 ``real_chunk_text()`` 的 116 字符兜底串——本树 ``documents/``
# 里 0 枚 .md（95 .txt + 2 .pdf），那 116 字符从来不是真语料。按真机逐条命中重量，
# 今天的倍率是 ``RUN5_SYNTHETIC_UNIT_TOKENS / RUN5_DOC_HIT_MEDIAN_TOKENS``。

#: 探针合成的那一条命中（行头 + 正文上限）按被测尺子值多少枚。
RUN5_SYNTHETIC_UNIT_TOKENS = 445
#: run5 全部 doc 腿**整条送出**的命中逐条摊平后的中位数（枚/条）。
RUN5_DOC_HIT_MEDIAN_TOKENS = 275  # 真机量到 275.3，取整入表，别让测试去凑小数
#: 上面那枚中位数的样本量。
RUN5_DOC_HIT_MEDIAN_N = 321


def doc_hit_prices(rows: list) -> list:
    """把 run5 里 doc 腿**整条送出**（``truncated=0`` 且 ``fitted>0``）的每一条命中摊平成单条枚数。"""
    prices = []
    for start, end in segments(rows):
        for _index, data in pack_lines(rows, start, end, leg="doc"):
            fitted, packed = int(data["fitted"]), int(data["packed_tokens"])
            if fitted > 0 and int(data["truncated"]) == 0:
                prices.extend([packed / fitted] * fitted)
    return sorted(prices)


def doc_hit_price_stats(rows: list) -> dict:
    """``doc_hit_prices`` 的分位数摘要：合成料倍率的真机分母从这里来。"""
    prices = doc_hit_prices(rows)
    if not prices:
        raise LogFormatError("doc 腿没有任何整条送出的发，合成料倍率算不出来")

    def quantile(fraction: float) -> float:
        return prices[min(len(prices) - 1, int(fraction * len(prices)))]

    return {
        "n": len(prices),
        "min": round(prices[0], 1),
        "p25": round(quantile(0.25), 1),
        "median": round(statistics.median(prices), 1),
        "p75": round(quantile(0.75), 1),
        "max": round(prices[-1], 1),
    }


def synthetic_overstatement_ratio(synthetic_tokens: int = None, real_median: int = None) -> float:
    """合成单条料比真机单条命中贵多少倍：分子现量（走被测尺子），分母默认烘进来的真机中位数。"""
    tokens = RUN5_SYNTHETIC_UNIT_TOKENS if synthetic_tokens is None else int(synthetic_tokens)
    median = RUN5_DOC_HIT_MEDIAN_TOKENS if real_median is None else int(real_median)
    if tokens <= 0 or median <= 0:
        raise ValueError("倍率两头都得是正数：synthetic=%r median=%r" % (tokens, median))
    return round(tokens / median, 2)

def records(table: tuple, order: tuple) -> list:
    """把烘进仓库的实测行还原成字典：表里只有数，没有第二把尺。"""
    return [dict(zip(order, row)) for row in table]


def as_tuple(record: dict, order: tuple) -> str:
    return "(%s)" % ", ".join(repr(record[key]) for key in order)


def emit_table(records: list, name: str, order: tuple) -> str:
    lines = ["%s = (" % name]
    for record in records:
        lines.append("    " + as_tuple(record, order) + ",")
    lines.append(")")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="真机装箱台账复算（R116）")
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--sidecar", default=DEFAULT_SIDECAR)
    parser.add_argument("--capacity", type=int, default=None,
                        help="容量真源；不给就走 context_pack_capacity()，取不到就硬失败（不许回退默认值）")
    parser.add_argument("--estimated-room", type=int, default=None)
    parser.add_argument(
        "--format",
        choices=("refused", "cost", "ledger", "counterfactual", "hits", "census", "pins"),
        default="refused",
    )
    parser.add_argument("--emit-table", action="store_true")
    args = parser.parse_args(argv)

    rows = read_backend_log(args.log)
    sidecar = load_sidecar(args.sidecar)
    if args.emit_table:
        print(emit_table(ledger(rows, sidecar), "MEASURED_PACKS_RUN5", TABLE_FIELDS))
        print(emit_table(refused_records(rows, sidecar), "MEASURED_REFUSED_RUN5", REFUSED_FIELDS))
        print(emit_table(cost_ledger(rows, sidecar), "MEASURED_COST_RUN5", COST_FIELDS))
        return 0
    if args.format == "cost":
        for record in cost_ledger(rows, sidecar):
            print(json.dumps(record, ensure_ascii=False))
        return 0
    if args.format == "pins":
        capacity, estimated = source_room()
        if capacity is None:
            raise SystemExit("pins 取不到被测真源的容量与估算 room：不许回退抄来的常数")
        for record in ledger(rows, sidecar):
            print(json.dumps(pin_account(record, capacity, estimated), ensure_ascii=False))
        return 0
    if args.format == "census":

        print(json.dumps(prompt_pack_census(rows), ensure_ascii=False, indent=1,
                           sort_keys=True))
        return 0
    if args.format == "hits":
        stats = doc_hit_price_stats(rows)
        print(json.dumps(stats, ensure_ascii=False))
        print("synthetic_unit_tokens=%d ratio=%.2f" % (
            RUN5_SYNTHETIC_UNIT_TOKENS, synthetic_overstatement_ratio(real_median=stats["median"])))
        return 0
    packs = ledger(rows, sidecar)
    if args.format == "ledger":
        for record in packs:
            print(json.dumps(record, ensure_ascii=False))
        return 0
    source = refused_records(rows, sidecar) if args.format == "refused" else packs
    capacity, estimated_room = args.capacity, args.estimated_room
    if capacity is None:
        capacity, estimated_room = source_room()
    for record in source:
        if capacity is None:
            print(json.dumps(record, ensure_ascii=False))
            continue
        billed = estimated_room if estimated_room is not None else record["room_total"]
        print(json.dumps(counterfactual(record, capacity, billed), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
