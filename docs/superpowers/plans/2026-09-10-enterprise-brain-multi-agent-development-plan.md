# 企业智脑多智能体并行开发实施计划

> **⚠️ 状态（2026-09-15 标注）**：**完成度未核实**。本文件不含任何进度标记，且 1323 行中的多数条目已被后续实现与验收覆盖或改写。
> **不得作为“功能是否已完成”的判断依据**（AGENTS.md 同此要求）。现状以 `docs/current-functionality-2026-09-10.md` + 其修订记录为准；前端以 `docs/frontend-plan-2026-09-14.md` 为准；跨端缺陷收口以 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 为准。
> 保留理由：其中的多 Agent 拆分方式与身份/权限约束仍是设计意图记录。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不覆盖现有未提交修改、不修改其他 Agent 所有文件、不过度占用本机 Ollama 资源的前提下，把“企业智脑”拆成可独立交付、可测试、可合并的多智能体开发项目。

**Architecture:** 采用“一个主集成 Agent + 多条领域 Agent 线 + 一个只读 Review Agent”的协作方式。主集成 Agent 独占公共契约、编排主流程和最终合并；领域 Agent 只修改自己的目录和测试；前端 Agent 继续独占 `frontend/`，后端通过 API、SSE、错误码和数据契约协作。所有生产数据边界、权限、版本、Trace 和来源信息必须通过结构化契约传递，不能依靠文件名、内存变量或固定演示值。

**Tech Stack:** Python 3.11、FastAPI、LangGraph、现有 Chroma 过渡检索、目标 PostgreSQL + PGVector + 本地文件存储 + Redis、本机 Ollama、Vue 3 + Vite + Element Plus、pytest、Docker Compose、Nginx。

## Global Constraints

- 当前工作区存在大量未提交修改，任何 Agent 不得 `reset --hard`、`checkout --`、删除或覆盖不属于自己的修改。
- 当前前端由其他 Agent 负责；本计划中的后端 Agent 不得修改 `frontend/`。
- 同一个文件同一时间只能由一个 Agent 负责；公共契约和主流程只能由主集成 Agent 修改。
- 当前 Chroma 只能作为过渡向量库；目标生产存储是 PostgreSQL、PGVector、本地文件存储和 Redis。
- 第一版模型管理只做本机 Ollama 自动发现、能力检测、用途选择、并发控制和降级；远程模型默认关闭。
- 不允许使用固定金额、固定部门、固定指标、固定阈值、固定模型名或固定演示数据冒充生产业务逻辑。
- 所有金额使用 `Decimal` 及明确货币；所有时间范围带时区、期间类型和边界；所有指标带公式、单位、来源和版本。
- 没有 `Principal`、资源所有权或授权范围时默认拒绝，禁止把 Agent、后台任务或缺失身份回退为 `admin`。
- 生成的图表、报告、导出文件和静态资源必须属于受控 `Artifact`，禁止通过公开 `/static/` 绕过权限。
- 每个长任务必须有任务 ID、状态、超时、取消、幂等键和可追踪结果；模型失败不能返回伪装成业务结论的文本。
- 真实 Ollama 推理测试只能在主集成线串行执行；领域 Agent 默认使用 Mock、Fake 或离线夹具。
- 测试使用临时目录、临时数据库或隔离命名空间，不污染现有 `chroma_db/`、`data/`、`documents/`、`static/`、`.env` 和用户模型。
- 不提交密钥、`.env`、模型文件、真实客户文档、Chroma 数据、日志和生成产物。
- 每个 Agent 完成时必须报告：变更文件、禁止触碰的文件、公开接口、测试命令、测试结果、未验证项、集成步骤和已知风险。
- API、SSE、数据库字段和公共模型变更必须先提交契约变更说明，由主集成 Agent 审核后才能实施。

---

## 1. 计划边界与当前基线

本计划不是对当前完成度的重新声明。当前能力以以下文件和当前源码为准：

- 当前功能盘点：[docs/current-functionality-2026-09-10.md](../../../docs/current-functionality-2026-09-10.md)
- 当前功能文档修订记录：[docs/current-functionality-2026-09-10-revision-log.md](../../../docs/current-functionality-2026-09-10-revision-log.md)
- 综合升级方案：[docs/superpowers/plans/2026-09-08-enterprise-brain-complete-upgrade-plan.md](2026-09-08-enterprise-brain-complete-upgrade-plan.md)
- 旧并行开发方案：[docs/superpowers/plans/2026-09-07-parallel-development-plan.md](2026-09-07-parallel-development-plan.md)
- 项目协作规则：[AGENTS.md](../../../AGENTS.md)

当前项目已存在基础代码或代码骨架，但不能直接视为生产闭环：

- FastAPI、登录、聊天、文档上传、Chroma 检索、BM25、RRF、查询改写、重排和 Excel/CSV 分析已有基础。
- `app/agents/contracts.py`、`app/quality/`、`app/approval/`、`app/insights/`、`app/dashboard/`、`app/semantics/`、`app/knowledge_graph/` 等目录已有不同程度的实现或骨架。
- 资源所有权、完整 RBAC/ABAC、会话隔离、文件上传安全、正式迁移、PGVector 生产链路、可靠 Redis 队列、Trace 持久化、评测闭环、真实审批闭环和完整备份恢复仍必须按当前源码重新验收。
- `docs/current-functionality-2026-09-10.md` 中的“已实现”“部分实现”“规划”和“无法确认”必须继续区分；测试文件名、历史日志和前端页面不能单独证明后端生产能力。

### 1.1 本计划交付物

本计划执行完成后，项目应得到：

1. 一套稳定的跨 Agent 公共契约；
2. 明确的源码、测试和文档所有权矩阵；
3. 可恢复的数据库、文件、队列、模型和 Trace 运行边界；
4. 可独立合并的领域模块；
5. 可追踪的集成顺序、验收标准和回滚方式；
6. 与当前前端 Agent 不冲突的 API/SSE 协作方式；
7. 一份可以直接复制给各个 Agent 的任务说明。

---

## 2. 协作拓扑

```text
                         ┌─────────────────────────────┐
                         │ Agent 0 主集成 / 公共契约     │
                         │ contracts + orchestrator     │
                         └──────────────┬──────────────┘
                                        │
       ┌──────────────┬─────────────────┼─────────────────┬──────────────┐
       │              │                 │                 │              │
 Agent 1 权限     Agent 2 存储       Agent 3 文件       Agent 4 RAG    Agent 5 模型性能
       │              │                 │                 │              │
       └──────────────┴─────────────────┼─────────────────┴──────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         │ Agent 6 队列 / Worker 运行时  │
                         │ Agent 7 Trace / 评测 / 后台   │
                         │ Agent 8 业务闭环               │
                         │ Agent 9 部署 / 安全 / 恢复     │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         │ 当前前端 Agent：只消费契约     │
                         │ Agent 10：只读 Review / 验收    │
                         └─────────────────────────────┘
```

