# V2 缺口复评 3（R479 · 2026-09-29 · 只读复评 + 只交这一枚新文档）

口径：本单**只读**。除这一枚文件之外零写入；没跑 `scripts/run_gate.py`、没跑 pytest／vitest、没起服务、没碰 `docker` 命令、没打模型、没向任何库发过一条语句。底本 = `docs/handoff/2026-09-27-v2-gap-recheck-2.md`（R407），本单**只把它当底本，不当事实**：下面每一格的读数都是本席今天自己跑出来的，凡引底本只用于点名「推翻了哪一行」。

## 0. 盘面（本席现取）

| 项 | 命令原文 | 实取读数 |
|---|---|---|
| 工作树基点与洁净 | `git rev-parse --short HEAD` · `git status --porcelain \| Measure-Object -Line` | `2ba2bc2` · **0 行**（dirty=0） |
| 主树同一枚基点 | `git -C `主树` rev-parse --short HEAD` | `2ba2bc2`（分支 `codex/data-file-catalog`） |
| 底本之后进树的七枚 | 逐枚 `git -C 主树 merge-base --is-ancestor <sha> HEAD` | `5963dfe d824b10 ef99d89 6fb2fed d8b132f 3dbf80e 2ba2bc2` **全部 rc=0** |
| 再早的八枚在册 sha | 同上一条命令 | `f509f36 69e0035 5621e8d 1b4406a b498c88 ed9f8b0 dbc2047 bee9d01` 全 rc=0 |
| 底本之后盘面动了多少 | `git log --oneline --since="2026-09-27 21:00" \| Measure-Object -Line` | **112 笔** ⇒ 这就是「旧底本不能照抄派工」的量 |
| 台账尺（点名跑，零成本） | `python scripts/audit_plan_ticket_ledger.py`（主树 venv） | rc=**0** · `RESULT=PASS（0 条违规，在册 43 号逐条自证）` · 本席自数 **LANDED 23 ／ PARTIAL 17 ／ ZERO 3** |
| 现役容器 | 本席**未碰**（明令） | 沿用看板 §4DT 与 R470 的在册读数（七枚 healthy），本单不背书 |

台账那一格要说清：§4DT 记的是 **21／19／3**，本席现取是 **23／17／3**。差的正是 `d824b10` 那两笔改判（R40③／R49② 是抄来的过期纸，同日 R237 已并树收掉），那张台账写在 `5963dfe` 时点、早于 `d824b10` ⇒ **归真之后账面欠账少两格**。记下来免得下一班拿 21／19 当今天的数。

## 1. 口径源与今天的有效行号（本席现取，未靠任何摘要）

`docs/version-roadmap-and-next-week-plan-2026-09-22.md`：硬要求 12 条 = `:253-264`（节头 `:247`「### V2：功能完整开发版」），新增业务能力 6 条 = `:268-273`，验收目标 5 条 = `:277-281`，V2 完成判据 = `:636-641`，5.3 并发组 = `:369-391`（必串行链 `:385-388`，`:391` 那句「`PGVector 不能只把 INDEX_BACKEND 改成 pgvector`」仍有效）。行号与底本 §2 三节标题逐一对齐，**未漂**。

其余三本只按派工范围读：底本 §2/§6/§6b/§7、看板 §0 名册 + §4DQ〜§4DT（`:5757-5812`）、计划书 §9.3（`:374-381`）与 §13（`:486-529`）、人闸 H1〜H13（末节 = `docs/handoff/2026-09-17-human-gates.md:365-376`）。`task_plan.md`／`progress.md`／`findings.md` 本单一格未引（计划书 §10 明令过期）。

## 2. 三分表（23 格，逐格本席现取）

裁定词只有四枚：**已落** ／ **半**（必写清缺的那一格） ／ **未落** ／ **本轮推翻上一轮**（必点名底本行号 + 凭哪条命令）。

### 2.1 V2 硬要求（roadmap `:253-264`）

