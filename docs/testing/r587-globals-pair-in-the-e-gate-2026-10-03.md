# R587｜E 门「备份恢复演练」必须连 globals 一起备：库级/角色级 setting 从今天起进门控

·单号 R587 ·执行层代号 **Tessila** ·日期 2026-10-03 ·工作树 `be-r587` ·基点 `6fcea4f`（dirty=0 起步）
·交付件四枚：`scripts/r575_vector_restore_drill.py`（改，+424/−19）、
`tests/test_r575_vector_restore_drill.py`（改，+88/−7）、
`tests/test_r587_globals_pair_gates_the_e_gate.py`（新，15 枚常驻牙）、本纸。
·复投说明：前任执行层死于 provider 429、零写入已取证，本席从干净树开工，未找其产物。

## 0. 这格判据从今天起怎么写死

> **E 门「备份恢复演练通过」= 数据逐枚同数 + 库级/角色级 setting（globals）成对取、恢复时先施加、
> 对账时逐枚等。三者缺一即红：备份工序没有与 dump 同目录同前缀的 `*.globals.json`/`*.globals.sql`
> 这一对产物，恢复工序就不许建库；恢复库里 `app.embedding_dimension` / `app.embedding_model`
> 与源库不等、或两侧都读成 MISSING，都算红——"缺失但看起来能跑"不是通过。**

为什么要有这一句：`pg_dump` 按构造不带 `ALTER DATABASE ... SET`（那是 `pg_dumpall` 的活）。
所以"恢复出来的库数据和生产逐枚同数"这件事，**天然不能证明**这库还声明着同一套向量档。
R575 那一轮就是这样：12 项指纹全等、`only_in_*=0`、备份日志全绿，而恢复库里那两枚 setting
是 `NONE` / `MISSING/MISSING`——`app/db/migrations.py`（`:57` 定义名字、`:82` 会话现读）
与 `app/rag/pg_store.py` 的读腿吃的正是这两枚。E 门要的"灾备之后还能跑"在那一刻是假绿。

## 1. 缺陷本体与一手读数（不复取总控的证，只补本席自己看见的一刀）

| 事实 | 读数 | 来源 |
|------|------|------|
| dump 的 TOC 零命中库级 SET | 269 条目录里 `ALTER DATABASE` 命中 0 | 总控 10-03 10:0x 现取（R575 纸面 §7 发现一同一族） |
| 库级 setting 真在挂着 | oid 16384=`enterprise_brain`、105788=`eb_r59_sandbox`，两枚都挂 `app.embedding_dimension=768` + `app.embedding_model=nomic-embed-text`（`setrole=0`/`(all)`） | 本席 10-03 12:0x 现取，见 §6.0 与 §6.7 |
| 消费方在树上 | `app/db/migrations.py:57`（`EMBEDDING_DIMENSION_GUC`）与 `:82`（`current_setting(...)` 探针） | 在册代码 |
| 老口径把它写成"上报" | `EXTRA_ITEMS = ("db_local_settings", "local_embedding_gucs", "cluster_roles")` + 件内注释"门禁之外**照实上报**……恢复库必然与生产不等" | `scripts/r575_vector_restore_drill.py:119-120`（改前） |
| R575 纸面已记过这笔账 | §3.2 `reconcile` 行"12 项全等 + 2 项 EXTRA 不等照实上报"；§7 发现一 | `docs/testing/r575-vector-restore-drill-2026-10-03.md` |

本席补的那一刀：**上报≠判红**。R575 把这件事诚实地写在纸上（这一点要照记），但它的对账口径
只比数据，所以同一轮既能"12 项全等"又能"恢复库读腿维度是错的"——两句话不矛盾，而 E 门会签字。

## 2. 写域选型：为什么修在 R575 演练件里，不去改 `scripts/backup_database.py` / `restore_database.py`

派工给的二选一，本席选 R575 那一头。三条取证，不是口味：

