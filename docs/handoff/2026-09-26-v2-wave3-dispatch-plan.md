# V2 波次三 派工计划（2026-09-26 20:4x（原文误记 23:2x：本机现取 21:05，落笔时为 20:4x） · 总控线 · 基点 `fa36ac1`）

- 事实源：`docs/version-roadmap-and-next-week-plan-2026-09-22.md` 的 V2 硬要求（`:253-264`）与新增业务能力（`:268-273`），验收口径在 `:636-641`。
- 本波只挑**写集互斥、可并发**的单；每单的判据在派工词里逐字下发，本文件只做队列与撞车图。
- 全部数字都在 `fa36ac1` 现取，不是转述。

> 🔴 **本波作废（R408 复算 · 2026-09-28）：§2 那六枚队列逐枚现取，六枚全部早已并树。**
> 照这张表派工＝给已经交付的单再派第二个人——本仓事故 #14 那一族（同单双人，账面记过九次）。
> 逐枚归因、现取凭据与「纸面那句症状现在的现场」在文末 §5。本文所有 `file:line` 坐标都是
> 09-26 落笔当日读数，多处已漂，引用前现取。
## 1. V2 硬要求逐条对照（今天真位置）

| V2 要求（roadmap 行号） | 今天 | 凭据 |
|---|---|---|
| `Document/DocumentVersion` | 已落 | R301 页源账 `a0179b6`、R298 OCR |
| `Dataset/DatasetVersion` | 已落 | V2 第一波 R249 |
| `Artifact` / `CalculationRun` | 已落 | V2 第一波 R248、R291 错误原话渲染 `67e28a4` |
| 所有资源有稳定 ID、owner | 已落 | 文档行 R310 `217d542` 已带 owner；数据预览那一格**今天也带了**（R337 已并树 `aefa3ce`；09-28 现取 `app/api/v1/data.py` 两处出口都答 owner，无主口径与 R310 同为 `None` 不是空串） |
| staff/manager/admin/auditor 权限统一 | 已落 | R30、R45、R200 |
| PG 成为主要业务存储 | 进行中 | R59 切读在途，默认仍 `chroma`（`app/rag/indexing.py:50`） |
| Dashboard 真实期间与真实数据 | 已落（期间那一半） | 四格真数在树；**期间口径今天有了**（R332 已并树 `ae7dc96`；09-28 现取 `app/api/v1/dashboard.py` 里 trend/period/series 逐枚命中，上面那句 exit 1 是 09-26 的读数、已过期）。随后 R340 `dbb8ba4`、R342 `e9aac2f` 两格也已并树 |
| 告警确认/转派/关闭闭环 | 已落 | R251（`alerts.py:343` 三枚动作字段表） |
| 管理员按 run_id 查 Trace | 已落 | R250 |
| OCR 与扫描 PDF | 已落 | R298 |
| PDF/Word 表格解析 | 已落 | R300 模块+契约、R304 接线 `9344028` |
| Excel/CSV 知识库模式 | 已落 | 解析层 R305 已并树 `01db964`；接线单 R306 第二棒**也已并树** `6d00d70`（09-28 现取：`app/rag/loader.py` import `app/rag/spreadsheets.py`，`app/documents/file_security.py` 点名 .xlsx/.csv 归它读） |
| 知识图谱、审批助手、通知基础能力 | 半（通知那一格已落） | 通知后端在树（`app/api/v1/notifications.py`）；前端正脸**今天有了**（R333 已并树 `42a4e9e`；09-28 现取 `frontend/src/components/NotificationBell.vue` 与 `frontend/src/lib/notifications.js` 都在树里） |
| PGVector 正式接入读路径 | 进行中 | 双写在跑、读路径仍在 Chroma，切读收口卡业主 live-PG |

**结论**：V2 不是"要不要开工"的问题，第一波/第二波共十三枚已并树。本波清的是三处**能力面缺口**与两处**同类出口欠账**。

## 2. 本波队列（写集互斥 ⇒ 可并发；序号即投递顺序）

