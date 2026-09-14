import json
import math
import statistics
from pathlib import Path


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


def evaluate_evaluation_set(path: str | Path, answer_fn) -> dict:
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
    return {
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
