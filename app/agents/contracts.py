from typing import Any, Literal

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
    def input_budget_tokens(self) -> int:
        """The largest prompt this tier may send and still fit its own output cap."""
        return max(1, int(self.context_limit_tokens) - int(self.max_tokens))

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
        """
        if prompt_tokens is None:
            return None
        if int(prompt_tokens) + int(self.max_tokens) <= int(self.context_limit_tokens):
            return None
        return CONTEXT_LIMIT_CODE


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
        # max_clearance 只存不用），业主口径亦未裁（H13）⇒ 硬加进枚举必然被
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

