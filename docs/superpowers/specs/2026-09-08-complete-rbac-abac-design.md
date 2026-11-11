# 企业智脑 RBAC + ABAC 混合权限升级设计

## 1. 文档信息

- 日期：2026-09-08
- 状态：待用户审核
- 适用项目：企业智脑
- 目标版本：第十阶段权限与企业安全能力升级
- 设计原则：后端强制授权、最小权限、默认拒绝、资源范围一致、可审计、可测试、可渐进迁移

## 2. 背景与问题

当前项目已经具备基础权限能力：

- 用户具有 `staff`、`manager`、`admin` 三种角色；
- 文档具有 `classification` 和 `department` 元数据；
- Chroma 检索、BM25 检索和 Excel 行过滤已经能够按密级和部门做基础过滤；
- Agent 工具能够接收角色和部门上下文。

但当前实现还不是完整 RBAC：

1. 角色主要被当作密级数值使用，没有独立的功能权限集合。
2. 部分接口没有统一认证和权限依赖。
3. 文档删除使用硬编码 `role == "admin"`，其他资源没有统一策略。
4. 数据文件、图表、导出、告警、会话、证据和未来洞察/审批资源缺少一致的资源级授权。
5. Agent 可以传递角色和部门，但没有统一的工具级权限检查契约。
6. 没有统一的拒绝响应和权限拒绝审计。
7. 前端权限展示与后端权限策略没有统一来源。
8. 现有测试主要验证基础过滤，没有覆盖接口越权、工具越权、跨部门访问和审计。

本设计采用“RBAC 主体授权 + ABAC 条件策略”的混合模式，解决功能权限和数据范围两个问题，同时为后续 SSO、LDAP、多租户和更复杂的企业 IAM 预留接口。

## 3. 目标与非目标

### 3.1 目标

- 对所有受保护 API 建立统一身份上下文。
- 将“能不能执行某类操作”和“能不能访问某个资源”分开判断。
- 覆盖文档、数据文件、分析、图表、导出、告警、洞察、会话、证据和 Agent 工具。
- 让普通用户、部门负责人、管理员、审计员的边界可解释、可配置、可测试。
- 后端拒绝逻辑作为最终安全边界，前端仅负责改善使用体验。
- 权限策略能够同时服务 FastAPI、Agent、MCP 和后台任务。
- 保持现有三种角色和历史文档字段兼容，避免一次迁移导致已有功能不可用。

### 3.2 非目标

本阶段不直接实现以下完整 IAM 能力：

- 企业级 SSO 产品、LDAP/AD 实时同步；
- 多租户隔离和跨租户计费；
- 复杂的审批式权限申请；
- 外部身份提供商的完整生命周期管理；
- 将所有权限配置做成复杂的可视化策略编辑器。

这些能力只保留接口和数据模型扩展点，不进入本阶段的交付范围。

## 4. 核心概念

### 4.1 主体 Subject

请求主体统一表示为 `Principal`：

```text
Principal
├── user_id: str
├── username: str
├── role: str
├── permissions: set[str]
├── department: str
├── department_ids: list[str]
├── clearance: int
├── status: active | disabled
├── auth_source: local | sso | system | worker
└── is_system: bool
```

JWT 只保存不可敏感的身份标识和令牌时间信息。每次请求由服务端根据 `sub` 加载当前用户状态和权限，用户被禁用或角色被修改后，旧令牌不会继续获得旧权限。

### 4.2 操作 Action

权限使用统一字符串标识，不在业务代码中直接比较角色：

```text
document:read
document:upload
document:preview
document:download
document:delete
document:manage_scope

data:read
data:preview
analysis:run
chart:generate
export:create

chat:use
session:read
session:delete
evidence:read

alert:read
alert:create
alert:update
alert:delete
insight:read
insight:manage

approval:read
approval:submit
approval:review

user:read
user:create
user:update
user:delete
role:manage
audit:read
permission:manage

agent:tool:retrieve
agent:tool:query_data
agent:tool:visualize
agent:tool:export
agent:tool:delete_document
agent:tool:manage_alert
```

