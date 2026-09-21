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

R29 asked whether that second half should move too, and measured the answer on this host instead
of assuming it: for one and the same prompt, the native leg with ``think:false`` returns zero
``thinking`` characters and about four hundred characters of *the same text* inside ``content``,
in the same wall time as the compatible leg. That pair was then re-measured on the request which
actually produced the 30.6 s ledger line -- ``scripts/perf_probe_think.py:gen_messages``, same
tool, same 400-token cap, eight questions, both legs warm: median wall 5.34 s native against
5.35 s compatible, ratio 0.9981, both arms spending the whole 400 tokens, the native arm
returning 667 characters of "好的，我现在需要回答用户…" where the compatible arm returned zero. The
flag relocates the reasoning, it does not stop it, so moving the answer leg here would not
collect the 思考税 of 跟进单 §21 R29 -- it would print the model's monologue into the customer's
answer stream, ahead of any ``[来源: ...]``, and pass ``answer_error_code`` as a finished answer.
One more reason it is not a one-line move: the two legs reject each other's tool-call history
(native 400s on a string ``arguments``, compatible 400s on an object) and LangChain's serializer
only ever emits the string. The streaming half stays where it is, and ``app/agents/nodes.py`` is
where the residency request (R34's other half, which R29 inherits and which is the one saving
this ticket could actually bank) now goes out.
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
from app.common.model_config import KeepAlivePolicy, get_local_model_settings, resolve_keep_alive

load_dotenv()

#: Ollama serves its own chat API on the same port, without the OpenAI-compatible /v1 prefix.
NATIVE_CHAT_SUFFIX = "/api/chat"
#: The native request field that stops a thinking model from thinking out loud.
NATIVE_THINK_FIELD = "think"
#: ``num_predict`` is the native spelling of this tier's ``max_tokens``.
NATIVE_MAX_TOKENS_FIELD = "num_predict"
#: The request field that tells the server how long to keep the model loaded after it has
#: answered. R34 is this one field on two legs: a cold load on the delivery machine costs
#: ~6.1 s of the server's own ``load_duration`` (measured 09-19), so a question that arrives
#: after the window closes pays it again. The window and its ceiling are configured in
#: app/common/model_config.py, which is also where "never unload" is refused -- this boundary
#: asks, the customer's memory decides, and an 8 GB laptop must be able to get its RAM back.
KEEP_ALIVE_FIELD = "keep_alive"
#: Which leg answered a call. A log line that cannot say this is not evidence of anything.
TRANSPORT_NATIVE = "ollama-native"
TRANSPORT_COMPAT = "openai-compat"
#: Statuses that mean "this server has no native chat API at all", as opposed to "not right
#: now". 429 and the 5xx family are deliberately absent from both halves below: they are
#: temporary, and retiring the leg over one overloaded afternoon would quietly downgrade
#: every request that follows.
#:
#: R147 split the one set this file used to carry. The two halves are different findings and
#: used to carry the same consequence. 404 / 405 / 410 say the endpoint is not there, so
#: asking again can only waste time. A 400 says the opposite -- the endpoint is there and
#: answered, and what it refused was the body we sent: measured on the host 2026-09-21, an
#: OpenAI-shaped ``tool_calls.arguments`` string handed to the native leg is answered with a
#: 400 naming the shape (``NATIVE_400_ON_STRING_ARGS`` in tests/test_r29_thinking_tax.py).
#: Retiring on that read a bug in our own payload as the server not having an API, and the
#: retirement lasted the rest of the process: every later rewrite lost the leg that asks for
#: no thinking chain, with nothing in the log to say which of the two happened.
NATIVE_PROTOCOL_ABSENT_STATUSES = frozenset({404, 405, 410})
#: Statuses that mean "this request body is not acceptable". The call goes to the compatible
#: leg and the native leg stays open, because the next body may well be fine.
NATIVE_REQUEST_REJECTED_STATUSES = frozenset({400})
#: Every status after which this call leaves the native leg. Being in this set is not a
#: reason to retire anything: that verdict belongs to
#: :data:`NATIVE_PROTOCOL_ABSENT_STATUSES` alone.
NATIVE_REFUSED_STATUSES = NATIVE_PROTOCOL_ABSENT_STATUSES | NATIVE_REQUEST_REJECTED_STATUSES

