# R525 · 活动先验「真库强度」取证（2026-09-30 · 全单只读 · 执行层 D）

一句话结论：**先验今天在读得到而没有数据的真库上，一名都挪不动**——0011 的表在、台账里有 0011、
表里 **0 行**；而它一旦有数据，位移上界是 **±1 名且与腿宽无关**（5 / 12 / 40 三档实测都是最远一名）。
🔴 「真库有信号」那一格本单**量不到**（只读单不许打点），下面按判据逐条把量到的与没量到的分开写。

所有数字一律是**执行层自报**，每条附命令原文或用例名；派工词要求的现取纪律照办（本文没有一个
数字是从旧纸抄的）。凭据一个字都不在本文里：两枚库只以 `postgresql://***@localhost:5432/enterprise_brain`
这种脱敏形状出现，脱敏函数就是量具自己的 `mask_dsn()`。

## 0. 口径（先说清「真库」是谁）

| 面 | 是哪枚库 | 怎么连 | 为什么这格算真 |
|---|---|---|---|
| **A 部署库** | 容器 `enterprise-brain-postgres-1` / 库 `enterprise_brain` | 在册只读出口 `docker exec … psql -c "SET default_transaction_read_only = on" -c "<SELECT>"`（与 `scripts/r483_empty_tables_triage.py` 同一把闸） | 17 枚迁移全在 `schema_migrations` 台账里，`chunk_vectors` 里躺着真向量 |
| **B 宿主 PG** | `.env` 里那枚 `DATABASE_URL`（计划书 §9.3 点名的「5432 上那台野 PostgreSQL」） | 产品自己的读取器 + 真 psycopg | 它连 `schema_migrations` 都没有 ⇒ 0011 的表也不存在 ⇒ **它就是判据⑤要的那枚「没跑 0011 的库」** |

量具：`scripts/r525_activity_prior_readout.py`（唯一发 SQL 出口 `assert_select_only()`，写句与
DDL/DCL 当场抛）。本文全部读数出自量具（09-30 首趟取证 + 收尾复跑对账，两趟逐格同值，
见 §8 那枚真库闸的现取读数）：

```
python scripts/r525_activity_prior_readout.py --dotenv <主树>/.env --section all --out %TEMP%\r525\readout-all.json
```

- 每条读数的命令原文由量具自己生成（`command_of()`），逐条躺在产物的 `surface_a.readings` 里；
  本文只点名其中判据要的那几枚，不手抄第二份。
- 🔴 面 A 那 1008 枚 / 100 篇是**演示语料**，本单所有产物都带 `corpus_is_demo_corpus: true`
  这枚旗（判据⑥）。宿主 psycopg 够不到部署库：compose 不给 postgres 发布宿主端口，本单实测
  `172.18.0.7:5432` connect timeout（`tests/conftest.py` 的注释与此同口径）。

## 1. 判据① 真库面读数

`tests/test_r525_real_store_readings.py`，9 枚用例（执行层自报，本单收尾现取：
`8 passed, 1 skipped in 0.29s`）。

| 读数 | 值 | 命令（量具生成，逐字在产物里） |
|---|---|---|
| `schema_migrations` 台账 | **17 枚**，`0011` 在列 | `SELECT version FROM schema_migrations ORDER BY version` |
| `to_regclass('public.document_activity_signals')` | `document_activity_signals`（**表在**） | `SELECT to_regclass('public.document_activity_signals')::text` |
| 行数 | **0** | `SELECT count(*)::int FROM document_activity_signals` |
| 非零计数分布 | **空**（`accepted_only` / `rejected_only` / `both` 三桶全零） | 分桶那条 `SELECT bucket, count(*) … GROUP BY bucket` |
| 能命中语料里哪几篇 | **0 篇** | `SELECT count(*)::int FROM document_activity_signals s WHERE EXISTS (SELECT 1 FROM chunk_vectors v WHERE v.filename = s.filename)` |
| 榜首清单 | **空** | `SELECT filename, accepted_count, rejected_count FROM document_activity_signals ORDER BY filename LIMIT 10` |

