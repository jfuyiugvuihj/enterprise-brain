# R640 · 账尺派生化——改前改后 43 行对照（取证纸）

- 工单：R640＝账尺派生化。树：`be-r640`（基点 `2103890`）。写域货四枚：`scripts/audit_plan_ticket_ledger.py`（改）＋ `tests/test_r640_ledger_tiers_are_derived.py` ＋ `tests/test_r640_counter_evidence_teeth.py` ＋ 本纸。
- 本纸不写账本：`docs/handoff/**` 一字未动、计划书一字未动；改表由人写段落笔。
- 表里每一格都不是手抄：改前档＝基点那把尺在基点上的读数，改后档与凭据＝本树这把尺的读数，复现命令在 §8。
- 行位口径：本纸不写 `文件:行号`，也不抄别家的 `.md` 行号；量具现取的行位在本纸里一律省略，要就重跑量具。

## 1. 命令原文与实取读数（成对）

```powershell
# 改前：基点的分离工作树＋基点原样那把尺（未投任何货）
git -C C:\Users\fengx\PycharmProjects\be-r640 worktree add --detach $env:TEMP\r640-state2 2103890
cd $env:TEMP\r640-state2
& C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe scripts\audit_plan_ticket_ledger.py
```

读数摘录：

> R262 计划书台账归真 · 机器账（只读 git 与工作树；判据原文一律现读现切）
> head=2103890b23183119baec31f81fdf7ee6a13eb553 commits_on_head=1289 worktree=clean
> 三档口径：LANDED＝产物在树且无点名欠账；PARTIAL＝产物在树但点名欠判据；ZERO＝HEAD 祖先链上全史零产物
> 归属口径：提交标题里第一枚单号＝该提交的归属号（拆单子号 R26a/R43a/R152 一类按账上具名挂靠，不自动并号）；标题含 catch up/追平/保活 的只记账不作产物证据
> 产物口径：产品码＝app/frontend/scripts/tests/migrations/deploy/static 与代码类后缀；契约＝docs/api/** 与 migrations/manifest.json

> 在册 43 号：LANDED=23 · PARTIAL=17 · ZERO=3
> - LANDED：R30 R32 R33 R34 R36 R40 R41 R42 R45 R49 R141 R142 R145 R146 R253 R254 R255 R256 R257 R258 R259 R260 R261
> - PARTIAL：R25 R26 R27 R28 R29 R31 R35 R37 R38 R43 R44 R46 R47 R48 R50 R51 R52
> - ZERO：R39 R143 R144
> RESULT=PASS（0 条违规，在册 43 号逐条自证）

```powershell
# 改后：本树这把尺（apply 未 commit 态）
cd C:\Users\fengx\PycharmProjects\be-r640
& .\.venv\Scripts\python.exe scripts\audit_plan_ticket_ledger.py
```

读数摘录：

> R262／R640 计划书台账归真 · 机器账（只读 git 与工作树；判据原文、裁定句、理由句一律现读现切）
> head=2103890b23183119baec31f81fdf7ee6a13eb553 commits_on_head=1289 worktree=dirty:4
> 六档口径：LANDED＝产物在树且无点名欠账；PARTIAL＝产物在树但点名欠判据；CLOSED＝账面结案裁定句点名量具且其产物与取证纸都在仓内（派生）；ZERO＝HEAD 祖先链上全史零产物；FOREIGN＝计划书与跟进单 §21 都没有它的行（派生）；NOTBUILT＝计划书划删除线＋§21 不建裁定（派生）
> 派生纪律：CLOSED／FOREIGN／NOTBUILT 只许从事实派生——判定写死咬 C11，把已结案／外来／不建记成 ZERO 咬 C13，理由句与取证纸打架咬 C14，取证纸已判达却仍挂欠账咬 C15，派生落不实地咬 C12
> 归属口径：提交标题里第一枚单号＝该提交的归属号（拆单子号 R26a/R43a/R152 一类按账上具名挂靠，不自动并号）；标题含 catch up/追平/保活 的只记账不作产物证据
> 产物口径：产品码＝app/frontend/scripts/tests/migrations/deploy/static 与代码类后缀；契约＝docs/api/** 与 migrations/manifest.json
> 取证纸面：以标题行写 `G-<号>-<序>` 认领欠账格的仓内取证纸 1 枚（读不到而跳过 0 枚；正文里另有 24 处转述——转述不认领，不许顶掉量具那张纸的判语）；%TEMP% 里的工件不作派生源

> 在册 43 号：LANDED=23 · PARTIAL=17 · CLOSED=1 · ZERO=0 · FOREIGN=1 · NOTBUILT=1
> - LANDED：R30 R32 R33 R34 R36 R40 R41 R42 R45 R49 R141 R142 R145 R146 R253 R254 R255 R256 R257 R258 R259 R260 R261
> - PARTIAL：R25 R26 R27 R28 R29 R31 R35 R37 R38 R43 R44 R46 R47 R48 R50 R51 R52
> - CLOSED：R143
> - ZERO：无
> - FOREIGN：R144
> - NOTBUILT：R39
> RESULT=PASS（0 条违规，在册 43 号逐条自证）

```powershell
# 派生源的硬事实（现取，逐条）
git merge-base --is-ancestor 4da0bad HEAD   # R143 结案笔 → rc=0
git merge-base --is-ancestor d00b791 HEAD   # R51 量具并树笔 → rc=0
Test-Path docs\perf\r626-legacy-engine-silent-empty-recall-2026-10-04.md   # True
Test-Path docs\perf\r631-stage-sum-delta-2026-10-04.md                     # True
Test-Path scripts\r626_legacy_engine_silent_empty_probe.py                  # True
Test-Path tests\test_r626_legacy_silent_empty_teeth.py                      # True
```

确定性：同一条命令在本树连跑两遍，两枚输出用 `git diff --no-index --stat` 比对为空（逐字节相同），所以本纸只认一份读数。

## 2. 四格前后（本单要治的病）

| 号 | 改前档 | 改前那格尺面原话 | 改后档 | 派生用的事实 | 仓内凭据 |
|---|---|---|---|---|---|
| R143 | ZERO | R143 名下全史零提交；它点名的脚本早在 R58 名下就有（`a896cf6`），那一次预跑至今记在 R58③ 真机欠账 | **CLOSED** | 计划书 §5.2 表内有它的行；跟进单 §21 无行；主干归集 0 枚产物提交；结案裁定：2026-09-15-backend-followup-requests.md 原文：**三、R143 结案（R626 那枚量具，快照副本读，105 题，13.0 s，两遍读数完全一致）** ／ 量具 R626 凭据 4da0bad｜取证纸 docs/perf/r626-legacy-engine-silent-empty-recall-2026-10-04.md｜仍在盘上的产物 2 枚：`scripts/r626_legacy_engine_silent_empty_probe.py`、`tests/test_r626_legacy_silent_empty_teeth.py` | `4da0bad` · `docs/perf/r626-legacy-engine-silent-empty-recall-2026-10-04.md` · `scripts/r626_legacy_engine_silent_empty_probe.py` · `tests/test_r626_legacy_silent_empty_teeth.py` |
| R144 | ZERO | R144 从没立过单——它是业主建议号里被避开的那一枚，也不在计划书 §5.2 表内 | **FOREIGN** | 计划书无行；跟进单 §21 无行；主干归集 0 枚产物提交；外来身份：计划书表格里读不到 R144 的行（含删除线形） ／ 外来身份：跟进单 §21 判据表里没有 R144 的行 ／ 外来身份：主干归集：R144 名下 0 枚产物提交 ／ 外来身份：台账未给它挂任何产物提交 | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R39 | ZERO | 裁定不建（沿用 R17）；HEAD 上 R39 名下零提交 | **NOTBUILT** | 计划书 §5.2 该行划了删除线；跟进单 §21 无行；主干归集 0 枚产物提交；计划书删除线行原文：\| ~~R39~~ \| **不建**，沿用 R17（裁定 5 = 甲） \| — \| — \| ／ §21 不建裁定原文：每单的**判据与禁改边界**以本节为准。**R39 不建，沿用 R17**（裁定=甲）。 | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R51 | PARTIAL | ② 加总误差 <1% 未量；rewrite/reflect 两格插桩后置 | **PARTIAL** | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 3 枚产物提交（最新 2477522·1 枚）；G-R51-1 纸面判语：量到了，三窗全 FAIL（RC=1）（docs/perf/r631-stage-sum-delta-2026-10-04.md）｜极性 MEASURED｜未过线枚数＝母集 105/105/106｜落盘凭据 d00b791 | `d00b791` · `docs/perf/r631-stage-sum-delta-2026-10-04.md` · G-R51-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |

第四格纠偏（派工词的前提不成立）：「机器尺把 R51 记成 LANDED 是假账」——上面第三列就是从基点尺子现取的，R51 改前已经是 `PARTIAL`。所以本单没改它的档，改的是理由句：从纸面派生（§4）。

## 3. 改前改后 43 行全表（D4）

列口径：「判定来源」＝尺子自己声明这一格是写死还是派生；「派生用了哪条事实」＝尺子 §3 派生台账的基准事实，其中『计划书 §5.2』＝`docs/handoff/2026-09-17-perf-architecture-plan.md`、『跟进单 §21』＝`docs/handoff/2026-09-15-backend-followup-requests.md`（这两枚本席只读未写）；「仓内凭据」＝尺子点名的 sha 与仓内路径（欠账格连出处路径一起给）。

| 号 | 改前档 | 改后档 | 判定来源 | 派生用了哪条事实 | 仓内凭据 |
|---|---|---|---|---|---|
| R25 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 b17b4dd·1 枚） | G-R25-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R26 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 4 枚产物提交（最新 6ee2f79·3 枚） | G-R26-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R27 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 4 枚产物提交（最新 6a4f02b·2 枚） | G-R27-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R28 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 1c0b08b·3 枚） | G-R28-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R29 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 791568c·4 枚） | G-R29-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R30 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 4 枚产物提交（最新 50aff1a·14 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R31 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 eef642b·4 枚） | G-R31-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R32 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 8a91f4e·4 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R33 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 3 枚产物提交（最新 9cdbef2·1 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R34 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 e4d0c1b·3 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R35 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 90d029f·6 枚） | G-R35-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R36 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 ac44d00·2 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R37 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 0c08209·4 枚） | G-R37-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R38 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 2e6abc6·5 枚） | G-R38-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R39 | ZERO | **NOTBUILT** ⬅ | 判定派生 | 计划书 §5.2 该行划了删除线；跟进单 §21 无行；主干归集 0 枚产物提交 | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R40 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 3 枚产物提交（最新 d824b10·1 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R41 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 571e0d6·2 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R42 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 89965d5·7 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R43 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 1 枚产物提交（最新 4586bb4·4 枚） | G-R43-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R44 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 3 枚产物提交（最新 564340e·4 枚） | G-R44-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R45 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 640ef08·2 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R46 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 1 枚产物提交（最新 245315b·16 枚） | G-R46-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R47 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 006c613·2 枚） | G-R47-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R48 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 0ad3d3e·8 枚） | G-R48-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R49 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 c26afda·6 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R50 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 94f7fa1·4 枚） | G-R50-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R51 | PARTIAL | **PARTIAL** | 判定写死＋理由派生 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 3 枚产物提交（最新 2477522·1 枚） | `d00b791` · `docs/perf/r631-stage-sum-delta-2026-10-04.md` · G-R51-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R52 | PARTIAL | **PARTIAL** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 判据表有它的行；主干归集 2 枚产物提交（最新 1b84fb2·2 枚） | G-R52-1→`docs/handoff/2026-09-15-backend-followup-requests.md` |
| R141 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 无行；主干归集 1 枚产物提交（最新 1cbd164·6 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R142 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 无行；主干归集 2 枚产物提交（最新 b58a5b9·5 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R143 | ZERO | **CLOSED** ⬅ | 判定派生 | 计划书 §5.2 表内有它的行；跟进单 §21 无行；主干归集 0 枚产物提交 | `4da0bad` · `docs/perf/r626-legacy-engine-silent-empty-recall-2026-10-04.md` · `scripts/r626_legacy_engine_silent_empty_probe.py` · `tests/test_r626_legacy_silent_empty_teeth.py` |
| R144 | ZERO | **FOREIGN** ⬅ | 判定派生 | 计划书无行；跟进单 §21 无行；主干归集 0 枚产物提交 | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R145 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 无行；主干归集 2 枚产物提交（最新 f747109·3 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R146 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书 §5.2 表内有它的行；跟进单 §21 无行；主干归集 3 枚产物提交（最新 143bac8·1 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R253 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 1 枚产物提交（最新 ea2a539·6 枚） | `d853153` · `8051897` |
| R254 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 2 枚产物提交（最新 c70548a·2 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R255 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 1 枚产物提交（最新 3bf271d·7 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R256 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 2 枚产物提交（最新 d853153·1 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R257 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 1 枚产物提交（最新 71aea57·5 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R258 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 0 枚产物提交 | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R259 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 1 枚产物提交（最新 67ea193·4 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R260 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 2 枚产物提交（最新 9dd6eba·1 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |
| R261 | LANDED | **LANDED** | 判定写死＋理由写死 | 计划书无行；跟进单 §21 无行；主干归集 1 枚产物提交（最新 c9ad493·1 枚） | `docs/handoff/2026-09-17-perf-architecture-plan.md`（出处见「事实」列） · `docs/handoff/2026-09-15-backend-followup-requests.md`（出处见「事实」列） |

- 移档只有三行（⬅：R39／R143／R144），其余 40 行改前改后同档——派生化没让任何一格变松或变严。
- 两态都 `RESULT=PASS`，在册 43 号逐条自证那条（C1–C18）一字没放宽；ZERO 从 3 枚降到 0 枚不是靠摘牙，是靠那三格各归其档。
- 抽验提示：本表 43 行由量具输出机械生成，本席没有对任何单号预写过结论；抽哪一枚都能顺着「仓内凭据」列回到尺子读数与本纸 §8 的命令。

## 4. 理由句前后（D3：跟纸面，不跟提交标题）

| 号 | 改前理由句（写死） | 改后理由句（派生） | 出处 |
|---|---|---|---|
| R51 | ② 加总误差 <1% 未量；rewrite/reflect 两格插桩后置 | 量到了，三窗全 FAIL（RC=1）（取证纸现取）｜未过线枚数＝母集 105/105/106｜凭据 d00b791 · docs/perf/r631-stage-sum-delta-2026-10-04.md | 取证纸 `docs/perf/r631-stage-sum-delta-2026-10-04.md`，落盘并树笔 `d00b791`（由尺子 `first_add()` 现取，不是手抄） |

订正一处派工词口径：取证纸现取的三窗母集枚数是 **105/105/106**，不是「105/105」（第三窗多一枚）；三窗全 FAIL、RC=1 的结论不变。尺子印的就是纸面切的 105/105/106。

## 5. 本席顶回／新查出的前提

1. 「机器尺把 R51 记成 LANDED」——**不成立**，基点尺子现取即 `PARTIAL`（§2 第三列原文）。本单据此只改理由句。
2. R51 母集枚数——纸面是 **105/105/106**，派工词写「105/105」少了第三窗那一枚；FAIL 结论不变。
3. 尺子字节数——派工词写 33,901 B；基点 blob `2103890:scripts/audit_plan_ticket_ledger.py` 实测 **33,265 B**（`git cat-file -s`），主树 HEAD 那枚同为 33,265 B。不影响判据，只记着免得拿错尺。
4. 样板笔 `48cc956`（R545 影子端三态）**不在本席基点的祖先链上**：`git merge-base --is-ancestor 48cc956 HEAD` 在 `be-r640` 里 rc=1（它在主树 HEAD 上 rc=0）。本席照的是它的思路，影子仓三态自己实现，测试源码里没有对它的硬编码引用。
5. **跑出来的第二处假账（原判据没写、本席补上）**：见 §6。

## 6. 新查出的病：正文转述被当成「认领」，新写的纸能顶掉量具的判语

两态亲跑第一次就炸出来了（D6 的价值正在于此）：

```powershell
# state②：基点分离树＋只投本单货
& C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py
```

```text
FAILED tests/test_r640_ledger_tiers_are_derived.py::test_only_one_paper_claims_the_r51_gap
同一格欠账被两枚纸认领＝得先定谁说话
2 = len({'docs/perf/r631-stage-sum-delta-2026-10-04.md', 'docs/testing/r640-ledger-derivation-2026-10-04.md'})
```

- 根因：`Deriver._paper_index()` 原本把**任何**提到 `G-<号>-<序>` 的行都当成认领。本纸在正文里转述了 `G-R51-1`（对照表必须引用欠账号），于是尺子把 R51 的理由句改从本纸读——量具那张纸的判语被一枚新写的纸顶掉。这是「写纸的人改写旧账」那一族假账，与本单治的病同源。
- 治法（只改尺，不改账）：认领只看**标题行**（`CLAIM_HEAD_RE`）；判语在认领那张纸里**倒扫全纸**取最后一条带极性的（纸内自己订正过的，取订正后那句）；同一格被两枚纸在标题里认领＝当场给 problem。报表头另加一枚转述计数，枚数以量具现取为准（见 §1 摘录），本纸不抄数字——抄了就成了又一处手抄账。
- 新牙：**C18**（同一格只许一枚纸认领；正文转述不算）＋ 写死理由句那族也管——认领了却没写判语的行，即使该格理由是写死的，C18 也红（不许沉默）。
- 反证刀 K7／K8／K9（每把先跑同机械正控）：K7 凭空添一枚只在正文转述的纸 → 这本账一字不动且转述被计入报表头；K8 凭空添一枚在标题认领同一格的纸 → C12 红并点名两枚纸；K9 凭空添一枚认领却没写判语的纸 → C18 红并点名该纸。三把都在影子层凭空添纸（`evidence_paths()` 可换、正文走覆盖视图），**盘上一个文件都不写**。

## 7. 两态亲跑与刀清单（D5／D6）

| 态 | 树 | 命令（原文） | 实取读数 |
|---|---|---|---|
| ① | `be-r640`（apply 未 commit） | `.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py` | 16 passed 枚 |
| ① | 同上 | `.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_counter_evidence_teeth.py` | 15 passed 枚 |
| ① | 同上（本纸定稿后合跑同名两件） | `.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py tests/test_r640_counter_evidence_teeth.py` | 31 passed 枚 |
| ② | `$env:TEMP\r640-state2`（`2103890` 分离树＋只投本单货四枚） | `C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py` | 16 passed 枚 |
| ② | 同上 | `C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_counter_evidence_teeth.py` | 15 passed 枚 |
| ② | 同上（本纸定稿后合跑同名两件） | `C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py tests/test_r640_counter_evidence_teeth.py` | 31 passed 枚 |

| 态 | 尺子读数 | 实取读数 |
|---|---|---|
| ① | `scripts\audit_plan_ticket_ledger.py` 输出 | 在册 43 号：LANDED=23 · PARTIAL=17 · CLOSED=1 · ZERO=0 · FOREIGN=1 · NOTBUILT=1 |
| ② | 同一枚尺在同一棵基点树＋只投本单货上跑 | 与 state① 逐字节相同（`git diff --no-index --quiet` rc=0），在册计数同上一行 |

两态同名件枚数相同（16／15，合跑 31）＝D6 达标；两态文件清单逐枚点名见本纸 §9。

刀清单（victim → 咬它的牙；每把都先用同一套机械跑正控，正控不绿就不算咬中）：

| 刀 | 摘什么 | 谁红 |
|---|---|---|
| K1 | 喂假 sha（`--fault R143=CLOSED@deadbeef`） | R143 → C2／C6／C17 红并点名 |
| K1b | 喂真但不在祖先链的 sha（`rev-list --all --not HEAD` 现取） | R143 → C3 红 |
| K2 | 摘掉跟进单 §21「R39 不建，沿用 R17」那句 | R39 变回它自己的判定（ZERO）并红 → C12 |
| K2b | 摘掉计划书那行的删除线（裁定句留着） | R39 → C12（缺另一条腿） |
| K3 | 把派生判定改回硬编码（CLOSED／FOREIGN／ZERO 三种写法） | C11 或 C13 红 |
| K4 | 把 R51 理由句改回写死的「未量」 | R51 → C14 红 |
| K5 | 把结案量具的取证纸假装从盘上拿走 | R143 → C12 红 |
| K6a | 把纸面判语翻成「量不到」 | 理由句跟着纸面改口，整本仍自证（翻面正控） |
| K6b | 把纸面判语翻成 PASS | R51 → C15 红 |
| K7 | 影子层凭空添一枚只在正文转述的纸 | 不许认领：判语与档位一字不动，转述进报表头计数 |
| K8 | 影子层凭空添一枚在标题认领同一格的纸 | R51 → C12 红并点名两枚纸 |
| K9 | 影子层凭空添一枚认领却没写判语的纸 | R25 → C18 红（理由句写死的格也不许沉默） |

摘刀、加豁免、`pytest.skip` 一律没有；常驻闸最后一枚断言影子没写回仓内、真仓读数仍原样自证。

## 8. 复现

```powershell
cd C:\Users\fengx\PycharmProjects\be-r640
& .\.venv\Scripts\python.exe scripts\audit_plan_ticket_ledger.py
git -C . worktree add --detach $env:TEMP\r640-state2 2103890
cd $env:TEMP\r640-state2
& C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe scripts\audit_plan_ticket_ledger.py
& C:\Users\fengx\PycharmProjects\be-r640\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py tests/test_r640_counter_evidence_teeth.py
```

六档口径、派生纪律与自检编号（C1–C18）以尺子自己的报告头为准，本纸不复制一份——复制了就会过期。

## 9. 两态文件清单（逐枚点名）

state①＝`C:\Users\fengx\PycharmProjects\be-r640`：
- `scripts/audit_plan_ticket_ledger.py`＝64286 B · 改（在册件，就地改）
- `docs/testing/r640-ledger-derivation-2026-10-04.md`＝22163 B · 新增（本纸）
- `tests/test_r640_counter_evidence_teeth.py`＝18629 B · 新增（反证刀）
- `tests/test_r640_ledger_tiers_are_derived.py`＝14441 B · 新增（常驻牙）

state②＝`%TEMP%\r640-state2`（基点 `2103890` ＋只投本单货）：
- `scripts/audit_plan_ticket_ledger.py`＝64286 B · 改（在册件，就地改）
- `docs/testing/r640-ledger-derivation-2026-10-04.md`＝30643 B · 新增（本纸）
- `tests/test_r640_counter_evidence_teeth.py`＝18629 B · 新增（反证刀）
- `tests/test_r640_ledger_tiers_are_derived.py`＝14441 B · 新增（常驻牙）

## 10. 未验事项

- 全量回归门 `python scripts/run_gate.py` 本席未跑（写域只碰尺子与新增件；门由总控并树后统一跑）。
- 计划书 §5.2 里 R143 那行仍写「待派」，尺子已在报表 §5 打上「🔴 账面滞后」——只报不改，改表归人。跟进单 §172 那句过期结论同样等人写段落笔订正。
- CLOSED 只证三件事：账面有结案裁定句、裁定句点名的量具的产物与取证纸都在仓内、结案笔在 HEAD 祖先链上。它不替业主重开裁定；尺子 §6 仍如实报 R143 名下自号产物提交 0 枚。
- 「同一格只许一枚纸认领」这条口径是按**今天只有一枚纸认领 `G-R51-1`** 落的；将来若真要两枚纸接力同一格，得先定「谁说话」的账面规矩，不是把这条牙放宽。

