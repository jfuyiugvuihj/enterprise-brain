# 企业智脑完整升级总方案

## 1. 文档定位

- 日期：2026-09-08
- 状态：总方案草案
- 项目：企业智脑
- 目标：将当前“知识库问答 + 数据分析 Demo”升级为可供公司内部试用的企业智能决策与审批平台
- 适用代码库：`C:\Users\fengx\PycharmProjects\企业智脑`

本方案整合此前已经提出的全部升级方向：

1. 测试基线与稳定性
2. 完整 RBAC + ABAC
3. 多 Agent 协作闭环
4. 答案溯源与可信度标注
5. 业务语义层
6. 主动洞察
7. 智能经营驾驶舱
8. 轻量企业知识图谱
9. 智能审批助手
10. Trace、评估集与可观测性
11. 性能优化
12. 生产部署与安全
13. 前端体验、浏览器验证和最终答辩演示

## 2. 最终产品定位

最终产品不再只是“用户提问，模型回答”，而是：

> 一个以企业私有数据为基础，能够安全检索、准确分析、主动发现问题、解释分析口径、辅助审批决策，并保留完整证据和审计记录的多 Agent 企业智能平台。

核心闭环为：

```text
企业数据/制度文档
        ↓
权限过滤 + 业务语义识别
        ↓
Planner 拆解任务
        ↓
Doc/Data/Chart/Graph/Approval Worker 并行执行
        ↓
Critic 证据、口径、权限和逻辑审查
        ↓
Synthesis 汇总答案、图表、审批建议和风险
        ↓
用户确认、处理洞察、执行审批
        ↓
Trace、审计、评估和反馈反哺系统
```

## 3. 第一版必须实现与明确不做

### 3.1 第一版必须实现

- 用户登录、角色、部门和资源权限；
- 文档、Excel/CSV 文件的上传、预览、下载、检索和删除；
- Planner、多个 Worker、Critic、Synthesis 的结构化闭环；
- 每个答案展示证据来源、定位、可信度和指标口径；
- 业务字段和指标定义管理；
- Excel 主动异常检测和洞察列表；
- 指标卡、趋势图、部门对比、异常列表组成的驾驶舱；
- 制度匹配、额度计算、责任方判断和审批路径建议；
- 文档、制度、部门、角色、指标之间的轻量知识图谱；
- Agent Trace、审计日志和评估集；
- 本地私有模型优先，外部模型仅作为测试适配，不作为正式部署依赖；
- Docker/部署配置、健康检查、备份、日志和安全基线。

### 3.2 第一版明确不做

- 自动批准真实财务审批；
- Agent 直接修改企业原始数据；
- 自动执行付款、转账或删除生产数据；
- 一次性引入 Neo4j、复杂图数据库集群；
- 完整 LDAP/AD/SSO 生命周期管理；
- 多租户计费体系；
- 无限轮次 Agent 辩论；
- 没有证据时把模型推测显示为确定事实。

## 4. 总体架构

### 4.1 分层结构

```text
前端层
├── 智能问答
├── 知识库
├── 数据分析
├── 驾驶舱
├── 主动洞察
├── 审批助手
├── 知识图谱
└── 管理与审计

API 层
├── auth
├── chat
├── documents
├── data
├── insights
├── dashboard
├── approval
├── knowledge_graph
├── audit
└── admin

智能编排层
├── Planner
├── Doc Worker
├── Data Worker
├── Chart Worker
├── Export Worker
├── Graph Worker
├── Approval Worker
├── Critic
└── Synthesis

治理层
├── Principal 身份上下文
├── RBAC + ABAC 策略
├── 业务语义层
├── 证据与可信度
├── Trace
├── 审计日志
└── 评估集

数据层
├── PostgreSQL 或兼容存储
├── Chroma 检索库
├── 文件存储
├── 语义目录
├── 洞察存储
├── 图谱存储
└── 缓存/队列

运行层
├── FastAPI
├── Vue 3
├── Ollama 私有模型
├── APScheduler/任务队列
├── Docker Compose
├── 监控和日志
└── 备份与恢复
```

