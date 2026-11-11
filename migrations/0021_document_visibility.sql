-- Enterprise-wide sharing of level-1 documents.
--
-- Sensitivity and sharing are separate facts:
--   classification 1/2/3 says who may read it at all;
--   visibility private/enterprise_shared says whether level 1 is also published
--   to every active account that has a department.
--
-- Existing rows stay private. Publishing is an explicit administrator action, never
-- a bulk re-label, and a document that is not fully classified is not publishable.

ALTER TABLE IF EXISTS documents
    ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';

ALTER TABLE IF EXISTS document_versions
    ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';

ALTER TABLE IF EXISTS chunk_vectors
    ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';

ALTER TABLE IF EXISTS documents
    DROP CONSTRAINT IF EXISTS documents_visibility_check;

ALTER TABLE IF EXISTS documents
    ADD CONSTRAINT documents_visibility_check
    CHECK (visibility IN ('private', 'enterprise_shared'));

ALTER TABLE IF EXISTS document_versions
    DROP CONSTRAINT IF EXISTS document_versions_visibility_check;

ALTER TABLE IF EXISTS document_versions
    ADD CONSTRAINT document_versions_visibility_check
    CHECK (visibility IN ('private', 'enterprise_shared'));

ALTER TABLE IF EXISTS chunk_vectors
    DROP CONSTRAINT IF EXISTS chunk_vectors_visibility_check;

ALTER TABLE IF EXISTS chunk_vectors
    ADD CONSTRAINT chunk_vectors_visibility_check
    CHECK (visibility IN ('private', 'enterprise_shared'));

CREATE INDEX IF NOT EXISTS documents_visibility_idx
    ON documents (visibility);

CREATE INDEX IF NOT EXISTS document_versions_visibility_idx
    ON document_versions (visibility);

CREATE INDEX IF NOT EXISTS chunk_vectors_visibility_idx
    ON chunk_vectors (visibility);
