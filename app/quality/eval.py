import json
import math
import statistics
from pathlib import Path

#: R123 甲案（跟进单 §57 三选一里业主 09-20 裁定的那一案）：采集器把「批准前那一帧」和
#: 「批准结果」写进侧车（scripts/eval_transport_ask_v2.py 的 _record），评分端据此同时给出
#: 两把尺。下面的键名与采集器逐字对得上，不在这另起一套口径。
APPROVAL_KIND = "approved_ok"
APPROVAL_FAILED_KIND = "approval_failed"
HITL_PRE_KIND = "hitl"


def evaluate_golden_set(path: str | Path, answer_fn) -> dict:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    total = len(rows)
    exact = 0
    relevancy = 0
    for row in rows:
        pred = str(answer_fn(row["question"]))
        gold = str(row["answer"])
        if pred.strip() == gold.strip():
            exact += 1
        if pred and gold and (gold[:4] in pred or pred[:4] in gold or pred.strip() == gold.strip()):
            relevancy += 1
    return {
        "total": total,
        "exact_match": round(exact / total, 2) if total else 0.0,
        "answer_relevancy": round(relevancy / total, 2) if total else 0.0,
    }


def _confidence_label(confidence: float | int | None) -> str:
    value = float(confidence or 0)
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def evaluate_provenance(answer: dict) -> dict:
    evidence = answer.get("evidence") or []
    claims = answer.get("claims") or []
    supported = [claim for claim in claims if claim.get("supported") is True]
    unsupported = [
        str(claim.get("text", "")).strip()
        for claim in claims
        if claim.get("supported") is False and str(claim.get("text", "")).strip()
    ]
    coverage = len(supported) / len(claims) if claims else (1.0 if evidence else 0.0)
    return {
        "has_evidence": bool(evidence),
        "evidence_coverage": round(coverage, 4),
        "confidence_label": answer.get("confidence_label")
        or _confidence_label(answer.get("confidence")),
        "unsupported_claims": unsupported,
    }


def _answer_text(result) -> str:
    if isinstance(result, dict):
        return str(result.get("answer", ""))
    return str(result)


def _is_correct(row: dict, result) -> bool:
    text = _answer_text(result)
    expected = [str(item) for item in row.get("must_contain", [])]
    if expected:
        return all(item in text for item in expected)
    answer = str(row.get("answer", "")).strip()
    return bool(answer) and answer in text


def load_approval_ledger(path: str | Path) -> dict[str, dict]:
    """读采集侧车（append-only 的逐题账），按题号留最后一行。

    显式指定了账本却找不到文件 ⇒ 硬失败：把「没有账本」当成「批准失败 0 题」是静默撒谎。
    半行（跑分中途被 kill 留下的）跳过：它不是一条记录，但也不该炸掉一份能出的报告。
    """
    ledger_path = Path(path)
    if not ledger_path.exists():
        raise FileNotFoundError(
            f"批准账本不存在：{ledger_path}（显式指定过它，就不能当没看见）")
    rows: dict[str, dict] = {}
    for line in ledger_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and str(row.get("id", "")):
            rows[str(row["id"])] = row
    return rows


def summarize_approval_ledger(fixture_rows: list[dict], ledger: dict[str, dict]) -> dict:
    """判据 4 那一行的数据源：本轮经审批取得终答 N 题 / 批准失败 M 题。"""
    fixture_ids = {str(row.get("id", "")) for row in fixture_rows}
    hitl_pre = [row for row in ledger.values() if row.get("pre_kind") == HITL_PRE_KIND]
    approved = [row for row in ledger.values() if row.get("kind") == APPROVAL_KIND]
    failed = [row for row in ledger.values() if row.get("kind") == APPROVAL_FAILED_KIND]
    return {
        "hitl_pre_n": len(hitl_pre),
        "hitl_pre_ids": sorted(str(row.get("id")) for row in hitl_pre),
        "approved_final_n": len(approved),
        "approved_final_ids": sorted(str(row.get("id")) for row in approved),
        "approval_failed_n": len(failed),
        "approval_failed_ids": sorted(str(row.get("id")) for row in failed),
        "ledger_rows": len(ledger),
        "ledger_rows_not_in_fixture": sorted(set(ledger) - fixture_ids),
    }


