# V2 波次三 派工计划（2026-09-26 20:4x（原文误记 23:2x：本机现取 21:05，落笔时为 20:4x） · 总控线 · 基点 `fa36ac1`）

- 事实源：`docs/version-roadmap-and-next-week-plan-2026-09-22.md` 的 V2 硬要求（`:253-264`）与新增业务能力（`:268-273`），验收口径在 `:636-641`。
- 本波只挑**写集互斥、可并发**的单；每单的判据在派工词里逐字下发，本文件只做队列与撞车图。
- 全部数字都在 `fa36ac1` 现取，不是转述。

## 1. V2 硬要求逐条对照（今天真位置）

| V2 要求（roadmap 行号） | 今天 | 凭据 |
|---|---|---|
| `Document/DocumentVersion` | 已落 | R301 页源账 `a0179b6`、R298 OCR |
| `Dataset/DatasetVersion` | 已落 | V2 第一波 R249 |
| `Artifact` / `CalculationRun` | 已落 | V2 第一波 R248、R291 错误原话渲染 `67e28a4` |
| 所有资源有稳定 ID、owner | **半** | 文档行 R310 `217d542` 已带 owner；数据预览那一格还没带 ⇒ **R337** |
| staff/manager/admin/auditor 权限统一 | 已落 | R30、R45、R200 |
| PG 成为主要业务存储 | 进行中 | R59 切读在途，默认仍 `chroma`（`app/rag/indexing.py:50`） |
| Dashboard 真实期间与真实数据 | **半** | 四格真数在树；全件零期间口径（`rg -n "trend\|period\|series" app/api/v1/dashboard.py` exit 1）⇒ **R332** |
| 告警确认/转派/关闭闭环 | 已落 | R251（`alerts.py:343` 三枚动作字段表） |
| 管理员按 run_id 查 Trace | 已落 | R250 |
| OCR 与扫描 PDF | 已落 | R298 |
| PDF/Word 表格解析 | 已落 | R300 模块+契约、R304 接线 `9344028` |
| Excel/CSV 知识库模式 | **在途** | R305 解析层 `01db964`；接线单 **R306** 施工中（`Mendel`/`Rawls` 线） |
| 知识图谱、审批助手、通知基础能力 | 半 | 通知后端在树（`app/api/v1/notifications.py`），前端正脸无主 ⇒ **R333** |
| PGVector 正式接入读路径 | 进行中 | 双写在跑、读路径仍在 Chroma，切读收口卡业主 live-PG |

**结论**：V2 不是"要不要开工"的问题，第一波/第二波共十三枚已并树。本波清的是三处**能力面缺口**与两处**同类出口欠账**。

## 2. 本波队列（写集互斥 ⇒ 可并发；序号即投递顺序）

| 号 | 一句话症状 | 写域 | 关键判据 | 撞车 |
|---|---|---|---|---|
| **R332** | Dashboard 只有"现在有几篇"，没有"这个月发生了什么" | `app/api/v1/dashboard.py` + 契约文末 + 新钉 | 期间只准由真实时间列算（`alerts.py:116/:122` 有 `acknowledged_at`/`created_at`，文档侧 `catalog.py` 有 `created_at`）；空期间必须给"零"这张脸而不是删键；不许新表、不许新列 | 无主，随时可投 |
| **R337** | 数据文件预览回 `dataset_id/version_id/classification`（`data.py:294-300`），独缺 owner；`:305` 那个 preview 出口同病 | `app/api/v1/data.py` + 新钉 | 与 R310 同一把无主口径（`catalog.py` 的 `None`，不是空串）；不为补字段多开一次查询；逐档行数不变 | 与 R332 同树不同文件，可并发 |
| **R336** | `.xls` 是条死路：`app/tools/excel.py:87` 按扩展名选 `engine="xlrd"`，而 `pyproject.toml` 只有 `openpyxl`（`:29`） | `app/tools/excel.py` + 新钉 | 要么明确拒绝并给可读原因码（零新增码⇒用既有枚举），要么换真在依赖里的读法；不许为此新增依赖 | 无主 |
| **R333** | 通知中心后端在树、前端没有正脸（G10/G16 一族） | 新组件 + `lib/notifications.js` + 新钉 | 🔴 若必须动 `App.vue` 立即停手回报（那是 R307 第二棒的写域）；不得另开第二本待办账 | 排在 `Ampere` 让出 `App.vue` 之后 |
| **R314/R315/R316** | 图谱承接 / 成果屏 / 管理屏骨架（R309 复评 A 组） | 见 `docs/handoff/2026-09-26-frontend-gap-recheck.md` | 三枚导航钉无主可改；`R315` 与 `R316` 同抢 `router/index.js` ⇒ 只能派一枚或合一枚 | 部分等 `App.vue` |
| **R338** | R301 那一跳的下游：`DocPanel.vue` 把 `pdf_extraction` 整格丢掉 | `frontend/src/components/DocPanel.vue` | 真路径凭据，不许手搭夹具冒充 | 🔴 与 **R313** 同文件 ⇒ 严格串行，排 R313 之后 |

## 3. 本波明确不做

- 不翻 `INDEX_BACKEND_DEFAULT`（`app/rag/indexing.py:50` 仍是 `chroma`），不宣布切读完成，**R60 不许翻绿**。
- 不动评测集（被 `tests/test_evaluation_report.py` 钉住），不改 105/135 两本题数口径。
- 不碰 `frontend/src/assets/theme.css` 的背景五层与 `ui/**` 原语（R307/R293 一族在写）。
- 反证钉（`counter_evidence` / `teeth`）不分层出门：门再便宜也全跑。
- 在途 ≥2 枚时不跑全量门；全量门只认 `python scripts/run_gate.py`。

## 4. 等业主本人（波次三推不动的那几格，不是代码问题）

1. live-PG 凭据：R305/R283 那一格真库读数、`r59_recall_compare` 的 135 题窗（题数须显式 `--fixture` 锁口径）。
2. 真机跑分窗口（V1 侧唯一剩余项），开窗前 `powercfg /change standby-timeout-ac 0`。
3. A① 整表 p95 还是分档 p95 —— 口径不钉死，阶段 A 不许翻绿。
4. `deploy/.env.server:56 VECTOR_DUAL_WRITE=on` 仍在喂墓碑堆，停不停由业主定。
