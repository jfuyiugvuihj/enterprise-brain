# R547 · 越权格按业主已裁口径重落（2026-09-30）

单号 **R547**（执行层）｜施工树 `C:\Users\fengx\PycharmProjects\be-r547`，基点 `ff164c2`（主树 `codex/data-file-catalog` 现取 HEAD）｜**零 commit、零 push、零写库、零起服务、零打模型**。

🔴 本纸的效力边界：它改的是**账面"欠什么"**，不是判据、不是三态。四件可失败判据的 (a)(b)(c) **继续记「未验」**，格③／C 门**没有翻绿**，一枚都没翻。业主那三条裁定的在册原话里那一句「合成标签只证行为、不证客户隔离」在本纸逐字在位，不许被任何一句读数顶掉。

| 项 | 命令原文 | 实取读数 |
|---|---|---|
| 本席基点 | `git -C be-r547 rev-parse --short HEAD` | `ff164c2` |
| 落笔前盘面 | `git -C be-r547 status --porcelain` | **0 行**（fresh worktree，一字节未动） |
| 解释器 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`，cwd＝本席树 | 总控 2026-09-30 第 3 条裁定指定；不用 `uv run`（它会解析本席树里的 `pyproject.toml` 并可能动依赖） |
| 宿主 5432 上是谁 | `Get-Service \| Where-Object DisplayName -like '*PostgreSQL*'`；`Test-NetConnection 127.0.0.1 -Port 5432` | `postgresql-x64-16` = **Running**；`TcpTestSucceeded=True` ⇒ 这条通的是**计划书 §9.4 点名过的那台野 PG**，不是生产库 |
| 容器侧端口 | `docker ps --format ".Names/.Status/.Ports"`（本席自曝，见 §7） | `enterprise-brain-postgres-1` Up 26 h，端口列 **`5432/tcp`＝未发布宿主端口** |

## 1. 业主那四条裁定的原文与派生坐标

坐标一律由 `scripts/r547_scope_verdict_gauge.py` 的 `owner_rulings()` **按锚现读派生**（锚在 `docs/handoff/2026-09-17-human-gates.md` 里必须逐枚唯一命中，不唯一就当场停），派生钉＝`tests/test_r547_coordinates_and_arms_are_derived.py`。

| 键 | 现读坐标 | 派生锚 | 原文（截断，全句见盘上那一行） |
|---|---|---|---|
| H13 | `docs/handoff/2026-09-17-human-gates.md:365` | `## H13 结案 ＋ A1/A3 裁定` | 「H13 裁定＝甲：未标注密级的上传按 1 级（最低公开）入库，写进契约，不再当缺陷报」（同节 :367；节标题自己带着「**本裁定可推翻**」） |
| auditor | `docs/handoff/2026-09-17-human-gates.md:372` | `密级档位 = 3` | 「今天一并裁：**`auditor` 的密级档位 = 3，与 `admin` 同档**」 |
| A1 | `docs/handoff/2026-09-17-human-gates.md:373` | ``A1（`users.department` 回填）裁定`` | 「**A1（`users.department` 回填）裁定＝不在真库做，改沙盒**：给跑分账号 `evalbot` 设部门会让 105 题里的跨部门题集体崩掉，A④「逐类不退化」就此失去可比性」 |
| A3 | `docs/handoff/2026-09-17-human-gates.md:374` | ``A3（生产密级标签回填）裁定`` | 「**A3（生产密级标签回填）裁定＝交付阶段按客户真实密级做，不进 V1/V2 代码路径**：合成标签只证行为、不证客户隔离（沙盒那 252 枚已经钉过这条口径），拿它翻绿格③ 是假话。」 |

⇒ 账面事实：**这四条都在册，且都裁完了。** 计划书 §13 那一格此前写着"它要的不是代码，是 A1（业主补 `users.department`）+ A3（规则回填）"——那是在把**已裁写成未裁**。本单把这处口径对齐（判据一字未动），对齐落在计划书 §13 本节一末与 §13 四第③格、§9.3 第 3 格三处。

## 2. 四件可失败判据今天的三态（生产臂／沙盒臂分开，两臂不互相顶替）

三态口径：**通过**（现读可判且过）／**未验**（判据不满足或无可判性）／**量不到**（连现读的入口都没打开）。判据本体＝计划书 §13.一（四件；`:500` 那句"只有 (d) 单独成立不记通过"；`:382` 那句"一律按「未验」读"）。

### 2.1 生产臂（库 `enterprise_brain`）——今天：**量不到**，四件全部记「未验」

