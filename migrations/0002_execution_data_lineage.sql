-- Enterprise Brain execution, data lineage, and index publication metadata.
-- This migration is intentionally additive and is applied only by the deployment
-- runner inside the transaction managed by app.db.migrations.

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    department_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    classification TEXT NOT NULL,
    visibility TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    status TEXT NOT NULL,
    current_version_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS datasets_active_filename_idx
    ON datasets (filename)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS datasets_owner_idx
    ON datasets (owner_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS datasets_scope_idx
    ON datasets USING GIN (department_ids);

CREATE TABLE IF NOT EXISTS dataset_versions (
    dataset_version_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets (dataset_id),
    owner_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    storage_key TEXT NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    schema_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    period_start DATE,
    period_end DATE,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (dataset_id, version_number)
);

CREATE INDEX IF NOT EXISTS dataset_versions_owner_idx
    ON dataset_versions (owner_id, dataset_id, status);

CREATE TABLE IF NOT EXISTS calculation_runs (
    calculation_run_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    dataset_version_id TEXT REFERENCES dataset_versions (dataset_version_id),
    metric_definition_id TEXT,
    request_id TEXT,
    task_id TEXT,
    status TEXT NOT NULL,
    formula TEXT,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS calculation_runs_owner_idx
    ON calculation_runs (owner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_definition_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    definition_version TEXT NOT NULL,
    formula TEXT NOT NULL,
    unit TEXT NOT NULL,
    currency TEXT,
    period_type TEXT NOT NULL,
    timezone TEXT NOT NULL,
    source_scope JSONB NOT NULL DEFAULT '[]'::jsonb,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, metric_id, definition_version)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    agent_run_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    session_id TEXT,
    worker TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_code TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS agent_runs_owner_idx
    ON agent_runs (owner_id, started_at DESC);

CREATE INDEX IF NOT EXISTS agent_runs_trace_idx
    ON agent_runs (trace_id, task_id);

CREATE TABLE IF NOT EXISTS agent_steps (
    agent_step_id TEXT PRIMARY KEY,
    agent_run_id TEXT NOT NULL REFERENCES agent_runs (agent_run_id),
    owner_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    worker TEXT NOT NULL,
    status TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_code TEXT,
    input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (agent_run_id, step_id)
);

CREATE INDEX IF NOT EXISTS agent_steps_run_idx
    ON agent_steps (agent_run_id, sequence);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    agent_run_id TEXT REFERENCES agent_runs (agent_run_id),
    agent_step_id TEXT REFERENCES agent_steps (agent_step_id),
    owner_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    request_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_code TEXT,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS tool_calls_owner_idx
    ON tool_calls (owner_id, started_at DESC);

CREATE TABLE IF NOT EXISTS model_calls (
    model_call_id TEXT PRIMARY KEY,
    agent_run_id TEXT REFERENCES agent_runs (agent_run_id),
    agent_step_id TEXT REFERENCES agent_steps (agent_step_id),
    owner_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    status TEXT NOT NULL,
    request_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_token_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    queue_wait_ms INTEGER,
    duration_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error_code TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS model_calls_owner_idx
    ON model_calls (owner_id, started_at DESC);

CREATE TABLE IF NOT EXISTS retrieval_traces (
    retrieval_trace_id TEXT PRIMARY KEY,
    agent_run_id TEXT REFERENCES agent_runs (agent_run_id),
    owner_id TEXT NOT NULL,
    request_id TEXT,
    trace_id TEXT NOT NULL,
    query_hash CHAR(64) NOT NULL,
    index_version_id TEXT,
    filter_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS retrieval_traces_owner_idx
    ON retrieval_traces (owner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS trace_events (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trace_id, sequence)
);

CREATE INDEX IF NOT EXISTS trace_events_owner_idx
    ON trace_events (owner_id, created_at DESC);

CREATE INDEX IF NOT EXISTS trace_events_trace_idx
    ON trace_events (trace_id, sequence);

CREATE TABLE IF NOT EXISTS index_registry (
    index_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    status TEXT NOT NULL,
    current_version_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS index_versions (
    index_version_id TEXT PRIMARY KEY,
    index_id TEXT NOT NULL REFERENCES index_registry (index_id),
    owner_id TEXT NOT NULL,
    source_version_id TEXT NOT NULL,
    backend TEXT NOT NULL,
    chunk_count INTEGER NOT NULL CHECK (chunk_count >= 0),
    checksum CHAR(64) NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS index_versions_publication_idx
    ON index_versions (index_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_version_id TEXT NOT NULL,
    index_version_id TEXT REFERENCES index_versions (index_version_id),
    content TEXT NOT NULL,
    embedding vector,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chunks_resource_idx
    ON chunks (owner_id, resource_type, resource_id, resource_version_id);

CREATE INDEX IF NOT EXISTS chunks_metadata_idx
    ON chunks USING GIN (metadata);

ALTER TABLE artifacts
    ADD COLUMN IF NOT EXISTS source_resource_type TEXT;

ALTER TABLE artifacts
    ADD COLUMN IF NOT EXISTS source_resource_id TEXT;

CREATE INDEX IF NOT EXISTS artifacts_source_idx
    ON artifacts (source_resource_type, source_resource_id, source_version_id);
