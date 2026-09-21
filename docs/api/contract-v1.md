# Enterprise Brain API and SSE Contract

Version: 2026-09-12-contract-v1
Status: Frozen for domain-agent implementation
Owner: Agent 0 (integration)

## Scope

This document is the cross-agent boundary for REST responses, SSE events, identity,
resource scope, structured Agent results, and error semantics. Domain agents may add
fields only through a compatibility note; they must not create a parallel contract.

## Identity and Resource Scope

Every protected request carries a `Principal` with `user_id`, `username`, `roles`,
`permissions`, `department_ids`, `clearance`, `status`, `auth_source`, `is_system`,
and `request_id`.

Every protected resource must be addressable by a stable resource ID and may carry a
`ResourceScope` with `resource_type`, `resource_id`, `owner_id`, `department_ids`,
`classification`, `visibility`, `version_id`, and `status`.

Missing identity, missing scope, or an authorization policy error is not an admin
fallback. The boundary must reject the operation with `401`, `403`, or
`authorization_unavailable` as appropriate.

## Session and Cross-Turn Memory Semantics (2026-09-21, R118 plan B / R127)

`POST /api/v1/ask` accepts an optional `session_id`. Supplying one reuses the same
conversation thread for transcript storage, cancellation generations and HITL parking.
It is **not** a promise that the specialist workers re-read what they retrieved on an
earlier turn. Because that difference changes how a caller must phrase a follow-up, the
boundary is stated here in prose. No field, event name, status code or payload shape is
introduced or changed by this section.

Guaranteed across turns of one `session_id`:

- The session transcript itself (`sessions` / `session_messages`), so a client can re-render
  earlier questions and answers.
- Best-effort rewriting of anaphoric follow-ups: before dispatch, a message may be rewritten
  into a standalone question. Since R126 the trigger is a text-only judgement (no model call,
  no lookup) that asks one thing: can this sentence stand on its own, or does it need the
  previous turn to supply its subject, object or comparison basis? It is a union of five
  wording families, **not** a closed prefix list: sentence-initial deixis (`那` / `它` / `这` /
  `他们` / `她们` / `换` / `改成` / `如果` / `要是` / `请给` / `只给`); a demand to re-judge or
  recompute part of the previous answer (`换成` / `改为` / `再算` / `换个` etc.); a
  meta-instruction about how the previous answer was worded (`更简单` / `通俗` / `大白话` /
  `总结` / `不要引用` etc.); a comparison against what was said before (`矛盾` / `前面说` /
  `刚才说` / `上面说` etc.); and a bare added situation whose rule came from the previous turn
  (`合住` / `昨晚` / `叠加` / `报多少` etc.). The "etc." is deliberate: the authoritative lists
  live in `app/api/v1/chat.py` (`_FOLLOWUP_PREFIXES`, `_REWRITE_MARKERS`, `_FORM_MARKERS`,
  `_PREVIOUS_ANSWER_MARKERS`, `_SITUATION_MARKERS`) and are expected to grow, so this section
  names the families instead of repeating a vocabulary that would then go stale, which is how
  the sentence it replaced stopped being true. Deixis is excused at the start of a sentence
  when the object or the time is already spelled out (`这份报告`, `那张图表`, `这个月`, `那周`),
  and a lone `他` / `她` is possessive, so only `他们` / `她们` count. This is a wording
  heuristic, not an anaphora resolver: it promises nothing about follow-ups phrased outside
  those families, and such messages are dispatched verbatim. Measured on the shipped
  105-question set it takes all 12 `多轮对话` questions and none of the other 93
  (`tests/test_r126_rewrite_prev_turn.py`); the seven-prefix list it replaced reached only 4
  of those 12. The caller's original text is still used unchanged whenever the rewriting model
  leg is unavailable or rate-limited.
- Per-user long-term memory recall, injected to the supervisor as `【用户历史记忆】`. It is
  keyed by the authenticated user, not by the session, so it is not a private
  per-conversation store and two sessions of one user share it.

Explicitly **not** guaranteed, and callers must not depend on it:

- A worker leg (`doc` / `data` / `chart` / `export`) remembering the documents or rows it
  fetched in a previous turn. Each worker turn starts cold: the prompt that leg sees is its
  system instruction plus this turn's question, so a follow-up that omits its subject can be
  retrieved against the wrong terms. Restate the subject in the follow-up, or pass the
  intended document explicitly.
- That a rewritten question proves the server resolved the reference. Rewriting is a text
  transform, not evidence of memory.

## REST Error Envelope

Error responses use a stable `code` from:

- `authentication_required`
- `permission_denied`
- `authorization_unavailable`
- `account_unavailable`
- `resource_not_found`
- `validation_error`
- `conflict`
- `rate_limited`
- `queue_unavailable`
- `model_unavailable`
- `context_limit_exceeded`
- `retrieval_unavailable`
- `storage_unavailable`
- `task_timeout`
- `task_cancelled`
- `unsupported_file`
- `parse_failed`
- `index_publish_failed`
- `invalid_filename`
- `dataset_filename_conflict`
- `dataset_preview_failed`
- `unsupported_chart_type`
- `chart_generation_failed`
- `unsupported_export_format`
- `department_scope_required`
- `no_answer_produced`
- `row_scope_denied`
- `no_visible_rows`
- `internal_error`

> `storage_unavailable` was added on 2026-09-16 (`35ee27e`) for "the schema this build requires
> is not applied" - see the HITL section below. The names in the list above are **ratified, not
> invented**: `tests/test_error_code_vocabulary.py::RATIFIED` maps each of them to the emitter in
> `app/**`, and `test_no_ratified_code_is_invented` fails when an emitter is removed while the name
> stays in the enum, so the list cannot quietly accumulate fossils. How many entries that register
> holds today is deliberately **not** written here: it moves with every ticket, and a count in prose
> is the first thing to go stale. What keeps this list and `ErrorEnvelope.code` the same set is
> `tests/test_r142_error_code_table_sync.py`, which reads the Literal out of
> `app/agents/contracts.py` by AST and requires the bullets above to carry the same members in the
> same order -- so a code added to the enum but not to this page fails, naming the code.
> `app/agents/evidence.py` used to keep its own copy of the retryable vocabulary; it now derives from
> the same Literal and a test asserts the two sets cannot drift (R13-4).
>
> The deliberate exceptions come in pairs and are **not** `ErrorEnvelope.code` members: they are
> bare detail strings on legacy-shaped responses. `503 storage_read_only` -- a durable store that
> was configured and then could not be opened or written -- is what `add_relation`
> (`app/api/v1/intelligence.py`) and `register_application` (`app/api/v1/open_platform.py`) answer
> when the store the operator did configure refuses them. Each has an `unconfigured` sibling telling
> different news: a deployment that never configured such a store at all answers
> `409 knowledge_graph_unconfigured` (R103) or `409 open_platform_unconfigured` (R106). Ratifying
> them was explicitly declined: "read-only protection", "this deployment never enabled the
> feature" and "schema missing" are different failures, and merging them would make an operator fix
> the wrong one. `409` rather than `503` for the unconfigured half is load-bearing: nothing a client
> retries will configure a store, so a `503` would bill a decision the operator still has to make as
> downtime.
>
> R142 gave that family the register it never had. Every bare snake_case detail an endpoint still
> emits is named in `tests/test_error_code_vocabulary.py::BARE_CODES_OUTSIDE_THE_ENUM` with its
> emitter, the sentence `frontend/src/lib/errcodes.js::LEGACY_ALIASES` folds it into, and the reason
> it stays outside the enum. `400 idempotency_key_required` is the entry this ticket ruled on: it is
> emitted by `_enqueue_ask_turn` (`app/api/v1/chat.py`) whenever a background turn arrives without an
> idempotency key, it is documented per endpoint in the `/ask` row of the status table below, and the
> client already reads it as `validation_error`. Renaming it **server-side** would change a response
> body -- a contract change, not housekeeping -- so it is named for the coordinator rather than
> folded on the side; `tests/test_r37_report_lane_enqueue.py` keeps pinning the exact string.

