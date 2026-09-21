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


def evaluate_evaluation_set(path: str | Path, answer_fn, *, approval_ledger: str | Path | None = None) -> dict:
    """给一套夹具与一个取答案的函数，产出报告；给了批准账本就在同一份报告里加两把尺。

    🔴 分母不因为甲案而变（判据 4）：`total` 与 `answer_correctness` 恒按全部题数算，
    卡闸的题现在拿真终答进分母，旧口径要的那个数在 `pre_approval_ruler` 里。
    """
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
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

    latencies = sorted(
        item["latency_ms"] for item in results if item["latency_ms"] is not None
    )
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

    p95 = 0
    if latencies:
        rank = max(1, math.ceil(len(latencies) * 0.95))
        p95 = latencies[min(len(latencies) - 1, rank - 1)]
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
        "latency_ms": {
            "count": len(latencies),
            "average": round(statistics.mean(latencies), 2) if latencies else 0,
            "p95": p95,
        },
    }
    if approval_ledger is not None:
        ledger = load_approval_ledger(approval_ledger)
        report["approval_ledger"] = summarize_approval_ledger(rows, ledger)
        report["pre_approval_ruler"] = pre_approval_ruler(results, ledger)
        report["approval_line"] = format_approval_line(report)
    return report
