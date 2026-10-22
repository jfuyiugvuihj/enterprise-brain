-- Generation lineage for artifacts (request R509, forensics in R503).
--
-- "Which question produced this chart" has no durable answer today: the artifacts table
-- carries no session or request column, ArtifactRegistry.register() accepts neither, and the
-- one jsonb cell that could hold them is read back through the SCOPE_METADATA_KEYS allow list
-- (app/storage/artifacts.py), so anything smuggled in is dropped on the way out. R503 proved
-- that and stopped; this file is the column half of the fix, with nothing else mixed in.
--
-- Both columns are nullable TEXT and neither has a DEFAULT, because NULL is the whole meaning
-- of an old row: "this deployment never recorded which turn produced it". A backfill would
-- invent that fact -- created_at does not name a conversation, and copying the request_id of
-- whoever reads or deletes the row (audit_events.request_id, migrations/0005) would put the
-- visitor's identity onto a stored artifact, which is the false-green R503 blade K2 named.
-- 0012 took the same line for its two columns and shipped no UPDATE statement; this file
-- ships none either.
--
-- The empty string is deliberately not the "unrecorded" spelling here, even though 0012 and
-- 0016 use it. Those two columns are NOT NULL, so they have to name an absence; these two are
-- nullable, and register() folds an empty value to NULL rather than storing a blank. A row
-- then says one of exactly two things -- it names the generating turn, or it names nothing --
-- and the API can honour "absent, never null": no key in the JSON at all when the column is
-- NULL, so a reader cannot fold "" and "unrecorded" into the same face on screen.
--
-- Two nullable columns and no CHECK, no FK, no second identity concept. source_version_id
-- (0001) already answers "which dataset version", which is a different question; reusing it
-- for a conversation would merge two identities in one column. And the lineage is not borrowed
-- from agent_runs by joining on request_id: that table only has a row when the orchestrator
-- actually ran, so a direct POST /chart or POST /export artifact would join to nothing, and
-- "joined to nothing" means neither "never generated" nor "no question". Both writers name
-- their own turn instead.
--
-- Both indexes are for the read the request asks for and nothing more: the row surface is
-- (session_id, request_id) -> "what did that turn make", and both are looked up by equality
-- on the indexed column. A btree over a mostly-NULL column is cheap and NULLs are not the
-- target of any query here, so neither index is a guess about an unmeasured report.
--
-- Additive and re-runnable: guarded ALTER and CREATE INDEX, nothing dropped, nothing rewritten.
-- Runtime imports still create nothing -- this file runs only under scripts/migrate.py, per
-- migrations/README.md.

ALTER TABLE IF EXISTS artifacts
    ADD COLUMN IF NOT EXISTS session_id TEXT;

ALTER TABLE IF EXISTS artifacts
    ADD COLUMN IF NOT EXISTS request_id TEXT;

CREATE INDEX IF NOT EXISTS artifacts_session_idx ON artifacts (session_id);

CREATE INDEX IF NOT EXISTS artifacts_request_idx ON artifacts (request_id);

COMMENT ON COLUMN artifacts.session_id IS
    'Conversation that generated this artifact, as the Agent runtime named it (configurable '
    'thread_id). NULL means this deployment never recorded one -- it does not mean no question '
    'was asked. Never backfilled, never inferred, never taken from the reading or deleting '
    'caller.';

COMMENT ON COLUMN artifacts.request_id IS
    'Request that generated this artifact, taken from the Principal or the span identity at the '
    'moment of generation. NULL means unrecorded. This is not audit_events.request_id, which '
    'names the access or the deletion, not the generation.';