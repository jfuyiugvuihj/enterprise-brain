"""角色密级表与数据行过滤（原「阶段 2 简化权限」模块，已收敛到只剩两件活事）。

**文档可见性的判定不在这里，也不许回到这里。** 唯一判定是
``app/rag/filters.py::resolve_document_retrieval_scope``：它一次产出下推给向量库的
``filters`` 与本地复核用的 ``allows``，两者同源于一个 scope 对象
（``app/rag/retrieval_pipeline.py`` 的 ``search_for_principal`` 只调它一次），
所以对「谁能看见什么」不可能给出两种答案。按 e2 裁定：``administrator_scope`` 的账号
不受部门限制；普通账号没有部门就直接拒（``authorization_unavailable``）；
**部门为空的文档对普通账号不可见**（fail-closed，而不是「公开」）。
守卫见 ``tests/test_rbac_single_scoping_source.py``。

本模块现在只提供：

- ``ROLE_CLEARANCE`` / ``clearance_for`` / ``allowed_levels``：角色到密级档位的映射。
- ``filter_dataframe_rows``：表格数据的行级过滤（被 ``app/agents/tools.py`` 调用）。
  注意它沿用的仍是旧口径：**部门列为空的行对任何同密级账号可见**，与上面文档链的
  fail-closed 相反。这是有记录的待决项 R17（``docs/handoff/2026-09-15-backend-followup-requests.md``），
  改它等于改客户数据的可见范围，必须业务点头，别顺手「统一」。
"""

ROLE_CLEARANCE = {"staff": 1, "manager": 2, "admin": 3}
ROW_DEPARTMENT_COLUMNS = ("department", "dept", "部门", "所属部门")
ROW_CLASSIFICATION_COLUMNS = ("classification", "密级", "security_level")


def clearance_for(role: str) -> int:
    return ROLE_CLEARANCE.get(role or "staff", 1)


def allowed_levels(role: str) -> list[int]:
    return list(range(1, clearance_for(role) + 1))


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
