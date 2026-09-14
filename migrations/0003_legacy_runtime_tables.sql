-- Legacy application tables required by the current compatibility adapters.
-- Runtime code may fall back to memory when the database is unavailable, but
-- production schema creation belongs to the explicit migration runner.

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text,
    department TEXT,
    role TEXT NOT NULL DEFAULT 'staff'
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    created_at TEXT NOT NULL
);

-- Older runtime tables used session IDs without an owner field. Preserve those
-- rows as unowned rather than assigning an invented principal.
ALTER TABLE IF EXISTS sessions
    ADD COLUMN IF NOT EXISTS user_id TEXT;

CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS session_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS session_messages_session_idx
    ON session_messages (session_id, id);

CREATE TABLE IF NOT EXISTS document_versions (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    version INTEGER NOT NULL,
    classification INTEGER NOT NULL DEFAULT 1,
    department TEXT,
    storage_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (filename, version)
);

CREATE INDEX IF NOT EXISTS document_versions_name_idx
    ON document_versions (filename, version DESC);

CREATE TABLE IF NOT EXISTS alert_rules (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    metric TEXT NOT NULL,
    op TEXT NOT NULL DEFAULT 'lt',
    threshold DOUBLE PRECISION NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES alert_rules (id) ON DELETE SET NULL,
    message TEXT,
    ai_analysis TEXT,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
);

CREATE INDEX IF NOT EXISTS alerts_created_idx ON alerts (id DESC);

CREATE TABLE IF NOT EXISTS memories (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding JSONB,
    created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
);

CREATE INDEX IF NOT EXISTS memories_user_idx ON memories (user_id, id DESC);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    department TEXT,
    position TEXT,
    preferences JSONB,
    updated_at TEXT NOT NULL
);