| # | 要求原文 | 裁定 | 命令原文 → 实取读数 | 缺的那一格 |
|---|---|---|---|---|
| 1 | `Document/DocumentVersion` | **已落** | `git grep -n "CREATE TABLE IF NOT EXISTS document_versions"` → `migrations/0003_legacy_runtime_tables.sql:39`、`app/documents/catalog.py:583`；`... documents` → `migrations/0004_legacy_runtime_compatibility.sql:30`。真行数从盘上 raw 件现取（`docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json`）：documents **105**／document_versions **100** | — |
| 2 | `Dataset/DatasetVersion` | **已落** | `git grep -n "CREATE TABLE IF NOT EXISTS" -- migrations/0002_execution_data_lineage.sql` → `:5`（datasets）、`:31`（dataset_versions）；`owner_id TEXT NOT NULL` = `:7`／`:34`，owner 索引 `:25`／`:49`。盘上 raw 件行数：datasets **6**／dataset_versions **6** | — |
| 3 | `Artifact 和 CalculationRun` | **已落（码与列齐；生产库里 CalculationRun 是空表）** | `migrations/0001_core_resource_versions.sql:36`（artifacts）、`:17`／`:38`（owner_id NOT NULL）、`:45`（expires_at）、`:46`（deleted_at）；`migrations/0002_execution_data_lineage.sql:52`（calculation_runs）。盘上 raw 件行数：artifacts **4**／calculation_runs **0**／metric_definitions **0** | 不是代码缺口：`calculation_runs=0` 是**演示库今天没有一次真计算落账**，所以「产物→计算→回读」这条链今天没有端到端读数 ⇒ 进 (乙) 类 |
| 4 | 所有资源有稳定 ID、owner 和生命周期 | **已落**（**本轮推翻上一轮**＝底本 `:51`「半」） | 底本那一格的缺格写的是「缺的不是字段是**角色**：`auditor` 今天开不出账号」。现取：`rg -n "CREATABLE_ROLES" app/common/permissions.py` → `:41 = frozenset({"staff","manager","admin","auditor"})`；`rg -n "ROLE_CLEARANCE" app/common/rbac.py` → `:31 = {staff:1, manager:2, admin:3, auditor:3}`；`git merge-base --is-ancestor 5963dfe HEAD` → **rc=0** | 无。`alerts` 无 `owner_id` 仍属**有意**（`migrations/0014_alert_disposal_columns.sql` 给的是处置人语义），本单不判成缺口 |
| 5 | staff、manager、admin、auditor 权限统一 | **已落**（**本轮推翻上一轮**＝底本 `:52`「半 ⇒ R413 且 H13 未裁前不可投」） | 同 #4 两枚现读 + `rg -n "CREATABLE_ROLES\|ALLOWED_ROLES" app/common/auth.py app/common/sso.py` → `sso.py:9 ALLOWED_ROLES = CREATABLE_ROLES`（真源一枚，`auth.py:606`／`:653` 共用），`permissions.py:16` auditor 权限集原样未动。牙在册：`tests/test_r413_auditor_role_admission.py`（本席现取 21 枚 `def test_` 名，含三本角色账键集两两差集恰为空集那枚）| —（H13 09-28 结案＝甲，auditor 档位＝3，见 `docs/handoff/2026-09-17-human-gates.md:365-372`） |
| 6 | 文档、数据、报告、告警资源级隔离 | **半**（行为已落；**生产侧隔离读数今天仍记「未验」**） | 隔离**行为**第一次有了真库上的有牙读数：`rg -n "MEASURED_WITH_TEETH" docs/testing/r469-sandbox-scope-readout-2026-09-28.md` → 沙盒臂五档全 `MEASURED_WITH_TEETH`、越权 **0 条**，同件 `:74` 无谓词对照组「本可越界」**200 条**（59／48／51／42／0）⇒ 闸门有牙。生产臂 `rg -n "VACUOUS_EMPTY_SET"` → 四档 `0/1008`、`(a) 未验 (b) FAIL (c) FAIL (d) 未验`（`docs/testing/r469-sandbox-scope-readout-2026-09-28.md:53-58`） | 缺的那一格 = **客户真实标签上的隔离读数**。🔴 本单同时作废底本 #6 引的两处旧账：`docs/handoff/2026-09-23-v1-acceptance-record.md:44`「R193 矩阵 51 格真红 0 格」与本席现读 `:69`「越权已结清」——按计划书 §13（`:486`）改写的口径，这两句今天**一律按「未验」读**，不得记通过 |
| 7 | PostgreSQL 成为主要业务存储 | **已落（口径同底本，但今天多了一层实测）** | 代码缺省仍是 json：`rg -n "os.getenv..PERSISTENCE_BACKEND" app` → `app/storage/persistence.py:654`、`app/storage/datasets.py:586`、`app/common/audit.py:146`；可达路径 `docker-compose.yml:31 PERSISTENCE_BACKEND: postgres`、`.env.example:55` 同值；`rg -n PERSISTENCE_BACKEND deploy/docker-compose.server.yml deploy/.env.server.example` → **零命中**（server 栈是 overlay，基栈的值照样到） | 新增读数：`d8b132f`（R470）重启两形后 **35 张 PG 表行数守恒** ⇒ 「主要业务存储」这一格第一次不是推定。裸 `uvicorn app.main` 落 json／内存过渡表那一格本单**未实测**（同底本 §8.6，仍是纸面事实） |
| 8 | Redis 可靠队列：重试、死信、幂等、失败原因完整 | **已落（码）／真机读数欠** | `rg -n "max_attempts\|idempotency_key\|def fail_or_retry\|def failure\|dead_letter_depth" app/common/reliable_queue.py` → `:156`／`:217`／`:223`／`:435`／`:497`／`:529` 六处逐一点名在位 | 台账现取 **R37 = PARTIAL**，欠账原文「③ 队列失败有终态与原因码」⇒ 端到端那一次仍未在真机读过（(乙) 类） |
| 9 | 会话、产物、数据和文档重启后可恢复 | **已落**（**本轮推翻上一轮**＝底本 `:56`「半 ⇒ 会话读腿在途 R397」） | 两笔同时到位：① 会话读腿那枚裸 500 已换具名 503 —— `git log --oneline --grep="R397"` → **`c0c4bcd` 并树 R397**，`git merge-base --is-ancestor c0c4bcd HEAD` → **rc=0**；现读 `rg -n "status_code=503" app/api/v1/chat.py` → `:3723`／`:3728`／`:3765`，`_require_migrated_tables` 调用点 `:1061`（documents）与 `:1556`（sessions, session_messages）。② 重启实测见 #21 | 无。残留边界随 #21 一起登记（本单不重复列） |
| 10 | Dashboard 使用真实期间和真实数据 | **已落**（**本轮推翻上一轮**＝底本 `:57` 的缺格「叙述缺 ⇒ R411」） | `git log --oneline --grep="R411"` → **`4fcca16`**（并树 R411）、`16337fc`（并树 R416，含 `lib/dashboard.js:142` 那一格转授），两枚 `merge-base --is-ancestor` 均 **rc=0**。现读 `rg -n "documents_ready" frontend/src/lib/dashboard.js` → `:52`／`:64`／`:195`／`:555` 四处；`:61-62` 原文已改口成「那句原文只活在那一版里，本件不复读」；牙 `frontend/src/lib/__tests__/r411-screen-never-waits-on-server.test.js` 在树 | —（底本那句「仍有四处替服务端说假话」今天不成立） |
| 11 | 告警支持确认、转派或关闭中的至少一部分闭环 | **已落（码与列齐）／端到端读数欠** | `rg -n "ALERT_ACTION_CLOSE\|ALERT_ACTION_ASSIGN\|ALERT_DISPOSAL_WRITE_COLUMNS" app/api/v1/alerts.py` → `:427`／`:428`／`:450-453`（ack→status+acknowledged_by+acknowledged_at／close→closed_by+closed_at／assign→assignee+assigned_by+assigned_at），时钟列 `migrations/0014_alert_disposal_columns.sql` 在位 | 缺的那一格 = **演示库里今天没有一行真告警可处置**：盘上 raw 件现取 `alerts = 0` 行、`alert_rules = 0` 行。三形闭环有码有列有钉，没有真数据走过 ⇒ (乙) |
| 12 | 管理员可查看一次运行的关键 Trace | **已落**（**本轮推翻上一轮**＝底本 `:59`「半 ⇒ 前端脸在途未并树」） | `git log --oneline --grep="R399"` → **`ed94d16` 并树 R399**，`git merge-base --is-ancestor ed94d16 HEAD` → **rc=0**。`git ls-files frontend/src \| Select-String "Trace\|traces"` → `components/TracePanel.vue`、`lib/traces.js`、`__tests__/r399-trace-render.test.js`、`components/__tests__/r399-trace-screen.test.js`、`lib/__tests__/r399-traces-contract.test.js` 五枚在树；路由现取 `rg -n "traces" frontend/src/router/index.js` → `:35` import、`:138-141` `/traces` 屏（`primary:false, administratorOnly:true`）。后端出口 `app/api/v1/observability.py:615 GET /traces/{trace_id}`、`:1403 RUN_READOUT_PATH="/runs/{run_id}"` | 底本那条命令的坐标今天已漂（它写 `:600`／`:1388`，本席现取 `:615`／`:1403`）——又一例「裸行号不许当引用」。未证照记（沿并树回执自述）：深链依赖 `deploy/nginx.conf` 的 `try_files` 没有起服务实测过 |

### 2.2 V2 新增业务能力（roadmap `:268-273`）

