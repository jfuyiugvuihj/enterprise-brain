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
`request.failed`, `request.cancelled`, and `heartbeat`. `POST /api/v1/ask` additionally emits the
canonical content event `sources` (R41, documented below) and the canonical first-screen card event
`answer.headline` (R48, documented in the R48 compatibility note below).

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

`sources` payload (`event: sources`, canonical envelope, `status: "completed"`):

- `sources` - the rows this principal may see, in retrieval order.
- `hit_count` - how many rows that is.
- `unauthorized_count` - how many retrieved rows were withheld. Without this number "0 条来源"
  cannot tell 「没检索到」 apart from 「检索到了但不给你看」, and those two need opposite replies.
- `scope_reason_code` - which scope judgement produced this list: `RetrievalScope.reason_code` from
  `app/rag/filters.py::resolve_document_retrieval_scope`, or the `RetrievalScopeError.code` when no
  usable scope could be resolved (then the rows are empty by construction, not by chance).
  `unauthorized_count` says how many rows were withheld; this names **why**, so a client need not
  re-derive the principal's scope to tell the two apart. Documented as the fifth key, which is what
  the 「the same five payload keys」 line below has been claiming all along.
- Per row, two provenance fields since R154. `excerpt` is **always present** (a string, possibly empty,
  at most 400 characters, truncated at the tool boundary by `app/agents/evidence.py::record_document_hits`)
  and is the passage that was actually used, not a sentence recovered from the answer. `published_at` is
  an ISO-8601 string and **may be absent**: absent means "this document has no published, non-tombstoned
  index version to report", which is not the same claim as "it has no date". A row is stamped only after
  it has passed `scope.allows`, so these fields add no visibility branch.
- `session_id`.

Per-row keys, all of them (registered 2026-09-22 by 总控 alongside R156: until this paragraph the two
provenance fields above were the only row keys the contract named, while the row the code builds carries
fourteen). This is a **record of what is on the wire**, not a new promise - a client must keep depending only
on what the provenance bullet above names, and the R156 same-source pin asserts only that *documented*
fields really exist and that their qualifiers do not lie. The shape comes from
`app/api/v1/chat.py::_document_source_row`, which is transport and not judgement: it copies what the tool
boundary actually retrieved (`app/agents/evidence.py::record_document_hits`) and adds no visibility branch;
a hit whose metadata is unusable is invisible, never partially shown.

| row key | where it comes from | on the wire |
|---|---|---|
| `worker` | which sub-agent's evidence this row was collected from | always |
| `source` | `source_name`, stripped | always - a row with an empty name is dropped before it can be emitted |
| `source_id` | `source_id`, falling back to `source` | always; it is also the de-duplication key when several workers hit the same source |
| `chunk_index` | the evidence locator's chunk position | may be null |
| `score`, `score_type` | the retrieval score, and which yardstick it is on | may be null |
| `excerpt` | see the provenance bullet above | always present, at most 400 characters |
| `document_version_id`, `index_version_id` | which document version and which index version produced the hit | may be null; the evidence record carries only a filename today, which is why the stamp below is keyed on the index |
| `content_sha256` | evidence metadata | may be null |
| `classification`, `department` | evidence metadata - these are the two values `DocumentRetrievalScope.allows` actually weighed | may be null; kept in the event so 「why was this one visible」 can be re-checked without re-deriving the caller's scope |
| `permission_checked` | `bool(...)` of the evidence flag | always a boolean |
| `provenance_status` | evidence-level provenance marker | may be null |
| `published_at` | **not** in the constructor: stamped afterwards, in place, by `app/api/v1/chat.py::_stamp_source_publications`, and only onto rows already granted to this caller | optional, and absence is a real answer (see the R154 compatibility note below) |

Position in the stream: after `request.completed`, before the legacy `done`. `done` stays the single
end-of-stream signal, an old client that ignores an unknown name keeps its answer, and the sequence
of `request.started` / `request.completed` does not shift.

### Compatibility note 2026-09-22 (R154: the cache-hit leg can now answer 「改版了没有」)

The asymmetry registered against R154 is closed, additively. A cache hit on `/ask` used to yield only
`status` / `text` / `done`, because the answer cache stored `{answer, created_at}` and nothing else, so a
repeated question could not name its sources. It now emits an **optional** `sources` event between `text`
and `done` with the same five payload keys and the same row shape as a live turn (`sequence` restarts at 1,
`done` remains the only terminal event). Three properties the client can rely on:

- **Absence is a real answer.** Entries written before R154, entries evicted from the cache, and entries
  that fail to parse yield **no** `sources` event - never an empty one. An empty list would say 「检索过了，
  没有来源」; absence says 「这一轮没有可交的清单」. The frontend renders these as the distinct
  `cached-unknown` face instead of guessing.
- **The counts survive the round trip.** The snapshot stores the rows *before* authorization filtering and
  the reader re-applies `_authorized_source_rows`, so `hit_count` / `unauthorized_count` on a cached turn
  mean the same thing as on a live turn. A cached turn's `published_at` is the moment recorded for that
  round; today's effective date comes from the versions route, not from a replayed answer.
- **Nothing new is decided here.** Visibility is still resolved by the single judgement in
  `app/rag/filters.py::resolve_document_retrieval_scope`; the manifest is evidence, and reading it back
  re-runs the filter.

`GET /api/v1/documents/{filename}/versions` gained the same `published_at` per row (also optional), and
`/approve` continuation turns carry both row fields. `GET /api/v1/documents/catalog` and `/documents` were not touched by that change — they
have since grown a `restricted` field, so read `## Document Catalog Visibility` below rather
than this sentence. Approval
turns (`/approve`) are unchanged in event order.
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

### Compatibility note 2026-09-24 (R48 route A: the first-screen source card)

`POST /api/v1/ask` gained one additive canonical event, `answer.headline`. It carries **which
documents this turn has already hit**, nothing else. Route A was chosen over the two alternatives
because it is the only shape that puts a `sequence` and a `timestamp` on the wire for that reading.

Position in the stream: after `request.started`, and as early as the turn has one *visible* source
row in hand - i.e. the moment the tool boundary reports evidence that `scope.allows` grants to this
caller. At most one per turn. `answer.headline` does not shift the relative order or the numbering of
anything that already ran: every emission shares one `sequence` counter, so `sources` still follows
`request.completed` immediately.

Envelope: the same builder as `request.started` (`canonical_sse_event`), so the seven envelope keys are
identical, with `status: "running"` - the card is not a terminal signal and no client may treat it as
one. Keys inside `data`:

| data key | what it is | on the wire |
|---|---|---|
| `session_id` | the turn this card belongs to | always |
| `carries_answer` | literal `false`, always. A client must not render this card as an answer, and the flag exists so that rule is machine-checkable rather than a comment | always |
| `sources` | up to `HEADLINE_SOURCE_LIMIT` rows, retrieval order, already filtered by `_authorized_source_rows` | always an array; a withheld filename never appears in it, not even as a string |
| `shown_count` | how many rows the card carries | always |
| `hit_count` | how many *visible* rows the turn had at the moment the card was sent - so a truncated card still reports the real total | always |
| `unauthorized_count` | how many retrieved rows were withheld at that moment | always |
| `elapsed_ms` | milliseconds between the turn starting and the card being built | always |

The row shape is the `sources` event's row shape, copied verbatim, so a client needs no second parser
and the contract does not grow a second field list. 🔴 The card is deliberately **not** a preview of
the answer: nothing in it is model output, no extra model call is made for it, and nothing is cut out
of `msg.content`. It is also never emitted on the `event: text` channel - a card frame that rides the
text channel would make the streaming yardstick read green (`text_frames > 1`, `max_stream_frames > 1`,
`prefix_breaks == 0`, `extra_chars == 0` all at once) for a turn that streams nothing at all. This is
pinned as behaviour, at `_consume` level, by `tests/test_r48_headline_never_enters_the_text_ledger.py`.

Absence is a real answer, three separate ways:
- a turn whose retrieved rows are all withheld sends **no** card (「检索到了但不给你看」),
- a turn that retrieved nothing sends **no** card (「库里没有」),
- and neither case may be papered over with an empty card - the two faces above belong to the
  `sources` event at the end of the turn, which is where the counts and the scope reason live.
- the cache-hit leg and the `/approve` continuation leg send no card: the first answers in
  milliseconds with its body already present, the second is the same turn resumed after an approval.

🔴 What this event does **not** claim: 「首屏 ≤1 s 有可用结论」 is not met and is not declared met. The
measured floor on this hardware is 11.0 s for a single generated token
(`docs/perf/raw/rate_prefill.jsonl`) and 27.5 s for the shortest real product leg
(`docs/perf/raw/rounds.jsonl`), so within one second there is no generated conclusion to show. What
lands within a second is a card of *readings*, and a change of yardstick is the owner's call, not this
event's. Clients must label the card as sources-not-conclusion (see `answer.headline` handling in
`frontend/src/lib/sessions.js`), and must not quote it as an answer.

## HITL Pending Listing (2026-09-16, R13)

`GET /api/v1/hitl/pending` is the read side of the parked-turn ledger added by
`migrations/0008_pending_approvals.sql`. Query params: `session_id` (optional filter), `limit`
(default 50, clamped to at least 1 and at most 200, `chat.py:1257-1258` and `:1290`), `offset`
(default 0). First registered by the coordinator at `1672841` (**800 passed / 22 skipped**);
re-registered on 2026-09-16 after `5ea8dee` (paging), `35ee27e` (missing-table 503) and `6606f59`
(code ratification), against the suite at **831 passed / 22 skipped / 0 failed**.

Shape (as implemented, not as aspirational). R175 grew a second list on the same call; this block
and the two key tables in the subsections below are one shape, and
`tests/test_r191_hitl_contract_pins.py` compares all three of them against the `return` dict of
`app/api/v1/chat.py::hitl_pending`:

