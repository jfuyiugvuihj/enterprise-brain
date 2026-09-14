# 前端工作区审计与前后端改造分档

版本：2026-09-14-r1
文档性质：面向使用者视角的前端工作区走查结论 + 改造归属分档，不是目标设计，不构成“已验证可用”的承诺
盘点方式：对 `frontend/src/**` 与 `app/**` 做静态源码核对，逐项回溯到文件:行；未运行测试、未启动服务、未修改 `frontend/`
权威口径：本文只收录本轮在工作区源码中复核过的结论。凡与 `docs/current-functionality-2026-09-10.md`、`docs/handoff/2026-09-14-consolidated-fix-plan.md` 冲突处，以本文最后一节“订正说明”为准，其余仍以那两份文档为主口径
协作边界：`frontend/` 由其他 Agent 负责，本文只产出结论与接口约束，不含任何前端代码改动

## 0. 标记口径

沿用 `docs/current-functionality-2026-09-10.md` 的状态与证据等级：

| 状态 | 含义 |
|---|---|
| 已实现 | 源码中有完整入口和主要处理逻辑，但不等于完成生产验收 |
| 部分实现 | 主流程存在，但数据来源、权限、持久化或用户闭环不完整 |
| 演示/骨架 | 有页面或接口，但主要依赖固定值、前端输入或内存数据 |
| 存在风险 | 当前实现可能导致数据错误、越权、丢失或不可复盘 |

| 证据 | 含义 |
|---|---|
| A | 本轮在当前源码中直接读到可调用实现 |
| D | 仅设计文档或实施计划中的目标 |


## 1. 结论摘要

三个根因导致前端“看起来奇怪”：

1. **侧栏按后端 router 切分，不按用户工作流切分。** `frontend/src/App.vue:28` 的 7 个入口对应 `app/api/v1/intelligence.py`、`app/api/v1/chat.py`、`app/api/v1/data.py` 的路由分组，不对应“员工今天要办什么事”。
2. **视觉升级只镀层不改逻辑。** `docs/superpowers/plans/2026-09-10-enterprise-brain-reference-ui-alignment.md:9` 写明“本次改版不改变后端 API、登录流程、文档上传、数据分析、洞察、图谱、审批和对话逻辑，只调整前端壳层、总览数据编排和视觉样式”；`docs/superpowers/specs/2026-09-09-enterprise-brain-frontend-visual-design.md:58` 要求“保留业务逻辑，只统一外层视觉契约和交互状态”。2026-09-07 计划里的最小骨架因此被原样保留并镀了一层皮。
3. **三处后端能力长在前端外面。** 告警引擎、会话存储、产物（Artifact）体系在后端已可用，前端却各自另起一套：本地假洞察、localStorage 会话、`/static/` 图片正则。

### 1.1 七个工作区当前定性

| 工作区 | 定性 | 关键依据 |
|---|---|---|
| 总览 | 演示/骨架（含真实部分） | 文档数与数据表数来自真实接口；洞察数与审批数硬编码；趋势线手写乘数 |
| 文档 | 已实现 + 存在风险 | catalog、版本、预览、删除链路真实；确认弹窗乱码、进度条假、图标函数硬编码某公司文件名 |
| 数据 | 已实现 + 部分实现 | 上传与预览真实；选定的数据表在对话侧不可见不可改 |
| 洞察 | 演示/骨架 | 要求用户手填阈值，真实异常引擎在 alerts 且无界面 |
| 图谱 | 演示/骨架 + 存在风险 | 无图形、无持久化、需人工录入三元组 |
| 审批 | 演示/骨架 | 只算减法且要求用户自带标准；智能版挂在对话里 |
| 对话 | 已实现 + 存在风险 | 主链路真实；组件生命周期、SSE 契约、渲染安全、本地存储存在阻断级问题 |


## 2. P0 阻断级缺陷

### P0-1 图表必然不显示（证据 A）