| # | 能力 | 裁定 | 命令原文 → 实取读数 | 缺的那一格 |
|---|---|---|---|---|
| 13 | OCR 和扫描 PDF | **已落（码／依赖／钉三面齐；一张真扫描件的端到端读数本单未取）** | `git ls-files app/rag` → **`app/rag/ocr.py`** 在树；`rg -n "from app.rag import ocr" -- app/rag/loader.py` → `app/rag/loader.py:33 from app.rag import ocr as ocr_channel`。本单新增三面：引擎本地化 —— `rg -n "OCR_ENGINE_MODULE" app/rag/ocr.py` → `:26 = "rapidocr_onnxruntime"`；依赖在册 —— `rg -n "rapidocr\|pypdfium2" pyproject.toml` → `:45-46`（模型随 wheel 分发，装机不联网抓）；牙 —— `tests/test_r298_ocr_channel.py` 在树 | 缺一次「真扫描 PDF 进 → 索引里有字」的端到端读数（(乙)，跑分窗内顺手可取） |
| 14 | PDF/Word 表格解析 | **已落** | `git ls-files app/rag` → **`app/rag/tables.py`；`rg -n "R304" app/rag/loader.py` → `:13`／`:354`／`:359`／`:362`（接线与日志前缀都在）；牙 `tests/test_r300_tables.py` + `tests/test_r304_table_wiring.py` 两枚在册 | — |
| 15 | Excel/CSV 知识库模式 | **已落** | `rg -n "R306" app/rag/loader.py` → `:18-19` 原文「电子表格（.xlsx/.csv）从 load_document 走 app/rag/spreadsheets.py」，`:34` import 在位；件 `app/rag/spreadsheets.py` 在树；牙 `tests/test_r305_spreadsheets.py` + `tests/test_r306_spreadsheets_in_the_upload_path.py` | — |
| 16 | Dashboard 使用真实数据 | **已落** | 同 #10（`4fcca16`／`16337fc` 两枚均 rc=0，`frontend/src/lib/dashboard.js:195` 现读 `documentsReady: countOf(payload.documents_ready)`） | — |
| 17 | 知识图谱、审批助手和通知基础能力 | **已落（图谱按定位裁定为非一级）** | 三面本席各自现取：图谱 `git grep -n "^@router" -- app/api/v1/intelligence.py` → `:192 POST /knowledge-graph/relations`、`:248 GET`；`frontend/src/router/index.js:114` 仍是 `primary: false`。审批 `intelligence.py:128 POST /approval/precheck` 在位，屏 `ApprovalPanel.vue`／`hitl/HitlPendingPanel.vue` 在树。通知 `app/api/v1/notifications.py:187/212/218`（列表／read／dismiss），屏 `NotificationBell.vue` 在树 | 读数分层要说清（**这不是缺口，是账面形状**）：盘上 raw 件现取 `pending_approvals = 177` 行（审批那一面今天**有**真数据），`notification_states = 0` 行（通知那一面今天**没有**一条已读／忽略行为可看）⇒ 通知的端到端读数进 (乙) |
| 18 | PGVector 正式接入读路径 + 完成 Chroma→PGVector 基本迁移验证 | **半**（裁定不变，但**缺的东西换了**） | 本席**进程内现取**（零 env、主树 venv、工作树代码）：`read_backend() = "chroma"`、`pgvector_reads_enabled() = False`、`configured_hnsw_ef_search() = 100`、`dual_write_enabled() = False`。现场面：主树 `rg -n "INDEX_BACKEND\|VECTOR_DUAL_WRITE" deploy/.env.server` → `:56 VECTOR_DUAL_WRITE=on`、**无 INDEX_BACKEND** ⇒ 现役读后端 = chroma。代码面：`app/rag/indexing.py:49 INDEX_BACKENDS={chroma,pgvector}`、`:50 INDEX_BACKEND_DEFAULT="chroma"`、`:2040 read_backend()`、`:2087 pgvector_reads_enabled()`；读腿 `app/rag/retriever.py:1106`／`:1166`，`app/rag/pg_store.py:983` 也走同一枚开关；候选宽度 `app/rag/pg_store.py:663 HNSW_EF_SEARCH_DEFAULT = 100`。迁移那一半：**chunks 1008 == chunk_vectors 1008**（盘上 raw 件本席逐枚数过），`schema_migrations` 到 `0016` | 四格，逐格今天各走到哪：**(i) 翻默认** = 业主动作（见 §4 丙-1）。**(ii) 格② 热集让路延迟** = 仍欠一台安静机器（R428 在册未跑）。**(iii) 格③ 生产标签** = 今天从「没有量具」变成「量具有牙、生产侧仍记未验」（`ef99d89`＝R469 并树 rc=0；业主 09-28 已裁 A3 落在**交付阶段**，见 `docs/handoff/2026-09-17-human-gates.md:375`）。**(iv) 客户尺寸两档差** = 未量（R432／R143 那一族；R432 由 `Zeno` 持有但从未进 §0 名册、产物不采信 ⇒ 视同未做） |

### 2.3 V2 验收目标（roadmap `:277-281`）