### 4.2 核心数据流

```text
请求进入
  → 加载 Principal
  → 检查功能权限
  → 生成资源范围
  → Planner 拆解
  → Worker 通过 Tool Gateway 调用工具
  → 每次检索/工具调用写 Trace
  → 结果生成 Evidence、MetricContext、AgentResult
  → Critic 检查证据、口径、权限和冲突
  → 必要时最多重试一次
  → Synthesis 生成最终结果
  → 再次过滤证据和资源
  → 写审计
  → SSE/HTTP 返回前端
```

## 5. 公共数据契约

所有模块必须基于公共契约协作，禁止各 Agent 自行定义重复字段。

### 5.1 Principal

```text
Principal
├── user_id
├── username
├── role
├── permissions
├── department
├── department_ids
├── clearance
├── status
├── auth_source
└── is_system
```

### 5.2 Evidence

```text
Evidence
├── source_type: document/table/chart/rule/inference
├── source_name
├── document_id
├── locator
├── page
├── paragraph
├── sheet
├── columns
├── row_range
├── excerpt
├── score
└── permission_checked
```

### 5.3 MetricContext

```text
MetricContext
├── metric_name
├── definition
├── formula
├── unit
├── time_granularity
├── include_refund
├── include_tax
├── filters
├── source_file
└── warnings
```

### 5.4 AgentResult

```text
AgentResult
├── task_id
├── worker
├── status
├── answer
├── evidence
├── metrics
├── confidence
├── confidence_label
├── warnings
├── artifacts
├── duration_ms
└── trace_id
```

### 5.5 ReviewResult

```text
ReviewResult
├── passed
├── issues
├── missing_evidence
├── conflicting_evidence
├── permission_violations
├── metric_warnings
├── recommended_action
└── confidence
```

## 6. 升级阶段总览

| 阶段 | 名称 | 结果 |
|---|---|---|
| 0 | 基线修复与工程准备 | 项目可启动、测试可定位、模型路由稳定 |
| 1 | RBAC + ABAC 权限底座 | 所有 API、资源和工具可授权、可审计 |
| 2 | 多 Agent 协作闭环 | Planner、Worker、Critic、Synthesis 真正接通 |
| 3 | 答案溯源与业务语义层 | 每个结论可解释、每个指标有口径 |
| 4 | 主动洞察 | 系统能自动扫描并发现异常 |
| 5 | 驾驶舱 | 指标、趋势、部门、异常形成经营视图 |
| 6 | 知识图谱 | 制度、部门、角色、指标和审批关系可查询 |
| 7 | 审批助手 | 制度匹配、超额计算、责任方和审批路径建议 |
| 8 | Trace、评估和质量平台 | 可追踪、可量化、可回归 |
| 9 | 性能优化 | 降低模型、检索、分析和页面等待时间 |
| 10 | 生产部署与安全 | 私有化、备份、监控、恢复和上线验收 |
| 11 | 全量联调与答辩演示 | 浏览器完整闭环、演示数据和验收报告 |

## 7. 阶段 0：基线修复与工程准备

### 目标

先把当前项目恢复到“可重复启动、可重复测试、可定位阻塞”的状态，不能在测试基线不清楚时继续堆叠业务功能。

### 必须处理

- 修复 `test_private_model_routing.py` 中 `_ResilientModel.model_name` 缺失；
- 定位全量测试 240 秒未结束的测试或阻塞点；
- 为模型、数据库、浏览器和调度器测试增加超时；
- 区分环境依赖失败、历史回归失败和本次代码失败；
- 修复前后端启动命令和依赖说明；
- 保留一份当前工作区检查点，不覆盖历史未提交改动；
- 前端生产构建通过；
- Ollama 模型路由、离线回退和私有模型配置明确。

