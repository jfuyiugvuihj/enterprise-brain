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