### 2.1 分支和 Worktree 规则

- 主集成分支：`codex/enterprise-brain-integration`
- 领域分支统一使用：`codex/enterprise-brain-<domain>`
- Review 分支统一使用：`codex/enterprise-brain-review`
- 在当前工作区仍有未提交修改时，不得自动创建会覆盖这些修改的 Worktree。
- 创建 Worktree 前必须保存当前 `git status --short`、当前分支和变更文件清单；如无法建立可靠基线，先在独立分支中完成只读盘点和契约设计。
- Agent 不能直接向主集成分支推送；只能提交自己的分支，交由主集成 Agent 合并。
- 不使用 `git reset --hard`、`git clean -fd`、`git checkout --` 清理冲突。

### 2.2 文件锁规则

1. 公共文件在任务开始前登记所有权。
2. 领域 Agent 发现必须修改他人文件时，停止修改并提交“集成请求”，说明：
   - 需要修改的文件；
   - 修改原因；
   - 最小接口变化；
   - 是否可以通过适配器解决；
   - 对现有前端和测试的影响。
3. 主集成 Agent 负责公共文件的最终修改。
4. 发生冲突时以当前源码和已冻结契约为准，不以某个 Agent 的本地实现为准。

---

## 3. 公共契约冻结

公共契约由 Agent 0 负责，其他 Agent 只能消费，不能复制一套平行模型。契约应先在 `app/agents/contracts.py`、`app/agents/state.py` 和 `docs/superpowers/specs/` 中冻结，再由各领域实现。

### 3.1 Principal

```text
Principal
├── user_id: str
├── username: str
├── roles: list[str]
├── permissions: list[str]
├── department_ids: list[str]
├── clearance: str
├── status: str
├── auth_source: str
├── is_system: bool
└── request_id: str
```

规则：

- `user_id` 是资源、会话、审计和 Trace 的稳定主体标识。
- `is_system=True` 只允许用于显式声明的最小权限后台任务，不等于管理员。
- 身份缺失、身份状态未知、权限策略无法计算时都必须拒绝或返回明确的 `authorization_unavailable`。

### 3.2 ResourceScope 和授权结果

```text
ResourceScope
├── resource_type: str
├── resource_id: str | None
├── owner_id: str | None
├── department_ids: list[str]
├── classification: str
├── visibility: str
├── version_id: str | None
└── status: str

AuthorizationDecision
├── allowed: bool
├── reason_code: str
├── policy_version: str
├── matched_rules: list[str]
└── audit_required: bool
```

任何文档、数据集、图表、报告、审批、洞察、告警、会话、Trace、评测报告和工具调用结果都必须能映射到 `ResourceScope`。

### 3.3 AgentContext 和 AgentResult

```text
AgentContext
├── principal: Principal
├── request_id: str
├── session_id: str | None
├── trace_id: str
├── task_id: str
├── allowed_actions: list[str]
├── allowed_resource_scope: list[ResourceScope]
├── cancellation_token: str | None
└── model_budget: object

AgentResult
├── task_id: str
├── worker: str
├── status: str
├── answer: str | None
├── evidence: list[Evidence]
├── metrics: list[MetricContext]
├── warnings: list[str]
├── artifacts: list[ArtifactRef]
├── duration_ms: int | None
├── trace_id: str
└── error: ErrorEnvelope | None
```

结果状态必须能区分成功、部分成功、拒绝、超时、取消、模型不可用、检索不可用和内部失败，不能把失败文本伪装成正常答案。

### 3.4 Evidence、MetricContext 和版本

```text
Evidence
├── source_type: document | dataset | rule | calculation | trace
├── source_id: str
├── document_version_id: str | None
├── dataset_version_id: str | None
├── index_version_id: str | None
├── locator: object
├── excerpt: str | None
├── score: float | None
├── score_type: cosine | bm25 | rrf | rerank | rule
├── permission_checked: bool
└── provenance_status: verified | inferred | unavailable

MetricContext
├── metric_id: str
├── definition_version: str
├── formula: str
├── unit: str
├── currency: str | None
├── period_type: str
├── timezone: str
├── source_scope: list[str]
├── filters: object
└── warnings: list[str]
```

### 3.5 SSE 事件和错误码

统一 SSE 事件类型：

```text
request.started
step.started
step.progress
tool.started
tool.completed
model.started
model.completed
retrieval.completed
evidence.available
approval.required
result.partial
request.completed
request.failed
request.cancelled
heartbeat
```

每个事件至少包含 `request_id`、`trace_id`、`sequence`、`timestamp`、`status` 和可选 `error`。事件必须可重放、可排序、可识别终态。

统一错误码：

```text
authentication_required
permission_denied
authorization_unavailable
resource_not_found
validation_error
conflict
rate_limited
model_unavailable
retrieval_unavailable
task_timeout
task_cancelled
unsupported_file
parse_failed
index_publish_failed
internal_error
```

### 3.6 分页、幂等和版本约定

- 列表接口统一使用 `page`、`page_size`、`sort`、`direction` 或游标方案，并明确最大值由配置决定。
- 写操作必须支持 `idempotency_key` 或等价业务幂等键。
- 文档、数据集、索引、Prompt、模型能力、策略、配置、Trace 和评测都必须有版本或不可变快照。
- 缓存键必须包含主体权限摘要、资源版本、策略版本、模型版本和请求模式，不能只使用问题文本。

---

## 4. Agent 分工与文件所有权

### Agent 0：主集成、公共契约和编排主流程

**职责：**

- 冻结跨模块数据契约、错误码、SSE 事件和版本语义；
- 集成 Planner、Worker、Critic、Synthesis；
- 维护 LangGraph 主流程、会话状态和取消传播；
- 解决跨 Agent 接口冲突；
- 最后负责统一合并和全量验收。

**允许修改：**

```text
app/agents/contracts.py
app/agents/state.py
app/agents/orchestrator.py
app/agents/nodes.py
app/api/v1/chat.py
app/api/v1/contracts.py
docs/superpowers/specs/
docs/api/
tests/test_agent_collaboration.py
tests/test_sse_contract.py
```

**禁止修改：**

```text
frontend/
app/rag/                     # 除非主集成适配已获明确授权
app/common/authorization.py
app/db/
app/approval/
app/insights/
```

