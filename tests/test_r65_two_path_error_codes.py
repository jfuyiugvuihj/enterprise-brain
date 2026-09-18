"""跟进单 R65：五处把码拼进人话的存量文案，改成「码 + 人话」两路一起走。

判据出处 docs/handoff/2026-09-15-backend-followup-requests.md §24 的 R65 行：
① 五处文案改为码 + 人话两路（**人话保留**，但码同时有一条结构化出口）；
② 形态沿用 R16 已定的那一条 —— `search_docs` 的「人话（error_code=码）」，不发明第二套；
③ 用例覆盖"前端拿得到码"：断言的是 AgentResult.error.code 与台账投影，不是正文正则；
④ 反证（回退成只拼字符串）由本文件的 `_codes(...)` 断言承担。

另外钉住简报里那条"合法用法一字不动"：`record_tool_status(error_code=...)` 那五条与
`span.finish(..., error_code=...)` 那三条是结构化出口本尊，不是债。

全程离线：不连库、不起服务，数据集准入用 tmp_path 上的临时 registry。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import get_args

import pytest

from app.agents import evidence, tools
from app.agents.contracts import AuthorizationDecision, ErrorEnvelope

_REPOSITORY = Path(__file__).resolve().parents[1]
_TOOLS_SOURCE = (_REPOSITORY / "app" / "agents" / "tools.py").read_text(encoding="utf-8")

# 「（error_code=X）」里允许出现的裸码名：枚举之内，或者下面这两条 R13 之前就在线上的历史码。
# authorization_required 是缺授权主体那句话用的，它由 evidence._terminal_status 折成
# permission_denied 之后才进信封，所以本来就不是枚举成员——登记在这里，不许再多一个。
LEGACY_PROSE_CODES = frozenset({"authorization_required"})

_PROSE_CODE = re.compile(r"（error_code=([a-z_]+)）")

# 允许拼出那句话格式的三处，见 test_the_sentence_shape_lives_in_the_three_known_places。
SHAPE_OWNERS = frozenset({"_denial_text", "search_docs", "_authorized_dataset_files"})

# app/common/policy.py::authorization_decision 今天可能交出来的全部拒绝 reason。
POLICY_DENY_REASONS = (
    "authentication_required",
    "principal_inactive",
    "permission_denied",
    "resource_scope_missing",
    "resource_scope_invalid",
    "clearance_insufficient",
    "department_scope_denied",
    "",
)


def _enum_codes() -> set[str]:
    return set(get_args(ErrorEnvelope.model_fields["code"].annotation))


def _config(**overrides) -> dict:
    configurable = {
        "user_id": "7",
        "username": "tester",
        "role": "staff",
        "department": "sales",
        "evidence_bag": evidence.new_evidence_bag(),
    }
    configurable.update(overrides)
    return {"configurable": configurable}


def _codes(config: dict, tool: str) -> list[str]:
    return [
        str(item["error_code"])
        for item in config["configurable"]["evidence_bag"]["tool_statuses"]
        if item.get("tool") == tool and item.get("error_code")
    ]


def _canonical(config: dict, answer: str, worker: str = "data"):
    return evidence.build_agent_result(
        worker=worker, answer=answer, bag=config["configurable"]["evidence_bag"], request_id="req-r65"
    )


def _registry(monkeypatch, tmp_path):
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(root=tmp_path, metadata_path=tmp_path / "dataset-metadata.json")
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    return registry


def _deny_with(monkeypatch, reason: str) -> None:
    monkeypatch.setattr(
        "app.common.policy.authorization_decision",
        lambda *args, **kwargs: AuthorizationDecision(
            allowed=False, reason_code=reason, policy_version="r65-probe", matched_rules=[]
        ),
    )


def _registered_selected_file(monkeypatch, tmp_path) -> str:
    from app.agents.contracts import Principal

    registry = _registry(monkeypatch, tmp_path)
    data_file = tmp_path / "finance.csv"
    data_file.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
    registry.register(
        data_file,
        principal=Principal.from_user(
            {"id": "7", "username": "tester", "role": "staff", "department": "sales"}
        ),
    )
    return "finance.csv"


# ==================== 判据①②：五处都改成两路，且格式只有一套 ====================


class _BrokenPipeline:
    """一条真的会失败的检索链：只负责抛出一个带着 code 的异常。"""

    def __init__(self, code: str):
        self.code = code

    def search_for_principal(self, query, principal, top_k=5):
        error = RuntimeError("索引发布失败")
        error.code = self.code
        raise error


def test_search_docs_carries_the_code_on_both_paths(monkeypatch):
    """:348 —— R16 已定的那一条，本单的样板：span.finish 交码，正文照旧说人话。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _BrokenPipeline("index_publish_failed"))
    config = _config()

    text = tools.search_docs.invoke({"query": "报销制度"}, config=config)

    assert text == "文档检索不可用（error_code=index_publish_failed）", text
    assert _codes(config, "search_docs") == ["index_publish_failed"]
    result = _canonical(config, text, worker="doc")
    assert result.error is not None and result.error.code in _enum_codes()


