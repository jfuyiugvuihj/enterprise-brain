# R648 · R46 判据① 从「离线形状」升到「真库读数」

* 工单：R648（派工代号 R46 现在做），基点 `f0c4572`，独占工作树 `be-r648`
* 量具：`scripts/r648_real_pg_gauge.py`（默认一枚库都不连，真腿靠 `R648_REAL_PG=on`）
* 同名件：`tests/test_r648_gauge_default_off.py`、`tests/test_r648_real_pg_concurrency.py`、
  `tests/test_r648_real_order_bound.py`、`tests/test_r648_counter_evidence_teeth.py`
  （共用夹具 `tests/_r648_gauge_harness.py`）
* 读数时刻：2026-10-04 22:3x（Asia/Shanghai），真腿全程 `docker exec` 进容器，零 recreate、零镜像重建
* 🔴 本文所有坐标一律 `文件::符号`，不抄行号；命令原文逐枚抄自量具产物（`run_report` 的
  `commands` 段），不在纸上手抄第二份

## 0. 这单欠的是哪一格

R46 的代码三棒全部在树：后端半张 R152（施工 `c29ccf5`／并树 `eaa9af8`，含
`migrations/0011_document_activity_signals.sql`）、消费侧 R195（并树 `484536c`）、强度校准 R153
（并树随附笔 `3a5c24b`）。欠账只剩判据①的**证据面**：`app/rag/retriever.py::activity_priors` 与
`app/rag/retriever.py::rank_hits_by_activity` 的读回与界，历史上全部打在假 `row_reader` 上；
在册 R525 到真库里量到的那一格是「0 行 ⇒ 无可读」（`docs/testing/r525-activity-prior-real-store-2026-09-30.md`）。
⇒ **真 PG 上的并发打点与真检索次序，从立案到今天一次都没量过**。本单只补这两条腿，
不改界、不改算术、不改账尺（界仍由 `scripts/r648_real_pg_gauge.py::R153_BOOKED_MAX_SHIFT_RANKS`
钉死为 1 枚名次）。

## 1. 打的是哪台 PG（派工词第 3 条点名的三枚读数）

| 读数 | 值 | 出处 |
| --- | --- | --- |
| `SELECT current_database()` | `eb_r59_sandbox` | `scripts/r648_real_pg_gauge.py::leg_identity`（rc=0） |
| `inet_server_addr()` / `inet_server_port()` | `127.0.0.1/32` / `5432` | 同上（rc=0，容器内 TCP 姿势） |
| `SHOW server_version` | `16.15 (Debian 16.15-1.pgdg12+2)` | 同上（rc=0） |
| 数据目录 | `/var/lib/postgresql/data` | 同上（rc=0） |
| `pg_postmaster_start_time()` | `2026-10-04 08:02:04.14819+00` | 同上（rc=0） |
| 同姿势的 socket 对照 | `inet_server_addr()`/`port()` 恒 `NULL` | `leg_identity`（rc=0） ⇒ 自证必须走 TCP，socket 姿势等于没自证 |

与在册容器口径的对账（三枚都上）：

* 容器名取自 `scripts/r525_activity_prior_readout.py`（`CONTAINER`），面 A 那台 PG 就是它；
  R525 在册记的 `vector_scope` 是 `1|nomic-embed-text|768|l2|16|100`，本件现读同一枚库交回
  `embedding_model=nomic-embed-text / dimension=768 / distance_function=l2 / schema_version=1`
  （`scripts/r648_real_pg_gauge.py::read_vector_scope`，rc=0）⇒ 对得上。
* 🔴 野 PG 那一坑的机器凭据：`docker inspect enterprise-brain-postgres-1 --format
  '{{json .HostConfig.PortBindings}}'` 交回 `{}`（rc=0）⇒ 容器 PG **没有发布宿主端口**，
  宿主 `5432` 上 listened 的那枚（本机现读为原生 `postgres` 进程，PID 9868）一定是**另一台服务器**。
  所以本件唯一的真连接通道是 `docker exec ... psql -h 127.0.0.1`，宿主 psycopg 直连 5432
  得到的（`fe_sendauth: no password supplied`／R525 面 B 连 `schema_migrations` 都没有）一律按假绿处理。
