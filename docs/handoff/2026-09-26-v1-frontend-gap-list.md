# 2026-09-26 · V1 前端线缺口清单（员工使用视角）— R265

- **单号**：R265（执行层）· 工作树 `be-r265` · 分支 `codex/be-r265` · 基点 `8613dc7`。
- **性质**：取证单。**零代码改动**，本文件是本单唯一产物（新建）。
- **行号口径**：以下所有 `文件:行` 一律锚 commit `8613dc7`，不锚工作树（主树是共享树，行号会漂）。
- **实测时间**：2026-09-26 11:48 (+08:00)，`node v24.13.0` / `npm 11.6.2`。
- **不引用旧结论**：计划书 §6.1 的状态词全部按今天的源码重核（§3），每条缺口都带 `文件:行` 或命令输出。
- **R426 现场重判**（2026-09-28，锚 commit `ac84f1a`，工作树 `be-r415`）：§1 的 T 表、§3 的八项对账、§4 的三条硬判据、§6 的 G 表已逐行在这棵树上重取一遍，**判定改了的行就地改写**，证据前一律标 `现读@ac84f1a`；拿不出磁盘字节或命令+EXIT 的行原样留着，进 §10 未证清单。
- **两枚行号锚并存**：没带锚的 `文件:行` 仍是 R265 基点 `8613dc7` 上的当时取证（今天多数已漂，别照抄去派工）；带 `@ac84f1a` 的是 R426 当场推导的 live coordinate。
- 🔴 **改口 ≠ 销账**：下面把若干行由「无 / 半」改判为「已落」，收益只是**让下一班不再重复派已经修完的活**；V1 门槛是否达标仍由总控按验收记录裁定，本文不构成达标凭据。

---

## 0. 一句话结论

八项对账里 **三格状态词已过期**（自研 UI 原语、三屏 SLO 契约、图谱降级承接），三条硬判据里 **一条今天实测不成立**（界面无技术注解：3 处技术文案确实上屏）。
- 从员工视角看今天**办得完**的：提问拿答案并看到出处、点开原文核对、批待办、被拒绝时看得懂人话。
- 今天**办不完**的四件事：我传的文档到底能不能被问到 / 我报的数据是谁传的 / 告警看到了怎么办完 / 换台机器我的历史在哪。
- 缺口 **20 条（P1 十一条）**，按写集归成 **8 块**，合计约 **12–12.5 人日**；只做 P1 约 **9 人日**。（R265 当时读数）
- 🔴 **R426 现读（`ac84f1a`）改写这一句**：上面「今天办不完的四件事」今天**办得完三件** —— 文档能不能被问到有正脸（G01）、告警看到了能就地办完（G05）、换台机器问过的话点一下就回得来（G04）；剩「我报的数据是谁传的」**半**：文档行已画上传者，数据文件行后端已回 `owner_id` 而界面一枚都不画。§6 那 20 枚的现读汇总（已落 / 半 / 未落 各几枚）见 §10.1。

---

## 1. 判据① · 员工一天的事 × 现状（有 / 无 / 半）

任务表取自计划书 §1 角色旅程（`docs/frontend-plan-2026-09-14.md:53-118`）与 §2 视图映射（同文件 `:121-135`），逐条到 09-26 的页面与 `docs/api/contract-v1.md` 上对。

| # | 员工要办的事 | 判定 | 半在哪 / 证据 |
|---|---|---|---|
| T1 | 提问 → 拿答案 → 看到出处并点开核对原文 | **有**（判定不变，坐标改现读） | 现读@ac84f1a：出处按钮 `frontend/src/components/SourceCard.vue:92-100`（`data-testid="source-open"` → `emit('preview', row)`）；面板接法 `frontend/src/components/ChatPanel.vue:1937` → `openSourcePreview` `:1608` → 预览弹窗挂载 `:2085`；每行密级 `SourceCard.vue:103`、首屏线索卡 `frontend/src/components/AnswerHeadlineCard.vue:90`；一次出处一次评价 `SourceCard.vue:109-135` |
| T2 | 上传文档 → 知道「多久能被问到」 | **有**（09-26 那句「已索引没有脸」= 过期账） | 现读@ac84f1a：indexed 有正脸 `frontend/src/components/DocPanel.vue:34`（`retrievable: 已可检索`），唯一出口 `:62`；上传回执之后开一轮有限轮询 `:681` → `armUploadPoll` `:883`，盯满一整轮仍没结果那一格给人工出口「再读一次」`:858`、`:1188-1190`；密级随上传发出 `:650`（`form.append(classification, …)`），后端 `Form(1)` 只是缺省（现读 `app/api/v1/chat.py:4419`） |
| T3 | 查自己报的数据（我传过什么、谁的） | **半**（半的地方换了） | 现读@ac84f1a：**文档行已画真值**——`DocPanel.vue:147` `ownerTruth` 与模板那一格 `:1195-1202`，三句话只读 catalog 已有的 `owner_id`/`size_bytes`/`parse_status`；**数据文件行仍缺一张脸**——后端今天回归属人（`app/api/v1/data.py:276` `owner_id`，R310/R337 之后），而 `rg -n owner frontend/src/components/DataPanel.vue` → **EXIT 1 零命中** ⇒ 这一格是零后端的前端读数题，不是后端字段题（旧账那半句已过期） |
| T4 | 看图与报告（成果找回） | **有**（09-26 那句「独立视图 0 屏」= 过期账） | 现读@ac84f1a：「交成果」是一枚一级屏——`frontend/src/router/index.js:100-105`（`path: /artifacts` + `meta.title: 交成果`，未写 `primary:false` ⇒ 由 `:167` 派生得出侧栏入口），薄壳 `frontend/src/components/ArtifactsPanel.vue:28`/`:44` 挂 `ArtifactList`；「喂料 → 数据」那一屏继续挂它（`frontend/src/components/DataPanel.vue:454`）；对话内图 `ChatPanel.vue:238`/`:1920`，取图走带 Bearer 的共享实例 `frontend/src/lib/artifacts.js:62`。残格：列表行里取不到「这一问」的键——`cd frontend; rg -n session_id ../app/api/v1/artifacts.py` → **EXIT 1**；`rg -n request_id ../app/api/v1/artifacts.py` → 1 命中，但那枚是删除审计的入参（`app/api/v1/artifacts.py:109` `request_id=principal.request_id or None,`），不是列表字段；列表行的字段全集 = `app/api/v1/artifacts.py:151-165` `_artifact_row()` 叠 `app/storage/artifacts.py:237-244` `public_payload()`，两本里都没有 `session_id`／`request_id` ⇒ 「按这一问找回那份成果」仍做不到（旧账里这半句仍然对） |
| T5 | 处理待批 | **有**（判定不变，坐标改现读） | 现读@ac84f1a：真挂起账本 + 分页 + 期限 + 失败轮 `frontend/src/components/hitl/HitlPendingPanel.vue:592`（`data-face`）、`:100`（`expiresAt`）、`:684`（`loadMore`）；对话内同一枚 resolver `frontend/src/components/ChatPanel.vue:1003`（`POST /approve`） |
| T6 | 处理告警 | **有**（09-26 那句「不能确认关闭指派」= 过期账；带一枚残格） | 现读@ac84f1a：确认 / 关闭 / 指派三枚已接——`frontend/src/lib/alerts.js:230` `ALERT_DISPOSAL_COLUMNS`、`:526` `disposeAlert`，消费点 `frontend/src/components/InsightPanel.vue:349`；处置写的列与后端 `app/api/v1/alerts.py:450-451` `ALERT_DISPOSAL_WRITE_COLUMNS` 同一本账。残格：单条详情 `GET /alerts/{alert_id}`（`app/api/v1/alerts.py:1124`）**前端仍 0 消费者**（`rg -n "alerts/\[" frontend/src` → **EXIT 1**）⇒ 每办一次都重读整页列表；已立案 R286，不占新号 |
| T7 | 被拒时知道下一步做什么 | **有**（09-26 那句「指向不存在的部门选择器」= 过期账） | 现读@ac84f1a：部门那一句已改成做得到的下一步——`frontend/src/lib/errcodes.js:149`「请联系管理员补上你的部门归属，或改用已登记部门的账号」；审批屏不再替员工填别人的部门 `frontend/src/components/ApprovalPanel.vue:45-54`（`ownDepartment` 只读本人），演示常量里已无部门 `frontend/src/devFixtures/approval-demo.js:11` |
| T8 | 登录 / 换密码 / 找回账号 | **半**（半的地方换了） | 现读@ac84f1a：登录页那句「请联系管理员在用户管理中重置」（`frontend/src/App.vue:419`）**不再指向空气**——管理屏已在树：`frontend/src/router/index.js:122-127`（`/admin`「账号与角色」）+ `frontend/src/components/AdminPanel.vue`，写口 `frontend/src/lib/users.js:277-281`（`/users`、`/users/password`、`/users/department`）。仍缺的那半是**员工自助**：`GET/PUT /profile`（`app/api/v1/auth.py:241`、`:249`）前端 0 消费者（`rg -n "/profile" frontend/src` → **EXIT 1**），改自己密码、看自己部门归属仍然只能找管理员 |
| T9 | 换个地方接着问（历史跟着人走） | **有**（09-26 那句「只从 localStorage 组装」= 过期账） | 现读@ac84f1a：`frontend/src/lib/sessions.js:888` `serverSessionRow`、`:924` `readBackendSessionList`、`:940` `mergeServerSessions`（并集不是覆盖；`fromServer`/`bodyFetched` 两格把「名单回来了、正文还欠着」与「这条没内容」分开记）；屏上有入口 `frontend/src/components/ChatPanel.vue:553` `pullServerSessions` → `:1751` `data-testid="session-pull"`、`:1761` `session-pull-face`，挂载期一枚请求都不发、伸手才读。退出仍整包清本地态：那是这一格的设计前提（`sessions.js:881-883` 明写它只依赖服务端读数 + 内存 store），不是漏洞 |
| T10 | 在对话里知道「这一问用的是哪张表」并能改 | **半**（09-26 判「无」= 过期账） | 现读@ac84f1a：**模板真把它画出来给人改了**——`ChatPanel.vue:2013-2025`（`本轮数据表` label + `<select data-testid="chat-data-table-select" :value="activeDataFilename" @change="chooseDataTable(...)">` + 重读清单 `:2030`），改的就是下一轮真正发出去的那一份（`send` 默认参数读它 `:813`/`:820`）；逐轮回显「那一轮带了哪张表」`:1951-1952` + `dataTableOf` `:657`；服务端用表那一句的脸也在屏上：`:1956-1957` `data-testid="server-data-readout"` + `serverDataOf` `:678`。**仍断的两格**：终态帧唯一解码处 `frontend/src/lib/sessions.js:478-482` 只抄 `awaiting_hitl`/`awaiting_steps`，`data` 其余键丢掉；且 `rg -n terminal_data_filename app` → **EXIT 1**（R414 未并这棵树）⇒ 屏上那句今天只出「不画」这一态 |
| T11 | 机器不健康时别骗我 | **有**（09-26 那句「前端只判一枚码」= 过期账；带一枚残格） | 现读@ac84f1a：`frontend/src/lib/health.js:24-26` 三枚码齐（`model_not_available` / `embedding_model_missing` / `queue_unavailable`），`:108-110` 各自派脸，`:253-254` 按 `problems[]` 逐族出脸，`:56-66` 读 `model.inference_compute*` 与 `storage.read_only_protected`（对端 `app/common/monitoring.py:131`、`:133`、`:146`、`:215-218`）；消费点 `ChatPanel.vue:242`/`:778` → 屏上 `:1830-1832` `data-testid="runtime-faces"`。残格：全站降级横幅仍没有——`rg -n runtimeFaces frontend/src/App.vue` → **EXIT 1**，脸目前只长在对话那一屏 |

