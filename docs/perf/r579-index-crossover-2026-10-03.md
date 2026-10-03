# R579 · PG 读腿的「索引拐点」第一次有数

- 单号 / 执行层：R579 ／ Faraday
- 日期：2026-10-03（现网读数全部落在 09:0x–11:1x，本席一手，无二手话）
- 工作树：`C:\Users\fengx\PycharmProjects\be-r579`，基点 `b85c277`（detached）
- 件：`scripts/r579_index_crossover_readout.py`（可重跑）／`tests/test_r579_readout_teeth.py` ＋ `tests/test_r579_synthetic_provenance.py`（126 枚离线钉，零连库、零模型）
- 量具：同一枚 PG 实例（`enterprise-brain-postgres-1`，PostgreSQL 16.15 ＋ pgvector 0.8.6，`shared_buffers=16384` 页＝128 MB，`effective_cache_size=524288` 页＝4 GB，`random_page_cost=4`，`max_parallel_maintenance_workers=2`）
- 一句话结论：**拐点区间量到了——在 5 000 与 20 000 枚之间，规划器从全表换成 HNSW 索引腿（分析态）；而同一区间正是索引腿名次开始塌的地方（k=5 重合率 5 000 档 0.700 → 20 000 档 0.305）。本单同时交出两枚仪器缺陷的一手证据，其中一枚足以把这一格读成假绿。**

---

## 0. 怎么重跑（本纸每个数的来历）

```powershell
# 库侧动作（件本身经 stdin 进容器，用 backend 镜像里的解释器；宽度现场从真源取）
Get-Content scripts\r579_index_crossover_readout.py -Raw -Encoding UTF8 |
  docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python - --action repro   --prepare-threshold none --expect-ef-search 100 --queries 12 --warm-rounds 2 --plan-samples 6 --repro-k 5
Get-Content scripts\r579_index_crossover_readout.py -Raw -Encoding UTF8 |
  docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python - --action build   --sizes 1008,5000,20000,50000 --replace --expect-ef-search 100
Get-Content scripts\r579_index_crossover_readout.py -Raw -Encoding UTF8 |
  docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python - --action measure --sizes 1008,5000,20000,50000 --k 5,20 --queries 40 --warm-rounds 1 --plan-samples 8 --states as_loaded,analyzed --prepare-threshold none --expect-ef-search 100
Get-Content scripts\r579_index_crossover_readout.py -Raw -Encoding UTF8 |
  docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python - --action cleanup

# 离线动作（宿主解释器，零连库）
python scripts\r579_index_crossover_readout.py --action report --from-results <measure.json> --format table   # 或 json
python scripts\r579_index_crossover_readout.py --action emit-data --sizes 1008,5000,20000,50000 --data-dir C:\Users\fengx\PycharmProjects\r579-drill
python scripts\r579_index_crossover_readout.py                      # 缺省动作 = plan，只打印打算发什么
```

缺省动作是 `plan`：不给 `--action` 时一条语句都不出站。`--expect-ef-search` 对账不上直接 `rc=2`，整单不量。

---

## 1. 六格自评（逐格可失败）

| 格 | 判据 | 结论 | 差哪条 |
| --- | --- | --- | --- |
| ① | 复现派工词第 3 条三行读数 | **达**（带两条不一致，照实写，见 §2） | 前提 2「一问 `idx_scan` ＋10」**没跑**——要真打模型，本单禁 |
| ② | 四档 × (a)(b)(c) 三组数 | **达**（四档全数在 §5；`as_loaded` 态的 (a) 交回的是"未量到＋为什么"，不是外推） | 无 |
| ③ | 候选宽度必须派生 | **达**：纸里每个宽度数字都点名来历＝`configured_hnsw_ef_search()` 现场调用＋服务端 `current_setting` 复核；件里零枚字面宽度数字 | 无 |
| ④ | 不可外推声明成格 | **达**（§9 独立一节；全纸不出现"客户机上会怎样"的断言） | 无 |
| ⑤ | 反证 ≥3 把 | **达**（四把，含一枚物理篡改，逐枚 sha256，见 §7） | 无 |
| ⑥ | 清理与零污染 | **达**（库名集合回到开局那一集；生产 12 项前后全等；大文件只在仓外 `r579-drill`，见 §8） | 无 |

---

## 2. 判据①：现网那三行读数（生产库只读，语句形状与派工词一致）

语句原文由 `RecordingConnection` 从 `pg_store.search_vectors()` 录下，本件不重写一套：

```sql
SELECT vector_id, content, filename, chunk_index, classification, department,
       embedding <-> %s::vector AS distance
FROM chunk_vectors
WHERE classification = ANY(%s::integer[])
ORDER BY embedding <-> %s::vector LIMIT %s
```

`where classification = any('{1}'::integer[])`、`limit 5`、常量向量为 768 维合成探针。

### 2.1 默认代价模型（不加任何开关）—— 纸面那句成立，数字比纸面大

EXPLAIN 原文（11:09 现取，768 维常量向量已摘）：

```
Limit  (cost=279.12..279.14 rows=5 width=906) (actual time=7.927..7.930 rows=5 loops=1)
  Buffers: shared hit=6294
  ->  Sort  (cost=279.12..281.64 rows=1008 width=906) (actual time=7.925..7.927 rows=5 loops=1)
        Sort Key: ((embedding <-> '<常量向量：768 维>'::vector))
        Sort Method: top-N heapsort  Memory: 34kB
        Buffers: shared hit=6294
        ->  Seq Scan on chunk_vectors  (cost=0.00..262.38 rows=1008 width=906) (actual time=0.025..7.392 rows=1008 loops=1)
              Filter: (classification = ANY ('{1}'::integer[]))
              Buffers: shared hit=6294
Planning Time: 0.122 ms
Execution Time: 7.951 ms
```

- 形状逐点对上纸面：`Seq Scan on chunk_vectors (rows=1008)` ＋ `Sort Method: top-N heapsort`。
- 🔴 **不一致之一（数字）**：纸面 `actual time 约 2.4 ms`；本席 10:50 现取 3.736–4.819 ms（p50 4.063），11:09 再取 6.856–9.370 ms（p50 7.966）。同一条 SQL、同一枚库，19 分钟内两次读数差到 2 倍——**这台机现在不安静**（同机在飞 `be-r572`／`be-r573`／`be-r575`／`be-r578`）。所以本单只把「腿名／名次／比值」当结论用，绝对延迟数一律带这枚噪声声明（§9 第 7 条）。

### 2.2 逼它走索引（`set enable_seqscan=off; set enable_sort=off`）—— 纸面那句**不复现**