**依赖：** Agent 1 的 Principal/授权上下文、Agent 2 的持久化接口、Agent 4 的检索结果、Agent 5 的模型调用接口、Agent 6 的任务状态。

**交付物：**

- `AgentContext`、`AgentResult`、`Evidence`、`MetricContext`、`ErrorEnvelope`；
- 可取消、可超时、有限重试的编排流程；
- SSE 终态唯一且可重连；
- 每次运行生成 `trace_id`、`request_id` 和 `task_id`；
- 集成说明和变更兼容矩阵。

**验收：**

- 单 Agent、文档问答、数据分析和需要多 Worker 的请求都能返回结构化结果；
- 模型、工具、检索失败时不会被包装成正常业务结论；
- 同一会话不会串入其他用户或其他会话状态；
- SSE 断线重连、取消、超时和失败都能识别终态；
- 不修改 `frontend/`。

---

### Agent 1：身份、RBAC/ABAC 和资源隔离

**职责：**

- 统一认证主体 `Principal`；
- 角色、权限、部门、密级、资源所有权和可见范围；
- 会话、文档、数据集、图表、报告、审批、洞察、告警和 Trace 的资源级授权；
- 静态资源和下载授权；
- Agent 工具调用的权限边界。

**允许修改：**

```text
app/common/auth.py
app/common/identity.py
app/common/permissions.py
app/common/policy.py
app/common/authorization.py
app/common/rbac.py
app/api/v1/auth.py
tests/test_rbac_abac.py
tests/test_authorization_api.py
tests/test_agent_tool_authorization.py
```

**禁止修改：**

```text
app/agents/orchestrator.py
app/agents/state.py
app/api/v1/chat.py
frontend/
```

**必须覆盖：**

- 缺失身份不降级为管理员；
- 列表和详情接口都做资源授权；
- `owner_id`、`department_ids`、`classification`、`visibility` 一致；
- 查询、预览、下载、导出、删除和引用展示使用同一授权策略；
- `/static/` 不再成为绕过授权的访问路径；
- 401、403、404 和授权不可用的语义统一；
- 删除、禁用用户和权限变更后旧 Token 的行为明确；
- 所有拒绝和策略异常进入审计事件。

**验收：**

- 普通用户不能读取、下载、检索或引用无权资源；
- 跨部门、跨密级、伪造资源 ID、伪造 session ID、伪造 artifact URL 的请求均被拒绝；
- Agent 在没有合法 `Principal` 时不能调用受保护工具；
- 同一资源的列表、详情、检索、预览和下载结果一致；
- 每个拒绝有明确错误码和审计记录。

---

### Agent 2：数据库、迁移、版本和统一存储

**职责：**

- PostgreSQL 目标架构；
- PGVector 扩展和向量表；
- 本地文件存储抽象；
- Redis 连接和状态存储接口；
- 正式迁移、事务、连接池、恢复和版本表；
- Chroma 到 PGVector 的可回滚迁移方案。

**允许修改或新增：**

```text
app/db/
app/storage/
migrations/
scripts/db/
tests/test_database_migrations.py
tests/test_storage_versions.py
tests/test_database_recovery_contract.py
docs/deployment/database.md
```

**禁止修改：**

```text
app/agents/orchestrator.py
app/rag/retrieval_pipeline.py
frontend/
```

**必须建立的核心实体：**

```text
User / Department / Role / Permission
Session / Message
Document / DocumentVersion / ParserRun
Dataset / DatasetVersion / CalculationRun
Index / IndexVersion / Chunk
Artifact
AgentRun / AgentStep / ToolCall / ModelCall / RetrievalTrace
Insight / Alert / Notification
ApprovalRequest / PolicyVersion / ReviewStep
MetricDefinition / ConfigVersion / EvalDataset / EvalRun / EvalResult
AuditEvent
```

**必须覆盖：**

- 禁止运行时散落建表代替迁移；
- 迁移版本、锁、失败回滚和重复执行；
- 事务边界和并发更新；
- 文档、数据、索引和配置版本不可混用；
- 索引发布采用临时版本校验后原子切换；
- 文件元数据和实际文件分离；
- 删除、归档、软删除和物理清理的级联规则；
- 备份包括数据库、文件、版本元数据、配置和恢复顺序；
- Chroma 只作为过渡读源或回滚源，不写成最终生产存储。

**验收：**

- 新环境可通过迁移创建所需 Schema；
- 重复执行迁移不会破坏数据；
- 迁移中断可恢复；
- 文档版本、数据集版本和索引版本可以独立查询、比较和回滚；
- 备份能在隔离环境恢复出可查询的资源、版本和权限关系；
- PGVector 不可用时，系统明确报告依赖不可用，而不是静默伪造成功。

---

### Agent 3：文件上传、解析和数据资产

**职责：**

- 上传安全、文件生命周期和解析质量；
- PDF、扫描 PDF/OCR、PDF 表格、DOCX、DOC、Word 表格、XLSX、XLS、CSV、Markdown、TXT；
- 文档知识库和经营数据集的明确分流；
- DocumentVersion、DatasetVersion、ParserRun 和 SourceLocator；
- 安全数据查询 DSL，替换 `eval()`。

**允许修改或新增：**

```text
app/rag/loader.py
app/documents/
app/datasets/
app/tools/excel.py
app/tools/data_query.py
app/api/v1/documents.py
app/api/v1/data.py
tests/test_file_upload_security.py
tests/test_document_parsers.py
tests/test_dataset_versions.py
tests/test_safe_data_query.py
```

**禁止修改：**

```text
frontend/
app/agents/orchestrator.py
app/rag/retrieval_pipeline.py
```

**必须覆盖：**

- 流式写入临时文件，不一次性无限读取；
- 文件大小、解压后大小、页数、行数、列数和处理时长均为配置项；
- 扩展名、真实 MIME、魔数和解析器结果交叉校验；
- 文件名只作为展示信息，存储使用随机资源 ID；
- 路径穿越、符号链接、双扩展名、压缩炸弹和恶意嵌套文件防护；
- 解析状态区分成功、部分成功、OCR 低置信度、表格异常、编码异常、索引失败；
- PDF 表格保留页码、表头、行列关系和原文定位；
- OCR 保留页码、识别置信度和失败原因；
- Word 保留标题层级、列表、表格和段落关系；
- Markdown 保留标题路径、代码块、表格、链接和引用；
- Excel/CSV 同时支持经营数据分析和可选知识库导入，不能只按扩展名判断用途；
- `safe_query()` 使用受限 DSL/AST 校验或隔离进程，禁止直接 `eval()`；
- 导出时防止 CSV/Excel 公式注入；
- 临时文件、失败文件和删除文件按生命周期清理。

