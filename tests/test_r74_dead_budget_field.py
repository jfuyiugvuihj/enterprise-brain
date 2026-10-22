"""R74: the ``model_budget`` two contracts declared and no code ever read.

``AgentState`` and ``AgentContext`` each carried a ``model_budget`` field. Nothing in
``app/**`` assigned either one and nothing read either one. The concurrency gate is the
process-wide ``default_model_budget()`` semaphore in ``app/common/model_budget.py``, and
the token and clock limits are resolved per tier from configuration at the call site
(``nodes._make_model`` through ``model_tier_budget``). A field on the contract therefore
read as a control that controlled nothing, which is the shape this ticket removes.

The judgment taken is "delete the field", not "wire it up", and these cases pin the
reasoning as well as the result:

* the published ``AgentContext`` field set is enumerated, so adding a budget back fails
  where it stands;
* neither contract declares a ``model_budget`` annotation, checked off the AST rather than
  off a grep, because both files mention the *module* path in prose and always did;
* nothing under ``app/**`` reads such an attribute off anything, so the deleted field
  cannot come back half-wired on somebody else's object;
* a budget can no longer be parked on the context, which is what the field pretended to
  accept;
* ``ModelBudget`` itself survives untouched -- R30's per-tier caps are built on it, and
  this ticket was about a field, never about the contract.
"""
import ast
import re
from pathlib import Path

import pytest

from app.agents.contracts import (
    CONTEXT_LIMIT_CODE,
    AgentContext,
    ModelBudget,
    ModelTier,
    Principal,
)
from app.agents.state import AgentState
from app.common.model_budget import default_model_budget, model_tier_budget, tier_max_tokens

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "app" / "agents" / "contracts.py"
STATE = REPO_ROOT / "app" / "agents" / "state.py"

#: Everything ``AgentContext`` publishes, named once, in the open. A field added here has
#: to be added below, and a reviewer gets to read the diff of that decision.
PUBLISHED_CONTEXT_FIELDS = {
    "principal",
    "request_id",
    "trace_id",
    "task_id",
    "session_id",
    "allowed_actions",
    "allowed_resource_scope",
}

#: ``.model_budget`` as an attribute read. ``app.common.model_budget`` is a module path
#: and not a field, so the lookbehind keeps this case from being satisfied by deleting the
#: imports it would otherwise flag.
BUDGET_ATTRIBUTE_READ = re.compile(r"(?<!common)\.model_budget\b")


def _context(**overrides) -> AgentContext:
    base = {
        "principal": Principal(user_id="u-r74", username="r74"),
        "request_id": "req-r74",
        "trace_id": "trace-r74",
        "task_id": "task-r74",
    }
    return AgentContext(**{**base, **overrides})


def _annotated_names(path: Path, class_name: str) -> set[str]:
    """Field names declared on a class, read off the AST instead of off an object.

    The AST is the point: ``model_fields`` cannot see ``AgentState``, which is a
    ``TypedDict``, and a grep cannot tell a field from a sentence about the module.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names = set()
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    names.add(statement.target.id)
            return names
    raise AssertionError(f"{class_name} is no longer declared in {path}")


def test_the_published_context_fields_are_exactly_the_enumerated_ones():
    """The counter-knife: put ``model_budget`` back on ``AgentContext`` and this is red."""
    assert set(AgentContext.model_fields) == PUBLISHED_CONTEXT_FIELDS


def test_the_dead_budget_field_is_not_left_in_the_middle():
    """The same verdict an earlier batch reached for ``cancellation_token``, applied here.

    ``test_cancellation_epoch.py`` keeps its own copy of this shape for the field it
    deleted; this one is kept here so R74 is pinned by R74's file and neither batch has to
    edit the other's tests.
    """
    assert "model_budget" not in AgentState.__annotations__
    assert "model_budget" not in AgentContext.model_fields


def test_neither_contract_declares_a_budget_field():
    """Deleted from both places, and not re-declared under another name in between."""
    assert "model_budget" not in _annotated_names(CONTRACTS, "AgentContext")
    assert "model_budget" not in _annotated_names(STATE, "AgentState")


def test_the_state_no_longer_imports_the_type_it_stopped_annotating():
    """An unused import is how a deleted field comes back as a suggestion.

    ``ModelBudget`` still lives in ``contracts.py``, where R30's tier profiles need it; it
    simply has no business being reachable from the state shape any more.
    """
    tree = ast.parse(STATE.read_text(encoding="utf-8-sig"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)

    assert "ModelBudget" not in imported
    assert "AgentContext" in imported, "the context the state does carry stays imported"


def test_nothing_under_app_reads_a_budget_attribute():
    """Zero reads was the fact this ticket opened on; it stays the fact.

    If this goes red, somebody began reading a field no contract declares, which is the
    half-wired state R74 exists to prevent -- in either direction.
    """
    hits = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if BUDGET_ATTRIBUTE_READ.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{number}")

    assert hits == [], hits


def test_a_budget_cannot_be_parked_on_the_context_anymore():
    """The hallucination, tested from the caller's side instead of asserted in prose.

    While the field existed, ``ctx.model_budget = ModelBudget(max_tokens=32)`` was a legal
    statement that capped nothing. It is now a rejected statement, which is the same answer
    given honestly.
    """
    context = _context()

    with pytest.raises(ValueError, match="model_budget"):
        context.model_budget = ModelBudget(tier=ModelTier.CHAT, max_tokens=32)

    assert not hasattr(context, "model_budget")


def test_a_budget_passed_to_the_constructor_reaches_nothing_a_caller_can_read():
    """The other half of the same sentence: the keyword is dropped, not stored.

    ``AgentContext`` ignores unknown input, so a stale caller cannot detect the omission
    from the object. What it can no longer do is publish the field in the serialized shape,
    which is why the payload assertion is the one that matters.
    """
    context = _context(model_budget=ModelBudget(tier=ModelTier.CHAT, max_tokens=32))

    assert "model_budget" not in context.model_dump()
    assert "model_budget" not in AgentContext.model_json_schema()["properties"]


def test_a_model_budget_could_never_have_been_the_gate_it_looks_like():
    """Why "wire it up" was not the honest option for a field of this type.

    ``ModelBudget.max_concurrency`` is a number on a tier profile; the slots are granted by
    a different object altogether. A per-request ``ModelBudget`` has no ``acquire`` to call,
    so wiring the field would have invented a second name for a thing with one owner, and a
    limit no caller could actually have passed in.
    """
    gate = default_model_budget()
    tight = ModelBudget(tier=ModelTier.CHAT, max_concurrency=1)

    assert gate is default_model_budget(), "the concurrency truth is one process-wide object"
    assert gate.max_concurrency >= 1
    assert not hasattr(tight, "acquire"), "a tier profile holds no slot to grant or deny"


def test_the_live_budget_still_comes_from_configuration_without_a_model_call():
    """The source of truth R74 leaves standing, proven with no provider on the wire.

    Nothing here builds a message or opens a socket: the cap is read from configuration and
    the guard refuses an oversized prompt before a request could be sent. Zero model
    round-trips is the point of doing it here -- this is the judgement the deleted field
    never took part in.
    """
    from app.common.model_budget import ModelContextLimitExceeded, authorize_call

    budget = model_tier_budget(ModelTier.ANALYSIS)
    assert budget.max_tokens == tier_max_tokens(ModelTier.ANALYSIS)

    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize_call(budget, budget.context_limit_tokens)

    assert refused.value.code == CONTEXT_LIMIT_CODE
