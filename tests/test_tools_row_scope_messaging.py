"""跟进单 R62：被权限隐藏的数据行，不能被说成「LLM 生成的代码执行未通过」。

判据出处 ``docs/handoff/2026-09-15-backend-followup-requests.md`` §23 的 R62 行，续 §13（R17 裁定＝甲）。
本单**只改怎么说、不改怎么选行**：行级判定的唯一出处仍是 ``app/common/rbac.py::filter_dataframe_rows``，
它的口径用例在 ``tests/test_rbac_department_fail_closed.py``，本文件一条都不重复测判定。

钉住五条：

1. 判据① 全部文件都因权限没有可见行时，终态必须报权限因由，且不得出现「代码」「沙箱」「执行未通过」。
2. 判据② 确实有可见行而查询没过时，仍报原来那句执行失败终态，一字不改。
3. 判据③ ``_analyze_data`` 的「没有可见数据行」按 ``reason_code`` 分开说：账号无部门被整体拒
   （``authorization_unavailable``）与行属别的部门 / 部门为空被藏（``department_scope``）是两句话。
4. 判据④ 反证锚点：文案改回单一「执行未通过」本文件必红——判据 1/2 的用例同时断言
   「这句必须在、那句必须不在」，而不是只查一个关键词。
5. 判据⑤ 工具层交给下游的行必须与 ``filter_dataframe_rows`` 选出的行逐字一致，不许多筛一行少筛一行。

全程离线：唯一需要模型的 ``_llm_pandas_code`` 在 fixture 里被换成「一被调用就红」的假实现。
"""
from __future__ import annotations

import inspect
import io
import re

import pandas as pd
import pytest

from app.agents import tools
from app.agents.tools import _analyze_data, _NO_VISIBLE_ROWS, _query_data
from app.common import rbac

# 判据①禁止出现在权限终态里的三个字样。
EXECUTION_BLAME = ("代码", "沙箱", "执行未通过")

# 判据②要求逐字保留的原终态。
EXECUTION_FAILURE = "查询失败：LLM 生成的代码在沙箱中多次执行未通过，请换个问法。"

HEADER = "name,department,金额\n"
MIXED_CSV = HEADER + "sales-a,sales,100\nhr-b,hr,200\nblank-c,,300\nsales-d,sales,400\n"
OWN_DEPARTMENT_CSV = HEADER + "sales-a,sales,100\nsales-d,sales,400\n"
OTHER_DEPARTMENT_CSV = HEADER + "hr-b,hr,200\nblank-c,,300\n"
FOREIGN_ONLY_CSV = HEADER + "hr-b,hr,200\n"
BLANK_ONLY_CSV = HEADER + "blank-c,,300\nblank-e,,500\n"
NO_ROWS_CSV = HEADER

# 三行都属本部门、但行级过滤后一帧不剩：部门维度一行都没藏过，因由不许瞎猜。
CLEARANCE_ONLY_CSV = "name,department,金额,classification\nsecret-a,sales,100,4\nsecret-b,sales,200,4\n"


def _config(role: str = "staff", department: str = "sales") -> dict:
    return {
        "configurable": {
            "user_id": "7",
            "username": "tester",
            "role": role,
            "department": department,
        }
    }


def _frame(body: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(body))


def _files(monkeypatch, tmp_path, *specs: tuple[str, str]) -> None:
    """把 (文件名, CSV 正文) 直接接成 ``_authorized_dataset_files`` 的返回值。

    整张表能不能被这个账号碰到由另一条线（resource_scope）判，本单只盯行级口径，所以钉死它。
    """
    resolved = []
    for filename, body in specs:
        path = tmp_path / filename
        path.write_text(body, encoding="utf-8")
        resolved.append((filename, str(path)))
    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: (resolved, None))


def _fake_code(monkeypatch, code: str) -> list:
    """让「生成的东西」固定为 ``code``，并记下工具层交下来的行。"""
    handed: list = []

    def fake(df, query):
        handed.append(list(df["name"]))
        return code

    monkeypatch.setattr(tools, "_llm_pandas_code", fake)
    return handed


def _blamed(answer: str) -> list[str]:
    return [term for term in EXECUTION_BLAME if term in answer]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """宿主模型与宿主 shell 里残留的灰度开关都不许参与本文件的判定。"""
    monkeypatch.delenv(rbac.ROW_DEPARTMENT_SCOPE_ENV, raising=False)

    def _never_call_the_model(df, query):
        raise AssertionError("_llm_pandas_code 被调用了：这条用例不该去请模型生成东西")

    monkeypatch.setattr(tools, "_llm_pandas_code", _never_call_the_model)


