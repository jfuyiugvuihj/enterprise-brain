# R596｜出厂 CLI 必须成对带走 globals，镜像必须自带 PG16 客户端工具

- 单号 R596 · 执行层名号**未随派工词交下来**（本纸不编名号，交回时一并报这一格）· 日期 2026-10-03 · 工作树 `be-r596` · 基点 `03507f3`（建树 dirty=0）
- 写域：`scripts/backup_database.py`、`scripts/restore_database.py`、`Dockerfile`、`tests/test_r596_*.py`、本纸。
- 交付：改三枚在册件、新增三枚常驻钉（34 枚牙）、本纸。**零 commit / 零 push / 零建分支；主树 `企业智脑` 一字未动**（只读过 `deploy/.env.server` 与两枚在册文档）。

## 0. E 门口径（判据⑤，从今天起写死）

> **备份恢复这一格五件缺一即红：① 数据逐枚同数；② globals 与归档成对取下来（`<归档名>.globals.json`
> + `<归档名>.globals.sql`，同目录同前缀，带归档自己的 sha256）；③ 恢复工序在 `pg_restore` 之后、
> 任何对账之前把它施加到恢复库；④ 对账把 globals 逐枚等值纳进门控（`globals_profile` /
> `globals_session` 进门控，`globals_deferred` / `cluster_roles` 只上报绝不当对账项）；⑤ 跑这两枚
> CLI 的镜像自带 `psql` / `pg_dump` / `pg_restore` / `pg_dumpall` 四枚工具。任何一件不成立，
> "备份恢复演练通过"就是假绿。**

为什么这一句要写死：`pg_dump` 按构造不把 `pg_db_role_setting` 写进归档目录（那是 `pg_dumpall` 的活），
所以"整库 dump + 数据指纹全等"天然证不了恢复库还声明着同一套向量档。`app/db/migrations.py:57-58`
定义、`:82-83` 会话现读的正是 `app.embedding_dimension` / `app.embedding_model` 这两枚，
`app/rag/pg_store.py` 的读腿吃它们——它们 MISSING 时向量一枚不少、备份日志全绿、维度是错的。

## 1. R587 交的那一半与 R596 交的那一半（逐格点名，不抢功也不重做）

🔴 **先纠一处派工前提**：派工写「R587 的 `collect_globals()`/`apply_globals()` 已随 R593/R582 落账」。
本席在本基点现取：`git show 03507f3:scripts/r575_vector_restore_drill.py` 里 `collect_globals`
命中 **0**，`RECON_ITEMS` 仍是 **12 枚**（没有 `globals_profile`/`globals_session`），`EXTRA_ITEMS`
仍是旧的 `("db_local_settings", "local_embedding_gucs", "cluster_roles")`；`rg collect_globals` 在本树
（除本席新写的件以外）零命中。R587 的成品今天躺在 **`be-r587` 的未提交脏态**里（HEAD `6fcea4f`；
`M scripts/r575_vector_restore_drill.py`、`M tests/test_r575_vector_restore_drill.py`、
`?? tests/test_r587_globals_pair_gates_the_e_gate.py`、`?? docs/testing/r587-globals-pair-in-the-e-gate-2026-10-03.md`）。
⇒ 本单**没继承到它的码**，只对齐它的**接口形状**（下表右列逐枚按 `be-r587` 现读取名，本席一字未改它的写域）。
两本账并树之后必须合成一处导入，见 §9 第 8 格。