产品自己那条读取语句（本单从 `app/rag/retriever.py` 现读，不重抄）：

```
SELECT filename, accepted_count, rejected_count FROM document_activity_signals
```

`retriever.py:483` 那段注释自陈「读成功而零行」——**这句话今天（09-30）在真库上仍然成立**，
量具把它变成两枚可对账的读数：

| 状态 | `activity_prior_diagnostics()` | 出处 |
|---|---|---|
| 面 A：读成功、零行 | `source=store` / `reason=""` / `documents=0` | `--section reader`，同场跑 `activity_priors(row_reader=真库那 0 行)` |
| 面 B：读不通 | `source=error` / `reason=UndefinedTable` / `documents=0` | 真 psycopg 打宿主 PG，产品自己的 `_read_activity_signal_rows()` |

**「有信号 / 无信号」两种输入各自的名次读数**（`--section gauge`，输入是真库 ANN 的 40 行名次）：

| 腿宽 | 输入 | 名次读数 | `places_moved` |
|---|---|---|---|
| 5 | **真库计数**（0 行 ⇒ 空先验） | 次序一字不动，交回**同一个列表对象**，命中上无任何注记 | 全 0，`same_object=True` |
| 12 | 真库计数 | 同上 | 全 0 |
| 40 | 真库计数 | 同上 | 全 0 |
| 5 | 合成计数（键真、值合成） | 独大窗口五席同篇 ⇒ 全体等强 ⇒ **一次交换都不发生**，次序仍不动（但会复制注记，`same_object=False`） | 全 0 |
| 12 | 合成计数 | 1 次交换（第 8↔9 名） | `worst_abs_move=1` |
| 40 | 合成计数 | 10 次交换、20 枚载体各挪 ±1 | `worst_abs_move=1` |

🔴 「用真库 SELECT 回来的计数打一次信号」这一格**不存在**：SELECT 回来 0 行。上面那三行
`synthetic_counts_on_real_filenames` 是**合成计数 × 真库真 filename**，只服务位移判据，
不许读成「真库有信号」。

## 2. 判据② 位移读数（断言写在名次与 `places_moved` 上）

`tests/test_r525_displacement_on_real_ranks.py`，16 枚用例（执行层自报：`16 passed in 0.26s`）。
夹具 = 真库真实 ANN 的 40 行（`l2` 算符现读 `vector_scope`、`hnsw.ef_search` 事务内 `set_config`
钉到真源 **100**、query 向量为定种子随机数——本单不许打模型）。

- `test_one_net_adoption_on_real_ranks_buys_exactly_one_place[5|12|40]`：一枚净采纳 =
  `(previous_rank, new_rank, places_moved)` 精确等于 `(p, p-1, +1)`，被挤的那枚 `(p-1, p, -1)`，
  非零位移枚数恒为 **2**。三档各测一次；5 名宽那一份是从真库榜尾裁出来的切片
  （`REAL_WINDOWS[5] = 真库 top-40 的第 36..40 名`），因为头 5 席全是同一篇、量不出「挪一名」。
- `test_the_bound_holds_on_real_ranks_at_every_shipped_leg_width[5|12|40]`：正负两侧同输入，
  `max |places_moved| <= ACTIVITY_PRIOR_MAX_SHIFT_RANKS`（现读 = **1**）。
- `test_the_real_reading_of_travel_when_the_dominant_document_is_adopted`：**读数钉**——赢家
  （真库 top-40 里独占 27 席那篇）被打满正分时，20 枚载体各挪 ±1、共 10 次交换，位移枚数
  **不因同篇席位多而放大**。
- `test_a_rejected_head_sinks_one_place_and_no_further_on_real_ranks[5|12|40]`：负侧真库读数
  `{5: 0, 12: 1, 40: 10}` 枚下沉；**榜首那一枚载体在任何档上都不动**（同篇相邻永远等强，
  交换条件是「下邻严格强于上位」）。