Worker terminal state (R111): 容量耗尽携带 `rate_limited`，模型不可用携带 `model_unavailable`，
status 均为 `model_unavailable` - `AgentResult.status` 的八枚 Literal 里没有 rate_limited 这一档，
本单也不加（加取值要走 D 项）。所以一轮只报过容量拒绝的交付是
`("model_unavailable", "rate_limited")`：status 不变、只有 error_code 分色，前端才可能说出
「请稍等一会儿再试」而不是「模型坏了」。优先级照旧：越权盖过这两枚，两枚同时在场报
`model_unavailable`（真坏了优先于容量紧）。钉在 `tests/test_r111_capacity_color.py`。

The payload is compatible with:

```json
{
  "code": "permission_denied",
  "message": "resource access is not permitted",
  "retryable": false,
  "details": {}
}
```

### Authentication surface codes (2026-09-15, R10 / backend batch C-1)

The authentication middleware in `app/main.py` guards every non-public path before any
router runs, so these are the codes a client actually receives for "not signed in" and for
"signed in with an account that cannot be used". No HTTP status changed; only the `detail`
value stopped being prose. Like the document-route codes below, these travel in a bare
`{"detail": "<code>"}` body rather than in the enveloped payload shape above.

| Status | `detail` | Trigger | Expression |
| --- | --- | --- | --- |
| 401 | `authentication_required` | No `Authorization: Bearer` header, a non-Bearer scheme, a token that fails signature or expiry validation, a valid token whose account no longer exists, or a route-side guard with no Principal on the request | `app/main.py:104`, `app/main.py:109`, `app/common/authorization.py:53`, `app/api/v1/auth.py:110` |
| 403 | `account_unavailable` | The token resolved to an account whose `status` is not `active` (disabled or deleted) | `app/main.py:113` |

The three authentication codes above are members of the canonical list at the head of
this section, and `account_unavailable` is in `ErrorEnvelope.code`
(`app/agents/contracts.py`) as well, so an enveloped body may carry it. The agent-worker
copy of the list (`app/agents/evidence.py::_ERROR_CODES`) is deliberately not widened: it
only rewrites codes that reach it from a worker status, and the authentication surface
never travels that path.

`account_unavailable` is not `permission_denied`: `permission_denied` says the subject is
usable but lacks this action, while `account_unavailable` says the subject may not act at
all until an operator re-enables the account. A client must not read it as
"try again with another role" and must not force a re-login prompt, because the
credentials themselves are valid.

Deliberately not taken, although the ruling allowed it: a separate `token_expired` code.
`verify_token` collapses `ExpiredSignatureError` and `InvalidTokenError` into a single
`None`, so the middleware cannot distinguish an expired token from a forged one or a
vanished account without a new return contract in `app/common/auth.py`. An expired token
therefore reports `authentication_required`, and
`tests/test_auth_stable_codes.py::test_an_expired_token_is_not_yet_distinguishable_from_a_forged_one`
pins that so a future split is a decision with a test to update.

The public path whitelist (`/api/v1/login`, `/api/v1/health`, `/api/v1/sso/login`,
`/api/v1/open*`, `/`, `/docs`, `/openapi.json`) is unchanged, and
`tests/test_auth_stable_codes.py` holds both the statuses and the whitelist in place. The
frontend keeps its prose-alias table for stacks built before this change, which still answer
`请先登录` and `账号不可用`.

## SSE Events

The canonical event names are:

`request.started`, `step.started`, `step.progress`, `tool.started`,
`tool.completed`, `model.started`, `model.completed`, `retrieval.completed`,
`evidence.available`, `approval.required`, `result.partial`, `request.completed`,
`request.failed`, `request.cancelled`, and `heartbeat`.

Every event includes `request_id`, `trace_id`, `sequence`, `timestamp`, and `status`.
A request has exactly one terminal event: `request.completed`, `request.failed`, or
`request.cancelled`. Legacy `step`, `text`, and `done` events may remain during the
compatibility period, but new fields must map to the canonical event semantics.

`POST /api/v1/ask` now emits canonical `request.started` and exactly one canonical
terminal event alongside the legacy events. The same `request_id`, `trace_id`, and
`task_id` are passed into the LangGraph run and its worker configurations. During
the transition, the orchestrator persists redacted request lifecycle, progress, and
worker-completion metadata to the local JSONL `TraceStore`; this is not yet the
planned PostgreSQL `AgentRun` / `AgentStep` / `ToolCall` / `ModelCall` schema.

Example:

```json
{
  "request_id": "req-1",
  "trace_id": "trace-1",
  "sequence": 7,
  "timestamp": "2026-09-12T12:00:00Z",
  "status": "running",
  "data": {}
}
```

## HITL Pending Listing (2026-09-16, R13)

`GET /api/v1/hitl/pending` is the read side of the parked-turn ledger added by
`migrations/0008_pending_approvals.sql`. Query params: `session_id` (optional filter), `limit`
(default 50, clamped to at least 1 and at most 200, `chat.py:1257-1258` and `:1290`), `offset`
(default 0). First registered by the coordinator at `1672841` (**800 passed / 22 skipped**);
re-registered on 2026-09-16 after `5ea8dee` (paging), `35ee27e` (missing-table 503) and `6606f59`
(code ratification), against the suite at **831 passed / 22 skipped / 0 failed**.

Shape (as implemented, not as aspirational):

```
{ "items": [ { "session_id", "owner_user_id", "parked_steps": [node...], "labels": [..],
               "status", "created_at", "expires_at", "request_id", "trace_id", "task_id" } ],
  "count": <== items.length, after filtering>, "limit": <applied>, "offset": <applied>,
  "has_more": <bool> }
```

- `parked_steps` values come from the compile-time constant `_HITL_PARKED`
  (`app/agents/orchestrator.py:223`) and nothing else.
- `count` is the post-filter length, so it is not a total of open approvals and must not be used as one.
- **The table is an event log, the graph is the authority.** Every row is reconfirmed with
  `check_interrupt(session_id)` before it is listed; a row whose steps no longer match is marked
  `stale` in place and excluded. If the recheck itself raises, the row is omitted **without** being
  judged stale - a transient graph failure must not destroy a real pending decision
  (`chat.py:1285-1293`).
- Ownership reuses the existing predicate, no new permission tier: anonymous -> `401
  authentication_required`; another user's session -> **`404 resource_not_found`, explicitly not 403**
  (`chat.py:242-246`, `tests/test_hitl_pending.py:175-197`), matching the `__init__` convention that
  an unreadable resource does not exist. The owner filter is fail-closed: `open_items` is always
  called with a string, never `None`, so a principal without a user id queries nothing rather than
  everything (`chat.py:1277`, `pending_approvals.py:263-276`).
- A second park on the same session supersedes the previous open row by marking it `stale`, which is
  what keeps the partial unique index `WHERE status = 'awaiting'` satisfiable
  (`tests/test_hitl_pending.py:69`).
- A row nobody decided within the approval TTL is reported as stale rather than deleted, so the audit
  trail survives (`0008` header). `abandoned` is only meaningful since R12 (`826d318`): before
  cooperative cancellation a "stopped" run still finished, so that label would have asserted
  something the process had not done.

Closed on 2026-09-16 (both were recorded above as "not guarantees", not discovered later):

1. **Paging (`5ea8dee`).** `limit`/`offset` are pushed into SQL - the store is not asked for the whole
   table and sliced in Python, because that would only make "bounded" half true. The endpoint
   over-fetches `limit + 1` rows (`chat.py:1297`) to answer `has_more` without a second query.
   **The rule that matters:** a row beyond the page is *not rechecked against the graph this call*, so
   it must **not** be marked `stale` - silently expiring rows the caller never looked at would be a
   second lie on top of the first. `tests/test_hitl_pending.py:471` pins "the list endpoint never
   rechecks more rows than the limit", `:492` pins the truncation-must-not-mark-stale rule, `:505`
   pins that `offset` moves to the next ledger rows. `has_more` means "the ledger has more rows", not
   "more rows you are allowed to see".
