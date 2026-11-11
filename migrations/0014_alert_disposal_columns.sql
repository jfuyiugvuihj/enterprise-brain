-- Disposition columns for the alert ledger: confirm / assign / close become a closed loop (request R251).
--
-- Before this file an alert could only be read. Nothing in the route could say "I am taking this
-- one", "it is that person's now", or "it is finished", so every sweep left another open row on the
-- ledger and there was no place to record the decision a human actually made about it. Three
-- actions, and each of them has to answer who did it and when: that is what these eight columns hold.
--
-- No backfill, no UPDATE, no INSERT anywhere in this file, for the same reason 0012 refuses one. A
-- disposition written by the database would be a statement about a decision nobody made. Existing
-- rows therefore take the column defaults and nothing else: status 'open' -- nobody has acted on it
-- -- and the empty string for every actor, assignee and timestamp, which is this schema's existing
-- spelling for "not recorded" (0012: the gap stays countable instead of being covered up). It is
-- never an invented name and never an inferred time.
--
-- Why status and read stay two axes. alerts.read is the notification flag the dashboard tile counts
-- (app/api/v1/dashboard.py::_alert_counts, pinned by tests/test_r188_alert_count_row_scope.py) and it
-- answers "has anybody opened this". status answers "has anybody decided what to do about this".
-- Confirming an alert is a business decision, not evidence about a notification, and folding one
-- into the other would let a new endpoint silently rewrite a measured contract: a department's whole
-- unread count would move because someone acked an alert.
--
-- Where the vocabulary lives. ALERT_STATUSES / ALERT_TERMINAL_STATUSES / ALERT_DISPOSAL_RULES in
-- app/api/v1/alerts.py is the product-side enumeration and the only place the legal transitions are
-- written. The CHECK below is a second copy because a CHECK is the only shape in which PostgreSQL
-- can hold a closed set. That duplication is tolerated, not forgotten:
-- tests/test_r251_alert_disposal.py replays this file through app.db.migrations and compares the
-- value set the CHECK admits against ALERT_STATUSES on every run, so a word added on one side
-- without the other goes red there rather than in front of a customer.
--
-- Assign deliberately does not move status. Routing an alert says who holds it, not that anybody has
-- decided anything, so the assignee still has to confirm it themselves and a re-assign never closes
-- or reopens anything. The actor and assignee columns carry a username, not a user id: that is the
-- one identity key both halves of the auth module agree on (app/common/auth.py::get_user looks
-- people up by username, and Principal.from_user falls back to the same string when the row has no
-- id column), so a user id here would put two spellings of one person in one column.
--
-- First install and re-run, in that order. Every ADD COLUMN carries IF NOT EXISTS, and the column is
-- added before the constraint that reads it, so a database that has never seen alerts builds the
-- column from 0003's table plus this file and takes the CHECK over rows that all say 'open'. The
-- constraint ships as a DROP CONSTRAINT IF EXISTS / ADD CONSTRAINT pair -- the pairing 0013
-- established for exactly this reason, since PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, and a
-- second run of this file therefore drops and re-adds an identical definition and stores nothing
-- differently. Every statement also carries ALTER TABLE IF EXISTS, so a database with no 0003
-- compatibility table skips with a notice instead of aborting the deployment transaction.
--
-- Nothing is dropped and no index is built: no DROP TABLE, no DROP COLUMN. An index on status would
-- be a guess about a workload nobody measured -- the ledger is read through alert_row_scope_sql(),
-- whose predicate is about department, and 0003 already ships alerts_created_idx for the newest-first
-- read that is the only measured access pattern.

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS acknowledged_by TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS acknowledged_at TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS closed_by TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS closed_at TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS assignee TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS assigned_by TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS assigned_at TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS alerts
    DROP CONSTRAINT IF EXISTS alerts_status_check;

ALTER TABLE IF EXISTS alerts
    ADD CONSTRAINT alerts_status_check
        CHECK (status IN ('open', 'acknowledged', 'closed'));

-- Recorded where the only reader that can see it is an operator holding a psql prompt against the
-- customer database. The value set is NOT restated here on purpose: a COMMENT naming the three words
-- would be a third copy to keep in step, and the CHECK above is already the second one.
COMMENT ON COLUMN alerts.status IS
    'Disposition state of this alert. The closed value set is the CHECK constraint on this column.
    The product-side enumeration, and the only spelling of the legal transitions, are ALERT_STATUSES
    and ALERT_DISPOSAL_RULES in app/api/v1/alerts.py, kept in step by tests/test_r251_alert_disposal.py.';

COMMENT ON COLUMN alerts.assignee IS
    'Who this alert is routed to, by username. The empty string means nobody has routed it. Routing
    moves the holder, never the disposition state -- the assignee still has to confirm it themselves.';
