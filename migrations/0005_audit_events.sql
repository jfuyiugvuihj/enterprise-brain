-- Durable security-audit journal for authorization decisions.
-- The runtime previously kept audit events in a process-local list, so every
-- denied request lost its judgment chain on restart. This migration is additive.

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    actor_username TEXT NOT NULL,
    actor_role TEXT NOT NULL DEFAULT 'unknown',
    owner_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    resource TEXT NOT NULL DEFAULT '',
    resource_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT '',
    policy_version TEXT NOT NULL DEFAULT '',
    before_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    retention_days SMALLINT NOT NULL DEFAULT 180 CHECK (retention_days > 0),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_events_created_idx
    ON audit_events (created_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_actor_idx
    ON audit_events (actor_username, created_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_request_idx
    ON audit_events (request_id, created_at)
    WHERE request_id <> '';

CREATE INDEX IF NOT EXISTS audit_events_retention_idx
    ON audit_events (expires_at)
    WHERE expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS audit_events_scope_idx
    ON audit_events USING GIN (resource_scope);