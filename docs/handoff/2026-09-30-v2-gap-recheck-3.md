# V2 缺口复评（R534 · 2026-09-30 · 纯只读取证 + 只交这一枚新文档）

身份：执行层单号 **R534**，独占工作树 `C:\Users\fengx\PycharmProjects\be-r534`，基点 **`05bec06b3123130805eebae8a73d97da39b6e32d`**（建树时＝主树 `codex/data-file-catalog` 现取 HEAD）。零 commit、零 push。

## 口径声明（先读这节再看表）

- 本单**只读**。除这一枚文件之外零写入：没跑 `pytest`／`vitest`／`scripts/run_gate.py`，没起服务，没碰 `docker`，没打模型，没向任何库发过一条语句。
- **所有代码读数取自本席这棵干净树**（`git status --porcelain` 在落这枚文档之前为 0 行）。主树今天已前进到 `24ade21`，且此刻是脏的（`git -C C:\Users\fengx\PycharmProjects\企业智脑 status --porcelain` 现取非空，含 `app/api/v1/observability.py`＝别席在途写域）⇒ 主树盘上的行号不可复跑，本席不在主树取代码数。两棵树本质的代码差异只有一枚文件，本席证过：`git diff --name-only 05bec06 24ade21` → **只有 `docs/handoff/2026-09-15-orchestration-board.md`** ⇒ 本席树上的代码行号＝今天主树 HEAD 的代码行号。
- 复跑环境：PowerShell，先 `cd C:\Users\fengx\PycharmProjects\be-r534`。🔴 **含正则的 `rg` 一律用单引号包模式**：双引号里的 `|` 会被 PowerShell 当管道吃掉、`(` 会被当子表达式——本席实测炸过两次（`rg -n "hitl/pending|APPROVE_ROUTE_PATH\"` 报 `unclosed group`）。表里的命令就是本席敲过的那一条，含引号形状。
- 裁定只用三档：**已落／半／未落**。「半」必须把缺的那一格写死。表里没有「大概」。
- 凡「某物不存在」本席都先报**查的是哪一层、用的哪一层的名字**（本仓教训原话）。两处最典型的坑本席踩过：`rg -n "ALTER TABLE IF EXISTS alerts ADD COLUMN" migrations` 在 05bec06 上**零命中**，因为那枚件的名字不是 09-27 写的 `0012_legacy_scope_columns.sql` 而是 `0012_alert_and_pending_approval_attribution_columns.sql`——按真名重查命中 `:43-44`，东西一直在；`rg -c "<button" frontend/src --glob "*.vue"` 今天回 14 枚命中，全是注释（见 §2.3 残格那一行的注）。

---

## 0. 盘面与三份底本对账（本席现取）

| 项 | 命令原文 | 实取读数 |
|---|---|---|
| 本席基点 | `git rev-parse HEAD` | `05bec06b3123130805eebae8a73d97da39b6e32d` |
| 本席树洁净 | `git status --porcelain` | 落这枚文档之前 **0 行**；落完之后只多 `?? docs/handoff/2026-09-30-v2-gap-recheck-3.md`（§8 原样贴） |
| 主树今天的 HEAD | `git -C 主树 log -1 --format=%h` · `git show --stat --oneline 24ade21` | `24ade21`「看板落账 第七班续席」＝ **1 file changed, 44 insertions(+), 4 deletions(-)**，只动 orchestration board |
| 09-27 底本（R407）并树笔 | `git log --oneline -1 9e817e1` · `git rev-list --count 9e817e1..HEAD` | 「并树 R407（施工 Boyle/01a0e35f…，基点 `5e9f901`）：V2 缺口按今天的树重画一遍，交回派工就绪队列 R408…」· 之后进树 **171 笔** |
| 09-29 底本（R479）并树笔 | `git log --oneline -1 46ee7ad` · `git rev-list --count 46ee7ad..HEAD` | 「并树 R479（施工 Lippmann/01a0e973，树 be-r479@d8fca78）：V2 缺口复评 3 · 23 格逐格带命令读数 · 🔴 当场推翻 09-27 底本 1…」· 之后进树 **68 笔** |
| 09-30 同题前作（R521） | `git log --oneline -1 581cfb0` · `git rev-list --count 97724c5..HEAD` | 「并树 R521（施工 Kant/01a0ed9f…，树 be-r521@97724c5，计划书八枚零提交单逐枚真欠账复评·纯只读·唯一产物一枚新文档）」· `97724c5..HEAD` = **13 笔** |
| 三份底本都在树 | `git ls-files docs/handoff`（逐枚数字节/行数量具现取，命令见下条注） | `2026-09-27-v2-gap-recheck-2.md` · `2026-09-29-v2-gap-recheck-3.md` · `2026-09-30-plan-eight-tickets-recheck.md` · 本枚 |

> 三枚底本的字节/行数是本席逐枚数出来的（量具：`[IO.File]::ReadAllBytes` 逐字节分 CRLF／loneLF／loneCR，并查前 3 字节 BOM），读数为：`2026-09-27-v2-gap-recheck-2.md` = 46,818 B／276 行、`2026-09-29-v2-gap-recheck-3.md` = 48,168 B／215 行、`2026-09-30-plan-eight-tickets-recheck.md` = 56,003 B／507 行，三枚都 **无 BOM、CRLF、loneCR=0**。⇒ 引用这些文件里的行号时，`rg -n` 的行号与 PowerShell `Get-Content` 的索引在本仓这一族文档里逐格相同（没有 lone CR 造成的错位），本单所有对底本的引用都按 `rg -n` 口径给。

🔴 **命名冲突先交代**：树里已有 `docs/handoff/2026-09-29-v2-gap-recheck-3.md`（R479），与本单被指定的文件名只差日期。本席按派工词落 `2026-09-30-v2-gap-recheck-3.md`，**不改别人的名**。⇒ 本枚是「recheck-3 的第二本（09-30）」，相对 R479 那本的增量 = 68 笔提交。两本打架时以本枚（今天现取）为派工事实源、R479 降为史料——与 R479 自己对待 R407 的姿势一致。

**三份底本今天各自的状态（一句话各一条）**

- **R407（09-27，276 行）**：23 行＋「前端残格」那一行，本席逐行重跑，每格的「09-27 说 X／今天说 Y／谁改的（sha）」都在 §2 表倒数第二列里。🔴 **本席把裁定改判的共 11 行**：往上抬（半／未落 → **已落**）＝**#4 #5 #9 #19 #21** 五格；往下收（已落 → **半**）＝**#6 #8 #11 #13 #22** 五格；外加**前端残格那一整行**（旧纸的四枚「半」今天全并完树，只剩 G03 的 a 半格未落，见 §5）。另有四格**判档不变但内容换了**：#12（缺的那一格整个换掉）、#18（缺的四格里两格已并树）、#14/#15/#17（判档不变，本席补了端到端保留）。纯行号漂但裁定不动的：**#1**（`catalog.py:583→:586`、`chat.py:1003→:1103`）、**#3**（`artifacts.py:65→:68`、`:276→:333-334`）、**#7**（`persistence.py:654→:656`）、**#12 后端**（`:600/:1388/:1392 → :615/:1781/:1785`）。
- **R479（09-29，215 行）**：它推翻过 R407 十二行，本席不复述它的结论、只复跑它给的命令 ⇒ 它自己的读数今天也漂（§3 乙组逐枚点名）。它 §5 提议的 R481/R482/R483/R484 **今天全部已并树**（`6907cff`／`e5917b6`／`8cc4937`／`5270c40`，逐枚 rc=0），R485/R486 **零提及＝从未跑**（§5）。
- **R521（09-30 上午）**：与本单判据② 同题。本席重跑八枚号给出今天的数，与它的差异写在 §4 末。
---

## 1. 口径源与今天的有效行号（现取，未靠任何摘要）