| 格 | R587 已交的一半 | R596 新交的一半 |
|----|---|---|
| 落点 | 只在**演练件** `scripts/r575_vector_restore_drill.py` 里 | **两枚出厂 CLI**：`scripts/backup_database.py`、`scripts/restore_database.py`，出厂路径默认就带 |
| 通道 | 容器内 `docker exec ... psql`（容器内 unix socket trust，不读口令） | `psql` 直连 `DATABASE_URL`（口令只在 `PGPASSWORD` env 里，不进 argv），`--psql` 可指路径 |
| 成对产物 | `*.globals.json` / `*.globals.sql`，`kind="r587-database-globals"` | 同一枚 kind、同一对后缀、同一套七列；`globals_paths_for()` 只从归档名派生 |
| 施加件不带库名 | `format('ALTER DATABASE %I SET ...', current_database(), ...)` + `\gexec` | 逐字同一形状；另加 `_APPLY_SHAPES` 两条正则：正文出现写死库名当场 REFUSE |
| 对账口径 | `RECON_ITEMS` 12→14 新增 `globals_profile`/`globals_session`；`EXTRA_ITEMS=("globals_deferred","cluster_roles")` | CLI 侧同名册同序（`restore_database.py:169` / `:173`），逐枚点名文案同族 |
| 真库那半 | 一次性演练库 `eb_r575_drill` 上的真 dump/restore/apply 读数 | **未做**（本单不许动容器、不许建库；见 §9 第 1-3 格） |
| 镜像带工具 | 只交出"四枚全 MISSING"这一枚事实 | `Dockerfile:88-99` 装 PGDG `postgresql-client-16` + 一枚只读文本的常驻静态钉（7 枚牙） |
| 反证 | 它自己那批 | 三把，逐枚给摘前/摘后/还原三枚 sha12，见 §5 |

**没有重复实现**：本单不碰 `scripts/r575_vector_restore_drill.py` 与 `tests/test_r575_*`／`test_r587_*`，
不碰 `migrations/**`（D8/D9 在窗口之后）、`chroma_db/**`、`.gitignore`、`deploy/.env.server`、
两枚评测集、`frontend/**`。globals 那枚目录查询在全树只有一份实现（钉在 §3 最后一条）。

## 2. 判据①：成对取与施加

- **备份侧**（`scripts/backup_database.py:145` `pair_globals_with_backup()`，挂在 `main()` 的 `:199-214`）：
  默认就写，不留 `--allow-*` 逃生门。账本从恢复侧取（`_globals_book()` 在 `:129`，包内导入优先，
  `python scripts/backup_database.py` 直跑退回同目录导入——牙
  `test_the_cli_can_import_the_book_when_run_as_a_file`）。交回 `globals=` / `globals_sql=` /
  `globals_pair=<json12>/<sql12> archive=<归档12>` / `globals_applied=` / `globals_profile=` / `globals_session=`。
- **恢复侧**（`scripts/restore_database.py:658` `restore_backup_with_globals()`）顺序写死：
  `read_globals_pair` →（`pg_restore`）`restore_database` → `apply_globals`（`:564`）→ `reconcile_globals`（`:625`）。
  成对产物**先读再进库**：没有配对 globals 的归档不该把恢复跑到一半才报出来；`--list` 那条只读目录的
  路径本来就不进库，保持原样。
- **施加件正文不带库名**：`DATABASE_APPLY_LINE` / `ROLE_APPLY_LINE`（`:139-146`）只用
  `format(... current_database() ...)`，Python 一头从不拼库名；`_APPLY_SHAPES`（`:149`）按形状白名单
  逐枚复核。四处不成对各拦一枚 REFUSE（`:482` `read_globals_pair`）：产物缺失 / `kind` 不对 /
  与归档 sha 不成对 / `.globals.sql` 正文与按 rows 现算的语句逐字节不等。
- **拒收空账**：源库里必读 setting 有一枚 MISSING 就拒（`collect_globals:420` → `required_global_settings():211`
  从 `app.db.migrations` 现取名字，件里不抄第二份）。
- **rc 契约**：`0` 成对且逐枚等／`1` 跑失败／`2` REFUSE（成对产物缺失、不成对、`psql` 不在镜像）／
  `3` 对账不等（逐枚点名到人话）。`_run_psql:352` 把 `FileNotFoundError` 翻成一句可执行的判据③文案，
  不留没法查的栈。
- **成对产物一律 LF 落盘**（`_write_text:477`）：同一份内容在 Windows 与容器里要交回同一枚 sha256，
  否则"与归档配对"那道闸会被行尾差异自己拧红。

## 3. 判据②：对账把 globals 逐枚等值纳入

- `RECON_ITEMS = ("globals_profile", "globals_session")`（`:169`）与 R587 那本账新增的两格**同名同序**；
  `EXTRA_ITEMS = ("globals_deferred", "cluster_roles")`（`:173`）照实上报、绝不当对账项
  （`ALTER ROLE ... SET` 会改整台实例；单库恢复既不建也不删角色）。牙
  `test_deferred_and_cluster_roles_are_reported_and_never_gated`、
  `test_the_reconcile_hands_back_both_gated_items_with_both_sides_of_every_number`。
