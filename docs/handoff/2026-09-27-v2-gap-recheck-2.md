# V2 缺口复评 2（R407 · 2026-09-27 · 只读复评 + 只交这一枚新文档）

- 取证树：`C:\Users\fengx\PycharmProjects\be-r407`，基点 **`5e9f901`**（detached HEAD，总控预配），开工实取 `git status --porcelain` = **0 行**。
- 主树 `C:\Users\fengx\PycharmProjects\企业智脑` 现取 `git rev-parse --short HEAD` = **`5e9f901`** ⇒ 本文所有行号同时是主树行号，无需换算。
- 纪律：零 commit、零 push、零新建 worktree/分支、不跑 pytest、不起服务、不动容器、不打模型、**不连真库**、不改 `frontend/**` 与任何已跟踪文件。本文那一枚新文档是本轮唯一写入。
- 🔴 行号一律本轮 `rg -n` / `git grep -n` / `Test-Path` 现取；下文每条读数都附命令原文（§9 汇总），抄不出现场的东西一律不写成结论。
- 性质：**这是给总控抄着派工用的队列**，不是进度报告。凡与 `2026-09-26-v2-wave3-dispatch-plan.md` / `-wave4-dispatch-plan.md` 冲突处，以本文为准并照 R408 那单去改那两份账面。

## 0. 为什么要有这一单：那两张波次计划今天**不能**照抄

总控 09-27 夜里差点把波次四那枚「无主、槽一空就投」的 **R341** 投出去。现场三笔：

| 现取 | 命令 | 读数 |
|---|---|---|
| R341 的「前端无脸」前提 | `git log --oneline -S"TREND_PATH" -- frontend/src/lib/dashboard.js` | **`acc092e` R341 并树（施工 `Herschel`/`01a0de12-9e78-7251-9063-ccb671390c05`，基点 `40fe97c`）** |
| 同一枚单在计划里的样子 | `docs/handoff/2026-09-26-v2-wave4-dispatch-plan.md:10` | 仍写「`DashboardPanel.vue:300-305` 明写服务端还没回传时间序列」＋「无主可占：`DashboardPanel.vue`（R341）」（`:20`） |
| 那句假话今天还在不在 | `rg -n "R341" frontend/src` | **10 枚命中**：`frontend/src/lib/dashboard.js:328`、`frontend/src/components/DashboardPanel.vue:55`、`frontend/src/assets/theme.css:2590`、`frontend/src/lib/__tests__/r341-trend-contract.test.js:2` 等 ⇒ 单已交付，只剩注释在指认它 |

波次四那六行**整列作废**：R341（`acc092e`）、R340（`dbb8ba4`）、R342（`e9aac2f`）、R337（`aefa3ce`）全部已并树；波次三那六行同样作废：R332（`ae7dc96`）、R336（`fc13df9`）、R333、R314、R315、R316（`d609165`）亦已并树。基点之后 `git log --oneline 18eebbc..HEAD` = **77 枚提交**。

⇒ 这不是「计划写得不好」，是**本仓事故 #14 那一族（同一枚单派两个 Agent，账面记过九次）**差一次就复现。照旧计划派工 = 给 `Herschel`/`01a0de12` 已并树的那张卡再派一个人。

## 1. 事实源与本轮真正读到的行号

| 用途 | 文件:行（本轮现取） |
|---|---|
| V2 硬要求 12 条 | `docs/version-roadmap-and-next-week-plan-2026-09-22.md:251-264` |
| V2 新增业务能力 6 条 | 同文件 `:266-273` |
| V2 验收目标 5 条 | 同文件 `:275-281` |
| V2 完成判据 | 同文件 `:636-641` |
| V2 可并行 / 必串行 | 同文件 `:369-391` |
| 五道验收门 A–E 的当天读数 | `docs/handoff/2026-09-23-v1-acceptance-record.md:38-46`（A①②③④ + C + D + **B/E 已由业主移出 V1 门槛**） |
| 切读收口唯一事实源 | `docs/handoff/2026-09-17-pgvector-adoption-plan.md`，最新一节 = **§13 `:486-517`** |
| 生产标签四件判据 | 同文件 `:490-499`（表在 `:492-497`） |
| 前端旧复评（当线索用） | `docs/handoff/2026-09-26-frontend-gap-recheck.md`（取证树 `9344028`，**今天已全部重验，见 §2**） |
| 在途六枚写域 | `docs/handoff/2026-09-15-orchestration-board.md:1387-1395`（名册）与 `:5283-5284`（本班实取） |

🔴 未使用 `task_plan.md` / `progress.md` / `findings.md` 判断任何进度（计划书 §10 明令已过期）。

## 2. 三分表（逐条：已落 / 半 / 未落）

口径：**「半」必须写清缺的那一格**。裁定只按今天树上的凭据下，不按任何旧计划下。

### 2.1 V2 硬要求（roadmap `:253-264`）

