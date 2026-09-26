# 2026-09-26 · V1 前端线缺口清单（员工使用视角）— R265

- **单号**：R265（执行层）· 工作树 `be-r265` · 分支 `codex/be-r265` · 基点 `8613dc7`。
- **性质**：取证单。**零代码改动**，本文件是本单唯一产物（新建）。
- **行号口径**：以下所有 `文件:行` 一律锚 commit `8613dc7`，不锚工作树（主树是共享树，行号会漂）。
- **实测时间**：2026-09-26 11:48 (+08:00)，`node v24.13.0` / `npm 11.6.2`。
- **不引用旧结论**：计划书 §6.1 的状态词全部按今天的源码重核（§3），每条缺口都带 `文件:行` 或命令输出。

---

## 0. 一句话结论

八项对账里 **三格状态词已过期**（自研 UI 原语、三屏 SLO 契约、图谱降级承接），三条硬判据里 **一条今天实测不成立**（界面无技术注解：3 处技术文案确实上屏）。
- 从员工视角看今天**办得完**的：提问拿答案并看到出处、点开原文核对、批待办、被拒绝时看得懂人话。
- 今天**办不完**的四件事：我传的文档到底能不能被问到 / 我报的数据是谁传的 / 告警看到了怎么办完 / 换台机器我的历史在哪。
- 缺口 **20 条（P1 十一条）**，按写集归成 **8 块**，合计约 **12–12.5 人日**；只做 P1 约 **9 人日**。

---

## 1. 判据① · 员工一天的事 × 现状（有 / 无 / 半）

任务表取自计划书 §1 角色旅程（`docs/frontend-plan-2026-09-14.md:53-118`）与 §2 视图映射（同文件 `:121-135`），逐条到 09-26 的页面与 `docs/api/contract-v1.md` 上对。

| # | 员工要办的事 | 判定 | 半在哪 / 证据 |
|---|---|---|---|
| T1 | 提问 → 拿答案 → 看到出处并点开核对原文 | **有** | 出处卡可点：`frontend/src/components/SourceCard.vue:91-97`（按钮文案「打开原文：文件名」→ 抛 preview 事件），预览与下载走受控接口：`ChatPanel.vue:1181`、`:1211`；首屏线索卡带密级：`AnswerHeadlineCard.vue:90`；来源反馈信号：`SourceCard.vue:114-131` |
| T2 | 上传文档 → 知道「多久能被问到」 | **半** | 未索引有脸、**已索引没有脸**：`DocPanel.vue:99-105`（注释即裁定「indexed 不涂」），模板只在 excluded 时画状态：`:460-464`；上传结束后只在收尾时刷一次列表，不轮询：`:206-246`；`POST /upload` 的 classification Form 字段前端从不发：`app/api/v1/chat.py:3768` |
| T3 | 查自己报的数据（我传过什么、谁的） | **半** | 数据文件行的全部字段是 `filename/size/size_label/modified_at/extension/dataset_id/version_id/classification`（`app/api/v1/data.py:221-236`）——**没有归属人**，界面无从显示「我传的」；文档行后端已给 `owner_id`/`size_bytes`/`parse_status`（`app/documents/catalog.py:236-238`），界面一行都不显示（`DocPanel.vue:444-465`） |
| T4 | 看图与报告（成果找回） | **半** | 对话内图 ✅（`ChatPanel.vue:1420` 挂 ChartViewer，带 Bearer 取 blob：`lib/artifacts.js:43`）；成果列表 ✅ 存在但**只有一个挂载点：喂料 → 数据标签之下**（`DataPanel.vue:451`，全仓 ArtifactList 无第二处引用）；计划书 §2 的「交成果」独立视图 0 屏：`router/index.js:52-99` |
| T5 | 处理待批 | **有** | 真挂起账本 + 分页 + 期限 + 失败轮：`components/hitl/HitlPendingPanel.vue:592-683`、`HitlPendingRow.vue:117`（「超过 … 就不再算挂着」）；对话内同一个 resolver：`ChatPanel.vue:1472-1473` |
| T6 | 处理告警 | **半** | 能读列表 / 改规则 / 手跑一次巡检：`lib/alerts.js:22-24`、`InsightPanel.vue:8-11`。**不能确认、不能关闭、不能指派、看不到单条详情**：`app/api/v1/alerts.py:961,982,993,1004` 四枚端点在前端 **0 消费者**；`mapAlertRow` 只取 5 个键（`lib/alerts.js:168-178`），而 alerts 表早已有 `status / acknowledged_by / acknowledged_at / closed_by / assignee / assigned_at`（`app/api/v1/alerts.py:114-121`）→ 两个人处理同一条告警，彼此看不见 |
| T7 | 被拒时知道下一步做什么 | **半** | 好的那半：稳定码一律洗成人话且带下一步（`lib/errcodes.js:135`、`lib/provenance.js:130`），失败与空态两张脸（`InsightPanel.vue:13-17`、`lib/alerts.js:164-166`）。坏的那半见 **G09 / G13 / G19**：`department_scope_required` 那句「请先选择部门范围」（`lib/errcodes.js:105`）指向**界面上不存在的**部门选择器 |
| T8 | 登录 / 换密码 / 找回账号 | **半** | 全屏登录 ✅（§4.1）；「忘记密码」弹窗把员工指向「管理员在**用户管理**中重置」（`App.vue:348`），而**这一屏不存在**（§4.3：`GET /users` 前端 0 消费者）；`PUT /users/password`、`GET/PUT /profile`（`app/api/v1/auth.py:115,155,163`）前端 0 消费者 → 员工改不了自己密码，也看不到自己的部门归属，而部门恰恰决定他能不能问出答案 |
| T9 | 换个地方接着问（历史跟着人走） | **半** | 会话列表**只从 localStorage 组装**（`lib/sessions.js:93-113`），退出时整包清空（`App.vue:183-197` + `lib/sessions.js:176-191`）；`GET /sessions` 今天已经回 `id/title/created_at/updated_at/msg_count`（`app/api/v1/chat.py:920-937`、表结构 `:1473-1479`），前端只把它用于**深链回放**（`ChatPanel.vue:226`）与**待办归属核对**（`HitlPendingPanel.vue:422`）→ 换机器 / 清缓存 / 被 401 踢下去的那一刻，后端还在的会话一条都回不来 |
| T10 | 在对话里知道「这一问用的是哪张表」并能改 | **无** | `activeDataFilename` 全仓只出现在脚本态（`lib/sessions.js:20,70,87,129,137,186,861`、`ChatPanel.vue:245,485-489,567,574,599`），**没有一个模板引用它** → 计划书 §2 的「数据上下文选择器常驻顶栏」与 J4 断点（`docs/frontend-plan-2026-09-14.md:80-83`）今天仍未销 |
| T11 | 机器不健康时别骗我 | **半** | 前端只判一枚码：`lib/health.js:57`。后端还会说 `embedding_model_missing`（`app/common/monitoring.py:146`）、`queue_unavailable`（`:133`）、`*_read_only`（`:131`），并单列 `model.inference_compute / _detail / _error_code`（`:215-217`）→ 前端 **0 消费者**：embedding 不在时顶栏仍是绿点 +「本地模型就绪」（`lib/health.js:62-66`）。这正是计划书 §6.1 那行「缺 embedding / 无 GPU 两张脸」的 today 状态 |