* 同一台服务器上 `eb_r59_sandbox` 与 `enterprise_brain` 并列在册（`pg_database` 现读五枚：
  `eb_r59_sandbox / enterprise_brain / postgres / template0 / template1`）⇒ 库名选错就是打到生产，
  所以 `scripts/r648_real_pg_gauge.py::assert_sandbox_database` 在连库之前就把生产库名按名字拒了
  （原因码 `production_database_refused`，`tests/test_r648_gauge_default_off.py::
  test_production_database_names_are_refused_before_any_connection` 不连库就验）。

## 2. 判据①① 真库并发腿：逐列精确相加、零丢更新

形状：8 枚真连接（8 个不同 `pg_backend_pid()`）同时对同一枚假名 `r648_concurrency_primary.md`
各打 10 笔**产品自己的那条 UPSERT**（`app/api/v1/feedback.py::_UPSERT_SQL` 原文渲染，量具里没有
第二份文本，由 `tests/test_r648_gauge_default_off.py::
test_the_gauge_sends_the_products_own_statements_and_no_second_copy` 钉住）。

| 读数 | 值 |
| --- | --- |
| 打点前该行的基数 | `accepted_count=0 / rejected_count=0`（`rows_before_wave`） |
| 该有多少 | `80 / 80`（`sessions × statements_per_session` 逐列） |
| 库里现读到 | `80 / 80` |
| 丢更新清单 | `[]`（逐列对平，缺 0 枚） |
| 同一时刻在打的真后端 | `concurrent_backends=8`（第三枚连接现读 `pg_stat_activity`，`client backend`、排除自己、`state <> 'idle'`） |
| `backend pid` 逐枚 | 8 枚互不相同（`distinct_backend_pids=8`） |
| 行数 | `row_count=1`（`filename` 是 PK ⇒ 一行不多一行不少） |
| 八枚会话 rc | `[0,0,0,0,0,0,0,0]` ⇒ 没有任何一枚靠报错躲过对账 |

**同一套判据打在「客户端先 SELECT、再 UPDATE 回去」那一族上必须红**（K1 的对照腿，
`scripts/r648_real_pg_gauge.py::leg_read_then_write_control`，两枚真连接按 0.4 s 错开、
都在对方提交之前读到基数）：

| 读数 | 值 |
| --- | --- |
| 两枚会话各自报回的基数 | 都是 `1 / 0`（`both_sessions_read_the_same_base=True` ⇒ 陈旧读在客户端手里，是现读的、不是推断的） |
| 该有多少 | `2 / 1`（S_A 只加采纳、S_B 只加驳回） |
| 库里现读到 | `1 / 1` |
| 丢更新 | `accepted_count`：该 2 实 1（缺 1） |
| 点名 | `victim_session=S_A`、`overwritten_by_session=S_B`、`actually_landed=0`、`expected_landed=1` |
| 两枚会话 rc | `[0, 0]` ⇒ 丢的是更新，不是连接 |

⇒ 那枚「零丢更新」不是「psql 没报错」的同义词：判据在同一批真连接上量得出丢更新，才配说 UPSERT 那一族零丢。
## 3. 两列不许被做成一枚净值（迁移注释那句「0/0 与 5/5 是两件事」的真读数）

`scripts/r648_real_pg_gauge.py::leg_mixed_columns`：4 枚真连接同时打同一枚假名，偶数席位只加采纳、
奇数席位只加驳回，各 6 笔 ⇒ **净值恰好为 0 而两列都非零**。

