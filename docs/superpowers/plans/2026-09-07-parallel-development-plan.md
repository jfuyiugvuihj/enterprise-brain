# 企业智脑并行开发实施计划

> **⚠️ 状态（2026-09-15 标注）**：**流程性计划，使命已完成**。它规定的 worktree 与检查点前提，后来由 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 的 Wave 1/2/3 实际派发方式取代。
> 不得据本文件判断功能完成度。它点名的主动洞察 / 驾驶舱 / 知识图谱 / 审批助手四项，现状见 `docs/frontend-workspace-audit-2026-09-14.md` §4.4 差距总表。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不互相覆盖代码、不重复设计接口、不同时压垮本地 Ollama 的前提下，并行完成企业智脑的多 Agent 协作闭环、答案溯源、主动洞察、业务语义层、驾驶舱、知识图谱和审批助手。

**Architecture:** 采用“一条主集成线 + 三条功能 Worktree + 一条测试 Review 线”的协作方式。主集成线负责公共数据契约、LangGraph 接入、冲突解决和最终验收；三个功能 Worktree 分别实现答案可信度、主动洞察、业务语义层；测试 Review 线只负责发现问题、补充测试和浏览器验收，不直接修改正在开发的核心文件。

**Tech Stack:** Git Worktree、Codex 多聊天/子 Agent、Python、FastAPI、LangGraph、Chroma、Pandas、APScheduler、Vue 3、Vite、现有 Ollama `qwen2.5:14b`。

## 当前状态

当前项目目录：

```text
C:\Users\fengx\PycharmProjects\企业智脑
```

当前工作区不是干净状态，已经存在大量历史改动、测试文件、知识库数据、图表文件和部署文件。并行开发前必须把当前状态固定成一个可恢复的检查点，不能让新 Worktree 直接基于不明确的临时状态。

当前已经完成的相关工作：

- 已确认 Ollama 模型 `qwen2.5:14b` 安装在 `C:\Users\fengx\.ollama\models`。
- 已将当前 Ollama 服务切换到正确模型目录。
- 已新增 Agent 模型请求失败时的离线降级包装。
- 已新增 `app/agents/contracts.py`、`app/agents/planner.py`、`app/agents/critic.py` 的基础实现。
- 已新增 `tests/test_agent_collaboration.py`，当前基础契约测试已通过。
- 已完成详细产品升级计划：
  `docs/superpowers/plans/2026-09-07-enterprise-intelligence-upgrade.md`

## 并行原则

- 同一时间只能有一个 Agent 修改公共契约和主流程文件。
- 每个功能 Worktree 只能修改自己负责的目录和对应测试。
- 未经主集成线程确认，不得修改 `app/agents/orchestrator.py`、`app/agents/state.py`、`app/api/v1/chat.py`。
- 端到端调用 `qwen2.5:14b` 的测试不能在多个 Worktree 中同时大量运行。
- 功能 Agent 先运行 Mock、纯函数和接口测试；主集成线最后统一运行真实 Ollama 测试。
- 所有 Worktree 必须使用独立分支，不允许两个 Worktree 同时 checkout 同一个分支。
- 所有跨模块数据必须依赖 `contracts.py` 中的结构化模型，不允许各模块自行定义重复字段。
- 不把 `.env`、Chroma 数据库、模型文件和生成图表作为跨 Worktree 手工复制的代码依赖。

## 分支和 Worktree 规划

### 主集成线程

```text
分支：codex/enterprise-intelligence-integration
用途：公共接口、LangGraph 接入、冲突解决、最终测试
```

负责：

- `app/agents/contracts.py`
- `app/agents/state.py`
- `app/agents/orchestrator.py`
- `app/agents/nodes.py`
- `app/api/v1/chat.py`
- `frontend/src/App.vue`
- 最终全量测试和浏览器测试

### Worktree A：答案溯源与可信度

```text
分支：codex/provenance-confidence
用途：证据定位、可信度评分、原文高亮、评估指标
```

负责：

