-- R58 (architecture line, item 1): give the chunk tables a real, dimensioned
-- vector column and the first vector index in this repository.
--
-- ===================================================================== 口径
-- This migration exists to close the Chroma/PostgreSQL double-write window and to let
-- authorization filtering and vector search run in one engine. It is NOT a latency
-- measure: measured retrieval is 0.242 s, 0.15% of the end-to-end request, and
-- docs/handoff/2026-09-17-pgvector-adoption-plan.md section 7 lists "swap the embedding
-- model / change the dimension / add a reranker to get faster" under 明确不做. Nothing
-- here changes what produces the vectors; it only gives the existing ones a typed home.
--
-- Chroma stays the read path. The application still does not read pgvector for search
-- (that is R59); this file makes a dual write and a shadow read *possible* without ever
-- making either engine the only surviving copy of a vector.
--
-- =================================================== what the earlier migrations left
-- * 0001_core_resource_versions.sql:4 creates the extension. Nothing else in the tree
--   ever put a vector in it, and [实测] no checked-in migration mentions hnsw or ivfflat.
-- * 0002_execution_data_lineage.sql declares chunks.embedding as bare `vector`, with no
--   type modifier. A bare vector cannot be indexed at all (hnsw and ivfflat both require
--   a dimensioned column) and cannot reject a mixed-dimension write, so this migration is
--   what retypes it. Untyped is not a legacy state worth preserving: every row written by
--   app/rag/indexing.py leaves the column NULL ("every row it writes leaves
--   chunks.embedding NULL", app/rag/indexing.py:8), so retyping costs no data.
-- * 0003_legacy_runtime_tables.sql:77 declares memories.embedding as JSONB. It is
--   deliberately NOT converted here: it is a different table with a different writer
--   (app/memory/long_term.py), and it is not part of the document-retrieval leg this
--   ticket is about. Converting it would also destroy information -- JSONB rows hold
--   whatever width the embedding service answered with, and vector(768) cannot hold them.
--   That table needs its own ticket and its own migration; what makes it safe to leave
--   alone is that the dual write and R59's filter both live in chunks/chunk_vectors.
-- * 0007_document_chunk_count.sql:41 says "vectors still belong to Chroma alone". That
--   sentence stays true of the read path and stops being true of the storage path here.
--   0007 is not edited: a checked-in migration is immutable once its digest is recorded.
--
-- ========================================================= distance operator (U1)
-- The plan left U1 open: "算符与 Chroma 不一致 = 后面所有召回对比全部作废". Measured
-- against this build's dependency set (chromadb 1.5.9, python 3.11) with an in-memory
-- client and the exact call shape app/rag/retriever.py uses for its collection:
--
--   python -c "import chromadb;from chromadb.config import Settings;\
--   c=chromadb.EphemeralClient(Settings(anonymized_telemetry=False));\
--   print(c.get_or_create_collection('enterprise_docs').configuration)"
--
--   -> {'hnsw': {'space': 'l2', 'ef_construction': 100, 'ef_search': 100,
--                'max_neighbors': 16, 'resize_factor': 1.2, 'sync_threshold': 1000}, ...}
--
-- So the collection default is L2, i.e. pgvector's <-> operator and vector_l2_ops. That
-- is recorded in vector_scope.distance_function and re-asserted by
-- scripts/compare_vector_recall.py before it compares any ranking, because the value is a
-- per-collection default that code can still change. The index parameters are not
-- invented either: m and ef_construction mirror the measured max_neighbors=16 and
-- ef_construction=100 so both engines are configured the same way. hnsw over ivfflat is
-- the plan's decided choice (section 3, P1): the corpus is 96 documents, hnsw is usable
-- the moment it is built, and ivfflat needs trained lists before its recall means
-- anything.
--
-- ================================================================ dimension source
-- 768 is NOT hard-coded here. It is resolved in this order, and a migration that has to
-- guess refuses instead of guessing:
--
--   1. current_setting('app.embedding_dimension') -- the explicit operator override.
--      scripts/migrate.py cannot set a GUC, so declare it once per database and the
--      runner's own connection inherits it:
--          ALTER DATABASE enterprise_brain SET app.embedding_dimension = 768;
--   2. otherwise: RAISE. The runtime spelling of the same value is EMBEDDING_DIMENSION
--      (app/rag/indexing.py:44, whose default is 768 at :46); an operator has to set the
--      two together, which is exactly what failing here forces them to notice.
--
-- Widths already stored are never adopted silently: they are compared against the
-- override and a disagreement is a RAISE. R22 forbids two dimensions coexisting in one
-- database, so every path that could create that state stops the migration.
--
-- Idempotent and additive overall: no column is dropped, no row is deleted, and
-- re-running against an already-migrated database is a no-op. CREATE INDEX CONCURRENTLY
-- is deliberately not used -- the runner executes each file inside one transaction block
-- (app/db/migrations.py), where a concurrent build is not permitted.

-- ------------------------------------------------------------------ preflight guard
DO $r58_preflight$
DECLARE
    has_extension BOOLEAN;
    has_vector_dims BOOLEAN;
    extension_version TEXT;
BEGIN
    SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
        INTO has_extension;
    IF NOT has_extension THEN
        RAISE EXCEPTION '0010 needs the vector extension; 0001_core_resource_versions.sql creates it and has not run';
    END IF;

    SELECT extversion INTO extension_version FROM pg_extension WHERE extname = 'vector';

    -- vector_dims() arrived with pgvector 0.7. Every dimension guard below depends on it,
    -- so an older extension must stop the migration rather than silently skip them.
    SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'vector_dims')
        INTO has_vector_dims;
    IF NOT has_vector_dims THEN
        RAISE EXCEPTION '0010 needs pgvector >= 0.7 for vector_dims(); found %, which is too old to police dimensions', extension_version;
    END IF;
