-- Metric-definition semantics promoted into real columns (request R15-b).
--
-- Two debts are paid here, both of which app/semantics/registry.py had already
-- admitted in its own module docstring:
--
-- 1. The table has always been "the authoritative store for what a business metric
--    means", but it could not hold what a metric is *called*. metric_definitions had
--    the calculation contract (formula, unit, period, currency, timezone, source scope,
--    filters, status) and nothing else, so the display label, the prose definition, the
--    wording a question is matched against, the granularity and the provenance origin
--    travelled inside the `filters` JSONB under the reserved `semantics` key. That is a
--    smuggled payload, not a schema: it cannot be queried, cannot be constrained, cannot
--    be indexed, and every reader has to know the private key to see the definition at
--    all. These five fields become real columns and the JSONB stops being the source of
--    truth for them.
-- 2. "This definition was reconciled with an uploaded policy document" had nowhere to
--    live, so the module could only ever answer `verified_against_documents = false` and
--    attach an "unreconciled" warning to every single definition. A warning that can
--    never be removed is noise, not provenance. The verification columns below turn it
--    into a closed enumeration whose satisfied state is backed by named evidence.
--
-- The two are the same feature: a candidate business relation that a human has checked
-- against a document has to land somewhere, and that somewhere is now a row that says
-- which document and which section. See app/knowledge_graph/promotion.py and
-- docs/design/knowledge-graph-positioning.md.

-- --------------------------------------------------------------------- semantics
-- All of these stay nullable: a row whose label nobody recorded must keep reading as
-- "no label was recorded" rather than as an empty label, and the read path falls back to
-- the derived display name. NULL is the honest absence; "" would be a claim.

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS metric_name TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS definition_text TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS time_granularity TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS origin TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS match_terms JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS metric_definitions
    DROP CONSTRAINT IF EXISTS metric_definitions_match_terms_check;

ALTER TABLE IF EXISTS metric_definitions
    ADD CONSTRAINT metric_definitions_match_terms_check
    CHECK (jsonb_typeof(match_terms) = 'array');

-- ------------------------------------------------------------- verification state
-- unverified: nothing has been reconciled with an uploaded document. This is the state
--   every pre-existing row is in, and the state the code fallback always reports.
-- verified: a named approver read the source document at a named section and certified
--   the definition. Reaching it requires the evidence columns, which is what stops a
--   self-declared flag from being its own proof.
-- rejected is deliberately NOT a value here: a rejected reconciliation belongs to the
--   candidate relation (app/knowledge_graph/service.py), not to a catalog row, and a
--   definition that failed review must not linger in the table that answers questions.

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS verification_state TEXT NOT NULL DEFAULT 'unverified';

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS verified_document TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS verified_section TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS verified_by TEXT;

ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

ALTER TABLE IF EXISTS metric_definitions
    DROP CONSTRAINT IF EXISTS metric_definitions_verification_state_check;

ALTER TABLE IF EXISTS metric_definitions
    ADD CONSTRAINT metric_definitions_verification_state_check
    CHECK (verification_state IN ('unverified', 'verified'));

ALTER TABLE IF EXISTS metric_definitions
    DROP CONSTRAINT IF EXISTS metric_definitions_verified_evidence_check;

-- The evidence is the point: "verified" without a document, a section, an approver and a
-- moment is exactly the overstated provenance this migration exists to remove. The CHECK
-- is one-directional on purpose - an unverified row may keep stale evidence after a
-- verification was withdrawn, and the read path ignores every evidence column unless the
-- state says verified.
ALTER TABLE IF EXISTS metric_definitions
    ADD CONSTRAINT metric_definitions_verified_evidence_check
    CHECK (
        verification_state <> 'verified'
        OR (
            nullif(btrim(coalesce(verified_document, '')), '') IS NOT NULL
            AND nullif(btrim(coalesce(verified_section, '')), '') IS NOT NULL
            AND nullif(btrim(coalesce(verified_by, '')), '') IS NOT NULL
            AND verified_at IS NOT NULL
        )
    );

-- The lineage link from a promoted definition back to the candidate relation it came
-- from. Nullable because the overwhelming majority of rows are curated by hand and never
-- passed through the graph at all.
ALTER TABLE IF EXISTS metric_definitions
    ADD COLUMN IF NOT EXISTS source_relation_id TEXT;