> 现读@ac84f1a：一级屏 **6 枚**（总览 / 喂料 / 异常与告警 / 审批与待办 / 问一句 / 交成果，`frontend/src/router/index.js:56-105`），另有三枚非一级落点——`/graph`（`:110-114`）、`/admin`「账号与角色」（`:122-127`）、`/traces`「运行留痕」（`:137-141`）；后两枚带 `administratorOnly:true`，只派生进管理员那一份入口清单（`:187-189` 与 `:196-197`）。⇒ R265 那句「管理视图整屏不存在」已过期。
---

## 2. 判据② · 缺口怎么补（只给文件清单与字段，不写实现）

每条缺口在 §6 里给两行：**动** = 要动的文件（含会被撞到的测试件），**字段** = 要哪个接口字段（标 `已有` 即零后端改动）。本单不写任何实现，也不改任何现有文件。

---

## 3. 判据③ · 计划书 §6.1 八项逐条对账

原表：`docs/handoff/2026-09-17-perf-architecture-plan.md:381-391`。右列为 09-26 实取。

| 项 | 计划书停在 | 今天的实真 | 证据 |
|---|---|---|---|
| 洞察 →「异常与告警」 | 已完成 | ✅ **已完成**（坐标改现读） | 现读@ac84f1a：定名 `frontend/src/router/index.js:76`（`meta.title: 异常与告警`）；页内同名 `frontend/src/components/InsightPanel.vue:423`/`:426`（`header.panel-head` 里的 `<h3>`）；数据源是真链 `frontend/src/lib/alerts.js:25-27`（`/alerts`、`/alerts/rules`、`/alerts/check`） |
| 审批 →「报销自查」 | 已完成 | ✅ **已完成，且定名已二次更正** | 现读@ac84f1a：这一屏叫「审批与待办」（`frontend/src/router/index.js:84`）；「报销」二字不得再作任何一屏的名字已由在册用例钉着：`frontend/src/components/__tests__/r174-screen-name.test.js:33-34`（常数）与 `:43`（枚用例）|
| 四张脸分开（无权限/空/降级/错误） | 已完成；缺 embedding / 无 GPU 两张脸仍未分 | ✅ **那半张今天已长出脸**（09-26 判 ❌ = 过期账） | 现读@ac84f1a：embedding 与算力两张脸都在 `frontend/src/lib/health.js`——`:25-26` 两枚码、`:108-110` 分派、`:214` `computeFace`、`:241`/`:253-254` `runtimeFaces` 逐族出脸，`:56-66` 读 `model.inference_compute*` 四键与 `storage.read_only_protected`；消费点 `ChatPanel.vue:778` → 屏上 `:1830-1832`。计划书那行「缺 embedding / 无 GPU 两张脸」今天**不再成立**（归因 `90c15bb`·R268/G07）；仍欠的那一格是全站降级横幅（`rg -n runtimeFaces frontend/src/App.vue` → EXIT 1）⇒ 见 G07 残格 |
| Element Plus 移除 | 已完成 | ✅ **已完成**（今天仍为真） | 现读@ac84f1a：`cd frontend; rg -c element-plus package.json` → **EXIT 1（0 命中）**；依赖清单实读 `frontend/package.json:15-24`（vue / vue-router / axios / dompurify / markdown-it / 两枚 fontsource / lucide-vue-next） |
| **自研 UI 原语（写「进行中」）** | 进行中 | ✅ **已完成，但完成的内容换了**：不是没写完，也不是「写完没接线」，是**接线已收口、只剩两枚原语无人消费** | 现读@ac84f1a：12 枚原语在树（`cd frontend; (Get-ChildItem src/components/ui/Ui*.vue).Count` → 12）；零消费者从四枚降到**两枚**——`UiTable` 已被 `components/AdminPanel.vue`、`components/TracePanel.vue` 消费，`UiDialog` 已被 `AdminPanel.vue` 消费，仍零消费者的只剩 `UiUpload` 与 `UiToastHost`（`rg -l UiUpload UiToastHost frontend/src -g "!src/components/ui/**" -g "!*.test.js"` → 只剩 `assets/theme.css` 提过 UiToastHost）；裸 `<button>` 债务**归零**：`frontend/src/components/__tests__/r288-native-buttons.test.js:60` `DEBT_TOTAL_RATCHET = 0`，同件 `:54-56` 逐枚写着 `App.vue: 0`、`components/DashboardPanel.vue: 0`、`components/SourceCard.vue: 0` ⇒ R265 那句「裸 button 计数 ChatPanel 10、DashboardPanel 9…」与并入 G20 的账都已过期 |
| **图谱撤一级入口** | 已完成 | ✅ 撤入口已完成 / ✅ **降级承接今天已建**（09-26 判 ❌ = 过期账） | 现读@ac84f1a：撤——`frontend/src/router/index.js:114` `primary:false`，导航由 `:161`/`:167` 派生；承接——文档预览里长出「依据 / 相关制度」那一格：`frontend/src/components/DocumentPreviewModal.vue:40`（R314 判据自述）、`:100` `relationsAboutDocument`、`:138-139` 取数 URL 走 `GET /knowledge-graph/relations`；`GraphPanel.vue` 那枚英文眉标也已摘（`rg -n class="eyebrow">[A-Za-z ]+< frontend/src --glob "*.vue"` → **EXIT 1 零命中**）⇒ G12 与这一行都该改口 |
| 前端路由 | 已完成 | ✅ **已完成**（坐标改现读） | 现读@ac84f1a：`router/index.js` 是屏↔URL 唯一真源，侧栏是它的派生视图（`:161` `isPrimaryScreen` → `:167` `navigation` → `:174` `screenIds`；管理员那一份由 `:187-189` + `:196-197` 派生）；`frontend/src/App.vue:497` `<KeepAlive :include="cachedScreens">`，`cachedScreens` 由路由表算出（`router/index.js:220`）|
| **三屏 SLO 契约（写「未做」）** | 未做·已拆两半（R105 甲/乙） | ⚠️ **状态词仍过期，但界面那一腿今天补了一半** | 现读@ac84f1a：甲半——契约段在 `docs/api/contract-v1.md:1547`（`## Three-Tier SLO Contract (2026-09-20, R105 甲半)`），闸在 `app/api/v1/observability.py:727`（`MIN_SLO_SAMPLES = 100`）+ `:1041`（`slo_readout`）；乙半——`lane_attribution_absent` 仍逐条挂在 blocker（同文件 8 枚命中，`:763` 是定义那格）⇒ 仍挂。**R265 记的那格「GET /slo 与 GET /stage-latency 前端 0 消费者」今天只对一半**：`/stage-latency` 已有消费者（`frontend/src/lib/traces.js:46` `STAGE_LATENCY_PATH`，屏在 `frontend/src/components/TracePanel.vue:10` + 路由 `frontend/src/router/index.js:137-141`）；`/slo` 仍 0（`rg -n -F "SLO_PATH" frontend/src` 与 `rg -n -F "'/slo'" frontend/src` 各 → **EXIT 1**。🔴 取证口径：裸 `rg -n "/slo" frontend/src` 今天交回 15 行，但枚枚都是模板里的 `</slot>` 误命中，拿它下判会判反）|