| # | 要求 | 裁定 | 命令原文 → 实取读数 | 缺的那一格（仅「半」） |
|---|---|---|---|---|
| 1 | `Document`/`DocumentVersion` | **已落** | `git grep -n "CREATE TABLE IF NOT EXISTS document_versions"` → `migrations/0003_legacy_runtime_tables.sql:39`、`app/documents/catalog.py:583`；`... documents` → `migrations/0004_legacy_runtime_compatibility.sql:30`、`app/api/v1/chat.py:1003` | — |
| 2 | `Dataset`/`DatasetVersion` | **已落** | 建表 + `owner_id NOT NULL`：`git grep -n owner -- migrations` → `0002_execution_data_lineage.sql:7`（datasets）、`:34`（dataset_versions）、两枚 owner 索引 `:25`/`:49`；生命周期列 `status TEXT` 该件 12 处（`rg -oN "status TEXT" migrations/0002_execution_data_lineage.sql`） | — |
| 3 | `Artifact`/`CalculationRun` | **已落** | `migrations/0001_core_resource_versions.sql:38`（artifacts + `owner_id` + `expires_at` + `deleted_at`）、`migrations/0002_execution_data_lineage.sql:54`（calculation_runs）；存储层 `app/storage/artifacts.py:65` 字段表、`:276` 空主即拒 | — |
| 4 | 所有资源有稳定 ID、owner 和生命周期 | **半** | `rg -n owner app/api/v1/data.py` → `:78 _dataset_row_owner_id`、出口 `:276`/`:339`/`:389`/`:435`；归因 `git log --oneline -S"owner" -- app/api/v1/data.py` → `aefa3ce`（R337）+ `0e390ee`（R353+R354） | 五枚资源（文档/版本/数据集/版本/产物/计算）**四件套齐**；缺的不是字段是**角色**：`auditor` 今天开不出账号 ⇒ 见 §2.1#5 与 R413。（`alerts` 无 `owner_id` 属**有意**：`migrations/0014` 给的是 `acknowledged_by`/`assigned_*` + `0012` 的 `department`，处置人语义不走 owner，本轮不判成缺口） |
| 5 | staff/manager/admin/auditor 权限统一 | **半** | `app/common/permissions.py:12-17` 四枚角色集齐；🔴 `app/common/rbac.py:31` → `ROLE_CLEARANCE = {"staff": 1, "manager": 2, "admin": 3}`（**无 auditor**）；`permissions.py:41` → `CREATABLE_ROLES = {"staff","manager","admin"}`；`app/common/auth.py:606`/`:653` 对不在该集的角色直接拒；`app/common/sso.py:9` → `ALLOWED_ROLES = CREATABLE_ROLES` | **auditor 有权限集、无密级档位 ⇒ 建不出账号、SSO 递进来也被挡**。四档「统一」今天只有三档可落地。病根不是代码：`permissions.py:34` 原文「密级口径是 **H13，业主未定**，本单不许替它编一档」。前端已经诚实记下这一格：`frontend/src/lib/users.js:48` + `frontend/src/lib/__tests__/r360-user-writes.test.js:604-606`（「auditor 读得到、开不出」）。⇒ **R413，且 H13 未裁前不可投** |
| 6 | 文档、数据、报告、告警资源级隔离 | **已落（读数受 §6b 限制）** | `rg -n owner app/api/v1/data.py:423`（「its owner reaches the deletion through `owner_match`」）、`app/storage/artifacts.py:276`；告警侧 `migrations/0012_...sql:43 ALTER TABLE IF EXISTS alerts ADD COLUMN IF NOT EXISTS department`；越权矩阵读数在 `docs/handoff/2026-09-23-v1-acceptance-record.md:44`（R193 矩阵 51 格真红 0 格） | 隔离**行为**有测试；但生产语料标签全空 ⇒ 「跨密级」那一半在生产上仍是空集，见 §6b。本轮不把它算成新的代码缺口 |
| 7 | PostgreSQL 成为主要业务存储 | **已落（口径要写清）** | 代码默认是 `json`：`rg -n "os.getenv..PERSISTENCE_BACKEND" app` → `app/storage/persistence.py:654`、`app/storage/datasets.py:586`、`app/common/audit.py:146`；可达路径：`docker-compose.yml:31 PERSISTENCE_BACKEND: postgres`、`.env.example:55` 同值；`rg -n PERSISTENCE_BACKEND deploy/docker-compose.server.yml deploy/.env.server.example` → **两枚文件零命中**，因为 `deploy/docker-compose.server.yml:1-8` 自述它是 **overlay**（`-f docker-compose.yml -f deploy/docker-compose.server.yml`）⇒ 生产仍拿到 `postgres` | 缺的不是码：`datasets.py:597-598` 那句日志已经承认「不配 postgres 就只活在内存过渡表里，进程重启即失」。**裸 `uvicorn app.main`（不带 env）今天仍是这条死道**，本轮判为口径事实、不立单（要立得先裁「装机器是否允许裸跑」） |
| 8 | Redis 可靠队列：重试/死信/幂等/失败原因完整 | **已落** | `app/common/reliable_queue.py:5`（模块自述含 retry, dead-letter, idempotency, cancellation）、`:156-180`（`max_attempts`/`idempotency_ttl`）、`:223 enqueue(payload, idempotency_key)`、`:408/:423 _record_discard`、`:435-436 fail_or_retry`、`:497-498 failure()` 原文「so a failed task always carries a reason」、`:529 dead_letter_depth()` | — |
| 9 | 会话、产物、数据和文档重启后可恢复 | **半** | 产物/数据/文档走 PG 表（`migrations/0001`/`0002`）；会话有 PG 面：`rg -n "_require_migrated_tables" app/api/v1/chat.py` → `:1000`（documents）、`:1495`（sessions, session_messages）；另存一份 JSON 主人登记：`app/storage/sessions.py:91 SESSION_REGISTRY_PATH` | **缺的是会话读腿那一格**：生产缺 `sessions`/`session_messages` 表时 `GET /sessions` 与 `GET /sessions/{id}` 抛 `UndefinedTable` 裸 500、无原因码可重试 ⇒ 已立案 **R397 在途**（`docs/handoff/2026-09-15-orchestration-board.md:1389`）。本轮不重复派工，只登记「R397 未并树前这一格不算收口」 |
| 10 | Dashboard 使用真实期间和真实数据 | **已落** | 期间序列：`rg -n trend app/api/v1/dashboard.py` → `:324 GET /dashboard/trend` 段、`:414 _trend_period`、`:900`；可回放：`git grep -n alerts_open -- app/api/v1/dashboard.py` → `:69-70`/`:363 _ALERT_SERIES_SQL`/`:740`，归因 `dbb8ba4`（R340）；`undated` 出口 `:63`/`:410 _TREND_UNDATED`/`:476`，归因 `e9aac2f`（R342）；前端接上：`acc092e`（R341） | 数字不缺，**叙述缺**：`frontend/src/lib/dashboard.js` 仍有四处替服务端说假话 ⇒ **R411**（见 §2.3 残格） |
| 11 | 告警确认/转派/关闭闭环 | **已落** | `rg -n ALERT_ACTION app/api/v1/alerts.py` → `:427 ALERT_ACTION_CLOSE`、`:428 ALERT_ACTION_ASSIGN`、`:450 ALERT_DISPOSAL_WRITE_COLUMNS`、`:520`；时钟列 `migrations/0014_alert_disposal_columns.sql:52-58` | — |
| 12 | 管理员可查看一次运行的关键 Trace | **半** | 后端出口在树：`git grep -n "^@router" -- app/api/v1/observability.py` → `:600 GET /traces/{trace_id}`、`:1392 @router.get(RUN_READOUT_PATH)`、`:1388 RUN_READOUT_PATH = "/runs/{run_id}"`。🔴 前端正脸：`git grep -n TracePanel -- frontend` → **零命中**；`git ls-files frontend/src \| Select-String "Trace\|traces"` → **零命中**；但 `Test-Path C:\Users\fengx\PycharmProjects\be-r399\frontend\src\components\TracePanel.vue` → **True**、`...\lib\traces.js` → **True** | 缺的那一格 = **前端脸在途未并树**（`be-r399` 盘上有件、HEAD 树里没有 ⇒ 对今天的用户是不存在的）。⇒ **R399 已在做，本轮禁止再派第二枚 Trace 单** |

### 2.2 V2 新增业务能力（roadmap `:268-273`）

