"""跟进单 R64：行级终态必须有结构化 error_code，人话不再是唯一载体。

判据出处 docs/handoff/2026-09-15-backend-followup-requests.md §24 的 R64 行，外加总控
09-18 对本单的当场改判：**密级拦截那一枚码本单不建**（密级维度今天没有任何 emit 点，
口径属 H13 未裁），登记在 tests/test_error_code_vocabulary.py::DEFERRED_CODES 旁边。

钉住六件事：
① 「行级口径拒绝」与「无可见行」两种终态各有一枚**枚举内**稳定码，且码与人话同批产出；
② 那枚码真的走到 AgentResult.error.code —— 也就是队列与审计台账实际在读的字段
   （deploy/queue_worker.py:94、app/trace/records.py:40 → summarize_agent_result）；
   把人话整段擦掉它仍然存在，就证明它不是从文案里正则出来的；
③ 逐文件的人话与整轮的码永不错位：文案说不出因由的那一支，码一律落到 no_visible_rows；
④ 公开码不等于任何 rbac 内部 reason 名（判据⑤的反证面），映射表全仓只有一份；
⑤ app/common/rbac.py 一个字都不改：判定出处仍在 rbac，本层只翻译；
⑥ R62 的资产不降级：那两句人话里仍然不许出现裸码名（tests/test_tools_row_scope_messaging.py:136
   钉过的那条，本文件用同口径再钉一次终态）。

全程离线：模型侧的 _llm_pandas_code 换成"一被调用就红"的假实现，数据集准入由 monkeypatch
钉死，不碰 storage、不连库、不起服务。
"""
from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from app.agents import evidence, tools
from app.agents.contracts import ErrorEnvelope
from app.common import rbac

_REPOSITORY = Path(__file__).resolve().parents[1]

# app/common/rbac.py 今天会交出来的全部 reason_code（rbac.py:95/163/169/173/179/181/215）。
# 本单不新增判定，所以这六个名字就是行级码层能收到的全部输入，一个都不许多。
RBAC_ROW_SCOPE_REASONS = (
    "",
    "administrator_scope",
    "department_column_missing",
    "department_scope",
    "authorization_unavailable",
    "legacy_open_department_scope",
)

HEADER = "name,department,金额\n"
MIXED_CSV = HEADER + "sales-a,sales,100\nhr-b,hr,200\nblank-c,,300\nsales-d,sales,400\n"
OWN_DEPARTMENT_CSV = HEADER + "sales-a,sales,100\nsales-d,sales,400\n"
OTHER_DEPARTMENT_CSV = HEADER + "hr-b,hr,200\nblank-c,,300\n"
FOREIGN_ONLY_CSV = HEADER + "hr-b,hr,200\n"
NO_ROWS_CSV = HEADER
# 有部门列、整帧却被另一个维度清空：部门维度一行都没藏过，本层说不出因由。
CLEARANCE_ONLY_CSV = "name,department,金额,classification\nsecret-a,sales,100,4\nsecret-b,sales,200,4\n"


def _config(role: str = "staff", department: str = "sales") -> dict:
    return {
        "configurable": {
            "user_id": "7",
            "username": "tester",
            "role": role,
            "department": department,
            "evidence_bag": evidence.new_evidence_bag(),
        }
    }


def _bag(config: dict) -> dict:
    return config["configurable"]["evidence_bag"]


def _codes(config: dict, tool: str) -> list[str]:
    """本轮这个工具真正交出去的结构化码，按记录顺序。"""
    return [
        str(item["error_code"])
        for item in _bag(config)["tool_statuses"]
        if item.get("tool") == tool and item.get("error_code")
    ]


def _canonical(config: dict, answer: str):
    return evidence.build_agent_result(
        worker="data",
        answer=answer,
        bag=_bag(config),
        request_id="req-r64",
        trace_id="trace-r64",
        task_id="task-r64",
    )