> 计划书 §2 承诺「5 主视图 + 1 管理视图」：主视图 5 枚在树（总览 / 喂料 / 异常与告警 / 审批与待办 / 问一句，`router/index.js:58-87`），**管理视图整屏不存在**（见 G10）。
---

## 2. 判据② · 缺口怎么补（只给文件清单与字段，不写实现）

每条缺口在 §6 里给两行：**动** = 要动的文件（含会被撞到的测试件），**字段** = 要哪个接口字段（标 `已有` 即零后端改动）。本单不写任何实现，也不改任何现有文件。

---

## 3. 判据③ · 计划书 §6.1 八项逐条对账

原表：`docs/handoff/2026-09-17-perf-architecture-plan.md:381-391`。右列为 09-26 实取。

| 项 | 计划书停在 | 今天的实真 | 证据 |
|---|---|---|---|
| 洞察 →「异常与告警」 | 已完成 | ✅ **已完成** | `frontend/src/router/index.js:73` 定名；页内同名 `InsightPanel.vue:243`；数据源已是真链 `lib/alerts.js:22-24` |
| 审批 →「报销自查」 | 已完成 | ✅ **已完成，且定名已二次更正** | 这一屏今天叫「审批与待办」（`router/index.js:81`，理由见 `:78-80` 的 R174③ 注释）；「报销」二字不得再作任何一屏的名字已被钉成用例：`components/__tests__/r174-screen-name.test.js:38-45` |
| 四张脸分开（无权限/空/降级/错误） | 已完成；缺 embedding / 无 GPU 两张脸仍未分 | ❌ **那半张今天仍缺（计划书这句今天仍然对）** | `lib/health.js:57` 只认 model_not_available；embedding_model_missing（`app/common/monitoring.py:146`）与 model.inference_compute 三键（`:215-217`）前端 0 消费者 → **G07** |
| Element Plus 移除 | 已完成 | ✅ **已完成** | 命令 `cd frontend; rg -c element-plus package.json` → **0 命中**；依赖清单实读 `frontend/package.json:12-25` |
| **自研 UI 原语（写「进行中」）** | 进行中 | ⚠️ **状态词对、内容已换：不是没写完，是写完了没接线** | 12 枚原语在树（命令 `cd frontend; (Get-ChildItem src/components/ui/Ui*.vue).Count` → 12）；**零屏幕消费者 4 枚**：UiTable / UiUpload（只被 `ui/` 自身与用例引用）、UiDialog / UiToastHost（全仓只剩 `assets/theme.css:116` 提过一次）。裸 button 计数：ChatPanel 10、DashboardPanel 9、DocPanel 5、DataPanel 5、GraphPanel 2 → 接线缺口并入 **G20**（记在块 E/块 F 写集里，不另立单） |
| **图谱撤一级入口** | 已完成 | ✅ 撤入口已完成 / ❌ **降级承接没建** | 撤：`router/index.js:97` primary:false，导航派生 `:123`。承接：计划书 `docs/frontend-plan-2026-09-14.md:129` 承诺的「文档预览里的 依据 / 相关制度 子视图」在 `DocumentPreviewModal.vue` **0 命中**（命令 `cd frontend; rg 依据|相关制度 src` 命中全落在 errcodes/devFixtures 注释里）；`GraphPanel.vue:84-95` 仍是四个输入框 + 关系列表 → **G12** |
| 前端路由 | 已完成 | ✅ **已完成** | `router/index.js` 是屏↔URL 唯一真源、侧栏导航是它的派生视图（`:123-128`）；`App.vue:409` KeepAlive 的 cachedScreens 由路由表算出（`router/index.js:152-154`） |
| **三屏 SLO 契约（写「未做」）** | 未做·已拆两半（R105 甲/乙） | ⚠️ **已过期：甲半已完成，乙半仍挂，另有一格从没记过** | 甲半：契约段已进 `docs/api/contract-v1.md:1539`（Three-Tier SLO Contract, 2026-09-20, R105 甲半），闸在 `app/api/v1/observability.py:727`（MIN_SLO_SAMPLES = 100）+ `:1041`（slo_readout）+ `:1130`（GET /slo）。乙半：lane_attribution_absent 仍逐条挂在 blocker（`:895,906,940,949,969,1115`）。**没记过的那格**：GET /slo 与 GET /stage-latency 在前端 0 消费者（命令 `cd frontend; rg -F stage-latency src` → 无命中，exit 1）→ **G10**

**对账净结论**：八项 = ✅ 五项、❌ 一项（四张脸那半张）、⚠️ 两项状态词过期（自研原语、SLO 甲半）。另有两笔计划书自己没记的账：**图谱降级承接**（G12）与 **SLO 读出面在界面上一处都没有**（G10）。
---

## 4. 判据④ · 计划书 §2 三条硬判据实测

判据出处：`docs/frontend-plan-2026-09-14.md` §11 验收清单（`:550-599`）+ 计划书 §2 视图映射；计划书 `2026-09-17-perf-architecture-plan.md:395` 把这三条统称「其余 V 线判据」。**注意**：那行写「见 frontend-plan §2」，而 §2（`:121-143`）实际是工作区映射表，三条判据的真正落点是 §11 与 §4.5（`:239`）—— 指路已过期，另记一笔（G21）。

