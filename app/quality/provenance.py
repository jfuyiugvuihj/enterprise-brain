from app.agents.contracts import AgentResult


def _coerce_result(item: AgentResult | dict) -> AgentResult:
    if isinstance(item, AgentResult):
        return item
    return AgentResult.model_validate(item)


def build_answer_provenance(results: list[AgentResult | dict]) -> dict:
    normalized = [_coerce_result(item) for item in results]
    evidence = []
    metrics = []
    workers = []
    for item in normalized:
        workers.append(item.worker)
        for fact in item.evidence:
            evidence.append(
                {
                    "worker": item.worker,
                    "source_type": fact.source_type,
                    "source_name": fact.source_name,
                    "locator": fact.locator,
                    "excerpt": fact.excerpt,
                    "score": fact.score,
                }
            )
        for metric in item.metrics:
            metrics.append(metric.model_dump())
    return {
        "workers": workers,
        "evidence": evidence,
        "metrics": metrics,
        "confidence": round(sum(item.confidence for item in normalized) / len(normalized), 4) if normalized else 0.0,
    }