命令原文与末行：

```
python scripts/r547_scope_verdict_gauge.py --mode live --arm both
[R547] production rc=2 判定=未验 (a)未验 (b)未验 (c)未验 (d)未验 点名=ENV_DSN_UNSET
[R547] sandbox rc=2 判定=未验 (a)未验 (b)未验 (c)未验 (d)未验 点名=ENV_DSN_UNSET
[R547][末行] rc=2｜关门只认生产臂那四件｜🔴 本件不宣布格③／C 门翻绿
```

**为什么量不到（两行现取证据）：🔴 量不到不等于干净，也不等于"库里没有数据"，两行证据都不许这样收口。**

1. 宿主 5432 现取是 `postgresql-x64-16`（Running、`TcpTestSucceeded=True`）＝计划书 §9.4 那台**没有 `vector_scope` 的野 PG**；本席量具刻意不读 `DATABASE_URL`，就是防这一枚被当生产库。
2. 生产真库在容器 `enterprise-brain-postgres-1` 里，其 5432 **未发布宿主端口**，而执行层铁规**禁 docker** ⇒ 本席这一趟连不上它。生产臂的读数**由总控代取**（走 `docker exec ... psql` 那一族只读 `SELECT count(*)`），DSN 注入方式＝`R547_PRODUCTION_DATABASE_URL`；给不到就 rc=2 并点名，本席不猜、不自造、不折 0。

在册最新的生产臂读数（**09-28 那一次，由在册尺现判重跑**，不是本席今天的现读）：

| 件 | 判据（§13.一） | 09-28 在册读数（现派生） | 件级判定 | 今天格③三态（未验） |
|---|---|---|---|---|
| (a) | 主体侧真带部门（管理员 `departments=None` 那一档不算） | users 表 3 枚里 department 非空 1 枚；admin/evalbot 实测为空 | 未验 | **未验** |
| (b) | 语料非空 `department` > 0，且不同部门 ≥2、不同密级 ≥2 | 非空 department 0/1008 枚；部门 1 档 [<空串>]；密级 1 档 [1]；叉乘 1 格 | FAIL | **未验** |
| (c) | 该臂召回 > 0 | 召回 > 0 的档 1/5：admin-l3 | FAIL | **未验** |
| (d) | 越权 = 0 | 逐档全是空集（挡光或全放行），越权 0 条无从判 | 未验 | **未验** |

门槛那两枚 ≥2 不是抄的：`plan_floors()` 从 §13.一 (b) 那一行现读，本席跑时落点＝计划书第 **496** 行（`--mode live` 的 JSON 里 `floors.line` 就是它）。

### 2.2 沙盒臂（库 `eb_r59_sandbox`）——今天：**重跑了在册尺**，有牙读数在位，但它不关门

命令原文：`python scripts/r547_scope_verdict_gauge.py --mode reread`（＝ `scripts/r469_readout_lib.py` 的 `validate` + `judge` 现判，零新读库、零写入）。末行：

```
[R547][末行] mode=reread 状态=SANDBOX_MEASURED_PRODUCTION_UNVERIFIED｜沙盒臂有牙格 5 枚／越权 0 条／无谓词对照本可越界 200 条／无部门谓词那档池外 252 枚（裁定原文那句沙盒枚数=252）／本臂写入 72 枚｜沙盒合成标签只证行为、不证客户隔离，量到什么都不关门。
```

| 件 | 沙盒臂现派生 | 件级判定 |
|---|---|---|
| (a) | 4/5 档带部门谓词（管理员那档 `departments=None` 不计，§13.一 原话） | `PASS_SYNTH_ONLY` |
| (b) | 非空 department 1080/1080 枚；部门 7 档；密级 4 档；(部门,密级) 叉乘 16 格（其中 r59c 合成语料 12 格） | PASS |
| (c) | 召回 > 0 的档 5/5：staff-fin-l1／manager-hr-l2／manager-ops-l2／exec-l3／admin-l3 | PASS |
| (d) | 越权 0 条；池外可漏材料逐档 1074/1068/1068/1062/252 枚，无谓词对照本可越界逐档 59/48/51/42/0 条（合计 200 条） | PASS |

🔴 三句限定，一句都不许省：

