# 前端逐文件工单（2026-09-15）

**用途**：把 `docs/frontend-plan-2026-09-14.md` 的 §6.2 十四步 + §6.5 并入项 + §6.6 改判，落成「打开文件就能勾」的工单。实施者不必先读计划全文。
**权威性**：本文件只拆不改。与计划冲突时以计划为准；与代码现状冲突时以代码为准并回来订正本文件。
**已并入**：后端 r8 收口（`c21c342` / `70792ce` / `84af113` / `3e35481` / `9c89ee4`）→ 见 §1。
**禁止**：本工单不授权任何人修改 `app/**`。需后端配合的项一律只登记。

---

## 0. 开工闸门（三条不满足就不要动代码）

### 0.1 工作树闸门

- [ ] `git status --porcelain -- frontend` 当前有 **19 处未提交**，面板文件 mtime 全停在 09-10。开工前先确认这 19 处属于谁、是否保留。**禁止** `git add -A`、`git reset --hard`、`git checkout .`。
- [ ] 建一条自己的分支或 worktree，基线记在 commit 里；每步一提交，提交信息带步骤号（`F1`…`V6`）。
- 理由：另一个 Agent 的未提交工作一旦被覆盖，无法从 git 恢复。

### 0.2 演示账号闸门（r8 带来，阻断全部端到端验收）

- 事实：`app/rag/filters.py` 对**无部门**的检索**硬拒**（`RetrievalScopeError`）；`app/common/rbac.py` 又把**空部门**解释为「全部门可见」。两套相反语义 → 开箱 `admin` 无部门 → **对知识库提问返回 403 `authorization_unavailable`**，也不能上传数据集/出图（403）。
- [ ] 所有需要「问出答案」的验收（F1、F2、F4、F5a、F6）必须用**带部门**的账号，不能用默认 `admin`。
- [ ] 准备至少两个部门账号（甲部 / 乙部）+ 一个 `admin`，用于验作用域不泄露（后端 `c21c342` 已改为按上传者定作用域）。
- [ ] 后端在 (e1) 强制 `AUTH_DEPARTMENT` 与 (e2) `admin` 走 `administrator_scope` 之间拍板前，本工单按「用带部门账号」执行。
- 这是**演示级 P0**：老板现场登录默认 `admin` 问一句话就失败。见计划 §9 R-11。

### 0.3 证据规则（沿用后端 §13.5 的教训）

- [ ] 声称一个缺陷存在，必须能指出**文件 + 符号或字面量**，且 `Test-Path` 通过；不接受「实测到」而无原始产物。
- [ ] 引用后端只用**路由 / 符号名 / 稳定码**，不写行号（计划 §9 R-7：后端实时提交，行号必过期）。
- [ ] 时间戳从环境实取，不接受推断时间。

---

## 1. 后端 r8 收口对本工单的影响

### 1.1 改判（原欠账 → 已落地）

| 项 | 原登记 | 现状态 | 对本工单的具体影响 |
|---|---|---|---|
| R9 / B-11 | `/chart`、`/export` 以 HTTP 200 返回业务失败 | **已落地**（`3e35481`）：改真状态码 | **F2 的「所有请求检查 `response.ok`」从此真正有效**；F7 字典可覆盖 `invalid_filename`、`unsupported_chart_type`、`unsupported_export_format`、`department_scope_required`、`dataset_filename_conflict`、`dataset_preview_failed`、`chart_generation_failed` |
| 计划 §9 R-10 | P1-4 归属曾被记成 health 渲染问题 | **已关闭**：后端 §13.5 采纳前端结论，明确「三页按 §2 裁定不镀层」并把错误码文案交给 F7 | 撤销「需同步订正后端文档」这条待办；冻结提示（hold notice）已被接受 |
| 统计摘要 | `describe()` 无 `sum` 却显示 `N/A` | 后端已修（`70792ce`） | F5a 总览无需再为该占位写特例 |
| HITL 拒绝 | 被拒动作照样执行、会话再次挂起 | 后端已修（`84af113`） | F2 的批准/拒绝流可恢复回归测试；**但不含下面的 D-3** |

### 1.2 新并入前端的缺陷（本轮实测，计划里没有）

