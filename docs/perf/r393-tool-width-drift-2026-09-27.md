# R393 · 两枚在册量具的候选宽度漂移（2026-09-27）

一句话：**`scripts/r59_recall_compare.py` 与 `scripts/r59c_sandbox_corpus.py` 在 2026-09-27
之前各自带着一枚 HNSW 候选宽度，而它不等于生产读腿钉下去的那一档。凡经这两枚量具取过
的召回/延迟读数，站在哪一档不可知 —— 引用它们必须带下面那句限定，且不许外推到客户尺寸。**

生产向量库口径按定案写：PostgreSQL + PGVector 是生产方案，Chroma 是退役中的遗留件；本单
只动量具的宽度口径，**没有**翻任何默认读后端（`INDEX_BACKEND_DEFAULT` 仍是 chroma，翻不翻
归业主）。

## 1. 实测证据（本班亲跑，全部只读）

取证方式（免密、只读、不落任何写入）：

```
docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -tAX -c "<SQL>"
```

环境：容器 `enterprise-brain-postgres-1`，PostgreSQL 16.15 / pgvector **0.8.6**，
`chunk_vectors` 现 **1008** 枚向量（`select count(*) from chunk_vectors` → `1008`）。

| # | 命令原文（一条会话内按序） | 读数 | 说明 |
|---|---|---|---|
| E1 | `SHOW hnsw.ef_search`（全新会话，此前无任何 vector 语句） | `ERROR: unrecognized configuration parameter "hnsw.ef_search"` | **pgvector 的 GUC 只在库被这条会话用过之后才存在** |
| E2 | `SELECT ... FROM pg_settings WHERE name='hnsw.ef_search'`（未加载时） | `count = 0` | 目录里也没有行 ⇒ 未加载时"读不到"是真的没有 |
| E3 | `SELECT '[1,2]'::vector(2) IS NOT NULL` 之后再读 E1 | `40`（`source=default`、`boot_val=40`、`reset_val=40`、`context=user`、界 `1..1000`） | **出厂档 = 40**，不是 100 |
| E4 | `SELECT indexdef FROM pg_indexes WHERE indexname='chunk_vectors_embedding_idx'` 之后再读 E1 | `40` | 渲染 hnsw 索引定义会调索引 AM 的 handler，**顺带把库加载了** |
| E5 | 同 E4 但只取 btree 索引（`indexname='chunk_vectors_pkey'`）的 indexdef | 仍 `unrecognized` | 证 E4 的因是 hnsw 那一行的 AM handler，不是 `pg_indexes` 本身 |
| E6 | `BEGIN; SELECT set_config('hnsw.ef_search','77',TRUE); ... COMMIT` 之后再读 | 事务内 `77`（`source=session`、`reset_val=40`），提交后回到 `40` | 事务内设定**不残留** |
| E7 | `SET hnsw.ef_search = 88` 之后跨事务再读 | 仍是 `88`（直到 `RESET` 才回 `40`） | **会话级 SET 会一直留在这条连接上**，把后面每一次读数都染成同一档 |
| E8 | 未加载时直接 `SELECT set_config('hnsw.ef_search','100',TRUE)`，再 `SHOW` | `SHOW` 也念回 `100` | 🔴 **占位参数陷阱**：那只是 PostgreSQL 给两段式名字立的占位值，pgvector 根本不读它 |
| E9 | 未加载时先 `set_config(...,'123',TRUE)`，随后 `SELECT NULL::vector IS NULL` 把库带起来，再 `SHOW` | `40` | 占位值在库真加载时被**顶掉** ⇒ 探测必须在设定之前，顺序反了设定就白钉 |
| E10 | 把改完之后那一版批头（`BEGIN;` -> `SELECT NULL::vector IS NULL;` -> `SELECT set_config('hnsw.ef_search','100',TRUE);` -> 一条排名 `SELECT` -> `ROLLBACK;`）用 `psql --csv -f -` 在容器里跑 | 输出顺序：`BEGIN` / `?column?` / `t` / `set_config` / `100` / 表头 / 数据行 / ... / `ROLLBACK`；每回一条排名 `SELECT` 再打一遍自己的表头 | 事务内 `SHOW` = `100`，`ROLLBACK` 之后同一条会话再读 = `40` ⇒ 事务内设定不残留；这一串形状也是 §4 那枚读数解析器的唯一凭据 |

