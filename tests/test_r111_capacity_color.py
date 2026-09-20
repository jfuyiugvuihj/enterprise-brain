"""R111 ·「容量不够」与「模型坏了」在证据面分色（跟进单 §50 立案，§56 补齐判据）。

缺陷：``app/agents/evidence.py`` 的 ``_terminal_status`` 原来那一支
``if "model_unavailable" in names or "rate_limited" in codes:`` 无条件返回
``("model_unavailable", "model_unavailable")``，把边界真报的容量码折成了「模型坏了」。
后果不是性能，是说真话：``frontend/src/lib/errcodes.js:57`` 给 ``rate_limited`` 写的那句
「操作太频繁了，请稍等一会儿再试。」在这套代码里永远不可能被客户看到。

裁定（§56.a/b 已定死，本单不另起炉灶）：``AgentResult.status`` 八枚 Literal 一枚不新增
（``app/agents/contracts.py:339``，加取值要走 D 项），``contracts.py`` 本单一个字都不改；
走法是 status 照旧 ``model_unavailable``、只让 ``error_code`` 分色
⇒ ``("model_unavailable", "rate_limited")``。

两处优先级钉子（§56.b）：越权那一支仍在最前 ——「没权限」永远盖过「容量不够」；两枚同时在场
取 ``model_unavailable`` —— 真坏了优先于容量紧，而这正是 ``app/agents/nodes.py`` 两条容量路径
（``:371`` 之后紧跟 ``:302`` 的离线兜底、``:496`` 之后紧跟 ``:503``）今天的实际形状，
那两轮的颜色本单一格都不动。

全程离线：只喂证据袋、直调 ``_terminal_status`` / ``build_agent_result`` /
``aggregate_agent_result`` 三个纯函数，不打模型、不起服务、不连数据库。
"""
from typing import get_args

from app.agents import evidence
from app.agents.contracts import AgentResult, ErrorEnvelope
from app.agents.evidence import (
    aggregate_agent_result,
    build_agent_result,
    new_evidence_bag,
    record_document_hits,
    record_model_status,
    record_tool_status,
)

WORKER = "doc"
REQUEST_ID = "req-r111"
#: 判据 d② 要的「真业务结论」：有数、有口径、有因果，不是任何一枚离线罐头句。
BUSINESS_ANSWER = "2024 年三季度毛利率 38.2%，环比提升 1.4 个百分点，主因原材料单价回落。"
#: 抄自真源 app/common/model_handler.py:63 的模型不可用罐头句，只作为判据 d③ 的输入形状。
MODEL_UNAVAILABLE_ANSWER = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"


def _bag(*, documents: bool = False, model: list[tuple[str, str]] = (), tool: list[tuple[str, str]] = ()):
    """按边界真实的形状装袋：走 record_* 三件套，不手抄 dict 字面量。"""
    bag = new_evidence_bag()
    if documents:
        record_document_hits(
            bag,
            query="三季度毛利率",
            hits=[
                {
                    "source": "2024Q3财务报告.docx",
                    "chunk_index": 3,
                    "content": "三季度毛利率 38.2%，环比提升 1.4 个百分点。",
                    "_score": 0.82,
                }
            ],
        )
    for status, code in tool:
        record_tool_status(bag, tool="search_docs", status=status, error_code=code)
    for status, code in model:
        record_model_status(bag, status, code)
    return bag


def _result(bag, answer: str = BUSINESS_ANSWER) -> AgentResult:
    return build_agent_result(worker=WORKER, answer=answer, bag=bag, request_id=REQUEST_ID)


# ==================== 判据 d：四枚输入输出组合 ====================


def test_only_a_capacity_refusal_colors_the_error_code_as_rate_limited():
    """判据 d①：袋里只有一枚 rate_limited ⇒ code=rate_limited。

    本单唯一的行为变化。§56.e 的反证就是把 :254 改回折叠写法 —— 这一枚当场红。
    """
    bag = _bag(model=[("rate_limited", "rate_limited")])

    assert evidence._terminal_status(bag, BUSINESS_ANSWER) == ("model_unavailable", "rate_limited")

    result = _result(bag)
    assert result.status == "model_unavailable"
    assert result.error is not None
    assert result.error.code == "rate_limited"
    # 词表闸（§56 前提 2）：rate_limited 本来就是 ErrorEnvelope.code 的合法成员，
    # 不会在 evidence.py:307 那行 ``if error_code in _ERROR_CODES`` 被降级成 internal_error。
    assert result.error.code in get_args(ErrorEnvelope.model_fields["code"].annotation)
    assert result.error.code in evidence._ERROR_CODES
    # 分色之后重试语义一格没变：两枚都写在 evidence.py:18 的 _RETRIABLE_CODES 里。
    assert result.error.retryable is True


def test_a_real_business_conclusion_does_not_wash_out_the_capacity_code():
    """判据 d②：rate_limited + 一枚 completed + 正文是真业务结论 ⇒ 仍 code=rate_limited。

    对照组先钉住「这袋料本来就是一枚 success」，否则这条断言只是在一件本来就不会成功的事上
    证明不会成功 —— 那是装饰，不是闸。
    """
    washed = _bag(documents=True, model=[("completed", "")])
    assert evidence._terminal_status(washed, BUSINESS_ANSWER) == ("success", ""), "对照组必须是一枚真成功"

    bag = _bag(documents=True, model=[("completed", ""), ("rate_limited", "rate_limited")])

    assert evidence._terminal_status(bag, BUSINESS_ANSWER) == ("model_unavailable", "rate_limited")

    result = _result(bag)
    assert result.status == "model_unavailable"
    assert result.error is not None
    assert result.error.code == "rate_limited", "成功不许把容量码洗掉"
    assert result.answer == BUSINESS_ANSWER, "分色只改码，不改正文：结论照旧交付"
    assert len(result.evidence) == 1


