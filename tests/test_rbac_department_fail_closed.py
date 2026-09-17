"""R17 裁定＝甲的落地用例：数据行的部门口径与文档链对齐，改成 fail-closed。

钉住四条事实（``docs/handoff/2026-09-15-backend-followup-requests.md`` §13 甲案）：

1. **部门列为空的行对普通账号不可见**，只有 ``administrator_scope``（``role == "admin"``）看得到。
2. 非管理员且账号没有部门 ⇒ **一行数据行都不可见**。这一条专门封掉「天真改成 ``values == dept``」：
   账号侧是空串、行侧也是空串时两边相等，那种写法反而把空部门行全放行，比原缺陷更宽（判据 1）。
3. 灰度开关 ``RBAC_ROW_DEPARTMENT_SCOPE`` 默认 ``fail_closed``；写 ``legacy`` 必须**逐字复现**改动前
   ``rbac.py:51`` 的行为，所以本文件自带一份改动前源码的副本 ``legacy_filter_dataframe_rows`` 当参照物，
   不靠人记住旧口径长什么样。
4. 被「因缺部门而隐藏」的行数必须可观测（``DataFrame.attrs`` + WARNING 日志），不许静默吞行（判据 4）。

密级维度另有用例钉住「一个字都没改」：``fillna(1)`` 属 H13，等业主定口径（判据 5）。
"""
from __future__ import annotations

import inspect
import logging

import pandas as pd
import pytest

from app.common import rbac
from app.common.rbac import filter_dataframe_rows

SWITCH = rbac.ROW_DEPARTMENT_SCOPE_ENV
FAIL_CLOSED_ROWS = ["sales-a", "sales-d"]
LEGACY_ROWS = ["sales-a", "blank-c", "sales-d"]