| 编号 | 事实（已复核） | 归属 |
|---|---|---|
| **D-1** | **属主删不掉自己的文档**。后端 `app/common/policy.py` 的 `_OWNER_CONTROLLED_ACTIONS` 含 `ACTION_DELETE`，`DELETE /documents/{filename}` 走 `_authorize_document_request(…, ACTION_DELETE)` → 属主有权删。前端 `DocPanel.vue` 的删除按钮、批量条、勾选框、页脚提示**全部** `v-if="isAdmin"`，而 `isAdmin` 只等于 `userRole === 'admin'` → 普通员工误传的文件在界面上**没有入口**，只能裸调 API | **F4** |
| **D-2** | **错误响应体 `detail` 三种形状并存**：① 字符串稳定码（`data.py`、`documents.py`、`auth.py`、多数 `chat.py`）；② 对象 `ErrorEnvelope`（`observability.py` 全部、`chat.py::_document_index_error`）；③ 数组（FastAPI 422 校验）。前端把 `err.response.data.detail` 原样插值 → 上传解析失败会弹 **`[object Object]`** | **F7** |
| **D-3** | **「停止」≠ 取消**。`POST /ask/{session_id}/cancel` 返回 `{cancelled, session_id}`，无在飞运行时 `cancelled` 为 **false**，且 Graph 的 HITL 挂起**不清**（后端 run12 实测：按停止后再批准，被停止的动作照样执行）。前端把 200 当「已停止」是撒谎 | **F2** |
| **D-4** | `ErrorEnvelope.code` 已成**封闭枚举 16 码**（`app/agents/contracts.py`）：`authentication_required`、`permission_denied`、`authorization_unavailable`、`resource_not_found`、`validation_error`、`conflict`、`rate_limited`、`queue_unavailable`、`model_unavailable`、`retrieval_unavailable`、`task_timeout`、`task_cancelled`、`unsupported_file`、`parse_failed`、`index_publish_failed`、`internal_error` | **F7** |

### 1.3 不进本工单（后端线自己的账，勿在前端排期内解决）

- PG `documents` 表已成只插不删的幽灵表（5 行全指向已删文件、`document_versions` = 0、全仓无读点）。
- 数据集 / artifact 删除 API 缺失：仍登记为 **R8 / B-10**，残留数字升到 5 数据集 + 4 artifact + 33 孤儿会话 + PG 5 行。前端**不**做「本地假装删除」。
- `0008` 缺列草稿、后端计划 §4 四项、`task_plan.md` / `progress.md` 的补写。

---

## 2. F 线工单（工作区修复，8 步）

顺序：`F1 → F2 → F3 → F4 → F5a → F7 → F6`；`F5b` 与后端 R1 并行等待。F2/F3/F4/F6 都要改 `App.vue`，**必须串行**。

### F1 图表恢复显示｜零后端｜前置无

文件：`components/ChatPanel.vue`、`components/ChartViewer.vue`、`lib/artifacts.js`（新）

- [ ] 新建 `lib/artifacts.js`：`fetchArtifactBlob(url)` → 用统一 axios 实例（带 Bearer）+ `responseType: 'blob'`，返回 `{ objectUrl, revoke }`
- [ ] `ChatPanel.vue` 图片正则不再只认 `/static/`（现为 `/!\[([^\]]*)\]\((\/static\/[^)]+)\)/g`），要同时吃 `content_url` 的 header-only 相对 URL
- [ ] `ChartViewer.vue` 不再直绑 `props.src`，改收 blob URL；`onUnmounted` 必 `revokeObjectURL`
- [ ] 取图失败渲染**占位卡 + 「重新取图」**，不是浏览器碎图标
- [ ] 切走再回来图仍在（或可无损重取），无内存增长
- 验收：带部门账号 → 问一句 → 要一张柱图 → 100% 可见；Network 里该请求带 `Authorization`
- 回滚：只回退正则与 `ChartViewer` 绑定
- 注意：P1-5 的处方是**前端带 Bearer 取 blob**，不要顺手要求后端放宽鉴权面（计划 §9 R-8）

### F2 对话页生命周期与取消语义｜零后端｜前置无

文件：`App.vue`、`components/ChatPanel.vue`