1. **头那侧做不到"默认开"，因为改它必然连带改两枚不在本单写域里的在册钉**：
   `tests/test_r283_backup_covers_vector_table.py:567` 那枚
   `test_the_cli_forwards_both_landing_points_and_the_restore_tool`，桩在 `:582-583`——
   `def fake_run(command, *, env, check): backup_module.Path(command[command.index("--file") + 1]).write_bytes(b"dump")`，
   它顶掉 `backup_module.subprocess.run` 且只认 argv 里带 `--file`；`:605` 钉 `assert backup_module.main(argv) == 0`
   （`:612` 另钉缺落点表时 `== 1`）。⇒ CLI 里多任何一次 psql/pg_dumpall 调用（它的 argv 不带 `--file`）
   要么 `ValueError` 要么真起进程，在册钉当场变红。同一文件 `:333`
   （`test_the_guard_checks_the_archive_without_narrowing_the_dump`）的桩在 `:337-339`，它把**每一次**
   `subprocess.run` 都记进 `calls`：`:359` 钉第一条 argv 逐字等于那枚 pg_dump，`:368` `calls.clear()`，
   `:374` 钉 `assert len(calls) == 1`——原文措辞是"不带 required_tables 时不得多出一次 pg_restore（既有件依赖这个形状）"，
   但被计数的是全部 `subprocess.run` ⇒ `backup_database()` 原语层同样加不进去。
   🔴 派工的允许清单只列了两枚 CLI、R575 演练件、`tests/test_r587_*`、本纸；`tests/test_r283_*` 一枚都不在其中。
2. **假绿的家不在 CLI，在演练件的对账口径**：那枚"恢复演练通过"的判据是 R575 写的，
   `EXTRA_ITEMS` 就是它的出口。改口径要连门一起改，改一头不改另一头就是换个地方继续绿。
3. **总控把这两枚 CLI 划给本号二选一，而 R60 那一单把它们记成"R587 在飞"**：
   `docs/handoff/2026-09-15-backend-followup-requests.md:5312` 是 **§158（R60 停 Chroma 写那一单）自己的禁碰清单**，
   原文把 `scripts/backup_database.py`·`scripts/restore_database.py` 标为「（R587 在飞）」——读法是**别人那单
   因此排队等本号**，不是本号必须两头都动。本号判据全文在同文件 `:5251` 起（五格在 `:5254`、写域"二选一"
   原文在 `:5256`），本席按 §1 第 4 行那条既有口径落在 R575 演练件这头。

🔴 **代价照实写**：生产 CLI 那一格**今天仍然没修**——`scripts/backup_database.py` /
`restore_database.py` 默认照样不取、不施加 globals。这一格要连 R283 那两枚钉一起改判据才动得了，
本席一枚字都没改（写域之外不越界），列为 §7.1。

另记一手（与本单判据无关但同源）：`pg_dumpall --globals-only` 在本机 PG 16.15 上零枚
`ALTER DATABASE`，只交回一行 `CREATE ROLE` 与一行带 **SCRAM 口令散列**的 `ALTER ROLE`。
所以"随手加 `--globals-only`"既不覆盖这格（它不带库级 SET），又把口令抄进备份件——本件因此
自己取 `pg_db_role_setting`、自己配施加件，且**只**取当前库的行、集群级行一律不上手。

## 3. 判据①：备份工序把 setting 成对取下来

件内新函数（`scripts/r575_vector_restore_drill.py`，全部插在原 `LEDGER` 之前）：

- `GLOBALS_SQL`：一条只读 `SELECT`，把 `pg_db_role_setting` 的
  `setdatabase` / `setrole` / `setconfig` 三列逐枚取回，外加四列把 oid 翻成名字、把
  `setconfig` 那枚数组 `CROSS JOIN LATERAL unnest` 摊平成"一名一行"，`WHERE` 收到
  `current_database()`；作用域三分类 `database` / `role_in_database` / `deferred`。
- `required_global_settings()`：必读项名字**惰性 import** `app.db.migrations` 那两枚常量，
  件里不再抄第二份（牙：`test_the_required_names_come_from_the_migration_file` 直接等式比对）。
- `collect_globals()` / `write_globals_artifacts()`：把读数连同**归档自己的 sha256**写进
  `<dump 同名>.globals.json`（账）与 `<dump 同名>.globals.sql`（能跑的施加件），
  落点与 dump **同目录同前缀**（`globals_paths_for()` 只从归档名派生）。
