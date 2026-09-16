from typing import Any, Literal

from pydantic import BaseModel, Field


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


class ModelBudget(BaseModel):
    """Per-request model budget; limits are supplied by configuration."""

    max_calls: int | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    max_concurrency: int | None = None


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
        "internal_error",
    ]
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AgentContext(BaseModel):
    """Shared execution context. No worker may invent a second identity model."""

    principal: Principal
    request_id: str
    trace_id: str
    task_id: str
    session_id: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    allowed_resource_scope: list[ResourceScope] = Field(default_factory=list)
    model_budget: ModelBudget = Field(default_factory=ModelBudget)


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

