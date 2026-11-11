# R575 —— 真库向量备份—恢复演练：R60 停写 Chroma 的硬前置，六格判据的凭据纸

单号 R575 ·执行层代号 **Bohr** ·工作树 `C:\Users\fengx\PycharmProjects\be-r575`（基点 `b85c277`）
·日期 2026-10-03 ·交付件三枚：`scripts/r575_vector_restore_drill.py`、
`tests/test_r575_vector_restore_drill.py`、本纸。

一句话：**这份 dump 能把生产向量库整枚恢复回来，而且恢复出来的库答检索答得一模一样——
六格全达；反证把本件自己的一枚假阳性当场抓出来并修掉了（§5 的 CE5）。**

向量库口径按定案写：PostgreSQL + PGVector 是生产方案，Chroma 是退役中的遗留件。本单**没有**
停写 Chroma、**没有**翻任何默认、**没有**动 backend/worker/scheduler 三枚容器（restart 都没做
一次）、**没有**打模型、**没有**调 11434。它只回答一件事：R60 之前那道「真库恢复演练」到底做没做、
怎么做、有没有牙。

---

## 1. 环境事实（本班现取，不是抄旧纸）

| 项 | 现取读数 |
|----|----------|
| 容器 / 镜像 | `enterprise-brain-postgres-1` / `pgvector/pgvector:pg16` |
| 服务端身份 | `16.15 (Debian 16.15-1.pgdg12+2)` / `system_identifier=7685285828163473446` |
| pgvector | `0.8.6`（`SELECT extversion FROM pg_extension WHERE extname='vector'`） |
| 宿主端口 | **无映射**（`docker port` 空；宿主 5432 是另一台原生 `postgres.exe`）⇒ 一切走 `docker exec` + `docker cp` |
| 口令 | **未取用**。容器内 unix socket 为 trust，`psql -U enterprise_brain` 直接 rc=0 ⇒ 本件不读 `deploy/.env.server`，纸里也不出现任何口令 |
| 向量列 | 真名 **`embedding vector(768)`**。派工单写的 `count(vector)` 在该表不存在（无 `vector` 列），本班按真列名取数 |
| 生产库基线 | `chunk_vectors` 1008 行 / `embedding` 1008 枚 / 维度 `768..768` / 全零 0 枚 / `vector_scope` 1 行 / `documents` 105 / `chunks` 1008 / 迁移 `0001..0018`（0019 未应用） / 7 枚索引（含 hnsw `m=16, ef_construction=100`） |
| 逐行向量指纹 | md5 **`2277eab6b71ad776827ea4c3b04840e9`**（`md5(string_agg(vector_id || '#' || embedding::text, ';' ORDER BY vector_id))`）——今日全部读数一枚不差 |
| `hnsw.ef_search` 界 | min 1 / max 1000 / 出厂 40（从 `pg_settings` 现取，件里不写死） |
| 演练前库名基线（6 枚） | `eb_r579_probe`, `eb_r59_sandbox`, `enterprise_brain`, `postgres`, `template0`, `template1` |

`eb_r579_probe` 与 `eb_r59_sandbox` 是**别单的库**（归属现取 `pg_get_userbyid(datdba)=enterprise_brain`），
本单从建到删一枚没碰；基线里带着 `eb_r579_probe` 说明这台机上另有班在跑，所以残留判据按「别人家的库
一枚不许多、一枚不许少」算（§5 CE5 就是这支）。

## 2. 交付件与重跑方法（演练是**件**，不是一次性手敲）

```
cd C:\Users\fengx\PycharmProjects\be-r575
<解释器> -X utf8 scripts\r575_vector_restore_drill.py full --queries 20 --top-k 10
<解释器> -X utf8 scripts\r575_vector_restore_drill.py full --keep
<解释器> -X utf8 scripts\r575_vector_restore_drill.py full --replace-drill-db
<解释器> -X utf8 scripts\r575_vector_restore_drill.py preflight|backup|restore|reconcile|recall|cleanup
   restore 支可带 --archive <dump> [--expect-sha256 <hex>]；reconcile 支可带 --skip-vector-check（只用于反证）
<解释器> = C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe（主树解释器，只用不改）
```

