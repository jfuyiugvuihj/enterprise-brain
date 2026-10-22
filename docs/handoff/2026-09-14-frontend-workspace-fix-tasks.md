# 前端工作区修复任务单（交前端 Agent）

生成时间：2026-09-14 13:58（Asia/Shanghai）
依据：`docs/frontend-workspace-audit-2026-09-14.md` 第 8 节第 1-6 项；SSE 相关约束见 `docs/api/contract-v1.md` 的 SSE Event Deprecation Policy 一节
性质：任务说明书。本文件不含任何代码改动，也不要求执行会改数据或启动服务的命令

## 0. 开工前必读（并发变更，不可跳过）

1. **另一路对话正在改后端。** 本文件生成前 3 小时内被写入的后端文件包括：`app/api/v1/chat.py`、`app/api/v1/alerts.py`、`app/api/v1/artifacts.py`、`app/documents/catalog.py`、`app/common/auth.py`、`app/common/audit.py`、`app/main.py`、`app/storage/persistence.py`、`app/knowledge_graph/service.py`。

   - 因此本文引用后端时一律用**符号名、事件名、路由路径**，不写行号；开工前请重新读一遍目标函数，不要照抄任何文档里的行号。

2. `frontend/src/**` 自 9/11 起无人写入（`App.vue` 最后修改 9/11 13:39，其余面板 9/9-9/10），可以安全开工。

3. **只允许改 `frontend/src/**`，不要修改 `app/**` 下任何文件。** 需要后端配合的项已在任务里标为“依赖”，只登记不实现。

4. 你不是独自在这棵代码树上工作：不得回退或覆盖他人改动，遇到冲突停下来报告，不要强解。

5. 验收一律用手工点击或本地 mock，不要跑迁移、不要连生产库、不要用真实文档做删除实验。

### 0.1 串行要求

F2、F3、F4、F6 都要改 `frontend/src/App.vue`，F4 与 F5 都要动 `InsightPanel.vue`。**按 F1 → F2 → F3 → F4 → F5 → F6 串行合入**，不要并行开多个分支改同一文件。

## F1 图表恢复显示（对应 P0-1）

**写入范围**：`frontend/src/components/ChatPanel.vue`、`frontend/src/components/ChartViewer.vue`

**现状**：

- 后端图表工具返回的标记形如 `![标题](/api/v1/artifacts/<id>/content)`（见 `generate_chart` 与 `ArtifactRecord.content_url`）。
- 前端 `parseCharts()` 与 `stripChartMarkers()` 的正则只匹配 `/static/` 前缀，因此该标记既不渲染也不被剥掉，以裸 Markdown 文本出现在回答里。
- `ChartViewer.vue` 用裸 `<img :src>` 请求图片，浏览器不带 Authorization，而后端 `get_token_from_request()` 只读 Authorization 头；同时 `/static/charts`、`/static/exports` 已被主动返回 404。

**要改**：

1. 图片标记正则放宽为同时接受 `/static/` 与 `/api/v1/artifacts/`（更稳的做法是接受任意本站绝对路径）。
2. `ChartViewer` 不再用裸 `<img>`：改为用带 Authorization 的请求取 blob，再 `URL.createObjectURL` 渲染，组件卸载时 `revokeObjectURL`。仓库内已有同类写法可参照（`DocPanel.vue` 取 `/documents/{filename}/file` 的那段）。
3. 补失败态：401 / 403 / 404 显示“图表无法显示（登录失效或无权限）”加一个重试按钮，不留空白。
4. 后端对 html 类图表返回的是 `[标题](url)` 而不是 `![标题](url)`：这类链接要单独识别为“在新窗口打开”，不要当图片处理。

**验收**：登录 → 对话 → 分别生成柱图、折线图、饼图各一张，三张图都在气泡内可见、可放大、可下载；手工把 `eb_token` 改坏后刷新，显示失败态而不是空白；重新登录后图仍可显示。

**不做**：不改后端 URL 方案，不引入签名 query token（那属于改动鉴权中间件，风险高且未获批）。


## F2 对话页生命周期（对应 P0-2）

**写入范围**：`frontend/src/App.vue`、`frontend/src/components/ChatPanel.vue`

**现状**：

- `App.vue` 用 `v-if / v-else-if / v-else` 链切换工作区，`ChatPanel` 落在 `v-else`，切到任意其他面板即销毁组件：SSE 读取随 `onUnmounted` 中断，`hitl` 卡片与 `loading` 一并丢失，回答停在半句。
- `ChatPanel.vue` 的 `approve()` 先置 `loading.value = true`，随后存在一条提前 `return` 分支不复位 `loading`，输入框永久锁死。
- 同一个函数里的 `fetch(/api/v1/approve)` 未检查 `response.ok`，401 / 403 / 500 都会继续按正常流读取 body。

**要改**：