### 交付物

```text
tests/test_upgrade_baseline.py
docs/testing/baseline-2026-09-08.md
scripts/run_backend_tests.ps1
scripts/run_frontend_tests.ps1
```

### 通过标准

- 相关测试全部通过；
- 全量测试可以结束并输出耗时；
- 前端构建通过；
- 后端可以启动；
- Ollama 不可用时有清晰降级，不阻塞 API。

## 8. 阶段 1：完整 RBAC + ABAC

### 目标

从“角色决定密级”升级为“功能权限 + 资源范围 + 密级 + 所有者 + 审计”的完整授权体系。

### 角色

- `staff`：本人及部门范围内的基础业务能力；
- `manager`：部门分析、告警和导出；
- `admin`：全局管理；
- `auditor`：全局审计只读。

### 权限维度

- 功能权限：查看、上传、下载、删除、分析、导出、审批、审计；
- 数据范围：本人、部门、全公司；
- 文档密级：公开、内部、机密；
- 资源状态：草稿、已发布、已归档；
- Agent 工具：检索、分析、画图、导出、删除；
- 审计：成功、拒绝、失败和策略异常。

### 关键改造

- 新增 `Principal`；
- 新增集中权限常量；
- 新增 `require_permission`；
- 新增 `authorize_resource`；
- 统一 401、403、404、503；
- 检索、预览、下载、分析、导出和证据展示使用同一资源策略；
- Agent 工具必须经过 Tool Gateway；
- 系统后台任务使用独立最小权限身份；
- 旧 `rbac.py` 函数保留兼容入口，但内部逐步收敛到统一策略；
- 前端根据权限展示按钮，但不把前端隐藏当作安全措施。

### 主要文件

```text
app/common/identity.py
app/common/permissions.py
app/common/policy.py
app/common/authorization.py
app/common/audit.py
app/common/auth.py
app/common/rbac.py
app/api/v1/auth.py
app/api/v1/chat.py
app/api/v1/data.py
app/api/v1/alerts.py
tests/test_rbac_abac.py
tests/test_authorization_api.py
tests/test_agent_tool_authorization.py
```

### 通过标准

- 未登录访问受保护 API 返回 401；
- 普通用户访问管理员功能返回 403；
- 跨部门文档、数据、证据、图表和导出不可绕过；
- 删除、用户管理、告警管理和审批操作都有权限检查；
- 所有拒绝行为可在审计中追踪。

## 9. 阶段 2：多 Agent 协作闭环

### 目标

将当前“Supervisor 选择 Worker”升级为：

```text
Planner → 并行 Worker → Critic → 必要重试 → Synthesis
```

### Agent 职责

- Planner：识别问题类型、拆解任务和依赖；
- Doc Worker：检索制度和文档；
- Data Worker：执行指标计算和数据分析；
- Chart Worker：生成图表；
- Export Worker：生成可下载报告；
- Graph Worker：查询业务关系；
- Approval Worker：执行审批预审逻辑；
- Critic：检查证据、口径、权限、数字和冲突；
- Synthesis：生成最终回答、建议和引用。

### 规则

- 独立 Worker 并行执行；
- 工具失败不能让整个 SSE 永久等待；
- Critic 最多触发一次补偿；
- 所有 Worker 返回 `AgentResult`；
- 无权限工具返回 `permission_denied`；
- 单轮对话状态必须隔离，避免多问题串线；
- 保留简单问题快速路径，避免所有问题都进入重型闭环。

### 前端

显示：

```text
任务规划
├── 文档检索
├── 数据分析
├── 图表生成
├── 证据审查
└── 汇总回答
```

每一步包含状态、耗时、错误、摘要和可展开证据。

## 10. 阶段 3：答案溯源与业务语义层

### 10.1 答案溯源

文档证据必须包含：

- 文件名；
- 页码；
- 段落或 chunk；
- 原文片段；
- 检索分数；
- 权限校验结果。

