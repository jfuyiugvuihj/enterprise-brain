"""R49 判据①：索引排除规则本体。

规则只读正文特征，不读文件名：文件名写着"草稿""模板"既不构成排除理由，也不构成放行理由。
真实语料的零误伤核对与余量复算在 tests/test_r49_corpus_calibration.py。
"""
import inspect
import re

import pytest

from app.documents import index_policy
from app.documents.index_policy import (
    INDEX_STATUSES,
    INDEX_STATUS_EXCLUDED,
    INDEX_STATUS_INDEXED,
    INDEX_STATUS_UNKNOWN,
    MIN_CONTENT_CHARS_DEFAULT,
    POLICY_REASONS,
    REASON_INDEX_REFUSED,
    REASON_NO_TEXT,
    REASON_OUTLINE_SHELL,
    REASON_PLACEHOLDER_SKELETON,
    REASON_TOO_SMALL,
    REASON_UNCHANGED_CONTENT,
    TRACEABLE_REASONS,
    classify_index_refusal,
    droppable_upload,
    evaluate_index_eligibility,
    index_notice,
    min_content_chars,
    substantive_chars,
)

CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# 正文完整、但通篇写着"草案/请勿作为正式文件使用"的制度文件。documents/ 里就有这样一篇
# （客户数据保护政策_草稿.txt），任何按文件名或按"草稿"字样下的排除规则都会把它挡在门外。
FULL_DRAFT_POLICY = """# 客户数据保护政策（草案）

**版本号：** V0.1（草案）
**状态：** 法务审核中，请勿作为正式文件使用。正式版以法务部发布为准。

## 1. 目的与适用范围

为保护客户隐私与数据安全，明确公司在客户数据处理过程中的合规要求，特制定本政策。
本政策适用于公司全体员工及所有涉及客户数据处理的相关业务环节。

## 2. 数据收集告知

在收集客户数据时，必须通过隐私政策弹窗等方式明确告知收集目的、范围与使用方式，
获得客户明确勾选同意后方可进行数据收集；未经客户同意，不得擅自收集或使用其数据。

## 3. 数据处理限制

客户数据仅可用于合同履行所需的范围，严禁超范围使用，禁止用于营销或其他非合同目的。
"""

BLANK_FORM = """报销申请单（模板）

报销人：【请填写】
部门：【请填写】
报销日期：[日期]
金额合计：__________
附件张数：【待补充】
审批意见：{{ 此处填写 }}
"""

#: 同一张表单写长一点：语料最短正文也有 173 个实质字符，一条"因为太短所以排除"的规则
#: 不该在这种长度上说话。它仍然必须被占位符判据抓住，否则就是尺寸规则冒充了模板规则。
LONG_BLANK_FORM = """费用报销审批单（模板）

报销人：【请填写】 部门：【请填写】 岗位：【请填写】
报销日期：[日期] 费用期间：【请填写】 单据编号：{{ 编号 }}
出发地：__________ 目的地：__________ 交通方式：【请填写】 行程天数：【请填写】
住宿天数：【请填写】 住宿金额：__________ 餐费金额：__________ 市内交通费：__________
事由说明：【请填写】 项目名称：【请填写】 客户名称：【请填写】 合同编号：【请填写】
附件张数：【请填写】 收款账户：【请填写】 开户银行：【请填写】
"""

HEADING_SHELL = """# 第一章 总则

# 第二章 适用范围

# 第三章 职责分工

# 第四章 管理要求

# 第五章 附则
"""

# 这两篇的形状就是本轮另有线在往 documents/ 里加的《指标口径登记表》《报销明细表》：
# 一行一条、行里有冒号或有空白分栏，绝不允许被"草稿骨架"判据吃掉。
NUMBERED_REGISTRY = """指标口径登记表

1. 营业收入：不含税已确认收入，确认时点为发货签收
2. 毛利率：毛利除以营业收入，按季度累计口径
3. 回款率：实收金额除以开票金额
4. 人均产值：营业收入除以平均在职人数
5. 费用率：期间费用除以营业收入，不含折旧
"""

