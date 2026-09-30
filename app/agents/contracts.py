from typing import Any, Literal

from dataclasses import dataclass
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class Principal(BaseModel):
    """The single authenticated subject carried across API, Agent, and audit boundaries."""

    user_id: str
    username: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    department: str = ""
    department_ids: list[str] = Field(default_factory=list)
    clearance: int = 1
    clearance_label: str = "internal"
    status: str = "active"
    auth_source: str = "local"
    is_system: bool = False
    request_id: str = ""

    @property
    def role(self) -> str:
        return self.roles[0] if self.roles else "staff"

    @classmethod
    def from_user(cls, user: dict[str, Any], *, auth_source: str = "local"):
        from app.common.permissions import permissions_for_role
        from app.common.rbac import clearance_for

        role = str(user.get("role") or "staff")
        return cls(
            user_id=str(user.get("id") or user.get("username") or ""),
            username=str(user.get("username") or ""),
            roles=[role],
            permissions=sorted(user.get("permissions") or permissions_for_role(role)),
            department=str(user.get("department") or ""),
            department_ids=[str(value) for value in (user.get("department_ids") or [])],
            clearance=int(user.get("clearance") or clearance_for(role)),
            clearance_label=str(user.get("clearance_label") or role),
            status=str(user.get("status") or "active"),
            auth_source=auth_source,
            is_system=bool(user.get("is_system", False)),
        )


class ResourceScope(BaseModel):
    """The authorization attributes attached to a protected resource."""

    resource_type: str
    resource_id: str | None = None
    owner_id: str | None = None
    department_ids: list[str] = Field(default_factory=list)
    classification: str = "internal"
    visibility: str = "private"
    version_id: str | None = None
    status: str = "active"


class AuthorizationDecision(BaseModel):
    allowed: bool
    reason_code: str
    policy_version: str = ""
    matched_rules: list[str] = Field(default_factory=list)
    audit_required: bool = True


class ModelTier(StrEnum):
    """Every local-model call belongs to one tier, and every tier carries its own budget.

    The list is the enumeration of the call sites that exist in ``app/**``. A tier with no
    caller is the same dead contract as an unassigned field, so
    ``tests/test_r30_model_tiers.py`` fails when one is added without a call site.
    """

    #: chitchat answer -- app/agents/nodes.py respond
    CHAT = "chat"
    #: compound-question split -- app/agents/nodes.py plan
    PLAN = "plan"
    #: short-term memory compression -- app/agents/orchestrator.py main_agent_node
    COMPRESS = "compress"
    #: retrieval follow-up rewrite -- app/common/model_handler.py chat (non-streaming)
    REWRITE = "rewrite"
    #: pandas / SQL expression synthesis -- app/agents/tools.py _llm_pandas_code
    CODE = "code"
    #: alert attribution -- app/api/v1/alerts.py _ai_analysis
    ALERT = "alert"
    #: analysis prose -- doc/data/chart/export workers plus supervisor routing
    ANALYSIS = "analysis"


DEFAULT_MODEL_TIER = ModelTier.ANALYSIS

#: A stream is not one long read: bytes keep arriving, so its read budget is an inter-chunk
#: stall allowance. This many tokens of decode is the most a stall may cost before the call
#: is declared wedged.
STREAM_STALL_TOKENS = 64

#: Budget verdicts. Deliberately NOT members of ``ErrorEnvelope``: they describe one model
#: call, not a client-facing failure class, and the public code vocabulary is R64's to grow.
CONTEXT_LIMIT_CODE = "context_limit_exceeded"
OUTPUT_TRUNCATED_CODE = "model_output_truncated"
#: Every line these budgets write is greppable by exactly one marker.
MODEL_BUDGET_MARKER = "[ModelBudget]"


