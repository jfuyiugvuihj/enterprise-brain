from __future__ import annotations

from app.agents.contracts import AgentResult, ReviewResult


def review_agent_results(results: list[AgentResult]) -> ReviewResult:
    """规则型结果审查，先保证证据完整性，再交给模型做语言润色。"""
    issues: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []

    if not results:
        return ReviewResult(
            passed=False,
            issues=["没有可审查的 Agent 结果"],
            missing_evidence=["至少需要一个成功的 Agent 结果"],
            recommended_action="retry_retrieval",
            confidence=0.0,
        )

    for result in results:
        if result.status == "failed":
            issues.append(f"{result.worker} Agent 执行失败")
        if not result.evidence:
            missing.append(f"{result.worker} Agent 没有提供证据")

    if issues:
        action = "retry_analysis" if any(
            result.worker == "data" and result.status == "failed"
            for result in results
        ) else "retry_retrieval"
        return ReviewResult(
            passed=False,
            issues=issues,
            missing_evidence=missing,
            conflicting_evidence=conflicts,
            recommended_action=action,
            confidence=0.25,
        )

    if missing:
        return ReviewResult(
            passed=False,
            issues=["存在没有来源依据的结论"],
            missing_evidence=missing,
            conflicting_evidence=conflicts,
            recommended_action="retry_retrieval",
            confidence=0.35,
        )

    confidence = min(
        0.98,
        0.55
        + min(0.2, 0.1 * len(results))
        + min(0.2, 0.05 * sum(len(result.evidence) for result in results)),
    )
    return ReviewResult(
        passed=True,
        issues=[],
        missing_evidence=[],
        conflicting_evidence=[],
        recommended_action="accept",
        confidence=confidence,
    )