1. 工作区切换改为让 `ChatPanel` 常驻（`v-show` 或 `keep-alive`），其余面板可按需渲染；流式进行中切页不中断，已到达的 token 不丢弃。
2. `approve()` 用 `try / finally` 保证 `loading` 复位，所有提前返回分支都要复位。
3. 加 `response.ok` 检查：非 2xx 时读出 `detail` 提示（401 走 F3 的统一逻辑），不要继续读流。
4. 终态兜底：收到 canonical 的 `request.completed / request.failed / request.cancelled` 或 legacy 的 `done / cancelled / error` 任一事件，都复位 `loading`、清 `hitl`、解锁输入框。此条与 `docs/api/contract-v1.md` 冻结规则第 3、4 条对齐。
5. 解析器改为忽略未知事件名（后端新增 canonical 事件时不能报错）。

**验收**：提问后立刻切到文档再切回，回答继续输出且不错位；输出中触发 HITL，确认后正常继续；把 `/approve` mock 成 401 时提示重新登录且输入框仍可用；连续中断 3 次不留死锁。

**不做**：不引入状态管理库；不要求后端改动事件。

## F3 统一鉴权与 401（对应 P0-3）

**写入范围**：`frontend/src/lib/api.js`、`frontend/src/components/DataPanel.vue`、`frontend/src/components/DocPanel.vue`、`frontend/src/components/ChatPanel.vue`、`frontend/src/App.vue`

**现状**：拼认证头有 4 套实现（`lib/api.js` 的独立 axios 实例、两个面板各自对全局 axios 注册拦截器、两处裸 fetch 手工拼头）；只有 request 拦截器没有 response 拦截器；`/login` 已返回 `expires_in` 但前端未用；`checkAuth()` 只看 token 是否存在。

**要改**：

1. REST 调用收敛到 `lib/api.js` 的实例；SSE 与 blob 请求共用同一个 token 读取函数，不要再手写第三处。
2. 登录成功时存 `expires_at`（当前时刻 + `expires_in`），`checkAuth()` 校验时间，过期即回登录页并说明原因。
3. 加 response 拦截器：401 → 清 token、跳登录、提示“登录已过期”；403 → 留在当前页提示“无权限做这件事”，不要静默吞掉，也不要误跳登录。
4. 各面板的“加载失败”文案带上 HTTP 状态码或服务端 `detail`，避免把掉登录误认成功能 bug。

**验收**：手工把 `eb_token` 改成非法值，任意面板操作统一弹回登录页；把 `expires_at` 改到过去同样；构造 403 时不跳登录只显示提示。

**不做**：不引入 `element-plus`；不新增前端路由库。

## F4 三页停止自动提交、定位与改名（对应 P1 1/2/3/4/5/8）

**写入范围**：`frontend/src/components/InsightPanel.vue`、`frontend/src/components/ApprovalPanel.vue`、`frontend/src/components/GraphPanel.vue`、`frontend/src/App.vue`

**要改**：

1. 删除三个面板 `onMounted` 里的自动请求，一律改为用户点击触发。理由：后端每个 intelligence 路由都写审计记录，用户只是看一眼侧栏就会留下三条“执行了分析”的操作日志。
2. 删除写死初值：洞察页三行假数据、审批页的 680 与 500 与市场部、图谱页的差旅费三元组。空态改成说明文字（例如“填写金额与费用类型后点击预审；制度标准由系统从知识库检索”）。
3. 侧栏“审批”改名“报销自查”；“图谱”暂时从导航里移除（组件与接口保留，只是不再暴露入口，理由见审计文档 4.2）。
4. 三个面板各加一个“带着这条去追问”按钮，复用 `App.vue` 已有的 `handleAsk`（数据面板已经在用这条链路，不要另发明一种通信方式）。
5. 顶栏“搜索”“通知”两个按钮要么接上功能要么删掉，不留假按钮；退出按钮从箭头改成明确文字“退出”，并加二次确认（在 F6 完成前，确认文案要写明“本机历史记录将被清除”）。

**验收**：冷启动依次点开三个面板，Network 面板中无自动请求；侧栏看不到图谱；每个面板都能一键跳到对话并带上上下文；退出不可能误触。

**不做**：不做审批工单，不做图谱可视化，不改后端权限。


## F5 异常视图接 alerts + 总览真实化（对应 P0-5）

**写入范围**：`frontend/src/components/DashboardPanel.vue`、`frontend/src/components/InsightPanel.vue`（或新建 `AlertPanel.vue`）

**先读依赖（重要）**：后端 alerts 的读接口目前**同样要求管理告警的权限**（`_require_alert_management` 对规则列表、`GET /alerts`、`POST /alerts/check` 一视同仁）。因此普通员工登录时这些调用会返回 403，**F5 不是纯前端可以完整交付的任务**。拆成两步：