def prompt_room(context_limit_tokens: int, declared_max_tokens: int) -> int:
    """How large a prompt may be when an answer of ``declared_max_tokens`` shares the window.

    R463 judgement (1) is about *where this is computed*. The window holds prompt plus answer,
    so the room left for material is the window minus the tier's own declared output cap -- and
    that one subtraction used to be written four times in four shapes:

    * ``ModelBudget.input_budget_tokens``                ``max(1, context_limit_tokens - max_tokens)``
    * ``ModelBudget.context_window_code``                 ``prompt + max_tokens <= context_limit_tokens``
    * ``ModelContextLimitExceeded.prompt_room_tokens``    ``max(1, context_limit - declared_max_tokens)``
    * ``WindowPlan.prompt_room_tokens``                   ``max(0, context_limit - declared_max_tokens)``

    The packing path consumed the first and the pre-request guard evaluated the second, so
    nothing made the two agree except that somebody had retyped the same algebra. 跟进单 §133 五
    read a prompt of ``prompt_tokens=14928`` built against ``MODEL_CONTEXT_TOKENS=16384`` and
    refused as ``required_n_ctx=16464``: the leg that fills a prompt and the leg that refuses
    one were arguing about a number neither of them owned. Every reader now goes through here.

    Deliberately a *strict* difference, not ``max(1, ...)``: a tier that declares an answer
    larger than its window must be told that nothing fits, while the timeout arithmetic beside
    it needs a positive number to divide by. That floor belongs to
    :attr:`ModelBudget.input_budget_tokens`, which now derives from this function.
    """
    return int(context_limit_tokens) - int(declared_max_tokens)