- `read_globals_artifact()`：恢复工序的入口（`scripts/r575_vector_restore_drill.py:440-482`），九枚 `Refuse`
  各拦一处"不成对"——少产物 / JSON 读不动 / 不是对象 / `kind` 不对 / 归档实算 sha 与产物记录不等 /
  没有会话账 / 缺必读 setting 的源值 / `apply_lines` 与按 rows 现算不等 / `.globals.sql` 正文与记录逐字节不等；
  另加 `checked_globals_row()` 与 `checked_globals_rows()`（`:313-346`）那七枚形状自校 `Refuse`。
  牙：`test_a_restore_without_its_pair_refuses_before_it_can_build_a_database`、
  `test_the_pair_must_match_the_archive_it_ships_with`、`test_the_archive_sha_and_the_pair_are_the_same_reading`。
- `backup()` 挂点：源库里 `required_global_settings()` 有一枚读成 `MISSING` 就 **REFUSE**
  （"没有源值就配不出可信的施加件"），不留 `--allow-*` 逃生门；交回的 manifest 多一枚 `globals`。

## 4. 判据②与③：恢复先施加、对账逐枚等

- **②施加**：`restore()` 在 `pg_restore` 成功之后、`ANALYZE` 之前，先
  `apply_globals(container, drill, payload)` 再 `verify_globals(...)`；不等即
  `Mismatch`，且清理从 `except Refuse` 扩到 `except (Refuse, Mismatch)`——红的一轮不留半截库。
  成对产物的发现与核对排在 **sha 闸 → `pg_restore --list` → 落点 → danger → globals** 之后、
  `CREATE DATABASE` 之前，且这一步**零枚 docker 调用**（在册那枚"sha 不对就什么都不发"没被挪）。
  施加走"整份 `.globals.sql` 原样进一枚新 psql 会话"（`BEGIN;` + 逐枚 `\gexec` + `COMMIT;`），
  语句文本由服务器自己 `format()`：库名一律 `current_database()`，Python 一头不拼库名。
- **③对账**：`RECON_ITEMS` 从 12 项升到 **14 项**（新增 `globals_profile` / `globals_session`），
  再在 `compare_fingerprints()` 里补一道 `gate_required_globals()`——因为整串比对对
  "两侧都 MISSING"是**相等**的，那一格正是假绿的出口。门控四态各点名：读不到 / 源库没声明 /
  恢复库 MISSING / 两侧不等，`differences` 里逐枚具名。

## 5. 判据⑤点名：R575 那两件里因此改了判据或加了格（逐格）

| # | 格子 | 改前 | 改后 | 为什么必须这么改 |
|---|------|------|------|----------------|
| 1 | `RECON_ITEMS` | 12 项 | 14 项（+`globals_profile` +`globals_session`） | 数据同数不证 setting 在位；门控要含它 |
| 2 | `EXTRA_ITEMS` | `db_local_settings`/`local_embedding_gucs`/`cluster_roles` | `globals_deferred`/`cluster_roles` | 前两枚读的就是这件事，"上报"升"门控"；一格只留一个口径（R393 的教训：一枚数字两处取，早晚各说各话）|
| 3 | `GUARD_READS` | 三枚 | 一枚（`cluster_roles`） | 同上；库级 setting 改由 `collect_globals` 一处取 |
| 4 | `DB_LOCAL_SETTINGS_SQL` / `LOCAL_GUC_SQL` | 在册两枚常量 | **摘掉** | 旧那枚形状带库名（`db=%s`），两侧永远不等，只能上报；留着就是第二口径 |
| 5 | `collect_fingerprint()` | 只比数据 | 末尾接 `collect_globals`，并带走 `globals_rows`/`globals_session_map` | 门要按枚点名，拿字符串反解就是自找漂移 |
| 6 | `compare_fingerprints()` | 整串相等即过 | 加 `gate_required_globals()` | "两侧都 MISSING"这一格只有这道门拦得住 |
| 7 | `backup()` | 不取 globals | 取→源值缺即 REFUSE→写成对产物→manifest 带 `globals` | 判据① |
| 8 | `restore()` | 不认 globals | 读通成对产物（建库前）→pg_restore 后先施加+现读现证→`except (Refuse, Mismatch)` 清半截库→交回 `globals` 账 | 判据② |
| 9 | `_full_steps()` / `report()` | 无 | `reading["backup"]` 带上 `globals`；报告多一行 `globals    : 施加 N 枚 / 集群级只上报 M 枚` + 三枚 sha 前 12 | 每轮 `full` 都留得下这本账 |
| 10 | 模块 docstring | ①/安全边界/反证三段 | 三段各补一句（假绿怎么来的、施加只准打恢复库、三把反证去哪看） | 纸与码同口径 |
| 11 | `tests/test_r575_...py::FakePg` | 背答案的句柄 | **有状态的库**：`self.settings[库名][名字]=值`、`_apply_globals()` 真把 `\gexec` 那句打在状态上、`current_setting` 现读现答、`_statements()` 认 `--` 注释与 `\gexec` | 不这么改，"全等"那枚在册钉要么自红、要么假绿 |
| 12 | `FakePg._patterns()` | 含 `FROM pg_db_role_setting`→`"NONE/db=..."`、`current_setting('app.embedding`→`"MISSING/MISSING"` | 两枚旧答案摘掉，改走 `_settings_rows()` | 形状必须跟着 `GLOBALS_SQL` 走，否则就是替件编故事 |
| 13 | `test_restore_refuses_to_create_a_second_database_with_the_same_name` | 只写归档 | 补 `_pair(archive)` | 今天"没有成对产物"就是 REFUSE，那枚用例要的才是第二枚同名库那道闸 |
| 14 | 在册那 23 枚 | 23 passed | 仍 23 passed（零枚改判据放宽） | 本单只加格与收紧，没给任何旧钉开后门 |
| 15 | 新加 | — | `tests/test_r587_globals_pair_gates_the_e_gate.py` 15 枚 | 判据④三把 + ①②③的形状，全部离线常驻 |

