"""R14-A1 (route A1): the overview page's server-side aggregate.

``GET /api/v1/dashboard/summary`` counts, for the authenticated caller only, from the
same sources the panels already render: the document catalog, the dataset registry, the
HITL ledger and the alert table. It takes no body and no client rows - the two existing
algorithm endpoints (``POST /dashboard``, ``POST /insights/detect``) compute over rows the
client supplies and are therefore not an overview data source (request R14's other half).

Design constraints this module is built around:

- **No second permission chain.** Documents are counted through
  ``chat.list_document_catalog`` (which is ``_visible_document_rows`` -> 
  ``authorization_decision``), datasets through ``data.list_data_files``, the analyze
  gate is ``intelligence._authorized``. A count that disagrees with the list beside it is
  the failure mode this endpoint was asked to remove, so none of them is restated here.
- **``documents_ready`` shares that read rather than adding one (R284).** The document
  tile has to say how many of the documents it just counted finished parsing, and a
  second query for that number is how two columns come to answer two different scopes.
  Both are counted out of the one catalog call in ``_document_counts``, reading a value
  on rows already in hand - not the R14-A1 shortcut, because the total is still not
  inferred from a page length.
- **Alerts are gated, and "no permission" is not "no alarms".** The alert count is taken
  only after ``app/api/v1/alerts.py::_require_alert_management`` (the same call
  ``GET /alerts`` makes) allows it. When it answers 403 the ``alerts`` key is **omitted**
  entirely: a ``0`` would render as a healthy tenant and would also be a back door around
  request R1 (staff may not read alerts), reachable with one ``ACTION_ANALYZE`` call.
 - **Passing that gate is the first layer only: the count is row-scoped like the ledger
   beside it (R188).** A finance manager must not read the company-wide alert total out of
   one overview tile - a number is information by itself, whether or not a message body
   came with it. Both branches therefore reuse the two predicates ``GET /alerts`` uses,
   ``alert_row_visible`` offline and ``alert_row_scope_sql`` against PostgreSQL, and this
   module restates neither of them. The cut goes *into* the ``COUNT(*)`` query, which is
   also why the count never reads a page back and takes its length.
- **The pending count is R13's ledger semantics.** It is one ``pending_approvals.open_items``
  call with the caller as ``owner_user_id`` - literally the read
  ``GET /hitl/pending`` performs. The ledger is not revalidated against the graph here,
  which keeps an overview load from paying one checkpoint read per row; the direction of
  the difference is safe because the panel only ever drops rows from that same set, so
  the summary can overstate open work and can never report a cleaner queue.
- **A missing ledger refuses the whole response.** ``503 storage_unavailable``, the code
  R13 established: partial counts on a broken install read as health. Only that one
  exception type is translated; any other ledger failure propagates unchanged so a real
  defect keeps its shape. No new error code is introduced, and the alert table keeps the
  behaviour of its own route (a bootstrap failure there stays a server error, exactly as
   ``GET /alerts`` answers it).
- **The trend series cuts periods out of stored time columns (R332).**
  ``GET /dashboard/trend`` is a second route in this module and it shares that whole
  permission story: the same ``intelligence._authorized`` analyze gate, the same
  ``NO_STORE_HEADERS``, documents out of the one ``chat.list_document_catalog`` read,
  datasets out of the one ``data.list_data_files`` read, alerts out of the one row-scope
  predicate. What it adds is a bucket, and a bucket is only honest when it is cut from the
  row's own ``created_at``. Never from a file mtime - ``data.list_data_files`` answers
  ``modified_at`` off ``path.stat()``, which is exactly why the period is not read from that
  key. Never from a page length - ``_document_counts``' docstring is the standing tombstone.
  A row that recorded no period is not a failed read: R342 counts those rows in ``undated``
  and the series still answers one question, because ``sum(buckets) + undated`` is what
  ``/summary`` reports for the same caller and the same scope. Two faces keep refusing the
  response - a value that was recorded but is not a period, and a file the listing calls
  visible while the registry holds no active row for it - and a read that raises still
  propagates unchanged.
  ``alerts_open`` is the one column drawn from a second clock (R340): 「这一档新增、到这一档结束
  那一刻仍未处置」, replayed from ``acknowledged_at`` / ``closed_at`` rather than from the status
  read at request time, so a past bar stops rewriting itself after the fact. The bucket still
  open has not closed and replays up to the request instant; a reassignment is not a disposal.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.v1 import alerts as alerts_api
from app.api.v1 import chat, data, intelligence
from app.common.logger import logger
from app.common.no_store import NO_STORE_HEADERS
from app.common.permissions import ACTION_ANALYZE
from app.storage import pending_approvals

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# The stored set, not the delivered page: GET /alerts is capped at the newest 100 rows, so
# a "total" read off that list shrinks silently once a tenant has more alarms than one page
# - the worst kind of wrong number, because it looks right. The statement carries no
# ownership clause of its own on purpose: ``alerts.alert_row_scope_sql`` is the one place
# that shape is written, and ``_alert_counts`` appends its answer here before counting.
_ALERT_COUNT_SQL = "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE read = FALSE) AS unread FROM alerts"


#: The one stored value that means 「解析完了」. The domain is
#: ``app/documents/catalog.py::PARSE_STATUSES`` -
#: ``("pending", "parsing", "ready", "failed")`` - and it is a database ``CHECK``
#: (``migrations/0006_document_ownership.sql``: ``document_versions_parse_status_check``),
#: not an application habit.
#: tests/test_r284_documents_ready_column.py pins this literal against that tuple, so a
#: rename on either side is caught by a failing test rather than by an overview tile
#: that quietly starts calling everything ready.
_PARSE_STATUS_READY = "ready"


async def _document_counts(request: Request) -> tuple[int, int]:
    """``(documents, documents_ready)`` - two numbers, one catalog read, one visible scope.

    Both are counted out of the same ``list_document_catalog`` return value, which is
    that caller's own document panel (``chat._classify_document_rows`` ->
    ``authorization_decision``). There is no second query here, so the two columns
    cannot answer two scopes and ``documents_ready <= documents`` is structural rather
    than a rule somebody has to remember. Counting a field on rows the endpoint already
    holds is not the R14-A1 shortcut this module exists to remove: the total is still
    not inferred from a page length.

    What this counts, and the two ways it could be misread:

    - **Ready is a parse state.** Only ``"ready"`` counts. ``"parsing"`` and ``"failed"``
      are both 「还没解析完」 for the employee reading the tile - a half-parsed document
      and one that produced no text answer the same question, so neither may join the
      ready side.
    - **A row that never recorded a status is not ready.**
      ``catalog._normalise_parse_status`` folds NULL, empty and unrecognised values into
      ``"pending"``, so a document stored before ``parse_status`` landed - the migration
      added the column ``NOT NULL DEFAULT 'pending'``, which is exactly what every
      existing row took - counts as unparsed until something re-parses it. The column
      can therefore understate 「已解析」 on a legacy corpus; it cannot invent a ready
      document. Normalisation happens before this function sees the row, so a response
      cannot split 「历史行」 from an honest ``pending`` without a second read;
      ``docs/api/contract-v1.md`` states the bias instead of quietly carrying it.
    - **Parse is not retrieval.** ``index_status``
      (``catalog._normalise_index_status``, whose unrecorded value is a first-class
      ``INDEX_STATUS_UNKNOWN``) answers 「助理能不能检索到这篇」 and is orthogonal by
      design (``app/documents/index_policy.py:32-36``). A ``ready`` document the index
      policy excluded still counts here; an indexed document still being parsed does
      not. This is not a count of askable documents, and the frontend wording
      「N 篇还没解析完」 is written against parse, not index.
    """
    catalog = await chat.list_document_catalog(request)
    rows = catalog["documents"]
    return len(rows), sum(
        1 for row in rows if row.get("parse_status") == _PARSE_STATUS_READY
    )


async def _dataset_count(request: Request) -> int:
    """How many registered data files this caller may analyze-and-open."""
    listing = await data.list_data_files(request=request)
    return len(listing["files"])


def _pending_count(principal) -> int:
    """Open HITL ledger rows owned by the caller (the R13 read, unchanged)."""
    try:
        rows = pending_approvals.open_items(owner_user_id=str(principal.user_id or ""))
    except pending_approvals.PendingApprovalStoreMissing as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    return len(rows)


def _alert_counts(request: Request) -> dict | None:
    """``{"total", "unread"}`` when the caller may manage alerts, ``None`` when not.

    ``None`` means the key must disappear from the response. The gate is handed the live
    Request: called with ``None`` it returns early as an offline/internal concession
    (alerts.py:99-100), and an HTTP route must never take that branch.
    """
    try:
        # The principal the gate resolves is the input of the second layer below; the
        # call keeps its single-argument shape because that is the seam the tests spy on.
        principal = alerts_api._require_alert_management(request)
    except HTTPException as exc:
        if exc.status_code == 403:
            return None
        raise

    if alerts_api._database_available():
        alerts_api._ensure()
        # Row scope first, then the count: filtering after a LIMIT would answer "0 alarms"
        # to a department whose rows were pushed off the page by another one (the reason
        # ``alert_row_scope_sql`` carries in its own docstring, and it applies here too).
        predicate, params = alerts_api.alert_row_scope_sql(principal)
        sql = " ".join(part for part in (_ALERT_COUNT_SQL, predicate) if part)
        with alerts_api._conn() as conn:
            row = conn.execute(sql, params).fetchone() or {}
        return {"total": int(row.get("total") or 0), "unread": int(row.get("unread") or 0)}

    stored = [
        dict(alert)
        for alert in alerts_api._MEM_ALERTS
        if alerts_api.alert_row_visible(principal, alert)
    ]
    return {
        "total": len(stored),
        "unread": sum(1 for alert in stored if not alert.get("read")),
    }


@router.get("/summary")
async def dashboard_summary(request: Request, response: Response):
    """One round trip for the four overview tiles, scoped to the signed-in principal.

    Anonymous and unauthorised callers are refused by the same analyze gate the
    algorithm endpoints use; the ledger is read before anything else so a broken
    install cannot answer 200 with the three numbers that did work.
    install cannot answer 200 with the three numbers that did work.

    ``documents`` and ``documents_ready`` are always present and always integers;
    ``alerts`` stays the only conditional key, and only there because declining to
    answer is the permission answer for that tile.
    """
    principal = intelligence._authorized(request, ACTION_ANALYZE, "dashboard_summary")
    # Every tile in here is a per-principal authorization answer, so a cached 200 is
    # another caller's scope.
    response.headers.update(NO_STORE_HEADERS)

    documents, documents_ready = await _document_counts(request)
    payload: dict = {
        "generated_for": str(principal.user_id),
        "pending_approvals": _pending_count(principal),
        "documents": documents,
        # R284: the tile's second line, and always a number. Unlike ``alerts`` this key
        # is never conditional - the frontend reads absence as 「已解析篇数未记录」 and
        # only an integer as an answer, so this endpoint does not get to pick which of
        # the two faces a quiet day shows by leaving the key out.
        "documents_ready": documents_ready,
        "datasets": await _dataset_count(request),
    }
    alerts = _alert_counts(request)
    if alerts is not None:
        payload["alerts"] = alerts
    return payload


# ================================================================= GET /dashboard/trend
#
# R332. ``/summary`` answers how many rows exist now; this route answers in which period
# they arrived. The second question is the one the overview panel is still asking:
# ``frontend/src/components/DashboardPanel.vue:12-13`` draws the 「数据趋势」 empty state
# *because* no server aggregate returned a period series, and ``:304`` says that card may
# only grow numbers once such an aggregate exists. This section is the aggregate it waits
# for. ``/summary`` itself is not touched - its four tiles carry R284's accounting and
# several pins of their own.

#: The single clock every bucket boundary is cut with: ``Asia/Shanghai``. The same fixed
#: +08:00 offset as ``app/common/auth.py:25`` and ``app/documents/catalog.py:15``, and the
#: same wall the alert table stamps its own rows from - ``alerts.py:122`` and
#: ``migrations/0003_legacy_runtime_tables.sql:9`` both store
#: ``(NOW() AT TIME ZONE 'Asia/Shanghai')::text``. China has no daylight saving, the
#: conclusion ``alerts.py:449`` already records beside the disposal clock, so a fixed offset
#: cannot slide a month edge by an hour the way a named zone with a rule would.
_TREND_TIME_ZONE = timezone(timedelta(hours=8))
_TREND_TIME_ZONE_NAME = "Asia/Shanghai"
_TREND_PERIODS = ("month", "week")
_TREND_DEFAULT_PERIOD = "month"
_TREND_DEFAULT_BUCKETS = 12

#: The cap exists because both legs keep whatever they count: the offline leg filters a
#: Python list in memory, and the SQL leg deliberately carries no ``LIMIT`` - a bounded read
#: is how a total starts shrinking quietly once a tenant outgrows the bound, which is the
#: defect ``_ALERT_COUNT_SQL`` above was written against. So the window is capped, not the
#: query. 60 monthly buckets is five years, 60 weekly buckets fourteen months; neither is a
#: range one card on one screen can draw anyway.
_TREND_MAX_BUCKETS = 60

#: Read row by row, not page by page, and with no ownership clause of its own: the predicate
#: comes from ``alerts.alert_row_scope_sql``, exactly as in ``_ALERT_COUNT_SQL``.
#:
#: The two disposal columns travel with the row since R340: 「这一档当时还没人处置」 is answered
#: from the disposal clock, so a projection carrying only ``created_at`` and ``status`` would
#: hand the PostgreSQL leg rows it cannot answer that question with, and the two legs would
#: disagree without any of it raising. ``assigned_at`` is not selected and never consulted -
#: being handed to somebody is not a disposal.
_ALERT_SERIES_SQL = "SELECT created_at, status, acknowledged_at, closed_at FROM alerts"

#: Denial cannot be spelled ``None`` here, because ``None`` is already the answer for "this
#: caller may read alerts and nothing arrived in the window". Same reason ``_alert_counts``
#: spells denial as a missing key rather than as a zero.
_ALERTS_DENIED = object()


def _trend_now() -> datetime:
    """The anchor of the window: server wall time, in the trend's own zone."""
    return datetime.now(_TREND_TIME_ZONE)