| # | 目标 | 裁定 | 命令原文 → 实取读数 | 缺的那一格 |
|---|---|---|---|---|
| 19 | 10～30 名内部用户 | **半**（**本轮推翻上一轮**＝底本 `:76`「未落 ⇒ R417」） | `git log --oneline --grep="R417"` → **`f65d42e` 并树 R417**（rc=0），同一族另一笔 `5963dfe`（R413）顺手改了本件。现读 `rg -n "role\|department" scripts/provision_bulk_accounts.py` → `:10` 用法行已写 `--roles staff manager admin auditor`、`:100-109 build_sample()` 角色逐枚轮换、部门整轮才进、`:121-126 sample_shape()` 报 `pairings/possible_pairings`、`:147 plan_errors()` 向 `CREATABLE_ROLES` 问而不是自带名单；牙 `tests/test_r417_bulk_role_mix.py`（本席现取 29 枚 `def test_`） | 量具齐了，**但没有一次真机 10～30 人混合角色样本**：盘上 raw 件现取 `users = 3` 行、`user_profiles = 0` 行。建号＝往库里写数据，须业主令 ⇒ (乙) 读数 + (丙) 授权各一格 |
| 20 | 跨部门和跨密级越权命中为 0 | **半（生产侧记「未验」）** | 见 #6 全行：沙盒臂四件 (a) PASS_SYNTH_ONLY／(b) PASS（1080／1080 带标签，7 部门 × 4 密级 16 格）／(c) PASS 5/5 召回>0／(d) PASS 越权 0 条；生产臂 (a) 未验／(b) FAIL 非空部门 **0/1008**／(c) FAIL 召回>0 仅 **1/5**（admin 那档）／(d) 未验。整单状态词：**`SANDBOX_MEASURED_PRODUCTION_UNVERIFIED`**（`docs/testing/r469-sandbox-scope-readout-2026-09-28.md:17` 现取） | 🔴 不许把沙盒那五档念成客户隔离。生产那一格今天欠的是**真实标签**，业主已裁它落在交付阶段（A3）⇒ 本单不立代码单，只登记「翻绿之前，C 门这一格永远是未验」 |
| 21 | 服务重启不丢核心业务数据 | **已落·实测一次**（**本轮推翻上一轮**＝底本 `:78`「半·本轮没做任何重启实测」） | 实测在册：`d8b132f`（R470，rc=0）两形（`stop/start` 进程死透、`up -d --force-recreate` 容器替换），只动 `backend worker scheduler` 三格。本席**自己重算了原始件**：`docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json` vs `probe-after-force-recreate.json` → 两枚都 **35 张表**，唯一行数变化 = `audit_events 2426 → 2429`（append-only，演练三次登录各写一条），其余逐枚等值（`sessions 1020／session_messages 2120／documents 105／document_versions 100／artifacts 4／chunk_vectors 1008`）；读腿三形 `GET /sessions = 656` 逐枚相等（`api-before.json` 首 16 位 sha256 = `103C408F6C8E83E1`，本席现取）。本席亲跑量具自检：`python scripts/r470_restart_diff.py --check` → **rc=0／PASS check problems=0** | 🔴 两格边界本单不许越：**实测跑在 09-28 那版镜像上**（R470 §开头自述「本席未重建镜像」；本席现取 `git rev-list --count 9c21490..HEAD` = **18** ⇒ 今天树上并的 18 枚不在那次实测覆盖里），且 PG 容器全程没重启 ⇒ **卷存活没证**。⇒ (乙) 类 R484 |
| 22 | 失败任务可定位和重试 | **已落（码）／真机读数欠** | 同 #8（`app/common/reliable_queue.py:497 failure()` 带原因、`:435 fail_or_retry()`、`:408/423 _record_discard`、`:529 dead_letter_depth()`）；台账现取 R37 = PARTIAL，欠账逐字 = 「③ 队列失败有终态与原因码」 | 同 #8，(乙) |
| 23 | 页面主要数据不依赖固定演示值 | **已落（演示区有旗）** | `rg -n "演示" frontend/src --glob "*.vue"` → 生产码命中只有旗与自述：`ApprovalPanel.vue:209`「演示数据」旗 + `:210` 逐字交代哪些是常量哪些是服务端真值、`DashboardPanel.vue:336` 旗、`hitl/HitlPendingPanel.vue:37/40`「不造演示行／演示常量目录一次都不 import」、`InsightPanel.vue:4`（旧演示机的改口）、`ArtifactList.vue:223`／`TracePanel.vue:5`（后者引的正是本条验收目标）。今日新增：`rg -n "inFlight\|runtimeHealthReadInFlight" frontend/src/lib/health.js` → `:44` 模块级在飞槽、`:53` 对外读数、`:59` single-flight 本体（`6fb2fed`＝R465，rc=0；牙 `lib/__tests__/r465-single-flight.test.js`） | 底本 §8.7 那句「没跑 `npm run test`／`lint:colors`」本席同样成立：**没跑**。在册今日数是总控在 `5963dfe` 时点亲跑的 **129 files／2615 passed／0 failed**、stylelint **148 problems／0 errors**（看板 §4DT:5800）；本单未复现、不背书 |

残格一行（底本 `:81` 那一行今天**整行过期**）：`G03 半（R414/R415）`／`G17 半（R412）`／`G20 半（R410）` 三枚「半」今天都并完树了 —— `git log --oneline --grep="R414\|R415\|R412\|R410"` → **`18ca560`（R414）、`ac84f1a`（R415）、`4344e6d`（R412）、`73dd85f`（R410）**，四枚 `merge-base --is-ancestor` 全 **rc=0**；G18／G08／G10／G11／G12 底本已判已落，本单复核 `frontend/src/components/AdminPanel.vue` 与 `router/index.js:126`（`/admin`，`primary:false, administratorOnly:true`）在树。**⇒ 底本 §3 第一梯队里那四枚前端号（R410/R412/R414/R415）连同 §2.1#5/#12 的 R413/R399、§2.3#19 的 R417，一共九格「待派」其实早已并树 —— 这正是本单存在的理由。**

## 3. 本轮推翻底本哪几行（逐行列，每行都给「凭哪条命令」）

| 底本行 | 底本原话（摘） | 今天 | 凭哪条命令（本席原文） |
|---|---|---|---|
| `:51` #4 | 缺的那一格是「`auditor` 今天开不出账号 ⇒ 见 R413」 | **推翻 → 已落** | `rg -n "CREATABLE_ROLES" app/common/permissions.py` → `:41` 四枚；`git merge-base --is-ancestor 5963dfe HEAD` → rc=0 |
| `:52` #5 | 「半 …… ⇒ **R413，且 H13 未裁前不可投**」 | **推翻 → 已落**（R413 已投已并，H13 已裁＝甲） | 同上 + `rg -n "ROLE_CLEARANCE" app/common/rbac.py` → `:31` 四档、`auditor:3`；`docs/handoff/2026-09-17-human-gates.md:365-372` 现读结案 |
| `:53` #6 | 引 `2026-09-23-v1-acceptance-record.md:44`「R193 矩阵 51 格真红 0 格」 | **推翻那句的效力**：该读数今天按「未验」读；同时隔离**行为**第一次有真库有牙读数 | `rg -n "越权已结清\|51 格真红" docs/handoff/2026-09-23-v1-acceptance-record.md`（本席现读 `:44`／`:69` 两句仍在盘上）；口径来源＝计划书 `:486` §13；新读数＝`rg -n "MEASURED_WITH_TEETH\|VACUOUS_EMPTY_SET" docs/testing/r469-sandbox-scope-readout-2026-09-28.md` |
| `:56` #9 | 「半……缺的是会话读腿那一格 ⇒ 已立案 **R397 在途**……未并树前这一格不算收口」 | **推翻 → 已落**（R397 已并树） | `git log --oneline --grep="R397"` → `c0c4bcd`；`merge-base --is-ancestor c0c4bcd HEAD` → rc=0；`rg -n "status_code=503" app/api/v1/chat.py` → `:3723/3728/3765` |
| `:57` #10 | 缺格「数字不缺，**叙述缺**：`lib/dashboard.js` 仍有四处替服务端说假话 ⇒ R411」 | **推翻 → 已落**（R411+R416 并完） | `git log --oneline --grep="R411"` → `4fcca16`（rc=0）、`--grep="R416"` → `16337fc`（rc=0）；`rg -n "documents_ready" frontend/src/lib/dashboard.js` 现读四处在位 |
| `:59` #12 | 「半……缺的那一格 = **前端脸在途未并树**（`be-r399` 盘上有件、HEAD 树里没有）」 | **推翻 → 已落**（R399 已并树，脸在 HEAD 里） | `git log --oneline --grep="R399"` → `ed94d16`（rc=0）；`git ls-files frontend/src \| Select-String "Trace"` → 五枚命中（含 `components/TracePanel.vue`）；`rg -n "traces" frontend/src/router/index.js` → `:138-141` |
| `:76` #19 | 「**未落**……现有量具造不出混合角色的 10～30 人样本 ⇒ **R417**」 | **推翻「未落」→ 半**（量具已齐，缺的是真机读数） | `git log --oneline --grep="R417"` → `f65d42e`（rc=0）；`rg -n "role" scripts/provision_bulk_accounts.py` → `:10/100-109/121-126/147`；牙 `tests/test_r417_bulk_role_mix.py`（29 枚用例名现取） |
| `:78` #21 | 「半……此外本轮**没有**做任何重启实测（禁起服务），故只报静态态」 | **推翻 → 已落·实测一次**（带两条没证的边界） | `d8b132f`（rc=0）＋本席自己重算两份 raw JSON（35 表、唯一变化 `audit_events +3`）＋本席亲跑 `scripts/r470_restart_diff.py --check` = rc=0 |
| `:81` 残格行 | 「G03 **半**（R414/R415）· G17 **半**（R412）· G20 **半**（R410）」 | **推翻 → 三枚全部已落** | `18ca560`／`ac84f1a`／`4344e6d`／`73dd85f` 四枚 rc=0 逐枚现取 |
| `:181` §6a 表行 | 「🔴 **零 env 面**：……**无一枚**在 `.env.example`／`deploy/.env.server.example`……」 | **推翻**（R408 已把带注释的落点写进两枚示例件，值仍是 `chroma`） | `rg -n "INDEX_BACKEND" .env.example deploy/.env.server.example` → `.env.example:91-111`、`deploy/.env.server.example:67-88`，末行 `# INDEX_BACKEND=chroma`；`git log --oneline --grep="R408"` → `2a54db3`（rc=0，`git show --name-only` 点名两枚 example） |
| `:187` §6a 净读第 2 条 | 「**新发现（可派、零风险）**……要治的是**文档面**……本轮**未立号**（建议并入 R408）」 | **推翻：已经立并并完树了，别再派**（同上一条命令） | 同上；另现读 `rg -c "INDEX_BACKEND" docs/api/contract-v1.md` = **零命中** ⇒ 契约那一面仍无此键，但底本要治的两枚 example 已治 |
| `:70` #18 缺格 (iii) | 「格③ 生产标签四件判据 (a)(b)(c) 全 ❌ ⇒ 记『未验』」 | **裁定不变，性质变了**：今天欠的**不是量具**，是真实标签与业主窗口 | `ef99d89`（R469，rc=0）＋`docs/testing/r469-sandbox-scope-readout-2026-09-28.md:74-78`（沙盒臂四件全 PASS）；业主裁定现读 `human-gates.md:375`「A3 交付阶段按客户真实密级做」 |