| # | 能力 | 裁定 | 命令原文 → 实取读数 |
|---|---|---|---|
| 13 | OCR 与扫描 PDF | **已落** | `git grep -n "from app.rag import ocr" -- app/rag/loader.py` → `app/rag/loader.py:33`，同件 `:9` 原文「本地 OCR 通道（app/rag/ocr.py，判据②），有文本层的页一个字都不再 OCR（判据④）」；件在树：`git ls-files app/rag \| Select-String ocr` → `app/rag/ocr.py` |
| 14 | PDF/Word 表格解析 | **已落** | `git ls-files app/rag \| Select-String tables` → `app/rag/tables.py`；接线自述 `app/rag/loader.py:13`「R304: 表格接进来了。带表的 PDF / DOCX 在交给分块器之前先经过 app/rag/tables.py」；旁证 `rg -n table_presence app/common/table_presence.py` 件在树 |
| 15 | Excel/CSV 知识库模式 | **已落** | `git log --oneline -S"R306" -- app` → **`6d00d70` R306 第二棒并树（施工 `Rawls`/`01a0ddab-…`，基点 `217d542`）**；读路径 `app/rag/loader.py:18` 原文「电子表格（`.xlsx`/`.csv`）从 `load_document` 走」；解析件 `app/rag/spreadsheets.py` 在树。⇒ 波次三/四里「R306 施工中」那行**过期** |
| 16 | Dashboard 使用真实数据 | **已落** | 同 §2.1#10 |
| 17 | 知识图谱、审批助手、通知基础能力 | **已落（图谱按定位裁定为非一级）** | 图谱：`git grep -n "^@router" -- app/api/v1/intelligence.py` → `:192 POST /knowledge-graph/relations`、`:248 GET /knowledge-graph/relations`；承接面 `rg -n "relations" frontend/src/components/DocumentPreviewModal.vue` → `:40`（R314 判据）、`:100 relationsAboutDocument`、`:138-139` 取数 URL；一级入口按裁定撤下 `frontend/src/router/index.js:110-113`（`primary: false`）。审批：`chat.py:3012 GET /hitl/pending`、`:3133 POST /approve`、`intelligence.py:128 POST /approval/precheck`、屏 `frontend/src/components/ApprovalPanel.vue` + `hitl/HitlPendingPanel.vue`。通知：`git grep -n "^@router" -- app/api/v1/notifications.py` → `:187 /notifications`、`:212 /read`、`:218 /dismiss`，生产侧写入件 `app/notifications/sources.py` 在树，前端 `frontend/src/components/NotificationBell.vue` + `lib/notifications.js:27-29` + 钉 `components/__tests__/r333-notification-inbox.test.js` |
| 18 | PGVector 正式接入读路径 + 迁移验证 | **半** | 码已齐：旋钮 `app/rag/indexing.py:49-58`、解析 `:2040 read_backend()`、开关 `:2087-2095 pgvector_reads_enabled()`，**读腿可达**：`git grep -n pgvector_reads_enabled -- app` → `app/rag/retriever.py:1106`、`:1166`；候选宽度 R386：`app/rag/pg_store.py:663 HNSW_EF_SEARCH_DEFAULT = 100`、`:678 _APPLY_HNSW_EF_SEARCH_SQL`。🔴 默认未翻：`app/rag/indexing.py:50 INDEX_BACKEND_DEFAULT = "chroma"` | 缺四格，逐格见 §6：**(i)** 翻默认本身 = 业主动作；**(ii)** 格② 热集让路延迟仍欠一台安静机器；**(iii)** 格③ 生产标签四件判据 (a)(b)(c) 全 ❌ ⇒ 记「未验」；**(iv)** 客户尺寸两档差未量（沙盒 1008 枚不可外推）。另：波次三/四写的「R386 挖出两枚量具站错窄档、未派」**今天已过期**，见 §7 |

### 2.3 V2 验收目标（roadmap `:277-281`）+ 前端残格

| # | 目标 | 裁定 | 命令原文 → 实取读数 |
|---|---|---|---|
| 19 | 10～30 名内部用户 | **未落** | `rg -n role scripts/provision_bulk_accounts.py` → `:114` 唯一建号处写死 `"role": "staff"`（`--departments` 可轮换 `:75/:110`，**角色不可轮换**）⇒ 现有量具造不出混合角色的 10～30 人样本，四档权限在这一目标下无法试。⇒ **R417** |
| 20 | 跨部门/跨密级越权命中为 0 | **半（生产侧记「未验」）** | 见 §6b 全表：`(a) ❌ (b) ❌ (c) ❌ (d) ✅ 但只在空集意义上成立`（`docs/handoff/2026-09-17-pgvector-adoption-plan.md:492-497` 本轮逐行读到原文） |
| 21 | 服务重启不丢核心业务数据 | **半** | 同 §2.1#9（会话读腿在途 R397）；此外本轮**没有**做任何重启实测（禁起服务），故只报静态态 |
| 22 | 失败任务可定位和重试 | **已落** | 同 §2.1#8（`reliable_queue.py:497-498` `failure()` 自带原因、`:435` 重试/死信、`:408/:423` 丢弃成因可区分） |
| 23 | 页面主要数据不依赖固定演示值 | **已落（演示区有旗）** | `rg -n 演示 frontend/src --glob "*.vue"` → 生产码命中仅 `DashboardPanel.vue:336` 与 `ApprovalPanel.vue:209/210` 两枚「演示数据」旗（`:210` 逐字交代哪些数是常量、哪些是服务端真值）＋ `InsightPanel.vue:4`/`HitlPendingPanel.vue:37-40` 的「不造演示行」自述 ⇒ 符合 roadmap V1「可以用演示数据，但必须明确是演示数据」，且真实业务区不再吃常量（G02/G14 已复验为已完成） |
| — | 前端残格（旧复评的四枚「半」今天重验） | 见下 | G03 **半**（§3 R414/R415）· G17 **半**（R412）· G18 **已落**（`rg -n class="eyebrow">[A-Za-z ]+< frontend/src --glob "*.vue"` → **零命中**）· G20 **半**（R410）· G08 **已落**（`rg -n classification frontend/src/components/DocPanel.vue` → `:650 form.append('classification', …)`，与波次三/四旧账相反）· G10/G11/G12 **已落**（`AdminPanel.vue` 在树 + `router/index.js:122-125 /admin`；`:100-103 /artifacts`；`DocumentPreviewModal.vue:40-49`） |

## 3. 派工就绪队列（按「槽一空即可投」排序）

取号规则：R402～R406 已被总控立案（`...orchestration-board.md:5289-5293`），R407 = 本单，故新号从 **R408** 起。🔴 本文**不复用** R341/R337/R336/R314/R315/R316/R340/R342（波次三/四已占或已并树），也不复用 R332/R333/R338/R339/R306/R305。

### 第一梯队 · 与在途六枚零交集，槽一空即可投