class ModelBudget(BaseModel):
    """One tier's explicit output cap plus the timeout budget that cap implies.

    This is the contract that used to be hollow: ``max_tokens`` was declared here and
    assigned nowhere in ``app/**``, while every real call handed one bare scalar to both
    ``ChatOpenAI(timeout=...)`` and ``httpx.Client(timeout=...)``. That scalar paid for
    prefill (reading the prompt) and decode (writing the answer) out of a single wall
    clock, so a longer prompt was more likely to be cut off mid-answer than to be given
    more time. Everything here is therefore accounted in two halves:

    ``prefill_seconds = prompt_tokens / prefill_tokens_per_second``
    ``decode_seconds  = max_tokens / decode_tokens_per_second``
    ``read_timeout    = clamp(margin * (prefill + decode), floor, ceiling)``

    The rates, margin, floor, ceiling and context window come from configuration (see
    ``app/common/model_budget.py`` and ``.env.example``), so an operator on a slower CPU
    raises two documented numbers instead of guessing a timeout. ``max_concurrency`` stays
    unfilled on purpose: slot semantics belong to the machine-wide budget (R23), not to a
    per-tier profile.
    """

    tier: ModelTier = DEFAULT_MODEL_TIER
    #: Explicit output cap; resolved from the configured tier when unset.
    max_tokens: int | None = None
    #: Wall-clock allowance for one request at this tier's largest permitted prompt.
    timeout_seconds: float | None = None
    max_concurrency: int | None = None
    #: ``n_ctx`` of the local server: prompt plus declared output must fit inside it.
    #: R255: this is a *claim about the server*, not a control that resizes it. The window
    #: Ollama actually serves is configured on the server, and this repository sends no
    #: ``num_ctx`` in any request payload (R135 read the same fact through
    #: ``/api/v1/model-budget/facts``), so raising this number alone makes the claim false:
    #: the prompt that used to be refused here goes out and comes back as the server's own
    #: HTTP 400. The numbers that have to move with it -- clock, queue, slots -- are derived
    #: in one place, ``app/common/model_budget.py:window_plan``.
    context_limit_tokens: int | None = None
    prefill_tokens_per_second: float | None = None
    decode_tokens_per_second: float | None = None
    timeout_margin: float | None = None
    timeout_floor_seconds: float | None = None
    timeout_ceiling_seconds: float | None = None
    connect_timeout_seconds: float | None = None

    @model_validator(mode="after")
    def _resolve_unset_limits_from_configuration(self) -> "ModelBudget":
        """An unset number means "the configured value for this tier", never "unlimited"."""
        from app.common.model_budget import tier_profile

        for name, value in tier_profile(self.tier).items():
            if getattr(self, name) is None:
                setattr(self, name, value)
        if self.timeout_seconds is None:
            self.timeout_seconds = self.read_timeout_seconds(self.input_budget_tokens)
        return self

    @property
    def prompt_room_tokens(self) -> int:
        """The prompt size THIS tier's own declared cap leaves inside the window.

        This is the available amount, computed once (see :func:`prompt_room`). The pre-request
        guard judges against it and the packing path fills against it, so a payload the packer
        delivered is never refused for being too big by the guard downstream: the only way a
        packed prompt can still collide is if the prompt *outside* the payload is bigger than
        the number the packer was handed -- which is why :meth:`pack_room_tokens` takes it.
        """
        return prompt_room(self.context_limit_tokens, self.max_tokens)

    @property
    def input_budget_tokens(self) -> int:
        """The largest prompt this tier may send and still fit its own output cap.

        The ``max(1, ...)`` is here for the clock, which divides by this number; the window
        judgement uses :attr:`prompt_room_tokens` and keeps the strict difference.
        """
        return max(1, self.prompt_room_tokens)

    def pack_room_tokens(self, prefix_tokens: int) -> int:
        """What one packed payload may occupy in a prompt billed by THIS tier.

        The only door from the packing side to the window (R463 judgement (1)). The number it
        subtracts from is the guard's own :attr:`prompt_room_tokens`; the number handed in is
        the rest of that prompt -- measured with ``estimate_text_tokens`` by a caller that can
        see the whole message list, or the pinned reserves beside the packing code by a tool
        leg that never sees the system segment. Either way the largest prompt the packer can
        emit is a subset of what :meth:`context_window_code` accepts, because both read one
        line of arithmetic instead of two copies of it.
        """
        return max(0, self.prompt_room_tokens - max(0, int(prefix_tokens)))

    def prefill_seconds(self, prompt_tokens: int | None = None) -> float:
        tokens = self.input_budget_tokens if prompt_tokens is None else max(0, int(prompt_tokens))
        return tokens / max(0.1, float(self.prefill_tokens_per_second))

    def decode_seconds(self, *, stream: bool = False) -> float:
        tokens = min(self.max_tokens, STREAM_STALL_TOKENS) if stream else self.max_tokens
        return tokens / max(0.1, float(self.decode_tokens_per_second))

    def read_timeout_seconds(self, prompt_tokens: int | None = None, *, stream: bool = False) -> float:
        """The prompt-scaled read budget that replaces the old single scalar.

        Monotonic in ``prompt_tokens`` by construction: a bigger prompt buys a bigger clock,
        up to the configured ceiling.
        """
        needed = (self.prefill_seconds(prompt_tokens) + self.decode_seconds(stream=stream)) * float(
            self.timeout_margin
        )
        return min(max(needed, float(self.timeout_floor_seconds)), float(self.timeout_ceiling_seconds))

    def fits_within_timeout(self, prompt_tokens: int | None = None, *, stream: bool = False) -> bool:
        """False when the ceiling had to cut this tier's own prefill+decode estimate short."""
        needed = (self.prefill_seconds(prompt_tokens) + self.decode_seconds(stream=stream)) * float(
            self.timeout_margin
        )
        return needed <= float(self.timeout_ceiling_seconds) + 1e-9

    def context_window_code(self, prompt_tokens: int | None) -> str | None:
        """Stable code for "this call cannot fit n_ctx", or None when it can.

        ``None`` also means "prompt size unknown", which is why the guard judges a number
        rather than guessing at a message list.

        R463: the judgement is ``prompt <= prompt_room_tokens``, the same number the packing
        path filled against. ``prompt + cap <= window`` and ``prompt <= window - cap`` are the
        same integer statement, so nothing about which call is refused changes -- what changes
        is that there is now one place that computes the boundary rather than two that retype
        it, and the packing path can no longer be one token out of agreement with this guard.
        """
        if prompt_tokens is None:
            return None
        if int(prompt_tokens) <= self.prompt_room_tokens:
            return None
        return CONTEXT_LIMIT_CODE

    def required_context_tokens(self, prompt_tokens: int | None) -> int:
        """The smallest ``n_ctx`` that would hold this prompt plus this tier's declared cap.

        Read it with :meth:`context_window_code`, never instead of it: this is arithmetic
        about a refusal that has already been decided, and an operator who raises the window
        to exactly this number has fitted one prompt and fixed nothing about the next.
        """
        return max(0, int(prompt_tokens or 0)) + int(self.max_tokens)

    def context_overage_tokens(self, prompt_tokens: int | None) -> int:
        """How far past the window this call is, in tokens; 0 when it is inside it.

        The 2026-09-25 real window refused ``prompt_tokens=2691`` and ``2778`` against
        ``n_ctx=4096`` (跟进单 run8 相 2 判读 §2) and named three numbers with no distance
        between them, so the reader had to do the subtraction at three in the morning to
        learn the one thing that mattered: the parameters are small, by 131 and 218 tokens.
        """
        return max(0, self.required_context_tokens(prompt_tokens) - int(self.context_limit_tokens))