- `app/rag/retrieval_pipeline.py`
- `app/rag/retriever.py`
- `app/rag/loader.py`
- `app/documents/catalog.py`
- `app/documents/preview.py`
- `app/quality/eval.py`
- 新增 `frontend/src/components/EvidencePanel.vue`
- 新增 `tests/test_answer_provenance.py`
- 新增 `tests/test_confidence_scoring.py`

禁止修改：

- `app/agents/orchestrator.py`
- `app/agents/state.py`
- `app/api/v1/chat.py`
- `frontend/src/components/ChatPanel.vue`

交付方式：

- 提供 `Evidence` 和可信度接口的使用说明。
- 如果需要主流程接入，只提交最小适配补丁或在说明中列出接口。
- 完成后运行不依赖 Ollama 的测试。

### Worktree B：主动洞察

```text
分支：codex/active-insights
用途：定时扫描、异常检测、洞察 API、洞察状态管理
```

负责：

- 新增 `app/insights/models.py`
- 新增 `app/insights/detector.py`
- 新增 `app/insights/service.py`
- 新增 `app/api/v1/insights.py`
- 修改 `app/scheduler/jobs.py`
- 修改 `app/api/v1/alerts.py`
- 新增 `frontend/src/components/InsightPanel.vue`
- 新增 `tests/test_insights.py`
- 新增 `tests/test_insight_scheduler.py`

禁止修改：

- `app/agents/orchestrator.py`
- `app/agents/state.py`
- `app/api/v1/chat.py`
- `frontend/src/components/ChatPanel.vue`

交付方式：

- 先用确定性规则实现异常发现。
- 模型只负责异常解释，不负责决定异常是否存在。
- 提供稳定的 `Insight` API 和测试夹具。
- 定时任务必须可手动触发，测试不能依赖等待 5 分钟。

### Worktree C：业务语义层

```text
分支：codex/business-semantics
用途：字段定义、指标口径、数据文件语义和冲突提醒
```

负责：

- 新增 `app/semantics/models.py`
- 新增 `app/semantics/catalog.py`
- 新增 `app/semantics/inference.py`
- 修改 `app/documents/catalog.py`
- 修改 `app/tools/excel.py`
- 新增 `frontend/src/components/SemanticDefinitionPanel.vue`
- 新增 `tests/test_business_semantics.py`

禁止修改：

- `app/agents/orchestrator.py`
- `app/agents/state.py`
- `app/api/v1/chat.py`
- `frontend/src/components/DataPanel.vue`

交付方式：

- 提供字段定义读取函数和指标口径匹配函数。
- 先实现本地 JSON/SQLite/内存兼容存储，不引入 Neo4j。
- 语义定义必须有 `draft`、`verified`、`deprecated` 状态。
- 未确认口径只能产生警告，不能作为确定事实。

### Worktree D：测试与 Review

```text
分支：codex/enterprise-intelligence-review
用途：独立测试、接口契约检查、浏览器验收和性能记录
```

负责：

- 新增或修改 `tests/test_upgrade_end_to_end.py`
- 新增 `tests/test_performance_guards.py`
- 新增浏览器测试记录
- 检查各 Worktree 的测试结果和接口兼容性

原则：

- 不直接重写功能代码。
- 发现问题后通过文件/行号和失败日志反馈给主集成线程。
- 如果必须修复测试夹具，可以只修改测试文件。

## 阶段 0：建立并行开发基线

### 主线程操作

- [ ] 检查当前分支和工作区状态。

```powershell
git status --short
git branch --show-current
git log -3 --oneline
```

- [ ] 记录当前全量测试结果。

```powershell
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' -m pytest -q
```

- [ ] 记录前端构建结果。

```powershell
Set-Location 'C:\Users\fengx\PycharmProjects\企业智脑\frontend'
npm run build
```

- [ ] 确认 Ollama 接口和模型。

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing |
  Select-Object -ExpandProperty Content