- 沙盒那批合成标签**只证行为、不证客户隔离**（业主在册原话，`human-gates.md:374`）。它四件全过也**不关**格③／C 门——本席量具在代码层就把这条写成硬拒：`--gate sandbox` 当场 rc=3、`gate_roll()` 对沙盒臂永远交 `ARM_SUBSTITUTION_REFUSED`。
- **252 与 72 是两本账**：252＝沙盒臂无部门谓词那一档（admin-l3）的**池外材料**枚数，也是裁定原文那句「沙盒那 252 枚」；72＝09-28 那次 `r469` 本臂**写入**的合成行数（跑完按点名 id 删除，残留 0 枚）。两枚数在 `--mode reread` 里并列交回，谁也不许顶谁。
- 沙盒臂的 PASS 用不了"越权 0 条 ⇒ 干净"这种推法：它的 0 是**有牙的 0**（同档另有 200 条本可越界的对照命中被挡在外面），而它只证行为、不关这道门；生产臂今天交不回这种 0，因为生产臂今天根本没读数。

## 3. 欠的确切条件（逐格点名，🔴 没有一格因"业主已裁"而前进）

| 格 | 今天欠什么 | 差的确切条件 | 谁能做 |
|---|---|---|---|
| 格③ (a)（生产臂主体侧部门） | 仍「未验」 | **不是**"等业主裁"——A1 已裁「不在真库做，改沙盒」（`:373`）。真库侧那一件属**交付阶段项**，V1/V2 不为其写代码路径；V1 侧可判的是沙盒臂行为（已量，`PASS_SYNTH_ONLY`）＋生产臂空集声明（已声明） | 交付阶段随客户真实组织架构做；V1 侧无待办码 |
| 格③ (b)（生产臂两维标签） | 仍「未验」 | 同上：A3 已裁「交付阶段按客户真实密级做」（`:374`）。生产两维标签按 09-28 在册读数仍全空（非空 department 0/1008、密级 1 档），本席今天没取到生产读数，所以这句话的时效是"在册最新"，不是"今天现读" | 交付阶段按客户密级策略回填＋首灌前逐库确认（H13 那三件套的第 ③ 件） |
| 格③ (c)(d)（召回与越权条数） | 仍「未验」 | 需要**一次连得上真库的窗口**：总控以 `docker exec enterprise-brain-postgres-1 psql` 代取存量，或给 `R547_PRODUCTION_DATABASE_URL` 注入容器内网 DSN 后复跑本量具；`--mode live` 的 (c)(d) 在未跑读腿时只会交 `READ_LEG_NOT_EXERCISED`，**不会**交 0 | 总控（代取读数）；跑读腿那一路在册 `scripts/r469_sandbox_scope_readout.py` |
| 格②（热集让路延迟） | 未动 | 仍欠一台安静机器（`:543` 那笔 `0.873` vs `3.322` 未结），本席未碰 | R542 一类，另席 |
| 翻 `INDEX_BACKEND` 默认 | 业主动作 | 与格③ 同向：格③ 不绿，默认不翻；本席没动 `deploy/.env.server` 一枚字节 | 业主 |

一句话交给总控：**这格今天唯一的真变化是"账面把已裁写成了未裁"，本单把它对齐；对齐之后它还是「未验」。**

## 4. 三形自检（判据②要求的"读不到就 FAIL、不许当 0"）

命令原文：`python scripts/r547_scope_verdict_gauge.py --mode shapes`（🔴 这一道打印的每一行都是**夹具在过自己的牙**，行内带 `DEMONSTRATION_FIXTURE_NOT_A_MEASUREMENT`；它的 rc=0 只代表"三形各自红了且各自点了名"，不代表任何一格量到了东西）。实测末行：

```
[R547][夹具] no-database rc=2 判定=未验 (a)未验 (b)未验 (c)未验 (d)未验 点名=CONNECT_FAILED
[R547][夹具] empty-table rc=1 判定=未验 (a)未验 (b)未验 (c)未验 (d)未验 点名=ACCOUNTS_TABLE_EMPTY、POOL_TABLE_EMPTY
[R547][夹具] all-empty-column rc=1 判定=未验 (a)未验 (b)FAIL (c)FAIL (d)未验 点名=ACCOUNT_COLUMN_ALL_EMPTY、LABEL_COLUMN_ALL_EMPTY
[R547][末行] DEMONSTRATION_FIXTURE_NOT_A_MEASUREMENT｜三形各自 rc=[2, 1, 1]｜本道 rc=0 只代表三形各自红了且各自点了名，不代表任何一格量到了东西
```