- `test_places_moved_is_always_previous_rank_minus_new_rank_on_real_ranks`：账目自洽，
  `places_moved == previous_rank - new_rank` 且 `new_rank == 它在自己返回次序里的位置`。
- `test_the_prior_never_adds_or_drops_a_real_candidate`：40 行进、40 行出，
  `(filename, chunk_index)` 多重集逐枚对平。
- 在册对照（本单不重复其口径）：`tests/test_r153_prior_shift_is_bounded.py` 钉的是合成名册上的
  界；本件钉的是**真库名次上的同一根界**。

真数据形状里与强度直接相关的三枚读数（执行层自报，命令在产物 `readings` 里）：

| 读数 | 值 | 为什么它管着强度 |
|---|---|---|
| top-5 / top-12 / top-40 里不同文档数 | **1 / 3 / 8** | filename 粒度 ⇒ 一次打点注记该篇窗口内**每一枚**命中 |
| 真库 top-40 里独大那篇占的席位 | **27 / 40** | 载体全体等强时相邻交换一次都不发生 ⇒ 打在赢家身上买到 0 名 |
| `chunk_vectors` 每篇枚数 | widest **586** / narrowest 1 / avg **10.08** / ≥5 枚的篇数 **26** | 一篇 586 枚 chunk 就是 586 个可被打点的载体 |

## 3. 判据③ 无信号＝与现状逐字一致

`tests/test_r525_no_signal_identity.py`，14 枚用例（执行层自报：`14 passed in 0.24s`）。

- `test_the_real_zero_row_store_returns_the_very_same_list_object`：空先验 + 开关开着 ⇒
  `ranked is hits`（**同一对象**，不是内容相等的拷贝）。
- `test_the_on_and_off_states_snapshot_identical_with_no_signals[None|on|off|OFF|0|false|no]`：
  同一对象同一份输入，走产品自己的 `_apply_activity_prior`，七种环境取值两态快照
  `json.dumps(..., sort_keys=True)` **逐字相等**，且每态都交回同一对象。这一跳在册只钉过
  属性态，环境那一跳由本件补上。
- `test_no_hit_carries_an_activity_prior_annotation_when_the_store_is_empty`：注记键压根不出现
  （NULL 语义），键集前后逐字相同。
- `test_the_switch_is_not_a_no_op_when_there_is_a_signal`：对照——有信号时开与关必须真的不一样
  （off ⇒ 同一对象、快照不动；on ⇒ 复制注记且 `(index-1, index, +1)`），否则上面那枚「逐字相等」是自证。
- `test_both_kinds_of_zero_come_back_untouched_but_say_different_things`：两种零在排序上同形、
  在观测面上异形（`store/""` vs `error/RuntimeError`）。

## 4. 判据④ 切读不倒退（`INDEX_BACKEND=pgvector` 摆进子进程 env）

`tests/test_r525_pgvector_leg_env_subprocess.py`，9 枚用例（执行层自报：`9 passed in 11.14s`，
子进程一趟跑三档，`DocumentRetriever` 只冷起一次）。

- `test_the_subprocess_really_read_the_switch_from_its_environment`：driver 里对 `INDEX_BACKEND`
  **一个 setattr 都没有**，`os.environ["INDEX_BACKEND"] == "pgvector"`、`indexing.read_backend()
  == "pgvector"`、`pgvector_reads_enabled() is True` 三枚读数同场成立。
- `test_the_pgvector_leg_answers_and_chroma_is_never_asked[5|12|40]`：`answered_by == "pgvector"`、
  `leg == "semantic"`（换引擎不是降级）、`rows_returned == k`、读腿计数 `answered == 1`、
  而遗留引擎被问的次数 **恒为空列表**——「只在 Chroma 腿上生效」这一条按派工词就是红，本件量的是
  它不红。
- `test_the_prior_still_moves_ranks_on_the_pgvector_leg[5|12|40]`：真库名次在这一支上照样
  `(p, p-1, +1)`，且候选多重集与输入逐枚对平。