def _trend_unreadable(source: str, ident: object) -> HTTPException:
    """The two faces that still refuse the whole response (R332, narrowed by R342).

    ``503 storage_unavailable`` is this module's existing face for "a book cannot be
    accounted for" (``_pending_count`` translates exactly that failure today), so no new
    error code is opened here. R332 routed three row shapes through here; R342 releases one
    of them - a row that recorded no period at all is counted in ``undated`` instead -
    because that shape is what our own write paths leave behind: a legacy sidecar import
    becomes ``_timestamp_text(None)`` -> ``""`` (``app/storage/datasets.py:763``). A
    predictable hole in one row does not get to blacken every card on the overview.

    What is left here is a failure of accountability, and it stays a refusal:

    - the value was recorded but is not a period - unparseable text, or a shape that is
      neither text nor a datetime. Guessing a month for it would move a row between buckets;
    - a file ``data.list_data_files`` reports visible that the registry carries no active row
      for. Two reads of one book contradicting each other is a defect, and washing it into
      ``undated`` would turn a consistency failure into a footnote.

    Neither face may be dropped silently and neither may be filled with ``0``: dropping makes
    the buckets total less than ``/summary`` reports for the same caller and scope, and ``0``
    is the face the client already refuses to render -
    ``frontend/src/lib/dashboard.js:32``, 「不会用旧数字或 0 顶上」.
    """
    logger.warning(f"[Dashboard] trend period unreadable: source={source} row={ident}")
    return HTTPException(status_code=503, detail="storage_unavailable")