- [ ] 切走再回来：会话列表、当前会话、滚动位置不丢（先 `shallowRef` 常驻，V3 后交给 router 上下文）
- [ ] `approve()` 后状态复位，不残留「处理中」
- [ ] **所有** fetch/axios 调用检查 `response.ok`（R9 已落地，此项现真正有效）
- [ ] SSE 解析器改为 **canonical envelope 为主 / legacy 兜底 / 未知事件丢弃不崩溃**，并补 `default` 分支（现为 **0 个**）
- [ ] 取消按钮：先 `await cancel()`，**读响应体的 `cancelled`**；`false` 时提示「当前没有正在生成的内容」，不得显示「已停止」（D-3）
- [ ] 取消按钮加二次确认，文案说明可能残留待确认动作；HITL 挂起期间取消后，UI 必须显式保留或清除待确认卡二者之一，不得静默
- 验收：生成中切页返回内容不丢；点停止后 Network 面板可见 `cancelled` 字段与其提示一致

### F3 统一鉴权与 401｜零后端｜前置无

文件：`lib/http.js`（新）、`lib/api.js`、`App.vue`、各面板

- [ ] 4 套鉴权收敛为 1 个 axios 实例；**删掉 `DocPanel.vue` 里那份重复的全局拦截器**（现在装了两份）
- [ ] 加**响应**拦截：401 → 清会话 + Toast + 回登录（现在只有请求拦截，401 判断散在 `DocPanel.vue` 2 处）
- [ ] `expires_in` 到期前提示续期
- [ ] 移除源码里字面 `'????'` 兜底串与 `window.alert(err.response?.data?.detail || …)`
- 验收：手动把 token 改坏 → 任意面板触发 401 → 一次 Toast + 回登录，无原生弹窗

### F4 三页定位、改名与权限入口｜零后端（员工读需 R1）｜前置 V1、V5

文件：`App.vue`、`InsightPanel.vue`、`ApprovalPanel.vue`、`GraphPanel.vue`、`DocPanel.vue`

- [ ] 洞察 → **「异常与告警」**：删手填五格阈值表单与演示数据，改接 `GET /alerts`、`GET/POST/DELETE /alerts/rules`、`POST /alerts/check`
- [ ] 审批 → **「报销自查」**：界面写明是自查工具；**不**加工单列表、不加审批按钮
- [ ] 图谱：撤下侧栏入口，降级为文档预览里的「依据 / 相关制度」子视图；保留路由做重定向
- [ ] 三页**去掉自动提交**（进页面不发请求）
- [ ] **D-1**：`DocPanel.vue` 删除入口从 `isAdmin` 改为「属主或管理员」——判据现成：`documents/catalog` 每行已带 `owner_id` 与 `ownership`（`legacy` 行只允许管理级删），**零后端**；但权限判定不许来自 localStorage（C-3）
- [ ] 顶栏死控件（搜索 / 通知无处理函数）要么接上要么删除；退出按钮补 `aria-label`（P2-4，与 V3 共担，先删）
- 验收：员工账号看「异常与告警」显示「暂无可见异常」而非空表；非管理员能删自己上传的文档
- 回滚：入口用路由重定向兜住，不产生 404

### F5a 总览真实化 + 管理端告警｜零后端｜前置 F4、V3

文件：`views/Alerts.vue`（新）、`DashboardPanel.vue`

- [ ] 删硬编码数字；计数来自 `alerts` + `documents/catalog` + `data-files`
- [ ] 每个数据块显式空态文案，**不放假数据**
- [ ] **B-7 未落地前不画趋势线**（宁可不画也不造）
- 验收：三档数据量（0 / 1 / 多）下总览不出现 `—`、`NaN`、`undefined`

### F5b 员工端告警读取｜**需后端 R1 / B-9**｜前置：后端

- [ ] 前端侧先写「权限未落地」分支：403 → 「暂无可见异常」+ 说明；**不**做假入口
- [ ] R1 落地后接真数据（本步在后端完成前保持未勾）

### F6 历史会话上后端｜部分需后端｜前置 V3

文件：`components/ChatPanel.vue`、`lib/sessions.js`（新）