Excel/CSV 证据必须包含：

- 文件名；
- 工作表；
- 列名；
- 行范围；
- 筛选条件；
- 计算过程。

点击引用后：

- PDF 跳转页码；
- 文本高亮段落；
- Excel 高亮工作表、列和行；
- 无权限证据不返回；
- 无证据时显示“引用不足”或“推测”。

### 10.2 业务语义层

每个指标至少维护：

- 显示名称；
- 字段名和别名；
- 定义；
- 公式；
- 单位；
- 时间粒度；
- 是否含税；
- 是否含退款；
- 数据来源；
- 责任部门；
- 状态：`draft`、`verified`、`deprecated`。

分析之前必须完成：

```text
用户问题
  → 指标和字段匹配
  → 读取业务口径
  → 检查口径冲突
  → 注入 Data Worker
  → 返回 MetricContext
```

未确认口径只能作为提醒，不得伪装成正式口径。

## 11. 阶段 4：主动洞察

### 目标

让系统从“被动问答”升级为“自动发现问题”。

### 首批规则

- 环比或同比超过阈值；
- 连续多个周期下降；
- 超过制度标准；
- 部门之间差异异常；
- 数据缺失；
- 重复记录；
- 指标口径冲突；
- 文件长时间未更新。

### 洞察模型

```text
Insight
├── id
├── title
├── severity
├── summary
├── metric
├── current_value
├── previous_value
├── change_rate
├── evidence
├── recommended_action
├── status
└── created_at
```

### 处理流程

```text
定时任务/上传触发
  → 文件权限过滤
  → 语义指标识别
  → 确定性规则检测
  → 生成证据
  → 可选模型解释
  → 去重
  → 保存洞察
  → 按部门权限展示
```

模型只负责解释原因和生成建议，不负责单独决定异常是否存在。

## 12. 阶段 5：智能经营驾驶舱

### 页面区域

1. 指标卡：当前值、变化率、口径和来源；
2. 趋势图：按日、周、月显示；
3. 部门对比：排名、差异和可见范围；
4. 异常列表：严重级别、证据和处理状态；
5. 制度关联：跳转制度原文；
6. 快捷提问：带入当前指标、文件和洞察上下文。

### API

```text
GET /api/v1/dashboard/summary
GET /api/v1/dashboard/trends
GET /api/v1/dashboard/departments
GET /api/v1/dashboard/anomalies
```

所有 API 必须使用 RBAC/ABAC，部门对比不能泄露无权限部门数据。

### 通过标准

- 至少展示 3 个真实指标；
- 至少生成 1 个趋势图；
- 至少识别 1 个测试数据异常；
- 异常可以跳转到证据和业务口径；
- 刷新后状态一致；
- 移动端和桌面端基本可用。

## 13. 阶段 6：轻量知识图谱

### 目标

将制度、部门、角色、费用、指标和审批节点之间的关系结构化。

### 实体

- 文档；
- 制度；
- 部门；
- 角色；
- 员工；
- 费用类型；
- 指标；
- 审批节点；
- 数据文件。

### 关系

- 制度规定费用标准；
- 费用由角色承担；
- 角色属于部门；
- 部门执行制度；
- 费用需要审批节点；
- 指标来自数据字段；
- 文档支持某个结论；
- 审批节点属于某个部门。

### 可靠性规则

- 自动抽取关系初始为 `candidate`；
- 没有原文证据的关系不能进入可信图谱；
- 管理员可以确认、拒绝或修正；
- 图谱查询必须返回关系来源；
- 图谱结果必须再次执行资源权限过滤。

第一版使用 PostgreSQL/JSON 或本地持久化存储，保留图数据库适配接口，不强制部署 Neo4j。

## 14. 阶段 7：智能审批助手

### 定位

审批助手只生成预审建议和审批草稿，不直接完成真实财务审批。

### 输入

