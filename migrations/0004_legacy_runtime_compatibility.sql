-- Align the legacy runtime tables with the current authenticated chat adapter.
-- This migration is additive so historical session rows remain available.

ALTER TABLE IF EXISTS sessions
    ADD COLUMN IF NOT EXISTS title TEXT;

ALTER TABLE IF EXISTS sessions
    ALTER COLUMN title SET DEFAULT '';

UPDATE sessions
SET title = ''
WHERE title IS NULL;

ALTER TABLE IF EXISTS sessions
    ALTER COLUMN title SET NOT NULL;

ALTER TABLE IF EXISTS sessions
    ADD COLUMN IF NOT EXISTS updated_at TEXT;

UPDATE sessions
SET updated_at = created_at
WHERE updated_at IS NULL;

ALTER TABLE IF EXISTS sessions
    ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE IF EXISTS session_messages
    ADD COLUMN IF NOT EXISTS steps TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT UNIQUE NOT NULL,
    classification INTEGER NOT NULL DEFAULT 1,
    department TEXT
);