- [ ] 历史读写 `/sessions*`（`GET` / `DELETE /sessions/{id}` 后端已有）；**退出登录不再清空历史**
- [ ] 标题用后端 `title`，不再前端自行推导
- [ ] 一次性导入 `eb_sessions_v2` / `eb_msg_*` 后**清除** localStorage，不留双轨
- [ ] 可选：重命名需 `PATCH /sessions/{id}`，未提供则**不做**重命名按钮
- 验收：登录 → 登出 → 再登录，历史仍在；清 localStorage 不影响服务端记录

### F7 错误码字典与告警面收敛｜零后端｜前置 F4、F5a

文件：`lib/errcodes.js`（新）、`ApprovalPanel.vue`、`GraphPanel.vue`、`InsightPanel.vue`、`DashboardPanel.vue`、`DataPanel.vue`、`DocumentPreviewModal.vue`、`DocPanel.vue`

- [ ] `normalizeError(err)` 处理 **D-2 三种形状**：字符串稳定码 / `ErrorEnvelope` 对象 / 422 数组，统一产出 `{ code, message, retryable }`
- [ ] 字典初版覆盖 **D-4 的 16 码** + `data.py` 的 `invalid_filename`、`unsupported_chart_type`、`unsupported_export_format`、`department_scope_required`、`dataset_filename_conflict`、`dataset_preview_failed`、`chart_generation_failed`
- [ ] 7 处 `{{ error }}` 原样插值全部改走字典 + `UiToast`：`ApprovalPanel.vue`、`GraphPanel.vue`、`InsightPanel.vue`、`DashboardPanel.vue`、`DataPanel.vue`（2 处）、`DocumentPreviewModal.vue`
- [ ] 未知码走兜底句，并在小字里附「错误码：xxx」保留可报告性
- [ ] 源码里 `window.alert(` 与字面 `'????'` 命中数为 **0**；不得出现 `[object Object]`
- 验收：故意传错文件、无部门出图、坏导出格式，三条路径各出一句人话

---

## 3. V 线工单（视觉与工程，6 步）

### V1 Token 与字体落地｜前置 F3

文件：`assets/theme.css`、`assets/fonts/`、`vite.config.js`、`package.json`

- [ ] `:root` 全量 token（色板、尺度、字号见计划 §4）；单一强调色 `#2ea8e6`
- [ ] `@fontsource-variable/manrope` + `jetbrains-mono` 自托管，**删掉远程 Google Fonts `@import`**（现为 1 处）
- [ ] 引入 `stylelint`：`color-no-hex` + `declaration-strict-value` 零违例
- 验收：断网（内网模拟）下字体正常；`theme.css` 不含远程字体域

### V2 登录页重建｜前置 V1

文件：`App.vue`（auth 分支）、`assets/login-earth.webp`

- [ ] 四层背景：`bg__base`（CSS 渐变）/ `bg__art`（WebP + `mix-blend-mode: screen`，免抠图）/ `bg__grid` + `bg__noise` / `bg__scrim`（只管对比度）
- [ ] 地球元素 1020×941、81KB；**位图不含任何文字**，文案 100% 来自 DOM
- [ ] 删 `100% 100%` 与 `height: 46%` 的拉伸式布局
- [ ] 三张装饰数据卡保留（已裁定：不必管真实性）
- 验收：五档视口截图无裁切、无拉伸；`@supports` 下 `screen` 不可用时回退纯色

### V3 Router + 数据上下文常驻｜前置 F2、F4

文件：`router/`（新）、`views/`（新）、`App.vue`

- [ ] 每个视图有 URL；刷新保持；浏览器后退可用；未登录统一跳登录
- [ ] **当前数据上下文显示在顶栏且可改**（这是本项目最容易出事故的地方：问错部门 / 错数据集）
- 验收：深链 `/{视图}` 未登录时跳登录后能回到原目标

### V4 清 `theme.css` 覆盖债｜前置 V2

文件：`assets/theme.css`

- [ ] `.reference-login` 三轮覆盖（现 **149 处**）清零；行数从 **3393** 下降 ≥ 30%；无孤立选择器
- 验收：逐段删除 + 截图比对，不做一次性大删

### V5 八个自研 token 化原语｜前置 V1

文件：`components/ui/*`、`package.json`

