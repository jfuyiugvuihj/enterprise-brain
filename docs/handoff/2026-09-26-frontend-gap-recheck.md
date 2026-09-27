# R309 现取复核 · V1 前端缺口清单 G01–G20 / T1–T11

- 取证树：`be-r309`，`git rev-parse --short HEAD` → `9344028`，分支 `codex/be-r309`，交回时 `git status --porcelain` 只多本文一枚。
- 事实源：`docs/handoff/2026-09-26-v1-frontend-gap-list.md`（R265）。本文所有行号**一律在 `9344028` 现取**，R265 的旧行号已漂，一处不复用。
- 基点之后动过前端的提交：`git log --oneline 8613dc7..9344028 -- frontend` → **12 枚**。
- 生产码 / 测试码 / `frontend/**` 零写入；归因一律走 `git log --oneline -S"<符号>" -- <路径>`，不采信提交自述。

## 净账

| 裁定 | 枚数 | 编号 |
| --- | --- | --- |
| 已完成 | 12 | G01 G02 G04 G05 G06 G07 G09 G13 G14 G15 G16 G19 |
| 半 | 4 | G03 G17 G18 G20 |
| 无 | 4 | G08 G10 G11 G12 |

- G05 判「已完成」但带一枚残格（详情端点仍零消费者），且该残格**已立案 R286**，不占新号。
- 本文推翻 R265 三处前提：① G10「先要后端读回」已过期（八枚端点全部在树）；② G07/G16 由「半」升「已完成」；③ **新增一级屏不需要改 `App.vue`**（证据见 §G11），故 G10/G11 由串行改可派。
## G01 · 传完文档不知道能不能被问到 —— **已完成**

    $ rg -n "retrievable|armUploadPoll|再读一次" frontend/src/components/DocPanel.vue
    34:  retrievable: '已可检索',
    62:  if (index === INDEX_STATUS_INDEXED) return 'retrievable'
    347:    armUploadPoll([res.data.filename || item.name])
    509:function armUploadPoll(names) {
    754:                label="再读一次"
    756:                @click.stop="armUploadPoll([row.filename])"

- indexed 已有正脸（`:62` 唯一出口），轮询有限且由人点「再读一次」续（`:78` 注释即裁定）。
- 归因：`git log --oneline -S"armUploadPoll" -- frontend/src/components/DocPanel.vue` → `4e3a71a`（R288 块 E）。

## G02 · 每篇都「已解析」、口径永远「高可信」 —— **已完成**

    $ rg -n "高可信" frontend/src
    → 5 命中全在 frontend/src/components/__tests__/r267-overview-real-status.test.js（:130 :148 为反向钉）
    $ rg -n "definition_source|verified" frontend/src/components/DashboardPanel.vue
    118:const evidenceVerified = computed(() => metricEvidence.value?.provenance?.verified_against_documents === true
    231:      definitionSource: typeof payload.definition_source === 'string' ? payload.definition_source : null,

- 生产码零命中，真值改读服务端回执；文档卡副文案另由 `273b13f`（R274 X-3）与 `77bbae5`（R284 `documents_ready`）收口。
- 归因：`git log --oneline -S"高可信" -- frontend/src/components/DashboardPanel.vue` → `d3d0b93`（R267）。

## G03 · 问出来的数与选的表对不上、无从纠正 —— **半**

    $ rg -n "chat-data-table-select|data-table-readout|dataTableOf" frontend/src/components/ChatPanel.vue
    1891:  <p v-if="dataTableOf(msg)" class="lane-readout" role="status"
    1892:     data-testid="data-table-readout">{{ dataTableOf(msg) }}</p>
    1949:  <label class="lane-label" for="chat-data-table-select">本轮数据表</label>
    1954:    :value="activeDataFilename"
    $ rg -n "data_filename" app/api/v1/chat.py
    1170:    data_filename: str = ""      # 请求模型
    2219: 2221: 2252: 2254: 全是入站读法
    → 终态读数里 0 命中：那一格说的是界面自己发出的那份，不是服务端记下的那份

- 已收：上屏（`:1949`）、就地可改（`:1954`）、逐轮回显（`:1891`）。未收：回显的**出处**。`ChatPanel.vue:591` 注释已自认这一点。
- 要动：`app/api/v1/chat.py`（终态帧补 `data_filename`）、`docs/api/contract-v1.md`、`frontend/src/components/ChatPanel.vue`。
- 🔴 相撞：chat.py 撞 `Planck` R59 块2 + 排队 `R301`/`R308`；契约文末撞 `Kepler` R310；ChatPanel 撞排队 `R293`。→ 见 §B。

## G04 · 换台电脑问过的话全不见 —— **已完成**

    $ rg -n "readBackendSessionList|mergeServerSessions" frontend/src/lib/sessions.js
    924:export async function readBackendSessionList() {
    940:export function mergeServerSessions(rows) {
    $ rg -n "pullServerSessions|从服务器取回" frontend/src/components/ChatPanel.vue
    553:async function pullServerSessions() {
    1694:        >从服务器取回</UiButton>

- 归因：`git log --oneline -S"readBackendSessionList" -- frontend/src/lib/sessions.js` → `90c15bb`（R268）；owner 归还那一半见 `d194d99`（R295）。

## G05 · 告警没法办、看不出别人办过 —— **已完成（带一枚残格）**

    $ rg -n "ALERT_DISPOSAL_COLUMNS|disposeAlert|DISPOSAL_FAILURE_TITLES" frontend/src/lib/alerts.js
    209:export const ALERT_DISPOSAL_COLUMNS = [
    504:export async function disposeAlert(alertId, action, assignee = '', client = http) {
    516:export const DISPOSAL_FAILURE_TITLES = {
    $ rg -n "disposeAlert" frontend/src/components/InsightPanel.vue
    349:    const verdict = await disposeAlert(item.id, action, assignee)
    $ rg -n "alerts/\[" frontend/src        # → exit 1，零命中

- 确认/关闭/指派三枚已接、台账三行只来自读回来的行。归因 `8b0b6ce`（R271）。
- 残格：`GET /alerts/{alert_id}`（`app/api/v1/alerts.py:961`）今天仍零消费者，代价是每次处置重读一发 LIMIT 100。**已立案**：`docs/handoff/2026-09-15-backend-followup-requests.md:3442`、看板 `2026-09-15-orchestration-board.md:4547`，拦路的块 E 已并树 ⇒ 即刻可做，沿用 R286。

## G06 · 排队那轮只能干等 —— **已完成**

    $ rg -n "defineEmits|cancellable|queue-cancel|不排了" frontend/src/components/QueueFace.vue
    31:const emit = defineEmits(['retry', 'action', 'cancel'])
    71:      v-if="face.cancellable"
    76:      data-testid="queue-cancel"
    78:    >{{ face.cancelRetry ? '再试一次取消' : (face.cancelling ? '取消中…' : '不排了') }}</UiButton>

- 归因 `90c15bb`（R268）；`cancel_requested` 那一格由 `c5c89b8`（R282）补齐。

## G07 · 不健康仍然报绿 —— **已完成**

    $ rg -n "EMBEDDING_MODEL_MISSING|QUEUE_UNAVAILABLE|inference_compute|readOnlyProtected" frontend/src/lib/health.js
    25:export const EMBEDDING_MODEL_MISSING = 'embedding_model_missing'
    26:export const QUEUE_UNAVAILABLE = 'queue_unavailable'
    56-62:computeKind / computeDetail / computeErrorCode / computeAgeSeconds
    65:      readOnlyProtected: Array.isArray(body?.storage?.read_only_protected)
    214:export function computeFace(health) {
    288:  ready: '本地模型就绪',
    $ rg -n "runtimeFaces" frontend/src/components/ChatPanel.vue
    242:import { fetchRuntimeHealth, modelState, modelStatusText, runtimeFaces } from '../lib/health.js'
    735:const runtimeFaceList = computed(() => runtimeFaces(runtimeHealth.value))

- embedding / queue / 只读 / 算力四族各自出脸，绿点只在 `:288` 且需真判过。归因 `90c15bb`（R268）。
- 剩「全站降级横幅」要 `frontend/src/App.vue` ⇒ 撞 R307，不计本单。

## G08 · 上传没人问密级 —— **无**

    $ rg -n "classification|密级" frontend/src/components/DocPanel.vue     # → exit 1，零命中
    $ rg -n "form\.append" frontend/src/components/DocPanel.vue
    321:  const form = new FormData()
    322:  form.append('file', file)      # 只发 file
    $ rg -n "classification.*Form" app/api/v1/chat.py
    3890:                          classification: int = Form(1),

- 后端字段原样躺着，前端一个字都不发 ⇒ 全库默认 1 级。零后端可收（`DocPanel.vue` 一枚文件）。→ §A R313。
## G09 · 员工一进审批屏就吃「没有权限」 —— **已完成**

    $ rg -n "ownDepartment|DEPARTMENT_KEY" frontend/src/components/ApprovalPanel.vue
    14:import { DEPARTMENT_KEY, errorDetail, isPermissionDenied } from '../lib/http'
    45:function ownDepartment() {
    47:    return localStorage.getItem(DEPARTMENT_KEY) || ''
    54:const form = ref({ ...demoForm, department: ownDepartment() })
    $ rg -n "department" frontend/src/devFixtures/approval-demo.js
    11:// R277（缺口 G09）：本文件【不再有 department】。

- 界面不再替人填别人的部门。归因 `52054d1`（R270＋R277），三元收口 `7c48f89`。

## G10 · 管理员没有任何管理屏 —— **无**（R265 前提已过期）

    $ Test-Path frontend/src/components/AdminPanel.vue      # → False
    $ foreach ($p in '/users','/profile','/audit/events','/slo','/stage-latency','/evaluations','/traces','/notifications') { rg --no-heading -N "'$p'" frontend/src --glob '!**/__tests__/**' }
    /users => 0    /profile => 0    /audit/events => 0    /slo => 0
    /stage-latency => 0    /evaluations => 0    /traces => 0    /notifications => 0

- 后端读口**全部在树**，「先要后端读回」这一条今天不成立：`app/api/v1/auth.py:90`（GET /users）`:98`（POST）`:123`（PUT /users/password）`:139`（PUT /users/department）`:233/:241`（GET/PUT /profile）；`app/common/auth.py:539/:543` 的回执已带 `department`；`app/api/v1/observability.py:600`（/traces/{id}）`:684`（/stage-latency）`:1130`（/slo）`:1144`（/evaluations）`:1183`（/audit/events）；`app/api/v1/notifications.py:171/:194/:200`。
- ⚠️ 取证注意：`rg -F '/slo'` 会把 `</slot>` 算成命中（我第一次就这么读出了 8 枚假命中）。要么带引号钉 `'/slo'`，要么 `\b/slo\b`。
- 归因：`674353c`（R290 落 PUT /users/department）、`fa8709c`（R299 落通知后端）。
- 要动：`frontend/src/router/index.js` + 新 `frontend/src/components/AdminPanel.vue` + 三枚导航钉（见 §G11）。**不碰 `App.vue`**。→ §A R316。

## G11 · 图与报告藏在「喂料 → 数据」底下 —— **无**

    $ rg -n "import ArtifactList|<ArtifactList" frontend/src
    frontend/src/components/DataPanel.vue:10:import ArtifactList, { advanceDelete, ... } from './ArtifactList.vue'
    frontend/src/components/DataPanel.vue:454:    <ArtifactList />      # 全仓唯一挂载点
    $ rg -n "path:|meta:" frontend/src/router/index.js      # 一级屏仍只有五枚 + 非一级 graph

- 🔴 **翻案（本单最值钱的一格）**：加一级屏不需要动壳层。导航是路由表的纯派生，面板走 `<component :is>`，props 只特判喂料屏：

      frontend/src/router/index.js:117  const isPrimaryScreen = route => isScreen(route) && route.meta.primary !== false
      frontend/src/router/index.js:123  export const navigation = routes.filter(isPrimaryScreen).map(...)
      frontend/src/App.vue:52   const screenProps = computed(() => (route.name === FEED_SCREEN ? { userRole: userRole.value } : {}))
      frontend/src/App.vue:445  <component :is="Component" v-bind="screenProps" @goto="openScreen" @ask="handleAsk" />

- 加屏真正会碰的是**三枚导航钉**（都不在八枚写域里）：`frontend/src/__tests__/navigation.test.js:50`、`frontend/src/router/__tests__/routes.test.js:110`（连带 `:112`）、`frontend/src/router/__tests__/r136-screen-names.test.js:70`。
- 要动：`router/index.js` + 新屏壳（薄封装，只 import `ArtifactList`，**一字不改** `ArtifactList.vue`）+ 上述三钉。与 R316 互撞（同 `router/index.js`、同三钉）⇒ 两枚只能串行或合成一枚。→ §A R315。

## G12 · 图谱降级承接不存在 —— **无**

    $ rg -n "依据|相关制度|relations" frontend/src/components/DocumentPreviewModal.vue   # → exit 1，零命中
    $ rg -n "def list_relations" app/api/v1/intelligence.py
    249:async def list_relations(source_entity: str | None = None, relation: str | None = None, request: Request = None):
    $ rg -n "KNOWLEDGE_GRAPH_STORE_PATH" app
    app/knowledge_graph/service.py:40:_STORE_PATH_ENV = "KNOWLEDGE_GRAPH_STORE_PATH"

- 零后端可收。`GraphPanel.vue:76` 仍是那枚英文眉标 + 手输表单。→ §A R314（与 G18 并一枚）。

## G13 · 屏上读到源码路径与 HTTP 路由 —— **已完成**

现取扫法：剥掉 `<template>` 内注释，只取文本节点与元素节点，再对 `app/`、`.py`、`.vue`、`GET /`、`/api/v1`、`router.` 等匹配。

    vue files=30 textNodes=361 RENDERED HITS=0

- 反证钉在树：`frontend/src/components/__tests__/r267-overview-no-tech-note.test.js`。归因 `d3d0b93`（R267）＋ `52054d1`（R277 收审批那两处）。

## G14 · 总览那条折线是前端常量编的 —— **已完成**

    $ git log --oneline --diff-filter=D --name-status -- frontend/src/devFixtures
    d3d0b93  D  frontend/src/devFixtures/dashboard-demo.js
    $ rg -n "devFixtures" frontend/src --glob '!**/__tests__/**'
    frontend/src/components/ApprovalPanel.vue:16:import { demoForm } from '../devFixtures/approval-demo'   # 唯一生产者引用
    $ rg -n "data-unwired|trend-empty" frontend/src/components/DashboardPanel.vue
    295:<article class="reference-card trend-card" data-testid="dashboard-trend-card" data-unwired="trend">
    303:          <p class="demo-note" data-testid="dashboard-trend-empty">
    $ rg -n "trend|period|series|monthly|aggregate_by" app/api/v1/dashboard.py      # → exit 1，零命中

- 趋势卡换成空态，`insights-demo.js` 已成死文件并被 `r274-devfixtures-readme-matches-tree.test.js:110` 钉成「生产引用 = []」。归因 `d3d0b93`（R267）＋ `21f18b8`（R285＋R287）。
- B-7（趋势聚合端点）另计：后端四个别名键全零命中，这一屏**没有**数据可画，不许有人拿假数补上。

## G15 · 删除走浏览器原生 confirm —— **已完成**

    $ rg -n "window\.confirm|window\.alert|window\.prompt|[^.\w]confirm\(" frontend/src --glob '!**/__tests__/**'
    frontend/src/components/DataPanel.vue:70   # 注释：两步内联确认，不用 window.confirm
    frontend/src/components/ArtifactList.vue:19 # 注释：同上
    → 生产码真调用 0 枚（两枚命中都在注释里）
    $ rg -n "pendingDelete|advanceDelete|isPendingDelete" frontend/src/components/DocPanel.vue
    374:const pendingDelete = ref('')
    394:  const step = advanceDelete(pendingDelete.value, key)
    788:              :label="deleteButtonLabel({ pending: isPendingDelete(pendingDelete, rowDeleteKey(row.filename)), ...

- 归因 `git log --oneline -S"pendingDelete" -- frontend/src/components/DocPanel.vue` → `4e3a71a`（R288）；会话那半 `90c15bb`（R268）。

## G16 · 顶栏两枚死控件、退出钮看不出是退出 —— **已完成（按「摘控件」收口）**

    $ rg -n "logoutLabel|原先摆着" frontend/src/App.vue
    431:  <!-- R278 · G16①②：这里原先摆着两枚按了没反应的按钮（搜索、通知），一并摘掉。
    436:  <button class="logout-link" type="button" :aria-label="logoutLabel" :title="logoutLabel" @click="doLogout">⌄</button>

- 归因 `git log --oneline -S"logoutLabel" -- frontend/src/App.vue` → `ec42480`（R278）。
- ⚠️ 但通知那一枚的「摘掉」理由今天已经软了一半：R299（`fa8709c`）落了 `GET /notifications` / `read` / `dismiss`，前端仍 0 消费者（见 G10 读数）。要摆正脸得动 `App.vue` ⇒ 撞 R307，见 §B。

## G17 · 同一屏两个名字 —— **半**

    $ rg -n "chat-screen-name" frontend/src/components/ChatPanel.vue
    1753:          <span class="chat-title" data-testid="chat-screen-name">问一句</span>   # ✅ 与 meta.title 逐字相等
    $ rg -n "知识库" frontend/src/components/DocPanel.vue
    581:        <strong>知识库</strong>
    717:      <UiEmptyState v-if="docs.length === 0" title="知识库是空的" ...
    $ rg -n "title:|label:" frontend/src/router/index.js frontend/src/router/feed-tabs.js
    frontend/src/router/index.js:67:  meta: { screen: true, title: '喂料', ... }
    frontend/src/router/feed-tabs.js:28: { id: 'docs', label: '文档', component: DocPanel, needsUserRole: true }

- 问一句那半已收（`90c15bb`）；喂料这一屏**三名并存**：路由「喂料」/ 标签「文档」/ 页内「知识库」。
- 只做文案：改 `DocPanel.vue` 两行 ⇒ 零相撞，并入 R313。若要「把屏名钉从三枚扩到全屏」，射程外证据：`frontend/src/router/__tests__/r136-screen-names.test.js:17` 明写「今天带页级屏名的屏就三枚」并钉死枚数 ⇒ 与三枚导航钉同写域。

## G18 · 屏头挂英文装饰字 —— **半**

    $ rg -n 'class="eyebrow">[A-Za-z ]+<' frontend/src --glob '*.vue'
    frontend/src/components/GraphPanel.vue:76:        <div class="eyebrow">Knowledge Graph</div>

- 现取只剩一枚（`InsightPanel.vue:425` 已换「服务端告警账本」，`ApprovalPanel.vue` 眉标已删）。并入 R314（同文件）。

## G19 · 被部门拒绝时叫用户做界面里做不到的事 —— **已完成**

    $ rg -n "message" frontend/src/lib/errcodes.js | rg 部门
    126:    message: '这次没能生成结果：你的账号还没有登记所属部门……请联系管理员补上你的部门归属，或改用已登记部门的账号，然后重新发起一次。',
    $ rg -n "请先选择部门范围" frontend/src
    → 5 命中全在测试内：errcodes.test.js:236（历史叙述）、r270-department-voice.test.js:34/:53（反向钉）、ui/__tests__/components.test.js:52/:59（夹具串）

- 归因 `52054d1`（R270）。

## G20 · 原语写完接线没收口 —— **半**

    $ rg --no-heading -c "<button" frontend/src/components --glob '*.vue'
    DashboardPanel.vue:9    SourceCard.vue:3        # components/ 内非 ui/ 只剩这两处
    ui/Ui{Button,Dialog,Table,Select,Upload(3),Toast(2),Tabs}.vue          # 原语自身，不算欠账
    $ rg -n "DEBT_TOTAL_RATCHET|App.vue|DashboardPanel" frontend/src/components/__tests__/r288-native-buttons.test.js
    42:  'App.vue': 8,
    43:  'components/DashboardPanel.vue': 9,
    44:  'components/SourceCard.vue': 3,
    46:const DEBT_TOTAL_RATCHET = 20
    $ 零消费者原语现取：UiTable => NONE；UiUpload => 只 lib/no-bare-code.test.js:523；UiDialog / UiToastHost => 只 assets/theme.css

- R288（`4e3a71a`）收掉六枚 .vue；剩余三处欠账**全部**落在 R307（`App.vue`/`SourceCard.vue`）与 R293（`DashboardPanel.vue`）写域里，四枚原语在 R291（`components/ui/**`）。⇒ 见 §B，棘轮 20 只准降不准升。
## T 表改口（只列与 R265 判定不同的行）

| 行 | R265 | 现取 | 依据（提交） |
| --- | --- | --- | --- |
| T2 | 半 | **已完成** | `DocPanel.vue:34/:62/:509/:754` ⇒ `4e3a71a`（R288） |
| T6 | 半 | **已完成** | `alerts.js:209/:504`、`InsightPanel.vue:349` ⇒ `8b0b6ce`（R271）；残格 R286 |
| T7 | 半 | **已完成** | `errcodes.js:126`、`ApprovalPanel.vue:45-54` ⇒ `52054d1`（R270） |
| T9 | 半 | **已完成** | `sessions.js:924/:940`、`ChatPanel.vue:553/:1694` ⇒ `90c15bb`＋`d194d99` |
| T10 | 无 | **半** | 屏上已有选择器并可改（`ChatPanel.vue:1949/:1954`）、逐轮回显（`:1891`）；服务端回显缺 ⇒ 见 G03 |
| T11 | 半 | **已完成** | `health.js:25-26/:56-65/:214/:288`、`ChatPanel.vue:242/:735` ⇒ `90c15bb` |
| T3 | 半 | 半（照旧） | 列表行仍无归属键：`app/api/v1/data.py:221-237` 只 filename/size/size_label/modified_at/extension（`:359` 那枚 `owner_id` 属 DELETE 回执，不是列表）；文档行后端已给 `owner_id`/`size_bytes`（`app/documents/catalog.py:236-238`），而 `DocPanel.vue` 行内只画 `row.filename / row.index_status / row.index_reason` |
| T4 | 半 | 半（照旧） | 挂载点仍唯一：`DataPanel.vue:454` ⇒ 见 G11 |
| T8 | 半 | 半（照旧） | 登录页指向的「用户管理」仍不存在（`Test-Path AdminPanel.vue` → False）⇒ 见 G10 |

## A · 现在立刻可派（写域与八枚在途全不相撞）

八枚写域 = 在途五枚（R59块2 / R305 / R307 / R291 / R310）+ 排队三支（R301·R308 同一支、R306、R293）。

### R313 · 喂料屏三格说假话（G08 + G17 文案 + T3 行内真值 + §新发现）

- 症状：① 上传从不发 `classification`，全库默认 1 级；② 明明「有 N 篇被权限藏起来」，屏上却说「知识库是空的」；③ 同一屏页内叫「知识库」、路由叫「喂料」、标签叫「文档」；④ 行上不显示谁传的、多大（后端已给）。
- 文件：`frontend/src/components/DocPanel.vue`（改）＋ 新 `frontend/src/components/__tests__/r313-docpanel-truth.test.js`。**禁碰** `components/ui/**`、`panel-states.test.js`、`assets/theme.css`、`app/**`。
- 判据要点：`form.append('classification', …)` 命中且 `chat.py:3890` 一字未动；`restricted` 存在时改口「另有 N 篇不在你的可见范围」且**不点名文件**（对照 `DataPanel.vue:414` 的 `v-if="!restrictedNotice"` 与 `:444-446`，那张脸已做对，抄它）；行内出 `owner_id`/`size_bytes` 真值；`:581` 那枚页内名与 `meta.title` 统一；本文件裸 `<button` 仍 0、`confirm(` 仍 0。
- 估时 0.75 人日。

### R314 · 图谱降级承接 + 最后那枚英文眉标（G12 + G18）

- 症状：预览里读不到「依据 / 相关制度」；图谱没开时说的是「没有依据」；`GraphPanel` 眉标仍是 `Knowledge Graph`。
- 文件：`frontend/src/components/DocumentPreviewModal.vue`、`frontend/src/components/GraphPanel.vue` ＋ 新 `__tests__/r314-graph-handoff.test.js`。**禁碰** `panel-states.test.js`、`components/ui/**`（`r191-modal-row-scope.test.js` 若不通过先回报，别当场改判）。
- 判据要点：零后端——读 `intelligence.py:249` 的 `GET /knowledge-graph/relations`；没配 `KNOWLEDGE_GRAPH_STORE_PATH`（`app/knowledge_graph/service.py:40`）时文案必须是「这台服务器没开图谱」而不是「没有依据」；`rg 'class="eyebrow">[A-Za-z ]+<' frontend/src --glob "*.vue"` → 0。
- 估时 1 人日。

### R315 · 成果屏归位（G11）

- 症状：图和报告只藏在「喂料 → 数据」标签底下，员工找不回来。
- 文件：`frontend/src/router/index.js`（加一枚 `path:'/artifacts'`、`meta:{screen:true,title:'交成果'}`）＋ 新 `frontend/src/components/ArtifactsScreen.vue`（薄封装，只 import `ArtifactList`）＋ 改三枚导航钉 `src/__tests__/navigation.test.js:50`、`src/router/__tests__/routes.test.js:110`（连带 `:112`）、`src/router/__tests__/r136-screen-names.test.js:70`。**`ArtifactList.vue` 一字不改**（R291 持有 `:394/:463`），只挂不改 ⇒ 不相撞。
- 判据要点：侧栏派生出第六枚入口而 `App.vue` 零 diff（`git diff --name-only` 必须不含 `App.vue`）；新 URL 直达可渲染；`meta.title` 与页内屏名逐字相等；`r141-lane-choice.test.js` 不得改判。🔴 本行原写「`r136-feed-merge.test.js` 不得改判」，09-27 由总控改口：那枚钉的本事是「图谱没被塞回一级」，`toHaveLength` 的枚数只是顺带读数——交出第六枚屏就必然要动它，R315 按「精确改号、定长不降成包含式」处理（5→6，两条 `not.toContain('graph')` 与 `screenRouteIds` 含 graph 一字未动），与 R316 动 `navigation.test.js`/`r136-screen-names.test.js` 同一姿势。从这里生效：禁的是**放宽**（改成 `toContain`/`>=`/删断言），不是禁枚数随屏数长。
- 估时 0.75 人日。

### R316 · 管理屏骨架 · 用户与我的归属（G10，第一片）

- 症状：管理员零管理屏，而登录页早把员工指向「用户管理」；员工也改不了自己密码、看不到自己部门归属。
- 文件：`frontend/src/router/index.js` ＋ 新 `frontend/src/components/AdminPanel.vue`、`frontend/src/components/ProfilePanel.vue` ＋ 同三枚导航钉。
- 判据要点：只读 `auth.py:90`（列表带 `department`）、写 `:139 PUT /users/department`、`:123 PUT /users/password`、`:233/:241 GET/PUT /profile`；`app/**` 零改动；**这一片不碰审计/SLO/评测/trace**（那些屏的口径要先立判据，另单）。
- ⚠️ 别照 §4.3(b) 的老路再造一枚假权限：`App.vue:52` 的 `screenProps` 只把 `userRole` 喂给喂料屏，新屏拿不到，于是**不许**自己去读 `localStorage.eb_role`。正解 = 进屏打 `GET /profile` 由服务端判角色，每枚写口（改密 / 改归属）都以服务端回执为准，客户端只负责「读不到就不画入口」。
- ⚠️ R315 与 R316 抢同一枚 `router/index.js` 与同三枚导航钉 ⇒ **两枚互撞，只能派一枚或合成一枚**（合称一枚估 1.5 人日）。
- 估时 1 人日。

### R286（沿用已立案号，别占新号）· 处置回读改走详情端点

- 症状：每办一次告警都重读一发 LIMIT 100 列表，而专门为此建的 `GET /alerts/{alert_id}`（`app/api/v1/alerts.py:961`）今天零消费者。
- 文件：`frontend/src/lib/alerts.js`、`frontend/src/components/InsightPanel.vue` ＋ 改判 `__tests__/insight-alerts.test.js`、`__tests__/r271-alert-loop.test.js`（这两件不在八枚写域里）。
- 判据要点：处置后打详情端点取回那一行；台账三行仍只来自读回来的行，不许改成「靠回执缓存」（`r271-alert-loop` 现钉 `alertsReads === 2`，改判要连它一起改且必须更尖）；六张处置脸一枚不退化。
- 估时 0.5 人日。

## B · 必须串行（等谁、等什么）

| 缺口 | 等的对象 | 让位标志 |
| --- | --- | --- |
| G03 后端回显 `data_filename` | `Planck` R59 块2 让出 `app/api/v1/chat.py`（块1 已并 `bee9d01`，块2 提交尚未产生）；同文件还压着 `R301`/`R308` 的上传/详情段 | 块2 并树号出现，且 `R301`/`R308` 让位 |
| G03 契约段 | `Kepler` R310 占用「契约文末」 | R310 并树，或由总控代落契约段 |
| G03 界面那半 / G17 扩屏名 | 排队 `R293`（`ChatPanel.vue`、`DashboardPanel.vue`、`panel-states.test.js`） | R293 并树号出现 |
| G16 通知正脸、G07 全站降级横幅 | `Herschel` R307 占用 `frontend/src/App.vue`（8 枚裸按钮）；通知后端已在树（`fa8709c`），只差壳层 | R307 并树 |
| G20 剩余裸按钮 + 四枚原语 | R307（`App.vue`/`SourceCard.vue`）、R293（`DashboardPanel.vue`）、R291（`components/ui/**`、`panel-states.test.js`） | 三枚全并树；棘轮 `DEBT_TOTAL_RATCHET=20` 只准降 |
| B-7 趋势聚合（G14 的后续） | `app/api/v1/dashboard.py` 无主可开工；契约段仍等 R310 | 后端补聚合端点，且不许有人先画假线 |

## 新发现（清单没写，员工会当场骂）

**喂料屏替后端说「知识库是空的」。** 后端明明会挂出「有 N 篇存在但你看不见」，界面把那半句话整枚扔掉：

    app/api/v1/chat.py:4172:    visible, withheld = _classify_document_rows(request, current_documents())
    app/api/v1/chat.py:4175:        # 判据②（两张脸）：形状与 GET /documents 共用 restricted_summary 那一份。
    app/api/v1/chat.py:4176:        result["restricted"] = restricted_summary(withheld, DOCUMENT_TEMPLATE)
    docs/api/contract-v1.md:1058  `restricted` … only when refused
    docs/api/contract-v1.md:1124  … instead of a shorter list plus silence

    $ rg -n "restricted" frontend/src/components/DocPanel.vue     # → exit 1，全件零引用
    236:    const res = await http.get('/documents/catalog', {
    240:    docs.value = (res.data.documents || [])                  # restricted 就这么被丢了
    717:      <UiEmptyState v-if="docs.length === 0" title="知识库是空的" ...

- 对照证据（说明这判据别的屏做得到）：同仓 `DataPanel.vue:414` 的 `v-if="!restrictedNotice"` ＋ `:444-446` 那块通知，正是「两枚控件不共用一句文案」的现成实现。
- 员工视角：一个只有部分可见范围的人，站在有货的库前听到的是「知识库是空的」，于是整屏弃用。
- 写域 = `DocPanel.vue`，已并进 **R313**，不另立单。

## 实跑验证（点名，未跑全量门）

    $ cd frontend; npx vitest run src/components/__tests__/r288-native-buttons.test.js
    Test Files 1 passed · Tests 14 passed
    $ npx vitest run src/components/__tests__/r271-alert-loop.test.js src/components/__tests__/r271-alert-contract.test.js `
        src/components/__tests__/r267-overview-real-status.test.js src/components/__tests__/r268-chat-panel-shell.test.js `
        src/lib/__tests__/r270-department-voice.test.js src/router/__tests__/r136-screen-names.test.js
    Test Files 6 passed · Tests 85 passed

- 这棵树的 `frontend/node_modules` 是指向主树那份的 junction（与 `.venv` 同法），已 gitignore，未提交。
- 未跑 `scripts/run_gate.py`、未起容器、未打模型、未碰 `deploy/**`、未 commit/add/push。

## 诚实账

- **复取到的**：G01–G20 每格都在 `9344028` 亲自跑过命令；T 表只有 T1（出处链路）、T5（待批）沿用 R265 的「有」，我没重新逐钉复取（本可跑 `r150-provenance`/`hitl-*` 那几件，我没跑）。
- **翻案的三格**：G10「先要后端读回」不成立（八枚端点全在树，读数见 §G10）；G07/G16 由半升已完成；G11/G10 由串行改可派——但这一条我只**读码**证明（`router/index.js:117/:123`、`App.vue:52/:445`），**没有实做一枚临时路由去跑 `routes.test.js` 自证**，派工词里请写明「若加屏发现必须动 `App.vue`，立即停下回报，不许越界改壳层」。
- **本轮没跑的**：`npm run lint:colors`、`npm run build`、全仓 `npx vitest run`、任何 `pytest`。R265 与提交自述里的 148/0、build exit 0 我未复现，不作为本文判据。
- **差点读错的一格**：G10 我用 `rg -F '/slo'` 首取到 8 枚假命中，实际那是 `</slot>`；严格读数（引号钉）是 0。下文已把这条写成取证注意事项。
- **R265 旧行号漂移的规模**：`disposeAlert` 定义、`DocPanel` 上传轮询、`pendingDelete` 三处现取行号与清单/上一轮手记都不一致（例如删除两步：清单时代在 `:444-465`，现取在 `:788/:793`）。所有派工词请只抄本文行号。
- 唯一写入 = `docs/handoff/2026-09-26-frontend-gap-recheck.md`。看板与跟进单我只 `rg` 读过、一字未动（它们有 BOM / 裸 CR，动就是事故）。