权限名称必须集中定义，禁止在 API 文件中临时创建同义字符串。

### 4.3 资源 Resource

资源统一包含：

```text
Resource
├── resource_type
├── resource_id
├── owner_id
├── department
├── classification
├── visibility
├── status
└── metadata
```

不同资源的实际字段可以不同，但策略引擎只依赖通用字段。缺失字段必须采用安全默认值，不允许因为元数据缺失而意外放开访问。

## 5. 角色与权限矩阵

### 5.1 角色定义

| 角色 | 定位 | 默认数据范围 | 默认密级 |
|---|---|---|---|
| `staff` | 普通员工 | 本人及所属部门公开/内部资源 | 1 |
| `manager` | 部门负责人 | 所属部门及公开资源，可查看部门分析与告警 | 2 |
| `admin` | 系统管理员 | 全部门、全部业务资源 | 3 |
| `auditor` | 审计人员 | 只读全局审计与合规视图，不得修改业务数据 | 3 |

`auditor` 是新增角色。为兼容旧代码，原有 `staff`、`manager`、`admin` 保留。

### 5.2 功能权限矩阵

| 功能 | staff | manager | admin | auditor |
|---|---:|---:|---:|---:|
| 登录、个人资料、修改本人密码 | 是 | 是 | 是 | 是 |
| 使用智能问答 | 是 | 是 | 是 | 否 |
| 查看有权限的文档 | 是 | 是 | 是 | 按审计脱敏视图 |
| 上传文档 | 是 | 是 | 是 | 否 |
| 预览/下载文档 | 是 | 是 | 是 | 按审计视图 |
| 删除文档 | 否 | 否 | 是 | 否 |
| 执行数据分析 | 是 | 是 | 是 | 否 |
| 查看部门分析 | 否 | 是 | 是 | 否 |
| 生成图表 | 是 | 是 | 是 | 否 |
| 创建导出任务 | 否 | 是 | 是 | 否 |
| 创建/修改告警规则 | 否 | 是 | 是 | 否 |
| 删除告警规则 | 否 | 否 | 是 | 否 |
| 用户列表 | 否 | 否 | 是 | 否 |
| 创建、修改、删除用户 | 否 | 否 | 是 | 否 |
| 查看审计日志 | 否 | 否 | 是 | 是 |
| 配置角色和权限 | 否 | 否 | 是 | 否 |

矩阵只是默认值。最终判断必须通过权限集合和 ABAC 策略完成，不能把此表直接写成散落的 `if role`。

## 6. ABAC 数据范围策略

### 6.1 判断顺序

所有资源访问按以下顺序判断：

1. 身份是否存在且处于 `active` 状态。
2. 主体是否具有目标操作权限。
3. 资源是否存在且状态允许访问。
4. 主体是否满足资源密级要求。
5. 主体是否满足部门/所有者范围。
6. 是否满足特殊资源策略，例如审计脱敏或审批状态。
7. 记录允许或拒绝事件。

任何一步失败都不得执行后续业务操作。

### 6.2 密级规则

定义：

```text
公开 = 1
内部 = 2
机密 = 3
```

普通规则为：

```text
principal.clearance >= resource.classification
```

缺失或非法密级统一按 `1` 处理；非法密级在写入时拒绝，在读取时按最低权限处理并记录异常元数据事件。

### 6.3 部门规则

- 资源部门为空：表示公司范围公开资源，但仍受密级和操作权限限制。
- 资源部门等于主体部门：允许访问。
- 资源部门不等于主体部门：`staff` 禁止；`manager` 默认禁止跨部门；`admin` 允许。
- 无部门主体不能访问部门专属资源，只能访问无部门资源。
- 数据表存在部门列时，必须进行行级过滤。
- 数据表没有部门列时，不能假设所有行都属于当前用户；应使用文件级部门策略。