## 4. 今日真欠账清单（三类，每类按「槽一空即可投」排序）

### 甲 · 代码单（能离线验收，零真机依赖）

1. **甲-1 `max_clearance` 接进 Principal、让它真的算数**（契约 `## R472` 文末把它登记为「R479」——**那一枚号已被本席占用**，见 §7-1）。现读症状：`rg -n "MAX_CLEARANCE_ENFORCED\|MAX_CLEARANCE_EFFECT" app/common/open_platform.py` → `:67 = False`、`:68 = "registered_only"`；`git grep -n max_clearance -- app` 全部命中都在「存 / 回显 / 注释」三态里，**没有一处比较**；`app/agents/contracts.py:7` `Principal` 有 `clearance` 字段但应用侧档位不参与判定。
2. **甲-2 `_frame_verdict` 那枚受控纠正豁免**（**沿用旧号 R471**，它 09-28 已在 §4DS:5795 立案，本单不换号）。现读凭据：`git ls-files tests \| Select-String "r471"` → **零命中** = 没做（与看板 §4DT:5808「R471 仍未做」同色）。
3. **甲-3 八枚空表逐枚定性（取证单，纯读码）**：本席从 raw 件现取 `alerts=0`、`alert_rules=0`、`notification_states=0`、`calculation_runs=0`、`metric_definitions=0`、`retrieval_traces=0`、`user_profiles=0`、`document_activity_signals=0`。逐格要么给出 seed 路径，要么明写「这台部署今天就没有这一类事件」——不许让「表结构在」继续冒充「闭环在」。
4. **甲-4 `sessions` 库里 1020 行 vs `GET /sessions` 回 656 条**：R470 §四 明写「本单不判」（属 R78／R35 那一族）。这是一枚可离线验收的口径单：逐形给出 owner／部门过滤的预期条数，并钉住「相等」这一条。

### 乙 · 要安静机器／真机的读数单（代码不缺，缺一次量）

1. **乙-1 格② 热集让路延迟（沿用旧号 R428）**：一次「一窗多判据」（A①②③④ ＋ C 两格）。前提＝机器空闲且无 Agent 复跑同窗（事故 #81）。
2. **乙-2 客户尺寸两档差（R432／R143 那一族）**：🔴 R432 名义由 `Zeno` 持有，但该 agent_id 从未进 §0 名册、产物不采信（§4DQ:5767）⇒ **视同未做，需重派**。
3. **乙-3 R470 在今天的树上重跑一次**：现役镜像 = `9c21490`（R469 件 `:3` BUILD_INFO 现取），落后 HEAD **18 枚提交**；先按 `human-gates.md:326` 的改令重建（`build migrate`），再跑两形。
4. **乙-4 10～30 人混合角色一次真机建号 + 四档权限矩阵读数**（量具＝甲-1 之外的现成 `--roles`）。
5. **乙-5 告警／通知／CalculationRun 三格的端到端一行数据**（甲-3 定性之后再量）。
6. **乙-6 OCR 一张真扫描件进→索引出字**、**乙-7 R37③ 队列失败终态与原因码**、**乙-8 R58 真机三件（`scripts/migrate.py`／备份恢复演练／双读差异表）**——后两枚分别是 V2 #8/#22 与 R60（停写退役）的硬前置（计划书 `:421` 现读：R60 仍受 `R305 真库恢复` 与格③ 两格阻塞）。

### 丙 · 只能业主本人（Agent 一件都不许代做）

1. **丙-1 翻默认**：`deploy/.env.server` 写 `INDEX_BACKEND=pgvector` ＋ `docker compose up -d --force-recreate`（🔴 **容器 recreate，不是镜像 rebuild**；`env_file:` 在容器创建那刻才解析，`docker restart` 不重读）。今天新增的一条便利：键名不再只能凭记忆抄——`deploy/.env.server.example:88` 有现成注释行（R408）。排在乙-1＋乙-2 之后。
2. **丙-2 A 桶 3 组金标与语料互相矛盾**（看板 `:2306` 现读「待业裁」）＋ **29 条 `must_contain` 改题面**（看板 `:5274`：D10 先乙后甲，run7p1 分已到手 ⇒ 现在能裁）。🔴 它直接决定 A④ 与 C 门翻不翻绿——上一轮就是在这里把「逐类不退化」当已验、后被实测打脸（看板 `:4437`：A④ 三格全退化，0.55→0.30）。
3. **丙-3 第二验证机**：本席现取 `Test-NetConnection 192.168.254.128 -Port 22 -Quiet` = **False**、`Test-Connection -Count 1 -Quiet` = **False** ⇒ **今天比底本更糟：整台机器 ping 不通，不只是 sshd 掉**。乙-1／乙-2 全部因此挤本机串行。
4. **丙-4 github 推送面**：`hosts` 里 `127.0.0.1 github.com`（看板 `:4311` 第⑨格）⇒ 主树分支仍只有 gitee 一份 + 本机一份；备份面的一半在业主手里。
5. **丙-5 心跳两枚是否启用**：本席未碰；在册现读仍 `PAUSED`（业主「别开人工提醒」那道令有效）。
6. 🔴 **本单从丙类账上划掉两格**（业主 09-28 已裁，别再挂着）：**A1 `users.department` 真库回填已裁「不做」**（改由 R469 沙盒量具承担，`human-gates.md:374` + 看板 §4DT:5806 重申「崩 A④ 的是给 evalbot 设部门，不是给语料打标签」）；**A3 生产密级回填已裁落「交付阶段」**（`:375`），不进 V1/V2 代码路径。派工单上那两行是**过期账**。

