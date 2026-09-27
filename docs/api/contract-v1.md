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

`POST /api/v1/upload` accepts exactly the extensions that the parser can read. As of S5 this
was four - `pdf`, `txt`, `md`, `docx` - and `.xlsx`/`.csv` had been taken off the knowledge-base
whitelist because they passed the header check, were written to storage, and surfaced as an
HTTP 500. **R306 (2026-09-26) put both back and made the promise behind it true**:
`app/rag/loader.py::load_document` dispatches `.xlsx` and `.csv` to `app/rag/spreadsheets.py`,
so an accepted upload is now also a readable upload. Six extensions today: `pdf`, `txt`, `md`,
`docx`, `xlsx`, `csv`; the closed set is pinned by `tests/test_r306_spreadsheets_in_the_upload_path.py`.
`.xls` stays out on purpose - openpyxl cannot read the legacy binary format and `xlrd` is not a
direct dependency - so it is refused as `unsupported_file` before any byte is written. A stored
spreadsheet is also still a dataset: `POST /api/v1/upload-excel` is unchanged and keeps its own
filename, permission and conflict rules (see `Dataset File Delivery`); the two routes share the
extension and nothing else. A body that passes the header check but cannot be parsed answers with
the pre-existing `500` `document_parse_failed` and keeps its file and catalog row, exactly as a
broken `.docx` does - no new error code was introduced for spreadsheets. An unsupported extension
is rejected before any byte is written, as `400` whose `detail` is exactly the stable code
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

## R290's residuals 1 and 2 are closed: identity at consumption, and session read-back (2026-09-26, R311)

R290 registered three residuals while writing `PUT /api/v1/users/department`. R296 closed the third
(the profile store stops carrying a department). This section closes the first two. The text of that
section is left exactly as it was written, including its "None of the three is fixed here" sentence,
which describes R290's own write set and stays true.

1. **The queued-task payload no longer decides scope from a `Principal` snapshot.** Closed by R294
   (merged `70fef37`): `deploy/queue_worker.py` and `app/agents/tools.py` take the identity at
   consumption time, so a turn enqueued before a department move runs with the department the row
   holds now, never the one it was enqueued with. The enqueue-time payload survives only as a
   reference plus drift evidence, which is the shape R290 asked for.
2. **Session history is no longer returned by owner alone.** Closed by R295 (merged `d194d99`):
   `GET /api/v1/sessions/{id}` re-runs `scope.allows` on read-back instead of trusting `is_owned_by`
   and a session/thread id as a credential. Turns produced under a department the caller has left are
   withheld, and the response says how many: `withheld_turns` sits beside `session` and `messages`.

Neither closure was made inside R290's route, and neither reopens it. Verification status: both are
pinned offline on this machine; the live-PostgreSQL run still outstanding here belongs to R59/R60, not
to these two residuals.

## The upload receipt carries its own page-source reading (2026-09-26, R301)

`POST /api/v1/upload` answers one more field, `pdf_extraction`. It is the reading of *this
one upload* -- what the PDF extractor saw, page by page. Nothing in it is invented:
`app/rag/loader.py` has assembled that book since R298 and R304 (`DocumentExtraction`,
carrying `pdf` and `tables`), and until now nothing outside the tests could reach it. A
customer who uploaded a scan could not see "12 pages, 3 of them scanned, page 7 never got
OCR'd" anywhere on screen, because both loader exits returned only the text string.

The public exit added for this is `extract_document_with_reports(file_path) ->
DocumentExtraction` -- `load_document`'s sibling with the books attached. `load_document`
keeps its signature and its behaviour word for word: `app/documents/preview.py` is a caller
that wants only the text, and it is untouched.

| field | where it comes from |
| --- | --- |
| `page_count` | `PdfExtractionReport.page_count` |
| `scanned_pages` / `scanned_page_numbers` | `.scanned_pages` / `.scanned_page_numbers` |
| `ocr_attempted` | `.ocr_attempted` -- did the OCR channel get opened at all this run |
| `ocr_available` | `.ocr_available` -- was the engine usable at that moment |
| `ocr_engine` / `ocr_dpi` | `.ocr_engine` / `.ocr_dpi` |
| `source_counts` | `.source_counts`, the loader's own five words (`text-layer`, `ocr`,
  `ocr-empty`, `ocr-degraded`, `blank`) -- no second vocabulary on the wire |
| `ocr_degraded_page_numbers` | the pages whose source is `ocr-degraded`, i.e. "which pages
  did not run", as page numbers |
| `degradation_note` | `.degradation_sentence`, verbatim |

Five rules the field obeys, each one pinned by `tests/test_r301_upload_readout.py`:

1. **Readings, not conclusions.** `ocr-degraded` means "this page's OCR did not run". It
   does not mean "this page has nothing on it", and the receipt never says or implies the
   second sentence while reporting the first. A page that was OCR'd and genuinely held no
   text stays `ocr-empty`; a page with neither text layer nor image object stays `blank`.
   Three facts, three words, not one word with three meanings.
2. **One ruler for the degradation sentence.** `degradation_note` is
   `report.degradation_sentence` with no editing here, which is what keeps R298's split
   visible on the wire: `ocr_available: false` opens with
   `ocr.ENGINE_UNAVAILABLE_NOTE` ("本地 OCR 引擎不可用，扫描页未识别文字"), while an engine
   that *was* available and lost one page opens with
   `loader.DEGRADATION_NOTE_PREFIX` ("扫描页 OCR 降级"). "Install the engine" and "this one
   page failed" stay two different answers, and a client does not have to parse the tail of
   the sentence to tell them apart.
3. **Not a PDF, no reading.** The key is present on all four outcomes of the endpoint
   (indexed, excluded by the R49 policy, duplicate not accepted, refused but kept) and its
   value is `null` for `.txt`, `.md`, `.doc` and `.docx`. An empty object is expressly not
   allowed: `{}` renders as "we looked, there was nothing", which is a claim about the
   document instead of a reading of it. `.docx` has a table book and still answers `null`
   here, because this field is about pages and only PDFs have a page book.
4. **Nothing is persisted, and there is no migration.** This is a reading of one upload, not
   a ledger over the corpus: the catalog row does not carry it, no version column holds it,
   and no file under `migrations/` mentions it. Keeping it across restarts would need a
   migration, which is a separate ticket and needs the owner. Until that exists, "what did
   this upload report" is answered by the upload response and by the WARNING log R298 already
   writes -- not by the document list.
5. **No server paths leave the endpoint.** `PdfExtractionReport.file_path` and
   `DocumentExtraction.file_path` are absolute paths on the customer's machine, and this
   field moves none of them. The only names a client sees are the `filename` they uploaded
   with and the basename `stored_name` R49 already returns.

The cost note, because it shaped the wiring: for a PDF the endpoint calls the with-books exit
*instead of* `load_document`, never in addition to it. Fetching this reading by parsing the
file twice would run R298's OCR a second time on every scanned upload -- the measured
per-page CPU cost in R298's own notes -- on the one machine whose purpose is to be the
customer's only copy. `test_one_pdf_is_parsed_exactly_once` pins the count, including that
the OCR engine is called once per scanned page and not twice.

Registered, not fixed: nothing under `frontend/**` renders this field yet -- that tree has
three tickets in flight and is outside this write set. The reading is on the wire today; the
「扫描页 N/M」 line in the upload panel is the next hop and needs only the fields above.

## Dataset rows name their owner (2026-09-26, R310)

V2 lists "every resource has a stable ID, an owner and a lifecycle" and "documents, data, reports and
alerts are isolated at resource level". The document catalogue has named an owner for a long time; the
dataset list has not, so an employee looking at the data panel could never tell who uploaded a table.
R310 closes that gap and nothing else: one field on one row, no new lookup, no second permission chain.

### `GET /api/v1/data-files` -> `files[].owner_id`

| key | type | presence | meaning |
| --- | --- | --- | --- |
| `owner_id` | string / null | always | the account that uploaded the table, or `null` when no owner is on record |

One row as it arrives now (`owner_id` sits next to `filename`, in both shapes of a row; read the key,
not its index):

```json
{
  "filename": "consolidated.csv",
  "owner_id": "u-17",
  "size": 20480,
  "size_label": "20.0 KB",
  "modified_at": "2026-09-26T19:39:03+08:00",
  "extension": ".csv",
  "dataset_id": "0f0c1c0a5b1e4f0d9a6c7e2b1d3c4a5f",
  "version_id": "0f0c1c0a5b1e4f0d9a6c7e2b1d3c4a5f:v2",
  "classification": "internal"
}
```

### Where the value comes from, and what `null` means

- The value is `DatasetRecord.owner_id` (`app/storage/datasets.py:121`) of the row the route already
  holds. It opens no second query: `list_data_files` performs exactly one
  `dataset_registry.get_active_by_filename` per candidate file on disk, before and after this ticket.
  `tests/test_r310_owner_lookup_cost.py` counts both sides on one fixture and reports them equal
  30 lookups and 20 policy calls on each side: five accounts plus the request-less call, over
  five files each.
- `owner_id` is a login username -- the same identity the document row names, and the same one the
  policy judges ownership with. It is never a password, a token or a server path.
- **Unowned answers `null`.** The rule is taken verbatim from the document catalogue
  (`app/documents/catalog.py:236`, whose predicate `_is_unowned` treats `None` and whitespace-only as
  no owner): an unowned row answers `null` -- not `""`, not `未分配`. There is no second spelling of
  "nobody owns this" in this API. The equality is machine-checked against the document layer's own
  predicate over a corpus of values, so neither surface may drift alone
  (`tests/test_r310_dataset_row_owner.py::test_the_unowned_rule_is_the_document_rule_on_the_same_corpus`).
  The two surfaces restate the predicate rather than share an import edge, on purpose: a router must
  not grow an import into the document layer for one field, and the ratchet that keeps the import face
  of `app/api/v1/data.py` at its `9344028` baseline is
  `tests/test_r310_dataset_row_owner.py::test_data_py_import_face_stays_the_baseline_set`.
- A row the registry never heard of answers `null` as well, and it still carries the key. That case is
  reachable only when the route runs without an HTTP request (in-process, as
  `tests/test_data_file_catalog.py` calls it): an authenticated request has always skipped unregistered
  files before reaching the row builder, and R310 did not change that. Presence of the key matters
  because "nobody is on record for this file" and "this surface does not speak about owners" are two
  different answers.

### Correspondence with the prose already in this document

The body above this section is byte-frozen for R310: no line was edited and no table in the middle was
touched. Two consequences are therefore registered here instead of rewritten there.

1. "Dataset File Delivery" states that `GET /api/v1/data-files` "returns only registered active
   datasets that pass `resource:view`, including `dataset_id`, `version_id`, and classification". That
   sentence is still true. `owner_id` is additive to those same rows and to nothing else: visibility is
   still judged by the one pre-existing `authorization_decision(..., action=resource:view,
   require_resource_scope=True)` gate, so a caller sees exactly the rows it saw before -- each of them
   now with an owner. Refused datasets stay behind `restricted` (`restricted -> the one shared
   projection`), still unnamed, and the owner of a refused row never travels.
2. "Dataset Row-Level Visibility" cites the construction site as `app/api/v1/data.py:240-249`. This
   ticket inserted 20 lines above and inside that text (19 for the owner reader and its separators,
   at `app/api/v1/data.py:66-84`, plus the one `owner_id` line at `app/api/v1/data.py:242`), so the
   cited block now reads `app/api/v1/data.py:260-269` and the row builder reads
   `app/api/v1/data.py:239-257`. That citation is a line-number note, not a contract: the
   shape it points at is unchanged, and it is pinned off the AST by
   `tests/test_r186_row_scope_contract.py`, which stayed green.

### Pins

- `tests/test_r310_dataset_row_owner.py` (9): every row carries the owner the registry already holds;
  an unregistered row carries the key and answers `null`; unowned is `null` and never `""`; the unowned
  rule is the document rule on the same corpus; the visible set equals what the existing policy
  computes for every account; only the login name travels (no foreign owner, no body, no path); the
  row's key list is the one documented here; and the field arrives through the real route table and
  JSON serialization, not only through a direct coroutine call.
- `tests/test_r310_owner_lookup_cost.py` (7): the before/after reconciliation, run through the shadow
  root with the assignment line physically removed from a copy of the source (so "before" is the
  `9344028` shape, not a recollection) -- per-account `len(files)`, filename lists and `restricted`
  tallies equal, lookup and decision counts equal -- plus four counter-evidence knives: (a) dropping
  the assignment reddens the every-row-has-an-owner pin; (b) answering `""` for an unowned row reddens
  the `null` pin; (c) widening the filter so refused rows arrive with owners reddens the row-set pin,
  the leak pin and the row-count reconciliation; (d) giving the field only to registered rows reddens
  the `record is None` pin (the stray row loses the key) and lets the registry's raw empty string
  reach the interface for an unowned row, while the per-account row set and every call count stay
  untouched -- which is what makes (d) a different knife from (a).


## The overview page grows a period: `GET /api/v1/dashboard/trend` (2026-09-26, R332)

`GET /api/v1/dashboard/summary` answers 「现在有几篇」. The 「数据趋势」 card on that same screen asks
another question -- 「哪一期新增了几篇」 -- and no server aggregate had ever answered it: `app/api/v1/dashboard.py`
carried exactly one route, and the frontend says so out loud (`frontend/src/components/DashboardPanel.vue:12-13`
draws an empty state because nothing returned a period series, `:304` promises numbers only once such an
aggregate exists). This is that aggregate. `/summary` is not modified -- its four tiles carry R284's
accounting and several pins of their own -- so this section documents a second route beside them.

### Query parameters

| Parameter | Domain | Default | Refused as |
| --- | --- | --- | --- |
| `period` | `month` \| `week` | `month` | `422 validation_error` |
| `buckets` | integer `1..60` | `12` | `422 validation_error` |

`422 validation_error` is the pre-existing rejection for a bad filter value and an out-of-range page limit
alike (`app/api/v1/notifications.py::_clean_state_filter`, `::_clean_page`). **No error code is opened by this
route**: a new bare `detail` would have to be ratified in `## REST Error Envelope` above and in
`tests/test_error_code_vocabulary.py::BARE_CODES_OUTSIDE_THE_ENUM` in the same change, and
`tests/test_r332_dashboard_trend.py::test_the_route_opens_no_error_code_outside_the_ratified_enum` keeps every
`HTTPException` literal in this module inside the enum so that debt cannot be incurred quietly. A non-numeric
`buckets` answers FastAPI's own `422`, the same face every other integer query parameter in the API gives.
The gate runs *before* parameter validation: an anonymous or unauthorised caller cannot probe which values
are legal.

### Response body

| Key | Type | Nullable | Says |
| --- | --- | --- | --- |
| `generated_for` | string | no | the principal the buckets were computed for |
| `period` | string | no | the period this series was cut with |
| `buckets` | int | no | `len(series)`, equal to the parameter |
| `time_zone` | string | no | `"Asia/Shanghai"` -- the zone every label below is cut in |
| `series` | array | no | `buckets` consecutive points, oldest first |

| Point key | Type | Nullable | Says |
| --- | --- | --- | --- |
| `bucket` | string | no | `2026-09` for a month, `2026-W40` (ISO year-week) for a week |
| `start` | date | no | the bucket's first Shanghai calendar day: the 1st, or the week's Monday |
| `documents` | int | no | catalog rows this caller may list, created in this bucket |
| `documents_ready` | int | no | those same rows, the ones whose `parse_status` is `ready` |
| `datasets` | int | no | visible data files whose registry `created_at` falls in this bucket |
| `alerts` | int | **absent without alert rights** | rows created in this bucket that the caller's row scope covers |
| `alerts_open` | int | **absent without alert rights** | of those, the rows whose `status` is `open` as of this request |

### Bucket semantics: one zone, three real columns, no clock of its own

The period is never generated here. Each bucket is cut from the stored time column of the row itself, and
the three books store three shapes, so the rule is stated once (`app/api/v1/dashboard.py::_trend_moment`):
a value carrying an offset is *converted*, a value without one is *read as Shanghai wall time*.

- `document_versions.created_at` -- `TEXT`, written with an explicit `+08:00` (`app/documents/catalog.py:580`).
- `alerts.created_at` -- `TEXT` holding `(NOW() AT TIME ZONE 'Asia/Shanghai')::text` (`app/api/v1/alerts.py:122`,
  `migrations/0003_legacy_runtime_tables.sql:9`): Shanghai wall time, offset stripped by the cast. The offline
  ledger appends `datetime.now().isoformat()` (`alerts.py:825`), naive for the same reason.
- `datasets.created_at` -- `TIMESTAMPTZ` (`migrations/0002_execution_data_lineage.sql:16`) written from
  `_utc_now_text()` (`app/storage/datasets.py:56`), so it is always an instant with an offset. Treating it as
  local would shift it eight hours: a table registered at `2026-08-31T16:30+00:00` *is*
  `2026-09-01T00:30+08:00` and belongs in the September bucket, and
  `test_a_month_edge_moment_is_bucketed_by_shanghai_wall_time` is the knife that keeps it there.

The zone is `Asia/Shanghai`, declared in the body as `time_zone` and pinned by the tests. It is the same
fixed +08:00 offset the rest of the server already keeps (`app/common/auth.py:25`, `catalog.py:15`) and the
same wall the alert table stamps itself from; China has no daylight saving, the conclusion
`alerts.py:449` already records beside the disposal clock, so a boundary cannot slide by an hour.

**No file mtime is consulted.** `data.list_data_files` answers `modified_at` off `path.stat()`
(`app/api/v1/data.py:239-248`); that key is not read for a period, which is why `_dataset_series` asks the
registry -- the same source the visibility check itself consulted a few lines earlier (`data.py:212`).
`test_the_period_is_not_read_from_the_filesystem_mtime` pins it by giving two datasets one shared mtime in a
third month and requiring that month to stay empty. One inheritance is stated rather than hidden: for a
document row whose `created_at` was never recorded, `catalog.py:386-387` substitutes the file mtime into the
*row itself*, so `GET /documents/catalog` already displays that value as the upload time; this route reads
that one project-wide value and adds no second mtime path, and it cannot separate the two because the
substitution happens before the row reaches this module.

### The two faces of nothing

- **An empty period answers `0`.** Nothing new was created in that bucket, which is a fact the server
  states; `series` is consecutive, so a client never has to infer which periods were omitted.
- **A book that cannot be read answers `503 storage_unavailable` for the whole response.** Three triggers,
  all of them a row with no accountable period: `created_at` empty, `created_at` unparseable, or a file
  `list_data_files` reported visible that the registry no longer carries. There is no partial series, no
  shortened `series`, no `0` standing in. `503 storage_unavailable` is this module's existing face for "a
  book cannot be accounted for" (`_pending_count`), so no code is added. The reason is arithmetic, not taste:
  a row quietly dropped makes the buckets total less than `/summary` reports for the same caller and the same
  scope -- one question, two answers -- and the client already refuses the other shortcut
  (`frontend/src/lib/dashboard.js:32`, 「不会用旧数字或 0 顶上」). Any other failure inside a read propagates
  unchanged; nothing is caught here.

**Series totals are not the tile totals.** `sum(bucket.documents)` counts only rows created inside the
window, while `/summary` counts every visible row; on a corpus older than `buckets` periods the series
sums to less. That is the window, not a lost row.

### Permission: the same legs, not a second pair

`GET /dashboard/trend` opens with the one call `/summary` opens with --
`app/api/v1/dashboard.py::dashboard_trend` runs `intelligence._authorized(request, ACTION_ANALYZE, ...)`,
which is `principal_from_request` -> `authorization_decision` -> audit -> `401 authentication_required` /
`403 <reason code>`, and then sets `NO_STORE_HEADERS` for the same reason `/summary` does: every bucket is
computed inside the caller's visible range, so a stored 200 is another department's company. Documents come
out of `chat.list_document_catalog` (the `_classify_document_rows` -> `authorization_decision` read that
`GET /documents/catalog` answers with), datasets out of `data.list_data_files`, and alerts out of the two
layers `GET /alerts` uses -- `_require_alert_management` and then `alert_row_scope_sql` against PostgreSQL or
`alert_row_visible` offline. None of them is restated in this module.

**A caller without alert rights gets no `alerts` and no `alerts_open` in any bucket** -- the keys are absent,
as on `/summary`. A `0` would be the alert ledger read through a route that is not `GET /alerts`, reachable
with one `ACTION_ANALYZE` call, i.e. request R1 reopened; and passing the resource gate is only the first
layer, since a finance manager's buckets must not carry the HR department's alarms (R188).

### `documents_ready` keeps R284's stated bias