#: ==================== R535: the claimed window and the served window ====================
#:
#: One number, two owners. ``MODEL_CONTEXT_TOKENS`` is the window this process computes
#: against (read at ``app/common/model_budget.py:context_limit_tokens``); the window a request
#: is actually served inside belongs to the model server. This product puts no ``num_ctx`` in
#: any payload -- ``app/common/model_handler.py`` sends ``num_predict`` on the native leg and
#: ``app/agents/nodes.py`` sends ``max_tokens`` on the compatible one -- so the server decides
#: its own half by its own default, and the two halves agree only while nobody edits one side.
#:
#: R255 made a refusal legible from the config side. R535 makes the *pair* legible, because
#: both directions are live failures on a real machine, not hypotheses: declared above served
#: turns a refusal that used to cost nothing into a round trip the server answers with its own
#: HTTP 400, and every question queued behind it waits for that; declared below served leaves
#: capacity the customer is already paying for unused while their real-sized document is
#: refused at this guard.
#:
#: These verdicts are deliberately NOT members of :class:`ErrorEnvelope`: they describe a pair
#: of readings, not a client-facing failure class, and the public code vocabulary is R64's to
#: grow. :data:`CONTEXT_LIMIT_CODE` above stays the only code a refusal carries, with the
#: semantics ``tests/test_r30_context_limit_guard.py`` pins; nothing below widens, renames,
#: reroutes or launders it.
CONTEXT_PAIRING_MARKER = "[ContextPairing]"

#: The two keys that have to move together, spelled the way an operator types them.
CONTEXT_WINDOW_ENV_KEY = "MODEL_CONTEXT_TOKENS"
RUNTIME_WINDOW_ENV_KEY = "num_ctx"
MIN_ANSWER_ENV_KEY = "MODEL_MIN_ANSWER_TOKENS"

#: Exactly four verdicts. ``runtime_unread`` is never spelled ``paired``: "nobody looked at
#: the server" is not evidence that the two numbers agree.
PAIRING_PAIRED = "paired"
PAIRING_ENV_ABOVE_RUNTIME = "env_above_runtime"
PAIRING_RUNTIME_ABOVE_ENV = "runtime_above_env"
PAIRING_RUNTIME_UNREAD = "runtime_unread"

#: The two directions that name something an operator has to act on.
PAIRING_ACTIONABLE = frozenset({PAIRING_ENV_ABOVE_RUNTIME, PAIRING_RUNTIME_ABOVE_ENV})

#: How much wider the served window must be before the gap is worth calling idle capacity.
#: A constant, not a knob: doubling is the only hop with a recorded measurement beside it
#: (``.env.example``, 附注在 ``MODEL_CONTEXT_TOKENS`` 上方：同一条 2154-token prompt 在
#: ``num_ctx`` 4096 与 8192 下 prefill 66.683 s / 68.849 s)，所以本闸不承认「白留着」一个
#: 从没被证明过得去的目标；差一枚是服务端的取整噪声，不是一条结论。
PAIRING_SLACK_RATIO = 2


