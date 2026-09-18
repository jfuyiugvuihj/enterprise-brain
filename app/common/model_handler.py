"""Local model adapter with explicit unavailable-state handling.

This is the second boundary that calls the local model -- the first is
``app/agents/nodes.py:_make_model`` -- so it consumes the same per-tier budgets: the
non-streaming calls here are query rewrites, the streaming one is the legacy answer.
"""
from enum import Enum
from threading import Lock

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from app.agents.contracts import ModelBudget, ModelTier
from app.common.logger import logger
from app.common.model_budget import (
    ModelContextLimitExceeded,
    authorize_call,
    budget_signal,
    context_error_code,
    estimate_prompt_tokens,
    http_timeout,
    model_tier_budget,
    request_timeout_ceiling_seconds,
)
from app.common.model_config import get_local_model_settings

load_dotenv()


class ModelSource(str, Enum):
    LOCAL = "local"
    OLLAMA = "local"


class _OfflineStreamChunk:
    def __init__(self, content: str):
        delta = type("Delta", (), {"content": content})()
        choice = type("Choice", (), {"delta": delta})()
        self.choices = [choice]


class _OfflineChatCompletions:
    # Accepts and ignores the per-call budget arguments so the offline client stays a
    # drop-in substitute for the provider one: a caller that sizes its request must not
    # work only when the model is up, which is precisely when it has no answer to give.
    def create(self, model: str, messages: list[dict], stream: bool = True, **ignored):
        content = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"
        if stream:
            return iter([_OfflineStreamChunk(content)])
        message = type("Msg", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()


class _OfflineChatClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _OfflineChatCompletions()})()


class ModelHandler:
    """Unified local-model call boundary."""

    def __init__(self):
        local_settings = get_local_model_settings()
        self.local_model = local_settings.model_name
        self.ollama_model = self.local_model
        #: Documented as 120 in both shipped env files while the code said 60; it is read
        #: here through the one helper that owns the default, so the two cannot disagree a
        #: third time. It is a ceiling, not a per-request guess: the clock a call actually
        #: gets is sized from its prompt in :meth:`chat`.
        self.request_timeout = request_timeout_ceiling_seconds()
        from app.common.model_budget import default_model_budget

        self._budget = default_model_budget()
        try:
            self.local_client = OpenAI(
                base_url=local_settings.base_url,
                api_key=local_settings.api_key,
                http_client=self._build_http_client(local=True),
                max_retries=0,
            )
            self.ollama_client = self.local_client
        except Exception as exc:
            logger.warning(f"[Model] local model client unavailable: {exc}")
            self.local_client = _OfflineChatClient()
            self.ollama_client = self.local_client

    def _build_http_client(self, local: bool) -> httpx.Client:
        """Keep local model traffic independent of ambient proxy settings.

        The client carries the tier's worst-case budget, split into the phases it
        actually measures: ``read`` waits for the model, the rest wait for a socket on a
        machine that is loopback by definition. Every real request overrides this with a
        clock sized from its own prompt in :meth:`chat`.
        """
        return httpx.Client(
            timeout=http_timeout(self._call_budget(stream=True), None),
            trust_env=False,
        )

    @staticmethod
    def _call_budget(stream: bool) -> ModelBudget:
        """Which tier this handler's next call belongs to.

        Streaming on this boundary is the legacy answer endpoint, so it gets the prose
        cap; not streaming is a query rewrite, which restates one question and must not
        be paid for like an essay. Sharing one cap between them would either truncate
        answers at a rewrite's length or let a rewrite run for minutes.
        """
        return model_tier_budget(ModelTier.ANALYSIS if stream else ModelTier.REWRITE)

    def _rate_limited_response(self, stream: bool):
        content = (
            "Local model capacity is exhausted (error_code=rate_limited); "
            "no business conclusion was generated."
        )
        if stream:
            return iter([_OfflineStreamChunk(content)])
        return content

    def _release_after_stream(self, response, slot):
        try:
            yield from response
        finally:
            slot.release()

    def chat(self, messages: list[dict], source: ModelSource = ModelSource.LOCAL, stream: bool = True):
        """Call the local model; failures remain explicit and non-business results."""
        client = self.ollama_client
        model = self.local_model
        from app.common.model_budget import ModelBudgetExhausted

        budget = self._call_budget(stream)
        prompt_tokens = estimate_prompt_tokens(messages)
        # Sized and, if it cannot fit, refused before a slot is taken. A request this
        # window will never hold must not queue behind real work, and must not come back
        # as an answer the server stopped halfway through.
        authorize_call(budget, prompt_tokens, stream=stream)

        try:
            slot = self._budget.acquire(wait_seconds=0)
        except ModelBudgetExhausted:
            logger.warning("[Model] local model concurrency budget exhausted")
            return self._rate_limited_response(stream)
        logger.info(f"使用内部本地模型: {model}")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
                max_tokens=budget.max_tokens,
                timeout=http_timeout(budget, prompt_tokens, stream=stream),
            )
        except Exception as exc:
            slot.release()
            provider_code = context_error_code(exc)
            if provider_code:
                # The server refused for the same reason authorize_call checks for, so it
                # gets the same verdict: one collision, one code, whoever detected it.
                logger.warning(
                    budget_signal(
                        budget.tier,
                        prompt_tokens=prompt_tokens,
                        read_seconds=budget.timeout_seconds,
                        code=provider_code,
                        stream=stream,
                    )
                )
                raise ModelContextLimitExceeded(budget, prompt_tokens or 0) from exc
            logger.warning(f"[Model] provider unavailable: {exc}")
            content = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"
            if stream:
                return iter([_OfflineStreamChunk(content)])
            return content

        if stream:
            return self._release_after_stream(response, slot)
        try:
            return response.choices[0].message.content
        finally:
            slot.release()
