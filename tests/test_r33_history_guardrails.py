"""R33 判据③④：确定性裁剪的硬护栏与"不许反向变胖"。

判据③ 的原话是"不许裁掉权限谓词与来源定位串"（跟进单 §21 表 L505），本班把它写成两条可机器验
的断言：**一条都不许多丢，一条都不许多截**。判据④ 要求裁剪后的估算 token 恒 ≤ 裁剪前，并写明
保留条数下限是多少轮、为什么。

🔴 反例文本一律从真源取，不在本文件手抄第二份：
* 权限谓词文本 —— 现调 ``app/rag/filters.py`` 的构造器，拿真 ``where`` 字典的 JSON；
* 来源定位串 —— 现调 ``app/agents/evidence.py:62`` 的 ``record_document_hits``，拿真 ``source_id``；
* 各生产方"定位串长什么样" —— 直接从源文件的字符串常量里扫出来，与 summarizer 的标记表对拍。
手抄正是 R116 那类病（把上游字面量抄进用例，上游改了用例还绿）。
"""
import ast
import json
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import contracts
from app.agents import evidence
from app.agents import orchestrator
from app.agents import tools
from app.api.v1 import chat
from app.common.model_budget import estimate_prompt_tokens
from app.memory.summarizer import (
    MIN_RECENT_MESSAGES,
    PERMISSION_MARKERS,
    TRUNCATED_BODY_CHARS,
    TRUNCATION_SUFFIX,
    carries_guardrail,
    trim_history,
)
from app.rag import filters as rag_filters

REPO = Path(__file__).resolve().parents[1]

#: 交出凭证文本的四枚真源（判据③ 正向半边逐枚点名）。
LOCATOR_PRODUCERS = (
    "app/agents/evidence.py",
    "app/agents/tools.py",
    "app/agents/orchestrator.py",
    "app/api/v1/chat.py",
)

#: "什么算一条定位串"的**形状**定义，故意不引用 summarizer 的标记表 —— 否则对拍变成自己验
#: 自己。已知边界：某天整体改拼成"出处:"这种新写法，这里扫不到字面量，只会少一处覆盖，
#: 不会假绿成"覆盖了"；写在明处比装作没有要好。
_LOCATOR_SHAPE = re.compile(r"来源\s*[:：]|#chunk=")


def _string_literals(relative: str) -> list[str]:
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _producer_name(obj) -> str:
    """工具被 ``@tool`` 包成 StructuredTool，函数名藏在 ``name`` 上，``callable()`` 也不成立。"""
    return str(getattr(obj, "name", "") or getattr(obj, "__name__", ""))


def _principal(department: str = "研发部"):
    return contracts.Principal(
        user_id="u-r33", username="staff-r33", roles=["staff"], department=department
    )


def _administrator_principal():
    return contracts.Principal(user_id="u-r33-admin", username="admin-r33", roles=["admin"])


def _permission_predicate_texts() -> list[str]:
    """真 ``where`` 文本：部门档与管理员档两条 scope，谁都不许被裁动。"""
    return [
        json.dumps(
            rag_filters.build_document_retrieval_filter(principal),
            ensure_ascii=False,
            sort_keys=True,
        )
        for principal in (_principal(), _administrator_principal())
    ]


def _source_locator_strings(count: int = 5) -> list[str]:
    """真来源定位串：走 evidence 的登记函数，不拼第二份 ``{source}#chunk=`` 字面量。"""
    bag = evidence.new_evidence_bag()
    recorded = evidence.record_document_hits(
        bag,
        query="差旅住宿标准是多少",
        hits=[
            {
                "source": "差旅制度手册.pdf",
                "chunk_index": index,
                "content": "住宿费按每人每晚 500 元计发。" * 30,
                "_score": 0.9 - index / 100,
                "classification": 2,
                "department": "研发部",
            }
            for index in range(count)
        ],
    )
    assert recorded == count, "登记函数没记账，本文件的前提就不成立"
    return [document["source_id"] for document in bag["documents"]]