2. **Missing table is now `503 storage_unavailable` (`35ee27e`).** The store raises the named
   subclass `PendingApprovalStoreMissing` (`pending_approvals.py:102`, raised at `:114`) instead of a
   bare `RuntimeError`, and only that exception maps to 503 - other `RuntimeError`s still propagate.
   Deliberate: if a missing *driver* were also reported as "try again later", this endpoint would be
   back to lying. The shape is `HTTPException(503, detail="storage_unavailable")`, i.e. a legacy
   string detail, not an `ErrorEnvelope` - matching this file's local convention (`chat.py:1303`).
   A subclass was required because `tests/test_hitl_pending.py:395` pinned the `RuntimeError` base
   class from the write side; naming the error must not turn an old assertion red.

## Structured Agent Result

`AgentResult.status` distinguishes `success`, `partial`, `failed`, `rejected`,
`timeout`, `cancelled`, `model_unavailable`, and `retrieval_unavailable`.
A failure status must not contain a fabricated business conclusion. Evidence carries
source/version/locator metadata, score type, permission-check status, and provenance
status. Metrics carry formula, unit, period type, timezone, source scope, and version.

## Versioning and Idempotency

Protected writes require an idempotency key or an equivalent domain key. Lists use a
consistent page/page_size/sort/direction or cursor contract. Caches must include
principal permission scope, resource version, policy/config version, model version,
and request mode.

## Long Task Status

There is no separate queue-submission endpoint. `POST /api/v1/ask` runs inline until the
per-user rate limit is exceeded; an over-limit request is enqueued by that same route and
answers an SSE `queued` event whose payload carries `request_id` and `status`. The client
then polls `GET /api/v1/queue/status/{request_id}` and may
`POST /api/v1/queue/{request_id}/cancel`.

```json
{
  "status": "queued",
  "request_id": "{request_id}",
  "position": 2,
  "failure": {"attempts": 1, "last_error": "model_unavailable", "max_attempts": 3}
}
```

`status` is one of `queued`, `processing`, `done`, `cancelled`, `dead`, or `expired`.
A `done` response additionally carries `result`.

### Compatibility note 2026-09-13

`failure` was added to every non-`expired` status response. Existing clients keep
working because it is additive; it exposes the queue's retry bookkeeping so a failed or
retried task always reports why (`last_error` holds a stable error code or the recorded
worker exception) instead of silently returning to `queued`. `dead` means the task
exhausted `max_attempts` and now lives on the dead-letter list.

## Generated Artifact Delivery

Generated charts and reports are controlled Artifacts. `POST /api/v1/chart` and
`POST /api/v1/export` require `resource:analyze` and `resource:export`,
respectively, before file generation. A successful response includes:

```json
{
  "path": "/api/v1/artifacts/{artifact_id}/content",
  "download_url": "/api/v1/artifacts/{artifact_id}/download",
  "artifact": {
    "artifact_id": "{artifact_id}",
    "artifact_type": "chart",
    "content_url": "/api/v1/artifacts/{artifact_id}/content",
    "download_url": "/api/v1/artifacts/{artifact_id}/download",
    "expires_at": null
  },
  "error": null
}
```

`GET /api/v1/artifacts/{artifact_id}/content` requires `resource:view`; `GET
/api/v1/artifacts/{artifact_id}/download` requires `resource:download`. Both load
the active Artifact record and evaluate its `ResourceScope`. Missing, expired, soft
deleted, or unauthorized Artifacts return `404` or `403` and do not expose a
filesystem path. `/static/charts/...` and `/static/exports/...` are not valid
delivery paths.

The current registry is JSON-backed local metadata while the canonical PostgreSQL
Artifact table is not yet integrated. It provides ownership, department scope,
classification, content hash, soft deletion, and expiry checks, but it does not
complete source-version lineage or physical retention cleanup.

## Dataset File Delivery

Dataset files use the same protected-resource boundary during the transition to
`Dataset` and `DatasetVersion` tables:

- `POST /api/v1/upload-excel` requires `resource:upload`; duplicate active logical
  filenames return `409 dataset_filename_conflict`.
- `GET /api/v1/data-files` returns only registered active datasets that pass
  `resource:view`, including `dataset_id`, `version_id`, and classification.
- `GET /api/v1/data-files/{filename}/preview` requires `resource:view`.
- `GET /api/v1/data-files/{filename}/file` requires `resource:download`.
- `analyze_data` and `query_data` require `resource:analyze` and resolve selected
  `data_filename` values through the same registered Dataset scope.

Unregistered legacy files beneath the local data directory are not exposed through
the protected HTTP or Agent data-analysis paths. The current registry is JSON-backed
metadata and retains the existing filename routes for frontend compatibility; it is
not a substitute for the planned persistent Dataset/DatasetVersion schema, immutable
physical storage, version history, schema snapshots, period metadata, or retention.

## Frontend Collaboration Boundary

The backend does not modify `frontend/`. The frontend agent consumes this contract,
including empty/error/loading/terminal states. UI visibility and local role checks are
not authorization controls.


### Compatibility note 2026-09-14 (HITL rounds, terminal-state honesty, legacy chat scope)

`request.completed` gained three additive fields: `answer_length` (characters of the answer
that was actually emitted), `awaiting_hitl` (whether the graph parked in front of a
confirmation-gated step) and `awaiting_steps` (the parked step names). A round that parks
for confirmation legitimately produces no answer, so it now emits a verifiable status
sentence before the `hitl` event, and that sentence is what gets persisted as the assistant
message; it is never written to the global answer cache.

Because of the dependency-layered dispatch, the `hitl` event may now arrive in a **later**
round than the analysis steps: the first round runs the analysis workers, and chart/export
park until their dependencies are recorded. Clients must keep listening after a `hitl`
event and must not treat `awaiting_hitl` as failure.

A round that produced neither an answer nor a parked step is an internal failure, not a
completed answer: the stream emits `error` plus `request.failed` with
`error_code=no_answer_produced`, and no empty assistant message is stored. Clients should
render it as a failed request with a retry affordance.

`POST /api/v1/chat` (legacy `text/plain` compatibility endpoint) is no longer an unscoped
retrieval path. It resolves the Principal from the request and pushes the same department
and clearance filter used by `/api/v1/ask` into the vector search, then re-checks every hit
locally, so a chunk with missing metadata stays invisible. It answers `401
authentication_required` when there is no Principal and `403 authorization_unavailable` (or
`permission_denied`) when the scope cannot be built, and internal exception text is no
longer streamed to the client. Any client relying on the old unfiltered behaviour must
move to `/api/v1/ask`.

`POST /api/v1/approve` and `POST /api/v1/ask/{session_id}/cancel` now resolve session
ownership before doing anything: a session that the caller does not own answers `404
resource_not_found`, exactly like `GET /api/v1/sessions/{session_id}` already did, and an
unauthenticated caller answers `401`. Both endpoints previously accepted any session id from
any logged-in user, which let one user hijack another user's parked HITL turn (and read its
streamed content) or mark another user's run as cancelled. Clients must therefore start a
conversation through `/api/v1/ask` (which binds the owner) before approving or cancelling.

`{"cancelled": ...}` from the cancel route is now factual: `true` only when this API process
had a run in flight for that session, `false` when nothing was running (the cancellation
marker is still armed, and queued-task cancellation remains a separate concern under
`/api/v1/queue/{request_id}/cancel`). A client that shows a "已取消" confirmation should key it
on the terminal SSE event rather than on this flag.

### Compatibility note 2026-09-14 (S5: queue submission and knowledge-base upload whitelist)

The `Long Task Status` section previously named a dedicated enqueue endpoint, which does not
exist anywhere in the source tree; no client may call it. Enqueueing is a behaviour of
`POST /api/v1/ask`, which returns `400` with detail `idempotency_key_required` when an
over-limit request carries no idempotency key, and `503` with code `queue_unavailable` when
Redis cannot be reached. `GET /api/v1/queue/status/{request_id}`,
`POST /api/v1/queue/{request_id}/cancel` and `GET /api/v1/queue/stats` are the only queue
routes.

