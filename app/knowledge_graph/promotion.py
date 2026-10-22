"""Promote one verified business relation into a formal metric definition (request R15-b).

This is the only productive exit the knowledge graph has, and it is deliberately narrow:

* The relation must have been verified by a reviewer who is not its author
  (app/knowledge_graph/service.py refuses the alternative), and the promotion needs the
  same ``resource:approve`` permission. No new authority tier is invented here.
* The definition lands in ``metric_definitions`` carrying that reconciliation as real
  columns (migrations/0009_metric_definition_semantics.sql), so the
  "\u672a\u4e0e\u5df2\u4e0a\u4f20\u5236\u5ea6\u6587\u4ef6\u6838\u5bf9" warning disappears because evidence exists, not
  because somebody flipped a flag.
* The ledger is closed only after the catalog row exists. If no row was written - the
  database is offline, or the write failed - the relation stays verified but unpromoted,
  because a promotion the table never accepted is exactly the overstated provenance this
  slice exists to remove.
"""
from __future__ import annotations

from typing import Any

from app.agents.contracts import Principal
from app.knowledge_graph.service import KnowledgeGraph, Relation
from app.semantics import registry


def _wording(record: Relation) -> tuple[str, str]:
    """The label and the prose a relation implies when the caller supplied neither.

    A relation says "X \u89c4\u5b9a Y", so the target is the name of the thing being defined and the
    sentence plus its source locator is the definition. An operator promoting a relation
    into a real metric will normally override both; the default exists so the step is one
    call rather than a form.
    """
    statement = " ".join(
        part for part in (record.source_entity, record.relation, record.target) if part
    ).strip()
    label = (
        str(record.target or "").strip()
        or str(record.source_entity or "").strip()
        or statement
    )
    source = str(record.source or "").strip()
    prose = f"{statement}\uff1b\u6765\u6e90 {source}" if source and statement else (statement or source)
    return label, prose


def promote_relation_to_definition(
    graph: KnowledgeGraph,
    relation_id: str,
    *,
    principal: Principal,
    metric_id: str,
    definition_version: str,
    formula: str,
    unit: str,
    period_type: str,
    metric_name: str = "",
    definition_text: str = "",
    match_terms: Any = (),
    currency: str | None = None,
    timezone: str | None = None,
    time_granularity: str = "",
    source_scope: Any = (),
    filters: dict[str, Any] | None = None,
    status: str = "active",
    owner_id: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Turn one verified relation into a curated definition, and record that it happened.

    The row goes into the shared ``system`` namespace unless the caller names another
    owner: a promotion means "this checked claim is now the company wording for the
    metric", not "one person's note". Promoting the same relation again under a new
    ``definition_version`` revises the catalog the same way any curation does - the earlier
    version stays as history, and both rows keep pointing back at this relation.
    """
    record = graph.reviewable(relation_id, principal=principal)
    default_name, default_prose = _wording(record)
    result = registry.register_metric_definition(
        metric_id=metric_id,
        definition_version=definition_version,
        formula=formula,
        unit=unit,
        period_type=period_type,
        metric_name=str(metric_name or "").strip() or default_name,
        definition_text=str(definition_text or "").strip() or default_prose,
        match_terms=match_terms,
        currency=currency,
        timezone=timezone,
        time_granularity=time_granularity,
        source_scope=source_scope,
        filters=filters,
        status=status,
        owner_id=owner_id,
        overwrite=overwrite,
        verified_document=record.verified_document,
        verified_section=record.verified_section,
        verified_by=record.verified_by,
        verified_at=record.verified_at,
        source_relation_id=record.relation_id,
    )
    definition_id = str(result.get("definition_id") or "").strip()
    if not definition_id:
        # "skipped" (no database) or "failed": nothing reached metric_definitions, so
        # nothing may be reported as promoted.
        return {"promoted": False, "relation_id": record.relation_id, **result}

    updated = graph.record_promotion(relation_id, principal=principal, definition_id=definition_id)
    return {
        "promoted": True,
        "relation_id": record.relation_id,
        "relation_status": updated.status,
        "relation_version": updated.version,
        **result,
    }