`documents_ready` is counted off the same rows and the same `ready` literal as the summary column, so the
「Historical rows count as unparsed - a stated understatement」 paragraph under
`## Overview Aggregate: documents_ready (2026-09-26, R284)` above applies to every bucket unchanged: a
document whose `parse_status` the migration defaulted to `pending` is 「还没解析完」 here too. This route
restates the bias, it does not revise it, and no bucket is permitted a friendlier reading of the same row
than the tile beside it gets.

### Pins

`tests/test_r332_dashboard_trend.py` (26): the route is published read-only and no-store; the gate is that
one `ACTION_ANALYZE` call (spied), with `401`/`403` refusing every bucket; a staff caller keeps documents and
datasets and loses both alert keys; row scope separates two managers and an admin; the buckets add up to
`/summary`, `/documents/catalog` and `/data-files` for the same caller; the window is consecutive and ends on
the current period; a quiet period is a stated `0` while the other eleven stay present; three unreadable-row
triggers plus the vanished-registry-row and the propagating read each refuse the whole response; the month
edge is bucketed by Shanghai wall time from both directions (UTC-offset instants and naive column text);
week buckets start on a Monday; the filesystem mtime is pinned out; `documents_ready` agrees with the tile;
both illegal parameters answer the pre-existing `422 validation_error` behind the gate; and every
`HTTPException` literal in the module stays inside the ratified enum.

## The data whitelist admits only extensions whose engine imports on this machine (2026-09-26, R336)

`app/api/v1/data.py` advertised `{".xlsx", ".xls", ".csv"}` while the leg that opens the file chose
`engine = "openpyxl" if ext == ".xlsx" else "xlrd"`. `xlrd` is in neither `pyproject.toml` (only
`openpyxl`, `:29`) nor this machine's environment -- read live, `importlib.util.find_spec("xlrd")` ->
`None`. So a customer uploading a real 97-2003 workbook met an unhandled exception, not an
instruction: `_fill_merged_cells` let openpyxl raise `InvalidFileException` first, with pandas'
`ImportError` waiting behind it, and the upload route's `except Exception` unlinked the file and
re-raised -- an HTTP 500. V2's line for a complex file is 「功能入口可用」: 明确拒绝 is 可用, a silent
explosion is not. 总控 ruled this ticket takes the honest-refusal branch -- no new dependency (taking
`xlrd` means a dependency change, a rebuilt image and a real `.xls` sample to verify, all owner-side
windows), and 「要不要真支持 2003 老格式」 stays on the owner's pending list.

### One table decides what is admitted and what reads it

| extension | admitted | engine on this machine | answer today |
| --- | --- | --- | --- |
| `.csv` | yes | `None`: pandas' built-in CSV channel | parsed, profiled |
| `.xlsx` | yes | `openpyxl`, importable here | parsed, profiled |
| `.xls` | no | would need `xlrd`, which is not installed | `400` + the sentence below |
| any other suffix | no | not declared | `400` + the generic sentence |

`app/tools/excel.py::DATA_READ_ENGINES` is the single source: adding a row *is* admitting an
extension, and the row must name the module that reads it. `DATA_FILE_EXTENSIONS` is now derived
(`accepted_data_file_extensions()`) instead of being a second hand-copied set, and `load_excel` picks
its branch from the same table (`engine_for(ext) is None` -> the CSV channel) instead of restating
`ext == ".csv"`. Formats customers will still hand us and this platform will not read live in
`REFUSED_DATA_FILE_READS`; the two tables are disjoint by pin, so no format can be both advertised
and refused.

### `POST /api/v1/upload-excel` -> `400` with a stable code and a next step, before any byte is written

```json
{
  "detail": {
    "code": "unsupported_file",
    "message": "「报销明细.xls」是 .xls 老格式，本系统不读它。请在 Excel 或 WPS 里打开它，选「另存为」，把保存类型改成「Excel 工作表 (*.xlsx)」或「CSV (逗号分隔) (*.csv)」，再上传另存出来的那一份。文件名和表格里的内容都不用改。"
  }
}
```

- **Zero new error codes.** `unsupported_file` is already a member of
  `app/agents/contracts.py::ErrorEnvelope.code` and is what `app/api/v1/chat.py::upload_document`
  answers on its upload gate today, so `tests/test_error_code_vocabulary.py` and
  `tests/test_r142_error_code_table_sync.py` move nothing (both green: 41 passed).
- The route does not retype the code: the detail's `code` is `exc.code` carried from
  `UnsupportedDataFile.code`, and a pin reddens if a code name is ever written as a literal there.
- **400, not 500 and not 415.** A format refusal is a product answer -- neither a fault nor a
  transport problem. It happens before `DATA_DIR` is touched, so an unreadable format no longer lands
  on disk and never reaches `load_excel`.
- `GET /api/v1/data-files/{filename}/preview` asks the same one place, so a legacy `.xls` row already
  in the dataset registry answers with this 400 instead of the old `500 dataset_preview_failed` --
  that shape was a refusal wearing a fault's clothes.

### Three kinds of "cannot read", three different sentences

1. `.xls`, explicitly not done: named as such, and it says which menu item to click.
2. a suffix nobody declared: the sentence lists the accepted extensions *derived from the table*, so
   the promise and the list cannot drift apart.
3. declared here but not installed here: this one is the server's fault and says so, names the
   missing module, and still gives the employee a step that works today (「另存为 *.csv」).

### What the employee sees on screen

`unsupported_file` is a known code, so under the R281 rule in `frontend/src/lib/errcodes.js` the
visible human slot carries that dictionary's own sentence and this backend sentence arrives as
`rawMessage`. The specific 「另存为 .xlsx」 step is therefore on the wire and in the 详情 area, not yet on
the line the employee reads; surfacing it is a `frontend/**` change and outside this write set.
Registered below, not fixed here.

### Falsification, run against the real source and not in a docstring

Each knife edited `app/tools/excel.py` / `app/api/v1/data.py` on disk, ran the pin file, and restored
the bytes (sha256 verified identical afterwards):

- `".xls": "xlrd"` pushed back into `DATA_READ_ENGINES` -> **9 red of 22**: the ruler names
  `[('.xls', 'xlrd')]`, the gate/table equality pin fires, the round-trip pin demands a real `.xls`
  sample, the disjointness pin fires, and the catalogue stops hiding it.
- the `.xlsx` engine misspelled -> **7 red of 22**, and the same run shows a genuine `.xlsx` on disk
  answering with sentence 3 instead of crashing. The ruler reads *this machine*, not a constant.
- the `.xls` row deleted from `REFUSED_DATA_FILE_READS` -> **exactly 2 red of 22**, both the
  named-refusal pin. The file is still refused by the generic sentence, so every other pin stays
  green: that is the 「功能没塌所以没人发现」 cell this knife exists for.
- `DATA_FILE_EXTENSIONS` written back as a hand-copied literal `{".xlsx", ".csv"}` (same content,
  wrong mechanism) -> **exactly 1 red of 22**: the AST pin requiring a derived call.

### Consequences admitted out loud

- `.xls` rows already registered are no longer listed by `GET /api/v1/data-files`: the catalogue stops
  advertising a format the read leg cannot open. Owner / `classification` / `restricted` semantics are
  untouched, and R310's and R200's pins stayed green.
- `.xlsm` used to slip in: there was no route-level suffix gate at all, so openpyxl read it, the
  registry took it, the tool leg analysed it -- while the same file stayed invisible in the catalogue,
  because the whitelist never named it. It now gets the named 400. Admitting it for real is one row in
  `DATA_READ_ENGINES` (`"openpyxl"`) plus a sample builder in the pin that walks every admitted
  extension -- an owner's call, not this ticket's.
- A `.xls` renamed to `.xlsx` still fails inside openpyxl and still surfaces as a 500: content-level
  spoof detection is a different gate than the suffix gate, and this ticket does not pretend otherwise.

### Registered, not fixed (outside this write set)

- `app/api/v1/alerts.py::_data_file_extensions` keeps a third copy of the list as a fallback literal
  `{".csv", ".xlsx", ".xls"}`, reachable only if `DATA_FILE_EXTENSIONS` were missing (it never is, so
  the literal is dead but visible). Its sweep also wraps `load_excel` in `except Exception: continue`,
  so an `.xls` left in a tenant `DATA_DIR` is skipped without a word.
- `docs/current-functionality-2026-09-10.md:289` still reads 「XLS | 代码尝试支持 | 使用 xlrd」, and
  `app/rag/spreadsheets.py:134` still cites `app/tools/excel.py:88` for a branch that no longer exists.
- Physical-line citations to `app/api/v1/data.py` moved: the file is 545 -> 576 lines (+10 above
  `:104`, +25 above `:300`, +28 above `:337`, +31 below). R310's restated anchors `:66-84` / `:242` /
  `:239-257` / `:260-269` now read `:76-94` / `:267` / `:264-282` / `:285-294`. These are line-number
  notes, not contracts; the shapes they point at are unchanged,
  `tests/test_r186_row_scope_contract.py` reads them off the AST, and
  `tests/test_r142_error_code_table_sync.py` pins that the code table anchors on symbols. The R186-era
  `:132-169` / "attached at `:319`" pair had already drifted before this ticket (R310 registered that
  once); this note only adds its own delta.

### Pins

- `tests/test_r336_read_engine_backs_the_whitelist.py` (19 tests / 22 cases): the ruler, over the union
  of both whitelist objects, with `find_spec` read by the test itself so no conclusion can be frozen
  into a constant; gate and table are one fact (AST: a derived call, not a literal set); every
  admitted extension round-trips a real file, including a merged-cell `.xlsx`; the read leg carries no
  `xlrd` string constant, no literal `engine=`, and no second `ext == "..."` branch; `.xls` is refused
  by name and the two tables are disjoint; every refusal sentence names the file, says 「另存为」, points
  at a real target format and avoids the blame jargon; the code is in the closed enum and reaches the
  wire through `exc.code`, with a 400 and a two-key detail; upload -> 400 with nothing written to disk,
  upload of `.csv` / `.xlsx` -> 200 and registered, legacy `.xls` preview -> 400 and not 500, and the
  catalogue stops listing `.xls`; plus three in-test knives over monkeypatched tables (the same four
  were also run on disk, above).
## Knowledge-Base Spreadsheets (2026-09-26, R306)

`.xlsx` and `.csv` reach the knowledge base through `POST /api/v1/upload`. The parse layer is
`app/rag/spreadsheets.py` (R305); the dispatch is one branch inside
`app/rag/loader.py::load_document`, gated by `spreadsheets.SPREADSHEET_SUFFIXES`, and the text it
hands back passes the same `sanitize_text` as every other loader exit (R130).
`extract_document_with_reports()` reaches spreadsheets through that same branch, so the two entries
return byte-identical text for one file: there is no "readable directly, unreadable through the
report channel".

### Anchor grammar

Every stored segment opens with exactly one anchor line, joined by ` · ` (`tables.ANCHOR_JOIN`,
the same joiner PDF and Word tables have used since R300):

    文件名.xlsx · Sheet「工作表名」 · 表N（i/j段） · 合并单元格K处
    文件名.csv · 表N（i/j段）

* **How the first field is computed.** It is the name the parser was handed, not necessarily the
  name the customer uploaded. `load_document()` receives the *storage* path (`uuid + suffix`), so
  unless the caller passes `display_name` the first field is that uuid name -- which is what PDF
  and Word table anchors already show, because `app/rag/tables.py` builds all three of its anchors
  from `path.name`. Passing `load_document(file_path, display_name=...)`, or the same keyword on
  `extract_document_with_reports()`, replaces the first field verbatim: cleaned once through
  `tables._cell_text`, and falling back to the storage name if the result is empty.
  Two call sites exist and today they are **deliberately asymmetric** (R306 ruling 3):
  * `POST /api/v1/upload` (`app/api/v1/chat.py:4005`) passes `inspection.display_filename`, so an
    indexed spreadsheet is anchored under the name the customer uploaded, never under its uuid.
  * `GET /api/v1/documents/{filename}/preview` (`app/documents/preview.py`) **does not** pass it.
    That `{filename}` is whatever the caller typed, and feeding it to the parser would let one
    stored file answer with a different anchor depending on who asked. A preview is therefore
    anchored by the stored (uuid) name while the indexed body is anchored by the uploaded name.
    This is a known, chosen gap, not a silent one: the two texts are not byte-identical for a
    spreadsheet, and a client that cites an anchor back to `/upload` must expect the uploaded
    spelling. Wiring the preview is a separate ticket.
  Clients must still treat the first field as a label and match on the sheet/ordinal fields.
* `Sheet「...」` exists only for `.xlsx`; a CSV is one table and has no sheet name.
* `表N` is 1-based over **emitted blocks**, not over sheets: an empty sheet takes no number, so a
  citation can never point at a `表1` that is not in the store.
* `（i/j段）` is the segment index of that table and `合并单元格K处` counts covered grid positions.
  Both are rendering metadata; neither ever carries a truncation.

### The five truncation codes

`Spreadsheet.truncated` names one code -- the first ceiling that bit -- and the per-sheet account is
in `stats()["sheets_detail"]`. Nothing is dropped silently.

| code | measured shape | ceiling | what it says |
|---|---|---|---|
| `rows:` | `rows:一月:3of6`, `rows:CSV:5000+` | `MAX_ROWS_PER_SHEET = 5_000` | materialisation stopped at the ceiling. For `.xlsx` the total is the grid the format itself claims (`ws.max_row`, header row included); a CSV is streamed and never counted to the end, so it says `+` instead of inventing a total. |
| `cols:` | `cols:一月:128of130` | `MAX_COLUMNS_PER_SHEET = 128` | the sheet is wider than the ceiling: the first 128 columns are kept, in original order, the rest are dropped. |
| `sheets:` | `sheets:2of3` | `MAX_SHEETS_PER_WORKBOOK = 200` (= `tables.MAX_TABLES_PER_DOCUMENT`) | reading stopped at sheet 2 of 3; the rest were never opened. |
| `budget:` | `budget:1:1of5` | `MAX_SPREADSHEET_CHARS = 40_000` (= `tables.MAX_TABLE_CHARS`) | the document-wide character ceiling, `<块序>:<留下>of<本可留下>` rows. The header is fitted first, then rows. A table whose header alone cannot fit is not stored at all, and says so here instead of vanishing. The ticket called this one `chars:`; `budget:` is the token the code emits. |
| `time:` | `time:0of3` | `SPREADSHEET_TIME_BUDGET_SECONDS = 12.0` (= `tables.TABLE_TIME_BUDGET_SECONDS`) | the wall-clock budget ran out before the next sheet was opened. `.xlsx` only: `load_csv()` takes no time budget, because one CSV is one pass and the row ceiling already bounds it. |

### The three fidelity rules

1. **Merged cells.** Coverage comes from `ws.merged_cells.ranges` and the value from its top-left
   cell, so a `None` is treated as covered only when a range says it is: a genuinely blank cell
   stays blank instead of inheriting its left neighbour. Same in-place expansion as
   `app/tools/excel.py::_fill_merged_cells`, and the reason `read_only=True` is not used (that mode
   exposes no `merged_cells` at all). A row that is nothing but one full-width merge renders as a
   caption line (`> 合计说明`) rather than N copies of one value.
2. **Dates and numbers.** One value, one spelling, and no locale anywhere on the rendering path:
   a `datetime` with a time -> `YYYY-MM-DD HH:MM:SS`; a pure date (which xlsx stores as midnight) ->
   `YYYY-MM-DD`; `date`/`time` -> `isoformat()`. Numbers are the stored value rendered with `str()`
   and are never rounded a second time: `100.0` arrives as `100` and `0.1+0.2` arrives as `0.3`
   because openpyxl's write-side `safe_string` (`"%.16g"`) already decided that. Re-formatting on
   the read side would be a second drift on top of the first.
3. **Column order.** Columns keep their original left-to-right order through trimming, blank-row
   removal and empty-column removal. `columns_total - columns_kept` is exactly what the ceiling and
   the dropped empty columns took, and `cols:` names the ceiling part of it. The markdown header row
   is the sheet's first kept row -- the parser never guesses which row "is really" the header.

### `.xls` is refused, out loud, at every layer

`spreadsheets.UNSUPPORTED_SUFFIXES == (".xls",)` and `.xls` is **not** in the upload whitelist:
`inspect_upload_header()` answers `400 unsupported_file` before any byte is written, and a direct
`load_document("...xls")` still answers `ValueError: Unsupported file format: .xls` (the dispatch's
own existing raise; calling `spreadsheets.load_spreadsheet_text()` directly names the reason:
openpyxl cannot read the legacy binary format and `xlrd` is not a direct dependency of this
repository). No error code was added anywhere in this ticket.

### What this ticket does not claim

* The upload response still does not carry the spreadsheet's own receipt (truncation code, sheet
  accounting). Surfacing it is R308; today that account goes to the server log
  (`R305 表格入库 xlsx: {...}`) and to `Spreadsheet.summary()` / `stats()`.
* Preview is **not wired to the display name** (R306 ruling 3). `app/documents/preview.py` calls
  `load_document(str(path))` with one argument, so `GET /api/v1/documents/{filename}/preview` returns
  a spreadsheet anchored by the stored uuid name while the indexed body is anchored by the uploaded
  name. The two texts for one file are therefore not byte-identical, by choice: `{filename}` is
  caller-supplied, and letting it into the parser would give one stored file a different source
  depending on who asked. Wiring it means first deciding where that name is authoritative -- a
  separate ticket, not a silent leftover of this one.
* A spreadsheet that is also a dataset keeps its other life: `POST /api/v1/upload-excel` is
  unchanged and shares nothing with the document whitelist except the extension.
* `app/tools/excel.py:87-88` still selects `engine = "xlrd"` for `.xls`, and `xlrd` is not a
  dependency, so that branch remains dead. Reported here, not treated here.

### Pins

- `tests/test_r306_spreadsheets_in_the_upload_path.py` (28): a real multi-sheet workbook and a real
  CSV arrive through `load_document()` with anchored text, and so do both corpus spreadsheets; the
  new exit cannot let a NUL through, both with a stub and with a file that really holds one; the
  report entry and the direct entry agree byte for byte on both suffixes and both carry the same
  first anchor field; every whitelisted extension is actually dispatched; the six-type closed set
  and its agreement with `SPREADSHEET_SUFFIXES`; `.xlsx` still has to match `PK\x03\x04` while
  `.csv` sits in the same no-magic tier as `.txt`/`.md`; storage stays `uuid + one suffix`;
  `.csv`/`.xlsx` in the middle of a name are still disguises while `V2.1` in the middle is still a
  naming habit; `.xls` is refused at all three layers; preview equals the indexed text for both
  suffixes and never runs ahead of the upload whitelist; the real route indexes a workbook and a CSV
  and answers the pre-existing `document_parse_failed` for a forged body while keeping the file; the
  comment above the whitelist and the S5 sentence above both changed in the same breath; and no
  module this ticket touched gained an error code.
- `tests/test_r130_text_unencodable_is_named_refusal.py`: `test_dispatch_exit_has_its_own_ruler`
  gained the spreadsheet exit in its monkeypatch list and `.xlsx`/`.csv` in its extension tuple;
  `test_every_loader_exit_calls_the_same_ruler` gained `load_spreadsheet`. Both are widenings -- no
  standard was lowered and no assertion was deleted.