def _files(monkeypatch, tmp_path, *specs: tuple[str, str]) -> None:
    resolved = []
    for filename, body in specs:
        path = tmp_path / filename
        path.write_text(body, encoding="utf-8")
        resolved.append((filename, str(path)))
    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: (resolved, None))


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """宿主 shell 里残留的灰度开关不许参与本文件的判定；模型一律不许被叫。"""
    monkeypatch.delenv(rbac.ROW_DEPARTMENT_SCOPE_ENV, raising=False)

    def _never_call_the_model(df, query):
        raise AssertionError("_llm_pandas_code 被调用了：这条用例不该去请模型")

    monkeypatch.setattr(tools, "_llm_pandas_code", _never_call_the_model)


# ==================== 判据①：两种终态各有一枚枚举内稳定码 ====================


def test_a_table_hidden_by_the_row_scope_denies_with_a_stable_code(monkeypatch, tmp_path):
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))

    answer = tools._query_data("各部门金额合计", config)

    assert "可见范围" in answer, answer                      # 人话照旧说给人听
    assert _codes(config, "query_data") == ["row_scope_denied"]
    assert _canonical(config, answer).error.code == "row_scope_denied"


def test_a_table_without_any_row_reports_no_visible_rows(monkeypatch, tmp_path):
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", NO_ROWS_CSV))

    answer = tools._query_data("金额合计", config)

    assert "没有可分析的数据行" in answer, answer
    assert _codes(config, "query_data") == ["no_visible_rows"]
    assert _canonical(config, answer).error.code == "no_visible_rows"


def test_the_two_terminal_codes_are_two_different_enumerated_codes(monkeypatch, tmp_path):
    """判据①的字面要求：两种终态各一枚，且都在封闭枚举里。"""
    enum_codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    denied = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))
    denied_answer = tools._query_data("各部门金额合计", denied)

    empty = _config()
    _files(monkeypatch, tmp_path, ("orders.csv", NO_ROWS_CSV))
    empty_answer = tools._query_data("金额合计", empty)

    assert _codes(denied, "query_data") == ["row_scope_denied"]
    assert _codes(empty, "query_data") == ["no_visible_rows"]
    assert {"row_scope_denied", "no_visible_rows"} <= enum_codes


def test_an_account_without_a_department_is_a_row_scope_denial(monkeypatch, tmp_path):
    """rbac 把这一支记成 authorization_unavailable，公开码却是 row_scope_denied。

    判据⑤要的就是这个落差：内部 reason 名一旦当公开码用，rbac 改个词表就破坏 API 兼容。
    """
    config = _config(department="")
    _files(monkeypatch, tmp_path, ("sales.csv", MIXED_CSV))

    answer = tools._query_data("各部门金额合计", config)

    assert "没有部门归属" in answer, answer
    assert _codes(config, "query_data") == ["row_scope_denied"]
    assert "authorization_unavailable" not in _codes(config, "query_data")


def test_the_gray_fallback_scope_is_denied_too(monkeypatch, tmp_path):
    monkeypatch.setenv(rbac.ROW_DEPARTMENT_SCOPE_ENV, rbac.ROW_DEPARTMENT_SCOPE_LEGACY)
    config = _config()
    # 放宽档仍然会藏掉「属于别的部门」的那些行，那一支照样是口径拒绝。
    _files(monkeypatch, tmp_path, ("sales.csv", FOREIGN_ONLY_CSV))

    answer = tools._query_data("各部门金额合计", config)

    assert "放宽档" in answer, answer
    assert _codes(config, "query_data") == ["row_scope_denied"]


# ==================== 判据②：码不是从人话里读出来的 ====================


def test_the_code_survives_the_prose_being_deleted_entirely(monkeypatch, tmp_path):
    """把人话整段擦掉，码还在：这条就是"文案不再是唯一载体"的机器形态。"""
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))
    tools._query_data("各部门金额合计", config)

    result = _canonical(config, "")

    assert result.answer == ""
    assert result.error is not None, "文案清空之后结构化出口也消失了＝码只是文案的影子"
    assert result.error.code == "row_scope_denied"