## 5. 可直接派工队列（新号一律从 **R481** 起；本席只提议号，不落看板、不建单、不派工）

排序口径＝「槽一空即可投」：先零撞车、再小写域、最后是要机器要窗口的。`R471`／`R428`／`R432`／`R58` 是**已在册旧号**，本单不换号、只排位置。

| 号 | 症状（本席现取） | 写域（逐枚文件） | 判据（逐格） | 人日 | 可投条件／与谁串行 |
|---|---|---|---|---|---|
| **R481**（甲·纯文档改口） | `docs/handoff/2026-09-23-v1-acceptance-record.md:44` 与 `:69` 今天还写着「越权格 ✅」「越权已结清」，而计划书 §13（`:486`）已把这条口径改成「一律按未验读」——两本纸互相矛盾，下一班照验收记录派工就会当 C 门已绿 | `docs/handoff/2026-09-23-v1-acceptance-record.md`（只改这两句的口径并指向 §13／R469）＋新钉 `tests/test_r481_v1_record_says_unverified.py`；🔴 零 `app/**`、零契约 | ① 那两句改口后，`rg -n "越权已结清" docs` = **零命中**；② 新钉扫 `docs/handoff/2026-09-23-*.md`，凡出现「越权」且不带「未验／R469 引用」即红；③ 强度只许升：把句子改回「✅」必须当场红；④ 历史读数段落（A②／A④ 那些）一律不动 | 0.2 | **与谁都不撞**（在途三枚零交集）。槽一空即投 |
| **R482**（甲·行为变更） | 甲-1：应用注册的 `max_clearance` 存着、回显着、**没有任何一处比较**（`open_platform.py:67 MAX_CLEARANCE_ENFORCED = False`） | `app/common/open_platform.py`、`app/api/v1/open_platform.py`、`app/agents/contracts.py`（`Principal` 加字段）、`app/rag/filters.py`（档位算式核对）＋ `docs/api/contract-v1.md` 追加一节 ＋ 新钉 `tests/test_r482_*` | 落树前**必须现读三件事**（契约 `## R472` 文末本席逐字读到）：① 哪些在册件会因它改口；② 既有注册应用的缺省档会不会因此读不到东西；③ `app/rag/filters.py` 与 PG／Chroma 两条读腿用的是不是同一套档位算式。判据：④ 改完之后 `MAX_CLEARANCE_ENFORCED` 若仍为 `False`，响应体与 OpenAPI 里那句话必须同步改口，**不许留一句「在等业主裁」**（`tests/test_r78_unearned_claims.py:275/307` 那两枚锚要按契约那节说的「换锚不删断言」处理） | 1（行为变更；若裁「不接、只把话说准」则 0.3） | 🔴 **必须排在 R478（`Ohm` 在途）之后**：两枚单碰同一批文件（`open_platform.py` ×2、`contracts.py`）。契约文末同一时间只许一枚追加 |
| **R483**（甲·取证单） | 八枚表今天在演示库里是 **0 行**（本席从 `probe-before-stop-start.json` 逐枚数）：`alerts`／`alert_rules`／`notification_states`／`calculation_runs`／`metric_definitions`／`retrieval_traces`／`user_profiles`／`document_activity_signals`。「表在」正在冒充「闭环在」 | 只读码 + 新件 `scripts/r483_empty_tables_triage.py`（生成器）+ `docs/testing/r483-empty-tables-2026-09-29.md`（生成物）+ 新钉 `tests/test_r483_*`；🔴 零 `app/**` | ① 逐枚给一个词：`no_seed_path`／`legitimately_empty`／`needs_owner`，并点名该走哪条写入道；② 读数表不许手写，`--check` 逐字节核（照 R470 那把尺的形状做，含 `END` 哨兵自证，免踩事故 #83）；③ V2 三条（#11 告警闭环、#17 通知、#3 CalculationRun）各挂一条「这条链今天有没有一行真数据」的明话 | 0.5 | **与谁都不撞**。槽一空即投；与 R481 同族可并一枚，但**写域不同，别并**（并一枚会撞 `scripts/` 与 `docs/testing/` 两棵新树） |
| **R484**（甲·口径单） | 库里 `sessions = 1020` 行，`GET /sessions` 对 `evalbot` 回 **656** 条；R470 §四 明写「本单不判」⇒ 这 364 之差今天**没人 owning** | `app/api/v1/chat.py` 会话读腿的过滤段 ＋ 新钉 `tests/test_r484_*`；禁入 `app/agents/orchestrator.py` | ① 逐形给出 owner／部门过滤后该有几条（含 `departments=None` 那档不受限的语义，`app/rag/filters.py` 现读）；② 钉住「三形相等」这件事不许退化成「只看总数」；③ 判红要有名字：哪一档、哪一条谓词、漏了几行 | 0.5–1 | 🔴 **排在 R464（`Ramanujan`）并树之后**：同文件 `app/api/v1/chat.py`。R471 也在这条队里，三枚同写域必须串行（`R464 → R471 → R484`） |
| **R485**（乙·读数） | 客户尺寸两档差没量（底本 #18 缺格 (iv)）。原号 `R432` 名义由 `Zeno` 持有，但该 id **从未进 §0 名册、产物不采信**（看板 `:5767`）⇒ 视同未做 | 不改产品码；跑在册量具（`scripts/r59_recall_compare.py`、`scripts/r59c_sandbox_corpus.py`，两枚已随 R393 `f509f36` 跟生产同宽）+ 一份新读数件 | ① 在**客户尺寸**语料上给出 `ef_search` 40 vs 100 的两档名次重合与延迟；② 明写不可外推：沙盒 1008 枚上「100 与暴力精确解 180/180 全等」**不许**当客户结论；③ 覆盖 R393 自己登记的那一族「近重复吃预算」 | 1（纯窗） | 🔴 要一台**安静机器**；与丙-3 冲突（第二验证机今天整台不可达）⇒ 只能本机串行，**不许与门或任何 Agent 复跑同窗**（事故 #81） |
| **R486**（乙·读数） | R470 那次实测跑在 09-28 那版镜像上；今天树比镜像**新 18 枚提交**（`git rev-list --count 9c21490..HEAD` = 18） | `docs/testing/r470-restart-drill-2026-09-29.md`（经 `scripts/r470_restart_diff.py --sync` 生成）+ `docs/perf/raw/` 新一批原件；🔴 不改量具逻辑 | ① 先重建镜像（`docker compose --env-file deploy/.env.server build migrate`，`human-gates.md:326` 业主改令在册）；② 两形各跑一次，`ALLOWED_GROWTH` 仍只许 `audit_events`；③ 逐字节核 `--check`；④ 若这次要连 PG 一起 `--force-recreate`，**必须先单列成一格新判据**，不许顺手扩 R470 的判定范围 | 0.5 + 窗 | 与门**同树不可并发**；建议与 R485 并窗（一次开窗拿两格） |
| **R487**（乙·读数，开场要丙授权） | V2 #19 只有量具没有样本：`users = 3` 行，四档权限从没被 10～30 人样本试过 | 不改码；跑 `scripts/provision_bulk_accounts.py --count 30 --roles staff manager admin auditor --departments …`（dry-run 先行，零 socket） | ① dry-run 报出 `role x department` 覆盖几格／共几格；② `apply` 之后 `GET /profile` 逐枚回显真角色（量具自己已有这枚反证）；③ 四档 × 部门矩阵下的越权读数，与 R469 沙盒臂逐档对得上才对 | 0.5 + 窗 | 🔴 **建号 = 往库里写数据**，须业主令；且必须排在 R482 之后（角色／密级档一动，样本口径就变） |
| 旧号 **R471** | 甲-2：`_frame_verdict` 里 R215 受控纠正替换把「正文出现两遍」豁免成绿（看板 `:5795` 立案原文；`git ls-files tests \| Select-String r471` 零命中 = 没做） | 看板原锁写域：`app/api/v1/chat.py` verdict 计算 + R215 三枚在册钉的判据 + 新钉 | 造一形「摘光三格前置导致正文两遍」的夹具，`verdict` 必须读 False；**R215 原有三枚钉不许改宽** | 0.5（原账） | 🔴 排 R464 并树之后（同文件）；与 R484 三枚串行 |
| 旧号 **R428** | 格② 热集让路延迟没量（计划书 `:376-378` 原句「`_hot_hits` 整层让路……两侧对比无数据」） | 读数单，不改产品码（新原因码 `hot_index_read_backend_switched` 在树） | 切读态与遗留态两侧各一次延迟与命中分布 | 1 + 窗 | 安静机器；建议与 R485／R486／乙-6 OCR **并成一窗多判据** |
| 旧号 **R58** | 真机三件（`scripts/migrate.py`／备份恢复演练／双读差异表）——R60 停写退役的第一块前置 | 看板原账；本单不改写域 | 三件逐件交回真机读数 | — | 计划书 `:421`：R60 还压着 `R305` 那枚真库恢复读数 |