**R265 当时的对账净结论**：八项 = ✅ 五项、❌ 一项（四张脸那半张）、⚠️ 两项状态词过期。

**R426 现读@ac84f1a 重算**：八项 = ✅ **七项**、⚠️ **一项**（SLO：甲半已完、乙半仍挂、界面腿补了 `/stage-latency` 那一半），❌ 归零。R265 点名的两笔「计划书自己没记的账」今天各自结案：图谱降级承接（G12）**已建**、SLO 读数面的运行留痕那一屏（G10 的一半）**已在树**——仍欠的是 `/slo` 那一格，见 §6 G10 现读。
---

## 4. 判据④ · 计划书 §2 三条硬判据实测

判据出处：`docs/frontend-plan-2026-09-14.md` §11 验收清单（`:550-599`）+ 计划书 §2 视图映射；计划书 `2026-09-17-perf-architecture-plan.md:395` 把这三条统称「其余 V 线判据」。**注意**：那行写「见 frontend-plan §2」，而 §2（`:121-143`）实际是工作区映射表，三条判据的真正落点是 §11 与 §4.5（`:239`）—— 指路已过期，另记一笔（G21）。

### 4.1 全屏登录 → ✅ 成立

- 现读@ac84f1a：结构上互斥——登录是 `frontend/src/App.vue:274` 的 `main v-if="!isLoggedIn"`，工作台是 `:429` 的 `v-else`，**未登录时工作台整棵子树不挂载**，面板与请求都不会发。
- 现读@ac84f1a：铺满视口——`frontend/src/assets/theme.css:1154` 起 `.login-v2`（`display: grid` + `min-height: 100dvh` + `overflow: hidden`），外层 `.app-root { min-height: 100dvh }`。
- 视觉回归已有件：`frontend/tests/visual/login-viewports.spec.js`（五档视口，含 3440×1440 与 1280×720）。

### 4.2 界面不得出现「来自 xx 接口」类技术注解 → ✅ **今天成立**（09-26 判 ❌ = 过期账；原判据与当时读数照录如下）

取证命令与命中数（在 `frontend/` 下跑）：

```bash
rg -n --no-heading "(src/[A-Za-z0-9_./-]+\.js|GET /[a-z]|POST /[a-z])" src/components --glob "*.vue"   # 命中 29
```
- R265 当时：29 命中里 26 处在源码注释（写给人看的实现说明，不上屏）；肉眼逐条筛后**确实渲染给员工**的是 3 处（下表为**病灶存档**，行号锚 `8613dc7`，今天已不在这些行）：

| # | 位置 | 上屏原文（片段） | 为什么算违规 |
|---|---|---|---|
| 1 | `frontend/src/components/DashboardPanel.vue:175` | 「…仍是前端常量 src/devFixtures/dashboard-demo.js，不来自任何接口。上面四个数字改为读服务端聚合 **GET /api/v1/dashboard/summary**…」 | 员工屏幕上出现**前端源码路径 + HTTP 方法与路由** |
| 2 | `frontend/src/components/ApprovalPanel.vue:168` | 「预审参数…来自前端常量 **src/devFixtures/approval-demo.js**…」 | 同上（源码路径） |
| 3 | `frontend/src/components/ApprovalPanel.vue:182` | 「挂起待办这一屏读的是服务端挂起账本（**GET /hitl/pending**）…」 | 同上（路由名） |

- R265 当时：三处全在 `<template>` 内、无条件渲染分支里，`data-testid` 分别叫 `dashboard-demo-flag` / `approval-demo-flag` / `approval-scope-note`。
- 🔴 **R426 现读@ac84f1a：这一格已收口，那条 rg 命令今天不能当判据用**——三枚 `data-testid` 仍然在屏上，但屏幕上说的话里已经没有源码路径与路由名：`frontend/src/components/DashboardPanel.vue:335-338`（诚实牌全文只说「这一格还没有服务端回传的数字」）、`frontend/src/components/ApprovalPanel.vue:208-211`（逐字交代哪些是演示常量、部门填的是本人登记的）与 `:219-228`（自查范围说明，无一条 `GET /` 与 `.js`）；`GET /hitl/pending` 那两句今天挪进了 `:204` 的注释。反证钉在册：`frontend/src/components/__tests__/r267-overview-no-tech-note.test.js`（R426 实跑 5 passed，判据是 SSR 出的真 HTML，不是源码正则）。旧那句「裸 rg 命中数」今天涨到 60 行（实现注释变多），**用它判上屏会判反**——这条方法学改口请下一班务必照抄。
- 对照组（说明这判据别的屏做得到）：`SourceCard.vue`、`QueueFace.vue`、`lib/errcodes.js` 一律把后端原串收进视图模型再说话，未知码只允许「错误码：xxx」小字（`frontend/src/components/ui/README.md`，并由 `frontend/src/lib/no-bare-code.test.js` 全仓扫）⇒ **G13 已落，别再派**。

### 4.3 管理视图对 staff 不可见 → ⚠️ **判据今天必须重测才成立**（R265 那句「因为这一屏根本不存在」= 过期账）

- 现读@ac84f1a：管理屏**已经在树**，R265 那条读数的两条腿都断了——`GET/POST/DELETE /users`、`PUT /users/password`、`PUT /users/department` 有消费者（`frontend/src/lib/users.js:36`、`:277-281`、`:223` `loadUsers`，屏在 `frontend/src/components/AdminPanel.vue`，路由 `frontend/src/router/index.js:122-127`）；`GET /traces/{id}` 与 `GET /stage-latency` 也有消费者（`frontend/src/lib/traces.js:46`、`:48`，屏 `frontend/src/components/TracePanel.vue`，路由 `:137-141`）。仍 0 消费者的只剩 `GET /audit/events`、`GET /evaluations`、`GET /slo`、`GET/PUT /profile`、`POST /retrieval/debug`（`rg -n "/profile" frontend/src` → **EXIT 1**；`rg -n -F "audit/events" frontend/src` → **EXIT 1**、`rg -n -F "evaluations" frontend/src` → **EXIT 1**、`/slo` 见 §3 那两支具名探针）。另两枚命中不是消费者：`rg -n -F "retrieval/debug" frontend/src` → 2 命中全是注释（`frontend/src/App.vue:61`、`frontend/src/__tests__/r278-topbar.test.js:12`），一枚调用点都没有。🔴 含 `|` 的正则（`"/slo"` 那一族）在本仓会误命中 `</slot>`，别当判据用）。
- 结论改口：这条判据今天**不再靠「没做」为真**，而是靠「入口按角色派生 + 服务端真判」为真：`navigationForRole(role)` 只对 `admin` 那一档追加 `administratorNavigation`（`router/index.js:187-189`、`:196-197`），staff / manager / auditor / 无角色四档拿到的都是同一份 `navigation`，`/admin` 与 `/traces` 两枚入口一枚都派生不出来——这一格由在册用例钉着：`frontend/src/router/__tests__/r316-admin-entry.test.js` 的「角色不对就一枚都不派生」与「壳层真的按角色派生入口」。
- 🔴 但「员工看不见」这一半今天是**客户端判据**：侧栏吃的 `userRole` 来自登录回包写进 localStorage 的 `eb_role`（`frontend/src/App.vue:111`、`:184`；`frontend/src/lib/http.js:10`、`:52`），员工自己改这一格就能长出管理入口——计划书 J5 说的那类**假权限**，病灶从「喂料屏的选择框」扩到了「管理入口」。挡它的是服务端那道闸：staff 走进去拿到的是 403 那张脸（`frontend/src/lib/users.js:62` `USERS_FACE_DENIED`、`:162-166` 分派，`frontend/src/components/AdminPanel.vue:300`/`:320` 用 `UiErrorState` 画它），不是空列表；真源 `app/api/v1/auth.py:106` 那发 `ACTION_MANAGE_USERS`。
- R265 那两笔暴露项今天各自的下场：**(a)** 登录页那句「请联系管理员在用户管理中重置」（现读 `frontend/src/App.vue:419`）**不再指向空气**（管理屏已在树）⇒ G10 的那半句过期；**(b)** 客户端角色仍被消费：`frontend/src/App.vue:54` 把 `userRole` 只喂给喂料屏，`frontend/src/components/DocPanel.vue:382` `isAdmin` 仍由它派生、`:1111` 用它开批量删除——这一格**照旧**，是计划书 J5 那笔没销的账。

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
- 结论：**零远程字体/CDN 请求** ✅（与 R148 记录一致，今天仍成立）。（R426 现读：这一行要构建产物才取得到，本单按硬约束没跑 `npm run build`，故照原样留着，未重取。）