#: The three faces one stored time value can show, classified before anything decides to
#: refuse, so that 「this row never recorded a time」 and 「this row recorded something that is
#: not a time」 cannot be folded into one answer again. ``_TREND_UNDATED`` doubles as the
#: response key carrying those counts: one word, one meaning, so the reading of a row and
#: the number the card renders cannot drift apart.
_TREND_RECORDED = "recorded"
_TREND_UNDATED = "undated"
_TREND_GARBLED = "garbled"


def _trend_period(value: object) -> tuple[str, datetime | None]:
    """Sort one stored time value into a face, without deciding what the face is worth.

    This is a classifier, not a decision - which is the whole point of R342. ``None`` and
    blank text mean 「nothing was recorded」; anything else that will not parse means
    「something was recorded and it is not a period」. The caller picks the consequence.
    """
    if isinstance(value, datetime):
        return _TREND_RECORDED, value
    if value is None:
        return _TREND_UNDATED, None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return _TREND_UNDATED, None
        try:
            return _TREND_RECORDED, datetime.fromisoformat(text)
        except ValueError:
            return _TREND_GARBLED, None
    return _TREND_GARBLED, None


def _trend_instant(moment: datetime) -> datetime:
    """Put one parsed time value on the trend clock, and nowhere else.

    An offset on the value is honoured (converted, not re-read); a missing offset is read as
    Shanghai wall time. This is the single place that rule lives, so the instant a row is
    bucketed by and the instant its disposal is compared against are cut on the same wall -
    two comparisons made on two different walls would replay a bucket wrong by an hour and
    still look like arithmetic.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_TREND_TIME_ZONE)
    return moment.astimezone(_TREND_TIME_ZONE)


def _trend_moment(
    value: object, *, source: str, ident: object
) -> tuple[str, datetime | None]:
    """``(face, moment)`` for one stored time column, in ``_TREND_TIME_ZONE``.

    The three books write three shapes today and each keeps its own meaning:

    - ``document_versions.created_at`` is ``TEXT`` holding ``catalog.py:580``, i.e. ISO text
      carrying an explicit ``+08:00``.
    - ``alerts.created_at`` is ``TEXT`` holding ``(NOW() AT TIME ZONE
      'Asia/Shanghai')::text`` (``alerts.py:122``) - Shanghai wall time with the offset
      stripped by the cast - and the offline list appends ``datetime.now().isoformat()``
      (``alerts.py:825``), naive for the same reason.
    - ``datasets.created_at`` is ``TIMESTAMPTZ`` (``migrations/0002:16``) written from
      ``_utc_now_text()`` (``datasets.py:56``), so it always reads back with an offset: an
      instant, never a local guess.

    An offset on the value is therefore honoured (convert, do not re-read the digits), and a
    missing offset is read as Shanghai, because that is what the two text columns above
    actually hold. Assuming UTC for naive text - the reflex that would be right for the
    datasets column - would push eight hours of every month into the bucket beside it.

    ``app/storage/datasets.py::_timestamp_text`` is the existing normaliser for "the driver
    hands back a datetime, the JSON import hands back a string"; this function accepts what
    it produces instead of opening a second parser, which is also why the datetime branch is
    first rather than an afterthought. That same normaliser is what turns a missing
    timestamp into ``""`` on the legacy import path, and R342 reads that row as
    ``_TREND_UNDATED`` rather than as a failure.

    Only ``_TREND_GARBLED`` refuses here. ``_TREND_UNDATED`` comes back without a moment and
    the caller counts the row in ``undated`` - which is why every book below has to declare
    an undated exit rather than inherit one blanket ``except``.
    """
    kind, parsed = _trend_period(value)
    if kind == _TREND_GARBLED:
        raise _trend_unreadable(source, ident)
    if kind == _TREND_UNDATED:
        return _TREND_UNDATED, None
    return _TREND_RECORDED, _trend_instant(parsed)


def _month_start(day: date, back: int) -> date:
    """First day of the month ``back`` months before ``day``."""
    ordinal = day.year * 12 + day.month - 1 - back
    return date(ordinal // 12, ordinal % 12 + 1, 1)


def _week_start(day: date, back: int) -> date:
    """Monday of the week ``back`` weeks before ``day``'s week."""
    return day - timedelta(days=day.weekday() + 7 * back)