### 4.1 全屏登录 → ✅ 成立

- 结构上互斥：登录是 `App.vue:230` 的 `main v-if=!isLoggedIn`，工作台是 `App.vue:353` 的 `v-else`，**未登录时工作台整棵子树不挂载**，面板与请求都不会发。
- 铺满视口：`assets/theme.css:1154-1164` `.login-v2 { position: relative; display: grid; grid-template-rows: auto 1fr auto; min-height: 100dvh; overflow: hidden }`，外层 `.app-root { min-height: 100dvh }`（`theme.css:174-176`）。
- 视觉回归已有件：`frontend/tests/visual/login-viewports.spec.js`（五档视口，含 3440×1440 与 1280×720）。

### 4.2 界面不得出现「来自 xx 接口」类技术注解 → ❌ 不成立（3 处确实上屏）

取证命令与命中数（在 `frontend/` 下跑）：

```bash
rg -n --no-heading "(src/[A-Za-z0-9_./-]+\.js|GET /[a-z]|POST /[a-z])" src/components --glob "*.vue"   # 命中 29
```
- 29 命中里 26 处在源码注释（写给人看的实现说明，不上屏）
- 肉眼逐条筛后**确实渲染给员工**的是 3 处：

| # | 位置 | 上屏原文（片段） | 为什么算违规 |
|---|---|---|---|
| 1 | `frontend/src/components/DashboardPanel.vue:175` | 「…仍是前端常量 src/devFixtures/dashboard-demo.js，不来自任何接口。上面四个数字改为读服务端聚合 **GET /api/v1/dashboard/summary**…」 | 员工屏幕上出现**前端源码路径 + HTTP 方法与路由** |
| 2 | `frontend/src/components/ApprovalPanel.vue:168` | 「预审参数…来自前端常量 **src/devFixtures/approval-demo.js**…」 | 同上（源码路径） |
| 3 | `frontend/src/components/ApprovalPanel.vue:182` | 「挂起待办这一屏读的是服务端挂起账本（**GET /hitl/pending**）…」 | 同上（路由名） |

- 三处全在 `<template>` 内、无条件渲染分支里（`DashboardPanel.vue:171` 起是加载成功分支），`data-testid` 分别叫 `dashboard-demo-flag` / `approval-demo-flag` / `approval-scope-note`。
- 对照组（说明这判据别的屏做得到）：`SourceCard.vue`、`QueueFace.vue`、`lib/errcodes.js` 一律把后端原串收进视图模型再说话，未知码只允许「错误码：xxx」小字（`components/ui/README.md:27`，并由 `lib/no-bare-code.test.js` 全仓扫）→ **G13**。

### 4.3 管理视图对 staff 不可见 → ✅ 形式成立（因为这一屏根本不存在）

- 命令 `cd frontend; rg -n users src` → 3 命中，全部在测试/用例里，**`GET/POST/DELETE /users`、`PUT /users/password`、`GET/PUT /profile`、`GET /audit/events`、`GET /evaluations`、`GET /traces/{id}`、`POST /retrieval/debug` 前端 0 消费者**；路由表里也没有管理屏（`router/index.js:52-99`）。
- 结论：这条判据今天**平凡为真**，但它是靠「没做」为真的，不是靠「藏好」为真 —— 一旦补管理屏就必须重测。
- 同时暴露两笔：**(a)** 登录页把员工指向不存在的用户管理（`App.vue:348`，见 G10）；**(b)** 现有唯一一处角色控制仍读客户端态：`App.vue:82` `userRole.value = localStorage.getItem(ROLE_KEY) || staff`，派给「喂料」屏后 `DocPanel.vue:37` 用它开批量删除。角色集只决定按钮可见性，后端一律真判（`app/api/v1/alerts.py:925` 等），**越权面为零**，但这就是计划书 J5 说过的**假权限**（`docs/frontend-plan-2026-09-14.md:85`）：员工改一下 `eb_role` 就能看见管理员选择框。

---

## 5. 判据⑤ · 三组实测数（2026-09-26 11:48 +08:00）

| 项 | 命令 | 读数 | 时间戳 |
|---|---|---|---|
| 单测全量 | `cd frontend; npx vitest run --fsModuleCache --fsModuleCachePath tmp/vc-r265` | **Test Files 58 passed (58) / Tests 1160 passed (1160) / failed 0**，Duration 3.19s | 11:48:04 起跑 |
| 构建 | `cd frontend; npm run build` | **退出码 0**，`✓ built in 365ms`；产物 `dist/assets/index-*.js 352.59 kB`（gzip 124.62）、`index-*.css 129.46 kB`（gzip 28.18）、`login-bg 108.90 kB` + `workbench-bg 7.12 kB` | 11:48:16 → 11:48:17 |
| 色值门 | `cd frontend; npm run lint:colors` | **148 problems (0 errors, 148 warnings)**，退出码 0 —— 与工单给的现值 **148** 逐字相同，未新增裸色值 | 11:48:22 |

**缓存隔离这件事：部分未做到，如实记**

- 工单给的 `--cacheDir <树>/tmp/vc-r265` 在本仓 vitest **不被接受**：实跑报 `CACError: Unknown option --cacheDir`（vitest 5 已删该开关）。等价开关是 `--fsModuleCache --fsModuleCachePath`（默认 `node_modules/.vitest-cache`），本班按此执行，缓存在本班树内 `frontend/tmp/vc-r265`，跑完已清（`git status --short` 交付前为空）。
- 但仍有一处**做不到隔离**：`node_modules` 是 Junction 指向主树（`Get-Item frontend 下的 node_modules | LinkType` → Junction），vitest 的结果缓存 `node_modules/.vite/vitest/<hash>/results.json` 走的是主树那份 —— 本班跑完后该文件 LastWriteTime 为 **11:57:04**（晚于本班 11:48 的跑次），即**同机另一枚 Agent 的 vitest 正在写同一枚文件**。
- 影响判定：`results.json` 只服务 changed/排序，本班跑的是 `vitest run` 全量，**58 files / 1160 tests 与 0 failed 这三个读数不受它影响**；若日后要用 `--changed` 取样，必须先把 node_modules 改为各自独立目录，不能只靠命令行开关。