## 5.2 R426 现取（2026-09-28 +08:00，锚 `ac84f1a`，工作树 `be-r415`：全量自 `Start at 03:19:51` 逐跑同数，最后一次 `Start at 03:38:32`）

| 项 | 命令 | 读数（原文） |
|---|---|---|
| 单测全量 | `cd frontend; npm run test` | **Test Files 119 passed (119)** ／ **Tests 2460 passed (2460)** ／ 退出码 0，零 failed、零新增 skip。全量逐跑同数、退出码皆 0（`03:19:51` 起至 `03:38:32`，Duration 只在 5.80–6.03 s 之间抖）⇒ 与总控给的基点读数 **119 files ／ 2460 tests** 逐字相同，本单两枚改动没动任何计数（没有一枚用例读本文：`rg -ln 2026-09-26-v1-frontend-gap-list frontend/src` 唯一命中是注释 `src/lib/__tests__/r270-department-voice.test.js:4`） |
| 色值门 | `cd frontend; npm run lint:colors` | **148 problems (0 errors, 148 warnings)**，退出码 0 —— 与基点读数 148 逐字相同，未新增裸色值；末次 `03:38:39`，逐次同数，退出码皆 0 |
| 点名复跑 | `cd frontend; npx vitest run src/lib/__tests__/r416-comments-cite-live-coordinates.test.js src/lib/__tests__/r420-stale-coordinates-second-blade.test.js src/router/__tests__/r316-admin-entry.test.js` | **3 files ／ 59 tests passed**`Start at 03:20:04`／Duration 519ms，改头注前后各跑一次，两次同数）⇒ 改 `r316-admin-entry.test.js:4-10` 没挪动那两本坐标账 |

- 落笔顺序自陈（自指，写明不装）：**判定与证据的落笔全部收在 03:35 之前**；那之后本节改的只有时间戳与本条说明这类账面文字，而每次改完都复跑一次全量与色值门，枚枚同数。所以本节任何一行都可能晚于它所引的那次跑，但没有任何一行**判定**晚于 03:35。总控要复核不必信这句话：改口落笔之后重跑 `cd frontend; npm run test` 与 `npm run lint:colors`，两数仍应是 **119 files ／ 2460 tests** 与 **148 problems（0 errors）**——本文没有任何用例读它（见上表括注），账面文字改不动计数。
- 没跑的：`npm run build`、`npm run test:e2e`、`python scripts/run_gate.py`（全量门归总控）、任何 `pytest`、任何容器／服务操作。
---

## 6. 缺口清单（20 枚 + 2 枚记账项）

优先级口径：**P1 = 挡 V1 门槛或构成屏上假话**，P2 = 明显缺口但不挡 V1，P3 = 打磨。
「动」只列文件，不写实现；字段标 **已有** 表示零后端改动（读路径或请求体里今天就有）。

🔴 **R426 读法（2026-09-28）**：下面三张表的「现状证据」列已逐行在 `ac84f1a` 上重取。判定改了的地方就地写明旧账是哪一句；**判「已落」的行，它的「动」列只作历史归因用，不是待办**。现读汇总（已落／半／未落各几枚）在 §10.1，未证清单在 §10.2，越界发现（只报不改）在 §10.3。

### P1（11 枚）