def _bucket_start(period: str, day: date) -> date:
    """Which bucket a Shanghai calendar day falls in, keyed by that bucket's first day."""
    return _month_start(day, 0) if period == "month" else _week_start(day, 0)


def _bucket_end(period: str, start: date) -> datetime:
    """The instant ``start``'s bucket stops being an open period: midnight after its last day.

    Walking one step forward with the same two step functions that cut the buckets
    (``back=-1``) is the point: the edge a row was bucketed out of and the edge its disposal is
    compared against are then one edge, computed once. Half-open ``[start, end)``, matching
    ``_bucket_start``: a disposal landing on the first instant of the next period belongs to
    the next period, not to the bucket it is being replayed against.
    """
    edge = _month_start(start, -1) if period == "month" else _week_start(start, -1)
    return _trend_instant(datetime(edge.year, edge.month, edge.day))


def _bucket_label(period: str, start: date) -> str:
    """``2026-09`` for a month, ``2026-W40`` for a week.

    The week label is taken from ``start``, which is always a Monday, so an ISO week that
    straddles New Year is labelled by the year its own Monday belongs to and appears once
    instead of being split across two year numbers.
    """
    if period == "month":
        return f"{start.year:04d}-{start.month:02d}"
    iso = start.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def _bucket_starts(period: str, buckets: int) -> list[date]:
    """``buckets`` consecutive bucket starts, oldest first, ending with the current period.

    Continuity is the deliverable, not an optimisation. A period in which nothing new
    arrived is a fact the server has to state (``0``); handing back only the non-empty
    buckets would make the client infer the gaps, and an inferred gap is exactly where a
    quiet quarter and a broken read become indistinguishable.
    """
    anchor = _trend_now().date()
    step = _month_start if period == "month" else _week_start
    starts = [step(anchor, back) for back in range(buckets)]
    starts.reverse()
    return starts


