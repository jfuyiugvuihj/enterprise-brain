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
"""
from fastapi import APIRouter, HTTPException, Request, Response

from app.api.v1 import alerts as alerts_api
from app.api.v1 import chat, data, intelligence
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