**验收：**

- 每种格式都有成功、部分成功和失败夹具；
- 解析结果可以定位到文档版本、页码、工作表、表格、章节或行列范围；
- 恶意文件无法写出工作区；
- 超限输入被拒绝且不会拖垮 Worker；
- 数据查询不能执行任意 Python；
- 解析失败可以重试、查看原因和从已发布版本回滚。

---

### Agent 4：RAG、索引和检索调试台

**职责：**

- Chroma 过渡适配和 PGVector 目标适配；
- 混合检索、BM25、向量、RRF、重排、查询改写、父子块；
- 权限前置过滤；
- 独立分数和分数类型；
- IndexVersion；
- 检索 Trace 和管理员调试 API。

**允许修改或新增：**

```text
app/rag/retriever.py
app/rag/retrieval_pipeline.py
app/rag/indexing.py
app/rag/filters.py
app/rag/debug.py
app/api/v1/retrieval_debug.py
tests/test_retrieval_pipeline.py
tests/test_retrieval_permissions.py
tests/test_retrieval_debug.py
```

**禁止修改：**

```text
app/agents/orchestrator.py
app/api/v1/chat.py
frontend/
```

**必须覆盖：**

- 过滤先于检索结果暴露，不能检索后再简单删除无权片段；
- 稳定 `chunk_id`、父块 ID、文档版本 ID 和索引版本 ID；
- 保存 `vector_score`、`bm25_score`、`rrf_score`、`rerank_score`，禁止覆盖成一个不可解释的 `score`；
- 每个分数带 `score_type`、方向、范围说明和是否可比较标志；
- 父子块做到“小块召回、大块生成”，并可追溯；
- 索引构建使用临时版本，校验完成后原子发布；
- 查询改写、HyDE、多查询扩展和重排都有调用预算；
- 快速、标准、深度模式由配置和硬件能力决定，不写死模型名；
- 检索调试台最多比较多套策略，但策略配置来自版本化配置，不来自固定演示值；
- 调试结果包含每阶段耗时、候选数、过滤原因、排序变化和最终证据；
- 缓存包含主体权限、知识库版本、索引版本、Prompt 版本和模型能力版本。

**验收：**

- 同一问题可以查看向量、BM25、融合、重排和最终结果；
- 结果能解释为何进入、为何被过滤、排名如何变化；
- 文档版本切换不会混用旧索引；
- 无权文档不会在调试台、Trace、证据或错误信息中泄露；
- Chroma 到 PGVector 的切换可比较、可回滚、可重建；
- 并发首次构建 BM25/索引不会产生竞态。

---

### Agent 5：Ollama 管理、模型路由和性能

**职责：**

- 本机 Ollama 自动发现；
- 模型能力检测；
- 聊天、Embedding、重排或工具用途选择；
- 单机模型并发和资源预算；
- 快速、标准、深度请求模式；
- 缓存、P50/P95、模型调用次数和资源竞争采集。

**允许修改或新增：**

```text
app/common/model_config.py
app/common/model_handler.py
app/common/performance.py
app/common/cache.py
app/common/model_capabilities.py
tests/test_ollama_discovery.py
tests/test_model_capabilities.py
tests/test_private_model_routing.py
tests/test_performance_runtime.py
```

**禁止修改：**

```text
frontend/
app/agents/orchestrator.py
app/api/v1/chat.py
```

**必须覆盖：**

- 通过 Ollama 本机 API 发现已有模型，不在生产代码写死某个模型名；
- 检测模型是否支持聊天、Embedding、工具调用、结构化输出等能力；
- 能力不匹配时拒绝或选择明确的替代路径；
- 远程模型回退默认关闭，启用必须是显式配置并进入审计；
- 14B 或其他高资源模型不能被多个 Agent 同时无上限调用；
- 并发、排队、超时、取消和降级均可配置；
- 失败状态区分连接失败、模型缺失、能力不支持、超时、资源不足和响应解析失败；
- Embedding、查询改写、重排和答案生成分别记录 ModelCall；
- 缓存键绑定权限、资源版本、模型版本、Prompt 版本和查询模式；
- 采集请求阶段、首 token、总耗时、输入输出 token 或等价计量、队列等待和错误原因；
- 性能目标以硬件画像和真实基线为依据，不能把固定秒数冒充所有部署环境的承诺。

**验收：**

- 本机已有模型能被发现并在管理接口展示能力；
- 删除或不可用模型后，系统给出明确不可用状态；
- 同一模型被占用时请求排队或降级，不会无限创建推理任务；
- 远程回退关闭时不会外发请求；
- P50/P95 和每次模型调用可以在 Trace 或运营接口中查到；
- 模型失败不会生成看似正常的业务答案。

---

### Agent 6：Redis 队列、Worker 和任务可靠性

**职责：**

- Redis 队列或 Streams；
- ACK、租约、可见性超时、重试、死信、幂等、取消和超时；
- Worker 崩溃恢复；
- 文档解析、索引、评测、洞察扫描和导出任务的统一状态。

**允许修改或新增：**

```text
app/common/queue.py
app/tasks/
deploy/queue_worker.py
deploy/scheduler.py
tests/test_queue_reliability.py
tests/test_worker_recovery.py
tests/test_task_cancellation.py
```

**禁止修改：**

```text
frontend/
app/agents/orchestrator.py
app/common/model_handler.py
```

**必须覆盖：**

- 不使用无确认的 `BLPOP` 作为唯一可靠队列；
- 每个任务有唯一 ID、幂等键、租约、尝试次数、超时和状态；
- Worker 处理成功后 ACK，崩溃或超时后可重新领取；
- 重试策略区分可重试错误和不可重试错误；
- 超过策略次数进入死信并保存原始错误；
- 取消只改变请求状态不等于立即停止副作用，必须记录实际终态；
- 任务结果写入持久化存储，进程重启后可恢复；
- Scheduler 单实例或使用分布式锁，不能多进程重复执行；
- 任务执行需要最小权限主体和资源范围；
- 任务输入和结果支持版本化，避免重试读到不一致的数据。

**验收：**

- Worker 被杀死后任务不会静默丢失；
- 重试不会重复生成不可逆 Artifact 或重复发送通知；
- 取消、超时、死信和恢复均有可查询状态；
- 多 Worker 不会重复执行同一调度任务；
- 队列不可用时 API 返回明确错误或进入受控降级。

---

### Agent 7：Trace、评测、后台治理和审计

**职责：**

- AgentRun、AgentStep、ToolCall、ModelCall、RetrievalTrace；
- 评测集、评测运行、评测结果、报告和策略对比；
- RAG 检索调试后台接口；
- Prompt、模型能力、检索策略、工具和配置版本；
- 审计事件、敏感信息脱敏和慢请求运营视图。