| 读数 | 值 |
| --- | --- |
| 该有多少 / 现读到 | `12 / 12` 对 `12 / 12`（`lost_updates=[]`） |
| `accepted_count - rejected_count` | `0`（`net_value`）——净值一列的方案在这一格会直接吐出一个 0 |
| 走产品读腿折回来的先验 | `{"accepted": 12, "rejected": 12}`（`app/rag/retriever.py::activity_priors` + 那条 SELECT 原文） |
| 同一台库里没打过点的假名 | 不在先验字典里（`unmarked_row_absent_from_priors=True`）⇒ 「没打过点」与「一人一半」读出来就是两枚形状 |
| 分值 | `activity_prior_value(12/12)=0.0`、`(0/0)=0.0`、`(无)=0.0` ⇒ 分开记买到的是**可分辨**，不是另一档权重（与 R153 的口径一致，本单一字未改） |

## 4. 时间戳与约束

`leg_timestamps`（一次播种 + 三波打点，四枚快照）：

| 读数 | 值 |
| --- | --- |
| `first_signal_at` | 四枚快照同一毫秒（`first_signal_at_constant=True`、`first_signal_at_rewritten=False`） |
| `last_signal_at` | 逐波严格向前（`last_signal_at_monotonic_non_decreasing=True`，`max_backwards_step_ms=0`） |
| `last >= first` | 成立（`last_at_least_first=True`） |
| 静态对照 | 产品那条 UPSERT 的 `DO UPDATE SET` 子句里**没有** `first_signal_at`（`product_upsert_touches_first_signal_at=False`）⇒ 动态读数与语句文本互相咬住 |
| 逐列对平 | `7 / 3` 对 `7 / 3`（`lost_updates=[]`） |

`leg_constraints`（0011 那几道约束在真库里拦不拦）：

| 读数 | 值 |
| --- | --- |
| 打 `(r648_probe_zero_zero.md, 0, 0)` | `rc=3`，stderr 点名 `document_activity_signals_not_empty_check`，`DETAIL: Failing row contains (…, 0, 0, …)` |
| 被拦之后那一行的行数 | `0`（`rows_after_refusal`）⇒「长度为 0 的行不留」不是纸上的话 |
| 真库约束台账 | 5 枚：PK + 4 枚 CHECK，全部 `convalidated=true`，`primary_key_count=1`，未验证清单为空 |
| 与在册 `migrations/0011_document_activity_signals.sql` 对平 | `booked_names_missing_live=[]`（四枚 CHECK 名字逐枚对上；PK 由 `filename TEXT PRIMARY KEY` 内联产生，所以台账比在册点名多它一枚） |

## 5. 判据①② 真次序腿：界在真数据上成立（5 / 12 / 40 三档各测）

名次来源（全部真库、只读）：`eb_r59_sandbox` 的 `chunk_vectors`（1008 枚 / 100 篇）上真 ANN 回来的
top-40。排名语句不是本件写的——由 `app/rag/pg_store.py::search_vectors` 自己交回（量具用一枚记录型
连接把它的语句与参数抓下来再渲染），同一笔事务里由 `app/rag/pg_store.py::_apply_hnsw_ef_search`
把候选宽度钉到 `app/rag/pg_store.py::configured_hnsw_ef_search()`（现读 `ef_search_width=100`）。
查询向量是定种子随机数（seed `20261004`，🔴 本单不许打模型，Ollama 一字节都没碰）。
`ranking_statement_sha256=4d9381427788effe`（16106 字符，经 stdin 送进 psql，不进命令行）。

| 腿宽 | 真库先验下的最大位移 | 被挪动的命中 | 钉死的界 | 界常量（未改） | 无信号交回同一对象 | 窗口内不同文档 |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 1 | 2 | 1 | 1 | 是 | 2 |
| 12 | 1 | 6 | 1 | 1 | 是 | 5 |
| 40 | 1 | 22 | 1 | 1 | 是 | 8 |