END
$r58_preflight$;

-- --------------------------------------------------------------- the vector contract
-- One row, machine-checkable: the profile this database's vectors were produced under,
-- and which arithmetic "similar" means here. app/rag/pg_store.py asserts its own
-- configuration against it before it writes a single vector, which is where U1 and R22
-- stop being prose in a document.
CREATE TABLE IF NOT EXISTS vector_scope (
    schema_version INTEGER PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    distance_function TEXT NOT NULL,
    hnsw_m INTEGER,
    hnsw_ef_construction INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT vector_scope_schema_version_check CHECK (schema_version = 1),
    CONSTRAINT vector_scope_dimension_check CHECK (dimension > 0),
    CONSTRAINT vector_scope_distance_function_check CHECK (distance_function IN ('l2', 'cosine', 'ip'))
);


-- ------------------------------------------------------------------ vector side table
-- chunks is the authorization table (owner_id, index_version_id, metadata) and it is
-- written by app/rag/indexing.py, which this ticket may not touch and whose insert never
-- carries an embedding (app/rag/indexing.py:110-119). chunk_vectors is therefore the table
-- the dual write actually targets: its primary key IS the Chroma id, so it is the
-- row-for-row PostgreSQL mirror of the enterprise_docs collection, which makes "Chroma has
-- it" and "PG has it" the same statement instead of two that can disagree.
--
-- The column is declared bare here and retyped to vector(<dim>) by the block below, in the
-- same transaction. That is not the objection raised against 0002: 0002 shipped bare and
-- stayed bare, so nothing could index or police it.
CREATE TABLE IF NOT EXISTS chunk_vectors (
    vector_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    classification TEXT,
    department TEXT NOT NULL DEFAULT '',
    content_sha256 TEXT,
    index_version_id TEXT,
    embedding vector NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    distance_function TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chunk_vectors_vector_id_check CHECK (vector_id <> ''),
    CONSTRAINT chunk_vectors_filename_check CHECK (filename <> ''),
    CONSTRAINT chunk_vectors_chunk_index_check CHECK (chunk_index >= 0),
    CONSTRAINT chunk_vectors_embedding_dimension_check CHECK (embedding_dimension > 0),
    CONSTRAINT chunk_vectors_distance_function_check CHECK (distance_function IN ('l2', 'cosine', 'ip')),
    -- The same key space the Chroma collection uses: one row per (document, ordinal).
    CONSTRAINT chunk_vectors_document_chunk_unique UNIQUE (filename, chunk_index)
);