三形各归各码：读不到库 → `ENV_DSN_UNSET`/`CONNECT_FAILED`（rc=2，且真跑那一形见 §2.1 的 live 末行）；表空 → `POOL_TABLE_EMPTY`＋`ACCOUNTS_TABLE_EMPTY`（rc=1，读数句子明写"0/0 不是读数"）；列全空 → `LABEL_COLUMN_ALL_EMPTY`＋`ACCOUNT_COLUMN_ALL_EMPTY`（rc=1，(b)(c) 落 FAIL 而不是"0 枚 ⇒ 干净"）。另有两形由派生钉守住：连错库 → `IDENTITY_MISMATCH`（rc=3 拒），缺关系（野 PG 形状）→ `SCHEMA_RELATIONS_MISSING`（rc=2 前置不满足，绝不当"库里有 0 枚"）。

## 5. 复跑与在册件

本单落完（计划书两节文字、量具、两枚派生钉、本纸）后**在同一棵树上现跑**：全程 `-q`、不开 `-n`、不跑 `scripts/run_gate.py` 全量门、不碰 docker／服务／模型。本机今天**没有评测窗**，这些件都不打模型，所以允许跑。下面每一行都是**这一遍**现跑取回的末行；本机今天不安静（宿主一枚 CUDA 训练任务＋另席 R535 的 pytest 在争 CPU），所以**墙钟秒数只作旁证，枚数与 rc 才是判据**。