def _bump(counts: dict[date, int], key: date) -> None:
    counts[key] = counts.get(key, 0) + 1


async def _document_series(
    request: Request, period: str
) -> tuple[dict[date, int], dict[date, int], dict[str, int]]:
    """``(documents, documents_ready, undated)``, out of the one catalog read of ``/summary``.

    Same call, same rows, same ``_PARSE_STATUS_READY`` literal as ``_document_counts``: the
    tile beside this chart and the chart itself cannot answer two scopes, because there is
    only one read between them. R284's stated understatement travels with the rows - a
    legacy line whose ``parse_status`` the migration defaulted to ``pending`` still counts as
    unparsed here too. This route does not get to look more optimistic than the tile about
    the same document; ``docs/api/contract-v1.md`` says why in one place and repeats it
    rather than restating a second, friendlier reading.

    A row whose ``created_at`` recorded nothing joins neither bucket and joins ``undated``
    instead, in both of its columns, so ``sum(buckets) + undated`` is what
    ``_document_counts`` reports for the same caller. Offline that hole is hard to reach -
    ``catalog._local_row`` substitutes ``_file_mtime`` into the row itself - but the TEXT
    column carries no ``DEFAULT`` (``migrations/0003_legacy_runtime_tables.sql:46``), so an
    empty cell is a stored shape, not a hypothetical. A recorded value that is not a period
    still refuses the whole response.
    """
    catalog = await chat.list_document_catalog(request)
    totals: dict[date, int] = {}
    ready: dict[date, int] = {}
    undated = {"documents": 0, "documents_ready": 0}
    for row in catalog["documents"]:
        kind, moment = _trend_moment(
            row.get("created_at"), source="documents", ident=row.get("filename")
        )
        parsed_ready = row.get("parse_status") == _PARSE_STATUS_READY
        if kind == _TREND_UNDATED:
            undated["documents"] += 1
            if parsed_ready:
                undated["documents_ready"] += 1
            continue
        start = _bucket_start(period, moment.date())
        _bump(totals, start)
        if parsed_ready:
            _bump(ready, start)
    return totals, ready, undated