COMMENT ON COLUMN chunk_vectors.content_sha256 IS
    'Chroma carries this as metadata key "hash" (app/rag/retriever.py:573); the SQL column keeps a name a reader can parse.';
COMMENT ON COLUMN chunk_vectors.classification IS
    'NULL means the writer supplied no classification, matching an absent metadata key rather than the empty string.';
COMMENT ON COLUMN chunk_vectors.department IS
    'Duplicated from the vector metadata so a filtered search can pre-filter without a join. owner_id is deliberately NOT duplicated: it is a document-level fact owned by the catalog, and a second copy of it here could drift from the authority. department and classification are not separable from the chunk the retriever already holds.';

-- ------------------------------------------------------------- resolve and police scope
-- Declared input, in priority order, with a refusal where a guess would be possible:
--   app.embedding_dimension      -> the width; EMBEDDING_DIMENSION is its runtime spelling
--   app.embedding_model          -> the label R22 binds index versions to; EMBEDDING_MODEL
--   app.vector_distance_function -> l2 | cosine | ip, default l2 for the reason measured in
--                                   the "distance operator (U1)" section above
DO $r58$
DECLARE
    declared_dimension TEXT;
    declared_model TEXT;
    declared_distance TEXT;
    vector_dimension INTEGER;
    stored_dimension INTEGER;
    stored_variants INTEGER;
    stored_rows BIGINT;
    model_name TEXT;
    distance_name TEXT;
    hnsw_m_setting INTEGER := 16;
    hnsw_ef_setting INTEGER := 100;
    has_scope BOOLEAN;
    scope_model TEXT;
    scope_dimension INTEGER;
    scope_distance TEXT;
    column_type TEXT;
    target_table TEXT;