@dataclass(frozen=True)
class ContextPairing:
    """Both window readings, plus the sentence that names which side has gone stale.

    Every field is a count or a name, and that is load-bearing rather than tidy: this object
    gets printed beside a refused customer question, so the only way to guarantee that no
    document text rides along is to make the builder structurally unable to accept text
    (R535 judgement 3).
    """

    verdict: str
    #: What this process claims the window is, and whether anybody wrote it down.
    declared_window_tokens: int
    declared_window_source: str
    #: What the server actually serves; ``None`` when nobody has observed it.
    runtime_window_tokens: int | None
    runtime_window_source: str
    #: The tier whose numbers make the claim worth checking at all.
    tier: str
    declared_max_tokens: int
    prompt_room_tokens: int
    min_answer_tokens: int
    #: Distance between the two windows in tokens; 0 when they agree or one side is unread.
    delta_tokens: int
    #: True only where the server is at least :data:`PAIRING_SLACK_RATIO` times the claim.
    idle_capacity: bool
    #: The widest window the clock and queue still pay for, read off ``WindowPlan``. Quoted,
    #: never recomputed here -- R463 keeps that arithmetic in exactly one place.
    coherent_ceiling_tokens: int | None
    keys: tuple[str, ...]
    sentence: str

    @property
    def actionable(self) -> bool:
        """True for the two directions an operator has to act on."""
        return self.verdict in PAIRING_ACTIONABLE

    def as_dict(self) -> dict[str, Any]:
        """A JSON-shaped reading for a caller that already exists. Opens nothing."""
        return {
            "verdict": self.verdict,
            "declared_window_tokens": self.declared_window_tokens,
            "declared_window_source": self.declared_window_source,
            "runtime_window_tokens": self.runtime_window_tokens,
            "runtime_window_source": self.runtime_window_source,
            "tier": self.tier,
            "declared_max_tokens": self.declared_max_tokens,
            "prompt_room_tokens": self.prompt_room_tokens,
            "min_answer_tokens": self.min_answer_tokens,
            "delta_tokens": self.delta_tokens,
            "idle_capacity": self.idle_capacity,
            "coherent_ceiling_tokens": self.coherent_ceiling_tokens,
            "actionable": self.actionable,
            "keys": list(self.keys),
            "sentence": self.sentence,
        }


#: Wording kept apart from the verdict so the idle-capacity sentence still reads as one line.
COHERENT_CEILING_HINT = "钟与队还付得起到 {ceiling} 枚（max_coherent_n_ctx，出自 window_plan），过这一格就不是抬窗口的事。"


