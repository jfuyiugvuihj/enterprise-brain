-- The cached-token counter needs a column of its own (request R523, R43 judgement 2).
--
-- The reading already exists. The native /api/chat done frame reports
-- prompt_eval_cached_count, app/common/model_handler.py copies it onto the reply, and
-- app/trace/spans.py sets counts["cached_tokens"] beside the other two counters -- only when
-- the reply really carried one, never as a zero and never as input_tokens - cached_tokens.
-- What does not exist is anywhere to put it: model_calls (0002) stops at input_tokens,
-- output_tokens, error_code and metadata, and the word "cached" does not appear anywhere
-- under migrations/. A number this platform has already metered is therefore dropped at the
-- last step, so R43 judgement 2 ("the cached count the model reports has to reach the
-- ledger") cannot be read off any customer database until a column holds it. This file is
-- that column and nothing else.
--
-- INTEGER, nullable, no DEFAULT, no backfill, no UPDATE -- and NULL here is a fact, not a
-- gap to be filled in. Two different answers reach this column and they must still be two
-- answers once they are stored:
--
--   * NULL -- this call reported no cached count. That is the shape of every streamed answer
--     turn: the compatible leg's stream carries no usage object at all, so input, output and
--     cached are all unmeasurable from it (跟进单 §74 四、§81; the verbatim frames are in
--     tests/test_r29_thinking_tax.py section D). It is also the shape of every row written
--     before this file existed. A DEFAULT would have invented a number for all of them, and
--     a backfill would have invented one for the old rows -- after which the column stops
--     being evidence of anything, because "the server said 0" and "nobody ever asked" would
--     read the same.
--   * 0 -- the server said zero. That really happens on this host: docs/perf/raw/
--     prodpath.jsonl reports 0 of a 116-token prompt on one round while two others report
--     292 and 257. Collapsing that NULL and this 0 into one face is precisely the misreading
--     app/trace/spans.py warns a reader against ("a streamed round with no cached_tokens
--     means the stream could not say, never the prefix cache did not hit").
--
-- Why a real column rather than the metadata jsonb already on the table. input_tokens and
-- output_tokens are columns, and these three counters are one fact stated three times by one
-- reply; putting the third in a jsonb bag would give the same measurement two shapes, one of
-- them unqueryable, and would hide it from the readout that names columns.
-- tests/test_r146_cached_token_ledger.py already pins that the cached count is not smuggled
-- through metadata today, and this file does not reverse that.
--
-- Why no CHECK and no constraint of any kind. This is a reading, not a state machine: the
-- vocabulary belongs to the server, and 0014 and 0015 each recorded what keeping a second
-- copy of a legal-value set in DDL costs. There is deliberately no generated column and no
-- expression either -- prompt_eval_count minus cached_tokens is arithmetic done to a reading,
-- and 跟进单 §21（「不得估算冒充实测 token 数」）keeps it out of the ledger. Writing it as a
-- computed column would put that refusal in SQL, where no metering-boundary test can see it.
--
-- Why no index. Every read of one of these rows is by model_call_id or by agent_run_id, and
-- 0002 already indexes those keys plus (owner_id, started_at DESC). Nothing selects model
-- calls by their cached count, so an index here would be a guess about a workload nobody has
-- measured.
--
-- Both installation paths have to keep walking, and that is the shape this statement is
-- written in. R90b's 事故 was a migration that stopped a clean install; 0010 still reads a
-- database-level embedding profile and can stop one today. This file reads nothing: no GUC,
-- no data, no session setting. ADD COLUMN IF NOT EXISTS is a no-op on a database that has
-- already run it, and ALTER TABLE IF EXISTS is a notice rather than an abort on a database
-- that never had model_calls at all. So a fresh install -- 0002 creates the table, this file
-- then adds the column -- and an install that has already reached 0017 both apply it in one
-- pass, and re-applying it applies nothing. Nothing is dropped and no existing column is
-- rewritten, so the rows that are already there stay readable.
--
-- Runtime imports still create nothing -- this file runs only under scripts/migrate.py, per
-- migrations/README.md.

ALTER TABLE IF EXISTS model_calls
    ADD COLUMN IF NOT EXISTS cached_tokens INTEGER;

COMMENT ON COLUMN model_calls.cached_tokens IS
    'Cached prompt tokens this call reported, in the server''s own words: native '
    'prompt_eval_cached_count, or usage.prompt_tokens_details.cached_tokens on the compatible '
    'leg. NULL means this call reported no cached count -- every streamed answer turn, whose '
    'frames carry no usage object, and every row written before this column existed. 0 means '
    'the server reported zero. The two are never collapsed into one, and this value is never '
    'computed: it is not input_tokens minus anything.';
