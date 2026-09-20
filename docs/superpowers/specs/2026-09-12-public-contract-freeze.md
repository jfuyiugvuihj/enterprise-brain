# Public Contract Freeze: 2026-09-12

## Decision

The project uses one shared contract module at `app/agents/contracts.py` for identity,
resource scope, Agent execution context, structured results, evidence, metrics,
artifacts, and errors. Domain modules must import these models instead of defining
parallel equivalents.

## Frozen Models

- `Principal`: stable authenticated subject and request origin.
- `ResourceScope`: owner, department, classification, visibility, version and status.
- `AuthorizationDecision`: decision, reason, policy version and audit requirement.
- `AgentContext`: request, trace, task, principal, allowed actions and model budget.
- `AgentResult`: structured status, answer, evidence, metrics, artifacts and error.
- `Evidence`: source IDs, document/dataset/index versions, locator, score type and provenance.
- `MetricContext`: formula, unit, currency, period, timezone, source scope and version.
- `ErrorEnvelope`: stable machine-readable error code and retryability.

## Compatibility Rules

Existing worker code may continue using `source_name`, string locators, `source_file`,
`time_granularity`, and string artifact values during migration. New implementations
must populate stable IDs and version fields whenever the backing resource exists.

No worker may infer an administrator identity. No failure path may present offline,
model-unavailable, or retrieval-unavailable text as a successful business conclusion.

## Ownership

Agent 0 owns the contract and state modules. Other agents consume the models and may
request additions through a contract change note. `frontend/` remains owned by the
separate frontend agent.
