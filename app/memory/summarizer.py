"""
短期记忆 —— 历史裁剪（R33：零模型）

这条腿以前**自己多发一发模型**：``app/agents/orchestrator.py`` 把
``_make_model(ModelTier.COMPRESS)`` 交给 ``compress_messages``，由本文件的 ``summarize()``
让本机模型把旧历史写成一句话。R33 按跟进单 §21 表 L505 判据②「裁剪过程零模型调用」
（总控改写版见 ``docs/handoff/2026-09-20-unblock-map.md`` §G-4）把它换成纯确定性裁剪。

一句话摘要在零模型前提下**做不到不损失信息**：摘要本身就是"由模型决定哪些事实可以丢"，
不换掉模型就没有这种判断力，硬做只会得到一个假装无损的字符串。所以本文件不再保留摘要
语义，改用一条可复算的规则（R118 定策纸里给出的替代方案）：

* 预算之内一律不动（估算 token 不超 ``input_budget_tokens`` 时原样返回）；
* 最近 ``MIN_RECENT_MESSAGES`` 条原样保留；
* 更旧的轮次里**人类问题原样保留**，模型侧长答按 ``TRUNCATED_BODY_CHARS`` 字符截断；
* 权限谓词文本与来源定位串**一条都不许少**（既不丢也不截）；
* 带 ``tool_calls`` 的 AIMessage 与 ToolMessage 整条不碰 —— 它们是一个配对，裁掉任一半
  会让消息序列本身变成 provider 直接拒收的非法结构，那已经不是"瘦身"而是"改形状"。
  护栏优先于预算：装不下就留日志把话说明白，不偷偷丢证据。

同输入必同输出：不掷随机数、不读时间、不调模型。
"""
from langchain_core.messages import HumanMessage

from app.common.logger import logger
from app.common.model_budget import estimate_prompt_tokens

#: 最近这么多条消息原样保留。8 条 = 4 个"一问一答"来回，与 R33 之前的 ``KEEP`` 同值：
#: 真机 run4/run5 的答案是在"最近 8 条可见"这个口径上量出来的，收窄这个窗口属于
#: "会改答案内容"的那一半（也正是判据③ 要它与 R36 同批合并的理由），由总控在 run6
#: 观察，不在 R33 这张零模型单里动。
MIN_RECENT_MESSAGES = 8

#: 旧轮长答保留的正文字符数。这个数不是本班新定的决定：R33 之前喂给摘要模型的每一行
#: 历史本来就是 ``content[:200]``（旧 ``_to_text``），所以确定性裁剪交给下游的信息
#: **不少于**摘要腿当天读到的量，只是不再为此花那一发往返。
TRUNCATED_BODY_CHARS = 200

#: 截断标记：被裁过的消息要当场认得出来，不许装作是一条完整回答。
TRUNCATION_SUFFIX = "\n…[R33 历史截断]"

#: 来源定位串的形状。这里只登记"怎么认"，真源各自点名，不抄第二份全文：
#: ``app/agents/evidence.py:78`` 造 ``f"{source}#chunk={index}"``，
#: ``app/agents/tools.py:782`` 造 ``f"[{i}] 来源:{source} 相关度:{score}"``，
#: ``app/agents/orchestrator.py:844`` 造 ``f"来源：{'、'.join(evidence_sources)}"``，
#: ``app/api/v1/chat.py:953`` 造 ``f"[来源: {s['source']}]"``。
PROVENANCE_MARKERS: tuple[str, ...] = ("#chunk=", "来源:", "来源：", "[来源: ")

#: 权限谓词文本：``app/rag/filters.py:84`` 交出的 ``{"classification": {"$in": [...]}}``
#: 与 ``:108`` 交出的 ``{"$and": [..., {"department": {"$in": [...]}}]}`` —— 也就是
#: ``where`` 的算子，加上 ``DocumentRetrievalScope.allows`` 那枚 ``pred`` 读的两个键名。
PERMISSION_MARKERS: tuple[str, ...] = ("$in", "$and", "classification", "department")

#: 不许裁的凭证文本全集（③ 的硬护栏）。
GUARDRAIL_MARKERS: tuple[str, ...] = PROVENANCE_MARKERS + PERMISSION_MARKERS


def carries_guardrail(text: str) -> bool:
    """这条消息里有没有"不许裁"的凭证文本（来源定位串或权限谓词）。

    判据刻意**过宽**：多留一条长答只是少省一点 token，少留一条来源定位串就是出处撒谎
    （R36 的诚实性边界）。认不准的时候一律按"要留"处理。
    """
    return any(marker in text for marker in GUARDRAIL_MARKERS)