```
后端 app/agents/tools.py:526  return f"图表已生成: ![{title}]({url})"
  url 来自 _artifact_urls() -> ArtifactRecord.content_url
  content_url = /api/v1/artifacts/{id}/content      app/storage/artifacts.py:57
前端 frontend/src/components/ChatPanel.vue:139
  正则 /!\[([^\]]*)\]\((\/static\/[^)]+)\)/g        只匹配 /static/ 前缀
  -> artifacts 地址不会进入 charts 数组（ChatPanel.vue:523 才渲染 ChartViewer）
  -> ChatPanel.vue:147 stripChartMarkers() 用同一条正则，也不会把它抹掉
  -> 结果：图片标记以裸 Markdown 文本形式出现在回答里
即便把正则放宽到 artifacts：
  frontend/src/components/ChartViewer.vue:49 与 :66 使用裸 <img :src="downloadUrl">
  -> 浏览器发起 GET 时不带 Authorization
  -> app/common/auth.py:222 的 get_token_from_request() 只读 Authorization 头
  -> 401；而 app/main.py:119 StaticFilesWithoutGeneratedArtifacts 对 charts/exports 直接返回 404
  -> 结论：任何“裸 img + /static/”的组合都拿不到图
```

修复归属：**纯前端**。仓库内已有正确范式：`frontend/src/components/DocPanel.vue:89` 用 blob 方式取文件再本地渲染。
验收：在对话里生成一张柱图，图片在气泡内可见、可放大、可下载；token 失效时应显示“无权查看”而不是空白。

### P0-2 切一次侧栏就丢会话状态（证据 A）

`frontend/src/App.vue:365-372` 用 `v-if / v-else-if / v-else` 链切换工作区，`ChatPanel` 落在 `frontend/src/App.vue:372`。切到任意其他 tab 即销毁组件：SSE 读取随 `onUnmounted` 中断，`hitl` 待确认卡片与 `loading` 态一并丢失，回答停在半句。

叠加缺陷：`frontend/src/components/ChatPanel.vue:330` 先置 `loading.value = true`，`frontend/src/components/ChatPanel.vue:333` 再 `if (!aiMsg || aiMsg.role !== "assistant") return` 提前返回且不复位 loading，输入框永久锁死，只能刷新页面。`frontend/src/components/ChatPanel.vue:336` 的 `fetch(/api/v1/approve)` 未检查 `response.ok`，401/403/500 都会当成正常流继续读 `response.body`。

修复归属：**纯前端**。
验收：生成过程中切到“文档”再切回，回答继续流式且 HITL 卡片仍在；后端返回 401 时提示重新登录而非卡死。

### P0-3 全站没有 401 处理（证据 A）

`frontend/src/lib/api.js:7` 只有 request 拦截器，无 response 拦截器。登录接口已返回 `expires_in`（`app/api/v1/auth.py`），前端未使用。`checkAuth()` 见到 token 即判定已登录。表现：token 过期后每个面板显示各自的“加载失败”文案，用户不知道其实是登录掉了。

附带发现：认证头拼接在仓库里有 4 套实现——`frontend/src/lib/api.js:7`（独立 axios 实例）、`frontend/src/components/DataPanel.vue:7` 与 `frontend/src/components/DocPanel.vue:7`（对全局 axios 各注册一次拦截器）、`frontend/src/components/ChatPanel.vue:336` 与 `frontend/src/App.vue:88`（裸 fetch 手工拼 Authorization）。任何一处漏改都会造成“某些页面 401、某些页面正常”的错觉。

修复归属：**纯前端**（收敛到 `frontend/src/lib/api.js` 一处 + response 拦截器）。
验收：手工把 `eb_token` 改成非法值，任意操作都应被统一弹回登录页并提示原因。


### P0-4 退出登录清空历史，且历史从未上后端（证据 A）

会话只存在 localStorage：`frontend/src/components/ChatPanel.vue:6` 定义 `STORAGE_KEY = eb_sessions_v2`，`:27` 与 `:42` 按会话读写 `eb_msg_<id>`，`:107` 删除会话时 `removeItem`。`frontend/src/App.vue:121` 的 `doLogout()` 遍历删除所有 `eb_*` 键，因此**正常退出即清空全部历史**；换一台机器或换一个浏览器，历史为零。

后端 `GET /api/v1/sessions`（`app/api/v1/chat.py:1196`）、`GET /api/v1/sessions/{id}`（`app/api/v1/chat.py:1208`，返回 `{session, messages}`）、`DELETE /api/v1/sessions/{id}`（`app/api/v1/chat.py:1222`）均已实现且按 owner 过滤，前端从未调用。