* 先验是在库里真打过点、再走产品那条 SELECT 读回来的：`r648_doc01.md=10/7`（净 3 ⇒ `shift_ranks=0.3`）、
  `r648_doc03.md=1/0`（`0.5`）、`r648_doc04.md=0/4`（**只有驳回** ⇒ `shift_ranks=-1.0`，夹在界的负侧）。
  界的负侧也有真读数：40 那一档量到 `places_moved=-1` 的位移，`min=-1`，一枚都不越界。
* 集中度是真库形状：那篇独占 40 席中的 **27** 席 ⇒ 一次打点能同时注记 27 枚命中（放大率的真凭据，
  由 `tests/test_r648_real_order_bound.py::
  test_the_window_is_concentrated_enough_that_one_document_can_move_many_seats` 钉住）。
* 🔴 唯一不是原文的一格：`filename` 经**单射**改名成 `r648_` 假名（写域只准假名，见 §7）。改名一对一，
  名次、距离、「同篇占几席」的集中度一个字没动——那三样才是位移算术的输入；正文换成占位串后
  `moves` 逐枚不变（`test_the_prior_never_reads_the_chunk_text`），所以「先验只读计数」也被顺手证了。
* 40 行距离严格递增、40 枚互不相同 ⇒ 这份快照只能是 ANN 回来的；`rows_seen_by_product_reader=7`
  与本单真写过的 7 枚假名逐枚对平。

## 6. 出厂默认关：未量到就说未量到

不设 `R648_REAL_PG` 时（`tests/test_r648_gauge_default_off.py`，21 枚用例，1.5 s，零子进程）：

* 九枚腿逐枚回 `status="unmeasured"` + `reason_code="r648_real_pg_opt_in_not_declared"`，`transport_calls=0`；
* 🔴 未量到的格子里**一个测量键都没有**（`walk_measurement_keys` 数出来是空）——伪 0 没有落点；
* 同名件里**没有一枚 `skip`／`xfail`**：`test_the_live_*` 那一族在关着的时候判的是「这一格回的是未量到 + 原因码」，
  开着的时候判的是「真读数与在册快照逐格相等」；
* 绊线（`tests/_r648_gauge_harness.py::Tripwire`）装在量具唯一的子进程出口上：默认态响 0 枚，
  闸门一开就响 ⇒ 上那一枚 0 是真读数，不是空炮。

## 7. 写域与清账

* 写点只有 `document_activity_signals` 一张表、只有 `r648_` 前缀假名；每条写脚本先过
  `scripts/r648_real_pg_gauge.py::assert_write_script_allowed`（禁词表、表名、假名形状三道），
  只读腿过 `assert_select_only` / `assert_read_script_allowed`。
* 本单真写过的假名 7 枚，逐枚点名：`r648_concurrency_primary.md`、`r648_control_read_then_write.md`、
  `r648_mixed_columns.md`、`r648_timestamps.md`、`r648_doc01.md`、`r648_doc03.md`、`r648_doc04.md`。
  `r648_never_marked.md`（缺席对照）与 `r648_probe_zero_zero.md`（被 CHECK 拦下的那一笔）
  一格都没落库。
* 清账：`leg_cleanup` 交回 `DELETE 7`、`r648_rows_after=0`、`row_count=0`、
  `rows_returned_to_original=True`；`document_activity_signals` 与 `chunk_vectors` 开跑前后都是
  原样（开跑前那张表就是 0 行，见 `leg_baseline`）。收席时（本文最后一节）再现读一次。
* 禁区一字节没动：`migrations/**` 只读它的文本（`booked_0011_constraint_names`），
  `app/**` 只读源码 AST，`deploy/**`、`.env*`、`frontend/**`、`docs/handoff/**`、评测夹具、
  `scripts/run_gate.py`、`pyproject.toml` 全没碰；没建库、没 `docker build`、没 `docker restart/recreate`、
  没打模型、没起服务。

## 8. 命令原文（逐枚抄自 `run_report` 的 `commands` 段）