EXPLAIN 原文（同一轮、同一形状）：

```
Limit  (cost=1639.76..1646.65 rows=5 width=906) (actual time=0.866..0.898 rows=5 loops=1)
  Buffers: shared hit=864
  ->  Index Scan using chunk_vectors_embedding_idx on chunk_vectors  (cost=1639.76..3027.94 rows=1008 width=906) (actual time=0.865..0.896 rows=5 loops=1)
        Order By: (embedding <-> '<常量向量：768 维>'::vector)
        Filter: (classification = ANY ('{1}'::integer[]))
        Buffers: shared hit=864
Planning Time: 0.097 ms
Execution Time: 0.920 ms
```

🔴 **不一致之二（方向）**：纸面写「`actual time` 约 44.5 ms／慢 18 倍」。**本席量不出来，并且能解释那 44.5 ms 从哪来**：

| 轮次 | 该臂第一枚（冷） | 稳态各枚（热） |
| --- | --- | --- |
| 10:50 那轮（无真热身） | `exec=169.291 ms`，`shared read=428` | 0.338–0.726 ms，`shared read=0` |
| 同前一小时（旧协议，`r579_prod_repro2.json`） | `exec=37.0 ms`，`shared read=420` | 0.31–0.79 ms |
| 11:09 那轮（真热身两轮） | `exec=0.685–2.406 ms`，`shared read=0` | 端到端 p50 2.655 ms |

⇒ 44.5 ms 是**冷启动一次性读数**（第一枚执行要把 HNSW 图的 420–428 枚页从盘上拽进 128 MB `shared_buffers`），不是稳态。稳态下 1008 枚这一档，索引腿比全表腿**快 5–10 倍**（服务端 0.835 ms vs 7.966 ms；端到端 2.66 ms vs 7.97 ms）。规划器不选它的理由是**估计代价**：`cost=1646.65` vs `cost=279.14`（5.9 倍），不是实测更慢。这一条直接改写本板 §4EJ 的口径，见 §11。

### 2.3 算符与索引对得上（纸面第三句成立）

- `vector_scope.distance_function` 现读 = `l2`；`app/rag/pg_store.py` 的 `DISTANCE_OPERATORS` 把 `l2` 映射成 `<->`；
- 索引原文现读 = `CREATE INDEX chunk_vectors_embedding_idx ON public.chunk_vectors USING hnsw (embedding vector_l2_ops) WITH (m='16', ef_construction='100')`；
- 算子类 `vector_l2_ops` 与 `<->` 同族 ⇒ **索引可用，只是 1008 枚这一档规划器嫌库小不选它**（这句与纸面一致）。

### 2.4 环境前提（本席 11:1x 现读，非引用）

```
docker exec <三枚容器> printenv INDEX_BACKEND       -> pgvector / pgvector / pgvector
backend 进程内 app.rag.indexing.read_backend()       -> pgvector
backend 进程内 app.rag.indexing.INDEX_BACKEND_DEFAULT -> chroma      （代码缺省仍是遗留件）
候选宽度 真源 configured_hnsw_ef_search()             -> 100
候选宽度 服务端 current_setting('hnsw.ef_search')      -> 100（同一笔事务内 set_config 钉过再读回）
```

### 2.5 顺手挖出来的一条口径修正（判据之外的发现，写进纸里）

生产 `chunk_vectors` 现读：`pg_statistic` 里 **14 行活统计**，而 `last_analyze` 与 `last_autoanalyze` **双双 NULL**。⇒ 在册口径「分析过没有＝看时间戳」在生产上是错的。本件的 `catalog_facts()` 因此**现读目录**（`pg_statistic.starelid` 计数），`state_flags()` 只看目录、不信时间戳；`as_loaded` 档若现场读到统计就自己标 `DIRTY`。生产那 14 行的实际后果：`reltuples=1008.0`、`relpages=246` 已进目录，规划器是按"分析过的表"在算 §2.1 那笔代价的——纸面那句"嫌库小"的结论不变，但**依据是活统计，不是缺省统计**。

---

## 3. 两枚仪器缺陷（本单一手；其中一枚足以把这一格读成假绿）

### 3.1 🔴 psycopg3 的同连接计划复用会吞掉 `SET LOCAL enable_seqscan/enable_sort`

第一轮全量（`r579_measure.json`，10:19–10:21，`prepare_threshold` 沿用 psycopg3 缺省 5）交回的 16 行里，**14 行 `legTrust=idx!`**：被开关逼出来的 `index` 臂，端到端 p50 与它自己 EXPLAIN 交回的时间差到 3 倍以上——

```
第一轮（缺省 prepare 阈值）：
  1008  analyzed k=5   p50nat=3.3  p50idx=3.5  overlap=1.0000  legTrust=idx!   ← 索引臂的墙钟贴着全表腿
  5000  analyzed k=5   p50nat=18.3 p50idx=17.8 overlap=1.0000  legTrust=idx!   ← 自己的 EXPLAIN 说 3.6 ms
  20000 analyzed k=5   p50nat=73.4 p50idx=73.9 overlap=1.0000  legTrust=nat-idx!
```

因为同一条连接上第 6 次起走的是**已 prepare 的旧计划**，事务里那句 `SET LOCAL` 对已缓存的计划**不生效**——所谓「索引臂」其实**在跑全表腿**，于是它与暴力精确解当然全等，`overlap=1.0000`。这不是 pgvector 的性质，是本件当时的连接姿势。