def staff_frame(**overrides) -> pd.DataFrame:
    """四行表：两行本部门（其中一行带空白，用来钉住 strip 语义）、一行别部门、一行部门为空。"""
    data = {
        "name": ["sales-a", "hr-b", "blank-c", "sales-d"],
        "department": ["sales", "hr", "", "  sales  "],
        "value": [1, 2, 3, 4],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def classified_frame() -> pd.DataFrame:
    """密级 1 / 4 / 缺失三种行，部门一律 sales，把部门维度从密级用例里摘干净。"""
    return pd.DataFrame(
        {
            "name": ["level-1", "level-4", "level-missing"],
            "department": ["sales", "sales", "sales"],
            "classification": [1, 4, None],
        }
    )


def no_department_column_frame() -> pd.DataFrame:
    """压根没有部门列的表：本单只裁定「部门列为空的行」，不裁定这种表。"""
    return pd.DataFrame({"name": ["a", "b"], "value": [1, 2]})


def legacy_filter_dataframe_rows(df, role: str, department: str):
    """改动前 ``app/common/rbac.py:34-53`` 的逐字副本 —— 灰度回退的参照物，不许顺手「改进」。"""
    if role == "admin":
        return df

    scoped = df
    levels = set(rbac.allowed_levels(role))
    dept = department or ""

    class_col = next((c for c in rbac.ROW_CLASSIFICATION_COLUMNS if c in scoped.columns), None)
    if class_col:
        mask = scoped[class_col].fillna(1).astype(int).isin(levels)
        scoped = scoped[mask]

    dept_col = next((c for c in rbac.ROW_DEPARTMENT_COLUMNS if c in scoped.columns), None)
    if dept_col:
        values = scoped[dept_col].fillna("").astype(str).str.strip()
        scoped = scoped[values.isin(("", dept))]

    return scoped.reset_index(drop=True)


@pytest.fixture(autouse=True)
def _clean_switch(monkeypatch):
    """每条用例都从「环境变量未设」起步：宿主 shell 里残留的开关不得参与判定。"""
    monkeypatch.delenv(SWITCH, raising=False)


def names(df) -> list[str]:
    return list(df["name"])


def scope_of(df) -> dict:
    return df.attrs[rbac.ROW_SCOPE_ATTR]


class TestFailClosedCore:
    """判据 1 与判据 2：空部门行、账号无部门、管理员不变。"""

    def test_blank_department_row_is_invisible_to_same_department_staff(self):
        scoped = filter_dataframe_rows(staff_frame(), role="staff", department="sales")

        assert names(scoped) == FAIL_CLOSED_ROWS
        assert "blank-c" not in names(scoped), "部门列为空的行不许再对同密级账号放行"
        assert "hr-b" not in names(scoped)

    @pytest.mark.parametrize("column", rbac.ROW_DEPARTMENT_COLUMNS)
    def test_the_rule_holds_for_every_recognised_department_column(self, column):
        df = pd.DataFrame({"name": ["mine", "blank"], column: ["sales", ""]})

        scoped = filter_dataframe_rows(df, role="manager", department="sales")

        assert names(scoped) == ["mine"]

    @pytest.mark.parametrize("role", ["staff", "manager"])
    def test_non_admin_without_department_sees_not_a_single_row(self, role):
        scoped = filter_dataframe_rows(staff_frame(), role=role, department="")

        assert len(scoped) == 0
        assert scoped.empty is True

    def test_the_naive_equality_fix_would_have_reopened_the_blank_row(self):
        """判据 1 的陷阱本身：``values == dept`` 在账号无部门时会把空部门行放出来。"""
        df = staff_frame()
        values = df["department"].fillna("").astype(str).str.strip()
        naive = df[values == ""]

        assert names(naive) == ["blank-c"], "参照：天真改法在账号无部门时确实漏行"
        assert len(filter_dataframe_rows(df, role="staff", department="")) == 0

    def test_blank_department_rows_are_visible_only_under_administrator_scope(self):
        """裁定的正面表述：空部门行「仅 administrator_scope 可见」。"""
        df = staff_frame()
        staff = filter_dataframe_rows(df, role="staff", department="sales")
        admin = filter_dataframe_rows(df, role="admin", department="sales")

        assert "blank-c" not in names(staff)
        assert "blank-c" in names(admin)

    def test_administrator_scope_behaviour_is_word_for_word_unchanged(self):
        """判据 2：admin 早退必须逐字不变，连返回对象都不许换。"""
        df = staff_frame()

        scoped = filter_dataframe_rows(df, role="admin", department="")

        assert scoped is df
        assert names(scoped) == ["sales-a", "hr-b", "blank-c", "sales-d"]
        assert rbac.ROW_SCOPE_ATTR not in scoped.attrs

    def test_administrator_scope_is_not_affected_by_the_switch(self, monkeypatch):
        df = staff_frame()
        monkeypatch.setenv(SWITCH, "legacy")

        assert filter_dataframe_rows(df, role="admin", department="") is df

        monkeypatch.delenv(SWITCH)

        assert filter_dataframe_rows(df, role="admin", department="") is df


class TestGraySwitch:
    """判据 3：开关默认＝新行为生效；置回旧值＝与改动前 :51 逐字一致。"""

    @pytest.mark.parametrize(
        ("scope_value", "department", "expected"),
        [
            pytest.param(None, "sales", FAIL_CLOSED_ROWS, id="默认-新口径-只看本部门"),
            pytest.param(None, "", [], id="默认-新口径-账号无部门全隐藏"),
            pytest.param("legacy", "sales", LEGACY_ROWS, id="回退-空部门行回来"),
            pytest.param("legacy", "", ["blank-c"], id="回退-只剩空部门行"),
        ],
    )
    def test_the_switch_pins_both_row_rules_in_one_place(self, monkeypatch, scope_value, department, expected):
        if scope_value is not None:
            monkeypatch.setenv(SWITCH, scope_value)

        scoped = filter_dataframe_rows(staff_frame(), role="staff", department=department)

        assert names(scoped) == expected

    @pytest.mark.parametrize(
        ("role", "department"),
        [
            ("staff", "sales"),
            ("staff", ""),
            ("staff", "hr"),
            ("manager", "sales"),
            ("admin", "sales"),
            ("admin", ""),
        ],
    )
    @pytest.mark.parametrize("build", [staff_frame, classified_frame, no_department_column_frame])
    def test_legacy_value_is_row_for_row_identical_to_the_pre_r17_implementation(
        self, monkeypatch, build, role, department
    ):
        """旧值那一侧不是"差不多"，而是与改动前实现逐行相等（含密级列、无部门列、管理员）。"""
        monkeypatch.setenv(SWITCH, "legacy")
        df = build()

        scoped = filter_dataframe_rows(df, role=role, department=department)
        expected = legacy_filter_dataframe_rows(df, role, department)

        assert names(scoped) == names(expected)
        assert scoped.shape == expected.shape
        assert scoped.equals(expected)
        if role == "admin":
            assert scoped is df
            assert rbac.ROW_SCOPE_ATTR not in scoped.attrs
        else:
            assert scope_of(scoped)["scope"] == rbac.ROW_DEPARTMENT_SCOPE_LEGACY

    def test_the_switch_is_read_on_every_call_so_no_restart_is_needed(self, monkeypatch):
        df = staff_frame()

        assert names(filter_dataframe_rows(df, role="staff", department="sales")) == FAIL_CLOSED_ROWS

        monkeypatch.setenv(SWITCH, "legacy")

        assert names(filter_dataframe_rows(df, role="staff", department="sales")) == LEGACY_ROWS

    def test_fail_closed_diverges_from_legacy_exactly_on_blank_department_rows(self, monkeypatch):
        df = staff_frame()
        monkeypatch.setenv(SWITCH, "legacy")
        legacy = filter_dataframe_rows(df, role="staff", department="sales")
        monkeypatch.delenv(SWITCH)
        strict = filter_dataframe_rows(df, role="staff", department="sales")

        assert set(names(legacy)) - set(names(strict)) == {"blank-c"}
        assert not set(names(strict)) - set(names(legacy)), "新口径只许收紧，不许顺手放宽"

    def test_a_frame_without_blank_departments_reads_the_same_under_both_rules(self, monkeypatch):
        # 名字里的 blank-c 只是行标签：这里部门列已无空值，两侧必须给同一批行。
        df = staff_frame(department=["sales", "hr", "sales", "sales"])
        monkeypatch.setenv(SWITCH, "legacy")
        legacy = filter_dataframe_rows(df, role="staff", department="sales")

        strict = filter_dataframe_rows(df, role="staff", department="sales")

        assert names(strict) == names(legacy) == ["sales-a", "blank-c", "sales-d"]
        assert scope_of(strict)["rows_hidden_missing_department"] == 0

    @pytest.mark.parametrize(
        "scope_value",
        ["", "   ", "fail_closed", "FAIL_CLOSED", "fail-closed", "strict", "new", "1", "true", "yes", "乱写"],
    )
    def test_anything_that_is_not_explicitly_legacy_keeps_the_new_rule(self, monkeypatch, scope_value):
        """配置写错绝不能把可见范围放宽回去：默认必须是 fail_closed。"""
        monkeypatch.setenv(SWITCH, scope_value)

        scoped = filter_dataframe_rows(staff_frame(), role="staff", department="sales")

        assert names(scoped) == FAIL_CLOSED_ROWS
        assert scope_of(scoped)["scope"] == rbac.ROW_DEPARTMENT_SCOPE_FAIL_CLOSED

    @pytest.mark.parametrize(
        "scope_value",
        ["legacy", "LEGACY", " legacy ", "old", "open", "off", "0", "false", "no", "disabled"],
    )
    def test_explicit_legacy_spellings_restore_the_old_rule(self, monkeypatch, scope_value):
        monkeypatch.setenv(SWITCH, scope_value)

        scoped = filter_dataframe_rows(staff_frame(), role="staff", department="sales")

        assert names(scoped) == LEGACY_ROWS
        assert rbac.resolve_row_department_scope() == rbac.ROW_DEPARTMENT_SCOPE_LEGACY


class TestMigrationHintIsObservable:
    """判据 4：被「因缺部门而隐藏」的行数必须拿得到，不许静默吞行。"""

    def test_metadata_counts_the_rows_the_blank_department_rule_hid(self):
        info = scope_of(filter_dataframe_rows(staff_frame(), role="staff", department="sales"))

        assert info["reason_code"] == "department_scope"
        assert info["policy"] == rbac.ROW_DEPARTMENT_SCOPE_POLICY
        assert info["account_department"] == "sales"
        assert info["department_column"] == "department"
        assert info["rows_in"] == 4
        assert info["rows_after_clearance"] == 4
        assert info["rows_visible"] == 2
        assert info["rows_hidden_blank_department"] == 1
        assert info["rows_hidden_account_department"] == 0
        assert info["rows_hidden_missing_department"] == 1

    def test_metadata_counts_the_rows_a_department_less_account_lost(self):
        info = scope_of(filter_dataframe_rows(staff_frame(), role="manager", department=""))

        assert info["reason_code"] == "authorization_unavailable"
        assert info["rows_visible"] == 0
        assert info["rows_hidden_blank_department"] == 1
        assert info["rows_hidden_account_department"] == 3
        assert info["rows_hidden_missing_department"] == 4

    def test_not_a_single_row_disappears_without_being_counted(self):
        info = scope_of(filter_dataframe_rows(staff_frame(), role="staff", department="sales"))

        # 部门维度藏掉的行分两类：缺部门（本单新增的隐藏）与别部门（一直就有的正常拒绝）。
        assert info["rows_hidden_by_department"] == 2
        assert info["rows_hidden_missing_department"] == 1
        assert (
            info["rows_visible"] + info["rows_hidden_by_department"] == info["rows_after_clearance"]
        )

    def test_the_hidden_rows_also_surface_as_a_warning_log(self, caplog):
        with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
            filter_dataframe_rows(staff_frame(), role="staff", department="sales")

        assert "[RBAC]" in caplog.text
        assert "reason=department_scope" in caplog.text
        assert "隐藏数据行 1 行" in caplog.text

    def test_a_frame_that_hides_no_department_rows_logs_nothing(self, caplog):
        df = staff_frame(department=["sales", "hr", "sales", "sales"])
        with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
            filter_dataframe_rows(df, role="staff", department="sales")

        assert [r for r in caplog.records if r.name == "enterprise_brain"] == []

    def test_the_helper_returns_the_same_rows_plus_the_metadata(self):
        scoped, info = rbac.filter_dataframe_rows_with_scope(
            staff_frame(), role="staff", department="sales"
        )

        assert names(scoped) == FAIL_CLOSED_ROWS
        assert info["rows_hidden_missing_department"] == 1
        assert info["reason_code"] == "department_scope"

    def test_the_helper_describes_admin_without_touching_the_frame(self):
        df = staff_frame()

        scoped, info = rbac.filter_dataframe_rows_with_scope(df, role="admin", department="")

        assert scoped is df
        assert info["reason_code"] == "administrator_scope"
        assert info["rows_hidden_missing_department"] == 0
        assert rbac.ROW_SCOPE_ATTR not in df.attrs

    def test_agents_tools_callers_still_get_a_plain_dataframe(self):
        """app/agents/tools.py:393、:473 直接 ``df = filter_dataframe_rows(...)``，返回类型不许变成元组。"""
        scoped = filter_dataframe_rows(staff_frame(), role="staff", department="sales")

        assert isinstance(scoped, pd.DataFrame)
        assert isinstance(scoped.head(15), pd.DataFrame)
        assert scoped.to_dict(orient="records")


class TestClassificationDimensionIsUntouched:
    """判据 5：密级维度一个字都不许改（``fillna(1)`` 属 H13，等业主定口径）。"""

    CLEARANCE_LINE = "mask = scoped[class_col].fillna(1).astype(int).isin(levels)"

    def test_the_clearance_predicate_line_is_still_the_original(self):
        assert self.CLEARANCE_LINE in inspect.getsource(rbac.filter_dataframe_rows)

    @pytest.mark.parametrize("scope_value", [None, "legacy"])
    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            ("staff", ["level-1", "level-missing"]),
            ("manager", ["level-1", "level-missing"]),
            ("admin", ["level-1", "level-4", "level-missing"]),
        ],
    )
    def test_missing_classification_is_still_read_as_level_one(
        self, monkeypatch, scope_value, role, expected
    ):
        if scope_value is not None:
            monkeypatch.setenv(SWITCH, scope_value)

        scoped = filter_dataframe_rows(classified_frame(), role=role, department="sales")

        assert names(scoped) == expected

    def test_clearance_axis_gives_the_same_rows_before_and_after_the_fix(self, monkeypatch):
        df = classified_frame()
        monkeypatch.setenv(SWITCH, "legacy")
        before = filter_dataframe_rows(df, role="staff", department="sales")
        monkeypatch.delenv(SWITCH)

        after = filter_dataframe_rows(df, role="staff", department="sales")

        assert names(after) == names(before) == legacy_filter_dataframe_rows(df, "staff", "sales").to_dict(orient="list")["name"]