`-f -` 那几枚的脚本正文走 stdin（含 16 k 字符的排名语句与打点批次），不进 argv；
其 sha 与字符数记在 `leg_order` 的 `provenance` 里。凭据一个字都不在命令里：容器内 psql 走
trust 认证，argv 没有口令。

下表共 **56 枚**命令，与快照 `booked_full.json` 里的 `transport_calls=56` 逐枚相等（枚数由
`scripts/r648_real_pg_gauge.py::run_report` 现记，正文由脚本从同一枚快照直填进本文，不手抄、不截断）。

```text
### leg=identity  (5 枚命令，全文不截断，抄自 booked_full.json)
# leg=identity_tcp rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT current_database() AS database, inet_server_addr()::text AS inet_addr, inet_server_port()::text AS inet_port, current_setting('server_version') AS server_version, current_setting('data_directory') AS data_directory, pg_postmaster_start_time()::text AS postmaster_start, pg_backend_pid()::text AS backend_pid) t"

# leg=identity_socket rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT current_database() AS database, coalesce(inet_server_addr()::text,'NULL') AS inet_addr, coalesce(inet_server_port()::text,'NULL') AS inet_port, pg_backend_pid()::text AS backend_pid) t"

# leg=identity_show rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SHOW server_version"

# leg=identity_ports rc=0 stderr=''
docker inspect enterprise-brain-postgres-1 --format "{{json .HostConfig.PortBindings}}"

# leg=identity_databases rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT datname FROM pg_database ORDER BY 1"


### leg=baseline  (2 枚命令，全文不截断，抄自 booked_full.json)
# leg=baseline_total rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals"

# leg=count rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals WHERE filename LIKE 'r648\_%'"


### leg=concurrency  (13 枚命令，全文不截断，抄自 booked_full.json)
# leg=reset_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=readback rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, first_signal_at, last_signal_at FROM document_activity_signals WHERE filename = 'r648_concurrency_primary.md') t"

# leg=concurrency_observe rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM pg_stat_activity WHERE datname = 'eb_r59_sandbox' AND backend_type = 'client backend' AND pid <> pg_backend_pid() AND state <> 'idle'"

# leg=concurrency_s1 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s3 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s2 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s0 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s5 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s7 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s4 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=concurrency_s6 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=readback rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, first_signal_at, last_signal_at FROM document_activity_signals WHERE filename = 'r648_concurrency_primary.md') t"

# leg=concurrency_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals WHERE filename = 'r648_concurrency_primary.md'"


### leg=read_then_write  (7 枚命令，全文不截断，抄自 booked_full.json)
# leg=reset_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=rmw_seed rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=readback rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, first_signal_at, last_signal_at FROM document_activity_signals WHERE filename = 'r648_control_read_then_write.md') t"

# leg=rmw_observe rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM pg_stat_activity WHERE datname = 'eb_r59_sandbox' AND backend_type = 'client backend' AND pid <> pg_backend_pid() AND state <> 'idle'"

# leg=rmw_s0 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=rmw_s1 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=readback rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, first_signal_at, last_signal_at FROM document_activity_signals WHERE filename = 'r648_control_read_then_write.md') t"


### leg=mixed_columns  (8 枚命令，全文不截断，抄自 booked_full.json)
# leg=reset_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=mixed_observe rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM pg_stat_activity WHERE datname = 'eb_r59_sandbox' AND backend_type = 'client backend' AND pid <> pg_backend_pid() AND state <> 'idle'"

# leg=mixed_s1 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=mixed_s2 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=mixed_s3 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=mixed_s0 rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=readback rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, first_signal_at, last_signal_at FROM document_activity_signals WHERE filename = 'r648_mixed_columns.md') t"

# leg=product_select rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT filename, accepted_count, rejected_count FROM document_activity_signals"


### leg=timestamps  (9 枚命令，全文不截断，抄自 booked_full.json)
# leg=reset_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=timestamps_seed rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=timestamps rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, floor(extract(epoch from first_signal_at) * 1000)::bigint AS first_ms, floor(extract(epoch from last_signal_at) * 1000)::bigint AS last_ms FROM document_activity_signals WHERE filename = 'r648_timestamps.md') t"

# leg=timestamps_wave rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=timestamps rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, floor(extract(epoch from first_signal_at) * 1000)::bigint AS first_ms, floor(extract(epoch from last_signal_at) * 1000)::bigint AS last_ms FROM document_activity_signals WHERE filename = 'r648_timestamps.md') t"

# leg=timestamps_wave rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=timestamps rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, floor(extract(epoch from first_signal_at) * 1000)::bigint AS first_ms, floor(extract(epoch from last_signal_at) * 1000)::bigint AS last_ms FROM document_activity_signals WHERE filename = 'r648_timestamps.md') t"

# leg=timestamps_wave rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=timestamps rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT filename, accepted_count, rejected_count, floor(extract(epoch from first_signal_at) * 1000)::bigint AS first_ms, floor(extract(epoch from last_signal_at) * 1000)::bigint AS last_ms FROM document_activity_signals WHERE filename = 'r648_timestamps.md') t"


### leg=constraints  (4 枚命令，全文不截断，抄自 booked_full.json)
# leg=reset_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=constraints_zero_zero rc=3 stderr='psql:<stdin>:2: ERROR:  new row for relation "document_activity_signals" violates check constraint "document_activity_signals_not_empty_check"\nDETAIL:  Failing row contains (r648_probe_zero_zero.md, 0, 0, 2026-10-04 14:33:19.319968+00, 2026-10-04 14:33:19.319968+00).'
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=constraints_inventory rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT conname, contype, convalidated FROM pg_constraint WHERE conrelid = 'document_activity_signals'::regclass ORDER BY conname) t"

# leg=constraints_row rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals WHERE filename = 'r648_probe_zero_zero.md'"


### leg=order  (5 枚命令，全文不截断，抄自 booked_full.json)
# leg=vector_scope rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT row_to_json(t) FROM (SELECT embedding_model, dimension, distance_function, schema_version FROM vector_scope ORDER BY schema_version) t"

# leg=ann_rank rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=reset_rows rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=order_signals rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=product_select rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT filename, accepted_count, rejected_count FROM document_activity_signals"


### leg=cleanup  (3 枚命令，全文不截断，抄自 booked_full.json)
# leg=cleanup_delete rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -f -

# leg=count rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals WHERE filename LIKE 'r648\_%'"

# leg=cleanup_total rc=0 stderr=''
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals"
```
## 9. 反证刀四把 + 正控（`tests/test_r648_counter_evidence_teeth.py`）