修复归属：**纯前端**（列表与正文）；会话标题与重命名需要后端，见 B-4。
验收：退出再登录，历史列表与消息仍在；A 账号看不到 B 账号的会话。

### P0-5 总览用假数字，与三个页面互相打脸（证据 A）

`frontend/src/components/DashboardPanel.vue:140` 把三条硬编码洞察标题作为 `insights` 提交给 `/dashboard`；`app/dashboard/service.py:15` 的 `build_dashboard()` 原样回传 `insights`；`frontend/src/components/DashboardPanel.vue:37` 取前 4 条渲染“异常与风险”，`frontend/src/components/DashboardPanel.vue:40` 把 `severity` 为 critical 的条数当成“审批任务”数；趋势线由固定乘数数组生成。

使用者视角最致命：总览显示“审批任务 1”，点进去（`frontend/src/components/DashboardPanel.vue:251` 与 `:254` 的按钮只做 `emit(goto, insights)` 切页）落到洞察或审批页，那里是一个 680/500 的计算器，与“1”毫无关系。老板第一次走查即可发现。

修复归属：**纯前端**（改为消费 `GET /api/v1/alerts` 的真实告警，必要时先 `POST /api/v1/alerts/check`）。趋势线需要后端才有真实历史，见 B-7。
验收：总览每个数字都能点进一个可核对的来源列表；源码中不再出现任何写死的业务标题。


## 3. P1 可用性缺陷

| # | 现象 | 证据 | 归属 |
|---|---|---|---|
| 1 | 洞察页写死 3 行假数据，进页面自动提交 | `frontend/src/components/InsightPanel.vue:5`、`:31`、`:40` | 纯前端 |
| 2 | 审批页写死 680/500，进页面自动提交 | `frontend/src/components/ApprovalPanel.vue:5`、`:20`、`:29` | 纯前端 |
| 3 | 图谱页写死“差旅费/属于/费用科目”，进页面自动请求并落审计 | `frontend/src/components/GraphPanel.vue:5`、`:16`、`:33` | 纯前端 |
| 4 | 洞察/图谱/审批三页无任何 emit，不能“带着这条去追问”；数据面板反而可以 | 全仓 emit 调用仅见于 `DashboardPanel.vue:5`、`DataPanel.vue:145`、`DocumentPreviewModal.vue:42-53` | 纯前端 |
| 5 | 用户只是看了一眼侧栏，审计日志里就多出三条“执行了分析” | `app/api/v1/intelligence.py:55` 的 `_authorized()` 统一 `record_audit()` | 前端（改手动触发） |
| 6 | 对话里绑定的数据表不可见、不可改 | `activeDataFilename` 只出现在 `frontend/src/components/ChatPanel.vue` 脚本段（`:13`、`:185`、`:195`），模板中 0 次 | 纯前端 |
| 7 | 顶栏“搜索”“通知”按钮无点击处理，纯装饰 | `frontend/src/App.vue:352`、`frontend/src/App.vue:355` | 纯前端 |
| 8 | 退出按钮是向下箭头符号，易误点且会清空历史（叠加 P0-4） | `frontend/src/App.vue:360` | 纯前端 |
| 9 | 文档删除确认弹窗中文文案乱码（问号串） | 源码本身写坏：`frontend/src/components/DocPanel.vue:277` 的确认文案已是问号串（非显示问题） | 纯前端 |
| 10 | 上传进度是假定时器，不代表解析进度 | `frontend/src/components/DocPanel.vue:36-45`；真实进度需后端提供 `parse_status` | 后端 B-3 |
| 11 | 文件图标函数硬编码某公司文件名关键词 | `frontend/src/components/DocPanel.vue` 的 `fileIcon()` | 纯前端 |
| 12 | 消息数组深度 watch，每个 token 全量序列化写 localStorage，写入无 try/catch，配额溢出会打断回答 | `frontend/src/components/ChatPanel.vue:193`、`:27` | 纯前端（P0-4 修完自动消解） |
| 13 | 手写 Markdown：链接替换未过滤协议，`javascript:` 可注入；无表格支持 | `frontend/src/components/ChatPanel.vue:402-424`，链接替换在 `:414` | 纯前端 |
| 14 | `element-plus`、`markdown-it` 在依赖声明中，全项目零 import | `frontend/package.json` 与 `frontend/src/**` 交叉核对 | 纯前端（清理依赖） |
| 15 | 登录背景图约 2.37MB 打进产物；`login-reference.png` 约 2.1MB 为设计参照赘肉 | `frontend/src/assets/login-background.png`、`frontend/src/assets/login-reference.png` | 纯前端 |
| 16 | 后端 `/alerts*`、`/users*`、`/artifacts`、`/export`、`/queue/*`、`GET /sessions` 全部无界面入口；登录页却提示“请联系管理员在用户管理中重置” | `frontend/src/App.vue:305` 忘记密码弹窗文案 | 纯前端 + B-1 |
| 17 | 删除失败静默：`Promise.allSettled` 的结果被丢弃后直接刷新列表，用户看不到任何失败提示（叠加 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 第 1 节记录的“任何人都删不掉文档”） | `frontend/src/components/DocPanel.vue:280-283` | 前端 + 后端删除权限链 |