`POST /api/v1/upload` now accepts exactly the four extensions that the parser can read:
`pdf`, `txt`, `md`, `docx`. `.xlsx` and `.csv` were removed from the knowledge-base whitelist
because they passed the header check, were written to storage, were deleted again by the
parse-failure handler, and surfaced as an HTTP 500. Spreadsheets are datasets and keep using
`POST /api/v1/upload-excel`, which has its own filename, permission and conflict rules (see
`Dataset File Delivery`) and does not share the document whitelist. An unsupported extension
is now rejected before any byte is written, as `400` whose `detail` is exactly the stable code
`unsupported_file` (`app/api/v1/chat.py:1245`). The human-readable reason - an unsupported
extension, a double extension, a path separator, or a magic-byte mismatch - stays in the
server log and is no longer a response body, so clients must branch on `detail` and never on
the message text.

`.md` documents are indexed as plain source text using the TXT encoding detection: no
Markdown rendering, no heading or table structure, no page locator. Preview is aligned with
that whitelist: `app/documents/preview.py` treats `.md` as readable text, so a Markdown file
that uploads and indexes also previews (`tests/test_file_preview.py` covers both the UTF-8 and
the legacy-encoding case, and asserts that the upload whitelist never drifts ahead of the
preview whitelist).

### Stable error codes on the document routes (2026-09-14, P2-8)

The upload, preview and document-lookup routes answer with the HTTP status plus a bare
`detail` string. The `detail` is always one of the codes below - never a sentence, never an
exception message - so clients can branch on it. The human-readable reason stays in the server
log (`[Docs] parse failed: ...`).

| Route | Status | `detail` |
| --- | --- | --- |
| `POST /api/v1/upload` | 400 | `unsupported_file` (unsupported extension, double extension, path separator, magic-byte mismatch) |
| `POST /api/v1/upload` | 413 | `upload_too_large` |
| `POST /api/v1/upload` | 500 | `document_parse_failed` |
| `POST /api/v1/upload` | 500 | `document_index_failed` |
| `GET /api/v1/documents/{filename}/preview` | 404 | `resource_not_found` |
| `GET /api/v1/documents/{filename}/preview` | 415 | `unsupported_preview` |
| `GET /api/v1/documents/{filename}/preview` | 500 | `document_preview_failed` |
| `GET /api/v1/documents/{filename}/versions` | 404 | `resource_not_found` |
| `POST /api/v1/ask` | 400 | `idempotency_key_required` |
| queue routes | 503 | `{"code": "queue_unavailable", "message": ...}` |

Two consequences for clients and for the `frontend/` owner:

- These codes are deliberately kept out of the `REST Error Envelope` list above, because that
  list describes the enveloped payload shape (`{"code", "message", "retryable", "details"}`)
  and these routes still answer with a bare string. Wrapping them is an open item, not a
  silent change; nothing may assume the envelope here until that work lands.
- `frontend/src/components/DocPanel.vue:120` and `DataPanel.vue:101,114` render
  `err.response?.data?.detail` as the user-visible message, which now shows a code instead of
  a sentence. The frontend must map these codes to localized text; a code-only fallback is
  not acceptable for an operator-facing UI. The document picker `accept` list
  (`frontend/src/components/DocPanel.vue:351`) is also still `.pdf,.docx,.doc,.txt`: `.doc`
  is rejected by `POST /api/v1/upload` with `400 unsupported_file`, and `.md` is not
  selectable. Both are frontend-owned fixes, not backend behaviour.

### Wave 1 consolidated fixes (2026-09-14): headers, catalog shape, health and admin surfaces

Landed in `d67987a..5db955c`. Everything below is additive or narrowing; no route was renamed
or removed, and no legacy SSE event changed.

- **`Cache-Control: no-store` on every authorised body.** `app/common/no_store.py` is the single
  helper. It now covers artifact content and download, document preview and download, data-file
  download and the dataset preview. A permission-checked 200 must not replay from a shared cache;
  clients must not add their own longer-lived caching on top.
- **`GET /api/v1/documents/catalog` rows no longer echo a server path.** `storage_path` is
  rewritten relative to the process working directory with forward slashes, or reduced to the bare
  file name when no relative form exists (for example across Windows drives). The absolute path
  stays in the catalog table and the server log. Treat `storage_path` as an opaque reference, never
  as a path to join.
- **`.md` preview works.** `app/documents/preview.py` treats `.md` as text next to `.txt`, `.doc`
  and `.docx`, so `415 unsupported_preview` now means "not a previewable type at all" instead of
  "markdown was never wired up".
- **`POST /api/v1/alerts/check` reports what it actually scanned.** The sweep evaluates the tenant
  `DATA_DIR` under the caller's Principal instead of the repository `data/` directory, and the
  response carries `scan_scope` (`data_dir_configured`, `reason`, `evaluated_files`). One sweep
  records a given rule at most once, so re-running the check cannot duplicate alerts.
- **`/health/details` names every storage mode.** Each subsystem reports `storage_mode`
  (`postgres`, `redis`, `json_file`, `memory` or `unavailable`), `durable`,
  `shared_across_processes`, `protection` and a `detail` string, and the report gains
  `degraded` status plus a `problems` code list (`users_store_not_persistent`,
  `<name>_read_only`, `queue_unavailable`, `postgres_<status>`, ...). A durable backend missing in
  production puts the subsystem into read-only protection instead of pretending to be healthy. For the
  knowledge graph and the open-platform registry the refusing state also names its cause in a `reason`
  field (`app/knowledge_graph/service.py:46-49`, `app/common/open_platform.py:55-56`): a store that was
  configured and then failed keeps `503 storage_read_only`, while a deployment that never enabled one
  answers `409 knowledge_graph_unconfigured` (R103) or `409 open_platform_unconfigured` (R106) - nothing a
  client retries can configure a store, so the two facts must not leave through one name. The subsystem
  keys carrying that `reason` are `knowledge_graph` and `open_platform_apps`
  (`app/common/monitoring.py:22`). Read `problems`; do not infer health from `status` alone.
- **Four admin observability routes exist** (`app/api/v1/observability.py`, mounted under
  `/api/v1`): `POST /retrieval/debug`, `GET /traces/{trace_id}`, `GET /evaluations`,
  `GET /audit/events`. They sit on already-authenticated paths - the `AuthMiddleware` allow-list
  was not widened - and an anonymous call gets `401 authentication_required` rather than an admin
  fallback. `POST /api/v1/apps` (open-platform registration) is now a route too: admin-only and
  audited.
- **Answer-cache keys carry a caller scope.** `app/common/cache.py` accepts a `scope` argument
  (`answer_cache_scope(principal, username=...)`) and `/ask` now passes it on both the read and the
  write, so a permission-shaped answer cannot be replayed to a different user. An empty scope keeps
  the historical question-only key, which is what an unauthenticated or legacy caller still gets;
  clients must never assume two users share a cached answer.

### Wave 3 consolidated fixes (2026-09-14): index publication, resource versions, metric semantics

Landed in `b9a0d6b` and `c0fdd21`. Additive only: no route was renamed or removed, no existing
response field changed meaning, and the retrieval read path is untouched.

- **A document upload now publishes an index version it can be audited against.**
  `POST /api/v1/upload` gained `index_publication` and `DELETE /api/v1/documents/{filename}` gained
  `index_retirement`, each `{status, index_id, source_version_id, chunk_count, mirrored, warnings[]}`
  plus `reason` when skipped. `status` is `published`, `retired` or `skipped`; `skipped` is not an
  error and carries `reason` of `no_indexed_chunks` (the version produced no chunks) or
  `no_published_index` (a delete of something that never published, or was already retired). Do not
  render a skip as a failure.
- **A failed publication says which stage failed and leaves nothing behind.** It answers
  `500 index_publish_failed` with `details.stage`. The PostgreSQL mirror is one transaction that
  aborts on any stage, and the local registry rolls its pointer back, so a half-published version
  cannot survive. `retryable` is true.
