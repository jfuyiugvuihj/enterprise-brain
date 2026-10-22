# 并行工作进程工单包 · 第二批（2026-09-16 15:5x，机器 15:40 重启后重开）

第一批（W1/W2/W3）已全部交付并合并：`fe-trunk` A-6 三件套 `8f3523d`、`fe-artifacts` W2 三条 `1253e00`、
`be-r14` R14-A1 `79018e9`；合并链 `d946a5d → d139f69 → 7232fc3`，主树全量 **854 passed / 22 skipped**，
容器门 **22 passed / 0 failed**（`--skip-build`）。第二批从主树 `7232fc3` 另起四棵树。

## 全员共同边界（违反即判未完成）

1. **只在自己的工作树里干活**。分支与路径写在各自工单头部，不许切换分支、不许碰别的树。
2. **禁止一切 Docker / compose / 容器操作**：不 build、不 up、不 exec、不 restart。总控正在用部署栈做演示链路验收，
   任何一次 `compose up` 都会把它的真机结论变成不可复现的噪声。需要真机证据的项一律写「待总控复验」。
3. **禁止 `git add -A` / `git add .`**。提交必须显式列路径：`git add -- <path>` + `git commit -q -m ... -- <path>`。
4. **不许提交 `chroma_db/**`**（它被跟踪但属运行期二进制，跑一次 pytest 就会脏一轮）。也不许对它做反跟踪。
5. 新树**没有 `.env`**（gitignored）。总控已把主树 `.env` 复制进去以对齐宿主 PG 语义；
   若某条测试的**红绿随 PG 可达性变化**，那是被测代码的缺陷，**报告它**，不要在用例里 `os.environ` 硬盖过去。
6. 声称任何缺陷/事实，必须同时给出：`Test-Path` 为真的证据文件路径 + 现场实取的 `Get-Date` 时间戳 + 可复制的命令。
   不接受「实测到」而无原始产物；不接受推断时间。**编造一条引用即整批作废。**
7. 数字必须带口径：命令、时点、`passed/failed/skipped` 三件齐全。「全绿」不算证据。
8. 收工前三条硬要求：工作树 `git status --porcelain -- app frontend docs scripts migrations tests` **为空**；
   自己重跑一次相关测试并把输出贴进最终答复；最终答复用中文，列提交号 + 改动文件 + 判据逐条对照结果 + 未做项与原因。
9. 行号会过期：引用后端只用路由名 / 符号名 / 稳定码。
10. 不许改本文件、不许改看板、不许改跟进单（那是总控的记账面）。需要登记的新发现写在最终答复的「新发现」一节。

## 工单 W4 —— R18 取消标记按「代」生效

**树 / 分支**：`C:\Users\fengx\PycharmProjects\be-r18` · `codex/be-r18`（自 `7232fc3`）
**权威需求**：`docs/handoff/2026-09-15-backend-followup-requests.md` §14（R18，四条事实与判据都在里面，先读它）
**允许改**：`app/api/v1/chat.py`（仅限 `_REQUESTS` 那一段与 `cancel_request`/`is_request_cancelled`/`register_request` 三个函数及其调用点）、
`app/agents/contracts.py`、`app/agents/state.py`、`app/agents/orchestrator.py`（仅取消检查处）、
`docs/api/contract-v1.md`（仅 cancel 一节）、新建 `tests/test_cancellation_epoch.py`。
**禁止改**：`app/rag/**`、`app/semantics/**`、`app/knowledge_graph/**`、`frontend/**`、`migrations/**`、其它任何 `app/api/v1/*.py`。
**做什**：
- 取消状态键改成 (session_id, epoch)。`register_request` 生成本代标识并返回它；一次运行结束（正常/异常/取消）必须在
  `finally` 里弹出本代条目。跨代不得泄漏：上一轮遗留的标记不许让新一轮开局即被判已取消。
- `cancellation_token` 二选一：真用起来（写=本代标识，读=每步比对），或者删干净。**不许留在既不读也不写的中间态。**
- 契约里把「不带 epoch 的 cancel 取消哪一代」写清楚，一句话即可，但必须与实现一致。
**判据（每条都要自己跑）**：
- `tests/test_cancellation_epoch.py` 至少含三组：① 先 `cancel_request` 后 `register_request` 的窗口——取消不许被抹掉；
  ② N 个完整问答之后 `_REQUESTS` 长度为 0；③ 上一轮被取消过的会话，新一轮不许开局即已取消。
- 红底先行：三条判据用例在**未改代码前必须先跑一次并留红证**（证明它们真的能抓到这个缺陷），改后转绿。
- 全量：`.venv\Scripts\python.exe -m pytest -q`，报 `passed/failed/skipped` 三个数与命令时点。