- **R408 · 派工面账面改口（防本仓事故 #14 复现）**
  - 症状：`2026-09-26-v2-wave3-dispatch-plan.md` 与 `-wave4-dispatch-plan.md` 两列队列**全部**指向已并树的单，而两文件正文没有任何一处写着「作废」——下一班照抄就必然给同一枚单派第二个人。
  - 写域：`docs/handoff/2026-09-26-v2-wave3-dispatch-plan.md`、`docs/handoff/2026-09-26-v2-wave4-dispatch-plan.md`（各加一节「已作废，逐行归因」）＋ `AGENTS.md` 向量库那行里「R386 挖出两枚在册量具自己还站在窄档 40 上量…未派」那半句 ＋ `docs/handoff/2026-09-17-pgvector-adoption-plan.md` §13.三 与 §13.四 第⑦格。🔴 零代码、零测试、零契约。
  - 人日：**0.3**。可投条件：**随时**；落笔前必须自己再跑一遍 §9 里那五条归因命令（不许抄本文的 sha）。
  - 判据：改口后 `rg -n "未派" docs/handoff/2026-09-17-pgvector-adoption-plan.md` 不许再把 R393 治过的那两枚脚本算作未派；两份波次计划在文末同屏可见「作废」二字。
- **R409 · 给回填计划表配一枚现跑的牙**
  - 症状：业主批准 1008 枚标签回填所依据的那张表（`docs/perf/r387-label-lineage-2026-09-27.md` §2.3，本轮读到「74 枚文档 / 923 枚 chunk 可规则回填」「研发 721」）仍是**纸账**——R400 只把「梯级」那一本账改成可复跑，§2.3 没有牙，且原文自己承认现读已漂到 713（同件 §9.5「没有回改原文」）。
  - 写域：`scripts/r387_backfill_estimate.py`（加一枚 `--emit-plan-table`，与既有 `--unlock-ladder` 同法）＋ §2.3 那一节改为由命令渲染 ＋ 新钉 `tests/test_r409_plan_table_is_derived.py`。
  - 人日：**1**。可投条件：**随时**（与六枚在途写域零交集；`test_r387_*`/`test_r400_*` 不在 R396/R401 名下，但落笔前要点名复跑它们，见 §9 最后两条）。
  - 归属：**V1-blocking（弱，链在业主批准输入上）**——A3 回填是 §6b 里 (b)(c) 两件判据的唯一出路，批准材料不可复跑就等于批不了。
- **R410 · 总览那张卡最后 8 枚裸按钮**
  - 症状：全仓剩余裸 `<button>` 债 **100% 落在同一枚文件**，棘轮已经贴到地板。
  - 凭据：`rg -c "<button" frontend/src/components --glob "*.vue"` → `DashboardPanel.vue:8`（其余命中全在 `ui/` 原语自身：`UiUpload.vue:3`/`UiToast.vue:2`/`Ui{Button,Dialog,Table,Select,Tabs}.vue:各 1`）；`frontend/src/components/__tests__/r288-native-buttons.test.js:52` → `'components/DashboardPanel.vue': 8`、`:56` → `DEBT_TOTAL_RATCHET = 8`、`:55` 原文「贴边」。
  - 写域：`frontend/src/components/DashboardPanel.vue` ＋ 同件 `:52`/`:56` 两格数字（🔴 只准降）＋ 需要时补一枚渲染态钉（照 `r278-topbar.test.js` 那套「挂一次真壳层、数屏上真的 `<button>`」姿势，🔴 不许退回源码正则计数——R307 第二棒已经把那条路判成假刀）。
  - 人日：**0.5**。可投条件：**随时**；🔴 与 R411 同屏不同文件 ⇒ 允许并发，但若 R411 需要动 `DashboardPanel.vue` 里那几句文案，两枚合一枚。
- **R411 · `lib/dashboard.js` 四处替服务端说假话**
  - 症状：后端从 R284 起**恒**回 `documents_ready`，前端却还写着「线上今天就是这一张脸」「等后端把已解析篇数一起回传」——一句永远兑现不了的承诺挂在一枚取不到的分支上。这正是 R341 交回时自己登记、明确「越界未做」的第一格。
  - 凭据：`rg -n documents_ready app/api/v1/dashboard.py` → `:315` 在 payload 里无条件出现，`:311-314` 原文「this key is never conditional」；前端 `frontend/src/lib/dashboard.js:54`「（线上今天就是这一张脸）」、`:58`「🚫 后端补上这一数之前…」、`:66-67` `DOCUMENTS_UNRECORDED_HINT`、`:176`「后端今天还没回这一数」。
  - 写域：`frontend/src/lib/dashboard.js`（注释 + `DOCUMENTS_UNRECORDED_*` 那一支的去留）＋ 按旧形状钉住它的现存夹具。**不含** `DashboardPanel.vue` 除非必须改挂载名。
  - 人日：**0.5**。可投条件：**随时**（六枚在途无一持有该文件）。
- **R412 · 喂料屏三名并存**
  - 症状：同一屏路由叫「喂料」、标签叫「文档」、页内叫「知识库」——员工嘴里说的和屏上写的是三个名字。
  - 凭据：`rg -n 知识库 frontend/src/components/DocPanel.vue` → `:354`/`:361`/`:501`/`:955`/`:1148`/`:1151`；路由名 `frontend/src/router/index.js:69`（`title: 喂料`）。旧复评 G17 判「半」，本轮复核**仍是半**（问一句那一半已收，`ChatPanel.vue` 屏名与 `meta.title` 逐字相等）。
  - 写域：`frontend/src/components/DocPanel.vue`（纯文案两行）；若顺手把屏名钉从三枚扩到全屏 ⇒ 追加 `frontend/src/router/__tests__/r136-screen-names.test.js`（🔴 那件明写「今天带页级屏名的屏就三枚」并钉死枚数）。
  - 人日：**0.3**。可投条件：**随时**（与 R399 只共用 `frontend/src` 这个前缀，不共用文件 ⇒ 判可并发）。
- **R417 · 批量建号只建得出 staff**
  - 症状：V2 验收第 19 条（10～30 名内部用户）今天没有量具——脚本把角色写死了。
  - 凭据：`rg -n role scripts/provision_bulk_accounts.py` → `:114` `"role": "staff"`（唯一建号点），`:75`/`:110` 只有 `--departments` 会轮换。
  - 写域：`scripts/provision_bulk_accounts.py`（加 `--roles`，缺省仍 `staff` ⇒ 旧读数一字不变）＋ 新钉 `tests/test_r417_bulk_role_mix.py`。🔴 不碰 `app/common/permissions.py`（那是 R413 的真源）。
  - 人日：**0.5**。可投条件：**随时**。归属：**V2 之后**（它不挡 A–E 任一格，只挡 V2 第 19 条的取证）。
  - ⚠ 诚实边界：`--roles` 里放 `auditor` 会撞上 R413 那道 `CREATABLE_ROLES` 拒收。要么本单只开 manager/admin 两档并写明 auditor 待 H13，要么排在 R413 之后。

### 第二梯队 · 写集与在途相交，必须串行