- 申请类型；
- 申请金额；
- 部门；
- 费用类型；
- 项目；
- 申请人；
- 时间；
- 附件和相关文档。

### 处理流程

```text
提交事项
  → 字段校验
  → 业务语义匹配
  → 制度文档检索
  → 知识图谱查询
  → 标准额度计算
  → 超额判断
  → 责任方判断
  → 审批路径推导
  → Critic 证据审核
  → 输出预审建议
```

### 输出

- 事项摘要；
- 匹配制度；
- 允许标准；
- 实际金额；
- 超出金额和比例；
- 责任部门或角色；
- 审批路径；
- 风险等级；
- 证据；
- 可信度；
- 可编辑审批说明。

### 安全约束

- 不自动批准；
- 不直接修改财务系统；
- 申请人只能看自己的申请；
- 审批人只能看授权范围；
- 管理员和审计员访问进入审计日志；
- 制度证据不足时必须标记“无法确认”。

## 15. 阶段 8：Trace、评估和质量平台

### Trace 内容

记录：

- 请求 ID；
- 会话 ID；
- 用户和权限摘要；
- Planner 计划；
- 检索耗时；
- 工具调用；
- 模型调用耗时；
- Worker 状态；
- Critic 结果；
- 重试原因；
- 最终结果；
- 错误和拒绝原因。

禁止记录：

- 密码；
- JWT；
- API Key；
- 完整敏感文档正文；
- 不必要的原始个人信息。

### 评估集

准备至少 30 至 50 条真实业务问题，分为：

- 文档问答；
- 多轮对话；
- Excel 计算；
- 口径冲突；
- 图表生成；
- 主动洞察；
- 审批判断；
- 跨部门权限；
- 无证据问题；
- 工具调用问题。

### 评估指标

- 回答正确率；
- 证据覆盖率；
- 证据定位准确率；
- 指标口径准确率；
- 工具选择准确率；
- 图表数据准确率；
- 权限拒绝准确率；
- 平均响应时间；
- P95 响应时间；
- SSE 中断率；
- 多轮上下文正确率。

## 16. 阶段 9：性能优化

### 重点问题

- 模型重复加载；
- 多 Agent 同时占满本地显存或内存；
- 重复 embedding；
- 长上下文导致推理慢；
- Excel 全表重复加载；
- 前端轮询过多；
- 上传解析与问答互相阻塞；
- 全量测试包含无超时的真实模型调用。

### 优化策略

- 模型单例和生命周期管理；
- embedding、检索、语义定义和洞察结果缓存；
- 文件版本哈希去重；
- 限制上下文长度；
- Planner 任务预算和并发上限；
- 小问题使用快速路径；
- 规则检查优先于模型调用；
- Excel 解析结果缓存；
- 后台任务异步化；
- SSE 支持心跳、取消和超时；
- 列表分页；
- 只返回必要数据；
- 统一慢测报告。

### 性能目标

第一版目标：

- 登录接口 P95 小于 500ms；
- 文档列表 P95 小于 800ms；
- 已缓存检索 P95 小于 2s；
- 简单问答首字节小于 3s；
- 数据分析有明确进度和超时；
- 任何请求不得无限等待；
- 同时运行多个大模型任务时有并发保护。

## 17. 阶段 10：生产部署与安全

### 部署形态

```text
Nginx/反向代理
  → Frontend
  → FastAPI
  → PostgreSQL
  → Chroma
  → 文件存储
  → Redis/任务队列
  → Ollama 私有模型服务
```

### 必须具备

- Docker Compose 一键启动；
- `.env.example`；
- JWT 密钥不进 Git；
- 数据库初始化和迁移；
- 文件目录隔离；
- 上传文件类型和大小限制；
- 路径穿越防护；
- 文件名规范化；
- 敏感数据脱敏；
- 访问和拒绝审计；
- 数据库、文件和 Chroma 备份；
- 恢复演练；
- 健康检查；
- 模型服务健康检查；
- 日志轮转；
- 监控 CPU、内存、磁盘、队列、模型耗时和错误率。

