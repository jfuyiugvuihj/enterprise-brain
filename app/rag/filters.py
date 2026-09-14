"""Authorization-aware filters for the transitional Chroma document index."""

from app.common.identity import Principal


class RetrievalScopeError(ValueError):
    """Raised when a caller cannot be safely scoped to document retrieval."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_document_retrieval_filter(principal: Principal | None) -> dict:
    """Build a Chroma-compatible document scope before any retrieval executes."""
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

    departments = [
        department
        for department in dict.fromkeys(
            [principal.department, *principal.department_ids]
        )
        if department
    ]
    if not departments:
        raise RetrievalScopeError(
            "authorization_unavailable",
            "Document retrieval requires a department scope.",
        )
    if principal.clearance <= 0:
        raise RetrievalScopeError(
            "authorization_unavailable",
            "Document retrieval requires a positive clearance level.",
        )

    return {
        "$and": [
            {"classification": {"$in": list(range(1, principal.clearance + 1))}},
            {"department": {"$in": departments}},
        ]
    }