#: The named readings for what the native leg last told us (R147). "A 400 happened" has to be
#: tellable apart from "this server has no native API" without re-reading a warning line, so
#: every outcome writes one of these names on the handler in the same breath as it decides
#: whether to retire. ``NATIVE_VERDICT_UNTRIED`` is the state of a process that has never
#: asked, which is not the same as a process that asked and was refused.
NATIVE_VERDICT_UNTRIED = "untried"
NATIVE_VERDICT_ANSWERED = "answered"
NATIVE_VERDICT_PROTOCOL_ABSENT = "protocol_absent"
NATIVE_VERDICT_REQUEST_REJECTED = "request_rejected"
NATIVE_VERDICT_NOT_JSON = "response_not_json"

#: The offline sentence, spelled once. It was already written twice in this file, and both
#: legs have to answer with the same words for the same reason.
MODEL_UNAVAILABLE_REPLY = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"


def keep_alive_log(policy) -> str:
    """The residency request as one greppable field, with the clamp note attached.

    A value that was silently clamped is indistinguishable from a value that worked, which
    is how an operator ends up believing a machine is warm when it is not.
    """
    return policy.wire + (f" ({policy.note})" if policy.note else "")


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
    text is unusable when it is, how much the server read and wrote -- which is what lets the query
    rewriter tell "the model answered nothing" apart from "the model answered something we
    cannot parse".
    """

    def __new__(
        cls,
        content: str = "",
        *,
        finish_reason: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        transport: str = TRANSPORT_COMPAT,
        error_code: str = "",
    ):
        reply = super().__new__(cls, "" if content is None else str(content))
        reply.finish_reason = str(finish_reason or "")
        #: What the server itself counted, read side and write side (R38). Either one stays
        #: ``None`` when the server did not report it, which is what makes the metering
        #: column NULL instead of a zero or a number somebody estimated.
        reply.input_tokens = input_tokens
        reply.output_tokens = output_tokens
        reply.transport = transport
        reply.error_code = error_code
        return reply


class _NativeChatUnsupported(RuntimeError):
    """The server behind this base_url has no native chat API to speak of.

    R147: this is the *retiring* refusal. The endpoint is absent, or something that is not
    this API is answering for it, so no fix to our payload changes the outcome and the
    process stops asking. A server that has the endpoint and disliked our body raises
    :class:`_NativeChatRequestRejected` instead.
    """

    #: Named reading for a refusal that retires (R147).
    verdict = NATIVE_VERDICT_PROTOCOL_ABSENT

    def __init__(self, message: str, verdict: str | None = None):
        super().__init__(message)
        if verdict is not None:
            self.verdict = verdict


class _NativeChatRequestRejected(RuntimeError):
    """The native endpoint is there and answered -- it refused *this* body.

    A separate exception type rather than a flag on the one above, because the decision
    site would otherwise have to re-parse status codes out of a message string to tell "our
    payload is wrong" from "this server has no API". That parse is exactly the mistake R147
    is fixing: the two used to be one class, so the two were one consequence.
    """

    #: Named reading for a refusal that must not retire (R147).
    verdict = NATIVE_VERDICT_REQUEST_REJECTED


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

    R38 did the same for the counters: ``usage`` carries ``prompt_tokens`` next to
    ``completion_tokens``, and only the second one was being read, so a compatible-leg answer
    reported what the model wrote while the number the server had for what it read was
    dropped. Reading it is not the same as trusting it: a missing ``usage`` still answers
    ``None`` on both sides.
    """
    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = str(getattr(message, "content", None) or "")
    finish_reason = str(getattr(choice, "finish_reason", "") or "")
    usage = getattr(response, "usage", None)
    return ModelReply(
        content,
        finish_reason=finish_reason,
        input_tokens=getattr(usage, "prompt_tokens", None),
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
        #: One probe per process, for the one kind of refusal that justifies it. A server
        #: that answers 404 on its native chat API is told so once and then never asked
        #: again, so a vLLM-style endpoint pays for the discovery exactly once instead of on
        #: every rewrite. See :meth:`_native_chat`. R147 narrowed this to the protocol-absent
        #: half: a 400 about our own body is not evidence about the endpoint, so it moves one
        #: call and leaves the flag alone.
        self._native_supported = True
        #: The last thing the native leg told us, as a name (R147). See ``NATIVE_VERDICT_*``.
        self._native_verdict = NATIVE_VERDICT_UNTRIED
        #: How many times an endpoint that stayed open refused one of our bodies (R147).
        #: Counted rather than only logged, because "once" and "every call" are different
        #: incidents: the second one means a payload bug is live right now and silently
        #: paying for the compatible leg on every rewrite.
        self._native_request_rejections = 0
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

    def native_leg_readout(self) -> dict:
        """Where the native leg stands, as three names instead of a guess (R147).

        Before this there was one boolean, so "the server has no native API", "the server
        disliked my body", and "I have not asked yet" were all the same absence of a fact.
        An operator deciding whether to go look at a payload bug needs those three apart, and
        needs it without grepping a warning line that fires once per process by design.
        """
        return {
            "supported": self._native_supported,
            "verdict": self._native_verdict,
            "request_rejections": self._native_request_rejections,
        }

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
    def _keep_alive() -> KeepAlivePolicy:
        """How long a call on either leg asks the model to stay resident.

        Resolved through the one module that reads configuration, and resolved per call
        rather than cached on the instance: the clamp notice has to travel with the request
        it explains, and an operator who edits the variable between two questions should not
        have to restart the service to learn whether it took. Both legs are asked the same
        window because the caller who tunes it should not have to know which transport
        answered -- whether the compatible leg honours it at all is a server fact, measured
        and written up in docs/handoff/2026-09-19-r34-keep-alive-residency.md.
        """
        return resolve_keep_alive()

    @staticmethod
    def _native_chat_request(url: str, payload: dict, *, timeout) -> dict:
        """One POST to the native endpoint, on a client that ignores ambient proxy settings.

        Same ``trust_env=False`` policy as :meth:`_build_http_client`: the model server of a
        private deployment lives on this machine, so a proxy from the environment must not be
        able to eat the request or answer it on the server's behalf.
        """
        with httpx.Client(trust_env=False) as http:
            response = http.post(url, json=payload, timeout=timeout)
        # Classified by status, at the one place that has the status. The two sets mean
        # different things and the caller decides retirement from the exception type, so
        # neither verdict is re-derived from text (R147).
        if response.status_code in NATIVE_PROTOCOL_ABSENT_STATUSES:
            raise _NativeChatUnsupported(f"HTTP {response.status_code}: {response.text[:200]}")
        if response.status_code in NATIVE_REQUEST_REJECTED_STATUSES:
            raise _NativeChatRequestRejected(f"HTTP {response.status_code}: {response.text[:200]}")
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            # Kept on the retiring side, deliberately: a body that is not JSON at all means
            # something other than this API is answering the URL -- a proxy, a login page, a
            # captive portal. No change to our payload makes a non-answer into an answer, so
            # this is a standing fact about the endpoint, not about one request.
            raise _NativeChatUnsupported(
                f"响应不是 JSON: {type(exc).__name__}", NATIVE_VERDICT_NOT_JSON
            ) from exc
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
            KEEP_ALIVE_FIELD: self._keep_alive().wire,
        }
        started = time.monotonic()
        try:
            body = self._native_chat_request(
                url, payload, timeout=http_timeout(budget, prompt_tokens, stream=False)
            )
        except _NativeChatRequestRejected as exc:
            # R147: our body was refused. This call moves; the leg does not retire.
            self._native_request_rejections += 1
            self._native_verdict = exc.verdict
            refused = context_error_code(exc)
            if refused:
                self._log_budget_verdict(budget, prompt_tokens, refused)
                raise ModelContextLimitExceeded(budget, prompt_tokens or 0) from exc
            logger.warning(
                f"[Model] 原生 {NATIVE_CHAT_SUFFIX} 拒收本次报文形状（{exc}）："
                f"本次退回 {TRANSPORT_COMPAT} 腿，原生腿不退役"
                f"（verdict={exc.verdict} request_rejections={self._native_request_rejections}）"
            )
            return None
        except _NativeChatUnsupported as exc:
            self._native_supported = False
            self._native_verdict = exc.verdict
            refused = context_error_code(exc)
            if refused:
                # A server that refuses this URL for length reasons says so the same way the
                # compatible one does, so it gets the same typed refusal rather than a
                # downgrade nobody asked for.
                self._log_budget_verdict(budget, prompt_tokens, refused)
                raise ModelContextLimitExceeded(budget, prompt_tokens or 0) from exc
            logger.warning(
                f"[Model] 服务端不支持原生 {NATIVE_CHAT_SUFFIX}（{exc}）："
                f"本进程后续非流式调用退回 {TRANSPORT_COMPAT} 腿（verdict={exc.verdict}）"
            )
            return None
        except Exception as exc:
            return self._model_failure(
                exc, budget, prompt_tokens, stream=False, transport=TRANSPORT_NATIVE
            )

        self._native_verdict = NATIVE_VERDICT_ANSWERED
        message = body.get("message") or {}
        content = str(message.get("content") or "")
        thinking = str(message.get("thinking") or body.get("thinking") or "")
        finish_reason = str(body.get("done_reason") or "")
        #: The server's own two counters (R38). ``prompt_eval_count`` is what it read and
        #: ``eval_count`` is what it wrote; the read side used to be dropped here, which left
        #: ``model_calls.input_tokens`` without a source on this leg. Neither is ever
        #: substituted by an estimate: the durations below are logged next to them for
        #: comparison only, and ``estimate_prompt_tokens`` sizes clocks, not the ledger.
        input_tokens = body.get("prompt_eval_count")
        output_tokens = body.get("eval_count")
        code = answer_error_code(content, finish_reason)
        load_seconds = float(body.get("load_duration") or 0) / 1e9
        logger.info(
            f"[Model] {TRANSPORT_NATIVE} 应答: seconds={time.monotonic() - started:.2f} "
            f"load_seconds={load_seconds:.2f} "
            f"keep_alive={keep_alive_log(self._keep_alive())} "
            f"done_reason={finish_reason or 'none'} "
            f"prompt_eval_count={input_tokens} eval_count={output_tokens} "
            f"content_chars={len(content)} thinking_chars={len(thinking)}"
            + (f" error_code={code}" if code else "")
        )
        return ModelReply(
            content,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
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
        keep_alive = self._keep_alive()
        logger.info(f"使用内部本地模型: {model} keep_alive={keep_alive_log(keep_alive)}")

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
                # The compatible leg gets the same request it would make without this line,
                # plus residency. Whether the server honours keep_alive is a server fact, and on
                # this one it does not: /v1 on Ollama 0.34.2 ignores the field outright (measured
                # 2026-09-21 from /api/ps -- 1200 s survived a compat call asking for 20m, one
                # asking for nothing, and one asking for 1800s). Asking anyway costs nothing and
                # keeps both legs stating the same window in the same request.
                extra_body={KEEP_ALIVE_FIELD: keep_alive.wire},
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