BEGIN
    SELECT btrim(coalesce(current_setting('app.embedding_dimension', TRUE), '')),
           btrim(coalesce(current_setting('app.embedding_model', TRUE), '')),
           btrim(coalesce(current_setting('app.vector_distance_function', TRUE), ''))
        INTO declared_dimension, declared_model, declared_distance;

    SELECT count(DISTINCT vector_dims(embedding)),
           min(vector_dims(embedding)),
           count(embedding)
        INTO stored_variants, stored_dimension, stored_rows
        FROM chunks
        WHERE embedding IS NOT NULL;

    -- R22: one database holds one embedding shape. Mixed widths already in the table prove
    -- the index was rebuilt under another model, and no CHECK added here can retroactively
    -- separate them, so the migration stops instead of picking a winner.
    IF coalesce(stored_variants, 0) > 1 THEN
        RAISE EXCEPTION '0010 refuses to migrate: chunks.embedding already holds % different vector widths (narrowest %). R22 forbids mixed dimensions in one database; rebuild the index under a single embedding profile first.',
            stored_variants, stored_dimension;
    END IF;

    -- The width is never inferred from what is already stored. An empty chunks table is the
    -- normal state here, which would leave the column untyped forever; and a stored width is
    -- evidence about a past write, not an authorisation to keep it.
    IF declared_dimension = '' THEN
        RAISE EXCEPTION '0010 needs an explicit vector width and will not guess one. Declare it for this database before migrating: ALTER DATABASE %I SET app.embedding_dimension = <EMBEDDING_DIMENSION>; the runtime spelling of the same value is EMBEDDING_DIMENSION (app/rag/indexing.py:44, default at :46), and R22 binds every index version to model + dimension, so an operator has to set the two together.',
            current_database();
    END IF;
    IF declared_dimension !~ '^[1-9][0-9]*$' THEN
        RAISE EXCEPTION '0010 needs app.embedding_dimension to be a positive integer, found %', declared_dimension;
    END IF;
    vector_dimension := declared_dimension::INTEGER;

    IF stored_dimension IS NOT NULL AND stored_dimension <> vector_dimension THEN
        RAISE EXCEPTION '0010 refuses to migrate: app.embedding_dimension = % but chunks.embedding already holds % vectors of width %. R22 forbids two dimensions in one database; this database is already claimed by width %.',
            vector_dimension, stored_rows, stored_dimension, stored_dimension;
    END IF;

    -- pgvector caps hnsw at 2000 dimensions. Saying so here beats failing halfway through a
    -- CREATE INDEX that has already rewritten the column.
    IF vector_dimension > 2000 THEN
        RAISE EXCEPTION '0010 cannot index % dimensions with hnsw: pgvector supports at most 2000', vector_dimension;
    END IF;

    IF declared_model <> '' THEN
        model_name := declared_model;
    ELSIF stored_rows > 0 THEN
        RAISE EXCEPTION '0010 refuses to record an unlabelled profile: chunks.embedding holds % vectors but app.embedding_model is unset. Set it to the runtime EMBEDDING_MODEL (app/rag/indexing.py:43): R22 keys index versions on model + dimension, and a vector whose model is unknown cannot be bound to a version.',
            stored_rows;
    ELSE
        -- Nothing exists to label yet. pg_store.py reads 'unknown' as "unclaimed" and claims
        -- the row with the real model name on the first vector it writes.
        model_name := 'unknown';
    END IF;

    distance_name := coalesce(nullif(declared_distance, ''), 'l2');
    IF distance_name NOT IN ('l2', 'cosine', 'ip') THEN
        RAISE EXCEPTION '0010 does not know distance function %: app.vector_distance_function must be l2, cosine or ip', declared_distance;
    END IF;

    -- The scope row is a promise to the next reader, so re-running either agrees with it or
    -- stops. Adopting a new model name into a database whose vectors came from another model
    -- is precisely the silent reindex this ticket is forbidden to perform.
    SELECT EXISTS (SELECT 1 FROM vector_scope WHERE schema_version = 1)
        INTO has_scope;
    IF has_scope THEN
        SELECT embedding_model, dimension, distance_function
            INTO scope_model, scope_dimension, scope_distance
            FROM vector_scope
            WHERE schema_version = 1;
        IF scope_dimension <> vector_dimension THEN
            RAISE EXCEPTION '0010 refuses to migrate: vector_scope records dimension % but app.embedding_dimension is now %. The vectors already stored were produced under the recorded width; reindex them before changing it.',
                scope_dimension, vector_dimension;
        END IF;
        IF scope_distance <> distance_name THEN
            RAISE EXCEPTION '0010 refuses to migrate: vector_scope records distance_function % but app.vector_distance_function is now %. Changing the arithmetic invalidates scripts/compare_vector_recall.py and every recall comparison already recorded on this database.',
                scope_distance, distance_name;
        END IF;
        IF scope_model = 'unknown' THEN
            NULL; -- first real claim: keep the freshly declared model
        ELSIF model_name = 'unknown' THEN
            model_name := scope_model;
        ELSIF scope_model <> model_name THEN
            RAISE EXCEPTION '0010 refuses to migrate: vector_scope records embedding_model % but app.embedding_model is now %. R22 binds index versions to model + dimension: a stored vector cannot be relabelled, only rebuilt.',
                scope_model, model_name;
        END IF;
        UPDATE vector_scope
            SET embedding_model = model_name,
                hnsw_m = hnsw_m_setting,
                hnsw_ef_construction = hnsw_ef_setting,
                updated_at = NOW()
            WHERE schema_version = 1;
    ELSE
        INSERT INTO vector_scope
            (schema_version, embedding_model, dimension, distance_function, hnsw_m, hnsw_ef_construction)
            VALUES (1, model_name, vector_dimension, distance_name, hnsw_m_setting, hnsw_ef_setting);
    END IF;

    -- Type both columns, then police both. Dropping the vector index first keeps the rewrite
    -- from reading an index whose opclass is about to stop matching; the block below
    -- rebuilds it in the same transaction.
    FOREACH target_table IN ARRAY ARRAY['chunks', 'chunk_vectors'] LOOP
        SELECT format_type(atttypid, atttypmod)
            INTO column_type
            FROM pg_attribute
            WHERE attrelid = target_table::REGCLASS
              AND attname = 'embedding'
              AND attnum > 0
              AND NOT attisdropped;
        IF column_type IS NULL THEN
            RAISE EXCEPTION '0010 expects %.embedding to exist and cannot find its type', target_table;
        END IF;
        IF column_type <> 'vector(' || vector_dimension || ')' THEN
            EXECUTE format('DROP INDEX IF EXISTS %I', target_table || '_embedding_idx');
            EXECUTE format('ALTER TABLE %I ALTER COLUMN embedding TYPE vector(%s)', target_table, vector_dimension);
        END IF;
        -- The CHECK is rebuilt every run because the width it names is operator input: a
        -- constraint left over from another width would police the wrong number. The type
        -- modifier is the primary gate -- vector(<dim>) rejects a foreign width on input --
        -- and this is the belt behind it, which also survives somebody re-typing the column
        -- bare without re-running 0010. The NULL branch comes first so vector_dims() is
        -- never evaluated on a NULL embedding.
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', target_table, target_table || '_embedding_dims_check');
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I CHECK (embedding IS NULL OR vector_dims(embedding) = %s)',
            target_table, target_table || '_embedding_dims_check', vector_dimension);
    END LOOP;
