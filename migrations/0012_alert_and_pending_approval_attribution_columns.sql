-- Attribution columns for the two ledgers whose shipped code already reads them (R184 + R183).
--
-- Two columns, one file, deliberately. The alert ledger is fail-closed without its column:
-- _ensure() in app/api/v1/alerts.py raises rather than answer a department-scoped read with a
-- company-wide one, and list_alerts() pushes alert_row_scope_sql() into the query itself, so a
-- backend image that expects alerts.department meets a database that cannot answer it. The
-- parking ledger is the other half of the same sentence: R172 carries a declared lane on the
-- record, 0008 has no column for it, and tests/test_r172_lane_across_hitl.py pins that its
-- INSERT must not bind a column the catalog does not have. Landing one column without the
-- other leaves a deployed revision in which one side reads "this column exists, that table
-- still has nothing", so the two ALTERs ship as one version and the gap between two migration
-- runs never opens.
--
-- Neither column carries a backfill, and there is no UPDATE anywhere in this file. That
-- absence is the point. A department inferred from rule_id, or looked up in the dataset
-- registry, or copied from whoever happens to be reading, is a false attribution written into
-- the customer's own database, and the row gate would then defend that invention as if it were
-- evidence. The same trap one step further: an old parked row never recorded a lane, and
-- filling one in would turn "nobody declared this" into "the caller declared this", which is
-- precisely the third state R141 and R172 forbade. Both columns therefore take the empty
-- string for existing rows: the gap stays countable instead of being covered up.
--
-- The empty string is not a meaning invented here. alert_row_visible() and
-- alert_row_scope_sql() already treat "department IS NULL OR department = ''" as unattributed,
-- which keeps such a row visible to a subject who cleared the resource-level gate -- the same
-- mind app/common/policy.py holds for an ownerless document. The columns are NOT NULL, so the
-- default is not a third state either: a row either names its owner or names the absence of
-- one, and it always says one of those two things.
--
-- No CHECK constraint on declared_lane. The value set belongs to LANE_TIERS in
-- app/agents/nodes.py, and normalize_declared_lane() is its only normalizer: it raises on an
-- unknown spelling instead of letting a typo read as "not declared". Enumerating that set
-- again in DDL would build a second source of truth, free to drift from the first.
--
-- No index on alerts.department. The predicate is a disjunction of an empty-string test and an
-- array overlap, and a btree on the column serves neither; writing one here would be a guess
-- about a workload nobody measured.
--
-- Additive and re-runnable: every statement is guarded, nothing is dropped, and re-applying
-- this file is a no-op. Runtime imports still create nothing -- this file runs only under
-- scripts/migrate.py, per README.

ALTER TABLE IF EXISTS alerts
    ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS pending_approvals
    ADD COLUMN IF NOT EXISTS declared_lane TEXT NOT NULL DEFAULT '';

-- Recorded where the only reader that can observe an empty string will see it: an operator
-- holding a psql prompt against the customer database.
COMMENT ON COLUMN alerts.department IS
    'Owning department, comma separated. The empty string means unattributed: such a row stays
    visible to any subject who cleared the resource-level gate. Never inferred, never backfilled.';
COMMENT ON COLUMN pending_approvals.declared_lane IS
    'Lane declared by the caller of the parked turn: qa, analysis or report. The empty string
    means the row carries no declaration. Normalized by normalize_declared_lane() in
    app/agents/nodes.py, which is the only place that set is enumerated.';
