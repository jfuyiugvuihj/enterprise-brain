# 企业智脑智能化升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有企业智脑的知识库、数据分析、图表、告警和多 Agent 基础上，构建一个具备多 Agent 协作闭环、答案溯源与可信度标注、主动洞察和业务语义层的企业智能决策与审批平台。

**Architecture:** 保留现有 Supervisor + Doc/Data/Chart/Export Agent 架构，增加 Planner Agent 负责任务拆解，增加 Critic Agent 负责证据和结果审查，并统一使用结构化的 `AgentResult` 传递结论、来源、指标口径和置信度。前端以“可解释执行链路”为主线，展示 Agent 执行状态、证据引用、可信度、异常洞察和审批建议。

**Tech Stack:** Python 3.11/3.14 兼容、FastAPI、LangGraph、LangChain、Chroma、Pandas、APScheduler、PostgreSQL/内存降级、Vue 3、Vite、现有 Chart/Export 工具。

## Global Constraints

- 任何新功能都必须先写失败测试，再实现最小代码，再运行单元测试和接口测试。
- 第 0 阶段必须先确认现有测试基线；基线失败时不得继续叠加业务功能。
- 保留现有知识库上传、预览、下载、删除、RBAC、数据文件列表和图表生成行为。
- 不把外部云端模型作为正式架构依赖；模型通过现有 `app/common/model_config.py` 配置，默认支持本地私有模型。
- 不在代码中写死 API Key、账号、密码或用户数据。
- 普通用户不能看到管理员删除能力；所有新接口继续执行现有角色和部门过滤。
- 文档证据必须经过权限过滤后才能展示，不能因为引用功能绕过 RBAC。
- 任何最终结论都必须区分“有证据支持”“证据不足”和“推测”，禁止把推测显示成确定事实。
- 当前工作区存在大量历史未提交改动，不得回滚或覆盖与本计划无关的用户改动。
- 本计划不一次性引入 Neo4j 等重型基础设施；第一版业务语义层和知识图谱使用 PostgreSQL/JSON 或本地持久化实现，保留未来替换接口。

## 质量门禁

当前仓库在 2026-09-07 的已验证基线为：

```text
157 passed
```

该结果来自当前项目虚拟环境：

```powershell
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' -m pytest -q
```

如果开发者本地运行结果不是 `157 passed`，先执行以下步骤：

1. 保存完整失败输出和失败测试名称。
2. 区分环境依赖问题、历史回归问题和本次代码问题。
3. 先修复阻断启动、路由、认证、知识库检索和数据分析的失败。
4. 在基线恢复为全绿前，不开始实现新的业务闭环。

弃用警告可以单独登记，不得把警告误判成测试失败；但新增代码不得继续扩大已知弃用用法。

## 产品范围

### 必须实现

1. 多 Agent 协作闭环：
   - Planner 任务拆解。
   - Doc/Data/Chart/Export Agent 并行执行。
   - Critic 证据、数字和逻辑审查。
   - 失败或冲突时自动补检索/重算一次。
   - Synthesis 汇总最终答案。
2. 答案溯源和可信度标注：
   - 文档回答显示文件名、页码或段落定位。
   - 表格回答显示文件名、工作表、列名和筛选口径。
   - 引用可展开，尽可能高亮原文。
   - 显示“引用充分”“引用不足”“推测”三档可信度。
3. 主动洞察：
   - 定时扫描已上传 Excel/CSV。
   - 自动发现趋势变化、异常值、超标指标和部门差异。
   - 自动生成摘要、图表和相关制度引用。
   - 前端显示未读洞察，支持查看、确认和标记已处理。
4. 业务语义层：
   - 维护字段含义、单位、时间粒度、计算方式和数据来源。
   - 分析前自动注入指标口径。
   - 发现用户问题与数据口径冲突时主动提醒。
5. 三个业务闭环：
   - 智能经营驾驶舱。
   - 企业知识图谱轻量版。
   - 智能审批助手。

