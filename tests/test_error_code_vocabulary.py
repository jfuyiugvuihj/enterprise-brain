"""错误码词汇表：谁有权定义一个码、以及码表只许有一份。

三件事各自都有代价，所以各自都要一条测试：
- 线上真的在吐、而封闭枚举里没有的码名（追认）；
- 枚举追认之后仍然要封闭（放宽输入不许变成开洞）；
- ``app/agents/evidence.py`` 那份手抄码表必须与枚举同源（历史上它比枚举少一码，
  于是证据边界把一个真码悄悄降级成了 ``internal_error``）。

# 第三件事之外还有两张登记表，分工是一句话：
# - ``DEFERRED_CODES``：一个还没有 emit 点的码，不许先进枚举；
# - ``BARE_CODES_OUTSIDE_THE_ENUM``（R142）：一个正在吐、但按裁定留在封闭枚举外的裸码，
#   必须有人记账。两张表都不能只是注释，否则下一个人只会看见「这里缺一枚码」，
#   看不见它为什么缺，更看不见「新增一枚裸码」原本需要谁签字。
"""

from pathlib import Path
from typing import Literal, get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.agents import evidence
from app.agents.contracts import ErrorEnvelope

# 追认清单：每个码都必须有 app/** 下的真实出处，测试不许发明码名。
RATIFIED = {
    "invalid_filename": "app/api/v1/data.py",
    "dataset_filename_conflict": "app/api/v1/data.py",
    "dataset_preview_failed": "app/api/v1/data.py",
    "unsupported_chart_type": "app/api/v1/data.py",
    "chart_generation_failed": "app/api/v1/data.py",
    "unsupported_export_format": "app/api/v1/data.py",
    # 常量 OWNER_SCOPE_REQUIRED 的值，经 detail=OWNER_SCOPE_REQUIRED 出现在 403 上。
    "department_scope_required": "app/api/v1/data.py",
    # canonical request.failed.data.error_code。
    "no_answer_produced": "app/api/v1/chat.py",
    # R30: app/common/model_budget.py 在发请求前拦下装不下的提示词，这是它的稳定码出处。
    "context_limit_exceeded": "app/common/model_budget.py",
    # R64：数据工具的两枚行级终态码。emit 点在 app/agents/tools.py 的行级码层
    # （_ROW_SCOPE_PUBLIC_CODES / _record_denial）；逐文件的因由仍归 R62 的文案层，
    # 那一层一个字都没改，本单只是给它旁边补了一条机器读得懂的路。
    "row_scope_denied": "app/agents/tools.py",
    "no_visible_rows": "app/agents/tools.py",
    # R32：/ask 的非法档位（AskRequest.lane 写了四值之外的字符串）吐的码。**不是新造码名**：
    # validation_error 早在这张表之外就被枚举追认（app/agents/contracts.py），observability /
    # intelligence / open_platform 三条 400 一直用它，本单只是给 chat.py 补上第一个 emit 点
    # （_require_valid_lane）。为什么不新造 invalid_lane：frontend/src/lib/errcodes.test.js 的「前端键集合恰好等于真源枚举」那枚用例
    # 拿 git ref codex/data-file-catalog 的枚举比对前端键集合——枚举行里多一枚而前端少一枚，
    # 执行层无法 commit 的那一半就会当场红。
    "validation_error": "app/api/v1/chat.py",
}

# ==================== 登记：还没资格进枚举的码（R64 判据①的改判面） ====================
# 「密级拦截」那一枚码 R64 **不建**，理由有两条，两条都得有人钉着：
# 1) 今天没有任何 emit 点 —— 行级判定的唯一出处 app/common/rbac.py 不判密级（密级维度沿用
#    旧实现），``Principal.max_clearance`` 全仓只存不用（见台账 R78①）；
# 2) 业主尚未裁口径（H13）。
# 硬加进封闭枚举只有两种下场：被 test_no_ratified_code_is_invented 判红，或者逼出一个人造
# emit 点去哄测试 —— 后者是本项目最重的一种作弊。等 H13 裁完、app/** 里真出现吐这个码的
# 那一行，再把它从这张表移进 RATIFIED 并按裁定评审；这张表就是「移进来之前先有出处」的门。
DEFERRED_CODES = {
    "classification_blocked": "H13（密级口径未裁）+ R78①（max_clearance 只存不用）",
}

