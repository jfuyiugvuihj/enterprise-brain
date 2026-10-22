-- HITL pending-approval ledger (request R13).
--
-- A parked turn exists only inside the LangGraph checkpoint: check_interrupt() has to be
-- told the thread_id up front (app/agents/orchestrator.py:1152) and nothing in the repo
-- can enumerate parked sessions, so an approval panel had no truth to read and could only
-- invent one. This table records one row per park, with a terminal state, instead of
-- trying to query a transient graph position.
--
-- session_id doubles as the graph thread_id on purpose: POST /ask sets
-- thread_id = request.session_id (app/api/v1/chat.py:783), so the two are the same value
-- for every parked turn. The equivalence is spelled out here because the read-side
-- recheck depends on it: the endpoint asks check_interrupt(session_id) to confirm that a
-- row still matches the graph.
--
-- owner_user_id is principal.user_id, the same identity the session registry binds
-- (app/storage/sessions.py:61-79). Listing is "reading your own stuff", so R13 adds no
-- new permission tier; see docs/handoff/2026-09-15-alert-and-hitl-design.md §3.5.
--
-- parked_steps is the node list from check_interrupt()["pending"], whose value domain is
-- the compile-time constant _HITL_PARKED (app/agents/orchestrator.py:223). It is a JSONB
-- array rather than a serialized blob of the whole state: the panel shows which step is
-- waiting, and nothing else may be smuggled in.
--
-- expires_at answers "until when is this actionable": a row nobody decided stops being
-- actionable at created_at + the approval TTL, and the read path reports it as stale
-- instead of deleting it, so the audit trail survives.

-- abandoned is only truthful since R12 (commit 826d318): before cooperative cancellation
-- a "stopped" run still finished, so labelling it abandoned would have asserted something
-- the process had not done. stale absorbs the MemorySaver fallback
-- (app/agents/orchestrator.py:68-71): after a restart the graph may hold nothing at all,
-- and a row that cannot be reconfirmed must not keep showing up as a to-do.
CREATE TABLE IF NOT EXISTS pending_approvals (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    parked_steps JSONB NOT NULL,
    request_id TEXT,
    trace_id TEXT,
    task_id TEXT,
    status TEXT NOT NULL DEFAULT 'awaiting',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ,
    CONSTRAINT pending_approvals_status_check
        CHECK (status IN ('awaiting', 'resumed', 'refused', 'abandoned', 'stale')),
    CONSTRAINT pending_approvals_parked_steps_check
        CHECK (jsonb_typeof(parked_steps) = 'array')
);

-- The panel's only query is "my open items, newest first".
CREATE INDEX IF NOT EXISTS pending_approvals_owner_idx
    ON pending_approvals (owner_user_id, status, created_at DESC);

-- One parked turn per session at a time: a newer park supersedes the previous row, which
-- the writer marks stale first so this index cannot be violated by a retry.
CREATE UNIQUE INDEX IF NOT EXISTS pending_approvals_open_session_idx
    ON pending_approvals (session_id)
    WHERE status = 'awaiting';

-- Expiry sweeps and "why did this disappear" queries both filter on this.
CREATE INDEX IF NOT EXISTS pending_approvals_expiry_idx
    ON pending_approvals (expires_at)
    WHERE status = 'awaiting';

COMMENT ON TABLE pending_approvals IS
    'HITL parked turns: who owns it, which steps await a decision, until when, and how it ended';
COMMENT ON COLUMN pending_approvals.session_id IS
    'Same value as the LangGraph thread_id (app/api/v1/chat.py:783); used to recheck the row against the graph';
COMMENT ON COLUMN pending_approvals.parked_steps IS
    'JSONB array of node names drawn from _HITL_PARKED (app/agents/orchestrator.py:223)';
COMMENT ON COLUMN pending_approvals.status IS
    'awaiting|resumed|refused|abandoned|stale; abandoned requires R12 cooperative cancellation, stale means the graph no longer confirms the park';
