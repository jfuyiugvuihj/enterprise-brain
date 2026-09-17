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
  按 R17 裁定＝甲（``docs/handoff/2026-09-15-backend-followup-requests.md`` §13）它现在与文档链
  **同口径**：部门列为空的行对普通账号不可见；非管理员且账号没有部门时一行数据行都不可见
  （``authorization_unavailable``，与文档链同一个码）；只有 ``role == "admin"``
  ——即 ``administrator_scope``，``:36`` 早退——看得到空部门行。
  灰度开关 ``RBAC_ROW_DEPARTMENT_SCOPE``：默认 ``fail_closed``（新口径生效），写 ``legacy`` 整块退回旧口径。
  被隐藏的行数不静默：既进返回帧的 ``df.attrs[ROW_SCOPE_ATTR]``，也打一条 WARNING 日志。
  用例见 ``tests/test_rbac_department_fail_closed.py``。

密级维度不在本单范围内：``fillna(1)``（缺密级按最低档处理）属 H13，等业主定口径，这里一个字没改。
"""

import os

from app.common.logger import logger

ROLE_CLEARANCE = {"staff": 1, "manager": 2, "admin": 3}
ROW_DEPARTMENT_COLUMNS = ("department", "dept", "部门", "所属部门")
ROW_CLASSIFICATION_COLUMNS = ("classification", "密级", "security_level")


# R17 灰度开关：默认新口径生效，回到旧口径必须是显式赋值，不能被拼错的配置值顺带放宽。
ROW_DEPARTMENT_SCOPE_ENV = "RBAC_ROW_DEPARTMENT_SCOPE"
ROW_DEPARTMENT_SCOPE_FAIL_CLOSED = "fail_closed"
ROW_DEPARTMENT_SCOPE_LEGACY = "legacy"
ROW_DEPARTMENT_SCOPE_POLICY = "r17-row-department-fail-closed"
_LEGACY_SCOPE_VALUES = frozenset({"legacy", "old", "open", "off", "0", "false", "no", "disabled"})

# 返回帧上携带的行级口径元数据：app/agents/tools.py 的调用方拿得到（R17 判据 4）。
ROW_SCOPE_ATTR = "rbac_row_scope"


def clearance_for(role: str) -> int:
    return ROLE_CLEARANCE.get(role or "staff", 1)


def allowed_levels(role: str) -> list[int]:
    return list(range(1, clearance_for(role) + 1))


def resolve_row_department_scope() -> str:
    """本次调用按哪套部门口径判：``fail_closed``（默认）还是 ``legacy``。

    未设、空、拼错、值连字符串都读不出来，一律按 ``fail_closed``：把可见范围放宽回旧口径
    必须是一次写得出来的显式赋值，不能被一个打错的配置值静默开启。
    """
    raw = os.getenv(ROW_DEPARTMENT_SCOPE_ENV, "")
    try:
        normalized = str(raw or "").strip().lower().replace("_", "-")
    except Exception:  # pragma: no cover - 配置值连字符串都读不出来时按最严的一档
        return ROW_DEPARTMENT_SCOPE_FAIL_CLOSED
    if normalized in _LEGACY_SCOPE_VALUES:
        return ROW_DEPARTMENT_SCOPE_LEGACY
    return ROW_DEPARTMENT_SCOPE_FAIL_CLOSED


def _row_scope_info(role: str, department: str, **overrides) -> dict:
    """行级口径元数据的唯一构造点，避免两条路径各写一份字段清单。

    ``rows_hidden_blank_department`` 是行侧（部门列为空）被藏起来的行数，也就是旧口径会给、
    新口径不给的那批；``rows_hidden_account_department`` 是账号侧没有部门而被额外藏起来的行数
    （含确实归属某个部门的行）；两者相加才是 ``rows_hidden_missing_department``。
    ``rows_hidden_by_department`` 是部门维度藏掉的总行数（含「属于别部门」这种一直就有的拒绝），
    它保证「密级内可见 = 实际可见 + 被部门藏掉」这笔账在任何口径下都对得平。
    """
    info = {
        "policy": ROW_DEPARTMENT_SCOPE_POLICY,
        "scope": ROW_DEPARTMENT_SCOPE_FAIL_CLOSED,
        "role": role,
        "account_department": department or "",
        "department_column": None,
        "classification_column": None,
        "rows_in": 0,
        "rows_after_clearance": 0,
        "rows_visible": 0,
        "rows_hidden_blank_department": 0,
        "rows_hidden_account_department": 0,
        "rows_hidden_missing_department": 0,
        # 部门维度藏掉的总行数，用来让「进得来几行、藏掉几行」这笔账在任何口径下都对得平。
        "rows_hidden_by_department": 0,
        "reason_code": "",
    }
    info.update(overrides)
    info["rows_hidden_missing_department"] = (
        info["rows_hidden_blank_department"] + info["rows_hidden_account_department"]
    )
    info["rows_hidden_by_department"] = max(
        0, info["rows_after_clearance"] - info["rows_visible"]
    )
    return info


def _report_hidden_rows(info: dict) -> None:
    """迁移期提示：因缺部门而隐藏的行必须可观测，不许静默吞行（R17 判据 4）。"""
    hidden = int(info["rows_hidden_missing_department"])
    if hidden <= 0:
        return
    logger.warning(
        "[RBAC] 部门口径隐藏数据行 %d 行：reason=%s scope=%s account_department=%r "
        "department_column=%s 行部门为空=%d 账号缺部门=%d 密级内可见=%d 实际可见=%d",
        hidden,
        info["reason_code"],
        info["scope"],
        info["account_department"],
        info["department_column"],
        info["rows_hidden_blank_department"],
        info["rows_hidden_account_department"],
        info["rows_after_clearance"],
        info["rows_visible"],
    )


def filter_dataframe_rows(df, role: str, department: str):
    """Apply row-level department/classification filtering to tabular data.

    密级维度沿用原实现（H13 未定口径）。部门维度按 R17 裁定＝甲 fail-closed：非管理员只有
    「行部门 == 自己部门」才可见，行部门为空一律不可见；账号本身没有部门时一行都不给。
    **这里绝不能写成 ``values == dept``**：账号侧是空串、行侧也是空串时它反而把空部门行全放行，
    比原缺陷更宽（R17 判据 1 的陷阱），所以「账号无部门」这一支必须在任何比较之前单独判掉。

    返回类型保持 DataFrame 不变（``app/agents/tools.py:393``、``:473`` 直接当帧用），口径与
    隐藏行数写在 ``result.attrs[ROW_SCOPE_ATTR]``，也可用 ``filter_dataframe_rows_with_scope`` 显式取。
    """
    if role == "admin":
        return df

    scoped = df
    rows_in = len(df)
    levels = set(allowed_levels(role))
    dept = department or ""

    class_col = next((col for col in ROW_CLASSIFICATION_COLUMNS if col in scoped.columns), None)
    if class_col:
        mask = scoped[class_col].fillna(1).astype(int).isin(levels)
        scoped = scoped[mask]

    rows_after_clearance = len(scoped)
    dept_col = next((col for col in ROW_DEPARTMENT_COLUMNS if col in scoped.columns), None)
    scope = resolve_row_department_scope()
    hidden_blank = 0
    hidden_account = 0

    if dept_col:
        values = scoped[dept_col].fillna("").astype(str).str.strip()
        blank_rows = int((values == "").sum())
        if scope == ROW_DEPARTMENT_SCOPE_LEGACY:
            # 灰度回退：这一行就是改动前的 :51，逐字保留，给现场留一条退路。
            scoped = scoped[values.isin(("", dept))]
            reason_code = "legacy_open_department_scope"
        elif not dept:
            # 非管理员且账号没有部门 ⇒ 一行都不给；必须在 values == dept 之前判掉，见 docstring。
            hidden_blank = blank_rows
            hidden_account = rows_after_clearance - blank_rows
            scoped = scoped.iloc[0:0]
            reason_code = "authorization_unavailable"
        else:
            hidden_blank = blank_rows
            scoped = scoped[values == dept]
            reason_code = "department_scope"
    elif not dept and scope != ROW_DEPARTMENT_SCOPE_LEGACY:
        # 表里根本没有部门列：本单只裁定「部门列为空的行」，有部门的账号维持密级过滤；
        # 但账号没有部门时同样 fail-closed，与文档链在看任何资源之前就把人拒掉是同一个次序。
        hidden_account = rows_after_clearance
        scoped = scoped.iloc[0:0]
        reason_code = "authorization_unavailable"
    else:
        reason_code = "department_column_missing"

    scoped = scoped.reset_index(drop=True)
    scoped.attrs[ROW_SCOPE_ATTR] = _row_scope_info(
        role,
        dept,
        scope=scope,
        department_column=dept_col,
        classification_column=class_col,
        rows_in=rows_in,
        rows_after_clearance=rows_after_clearance,
        rows_visible=len(scoped),
        rows_hidden_blank_department=hidden_blank,
        rows_hidden_account_department=hidden_account,
        reason_code=reason_code,
    )
    _report_hidden_rows(scoped.attrs[ROW_SCOPE_ATTR])
    return scoped


def filter_dataframe_rows_with_scope(df, role: str, department: str) -> tuple:
    """``filter_dataframe_rows`` 的同一批行，外加一份行级口径元数据。

    ``filter_dataframe_rows`` 的签名与返回类型都不许改（两处调用点直接把它当 DataFrame 用），
    所以本单要的可观测性主走 ``DataFrame.attrs`` + 日志；这里再给一个显式入口，调用方想拿
    隐藏行数就不必自己拆 attrs。管理员在早退那一行原样返回帧、不带元数据，这里补齐，
    口径名与 ``app/common/policy.py:202`` 的 ``administrator_scope`` 同名。
    """
    scoped = filter_dataframe_rows(df, role=role, department=department)
    info = scoped.attrs.get(ROW_SCOPE_ATTR)
    if info is None:
        info = _row_scope_info(
            role,
            department,
            reason_code="administrator_scope",
            rows_in=len(df),
            rows_after_clearance=len(df),
            rows_visible=len(df),
        )
    return scoped, dict(info)