END
$r58$;

-- ------------------------------------------------------------------------ vector index
-- hnsw, not ivfflat: the plan decided it (docs/handoff/2026-09-17-pgvector-adoption-plan.md
-- section 3, P1). A 96-document corpus is below the size where ivfflat's trained lists pay
-- off, and ivfflat recalls nothing at all until it has been trained on data, which a fresh
-- private install does not have. m and ef_construction mirror the measured Chroma defaults
-- (max_neighbors 16, ef_construction 100) rather than inventing tuned numbers.
--
-- The opclass has to match vector_scope.distance_function or the two engines rank
-- differently and every comparison between them is void -- which is why the block above
-- refuses to change a recorded function instead of quietly rebuilding around it.
DO $r58_index$
DECLARE
    distance_name TEXT;
    hnsw_m_setting INTEGER;
    hnsw_ef_setting INTEGER;
    target_table TEXT;
BEGIN
    SELECT distance_function, coalesce(hnsw_m, 16), coalesce(hnsw_ef_construction, 100)
        INTO distance_name, hnsw_m_setting, hnsw_ef_setting
        FROM vector_scope
        WHERE schema_version = 1;

    FOREACH target_table IN ARRAY ARRAY['chunks', 'chunk_vectors'] LOOP
        IF distance_name = 'cosine' THEN
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I USING hnsw (embedding vector_cosine_ops) WITH (m = %s, ef_construction = %s)',
                target_table || '_embedding_idx', target_table, hnsw_m_setting, hnsw_ef_setting);
        ELSIF distance_name = 'ip' THEN
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I USING hnsw (embedding vector_ip_ops) WITH (m = %s, ef_construction = %s)',
                target_table || '_embedding_idx', target_table, hnsw_m_setting, hnsw_ef_setting);
        ELSE
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I USING hnsw (embedding vector_l2_ops) WITH (m = %s, ef_construction = %s)',
                target_table || '_embedding_idx', target_table, hnsw_m_setting, hnsw_ef_setting);
        END IF;
    END LOOP;
END
$r58_index$;