def test_a_code_the_upstream_invented_stays_inside_the_enum(monkeypatch):
    """上游异常能塞任意 code：没进枚举的名字既不许进正文，也不许进结构化出口。"""

    monkeypatch.setattr(tools, "_get_pipeline", lambda: _BrokenPipeline("rbac_branch_seven"))
    config = _config()

    text = tools.search_docs.invoke({"query": "报销制度"}, config=config)

    assert "rbac_branch_seven" not in text, text
    assert text == "文档检索不可用（error_code=retrieval_unavailable）", text
    assert _codes(config, "search_docs") == ["retrieval_unavailable"]


def test_a_selected_file_that_was_never_registered_denies_with_a_public_code(monkeypatch, tmp_path):
    """:139 —— 未找到选中的数据文件：resource_not_found 同时走两条路。"""
    _registry(monkeypatch, tmp_path)
    config = _config(data_filename="ghost.csv")

    text = tools._analyze_data("金额合计", config)

    assert text.endswith("（error_code=resource_not_found）"), text
    assert "未找到选中的数据文件：ghost.csv" in text, text
    assert _codes(config, tools._DATASET_GATE) == ["resource_not_found"]
    assert _canonical(config, text).error.code == "resource_not_found"


@pytest.mark.parametrize("reason", POLICY_DENY_REASONS)
def test_the_contract_carries_a_mapped_code_even_where_the_sentence_does_not(reason, monkeypatch, tmp_path):
    """:147 —— 两路各走各的，且只有契约那一路被收窄。

    正文沿用 policy 那句（tests/test_dataset_route_authorization.py:188 把它钉在了可见
    文案上，要改得动别人写域里的文件，已作为待裁残留登记进回执）；结构化那一路只交
    映射表翻出来的枚举码，前端与审计因此不必再正则读人话——判据⑤要防的就是这一层。
    """
    filename = _registered_selected_file(monkeypatch, tmp_path)
    _deny_with(monkeypatch, reason)
    config = _config(data_filename=filename)

    text = tools._analyze_data("金额合计", config)

    assert text == f"暂无可访问的数据文件（error_code={reason}）", text
    codes = _codes(config, tools._DATASET_GATE)
    assert codes == [tools._policy_denial_code(reason)], codes
    assert codes[0] in _enum_codes(), codes
    if reason and reason not in _enum_codes():
        assert codes[0] != reason, f"内部 reason 名 {reason} 被直接当成了公开码"


def test_an_authorization_terminal_keeps_its_sentence_and_adds_a_code():
    """:81 与 :448 —— 两句人话一个字不改（tests/test_tools.py:68 等钉着它们），旁边多一条码的路。"""
    missing_identity = _config(user_id=None, username=None)

    text = tools._analyze_data("金额合计", missing_identity)

    assert text == "暂无数据：当前请求缺少有效授权主体（error_code=authorization_required）", text
    assert _codes(missing_identity, "analyze_data") == ["authorization_required"]
    result = _canonical(missing_identity, text)
    assert result.error is not None and result.error.code in _enum_codes()
    assert result.status == "rejected"


