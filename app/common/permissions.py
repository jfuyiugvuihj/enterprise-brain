ACTION_VIEW = "resource:view"
ACTION_UPLOAD = "resource:upload"
ACTION_DOWNLOAD = "resource:download"
ACTION_DELETE = "resource:delete"
ACTION_ANALYZE = "resource:analyze"
ACTION_EXPORT = "resource:export"
ACTION_APPROVE = "resource:approve"
ACTION_AUDIT = "audit:read"
ACTION_MANAGE_USERS = "users:manage"
ACTION_MANAGE_ALERTS = "alerts:manage"

ROLE_PERMISSIONS = {
    "staff": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),
    "manager": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS, ACTION_APPROVE}),
    "admin": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),
    "auditor": frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT}),
}


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role or "staff", ROLE_PERMISSIONS["staff"])