-- ------------------------------------------------------------------ scalar pre-filters
-- pgvector filters after the graph walk unless a scalar index lets the planner start from
-- the rows a principal may read, so these are what make "authorization and retrieval in one
-- engine" more than a slogan (R59 uses them; R58 only provides them).
--
-- The chunks-side indexes are partial on embedding IS NOT NULL: they exist to serve filtered
-- vector search, and indexing.py has never written an embedding, so today they stay empty.
-- An unconditional index would instead compete with 0002's chunks_resource_idx for every
-- non-vector query while still not being the one a vector query wants.
CREATE INDEX IF NOT EXISTS chunks_owner_prefilter_idx
    ON chunks (owner_id)
    WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS chunks_index_version_prefilter_idx
    ON chunks (index_version_id)
    WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS chunks_department_prefilter_idx
    ON chunks (((metadata ->> 'department')))
    WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS chunks_classification_prefilter_idx
    ON chunks (((metadata ->> 'classification')))
    WHERE embedding IS NOT NULL;

-- The chunk_vectors-side indexes are unconditional: every row in that table has a vector by
-- definition (embedding NOT NULL), so a partial predicate there would be decoration.
CREATE INDEX IF NOT EXISTS chunk_vectors_filename_idx
    ON chunk_vectors (filename);

CREATE INDEX IF NOT EXISTS chunk_vectors_department_idx
    ON chunk_vectors (department);

CREATE INDEX IF NOT EXISTS chunk_vectors_classification_idx
    ON chunk_vectors (classification);

CREATE INDEX IF NOT EXISTS chunk_vectors_index_version_idx
    ON chunk_vectors (index_version_id);

-- ---------------------------------------------------------------------- chunks backfill
-- Why a trigger instead of a change to app/rag/indexing.py (which this ticket may not edit):
--
-- * chat.py calls retriever.add_document -- the vector write -- before it publishes the
--   index rows, so chunk_vectors is normally already filled by the time chunks rows arrive;
-- * the two id spaces differ: indexing.py builds chunk_id as
--   index_chunk_id(document_resource_version_id(filename, version), ordinal), i.e.
--   "<filename>|v<version>#<ordinal>" (app/rag/indexing.py:131-137), while the Chroma id --
--   and so chunk_vectors.vector_id -- is "<filename>_<ordinal>" (app/rag/retriever.py:568);
-- * _INSERT_CHUNK_SQL (app/rag/indexing.py:110-119) lists no embedding column at all, so
--   without this hook chunks.embedding would stay NULL forever and the column 0002 declared
--   would still be the one nothing reads.
--
-- Both derivations are guarded by content equality, and a guard that fails leaves embedding
-- NULL -- today's state -- rather than attaching somebody else's vector. A wrong embedding
-- is a correctness fault; a missing one is only a gap in the mirror.
CREATE OR REPLACE FUNCTION sync_chunk_embedding() RETURNS TRIGGER
LANGUAGE plpgsql
AS $r58_trigger$
BEGIN
    IF NEW.embedding IS NULL THEN
        IF NEW.metadata ? 'vector_id' AND jsonb_typeof(NEW.metadata -> 'vector_id') = 'string' THEN
            -- An explicit key wins, if a future writer ever supplies one.
            SELECT matched.embedding
                INTO NEW.embedding
                FROM chunk_vectors AS matched
                WHERE matched.vector_id = NEW.metadata ->> 'vector_id';
        ELSE
            -- Otherwise derive the Chroma id from the chunk id, and prove the match by text.
            SELECT matched.embedding
                INTO NEW.embedding
                FROM chunk_vectors AS matched
                WHERE matched.vector_id = split_part(NEW.chunk_id, '|v', 1) || '_' || NULLIF(split_part(NEW.chunk_id, '#', 2), '')
                  AND matched.content = NEW.content;
        END IF;
    END IF;
    RETURN NEW;
END
$r58_trigger$;

COMMENT ON FUNCTION sync_chunk_embedding() IS
    'Backfill chunks.embedding from the chunk_vectors mirror so authorization filtering and vector search can read one table. Never overwrites a stored vector; a guard that does not match leaves NULL.';

DROP TRIGGER IF EXISTS chunks_sync_embedding ON chunks;

CREATE TRIGGER chunks_sync_embedding
    BEFORE INSERT OR UPDATE OF embedding, metadata ON chunks
    FOR EACH ROW
    EXECUTE FUNCTION sync_chunk_embedding();