def test_a_broken_model_reports_both_halves_word_for_word():
    """判据 d③：只有 model_unavailable ⇒ 逐字不变（status 与 code 都是 model_unavailable）。"""
    bag = _bag(model=[("model_unavailable", "model_unavailable")])

    assert evidence._terminal_status(bag, MODEL_UNAVAILABLE_ANSWER) == (
        "model_unavailable",
        "model_unavailable",
    )

    result = _result(bag, answer=MODEL_UNAVAILABLE_ANSWER)
    assert result.status == "model_unavailable"
    assert result.error is not None
    assert (result.error.code, result.error.retryable) == ("model_unavailable", True)
    assert result.error.message == "doc worker finished with status=model_unavailable"
    assert result.error.details == {"worker": "doc", "status": "model_unavailable"}
    assert result.warnings == ["执行边界报告了失败状态：model_unavailable"]


def test_a_broken_model_outranks_a_tight_capacity_budget():
    """判据 d④ + 判据 b：两枚同时在场 ⇒ 取 model_unavailable（真坏了优先于容量紧）。

    这不是假想袋：nodes.py 的容量路径就是「先记 rate_limited、紧接着离线兜底记
    model_unavailable」（:371→:302、:496→:503），所以这两轮交付的颜色本单不动。
    """
    bag = _bag(model=[("rate_limited", "rate_limited"), ("model_unavailable", "model_unavailable")])

    assert evidence._terminal_status(bag, BUSINESS_ANSWER) == ("model_unavailable", "model_unavailable")

    result = _result(bag)
    assert (result.status, result.error.code) == ("model_unavailable", "model_unavailable")


# ==================== 判据 b：越权仍盖过容量 ====================


def test_no_permission_still_outranks_not_enough_capacity():
    """判据 b：「没权限」永远盖过「容量不够」——越权那一支必须留在分色之前。"""
    bag = _bag(
        tool=[("rejected", "permission_denied")],
        model=[("rate_limited", "rate_limited")],
    )

    assert evidence._terminal_status(bag, BUSINESS_ANSWER) == ("rejected", "permission_denied")

    result = _result(bag)
    assert (result.status, result.error.code, result.error.retryable) == (
        "rejected",
        "permission_denied",
        False,
    )


# ==================== 判据 c：头（告警句随 code 自动变） ====================


def test_the_alarm_sentence_carries_the_capacity_code_without_a_second_fold():
    """判据 c：evidence.py:296 那句告警随 code 自动变，不许为它单独再折一次。

    这条钉的是「没有第二处折叠」：告警句子、ErrorEnvelope.code、details.status 三处同源，
    只有 code 分色，status 那一半照旧 model_unavailable。
    """
    result = _result(_bag(model=[("rate_limited", "rate_limited")]))

    assert result.warnings == ["执行边界报告了失败状态：rate_limited"]
    assert result.error is not None
    assert result.error.code == "rate_limited"
    assert result.error.details == {"worker": "doc", "status": "model_unavailable"}
    assert result.error.message == "doc worker finished with status=model_unavailable"


# ==================== 判据 c：尾（orchestrator 聚合不许把颜色折回去） ====================


def test_the_orchestrator_tail_keeps_the_capacity_color():
    """判据 c 的尾巴：``aggregate_agent_result`` 拿子记录的 error 优先，rate_limited 一路到顶。

    :407 那行 ``error_code = {...}.get(status, status)`` 是同一段逻辑的尾巴 —— 它只给「子记录
    没带 error」兜底。若它反过来覆盖子记录，客户在编排层看到的仍是折叠前的那一枚码，本单等于没做。
    """
    child = _result(_bag(model=[("rate_limited", "rate_limited")]))

    merged = aggregate_agent_result({"doc": child}, answer=BUSINESS_ANSWER, request_id=REQUEST_ID)

    assert merged.status == "model_unavailable"
    assert merged.error is not None
    assert merged.error.code == "rate_limited"
    assert merged.error.retryable is True
    assert merged.warnings == ["doc: 执行边界报告了失败状态：rate_limited"]


def test_the_orchestrator_tail_invents_no_color_it_was_not_given():
    """反向钉：子记录压根没带 error 时，尾巴仍按 status 兜底成 model_unavailable，不许凭空发明容量码。"""
    merged = aggregate_agent_result(
        {"doc": {"worker": "doc", "status": "model_unavailable", "answer": MODEL_UNAVAILABLE_ANSWER}},
        answer=MODEL_UNAVAILABLE_ANSWER,
        request_id=REQUEST_ID,
    )

    assert merged.status == "model_unavailable"
    assert merged.error is not None
    assert merged.error.code == "model_unavailable"


# ==================== 判据 a：分色走 error_code，不给 status 加第九枚取值 ====================


def test_the_status_enum_gained_no_ninth_member_for_capacity():
    """判据 a 的反向钉：八枚 Literal 一枚不许新增，contracts.py 本单不许改。

    哪天有人想「正确地」加一枚 ``rate_limited`` status，这条会红着提醒他：那要走 D 项。
    """
    assert get_args(AgentResult.model_fields["status"].annotation) == (
        "success",
        "partial",
        "failed",
        "rejected",
        "timeout",
        "cancelled",
        "model_unavailable",
        "retrieval_unavailable",
    )