```
{ "items": [ { "session_id", "owner_user_id", "parked_steps": [node...], "labels": [..],
               "status", "created_at", "expires_at", "request_id", "trace_id", "task_id" } ],
  "count": <== items.length, after filtering>, "limit": <applied>, "offset": <applied>,
  "has_more": <bool>,
  "failed_turns": [ { "session_id", "owner_user_id", "parked_steps": [node...], "status",
                      "created_at", "expires_at", "request_id", "trace_id", "task_id" } ],
  "failed_turns_has_more": <bool> }
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

### `GET /api/v1/hitl/pending` -> response envelope

Machine-checked section. Every key table below is compared, in order and in both directions, with
the AST of `app/api/v1/chat.py::hitl_pending`: its single `return` dict, the dict literal appended
to `items`, and the dict literal inside the `failed_turns` comprehension. The pins live in
`tests/test_r191_hitl_contract_pins.py`. A key built in code and missing here is a hole in this
contract; a key documented here and not built is a client reading a field that never arrives.

| key | type | meaning |
| --- | --- | --- |
| `items` | object[] | parked rows this principal owns, each reconfirmed against the graph. One key wider than the table below: `labels`, which only the rechecked rows may carry |
| `count` | int | `len(items)`, after filtering and after the recheck dropped rows - a page length, never a total of open approvals |
| `limit` | int | the applied limit: default `DEFAULT_PENDING_LIMIT` (50), clamped to at least 1 and at most `MAX_PENDING_LIMIT` (200) |
| `offset` | int | the applied offset. It pages `items` and **does not** page `failed_turns` |
| `has_more` | bool | the awaiting leg of the ledger holds rows beyond this page, not "more rows you are allowed to see" |
| `failed_turns` | object[] | rows the ledger closed as `failed`: the approver decided and the system did not finish that round - shape in the next subsection |
| `failed_turns_has_more` | bool | the failed leg holds more rows than the applied limit; since `offset` is not applied to that leg, "more" is a standing fact here, not a next page this call can move through |

Four rules a consumer has to be able to read off this table:

* **Both legs are one request.** `failed_turns` comes from the second read of the same ledger
  (`app/storage/pending_approvals.py::failed_items`) inside the same `try`, so a missing table is
  still `503 storage_unavailable` for the whole call. Answering "you have no failed turns" for a
  ledger that could not be read would be the second lie on top of the first.
* **Rows in `failed_turns` are never reconfirmed against the graph.** `check_interrupt` answers "is
  this still parked?", and for a closed row the answer is always no; running that leg over these
  rows would mark them `stale` (「已作废」) in place, which is the exact sentence R175 exists to
  remove. This endpoint asks the graph once per listed to-do and zero times per failed turn.
* **`offset` does not move the failed leg.** The code calls `failed_items(..., offset=0)`
  unconditionally, so this list is always the newest `limit` closed-as-failed rows, ordered
  `created_at DESC`. A screen that pages `items` with 「看更早的」 must keep this block as what it
  is (the recent ones) and must not present the second page of to-dos as a second page of failed
  turns. Paging this leg is not offered by v1.
* **Empty `items` plus non-empty `failed_turns` is a real state.** The two blocks do not substitute
  for each other: 「没有等你拍板的事」 and 「你批过了，那一轮失败了」 are statements about two
  different sets of rows, and each may only ever be rendered from its own list.

### `GET /api/v1/hitl/pending` -> `failed_turns[]` rows

```json
{
  "failed_turns": [
    {
      "session_id": "sess-1",
      "owner_user_id": "u-1",
      "parked_steps": ["chart"],
      "status": "failed",
      "created_at": "2026-09-23T09:12:44.123456+08:00",
      "expires_at": "2026-09-23T11:12:44.123456+08:00",
      "request_id": "req-1",
      "trace_id": "trace-1",
      "task_id": "task-1"
    }
  ]
}
```

| key | type | meaning |
| --- | --- | --- |
| `session_id` | string | the conversation the parked round belonged to - the same route a client uses to re-ask |
| `owner_user_id` | string | whose ledger this is; the read is filtered by it fail-closed, so it is the caller's own id |
| `parked_steps` | string[] | the step names that were parked when the round died, from `_HITL_PARKED` and nothing else |
| `status` | string | always `failed` in this list - see the value domain below |
| `created_at` | string | when the round parked |
| `expires_at` | string | end of the action window: past it the row leaves this list but stays in the ledger and the audit trail |
| `request_id` | string | locates the dead round in the audit log; the only handle back to 「哪一轮」 |
| `trace_id` | string | the trace of that round |
| `task_id` | string | the queue task of that round, empty when the run was inline |

There is deliberately **no `labels` key** in this shape, and that is the whole difference between
the two element shapes: `labels` is the only key `items` rows carry that these do not, and these
carry nothing that `items` rows lack. Labels are read off the graph during the recheck, which this
list is forbidden to run (above). A client that needs a human-readable step name says it out of
`parked_steps`, whose values come from the same compile-time constant `items` uses, and it must not
invent a status the backend did not report.

### The `failed` terminal status, and the CHECK that had to widen to admit it

`pending_approvals.status` value domain: awaiting | resumed | refused | abandoned | stale | failed

`items[].status` value domain: awaiting

`failed_turns[].status` value domain: failed

`DECIDED_STATUSES`: resumed | refused | abandoned | failed

`pending_approvals_status_check` accepts: awaiting | resumed | refused | abandoned | stale | failed

Those five lines are not prose to be skimmed. Each is compared with a constant read out of
`app/storage/pending_approvals.py` by AST, and the last one with the text of the CHECK that is
*actually in force*: `migrations/0013_pending_approvals_status_includes_failed.sql` redefines
`pending_approvals_status_check`, so the pin reads the last redefinition by filename order instead of
trusting the five-value text still sitting in `migrations/0008_pending_approvals.sql`. Neither side may
say "five" where the other says "six" - and this file may not promise a wide CHECK the SQL does not hold.

What each decided value means, and why `failed` is a fifth thing rather than a synonym:

* `resumed` - the approver pressed 「同意」 and the round went on running.
* `refused` - the approver pressed 「驳回」. The employee said no.
* `abandoned` - the run was cancelled or stopped while parked. Meaningful only since R12's
  cooperative cancellation (`826d318`): before it, a "stopped" run still finished, and the label
  would have asserted something the process had not done.
* `stale` - nobody decided. A newer park on the same session superseded this row, the graph
  recheck no longer confirms it, or it aged past the approval TTL (reported stale, never deleted).
* `failed` - **the approver decided, and the system did not finish the round.** Written by
  `app/api/v1/chat.py::_fail_pending_approval_turn` on exactly two legs of `/approve`: the error
  leg (`request.failed` carrying `internal_error`) and the budget leg (`request.failed` carrying
  `task_timeout`), both of which used to `break` with the row still `awaiting`. It closes the row
  through the same `mark_status` and the same `DECIDED_STATUSES` as its three neighbours - no
  second state machine, no second ledger, no new table.

`failed` must never be written as one of its neighbours. 「批过然后系统跑挂」 is not `refused` - that
puts a refusal in the approver's mouth, the same ruling as the cancel leg's 「停止 != 拒绝，账面写
abandoned，绝不写 refused」. It is not `abandoned` - nobody stopped anything. It is not `stale` -
the graph may well still be parked on that very interrupt, and `stale` would tell the approver
their own decision expired by itself.

**`failed` is stored in PostgreSQL today.** It is a member of the CHECK in force, so
`mark_status(..., "failed")` moves the row on a PostgreSQL deployment exactly as it does in the local
file ledger: the same `mark_status`, the same `DECIDED_STATUSES`, one read path, no second state machine
and no second ledger. That was not true when this subsection was written. Until 0013 landed, 0008's CHECK
did not admit `failed`, so the PG leg raised, `_decide_pending_approval` recorded the exception instead of
interrupting the answer, and **that row stayed `awaiting`** - neither reported as decided nor closed, with
`failed_turns` coming back empty for it. The sentence above is today's fact and the paragraph before it is
yesterday's; only one of them may be quoted at a customer.

**What keeps this subsection from ageing into a second set of truth.** The rewording obligation sat on the
change that closed the gap - the R190 merge, whoever widens `pending_approvals_status_check` or grows
`app/storage/pending_approvals.py::PG_STATUSES` - and not on some later reader of this file. The fuse is
`tests/test_r191_hitl_contract_pins.py::test_the_contract_states_the_pg_gap_while_the_gap_exists`, which
now runs in two directions: while the code reports a gap (`ALL_STATUSES - PG_STATUSES` non-empty) it demands
the "PG cannot store it" sentences stay here, and with the gap closed - as today - it refuses to let those
sentences keep lying in place. Either half flipping without the other goes red by name. What no direction
permits is the old shortcut R175 was filed against: writing `refused` or `abandoned` to make the numbers add
up.

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

`status` is one of `queued`, `processing`, `cancel_requested`, `done`, `cancelled`, `failed`, `dead`, `awaiting_approval`, or `expired`.
A `done` or `awaiting_approval` response additionally carries `result` plus the structured terminal
readout documented in `Structured Terminal Readout (2026-09-25, R254)` below.

The vocabulary is split twice over: by which layer answers the value, and by whether polling should
stop. A non-terminal value means the task can still move; a terminal value means its outcome will not
change, so the client must stop polling.

* `queued` (non-terminal, written by the queue): `submit()` writes it when a task arrives, and
  `fail_or_retry()` writes it again when a retryable attempt goes back for another run.
* `processing` (non-terminal, written by the queue): `reserve()` moved the task onto the processing
  list under a live lease. A task whose lease was dropped without an acknowledge stays here, so this
  is what a client reads while an attempt runs and between a lost lease and the next sweep.
* `cancel_requested` (non-terminal, written by the queue): `cancel()` was called after the task had
  already left the pending list, so the cancel mark is recorded and the owning worker settles the task
  on its next check. From here the task ends `cancelled`; it never becomes `done`.
* `done` (terminal, written by the queue): `ack()` closed the task while it still held its lease, and
  the answer is readable as `result`.
* `cancelled` (terminal, written by the queue): the task was cancelled while it still sat on the
  pending list, or a worker found the cancel mark before or after running it and discarded the result
  instead of publishing it.
* `failed` (terminal, written by the queue): `reserve()` found a request id on a list whose message
  payload is already gone, so there is nothing left to run and no attempt was made for it.
* `dead` (terminal, written by the queue): `fail_or_retry()` gave up on the task, either because it
  exhausted `max_attempts` or because it was failed with `retryable=False`; see the compatibility
  note below.
* `awaiting_approval` (terminal, written by the queue): the run stopped in front of a HITL step and
  published no answer at all, so `result` is `null` and `approval` names the thing a human can
  approve. Terminal **for the poll** - nothing more will happen by itself, so a client must stop
  polling - but not terminal **for the turn**: `POST /api/v1/approve` moves it again without
  re-asking the question. It is never `done`, and it never carries the parked notice as `result`.
* `expired` (terminal, answered by the route): the queue's status key can no longer be read, so
  `GET /api/v1/queue/status/{request_id}` answers this value itself; the queue never writes it.

A `complete()` that returns `False` is a discard, never a completion: no answer is published,
the status is never `done`, and `failure.last_error` records the stable code
`result_discarded:cancelled` or `result_discarded:lease_lost`. A lease-discarded task stays on the
processing list without a lease, so the next sweep requeues it and only the attempt that still
holds a live lease may publish; a discard never consumes a retry slot.

### Structured terminal readout (2026-09-25, R254)

Before R254 the queue lane published exactly one string. That string was the only thing a client
could ever read back, and it produced three measured lies (see
`docs/testing/run8-phase2-readout-2026-09-25.md`): eleven parked turns handed back the 37-character
「waiting for your confirmation」 sentence **as the answer** while reporting `done`; a turn with zero
model calls reported `done`; and no turn could deliver sources or token usage at all, because
`complete()` had nowhere to put them.

`GET /api/v1/queue/status/{request_id}` now answers the two published states with the keys below.
`status`, `request_id` and `failure` keep their old meaning; the queue's own authorization gate is
unchanged and is still walked before a single one of these keys is read.

```json
{
  "status": "done",
  "request_id": "6f1c…",
  "result": "上季度毛利率 38.2%，环比 +1.4 个百分点。",
  "failure": {"attempts": 1, "last_error": null, "max_attempts": 3},
  "terminal_schema": "queue-terminal-v1",
  "terminal_state": "answered",
  "answer_present": true,
  "answer_is_park_notice": false,
  "worker_status": "success",
  "sources_present": true,
  "sources": [{"worker": "doc", "source": "经营月报.pdf", "excerpt": "…", "published_at": "…"}],
  "scope_reason_code": "department_and_classification",
  "sources_error": "",
  "usage": {
    "prompt_tokens": 91271,
    "completion_tokens": 18859,
    "total_tokens": 110130,
    "model_calls": 70,
    "calls_with_token_readout": 68,
    "calls_missing_token_readout": 2,
    "token_readout_complete": false,
    "authoritative": true,
    "ledger": "postgres_model_calls"
  },
  "approval": null,
  "terminal_note": ""
}
```

| key | what it says |
|---|---|
| `terminal_state` | `answered` or `awaiting_approval`. The queue's status key is derived from this one field, so a payload cannot say it is waiting for a human while the status says `done`. |
| `answer_present` | whether `result` really is answer text. A parked turn publishes no answer at all (`result` is `null`), so 「ran out with an empty body」 and 「is waiting for you」 stay distinguishable. |
| `sources`, `sources_present`, `scope_reason_code` | the same rows the synchronous lane puts on its canonical `sources` event, filtered by the same `DocumentRetrievalScope.allows`. This adds no visibility branch and loosens no check. |
| `sources_error` | 「could not be computed at all」 (`principal_unavailable`, `sources_unavailable`, `answer_cache_without_manifest`) - a different claim from 「zero rows」. |
| `usage` | prompt / completion / total tokens plus the call count, summed over the `model_calls` rows of this `request_id` in the same PostgreSQL the server writes them to. Nothing is estimated: `calls_missing_token_readout` counts the rows that reported no token and `token_readout_complete` is `false` whenever the ledger holds such a row. `total_tokens` is prompt + completion, an arithmetic result rather than a third reported number. `authoritative` is `true` only for `ledger: "postgres_model_calls"`; a box whose ledger cannot be read answers with nulls in the four number slots and **no** zero, because 「did not read」 and 「read zero」 are different facts. |
| `approval` | what a human can act on, for `awaiting_approval` only: `session_id`, `pending_steps`, `labels`, the parked sentence as `notice` (a notice, never a result), and the addressable `decide_method` / `decide_path` / `decide_body` for `POST /api/v1/approve`. `ledger_status` is re-read from the pending-approval ledger at the time of the poll using the vocabulary the `HITL Pending Listing` section already names (`awaiting`, `resumed`, `refused`, `abandoned`, `stale`, `failed`), plus `absent` / `unavailable` / `owner_mismatch` / `no_session`. |
| `terminal_note` | one human-readable sentence for the two states below; empty on a structured row. |

The synchronous lane's legacy `event: done` frame carries the same readings under the same names, so one
parser covers both lanes. Its frame name, its `type` key, and the rule that `done` is the only
end-of-stream signal are untouched (freeze rule 1); every key below it is additive:

```json
{
  "type": "done",
  "terminal_state": "awaiting_approval",
  "answer_present": false,
  "sources_present": false,
  "sources": [],
  "sources_error": "",
  "usage": {"prompt_tokens": 412, "completion_tokens": 0, "total_tokens": 412, "model_calls": 1,
            "calls_with_token_readout": 1, "calls_missing_token_readout": 0,
            "token_readout_complete": true, "authoritative": true, "ledger": "postgres_model_calls"},
  "approval": {"session_id": "…", "pending_steps": ["export"], "labels": ["📋 导出报告"],
               "notice": "本轮在「📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答内容。",
               "decide_method": "POST", "decide_path": "/api/v1/approve",
               "decide_body": {"session_id": "…", "approved": true}, "decide_note": "…"}
}
```

`sources_error` on this frame carries the one claim the synchronous lane can make and the queue lane
cannot: an answer-cache entry written before per-turn source manifests existed, or whose manifest
will not parse. That leg answers `answer_cache_without_manifest` beside an empty `sources` list, which
says 「cannot be verified」, not 「there were none」 - the same distinction `provenance.js` keeps as its
fourth cache state (`cached-unknown`). A bare empty list would be the other claim.

`usage` on that frame is summed from the `model_calls` rows of the same `request_id` in the same
PostgreSQL, so the two lanes cannot disagree about what a turn cost. `approval` is the same handle the
queue hands back, minus `ledger_status` - that one is a read taken at the moment of a poll, and a stream
that never polls has no moment to read it at. `terminal_state` on this frame takes a fourth value the
queue cannot carry, `no_answer`: the graph finished and produced no body at all, which the stable code
`no_answer_produced` already named on the canonical channel. A parked turn's frame says
`awaiting_approval` here exactly as it does in `status` there.

**A run that made zero model calls may not report `done`.** When the authoritative ledger holds no
`model_calls` row for this `request_id`, the worker does not publish: it fails the attempt with
`last_error` `no_model_call_recorded` and lets the ordinary retry budget decide between `queued` and
`dead`. It does not declare the task non-retryable - the queue layer has no standing to make that
call for the contract. When the ledger is not authoritative the gate cannot run, and the response
says so rather than pretending it passed.

### Compatibility note 2026-09-25 (R254: rows published before the structured terminal)

Rows already in Redis when this ships have no `:terminal:` key. They stay readable, and they are
marked instead of guessed: `terminal_schema: "legacy"`, `terminal_state: "legacy_row"`,
`usage: null`, `sources: []`, `approval: null`, and `answer_is_park_notice` computed by rebuilding
the parked sentence from `hitl_park_text` and comparing byte for byte. A legacy row therefore says
「I cannot tell you whether this had sources」, which is true, instead of 「there were none」, which is
not. A terminal key that is present but will not parse reports `terminal_schema: "unreadable"` /
`terminal_state: "unreadable_terminal"` - corruption and legacy are two different diagnoses.

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

## Dataset Row-Level Visibility (2026-09-23, R180 / R186)

Two dataset routes report a **row-level** verdict next to the file-level grant they already
honoured, and they report it inside the *success* body - never folded back into the file-level
answer, never degraded into a 404 or an empty list. Being allowed to open a dataset is not the
same as being allowed to read every row of it; being refused some datasets is not the same as
there being none. Both fields are additive: a client that ignores them keeps working, and a
client that reads them must not restate them as absence. That restatement ("there are none") is
exactly the class of defect R163 catalogued as class B, and `frontend/src/components/DataPanel.vue`
is the consumer that R186 made stop doing it.

Machine-checked against the construction sites: `app/api/v1/data.py::_row_scope_status`
(`app/api/v1/data.py:132-169`, attached at `app/api/v1/data.py:319`) and
`app/api/v1/data.py::list_data_files` (`app/api/v1/data.py:240-249`). The pins live in
`tests/test_r186_row_scope_contract.py`; they compare key sets, code value domains and the
sentence a route emits, so prose and code cannot drift apart silently.

### `GET /api/v1/data-files/{filename}/preview` -> `preview.row_scope`

Requires `resource:view` like every other preview path; a file-level refusal is still a `403`
with the policy reason code and never reaches this layer. This field is the row-level layer, and
every successful response of this route carries it - including the ordinary answer, where the two
counts are equal or only part of the frame is visible and `code` stays the empty string:

```json
{
  "row_scope": {
    "code": "",
    "reason_code": "department_scope",
    "rows_in": 120,
    "rows_visible": 40
  }
}
```

| key | type | meaning |
| --- | --- | --- |
| `code` | string | the row layer's own verdict; see the value domain below |
| `reason_code` | string | `app/common/rbac.py` row-scope reason passed through verbatim - **not** a contract enum, consumers must branch on `code` |
| `rows_in` | int | rows in the frame before row-level filtering |
| `rows_visible` | int | rows the caller may see, i.e. the rows the rest of this body describes |
| `message` | string | optional; present only when the row layer has something to say (see below) |

`row_scope.code` value domain: row_scope_denied | no_visible_rows | ""

* `row_scope_denied` - the frame had rows and the caller may see none of them, and rbac can show
  the department dimension really hid them. The rows exist; they are outside this account's
  visibility. This is the only member of the domain that carries a `message`.
* `no_visible_rows` - the frame came back empty and the row layer **deliberately declines to say
  why**. The department dimension had not hidden a row, so the clearing came from some other,
  unratified dimension (classification is H13, owner-open). Guessing a cause here would present an
  unratified dimension as a permission call, which R62/R64 ruled out.
* `""` - nothing for this layer to report: a normal answer (some or all rows visible), or a table
  that genuinely has no rows. A genuinely empty table is *not* a permission event; it stays with
  the R170 `profile.empty` marker, and consumers must not dress it in visibility wording.

`message` is attached under the same condition as `row_scope_denied`, so the two cannot disagree.
The sentence is the tool leg's own - `app/agents/tools.py::_row_scope_reason`, one translation
source for both the streaming tool answers and this route - and it is composed from rbac counters
only. Example, with the shape the route actually returns:

```json
{
  "row_scope": {
    "code": "row_scope_denied",
    "reason_code": "department_scope",
    "rows_in": 3,
    "rows_visible": 0,
    "message": "本表 3 行属于其他部门，都不在当前账号（部门「财务」）的可见范围内"
  }
}
```

When `code` is `no_visible_rows` the `message` key is **absent**, not empty. Consumers must then
either stay silent or state only facts this body already carries (`rows_in`, `rows_visible`); they
must not reuse the `row_scope_denied` sentence, and must not introduce permission, visibility or
department wording of their own.

`rows_in > rows_visible > 0` keeps `code: ""` - it is a normal answer, not a refusal - but the two
counts differ, and a consumer that prints `rows_visible` as the size of the table is lying about
the table. Say both numbers.

A refusal at this layer is audited (`record_audit(... "denied" ...)` with subject, dataset id and
verdict only) while the body stays free of row contents, column names, and any other account's
department.

### `GET /api/v1/data-files` -> `restricted`

The catalogue appends one key when registered active datasets exist that this principal was
refused at the file level. It is **absent entirely** when nothing was refused, so "no key" means
"nothing is being hidden from you", not "the check failed". How that object is built is said once
for every exit that carries it - see `restricted -> the one shared projection` under
`## Document Catalog Visibility` - so this leg registers only what is its own: the sentence below.