def _history_with_evidence(evidence_pairs: int = 10, plain_pairs: int = 6, recent_pairs: int = 4):
    """一段真会超预算的历史，分三段，段段有用：

    * 前段：带凭证的旧轮长答 —— 判据③ 的宿主，一条不许动；
    * 中段：不带凭证的旧轮长答 —— 判据④ 的可裁对象（先截后丢）；
    * 末段：最近 ``recent_pairs`` 轮短答 —— 撑住"最近 N 条原样保留"那条下限，
      也让上面两半都稳稳落在旧区，不至于被最近窗口顺手保住而把对照变成空转。
    """
    locators = _source_locator_strings(evidence_pairs)
    predicates = _permission_predicate_texts()
    messages: list = []
    for turn in range(evidence_pairs):
        messages.append(HumanMessage(content="旧%d问：住宿费标准是多少？" % turn))
        messages.append(
            AIMessage(
                content=(
                    "旧%d答：按职级分档。检索范围 %s；引用 %s 第 %d 段。"
                    % (turn, predicates[turn % len(predicates)], locators[turn], turn)
                )
                + "正文补充说明。" * 60
            )
        )
    for turn in range(plain_pairs):
        messages.append(HumanMessage(content="旧%d问：食堂餐标是多少？" % turn))
        messages.append(
            AIMessage(content="旧%d答：按人次计发。" % turn + "详细口径见制度文件正文。" * 60)
        )
    for turn in range(recent_pairs):
        messages.append(HumanMessage(content="近%d问：上个月门店利润是多少？" % turn))
        messages.append(AIMessage(content="近%d答：三个门店合计 128 万元。" % turn))
    return messages, locators, predicates


def _contents(messages) -> str:
    return "\n".join(str(getattr(message, "content", "")) for message in messages)


def _tail(rounds: int):
    return [
        pair
        for turn in range(rounds)
        for pair in (
            HumanMessage(content="近%d问：那市内交通呢？" % turn),
            AIMessage(content="近%d答：单日上限 200 元。" % turn),
        )
    ]


# ==================== 判据③ 硬护栏：一条不许少、一条不许截 ====================

def test_the_named_producer_modules_are_still_the_ones_emitting_those_strings():
    """四枚真源仍是这些文件、生产方仍叫这个名字：改名或搬走，这条先红，别让扫描空转。"""
    for module, relative, producer, expected in (
        (evidence, "app/agents/evidence.py", evidence.record_document_hits, "record_document_hits"),
        (tools, "app/agents/tools.py", tools.search_docs, "search_docs"),
        (orchestrator, "app/agents/orchestrator.py", orchestrator._approval_worker_node, "_approval_worker_node"),
        (chat, "app/api/v1/chat.py", chat.chat, "chat"),
    ):
        assert Path(module.__file__).resolve() == (REPO / relative).resolve(), relative
        assert _producer_name(producer) == expected, "%s 的生产方不在了" % relative


def test_the_recognizer_accepts_text_the_producers_actually_emit():
    """护栏标记表认得真源交出的每一枚凭证；认不得就等于"裁掉了权限谓词/来源定位串"。"""
    samples = _permission_predicate_texts() + _source_locator_strings()
    unrecognised = [sample for sample in samples if not carries_guardrail(sample)]
    assert unrecognised == [], "这些真源文本会被裁剪动到：%r" % unrecognised


def test_every_locator_literal_in_the_producer_files_is_recognised():
    """逐枚源文件扫字符串常量：凡形状像定位串的，标记表必须覆盖（不覆盖就等着被裁）。"""
    offenders = {}
    for relative in LOCATOR_PRODUCERS:
        shaped = [lit for lit in _string_literals(relative) if _LOCATOR_SHAPE.search(lit)]
        assert shaped, "真源里扫不到定位串字面量，本用例空转：%s" % relative
        offenders[relative] = [lit for lit in shaped if not carries_guardrail(lit)]
    offenders = {name: lits for name, lits in offenders.items() if lits}
    assert offenders == {}, "这些定位串写法不在护栏标记表里：%r" % offenders