- **`chunk_count` distinguishes "never indexed" from "indexed and empty".** It appears on
  `documents` and `document_versions` (migration `0007`). `NULL` means no index version has ever
  been published for that row; `0` means a version was published and it holds no chunks. Clients
  must not read `NULL` as `0`.
- **Four control-plane tables stop being write-only in name.** `chunks`, `index_registry`,
  `index_versions` and `resource_versions` are written by the same transaction. `owner_id` became
  optional on all four: `NULL` means a legacy row with no recorded owner, and legacy is not public.
  `resource_versions` and the chunk rows carry the same scope projection the authorization decision
  used, so they cannot disagree.
- **Retrieval is unchanged.** Chroma remains the only read path; `chunks.embedding` is never
  written by this work, and classification and department live in `chunks.metadata`.
- **`GET /api/v1/semantics/metrics` is new** and returns
  `{metrics[], definition_sources, definition_versions, database_available,
  verified_against_documents}`. Each metric carries `definition_version` and a `provenance` block.
  The catalog is scoped to the caller.
- **`POST /api/v1/semantics/match` is additive**: `{context, definition_source, provenance}`.
  `context` keeps its previous shape, and it already carried `definition_version`; the source is
  repeated at the top level so a caller can tell a curated row from a code fallback without parsing
  the warning text. Matching is scoped to the caller's `user_id`.
- **Definition provenance is three-valued and is never upgraded silently.** A definition comes from
  `metric_definitions` as an operator row, from `metric_definitions` seeded from code, or from the
  `code_registry` fallback when the table, its schema or the connection is missing.
  `verified_against_documents` is `false` on every server path and cannot be set by stored JSON, so
  a row cannot claim a policy review that never happened.
- **Do not assume the metric table is populated.** Nothing in the running application calls
  `sync_code_definitions()` or `register_metric_definition()` yet, so `metric_definitions` may
  legitimately be empty and every answer will come from the code fallback. The write path exists
  and is tested; invoking it is a deployment decision.

### Compatibility note 2026-09-15 (R11: cancellation detaches the stream, it does not stop the work)

Ruled by the coordinator after the r8 finding "pressing stop while a session is parked on HITL
returns 200, and the parked action still executes after a later approve". Every statement below was
re-read from the source in this revision, not taken from the report.

- `POST /api/v1/ask/{session_id}/cancel` arms one streaming cancellation marker
  (`app/api/v1/chat.py::cancel_request`). It does not read, clear or resolve the graph's parked
  interrupt. Superseded on this point by R18 below: the marker used to be replaced by a **fresh**
  event on every `register_request`, which silently wiped a stop that had already landed; it is now
  bound to one generation, and a stop that lands while nothing is in flight is armed for the next
  generation instead. So "stop while parked, then press approve" no longer executes the stopped
  action — it stays parked, and it is still not a refusal.
- The parked action has exactly one resolver: `POST /api/v1/approve` with `approved` true or false.
  A rejected action is genuinely not executed (`84af113`), and that is the behaviour clients may
  rely on.
- Cancellation is cooperative only in the SSE loop. Both `/ask` and `/approve` run the agent graph in
  an executor thread and check `cancel_event.is_set()` solely while draining the queue; on a hit they
  emit `cancelled` and `break`, while the worker thread keeps running to completion and writes into a
  queue nobody reads any more. `is_request_cancelled` is referenced only inside `app/api/v1/chat.py` -
  neither `run_interrupt_stream` nor any worker consults a cancellation marker. **So "stop" means
  "detach me from this answer", not "the analysis is aborted".** A follow-up request to make execution
  honour cancellation is recorded as R12 in `docs/handoff/2026-09-15-backend-followup-requests.md`;
  until it lands, no client may claim that a cancelled run produced no side effects.
- The parked state offers no stop control in the product: `ChatPanel.vue` sets `loading = false` when
  the `hitl` event lands, and the stop pill renders under `v-if="loading"`, so the only control is the
  card's own cancel button, which sends `approved: false`. The r8 scenario is therefore reachable by
  calling the cancel route directly while a turn is parked, not by clicking through the UI. Note that
  during the *resumed* stream the stop pill is visible again, and pressing it there is the case in the
  previous bullet: the approved action finishes, the user only loses the answer text.

Contract, as ruled: **cancellation governs the stream, approval governs the action.** A client that
means "stop everything" must send `POST /api/v1/approve` with `approved: false` for the parked turn,
and may additionally call the cancel route to tear down an in-flight stream. Making cancel implicitly
reject a parked action was considered and rejected: it turns one mistap on a stop button into the loss
of an analysis that has already been running, and the user cannot undo it.

### Compatibility note 2026-09-16 (R18: cancellation is per-generation, and the table only holds runs in flight)

Landed by the backend worker on `codex/be-r18` from `docs/handoff/2026-09-15-backend-followup-requests.md`
§14. Every statement below was re-read from the source in this revision.

- Cancellation state is keyed by `(session_id, epoch)`. `app/api/v1/chat.py::register_request` opens
  a generation and returns its marker (`CancelGeneration`, a `threading.Event` subclass carrying
  `session_id` and `epoch`); `epoch` is a monotonic in-process counter, so two generations of one
  session never reuse an identity.
- **The sentence the R11 note owed:** a `POST /api/v1/ask/{session_id}/cancel` with no epoch cancels
  **the session's current generation**, i.e. the newest one still in flight. When nothing is in
  flight, the route still answers `{"cancelled": false}` (R12 item 4, response shape frozen) and
  arms a **one-shot** marker that the *next* `register_request` for that session consumes. That
  covers the two windows R11 could not: a stop arriving between the ownership check and
  `register_request`, and a stop arriving while the turn is parked on HITL.
- A marker never outlives its generation. Both `/ask` and `/approve` register inside the response
  generator and pop their own entry in a `finally` (`release_request`), so a completed round, a
  worker-thread exception, a cancellation and a client that disconnects mid-stream all retire it.
  `_REQUESTS` therefore reflects only runs in flight and returns to empty; a stop bound to a closed
  generation cannot make a later turn start cancelled.
- Per-step checks are generation-exact: the two SSE drain loops call
  `is_request_cancelled(session_id, epoch=...)`, and every orchestrator checkpoint
  (`app/agents/orchestrator.py::_is_cancelled`) tests the marker object handed to *that* run through
  `config["configurable"]` — object identity is the generation, so no cross-request lookup is
  involved and no process-global marker can be borrowed by another run.
- `cancellation_token` is **deleted** from `AgentState` (`app/agents/state.py`) and `AgentContext`
  (`app/agents/contracts.py`). It had no writer and no reader anywhere in `app/` or `tests/`; a field
  advertising a generation identity that nobody honours is worse than none. The generation identity
  now lives in the marker object itself.
- No SSE event name, status or error code changed. `request.cancelled` / legacy `cancelled` keep
  their R12 and R13-1 shapes, and `request_id` / `trace_id` / `task_id` / `sequence` are untouched.

### Compatibility note 2026-09-16 (R13-1: `/approve` emits a canonical terminal event)

Registered by the coordinator after reading the code, not from the backend agent's report.
Source read at `521913f`: `app/api/v1/chat.py:1204` (`POST /api/v1/approve`), ids generated at
`:1213-1215` the same way `/ask` generates them at `:784-786`, sequence counter at `:1249`,
cancellation branch at `:1256-1276`.

- Before this change the whole `/approve` stream carried **legacy events only** and had no
  `request_id` / `trace_id` / `task_id` at all, so a client had to keep two parsers to resume a
  HITL turn. It now emits exactly **one** canonical event:
  `request.cancelled` with `status="cancelled"` and `data.session_id`, emitted **before** the
  legacy `cancelled` event, matching the `/ask` cancellation shape at `:958-973` field for field.