def pre_approval_ruler(results: list[dict], ledger: dict[str, dict]) -> dict:
    """旧口径重算：分母仍是全部 105 题，但卡在闸上的题拿「批准前那一帧」去计分。

    run2..run5 的 answers 文件里，那 18 枚存的就是「等待确认」park 文本 ⇒ 这个数就是
    它们当时的 correctness（判据 2 要的两个数之一，另一枚是主报告本身）。证据侧只用
    「有没有出处」这个布尔，因为采集器从不交 claims，per 行 evidence_coverage 与它同值。
    """
    total = len(results)
    correct = 0
    evidence_ok = 0
    substituted = 0
    for item in results:
        row = item["row"]
        ledger_row = ledger.get(str(row.get("id", ""))) or {}
        if "pre_answer" in ledger_row:
            substituted += 1
            answer_text = str(ledger_row.get("pre_answer") or "")
            has_evidence = int(ledger_row.get("pre_evidence_n") or 0) > 0
        else:
            answer_text = _answer_text(item["result"])
            has_evidence = item["provenance"]["has_evidence"]
        if _is_correct(row, {"answer": answer_text}):
            correct += 1
        if has_evidence or not row.get("requires_evidence", False):
            evidence_ok += 1
    return {
        "total": total,
        "answer_correctness": round(correct / total, 4) if total else 0.0,
        "evidence_coverage": round(evidence_ok / total, 4) if total else 0.0,
        "substituted_rows": substituted,
        "basis": "卡闸的题按侧车 pre_answer / pre_evidence_n 计分＝run2..run5 口径；分母不变",
    }


def format_approval_line(report: dict) -> str:
    """判据 4 要「多印的那一行」。没有账本时返回空串：印一行假的「批准失败 0」比不印更坏。"""
    summary = report.get("approval_ledger")
    if not summary:
        return ""
    ruler = report.get("pre_approval_ruler") or {}
    return (
        f"approval: 本轮经审批取得终答的题数 {summary['approved_final_n']} / 批准失败 "
        f"{summary['approval_failed_n']}"
        f"（批准前卡在闸上 {summary['hitl_pre_n']} 题，账本 {summary['ledger_rows']} 行）"
        f" ｜ correctness 甲案 {report['answer_correctness']:.4f}"
        f" / 旧口径 {ruler.get('answer_correctness', 0.0):.4f}"
        f" ｜ evidence 甲案 {report['evidence_coverage']:.4f}"
        f" / 旧口径 {ruler.get('evidence_coverage', 0.0):.4f}"
    )


# ===== R205a：时延记账（跟进单 §93.9）=============================================
#
# run6 正式报告里 latency_ms.average = 351 121 ms 比逐题最大值（诚实的 272.2 s）还大。
# 起因在采集器：载荷不自报 latency_ms 时，它拿自己 perf_counter 的**整调用跨度**冒充
# 「这一发的时延」（scripts/collect_evaluation_answers.py 的 _latency_ms），而采集适配器
# 是故意不自报的。整调用跨度里含被打回的重试、重试 sleep，以及 09-23 23:34 → 09-24 07:40
# 那段 8 h 6 min 整机待机 —— 它不是「每发尝试自己的真实跨度」。诚实的那一发在帧账 sidecar
# 的 wall_ms 里（适配器每次尝试开头重取时间、重试不记账），而这份账本评分时本来就要读
# （R123 甲案），所以时延与它同源核对，不再各说各话。
#
# 规则（写在数上，不写在题号上）：
#   ① 有帧账可对：实测值不超过帧账跨度的容忍带 ⇒ 两者本就是同一发，按实测进聚合；
#      越过容忍带 ⇒ 这一发解释不了，改用帧账的逐发跨度（repaired_to_frame_ledger）；
#   ② 没有帧账可对：实测值仍在一发量级之内才允许进聚合；否则该题排除并逐题列出；
#   ③ 这一发压根没有可用实测（载荷没自报，或被采集器按量级拒记 ⇒ answers 行那格记 null）：
#      帧账 wall_ms 在一发量级之内就直接顶上（recovered_from_frame_ledger）；两边都拿不出
#      诚实跨度，才落进 count < total 那个既有出口。读不成毫秒的读数同样不许静默消失。
#   ④ 聚合出的格子必须自洽：average ≤ max，且 average / max 都不许越过帧账给出的诚实
#      上界。任何一条不成立 ⇒ 当场 LatencyAccountingError，这份报告不出。
# 被 ①②③ 处置过的题逐条列在 latency_ms.suspect：谁、原读数多少、帧账多少、最终用了谁。
# 🔴 两把尺各管一件事，不许混用：量级上限问「这还像不像一发尝试」（run6 那发 8 h 待机），
#    帧账容忍带问「这是不是这一发的跨度」（run6 另外三枚 6.5~523 倍的重试虚高）。
#    源头那道守卫（采集器 _latency_ms）只管前者，所以重试虚高那一类仍要靠这里的帧账对账。