**并行度提醒（AGENTS.md：默认并行度不低于 3）**：上表里 R481／R483 两枚**今天就能各占一棵树同投**（写域零交集、都不碰 `app/**`）；R482 与 R478 串行、R484 与 R464／R471 串行、R485／R486／R428 只能排队进窗。

## 6. 本单**没量到**的格子（明列，不用「应该已落」糊）

1. **一格测试都没跑**：没跑 `scripts/run_gate.py`、没跑任何 `pytest`、没跑 `npm run test`／`lint:colors`（同树两枚 Agent 在跑，两跑同窗会假红，事故 #81）。⇒ 全表里凡是「有码 + 有钉」的裁定，本席只报**凭据在场**，不报**今天全绿**。
2. **门基线本席未复跑**：在册最新一张绿票是总控在 `5963dfe` 时点亲跑的 **8479 passed／55 skipped／1 xfailed／exit=0**（`-n 6`，507.9 s，看板 §4DT 第一节）。🔴 `AGENTS.md` 里那行「7722／50／2／302.16 s」到今天**已经过期两档**（号数与用时都是旧账），下一班引用前先复跑。
3. **容器与镜像一律未亲验**（明令不碰 `docker`）：healthy 与否、`BUILD_INFO`、`GET /sessions` 活体回执——全部是从落盘 raw 件读出来的，不是现场问的。「镜像落后 18 枚」是从 git 推的，不是从容器读的。
4. **真库一条语句都没发**：生产标签今天**这一秒**是否仍 `department 0/1008`，本席只能引 `docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 第一节那批读数（09-28T23:42 那一批）。
5. **格② 热集让路／客户尺寸两档差／A②③④／C 门／D 门真机读数**：一格未动，全在 (乙)。
6. **R478 的产物**：本席只读到「四处假指针**还在盘上**」（`app/common/rbac.py:130`／`app/agents/contracts.py:340`／`app/documents/catalog.py:437`／`app/common/open_platform.py:62,72`＋`app/api/v1/open_platform.py:307,320`），**没读到**它是否即将并树——那几枚文件本席一行没改、一次没问。
7. **OCR 端到端**：通道、依赖、钉三面齐（#13），但没有「一张真扫描 PDF 进 → 索引里有字」的读数；`app/rag/ocr.py` 里那条 `Global.max_side_len=2000` 降采样账本单没验。
8. **裸进程启动路径**（#7 那一格「`uvicorn app.main` 不带 env 落 json／内存过渡表」）：底本 §8.6 一行没读 `setup.sh`／`Dockerfile`，本席同样没读——**两班都没证，别把它当已验**。
9. **前端**：`frontend/**` 一切「在树」判定都是 `git ls-files` + 内容现读，没跑过前端任何一件测试；未经授权本单一行前端码都没碰。
10. **`app/memory/**`、`app/semantics/**`、`app/quality/**`、`app/open_platform` 四棵子树**不在 V2 二十三条上**，本单没逐条对判据（同底本 §8.8，那一格今天仍然开着）。

## 7. 本席不确定、请总控裁的格子

1. 🔴 **号冲突（最急）**：契约 `docs/api/contract-v1.md## R472` 文末把「把 `max_clearance` 接进 Principal、让它真的算数」登记为 **R479**，现读逐字：「**R479** 做『把 `max_clearance` 接进 Principal、让它真的算数』的行为变更」。而 **R479 已被本席（复评）占用**。⇒ 请裁：这笔行为变更改挂 **R482**（本单 §5 的写法），并由下一笔**追加**一节契约改口（append-only，不动 `## R472` 历史段落）。这正是事故 #62／#82 那一族「同号双投」，不裁就会派重。
2. **#21 与 #9 判「已落」是否越界**：凭据是「两形实测 + 读腿具名 503」，但实测跑在 09-28 那版镜像上（今天树新 18 枚），且 PG 容器换代／卷存活没证。🔴 上一班正是在「逐类不退化」那一格翻过车（后被 A④ 三格全退化打脸，看板 `:4437`），所以本席把这一格**明写成可推翻**：若总控认为镜像代差足以压回「半」，本单改判，不争。
3. **#19 判「半」还是「已落」**：量具已齐（R417＋R413），演示库今天仍 3 枚账号、没一次真机样本。本席按「验收目标未取读数」判半——请裁这一格以「量具在」还是「样本在」为闸（它决定 R487 要不要排在翻默认之前）。
4. **本单是否该有第 24 行**：底本 `:81` 的「前端残格」行今天整行过期。本席把它折进 #10／#12／#23 三格，**没有单列一行**；若总控要保留独立残格行（便于与前两班逐格对齐），请裁，本单可补。
5. **`Zeno`／R432 那一格**：本席按「从未进 §0 名册、产物不采信」判**视同未做**并重派 R485。若总控手上有 `Zeno` 的独立交回件，这一格要改判，R485 就不必投。
6. **翻默认到底是「重建容器」还是「重建镜像」**：AGENTS.md 与本单丙-1 都按「容器 `--force-recreate`、不是镜像 rebuild」记账（并有 `tests/test_r255_env_documents_the_conversion.py` 同口径钉着），而计划书第 ④ 件原文（`docs/handoff/2026-09-17-pgvector-adoption-plan.md:483`）写的是「业主把 `INDEX_BACKEND=pgvector` 写进 `deploy/.env.server` 并**重建镜像**」。两本纸口径不一，🔴 本席按 AGENTS.md 现读以**容器 recreate** 为准；请裁计划书那一行要不要追加一笔改口（零代码纸面单，可并进 R481）。
7. **`R473`／`R474` 的号账**：`R473` 有并树提交（`7733208`「前端死坐标」），但本席在 §0 名册里没检索到那一行；`R474` 已由 §4DT 明判「不立」。⇒ 只登记不裁：下一班派号请把这两枚当**已消耗**（`R475`〜`R477` 本席在 `AGENTS.md docs/ specs/ tests/ scripts/ app/` 六面现取零命中（唯一命中是本单这枚新文档自己），但**没有检索全部 40+ 棵工作树**，不能替总控保证它们真空）。

## 8. 复算命令清单（全部为本席本轮原文，逐条可贴回 PowerShell）

```powershell
# 0 盘面（每步之后本席都 git status 复洁）
cd C:\Users\fengx\PycharmProjects\be-r479
git rev-parse --short HEAD                                   # 2ba2bc2
git status --porcelain | Measure-Object -Line                # 0 行
cd C:\Users\fengx\PycharmProjects\企业智脑
git log --oneline --since="2026-09-27 21:00" | Measure-Object -Line    # 112 笔
foreach($s in @('5963dfe','d824b10','ef99d89','6fb2fed','d8b132f','3dbf80e','2ba2bc2','ed94d16','c0c4bcd','4fcca16','16337fc','18ca560','ac84f1a','4344e6d','73dd85f','f65d42e','2a54db3','f509f36','9c21490')){ git merge-base --is-ancestor $s HEAD; "$s rc=$LASTEXITCODE" }
git rev-list --count 9c21490..HEAD                           # 18

# 1 台账尺（点名跑，零成本）
& ..\企业智脑\.venv\Scripts\python.exe scripts/audit_plan_ticket_ledger.py    # rc=0 / RESULT=PASS / 43 号

# 2 权限那一族（#4 #5 #19）
rg -n "CREATABLE_ROLES" app/common/permissions.py
rg -n "ROLE_CLEARANCE|auditor|H13" app/common/rbac.py
rg -n "CREATABLE_ROLES|ALLOWED_ROLES" app/common/auth.py app/common/sso.py
rg -n "role|department" scripts/provision_bulk_accounts.py
git ls-files tests | Select-String "r413|r417"

# 3 会话读腿与重启实测（#9 #21）
rg -n "status_code=503|_require_migrated_tables" app/api/v1/chat.py
git log --oneline --grep="R397"
& ..\企业智脑\.venv\Scripts\python.exe scripts/r470_restart_diff.py --check   # PASS / rc=0
$j = Get-Content docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json -Raw | ConvertFrom-Json
$j.db.PSObject.Properties.Name.Count                                         # 35
($j.db.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value.rows)" }) # 逐枚行数

# 4 旋钮（#7 #18）：定义 → 解析 → 调用点 → 进程内现取
rg -n "os.getenv..PERSISTENCE_BACKEND" app
rg -n "INDEX_BACKEND" .env.example deploy/.env.server.example docker-compose.yml
git grep -n pgvector_reads_enabled -- app
& ..\企业智脑\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from app.rag import indexing as ix; from app.rag import pg_store as ps; print(ix.read_backend(), ix.pgvector_reads_enabled(), ps.configured_hnsw_ef_search(), ps.dual_write_enabled())"

# 5 隔离读数与越权那一格（#6 #20）
rg -n "MEASURED_WITH_TEETH|VACUOUS_EMPTY_SET|越权" docs/testing/r469-sandbox-scope-readout-2026-09-28.md
rg -n "越权已结清|51 格真红" docs/handoff/2026-09-23-v1-acceptance-record.md

# 6 能力面（#13〜#17）与 Trace（#12）
git ls-files app/rag; rg -n "OCR_ENGINE_MODULE" app/rag/ocr.py; rg -n "rapidocr|pypdfium2" pyproject.toml
git grep -n "^@router" -- app/api/v1/intelligence.py app/api/v1/notifications.py
git ls-files frontend/src | Select-String "Trace|traces"; rg -n "traces|primary" frontend/src/router/index.js

# 7 演示值与在飞读数（#23）
rg -n "演示" frontend/src --glob "*.vue"
rg -n "inFlight|runtimeHealthReadInFlight" frontend/src/lib/health.js

# 8 R478 那四处假指针（只读，本席一行没改）
rg -n "H13 未定口径|业主口径亦未裁|替业主裁掉" app/common/rbac.py app/agents/contracts.py app/documents/catalog.py
rg -n "MAX_CLEARANCE_NOTE|MAX_CLEARANCE_ENFORCED|MAX_CLEARANCE_EFFECT" app/common/open_platform.py

# 9 第二验证机
Test-NetConnection -ComputerName 192.168.254.128 -Port 22 -InformationLevel Quiet    # False
Test-Connection -ComputerName 192.168.254.128 -Count 1 -Quiet                         # False
```

---

**本席交回声明**：本单一枚新件 `docs/handoff/2026-09-29-v2-gap-recheck-3.md`；`app/**`、`frontend/**`、`tests/**`、`docs/api/contract-v1.md`、看板、跟进单、评测集**一字未改**；无 commit／push／建分支／删文件／改忽略／改 git 配置；无服务、无容器、无模型、无真库语句、无写数据。台账尺与 `r470 --check` 两枚零成本件是本席亲跑，其余一律未跑并已在 §6 明列。