EXPENSE_TABLE = """报销明细表

| 日期 | 报销人 | 事由 | 金额 |
|---|---|---|---|
| 2026-03-02 | 张三 | 客户拜访差旅 | 1280.00 |
| 2026-03-05 | 李四 | 展会物料制作 | 460.00 |
| 2026-03-11 | 王五 | 客户端软件许可 | 3600.00 |
"""


def test_a_complete_document_that_admits_being_a_draft_is_eligible():
    eligibility = evaluate_index_eligibility(FULL_DRAFT_POLICY)

    assert eligibility.eligible is True
    assert eligibility.excluded is False
    assert eligibility.reason == ""
    assert eligibility.metrics["content_chars"] > index_policy.OUTLINE_MAX_CONTENT_CHARS


@pytest.mark.parametrize(
    "content",
    ["", "   \n\t ", "。——，！！\n……\n", "***\n---\n", "\u3000\u3000"],
)
def test_a_body_without_a_single_substantive_character_is_excluded(content):
    eligibility = evaluate_index_eligibility(content)

    assert eligibility.eligible is False
    assert eligibility.reason == REASON_NO_TEXT
    assert substantive_chars(content) == 0


def test_a_body_below_the_floor_is_excluded_as_too_small():
    eligibility = evaluate_index_eligibility("同意。")

    assert eligibility.reason == REASON_TOO_SMALL
    assert eligibility.metrics["content_chars"] == 2
    assert eligibility.metrics["min_content_chars"] == MIN_CONTENT_CHARS_DEFAULT


def test_a_body_exactly_at_the_floor_is_still_indexed():
    """下限是"少于"而不是"少于等于"：现存上传契约里 4 个字符的正文必须照常入索引。"""
    assert substantive_chars("同意报销") == MIN_CONTENT_CHARS_DEFAULT
    assert evaluate_index_eligibility("同意报销").eligible is True


def test_the_floor_is_an_operator_knob_that_never_excludes_the_corpus(monkeypatch):
    assert min_content_chars() == MIN_CONTENT_CHARS_DEFAULT

    monkeypatch.setenv("DOCUMENT_INDEX_MIN_CHARS", "0")
    assert evaluate_index_eligibility("同意报销").eligible is True

    monkeypatch.setenv("DOCUMENT_INDEX_MIN_CHARS", "200")
    eligibility = evaluate_index_eligibility("同意报销，明细见附件。")
    assert eligibility.reason == REASON_TOO_SMALL

    # 语料最短正文 173 个实质字符：把下限调到 173 以下都不会误伤现有语料。
    monkeypatch.setenv("DOCUMENT_INDEX_MIN_CHARS", "60")
    assert evaluate_index_eligibility(FULL_DRAFT_POLICY).eligible is True


def test_an_unfilled_form_is_excluded_as_a_placeholder_skeleton():
    eligibility = evaluate_index_eligibility(BLANK_FORM)

    assert eligibility.reason == REASON_PLACEHOLDER_SKELETON
    assert eligibility.metrics["placeholder_tokens"] >= index_policy.PLACEHOLDER_MIN_TOKENS
    assert eligibility.metrics["placeholder_ratio"] >= index_policy.PLACEHOLDER_CHAR_RATIO


def test_a_placeholder_form_of_ordinary_length_is_still_excluded_as_a_template():
    """占位符判据不靠"短"吃饭：正文够长也照样要判，否则就是尺寸规则冒充模板规则。"""
    eligibility = evaluate_index_eligibility(LONG_BLANK_FORM)

    assert eligibility.metrics["content_chars"] > index_policy.OUTLINE_MAX_CONTENT_CHARS
    assert eligibility.eligible is False
    assert eligibility.reason == REASON_PLACEHOLDER_SKELETON


def test_a_heading_only_skeleton_is_excluded_as_an_outline_shell():
    eligibility = evaluate_index_eligibility(HEADING_SHELL)

    assert eligibility.reason == REASON_OUTLINE_SHELL
    assert eligibility.metrics["headings"] == 5
    assert eligibility.metrics["empty_sections"] == 5
    assert eligibility.metrics["empty_section_ratio"] == 1.0