async def _dataset_series(
    request: Request, period: str
) -> tuple[dict[date, int], dict[str, int]]:
    """Datasets per bucket plus the visible files that recorded no period at all.

    ``data.list_data_files`` is the scope and nothing else decides it - the very call
    ``_dataset_count`` makes, so a file the caller may not list cannot enter a bucket either.
    What is *not* read from that listing is its ``modified_at``: that key comes off
    ``path.stat()`` (``data.py:239-248``), a filesystem timestamp, not a registration time.
    The period therefore comes from the registry, which is the same source the visibility
    check consulted a few lines earlier (``data.py:212``).

    The registry is read once (``active_records()``) rather than once per file, and several
    rows for one name resolve to the newest *recorded* registration by the same rule
    ``DatasetRegistry.get_active_by_filename`` applies (``datasets.py:1039-1049``): ``""``
    sorts below every ISO timestamp, so an undated row can never win a bucket. The unit this
    counts is the visible file, not the registry row.

    R342 separates the two faces that used to share one refusal here (判据 乙):

    - every active row for a visible file recorded nothing - what a legacy sidecar import
      leaves behind (``datasets.py:763``, ``_timestamp_text(None)`` -> ``""``) - is one
      undated file, and it goes to ``undated``;
    - a visible file the registry carries **no active row for at all** is two reads of one
      book contradicting each other. That stays ``_trend_unreadable``: an agreement failure
      must not be laundered into a footnote about missing time.

    A recorded value that will not parse is the third face and refuses as before, because
    each row is classified by ``_trend_moment`` before this loop decides anything.
    """
    listing = await data.list_data_files(request=request)
    recorded: dict[str, list[object]] = {}
    for record in data.dataset_registry.active_records():
        recorded.setdefault(str(record.filename), []).append(record.created_at)

    counts: dict[date, int] = {}
    undated = {"datasets": 0}
    for item in listing["files"]:
        filename = str(item.get("filename") or "")
        values = recorded.get(filename)
        if not values:
            raise _trend_unreadable("datasets", filename)
        moments = []
        for value in values:
            kind, moment = _trend_moment(value, source="datasets", ident=filename)
            if kind == _TREND_RECORDED:
                moments.append(moment)
        if not moments:
            undated["datasets"] += 1
            continue
        _bump(counts, _bucket_start(period, max(moments).date()))
    return counts, undated


def _alert_management_principal(request: Request):
    """The principal ``GET /alerts`` would resolve, or ``_ALERTS_DENIED``.

    The 403 branch is written twice in this module on purpose. ``_alert_counts`` keeps its
    body untouched: it is the seam ``tests/test_dashboard_summary.py`` watches, and editing a
    pinned helper to save four lines is how a closing week acquires a second set of red tests.
    """
    try:
        return alerts_api._require_alert_management(request)
    except HTTPException as exc:
        if exc.status_code == 403:
            return _ALERTS_DENIED
        raise


#: The two columns that hold 「有人处置过这一行」的时刻: the ack and close actions of
#: ``alerts.ALERT_DISPOSAL_WRITE_COLUMNS`` stamp ``acknowledged_at`` and ``closed_at``. That
#: equality with the write set is measured, not held up by this comment
#: (``test_the_disposal_clock_excludes_the_assignment_column``). ``assigned_at`` is absent on
#: purpose (R340 判据甲) - a reassignment says 「现在归他」, not 「有人决定了」, and counting it
#: would let one 转派 empty a bucket.
_ALERT_DISPOSAL_MOMENT_COLUMNS: tuple[str, ...] = ("acknowledged_at", "closed_at")


def _alert_disposal_moment(row: dict) -> datetime | None:
    """The first instant anybody disposed of this row, or ``None`` when its clock says nobody did.

    The minimum over the two disposal columns, not "the column that matches the current
    status": a row acknowledged in February and closed in March was dealt with as of the end
    of February, and asking only ``closed_at`` would keep drawing it as open in a bucket where
    somebody had already answered it.

    Three shapes answer ``None`` rather than raising, because R340 opens no second refusal
    face (判据庚) and the two legs must never disagree about one row (判据丁): the column is
    absent, ``NULL``, empty or whitespace - 「没记过处置时间」, which is exactly what migration
    0014 fills the 存量行 with - and a recorded value that is not a time. The last of those
    leaves the row with no readable clock, so it falls back to the present reading, which is
    the face ``GET /alerts`` already shows for it.
    """
    moments: list[datetime] = []
    for column in _ALERT_DISPOSAL_MOMENT_COLUMNS:
        kind, parsed = _trend_period(row.get(column))
        if kind == _TREND_RECORDED:
            moments.append(_trend_instant(parsed))
    return min(moments) if moments else None