### 6.4 所有者规则

- 会话默认只有创建者可读写和删除。
- 普通用户只能删除自己的草稿型资源，不能删除已入库文档。
- 管理员可以管理全局资源，但删除必须记录原因。
- 审计员只能读取审计副本，不访问原始敏感内容。

### 6.5 失败安全规则

- 缺失主体：拒绝。
- 缺失资源元数据：按照最严格策略处理。
- 策略引擎异常：拒绝，不降级为管理员。
- Agent 未携带主体上下文：拒绝工具调用；仅在明确标记为系统后台任务时使用系统主体。
- 旧调用方传入空角色：不再默认 `admin`，改为最低权限或直接拒绝，具体由迁移适配层控制。

## 7. 后端架构

### 7.1 公共权限模块

建议新增并逐步收敛为以下模块：

```text
app/common/
├── auth.py              # 令牌、用户加载、兼容现有认证
├── identity.py          # Principal 和请求身份上下文
├── permissions.py       # 权限常量和角色默认权限
├── policy.py            # ABAC 策略判断
├── authorization.py     # require_permission、authorize_resource
├── audit.py             # 审计事件接口和安全字段过滤
└── rbac.py              # 兼容旧过滤函数，最终调用 policy
```

本阶段不要求一次性删除 `rbac.py`。旧的 `build_where`、`make_pred`、`filter_dataframe_rows` 保留兼容入口，但内部必须使用统一策略对象，避免两套规则长期漂移。

### 7.2 FastAPI 依赖

统一提供：

```python
get_current_principal(request) -> Principal
require_permission("document:read")
require_any_permission(...)
authorize_resource(principal, action, resource)
```

API 处理函数只负责：

1. 获取主体；
2. 声明所需权限；
3. 获取资源元数据；
4. 调用授权策略；
5. 执行业务逻辑；
6. 写入审计事件。

禁止在 API 中直接读取 `request.state.user["role"]` 后自行拼接权限判断。

### 7.3 统一错误

REST API：

```json
{
  "error": {
    "code": "permission_denied",
    "message": "没有执行该操作的权限",
    "request_id": "..."
  }
}
```

- 未认证：HTTP 401，错误码 `authentication_required`
- 功能权限不足：HTTP 403，错误码 `permission_denied`
- 资源存在但范围不足：HTTP 404，错误码 `resource_not_found`
- 策略或服务异常：HTTP 503，错误码 `authorization_unavailable`

不向客户端返回角色内部规则、其他部门名称或资源是否确实存在等敏感信息。

## 8. Agent 与后台任务授权

### 8.1 Agent 上下文

Planner、Worker、Critic 和汇总 Agent 使用统一 `AgentContext`：

```text
AgentContext
├── principal
├── request_id
├── session_id
├── allowed_actions
├── allowed_resource_scope
└── trace_id
```

Worker 不能自行修改 `principal`、`allowed_actions` 或部门范围。

### 8.2 工具授权

每个工具声明：

```text
ToolPolicy
├── tool_name
├── required_permission
├── resource_types
├── read_or_write
├── supports_row_filter
└── audit_event
```

调用流程：

```text
Planner 选择工具
 -> Tool Gateway 检查工具权限
 -> 资源策略检查
 -> 工具执行
 -> 输出过滤
 -> 写入 Trace 和审计
```

例如：

- `query_data` 需要 `agent:tool:query_data` 和 `data:read`
- `visualize` 需要 `agent:tool:visualize`、`data:read` 和 `chart:generate`
- `export` 需要 `agent:tool:export` 和 `export:create`
- `delete_document` 需要 `agent:tool:delete_document` 和 `document:delete`

任何工具权限失败都必须返回结构化 `AgentResult(status="permission_denied")`，不能返回普通字符串掩盖失败。