def evaluate_context_pairing(
    *,
    declared_window_tokens: int,
    runtime_window_tokens: int | None,
    declared_window_source: str = "",
    runtime_window_source: str = "",
    tier: str = "",
    declared_max_tokens: int = 0,
    min_answer_tokens: int = 0,
    coherent_ceiling_tokens: int | None = None,
) -> ContextPairing:
    """Judge the window this process claims against the window the server actually serves.

    Pure, and blind to content by construction: every argument is an integer or a name, so
    there is no channel through which a customer document could reach the log.

    The judgement has two directions and both are asked for by this ticket.
    ``env_above_runtime`` is the one that costs money: the guard sizes against a window the
    server does not have, so prompts that used to be refused here for free go out and come
    back as the server's own HTTP 400 (``docs/perf/raw/rate_prefill.jsonl`` records that
    answer). ``runtime_above_env`` is the one the customer feels: the server would hold more
    than this process is willing to send, so a real-sized document is refused at the guard
    while the capacity sits idle. Equal windows are ``paired`` and say nothing further; an
    unobserved server is ``runtime_unread``, which is neither a pass nor a failure.

    The subtraction that produces ``prompt_room_tokens`` is :func:`prompt_room` -- the same
    single home the guard and the packing path already share (R463), not a fourth copy.
    """
    declared = int(declared_window_tokens)
    cap = int(declared_max_tokens)
    room = prompt_room(declared, cap)
    floor = int(min_answer_tokens)
    keys = (CONTEXT_WINDOW_ENV_KEY, RUNTIME_WINDOW_ENV_KEY)
    ceiling = None if coherent_ceiling_tokens is None else int(coherent_ceiling_tokens)

    if not runtime_window_tokens or int(runtime_window_tokens) <= 0:
        return ContextPairing(
            verdict=PAIRING_RUNTIME_UNREAD,
            declared_window_tokens=declared,
            declared_window_source=declared_window_source,
            runtime_window_tokens=None,
            runtime_window_source=runtime_window_source or "not_observed",
            tier=tier,
            declared_max_tokens=cap,
            prompt_room_tokens=room,
            min_answer_tokens=floor,
            delta_tokens=0,
            idle_capacity=False,
            coherent_ceiling_tokens=ceiling,
            keys=keys,
            sentence=(
                f"只读到一侧：{CONTEXT_WINDOW_ENV_KEY}={declared}"
                f"（来源 {declared_window_source or '未知'}），运行时那一侧没有读数"
                f"（{runtime_window_source or '未探测'}）。缺席不判配套、也不判不配套；"
                f"要出结论得两枚一起读：{CONTEXT_WINDOW_ENV_KEY} 与 服务端 {RUNTIME_WINDOW_ENV_KEY}。"
            ),
        )

    runtime = int(runtime_window_tokens)
    if runtime < declared:
        return ContextPairing(
            verdict=PAIRING_ENV_ABOVE_RUNTIME,
            declared_window_tokens=declared,
            declared_window_source=declared_window_source,
            runtime_window_tokens=runtime,
            runtime_window_source=runtime_window_source,
            tier=tier,
            declared_max_tokens=cap,
            prompt_room_tokens=room,
            min_answer_tokens=floor,
            delta_tokens=declared - runtime,
            idle_capacity=False,
            coherent_ceiling_tokens=ceiling,
            keys=keys,
            sentence=(
                f"不配套：{CONTEXT_WINDOW_ENV_KEY}={declared}（来源 {declared_window_source or '未知'}）"
                f"声明得比运行时给得起的多，服务端只到 {runtime}"
                f"（来源 {runtime_window_source}），差 {declared - runtime} 枚。"
                f"守卫按 {declared} 放行、服务端按 {runtime} 拒收：本该零成本挡下的一问变成一发白烧的"
                f"往返，排在它后面的每一问都跟着等。要一起动的两枚键：{CONTEXT_WINDOW_ENV_KEY} 与"
                f" 服务端 {RUNTIME_WINDOW_ENV_KEY}——本仓从不把后者写进请求载荷，服务端那一侧只能在"
                f"服务端改；把声明那一枚摘回 {runtime} 也算配套，但那是把容量还回去，不是解决问题。"
            ),
        )
    if runtime > declared:
        idle = declared > 0 and runtime >= declared * PAIRING_SLACK_RATIO
        lead = (
            f"白留着容量：运行时给到 {runtime}（来源 {runtime_window_source}），"
            f"而 {CONTEXT_WINDOW_ENV_KEY}={declared}（来源 {declared_window_source or '未知'}）"
            f"只肯声明 {declared}，多出的 {runtime - declared} 枚一个字都没用上。"
            if idle
            else f"运行时比声明宽 {runtime - declared} 枚（{runtime} 对 {declared}，"
            f"来源 {runtime_window_source}）——还没到「白留着」那一格（不足 {PAIRING_SLACK_RATIO} 倍）。"
        )
        coherence = (
            f"抬之前先看钟与队付不付得起：{COHERENT_CEILING_HINT.format(ceiling=ceiling)}"
            if ceiling is not None
            else ""
        )
        return ContextPairing(
            verdict=PAIRING_RUNTIME_ABOVE_ENV,
            declared_window_tokens=declared,
            declared_window_source=declared_window_source,
            runtime_window_tokens=runtime,
            runtime_window_source=runtime_window_source,
            tier=tier,
            declared_max_tokens=cap,
            prompt_room_tokens=room,
            min_answer_tokens=floor,
            delta_tokens=runtime - declared,
            idle_capacity=idle,
            coherent_ceiling_tokens=ceiling,
            keys=keys,
            sentence=(
                lead
                + f"本档声明输出 {cap}，守卫只给资料留 {room} 枚——客户真尺寸的文档撞的就是这一格。"
                + coherence
                + f"要一起动的两枚键：{CONTEXT_WINDOW_ENV_KEY} 与 服务端 {RUNTIME_WINDOW_ENV_KEY}"
                f"（这一头服务端已给得起，抬声明那一枚才叫配套）；改完要 recreate 容器。"
            ),
        )
    return ContextPairing(
        verdict=PAIRING_PAIRED,
        declared_window_tokens=declared,
        declared_window_source=declared_window_source,
        runtime_window_tokens=runtime,
        runtime_window_source=runtime_window_source,
        tier=tier,
        declared_max_tokens=cap,
        prompt_room_tokens=room,
        min_answer_tokens=floor,
        delta_tokens=0,
        idle_capacity=False,
        coherent_ceiling_tokens=ceiling,
        keys=keys,
        sentence=(
            f"配套：{CONTEXT_WINDOW_ENV_KEY}={declared} 与服务端 {RUNTIME_WINDOW_ENV_KEY}={runtime}"
            f" 是同一枚数（运行时来源 {runtime_window_source}）。"
        ),
    )