```

- [ ] 将当前改动保存为一个明确的基线提交或由用户确认的恢复点。

建议提交信息：

```text
chore: checkpoint current enterprise brain baseline
```

如果当前改动混杂了用户尚未确认的实验文件，不要自动提交全部内容；先把需要保留的范围列出来，再建立基线。

### 基线验收

- 后端测试结果可重复。
- 前端构建成功。
- Ollama 能看到 `qwen2.5:14b`。
- 当前主线程可以正常启动应用。
- 新 Worktree 创建后能够安装或复用依赖。

## 阶段 1：主线程完成公共契约

### 目标

在功能 Worktree 开始前，先固定跨模块接口，避免每个 Agent 设计不同数据结构。

### 文件

- 修改：`app/agents/contracts.py`
- 修改：`app/agents/state.py`
- 修改：`app/agents/planner.py`
- 修改：`app/agents/critic.py`
- 新增：`tests/test_agent_collaboration.py`

### 交付接口

必须固定以下模型：

```python
Evidence
MetricContext
AgentResult
ReviewResult
Insight
SemanticDefinition
```

主流程状态必须支持：

```python
plan
agent_results
review_result
retry_count
trace_events
```

### 测试

- [ ] 结果模型可以序列化为 JSON。
- [ ] 默认列表不会在不同实例之间共享。
- [ ] Planner 为每个任务生成唯一 `task_id`。
- [ ] Critic 能识别没有证据的结果。
- [ ] Critic 最多只允许一次重试。
- [ ] 不同模块可以读取相同的 `Evidence` 和 `MetricContext`。

完成后才允许启动 Worktree A、B、C 的功能开发。

## 阶段 2：并行启动三个功能 Worktree

三个 Worktree 只在公共契约完成后启动。

### A 线：答案溯源与可信度

工作顺序：

- [ ] 为 PDF、TXT、DOCX 保存 chunk、页码、段落和原文片段。
- [ ] 为 Excel/CSV 保存文件、工作表、列名和行范围。
- [ ] 将检索结果转换为 `Evidence`。
- [ ] 实现规则型可信度评分。
- [ ] 扩展 `eval.py` 统计证据覆盖率和无依据结论。
- [ ] 编写证据 API 单元测试。
- [ ] 编写权限过滤测试，确保普通用户看不到无权文档证据。
- [ ] 向主线程提交接口说明，不直接改聊天主流程。

验收：

```text
用户答案
  └─ 可信度：引用充分 82%
  └─ 来源：《差旅费报销制度.pdf》第3页
  └─ 点击后打开预览并高亮原文