本班在容器里只发过三类只读语句：E1〜E9 那几组取证、E10 那一版批头形状探针、一句 `select count(*) from chunk_vectors`（跑前跑后都是 1008）。零 DDL、零 DML、零写入。一处如实报备：E10 最初是 `docker cp` 进容器 `/tmp/shape.sql` 跑的，跑完已用 `rm -f` 删掉，其后的取证改走 `psql -f -`（stdin），未在容器里再落任何文件。

生产读腿那一侧：R386（落树 `1b4406a`）在排名语句之前、同一笔事务内用
`set_config(..., TRUE)` 钉 `HNSW_EF_SEARCH_DEFAULT = 100`（`app/rag/pg_store.py:663`），
读取点 `configured_hnsw_ef_search()`（`app/rag/pg_store.py:800`）是全仓唯一一枚。
**40（库里出厂档）与 100（生产那一档）不是同一个数** —— 这就是这单的全部内容。

## 2. 量具当时实际做了什么

* `scripts/r59_recall_compare.py`：`--pg-ef-search` 缺省 `0`，help 原文「把 hnsw.ef_search
  设成这个值再跑 live 腿；0 = 用库里的默认」。结合 E3，"库里的默认"就是 40 ⇒ **不显式给值
  时，这一腿量的从来不是生产那一档**。真给值时用的是会话级 `SET`（E7 那一族），残留在连接上。
* 取证格（「这一腿踩在哪套口径上」）：`pg_engine_facts()` 按 `vector_scope` → `pg_indexes`
  → `SHOW` 的顺序发语句，只有第二条**恰好**会加载库（E4），而它一旦失败（表名不同、索引还
  没建、这一格被 except 记账），第三条就当场 `unrecognized`，而那条异常被吞进
  `errors["hnsw_ef_search"]` 字符串、正文留空，读数照印。
  🔴 更正一处转述：本班实测**这条取证格并非"从诞生起就没填过数"** —— 09-24 那份归档产物里它
  填上了，见下表 P1/P2（`"hnsw_ef_search": "40"`、`"errors": {}`）。真话是：**它填上数靠的是
  E4 那一枚不相干的副作用，不是设计**；而它填上的那一格恰好就是 40。
* `scripts/r59c_sandbox_corpus.py`：同一个数被抄了三份（`emit_probe_queries` 的签名默认值、
  生成的 `SET hnsw.ef_search = ...`、CLI `--ef-search` 默认值），生成的探针批以**会话级** `SET`
  开头，跑完整批都留在那条连接上。

## 3. 受影响的历史读数（本仓在档的每一件）

| 件 | 生成者 | 当时那一档的凭据 | 判定 |
|---|---|---|---|
| `docs/testing/r59b-recall-comparison-2026-09-24.json`（`"tool": "scripts/r59_recall_compare.py"`） | r59_recall_compare | 同文件 `"hnsw_ef_search": "40"`、`"errors": {}` | **站在 40**（出厂档），不是生产那一档 |
| `docs/testing/r59b-stability-2026-09-24.json` | r59_recall_compare（R59b build + reachability probe） | 同文件 `"hnsw_ef_search": "40"` | 同上 |
| `docs/testing/r59b-recall-reading-2026-09-24.md` | 人对上面两份的读表 | 原文：「条件是当时会话 `SHOW hnsw.ef_search` = `40`（pgvector 默认值）。本轮没有扫参、没有为了好看把它调大。」 | 同上；同文件已自带一句边界（只在 1008 枚 / k=5 上量到，几万枚没量过，不替它外推） |
| `docs/testing/r59-recall-reading-2026-09-24.md` | r59_recall_compare 的前一遍（该遍结论已作废） | 全文**无**任何候选宽度记录 | **档不可知**（产物里根本没有这一格） |
| 计划书 §9.3 格① 的 84 问读数（`b498c88` 一族）与格④ 的两档实测（R386 `1b4406a`） | 另两件取证脚本，逐笔显式给档 | R386 回执：`ef=40` / `ef=100` 两臂分开跑、每臂同形 `BEGIN; 设定; 排名; ROLLBACK;` | **不受本单影响**（档是显式的），列在这里是为了划清边界 |
| `sql/probes.sql`（`scripts/r59c_sandbox_corpus.py` 的 `plan` 产物） | r59c_sandbox_corpus | 批头写死 `SET hnsw.ef_search = 40` | 任何**在别处**据此批取过的读数按 40 读；本仓查无该批的沙盒读数落档（`docs/testing` 里只有操单第 10.3 步那条待执行的注释）⇒ 是否曾有人在窗内跑过：**未证** |