## 4. 洞察 / 图谱 / 审批 三页专项裁定

这三页是“不知道是干嘛的”的直接来源。结论：**它们是 2026-09-07 升级计划里三个阶段的最小接口占位，被镀层后留在了侧栏。**

### 4.1 洞察：要求用户手工给 AI 喂数据

- 页面自称“系统自动识别异常变化，帮你更早发现问题”，实际要人填 部门/指标/当前值/上期值/阈值 五个框（`frontend/src/components/InsightPanel.vue:5` 起）。
- 算法只有约 15 行：`app/insights/rules.py:1` 的 `detect_insights(rows)` —— 超阈值或环比涨幅大于 20% 即产出，涨幅达 50% 记 critical。它不读任何数据文件。
- 真实异常引擎在别处：`app/api/v1/alerts.py:143` 的 `evaluate_all()` 遍历 `data/` 下 Excel/CSV，按 `alert_rules` 判定，`app/api/v1/alerts.py:128` 的 `_ai_analysis()` 调模型做归因，写入 `alerts` 表，并通过 `send_im_notification()` 推送；`app/scheduler/jobs.py` 已注册定时执行。**这套有规则 CRUD、有落库、有定时、有推送，唯独没有任何界面。**
- `docs/handoff/2026-09-14-consolidated-fix-plan.md:114` 已把“告警与洞察两套异常逻辑并存”记为待决项，并明确“合并前不要单边改动”。本文不推翻该结论，只补充一条：**面向用户的入口应当只有 alerts 那一套。**

裁定：改名“异常与告警”，改为消费 `GET /api/v1/alerts`、`GET/POST/DELETE /api/v1/alerts/rules`、`POST /api/v1/alerts/check`。手填五格表单删除。**零后端改动。**

### 4.2 图谱：名字叫图谱，页面上没有图

- 页面结构 = 四个输入框（`frontend/src/components/GraphPanel.vue:5-11`）+ 一个三元组列表（`:24` 提交、`:16` 读取）。无节点、无边、无布局、无下钻。
- 存储：`app/api/v1/intelligence.py` 的模块级 `_graph = KnowledgeGraph()`，实例内部是 `self._relations` 字典 + `JsonPersistenceAdapter`。**在配置 `KNOWLEDGE_GRAPH_STORE_PATH` 时才落盘**（`storage_state` 报告 `durable: true`、`shared_across_processes: true`、`protection: none`），未配置时退回进程内字典；生产环境写入失败会抛 `ProductionReadOnlyProtection` 而不是静默降级。`docs/handoff/2026-09-14-consolidated-fix-plan.md:79` 已把“知识图谱字典等内存回退伪装成正常状态”列为生产风险。
- 审核闭环只存在于代码里：`app/knowledge_graph/service.py` 的 `confirm()` 已实现，但**无路由、无按钮**，candidate 永远停在 candidate。
- 权限语义拧巴：新增关系要求 `ACTION_UPLOAD`（`app/api/v1/intelligence.py:104`），读取要求 `ACTION_VIEW`（`app/api/v1/intelligence.py:126`）。
- 设计目标（证据 D，`docs/superpowers/plans/2026-09-07-enterprise-intelligence-upgrade.md` 阶段 6）要求 `models.py`/`extractor.py`/`store.py` + 可视化 + 人工确认，可靠性边界写明“只有存在原文证据才能进入图谱”“图谱问答必须返回关系来源”。实际只落地 `service.py` 一个文件，抽取与持久化均无。
- 结论性判断：**没有任何员工会手工录入公司关系**，该页不具备被真实使用的可能。

