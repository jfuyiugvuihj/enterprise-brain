-- Document ownership and parse lifecycle.
--
-- Two defects are closed by this additive migration:
--
-- * documents and document_versions had no owner column, so the runtime wrote no
--   owner and _document_authorization_decision always read owner_id as NULL. Every
--   delete therefore fell through to the department intersection and was denied,
--   which blocked the whole document lifecycle (authorization, index rollback,
--   physical cleanup and audit could never run end to end).
-- * The document catalog needs the stored size and the parse state of a version
--   (frontend request R4) so the upload view can stop faking progress.
--
-- chunk_count is intentionally NOT added here: chunk bookkeeping belongs to the
-- index publication slice (S4, Wave 3), the only writer that knows how many chunks
-- actually reached an index.
--
-- Rows written before this migration keep owner_id IS NULL. An unowned document is
-- never treated as public; see docs/documents/ownership-and-authorization.md.

ALTER TABLE IF EXISTS documents
    ADD COLUMN IF NOT EXISTS owner_id TEXT;

ALTER TABLE IF EXISTS documents
    ADD COLUMN IF NOT EXISTS size_bytes BIGINT;

-- pending: no parse attempt has completed
-- parsing: a parse and index attempt is in flight
-- ready:   the version parsed and was accepted into the knowledge base
-- failed:  the version could not be parsed; row and stored file are kept for review
ALTER TABLE IF EXISTS documents
    ADD COLUMN IF NOT EXISTS parse_status TEXT NOT NULL DEFAULT 'pending';

ALTER TABLE IF EXISTS documents
    DROP CONSTRAINT IF EXISTS documents_parse_status_check;

ALTER TABLE IF EXISTS documents
    ADD CONSTRAINT documents_parse_status_check
    CHECK (parse_status IN ('pending', 'parsing', 'ready', 'failed'));

CREATE INDEX IF NOT EXISTS documents_owner_idx
    ON documents (owner_id, filename);

CREATE INDEX IF NOT EXISTS documents_parse_status_idx
    ON documents (parse_status);

ALTER TABLE IF EXISTS document_versions
    ADD COLUMN IF NOT EXISTS owner_id TEXT;

ALTER TABLE IF EXISTS document_versions
    ADD COLUMN IF NOT EXISTS size_bytes BIGINT;

-- See the parse_status value list above (pending / parsing / ready / failed).
ALTER TABLE IF EXISTS document_versions
    ADD COLUMN IF NOT EXISTS parse_status TEXT NOT NULL DEFAULT 'pending';

ALTER TABLE IF EXISTS document_versions
    DROP CONSTRAINT IF EXISTS document_versions_parse_status_check;

ALTER TABLE IF EXISTS document_versions
    ADD CONSTRAINT document_versions_parse_status_check
    CHECK (parse_status IN ('pending', 'parsing', 'ready', 'failed'));

CREATE INDEX IF NOT EXISTS document_versions_owner_idx
    ON document_versions (owner_id, filename, version DESC);

CREATE INDEX IF NOT EXISTS document_versions_parse_status_idx
    ON document_versions (parse_status);