```

### B 线：主动洞察

工作顺序：

- [ ] 实现基于环比、同比、阈值、部门差异和连续下降的确定性检测器。
- [ ] 实现 `Insight` 持久化和去重。
- [ ] 实现手动扫描 API。
- [ ] 将扫描任务接入现有 APScheduler。
- [ ] 增加已读、已确认、已解决状态。
- [ ] 生成洞察关联证据和建议字段。
- [ ] 编写不依赖模型的异常检测测试。
- [ ] 编写调度任务可手动触发测试。

验收：

```text
市场部差旅费环比增长 38%
等级：预警
原因：住宿费字段连续两个月超过制度标准
建议：打开差旅制度并进入审批预审
```

### C 线：业务语义层

工作顺序：

- [ ] 自动登记上传表格的字段名、类型和示例值。
- [ ] 支持字段别名和人工定义。
- [ ] 保存公式、单位、时间粒度、是否含税、是否含退款等口径。
- [ ] 实现字段匹配和冲突检测。
- [ ] 未确认定义显示警告。
- [ ] 编写字段注册和查询测试。
- [ ] 编写同名字段不同口径的冲突测试。

验收：

```text
本次分析口径：
销售额 = 已支付订单金额，不含退款
统计周期 = 自然月
数据来源 = 2026_business_analysis_test.xlsx / Sheet1
```

## 阶段 3：主线程接入并行结果

此阶段只能由主集成线程修改公共主流程文件。

### 目标

把三个功能的独立结果接入当前 LangGraph 和 SSE。

### 文件

- 修改：`app/agents/orchestrator.py`
- 修改：`app/agents/state.py`
- 修改：`app/agents/nodes.py`
- 修改：`app/api/v1/chat.py`
- 修改：`frontend/src/components/ChatPanel.vue`
- 新增：`frontend/src/components/AgentTrace.vue`
- 新增：`frontend/src/components/EvidencePanel.vue`

### 接入顺序

- [ ] 将现有 `worker_results` 兼容转换为 `AgentResult`。
- [ ] Planner 先生成任务，不改变现有简单问题的快速路径。
- [ ] 独立任务使用现有 LangGraph `Send` 并行执行。
- [ ] Worker 完成后写入 `agent_results`。
- [ ] Critic 审查全部结果。
- [ ] 审查失败时最多自动补偿一次。
- [ ] Synthesis 使用审查后的结果汇总。
- [ ] SSE 增加 `plan`、`agent`、`review`、`evidence`、`confidence` 事件。
- [ ] 前端显示任务规划、并行 Worker、审查和汇总状态。
- [ ] 旧前端仍能兼容没有新字段的 SSE 事件。

### 不能并行修改的文件

以下文件必须在主线程串行修改：

```text
app/agents/orchestrator.py
app/agents/state.py
app/api/v1/chat.py
frontend/src/components/ChatPanel.vue
```

## 阶段 4：驾驶舱、知识图谱和审批助手

这三个模块不再拆给多个 Agent 同时修改，因为它们都依赖前面三条线的接口。

### 驾驶舱

主线程新增或修改：

- `app/api/v1/dashboard.py`
- `frontend/src/components/DashboardPanel.vue`
- `frontend/src/components/MetricCard.vue`
- `frontend/src/components/InsightCard.vue`

交付：

- 指标卡片。
- 趋势图。
- 部门对比。
- 主动洞察。
- 证据跳转。
- 快捷提问。

### 知识图谱

主线程新增：

- `app/knowledge_graph/models.py`
- `app/knowledge_graph/extractor.py`
- `app/knowledge_graph/store.py`
- `app/api/v1/knowledge_graph.py`
- `frontend/src/components/KnowledgeGraphPanel.vue`

交付：

- 文档、制度、部门、费用、审批节点实体。
- 规则、责任和审批关系。
- 候选关系必须有证据。
- 管理员可以确认或拒绝候选关系。

### 审批助手

主线程新增：

- `app/approval/models.py`
- `app/approval/rules.py`
- `app/approval/service.py`
- `app/api/v1/approval.py`
- `frontend/src/components/ApprovalPanel.vue`

交付：

- 事项字段校验。
- 制度匹配。
- 超额计算。
- 责任方判断。
- 审批路径。
- 风险等级。
- 审批说明草稿。

第一版只生成预审建议和审批草稿，不直接提交真实财务审批。

## 阶段 5：并行 Review 和浏览器验收

### Review Agent A：后端质量

检查：

- LangGraph 是否存在重复派发。
- Critic 是否可能无限重试。
- Agent 失败是否导致 SSE 永久等待。
- 证据是否绕过 RBAC。
- 同一洞察是否重复生成。

### Review Agent B：前端视觉

使用浏览器验证：

- AgentTrace 步骤是否实时变化。
- 证据点击是否打开正确文档。
- 可信度标记是否明显。
- 主动洞察是否能刷新后保留。
- 驾驶舱是否能适配移动端。
- 失败状态是否有可理解的提示。

### Review Agent C：性能

检查：

- 是否每次问答重复调用 embedding。
- 是否同时启动多个 `qwen2.5:14b` 推理。
- 是否将长文档完整塞入 Prompt。
- 是否有无界重试。
- 是否把大表格全部返回前端。

## 合并策略

### 合并顺序

```text
主线程公共契约
  ↓
Worktree A：答案溯源
  ↓
Worktree C：业务语义层
  ↓
Worktree B：主动洞察
  ↓
主线程 LangGraph/SSE 接入
  ↓
驾驶舱、知识图谱、审批助手
  ↓