- `test_the_control_run_stays_on_the_legacy_engine`：同一份夹具把开关留回缺省 ⇒ `answered_by
  == "chroma"`、`read_topk` 零次调用——证明上面几枚不是夹具自带的。
- `test_the_registered_source_count_pin_cannot_see_a_stripped_pg_exit`：**现数**接线次数 = **5**，
  而在册那枚判据的下界写的是 `>= 4` ⇒ 摘掉任何一支它照样绿。这就是判据④需要新钉的理由。

🔴 这一格里被顶替的只有 `pg_store.read_topk` 那一枚网络出口（宿主够不到部署库端口 + 真 ANN 要
embedding ⇒ 打模型 ⇒ 本单禁）；顶回去的行是量具在真库上真跑过的 ANN 名次。
**「真库 ANN 经 psycopg 端到端 + 先验」这一格未量到**，见 §6。

## 5. 判据⑤ 没跑 0011 的库必须 fail-open

`tests/test_r525_missing_0011_fail_open.py`，7 枚在册用例 + 1 枚真库复跑闸（执行层自报，
本单收尾现取：`7 passed, 1 skipped in 0.46s`）。两枚真库闸同时打开
（`R525_REAL_STORE=on R525_DOTENV=<主树>/.env`）复跑 §1 与本件 ⇒ 现取 `17 passed in 33.11s`。

- 真样本型与原文（面 B 现取，不是编的）：

```
psycopg.errors.UndefinedTable: 关系 "document_activity_signals" 不存在
```

  `test_the_real_exception_type_and_message_are_the_ones_the_host_server_sends` 钉型名、
  钉 `psycopg.errors.ProgrammingError` 的子型关系、钉服务端原文首行。
  `test_the_host_pg_without_0011_really_raises_the_pinned_error`（opt-in）真连面 B 复跑同一枚读数。
- `test_a_missing_relation_fails_open_instead_of_reaching_the_question`：读不通 ⇒ 空先验 +
  `source=error` / `reason=UndefinedTable` / `documents=0`，异常不穿到问答里（**不许 500**）。
- `test_a_loader_that_raises_at_the_hub_never_reaches_the_question`：兜底那一层的另一半——注入
  的读取方抛穿时 `_apply_activity_prior` 仍交回**同一个对象**、异常不上抛、留一行日志。
- `test_fail_open_leaves_the_real_ranks_untouched_and_adds_no_annotation`：真库 top-40 原序回来、
  键集逐字相同、`activity_prior` 键一枚都不出现（NULL 语义）。
- `test_exactly_one_warning_line_is_left_behind`：`enterprise_brain` 那枚 logger 在这一路上**恰好一行**
  `活动信号计数读不到…`，且行内含服务端原文首行。
- `test_a_reading_that_returns_zero_rows_is_not_reported_the_same_way`：两种零的读数必须与面 A /
  面 B 那两枚真读数逐字段对得上——「读不到」冒充成「没有信号所以本该如此」在这里当场红。
- `test_the_backoff_window_does_not_silence_the_next_question_forever`：退避只占一个窗口，
  第二问仍能读到（fail-open 不能变成永久失明）。

## 6. 🔴 未量到的格子（逐枚点名 + 差什么条件；按计划书 §5「没量到的格子不许当已达标」）