- 改一枚值必须点名，两侧读数都上纸：
  `globals_session[app.embedding_dimension]: 生产='768' 恢复='1536'`（派工给的人话样例逐字可达，牙
  `test_one_changed_value_is_named_item_by_item_in_plain_language`）；少一枚 →
  `globals_profile[database|(all)|app.embedding_dimension]: 备份里有、恢复库没有（施加那一步没落地）`；
  两侧都 MISSING 也算红；源库本来没声明也算红（配不出可信施加件）。
- 钥匙不带库名：`globals_profile_key()`（`:232`）= `scope|role|name`。恢复库本来就叫别的名字，
  带上库名两侧永远不等（那是老口径的死因）。
- 一本账不许两处取（R393/R592 同族病）：
  `test_only_one_query_reads_pg_db_role_setting_across_the_two_clis` 用 AST 只收"真发出去的语句"，
  钉那枚目录查询在恢复侧恰好一份、在备份侧零份；
  `test_the_reconcile_reads_with_the_same_collector_as_the_backup` 钉对账必须走 `collect_globals`
  加两枚共享 builder，不许自己再拼一遍 `";; "`；
  `test_the_pair_readers_do_not_reformat_the_seven_columns` 钉 profile builder 只有三枚。

## 4. 判据③：镜像带那四枚工具（可静态证明，不把演练当性质）

- `Dockerfile:88-99` 新增一层：两枚 `ARG`（`PGDG_MIRROR` / `PGDG_KEY_URL`）+ 一次
  `apt-get install --no-install-recommends postgresql-client-16`，PGDG 源走 `signed-by` 验签、
  codename 由 `/etc/os-release` 现取不写死；取件用镜像里已有的 python `urllib`，不引入第二枚下载器。
  层位放在 `uv sync` 之下：不动依赖层，只在其上多两枚小层。
- 大版本对得上（本席现取）：`SELECT version()` → `PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)`，rc=0。
  Debian 12 自带源只有 `postgresql-client-15`，而 `pg_dump` 比服务端老会当场中止，所以必须走 PGDG 取 16；
  "客户端大版本 == 服务端大版本"这枚判断由钉从 `docker-compose.yml:48` 的
  `image: pgvector/pgvector:pg16` 现取 tag 推出，不写死数字。
- 常驻钉 `tests/test_r596_image_carries_the_pg16_tools.py`（7 枚，**只读 `Dockerfile` 与
  `docker-compose.yml` 文本，一次容器都不碰**）：装了带大版本的 postgresql-client／大版本等于服务端
  实际那枚／没有第二枚大版本混进来／包交的四枚工具名逐枚在册／`ENV PATH` 仍覆盖 `/usr/bin`／
  PGDG 源验签且 codename 派生／egress 只在两枚命名 ARG 后面。
- 🔴 明写不做的事：**没有**任何一枚钉把"容器里 `command -v` 跑得通"写成常驻判据。那是一次演练的读数，
  R593 刚治过同族病（把此刻读数当不变量）。容器现读只出现在 §6 的一手凭据里，不当牙。

## 5. 判据④：反证三把（sha256 前 12 位，全部在终盘上跑）

终盘基线：三枚新钉合跑 `34 passed`，rc=0。

| 把 | 摘什么 | 摘前 | 摘后 | 还原 | 逐字节全等 | 读数 |
|---|---|---|---|---|---|---|
| K1 | `scripts/restore_database.py:674` `applied = apply_globals(...)` 那一行 | `62d20c96e7cb` | `183266eeb544` | `62d20c96e7cb` | True | rc=1，**7 failed** / 27 passed |
| K2 | `scripts/backup_database.py:199-214` 备份侧采集那整步 | `14eae2a1bcf1` | `761df4c60809` | `14eae2a1bcf1` | True | rc=1，**4 failed** / 30 passed |
| K3 | `Dockerfile:99` `apt-get install ... postgresql-client-16;` 那一行 | `86847f2167a9` | `216d6d12f31a` | `86847f2167a9` | True | rc=1，**3 failed** / 31 passed |