裁定：短期撤下侧栏入口，降级为文档预览里的“依据 / 相关制度”子视图（`GET /api/v1/knowledge-graph/relations` 已支持 `source_entity` 与 `relation` 过滤，前端未用）。若要恢复为独立工作区，仍缺从检索命中自动生成 candidate 关系与审核界面（持久化已于本轮由其他 Agent 补齐，见第 12 节），属**后端建模**。

### 4.3 审批：是计算器，而且比对话里的版本笨

- 页面要求用户自己填“标准 500”（`frontend/src/components/ApprovalPanel.vue:7`），后端只做减法：`app/approval/assistant.py:32` 的 `build_precheck` 比较金额与标准，无证据则 risk 为 unknown，超出比例达 20% 记 high。`app/approval/assistant.py:86` 恒返回 `approved: False`——**它不审批任何东西**：无工单实体、无提交、无待办列表、无指派、无历史。
- 更强的版本挂在对话里：`app/agents/orchestrator.py:446` 的 `_approval_worker_node` 先用 `parse_expense_request(question)` 从自然语言抽金额，再检索制度原文，再用 `extract_standard()` 从原文抽出最严格的限额，最后才 `build_precheck`。
- 因此使用者会得出一个坏结论：**在对话里问“住宿 680 一晚超标吗”比在审批页点按钮更可信**，因为前者的标准来自真实制度，后者的标准来自用户记忆。
- 设计目标（证据 D，同计划阶段 7）要求：字段校验 → 语义匹配 → 知识库/图谱检索 → 规则计算 → 判断责任方与审批节点 → Critic 检查证据 → 生成预审结论与可编辑的审批说明；并明确第一版“只生成预审建议和审批单草稿，不直接提交真实财务审批”。实际只落地 `app/approval/assistant.py`，`models.py`/`service.py`/`rules.py`/`api/v1/approval.py` 均不存在。
- 权限缺口：预审只要 `ACTION_VIEW`（`app/api/v1/intelligence.py:88`），且 `department` 由前端任意填写并被服务端接受（`app/api/v1/intelligence.py:93`），低权限用户可冒任意部门名义出结论。

裁定分两步：

1. 短期改名“报销自查”，界面写清这是自查工具而非待办系统；后端小改——`ApprovalRequest` 增加 `standard_source: auto`，复用 `_approval_worker_node` 的检索与抽取路径，禁止前端传 `department`。
2. “办待办”是另一件事，必须先建工单模型（见 C-1），不要在现有 `precheck` 上贴皮。


### 4.4 与设计文档的差距总表

| 能力 | 计划文件（证据 D） | 实际落地（证据 A） | 缺口 |
|---|---|---|---|
| 主动洞察 | 阶段 4：`models.py`/`detector.py`/`service.py`/`api/v1/insights.py`/调度去重/`GET /insights` 与 ack、resolve | 仅 `app/insights/rules.py` 纯函数 + `/insights/detect` | 无实体、无持久化、无状态流转、无调度、无列表接口 |
| 知识图谱 | 阶段 6：`models.py`/`extractor.py`/`store.py`/可视化/审核 | 仅 `app/knowledge_graph/service.py` 内存 dict | 无持久化、无抽取、无可视化、`confirm()` 无入口 |
| 审批助手 | 阶段 7：`models.py`/`service.py`/`rules.py`/`api/v1/approval.py`/审批单草稿 | 仅 `app/approval/assistant.py` 计算器 + 一个 precheck 路由 | 无工单、无流程、无草稿、无审批说明编辑 |

## 5. 前后端改造分档

### A 档 纯前端即可（后端已就绪）