| 号 | 一句话症状 | 写域 | 关键判据 | 撞车 | 今天（R408 现取 2026-09-28） |
|---|---|---|---|---|---|
| **R332** | Dashboard 只有"现在有几篇"，没有"这个月发生了什么" | `app/api/v1/dashboard.py` + 契约文末 + 新钉 | 期间只准由真实时间列算（`alerts.py:116/:122` 有 `acknowledged_at`/`created_at`，文档侧 `catalog.py` 有 `created_at`）；空期间必须给"零"这张脸而不是删键；不许新表、不许新列 | 无主，随时可投 | **已并树 `ae7dc96`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：`GET /dashboard/trend` 在树。 |
| **R337** | 数据文件预览回 `dataset_id/version_id/classification`（`data.py:294-300`），独缺 owner；`:305` 那个 preview 出口同病 | `app/api/v1/data.py` + 新钉 | 与 R310 同一把无主口径（`catalog.py` 的 `None`，不是空串）；不为补字段多开一次查询；逐档行数不变 | 与 R332 同树不同文件，可并发 | **已并树 `aefa3ce`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：两处出口都答 owner。 |
| **R336** | `.xls` 是条死路：`app/tools/excel.py:87` 按扩展名选 `engine="xlrd"`，而 `pyproject.toml` 只有 `openpyxl`（`:29`） | `app/tools/excel.py` + 新钉 | 要么明确拒绝并给可读原因码（零新增码⇒用既有枚举），要么换真在依赖里的读法；不许为此新增依赖 | 无主 | **已并树 `fc13df9`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：`.xls` 走可读原因码，不再 ImportError。 |
| **R333** | 通知中心后端在树、前端没有正脸（G10/G16 一族） | 新组件 + `lib/notifications.js` + 新钉 | 🔴 若必须动 `App.vue` 立即停手回报（那是 R307 第二棒的写域）；不得另开第二本待办账 | 排在 `Ampere` 让出 `App.vue` 之后 | **已并树 `42a4e9e`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：通知前端正脸在树。 |
| **R314/R315/R316** | 图谱承接 / 成果屏 / 管理屏骨架（R309 复评 A 组） | 见 `docs/handoff/2026-09-26-frontend-gap-recheck.md` | 三枚导航钉无主可改；`R315` 与 `R316` 同抢 `router/index.js` ⇒ 只能派一枚或合一枚 | 部分等 `App.vue` | **三枚全部已并树**：R314 `40fe97c`｜R315 `2cb3401`｜R316 `d609165`（三枚 cat-file -t→commit｜HEAD 祖先）｜它们依赖的那份复评 R309 亦已并树 `fa36ac1` |
| **R338** | R301 那一跳的下游：`DocPanel.vue` 把 `pdf_extraction` 整格丢掉 | `frontend/src/components/DocPanel.vue` | 真路径凭据，不许手搭夹具冒充 | 🔴 与 **R313** 同文件 ⇒ 严格串行，排 R313 之后 | **已并树 `e0168b7`**（cat-file -t→commit｜HEAD 祖先）｜症状已兑现：`DocPanel.vue` 今天读 `pdf_extraction`；它等的 R313 亦已并树 `e80810c`。 |

## 3. 本波明确不做

- 不翻 `INDEX_BACKEND_DEFAULT`（09-28 现取 `app/rag/indexing.py` 里它仍是 `chroma`），不宣布切读完成，**R60 不许翻绿**。09-28 补一格：这枚旋钮今天起在两枚示例模板里各有一行**注释掉、值仍是 `chroma`** 的可抄落点（`.env.example`、`deploy/.env.server.example`）——落点是文档面，翻闸仍属业主。
- 不动评测集（被 `tests/test_evaluation_report.py` 钉住），不改 105/135 两本题数口径。
- 不碰 `frontend/src/assets/theme.css` 的背景五层与 `ui/**` 原语（R307/R293 一族在写）。
- 反证钉（`counter_evidence` / `teeth`）不分层出门：门再便宜也全跑。
- 在途 ≥2 枚时不跑全量门；全量门只认 `python scripts/run_gate.py`。

## 4. 等业主本人（波次三推不动的那几格，不是代码问题）

1. live-PG 凭据：R305/R283 那一格真库读数、`r59_recall_compare` 的 135 题窗（题数须显式 `--fixture` 锁口径）。09-28 现取：R305 已并树 `01db964`、R283 已并树 `920460f`，那枚量具的候选宽度口径也已由 R393 并树 `f509f36` 收掉⇒ 这一格欠的是**窗**，不是码。
2. 真机跑分窗口（V1 侧唯一剩余项），开窗前 `powercfg /change standby-timeout-ac 0`。
3. A① 整表 p95 还是分档 p95 —— 口径不钉死，阶段 A 不许翻绿。
4. `deploy/.env.server:56 VECTOR_DUAL_WRITE=on` 仍在喂墓碑堆，停不停由业主定。09-28 现取补两句：`deploy/.env.server` 是**未跟踪的现场件**（只存在于主树，本树 `Test-Path` 为 False），且同一份文件里 `INDEX_BACKEND` 零命中 ⇒ 默认确实还没翻。

