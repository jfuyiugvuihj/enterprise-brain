"""Evidence gathered by tool boundaries during one Agent execution.

The evidence bag travels inside the LangGraph ``configurable`` mapping, so parallel
workers keep separate bags and no execution can inherit another caller's evidence.
Tool boundaries record what they actually retrieved; nothing is reconstructed from
the answer text afterwards.
"""
from __future__ import annotations

import hashlib
from typing import Any, get_args

from app.agents.contracts import AgentResult, ArtifactRef, ErrorEnvelope, Evidence, MetricContext

BAG_KEY = "evidence_bag"
_EXCERPT_LIMIT = 400

_RETRIABLE_CODES = {"model_unavailable", "retrieval_unavailable", "task_timeout", "rate_limited", "queue_unavailable"}


def _enum_error_codes(model=ErrorEnvelope) -> frozenset[str]:
    """错误码词表的唯一来源：``ErrorEnvelope.code``。

    这里原本手抄了一份 16 码字面量集合，而枚举当时已有 18 码。抄漏的那两档
    （``account_unavailable``、``storage_unavailable``）会撞上
    ``code=error_code if error_code in _ERROR_CODES else "internal_error"``：
    一个线上真在吐的稳定码，在证据边界上被洗成了通用内部错。所以第二份手抄码表
    本身就是缺陷，不是风格问题——``tests/test_error_code_vocabulary.py`` 同时钉
    "两份相等"与"它是从枚举派生的"（换合成模型码表要跟着变）。
    """
    return frozenset(get_args(model.model_fields["code"].annotation))


_ERROR_CODES = _enum_error_codes()


def new_evidence_bag() -> dict[str, list[Any]]:
    return {
        "documents": [],
        "datasets": [],
        "artifacts": [],
        "metrics": [],
        "tool_statuses": [],
        "model_statuses": [],
    }


def bag_from_config(config: Any) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    bag = configurable.get(BAG_KEY)
    return bag if isinstance(bag, dict) else None


def _digest(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:16]


def record_document_hits(bag: dict[str, Any] | None, *, query: str, hits: list[dict]) -> int:
    if bag is None:
        return 0
    recorded = 0
    for hit in hits or []:
        if not isinstance(hit, dict):
            continue
        source = str(hit.get("source") or "unknown")
        chunk_index = hit.get("chunk_index")
        try:
            score = float(hit.get("_score"))
        except (TypeError, ValueError):
            score = None
        bag["documents"].append(
            {
                "source_name": source,
                "source_id": f"{source}#chunk={chunk_index if chunk_index is not None else ''}",
                "locator": {"chunk_index": chunk_index if chunk_index is not None else None},
                "excerpt": str(hit.get("content") or "")[:_EXCERPT_LIMIT],
                "score": score,
                "score_type": "rerank" if score is not None else None,
                "permission_checked": True,
                "provenance_status": "verified",
                "metadata": {
                    "query": str(query or "")[:200],
                    "classification": hit.get("classification"),
                    "department": hit.get("department"),
                    "content_sha256": hashlib.sha256(str(hit.get("content") or "").encode("utf-8")).hexdigest(),
                },
            }
        )
        recorded += 1
    return recorded


def record_dataset(
    bag: dict[str, Any] | None,
    *,
    filename: str,
    dataset_id: str = "",
    version_id: str = "",
    rows: int | None = None,
    columns: list[str] | None = None,
    department: str = "",
    calculation: str = "",
) -> None:
    if bag is None:
        return
    bag["datasets"].append(
        {
            "source_name": str(filename or "unknown"),
            "source_id": str(dataset_id or filename or "unknown"),
            "version_id": str(version_id or ""),
            "locator": {"filename": str(filename or "")},
            "excerpt": str(calculation or "")[:_EXCERPT_LIMIT],
            "permission_checked": True,
            "provenance_status": "verified",
            "metadata": {
                "row_count": rows,
                "columns": [str(column) for column in (columns or [])][:40],
                "department": department,
            },
        }
    )


def record_metric(bag: dict[str, Any] | None, context: MetricContext) -> None:
    if bag is None or context is None:
        return
    bag["metrics"].append(context.model_dump())


def record_artifact(
    bag: dict[str, Any] | None,
    *,
    artifact_id: str,
    artifact_type: str,
    owner_id: str = "",
    version_id: str = "",
    download_url: str = "",
    expires_at: str = "",
) -> None:
    if bag is None:
        return
    bag["artifacts"].append(
        {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "owner_id": owner_id or None,
            "version_id": version_id or None,
            "download_url": download_url or None,
            "expires_at": expires_at or None,
        }
    )


def record_tool_status(
    bag: dict[str, Any] | None,
    *,
    tool: str,
    status: str,
    error_code: str = "",
) -> None:
    if bag is None:
        return
    bag["tool_statuses"].append(
        {"tool": str(tool or ""), "status": str(status or ""), "error_code": str(error_code or "")}
    )