```json
{
  "files": [],
  "restricted": {
    "count": 2,
    "reason_codes": ["department_scope_denied"],
    "message": "有 2 个数据文件存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文件的部门标注。"
  }
}
```

| key | type | meaning |
| --- | --- | --- |
| `count` | int | how many registered, present datasets were refused for this caller |
| `reason_codes` | string[] | distinct policy reason codes, in first-refusal order - **not** a contract enum |
| `message` | string | the ready-made sentence for this case; present whenever `restricted` is |

`restricted.message` template (the route substitutes the count; the wording is the contract):

`有 {count} 个数据文件存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文件的部门标注。`

**Why nothing is named.** A refused dataset contributes no filename, no dataset id and no
classification to this response - only a tally and the reason codes. Naming a resource an account
has no scope for is itself a disclosure: it would hand a caller a way to enumerate other
departments' files through an endpoint that is only supposed to say "some are not yours", while
`GET /api/v1/data-files/{filename}/preview` still answers those very names with `403`/`404`. Every
other dataset route already hides behind those two codes, so the catalogue keeps the same boundary
and speaks the *quantity* instead. Each refusal is separately audited with subject, dataset id and
verdict.

Three cases the catalogue must not collapse into one another, and the consumer's duty:

* a file that is not in the registry at all is not part of the managed catalogue: the policy was
  never consulted, so it is neither listed nor counted in `restricted`;