### 8.3 后台任务

调度器、文件解析和主动洞察任务使用独立系统主体：

```text
system:ingestion
system:insight_scanner
system:alert_scheduler
```

系统主体只拥有完成任务所需的最小权限，不能复用管理员主体，也不能把系统任务结果直接暴露给所有用户。结果读取时仍按当前用户策略过滤。

## 9. 资源接入清单

### 9.1 知识库文档

- 列表：`document:read`
- 预览：`document:preview`
- 下载：`document:download`
- 上传：`document:upload`
- 删除：`document:delete`
- 检索和证据：同时检查 `document:read`、密级和部门范围
- 原文高亮：引用中的每个片段重新执行资源授权，不能只信任模型返回的引用

### 9.2 数据文件与分析

- 数据文件列表和预览：`data:read`、`data:preview`
- 分析：`analysis:run`
- 图表：`chart:generate`
- 导出：`export:create`
- 文件级策略先于 Excel 行级过滤
- 结果中不能混入未授权行，也不能通过聚合结果反推出被过滤数据

### 9.3 告警与主动洞察

- 查看：`alert:read` 或 `insight:read`
- 创建/修改规则：manager/admin
- 删除规则：admin
- 后台扫描可以读取必要数据，但推送和展示仍按部门、密级和订阅范围过滤

### 9.4 会话、证据和审批

- 会话默认按 `owner_id` 隔离
- 管理员不因角色自动读取员工私有会话，除非有明确审计权限和审计原因
- 证据片段继承源文档权限
- 审批助手的提交人、审批人、责任部门和金额范围都进入资源策略

## 10. 数据模型与迁移

### 10.1 用户表扩展

保持现有字段兼容，逐步增加：

```text
users
├── id
├── username
├── password_hash
├── role
├── department
├── status
├── auth_source
├── last_login_at
├── token_version
└── created_at / updated_at
```

本阶段角色仍使用单角色字段，权限集合由角色映射得到。多角色通过后续 `user_roles` 表扩展，不在本阶段强行引入。

### 10.2 权限与角色映射

可先使用代码内置映射，稳定后迁移到表：

```text
roles
permissions
role_permissions
```

迁移必须提供默认映射和回滚方案。已有 `admin` 保持全局管理权限，已有 `staff` 和 `manager` 的文档过滤行为不能被意外放宽。

### 10.3 审计表

```text
audit_events
├── id
├── request_id
├── trace_id
├── actor_id
├── actor_username
├── actor_role
├── department
├── action
├── resource_type
├── resource_id
├── decision
├── reason_code
├── latency_ms
├── metadata_json
└── created_at
```

`metadata_json` 必须经过敏感字段过滤，限制长度，禁止保存密码、令牌、API Key 和完整文档正文。

## 11. 明确的多 Agent 分工

### 11.1 主 Agent：公共契约与集成负责人

负责：

- 建立 `Principal`、权限常量、策略接口和错误契约；
- 修改 `app/main.py`、`app/agents/orchestrator.py` 等共享入口；
- 维护迁移兼容层；
- 集成其他 Agent 分支；
- 处理冲突和统一回归。

独占文件：

```text
app/common/identity.py
app/common/permissions.py
app/common/policy.py
app/common/authorization.py
app/common/rbac.py
app/agents/orchestrator.py
app/main.py
```

其他 Agent 不得修改以上文件。

### 11.2 Agent A：认证上下文

负责：

- 用户状态、角色映射和权限加载；
- JWT 与请求身份上下文；
- 认证依赖和 401 处理；
- 本地内存存储、PostgreSQL 两种模式兼容。

允许修改：

```text
app/common/auth.py
app/common/sso.py
tests/test_auth_context.py
tests/test_auth.py
```

不负责权限策略本身，不修改 API 资源代码。

### 11.3 Agent B：文档与证据资源

负责：

