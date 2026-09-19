"""Local model adapter with explicit unavailable-state handling.

This is the second boundary that calls the local model -- the first is
``app/agents/nodes.py:_make_model`` -- so it consumes the same per-tier budgets: the
non-streaming calls here are query rewrites, the streaming one is the legacy answer.

The two halves do not share a request shape, and that is deliberate. On the OpenAI-compatible
``/v1`` leg Ollama bills a thinking model's hidden chain of thought against the same
``max_tokens`` that is supposed to hold the rewrite's JSON, so on the delivery machine a
rewrite comes back 200 with an empty body and ``finish_reason=length`` -- roughly 12 s of GPU
per question for text nothing can parse. The native ``/api/chat`` leg with ``think:false``
answers the same prompt inside the same budget, so the non-streaming half asks Ollama
natively and the streaming half is left exactly as it was.
"""
from enum import Enum
import time
from threading import Lock

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from app.agents.contracts import ModelBudget, ModelTier
from app.common.logger import logger
from app.common.model_budget import (
    ModelContextLimitExceeded,
    OUTPUT_TRUNCATED_CODE,
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

#: Ollama serves its own chat API on the same port, without the OpenAI-compatible /v1 prefix.
NATIVE_CHAT_SUFFIX = "/api/chat"
#: The native request field that stops a thinking model from thinking out loud.
NATIVE_THINK_FIELD = "think"
#: ``num_predict`` is the native spelling of this tier's ``max_tokens``.
NATIVE_MAX_TOKENS_FIELD = "num_predict"
#: Which leg answered a call. A log line that cannot say this is not evidence of anything.
TRANSPORT_NATIVE = "ollama-native"
TRANSPORT_COMPAT = "openai-compat"
#: Statuses that mean "this server has no native chat API", as opposed to "not right now".
#: 429 and the 5xx family are deliberately absent: they are temporary, and retiring the leg
#: over one overloaded afternoon would quietly downgrade every request that follows.
NATIVE_REFUSED_STATUSES = frozenset({400, 404, 405, 410})

#: The offline sentence, spelled once. It was already written twice in this file, and both
#: legs have to answer with the same words for the same reason.
MODEL_UNAVAILABLE_REPLY = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"
#: Verdicts for an answer this boundary cannot use. Deliberately not ``ErrorEnvelope``
#: members, exactly like the budget codes in app/agents/contracts.py:100-103: they describe
#: one model call, not a client-facing failure class.
RESPONSE_EMPTY_CODE = "model_response_empty"
MODEL_UNAVAILABLE_CODE = "model_unavailable"
RATE_LIMITED_CODE = "rate_limited"


class ModelSource(str, Enum):
    LOCAL = "local"
    OLLAMA = "local"


class ModelReply(str):
    """A non-streaming answer that still says what the server actually did.

    Subclass rather than a new return type: ``str`` is the contract every caller already
    reads, so equality, ``in``, ``.strip()`` and ``json.loads(str(x))`` all keep working
    unchanged. The attributes carry what a string cannot hold -- which leg answered, why the
    text is unusable when it is, how much the server wrote -- which is what lets the query
    rewriter tell "the model answered nothing" apart from "the model answered something we
    cannot parse".
    """

    def __new__(
        cls,
        content: str = "",
        *,
        finish_reason: str = "",
        output_tokens: int | None = None,
        transport: str = TRANSPORT_COMPAT,
        error_code: str = "",
    ):
        reply = super().__new__(cls, "" if content is None else str(content))
        reply.finish_reason = str(finish_reason or "")
        reply.output_tokens = output_tokens
        reply.transport = transport
        reply.error_code = error_code
        return reply


class _NativeChatUnsupported(RuntimeError):
    """The server behind this base_url has no native chat API to speak of."""


def answer_error_code(content, finish_reason) -> str:
    """The stable code for "this answer cannot be used", or "" when it can.

    ``length`` is checked before emptiness because the two are different findings: a
    completion the server stopped at its cap says the budget or the thinking chain ate the
    answer, while a 200 that carries no text at all says the model simply did not talk.
    Collapsing them into one message is what made every rewrite failure in the field read as
    a JSON bug.
    """
    text = str(content or "").strip()
    if text == MODEL_UNAVAILABLE_REPLY:
        # That sentence is produced here, not by the model: reporting it as an answer that
        # came back unparseable would send an operator looking for a prompt bug on a machine
        # whose model server never answered at all.
        return MODEL_UNAVAILABLE_CODE
    reason = str(finish_reason or "").strip().lower()
    if reason == "length":
        return OUTPUT_TRUNCATED_CODE
    if not text:
        return RESPONSE_EMPTY_CODE
    return ""


def compat_reply(response) -> ModelReply:
    """Read a compatible-leg completion into the same verdict object the native leg returns.

    The old boundary handed back ``response.choices[0].message.content`` and nothing else, so
    a truncated answer and an empty one arrived identically dressed. Both facts are still on
    the response object; this only stops throwing them away.
    """
    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = str(getattr(message, "content", None) or "")
    finish_reason = str(getattr(choice, "finish_reason", "") or "")
    usage = getattr(response, "usage", None)
    return ModelReply(
        content,
        finish_reason=finish_reason,
        output_tokens=getattr(usage, "completion_tokens", None),
        transport=TRANSPORT_COMPAT,
        error_code=answer_error_code(content, finish_reason),
    )


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
        content = MODEL_UNAVAILABLE_REPLY
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
        #: One probe per process. A server that answers 404 on its native chat API is told so
        #: once and then never asked again, so a vLLM-style endpoint pays for the discovery
        #: exactly once instead of on every rewrite. See :meth:`_native_chat`.
        self._native_supported = True
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
        return ModelReply(content, error_code=RATE_LIMITED_CODE)

    def _release_after_stream(self, response, slot):
        try:
            yield from response
        finally:
            slot.release()

    @staticmethod
    def _native_chat_url(client) -> str:
        """Where this server's native chat API is, or "" for a transport we do not own.

        The handler builds its own OpenAI client from the configured base URL, so the Ollama
        root is that URL with the ``/v1`` prefix taken off. A caller that swaps in another
        object -- the offline client, a test double, a hand-built provider client -- only
        ever advertised ``chat.completions``, and inventing a second endpoint for a transport
        nobody configured here would be a way to send a company's questions to a server nobody
        chose. Such a caller keeps exactly the leg it implements.
        """
        if not isinstance(client, OpenAI):
            return ""
        base = str(getattr(client, "base_url", "") or "").strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base.rstrip('/')}{NATIVE_CHAT_SUFFIX}" if base else ""

    @staticmethod
    def _native_chat_request(url: str, payload: dict, *, timeout) -> dict:
        """One POST to the native endpoint, on a client that ignores ambient proxy settings.

        Same ``trust_env=False`` policy as :meth:`_build_http_client`: the model server of a
        private deployment lives on this machine, so a proxy from the environment must not be
        able to eat the request or answer it on the server's behalf.
        """
        with httpx.Client(trust_env=False) as http:
            response = http.post(url, json=payload, timeout=timeout)
        if response.status_code in NATIVE_REFUSED_STATUSES:
            raise _NativeChatUnsupported(f"HTTP {response.status_code}: {response.text[:200]}")
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise _NativeChatUnsupported(f"响应不是 JSON: {type(exc).__name__}") from exc
        return body if isinstance(body, dict) else {}

    def _native_chat(self, client, model, messages, budget, prompt_tokens):
        """The non-streaming answer, from Ollama's native API with thinking switched off.

        Returns ``None`` only when this call has to be made on the compatible leg after all:
        the transport is not ours to route, or the server has already refused the native API.
        Every other outcome is terminal for this call, because a request the server answered
        has already spent the GPU -- retrying it on a second leg would pay for the same
        completion twice and still hand back the worse of the two.
        """
        url = self._native_chat_url(client)
        if not url or not self._native_supported:
            return None

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            NATIVE_THINK_FIELD: False,
            "options": {NATIVE_MAX_TOKENS_FIELD: budget.max_tokens},
        }
        started = time.monotonic()
        try:
            body = self._native_chat_request(
                url, payload, timeout=http_timeout(budget, prompt_tokens, stream=False)
            )
        except _NativeChatUnsupported as exc:
            self._native_supported = False
            refused = context_error_code(exc)
            if refused:
                # A server that refuses this URL for length reasons says so the same way the
                # compatible one does, so it gets the same typed refusal rather than a
                # downgrade nobody asked for.
                self._log_budget_verdict(budget, prompt_tokens, refused)
                raise ModelContextLimitExceeded(budget, prompt_tokens or 0) from exc
            logger.warning(
                f"[Model] 服务端不支持原生 {NATIVE_CHAT_SUFFIX}（{exc}）："
                f"本进程后续非流式调用退回 {TRANSPORT_COMPAT} 腿"
            )
            return None
        except Exception as exc:
            return self._model_failure(
                exc, budget, prompt_tokens, stream=False, transport=TRANSPORT_NATIVE
            )

        message = body.get("message") or {}
        content = str(message.get("content") or "")
        thinking = str(message.get("thinking") or body.get("thinking") or "")
        finish_reason = str(body.get("done_reason") or "")
        output_tokens = body.get("eval_count")
        code = answer_error_code(content, finish_reason)
        logger.info(
            f"[Model] {TRANSPORT_NATIVE} 应答: seconds={time.monotonic() - started:.2f} "
            f"done_reason={finish_reason or 'none'} eval_count={output_tokens} "
            f"content_chars={len(content)} thinking_chars={len(thinking)}"
            + (f" error_code={code}" if code else "")
        )
        return ModelReply(
            content,
            finish_reason=finish_reason,
            output_tokens=output_tokens,
            transport=TRANSPORT_NATIVE,
            error_code=code,
        )

    @staticmethod
    def _log_budget_verdict(budget, prompt_tokens, code, stream=False):
        logger.warning(
            budget_signal(
                budget.tier,
                prompt_tokens=prompt_tokens,
                read_seconds=budget.timeout_seconds,
                code=code,
                stream=stream,
            )
        )

    def _model_failure(self, exc, budget, prompt_tokens, *, stream, transport=TRANSPORT_COMPAT):
        """The one verdict for "this call produced no answer", shared by both legs.

        Two outcomes have to stay exactly as the compatible leg always had them: a server
        that refuses for length reasons raises the typed budget error, anything else answers
        with the offline sentence. Sharing this between the legs is what keeps a second
        transport from inventing a second failure wording.
        """
        provider_code = context_error_code(exc)
        if provider_code:
            # The server refused for the same reason authorize_call checks for, so it
            # gets the same verdict: one collision, one code, whoever detected it.
            self._log_budget_verdict(budget, prompt_tokens, provider_code, stream=stream)
            raise ModelContextLimitExceeded(budget, prompt_tokens or 0) from exc
        logger.warning(f"[Model] provider unavailable: {exc}")
        if stream:
            return iter([_OfflineStreamChunk(MODEL_UNAVAILABLE_REPLY)])
        return ModelReply(
            MODEL_UNAVAILABLE_REPLY,
            transport=transport,
            error_code=MODEL_UNAVAILABLE_CODE,
        )

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

        if not stream:
            # A query rewrite is the only non-streaming caller on this boundary, and the
            # thinking-model collision is precisely its bug: 256 tokens of hidden chain of
            # thought leave no room for the JSON, so this call asks the native leg first.
            # ``None`` means the compatible leg is still the right one -- an injected
            # transport, or a server that has already refused the native API.
            try:
                native = self._native_chat(client, model, messages, budget, prompt_tokens)
            except BaseException:
                slot.release()
                raise
            if native is not None:
                slot.release()
                return native

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
            return self._model_failure(exc, budget, prompt_tokens, stream=stream)

        if stream:
            return self._release_after_stream(response, slot)
        try:
            return compat_reply(response)
        finally:
            slot.release()