**允许修改或新增：**

```text
app/quality/
app/admin/
app/trace/
app/common/audit.py
app/common/tracing.py
app/api/v1/admin.py
app/api/v1/trace.py
app/api/v1/evaluation.py
tests/test_quality_platform.py
tests/test_quality_runner.py
tests/test_trace_persistence.py
tests/test_audit_redaction.py
```

**禁止修改：**

```text
frontend/
app/agents/orchestrator.py
app/db/
```

**必须覆盖：**

- Trace 记录请求主体、资源范围、模型、Prompt、工具、检索阶段、耗时、错误和终态；
- Trace 中不直接泄露密码、Token、密钥、完整敏感文档和无权证据；
- AgentResult、Evidence、ModelCall 和 ToolCall 不只留在内存或 SSE；
- 评测数据集支持人工录入、来源片段关联、版本、批量运行和结果复现；
- 评测至少区分召回、排序、忠实度、回答相关性，并标记裁判模型和版本；
- Context Recall 优先使用明确的来源片段集合，不把整篇文档误当作参照；
- RAG 调试可查看每阶段候选、分数、过滤和耗时；
- Prompt、检索策略、工具、模型能力和系统配置均有草稿、校验、发布、回滚版本；
- 后台管理 API 与业务 API 分离并受管理员权限保护；
- 审计事件记录成功、拒绝、失败、删除、导出、模型外发开关和策略变化。

**验收：**

- 一次问答可以从 Trace 回放到模型、工具、检索和证据；
- 评测结果能关联策略、模型、Prompt、索引和数据集版本；
- 同一评测运行可以复现输入和配置；
- 管理员可以看到慢请求、模型失败、队列堆积和权限拒绝；
- 审计日志可查询、可脱敏、可按策略保留。

---

### Agent 8：业务语义、Dashboard、洞察、告警、审批和知识图谱

**职责：**

- 业务指标语义；
- DatasetVersion 到 Dashboard、图表和报告的真实数据链路；
- Insight、Alert、Notification 统一事件模型；
- 审批助手的制度匹配、金额计算、责任人和人工确认；
- PostgreSQL 持久化知识图谱。

**允许修改或新增：**

```text
app/semantics/
app/dashboard/
app/insights/
app/approval/
app/knowledge_graph/
app/api/v1/intelligence.py
app/api/v1/alerts.py
app/api/v1/approval.py
tests/test_business_semantics.py
tests/test_dashboard.py
tests/test_insights.py
tests/test_approval_assistant.py
tests/test_knowledge_graph.py
```

**禁止修改：**

```text
frontend/
app/agents/orchestrator.py
app/agents/state.py
```

**必须覆盖：**

- 指标定义包括名称、字段映射、公式、单位、货币、税费/退款口径、时间粒度、时区、责任部门、来源和版本；
- 未确认的指标口径只能标记为警告或草稿，不能作为确定事实；
- Dashboard、图表和报告必须绑定 DatasetVersion、CalculationRun、MetricDefinition 和权限范围；
- 空数据、缺字段、口径冲突和权限不足必须展示空状态或警告，不得返回演示数据；
- 洞察和告警共享 `BusinessEvent`、去重键、状态、责任人、确认、解决和通知记录；
- 洞察规则与告警规则不能各自维护一套冲突状态；
- 金额和比例使用 `Decimal`、明确货币和舍入规则；
- 审批只生成预审建议和草稿，不直接替代真实财务审批；
- 缺少制度、材料或责任人时，必须明确“无法判断”；
- 知识图谱实体、关系、来源、版本、置信状态和人工审核持久化；
- 所有业务结果都可回到数据集、文档、制度或计算过程。

**验收：**

- 删除演示数据后页面和 API 仍能正确显示空状态；
- 同一指标在 Dashboard、洞察、告警、审批和报告中口径一致；
- 审批建议可以显示依据、缺口、责任人和下一步，而不是固定部门或固定金额；
- 洞察确认、转告警、通知、解决和审计形成完整闭环；
- 知识图谱重启后数据、来源和权限不丢失。

---

### Agent 9：Docker、Nginx、安全基线、监控和恢复

**职责：**

- Dockerfile、Compose、Nginx、Worker、Scheduler 拓扑；
- 真实健康检查；
- 依赖和镜像锁定；
- 密钥、CORS、网络隔离；
- 备份、恢复、灾备演练；
- 运行监控和资源告警。

**允许修改或新增：**

```text
Dockerfile
docker-compose.yml
deploy/
docs/deployment/
app/common/backup.py
app/common/monitoring.py
app/common/secret_rotation.py
tests/test_deployment_guards.py
tests/test_backup_restore.py
tests/test_security_operations.py
```

**禁止修改：**

```text
frontend/
app/agents/orchestrator.py
app/common/model_handler.py
```

**必须覆盖：**

- Compose、Nginx、FastAPI、Worker、Scheduler、PostgreSQL、Redis、PGVector、文件卷和 Ollama 的拓扑一致；
- 健康检查真实探测关键依赖，不固定返回 `ok`；
- Scheduler 单实例，Worker 可水平扩展且任务幂等；
- `.env.example` 不包含真实密钥，默认 JWT 密钥和默认管理员密码不能进入生产；
- CORS 使用明确白名单；
- PostgreSQL、Redis、Ollama 和存储服务默认只监听内网或容器网络；
- 镜像和依赖尽量锁定版本或摘要，禁止无审查的 `latest`；
- 备份覆盖数据库、文件、版本元数据、配置、密钥轮换信息和恢复顺序；
- 恢复需要校验权限、索引、Artifact 和队列状态；
- 监控 CPU、内存、磁盘、队列、模型耗时、错误率、P50/P95、权限拒绝和备份结果；
- 日志和监控脱敏。

**验收：**

- 新环境可以按照部署文档构建并启动；
- 关键依赖不可用时健康检查返回对应状态；
- 单个组件重启后任务、数据和权限可恢复；
- 全量备份可以在隔离目录恢复；
- 默认密钥、公开静态资源、宽松 CORS 和未锁定镜像检查会失败并阻止部署。

---

### Agent 10：只读 Review、跨模块测试和最终验收

**职责：**

- 检查各 Agent 是否越过文件边界；
- 编写跨模块契约、安全、恢复和性能测试；
- 不重写业务实现；
- 输出按 P0/P1/P2/P3 排序的问题报告；
- 复核文档是否把目标误写成当前实现。

**允许修改或新增：**

```text
tests/integration/
tests/security/
tests/recovery/
tests/performance/
docs/reviews/
```