def test_the_permission_markers_are_the_operators_and_keys_the_scope_uses():
    """``PERMISSION_MARKERS`` 每一枚都得真出现在 ``where`` 文本里，不许有凑数的词。"""
    text = " ".join(_permission_predicate_texts())
    unused = [marker for marker in PERMISSION_MARKERS if marker not in text]
    assert unused == [], "这些标记在生产方交出的 where 文本里根本见不到：%r" % unused


def test_predicates_and_locators_survive_a_budget_of_one():
    """判据③ 主体：预算压到 1 token，权限谓词与来源定位串仍要一条不少、一条不截。"""
    history, locators, predicates = _history_with_evidence()
    hosts_before = {
        str(message.content) for message in history if carries_guardrail(str(message.content))
    }
    assert len(hosts_before) == 10, "带凭证的宿主消息条数不对，对照前提变了：%d" % len(hosts_before)

    trimmed = trim_history(history, budget_tokens=1)
    after = _contents(trimmed)

    missing_locators = [locator for locator in locators if locator not in after]
    assert missing_locators == [], "这些来源定位串被裁掉了：%r" % missing_locators
    missing_predicates = [text for text in predicates if text not in after]
    assert missing_predicates == [], "这些权限谓词文本被裁掉了：%r" % missing_predicates

    survivors = {
        str(message.content) for message in trimmed if carries_guardrail(str(message.content))
    }
    assert survivors == hosts_before, (
        "带凭证的消息被改过形状：少了 %r，多了 %r"
        % (hosts_before - survivors, survivors - hosts_before)
    )
    assert all(
        TRUNCATION_SUFFIX not in str(message.content)
        for message in trimmed
        if carries_guardrail(str(message.content))
    ), "凭证文本被截断了：出处就撒了谎"


def test_an_ordinary_long_answer_without_evidence_is_still_trimmed():
    """判据③ 的反向半边（也是反空转）：不带凭证的旧轮长答该截就截、该丢就丢。"""
    history, _locators, _predicates = _history_with_evidence(evidence_pairs=2, plain_pairs=8)
    plain_contents = [
        str(message.content)
        for message in history
        if "按人次计发" in str(message.content)
    ]
    assert plain_contents and not any(map(carries_guardrail, plain_contents)), (
        "无凭证题面被认成凭证，这条对照不成立"
    )

    trimmed = trim_history(history, budget_tokens=1)
    after = _contents(trimmed)
    still_whole = [text for text in plain_contents if text in after]
    assert still_whole == [], "无凭证旧长答一条都没动，裁剪就是假的：%r" % still_whole


# ==================== 判据④ 不许反向变胖 + 保留条数下限 ====================