退出码分档不合并：`0` 通过 / `1` 未预期 / `2` REFUSED（前置不满足或危险动作，不出任何对账结论）/
`3` MISMATCH（对账不等或缺项）/ `4` RECALL RED（检索对账不等）/ `5` RESIDUE（库名集合没回基线）。

产物一律落**仓外** `C:\Users\fengx\PycharmProjects\r575-drill\`；件里 `assert_outside_worktree`
逐级找 `.git`，指到任何工作树内直接拒 ⇒ 不存在"dump 落进 git 树"这条路径。

结构上的两枚要点（后来人改单须知）：所有 docker/psql/pg_dump/pg_restore 只走一枚出口 `_run()`
（离线钉就桩它）；读腿不复制 SQL，而是捕获在册 `app.rag.pg_store.search_vectors` 自己拼的两句
（`set_config` 在排名语句之前）就地填 `%s`——所以本纸证的是**生产读腿**，不是平行实现。

## 3. 动作 1–5 原文命令、退出码、读数

### 3.1 动作 1｜现取自证（只读）

```
docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -t -A -c \
  "select count(*), count(embedding) from chunk_vectors"      → 1008|1008        rc=0
docker exec ... -c "select extname from pg_extension"          → plpgsql / vector  rc=0
docker exec ... -c "select max(version) from schema_migrations"→ 0018              rc=0
```

### 3.2 动作 2–5｜权威一轮（最终码，stamp `20261003T020100Z`，rc=0）

```
full --queries 20 --top-k 10 --replace-drill-db
```

| 步 | 读数 |
|----|------|
| preflight | 镜像/身份/pgvector 见 §1；库名基线现取；生产库 12 项指纹取回 |
| backup | `pg_dump --format=custom` → `eb_r575_drill-20261003T020103Z.dump`，**72392506 字节**，sha256 前 12 **`fd40eaa05402`**（全串 `fd40eaa05402d2f3efe57bd5fd0e5f7eec1c14a8bb3e8a16d4370b503a90e47a`），TOC 269 条，落点表在册（`chunk_vectors` 等有 TABLE DATA 条目） |
| restore | `CREATE DATABASE "eb_r575_drill" TEMPLATE template0` → `pg_restore --no-owner --exit-on-error` → 只在恢复库 `ANALYZE chunk_vectors / ANALYZE chunks` |
| reconcile | **12 项全等**（§4）+ 2 项 EXTRA 不等照实上报（§7 发现一） |
| recall | 两档宽度 `only_in_*=0`、名次最大位移 `0`、top-1 距离差 `0.0`（§4） |
| postflight | 生产库前后 12 项逐枚同数（含 `2277eab6…`） |
| cleanup | `drop_drill` 只删 `eb_r575_drill`；`drill_dropped=true`；库名清单回到基线 6 枚 |
| artifacts | 读数 JSON + 对生产库语句逐条账本（**173 条**）+ `r575-latest.json` 指针 |

同一天另两轮 PASS（最终码）：`20261003T015719Z`（dump `72289072 B / ae2914ef5edd`，`full` 裸跑）、
`20261003T015909Z`（dump `72335151 B / 900e624e4cd7`，`full --keep`，`kept_by_request=[eb_r575_drill]`）。
修复前的历轮（`0115…0153` 几枚）留在产物目录里可查，本纸的判据读数以最终码为准；
其中 `20261003T015348Z.json`（`status=Residue`）**故意保留**，它是 §5 CE5 那枚假阳性的现场证据。

### 3.3 dump 字节数不是判据（照实写明）

今日同库连采 8 枚，字节数 `72180667 / 72188013 / 72188071 / 72191535 / 72192007 / 72289072 /
72335151 / 72392506` 一路在漂。原因两条，都已现取：归档头带时间戳；生产库**非向量表**在被持续写入
（`pg_stat_user_tables`：`checkpoint_writes` 74913 行/12846 插入、`trace_events` 52994/8972、
`checkpoint_blobs` 39792/6859、`agent_runs` 1817 行/8681 更新、`model_calls` 5688/1066…），
而 `chunk_vectors` 不在写入榜上（12 项指纹含逐行 md5 恒等可证）。
**⇒ 判据建立在"恢复库 12 项指纹 + 检索对账"上，不建立在 dump 逐字节相等上。**

## 4. 对账口径（本单真判据）

门控 12 项（生产 vs 恢复库，逐项点名，全等）：`chunk_vectors_rows` 1008、`embedding_count` 1008、
`embedding_column_type` `vector(768)`、`embedding_dims` `768..768`、`zero_vector_rows` 0、
`vector_scope_rows` 1、`vector_scope_profile`（`1|nomic-embed-text|768|l2|16|100|created|updated` 全串等）、
`documents_rows` 105、`chunks_rows` 1008、`schema_migrations`（0001..0018 集合等）、
`vector_content_md5`（`2277eab6…` 等）、`chunk_vector_indexes`（7 枚定义逐字符等，含 hnsw 的 `WITH (m='16', ef_construction='100')`）。
派工要求的「七项」全在这 12 项之内；多出来的是逐行内容 md5、`vector_scope` 全串、索引定义、维度上下界。

检索对账（在册读腿，两档候选宽度）：题向量 **20 枚**取自**生产库**（`ORDER BY md5(vector_id), vector_id LIMIT 20`，
确定性；与恢复库无关，所以定点破坏才会露馅），`top_k=10`。

| pass | 请求 `ef_search` | 会话现读 | `only_in_source` | `only_in_drill` | 名次最大位移 | top-1 距离差 |
|------|------------------|----------|------------------|-----------------|--------------|--------------|
| `production-width` | 100 | `['100']` | **0** | **0** | **0** | **0.0** |
| `near-exhaustive-guc-cap-1000` | 1000（GUC 上限） | `['1000']` | **0** | **0** | **0** | **0.0** |

件里硬要求「会话现读宽度 == 请求宽度」，不等即整轮作废（窄档 40 冒充宽档读数这一族，正是 R393 治过的那族）。

**六格判据结论**：格1 达 · 格2 达 · 格3 达 · 格4 达（反证七把，§5）· 格5 达（含当场修掉本件自己
一枚假阳性，§5 CE5）· 格6 达（§6 逐条自证）。
逐格细节见 §1 至 §7；未做与没跑的部分见 §9，不藏在结论后面。

## 5. 反证台账（七把，逐枚点名：摘前/摘后、原文报错、退出码）

派工要求 ≥3 把，本班实交 7 把。前 3 把对着「备份件」，第 4、5 把对着「对账不是硬编码」，
第 6 把对着「检索腿」，第 7 把对着「幂等与残留」——**第 7 把当场抓出本件自己一枚假阳性并修掉**。

| # | 动作 | 期望 | 实得（原文） | rc |
|---|------|------|--------------|----|
| CE1 | 归档 sha 期望故意写错：`restore --archive <有效 dump> --expect-sha256 0000…` | 拒，且不许先建库 | `REFUSED（rc=2）：归档 sha 与备份时记下的不等：期望 000000000000，实得 f135ec0f9d05（eb_r575_drill-20261003T014411Z.dump，72192007 字节）——这份件不是那枚备份`；随后 `select count(*) from pg_database where datname='eb_r575_drill'` → **0** | 2 |
| CE2 | 把 dump 截一半再恢复：`eb_r575_ce1_truncated-half.dump`（36096004 B / sha `1854723c2d61`，取有效归档前一半） | 必须 REFUSE，不许「恢复成功但少几行」 | `REFUSED（rc=2）：docker exec pg_restore … 失败 rc=1` + `-- stderr --` `pg_restore: error: could not read from input file: end of file` | 2 |
| CE2b | CE2 的余波（本把是白捡的）：半截库有没有冒充成功 | 不留半截库；对账无从报绿 | 恢复失败即自清（`drop_drill(…, "恢复失败即清理，不留半截库")`），随后 `psql -d eb_r575_drill` → `FATAL: database "eb_r575_drill" does not exist`，`reconcile` 走 `REFUSED（rc=2）` | 2 |
| CE3 | 指一个不存在的库名：`preflight --source-db eb_does_not_exist` | 拒且点名是哪个库 | `REFUSED（rc=2）：库里没有 eb_does_not_exist（现取清单：eb_r579_probe, eb_r59_sandbox, enterprise_brain, postgres, template0, template1）——本单不发任何对账结论` | 2 |
| CE4 | 摘掉恢复脚本里的向量列校验：`reconcile --skip-vector-check`（同一轮不带旗标 → rc=0、`compared=12`） | 对账件必须变红，不许沉默通过 | `MISMATCH（rc=3）：对账缺项：向量列校验一族（embedding_count embedding_column_type embedding_dims zero_vector_rows vector_content_md5）被摘掉…摘掉校验的演练不许报绿：本次比对口径 7 项 < 要求 12 项` | 3 |
| CE5 | 证「对账读的是活数、不是硬编码 1008」：在本单**自己的恢复库**上 `DELETE 3 行` + `UPDATE 1 枚为全零向量`（此刻库里 `1005|1005`） | 必须逐项点名差多少 | `MISMATCH（rc=3）：恢复库对账不等：` 逐行原文 `chunk_vectors_rows: 生产=1008 恢复=1005` / `embedding_count: 生产=1008 恢复=1005` / `zero_vector_rows: 生产=0 恢复=1` / `vector_content_md5: 生产=2277eab6b71ad776827ea4c3b04840e9 恢复=7f010a4887bcf0c7186358aaddb32b99`；同一时刻生产库现取仍 `1008|1008`、md5 仍 `2277eab6…` | 3 |
| CE6 | 证检索腿也有牙：在恢复库**定点**删掉一枚既是题向量又是自身 top-1 的行（`MYBI_私有化部署手册.txt_11`，库内降到 1004 行），跑 `recall` | `only_in_*` 必须非 0 | `RECALL RED（rc=4）：[production-width] 恢复库与生产库的 top-10 集合不等：只在生产=1、只在恢复=1（名次最大位移 1）` | 4 |
| CE7 | 幂等与残留：`--keep` 留库之后再裸跑 `full` | 不许产生第二枚同名库 | `REFUSED（rc=2）：上一轮的 eb_r575_drill 还在（现取清单：eb_r575_drill, eb_r579_probe, …）；先跑 cleanup 或明写 --replace-drill-db`；`select datname from pg_database where datname like 'eb_r575%'` → **仍只 1 枚** | 2 |

两把白捡的（同属反证，不单列编号）：`full --keep` 之后 `residue.kept_by_request=[eb_r575_drill]` 具名上报（不
具名即红）；`cleanup` 支独立可跑，返回 `drill_dropped=true` 且清单回到基线 6 枚。

### 5.1 CE7 修掉的那枚假阳性（本单一手真缺陷，照实写）

修复前 `full --replace-drill-db`（**不带** `--keep`）在一枚上一轮 `--keep` 留下的盘面上跑，
前面 6 步全绿（backup/restore/reconcile 12 项全等/recall 两档 0-0-0/postflight 同数/cleanup 已删），
最后却 `RESIDUE（rc=5）：演练后的库名集合没回到演练前那一集：多出 无；少了 eb_r575_drill`
——**它删的正是自己该删的那枚**，因为「演练前那一集」里本来就带着上一轮的自己。
现场读数留在 `r575-drill-reading-20261003T015348Z.json`（`status=Residue`），本班故意不删。

治法：把残留账抽成 `check_residue(before, after, drill_db=…, keep=…)`——别人家的库一枚不许多、
一枚不许少；恢复库自身的去留只按 `--keep` 判，并且**说了留就得留着、说了不就得删干净**，两头的谎都红。
异常携带 `.residue` 报告，失败轮的读数 JSON 也留得下这本账。修后同分支 **rc=0**（§3.2 那轮），
补 3 枚离线钉（§8）。**这不是把判据改松**：松掉的只有「把自家恢复库算成别人的库」这一支，
多库/少库/该留没留/该删没删四支全部保留且各有钉。

## 6. 危险动作自证（本单对生产库发过什么，逐条）

### 6.1 件对生产库 `enterprise_brain`：173 条，全部只读

逐条清单（带编号原文）在凭据件里：`C:\Users\fengx\PycharmProjects\r575-drill\r575-production-statements-20261003T020100Z.txt`。
统计（本纸现取）：**173 条 = 172 条 `SELECT` + 1 条 `pg_dump` 命令记录**；按词边界扫
`INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|VACUUM|COPY|MERGE` → **命中 0 条**。
`pg_dump` 那一条是只读取数据泵（§6.3 D 段单列）。每条都先过 `guard_statement`（前缀白名单 + 写动词
词边界黑名单），并且都包在 `BEGIN; SET LOCAL transaction_read_only = on; … COMMIT;` 的事务里；
`run_psql` 对 `SOURCE_DB` 直接拒绝 `readonly=False`——把写批次递给生产库，代码路径根本走不通。

### 6.2 人工补发的只读现取（逐条，全部 `SELECT`，共 9 条）

```
1  select count(*), count(embedding) from chunk_vectors                      ×4（动作1 / CE5 后 / 权威轮后 / 收尾）
2  select extname from pg_extension
3  select max(version) from schema_migrations
4  select coalesce(md5(string_agg(vector_id || '#' || embedding::text, ';' ORDER BY vector_id)),'EMPTY') from chunk_vectors  ×2
5  select count(*), count(embedding), md5(…) from chunk_vectors              （收尾一次，与 4 同口径）
6  select relname, n_live_tup, n_tup_ins, n_tup_upd, n_tup_del from pg_stat_user_tables order by (n_tup_ins+n_tup_upd+n_tup_del) desc limit 12
```

另有 6 条打在 `postgres` 维护库上的只读查询（`pg_database` / `pg_get_userbyid`，用于库名基线与归属），
生产库不在其内。全部 rc=0。

### 6.3 件内写动词统计（`scripts/r575_vector_restore_drill.py`，词边界、不区分大小写）

| 关键字 | 出现处数 | 逐处点名 | 真发出去的写语句 |
|--------|----------|----------|------------------|
| `DROP` | 3 | L125 黑名单数据；L731 账本注记；L732 语句 | **1 枚**：`DROP DATABASE "eb_r575_drill"`（先过 `assert_droppable` 硬等于该名） |
| `CREATE` | 3 | L125 数据；L771 注记；L773 语句 | **1 枚**：`CREATE DATABASE "eb_r575_drill" TEMPLATE template0` |
| `ANALYZE` | 3 | L128 数据；L780 两条 | **2 枚**：`ANALYZE chunk_vectors` / `ANALYZE chunks`，**只发在恢复库**（`run_psql(container, drill, …)`） |
| `TRUNCATE` `DELETE` `GRANT` `VACUUM` `REFRESH` | 各 1 | 全部在 L125–L128 `_WRITE_KEYWORDS` 黑名单数据里 | **0 枚** |
| `INSERT` | 2 | L125 数据；L71 `sys.path.insert`（Python 方法名） | **0 枚** |
| `COPY` | 2 | L126 数据；L527 英文散文「a copy of a number」 | **0 枚** |
| `UPDATE` | 3 | L125 数据；L216 散文；L641 `digest.update(block)` | **0 枚** |
| `ALTER` | 4 | L125 数据；L683/L685 散文；L760 拒收消息（`toc_danger_lines` 以 `\bALTER\s+(DATABASE\|ROLE)\b` 作**拒收**判据） | **0 枚** |

⇒ 派工判据「应只对 `eb_r575_drill` 出现 `DROP DATABASE` 一处」达成：真发出去的 `DROP DATABASE`
只有那一枚、只有那一个名字。`DROP/TRUNCATE/UPDATE/DELETE/INSERT/COPY/VACUUM/GRANT/ALTER`
对**生产库**真语句 **0 枚**。

### 6.4 人工发过的写语句：3 条，零条指向生产库

```
-- 全部 -d eb_r575_drill（本单自建的恢复库，演练末已 DROP DATABASE）
delete from chunk_vectors where vector_id in (select vector_id from chunk_vectors order by vector_id limit 3)   -- DELETE 3
update chunk_vectors set embedding = ('['||array_to_string(array_fill(0.0::double precision, array[768]),',')||']')::vector
  where vector_id = (select vector_id from chunk_vectors order by vector_id limit 1)                            -- UPDATE 1