| # | 员工视角的症状 | 现状证据 | 动（文件） | 要哪个接口字段 |
|---|---|---|---|---|
| **G01** | 传完文档只知道「上传完成」，**不知道这篇能不能被问到** | ✅ **已落**（现读@ac84f1a）：`DocPanel.vue:34` 有正脸 `retrievable: 已可检索`，唯一出口 `:62`；`:681` 上传回执之后开一轮有限轮询、`:883` 是 `armUploadPoll` 定义，盯满一整轮仍没结果那一格给人工出口「再读一次」（`:858`、`:1188-1190`）。R265 那三行旧证据（`:99-105`／`:460-464`／`:206-246`）已过期 ⇒ **勿再派** | `components/DocPanel.vue`；`components/__tests__/r237-r49-index-face.test.js`、`panel-states.test.js` | **已有**：catalog 行 `index_status=indexed`、`parse_status`（`app/documents/catalog.py:238-257`）。缺的是一枚「已可检索」正脸，不是字段 |
| **G02** | 总览上每篇文档都写着「已解析」、指标口径永远「高可信」 | ✅ **已落**（现读@ac84f1a）：两枚写死字串都不在生产码里——每行解析态走 `DashboardPanel.vue:112-122` 的四档 + 未知脸，模板 `:532`／`:534` 画的是 `indexStatusText(item)` 与 `parseStatusText(item)`；口径那一格改读回执字段 `:291-292`（`definition_source`／`provenance`），屏上 `:569` 那枚「已按制度核对」要 `provenance.verified_against_documents === true`（`:152`）才挂；`rg -n 高可信 frontend/src` → 5 命中全在 `components/__tests__/r267-overview-real-status.test.js`（`:130`／`:148` 是反向钉）。「已解析几篇」那一句今天有三张脸（`lib/dashboard.js:75-84`：未记录／全部已解析／对不上），派生自聚合回执里的 `documents_ready`（同文件 `:191-195`）⇒ **勿再派**。在册钉：`components/__tests__/r274-documents-tile-truth.test.js`、`r267-overview-real-status.test.js` | `components/DashboardPanel.vue`；`components/__tests__/dashboard-summary.test.js`、`v7-fake-data.test.js` | **已有**：`parse_status`/`index_status`（catalog）、`definition_source` 与 `context.warning` 与 `provenance`（`app/api/v1/intelligence.py:283-290`） |
| **G03** | 问出来的数和页面上选的表**对不上，也无从纠正**（J4） | 🟡 **半**（现读@ac84f1a，半的地方换了）：界面那一半已收——选择器 `ChatPanel.vue:2013-2025`（`:value="activeDataFilename"` + `@change="chooseDataTable(...)"`）、逐轮回显「那一轮发出去带了哪张表」`:1951-1952`；服务端那一半今天**两格都欠**：① `rg -n terminal_data_filename app` → **EXIT 1**（R414 未并这棵树，终态帧里没有这一格）；② 终态帧唯一解码处 `lib/sessions.js:478-482` 只抄 `awaiting_hitl`／`awaiting_steps`，`data` 其余键丢掉 ⇒ 屏上 `server-data-readout`（`ChatPanel.vue:1956-1957`，`serverDataOf` `:678`）今天恒走「不画」那一态。三态各自的名字与「不许拿发依据填」那枚反向钉在册：`components/__tests__/r415-server-data-readout.test.js`。**这一行仍是活，但要的是后端终态帧 + lib 两行，不是界面** 🔴 **09-29 第五班现读改口（勿再照上面那两格派工）**：① 那一格已真落——判定件 `terminal_data_filename` 与挂载件 `attach_terminal_data_filename` 两枚都在 `app/api/v1/chat.py` 里（R414 起、R504 并树 `60a8e01`；现取 `rg -c terminal_data_filename app` 该件 11 枚命中——本行按 r455 口径不抄后端行号，要坐标跑 `python scripts/r455_gapdoc_coordinates.py --emit-doc-cells` 取派生读数），队列道三处也已递键（`deploy/queue_worker.py:711`/`:757`/`:921`，R514 并树 `333d728`）；② 解码处今天**两枚**——canonical `lib/sessions.js:481`、legacy `done` `:575`（R512 并树 `131df9b`；三形：非空才抄／空串不覆盖不补造／缺席一字不动，先到者胜），故 `server-data-readout` 不再恒走「不画」那一态。屏侧读者仍只有 `adoptServerDataRead`（`ChatPanel.vue:698-703`，调用点 `:1060`／`:1186`），`/queue/status` 那一格屏侧仍无读者 ⇒ G03 剩下的活已从「后端终态帧＋lib 两行」换成「队列道屏侧读数」一枚。旧句里那个 `ChatPanel.vue:599` 坐标随 R517 改口已不含 `data_filename` 这一字面。凭据另见 `docs/api/contract-v1.md` 的 R504／R512／R514 节与 `docs/testing/r517` 系列订正。 | `components/ChatPanel.vue`（回显 + 就地改表）、`App.vue`（若按计划书放顶栏常驻）、`lib/sessions.js`（只读）；用例 `components/__tests__/r174-*`、`panel-states.test.js` | 上行已有 `data_filename`（`ChatPanel.vue:599`）；**回显要后端补**：canonical `sources`/done 帧里带本轮真正用的 `data_filename`（今天流里没有） |
| **G04** | 换台电脑 / 被登出一次，**问过的话全不见了**（后端其实还在） | ✅ **已落**（现读@ac84f1a）：`lib/sessions.js:888` `serverSessionRow`、`:924` `readBackendSessionList`、`:940` `mergeServerSessions`（并集不是覆盖；`fromServer` + `bodyFetched` 两格把「名单回来了、正文还欠」与「这条没内容」分开记），屏上入口 `ChatPanel.vue:553` → `:1751` `data-testid="session-pull"`、`:1761` `session-pull-face`，挂载期零请求、伸手才读。旧那两行（`sessions.js:93-113` 只从 localStorage 组装、退出即回不来）过期 ⇒ **勿再派**；退出仍整包清本地态，那是这一格自述的设计前提（`sessions.js:881-883`），不是漏洞 | `components/ChatPanel.vue`（会话侧栏加「从服务器取回」）、`lib/sessions.js`（列表合并读取）；用例 `lib/sessions-error-text.test.js`、`components/__tests__/r174-replay-ownership.test.js` | **已有**：`GET /sessions` 回 `id/title/created_at/updated_at/msg_count`（`app/api/v1/chat.py:3921（`GET /sessions` 路由本体）`）→ 零后端改动 |
| **G05** | 告警看到了**没法办**：不能确认、不能关闭、不能指派，也看不出别人是不是已经办过 | ✅ **已落·带一枚残格**（现读@ac84f1a）：确认／关闭／指派三枚处置已接——`lib/alerts.js:230` `ALERT_DISPOSAL_COLUMNS`、`:526` `disposeAlert`，消费点 `components/InsightPanel.vue:349`；处置写的列与后端 `app/api/v1/alerts.py:450-451` `ALERT_DISPOSAL_WRITE_COLUMNS` 同一本账 ⇒ R265 那句「四枚端点 0 消费者」过期。残格只剩单条详情：`GET /alerts/{alert_id}`（`app/api/v1/alerts.py:1124`）仍 0 消费者（`rg -F "alerts/[" frontend/src` → **EXIT 1**）⇒ 每办一次都重读整页列表；**已立案 R286，不占新号** | `lib/alerts.js`、`components/InsightPanel.vue`；用例 `components/__tests__/insight-alerts.test.js` | **已有**：`GET /alerts` 行里 `status/acknowledged_by/acknowledged_at/closed_by/closed_at/assignee/assigned_at`（`app/api/v1/alerts.py:114-121`）+ `POST /alerts/{id}/ack|close|assign` |
| **G06** | 被排队那一轮**只能干等**，界面没有「不排了」 | ✅ **已落**（现读@ac84f1a）：`components/QueueFace.vue:71-78` 画那枚「不排了」，给不给由 `face.cancellable` 决定（同文件 `:14-15` 写着「对着已落定的一轮、对着挂起等人拍板的一轮说不排了都是假话」）；落点走排队那条腿 `ChatPanel.vue:1489` → `:1511`（`POST /queue/{request_id}/cancel`，后端路由现读 `app/api/v1/chat.py:5161`），与输入框旁「中断本次回答」`/ask/{session}/cancel`（`:944`）各管一头 ⇒ **勿再派** | `components/QueueFace.vue`、`components/ChatPanel.vue`；用例 `__tests__/r198-queue-poll-stop.test.js`、`r202-queue-poll-stop-authz.test.js`、`r221-queue-deadline.test.js`、`r260-queue-awaiting-approval.test.js` | **已有**：request_id 已在 queued 回执里（`lib/sessions.js:389-397`），cancel 端点已在契约 |
| **G07** | 模型/embedding 不在时界面**仍然报绿**，答案质量崩了却没有解释 | ✅ **已落·带一枚残格**（现读@ac84f1a）：`lib/health.js:24-26` 三枚码齐、`:56-66` 读 `model.inference_compute*` 四键与 `storage.read_only_protected`、`:108-110` 分派、`:214` `computeFace`、`:241`/`:253-254` `runtimeFaces` 逐族出脸（对端 `app/common/monitoring.py:131`、`:133`、`:146`、`:215-218`）；消费点 `ChatPanel.vue:242`/`:778` → 屏上 `:1830-1832` `data-testid="runtime-faces"` ⇒ 旧那行「`health.js:57` 只判一枚码、embedding 不在仍报绿」过期。残格：全站降级横幅仍没有（`rg -n runtimeFaces frontend/src/App.vue` → **EXIT 1**），写域在 `App.vue` ⇒ 本行不算全清 | `lib/health.js`、`components/ChatPanel.vue`（状态位文案）、`App.vue`（若做全站降级横幅，与 G16 同写集）；用例 `components/__tests__/chat-model-status.test.js` | **已有**：`GET /health/details` 的 `problems[]` 与 `model.inference_compute / _detail / _error_code / _age_seconds`、`embedding`（`app/common/monitoring.py:228-244`）。「无 GPU 那张脸」缺的是**码**：inference_compute_error_code 已有具名读数，前端接上即可，不必后端新造 |
| **G08** | 上传时**没人问密级**，全库默认 1 级；员工想给一份资料加密级，界面没有地方 | ✅ **已落**（现读@ac84f1a）：上传表单问密级且真发得出——`DocPanel.vue:650` `form.append('classification', String(item.classification))`（建 `FormData` 的时刻 `:642-643`，注释 `:386` 写明为什么必须在建那一刻读下拉），档位措辞走全站那一份 `:394-401` → `classificationLabel`；后端那枚 `Form(1)` 现读在 `app/api/v1/chat.py:4419` ⇒ R265 那句「表单只 append file」过期，**勿再派**（读回那一格是否已回 `classification` 本单未重取，见 §10.2） | `components/DocPanel.vue`（+ 顺带把 UiUpload 接上，见 G20）；用例 `components/ui/__tests__/upload-rules.test.js`、`panel-states.test.js`、`r151-legacy-colors.test.js`（若动样式） | **已有**：`POST /upload` 的 `classification` Form。**建议同时给一枚读回**：上传回执里回 `classification` 与最终 `department`（今天回的是 status/message） |
| **G09** | 普通员工一进「审批与待办」就看到**「没有权限做审批预审」**——真实原因是界面替他填了别人的部门 | ✅ **已落**（现读@ac84f1a）：界面不再替员工填别人的部门——`ApprovalPanel.vue:45-47` `ownDepartment` 只读本人（`DEPARTMENT_KEY`），`:54` 起点 = `{ ...demoForm, department: ownDepartment() }`，演示常量今天没有 department 这一格（`devFixtures/approval-demo.js:11` 自述 R277 起拿掉）⇒ 病根已治、**勿再派**。两格照实登记：`import { demoForm } ... :16` 仍在（其余初始值仍吃常量），挂载即自动预审也仍在（`:58` 注释 + `:189` `onMounted(submitCheck)`），但它今天不再制造「假无权限」那一张脸 | `components/ApprovalPanel.vue`、`devFixtures/approval-demo.js`；用例 `r237-r40-standard-auto.test.js`、`r247-approval-mount-dedupe.test.js`；`lib/errcodes.js`（把 department_override_denied 收进字典，今天 0 命中） | **已有**：登录响应 `department`（`lib/http.js:53` 已存 eb_department）；后端 `verify_department_self_report` 允许「重复自己」或留空（`authorization.py:89-90`）→ 界面只要不替员工填别人的部门就成立 |
| **G14** | 总览上有一条**画着金额的折线图**和一张「异常与风险」清单，数全是前端常量编的；这一屏还继续把自己造的 rows 送给后端算 | ✅ **已落**（现读@ac84f1a）：三枚演示常量（`demoRows`、`demoInsights`、`demoTrendShape`）已不在生产码（`cd frontend; rg -n -e demoRows -e demoInsights -e demoTrendShape src` → 2 命中全是反证钉：`src/components/__tests__/insight-alerts.test.js:446`、`src/components/__tests__/r267-overview-no-self-fed-rows.test.js:106`；`Test-Path frontend/src/devFixtures/dashboard-demo.js` → **False**；同一条 `rg` 今天交回 5 行，其中生产码里唯一还在 import 的是 `ApprovalPanel.vue:16` 那枚 `demoForm`，余下四行是注释与上线前清空告示（`src/lib/alerts.js:18`、`src/assets/theme.css:761`、`src/devFixtures/README.md:1` 与 `:11`）；`insights-demo.js` 文件还在但已清空成一纸告示，全仓无一枚 import（`devFixtures/README.md:17` 自述 R287））；自备 rows 那条腿也断了（`DashboardPanel.vue:26` 自述、`lib/dashboard.js:21-22` 只留 `SUMMARY_PATH`，反向钉 `components/__tests__/r267-overview-no-self-fed-rows.test.js:106`）；趋势卡走空态：`:335-338` 诚实牌 + `:366` `dashboard-trend-card` + `:409` `dashboard-trend-empty`，没有服务端数字就不画线、不放金额刻度 ⇒ **勿再派**。R265 那句「B-7 未落地」也已过期：`app/api/v1/dashboard.py:825` 有 `@router.get("/trend")`（R340／R342 并树，前端读数 `acc092e` R341） | `components/DashboardPanel.vue`、`devFixtures/dashboard-demo.js`；用例 `components/__tests__/v7-fake-data.test.js`（`:70-72` 钉引用面清单、`:104` 钉 demo-flag 计数）、`dashboard-summary.test.js` | 趋势要 **B-7 最小聚合**：`/dashboard/summary` 需新增 `trend[]`（元素 `period/department/metric/value`，今天无此键）。**B-7 落地前先删卡画空态**，不留假线 |
| **G13** | 员工在屏幕上读到**源码路径与 HTTP 路由**（违反 §2 硬判据） | ✅ **已落**（现读@ac84f1a）：那三处上屏的技术注解已改口成人话，源码路径与路由名都退进注释——`DashboardPanel.vue:337`、`ApprovalPanel.vue:210`、`:221-228`；反证钉在册（`components/__tests__/r267-overview-no-tech-note.test.js`，R426 实跑 5 passed，判据是 SSR 真 HTML）。🔴 取证方法一并改口：裸 `rg` 命中数今天涨到 60 行（实现注释变多），**拿它判「上屏」会判反**，见 §4.2 ⇒ **勿再派** | `components/DashboardPanel.vue`、`components/ApprovalPanel.vue`；用例 `components/__tests__/v7-fake-data.test.js:104`（钉 demo-flag 计数）、`r237-r40-standard-auto.test.js:403-405`（丁3 钉「这块仍挂牌」） | 无需接口 |