| # | 哪一格 | 为什么今天量不到 | 需要什么条件（交回总控排期） |
|---|---|---|---|
| U1 | **真库「有信号」的名次读数**（判据① 的后半） | 面 A 的 0011 今天 0 行，本单全单只读，一条 `INSERT` 都不许发 | 一次真实打点：业主在产品里点「采纳/驳回」，或授权在**非生产**演示库上跑一次 `POST /api/v1/feedback`（写操作，属业主动作） |
| U2 | **真库 ANN 经 psycopg 端到端 + 先验**（判据④ 的字面口径） | ① 宿主 psycopg 够不到部署库（compose 未发布 postgres 宿主端口，实测 connect timeout）；② 真 ANN 需要 query embedding ⇒ **打模型**，本单禁且今晚开 run10 窗 | 开一个能打 embedding 的窗口，照 `docs/perf/r382-readpath-2026-09-27.md` 那套 `docker run --rm --network enterprise-brain_default` 的姿势跑本单量具 `--section gauge`（本单不许起容器） |
| U3 | **真库真并发打点下的名次**（R224 在册判负那格） | 并发打点＝写 + 压库，两条都在本单硬规矩外；且需要安静机器 | run10 之后的安静机器窗口；判据现成：同篇多载体并发打点，看名次是否仍受 ±1 界与 TTL 一致性约束 |
| U4 | **客户尺寸**（非演示语料）下的强度与位移 | 本机只有一枚演示库（1008 枚 / 100 篇，`corpus_is_demo_corpus=true`）；🔴 本单一律不许拿它冒充客户尺寸 | 客户机或业主批准的等尺寸语料；同时 §13 那四件判据要的**非空 `department`/`classification`** 标签（A1/A3 回填属业主动作） |
| U5 | **窗口外先验回填**（`n_results` 之外那半张单） | 不是本单写域：`retriever.py` 的 R46 注释明写「回填目前只作用于召回窗口之内，窗口外的先验等 next-result 那一单」 | 另立单（本单只登记，没动一行产品码） |

一句话给翻默认那笔（`INDEX_BACKEND=pgvector`）：**本单没有给这一格添任何绿票**。先验这一路
切读前后接线都在（判据④ 量到了），但它对名次的**实际影响**今天仍是零行上的空集读数。

## 7. 判据⑦ 反证刀（六把，每把先在影子端跑正控）

`tests/test_r525_counter_evidence_teeth.py`，14 枚用例（执行层自报：`14 passed, 6 warnings in 6.95s`）。
🔴 全程只在 `tmp_path` 的副本上动手；原件 `app/rag/retriever.py` 每把刀前后各核一次 sha256，
最后一枚用例总清点（`test_the_original_source_is_untouched_after_every_knife`）。
锚点唯一性逐枚现取（`test_every_knife_is_declared_with_one_unique_anchor`）。

| 刀 | 改哪里 | 影子端正控读数 | 刀下读数（会咬的证据） | victim |
|---|---|---|---|---|
| K1 | `return self._apply_activity_prior(pg_hits)` → `return pg_hits` | PG 腿 `answered_by=pgvector`、`chroma_asks=[]`、`moves` 含 +1 | 腿还是那条腿，`moves` 全 0、次序与真库名次逐字相同 | 判据④ 三档用例；并当场量出**在册那枚计数覆盖对它全盲**（把 `test_r46…routes_through_the_prior` 指向变异副本，不抛） |
| K2 | `priors = self._activity_prior_loader() or {}` → `priors = {}` | PG 腿与排序都动得 | 两条都不动，而**接线次数一个字没变**（现数对拍相等） | 判据①②④；同一枚在册计数覆盖全盲 |
| K3 | 摘掉 `if not any(strengths): return hits` 早退 | 空先验交回**同一个对象**、注记 0 枚 | 换了对象、40 枚全被注记 | 判据③ |
| K4 | `ACTIVITY_PRIOR_MAX_SHIFT_RANKS = 1` → `= 3` | `worst_abs_move == 1` | `worst_abs_move > 1` | 判据②「买到一名」那三档 |
| K5 | `places_moved = index + 1 - new_rank` → `= 0` | 账目自洽、`moves[index-1]==1` | **次序照变**、账上全 0（`previous_rank != new_rank` 而 `places_moved==0`） | 判据② 账目钉——正是「不许只断言读到了计数」那一句 |
| K6 | `"reason": type(exc).__name__,` → `"reason": "",` | `source=error` / `reason=UndefinedTable` | `reason=""` ⇒ 与「零行」撞成同一份读数 | 判据⑤「不许冒充」 |

