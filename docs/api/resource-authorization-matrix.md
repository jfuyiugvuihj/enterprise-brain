# Resource Authorization Matrix

Version: 2026-09-12
Owner: Agent 0 integration contract

This matrix describes the required backend boundary. It is not evidence that every
route currently enforces the rule. Current implementation status remains in the
current functionality document and must be re-audited after each domain merge.

| Resource | Stable identity | Required scope | Read/preview | Download/export | Mutate/delete | Audit |
|---|---|---|---|---|---|---|
| Session | session_id + owner_id | owner, department, status | owner or policy scope | n/a | owner/policy | yes |
| Document | document_id | owner, departments, classification, visibility, version | same policy | same policy | owner/admin policy | yes |
| Dataset | dataset_id | owner, departments, classification, version | same policy | same policy | owner/admin policy | yes |
| Artifact | artifact_id | owner, source version, expiry, status | same policy | same policy | owner/admin policy | yes |
| Trace | trace_id + owner/run | principal, run owner, classification | operator policy | no public path | retention policy | yes |
| Insight | insight_id | dataset/version scope, assignee, status | scope policy | policy | assignee/admin policy | yes |
| Alert | alert_id | rule owner, department scope, status | scope policy | policy | rule owner/admin policy | yes |
| Approval | approval_id | requester, department, policy version | participant policy | policy | assigned reviewer only | yes |
| Evaluation | eval_run_id | dataset/index/model versions | operator policy | policy | evaluator/admin policy | yes |

## Artifact Delivery Boundary

- `POST /api/v1/chart` requires `resource:analyze` before generation and returns a
  controlled Artifact content URL plus a download URL.
- `POST /api/v1/export` requires `resource:export` before generation and returns a
  controlled Artifact content URL plus a download URL.
- `GET /api/v1/artifacts/{artifact_id}/content` requires `resource:view`.
- `GET /api/v1/artifacts/{artifact_id}/download` requires `resource:download`.
- Both reads resolve active metadata first: expired and soft-deleted Artifacts are
  indistinguishable from missing resources.
- Generated-file paths beneath `/static/charts` and `/static/exports` return `404`
  even for authenticated callers; no static URL is an Artifact authorization proof.

## Dataset Delivery Boundary

- Dataset list, preview, download, and Agent analysis resolve a registered Dataset
  record before opening a local file.
- Lists filter unauthorized records without revealing unmanaged legacy file names.
- Preview requires `resource:view`; download requires `resource:download`; Agent
  analysis requires `resource:analyze`; upload requires `resource:upload`.
- Dataset records carry stable `dataset_id`, `version_id`, owner, department scope,
  classification, status, and content SHA-256 while the PostgreSQL tables are
  pending.
- Filename URLs are temporary compatibility keys only. They are not the resource
  identity or authorization proof.

## Non-negotiable rules

- A client filename, URL, session ID, or artifact path is not an authorization proof.
- A missing Principal or incomplete ResourceScope is rejected for protected operations.
- List filtering and detail authorization must use the same policy evaluator.
- Public static mounts cannot expose charts, reports, evidence, traces, or uploads.
- A successful response must not imply a resource was created or published until the
  backing metadata and file/index state are committed.
- Deletion must state whether it is soft deletion, retention, or physical cleanup and
  must cover derived indexes, caches, artifacts, traces, and backup references.

## Frontend boundary

The frontend agent may use `resource_id`, status, version, authorization errors and
artifact download endpoints. It must not treat a hidden button or a locally cached
role as authorization. Backend changes should remain backward compatible until the
frontend agent confirms migration to the frozen contract.


## Enforced-by-code evidence (2026-09-13)

The paragraph above is the requirement. This section is current evidence, so a
reader no longer has to infer status from the requirement text alone. Line numbers
refer to the working tree on 2026-09-13 and must be re-audited after the next merge.

| Boundary | Code | Evidence that it actually rejects |
|---|---|---|
| Intelligence (insights/alerts) routes | `app/api/v1/intelligence.py:60` `_authorized()` | `tests/test_intelligence_route_authorization.py` |
| Knowledge graph write/confirm/query | `app/knowledge_graph/service.py:51`, `:96`, `:120` | `tests/test_knowledge_graph.py` |
| Agent tools without a Principal | `app/agents/tools.py:24`, `:53`, `:61`, `:325`, `:372`, `:450`, `:513`, `:539` | rejected with `error_code=authorization_required`; the rejection text is returned as an error string, never as a business conclusion |
| Orchestrator worker results | `app/agents/orchestrator.py:277`, `:368`, `:389`, `:525`, `:593` | `tests/test_agent_result_records.py`, `tests/test_approval_worker_honesty.py` |
| Queue worker identity | `deploy/queue_worker.py:73` (refuses a payload with no Principal), `:79` (`thread_id = session_id or "queue:<request_id>"`) | `tests/test_redis_worker_recovery.py` asserts `failure.last_error == "authorization_required"` and that no conclusion leaves the process |
| Amount handling | `app/approval/assistant.py:6` `Decimal`, `:11` two-place quantisation, `:14` `to_decimal()` | a missing policy standard stays `unknown` instead of being invented |
| Metric semantics versioning | `app/semantics/registry.py:11` `semantic-registry-v1`, exposed via `match_metric_context()` | `tests/test_business_semantics.py`, plus the route assertion at `tests/test_intelligence_route_authorization.py:188` |
| Persistence requires an owner | `app/storage/persistence.py` (`ValueError` when a record has no owner) | `tests/test_postgres_execution_persistence.py` |

### Still requirement-only (not yet evidence)

- Audit is process-memory only (`app/common/audit.py`); the "Audit = yes" column of
  the matrix is a target for those rows, not a current guarantee across restarts.
- Insight provenance is not server-verified: `app/api/v1/intelligence.py:145` sets
  `provenance_source = "client_provided"` and `:146` sets `server_verified = False`.
  Until a `trace_id` can be resolved against the stored execution ledger on the
  server, the Insight and Alert rows of the matrix remain partially enforced.
- Dataset, Artifact and chat-history entities are still file-backed registries; the
  PostgreSQL tables and migrations named in the plan are not applied yet, so
  multi-instance consistency for those rows is unverified.
- The delivery boundary holds in code and in the rewritten `deploy/nginx.conf`
  (no public `/static`, no `alias`, runtime directories denied), but it has not been
  re-probed through a running container, so treat it as statically enforced and
  operationally unverified until the Docker gate passes.
