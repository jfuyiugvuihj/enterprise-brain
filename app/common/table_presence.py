"""Ask a connection this repository already has, in one place, whether a table is really there.

Why this module exists (R392). A health report that answers ``postgres`` / ``durable`` is making a
claim about **a table**, not about a socket. ``app/common/auth.py`` keeps the repository's one
ratified answer to "can this process reach PostgreSQL" (``_db_ready``), and that answer says nothing
about whether some *other* table was ever created -- which is how, on one production machine, two
mouths said opposite things about the same cell: ``app/memory/profile.py`` reported a durable
``user_profiles`` table while ``PUT /api/v1/profile`` was refusing with ``503 storage_unavailable``,
because the write path had just looked for that very table and not found it.

What this module is not. It is not a second readiness verdict: "can we reach the database" stays
with ``_db_ready``, and nothing here answers it. It is not a second way to connect either -- the
probe is sent on a connection factory the calling module already owns (its own ``_conn``), because
``tests/test_r238_bare_connect_ratchet.py`` counts bare ``psycopg.connect`` sites and
``app/db/connection.py`` is where a connect latency policy belongs, applied leg by leg by its
operator. Handing this probe its own timeout would be exactly the "小房子" R238 warns about, so it
deliberately does not happen here: the health page inherits the leg's existing reach.

Which leaves the whole of this module as one question and three honest answers. The question is the
statement this repository already asks leg by leg -- ``SELECT to_regclass('public.<table>')``,
a NULL meaning the table is not there -- given a single home so that a readout and a write gate
cannot drift apart. It is read-only by construction: one SELECT, no DDL, no commit. And "could not
ask" is its own answer, never folded into "it is not there"; that collapse would be the same lie,
mirrored.
"""
from contextlib import closing

from app.common.logger import logger

#: The table is in the database. Only this verdict may back a claim of ``durable``.
PRESENT = "present"
#: The database was asked and answered NULL: the migration that owns this table has not run here.
ABSENT = "absent"
#: Nothing was learned -- no connection, no answer, or an answer this reader cannot parse. Not
#: evidence of absence, and not evidence of presence either, which is why it is its own verdict.
UNKNOWN = "unknown"

#: The one statement this repository asks with. ``to_regclass`` is the only safe form: DML against a
#: missing table aborts the surrounding transaction, which is what
#: ``app/documents/catalog.py._logical_documents_table_exists`` says about its own probe.
PROBE_STATEMENT = "SELECT to_regclass('public.{table_name}') AS table_name"

#: The column the statement answers with, read out of the statement itself so the question and its
#: reader cannot be edited apart.
ANSWER_COLUMN = PROBE_STATEMENT.split(" AS ")[1].split(")")[0].strip()

#: A cursor answer this reader cannot interpret. "I did not understand it" is reported as UNKNOWN,
#: never as ABSENT: an unreadable shape must not be dressed up as a missing migration.
_UNREADABLE = object()


def _answer(row):
    """Read a cursor answer the way the existing legs read it: a mapping, or one column by place."""
    if isinstance(row, dict):
        return row.get(ANSWER_COLUMN, _UNREADABLE)
    if isinstance(row, (tuple, list)):
        return row[0] if row else _UNREADABLE
    try:
        return dict(row).get(ANSWER_COLUMN, _UNREADABLE)
    except (TypeError, ValueError):
        return getattr(row, ANSWER_COLUMN, _UNREADABLE)


def probe_table(connect, table_name: str) -> str:
    """Return ``PRESENT`` / ``ABSENT`` / ``UNKNOWN`` for one table, on a connection already owned.

    ``connect`` is a zero-argument factory -- the calling module's own ``_conn``. Never a connection
    object: a probe that borrowed somebody's cursor would also borrow their transaction.
    """
    if not callable(connect) or not str(table_name or "").strip():
        return UNKNOWN
    try:
        with closing(connect()) as conn:
            row = conn.execute(PROBE_STATEMENT.format(table_name=table_name)).fetchone()
    except Exception as exc:  # noqa: BLE001 - "could not ask" is the answer, never a raised failure
        # debug 而不是 warning：这一支每次健康轮询都会走一遍，库整日不通的机器上那会是一日数千行
        # 日志；运维当场读得到的是本次的答复（读数里那句 detail），不是日志的条数。
        logger.debug(f"[Store] 现查 {table_name} 是否在位没问出来: {type(exc).__name__}")
        return UNKNOWN
    if row is None:
        return UNKNOWN
    value = _answer(row)
    if value is _UNREADABLE:
        logger.debug(f"[Store] 现查 {table_name} 交回一副读不懂的答案，按「问不到」记一笔")
        return UNKNOWN
    return PRESENT if value else ABSENT