- **R413 · auditor 有权限集、无密级档位**
  - 症状：四档角色里的一档**开不出账号**：`app/common/rbac.py:31 ROLE_CLEARANCE = {"staff": 1, "manager": 2, "admin": 3}` 少 auditor ⇒ `app/common/permissions.py:41 CREATABLE_ROLES` 不收它 ⇒ `app/common/auth.py:606`（建号）/`:653`（改派）拒，`app/common/sso.py:9 ALLOWED_ROLES = CREATABLE_ROLES` 连 SSO 递进来的 auditor 身份也挡。
  - 写域：`app/common/rbac.py`、`app/common/permissions.py`、两枚差集钉（`permissions.py:36-38` 自述：`ROLE_PERMISSIONS - CREATABLE_ROLES` 与 `ROLE_PERMISSIONS - ROLE_CLEARANCE` 必须**恰好** `{auditor}`）、`frontend/src/lib/users.js:48` 与钉 `lib/__tests__/r360-user-writes.test.js:604-608`。
  - 人日：**1**（若 H13 裁「auditor 与 staff 同档」则 0.3）。
  - 🔴 可投条件：**业主先裁 H13（密级维度）**。未裁不许投——`permissions.py:32-39` 那段就是为「不许把未决问题偷换成静默默认值」写的，硬派 = 逼执行层造一档假密级。归属：**V2 之后**（它不挡 A–E 今天的读数：五道门里没有 auditor 那一臂）。
- **R414 · 空部门上传静默成功 + 终态帧不回显 + 一处字面转义（同一枚文件，建议一笔带走）**
  - 症状 a（**最重**）：`POST /upload` 在 `principal.department` 为空时**照收**，文档落成 `department=''`，`filters.py` 的部门谓词于是恒空集 ⇒ 员工看到「上传成功」，那篇文档**谁都检索不到**。这是 R387 取证给出的修法 **A2**，本轮现取仍**未做**：`rg -n department app/api/v1/chat.py \| rg ":4088"` → `department = str(getattr(principal, "department", "") or "")` 之后一路放行，全仓 `git grep -n department_scope_required -- app` 只命中 `contracts.py:271`/`tools.py:122`/`data.py:55` 三枚**非上传**出口。
  - 症状 b：终态读数里从不回 `data_filename` ⇒ 屏上「本轮数据表」那一句只能报界面自己发出的那一份（旧复评 G03，本轮复核仍是半）。`rg -n data_filename app/api/v1/chat.py` → `:1196`（入站模型）、`:2255/:2257/:2288/:2290`（全是入站读法，**零枚出站**）。
  - 症状 c：`app/api/v1/chat.py:4083` 的 docstring 里躺着一枚**字面** 6 字符 `\u2019`（不是右单引号），同句还有 `uploader''s` 双撇号。字节级证据：`b.count(rb'\u2019')` → **1**；`b.decode("utf-8").count("\u2019")` → **0**。归因 `git log --oneline -S"uploader''s" -- app/api/v1/chat.py` → `c21c342`。
  - 写域：`app/api/v1/chat.py` ＋ `docs/api/contract-v1.md` 文末 ＋ 新钉 `tests/test_r414_*`。人日：**2**。
  - 🔴 可投条件：**必须排在 R397 结案之后**（R397 在途写域含 `app/api/v1/chat.py`，见 §4）。三格同文件 ⇒ 拆成三枚就是三次串行排队，反而更慢，故建议一笔带走；若总控要拆，`chat.py` 上任何两枚都不得并树。
  - 归属：a = **V1-blocking**（它是 §6b 四件判据里 (a)(b)(c) 唯一可用代码推动的那半格，且直接决定「越权 0」是真判据还是空集）；b/c = V2 之后。
- **R415 · 让「本轮数据表」那一句改口报服务端那一份**
  - 症状：`frontend/src/components/ChatPanel.vue:591` 原文自认「要说出服务端那一份，需要后端在终态读数里带 `data_filename` —— 已写进转出项」；屏上 `:1903-1904` 那个 `data-testid="data-table-readout"` 现在报的是界面自己发出去的那一份。
  - 写域：`frontend/src/components/ChatPanel.vue` ＋ 新钉。人日：**0.5**。
  - 可投条件：写集与六枚在途**零交集** ⇒ 可与 R414 并发开工；🔴 但**验收必须等 R414 并树**（数据源在它那儿）。这条要逐字写进派工词，否则执行层会自己造夹具冒充服务端回执（本仓为这一条记过假绿）。
- **R416 · `router/index.js` 两处注释说「入口还没接线」，而同树已通过的钉证明接了**
  - 症状：`frontend/src/router/index.js:116`「壳层今天还不认识角色」、`:166-168`「今天它还没有消费方 —— App.vue 的侧栏仍按 navigation 渲染」。现场反证：`App.vue:4` import `navigationForRole`、`App.vue:448` `v-for="item in navigationForRole(userRole)"`，且 `frontend/src/router/__tests__/r316-admin-entry.test.js:106-118` 正是钉这件事的用例（同 commit `d609165` 里注释与实现自相矛盾）。
  - 写域：`frontend/src/router/index.js`（纯注释）。人日：**0.2**。
  - 🔴 可投条件：**必须排在 R399 结案之后**——R399 在途写域第一枚就是 `frontend/src/router/index.js`（`...board.md:1391` 本班改口段逐字列着），同树两枚即写域冲突 ⇒ 直接判不可投。

## 4. 撞车表（每枚写域 × 在途六枚，逐枚比）

在途六枚按 `...orchestration-board.md:5283-5284` 本班实取：**R395** `Aquinas`／**R396** `Lovelace`／**R397** `Ampere`／**R398** `Boole`／**R399** `Feynman`／**R401** `Herschel`。🔴 一条账面滞后要先说：HEAD `5e9f901` 的提交标题就是「并树 R398」⇒ **R398 名义在途、实际已并树**，它那三枚测试件写域今天已释放；本文仍把它列进比对（照总控口径），但凡落在 `test_r132_*`/`test_r134_*`/`test_r120_*` 上的候选单，判据要按「已释放」重算一次。