排除过程（逐条一手，产物全在 `r579-drill\`）：
1. `exact` 臂的 id 逐枚、逐轮、逐态**逐字节相同**，查询向量字面量 sha 也相同 ⇒ 不是数据或 seed 漂；
2. `--action repeat-probe`（同一枚问题连打 12 次）三臂各自 `distinct_answers=1` ⇒ **pgvector 不是随机的**，"每跑一次换一个答案"这个解释被排除；
3. 同一枚 5 000 档，`repeat-probe` 交回 `index ≠ exact`（1 枚换位），而全量第一轮交回 `index == exact` ⇒ 差异只在**测量姿势**；
4. 件里加 `arm_consistency()`：逐臂算「端到端 p50 / 本臂自己的 EXPLAIN Execution Time p50」，比值门 3.0，超门就在主表 `legTrust` 格打 `idx!`——第一轮那 14 行当场报警；
5. 改连接姿势为 `prepare_threshold=None`（永不 prepare）＋ 真热身，重跑：**16 行全部 `ok`，最大比值 2.315**，名次差随之变成 §5 那组真数。

⇒ 件里现在**缺省就是 `--prepare-threshold none`**，并把这一项自写进产物（`"prepare_threshold": "none"`）；`--prepare-threshold psycopg` 留给下一班复现旧假绿用。

### 3.2 假热身：`warmup` 那几轮只发 `BEGIN/ROLLBACK`，一条读语句都不执行

同一条生产 SQL，10:50 那轮：第一枚 `EXPLAIN (ANALYZE)` = **169.291 ms（`shared read=428`）**，紧随其后的真执行 = **1.317 ms**。因为所谓"热身"根本没执行过任何东西，于是**冷页拽入的成本被记进"服务端时间"，而端到端时间记的是热的那一枚**——两本账互相抄，稳态与冷启动混成一格。

修法（已落件，`run_reader()` 三相位）：

- 相位 W：`--warm-rounds` 轮，每轮把全部向量**真的执行一遍**，读数丢弃；
- 相位 T：每枚向量执行一次并计时、收名次，事务里不夹 EXPLAIN；
- 相位 P：对前 `plan_samples` 枚向量各打**两次** `EXPLAIN (ANALYZE, BUFFERS)`，第一次只为把这条腿的页拽热，**留第二次**。

钉：`test_warm_phase_is_the_bug_that_was_fixed_not_a_renamed_noop`（`warm_rounds` 0/1/2 必须差一整轮真执行，而计时样本枚数不随之变化）＋ `test_run_reader_only_uses_read_shapes_and_pins_the_width_inside_each_txn`（逐枚点名事务数 3/3/1、真执行 6 次、EXPLAIN 2 次）。

🔴 两枚缺陷合起来就是这一格原本的假绿形状：**「索引腿 = 精确解 1.0000」既可能是计划缓存吞了开关，也可能是冷启动混进稳态**。本单两枚都留下了可复现的开关（`--prepare-threshold psycopg` ＋ `--warm-rounds 0`）。

---

## 4. 沙盒构建账（`eb_r579_probe`，同实例内；建完已删）

- 库名守卫：只认 `eb_r579_probe`（`--sandbox-db`／`--db-prefix` 可换），连上先 `SELECT current_database()` 现场对账；`enterprise_brain` 一律走只读连接＋逐条写形状拦截（§7 反证③）。
- pgvector 版本对账：沙盒 `0.8.6` ＝ 生产 `0.8.6`，不同版本本件直接 `SystemExit`（换了算符实现就不是这台机那一格）。
- 列定义逐枚对齐生产（`columns_match_prod: true`），HNSW 索引原文与生产同参：`USING hnsw (embedding vector_l2_ops) WITH (m='16', ef_construction='100')`。
- 语料：768 维、固定 seed 的 LCG 合成**单位向量**；`classification` 全 = 1（与生产主密级同形）；正文长度取生产现读 `avg(octet_length(content)) = 782 B`；行宽与生产同量级（`toast_bytes_per_row = 4096.0 B/行`，生产同值）。
- 生成器与在册件 `scripts/r59c_sandbox_corpus.py:116` **逐枚同源**（同一枚 LCG 链、同一个取值域、同一个按取值域算的模长、同一位小数）；`tests/test_r579_synthetic_provenance.py` 逐枚对过，漂了就红。在册件本单只 import／读，没改一个字。
- 四档建表＋建索引（串行，`--parallel-maintenance-workers 0`；容器 `/dev/shm` 只有 64 MB，20 000 档并行建索引曾当场 `DiskFullError: could not resize shared memory segment`）：

| 档 | 行数 | HNSW 建索引 | `data_sha256`（＝ TSV 前缀逐字节 sha） |
| --- | --- | --- | --- |
| 1 008 | 1008 | 0.53 s | `eb9ac0f88e72…` |
| 5 000 | 5000 | 5.73 s | `024675ba8824…` |
| 20 000 | 20000 | 34.90 s | `157608a61e1b…` |
| 50 000 | 50000 | 115.76 s | `8ac224139795…` |

- 50 000 档**灌成了**，没有停在最大可灌档。
- 语料文件：`C:\Users\fengx\PycharmProjects\r579-drill\r579_corpus_50000.tsv`（`--action emit-data` 落的最大档，50 000 行／413 100 126 B，整文件 sha256 = `8ac224139795c2c5b14f19706db5bcf23c36595c9c99d6024ceef6a27071ebab`）⇒ **与 COPY 进沙盒的字节流逐字节同 sha**；前缀即小档（第 N 行之前的字节流就是 N 档语料本身）。落仓外目录，主树／工作树零污染。
- `autovacuum_enabled=false`（`reloptions` 现读）＋ 四档灌完现读 `pg_statistic = 0 行`、`last_analyze/last_autoanalyze = NULL` ⇒ **`as_loaded` 这一态是"真没人分析过"**（第一轮量测时这一态被本席的 ANALYZE 污染过，本纸 §5 用的是重灌之后的干净态）。

---

## 5. 判据②：四档 × 三组数（分析态与未分析态各一遍；`--prepare-threshold none` ＋ 真热身）

主产物：`r579_measure_main.json`（16 条记录 = 4 档 × 2 态 × k∈{5,20}，每条 40 枚计时样本）。候选宽度全纸只有一种来历：`configured_hnsw_ef_search()` 现场 = **100**，服务端 `current_setting` 复核 = **100**。

### 5.1 原文表（逐字节抄自 `--action report --format table`）

```text
   size      state    k   nat.leg   idx.leg   exa.leg overlap  meanΔ  maxΔ onlyIx onlyEx   p50nat   p50idx   p50exa   p95nat   p95idx   p95exa  eqIdx   stat onHNSW  legTrust
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
   1008   analyzed    5       seq       idx       seq  1.0000  0.000     0      0      0      8.0      1.8      8.5      8.8      2.1      9.1  40/40  clean     no        ok
   1008   analyzed   20       seq       idx       seq  0.9912  0.061     1      7      7      8.4      2.2      8.3      9.4      2.5      9.5  33/40  clean     no        ok
   1008  as_loaded    5 bitmap_in       idx       seq  1.0000  0.000     0      0      0      8.1      1.9      8.0      9.6      2.2      8.9  40/40  clean     no        ok
   1008  as_loaded   20 bitmap_in       idx       seq  0.9912  0.061     1      7      7      8.0      1.9      8.2      9.2      2.5      9.2  33/40  clean     no        ok
   5000   analyzed    5       seq       idx       seq  0.7000  0.656     2     60     60     36.7      3.7     24.3     41.3      4.2     33.9   7/40  clean     no        ok
   5000   analyzed   20       seq       idx       seq  0.6938  3.008     9    245    245     37.5      3.7     36.5     40.1      4.4     43.5   0/40  clean     no        ok
   5000  as_loaded    5 bitmap_in       idx       seq  0.7000  0.656     2     60     60     37.3      3.7     37.7     67.5      4.4     40.5   7/40  clean     no        ok
   5000  as_loaded   20 bitmap_in       idx       seq  0.6938  3.008     9    245    245     35.9      3.7     36.4     38.5      4.4     40.4   0/40  clean     no        ok
  20000   analyzed    5       idx       idx       seq  0.3050  1.179     4    139    139      3.3      3.2    123.2      3.9      4.2    152.3  40/40  clean    yes        ok
  20000   analyzed   20       idx       idx       seq  0.2775  6.718    18    578    578      5.2      4.7     92.3      6.0      6.6    101.1  40/40  clean    yes        ok
  20000  as_loaded    5 bitmap_in       idx       seq  0.3050  1.179     4    139    139     95.6      3.6     96.8    105.8      4.4    112.4   0/40  clean     no        ok
  20000  as_loaded   20 bitmap_in       idx       seq  0.2775  6.718    18    578    578     92.9      3.0     95.6    102.4      3.7    103.5   0/40  clean     no        ok
  50000   analyzed    5       idx       idx       seq  0.1500  0.821     4    170    170      4.5      4.5    239.5      5.6      5.3    262.0  40/40  clean    yes        ok
  50000   analyzed   20       idx       idx      pseq  0.1525  6.931    17    678    678      5.2      5.0    115.2      6.4      6.0    125.0  40/40  clean    yes        ok
  50000  as_loaded    5 bitmap_in       idx       seq  0.1500  0.821     4    170    170    358.8      8.8    290.5    464.6     11.2    448.4   0/40  clean     no        ok
  50000  as_loaded   20 bitmap_in       idx       seq  0.1525  6.931    17    678    678    258.5      5.6    218.4    285.5      6.9    231.8   0/40  clean     no        ok