## 工单 W5 —— R15-a/R15-b 图谱定位收口 + 口径晋升路径

**树 / 分支**：`C:\Users\fengx\PycharmProjects\be-r15` · `codex/be-r15`（自 `7232fc3`）
**权威需求**：`docs/handoff/2026-09-15-backend-followup-requests.md` §11（R15-a/b/c/d）。**只做 a 与 b**；
R15-c（阈值进配置表）总控判定并入 §12.4 配置治理，**不许在本单里动 `app/insights/rules.py` / `app/approval/assistant.py`**；
R15-d 已裁定不引入 Neo4j，**不许加任何图数据库依赖**。
**允许改**：`app/knowledge_graph/**`、`app/semantics/**`、`migrations/0009_*.sql`（新建）、
`tests/test_knowledge_graph*.py`、`tests/test_semantic*.py`、`docs/system-design-2026-09-16.md`（仅 §10.4 与 §18 图谱那行）、
新建一份 `docs/design/knowledge-graph-positioning.md`（若需要写定位结论）。
**禁止改**：`app/api/v1/**`、`app/agents/**`、`app/rag/**`、`frontend/**`、`migrations/0001`–`0008`（**已发布的迁移一个字都不许改**，要变更就新开 0009）。
**现场事实（总控 2026-09-16 部署栈实测，可直接引用）**：`GET /api/v1/health/details` 的
`storage.subsystems.knowledge_graph = {"storage_mode":"unavailable","protection":"read_only","detail":"KNOWLEDGE_GRAPH_STORE_PATH is not configured; relation writes are refused"}`，
`problems` 含 `knowledge_graph_read_only`。也就是说**生产里图谱今天就是只读**，这一点必须与文档口径一致。
**做什**：
- **R15-a 二选一，选完就钉死**：要么在 `app/agents/**` 之外**不**假装 Agent 会用它、把 `docs/system-design-2026-09-16.md` §10.4
  改写成「候选断言采集表，非推理引擎」并删掉「第一版存储用 PostgreSQL（邻接表）」那句与代码不符的目标态；
  要么真加一处可测的消费点。判据必须二选一明确落在一边：**不许两边都留一半**。
  注意 §18 那张对照表已经有图谱行了（`dcf385d` 补的），别重复加。
- **R15-b 晋升路径**：`Relation.status == candidate` → 人工核对来源 → 落成 `metric_definitions` 正式口径。
  `0009` 迁移里办两件事：① 把 `metric_definitions` 现在塞在 `filters` JSONB `semantics` 保留键里的
  display label / prose definition 提成真实列（`app/semantics/registry.py` 模块文档自己承认这是欠的）；
  ② 加「已核对：<文档> <段落>」字段，让 warning 从「未核对」变成可消除的枚举。
- **迁移必须幂等**且能被 `scripts/migrate.py` 记账（照 0006/0007/0008 的写法抄，别自创格式）。
**判据**：
- 一条测试跑通「候选关系 → 正式定义 → warning 消失」全链路，断言落在真列上而不是 JSONB 里。
- `docs/system-design-2026-09-16.md` §10.4 的存储介质描述与 `app/knowledge_graph/service.py` 实际实现一致（自己 diff 一遍再交）。
- 全量 pytest 三件数字。

## 工单 W6 —— 总览页接 R14 服务端聚合（`/api/v1/dashboard/summary` 现在是零消费者的悬空端点）

**树 / 分支**：`C:\Users\fengx\fe-dash` · `codex/fe-dash`（自 `7232fc3`）
**背景（总控实测）**：`GET /api/v1/dashboard/summary` 已在部署栈实测 200：
`{"generated_for":"admin","pending_approvals":0,"documents":0,"datasets":5,"alerts":{"total":0,"unread":0}}`；
而 `git grep -c "dashboard/summary" -- frontend/src` **0 命中** ⇒ 这是刚产生的新「悬空未接」。
**允许改**：`frontend/src/components/DashboardPanel.vue`、新建 `frontend/src/lib/dashboard.js`、
新建 `frontend/src/components/__tests__/dashboard-summary.test.js`。
**禁止改**：`frontend/src/App.vue`、`assets/theme.css`、`assets/**`、`lib/http.js`、`lib/errcodes.js`、`package.json`、
`components/InsightPanel.vue`、`components/ApprovalPanel.vue`、`components/GraphPanel.vue`、`frontend/src/**` 下其它任何文件
（W7 正在同窗口改那三个面板，写集互斥是本批唯一的合并前提）。
**做什**：
- 总览四个数字改为**读服务端聚合**，删掉前端自己数行的那套（数 = 拿列表长度 = 页长截断，正是 R14 要消灭的错法）。
- **`alerts` 键可能整个不存在**——那是 W3 定的契约：无告警权限时省略字段。界面必须把「无权限」和「0 条告警」
  渲染成两件不同的事，**不许**用 `?? 0`、`|| 0`、`len(list)` 之类把缺字段折成 0（那就是假健康绿灯）。