---

## 5.1 附带实测：产物零远程请求（判据「内网别给我看转圈的字体」）

- 命令：`cd frontend; rg -o -n "https?://[^ ,);]" dist/assets/index-*.css` → **1 命中**，值为 `http://www.w3.org/2000/svg`（SVG 命名空间字符串，不发请求）。
- 结论：**零远程字体/CDN 请求** ✅（与 R148 记录一致，今天仍成立）。
---

## 6. 缺口清单（20 枚 + 2 枚记账项）

优先级口径：**P1 = 挡 V1 门槛或构成屏上假话**，P2 = 明显缺口但不挡 V1，P3 = 打磨。
「动」只列文件，不写实现；字段标 **已有** 表示零后端改动（读路径或请求体里今天就有）。

### P1（11 枚）

| # | 员工视角的症状 | 现状证据 | 动（文件） | 要哪个接口字段 |
|---|---|---|---|---|
| **G01** | 传完文档只知道「上传完成」，**不知道这篇能不能被问到** | `DocPanel.vue:99-105` 裁定 indexed 不涂；模板只在 excluded 画脸 `:460-464`；收尾只刷一次列表 `:206-246` | `components/DocPanel.vue`；`components/__tests__/r237-r49-index-face.test.js`、`panel-states.test.js` | **已有**：catalog 行 `index_status=indexed`、`parse_status`（`app/documents/catalog.py:238-257`）。缺的是一枚「已可检索」正脸，不是字段 |
| **G02** | 总览上每篇文档都写着「已解析」、指标口径永远「高可信」 | 写死字串：`DashboardPanel.vue:281-282`（每行都标 知识库 · 已解析 / 已解析）、`:307`（`<b>高可信</b>`） | `components/DashboardPanel.vue`；`components/__tests__/dashboard-summary.test.js`、`v7-fake-data.test.js` | **已有**：`parse_status`/`index_status`（catalog）、`definition_source` 与 `context.warning` 与 `provenance`（`app/api/v1/intelligence.py:283-290`） |
| **G03** | 问出来的数和页面上选的表**对不上，也无从纠正**（J4） | `activeDataFilename` 无任何模板引用（引用面见 §1 T10） | `components/ChatPanel.vue`（回显 + 就地改表）、`App.vue`（若按计划书放顶栏常驻）、`lib/sessions.js`（只读）；用例 `components/__tests__/r174-*`、`panel-states.test.js` | 上行已有 `data_filename`（`ChatPanel.vue:599`）；**回显要后端补**：canonical `sources`/done 帧里带本轮真正用的 `data_filename`（今天流里没有） |
| **G04** | 换台电脑 / 被登出一次，**问过的话全不见了**（后端其实还在） | 列表只从 localStorage 组装 `lib/sessions.js:93-113`；退出整包清 `App.vue:183-197` | `components/ChatPanel.vue`（会话侧栏加「从服务器取回」）、`lib/sessions.js`（列表合并读取）；用例 `lib/sessions-error-text.test.js`、`components/__tests__/r174-replay-ownership.test.js` | **已有**：`GET /sessions` 回 `id/title/created_at/updated_at/msg_count`（`app/api/v1/chat.py:920-937`）→ 零后端改动 |
| **G05** | 告警看到了**没法办**：不能确认、不能关闭、不能指派，也看不出别人是不是已经办过 | 四枚端点 0 消费者（`app/api/v1/alerts.py:961,982,993,1004`）；`mapAlertRow` 只取 5 键（`lib/alerts.js:168-178`），注释仍写「后端六列」（`:164`，实为 13 列） | `lib/alerts.js`、`components/InsightPanel.vue`；用例 `components/__tests__/insight-alerts.test.js` | **已有**：`GET /alerts` 行里 `status/acknowledged_by/acknowledged_at/closed_by/closed_at/assignee/assigned_at`（`app/api/v1/alerts.py:114-121`）+ `POST /alerts/{id}/ack|close|assign` |
| **G06** | 被排队那一轮**只能干等**，界面没有「不排了」 | QueueFace 只有 retry 与 action 两枚按钮（`QueueFace.vue:38-56`）；`POST /queue/{request_id}/cancel`（`app/api/v1/chat.py:4380`）**前端 0 消费者**；现「中断本次回答」走的是另一条腿 `/ask/{session}/cancel`（`ChatPanel.vue:692`） | `components/QueueFace.vue`、`components/ChatPanel.vue`；用例 `__tests__/r198-queue-poll-stop.test.js`、`r202-queue-poll-stop-authz.test.js`、`r221-queue-deadline.test.js`、`r260-queue-awaiting-approval.test.js` | **已有**：request_id 已在 queued 回执里（`lib/sessions.js:389-397`），cancel 端点已在契约 |
| **G07** | 模型/embedding 不在时界面**仍然报绿**，答案质量崩了却没有解释 | `lib/health.js:57` 只认 model_not_available；`embedding_model_missing`（`app/common/monitoring.py:146`）、`queue_unavailable`（`:133`）、`*_read_only`（`:131`）、`model.inference_compute*`（`:215-217`）全部无人读 | `lib/health.js`、`components/ChatPanel.vue`（状态位文案）、`App.vue`（若做全站降级横幅，与 G16 同写集）；用例 `components/__tests__/chat-model-status.test.js` | **已有**：`GET /health/details` 的 `problems[]` 与 `model.inference_compute / _detail / _error_code / _age_seconds`、`embedding`（`app/common/monitoring.py:228-244`）。「无 GPU 那张脸」缺的是**码**：inference_compute_error_code 已有具名读数，前端接上即可，不必后端新造 |
| **G08** | 上传时**没人问密级**，全库默认 1 级；员工想给一份资料加密级，界面没有地方 | 表单只 append file：`DocPanel.vue:216-217`；后端 `classification: int = Form(1)`（`app/api/v1/chat.py:3768`）；department 由服务端按 principal 定（`:3785`，这是对的，别动） | `components/DocPanel.vue`（+ 顺带把 UiUpload 接上，见 G20）；用例 `components/ui/__tests__/upload-rules.test.js`、`panel-states.test.js`、`r151-legacy-colors.test.js`（若动样式） | **已有**：`POST /upload` 的 `classification` Form。**建议同时给一枚读回**：上传回执里回 `classification` 与最终 `department`（今天回的是 status/message） |
| **G09** | 普通员工一进「审批与待办」就看到**「没有权限做审批预审」**——真实原因是界面替他填了别人的部门 | 表单默认值取演示常量 `ApprovalPanel.vue:16,33`（`approval-demo.js:11-14` 里 department 市场部），挂载即自动预审 `:146`（并被用例钉着：`r237-r40-standard-auto.test.js:400`）；后端拒收他人部门 403 `department_override_denied`（`app/common/authorization.py:84-100`）；前端把这一枚 403 一律画成无权限（`ApprovalPanel.vue:138-140`，用例 `r237-r40-standard-auto.test.js:387-399`） | `components/ApprovalPanel.vue`、`devFixtures/approval-demo.js`；用例 `r237-r40-standard-auto.test.js`、`r247-approval-mount-dedupe.test.js`；`lib/errcodes.js`（把 department_override_denied 收进字典，今天 0 命中） | **已有**：登录响应 `department`（`lib/http.js:53` 已存 eb_department）；后端 `verify_department_self_report` 允许「重复自己」或留空（`authorization.py:89-90`）→ 界面只要不替员工填别人的部门就成立 |
| **G14** | 总览上有一条**画着金额的折线图**和一张「异常与风险」清单，数全是前端常量编的；这一屏还继续把自己造的 rows 送给后端算 | `DashboardPanel.vue:6` 引入三枚演示常量、`:125-128` 仍 `POST /dashboard` 送 `rows: demoRows, insights: demoInsights`、`:206-248` 折线卡（纵轴刻度 `:221-223` 由演示常量算出）、`:250-267` 异常卡；判据：计划书 §11「B-7 未落地时没有趋势线」（`:568`）+ J7 裁定（`docs/frontend-plan-2026-09-14.md:116`、`:568`）；`GET /dashboard/summary` 今天只有计数、没有时间序列（`app/api/v1/dashboard.py:3,56,60-74`） | `components/DashboardPanel.vue`、`devFixtures/dashboard-demo.js`；用例 `components/__tests__/v7-fake-data.test.js`（`:70-72` 钉引用面清单、`:104` 钉 demo-flag 计数）、`dashboard-summary.test.js` | 趋势要 **B-7 最小聚合**：`/dashboard/summary` 需新增 `trend[]`（元素 `period/department/metric/value`，今天无此键）。**B-7 落地前先删卡画空态**，不留假线 |
| **G13** | 员工在屏幕上读到**源码路径与 HTTP 路由**（违反 §2 硬判据） | 三处上屏：`DashboardPanel.vue:175`、`ApprovalPanel.vue:168`、`ApprovalPanel.vue:182`（取证与筛法见 §4.2） | `components/DashboardPanel.vue`、`components/ApprovalPanel.vue`；用例 `components/__tests__/v7-fake-data.test.js:104`（钉 demo-flag 计数）、`r237-r40-standard-auto.test.js:403-405`（丁3 钉「这块仍挂牌」） | 无需接口 |