## 6. 一手凭据（命令 → rc → 末行）

真库那一律 `docker exec`（容器 `enterprise-brain-postgres-1` **没有宿主端口映射**，宿主 5432 上那枚
是没有 `vector_scope` 的野库，直连就是假读数）；`enterprise_brain` 全程只读；
自建演练库只有 `eb_r587_restore` 这一枚名字，用完 `DROP DATABASE`。
🔴 **窗内纪律**：run16 评测窗在飞，所以本单的真库取证**零枚 pg_dump / pg_restore**（见 §7.2），
只做毫秒级的 catalog 现取与 `ALTER DATABASE ... SET/RESET`；离线测试一律单文件跑、不开并行。

### 6.0 一手现取：这台机上现在挂着哪些库级 setting
```
docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d postgres -X -q --csv -t -c \
  "SELECT coalesce(d.datname,'(cluster)') || ' | ' || st.setconfig::text FROM pg_db_role_setting st
   LEFT JOIN pg_database d ON d.oid = st.setdatabase ORDER BY 1"
→ rc=0
  "eb_r59_sandbox | {app.embedding_dimension=768,app.embedding_model=nomic-embed-text}"
  "enterprise_brain | {app.embedding_dimension=768,app.embedding_model=nomic-embed-text}"
```
末行即取证收尾后的现状：两枚在册行原样在位，本单自己造成的行一枚不留。

### 6.1 配对的那枚真归档（沿用，不重 dump）
```
Get-FileHash C:\Users\fengx\PycharmProjects\r587-drill\eb-r587-src.dump → 74,011,209 字节
  sha256 = 385c74095df5f3df038813e6a0a3173dd77bf4b3e0e6e1c86321bffaa0a6eb50（前 12 385c74095df5）
docker exec ... sha256sum /tmp/r587-drill/eb-r587-src.dump → 同一枚全串（容器内外逐字节同）
```
🔴 订正一处交接数字：这枚 dump 是 **74,011,209 字节**（前任手记写成 7,401,120，少一位）。