- Scope of this registration, stated narrowly: `/approve` does **not** emit `request.started`,
  `request.completed` or `request.failed`. Those remain `/ask`-only. The freeze rule 2
  (canonical introduced additively, legacy kept) is satisfied: the legacy `cancelled` event was
  retained, and it was kept on purpose, not left over from a migration.
- No status code changed, no legacy payload key changed meaning, no event was removed, renamed or
  reordered. Full suite at this commit: **772 passed / 22 skipped** (backend agent), coordinator
  baseline before the merge was **771 / 22 / 0** at `826d318`. No live-stack verification: Docker
  Desktop is not running (board §4H.3), so this entry is code-green only.

## SSE Event Deprecation Policy (2026-09-14)

Snapshot basis: `app/api/v1/chat.py` as read on 2026-09-14 13:50 (+08:00). Event names and function names are the durable identifiers in this section; line numbers are deliberately not quoted because the backend is being edited concurrently. Frontend-side evidence and impact are recorded in `docs/frontend-workspace-audit-2026-09-14.md`.

### What `POST /api/v1/ask` actually emits

| Emitter | Event names | Carries answer content | Status |
|---|---|---|---|
| `canonical_sse_event()` | `request.started`, `request.completed`, `request.failed`, `request.cancelled` | no | emitted |
| `sse_event()` | `cancelled`, `error`, `heartbeat` | only `error` | emitted |
| inline `event: <name>` yields inside the ask generator | `queued`, `status`, `text`, `step`, `hitl`, `done`, `error`, `cancelled`, `heartbeat` | yes: `text` and `hitl` | emitted |
| canonical content events listed in the SSE Events section above | `step.started`, `step.progress`, `tool.started`, `tool.completed`, `model.started`, `model.completed`, `retrieval.completed`, `evidence.available`, `approval.required`, `result.partial` | - | documented but NOT emitted by any route today |

Consequence: the canonical envelope is currently a lifecycle wrapper only. Streamed answer text, worker step progress and HITL prompts exist solely on the legacy channel. There is no `sources` event on either channel; retrieval sources are assembled only inside the non-streaming `POST /api/v1/chat` response, so a client cannot obtain them from `/ask` at all.

### Freeze rules

1. During the freeze no event name in the second and third row may be removed or renamed, and the legacy payload keys `type` and `content` must keep their current meaning. A silent rename on that channel blanks the chat page without producing any client-visible error.
2. Canonical events are introduced additively. A backend change must not replace a legacy emission in the same commit: both channels run side by side for at least one review cycle.
3. Terminal state is canonical-first from now on. Exactly one of `request.completed`, `request.failed` or `request.cancelled` closes a request. Clients treat the canonical terminal event as authoritative and the legacy `done` event as the compatibility fallback.
4. Clients must ignore unknown event names, and must reset the generating state on any terminal event, including a cancellation or a failure that carries no text at all.
5. Add `protocol_version` to the canonical envelope before any retirement begins, so a client can fail loudly instead of rendering an empty answer.

### Preconditions for retiring the legacy channel

- A canonical event carries streamed text (named `result.partial` in the list above).
- `step.started` plus a matching completion event carry worker progress.
- `approval.required` carries the HITL pending payload and its labels.
- A sources event exists on `/ask` and is documented with its payload shape.
- The frontend parser is switched to canonical-first with a legacy fallback and verified in a browser.
- Both owners sign a dated entry in the migration log below.

Until all six hold, the legacy rows above are the only supported content channel, and any backend cleanup that deletes them counts as a breaking change.

### Migration log

- 2026-09-16 (R13-1): `/approve` gained one additive canonical event, `request.cancelled`, after the cancellation shape was re-read from `app/api/v1/chat.py:1256-1276` against `/ask` at `:958-973`. No legacy event removed, renamed or reordered; `/approve` still carries no canonical content events, so the six retirement preconditions below are unchanged and the frontend parser work (F2) is still the blocker.
- 2026-09-14: section added after the frontend workspace audit. No event was removed, renamed or reordered by this change. Backend line-number references elsewhere in the repository are treated as a dated snapshot, not as contract.

---

## Three-Tier SLO Contract (2026-09-20, R105 甲半)

Snapshot basis: `app/api/v1/observability.py` (`slo_units`, `slo_tiers`, `slo_readout`),
`app/agents/nodes.py`, `app/agents/contracts.py`, `app/common/stage_timing.py`,
`app/common/performance.py` and `frontend/src/router/index.js`, as read on 2026-09-20 on
`codex/be-r105a` @ `0066cce` (ff-checked 2026-09-20 16:4x). Identifiers (lane values, route names, stage names, JSON paths)
are the durable contract in this section; line numbers are a dated snapshot.

🔴 **Nothing in this section is measured.** It fixes the units, the mapping, the arithmetic and
the addressable slots, and it fills every number slot with 「待真机样本」. A target value arrives
only with 乙半, from the D14甲 window's real distribution. Publishing an unmeasured figure as an
SLO is the same breach as R36's boundary rule (不得用演示语料充当评测集), and the seconds in
`docs/handoff/2026-09-17-perf-architecture-plan.md` §3.1 stay **proposals** until E2/E3 has
sampling behind them (计划书 §3.2: 任何未经 E2/E3 实测的秒数 = 不可承诺). They are referenced
here, never copied into a target cell.

### 1. "三档" collides three different units - they are not three names for one thing

| 单位 | 成员 | 名字归谁 | 是 SLO 的单位吗 |
|---|---|---|---|
| **product lane** 产品档 | `qa` 问答档 · `analysis` 分析档 · `report` 报告档 | `app/agents/nodes.py` `LANE_QA` / `LANE_ANALYSIS` / `LANE_REPORT`; decided by R42 `classify_route()` (rules only, zero model calls) | **yes** - one row of the contract is one lane |
| **model budget tier** 预算档 | `chat` `plan` `compress` `rewrite` `code` `alert` `analysis` | `app/agents/contracts.py:69` `ModelTier`; chosen by the call site that asks for a budget | no - it budgets one model call, not one user-perceived wait |
| **ledger stage** 台账分段 | `classify` `rewrite` `retrieve` `generate` `reflect` | `app/common/stage_timing.py` `CANONICAL_STAGES`; assigned by `classify_stage()` from label → tool → tier → worker | no - it is the inside of a lane's number |

The bridge is read out of `nodes.py` `LANE_TIERS` (`slo_units()["model_budget_tier"]["bridge_from_product_lane"]`),
never retyped, and it is **not** a bijection:

| product lane | 预算档 (`LANE_TIERS`) |
|---|---|
| `qa` | `chat` |
| `analysis` | `analysis` |
| `report` | `analysis` |

- `analysis` and `report` share one budget tier, so a "per-tier budget" and a "per-tier SLO" are
  different groupings and must not be drawn from the same table.
- Five of the seven budget tiers (`plan` `compress` `rewrite` `code` `alert`) are named by no lane
  at all: they are work performed *inside* one lane's request, which is why a budget-tier split
  and a per-tier SLO can never be the same table.
- 🔴 Neither side renames for the other's convenience. `ModelTier` growing a member must not
  create a fourth SLO row, and an SLO row must not be renamed to a budget tier that happens to
  share its spelling (`analysis` is the collision to watch).

### 2. 档 → 屏 / 端点 → stage 组

The single source of truth is `app/api/v1/observability.py::slo_tiers()`. This table is a
rendering of it; `tests/test_r105_slo_contract.py::test_the_contract_table_and_the_document_cannot_drift`
reddens if the two disagree, so the mapping is written down once and mirrored, never copied.

| 档 | 屏 route / path | 端点 | 台账 stage 组 |
|---|---|---|---|
| `qa` 问答档 | `chat` `/chat` | `POST /api/v1/ask` | `classify` `rewrite` `retrieve` `generate` `reflect` |
| `analysis` 分析档 | `chat` `/chat` | `POST /api/v1/ask` | `classify` `rewrite` `retrieve` `generate` `reflect` |
| `report` 报告档 | `chat` `/chat` | `POST /api/v1/ask` · `GET /api/v1/queue/status/{request_id}` | `classify` `rewrite` `retrieve` `generate` `reflect` |