- 走统一 axios 实例取数、检查 `response.ok`、失败渲染错误态并给重试；`503 storage_unavailable` 要有独立人话文案，
  不许和「读不到」混成一句。
- 数字要有口径来源提示（这是「按你的可见范围算的」，不是全租户总数）。
**判据**：
- 新测试文件覆盖：① 缺 `alerts` 键 → 渲染「无权限查看告警」而不是 0；② `alerts.total=137` 且列表页长 100 → 显示 137；
  ③ 503 分支文案与「读不到」分支文案不同；④ 四个数字全部来自聚合响应，源码里不再出现自己数行的写法。
- 三闸自己跑并贴数字：`npm run test` / `npm run lint` / `npm run lint:colors`。**色值告警只准降不准涨**；
  若你一条颜色都没新增，`lint:colors` 必须仍是 339 且 `--max-warnings` 不许动。
- `node_modules` 是指向 `fe-trunk` 的目录联接，**禁止 `npm install`**。


## 工单 W7 —— 洞察页接真告警链 + 审批页定位说清（R1 裁定 (c) 的前端半边）

**树 / 分支**：`C:\Users\fengx\fe-alerts` · `codex/fe-alerts`（自 `7232fc3`）
**背景**：看板 §4F.5 已裁定 R1 走 (c)——**后端零改动、`GET /alerts` 对 staff 保持 403**，
「无权限」与「空列表」由**前端分开渲染**。这条裁定至今没有前端实现，所以状态板上 G4 那一行永远不会绿。
同时 `docs/handoff/2026-09-15-frontend-work-checklist.md` 里洞察/审批两页的定位一直没落地（手填阈值、演示数据仍在）。
**允许改**：`frontend/src/components/InsightPanel.vue`、`frontend/src/components/ApprovalPanel.vue`、
新建 `frontend/src/lib/alerts.js`、新建 `frontend/src/components/__tests__/insight-alerts.test.js`。
**禁止改**：`DashboardPanel.vue`、`lib/dashboard.js`（W6）、`App.vue`、`GraphPanel.vue`、`ChatPanel.vue`、
`assets/**`、`lib/http.js`、`lib/errcodes.js`、`package.json`、`app/**`（**后端零改动是本单的前提**，
尤其不许为了让 staff 能看到告警去放宽 `app/api/v1/alerts.py` 的判定——那会推翻 R1 裁定并撞穿权限线）。
**做什（洞察页）**：
- 删掉「手填五格阈值 + 演示数据」，改接真端点：`GET /alerts`、`GET /alerts/rules`、`POST /alerts/rules`、
  `DELETE /alerts/rules/{id}`、`POST /alerts/check`（**这些路由都存在**，用 `git grep -n '@router' -- app/api/v1/alerts.py` 自己核对名字，别照抄本工单的行号）。
- **403 与空列表必须是两张脸**：403 → 「这个账号没有查看告警的权限」+ 说明去哪申请；200 空 → 「当前没有触发中的告警」。
  两者都不许显示成 0 个异常。
- 错误态走 `UiErrorState`、空态走 `UiEmptyState`（`components/ui/` 下已有原语），不许手搓 `.empty-state`。
- 文案走 `lib/errcodes.js` 的 `resolveCode`，不许把裸 snake_case 码名印给用户。
**做什（审批页）**：界面写明它是**报销政策自查工具**（按 checklist L111 的裁定），
**不许**加工单列表、不许加「批准/驳回」按钮（工单模型 C-1 未建，加了就是假审批）。
HITL 的批准入口在对话页 `ChatPanel`，不要在这里复制一套第二判定。
**判据**：
- 新测试覆盖：① 401/403/200-空/200-有数据 四种响应渲染出四种不同结果（源码或真 render 断言均可，但要能判真假）；
  ② 洞察页源码里不再出现手填阈值表单与演示常量；③ 审批页出现「自查」定位措辞且**不存在**审批按钮。
- 三闸自己跑并贴数字；色值告警**只准降不准涨**（不动 `assets/**` 就应当仍是 339）。
- `node_modules` 是目录联接，禁止 `npm install`。

## 交付顺序与合并权

四单的**合并只能由总控做**，顺序固定：**W6 → W7 → W4 → W5**（前端两单先走，因为它们决定明天演示范畴；
W4 涉及契约文本，W5 涉及新迁移，都要在前面都并完之后单独复跑全量）。
每个 Worker 交完就停，不许自己往 `codex/data-file-catalog` 合，也不许替别人收尾。