### 引用时必须原样带上的限定语

> 这份读数出自 R393 之前的 `scripts/r59_recall_compare.py` / `scripts/r59c_sandbox_corpus.py`，
> 它站在 HNSW 的哪一档候选宽度上**不可知**（那一格要么没录，要么录的是 pgvector 的出厂档，
> 而不是生产读腿钉下去的那一档）；它不能当"生产口径下召回不退化"的证据，也**不许外推到客户
> 尺寸**。

## 4. 本单改完之后新的读数长什么样

* 缺省档 = 现场向 `app.rag.pg_store.configured_hnsw_ef_search()` 取（旋钮 `PGVECTOR_EF_SEARCH`
  改口立刻跟着变；两枚脚本里一个候选宽度数字都没有，注释里也没有）。真源取不到 ⇒ 明确报错
  退出（`[前置不满足] ... 本件不许自带宽度，读数作废`），不退回自定的数。
* 档位钉法与生产读腿同一条 SQL、同一作用域：`SELECT set_config(%s, %s, TRUE)`，在真正跑读数
  的那笔事务里、排名语句**之前**；每条排名语句前各钉一次，并当场读回真库认的那一档核对。
* 取证格现在记三档：`session_baseline`（这条连接进来时踩在哪一档，含真库自报 `source` 与
  `boot_val`）/ `read_txn`（这一腿实际钉下去并被读回来的那一档 ×次数）/ `after_read_txn`
  （读数事务结束后的残留检查 —— 会话级污染会在这里露馅）。读不出 = 整轮读数作废并报错，
  不再吞成一句 errors 字符串。
* `probes.sql` 整批包在 `BEGIN; ... ROLLBACK;` 里，设定只在笔内有效；批头写明这一批踩在哪一
  档、来历是谁。开头一条 `SELECT NULL::vector IS NULL` 是 **E8/E9 那一族陷阱的解药**：库没被
  这条会话用过之前，设定只会立一枚 pgvector 不读的占位参数。
* 沙盒件那条 psql 读数解析器（`read_probe_csv_run`）跟着批头一起改了：它过去按「第一行就是
  表头」走 `csv.DictReader`，而批头现在前面排着 `BEGIN` / 库探测 / 设定三句（E10 那一串形状），
  照旧读法每一条真读数都会被读没 —— 而"零读数"在 verify 里长得和"没跑"一模一样。现在认行
  的唯一凭据是矩阵自己（第一列 = principal、第二列 = 它名下的 qid），一条都没认出来就当场报错，
  不再交回空桶。


## 5. 未证 / 未修的格子（如实列）

1. **客户尺寸的两档差：未做、未证。** 本节全部证据来自 1008 枚这一档的沙盒与现库；抬宽之后
   索引扫描代价已≈全库暴力扫量级，且这批探针只量索引算术、量不到近重复吃预算那一族（R269
   症状）。不许拿 1008 枚上的"100 与精确解全等"外推成"客户尺寸无差"。
2. **第三枚同族件没动：`scripts/r59c_recall_compare.py` 全文零 `ef_search`。** 它走服务层
   （`answered_by` 腿凭证），R386 之后 PG 腿由读腿自己钉档，所以它"跟着真源"；但 R386 之前
   经它取的读数同样落在出厂档上，且产物里**没有**候选宽度那一格 ⇒ 那批读数的档**不可知**。
   它不在本单写域，未改。
3. **`docs/testing/r59c-selfcheck-2026-09-25.md:61` 仍写着 S12 的形状是「只有 SELECT + SET」。**
   本单把探针批改成事务内 `set_config(..., TRUE)` 之后，那行文档描述的是旧形状。`docs/testing/**`
   不在本单写域，未改，留给总控决定（改口要连着那份自校实录一起改，别只改标题）。
4. **翻默认读后端不在本单**：`INDEX_BACKEND=pgvector` 写进 `deploy/.env.server` 是业主动作；
   本单只保证"以后这两枚量具量的档与读腿同档"，不保证任何一格的读数结论。