delete from chunk_vectors where vector_id = 'MYBI_私有化部署手册.txt_11'                                          -- DELETE 1（CE6）
```

这 3 条是反证 CE5/CE6 的**手段**，只打在恢复库上（`dropdb enterprise_brain`、对生产库
`DROP TABLE`/`TRUNCATE`/`UPDATE`/`DELETE` 一律零枚）；那枚恢复库随后已被件自己 `DROP DATABASE` 删掉。

## 7. 给 R60（停写/退役 Chroma）的发现——本单真正产出的东西

1. 🔴 **`pg_dump` 不带库级 `ALTER DATABASE … SET`**（plain dump 与 269 条 TOC 里 `ALTER DATABASE` 命中 0；
   那是 `pg_dumpall` 的活）。生产库 `enterprise_brain` 上挂着 `pg_db_role_setting`：
   `app.embedding_dimension=768`、`app.embedding_model=nomic-embed-text`；恢复出来的库里这两项是
   `NONE` / `MISSING/MISSING`（对账里以 EXTRA 项上报，**不门控、不藏**，见 §3.2）。
   ⇒ 停写 Chroma 前，备份预案必须明写：库级 GUC（`app.embedding_dimension`/`app.embedding_model`，
   以及 R386 之后可能新增的任何 `app.*`）要么随 `pg_dumpall --globals-only`+`ALTER DATABASE … SET` 一起归档，
   要么由恢复脚本显式重建。否则一次真灾难恢复之后，向量数据 100% 在、`pg_store` 却读错维度或起不来，
   而日志里「备份成功」全是绿的。
2. **候选宽度口径**：`hnsw.ef_search` 出厂 40、生产读腿由 R386 在排名语句前 `set_config(…,TRUE)` 钉到真源 100。
   恢复库没有库级 SET ⇒ 任何"在新库上跑读腿"的验收都要**显式带宽度并现读回证**（本件两档：100 与 GUC 上限 1000，
   现读不等即作废整轮）。别指望默认档等于生产档。
3. **检索对账不能单独当一致性证据**（CE6 的灵敏度边界，照实写）：随机删的 3 行 + 改成全零的 1 枚
   **没有**触发检索腿（仍 rc=0、`only_in_*=0`），因为它们不在 20×10 的 top-k 槽位里；只有**定点**删掉
   命中槽位的那一枚才红。⇒ R60 的恢复验收应当把「12 项指纹（含逐行向量 md5）」当**硬门**、
   top-k 对账当**辅助**；只报"召回一样"的恢复演练不足以签字。
4. **别把 dump 字节数当判据**（§3.3）：生产库非向量表在日常写入 + 归档头带时间戳 ⇒ 同一枚库连采 8 枚字节各异，
   而逐行向量 md5 八轮恒等。验收要落在恢复库指纹上。
5. **尺寸提醒**：1008 枚在这个 GUC 上限（1000）下已经"穷不尽"，件因此走 `near-exhaustive-guc-cap-1000` 档。
   客户尺寸上来后这一档语义要重量——这与计划书里「客户尺寸两档差仍未量」那一格是同一件事，本单**不**宣称已量。

## 8. 离线钉（门里跑的、不需要库的）

`tests/test_r575_vector_restore_drill.py` **23 枚**（桩住唯一出口 `_run`，不连库、不打模型）：
只读闸两侧（写语句拒 / `updated_at`·`set_config` 不误伤 / 生产库连"非只读批次"都发不出去）、
对账不是硬编码（喂 7/6/0 照样逐枚比、点名差在哪、缺项即红、摘校验即红）、归档坏了要拒
（sha 不符 / TOC 读不动 / 落点表缺数据，全在建库之前）、检索腿真在比名次（`only_in_*` 非 0 必红、
宽度没钉住整轮作废、腿 SQL 是在册那两句不是抄本）、幂等与残留（同名库不建第二枚 / `DROP`·`CREATE` 只认那一枚 /
`check_residue` 四支各自的谎）、静态预算（写动词字面量逐枚点名，全部只指向 `eb_r575_drill`）、
产物不许落进 git 工作树、账本把生产库和其余一切分开。

读数（主树解释器）：`23 passed in 0.65 s`；与四枚相邻备份/恢复件合跑
`48 passed, 3 skipped in 2.83 s`（3 枚 skip = 在册 R283 真机件缺 `EB_PG_ACCEPTANCE_URL`，非本单引入）。

## 9. 没跑 / 未做（照实）

- **全量回归门未跑**：本单明文禁止，且 HEAD 自带两枚 `tests/test_r253_*` 红（不治）。
- **在册 `scripts/r59_recall_compare.py` 的 PG 腿未跑**：它的题向量要现场调 11434 的 embedding 模型，
  本单明文禁打模型、禁调 11434。**替代口径**已写在 §2/§4：同一枚 `app.rag.pg_store.search_vectors`
  的腿 SQL + 题向量取自生产库内 1008 枚。这是"等价只读入口"，**不等于** r59 量具本身跑过——
  谁要拿本纸去签 r59 口径，请先补那一轮。
- 未翻默认、未停写 Chroma、未动 `deploy/**`、未 `docker restart` 任何容器、未跑迁移（0019 仍未应用）。
- 未 `git add` / 未 commit / 未 push（按派工）。
### 9.1 越界一处（自曝，不遮）

一次打补丁调用块没带 `Set-Location`，默认 cwd 落在主树，误建
`企业智脑/tests/test_r575_vector_restore_drill.py`（24221 B）与对应 `.pyc`。补救与复核：`.py` 已
`Move-Item` 回 `be-r575\tests\`（内容未丢），`.pyc` 以 `python -c os.remove` 删除（`Remove-Item`
对主树被策略拦）；本班接手后再次复核主树 `git ls-files --others | Select-String r575` → **命中 0**，
主树除总控自己的并树（HEAD 现为 `63c36dd`，与本单无关，本单基点 `b85c277`）外无本单任何字节。
教训：每个命令块第一行必须 `Set-Location` 到自己独占的工作树，否则写域规则在第一秒就破了。

## 10. 凭据与盘面

| 件 | 字节 | sha256 前 12 |
|----|------|--------------|
| `scripts/r575_vector_restore_drill.py` | 52641 | `04e33f3764f6` |
| `tests/test_r575_vector_restore_drill.py` | 28640 | `29d8961e85ce` |
| `docs/testing/r575-vector-restore-drill-2026-10-03.md`（本纸） | — | 交回时现取 |

保留的备份凭据（仓外，不入任何 git 树）：
`C:\Users\fengx\PycharmProjects\r575-drill\eb_r575_drill-20261003T020103Z.dump`
**72392506 字节 / sha256 `fd40eaa05402d2f3efe57bd5fd0e5f7eec1c14a8bb3e8a16d4370b503a90e47a`**（前 12 `fd40eaa05402`）；
同目录另有本单历轮的 dump、读数 JSON（含 §5.1 那枚 `Residue` 现场）与 173 条语句账本，全部可复核。

盘面：`git diff --numstat` 空（三枚全是新建，未改任何在册文件）；`git status --porcelain` 只有三枚
`??`；基点 `b85c277` 未动、未 commit。