- **"三屏" is a name for three tiers, not a count of screens.** All three lanes are hosted by the
  one screen today: `frontend/src/router/index.js` has seven screens (`overview` `docs` `data`
  `insights` `approval` `chat`, plus `graph` with `meta.primary: false`), and `ChatPanel.vue` is
  the only panel that calls `/ask`. Inventing two more screens to match the phrase would be
  inventing data of a different kind, so the contract records the shared host instead.
- Screen names are route names and come from the router (R104). A backend row may name a route;
  it may not define one, and `frontend/**` is not this ticket's to edit.
- `report` is the only tier with a second addressable surface, and that route answers only when
  `REPORT_LANE_VIA_QUEUE` is on (`app/api/v1/chat.py::_report_lane_via_queue_enabled`, which gates
  `_queue_lane`); with it off, the tier is served
  synchronously by `/ask` and the queue path does not exist.
- What the client sends in `AskRequest.lane` is **not** the tier. The field is a closed set of four
  values -- `""` (declare nothing), `qa`, `analysis`, `report` (`ASK_LANE_VALUES` and the
  `_require_valid_lane` guard in `app/api/v1/chat.py`) -- and anything else is refused with `400` and stable code
  `validation_error`, before a session row, a queue entry or a model call is spent. The previous
  draft of this line said that refusal “is not implemented”; R32 implemented it, so the sentence
  now reads the other way. Empty means the server picks: the tier of a measured request is R42's
  verdict (`app/agents/nodes.py::classify_route`, a function of the question text alone), so a
  request cannot choose its own SLO bucket. Accepting a label is not the same as honouring it --
  the only behaviour a client label can change today is the `report`-plus-switch-on detour above,
  measured dimension by dimension by `tests/test_r32_lane_contract.py`, which is also why
  `frontend/**` still ships no tier selector (R32's fake-control ban: a control that changes
  nothing is a lie about a feature).

### 3. One percentile algorithm

`app/common/performance.py::PerformanceStats` is the only rank rule in the repository: nearest
rank, the value sitting at `ceil(n * q)`, 1-based (`:26-30`), reported as `p50_ms` / `p95_ms` by
`report()` (`:44-51`). `stage_timing._stats()` builds on it, `/health/details` and
`GET /api/v1/stage-latency` read that, and `slo_readout()` imports the same class. No document and
no second module may define quantiles of its own.

Registered exception, not sanctioned: `app/quality/eval.py:117-120` keeps its own
`max(1, ceil(n * 0.95))` to produce the `latency_ms.p95` that `observability._REPORT_LATENCY_KEYS`
reads back. It agrees with the source today, and
`tests/test_r105_slo_contract.py::test_the_registered_second_quantile_cannot_diverge_from_the_source`
pins that agreement distribution by distribution so a one-sided edit goes red. Collapsing it into
`PerformanceStats` needs a write scope this ticket does not have, so it is named here for the
coordinator instead of being rewritten on the side.

### 4. Number slots: addressable, and every one of them says 「待真机样本」

Each slot is a stable JSON path under `GET /api/v1/slo` → `tiers[]`, keyed by the tier's `lane`.
乙半 writes into `target`; `value`-side keys (`p50_ms` / `p95_ms`) are always computed, never
typed. `target_status` is `awaiting_real_samples` until then.

| 档 | 槽位 (`tiers[lane].numbers.<name>`) | 分母 = 一个样本是什么 | 现在能否算 | 目标 |
|---|---|---|---|---|
| `qa` | `end_to_end_p95_ms` 结论完成 | one `qa` request that reached a terminal event | gated: needs lane labels | 「待真机样本」 |
| `qa` | `first_text_p95_ms` 首屏 | one streamed `qa` request, `request.started` → first observed token | no - see §6 | 「待真机样本」 |
| `qa` | `cache_hit_p95_ms` 缓存命中 | one cache-hit response on the ask path | no - see §6 | 「待真机样本」 |
| `analysis` | `end_to_end_p95_ms` 端到端 | one `analysis` request that reached a terminal event | gated: needs lane labels | 「待真机样本」 |
| `analysis` | `progress_interval_p95_ms` 进度间隔 | one gap between consecutive `step.progress` events in one trace | no - see §6 | 「待真机样本」 |
| `report` | `end_to_end_p95_ms` 端到端 | one `report` request that reached a terminal event, queue entry point included | gated: needs lane labels | 「待真机样本」 |

Plus one pair of slots per stage, `tiers[lane].stage_numbers.<stage>.{p50_ms,p95_ms}`, over the
samples that carry that lane and that stage. They inherit the same floor and the same
null-instead-of-zero rule.

### 5. The sample floor: below it, the readout must confess, not answer

- The floor is `app/api/v1/observability.py::MIN_SLO_SAMPLES` = 100 (R36 判据②). The document
  names the constant rather than keeping its own copy of the number.
- It gates **each number against the n of the distribution that number describes**: a tier's
  end-to-end is gated by its request count, a stage percentile by that stage's sample count.
- The gate is a knife edge: `n = 99` answers `insufficient_samples` with `shortfall = 1` and
  `p95_ms = null`; `n = 100` answers `measured`.
- 🔴 **The floor is not a query parameter.** A caller-lowerable threshold is not a threshold.
- What this prevents, concretely: `PerformanceStats.report()` answers `0` for a distribution it
  has never seen, so an ungated SLO readout on an empty ledger publishes `p95_ms: 0` - a
  spectacularly passing SLO manufactured out of nothing. `slo_readout()` answers `null` plus its
  own shortfall there.
- Population rule: failed and cancelled requests are counted. Excluding the slow failures is how
  a P95 turns optimistic. Calls discarded before the stream body ran never reach the ledger at
  all (R110), so a window filled before that merge is biased and must say so.

### 6. What cannot be computed even after the window runs (甲半 registers, does not fix)

Each code is emitted in-band by `GET /api/v1/slo` under `blockers[]`, with the same detail text.

| code | 事实 |
|---|---|
| `lane_attribution_absent` | `app/trace/spans.py:201-215` hands the ledger stage, tool, tier and worker but never a lane, and no persisted request event carries the question ⇒ live samples all group under `lanes.unknown`, so every per-tier population is empty and every gated slot reads `n = 0` |
| `first_token_not_a_stage_sample` | `first_token_at` is recorded (`spans.py:174`) and persisted (`store.py:259`) but `stage_timing.samples_from_span_payload` (`:330-345`) never reads it ⇒ 首屏 is computable from a persisted trace, not from the ledger |
| `wire_first_text_not_recorded` | the promised 首屏 is the first `text` event **on the wire**; canonical envelopes are stamped (`chat.py:222-243`) but not persisted ⇒ a model-side first token is a proxy, and must be labelled one |
| `cache_hits_are_not_traced` | a cache hit returns before any `request.started` (`chat.py:1191-1215`) ⇒ no window, no sample; 缓存命中 has a zero denominator today, not a fast answer |
| `wire_step_events_are_not_recorded` | `step.progress` is persisted per graph superstep (`orchestrator.py:1173-1185`), which measures graph advancement rather than delivery to the client |
| `export_leg_has_no_stage` | `TOOL_TO_STAGE["export_report"]` is empty (`stage_timing.py:71`) ⇒ the report tier's file writing lands in `unattributed`, so the five-stage sum is not that tier's end-to-end; `coverage_error_pct` / `gap_ms` are what say so |
| `native_leg_reports_no_cached_tokens` | **a refuted marker, kept on purpose** (R146): the name still has to appear in this table and in `spans.py` because `tests/test_r38_cached_tokens_honesty.py` pins the literal, and `spans.py` now files it under `REFUTED_CACHED_TOKEN_CLAIM`. The truth is per-shape, measured: Ollama's native `/api/chat` `done` frame **does** report `prompt_eval_cached_count` (R29 verbatim frames 148 / 1 / 3); the compatible leg's `usage.prompt_tokens_details.cached_tokens` is **non-zero on product traffic** (`docs/perf/raw/prodpath.jsonl`: 543 prompt / 292 cached, 769 / 257, with 116 / 0 an honest zero); compatible **streaming** frames stay silent **unless** the request opts into `stream_options.include_usage`, after which the last frame carries it (R31 probe). What is still true is the ledger half: `spans.py::model_token_counts` meters `input_tokens` / `output_tokens`, `model_calls` has no cached column, so a `cached_tokens=0` in the perf ledger is a measured 0 and never a cache-hit rate, and an absent key means the stream could not say, not that nothing was cached (R38, R146) |

