-- Enterprise Brain canonical control-plane baseline.
-- This migration is executed only by an explicit deployment runner.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) PRIMARY KEY,
    name TEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resource_versions (
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    department_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    classification TEXT NOT NULL,
    visibility TEXT NOT NULL,
    status TEXT NOT NULL,
    storage_key TEXT,
    content_sha256 CHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    PRIMARY KEY (resource_type, resource_id, version_id)
);

CREATE INDEX IF NOT EXISTS resource_versions_owner_idx
    ON resource_versions (owner_id, resource_type, status);

CREATE INDEX IF NOT EXISTS resource_versions_scope_idx
    ON resource_versions USING GIN (department_ids);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    source_version_id TEXT,
    storage_key TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    status TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS artifacts_owner_idx
    ON artifacts (owner_id, status, expires_at);
