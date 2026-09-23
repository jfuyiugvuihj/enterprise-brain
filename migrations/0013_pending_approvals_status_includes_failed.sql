-- Widen the parked-turn status check to admit the turn the system lost (request R190).
--
-- R175 added a sixth terminal reading to the parking ledger, for the round an employee had
-- already approved and the runtime then crashed or timed out on. That row is none of the three
-- states nearest to it: nobody refused it, nobody pressed stop, and the graph is not what
-- stopped confirming it. Recording one of those instead would put words in the approver's mouth,
-- so the code side was right and the database side was the incomplete half.
--
-- The gap was measured, not guessed. 0008 closed the column over five spellings, so the PG
-- branch of mark_status() hit pending_approvals_status_check, _decide_pending_approval() logged
-- the exception, and the row stayed open -- on the approver's screen as a to-do that can never be
-- cleared, and in pending_approvals_open_session_idx as the slot that blocks that session's next
-- park. The local file ledger closed; the durable half did not.
--
-- A new version rather than an edit to 0008: that file is already applied in customer databases,
-- and its digest is carried by migrations/manifest.json and by each database's schema_migrations
-- ledger, so rewriting it would make every migrated database fail the loader's checksum
-- comparison. Shipped migrations are immutable; this file is the forward half of the sentence.
--
-- Purely forward: no UPDATE, no INSERT, no backfill, no DROP TABLE, and no statement that reads a
-- row. Dropping the check and re-adding it over a superset of the same value set cannot
-- invalidate anything already stored -- every row that satisfied the five-word check satisfies
-- this one -- so whatever the row count is, this file changes no row and reclassifies no history.
--
-- Where the vocabulary lives. The product-side enumeration is the block of constants that ends in
-- PG_STATUSES in app/storage/pending_approvals.py; the words written below are a second copy,
-- because a CHECK is the only shape in which PostgreSQL can hold a closed set. That duplication
-- is tolerated, not forgotten: tests/test_r190_status_failed_domain.py replays this statement
-- through app.db.migrations and compares the value set it produces against PG_STATUSES and
-- against ALL_STATUSES on every run, so a word added to one of the three without the other two
-- goes red there rather than in front of an approver. Nothing hand-copies the list into a test.
--
-- Re-runnable and guarded: each statement carries its own IF EXISTS guard, so a database that has
-- no pending_approvals table skips both with a notice instead of aborting the deployment
-- transaction, and re-applying this file drops the constraint and re-adds the identical
-- definition, leaving the same schema. The drop comes first on purpose -- PostgreSQL has no ADD
-- CONSTRAINT IF NOT EXISTS, so it is the pairing that makes a second run safe.
--
-- What this file deliberately does not do: it leaves 0008 alone, including that migration's
-- column comment, which names only the readings it knew about. Restating the six words a third
-- time in a COMMENT would hand the next reader three places to keep in step instead of two.

ALTER TABLE IF EXISTS pending_approvals
    DROP CONSTRAINT IF EXISTS pending_approvals_status_check;

ALTER TABLE IF EXISTS pending_approvals
    ADD CONSTRAINT pending_approvals_status_check
        CHECK (status IN ('awaiting', 'resumed', 'refused', 'abandoned', 'stale', 'failed'));