**禁止修改：**

```text
app/
frontend/
Dockerfile
docker-compose.yml
deploy/
```

**必须覆盖：**

- 资源级越权；
- 静态文件和下载泄露；
- 文件路径穿越和恶意文件；
- `eval()` 或任意代码执行；
- Prompt Injection 和工具越权；
- 缓存权限污染；
- 队列 ACK、重试、死信和幂等；
- Ollama 并发和失败降级；
- Trace、证据和报告来源完整性；
- 备份恢复、删除清理和版本切换；
- API/SSE 错误码和终态；
- Docker/Nginx/健康检查一致性。

**验收：**

- Review 输出每个问题的路径、位置、风险、责任 Agent、修复阶段和验收标准；
- 不直接修改业务实现；
- 只有主集成 Agent 处理跨模块修复；
- Review 结果能够映射到本计划的任务和问题编号。

---

## 5. 当前前端 Agent 的协作边界

前端 Agent 继续独占 `frontend/`，本计划不修改以下文件：

```text
frontend/
```

后端与前端只通过以下方式协作：

1. Agent 0 维护 `docs/api/` 中的 REST、SSE、错误码、分页和取消契约；
2. 后端接口变更先写兼容说明，再通知前端 Agent；
3. 前端 Agent 可以先使用 Mock，但 Mock 字段必须来自冻结契约；
4. 后端不得为了迁就页面而返回固定演示数据；
5. 前端不得把按钮隐藏、路由隐藏或本地角色判断当作安全控制；
6. SSE 事件名称、字段和终态不可由各模块自行发明；
7. 需要前端联调时只提供接口地址、示例响应、错误状态和验收步骤，不直接改前端代码；
8. 前端 Agent 负责页面状态、断线重连、空状态、错误状态、进度和移动端布局；后端负责权限、数据可信度和终态。

---

## 6. 阶段与依赖关系

### 阶段 0：基线和协作冻结

**负责人：** Agent 0 + Agent 10  
**串行，其他 Agent 不启动生产代码修改。**

- [ ] 记录当前分支、工作区、未提交文件和当前运行环境。
- [ ] 阅读 `AGENTS.md`、当前功能文档、修订记录、升级方案和旧并行计划。
- [ ] 标记现有实现、部分实现、演示骨架和无法确认项。
- [ ] 建立本计划的文件所有权矩阵。
- [ ] 冻结公共错误码、SSE 事件、Principal、ResourceScope、AgentResult 和版本语义。
- [ ] 为每条 Agent 线建立分支或隔离工作目录。
- [ ] 确认前端 Agent 的当前修改文件，禁止后端 Agent 进入 `frontend/`。

**阶段门槛：**

- 没有文件所有权冲突；
- 没有未解释的公共契约分叉；
- 没有把历史测试输出直接当作当前通过证据；
- 未提交修改未被覆盖。

### 阶段 1：权限和存储基础

**可并行：** Agent 1、Agent 2。  
**集成前提：** 两者均消费阶段 0 的公共契约。

- [ ] Agent 1 完成 Principal、授权策略和资源隔离接口。
- [ ] Agent 2 完成迁移、版本实体、连接池和存储接口。
- [ ] 主集成 Agent 先接入最小的资源范围和错误码。
- [ ] Agent 10 添加越权和迁移失败的跨模块测试。

**阶段门槛：**

- 所有受保护资源都有资源类型和所有权模型；
- 新环境可以执行迁移；
- 没有默认管理员降级；
- 不同资源的授权结果一致。

### 阶段 2：文件、任务队列和 Ollama

**可并行：** Agent 3、Agent 5、Agent 6。  
**依赖：** Agent 1 的授权接口、Agent 2 的版本和存储接口。

- [ ] Agent 3 完成上传安全、解析质量和数据资产版本。
- [ ] Agent 5 完成 Ollama 发现、能力检测和模型调用预算。
- [ ] Agent 6 完成可靠队列、Worker 状态和取消恢复。
- [ ] 每条线先使用离线夹具，不启动真实 14B 压力测试。

**阶段门槛：**

- 文件不再依赖客户端文件名或共享目录；
- 长任务不会静默丢失；
- 模型失败可区分且不会伪造答案；
- 文档、数据集和解析结果具有版本。

### 阶段 3：RAG 和 Trace

**可并行：** Agent 4、Agent 7。  
**依赖：** 阶段 1 和阶段 2。

- [ ] Agent 4 接入版本化索引、权限前置过滤和检索调试结果。
- [ ] Agent 7 接入 AgentRun、Step、ModelCall、ToolCall、RetrievalTrace 和评测实体。
- [ ] Agent 0 将检索结果和 Trace 接入主编排。

**阶段门槛：**

- 每个回答可以关联权限检查后的 Evidence；
- 检索分数不再相互覆盖；
- Trace 不只存在于 SSE；
- Chroma/PGVector 切换可观察、可回滚。

### 阶段 4：业务闭环

**负责人：** Agent 8  
**依赖：** 阶段 1、2、3，尤其是 DatasetVersion、MetricDefinition、Evidence 和授权接口。

- [ ] 完成指标语义和版本。
- [ ] 完成 Dashboard、图表、报告来源。
- [ ] 完成统一洞察、告警、通知和状态闭环。
- [ ] 完成审批助手的制度、材料、责任人和人工确认。
- [ ] 完成持久化知识图谱和来源审核。

**阶段门槛：**

- 没有固定金额、部门、指标或演示数据；
- 所有业务结果有数据或制度来源；
- 审批助手不直接执行真实审批；
- 洞察和告警不会形成两套互相冲突的状态。

### 阶段 5：管理、部署和恢复

**可并行：** Agent 7、Agent 9。  
**依赖：** 业务实体、Trace 和版本模型已稳定。

- [ ] Agent 7 完成后台配置、评测、慢请求和审计视图。
- [ ] Agent 9 完成 Docker、Nginx、健康检查、备份和恢复。
- [ ] Agent 0 冻结前后端接口并提供给前端 Agent。

**阶段门槛：**

- 部署配置与代码拓扑一致；
- 健康检查真实探测依赖；
- 配置可发布、审计和回滚；
- 备份能恢复数据库、文件和权限关系。

### 阶段 6：主流程和前端联调

**负责人：** Agent 0 + 当前前端 Agent  
**必须串行，避免同时改公共接口。**

- [ ] Agent 0 将所有领域结果接入 LangGraph。
- [ ] 固定 SSE 事件、错误码、取消和重连语义。
- [ ] 前端 Agent 根据冻结契约接入页面状态。
- [ ] 后端不修改 `frontend/`。
- [ ] 完成文档问答、数据分析、图表、报告、洞察、审批和 Trace 的端到端联调。