* a file that is registered, present and refused is counted in `restricted` and is *not* "missing";
* `restricted` absent plus an empty `files` is the only shape that entitles a screen to say
  「暂无数据文件」. A screen that renders an emptiness sentence while `restricted.count` is
  non-zero contradicts itself in one breath, which R186 pins in
  `frontend/src/components/__tests__/r186-row-scope-voices.test.js`.

> The two flat document routes are specified in their own section,
> `## Document Catalog Visibility (2026-09-24, R194 / R201)`. Their sentences used to sit here as
> prose because the set of subheads in this part of the contract is pinned; R201 moved the block
> out instead of adding a third one, and welded it to the AST of the routes.

> **Merged (R200)**: the object is no longer spelled out twice. One builder owns it -
> `app/api/v1/restricted.py::restricted_summary` - and the two sentences are the module constants
> sitting next to it, `DATA_FILE_TEMPLATE` (the one above) and `DOCUMENT_TEMPLATE` (the one in the
> canon section below). A leg hands that builder its own refused `(resource, reason code)` pairs and
> its own sentence and keeps no shape of its own: `app/api/v1/data.py` is this leg,
> `app/api/v1/chat.py` is the two document routes. What stays local to this page is therefore only
> the sentence; the key list and its order, the tally behind the count, the ordered single-pass dedup
> and the boundary that a thing counted is never a thing named are stated once, under
> `restricted -> the one shared projection` below, and are the same words at every exit.
> `tests/test_r200_restricted_single_source.py` scans `app/**` for the construction site and turns
> red the moment a second one appears, so this paragraph cannot be left behind by the code again.


## Document Catalog Visibility (2026-09-24, R194 / R201)

Two flat document routes answer a listing request with a *success* body that has to carry two
different facts: which documents this caller may read, and how many documents exist that this caller
may not. Both carry the second fact in the same optional key, and the rule that builds it is stated
once below, under `restricted -> the one shared projection` - there is no second place that could
start saying something the other one does not.

Machine-checked against the construction sites, never against a hand copy: the envelope comes from
`app/api/v1/chat.py::list_documents` and `app/api/v1/chat.py::list_document_catalog`, the withheld
tally from `app/api/v1/restricted.py::restricted_summary`, and one array element of the catalogue from
`app/documents/catalog.py::public_document_row`, whose offline twin
`app/documents/catalog.py::_local_row` has to keep the same key set. The pins live in
`tests/test_r201_flat_document_contract.py`: key sets and their order, the element type of each
array, the ownership marker and the message sentence are compared with the AST of those four
construction sites, so prose and code cannot drift apart silently. Neither route declares a
`response_model`: the dict the body builds *is* the wire shape, and a route that ever grows a model
of its own has to make this page say so.

### `GET /api/v1/documents` -> body

```json
{
  "documents": [
    "handbook-v3.txt",
    "policy-2026.txt"
  ],
  "restricted": {
    "count": 2,
    "reason_codes": [
      "department_scope_denied"
    ],
    "message": "有 2 份文档存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文档的部门、密级标注。"
  }
}
```

```json
{
  "documents": [
    "handbook-v3.txt"
  ]
}
```

| key | type | presence | meaning |
| --- | --- | --- | --- |
| `documents` | string[] | always | plain array of filenames, each one read from `filename`: what this caller may view **and** what the index currently holds, newest version only |
| `restricted` | object | only when refused | the withheld tally, `restricted` below; absent entirely when nothing was refused |

* `documents` is an **intersection**, not the visible list: a document this caller may see whose
  latest version was never published into the index appears in neither `documents` nor
  `restricted`. That is an indexing fact and not a permission fact, and
  `GET /api/v1/documents/catalog` is where it shows up.

### `GET /api/v1/documents/catalog` -> body

```json
{
  "documents": [
    {
      "filename": "handbook-v3.txt",
      "version": 2,
      "classification": 1,
      "department": "finance",
      "storage_path": "documents/handbook-v3__v2.txt",
      "created_at": "2026-09-18T22:01:04+08:00",
      "owner_id": "u-17",
      "size_bytes": 20480,
      "parse_status": "ready",
      "ownership": "owned",
      "index_status": "indexed",
      "index_reason": ""
    },
    {
      "filename": "policy-2026.txt",
      "version": 1,
      "classification": 3,
      "department": "",
      "storage_path": "documents/policy-2026__v1.txt",
      "created_at": "2026-09-14T09:02:11+08:00",
      "owner_id": null,
      "size_bytes": 4096,
      "parse_status": "ready",
      "ownership": "legacy"
    }
  ],
  "restricted": {
    "count": 1,
    "reason_codes": [
      "department_scope_denied"
    ],
    "message": "有 1 份文档存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文档的部门、密级标注。"
  }
}
```

| key | type | presence | meaning |
| --- | --- | --- | --- |
| `documents` | object[] | always | every document this caller may view, indexed or not; each row is the `documents[]` shape at the end of this section, built by `public_document_row` |
| `restricted` | object | only when refused | the same projection as `GET /api/v1/documents`, the same builder, one shape for both |