### P2（5 枚）

| # | 症状 | 证据 | 动 | 字段 |
|---|---|---|---|---|
| **G10** | 管理员**没有任何管理屏**：用户/改密/审计/评测/SLO/检索调试全都在后端躺着；而登录页已经把员工指向「用户管理」 | `rg users src` → 0 消费者（§4.3）；`GET /slo`、`GET /stage-latency`、`GET /audit/events`、`GET /evaluations`、`GET /traces/{id}`、`POST /retrieval/debug` 前端 0 消费者；文案落点 `App.vue:348` | 新屏 `components/AdminPanel.vue`（或按能力拆两三枚）、`router/index.js`（加一条 primary 屏 + 角色可见性判定）、`App.vue`（入口与派生导航）、`lib/` 新只读模块；用例 `router/__tests__/routes.test.js`、`src/__tests__/navigation.test.js` | 已有端点即可开工（只读优先：audit/events、slo、evaluations）；**先要一枚后端读回**：`GET /users` 是否已回 `department`（决定管理屏能不能真把 G19 那句「选部门范围」办成） |
| **G11** | 图和报告**藏在「喂料 → 数据」标签底下**，员工找不回来 | ArtifactList 唯一挂载点 `DataPanel.vue:451`；路由表无成果屏 `router/index.js:52-99` | `router/index.js`、`components/DataPanel.vue`（摘出挂载）、`components/ArtifactList.vue`（提为屏时改页头与筛选）、`App.vue`（导航派生）；用例 `components/__tests__/artifact-list.test.js`、`router/__tests__/routes.test.js` | **已有**：`GET /artifacts` 分页（`app/api/v1/artifacts.py:168`），前端已按 `artifactTypeLabel` 分类型（`ArtifactList.vue:36-48`）。若要「按会话找回」需 `request_id`/`session_id` 进列表行 |
| **G16** | 顶栏两枚**按了没反应**的按钮（搜索、通知），退出那颗是个「⌄」看不出是退出 | `App.vue:394-401`：两枚 button 无 @click，退出按钮无可及名称（内容只有 ⌄）——计划书 §11「顶栏无死控件；退出按钮有可及名称」（`docs/frontend-plan-2026-09-14.md:592`）今天不成立 | `App.vue`；用例 `src/__tests__/navigation.test.js` 或新增顶栏件 | 通知若要真数：`GET /hitl/pending` 的 `count`（**不能当总数用**，契约 `docs/api/contract-v1.md` HITL 一节明写它是一页长度）；搜索今天**无全局检索端点**，建议先摘控件而不是接半截 |
| **G19** | 被部门问题拒绝时，界面叫用户**去做一件界面里做不到的事** | 文案 `lib/errcodes.js:105`「请先选择部门范围，再生成这项结果。」；全站无部门选择器（`rg 部门 src/components` 只剩报销自查那一格输入框） | `lib/errcodes.js`（改成能做到的下一步：找管理员核对部门归属）、`lib/errcodes.test.js`、`lib/r208-alias-coverage.test.js`、`lib/no-bare-code.test.js` | 无需接口。真要给「选择部门范围」的能力属后端语义（Principal 的部门集），归 G10 一并裁 |
| **G20** | 「自研原语」写完了但**接线没收口**：4 枚原语零消费者，5 块屏仍在裸写按钮 | 零消费者：UiTable / UiUpload / UiDialog / UiToastHost（§3 行 5 命令）；裸 button 计数 ChatPanel 10、DashboardPanel 9、DocPanel 5、DataPanel 5、GraphPanel 2 | 分屏接线，各自落在所在块写集里（H/D/E/F）；用例 `components/ui/__tests__/components.test.js`、`states.test.js` | 无需接口 |