### 阶段 7：Review、真实依赖验收和发布

**负责人：** Agent 10 + Agent 0 + Agent 9

- [ ] 先运行离线单元和契约测试。
- [ ] 再在隔离环境运行 PostgreSQL、PGVector、Redis 和文件存储测试。
- [ ] 最后串行运行真实 Ollama 测试。
- [ ] 完成越权、删除、恢复、队列崩溃和重启验证。
- [ ] 生成 P0/P1/P2/P3 问题清单和发布阻断项。

---

## 7. 不能并行的任务

以下任务必须串行：

1. 公共契约冻结与主编排修改；
2. 同一数据库表、迁移版本和索引发布协议；
3. 同一 API 路由和同一 SSE 事件定义；
4. `app/agents/orchestrator.py`、`app/agents/state.py`、`app/api/v1/chat.py`；
5. Chroma 到 PGVector 的切换和回滚；
6. 前端消费尚未冻结的 API；
7. 真实 Ollama 大模型调用和性能压测；
8. 生产部署配置、密钥策略和备份恢复演练；
9. 洞察/告警统一状态迁移；
10. 版本发布、索引发布和删除清理。

以下任务可以并行，但必须只通过契约交互：

- 权限和数据库 Schema 的独立实现；
- 文件解析、模型管理和队列可靠性；
- RAG 检索与评测数据模型；
- Trace、后台管理和部署安全；
- 业务语义、洞察和审批，但必须消费统一 DatasetVersion/MetricDefinition。

---

## 8. 每个 Agent 的固定派发模板

将下面的模板复制给对应 Agent，并替换领域名称：

```text
你负责“<领域名称>”，工作目录为当前项目的独立分支或 Worktree。

先读取：
- AGENTS.md
- docs/current-functionality-2026-09-10.md
- docs/superpowers/plans/2026-09-10-enterprise-brain-multi-agent-development-plan.md
- 你负责目录中的当前源码和测试

只允许修改计划中列出的文件，不得修改 frontend/、公共主流程或其他 Agent 文件。
如果发现必须修改边界外文件，停止实现，先输出集成请求，不要直接覆盖。

要求：
1. 以当前源码为第一证据，不因文档、测试名称或页面存在就判断功能完成；
2. 不使用固定金额、固定部门、固定指标、固定阈值、固定模型名或演示数据冒充生产逻辑；
3. 先补失败测试或契约测试，再实现最小闭环；
4. 所有资源操作带 Principal、owner_id、版本和审计上下文；
5. 长任务支持任务 ID、状态、超时、取消、幂等和失败原因；
6. 不运行会改变用户数据或外部环境的命令；
7. 真实 Ollama 调用只能由主集成 Agent 串行执行；
8. 完成后报告变更文件、公开接口、测试命令和结果、未验证项、风险和集成步骤。
```

---

## 9. 分支交付和合并流程

每个领域 Agent 必须按以下顺序交付：

1. [ ] 阅读当前源码和所属文档，记录当前真实状态。
2. [ ] 写出本领域的接口变化和数据版本变化。
3. [ ] 增加失败测试、边界测试或安全测试。
4. [ ] 实现最小可独立运行的功能。
5. [ ] 运行只针对本领域的离线测试。
6. [ ] 检查没有生成密钥、真实数据或大文件。
7. [ ] 执行 `git diff --check`。
8. [ ] 输出变更清单和集成说明。
9. [ ] 由主集成 Agent 先审查接口，再合并。
10. [ ] 合并后立即运行该领域测试和契约测试。

合并顺序：

```text
公共契约
  -> 权限与存储
  -> 文件、队列、模型
  -> RAG 与 Trace
  -> 业务闭环
  -> 后台与部署
  -> 主流程接入
  -> 前端联调
  -> 全量 Review
```

任何合并失败都必须保留失败日志和冲突文件清单，不得用强制覆盖解决。

---

## 10. 测试和验收矩阵

| 层级 | 责任人 | 重点 | 真实依赖 |
|---|---|---|---|
| 单元测试 | 各领域 Agent | 纯函数、解析、策略、状态转换 | 否 |
| 契约测试 | Agent 0 + Agent 10 | Pydantic、REST、SSE、错误码、版本字段 | 否 |
| 权限测试 | Agent 1 + Agent 10 | 用户、部门、密级、所有权、静态资源 | 否 |
| 数据库测试 | Agent 2 | 迁移、事务、并发、回滚、版本 | 隔离 PostgreSQL |
| 文件安全测试 | Agent 3 | MIME、魔数、路径、压缩炸弹、生命周期 | 否 |
| 队列恢复测试 | Agent 6 | ACK、租约、重试、死信、取消、崩溃恢复 | 隔离 Redis |
| RAG 测试 | Agent 4 | 分数、过滤、父子块、版本、调试 | Chroma 或隔离 PGVector |
| 模型测试 | Agent 5 | 发现、能力、并发、降级、缓存 | Mock；最后串行 Ollama |
| Trace/评测测试 | Agent 7 | 落库、回放、裁判版本、脱敏 | 隔离数据库 |
| 业务闭环测试 | Agent 8 | 指标、Dashboard、洞察、审批、图谱 | 隔离数据集 |
| 部署测试 | Agent 9 | Compose、Nginx、健康检查、备份恢复 | 隔离容器 |
| 浏览器验收 | 前端 Agent + Agent 10 | 页面状态、SSE、下载、空状态、错误态 | 隔离服务 |

### 10.1 最终验收场景

使用不包含真实敏感信息的临时资料，完成以下链路：

1. 管理员创建用户、部门、角色和权限范围；
2. 用户上传普通 PDF、扫描 PDF、Word、Markdown、Excel 和 CSV；
3. 系统显示解析状态、质量、版本和失败原因；
4. 通过权限范围检索文档和数据集；
5. 查看向量、BM25、融合、重排、父块回填和证据定位；
6. 通过自然语言完成数据分析并展示 MetricContext；
7. 生成图表和报告，检查 Artifact 来源、所有权、下载权限和生命周期；
8. 触发洞察、告警、通知和处理状态；
9. 生成审批预审建议，检查制度来源、材料缺口和人工确认；
10. 查看 Agent Trace、Tool Call、Model Call、RetrievalTrace 和评测结果；
11. 取消一个长任务，重启一个 Worker，恢复一个任务；
12. 删除一个文档或数据集，检查索引、缓存、Artifact、Trace 和备份副本的清理策略；
13. 重启服务，检查版本、权限和知识图谱仍然存在；
14. 使用无权用户、跨部门用户和过期 Token 重复验证所有边界。