The catalogue does not intersect with the index the way the flat route above does: a row that is
visible but not indexed is exactly the difference the two routes are allowed to disagree about.

For a caller nothing was refused from, the answer is one key shorter:

```json
{
  "documents": [
    {
      "filename": "handbook-v3.txt",
      "version": 2,
      "classification": 1,
      "department": "finance",
      "storage_path": "documents/handbook-v3__v2.txt",
      "created_at": "2026-09-18T22:01:04+08:00",
      "owner_id": "u-17",
      "size_bytes": 20480,
      "parse_status": "ready",
      "ownership": "owned",
      "index_status": "indexed",
      "index_reason": ""
    }
  ]
}
```

### `restricted` -> the one shared projection

**Canon - one judgement, one projection.** Every exit that answers a refusal with a tally builds it
the way this subsection says, and this is the only place the contract states the rule: the policy
layer judges once, the route counts what that judgement already returned, and the projection only
*explains* it. Judgement and counting happen once, so a route never counts permissions a second
time, and the object therefore carries the number and the stable codes behind it in the order of the
table below - at every exit that has one, identically. Since R200 the rule has exactly one
implementation as well: `app/api/v1/restricted.py::restricted_summary`, next to whose two module
constants the two sentences live, one per leg; every exit calls that builder and shapes nothing of
its own, and a second construction site is a red test rather than a documentation task. What may
differ per exit is the sentence alone, and each exit registers its own wording where it is specified:
the dataset leg lives in `## Dataset Row-Level Visibility`, and its sentence is a different sentence
because a dataset is not a document.

| key | type | presence | meaning |
| --- | --- | --- | --- |
| `count` | int | always | how many documents exist outside this caller's visibility; the same `len(withheld)` that the sentence below repeats |
| `reason_codes` | string[] | always | the distinct policy reason codes of those refusals in first-seen order (`dict.fromkeys`) - **not** a contract enum, branch on presence and never on a name |
| `message` | string | always | the ready-made sentence for this case; present whenever `restricted` is |

`restricted.message` template (the projection substitutes the count; the wording is the contract):

`有 {count} 份文档存在，但不在当前账号的可见范围内；如需访问，请联系管理员核对你的部门归属与文档的部门、密级标注。`

Nothing in this object names a document: a withheld row contributes a tally and its reason code
only, never a filename, never an id, never a classification. Each refusal is separately audited
with subject, filename and verdict, and this body stays free of that record.

**`GET /api/v1/documents` and `GET /api/v1/documents/catalog` -> `restricted`**
> Rewelded 2026-09-24 (R201): the two flat document routes are specified here, in their own
> section, and the subheads of the dataset section above stay pinned by the R186 contract test -
> which is why they still carry no third one. If a subhead is ever added there, it needs its own
> justification for not speaking for the other field.

Both flat document routes answer with the **same** optional key, built by one shared projection
(`app/api/v1/restricted.py::restricted_summary`), and its keys are exactly the table above: `documents`
stays a plain list of what the caller may see, while a caller who was withheld documents sees
`restricted` next to it instead of a shorter list plus silence. How that key is arrived at is stated
once, in the canon at the head of this subsection; the routes add no tally of their own.

* `restricted` **absent** plus a non-empty `documents` means nothing is being hidden;
* `restricted` **absent** plus an empty `documents` is the only shape that entitles a screen to say
  「没有文档」;
* the flat route is a plain array of filenames and is **not** paginated — it declares no query
  parameters, so `?page=&page_size=` on it is discarded by the framework, not honoured.

### `GET /api/v1/documents/catalog` -> `documents[]` rows

```json
{
  "filename": "handbook-v3.txt",
  "version": 2,
  "classification": 1,
  "department": "finance",
  "storage_path": "documents/handbook-v3__v2.txt",
  "created_at": "2026-09-18T22:01:04+08:00",
  "owner_id": "u-17",
  "size_bytes": 20480,
  "parse_status": "ready",
  "ownership": "owned",
  "index_status": "indexed",
  "index_reason": ""
}
```

A row stored before an index decision was ever recorded answers without that pair, and a client
must read the absence as no decision, never as not indexed:

```json
{
  "filename": "policy-2026.txt",
  "version": 1,
  "classification": 3,
  "department": "",
  "storage_path": "documents/policy-2026__v1.txt",
  "created_at": "2026-09-14T09:02:11+08:00",
  "owner_id": null,
  "size_bytes": 4096,
  "parse_status": "ready",
  "ownership": "legacy"
}
```

Required keys come first and the two conditional keys come last; that is the order of this table, not
an order on the wire. The conditional pair is what a row drops when no index decision was ever
recorded for it: a row stored before that decision existed stays silent rather than being
stamped a value it never carried, and silence is not the same answer as `excluded`, which is a
decision somebody made.

| key | type | presence | meaning |
| --- | --- | --- | --- |
| `filename` | string | always | the document name, as the catalogue registered it |
| `version` | int | always | the newest version of that document; one row per document, not per version |
| `classification` | int | always | the recorded classification level this row was judged with |
| `department` | string | always | the recorded department scope; empty means no department was recorded |
| `storage_path` | string | always | an opaque de-identified reference, never a server path (Wave 1 above) |
| `created_at` | string | always | when that version was recorded |
| `owner_id` | string / null | always | the owning account, or `null` for a row that predates document ownership |
| `size_bytes` | int | always | the stored size the catalogue resolved for that version |
| `parse_status` | string | always | how the parse of that version ended |
| `ownership` | string | always | which of the two visibility groups this row belongs to: `owned` or `legacy` |
| `index_status` | string | only when recorded | whether the assistant can find this version: `indexed`, `excluded` or `unknown`; the pair is absent when no decision was ever recorded |
| `index_reason` | string | only when recorded | the stable reason an `excluded` row gives; the empty string for every other state |

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
| `canonical_sse_event()` | `request.started`, `request.completed`, `request.failed`, `request.cancelled`, `answer.headline` | no | emitted |
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
- ✅ Met 2026-09-21: `/ask` emits a canonical `sources` event, and its payload shape is documented
  above. The event itself landed with R41; what was missing until today was the documentation half,
  which is why this line still read as unmet. 🔴 It is met for the normal answer path only - the
  cache-hit leg emits no `sources` (R154), so a client cannot retire the legacy channel on this
  precondition alone.
- The frontend parser is switched to canonical-first with a legacy fallback and verified in a browser.
- Both owners sign a dated entry in the migration log below.

Until all six hold, the legacy rows above are the only supported content channel, and any backend cleanup that deletes them counts as a breaking change.

### Migration log

- 2026-09-21 (R149, 收端半张): all three `event: text` paths of `/ask` now share one builder
  (`text_sse_frame`), and the frame's `content` is **the cumulative answer up to that frame, not a
  delta** - the last frame equals the whole answer, so a client that replaces `msg.content` per frame
  keeps working unchanged. 🔴 Measured on the current tree: the generation leg is still invoked
  rather than streamed, so a real turn still carries exactly one `text` frame. Wiring the leg is
  R149b, whose hard preconditions are (a) a piece must carry its calling identity, otherwise planner
  and worker text merge into one cumulative string and the receiving end can only log the mismatch,
  and (b) usage must not go back to NULL (measured: the compatible leg returns usage when the
  request opts into `stream_options.include_usage`). Byte-equality of the done frame is pinned by
  `tests/test_r149_sse_text_pieces.py`; the piece branch's single `await` is `sleep(0)`.
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
    request that declares nothing therefore cannot choose its own SLO bucket, and a request that
  does declare one gets it on `POST /api/v1/ask` or a `400` on `POST /api/v1/chat` (2b). A label
  being accepted is not the same as a label being honoured, and as of R141 those two are no longer
  the same sentence: a declaration now moves real worker legs, which is why `frontend/**` now
  ships a tier selector. R32 ban was never on the control, it was on a control that changes
  nothing; the pin that forbade the selector was rewritten into four harder ones rather than
  relaxed (closed shipment list, one source of truth, wire-equal literals, diverging leg sets).

### 2b. What a declaration buys, and where the outcome is readable (2026-09-22, R141)

A label is honoured on one axis only. `app/agents/nodes.py::LANE_WORKERS` is the ceiling -- `qa`
may use `doc`, `analysis` may use `doc`, `data`, `chart`, `report` may use all four -- and the
three sets are strictly increasing, which `tests/test_r32_lane_contract.py` reddens if anyone
flattens them, because a selector whose options are equal is the fake control R32 refused to
ship. `LANE_REQUIRED_WORKERS` is the floor, so a requested `report` turn always owes an `export`
leg rather than merely being allowed one; the floor is charged to an `explicit` declaration and
never to a tier R42 inferred, so an unrequested turn pays for no leg it did not need. Nothing
else is for sale -- not the model, not the retrieval budget, not the queue policy -- and
`tests/test_r141_lane_behavior.py` names every call site a label may reach.

The outcome is readable at three outlets, all of them the same body (`TurnLane.as_dict()`), so no
downstream may convert it a second time: the response headers `x-effective-lane`, `x-lane-source`
and `x-declared-lane`; the same-named keys inside the canonical `request.started` frame data,
together with `lane`, `lane_rule`, `declared_lane`, `rules_lane`, `tier`, `allowed_workers`,
`required_workers` and `may_plan`; and the `request.started` trace payload, read back from
`GET /api/v1/traces/{trace_id}`. A header is omitted, never faked with an empty value, when the
readout has nothing to say, because a header that exists must always be believed. These keys are
invisible to `tests/test_r156_sse_event_surface_sync.py`, which scrapes literals at the emission
site and here receives a helper return value; that hole is why `tests/test_r32_lane_contract.py`
pins them from the runtime reading instead.