### 6.2 判据①｜备份工序在真库上的读数
```
python -X utf8 %TEMP%\r587_real_driver.py        （驱动在仓外 TEMP，不入库）
→ rc=0，末行 "log 已落 TEMP\r587_evidence.log"
  collect_globals(CONTAINER, "enterprise_brain") rows=
    [{"scope":"database","setdatabase":"16384","setrole":"0","database":"enterprise_brain",
      "role":"(all)","name":"app.embedding_dimension","value":"768"},
     {"scope":"database","setdatabase":"16384","setrole":"0","database":"enterprise_brain",
      "role":"(all)","name":"app.embedding_model","value":"nomic-embed-text"}]
  profile=database|(all)|app.embedding_dimension=768 ;; database|(all)|app.embedding_model=nomic-embed-text
  session_profile=app.embedding_dimension=768 ;; app.embedding_model=nomic-embed-text   deferred=NONE
  成对产物 C:\Users\fengx\PycharmProjects\r587-drill\eb-r587-src.globals.json / .globals.sql
    applied=2 deferred=0 json_sha[:12]=d6c2b1cdd195 sql_sha[:12]=9732c06d3f85 配对归档_sha=385c74095df5
  read_globals_artifact(真 74MB 归档) 通过：archive_sha[:12]=385c74095df5 apply_lines=2
```
施加件正文（注释与事务壳剥掉，逐字符）：
```
SELECT format('ALTER DATABASE %I SET app.embedding_dimension = %L', current_database(), '768') \gexec
SELECT format('ALTER DATABASE %I SET app.embedding_model = %L', current_database(), 'nomic-embed-text') \gexec
```
两枚语句里**零枚库名**：`enterprise_brain` / `eb_r587_restore` 都不出现，落点由服务器
`current_database()` 现算（牙：`test_the_pair_lands_next_to_the_dump_under_the_same_stem`、
`test_the_archive_sha_and_the_pair_are_the_same_reading`、`test_cluster_wide_settings_are_reported_never_applied`）。

顺手捡到的反例（本席没写死两枚名字的证据）：上一席在 `eb_r587_restore` 上留过一枚
`app.r587_probe=7'6;8`，`collect_globals` 把它原样取回并写进 profile——
`database|(all)|app.r587_probe=7'6;8`。取数按行摊平，不按名字表挑。

### 6.3 判据②与③｜空库先红、施加后绿（同一枚库、同一份产物）
| 步 | 命令（`docker exec` 内） | rc | 末行读数 |
|----|--------------------------|----|----------|
| 建空库 | `CREATE DATABASE "eb_r587_restore" TEMPLATE template0` | 0 | 库名清单回到 6 枚 |
| **CE-A 摘前**（= 没有施加那一步的盘面） | `collect_globals` + `verify_globals` | — | `profile=EMPTY`；`session=app.embedding_dimension=MISSING ;; app.embedding_model=MISSING`；`gate` 两条：**"恢复库里它是 MISSING：globals_session[app.embedding_dimension]: 生产='768' 恢复='MISSING'。向量一枚不少、备份日志全绿，读腿维度仍是错的——R587 拆的就是这枚假绿"**；`verify` 四条（两枚"备份里有、恢复库没有（施加那一步没落地）"＋两枚 MISSING） |
| **CE-A 摘后**（把施加打回去） | `apply_globals(...)` | 0 | 新会话现读 `rows` 两枚在位（注意 oid 已变成 701193——建一枚库换一个，所以**对账钥匙不带 oid 也不带库名**）；`gate=[] verify=[]` |
| **CE-B 摘前** | `ALTER DATABASE eb_r587_restore SET app.embedding_dimension = 1536` | 0 | `session_profile=...dimension=1536 ...`；`gate` 一条："恢复库与源库不等：globals_session[app.embedding_dimension]: 生产='768' 恢复='1536'"；`verify` 两条（备份='768' 恢复库='1536' / 会话值不等） |
| **CE-B 摘后** | — | — | 产物与件一字未动（见 §6.5 的 sha 行） |
| **CE-C 摘前** | `ALTER DATABASE eb_r587_restore RESET app.embedding_dimension`；`RESET app.embedding_model` | 0 / 0 | `profile=EMPTY`；`session` 两枚 MISSING；`gate` 两条 MISSING 原文 |
| **CE-C 摘后** | `apply_globals` 再打一遍 | 0 | `gate=[] verify=[]`（正控：这枚牙不是永远红） |

`enterprise_brain` 上本席只发过只读语句（`collect_globals` / `collect_fingerprint` 都走
`run_psql(..., readonly=True)`，两道独立闸）；改值那三步全部打在自建库上。