| 新单 | R395 `app/agents/**` | R396 `tests/test_r377_*`+`tests/test_r383_catalog_*`+`scripts/r396_anchor_ledger.py` | R397 `app/api/v1/chat.py`+`tests/test_r384_*`+`tests/test_r391_*` | R398 `tests/test_r132_*`+`test_r134_*`+`test_r120_*`+runbook §8 | R399 `frontend/src/router/index.js`+`components/TracePanel.vue`+`lib/traces.js`+新钉 | R401 `tests/fixtures/business_evaluation_100.jsonl`+评测两枚守卫+`scripts/check_eval_evidence_coverage.py` | 结论 |
|---|---|---|---|---|---|---|---|
| R408 docs 改口 | 无 | 无 | 无 | 无 | 无 | 无 | **可投**（零交集；落笔前自跑归因命令） |
| R409 计划表配牙 | 无 | 无（碰 `test_r387_*`/`test_r400_*`，不在其名下） | 无 | 无 | 无 | 无 | **可投**；点名复跑 `test_r387_label_ruler_teeth.py`+`test_r400_backfill_ladder_pins.py` |
| R410 裸按钮 | 无 | 无 | 无 | 无 | 无（不碰 router） | 无 | **可投**；与 R411 同屏不同文件 ⇒ 可并发 |
| R411 lib/dashboard.js | 无 | 无 | 无 | 无 | 无 | 无 | **可投** |
| R412 屏名文案 | 无 | 无 | 无 | 无 | 无（`r136-screen-names.test.js` 不在其写域） | 无 | **可投** |
| R413 auditor 档位 | 无（`app/common/**` 不在 `app/agents/**` 下） | 无 | 无 | 无 | 无 | 无 | **不可投（非撞车）**：等业主裁 H13 |
| R414 chat.py 三格 | 无 | 无 | 🔴 **同文件 `app/api/v1/chat.py`** | 无 | 无 | 无 | **必须串行，排在 R397 之后** |
| R415 ChatPanel 改口 | 无 | 无 | 无（不同文件） | 无 | 无 | 无 | **可投（写集）**，但验收等 R414 并树 |
| R416 router 注释 | 无 | 无 | 无 | 无 | 🔴 **同文件 `frontend/src/router/index.js`** | 无 | **必须串行，排在 R399 之后**；同树两枚即判不可投 |
| R417 建号角色 | 无 | 无 | 无 | 无 | 无 | 无（不碰评测 fixture/守卫/量具） | **可投** |

同树规则复述：**九枚新单里没有任何两枚共用一枚文件**，故第一梯队六枚（R408/R409/R410/R411/R412/R417）彼此可并发；R414 与 R415 之间是**数据依赖**不是写集冲突（不同文件），可以并树排队但验收有先后。

## 5. V1-blocking / V2 之后（判据＝是否挡五道验收门 A–E 或 pgvector 切读收口）

| 归属 | 单 | 为什么 |
|---|---|---|
| **V1 -blocking** | **R414 的 a 半格**（空部门上传拒收） | 它是 §6b 四件判据里唯一能用代码推动的一格；门 **C**（检索与缓存）的「跨部门/跨密级」那一臂今天只有真标签落地才算验过 |
| **V1 -blocking（弱：业主批准的输入）** | **R409** | A3 回填是 (b)(c) 两件的唯一出路，批准材料不可复跑 ⇒ 批不了；它本身不改判据，改的是**能不能批** |
| **V2 之后** | R408（账面）、R410（裸按钮债）、R411（叙述假话）、R412（屏名）、R413（auditor 档位，另需 H13）、R414 的 b/c 两格（回显与 docstring）、R415（回显那半屏）、R416（注释）、R417（批量建号角色） | 逐条比过五道门今天的读数（`v1-acceptance-record.md:38-46`）与计划书 §13 的四格：没有一枚挡得住。B/E 两门已由业主移出 V1 门槛，**不许**再拿「门」替这些单抬优先级 |

🔴 一句反直觉的话放在最前面：**这一轮 V2 剩下的活儿，绝大多数不挡 V1。** 拿 R410/R412/R416 去挤 V1 的槽位就是上一班「波次四」犯的错的另一面——把「看着像缺口」当成「挡门」。

## 6. 两格实测确认（V1/切读收口的现账，不属 V2）

### 6a. `INDEX_BACKEND` 与 `VECTOR_DUAL_WRITE`：今天的默认值与可达路径

判据提醒：**一枚默认值是否可达必须查调用点**（上一班就是靠一个只看签名的 grep 漏掉了 `chat.py` 里的 `Form(1)`）。本轮两枚旋钮都按「定义 → 解析函数 → 调用点」三段各取一次。

| 旋钮 | 代码默认 | 解析处 | 🔴 可达调用点（本轮实取） | 环境面 | 今天实际生效值 |
|---|---|---|---|---|---|
| `INDEX_BACKEND` | `app/rag/indexing.py:50` `INDEX_BACKEND_DEFAULT = "chroma"`；`:58` `INDEX_BACKEND = INDEX_BACKEND_DEFAULT` | `:2040 read_backend()`（`:2073-2075` 先读 env `:2077` 认 `INDEX_BACKENDS`、认不出 `:2079-2084` 落回默认并 warn）；`:2087-2095 pgvector_reads_enabled()` | `git grep -n pgvector_reads_enabled -- app` → **`app/rag/retriever.py:1106`、`:1166`**（语义读腿两处）；记账侧 `indexing.py:1091`、`:1609`、`hot_index.py:678` | 🔴 **零 env 面**：`git grep -ln INDEX_BACKEND` 全仓 41 枚命中，**无一枚**在 `.env.example`/`deploy/.env.server.example`/`docker-compose.yml`/`deploy/docker-compose.server.yml`/`docs/api/contract-v1.md` 里；主树 `rg -n INDEX_BACKEND .env deploy\.env.server` → **零命中** | **`chroma`**（读路径仍在遗留引擎）。旋钮本身可达，但**只能靠运维手搓 env**， shipped 面上没有可抄的落点 |
| `VECTOR_DUAL_WRITE` | `app/rag/pg_store.py:175-191 dual_write_enabled()`：**未设置/空/拼错 ⇒ False**（`:181` 读 env、`:182-185` 认布尔词、`:186-190` 拼错即 warn 后照样关） | 同左（`:63 DUAL_WRITE_ENV = "VECTOR_DUAL_WRITE"`） | `git grep -n vector_mirror\( -- app` → **`pg_store.py:893`、`:930`**；`retriever.py:1252 _open_vector_mirror` → `:1264 pg_store.vector_mirror()` → 调用点 `:1380`、`:1716`；闸门本身在 `pg_store.py:532` 定义、`:544-545` 关则返回 `None`（一条 PG 语句都不发） | `.env.example:89 =off`、`deploy/.env.server.example:66 =off`、`docker-compose.yml:161/204/241 = ${VECTOR_DUAL_WRITE:-off}`；🔴 **主树 `deploy/.env.server:56 =on`** | **`on`**（现役部署）。注意这层差别来自**未跟踪的现场 env**，不在树里 ⇒ 引用时必须写「主树 `deploy/.env.server`」而不是「仓库默认」 |

净读出来的两格：