def test_the_audit_projection_carries_the_same_code(monkeypatch, tmp_path):
    """台账读的是 summarize_agent_result 里的 error_code，不是正文正则。"""
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))
    answer = tools._query_data("各部门金额合计", config)

    summary = evidence.summarize_agent_result(_canonical(config, answer))

    assert summary["error_code"] == "row_scope_denied"
    assert summary["status"] == "failed"


def test_the_terminal_state_reaches_the_canonical_envelope(monkeypatch, tmp_path):
    """ErrorEnvelope 的 message/retryable/details 都得跟着成立，否则只是填了个字段。"""
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", NO_ROWS_CSV))
    answer = tools._query_data("金额合计", config)

    result = _canonical(config, answer)

    assert result.status == "failed"
    assert result.error.retryable is False
    assert result.error.details["status"] == "failed"


# ==================== 判据③：码与人话共用同一条判据源 ====================


@pytest.mark.parametrize("reason_code", RBAC_ROW_SCOPE_REASONS)
def test_the_code_layer_never_says_denial_when_the_prose_layer_cannot(reason_code):
    """文案空手回去的那一支，码也只能说「没有可见行」。

    这条把 R62 的诚实性规矩搬到了结构化那一路：说不出因由就不许说成权限。
    """
    info = {
        "reason_code": reason_code,
        "rows_in": 3,
        "rows_visible": 0,
        "rows_after_clearance": 3,
        "rows_hidden_by_department": 3,
        "rows_hidden_blank_department": 1,
        "rows_hidden_account_department": 0,
        "account_department": "sales",
    }

    reason = tools._row_scope_reason(info)
    code = tools._row_scope_code(info)

    assert code in set(get_args(ErrorEnvelope.model_fields["code"].annotation)), code
    assert (code == "row_scope_denied") is bool(reason), (reason_code, reason, code)
    assert code in {"row_scope_denied", "no_visible_rows"}


@pytest.mark.parametrize(
    "reason_code",
    ("department_scope", "legacy_open_department_scope"),
)
def test_a_denial_sounding_reason_still_says_nothing_when_that_dimension_hid_no_rows(reason_code):
    """reason 名叫「口径拒绝」，但部门维度一行都没藏过 ⇒ 码也只能说「没有可见行」。

    这一支是 R62 退回过的那个缺陷（把别的维度的账挂到部门列上）在结构化那一路的镜像：
    照着 reason_code 编码就会把密级维度清空的表说成权限拒绝。
    """
    info = {
        "reason_code": reason_code,
        "rows_in": 2,
        "rows_visible": 0,
        "rows_after_clearance": 0,
        "rows_hidden_by_department": 0,
        "account_department": "sales",
    }

    assert tools._row_scope_reason(info) == ""
    assert tools._row_scope_code(info) == tools._NO_VISIBLE_ROWS_CODE


def test_a_frame_cleared_by_another_dimension_is_not_reported_as_a_block(monkeypatch, tmp_path):
    """整帧被部门维度之外的东西清空：只报 no_visible_rows，不替没裁的口径下结论。"""
    config = _config()
    _files(monkeypatch, tmp_path, ("secret.csv", CLEARANCE_ONLY_CSV))

    answer = tools._query_data("金额合计", config)

    for guessed in ("属于其他部门", "未标注部门", "没有部门归属", "可见范围", "权限"):
        assert guessed not in answer, f"{guessed} 是无依据的因由：{answer}"
    assert _codes(config, "query_data") == ["no_visible_rows"]


def test_a_file_that_cannot_be_read_gets_no_row_scope_code(monkeypatch, tmp_path):
    """读都读不出来的文件不是行级口径的账：本层不编码，也不许凭空造一个失败终态。"""
    missing = tmp_path / "gone.csv"
    config = _config()
    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda cfg: ([("gone.csv", str(missing))], None))

    answer = tools._query_data("金额合计", config)

    assert "载入失败" in answer, answer
    assert _codes(config, "query_data") == []
    assert _canonical(config, answer).error is None


# ==================== analyze_data：终态只在真的什么都没产出时报 ====================