### 第一版明确不做

- 不实现复杂的全自动审批付款。
- 不允许 Agent 直接修改企业原始数据。
- 不把所有文档自动转换成完全可信的知识图谱关系。
- 不实现无限轮 Agent 辩论；最多自动审查和补偿一次。
- 不引入必须联网才能运行的外部 SaaS。
- 不在没有权限判断的情况下展示跨部门敏感数据。

## 核心数据契约

### AgentResult

新增统一结果模型，建议放在 `app/agents/contracts.py`：

```python
class Evidence(BaseModel):
    source_type: Literal["document", "table", "chart", "rule", "inference"]
    source_name: str
    locator: str
    excerpt: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = {}


class MetricContext(BaseModel):
    metric_name: str
    definition: str
    formula: str = ""
    unit: str = ""
    time_granularity: str = ""
    source_file: str = ""
    warnings: list[str] = []


class AgentResult(BaseModel):
    worker: str
    status: Literal["success", "partial", "failed"]
    answer: str
    evidence: list[Evidence] = []
    metrics: list[MetricContext] = []
    confidence: float = 0.0
    confidence_label: Literal["引用充分", "引用不足", "推测"] = "引用不足"
    warnings: list[str] = []
    artifacts: list[str] = []
    duration_ms: int = 0
```

实际实现时要避免使用可变默认值，使用 `Field(default_factory=list)`。

### ReviewResult

Critic Agent 输出：

```python
class ReviewResult(BaseModel):
    passed: bool
    issues: list[str]
    missing_evidence: list[str]
    conflicting_evidence: list[str]
    recommended_action: Literal["accept", "retry_retrieval", "retry_analysis", "answer_with_warning"]
    confidence: float
```

### Insight

主动洞察统一使用：

```python
class Insight(BaseModel):
    id: str
    title: str
    severity: Literal["info", "warning", "critical"]
    summary: str
    metric: str
    current_value: float | None
    previous_value: float | None
    change_rate: float | None
    evidence: list[Evidence]
    recommended_action: str
    status: Literal["unread", "acknowledged", "resolved"] = "unread"
    created_at: str
```

## 阶段 0：锁定测试基线

### 目标

确认当前版本能启动、认证、上传和检索，并为后续升级建立可重复的质量门禁。

### 文件

- 检查：`tests/`
- 检查：`app/main.py`
- 检查：`app/api/v1/chat.py`
- 检查：`app/agents/orchestrator.py`
- 检查：`frontend/src/components/ChatPanel.vue`
- 新增：`tests/test_upgrade_baseline.py`

### 步骤

- [ ] 运行 `pytest -q` 并保存总数、失败项和耗时。
- [ ] 运行 `pytest tests/test_auth.py tests/test_orchestrator.py tests/test_tools.py -q`。
- [ ] 运行前端构建命令，确认 Vite 编译通过。
- [ ] 使用浏览器验证登录、上传文档、问答、数据文件选择、图表显示。
- [ ] 为当前关键路径增加最小冒烟测试：

```python
def test_existing_chat_route_still_has_doc_data_chart_export_nodes():
    from app.agents.orchestrator import multi_agent_graph

    nodes = set(multi_agent_graph.get_graph().nodes.keys())
    assert {"doc", "data", "chart", "export"} <= nodes
```

- [ ] 只有基线通过后，才进入阶段 1。

### 验收标准

- 后端测试全绿。
- 前端构建成功。
- 现有上传、检索和数据分析功能没有行为回归。
- 所有失败项有记录，不允许静默跳过。

## 阶段 1：多 Agent 协作闭环

### 目标

将现有“Supervisor 选择 Worker”升级为“规划、并行执行、审查、纠错、汇总”的有限闭环。

### 文件