### P2（5 枚）

| # | 症状 | 证据 | 动 | 字段 |
|---|---|---|---|---|
| **G10** | 管理员**没有任何管理屏**：用户/改密/审计/评测/SLO/检索调试全都在后端躺着；而登录页已经把员工指向「用户管理」 | 🟡 **半**（09-26 那行「管理员**没有任何管理屏**」= 过期账；现读@ac84f1a）：两枚管理屏已在树——「账号与角色」`router/index.js:122-127` + `components/AdminPanel.vue`（读 `lib/users.js:223` `loadUsers`，写 `:277-281` 三枚路径 + `:626` 改密），「运行留痕」`:137-141` + `components/TracePanel.vue`（读 `lib/traces.js:46`、`:48`）。今天仍 0 消费者的只剩 `GET /slo`、`GET /audit/events`、`GET /evaluations`、`GET/PUT /profile`、`POST /retrieval/debug` ⇒ 剩那一格才是活，而且它不需要新后端 | 新屏 `components/AdminPanel.vue`（或按能力拆两三枚）、`router/index.js`（加一条 primary 屏 + 角色可见性判定）、`App.vue`（入口与派生导航）、`lib/` 新只读模块；用例 `router/__tests__/routes.test.js`、`src/__tests__/navigation.test.js` | 已有端点即可开工（只读优先：audit/events、slo、evaluations）；**先要一枚后端读回**：`GET /users` 是否已回 `department`（决定管理屏能不能真把 G19 那句「选部门范围」办成） |
| **G11** | 图和报告**藏在「喂料 → 数据」标签底下**，员工找不回来 | ✅ **已落**（现读@ac84f1a）：成果有独立一级屏——`router/index.js:100-105`（`/artifacts`，`meta.title: 交成果`，未写 `primary:false` ⇒ `:167` 派生得出侧栏入口），薄壳 `components/ArtifactsPanel.vue:28`/`:44` 只 import `ArtifactList`（那枚文件一字未动），「喂料 → 数据」那一屏继续挂它（`DataPanel.vue:454`）⇒ **勿再派**。残格照实登记：`cd frontend; rg -n session_id ../app/api/v1/artifacts.py` → **EXIT 1**；`rg -n request_id ../app/api/v1/artifacts.py` → 1 命中而那枚是删除审计的入参（`app/api/v1/artifacts.py:109`），列表行字段全集（`app/api/v1/artifacts.py:151-165` + `app/storage/artifacts.py:237-244`）里两把键都没有 ⇒ 「按这一问找回那份成果」仍要后端先给键。🔴 R426 自纠（不是改 R265 的账）：本单草稿的上一版把这枚 `rg` 记成 EXIT 1，是假读数，已换成字段全集当判据 | `router/index.js`、`components/DataPanel.vue`（摘出挂载）、`components/ArtifactList.vue`（提为屏时改页头与筛选）、`App.vue`（导航派生）；用例 `components/__tests__/artifact-list.test.js`、`router/__tests__/routes.test.js` | **已有**：`GET /artifacts` 分页（`app/api/v1/artifacts.py:168`），前端已按 `artifactTypeLabel` 分类型（`ArtifactList.vue:36-48`）。若要「按会话找回」需 `request_id`/`session_id` 进列表行 |
| **G16** | 顶栏两枚**按了没反应**的按钮（搜索、通知），退出那颗是个「⌄」看不出是退出 | ✅ **已落**（现读@ac84f1a）：搜索那枚死控件按 R278 摘着（理由今天仍然对：全站没有一枚诚实的全局检索端点，`App.vue:60-63`），通知这一格 R333 已用**真数**接回来——`App.vue:473-478` `<NotificationBell />`（件 `components/NotificationBell.vue`，出口 `lib/notifications.js:27-29`，徽标只吃全集未读 `unread_total`）；退出那枚有可及名称：`App.vue:80-82` `logoutLabel`（含「当前是谁」）→ 模板 `:486-487` `:aria-label`／`:title` ⇒ **勿再派** | `App.vue`；用例 `src/__tests__/navigation.test.js` 或新增顶栏件 | 通知若要真数：`GET /hitl/pending` 的 `count`（**不能当总数用**，契约 `docs/api/contract-v1.md` HITL 一节明写它是一页长度）；搜索今天**无全局检索端点**，建议先摘控件而不是接半截 |
| **G19** | 被部门问题拒绝时，界面叫用户**去做一件界面里做不到的事** | ✅ **已落**（现读@ac84f1a）：`lib/errcodes.js:149` 那句已是做得到的下一步（「联系管理员补上你的部门归属，或改用已登记部门的账号」）；旧句 `rg -n 请先选择部门范围 frontend/src` → 6 命中**全在测试内**（`lib/errcodes.test.js:236` 历史叙述、`lib/__tests__/r270-department-voice.test.js:5` 注释、`:34`/`:53` 反向钉、`components/ui/__tests__/components.test.js:52`/`:59` 夹具串），生产码 0 命中 ⇒ **勿再派** | `lib/errcodes.js`（改成能做到的下一步：找管理员核对部门归属）、`lib/errcodes.test.js`、`lib/r208-alias-coverage.test.js`、`lib/no-bare-code.test.js` | 无需接口。真要给「选择部门范围」的能力属后端语义（Principal 的部门集），归 G10 一并裁 |
| **G20** | 「自研原语」写完了但**接线没收口**：4 枚原语零消费者，5 块屏仍在裸写按钮 | ✅ **已落**（现读@ac84f1a）：裸按钮债已归零——`components/__tests__/r288-native-buttons.test.js:60` `DEBT_TOTAL_RATCHET = 0`，同件 `:54-56` 逐枚写着 `App.vue: 0`、`components/DashboardPanel.vue: 0`、`components/SourceCard.vue: 0`（R410 收的最后八枚已在树）；零消费者原语从四枚降到**两枚**：`UiTable`／`UiDialog` 已被 `AdminPanel.vue:68`/`:336`/`:345` 与 `TracePanel.vue:73`/`:261` 真消费，仍无人接的只剩 `UiUpload` 与 `UiToastHost` ⇒ R265 那串「裸 button 计数」过期、**勿再派**；剩那两枚要不要接线属 `components/ui/**` 那一层的裁定 | 分屏接线，各自落在所在块写集里（H/D/E/F）；用例 `components/ui/__tests__/components.test.js`、`states.test.js` | 无需接口 |

### P3（4 枚）

