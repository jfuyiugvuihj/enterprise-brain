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


async def _document_count(request: Request) -> int:
    """How many stored documents this caller's own document panel can list."""
    catalog = await chat.list_document_catalog(request)
    return len(catalog["documents"])


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
    """
    principal = intelligence._authorized(request, ACTION_ANALYZE, "dashboard_summary")
    # Every tile in here is a per-principal authorization answer, so a cached 200 is
    # another caller's scope.
    response.headers.update(NO_STORE_HEADERS)

    payload: dict = {
        "generated_for": str(principal.user_id),
        "pending_approvals": _pending_count(principal),
        "documents": await _document_count(request),
        "datasets": await _dataset_count(request),
    }
    alerts = _alert_counts(request)
    if alerts is not None:
        payload["alerts"] = alerts
    return payload
