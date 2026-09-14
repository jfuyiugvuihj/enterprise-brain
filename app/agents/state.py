"""
Stage 0 public execution state.

The state keeps the authenticated principal, resource scope, request identifiers,
and structured worker results in one shared shape for all Agent domains.
"""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from app.agents.contracts import AgentContext, AgentResult, ModelBudget, Principal, ResourceScope


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge parallel worker maps while allowing an explicit reset."""
    if "__reset__" in b:
        return dict(b["__reset__"] or {})
    return {**a, **b}


def _last_wins(a, b):
    """Ordinary state fields use last-write-wins semantics."""
    return b


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    intent: str
    user_id: str

    principal: Principal
    request_id: str
    trace_id: str
    task_id: str
    session_id: str
    allowed_actions: list[str]
    allowed_resource_scope: list[ResourceScope]
    cancellation_token: str
    model_budget: ModelBudget
    agent_context: AgentContext

    memory: dict
    memory_error: str
    plan: list
    agent_results: Annotated[dict[str, AgentResult], _merge_dicts]
    worker_results: Annotated[dict, _merge_dicts]
    review_result: dict
    retry_count: int
    trace_events: list
    reflect_count: int
    redo: bool
    final_answer: str