class TestFrameWithoutDepartmentColumn:
    """没有部门列的表不在本单裁定范围内，但账号无部门时同样 fail-closed，口径要写清楚。"""

    def test_an_account_with_a_department_keeps_the_clearance_only_view(self):
        df = no_department_column_frame()

        scoped = filter_dataframe_rows(df, role="staff", department="sales")

        assert names(scoped) == ["a", "b"]
        assert scope_of(scoped)["reason_code"] == "department_column_missing"

    def test_an_account_without_a_department_still_gets_nothing(self):
        """判据 1 的字面口径：非管理员且账号无部门 ⇒ 一行都不可见，与有没有部门列无关。"""
        df = no_department_column_frame()

        scoped = filter_dataframe_rows(df, role="staff", department="")

        assert len(scoped) == 0
        assert scope_of(scoped)["reason_code"] == "authorization_unavailable"
        assert scope_of(scoped)["rows_hidden_missing_department"] == 2

    def test_the_legacy_switch_leaves_such_a_frame_alone(self, monkeypatch):
        monkeypatch.setenv(SWITCH, "legacy")

        scoped = filter_dataframe_rows(no_department_column_frame(), role="staff", department="")

        assert names(scoped) == ["a", "b"]


class TestTheRulingIsRecordedInTheSource:
    """防「顺手统一」与防原缺陷复活的两条静态守卫。"""

    def test_the_old_open_department_predicate_only_survives_in_the_fallback_branch(self):
        source = inspect.getsource(rbac.filter_dataframe_rows)

        lines = [line.strip() for line in source.splitlines()]
        hits = [index for index, line in enumerate(lines) if 'values.isin(("", dept))' in line]

        assert len(hits) == 1, "旧口径只许留在灰度回退那一支"
        assert lines[hits[0] - 2] == "if scope == ROW_DEPARTMENT_SCOPE_LEGACY:"
        assert "elif not dept:" in lines[hits[0] :], "账号无部门那一支必须在回退支之后"
        assert 'scoped = scoped.iloc[0:0]' in source, "账号无部门那一支得真的把行清空"


    def test_the_module_docstring_no_longer_shops_the_old_rule_as_current(self):
        head = inspect.getsource(rbac).split("def clearance_for")[0]

        assert "注意它沿用的仍是旧口径" not in head
        assert SWITCH in head
        assert "R17" in head