def context_refusal_attribution(
    budget: ModelBudget | None,
    prompt_tokens: int | None,
    pairing: ContextPairing | None = None,
) -> str:
    """The diagnosable half of a window refusal: two numbers and the two keys behind them.

    R535 judgement 3. Nothing about the verdict moves: the refusal still happens before the
    request goes on the wire, :data:`CONTEXT_LIMIT_CODE` still means what R30 ratified, it is
    still never laundered through the offline sentence, and the ``[ModelBudget]`` line keeps
    its registered one-line shape (``tests/test_r30_context_limit_guard.py`` pins one grep,
    one finding). What was missing when a real customer hit the ceiling on a real machine is
    the layer that reads as *these parameters are small* rather than *this model is weak*:
    how many slots this question needs, how many the current budget actually leaves for
    material, and which two keys have to be moved together to change either number.

    No argument here is prose: ``prompt_tokens`` is a count from ``estimate_prompt_tokens``,
    never the text it counted, which is how "the attribution must not carry document content"
    is a structural property rather than a promise.
    """
    if budget is None:
        return ""
    prompt = max(0, int(prompt_tokens or 0))
    required = budget.required_context_tokens(prompt)
    over = budget.context_overage_tokens(prompt)
    line = (
        f"本问需要 {required} 枚 token 槽位（prompt {prompt} + 本档声明输出 {budget.max_tokens}），"
        f"当前 {CONTEXT_WINDOW_ENV_KEY}={budget.context_limit_tokens} 只给资料留 {budget.prompt_room_tokens} 枚，"
        f"还差 {over} 枚；要调的是 {CONTEXT_WINDOW_ENV_KEY} 与 服务端 {RUNTIME_WINDOW_ENV_KEY} 这两枚，"
        f"两枚必须配套动——单改一头要么没用要么把机器撑爆；改完要 recreate 容器"
        f"（env_file 在建容器那一刻才解析，单改文件与 docker restart 都不生效）。"
        f"{MIN_ANSWER_ENV_KEY} 不是窗口旋钮：没有一问是因为它被判拒的。"
    )
    if pairing is not None and pairing.actionable:
        line = f"{line} 配套自检：{pairing.sentence}"
    return line


class ArtifactRef(BaseModel):
    artifact_id: str
    artifact_type: str
    owner_id: str | None = None
    version_id: str | None = None
    download_url: str | None = None
    expires_at: str | None = None