- 新增：`app/agents/contracts.py`
- 修改：`app/agents/state.py`
- 修改：`app/agents/orchestrator.py`
- 修改：`app/agents/nodes.py`
- 修改：`app/api/v1/chat.py`
- 修改：`frontend/src/components/ChatPanel.vue`
- 新增：`frontend/src/components/AgentTrace.vue`
- 新增：`tests/test_agent_collaboration.py`
- 新增：`tests/test_agent_contracts.py`

### 状态扩展

在 `AgentState` 中增加：

```python
plan: list[dict]
agent_results: dict[str, AgentResult]
review_result: ReviewResult | None
retry_count: int
trace_events: list[dict]
```

### Planner 行为

Planner 只负责结构化拆解，不执行具体数据操作：

- 判断问题是文档、数据、图表、导出、审批还是组合任务。
- 给每个子任务生成唯一 `task_id`。
- 标注依赖关系；独立任务并行执行。
- 组合问题必须明确数据文件和文档范围。
- 任务拆解失败时回退到现有 Supervisor 路由。

### Worker 行为

现有 Worker 保留职责，但返回 `AgentResult`：

- `doc`：返回文档片段、文件名、页码/段落定位和检索分数。
- `data`：返回分析结论、文件名、工作表、列名、筛选条件和指标口径。
- `chart`：返回图表路径和生成数据来源。
- `export`：返回报告路径及报告包含的证据列表。

### Critic 行为

Critic 不重新回答原问题，专门检查：

- 最终结论是否有证据。
- 引用是否支持结论。
- 数据数字是否来自实际表格。
- 多个 Worker 是否出现冲突。
- 结论是否混用了不同时间范围或不同口径。
- 回答是否超出用户权限。

当审查失败时只允许一次补偿：

```text
retry_retrieval → 重新检索 Doc Agent
retry_analysis → 重新执行 Data Agent
answer_with_warning → 保留结果，但明确标注证据不足
```

### 前端展示

在 `ChatPanel.vue` 中将现有 Agent 步骤升级为：

```text
任务规划
  ├─ 搜索知识库      已完成  1.2s
  ├─ 分析经营数据    已完成  2.8s
  ├─ 生成图表        已完成  1.1s
  ├─ 结果审查        已完成  0.7s
  └─ 汇总回答        已完成  0.5s
```

每个步骤允许展开查看输入摘要、输出摘要、耗时和状态，但不能显示 API Key 或内部系统提示词。

### 测试

- [ ] Planner 能把组合问题拆成多个任务。
- [ ] 独立 Worker 能并行执行。
- [ ] Worker 失败时不会导致整个回答异常退出。
- [ ] Critic 能识别没有来源的回答。
- [ ] Critic 发现冲突时只触发一次重试。
- [ ] 重试后仍失败时，最终回答显示警告。
- [ ] 多轮对话不会把上一轮 Worker 结果错误带入当前轮。
- [ ] 前端能显示步骤开始、进行中、完成和失败状态。

## 阶段 2：答案溯源与可信度标注

### 目标

让用户能知道每条结论来自哪里、为什么可信、哪些内容只是推测。

### 文件

- 修改：`app/rag/retrieval_pipeline.py`
- 修改：`app/rag/retriever.py`
- 修改：`app/rag/loader.py`
- 修改：`app/documents/catalog.py`
- 修改：`app/documents/preview.py`
- 修改：`app/agents/tools.py`
- 修改：`app/quality/eval.py`
- 修改：`app/api/v1/chat.py`
- 修改：`app/api/v1/data.py`
- 修改：`frontend/src/components/ChatPanel.vue`
- 新增：`frontend/src/components/EvidencePanel.vue`
- 新增：`tests/test_answer_provenance.py`
- 新增：`tests/test_confidence_scoring.py`

### 文档定位

解析文档时保存：

- `document_id`
- 原始文件名
- 页码
- 段落序号
- chunk_id
- 原文片段
- chunk 起止字符位置

PDF 至少支持页码和片段；TXT/DOCX 支持段落或 chunk 定位；XLSX/CSV 支持文件名、工作表、列名、行范围。

### 可信度规则