Closing `lane_attribution_absent` is one field on one call site; it belongs to the ticket that
owns `spans.py`, not to this one. Until it closes, 乙半 can fill the pooled distribution
(`unattributed_pool.end_to_end`) and nothing lane-split.

### 7. Route registration

`GET /api/v1/slo` (`app/api/v1/observability.py::read_slo`) - read-only management plane, same
gate as `/stage-latency`: an authenticated principal with the audit action, else `401
authentication_required` as an `ErrorEnvelope`. It opens no engine, runs no request, writes no
sample. Additive: no existing route, field or event changed by this section. Note that the
"Four admin observability routes exist" entry under *Wave 1 consolidated fixes (2026-09-14)* is a
dated snapshot - since then `GET /stage-latency` (R51) and `GET /slo` (R105) joined the router,
so the live route set is readable from `app.main` and the OpenAPI document, not from that entry.

## Evaluation Report Provenance (2026-09-20, R105 甲案)

`GET /api/v1/evaluations` reads report files from two different places, and the answer did not say
which was which. `_evaluation_report_candidates` takes the operator's
`EVALUATION_REPORT_DIRS` / `EVALUATION_REPORT_DIR` first and then **unconditionally** appends
`DEFAULT_EVALUATION_REPORT_FILES` - the score that ships inside the image. Since the first real
number was committed to `docs/testing/evaluation-report.json`, 「没配报告目录」 no longer equals
「没有报告」: a box with no configured directory still answers `reports_available`. This section
puts that in the payload instead of in a code comment.

### 1. The field

| key | type | values | meaning |
| --- | --- | --- | --- |
| `reports[].source` | string | `configured` \| `shipped_default` | what brought this file into the list |

- `configured` (`REPORT_SOURCE_CONFIGURED`): reached through the operator's report dirs.
- `shipped_default` (`REPORT_SOURCE_SHIPPED_DEFAULT`): the file *is* one of
  `DEFAULT_EVALUATION_REPORT_FILES`, i.e. the image came with it.
- Provenance is a property of the file, not of the route that found it. An operator who points
  `EVALUATION_REPORT_DIRS` at `docs/testing` is still looking at the bundled score, and the answer
  still says `shipped_default`. The identity test lives in exactly one place,
  `app/api/v1/observability.py::_shipped_report_paths` (resolved paths, so both spellings match).
- Every record carries it, including the ones that stop early at `unreadable` / `too_large`: the
  key is written into the record before anything is read from disk.

### 2. What did not change

甲案 adds one key. Unchanged: the candidate set and its order (configured entries first, defaults
appended, deduplicated), `status` (`ok` / `unreadable` / `too_large`), `id`, `path`, `size_bytes`,
`modified_at`, `metrics`, `category_count`, `reports_total`, `truncated`, the
`MAX_EVALUATION_REPORTS` clamp, and the `no_reports` / `reports_available` decision. No file is
hidden from the list and no file is invented for it - the shipped score is **not** demoted out of
the response when a configured directory exists, it is only labelled. Additive field: a client that
ignores `source` keeps working.

### 3. Registered, not fixed

`tests/test_observability_routes.py::test_evaluations_reports_an_absent_suite_and_no_reports`
(`9de5e89`) has to neutralise `DEFAULT_EVALUATION_REPORT_FILES` in order to reach `no_reports`. That
is the behaviour this section documents, not a flaw in the test. Whether the unconditional append
should become 「显式配置是唯一真源」 is a route-semantics decision held by 总控 - same family as R111
(配置/诊断未被完全尊重), and its route is decided together, not here.


## Document Activity Feedback (2026-09-21, R152 / R46)

`app/api/v1/feedback.py` records a 「采纳 / 驳回」 signal against a source document and lets retrieval
ranking read it back as a prior. Two routes, both mounted under `/api/v1`.

### `POST /api/v1/feedback/document`

The body accepts **exactly two keys**: `filename` (at most 512 characters, the same hard ceiling as the
`CHECK` in `migrations/0011_document_activity_signals.sql` - both sides are enforced, neither trusts the
caller) and `signal`, one of `accepted` | `rejected`. The enum holds two members on purpose: the
browse/click family named in 跟进单 §21 needs frontend instrumentation, and this contract does not
advertise a value that nothing writes yet.

A third key is refused with 422, and only the **field name** reaches the log, never the value - a body
carrying a free-text `note` key is precisely how a user question would end up stored in a second place.
That is why 判据③ (counts, not content) is structural rather than a promise: the only INSERT in the
module takes `(filename, 1, 0)` or `(filename, 0, 1)`.

`200` returns `{status, filename, signal, accepted_count, rejected_count}`; the two counts are the totals
for that filename *after* this write.

| Status | `detail` | when |
| --- | --- | --- |
| 401 | `authentication_required` | no principal on the request |
| 403 | `permission_denied`, or the `RetrievalScopeError.code` | the document exists but this principal may not see it |
| 404 | `resource_not_found` | the filename is not in the catalog |
| 422 | `validation_error` | body is not a JSON object, carries an extra key, or fails the shape |
| 503 | `storage_unavailable` | PostgreSQL is unreachable, or 0011 has not been applied |

Signals for documents that are not in the catalog are refused (404) instead of counted: an unregistered
key would turn the table into somewhere anyone can write, and the ranking would then read a prior with
no source. 「能不能给这篇打分」 is resolved by the single visibility judgement
(`app/rag/filters.py::resolve_document_retrieval_scope`), so it can never be wider than 「能不能看见
这篇」. Denials are audited (`record_audit` records outcome `failure`) so 判据④ is checkable as a count
of things that got through, not as a status code that looks tidy.

### `GET /api/v1/feedback/document?filename=...`

`200` returns `{filename, accepted_count, rejected_count, prior_source, prior_reason, prior_enabled}`.
The last three exist because a bare `0` cannot answer 「这篇真没人打点，还是这一趟根本没读到表」:
`prior_source` is one of `store` / `error` / `never`, and `prior_reason` says why a read failed. Reads go
through the same 30-second in-process snapshot the ranker uses - deliberately, because two SELECTs
written in two places eventually answer two different questions. A successful POST resets that snapshot,
so the receipt and the next read cannot disagree.

### What this switch does not claim

- `RAG_ACTIVITY_PRIOR` (defined in `app/rag/retriever.py`, listed in `.env.example` and
  `deploy/.env.server.example`) is on by default. `off` / `0` / `false` / `no` turn it off; a misspelled
  value does **not** - reading 「nobody configured it」 as 「it was configured off」 would make 判据②
  (identical to today when nothing signalled) unfalsifiable.
- The prior re-orders candidates that are already authorised. It adds none, removes none, and sits
  downstream of the permission filter, so it cannot widen visibility.
- Counts are aggregated by `filename` and carry no identity, and the weight (`ACTIVITY_PRIOR_WEIGHT = 0.01`) is bigger than it looks.
  Measured against the shape it adjusts (base 60 reciprocal rank): the gap between first and second is
  0.00026, while one acceptance is worth 0.0025, so a **single click moves a hit 11 places** - more
  than a whole leg, because `search()` ships `k=5`. One person,
  clicking once, can decide the top of a leg; there is no throttle and no cooldown. Recalibration is
  R153; whether to additionally cap signals per person stays an owner decision.
- 判据① (the order really changes) is proven offline today: the tests drive the ranker with fabricated
  rows, not a live PostgreSQL under concurrent clicks. Registered in 跟进单 §77 as an open item.