1. 两枚旋钮的**默认都是安全的那一侧**（关 / 遗留引擎），且拼错值一律落回默认而不是猜——这一格今天仍然成立，`INDEX_BACKEND_DEFAULT = "chroma"` 与 `app/rag/indexing.py:50` 逐字在位（计划书 `:421` 记的同一枚读数，本轮重取未漂）。
2. **新发现（可派、零风险）**：`INDEX_BACKEND` 在**任何 shipped env 面上都不存在**，而 `VECTOR_DUAL_WRITE` 有 `.env.example` + `.env.server.example` + compose 三处说明。⇒ 业主真要翻默认时，没有一处带注释的落点可抄，只能凭记忆写键名；写错一个字母（`pg_vetcor`）的后果 `read_backend()` 的 docstring 自己就举了例。要治的是**文档面**：在 `.env.example` 与 `deploy/.env.server.example` 各加一行**注释掉、值仍为 `chroma`** 的说明。🔴 不许把示例值写成 `pgvector`——那等于替业主翻闸，计划书 §P4 明令 Agent 不改 `.env`，`.example` 是可写的但值必须保持现语义。本轮**未立号**（建议总控并入 R408 那枚纯文档单，同为零代码零测试）。

### 6b. 生产 `department` / `classification` 是否仍全空（验收 C 的格③）

🔴 **本轮没有连真库、没有对任何库发过一条语句**（明令：不许连真库、不许写任何数据）。所以这一格的读数**全部来自今天落在树里的那两份取证**，我核的是「账面今天怎么写、四件判据逐件什么色」，不是重量。

- 现取凭据一：`docs/handoff/2026-09-17-pgvector-adoption-plan.md:490-499`（§13 一）——原句「四臂各 60/60、越权 0/0」在生产上不构成通过证据，`:490` 逐字写着 `chunk_vectors.department` 非空 **0/1008**、`classification` 只有 **1 档**。四件表（`:492-497`）本轮逐行读到：**(a) ❌** 主体侧真带部门（`users.department` 有值 1/3 行，`admin`/`evalbot` 是 SQL NULL）／**(b) ❌** 语料非空部门 > 0 且不同部门 ≥2、不同密级 ≥2／**(c) ❌** 该臂召回 > 0（有部门那条臂恒空集，召回必为 0）／**(d) ✅ 但只在空集意义上成立**。
- 现取凭据二：`docs/perf/r387-label-lineage-2026-09-27.md:70-76` 分桶读数——`chunk_vectors` 1008 行 department 非空 **0**、不同部门 **0**、不同密级 **1**、文件 100；`documents` 105 行非空 **3**（同件 `:79` 逐名点出那 3 枚是 R8 时代探针样本行，`status=retired`，既无 `document_versions` 行也无 `chunk_vectors` 行）；`document_versions` 100 行非空 **0**；遗留引擎 `enterprise_docs` 1008 枚 department 值 `''` **1008**。
- 传播链没坏：同件 `:85-90` 的三桶——①源头就没有 **100 文档 / 1008 chunk**、②源头有但没传下来 **0**、③传下来写错列 **0**。⇒ 修法不许往 `pg_store.py` 打补丁，也不许新迁移补列（列/默认/COMMENT/索引在 `migrations/0010_pgvector_chunks.sql` 现成，同件 `:123` 逐条点了 `:141`/`:163-164`/`:374-375`/`:387-388`）。
- 记账口径（照抄 `:499`，不许改软）：**只有 (d) 单独成立不记通过；只有真出现 breaches > 0 才记「不通过」，且「不通过」优先于「未验」**。沙盒 `eb_r59_sandbox`（4×4×252 合成标签）只证行为、不证客户隔离，不许拿它替 C 翻绿。

⇒ **结论：格③ 今天仍是「未验」，四件判据三红一灰，与 AGENTS.md 记的位置一致，未翻绿、也未被人翻绿。** 出路只有三件：A1（业主补 `users.department`，只能走 `PUT /api/v1/users/department`——`AUTH_DEPARTMENT` 对既有账号无效，凭据 `docs/perf/r387-label-lineage-2026-09-27.md:97`）、A2（空部门拒收 ⇒ **本文 R414**）、A3（规则回填 = 写生产数据 = 业主动作，批准材料的复跑牙 ⇒ **本文 R409**）。A1/A3 都不是 Agent 能做的单。

## 7. 顺手清掉的三格过期账（本轮现场证明它们已不再是缺口）

| 过期账 | 记在哪 | 本轮现场反证 |
|---|---|---|
| 「R291 那格欠账（`lib/artifacts.js` 把 `rawMessage`/`rawCode` 丢在消费口），本班新立，**未派**」 | `...orchestration-board.md:4685-4687` | `frontend/src/lib/artifacts.js:45-49` → `attachRawText()` 两枚字段都搬，`:41` 原文交代语义；`rg -n rawMessage frontend/src` → 命中含 `__tests__/r380-shape-table.test.js:8`（「message/code/rawMessage/label 改判之后屏上该是哪一句」）⇒ **已收口** |
| 「`test_r342_trend_undated_exit.py:367` 那句 `sum(alerts_open)+undated==当下 open` 在新口径下已从律降为巧合，留档**待单**」 | R340 并树标题尾段（`git log -1 dbb8ba4`） | `tests/test_r342_trend_undated_exit.py:21-25` 自述「**戊 · 「各档之和 + 无期间 == 当下未处置的行数」不是律**」，并指向 `_assert_alerts_open_conserves` 与「那几枚 R365 具名钉」⇒ **已被 R365 收口**。（另注：`git grep` 引用的 `:367` 今天已漂——本轮 `:367` 是空行、`:368` 是 `class _BucketClockRow`，**又一例「裸行号不许当引用」**） |
| 「R386 挖出两枚在册量具自己还站在窄档 40 上量（`scripts/r59c_sandbox_corpus.py`、`scripts/r59_recall_compare.py`，**未派**）」 | `AGENTS.md` 向量库那行 ＋ 计划书 §13.三（`:508-510`）与 §13.四 第⑦格（`:516`） | `git show -s --format="%h %ad" f509f36` → **`f509f36 09-27 20:51` 并树 R393**；而计划书最后一次被改是 `772f3f9 09-27 19:01`（`git log --oneline -3 -- docs/handoff/2026-09-17-pgvector-adoption-plan.md`）⇒ **账面比并树早 1 小时 50 分，属纯滞后**。现状：`scripts/r59c_sandbox_corpus.py:380`、`scripts/r59_recall_compare.py:75` 都写 `TRUE_SOURCE = "app.rag.pg_store.configured_hnsw_ef_search"`，后者 `:129/:138 resolve_ef_search()` 缺省现场取真源、`:163 --pg-ef-search default=None` ⇒ 两枚量具已跟生产同宽。**⇒ 这一格不用再派，只需改口（R408）。** |

## 8. 我不敢确认的（静态推断 / 需真机真库 / 缺什么）