#: 实测值与帧账 wall_ms 的容忍带：倍差 1.25 + 固定 2 s，两个数量级的余量，不是题号白名单。
#: 下界依据（前任按 run6 逐题实录归纳，本班**没能复核**：仓内与 %TEMP% 都没有 run6 的 answers/
#: sidecar 原件，只有 §93.0 的汇总数）——无重试题两数差 <0.1%（最大约 4 ms，是采集器在适配器之外
#: 多花的登录/节拍/记账），三枚越界题差 6.5~523 倍。本班能证的那一半在
#: tests/test_r205a_latency_ledger.py：带上沿逐字是 limit，越出去才换帧账。
LATENCY_LEDGER_RATIO_TOLERANCE = 1.25
LATENCY_LEDGER_SLACK_MS = 2000.0

#: 一发尝试的量级上限 = 模型单发请求超时（全仓唯一读点在 app/common/model_budget.py）× 本倍数：采集器整调用最多含 EVAL_ATTEMPTS
#: （默认 3）发模型请求 + 两枚 EVAL_RETRY_SLEEP（默认 20 s）+ 排队轮询观测窗，再往上一个
#: 数量级就不可能是「一发的真实跨度」。上限走唯一读者 latency_envelope_ms()，这里不另存
#: 那个超时常量（app/common/model_budget.py 是它全仓唯一的读点）。
LATENCY_ENVELOPE_TIMEOUT_MULTIPLES = 8.0

#: 同一个数四舍五入两次之内的差，不算「平均值大于逐题最大值」。
LATENCY_ROUNDING_TOLERANCE_MS = 0.01

LATENCY_ACTION_KEPT = "kept"
LATENCY_ACTION_REPAIRED = "repaired_to_frame_ledger"
#: 没有可用实测、但帧账那一发的跨度可用 ⇒ 用帧账顶上（逐题列出，不静默补数）。
LATENCY_ACTION_RECOVERED = "recovered_from_frame_ledger"
LATENCY_ACTION_EXCLUDED = "excluded_without_honest_span"
LATENCY_ACTION_ABSENT = "not_measured"

LATENCY_BASIS = (
    "latency_ms 只由每发尝试自己的真实跨度构成：与帧账 wall_ms 相符者按实测进聚合，"
    "越界者按帧账逐发跨度替换，无实测而帧账可用者按帧账顶上，"
    "拿不出诚实跨度的题排除并逐题列在 suspect"
)


class LatencyAccountingError(RuntimeError):
    """报告的 latency_ms 出现了「平均值大于逐题最大值」这类不可能形状。"""


def latency_envelope_ms() -> float:
    """一发尝试的量级上限：读 app.common.model_budget 里那个唯一的超时上限。"""
    from app.common.model_budget import request_timeout_ceiling_seconds

    return request_timeout_ceiling_seconds() * 1000.0 * LATENCY_ENVELOPE_TIMEOUT_MULTIPLES


