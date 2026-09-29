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
# R357：「可创建 / 可指派」的角色集 —— 全仓唯一一份定义；R413（H13 结案）把它补成四枚。
#
# 为什么真源长在这一格：这枚文件已经是角色词汇表的事实源（`ROLE_PERMISSIONS`），
# "哪些角色建得出、指派得动"是它的子集，两本账并排摆在同一屏里，"差的到底是哪一枚"
# 才读得出来。`app/common/auth.py`（建号与改派两处）与 `app/common/sso.py`（SSO 头里的
# 角色）一律 import 这一枚，不许再各自抄一份名单 —— 那三行手抄字面量是 R357 的病根。
#
# `auditor` 为什么 R357 那天不在、R413 起在（判据⑧要求写成一句人话，不许靠一份没来源的
# 四元组碰运气）：R357 开单那天 `app/common/rbac.py:31` 的 `ROLE_CLEARANCE` 只给 staff /
# manager / admin 三枚档位，**auditor 没有密级档位**，而密级口径是 H13、业主未裁 —— 谁都不
# 许替它编一档，把一个没档位的角色放进可创建集合就是拿一枚静默默认值顶替未决问题。H13 已于
# 2026-09-28 结案＝甲，同批裁定 auditor 的密级档位 = 3、与 admin 同档：审计员读不到机密件就是
# 假审计，「读得到但改不动」靠的是上面 `ROLE_PERMISSIONS` 那一行权限集，不是密级档。两枚差集
# 钉跟着改口到按新现实仍然可失败的形状：`CREATABLE_ROLES`、`ROLE_CLEARANCE`、`ROLE_PERMISSIONS`
# 三者键集两两差集都必须**恰好**是空集，多一枚少一枚都红（`tests/test_r413_auditor_role_admission.py`）。
# ---------------------------------------------------------------------------
CREATABLE_ROLES: frozenset[str] = frozenset({"staff", "manager", "admin", "auditor"})