# ==================== 登记：有 emit 点、但按裁定不进枚举的裸码（R142 立的账） ====================
# 与上面 DEFERRED_CODES 的分工是一句话：那张表记「**还没有** emit 点」的码，这张表记
# 「**正在吐**、但按裁定留在封闭枚举之外」的码。两张表都不能只是注释，所以两边的牙齿各自存在：
#   - DEFERRED_CODES -> test_a_deferred_code_stays_out_of_the_enum_until_it_has_an_emit_point
#   - 本表 -> tests/test_r142_error_code_table_sync.py（扫描器、出处、前端归一，三头都钉）
# 每枚条目三个必填字段：emitter（``app/**.py::函数名`` 位锚；位锚指位置，本仓不写裸行号）、
# folds_into（frontend/src/lib/errcodes.js::LEGACY_ALIASES 把它归一到的枚举码）、why（为什么留在枚举外）。
# 为什么这族码不能"顺手并进枚举"：并一枚枚举就要补一枚前端键（frontend/src/lib/errcodes.test.js
# 双向钉着键集合相等），而契约对它们的裁定是**故意不追认**——R103/R106 明写"合并会让运维修错的那一个"。
# 但"故意留在外面"和"没人记账"是两件事：R142 之前这 17 枚里连一枚都没有后端侧的登记，
# 于是新增一枚裸码不需要任何人签字。这张表就是那道签字的格子。
BARE_CODES_OUTSIDE_THE_ENUM = {
    # ---- 上传 / 预览这条腿的 5 枚（chat.py 的既有响应形状） ----
    "upload_too_large": {
        "emitter": "app/api/v1/chat.py::upload_document",
        "folds_into": "unsupported_file",
        "why": "413 说的是「太大」，枚举里的 unsupported_file 说的是「类型不支持」；"
               "R89 那批追认只收 data.py 的 7 枚加 no_answer_produced，把这道尺寸闸收进枚举要连 413 的语义一起重评。",
    },
    "document_parse_failed": {
        "emitter": "app/api/v1/chat.py::upload_document",
        "folds_into": "parse_failed",
        "why": "与枚举里的 parse_failed 同义不同名，是上传链路早于枚举的形状；服务端就地改名会改响应体。",
    },
    "document_index_failed": {
        "emitter": "app/api/v1/chat.py::upload_document",
        "folds_into": "index_publish_failed",
        "why": "同上：对位码已在枚举里，但这条响应形状早于它，改名是契约变更而不是卫生作业。",
    },
    "document_preview_failed": {
        "emitter": "app/api/v1/chat.py::get_document_preview",
        "folds_into": "internal_error",
        "why": "预览读不出文件时的 500 兜底，枚举里没有「预览」这一格的码；折到 internal_error 已经是将就，"
               "但把它升成枚举码等于新开一格语义，得按契约变更评。",
    },
    "unsupported_preview": {
        "emitter": "app/api/v1/chat.py::get_document_preview",
        "folds_into": "unsupported_file",
        "why": "415 只说「这种类型不能在线预览」，与「这种类型不能入库」是两件事；混成一格会把客户端送去"
               "重传一个永远不支持预览的文件。",
    },
    # ---- R142 本单裁的那枚 ----
    "idempotency_key_required": {
        "emitter": "app/api/v1/chat.py::_enqueue_ask_turn",
        "folds_into": "validation_error",
        "ruling": "R142 裁定：留在账里，既不并进枚举，也不在服务端改名。",
        "why": "它是后台轮次的入参闸：400 加裸串，契约 /ask 状态表已按端点登记它，"
               "tests/test_r37_report_lane_enqueue.py 逐字钉着这个字符串。并进枚举要同时补前端键"
               "（frontend/** 本单禁碰）；服务端折叠成 validation_error 会改响应体——那是契约变更，"
               "本单只具名回报，不顺手做。",
    },
    # ---- 导出腿 ----
    "export_failed": {
        "emitter": "app/api/v1/data.py::export_report",
        "folds_into": "internal_error",
        "why": "导出没跑完时的 500。语义确实被 internal_error 吃掉了半截，但它对的是「导出」这一格，"
               "而枚举里那一格叫 unsupported_export_format（说的是格式不支持，不是跑挂了）。",
    },
    # ---- 存储 / 未配置这一对：R103 与 R106 明写"拒绝追认" ----
    "storage_read_only": {
        "emitter": "app/knowledge_graph/service.py::<module>",
        "also_emitted_by": ["app/common/open_platform.py::<module>"],
        "folds_into": "internal_error",
        "why": "「存储配好了、这一笔写不进去」。契约明写不与 schema 缺失、不与「这台机器根本没开这个功能」"
               "合并，因为运维会去修错的那一个。",
    },
    "knowledge_graph_unconfigured": {
        "emitter": "app/knowledge_graph/service.py::<module>",
        "folds_into": "storage_unavailable",
        "why": "「这台服务器压根没开关系存储」。409 而不是 503 是承重的：客户端重试配置不出一个功能，"
               "报成 503 就是把运维还没做的决定算成停机。",
    },
    "open_platform_unconfigured": {
        "emitter": "app/common/open_platform.py::<module>",
        "folds_into": "storage_unavailable",
        "why": "R106 把图谱那处分家搬到开放平台的应用登记上，理由与上一条同构。",
    },
    # ---- /intelligence 这条腿 ----
    "relation_source_required": {
        "emitter": "app/api/v1/intelligence.py::add_relation",
        "also_emitted_by": ["app/knowledge_graph/service.py::add_relation"],
        "folds_into": "validation_error",
        "why": "「起始对象没选」是这一格特有的下一步；折进 validation_error 之后句子还能说，"
               "但把码名一起折掉会让排查丢掉落点，改名是契约变更。",
    },
    "invalid_agent_result": {
        "emitter": "app/api/v1/intelligence.py::provenance_summary",
        "folds_into": "internal_error",
        "why": "调用方递进来的 AgentResult 过不了校验：那是**输入面**的 400，今天却折在 internal_error 这个"
               "内部码上——本身就已经是将就，翻案要按契约变更走。",
    },
    # ---- app/common/policy.py 的拒绝原因族：raise 处连字面量都没有 ----
    "principal_inactive": {
        "emitter": "app/common/policy.py::authorization_decision",
        "also_emitted_by": ["app/api/v1/observability.py::_require_admin", "app/agents/tools.py::<module>"],
        "folds_into": "account_unavailable",
        "why": "五枚 policy 原因码一起经 HTTPException(detail=decision.reason_code) 落地，"
               "raise 那一行抠不出字面量；它们是「按什么维度拒的」这套独立词汇，"
               "塞进传输层枚举会把「为什么被拒」和「请求哪里错了」混成一格。",
    },
    "department_scope_denied": {
        "emitter": "app/common/policy.py::authorization_decision",
        "also_emitted_by": ["app/agents/tools.py::<module>"],
        "folds_into": "permission_denied",
        "why": "同上族：部门维度那一刀。枚举里的 permission_denied 不区分维度，客户端要分维度只能读裸码。",
    },
    "clearance_insufficient": {
        "emitter": "app/common/policy.py::authorization_decision",
        "folds_into": "permission_denied",
        "why": "同上族：密级维度那一刀。H13 未裁之前它连语义边界都还是旧的（见 R78①）。",
    },
    "resource_scope_missing": {
        "emitter": "app/common/policy.py::authorization_decision",
        "folds_into": "authorization_unavailable",
        "why": "同上族：资源没登记归属，判不了而不是不该判——这层差别正是不能并进 permission_denied 的理由。",
    },
    "resource_scope_invalid": {
        "emitter": "app/common/policy.py::authorization_decision",
        "folds_into": "authorization_unavailable",
        "why": "同上族：登记值格式坏。它与上一条都是数据质量问题，不是权限决定。",
    },
}