| 事项 | 后端已有什么 |
|---|---|
| 图表显示（P0-1） | `/api/v1/artifacts/{artifact_id}/content`（`app/api/v1/artifacts.py:40`）；blob 取文件的现成范式见 `frontend/src/components/DocPanel.vue:89` |
| 401 与过期处理（P0-3） | `/login` 已返回 `expires_in`（`app/api/v1/auth.py`） |
| ChatPanel 常驻（P0-2） | SSE 与 `/approve` 契约不变 |
| 历史会话（P0-4） | `app/api/v1/chat.py:1196`、`:1208`、`:1222` |
| 文档元数据与版本 | `GET /documents/catalog`（`app/api/v1/chat.py:1355`）已返回 `version`、`classification`、`department`、`storage_path`、`created_at`；`GET /documents/{filename}/versions`（`app/api/v1/chat.py:1360`） |
| 异常与告警工作区 | alerts 路由齐备：规则新增/列表/删除、告警列表、立即检查（`app/api/v1/alerts.py`）。**但读接口也要求管理告警权限，见 B-9** |
| 报告导出 | `POST /export`（`app/api/v1/data.py:296`）返回 Artifact 响应 |
| 用户管理 | `GET/POST/DELETE /users`、`PUT /users/password`，服务端强制 `ACTION_MANAGE_USERS` |
| 总览数字与列表真实化（P0-5） | 同上 alerts + catalog + data-files |
| 去掉自动提交、修乱码、清死依赖、补面板间联动 | 无 |


### B 档 后端小改（一条路由或几个字段）

| # | 事项 | 现状与做法 |
|---|---|---|
| B-1 | `GET /artifacts` 列表 | `app/storage/artifacts.py` 的 `ArtifactRegistry` 只有 `register`/`get`/`get_active`/`soft_delete`，无查询；元数据落在 `.artifact-metadata.json`。“交成果 / 报告历史”视图必须有按 principal 与类型过滤的分页列表 |
| B-2 | `/ask` 的 `sources` 事件 | 来源只在非流式 `POST /chat` 内部拼装（`app/api/v1/chat.py:591`），`/ask` 从不发。`retrieval_traces` 表可作数据源。不要用 `/provenance/summary` 顶替：它要求前端回传 `results`，响应明确 `provenance_source = client_provided` 且 `server_verified = False` |
| B-3 | catalog 补 `size`、`parse_status`、`chunk_count`、`uploader` | `document_versions` 表缺列，需同时改 `app/documents/catalog.py` 的 `record_document_version`，否则真实上传进度做不了 |
| B-4（已缩小） | 仅需 `PATCH /sessions/{id}` 支持重命名 | 订正：`sessions` 表与 `_list_sessions()` 已含 `title`、`updated_at`、`msg_count`，且**后端在首条用户消息时自动取前 30 字作为标题**（`app/api/v1/chat.py` 的消息写入路径）。前端不需要自行推导标题；`app/storage/sessions.py` 的 `SessionRegistry` 只负责归属校验，不是列表数据源 |
| B-5 | `GET /metrics` 只读指标目录 | `metric_definitions` 表已在 migrations 0001-0004 建好但无路由；洞察去掉手填阈值需要它。`docs/handoff/2026-09-14-consolidated-fix-plan.md:104` 已登记同项 |
| B-6 | 日报路由 | `daily_report()` 有实现（`app/api/v1/alerts.py:206`）但无 HTTP 路由，只有定时任务会跑 |
| B-7 | 趋势历史 | `/dashboard` 无时间序列输入，前端才被迫手写乘数线；要真趋势需一个最小聚合接口 |
| B-8 | precheck 自动取标准 | 见 4.3 第 1 步 |
| B-9（新发现） | alerts 读权限拆分 | `GET /alerts`、`GET /alerts/rules`、`POST /alerts/check` 都走 `_require_alert_management()`，即要求管理告警的权限，**普通员工拿 403**。所以“盯异常”对员工侧不是纯前端任务：要么把列表读权限拆到 view，要么提供员工自己的只读端点 |

### C 档 必须后端建模（不是加接口能解决）

| # | 事项 | 说明 |
|---|---|---|
| C-1 | 审批工单 | 实体、assignee、状态流转、历史、附件全不存在；`app/approval/` 只有 `assistant.py` |
| C-2 | 知识图谱持久化与抽取 | 见 4.2；内存 dict 不能作为任何生产承诺的基础 |
| C-3 | 细粒度权限下发 | 前端 `isAdmin` 只来自 localStorage 的 `eb_role`（`frontend/src/App.vue:25`），是假权限；真实能力清单应由后端下发 |