- 文档列表、上传、预览、下载、删除；
- 文档 catalog 和检索证据授权；
- 原文打开/高亮前的二次授权；
- 文档越权和密级测试。

允许修改：

```text
app/api/v1/chat.py
app/api/v1/data.py  # 仅文档相关交界处需先由主 Agent 划分
app/documents/
app/rag/
tests/test_document_authorization.py
tests/test_evidence_authorization.py
```

为避免 `chat.py` 冲突，实际执行时应将文档相关改动先拆成独立提交，由主 Agent 集成；其他 Agent 不得顺手重构聊天流程。

### 11.4 Agent C：数据、图表、告警和洞察

负责：

- 数据文件列表、预览、分析和导出；
- 图表生成；
- 告警规则和主动洞察结果；
- 行级过滤与聚合结果权限；
- 数据和洞察越权测试。

允许修改：

```text
app/api/v1/data.py
app/api/v1/alerts.py
app/insights/
app/analytics/
tests/test_data_authorization.py
tests/test_alert_authorization.py
tests/test_insight_authorization.py
```

不得修改公共策略文件和聊天 Agent 编排。

### 11.5 Agent D：用户管理与审计

负责：

- 用户管理、角色修改、账号禁用；
- 审计日志存储、查询、脱敏；
- 管理员与审计员 API；
- 管理操作审计测试。

允许修改：

```text
app/api/v1/auth.py
app/common/audit.py
app/audit/
tests/test_user_management_authorization.py
tests/test_audit_log.py
```

用户管理 API 的最终权限依赖由主 Agent 提供，Agent D 不重复实现策略。

### 11.6 Agent E：前端权限体验

负责：

- 当前用户权限加载；
- 页面、按钮和菜单的权限展示；
- 401 跳转登录；
- 403/404/策略异常的友好提示；
- 文档、分析、告警、审计等页面的权限状态。

允许修改：

```text
frontend/src/
tests/test_frontend_authorization.py
```

前端隐藏按钮不能被视为安全验证，必须配合后端测试。

### 11.7 Review Agent：安全审查和浏览器验证

负责：

- 汇总权限矩阵；
- 检查所有 API 是否有认证和操作权限；
- 构造普通用户、部门经理、管理员、审计员测试身份；
- 验证跨部门、跨密级、资源猜测、工具越权；
- 使用真实浏览器验证按钮、错误提示和数据列表；
- 检查慢测、阻塞和权限回归。

Review Agent 只修改测试和审查报告，不直接修改业务实现，除非主 Agent 明确分配修复文件。

## 12. 并行开发顺序

不能一开始让所有 Agent 同时开发。依赖顺序如下：

```text
阶段 0：主 Agent 建立公共契约和测试夹具
    ↓
阶段 1：Agent A 完成认证上下文
    ↓
阶段 2：B、C、D、E 并行适配各自资源
    ↓
阶段 3：主 Agent 接入 Agent/MCP/后台任务
    ↓
阶段 4：Review Agent 进行 API、Agent、浏览器和全量测试
    ↓
阶段 5：主 Agent 修复集成问题并再次验证
```

并行规则：

1. 每个 Agent 只修改自己声明的文件。
2. 不允许多个 Agent 同时修改 `app/common/*` 公共策略文件。
3. 不允许为了方便把共享逻辑复制到各自目录。
4. 所有跨模块需求先写接口或测试，再由主 Agent 合并。
5. 每个 Agent 完成后提供改动文件、测试命令、已知风险和待集成点。

## 13. 测试设计

### 13.1 单元测试

- 角色到权限映射；
- 密级判断；
- 部门范围；
- 所有者范围；
- 缺失元数据；
- 非法角色和非法密级；
- 策略异常时默认拒绝；
- Chroma、BM25、DataFrame 三种过滤结果一致。

### 13.2 API 测试

每个受保护 API 至少测试：