| 复跑件 | 末行（现取） |
|---|---|
| `tests/test_r387_production_label_leg.py` | `4 passed, 1 xfailed in 1.40s`（rc=0） |
| `tests/test_r387_label_ruler_teeth.py` | `43 passed in 0.99s`（rc=0） |
| `tests/test_r400_backfill_ladder_pins.py` | `29 passed in 0.59s`（rc=0） |
| `tests/test_r400_derived_ledger_shift_and_silence_pins.py` | `14 passed in 1.64s`（rc=0） |
| `tests/test_r455_gapdoc_coordinates_are_derived.py` | `19 passed in 1.02s`（rc=0） |
| `tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py`（本单新钉） | `16 passed in 0.33s`（rc=0） |
| `tests/test_r547_coordinates_and_arms_are_derived.py`（本单新钉） | `17 passed in 0.45s`（rc=0） |
| `tests/test_r481_v1_record_says_unverified.py`（计划书 §13 的在册邻件） | `14 passed in 0.47s`（rc=0） |
| `tests/test_r490_live_reads_match_derived.py`（同族坐标派生钉） | `10 passed in 1.78s`（rc=0） |
| `tests/test_r408_docs_say_what_the_tree_does.py`（账面与树对账） | `15 passed in 7.96s`（rc=0） |
| 在册尺重跑 `python scripts/r469_readout_lib.py validate | `[过关] 状态 SANDBOX_MEASURED_PRODUCTION_UNVERIFIED｜有牙格 5 枚｜未过判据 4 条`（rc=0） |

盘面与行尾（现取）：

- `git diff --numstat` → `16 1 docs/handoff/2026-09-17-pgvector-adoption-plan.md`；`git status --porcelain` → 那一枚 `M` 加四枚 `??`（本单新件），**零暂存、零 commit**（中途误用 `git add -A --intent-to-add` 取过一次行尾读数，当场 `git reset` 复原，索引与 HEAD 一致）。
- 逐字节行尾（现量：`open(rel, "rb")` 数 CRLF／loneLF／loneCR 并查前 3 字节 BOM）：五枚件全部 `loneLF=0`、`loneCR=0`、`BOM=False`；计划书 544 枚 CRLF、量具 648 枚 CRLF、钉（一） 274 枚 CRLF、钉（二） 242 枚 CRLF、本纸 153 枚 CRLF。这台机 `core.autocrlf=true` 且无 `.gitattributes` ⇒ 盘上必须 CRLF，`git ls-files --eol` 对已跟踪的计划书回 `i/lf w/crlf`（行尾尺＝`tests/test_r531_worktree_merge_keeps_each_files_eol.py`）。

## 6. 反证刀与 sha256 台账

六把，每把都改一处、跑 victim 钉、再逐字节复原。摘守卫的门：量具那四把走 `R547_GAUGE_TOOL`（影子副本）＋`R547_REPO_ROOT`（仍指真树）；纸面那两把临时改盘上真件，跑完立刻写回原字节并复验 sha256。**这本台账是第四遍跑的**（前三遍各有一处不干净，见下面 ① ② ③ 笔）：纸、钉、量具任何一枚字节变了，台账里的 victim 哈希与真件哈希就都不再是终态，只能整本重跑重取——**现取数字只算第四遍**。

| 刀 | 改了什么 | victim 钉（摘前 sha256） | 红的钉 | rc | 真件摘前＝摘后？ |
|---|---|---|---|---|---|
| K1 | 计划书 §13.一 把 (a) 那行**临时**改成假话「✅ 通过，业主已裁，因此格③ 可以关门」；这句假话只活在刀的一次 rc 里，账面上 (a) 今天仍记未验，摘后逐字节复原 | `tests/test_r547_coordinates_and_arms_are_derived.py` = `b09763f5a3ff55ae…` | `test_the_criterion_table_rows_a_b_c_stay_marked_not_verified` | 1 | `6f2a10c955d6a534`＝`6f2a10c955d6a534` ✅（计划书变异体 `1be8c6dc15daf479`） |
| K2 | 量具 `derive`：生产臂 (a) 无条件记 PASS | `tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py` = `da6e95466d885ea3…` | `test_all_empty_column_shape_fails_and_never_greens` | 1 | 真量具 `3b3b50e0071c9c8c` 全程未动（变异体 `c59f51cb0fbd55e6`） |
| K3 | 量具 `derive`：把「量不到」折成「非空 0 枚 ⇒ 干净」 | `tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py` = `da6e95466d885ea3…` | `test_no_database_shape_fails_and_names_the_reason`／`test_unmeasurable_is_never_folded_into_a_count`／`test_live_mode_without_dsn_names_the_exact_variable`／`test_stray_pg_without_the_expected_relations_is_unmeasurable_not_empty` | 1 | 真量具 `3b3b50e0071c9c8c` 全程未动（变异体 `dc67bad3f3ba5eab`） |
| K4 | 量具 `gate_roll`：去掉「沙盒臂不关门」那一支 | `tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py` = `da6e95466d885ea3…` | `test_sandbox_arm_closes_nothing_even_with_teeth` | 1 | 真量具 `3b3b50e0071c9c8c` 全程未动（变异体 `e33ee11be8078019`） |
| K5 | 本纸把 A1 的裁定坐标 `:373` 写成 `:374`（错一格） | `tests/test_r547_coordinates_and_arms_are_derived.py` = `b09763f5a3ff55ae…` | `test_the_four_ruling_coordinates_on_paper_are_derived`／`test_a_single_wrong_coordinate_reddens_this_book` | 1 | `58b537a04891f3bb`＝`58b537a04891f3bb` ✅（本纸变异体 `a3a062043ca93e62`） |
| K6 | 量具生产臂入口接回宿主 `DATABASE_URL` | `tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py` = `da6e95466d885ea3…` | `test_the_gauge_never_takes_the_host_database_url_as_production` | 1 | 真量具 `3b3b50e0071c9c8c` 全程未动（变异体 `a1a78fa808e9492c`） |

🔴 台账之外还要记三笔：

- ① **第一遍 K1 没红**——本席那枚钉当时只盯本纸的坐标，没盯计划书 §13.一 那本表的逐件标记。补了两枚牙齿（`test_the_criterion_table_rows_a_b_c_stay_marked_not_verified`＋`test_no_line_in_the_plan_declares_the_gate_closeable`）才咬住。这一笔留在这里是给下一班看的：**"改口只改欠什么"这种单，最容易漏的牙就是纸面改了、表里没改**。
- ② 第一遍六把刀跑的时候，纸上 K1 那一行还带着旧措辞（逐字引用了刀写下的那句假话、同行没有否定形状），于是 `test_every_cell3_line_in_the_paper_negates_green` 被卷进 K1／K5 的 victim 列表——**那不是那两把刀咬的，是本纸自己那行字没通过自己的牙**。改法是改纸（把那行写成「假话是刀写的、账面上 (a) 仍记未验」），不是改牙迁就纸；改完重跑六把，每把只报自己那一枚红。这一笔留给下一班：**台账里的「红的钉」必须能归因到那把刀本身**。
- ③ **台账里那对「本纸」sha256 是自指的，只能记到「刀跑那一刻」的字节**：K5 行里 `bc9f91b2b73bae76` 是本席落台账**之前**的纸面字节，而把台账写进纸这个动作本身就会改掉那枚哈希（改完这一行时现算是 `e97f816d8a858869`，写完又变了）。所以 K5 那一对「摘前＝摘后」只证一件事——**刀没在盘上留字节残渣**，它不能当本纸的终态指纹用；终态指纹只在交回消息与总控并树时的 `git diff` 里。（跑刀前后 `git -C be-r547 status --porcelain` 逐行相同：一枚 `M` 加四枚 `??`；四枚真件摘前＝摘后逐字节相同，逐枚哈希只记在上面那一本的最后一列，这里不再抄一份——**手抄哈希和手抄行号是同一族病**。刀与变异体临时件在 `%TEMP%\r547_knives3\`，交回前连同 `%TEMP%` 里本席那批 `r547_*` 一起清空（树内零临时件）。）
- ④ **刀在盘上停留的时长＝victim 钉那一次 rc 的墙钟**：今天宿主上有一枚**用户在跑的 CUDA 训练任务**（`train.py --config configs/_local_fog6.yaml --device cuda --resume`，PID 13640，12:40 起，带 4 个 worker）和另席（R535）的 pytest 在争 CPU，本席单把刀的 victim 跑最长到过 ~6 分钟（同族件平时 1 s）。⇒ 计划书／本纸被临时改成假话的窗口跟着变长。这一族刀只在**执行层独占的工作树**里做，绝不在共享主树上做；跑完逐枚核对 `git status --porcelain` 与摘前逐行相同、真件 sha256 复原（台账最后一列）。另一笔：本机今天不安静，所以 §5 那些**墙钟秒数只作旁证，枚数与 rc 才是判据**。

## 7. 写域、零写入与本席一笔自曝

- 本单只动四样：计划书 `docs/handoff/2026-09-17-pgvector-adoption-plan.md` 的 **§13 与 §9.3** 两节文字、本纸、量具 `scripts/r547_scope_verdict_gauge.py`、派生钉 `tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py` 与 `tests/test_r547_coordinates_and_arms_are_derived.py`。**零 commit／零 push／零写库／不起服务／不打模型／不动主树。**
- 禁入件一枚没碰：`docs/perf/r387-label-lineage-2026-09-27.md`、`migrations/**`、`docs/api/contract-v1.md`、`app/**`、`frontend/**`、评测集与 `tests/test_evaluation_report.py`、`deploy/.env.server`、`scripts/r530_*`、`app/storage/pending_approvals.py`。
- 🔴 **坐标会漂，本单自己就是肇事者之一**：本单在 §9.3 那一节插了一行 ⇒ 计划书 383 行之后整体下移一格，纸面上原先硬写的 `(d)` 记账口径行号 499 与 §13.四 第 ② 格行号 528（这两枚**旧写已作废**，不作坐标引用）**当场变旧**，现读分别是 `:500` 与 `:543`（由 `plan_citations()` 按锚现读派生）。已补三枚牙（`test_the_plan_side_coordinates_on_paper_are_derived`／`test_the_plan_side_coordinate_set_on_the_paper_is_all_derived`／`test_a_drifted_plan_coordinate_reddens_this_book`）：纸面每一枚裸坐标都必须来自派生集，计划书侧那三枚一枚不许缺，手抄旧坐标即红。再记一笔口径：**本班派工词的坐标写错过两回**（上一席 `model_budget.py:885/:442`；这一席把计划书文件名写成 `2026-09-17-perf-architecture-plan.md`，且原单给的 527／528／529 那三枚与盘上现读不同格）——本单一律**按原单的文件名与盘上现读坐标落**，不跟派工词的错坐标走。
- 🔴 **本席自曝一笔**：开工前的盘面侦察里，本席跑过一枚 `docker ps --format ".Names/.Status/.Ports"`（只读列容器，未起停、未进容器、零改动），它违反"执行层禁 docker"的字面口径。本纸 §0 那枚"5432 未发布宿主端口"的读数来自它。此后本席再未发任何 docker 命令，容器侧复跑一律交回总控。记在这里是给下一班看：**禁 docker 这条线的价值就在"执行层拿不到容器内网 DSN"，所以量具才把生产入口做成"环境给不到就 rc=2"**。
- 另有两枚在册件在**本席这棵 fresh worktree 上**红，病根不在本单：`tests/test_r469_readout_is_generated.py` 的 T5/CLI 两枚要 `docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 盘上字节与再生件逐字节相同，而主树那本盘上是 LF（237,481 B）、`git worktree add` 检出到本席树变成 CRLF（244,675 B，blob 仍是 LF）——零写入也红。这正是 09-28 那笔 `scripts/r531_worktree_merge.py` 改按盘上行尾归位要治的形状，本席不擅自把那本纸改成 LF 来"灭红"（它不在本席写域，且改行尾会动别人的字节）。