---

## 11. 生产阻断项

以下问题未处理前不得宣称生产可用：

### P0

- 任意资源可通过静态 URL、文件路径、伪造 ID 或缺失身份读取；
- Agent、后台任务或错误路径默认使用管理员身份；
- `eval()` 或等价逻辑可以执行任意 Python；
- 上传文件可路径穿越、无限读取或压缩炸弹拖垮服务；
- 模型失败返回伪装成业务结论的文本；
- 数据库、队列、文件或索引写入不是原子操作并可能静默丢失；
- 真实审批或外部副作用没有人工确认和权限边界。

### P1

- 会话、文档、数据集、Artifact、Trace 没有稳定 `owner_id` 和资源授权；
- Redis 队列没有 ACK、租约、重试和死信；
- 运行时建表替代正式迁移；
- Chroma/PGVector 切换无法校验和回滚；
- 文档索引发布不是原子版本切换；
- Trace、Evidence、ToolCall 和 ModelCall 没有完整落库；
- 缓存键没有绑定权限和版本；
- 备份不能恢复数据库、文件和权限关系；
- Ollama 未自动发现或并发失控导致本机模型资源竞争；
- 前后端 API/SSE 错误状态和终态不一致。

### P2

- PDF 表格、OCR、Word 表格、Markdown、Excel/CSV 知识库处理不完整；
- 检索分数被覆盖，无法解释量纲和排序变化；
- 评测集、批量评测和策略对比不完整；
- Dashboard、图表、报告、洞察和告警缺少真实来源；
- 指标语义、金额、时间范围、单位和公式未统一；
- 审计日志、脱敏、保留期和删除级联不完整；
- Scheduler、健康检查、依赖版本、CORS 和 Nginx 配置不一致。

### P3

- 运营页面缺少慢请求、模型调用、队列堆积和失败原因；
- 前端空状态、移动端布局、重连和错误提示需要继续完善；
- 评测可视化、策略对比和知识图谱交互需要扩展；
- 后续再考虑 LDAP/AD/SSO、复杂多租户计费、外部消息平台和大规模图数据库。

---

## 12. 暂时不应实现的内容

在本计划的核心闭环完成前，不启动以下工作：

- 自动执行真实财务审批、付款、转账、删除生产数据或其他不可逆操作；
- 以固定部门、金额、阈值或模型名堆出“看起来完整”的演示逻辑；
- 同时引入 Neo4j、复杂多租户计费或大规模分布式检索集群；
- 远程模型默认回退、自动把客户数据发送到公有云或外部消息平台；
- 无限轮次 Agent 辩论、无限自动重试或无上限大模型并发；
- 在 PGVector、迁移、权限和文件生命周期未稳定前继续堆叠页面；
- 通过前端隐藏按钮替代后端授权；
- 仅为了让测试通过而修改测试夹具、放宽安全校验或返回固定演示数据；
- 将历史浏览器截图、旧日志或未重跑的测试结果当作当前发布证据。

---

## 13. 回滚、恢复和冲突处理

- 每个 Agent 的提交必须小而可回退，提交信息包含领域和任务编号。
- 合并前保存基线和变更清单；合并后保存契约测试结果。
- 如果某领域破坏公共契约，主集成 Agent 先回滚该领域分支，不回滚用户已有的无关修改。
- 数据库迁移必须提供向前修复和必要的回滚策略；不可逆迁移先做备份和恢复演练。
- PGVector 切换保留旧索引或可重建元数据，切换失败回到上一发布的 IndexVersion。
- 队列版本变更必须兼容旧任务或明确清空/迁移策略，禁止静默丢任务。
- 模型路由变更必须保留旧能力快照，模型不可用时返回结构化失败。
- Artifact 删除必须先标记状态，再按生命周期清理文件、缓存、索引、Trace 和备份引用。
- 出现文件冲突时停止冲突 Agent，由主集成 Agent 根据契约手工整合，不允许强制覆盖。

---

## 14. 最终发布门槛

只有同时满足以下条件，才能把当前版本标记为“可进入生产试运行”：

- [ ] 公共契约唯一，前端 Agent 已按同一契约联调。
- [ ] 所有受保护资源都有稳定主体、所有权、范围和版本。
- [ ] 认证、授权、下载、预览、检索和静态资源没有绕过路径。
- [ ] 上传、解析、索引、数据查询和导出有安全边界。
- [ ] PostgreSQL、PGVector、本地文件存储和 Redis 的目标链路已在隔离环境验证。
- [ ] Chroma 过渡链路和 PGVector 切换可观测、可回滚。
- [ ] Ollama 自动发现、能力检测、并发、超时和降级已验证。
- [ ] 队列 ACK、重试、死信、取消、超时、幂等和恢复已验证。
- [ ] Agent Trace、Evidence、Tool Call、Model Call 和评测报告真实落库。
- [ ] Dashboard、图表、报告、洞察、告警和审批都有真实来源和口径。
- [ ] 审计、脱敏、备份、恢复、删除和生命周期策略已验证。
- [ ] Docker、Compose、Nginx、Worker、Scheduler 和健康检查一致。
- [ ] P0 全部关闭，P1 全部关闭或有明确的试运行阻断说明。
- [ ] Agent 10 输出最终 Review，主集成 Agent 完成全量测试和浏览器验收。

---

## 15. 本计划的执行方式

建议创建以下 Codex 会话或多智能体线程：

```text
线程 0：主集成 / 公共契约 / LangGraph / SSE
线程 1：权限、资源隔离和审计边界
线程 2：PostgreSQL、PGVector、文件存储和迁移
线程 3：文件上传、解析和数据资产
线程 4：RAG、索引和检索调试
线程 5：Ollama、模型路由、缓存和性能
线程 6：Redis 队列、Worker、Scheduler 和恢复
线程 7：Trace、评测、后台治理和配置版本
线程 8：业务语义、Dashboard、洞察、告警、审批和知识图谱
线程 9：Docker、Nginx、安全基线、监控和备份
线程 10：只读 Review、跨模块测试和最终验收
```

启动顺序：

```text
线程 0 + 线程 10 只读基线
    -> 线程 0 冻结契约
    -> 线程 1 + 线程 2
    -> 线程 3 + 线程 5 + 线程 6
    -> 线程 4 + 线程 7
    -> 线程 8
    -> 线程 9
    -> 线程 0 接入主流程
    -> 当前前端 Agent 联调
    -> 线程 10 全量 Review
```

每个线程只领取自己负责的文件和任务，不要把整份计划复制成多个平行实现。主集成 Agent 是唯一负责公共契约、主流程、合并和最终发布判断的线程。
