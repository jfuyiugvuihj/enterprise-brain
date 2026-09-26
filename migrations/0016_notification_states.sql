-- Reader lifecycle states for the notification inbox (request R299).
--
-- The platform has always been able to push an alert out, but it had no answer to "who is
-- supposed to look at what": there was no inbox, no per-person read state, and nowhere to park a
-- dismissal. R299 adds the inbox as a read model over the three ledgers that already exist -- the
-- HITL approval ledger (pending_approvals, 0008 and 0013), the alert ledger (alerts, 0003, 0012
-- and 0014) and the document catalog (document_versions, 0006 and 0007). This file creates the one
-- piece of state that read model genuinely needs and that no existing table can hold: what a
-- single recipient has already looked at.
--
-- Read that last paragraph again, because it is the whole design. This table is not a notification
-- ledger. It stores no message body, no severity, no recipient list, and no copy of any alert,
-- parked turn or document. Those three tables remain the source of truth for what exists; a row
-- here says only that this person has read, or has dismissed, this one. The inbox is assembled per
-- request by reading the three ledgers through their own read paths (app/notifications/sources.py),
-- so a second account of open work cannot come into being here: there is nothing that could fall
-- out of step, and closing an alert in its own ledger takes it out of every inbox the next time
-- anybody looks. R278 deleted a badge rather than let a number be invented beside the ledger it
-- described. This file is the same refusal written the other way round: the state that is genuinely
-- new is reader state, and it is the only thing stored.
--
-- Why no department or classification column. A scope copy here would be a second answer to "who
-- may see this", and the platform has exactly one of those (app/common/policy.py, with the
-- row-level alert predicate in app/api/v1/alerts.py beside it). It would also be wrong in the
-- dangerous direction: a document moved to another department, or an alert whose attribution was
-- corrected, would keep an inbox entry addressed to the scope it had when the row was written.
-- Visibility is therefore resolved against the source row at read time and this table stays blind
-- to it. That is also why there is no backfill: 0012 and 0015 each refuse to invent a scope for a
-- row that never recorded one, and an inbox has no right to be the first place that guesses.
--
-- Why unread is the absence of a row. The alternative -- fan out one row per notification and
-- recipient when something happens -- is precisely the second ledger this file exists not to be.
-- It would need a writer at every event source, it would grow with the corpus whether or not
-- anybody read it, and every missed write would be a notification nobody can receive again.
-- Absence is also the house spelling for the cheaper half of this question: alerts.read defaults
-- to FALSE and nothing inserts a row to announce that an alert has not been opened yet, which is
-- the asymmetry 0014 records for the disposition columns.
--
-- Why the state set is two words and not three. Read and dismissed are the only two things a
-- reader can do, and both arrive through an explicit action. Unread is what a reader has not done
-- yet, so it has no row to live in. The CHECK below is a closed set in the only shape PostgreSQL
-- can hold one. Its Python-side twin is NOTIFICATION_STATES in app/notifications/contracts.py, and
-- the duplication is tolerated, not forgotten: tests/test_r299_notification_states.py replays this
-- file through app.db.migrations and compares the set the CHECK admits against that enumeration on
-- every run, the same arrangement 0014 sets up with tests/test_r251_alert_disposal.py.
--
-- Why the two timestamps are TEXT written by the process. This is the reason 0014 already gives,
-- kept: the store has two legs (PostgreSQL, and the offline in-memory list that every test and
-- every air-gapped development machine runs on), and NOW() would let the two legs spell the same
-- fact in two shapes. One clock in app/notifications/states.py stamps both legs, so a read and a
-- re-read agree to the character. The empty string stays this schema spelling for "not recorded"
-- (0012) and is reachable only by a row written before the column pair existed; no writer is
-- allowed to leave it blank.
--
-- First install and re-run, in that order. CREATE TABLE IF NOT EXISTS with table-level constraints
-- is repeatable by construction, and the index carries IF NOT EXISTS, so a second pass stores
-- nothing differently. Nothing is dropped, and no INSERT or UPDATE statement appears in this file:
-- a lifecycle row written by the migration would claim that somebody read something, and nobody
-- did. The unique key is what makes the write endpoint idempotent down at the storage layer -- a
-- double tap on read lands on one row and reports the same conclusion twice -- and the index on
-- recipient is the one measured access pattern (every lifecycle row this person holds), not a
-- guess about a report nobody has asked for.
CREATE TABLE IF NOT EXISTS notification_states (
    id BIGSERIAL PRIMARY KEY,
    notification_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'read',
    recorded_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    CONSTRAINT notification_states_id_not_empty CHECK (notification_id <> ''),
    CONSTRAINT notification_states_recipient_not_empty CHECK (recipient <> ''),
    CONSTRAINT notification_states_state_check
        CHECK (state IN ('read', 'dismissed')),
    CONSTRAINT notification_states_reader_key UNIQUE (notification_id, recipient)
);

-- The inbox read: every lifecycle row one recipient holds, overlaid on the candidates the three
-- ledgers just produced. State is deliberately not in the key -- reader_key above already
-- guarantees one row per notification per person, and the whole set is small enough to overlay in
-- a single pass. Filtering by state here would be a second opinion about what unread means, and
-- that conclusion belongs to the read model.
CREATE INDEX IF NOT EXISTS notification_states_recipient_idx
    ON notification_states (recipient);

COMMENT ON TABLE notification_states IS
    'Reader lifecycle state (read or dismissed) for the R299 inbox. Deliberately not a notification
    ledger: the body of every notification lives in pending_approvals, alerts or document_versions,
    and this table holds only what one recipient has already done about it. The absence of a row
    means unread.';

COMMENT ON COLUMN notification_states.notification_id IS
    'Stable identity of the notification, spelled <source_type>:<source_record_id> by
    app/notifications/contracts.py -- approval:<session_id>, alert:<alerts.id>,
    document:<filename>#v<version>. Stable across processes and restarts because it is derived from
    the key the source row already carries, never from anything this table generates.';

COMMENT ON COLUMN notification_states.state IS
    'read or dismissed. The closed value set is the CHECK constraint on this column. The
    product-side enumeration, and the only place the two words are named for the application, is
    NOTIFICATION_STATES in app/notifications/contracts.py, kept in step by
    tests/test_r299_notification_states.py. Unread is not a third word here: it is the absence of a
    row for this notification and this recipient.';

COMMENT ON COLUMN notification_states.recipient IS
    'Username, the same identity key 0014 chose for alerts.assignee. It is the one spelling both
    halves of the auth module agree on: app/common/auth.py::get_user looks people up by username,
    and Principal.from_user falls back to the same string when the row carries no id column.';