## 8. 在册四把 A② 尺与写域自证

```
git -C C:\Users\fengx\PycharmProjects\be-r525 diff --numstat        # 空（零枚跟踪文件被改）
git -C C:\Users\fengx\PycharmProjects\be-r525 status --short         # 只有本单八枚 ?? 新文件（含本纸）
```

新文件清单（共八枚，除这八枚外没有任何改动，`app/**` 与 `migrations/**` 一行未动）：

- `scripts/r525_activity_prior_readout.py`（取证量具，488 行）
- `tests/test_r525_real_store_readings.py`（判据①⑥ + 全单共用夹具）
- `tests/test_r525_displacement_on_real_ranks.py`（判据②）
- `tests/test_r525_no_signal_identity.py`（判据③）
- `tests/test_r525_pgvector_leg_env_subprocess.py`（判据④）
- `tests/test_r525_missing_0011_fail_open.py`（判据⑤）
- `tests/test_r525_counter_evidence_teeth.py`（判据⑦）
- `docs/testing/r525-activity-prior-real-store-2026-09-30.md`（本读数纸，247 行）

- 四把 A② 尺（`scripts/r239_*` / `r506_*` / `r507_*` / `r518_*` / `eval_frame_caliber_readout.py`）：
  `diff --numstat` 为空即逐字未动，sha 无需另拍。
- 合跑枚数（执行层自报，本单收尾现取）：六枚新件正序 `68 passed, 2 skipped in 59.87s`；**反序合跑
  同数**（上一趟现取 `68 passed, 2 skipped in 16.24s`）；与同名域在册件
  （`test_r46_activity_signals.py` / `test_r153_prior_shift_is_bounded.py` / `test_r152_activity_feedback_docs.py`）
  合跑 `144 passed, 2 skipped in 56.41s`，在册断言一字未放宽。
  🔴 纸面更正：上一版这里自报 `143 passed`，本次现取 144——三枚在册邻件在本树与主树各收 76 枚
  （`--collect-only -q` 双向对拍），本单六枚收 70 枚，70 + 76 = 146 = 144 passed + 2 skipped，
  143 那一笔作废。收尾两笔耗时（59.87s / 56.41s）盘面另有三枚 Agent 在跑，耗时上浮，枚数不受影响。
- 🔴 真库复跑闸今天真咬了一口（本单最后一处缺陷就是这么被抓住的）：`--section all` 产物里
  `chunks_per_document` 发的是**单元素列表**，而快照钉的是 dict ⇒
  `test_the_live_real_store_still_matches_the_pinned_snapshot` 当场报红
  （`AssertionError: ('chunks_per_document', [{'widest': 586, 'narrowest': 1, 'average': 10.08,
  'docs_with_5plus_chunks': 26}])`）。根因在量具：无 GROUP BY 的聚合走了多行发形。已改
  `scripts/r525_activity_prior_readout.py`——钉住「恒回一行」并拆成 dict——同时把 `vector_scope`
  纳进逐格对账、快照发形与产物对齐；修后两枚真库闸现取 `17 passed in 33.11s`。
- 两枚 `skipped` 是本单的两枚真库复跑闸（`R525_REAL_STORE=on` 才跑），默认不进全量门；
  本单**没跑**全量回归门（`python scripts/run_gate.py`），照硬规矩留给总控。
- 资源纪律：本单跑过量具全节 2 趟（首趟取证 + 收尾复跑）与 pytest 若干趟（单件 / 合跑 / opt-in
  各一趟），全程串行，没有并发压库、
  没有长跑、没动容器、没打模型；`docker exec … psql` 全部只读，`SET default_transaction_read_only
  = on` 每条都在。
- 一处需要总控知情的盘面事实：`tests/` 合跑时 R134 那枚 Chroma 写回闸报
  `PersistentClient 调用: 1 次，落点被改道出工作树`，落点是 conftest 自己给的临时目录，
  `工作树 chroma_db 写回告警用例: 0 枚` ⇒ 没脏本树。