-- ------------------------------------------------------------------------ backfill
-- Only rows that still say nothing get filled, from the payload that used to be the only
-- place the value existed, so re-running this file changes nothing a second time and a
-- row the application already wrote through its real columns is never rewritten from the
-- older JSONB copy. definition_text falls back to formula because that is what the read
-- path did when no prose was recorded. The reserved key stays in `filters` afterwards:
-- app/semantics/registry.py keeps writing it for one release so that an application
-- rollback without a schema rollback does not lose the label, and it stops being read
-- once that window closes.
WITH smuggled AS (
    SELECT metric_definition_id,
           nullif(btrim(coalesce(filters -> 'semantics' ->> 'metric_name', '')), '')
               AS smuggled_metric_name,
           nullif(btrim(coalesce(filters -> 'semantics' ->> 'definition_text', '')), '')
               AS smuggled_definition_text,
           nullif(btrim(coalesce(filters -> 'semantics' ->> 'time_granularity', '')), '')
               AS smuggled_time_granularity,
           nullif(btrim(coalesce(filters -> 'semantics' ->> 'origin', '')), '')
               AS smuggled_origin,
           CASE
               WHEN jsonb_typeof(filters -> 'semantics' -> 'match_terms') = 'array'
                   THEN filters -> 'semantics' -> 'match_terms'
               ELSE '[]'::jsonb
           END AS smuggled_match_terms
    FROM metric_definitions
    WHERE jsonb_typeof(filters) = 'object'
      AND jsonb_typeof(filters -> 'semantics') = 'object'
)
UPDATE metric_definitions AS md
SET metric_name      = coalesce(md.metric_name, smuggled.smuggled_metric_name),
    definition_text  = coalesce(md.definition_text, smuggled.smuggled_definition_text,
                                nullif(btrim(md.formula), '')),
    time_granularity = coalesce(md.time_granularity, smuggled.smuggled_time_granularity),
    origin           = coalesce(md.origin, smuggled.smuggled_origin),
    match_terms      = CASE
                           WHEN coalesce(md.match_terms, '[]'::jsonb) = '[]'::jsonb
                               THEN smuggled.smuggled_match_terms
                           ELSE md.match_terms
                       END
FROM smuggled
WHERE md.metric_definition_id = smuggled.metric_definition_id
  AND (
        md.metric_name IS NULL
        OR md.definition_text IS NULL
        OR md.time_granularity IS NULL
        OR md.origin IS NULL
        OR coalesce(md.match_terms, '[]'::jsonb) = '[]'::jsonb
  );

-- Nothing is backfilled into the verification columns, and that is not an oversight. The
-- reserved JSONB key could hold any field an operator pasted in, so a "verified" flag
-- smuggled in the same place as the label would let a row certify itself. A row only
-- becomes verified through a write that names the approver, the document and the section.

-- -------------------------------------------------------------------------- indexes
-- The catalog answer to "how much of this catalog is still unreconciled" and the review
-- queue "show me what nobody has checked yet" both lead with the state.
CREATE INDEX IF NOT EXISTS metric_definitions_verification_idx
    ON metric_definitions (verification_state, owner_id, metric_id);

-- A promotion must be replayable: register_metric_definition targets
-- UNIQUE (owner_id, metric_id, definition_version), so re-promoting the same relation to
-- the same version revises one row instead of minting a second. This index is the audit
-- direction of that question - "which definition did this relation become".
CREATE INDEX IF NOT EXISTS metric_definitions_source_relation_idx
    ON metric_definitions (source_relation_id)
    WHERE source_relation_id IS NOT NULL;

COMMENT ON TABLE metric_definitions IS
    'Authoritative business metric definitions: calculation contract, the wording a question is matched against, and how far its reconciliation with an uploaded document has got';
COMMENT ON COLUMN metric_definitions.metric_name IS
    'Display label; NULL means none was recorded and the reader derives one from metric_id';
COMMENT ON COLUMN metric_definitions.definition_text IS
    'Prose definition; NULL means none was recorded and the reader shows the formula instead';
COMMENT ON COLUMN metric_definitions.match_terms IS
    'JSONB array of business wording a question is matched against; explicit terms beat wording derived from metric_id/formula';
COMMENT ON COLUMN metric_definitions.origin IS
    'code_registry when a row was seeded from the fallback rules, operator when a human or a promotion recorded it';
COMMENT ON COLUMN metric_definitions.verification_state IS
    'unverified|verified; verified requires verified_document, verified_section, verified_by and verified_at, enforced by a CHECK';
COMMENT ON COLUMN metric_definitions.verified_document IS
    'The uploaded document a definition was reconciled against; ignored unless verification_state = verified';
COMMENT ON COLUMN metric_definitions.verified_section IS
    'The section or locator inside that document; the answer to "who checked what, where"';
COMMENT ON COLUMN metric_definitions.source_relation_id IS
    'The candidate business relation this definition was promoted from, when it came through the knowledge graph';