| # | 症状 | 证据 | 动 |
|---|---|---|---|
| **G12** | 图谱降级承诺的承接面不存在：一级入口撤了，「文档预览里的 依据 / 相关制度」没建，/graph 变成只能手输三元组的表单页 | ✅ **已落**（现读@ac84f1a）：承接面已建在文档预览里——`components/DocumentPreviewModal.vue:40`（R314 判据自述「依据／相关制度」这一格）、`:100` `relationsAboutDocument`、`:138-139` 取数 URL 走 `GET /knowledge-graph/relations`（登记名原文递给取数腿，筛由服务端做，R348）、`:149-160` `readDocumentRelations` 把 `failed`／`empty`／`matched`／`denied` 四支分开（读失败不冒充「没有关联」）；在册钉 `components/__tests__/r314-related-docs.test.js` ⇒ **勿再派**。残格：R314 判据要点里那句「没配 `KNOWLEDGE_GRAPH_STORE_PATH` 时要说『这台服务器没开图谱』而不是『没有依据』」本单**没证**——两枚件里现取「没开」与「未开启」两串只命中一枚无关注释（`DocumentPreviewModal.vue:130`），见 §10.2 | `components/DocumentPreviewModal.vue`、`components/GraphPanel.vue`（复用其行读法）；用例 `panel-states.test.js`、`__tests__/r191-modal-row-scope.test.js`（弹窗形状） |
| **G15** | 删除文档 / 删除会话用**浏览器原生 confirm**，与全站两步确认并存 | ✅ **已落**（现读@ac84f1a）：生产码里原生弹窗**真调用 0 枚**——现取「原生 confirm／alert／prompt」那一族扫描（`rg -n window.confirm frontend/src` 加同族两支，排除 `__tests__`）的 3 枚命中全在注释（`DataPanel.vue:70`、`ArtifactList.vue:19`、`AdminPanel.vue:342`）；删除走两步内联确认（`DocPanel.vue:1236` `isPendingDelete(pendingDelete, rowDeleteKey(row.filename))`）⇒ **勿再派** | `components/DocPanel.vue`、`components/ChatPanel.vue`（接 UiDialog，见 G20） |
| **G17** | 同一屏两个名字：路由叫「问一句」页内叫「智能问答」，路由叫「喂料」页内叫「知识库」 | ✅ **已落**（现读@ac84f1a）：旧那两枚病名都归一了——「问一句」页内 `ChatPanel.vue:1813` `data-testid="chat-screen-name"` 与 `meta.title` 逐字相等（R268）；「喂料」屏那第三枚名字（页内「知识库」）由 R412 收掉，今天页内写的是 `DocPanel.vue:955` `<strong>喂料</strong>`，在册钉 `components/__tests__/r412-one-screen-one-name.test.js`（它同时钉「一屏只许一处主标题」「不许抄出第二处」）⇒ **勿再派**。标签条仍叫「文档／数据」那是内容标签不是屏名（`router/feed-tabs.js:28-29`，R136 判据① 已裁定，不算回归） | `ChatPanel.vue`、`DocPanel.vue`（文案）+ 把 `components/__tests__/r174-screen-name.test.js` 的断言从 1 屏扩到 5 屏（这条一扩，四块屏立刻自证） |
| **G18** | 屏头挂英文装饰字（Approval / Alerts / Knowledge Graph），员工读到的是半中半英 | ✅ **已落**（现读@ac84f1a）：`rg -n 'class="eyebrow">[A-Za-z ]+<' frontend/src --glob "*.vue"` → **EXIT 1 零命中**，最后那枚 `Knowledge Graph` 眉标已随 R314 摘掉（另两枚 09-26 时就已没了）⇒ **勿再派** | 三块屏各一行文案；**不许顺手改 theme.css**（写集独占见 §7） |

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

**总数（R265 当时账）**：缺口 **20 条**，其中 **P1 十一条**（G01、G02、G03、G04、G05、G06、G07、G08、G09、G13、G14）、P2 五条（G10、G11、G16、G19、G20）、P3 四条（G12、G15、G17、G18），另有记账两条 G21/G22 不派工。🔴 R426 现读的三态汇总见 §10.1——这一句里的「缺口枚数」今天已经不能当派工量用。

### 建议先派的三枚（🔴 R426 现读@ac84f1a：这三枚**全部已并树**，照抄这张表派工就是给同一枚单派第二个人）

| 顺序 | 派哪块（=单号落点） | R426 现读：这一枚今天在哪 |
|---|---|---|
| 1 | 块 B（G09 + G13 审批那两处） | **已落**：G09 见 `ApprovalPanel.vue:45-54` + `devFixtures/approval-demo.js:11`；G13 见 `ApprovalPanel.vue:208-211`/`:219-228`（屏上已无源码路径与路由名） |
| 2 | 块 A（G14 + G02 + G13 总览那处） | **已落**：`devFixtures/dashboard-demo.js` 已不在树（`Test-Path` → False），趋势卡走空态 `DashboardPanel.vue:335-338`/`:409`，文档卡三张脸在 `lib/dashboard.js:75-84` |
| 3 | 块 D 的 D1 半（G04 + G03） | **G04 已落**（`lib/sessions.js:888`/`:924`/`:940` + `ChatPanel.vue:1751`）；**G03 仍半**，缺的两格今天写明在后端终态帧与 `lib/sessions.js:478-482`，不在界面 |

**R265 当时的理由（存档，锚 `8613dc7`；这三行理由点名的病灶，今天三处都已改口，见上面那张表）**：

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

---

## 10. R426 现场重判（2026-09-28 · 锚 `ac84f1a` · 工作树 `be-r415`）

性质：**纯账面亲验单**。写集两枚——本文与 `frontend/src/router/__tests__/r316-admin-entry.test.js`（只改头注 `:4-10` 那七行的文字；行数与行序未动，`:13` 仍居原位）。零代码改动、零 commit。判据只认两样：磁盘字节（`文件:行`，当场取）与命令输出（含 EXIT 码）。

### 10.1 §6 那 20 枚的现读三态

- **已落 18 枚**：G01、G02、G04、G05、G06、G07、G08、G09、G11、G12、G13、G14、G15、G16、G17、G18、G19、G20。其中四枚各带一枚**已写在该行**的残格：G05（`GET /alerts/{alert_id}` 仍 0 消费者，已立案 R286）、G07（全站降级横幅仍没有，写域 `App.vue`）、G11（列表行无 `request_id`／`session_id` ⇒ 按会话找回仍缺）、G12（「这台服务器没开图谱」那句没证）。
- **半 2 枚**：G03（缺的两格在后端终态帧 + `lib/sessions.js:478-482`，不在界面）、G10（两枚管理屏已在树；🔴 **R494 现读@5b8d767 把这一格改口**：`/profile` 从今天起有脸——路由 `frontend/src/router/index.js` 的 `name: 'profile'` 一条 + 屏 `frontend/src/components/ProfilePanel.vue` + 唯一取数点 `frontend/src/lib/profile.js`，四格（用户名／角色／部门／档位）逐格真接 `GET /api/v1/profile`，档位那格吃后端新交的只读派生 `profile.clearance`；部门一格只读并写明出路，三张失败脸（403 `department_override_denied`／503 `storage_unavailable`／500 画像保存失败）分开留名；🔴 这一屏今天只有深链，`meta.primary:false` ⇒ 侧栏入口未挂，挂不挂归总控。仍没脸的是 `/slo`、`/audit/events`、`/evaluations`、`/retrieval/debug`）。
- **未落 0 枚**。G21／G22 两枚记账项照旧（本单没重取，见 §10.2 第 4 条）。
- 🔴 这一节是**逐行证据的汇总**，不是达标判定：改口的收益只是让下一班不再重复派已经修完的活；V1 门槛归总控按 `docs/handoff/2026-09-23-v1-acceptance-record.md` 裁。

### 10.2 未证清单（拿不出磁盘字节或命令＋EXIT 的，一律没改口）

1. §1 的 T1 与 T5：判定「有」沿用 R265，本单只把坐标改成现读，没重跑端到端（出处点开→原文核对→批准落账这条链没实测过渲染）。
2. §4.3 的「越权面为零」那半句：本单只现读到 `app/api/v1/alerts.py:382` 是 `_require_alert_management` 的定义处，没逐条复核 R265 点名的后端授权行号（`alerts.py:925` 之类已漂），故该结论原样留着。
3. R265 §9.4 的三处待验项（`GET /users` 是否回 `department`、`POST /upload` 回执是否回 `classification`、`GET /alerts/{id}` 与三枚处置端点的请求体形状）：本单没起服务、没打后端 ⇒ 全部未证。第 2 枚里 `GET /users` 那一格有旁证（`frontend/src/lib/users.js` 的角色与部门词表），但旁证不等于读回。
4. G21／G22：计划书 §2 与 §11 的指路是否仍过期、`docs/current-functionality-2026-09-10.md:335-349` 那笼统口径，本单都没重取。
5. §5.1 产物零远程请求：要 `npm run build` 才取得到，本单按硬约束没跑构建 ⇒ 那两行原样留着（见 §5.2 末行）。
6. §7 八块清单（A–H）与人日估算：本单**没逐块重判**，只把 §8「建议先派的三枚」标了作废并重给现读落点。派工前请按 §6 现读列重新切块——那八块里有六块的缺口已经不在。
7. §3 表 SLO 那行的乙半：`lane_attribution_absent` 今天仍有 8 枚命中（`app/api/v1/observability.py:763` 起），但本单没逐条读那六枚 blocker 的形状 ⇒ 「仍挂」这句沿用。
8. G12 那句「没配 `KNOWLEDGE_GRAPH_STORE_PATH` 时要说『这台服务器没开图谱』」：两枚件里现取「没开」与「未开启」只命中一枚无关注释（`DocumentPreviewModal.vue:130`），没证。
9. 「界面无技术注解」这条今天只跑到「在册反证钉全绿 + 三处上屏原文逐条读到已改口」这一层（SSR 真 HTML 判据在 `r267-overview-no-tech-note.test.js`），没做全仓渲染扫描复现。

### 10.3 越界发现（只报不改）