@pytest.mark.parametrize(
    "content",
    [NUMBERED_REGISTRY, EXPENSE_TABLE, FULL_DRAFT_POLICY],
    ids=["numbered-registry", "markdown-table", "draft-policy"],
)
def test_a_registry_or_table_body_is_never_read_as_a_skeleton(content):
    eligibility = evaluate_index_eligibility(content)

    assert eligibility.eligible is True, eligibility.message
    assert eligibility.metrics["content_chars"] > 0


def test_a_bold_label_line_does_not_become_an_empty_section():
    content = "**注意：** 本表每月 5 日前由财务部汇总后提交总经理办公会审议。\n\n**填报说明：** 金额一律保留两位小数，币种为人民币。\n"

    assert evaluate_index_eligibility(content).eligible is True


def test_every_policy_reason_is_a_stable_ascii_code_with_its_own_notice():
    assert len(set(POLICY_REASONS)) == len(POLICY_REASONS)
    assert set(POLICY_REASONS) <= set(TRACEABLE_REASONS)
    fallback = index_notice("something_else")

    for reason in TRACEABLE_REASONS:
        assert CODE_RE.match(reason), reason
        notice = index_notice(reason, {"content_chars": 3, "min_content_chars": 4})
        assert notice.endswith("。"), reason
        assert notice != fallback, reason


def test_a_notice_quotes_the_measured_numbers_it_decided_on():
    notice = index_notice(REASON_TOO_SMALL, {"content_chars": 3, "min_content_chars": 80})

    assert "3" in notice and "80" in notice
    assert index_notice(REASON_PLACEHOLDER_SKELETON, {"placeholder_tokens": 6, "placeholder_ratio": 0.52})


def test_index_status_is_a_three_valued_field_of_its_own():
    assert INDEX_STATUSES == (INDEX_STATUS_INDEXED, INDEX_STATUS_EXCLUDED, INDEX_STATUS_UNKNOWN)


def test_a_refusal_the_rules_do_not_know_about_falls_back_to_a_stable_code():
    assert classify_index_refusal("文件内容未变化，已跳过") == REASON_UNCHANGED_CONTENT
    assert classify_index_refusal("文档内容为空") == REASON_NO_TEXT
    assert classify_index_refusal("向量库这一版不收") == REASON_INDEX_REFUSED
    assert classify_index_refusal("") == REASON_INDEX_REFUSED


def test_only_an_unchanged_duplicate_is_allowed_to_lose_its_physical_copy():
    assert droppable_upload(REASON_UNCHANGED_CONTENT) is True
    for reason in TRACEABLE_REASONS:
        if reason != REASON_UNCHANGED_CONTENT:
            assert droppable_upload(reason) is False, reason


def test_an_eligible_upload_still_reports_the_measured_features():
    metrics = evaluate_index_eligibility(EXPENSE_TABLE, size_bytes=2048).metrics

    for key in ("raw_chars", "content_chars", "min_content_chars", "placeholder_ratio", "headings"):
        assert key in metrics
    assert metrics["size_bytes"] == 2048


def test_no_rule_asks_the_filename_or_matches_a_keyword_list():
    """反证锚点：将来谁想按文件名或"草稿/模板"字样下判据，这个用例先变红。"""
    assert "filename" not in inspect.getsource(evaluate_index_eligibility)
    assert "basename" not in inspect.getsource(index_policy)

    pattern_text = "".join(
        [pattern.pattern for pattern in index_policy._PLACEHOLDER_PATTERNS]
        + [pattern.pattern for pattern in index_policy._TITLE_HEADING_PATTERNS]
        + [index_policy._ATX_HEADING_RE.pattern, index_policy._TITLE_PUNCTUATION_RE.pattern]
    )
    for keyword in ("草稿", "模板", "试行", "临时", "初稿"):
        assert keyword not in pattern_text, keyword


def test_the_skeleton_rule_gives_up_entirely_on_a_long_document():
    """正文一长就放弃"草稿骨架"判据：宁可漏排除，也不误伤只写了标题式目录的资料。"""
    shell = HEADING_SHELL + "\n".join(
        f"第 {number} 条 本条用以说明公司报销流程中对应环节的责任部门与审批时限要求。"
        for number in range(1, 20)
    )

    assert substantive_chars(shell) >= index_policy.OUTLINE_MAX_CONTENT_CHARS
    assert evaluate_index_eligibility(shell).eligible is True