- **K1 红在顺序与 MISSING 两面**（正是判据要的那两面）：工序钉交回
  `AssertionError: apply_globals 不在恢复工序里：那一格没人做了`；对账钉交回
  `globals_session: 备份='app.embedding_dimension=768 ;; app.embedding_model=nomic-embed-text'
  恢复库='app.embedding_dimension=MISSING ;; app.embedding_model=MISSING'`。红名册 7 枚：
  `test_the_cli_applies_the_pair_after_pg_restore_and_before_any_reconcile`／
  `test_the_order_is_also_pinned_in_the_function_body`／
  `test_one_changed_value_is_named_item_by_item_in_plain_language`／
  `test_deferred_and_cluster_roles_are_reported_and_never_gated`／
  `test_the_reconcile_hands_back_both_gated_items_with_both_sides_of_every_number`／
  `test_the_two_shipped_clis_finish_the_job_when_chained`／
  `test_the_cli_prints_the_reconciled_items_only_on_a_clean_reconcile`。
- **K2 红在成对产物缺失**：链式件交回
  `database restore refused: 备份没有成对的 globals 产物（判据①）：<...>.chained.globals.json、
  <...>.chained.globals.sql——少了它，恢复库的 app.embedding_dimension/app.embedding_model 就是
  MISSING，备份日志再绿也是假绿`；另三枚红在 `is_file()` 为假与两枚 REFUSE 语义。红名册 4 枚：
  `test_the_backup_cli_writes_the_pair_by_default`／
  `test_the_backup_cli_refuses_loudly_when_psql_is_not_in_the_image`／
  `test_the_backup_cli_refuses_an_unreadable_source_instead_of_shipping_an_empty_pair`／链式那一枚。
  ⚠️ 施工笔记（下一班别再踩）：本把第一版只摘 `pair = pair_globals_with_backup(...)` 那一行，
  交回的是 `IndentationError` + pytest **rc=2 集合期中断**（`2 errors during collection`）——那证明的是
  "文件被摘坏"，不是判据。摘坏文件不算反证，故改成摘整步。
- **K3 只红在镜像那族，没红在别人身上**：红名册正好 3 枚，全在
  `tests/test_r596_image_carries_the_pg16_tools.py`
  （`test_the_image_installs_a_version_pinned_postgresql_client`／
  `test_the_client_major_equals_the_postgres_the_stack_actually_runs`／
  `test_no_second_postgresql_client_major_is_pulled_in`），读数
  `assert 'postgresql-client-16' in ['build-essential', 'git', 'tzdata', 'fonts-wqy-microhei', ...]`；
  另两枚 CLI 的 31 枚牙全绿。
- 三把跑完盘面逐字节还原：`git diff --numstat HEAD` 与跑前一致（`35 0 Dockerfile`／`62 1 scripts/backup_database.py`／`621 2 scripts/restore_database.py`），`git status --porcelain` 只有本单七枚（三改 + 四未跟踪，含本纸）。

## 6. 一手凭据（本席现取，全部只读）

| 事实 | 读数 | 命令 |
|---|---|---|
| 服务端大版本 | `PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)`，rc=0 | `docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -c "SELECT version()"` |
| 库级 setting 真在挂着 | 4 行：oid `16384`(`enterprise_brain`) 与 `105788`(`eb_r59_sandbox`) 各带 `app.embedding_dimension=768` + `app.embedding_model=nomic-embed-text`，`setrole` 为空＝`(all)`，rc=0 | 同上 `-c "SELECT setdatabase::regclass AS db, setrole::regrole AS role, unnest(setconfig) AS setting FROM pg_db_role_setting ORDER BY 1"` |
| 后端镜像四枚工具全缺 | `psql`／`pg_dump`／`pg_restore`／`pg_dumpall` 逐枚 `MISSING`，四枚 rc 全 =127 | `docker exec enterprise-brain-backend-1 sh -c "command -v <tool>"` |
| 宿主没有 psql | `Get-Command psql` → `MISSING`（所以 §7 的钉一律走假 `psql`，见 §9 第 3 格） | Windows 宿主现取 |
| 库名与口令来源 | `deploy/.env.server:17 POSTGRES_DB=enterprise_brain`、`:18 POSTGRES_USER=enterprise_brain`（Redis 走 `:20 REDIS_PASSWORD`，`EB_EVAL_PASSWORD` 会 WRONGPASS 读出假零） | `rg` 只读 |