`lane_source` is a closed set of four: `r42` (the server picked), `explicit` (a client declaration
was honoured), `not_routed` (this turn never entered the graph -- queued, or answered from the
answer cache -- so no tier participated in it), and `resumed` (the graph is running after an
approval while the original declaration did not survive the checkpoint). The last two exist
because a lost declaration, an irrelevant declaration and an absent declaration are three
different facts; letting `r42` absorb all three puts the third state back in through the reading
panel.

`POST /api/v1/chat` refuses every declaration with `400` and the same stable code, before a
retrieval, a model call or a session row: it is one retrieval plus one model round and has no
worker legs to route. `ChatRequest.lane` exists only so that this refusal happens out loud, since
pydantic would otherwise drop an unknown field and hand the caller an answer that quietly ignored
what it asked for.

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
- Counts are aggregated by `filename` and carry no identity, and there is no per-person throttle or
  cooldown, so one reader clicking twice is two signals. Since R153 the prior speaks in ranks, not in
  score: one net acceptance is worth `0.5000` of a rank (`ACTIVITY_PRIOR_SIGNAL_GAIN = 2.0`, smoothed by
  three phantom votes, so three net acceptances saturate it), and the hard bound is `1 rank`
  (`ACTIVITY_PRIOR_MAX_SHIFT_RANKS = 1`). Measured through the ranker itself, the displacement is
  measured as 1 place at leg widths 5, 12 and 40, in both directions, and it is the same number at the
  20-acceptance ceiling: extra votes buy only precedence when two candidates want the same swap, never a
  second place. The bound is structural rather than arithmetic - a candidate takes part in at most one
  adjacent swap per round and the number of rounds is the bound, so the code that moves rows never reads
  `k`, the candidate count or `ACTIVITY_PRIOR_RANK_BASE`. For reference, in the reciprocal-rank shape the
  prior used to be added into, first and second differ by 0.00026; before R153 that is what made a single
  click on a `search(k=5)` leg worth more than the whole leg (measured and recorded in 跟进单 §78).
  What is still true today: one click can swap the top two of a short leg, and last can still reach
  second-last. Whether to additionally cap signals per person stays an owner decision.

- 判据① (the order really changes) is proven offline today: the tests drive the ranker with fabricated
  rows, not a live PostgreSQL under concurrent clicks. Registered in 跟进单 §77 as an open item.

## Overview Aggregate: `documents_ready` (2026-09-26, R284)

`GET /api/v1/dashboard/summary` is the overview page's server-side aggregate (R14-A1). The
document tile shows two numbers and the route carried only one of them until R284: how many
documents this caller may see, and - the missing column - how many of those finished parsing.
R274 had already given the frontend the reading position (`payload.documents_ready`, absence
folds to `null`, never to 0 and never to 「全部」), and it deliberately declined to count a
list length client-side, which is the silent shrink R14-A1 exists to remove. The gap was
server-side, so this is the contract for that column.

### `GET /api/v1/dashboard/summary` -> body

| Key | Type | Nullable | Counted over |
| --- | --- | --- | --- |
| `generated_for` | string | no | the principal these counts were computed for |
| `pending_approvals` | int | no | that principal's open HITL ledger rows |
| `documents` | int | no | catalog rows this principal may list |
| `documents_ready` | int | no | **those same rows**, the ones whose `parse_status` is `ready` |
| `datasets` | int | no | registered data files this principal may analyze-and-open |
| `alerts` | object `{total, unread}` | **the key is absent** | only when the alert gate allows it |

**The key is never omitted.** `alerts` is conditional on purpose - there, absence *is* the
permission answer (R14-A1). `documents_ready` is not: an absent column is a number the client
would have to invent, so the route always answers with an integer, `0` included, and never
with `null` or a numeric string. `documents_ready <= documents` holds because of the next
paragraph, not because of a check.

**One read, not a second query.** Both document columns come out of the single
`chat.list_document_catalog` call in `app/api/v1/dashboard.py::_document_counts` - that is,
out of `_classify_document_rows` -> `authorization_decision`, the same judgment
`GET /documents/catalog` answers with. Counting a field on rows already in hand is not the
R14-A1 shortcut: the total is not inferred from a delivered page. The pair is pinned in
`tests/test_r284_documents_ready_column.py`, which counts the calls (exactly one per request)
and re-derives both columns from that one return value, so two columns answering two scopes
is a failing test rather than something a reviewer has to notice.

**`ready` is 解析完成, not 可检索.** The counted value is the stored `parse_status`, whose
domain is `("pending", "parsing", "ready", "failed")` (`app/documents/catalog.py`, enforced
as `document_versions_parse_status_check` in `migrations/0006_document_ownership.sql`). Only
`ready` counts, so `parsing` and `failed` both stay on the 「N 篇还没解析完」 side - the tile
asks 「这篇读完了没有」, and a half-parsed document has not answered it. `index_status`
(`app/documents/index_policy.py`, where an unrecorded value is a first-class
`INDEX_STATUS_UNKNOWN`) is a different question - 「助理能不能检索到这篇」 - and the two are
orthogonal in code as well as in name: the upload path records `parse_status="ready"`
together with `index_status=excluded` whenever a document parsed into content the index
policy does not want (`app/api/v1/chat.py:3870-3874`, `:3997-4008`), and a document still
`parsing` is not ready however its index row reads. **Read this column as 「几篇解析完了」
and never as 「几篇能被问到」.**

**Historical rows count as unparsed - a stated understatement.** Two mechanisms, same
outcome: `app/documents/catalog.py::_normalise_parse_status` folds NULL, empty and
unrecognised values into `pending`, and `migrations/0006_document_ownership.sql:31,54` added
the column as `TEXT NOT NULL DEFAULT 'pending'`, so every row already in the table took
`pending` at migration time. A document ingested before that column landed is therefore
counted as 未解析 until something actually parses it and records `ready`, even when the file
on disk is fine. For the employee reading the tile: on a legacy corpus `documents_ready` can
be **smaller** than the number of documents that really are usable, and 「N 篇还没解析完」
may name rows nobody ever re-parsed. Two things were considered and rejected: the response
cannot carry a 「历史行」 split without a second read - normalisation has already erased the
difference by the time the endpoint sees the row - and counting NULL as ready to make the
number look better would break the one property the tile depends on, namely that
「全部已解析」 is only ever said when it is true. The bias is pessimistic in the same
direction the pending count was already allowed to be (R13: it may overstate open work,
never report a cleaner queue).

The auth gate is unchanged: `401 authentication_required` and `403 permission_denied`
bodies carry no counts, and neither document column is readable through them.


## Moving an account between departments: `PUT /api/v1/users/department` (2026-09-26, R290)

Until today an account's department could only be changed by deleting and recreating the account
(`POST /api/v1/users` is the only other writer of that column). This route is the missing writer.
It is gated server-side on `users:manage` (`ACTION_MANAGE_USERS`) and it **has no self-service
exemption** - unlike `PUT /api/v1/users/password`, which lets a caller change their own password,
this one refuses even when `body.username` equals the caller. That asymmetry is deliberate:
department is an authorization input, a password is not.

### Request body `UpdateDepartmentRequest`

- `username` *string* - required. The **target** account, not the caller.
- `department` *string | null* - optional, and absence is not the same as an empty string:
  1. **absent or `null`** - nothing is written, the response says `changed: false`. A dropped
     field must never read as "clear this person's belonging".
  2. **`""`** (whitespace-only folds to the same) - explicitly clear the belonging. PostgreSQL
     stores `NULL`, the in-memory table stores `""`, matching `POST /api/v1/users` and
     `migrations/0003_legacy_runtime_tables.sql`.
  3. **non-empty string** - trimmed, then written.

There is no dictionary of legal departments: values are free text, exactly as in `create_user`.
A typo therefore creates a brand-new empty scope rather than failing loudly - recorded in 跟进单
as an open product decision, not a defect this route fixes.

### `200`

`{"status":"ok","username":string,"department":string,"changed":boolean,"message":string}`

`department` is the effective value after the call (`""` when cleared); `changed` reports whether
this call actually moved the value.

### Errors (verbatim `detail` strings, no new wording invented)

| status | body | who can see it |
| --- | --- | --- |
| 401 | `{"detail":"authentication_required"}` | everyone |
| 403 | `{"detail":"权限不足: users:manage (permission_denied)"}` | any caller without `users:manage`, **including a caller naming themselves** |
| 404 | `{"detail":"用户不存在"}` | only a caller who already holds the gate |

The gate runs before validation and before existence lookup, so a staff member probing whether an
account exists receives 403 and learns nothing (`tests/test_r290_department_endpoint.py`).

### Audit

One `app.common.audit.record_audit` line per write, same five positional arguments and shape as
`app/api/v1/artifacts.py`: `action="users:manage"`, `resource="users:<username>"`, success as
`outcome="allowed"` / `reason="department_updated"` carrying `before_summary` and
`after_summary` `{"department": ...}`; a missing account as `outcome="failure"` /
`reason="user_not_found"`. Refusals are booked by the existing gate
(`app/common/authorization.py`), not by a second path invented here.

### What clearing a department actually does (the frontend must copy this, not guess)

Clearing is locking someone out, not widening their boundary. A non-administrator with no
department: is refused the whole retrieval path (`app/rag/filters.py` returns
`authorization_unavailable`), cannot produce artifacts (`app/storage/artifacts.py` refuses), and
fails every department-scoped resource check as `resource_scope_missing`
(`app/common/policy.py`). Administrators are unaffected (`administrator_scope`).

### Registered, not fixed (three residuals found while writing this route)

1. 🔴 **The queued-task payload carries a `Principal` snapshot.** `app/api/v1/chat.py` enqueues
   `principal.model_dump(mode="json")` and `deploy/queue_worker.py` reconstructs the Principal
   from that snapshot, so a turn enqueued *before* the move still runs with the *old* department's
   scope. Either the payload stores only `user_id` and the worker re-reads the Principal, or
   `department` joins the payload fingerprint and the entry goes stale. Measured offline:
   queue-time `市场部` vs live row `研发部` vs consumption-time scope `['市场部']`.