### P3（4 枚）

| # | 症状 | 证据 | 动 |
|---|---|---|---|
| **G12** | 图谱降级承诺的承接面不存在：一级入口撤了，「文档预览里的 依据 / 相关制度」没建，/graph 变成只能手输三元组的表单页 | `router/index.js:97` primary:false（撤 ✅）；`DocumentPreviewModal.vue` 无依据/相关制度 0 命中；`GraphPanel.vue:84-95` 仍是四输入框 + 列表；生产未配 `KNOWLEDGE_GRAPH_STORE_PATH` 时写入必拒（计划书 `2026-09-17-perf-architecture-plan.md:393`） | `components/DocumentPreviewModal.vue`、`components/GraphPanel.vue`（复用其行读法）；用例 `panel-states.test.js`、`__tests__/r191-modal-row-scope.test.js`（弹窗形状） |
| **G15** | 删除文档 / 删除会话用**浏览器原生 confirm**，与全站两步确认并存 | `DocPanel.vue:281`、`ChatPanel.vue:448`（原生 confirm 全仓仅这 2 处，`rg confirm\(`）；同一仓已有两步确认状态机：`lib/alerts.js:201-205`、`ArtifactList.vue:141-153` | `components/DocPanel.vue`、`components/ChatPanel.vue`（接 UiDialog，见 G20） |
| **G17** | 同一屏两个名字：路由叫「问一句」页内叫「智能问答」，路由叫「喂料」页内叫「知识库」 | `router/index.js:87` vs `ChatPanel.vue:1324`；`router/index.js:67` vs `DocPanel.vue:335`。R136/R174 那条病（页内与顶栏各写一份）今天只钉住了审批一屏：`r174-screen-name.test.js:58-62` 只对 approval 断言 | `ChatPanel.vue`、`DocPanel.vue`（文案）+ 把 `components/__tests__/r174-screen-name.test.js` 的断言从 1 屏扩到 5 屏（这条一扩，四块屏立刻自证） |
| **G18** | 屏头挂英文装饰字（Approval / Alerts / Knowledge Graph），员工读到的是半中半英 | `ApprovalPanel.vue:153`、`InsightPanel.vue:242`、`GraphPanel.vue:76`（样式 `theme.css:178-184` .eyebrow） | 三块屏各一行文案；**不许顺手改 theme.css**（写集独占见 §7） |

### 记账项（不算缺口，别派工）

| # | 内容 |
|---|---|
| **G21** | 计划书 `2026-09-17-perf-architecture-plan.md:395` 把三条硬判据指到 `docs/frontend-plan-2026-09-14.md` §2，而 §2（`:121-143`）是工作区映射表，三条判据实落在 §11（`:550-573`）与 §4.5 —— 指路过期。计划书是 **R262 的写域**，本单不动，只报。 |
| **G22** | §6.1 那行「Element Plus 移除 [实测]」今天仍为真（0 命中），但 `docs/current-functionality-2026-09-10.md:335-349` 的 6.4「当前前端能力」还写着「上传进度显示 / 解析入库状态显示」这种笼统口径，掩盖了本单 G01/G08 的真缺口。该文档 09-10 快照，本单不判它过期，只登记。 |

---

## 7. 判据⑥ · 可直接派工的拆解（按写集切块）

**分块的唯一依据是写集**：同一枚文件（含同一枚测试件）只允许一枚 Agent 持有。并行度可达 5，**两处硬串行**与**四处全局独占**如下。

### 7.1 全局独占（谁都不许顺手碰）

| 文件 | 独占块 | 理由 |
|---|---|---|
| `frontend/src/assets/theme.css` | **块 F** | 全站唯一样式真源；其余七块一律「零新增样式」开工（要新组件用现成原语）。否则八块排队改一枚 CSS，且 `--max-warnings=148` 这道门会被同时改写 |
| `frontend/package.json` | **块 F** | `lint:colors` 的 148 预算是棘轮：`components/__tests__/r151-legacy-colors.test.js:152-158` 钉「只准降不准升（<334 且 ≥7）」。任何一块想调预算都必须先并树到 F 之后 |
| `frontend/src/components/__tests__/panel-states.test.js` | **块 E** | 这枚件一次 import 全部八块面板（`:16-23`），任何面板改状态形状都会撞它；只留一块持有，其余块要新断言就另立 `r26x-*.test.js` |
| `frontend/src/components/__tests__/r151-legacy-colors.test.js` + 那四份 style 段（DocPanel / DataPanel / DocumentPreviewModal / ChartViewer） | **块 E** | 台账按「文件 + 属性 + 旧值 + 新值」逐条记账（`:44-45` LEDGER/DELETED），改这四份的 `<style>` 必须先更台账；块 H 只许动 template/script |

另有一条**不许写进代码的门**：每块交付都必须是 `npm run lint:colors` 仍 **148 / 0 errors**（新增裸色值 0 命中），不许靠调预算过关。

### 7.2 八块清单