def test_the_shared_authorization_sentence_is_used_by_every_data_entry_point():
    """:81 那句话经由四件工具吐出去时，四处都必须在旁边留一条结构化状态。"""
    config = _config(user_id=None, username=None)

    search = tools.search_docs.invoke({"query": "报销"}, config=config)
    query = tools._query_data("金额合计", config)
    chart = tools._generate_chart("bar", config, labels=["a"], values=[1])
    report = tools._export_report("标题", "[]", config)

    for text in (search, query, chart, report):
        assert "error_code=authorization_required" in text, text
    assert _codes(config, "search_docs") == ["authorization_required"]
    assert _codes(config, "query_data") == ["authorization_required"]
    assert _codes(config, "generate_chart") == ["authorization_required"]
    assert _codes(config, "export_report") == ["authorization_required"]


def test_every_user_visible_code_in_tools_py_is_enumerated_or_ratified_legacy():
    """正文里的码名要么在封闭枚举内，要么在下面这份登记里 —— 一码一登记，不许自然生长。"""
    tree = ast.parse(_TOOLS_SOURCE)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in _PROSE_CODE.findall(node.value):
                if name not in _enum_codes() and name not in LEGACY_PROSE_CODES:
                    offenders.append((node.lineno, name))

    assert offenders == [], offenders


def test_no_structured_exit_is_ever_built_from_a_raw_reason_name():
    """反证锚点（判据⑤的永久形态）：内部 reason 名只许出现在正文里，一次都不许当码用。

    哪天真要把那句文案换掉（等总控裁了残留账），这条也还在守着：换了文案不等于可以把
    ``error_code=decision.reason_code`` 再塞回结构化出口。
    """
    tree = ast.parse(_TOOLS_SOURCE)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg not in {"error_code", "code"}:
                continue
            value = keyword.value
            if isinstance(value, ast.Attribute) and value.attr == "reason_code":
                offenders.append((node.lineno, keyword.arg))

    assert offenders == [], f"结构化出口直接把内部 reason 名当公开码用了：{offenders}"


def test_the_sentence_shape_lives_in_the_three_known_places():
    """格式只有一套（判据②）：拼「人话（error_code=…）」的 f-string 只有三处，各有各的名字。

    _denial_text 是本单的两路出口，search_docs 是 R16 已定的样板，
    _authorized_dataset_files 那句是钉在别人写域既有用例上的待裁残留（见回执 §⑥）。
    冒出第四处就是发明了第二套格式；那句残留被改掉的那一天，这条会红着要求把它摘登记。
    """
    tree = ast.parse(_TOOLS_SOURCE)
    owners: dict[int, str] = {}
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(parent):
                if isinstance(inner, ast.JoinedStr):
                    shape = "".join(
                        part.value for part in inner.values if isinstance(part, ast.Constant)
                    )
                    if "（error_code=" in shape:
                        owners[id(inner)] = parent.name

    assert set(owners.values()) == SHAPE_OWNERS, sorted(owners.values())
    assert len(owners) == len(SHAPE_OWNERS), "「人话（error_code=…）」长出了登记之外的出处"


# ==================== 判据⑥：合法用法一字不动 ====================


def test_the_five_ratified_record_tool_status_denials_are_still_there():
    tree = ast.parse(_TOOLS_SOURCE)
    rejected = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "record_tool_status"
        and any(
            keyword.arg == "status"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "rejected"
            for keyword in node.keywords
        )
    ]

    assert len(rejected) == 5, [node.lineno for node in rejected]


def test_the_three_span_finish_error_code_uses_are_still_there():
    tree = ast.parse(_TOOLS_SOURCE)
    finishes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") == "finish"
        and any(keyword.arg == "error_code" for keyword in node.keywords)
    ]

    assert len(finishes) == 3, [node.lineno for node in finishes]


# ==================== 翻译层自身的封闭性（判据⑤的公开面） ====================


@pytest.mark.parametrize("reason", POLICY_DENY_REASONS)
def test_the_policy_table_covers_the_denials_it_claims_to(reason):
    code = tools._policy_denial_code(reason)

    assert code in _enum_codes(), (reason, code)


def test_the_policy_fallback_code_is_permission_denied_and_not_a_guess():
    assert tools._policy_denial_code("a_reason_invented_tomorrow") == "permission_denied"
    assert tools._policy_denial_code(None) == "permission_denied"


def test_the_policy_mapping_table_exists_exactly_once():
    offenders = [
        path.as_posix()
        for path in (_REPOSITORY / "app").rglob("*.py")
        if path.name != "tools.py" and "_POLICY_DENIAL_CODES" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], f"映射表长出了第二份：{offenders}"