2. 🔴 **Session history is returned by owner only.** `GET /api/v1/sessions/{id}` filters on
   `is_owned_by` and nothing else, so answers produced under the old department (including their
   document citations) stay readable after the move. Either the session records a department
   dimension or the read-back re-checks `scope.allows`.
3. 🔴 **A second, self-writable copy of `department` exists.** `app/memory/profile.py`
   **overrides** the authoritative value from `users` with `user_profiles.department`, and
   `PUT /api/v1/profile` is self-service; `app/agents/nodes.py` then splices it into the model
   context. So after an administrator moves someone, `GET /profile` and the prompt still report the
   old department - and an employee can self-report an arbitrary department string into their own
   prompt. `user_profiles` is not an authorization input (`Principal` reads `users`), which is why
   this is a labelling/prompt defect rather than a privilege escalation, and why it needs its own
   ticket.

None of the three is fixed here: the cache, session and profile layers belong to other write
domains. Verification status: the PostgreSQL branch is pinned with a fake table that recognises
exactly the one new `UPDATE`; a live-PostgreSQL run is still outstanding on this machine.

## The profile store stops carrying a department: `PUT /api/v1/profile` (2026-09-26, R296)

R290 registered this as residual 3 of `PUT /api/v1/users/department`. This section closes it; the text
of that section is left as written.

### Single source of truth

`users.department` is the only authoritative department. `Principal` is built from that row
(`app/agents/contracts.py::Principal.from_user`), and since this ticket the profile read path takes its
department from the same row: `app/memory/profile.py::get_profile` no longer selects the `department`
column of `user_profiles`, and neither the PostgreSQL leg nor the in-memory leg merges it back. Moving
someone with `PUT /api/v1/users/department` therefore shows up in `GET /api/v1/profile` and in the model
context on the next call - there is no second copy left to catch up.

### `PUT /api/v1/profile` refuses a department

`department` is read-only here. A body that **contains the key at all** - `"department": ""` included -
is refused as a whole request:

| status | body |
| --- | --- |
| 403 | `{"detail":{"code":"department_override_denied","message":"..."}}` |

Nothing is written on such a request: `position` and `preferences` are not saved either, because "accept
the field, then quietly drop it, and store the rest" is exactly how a second truth comes back with a
friendly error message. A client that serializes its whole form must stop sending the field. A body
without `department` behaves as before and returns `{"status":"ok"}`.

The code is not invented here: it is `DEPARTMENT_SELF_REPORT_DENIED` (`app/common/authorization.py`),
already carried by `tests/test_error_code_vocabulary.py::BARE_CODES_OUTSIDE_THE_ENUM` and already folded
by `frontend/src/lib/errcodes.js::LEGACY_ALIASES`. Frontend: show it with the same wording as every other
refused self-report - "the department you sent is not writable here" - not as a generic permission
failure, and no retry button (a resend of the same body is refused again).

### The prompt keeps its line

`app/agents/nodes.py::load_memory` derives the department from `users` at that moment
(`_authoritative_department`), falling back to the request's `Principal` snapshot only when the row cannot
be read. The splice itself is untouched: `compose_profile_context` still emits the `department:` line, so
closing the second truth does not remove context the answer needs.

### The legacy column: kept, no longer read, no longer written

`user_profiles.department` keeps every value already stored. This ticket deletes nothing.
`upsert_profile` dropped the column from the `INSERT` list and from the `ON CONFLICT DO UPDATE` set, so
saving a profile neither overwrites an old value with a new claim nor nulls it out.

Cleanup guidance for the owner (`migrations/**` is not this ticket's domain, nothing below was executed):

1. No production path reads or writes the column any more, so `ALTER TABLE user_profiles DROP COLUMN
   department` is behaviour-neutral whenever the owner decides to take it.
2. Until then the column may still hold values that contradict `users.department`. No API surfaces them,
   so anything reading the table directly - a customer SQL query, a future report - must treat `users` as
   the standard, and `user_profiles` as position and preferences only.
## Notification Inbox (2026-09-26, R299)

One inbox, three existing ledgers, no new account of work. This resource answers the question the
platform could not answer before -- *what should this particular person look at* -- and nothing
else. Every candidate is a read-time projection over a book that already exists. The only thing
`migrations/0016_notification_states.sql` stores is reader state: there is no body, department or
classification column, so the inbox cannot grow into a second to-do ledger even by accident.

### Endpoints

| method | path | who |
| --- | --- | --- |
| GET | `/api/v1/notifications` | any authenticated principal; each caller sees only what their own scope admits |
| POST | `/api/v1/notifications/read` | the same, and only for ids the caller can address |
| POST | `/api/v1/notifications/dismiss` | the same, and only for ids the caller can address |

### The three sources and the key each id is built from

`id` is `<source_type>:<source_record_id>`, derived from a key that already exists in the source
book -- never a number generated here -- so the same candidate spells the same string across
processes, across restarts and across "nobody has read it yet".

| source_type | the existing book that is read | `source_record_id` | in the inbox while |
| --- | --- | --- | --- |
| `approval` | `app/storage/pending_approvals.py::open_items(owner_user_id=<caller>)`, the same read `GET /api/v1/hitl/pending` performs | that ledger's `session_id` | the row is still `awaiting` and inside its action window |
| `alert` | `app/api/v1/alerts.py::list_alerts(request)`, called directly so the resource gate, the row predicate and the row projection each keep exactly one definition | that ledger's `id` | `status` is not in `ALERT_TERMINAL_STATUSES` |
| `document` | `app/api/v1/chat.py::list_document_catalog(request)`, called directly so visibility stays `authorization_decision`'s answer | `<filename>#v<version>` | `index_status == "indexed"` |

A fourth source type is refused by `parse_notification_id`, and there would be nothing for it to
write into: a candidate that no book would still list is simply not addressable.

### Visibility: no second filter is written here

Approval ownership is the ledger's own `owner_user_id`; alert row ownership is
`alerts.alert_row_visible` / `alert_row_scope_sql`; document visibility is
`app/common/policy.py::authorization_decision` behind the catalog route. Consequences that are
pinned by `tests/test_r299_notification_inbox.py`: another person's approval todo is invisible and
not dismissible; a same-department staff account does not see a level-2 document notification that
a manager sees; another department's alert does not cross over even between two managers.
Administrators are unconstrained **only** on the two books that already say so (alerts, documents)
-- the HITL ledger stays owner-scoped for an administrator too.

When a source is refused outright (a `staff` caller holds no `alerts:manage`), that source answers
`included: false` with the ledger's own `reason_code` (`permission_denied`) -- never `0`, which
would render as "your department had a quiet day" (the standing rule from the R188 overview tile).

### `GET /api/v1/notifications` -- request and response

Query parameters: `state` in `unread | read | all` (default `all`; `dismissed` is not a filter
value, it is 422), `limit` 1..100 (default 20), `offset` >= 0. Rows are ordered newest first by
`(created_at, id)`, where `created_at` is the source's own recorded time -- nothing here is
re-timestamped.

```json
{
  "notifications": [
    {"id": "alert:701", "source_type": "alert", "source_id": "701", "title": "...",
     "detail": "...", "created_at": "2026-09-26T09:00:00+08:00", "state": "unread",
     "reference": {"alert_id": 701}}
  ],
  "state": "all", "limit": 20, "offset": 0,
  "returned": 3, "has_more": false,
  "total": 12, "unread_total": 9, "unread_returned": 3,
  "is_exact": true,
  "sources": {
    "approval": {"included": true, "reason_code": "ok", "candidates": 3, "scanned": 3, "truncated": false},
    "alert": {"included": false, "reason_code": "permission_denied", "candidates": 0, "scanned": 0, "truncated": false},
    "document": {"included": true, "reason_code": "ok", "candidates": 0, "scanned": 0, "truncated": false}
  }
}
```

**The four counts, and which base each one is read against** (the R278 lesson, spelled out):

| field | base | meaning |
| --- | --- | --- |
| `returned` | **this page** | how many rows this response carries |
| `unread_returned` | **this page** | how many of those rows are unread |
| `total` | **the whole set** | every candidate this caller can see, unread and read alike, not dismissed |
| `unread_total` | **the whole set** | how many of those have no reader row yet |

`total` and `unread_total` are page-independent and `state`-independent: paging to the last two
rows does not make the set smaller, and filtering by `unread` does not change `total`. "Whole set"
means the whole set **inside the candidate window**, not the whole table: each source contributes
at most `SOURCE_WINDOW` (50) candidates and the alert leg carries its own `LIMIT 100`, so when any
source was trimmed, `is_exact` is `false` and both totals are honest lower bounds rather than a
claim of completeness. `scanned` says how many rows that source actually looked at.

### Lifecycle: two writable states, one direction

`unread` is not a state that is ever written -- it is the absence of a row, which is why reading
the list leaves the table untouched. `read` and `dismissed` are the only two values
`notification_states.state` takes (the CHECK in 0016 and `contracts.NOTIFICATION_STATES` are kept
equal by `tests/test_r299_notification_states.py`). Advancement is one-way: `read` may become
`dismissed`, `dismissed` never returns to `read`, because a page flip must not reopen something a
reader already refused to look at. A dismissed row leaves the list **and** both totals; a read row
stays in the list and leaves only `unread_total`.

Writes take `{"ids": [<notification id>, ...]}` and nothing else -- 1 to 50 ids after de-duplication,
`extra="forbid"`, so `recipient`, `username` and `department` in the body are each a 422. The
recipient is always taken from the session, never from the client: this table's entire meaning is
"who actually saw what".

```json
{"action": "dismiss", "requested": 2, "changed": 1,
 "results": [{"id": "alert:701", "state": "dismissed", "changed": true, "reason": "applied"},
             {"id": "approval:sess-x", "state": null, "changed": false,
              "reason": "notification_not_addressable"}]}
```

Both actions are idempotent, and the receipt says so rather than merely not failing: the second
`dismiss` of the same id answers the same `state` with `changed: false`.

### Errors (verbatim `detail` strings, no new wording invented)

| status | body | who can see it |
| --- | --- | --- |
| 401 | `{"detail":"authentication_required"}` | anonymous callers, on all three routes |
| 422 | `{"detail":"validation_error"}` | out-of-range `state`/`limit`/`offset`, unparseable body, unregistered field, empty or oversized `ids`, malformed id |
| 503 | `{"detail":"storage_unavailable"}` | 0016 has not been applied; the whole answer refuses rather than reporting "nothing unread" |

There is deliberately no 403 and no 404 on this resource. Someone else's notification and a
notification that never existed answer the same way -- `200` with `state: null` and
`reason: "notification_not_addressable"`, `changed: false`, no row written -- because a status-code
difference between those two would be an existence oracle over other people's ids (the same stance
`GET /api/v1/alerts/{id}` takes with its single 404).

