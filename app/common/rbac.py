"""
阶段 2 · 简化权限（密级模型）

角色 → 权限等级 clearance：staff=1, manager=2, admin=3
文档 → 密级 classification：1公开 2内部 3机密；department 为空串=全部门可见
访问条件：clearance >= classification 且（doc.department=="" 或 == 用户部门）
admin 直接放行（不设过滤）。

提供两种过滤器：
- build_where(): Chroma 语义检索的 where 下推
- make_pred():  BM25 内存检索的 Python 谓词
"""

ROLE_CLEARANCE = {"staff": 1, "manager": 2, "admin": 3}
ROW_DEPARTMENT_COLUMNS = ("department", "dept", "部门", "所属部门")
ROW_CLASSIFICATION_COLUMNS = ("classification", "密级", "security_level")


def clearance_for(role: str) -> int:
    return ROLE_CLEARANCE.get(role or "staff", 1)


def allowed_levels(role: str) -> list[int]:
    return list(range(1, clearance_for(role) + 1))


def doc_visible(doc_classification: int, doc_department: str,
                role: str, user_department: str) -> bool:
    """单个文档对某用户是否可见"""
    if role == "admin":
        return True
    if (doc_classification or 1) > clearance_for(role):
        return False
    if doc_department and doc_department != (user_department or ""):
        return False
    return True


def build_where(role: str, department: str) -> dict | None:
    """Chroma where 下推；admin 返回 None（不过滤）"""
    if role == "admin":
        return None
    levels = allowed_levels(role)
    return {
        "$and": [
            {"classification": {"$in": levels}},
            {"$or": [{"department": ""}, {"department": department or ""}]},
        ]
    }


def make_pred(role: str, department: str):
    """BM25 内存过滤谓词"""
    if role == "admin":
        return lambda d: True
    levels = allowed_levels(role)
    dept = department or ""
    return lambda d: (
        (d.get("classification", 1) in levels)
        and (d.get("department", "") in ("", dept))
    )


def filter_dataframe_rows(df, role: str, department: str):
    """Apply row-level department/classification filtering to tabular data."""
    if role == "admin":
        return df

    scoped = df
    levels = set(allowed_levels(role))
    dept = department or ""

    class_col = next((col for col in ROW_CLASSIFICATION_COLUMNS if col in scoped.columns), None)
    if class_col:
        mask = scoped[class_col].fillna(1).astype(int).isin(levels)
        scoped = scoped[mask]

    dept_col = next((col for col in ROW_DEPARTMENT_COLUMNS if col in scoped.columns), None)
    if dept_col:
        values = scoped[dept_col].fillna("").astype(str).str.strip()
        scoped = scoped[values.isin(("", dept))]

    return scoped.reset_index(drop=True)