def record_model_status(bag: dict[str, Any] | None, status: str, error_code: str = "") -> None:
    if bag is None:
        return
    bag["model_statuses"].append({"status": str(status or ""), "error_code": str(error_code or status or "")})


def evidence_from_bag(bag: dict[str, Any] | None) -> list[Evidence]:
    if not bag:
        return []
    evidence: list[Evidence] = []
    for document in bag.get("documents", []):
        evidence.append(
            Evidence(
                source_type="document",
                source_id=document.get("source_id", ""),
                source_name=document.get("source_name", ""),
                document_version_id=document.get("version_id") or None,
                locator=document.get("locator") or "",
                excerpt=document.get("excerpt", ""),
                score=document.get("score"),
                score_type=document.get("score_type"),
                permission_checked=bool(document.get("permission_checked")),
                provenance_status=document.get("provenance_status", "verified"),
                metadata=document.get("metadata") or {},
            )
        )
    for dataset in bag.get("datasets", []):
        evidence.append(
            Evidence(
                source_type="dataset",
                source_id=dataset.get("source_id", ""),
                source_name=dataset.get("source_name", ""),
                dataset_version_id=dataset.get("version_id") or None,
                locator=dataset.get("locator") or "",
                excerpt=dataset.get("excerpt", ""),
                permission_checked=bool(dataset.get("permission_checked")),
                provenance_status=dataset.get("provenance_status", "verified"),
                metadata=dataset.get("metadata") or {},
            )
        )
    for metric in bag.get("metrics", []):
        evidence.append(
            Evidence(
                source_type="rule",
                source_id=str(metric.get("metric_id") or metric.get("metric_name") or ""),
                source_name=str(metric.get("metric_name") or ""),
                locator=str(metric.get("formula") or ""),
                excerpt=str(metric.get("definition") or ""),
                permission_checked=True,
                provenance_status="verified",
                metadata={"unit": metric.get("unit"), "definition_version": metric.get("definition_version")},
            )
        )
    return evidence


def artifacts_from_bag(bag: dict[str, Any] | None) -> list[ArtifactRef]:
    if not bag:
        return []
    return [ArtifactRef.model_validate(item) for item in bag.get("artifacts", [])]


def metrics_from_bag(bag: dict[str, Any] | None) -> list[MetricContext]:
    if not bag:
        return []
    contexts = []
    for item in bag.get("metrics", []):
        try:
            contexts.append(MetricContext.model_validate(item))
        except Exception:
            continue
    return contexts


def _terminal_status(bag: dict[str, Any] | None, answer: str) -> tuple[str, str]:
    """Derive the worker status from what the boundaries actually reported."""
    statuses = list((bag or {}).get("tool_statuses", [])) + list((bag or {}).get("model_statuses", []))
    codes = [str(item.get("error_code") or "") for item in statuses]
    names = [str(item.get("status") or "") for item in statuses]

    if "rejected" in names or "authorization_required" in codes or "permission_denied" in codes:
        return "rejected", "permission_denied"
    # R111：「容量不够」与「模型坏了」不是一件事，证据面不许同色。AgentResult.status 的八枚 Literal
    # 里没有 rate_limited 这一档（app/agents/contracts.py:339，加取值要走 D 项），所以 status 照旧
    # model_unavailable、只让 error_code 分色：只报过 rate_limited 的一轮交付
    # ("model_unavailable", "rate_limited")，否则 frontend/src/lib/errcodes.js 那句「请稍等一会儿再试」
    # 永远到不了客户。内层把两枚同时在场判回 model_unavailable —— 真坏了优先于容量紧，折叠前的
    # 判定一格不动；越权那一支仍留在最前，「没权限」永远盖过「容量不够」。
    if "model_unavailable" in names or "rate_limited" in codes:
        if "model_unavailable" in names or "model_unavailable" in codes:
            return "model_unavailable", "model_unavailable"
        return "model_unavailable", "rate_limited"
    if "retrieval_unavailable" in names or "retrieval_unavailable" in codes:
        return "retrieval_unavailable", "retrieval_unavailable"
    if "timeout" in names or "task_timeout" in codes:
        return "timeout", "task_timeout"
    if "failed" in names or "rejected" in names:
        index = names.index("failed") if "failed" in names else names.index("rejected")
        code = str(statuses[index].get("error_code") or "")
        if "rejected" in names and not code:
            return "rejected", "permission_denied"
        return ("failed" if "failed" in names else "rejected"), (code or "internal_error")
    if not str(answer or "").strip():
        return "failed", "internal_error"
    evidence = evidence_from_bag(bag)
    if not evidence:
        return "partial", ""
    return "success", ""