_REPOSITORY = Path(__file__).resolve().parents[1]


def _enum_codes() -> frozenset[str]:
    return frozenset(get_args(ErrorEnvelope.model_fields["code"].annotation))


@pytest.mark.parametrize("code", sorted(RATIFIED))
def test_the_enum_ratifies_each_bare_code_the_apis_actually_emit(code):
    """成员资格，不是长度：与 `tests/test_public_contracts.py` 的
    test_the_envelope_enum_names_the_authentication_surface_codes 同口径。"""
    assert code in _enum_codes(), code
    assert ErrorEnvelope(code=code, message="live response").code == code


@pytest.mark.parametrize("code", sorted(RATIFIED))
def test_no_ratified_code_is_invented(code):
    """追认的每个码都得能在 app/** 源码里找到吐它的那个人。

    这条让上面那张出处表不是装饰：删掉某个 emit 点而忘了摘枚举，这里会响。
    """
    sources = [path for path in (_REPOSITORY / "app").rglob("*.py")]
    hits = [path.as_posix() for path in sources if code in path.read_text(encoding="utf-8")]

    assert hits, f"{code} is in the enum but nothing in app/** emits it"
    assert any(Path(RATIFIED[code]).as_posix() in hit for hit in hits), hits


def test_the_enum_is_still_closed_after_ratifying_eight_more():
    """放宽输入 Literal 不等于开洞：未登记的码名依旧过不了校验。"""
    with pytest.raises(ValidationError):
        ErrorEnvelope(code="not_a_real_code", message="invented")


