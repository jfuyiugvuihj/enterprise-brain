# Database Migrations

The production database target is PostgreSQL with PGVector. Runtime imports must not
create tables. Checked-in migration files use `NNNN_descriptive_name.sql`; every SQL
file must be listed in `manifest.json` with its SHA-256 digest. The migration loader
fails closed if a file is missing, added without a manifest entry, renamed, empty, or
changed without a matching manifest update.

An explicit deployment runner must:

1. Parse and validate `DATABASE_URL`.
2. Open a PostgreSQL connection and pass it to `app.db.migrations.apply_migrations`.
3. Acquire the transaction-scoped advisory lock selected by `migration_lock_key`.
4. Create and read `schema_migrations`, then reject checksum drift or removed versions.
5. Apply pending files and record each version, name, and checksum in the same transaction.
6. Release the lock at transaction completion and expose any failure state to health checks.

Run the checked-in runner from the project root:

```bash
python scripts/migrate.py
```

The runner loads `DATABASE_URL` from the process environment or local `.env`,
validates that it is PostgreSQL, and reports failures without swallowing rollback.
PostgreSQL must have PGVector installed before this catalog can be applied.

`0001_core_resource_versions.sql` establishes the migration ledger, the target
PGVector extension, generic versioned resource metadata, and controlled Artifact
metadata. It does not migrate existing runtime-created tables or prove that
PostgreSQL/PGVector has been deployed; those require an isolated integration run.

`0002_execution_data_lineage.sql` adds Dataset/DatasetVersion, execution and trace
records, index publication metadata, chunks, and Artifact source lineage. It is
additive and repeatable and does not import historical JSON registry records.

`0003_legacy_runtime_tables.sql` adds the compatibility tables still consumed by
the current authentication, session, document-version, alert, memory, and profile
adapters. It makes their production schema explicit without changing the offline
memory fallback behavior.

`0004_legacy_runtime_compatibility.sql` closes the gap between the 0003 compatibility tables and
the columns the current authenticated chat adapter actually reads: `sessions.title`,
`sessions.updated_at`, `session_messages.steps`, and the `documents` table behind
`app/documents/catalog.py`. It is additive so historical session rows stay available.

`0005_audit_events.sql` adds the durable security-audit journal that `app/common/audit.py` now
writes through `app/storage/persistence.py`. Before it, the judgment chain for a denied request
lived only in a process-local list and disappeared on restart, so a wave of 403s left no
traceable history. Each row keeps `request_id`, actor, action, resource, the resource scope as
JSONB, outcome, `reason_code` and `policy_version`.

`0006_document_ownership.sql` and `0007_document_chunk_count.sql` give the document catalog a
writer-side owner (`owner_id`) and a stored chunk count, so a listing no longer has to guess
whether a file was indexed and a department can be held to what it uploaded.

`0008_pending_approvals.sql` parks a HITL action in `pending_approvals` instead of only in the
process that created it, which is what lets `GET /api/v1/hitl/pending` answer after a restart
or from another worker.

`0009_metric_definition_semantics.sql` lifts the wording a metric is called by, its prose
definition, its granularity, its match terms and its origin out of the reserved `semantics`
key inside the `filters` JSONB and into real columns, and adds the verification columns that
make `verified_against_documents` a closed enumeration instead of a warning that can never be
cleared (R15-b). It is additive and idempotent: every statement is guarded, nothing is
dropped, and the backfill only fills empty values.