### 安全验收

- 普通用户无法读取其他部门文档；
- 下载、预览、检索和证据权限一致；
- Agent 工具不能绕过权限；
- 管理员删除有审计；
- 审计日志不泄露令牌和密码；
- 文件不可通过路径穿越读取；
- 禁用用户旧令牌不能继续使用；
- 服务重启后任务状态可恢复或明确失败。

## 18. 多 Agent 并行开发分工

### 主集成 Agent

负责：

- 公共契约；
- 权限公共层；
- Agent State；
- LangGraph；
- SSE；
- 主分支合并；
- 最终全量测试。

独占：

```text
app/agents/contracts.py
app/agents/state.py
app/agents/orchestrator.py
app/agents/nodes.py
app/api/v1/chat.py
app/main.py
```

### 权限 Agent

负责：

```text
app/common/auth.py
app/common/identity.py
app/common/permissions.py
app/common/policy.py
app/common/authorization.py
app/common/audit.py
app/common/rbac.py
tests/test_rbac_abac.py
tests/test_authorization_api.py
```

### 溯源与语义 Agent

负责：

```text
app/rag/
app/documents/
app/quality/
app/semantics/
tests/test_answer_provenance.py
tests/test_business_semantics.py
frontend/src/components/EvidencePanel.vue
frontend/src/components/SemanticDefinitionPanel.vue
```

### 主动洞察 Agent

负责：

```text
app/insights/
app/api/v1/insights.py
app/scheduler/
tests/test_insights.py
tests/test_insight_scheduler.py
frontend/src/components/InsightPanel.vue
```

### 驾驶舱 Agent

负责：

```text
app/api/v1/dashboard.py
frontend/src/components/DashboardPanel.vue
frontend/src/components/MetricCard.vue
frontend/src/components/InsightCard.vue
tests/test_dashboard.py
```

### 知识图谱 Agent

负责：

```text
app/knowledge_graph/
app/api/v1/knowledge_graph.py
frontend/src/components/KnowledgeGraphPanel.vue
tests/test_knowledge_graph.py
```

### 审批助手 Agent

负责：

```text
app/approval/
app/api/v1/approval.py
frontend/src/components/ApprovalPanel.vue
tests/test_approval_assistant.py
```

### 性能与部署 Agent

负责：

```text
app/common/cache.py
app/common/model_handler.py
deploy/
Dockerfile
docker-compose.yml
docs/deployment/
tests/test_performance_guards.py
```

### Review Agent

只负责：

- 跨模块接口检查；
- 越权测试；
- 性能测试；
- 浏览器验证；
- 全量测试报告；
- 安全问题清单。

Review Agent 原则上不直接修改业务实现。

## 19. 并行开发顺序

不能所有 Agent 同时开工，正确顺序为：

```text
阶段 0：主 Agent 修复基线
    ↓
阶段 1：主 Agent 建立公共契约
    ↓
权限 Agent 完成 RBAC/ABAC
    ↓
溯源 Agent + 语义 Agent 并行
    ↓
主动洞察 Agent 并行
    ↓
主 Agent 接通多 Agent 闭环
    ↓
驾驶舱 Agent + 知识图谱 Agent + 审批助手 Agent 并行
    ↓
性能部署 Agent
    ↓
Review Agent 全面验收
    ↓
主 Agent 修复集成问题
```

并行硬规则：

1. 同一文件只能由一个 Agent 负责。
2. 公共契约文件只能由主 Agent 修改。
3. Agent 不得为了方便复制公共策略或数据模型。
4. 每个 Agent 必须先写失败测试，再实现功能。
5. 每个 Agent 完成后必须报告文件、接口、测试、风险和集成点。
6. 真实 Ollama 测试只在主集成线串行执行。
7. 合并任何分支后立即运行该模块测试。
8. 未通过基线不得继续扩展下一个大阶段。