第一版使用可解释的规则评分，不让模型凭感觉输出分数：

- 有至少一个权限可见的直接引用：基础分 0.45。
- 两个以上相互一致的引用：加 0.2。
- 引用与结论的关键词/实体匹配：加 0.15。
- 有明确数据计算过程：加 0.15。
- Critic 通过：加 0.1。
- 存在冲突、口径缺失或没有引用：扣分。

显示规则：

- `>= 0.75`：引用充分。
- `0.45 - 0.74`：引用不足。
- `< 0.45`：推测。

分数必须同时展示原因，例如：

```text
可信度：引用充分 82%
依据：2 条制度原文，1 个表格计算结果，Critic 审查通过
```

### 可点击高亮

点击引用时：

- 文档：打开现有预览组件并跳转到页码/段落，显示高亮片段。
- 表格：打开数据预览并高亮工作表、列和行范围。
- 图表：显示图表生成数据和对应字段。

### eval.py 升级

在现有 `evaluate_golden_set` 基础上增加：

```python
def evaluate_provenance(answer: dict) -> dict:
    return {
        "has_evidence": bool(answer.get("evidence")),
        "evidence_coverage": float,
        "confidence_label": str,
        "unsupported_claims": list[str],
    }
```

测试不能只比较字符串答案，还要检查：

- 是否有引用。
- 引用是否属于用户可见文件。
- 引用定位是否存在。
- 低证据答案是否标注推测。

## 阶段 3：业务语义层

### 目标

统一企业数据指标口径，防止“同一个字段不同理解”造成错误分析。

### 文件

- 新增：`app/semantics/models.py`
- 新增：`app/semantics/catalog.py`
- 新增：`app/semantics/inference.py`
- 修改：`app/documents/catalog.py`
- 修改：`app/tools/excel.py`
- 修改：`app/agents/tools.py`
- 修改：`app/agents/contracts.py`
- 修改：`app/api/v1/data.py`
- 新增：`frontend/src/components/SemanticDefinitionPanel.vue`
- 新增：`tests/test_business_semantics.py`

### 语义定义

每个字段至少包含：

```python
class SemanticDefinition(BaseModel):
    field_name: str
    display_name: str
    definition: str
    formula: str = ""
    unit: str = ""
    time_granularity: str = ""
    include_tax: bool | None = None
    include_refund: bool | None = None
    source_files: list[str] = []
    aliases: list[str] = []
    owner_department: str = ""
    status: Literal["draft", "verified", "deprecated"] = "draft"
```

### 口径学习和确认

- 首次上传数据文件时，自动提取字段名、示例值、类型和可能别名。
- 对“GMV 是否含退款”“销售额是否含税”等关键问题生成待确认定义。
- 用户或管理员确认后进入 `verified` 状态。
- 未确认的定义只能作为提示，不得伪装成正式口径。
- 同名字段来自不同文件且定义冲突时，分析前必须警告。

### 分析注入

Data Agent 调用 `analyze_data` 前读取匹配的 `SemanticDefinition`，将以下内容放入 `MetricContext`：

- 使用的字段。
- 采用的定义。
- 公式。
- 时间范围。
- 排除或包含的记录。

最终答案必须显示：

```text
本次分析口径：销售额 = 已支付订单金额，不含退款，统计周期为自然月。
```

## 阶段 4：主动洞察

### 目标

让系统主动扫描数据文件并生成异常、趋势和行动建议，不再完全依赖用户提问。

### 文件

- 新增：`app/insights/models.py`
- 新增：`app/insights/detector.py`
- 新增：`app/insights/service.py`
- 新增：`app/api/v1/insights.py`
- 修改：`app/scheduler/jobs.py`
- 修改：`app/api/v1/alerts.py`
- 修改：`app/agents/tools.py`
- 修改：`app/tools/visualize.py`
- 修改：`app/main.py`
- 新增：`frontend/src/components/InsightPanel.vue`
- 新增：`tests/test_insights.py`
- 新增：`tests/test_insight_scheduler.py`

