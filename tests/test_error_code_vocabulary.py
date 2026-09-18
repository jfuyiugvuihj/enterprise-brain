"""错误码词汇表：谁有权定义一个码、以及码表只许有一份。

三件事各自都有代价，所以各自都要一条测试：
- 线上真的在吐、而封闭枚举里没有的码名（追认）；
- 枚举追认之后仍然要封闭（放宽输入不许变成开洞）；
- ``app/agents/evidence.py`` 那份手抄码表必须与枚举同源（历史上它比枚举少一码，
  于是证据边界把一个真码悄悄降级成了 ``internal_error``）。

第三件事之外还有一张登记表（``DEFERRED_CODES``）：一个**还没有 emit 点**的码不许先进
枚举。登记本身也要有护栏，否则下一个人只会看见「这里缺一枚码」，看不见它为什么缺。
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

_REPOSITORY = Path(__file__).resolve().parents[1]


def _enum_codes() -> frozenset[str]:
    return frozenset(get_args(ErrorEnvelope.model_fields["code"].annotation))


@pytest.mark.parametrize("code", sorted(RATIFIED))
def test_the_enum_ratifies_each_bare_code_the_apis_actually_emit(code):
    """成员资格，不是长度：与 `tests/test_public_contracts.py:94` 同口径。"""
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

    `evidence.py:309` 的 ``code=error_code if error_code in _ERROR_CODES else
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
    笔误，而这条政策目前是被后端自己违反的（`chat.py:1027`）。
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
