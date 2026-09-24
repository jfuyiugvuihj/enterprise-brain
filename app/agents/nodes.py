"""
阶段 1 · 新图各节点逻辑

节点：classify_intent / respond / load_memory / plan / reflect / synthesize
共享模型工厂 _make_model 也放这里，避免 orchestrator 循环依赖。
"""
import os
import time
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
    get_local_model_settings,
    resolve_keep_alive,
)
from app.common.model_handler import KEEP_ALIVE_FIELD
from app.agents.contracts import AgentResult, DEFAULT_MODEL_TIER, ModelTier
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
    discuss offline mode. The direction of the error is what decided that -- a false positive
    costs one cache miss, a false negative replays a canned sentence as an answer until the
    entry expires. Nothing in the delivery path changes today: the caller that has to ask
    this question is the cache guard in app/api/v1/chat.py, outside this ticket's write
    domain, and tests/test_r99_budget_selfconsistency.py pins that it does not yet.
    """
    return isinstance(text, str) and text.strip() in _OFFLINE_REPLY_VARIANTS


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
        if tool_output:
            return AIMessage(content=tool_output)
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
        f"（{'请求体带 thinking 字段' if policy.wire else '请求体不带 thinking 字段，与 R100 之前逐字节相同'}）"
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
#:   2. 挂起之后从 ``/approve`` 续的那一跑道**结构上接不到 sink**：
#:      ``run_interrupt_stream``（orchestrator.py:1341-1350）不收这一格，config
#:      （:1359-1367）也不塞，``chat._approve_stream`` 的队列只有 event/done/error 三件
#:      （chat.py:2676-2682），收端循环（:2777 起）没有 piece 一支。
#:      ⇒ 这一腿的逐字交付落在本单写域之外（要改的是续跑道那本 config），
#:      且第 1 条已经说明改了也发不出字：明写不判为缺陷，也不默默漏掉。
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
        for piece in self.merger.feed(visible_chunk_text(message)):
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
            return self._offline_fallback(messages, config=config, **kwargs)

        span = self._span(config, queue_wait_ms=slot.wait_ms)
        prompt_tokens = estimate_prompt_tokens(messages)
        try:
            budget_kwargs, verdict = self._budget_kwargs(prompt_tokens, stream=False)
            call_kwargs = _with_boundary_fields({**budget_kwargs, **kwargs})
        except ModelContextLimitExceeded as exc:
            # Refused before the provider saw it. The offline reply is deliberately not
            # used here: it would record model_unavailable, and evidence._terminal_status
            # reports model_unavailable ahead of a failure, so the customer would read a
            # canned greeting while the real verdict -- this prompt does not fit n_ctx --
            # stayed in a log line.
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
                    # whether the window was measured here or refused by the server.
                    slot.release()
                    span.finish("failed", error_code=provider_code)
                    raise ModelContextLimitExceeded(self.budget, prompt_tokens or 0) from exc
            from app.trace.spans import error_code_for

            timeout_code = model_timeout_code(exc)
            span.finish("failed", error_code=timeout_code or error_code_for(exc))
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
                    )
                    + f" [Model] provider 超时，改用离线回复（该回复不计为业务结论）: {exc}"
                )
            else:
                logger.warning(f"[Model] provider invoke 失败，使用离线回复: {exc}")
            return self._offline_fallback(messages, config=config, **kwargs)
        slot.release()
        if tap is not None:
            delivered = tap.close()
            if delivered:
                logger.info(
                    f"[R203] leg={tap.worker} call={tap.call_id} 生成腿流式 pieces={delivered}"
                )
        from app.trace.spans import model_token_counts

        summary = dict(model_token_counts(response))
        empty_code = None
        if self.budget is not None:
            truncated = detect_output_truncation(response)
            summary["budget_tier"] = self.budget.tier.value
            if truncated:
                summary["truncation_code"] = truncated
                logger.warning(
                    budget_signal(
                        self.budget.tier,
                        prompt_tokens=prompt_tokens,
                        read_seconds=self.budget.timeout_seconds,
                        code=truncated,
                        **self._verdict_fields(verdict),
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
                    )
                    + " [Model] 模型正文为空，不作为答案交付（同一行的 thinking= 说明这次到底有没有要求"
                    "关掉思考，max_tokens= 说明预算有多大；思考链吃满预算只是已测过的成因之一）"
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
            prompt_tokens = estimate_prompt_tokens(messages)
            try:
                budget_kwargs, verdict = self._budget_kwargs(prompt_tokens, stream=True)
                kwargs = _with_boundary_fields({**budget_kwargs, **kwargs})
            except ModelContextLimitExceeded as exc:
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
                    span.finish("failed", error_code=provider_code)
                    raise ModelContextLimitExceeded(self.budget, prompt_tokens or 0) from exc
                from app.trace.spans import error_code_for

                timeout_code = model_timeout_code(exc)
                span.finish("failed", error_code=timeout_code or error_code_for(exc))
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
                    )
                    + " [Model] 流式正文为空，不作为答案交付（同一行的 thinking= 说明这次到底有没有要求"
                    "关掉思考；思考链吃满预算只是已测过的成因之一）"
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


# ==================== 意图分类（确定性，不调 LLM） ====================

_SMALLTALK = ["你好", "您好", "在吗", "谢谢", "感谢", "再见", "拜拜",
              "你是谁", "你叫什么", "hello", "hi", "早上好", "晚上好"]


def classify_intent(state) -> dict:
    """规则分类：chat(闲聊) / task(任务)。快、稳、可解释。"""
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


def respond(state) -> dict:
    """闲聊直接回答，不走 worker"""
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
            "department": state.get("department") or "",
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

def reflect_node(state) -> dict:
    """检查最终回答质量，决定重派(redo)或放行"""
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

def synthesize(state) -> dict:
    """把最终回答写入 state，并把值得记的沉淀进长期记忆"""
    q = _last_user(state)
    final = state.get("final_answer") or ""
    worker_results = state.get("worker_results") or {}
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

    if state.get("intent") == "task" and q and final:
        user_id = _memory_user_id(state)
        if user_id:
            remember(user_id, f"问: {q[:60]} → 答: {final[:80]}")
        else:
            logger.warning("[Synthesize] memory persistence skipped because the request has no authenticated identity")

    return {"final_answer": final}