### 6.4 施加的原子性（件头那句"要么两枚都在、要么一枚都没有"）
从**空库**起跑，两枚 ALTER 之间掺一句非 SQL：
```
psql -f <掺坏话的施加件>   → rc=3
  psql:<stdin>:3: ERROR:  syntax error at or near "THIS"
  LINE 1: THIS IS NOT SQL
之后 collect_globals → profile=EMPTY  → 两枚都没落地（全或无成立）
再打干净的施加件     → rc=0 → profile=database|(all)|app.embedding_dimension=768 ;; ...nomic-embed-text
verify=[]
```
🔴 照实记一笔本席自己的错：CE-D 第一次跑的时候期望写错了——当时库里还留着 CE-C 收口时施加的
`app.embedding_model`，我只 RESET 了 `app.embedding_dimension`，于是驱动打印出"有半套残留"。
那是**驱动的判定句错**，不是件的行为（被 RESET 的那枚确实没随坏批次落地）。上面这一版是
"从空库起跑"的重测，第一轮读数不引用。

### 6.5 三把反证的摘前/摘后 sha256 前 12（逐把点名）
每一把都记同一组四枚：`drill件 / dump / globals.json / globals.sql`
```
取证开始   f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-A 摘前  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-A 摘后  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
施加后     f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-B 摘前  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-B 摘后  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-C 摘前  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-C 摘后  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-D 摘前  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
CE-D 摘后  f6e551a53e48 385c74095df5 d6c2b1cdd195 9732c06d3f85
```
十行逐列相同 ⇒ 三把红都不是"换了文件"造成的；红的来源只有盘面状态或那一格代码。
（离线那三把另有摘法，见 §6.6 的变异表；每枚摘完当场还原，`[Mx] 还原 sha … 一致` 逐条打印。）

### 6.6 变异表（离线常驻牙的灵敏度，一次一枚，当场还原）
| # | 摘掉的挂点 | 摘后读数（两册钉合跑，共 38 枚） | 还原自证 |
|---|------------|----------------------------------|----------|
| M1 | `compare_fingerprints` 里那道 `gate_required_globals` | **1 failed / 37 passed**，红在 `test_both_sides_missing_is_not_a_pass`：`AssertionError: 整串相等也不算过` | `还原 sha f6e551a53e48 摘前 sha f6e551a53e48 -> 一致` |
| M2 | `restore()` 里 `applied = apply_globals(...)` 那一行 | **2 failed / 36 passed**，红在 `test_globals_land_before_the_restored_database_is_checked` 与 `test_a_third_setting_travels_with_the_pair`（两条 Mismatch 原文"globals 施加之后恢复库仍与备份记录不等"） | 同上 |
| M3 | `read_globals_artifact` 的归档 sha 那道闸 | 第一轮 **36 passed（零枚红）**→ 暴露本席漏写了"成对可核对"那枚牙；补 `test_the_pair_must_match_the_archive_it_ships_with` 之后复跑 **1 failed / 37 passed**（`DID NOT RAISE Refuse`） | 同上 |
| M4 | `collect_fingerprint` 里 `globals_profile` 那格（退回"只上报"） | **6 failed / 32 passed**，逐枚具名——r575 三枚 `test_the_fingerprint_reads_live_numbers_not_constants`／`test_the_reconcile_is_data_driven_and_names_the_offending_item`／`test_taking_the_vector_check_out_turns_the_reconcile_red`；r587 三枚 `test_the_reconcile_gate_names_every_setting_that_did_not_land`／`test_one_changed_value_on_the_source_turns_the_third_cell_red`／`test_both_sides_missing_is_not_a_pass`。读数：四枚 `Mismatch: 对账缺项：globals_profile` ＋ 一枚 `KeyError: 'globals_profile'` ＋ 一枚 `AssertionError`（`tests/test_r575_vector_restore_drill.py:385`）；日志 `%TEMP%\r587_m4.txt` | `还原 sha f6e551a53e48 摘前 sha f6e551a53e48 -> 一致` |
| M5 | `restore()` 里 `payload = read_globals_artifact(archive)` 那道门 | **6 failed / 32 passed**，逐枚具名——r575 一枚 `test_restore_refuses_to_create_a_second_database_with_the_same_name`；r587 五枚 `test_a_restore_without_its_pair_refuses_before_it_can_build_a_database`／`test_globals_land_before_the_restored_database_is_checked`／`test_taking_the_apply_step_out_turns_the_third_cell_red`／`test_a_third_setting_travels_with_the_pair`／`test_the_pair_must_match_the_archive_it_ships_with`。判据本体那枚 `test_taking_the_apply_step_out_...` 交回 `Failed: DID NOT RAISE Mismatch`，其余五枚以 `PermissionError: [Errno 13] Permission denied: '.'` 现出——变异桩把 `sql_path` 抹成空串，红得难看但方向对；日志 `%TEMP%\r587_m5.txt`（10-03 12:4x 复跑，读数与第一轮逐枚同） | `还原 sha f6e551a53e48 摘前 sha f6e551a53e48 -> 一致` |