- [ ] `UiButton` / `UiField` / `UiSelect` / `UiTable` / `UiDialog` / `UiToast` / `UiTabs` / `UiUpload`
- [ ] `package.json` 与源码中 `element-plus` 命中为 **0**（现为死依赖：`main.js` 未注册、源码零引用、dist 产物零命中）
- [ ] 每个原语至少 1 条 vitest（键盘导航、空态、排序）
- 代价：3–5 人日。退路（按需保留 Table + DatePicker）需用户拍板才启用

### V6 视觉回归与锁色值｜前置 V2、V4

文件：`playwright.config.js`、`tests/visual/`、`.stylelintrc`、`vite.config.js`

- [ ] 五档基线入库：`1440×900`、`1920×1080`、`3440×1440`、`1280×720`、`768×1024`
- [ ] **不起真实服务器**：`context.route("**/*", …)` 从磁盘 fulfill；abort 掉 `fonts.googleapis.com` / `gstatic` / CDN 模拟客户内网；`/api/*` fulfill 401 验 F3 分支
- [ ] `vite.config.js` 加 `emptyOutDir`
- [ ] 加一条事件契约用例：喂 canonical + legacy + **未知事件**，断言不崩、不空白
- [ ] CI 阻断裸色值与裸间距
- 参考实现：`docs/reference/capture.cjs`（CommonJS + `NODE_PATH`，ESM 不认 `NODE_PATH`）

---

## 4. 文件冲突矩阵（同文件不得并行）

| 文件 | 涉及步骤 | 串行要求 |
|---|---|---|
| `App.vue` | F2、F3、F4、V2、V3、V5 | 六步同文件，**严格按 §2/§3 顺序** |
| `InsightPanel.vue` | F4、F7 | F7 必在 F4 后 |
| `ApprovalPanel.vue` / `GraphPanel.vue` / `DashboardPanel.vue` / `DataPanel.vue` | F4、F5a、F7 | 同上 |
| `DocPanel.vue` | F3、F4（D-1）、F7 | 同上 |
| `assets/theme.css` | V1、V4 | V4 必在 V2 后 |
| `ChatPanel.vue` | F1、F2、F6 | F6 必在 V3 后 |
| `package.json` | V1、V5 | 一次改完，别分两次装依赖 |

---

## 5. 待决策（阻塞上线，不阻塞开工）

| # | 事项 | 影响哪步 | 前端默认执行值 |
|---|---|---|---|
| 1 | 「停止」是否等于拒绝挂起动作（后端语义） | F2 | 按钮文案改「中断生成」+ 二次确认 + 如实读 `cancelled` |
| 2 | admin 检索语义统一（(e1) 强制部门 / (e2) administrator_scope） | 0.2 闸门、F1/F2/F4/F5/F6 全部验收 | 用带部门账号验收；字典含 `authorization_unavailable` |
| 3 | Element Plus：自研 8 原语 vs 按需保留 Table + DatePicker | V5 | **自研** |
| 4 | 「办待办」是否预留入口（依赖 C-1 未建模） | F4 | **不预留** |
| 5 | 管理视图可见性（C-3 假权限未解） | F5a | 上线前对所有人隐藏 |
| 6 | 数据集 / artifact 删除 API（R8 / B-10） | F5a、F7 | 前端不做假删除 |

---

## 6. 完成度快照（2026-09-15 实测，勿凭印象填写）

F1–F7、V1–V6 **执行进度 0**。逐项证据：`ChartViewer.vue` 无 `createObjectURL`；`ChatPanel.vue` 仍有 `renderMd`；`lib/api.js` 无 401 响应拦截；侧栏仍是「总览 / 文档 / 数据 / 洞察 / 图谱 / 审批 / 对话」七个；`InsightPanel.vue` 仍手填阈值 + 演示数据；`ApprovalPanel.vue` 仍 `standard: 500`；`ChatPanel.vue` 仍用 `eb_sessions_v2`；`theme.css` 3393 行 / `.reference-login` 149 处；无 `router/`、无 `components/ui/`；`package.json` 仍挂 `element-plus`。

每完成一步，把本节的对应证据改成「已消除」并附 commit 号，不要只改勾。