def _alert_open_at(row: dict, as_of: datetime) -> bool:
    """「这一行到 ``as_of`` 那一刻仍未处置」 - the one predicate both legs run (判据丙).

    The status *face* is never re-derived here: ``alerts.alert_row_status`` stays the only
    status judgment in the platform, so a row predating migration 0014 - no ``status``, no
    disposal clock - answers ``open`` exactly as the alert panel answers it, and this module
    adds no second rule for it (判据丁).

    Four edges, named by 判据甲, all of them replayable:

    - ① acknowledged inside the bucket: its clock falls strictly before the bucket edge, so
      the bucket does not count it;
    - ② acknowledged only *after* the bucket: the clock is later than the edge, so the bucket
      still counts it. This is the row the present-status read lost, and the reason the chart
      could rewrite its own past;
    - ③ never disposed: ``status`` is ``open``, so it was open at every earlier instant too;
    - ④ closed: the same two readings, taken from ``closed_at`` (or from ``acknowledged_at``
      when that came first).

    A disposal landing exactly on the bucket edge is a disposal in the bucket *beside* it:
    ``>=`` here is the same half-open ``[start, end)`` ``_bucket_start`` already uses for
    ``created_at``, so the two comparisons cannot disagree about which period an instant
    belongs to. A reassignment appears in none of the branches: ``assigned_at`` is not a
    disposal column.
    """
    if alerts_api.alert_row_status(row) == alerts_api.ALERT_STATUS_OPEN:
        return True
    disposed_at = _alert_disposal_moment(row)
    if disposed_at is None:
        return False
    return disposed_at >= as_of


def _alert_series(
    request: Request, period: str
) -> tuple[dict[date, tuple[int, int]], dict[str, int]] | None:
    """``({bucket: (alerts, alerts_open)}, undated)``, or ``None`` when alerts are denied.

    Two layers, same as ``_alert_counts``: the ``_require_alert_management`` gate first, then
    the row-scope predicate - passing the gate is not a licence for the company-wide total.
    ``None`` means the ``alerts`` keys disappear from every bucket *and* from ``undated``: a
    ``0`` there would tell a staff account "no alarms this month", which is a false green
    light and, worse, the alert ledger read through a route that is not ``GET /alerts`` -
    reachable with one ``ACTION_ANALYZE`` call, which is request R1 reopened.

    ``alerts_open`` is replayable (R340): the rows created in that bucket that were still
    undisposed *as of that bucket's own closing instant*, answered by ``_alert_open_at`` out
    of ``acknowledged_at`` / ``closed_at``. An alarm created last week and acknowledged last
    Friday keeps its place in last week's bar; one acknowledged inside the bucket leaves it;
    one nobody has touched is still counted. The status face stays
    ``alerts.alert_row_status``, so a row predating migration 0014 answers the same ``open``
    the alert panel answers - this module owns no second status rule.

    The newest bucket has not closed, so its horizon is the request instant: today's bar is
    still the open count ``/summary`` reports today, which is what keeps the two numbers on
    the overview from splitting into two 口径. Only closed buckets replay.

    Bucketing *and* the replay predicate happen in Python on both legs rather than in SQL:
    ``created_at`` is ``TEXT`` holding the three shapes ``_trend_moment`` documents, and
    ``date_trunc`` over it would hand the PostgreSQL leg a period rule the offline leg does
    not have. R340 does not open that exception for the disposal clock either: no SQL time
    function and no second parser appear here, the legs differ only in where the rows come
    from, and ``_ALERT_SERIES_SQL`` selects the two disposal columns so both legs hand
    ``_alert_open_at`` the same row. ``NOW()`` stays out of the disposal clock, which is the
    reason ``alerts.py:441-450`` stamps those columns from one server clock.

    A ledger row that recorded no time is undated rather than a month with nothing in it
    (R342), and it is counted in both columns. 「该档结束那一刻」 does not exist for such a row,
    so its ``alerts_open`` stays the present reading and R340 does not quietly extend the new
    rule to it (判据己, and the contract says why). The ``alerts`` conservation of R342 is
    untouched: ``sum(buckets) + undated`` still equals the rows the caller's scope covers. The
    open column is bounded by that law rather than equal to a second total - it can never
    exceed the rows in its own bucket, and only reaches today's open count when no dated row
    was disposed after its own bucket closed. A row whose value was recorded but is not a
    period still refuses the whole response.
    """
    principal = _alert_management_principal(request)
    if principal is _ALERTS_DENIED:
        return None

    if alerts_api._database_available():
        alerts_api._ensure()
        predicate, params = alerts_api.alert_row_scope_sql(principal)
        sql = " ".join(part for part in (_ALERT_SERIES_SQL, predicate) if part)
        with alerts_api._conn() as conn:
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    else:
        rows = [
            dict(alert)
            for alert in alerts_api._MEM_ALERTS
            if alerts_api.alert_row_visible(principal, alert)
        ]

    totals: dict[date, int] = {}
    open_counts: dict[date, int] = {}
    undated = {"alerts": 0, "alerts_open": 0}
    # Read the clock once per request: every closed bucket replays against its own edge, and
    # only the bucket still open replays against 当下. Clamping with ``min`` is what stops the
    # newest bar from being replayed against an instant that has not happened yet.
    now = _trend_now()
    horizon: dict[date, datetime] = {}
    for row in rows:
        kind, moment = _trend_moment(
            row.get("created_at"), source="alerts", ident=row.get("id")
        )
        if kind == _TREND_UNDATED:
            # 判据己: this row has no bucket edge to replay against, so it keeps the present
            # reading. R340 changes the dated column and leaves this one exactly where it was.
            undated["alerts"] += 1
            if alerts_api.alert_row_status(row) == alerts_api.ALERT_STATUS_OPEN:
                undated["alerts_open"] += 1
            continue
        start = _bucket_start(period, moment.date())
        _bump(totals, start)
        if start not in horizon:
            horizon[start] = min(_bucket_end(period, start), now)
        if _alert_open_at(row, horizon[start]):
            _bump(open_counts, start)
    bucketed = {start: (total, open_counts.get(start, 0)) for start, total in totals.items()}
    return bucketed, undated