**现场挖出的真缺陷（已钉）**：PG 16.15 的 `json_agg(...)::text` 在数组元素之间插换行——现取交回
`[{"name":"app.embedding_dimension","value":"768"}, ` + 换行 + `{"name":"app.embedding_model",...}]`。
按"一行一值"读会把两枚 setting 误拒成"读不动"。`_read_json:402` 改成整段拼回再解，并坚持**标量**
那一腿多一行即拒（两枚牙：`test_the_reader_rejoins_the_json_that_postgres_wraps_across_lines`／
`test_a_scalar_that_comes_back_as_two_lines_is_still_refused`，钉里直接复现那枚字节形状）。
`oid` 列在 JSON 里是**字符串**（`"16384"`），桩按真形状对齐，不许按 int 写桩。

## 7. 复跑数字（全部「执行层自报」；未跑全量门）

跑法：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8 -m pytest <清单> -o addopts= -p no:cacheprovider --basetemp=$env:TEMP\... -q`。禁域件只跑未改。

| 清单 | 结果（执行层自报） |
|---|---|
| 本单三枚新钉（34 枚） | `34 passed`，rc=0 |
| `test_database_backup` + `test_r283_backup_covers_vector_table` + `test_postgres_backup_recovery` + `test_r575_vector_restore_drill` + 本单三枚 | `1 failed, 79 passed, 3 skipped` |
| 上一行再加 `test_deployment_guards` + `test_r96_image_provenance` | `1 failed, 116 passed, 3 skipped, 8 warnings` |
| **基点态**（同一批六枚邻居件，跑在 `03507f3` 的干净影子树里） | `83 passed, 3 skipped, 8 warnings`，**0 failed** |

对账：基点六枚 83 passed → 本单跑同批 82 passed + 1 failed = 83，**差额恰好只有 §8 那一枚**，
本单没把别家弄红（在这批件范围内成立；全量门未跑，见 §9 第 10 格）。

## 8. 一枚邻居红：本单唯一的越界风险点，请总控裁决

- 红名：`tests/test_r283_backup_covers_vector_table.py::test_the_cli_forwards_both_landing_points_and_the_restore_tool`
  （`:567`），读数 `TypeError: fake_run() got an unexpected keyword argument 'capture_output'`，栈在
  `scripts/restore_database.py:355`。
- 成因（不是本席改坏了它）：该桩 `monkeypatch.setattr(backup_module.subprocess, "run", fake_run)`
  顶掉的是**共享的 stdlib `subprocess` 模块**，而签名 `def fake_run(command, *, env, check)`（`:582`）
  既没有 `capture_output` 也没有 `**kwargs`。判据①要求备份 CLI 多起一枚 `psql`，这枚桩就必然被第二枚
  进程叫到——它把"出厂 CLI 只起一枚进程"当成了常驻不变量。
- **归因实验**（本席现跑）：临时摘掉备份侧采集那一步（`14eae2a1bcf1` → `761df4c60809`），那枚邻居
  **立刻 `1 passed`**（rc=0），随后逐字节还原 True ⇒ 红 100% 来自本单新增的第二枚进程，不是另一起因。
- 为什么本席没绕开它（两条路都不合规）：① 让备份侧改用 Python 驱动（`psycopg`）在进程内取 setting——
  两枚出厂 CLI 今天只依赖 stdlib + `subprocess` + `dotenv`（imports 逐枚现读点名），为省一枚邻居红
  给灾备件新添一枚 DB 依赖，是把形状换成假绿；而且派工判据③要的就是"镜像带那四枚工具"，
  走进程内驱动等于不修那一格。② 把 globals 只接在 `backup_database()` 原语层——同文件 `:374`
  的 `assert len(calls) == 1`（它把**每一次** `subprocess.run` 都计数）会一起红，红面从 1 枚变 2 枚。
  本席按 R587 纸面 §2 同一口判断执行：成对产物只接在 `main()`，两枚原语
  （`backup_database()`／`restore_database()`）的进程形状一字未动。
- 请总控裁（三选一，全在本席写域外）：(a) 该枚 `fake_run` 加 `**kwargs` 并按 `command[0]` 分派
  `pg_dump`/`psql`；(b) 该枚另桩 `restore_database._run_psql`；(c) 随 R596 并树时把这枚红按
  「派工判据①与既有形状冲突」记进落账，别写成"本单自带缺陷"。

## 9. 没验的格子（逐枚点名，不许当已验）

1. **镜像未重建**：`apt-get install postgresql-client-16` 在这套 `Dockerfile` 里能不能真装上、
   装完四枚是否真在 PATH——**未验**。判据③要的就是可静态证明，本单只交静态证明。
2. **没动容器／没 `docker compose build/up`**（硬规矩）：所以"生产容器里那条 `--psql` 腿今天还跑不通"
   这一格仍在；`INDEX_BACKEND=pgvector` 那三枚容器的现读与本单无关，未复核。
3. **真机端到端未跑**：`pg_dump` → `pg_restore` → 施加 globals → 逐枚对账，一次都没真跑过。
   宿主没有 `psql`、PG 侧只读、不许建库，K1/K2/§7 全走假 `psql` 与假归档。
   🔴 **生产那一格今天仍未修**：本单修的是代码与镜像配方，不是现网读数。
4. **PGDG 可达性未验**：离线／内网客户机上 `apt.postgresql.org` 未必可达，两枚 ARG 只是把 egress
   挪到命名参数后面；这一条欠一次能连外网的构建窗口。
5. **compose 没接新 ARG**：`docker-compose.yml` 的 `args:` 仍只有 `APT_MIRROR`/`PIP_INDEX_URL`
   （`:126-127`、`:270-271`），`PGDG_MIRROR`/`PGDG_KEY_URL` 要往上传得改 compose——**未做**（他域）。
6. **纸面未同步**：`docs/deployment/backup-restore.md` 那套 CLI 用法（`:36-47`）没写 globals 成对产物、
   没写 `--psql`、没写 rc=2/3 契约——**未改**（他域）。本单只交自己这张纸。
7. **airgap 登记未更新**：新增一层 apt 安装要不要进离线件登记，本席没动（他域），
   `tests/test_r52_airgap_readiness.py` 一枚没跑。
8. **R587 并树后的合账**：它那份 globals 与本单这份是**两处实现**（同名册、同 kind、同形状，
   但不是同一份码）。并树后必须由总控合成一处导入，否则"一枚口径两处取"这族病（R393/R592）在此复发。
   本单不许碰它的写域，只能记成待办。
9. **禁域未碰**：评测集与业务 fixture、`migrations/**`（D8/D9）、`chroma_db/**`、`.gitignore`、
   `deploy/.env.server`、`frontend/**`。
10. **全量门未跑**（硬规矩禁），所以"没把别家弄红"这句只在 §7 那批件范围内成立。

## 10. 编码与盘面自证

- 六枚代码件（三枚在册件 + 三枚新钉）全部 **CRLF、无 BOM、无裸 CR**：
  逐枚 `count('\r') == count('\n') == count('\r\n')`，现场数过，见下表。
  现场数过，见下表（本纸自身同口径，故 §10 之后无正文）。
- 该树 `core.autocrlf=true`，`git add` 会把 CRLF 归一回 LF 再进 blob，所以 `git diff --numstat`
  只认本单真正改动的行（若 CR 被当内容，numstat 会显示整文件重写）；`Dockerfile` 的续行因此
  不会被带进 `\r`。
- 未 commit / 未 push / 未建分支。

| 件 | sha12 | 行数 | `\r`=`\n`=`\r\n` |
|---|---|---|---|
| `scripts/restore_database.py` | `62d20c96e7cb` | 734 | 734 = 734 = 734 |
| `scripts/backup_database.py` | `14eae2a1bcf1` | 219 | 219 = 219 = 219 |
| `Dockerfile` | `86847f2167a9` | 141 | 141 = 141 = 141 |
| `tests/test_r596_globals_pair_leaves_the_dump.py` | `78d7562e39c3` | 422（17 枚牙） | 422 = 422 = 422 |
| `tests/test_r596_restore_applies_globals_before_the_reconcile.py` | `1a64a619ce2b` | 351（10 枚牙） | 351 = 351 = 351 |
| `tests/test_r596_image_carries_the_pg16_tools.py` | `13eeca5d0902` | 178（7 枚牙） | 178 = 178 = 178 |

本纸自身同口径：CRLF、无 BOM、无裸 CR，`count('\r') == count('\n') == count('\r\n')` 现算为真。本纸的 sha12 不写在本纸里——自引用的数字写下去就会自己变成假话（同族病：把此刻读数当性质，R593 刚治过）。