影子只在 `tmp_path` 的副本上动手，两份原件（`app/rag/retriever.py`、`scripts/r648_real_pg_gauge.py`）
前后各核一次 sha256；锚点是唯一文本，不含行位（`tests/_r648_gauge_harness.py::load_gauge`、
`::load_retriever_copy`、`::Tripwire`）。

| 刀 | 改了什么 | 结果（真读数） |
| --- | --- | --- |
| K1 读后写 | 打点语句从服务端原子 UPSERT 换成「客户端先 SELECT、睡 0.4/0.9 s、再 UPDATE 回去」 | 同一套判据在真库上红：`accepted_count` 该 2 实 1（缺 1），点名 `victim_session=S_A` 被 `S_B` 覆盖；正控（UPSERT 那一族）同判据空清单 |
| K2 界换成分母 | `app/rag/retriever.py::rank_hits_by_activity` 里「交换轮数 = 界」改成「= 候选条数」 | 在册真库 40 席窗口 + 真库先验当场量出：5 档最大位移 1→2、12 档 1→7、40 档 **1→33** ⇒ 次序腿红并点名「宽度 40 上位移 33 名，超出钉死的 1 名界」。🔴 界由 `R153_BOOKED_MAX_SHIFT_RANKS` 出题，刀改的常量（`bound_constant_in_module` 仍 1）不参与答题——这正是要它红的理由 |
| K3 闸门摸成恒开 | `scripts/r648_real_pg_gauge.py::gate_declared` 改成 `return True` | 绊线响 ≥1 枚（`docker exec ... psql` 被记进 `calls`），且 `identity` 那一格不再是 `unmeasured` ⇒ 「常驻件偷偷连库」当场红；正控同机械响 0 枚 |
| K4 两列折成净值 | `scripts/r648_real_pg_gauge.py::fold_rows_to_priors` 改成 `accepted = max(a-b, 0)`、`rejected = 0` | 库里明明是 12/12，折回来成了 0/0 ⇒ 混排腿判据红（「读回来的两列与库里的两列不等」）。这一刀量的是 §3 那格：净值方案会把「一人一半」洗成「没人打过点」 |