| 块 | 收的缺口 | 独占写集 | 一句可验判据 | 粗估 |
|---|---|---|---|---|
| **A 总览归真** | G14、G02、G13（DashboardPanel 那半） | `DashboardPanel.vue`、`devFixtures/dashboard-demo.js`、`v7-fake-data.test.js`、`dashboard-summary.test.js` | 员工打开总览：**屏上不再有任何一条折线或金额来自前端常量**（`rg -n demoTrendShape|demoInsights|demoRows src` → 0 命中），最新文档每行显示的是 `parse_status`/`index_status` 的真值，「高可信」那格改为读 `definition_source`/`warning`；B-7 未落地时趋势卡为**空态**而非假线 | 1.5 人日 |
| **B 自查归真** | G09、G13（ApprovalPanel 那两处）、G18（Approval 头） | `ApprovalPanel.vue`、`devFixtures/approval-demo.js`、`r237-r40-standard-auto.test.js`、`r247-approval-mount-dedupe.test.js`、`lib/errcodes.js` 的新码位 | 换一个**非市场部**的 staff 账号进「审批与待办」：屏上不再出现「没有权限做审批预审」，部门格默认是本人部门（读 `eb_department`）或留空由服务端补，屏上再无 `src/devFixtures/...` 字样 | 0.5–1 人日 |
| **C 告警闭环** | G05、G18（Alerts 头） | `InsightPanel.vue`、`lib/alerts.js`、`insight-alerts.test.js` | 一条 open 告警能被**就地确认 / 关闭 / 指派**并刷新后仍显示处理人与时间；`mapAlertRow` 读到 `status/acknowledged_*/closed_*/assignee`（不再写「后端六列」），且「无权限 / 空 / 降级 / 错误」四张脸不互相顶替 | 2 人日 |
| **D 对话页四件** | G04、G07、G06、G03、G15（会话那半）、G17（问一句那半）、G20（ChatPanel 裸控件） | `ChatPanel.vue`、`QueueFace.vue`、`lib/sessions.js`、`lib/health.js`、`chat-model-status.test.js`、`r169-cancel-stream.test.js`、`r174-replay-ownership.test.js`、`r198/r202/r221/r260` 四枚排队件、`sessions-error-text.test.js` | 四件各一条：① 换一台干净浏览器登录后点「从服务器取回」能列回会话（标题/时间/问数）；② 后端回 `embedding_model_missing` 或 `inference_compute_error_code` 时，顶栏不许再出现绿点 +「本地模型就绪」；③ 排队中那一轮可取消且取消后状态读数一致；④ 对话每条回答标出本轮用的表并可就地改 | 3 人日（可再拆 D1=D①+④ / D2=D②+③，但两半都要过 `r198/r202` 那组件 ⇒ **只能串行**） |
| **E 喂料归真** | G01、G08、G20（UiUpload/UiTable 接线）、G15（文档删除那半）、G17（喂料/知识库） | `DocPanel.vue`、`DataPanel.vue`、`DocumentPreviewModal.vue`、`ChartViewer.vue`、`components/ui/UiUpload.vue` 与 `upload-rules.js`、`panel-states.test.js`、`r151-legacy-colors.test.js`、`r237-r49-index-face.test.js`、`upload-rules.test.js`、`states.test.js` | 上传一篇制度后**不刷新页面**也能看到它从「解析中」走到「已可检索」，且 indexed 有正脸；上传表单能选密级并发出 `classification`；两处原生 confirm 全部换成应用内确认（`rg -c confirm\( src/components` → 0） | 1.5 人日 |
| **F 壳层与导航** | G16、G11、G10（管理屏骨架）、G20（顶栏）、theme.css 与 package.json 棘轮 | `App.vue`、`router/index.js`、`src/router/nav-focus.js`、`navigation.test.js`、`router/__tests__/*`、`assets/theme.css`、`package.json`、新增 `AdminPanel.vue` + 成果屏 | 顶栏无死控件、退出按钮有可及名称；「交成果」「管系统」两条路由各有 URL 与派生导航项，且 `meta.role`（或等价判据）对 staff 不派生入口——**这条要连后端一起验**，客户端角色仍算假权限（§4.3 b） | 2 人日 |
| **G 错误话术** | G19（+ 把 `department_override_denied` 收进字典，与块 B 同一枚文件须串行） | `lib/errcodes.js`、`errcodes.test.js`、`r208-alias-coverage.test.js`、`r208-dictionary-voice.test.js`、`no-bare-code.test.js` | `rg -n 请先选择部门范围 src/lib/errcodes.js` 改为可执行的下一步；`department_override_denied` 在字典或别名表里有一枚真码，屏上不再一律画成「没有权限」 | 0.5 人日 |
| **H 图谱承接** | G12 | `DocumentPreviewModal.vue`（template/script 部分）、`GraphPanel.vue`、`r191-modal-row-scope.test.js` | 在文档预览里能看到该文档的「依据 / 相关制度」关系行（读 `GET /knowledge-graph/relations`），未开启存储时那句文案说清是「这台服务器没开」而不是「没有依据」 | 1 人日 |

**合计 ≈ 12–12.5 人日**；只做 P1（A + B + C + D 的 ①②④ + E 的 ①② + G13 文案）≈ **9 人日**。

### 7.3 排法（谁必须等谁）

- **可并行 5 路**：A、B、C、D、G 的写集互不相交（除 errcodes.js：B 要新码位、G 要改文案 ⇒ **B 与 G 串行**，让 G 先并树，B 复用 G 的字典出口）。
- **E 与 H 串行**（H 借 DocumentPreviewModal 与 panel-states，两块都有）。
- **F 排最后**（或最早并树后冻结 theme.css/package.json 给其余块）：F 是 App.vue 与 router 的唯一持有者，A–H 任何一块想加屏或加顶栏都要等它。
- 反证钉不动：**每块出门前跑 `python scripts/run_gate.py` 由总控代跑，执行层不 commit**（AGENTS.md 规矩）；本单已实测 58/1160/0 failed 与 148/0 errors 作对照基线。

---

## 8. 交回 · 六条判据逐条