@router.get("/trend")
async def dashboard_trend(
    request: Request,
    response: Response,
    period: str = _TREND_DEFAULT_PERIOD,
    buckets: int = _TREND_DEFAULT_BUCKETS,
):
    """The overview page's period series, computed inside the signed-in caller's scope.

    ``period`` is ``month`` or ``week``; ``buckets`` is ``1.._TREND_MAX_BUCKETS``. Either one
    out of range answers ``422 validation_error``, which is ``app/api/v1/notifications.py``'s
    existing rejection for a bad filter value and an out-of-range page limit alike - this
    route opens no error code, so the error-code table and its two sync pins stay untouched.

    The gate is the same call ``/summary`` makes, ``intelligence._authorized`` with
    ``ACTION_ANALYZE``, and the answer is no more cacheable: every bucket is a
    per-principal authorization result, so one stored 200 is another department's company.

    A bucket of ``0`` asserts that nothing new was created in that period, and it is never a
    stand-in for a read that failed: all three books are still read before a single point is
    assembled. R342 retires the tail of that sentence - "the response is either every period
    or no response" - because a row that recorded no period is not a failed read: it is
    counted in ``undated`` beside the buckets and the card says so out loud. What the
    response is still never allowed to be is a *partial* series. A recorded value that is not
    a period, a visible file with no active registry row, and any read that raises all keep
    failing the whole response, which is what keeps
    ``sum(buckets) + undated == /summary`` true rather than merely hopeful.
    """
    principal = intelligence._authorized(request, ACTION_ANALYZE, "dashboard_trend")
    # Same reason as on /summary: each bucket is scoped to the caller, so a cached body is
    # somebody else's visible range.
    response.headers.update(NO_STORE_HEADERS)

    if period not in _TREND_PERIODS:
        raise HTTPException(status_code=422, detail="validation_error")
    if not 1 <= buckets <= _TREND_MAX_BUCKETS:
        raise HTTPException(status_code=422, detail="validation_error")

    starts = _bucket_starts(period, buckets)
    documents, documents_ready, undated_documents = await _document_series(request, period)
    datasets, undated_datasets = await _dataset_series(request, period)
    alerts = _alert_series(request, period)
    alert_counts: dict[date, tuple[int, int]] | None = None
    undated_alerts: dict[str, int] = {}
    if alerts is not None:
        alert_counts, undated_alerts = alerts

    # ``undated`` is a sibling of ``series``, never another bucket: 「有多少条没有期间」 answers a
    # different question from 「这一期新增了几条」, and folding the two together would let a row
    # with no period be drawn as if it had landed in some period. Denied callers get no
    # alert keys here either - the same absence rule the buckets carry.
    undated: dict[str, int] = {**undated_documents, **undated_datasets, **undated_alerts}
    if any(undated.values()):
        # One line per response that had to name a hole. The card is honest about the number,
        # which is not the same as the operator being able to find out which book leaks.
        logger.info(f"[Dashboard] trend rows without a period: {undated}")

    series: list[dict] = []
    for start in starts:
        point: dict = {
            "bucket": _bucket_label(period, start),
            "start": start.isoformat(),
            "documents": documents.get(start, 0),
            "documents_ready": documents_ready.get(start, 0),
            "datasets": datasets.get(start, 0),
        }
        if alert_counts is not None:
            total, still_open = alert_counts.get(start, (0, 0))
            point["alerts"] = total
            point["alerts_open"] = still_open
        series.append(point)

    return {
        "generated_for": str(principal.user_id),
        "period": period,
        "buckets": buckets,
        "time_zone": _TREND_TIME_ZONE_NAME,
        "series": series,
        "undated": undated,
    }