def test_analyze_data_reports_no_visible_rows_when_the_neutral_sentence_is_all_it_can_say(
    monkeypatch, tmp_path
):
    """同一张表走 analyze_data：文案只能说「没有可见数据行」，码就只能是 no_visible_rows。

    这一支不经过 _query_data 的那条短路，所以它是码/人话错位真正的反证面。
    """
    config = _config()
    _files(monkeypatch, tmp_path, ("secret.csv", CLEARANCE_ONLY_CSV))

    answer = tools._analyze_data("金额合计", config)

    assert "当前账号没有可见数据行" in answer, answer
    for guessed in ("属于其他部门", "未标注部门", "没有部门归属", "可见范围"):
        assert guessed not in answer, f"{guessed} 是无依据的因由：{answer}"
    assert _codes(config, "analyze_data") == ["no_visible_rows"]
    assert _canonical(config, answer).error.code == "no_visible_rows"


def test_analyze_data_denies_when_no_frame_reached_analysis(monkeypatch, tmp_path):
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))

    answer = tools._analyze_data("金额合计", config)

    assert "属于其他部门" in answer, answer
    assert _codes(config, "analyze_data") == ["row_scope_denied"]
    assert _canonical(config, answer).error.code == "row_scope_denied"


def test_analyze_data_reports_a_denial_over_emptiness_when_files_mixed(monkeypatch, tmp_path):
    """一张被挡、一张本来就是空表：报得出去的那条断言优先，取拒绝。"""
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV), ("empty.csv", NO_ROWS_CSV))

    answer = tools._analyze_data("金额合计", config)

    assert _codes(config, "analyze_data") == ["row_scope_denied"]
    assert "未标注部门" in answer, answer


def test_analyze_data_with_a_visible_frame_reports_no_denial(monkeypatch, tmp_path):
    """本轮确实产出了分析：不许把别的文件的行级因由升级成整轮失败。"""
    config = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV), ("own.csv", OWN_DEPARTMENT_CSV))

    answer = tools._analyze_data("金额合计", config)

    assert "2行" in answer, answer
    assert _codes(config, "analyze_data") == []
    assert _canonical(config, answer).error is None


# ==================== 判据⑤：映射表只有一份，且不泄漏内部词表 ====================


def test_the_row_scope_mapping_table_is_closed_and_public():
    enum_codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    values = set(tools._ROW_SCOPE_PUBLIC_CODES.values())

    assert values <= enum_codes, values - enum_codes
    assert not (values & set(RBAC_ROW_SCOPE_REASONS)), "rbac 的内部 reason 名不许直接当公开码"
    assert values == {"row_scope_denied"}, "映射表只该产出「口径拒绝」这一枚码，其余走兜底"
    assert set(tools._ROW_SCOPE_PUBLIC_CODES) <= set(RBAC_ROW_SCOPE_REASONS)
    assert tools._NO_VISIBLE_ROWS_CODE in enum_codes
    # 表里没登记的 reason（以及什么都没有的兜底面）只能落到「没有可见行」这一枚。
    assert tools._row_scope_code(None) == tools._NO_VISIBLE_ROWS_CODE


def test_the_row_scope_mapping_table_exists_exactly_once():
    offenders = []
    for path in (_REPOSITORY / "app").rglob("*.py"):
        if path.name == "tools.py":
            continue
        if "_ROW_SCOPE_PUBLIC_CODES" in path.read_text(encoding="utf-8"):
            offenders.append(path.as_posix())

    assert offenders == [], f"行级码的映射表长出了第二份：{offenders}"


def test_the_two_public_codes_are_not_emitted_inside_rbac():
    """判定出处一个字都不改：公开码只存在于翻译层，rbac 里不该有它们的名字。"""
    source = (_REPOSITORY / "app" / "common" / "rbac.py").read_text(encoding="utf-8")

    for code in ("row_scope_denied", "no_visible_rows"):
        assert code not in source
    assert '"reason_code"' in source                      # 内部词表还留在原处
    assert "filter_dataframe_rows_with_scope" in source


