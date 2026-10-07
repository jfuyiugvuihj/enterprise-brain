"""Evidence gathered by tool boundaries during one Agent execution.

The evidence bag travels inside the LangGraph ``configurable`` mapping, so parallel
workers keep separate bags and no execution can inherit another caller's evidence.
Tool boundaries record what they actually retrieved; nothing is reconstructed from
the answer text afterwards.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, get_args

from app.agents.contracts import (
    AgentResult,
    ArtifactRef,
    Claim,
    CLAIMS_MEASURED,
    CLAIMS_NOT_MEASURED,
    ErrorEnvelope,
    Evidence,
    MetricContext,
)

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
        #: 图腿的数值缓冲（不是「模型读过什么」的证据，不进 sources、不进任何客户可见字段）：
        #: 数据腿算好的标签—数值序列存在这儿，模型只点名不带数时由图腿自己装箱。
        "chart_series": [],
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


def record_chart_series(bag: dict[str, Any] | None, series: list[dict] | None) -> int:
    """把数据腿算好的数值序列记进本轮缓冲，供图腿在模型没带数时装箱。

    只收「标签与数值等长、至少一个数」的序列：半截序列装出来的是一张缺柱子的图，
    那比没有图更难向客户解释。
    """
    if bag is None:
        return 0
    buffer = bag.setdefault("chart_series", [])
    recorded = 0
    for row in series or []:
        if not isinstance(row, dict):
            continue
        labels = row.get("labels") or []
        values = row.get("values") or []
        if not values or len(labels) != len(values):
            continue
        buffer.append(dict(row))
        recorded += 1
    return recorded


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


# ==================== R699 · 答案件里的逐条断言 ====================
#
# 判分器 ``app/quality/eval.py::evaluate_provenance`` 逐条读 ``supported``，所以这一节的计量
# 单位是一枚断言，不是一段话，也不是「有出处」三个字。
# 🔴 判据 1 的红线：``supported`` 只由**本轮检索到的证据**决定。比对之前先把引用记号摘掉 ——
# 让「答案里出现了 ``[来源: …]``」等于 supported，就是把 0 换成 1 的那本假账。

#: 断言边界：中文句末标点与换行切开；英文句号只在后面是空白或结尾时才切（``V1.2`` 不切）。
CLAIM_ASSERTION_BREAKS = re.compile(r"[。！？；;!?]+|\.(?=\s|$)|\n+")
#: 列表符与编号符不是断言的内容。
CLAIM_LIST_MARKER = re.compile(
    r"^\s*(?:[-*•]+|\d{1,3}[)）.、]|[（(]\d{1,3}[)）]|[（(][一二三四五六七八九十]+[)）])\s*")
#: 引用记号的在册两形：``[来源: xxx]`` 与 ``（依据条号 …；来源 …）``。产品自己只写这两形，
#: 出处见 ``app/agents/nodes.py::render_caliber_side`` 与检索提示词那一枚 f-string。
CLAIM_CITATION_MARK = re.compile(
    r"\[[^\]\n]{0,120}\]|（[^（）\n]{0,160}(?:来源|依据|条号)[^（）\n]{0,160}）")
#: 字面包含度只数内容字符：空白与标点不进 gram。
CLAIM_CONTENT_NOISE = re.compile(r"[^\w]+", re.UNICODE)
#: 数字与拉丁词是断言里最容易被幻觉改掉的那部分，必须在同一条证据里逐字见到才算被撑住。
CLAIM_KEY_TOKEN = re.compile(r"\d+(?:[.,]\d+)*%?|[A-Za-z][A-Za-z0-9_.\-]*")
#: 一枚断言要被叫作 supported，至少要被本轮证据撑住这一枚比例。
CLAIM_SUPPORT_CONTAINMENT_FLOOR = 0.6


class ClaimsDenominatorError(ValueError):
    """答案有正文却交不出任何断言：``unsupported_claim_rate`` 在这一行没有分母。"""


def _claim_grams(text: str) -> set[str]:
    folded = CLAIM_CONTENT_NOISE.sub("", str(text or "")).lower()
    return {folded[index:index + 2] for index in range(len(folded) - 1)}


def _claim_key_tokens(text: str) -> set[str]:
    return {item.lower() for item in CLAIM_KEY_TOKEN.findall(str(text or ""))}


def atomize_answer_claims(answer: str) -> list[str]:
    """把答案正文切成一枚一枚可判定的断言；正文非空就至少交出一枚。"""
    raw = str(answer or "")
    if not raw.strip():
        return []
    assertions: list[str] = []
    for piece in CLAIM_ASSERTION_BREAKS.split(raw):
        piece = CLAIM_LIST_MARKER.sub("", piece).strip()
        if not piece:
            continue
        #: 一枚断言至少得有两个内容字符（"1."／"（2）"这类编号碎片不是断言，把它们交进
        #: 分母就是拿编号冒充幻觉）。字符数够了才算一条。
        if _claim_grams(piece):
            assertions.append(piece)
    if assertions:
        return assertions
    #: 整篇切不出可用断言（只剩一串标点）时，把整段正文当作一枚断言交出去。绝不交「零枚」，
    #: 零枚就是判分器那把尺的零分母。
    return [raw.strip()]


def claim_support_scan(assertion: str, evidence: list[Evidence]) -> tuple[float, list[str]]:
    """一枚断言对「本轮证据」的最高字面包含度，以及撑住它的那一枚出处。

    出处取 ``Evidence.source_id``：文档那一形是 ``{source}#chunk={chunk_index}``，由
    :func:`record_document_hits` 写进证据袋，本函数只搬运不另造。证据正文读的是
    ``Evidence.excerpt``，它在 :func:`record_document_hits` 那头被 ``_EXCERPT_LIMIT`` 截断 ——
    截断只会让判定更保守（量不到就判 false），不会把没撑住的断言抬成撑住。
    """
    probe = CLAIM_CITATION_MARK.sub(" ", str(assertion or ""))
    grams = _claim_grams(probe)
    if not grams:
        return 0.0, []
    tokens = _claim_key_tokens(probe)
    #: 实际量到的最高包含度（可以低于阈值）：今晚窗口要校准这一把时，缺的就是这个数。
    seen_ratio = 0.0
    #: 真正撑住这一枚断言的那一条证据的包含度；没有一条撑住就是 0.0。
    chosen_ratio = 0.0
    best_refs: list[str] = []
    for item in evidence or []:
        excerpt = str(item.excerpt or "")
        haystack = _claim_grams(excerpt)
        if not haystack:
            continue
        ratio = len(grams & haystack) / len(grams)
        if ratio > seen_ratio:
            seen_ratio = ratio
        if ratio < CLAIM_SUPPORT_CONTAINMENT_FLOOR:
            continue
        #: 断言里的数字／拉丁词必须在同一条证据里逐字见到：半句真话配上枚假数字，
        #: 光靠 bigram 重叠是拦不住的。
        if tokens and not tokens <= _claim_key_tokens(excerpt):
            continue
        ref = str(item.source_id or item.source_name or "").strip()
        if not ref:
            continue
        if ratio >= chosen_ratio:
            chosen_ratio = ratio
            best_refs = [ref]
    return seen_ratio, best_refs


def build_answer_claims(answer: str, evidence: list[Evidence]) -> list[Claim]:
    """逐条断言加 ``supported``，判定只看本轮检索到的证据（判据 1 的唯一定夺点）。"""
    claims: list[Claim] = []
    for assertion in atomize_answer_claims(answer):
        ratio, refs = claim_support_scan(assertion, evidence)
        claims.append(
            Claim(
                text=assertion,
                supported=bool(refs) and ratio >= CLAIM_SUPPORT_CONTAINMENT_FLOOR,
                evidence_refs=refs,
                support_ratio=round(ratio, 4),
            )
        )
    return claims


def claims_denominator_state(answer: str, claims: list[Claim] | list[Any]) -> str:
    """分母在不在，只看这一格：有断言＝MEASURED，没有断言＝NOT_MEASURED。"""
    return CLAIMS_MEASURED if (claims or []) else CLAIMS_NOT_MEASURED


def require_measured_claims_denominator(
    answer: str, claims: list[Claim] | list[Any], *, worker: str = ""
) -> None:
    """答案有正文却交不出断言 ⇒ 当场拒绝，不许把零分母交成一枚 0.0。

    判分器（一字节不许改）算的是 ``unsupported_claims`` 非空的行数 ÷ 行数：一行带着空 claims
    进分母，它贡献的就是「没有一条不被支撑」这枚假绿。所以拒绝点在**产品侧**，不在尺上。
    """
    if claims or not str(answer or "").strip():
        return
    raise ClaimsDenominatorError(
        f"claims 分母为零（{CLAIMS_NOT_MEASURED}）：worker={worker or 'unknown'} 的答案正文有 "
        f"{len(str(answer).strip())} 字却交不出枚断言 ⇒ 判分器会把这一行读成 "
        "unsupported_claims=[]，也就是拿「没有分母的 0」冒充达标。这份答案件不发。")


def eval_payload_for_answer(result: AgentResult) -> dict[str, Any]:
    """答案件交出之前的唯一投影：只放判分器与采集器**已经在读**的键，零分母当场拒绝。

    ``scripts/collect_evaluation_answers.py::build_answer`` 对 ``claims``／``confidence``／
    ``confidence_label`` 三枚可选键是「响应里有就带走」；``app/quality/eval.py::
    evaluate_provenance`` 逐条读 ``text``／``supported``。两头的键名本函数一个都不新造，
    出口那一枚调用点（``app/api/v1/chat.py::done_sse_frame`` 与队列终态）不在 R699 写域，
    见 ``docs/testing/`` 本单凭据纸的「egress 待并」那一节。
    """
    require_measured_claims_denominator(result.answer, result.claims, worker=result.worker)
    return {
        "answer": result.answer,
        "evidence": [item.model_dump() for item in result.evidence],
        "claims": [item.model_dump() for item in result.claims],
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
    }


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
    #: R699：断言在这一枚边界上组装 —— 证据袋刚收完、正文已在手上，流式首字那一腿早就走完了
    #: （首帧发布点是 ``app/agents/nodes.py::publish_formed_answer_pieces``，本函数不在它上游）。
    claims = build_answer_claims(answer, evidence)
    require_measured_claims_denominator(answer, claims, worker=worker)
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
        claims=claims,
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
    #: 终答那一轮的断言按**合并后的本轮证据**重算：各 worker 的袋在图里是分开收的，
    #: 一句话可能由另一条腿检索到的那一枚 chunk 撑住。
    claims = build_answer_claims(answer, evidence)
    require_measured_claims_denominator(answer, claims, worker="orchestrator")

    return AgentResult(
        worker="orchestrator",
        status=status,
        answer=str(answer or ""),
        task_id=task_id,
        request_id=request_id,
        trace_id=trace_id,
        evidence=evidence,
        claims=claims,
        metrics=metrics,
        confidence=confidence,
        confidence_label="引用充分" if evidence else "引用不足",
        warnings=warnings,
        artifacts=artifacts,
        duration_ms=duration_ms,
        error=error,
    )
