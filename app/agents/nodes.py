"""
阶段 1 · 新图各节点逻辑

节点：classify_intent / respond / load_memory / plan / reflect / synthesize
共享模型工厂 _make_model 也放这里，避免 orchestrator 循环依赖。
"""
import os
import httpx
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import Runnable

from app.common.logger import logger
from app.common.model_config import get_local_model_settings
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


def _with_thinking_field(call_kwargs: dict) -> dict:
    """Re-assert the thinking field on the body this boundary is about to send.

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
    """
    thinking = thinking_extra_body()
    if not thinking:
        return call_kwargs
    extra_body = dict(call_kwargs.get("extra_body") or {})
    for field, value in thinking.items():
        extra_body.setdefault(field, value)
    return {**call_kwargs, "extra_body": extra_body}


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
            call_kwargs = _with_thinking_field({**budget_kwargs, **kwargs})
        except ModelContextLimitExceeded as exc:
            # Refused before the provider saw it. The offline reply is deliberately not
            # used here: it would record model_unavailable, and evidence._terminal_status
            # reports model_unavailable ahead of a failure, so the customer would read a
            # canned greeting while the real verdict -- this prompt does not fit n_ctx --
            # stayed in a log line.
            slot.release()
            span.finish("failed", error_code=exc.code)
            raise
        try:
            response = self.primary.invoke(messages, config=config, **call_kwargs)
        except Exception as exc:
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
                kwargs = _with_thinking_field({**budget_kwargs, **kwargs})
            except ModelContextLimitExceeded as exc:
                span.finish("failed", error_code=exc.code)
                raise
            visible_total = 0
            saw_tool_call = False
            try:
                for chunk in self.primary.stream(*args, **kwargs):
                    span.mark_first_token()
                    visible_total += len(answer_text(chunk))
                    saw_tool_call = saw_tool_call or produced_a_tool_call(chunk)
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


def plan(state) -> dict:
    """复杂问题拆子任务；简单问题返回空列表"""
    q = _last_user(state)
    deterministic_plan = build_task_plan(q)
    if deterministic_plan:
        logger.info(f"[Plan] deterministic tasks={len(deterministic_plan)}")
        return {"plan": deterministic_plan}
    if classify_route(q).lane == LANE_QA:
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