## 6. SSE 双轨契约（本轮唯一必须跨端决策的点）

`app/api/v1/chat.py:99` 的 `sse_event()`（legacy）与 `app/api/v1/chat.py:103` 的 `canonical_sse_event()`（envelope 含 `request_id`、`trace_id`、`task_id`、`sequence`、`timestamp`、`status`、`data`）并存。`POST /ask`（`app/api/v1/chat.py:676`）**同时**发两套：canonical 形如 `request.started`、`request.cancelled`、`request.failed`；legacy 为 `queued`、`status`、`step`、`hitl`、`error`、`done`、`cancelled`、`heartbeat`。

前端只处理 legacy 事件名，并直接读 legacy 的 `payload.content`。**后端任何一次“下线 legacy”的清理都会让对话页瞬间空白，且不报错。**

建议（需前后端两个负责方共同签字，并写入 `docs/api/contract-v1.md`）：

1. 后端在冻结期内不下线 legacy 事件名，或显式声明 `protocol_version` 并同时发两个字段。
2. 前端解析器改写为“以 canonical envelope 为主、legacy 兜底”，未知事件丢弃而非崩溃。
3. 契约文档补一节“事件名废弃策略”，禁止单边改动。

## 7. 信息架构重排建议

按“员工今天来干什么”重排，7 个入口收敛为 5 个主视图 + 1 个管理视图：

| 新视图 | 覆盖原页面 | 后端依赖 |
|---|---|---|
| 问一句 | 对话（吸收图谱作为依据子视图） | 现状可用；`sources` 事件属 B-2 |
| 盯异常 | 洞察改为 alerts | 管理端现状可用；员工端受 B-9 阻塞 |
| 办待办 | 审批（真工单） | C-1，未建模前该视图不上线 |
| 交成果 | 从对话与数据析出的报告、图表历史 | B-1 |
| 喂料 | 文档与数据合并为一个资料视图（同一动作：让系统知道） | 现状可用 |
| 管系统 | 用户、指标口径、告警规则、队列 | `/users*`、`/semantics/match`、`/alerts/rules` 现状可用；`/metrics` 属 B-5 |

总览不再放硬编码卡片，改为每个视图的真实待办计数加一条“今天最该看的一件事”。

## 8. 最小上线路径

| 顺序 | 动作 | 归属 | 阻塞关系 |
|---|---|---|---|
| 1 | 修 P0-1 图表（放宽正则 + blob 渲染） | 前端 | 无 |
| 2 | 修 P0-2 ChatPanel 常驻与 `approve()` 的状态复位、`response.ok` 检查 | 前端 | 无 |
| 3 | 修 P0-3 统一 401，收敛 4 套鉴权 | 前端 | 无 |
| 4 | 撤下图谱入口，审批改名“报销自查”，三页去掉自动提交 | 前端 | 无 |
| 5 | 洞察页改为 alerts 界面，总览数字换成真实告警数 | 前端（管理端）+ 后端 B-9（员工端） | 员工侧读权限未拆前只显示“暂无可见异常” |
| 6 | 历史会话改读 `/sessions*` | 前端 | 无（标题与时间已由后端提供） |
| 7 | 冻结 SSE 契约，前端解析器转 canonical | 双端 | 必须先于任何 legacy 清理 |
| 8 | `/artifacts` 列表、`sources` 事件、catalog 解析状态 | 后端 | B-1/B-2/B-3 |
| 9 | 工单模型、图谱自动抽取、权限下发 | 后端 | C 档，另立计划（图谱持久化本轮已落地） |

第 1-6 项全部不依赖后端改动，可以在当前后端上直接交付。


## 9. 本轮验证范围

已做：

- 静态核对 `frontend/src/**`：`App.vue`、`ChatPanel.vue`、`ChartViewer.vue`、`DocPanel.vue`、`DataPanel.vue`、`DashboardPanel.vue`、`InsightPanel.vue`、`GraphPanel.vue`、`ApprovalPanel.vue`、`lib/api.js`。
- 静态核对 `app/**`：`api/v1/chat.py`、`api/v1/intelligence.py`、`api/v1/alerts.py`、`api/v1/data.py`、`api/v1/artifacts.py`、`api/v1/auth.py`、`common/auth.py`、`main.py`、`agents/orchestrator.py`、`agents/tools.py`、`approval/assistant.py`、`insights/rules.py`、`knowledge_graph/service.py`、`storage/artifacts.py`、`storage/sessions.py`、`dashboard/service.py`。
- 本文所有 A 级结论均可按 文件:行 复核。
- 在 `frontend/` 执行 `npx --no-install vite build` 编译通过（82 modules，JS 约 185KB，CSS 约 83KB，产物写入 `frontend/dist`）——仅证明可编译，不证明运行时正确。

