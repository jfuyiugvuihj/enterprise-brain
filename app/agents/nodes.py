"""
阶段 1 · 新图各节点逻辑

节点：classify_intent / respond / load_memory / plan / reflect / synthesize
共享模型工厂 _make_model 也放这里，避免 orchestrator 循环依赖。
"""
import os
import httpx
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import Runnable

from app.common.logger import logger
from app.common.model_config import get_local_model_settings
from app.agents.contracts import AgentResult, DEFAULT_MODEL_TIER, ModelTier
from app.common.model_budget import (
    budget_signal,
    context_error_code,
    detect_output_truncation,
    estimate_prompt_tokens,
    http_timeout,
    model_tier_budget,
    report_budget,
)
from app.agents.critic import review_agent_results
from app.agents.planner import build_task_plan
from app.memory import recall, remember
from app.memory.profile import compose_profile_context, get_profile


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
            content = "公司报销流程一般包括提交申请、部门审批、财务复核和付款归档。离线模式下我先给你这个通用版本。"
        elif "利润" in text or "门店" in text or "分析" in text:
            content = "离线模式下可先按门店利润、营收和成本三项做排序，再进一步看利润率和同比环比变化。"
        else:
            content = "离线模式已启用，但我仍可以继续帮你梳理问题、拆解任务，并给出可执行的下一步建议。"
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
        yield type("Chunk", (), {"choices": [type("Choice", (), {"delta": type("Delta", (), {"content": "离线模式已启用"})()})()]})()


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
        #: This call's token and clock budget; ``None`` means "an un-typed hand-built model",
#: which is only ever constructed by tests, never by ``_make_model``.
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

    def _span(self, config, *, provider=None, model_name=None, queue_wait_ms=None):
        from app.trace.spans import start_model_call

        return start_model_call(
            config,
            provider=provider or self.provider,
            model_name=model_name or self.recorded_model_name,
            queue_wait_ms=queue_wait_ms,
        )

    def _offline_fallback(self, messages, config=None, **kwargs):
        span = self._span(config, provider="offline", model_name="offline")
        response = self.fallback.invoke(messages, config=config, **kwargs)
        from app.trace.spans import model_token_counts

        span.finish("model_unavailable", error_code="model_unavailable", summary=model_token_counts(response))
        return response

    def _budget_kwargs(self, messages, *, stream: bool) -> dict:
        """Size this exact call: its own output cap and a clock proportional to its prompt.

        The per-request values override the client defaults, which are only the worst case
        for the tier. A provider that has never heard of ``extra_body`` still gets a valid
        request: the OpenAI-compatible wire format carries ``max_tokens`` there.
        """
        if self.budget is None:
            return {}
        prompt_tokens = estimate_prompt_tokens(messages)
        report_budget(self.budget, prompt_tokens, stream=stream)
        return {
            "timeout": http_timeout(self.budget, prompt_tokens, stream=stream),
            "extra_body": {"max_tokens": self.budget.max_tokens},
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
        call_kwargs = {**self._budget_kwargs(messages, stream=False), **kwargs}
        try:
            response = self.primary.invoke(messages, config=config, **call_kwargs)
        except Exception as exc:
            provider_code = context_error_code(exc)
            if provider_code:
                logger.warning(
                    budget_signal(
                        getattr(self.budget, "tier", None) or "analysis",
                        prompt_tokens=estimate_prompt_tokens(messages),
                        read_seconds=float(getattr(self.budget, "timeout_seconds", 0.0) or 0.0),
                        code=provider_code,
                    )
                )
            from app.trace.spans import error_code_for

            span.finish("failed", error_code=error_code_for(exc))
            logger.warning(f"[Model] provider invoke 失败，使用离线回复: {exc}")
            slot.release()
            return self._offline_fallback(messages, config=config, **kwargs)
        slot.release()
        from app.trace.spans import model_token_counts

        summary = dict(model_token_counts(response))
        if self.budget is not None:
            truncated = detect_output_truncation(response)
            summary["budget_tier"] = self.budget.tier.value
            if truncated:
                summary["truncation_code"] = truncated
                logger.warning(
                    budget_signal(
                        self.budget.tier,
                        prompt_tokens=estimate_prompt_tokens(messages),
                        read_seconds=self.budget.timeout_seconds,
                        code=truncated,
                    )
                )
        span.finish("completed", summary=summary)
        return response

    def stream(self, *args, **kwargs):
        from app.common.model_budget import ModelBudgetExhausted, default_model_budget

        config = kwargs.get("config")
        if args:
            kwargs = {**self._budget_kwargs(args[0], stream=True), **kwargs}
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

        span = self._span(config, queue_wait_ms=slot.wait_ms)
        try:
            for chunk in self.primary.stream(*args, **kwargs):
                span.mark_first_token()
                yield chunk
        except Exception as exc:
            from app.trace.spans import error_code_for

            span.finish("failed", error_code=error_code_for(exc))
            logger.warning(f"[Model] provider stream 失败，使用离线流: {exc}")
            fallback = self._span(config, provider="offline", model_name="offline")
            try:
                for chunk in self.fallback.stream(*args, **kwargs):
                    fallback.mark_first_token()
                    yield chunk
            finally:
                fallback.finish("model_unavailable", error_code="model_unavailable")
            return
        span.finish("completed")


def _make_model(tier: ModelTier | str = DEFAULT_MODEL_TIER, *, prompt=None):
    """Build the model for one tier: an explicit output cap and a prompt-scaled clock.

    There is no ``timeout`` parameter any more, and that is the point. A bare scalar used to
    be handed to both ``ChatOpenAI`` and ``httpx.Client``, which made prefill and decode
    share one wall clock: the longer the prompt, the more likely the answer was cut off in
    the middle. ``prompt`` is the text or message list this instance is about to send, where
    the call site already knows it; when nobody passes it, the budget is sized for the
    tier's largest permitted prompt and every call is re-sized again in
    :meth:`_ResilientModel.invoke` from the messages actually on the wire.
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