M3 那一行是本单最该记住的一笔：**"新加的钉全绿"不等于"新加的钉有牙"**。第一版 15 枚钉交出
15 passed，摘掉归档 sha 那道闸也照样 15 passed——直到我按 §5 第 13 行那口径把"成对可核对"
补成一枚独立用例。这枚教训按 AGENTS 的规矩写进纸，不藏在"全绿"两个字后面。

### 6.7 收尾自证（本单残留清空；容器 /tmp 里另有两枚别席的件，照记不删）
```
DROP DATABASE eb_r587_restore（drill.drop_drill，只认这一枚名字）→ rc=0
docker exec ... sh -c "rm -rf /tmp/r575-drill* /tmp/r587-drill"   → rc=0
  （后者是上一席留在 PG 容器 /tmp 里的 74MB scratch，一并清掉）
库名清单：['eb_r59_sandbox', 'enterprise_brain', 'postgres', 'template0', 'template1']
容器内 scratch：本单那一族（``/tmp/r575-drill*``、``/tmp/r587-drill``）已清空。
  🔴 12:5x 复读仍见两枚**不是本单的**：``/tmp/a.sql``(3279B) 与 ``/tmp/b.sql``(3324B)，root，
  mtime ``Oct 3 00:56``，正文是 ``explain analyze ... set_config('hnsw.ef_search','100',TRUE)`` 与
  ``set enable_seqscan=off; set enable_sort=off`` 那一族 —— 归属按推断留手（正文形状与 R579 那一族同源；本单禁碰
  ``scripts/r579_*``/``tests/test_r579_*``），本席一枚没删，只把事实记在这里。
全实例 pg_db_role_setting：只剩 §6.0 那两枚在册行
仓外产物（本单判据①的凭据，留在仓外不入 git）：
  C:\Users\fengx\PycharmProjects\r587-drill\{eb-r587-src.dump, eb-r587-src.globals.json, eb-r587-src.globals.sql}
```
🔴 一处与本席无关但总控要知道的盘面变化：本班开工时库名有 `eb_r579_probe`（6 枚），
收尾时是 5 枚。本席的驱动只调 `drop_drill(DRILL_DB="eb_r587_restore")`，
`assert_droppable` 只认那一枚名字，`eb_r579_probe` 一枚都没碰——它是 R579 那一席自己收掉的。

## 7. 没验的格子（照实列，不用"应该没问题"盖）

1. 🔴 **生产 CLI 那一格没修**：`scripts/backup_database.py` / `restore_database.py` 今天默认
   照样不取、不施加 globals（选型与代价见 §2）。这一格要连
   `tests/test_r283_backup_covers_vector_table.py` 的两枚在册钉一起改判据才动得了——`:333`（配 `:337-339`
   的桩与 `:374` 的 `len(calls) == 1`）与 `:567`（配 `:582-583` 的桩与 `:605`/`:612` 的 rc 断言）；
   而那两枚件不在本单写域，本席一枚字没改。
2. **真库上没跑 pg_dump/pg_restore 那一轮**：run16 在飞，窗内不给 PG 容器加 IO/CPU。
   因此判据②里"排在 `pg_restore` 之后、`ANALYZE` 与任何对账之前"这一格的**真库顺序**证据，
   今天由 15 枚离线钉（含 M2/M5 的变异读数）＋ §6.3 的"建空库→红→施加→绿"代证，
   R575 那一轮 `full`（12→14 项、检索两档）今天不重跑。翻默认之后要签 E 门的人应当重跑
   `full` 一次，读数会把 `globals    :` 那行一起带出来。
