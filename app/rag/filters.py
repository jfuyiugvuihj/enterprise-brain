"""Authorization scope for document retrieval against the transitional Chroma index.

Three chains decide who may read a document, and only this one had never heard of an
administrator: the data chain hands an admin the whole frame, the resource chain returns
``administrator_scope``, and the retrieval chain refused any caller without a department.
``docs/handoff/2026-09-15-backend-followup-requests.md`` 6.2 settled that as e2 -- the
retrieval chain now asks the same question the resource chain asks, through
``app.common.policy.is_administrator``, rather than carrying a fourth copy of the test.

Both outcomes leave the same journal: ``record_retrieval_scope`` writes the one scope that
widens access, and ``resolve_document_retrieval_scope`` writes every refusal it raises, so
"the account with no department was turned away" is attributable to an account instead of
vanishing into an exception. R163's matrix cell
``retrieval.nodept_account_is_refused`` is what pinned the missing half.
"""

from typing import NamedTuple

from app.common.audit import record_audit
from app.common.identity import Principal
from app.common.permissions import ACTION_VIEW
from app.common.policy import is_administrator


class RetrievalScopeError(ValueError):
    """Raised when a caller cannot be safely scoped to document retrieval."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DocumentRetrievalScope(NamedTuple):
    """One retrieval''s access decision, in the form both the store and the audit need.

    ``departments`` is ``None`` when the caller is not department-restricted at all,
    which is the difference between an administrator and everybody else. Keeping it as
    ``None`` instead of "every department we know about" means a document whose scope
    arrived later is judged by the same rule as one that did not.
    """

    filters: dict
    reason_code: str
    classification_levels: frozenset
    departments: frozenset | None

    def allows(self, hit: dict) -> bool:
        """Re-check one recalled chunk locally; a chunk without usable metadata is never visible."""
        try:
            level = int(hit.get("classification"))
        except (TypeError, ValueError):
            return False
        if level not in self.classification_levels:
            return False
        if self.departments is None:
            return True
        return str(hit.get("department") or "") in self.departments


#: 检索面在审计台账里的资源标识：写的是「哪一道闸门拒的」，不是「哪一份文档」。
AUDIT_SURFACE = "document_retrieval"


def _record_refusal(principal: Principal | None, code: str) -> None:
    """把「谁在检索闸门前被拒了」记进既有审计通路。

    这一条只写三样东西：主体（record_audit 自己从 principal 投影 username/role/user_id）、
    资源标识（固定写检索面名）、判定结果（denied + 稳定码）。文档正文、别人的部门实际值、
    密级实际值一个字都不许进 —— 此刻手里只有主体，还没碰到任何资源，写了就是凭空造账。
    也不自造第二套事件表：用的就是 record_retrieval_scope 同一条 record_audit。
    """
    record_audit(principal, ACTION_VIEW, "denied", AUDIT_SURFACE, code)


def _resolve_document_retrieval_scope(principal: Principal | None) -> DocumentRetrievalScope:
    """判定本体：四条 raise 出处、谓词形状与放行条件一字未改。

    对外的承诺（含管理员那一档为什么保留）写在入口 ``resolve_document_retrieval_scope``
    的 docstring 里——留账也在入口那一层，本层只负责判定。
    """
    if principal is None:
        raise RetrievalScopeError(
            "authentication_required",
            "Document retrieval requires an authenticated principal.",
        )
    if principal.status != "active":
        raise RetrievalScopeError(
            "permission_denied",
            "Inactive principals cannot retrieve documents.",
        )
    if principal.clearance <= 0:
        raise RetrievalScopeError(
            "authorization_unavailable",
            "Document retrieval requires a positive clearance level.",
        )

    levels = frozenset(range(1, principal.clearance + 1))
    classifications = {"classification": {"$in": sorted(levels)}}

    if is_administrator(principal):
        # No department predicate: same name, same meaning as the resource chain, and
        # record_retrieval_scope() gives it its own audit reason so an override is never
        # written up as an ordinary department match.
        return DocumentRetrievalScope(
            filters=classifications,
            reason_code="administrator_scope",
            classification_levels=levels,
            departments=None,
        )

    departments = frozenset(
        department
        for department in dict.fromkeys([principal.department, *principal.department_ids])
        if department
    )
    if not departments:
        raise RetrievalScopeError(
            "authorization_unavailable",
            "Document retrieval requires a department scope.",
        )
    return DocumentRetrievalScope(
        filters={"$and": [classifications, {"department": {"$in": sorted(departments)}}]},
        reason_code="department_scope",
        classification_levels=levels,
        departments=departments,
    )


def resolve_document_retrieval_scope(principal: Principal | None) -> DocumentRetrievalScope:
    """Build the scope for one retrieval before any query runs.

    The classification clause is kept for an administrator even though it restricts
    nothing today, so that the filter states the rule instead of the accident:
    ``Principal.clearance`` comes from ``clearance_for(role)`` and
    ``ROLE_CLEARANCE["admin"] = 3`` is the highest level the model defines, so "respect
    the classification ceiling" currently imposes no limit on an administrator. The real
    effect of e2 is therefore cross-department *and* cross-classification read access
    across the whole library. If a customer later asks for "the owner may not read
    confidential documents", the knob is ``ROLE_CLEARANCE`` (or a separate clearance for
    that account) -- not the department rule. Do not re-derive that from the code.

    留账是这一层加进来的：判定本体在 ``_resolve_document_retrieval_scope``，而四条 raise
    出处（无主体、账号停用、无正密级、无部门）今天都先从入口这里落一行 ``_record_refusal``
    再原样抛出去。放在入口而不是分支里，是因为分支会长——明天再加一条判定，只要它还是从
    这里 raise，账就还在。判定逻辑、谓词形状与放行条件一律不改。
    """
    try:
        return _resolve_document_retrieval_scope(principal)
    except RetrievalScopeError as exc:
        _record_refusal(principal, exc.code)
        raise


def build_document_retrieval_filter(principal: Principal | None) -> dict:
    """The Chroma ``where`` clause alone, for callers that do not need the reason."""
    return resolve_document_retrieval_scope(principal).filters


def record_retrieval_scope(
    principal: Principal | None,
    scope: DocumentRetrievalScope,
    *,
    hit_count: int,
    request_id: str | None = None,
) -> None:
    """Leave a trail for the one scope that widens access beyond a department."""
    if scope.reason_code != "administrator_scope":
        return
    record_audit(
        principal,
        ACTION_VIEW,
        "allowed",
        AUDIT_SURFACE,
        scope.reason_code,
        request_id=request_id,
        after_summary={"hit_count": hit_count},
    )
