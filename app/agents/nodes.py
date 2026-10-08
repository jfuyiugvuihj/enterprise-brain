"""
阶段 1 · 新图各节点逻辑

节点：classify_intent / respond / load_memory / plan / reflect / synthesize
共享模型工厂 _make_model 也放这里，避免 orchestrator 循环依赖。
"""
import os
import time
import re
import httpx
from dataclasses import dataclass
from typing import Any, NamedTuple, Sequence
from uuid import uuid4

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import Runnable

from app.common.logger import logger
from app.common.model_config import (
    DEFAULT_KEEP_ALIVE_SECONDS,
    check_context_pairing,
    get_local_model_settings,
    observe_runtime_context_window,
    record_runtime_context_window,
    resolve_keep_alive,
    runtime_window_from_refusal,
)
from app.common.model_handler import KEEP_ALIVE_FIELD
from app.common.model_handler import TRANSPORT_COMPAT
from app.agents.contracts import (
    CONTEXT_PAIRING_MARKER,
    AgentResult,
    DEFAULT_MODEL_TIER,
    ModelTier,
    context_refusal_attribution,
)
from app.common.model_budget import (
    NO_ANSWER_CODE,
    ModelContextLimitExceeded,
    answer_text,
    authorize,
    budget_signal,
    context_error_code,
    detect_empty_answer,
    detect_output_truncation,
    estimate_prompt_tokens,
    http_timeout,
    model_tier_budget,
    model_timeout_code,
    produced_a_tool_call,
    lever_rejection_code,
    no_think_request_fields,
    resolve_model_thinking,
    record_budget_event,
    report_budget,
    thinking_extra_body,
)
from app.agents.critic import review_agent_results
from app.agents.planner import build_task_plan
from app.memory import recall, remember
from app.memory.profile import compose_profile_context, get_profile


#: The sentences this boundary answers with when the model did not answer. They are named
#: here, next to the code that writes them, because there is a second reader: an answer cache
#: keyed on the customer's question must not store one of these, or a single timeout keeps
#: being "answered" long after the model came back (R99 judgement 4, and the shipped cache
#: TTL is 1800 s). These are the sentences the boundary has always written, verbatim; the
#: class below now spends these names instead of the literals, so a reworded sentence cannot
#: drift away from the predicate that is supposed to recognise it.
OFFLINE_REIMBURSEMENT_ANSWER = '公司报销流程一般包括提交申请、部门审批、财务复核和付款归档。离线模式下我先给你这个通用版本。'
OFFLINE_ANALYSIS_ANSWER = '离线模式下可先按门店利润、营收和成本三项做排序，再进一步看利润率和同比环比变化。'
OFFLINE_GENERIC_ANSWER = '离线模式已启用，但我仍可以继续帮你梳理问题、拆解任务，并给出可执行的下一步建议。'
#: The streaming fallback emits this chunk on its own, so the text a client accumulates is
#: this sentence and nothing else.
OFFLINE_STREAM_CHUNK = '离线模式已启用'
#: 模型不可用、而工具已经查到料时往屏上放的那一格（B25）。以前这里零判据：整段原文包成
#: AIMessage 就交出去，10-08 撤下演练屏上落了 12,476 字检索原文（读数
#: %TEMP%\evalrun\r7revert 环 7）——既没人整理，也不说模型坏了，还被当成答案进缓存。
#: 现在两条：失败当场说破，材料限长。
OFFLINE_TOOL_OUTPUT_LEAD = '本轮模型不可用，下面是系统这一步返回的原文，未经整理：'
#: 上限按「一屏读得完」定；超出的部分不带上屏，但当场写明还剩多少字没显示。
OFFLINE_TOOL_OUTPUT_MAX_CHARS = 600

OFFLINE_REPLY_TEXTS = frozenset(
    {
        OFFLINE_REIMBURSEMENT_ANSWER,
        OFFLINE_ANALYSIS_ANSWER,
        OFFLINE_GENERIC_ANSWER,
        OFFLINE_STREAM_CHUNK,
    }
)
_OFFLINE_REPLY_VARIANTS = frozenset(value.strip() for value in OFFLINE_REPLY_TEXTS)