### 检测规则

第一版实现确定性规则，不让模型单独决定异常：

- 环比/同比变化超过阈值。
- 数值超过业务语义层定义的标准。
- 部门之间差异超过阈值。
- 连续多个周期下降。
- 缺失值或字段质量异常。

模型只负责：

- 解释异常可能原因。
- 从知识库寻找相关制度。
- 生成建议。

### API

建议提供：

```text
GET  /api/v1/insights
GET  /api/v1/insights/{insight_id}
POST /api/v1/insights/{insight_id}/ack
POST /api/v1/insights/{insight_id}/resolve
POST /api/v1/insights/scan
```

所有列表和详情接口都必须执行用户身份和部门过滤。

### 调度

复用现有 `APScheduler`：

- 数据文件上传完成后触发一次轻量扫描。
- 现有 5 分钟任务中增加去重后的洞察扫描。
- 同一文件、同一指标、同一周期不得重复生成相同洞察。
- 失败任务记录日志并保留下一次重试机会。

## 阶段 5：智能经营驾驶舱

### 目标

把主动洞察、业务语义、图表和知识库组合成一个可展示的经营决策页面。

### 文件

- 新增：`app/api/v1/dashboard.py`
- 修改：`app/api/v1/data.py`
- 修改：`app/tools/visualize.py`
- 修改：`frontend/src/App.vue`
- 新增：`frontend/src/components/DashboardPanel.vue`
- 新增：`frontend/src/components/MetricCard.vue`
- 新增：`frontend/src/components/InsightCard.vue`
- 新增：`tests/test_dashboard.py`

### 页面区域

1. 核心指标卡片：当前值、变化率、口径。
2. 趋势图：按时间粒度展示。
3. 部门对比：排名和差异。
4. 异常列表：严重等级、证据、建议。
5. 关联制度：一键打开文档依据。
6. 快捷提问：携带当前文件、指标和洞察上下文进入聊天。

### 验收案例

使用 `data/2026_business_analysis_test.xlsx`：

- 页面能够展示至少 3 个指标。
- 能识别一个人为构造的异常。
- 能生成趋势图。
- 能从异常跳转到证据和业务口径。
- 刷新页面后洞察状态保持。

## 阶段 6：轻量企业知识图谱

### 目标

让制度、部门、费用、角色和审批关系可视化，并服务于问答和审批判断。

### 文件

- 新增：`app/knowledge_graph/models.py`
- 新增：`app/knowledge_graph/extractor.py`
- 新增：`app/knowledge_graph/store.py`
- 新增：`app/api/v1/knowledge_graph.py`
- 修改：`app/agents/tools.py`
- 修改：`app/agents/orchestrator.py`
- 新增：`frontend/src/components/KnowledgeGraphPanel.vue`
- 新增：`tests/test_knowledge_graph.py`

### 第一版实体和关系

实体：

- 文档、制度、部门、员工角色、费用类型、指标、审批节点。

关系：

- 制度规定费用标准。
- 超标费用由角色承担。
- 角色属于部门。
- 部门执行制度。
- 费用需要审批节点。
- 指标来自数据字段。

### 可靠性边界

- 自动抽取的关系初始状态为 `candidate`。
- 只有存在原文证据才能进入图谱。
- 管理员可确认、拒绝或修正关系。
- 图谱问答必须返回关系来源。

## 阶段 7：智能审批助手

### 目标

把业务语义、知识图谱、文档引用和数据分析组合成业务办理闭环。

### 文件

- 新增：`app/approval/models.py`
- 新增：`app/approval/service.py`
- 新增：`app/approval/rules.py`
- 新增：`app/api/v1/approval.py`
- 修改：`app/agents/orchestrator.py`
- 修改：`app/agents/tools.py`
- 修改：`frontend/src/App.vue`
- 新增：`frontend/src/components/ApprovalPanel.vue`
- 新增：`tests/test_approval_assistant.py`