class ErrorEnvelope(BaseModel):
    code: Literal[
        "authentication_required",
        "permission_denied",
        "authorization_unavailable",
        "account_unavailable",
        "resource_not_found",
        "validation_error",
        "conflict",
        "rate_limited",
        "queue_unavailable",
        "model_unavailable",
        # R30：本机 n_ctx 装不下「这条 prompt + 本档声明的输出」时吐的码。它不是可重试的错
        # （同一个提示词永远装不下），所以不进 evidence._RETRIABLE_CODES。出处有两条，都在
        # app/common/model_budget.py：authorize_call 在发请求前拦下，provider 自己拒了之后翻成
        # 同一个码；两条都由 tests/test_r30_context_limit_guard.py 钉住。缺的是
        # tests/test_error_code_vocabulary.py::RATIFIED 里同一行出处——那个文件不在本单写域内。
        "context_limit_exceeded",
        "retrieval_unavailable",
        "storage_unavailable",
        "task_timeout",
        "task_cancelled",
        "unsupported_file",
        "parse_failed",
        "index_publish_failed",
        # 以下 8 档不是新发明的码：它们在 R13(4) 之前就已由 app/api/v1 真实吐出，
        # 只是从没进过封闭枚举。逐条出处与被哪个函数抛，钉在
        # tests/test_error_code_vocabulary.py::RATIFIED —— 那里还有一条"删了 emit 点
        # 却忘了把码摘掉就响"的护栏，所以这份清单不会慢慢烂成无主字符串。
        # 放在 internal_error 之前：兜底码留在最后，读的人一眼能看出谁是兜底。
        "invalid_filename",
        "dataset_filename_conflict",
        "dataset_preview_failed",
        "unsupported_chart_type",
        "chart_generation_failed",
        "unsupported_export_format",
        "department_scope_required",
        "no_answer_produced",
        # R64：数据工具的两枚行级终态码。它们不是 rbac 内部 reason 名的别名，公开读法
        # 只有一句：row_scope_denied＝这些行存在，但在当前账号的行级可见范围之外；
        # no_visible_rows＝本轮一行可分析的都没有，至于为什么——这一枚不下结论。
        # emit 点在 app/agents/tools.py 的行级文案层旁边，逐码出处钉在
        # tests/test_error_code_vocabulary.py::RATIFIED。
        # 密级拦截那一枚**不在这里**：密级维度今天没有任何 emit 点（rbac 不判密级，
        # max_clearance 只存不用），而这一维的拒绝今天已由两枚在册码承担——越档回
        # clearance_insufficient、密级元数据缺失回 resource_scope_missing，本层再造一枚
        # 同义码就没有 emit 点可指（口径出处 docs/handoff/2026-09-17-human-gates.md 最后一节
        # 「H13 结案 ＋ A1/A3 裁定」：H13 已于 2026-09-28 结案＝甲；口径已写进契约
        # docs/api/contract-v1.md 的「## R467」节）⇒ 硬加进枚举必然被
        # test_no_ratified_code_is_invented 判红，或者逼出假 emit 点。登记见同一个测试文件。
        "row_scope_denied",
        "no_visible_rows",
        "internal_error",
    ]
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AgentContext(BaseModel):
    """Shared execution context. No worker may invent a second identity model.

    Identity, scope and trace only -- there is deliberately no model budget on this
    object, and none on ``AgentState`` either (R74). Two reasons, both structural:

    * Concurrency is machine-wide. The one semaphore that keeps a 14B model from being
      stampeded is ``app/common/model_budget.py:default_model_budget()``, because a
      private deployment runs exactly one model server shared by every request and
      every worker. A per-request object cannot arbitrate slots it does not own, so a
      caller that filled a budget in here would have throttled nothing.
    * Tokens and clock are per tier, not per request.
      ``app/agents/nodes.py:_make_model`` resolves them through ``model_tier_budget``
      and one request legitimately spans tiers: a query rewrite and the analysis
      answer that follows it do not share a cap. One budget object riding along the
      context would flatten all of them to whichever tier the entry point picked.

    Both fields used to exist, assigned by nothing and read by nothing, which is worse
    than absent: it read like a switch. ``tests/test_r74_dead_budget_field.py`` pins
    the published field set, so re-introducing one fails where it stands.
    """

    principal: Principal
    request_id: str
    trace_id: str
    task_id: str
    session_id: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    allowed_resource_scope: list[ResourceScope] = Field(default_factory=list)


class Evidence(BaseModel):
    source_type: Literal[
        "document",
        "dataset",
        "table",
        "chart",
        "rule",
        "calculation",
        "trace",
        "inference",
    ]
    source_id: str = ""
    source_name: str = ""
    document_version_id: str | None = None
    dataset_version_id: str | None = None
    index_version_id: str | None = None
    locator: str | dict[str, Any] = ""
    excerpt: str = ""
    score: float | None = None
    score_type: Literal["cosine", "bm25", "rrf", "rerank", "rule"] | None = None
    permission_checked: bool = False
    provenance_status: Literal["verified", "inferred", "unavailable"] = "unavailable"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricContext(BaseModel):
    metric_name: str
    definition: str
    metric_id: str = ""
    definition_version: str = ""
    formula: str = ""
    unit: str = ""
    currency: str | None = None
    period_type: str = ""
    timezone: str = ""
    time_granularity: str = ""
    source_file: str = ""
    source_scope: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    worker: str
    status: Literal[
        "success",
        "partial",
        "failed",
        "rejected",
        "timeout",
        "cancelled",
        "model_unavailable",
        "retrieval_unavailable",
    ]
    answer: str = ""
    task_id: str = ""
    request_id: str = ""
    trace_id: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    metrics: list[MetricContext] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_label: Literal["引用充分", "引用不足", "推测"] = "引用不足"
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRef | str] = Field(default_factory=list)
    duration_ms: int | None = None
    error: ErrorEnvelope | None = None


class ReviewResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    recommended_action: Literal[
        "accept",
        "retry_retrieval",
        "retry_analysis",
        "answer_with_warning",
    ]
    confidence: float = 0.0