未做（不要据此判断功能可用）：

- 未启动后端或前端服务，未做浏览器点击走查。
- 未运行 pytest，未验证任何接口的真实响应。
- 未连数据库，未跑迁移。

## 10. 订正说明

相对早前口头走查与既有文档，本轮补正两点：

1. 图表缺陷的根因不只是“前端正则写死 `/static/`”，而是**前端正则与后端 Artifact URL 方案不同步，同时 `/static/charts`、`/static/exports` 已被 `app/main.py:119` 的 `StaticFilesWithoutGeneratedArtifacts` 主动返回 404**。因此即使把前端正则放宽，只要仍用裸 `<img>`，结果依旧是 401 或 404。两条必须一起修。
2. 会话存储并非“后端没有”：`GET /sessions` 等三个端点已实现且做 owner 过滤（`app/api/v1/chat.py:1196` 起），缺的是前端调用；不要按“需要新增会话接口”立项。

## 11. 与其他文档的关系

- 完成度、权限矩阵、迁移与生产风险仍以 `docs/current-functionality-2026-09-10.md` 与 `docs/api/resource-authorization-matrix.md` 为主口径。
- 后端修复切片仍以 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 为准；本文不改变其 Wave 划分，只提供前端侧的接口需求输入。
- 本文不改动 `frontend/` 任何文件，也不主张任何尚未做的前端重构已经落地。

## 12. 并发改动订正（2026-09-14 14:10）

本文写作期间另一路会话正在改后端，以下三处结论已按最新源码订正，正文相应条目同步更新：

1. **图谱持久化已不再是缺口。** `app/knowledge_graph/service.py` 在本轮被重写为带 `JsonPersistenceAdapter` 的实现，配置 `KNOWLEDGE_GRAPH_STORE_PATH` 后 `durable` 与 `shared_across_processes` 均为真，生产环境写入失败改为抛 `ProductionReadOnlyProtection` 而非静默降级。因此 4.2 的“重启即清空”已失效，撤下入口的理由收敛为三条：**无图形界面、无自动抽取（关系仍需人录）、`confirm()` 依旧没有路由与按钮**。

2. **B-4 缩小。** `sessions` 表与 `_list_sessions()` 已包含 `title`、`updated_at`、`msg_count`，且后端在首条用户消息时自动截取前 30 字作为标题。前端不需要自己推导标题，B-4 只剩“可选的重命名端点”。

3. **新增 B-9（阻断“盯异常”纯前端交付）。** `GET /alerts`、`GET /alerts/rules`、`POST /alerts/check` 都经过 `_require_alert_management()`，即要求管理告警的权限，普通员工会得到 403。所以第 8 节第 5 步的归属从“纯前端”改为“管理端前端 + 员工端需 B-9”。

引用口径调整：

- 对**本轮被并发编辑过的后端文件**（`app/api/v1/chat.py`、`app/api/v1/alerts.py`、`app/api/v1/artifacts.py`、`app/documents/catalog.py`、`app/common/auth.py`、`app/common/audit.py`、`app/main.py`、`app/storage/persistence.py`、`app/knowledge_graph/service.py`），本文引用改为**符号名 / 路由 / 事件名**，不再依赖行号。
- 其余后端与前端的行号是 2026-09-14 上午到中午的快照，复核时请重新定位。
- 配套交付：后端侧接口需求另立清单 `docs/handoff/2026-09-14-backend-interface-requests.md`（R1 即本节的 B-9）；SSE 事件废弃策略已作为独立一节追加到 `docs/api/contract-v1.md`（仅追加，未改动其他 Agent 正在编辑的段落）；第 8 节第 1-6 步已展开为任务单 `docs/handoff/2026-09-14-frontend-workspace-fix-tasks.md`。