class TestQueryDataPermissionTerminal:
    """判据①：因权限而空的终态报权限因由，不污蔑用户的问法。"""

    def test_every_file_hidden_by_rowscope_reports_the_authorization_reason(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV), ("orders.csv", BLANK_ONLY_CSV))

        answer = _query_data("各部门金额合计", _config(role="staff", department="sales"))

        assert not _blamed(answer), f"权限导致的空结果被说成代码问题：{_blamed(answer)}\n{answer}"
        assert "换个问法" not in answer, answer
        assert "可见范围" in answer, answer
        assert "未标注部门" in answer, answer
        assert "属于其他部门" in answer, answer

    def test_the_denial_names_both_hidden_row_kinds_for_the_same_file(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))

        answer = _query_data("各部门金额合计", _config(role="staff", department="sales"))

        assert "1 行未标注部门" in answer, answer
        assert "1 行属于其他部门" in answer, answer

    def test_an_account_without_a_department_is_not_told_to_rephrase(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", MIXED_CSV))

        answer = _query_data("各部门金额合计", _config(role="staff", department=""))

        assert not _blamed(answer), answer
        assert "没有部门归属" in answer, answer
        assert "属于其他部门" not in answer, answer

    def test_the_permission_terminal_carries_no_bare_code_name(self, tmp_path, monkeypatch):
        """R16 那条政策对后端同样成立：用户可见文案里不许夹裸码名。"""
        _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))

        answer = _query_data("各部门金额合计", _config(role="staff", department="sales"))

        assert "error_code" not in answer, answer
        for code in ("department_scope", "authorization_unavailable", "row_scope_denied"):
            assert code not in answer, answer


class TestQueryDataExecutionTerminal:
    """判据②：有可见行而查询确实没过时，原话一字不改地留着。"""

    def test_visible_rows_with_a_failing_query_still_get_the_original_copy(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", OWN_DEPARTMENT_CSV))
        _fake_code(monkeypatch, 'df["营收"].sum()')

        answer = _query_data("金额合计", _config(role="staff", department="sales"))

        assert answer == EXECUTION_FAILURE, answer

    def test_a_passing_query_still_returns_the_number(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", OWN_DEPARTMENT_CSV))
        _fake_code(monkeypatch, 'df["金额"].sum()')

        answer = _query_data("金额合计", _config(role="staff", department="sales"))

        assert "查询结果" in answer, answer
        assert "500" in answer, answer

    def test_the_two_terminals_are_two_different_sentences(self, tmp_path, monkeypatch):
        """判据①②合起来的那条：两种终态不许合并成一句模糊话。"""
        _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))
        hidden = _query_data("各部门金额合计", _config(role="staff", department="sales"))

        _files(monkeypatch, tmp_path, ("sales.csv", OWN_DEPARTMENT_CSV))
        _fake_code(monkeypatch, 'df["营收"].sum()')
        failed = _query_data("金额合计", _config(role="staff", department="sales"))

        assert hidden != failed, hidden
        assert not _blamed(hidden), hidden
        assert _blamed(failed), failed


class TestQueryDataOtherEmptyTerminals:
    """判据①的边界：表本来是空的、文件读不出来，都不许算成权限，也不许算成查询没通过。"""

    def test_a_file_with_no_rows_is_not_reported_as_a_permission_block(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", NO_ROWS_CSV))

        answer = _query_data("金额合计", _config(role="staff", department="sales"))

        assert not _blamed(answer), answer
        assert "权限" not in answer, answer
        assert "可见范围" not in answer, answer
        assert "没有可分析的数据行" in answer, answer

    def test_a_file_that_cannot_be_read_is_not_blamed_on_the_question(self, tmp_path, monkeypatch):
        missing = tmp_path / "gone.csv"
        monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: ([("gone.csv", str(missing))], None))

        answer = _query_data("金额合计", _config(role="staff", department="sales"))

        assert not _blamed(answer), answer
        assert "载入失败" in answer, answer


