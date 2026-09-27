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


# ---------------------------------------------------------------------------
# R357：「可创建 / 可指派」的角色集 —— 全仓唯一一份定义。
#
# 为什么真源长在这一格：这枚文件已经是角色词汇表的事实源（`ROLE_PERMISSIONS`），
# "哪些角色建得出、指派得动"是它的子集，两本账并排摆在同一屏里，"差的到底是哪一枚"
# 才读得出来。`app/common/auth.py`（建号与改派两处）与 `app/common/sso.py`（SSO 头里的
# 角色）一律 import 这一枚，不许再各自抄一份名单 —— 那三行手抄字面量是 R357 的病根。
#
# `auditor` 为什么不在可创建集合里（判据⑧要求写成一句人话，不许靠一份没来源的三元组
# 碰运气）：`app/common/rbac.py:31` 的 `ROLE_CLEARANCE` 只给 staff / manager / admin 三枚
# 档位，**auditor 到今天还没有密级档位**。密级口径是 H13，业主未定，本单不许替它编一档，
# 也不许把一个没档位的角色放进可创建集合 —— 建得出、却算不出他能看哪一档数据，那是把
# 一个未决问题偷换成一个静默的默认值。两枚差集钉（`ROLE_PERMISSIONS - CREATABLE_ROLES`
# 与 `ROLE_PERMISSIONS - ROLE_CLEARANCE`，两边都必须**恰好** {"auditor"}，多一枚少一枚都红）
# 就是为了让这件事问得出来：谁给 auditor 补了档位，这两枚钉会同时要求他回答
# "要不要让它可创建"，而不是让名单悄悄漂移。
# ---------------------------------------------------------------------------
CREATABLE_ROLES: frozenset[str] = frozenset({"staff", "manager", "admin"})
