-- Chunk bookkeeping for the index publication slice (S4, Wave 3).
--
-- 0006_document_ownership.sql deliberately stopped at ownership and left this column to
-- the only writer that knows how many chunks a version really produced. Uploading and
-- deleting a document now publish an index version, and the published count is read back
-- from the vector store rather than predicted by the splitter, so documents and
-- document_versions can carry it.
--
-- chunk_count is nullable on purpose: NULL means "no index version has ever been
-- published for this row" (every row written before this migration, and every upload
-- whose chunks could not be enumerated), while 0 means "a version was published and it
-- holds no chunks", which is what a retired document is. A NOT NULL DEFAULT 0 would make
-- an unindexed historical row look like a deliberately empty index.

ALTER TABLE IF EXISTS documents
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER;

ALTER TABLE IF EXISTS documents
    DROP CONSTRAINT IF EXISTS documents_chunk_count_check;

ALTER TABLE IF EXISTS documents
    ADD CONSTRAINT documents_chunk_count_check
    CHECK (chunk_count IS NULL OR chunk_count >= 0);

ALTER TABLE IF EXISTS document_versions
    ADD COLUMN IF NOT EXISTS chunk_count INTEGER;

ALTER TABLE IF EXISTS document_versions
    DROP CONSTRAINT IF EXISTS document_versions_chunk_count_check;

ALTER TABLE IF EXISTS document_versions
    ADD CONSTRAINT document_versions_chunk_count_check
    CHECK (chunk_count IS NULL OR chunk_count >= 0);

-- The publication mirror writes owner_id straight from the catalog row, and a document
-- uploaded before ownership existed has no owner to write. These three tables required an
-- owner, so a legacy document could never have been indexed honestly: the only remaining
-- options were to invent a principal or to skip the record. Inventing one is what the
-- ownership slice rejected, so an absent owner is now stored as NULL and read as legacy.
-- No column is added to chunks, and no embedding is written: classification and
-- department live in chunks.metadata, and vectors still belong to Chroma alone.

ALTER TABLE IF EXISTS chunks
    ALTER COLUMN owner_id DROP NOT NULL;

ALTER TABLE IF EXISTS index_registry
    ALTER COLUMN owner_id DROP NOT NULL;

ALTER TABLE IF EXISTS index_versions
    ALTER COLUMN owner_id DROP NOT NULL;

-- resource_versions is the authorization view of one stored version, and the index mirror
-- writes the owner it read out of the catalog rather than a fresh one. A document uploaded
-- before ownership existed has no owner to copy, and inventing one is exactly what the
-- ownership slice rejected, so this column becomes optional on the same terms: NULL reads
-- as legacy and never as public.
ALTER TABLE IF EXISTS resource_versions
    ALTER COLUMN owner_id DROP NOT NULL;

-- A publication reads its own count back per index version and a retirement removes every
-- chunk row of one logical document; neither query can use chunks_resource_idx because
-- that index leads with owner_id, which is now optional.
CREATE INDEX IF NOT EXISTS chunks_index_version_idx
    ON chunks (index_version_id);

CREATE INDEX IF NOT EXISTS chunks_resource_key_idx
    ON chunks (resource_type, resource_id, resource_version_id);

CREATE INDEX IF NOT EXISTS documents_chunk_count_idx
    ON documents (chunk_count);