def _span_ms(value) -> float | None:
    """把一格时延读数读成非负毫秒；读不出来就是 None —— 不猜、不补、不当 0 用。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _latency_verdict(action, used_ms, *, corroborated, row) -> dict:
    """分类结论的统一形状：row 为 None 表示这一题不需要被逐题列出。"""
    return {"action": action, "used_ms": used_ms, "corroborated": corroborated, "row": row}


def classify_latency_span(row_id, reported_ms, frame_ledger_ms, *, envelope_ms: float) -> dict:
    """这一发的实测读数能不能算「每发尝试自己的真实跨度」，以及最终用哪个数。

    返回 {"action", "used_ms", "corroborated", "row"}：row 只在该题需要被逐题列出时非空。
    两把尺各问一件事：envelope_ms 问「这还像不像一发尝试」，帧账容忍带问「这是不是这一发」。
    """
    reported = _span_ms(reported_ms)
    ledger = _span_ms(frame_ledger_ms)
    # 帧账自己也得先过量级这一关：越出一发量级的 wall_ms 不是诚实跨度，不能拿去替换别人。
    ledger_span = ledger if ledger is not None and ledger <= envelope_ms else None

    if reported is not None:
        row = {"id": str(row_id), "reported_ms": reported, "frame_ledger_ms": ledger}
        if ledger is None:
            # 规则②：没有帧账可对，只剩量级这一把尺。
            if reported <= envelope_ms:
                return _latency_verdict(LATENCY_ACTION_KEPT, reported,
                                        corroborated=False, row=None)
            row["reason"] = (
                f"实测 {reported} ms 越出一发量级上限 {envelope_ms} ms，且这一题没有帧账可对"
                " ⇒ 没有可信的逐发跨度可替换")
            return _latency_verdict(LATENCY_ACTION_EXCLUDED, None,
                                    corroborated=False, row=row)
        # 规则①：有帧账可对，两数同带就说明它们本就是同一发。
        limit = round(ledger * LATENCY_LEDGER_RATIO_TOLERANCE + LATENCY_LEDGER_SLACK_MS, 2)
        if reported <= limit:
            return _latency_verdict(LATENCY_ACTION_KEPT, reported,
                                    corroborated=True, row=None)
        if ledger_span is not None:
            row["reason"] = (
                f"实测 {reported} ms 超过帧账逐发跨度 {ledger} ms 的容忍带 {limit} ms"
                "（被打回的重试或被冻的整机待机被算了进来）⇒ 改用帧账那一发的跨度")
            return _latency_verdict(LATENCY_ACTION_REPAIRED, ledger_span,
                                    corroborated=True, row=row)
        row["reason"] = (
            f"实测 {reported} ms 越出容忍带 {limit} ms，帧账 {ledger} ms 自己也越出一发量级上限"
            f" {envelope_ms} ms ⇒ 两边都不可信")
        return _latency_verdict(LATENCY_ACTION_EXCLUDED, None,
                                corroborated=False, row=row)

    # 规则③：这一发没有可用实测——载荷没自报、被采集器按量级拒记（latency_ms 记 null），
    # 或者字面上读不成毫秒。帧账能用就直接顶上并逐题列出，两条都不通才不计入聚合。
    if ledger_span is not None:
        reason = ("这一发没有可用的实测读数（载荷未自报或被采集器拒记 ⇒ 看该题 answers 行的"
                  " latency_suspect）⇒ 用帧账 wall_ms 那一发的真实跨度")
        if reported_ms is not None:
            reason = f"实测读数 {reported_ms!r} 读不成毫秒 ⇒ 改用帧账 wall_ms 那一发的真实跨度"
        return _latency_verdict(
            LATENCY_ACTION_RECOVERED, ledger_span, corroborated=True,
            row={"id": str(row_id), "reported_ms": None, "frame_ledger_ms": ledger,
                 "reason": reason})
    if reported_ms is None and ledger is None:
        # 没测到不等于测得假：count 小于 total 就是这一格的既有出口，不另造形状。
        return _latency_verdict(LATENCY_ACTION_ABSENT, None, corroborated=False, row=None)
    row = {"id": str(row_id), "reported_ms": reported, "frame_ledger_ms": ledger}
    row["reason"] = (
        "这一发既没有可用的实测读数"
        + ("（未自报）" if reported_ms is None else f"（实测读数 {reported_ms!r} 读不成毫秒）")
        + "，帧账那一发也不可用"
        + (f"（wall_ms {ledger} ms 越出一发量级上限 {envelope_ms} ms）"
           if ledger is not None else "（帧账没有这一题）")
        + " ⇒ 不计入聚合")
    return _latency_verdict(LATENCY_ACTION_EXCLUDED, None, corroborated=False, row=row)


def guard_latency_cell(cell: dict, *, honest_max_ms: float | None = None) -> None:
    """时延格子的自洽闸：不可能形状在这里炸，不许变成一份能看的报告。"""
    if not cell.get("count"):
        return
    average = cell["average"]
    highest = cell["max"]
    if average > highest + LATENCY_ROUNDING_TOLERANCE_MS:
        raise LatencyAccountingError(
            f"latency_ms 平均值 {average} 大于逐题最大值 {highest}"
            " ⇒ 聚合里混进了不同源的数（run6 那一格就是这么来的）")
    if honest_max_ms is None:
        return
    ceiling = honest_max_ms * LATENCY_LEDGER_RATIO_TOLERANCE + LATENCY_LEDGER_SLACK_MS
    if highest > ceiling or average > ceiling:
        raise LatencyAccountingError(
            f"latency_ms 越出帧账的诚实上界 {round(ceiling, 2)} ms（逐题帧账最大跨度 "
            f"{honest_max_ms} ms）：max={highest} average={average}"
            " ⇒ 平均值里仍有不是「一发尝试」的跨度")


def build_latency_cell(values, *, honest_max_ms: float | None = None) -> dict:
    """把「已经可信的逐发跨度」汇成报告那一格，并当场自证自洽。

    p95 的排名规则沿用既有那一把（与 app/common/performance.py::PerformanceStats 对齐，
    由 tests/test_r105_slo_contract.py 钉住），这里只补上逐题最大值 max 那一格。
    """
    latencies = sorted(item for item in (_span_ms(value) for value in values)
                       if item is not None)
    if not latencies:
        cell = {"count": 0, "average": 0, "p95": 0, "max": 0}
    else:
        rank = max(1, math.ceil(len(latencies) * 0.95))
        cell = {
            "count": len(latencies),
            "average": round(statistics.mean(latencies), 2),
            "p95": latencies[min(len(latencies) - 1, rank - 1)],
            "max": latencies[-1],
        }
    guard_latency_cell(cell, honest_max_ms=honest_max_ms)
    return cell


def aggregate_latency_ms(spans, *, envelope_ms: float | None = None) -> dict:
    """逐题「实测 + 帧账」两列读数 → 报告里那一格时延。

    spans 每项形如 {"id", "reported_ms", "frame_ledger_ms"}；被替换、被顶上、被排除的题按传入
    顺序逐条落进 cell["suspect"]，一条都不许默默消失。
    """
    ceiling_one = _span_ms(envelope_ms)
    if ceiling_one is None:
        ceiling_one = latency_envelope_ms()
    values: list[float] = []
    honest_spans: list[float] = []
    suspect: list[dict] = []
    corroborated = 0
    for span in spans:
        ledger = _span_ms(span.get("frame_ledger_ms"))
        verdict = classify_latency_span(span.get("id"), span.get("reported_ms"), ledger,
                                        envelope_ms=ceiling_one)
        if ledger is not None and ledger <= ceiling_one:
            # 诚实上界取全部可用的逐发帧账跨度，不以「这次有没有用上它」为条件。
            honest_spans.append(ledger)
        if verdict["row"] is not None:
            verdict["row"]["action"] = verdict["action"]
            verdict["row"]["used_ms"] = verdict["used_ms"]
            suspect.append(verdict["row"])
        if verdict["used_ms"] is None:
            continue
        values.append(verdict["used_ms"])
        if verdict["corroborated"]:
            corroborated += 1
    cell = build_latency_cell(
        values, honest_max_ms=max(honest_spans) if honest_spans else None)
    cell["frame_ledger_rows"] = corroborated
    cell["one_attempt_envelope_ms"] = ceiling_one
    cell["suspect_n"] = len(suspect)
    cell["suspect"] = suspect
    cell["basis"] = LATENCY_BASIS
    return cell


def evaluate_evaluation_set(path: str | Path, answer_fn, *, approval_ledger: str | Path | None = None) -> dict:
    """给一套夹具与一个取答案的函数，产出报告；给了批准账本就在同一份报告里加两把尺。

    🔴 分母不因为甲案而变（判据 4）：`total` 与 `answer_correctness` 恒按全部题数算，
    卡闸的题现在拿真终答进分母，旧口径要的那个数在 `pre_approval_ruler` 里。

    R205a：`latency_ms` 那一格不再由「载荷里有什么就算什么」决定，改由
    `aggregate_latency_ms` 对着帧账逐发记账（跟进单 §93.9 ①）；账本读不出来就当场
    `LatencyAccountingError`，这份报告不出。
    """
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    # 同一份侧车既是批准账本，也是「每发尝试自己的跨度」的帧账（R123 甲案读的就是它）。
    # 🔴 先读账本再取答案：账本缺失要在打模型之前炸，不许跑完 105 题才发现没法对账。
    ledger: dict[str, dict] = {}
    if approval_ledger is not None:
        ledger = load_approval_ledger(approval_ledger)
    results = []
    for row in rows:
        result = answer_fn(row)
        provenance = evaluate_provenance(result if isinstance(result, dict) else {})
        latency = result.get("latency_ms") if isinstance(result, dict) else None
        results.append(
            {
                "row": row,
                "result": result,
                "correct": _is_correct(row, result),
                "provenance": provenance,
                "evidence_ok": (
                    not row.get("requires_evidence", False)
                    or provenance["has_evidence"]
                ),
                "latency_ms": float(latency) if latency is not None else None,
            }
        )

    def ratio(values):
        return round(sum(bool(value) for value in values) / len(values), 4) if values else 0.0

    # 两列读数一起交给记账闸：answers 行的实测（载荷自报，或采集器当时的整调用跨度）与
    # 帧账 sidecar 的逐发 wall_ms。谁配进聚合由 aggregate_latency_ms 判，不由这里猜。
    latency_spans = [
        {
            "id": item["row"].get("id"),
            "reported_ms": item["latency_ms"],
            "frame_ledger_ms": (ledger.get(str(item["row"].get("id", ""))) or {}).get("wall_ms"),
        }
        for item in results
    ]
    category_metrics = {}
    for item in results:
        category = item["row"].get("category", "未分类")
        bucket = category_metrics.setdefault(
            category, {"total": 0, "correct": 0, "evidence": 0.0}
        )
        bucket["total"] += 1
        bucket["correct"] += int(item["correct"])
        bucket["evidence"] += item["provenance"]["evidence_coverage"]
    for bucket in category_metrics.values():
        total = bucket.pop("total")
        correct = bucket.pop("correct")
        evidence = bucket.pop("evidence")
        bucket["correctness"] = round(correct / total, 4) if total else 0.0
        bucket["evidence_coverage"] = round(evidence / total, 4) if total else 0.0
        bucket["total"] = total

    report = {
        "total": len(rows),
        "answer_correctness": ratio([item["correct"] for item in results]),
        "evidence_coverage": ratio([item["evidence_ok"] for item in results]),
        "unsupported_claim_rate": round(
            sum(bool(item["provenance"]["unsupported_claims"]) for item in results)
            / len(results),
            4,
        )
        if results
        else 0.0,
        "category_metrics": category_metrics,
        "latency_ms": aggregate_latency_ms(latency_spans),
    }
    if approval_ledger is not None:
        report["approval_ledger"] = summarize_approval_ledger(rows, ledger)
        report["pre_approval_ruler"] = pre_approval_ruler(results, ledger)
        report["approval_line"] = format_approval_line(report)
    return report