5. **热集让路延迟那一格仍欠一台安静机器**：本单没跑跑分窗，也没起服务（AGENTS：未经授权不起
   服务、不动容器）。

## 6. 反证刀台架（判据⑤ · 逐把进/出 sha256 前缀，逐把按字节复原）

台架：`%TEMP%\r393\knives\harness.py`（临时件，不进版本库）。每把刀只改一处 → 逐枚点名单跑本单
新增的三件钉 → 立刻用原始字节写回并核对 sha。**七把全部咬人，全部 `restored=True`**；台架开跑前后
两枚脚本的 sha 逐位相同（比对件 `b134a9b06d69ef66`、沙盒件 `dd1dda14f4af3fa5`）。钉名照台架原文，不去前缀、不缩写。

| 刀 | 塞回去的缺陷形状 | 进 sha | 出 sha | 咬住的钉 |
|---|---|---|---|---|
| A1 | 把候选宽度字面量塞回沙盒件的 CLI 缺省（历史缺陷形状） | `dd1dda14f4af3fa5` | `468cdf9c32a20f09` | `test_no_candidate_width_number_on_any_width_line`、`test_no_number_is_bound_to_a_width_name`、`test_the_cli_defaults_no_longer_promise_a_library_default`、`test_the_script_itself_carries_no_guc_name_no_handwritten_statement_no_width`（4 枚） |
| A2 | 把候选宽度字面量塞回探针生成器的签名缺省（历史 ef_search: int = 40） | `dd1dda14f4af3fa5` | `e829bb31fa808759` | `test_no_candidate_width_number_on_any_width_line`、`test_no_number_is_bound_to_a_width_name`、`test_no_second_width_number_appears_on_any_width_line_of_the_batch`、`test_the_batch_head_names_the_width_and_its_true_source`、`test_the_default_tracks_the_knob_at_call_time`、`test_the_probe_emitter_still_defaults_to_no_width_of_its_own`、`test_the_script_itself_carries_no_guc_name_no_handwritten_statement_no_width`、`test_the_value_written_in_the_head_is_the_value_the_batch_runs`（8 枚） |
| A3 | 把 --pg-ef-search 的缺省退回 0（= 库里那一档） | `b134a9b06d69ef66` | `865082cf5ee38c12` | `test_no_number_is_bound_to_a_width_name`、`test_the_cli_defaults_no_longer_promise_a_library_default`（2 枚） |
| B | 把取证格的失败改回「吞进 errors 字符串、正文留空」 | `b134a9b06d69ef66` | `dad6cc4b3f6c899d` | `test_the_cell_shouts_instead_of_swallowing_when_the_guc_is_unreachable`、`test_the_failure_never_lands_in_an_errors_string`（2 枚） |
| C | 把事务内 set_config 换回会话级 SET（历史污染路径） | `b134a9b06d69ef66` | `67c19cee528e6753` | `test_the_residue_check_passes_our_own_transaction_local_setting`、`test_the_width_is_pinned_in_the_read_txn_before_the_ranking_sql`（2 枚） |
| D | 摘掉现场取真源，改成 import 期取一次冻成模块常量 | `dd1dda14f4af3fa5` | `fff71100e6bf9997` | `test_sandbox_tool_refuses_to_emit_when_the_source_is_gone`、`test_the_default_tracks_the_knob_at_call_time`、`test_true_source_is_the_only_reader_and_is_asked_at_run_time`（3 枚） |
| E | 把探针读数解析器换回「按第一行当表头」的 DictReader 读法 | `dd1dda14f4af3fa5` | `b9a19772d5256500` | `test_the_parser_admits_no_bucket_the_matrix_did_not_declare`、`test_the_parser_reads_a_real_psql_dump_with_command_tags_in_front`（2 枚） |

没咬的刀：**无**（七把全部有钉红）。边界另说一句：台架证明的是"这些缺陷形状回来会被抓到"，
不是"再无别的漂法"。已经各自有钉的两族是「批头注释与设定语句各说一个数」
（`test_the_value_written_in_the_head_is_the_value_the_batch_runs`）与「绕开真源、把档冻在 import
期」（A2 与 D 两把）。**没钉住的一族**：如果有人把第三枚文件立成宽度源、再让这两枚量具去读
它（反向依赖），本单的 AST 钉只扫这两枚脚本，看不见那种漂移。