1. **§2 全部 23 行都是静态取证**。本轮零运行：没跑 pytest、没跑 vitest、没起服务、没打模型、没碰容器 ⇒ **「有码 + 有钉」我敢报，「端到端真的能跑出来」我一律没报**。特别是 §2.1#8/#11/#12（队列、告警闭环、Trace）三条，我给的是接口与账本在场，不是达标的真机读数。
2. **§6b 的读数不是我量的**。两份额外的现场禁令叠加：我不连真库，也**没去读 `chroma_db/chroma.sqlite3`**——`scripts/r382_chroma_space.py` 那族只读直开引擎文件的做法本身还压着一格未验（「WAL 下只读打开会不会新建/回写 `-shm`/`-wal`」，立案 R405）。⇒ 生产标签今天这一秒是否仍全空，只有总控或业主在真库上重跑那两张分桶表才能定。
3. **R399 的前端 Trace 脸我只 `Test-Path`**。我在 `be-r399` 盘上确认了两枚文件存在，但**没有在那棵树里跑任何 git 命令**（`git status` 会刷新它的 index，等于我伸手动了别人正在施工的树），所以：那两枚文件是否完整、是否可跑、R399 是否即将并树，我一概不知。「半」这一格只支持一句话：**HEAD 里没有**。
4. **R398 的账面状态我判不准**。HEAD `5e9f901` 的标题就是「并树 R398」，而名册 `:5283-5284` 与 `:1390` 仍写 🔵 在途。我按总控口径把它算进六枚，但**不排除名册滞后**。落在 `test_r132_*`/`test_r134_*`/`test_r120_*` 上的候选单需要总控亲自确认一次才算数。
5. **人日估计是执行层口径，不是承诺**。R413 那枚在 H13 裁「auditor 与 staff 同档」时是 0.3 人日，裁「独立一档 + 补密级词表」时我估不出（会连带撞 `filters.py` 与密级展示那一族）。
6. **§2.1#7「裸 `uvicorn` 不带 env 落 JSON/内存过渡表」我只验到读码**。它今天在生产部署形态下不可达（compose 是基栈，server 栈是 overlay，`deploy/docker-compose.server.yml:1-8` 自述），但我**没有实测**过任何一条启动路径，也没有核对 `setup.sh` 与 Dockerfile 的 env 注入次序——那三枚文件本轮我一行都没读。若总控要把「裸进程默认值」抬成一枚单，需要先有人把启动链读一遍再定判据。
7. **§2.3#23「页面主要数据不依赖固定演示值」是文案级判读**。我核的是两枚「演示数据」旗与两处自述，**没跑** `lint:colors`、`npm run build`、`npx vitest run`，也没按旧复评那样逐枚点名跑前端件（六枚 Agent 在施工，CPU 争用会给假读数）。旧复评 §实跑验证 那一节的 99 枚读数一律未采信、也未复现。
8. **我没查过的三面**：① 契约 `docs/api/contract-v1.md` 与 R414/R415 的具体冲突面（只确认了在途六枚无人持有文末，没逐节读）；② V3/V4 的恢复与备份账（R283 那格「备份隔离演练未点名 `chunk_vectors`」今天是否已收，本轮未验）；③ `app/memory/**`、`app/semantics/**`、`app/quality/**`、`app/open_platform` 四棵子树——它们不在 V2 硬要求条目上，本轮没逐条对判据。

## 9. 复算命令清单（全部为本轮原文，逐条可贴回 PowerShell）

```powershell
# 0 盘面
Set-Location C:\Users\fengx\PycharmProjects\be-r407
git rev-parse HEAD                # 5e9f901
git status --porcelain            # 空 / 交回时只多本文一枚
git rev-list --count 5e9f901..HEAD  # 0

# 1 波次计划过期（四枚「待派」其实都已并树）
git log --oneline 18eebbc..HEAD | Measure-Object -Line          # 77
git log --oneline -S"TREND_PATH" -- frontend/src/lib/dashboard.js   # acc092e (R341)
git log --oneline -S"alerts_open" -- app/api/v1/dashboard.py        # dbb8ba4 (R340)
git log --oneline -S"undated" -- app/api/v1/dashboard.py            # e9aac2f (R342)
git log --oneline -S"owner" -- app/api/v1/data.py                   # aefa3ce (R337) + 0e390ee (R353/354)
git log --oneline -S"xlrd" -- app/tools/excel.py                    # fc13df9 (R336)
git log --oneline -S"navigationForRole" -- frontend/src/App.vue      # d609165 (R316)
git log --oneline -S"R306" -- app                                   # 6d00d70 (R306 第二棒)

# 2 前端旧复评今天重验
rg -n "R341" frontend/src
rg -n "classification" frontend/src/components/DocPanel.vue         # G08 已落：:650
rg -n 'class="eyebrow">[A-Za-z ]+<' frontend/src --glob '*.vue'     # G18 零命中
rg -n "知识库" frontend/src/components/DocPanel.vue                 # G17 仍半
rg -c "<button" frontend/src/components --glob '*.vue'              # G20 仍半：DashboardPanel 8
rg -n "data_filename" app/api/v1/chat.py                           # G03 仍半：全入站、零出站
rg -n "rawMessage" frontend/src | Select-Object -First 4            # R291 欠账已收

# 3 两枚旋钮（定义 → 解析 → 调用点）
rg -n "INDEX_BACKEND" app/rag/indexing.py
rg -n "pgvector_reads_enabled" app/rag/retriever.py
git grep -ln "INDEX_BACKEND"        # 全仓 41 命中，无一枚 env/compose 面
rg -n "VECTOR_DUAL_WRITE|dual_write_enabled" app/rag/pg_store.py
git grep -n "vector_mirror(" -- app
rg -n "VECTOR_DUAL_WRITE" .env.example deploy\.env.server.example docker-compose.yml   # 主树跑：deploy\.env.server:56 =on

# 4 auditor 那一格
rg -n "ROLE_CLEARANCE" app/common/rbac.py
rg -n "CREATABLE_ROLES" app/common/permissions.py app/common/auth.py app/common/sso.py
rg -n "auditor" frontend/src/lib/users.js frontend/src/lib/__tests__/r360-user-writes.test.js

# 5 Trace：HEAD 里没有、别人树上有
git grep -n "TracePanel" -- frontend                                # 零命中
git ls-files frontend/src | Select-String -Pattern "Trace|traces"   # 零命中
Test-Path C:\Users\fengx\PycharmProjects\be-r399\frontend\src\components\TracePanel.vue  # True
rg -n "^@router|^RUN_READOUT_PATH" app/api/v1/observability.py

# 6 量具窄档已收（R393）
git show -s --format="%h %ad" f509f36
git log --oneline -3 -- docs/handoff/2026-09-17-pgvector-adoption-plan.md
rg -n "TRUE_SOURCE|configured_hnsw_ef_search" scripts/r59c_sandbox_corpus.py scripts/r59_recall_compare.py

# 7 交回前纪律
git status --porcelain          # 只应有本文一行 ??
git rev-list --count 5e9f901..HEAD   # 0
```

> 取证时间：2026-09-27（本机）。执行人：R407（执行层）。唯一写入 = 本文件。