| 判据 | 状态 | 凭据片段 |
|---|---|---|
| ① 从任务出发逐条对有/无/半 | **做到** | §1 表 T1–T11，11 条旅程各给判定与 `文件:行`；四条「办不完」写清半在哪 |
| ② 每条缺口给文件 + 接口字段，不写实现不改文件 | **做到** | §6 三张表每行带「动」「字段」两列；`git status --short` 本单交付前只有本文件一处新增 |
| ③ §6.1 八项逐项对账 + 两枚陈旧状态词核真 | **做到** | §3 表：✅5 / ❌1 / ⚠️2；「自研原语」实为 12 枚在树 + 4 枚零消费者；「三屏 SLO 契约」甲半已进 `contract-v1.md:1539` 与 `observability.py:727/1041/1130`，乙半仍挂 `lane_attribution_absent` |
| ④ 三条硬判据实测 | **做到（一条判据实测为 ❌）** | §4：全屏登录 ✅（`theme.css:1154-1164` + `App.vue:230/353`）；无技术注解 ❌（**3 处上屏**，取证命令与 29 命中筛法在 §4.2）；管理视图对 staff 不可见 ✅ 但属「因为没做所以为真」（§4.3） |
| ⑤ 三组数实测并注时间戳 | **做到（缓存隔离部分做到）** | §5：vitest 58 files / 1160 tests / 0 failed @11:48:04；build exit 0 @11:48:16–17；lint:colors **148 / 0 errors** @11:48:22。缓存：`--cacheDir` 在 vitest 5 不存在（实跑 CACError），改用 `--fsModuleCachePath`；`node_modules/.vite/vitest/…/results.json` 因 junction 仍与另一枚 Agent 共用（11:57:04 有他人写入），已判定不影响全量读数 |
| ⑥ 可派工拆解 + 还差哪几枚、几人日 | **做到** | §7：8 块（A–H）+ 4 处全局独占 + 并行/串行排法；**合计 ≈12–12.5 人日，P1 部分 ≈9 人日** |

**总数**：缺口 **20 条**，其中 **P1 十一条**（G01、G02、G03、G04、G05、G06、G07、G08、G09、G13、G14）、P2 五条（G10、G11、G16、G19、G20）、P3 四条（G12、G15、G17、G18），另有记账两条 G21/G22 不派工。

### 建议先派的三枚

| 顺序 | 派哪块（=单号落点） | 为什么是它 |
|---|---|---|
| 1 | **块 B（G09 + G13 审批那两处）** | 最小的一枚（0.5–1 人日、独占 5 个文件、零后端），却是**演示现场必翻车**的一格：任何非市场部账号一进「审批与待办」就被界面自己塞的部门判成「没有权限」。今天有两条用例（丁2/丁3）把假象钉住了，改的时候连它们一起改判，是本轮性价比最高的写入 |
| 2 | **块 A（G14 + G02 + G13 总览那处）** | 信任级 + 判据级双重命中：老板第一眼看到的是**一条编出来的金额折线**和每篇都「已解析」、口径永远「高可信」。计划书 §11 已把「B-7 未落地不得有趋势线」写成硬约束，判据现成、验收口径现成，且块 A 写完顺手把 `devFixtures/dashboard-demo.js` 清空一半，G13 的三处也掉两处 |
| 3 | **块 D 的 D1 半（G04 会话回得来 + G03 本轮用哪张表）** | 员工视角最疼的两件事，且**零后端**（`GET /sessions` 已把 title/updated_at/msg_count 吐完，只差没人读列表；data_filename 上行已有、只差回显）。放在第三位是因为它撞 `ChatPanel.vue` 与四枚排队用例，写集最重，宜在两枚小单并树、基线稳定后开工 |

---

## 9. 未做到 / 边界（不写「应该、大概、基本」）

1. **判据⑤给的命令没照原样跑成**：`npx vitest run --cacheDir ...` 被 vitest 5 拒绝（`CACError: Unknown option --cacheDir`）。改用等价开关 `--fsModuleCache --fsModuleCachePath tmp/vc-r265` 完成读数；**vitest 的结果缓存目录仍与另一枚 Agent 共用**（junction 指向主树 `node_modules`），无法用命令行隔离，已用「全量跑 + 只看 files/tests/failed 三数」把影响降到零，并留了 LastWriteTime 证据。
2. **没跑 Playwright**：`npm run test:e2e` 会驱动 `dist` 且与另一枚 Agent 抢同一份构建产物，工单也未要求；本单只 `npm run build` 取退出码，未复跑视觉回归（`tests/visual/` 4 枚 spec 存在，R148 记录过 40 passed/25 skipped，**那是旧读数，本单不据以判达标**）。
3. **没跑全量回归门、没起服务、没动容器/镜像、没 commit/push**：按硬约束执行。任何「真机渲染」类判据（如 G4 的 staff 探针、G07 的降级横幅实际观感）本单**只给源码证据，不宣布真机已过**。
4. **未验的三处待验项**（派单时须带）：① `GET /users` 是否已回 `department`（决定 G10 管理屏能否真解决 G19 那句话）；② `POST /upload` 回执是否愿意回 `classification`（G08 的读回）；③ `GET /alerts/{id}` 与 ack/close/assign 三枚端点的请求体形状（G05 我只读到路由与表列，**未逐字段读 handler**）。
5. **写过的两处临时痕迹已清**：`frontend/tmp/vc-r265`（本班 vitest 缓存）与仓库根一枚误写日志，均用 `git clean -f -- <path>` 定点清除，交付前 `git status --short` 只剩本文件（见 §8 判据② 凭据）。
6. **不碰的文件**：`frontend/**`、`app/**`、`tests/**`、评测集、看板、跟进单、计划书（R262 写域）——本单全程只读。

### 附：本单取证命令（可复跑）

```bash
# 三组数
cd frontend; npx vitest run --fsModuleCache --fsModuleCachePath tmp/vc-r265
cd frontend; npm run build; echo $LASTEXITCODE
cd frontend; npm run lint:colors   # 期望 148 problems (0 errors, 148 warnings)

# 判据④-2 技术注解扫描（命中 29，上屏 3）
cd frontend; rg -n --no-heading "(src/[A-Za-z0-9_./-]+\.js|GET /[a-z]|POST /[a-z])" src/components --glob "*.vue"

# 原语接线（§3 行 5）与零消费者
cd frontend; (Get-ChildItem src/components/ui/Ui*.vue).Count
cd frontend; rg -l UiTable UiUpload UiDialog UiToastHost src -g "!src/components/ui/**"

# 端点消费者（G05 / G10 / §4.3）
cd frontend; rg -n "/ack|/close|/assign|/users|/profile|/slo|stage-latency|queue/.*cancel" src -g "!*.test.js"

# 假权限与原生弹窗（§4.3、G15）
cd frontend; rg -n "ROLE_KEY|isAdmin = computed" src/App.vue src/components/DocPanel.vue
cd frontend; rg -n "confirm\(" src -g "!*.test.js"
```