def test_the_evidence_vocabulary_cannot_drift_from_the_enum():
    """两份手抄的差 == 一个真码被说成 internal_error。同源，不然就钉相等。"""
    assert evidence._ERROR_CODES == _enum_codes()

    # 上面那条相等可以是巧合地抄对，所以再钉"它是派生的"：换一个合成模型，
    # 码表要跟着变。字面量集合做不到这件事——这正是本手要消灭的形态。
    class _Synthetic(BaseModel):
        code: Literal["only_here_in_this_test", "task_timeout"]

    assert evidence._enum_error_codes(_Synthetic) == frozenset(
        {"only_here_in_this_test", "task_timeout"}
    )


def test_a_ratified_code_is_no_longer_downgraded_to_internal_error():
    """本批唯一的行为变化，故意钉死它。

    `app/agents/evidence.py` 里 `build_agent_result` 与 `aggregate_agent_result` 共用的 ``code=error_code if error_code in _ERROR_CODES else
    "internal_error"`` 之前会把 chart_generation_failed 降级——因为那份 16 码手抄里
    没有它。追认 + 同源之后，执行边界报什么码，证据袋里就留什么码。
    """
    result = evidence.build_agent_result(
        worker="chart",
        answer="图表没能生成",
        bag={"tool_statuses": [{"status": "failed", "error_code": "chart_generation_failed"}]},
        request_id="req-1",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "chart_generation_failed"
    assert result.error.retryable is False


def test_no_bare_error_code_lives_inside_a_string_literal_in_chat_py():
    """跟进单 §12.1 的机器判据：``error_code=`` 只许出现在结构化赋值处。

    钉整份 chat.py 而不是某一行：往用户看得见的文本里塞码名是一条政策，不是一个人的
    笔误，而这条政策当年是被后端自己违反过的（一处把码名前缀塞进了可读文本；R142 复核时
    这份违规枚数已经归零，所以这条用例守的是别再犯，而不是给今天的自己定罪）。
    """
    import ast

    source = (_REPOSITORY / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "error_code=" in node.value
    ]

    assert offenders == [], offenders


@pytest.mark.parametrize("code", sorted(DEFERRED_CODES))
def test_a_deferred_code_stays_out_of_the_enum_until_it_has_an_emit_point(code):
    """登记不是注释：口径没裁、出处没有，就既不许进枚举，也不许已经在吐这个码。

    两头都钉。哪天 H13 裁完、真写出了 emit 点，这条会红着提醒下一个人把码移进
    RATIFIED 并删掉这条登记，而不是让他重新查一遍"这枚码为什么不在枚举里"。
    """
    assert code not in _enum_codes(), f"{code} 的口径仍待 H13 裁定，不许先进封闭枚举"

    sources = [path for path in (_REPOSITORY / "app").rglob("*.py")]
    hits = [
        path.as_posix()
        for path in sources
        if code in path.read_text(encoding="utf-8")
    ]

    assert hits == [], f"{code} 已经有出处了：{hits}，该移进 RATIFIED 并按 H13 的裁定评审"