正控（同一套影子机械、`edits=()`）全部绿；同名件在**两态亲跑**下枚数相等、清单逐枚相等：

| 态 | 怎么摆的 | 结果 |
| --- | --- | --- |
| state①（apply 未 commit，本树） | `be-r648` 现盘 | `46 passed in 5.06s`（默认关）/ `46 passed in 27.07s`（`R648_REAL_PG=on` 真腿） |
| state②（干净检出 + 只投本单货） | `git archive f0c4572` 解到 `%TEMP%\r648_state2_a`，只拷 `scripts/r648_real_pg_gauge.py`、`tests/_r648_gauge_harness.py`、四枚 `tests/test_r648_*.py`、本文 | `46 passed in 5.07s`；`--collect-only` 清单与 state① `Compare-Object` diff=0（46 vs 46） |

⇒ 没有一枚钉把「此刻工作树脏不脏」当判据：state② 里 `app/**` 与基点逐字节相同，四枚同名件照样绿。

## 10. 账尺那句该怎么改（`scripts/audit_plan_ticket_ledger.py::LEDGER_EXTRA` 里 R46 那一行，归总控改）

在册现读到的原文是：

```text
"① 真库/真并发次序未证；按 filename 聚合无身份 ⇒ 强度校准另在 R153"
```

🔴 后半句已过期：R153 早已并树（并树随附笔 `3a5c24b`，跟进单 §80 记「四枚并树 R153/R154/R155/R136」），
把它当待办就是把一笔已结的账挂在本单名下。逐字建议（判据① 两腿换成真库读数，同时把**仍未量到的
那一格留在句里**）：

```text
"① 真库两腿已于 R648 量到：8 枚真连接同打一枚 filename 逐列 80/80 零丢更新、行单一枚、0/0 被 0011 的 CHECK 拦下；真库 40 席窗口上位移三档全部 ≤1 名（含负侧），界由 R153 钉死未改（docs/testing/r648-real-pg-concurrency-2026-10-04.md）；🔴 证据面是 eb_r59_sandbox 演示语料 + 合成标签 + 单射改名的假 filename，生产库那张表仍 0 行（R525 在册），客户尺寸与客户隔离不在本单断言内"
```

凭据（逐枚可在册复现）：UPSERT 形状零丢更新的读数、读后写对照点名的 victim、三档位移与集中度、
`ranking_statement_sha256=4d9381427788effe`、`ef_search_width=100`、清账 `DELETE 7` 后行数回 0。
状态位怎么翻由总控裁：本单只交证据，不自称 LANDED。

## 11. 未量到 / 边界（诚实清单，别拿这些当绿）

* 生产库 `enterprise_brain` 的 `document_activity_signals` 本单一字节没碰（禁区）；R525 在册那格
  仍是 0 行 ⇒ **生产侧至今没有真打点**，本单的两腿证据面在沙盒库。翻账不许把这句读成「生产已验」。
* 沙盒是 R59 的演示语料（1008 枚 / 100 篇）+ 252 枚**合成**标签 ⇒ 只证行为，不证客户隔离，
  也不证客户尺寸（计划书 §13 那句改写后的四件可失败判据与本单无关，本单不主张）。