## 20. 测试总矩阵

### 后端

- 单元测试；
- API 认证测试；
- RBAC/ABAC 越权测试；
- 文档检索和证据测试；
- Excel 计算和口径测试；
- Agent 合作测试；
- 洞察规则测试；
- 驾驶舱聚合测试；
- 图谱关系和来源测试；
- 审批路径测试；
- 审计脱敏测试；
- 超时和并发测试。

### 前端

- 生产构建；
- 登录和注册；
- 上传多个文件；
- 解析进度；
- 文件列表即时刷新；
- 预览和下载；
- 删除权限；
- 多轮问答；
- Agent Trace；
- 证据高亮；
- 驾驶舱；
- 主动洞察；
- 图谱；
- 审批助手；
- 401/403/500/502/空响应处理。

### 浏览器验收主流程

1. 使用普通用户登录；
2. 上传制度 PDF 和分析 Excel；
3. 查看文件进入知识库和数据分析；
4. 打开驾驶舱；
5. 查看主动洞察；
6. 点击洞察打开证据；
7. 提出需要文档和数据联合分析的问题；
8. 查看 Planner、Worker、Critic、汇总过程；
9. 检查引用页码、工作表、列名和行范围；
10. 打开知识图谱；
11. 提交审批助手预审；
12. 使用管理员验证用户管理和删除；
13. 使用跨部门普通用户验证越权；
14. 刷新页面确认状态持久化；
15. 重启服务确认数据、任务和权限仍然正确。

## 21. 最终演示场景

使用一份制度文档和一份经营分析 Excel，演示：

> 分析本月各部门差旅费用，找出超过住宿标准的项目，说明异常原因，结合制度判断责任部门和审批路径，展示趋势图、证据原文、指标口径、知识图谱关系，并生成审批预审建议。

该场景一次覆盖：

- 多 Agent 拆解；
- 文档检索；
- Excel 分析；
- 业务语义；
- 答案溯源；
- 可信度；
- 主动洞察；
- 驾驶舱；
- 知识图谱；
- 审批助手；
- RBAC/ABAC；
- Trace 和审计。

## 22. 最终验收标准

### 功能

- 多 Agent 能够拆解、并行、审查和汇总；
- 文档和数据回答有真实证据；
- 指标有明确口径；
- 系统能主动发现异常；
- 驾驶舱能展示经营信息；
- 图谱能展示制度、部门、角色和指标关系；
- 审批助手能输出有依据的预审建议；
- 管理员和普通用户权限边界正确。

### 质量

- 基线测试恢复并保持通过；
- 新增测试全部通过；
- 全量测试可结束且无无限阻塞；
- 前端生产构建通过；
- 浏览器主流程通过；
- 真实模型不可用时系统有明确降级；
- 失败时前端不出现 JSON 解析崩溃或无限转圈。

### 安全

- 所有受保护资源统一鉴权；
- 查询、预览、下载、证据和图表不能绕过权限；
- 审批结果不能直接变成真实审批；
- 审计日志完整且脱敏；
- 文件和模型服务部署隔离；
- 数据备份和恢复可验证。

## 23. 实施结论

正确的开发策略不是先把所有业务模块并行堆上去，而是：

```text
先修复测试基线
→ 建立 RBAC/ABAC 和公共契约
→ 接通多 Agent 闭环
→ 加入溯源和业务语义
→ 实现主动洞察
→ 并行建设驾驶舱、知识图谱、审批助手
→ 做性能与生产部署
→ 浏览器、越权、全量测试和答辩验收
```

这样升级后，项目的核心故事将从“做了一个 RAG 问答系统”变成：

> 在企业私有数据和权限边界内，通过多 Agent 协作完成可溯源分析、主动洞察、经营驾驶舱、知识关系推理和审批预审，并具备可观测、可评估、可部署的企业智能平台。