- 未登录；
- staff 正常访问；
- manager 部门内访问；
- manager 跨部门访问；
- admin 全局访问；
- auditor 只读访问；
- 无权限操作；
- 不存在资源；
- 禁用用户；
- 过期或伪造令牌。

### 13.3 Agent 测试

- Planner 选择无权限工具时被拒绝；
- Worker 不能修改主体上下文；
- 检索结果不包含越权文档；
- 数据工具不返回越权行；
- 图表和导出继承源数据权限；
- 证据引用重新校验权限；
- 工具失败返回结构化结果；
- Trace 包含权限决策和失败原因。

### 13.4 前端和浏览器测试

- 普通用户看不到管理员按钮；
- 直接调用接口仍被后端拒绝；
- 登录过期自动回登录页；
- 403 显示明确提示，不出现 JSON 解析错误；
- 文档、数据文件、告警列表只显示当前权限范围；
- 上传、下载、预览、删除和分析按钮状态与真实后端结果一致。

### 13.5 性能与阻塞测试

- 单次请求不能重复加载模型或重复创建权限配置；
- 权限检查不得触发全量文档读取；
- 审计写入不能阻塞主请求，可采用短队列或异步写入；
- 大量资源列表必须分页；
- 全量测试按测试模块分组运行，定位超过阈值的慢测；
- 为模型、数据库和浏览器测试设置明确超时。

## 14. 兼容、迁移与回滚

### 14.1 兼容策略

- 保留 `staff`、`manager`、`admin`；
- 旧文档字段 `classification`、`department` 继续可用；
- 旧检索过滤函数保留兼容入口；
- 旧的 `role/department` Agent 配置转换为 `Principal`；
- 旧接口响应字段暂不删除，只增加权限信息和错误码。

### 14.2 分阶段发布

1. 影子模式：记录策略结果，但不改变允许结果，用于发现现有接口缺口。
2. 只读资源强制：先保护列表、预览、下载、检索和证据。
3. 写操作强制：保护上传、删除、告警配置、用户管理和导出。
4. Agent 工具强制：所有工具通过 Tool Gateway。
5. 审计和前端权限状态完整上线。

### 14.3 回滚

- 通过环境变量切换策略模式：`legacy`、`shadow`、`enforced`；
- 回滚不能关闭身份认证；
- 回滚只允许恢复兼容过滤逻辑，不允许把普通用户提升为管理员；
- 所有策略模式切换进入审计日志。

## 15. 验收清单

交付前必须满足：

- 所有受保护 API 都有统一认证入口；
- 所有写操作都有明确操作权限；
- 文档、数据、证据、图表、告警和洞察共享同一数据范围规则；
- 普通用户不能删除文档或管理用户；
- 不同部门无法通过列表、详情、下载、搜索、分析、图表和证据绕过权限；
- Agent 工具不能绕过 RBAC/ABAC；
- 审计日志记录允许和拒绝事件且不泄露敏感数据；
- 前端权限状态与后端最终结果一致；
- 旧测试保持通过，新增权限测试全部通过；
- `test_private_model_routing.py` 的 `model_name` 问题单独修复；
- 全量测试不再无限等待，并能输出慢测定位信息；
- 前端生产构建通过；
- 浏览器完成至少一轮真实登录、越权、上传、下载、分析和管理员操作验证。

## 16. 设计结论

本项目不直接实现完整企业 IAM，而是落地“可生产使用的 RBAC + ABAC 核心层”。该方案能解决当前项目最现实的安全问题：功能越权、跨部门读取、密级绕过、Agent 工具越权、证据泄露和缺少审计，同时把 SSO、LDAP、多角色和多租户保留为后续扩展点。

实施时必须先完成公共权限契约，再分派资源模块。多 Agent 的关键不是让所有 Agent 同时改代码，而是通过清晰的文件所有权、稳定的接口契约和 Review Agent 的越权测试实现并行而不失控。