def _content_text(message) -> str:
    """只有字符串正文才参与截断；多模态/结构化 content 一律按"不许动"处理。"""
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _is_human(message) -> bool:
    return isinstance(message, HumanMessage) or type(message).__name__ == "HumanMessage"


def _is_structural(message) -> bool:
    """tool_calls 与它的返回是一枚配对：只许整条留，不许裁成半条。

    裁掉一条带 ``tool_calls`` 的 AIMessage，剩下那条 ToolMessage 就失去前置；反过来裁掉
    ToolMessage 也一样。这种历史发给 provider 是被拒收，不是变短，所以它跟凭证同级。
    """
    return bool(getattr(message, "tool_calls", None)) or type(message).__name__ == "ToolMessage"


def _truncate(message, text: str):
    return message.model_copy(
        update={"content": text[:TRUNCATED_BODY_CHARS] + TRUNCATION_SUFFIX}
    )


def history_input_budget_tokens(tier=None) -> int:
    """真正吃这份历史的那一档，还允许塞进 prompt 多少 token。

    预算不从 ``summarizer`` 自己猜，而是问 :class:`app.agents.contracts.ModelBudget` 的
    ``input_budget_tokens``（R30 落地的口径：上下文上限减掉该档自己的输出顶）。惰性导入
    只为让 ``app.memory`` 单独可导入，不构成环：``app/agents/__init__.py`` 是空文件。
    """
    from app.agents.contracts import DEFAULT_MODEL_TIER, ModelBudget

    return int(ModelBudget(tier=DEFAULT_MODEL_TIER if tier is None else tier).input_budget_tokens)


def trim_history(messages, *, budget_tokens: int) -> list:
    """确定性历史裁剪：零 provider 调用。规则见模块 docstring。

    返回的列表只可能**变短或变短内容**：每条操作要么是"原样保留"，要么是"截断"，要么是
    "丢掉一条已经截过、且不带凭证的模型侧长答"，所以估算 token 对裁剪前恒 ≤（判据④）。
    """
    original = list(messages)
    if not original:
        return messages

    budget = max(1, int(budget_tokens))
    if estimate_prompt_tokens(original) <= budget:
        return messages

    recent_cut = max(0, len(original) - MIN_RECENT_MESSAGES)
    trimmed: list[tuple[object, bool]] = []
    for index, message in enumerate(original):
        text = _content_text(message)
        protected = (
            index >= recent_cut
            or _is_human(message)
            or _is_structural(message)
            or not text
            or carries_guardrail(text)
        )
        trimmed.append((message if protected else _truncate(message, text), protected))

    def _selected(keep_flags):
        return [message for (message, _protected), keep in zip(trimmed, keep_flags) if keep]

    keep_flags = [True] * len(trimmed)
    for position, (_message, protected) in enumerate(trimmed):
        if estimate_prompt_tokens(_selected(keep_flags)) <= budget:
            break
        if protected:
            continue
        keep_flags[position] = False

    result = _selected(keep_flags)
    if estimate_prompt_tokens(result) > budget:
        # 护栏赢过预算：宁可这一发 prompt 仍然偏大并留账，也不靠丢证据把数字做小。
        logger.warning(
            f"[Summarizer] R33 裁剪后仍超预算（{estimate_prompt_tokens(result)} > {budget} token）："  
            f"留下的是最近 {MIN_RECENT_MESSAGES} 条、全部人类问题、凭证文本与 tool_calls 配对，"
            "这四类不裁也不丢（判据③：护栏优先于预算；宁可 prompt 偏大，不靠丢证据把数字做小）"
        )
    return result


def compress_messages(messages, model=None, *, tier=None, budget_tokens=None) -> list:
    """短期记忆入口：**零模型**（R33）。

    ``model`` 这个位置只保留下来是为了把话说重——谁再想把一发模型往返塞回这条腿，这里
    当场 ``TypeError``，而不是静默收下再多花一次往返。R33 之前的写法
    ``compress_messages(msgs, _make_model(ModelTier.COMPRESS))`` 因此直接失效，这正是
    判据① 要的形状；按 ``model=None`` 传参的既有用例（``tests/test_phase1_arch.py:68``）
    不受影响。
    """
    if model is not None:
        raise TypeError("R33 起历史裁剪零模型：compress_messages 不再接受 model 参数")

    budget = (
        history_input_budget_tokens(tier) if budget_tokens is None else int(budget_tokens)
    )
    trimmed = trim_history(messages, budget_tokens=budget)
    if len(trimmed) != len(messages):
        logger.info(
            f"[Summarizer] R33 确定性裁剪 {len(messages)} → {len(trimmed)} 条（零模型，预算 {budget} token）"
        )
    return trimmed