Review Worktree 验收
```

虽然 A、B、C 可以并行编写，但合并时建议按上面的顺序，以减少接口冲突：

- 答案溯源定义 `Evidence`。
- 业务语义层定义 `MetricContext`。
- 主动洞察同时依赖 `Evidence` 和 `MetricContext`。

### 每条分支合并前必须提供

- 分支名。
- 修改文件列表。
- 新增接口列表。
- 单元测试命令和结果。
- 已知警告。
- 是否依赖 Ollama、PostgreSQL、Chroma 或前端服务。
- 是否需要主线程额外适配。

### 主线程合并后必须运行

```powershell
Set-Location 'C:\Users\fengx\PycharmProjects\企业智脑'
& '.venv\Scripts\python.exe' -m pytest tests/test_agent_collaboration.py -q
& '.venv\Scripts\python.exe' -m pytest tests/test_answer_provenance.py tests/test_business_semantics.py tests/test_insights.py -q
& '.venv\Scripts\python.exe' -m pytest -q
Set-Location 'frontend'
npm run build
```

## Codex 操作方式

### 建议创建的聊天

```text
聊天 1：主集成线
聊天 2：答案溯源 Worktree
聊天 3：主动洞察 Worktree
聊天 4：业务语义 Worktree
聊天 5：测试 Review Worktree
```

### 每个功能聊天的固定提示词

#### 答案溯源聊天

```text
你在 Worktree codex/provenance-confidence 中工作。
只负责答案溯源、可信度评分、原文定位和相关测试。
允许修改计划中列出的 provenance 文件和测试文件。
不要修改 app/agents/orchestrator.py、app/agents/state.py、app/api/v1/chat.py、
frontend/src/components/ChatPanel.vue。
先阅读 app/agents/contracts.py 和现有检索管线。
先写失败测试，再实现。
完成后报告修改文件、测试命令、测试结果和主线程需要的接入接口。
```

#### 主动洞察聊天

```text
你在 Worktree codex/active-insights 中工作。
只负责主动洞察模型、异常检测、调度、洞察 API 和对应测试。
异常判定必须使用确定性规则，模型只负责解释。
不要修改 app/agents/orchestrator.py、app/agents/state.py、app/api/v1/chat.py。
先写失败测试，再实现。
完成后报告 API 契约、去重规则、权限规则和测试结果。
```

#### 业务语义聊天

```text
你在 Worktree codex/business-semantics 中工作。
只负责字段定义、指标口径、别名、冲突检测和对应测试。
不要修改 app/agents/orchestrator.py、app/agents/state.py、
app/api/v1/chat.py、frontend/src/components/DataPanel.vue。
先写失败测试，再实现。
完成后报告 SemanticDefinition 接口、存储方式和测试结果。
```

#### Review 聊天

```text
你在独立 Review Worktree 中工作。
不要重写功能代码。
检查答案溯源、主动洞察和业务语义层的接口兼容性、权限、性能和测试缺口。
先运行相关测试，再输出按严重程度排序的问题、文件路径和行号。
```

## 风险控制

### 当前未提交改动

不要直接从一个不明确的脏工作区创建多个 Worktree。先建立可恢复检查点，或者在 Codex 创建 Worktree 时明确选择当前分支并确认未提交修改会被带入。

### `.env` 和本地数据

Worktree 默认只包含 Git 已跟踪文件。若测试需要 `.env`，使用项目根目录的 `.worktreeinclude` 明确复制：

```text
.env
```

不得把真实密钥提交到 Git。

### Ollama 资源

- 只保留一个 Ollama 服务。
- 不要在每个 Worktree 启动一份 Ollama。
- 功能 Worktree 默认运行 Mock 测试。
- 主线程串行运行真实模型端到端测试。

### 冲突解决

如果两个分支都需要修改公共文件：

1. 功能分支只提交独立模块。
2. 主线程统一接入。
3. 不让两个 Agent 同时解决同一个冲突。
4. 合并后立即运行相关测试。

## 最终验收标准

- 主线程和各 Worktree 的职责清晰。
- 三条功能线都能独立测试。
- 公共契约只有一份。
- 多 Agent 协作链路不会重复派发或无限重试。
- 答案能显示证据和可信度。
- 系统能主动发现至少一种异常。
- 数据分析能显示业务口径。
- 驾驶舱、知识图谱和审批助手能完成一条完整演示链路。
- 全量后端测试通过。
- 前端构建通过。
- 至少完成一次真实浏览器验收。

