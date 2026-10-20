-- Scope columns on the version chain: a dataset version answers for its own scope (request R256).
--
-- Before this file the version rows carried content but no scope. datasets (0002) holds
-- classification and department_ids and dataset_versions holds none, so every version-addressed
-- authorization question had exactly one place to be answered from: the parent row. That is a
-- widening hole, and it is one-directional in the worst sense. Re-registering the same logical
-- filename at a lower classification moves the only scope any version has, so the historical rows -
-- whose bytes were stored under a stricter rule than the one now in force - become readable under
-- the new, looser one. R249 named this and pinned it as it stands, in the case that documents a
-- lower classification on a later registration widening the whole chain; the antidote it pointed
-- at is the pair of columns this file adds.
--
-- No backfill, no UPDATE, no INSERT anywhere in this file, for the same reason 0012 and 0014 refuse
-- one. A scope written by the database would be a statement about a declaration nobody made.
-- Registration is the only moment the classification and the department set of a version are
-- actually known, so the only honest default is the one that says 'not recorded', and this schema
-- already spells that with the empty value (0012: the gap stays countable instead of being covered
-- up). A row this file touches therefore reads back as department_ids [] and classification ''
-- until something registers a version through app/storage/datasets.py, which is the one writer that
-- has ever stamped a real scope on one.
--
-- What the empty value costs, stated plainly rather than at delivery time. scope_for_version()
-- answers None for a version row carrying no recorded scope, and app/common/policy.py reads a
-- missing scope as resource_scope_missing - a denial, not a fallback to the parent. A database that
-- already holds version rows will find them unreadable by version after this file. That is the
-- point: unreadable is a true statement about bytes whose classification nobody recorded, while
-- inheriting the parent's current classification is the false one. Nothing here is repaired by
-- guessing. An operator recovers a version by registering that file again, which records the scope
-- it is being given now, and the history the old rows hold is untouched either way.
--
-- The two columns are a lower bound on the parent row, not a replacement for it. scope_for_version
-- takes the meet of the version's own scope and its dataset row's scope: the stricter
-- classification and the intersection of the department sets. That matters in the direction this
-- file is not fixing. A version whose own row says internal, under a dataset row later raised to
-- confidential, would otherwise become looser than its parent - the property R249 named when it
-- said a version is never its own looser resource - and a widening dressed as a bug fix is still a
-- widening.
--
-- Why neither column carries a CHECK. classification is a closed vocabulary
-- (app/common/policy.py::_CLASSIFICATION_LEVELS), and 0014 showed what a second copy of one costs:
-- a value set the product side and the DDL side must keep in step, plus a test whose only job is to
-- notice when they do not. alerts.status earns that cost because the database is where a
-- disposition has to be legal. A version's classification is not a state machine - it is a label
-- read by one policy function that already refuses a word it cannot rank (resource_scope_invalid) -
-- so a CHECK here would buy a third place to maintain and nothing else.
--
-- Why no index. Every read of these two columns is a lookup of one version row, by its primary key
-- or by (dataset_id, version_number), and 0002 already indexes both shapes
-- (dataset_versions_owner_idx and its UNIQUE (dataset_id, version_number)). Nothing selects
-- versions by department. A GIN index on department_ids would be a guess about a workload nobody
-- measured, which is the same reason 0014 built none.
--
-- Re-run shape. Both statements are ALTER TABLE IF EXISTS ... ADD COLUMN IF NOT EXISTS, so a
-- database that has never seen 0002's table skips with a notice instead of aborting the deployment
-- transaction, and a second run of this file is a no-op. No constraint is added, so the DROP
-- CONSTRAINT / ADD CONSTRAINT pairing 0013 and 0014 need is not needed here, and nothing is
-- dropped: no DROP TABLE, no DROP COLUMN.

ALTER TABLE IF EXISTS dataset_versions
    ADD COLUMN IF NOT EXISTS department_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS dataset_versions
    ADD COLUMN IF NOT EXISTS classification TEXT NOT NULL DEFAULT '';

-- Recorded where the only reader that can see it is an operator holding a psql prompt against the
-- customer database. Neither COMMENT restates the classification vocabulary or the policy that
-- reads it: 0014's lesson was that every copy is one more thing to keep in step.
COMMENT ON COLUMN dataset_versions.department_ids IS
    'The departments this version was registered for, as recorded at registration. An empty array
    means it was never recorded: no migration infers one for a row written before this file, and a
    version with no recorded departments is not authorized by guessing what its parent would say.
    Read as the intersection with datasets.department_ids, never as a union.';

COMMENT ON COLUMN dataset_versions.classification IS
    'The classification this one version was registered under. The empty string means it was never
    recorded, which is a denial rather than a fallback: app/common/policy.py answers a missing scope
    with resource_scope_missing. It is never inherited from the datasets row, because that is the
    row a later registration moves, and moving it must not retrospectively loosen a version that
    was stored under a stricter rule.';