1. 🔴 **派工词里那枚证据在这棵树上没复现**：`rg -n "已解析|高可信" frontend/src/components/DashboardPanel.vue` → **3 命中**（`:111` 是记下旧假话的注释、`:115` 是四档 `PARSE_STATUS_TEXT` 里的 `ready: 已解析`、`:420` 是表头「其中已解析（条）」）。**结论方向不变**（那三处都是从回执派生的脸，不是「每行写死已解析」），但别拿这条命令当判据；要用的是 `rg -n 高可信 frontend/src` → 5 命中全在 `components/__tests__/r267-overview-real-status.test.js`（`:130`／`:148` 为反向钉）。
2. `frontend/src/components/DocPanel.vue:103` 注释手抄的后端坐标已漂：它写 `app/api/v1/chat.py:3933`，现读 `classification: int = Form(1)` 在 `app/api/v1/chat.py:4419`。该件在 `components/**`（Hume／R421 名下），本单未动。
3. 派工词说「`r416` 的 LEDGER 引用着 `r316-admin-entry.test.js:13`」——**这枚耦合不存在**：`r416` 甲组只扫 `router/index.js` 与 `lib/dashboard.js`（`scanCitations(ROUTER)`／`scanCitations(DASHBOARD)`），它对 r316 那枚件的唯一耦合是丙组要求 router 注释点名一枚在册用例（`r416:458-477`）。真正逐枚对账 r316 里 `path:line` 的是 `frontend/src/lib/__tests__/r420-stale-coordinates-second-blade.test.js`（`ADMIN_ENTRY` 名下五条：`auth.py:106`、`policy.py:44/:95`、`permissions.py:15`、`App.vue:4/448`、`App.vue:27`）。本单按更硬的那条执行：头注改写后**行数与行序一字节未动**（`:13` 今天仍写着 `app/api/v1/auth.py:106`），也没往那枚件里新增任何 `path:line` 引用 ⇒ 两本账都不必改口，`r416`＋`r420`＋`r316` 现跑 59 枚全绿。
4. `frontend/package.json:20` 挂着 `lucide-vue-next` 依赖，而 `frontend/src/components/ui/README.md:4` 写着「本目录不 import `lucide-vue-next`（图标暂用内联 SVG）」：`rg -n lucide frontend/src` 的命中全在注释，生产码 0 import。是死依赖还是待接线本单不判。
5. `docs/handoff/2026-09-27-v2-gap-recheck-2.md`（R407，锚 `5e9f901`）是**第三本**前端账，且比 R309 更接近今天：它已写下 G08／G10／G11／G12／G18 已落、G03 半、G17 半（R412 在途）、G20 半（棘轮 8）。本单现读与之**唯一分歧**是 G17 与 G20——那两枚在 `ac84f1a` 上都已经并树落地（`DocPanel.vue:955` 与 `r288-native-buttons.test.js:60` 棘轮 0）。总控若要定「谁是派工唯一事实源」，请把这三本一起裁，别让下一班挑一本抄。

### 10.4 两本账对不上的地方（点名，不选边）

| 项 | R265（本文当时） | R309 复评（锚 `9344028`） | R426 现读（锚 `ac84f1a`） | 差在哪 |
|---|---|---|---|---|
| G02／T2 | 半：屏上写死「已解析／高可信」 | 已完成 | 有（已落） | R309 与今天一致；R265 过期 |
| G10 | 「管理员没有任何管理屏」 | 「无」＋派 R316 | 半：`AdminPanel` 与 `TracePanel` 两屏已在树（R316／R399 并树） | 🔴 R309 那句 `Test-Path AdminPanel.vue → False` 今天不成立——**两本都不能照抄去派工** |
| G16 | 顶栏两枚死控件、退出无可及名称 | 已完成，但注「通知那格理由今天软了一半，要摆正脸得动 `App.vue` ⇒ 撞 R307」 | 已落：`App.vue:473-478` 已摆上 `NotificationBell`（R333 并树），退出钮有 `logoutLabel`（`:486-487`） | R309 那半句也已过期；今天欠的不是接线 |
| G17 | 半：路由「喂料」／页内「知识库」 | 半：三名并存，派 R313 | 已落：`DocPanel.vue:955` 写「喂料」，钉在 `r412-one-screen-one-name.test.js` | R412 已并树，两本的「半」都不再是今天 |
| G20 | 半：4 枚原语零消费者、五屏裸按钮 | 半：棘轮 20 只准降 | 已落：棘轮 0（`r288-native-buttons.test.js:60`），零消费者原语只剩 2 枚 | 同上，R410 已并树 |
| G03／T10 | 无：界面根本没画 | 半：界面已画，缺「服务端回显出处」 | 半：界面已画且逐轮回显，**缺的两格是** `lib/sessions.js:478-482` 丢 `data` 其余键 ＋ `rg -n terminal_data_filename app` → EXIT 1 | 三本都说「半」但缺的不是同一格：照 R265 派会去补一件已补好的东西，照 R309 派会漏掉那两行解码处 |
| G05 | 半：四枚端点 0 消费者 | 已完成（带残格 R286） | 已落（残格同 R309：`alerts.py:1124` 仍 0 消费者） | 一致；R265 过期 |
| G12 | 无：承接面不存在 | 无（派 R314） | 已落：`DocumentPreviewModal.vue:40`／`:100`／`:138-139`／`:149-160`（R314 并树），只欠那句「这台服务器没开图谱」的取证 | R309 的「无」今天过期 |

- 两本账**方法学**上的一处冲突，值得总控定口径：R309 判定「已完成」用的是 `rg` 命中 + 提交归因（读码），本单同一格用的是磁盘字节 + 在册反证钉 + 命令 EXIT。两者都不等于真机渲染——R265 §9.3 那句「任何真机渲染类判据只给源码证据，不宣布真机已过」今天仍然适用，本文所有「已落」都只到这一层。

### 附：09-28 坐标对账（总控收口，主树 `4037868`）

本文表格里的「现读」一律钉在 `ac84f1a`，而 `app/api/v1/chat.py` 自那以后涨了两笔（R439 摘内部标记、R438 前后的路由改动），所以三枚后端坐标今天已漂，本笔按现读重落地：

| 坐标 | 写下时（`ac84f1a`） | 今天（`4037868`） | 本笔 |
|---|---|---|---|
| `classification: int = Form(1)` | :4110 ✅ 对 | **:4213** | 三处引用（T2 :31／G08 :160／§遗留 :323 那句「现读」）一起改 |
| `POST /queue/{request_id}/cancel` | :4829 ✅ 对 | **:4932** | G06 :158 一处 |
| `GET /sessions` | :920 ❌ **写下时就错**（:920 是 `_ensure_session`，路由在 :3612） | **:3715** | G04 :156 改成路由本体，并点名那一格当时查错了层 |

- 🔴 `chat.py:3933` 这一处**原样不动**：它是 `DocPanel.vue:103` 注释里手抄的那枚旧号，本文 :323 引它正是为了说「这枚已经漂了」，把它改成对的等于抹掉那句反证。真正该改的是前端那行注释，归前端线（`components/**` 在 `Hume`/R421 名下），本笔不动 `frontend/**`。
- ⇒ 教训进在册账：**引用行号必须带上「哪个 commit 的现读」**，否则下次并树就把它变成假话；能引符号就别引行号。

### 附：09-28 坐标对账·第二笔（R404 在途，本笔基点 `4cd0a1c`）

上一笔那张表钉在 `4037868`，属**历史读数，原样不追改**；本笔按那格的规矩另起一段。R404 给 `app/api/v1/chat.py` 的 catalog import 块加进一枚符号（净 +1，落点在本文三枚坐标最靠前那枚之上），又把 `document_version_history` 那条腿重排成「判定先读台账最新那一行、全量读只喂响应正文」（净 +17，落在 `:4214` 与 `:4950` 之间）⇒ 三枚手抄坐标再次打漂，本笔按现读改口：

| 坐标 | 上一笔（`4037868`） | 现在（`4cd0a1c` ＋ R404 在途） | 本笔改了哪几处行内引用 |
|---|---|---|---|
| `classification: int = Form(1)` | :4213 | **:4214** | 三处：T2 :31／G08 :160／§遗留 :323 那句「现读」 |
| `POST /queue/{request_id}/cancel` | :4932 | **:4950** | 一处：G06 :158 |
| `GET /sessions` 路由本体 | :3715 | **:3716** | 一处：G04 :156 |

- 三枚「现在」全属本笔现场 `rg` 取得，不是按偏移换算：`rg -n "classification: int = Form\(1\)" app/api/v1/chat.py` ⇒ 4214；`rg -n "queue/\{request_id\}/cancel" app/api/v1/chat.py` ⇒ 4950；`rg -n -F '@router.get("/sessions")' app/api/v1/chat.py` ⇒ 3716，三发退出码均为 0（同腿的装饰器与函数体分别落 `:3716`／`:3717`，本文引的是路由装饰器那一行）。
- 🔴 `chat.py:3933`（本文 :323 与 :353 两处）**继续原样不动**：它是 `frontend/src/components/DocPanel.vue:103` 注释里手抄的那枚旧号，本文引它正是为了说「这枚已经漂了」，把它改成今天的数等于抹掉那句反证。真正该改的是前端那行注释，`frontend/**` 不归本笔。
- 本文原有 `chat.py` 行号引用 7 枚（:4213 三枚／:4932 一枚／:3715 一枚／:3933 两枚），本笔改其中 5 枚、留 2 枚（正是那两处 `:3933`）；本笔新写的正文里也出现一次 `chat.py:3933`，那是复述「为什么这枚留着不动」，不是第三枚待改的引用。除这三格外，本文没有别的后端行号依赖并树。
- ⇒ 这一笔又把上一笔那条教训演示了一遍：能引符号就别引行号。本单里那枚 `catalog.latest_document_version`／`chat.document_version_history` 走的是符号名，正是为此。