class TestAnalyzeDataReasons:
    """判据③：同一句「没有可见数据行」必须按 ``reason_code`` 分成不同的话。"""

    def test_rows_from_other_departments_and_blank_rows_are_both_named(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "未标注部门" in answer, answer
        assert "属于其他部门" in answer, answer
        assert "没有部门归属" not in answer, answer

    def test_blank_department_rows_alone_are_reported_separately(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", BLANK_ONLY_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "未标注部门" in answer, answer
        assert "属于其他部门" not in answer, answer

    def test_foreign_department_rows_alone_are_reported_separately(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", FOREIGN_ONLY_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "属于其他部门" in answer, answer
        assert "未标注部门" not in answer, answer

    def test_an_account_without_a_department_says_so(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", MIXED_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department=""))

        assert "没有部门归属" in answer, answer
        assert "未标注部门" not in answer, answer
        assert "属于其他部门" not in answer, answer

    def test_the_three_reasons_produce_three_different_sentences(self, tmp_path, monkeypatch):
        copies = []
        for filename, body, role, dept in (
            ("a.csv", OTHER_DEPARTMENT_CSV, "staff", "sales"),
            ("a.csv", MIXED_CSV, "staff", ""),
            ("a.csv", NO_ROWS_CSV, "staff", "sales"),
        ):
            _files(monkeypatch, tmp_path, (filename, body))
            copies.append(_analyze_data("金额合计", _config(role=role, department=dept)))

        assert len(set(copies)) == 3, copies

    def test_an_admin_still_sees_blank_department_rows(self, tmp_path, monkeypatch):
        """管理员早退路径的 ``attrs`` 是空的，补齐之后也不许被说成权限问题（R62 只改文案）。"""
        _files(monkeypatch, tmp_path, ("sales.csv", BLANK_ONLY_CSV))

        answer = _analyze_data("金额合计", _config(role="admin", department=""))

        assert "未标注部门" not in answer, answer
        assert "没有部门归属" not in answer, answer
        assert "2行" in answer, answer


class TestSelectionIsUnchanged:
    """判据⑤：本单零判定变化 —— 交下去的行与 ``filter_dataframe_rows`` 选出的行逐字相同。"""

    def test_query_data_hands_down_exactly_the_rows_rbac_selects(self, tmp_path, monkeypatch):
        expected = list(rbac.filter_dataframe_rows(_frame(MIXED_CSV), role="staff", department="sales")["name"])
        assert expected == ["sales-a", "sales-d"], "R17 的裁定被这单改动了"

        _files(monkeypatch, tmp_path, ("sales.csv", MIXED_CSV))
        handed = _fake_code(monkeypatch, 'df["金额"].sum()')

        _query_data("金额合计", _config(role="staff", department="sales"))

        assert handed == [expected], handed

    def test_analyze_data_profiles_exactly_the_rows_rbac_selects(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("sales.csv", MIXED_CSV))

        answer = _analyze_data("哪个金额最高", _config(role="staff", department="sales"))

        assert "2行" in answer, answer
        assert "sales-a" in answer and "sales-d" in answer, answer
        for hidden_row in ("hr-b", "blank-c"):
            assert hidden_row not in answer, f"{hidden_row} 漏进了分析结果：{answer}"


class TestNoGuessing:
    """判据③的反面：因由不在部门维度上时，本单不许把它说成部门问题（密级结论也不许下）。"""

    def test_analyze_data_stays_neutral_when_the_department_dimension_hid_nothing(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("secret.csv", CLEARANCE_ONLY_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        for guessed in ("属于其他部门", "未标注部门", "没有部门归属", "可见范围"):
            assert guessed not in answer, f"{guessed} 是无依据的因由：{answer}"
        assert _NO_VISIBLE_ROWS in answer, answer

    def test_query_data_does_not_invent_an_authorization_reason(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("secret.csv", CLEARANCE_ONLY_CSV))

        answer = _query_data("金额合计", _config(role="staff", department="sales"))

        assert not _blamed(answer), answer
        for guessed in ("属于其他部门", "未标注部门", "没有部门归属", "可见范围", "权限"):
            assert guessed not in answer, f"{guessed} 是无依据的因由：{answer}"


class TestNoParallelImplementation:
    """判据③④的守卫：因由只能来自 rbac，文案层不许长出第二套判定。"""

    def test_both_data_tools_consume_the_rbac_scope_entry_point(self):
        for fn in (_query_data, _analyze_data):
            source = inspect.getsource(fn)
            assert "filter_dataframe_rows_with_scope" in source, fn.__name__
            assert re.search(r"filter_dataframe_rows\(", source) is None, fn.__name__

    def test_tools_py_does_not_reimplement_the_row_scope(self):
        source = inspect.getsource(tools)
        for token in (
            "ROW_DEPARTMENT_COLUMNS",
            "ROW_CLASSIFICATION_COLUMNS",
            "ROLE_CLEARANCE",
            "allowed_levels",
            "clearance_for",
            "resolve_row_department_scope",
            "isin(",
            "fillna(1)",
        ):
            assert token not in source, f"tools.py 里出现了平行判定的痕迹：{token}"


# ==================== 总控收口补充（09-18）：判据①的正解面 ====================
# 执行层交付的 21 例把「有部门列」的三支都钉住了，但 R62 退回的那条缺陷——
# ``department_column_missing`` 下把账挂到部门列上——修好之后**没有任何用例钉住它**，
# 灰度回退档（``legacy_open_department_scope``）的文案也一例未涉。下面三类补上。

# 三行都被密级维度清空（staff 上限 1，这里全是 4），而这张表**根本没有部门列**。
# 这正是缺陷现场 S1：部门维度一行都没藏过，rows_in 还是密级过滤**之前**的计数。
CLEARANCE_ONLY_NO_DEPT_CSV = "name,金额,classification\nsecret-a,100,4\nsecret-b,200,4\n"


class TestClearanceClearedTableWithoutDepartmentColumn:
    """S1 复现：无部门列 + 密级清空 ⇒ 只许走中性文案，一个字都不许提部门列。"""

    def test_it_uses_the_neutral_sentence(self, tmp_path, monkeypatch):
        _files(monkeypatch, tmp_path, ("policy.csv", CLEARANCE_ONLY_NO_DEPT_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "当前账号没有可见数据行" in answer, answer
        assert "部门列" not in answer, answer
        assert "属于其他部门" not in answer, answer
        assert "未标注部门" not in answer, answer
        # 密级维度的口径属 H13（业主未裁），本单不许借文案对它下任何结论。
        assert "密级" not in answer, answer

    def test_the_reason_layer_hands_back_nothing(self):
        reason = tools._row_scope_reason(
            {
                "reason_code": "department_column_missing",
                "rows_in": 2,
                "rows_visible": 0,
                "rows_after_clearance": 0,
                "rows_hidden_by_department": 0,
                "account_department": "sales",
            }
        )

        assert reason == ""

    def test_a_nonzero_department_count_cannot_reopen_that_branch(self):
        """守门：这一支部门维度永远是 0；上游即使给了非 0 也不许据此说话。"""
        reason = tools._row_scope_reason(
            {
                "reason_code": "department_column_missing",
                "rows_in": 5,
                "rows_visible": 0,
                "rows_hidden_by_department": 5,
                "account_department": "sales",
            }
        )

        assert reason == ""


class TestLegacyOpenDepartmentScope:
    """灰度回退档：放宽是事实，被别的部门藏掉的那些行仍然要说清楚，并标出这是回退档。"""

    def _legacy(self, monkeypatch):
        monkeypatch.setenv(rbac.ROW_DEPARTMENT_SCOPE_ENV, rbac.ROW_DEPARTMENT_SCOPE_LEGACY)

    def test_it_names_hidden_foreign_rows_and_marks_the_fallback(self, tmp_path, monkeypatch):
        self._legacy(monkeypatch)
        _files(monkeypatch, tmp_path, ("sales.csv", FOREIGN_ONLY_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "属于其他部门" in answer, answer
        assert "1 行" in answer, answer
        assert "放宽档" in answer, answer

    def test_it_keeps_blank_department_rows_visible(self, tmp_path, monkeypatch):
        """回退档下空部门行是可见的 ⇒ 根本不该出现「没有可见数据行」这类断言。"""
        self._legacy(monkeypatch)
        _files(monkeypatch, tmp_path, ("sales.csv", BLANK_ONLY_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "当前账号没有可见数据行" not in answer, answer
        assert "未标注部门" not in answer, answer

    def test_fail_closed_is_the_default_and_a_typo_does_not_widen_it(self, tmp_path, monkeypatch):
        """拼错的开关值不许顺带放宽：与 fail_closed 同义，空部门行仍不可见、仍报未标注部门。"""
        monkeypatch.setenv(rbac.ROW_DEPARTMENT_SCOPE_ENV, "legacyy")
        _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))

        answer = _analyze_data("金额合计", _config(role="staff", department="sales"))

        assert "未标注部门" in answer, answer
        assert "放宽档" not in answer, answer