def test_the_trim_never_grows_the_estimated_prompt():
    """判据④：四档预算全量过，裁剪后估算 token 恒 ≤ 裁剪前，数写进断言消息。"""
    history, _locators, _predicates = _history_with_evidence()
    before = estimate_prompt_tokens(history)
    for budget in (before, before - 1, before // 2, 1):
        after = estimate_prompt_tokens(trim_history(history, budget_tokens=budget))
        assert after <= before, "裁剪后反而变胖：budget=%d 时 %d → %d" % (budget, before, after)


def test_the_three_regimes_are_actually_different():
    """反空转：预算够 → 一个字不动；只差一点 → 只截不丢；几乎没有 → 才允许丢整条。

    三档分别把 ② 的"按字符截断"这条腿和"丢不带凭证长答"这条腿各自量到，缺一条就是假绿。
    """
    history, _locators, _predicates = _history_with_evidence()
    full = estimate_prompt_tokens(history)

    untouched = trim_history(history, budget_tokens=full)
    assert [m.content for m in untouched] == [m.content for m in history], "预算够就该一个字不动"

    tight = trim_history(history, budget_tokens=full - 1)
    assert len(tight) == len(history), (
        "只差一个字就该靠截断解决，不该丢条：%d → %d（full=%d）" % (len(history), len(tight), full)
    )
    cut = [m for m in tight if TRUNCATION_SUFFIX in str(m.content)]
    assert cut, "中间条一条都没截，截断这条腿没被量到"
    assert all(
        len(str(m.content)) <= TRUNCATED_BODY_CHARS + len(TRUNCATION_SUFFIX) + 4 for m in cut
    ), "截断长度不守 TRUNCATED_BODY_CHARS 口径"
    assert all(
        type(m).__name__ != "HumanMessage" for m in cut
    ), "人类问题被截了：旧轮问题要原样留在历史里"

    starved = trim_history(history, budget_tokens=1)
    assert len(starved) < len(tight), "丢弃腿没被量到：%d → %d" % (len(tight), len(starved))


def test_the_retained_floor_is_the_most_recent_four_rounds():
    """保留条数下限：最近 ``MIN_RECENT_MESSAGES`` = 8 条 = 4 个一问一答，逐字节原样。

    为什么是 8：与 R33 之前旧版 ``KEEP`` 同值。真机 run4/run5 的答案就是在"最近 8 条可见"这个
    口径上量出来的，收窄这个窗口属于"会改答案内容"的那一半（也正是原判据③ 要它与 R36 同批
    合并的理由），由总控在 run6 观察，不在零模型这张单里动。
    """
    assert MIN_RECENT_MESSAGES == 8, "下限口径变了，上面那段理由要跟着重写"
    assert MIN_RECENT_MESSAGES % 2 == 0, "按整轮计过，奇数条就不再是完整的一问一答"
    history, _locators, _predicates = _history_with_evidence(evidence_pairs=14, plain_pairs=8)
    trimmed = trim_history(history, budget_tokens=1)
    floor = history[-MIN_RECENT_MESSAGES:]
    assert _contents(trimmed[-MIN_RECENT_MESSAGES:]) == _contents(floor), (
        "最近 8 条没能逐字节原样保留"
    )


def test_older_human_questions_survive_verbatim():
    """替代方案的形状：旧轮保住人类问题与凭证，模型侧长答才是可截可丢的那一半。"""
    history, _locators, _predicates = _history_with_evidence()
    questions = [
        str(message.content) for message in history if type(message).__name__ == "HumanMessage"
    ]
    trimmed = trim_history(history, budget_tokens=1)
    after = _contents(trimmed)
    missing = [question for question in questions if question not in after]
    assert missing == [], "旧轮的人类问题被裁掉了：%r" % missing
    assert len(trimmed) < len(history), "一条都没丢，这一档的丢弃腿就没被量到"


def test_tool_call_pairs_are_never_cut_apart():
    """结构护栏（本班自加，判据未点名）：带 tool_calls 的 AIMessage 与它的 ToolMessage 整条不碰。

    裁掉任一半，剩下那一半就是 provider 直接拒收的非法消息序列 —— 那不叫瘦身，叫改形状。
    它与"凭证不裁"同级，写在这里防下一次手滑把消息序列裁成半截。
    """
    call = {"name": "dispatch", "args": {"workers": ["doc"]}, "id": "call-r33"}
    tool_payload = "【doc Agent 返回】住宿费按每人每晚 500 元计发。" * 40
    history = [
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content=tool_payload, tool_call_id="call-r33"),
    ] + _tail(6)

    trimmed = trim_history(history, budget_tokens=1)
    tools_messages = [m for m in trimmed if type(m).__name__ == "ToolMessage"]
    assert len(tools_messages) == 1, "ToolMessage 被丢了（配对的另一半还留着）"
    assert str(tools_messages[0].content) == tool_payload, "ToolMessage 被截断了"
    callers = [m for m in trimmed if getattr(m, "tool_calls", None)]
    assert len(callers) == 1, "带 tool_calls 的 AIMessage 被丢了"
    assert callers[0].tool_calls[0]["name"] == "dispatch", "tool_calls 被裁坏了"
    assert callers[0].tool_calls[0]["id"] == "call-r33", "tool_calls 配对 id 变了"
    assert callers[0].tool_calls[0]["args"] == {"workers": ["doc"]}, "tool_calls 参数被动过"