| 口径 | 命令原文 | 读数 |
|---|---|---|
| V2 三段要求在底本里的位置 | `rg -n '^### 2\|^## ' docs/handoff/2026-09-27-v2-gap-recheck-2.md` | §2.1 `:44`（表体 `:46-59`）·§2.2 `:61`（表体 `:63-70`）·§2.3 `:72`（表体 `:76-81`，「前端残格」在 `:81`） |
| 计划书八枚号的索引位置 | `rg -n 'R46 \|' docs/handoff/2026-09-17-perf-architecture-plan.md` | §5.2 表：R29 `:179`·R31 `:181`·R32 `:182`·R33 `:183`·R38 `:188`·R43 `:193`·R46 `:196`·R48 `:198`（`:196` 原文「R46 \| 活动信号回填排序（采纳/驳回 → 相关度先验） \| L3 \| 1.5」） |
| 计划书自己作废「还剩 8 枚」 | `rg -n '还剩 8 枚' docs/handoff/2026-09-17-perf-architecture-plan.md` | `:470`（09-24 作废，逐号点名七枚早已在主干）·`:474`（09-25 二次订正：连「真零产物的只有 R46 消费侧与 R50」也是**假账**，R46 消费侧在 **R195** 名下） |
| 台账尺三档（不跑脚本，只读表） | `rg -n '"R(29\|31\|32\|33\|37\|38\|43\|46\|48)"' scripts/audit_plan_ticket_ledger.py` | `:267 R29 PARTIAL`·`:271 R31 PARTIAL`·`:273 R32 LANDED`·`:275 R33 LANDED`·`:283 R37 PARTIAL`·`:285 R38 PARTIAL`·`:299 R43 PARTIAL`·`:310 R46 PARTIAL`·`:316 R48 PARTIAL` |
| 全库在册迁移 | `git ls-files migrations` | 0001…**0017** ＋ `README.md` ＋ `manifest.json`（共 19 行）；🔴 **0018／0019 不在树**：`git ls-files migrations` 里零命中，0018 由在途 R523 预分配（看板 `:1616` 原文「新 `migrations/0018_prompt_cache_tokens.sql`（号预分配死）」），0019 由代号 C 预分配（看板 `:6010`） |
| 现役 env 的两个旋钮 | 主树 `rg -n 'INDEX_BACKEND\|VECTOR_DUAL_WRITE\|REPORT_LANE_VIA_QUEUE\|PERSISTENCE_BACKEND' deploy/.env.server` | `:56 VECTOR_DUAL_WRITE=on`·`:71 REPORT_LANE_VIA_QUEUE=on`·🔴 **无 `INDEX_BACKEND`**·无 `PERSISTENCE_BACKEND` |
| 那枚 env 是不是在册件 | `git ls-files deploy/.env.server` | **0 行** ⇒ 未跟踪、只在主树盘上。🔴 这是本单**唯一一处必须在主树取的读数**（本席树里没有这枚文件），其余全部来自 `05bec06` 的干净树 |
| shipped env 面有没有 `INDEX_BACKEND` | `rg -n 'INDEX_BACKEND' .env.example deploy/.env.server.example` | `.env.example:91-111`（`:111` = `# INDEX_BACKEND=chroma`）·`deploy/.env.server.example:67-88`（`:88` = `# INDEX_BACKEND=chroma`）⇒ 文档面已存在（归因 R408 `2a54db3`，命令 `git log -S"INDEX_BACKEND" --oneline -- .env.example`） |
| `REPORT_LANE_VIA_QUEUE` 在 shipped 面 | `rg -n 'REPORT_LANE_VIA_QUEUE' .env.example deploy docker-compose.yml` | 只有 `deploy/queue_worker.py:593` 的散文一枚；`.env.example`／`compose`／`deploy/.env.server.example` **零命中**；代码缺省面 `app/api/v1/chat.py:1305 REPORT_LANE_QUEUE_ENV = "REPORT_LANE_VIA_QUEUE"`＋`:1306 REPORT_LANE_ON_VALUES = {"1","true","yes","on"}`，`_report_lane_via_queue_enabled()` 自述「默认关」 |
| V1 验收门今天的脸 | `Get-Content docs/handoff/2026-09-23-v1-acceptance-record.md` 取 `:43-46` | `:43` **A④ 逐类不退化 ❌**（原文「`口径冲突 0.4211 → 0.3158`（19 题掉 2 题）…第二次由本判据抓到真退化」）·`:44` **C 检索与缓存：越权格 未验**（已随 R490 改口，判据出处指向计划书 §13）·`:45` **D 后台化与观测：三格从未宣布验过 ⇒ 🔴 0 格**·`:46` **B／E ⚪ 移出 V1 门槛**（E 的越权格随 C 一起记「未验」） |
| 生产标签四件判据的原文 | `rg -n '^## 13\|未验' docs/handoff/2026-09-17-pgvector-adoption-plan.md` | `:382`（「所有''越权 0 条''的读数一律按「未验」读」）·`:486`（§13 标题）·`:490`（四件判据本体：`chunk_vectors.department` 非空 **0/1008**、`classification` 只有 **1 档**）·`:499`（只有 (d) 单独成立不记通过）·`:527`（第③格要的不是代码，是 A1＋A3）·`:528`（第②格仍欠一台安静机器，`0.873` vs `3.322` 差 4 倍未结）·`:529`（第⑦格已由 R393 `f509f36` 收掉，收这一格不收任何别的格） |
| 业主三条裁定 | `rg -n 'A1（\|A3（\|auditor` docs/handoff/2026-09-17-human-gates.md` 取 `:365-374` | `:365` H13 结案节·`:372` auditor 密级档＝**3**（与 admin 同档，人日按 1 计）·`:373` **A1 不在真库做，改沙盒**（理由：给 `evalbot` 设部门会让 105 题里跨部门题集体崩掉）·`:374` **A3 交付阶段按客户真实密级做，不进 V1/V2 代码路径**（「合成标签只证行为、不证客户隔离」） |

**一句总结给排波的席**：今天翻 `INDEX_BACKEND=pgvector` 前面立着的**不是代码**——码全在树（旋钮 `app/rag/indexing.py:49/:50/:58`、读腿 `app/rag/pg_store.py:983`＋`app/rag/retriever.py:1106/:1166`、候选宽度 `app/rag/pg_store.py:663 HNSW_EF_SEARCH_DEFAULT = 100`）。立着的是 §13 那三格（②安静机器、③业主标签、客户尺寸两档差）＋业主那一步 `env_file:` 改写后 `docker compose up -d --force-recreate`。
---

## 2. 重验表本体（23 行 + 前端残格，逐格命令原文 → 实取读数）

「与 09-27 对账」那一列只在**不一致**时写；一致时写「同」。归因列里的 sha 全部满足 `git merge-base --is-ancestor <sha> HEAD` rc=0（本席逐枚跑过，见 §5 末那批复跑命令）。

### 2.1 V2 硬要求（#1–#12）

| # | 要求 | 今日裁定 | 命令原文 → 实取读数 | 与 09-27 对账（09-27 说 X／今天说 Y／谁改的） | 缺的那一格（仅「半」） |
|---|---|---|---|---|---|
| 1 | `Document`/`DocumentVersion` | **已落** | `git grep -n "CREATE TABLE IF NOT EXISTS document_versions"` → `app/documents/catalog.py:586`＋`migrations/0003_legacy_runtime_tables.sql:39`（另命中两枚**史料抄写**：`docs/handoff/2026-09-27-v2-gap-recheck-2.md:48`、`2026-09-29-v2-gap-recheck-3.md:33`）；`git grep -n "CREATE TABLE IF NOT EXISTS documents "` → `app/api/v1/chat.py:1103`＋`migrations/0004_legacy_runtime_compatibility.sql:30` | 09-27 说 `catalog.py:583`／`chat.py:1003` → 今天 `:586`／`:1103`。归因：`git log --oneline 9e817e1..HEAD -- app/documents/catalog.py` = `c23e44c`(R478)＋`c2e6546`(R404)（`+32/−8`）；`git diff --numstat 9e817e1 HEAD -- app/api/v1/chat.py` = **`+472 −50`**，动过它的是九笔：`05bec06 60a8e01 399a5a4 d8fca78 c2e6546 b4ce04e 6ef6ddc 18ca560 c0c4bcd`。裁定不变 | — |
| 2 | `Dataset`/`DatasetVersion` | **已落** | `rg -n "CREATE TABLE IF NOT EXISTS" migrations/0002_execution_data_lineage.sql` → `:5 datasets`/`:31 dataset_versions`/`:52 calculation_runs`/`:72 metric_definitions`/`:89 agent_runs`/`:110 agent_steps`/`:129 tool_calls`/`:147 model_calls`/`:170 retrieval_traces`/`:187 trace_events`/`:207 index_registry`/`:217 index_versions`/`:235 chunks`；`git grep -n owner -- migrations/0002_execution_data_lineage.sql` → `owner_id TEXT NOT NULL` 在 `:7`/`:34`/`:54`/`:74`，owner 索引 `:25`/`:49`/`:69`；`rg -c "status TEXT" migrations/0002_execution_data_lineage.sql` → **12** | 同（09-27 的 `:7`/`:31`/`:34`/`:52`/`:25`/`:49`/12 处全部逐字复现）。🔴 一枚坑：本席先用 `rg -n "owner_id UUID"` 查 → **零命中**，因为那列的类型是 `TEXT` 不是 `UUID`——按 09-27 原命令（`git grep -n owner -- migrations`）重查才有 | — |
| 3 | `Artifact`/`CalculationRun` | **已落** | `rg -n "CREATE TABLE\|owner_id\|expires_at\|deleted_at\|CREATE INDEX" migrations/0001_core_resource_versions.sql` → `:13 resource_versions`／`:17 owner_id TEXT NOT NULL`／`:30-31` owner 索引／**:36 artifacts**／`:38 owner_id`／`:44 status`／`:45 expires_at`／`:46 deleted_at`／`:51-52 artifacts_owner_idx`；`migrations/0002...:52 calculation_runs`；`rg -n "owner_id\|expires_at\|deleted_at" app/storage/artifacts.py` → 字段表 `:68 "owner_id"`、`:75/:76 expires_at/deleted_at`、🔴 空主即拒在 **`:333-334`**（`if not str(record.get("owner_id") or "").strip():` → `raise ValueError("owner_id is required for protected records")`） | 09-27 说 `0001:38`（artifacts 表）→ 今天表名在 `:36`、`:38` 是它的 `owner_id` 行；说 `artifacts.py:65`→今天 `:68`；说 `:276` 是「空主即拒」→ 今天 `:276` 是 `expiry = _as_datetime(self.expires_at)`，空主即拒挪到 `:333-334`。归因：`git log --oneline 9e817e1..HEAD -- app/storage/artifacts.py` = **只有 `dc47119`（R509，`+76 −1`）** 一笔。裁定不变 | — |
| 4 | 所有资源有稳定 ID／owner／生命周期 | **已落**（🔴 推翻 09-27 的「半」） | `rg -n owner app/api/v1/data.py` → `:78 def _dataset_row_owner_id`、`:55 OWNER_SCOPE_REQUIRED = "department_scope_required"`、`:423` 那句「its owner reaches the deletion through `owner_match`」逐字仍在 | 09-27 这一行「缺的不是字段是**角色**：`auditor` 今天开不出账号 ⇒ 见 #5」今天不成立——四档已全部落地。谁改的：**`5963dfe`**（并树 R413，标题原文「V2 #5 权限统一落地 —— auditor 补到 3 档并进入可创建集合」）；命令 `git log --oneline -S'"auditor": 3' -- app/common/rbac.py` → 直指该笔 | —（`alerts` 无 `owner_id` 属**有意**：走 `acknowledged_by`/`assigned_*`＋`0012` 的 `department`，09-27 已注，今天不改） |
| 5 | staff/manager/admin/auditor 权限统一 | **已落**（🔴 推翻 09-27 的「半」） | `rg -n ROLE_CLEARANCE app/common/rbac.py` → **`:31 ROLE_CLEARANCE = {"staff": 1, "manager": 2, "admin": 3, "auditor": 3}`**；`rg -n CREATABLE_ROLES app/common/permissions.py` → `:41 CREATABLE_ROLES: frozenset[str] = frozenset({"staff", "manager", "admin", "auditor"})`；`rg -n ALLOWED_ROLES app/common/sso.py` → `:9 ALLOWED_ROLES = CREATABLE_ROLES`；`rg -n CREATABLE_ROLES app/common/auth.py` → `:539` import、拒收点 `:606`（create_user）与 **`:680`**；`git ls-files tests \| rg r413` → `tests/test_r413_auditor_role_admission.py` 在树；前端同批：`rg -n auditor frontend/src/lib/users.js` → `:48 USER_ROLES = ['staff','manager','admin','auditor']`、`:54 auditor: '审计人员'`、`:321 creatableRoles: [四枚]`、`:327-328` 自述「R413 起与能读到的角色同集」；钉 `frontend/src/lib/__tests__/r360-user-writes.test.js:604-607`（`it('可创建的角色与可读到的角色同集：auditor 读得到、也开得出（R413…）'`） | 09-27 说 `rbac.py:31` **无 auditor**、`CREATABLE_ROLES` 只有三枚、`auth.py:653` 拒收 → 今天四枚都在、拒收点在 `:680`。归因：角色面 = **`5963dfe`（R413）**；`auth.py` 行号 = **`8d228be`（并树 R495，`+31 −4`，`9e817e1..HEAD` 里唯一动过 `auth.py` 的一笔）**。H13 裁定原文在 `docs/handoff/2026-09-17-human-gates.md:372`（auditor 档＝3），代码自述同步在 `app/common/rbac.py:24`＋`app/common/permissions.py:32-39` | — |
| 6 | 文档/数据/报告/告警**资源级隔离** | **半** | `rg -n "ALTER TABLE IF EXISTS alerts" migrations/0012_alert_and_pending_approval_attribution_columns.sql` → `:43`＋`:44 ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT ''`；`rg -n "SANDBOX_MEASURED\|VACUOUS_EMPTY_SET\|MEASURED_WITH_TEETH" docs/testing/r469-sandbox-scope-readout-2026-09-28.md` → **`:13`／`:62` 整单与臂状态都是 `SANDBOX_MEASURED_PRODUCTION_UNVERIFIED`**；生产臂 `:47-51` **五档全 `VACUOUS_EMPTY_SET`**（部门非空 0/1008）；沙盒臂 `:66-70` **五档全 `MEASURED_WITH_TEETH`**（b 腿 1080/1080、越权 0 条、无谓词对照本可越界 59/48/51/42/0＝**200 条**）；业主裁定 `docs/handoff/2026-09-17-human-gates.md:373`（A1 不在真库做，改沙盒）／`:374`（A3 交付阶段做，「合成标签只证行为、不证客户隔离」） | 🔴 底本件名陷阱：09-27 把这件写作 `migrations/0012_...sql:43`，真名是 `0012_alert_and_pending_approval_attribution_columns.sql`；本席照 `0012_legacy_scope_columns.sql` 试 → `IO error … 系统找不到指定的文件`。**列一直在那儿，是名字被底本写没了** | 缺的那一格 = **生产侧 `department`/`classification` 仍是空集**，计划书 §13（`docs/handoff/2026-09-17-pgvector-adoption-plan.md:490`）的四件判据今天记 **「未验」**：沙盒只证行为、不证客户隔离。治它的是**业主 A1＋A3**，不是代码 ⇒ 见 §7 丙组 |
| 7 | PostgreSQL 成为主要业务存储 | **已落（口径事实，同 09-27）** | `rg -n "os.getenv..PERSISTENCE_BACKEND" app` → `app/storage/persistence.py:656`、`app/storage/datasets.py:586`、`app/common/audit.py:146`；`rg -n PERSISTENCE_BACKEND docker-compose.yml .env.example` → `docker-compose.yml:31 postgres`、`.env.example:55 postgres`；`rg -n PERSISTENCE_BACKEND deploy/docker-compose.server.yml deploy/.env.server.example` → **两枚零命中**（overlay 语义同 09-27：生产靠 `-f docker-compose.yml -f deploy/…` 仍拿到 `postgres`）；`rg -n "in-memory\|silent fallback" app/storage/datasets.py` → `:580`「gets the in-memory…」/`:583`「a silent fallback would be a lost dataset」/`:597` 那句中文日志原文 | 09-27 说 `persistence.py:654` → 今天 `:656`；归因 `git diff --numstat 9e817e1 HEAD -- app/storage/persistence.py` = **`+2 −0`**。`datasets.py:586`／`audit.py:146` 未漂 | —（09-27 留的那句「裸 `uvicorn app.main` 仍是死道」本席**未实测**——禁起服务；它是口径事实，不立单） |
| 8 | Redis 可靠队列：重试/死信/幂等/失败原因完整 | **半**（🔴 改判 09-27 的「已落」） | `rg -n "retry, dead-letter\|max_attempts\|idempotency_ttl\|def enqueue\|def _record_discard\|def fail_or_retry\|always carries a reason\|def dead_letter_depth" app/common/reliable_queue.py` → `:5`（模块自述）/`:156-157`/`:179-180`/`:223 def enqueue(payload, idempotency_key)`/`:408 _record_discard`/`:435 fail_or_retry`/🔴 **`:498 """Report retry bookkeeping so a failed task always carries a reason."""`**/`:509`/`:529 dead_letter_depth()`；丢弃调用点 `:363`/`:369` | 09-27 判「已落」，本席按在册台账口径**改判半**：`rg -n '"R37"' scripts/audit_plan_ticket_ledger.py` → `:283 T("R37", "PARTIAL", [A("45b9720","worker 半程","deploy/queue_worker.py"), A("0c08209","并树")], …)`＝**这仓自己的尺子判它 PARTIAL**。行号全部未漂：`git diff --numstat 9e817e1 HEAD -- app/common/reliable_queue.py` = **ZERO-CHANGE** | 缺的那一格 = **判据③「队列失败有终态与原因码」的真机重量**（码与牙都在，欠一次真跑）⇒ §7 乙组，建议号 **R545** |
| 9 | 会话/产物/数据/文档重启后可恢复 | **已落**（🔴 推翻 09-27 的「半」） | `git log --oneline --grep=R397` → 🔴 **`c0c4bcd`「并树 R397」**（rc=0）；`rg -n "_require_migrated_tables" app/api/v1/chat.py` → 定义 **`:951`**、转调 `:972`、调用 `:1100`（documents）／`:1595`（sessions, session_messages）；`rg -n "storage_unavailable" app/api/v1/chat.py` → 具名 route 三枚 `:2502 route=ask`／`:3982 route=list_sessions`／`:4019 route=get_session`，`rg -c "status_code=503" app/api/v1/chat.py` → **8**（`:2434 :2504 :3343 :3984 :4021 :5177 :5220 :5247`）；`rg -n SESSION_REGISTRY_PATH app/storage/sessions.py` → **`:199`** | 09-27 说「R397 在途未并树 ⇒ 不算收口」→ 已并树 **`c0c4bcd`**；说守卫在 `:1000`/`:1495` → 今天 `:1100`/`:1595`（chat.py `+472 −50`，九笔，见 #1）；说 `sessions.py:91` → 今天 `:199`，归因 **`8d228be`（并树 R495）** 一笔（`git diff --numstat 9e817e1 HEAD -- app/storage/sessions.py` = `+113 −5`）。同族后续全在树：R470 实测 `d8b132f`、R484 会话读腿 `5270c40`、R492 `5b8d767`、R497 去 N+1 `399a5a4`、R510 四枚终态读数脸 `793fcce`（逐枚 `--grep` 现取） | — |
| 10 | Dashboard 用真实期间与真实数据 | **已落**（🔴 推翻 09-27 留的「叙述缺 R411」那一格） | `git log --oneline --grep=R411` → **`4fcca16`「并树 R411…四处『替服务端说假话』的注释与文案改口」**（rc=0）；`git log --oneline --grep=R416` → **`16337fc`「并树 R416」**＋两笔换锚 `5dc5192`/`0713cd5`（rc=0）；`rg -n documents_ready frontend/src/lib/dashboard.js` → **`:52 :64 :192 :195 :522 :555`**（全是按真 payload 键读数形的叙述）；`rg -n "后端今天还没回这一数\|线上今天就是这一张脸\|等后端补上" frontend/src/lib/dashboard.js` → **零命中**（rc=1）⇒ 09-27 点名的四处假话原文已不在；后端 `rg -n "undated\|_ALERT_SERIES_SQL\|_TREND_UNDATED\|def _trend_period\|GET /dashboard/trend" app/api/v1/dashboard.py` → `:63 :64 :324 :363 :410 :414`，09-27 另点的三格本席逐行取原文：`:476`（R342 那句 legacy import）、`:740`（`alerts_open` is replayable (R340)）、`:900`（`point["alerts_open"] = still_open`）⇒ **三格一字未漂**；归因 `dbb8ba4`(R340)／`e9aac2f`(R342)／`acc092e`(R341) 全 rc=0 | 09-27 说「缺的是 R411」→ 已由 **`4fcca16`** 收掉，另加 **`16337fc`（R416）** 治过期注释；`app/api/v1/dashboard.py` **`git diff --numstat 9e817e1 HEAD` = ZERO-CHANGE** ⇒ 后端那一列行号全有效；前端 `frontend/src/lib/dashboard.js` = `+33 −15`（就是 R411/R416 自己） | — |
| 11 | 告警确认/转派/关闭闭环 | **半**（码已落，端到端一行真数据都没有） | `rg -n "ALERT_ACTION_CLOSE\|ALERT_ACTION_ASSIGN\|ALERT_DISPOSAL_WRITE_COLUMNS" app/api/v1/alerts.py` → `:427 :428 :429 :439 :443 :450 :452 :453 :520`（`ALERT_DISPOSAL_WRITE_COLUMNS` 的 close 写列＝`("status","closed_by","closed_at")`，assign＝`("assignee","assigned_by","assigned_at")`）；时钟列 `rg -n "acknowledged_at\|closed_at\|assigned_at" migrations/0014_alert_disposal_columns.sql` → **`:58 :64 :73`**；真数据 `docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json` 现取 `db.alerts = {pk:"id", pk_max:null, rows:0}`、`db.alert_rules.rows = 0`；定性 `rg -n '^### `' docs/testing/r483-empty-tables-2026-09-29.md` → `:33 alerts —— legitimately_empty`、`:45 alert_rules —— needs_owner` | 09-27 判「已落」，本席**改判半**：闭环的**码与列**都实取到了（`alerts.py` 行号与 09-27 逐枚相同，该件自底本 ZERO-CHANGE），缺的是**这轮闭环从没吃过一行真数据**，而闸门是 `alert_rules = needs_owner`（业主侧）。09-27 写「时钟列 `0014...:52-58`」是一段范围而非逐列行号：`git diff --numstat 9e817e1 HEAD -- migrations/0014_alert_disposal_columns.sql` = **ZERO-CHANGE** ⇒ 这不是漂，是底本写得粗，今天钉死为 `:58/:64/:73` | 缺的那一格 = **一行真的 ack→assign→close 走账**（需 `alert_rules` 先有 owner，属业主）⇒ §7 丙＋乙；建议号 **R539** |
| 12 | 管理员可查看一次运行的关键 Trace | **半**（🔴 09-27 的「半」治掉了，本席另抓到一枚更狠的） | 前端脸：`git ls-files frontend/src \| rg -i trace` → **5 枚**（`components/TracePanel.vue`、`lib/traces.js`、`__tests__/r399-trace-render.test.js`、`components/__tests__/r399-trace-screen.test.js`、`lib/__tests__/r399-traces-contract.test.js`）；`rg -n traces frontend/src/router/index.js` → `:152`（`/traces?trace=<编号>` 是真落点）、**`:155 path: '/traces'`**、`:156 name: 'traces'`、`:162`（`primary:false` 派生不出一级入口）；`git grep -n TracePanel -- frontend` → **14 命中**（代表三枚：`components/TracePanel.vue:45 export default { name: 'TracePanel' }`、`components/__tests__/r399-trace-screen.test.js:71`「`/traces` 挂的不是那枚壳」、`:82` 三行同形钉）；R399 并树 **`ed94d16`**（rc=0）。后端：`app/api/v1/observability.py:615 @router.get("/traces/{trace_id}")`、**`:1781 RUN_READOUT_PATH = "/runs/{run_id}"`**、`:1785 @router.get(RUN_READOUT_PATH, …)`。🔴 数据面（本席新抓）：`git grep -n "retrieval.completed" -- app` → **只有 3 处**（`app/rag/debug.py:72` 发射、`app/trace/projections.py:322`/`:378` 消费），产品问答腿 `app/api/v1/chat.py:1669 recalled = list(retriever.search(...)) → :1671 record_retrieval_scope(...)` **一枚都不发**；库里 `retrieval_traces rows=0`（同一枚 raw 件） | 09-27 说「前端零命中、件只在 `be-r399` 盘上 ⇒ 对用户不存在」→ 已被 **`ed94d16`（并树 R399）** 推翻；后端 `:600`/`:1388`/`:1392` → 今天 `:615`/`:1781`/`:1785`，归因两笔：`git log --oneline 9e817e1..HEAD -- app/api/v1/observability.py` = **`227949e`（R438）＋ `efc5c50`（R526）**，`+472 −50`。🔴 新缺口不在 09-27 的任何一格里：`docs/testing/r483-empty-tables-2026-09-29.md:104` 已把它裁成「**no_seed_path，不是合法为空，按 V2 目标态这是欠码**」 | 缺的那一格 = **正常问答链不发 `retrieval.completed`** ⇒ 屏与读腿全在、检索那一块永远空集。写域与撞车见 §6 **R536** |
### 2.2 V2 新增业务能力（#13–#18）

| # | 能力 | 今日裁定 | 命令原文 → 实取读数 | 与 09-27 对账 | 缺的那一格（仅「半」） |
|---|---|---|---|---|---|
| 13 | OCR 与扫描 PDF | **半**（🔴 改判 09-27 的「已落」） | `git ls-files app/rag` → `app/rag/ocr.py` 在树；`rg -n "from app.rag import ocr" -- app/rag/loader.py`（PowerShell 里写作 `rg -n "^from app.rag" app/rag/loader.py`）→ **`:33 from app.rag import ocr as ocr_channel`**；`app/rag/loader.py:9` 原文「本地 OCR 通道（app/rag/ocr.py，判据②），有文本层的页一个字都不再 OCR（判据④）」；引擎名 `rg -n OCR_ENGINE_MODULE app/rag/ocr.py` → **`:26 OCR_ENGINE_MODULE = "rapidocr_onnxruntime"`**；依赖 `rg -n "pypdfium2\|rapidocr" pyproject.toml` → **`:45 "pypdfium2>=4.30.0"` / `:46 "rapidocr-onnxruntime>=1.4.0"`**；降级三形 `app/rag/loader.py:81-83 PAGE_SOURCE_OCR / PAGE_SOURCE_OCR_EMPTY / PAGE_SOURCE_OCR_DEGRADED`、`:90 DEGRADATION_NOTE_PREFIX = "扫描页 OCR 降级"` | 行号全部未漂：`git diff --numstat 9e817e1 HEAD -- app/rag/loader.py` = **ZERO-CHANGE**。09-27 判「已落」的凭据是**码与依赖**，本席不驳它码的那一半；改判半是因为**端到端从没跑过一次**：`retrieval_traces=0`/`chunks=1008` 里 1008 枚来自演示语料（`r483` 面 A 自述 `corpus_is_demo_corpus`），没有任何一份真扫描件走过「上传→OCR→索引里有字」 | 缺的那一格 = **一份真扫描件跑通一次并留读数**（本地 rapidocr，不打模型，但要 CPU 窗）⇒ §7 乙组，建议号 **R540** |
| 14 | PDF/Word 表格解析 | **已落（码）／半（端到端同 #13）** | `git ls-files app/rag \| rg tables` → `app/rag/tables.py`；`app/common/table_presence.py` 也在树（`git ls-files app/common \| rg table_presence`）；接线 `rg -n "R304\|table_channel" app/rag/loader.py` → **`:13`（自述）/`:35 import tables as table_channel`/`:354` 段标题「把 R300 的表格模块接进上传路径」/`:359 :362` 两枚日志前缀/`:529 :537` 段拼装/`:548` PDF 接线出口** | 同（`loader.py` ZERO-CHANGE ⇒ 09-27 的 `:13/:354/:359/:362/:548` 逐枚复现） | 同 #13 那一格，不重复立单 |
| 15 | Excel/CSV 知识库模式 | **已落（码）／半（端到端同 #13）** | `git log --oneline -S"R306" -- app` → **`6d00d70`「R306 第二棒并树（施工 Rawls…基点 217d542）：电子表格真接进知识库上传路径」**（rc=0）；`git ls-files app/rag \| rg spreadsheets` → `app/rag/spreadsheets.py`；`app/rag/loader.py:34 from app.rag import spreadsheets as spreadsheet_channel`、`:18` 原文「电子表格（`.xlsx`/`.csv`）从 `load_document` 走」 | 同（09-27 的 `6d00d70`/`:18` 复现；本席另证 `:34` 那行 import 也在） | 同 #13 |
| 16 | Dashboard 使用真实数据 | **已落** | 同 §2.1#10 那一行的全部命令与读数 | 同（09-27 也写「同 §2.1#10」；那一行今天已被 R411 `4fcca16` 补实） | — |
| 17 | 知识图谱／审批助手／通知 | **已落（码）／半（通知端到端欠一行真已读）** | 图谱：`rg -n "^@router" app/api/v1/intelligence.py` → **`:128 approval/precheck`、`:192 POST /knowledge-graph/relations`、`:248 GET /knowledge-graph/relations`**（与 09-27 同号）；一级入口撤下：`rg -n "primary: false" frontend/src/router/index.js` → `:131` 知识图谱那格 `primary:false`。审批：`rg -n 'hitl/pending\|APPROVE_ROUTE_PATH' app/api/v1/chat.py` → **`:3290 @router.get("/hitl/pending")`**、**`:3411 @router.post("/approve")`**、`:2081 APPROVE_ROUTE_PATH = "/api/v1/approve"`。通知：`rg -n "^@router" app/api/v1/notifications.py` → **`:187 /notifications`、`:212 /read`、`:218 /dismiss`**；`git ls-files frontend/src/components \| rg "AdminPanel\|ApprovalPanel\|NotificationBell\|TracePanel"` → 四枚全在树；`rg -n notifications frontend/src/lib/notifications.js` → `:27 INBOX_PATH`、`:28 READ_ACTION_PATH`、`:29 DISMISS_ACTION_PATH`。🔴 本席新抓（假话一枚）：`rg -n "notifications.py:171" frontend/src/lib/notifications.js` → **`:26 /** 三条路由：一条读，两条写（notifications.py:171 / :194 / :200）。 */`**，而真坐标是 `:187/:212/:218` ⇒ **前端手抄的后端行号今天漂了三处** | 09-27 说 `chat.py:3012 GET /hitl/pending`／`:3133 POST /approve` → 今天 `:3290`/`:3411`（chat.py `+472 −50`，九笔，见 #1）；通知三枚 `:187/:212/:218` **未漂**（09-27 记的就是这三个号）。09-27 没抓到 `notifications.js:26` 这枚手抄漂 ⇒ 新缺口，见 §6 **R538** | 缺的那一格 = 通知**没有一行真已读/忽略行为**：`docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json` 现取 `db.notification_states.rows = 0`，`docs/testing/r483-empty-tables-2026-09-29.md:57` 定性 `legitimately_empty`（合法为空，但 V2「通知有人用」这格仍没被证过）⇒ 属乙组，随 §7 那一次真机走查一起收 |
| 18 | PGVector 正式接入读路径 + 迁移验证 | **半**（同 09-27，但缺的东西换了） | 旋钮：`rg -n "INDEX_BACKENDS\|INDEX_BACKEND_DEFAULT\|def read_backend\|def pgvector_reads_enabled" app/rag/indexing.py` → **`:49 INDEX_BACKENDS = frozenset({"chroma","pgvector"})`、`:50 INDEX_BACKEND_DEFAULT = "chroma"`、`:58 INDEX_BACKEND = INDEX_BACKEND_DEFAULT`、`:2040 def read_backend()`、`:2077/:2084/:2087`**；读腿：`rg -n pgvector_reads_enabled app/rag/retriever.py` → **`:1106`/`:1166`**、`app/rag/pg_store.py:983`（逐字：`if not indexing_module.pgvector_reads_enabled():`）；候选宽度：`rg -n "HNSW_EF_SEARCH_DEFAULT\|_APPLY_HNSW_EF_SEARCH_SQL\|def configured_hnsw_ef_search" app/rag/pg_store.py` → **`:663 = 100`／`:678 SELECT set_config(%s, %s, TRUE)`／`:800`**（R386 `1b4406a` rc=0）；现场＝仍在 Chroma：主树 `deploy/.env.server` 里**没有 `INDEX_BACKEND`**（见 §1）⇒ 读路径缺省 `chroma`。迁移面：raw 件现取 `chunks.rows=1008 == chunk_vectors.rows=1008`、`schema_migrations` 尾 = **0016** | 🔴 推翻 09-27 §6a：09-27（与 AGENTS.md 那一大段）都把「shipped env 面还没有 `INDEX_BACKEND`」当欠账，今天**这半已并树** —— `.env.example:91-111`＋`deploy/.env.server.example:67-88` 都写清了这颗旋钮，归因 **`2a54db3`（并树 R408）**，命令 `git log -S"INDEX_BACKEND" --oneline -- .env.example`。另：09-27 §6 里点名的「R386 挖出两枚量具站错窄档、未派」也已由 **R393 `f509f36`** 收掉（`git ls-files scripts \| rg r59` 两枚在册）。今天迁移侧新欠一格：库里到 **0016** 而树里已有 **0017**（`git ls-files migrations` 现取；0017 = `dc47119` R509 并树）⇒ **现役库落后一笔**，属业主 `migrate` 动作 | 四格逐枚：**(i)** 翻默认 = 业主动作（`env_file:` ⇒ `docker compose up -d --force-recreate`，不是 `restart`、不是 `build backend`）；**(ii)** 格② 热集让路延迟从未量 ⇒ 见下条硬证；**(iii)** 格③ 生产标签 = 「未验」，治它的是业主 A1/A3（#6）；**(iv)** 客户尺寸两档差未量 |
| 18-b | 格②「从未跑」的硬证（本格唯一事实源） | **未落** | `git log --oneline -E --grep 'R428([^0-9\|])'` → **2 笔，全是提及**；`git log --oneline -E --grep '并树 R428([^0-9\|])'` → **0 笔**；`git log --oneline -E --grep 'R485([^0-9\|])'` → **0 提及**；`git log --oneline -E --grep 'R486([^0-9\|])'` → **0 提及**（⇒ R479 提的队列号今天从没被投过）。在册原因码一直在树：`rg -n hot_index_read_backend_switched app/rag/hot_index.py` → **`:78 REASON_READ_BACKEND_SWITCHED = "hot_index_read_backend_switched"`**；判据出处 `docs/handoff/2026-09-17-pgvector-adoption-plan.md:528`（「仍欠一台没人在跑测试的安静机器，`0.873` vs `3.322` 差 4 倍那笔未结」） | 09-27/09-29 都写「欠一台安静机器」，本席今天把它从「欠量」升级成**可证零执行**：连一次派工记录都没有 | 缺的那一格 = 一次独占安静机器窗口 ⇒ §7 乙组，建议号 **R542**（②）／**R543**（④）／**R544**（R470 今天重跑） |

### 2.3 V2 验收目标（#19–#23）+ 前端残格

| # | 目标 | 今日裁定 | 命令原文 → 实取读数 | 与 09-27 对账 | 缺的那一格（仅「半」） |
|---|---|---|---|---|---|
| 19 | 10～30 名内部用户 | **半**（🔴 推翻 09-27 的「未落」） | `git log --oneline --grep=R417` → **`f65d42e`「并树 R417…批量建号量具第一次能造混合角色」**（rc=0）；`rg -n "role\|roles" scripts/provision_bulk_accounts.py` → **`:10` 用法行已带 `--roles staff manager admin auditor`**、`:12-15` 轮换语义自述、`:49` 缺省单角色（R417 判据①「一字不变」）、**`:100 def build_sample(count, prefix, departments, roles)`**、**`:109 "role": roles[(index - 1) % len(roles)]`**、`:121-125 sample_shape` 带 `roles` 计数、`:46` `from app.common.permissions import CREATABLE_ROLES, ROLE_PERMISSIONS`、`:154` 那句「CREATABLE_ROLES ever drift apart again」；牙 `git ls-files tests \| rg r417` → `tests/test_r417_bulk_role_mix.py` 在树 | 09-27 说「`:114` 唯一建号处写死 `"role": "staff"`，角色不可轮换 ⇒ **未落**，立 R417」→ **R417 已并树 `f65d42e`**，那枚写死已换成 `:109` 的轮换式。今天缺的**不是量具是样本**：raw 件现取 `users.rows=3`、`user_profiles.rows=0`（`docs/testing/r483-empty-tables-2026-09-29.md:106` 定性 `needs_owner`）；建号＝往库里写数据，须业主令 ⇒ §7 乙＋丙，建议号 **R541** | 缺的那一格 = 样本本身：`users=3`／`user_profiles=0`，建号＝写库须业主令 ⇒ **R541** |
| 20 | 跨部门/跨密级越权命中为 0 | **半（生产侧记「未验」）** | 四件判据逐枚现取（同一枚读数的两张表）：`Get-Content docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 取 `:55-58`（生产臂）→ **(a) 未验**（users 3 枚里 department 非空 1 枚；admin/evalbot 实测为空）／**(b) FAIL**（非空 department **0/1008**、部门 1 档、密级 1 档、叉乘 1 格）／**(c) FAIL**（召回>0 的档 **1/5**＝admin-l3）／**(d) 未验**（逐档全是空集，越权 0 条无从判）；取 `:74-77`（沙盒臂）→ (a) `PASS_SYNTH_ONLY`／(b) PASS **1080/1080**、7 部门 × 4 密级、叉乘 **16 格**／(c) PASS **5/5**／(d) PASS 越权 **0 条**、无谓词对照本可越界逐档 59/48/51/42/0＝**合计 200 条**；整单状态 `:13`／`:62`＝`SANDBOX_MEASURED_PRODUCTION_UNVERIFIED`；判据本体 `docs/handoff/2026-09-17-pgvector-adoption-plan.md:490`（四件）／`:499`（只有 (d) 成立不记通过）／`:382`（一律按「未验」读） | 09-27 记 `(a)❌ (b)❌ (c)❌ (d)✅只在空集意义上成立`。今天改判为 **(a) 未验 (b) FAIL (c) FAIL (d) 未验** —— 谁改的：**`5963dfe`（R413）之后的 R469 读数件**＋计划书 §13 那四件；AGENTS.md 已把这条口径写成「四件可失败判据、记未验」，本席逐字复现 | 缺的那一格 = 业主 A1（`users.department` 回填，已裁「不在真库做」`human-gates.md:373`）＋ A3（密级标签，已裁「交付阶段」`:374`）。⇒ **这格 Agent 永远收不掉**，只能记「未验」并向业主报闸门 |
| 21 | 服务重启不丢核心业务数据 | **已落·实测一次**（同 09-29 的改判） | 实测笔 **`d8b132f`**（R470，`git log --oneline --grep=R470` 现取；标题原文「两形都过（35 表 146115→146118 只长 audit_events +3…）」）rc=0；原件在树：`Test-Path docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json` → **True**；本席自己解析这枚 raw 件，命令原文：`$j = Get-Content -Raw -LiteralPath docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json \| ConvertFrom-Json` 然后逐键 `$j.db.<表名>.rows`（每件形状为 `{pk, pk_max, rows}`）现取：**documents 105／document_versions 100／datasets 6／dataset_versions 6／artifacts 4／calculation_runs 0／metric_definitions 0／alerts 0／alert_rules 0／users 3／user_profiles 0／pending_approvals 177／notification_states 0／document_activity_signals 0／retrieval_traces 0／chunks 1008／chunk_vectors 1008／sessions 1020／session_messages 2120／trace_events 35108／agent_runs 1181／tool_calls 4526／model_calls 3616／audit_events 2426**；`$j.files` → `data_dir 9／documents 101／static_charts 82`；`schema_migrations` 尾 = **0016** | 09-27 判「半」（只报静态态），09-29 改判「已落·实测一次」——本席**复跑它给的命令并自己解析原始件**，结论同 09-29。🔴 两格边界今天仍在：那次实测跑在 **09-28 那版镜像**上，`docs/handoff/2026-09-15-orchestration-board.md:5995` 今天仍点名「R523 一动 `migrations/`＋`app/trace/`、R524 一动 `app/agents/`＋`app/api/`，并树后镜像即过期」⇒ 覆盖今天树的实测**还没跑过**（R486 零提及＝从未投，见 #18-b）；且 PG 容器全程没重启 ⇒ **卷存活没证** | 缺的那一格 = 覆盖今天这棵树的另一次实测（镜像已过期）⇒ **R544** |
| 22 | 失败任务可定位和重试 | **半**（🔴 改判 09-27 的「已落」，与 #8 同因） | 同 #8 那一条命令与读数（`app/common/reliable_queue.py:498` 的 `failure()` 自述、`:435 fail_or_retry`、`:408` 定义 `_record_discard`、`:423` 那行写 `data["last_error"] = f"{RESULT_DISCARDED}:{reason}"`（原因码就是在这落进终态的）、`:529 dead_letter_depth()`，件自底本 ZERO-CHANGE）；台账口径 `rg -n '"R37"' scripts/audit_plan_ticket_ledger.py` → `:283 **PARTIAL**` | 同 #8：这仓自己的尺子判 PARTIAL，09-27 判 已落 ⇒ 本席按尺子收口 | 缺的那一格 = 真机「失败→死信→带原因码可查」一次读数 ⇒ 与 #8 同一枚单（**R545**），不重复派 |
| 23 | 页面主要数据不依赖固定演示值 | **已落（演示区有旗）** | `rg -n 演示 frontend/src/components --glob "*.vue"` → **13 命中行／7 枚文件**（同式换 `rg -l` 或把范围放宽到 `frontend/src` 都仍是 **7 枚文件**，全部落在 `components/` 下）：`ApprovalPanel.vue:207/:209/:210/:266`（`:209 class="demo-flag">演示数据`、`:210` 逐字交代哪些是常量/哪些是服务端真值）、`DashboardPanel.vue:336`（`demo-flag`）、`hitl/HitlPendingPanel.vue:37/:40`（「不造演示行」「演示常量目录在本文件一次都不 import」）、`InsightPanel.vue:4`（自述原先是演示机）、`ProfilePanel.vue:10/:109`、`ArtifactList.vue:256`、`TracePanel.vue:5`（引用 roadmap `:281`） | 同（09-27 的 `DashboardPanel.vue:336`/`ApprovalPanel.vue:209/210`/`InsightPanel.vue:4`/`HitlPendingPanel.vue:37-40` 逐枚复现；本席多取到 `ProfilePanel.vue:10/:109`、`ArtifactList.vue:256`、`TracePanel.vue:5` 三枚同类自述，全部是**旗或自述**，不是常量喂业务区） | — |
| — | 前端残格（09-27 那一行今天**整行过期**） | 逐枚见右 | 🔴 **G18 已落**：`rg -n 'class="eyebrow">[A-Za-z ]+<' frontend/src --glob '*.vue'` → **零命中（rc=1）**（09-27 也记零命中，今天仍零）·**G20 已落**：`rg -n DEBT_TOTAL_RATCHET frontend/src/components/__tests__/r288-native-buttons.test.js` → **`:60 const DEBT_TOTAL_RATCHET = 0`**，`:55` 已在 `DEBT_RATCHET` 里写 `'components/DashboardPanel.vue': 0`，`:132-133`/`:166` 两枚棘轮钉；归因 **R410 `73dd85f`**（rc=0）。⚠️ 教训样本（本单口径规矩的活例）：`rg -c '<button' frontend/src --glob '*.vue'` 今天回 **14 枚**，逐枚读原文全是注释与自述（`App.vue:630/:672`、`DashboardPanel.vue:621`、`AdminPanel.vue:26`、`AuditEventsPanel.vue:25`、`EvaluationsPanel.vue:23`、`SloPanel.vue:28`、`TracePanel.vue:41`），且本仓唯一的量具 `frontend/src/components/__tests__/r288-native-button-scan.js:40` 明写 `if (normalized.startsWith('components/ui/')) return false` ⇒ 「还有 `<button`」根本不是判据，**判据是那把尺的计数**。·**G17 已落**：归因 **R412 `4344e6d`**（rc=0）；`rg -n 知识库 frontend/src/components/DocPanel.vue` → 今天只剩 **`:354` 一枚注释**（引 R313 旧原话），路由名 `rg -n "title: '喂料'" frontend/src/router/index.js` → **`:74`** 一屏一名。·**G08 已落**：`rg -n form.append frontend/src/components/DocPanel.vue` → **`:650 form.append('classification', String(item.classification))`**（与波次三/四旧账相反；`:103` 另交代默认值出处 `app/api/v1/chat.py:3933`）。·**G10/G11/G12 已落**：`rg -n "path: '/artifacts'\|path: '/admin'" frontend/src/router/index.js` → **`:105`/`:140`**，`:143` 管理员屏 `title: '账号与角色'`＋`administratorOnly: true`；`AdminPanel.vue` 在树＋`components/__tests__/r316-admin-panel.test.js` 在册。·**G03 已落（主货）／🔴 a 半格今天仍未落**：归因 **R414 `18ca560`**＋**R415 `ac84f1a`**（均 rc=0），再加同族 **R519 `03cd2eb`**；后端 `rg -n "terminal_data_filename\|data_filename" app/api/v1/chat.py` → **`:362 def terminal_data_filename`/`:372 def attach_terminal_data_filename`/`:383-384 payload["data_filename"]`**；屏侧 `rg -n "data_filename\|data-table-readout" frontend/src/components/ChatPanel.vue` → `:597`（自述「R414 已并树」）/`:669`/`:1546-1560`（R519 队列道读者）/`:2155 data-testid="data-table-readout"` | 🔴 **G03 的 a 半格 = 今天唯一还立着的前端族欠账**：`git show --stat 18ca560` 的标题明写「空部门那一格整格退回并钉成现状形状」，三枚件 `tests/test_r414_a_department_free_upload.py`／`_b_terminal_data_filename`／`_c_upload_prose` 各守一格。本席复证：`git grep -n department_scope_required -- app` → 只有 `app/agents/contracts.py:332`、`app/agents/tools.py:127`、`app/api/v1/data.py:55`（**都不是上传出口**）；`rg -n '"department": principal.department' app/api/v1/chat.py` → **`:769 "department": principal.department or ""`** ⇒ 空部门上传照收，**这一格今天还是未落**。堵点是业主 A1（已裁「不在真库做」）⇒ 见 §6 关于「这格今天该怎么收」的写死建议 | 🔴 只剩 G03 的 a 半格（空部门上传拒收）**未落**，且它早已整格退回、不许再立单（见 §5） |
---

## 3. 今天过期了哪些旧账（逐条给凭据）

### 甲组：R407（09-27）那张表里今天已被推翻或改判的行

| 底本行 | 09-27 说 | 今天说 | 谁改的（并树 sha） | 复跑命令 |
|---|---|---|---|---|
| §2.1 #4 | 「缺的不是字段是角色：`auditor` 开不出账号」 | 角色齐了，四档可建可读 | **`5963dfe`**（R413） | `git log --oneline -S'"auditor": 3' -- app/common/rbac.py` |
| §2.1 #5 | 「`rbac.py:31` 无 auditor／`CREATABLE_ROLES` 三枚／拒收点 `auth.py:653`」 | `:31` 四枚、`:41` 四枚、拒收点 `:606`/`:680` | 角色＝**`5963dfe`**；行号＝**`8d228be`**（R495，`auth.py` `+31 −4`） | `rg -n ROLE_CLEARANCE app/common/rbac.py` |
| §2.1 #8／§2.3 #22 | 「**已落**」 | 本席改判 **半**：这仓自己的尺子判 R37 = PARTIAL，欠真机重量 | 不是被谁改的，是**底本判得比台账松** | `rg -n '"R37"' scripts/audit_plan_ticket_ledger.py` → `:283` |
| §2.1 #9 | 「半：R397 在途，未并树前不算收口」 | **已落**：会话读腿有守卫、503 具名 `route=`、三形都过 | **`c0c4bcd`**（R397）＋后续 `5270c40`(R484)／`5b8d767`(R492)／`399a5a4`(R497)／`793fcce`(R510) | `git log --oneline --grep=R397` |
| §2.1 #10 | 「数字不缺、**叙述缺**（四处假话）⇒ R411」 | 四处假话原文已不在 | **`4fcca16`**（R411）＋**`16337fc`**（R416，另 `5dc5192`/`0713cd5` 两笔换锚） | `rg -n '后端今天还没回这一数\|线上今天就是这一张脸\|等后端补上' frontend/src/lib/dashboard.js` → 零命中 |
| §2.1 #11 | 「**已落**」 | 码与列在，但**闭环从未吃过一行真数据**（`alerts=0`／`alert_rules=0`，后者 `needs_owner`）⇒ 改判 **半** | 定性出处 **`8cc4937`**（并树 R483） | `rg -n '^### `' docs/testing/r483-empty-tables-2026-09-29.md` → `:33`/`:45` |
| §2.1 #12 | 「半：前端正脸零命中、件只在 `be-r399` 盘上」 | 脸与路由都在 HEAD 里；🔴 本席另抓到**数据面零种子**⇒ 仍判半（换了缺的那一格） | **`ed94d16`**（R399） | `git ls-files frontend/src \| rg -i trace` → 5 枚 |
| §2.2 #13/14/15 | 「**已落**」 | 码/依赖/接线全在，但**端到端从没跑过一份真扫描件**⇒ 改判 **半** | 不是码的问题，是缺一次量 | `git diff --numstat 9e817e1 HEAD -- app/rag/loader.py` → ZERO-CHANGE（行号未漂） |
| §2.2 #18 缺格 | 「shipped env 面还欠 `INDEX_BACKEND` 那一半」 | 文档面已存在（`.env.example:91-111`＋`deploy/.env.server.example:67-88`）；🔴 今天新欠的是**现役库只到 0016、树里已有 0017** | **`2a54db3`**（R408）；0017＝**`dc47119`**（R509） | `rg -n INDEX_BACKEND .env.example deploy/.env.server.example` |
| §2.3 #19 | 「**未落**：`:114` 写死 `role: staff`，角色不可轮换 ⇒ R417」 | **半**：量具已能造混合角色（`:100/:109` 轮换式），欠的是真样本 | **`f65d42e`**（R417） | `rg -n '"role"' scripts/provision_bulk_accounts.py` → `:109` |
| §2.3 #20 记法 | 「(a)❌ (b)❌ (c)❌ (d)✅ 只在空集意义上成立」 | 「(a) **未验** (b) **FAIL** (c) **FAIL** (d) **未验**」（计划书 §13 四件可失败判据，`docs/.../r469` 生产臂 `:55-58` 原文） | 判据改写＝计划书 §13（`:490`），读数＝R469 件（`:13/:55-58/:74-77`） | `Get-Content docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 取 `:55-58` |
| §2.3 前端残格行 | 「G03 半／G17 半／G18 已落／G20 半／G08 已落／G10-12 已落」 | 今天**整行过期**：G17/G18/G20/G08/G10-12 **已落**，G03 主货**已落**、🔴 只剩它的 **a 半格（空部门上传拒收）未落** | G17＝`4344e6d`(R412)、G20＝`73dd85f`(R410)、G03＝`18ca560`(R414)＋`ac84f1a`(R415)＋`03cd2eb`(R519)、G08/G10-12＝R313/R316 族 | `git log --oneline --grep=R414` / `--grep=R410` / `--grep=R412` |

### 乙组：R479（09-29）那本自己也漂了（逐枚点名，每条都给归因）

| R479 写的 | 今天现取 | 归因 |
|---|---|---|
| `app/documents/catalog.py:583`（`:33` 那一行） | **`:586`** | `c23e44c`（并树 R478）——`git merge-base --is-ancestor c23e44c 46ee7ad` → **rc=1**（这笔在 R479 之后才进树，所以它当时不算写错） |
| `observability.py:615 GET /traces/{trace_id}`、**`:1403 RUN_READOUT_PATH`**（`:44` 那一行） | `:615` 仍对；**`:1781 RUN_READOUT_PATH`**＋`:1785` 路由 | `efc5c50`（并树 R526，`git merge-base --is-ancestor efc5c50 46ee7ad` → **rc=1**）；`git diff --numstat 46ee7ad HEAD -- app/api/v1/observability.py` = **`+378 −0`** |
| `frontend/src/router/index.js:35 import TracePanel`、`:138-141` `/traces` 屏、`:114` 知识图谱 `primary:false` | **`:39` import**、**`:155 path`/`:156 name`/`:157 component`**、**`:131`** 知识图谱 `primary:false` | 三笔动了这枚文件：`git log --oneline 46ee7ad..HEAD -- frontend/src/router/index.js` → **`0f12a17` `6e62379` `8ab62d8`**；`git diff --numstat 46ee7ad HEAD -- frontend/src/router/index.js` = **`+48 −1`** |
| §4 甲-1／甲-2／甲-3／甲-4 ＝ R482／R471／R483／R484「今天就能投」 | **四枚全部已并树**：`e5917b6`／`438d67d`／`8cc4937`／`5270c40`（逐枚 `git log --oneline -E --grep '并树 R<号>([^0-9]\|$)'` 现取，均 rc=0） | 见 §5 |
| §5 队列 R485（客户尺寸两档差）／R486（R470 今天重跑）／R487（10～30 人样本） | 🔴 **R485/R486 零提及＝从未派过也从未跑**（`git log --oneline -E --grep 'R485([^0-9]\|$)'` → 0 行；R486 同 0 行）；R487 mention=1 且只在提案纸里 ⇒ 未投 | 三格今天照旧欠，本席改号为 **R543/R544/R541** 重排（§6） |
| #21「已落·实测一次」＋「跑在 09-28 那版镜像上（`git rev-list --count 9c21490..HEAD` = 18）」 | 结论今天仍对，但**镜像那格更严重了**：看板 `:5995` 原文点名「R523 一动 `migrations/`＋`app/trace/`、R524 一动 `app/agents/`＋`app/api/`，并树后镜像即过期」；而 R524（`05bec06`）**今天已并树** ⇒ 18 枚那一格已涨到今天 `git rev-list --count 9c21490..HEAD`（本席未复跑该式，只登记结论方向：覆盖今天树的实测仍未跑） | 属乙组量，建议号 **R544** |

### 丙组：本席今天**新抓**的缺口（不在任何一本底本里）

| 编号 | 症状（一句话） | 硬证（命令原文 → 读数） | 归到 |
|---|---|---|---|
| **D** | 产品问答链不发 `retrieval.completed` ⇒ `retrieval_traces` 永远是空集，Trace 屏上「检索」那一块没有数据可看 | `git grep -n "retrieval.completed" -- app` → **只有 3 处**：`app/rag/debug.py:72 event_type="retrieval.completed"`（挂在 `app/api/v1/observability.py:527 @router.post("/retrieval/debug")`，函数体 `:528 def retrieval_debug`）、`app/trace/projections.py:322`（文档串）、`:378 if event_type == "retrieval.completed"`（消费侧，`project_retrieval` 定义在 `:321`）；问答腿 `app/api/v1/chat.py:1669 recalled = list(retriever.search(request.message, k=5, where=retrieval_filter))`→`:1670`→`:1671 record_retrieval_scope(...)` 不发这枚事件；raw 件 `db.retrieval_traces = {pk:"retrieval_trace_id", pk_max:null, rows:0}`；裁定原文 `docs/testing/r483-empty-tables-2026-09-29.md:104`「**no_seed_path，不是合法为空……按 V2『每轮问答可回查检索』的目标态，这是欠码**」 | **R536**（甲·码） |
| **E** | 同一件事两本口径各说各话：代码注释说「**six** of the seven budget tiers belong to no lane」，契约说「**Five** of the seven」 | `app/api/v1/observability.py:864-866` bridge_note 原文（`"not one-to-one: analysis and report share ModelTier.ANALYSIS, and six of the "`／`"seven budget tiers belong to no lane at all"`）；`docs/api/contract-v1.md:1582` 原文「Five of the seven budget tiers (`plan` `compress` `rewrite` `code` `alert`) are named by no lane」；本席派生真值：`app/agents/contracts.py:78-90` ModelTier 共 **7** 枚（chat/plan/compress/rewrite/code/alert/analysis，逐枚行号 `:78/:80/:82/:84/:86/:88/:90`）＋`app/agents/nodes.py:1237-1241 LANE_TIERS = {LANE_QA: CHAT, LANE_ANALYSIS: ANALYSIS, LANE_REPORT: ANALYSIS}` ⇒ 被跑道点名的是 **{chat, analysis} = 2 枚** ⇒ 无名档位 = **5** ⇒ **契约对、代码注释错** | **R537**（甲·账面，🔴 与在途 R533 同写域，条件投） |
| **F** | 前端**手抄后端坐标**这一族今天抓到三枚假话（同一病根，R455 只治了缺口单那一面） | ① `frontend/src/lib/notifications.js:26`「（notifications.py:171 / :194 / :200）」vs 真 `:187/:212/:218`；② `frontend/src/components/DocPanel.vue:112`「ROLE_CLEARANCE = {staff:1, manager:2, admin:3}」vs 真 `app/common/rbac.py:31` 四枚（**少 auditor＝今天已是假话**）；③ `frontend/src/components/DocPanel.vue:103`「默认值就是后端那一句 `classification: int = Form(1)`（app/api/v1/chat.py:3933）」vs 真 **`app/api/v1/chat.py:4470 classification: int = Form(1)`**（`rg -n "classification: int = Form" app/api/v1/chat.py` 现取，全仓唯一一枚） | **R538**（甲·前端 lane，本席只点名不动 `frontend/**`） |
| **G** | 现役库落后一笔迁移：库里 `schema_migrations` 尾 = **0016**，树里已有 **0017**（`migrations/0017_artifact_generation_lineage.sql`，`git ls-files migrations` 现取；manifest 尾行同） | raw 件 `$j.db.schema_migrations` 尾值＋`rg -n '0017' migrations/manifest.json` → `"0017_artifact_generation_lineage.sql": "b60fd974…"` | 属丙（业主 `migrate`）——不立 Agent 单，见 §7 |

---

## 4. 判据②：计划书那八枚「零提交」号逐枚现取

🔴 先给结论：**八枚里没有一枚是真零提交**。「计划书还剩 8 枚零提交」这句话本身是过期账——计划书自己 `:470`（09-24）与 `:474`（09-25）已两度作废它，R521（`581cfb0`）已推翻一次，本席今天再证一遍。

复跑量具（八枚一次跑完，本席就是这么数的）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r534
foreach ($t in 'R29','R31','R32','R33','R38','R43','R46','R48') {
  $m = (git log --oneline -E --grep "$t([^0-9]|`$)" | Measure-Object -Line).Lines
  $l = (git log --oneline -E --grep "并树 $t([^0-9]|`$)" | Measure-Object -Line).Lines
  Write-Output "$t mention=$m landed=$l"
}
```

| 号 | 提及／自号并树（上面那条命令的读数） | 在册产物（本席逐枚 `git ls-files` 现取） | 逐枚结论 | 缺的那半 |
|---|---|---|---|---|
| **R29** | `mention=30 landed=1` → **`791568c`**「并树 R29（Laplace/01a0bf4f）：思考税判负并钉成契约」；施工 `62c734d` | `tests/test_r29_thinking_tax.py` 在树 | **已被别的说法并树＝负结果入契约**（不是零提交） | 台账 `:267-268` 原文：「真机 A/B 判负：并的是『不迁腿』这个负结果与契约钉，**30.6 s→≤22 s 一分没省**」⇒ 缺的是收益那一半，判负后不迁腿 |
| **R31** | `mention=17 landed=1` → **`eef642b`**「并树 R31：后端流式产出合格片序列（判据①a）」；施工 `a7cd9b6`；端点多发那一半转出 **R149 `3aba146`**「SSE 收端三道共用一枚 `text_sse_frame`，片到即发累计帧」；🔴 **今天 `05bec06`（R524·代号 B）并批准腿** | `git grep -c stream_piece_sink` → **`app/agents/nodes.py:3`／`app/agents/orchestrator.py:9`／`app/api/v1/chat.py:2`**；`git grep -q stream_piece_sink -- deploy/queue_worker.py` → **rc=1（零命中）** | **部分并树**（判据①a＋批准腿都在；队列道那一格今天交回 `not_applicable` 带凭据） | 队列道**没有可注册点**（`deploy/queue_worker.py::_drain_report_stream` 在 `:415`，本席现取），差格 b 属另一写域；台账 `:271-272`：「② 逐片无缺字等 A 门，端点多发那一半转出 R149」；A② 真机分布仍欠（run10 未开） |
| **R32** | `mention=11 landed=1` → **`8a91f4e`**「并树 R32：档位取值闸 + 契约散文归真」；施工 `0cfd86a` | `tests/test_r32_lane_contract.py` 在树 | **真零提交＝假**；台账判 **LANDED**（`:273-274`：「①②③ 达；档位选择器按假控件禁令不交、拆 **R141**」） | 无（🔴 拆出去的 R141 是**业主自用号**，本单禁止占用） |
| **R33** | `mention=10 landed=1` → **`9678d21`**「并树 R33：短期记忆那条腿自本枚起零模型」；施工 `b35e10f` | `app/memory/summarizer.py:2`（「短期记忆 —— 历史裁剪（R33：零模型）」）、`:6`（判据②「裁剪过程零模型调用」）、**:21**（「同输入必同输出：不掷随机数、不读时间、不调模型」）；件 `tests/test_r33_history_guardrails.py`＋`tests/test_r33_zero_model_compression.py` 在树 | **LANDED**（台账 `:275-276`） | 无 |
| **R38** | `mention=10 landed=1` → **`2e6abc6`**「并树 R38：input_tokens 穿得出原生腿 + cached_tokens 归真为事实」；施工 `c81fbb5` | `app/trace/spans.py:289 REFUTED_CACHED_TOKEN_CLAIM = "native_leg_reports_no_cached_tokens"`；件 `tests/test_r38_cached_tokens_honesty.py`＋`tests/test_r38_native_input_tokens.py` 在树 | **部分并树** | 台账 `:285-286`：「通路形状已修；**『抽查一问非零』等真机 D-2**」⇒ 缺真机读数 |
| **R43** | `mention=16 landed=1` → **`4586bb4`**「并树 R43a：原生腿 cached 计数接上 + 改写 prompt 可变内容后置」；R43b＝**R167 `839c344`** | `tests/test_r167_answer_prefix_reuse.py`（台账点名）在树；🔴 `git grep -n cached -- migrations` → **零命中（rc=1）** ⇒ 全库迁移里没有一枚 cached 列 | **部分并树** | 台账 `:299-301`：「① 由 R43a 落码；② **真机 E3 读数与『cached 落库那一列』都还没有**」⇒ 那一列正是在途 **R523**（代号 A）的活：看板 `:1616` 原文「写域 新 `migrations/0018_prompt_cache_tokens.sql`（号预分配死）＋`manifest.json`＋`app/trace/{schema,projections}.py`＋`spans.py`」，且 `git ls-files migrations` 现取 **0018 不在树** |
| **R46** | `mention=16 **landed=0**`（唯一一枚没有自号并树笔） | 后端半张＝**R152 `eaa9af8`**（施工 `c29ccf5`，`migrations/0011_document_activity_signals.sql` 在树）；消费侧＝**R195 `484536c`**（`frontend/src/lib/feedback.js` 在树） | **部分并树（跨号落地，不是零提交）**：计划书 `:474` 自己就这么订正过 | 台账 `:310-312`：「① 真库/真并发次序未证；按 filename 聚合无身份 ⇒ 强度校准另在 **R153**」。今天新读数：**R525 `0b44df1`**（`docs/testing/r525-activity-prior-real-store-2026-09-30.md:4`「表里 **0 行**；而它一旦有数据，位移上界是 **±1 名且与腿宽无关**（5／12／40 三档实测都是最远一名）」、`:41` 行数 **0**、`:43` 能命中语料 **0 篇**）⇒ 「真库有信号」那一格仍量不到（U1）；🔴 点击／浏览那半张属**代号 C（R527 待投，持 `migrations/0019`）**，本单不许占号 |
| **R48** | `mention=12 landed=2` → **`0ad3d3e`**「并树 R48 路线甲（施工 Confucius…）：首屏线索卡 answer.headline」＋**`efe5461`**「总控亲做（R48 前置解锁）」 | `frontend/src/components/AnswerHeadlineCard.vue` 在树 | **部分并树** | 台账 `:316-317`：「① 首屏 ≤1 s 在本机硬件口径上**物理不可达（地板 11.0 s）**，B 行已整行移出 V1」；现场另证：主树 `deploy/.env.server:71 REPORT_LANE_VIA_QUEUE=on`（树上 shipped 面零命中、代码缺省 off＝`app/api/v1/chat.py:1305`）⇒ 这条现网开关是**业主现场**，不是 V1 门 |

**与 R521（09-30 上午那本）的差异**：它的结论方向（八枚无一真零提交）本席复现成立；本席**多交三格今天的数**——① R31 今天由 `05bec06`（R524）补了批准腿并给出队列道 `rc=1 零命中` 的不可注册凭据；② R43 缺的那一列本席用 `git grep -n cached -- migrations` 证到零命中，并指到在途 R523 的 `migrations/0018` 号；③ R46 补 `0b44df1`（R525）的真库读数（表在、0 行、±1 名、5/12/40）。

---

## 5. 判据⑤：🔴「今天看起来缺、其实已被并树」清单（防重复派工，与抓缺口同等重要）

每一条都是「旧纸写着欠、今天树上有货」。派工前请逐条按本表命令复跑，别再往这些方向下单：

| 格子（看上去缺什么） | 真已落地点 | 并树 sha（本席逐枚 `merge-base --is-ancestor <sha> HEAD` → **rc=0**） | 在册牙／现取坐标 |
|---|---|---|---|
| #4/#5「auditor 开不出账号／没有密级档位」 | R413 四档齐、auditor＝3 档 | **`5963dfe`**（＋同批契约面） | `tests/test_r413_auditor_role_admission.py`；`app/common/rbac.py:31`／`app/common/permissions.py:41`／`app/common/sso.py:9`／`app/common/auth.py:606/:680` |
| #9「会话读腿缺表会裸 500」 | R397 `_require_migrated_tables`＋503 具名 `route=` | **`c0c4bcd`** | `app/api/v1/chat.py:951`（定义）／`:1100`／`:1595`／`:2502 :3982 :4019`（三枚具名 route）；`rg -c "status_code=503"` = 8 |
| #9/#21「会话读腿拦了什么没人 owning」 | R484 会话读腿归属取证 | **`5270c40`** | 并树笔标题「会话读腿到底在拦…」 |
| #9「会话列表 N+1」 | R497 去 N+1（一条聚合替每行子查询） | **`399a5a4`**（标题形如 `R497: …`，`--grep` 现取） | 附 17 枚牙＋四把反证刀（标题自述） |
| #10「`dashboard.js` 四处替服务端说假话」 | R411 四处改口；R416 过期注释 | **`4fcca16`**／**`16337fc`** | `rg -n documents_ready frontend/src/lib/dashboard.js` → `:52 :64 :192 :195 :522 :555`；三句假话原文零命中 |
| #12「管理员 Trace 缺前端正脸」 | R399 前端脸＋路由 | **`ed94d16`** | `frontend/src/components/TracePanel.vue`、`lib/traces.js`、三枚 r399 测试件；`frontend/src/router/index.js:39/:155/:156/:157` |
| #18「`hnsw.ef_search` 与遗留引擎不同宽」 | R386 读腿同事务钉档 | **`1b4406a`** | `app/rag/pg_store.py:663 = 100`／`:678`／`:800 configured_hnsw_ef_search()` |
| #18「两枚量具自己站错窄档」 | R393 改派生（读真源） | **`f509f36`** | `scripts/r59_recall_compare.py`＋`scripts/r59c_sandbox_corpus.py` 各调 `configured_hnsw_ef_search()` |
| #18「shipped env 面还没有 `INDEX_BACKEND`」 | R408 旋钮文档落地（零行为变更） | **`2a54db3`** | `.env.example:91-111`、`deploy/.env.server.example:67-88` |
| #18「`notification_states`／`artifact 血缘`没有列」 | 迁移 0016／0017 已在树 | `dc47119`（R509，0017）；0016 在册 | `git ls-files migrations` 现取 0001–0017；`migrations/manifest.json` 尾行 `"0017_artifact_generation_lineage.sql"` |
| #19「批量建号只能造 staff」 | R417 `--roles` 轮换＋dry-run 拒未知角色 | **`f65d42e`** | `scripts/provision_bulk_accounts.py:10/:100/:109/:121-125`；`tests/test_r417_bulk_role_mix.py` |
| #21「重启从没实测过」 | R470 两形实测一次 | **`d8b132f`** | `docs/perf/raw/r470-2026-09-29/probe-before-stop-start.json`（本席逐键解析过，读数见 §2.3 #21）；🔴 但**镜像已过期**（board `:5995`），覆盖今天树的实测仍欠 |
| #22/#8「队列失败没有原因码」 | R37 worker 半程在树（但台账仍判 PARTIAL） | `0c08209`（并树）／`45b9720`（施工） | `app/common/reliable_queue.py:498`；🔴 **不许据此翻绿**：`scripts/audit_plan_ticket_ledger.py:283` 自判 PARTIAL |
| 前端残格 G17/G18/G20/G08/G10-12 | R412（`4344e6d`）／G18 零命中／R410（`73dd85f`）／R313 族／R316 族 | 逐枚 rc=0 | `DocPanel.vue:354` 只剩一枚注释；`router/index.js:74 title:'喂料'`；`DEBT_TOTAL_RATCHET = 0`（`:60`）；`DocPanel.vue:650`；`router/index.js:105/:140`＋`AdminPanel.vue` |
| 前端残格 G03 主货（终答文件名） | R414（`18ca560`）＋R415（`ac84f1a`）＋R519（`03cd2eb`） | rc=0 | `chat.py:362/:372/:383-384`；`ChatPanel.vue:597/:669/:1546-1560/:2155`；件 `tests/test_r414_b_terminal_data_filename.py`／`_c_upload_prose.py` 在树 |
| 🔴 G03 的 a 半格（空部门上传拒收） | **这格不是「待立单」——早已整格退回并钉成现状形状** | `18ca560`（并树 R414） | 看板 `:5802` 原文：「『要新立一枚治 upload 空部门』是**重复立案**——R414 (a) 格早已随 `18ca560` 并树并整格退回，本席已撤销」；`tests/test_r414_a_department_free_upload.py` 钉的就是**现状形状**；真堵点＝业主 A1（`human-gates.md:373` 已裁「不在真库做」）⇒ **谁再派一枚「让上传拒空部门」都是重复单** |
| #R48 首屏线索卡 | 路线甲并树 | **`0ad3d3e`**＋前置解锁 **`efe5461`** | `frontend/src/components/AnswerHeadlineCard.vue` 在树 |
| R32／R33 整单 | 台账判 LANDED | `8a91f4e`／`9678d21` | 件 `tests/test_r32_lane_contract.py`／`tests/test_r33_*.py` 两枚；`app/memory/summarizer.py:2/:6/:21` |
| R43 的 ① 半张 | R43a 已落码 | `4586bb4`（＋R43b＝R167 `839c344`） | 台账 `:299-301` 明写「① 由 R43a 落码」；🔴 只欠「cached 落库那一列」＝在途 R523 |
| R46 后端半张＋消费侧 | R152／R195 跨号落地 | `eaa9af8`（施工 `c29ccf5`）／`484536c` | `migrations/0011_document_activity_signals.sql`／`frontend/src/lib/feedback.js` 在树；强度校准今天有 **R525 `0b44df1`** 读数 |
| R31 批准腿（今天） | R524 代号 B 并树 | **`05bec06`**（＝本席基点） | `git grep -c stream_piece_sink` → nodes 3／orchestrator 9／chat 2；件 `tests/test_r524_sink_reaches_both_runways.py` 等三枚在树 |
| 计划书「还剩 8 枚零提交」 | 已被三次推翻（`:470`／`:474`／R521） | `581cfb0`（并树 R521） | 见 §4 全表 |

**🔴 号账两条（派工前必读，防同号双投）**

1. `git log --oneline --grep=R511` → **`bcad2a8`「R511: P-19 执行状态锁落进仓内…」**已被占用，而看板 `:6010` 那行仍写「`R511` 候选 `calculation_runs` 生产方取证」⇒ 名册滞后，**R511 不可再用**。
2. 本席对 R536–R550 逐号 `git log --oneline -E --grep '<号>([^0-9]|$)'` 现取 → **全部 0 提及**（干净号）。禁用：R527（＝代号 C，业主席已写好待投）、R141–R144（业主自用号，且 `R141` 是 R32 拆出去的那一格）、R532/R533/R534/R535（本班在途）。

---

## 6. 波次五派工底稿（判据③＋判据④：每条半／未落给写域、撞谁、估时、归属）

**在途名册（本席现取，两条来源分开标）**：本席树里的看板（`05bec06` 版）`:6009` 仍写「本波在途四枚＝`Kuhn`/R523 · `Raman`/R524 · `Parfit`/R525 · `Gauss`/R526」，其中 **R524 `05bec06`／R525 `0b44df1`／R526 `efc5c50` 今天都已并树**（逐枚 rc=0）⇒ 那一行该改口，只剩 **R523 仍在途**（`git log --oneline -E --grep '并树 R523([^0-9]|$)'` → **0 笔**；`--grep R523` → mention=1）。主树那笔看板（`git show 24ade21:docs/handoff/2026-09-15-orchestration-board.md` 现取 `:6051-6054`）已登记本班新派四枚：`Boole`/R532（`be-r532@05bec06`，审批题 15.03 s 超时**真成因取证**）、`Schrodinger`/R533（**`bridge_note` 那句手写枚数改派生**，明令禁碰 `contract-v1.md`＋`manifest.json`）、`Singer`/R534＝本席、`Erdos`/R535（`MODEL_CONTEXT_TOKENS` 与运行时 `num_ctx` 配套自检闸，一枚缺省值都不许改）。

| 号 | 一句症状 | 最小可执行写域（点到文件） | 它撞谁（在途单） | 估时 | V1 门还是纯 V2 | 顶替／前置条件 |
|---|---|---|---|---|---|---|
| **R536** | 产品问答链不发 `retrieval.completed` ⇒ `retrieval_traces` 永远空，V2「每轮问答可回查检索」没有数据（#12 的缺格、#20 的前置） | `app/api/v1/chat.py` 检索腿（`:1669-1671` 那一段）＋发射实现落在**唯一一处**：`app/rag/retrieval_pipeline.py`（该件在树，`git ls-files app/rag` 现取）＋新钉 `tests/test_r536_*.py`＋读数纸 `docs/testing/r536-*.md`。🔴 禁入：`app/trace/**`、`app/storage/persistence.py`、`migrations/**`、`docs/api/contract-v1.md`（全在 R523 写域） | 🔴 **R523**（`app/trace/**`＋`migrations/**`＋契约）⇒ 必须排它之后；同文件 `chat.py` 还压着 **R532**（它只取证不改，若改 `chat.py` 即冲突）与 R484/R497 族 | **1.5 人日** | **纯 V2**（V1 五格 A/B/C/D/E 不含它；但它是 C 门「检索留痕」那半从沙盒升级到生产读数的**唯一路径**） | 判据要能失败：跑一轮真问答后 `retrieval_traces.rows > 0` 且 `project_retrieval`（`app/trace/projections.py:321`）吃得到事件；🔴 不许拿 `POST /retrieval/debug` 那一腿冒充产品道（`docs/testing/r483-empty-tables-2026-09-29.md:104` 已钉死这条口径） |
| **R537** | `observability.py:864-866` 的 `bridge_note` 硬写「**six** of the seven」，契约 `contract-v1.md:1582` 写「**Five**」；派生真值＝5（7 枚 ModelTier − LANE_TIERS 点名的 2 枚） | 只改 `app/api/v1/observability.py:864-866` 那一串（改派生：`len([t for t in ModelTier if t not in set(LANE_TIERS.values())])`）＋一枚按形状而非枚数失败的钉。🔴 禁碰契约与 manifest | 🔴 **在途 R533 正是这一格**（看板 `:6052` 原文「`bridge_note` 那句手写枚数改**派生**」） | **0.2 人日** | 纯 V2 账面 | **默认不投**：只有 R533 交回时没收到这格才投（否则＝重复单，本席把它登记成 R533 的验收判据） |
| **R538** | 前端手抄后端坐标三枚假话：`notifications.js:26`（`:171/:194/:200` vs 真 `:187/:212/:218`）／`DocPanel.vue:112`（ROLE_CLEARANCE 少 auditor，rbac 今天四枚）／`DocPanel.vue:103`（`chat.py:3933` vs 真 `chat.py:4470`） | 只改这三行注释＋让它们**按派生失败**的钉（同族先例：`components/__tests__/r313-upload-classification.test.js:181` 就是正则现读 rbac 的派生钉，照它的形状做） | 属**前端 Agent 写域**（AGENTS.md：未经授权不得改 `frontend/`）；后端零写域冲突 | **0.3 人日** | 纯 V2 账面（V1 门无关） | 🔴 本席**只点名不动**；请总控转授前端席，并禁止再用「rg 一下注释还在不在」当判据——判据必须是「注释里的坐标＝后端现取坐标」 |
| **R539** | 告警闭环（ack→assign→close）今天**没有一行真数据**：`alerts=0`、`alert_rules=0`（后者 `needs_owner`） | 不改产品码；跑在册量具出读数＋新纸 `docs/testing/r539-*.md`；若要造规则须业主令 | 与 R523/R533/R535 零交集（不碰 `app/**`） | **0.5 人日 ＋ 业主令** | 纯 V2（V1 B/E 已整行移出门槛） | 前置＝业主给 `alert_rules` 定 owner；判据里要写死「造出来的规则必须带部门归因（`migrations/0012...:44`）」 |
| **R540** | OCR／表格／电子表格三格**端到端从没跑过一份真扫描件**（#13/#14/#15 的缺格） | 新 `scripts/r540_scanned_pdf_readout.py`＋读数纸；不改解析码 | 零交集；🔴 但要 CPU（rapidocr 本地跑，与 run10 窗争用；不打模型） | **1 人日** | 纯 V2 | 判据：一份真扫描件 → `loader` 交回的段里 `PAGE_SOURCE_OCR`（`app/rag/loader.py:81`）非空 → 索引里有字 |
| **R541** | V2 #19 只有量具没有样本：`users=3`、`user_profiles=0`，四档权限从没被 10～30 人样本试过 | 不改码；跑 `scripts/provision_bulk_accounts.py --count 30 --roles staff manager admin auditor --departments …`（dry-run 先行，零 socket）＋读数纸 | 零文件交集；🔴 **建号＝往库里写数据** | **0.5 人日 ＋ 窗** | 纯 V2 | 🔴 须业主令；且排在 R536 之后才有意义（样本要能触发检索留痕才测得出跨密级） |
| **R542** | pgvector 格②「热集让路延迟」两侧对比**从未有数据**（R428 从未跑：`--grep '并树 R428'` = 0 笔） | 不改产品码；读数单（在册原因码 `app/rag/hot_index.py:78`）＋新纸 | 零代码交集；🔴 要**独占安静机器**（计划书 `:528`：`0.873` vs `3.322` 差 4 倍那笔未结） | **1 人日（纯窗）** | 纯 V2，但是**翻 `INDEX_BACKEND` 默认的前置** | 不许与门或任何 Agent 同窗（事故 #81 口径）；建议与 R543/R544 并成一窗多判据 |
| **R543** | 客户尺寸两档差（`ef_search` 40 vs 100 在客户量级上的名次与延迟）仍未量；R485 今天**零提及＝从未投** | 不改码；跑 `scripts/r59_recall_compare.py`＋`scripts/r59c_sandbox_corpus.py`（两枚已随 R393 `f509f36` 跟生产同宽）＋一份新读数件 | 零代码交集；要安静机器 | **1 人日（纯窗）** | 纯 V2，同为翻默认前置 | 🔴 判据必须自带不可外推声明：沙盒 1008 枚上「100 与暴力精确解 180/180 全等」**不许**当客户结论（计划书 `:523` 原文） |
| **R544** | R470 那次重启实测跑在 **09-28 那版镜像**上；今天镜像又落后（R524/R525/R526 已并、R523 将动 `migrations/`） | `docs/testing/r470-restart-drill-2026-09-29.md`（经 `scripts/r470_restart_diff.py --sync` 生成）＋`docs/perf/raw/` 新批；🔴 不改量具逻辑 | 零代码交集；要窗；🔴 **与门不同树并发** | **0.5 人日 ＋ 窗** | 纯 V2（#21 已落一次，这格是「覆盖今天的树再证一次」） | 先 `docker compose --env-file deploy/.env.server build migrate`（业主侧口令在 `human-gates.md:326`）；`ALLOWED_GROWTH` 仍只许 `audit_events`；连 PG 一起 recreate 要**单列成新判据**，不许顺手扩 R470 |
| **R545** | #8/#22 那半格：队列道「失败有终态与原因码」缺真机重量（台账 R37 PARTIAL）；R31 队列道缺可注册点（`stream_piece_sink` 在 `deploy/queue_worker.py` **零命中**） | 注册点在 **`deploy/queue_worker.py:415 _drain_report_stream`**；投递面先裁契约（🔴 `docs/api/contract-v1.md`＝R523 写域）＋新钉 | 🔴 **R523**（契约那半）⇒ 排它之后 | **1 人日 ＋ 窗** | 纯 V2 | R524 已交回「队列道无可注册点 ⇒ `not_applicable` 带凭据」，**不许把这格洗绿**，只允许改派成「先裁投递面契约」 |
| **R546** | V1 **D 门三格从未宣布验过**：报告档可查回／`usage` 非零／`sources` 在流里（`v1-acceptance-record.md:45` 现取「🔴 0 格」） | 零产品码；run10 窗内读数＋验收记录改口（由总控代笔，`docs/handoff/2026-09-23-v1-acceptance-record.md:45`） | 开窗前置：主树那笔看板自述（`git log -1 --format=%B 24ade21`）「P-20 七格只剩 **provenance** 一枚 FAIL…开窗只差 `GIT_SHA`→build migrate→`up -d --no-build`→P-8 复跑」 | **0.5 人日 ＋ 窗** | 🔴 **这是 V1 验收门（D 格）**，不是纯 V2 | 排 R523 并树之后（它一动 `migrations/`＋`app/trace/`，镜像即过期，provenance 那格必先过）；同窗顺带收 `usage`／R38 那格 D-2 真机读数 |
---

## 7. 量不到／量不准的格子逐枚点名（＋各差什么条件）

### 甲·量不到：差一次「安静机器／真机」窗口（代码不缺）

| 格 | 今天为什么量不到 | 差的确切条件 | 归到 |
|---|---|---|---|
| pgvector 格②「热集让路延迟」 | 从未跑过：`git log --oneline -E --grep '并树 R428([^0-9]\|$)'` → **0 笔**（提及 2 笔） | 一台没人在跑测试的机器（计划书 `:528`：`0.873 ms` vs `3.322 ms` 差 4 倍那笔未结）；🔴 不许与门／任何 Agent 同窗 | **R542** |
| pgvector 格④「客户尺寸两档差」 | `R485` 今天**零提及＝从未投**；旧 `R432` 的产物**不采信**——看板 `:1573` 原文「`Zeno` … 🔴 **从未进 §0 名册**：不 wait／不 close／不并树，其产物一律不采信；R432 那一格需要重新派工」 | 客户量级语料＋安静机器；判据须自带「沙盒 1008 枚不可外推」声明（计划书 `:523`） | **R543** |
| #21 重启实测覆盖今天的树 | 那一次跑在 **09-28 镜像**上；看板 `:5995` 点名「R523 一动 `migrations/`＋`app/trace/`、R524 一动 `app/agents/`＋`app/api/`，并树后镜像即过期」，而 R524 今天已并树（`05bec06`） | 先 `docker compose --env-file deploy/.env.server build migrate`（业主口令在册 `human-gates.md:326`）→ 两形各一次 → `--check` 逐字节；🔴 连 PG 一起 `--force-recreate` 要单列新判据（**卷存活今天没证**） | **R544** |
| #13/#14/#15 端到端（真扫描件进→索引有字） | 全库 1008 枚向量来自演示语料（`r483` 面 A 自述 `corpus_is_demo_corpus: true`），没有一份真扫描件走过这条腿 | 一份真扫描件＋CPU 窗（rapidocr 本地，**不打模型**） | **R540** |
| #8/#22 队列道「失败有终态与原因码」 | 码与牙在（`reliable_queue.py:498`），台账 `:283` 自判 **PARTIAL**，欠真机重量；R31 那半格更硬：`git grep -q stream_piece_sink -- deploy/queue_worker.py` → **rc=1**（无可注册点） | 一次真队列失败读数；且先裁投递面契约（`docs/api/contract-v1.md`＝R523 写域） | **R545** |
| R46 的 U1/U2/U3（真库有信号名次／真 ANN 端到端／真并发打点名次） | R525 已并树（`0b44df1`）但**三格原样入档**，其并树笔自述（`git log -1 --format=%B 0b44df1`）：U1「全单只读不许打点，需业主在产品里点采纳/驳回，或授权在非生产演示库跑一次 `POST /api/v1/feedback`——写操作属业主动作」；U2「compose 未发布 postgres 宿主端口，实测 connect timeout；且需打 embedding＝打模型」；U3「需 run10 之后的安静机器窗口」 | U1 业主动作；U2 宿主端口＋禁打模型；U3 窗 | 丙＋乙（不重复派 R525 的活） |
| #12 检索留痕（D 组那枚） | `retrieval_traces.rows=0`，而闸门是**有没有人发事件**，不是有没有窗 | 先补码（R536），窗只用来验 | **R536** |

### 乙·量不到：差一次「V1 验收门」本身

| V1 格 | 今天的脸（现取坐标） | 差什么 | 归到 |
|---|---|---|---|
| **A④ 逐类不退化** | `docs/handoff/2026-09-23-v1-acceptance-record.md:43`：「`口径冲突 0.4211 → 0.3158`（19 题掉 2 题）…**第二次由本判据抓到真退化**⇒ 不许拿『总分涨了』抵账，需归因单」 | 一枚**归因单**（不是门）：本席未跑分、不代判 | 🔴 归因单，不属 Agent 波次 |
| **C 检索与缓存（越权格）** | 同件 `:44`：「越权格 **未验**」，判据出处计划书 §13；`docs/testing/r469-sandbox-scope-readout-2026-09-28.md:55-58`（a 未验／b FAIL／c FAIL／d 未验） | 业主 A1＋A3；**已裁「不在真库做」/「交付阶段做」** ⇒ Agent 侧永远收不掉，只能保持「未验」 | 丙（业主 A1/A3） |
| **D 后台化与观测** | 同件 `:45`：「报告档可查回／`usage` 非零／`sources` 在流里——**三格从未宣布验过** ⇒ 🔴 0 格」 | run10 窗一次读数；开窗前置今天只剩 provenance（`git log -1 --format=%B 24ade21` 原文「P-20 七格只剩 provenance 一枚 FAIL，🔴 gpu_apps／foreign_python 今天双双 PASS…开窗只差 `GIT_SHA`→build migrate→`up -d --no-build`→P-8 复跑」） | **R546** |
| **B／E** | 同件 `:46`：「⚪ **移出 V1 门槛**（B＝部署档位标定，物理前提在第一版硬件上不成立；E＝上线实施清单，其越权格随 C 一起记『未验』）」 | 不排期；E 那半随 C | 不排期（随 C 记未验） |
| 首屏 ≤1 s（R48 判据①） | 台账 `:316-317`：「① 首屏 ≤1 s 在本机硬件口径上**物理不可达（地板 11.0 s）**，B 行已整行移出 V1」 | 业主裁口径（看板 `:6010` 队列里那行「R48 判据① 首屏秒数（欠业主裁口径）」） | 丙 |
| 评测集 29 条无出处 | `human-gates.md:320` D10：「105 题里 **29 条无出处，其中 25 条补料救不回**（分解：8 措辞漂移＋15『出处』概念不适用＋1 要补条款＋1 …）」 | 业主改题面／裁口径，Agent 不许代判 | 丙 |

### 丙·量不准：🔴 本席亲自抓到并写进规矩的六枚口径陷阱

| 陷阱 | 现取的假读数 | 正确的量具／名字 |
|---|---|---|
| 用 `rg -c '<button'` 判裸按钮 | 今天回 **14 枚**，逐枚原文全是注释/自述（`App.vue:630/:672`、`DashboardPanel.vue:621`、`AdminPanel.vue:26`、`AuditEventsPanel.vue:25`、`EvaluationsPanel.vue:23`、`SloPanel.vue:28`、`TracePanel.vue:41`） | 本仓唯一量具 `frontend/src/components/__tests__/r288-native-button-scan.js`（`:40` 明写排除 `components/ui/`）＋棘轮 `r288-native-buttons.test.js:60 DEBT_TOTAL_RATCHET = 0` |
| 按底本省略号里的假件名查迁移 | `rg -n "ALTER TABLE IF EXISTS alerts ADD COLUMN" migrations/0012_legacy_scope_columns.sql` → `IO error … 找不到文件`；换成不带文件名的 `rg ... migrations` 也**零命中**（因为那行被拆成 `:43` ALTER＋`:44` ADD COLUMN 两行） | 真名 `migrations/0012_alert_and_pending_approval_attribution_columns.sql`，查 `ALTER TABLE IF EXISTS alerts` → `:43/:44` |
| 用「这一层的错名字」查列类型 | `rg -n "owner_id UUID" migrations/0002...` → **零命中**（列其实是 `TEXT NOT NULL`） | `git grep -n owner -- migrations/0002_execution_data_lineage.sql` → `:7/:34/:54/:74` |
| 拿段范围当逐列行号 | 底本写「时钟列 `0014...:52-58`」，而该件自底本 **ZERO-CHANGE** ⇒ 不是漂，是写得粗 | 今天逐列钉死：`acknowledged_at :58`／`closed_at :64`／`assigned_at :73` |
| 现场 env 不在任何树里 | `git ls-files deploy/.env.server` → **0 行**；本席树里 `Test-Path` 取不到 ⇒ 「翻没翻旋钮」这格**只能**在主树盘上取（`rg -n 'INDEX_BACKEND' deploy/.env.server` → 零命中） | 现场态与代码态分开报；不许拿代码缺省值冒充客户现场 |
| `git grep -c` 不报零命中文件 | 它对 `deploy/queue_worker.py` **根本不出现**在输出里，容易被误读成「命令没跑」 | 证「没有」用 `git grep -q <名> -- <路径>`，看 `rc`（本席对 `stream_piece_sink` 交回 **rc=1**） |

---

## 8. 交回格式①：`git -C <树> status --porcelain` 原样

```
?? docs/handoff/2026-09-30-v2-gap-recheck-3.md
```

（本单唯一写入＝这枚新文档；无任何已跟踪文件被改动，`git diff --stat` 与 `git diff --cached --stat` 在本席树上均为空。）

### 附：一条命令复跑本单全部 sha 归因（总控抽验请直接用这条）

```powershell
cd C:\Users\fengx\PycharmProjects\be-r534
$shas = '5963dfe','c0c4bcd','4fcca16','16337fc','ed94d16','f65d42e','d8b132f','2a54db3','1b4406a',
        'f509f36','dc47119','05bec06','0b44df1','efc5c50','581cfb0','791568c','eef642b','a7cd9b6',
        '62c734d','8a91f4e','0cfd86a','9678d21','b35e10f','c81fbb5','2e6abc6','839c344','4586bb4',
        'c29ccf5','eaa9af8','484536c','0ad3d3e','efe5461','3aba146','dbb8ba4','e9aac2f','acc092e',
        '6d00d70','18ca560','ac84f1a','4344e6d','73dd85f','3b20e68','5270c40','e5917b6','8cc4937',
        '438d67d','f2434f8','5b8d767','399a5a4','793fcce','03cd2eb','cda0e28','8d228be','bcad2a8',
        '227949e','c23e44c','c2e6546','9e817e1','46ee7ad','5e9f901','2ba2bc2','97724c5'
$bad = @(); foreach ($s in $shas) { git merge-base --is-ancestor $s HEAD; if ($LASTEXITCODE -ne 0) { $bad += $s } }
Write-Output "checked=$($shas.Count) not-ancestor=$($bad -join ',')"
```

本席现取：`checked=62 not-ancestor=`（空 ⇒ 62 枚全部是 `05bec06` 的祖先）。🔴 唯一例外说明：`24ade21` **不是**本席基点的祖先（它是本席建树之后总控落的看板笔），所以它不进这条复跑，凡引用它都用 `git show 24ade21:<路径>` 或 `git log -1 --format=%B 24ade21` 这两种可逐字复跑的形式。

另附一条复跑「八枚零提交」的计数器（§4 的数就是这么来的）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r534
foreach ($t in 'R29','R31','R32','R33','R38','R43','R46','R48') {
  $m = (git log --oneline -E --grep "$t([^0-9]|`$)" | Measure-Object -Line).Lines
  $l = (git log --oneline -E --grep "并树 $t([^0-9]|`$)" | Measure-Object -Line).Lines
  Write-Output "$t mention=$m landed=$l"
}
```

本席现取：`R29 30/1`·`R31 17/1`·`R32 11/1`·`R33 10/1`·`R38 10/1`·`R43 16/1`·`R46 16/0`·`R48 12/2`。

---

## 9. 一句话交给波次五

**V2 今天真正欠的码只有一枚**（R536：问答腿不发 `retrieval.completed`），其余全是**账面改口**（R537/R538，两枚都撞在途单，默认不投）与**欠一次量**（R540–R546，全要窗口或业主令）；而**翻 `INDEX_BACKEND` 前面立着的三格没有一格是代码**——是业主 A1/A3、一台安静机器、和客户量级。派工前请先复跑 §5 那张「已并树」表，那十二行里有五行是旧纸还写着「欠」的。