* 名次来自定种子随机向量的真 ANN：查询向量是合成的（本单不许打模型），行、距离、`chunk_index`、
  标签、集中度是真库回来的。本单**不主张**索引腿质量——生产现网那枚「规划器不选 HNSW 索引」的
  在册读数（计划书 §9.3，`idx_scan=0`）不在本单写域，留给 R579。
* 并发量的是「同一枚 filename 上的原子相加 + 单行 PK + CHECK + 两列非净值 + 两枚时间戳」。
  `last_signal_at` 的单调判据按**波次之间**取快照；同一波内多枚并发提交的微秒级先后不在本单断言里
  （`NOW()` 是事务时间戳，本单没去改这个语义）。
* 打点走的是产品那条 `_UPSERT_SQL` 原文渲染成字面量后经 psql 送出，**没有**经过 `app/api/v1/feedback.py`
  的 HTTP 端点（禁区）⇒ 端点侧的请求校验、审计与本单读数无关；API 腿要另量。
* 复跑要真库 + docker：不设 `R648_REAL_PG` 时那两枚 live 用例回的是显式「未量到 + 原因码」，不是 skip。

## 12. 复跑

```powershell
# 默认（零连库，46 枚，约 5 秒）
C:\Users\fengx\PycharmProjects\be-r648\.venv\Scripts\python.exe -m pytest -p no:randomly -q `
  tests/test_r648_gauge_default_off.py tests/test_r648_real_pg_concurrency.py `
  tests/test_r648_real_order_bound.py tests/test_r648_counter_evidence_teeth.py

# 真腿（约 30-45 秒，只打 eb_r59_sandbox，跑完当场清账）
$env:R648_REAL_PG = 'on'
C:\Users\fengx\PycharmProjects\be-r648\.venv\Scripts\python.exe scripts/r648_real_pg_gauge.py `
  --json-out $env:TEMP\r648-readout.json          # 产物必须落仓外（仓内路径当场拒）
```

同名件之外一枚都不跑；`scripts/run_gate.py` 是禁区（本机此刻另有席位在飞），全量回归留给总控。

## 13. 交付前的最后一遍亲跑（转码后复现，本席现取）

§9 那张两态表记的是转 CRLF 之前那一遍。归一之后（7 枚新文件全部 CRLF、无 BOM、控制符
`0x00/07/08/0b/0c` 零枚）本席又亲跑了一遍，枚数与判定一字未变：

| 态 | 怎么跑的 | 结果（现读） |
| --- | --- | --- |
| state① 默认关 | §12 第一段命令，四枚同名件 | `46 passed in 5.30s` |
| state① 真腿 | 同上串，`R648_REAL_PG=on` | `46 passed in 31.01s`（含 K1／K3／K4 三枚 live 反证与当场清账） |
| state② 干净检出 | `%TEMP%\r648_state2_a` 里的同名件，解释器仍取本树 venv | `46 passed in 5.03s` |
| 收集态对平 | 两态各跑一遍 `--collect-only -q` | state① `46 tests collected in 2.79s`／state② `46 tests collected in 2.74s`，清单 diff=0 |
| 出厂默认关的量具 | `python scripts/r648_real_pg_gauge.py --json-out <仓外>` | rc=0、`transport_calls=0`、9 枚腿全部 `unmeasured`（原因码 `r648_real_pg_opt_in_not_declared`） |

清账后的现读（收席那一刻，零写）：

```text
docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT current_database()||' total='||count(*)::text FROM document_activity_signals"
eb_r59_sandbox total=0

docker exec -i enterprise-brain-postgres-1 psql -h 127.0.0.1 -p 5432 -U enterprise_brain -d eb_r59_sandbox -At -v ON_ERROR_STOP=1 -c "SELECT count(*)::text FROM document_activity_signals WHERE filename LIKE 'r648\_%'"
0
```