拐点 analyzed|k=20: 在 5000 与 20000 之间从全表换成索引腿｜legs={1008: 'seq', 5000: 'seq', 20000: 'index', 50000: 'index'}
   向量索引那本账 analyzed|k=20: 在 5000 与 20000 之间，自然腿第一次踩上向量索引｜natural_on_hnsw={1008: False, 5000: False, 20000: True, 50000: True}
拐点 analyzed|k=5: 在 5000 与 20000 之间从全表换成索引腿｜legs={1008: 'seq', 5000: 'seq', 20000: 'index', 50000: 'index'}
   向量索引那本账 analyzed|k=5: 在 5000 与 20000 之间，自然腿第一次踩上向量索引｜natural_on_hnsw={1008: False, 5000: False, 20000: True, 50000: True}
拐点 as_loaded|k=20: 未量到拐点：四档里没有出现「小的走全表、大的走索引」这一对，见 legs_by_size｜legs={1008: 'index', 5000: 'index', 20000: 'index', 50000: 'index'}
   向量索引那本账 as_loaded|k=20: 未量到：四档里自然腿没有从「不踩向量索引」翻成「踩向量索引」｜natural_on_hnsw={1008: False, 5000: False, 20000: False, 50000: False}
拐点 as_loaded|k=5: 未量到拐点：四档里没有出现「小的走全表、大的走索引」这一对，见 legs_by_size｜legs={1008: 'index', 5000: 'index', 20000: 'index', 50000: 'index'}
   向量索引那本账 as_loaded|k=5: 未量到：四档里自然腿没有从「不踩向量索引」翻成「踩向量索引」｜natural_on_hnsw={1008: False, 5000: False, 20000: False, 50000: False}

服务端那本账（不含协议往返）:
   size      state    k |   nat.leg   srvP50   srvP95  rdMax |   idx.leg   srvP50   srvP95  rdMax |   exa.leg   srvP50   srvP95  rdMax
--------------------------------------------------------------------------------------------------------------------------------------
   1008   analyzed    5 |  seq_scan    7.218   11.163    8/0 | index_scan    1.063    1.164    8/0 |  seq_scan    7.314    8.557    8/0
   1008   analyzed   20 |  seq_scan    7.068    7.492    8/0 | index_scan    1.074    1.629    8/0 |  seq_scan    6.899    7.568    8/0
   1008  as_loaded    5 | bitmap_index_scan+heap    7.279    9.700    8/0 | index_scan    0.945    1.079    8/0 |  seq_scan    7.250    9.516    8/0
   1008  as_loaded   20 | bitmap_index_scan+heap    7.012    7.754    8/0 | index_scan    0.995    1.195    8/0 |  seq_scan    7.169    8.291    8/0
   5000   analyzed    5 |  seq_scan   37.222   40.114    8/0 | index_scan    2.463    3.263    8/0 |  seq_scan   26.247   30.571    8/0
   5000   analyzed   20 |  seq_scan   36.748   43.969    8/0 | index_scan    2.672    3.023    8/0 |  seq_scan   35.772   36.859    8/0
   5000  as_loaded    5 | bitmap_index_scan+heap   33.813   41.265    8/0 | index_scan    2.313    2.531    8/0 |  seq_scan   35.806   37.330    8/0
   5000  as_loaded   20 | bitmap_index_scan+heap   35.529   36.995    8/0 | index_scan    2.217    3.369    8/0 |  seq_scan   36.081   39.171    8/0
  20000   analyzed    5 | index_scan    2.374    3.180    8/0 | index_scan    2.592    2.638    8/0 |  seq_scan  139.498  156.748    8/0
  20000   analyzed   20 | index_scan    3.942    4.994    8/0 | index_scan    3.161    3.884    8/0 |  seq_scan   96.488  102.727    8/0
  20000  as_loaded    5 | bitmap_index_scan+heap   96.222  105.460    8/0 | index_scan    2.190    3.032    8/0 |  seq_scan  103.633  118.840    8/0
  20000  as_loaded   20 | bitmap_index_scan+heap   91.454   95.414    8/0 | index_scan    2.171    3.014    8/0 |  seq_scan   94.831  100.158    8/0
  50000   analyzed    5 | index_scan    2.831    4.293    8/0 | index_scan    2.179    2.777    8/0 |  seq_scan  244.220  282.839 8/31546
  50000   analyzed   20 | index_scan    2.253    3.154    8/0 | index_scan    2.471    2.986    8/0 | parallel_seq_scan  117.225  130.778 8/31556
  50000  as_loaded    5 | bitmap_index_scan+heap  463.285  568.853 8/31567 | index_scan    4.517    6.298    8/0 |  seq_scan  284.731  318.614 8/31546
  50000  as_loaded   20 | bitmap_index_scan+heap  246.882  268.107 8/31567 | index_scan    3.017    3.723    8/0 |  seq_scan  215.217  229.140 8/31546