def test_the_translation_layer_adds_no_row_selection_of_its_own():
    """R62 立过的规矩，本单原样遵守：翻译层不许长出平行判定。"""
    source = (_REPOSITORY / "app" / "agents" / "tools.py").read_text(encoding="utf-8")

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


# ==================== 判据⑥：R62 的正文清洗资产不降级 ====================


def test_neither_terminal_sentence_carries_a_bare_code_name(monkeypatch, tmp_path):
    """码走结构化那一路，两句人话里连码名都不该出现（与 R62 同口径）。"""
    denied = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", OTHER_DEPARTMENT_CSV))
    denied_answer = tools._query_data("各部门金额合计", denied)

    empty = _config()
    _files(monkeypatch, tmp_path, ("sales.csv", NO_ROWS_CSV))
    empty_answer = tools._query_data("金额合计", empty)

    for answer in (denied_answer, empty_answer):
        assert "error_code" not in answer, answer
        for code in ("department_scope", "authorization_unavailable",
                     "row_scope_denied", "no_visible_rows",
                     "legacy_open_department_scope", "department_column_missing"):
            assert code not in answer, f"{code} 漏进了人话：{answer}"


# ==================== 总控验收补钉（09-18：三把砍不出红的刀的下颌）====================


def test_mixed_frames_take_the_denial_code_whatever_the_order() -> None:
    """多张表混合时「口径拒绝」压过「没有可见行」，且与文件顺序无关。

    总控的刀 M2 把这条优先级改成「取第一个码」，本文件 27 条加邻域共 122 条一声不响：
    这条规矩当时只写在注释里。补上之后，取第一个码立刻红。
    """
    assert tools._row_scope_terminal_code(["no_visible_rows", "row_scope_denied"]) == "row_scope_denied"
    assert tools._row_scope_terminal_code(["row_scope_denied", "no_visible_rows"]) == "row_scope_denied"
    assert tools._row_scope_terminal_code(["no_visible_rows"]) == "no_visible_rows"
    assert tools._row_scope_terminal_code([]) == ""


def test_an_empty_code_writes_no_status_at_all() -> None:
    """本层说不出因由就不落终态：幽灵 failed 会被队列当失败一路重试到 dead。

    总控的刀 M3 摘掉 `if not code: return` 这道护身符，122 条全绿，也就是说今天没有一条
    用例知道它在。摘掉之后「文件载入失败」「暂无数据文件」两条终态各写一条 error_code 为
    空的 failed，`_terminal_status` 再把空码洗成 internal_error：于是「本层不猜因由」被
    说成「执行边界报了内部错误」。这条钉的就是那段。
    """
    config = _config()
    before = list(_bag(config)["tool_statuses"])

    tools._record_denial(config, tool="query_data", code="")

    assert _bag(config)["tool_statuses"] == before
    result = _canonical(config, "本轮没有可分析的数据。")
    assert result.status != "failed"
    assert (result.error is None) or result.error.code != "internal_error"


@pytest.mark.parametrize(
    "reason_code",
    ("clearance_insufficient", "row_limit_reached", "some_future_reason"),
)
def test_an_unmapped_reason_cannot_borrow_the_denial_code(reason_code: str) -> None:
    """映射表之外的因由只许说「没有可见行」，不替未裁的密级维度（H13）或 rbac 改名下结论。

    总控的刀 M4 把映射表的默认值换成 row_scope_denied 时砍不出红。查因坐实：
    `_row_scope_reason` 对不认识的因由本来就返回空串，`_row_scope_code` 在查表之前已经
    短路，那个默认值是走不到的分支。真正兜住这件事的是「认不出因由就不说」这条规矩，
    所以钉的是规矩本身，不是一个走不到的分支。
    """
    info = {
        "reason_code": reason_code,
        "rows_in": 3,
        "rows_visible": 0,
        "rows_after_clearance": 3,
        "rows_hidden_by_department": 3,
        "rows_hidden_blank_department": 1,
        "rows_hidden_account_department": 0,
        "account_department": "sales",
    }

    assert tools._row_scope_reason(info) == ""
    assert tools._row_scope_code(info) == "no_visible_rows"