---

## 5. 🔴 本波作废：逐枚归因（R408 · 2026-09-28 · 凭据全部本轮 `git` 现取）

**结论一句话：§2 那六枚队列六枚全部早已并树，本波作废，不许再照它派工。**

为什么这一节要现取：09-27 夜里总控差点把波次四那枚「无主、槽一空就投」的 R341（已并树 `acc092e`）
投出去——就是这两张纸咬的。本仓事故 #14 是同一族（同一枚单派两个 Agent，账面记过九次），差一次
就复现。下面每一枚的 sha 都跑过一次 `git cat-file -t`，读数原样抄在栏里；零提交的写法只有「零提交」
一种，且附空读数（本波没有零提交项：六枚全有）。

| 单号 | 今天的状态 | `git cat-file -t <sha>` | 并树标题（`git log -1 --format=%s` 截取） | 纸面那句症状，09-28 现取的现场 |
|---|---|---|---|---|
| R332 | 已并树 `ae7dc96`（09-26 21:23） | `commit`，且 `merge-base --is-ancestor` rc=0 | R332 并树（施工 Halley…@be-r332）：Dashboard 第一次有期间口径 | `app/api/v1/dashboard.py`：trend/period/series 命中，`GET /dashboard/trend` 在树 |
| R337 | 已并树 `aefa3ce`（09-27 11:03） | `commit`，rc=0 | R337 并树（施工 Harvey…@be-r337）：数据集两处出口第一次都答 owner | `app/api/v1/data.py`：owner 与 `_dataset_row_owner_id` 在树，无主交 `None` |
| R336 | 已并树 `fc13df9`（09-26 22:30） | `commit`，rc=0 | R336 并树（施工 Heisenberg…@be-r336）：客户传真来的 .xls 以前走到的是运行时 ImportError | `app/tools/excel.py`：扩展名表里 `.xls` 走拒收原因码，`xlrd` 只出现在解释为什么不能用的注释里 |
| R333 | 已并树 `42a4e9e`（09-27 10:36） | `commit`，rc=0 | R333 并树（施工 Huygens…@be-r333）：通知中心第一次有前端正脸 | `frontend/src/components/NotificationBell.vue`、`frontend/src/lib/notifications.js` 均在 `git ls-files` |
| R314 | 已并树 `40fe97c`（09-26 22:15） | `commit`，rc=0 | R314 并树（施工 Bohr…@be-r314） | `frontend/src/router/index.js` 有 `/graph` 路由，`GraphPanel.vue` 在树 |
| R315 | 已并树 `2cb3401`（09-27 12:25） | `commit`，rc=0 | R315 并树（施工 Noether…@be-r315）：成果屏第一次有自己的位置 | 同文件 `/artifacts` 路由在树，`ArtifactsPanel.vue` 在树 |
| R316 | 已并树 `d609165`（09-27 11:47） | `commit`，rc=0 | R316 并树（施工 Sartre…@be-r316）：管理员第一次有一枚能看的屏 | `AdminPanel.vue` 今天存在（09-26 那行 `Test-Path False` 已过期），路由 `/admin` 在树 |
| R338 | 已并树 `e0168b7`（09-26 22:34） | `commit`，rc=0 | R338 并树（施工 Plato…@be-r338） | `frontend/src/components/DocPanel.vue` 今天读 `pdf_extraction` |

另三格顺手登记（都是这两张纸的下游，别再当欠账派）：R306 第二棒 `6d00d70`、R339 `957c7d2`、R340 `dbb8ba4`、R342 `e9aac2f`、R341 `acc092e`——五枚 `git cat-file -t` 读数同为 `commit`。
本节一字不改判据：§3 那五句「本波明确不做」今天全部仍然成立。

> 复算人：R408（执行层）。本文件与 `-wave4-dispatch-plan.md` 是本单唯一被改的两张派工面纸，改动全部是**加今天的状态**，纸面原话逐字留在行内。