srvP50/srvP95 = EXPLAIN (ANALYZE) 交回的 Execution Time；rdMax = 该臂采样里 shared read 的最大值（读盘枚数）
协议往返本身 arm=natural p50=0.247 p95=0.380 n=25 事务内语句枚数=4
协议往返本身 arm=index p50=0.201 p95=0.321 n=25 事务内语句枚数=6
协议往返本身 arm=exact p50=0.169 p95=0.255 n=25 事务内语句枚数=7

腿名可信度 = 端到端 p50 / 本臂自己的 EXPLAIN Execution Time p50（比值门 3.0，超门标 *：这一臂没在跑它宣称的那条腿，腿名不许写进结论）
     1008   analyzed k=5   nat=1.106 idx=1.698 exa=1.155
     1008   analyzed k=20  nat=1.184 idx=2.044 exa=1.208
     1008  as_loaded k=5   nat=1.109 idx=2.038 exa=1.098
     1008  as_loaded k=20  nat=1.139 idx=1.949 exa=1.139
     5000   analyzed k=5   nat=0.986 idx=1.521 exa=0.927
     5000   analyzed k=20  nat=1.02 idx=1.395 exa=1.019
     5000  as_loaded k=5   nat=1.104 idx=1.589 exa=1.053
     5000  as_loaded k=20  nat=1.011 idx=1.683 exa=1.01
    20000   analyzed k=5   nat=1.37 idx=1.242 exa=0.883
    20000   analyzed k=20  nat=1.314 idx=1.476 exa=0.957
    20000  as_loaded k=5   nat=0.994 idx=1.656 exa=0.934
    20000  as_loaded k=20  nat=1.015 idx=1.399 exa=1.009
    50000   analyzed k=5   nat=1.599 idx=2.043 exa=0.981
    50000   analyzed k=20  nat=2.315 idx=2.021 exa=0.983
    50000  as_loaded k=5   nat=0.774 idx=1.946 exa=1.02
    50000  as_loaded k=20  nat=1.047 idx=1.856 exa=1.015

自检: 达｜拐点: analyzed|k=20 -> 在 5000 与 20000 之间从全表换成索引腿; analyzed|k=5 -> 在 5000 与 20000 之间从全表换成索引腿; as_loaded|k=20 -> 未量到拐点：四档里没有出现「小的走全表、大的走索引」这一对，见 legs_by_size; as_loaded|k=5 -> 未量到拐点：四档里没有出现「小的走全表、大的走索引」这一对，见 legs_by_size
```

### 5.2 逐档读数（分析态，k=5）

| 档 | (a) 自然腿 | (a) 逼索引对照组 | (b) 重合率／only_in／平均绝对位移／最大位移 | (c) 索引腿 vs 暴力腿 p50／p95（端到端） | (c) 服务端 p50（EXPLAIN 自报） |
| --- | --- | --- | --- | --- | --- |
| 1 008 | `Seq Scan`（`onHNSW=no`） | `Index Scan using chunk_vectors_embedding_idx` | 1.0000 ／ 0+0 ／ 0.000 ／ 0 | 1.8 & 8.5 ms ／ 2.1 & 9.1 ms | 1.063 ／ 7.218 ms |
| 5 000 | `Seq Scan`（`onHNSW=no`） | 同上 | 0.7000 ／ 60+60 ／ 0.656 ／ 2 | 3.7 & 24.3 ms ／ 4.2 & 33.9 ms | 2.463 ／ 26.247 ms |
| 20 000 | **`Index Scan`（`onHNSW=yes`）** | 同上 | 0.3050 ／ 139+139 ／ 1.179 ／ 4 | 3.2 & 123.2 ms ／ 4.2 & 152.3 ms | 2.592 ／ 139.498 ms |
| 50 000 | **`Index Scan`（`onHNSW=yes`）** | 同上 | 0.1500 ／ 170+170 ／ 0.821 ／ 4 | 4.5 & 239.5 ms ／ 5.3 & 262.0 ms | 2.179 ／ 244.220 ms |

k=20 那半张表在 §5.1 原文里逐档可点，形状与 k=5 一致（重合率 0.9912／0.6938／0.2775／0.1525；`only_in` 7／245／578／678 枚；最大位移 1／9／18／17）。

### 5.3 `as_loaded`（未分析）态必须单独说，不许与上一态混读

四档的自然腿**全部**落在 `bitmap_index_scan+heap`——那是 `classification` 的 btree ＋ 堆取 ＋ 顶层排序，**不是** HNSW（`onHNSW` 四档全 `no`）。这是一族完全不同的腿，代价形状也不同，所以：

- 未分析态**量不到**「全表 → 向量索引」这一本拐点（§6 原文就写「未量到」）；
- 名次差那一组 (b) 在两态下同数，因为 (b) 比的是「被开关逼出来的索引腿」与「暴力腿」，与自然腿选谁无关；
- 端到端延迟差得很远（1 008 档 8.1 ms → 50 000 档 358.8 ms），说明**没有统计信息时规划器在真库上是另一回事**。这一条不属于本单判据，只登记现象、不外推。

### 5.4 两本账分开（服务端 `srvP50` ＋ 协议往返地板 ＋ 腿名可信度）

三臂在计时区之外的语句枚数不同（4／6／7 条），所以端到端与服务端必须分列——原文在 §5.1 的下半张表。协议往返本身（同一事务形状下 `SELECT 1`）：`p50 = 0.169–0.247 ms`，本轮负载下比早上那轮（0.043 ms）大一档，同样是争用噪声。

腿名可信度那一格：本轮 16 行**全部 `ok`**（比值 0.774–2.315，门 3.0）。对照：第一轮那 16 行里 **14 行 `idx!`**（§3.1）。

---

## 6. 拐点区间（原文，逐字抄自 `--action report`）

```
拐点 analyzed|k=5:  在 5000 与 20000 之间从全表换成索引腿｜legs={1008: 'seq', 5000: 'seq', 20000: 'index', 50000: 'index'}
   向量索引那本账 analyzed|k=5:  在 5000 与 20000 之间，自然腿第一次踩上向量索引｜natural_on_hnsw={1008: False, 5000: False, 20000: True, 50000: True}