def is_offline_reply_text(text) -> bool:
    """Whether this text is one of the sentences above rather than something a model wrote.

    Exact match, deliberately: a substring test would flag a real answer that happens to
    discuss offline mode. The one exception is the bounded excerpt below, whose lead is a
    constant written by this same boundary -- text a model authored cannot start with it.
    The direction of the error is what decided that -- a false positive
    costs one cache miss, a false negative replays a canned sentence as an answer until the
    entry expires. Nothing in the delivery path changes today: the caller that has to ask
    this question is the cache guard in app/api/v1/chat.py, outside this ticket's write
    domain, and tests/test_r99_budget_selfconsistency.py pins that it does not yet.
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if stripped in _OFFLINE_REPLY_VARIANTS:
        return True
    # 兜底那半截原文（``_offline_tool_output_reply``）：开头这句是死的、后面那段料是活的，
    # 精确匹配认不出它，于是它既会进答案缓存（一次模型故障被当成这个问题的答案回放半
    # 小时），又会被 ``_answer_leg_publishes_tail`` 当成刚才那半截字的延伸接到屏上。这枚
    # 开头由本文件写，模型写的字不可能以它开头。
    return stripped.startswith(OFFLINE_TOOL_OUTPUT_LEAD)


def _offline_tool_output_reply(tool_output: str) -> str:
    """模型不可用时兜底交回的那一格：说破失败，且不许把整段原始材料堆上屏（B25）。

    点名那句与料之间空一行，屏上是两格不是一坨；料太长就只送头一截，尾巴上当场写明
    还有多少字没显示——不许让人以为这一屏是完整的。
    """
    gap = chr(10) * 2
    body = (tool_output or "").strip()
    if len(body) <= OFFLINE_TOOL_OUTPUT_MAX_CHARS:
        return OFFLINE_TOOL_OUTPUT_LEAD + gap + body
    shown = body[:OFFLINE_TOOL_OUTPUT_MAX_CHARS]
    omitted = f"（余下 {len(body) - len(shown):,} 字未显示：模型不可用，没有人整理它。）"
    return OFFLINE_TOOL_OUTPUT_LEAD + gap + shown + gap + omitted


class _OfflineModel(Runnable):
    def __init__(self, tool_names=None):
        self.tool_names = list(tool_names or [])

    def bind_tools(self, tools):
        return _OfflineModel([
            getattr(tool, "name", "")
            for tool in tools
            if getattr(tool, "name", "")
        ])

    def invoke(self, messages, config=None, **kwargs):
        text = ""
        tool_output = ""
        for msg in reversed(messages or []):
            content = getattr(msg, "content", None)
            if content is None and isinstance(msg, dict):
                content = msg.get("content", "")
            if type(msg).__name__ == "ToolMessage" or (
                isinstance(msg, dict) and msg.get("role") == "tool"
            ):
                tool_output = str(content or "")
                break
            if content:
                text = str(content)
                if type(msg).__name__ in {"HumanMessage", "SystemMessage"} or (
                    isinstance(msg, dict) and msg.get("role") == "user"
                ):
                    break
        if tool_output.strip():
            return AIMessage(content=_offline_tool_output_reply(tool_output))
        if "dispatch" in self.tool_names:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "dispatch",
                    "args": {"workers": self._choose_workers(text)},
                    "id": "offline-dispatch",
                    "type": "tool_call",
                }],
            )
        if "search_docs" in self.tool_names:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_docs",
                    "args": {"query": text},
                    "id": "offline-search-docs",
                    "type": "tool_call",
                }],
            )
        if "analyze_data" in self.tool_names:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "analyze_data",
                    "args": {"query": text},
                    "id": "offline-analyze-data",
                    "type": "tool_call",
                }],
            )
        if "报销" in text or "流程" in text:
            content = OFFLINE_REIMBURSEMENT_ANSWER
        elif "利润" in text or "门店" in text or "分析" in text:
            content = OFFLINE_ANALYSIS_ANSWER
        else:
            content = OFFLINE_GENERIC_ANSWER
        return AIMessage(content=content)

    @staticmethod
    def _choose_workers(text: str) -> list[str]:
        lowered = text.lower()
        chart_keywords = ["画图", "图表", "柱状图", "折线图", "饼图", "可视化", "chart"]
        export_keywords = ["导出", "pdf", "报告", "下载", "export"]
        data_keywords = ["数据", "收入", "成本", "利润", "排名", "统计", "分析", "对比", "销售部", "研发部"]
        doc_keywords = ["文档", "制度", "流程", "报销", "差旅", "审批", "标准", "知识库", "手册"]
        if any(keyword in lowered for keyword in chart_keywords):
            return ["chart"]
        if any(keyword in lowered for keyword in export_keywords):
            return ["export"]
        has_doc = any(keyword in text for keyword in doc_keywords)
        has_data = any(keyword in text for keyword in data_keywords)
        if has_doc and has_data:
            return ["doc", "data"]
        if has_data:
            return ["data"]
        return ["doc"]

    def stream(self, *args, **kwargs):
        yield type("Chunk", (), {"choices": [type("Choice", (), {"delta": type("Delta", (), {"content": OFFLINE_STREAM_CHUNK})()})()]})()


#: Whether the resolved thinking mode has been announced to the log this process lifetime.
#: ``_make_model`` runs once per graph at import time -- the four worker graphs, the
#: orchestrator's dispatcher, the planner, the code and alert sites -- so an un-latched line
#: prints eight identical sentences before the first request and adds nothing after it.
_THINKING_MODE_LOGGED = False


def _log_thinking_mode(base_url: str) -> None:
    """Say once which thinking mode the compatible leg will send, and how it got that one."""
    global _THINKING_MODE_LOGGED
    if _THINKING_MODE_LOGGED:
        return
    _THINKING_MODE_LOGGED = True
    policy = resolve_model_thinking()
    logger.info(
        f"[Model] 兼容腿 thinking={policy.mode}"
        f"（{('请求体带 ' + '|'.join(no_think_request_fields())) if policy.wire else '请求体不带 thinking 字段，与 R100 之前逐字节相同'}）"
        f"，来源 {policy.note}，端点 {base_url}"
    )


def reset_thinking_mode_log() -> None:
    """Let the next model built announce its mode again. A test seam for the latch above."""
    global _THINKING_MODE_LOGGED
    _THINKING_MODE_LOGGED = False


#: Whether the residency window this leg asks for has been announced to the log yet. Same
#: latch and same reason as ``_THINKING_MODE_LOGGED`` above.
_KEEP_ALIVE_MODE_LOGGED = False


def _log_keep_alive_mode(base_url: str) -> None:
    """Say once how long the answer leg asks the local server to keep the model loaded.

    R34 gave the deployment ``LOCAL_MODEL_KEEP_ALIVE`` and resolved it into one bounded policy,
    but this file carried no ``keep_alive`` reference at all, so only the rewrite leg sent it and
    the answer leg never said what it wanted. 跟进单 L1519 charges that gap to this ticket; say
    what the gap actually turns out to be, because the honest version is narrower than the
    variable suggests. On this host (Ollama 0.34.2, measured 2026-09-21 by reading ``/api/ps``
    between calls) the native leg does obey the field -- ``20m`` left 1200 s, ``6m`` left 360 s --
    while ``/v1`` ignores it: the same 1200 s survived a compat call asking for ``20m``, one
    asking for nothing, and one asking for ``1800s`` while only 360 s were left. So this line
    announces a request, not a result. The reason to make the request anyway is that a leg which
    never states its window cannot be audited, cannot be migrated, and cannot be the leg that
    benefits the day the server starts listening. What a cold load costs here was observed once,
    not designed for: 9.36 s against 2.62 s for the same request warm.
    """
    global _KEEP_ALIVE_MODE_LOGGED
    if _KEEP_ALIVE_MODE_LOGGED:
        return
    _KEEP_ALIVE_MODE_LOGGED = True
    policy = resolve_keep_alive()
    logger.info(
        f"[Model] 兼容腿 keep_alive="
        + (
            f"{policy.wire}（来源 {policy.note}）"
            if policy.seconds != DEFAULT_KEEP_ALIVE_SECONDS
            else f"未下发，即用服务端默认 {DEFAULT_KEEP_ALIVE_SECONDS}s（本机未改常驻窗口，来源 {policy.note}）"
        )
        + f"，端点 {base_url}"
    )


def reset_keep_alive_mode_log() -> None:
    """Let the next model built announce its residency window again. A test seam for the latch."""
    global _KEEP_ALIVE_MODE_LOGGED
    _KEEP_ALIVE_MODE_LOGGED = False


#: Whether the context-window pairing has already been announced, and with which verdict. Same
#: latch shape as ``_THINKING_MODE_LOGGED`` and ``_KEEP_ALIVE_MODE_LOGGED`` beside it, with one
#: difference on purpose: it remembers the verdict it said rather than the fact that it said
#: something, so a process that started before any model was resident announces the real pairing
#: the moment a reading arrives instead of repeating "unread" at every graph build.
_CONTEXT_PAIRING_ANNOUNCED: str | None = None


def reset_context_pairing_log() -> None:
    """Let the next model built announce its pairing again. A test seam for the latch above."""
    global _CONTEXT_PAIRING_ANNOUNCED
    _CONTEXT_PAIRING_ANNOUNCED = None


def _log_context_pairing(base_url: str, budget) -> None:
    """Say once, while the service starts, whether the claimed window and the served one agree.

    R535 judgement 2. The hook is the one this file already uses to announce configuration at
    build time (:func:`_log_thinking_mode`, :func:`_log_keep_alive_mode`), because that is the
    path a process walks exactly once before it answers anything: ``_make_model`` runs per graph
    at import time. No route is opened for it and none is needed -- the same verdict comes back
    from ``app.common.model_config.check_context_pairing`` for any reader that already exists,
    which is what the ticket asks for instead of a second对外出口.

    What the two readings are, and why only one of them is ours: ``MODEL_CONTEXT_TOKENS`` is the
    window this process computes against, while the window a request is served inside belongs to
    the model server, which this product never tells what to load (no ``num_ctx`` goes into any
    payload). The registry question is throttled and optional: a server that has not been asked,
    or that answers with nothing resident, yields ``runtime_unread`` and one honest line naming
    the single side that was read. That is neither an outage nor a pass, and it never prints as
    either. Nothing here refuses to build the graph over a missing answer -- a startup self-check
    that can take the service down would be a second bug, not a fix.
    """
    global _CONTEXT_PAIRING_ANNOUNCED
    if budget is None:
        return
    try:
        observe_runtime_context_window(base_url)
        pairing = check_context_pairing(budget=budget)
    except Exception as exc:  # noqa: BLE001 - the announcement observes, it never decides
        logger.warning(f"{CONTEXT_PAIRING_MARKER} 配套自检未运行: {type(exc).__name__}")
        return
    if pairing.verdict == _CONTEXT_PAIRING_ANNOUNCED:
        return
    _CONTEXT_PAIRING_ANNOUNCED = pairing.verdict
    (logger.warning if pairing.actionable else logger.info)(
        f"{CONTEXT_PAIRING_MARKER} tier={pairing.tier}"
        f" declared={pairing.declared_window_tokens}({pairing.declared_window_source})"
        f" runtime={pairing.runtime_window_tokens}({pairing.runtime_window_source})"
        f" verdict={pairing.verdict} delta={pairing.delta_tokens}"
        f" room={pairing.prompt_room_tokens} cap={pairing.declared_max_tokens}"
        f" min_answer={pairing.min_answer_tokens} {pairing.sentence}"
    )


def _harvest_runtime_window(exc: BaseException) -> None:
    """Keep the window the server named when it refused, for the next pairing verdict.

    A provider's answer to an over-long prompt states the server's own number --
    ``request (4402 tokens) exceeds the available context size (4096 tokens)``, recorded at
    ``docs/perf/raw/rate_prefill.jsonl`` -- so a collision is also a measurement: taken on the
    request that was already in flight, at the moment it hurt, and reduced to one integer before
    anything is written down. The text itself is not kept, which is the other half of R535
    judgement 3: no customer document reaches the log through this path.
    """
    served = runtime_window_from_refusal(str(exc))
    if served is not None:
        record_runtime_context_window(served, source="provider_refusal")


def _log_context_refusal(budget, prompt_tokens) -> None:
    """Beside a refusal, name the two numbers that produced it and the two keys that fix them.

    R535 judgement 3, and it moves no verdict: the request is still refused before it goes on
    the wire, ``context_limit_exceeded`` is still the code it carries, and the offline sentence
    is still not used -- ``tests/test_r30_context_limit_guard.py`` and
    ``tests/test_r255_refusal_says_the_parameters_are_small.py`` are the pins that would notice
    any of that changing. It gets its own marker because a second ``[ModelBudget]`` line for one
    call would break the "one grep, one finding" property that same file pins.

    ``prompt_tokens`` is a count from ``estimate_prompt_tokens``, never the text it counted, and
    ``context_refusal_attribution`` accepts nothing else, so "the attribution must not carry
    document content" is structural rather than a promise somebody keeps editing.
    """
    if budget is None:
        return
    try:
        pairing = check_context_pairing(budget=budget)
    except Exception as exc:  # noqa: BLE001 - a diagnosis must not change what is refused
        logger.warning(f"{CONTEXT_PAIRING_MARKER} 配套自检未取到读数: {type(exc).__name__}")
        pairing = None
    attribution = context_refusal_attribution(budget, prompt_tokens, pairing)
    if attribution:
        logger.warning(f"{CONTEXT_PAIRING_MARKER} {attribution}")


def _with_boundary_fields(call_kwargs: dict) -> dict:
    """Re-assert the body fields this boundary owns on the request it is about to send.

    :meth:`_ResilientModel._budget_kwargs` already puts it there, and a caller that brings its
    own ``extra_body`` would otherwise delete it: ``langchain_openai`` merges call-time kwargs
    over the client defaults, it does not deep-merge ``extra_body``. So the merge happens here
    instead. The caller keeps its own ``max_tokens`` -- R30 pinned that a caller's cap wins --
    and only the field this boundary owns is put back when the caller never mentioned it. A
    caller that writes an explicit ``thinking`` value is obeyed, because that is a decision
    rather than an accident.

    An ``enabled`` process adds nothing at all, which is what makes "switch it back on" mean
    "send the bytes this product sent before this ticket" instead of inventing a second
    spelling nobody measured.

    R591 is about *which* fields a ``disabled`` process adds, not about this merge: the loop
    below already takes whatever :func:`thinking_extra_body` returns, so the compatible leg
    gained the field its endpoint actually reads (``reasoning_effort="none"``, measured against
    the inert ``thinking`` object in ``app/common/model_budget.py``) without a second call site
    to forget. That is the property worth keeping -- one switch, one fragment, both legs of this
    boundary, and a caller that wrote its own value is still obeyed.

    ``keep_alive`` joined the same merge under R29, for the same reason and with the same
    respect for a caller that spelled the field itself. Its value is resolved per call rather
    than cached on the instance, exactly like :meth:`app.common.model_handler.ModelHandler._keep_alive`:
    an operator who edits the variable between two questions must not have to restart the
    service, and a clamped window has to travel with the request it explains. Note what this
    field is and is not: it buys back the seconds a *cold* load costs, and it does nothing about
    a thinking model's tokens -- 跟进单 §21 R29 的「思考税」与 R34 的「常驻」是两笔账。

    It is asked for only when this deployment actually moved the window. Two reasons, and both
    are load-bearing: a number equal to the server's own documented default
    (``DEFAULT_KEEP_ALIVE_SECONDS``) changes nothing on the wire, and ``tests/test_r100_thinking_switch.py``
    holds this leg's body to a byte-level claim -- "an ``enabled`` process sends exactly the body
    it sent before R100" -- which any always-on field would break. So the shipped ``15m`` in the
    deployment files reaches the answer leg's *request* from here on, and a box that never
    configured one keeps sending nothing at all, which is what it would have done anyway. What
    the server does with the request is a separate, measured fact and it is not flattering: on
    this host ``/v1`` ignores the field -- ``_log_keep_alive_mode`` carries the reading -- so the
    client half of 跟进单 L1519 is closed and the wire half is still open. Two consequences
    belong here: today the rewrite leg's native window does survive the answer call, because a
    compat call neither applies nor resets, which is also why R34's 09-19 finding that the answer
    leg shortens the window no longer reproduces on 0.34.2.
    """
    extra_body = dict(call_kwargs.get("extra_body") or {})
    for field, value in thinking_extra_body().items():
        extra_body.setdefault(field, value)
    keep_alive = resolve_keep_alive()
    if keep_alive.seconds != DEFAULT_KEEP_ALIVE_SECONDS:
        extra_body.setdefault(KEEP_ALIVE_FIELD, keep_alive.wire)
    return {**call_kwargs, "extra_body": extra_body}


# ==================== R31：生成轮流式片段边界 ====================
#
# 判据出处：跟进单 §21 R31 判据②③，以及《计划书》§2.7 点名的两个静默陷阱。前端
# ``frontend/src/lib/sessions.js`` 的 ``case 'text'`` 是**逐片追加**，并且拿
# ``state.segments.includes(chunk)`` 做去重：把模型逐 token 吐出的增量原样转成 SSE，
# "。""，"、空格、短数字会互相撞车并被**静默丢弃**——表现为答案缺字，且不报任何错。
# 所以合并只能做在后端（本单判据③ 追加约束也明写不许推给前端）。规则做成三枚常量 +
# 一枚可钉的类：
#
#   尺寸闸  缓冲攒到 ``STREAM_PIECE_MIN_CHARS``（20 字）即成片——这是正常输出速率下的
#            唯一闸，所以"每片 ≥20 字"是真的成立，不是一个被另一条 OR 掉掉的形容词；
#   空档闸  下一个字隔了 ``STREAM_PIECE_MERGE_SECONDS``（100 ms）还没到，就把已攒的字成片
#            发出（"按 100 ms 合并"）。空档判定发生在**下一次到达**，所以本层不需要线程
#            与定时器；另有 ``STREAM_PIECE_STALL_FLOOR_CHARS`` 一枚地板，因为"按 100 ms
#            合并"绝不许被实现成"每 100 ms 发一个单字碎片"，那正是 §2.7 要禁的东西。
#   末片    收尾时残余的缓冲照发，允许短于 20 字：无损（判据②）优先于整齐，末尾没有
#            下一个字来把它补足。
#
# 空档闸为什么按"离上一次到达隔了多久"量，而不是按"缓冲攒了多久"量：后者是字面能过而
# 实际不设防的写法。R31 真机第一版就是这么写的（缓冲起算 100 ms 即成片），在宿主
# qwen2.5:3b-instruct 实测 ~90 字/s 的解码速率下，9 发 136 片里 127 片不足 20 字
# （p50=11、p95=15）——每一片都是被时延闸提前放走的，"≥20 字"一个字都没做到。按空档量，
# 只要字还在连续到达就一定是尺寸闸说了算，只有模型真停手才让短片出去。

#: 判据③ 的两把尺。改这两个数就是改契约，由 ``tests/test_r31_stream_pieces.py`` 钉住。
STREAM_PIECE_MIN_CHARS = 20
#: 空档闸：离上一次字到达隔过这么多秒，才允许发一片不足 20 字的片。
STREAM_PIECE_MERGE_SECONDS = 0.1
#: 空档闸的地板。判据③ 禁"单字碎片"，所以它不许被设成 1；也不许高过尺寸闸，
#: 否则空档闸形同不存在（构造期夹住）。
STREAM_PIECE_STALL_FLOOR_CHARS = 4

#: ``config["configurable"]`` 里"这一轮的流式片段往哪儿送"的键。走 configurable 而不是
#: state：state 要过 checkpointer 序列化，回调不可 JSON 化；``cancel_event``、``principal``、
#: ``evidence_bag`` 走的就是同一条只读通道。
STREAM_PIECE_SINK_KEY = "stream_piece_sink"


class StreamPiece(NamedTuple):
    """一片可以发给前端的可见正文，连同它自己的字到达区间。

    ``start_at`` 是这片**第一个字符**到达的时刻，``end_at`` 是它**最后一个字符**到达的时刻，
    ``emitted_at`` 是它被交出去的时刻，三枚读数取自同一枚单调时钟。判据② 的"片段时间戳不
    重叠"说的是字到达区间：任何两片的 ``[start_at, end_at]`` 互不相交——后一片的第一个字
    一定在前一片的最后一个字之后才到达。发射时刻另记一枚，是因为空档闸天然要等到下一次
    到达才决定"上一片该走了"，区间与交出时刻本来就不该混在同一枚数里。
    """

    text: str
    start_at: float
    end_at: float
    source_fragments: int
    emitted_at: float = 0.0
    #: R203 判据① 的硬前置（R149 交工时具名留在这里的那一条）：**片必须带调用身份**。
    #: 一轮里跑的不止一发模型——supervisor 派发、worker 的工具轮、工具之后那一发终答，
    #: 全都可能往同一个出口里吐字。收端要把"终答的那一发"与"别的那些发"分开，只有靠
    #: 这两格：``call_id`` 认"同一次调用"（同一次调用的字必然首尾相接），``worker`` 认
    #: "哪条腿"（收端拿它比对已经落定的 ``worker_results``，判断这一发是不是接在已交付
    #: 的答案后面）。缺任何一格，一轮里两次调用的字就会混进同一条累计串，而累计串一旦
    #: 不是终答的前缀，线上读到的就是坏形（``prefix_breaks``）——那正是判据② 的红线。
    #: 默认空串：不带身份的片（全部既有用例、``stream()`` 的老口径）形状一字不变。
    call_id: str = ""
    worker: str = ""

    @property
    def chars(self) -> int:
        return len(self.text)


def visible_chunk_text(chunk: Any) -> str:
    """一个流式片段里的可见文字，**不 strip**。

    这里不复用 :func:`app.common.model_budget.answer_text` 是有意为之：它对结果做
    ``strip()``。逐 token 调用它，每个片界都会被剥掉头尾的空白与换行——拼回去就少字，
    那正是判据② 要防的"缺字"。空答案守卫仍然用 ``answer_text``（整段剥一次没错），
    片边界这一层必须用这一枚。
    """
    content = getattr(chunk, "content", None)
    if content is None and isinstance(chunk, dict):
        content = chunk.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


class StreamPieceMerger:
    """把逐 token 的模型增量合并成满足判据②③ 的片段序列。

    四条不变量，每条都有具名用例钉住：

    G1 无损    ``"".join(p.text for p in 所有片)`` 逐字等于按到达顺序拼起来的可见正文，
              一个字符不多也不少（含空白与换行）。
    G2 不重叠  ``pieces[i].end_at <= pieces[i + 1].start_at``；调用方的时钟倒着走也拦得住。
    G3 禁单字  任何一片都不短于 ``stall_floor_chars``（末片除外——末片是答案的全部剩余，
              扣着不发就是丢字，而它后面已经没有字了）。
    G4 不扣字  字还在连续到达时由尺寸闸说了算；一旦隔满 ``merge_seconds`` 才来下一个字，
              那一次到达必须先把已攒的字成片发出去，不许继续攒着。

    没有线程也没有定时器：空档是在**下一次到达**时结算的，所以判据③ 的"100 ms"读作
    "字与字之间最多允许被攒多久"，而不是"每 100 ms 一定发一片"。答案结束由 :meth:`finish`
    兜底，残余必发。
    """

    def __init__(
        self,
        *,
        min_chars: int = STREAM_PIECE_MIN_CHARS,
        merge_seconds: float = STREAM_PIECE_MERGE_SECONDS,
        stall_floor_chars: int = STREAM_PIECE_STALL_FLOOR_CHARS,
        clock=time.monotonic,
    ) -> None:
        self.min_chars = max(1, int(min_chars))
        self.merge_seconds = max(0.0, float(merge_seconds))
        self.stall_floor_chars = min(max(2, int(stall_floor_chars)), self.min_chars)
        self._clock = clock
        self._buffer: list[str] = []
        self._buffered_chars = 0
        self._opened_at: float | None = None
        self._last_arrival_at: float | None = None
        self._fragments = 0
        self._previous_end_at: float | None = None

    @property
    def buffered_chars(self) -> int:
        """还没发出去的字数（观测用；不影响任何一门的判据）。"""
        return self._buffered_chars

    def feed(self, text: str) -> list:
        """喂进模型刚吐出的一段可见文字，返回此刻可以发出去的片（0、1 或 2 枚）。

        2 枚只可能出现在"隔了空档之后又来了一大坨"：先把上一坨按空档闸结清，再让新来的
        这坨把尺寸闸撞响。两枚的先后顺序仍然与到达顺序一致。
        """
        if not text:
            return []
        now = float(self._clock())
        pieces: list = []
        gap = (
            now - self._last_arrival_at
            if self._last_arrival_at is not None
            else 0.0
        )
        if (
            self._buffered_chars
            and gap >= self.merge_seconds
            and self._buffered_chars >= self.stall_floor_chars
        ):
            pieces.append(self._emit(self._last_arrival_at, now))
        if self._opened_at is None:
            self._opened_at = now
        self._buffer.append(text)
        self._buffered_chars += len(text)
        self._last_arrival_at = now
        self._fragments += 1
        if self._buffered_chars >= self.min_chars:
            pieces.append(self._emit(now, now))
        return pieces

    def finish(self) -> list:
        """收尾：把残余缓冲照发。这是唯一允许短于 ``min_chars`` 的一片。"""
        if not self._buffered_chars:
            return []
        return [self._emit(self._last_arrival_at, float(self._clock()))]

    def _emit(self, content_end_at: float | None, emitted_at: float):
        """把当前缓冲结清成一片：区间＝首字到达到末字到达，交出时刻＝``emitted_at``。"""
        text = "".join(self._buffer)
        start_at = self._opened_at if self._opened_at is not None else emitted_at
        if self._previous_end_at is not None and start_at < self._previous_end_at:
            # 时钟倒着走（或调用方换了时间源）也不许造出重叠的两片：把这一片的起点抬到
            # 上一片的终点。区间偏窄可以，区间重叠不行——§2.7 陷阱② 里"新片整体替换旧片"
            # 那条 covering 分支正是被重叠/包含关系触发的。
            start_at = self._previous_end_at
        end_at = content_end_at if content_end_at is not None else emitted_at
        if end_at < start_at:
            end_at = start_at
        piece = StreamPiece(
            text=text,
            start_at=start_at,
            end_at=end_at,
            source_fragments=self._fragments,
            emitted_at=emitted_at,
        )
        self._previous_end_at = end_at
        self._buffer = []
        self._buffered_chars = 0
        self._opened_at = None
        self._last_arrival_at = None
        self._fragments = 0
        return piece


def publish_stream_pieces(
    config: Any, pieces: Sequence, *, call_id: str = "", worker: str = ""
) -> None:
    """把成片交给本轮注册的 sink；没注册就什么都不做。

    sink 抛错不许影响答案：正文已经在同一条腿上手递手流出去了，为一根观测通道把用户的
    回答打断是最差的取舍，所以异常只记一行日志然后继续。默认无人注册时这一枚函数是整个
    特性关掉的样子——不建列表、不发事件、``stream_mode="values"`` 的形状一个字节都不动
    （判据④）。

    ``call_id`` / ``worker``（R203）非空时盖到每一片上——只加字段，不改任何一片的文字与
    时间戳；两格都留空时（``stream()`` 那条老路、全部既有用例）交出去的就是原对象本身，
    与改动前逐枚同身份。这是全仓唯一的盖章点，收端认的就是这里写进去的那两格。
    """
    if not pieces:
        return
    sink = None
    if isinstance(config, dict):
        configurable = config.get("configurable")
        if isinstance(configurable, dict):
            sink = configurable.get(STREAM_PIECE_SINK_KEY)
    if sink is None:
        return
    for piece in pieces:
        if call_id or worker:
            try:
                piece = piece._replace(call_id=call_id, worker=worker)
            except (AttributeError, ValueError):
                # 不是 ``StreamPiece``（调用方自定义的片形状）就原样交出去，不为一格
                # 观测字段把这一片丢掉。
                pass
        try:
            sink(piece)
        except Exception as exc:
            logger.warning(f"[R31] 流式片段出口抛错，已忽略（答案不受影响）: {exc}")
            return

# ==================== R203：图路径上的生成腿改走流式 ====================

#: 允许把 ``invoke`` 这一发改走流式的工作腿。名单之外的那几条是逐条查过的，不是漏的：
#:
#: ``export``：它那一发的正文会在**调用返回之后**被
#: :func:`app.agents.orchestrator._fallback_export_result` 整段换掉（模型没写出下载链接时
#: 报告由工具重新产出），"片必须是终答的前缀"这条硬红线在它身上结构上不成立。
#:
#: ``approval``：两条各自成立的理由，取证见 R203 交回单，钉在
#: ``tests/test_r203_sink_reaches_the_leg.py``。
#:   1. 挂起之前的那一轮里它**没有字可流**：审批腿不是 react 子图
#:      （``_builder.add_node("approval", _approval_worker_node)`` 挂的是普通节点），
#:      正文由 orchestrator.py:856-877 用 ``build_precheck()`` / ``extract_standard()``
#:      确定性拼出（``app/approval/assistant.py`` 全文零枚模型符号），既没有一发模型调用
#:      可流、拼出来的散文也不是模型正文 —— "每枚帧都是终答的前缀"在这里无从谈起。
#:      它的 child_conf 确实把本轮 sink 整本带进 configurable（:777 是全量拷贝），
#:      名单挡它不是因为接不到，是因为接到了也没有字。
#:   2. 挂起之后从 ``/approve`` 续的那一跑道**当年结构上接不到 sink**——这一格已由 **R524**
#:      接上（09-30 并树前的取证抄在下面，行号是 R203 当时的，早已漂移）：
#:      ``run_interrupt_stream`` 当年不收这一格、config 也不塞，``chat._approve_stream`` 的队列
#:      只有 event/done/error 三件、收端循环没有 piece 一支。今天四格翻了三格：形参收了、
#:      config 塞了、队列长出了第四种件 ``piece``、收端也有 ``kind == "piece"`` 那一支。
#:      名单仍旧挡住 approval 这条腿，而第 1 条说明它本来就一枚字都发不出——**名单不因 R524 放宽**。
#:      ⇒ 续跑道上真正流得出字的是被挂起之后才跑的那条腿（``_HITL_PARKED`` 现读 chart / export，
#:      其中 chart 在名单里）；逐片帧上不上屏由 R464 那道闸说了算，不由本单改。对账见
#:      ``docs/testing/r524-stream-piece-sink-two-runways.md``。
ANSWER_LEG_STREAM_WORKERS = frozenset({"doc", "data", "chart"})


def answer_leg_stream_target(config: Any) -> tuple[Any, str]:
    """这一发是不是"在场 SSE 上的工作腿生成调用"？是就返回 ``(sink, worker)``。

    两格必须在 ``configurable`` 里同时出现，缺一不发：

    - ``stream_piece_sink`` —— 只有 :func:`app.api.v1.chat._ask_stream` 会为本轮注册它。
      队列道、审批道、离线直调一律没有它，于是那些道上的字节与今天逐字相同。
    - ``worker`` —— 只有 ``_make_worker_wrapper`` 交给子图的那本 config 带它。这一格把
      supervisor 派发那一发、``plan()``、``respond()``、``_llm_pandas_code`` 这些
      **同样会经过 ``_ResilientModel.invoke`` 但不是终答**的调用关在外面：它们的字一旦
      进了累计串，收端就再也拿不回"每枚帧都是终答的单调前缀"。

    子图能看见这两格，靠的是 langgraph 把父运行的 ``configurable`` 并进嵌套调用——
    ``orchestrator.py`` 那张白名单里并没有 ``stream_piece_sink``，实测照样传得下去。
    这条取证记在交回单，别把它误当成白名单的功劳（也不必为此去改白名单）。
    """
    if not isinstance(config, dict):
        return None, ""
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None, ""
    sink = configurable.get(STREAM_PIECE_SINK_KEY)
    if sink is None or not callable(sink):
        return None, ""
    worker = str(configurable.get("worker") or "")
    if worker not in ANSWER_LEG_STREAM_WORKERS:
        return None, ""
    return sink, worker


def publish_formed_answer_pieces(config: Any, text: str, *, call_id: str = "") -> int:
    r"""把**已经成形的一整段答复**逐片交给本轮注册的出口：R662 判据① 「不许一坨」。

    病形（``docs/testing/r662-a2-single-frame-rows-2026-10-05.md``）：离线回复、以及"框架聚合
    完才交回、一枚字都没经过出口"的那一发，正文到手时**已经是一整段写完的字**。收端今天只能
    把它发成一枚帧，A② 在帧账上就读成 ``max_stream_frames == 1``——"答案已成形"这一类从来没有
    逐片上过屏。本件只管一件事：把这一整段按在册那两把尺切成片，交给同一条出口。

    🔴 分片只能做在**答复成形腿**这一侧，不许做在收端：``app/api/v1/chat.py::_AnswerPieceStream``
    的"收端一个字都不切"是 R149 判据②③ 钉住的既有裁定（``tests/test_r149_sse_text_pieces.py::
    test_a_whole_answer_with_no_pieces_still_issues_exactly_one_text_frame`` 与
    ``test_one_oversized_piece_is_never_split_by_the_receiver`` 两枚钉），收端切了就凭空造短碎片。

    四条纪律，逐条对着既有尺写，一枚都不新造：
      * **准入一字不放宽**：走 :func:`answer_leg_stream_target`——名单外（``approval``／
        ``export``／supervisor 派发）与没注册出口的道（队列道、审批道、离线直调）一枚片都不发。
      * **两把尺不动**：成片用的就是 R31 那枚 :class:`StreamPieceMerger`，尺寸闸
        （``STREAM_PIECE_MIN_CHARS``）与空档地板由它钉着；判据② 的"片段时间戳不重叠"由
        ``StreamPieceMerger._emit`` 抬起点保证（区间可偏窄不可重叠）。
      * **禁硬切凑多发**：攒不出第二枚就一枚都不发（交回 0）。天然短过尺寸闸的那一族由尺寸闸
        说了算，本件不拿多发一枚同文帧去把 ``text_frames`` 洗大。
      * **零等待**：一次喂一段、成一片，中间没有任何 sleep／定时器／节流——片与片之间的间隔
        由发射本身产生（出口 → 队列 → 收端那一枚 ``await asyncio.sleep(0)``）。

    ``call_id`` 非空时沿用那一发自己的身份（R149b 硬前置：片必须带调用身份）；留空由本件现铸
    一枚——离线回复与"聚合完才交回"都是**新的一发**，没身份收端就分不开它和别的腿。交回真正
    交出几片，调用方只拿来记日志。
    """
    sink, worker = answer_leg_stream_target(config)
    if sink is None:
        return 0
    body = text if isinstance(text, str) else ""
    if not body.strip():
        return 0
    merger = StreamPieceMerger()
    size = merger.min_chars
    pieces: list[StreamPiece] = []
    for start in range(0, len(body), size):
        pieces.extend(merger.feed(body[start:start + size]))
    pieces.extend(merger.finish())
    if len(pieces) < 2:
        return 0  # 攒不出第二枚 = 天然短，本件不硬切凑多发
    publish_stream_pieces(config, pieces,
                          call_id=call_id or uuid4().hex[:12], worker=worker)
    return len(pieces)


def publish_formed_reply_for_call(config: Any, reply: Any, *, tap: Any = None) -> int:
    """这一发一枚片都没交出去、交回来的却是整段成形的字 ⇒ 按尺寸闸补成逐片（R662 判据①）。

    ``tap`` 是那一发的流式闸门，可能为 ``None``（预算耗尽那一刻连请求都没发出去）。三种情况
    一枚片都不许多发，前两条是 R203 自己在册的闸门，本件一字不改地尊重、并且把它读全：
      * 这一发**有任何字到过闸门** —— 已经有一半真话上过屏，离线回复不是它的延伸（T3 与
        ``app/api/v1/chat.py`` 里那行「流式片段与终答不同源」的 error 日志同一裁定）。
        🔴 判据是 :attr:`_AnswerPieceTap.arrived_chars`，不是 :attr:`published`：T2 压着
        最新那枚片等下一枚来证明「还在写字」，provider 死在半路时 ``abandon()`` 把手里那枚
        整片丢弃 —— 于是「流过半截真话」那一发的 ``published`` 读数可以是 0。拿它当准入
        就会把 R210 那族「半截真话 + 离线话术」的纠正替换改发成一串片（那一形钉在
        ``tests/test_r210_frame_ledger_of_a_broken_round.py``）。
      * :attr:`_AnswerPieceTap.abandoned` 是 ``tool_call`` —— 那一发是工具轮，它的字不是终答
        （T1，钉在 ``tests/test_r203_answer_leg_streams.py::test_a_tool_call_round_publishes_no_pieces``）；
      * 准入不在名单、或本轮压根没注册出口 —— 与 :func:`publish_formed_answer_pieces` 同一条。
    """
    if tap is not None:
        if (getattr(tap, "published", 0) or getattr(tap, "arrived_chars", 0)
                or getattr(tap, "abandoned", "") == "tool_call"):
            return 0
    return publish_formed_answer_pieces(
        config, visible_chunk_text(reply),
        call_id=str(getattr(tap, "call_id", "") or ""))


class _AnswerPieceTap(BaseCallbackHandler):
    """把框架在 ``invoke`` 内部走的那一路流，接回 R31 的片段出口。

    装法走的是 langchain 的正门：一枚带 ``tap_output_iter`` 的 v1 流式回调挂进
    ``config["callbacks"]``，``BaseChatModel._should_stream`` 就认定这次 invoke 要按流式
    发——于是**聚合由框架自己做**（``generate_from_stream`` → ``message_chunk_to_message``），
    交回给 react agent 的仍是 ``type == "ai"`` 的 ``AIMessage``、带同一份 ``usage_metadata``。
    这一条是判据④ 的地基：自己拿 ``+`` 拼片会交出 ``AIMessageChunk`` 并丢掉
    ``token_usage``，而 ``synthesize``、``reflect_node``、收端判据全都用
    ``type(m).__name__ == "AIMessage"`` 认答案——形状一变，终答就不是今天这份终答。

    三道闸门决定"哪些字可以交出去"，每一道对着一条硬红线：

    T1 只发答案那一发  任何一枚 chunk 里出现工具调用（``tool_call_chunks``）就永久放弃
      这一发：它是工具轮，它的字不是终答。
    T2 滚动留一  第 k 片要等第 k+1 片真到了才发。只憋出半句就转去调工具的那一发，
      一片都发不出去——这挡掉的正是 R149 记名的"规划器口播混进同一条累计串"。
    T3 干净跑完才收尾  ``close()`` 只在 ``invoke`` 正常返回之后调；provider 抛错改走离线
      回复时 ``abandon()``，残余缓冲整片丢弃（与 R31 那枚
      ``test_a_mid_stream_provider_failure_does_not_publish_a_final_piece`` 同一条裁定：
      半截字不许冒充答案的最后一块）。

    尺寸闸与空档闸一个字不改：这里用的就是 R31 那枚 ``StreamPieceMerger``——判据③ 的两把
    尺由它钉着，本单不动它，动它就是动契约。
    """

    def __init__(self, config: Any, sink, *, worker: str, call_id: str) -> None:
        self.config = config
        self.sink = sink
        self.worker = worker
        self.call_id = call_id
        self.merger = StreamPieceMerger()
        self.published = 0
        #: 这一发**到过闸门的可见字数**（R662 的判据，与 ``published`` 不是一回事）。
        #: ``published`` 只数「已经放出门的片」，而 T2 天生压着最新那枚等下一枚来证明
        #: 「还在写字」——provider 死在半路时 ``abandon()`` 会把手里那枚整片丢弃，于是
        #: 明明流过半截真话的一发读起来像「一个字都没到过」。R662 补成形片时必须认这一格。
        self.arrived_chars = 0
        self._pending = None
        self._abandoned = ""

    # --- v1 流式回调的认门标记：``_should_stream`` 靠这两枚方法判定本 handler 要流 ---
    def tap_output_iter(self, run_id, output):
        return output

    def tap_output_aiter(self, run_id, output):
        return output

    @property
    def abandoned(self) -> str:
        return self._abandoned

    def on_llm_new_token(self, token, **kwargs) -> None:
        if self._abandoned:
            return
        message = getattr(kwargs.get("chunk"), "message", None)
        if message is None:
            return
        if produced_a_tool_call(message):
            self.abandon("tool_call")
            return
        text = visible_chunk_text(message)
        if text:
            self.arrived_chars += len(text)
        for piece in self.merger.feed(text):
            self._offer(piece)

    def _offer(self, piece) -> None:
        """T2：手里始终压着最新那片，等下一片证明"这一发还在往答案里写字"再放。"""
        if self._pending is not None:
            self._deliver(self._pending)
        self._pending = piece

    def _deliver(self, piece) -> None:
        if self._abandoned:
            return
        publish_stream_pieces(self.config, [piece], call_id=self.call_id, worker=self.worker)
        self.published += 1

    def close(self) -> int:
        """这一发没有工具调用、也没有抛错：它就是终答那一发，把尾巴放完。"""
        if self._abandoned:
            return self.published
        pending, self._pending = self._pending, None
        if pending is not None:
            self._deliver(pending)
        for piece in self.merger.finish():
            self._deliver(piece)
        return self.published

    def abandon(self, reason: str) -> None:
        if self._abandoned:
            return
        self._abandoned = reason
        self._pending = None


def _config_with_tap(config: Any, tap: _AnswerPieceTap) -> dict:
    """把 tap 挂进 ``callbacks``，其余键原样带过去——**不改调用方那本 config**。

    ``config["callbacks"]`` 到这里可能是一枚 ``CallbackManager``（langgraph 给的）也可能是
    一个列表，两种都得把已有的 handler 留住：trace 与计量的 handler 全在里面，把它们换掉
    等于让这一发的读数凭空消失。
    """
    merged = dict(config or {})
    existing = merged.get("callbacks")
    if existing is None:
        handlers: list = []
    elif isinstance(existing, (list, tuple)):
        handlers = list(existing)
    else:
        handlers = list(getattr(existing, "handlers", None) or [])
    merged["callbacks"] = [tap, *handlers]
    return merged


class _ResilientModel(Runnable):
    """Provider 请求失败时回退到本地离线模型，避免单点服务故障扩散。

    Every call passes through the machine-wide local-model budget and records one
    ``model_calls`` span, so a 14B model cannot be called without limit and the
    recorded timings come from the boundary that actually made the call.
    """

    def __init__(
        self,
        primary,
        fallback=None,
        *,
        provider: str = "local",
        model_name: str = "",
        capacity_wait_seconds: float | None = None,
        budget=None,
    ):
        self.primary = primary
        self.fallback = fallback if fallback is not None else _OfflineModel()
        self.provider = provider or "local"
        self.recorded_model_name = model_name or str(getattr(primary, "model_name", "") or "")
        self.capacity_wait_seconds = capacity_wait_seconds
        #: This call's token and clock budget; ``None`` means "an un-typed
        #: hand-built model", which only tests construct, never ``_make_model``.
        self.budget = budget

    @property
    def model_name(self):
        return getattr(self.primary, "model_name", None)

    @property
    def root_client(self):
        return getattr(self.primary, "root_client", None)

    def bind_tools(self, tools):
        try:
            primary = self.primary.bind_tools(tools)
        except Exception as exc:
            logger.warning(f"[Model] bind_tools 失败，使用离线模型: {exc}")
            primary = self.primary
        return _ResilientModel(
            primary,
            self.fallback.bind_tools(tools),
            provider=self.provider,
            model_name=self.model_name,
            capacity_wait_seconds=self.capacity_wait_seconds,
            budget=self.budget,
        )

    def _span(self, config, *, provider=None, model_name=None, queue_wait_ms=None, stage=None):
        """Open the span for this exact call, stamped with the tier that sized its budget.

        R51: ``model_tier`` is read off the budget this instance already carries, so a
        duration can be attributed to a pipeline segment without any new judgement here.
        ``stage`` stays available for a call site that knows better than the tier does.
        Nothing in this method decides routing, fallback or degradation.
        """
        from app.trace.spans import start_model_call

        return start_model_call(
            config,
            provider=provider or self.provider,
            model_name=model_name or self.recorded_model_name,
            queue_wait_ms=queue_wait_ms,
            stage=stage or "",
            model_tier=str(getattr(getattr(self.budget, "tier", None), "value", "") or ""),
        )

    def _offline_fallback(self, messages, config=None, **kwargs):
        span = self._span(config, provider="offline", model_name="offline")
        response = self.fallback.invoke(messages, config=config, **kwargs)
        from app.trace.spans import model_token_counts

        span.finish("model_unavailable", error_code="model_unavailable", summary=model_token_counts(response))
        return response

    def _wire_prompt_tokens(self, messages, kwargs) -> int | None:
        """Size the prompt the way the server will see it: the messages plus the tool fields.

        estimate_prompt_tokens(messages) 只量了消息那一半：bind_tools 挂进请求体的工具字段每一发
        都真占窗口，却不在账上。补上它，这道守卫判的是完整的一发——宁可在这里先说一句「这题装不
        下」，也不让服务端自己把本轮问题裁掉再回一枚 500。
        """
        from app.common.model_budget import request_shell_tokens

        prompt_tokens = estimate_prompt_tokens(messages)
        if prompt_tokens is None:
            return None
        return prompt_tokens + request_shell_tokens((kwargs or {}).get("tools"))

    def _budget_kwargs(self, prompt_tokens: int | None, *, stream: bool) -> tuple[dict, Any]:
        """Size this exact call: its own output cap and a clock proportional to its prompt.

        The per-request values override the client defaults, which are only the worst case
        for the tier. A provider that has never heard of ``extra_body`` still gets a valid
        request: the OpenAI-compatible wire format carries ``max_tokens`` there.

        ``authorize`` is what makes judgement (4) real twice over. When the measured prompt
        plus this cap cannot fit ``n_ctx`` it raises here, before the request goes on the
        wire, instead of letting the server answer with a truncated completion. And when the
        clock is what binds, it shortens the *answer* to the length the ceiling can pay for
        and hands that number back -- both the timeout and the ``max_tokens`` on the wire come
        from the same sized budget, so the request can no longer outlive its own deadline.

        The verdict travels with the kwargs because a clamp that is not written down is a
        mystery, and ``self.budget`` is deliberately left alone: this instance is built once
        per graph at import time and shared by every request.

        The same body also carries the thinking field, for the reason §42 measured: on the
        compatible leg an output cap and a thinking mode are not two independent settings. At
        the same ``max_tokens=1536`` the model spent the whole budget on a hidden chain and
        returned zero characters with ``finish_reason=length``, or answered 93 characters with
        ``finish_reason=stop``, depending on one request field. Sizing an answer while leaving
        the model free to eat that answer thinking would make the cap below the floor a
        mystery to the next reader, so the two decisions are made in one place and sent in one
        body.

        R591 corrected the last sentence's *field*, not its shape. The pair run16/run17 shipped
        was ``max_tokens=1536`` and ``thinking={"type":"disabled"}``, and both arms of that pair
        came back with zero visible characters at ``finish_reason=length``: the cap went to the
        hidden chain either way. The field that does change the answer on this endpoint is
        ``reasoning_effort``, and :func:`thinking_extra_body` now sends both spellings under the
        one mode word. Sizing an answer and asking for no thinking chain are still one decision
        in one body -- which is the half of this docstring that was right.
        """
        if self.budget is None:
            return {}, None
        authorized = authorize(self.budget, prompt_tokens, stream=stream)
        sized = authorized.budget
        return (
            {
                "timeout": http_timeout(sized, prompt_tokens, stream=stream),
                "extra_body": {"max_tokens": sized.max_tokens, **thinking_extra_body()},
            },
            authorized.verdict,
        )

    def _verdict_fields(self, verdict: Any) -> dict:
        """The clamp's own numbers, for the log line of whatever happened afterwards.

        Empty when this call has no verdict at all, so an unremarkable call keeps the one line
        format it always had. ``budget_verdict`` rides along because a truncation or a timeout
        on a call that was already shortened is one finding, not two: the operator reading
        "provider timed out" needs to know the clock had already been argued about once.
        """
        if verdict is None:
            return {}
        return {
            "verdict": verdict.verdict_word,
            "max_tokens": verdict.max_tokens,
            "declared_max_tokens": verdict.declared_max_tokens,
            "affordable_max_tokens": verdict.affordable_max_tokens,
            "min_answer_tokens": verdict.min_answer_tokens,
            "clamp_basis": verdict.basis,
        }

    @staticmethod
    def _leg_fields() -> dict:
        """Name the leg this boundary is on, and the fields it asked the model with.

        R591 判据① is a sentence about evidence, not about code: run16 and run17 could not be
        asked "which leg made this call?" because only the native leg ever named itself, in its
        own应答 line, while every answer leg on this boundary is compatible by construction and
        said nothing. Two things came out of that. A 400-downgrade from native to compat (R147)
        is indistinguishable from a call that never asked for native, and an empty answer is
        indistinguishable from an empty answer caused by a field this leg never sent. Both lines
        now carry the leg and the field names, and a third now carries them in the span summary,
        so the trace export answers it after the log rotation.

        Streaming is a mode, not a transport: ``invoke`` with the R203 tap, ``stream``, and the
        rewrite fallback are three different shapes of the same ``/v1/chat/completions`` request,
        which is exactly why this is a method on the boundary instead of a guess at a call site.
        """
        return {"transport": TRANSPORT_COMPAT, "no_think_fields": no_think_request_fields()}

    def _answer_leg_tap(self, config, call_kwargs: dict) -> tuple[Any, Any, dict]:
        """该发流式就返回 ``(tap, 这一发要用的 config, 附加 kwargs)``，否则 ``(None, config, {})``。

        ``stream_options.include_usage`` 是 R149b 具名的第二条硬前置（计量不许回 NULL）：
        兼容腿的流帧默认一个 ``usage`` 都不带，R38 那两格会整排回 NULL。带上它，末帧把
        ``prompt_tokens_details.cached_tokens`` 一并送回来——``stream()`` 那条老路的本机
        实测已经证明这一格可用；非流式的 body 一个字不受影响，因为只有真走流式时 langchain
        才把它放进请求。调用方自己写过 ``stream_options`` 时不越俎代庖（与 R30 那一条
        "caller's cap wins" 同一个裁定）。
        """
        sink, worker = answer_leg_stream_target(config)
        if sink is None:
            return None, config, {}
        tap = _AnswerPieceTap(config, sink, worker=worker, call_id=uuid4().hex[:12])
        extra: dict = {}
        if "stream_options" not in call_kwargs:
            extra["stream_options"] = {"include_usage": True}
        return tap, _config_with_tap(config, tap), extra

    def invoke(self, messages, config=None, **kwargs):
        from app.common.model_budget import ModelBudgetExhausted, default_model_budget

        try:
            slot = default_model_budget().acquire(wait_seconds=self.capacity_wait_seconds)
        except ModelBudgetExhausted as exc:
            logger.warning("[Model] 本地模型并发预算耗尽，使用离线回复")
            span = self._span(config, queue_wait_ms=exc.wait_ms)
            span.finish("rate_limited", error_code=exc.code)
            reply = self._offline_fallback(messages, config=config, **kwargs)
            publish_formed_reply_for_call(config, reply)
            return reply

        span = self._span(config, queue_wait_ms=slot.wait_ms)
        prompt_tokens = self._wire_prompt_tokens(messages, kwargs)
        try:
            budget_kwargs, verdict = self._budget_kwargs(prompt_tokens, stream=False)
            call_kwargs = _with_boundary_fields({**budget_kwargs, **kwargs})
        except ModelContextLimitExceeded as exc:
            # Refused before the provider saw it. The offline reply is deliberately not
            # used here: it would record model_unavailable, and evidence._terminal_status
            # reports model_unavailable ahead of a failure, so the customer would read a
            # canned greeting while the real verdict -- this prompt does not fit n_ctx --
            # stayed in a log line. The line added here changes what an operator can read,
            # not which verdict this is: see _log_context_refusal.
            _log_context_refusal(self.budget, prompt_tokens)
            slot.release()
            span.finish("failed", error_code=exc.code)
            raise
        # R203：在场 SSE 的工作腿这一发改走流式，好让本轮注册的那枚片段出口真响。
        # 预算**仍按 ``stream=False`` 那一档量**（``call_kwargs`` 就是它算出来的）：这不是
        # 笔误。``authorize(..., stream=True)`` 会按钟重新裁 ``max_tokens``，裁了就可能裁出
        # 另一个答案，而判据④ 要的是"同一个答案，逐字到达"——所以只改传输道，不改量法，
        # 发出去的 body 与今天只差 ``stream`` 与 ``stream_options`` 两格。要紧的一句话留
        # 在这里：日志里那枚 ``stream=no`` 说的是 sizing 口径（由 ``report_budget`` 格式化，
        # 不在本单写域），不代表这一发没走流式。
        tap, leg_config, leg_kwargs = self._answer_leg_tap(config, call_kwargs)
        try:
            response = self.primary.invoke(
                messages, config=leg_config, **{**call_kwargs, **leg_kwargs}
            )
        except Exception as exc:
            if tap is not None:
                # 离线回复顶上来了，而那一句话不是刚才流出去的半截字：整发放弃，剩下的
                # 片一片不发（T3）。已经发出去的那几片是判据④ 的残余风险，如实记在交回单。
                tap.abandon("provider_error")
            provider_code = context_error_code(exc)
            if provider_code:
                logger.warning(
                    budget_signal(
                        getattr(self.budget, "tier", None) or "analysis",
                        prompt_tokens=prompt_tokens,
                        read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                        code=provider_code,
                    )
                )
                if self.budget is not None:
                    # Same code as the pre-flight verdict: one collision, one answer,
                    # whether the window was measured here or refused by the server. The
                    # server's own answer is also the only reading of its window that costs no
                    # extra request, so it is kept before the verdict is re-raised.
                    _harvest_runtime_window(exc)
                    _log_context_refusal(self.budget, prompt_tokens)
                    slot.release()
                    span.finish("failed", error_code=provider_code)
                    raise ModelContextLimitExceeded(self.budget, prompt_tokens or 0) from exc
            #: R591: the one failure this boundary can *create* by fixing an empty answer. A
            #: server that has no idea what ``reasoning_effort`` means answers 400, and without
            #: this name that is a deployment losing every answer to a line that reads
            #: "provider unavailable" -- indistinguishable from the model being down. Checked
            #: after :func:`context_error_code` on purpose: a refusal that names both the window
            #: and a field belongs to the window, which has its own code and its own re-raise.
            #: The verdict below is untouched (offline reply, ``failed`` span, same evidence), so
            #: this adds a name, not a behaviour -- and it adds no fallback sentence either,
            #: which is the line app/agents/nodes.py:379-387 holds against masking.
            lever_code = lever_rejection_code(exc)
            if lever_code:
                record_budget_event("lever_rejected")
                logger.error(
                    budget_signal(
                        getattr(self.budget, "tier", None) or "analysis",
                        prompt_tokens=prompt_tokens,
                        read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                        stream=False,
                        code=lever_code,
                        **self._leg_fields(),
                    )
                    + f" [Model] 服务端拒收了关闭思考的请求字段，本次不发兜底文案冒充答案: {exc}"
               )
            from app.trace.spans import error_code_for

            timeout_code = model_timeout_code(exc)
            span.finish(
                "failed",
                error_code=timeout_code or error_code_for(exc),
                #: The name rides on the same span the failure already closed, so the trace
                #: export carries it and the verdict, the evidence bag, and the customer reply
                #: are exactly what they were before this line existed (R591 判据③: an
                #: observable failure, not a different one).
                summary={"lever_rejection_code": lever_code} if lever_code else None,
            )
            slot.release()
            if timeout_code:
                # R99: the expired clock used to be filed as ``internal_error`` and logged at
                # warning, which made a machine that is too slow for its own budget look like
                # a bug in the prompt. It is also the one failure this boundary answers with a
                # canned sentence, so the count is what tells an operator how many of
                # today's answers were not answers. The sentence itself stays: judgement 4 asks
                # for it to be loud, not for it to be gone.
                record_budget_event("timeout_offline_reply")
                logger.error(
                    budget_signal(
                        getattr(self.budget, "tier", None) or "analysis",
                        prompt_tokens=prompt_tokens,
                        read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                        stream=False,
                        code=timeout_code,
                        **self._verdict_fields(verdict),
                        **self._leg_fields(),
                    )
                    + f" [Model] provider 超时，改用离线回复（该回复不计为业务结论）: {exc}"
                )
            else:
                logger.warning(f"[Model] provider invoke 失败，使用离线回复: {exc}")
            reply = self._offline_fallback(messages, config=config, **kwargs)
            publish_formed_reply_for_call(config, reply, tap=tap)
            return reply
        slot.release()
        if tap is not None:
            delivered = tap.close()
            if delivered:
                logger.info(
                    f"[R203] leg={tap.worker} call={tap.call_id} 生成腿流式 pieces={delivered}"
                )
            else:
                formed = publish_formed_reply_for_call(config, response, tap=tap)
                if formed:
                    logger.info(
                        f"[R662] leg={tap.worker} call={tap.call_id} "
                        f"生成腿交回成形整段，按尺寸闸补逐片 pieces={formed}"
                    )
        from app.trace.spans import model_token_counts

        summary = dict(model_token_counts(response))
        empty_code = None
        if self.budget is not None:
            truncated = detect_output_truncation(response)
            summary["budget_tier"] = self.budget.tier.value
            #: R591: the leg, on the span as well as on the log line, because a trace export is
            #: what survives log rotation, and "which leg answered this" is a question about the
            #: round, not about the moment somebody happened to be tailing stdout.
            summary.update(self._leg_fields())
            if truncated:
                summary["truncation_code"] = truncated
                logger.warning(
                    budget_signal(
                        self.budget.tier,
                        prompt_tokens=prompt_tokens,
                        read_seconds=self.budget.timeout_seconds,
                        code=truncated,
                        **self._verdict_fields(verdict),
                        **self._leg_fields(),
                    )
                )
            empty_code = detect_empty_answer(response)
            if empty_code:
                # Measured, not theorised: on the shipping container qwen3.5:9b spends a
                # 1024-or-1536 token cap entirely on its hidden reasoning and hands back zero
                # visible characters with done_reason=length. An empty body that reaches the
                # client is a silent success, so the boundary records it as a failure with
                # the ratified code for "this round produced no conclusion" and refuses to
                # answer for the model. The response object still goes back unchanged -- what
                # changes is that it is no longer filed as a completed call.
                summary["empty_answer_code"] = empty_code
                record_budget_event("empty_answer_rejected")
                logger.error(
                    budget_signal(
                        self.budget.tier,
                        prompt_tokens=prompt_tokens,
                        read_seconds=self.budget.timeout_seconds,
                        stream=False,
                        code=empty_code,
                        **self._verdict_fields(verdict),
                        **self._leg_fields(),
                    )
                    + " [Model] 模型正文为空，不作为答案交付（同一行的 thinking= 说明这次到底有没有要求"
                    "关掉思考，no_think_fields= 说明请求体里真的带了哪几枚字段，transport= 说明是哪条腿"
                    "发的，max_tokens= 说明预算有多大；思考链吃满预算只是已测过的成因之一）"
                )
        span.finish(
            "failed" if empty_code else "completed",
            error_code=empty_code or "",
            summary=summary,
        )
        return response

    def stream(self, *args, **kwargs):
        """流式跑一发：预算、span、离线回退，外加 R31 的片段边界出口。

        这一枚边界把模型逐 token 吐的增量合并成判据②③ 合格的片，只送给**注册了 sink 的**
        调用方；没注册时一个字节都不变。今天生产图路径上根本走不到这里（
        ``stream_mode="values"`` 下 react agent 只调 ``invoke``），所以它是 R31 的上半场：
        规则先落地并钉住，下半场（生成腿改流式 + SSE 出口多发 ``text``）见交付说明。
        """
        from app.common.model_budget import ModelBudgetExhausted, default_model_budget

        config = kwargs.get("config")
        # A stream may be started positionally (LangGraph) or by keyword, so the prompt is
        # read either way: sizing it only when it arrived positionally would leave every
        # keyword-started stream unsized, which is the same blind spot as no budget at all.
        messages = args[0] if args else kwargs.get("messages")
        try:
            slot = default_model_budget().acquire(wait_seconds=self.capacity_wait_seconds)
        except ModelBudgetExhausted as exc:
            logger.warning("[Model] 本地模型并发预算耗尽，使用离线流")
            span = self._span(config, queue_wait_ms=exc.wait_ms)
            span.finish("rate_limited", error_code=exc.code)
            fallback = self._span(config, provider="offline", model_name="offline")
            try:
                for chunk in self.fallback.stream(*args, **kwargs):
                    fallback.mark_first_token()
                    yield chunk
            finally:
                fallback.finish("model_unavailable", error_code="model_unavailable")
            return

        # Every way out of this generator gives the slot back, and there are three: the
        # answer completed, the provider failed and got the offline answer, and the
        # consumer stopped reading. That last one is not an exception this body can catch
        # -- it is GeneratorExit raised at a yield -- so the release is one finally rather
        # than the call on each refusal path, which is all it used to be.
        # The same exit has to close the span as well, and R102 left that half undone.
        span = None
        try:
            span = self._span(config, queue_wait_ms=slot.wait_ms)
            prompt_tokens = self._wire_prompt_tokens(messages, kwargs)
            try:
                budget_kwargs, verdict = self._budget_kwargs(prompt_tokens, stream=True)
                kwargs = _with_boundary_fields({**budget_kwargs, **kwargs})
            except ModelContextLimitExceeded as exc:
                _log_context_refusal(self.budget, prompt_tokens)
                span.finish("failed", error_code=exc.code)
                raise
            visible_total = 0
            saw_tool_call = False
            piece_merger = StreamPieceMerger()
            try:
                for chunk in self.primary.stream(*args, **kwargs):
                    span.mark_first_token()
                    visible_total += len(answer_text(chunk))
                    saw_tool_call = saw_tool_call or produced_a_tool_call(chunk)
                    publish_stream_pieces(config, piece_merger.feed(visible_chunk_text(chunk)))
                    yield chunk
            except Exception as exc:
                provider_code = context_error_code(exc)
                if provider_code and self.budget is not None:
                    logger.warning(
                        budget_signal(
                            self.budget.tier,
                            prompt_tokens=prompt_tokens,
                            read_seconds=self.budget.timeout_seconds,
                            code=provider_code,
                            stream=True,
                        )
                    )
                    _harvest_runtime_window(exc)
                    _log_context_refusal(self.budget, prompt_tokens)
                    span.finish("failed", error_code=provider_code)
                    raise ModelContextLimitExceeded(self.budget, prompt_tokens or 0) from exc
                #: R591, same name as the :meth:`invoke` exit above: the streamed answer leg is
                #: the shape run16/run17 actually lost, so a server that refuses the lever has to
                #: say so here as well or the fix is only half observable.
                lever_code = lever_rejection_code(exc)
                if lever_code:
                    record_budget_event("lever_rejected")
                    logger.error(
                        budget_signal(
                            getattr(self.budget, "tier", None) or "analysis",
                            prompt_tokens=prompt_tokens,
                            read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                            stream=True,
                            code=lever_code,
                            **self._leg_fields(),
                        )
                        + f" [Model] 服务端拒收了关闭思考的请求字段，本次不发兜底文案冒充答案: {exc}"
                    )
                from app.trace.spans import error_code_for

                timeout_code = model_timeout_code(exc)
                span.finish(
                    "failed",
                    error_code=timeout_code or error_code_for(exc),
                    summary={"lever_rejection_code": lever_code} if lever_code else None,
                )
                if timeout_code:
                    record_budget_event("timeout_offline_reply")
                    logger.error(
                        budget_signal(
                            getattr(self.budget, "tier", None) or "analysis",
                            prompt_tokens=prompt_tokens,
                            read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                            stream=True,
                            code=timeout_code,
                            **self._verdict_fields(verdict),
                            **self._leg_fields(),
                        )
                        + f" [Model] provider 流式超时，改用离线流（该回复不计为业务结论）: {exc}"
                    )
                else:
                    logger.warning(f"[Model] provider stream 失败，使用离线流: {exc}")
                fallback = self._span(config, provider="offline", model_name="offline")
                try:
                    for chunk in self.fallback.stream(*args, **kwargs):
                        fallback.mark_first_token()
                        yield chunk
                finally:
                    fallback.finish("model_unavailable", error_code="model_unavailable")
                return
            if self.budget is not None and not saw_tool_call and not visible_total:
                # The same verdict a non-streaming call records, because a thinking model that
                # spends its cap on hidden tokens does it in both transports, and a stream that
                # delivered no characters is not an answer either. Nothing the caller received
                # changes: what changes is that the round is filed as a failure.
                record_budget_event("empty_answer_rejected")
                logger.error(
                    budget_signal(
                        self.budget.tier,
                        prompt_tokens=prompt_tokens,
                        read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                        stream=True,
                        code=NO_ANSWER_CODE,
                        **self._leg_fields(),
                    )
                    + " [Model] 流式正文为空，不作为答案交付（同一行的 thinking= 说明这次到底有没有要求"
                    "关掉思考，no_think_fields= 说明请求体里真的带了哪几枚字段，transport= 说明是哪条腿"
                    "发的；思考链吃满预算只是已测过的成因之一）"
                )
                span.finish("failed", error_code=NO_ANSWER_CODE)
                return
            # 末片只在真的跑完这一发时发：中途 provider 失败会改走离线流，
            # 把半截缓冲当成"答案的最后一块"推给出口，是判据③ 明确不许的那种冒充。
            publish_stream_pieces(config, piece_merger.finish())
            span.finish("completed")
        finally:
            slot.release()
            # Nothing above closed it, so this is the consumer throwing the stream away:
            # GeneratorExit walks past every except clause here, and an open span leaves
            # two marks, not one. Trace keeps a `model.started` that never pairs, and the
            # R51 stage ledger -- which is fed by finish() alone -- never sees the call,
            # so the slowest tail of the distribution (a user who stopped waiting) is
            # missing from the statistics rather than merely under-counted. Cancelling is
            # the caller's decision and not a model failure, so it closes as `cancelled`
            # and stays out of the evidence bag: the round is judged exactly as a round
            # that ran to the end would have been.
            if span is not None and not span.finished:
                span.finish("cancelled", record_evidence=False)


def _make_model(tier: ModelTier | str = DEFAULT_MODEL_TIER, *, prompt=None):
    """Build the model for one tier: an explicit output cap and a prompt-scaled clock.

    There is no ``timeout`` parameter any more, and that is the point. A bare scalar used to
    be handed to both ``ChatOpenAI`` and ``httpx.Client``, which made prefill and decode
    share one wall clock: the longer the prompt, the more likely the answer was cut off in
    the middle. ``prompt`` is the text or message list this instance is about to send, where
    the call site already knows it; when nobody passes it, the budget is sized for the
    tier's largest permitted prompt and every call is re-sized again in
    :meth:`_ResilientModel.invoke` from the messages actually on the wire.

    Building a model never refuses a request -- ``report_budget`` records the verdict for
    the prompt known here and :func:`authorize_call` is what declines to send, at the
    moment the real message list exists. A factory that threw because a *caller* asked for
    too much would turn one oversized question into a dead worker graph.
    """
    budget = model_tier_budget(tier)
    prompt_tokens = estimate_prompt_tokens(prompt)
    report_budget(budget, prompt_tokens, stream=False)
    settings = get_local_model_settings()
    if not settings.model_name:
        # No configured and no discovered model: report unavailability instead of
        # calling an invented model name that may not exist on this machine.
        logger.warning("[Model] 本机未配置也未发现可用对话模型，按模型不可用处理")
        return _OfflineModel()
    provider = "ollama" if ":11434" in settings.base_url else "local-openai-compatible"
    try:
        _log_thinking_mode(settings.base_url)
        _log_keep_alive_mode(settings.base_url)
        _log_context_pairing(settings.base_url, budget)
        client_timeout = http_timeout(budget, prompt_tokens)
        primary = ChatOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model_name,
            temperature=0,
            max_retries=0,
            timeout=client_timeout,
            http_client=httpx.Client(timeout=client_timeout, trust_env=False),
        )
        return _ResilientModel(
            primary,
            provider=provider,
            model_name=settings.model_name,
            budget=budget,
        )
    except Exception as exc:
        logger.warning(f"[Model] 回退到离线模式: {exc}")
        return _OfflineModel()


def _last_user(state) -> str:
    for m in reversed(state.get("messages", [])):
        if type(m).__name__ == "HumanMessage":
            return getattr(m, "content", "") or ""
    return ""


def _stage_account(config, *, stage, tier="", summary=None):
    """R688（判据①）：为没有自己的跨度的那一段产品码开一本五段事件账。

    懒导入的理由与 ``_ResilientModel._span`` 同一枚：路由不该依赖 trace 包，节点更不该
    因为记账失败而失败。config 里没有认证主体时一个字节都不写（``ExecutionSpan.active``
    是所有跨度共用的那条「无主不记」规矩），发点因此不需要任何新判断。段名只认
    ``app/common/stage_timing.py::CANONICAL_STAGES``，自造的段名在写入口就被拒。
    """
    from app.trace.spans import stage_account

    return stage_account(config, stage=stage, tier=tier, summary=summary)


# ==================== 意图分类（确定性，不调 LLM） ====================

_SMALLTALK = ["你好", "您好", "在吗", "谢谢", "感谢", "再见", "拜拜",
              "你是谁", "你叫什么", "hello", "hi", "早上好", "晚上好"]


def classify_intent(state, config=None) -> dict:
    """规则分类：chat(闲聊) / task(任务)。快、稳、可解释。"""
    # R688（判据①·生产发点）：规则分类这一段今天没有任何跨度（无 model、无 tool），端到端里它落在 gap_ms。一段一枚件：区间内不存在第二枚在册跨度，所以不可能与谁重复计数。
    with _stage_account(config, stage="classify", summary={"node": "classify_intent"}):
        q = _last_user(state).strip()
        ql = q.lower()
        if any(k in ql for k in _SMALLTALK) and len(q) <= 12:
            intent = "chat"
        else:
            intent = "task"
        logger.info(f"[Classify] '{q[:30]}' → {intent}")
        return {"intent": intent}


# ==================== R42 快慢判别器（规则优先，零模型调用） ====================
#
# 判据出处：docs/handoff/2026-09-15-backend-followup-requests.md §21 R42 —— 学 Glean 的
# Waldo，但**不再花一发模型**做判别；docs/handoff/2026-09-17-perf-architecture-plan.md
# §7 明确不做里点名"用模型做快慢判别"。所以这里全是字符串规则：判别路径上没有任何
# _make_model / .invoke / .stream / chat（判据①由 tests/test_r42_zero_model_calls.py 用
# 计数桩钉死）。
#
# 输出是"走哪条道 / 用哪个档"，不是再问一次模型：
# - LANE_QA       问答档：单轮检索就能答，不拆题、不进 pandas、不出图表。默认走这条。
# - LANE_ANALYSIS 分析档：命中算数、对比、趋势、图表或复合连接词 ⇒ 值得付拆题与 worker。
# - LANE_REPORT   报告档：命中导出/报告产物词 ⇒ 有副作用的一轮（export 走 HITL 挂起）。
# 档位形状接 R30：ModelTier 的枚举属于 app/agents/contracts.py，本单不修它，只在现有
# 档位里选道——多造一个没有调用点的档，tests/test_r30_model_tiers.py 会当场红。

#: 问答档：默认道，也是最便宜的道。
LANE_QA = "qa"
#: 分析档：需要算数/画图/拆题。
LANE_ANALYSIS = "analysis"
#: 报告档：产出文件，带副作用。
LANE_REPORT = "report"

#: 每条道用 R30 的哪个档出牌。报告档与分析档共用 ANALYSIS：四张 worker 子图在导入期
#: 就是按 ANALYSIS 装配的（app/agents/orchestrator.py 的 `doc_graph = create_react_agent(...)`
#: 那一组），本单不动那条装配，也不发明新档。
LANE_TIERS = {
    LANE_QA: ModelTier.CHAT,
    LANE_ANALYSIS: ModelTier.ANALYSIS,
    LANE_REPORT: ModelTier.ANALYSIS,
}

#: 产物词优先于一切：命中它就必须付重流程，后面再算都不认。
_REPORT_MARKERS = (
    "导出", "下载链接", "pdf", "word", "一页纸", "周报", "月报里", "复盘", "报告",
    "插进正文",
)

#: 制图动词：命中它就是"要一张图"，比任何口径词都硬（判据②的反向证据：
#: chart-04 同时带"统计口径"和"画……对比图"，必须由这条而不是口径条定档）。
#: 刻意不含裸"图表"——"图表数据来自哪里？"问的是来源，不是要图。
_ARTIFACT_MARKERS = (
    "画", "柱状图", "折线图", "饼图", "趋势图", "对比图", "可视化", "生成图",
)

#: 口径/定义题：问的是"按哪个口径、算哪个月、哪一版"，答案在知识库里，不在表格里。
#: 这类题不需要 pandas，也不需要拆题，是问答档的主力人群。
_DEFINITIONAL_MARKERS = (
    "口径", "是否包含", "是否计入", "按晚还是按天", "分母", "哪一版", "按什么时点",
    "怎么判定", "归口", "哪个月", "适用于",
)

#: 强复合连接词：一条问题里塞了两件独立的事 ⇒ 交给 plan 拆。刻意不含裸"和"
#: ——"餐费和住宿费的票能开在一张上吗"是一件事，为它花一发拆题模型正是 L0 要省的。
_COMPOUND_MARKERS = ("并且", "同时", "另外", "还有", "以及", "然后", "顺便")

#: 分析触发词：算数、排名、对比、趋势、异常。刻意不收裸"统计"——本语料里它是名词
#: （"代码量统计""按什么口径统计"）而不是动词，收进来会把定义题拖进分析档；
#: route_main 的 data_kw 仍带"统计"，真要算的那类题由既有兜底升档（判据②）。
_ANALYSIS_MARKERS = (
    "排名", "前五", "汇总", "合计", "总计", "平均", "最高", "最低", "差多少",
    "环比", "同比", "趋势", "对比", "比较", "相比", "总额", "除以", "异常",
    "超标率", "连续上升", "为什么涨", "变化", "计算", "哪些部门", "哪个部门",
    "重复提交", "重复的单据", "分布", "增长率", "占比", "明细表",
)


#: ⑤ 形状规则的两个词集（总控裁定："一句题里同时出现〔口径/归属词〕与〔取值动词〕
#: ⇒ 判分析档"）。闭集是刻意为窄的：命中一条不等于命中另一条就不算，
#: 任何一侧放宽都会把"制度里写着一个数"的正当快道题踢出去（doc-01 住宿费标准是多少？
#: 答案 500 元/晚——那是查出来的，不是算出来的）。
#:
#: 归属词闭集不收"哪个月"：metric-10/11「把这笔报销费用算进哪个月」问的是归属口径，
#: 总控点名这类是 lookup、快道答得对。
_CALIBER_MARKERS = ("口径", "分母", "时点", "归口")

#: 取值动词闭集：总控点名的十个词一个不少（是多少/算/合计/占比/环比/同比/趋势/
#: 排名/总额/平均），另补三个同族的硬算数词。刻意不收裸"多少"与"统计"——
#: "能报多少""按什么口径统计"都是问制度，不是要算。
_VALUE_VERB_MARKERS = (
    "是多少", "算", "合计", "占比", "环比", "同比", "趋势", "排名", "总额", "平均",
    "汇总", "除以", "变化",
)

#: R206a：口径题"知识库腿必须出门"的词集。刻意不新造第三张表——它就是上面两张
#: 已裁定闭集的并（⑤ 的归属词 ∪ 定义题词集）。两张表都已经为"这类题的答案在制度里、
#: 不在表格里"做过一次裁定（run6 前），再抄一遍只会漂。
#: 面向的是派工，不是档位：档位判别（classify_route）问"这一题要不要花重流程的钱"，
#: 本词集问"这一题的原文在不至少在知识库里"——metric-12「算人均产值用哪个分母」
#: 判到分析档是对的，但那一档里一条读腿都没有就是错的。
#: 闭集之外的裸"多少"/裸"统计"一律不收：那是问数，不是问口径（判据③）。
KB_CALIBER_MARKERS: tuple[str, ...] = tuple(dict.fromkeys(_CALIBER_MARKERS + _DEFINITIONAL_MARKERS))


@dataclass(frozen=True)
class RouteDecision:
    """一次判别的完整结果：走哪条道、用哪个档、被哪条规则定的。

    ``rule`` 与 ``matched`` 是判据④的抓手——每条规则都要能被摘掉并让对应用例变红，
    所以命中必须可指名道姓，不能只给一个 lane 字符串。
    """

    lane: str
    tier: ModelTier
    rule: str
    matched: tuple[str, ...] = ()


def _markers_hit(text: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(marker for marker in markers if marker in text)


def classify_route(question: str) -> RouteDecision:
    """规则判别：这条问题该走哪条道、用哪个档。纯函数，零模型调用。

    规则的**先后**就是裁定，摘掉任意一条都有用例变红（判据④）：
    产物词 > 制图词 > **⑤ 口径×取值动词** > 复合连接词 > 口径定义 > 算数词 > 默认问答档。

    ⑤ 排在口径定义条之前：同一句里"按哪个口径"和"算出多少"同时出现时，
    取值动词赢——判错方向必须是"多花钱"而不是"答错数"（总控 09-18 裁定）。

    判别的**偏向**是刻意的：宁可把重问题先判到问答档，也不为判别花一发模型。判错的
    代价有边界——reflect 的"要图没图/要导出没下载链接"与 route_main 的关键词兜底都还
    能把这一轮升回分析档（判据②：tests/test_r42_fallback_upgrade.py），而判别本身省的
    那发拆题模型是白赚的。
    """
    text = str(question or "").strip()
    decision = _route_rules(text)
    logger.info(
        f"[R42] '{text[:30]}' → lane={decision.lane} tier={decision.tier.value} "
        f"rule={decision.rule} hit={'/'.join(decision.matched) or '-'}"
    )
    return decision


def _route_rules(text: str) -> RouteDecision:
    """classify_route 的规则本体：只做字符串比对，一个字符都不碰模型。"""
    if not text:
        return RouteDecision(LANE_QA, LANE_TIERS[LANE_QA], "empty")
    lowered = text.lower()

    caliber = _markers_hit(text, _CALIBER_MARKERS)
    if caliber:
        # ⑤：口径/归属词与取值动词同现 ⇒ 这一题要的是**算出来的数**，不是定义。
        # 快道不许接（tests/test_r42_numeric_questions.py）。
        verbs = _markers_hit(text, _VALUE_VERB_MARKERS)
        if verbs:
            return RouteDecision(LANE_ANALYSIS, LANE_TIERS[LANE_ANALYSIS], "caliber_value", caliber + verbs)

    for rule, lane, markers in (
        ("report_marker", LANE_REPORT, _REPORT_MARKERS),
        ("artifact", LANE_ANALYSIS, _ARTIFACT_MARKERS),
        ("compound", LANE_ANALYSIS, _COMPOUND_MARKERS),
        ("definitional", LANE_QA, _DEFINITIONAL_MARKERS),
        ("analysis_marker", LANE_ANALYSIS, _ANALYSIS_MARKERS),
    ):
        matched = _markers_hit(lowered, markers)
        if matched:
            return RouteDecision(lane, LANE_TIERS[lane], rule, matched)
    return RouteDecision(LANE_QA, LANE_TIERS[LANE_QA], "default")


# ==================== R141 · 声明档位 → 真实路径差 ====================
#
# R42 交的是判别器（读题面猜一条道，判错有兜底与 reflect 往上抬），R32 交的是一枚取值闸
# （调用方写错档位当场 400）。两单之间缺了中间那一环：**显式声明**的档位除了决定进不进
# 可靠队列（chat._queue_lane），对图里到底派谁出门一个字都不影响。R32 因此拒交前端选择器
# ——「一枚点了没反应的控件比没有控件更糟」。本节把那一环补上，只有三条新事实：
#  ① 天花板 LANE_WORKERS：这一档最多允许哪几条工作腿；
#  ② 地板 LANE_REQUIRED_WORKERS：这一档缺了哪条腿就不算兑现承诺；
#  ③ 读数 TurnLane.as_dict()：本轮生效的是哪条道、它是"你选的"还是"系统判的"、
#     允许与要求各有哪些腿。同一份 as_dict 上到三处出口：HTTP 响应头、
#     canonical 的 request.started 帧、trace 的 request.started 载荷。
#     判据① 要的是**读数**，不是文档里的一段散文。
#
# 🔴 天花板与地板**只作用在 source == LANE_SOURCE_EXPLICIT 上**，一条都不许漏给 R42 判出
# 的道。这不是保守，是已并树的裁定：tests/test_r42_fallback_upgrade.py 钉着"route_main 的
# 关键词兜底与 reflect 仍能把 rules 判出的问答档升回分析档"。拿同一张天花板去压 rules-qa，
# 那条升档道今天就红。
#
# 未声明（lane 缺省或空串）时本节四个函数一个都不改派、一个都不加日志，图的形状与 R141
# 之前逐字节相同 —— 判据④ 那句"阶段 A 的问答档口径今天不可比风险为零"靠的就是这一条。

#: 显式档位进入图内的通道：``config["configurable"]`` 里的键名。
#:
#: 走 configurable 而不是走 state，理由与 ``cancel_event``、``STREAM_PIECE_SINK_KEY``
#: 逐字相同（见 app/agents/orchestrator.py::run_with_stream 那段注释）：state 要被
#: checkpointer 序列化，PG 路径下多塞一个键就是把面扩到别人的写域里去了。
DECLARED_LANE_KEY = "declared_lane"

#: ``lane_source`` 读数取值的全集（判据②：四态两两可分辨，而"未知值"**不在**这张表里 ——
#: 它在 HTTP 边界上被 _require_valid_lane 400，在图内被 normalize_declared_lane 当场炸）。
#: 前两态回答"这一轮按谁的判断走"，后两态回答"这一轮压根没按任何档位走，为什么"。
#: - r42         调用方没声明，本轮的道是 R42 判别器按题面判的（R141 之前唯一存在的一种）。
#: - explicit    调用方显式声明，本节真的按它改派了腿。
#: - not_routed  本轮根本没进图（入队 / 答案缓存命中）：档位没有参与路径。
#:               诚实说"没参与"比假装生效值钱，那正是判据② 严禁的第三张脸。
LANE_SOURCE_R42 = "r42"
LANE_SOURCE_EXPLICIT = "explicit"
LANE_SOURCE_NOT_ROUTED = "not_routed"
#: - resumed     批准后从挂起点续跑的那一轮：图**在跑**，而这一轮的档不是本轮定的。
#:               R172 起，挂起前那一轮声明的档位随 pending_approvals 的挂起行跨过 HITL
#:               那道门一起读回来，住在 declared_lane 那一格；把这一格读成 r42 或
#:               not_routed 都是撒谎，读成 explicit 更是（本轮没有现声明，续跑这条腿也
#:               没按这一档重新派发过 —— 那要跨 checkpointer 与 orchestrator，仍在写域外）。
#:               挂起行里没有这一格时（R172 之前挂起的旧行、0008 尚无此列的 PG 后端）
#:               declared_lane 落空串，读数与 R172 之前逐字节相同：缺口照旧可数，不遮丑。
LANE_SOURCE_RESUMED = "resumed"

#: 图里真实存在的四条工作腿。顺序就是阅读与派发的顺序，不是集合：读数要能逐字比对。
#: 出处是 app/agents/orchestrator.py 的 add_node 装配与 route_main 里的 valid。
WORK_LEGS: tuple[str, ...] = ("doc", "data", "chart", "export")

#: approval 不是工作腿而是批准闸（工具层要人工确认时才挂它）。把它关进天花板，等于
#: "选了问答档 ⇒ 待确认卡凭空消失"：那是减一道安全门，不是省算力，故无条件放行。
LANE_EXEMPT_WORKERS: tuple[str, ...] = ("approval",)

#: 天花板：这一档允许出现的工作腿。阶梯是**单调包含**的（qa ⊂ analysis ⊂ report），
#: 往便宜档选 = 少付；每一档都含 doc = 最便宜的那条读腿，任何档都不许把人家的文件
#: 库看没了。qa 只给 doc：不拆题、不进 pandas、不出图、不产文件，这就是问答档的承诺。
LANE_WORKERS: dict[str, tuple[str, ...]] = {
    LANE_QA: ("doc",),
    LANE_ANALYSIS: ("doc", "data", "chart"),
    LANE_REPORT: ("doc", "data", "chart", "export"),
}

#: 地板：``(worker, 条件名)``。只有天花板会退化成"点了没反应的控件"——题目里没写"导出"
#: 二字时 supervisor 本就不排 export，用户显式选了报告档却什么都没多出来，那一格就是
#: R32 拒交的那张脸。地板只在 explicit 生效，条件三条见 _FLOOR_CONDITIONS。
LANE_REQUIRED_WORKERS: dict[str, tuple[tuple[str, str], ...]] = {
    LANE_QA: (("doc", "abstained"),),
    LANE_ANALYSIS: (("data", "has_data"),),
    LANE_REPORT: (("export", "always"), ("data", "has_data")),
}

#: 地板条件的全部取值（写错就当场炸，不许静默不补腿）：
#: - always     无条件补。选了报告档就得真出产物腿；export 带 HITL 挂起，那正是它的脸。
#: - has_data   本轮带了 data_filename 才补。没料硬派 pandas 是编造数字，不是分流。
#: - abstained  supervisor 既没派发也没给正文时才补一条读腿。触发条件与 R42 那句
#:              "[R42] 弃权轮判为问答档 → 补派 doc，不再空转一轮" 同一条：省的是空转，
#:              不是在已经答完的轮上多花一发模型。
_FLOOR_CONDITIONS = ("always", "has_data", "abstained")

#: 天花板把腿砍到零时的退路 = 这一档最小可兑现的一条读腿。砍到零不等于"这档什么都不做"：
#: route_main 会在 workers 为空时 return "reflect"，reflect 判 redo，再烧一发 supervisor，
#  恰恰是 R42 花力气省掉的那种空转轮。
LANE_PRIMARY_LEG = "doc"


@dataclass(frozen=True)
class TurnLane:
    """一轮的档位读数：生效道、它的来源、它的腿边界、它要不要付拆题。

    字段就是判据① 的读数，``as_dict`` 是三处出口共用的那一份身体。``rule`` 与
    ``rules_lane`` 保留 R42 判别器的原始裁定：声明与判别不一致时（用户选了问答档、
    题面却带"环比"），两个都必须能读回来，否则界面上"你选的"三个字没有对账依据。
    """

    lane: str
    source: str
    rule: str
    declared: str
    rules_lane: str
    tier: str
    allowed_workers: tuple[str, ...]
    required_workers: tuple[tuple[str, str], ...]
    may_plan: bool

    def as_dict(self) -> dict:
        """JSON-safe 出口：trace 载荷与 SSE 帧都只认这一条，别在下游再换算一遍。"""
        return {
            "lane": self.lane,
            "lane_source": self.source,
            "lane_rule": self.rule,
            "declared_lane": self.declared,
            "rules_lane": self.rules_lane,
            "tier": self.tier,
            "allowed_workers": list(self.allowed_workers),
            "required_workers": [[worker, condition] for worker, condition in self.required_workers],
            "may_plan": self.may_plan,
        }


def normalize_declared_lane(declared) -> str:
    """把"声明的档位"归一成三值之一或空串，未知值**硬失败**。

    HTTP 边界上 _require_valid_lane 已经 400 过一遍，这一道管的是图内与以后所有调用方：
    把 REPORT / repot 这类拼错的名字静默当成"没声明"，就是把判据② 严禁的第三态从后门
    放回来 —— 而且放回的是最贵的一种：调用方以为选了档，路径照旧。
    """
    text = str(declared or "").strip()
    if not text:
        return ""
    if text not in LANE_TIERS:
        allowed = ", ".join(f"'{value}'" for value in LANE_TIERS)
        raise ValueError(f"unknown declared lane {text!r}; declare one of {allowed} or nothing")
    return text


def turn_lane_from_decision(decision: RouteDecision, declared=None) -> TurnLane:
    """把 R42 的判别结果与调用方的声明合成本轮读数。纯函数，零日志，零模型调用。"""
    declared = normalize_declared_lane(declared)
    if not declared:
        # 没声明 ⇒ 生效道就是判别器判的那条。天花板给满、地板给空，于是 decide_workers
        # 在这一条道上必然原样返回；lane_source 那格明写 r42，与 explicit 永远可分辨。
        return TurnLane(
            lane=decision.lane,
            source=LANE_SOURCE_R42,
            rule=decision.rule,
            declared="",
            rules_lane=decision.lane,
            tier=decision.tier.value,
            allowed_workers=WORK_LEGS + LANE_EXEMPT_WORKERS,
            required_workers=(),
            may_plan=decision.lane != LANE_QA,
        )
    return TurnLane(
        lane=declared,
        source=LANE_SOURCE_EXPLICIT,
        rule=decision.rule,
        declared=declared,
        rules_lane=decision.lane,
        tier=LANE_TIERS[declared].value,
        allowed_workers=LANE_WORKERS[declared] + LANE_EXEMPT_WORKERS,
        required_workers=LANE_REQUIRED_WORKERS[declared],
        may_plan=declared != LANE_QA,
    )


def resolve_turn_lane(question: str, declared=None) -> TurnLane:
    """按题面与声明算出本轮读数。

    🔴 刻意调 _route_rules 而不是 classify_route：那行 ``[R42]`` 日志是 R51 读表的锚点，
    app/common/stage_timing.py::R42_LOG_PATTERN 逐字节钉着它的形状，它的**频次**同样是
    口径的一部分（一次运行敲几次钟）。锚点仍归 classify_route 在 plan() 里敲，本函数只
    借规则本体，不重复敲钟。
    """
    return turn_lane_from_decision(_route_rules(str(question or "").strip()), declared)


def declared_lane_from_config(config) -> str:
    """读本轮声明。没走 run_with_stream 的调用（含全部单参数直调）自然拿到空串。"""
    configurable = (config or {}).get("configurable") or {}
    return str(configurable.get(DECLARED_LANE_KEY) or "")


def not_routed_lane(declared=None) -> TurnLane:
    """本轮没进图（入队 / 答案缓存命中）时的诚实读数。

    lane 读空串而不是把声明抄进 lane 那格：选了报告档而这一轮被入队，此刻"报告档生效"
    还没有任何证据，有证据的是"它被排队后台跑"（载荷里的 lane 就是给 worker 的交代）。
    声明本身留在 declared 那格，两件事不混。
    """
    declared = normalize_declared_lane(declared)
    return TurnLane(
        lane="",
        source=LANE_SOURCE_NOT_ROUTED,
        rule="",
        declared=declared,
        rules_lane="",
        tier="",
        allowed_workers=(),
        required_workers=(),
        may_plan=False,
    )


def resumed_lane(declared=None) -> TurnLane:
    """批准后续跑那一轮的读数：图在跑，档位是挂起前那一轮定的（R172 才读得回来）。

    与 not_routed 同构（lane 读空串、不付拆题、不声称任何腿边界），区别只在 source 那一格：
    这一轮确实进了图。declared 那一格装的是随挂起行跨过 HITL 读回来的原始声明，读不到时
    是空串 —— 与 R172 之前逐字节相同。填不填得上都不许动 lane：续跑的腿没有按这一档重新
    派发过，把承诺写进生效格就是判据② 严禁的那张脸。声明与"这一轮沿用它"是两句话，
    分别住在 declared_lane 与 lane_source 两格里，谁也不许并谁的格。
    """
    declared = normalize_declared_lane(declared)
    return TurnLane(
        lane="",
        source=LANE_SOURCE_RESUMED,
        rule="",
        declared=declared,
        rules_lane="",
        tier="",
        allowed_workers=(),
        required_workers=(),
        may_plan=False,
    )


def decide_workers(turn: TurnLane, workers, *, has_data: bool = False, abstained: bool = False):
    """按本轮读数改派工作腿，返回 ``(改派后, 被砍的腿, 被补的腿)``。

    后两组是判据① 要的"那条分支"：选了 A 少跑哪条腿、选了 B 多跑哪条腿，全部具名。
    source 不是 explicit 就一个字符都不动 —— 判据② 的"缺省与显式可分辨"在行为上的
    那一半就是这一句，读数那一半在 as_dict 里。
    """
    given = [str(worker) for worker in (workers or [])]
    if turn.source != LANE_SOURCE_EXPLICIT:
        return tuple(given), (), ()
    allowed = set(turn.allowed_workers)
    kept = [worker for worker in given if worker in allowed]
    cut = [worker for worker in given if worker not in allowed]
    added: list[str] = []
    if cut and not kept:
        kept.append(LANE_PRIMARY_LEG)
        added.append(LANE_PRIMARY_LEG)
    for worker, condition in turn.required_workers:
        if condition not in _FLOOR_CONDITIONS:
            raise ValueError(f"unknown floor condition {condition!r} for lane {turn.lane!r}")
        if condition == "has_data" and not has_data:
            continue
        if condition == "abstained" and not abstained:
            continue
        if worker not in kept:
            kept.append(worker)
            added.append(worker)
    return tuple(kept), tuple(cut), tuple(added)


def respond(state, config=None) -> dict:
    """闲聊直接回答，不走 worker"""
    # R688（判据①·生产发点）：闲聊作答腿与 plan 同形：模型调用不带 config ⇒ 今天不发 model 跨度，generate 段在 a1 车道整条缺账。这枚件补的就是那一格；不带 config 的那一发一字不动，免得同一段区间被两枚件重复计数（那是 <1% 加总判据的死法）。
    with _stage_account(config, stage="generate", tier="chat", summary={"node": "respond"}):
        q = _last_user(state)
        try:
            resp = _make_model(ModelTier.CHAT, prompt=q).invoke([HumanMessage(content=q)])
            text = resp.content or "你好，我是企业智脑，可以帮你查文档、分析数据、画图、导出报告。"
        except Exception:
            text = "你好，我是企业智脑，可以帮你查文档、分析数据、画图、导出报告。"
        return {"final_answer": text, "messages": [AIMessage(content=text)]}


# ==================== 记忆加载 ====================

def _memory_user_id(state) -> str:
    principal = state.get("principal")
    if isinstance(principal, dict):
        principal_user_id = principal.get("user_id")
    else:
        principal_user_id = getattr(principal, "user_id", None)
    return str(principal_user_id or state.get("user_id") or "").strip()


def _authoritative_department(state) -> str:
    """R296：画像与 prompt 里的部门只认 ``users`` 那一行。

    ``AgentState``（``app/agents/state.py``）里并没有 ``department`` 这一格，所以
    ``state.get("department")`` 恒为空：过去 prompt 里那一行 ``department:`` 实际只剩
    ``user_profiles`` 那列员工自助可写的遗留值。这里改成现取 ``users``；读不到（库不通、账号不在）
    才退回请求进来时那份 Principal 快照——快照同样是 ``users`` 那一行的投影。

    它只喂画像块的标注与 prompt 拼接。授权判定从来不看画像，本函数不参与任何范围计算。
    """
    principal = state.get("principal")
    if isinstance(principal, dict):
        username = str(principal.get("username") or "").strip()
        snapshot = str(principal.get("department") or "")
    else:
        username = str(getattr(principal, "username", "") or "").strip()
        snapshot = str(getattr(principal, "department", "") or "")
    if not username:
        return snapshot
    try:
        from app.common import auth

        row = auth.get_user(username)
    except Exception as exc:
        logger.warning(f"[LoadMemory] users lookup skipped: {exc}")
        return snapshot
    if not row:
        return snapshot
    return str(row.get("department") or "")


def load_memory(state) -> dict:
    """召回长期记忆注入 state"""
    user_id = _memory_user_id(state)
    if not user_id:
        logger.warning("[LoadMemory] skipped because the request has no authenticated identity")
        return {
            "memory": {
                "long": [],
                "work": [],
                "profile": {},
                "profile_context": "",
            },
            "memory_error": "authorization_required",
        }
    q = _last_user(state)
    long_mem = recall(user_id, q, k=3) if q else []
    profile = get_profile(
        user_id,
        fallback={
            "department": _authoritative_department(state),
            "role": state.get("role") or "",
        },
    )
    profile_context = compose_profile_context(profile)
    logger.info(f"[LoadMemory] user={user_id} 召回 {len(long_mem)} 条")
    return {"memory": {"long": long_mem, "work": [], "profile": profile, "profile_context": profile_context}}


# ==================== 任务规划（仅复杂问题） ====================

_COMPLEX = ["和", "并且", "同时", "另外", "还有", "以及", "然后"]


def plan(state, config=None) -> dict:
    """复杂问题拆子任务；简单问题返回空列表

    ``config`` 只用来读 R141 的声明档位（``configurable["declared_lane"]``）。不传
    时与 R141 之前逐字节相同：单参数直调它的 tests/test_r42_zero_model_calls.py
    两枚用例都不必改口。
    """
    # R688（判据①·生产发点）：这一腿里模型调用不带 config（在册 identityless 钉守着，本单不碰它），所以今天连 model 跨度都不发；这一段的时间由下面这枚 stage 件交出。config 只用于取记账身份，不参与路由，也不参与 R42 的零模型判据。
    with _stage_account(config, stage="classify", tier="plan", summary={"node": "plan"}):
        q = _last_user(state)
        deterministic_plan = build_task_plan(q)
        if deterministic_plan:
            logger.info(f"[Plan] deterministic tasks={len(deterministic_plan)}")
            return {"plan": deterministic_plan}
        decision = classify_route(q)
        turn = turn_lane_from_decision(decision, declared_lane_from_config(config))
        if not turn.may_plan:
            # R42 判别器判到问答档 ⇒ 这一发拆题模型不付。判错了有边界：route_main 的
            # 关键词兜底与 reflect 的"要图没图/要导出没下载链接"仍能把这一轮升回分析档
            # （判据②），而省下的这一发是真的会打顶的：docs/perf/latency-budget-2026-09-16.md
            # 记的同日 21:50 那次冷启动，`[Plan]` 之后连吃 5 发 60 s 超时、整轮 302 s，
            # 最后只交付一句兜底文案。
            logger.info("[Plan] 问答档 → 不拆题")
            return {"plan": []}
        if not any(k in q for k in _COMPLEX):
            return {"plan": []}
        prompt = (
            "把下面的复合问题拆成 2-4 个独立子任务，返回 JSON 数组（只输出数组）：\n"
            f"{q}"
        )
        try:
            import json
            resp = _make_model(ModelTier.PLAN, prompt=prompt).invoke([HumanMessage(content=prompt)])
            arr = json.loads(str(resp.content).strip().removeprefix("```json").removesuffix("```"))
            plan_list = arr if isinstance(arr, list) else []
        except Exception as e:
            logger.warning(f"[Plan] 拆解失败: {e}")
            plan_list = []
        logger.info(f"[Plan] {len(plan_list)} 个子任务")
        return {"plan": plan_list}


# ==================== 反思 ====================

def reflect_node(state, config=None) -> dict:
    """检查最终回答质量，决定重派(redo)或放行"""
    # R688（判据①·生产发点）：复审是纯规则过：五段里 reflect 今天全线不产账（真窗 105/105 缺这一段），因为这条腿根本没有插桩点。写入口见 app/trace/spans.py::record_stage_event。
    with _stage_account(config, stage="reflect", summary={"node": "reflect_node"}):
        q = _last_user(state)
        review_result = None
        retry_count = state.get("retry_count", 0)
        raw_results = state.get("agent_results") or {}
        if raw_results:
            structured_results = []
            for worker, raw in raw_results.items():
                try:
                    if isinstance(raw, AgentResult):
                        structured_results.append(raw)
                    else:
                        payload = dict(raw)
                        payload.setdefault("worker", worker)
                        structured_results.append(AgentResult.model_validate(payload))
                except Exception as exc:
                    logger.warning(f"[Reflect] 忽略无效 Agent 结果 {worker}: {exc}")
            if structured_results:
                review = review_agent_results(structured_results)
                review_result = review.model_dump()
        final = str(state.get("final_answer") or "").strip()
        if not final:
            delivered = [
                str(value).strip()
                for value in (state.get("worker_results") or {}).values()
                if str(value or "").strip()
            ]
            final = "\n\n".join(delivered)
        if not final:
            for m in reversed(state.get("messages", [])):
                if type(m).__name__ == "AIMessage" and getattr(m, "content", "") and not getattr(m, "tool_calls", None):
                    final = m.content
                    break

        redo = False
        if review_result and not review_result["passed"] and retry_count < 1:
            redo = True
            retry_count += 1
        if not final or len(final) < 5:
            redo = True
        elif any(bad in final for bad in ["失败", "错误", "无法", "抱歉"]):
            redo = True
        elif any(k in q for k in ["图", "图表", "柱状", "折线", "饼图"]) and "![" not in final:
            redo = True   # 要图却没图
        elif any(k in q for k in ["导出", "报告", "PDF", "pdf"]) and "下载" not in final:
            redo = True   # 要导出却没下载链接

        count = state.get("reflect_count", 0) + (1 if redo else 0)
        logger.info(f"[Reflect] redo={redo} count={count}")
        update = {
            "redo": redo,
            "reflect_count": count,
            "retry_count": retry_count,
        }
        if review_result is not None:
            update["review_result"] = review_result
        return update


def route_reflect(state) -> str:
    """redo 且未超重派上限 → 回 supervisor；否则 → synthesize"""
    if state.get("redo") and state.get("reflect_count", 0) <= 1:
        return "supervisor"
    return "synthesize"


# ==================== 汇总 + 沉淀 ====================

#: 这一腿的账进日志时用的标记：run7 窗内要能 grep 出"哪一题被守卫带进了原话"，
#: 也要能反证守卫一次没开口时确实没开口。
CALIBER_QUOTE_MARKER = "[CaliberQuote]"

# ==================== R216：互斥口径的择边（特例压过一般条款） ====================
#
# A④ 判据④ 五分类的第 4 格（`docs/testing/a4-metric-conflict-attribution-2026-09-24.md` §5）：
# 被引证的登记料里**同时**躺着一条一般条款和一条只管某个范围的特例条款，特例条款的登记原文
# 自己就把那个范围让给了别条（``… 销售部的签约统计另按 cp-03 销售部一侧执行。``）。模型两条
# 都抄了，结论段却按一般条款作答 ⇒ 答反了。R206a 治派工、R206b 治逐字保真，两枚都不治这一格。
#
# 🔴 与邻单的两道边界写在这里不是装饰，是收口的把手：
#   * 本腿**不补召回**：特例那一行没被引证到上下文时它必须闭嘴（那格账在装箱/切读那边）；
#   * 本腿**不逐字保真**：它只判"哪一侧算本题结论"，逐字引证是 R206b 的活，两枚的收益不许互记；
#   * 本腿只追加、不改写，落点抄 ``_carry_caliber_quotes``，为的是 R203 那条"已发帧仍是终答前缀"。

#: 台账标记：run7 窗内要能 grep 出"哪一题被择边腿判过边"。
CLAUSE_SIDE_MARKER = "[ClauseSide]"

#: 追加段落的标题。这一段不是模型的话，是登记表自己的排序规则，标题里写明依据来自条号。
CLAUSE_SIDE_LABEL = "口径择边（本题按题面点名的那一侧作答）"

#: 条号形状。与 R206b 同一把尺：只认带条号的登记行——散文不是「登记」，把任意一段话当条款
#: 就会让本腿退化成第二个复读机（R206 交回里明写的边界）。
_CLAUSE_CODE = r"[A-Za-z]{1,6}-\d{1,4}"
_CLAUSE_CODE_AT_LINE_START = re.compile(r"^\s*\|?\s*(" + _CLAUSE_CODE + r")\s*\|")
_CLAUSE_CODE_IN_TEXT = re.compile(_CLAUSE_CODE)

#: 一条登记行里能当「适用范围」的格子最长多长。超过它就不是范围名而是口径正文本身，
#: 拿口径正文去题面里找子串会把每一条都判成"被点名"。
CLAUSE_SCOPE_MAX_CHARS = 12

#: 登记行里那些**讲出处而不是讲范围**的格子（``本表 cp-03`` / ``《费用报销管理制度》`` / ``V1.0``）。
#: 这一格是表格的"依据/版本"列，形状上是"前缀词 + 引用体"或版本号，不是部门名也不是事项名；
#: 不收掉它，"依据 cp-03"这种格子会被当成范围名拿去题面里找子串。
_CLAUSE_PROVENANCE_CELL = re.compile(r"^(本表|依据|来源|版本|生效|V\d|v\d|《)")

#: 赢家至少要比第二名多命中几枚双字组才敢定"题面点的是它"。这枚余量不是风格问题：并列时
#: 本腿必须闭嘴（判据③——不涉及冲突的族一个字都不许变）。重合度沿用 R206b 那一枚尺。
CLAUSE_SIDE_MIN_MARGIN = 2


def _caliber_clause_rows(fragments) -> list:
    """把被引证的**登记行**摊成条款：``[{"code","payload","scopes","line","source"}]``。

    行还是 R206b 那把尺挑出来的（``caliber_candidate_lines``：条号开头、整行、没被裁断），本函数
    只多做一件结构分析：一行表格里有三种格子——条号、口径正文、范围名。切法不按列号，因为
    cp 表与 t 表列数不同；按「最长格是正文、其余短格是范围」切，两张表都成立。
    """
    from app.rag.retrieval_pipeline import caliber_candidate_lines

    rows = []
    for fragment in fragments or []:
        text = str((fragment or {}).get("text") or "")
        source = str((fragment or {}).get("source") or "")
        for line in caliber_candidate_lines(text):
            started = _CLAUSE_CODE_AT_LINE_START.match(line)
            if not started:
                continue
            cells = [cell for cell in (item.strip() for item in line.strip().strip("|").split("|")) if cell]
            body = cells[1:]
            if not body:
                continue
            payload = max(body, key=len)
            scopes = [
                cell for cell in body
                if cell != payload
                and len(cell) <= CLAUSE_SCOPE_MAX_CHARS
                and not _CLAUSE_PROVENANCE_CELL.match(cell)
            ]
            rows.append({
                "code": started.group(1),
                "payload": payload,
                "scopes": scopes,
                "line": line,
                "source": source,
            })
    return rows


def _clause_named_rows(rows, question: str) -> list:
    """哪些登记行的**范围格整格出现在题面里**，按与题面的重合度从高到低排。

    「点名」只看一件事：范围名本身是从被引证的登记行里读出来的，不是本腿带来的词表——换一份
    制度文件、换一批部门、换一种问法，这一格跟着材料走（判据②：不许出现题目关键词硬编码）。
    """
    from app.rag.retrieval_pipeline import caliber_match_score, caliber_question_bigrams

    bigrams = caliber_question_bigrams(question)
    if not bigrams:
        return []
    named = []
    for row in rows:
        hit = [scope for scope in row["scopes"] if scope and scope in str(question or "")]
        if not hit:
            continue
        named.append((caliber_match_score(row["line"], bigrams), row, hit))
    named.sort(key=lambda item: item[0], reverse=True)
    return named


def _clause_rows_citing(rows, code: str, question: str) -> list:
    """正文里**显式指向**某个条号、而自己没有范围被题面点名的那些登记行。

    只认条号字面（``… 另按 cp-03 销售部一侧执行`` 里的 ``cp-03``）：这是登记表自己写明的引用
    关系（§三.3 要求被引用时给出条号），不是本腿发明的语义匹配。排除"自己也被点名"的行，
    否则两枚同族特例会互相指认，一般条款就无处可寻。
    """
    citing = []
    for row in rows:
        if row["code"] == code:
            continue
        if code not in _CLAUSE_CODE_IN_TEXT.findall(row["payload"]):
            continue
        if any(scope in str(question or "") for scope in row["scopes"]):
            continue
        citing.append(row)
    return citing


def select_caliber_side(fragments, question: str):
    """判出本题的「特例侧 / 让位的一般侧 / 并列对侧」；够不上形状就交回 ``None``。

    三件事必须同时成立，缺一枚本腿都不开口（每一枚都对着判据③ 要求一字不变的一族形状）：

    1. 有一枚登记行的**范围格被题面点名**，且它与题面的重合度**明显**赢过第二名；
    2. 另有一枚登记行在自己的正文里**指向**赢家那个条号 ⇒ 一般条款自己就写明了不适用于那个范围；
    3. 特例那一行确实在被引证的料里（枚 1 与枚 2 都只看引证料，本腿不补召回）。
    """
    rows = _caliber_clause_rows(fragments)
    if len(rows) < 2:
        return None
    named = _clause_named_rows(rows, question)
    if not named:
        return None
    top_score, special, scopes = named[0]
    if len(named) > 1 and top_score - named[1][0] < CLAUSE_SIDE_MIN_MARGIN:
        return None
    general = _clause_rows_citing(rows, special["code"], question)
    if not general:
        return None
    peers = [row for row in rows if row["code"] == special["code"] and row is not special]
    return {"special": special, "general": general, "peers": peers, "scopes": scopes}


def render_caliber_side(decision, model_answer: str) -> str:
    """把择边的结论写成正文末尾那一段；结论本来就站在对侧时交回空串。

    🔴 每一句口径都是登记行里的原格子，本函数一个字都不重写：它只决定"哪一句是本题结论"。

    ``model_answer`` 喂的是**模型自己写的那一份**，不是逐字保真腿补写之后的那一份：判"边有没有
    选错"问的是模型说了什么。拿补写后的正文去判，R206b 带进来的那句原话会冒充"模型已经选对了"，
    两枚守卫就会互相把对方的活记到自己账上（判据① 那条纪律要挡的正是这个）。
    """
    if not decision:
        return ""
    special = decision["special"]
    payload = special["payload"]
    if payload and payload in str(model_answer or ""):
        # 模型已经按特例侧作答 ⇒ 没有边选错，本腿一个字都不许多说。
        return ""
    scope = "／".join(decision["scopes"])
    lines = [f"### {CLAUSE_SIDE_LABEL}", "", f"- 本题结论（特例 {special['code']}·{scope}）：{payload}"]
    for row in decision["general"]:
        lines.append(
            f"- 不适用本题的一般条款 {row['code']}：其登记原文已把{scope}指向 {special['code']}，"
            f"不得拿它当{scope}的结论。"
        )
    for row in decision["peers"]:
        other = "／".join(item for item in row["scopes"] if item not in special["scopes"]) or row["code"]
        lines.append(f"- 并列对侧（{other}）：{row['payload']}")
    basis = f"（依据条号 {special['code']}；来源 {special['source']}）"
    lines.append(basis if special["source"] else f"（依据条号 {special['code']}）")
    return "\n".join(lines)


def _apply_caliber_side(state, question: str, final: str, worker_results: dict,
                        model_answer: str = ""):
    """择边腿的落地：只往**最后**那条有字的腿上追加，并整张交回 ``worker_results``。

    追加位置与交回形状两件事都抄 ``_carry_caliber_quotes`` 的三条约束，理由同一条：收端拿
    ``"\\n\\n".join(worker_results.values())`` 当终答正文，而流式那一边要求已发的帧仍是终答前缀。
    """
    decision = select_caliber_side(_cited_caliber_fragments(state), question)
    block = render_caliber_side(decision, model_answer or final)
    if not block:
        return final, None

    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + "\n\n" + block
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + "\n\n" + block
    logger.info(
        f"{CLAUSE_SIDE_MARKER} special={decision['special']['code']} scopes={decision['scopes']} "
        f"general={[row['code'] for row in decision['general']]} peers={len(decision['peers'])} "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


def _cited_caliber_fragments(state) -> list[dict]:
    """本轮**模型真读到过**的那些片段，按引证顺序交回 ``[{"text", "source"}]``。

    读的是 ``agent_results[*].evidence``——那是工具边界在装箱**之后**记下的账（R112/R36：
    装进 prompt 的才算被引证，装不下的不许报出处），不是从答案文字里反推的。只认过了权限、
    ``provenance_status=verified`` 的那几枚：守卫的产物是要进客户看到的正文的，它的每一行
    都必须能在真出处里逐字找到，所以这里不但不许编，也不许把没核过的行当原文抬。
    """
    fragments: list[dict] = []
    for raw in (state.get("agent_results") or {}).values():
        if isinstance(raw, dict):
            evidence = raw.get("evidence") or []
        else:
            evidence = getattr(raw, "evidence", None) or []
        for item in evidence:
            if isinstance(item, dict):
                row = item
            elif hasattr(item, "model_dump"):
                row = item.model_dump()
            else:
                continue
            if not isinstance(row, dict):
                continue
            if str(row.get("provenance_status") or "") != "verified":
                continue
            if row.get("permission_checked") is not True:
                continue
            excerpt = str(row.get("excerpt") or "")
            if not excerpt.strip():
                continue
            fragments.append({"text": excerpt, "source": str(row.get("source_name") or "")})
    return fragments


def _carry_caliber_quotes(state, question: str, final: str, worker_results: dict):
    """把本题那句**登记口径原话**逐字带进正文；正文里已经有的，一个字都不动。

    三条形状约束，每条都不是审美：

    1. **只追加、不改写**。正文是模型写的，守卫没有资格替它重说话；而 R203 的流式帧要求
       每一枚帧都是终答的前缀——只有往末尾加能同时满足"不替模型说话"和"帧仍是前缀"。
       所以追加落在 ``worker_results`` 里**最后**那一条腿上：收端 ``_select_final_answer``
       交出去的就是 ``"\n\n".join(worker_results.values())``，改末尾才不动前面已发的字。
    2. **交回的是整张 ``worker_results``**。``chat.py`` 是拿节点增量整张覆盖
       （``latest_worker_results = dict(worker_results)``），只回一条腿会把别的腿洗掉；
       也不用 ``__reset__``——那是 state 合并协议内部的记法，漏进收端就是脏字。
    3. **够不上判据就闭嘴**。``select_caliber_quotes`` 认不出登记行时返回空，本腿原样交回，
       ``final_answer`` 与守卫落地前逐字相同（判据③：硬门只许加，不许把别的族改出新形状）。
    """
    from app.rag.retrieval_pipeline import render_caliber_quotes, select_caliber_quotes

    quotes = select_caliber_quotes(_cited_caliber_fragments(state), question)
    block = render_caliber_quotes(quotes, final).strip()
    if not block:
        return final, None

    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + "\n\n" + block
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + "\n\n" + block
    logger.info(
        f"{CALIBER_QUOTE_MARKER} quotes={len(quotes)} sources="
        f"{[str(item.get('source') or '')[:24] for item in quotes]} "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


# ==================== R703：答复不许拿文字冒充屏上的图 ====================
#
# 病形同族（走查环 7 与环 8 那一格：``charts_on_screen=0``／``chart_srcs=[]``／``artifact_total=0``）：
# 答复里写着图，屏上一枚图都没有。导出件那一格另立号，本单只在**答复侧**钉一句真话，
# 而且只钉「声称有图、本轮却一枚图表件都查不回」这一枚形状。
#
# 🔴 三条边界：
#   * 只追加、不改写，落点与交回形状抄 ``_carry_caliber_quotes``（R203：已发帧仍是终答前缀）；
#   * 判据只读物证：本轮真有 ``artifact_type == "chart"`` 的件就闭嘴。读不出件型的老形状
#     （``artifacts`` 里躺一枚裸字符串）也闭嘴 —— 宁可少说一句，不许冤称客户「没有图」；
#   * 本腿不出图、不补工具调用、不碰批准链（那在 app/api/v1/chat.py，另单）。

#: 台账标记：窗内要能 grep 出"哪一题被图表真话腿钉过一句"，也要能反证它没开口时确实没开口。
CHART_TRUTH_MARKER = "[R703ChartTruth]"

#: 台账标记：同一读法，钉的是"答复说文档里没数据、本轮却真算过一张有行的表"那一格。
DATASET_TRUTH_MARKER = "[R703DatasetTruth]"

#: 声称"屏上已经有这张图"的两类形状。图片 markdown／``<img>`` 是直接摆出物件；短语那一族
#: 只收完成态（已生成／请看下图），刻意不收「柱状图」「画一张图」这种光**提到**图的词 ——
#: 走查那一轮的答复通篇说的是"无法直接生成…柱状图"，本腿必须对它闭嘴。
_CHART_CLAIM_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>", re.IGNORECASE)
_CHART_CLAIM_PHRASES = (
    "图表已生成",
    "已生成图表",
    "已生成图",
    "图已生成",
    "已出图",
    "见下图",
    "如下图",
    "如图所示",
    "图表如下",
    "生成的图表",
)
#: 图这一族词的粗筛：一条都没提"图"的文字不可能是"声称有图"，先挡掉，免得把知识库里的
#: 表格 markdown 当作出图声称。
_CHART_WORD_RE = re.compile(r"图|表|chart|plot", re.IGNORECASE)

#: 追加那一句。措辞红线：不说"失败"（那会把没执行说出错）、不说"没权限"（因由不归这里猜）、
#: 不替客户决定要不要重跑，只把"文字不等于屏上有图"这一件事实说清。
CHART_TRUTH_SENTENCE = (
    "⚠️ 说明：本轮没有真正生成可打开的图表文件，上面关于图表的文字不代表屏上已有图。"
)


def _chart_artifacts_in_state(state) -> list[dict]:
    """本轮工具边界真登记过的图表件（``agent_results[*].artifacts`` 里件型为 chart 的那些）。

    读的是 ``app/agents/evidence.py::record_artifact`` 落进证据袋、再由
    ``app/agents/orchestrator.py::_make_worker_wrapper`` 写进 ``agent_results`` 的那本账 ——
    装箱之后还在的料才算数，与 ``_cited_caliber_fragments`` 同一读法。本函数只搬运读数，
    不判定、不补记。
    """
    rows: list[dict] = []
    for raw in (state.get("agent_results") or {}).values():
        if isinstance(raw, dict):
            artifacts = raw.get("artifacts") or []
        else:
            artifacts = getattr(raw, "artifacts", None) or []
        for item in artifacts:
            if isinstance(item, dict):
                row = item
            elif hasattr(item, "model_dump"):
                row = item.model_dump()
            else:
                continue
            if str(row.get("artifact_type") or "") == "chart":
                rows.append(row)
    return rows


#: 10-07 13:21 现读（走查环 7，账本 rings[ring=7].readings：``chart_artifact.found=True``
#: 而 ``charts_on_screen=0``；会话正文逐字读下来 ``has_image_md=False``）：图真的画出来并登记进
#: 台账了，模型却把工具交回的那行图片 markdown 换成自己"画"的 ASCII 方块（一整屏 █），
#: 客户屏上看不到一张图。判据写的是「图当场显示」——文件在台账不等于客户看见了。
#: 这一格不再押模型的抄写：本轮真登记过图表件，产品自己把每一张图贴进终答，
#: 前端 ``frontend/src/components/ChartViewer.vue`` 认的就是这一行（它走鉴权取 blob 再显示）。
CHART_IMAGE_MARKER = "[R725ChartImage]"
CHART_IMAGE_CAPTION = "本轮生成的图表"


def _append_chart_images(state, final: str, worker_results: dict):
    """本轮真登记过图表件、正文里却没有它的地址 ⇒ 末尾替客户贴上图；贴过的不贴第二遍。"""
    rows = _chart_artifacts_in_state(state)
    if not rows:
        return final, None
    from app.storage.artifacts import artifact_content_url

    body = str(final or "")
    lines: list[str] = []
    for row in rows:
        artifact_id = str(row.get("artifact_id") or "").strip()
        if not artifact_id or artifact_id in body:
            continue
        lines.append(f"![{CHART_IMAGE_CAPTION}]({artifact_content_url(artifact_id)})")
    if not lines:
        return final, None
    tail = "\n\n" + "\n".join(lines)
    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + tail
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + tail
    logger.info(
        f"{CHART_IMAGE_MARKER} charts={len(rows)} pasted={len(lines)} "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


#: 台账标记：窗内要能 grep 出「本轮明明出了图、正文里还躺着几段绘图代码」。
PLOT_RECIPE_MARKER = "[R728PlotRecipe]"

#: 点名了绘图库的围栏代码块才算「配方」；一段 SQL 或一段 shell 不是本腿要摘的东西。
_PLOT_RECIPE_HINTS = (
    "matplotlib",
    "pyplot",
    "plt.",
    "savefig",
    "seaborn",
    "sns.",
    "plotly",
    "px.bar",
    "go.figure",
    "pyecharts",
)

#: 一段绘图配方 = 围栏代码块，外加紧挨在它上面的小标题与那句引导话（"### 柱状图可视化建议"
#: + "如需绘制柱状图，可使用以下Python代码："）。10-07 17:0x 现读：只摘围栏会留下一节空标题，
#: 客户看见的是"建议"两个字底下一片空白，比留着代码更懵 —— 引导句以冒号收尾，一起带走。
_PLOT_FENCE_RE = re.compile(
    r"(?:^|\n)(?:#{1,6} [^\n]*\n+)?(?:[^\n]{0,120}[:：]\s*\n+)?```[^\n]*\n.*?```",
    re.DOTALL,
)


def _is_plot_recipe(block: str) -> bool:
    body = str(block or "").lower()
    return any(hint in body for hint in _PLOT_RECIPE_HINTS)


def _strip_plot_recipes(text: str) -> tuple[str, int]:
    """摘掉点名绘图库的围栏代码块，其余文字一个字不动；交回（新文字, 摘掉的段数）。"""
    dropped = 0

    def _sub(match: "re.Match[str]") -> str:
        nonlocal dropped
        block = match.group(0)
        if not _is_plot_recipe(block):
            return block
        dropped += 1
        return ""

    stripped = _PLOT_FENCE_RE.sub(_sub, str(text or ""))
    if dropped:
        stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped, dropped


def _drop_plot_recipes(state, final: str, worker_results: dict):
    """本轮真登记过图表件 ⇒ 把正文里那些「教你自己画一张」的绘图代码摘掉。

    客户点的是「画一张柱状图」，图已经贴在同一个气泡里了，正文再留一段 ``plt.bar(...)``
    加一串颜色，等于一边交货一边教客户重做一遍——业主 10-07 现读纠的就是这一格：屏上
    那张图是一根色，正文里那段配方还是六道彩虹。本轮没有图表件时整条闭嘴：那时
    「怎么画」可能正是客户唯一能拿走的回答，摘它就是替客户把答案撕了。
    """
    if not _chart_artifacts_in_state(state):
        return final, None
    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    if not values:
        stripped, dropped = _strip_plot_recipes(final)
        if not dropped:
            return final, None
        logger.info(
            f"{PLOT_RECIPE_MARKER} dropped={dropped} answer_chars={len(str(final))}->{len(stripped)}"
        )
        return stripped, None
    merged = dict(worker_results)
    dropped = 0
    for key in values:
        stripped, cut = _strip_plot_recipes(merged[key])
        if cut:
            merged[key] = stripped
            dropped += cut
    if not dropped:
        return final, None
    rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    logger.info(
        f"{PLOT_RECIPE_MARKER} dropped={dropped} answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


def _claims_a_chart(text) -> bool:
    """这一份文字有没有声称"图已经在了"。判定只看完成态声称，不看光提到图。"""
    body = str(text or "")
    if not _CHART_WORD_RE.search(body):
        return False
    if _CHART_CLAIM_IMAGE_RE.search(body):
        return True
    return any(phrase in body for phrase in _CHART_CLAIM_PHRASES)


def _carry_chart_truth(state, model_answer: str, final: str, worker_results: dict):
    """声称有图而本轮查不回图表件 ⇒ 末尾追加一句真话；其余情形一个字都不动。

    声称以 ``model_answer``（逐字保真与择边两腿补写**之前**那一份模型正文）为准：那两枚守卫
    抬进正文的是知识库原文，原文里若躺着一枚图片 markdown，不该算成本腿要治的"声称有图"。
    """
    if _chart_artifacts_in_state(state):
        return final, None
    if not _claims_a_chart(model_answer or final):
        return final, None
    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + "\n\n" + CHART_TRUTH_SENTENCE
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + "\n\n" + CHART_TRUTH_SENTENCE
    logger.info(
        f"{CHART_TRUTH_MARKER} claim=image_or_phrase artifacts=0 "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


#: 答复里"文档没有数据"那一张脸的说法族。只收**指向文档**的那几句：工具腿自己那句诚实的
#: 「文件里没有数据行」不在此列 —— 它说的是量不到，不是"本轮没带表"，两句不能并成一格。
_DATASET_ABSENCE_BLAME = (
    "文档中未包含",
    "文档里没有数据",
    "文档中没有数据",
    "文档中未提及",
    "所有文档均为",
    "未包含实际报销数据",
)

#: 补写那一句：只把台账里已有的读数递到客户眼前，不替模型重写它的结论。
DATASET_TRUTH_SENTENCE = "本轮带着数据文件：{names}。上面「文档里没有数据」那句话说的是文档，不是这张表。"


def _dataset_readouts_in_state(state) -> list[dict]:
    """本轮工具边界真算过的数据文件读数 ``[{name, rows, cols}]``，逐枚去重。

    读的是 ``app/agents/tools.py::_record_dataset_evidence`` 在装箱**之后**记进证据袋的那本账
    （`source_type == "dataset"`，行数列数来自过滤后的真帧），与 ``app/api/v1/chat.py`` 汇
    ``data_filename`` 用的是同一批料。本函数只搬运读数，不判定、不补记，也不新算任何数字。
    """
    readouts: list[dict] = []
    seen: set[str] = set()
    for raw in (state.get("agent_results") or {}).values():
        if isinstance(raw, dict):
            rows_in_bag = raw.get("evidence") or []
        else:
            rows_in_bag = getattr(raw, "evidence", None) or []
        for item in rows_in_bag:
            if isinstance(item, dict):
                row = item
            elif hasattr(item, "model_dump"):
                row = item.model_dump()
            else:
                continue
            if str(row.get("source_type") or "") != "dataset":
                continue
            locator = row.get("locator")
            name = ""
            if isinstance(locator, dict):
                name = str(locator.get("filename") or "")
            name = name or str(row.get("source_name") or "")
            if not name or name in seen:
                continue
            metadata = row.get("metadata") or {}
            columns = metadata.get("columns") or []
            seen.add(name)
            readouts.append(
                {
                    "name": name,
                    "rows": int(metadata.get("row_count") or 0),
                    "cols": len(columns) if isinstance(columns, list) else 0,
                }
            )
    return readouts


def _format_dataset_readouts(readouts: list[dict]) -> str:
    """读数 → 人话：``报销明细表.csv（144 行 × 9 列）``；列数读不出就只报行。"""
    parts = []
    for item in readouts:
        shape = f"{item['rows']} 行"
        if item["cols"]:
            shape += f" × {item['cols']} 列"
        parts.append(f"{item['name']}（{shape}）")
    return "、".join(parts)


def _carry_dataset_truth(state, model_answer: str, final: str, worker_results: dict):
    """答复按"文档里没有数据"作答、本轮却真算过一张有行的表 ⇒ 末尾追加一句真话。

    只读物证：台账里没有 dataset 证据（本轮没跑数据、或跑的表一行都不剩）时本腿闭嘴 ——
    那时"没有数据"可能正是实话，替它说一句"带着数据文件"就是编。声称以 ``model_answer``
    （补写之前那一份模型正文）为准，理由与 ``_carry_chart_truth`` 同一条。
    """
    readouts = [item for item in _dataset_readouts_in_state(state) if item["rows"] > 0]
    if not readouts:
        return final, None
    body = str(model_answer or final or "")
    if not any(phrase in body for phrase in _DATASET_ABSENCE_BLAME):
        return final, None
    block = DATASET_TRUTH_SENTENCE.format(names=_format_dataset_readouts(readouts))
    #: R727：批准续跑的那一轮会把本腿再走一遍，而补写落的是 worker_results 里的那条腿 ——
    #: 上一遍的那句已经躺在正文里了。屏上同一句提示出现两遍就是这一格（业主 10-07 现读）：
    #: 已经说过的一次都不许再说第二遍。
    if block in str(final or ""):
        return final, None
    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + "\n\n" + block
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + "\n\n" + block
    logger.info(
        f"{DATASET_TRUTH_MARKER} datasets={len(readouts)} "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


#: 台账标记：窗内要能 grep 出"哪一轮声称报告文件已经交出去了、而本轮台账里一枚报告件都没有"。
#: 名字里的腿（leg=export）是判据 3 要的"点名是哪条腿在冒充"：读数只说 artifacts=0 不够，
#: 得说得出这一句是替导出腿还的债。
REPORT_TRUTH_MARKER = "[R710ReportTruth]"

#: 声称"报告文件已经交出去了"的两类形状：一句完成态话，或一枚点到产物下载口的链接。
#: 刻意不收「可以导出为PDF」「建议导出Excel格式」「请上传该文件」这一族**建议** —— 走查环 8
#: 那一轮的正文里就躺着这两句，本腿若对它开口，就是把一句真话钉成第枚假话；也不收用户自己
#: 那句"并导出成报告文件"（那是问题，不是声称）。
_REPORT_CLAIM_PHRASES = (
    "报告文件已导出",
    "已导出报告文件",
    "报告文件已生成",
    "已生成报告文件",
    "报告已导出",
    "已导出报告",
    "报告已生成",
    "已生成报告",
    "报告导出完成",
    "报告已准备好",
    "报告文件已就绪",
)
#: 图那一腿交回的是 ``/content``（png/html），数据导出是 xlsx，只有报告件走 ``/download``，
#: 所以这一枚形状不会把别的腿的链接错认成"报告已经在这儿了"。
_REPORT_DELIVERY_LINK_RE = re.compile(r"/api/v1/artifacts/[^)\s]+/download")
_REPORT_WORD_RE = re.compile(r"报告|report", re.IGNORECASE)

#: 追加那一句。措辞红线与 ``CHART_TRUTH_SENTENCE`` 同一条：不说"失败"（那一格因由不归这层猜，
#: 工具腿自己那句话已经把码说清了）、不说"没权限"、不替客户决定要不要重跑，
#: 只把"台账里没有这枚可查回的件"这一件事实说清。
REPORT_TRUTH_SENTENCE = (
    "⚠️ 说明：本轮产物台账里没有可查回的报告文件，上面「报告已导出／已生成」那类说法"
    "不对应一个能打开的文件。"
)


def _report_artifacts_in_state(state) -> list[dict]:
    """本轮工具边界真登记过的报告件（``agent_results[*].artifacts`` 里件型为 report 的那些）。

    读法与 ``_chart_artifacts_in_state`` 同一枚：账本出自
    ``app/agents/evidence.py::record_artifact``，由 ``app/agents/orchestrator.py`` 的 worker
    包装写进 ``agent_results``，装箱之后还在的料才算数。本函数只搬运读数，不判定、不补记。
    """
    rows: list[dict] = []
    for raw in (state.get("agent_results") or {}).values():
        if isinstance(raw, dict):
            artifacts = raw.get("artifacts") or []
        else:
            artifacts = getattr(raw, "artifacts", None) or []
        for item in artifacts:
            if isinstance(item, dict):
                row = item
            elif hasattr(item, "model_dump"):
                row = item.model_dump()
            else:
                continue
            if str(row.get("artifact_type") or "") == "report":
                rows.append(row)
    return rows


def _claims_an_exported_report(text) -> bool:
    """这一份文字有没有声称"报告文件已经交出去了"。只看完成态声称，光提到导出不算。"""
    body = str(text or "")
    if not _REPORT_WORD_RE.search(body):
        return False
    if any(phrase in body for phrase in _REPORT_CLAIM_PHRASES):
        return True
    return bool(_REPORT_DELIVERY_LINK_RE.search(body))


def _carry_report_truth(state, model_answer: str, final: str, worker_results: dict):
    """声称报告文件已导出、本轮台账却一枚报告件都查不回 ⇒ 末尾追加一句真话；其余一字不动。

    环 8 的病形就是这一格：导出腿自报 ``status=failed`` 交回 51 字，终答里却写着报告文件已
    导出并点了文件名。三条边界抄在册正例 ``_carry_chart_truth``：只追加不改写、判据只读物证
    （读不出件型的老形状一律当没这回事，宁可少说一句）、本腿不产文件也不碰批准链。
    声称以 ``model_answer``（逐字保真与择边两腿补写**之前**那一份模型正文）为准，同一条理由。
    """
    if _report_artifacts_in_state(state):
        return final, None
    if not _claims_an_exported_report(model_answer or final):
        return final, None
    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + "\n\n" + REPORT_TRUTH_SENTENCE
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + "\n\n" + REPORT_TRUTH_SENTENCE
    logger.info(
        f"{REPORT_TRUTH_MARKER} leg=export claim=phrase_or_delivery_link artifacts=0 "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


# ==================== R715 · 图腿登记不下那一格的人话（判据 2） ====================

#: 台账标记：窗内要能 grep 出"哪一轮的图腿登记不下、屏上因此补了一句为什么没有图"，也要能反证
#: 它没开口时确实没开口。名字里的腿（leg=chart）是判据 2 要的点名：读数只说 artifacts=0 不够，
#: 得说清这一句是替图腿还的债（导出腿那一位是 [R710ReportTruth] 的 leg=export）。
CHART_LEG_TRUTH_MARKER = "[R715ChartLegTruth]"

#: 读数面里图腿会交回来、而本腿说得出口的因由码 → 人话。表外的码（含读不出 error 格的老形状）
#: 一律闭嘴：因由不在表内就是本层说不出，宁可少说一句，不许替别的层猜。
#: ``department_scope_required`` 的出处是 ``app/agents/tools.py::_generate_chart`` 里 preflight 与
#: 登记被拒那两支，两支撑的是同一件事：属主交不出部门，``ArtifactRegistry.register`` 当场拒。
_CHART_LEG_REFUSAL_HEADS = {
    "department_scope_required": (
        "发起这一轮的账号没有部门归属，图表文件登记不进产物台账，本轮因此没有落盘"
    ),
    "chart_refusal_repeated": (
        "同一发画图请求本轮原样试过多次，每次都交回同一个结果，图腿因此停了手"
    ),
}

#: 追加那一句的模板：``{code}`` 与读数面那一枚码同源（判据 1 的"具名格与读数面一致"）——本层
#: 从不把正文里读到的码名再写回账上，也不给同一格换第二枚码。措辞红线抄在册正例：只把"这一轮
#: 没有图、原因写在账上"这一件事实说清，不替客户决定要不要重跑。
CHART_LEG_TRUTH_SENTENCE = "⚠️ 说明：为什么没有图：{reason}（error_code={code}）"


def _chart_leg_refusal_code_in_state(state) -> str:
    """本轮图腿交回的那枚拒绝码（``agent_results`` 里 worker 为 chart 那一行的 ``error.code``）。

    读的是 ``app/agents/evidence.py::build_agent_result`` 从证据袋折出来的那本账——工具腿在
    ``app/agents/tools.py::_generate_chart`` 里用 ``_denial_text`` 同一处写下正文与码，装箱之后
    还在的料才算数。只认图腿那一行：别的腿的拒绝不归本腿说话；只认表内的码：表外与读不出
    error 格的老形状一律交回空串。本函数只搬运读数，不判定、不补记。
    """
    for key, raw in (state.get("agent_results") or {}).items():
        if isinstance(raw, dict):
            row = raw
        elif hasattr(raw, "model_dump"):
            row = raw.model_dump()
        else:
            continue
        if str(row.get("worker") or key or "") != "chart":
            continue
        error = row.get("error")
        code = ""
        if isinstance(error, dict):
            code = str(error.get("code") or "")
        elif error is not None:
            code = str(getattr(error, "code", "") or "")
        if code in _CHART_LEG_REFUSAL_HEADS:
            return code
    return ""


def _says_why_there_is_no_chart(text, code: str) -> bool:
    """这一份正文里是不是已经把那枚因由码写在屏上了：写过就闭嘴，不许钉第二句。

    工具腿那句诚实话本来带着同一个码（两路同源），模型把它原样抬进终答时屏上已经说清，
    再补一句就是两句互相打脸。
    """
    return f"error_code={code}" in str(text or "")


def _carry_chart_leg_truth(state, model_answer: str, final: str, worker_results: dict):
    """图腿本轮登记不下、屏上却没写「为什么没有图」⇒ 末尾追加一句真话；其余情形一个字都不动。

    这一格与 ``_carry_chart_truth``（R703）不是同一格：那一枚治"文字冒充屏上已有图"，它的句子
    按措辞红线不许说因由，而且对「无法生成柱状图」那类答复刻意闭嘴；本枚治走查环 7 的另一半
    ——图腿一路走到 ``ArtifactRegistry.register`` 被拒，屏上 6 250 字没有一个字交代原因
    （凭据 docs/testing/walkthrough-2026-10-06/README.md 缺陷 #2，账本 rings[ring=7].readings）。
    三条边界抄在册正例：只追加不改写、判据只读物证（读数面交不出表内的码就闭嘴）、本腿不产
    文件也不碰批准链。声称与否不参与判定——因由是账上写下的，不从正文猜；屏上连一个字都没有时
    也闭嘴（那一份空正文的账归 R439，不归本单）。
    """
    if _chart_artifacts_in_state(state):
        return final, None
    code = _chart_leg_refusal_code_in_state(state)
    if not code:
        return final, None
    if _says_why_there_is_no_chart(final, code) or _says_why_there_is_no_chart(model_answer, code):
        return final, None
    if not str(final).strip():
        return final, None
    sentence = CHART_LEG_TRUTH_SENTENCE.format(reason=_CHART_LEG_REFUSAL_HEADS[code], code=code)
    values = [key for key, value in (worker_results or {}).items() if str(value or "").strip()]
    merged: dict | None = None
    if values:
        merged = dict(worker_results)
        last = values[-1]
        merged[last] = str(merged[last]).strip() + "\n\n" + sentence
        rebuilt = "\n\n".join(str(merged[key]).strip() for key in values if str(merged[key]).strip())
    else:
        rebuilt = str(final).strip() + "\n\n" + sentence
    logger.info(
        f"{CHART_LEG_TRUTH_MARKER} leg=chart refusal_code={code} artifacts=0 "
        f"answer_chars={len(str(final))}->{len(rebuilt)}"
    )
    return rebuilt, merged


_DOC_CHART_REFUSAL_RE = re.compile(
    r"(?:无法|不能|未能|不支持)[^。\n]{0,20}(?:生成|绘制|画出|提供)[^。\n]{0,60}(?:图表|柱状图|折线图|饼图)"
)
_DOC_CHART_WORKAROUND_RE = re.compile(
    r"文档性质|数据缺失|图表缺失|不包含.{0,12}(?:历史|报销|实际)数据|没有实际报销.*数据"
    r"|建议操作|联系财务.*数据|导出.{0,20}(?:报销|数据)|Excel|Python|matplotlib|MYBI|BI工具"
)


def _reconcile_document_chart_refusal(state, worker_results: dict):
    """已有本轮图表时，文档腿的出图拒绝和自助步骤不再代表合流结果。"""
    doc = str(worker_results.get("doc") or "")
    if not _chart_artifacts_in_state(state) or not _DOC_CHART_REFUSAL_RE.search(doc):
        return None
    cited = [row["text"] for row in _cited_caliber_fragments(state)]
    kept = []
    refusal_seen = False
    for line in doc.splitlines():
        quote = line.strip(" -*>#\t")
        if len(quote) >= 12 and any(quote in text for text in cited):
            kept.append(line)
            continue
        if _DOC_CHART_REFUSAL_RE.search(line):
            refusal_seen = True
            continue
        if refusal_seen and _DOC_CHART_WORKAROUND_RE.search(line):
            continue
        kept.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    merged = dict(worker_results)
    merged["doc"] = cleaned
    return merged


def synthesize(state, config=None) -> dict:
    """把最终回答写入 state，并把值得记的沉淀进长期记忆"""
    # R688（判据①·生产发点）：终答装配是规则腿，没有自己的跨度；worker 的作答往返另有 model 跨度，本件只记这一段自己的墙钟，区间不与之重叠。
    with _stage_account(config, stage="generate", summary={"node": "synthesize"}):
        q = _last_user(state)
        final = state.get("final_answer") or ""
        worker_results = state.get("worker_results") or {}
        doc_update = _reconcile_document_chart_refusal(state, worker_results)
        if doc_update is not None:
            worker_results = doc_update
        if worker_results:
            answers = [
                str(value).strip()
                for value in worker_results.values()
                if str(value).strip()
            ]
            if answers:
                # Worker output is authoritative; trailing supervisor chatter is not.
                final = "\n\n".join(answers)
        if not final:
            for m in reversed(state.get("messages", [])):
                if type(m).__name__ == "AIMessage" and getattr(m, "content", "") and not getattr(m, "tool_calls", None):
                    final = m.content
                    break

        # R206（A④ 判据④那枚真退化）：被引证片段里的那句口径原话必须逐字进正文。
        # 它排在记忆沉淀**之前**：值得沉淀的是交回客户的那一份文字，不是补写前的半成品。
        # 整条守卫炸了也不能带走终答——这一腿是 END 前最后一站。
        #: 模型自己写的那一份，在逐字保真腿补写**之前**取：R216 的择边腿判"边选错没"要问这一份，
        #: 不能问补写之后的那一份（否则 R206b 抬进来的原话会冒充"模型已经选对了"）。
        model_final = final
        try:
            guarded, worker_update = _carry_caliber_quotes(state, q, final, worker_results)
        except Exception as exc:  # noqa: BLE001 - 终答优先，守卫失声只许记账不许拦
            guarded, worker_update = final, None
            logger.warning(f"{CALIBER_QUOTE_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded

        # R216（A④ 判据④ 第 4 格）：互斥口径必须按题面点名的那一侧作答。排在逐字保真**之后**：
        # 先把原话送进正文，再判哪一句是本题结论——两枚守卫各治各的格，收益不互记。
        # 与上一腿同一条硬规矩：整条炸了也不能带走终答，这一腿是 END 前最后一站。
        try:
            side_base = worker_update if worker_update is not None else worker_results
            guarded, side_update = _apply_caliber_side(state, q, final, side_base, model_final)
        except Exception as exc:  # noqa: BLE001 - 终答优先，择边腿失声只许记账不许拦
            guarded, side_update = final, None
            logger.warning(f"{CLAUSE_SIDE_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if side_update is not None:
            worker_update = side_update

        # R703（判据 3）：声称有图、本轮却一枚图表件都查不回 ⇒ 钉一句真话。排在逐字保真与
        # 择边之后：那两枚送的是真料原话，本枚送的是"没发生的事别说成发生了"，最后一步只追加一次。
        # 与前两枚同一条硬规矩：整条炸了也不能带走终答。
        try:
            truth_base = worker_update if worker_update is not None else worker_results
            guarded, truth_update = _carry_chart_truth(state, model_final, final, truth_base)
        except Exception as exc:  # noqa: BLE001 - 终答优先，守卫失声只许记账不许拦
            guarded, truth_update = final, None
            logger.warning(f"{CHART_TRUTH_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if truth_update is not None:
            worker_update = truth_update

        # R703（判据 2）：答复走"文档里没有数据"那一支、台账里却躺着本轮真算过的有行的表 ⇒ 钉一句真话。
        # 排在图表那枚之后：两句都是追加，先说数据在哪儿，再说图没生成。同样炸了也不许带走终答。
        try:
            data_base = worker_update if worker_update is not None else worker_results
            guarded, data_update = _carry_dataset_truth(state, model_final, final, data_base)
        except Exception as exc:  # noqa: BLE001 - 终答优先，守卫失声只许记账不许拦
            guarded, data_update = final, None
            logger.warning(f"{DATASET_TRUTH_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if data_update is not None:
            worker_update = data_update

        # R710（判据 3）：声称报告文件已导出、本轮却查不回一枚报告件 ⇒ 钉一句真话。排在数据那枚
        # 之后：三句都是追加，最后一步只追加一次；与前两枚同一条硬规矩，整条炸了也不许带走终答。
        try:
            report_base = worker_update if worker_update is not None else worker_results
            guarded, report_update = _carry_report_truth(state, model_final, final, report_base)
        except Exception as exc:  # noqa: BLE001 - 终答优先，守卫失声只许记账不许拦
            guarded, report_update = final, None
            logger.warning(f"{REPORT_TRUTH_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if report_update is not None:
            worker_update = report_update

        # R715（判据 2）：图腿本轮登记不下、屏上却没写「为什么没有图」⇒ 钉一句因由。排在报告那枚
        # 之后：几句都是追加，最后一步只追加一次；同一条硬规矩——整条炸了也不能带走终答。
        # 与 ``_carry_chart_truth`` 各治各的格：那一枚说"屏上没有图"，本枚说"为什么没有"。
        try:
            leg_base = worker_update if worker_update is not None else worker_results
            guarded, leg_update = _carry_chart_leg_truth(state, model_final, final, leg_base)
        except Exception as exc:  # noqa: BLE001 - 终答优先，守卫失声只许记账不许拦
            guarded, leg_update = final, None
            logger.warning(f"{CHART_LEG_TRUTH_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if leg_update is not None:
            worker_update = leg_update

        # R725：本轮真出过图 ⇒ 图自己上屏，不指望模型把工具那行图片 markdown 抄回来。
        # 排在所有"说没图"的守卫之后：那几枚只在查不回图表件时开口，本枚只在查得回时贴图，
        # 两拨条件互斥，打不着架。同一条硬规矩——整条炸了也不能带走终答。
        try:
            image_base = worker_update if worker_update is not None else worker_results
            guarded, image_update = _append_chart_images(state, final, image_base)
        except Exception as exc:  # noqa: BLE001 - 终答优先，贴图失声只许记账不许拦
            guarded, image_update = final, None
            logger.warning(f"{CHART_IMAGE_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if image_update is not None:
            worker_update = image_update

        # R728：本轮真出过图 ⇒ 正文里那些"教你自己画一张"的绘图代码不再递给客户。排在贴图之后：
        # 图先上屏，本枚只摘文字里的代码块，两枚打的不是同一格。同一条硬规矩——炸了也不许带走终答。
        try:
            recipe_base = worker_update if worker_update is not None else worker_results
            guarded, recipe_update = _drop_plot_recipes(state, final, recipe_base)
        except Exception as exc:  # noqa: BLE001 - 终答优先，守卫失声只许记账不许拦
            guarded, recipe_update = final, None
            logger.warning(f"{PLOT_RECIPE_MARKER} status=skipped error={exc}")
        if guarded != final:
            final = guarded
        if recipe_update is not None:
            worker_update = recipe_update

        if state.get("intent") == "task" and q and final:
            user_id = _memory_user_id(state)
            if user_id:
                remember(user_id, f"问: {q[:60]} → 答: {final[:80]}")
            else:
                logger.warning("[Synthesize] memory persistence skipped because the request has no authenticated identity")

        update = {"final_answer": final}
        if worker_update is None:
            worker_update = doc_update
        if worker_update is not None:
            # 交回整张表：收端拿 worker_results 当终答正文（见 _carry_caliber_quotes 约束 1、2）
            update["worker_results"] = worker_update
        return update