### 审批预审流程

```text
用户提交事项
  ↓
字段校验
  ↓
业务语义匹配
  ↓
知识库/图谱检索制度
  ↓
规则计算是否超标
  ↓
判断责任方和审批节点
  ↓
Critic 检查证据
  ↓
生成预审结论和审批说明
```

### 预审输出

- 事项摘要。
- 使用的制度。
- 允许标准。
- 实际金额。
- 超出金额。
- 承担方。
- 审批路径。
- 风险等级。
- 证据和可信度。
- 用户可编辑的审批说明。

第一版只生成预审建议和审批单草稿，不直接提交真实财务审批。

## 阶段 8：质量、性能和前端体验

### 目标

确保新功能不是只在演示数据上工作，且不会明显加重本地模型负担。

### 文件

- 新增：`tests/test_upgrade_end_to_end.py`
- 新增：`tests/test_performance_guards.py`
- 修改：`frontend/src/components/ChatPanel.vue`
- 修改：`frontend/src/components/DashboardPanel.vue`
- 修改：`app/common/model_handler.py`
- 修改：`app/common/cache.py`

### 性能策略

- Planner 只使用短上下文和结构化输出。
- Doc/Data/Chart 独立任务并行执行。
- Critic 优先使用规则检查，必要时才调用模型。
- 语义定义、文档定位和洞察结果缓存。
- 同一问题、同一文件和同一版本避免重复计算。
- 前端显示每个 Agent 的耗时，识别卡顿来源。
- 对长任务提供取消和超时状态，不无限等待。

### 浏览器验收

至少完成以下流程：

1. 登录普通用户。
2. 上传一个制度文档和一个数据文件。
3. 打开驾驶舱。
4. 查看自动洞察。
5. 点击异常进入证据。
6. 从证据跳转原文高亮。
7. 发起组合问题。
8. 查看 Planner、并行 Agent、Critic 和汇总步骤。
9. 打开知识图谱关系。
10. 使用审批助手生成预审结果。
11. 刷新页面，确认结果仍然存在。
12. 使用管理员确认或修正候选关系。

## 最终验收标准

### 功能

- 多 Agent 组合问题可拆解、并行执行、审查和汇总。
- 任何制度结论都有来源或明确标注证据不足。
- 表格分析显示文件、工作表、字段和口径。
- 主动洞察能自动发现至少一种变化异常。
- 驾驶舱能展示指标、趋势、异常和建议。
- 知识图谱能展示制度、部门、费用和审批关系。
- 审批助手能判断标准、超额、责任方和审批路径。

### 质量

- 全量后端测试通过。
- 前端生产构建通过。
- 新增接口有认证和 RBAC 测试。
- 普通用户不能读取不属于自己的证据。
- 低证据回答不能显示为高可信度。
- 失败 Agent 不会让整个 SSE 流无响应。
- 至少一条真实浏览器流程通过。

### 答辩展示

准备一个固定演示问题：

> 分析市场部本月差旅费用，找出超出住宿标准的项目，结合公司制度判断责任方，展示依据、可信度、关联关系，并生成审批建议和图表。

演示时重点展示：

- Agent 协作链路。
- 证据和原文高亮。
- 业务口径。
- 主动洞察。
- 知识图谱关系。
- 审批预审结果。

## 开发顺序结论

正确顺序不是“先把所有测试修完再想计划”，也不是“测试失败仍然直接堆新功能”，而是：

```text
确认当前基线
  ↓
写并评审本计划
  ↓
修复基线阻断问题
  ↓
阶段 1：多 Agent 协作闭环
  ↓
阶段 2：答案溯源和可信度
  ↓
阶段 3：业务语义层
  ↓
阶段 4：主动洞察
  ↓
阶段 5-7：驾驶舱、知识图谱、审批助手
  ↓
全量测试 + 浏览器验收 + 答辩演示
```

每个阶段都必须保持可启动、可测试、可演示，不能等所有模块完成后才第一次联调。