- **F5a（现在就能做）**：管理员视角的“告警规则 + 告警列表 + 立即巡检”界面，接 `POST /alerts/rules`、`GET /alerts/rules`、`DELETE /alerts/rules/{id}`、`GET /alerts`、`POST /alerts/check`；403 时显示“仅管理员可管理告警”。
- **F5b（需后端）**：员工级只读告警列表，需要后端补归属列并把读权限拆到 view（审计文档记为 B-9，接口需求见 `docs/handoff/2026-09-14-backend-interface-requests.md` 的 R1）。在 B-9 落地前，非管理员的总览**不要显示告警计数**，改为“暂无可见异常”。

**已知响应字段**（按源码读到的键写，不要猜）：

| 端点 | 响应 |
|---|---|
| `GET /alerts` | `{ alerts: [ { id, rule_id, message, ai_analysis, read, created_at } ] }`（最新 100 条，倒序） |
| `GET /alerts/rules` | `{ rules: [ { id, name, metric, op, threshold, enabled } ] }` |
| `POST /alerts/rules` | 创建后的规则对象 |
| `DELETE /alerts/rules/{id}` | `{ status: "ok" }` 或 `{ status: "not_found" }` |
| `POST /alerts/check` | `{ triggered: [ { message, ai_analysis } ], scan_scope: { data_dir_configured, evaluated_files, reason } }` |

`scan_scope.reason` 必须显示给用户（例如 `no_permitted_datasets`、`tenant_data_dir_unavailable`），否则“巡检没结果”会被误读成“系统认为一切正常”。这条属于诚实性要求，不要省。

**总览真实化**：

1. 删除 `demoRows` 与硬编码的 `insights` 数组，删除固定乘数生成的趋势线。
2. KPI 改为真实来源：文档数用 `GET /documents/catalog`，数据表数用 `GET /data-files`，异常数用 `GET /alerts`（仅有权限时）。
3. “审批任务”卡在没有工单模型之前**必须移除**，不要再拿 critical 条数冒充待办数。
4. 无真实历史接口时，趋势区显示空态说明，不要画假曲线。

**验收**：总览不存在任何写死的业务标题；非管理员账号登录时告警区显示权限说明而非空白或报错；点“立即巡检”能看到 triggered 列表与扫描范围（含被跳过原因）。

## F6 历史会话上后端（对应 P0-4）

**写入范围**：`frontend/src/components/ChatPanel.vue`、`frontend/src/App.vue`

**契约（已按当前源码核对，字段以重新读取为准）**：

| 端点 | 响应 |
|---|---|
| `GET /sessions` | `{ sessions: [ { id, user_id, title, created_at, updated_at, msg_count } ] }`，已按 `updated_at` 倒序 |
| `GET /sessions/{id}` | `{ session, messages }` |
| `DELETE /sessions/{id}` | `{ status: "ok" }` |

会话归属由服务端按 principal 过滤；`title` 后端已在首条用户消息时自动取前 30 字，**前端不要再自己推导标题**。

**要改**：

1. 会话列表与消息改读上面三个端点；localStorage 只保留 UI 偏好（侧栏折叠等），会话正文不再落本地。
2. `doLogout()` 不再删除 `eb_msg_*` 与 `eb_sessions_v2`，只清 token、user、role。
3. 拉取失败区分 401（交给 F3 统一处理）与空列表（显示“还没有历史对话”）。
4. 去掉“每个 token 全量序列化写本地”的深监听大户，改为不写或只在终态写元数据。

**验收**：退出并重新登录后，历史列表与消息仍在；两个账号互不可见对方会话；长对话不再触发 localStorage 配额错误。

**不做**：会话重命名（需后端提供 `PATCH /sessions/{id}`，属可选项）。

## 依赖矩阵

| 任务 | 是否需要后端 | 阻塞项 | 未解阻塞时的降级方案 |
|---|---|---|---|
| F1 图表 | 否 | 无 | - |
| F2 生命周期 | 否 | 无 | - |
| F3 鉴权 | 否 | 无 | - |
| F4 三页定位 | 否 | 无 | - |
| F5a 管理端告警 | 否 | 无 | - |
| F5b 员工端告警 | 是 | B-9（读权限拆分） | 非管理员显示“暂无可见异常” |
| F6 会话 | 部分 | 重命名需 PATCH（可选） | 不提供重命名入口 |
| 交成果视图 | 是 | B-1（`GET /artifacts` 列表） | 不做该视图 |
| 办待办视图 | 是 | C-1（工单模型） | 不做该视图 |

## 完成后请回报

每个 F 项一段，包含：改了哪些文件、手工验收路径与结果、发现的新缺陷、是否需要后端配合（引用审计文档的 B/C 编号）。**不要提交 `app/**` 的改动，不要把别人未完成的改动一起回退或覆盖。**