### Audit

Every refused write books one line through the existing `app.common.audit.record_audit` path:
`action="resource:view"`, `outcome="denied"`, `resource=<notification id>`,
`reason="notification_not_addressable"`. Nothing is written for a successful state change -- the
state row is itself the record of that act, and a second copy of it in a journal is exactly the
parallel book this ticket forbids.

### Registered, not fixed

1. **There is no event stream in this slice.** The document rows are derived from catalog state --
   "the set that is retrievable for you right now" -- not from a timestamped "indexing finished"
   event. On first boot of this feature a long-indexed document therefore surfaces as one unread
   row per person who can see it, and `created_at` is the version row's time, not the moment the
   index job completed. A real `notification` event table would be a fourth ledger; it is out of
   scope here by the ticket's own wording.
2. **Approval candidates are not re-verified against the graph.** `GET /api/v1/hitl/pending` does
   not re-run `check_interrupt` per row either, and this read deliberately matches that stance. A
   session resolved out of band closes its ledger row, so the next read agrees; the row does not
   linger in the inbox, because the inbox never kept a copy.
3. **No delegate, no administrator override.** Nobody can mark someone else's inbox, and there is
   no "unread for my department" roll-up. Both would require answering on behalf of a person who
   has not looked.

Verification status: pinned offline. The PostgreSQL leg of `notification_states` is exercised with
a fake connection that answers `to_regclass` with NULL and with the same migration runner the
first-boot family uses; a live-PostgreSQL run is still outstanding on this machine.

## Notification Inbox: the four faces R303 turned into pins (2026-09-26, R303)

Follow-up to `## Notification Inbox (2026-09-26, R299)` above. That section stays the authority for
everything it already says, and nothing in it is reworded here. R303 took the four faces R299
declared "implemented, nobody exercised them" and made each one checkable; this page is where each
claim now lives, so a client reader never has to open `app/notifications/sources.py` to learn what
a field means.

### `truncated` has two independent triggers, and each half is named

`sources.<source>.truncated` is written by an `or` with two different reasons behind it. Each half
now has a dedicated case that seeds the *other* half out of the picture, so neither claim rests on
reading the code:

| half | fires when | the bound it is measured against |
| --- | --- | --- |
| candidate window | this source offered more than `SOURCE_WINDOW` (50) candidates, so `_sorted_window` dropped some | `app/notifications/sources.py::SOURCE_WINDOW` |
| alert leg page | `GET /api/v1/alerts` handed back `ALERT_LEG_PAGE` (100) rows, so the ledger's own `LIMIT 100` may have swallowed more than this read ever saw | `app/notifications/sources.py::ALERT_LEG_PAGE` |

The two halves stay distinguishable from the receipt alone: `candidates` is how many items survived
that source's own terminal-status filter, `scanned` is how many rows the source actually looked at,
and `truncated` says at least one of the two limits bit. A projection reading `candidates: 1,
scanned: 100, truncated: true` was trimmed by the ledger page while `included: true` and
`reason_code: "ok"` still hold; one reading `candidates: 50, scanned: 55, truncated: true` was
trimmed by the window. Both cases, plus a third where the two halves fire together, are in
`tests/test_r303_notification_pins.py`; its counter-evidence deletes the leg-page half and shows
that pin going red while the window pin stays green.

### One refused id does not roll back the batch -- and must not be rewritten that way

`POST /api/v1/notifications/read` and `POST /api/v1/notifications/dismiss` answer per id, not per
batch. An id the caller cannot address is refused inside its own `results[]` element -- `state:
null`, `changed: false`, `reason: "notification_not_addressable"` -- while every other id in the same
call is still written, still counted in `changed`, and the status is still `200`. This is a contract
and not an accident of the loop: turning it into an all-or-nothing transaction would let one
somebody-else's id throw away the reader's other actions, and would make `changed: false` ambiguous
between "already dismissed" and "never attempted". `tests/test_r303_notification_pins.py` pins it
for both actions and three id orderings (a refusal first, middle and last must give the same
verdicts), and its counter-evidence installs exactly that batch gate to show the pin red.

### The full-window read is timed offline -- that number is not a production reading

`tests/test_r303_notification_pins.py` seeds all three sources to their caps (55 parked approvals,
100 alert rows, 55 indexed documents, so `total: 150`), pages with `limit=100`, and times one read
through `TestClient` with no PostgreSQL, no vector-store traffic and no host model. Nine runs of that
case on this machine landed between 8.9 ms and 12.4 ms. That is a **test-double measurement taken
under a pin, not a real-machine reading**: it is not a latency target, not an SLO row, and not
comparable with `## Three-Tier SLO Contract`, which requires real deployment samples. What it does
establish is the shape of the cost: pagination merges the three books in memory and pages over the
merged list with an `offset` cursor only -- there is no keyset cursor -- so one read costs on the
order of 3 x `SOURCE_WINDOW` candidates plus one lifecycle-row read, and that bound is a design
decision, not an accident.

### The PostgreSQL leg of `apply_state` is now executed by a test

The `INSERT ... ON CONFLICT (notification_id, recipient) DO UPDATE` statement is asserted
statement-for-statement against a fake connection that records SQL text and bound parameters, with
the conflict target checked against the `notification_states_reader_key` UNIQUE columns in
`migrations/0016_notification_states.sql` rather than a hand-copied list. `tests/test_r303_pg_upsert_leg.py`
also pins that the one-way lifecycle rule has exactly one implementation: `advance_state` in
`app/notifications/contracts.py`. The storage leg may not carry its own copy of the ordering -- a
second rule there is precisely the parallel-book shape this resource exists to avoid -- so the
stored value is asserted to be whatever `advance_state` returned, and an AST pin checks that `final`
is assigned once inside `apply_state` and comes from that call.

Concurrency is claimed only as far as the row lock reaches. With a `dismissed` row already
committed, two threads hammering `read` and `dismissed` at the same `(notification_id, recipient)`
never revive it and never issue a write at all. On a pair nobody has ever written, both legs can
read "no row" before either writes; the unique key plus the UPSERT then guarantee exactly one legal
row, not which of the two words it holds. That window is the one `app/notifications/states.py`
already documents in its own comment: pinned here as "one row, one legal word", deliberately not as
"the loser is discarded", because closing it would mean putting the ordering rule into SQL -- a
second book, which the whole resource exists not to be. Registered, not fixed.

The five keys of one `sources.<source>` projection, named once as a list so a client can check this
page instead of the code: `included` (did that book answer at all), `reason_code` (`ok`, or the
ledger's own refusal word), `candidates`, `scanned`, `truncated`.

Sample spread, and a superseding note on the paragraph above. Seven more runs of the same case on
the same machine gave 8.6 / 9.3 / 9.7 / 11.5 / 13.6 / 14.0 / 15.5 ms, so the honest reading across
all sixteen samples taken for this ticket is **min 8.6 ms, max 15.5 ms** -- "single-digit to
mid-teens milliseconds on a development laptop", not the 8.9--12.4 ms window quoted a few lines up.
That spread is also why the case prints its own measurement instead of asserting a bound: no upper
bound is pinned here, and a page of this contract must not leave one behind as if it were. The only
standing claim is the shape -- 3 x `SOURCE_WINDOW` candidates merged and paged in memory, an
`offset` cursor, no keyset -- plus the warning that every millisecond figure in this section is a
test-double reading, not a production one.

Write-side receipts are named the same way, because a client must not have to read
`app/api/v1/notifications.py` to parse one. A successful call carries `action` (`read` or
`dismiss`), `requested` (how many ids survive de-duplication), `changed` (how many of those
actually moved a row) and `results`, one element per id carrying `id`, `state`, `changed` and
`reason`. `reason` takes exactly two words: `applied` for an id this caller may address, and
`notification_not_addressable` for one it may not. `state: null` appears only beside a refused id
-- never beside an applied one -- and both actions answer through the same four fields, so a reader
can tell "I just dismissed it" from "it was already dismissed" (`changed` true versus false) while
`state` stays the same word.

Recorded tally for the sentence above, so nobody has to guess which runs it covers: nineteen
recorded readings of that case on this machine, minimum 8.6 ms, maximum 15.5 ms, median 10.2 ms.
Executions whose reading was not written down are not counted, and the case prints its own reading
on every run -- that printed line, not any number quoted here, is what a later reader should trust.

Handoff sample, and the last timing run of this ticket: 11.5 ms, inside the range above, taken with
the same seed set on the same machine. Twenty recorded readings in total; nothing after this line is
a number anyone should quote.