3. **`--drill-db` 仍锁 `eb_r575_drill`**：派工要本席自建 `eb_r587_restore`，所以真库证据走的是
   仓外一次性驱动，把件里的 `DRILL_DB` 换成那一枚名字；件里 `assert_creatable` /
   `assert_droppable` / `apply_globals` 的三道同名闸跟着它，没有绕过。件本身没改默认。
4. **集群级 `ALTER ROLE ... SET` 与角色清单**：真库现取 `deferred=NONE`（这台机上一枚都没有），
   所以"只上报不施加"那一族只由离线钉证形状（`test_cluster_wide_settings_are_reported_never_applied`）。
5. **`role_in_database` 的施加语句**：真库上没有这一族行，语句文本（
   `ALTER ROLE %I IN DATABASE %I SET ... current_database() ...`）只逐字符核对于离线。
6. **宿主直连容器 5432 那条路今天仍然不存在**（R575 件头写明），本单一枚语句都没走网络；
   `deploy/README.server.md:133` 那句 `docker compose run --rm backend python scripts/backup_database.py
   --output /app/data/backups/brain.dump` 今天仍然跑不动——本席 12:4x 逐枚现读（dash 下 `command -v`
   多参数只报第一枚，所以四枚分开问）：`docker exec enterprise-brain-backend-1 sh -c "command -v psql"`
   （及 `pg_dump` / `pg_restore` / `pg_dumpall` 三次）逐次交回 **MISSING**；容器
   `enterprise-brain-backend-1`（image `enterprise-brain:local`）Up healthy。服务端身份本席也复取了：
   `SELECT version()` → `PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)`，rc=0。
   这是**另一枚缺陷**，本单不修，只回报。
7. **CE-D 第一轮的判定句写错**（§6.4），已重测；引用的是重测那一版。
8. **全量回归门没跑**（`scripts/run_gate.py` 是总控独占）：本席只单文件跑了三册——
   `tests/test_r575_vector_restore_drill.py` 23 passed、
   `tests/test_r587_globals_pair_gates_the_e_gate.py` 15 passed、
   邻座回归 `tests/test_r283_backup_covers_vector_table.py`+`tests/test_database_backup.py`+
   `tests/test_postgres_backup_recovery.py` 23 passed / 3 skipped。合跑 38 passed。
   枚数与最新绿票对账归总控，不在本纸上算。
9. 没跑 `r575 full`，所以 R575 纸面 §3.2/§4 那几张表今天**不会**自动多出 `globals` 那一行；
   §5 第 9 行只声称码与报告函数已经带上它。

## 8. 盘面与复跑

| 文件 | 状态 | 行数 | sha256[:12] |
|------|------|------|-------------|
| `scripts/r575_vector_restore_drill.py` | 改 +424/−19 | 1457 | `f6e551a53e48` |
| `tests/test_r575_vector_restore_drill.py` | 改 +88/−7 | 651 | `2da8f5e036f5` |
| `tests/test_r587_globals_pair_gates_the_e_gate.py` | 新（未跟踪） | 319（15 枚 test） | `7071caf69f23` |
| `docs/testing/r587-globals-pair-in-the-e-gate-2026-10-03.md` | 新（本纸） | **不落数** | **不落数**——本纸的行数与 sha 都会在抄下它的那一刻因自己而变（自指假账）；交回报告给装配后的读数 |

四件交付件都是 **统一 CRLF、无 BOM**（`count('\r')==count('\n')==count('\r\n')` 逐枚自证）。
基点 `6fcea4f`，未 commit、未建分支、未 push（交总控验收后代提交）。

复跑（离线，单文件）：
```
$env:PYTHONPATH="C:\Users\fengx\PycharmProjects\be-r587"
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8 -m pytest `
  tests/test_r575_vector_restore_drill.py tests/test_r587_globals_pair_gates_the_e_gate.py `
  -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r587x" -q --no-header
→ 38 passed
```
真库取证：`python -X utf8 %TEMP%\r587_real_driver.py`（驱动在仓外，日志
`%TEMP%\r587_evidence.log`）；它可重跑——第 0 步会把同名库先清场。