def build_agent_result(
    *,
    worker: str,
    answer: str,
    bag: dict[str, Any] | None,
    request_id: str = "",
    trace_id: str = "",
    task_id: str = "",
    session_id: str = "",
    duration_ms: int = 0,
) -> AgentResult:
    evidence = evidence_from_bag(bag)
    artifacts = artifacts_from_bag(bag)
    metrics = metrics_from_bag(bag)
    status, error_code = _terminal_status(bag, answer)

    warnings: list[str] = []
    if status == "success":
        pass
    elif status == "partial":
        warnings.append("该 Worker 未产生可核验的数据或文档来源")
    elif error_code:
        warnings.append(f"执行边界报告了失败状态：{error_code}")

    confidence = 0.0
    if evidence:
        confidence = round(min(0.9, 0.35 + 0.1 * len(evidence) + 0.05 * len(artifacts)), 4)
    if status not in {"success", "partial"}:
        confidence = 0.0

    error = None
    if error_code:
        error = ErrorEnvelope(
            code=error_code if error_code in _ERROR_CODES else "internal_error",
            message=f"{worker} worker finished with status={status}",
            retryable=error_code in _RETRIABLE_CODES,
            details={"worker": worker, "status": status},
        )

    return AgentResult(
        worker=worker,
        status=status,
        answer=str(answer or ""),
        task_id=task_id,
        request_id=request_id,
        trace_id=trace_id,
        evidence=evidence,
        metrics=metrics,
        confidence=confidence,
        confidence_label="引用充分" if evidence else "引用不足",
        warnings=warnings,
        artifacts=artifacts,
        duration_ms=duration_ms,
        error=error,
    )


def summarize_agent_result(result: AgentResult) -> dict[str, Any]:
    """Redacted projection stored inside trace rows: counts and identifiers only."""
    return {
        "worker": result.worker,
        "status": result.status,
        "answer_length": len(result.answer or ""),
        "evidence_count": len(result.evidence),
        "document_count": len({item.source_name for item in result.evidence if item.source_type == "document"}),
        "artifact_count": len(result.artifacts),
        "metric_count": len(result.metrics),
        "confidence": result.confidence,
        "duration_ms": result.duration_ms,
        "error_code": result.error.code if result.error else None,
        "warning_count": len(result.warnings),
    }

_FAILURE_STATUSES = ("rejected", "model_unavailable", "retrieval_unavailable", "timeout", "failed")


def coerce_agent_result(worker: str, raw: Any) -> AgentResult | None:
    try:
        if isinstance(raw, AgentResult):
            return raw
        if isinstance(raw, dict):
            payload = dict(raw)
            payload.setdefault("worker", worker)
            return AgentResult.model_validate(payload)
    except Exception:
        return None
    return None


def aggregate_agent_result(
    results: dict[str, Any],
    *,
    answer: str,
    request_id: str = "",
    trace_id: str = "",
    task_id: str = "",
    session_id: str = "",
    duration_ms: int = 0,
) -> AgentResult:
    """Combine worker records into one canonical record for the whole execution."""
    normalized = [item for item in (coerce_agent_result(worker, raw) for worker, raw in (results or {}).items()) if item]
    if not normalized:
        return build_agent_result(
            worker="orchestrator",
            answer=answer,
            bag=None,
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
            session_id=session_id,
            duration_ms=duration_ms,
        )

    evidence: list[Evidence] = []
    artifacts: list[ArtifactRef] = []
    metrics: list[MetricContext] = []
    warnings: list[str] = []
    statuses: list[str] = []
    for item in normalized:
        evidence.extend(item.evidence)
        artifacts.extend(item.artifacts)
        metrics.extend(item.metrics)
        warnings.extend(f"{item.worker}: {text}" for text in item.warnings)
        statuses.append(item.status)

    failure = next((name for name in _FAILURE_STATUSES if name in statuses), "")
    if failure:
        status = failure
    elif "partial" in statuses:
        status = "partial"
    else:
        status = "success"

    error_code = {"rejected": "permission_denied", "timeout": "task_timeout", "failed": "internal_error"}.get(status, status)
    error = None
    if status in _FAILURE_STATUSES:
        first = next((item for item in normalized if item.status == status), None)
        error = (
            first.error
            if first is not None and first.error is not None
            else ErrorEnvelope(
                code=error_code if error_code in _ERROR_CODES else "internal_error",
                message=f"{status} worker result for request {request_id}",
                retryable=error_code in _RETRIABLE_CODES,
                details={"status": status},
            )
        )

    confidence = 0.0
    if status in {"success", "partial"} and evidence:
        confidence = round(min(0.9, 0.35 + 0.1 * len(evidence) + 0.05 * len(artifacts)), 4)

    return AgentResult(
        worker="orchestrator",
        status=status,
        answer=str(answer or ""),
        task_id=task_id,
        request_id=request_id,
        trace_id=trace_id,
        evidence=evidence,
        metrics=metrics,
        confidence=confidence,
        confidence_label="引用充分" if evidence else "引用不足",
        warnings=warnings,
        artifacts=artifacts,
        duration_ms=duration_ms,
        error=error,
    )