拐点 analyzed|k=20: 在 5000 与 20000 之间从全表换成索引腿｜legs={1008: 'seq', 5000: 'seq', 20000: 'index', 50000: 'index'}
   向量索引那本账 analyzed|k=20: 在 5000 与 20000 之间，自然腿第一次踩上向量索引｜natural_on_hnsw={1008: False, 5000: False, 20000: True, 50000: True}
拐点 as_loaded|k=5:  未量到拐点：四档里没有出现「小的走全表、大的走索引」这一对，见 legs_by_size｜legs={1008: 'index', 5000: 'index', 20000: 'index', 50000: 'index'}
   向量索引那本账 as_loaded|k=5:  未量到：四档里自然腿没有从「不踩向量索引」翻成「踩向量索引」｜natural_on_hnsw 四档全 False
拐点 as_loaded|k=20: 未量到拐点：（同上）
```

**两本账给的是同一个区间：5 000 ↔ 20 000 枚。** 派工词要的是区间不是单点，这一条满足；区间内部的细拐点没量（§10 第 2 条）。

顺带一条同区间的读数：拐点两侧的名次差不是零——过了拐点的 20 000／50 000 档，索引腿与暴力腿 k=5 重合率只有 **0.305／0.150**。所以「规划器开始选索引」与「索引开始丢名次」发生在**同一个规模区间**，这一格不能只写拐点不写名次。

---

## 7. 判据⑤：反证逐枚（摘前摘后逐字节 sha256）

件的 sha256（前 12）：摘前 `F37B308B36AD` ＝ 摘后（还原）`F37B308B36AD`（逐字节全等）；pristine 副本另存 `r579-drill\pristine_r579_tool.py`。

| # | 手法 | 期望 | 现取 |
| --- | --- | --- | --- |
| ① | 逻辑摘掉 `only_in_*` 比对（`--tamper drop-only-in-compare`） | 件必须红 | `rc=1`；`自检: 红（判据 5 第①把的牙不在了）` ＋ `🔴 自检夹具逃掉：一名之差（term=members_agree）——「全等」是硬编码，本件红` |
| ①b | 逻辑摘掉顺序比对（`--tamper drop-order-compare`） | 件必须红 | `rc=1`；逃掉的是**另一枚**夹具：`同成员乱序（term=relative_order_agree）` ⇒ 证明两项互相独立，摘一项仍有一项能判 |
| ② | 指一档不存在的规模（`--action report --sizes 12345`） | `rc≠0` 且点名哪一档 | `rc=4`；`🔴 缺档（不许外推）: {"12345": "没有任何该档读数"}` ＋ `🔴 档位 12345 没有读数` |
| ③ | 在生产库上试图写（`--action guard-proof`） | 件必须拒（写域自护的牙，不靠人守） | `rc=0`；`牙在：12 枚写形状全部拦在出站之前`；逐枚点名 `INSERT`／`UPDATE`／`DELETE`／`CREATE INDEX`／`DROP TABLE`／`COPY … FROM STDIN`／`TRUNCATE`／`VACUUM FULL`／`DO $$ … INSERT`／`SELECT … INTO`／`EXPLAIN (ANALYZE) INSERT`／`WITH DELETE … RETURNING` 全部 `refused=true`；`statements_sent_before_proof=3`（只有 `SET default_transaction_read_only=on`／`SHOW`／`SELECT current_database()`）；会话级与事务级 `read_only` 现读双 `on`；合法读形状照放（`SELECT count(*)`／`EXPLAIN (ANALYZE, BUFFERS)`／`SET LOCAL`／`SHOW hnsw.ef_search`／`BEGIN`／`ROLLBACK`）——**不许把合法的读成本单的罪证** |
| ④ | **物理**摘牙：把 `members_agree = (only_in_exact == 0 and only_in_index == 0 and n_exact == n_got)` 真改成 `members_agree = True`，重跑 | 件必须自红 | `report rc=1` ＋ `🔴 自检夹具逃掉：一名之差（term=members_agree）`；同态下 126 枚钉**当场 8 枚红**（`8 failed, 87 passed`）；还原后 sha256 逐字节全等，重跑 `126 passed` |

第④把的意义：`--tamper` 是件自带的开关，别人可以说"那只是你自己演的一出"；物理改文件之后件**自己**红了，而且离线钉也**自己**红了——两道牙都在，不靠人守。

---

## 8. 判据⑥：清理与零污染（逐枚点名）

**库名集合**（`select datname from pg_database order by 1`）：

| 时点 | 集合 |
| --- | --- |
| 开局 09:36（本席动手之前，`r579_dbset_before.json`） | `eb_r59_sandbox, enterprise_brain, postgres, template0, template1`（5 枚） |
| 中段 10:56（本席库在位；兄弟的 `eb_r575_drill` 已被对方删掉） | `eb_r579_probe, eb_r59_sandbox, enterprise_brain, postgres, template0, template1`（6 枚） |
| 收尾 11:1x（`dropdb eb_r579_probe` 之后） | `eb_r59_sandbox, enterprise_brain, postgres, template0, template1` ⇒ **＝开局那一集，逐枚全等** |
| 再点一次 11:2x（交回前最后一遍） | `eb_r587_restore, eb_r59_sandbox, enterprise_brain, postgres, template0, template1` ⇒ 比开局**多一枚 `eb_r587_restore`**，那是兄弟单（R587 restore 演练）在本席收尾之后建的库，**非本席动作、本席不删他人库**；本席名下 `eb_r579_probe` 与四枚 `sz_*` 已归零 |

- `--action cleanup` 只删 `sz_*`：`dropped_schemas=[sz_0001008, sz_0005000, sz_0020000, sz_0050000]`，`schemas_left=[]`；
- 宿主 `dropdb` 只删**一个名字** `eb_r579_probe`（`rc=0`）；本席没碰任何容器（无 restart／无重建／无 `docker compose up`），没动兄弟的库与树；
- 其他 agent 的库名涨跌由对方支配（本单窗口内实测：`eb_r575_drill` 曾出现又消失，`eb_r587_restore` 在收尾之后出现）。⇒ 判据⑥这句在今天的机器上只能按**「本席名下归零 ＋ 逐枚点名偏差」**来判，不能按「整集与开局全等」来判；把集合差算到本席头上是假指控，放过这一枚是真话。

**生产库前后逐枚同数**（`--action snapshot` → `snapshot_diff`：`all_equal = true`，`unequal = []`）：

| 项 | before（10:56） | after（11:09） |
| --- | --- | --- |
| `chunk_vectors_rows` | 1008 | 1008 |
| `vector_count` | 1008 | 1008 |
| `dimension_prod_min_max` | `[768, 768]` | `[768, 768]` |
| `dimension_declared` | 768 | 768 |
| `vector_scope_rows` | 1 | 1 |
| `vector_scope_digest` | `a278bdb31efc…` | 同 |
| `migrations` | `count=18 / digest=401db40a104e…` | 同 |
| `index_names`／`index_set_digest` | 7 枚同名单／`efb498f2870e…` | 同 |
| `heap_bytes` | 2 015 232 | 2 015 232 |
| `toast_bytes` | 4 128 768 | 4 128 768 |

**临时文件**：只有 `%TEMP%\r579bt`（pytest basetemp，本席专用）＋ 仓外 `C:\Users\fengx\PycharmProjects\r579-drill\`（全部读数、TSV 语料、pristine 副本、篡改备份）。工作树里只剩写域那四枚新文件；`.bak` 中间产物已全部移出仓库树。

---

## 9. 🔴 不可外推声明（判据④，独立成节）

本节是本单唯一"必须与 §5–§6 一起读"的部分。**下面每一条都在限制上面那些数的适用范围。**

1. **合成向量 ≠ 客户语料分布。** 语料是固定 seed 的 LCG 均匀采样再归一化的**单位向量**，768 维，各维独立、无簇、无近重复。真实企业语料的 embedding 有强簇结构（同一文档相邻 chunk 几乎共线）、有近重复、有方向偏置；HNSW 图在**有簇**的数据上通常更容易导航（近邻就是图上的近邻），在**各向同性无簇**的数据上接近最坏导航任务。⇒ §5 那组名次差（0.700／0.305／0.150）是这枚几何夹具上的读数，**是下界方向的示意，不是任何一库的召回率**。
2. **偏置方向未量到。**「真实客户语料会让索引腿更贵还是更便宜」——**本单量不到**。能给的只有两条一手现象：合成单位向量上索引腿在服务端比暴力腿快 30–100 倍（50 000 档 2.18 ms vs 244.2 ms）；名次同时塌（k=5 重合率 0.150）。这中间的**取舍**取决于真实分布的近重复吃不吃候选宽度预算，本单没有那枚数据。
3. **行宽按生产校准，模长分布故意没校准。** 生产 nomic 向量现读模长 17.10–23.40（std 0.889，1008 枚里 987 种不同模长，相对离散 ≈4.4%），本席沙盒一律 1.0。这枚不对称有一个可直接量到的后果：**把合成查询打到生产真语料上，L2 名次被模长项主导**——12 枚互不相同的查询向量只交出 **2 种**不同 top-5（`r579_prod_repro4.json`）；同样 40 枚查询打在单位向量沙盒上，四档每臂都交出 **40/40 种**不同答案。⇒ 合成探针在真语料上是**近退化**的，只测得到"能不能翻到最小的那几枚"，测不到角域导航。本纸所有名次差读数**全部来自沙盒，无一来自生产**。
4. **规模档位是四枚离散点，不是曲线。** 拐点只在 5 000 ↔ 20 000 之间成立，**中间没量**；把它说成"大约 1 万枚翻脸"就是外推，本单不许这样写。
5. **规划器开关是诊断工具，不是生产配置。** `enable_seqscan=off` / `enable_sort=off` / `enable_indexscan=off` 等只在**本席事务内**（`SET LOCAL`，随事务消失），生产 GUC 一个字节都没改。⇒ §5 的"逼索引对照组"给的是**索引腿自己的能力**，不等于规划器在生产上会选它。
6. **候选宽度 100 来自代码缺省派生**（真源现场读数，与遗留引擎同宽那一枚；见 R386／R393 两笔账），不是客户调过的值。换宽度，拐点区间与名次差都会动——本单没量宽度敏感性。
7. **这台机不安静。** 同机在飞四枚（`be-r572`／`be-r573`／`be-r575`／`be-r578`），同一条 SQL 的绝对延迟 19 分钟内能差 2 倍（§2.1）。本纸的**结构性**读数（腿名、`onHNSW`、名次差、比值、sha）不受影响；**绝对延迟数一律不可当基线引用**，要基线得在一台安静机器上重量。
8. **⇒ 全纸不出现、也不允许读者推出"客户机上会怎样"这一类断言。** 这一格现在只能说：**"在 pgvector 0.8.6 ＋ 这台机的代价模型常数下，HNSW 索引腿第一次被规划器选中发生在 5 000–20 000 枚之间；在同一区间它开始丢名次（合成几何上）。"** 到这一句为止。

---

## 10. 没跑的部分（照实写，不补投、不外推）

1. **派工词前提 2**：「单题真机一问 ⇒ `vector_scope.vector_scope_pkey` 的 `idx_scan` ＋10」——**没跑**。它要真打一次端到端问答（会调模型），本单明文「不打模型、不连 11434」。§2.4 那五条环境现读**只证配置与读后端**，**不替代**这条硬凭据。
2. **5 000 ↔ 20 000 之间的细拐点**：没灌中间档（8 000／10 000／15 000／30 000）。
3. **候选宽度敏感性**：只量了真源那一枚（100）。宽度更大／更小时名次差与延迟怎么动——没量。
4. **簇状／近重复语料**：没量（§9 第 1 条的正面版本）。这一枚是下一单最该补的，因为它直接决定"合成下界"离客户有多远。
5. **删除/更新带来的图退化、`n_dead_tup` 影响**：没量（一次性灌满，零写）。
6. **全量回归门**：没跑（本单明文不许）。跑的是本席两枚钉文件：`126 passed`。HEAD 自带的 `tests/test_r253_*` 两枚红与本单无关，未触碰。
7. **第一轮量测（`r579_measure.json`）没重跑**：它作为**仪器对照**留在纸里（§3.1），**不作为判据②的数**——判据②用的是重灌＋修协议之后的 `r579_measure_main.json`。

---

## 11. 给总控：这一格现在该怎么改写口径

1. 🔴 **跟进单 §151／本板 §4EJ 那句「PG 索引＝精确 105/105」必须降级**——本席一手：那 105 题的 PG 腿走的是全表精确解（`Seq Scan`＋top-N heapsort），HNSW 图**一次都没被选中**（生产 1008 枚实测，§2.1）；而且"索引腿＝精确解"这个读数形状**已被证明是仪器可造的假绿**（§3.1，同连接计划复用）。那句话既没量到索引，也不能拿来当索引质量的凭据。
2. **计划书 §9.3「客户尺寸两档差」那一格第一次有了数**，但形状是**拐点＋拐点两侧名次差**，不是原来说的"索引等不等于精确解"：
   - 拐点区间：**5 000 ↔ 20 000 枚**（分析态；未分析态四档全走 btree-bitmap，另一族腿，量不到）；
   - 拐点之前（≤5 000）自然腿是全表 ⇒ 精确解，名次差 = 0，服务端延迟随行数涨（7.2 → 37.2 ms）；
   - 拐点之后（≥20 000）自然腿是 HNSW ⇒ 服务端延迟被钉在 2–5 ms 量级，代价是合成几何下 k=5 重合率只有 0.305／0.150。
3. **翻默认读后端这件事的判据不受本单影响**：本单没量服务内端到端、没量让路延迟；§9.3 那几格（格②热集让路、格③生产标签回填）照原样欠着。
4. **下一单的形状建议（不是本单范围）**：4 档换 8 档（补 8 000／10 000／15 000／30 000）＋ 灌一枚**簇状语料**（同文档 chunk 共线＋近重复）＋ 宽度敏感性（真源那枚 ± 一档），并且**必须**带 `--prepare-threshold none` 与真热身——否则又会拿到一个看着像绿的 1.0000。

---

## 附 A：盘面与工作树卫生

```
git -C C:\Users\fengx\PycharmProjects\be-r579 rev-parse HEAD    -> b85c2774c4dc279d1a4014acb88cfba0a35ba9ea
git -C ...\be-r579 status --porcelain                            -> 只有下面四枚未跟踪
git -C ...\be-r579 diff --numstat                                -> 空（四枚全是新增，未 git add）
```

| 文件 | sha256（前 12） | 说明 |
| --- | --- | --- |
| `scripts/r579_index_crossover_readout.py` | `F37B308B36AD` | 件本体（12 枚动作；写域守卫；三相位；比值门） |
| `tests/test_r579_readout_teeth.py` | `0aadf81a206f` | 常驻牙（离线，假连接，一条真 SQL 都不出站） |
| `tests/test_r579_synthetic_provenance.py` | `6183073554a8` | 合成语料与在册件同源的逐枚对账 |
| `docs/perf/r579-index-crossover-2026-10-03.md` | —（本纸不自记：纸里的自 hash 落笔即失效，终值在交回单，由总控收单时取） | 本纸 |

写域之外**一个字节没改**：`app/**`、`frontend/**`、`migrations/**`、`deploy/**`、`docs/handoff/**`、评测集、`scripts/r59_recall_compare.py`、`scripts/r59c_sandbox_corpus.py`、`app/rag/pg_store.py`（三枚只 import／读）、`chroma_db/**`、`pyproject.toml`、`uv.lock`。未 `git add`／`commit`／`push`；未 restart／重建任何容器。

## 附 B：件的动作清单（`--action`）

| 动作 | 连哪儿 | 干什么 |
| --- | --- | --- |
| `plan`（缺省） | 不连 | 只打印打算发什么，零外溢 |
| `snapshot` | 生产只读 | 12 项存量恒量（行数／向量枚数／维度／`vector_scope` 行与指纹／迁移集合与指纹／索引名单与指纹／heap 与 toast 字节）＋ 逐索引 `idx_scan` |
| `repro` | 生产只读 | 判据①三行读数（三臂同形状） |
| `db-set` | `postgres` | 库名集合逐枚点名 |
| `guard-proof` | 生产只读 | 12 枚写形状必须全拦在出站之前 |
| `build` | 沙盒 | 建 `sz_*` 四档＋同参索引，`--replace` 才重建 |
| `measure` | 沙盒 | 四档 × 两态 × k∈{5,20} × 三臂 |
| `report` | 不连 | 由 measure 产物出表（`--tamper` 两枚逻辑摘牙；缺档 `rc=4`；摘牙 `rc=1`） |
| `repeat-probe` | 沙盒 | 同一枚问题连打 N 次，逐臂 `distinct_answers` |
| `emit-data` | 不连 | 最大档 TSV 落仓外＋逐档前缀 sha256 |
| `cleanup` | 沙盒 | 只删 `sz_*`，并把那条 `dropdb` 原话交回宿主 |

`--expect-ef-search` 对账不上 ⇒ `rc=2`（整单不量）；`--sandbox-db`/`--db-prefix` 之外的库名一律 `SandboxTargetRefused`；`--prod-db` 不在受保护名单 ⇒ 直接拒（否则写域守卫失去凭据）。

## 附 C：产物清单（`C:\Users\fengx\PycharmProjects\r579-drill\`）

| 文件 | 是什么 |
| --- | --- |
| `r579_measure_main.json` | 🔴 判据②主产物（16 条，每条 40 枚计时样本，`prepare_threshold=none`） |
| `r579_report_main.txt`／`.json` | 主表原文（§5.1）／机读版 |
| `r579_measure.json`／`r579_report_run1_control.txt` | 仪器对照：psycopg 缺省 prepare 阈值下那 14 行 `idx!`（§3.1） |
| `r579_build2.json` | 四档灌数账（建索引秒数、列对齐、`data_sha256`） |
| `r579_corpus_50000.tsv` | 最大档语料字节流（413 100 126 B，sha256 与灌库逐字节全等） |
| `r579_prod_repro3.json`／`r579_prod_repro4.json` | 现网三行读数：无真热身那轮（冷 169 ms 抓现行）／有真热身那轮（§2） |
| `r579_prod_repro.json`／`r579_prod_repro2.json` | 更早两轮（同一结论，冷读数 37.0 ms 那枚在 repro2） |
| `r579_prod_before3.json`／`r579_prod_after.json` | 判据⑥生产 12 项前后对账（`all_equal=true`） |
| `r579_dbset_before.json`／`r579_dbset_before3.json` | 库名集合开局／中段 |
| `r579_guard_proof2.json` | 写域牙（12 枚写形状全拦） |
| `r579_repeat_probe.json`／`r579_probe_pass1..5.json` | 决定性排除：pgvector 逐次同答（`distinct_answers=1`） |
| `r579_cleanup_final.json` | 只删 `sz_*` 的四枚点名 |
| `pristine_r579_tool.py`／`tamper_target_backup.py` | 物理篡改前的逐字节副本（还原凭据） |
| `r579_ce1_drop_only_in.txt`／`ce2_drop_order.txt`／`ce3_missing_size.txt`／`ce4_physical_tamper.txt`／`ce4_teeth_under_tamper.txt` | 反证原文（`rc=1／1／4／1` ＋ `8 failed, 87 passed`） |
| `r579_measure_smoke.json`／`r579_build_1008.json`／`r579_report_table.txt` 等 | 施工期冒烟件（协议修好之前，不作任何判据凭据） |