- `tests/test_file_upload_security.py` -- the eight places that pinned the **old** state ("a
  spreadsheet never reaches the upload path") were re-bound, not weakened, in the same breath as the
  whitelist: the closed set grew four cells to six; the rejected-extension list swapped
  `sheet.xlsx`/`table.csv` (now accepted) for five still-rejected names; `build_storage_path` gained
  a "stored as `uuid` + exactly one suffix" assertion; `load_document` is now pinned to hand a
  workbook to the parser (`zipfile.BadZipFile` on a forged body, real text on a real one); the route
  is pinned to pass **both** the storage path and `display_name=inspection.display_filename` to the
  parser; the fake-workbook case moved from `400 unsupported_file` to the pre-existing
  `500 document_parse_failed` while keeping the file and writing nothing to the index; and the
  "a rejected upload must touch no disk" tooth was re-bound onto a new parametrized pair
  (`.xls`, `.pptx`) that asserts the directory stays empty. The disguise blocklist copy gained the
  same two cells as production, each backed by its own refusal case.
- `tests/test_r305_spreadsheets.py::test_load_document_reads_both_formats_once_wired` replaces
  `..._still_refuses_both_formats_today`, which pinned the pre-wiring state and is now the inverse
  of the truth. It is a positive pin with teeth: dropping the dispatch branch makes it fail on the
  first assertion, and it additionally pins the anchor's first field with and without
  `display_name`, plus `extract_document_with_reports()` agreeing byte for byte.
- `tests/test_document_upload_resilience.py` / `tests/test_r49_upload_contract.py` /
  `tests/test_document_ownership.py`: six `lambda path:` parser stubs became
  `lambda path, display_name=None:` to match the real signature -- a binding change, same behaviour
  asserted. The source-text pin `test_upload_moves_blocking_parsing_and_indexing_off_the_event_loop`
  was re-bound to the new one-line call including `display_name=inspection.display_filename`; the
  new string is a superset of the old one, so the pin is strictly stronger, and it now turns red if
  the display name is dropped.

## The alert sweep stops hiding the files it could not open (2026-09-27, R345)

R336 ratified one fact for 「which suffix does this platform accept」 and 「which engine reads it」:
`app/tools/excel.py::DATA_READ_ENGINES`, with `app/api/v1/data.py::DATA_FILE_EXTENSIONS` derived from it by
`accepted_data_file_extensions()`. R336 registered, in its own 「Registered, not fixed」 list, that a **third**
copy of that list was still sitting in the alert sweep, and that the sweep swallowed every read failure. This
section closes that registered item; the bullet above it stays as written history, and this paragraph supersedes it.

### The third hand-copied extension list is gone

`app/api/v1/alerts.py::_data_file_extensions` used to read

    extensions = getattr(_data_api_module(), "DATA_FILE_EXTENSIONS", None)
    return {str(ext).lower() for ext in (extensions or {".csv", ".xlsx", ".xls"})}

The fallback branch is dead today (`data.py` always answers) but it was **visible dead code, and the format it
put back on the sweep list is exactly the one R336 refused to read**. Whoever next changes `data.py`'s import
path, or hits a module that cannot hand over that attribute, would have restored a sweep over `.xls` while the
read leg `load_excel` now refuses it first: two books, each drifting on its own. The function is now one call
and no fallback at all:

    from app.tools.excel import accepted_data_file_extensions

    return {str(ext).lower() for ext in accepted_data_file_extensions()}

That is the same call `data.py` takes, so the sweep, the upload gate and the read leg ask one table. If the
declaration table were ever emptied, the sweep finds no files and `scan_scope.reason` says `no_data_files` --
an unusable list is reported as 「no data to evaluate」, never as a possibly stale hand copy. `no extension
literal` is pinned off the AST, so the pin bites the next copy rather than today's value.

### `scan_scope` now names the files it could not read

`POST /api/v1/alerts/check` returns `scan_scope`, and `app/api/v1/alerts.py::evaluate_all` fills it:

| Key | Shape | Contract |
| --- | --- | --- |
| `data_dir_configured` | bool | unchanged from P1-3 |
| `scoped_to_principal` | bool | unchanged from P1-3 |
| `evaluated_files` | list of file names | narrowed to the files that were **actually loaded and fed to the rules**; a file that could not be read is no longer counted as evaluated |
| `unreadable_files` | list of `{"filename": ..., "error": <exception class name>}` | **new**: every file the sweep scoped in and could not read, named |
| `reason` | str | unchanged `tenant_data_dir_unavailable` / `no_data_files` / `no_permitted_datasets`, plus `all_data_files_unreadable` |

- **读不到 ≠ 无异常.** Files were scoped in but none could be read => `reason` is
  `all_data_files_unreadable`, `evaluated_files` is `[]`, and `unreadable_files` names every one of them. That
  is a different sentence from `no_data_files` (the directory really holds nothing), and neither one is
  「no anomaly found」. Before R345 both cases looked identical on screen: `except Exception: continue` left
  `reason` empty and `evaluated_files` listing files that were never opened.
- The two counting cells appear **only when the sweep actually tried to read at least one file**. When nothing
  was found the three existing `reason` values already say the whole thing, and the summary keeps the exact
  four-key shape P1-3's pins assert -- no invented zeros.
- `len(evaluated_files) + len(unreadable_files)` equals the number of files scoped in for this sweep.
- **No server path leaves the process.** `evaluated_files` and `unreadable_files[*]["filename"]` carry
  basenames only and `error` carries an exception class name, never `str(exc)`: `FileNotFoundError` writes the
  absolute path into its own message, and this payload goes to the customer's browser. Same rule as
  `_scan_data_files` (and the same one `chat.py::_pdf_extraction_cell` follows). The full text plus the stack
  go to the server log: `logger.warning(..., exc_info=True)` naming the file and the exception class.
- `app/api/v1/alerts.py::daily_report` held the same bare `except Exception: continue`. Its report text is
  unchanged (wording is another ticket's call), but it no longer swallows the stack: the skipped file is named
  in the log with its exception class.

### What did not move

Alert judgment is word for word untouched: rule selection, `hit`, thresholds, `_metric_value`, the E1-11
per-sweep dedupe, `alert_owner_department` / `_dataset_department_index` stamping, `alert_row_scope_sql` and
`alert_row_visible` row scope, and the `_permitted_dataset_files` authorization loop. No error code and no bare
code is added -- `all_data_files_unreadable` is an internal summary word; it appears in `scan_scope` only, never
as an `HTTPException` `detail`, and both scanners
(`tests/test_r142_error_code_table_sync.py`, `tests/test_error_code_vocabulary.py`) stayed green. The one
customer-visible follow-up this ticket may not do itself: `frontend/src/lib/alerts.js::SCAN_REASON_MESSAGES`
does not carry a Chinese sentence for the new token yet (`frontend/**` is another agent's write set), so the
face falls through to its conservative `unknown` reading -- 「既不说有异常，也不说一切正常」 -- rather than an
all-clear. Adding that one key is a one-line follow-up for the frontend owner.

### Pins

- `tests/test_r345_alert_sweep_shares_the_extension_source.py` (7): AST says no extension-shaped string literal
  survives anywhere in `alerts.py`, and `_data_file_extensions` returns a call on `accepted_data_file_extensions`
  with no container literal in its return; sweep / declaration table / upload gate are one fact today; the sweep
  set **and** `_directory_data_files` follow the declaration table when a row is added and when `.csv` is
  removed (an import-time snapshot fails this, which is the point); every extension the sweep scans is one the
  read leg actually opens; plus the in-test mirror proving the old fallback shape would be caught.
- `tests/test_r345_unreadable_data_files_are_counted.py` (13): one unreadable file is named with its exception
  class while its readable sibling is still judged; the two cells add up to the files found; every file
  unreadable is *not* reported as an all-clear, including end to end through `POST /api/v1/alerts/check` with a
  registered `.xls` (the exact shape R336 registered); the log carries file + class + stack, in the sweep and
  in `daily_report`; a path-bearing exception leaks nothing into `scan_scope`; nothing was found => no counting
  cell is invented; department stamp and rule hit are untouched; the token is not in the closed enum and not in
  any `detail`; `evaluate_all` still never raises; and the AST refuses a bare `except ...: continue` in the sweep.
- Four knives were run on disk against `app/api/v1/alerts.py` and restored by sha256 (control readings before
  and after matched: `542d393ffd99fda1`): reverting the extension leg to the base two lines reddens 5 pins in
  the first file; reverting the read-failure leg to a bare `continue` reddens 9 in the second while all 8 of
  `tests/test_r345_alert_scan_scope.py` stay green (the existing pins do not forbid the new cells); the same
  mutation, probed against a directory whose every file fails, answers
  `{'data_dir_configured': True, 'evaluated_files': ['empty.csv', 'fake.xlsx'], 'reason': '', ...}` -- the
  all-clear face -- where the shipped code answers `reason='all_data_files_unreadable'`, `evaluated_files=[]`
  and names both files with `EmptyDataError` / `BadZipFile`; replacing the live call with an import-time
  snapshot reddens 3 (the shape pin plus both direction teeth) while 「one fact today」 stays green -- which is
  exactly why the value-only pin was not enough.
- Physical lines: `app/api/v1/alerts.py` 1012 -> 1055 (+48 / -5). No other tracked file changed; this section is
  appended and deletes nothing.

## The relation listing can be asked about a document on either end: `GET /api/v1/knowledge-graph/relations?document=` (2026-09-27, R344)

`app/knowledge_graph/service.py::_listing` filtered this enumeration one way only:
`item.source_entity == source_entity` -- the subject end, and the whole registered name character for
character. A document that a relation names as its **object** was therefore unreachable from the server:
《差旅管理办法》 `--依据-->` 《员工手册》 registers the handbook in `target`, so
`?source_entity=员工手册` answers empty for it. That is why `frontend/src/components/DocumentPreviewModal.vue:239`
fetches this route with **no** query parameter and filters the rows in the browser (`:96-120`), and why its own
comment (`:48-50`) states the reason out loud. This section adds the server-side leg the client was compensating
for. `source_entity` is not modified, `relation` is not modified, and the response body is not modified.

### Query parameters of `GET /api/v1/knowledge-graph/relations`

| Parameter | Compares against | Rule | Absent means |
| --- | --- | --- | --- |
| `source_entity` | `Relation.source_entity` | whole registered name, verbatim -- **unchanged by R344**, still not normalised | no filter |
| `relation` | `Relation.relation` | verbatim -- unchanged | no filter |
| `document` | `Relation.source_entity` **or** `Relation.target` | either end may match; both ends are compared through `document_identity_key` below | no filter |

- It is an **addition**, not a replacement: `?document=` alone leaves the subject leg out of the picture, and
  `?source_entity=` alone behaves exactly as it did before this ticket.
- Given **together they intersect (AND)**. `?source_entity=部门预算&document=员工手册` returns nothing when the
  only row naming the handbook has 《差旅管理办法》 as its subject -- the new parameter does not override the old
  one, and the old one does not override the new one. Neither parameter widens the other.
- A row that names the document on **both** ends is listed **once** (self-referential registrations included);
  the filter narrows candidate rows, it does not join the row to itself.
- A `document` whose identity key is empty -- `?document=`, or a name made only of whitespace -- matches
  **nothing**, which is what the client's own reader does with a blank name
  (`DocumentPreviewModal.vue:106` `if (!key) return []`). It is not treated as "no filter".
- `document` sits after `request` in the route signature (`app/api/v1/intelligence.py:248`) on purpose: existing
  callers in this repo and its tests pass the request object positionally as the third argument.

### The identity standard is the client's, transcribed -- not Python's `re.\s`

`document_identity_key` (`app/knowledge_graph/service.py`) is the server-side twin of `documentIdentityKey`
(`frontend/src/components/DocumentPreviewModal.vue:58-61`), which is

```javascript
const text = String(value ?? '').replace(/\s+/g, '')
return text.toLowerCase()
```

and this is the Python, in full, as it stands:

```python
_JS_WHITESPACE_CODE_POINTS = frozenset(
    {
        0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x0020, 0x00A0, 0x1680,
        0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF,
        *range(0x2000, 0x200B),
    }
)
_DELETE_JS_WHITESPACE = {code_point: None for code_point in _JS_WHITESPACE_CODE_POINTS}

def document_identity_key(value):
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return text.translate(_DELETE_JS_WHITESPACE).lower()
```

The set is spelled out rather than taken from `re.sub(r"\s+", "", ...)` or `str.split()`, because those are not
the same set. Both readings below are measured: the JS column is
`node -e "String(v).replace(/\s+/g, '').toLowerCase()"` and `/\s/.test(...)`, the Python column is
`re.match(r"\s", chr(cp))` and `chr(cp).isspace()` swept over the whole plane.

| Code point | ECMAScript `\s` | Python `\s` / `isspace()` | What `?document=` does |
| --- | --- | --- | --- |
| `U+FEFF` BOM | matches | **does not** | deletes it: `\ufeff员工手册.pdf` and `员工手册.pdf` are one 篇 |
| `U+0085` NEL | does not | **matches** | keeps it: it is part of the name at both ends |
| `U+001C`-`U+001F` | do not | **match** | keep them |
| `U+200B` ZWSP | does not | does not | keeps it: `员工\u200b手册` is a different name from `员工手册` |
| `U+00A0`, `U+2000`-`U+200A`, `U+2028`, `U+2029`, `U+202F`, `U+205F`, `U+3000` | match | match | delete them, including the full-width space typed into a registered name |

`.lower()`, and never `.casefold()`: `'ß'.toLowerCase()` is `'ß'` while `'ß'.casefold()` is `'ss'`, and
`'İ'.toLowerCase()` is `'i\u0307'` -- two code points. A casefolded server would recognise document pairs the
browser refuses, which is a second standard, which is the failure this section exists to prevent. The pair table
in `tests/test_r344_document_identity_normalization.py` carries the JS readings row by row, and
`test_the_whitespace_set_is_the_ecmascript_one_and_not_python_s` pins the two set differences code point by code
point so that swapping in `\s` cannot pass quietly.

The comparison is **whole name only, both directions**. `员工手册` must never pick up `员工手册.pdf`,
`员工手册补充规定`, or `员工`, and `员工手册.pdf` must never pick up `员工手册`: `includes`, `startswith`
and any other prefix or substring rule are refused here, and are pinned red by named cases.

### Authorisation does not move, and the new leg is not a bypass

`_listing` remains one scan with one predicate order: entity filters decide *which rows are candidates*,
`may_see` then decides *whether this principal may be shown each candidate*. The document leg only ever removes
rows. Concretely:

- `may_see` is `can_browse` (`app/knowledge_graph/service.py:480-520`) and runs on **every** candidate row that
  survives the entity filters, including rows matched through `target`. Skipping it for filtered rows is pinned
  red by name, not by row count.
- `principal is None` still returns `[]` before any filtering.
- `staff` 密级下的行为 is the same reading as without the filter, because nothing in the clearance or visibility
  math was touched: every relation is written `visibility="private"` with `classification` capped at its author's
  clearance, so `discloses_to` gives a private row to its author or to an administrator and to nobody else --
  a `staff` colleague in the same department browsing `?document=员工手册` gets an empty listing, and the author
  of that row gets the row. `discloses_to` has no line changed in this ticket.
- **The division of labour between `query()` and `browse()` stands** (`service.py:516-544`): `query` is the scope
  answer and must never be rendered; `browse` is the exit allowed to reach a client. `document` was added to
  `browse` only. `KnowledgeGraph.query` takes no `document` parameter, and
  `test_the_scope_leg_still_has_no_document_parameter` pins that so the new filter can never become a way of
  getting a withheld row onto a screen.
- The response shape is unchanged: `{"relations": [Relation.to_dict()...]}`, one key at the top, no new key, no
  renamed key, no dropped key, and the `document` parameter is never echoed back into a record.

### What this ticket does not claim

- No migration, no new table, no index, no storage format change (判据⑥). The listing is still the JSON store's
  in-memory dictionary scan it was. If the row count ever makes that scan the wrong answer, that is a separate
  ticket to be argued; it is reported here and deliberately not acted on.
- The frontend is **not** changed by this ticket -- `DocumentPreviewModal.vue` still pulls the full browsable
  listing and filters client-side. Switching it to `?document=` is a follow-up that belongs to the frontend
  write set, and this section documents the leg it would use.
- No promotion, verification, or classification behaviour is claimed here: only enumeration.

### Pins

- `tests/test_r344_document_identity_normalization.py` (43): 27 paired samples whose expected readings were
  taken from a real JS engine, 6 same-document pairs, 6 different-document pairs, the whitespace-set identity
  including both Python divergences, the `.lower()`-not-`.casefold()` pair (`ß`, `İ`), the blank-name key, and
  idempotence of the key.
- `tests/test_r344_relations_document_filter.py` (40): either-end hit and the old leg's blindness in the same
  case (刀A), both-ends-lists-once, the route on the wire through `TestClient`, 7 spelling-variant rows (刀B),
  9 one-character-off rows (刀C), 5 verbatim-`source_entity` rows (判据③), the AND intersections with
  `source_entity` and with `relation`, anonymous `[]`, the withheld private row named by `relation_id` (刀D),
  a spy that proves `can_browse` was asked about the row the document leg matched (刀D second half), the
  cross-department and `staff` legs, the administrator leg, `query`'s signature, the response shape measured
  from `dataclasses.fields(Relation)`, and the fact that the new leg still rides the one existing scan.
- Reversal readings, each run against the real source and restored byte for byte (sha256 verified against the
  pristine copy after every run): subject-only predicate -> 13 red; `==` instead of the identity key -> 7 red
  (`test_a_registration_spelling_variant_answers_as_the_same_document`, every parameter); `includes` -> 4 red
  and `startswith` -> 4 red (the two directions of
  `test_a_name_one_character_off_does_not_answer`); `and may_see(...)` dropped -> 15 red across this file and
  `tests/test_r177_relation_visibility_read_path.py`, and the first assertion to fail is
  `assert private.relation_id not in ids` naming the withheld record rather than a length; `source_entity`
  normalised as well -> 4 red (`test_the_subject_leg_still_demands_the_whole_registered_name_verbatim`), which
  is the pin that keeps the old parameter's meaning frozen.

## The upload receipt says one reason once, not once per page (2026-09-27, R347)

`pdf_extraction.degradation_note` keeps its key and its two tiers, and stops repeating itself.
The per-page book in `app/rag/loader.py` is untouched and is still the source of truth
(`degradation_notes` -- one entry per degraded page -- and `degradation_sentence`, which joins
all of them with the full-width semicolon). That join is what made the receipt unreadable: a
400-page scan that failed for one reason got that same sentence recited 400 times, and R338
measured the shape (`4853 chars truncated`). The merge therefore happens **only in the receipt
layer**, in `app/api/v1/chat.py::_pdf_extraction_cell`, reading `report.pages` -- 同因合并只发生在
回执层，逐页真源账没变.

| today's shape | |
| --- | --- |
| group | degraded pages sharing a byte-for-byte identical `page.note` form one group; different reasons stay different sentences (no normalization, no fuzzy match: `栅格化失败 RuntimeError` and `识别失败 RuntimeError` are two sentences) |
| order | groups in order of first appearance, page numbers ascending -- the same order `report.pages` has |
| sentence | `第1、2、3页：{reason}`, joined with `；`, preceded by the tier head and `：` |
| page cap | `chat.PDF_DEGRADATION_PAGE_LIST_CAP = 10` page numbers per group |
| over the cap | `第1、2、…、10页，另有 290 页未列出：{reason}` -- `N` is the true remainder for that group (`len(pages) - len(shown)`), never the length of the truncated list |
| no repetition | when every group holds one page, the receipt ships `report.degradation_sentence` verbatim: the merge only compresses repetition, it does not re-render the ruler (R301's "if the ruler changes its wording, the receipt changes with it" still holds) |
| no degradation | empty string `""` -- not `null`, not a polite invention. `page_count: 0` and "pages exist, nothing degraded" remain two different readings |

Three things did not move, each pinned by `tests/test_r347_degradation_note_merges_by_reason.py`:

1. **The two tiers are still two sentences.** The head comes from `ocr_available`: `false` opens
   with `ocr.ENGINE_UNAVAILABLE_NOTE` ("本地 OCR 引擎不可用，扫描页未识别文字"), `true` opens with
   `loader.DEGRADATION_NOTE_PREFIX` ("扫描页 OCR 降级"). R347 merged pages, not tiers -- R338's
   knife 1 measured what happens when they are squeezed into one sentence (9 pins red).
2. **The reason is copied, never rewritten.** No translation, no polish, no "很抱歉", no stripped
   punctuation: the segment after `页：` equals `page.note` character for character, colons inside
   the reason included.
3. **Nothing is lost and no key moved.** `ocr_degraded_page_numbers` is still the full list of
   degraded pages (the merge truncates the *sentence*, not the *account*), `source_counts` is
   `report.source_counts` word for word -- `blank` and `ocr-empty` are not merged -- and the key
   set of `_pdf_extraction_cell` is byte-identical to the one at base `c5c3c41`. Only the text
   inside `degradation_note` got shorter.

Physical lines: `app/api/v1/chat.py` 4690 -> 4761 (+75 / -4). `app/rag/loader.py` untouched.
This section is appended and deletes nothing.


## The preview and the upload receipt also name their owner (2026-09-27, R337)

R310 gave `GET /api/v1/data-files` an `owner_id` and stopped there. Two sibling exits of the same
surface never followed: `POST /api/v1/upload-excel` answered `dataset_id` / `version_id` /
`classification` with no owner, and `GET /api/v1/data-files/{filename}/preview` answered
`dataset_id` / `version_id` -- neither owner, nor classification. V2 asks for a stable ID *and an
owner* on every resource; a field that names an owner on one of three exits is half a clause.
R337 adds two keys and nothing else: no new lookup, no second permission chain, no new row, no new
column, no new error code.

### `POST /api/v1/upload-excel` -> `owner_id` and `GET /api/v1/data-files/{filename}/preview` -> `owner_id`

| key | type | presence | meaning |
| --- | --- | --- | --- |
| `owner_id` | string / null | always, on a 200 body | the account that owns the row, or `null` when nobody is on record |

Both answers come from the record the route already holds. The upload receipt reads the
`DatasetRecord` that `dataset_registry.register(...)` just returned, in the same statement that
reads its `dataset_id`; the preview reads the record `_authorized_dataset` handed back a few lines
above. Neither opens a query to get it.

### Where the value comes from

Both sites call the one reader, `app/api/v1/data.py::_dataset_row_owner_id`, and its docstring is
the rule. This section deliberately does not re-copy that wording: a second paraphrase is exactly
how two surfaces start to disagree about one field. The reader is checked against the document
catalogue's own `_is_unowned` predicate over a corpus of values
(`tests/test_r310_dataset_row_owner.py`), and `tests/test_r337_owner_receipt_on_both_exits.py`
(`owner_shape_violations`) checks that both new exits obtain the value through that reader and
nowhere else -- an inline `record.owner_id` at either site is red even when it happens to produce
the same string, because then the rule lives in two places and only one of them gets fixed.

Why `null` rather than `""` is worth a ticket: `""` is a value a client can drop straight into a
table cell, and an empty cell reads the same as "the record has no owner column" and the same as
"nobody looked". `null` is the only spelling that says *this row was looked at, and nobody is on
record for it*. A renderer writing `owner || '—'` cannot tell those three apart; a renderer testing
`owner === null` can. That is why "unowned is `null`, never `""`, never 未分配" is a contract line
and not a style preference.

### Three faces, and they must not be folded into each other

- **The row exists and has no owner on record.** The body carries the key and answers
  `"owner_id": null`. Decided by `_dataset_row_owner_id`.
- **The caller may not see this row.** There is no body to hold a key: the preview answers 403 with
  the policy's own reason, and the catalogue counts the row under `restricted` without naming it.
  Decided by `app/common/policy.py`, before anyone reads an owner.
- **The registry never heard of this row.** The preview answers 404 `resource_not_found`; a
  request-less catalogue listing still carries the key and answers `null`. Decided by
  `_authorized_dataset` / `get_active_by_filename`.

The first and the third answer `null` in this field -- that equivalence was R310's ruling, and it is
pinned -- and they remain distinguishable by the key next to them: the row the registry never heard
of has no `dataset_id`. What none of the three may ever do is answer `""`. A record object that
carries no owner column at all (in-process fakes; the registry fills the column on every row it
reads) is given the first face's answer as well, so that an ownership field can never surface as a
500 `dataset_preview_failed` -- a missing field reported as a server fault would be a lie about
which layer broke.

### Cost, measured rather than asserted

`tests/test_r337_owner_receipt_cost_and_knives.py` runs two identical worlds through the shadow root
of `tests/_temp_edit_overlay.py`: one with the delivered source, one in which both owner reads are
physically removed -- the `957c7d2` shape, not a recollection. Reported numbers: 13 exit cells (five
catalogue listings, seven previews, one upload receipt) whose bodies are byte-identical with the
owner key stripped, and `get_active_by_filename` 25 / `authorization_decision` 21 on both sides.
One knife in that file re-adds a registry lookup inside the owner read; the bodies stay identical
and only the tally moves (25 -> 33, one extra lookup per preview cell), which is the whole reason
the tally exists.

### Registered, not fixed (outside this write set)

- **The preview exit still answers no `classification`, and R337 did not add one.** The catalogue
  row may carry it and the preview may not, and the difference is defensible today: the catalogue
  row describes the *object* (name, size, mtime, ids, classification), while the preview is a
  row-scoped view of *content* whose honest-empty and refused-row shapes are pinned by R170/R180 --
  putting a file-level classification next to filtered rows invites the reading "these rows are
  classified X", which is not what the field means. It is also an asymmetry inside one product:
  the upload receipt next to it does answer `classification`. Whether registration fields belong on
  a preview surface is a ruling for 总控/业主, not a tail to be trimmed by an owner ticket, so
  `test_the_two_exits_answer_exactly_the_documented_registration_keys` pins the current shape and
  goes red the moment anyone adds it silently.
- `app/api/v1/data.py::delete_data_file` still spells the owner for its audit summary as
  `record.owner_id` (`:434`) instead of the shared reader. It is an audit payload, not a response
  exit, so it can carry the registry's raw `""` for an unowned row today; unifying it changes what
  lands in the audit log, which is a different surface and a different ticket.
- Physical-line citations moved again: `app/api/v1/data.py` is 575 -> 599 lines (+26 / -2). The
  reader R336 restated as `:76-94` now reads `:78-103`; the catalogue's owner line `:267` now reads
  `:276`. These are line-number notes, not contracts -- the shapes they point at are unchanged, and
  `tests/test_r186_row_scope_contract.py` reads them off the AST.

### Pins

- `tests/test_r337_owner_receipt_on_both_exits.py` (9): the upload receipt names the uploader
  through the real route table; the preview names the owner the registry holds, for every account
  and every file it may open; the three exits never disagree about one row's owner; both new sites
  read it only through the shared helper (AST, `owner_shape_violations`); the two exits answer
  exactly the documented registration keys; an unowned row answers `null` on the wire and never a
  blank; a record without an owner column answers `null` instead of a 500; the three faces stay
  three; and R310's line anchors still hit `data.py` exactly once, so that ticket's four knives
  still land.
- `tests/test_r337_owner_receipt_cost_and_knives.py` (7): the two-world reconciliation above, plus
  five knives -- unowned -> `""`, bypass the helper, add a lookup, drop the preview owner, drop the
  upload owner -- each run inside a shadow window and re-run green after it closes.

## The preview asks the relation table about one document: the client leg of `?document=` (2026-09-27, R348)

The last bullet of the R344 section above no longer describes today's tree, and it is kept exactly as that
ticket wrote it. It records what R344 promised at the time: no frontend file was touched, and
`DocumentPreviewModal.vue` still pulled the whole browsable listing and filtered in the browser. R348 is the
follow-up that section already named, and its line-number references (`:239`, `:96-120`, `:58-61`, `:106`) are
the coordinates of that day and stay that way on purpose -- rewriting history lines would leave the contract
with no provenance. Today's coordinates are below.

### The read, and the shape it must keep

`frontend/src/components/DocumentPreviewModal.vue` reads the relation table through exactly one `api.get`, and
that call builds its URL in exactly one place:

- `:138-140` `relationsListingUrl(name)` returns `/knowledge-graph/relations?document=` plus the name through
  `encodeURIComponent`. One path, one parameter, and its name is `document`.
- `:519-522` `fetchRelationRows(documentName)` is the only caller: `api.get(relationsListingUrl(documentName))`.
  The file holds no second relation read; `GraphPanel.vue:31` keeps its unparameterized listing because that
  screen has no current document to ask about.
- `:151` `readDocumentRelations` hands the name it was given straight to the fetch leg, so what goes out is the
  registered name of the document on screen.

The client sends that name **verbatim**: percent-encoding only, never `documentIdentityKey`. Stripping
whitespace or folding case before the request would put two identity standards on the wire at once, and the
server's `document_identity_key` would then be comparing a value the client had already edited. The store's
blank-name guard (`:183-186`) is what keeps an empty `?document=` from ever being sent: an empty identity key
matches nothing server-side, so it must never be used as a way of asking for everything.

Both legs that open a document share this one read -- the preview the parent opened (`:626` from the watcher,
`:641` from `onMounted`) and the R343 jump-to-the-other-end leg (`:611-612`). One opened document, one relation
read; not two reads, and not a second filter parameter. The three late-response token gates are byte-identical
to what R343 left: relations `:189`, preview jump `:370`, catalog `:448`.

### The client comparison is now a belt, and a belt has to be the same ruler

`relationsAboutDocument` (`:100-128`) still drops rows whose two ends do not name this document. It is no
longer the only filter, so keeping it is only honest while it judges the way the server does: two rulers that
disagree lose rows in silence, and the screen then offers 「登记的关联里，没有文档名与这篇相同的」 for what is
actually a mismatch between the ends. That is pinned twice, both times by reading the server's own evidence
off disk rather than by a copy of it, in
`frontend/src/components/__tests__/r348-document-scoped-relations.test.js`:

- 乙 · 反证 3（其一） `:164-168` and （其二） `:170-177`: the 27 paired samples and the 6+6 same/different
  pairs of `tests/test_r344_document_identity_normalization.py` are parsed at test time and fed to the
  frontend `documentIdentityKey`; every reading has to match the column that pin was measured against a real
  JS engine. The frontend carries no list of its own -- a hand-copied second table would be a third ruler.
- 乙 · 同判 `:179-200`: those 27 names are laid out as a 27x27 listing, the server-side keep/drop is derived
  from the table readings with the empty-key-matches-nothing rule `app/knowledge_graph/service.py` applies, and
  the row keys the client keeps have to equal that list for each of the 27 choices of the current document.

Keeping the belt instead of deleting it is also what makes an older server harmless: on a deployment that
predates R344, `?document=` is an unknown query parameter and gets ignored, so the response is the full
listing -- and the belt is then the only thing between that listing and the screen.

### Server-side narrowing did not merge any faces

`[]` means the document has no registered relations and stays `empty`; `:152` asks only whether the payload is
an array, never whether it has a length. A throw, a wrong shape and a 403 stay `failed`, with `denied` its own
branch. idle / loading / failed / empty / matched are still five, pinned by `r314-related-docs.test.js` (37
cases, one of them reworded below) and by 丙 · 反证 4 of the R348 file.

### Pins

- `frontend/src/components/__tests__/r314-related-docs.test.js:463-488` -- the case that used to forbid any
  query parameter became a shape criterion rather than being deleted or skipped: one `api.get` in the file,
  one place where the URL is built, exactly one filter parameter and it must be `document`, no `source_entity=`
  (the subject-only leg, blind to this document in the object position -- the very reason the full pull
  existed), no second parameter, no `post/put/delete/patch`. Five assertions became twelve; the two `not.toMatch`
  lines that still describe the truth were kept word for word.
- `frontend/src/components/__tests__/r343-open-related-document.test.js:614-629` -- the same stale literal turned
  out to be pinned a second time, in the request-budget case. Reworded the same way; case count unchanged (38).
- `frontend/src/components/__tests__/r348-document-scoped-relations.test.js` (14): 甲 the name goes out verbatim,
  percent-encoded and un-normalised, and one open is one read; 乙 the two-ruler readings above; 丙 read count,
  parameter count, the faces, and the late-response race.
- Reversal readings, each run against the real source and restored byte for byte, with the sha256 of the
  pristine buffer re-checked after every run: `document=` back to `source_entity=` -> 6 red; the frontend ruler
  loses its case folding -> 8 red; one row of the R344 table edited to keep `U+FEFF` -> 2 red, and those two are
  the 乙 pair, which is what shows the belt pin is fed by the server table rather than by a copy; `[]` routed
  into `failed` -> 4 red; `failed` routed into `empty` -> 4 red; the relations token gate removed -> 3 red; a
  second relation read added on the jump leg -> 3 red.
- Suite: 96 files / 1882 passed against a base of 95 / 1868 (one new file, fourteen new pins, zero
  regressions); `npm run lint:colors` still 148 problems / 0 errors with no new colour value; `npm run build`
  exit 0; the three contract pins `tests/test_r302_docs_utf8_guard.py`, `tests/test_r132_contract_followup_sync.py`
  and `tests/test_r156_sse_event_surface_sync.py` re-run after this section was appended.

### What this ticket does not claim

- Nothing about backend behaviour is claimed or changed here. `app/**` was read-only for this ticket; this is
  the client leg of the parameter R344 already documented.
- No test in this repo executes the URL that actually leaves the browser. There is no jsdom, and
  `fetchRelationRows` lives in `<script setup>`, which SSR never lets reach the network
  (`DocumentPreviewModal.vue:639-641`). The builder and the name forwarding are run for real; the last
  centimetre of wiring is held by the shape pins and by the second-read reversal above. It is registered here
  as a known edge for the real-browser pass, and the answer is not to install a DOM.
- The identity standard itself is R344's, unchanged: `document_identity_key` and `documentIdentityKey` are the
  two ends of one ruler, and this section adds no third.


## The trend names its holes: `undated`, and three faces that used to share one 503 (2026-09-27, R342)

`GET /api/v1/dashboard/trend` gains one top-level key. `app/api/v1/dashboard.py` stops treating 「这一枚行没有期间」
as a reason to refuse the whole response, and the R341 card that now reads this route (`TREND_PATH`,
`frontend/src/lib/dashboard.js:346`) says the hole out loud instead of disappearing.

| Key | Type | Nullable | Says |
| --- | --- | --- | --- |
| `undated` | object | no | per-book counts of rows **inside this caller's visible scope** whose stored period was never recorded |

`undated` carries `documents`, `documents_ready`, `datasets`, and -- only for a caller with alert rights --
`alerts`, `alerts_open`. The name was set upstream: board §4CV, R332 ruling ③ asked for 「显式 `undated` 出口」, and
`app/api/v1/dashboard.py::_TREND_UNDATED` is that same word, used both as the classifier's face and as the
response key, so the reading of a row and the number the card renders cannot drift apart. It is a sibling of
`series`, never another bucket: 「有多少条没有期间」 is a different question from 「这一期新增了几条」.

**The law this shape exists to keep.** Per book and per caller:

    sum(bucket[key] for bucket in series) + undated[key] == the number /summary reports for the same key

holds whenever the window covers the corpus (`/summary` counts every visible row; `series` counts the window --
R332's 「Series totals are not the tile totals」 still applies to the *dated* rows). `tests/test_r342_trend_undated_exit.py`
measures both sides rather than asserting the arithmetic in prose: `test_the_three_books_all_reconcile_with_what_summary_reports`
seeds dated + undated + disposed rows and reconciles four keys against the live `/summary` of the same caller, and
`test_no_row_is_counted_twice` pins the other direction (a row may not land in a bucket *and* in `undated`).
A `0` in a bucket still means 「这一期真的没有新增」; it is never a stand-in for a missing period, and the client is
forbidden to compute the difference itself -- the browser moves these numbers and never re-derives them.

### Three faces, classified before anything decides (`_trend_period` -> `_trend_moment`)

| Face | Stored shape | Answer | Evidence the shape is real |
| --- | --- | --- | --- |
| **undated** | nothing was recorded: `None`, `""`, whitespace | `200`, `undated[key] += 1` | `app/storage/datasets.py:763` feeds the legacy sidecar import through `_timestamp_text(None)` -> `""` (`datasets.py:60-72`); the register path itself takes `created_at = previous.created_at or now` (`datasets.py:921`) |
| **garbled** | recorded, but not a period (unparseable text, or neither text nor `datetime`) | `503 storage_unavailable`, unchanged | `document_versions.created_at` is `TEXT NOT NULL` with **no `DEFAULT`** (`app/documents/catalog.py:528`, `migrations/0003_legacy_runtime_tables.sql:46`), so a cell can hold anything a writer put there |
| **contradiction** | a file `data.list_data_files` reports visible that the registry holds **no active row** for | `503 storage_unavailable`, unchanged | two reads of one book disagreeing is a defect, not a footnote; `_dataset_series` still raises before counting anything |

The split is the point (判据 乙). Washing the second face into `undated` would launder a consistency failure into a
sentence about missing time; R332's pins `test_a_visible_file_whose_registry_row_vanished_refuses_the_series` and
`test_a_document_row_with_an_unparseable_time_refuses_the_whole_series` stay green, and R342 adds named pins for each
face on each of the three legs (`..._still_refuses_the_whole_series`, `..._still_refuses`,
`test_a_non_text_non_datetime_period_still_refuses`). No `except` clause in this module catches a whole book:
`_document_series`, `_dataset_series` and `_alert_series` contain no `except` at all -- each row is classified, then
the caller decides, and a read that raises propagates untouched (判据 丙).

### What this overturns, and why in the open

This section **retires** one sentence and one bullet of the record above it:

- `app/api/v1/dashboard.py::dashboard_trend` used to say 「the response is either every period or no response」
  (line 510-512 of the base). It now says the response is never *partial*, and lists the two faces that still refuse
  it. A row with no recorded period is not a read that failed, so it is counted and named instead.
- 「The two faces of nothing」 above (R332) listed **three** triggers of the 503, the first being 「`created_at` empty」.
  That first trigger is no longer true: empty is `undated`. The other two (unparseable, vanished active row) still are.

Nothing is deleted from those paragraphs, per this repository's append-only contract: supersession is stated here,
next to the citation it supersedes, which is how R337 / R344 / R347 handled the same situation. The 判据 the R332
docstring derived from the refusal also survives, because it was never about refusing for its own sake:

- 「dropping the row makes the series total less than `/summary` reports for the same caller」 -- kept, and now honoured
  by *naming* the hole rather than by rejecting the answer: the equation above is exactly that invariant, with
  `undated` as the term that used to be missing.
- 「filling the hole with `0` is the face the client already refuses to render」
  (`frontend/src/lib/dashboard.js:32`, 「不会用旧数字或 0 顶上」) -- kept: no bucket gains a phantom row, and
  `undated` never absorbs a real count into zero (`test_the_undated_count_is_never_written_as_the_zero_it_replaced`).

### Permission, codes, migrations

`undated` follows the alert-absence rule of the buckets exactly: a caller without alert rights gets **no** `alerts`
and **no** `alerts_open` key in `undated` either -- a `0` there would be the alert ledger read through a route that
is not `GET /alerts`, reachable with one `ACTION_ANALYZE` call (request R1). Zero new error codes (`503
storage_unavailable` and `422 validation_error` only, `detail` literals uninterpolated, so
`test_the_route_opens_no_error_code_outside_the_ratified_enum` stays green), zero migrations, zero backfill: the
route reports the shape it finds, it does not repair it.

### Pins

- `tests/test_r342_trend_undated_exit.py` (20): the block is always present and starts at zero; a legacy dataset row
  answers `200` with `undated.datasets == 1` and no bucket absorbed; blank and whitespace are one face; an undated
  row moves neither a dated row nor the newest-recorded winner when one file has several rows; alerts count in both
  of their columns by disposition; documents count in both of theirs; the four conservation measurements against
  `/summary`; `undated` is a sibling of `series` and never a bucket key; the three faces stay three; a raising read
  still propagates; a staff caller gets no alert keys in either place; the analyze gate still runs first.
- Frontend (R341 files, 改口 by addition only): `parseTrendPayload` requires the `undated` object, refuses to
  invent zeros, and never derives a number from it; `DashboardPanel.vue` renders the sentence the server's numbers
  produced; `r267-overview-no-self-fed-rows.test.js` pins that the browser keeps no second book.

## Listing accounts: the three faces of `GET /api/v1/users` (2026-09-27, R356)

This route answers with one of three faces, and they are three different claims. Before this ticket
the second one was rendered as the third. In production with the process-local user table -- the
condition `_memory_store_denied("user listing")` in `app/common/auth.py`, i.e. `APP_ENV=production`
and no reachable PostgreSQL -- the read path returned `[]`, so a client that asked "who works here"
was told "nobody". That sentence is about the company, not about storage, and it was false. The write
path sitting in the same module had always answered honestly
(`(False, "production_user_store_unavailable")`): one fact, two faces, one of them a lie.

| Face | When it happens | Provenance |
|---|---|---|
| `403 {"detail":"权限不足: users:manage (permission_denied)"}` | Authenticated but no `users:manage`. The gate still runs before anything is read, so somebody who cannot manage accounts cannot use this route to learn whether the store is up. | `authorize_request` (`app/common/authorization.py:50-57`) called at `app/api/v1/auth.py:101`; pinned by `tests/test_r356_users_refusal_face.py::test_the_authorization_gate_still_runs_before_the_roster_is_read`, and on the gate side by `tests/test_r290_department_endpoint.py` / `tests/test_authorization_api.py` |
| `503 {"detail":"storage_unavailable"}` | The store refused to answer. Not "no accounts", not "some accounts are hidden": the roster cannot be read. | `app/api/v1/auth.py:102-105` catches `app.common.auth.UserStoreUnavailable`, raised at `app/common/auth.py:581-583`; pinned by `test_the_route_answers_503_when_the_user_store_refuses_the_roster` and `test_a_refusal_is_never_rendered_as_an_empty_roster` |
| `200 {"users": []}` | The store answered and the roster really is empty -- a clean installation, or every account deleted. This face must stay reachable, otherwise "refused" would be the only answer a client ever sees. | `tests/test_r356_users_refusal_face.py::test_a_clean_store_answers_200_with_zero_rows`; the five keys of every row (`id`, `username`, `role`, `department`, `created_at`) are unchanged and pinned by `test_the_roster_projection_still_answers_the_five_keys_r316_reads` |

The refused face and the empty face share no wording, and that is a contract rather than a style
choice: `test_the_three_faces_share_no_words` compares the three bodies byte for byte. A client must
render 503 as "the roster cannot be read right now" (fix `DATABASE_URL`, run the migrations, wait for
the store and retry), never as "this company has no accounts".

**Zero new error codes.** `storage_unavailable` is already a member of
`app/agents/contracts.py::ErrorEnvelope.code` and already sits in the table under
`## REST Error Envelope`; this route reuses that word verbatim because the client-side 503 face keys
off exactly it. `tests/test_r142_error_code_table_sync.py` and
`tests/test_error_code_vocabulary.py` are unchanged and green, and
`test_the_refusal_face_uses_a_code_the_repository_already_registers` re-reads the enum from the AST so
this section cannot name a code the backend does not have.

### Registered, not fixed (outside this write set)

- **`auth.list_users()` still answers `[]` when the caller does not say which face it wants.** That
  legacy reading is pinned by three tickets that are not this one's to edit:
  `tests/test_r229_auth_semantics.py:88`, `tests/test_deployment_guards.py:288`,
  `tests/test_r230_db_ready_selfheal.py:54` -- and that last file also compares
  `type(result) is type([])` at `:577`, so it is itself an anti-"empty enough to pass" pin. Flipping
  the default is a 改口 of another ticket's assertions and belongs to 总控, not to an execution layer
  quietly rewriting its neighbours.
- What this ticket does instead is make the refusal *sayable*, and make silence impossible to re-grow
  by accident: `list_users(denial=auth.DENIAL_RAISES)` raises `auth.UserStoreUnavailable`, and
  `test_every_production_call_site_asks_for_the_truthful_shape` scans `app/**` and goes red if a
  roster read does not name the shape it wants. Today there is exactly one such read, the route.
- Physical line numbers are the lines at delivery; the shapes they point at are the contract.

### One line on roles, because `role` is contract-visible (R357)

R357 changes no answer any client can see. The set of roles that may be created or assigned is still
exactly `staff / manager / admin` -- one definition now (`CREATABLE_ROLES`,
`app/common/permissions.py:41`) instead of three hand-copied lists, imported by `app/common/auth.py`
(create, SSO re-assign) and `app/common/sso.py`. `auditor` stays in `ROLE_PERMISSIONS` and stays *not*
creatable, with the reason stated where a reader will meet it: it has no clearance tier yet
(`app/common/rbac.py:31`), and the tier question is H13, still with 业主. So `POST /api/v1/users` with
`"role": "auditor"` still answers `400 非法角色: auditor`, and an `X-SSO-Role: auditor` header still
lands on `staff` (`tests/test_r357_single_role_roster.py`). No switch was added: nothing in this
family reads an environment variable.

## 「其中当时未闭环」: `alerts_open` is now counted at its own bucket edge (2026-09-27, R340)

One column of `GET /api/v1/dashboard/trend` changes口径. The key, its type, its absence rule, its sibling in
`undated` and every other column do not: this section adds no column, renames nothing, deletes nothing.

### What the old reading was, and why it misled while telling the truth

Two sentences are retired by this section, quoted verbatim so a reader who meets them above knows which one
is standing:

| Retired sentence | Where it stood |
| --- | --- |
| 「截至今日仍未处置」 | `app/api/v1/dashboard.py`, the R332-era docstring of `_alert_series` |
| 「of those, the rows whose `status` is `open` as of this request」 | the point-key table of the R332 section, the `alerts_open` row |

The column counted 「那一档新增的行里，到本次请求这一刻 `status` 还是 `open` 的」 -- a present state plotted on a
past creation axis. The label was honest and the chart still was not: a bar for last week carrying three
unhandled alarms lost one the moment somebody clicked 确认 today, and nothing on the screen said that a past
period would rewrite itself. An employee reads that bar as 「上周还剩 3 件没处理」, which is the one sentence the
number was never saying. Labelling a当下投影 「截至今日」 is disclosure, not correction -- which is why this is a
口径 change with a wording change attached, and not a wording change.

The material to answer properly has been in the same table since migration 0014: `alerts.py` stamps
`acknowledged_at` / `closed_at` on every disposal, from one server clock (`_alert_disposal_now`, which exists
precisely so that `NOW()` never grows into the disposal clock).

### The new口径, written out

    alerts_open(B) = |{ row : created_at in B and undisposed_at(row, min(close(B), now)) }|

    undisposed_at(row, t)  ⟺  alert_row_status(row) == "open"  or  disposal_instant(row) >= t
    disposal_instant(row)  =  the earliest readable value among { acknowledged_at, closed_at }
                              (blank / NULL / absent key / unparseable ⟹ no instant)
    close(B)               =  midnight Asia/Shanghai of the first day after B, i.e. _bucket_start of the
                              next bucket -- the same half-open [start, close) a row is bucketed by, so
                              a disposal landing exactly on the edge belongs to the bucket beside it

The answer is computed by one function, `app/api/v1/dashboard.py::_alert_open_at`, and it is the only place
this module decides 「处置过没有」. `alert_row_status` is still the only status judgment in the platform: this
module reads no `status` key of its own and compares against no status literal.

| Edge (判据甲) | Seed | What that bucket answers |
| --- | --- | --- |
| ① acknowledged inside the bucket | created 2nd of last month, acked 20th of last month | does not count it |
| ② acknowledged after the bucket | created last month, acked today | **counts it** -- the row the old reading dropped |
| ③ never disposed | created last month, still `open` | counts it |
| ④ closed | the same two readings taken from `closed_at`, or from `acknowledged_at` when that came first | ①/② |

`disposal_instant` is the *earliest* of the two clocks, not the one matching the current status: a row
acknowledged in February was already answered at the end of February even if it was closed in March.

**转派 is not a disposal.** `assigned_at` is not a disposal column and `_alert_open_at` never consults it: a
reassignment says 「现在归他」, not 「有人决定了」, so a row that was only handed over still has nobody who
answered it. Counting `assigned_at` would let one 转派 empty a bucket and report 「0 件未处置」 for a week in
which nobody did anything.

### Two storage legs, one predicate

Bucketing has been Python-side on both legs since R332, because `created_at` is `TEXT` holding three shapes
and `date_trunc` over it would hand the PostgreSQL leg a period rule the offline leg does not have. R340 does
not open that exception for the disposal clock either:

- `_ALERT_SERIES_SQL` reads `created_at, status, acknowledged_at, closed_at` -- the clock travels with the row;
- no `date_trunc`, no `AT TIME ZONE`, no `NOW()`, no `to_timestamp` and no second parser appear in any SQL
  statement of this module (`test_the_replay_uses_no_second_time_parser` scans the SQL string literals and the
  one `fromisoformat` call site);
- the legs differ only in where the rows come from, and `alert_row_scope_sql` is still the row-scope cut.
  `test_both_legs_answer_the_same_series_on_the_same_seed` compares the whole response body -- every bucket,
  `undated`, key absence included -- over three worlds x month/week x a department-scoped manager and an
  administrator, against a PostgreSQL double that recognises only the three canonical disjuncts and projects
  exactly the columns named in the `SELECT`.

### The newest bucket, and `undated`, stay today's reading

- The last bucket of the window has not closed, so its horizon is `min(close(B), now)` = the request instant.
  Today's bar therefore still equals the open count `/summary` reports for the same caller, and the overview
  does not split into two口径 beside each other. Only closed buckets replay.
- `undated.alerts_open` is **not** changed by this ticket, and that is a decision rather than an omission
  (判据己): a row that recorded no period has no 「该档结束那一刻」 -- there is no bucket edge to replay it
  against. Inventing an anchor (the request instant, a file mtime, the ledger's newest row) would open a
  second口径 under the name of 「顺手统一」. The consequence a reader should know: a disposal today can lower
  the `undated` cell, and cannot lower any closed bucket. The pin that holds the line is a row whose
  `acknowledged_at` is stamped *after* the request instant -- the one shape where present reading and replay
  disagree -- and `undated` still answers the present reading (`test_the_undated_open_cell_keeps_the_present_reading`).

### Old rows, empty clocks, and the faces that did not move

- A row predating migration 0014 carries no `status` and no disposal time. `alert_row_status` answers `open`
  for it and the alert panel says the same thing on the same row, so the bucket counts it (判据丁:
  `test_a_pre_0014_row_shows_the_same_face_as_the_alert_panel`, which reads the row through `GET /alerts`).
- Empty string, `NULL` and an absent key are one face on both legs, and neither leg raises for them.
- A `acknowledged_at` that is not a time leaves the row with no readable clock; it falls back to the present
  reading and answers 200. R340 opens **no** new refusal: the 422 `validation_error` and 503
  `storage_unavailable` faces are byte-identical to the base version, `tests/test_r142_error_code_table_sync.py`
  and `tests/test_error_code_vocabulary.py` are untouched, and no migration or backfill runs.

### Conservation, stated for the new column

R342's law does not move, because the `alerts` column does not move: `sum(bucket.alerts) + undated.alerts`
still equals the rows this caller's scope covers, which is what `/summary` reports. `alerts_open` gets its own
law, and it is a bound rather than a second total -- the replayed column counts a row in the bucket it was
born in, as of that bucket's edge, so summing it across buckets answers no present-tense question and the
client must not do it:

    0 <= bucket.alerts_open <= bucket.alerts                      (every bucket, pinned)
    sum(bucket.alerts_open) + undated.alerts_open <= visible rows  (= the same total as above)

The upper bound is reachable, not decorative: a bucket in which nobody disposed anything answers
`alerts_open == alerts` (`test_the_upper_bound_is_reachable`). The 「某档 alerts_open > alerts」 overhang is
pinned red in every seeded world.

### The screen says what the server now computes

改口 ships in the same ticket as the arithmetic (判据乙), so no surface keeps the retired sentence while the
server has moved:

| Surface | Was | Is |
| --- | --- | --- |
| `frontend/src/components/DashboardPanel.vue` column header | 「其中未闭环（条）」 | 「其中当时未闭环（条）」 |
| `frontend/src/lib/dashboard.js` `TREND_ALERTS_OPEN_NOTE` | 「按这次请求时刻的处置状态计算……事后回看可能对不上」 | 「按每一档自己结束的那一刻计算……不会回头改写它」, plus the two admissions below |
| `frontend/src/lib/dashboard.js` `TREND_ALERTS_DENIED_NOTE` | names the column 「其中未闭环」 | names it 「其中当时未闭环」 |

The note also states the two exceptions out loud rather than leaving them to be inferred: the newest bucket
has not closed and is measured at the request instant, and the 「没有期间」 cell is still today's reading. The
R341 card pins are updated in the same breath and now *refuse* the old wording
(`r341-trend-card.test.js` asserts 「事后回看」 never reaches the screen), and
`r341-trend-contract.test.js` pins the sentence literally -- comparing a constant against its own name cannot
prove the words moved.

### What this does not claim

- Historical bars already drawn will read *higher* than they did, for any bucket whose rows were disposed
  after it closed. That is the same set of rows being counted honestly for the first time, not data being
  rewritten; the ticket writes no row.
- A disposal stamped after the request instant (hand-written row, clock skew -- `_alert_disposal_now` cannot
  produce it) reads as 「尚未处置」 at every earlier instant, so today's bar can sit one above the panel's open
  count while such a stamp is in the table. Stated rather than patched, because clamping the future stamp
  would be a second opinion about which clock is wrong.
- `/summary`'s `alerts` tile and `GET /alerts` are untouched: `unread` is still 「how many of my visible rows
  are unread」 and the ledger still shows the current `status`. Only the trend column moved.
- Nothing about replayability of `documents` / `documents_ready` / `datasets` is claimed here -- those three
  count creations, which never change. `alerts_open` was the one column whose value depended on when you asked.

### Pins

- `tests/test_r340_replayable_alerts_open.py` (47): the four edges ①--④ plus 「acknowledged then closed
  replays from the earlier stamp」 and 「a reassignment is not a disposal」; the symptom itself
  (`test_acknowledging_today_does_not_rewrite_any_closed_bucket`, which requires the whole series to come back
  byte-identical after a 确认); today's bar equals today's open count; the Monday edge and its half-open
  tie-break; the two-leg equality over three worlds x two periods x two readers; the `SELECT` list; the
  no-second-parser scan; the pre-0014 face read through `GET /alerts`; the no-second-status-rule AST pin;
  blank/NULL/absent/garbled as one face on both legs; the per-bucket bound and the visible-total bound; the
  `undated` cell keeping the present reading; contract-and-screen改口; key set unchanged; 422 unchanged;
  detail-literal set equal to the base version read out of `git show e9aac2f`.
- `tests/test_r332_dashboard_trend.py` and `tests/test_r342_trend_undated_exit.py`: 46 passed, unedited. The
  R342 conservation measurements do not move because the `alerts` column did not move, and its `alerts_open`
  equation still holds for its own seed -- every dated row in that seed lives in the newest bucket, whose
  horizon *is* the request instant.

## The receipt caps reason classes too, and the delete audit reads its owner through the one helper (2026-09-27, R353 / R354)

Two half-finished clauses from the previous shift, closed in one go. Neither adds a key, a code, a lookup,
a row, or a column.

### R353 · `pdf_extraction.degradation_note` has a second cap, and the over-cap face says so

R347 merged the pages: `chat.PDF_DEGRADATION_PAGE_LIST_CAP = 10` page numbers per reason group, 300 pages
of one reason down from 6,802 characters to 62. It left one face open. When every degraded page carries a
*different* reason, each group holds one page, the merge compresses nothing, and the note took the identity
path: `report.degradation_sentence` shipped verbatim. That is no longer repetition, but it is still a
length that grows one sentence per reason class -- 400 distinct reasons, 400 sentences. The old problem
had only moved from "the same sentence 300 times" to "300 sentences, once each".

| today's shape | |
| --- | --- |
| class cap | `chat.PDF_DEGRADATION_REASON_GROUP_CAP = 10` reason groups listed one by one, declared next to the page cap and written the same way |
| over the cap | the first `M` groups are rendered by the same `_degradation_segment` template R347 introduced, then the note closes with `；另有 N 类原因未逐条列出` |
| `N` | the true remainder (`len(groups) - len(shown_groups)`), never the number that was drawn, and never zero: at or under the cap the tail is the empty string, not `另有 0 类` |
| no fake finish | no ellipsis, no `等等`, no `以此类推`. An omission has to be counted, because "we stopped listing" and "there is nothing more" read the same to a client that trusts this field |
| identity path | `report.degradation_sentence` is still shipped verbatim, and is now only reachable when nothing was omitted *and* every group holds one page -- the case R347 measured as "the merge has nothing to compress" |
| still two tiers | the head still comes from `ocr_available`: `loader.DEGRADATION_NOTE_PREFIX` or `ocr.ENGINE_UNAVAILABLE_NOTE`. Capping classes does not squeeze the tiers into one sentence |

The bound is computed, not observed. `_note_char_bound` in
`tests/test_r353_degradation_note_caps_reason_classes.py` adds the pieces up: the fixed head, one `：`, at
most `M` segments, `M-1` `；` separators, and the closing sentence. Each segment is itself a maximum built
from the code's own literals -- `第`, up to `cap` page numbers each as wide as the widest page number in
the account, `、` separators, `页`, the `，另有 n 页未列出` tail at its widest digit count, `：`, and the
widest reason string. Every term is a maximum over the account being rendered, so the inequality holds for
any input rather than for today's corpus. Two of its teeth are the unglamorous ones: widening either cap
has to widen the bound, and growing only the *omitted* class count has to move it by the digits of `N` and
nothing else. A `len(note) < 5000` reading would have recorded one measurement and rotted the first time
the sentence template changed, so there is none in the file.

What the bound does **not** claim, said here so nobody reads it as a constant: it is a bound per class, so
one pathologically long reason still contributes its own length. The cap bounds *how many reasons get
recited*, not how long a reason the loader may write -- which is exactly the shape R347's page cap already
had.

`app/rag/loader.py` is untouched, line for line. The per-page account is still the only source of truth:
`degradation_notes` keeps one entry per degraded page and `ocr_degraded_page_numbers` is still the complete
list of broken pages, so "which pages failed" stays askable after the cap. That is the clause R347 wrote
(逐页那本账仍是唯一事实源，不许有人顺手把「哪几页坏了」永久问不出来), and a length cap that let the whole
note go silent would have quietly repealed it. Knife 3 of this ticket sets the class cap to 1 and re-reads
the page-level book for exactly that reason: the receipt gets shorter, the page account does not lose an
entry.

Physical lines: `app/api/v1/chat.py` 4761 -> 4790 (+36 / -7). `app/rag/loader.py` untouched.
This section is appended and deletes nothing.

### R354 · `DELETE /api/v1/data-files/{filename}` reads its owner through the same helper

R337 wired `_dataset_row_owner_id` into the two exits it named (the upload receipt, `/preview`) and forbade
a direct `.owner_id` at those two sites. A third reader of the same fact sat outside that net because it
answers into the audit journal rather than into a response: `delete_data_file` built its `before_summary`
from a direct `record.owner_id`, so a legacy row whose registry cell holds the raw `""` answered `null` in
the receipt and `""` in the journal. Two books, one fact -- and the empty-string one is the book that gets
queried during an incident review.

The delete leg now assigns through the same reader, in the same shape as the other two exits:

```
owner_id = _dataset_row_owner_id(record)
before = {
    "filename": record.filename,
    "owner_id": owner_id,
    ...
```

| what moved | what did not |
| --- | --- |
| `before_summary.owner_id` for an unowned row: `""` -> `null` | the audit event schema: the same five keys in the same order (`filename`, `owner_id`, `department_ids`, `classification`, `size_bytes`) |
| one more reader of the one helper | no new stable code, no new HTTP status, no change to the delete response body |
| the ruler got stricter | no second owner-reading implementation, and no fresh registry lookup opened to feed the audit cell |

**In the journal, an unowned row is now `null`, not the empty string.** `audit._summarize` keeps the key
and projects the value as JSON `null`, so "nobody is on record" is one answer on both books. The key is
not dropped: an absent cell reads as "this row was never looked at", which is a different claim from "no
owner'. Nothing in this repository reads that cell as an empty string; the only consumer of
`before_summary` in a test asserts a *non-empty* owner (`tests/test_resource_delete_cascade.py`) and is
unaffected. Reported, not fixed: a deployment whose own tooling pinned `before_summary.owner_id == ""` for
legacy rows needs a data question answered first, and this section does not pretend to have answered it.

One asymmetry is left standing on purpose, and this section must not be read as claiming full coverage.
The *third* book is `resource_scope`: `app/common/audit.py::_project_scope` drops keys whose value is
blank, so for an unowned row `resource_scope` has no `owner_id` cell at all. `before_summary` and
`resource_scope` therefore still answer "who owns this" differently -- `null` versus "absent". Unifying
them is another ticket with its own ruler;
`tests/test_r354_delete_audit_shares_the_owner_reader.py` pins today's reading so the next shift cannot
write "the journal now says null everywhere".

### The ruler upgrade, and how strictness was measured instead of asserted

`tests/test_r337_owner_receipt_on_both_exits.py` grew a second layer; nothing was removed from the first:

- `EXIT_SHAPE` gains a third entry, `delete_data_file` (source object `record`, the five audit keys in
  order). The `upload_excel` and `preview_data_file` rows are unchanged, word for word.
- `module_owner_read_violations` is new and scans the whole module: any `.owner_id` attribute read, or any
  `["owner_id"]` subscript read or write, outside `_dataset_row_owner_id` is a violation, and any
  owner-keyed dict literal must fill that cell from a direct call of the helper or from a name holding its
  return value. The first layer asked "did the two named exits use the helper"; the second asks "is there
  any path anywhere that reads an owner without it". That is the promotion this ticket was given, and it
  is a superset of the old question, not a replacement.
- Strictness is read off disk, not argued: the base text of `app/api/v1/data.py` (`git show a7ac040:...`)
  must produce violations naming `delete_data_file` and `record.owner_id` while the delivered text
  produces none; and the old two-exit roster, replayed against that same base text, reports zero. That
  gap is exactly what this ticket closed, so the fix cannot be re-described as "a pin was already there".
- The six R337 knives were re-run one by one after the upgrade and read the same as before it (6 / 6 / 2 /
  8 / 1, plus the reconciliation case, which still compares 13 bodies byte for byte and still reads
  `get_active_by_filename 25 == 25` and `authorization_decision 21 == 21`), and the four R310
  counter-evidence anchors still hit `data.py` exactly once each. "Only tightened, never loosened" is
  those readings; no assertion in that file was deleted.

Physical lines: `app/api/v1/data.py` 599 -> 600 (+2 / -1). The audit event schema, the stable-code
register, and the delete response body are unchanged.


## The alert surface refuses a store that is not there (2026-09-27, R359)

`app/api/v1/alerts.py` was the last of the four customer-visible read surfaces still answering a storage
refusal with an empty collection. R356 ruled it for `GET /users`; `/dashboard` already answers
`503 storage_unavailable` (`app/api/v1/dashboard.py:143`) and so does the inbox
(`app/api/v1/notifications.py:161`). What `GET /api/v1/alerts` did instead, on a customer machine whose
PostgreSQL is not up or whose migrations have not run: read the process-local `_MEM_ALERTS` -- which is
always empty on such a host -- and answer `200 {"alerts": []}`. The panel drew that literally
(`frontend/src/lib/alerts.js::ALERTS_EMPTY_TITLE`, 「当前没有触发中的告警」). A deployment gap was being
translated into a business all-clear, on the one screen that may not say the wrong thing.

### One gate, two faces

`app/api/v1/alerts.py::_require_ready_store(operation)` (`:64`) is the whole addition. It asks two questions
the module already knew how to ask, and answers a third:

- 「Is the store there?」 -- `_database_available()` (`:55`), the module's only reader of
  `app.common.auth._db_ready`. **No second probe, and no new reader of that flag**: `app/common/auth.py:231`
  keeps that count, and `tests/test_r246_honest_readiness_claims.py` counts it off the AST.
- 「Is this a production install?」 -- `_is_production_environment()` (`:60`), unchanged, still the only
  `APP_ENV` read in the module.
- Both true => `raise HTTPException(status_code=503, detail="storage_unavailable")`. **Zero new error
  codes**: the same word the three exits above already emit, already a member of `ErrorEnvelope.code`,
  already given a sentence by `frontend/src/lib/errcodes.js` (`retryable: false` -- a migration has to be
  run, retrying the request cannot produce it).

The development leg is **not** tightened, deliberately. On bare metal the in-process store is today's
legitimate backend -- `_ensure()` builds tables for it -- so that branch's response, its shape, its row
count and its ordering are byte for byte what they were before this section. What changed is that the two
faces are now separable: 「this install has no database」 and 「this company has no anomalies」 no longer
render as the same screen. A ticket that killed the development leg would be telling the opposite lie, and
`tests/test_r359_alerts_refuse_a_store_that_is_not_there.py` has pins pointed at both directions.

### Every leg passes it: the nine exits

| # | Exit | Function (line) | Answer before, production + no store | Answer after |
| --- | --- | --- | --- | --- |
| 1 | `GET /api/v1/alerts` | `list_alerts` (`:1003`), gate at `:1012` | `200 {"alerts": []}` | `503 storage_unavailable` |
| 2 | `GET /api/v1/alerts/{id}` | `get_alert` (`:1050`), gate at `:1059` | `404 resource_not_found` -- a row that exists in PostgreSQL is reported as missing | `503 storage_unavailable` |
| 3 | `GET /api/v1/alerts/rules` | `list_rules` (`:976`), gate at `:978` | `200 {"rules": []}` | `503 storage_unavailable` |
| 4 | `POST /api/v1/alerts/check` | `check_now` (`:1038`), gate at `:1041` | `200 {"triggered": [], "scan_scope": {...}}` -- a sweep that could not store anything | `503 storage_unavailable`, and `evaluate_all` is not entered |
| 5 | `POST /api/v1/alerts/rules` | `create_rule` (`:946`), gate at `:950` | `200 {"id": n, "status": "ok"}` -- 「ok」 against a row that exists only in this process | `503 storage_unavailable` |
| 6 | `DELETE /api/v1/alerts/rules/{id}` | `delete_rule` (`:988`), gate at `:990` | `200 {"status": "ok" \| "not_found"}` against the same process-local list | `503 storage_unavailable` |
| 7 | `POST /api/v1/alerts/{id}/ack` | `acknowledge_alert` (`:1072`) -> `_dispose_alert` (`:598`), gate at `:613` | `200` with a 「disposal」 written onto a memory row, or `404` for a row the store holds | `503 storage_unavailable` |
| 8 | `POST /api/v1/alerts/{id}/close` | `close_alert` (`:1083`) -> same helper | same | `503 storage_unavailable` |
| 9 | `POST /api/v1/alerts/{id}/assign` | `assign_alert` (`:1094`) -> same helper | same | `503 storage_unavailable` |

Exits 7-9 share one helper, so they share one gate call -- three separate calls would be three doors to
forget. The gate sits **after** `_require_alert_management` in all nine and **before** `_ensure()` /
`_conn()` in all nine: an unauthorised caller gets 401/403 as before and can never use the status code of a
refusal to learn whether this customer has started PostgreSQL.

### What did not move

- The development branch of every leg: `_MEM_ALERTS` / `_MEM_RULES` reads and writes, `alert_row_visible`
  row scope, the `islice(..., 100)` page, the reversed ordering, `alert_ledger_row`'s eight disposal columns.
- `evaluate_all` (`:814`) itself. It is shared with the scheduler (`app/scheduler/jobs.py`), it is pinned
  never to raise by `tests/test_r345_unreadable_data_files_are_counted.py`, and it has no HTTP response to
  lie about -- the sweep's HTTP face is `check_now`, which is gated.
- `daily_report`, the row-scope predicate pair, the disposal state machine, the audit ledger
  (`_audit_alert_denial` records refusals of *permission*, and a 503 is not one: this ticket adds no audit
  row and logs one `logger.warning` naming which leg refused).
- The three error codes already used by the disposal exits (`resource_not_found` / `conflict` /
  `validation_error`) and every status code in this module.

### Pins

- `tests/test_r359_alerts_refuse_a_store_that_is_not_there.py` (112): the nine exits refusing one by one;
  no read leg answering an empty collection; no write leg answering success or writing to memory; the
  refusal landing before any `_conn()` / `_ensure()`; every production spelling (`production`, `prod`,
  `PRODUCTION`, ` Production `) refusing and every non-production one answering; the development leg's
  exact 200 payload, its 100-row cap and its column set; production *with* a store still answering all
  nine from the store and never from memory; 401/403 unchanged; the refusal carried by direct calls too;
  and three structural pins -- the route roster, 「every route reaches the gate along the call graph」,
  and 「the gate is wired after the authorization gate」 off the AST.
- Error-code accounting (判据丁): a R332-shaped AST pin now reads every static `detail=` in `alerts.py`,
  resolving module-level constants as well, and asserts each is an `ErrorEnvelope.code` member. The
  interpolated one (`create_rule`'s 400 「非法操作符: ...」) and the parameterised ones
  (`decision.reason_code`, `_refuse_alert_disposal(code=...)`) are pinned as a closed roster of exactly
  those three sites, so a fourth `detail` cannot hide from the table; the codes that arrive as arguments
  are checked at their call sites instead. `tests/test_r142_error_code_table_sync.py` and
  `tests/test_error_code_vocabulary.py` were run and needed no edit -- zero new codes is what makes that
  true, and it is checked, not asserted.
- Five knives were run on disk against `app/api/v1/alerts.py` and restored by sha256
  (`8cb54e349391828d8340673284fa1dfa49b0d040d0e3320da3184cc23af6e2cd`, re-verified after every knife). Both
  directions are covered: neutering the gate reddens **41**; refusing in development too reddens **23** in
  this file **and 47 across five pre-existing alert files** (`test_alert_route_authorization`,
  `test_alert_scan_scope`, `test_r176_alert_row_scope`, `test_r251_alert_disposal`,
  `test_r345_unreadable_data_files_are_counted`); opening every side door but the list reddens **40**;
  letting the write legs pretend success reddens **19**; moving the gate in front of the authorization
  gate reddens **2** (one behavioural, one AST). Knives 1, 3 and 4 leave the pre-existing family green
  -- today's net has no cell for 「production without a store」, which is the hole this ticket closes.

### Registered, not fixed

- **`app/notifications/sources.py:151`** folds only `403` into a named 「this leg is omitted」 answer and
  re-raises anything else, and `app/notifications/inbox.py:161` folds only `401/403/404` in `can_address`.
  Both call these legs *directly* (`list_alerts` / `get_alert`), which is the single-definition contract this
  section keeps -- so on a production host without a store the inbox now answers `503 storage_unavailable`
  instead of a 200 whose alert leg was silently empty. Defensible, but the narrower answer is available:
  `_omitted(SOURCE_ALERT, "storage_unavailable")` is one line in that owner's file, and `frontend/**` plus
  that module are outside this ticket's write set. Ruled by the controller, not here.
- **`app/api/v1/dashboard.py:174-182`** (`_alert_counts`) reads `alerts._MEM_ALERTS` itself whenever
  `_database_available()` is false, so the overview page's 「N 条告警」 tile is still `{"total": 0,
  "unread": 0}` on the same broken install -- it never goes through `GET /alerts`, so this gate cannot reach
  it. Same for the trend tile's alert leg (`:477`). That file is R342's write set.
- **Three `RuntimeError("... is required in production; run migrations first")`** in this module (`:88`
  table missing, `:98` `alerts.department`, `:541` `alerts.status`) still surface as a bare 500
  `internal_error`, which `frontend/src/lib/errcodes.js:114` renders as 「请稍后重试」 -- a deployment gap
  described as a transient. Evidence for the controller, unadjudicated here: only the `:98` sentence is
  pinned by message text (`tests/test_r184_alerts_department_column.py:420`, plus a looser
  `match="run migrations first"` at `tests/test_r176_alert_row_scope.py:469` and a source-text pin at
  `tests/test_r184_alerts_department_column.py:205`). **Nothing pins `:88` or `:541`** -- the phrase exists in
  `tests/test_r98_checkpointer_backend.py:279` and `tests/test_bootstrap_admin.py:107`, but those drive other
  modules. So two of the three sentences could be reworded today without a test noticing.
- `create_rule`'s interpolated `detail` stays as-is: changing it is a response-body change, not a
  storage-face change. Pinned as an exact roster of three sites so it cannot quietly grow a fourth.
- **The alerts screen will offer 「重新加载」 for this 503.** `frontend/src/lib/alerts.js::readFailureView`
  hardcodes `retryable: true` on its generic error branch (`:141`) while `frontend/src/lib/errcodes.js:105`
  says `storage_unavailable` is `retryable: false` -- the alerts panel is the one place the two disagree,
  and `isRetryable(err)` already exists for it to read (that is what `ApprovalPanel.vue:173` does). One
  line, in a file this ticket may not touch. The empty-state copy needs nothing: a 200 with an empty list
  now genuinely means 「this store answered, and it holds nothing」, which is what
  ALERTS_EMPTY_DESCRIPTION already says.

## The alert leg may refuse without taking the inbox down with it (2026-09-27, R366)

R359 put `_require_ready_store()` in front of the nine alert exits, and that direction stands -- this section
walks none of it back. What it closes is the collision R359 itself registered under 「Registered, not fixed」:
`app/notifications/sources.py::alert_candidates` and `app/notifications/inbox.py::can_address` call those
endpoints *directly* (the single-definition choice R299 made, so the resource gate, the row predicate and the
row projection each keep exactly one definition), and each of the two folded only a narrow set of statuses --
the read leg folded `403`, `can_address` folded `401, 403, 404`. The new `503` fell straight through both and
out of the route. On a customer machine whose PostgreSQL is not up, `GET /api/v1/notifications` therefore went
from 「200 whose alert leg is quietly empty」 to a whole-page `503 storage_unavailable`: one leg could not be
asked, so all three tiles went dark. That is a worse answer than the one R359 replaced, because it destroys
the two readings that were still true.

### The read side: one absence, registered in the shape that already existed

`app/notifications/sources.py:162` adds a second folded status beside the first, in the same one-line shape.
Nothing else in the function moved:

| status | what happens | what the caller reads |
| --- | --- | --- |
| `403` | folded into `_omitted(SOURCE_ALERT, exc.detail)` | 「you have no right to this class of ledger」 -- `reason_code: permission_denied`, the branch R299 wrote, byte for byte untouched |
| `503` | folded into `_omitted(SOURCE_ALERT, exc.detail)`, non-string detail falls back to the literal `storage_unavailable` | 「this cell is not supplying data, because the store will not answer」 -- `reason_code: storage_unavailable`, new in R366 |
| anything else | re-raised | unchanged: a 500 stays a 500, it is not folded into anybody's absence |

The refused leg's projection is exactly what `_omitted` already produced -- `sources.alert` =
`{"included": false, "reason_code": "storage_unavailable", "candidates": 0, "scanned": 0, "truncated":
false}` -- five keys, none added, none dropped.

**「This cell is not supplying data」 and 「there is really nothing here」 stay two sentences.** The 503 is not
folded into an empty bundle, not into `items=[]` with `included: true`, not into 「no new items」. Doing that
would move the lie R359 was written to kill into the inbox instead of killing it. The pin reads one seeded
world twice -- 「the only open alert has been closed, store answering」 against 「store refusing」 -- and
requires the two projections to differ, and a second pin requires that the refused leg does not launder
`_MEM_ALERTS` into a 200 (the row is absent *and* the reason says why).

**Zero new error codes, zero new reason strings.** The value carried is the one the alert module emitted; the
fallback literal is `storage_unavailable`, already emitted at `app/api/v1/dashboard.py:150`,
`app/api/v1/notifications.py:161`, `app/api/v1/chat.py:3037`, `app/api/v1/auth.py:105`, and already a member
of `app/agents/contracts.py::ErrorEnvelope.code`. No fourth ledger such as `alerts_unavailable` exists.
Neither file gained a probe of its own -- no read of `_db_ready`, no second `_database_available()`, no new
`HTTPException` outlet -- and that is pinned off the AST rather than promised, because 「the same three faces
the alert leg can carry」 is checked against `ErrorEnvelope`, not against this file's own literals.

Everything else on the page reads the same words it read before this ticket, in the same seeded world: the
`approval` and `document` leg projections and their row payloads, `is_exact`, `state`, `limit`, `offset`.
`total` / `unread_total` / `returned` / `unread_returned` each move by exactly the number of alert rows the
refusal took away -- no more, no less -- and `is_exact` is not flipped to `False` to make the absence 「look
counted for」: the absence has its own field, and a cut window has another.

### The write side: `can_address` is not allowed to guess

`app/notifications/inbox.py:161` sees the same status and deliberately does **not** fold it. That leg answers a
question -- 「is this alert still open, and may this person act on it」 -- and the two possible 「no」 answers
are not interchangeable:

- `404` is 「this row is not there any more」. The leg returns `False`, which is the right verb: the todo is
  over. `401` and `403` share that face on purpose (R299: someone else's alert and a nonexistent alert must
  not look different, or alert numbers become probeable). That tuple is still `401, 403, 404`, edited by
  nobody in this ticket, and its branch is a different statement from the one below.
- `503` is 「this machine cannot ask right now」. The leg re-raises, and the route answers
  `503 {"detail": "storage_unavailable"}` -- the code `POST /notifications/read` and `/dismiss` already emit
  when their own state ledger is missing.

`503` must not share that return `False` with `404`. Folding it would print 「not addressable」 on the receipt of a todo that is
still open somewhere the server cannot currently see, and a swallowed todo is the same translation error one
level down: 「cannot ask」 drawn as 「resolved」. The separation is pinned twice over -- once off the AST (the
`503` branch body is one bare `raise`; the `404` branch body is `return False`; the two are not the same
node; a fifth status in either list reddens the roster) and once end to end (a dismissal of an open alert on
that machine gets a 503 and writes no reader state; a dismissal of a genuinely gone alert gets a 200 whose
per-id receipt says `notification_not_addressable`). The other two legs keep working while the alert leg
refuses: in that same production-without-a-store world, dismissing an approval row still answers 200 with
`changed: true`.

Why the write side keeps a refusal while the read side folds one: they answer different questions. The list
page can say 「this class is not supplying data, here are the other two」 and stay useful. A write cannot
verify what it is about to overwrite, and there is no partial success to hand back -- 「I could not check」 is
the only honest receipt, and it is a code the route already speaks.

### Evidence and boundaries

`tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py` (24 pins, all offline: no service, no
PostgreSQL, no model port, no `chroma_db/` write). Three legs are seeded once -- an approval round, one open
alert, one indexed document -- and 「no store」 is produced the way a customer machine produces it, by
`APP_ENV=production` meeting a `_db_ready` that is false, so the gate under test is R359's own and not a
substitute. Three knives were then run on disk against these very bytes and restored by sha256 --
`sources.py` `0c618dadfe463f49792b397ab86d16a1acaae0a9ed3af9add691ab847ec28545`, `inbox.py`
`75f97367c1d2a02fe90c390c9aae8109bf50c9d3ef9429b91466f1f550bd8423`, both re-measured after every knife:

- (1) lifting the `503` out of `alert_candidates` reddens **11** of the 24 new pins: the 200 itself, the
  omitted shape, the two-faces comparison, the count arithmetic, the code-equality pin, the AST roster.
  The 162 pre-existing pins in `test_r299_notification_inbox`, `test_r303_notification_pins` and
  `test_r359_...` stay green -- that net has no cell for 「production inbox without a store」, which is the
  hole this ticket closes, not a coincidence.
- (2) folding the `503` into 「an empty bundle with no registered absence」 reddens **8**, including the two
  pins whose entire job is to keep 「not supplying data」 apart from 「nothing here」. Not passed over.
- (3) letting `can_address` treat `503` like `404` (one merged branch, `return False`) reddens **3**: the
  AST branch-roster pin, the direct-call pin, and the end-to-end pin that reads the 503 receipt instead of
  a 「not addressable」 line.

Physical lines: `app/notifications/sources.py` +11 / -0, `app/notifications/inbox.py` +7 / -0.
`app/api/v1/alerts.py` is not touched by this ticket -- the gate, its nine call sites and their position behind
the authorization gate are R359's, unchanged.

Out of this ticket's write set, registered rather than fixed:

- `app/notifications/states.py` has no production branch. With `_database_available()` false, both
  `recipient_states` (`:94-100`) and `apply_state` (`:146-155`) read and write `_ROWS`, the process-local
  overlay, whatever `APP_ENV` says. So the 200 this section promises keeps 「who has read what」 in a table
  that dies with the process, and the write receipt will still report `changed: true` against it. That is the
  same class of sentence R299 pinned for the three business ledgers, in the one notification file that was
  not in scope here.
- The overview page still answers `{"total": 0, "unread": 0}` for the alert tile on exactly this machine:
  `app/api/v1/dashboard.py:181-189` reads `alerts._MEM_ALERTS` itself instead of going through `GET /alerts`,
  so R359's gate cannot reach it (same for the trend tile's alert leg). R367.
- `frontend/src/lib/notifications.js` never reads the `sources` projection at all -- `git grep included
  frontend/src` is empty on the day this section lands -- so a folded absence is rendered as 「fewer rows」,
  which is the honest server answer wearing the dishonest client face. And `frontend/src/lib/alerts.js:141`
  hardcodes `retryable: true` on its generic failure branch where `frontend/src/lib/errcodes.js:105` says
  `storage_unavailable` is not retryable. Both are R368 (frontend write set).


## The overview screens refuse a store that is not there (2026-09-27, R367)

R359 closed one face of this bug and registered the other two in its own 「Registered, not
fixed」: `app/api/v1/dashboard.py` does not go through `GET /alerts` -- it reads the alert ledger
itself. So on the same broken customer host (PostgreSQL not up, or the migrations not run) the
overview still answered in numbers that had no source:

| Screen | Leg | Production + no store, before | After |
| --- | --- | --- | --- |
| `GET /api/v1/dashboard/summary` | `_alert_counts` -> `alerts._MEM_ALERTS` | `200` with `"alerts": {"total": 0, "unread": 0}` | `503 storage_unavailable` |
| `GET /api/v1/dashboard/summary` | `_pending_count` -> `pending_approvals.open_items` -> `_MEM_ROWS` | `200` with `"pending_approvals": 0` | `503 storage_unavailable` |
| `GET /api/v1/dashboard/trend` | `_alert_series` -> `alerts._MEM_ALERTS` | `200`, every `alerts` / `alerts_open` bar at `0` | `503 storage_unavailable` |

Those are the same sentence told three times: 「这家公司一切正常」, printed out of a store that
never answered. `_MEM_ALERTS` and `_MEM_ROWS` are process-local containers, empty on a customer
machine by construction, and nothing on either screen separates 「the ledger is empty」 from
「the ledger is not there」. R340 makes that worse rather than better on the trend card: the
bucket-edge replay is arithmetically perfect on an empty ledger, so a chart that looks like the
most careful possible reading of the past is the loudest possible lie about a deployment gap.

### One gate, three legs

`app/api/v1/dashboard.py::_refuse_unaccounted_screen(route, leg, *, database_available)` is the
whole addition, called from exactly three places -- `_pending_count`, `_alert_counts`,
`_alert_series` -- and from nowhere else. It asks two questions the repository already knew how
to ask, and restates neither:

- 「Is this a customer install?」 -- `alerts_api._is_production_environment()`, the same `APP_ENV`
  reader R359 uses. `dashboard.py` defines no second one, reads no `APP_ENV`, no `os.getenv`, and
  holds no copy of the environment roster.
- 「Is the store up?」 -- the answer of the leg that is about to be read:
  `alerts_api._database_available()` on the two alert legs,
  `pending_approvals._database_available()` on the ledger leg. Those two probes are the module
  boundaries this ticket is allowed to see; `dashboard.py` still is not a reader of
  `app.common.auth._db_ready`, which is what keeps `app/common/auth.py`'s reader ledger -- and
  `tests/test_r246_honest_readiness_claims.py`, which counts it off the AST -- untouched.
- Both true => `503 storage_unavailable`. **Zero new error codes**: it is the literal this module
  already emits for the ledger table (`_pending_count`, R13) and for an unreadable period
  (`_trend_unreadable`, R332), and it is already a member of `ErrorEnvelope.code`.

The whole screen refuses rather than one tile going quiet, and that is a shape argument, not a
mood: neither route owns a usable 「this column did not supply data」 face. `alerts` is the only
conditional key in `/summary`, and its absence is already somebody else's answer -- a 403 from
`_require_alert_management` deletes the key (R188/R332), so borrowing absence for 「the storage
did not answer」 would put two things back on one face. The other tiles are pinned from the
opposite side: R284 wrote into the route body that `documents` and `documents_ready` are always
present and always integers, because this endpoint does not get to pick which of two faces a
quiet day shows by leaving the key out. `/trend` is stricter still: a bucket of `0` asserts that
nothing was created in that period, and R332 already refused a *partial* series. So the response
as a whole answers 503, which is the family ruling of `/users` (R356), `GET /alerts` (R359), the
notification inbox (R299) and the missing ledger table (R13).

### The order the questions are asked in

The gate is the second question everywhere it stands. `intelligence._authorized` is still the
first act of both routes, so an anonymous caller gets 401 and a caller without
`resource:analyze` gets 403 on a host with no database exactly as they did on a host with one --
otherwise the difference between 401/403 and 503 becomes a probe for whether this customer
started PostgreSQL, and that is not the caller's information.

Inside the alert legs the same rule holds one layer down: `_alert_counts` resolves
`_require_alert_management` first and keeps its 403 -> `None` -> key-deleted shape untouched, and
`_alert_series` keeps `_alert_management_principal` -> `_ALERTS_DENIED` -> `None` untouched. A
staff caller on a machine whose alert store is missing therefore still gets a 200 without the
alert keys, provided the tile beside it can answer. The ledger leg is not alert-scoped, and never
was: R13 already refuses the whole screen for a staff caller whose ledger table is missing, and
this ticket's gate is the same width as the read it replaces.

### What did not move

- **Development and bare metal: nothing.** The in-process store is today's legitimate backend
  there -- `alerts._ensure()` still builds its tables on that branch -- so the 200 body keeps its
  keys, its row counts and its ordering verbatim, including the `alerts` key for a caller who
  passes the alert gate. The behaviour file pins that body by equality, in both routes, because a
  ticket that killed the development leg would be telling the same lie backwards.
- **The `PendingApprovalStoreMissing` catch stays**, at the same place, as the only exception type
  translated, with `raise ... from exc` intact. The two ledger refusals are two doors and the
  pins keep them apart: no store at all => the new gate, and `open_items` is never entered;
  store up but migration `0008` not run => that catch, and `open_items` is entered once. Widening
  it to `except RuntimeError` is refused on purpose -- a missing driver travels that same path,
  which is the reason the named exception exists.
- No key was added to either response, none was removed, no request parameter changed, no cache
  header moved. `/trend` grew no ledger leg: it does not count pending approvals, so it refuses
  nothing on the store it never reads.
- `documents` / `documents_ready` / `datasets` keep their own owners: this ticket gates only the
  legs it was assigned, and the document and dataset books answer through
  `chat.list_document_catalog` and `data.list_data_files` as before.

### The newest bucket edge (the paragraph R365 asked to have on paper)

`alerts_open` counts, per bucket, the rows created in that bucket that were still undisposed **at
that bucket's own closing instant** (R340). The rule that makes the newest bucket honest has been
in `app/api/v1/dashboard.py` since R340 and never had a contract line; it is here now, in the
same words the code uses:

- the clock is read **once per request** -- `now = _trend_now()` -- not once per row, so one
  response cannot contain two different answers to 「what is still open now」;
- a bucket's horizon is `min(_bucket_end(period, start), now)`: clamping with `min` is what stops
  the newest bar from being replayed against an instant that has not happened yet;
- so every **closed** bucket replays against its own edge, and only the bucket that has not
  closed yet -- the newest one -- replays against 当下;
- consequence, and the reason the two overview numbers still agree: the newest bar's
  `alerts_open` is what `/summary` reports as open today, while every earlier bar keeps the value
  its own rows had at the end of that earlier period. A disposal that lands exactly on a bucket
  edge belongs to the bucket beside it, because `_bucket_start` is half-open `[start, end)` and
  the disposal comparison uses `>=` for the same reason -- the two comparisons cannot disagree
  about which period an instant belongs to;
- an undated row has no bucket edge to replay against, so its `alerts_open` stays the present
  reading (R342 判据己, unchanged).

### Pins

`tests/test_r367_dashboard_refuses_a_store_that_is_not_there.py` -- behaviour, both directions:
the three legs refuse in production (`test_summary_refuses_when_the_alert_store_is_not_there`,
`test_trend_refuses_when_the_alert_store_is_not_there`,
`test_summary_refuses_when_the_ledger_store_is_not_there`,
`test_a_tile_that_did_answer_does_not_rescue_the_screen`,
`test_the_refusal_wears_the_code_the_repo_already_ships`), the development body is unchanged
(`test_development_still_counts_the_memory_ledgers_verbatim`,
`test_development_still_draws_the_memory_alert_bars`,
`test_every_non_production_name_keeps_answering`), the refusal comes after the permission answer
(`test_an_anonymous_caller_still_hears_the_permission_answer`,
`test_a_caller_without_analyze_rights_still_hears_the_permission_answer`,
`test_a_denied_alert_caller_still_loses_the_key_rather_than_the_screen`), and the two ledger doors
stay apart (`test_the_missing_ledger_table_still_refuses_through_the_pre_existing_catch`,
`test_the_two_ledger_refusals_are_two_different_doors`,
`test_the_pre_existing_catch_still_names_the_migration_it_waits_for`,
`test_any_other_ledger_failure_keeps_its_own_shape`).

`tests/test_r367_gate_shape_pins.py` -- shape: no second probe book
(`test_the_module_defines_no_second_production_or_storage_probe`,
`test_the_module_reads_neither_the_readiness_flag_nor_the_environment`,
`test_the_three_probes_the_gate_uses_already_existed_at_the_base`), one gate with three legs and
no side door (`test_the_gate_is_one_function_called_from_exactly_three_legs`,
`test_the_module_opens_exactly_the_storage_doors_it_names`,
`test_every_refusal_word_is_the_one_the_repo_already_ships`), the ordering
(`test_every_gate_call_sits_behind_its_leg_authorization`,
`test_the_alert_legs_still_answer_denial_before_storage`,
`test_the_pending_leg_gates_before_it_touches_the_ledger`,
`test_the_routes_authorize_before_any_leg_that_can_refuse`), the exact catch
(`test_the_r13_catch_is_still_the_exact_named_type`,
`test_the_module_translates_no_broad_exception_anywhere`), this section's own text
(`test_the_new_section_states_the_two_faces_and_why_absence_was_not_available`,
`test_the_new_section_carries_the_bucket_edge_paragraph_r365_asked_for`), and the append rule
(`test_the_contract_appends_one_section_and_deletes_nothing`,
`test_the_bucket_edge_words_in_the_contract_match_the_code`). The two probes this ticket refuses
to re-derive are named where they bite
(`test_the_gate_asks_the_production_question_through_the_existing_reader`,
`test_each_leg_hands_the_gate_its_own_storage_probe`,
`test_the_gate_reads_nothing_before_it_decides`), as is the environment roster it borrows instead
of copying (`test_every_production_name_refuses`) and the byte shape of every file it touched
(`test_the_files_this_ticket_touched_keep_the_repo_line_ending`).

### Registered, not fixed

- **`/summary` answers 503 before `/trend` can be asked the same question twice.** Both routes are
  covered, but by different legs: `/trend` has no ledger tile, so a production host whose *only*
  missing store is the HITL ledger still answers `/trend` with a full series. That is the honest
  shape -- that screen does not count approvals -- and it is written down because the asymmetry
  otherwise looks like an oversight.
- **The `RuntimeError("... is required in production; run migrations first")` bootstrap failures
  inside `alerts._ensure()`** stay a 500 on both screens when PostgreSQL is up and the schema is
  not, exactly as R359 registered them for `GET /alerts`. This ticket moved no error shape; only
  the `storage_unavailable` doorway is new here, and only for 「no store at all」.
- **`app/notifications/sources.py` calls the dashboard legs?** No -- it calls `list_alerts` /
  `get_alert` directly (R359's own registration). Recorded here only so the next reader does not
  look for a fourth leg: the inbox is not built on `/dashboard`, and nothing in this section
  changes what the inbox answers.

## A store that still needs its migrations answers 503 as well (2026-09-27, R371)

The section above closed with one sentence left unpinned and unfaced. `app/api/v1/alerts.py` carries three
`RuntimeError(... "run migrations first")` refusals -- positions read from base `b291324`: `:120` a missing
table (`alert_rules` / `alerts`), `:131` a missing `alerts.department`, `:573` a missing `alerts.status`.
(The `:88 / :98 / :541` in the paragraph above are those same three sentences as of R359's own base; the
roster of sentences has not changed.) Two of them had test pins. The third -- `_require_alert_disposal_schema`,
whose single call site was `_dispose_alert:635`, i.e. exactly the 「处置一条告警」 action -- had **zero pins in
the repository** (`git grep "status column" -- tests` and `git grep -l "_require_alert_disposal_schema"` both
hit `alerts.py` alone), and `git grep exception_handler -- app` hit nothing, so any of the three escaping to an
HTTP exit left FastAPI to produce an anonymous `500`: no stable code, no human sentence, and no 「run 0014」
for the operator. `alerts.py:410` said the status leg behaves 「像缺归属列一样」; the department leg had both a
tight pin and an HTTP face, the status leg had neither. That gap is what this section closes.

### The translation lives at the exit, not in the probe

Positions in this subsection are read from `app/api/v1/alerts.py` as delivered by this ticket.
`_migrations_first_at_http_exit(operation)` (`:137`) is the whole mechanism: a context manager wrapped around
the schema-touching statements inside the eight route functions that can reach one of the three sentences. It
catches **one** type and hands the conclusion to the gate that already exists:

- `AlertSchemaNotMigratedError` (`:65`) is the new name of exactly those three sentences. It is a subclass of
  `RuntimeError`, not a replacement -- the same ruling `app/storage/pending_approvals.py:140` already records:
  the existing assertions pin the base class (`pytest.raises(RuntimeError, match=...)`), so naming may only
  add a layer. **The three message texts are byte for byte unchanged**; the tight pin that matches a whole
  sentence (`tests/test_r184_alerts_department_column.py:420`) still matches.
- `_ensure()` (`:178`, raising at `:187` and `:199`) and `_require_alert_disposal_schema()` (`:632`,
  raising at `:642`) keep raising
  `RuntimeError`. They are the probe layer, and that is where the existing pins live. Converting there would
  be rewriting somebody else's ledger.
- The refusal is `503 storage_unavailable`, produced by the **existing** `_require_ready_store` gate (`:99`),
  now reachable through its `migrations_missing=True` keyword. The module still contains exactly one
  `status_code=503` raise point and it is still inside that gate: R371 borrowed the door, it did not build a
  second one. **Zero new error codes** -- the same word is already emitted by `app/api/v1/dashboard.py:150`,
  `app/api/v1/notifications.py:161`, `app/api/v1/chat.py:3037` and R359's gate, and 「the tables and columns
  are not there yet」 is exactly what that code already means.
- The capture is narrow on purpose (`tests/test_r371_the_conversion_is_narrow_and_stays_at_the_exit.py` pins
  the shape, `tests/test_r371_migrations_first_answers_503_not_500.py` pins the behaviour). A missing driver,
  or `_dispose_alert`'s 「wrote a row that cannot be read back」 (`:733`), is still a plain `RuntimeError` and
  still leaves a 500: translating every runtime error into 503 would hand a real bug an infrastructure alibi.
- 401 and 403 still come first. Every conversion sits after `_require_alert_management`, so an anonymous or
  staff-level caller still gets `authentication_required` / `permission_denied`, never a status code that
  leaks whether this install has run its migrations.

### Which sentence reaches which exit (evidence, not a blanket claim)

「All three sentences produce a bare 500」 would be false. Nine exits, three gaps:

| Exit | missing table (`:120` at base) | missing `alerts.department` (`:131`) | missing `alerts.status` (`:573`) |
| --- | --- | --- | --- |
| `POST /alerts/rules` `create_rule` | bare 500 -> `503` | bare 500 -> `503` | not on this path (200) |
| `GET /alerts/rules` `list_rules` | bare 500 -> `503` | bare 500 -> `503` | not on this path (200) |
| `DELETE /alerts/rules/{id}` `delete_rule` | bare 500 -> `503` | bare 500 -> `503` | not on this path (200) |
| `GET /alerts` `list_alerts` | bare 500 -> `503` | bare 500 -> `503` | not on this path (200) |
| `GET /alerts/{id}` `get_alert` | bare 500 -> `503` | bare 500 -> `503` | not on this path (200) |
| `POST /alerts/{id}/ack` `acknowledge_alert` | bare 500 -> `503` | bare 500 -> `503` | **bare 500, unpinned -> `503`** |
| `POST /alerts/{id}/close` `close_alert` | bare 500 -> `503` | bare 500 -> `503` | **bare 500, unpinned -> `503`** |
| `POST /alerts/{id}/assign` `assign_alert` | bare 500 -> `503` | bare 500 -> `503` | **bare 500, unpinned -> `503`** |
| `POST /alerts/check` `check_now` | swallowed at `:891` (`except Exception`, falls back to memory rules) | swallowed at `:891` | not on this path (200) |

`check_now` deliberately got no conversion: its `_ensure()` sits inside `evaluate_all`, whose broad catch is
pinned 「never raises」 by `tests/test_r345_unreadable_data_files_are_counted.py:394`, and the sweep's own
storage face is the R359 gate. Wrapping it would have installed a door that can never be reached. On the same
broken install the sweep still dies further down, at `alerts.py:928` (`SELECT * FROM alert_rules`), with a
driver error -- that is not one of the three sentences, so it is registered below instead of being folded
into this ticket.

### The three gaps stay three different jobs

All three now answer the same `503 storage_unavailable` (a closed enumeration, zero new codes), so the
response is not what separates them. What does is the sentence and, on the operator's side, one log line per
refusal naming the migration file: `MIGRATION_REQUIRED_HINTS` (`:83`) maps 「`alert_rules` / `alerts` table」
to `migrations/0003_legacy_runtime_tables.sql`, 「`alerts.department` column」 to
`migrations/0012_alert_and_pending_approval_attribution_columns.sql`, 「`alerts.status` column」 to
`migrations/0014_alert_disposal_columns.sql`; an unrecognised sentence logs `migration=unknown` rather than
staying silent. Two corrections, both read off the repository rather than off the ticket: the department
column is **0012**, not 0013 (0013 is the `pending_approvals` status vocabulary), and the 「nothing pins the
missing-table sentence」 claim in the section above was already stale at `b291324` --
`tests/test_memory_production_schema.py:83` pins it for `app.api.v1.alerts` through the `_ensure()`
parametrization at `:72` (loosely: `match="run migrations first"`, which is also why that sentence is the one
sentence in this family that may not be reworded by a message-text pin).

### What did not move

- `_ensure()`'s development branch (`:204` onward): a self-built catalogue still repairs itself in place
  (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`), answers 200, and never sees this
  ticket's face. What is separated is two faces, not one blanket 503 -- the same ruling as R359.
- The three message texts, the row-scope predicate, the disposal state machine, the audit ledger, and every
  existing pin pointed at the probe layer.
- Registered, not touched: `check_now`'s driver-level failure (`alerts.py:928`); the two direct awaits of
  `list_alerts` / `get_alert` inside `app/notifications/`, which on this install now propagate a `503`
  HTTPException where they used to propagate a `RuntimeError` (both fold only 401/403/404, so the status code
  of the alert leg reaches the inbox either way -- that module is R366's write set); the dashboard's alert
  tiles, which read `_MEM_ALERTS` directly and therefore still show 「0 条告警」 on this install (R367's write
  set). All three are one-line changes in files this ticket may not write.

Evidence layer: every case in both new test files runs against an in-memory catalogue stand-in. No PostgreSQL,
no container, no model port was touched -- so these pins prove 「what the exit answers when the probe reads a
missing table or column」, and do not prove that the migrations themselves create those objects. That leg
belongs to `tests/test_r184_alerts_department_column.py` and `tests/test_r251_alert_disposal_migration.py`.

## Either remaining leg may refuse without taking the inbox down (2026-09-27, R373)

R366 folded the alert leg and named the other two as the same black. This section closes those two, in the shape
R366 left. The inbox has **one outlet for three legs** -- `app/notifications/inbox.py::collect` awaits the three
sources in sequence and is pinned to degrade nothing itself -- so a leg that raises still takes the whole page
with it, and the customer reads 「the notification feature is broken」 while the real sentence (a table is
missing) stays in the log.

What the two legs actually do was measured on the base bytes, not read off the callee's signature:

- **approval.** `sources.py::approval_candidates` and `inbox.py::can_address` each called
  `pending_approvals.open_items` with no handler at all. `open_items` reaches
  `_items_with_status` (`app/storage/pending_approvals.py:390 -> :371`) which calls `_require_table`, and
  `_require_table:152` raises the domain error `PendingApprovalStoreMissing` (defined `:140`, deliberately a
  **subclass of `RuntimeError`**, not `Exception`). There is no `exception_handler` anywhere under `app/**`
  (`git grep -n exception_handler app` -> exit 1), so the page did not even answer in an envelope:
  `GET /api/v1/notifications` returned a **bare 500** with the plain-text body `Internal Server Error`, and
  `POST /api/v1/notifications/dismiss` the same. The same ledger and the same missing table on another screen
  answer `503 storage_unavailable` -- `app/api/v1/chat.py:3034` and `app/api/v1/dashboard.py:149` -- so one
  fact used to speak 503 in one place and 500 in this one.
- **document.** Both files also called `chat_api.list_document_catalog` with no handler. Measured: that call
  cannot today raise a storage error into the inbox, because `app/documents/catalog.py:709-724` wraps the SQL
  leg in `except Exception` and falls back to a local directory scan. So a missing table or column surfaces
  here as `sources.document` = `included: true`, `reason_code: ok`, `scanned: 0` -- not a 500, but the exact
  face this file has been refusing since R299: 「scanned, and clean」. Registered below, not fixed here; what
  this ticket closes is the boundary one level up -- if that ledger answers 503, this leg folds an absence and
  the other two keep reading.

### The read side: same door, two more legs

| leg | catches | folded into | folded roster, pinned off the AST |
| --- | --- | --- | --- |
| approval | `pending_approvals.PendingApprovalStoreMissing` -- that type only | `_omitted(SOURCE_APPROVAL, STORAGE_UNAVAILABLE)` | 「this cell is not supplying data, because that table is not there」 |
| document | `HTTPException` whose `status_code == 503` | `_omitted(SOURCE_DOCUMENT, exc.detail)`, non-string detail falls back to the same word | exactly `{503}` |
| alert | (R366, untouched) | `_omitted(SOURCE_ALERT, ...)` | exactly `{403, 503}` |

The absence is registered through the `_omitted` helper that already existed. Five keys, none added, none
dropped: `sources.approval` = `{"included": false, "reason_code": "storage_unavailable", "candidates": 0,
"scanned": 0, "truncated": false}`, and `sources.document` in the same shape.

**Zero new error code, zero new reason string.** The word folded in is `storage_unavailable`, already emitted by
`app/api/v1/chat.py:3037`, `app/api/v1/dashboard.py:150` and `app/api/v1/notifications.py:161` for exactly this
fact, and already a member of `app/agents/contracts.py::ErrorEnvelope.code`. R373 hoists the literal R366 had
written inline into one module constant `STORAGE_UNAVAILABLE` (`app/notifications/sources.py:56`) so the three
fold sites reference one definition; the literal's occurrence count inside that file is 1 before this ticket and
1 after it, and a pin reads that count off the file rather than trusting the prose. Every value any leg can put
in `reason_code` is checked against `ErrorEnvelope`, not against this ticket's own strings: the reachable set is
exactly `ok` / `permission_denied` / `storage_unavailable`.

**An absence and a quiet ledger stay two sentences**, one pin per leg, each reading one seeded world twice.
Approval: 「the ledger is answering and this owner has nothing pending」 = `included: true, reason_code: ok,
candidates: 0, scanned: 0` against 「the table is gone」 = `included: false, reason_code: storage_unavailable`.
Document: 「this mailbox really has nothing indexed」 (a second recipient over the same seeded directory)
against 「the catalog refused」. Neither is folded into the other; `is_exact` is not flipped to `False` to make
an absence look counted for, and a refused read writes no reader state.

**The permission branch is not merged with the storage branch.** The document leg's roster is *derived* and
pinned to exactly `{503}`: a `403` or `401` out of that ledger still propagates with its own status and detail
and is never dressed as 「this cell is not supplying data」; the alert leg's tuple in `can_address` is still
`401, 403, 404`, edited by nobody here; a `staff` caller still reads `permission_denied` on the alert tile even
while the approval ledger is missing. Knives 1 and 3 redden on this: merging `403` into the document roster
reddens the face pin and the roster pin, and lifting the approval fold back out reddens ten.

### The write side: 「cannot ask」 is not 「not yours」

`app/notifications/inbox.py:151` asks 「is this round still pending for this person」. With the table gone, the
honest answer is 「cannot be asked」, so the branch re-raises the domain error -- a bare `raise`, pinned off the
AST (its statement body is exactly one `Raise` with no expression, and `can_address` carries exactly three
handlers: the `int(source_id)` guard, this one, and R366's `HTTPException` one). Returning `False` would render
a still-pending approval as `notification_not_addressable` and close the todo -- the same silent swallow R366
refused for a still-open alert. The document branch gained **no** handler at all, pinned structurally: a 503 or
401 out of the catalog propagates, it is not folded into 「not addressable」.

What the customer sees on that path is still a `500`: the outlet `app/api/v1/notifications.py` translates only
`NotificationStateStoreMissing` into `503 storage_unavailable` (`:159` in `_apply`, `:190` in
`list_notifications`) and translating a second ledger's error is that file's call, outside this ticket's write
set -- registered below. The pins therefore assert 「not a 200, no `results` receipt, no reader state written」
instead of hardcoding `500`: when the outlet adds its two lines, nothing here turns red, and the laundering
knife (4) still reddens three.

### Evidence and boundaries

`tests/test_r373_the_two_remaining_legs_answer_absence.py` -- 39 pins, all offline (no service, no PostgreSQL,
no model port, no `chroma_db/` write). Three legs are seeded once -- one pending approval round, one open alert,
one indexed document. 「That table is gone」 is produced the way `tests/test_hitl_pending.py:697 _no_table`
produces it: `_database_available()` true and a stub connection whose `to_regclass` answers `NULL`, so the
exception under test is the ledger's own and not a substitute. 「The catalog refused」 is produced by the one
face that ledger can emit -- a `503` whose `detail` is the code itself -- and this ticket says plainly that
`chat.py` does not emit it yet, which is why the document-leg pin is a boundary and not a bug reproduction.

Four knives, run **on disk** against these very bytes and restored by sha256 -- `sources.py`
`c00354a8ddf2b77e23c0568758b37a9e22cd8b6e1ab92d50d57445ab76b1c59a`, `inbox.py`
`828e691cc8e94e82e79e88b866e265473f0e39cf9791c0c9e0d5bd659c34d991`, each re-measured after every knife and
equal to the entry reading. The same four knives are also permanent pins inside the new file, run through
`tests/_temp_edit_overlay.py` so a regression run can re-cut them without touching disk:

- (1) lifting the new approval fold out of `approval_candidates` reddens **12**: the 200 itself, the omitted
  shape, the two-legs-at-once reading, the other-legs-unchanged reading, the count arithmetic, the refused read
  that must write no state, the two-faces comparison, the code-equality pin, the reason-table pin, the
  literal-count pin, the typed-catch AST pin, and the permission-face pin (a black page cannot show the
  permission face either -- that last one is this ticket's whole argument in a single red).
- (2) folding the refusal into 「an empty bundle with no registered absence」 reddens **7**: the 200 reading,
  the two-legs-at-once reading, the omitted shape, the two-faces comparison whose whole job is to keep 「not
  supplying data」 apart from 「nothing here」, the code-equality pin, the literal-count pin, and the
  permission-face pin. The page answers 200 under this mutant, and the lie is that it answers 「nothing
  pending」.
- (3) putting `403` into the document leg's roster reddens **2**: the roster pin and the face pin that reads a
  `403` as a `403`.
- (4) making the approval write branch answer `False` reddens **3**: the direct-call pin, the AST pin, and the
  end-to-end pin that refuses a quiet receipt.

In the same window as every knife, the seven neighbours named in the ticket ran together --
`test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses`, `test_r299_notification_inbox`,
`test_r299_notification_states`, `test_r303_notification_pins`, `test_r359_alerts_refuse_a_store_that_is_not_there`,
`test_r142_error_code_table_sync`, `test_error_code_vocabulary` -- **236 passed, 0 failed**, under all four
mutants. Nothing here was passed over, skipped, or widened to reach that number.

Physical lines: `app/notifications/sources.py` +32 / -3, `app/notifications/inbox.py` +12 / -1. The three
deleted lines are R366's fallback literal (hoisted to the shared constant) and the two call sites this ticket
wrapped in a `try`; no expectation, no fold, and no status code that was already there moved.

Out of this ticket's write set, registered rather than fixed:

- `app/documents/catalog.py:709-724`: the SQL leg of the document catalog is wrapped in `except Exception` and
  falls back to `_local_version_rows()`, and the offline leg at `:707` is not inside any `try` at all. So a
  missing `document_versions` table, a missing column, or a dead connection reads as a normal 200 whose
  `sources.document` says 「scanned」. This is the R359 disease one layer down, and no inbox-side fix can
  reach it without a second storage probe, which R366 pins away.
- `app/api/v1/notifications.py:159` and `:190`: the outlet translates `NotificationStateStoreMissing` and
  nothing else. Adding `pending_approvals.PendingApprovalStoreMissing` beside it would turn the write-side
  `bare 500` above into the `503 storage_unavailable` the rest of the repository already speaks.
- The named-type boundary this ticket keeps also leaves two cells black on purpose: `_conn()`
  (`app/storage/pending_approvals.py:104`) raises a plain `RuntimeError` when the driver is absent, and a
  pre-0012 ledger answers `UndefinedColumn` at `:372` -- neither is an instance of the domain error, so
  neither is folded, and a pin requires that the driver case still reaches the customer as a 500. Widening the
  catch is not the fix: the ledger itself would have to name those states, and `pending_approvals.py` is under
  a standing do-not-touch.
- `app/storage/pending_approvals.py:336`: when PostgreSQL is not there at all, `_items_with_status` falls back
  to `_MEM_ROWS` without raising, so the approval leg answers 「nothing pending」 on a customer machine with no
  database. `PendingApprovalStoreMissing` only fires when the process thinks the store is ready and the table
  is gone -- same asymmetry R367 registered for the dashboard tiles.

## A write that cannot be stored must not say it was (2026-09-27, R376)

R366 registered this cell instead of fixing it: `app/notifications/states.py` chose its leg by
`_database_available()` alone, so on a customer machine whose PostgreSQL is not up, `POST
/api/v1/notifications/read` and `POST /api/v1/notifications/dismiss` wrote the process-local `_ROWS`
overlay, answered `200`, and reported `changed: true` for a row no table ever held. Restart the
process and that notification is unread again. The missing store is the situation; the receipt was
the lie. (This closes the write half of 「`app/notifications/states.py` has no production branch」,
registered at the foot of the R366 section; the read half is registered again below, deliberately.)

`app/notifications/states.py::_require_writable_store` (`:94`, called at `:191`) is the gate, and it
reads two numbers this module already had: `_database_available()` (`:65`, still the one `_db_ready`
reader in this file) and `_is_production_environment()` borrowed from `app/api/v1/alerts.py:60` --
the same ruler `app/api/v1/dashboard.py` borrows (R367), so `app/**` still holds eight definitions of
it and this ticket added none. Both halves must hold before anything is refused; states.py itself
reads no `APP_ENV` and compares no spelling of it.

### The three worlds, per face

| world | what the write does | HTTP face | is anything recorded |
| --- | --- | --- | --- |
| store ready (`_db_ready` true), any `APP_ENV` | one `INSERT ... ON CONFLICT (notification_id, recipient) DO UPDATE` plus `commit()` against `notification_states` | `200`, `results[].changed` true on the first mark and false on a repeat | yes -- the table |
| production, store not ready | nothing: `_ROWS` is not written, `read_state` is not called, `_now()` is not read, `_conn()` is not called | `503 {"detail": "storage_unavailable"}` | no |
| development / bare machine, store not ready | the process-local overlay, exactly as since R299 | byte-for-byte the base answer: `200`, `changed: true`, `reason: "applied"` | process memory, which is legitimate there |

**Zero new error codes, zero new reason words.** The refusal is the exception this outlet already
translates -- `NotificationStateStoreMissing` (`states.py:53`), caught at
`app/api/v1/notifications.py:159` for the two writes and at `:190` for the list, turned into the
`503 storage_unavailable` this module has emitted since R299. The outlet did not change by a byte:
no third `except` type, no new `detail`, no new receipt key. `reason` is still exactly two words --
`applied` and `notification_not_addressable` -- and 「nothing was recorded」 is not a third one: a
storage refusal is an error, never a footnote smuggled inside a 200.

### What the gate does not fold

Ordering is unchanged and pinned. 401 (`authentication_required`) and the per-id
`notification_not_addressable` are both answered before the storage question is asked, and the
storage refusal is not folded into either: a call over someone else's notification id still answers
`200` with that per-id receipt on a production machine whose store is down, because a permission
answer must not double as a probe for whether this customer has PostgreSQL up. One addressable id in
a batch is enough to refuse the whole call -- there is no 「200 with a half-written batch」 here, and
there cannot be, since the other half could not have been written either.

The read legs are left alone on purpose, which is a visible seam rather than an oversight:
`recipient_states` (`:131`) and `read_state` (`:157`) still take the overlay in that world, so
`GET /api/v1/notifications` keeps answering `200` exactly as R366 ratified. What changed is that the
two legs can no longer contradict each other. Before: 「I recorded it」 on the write and 「nobody has
read anything」 after a restart. Now: 「this machine cannot record it」 on the write, and an empty
overlay on the read that is finally the truth -- nothing was recorded, and nothing could be. Still
unsaid, registered rather than fixed:

- A customer whose PostgreSQL was healthy at boot and dies mid-life keeps reading `200`, everything
  unread, while the `notification_states` rows sit on the dead server: the lifecycle leg has no
  「this cell is not supplying data」 field of its own. Adding one belongs where R366 put the alert
  leg's -- `app/notifications/inbox.py`, via `_omitted` -- and that file is another ticket's write
  set. It would need no new code either.
- `tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py::test_the_other_legs_keep_their_writes_while_the_alert_leg_refuses`
  still asserts the base face -- `200`, `changed: true`, a row in `_ROWS` for an approval
  notification on that same production-without-a-store machine -- and the R366 sentence 「dismissing
  an approval row still answers 200 with `changed: true`」 (`:4021-4022`) says the same thing. Both
  are precisely the claim this section retires, and both are outside this ticket's write set, so
  they are listed for correction by their owner rather than adjusted to green here.

### Evidence

`tests/test_r376_notifications_refuse_a_store_that_is_not_there.py` (30 pins) walks both worlds from
the route and from the storage layer directly: the refusal and the emptiness of `_ROWS`, the counters
that prove no connection, clock or ledger read precedes the gate, the inequality of one same request
across the two worlds, the ready-store case that still records and still tells a first mark from a
repeat, four production spellings and six non-production spellings of `APP_ENV`, and the 401 /
not-addressable faces that must not move. `tests/test_r376_gate_shape_pins.py` (24 pins) judges shape
off the AST: one `_db_ready` reader in this file, eight production rulers in `app/**` and none of
them here, no `getenv("APP_ENV")`, no `HTTPException` in the storage layer, the outlet's
`(status_code, detail)` and `except` rosters unchanged, the two folded status rosters derived
separately (`401/403/404` in `can_address`, `403/503` in `alert_candidates`), the gate ordered before
`read_state` / `_now` / the `_ROWS` write, and `_ROWS.clear()` inside `reset_for_testing` still in
place. All offline: no service, no PostgreSQL, no model port, no `chroma_db/` write.

Physical lines: `app/notifications/states.py` +57 / -2 -- one gate, its call site, and the two
docstrings that used to describe one difference now describing two. `app/api/v1/notifications.py`
+0 / -0.

## A chat turn that still needs its migrations answers 503 too (2026-09-27, R384)

R371 folded the `alerts.py` refusals, R377 walked the four store-layer siblings and judged all four
contained. Two cells were left unread: the `chat.py` ones R377 named without probing. This section probes
them. Every face below is read off `TestClient(app, raise_server_exceptions=False)` against a substitute
ledger that answers only 「does this one `to_regclass('public.x')` lookup find the table」 and 「a write
against an absent ledger fails like PostgreSQL fails」 (`psycopg.errors.UndefinedTable`). Nothing here
evaluates real SQL, opens a database, starts a service or touches a model port. Sentence: **one of the
three cells could actually reach an HTTP exit, and exactly that one changed.**

### The three call sites, measured before anything was edited

Base positions are read from `5ba73bd`; `app/**` still holds zero exception handlers (re-scanned off the
AST in `tests/test_r384_migrations_first_refuses_at_the_ask_exit.py`, not off a substring -- this ticket
learned the hard way that its own source comment mentions that very phrase).

| call site | who raises | who catches | what the catch hands out | production, ledger missing | development | offline |
| --- | --- | --- | --- | --- | --- | --- |
| `_ensure_documents_table()` at import, `:1000` | `:878` (`documents` absent) | its own `except Exception: pass` (`:1001`) | nothing: the import continues, the comment says the table is built lazily at upload | raises once, eaten, `reload` succeeds (measured in a fresh process; zero exit touched) | builds it in place, never raises | never entered: `:998` `if catalog_database_available():` short-circuits, substitute ledger records **zero statements** |
| `_ensure_documents_table()` inside `_upsert_document`, `:1020` | `:878` (`documents` absent) | `_record_uploaded_version` `:3655` `except Exception as exc` + `logger.warning` | **`200`** from `POST /api/v1/upload`: the file is stored, the metadata row is not, and the log carries `metadata sync failed: ... run migrations first` | measured `200` | builds it, then writes the row | takes `record_local_document_version` |
| `_ensure_sessions_table()` inside `ask()`, `:2218` | `:878` (`sessions`, then `session_messages`) | **nobody** | -- | **before: `500` `text/plain` `Internal Server Error`** / after: `503 {"detail":"storage_unavailable"}` | self-heals with `CREATE TABLE IF NOT EXISTS`, passes the gate | gate returns on its first line, zero connections |

That first `500` is the whole subject of this ticket: an anonymous plain-text 500 is what a customer sees
when they have PostgreSQL up and have not run the migrations, and the traceback is the only place the
answer 「which table, and what do I run」 exists -- which is exactly what a 500 logs and a 503 does not.
So the exit that removed the traceback also writes the sentence back: one `logger.warning` line carrying
`code=storage_unavailable` and the original `reason=sessions table is required in production; run
migrations first`.

### One layer of naming, folded at the existing exit

`ChatSchemaNotMigratedError` (`app/api/v1/chat.py:874`) is a subclass of `RuntimeError`, not a
replacement -- same ruling R371 recorded for `alerts.py`, and for the same reason: the two cells above
are caught by `except Exception`, and both `tests/test_document_upload_resilience.py` and the import
path assert through that layer. The message text is byte-for-byte the sentence it always was.

`ask()` now wraps exactly that one call, catches exactly that one type, and hands the conclusion to the
503 this module already emits (`hitl_pending`, `:3037` at base / `:3065` as delivered). Counting the
module's `raise HTTPException(status_code=503, ...)` sites by AST: **five before, six after**, and the
one addition is named, with its reason, in `test_the_module_now_opens_exactly_six_503_raises_each_named`
(`_enqueue_ask_turn` / `hitl_pending` / `queue_status` / `cancel_queued_request` / `queue_stats` are the
five that were already there; `ask` is this ticket's). **Zero new error codes, zero new reason words,
zero new status tiers**: the new detail is the same string object-level equal to the existing exit's
(`ast.literal_eval`, not a quote-matched substring). The four queue exits keep their
`{"code": "queue_unavailable", ...}` shape, so 「the store cannot answer」 and 「Redis is not there」 are
still two faces, and they are still distinguishable from 「this deployment never enabled PostgreSQL」 --
which stays `200` on the process-local session tables and answers nothing at all on the gate.

Nothing was folded into a `200`. The refusal is ordered before `session_registry.bind`, before
`_ensure_session`, before `_save_message`, before the queue and before the model, so a refused turn
leaves zero side effects (pinned, not asserted in prose).

### Judged, and left alone on purpose

- `:1000` and `:1020` are **unreachable as a 500** -- each is already eaten inside the module, one by a
  bare `pass`, one by a warning that is a deliberate ruling: dropping an upload because a metadata table
  is unreachable would lose a document the caller can no longer address. Converting either into a 503
  would have to pass through `app/documents/catalog.py`, which is another ticket's write set, so this
  ticket registers them instead of fixing them. Both faces are now pinned as measured (including the
  `200`), so whoever does change them changes a number and not a rumour.
- The `200` on upload is the same disease R356/R359/R332 ruled on: the store refused to answer, and the
  response says 「stored, owned, parse ready」. It is not an empty set -- it is a receipt for a row that
  was never written. That is registered here, in the outlet that produces it, and not fixed.

### Registered, still not faced (out of this ticket's table, measured anyway)

- `_ensure_session()` inside `ask()` (base `:2223`): with the gate stubbed out, production plus a missing
  `sessions` answers **`500` `text/plain`**. It is raised by `INSERT INTO sessions` as
  `UndefinedTable`, not by the `run migrations first` lookup, so it is not a cell of this table; the
  gate stands in front of it and still does, so this ticket did not uncover it either.
- `GET /api/v1/sessions` with the same missing ledger: measured **`500` `text/plain`**, same
  `UndefinedTable` family. `_list_sessions()` is not an `_ensure_*` / `_require_migrated_tables` call
  site, so it is listed, not treated.
- `app/agents/orchestrator.py:110` (`PostgresSaver checkpointer is required in production; run
  migrations first`) is the sixth sibling of this sentence and has no pin of its own in the repository.
  Not this ticket's file, not this ticket's write set.
- One existing pin had to be reworded to survive this legal change:
  `tests/test_r377_migrations_first_family_is_contained_at_the_store_layer.py::test_the_two_out_of_write_set_modules_are_still_report_only`
  used to compare the `chat.py` raise against a **copied source line**, which is the fourth member of the
  family R346 / R351 / R364 named. It now counts the sentence instead of the statement shape -- the claim
  it was actually making (that sentence appears exactly once in `chat.py`) is unchanged, and the type and
  exit shape moved into this ticket's file.

### Evidence

`tests/test_r384_migrations_first_refuses_at_the_ask_exit.py` (25 pins): the 503 and its exact body, the
per-table diagnosis (a missing `session_messages` names `session_messages`, not `sessions`), the refusal
ordered before every side effect, development self-heal passing the gate, offline opening no connection,
a fully-migrated production turn still passing, a missing driver still answering the bare 500 it always
answered (the anti-laundering pin), the message reconstructed from its template rather than copied, and
the AST roster of the six 503 exits. Eight counter-evidence knives were run against the delivered file
and restored byte-for-byte (sha256 in == out): strip the conversion (9 of this ticket's pins red), widen
the catch to `Exception` (3), reword the sentence (6), replace the base class (5), invent a new error
code (3), invent a second probe (1), narrow the import-time catch-all (1), build a second 503 door (1).

Physical lines: `app/api/v1/chat.py` +30 / -2 -- the named class, its raise, and the one exit that folds
them. `tests/test_r377_...` +13 / -8 -- one reworded assertion, zero pins deleted. `tests/test_r384_...`
+545 / -0 new.