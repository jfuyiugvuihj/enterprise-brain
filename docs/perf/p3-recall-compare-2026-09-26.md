# R264 · pgvector P3 影子读对照读数（2026-09-26）

- 单号：R264（= 计划书 §3/§8 的 P3 影子读对比，R58 之三）· 只读 · **不切流量**
- 工作树：`C:/Users/fengx/PycharmProjects/be-r264`　分支：`codex/be-r264`　基点：`8613dc7`
- 窗口：2026-09-26 11:57 – 12:12（本地）= 03:57 – 04:12 UTC　执行人：执行层 Agent（R264）
- 本班**未**停写、**未**打开生产目录 `/app/chroma_db`、**未**跑 migrate、**未**改树、**未** commit
- 逐题清单与机器可读读数：`docs/perf/raw/p3-2026-09-26/`（本目录＝本单唯一附加交付）

## 0. 结论（三档选一）

**不可切读。** 但欠的三格没有一格在 PG 镜像身上——镜像这一侧本次零欠账：

| # | 欠的格 | 为什么算欠 | 归谁 |
|---|---|---|---|
| 1 | `must_contain` 查无出处 **29 条未清零** | 计划书 §8.8 白纸黑字：复算仍给非零 ⇒ 这一轮**只是影子读的技术差集**，不是跟进单 §22.2 R58 判据③ 要的验收证据。本班 09-26 现场复算仍 = 29 行 / 29 词（证实手册注的"55 是旧数"） | 清零那一单（业主批准改评测集，看板 §4BT 七②） |
| 2 | **权限过滤下推的语义等价未测** | 本轮两腿都是**无 `WHERE` 的裸检索**。§3 P4 要求 `owner_id/department/classification` 下推后仍"先按权限过滤，后去重"，R45/R57 越权用例逐条平移 | R59 |
| 3 | **密级口径未裁（U5 / H13）** | `classification` 缺省算公开还是算不可见业主未裁 ⇒ 下推 SQL 今天写不出来 | 业主 |

反向的一条更要紧：**本次读数是"现网 Chroma 读路径有缺陷"的证据**，不是"镜像召回退化"的证据。见 §3 归因四行——105 题里 21 题现网 Chroma 直接返回**空 top-5**，而 pgvector 腿在 105/105 题上等于同一份数据的精确解。

## 1. 判据① · 前置三查（现场实取，非引用）

```
# 0010 在位（生产 head 到 0013；0014/0015 未上生产）
0010|pgvector_chunks|abc4f16d25fec72e174305c95589c1cb9475245856be0ab0035082279176d6d3|2026-09-18 12:22:20.779903+00
# vector_scope（本库唯一口径）
nomic-embed-text|768|l2|2026-09-18 12:22:20+00|2026-09-22 00:08:29+00      column_type=vector(768)
```

- **全零向量普查（两侧各一份）**
  - Chroma 侧：`rebuild_index.py --status --json` → `census_measurable=true`、`zero_vectors_before=0`、`cross_dimension_vectors_before=0`、`vectors_read=1008 == store_vectors=1008`、`pages_read=6`（page_size 200）、`zero_vector_documents=[]`。**先读 measurable 再读数**，这一格是真测出来的，不是 `null` 当 0。
  - PG 侧：`all_zero_rows=0`（零值字面量按 `vector_scope.dimension` 现拼），逐行清单（§8.6 那条 `WITH z AS ...`）**为空**；另 `embedding IS NULL=0`、`vector_dims min=max=768 distinct=1`。
- **`VECTOR_DUAL_WRITE` 现场值 = `on`**（backend / worker / scheduler 三处 `printenv` 均为 `on`，来源 `deploy/.env.server:56`）。
  🔴 **这与派工词写的"双写当前关着"相反**：`docker-compose.yml:161/204/241` 的 `${VECTOR_DUAL_WRITE:-off}` 只是**没赋值时的默认**，现场被 env 文件覆盖了。⇒ 脚本前置第 3 条（双写开着且完整重建过）今天**成立**，本班因此没有触碰任何开关。
- 三查全绿，才有下面的读数。任何一项取不到本班就会停在门口报数。

## 2. 判据② · 两侧来源各自自证（误判 #43 的正面对症）

**PG 腿**（`psycopg.Connection`，连上即 `read_only=True`）

```
client dsn  postgresql://enterprise_brain:***@postgres:5432/enterprise_brain
info.host   'postgres'  info.port 5432  info.dbname 'enterprise_brain'
server      inet_server_addr=172.18.0.7/32:5432   data_directory=/var/lib/postgresql/data
            SYSTEM_IDENTIFIER=7685285828163473446   server_version=16.15   vector 0.8.6
            databases=enterprise_brain,postgres,template0,template1
trap        容器内 127.0.0.1:5432 connect_ex=111 (REFUSED)
```

- **不是宿主那台野 PostgreSQL**：误判 #43 的野库今天仍在位（宿主 `0.0.0.0:5432 LISTENING` pid 9036，12 枚 `postgres` 进程今晨 10:25/10:26 起），但 5432 **未向宿主发布**，且本班整条链路跑在 backend 容器内 ⇒ 容器里 `localhost:5432` 直接 ECONNREFUSED，**结构上连不到**。身份再由 `SYSTEM_IDENTIFIER` + `data_directory=/var/lib/postgresql/data` 双钉锁定。
- **"这次真读到库没有"**：`chunk_vectors=1008`、`chunks=1008`、`index_version_id IS NULL=0`（R76 回填已结清）、`vector_dims distinct=1`。任一为空即 `exit 3` 报错退出，不许静默算 overlap。

**Chroma 腿**（生产卷快照，`chromadb 1.5.9`）

- 存储身份：`chromadb:///tmp/p3snap#enterprise_docs`，来源＝docker 卷 `enterprise-brain_vectordb` → 容器内 `/app/chroma_db` 的 `cp -a` **字节级快照**（6 枚文件 / 251,908,236 字节）。
- **字节等同证明**：`sha256sum` 逐文件对账 活目录 vs 快照 = 全等；跑完再取活目录 = 与开局全等（`LIVE-UNCHANGED` × 3 个回合）。
- 🔴 **本班全程没有打开生产目录**。理由不是保守，是计划书 §8.6 自己写的：Chroma 目录只要被新进程打开就会自己重写一遍索引与 sqlite；服务还持着它时抢开＝未知状态。而 §8.2 的停写（`stop backend worker scheduler`）不在本单授权内（会改现网环境），所以走脚本 `:14-21` 前置第 1 条明允许的**另一条路：只读副本 / 目录快照**。
- 顺带把 §8.6 那句话复现了一次：快照被 census 打开后，`chroma.sqlite3` 的 mtime 从 `2026-09-25 17:51:57` 变成打开的那一刻，HNSW 三件套 mtime 未动。**这就是不能对活目录动手的原因。**
- **"这次真读到库没有"**：`collection.count()=1008`、`get()` 全量 id=1008、回读一枚得 768 维向量＋metadata。为 0 直接 `exit 3`。
- 空读/降级必须当场报错——故意打错 + 空库负控（原文见 `raw/summary.json`）：
  - `--chroma-dir /tmp/definitely-not-here` → `[前置不满足] Chroma 目录不存在…（不要新建）`，**没写出任何 out 文件**；
  - `--collection enterprise_brain_wrongname`（把库名当集合名）→ `[前置不满足] 取不到 collection …`，同样不出文件。
  - ⚠ 两枚退出码都是 **1 不是 2**，见 §7。
  - **第三枚＝空库负控**（09-26 现场加做，直指误判 #43 为什么能算出漂亮的 1.0）：在一次性容器的 `/tmp` 里造一个**名字对、目录真、一枚向量都没有**的沙盒 collection（`enterprise_docs` count=0；生产卷仍一字未动，收尾 sha 复核 `LIVE-UNCHANGED-NEGCTRL`），两腿对着它重跑——

        官方脚本  EXIT=2  [前置不满足] collection 距离=measured，vector_scope 声明=l2
                              U1 判读：样本只有 0 枚，少于 12 —— 按前置不满足处理   ← 且没有写出 --out 文件
        本班腿    EXIT=3  🔴 [空读] Chroma 腿一条都没读到 —— 退出（上一班那种沙盒数就是这么混进来的）

    ⇒ "降级/空读必须当场报错退出、不许静默算 overlap" 这一格是**看着它响过一次**的，不是嘴上承诺。顺带钉一条：官方脚本撞上空库时报的因是"两边排序天然不同"，真因却是"库里 0 枚样本可测"——**码 fail-closed 判对了，诊断文案是错的**。

## 3. 判据③ · 真 top-k 对照（同题·同 k·canonical 拼法统一之后）

比对在 `canonical_distance()` 统一拼法之后进行：`vector_scope.distance_function=l2` → canonical `l2`；Chroma 侧 metadata 为空 ⇒ U1 **实测**（样本 64 枚、探针 2 枚、命中 `['l2']`、来源=measured）→ `l2`。两侧一致，算符 `<->` / `vector_l2_ops` 与索引 `chunk_vectors_embedding_idx USING hnsw (embedding vector_l2_ops) WITH (m='16', ef_construction='100')` 同源。题面 `tests/fixtures/business_evaluation_100.jsonl`（sha256 `2230b2b4…`，只读挂载进容器，本班未改一字）。

**第一轮 · 语料级差集**（`--skip-questions`，退出码 0）

```
pg_vectors 1008   chroma_vectors 1008   chunks_rows 1008   chunks_with_backfilled_embedding 1008
only_in_pg 0      only_in_chroma 0      wrong_width 0      all_zero_rows 0   index_version_id_null 0
```
⇒ 误判 #43 那笔"差 607 枚"的账彻底作废，两侧条数与 id 集合**完全相等**。

**第二轮 · 逐题 top-5**（105 题，退出码 1＝有差异，属正常结论）

| 指标 | 读数 |
|---|---|
| mean_overlap（集合交集 / k） | **0.7238** |
| mean_jaccard | 0.6830 |
| 逐位全等 | 55/105 |
| first_diff_rank 分布 | 0 名 → **32 题**；1 → 8；2 → 5；3 → 5；一致 → 55 |
| **Chroma 返回空 top-5** | **21/105** |

- 21 题题号：`doc-09 doc-13 metric-04 metric-05 metric-10 metric-11 metric-13 metric-18 metric-19 data-08 insight-02 insight-06 chart-04 approval-06 scope-01 scope-03 scope-05 scope-06 tool-01 tool-04 report-12`
- 逐题清单（105 行，含 overlap / jaccard / first_diff_rank / 两腿 id / 是否属 29 条无出处）：`docs/perf/raw/p3-2026-09-26/per-question-k5.tsv`
- 两轮 `--out` 原文件：`r58_drift.json`、`r58_recall_diff.json`（同目录）

**按 §8.8 的切刀切一刀**（先复跑 `check_eval_evidence_coverage.py`：29 行 / 29 词，主口径 `documents/*.txt` 95 篇，与手册一致）

| 子集 | n | mean_overlap | 逐位全等 | Chroma 空表 |
|---|---|---|---|---|
| 全部 | 105 | 0.7238 | 55 | 21 |
| **剔掉查无出处 29 条** | 76 | **0.6947** | 37 | **17** |
| 只剩那 29 条 | 29 | 0.8000 | 18 | 4 |

⇒ 差异**不是**评测集无出处造成的：把 29 条剔掉，overlap 反而从 0.7238 掉到 0.6947，空表从 21 掉到 17（只少了 4 题）。

**归因四行**（同 105 题、同 k=5；每行都是"某一腿 vs 一份精确 L2 扫描"）

| 对比 | mean_overlap | 逐位全等 | 零重叠 |
|---|---|---|---|
| `chromadb HNSW` vs **它自己那份数据**的精确解 | 0.7238 | 55/105 | 21 |
| `pgvector HNSW` vs **它自己那份数据**的精确解 | **1.0000** | **105/105** | 0 |
| 两份数据的精确解互相（与引擎无关的数据面） | **1.0000** | **105/105** | 0 |
| 两引擎实际输出互相（= 上面第二轮的数） | 0.7238 | 55/105 | 21 |

一句话：**第一行与第四行逐字相同** ⇒ 跨引擎的全部差异，等于 Chroma 腿与自己那份数据的差距；镜像与引擎都不背这个账。

**数据面是否同一枚（官方脚本只比 id 集合、不比数值，本班补测）**

- 1008 枚共有 id 中**逐位全等 0 枚**，都存在差异，但单元素最大绝对差 **2.17e-07**（float4/float64 表示级）。
- 这份噪声**没有换过任何一次名次**：两侧各自的精确 top-5 在 105/105 题上完全相同。

**Chroma 侧索引取证（为什么是它的问题）**

- 拿库里 1008 枚向量自己当探针问自己（l2 下距自己=0，只要在索引里且可达必排第 1）：**138/1008 取不到自己**；"距离 0 但换了名"（并列顶替）**0 例**。分布：`深度学习入门…pdf 126/586`、`AI-Agent学习路线图.pdf 2/23`、`ISO27001…txt 2/4`、`MYBI_数据模型设计文档.txt 2/5` …
- 21 道空表题的精确 top-5 里只有 **6/105** 枚落在这 138 枚内（15 题的精确近邻**全部可达**）⇒ 空表与不可达是同一份持久索引的两个症状，但**不是**"要的邻居没进索引"这一因。逐题探针原文见 `raw/same-source-control.json` 与 §3 表；根因在 Chroma 内部，不属本单写域。
- 探针题的向量本身没问题：`len=768 nan=0 inf=0 norm≈21.1–23.3`，且 `n_results=50` 仍返回 0 条；同一题 pgvector 与精确扫描**逐条全等**。

## 4. 判据④ · 同源反证（钉，不是可选项）

判定机制：**provenance.storage 相同 ⇒ 判两侧同源，数字一律作废**。storage 键取法：PG 腿 `postgres://<inet_server_addr>:<port>/<db>#<table>`，Chroma 腿 `chromadb://<realpath>#<collection>`；把任一腿换成"同一份库上的 numpy 全库暴力"时，它的 storage 仍指向那份库 ⇒ 立刻被认出。

```
[real]  左 chromadb:///tmp/p3snap#enterprise_docs   右 postgres://172.18.0.7:5432/enterprise_brain#chunk_vectors
        两腿不同源（pgvector 引擎 vs chromadb 引擎）：mean_overlap=0.700 逐位相同 3/10

[chroma_vs_chromabrute]  右腿 = numpy 全库暴力，跑在同一份 Chroma 快照上（= 误判 #43 第三行的形状）
        🔴 两侧同源（storage 同一个）：mean_overlap=0.700 —— 同一份数据自己比自己，不构成任何切读证据，读数作废

[pg_vs_pgnumpy]  左腿 = numpy 全库暴力，跑在同一张 chunk_vectors 上
        🔴 两侧同源（storage 同一个）：mean_overlap=1.000 逐位相同 10/10 —— 读数作废
```

- 两枚同源控制**均被认出**，真跑那一格判为不同源 ⇒ 反证钉生效（`harness samesource` 在控制没被认出时返回 4 并判失败，不是只打印一行字）。
- 顺带把上一班那个漂亮的 `mean_overlap=1.0` 的形状**现场复刻**了一次：`pg_vs_pgnumpy` 就是 1.000。而 `chroma_vs_chromabrute` 只有 0.700 ⇒ **"同源"甚至不保证给出 1.0**，所以 1.0 好不好看根本分不出真假，能分清真假的只有来源身份这一格。

## 5. 判据⑤ · 镜像落后的影响评估

- 现场 sha256：镜像内 `/app/scripts/compare_vector_recall.py` ＝ 树上 `/tree/scripts/compare_vector_recall.py` ＝ `9e0e81cfa4fa719f8e7645461177adafd54feae982655ba7a14b2be8b8be42eb`；git blob 在 `75d9a6d`(镜像 rev) / `8613dc7`(本基点) / `7e2a0d5`(主树 HEAD) 三处同为 `b5436b5`。
- 承重脚本 import 链同样逐枚比过：`app/rag/pg_store.py` `a30a47e1` SAME、`app/db/connection.py` `390b4066` SAME、`app/rag/retriever.py` `a59aaa13` SAME（题向量由它的 `OllamaEmbeddings` 产出）、`app/rag/indexing.py` `b55b90df` SAME、`app/common/logger.py` `0931d8bd` SAME、`scripts/rebuild_index.py` `0e0f5ec0` SAME、`migrations/0010_pgvector_chunks.sql` `b2adbca7` SAME。
- ⇒ **读数不降级**：这条链上没有一枚依赖件在镜像与树之间不同。**没有**重建镜像、**没有** `docker compose build`。
- 落后的确有、但落在别处：镜像 rev `75d9a6d` 落后主树，生产库 head 只到 **0013**（树上 0014/0015 未上生产）⇒ 所有 `compose run` 一律带 **`--no-deps`**，否则它会先满足 `depends_on: migrate` 而**替我改库**。这是本单最险的一处环境陷阱。

## 6. 判据⑥ · 结论

**不可切读**（见 §0 三格欠账）。同时必须写清另一半，否则这条结论会被读反：

- 镜像侧：**数据面与现网等价**（id 集合全等、精确 top-5 在 105/105 题上全等、值差仅 float 表示级），且 pgvector HNSW 在 105/105 题上**等于精确解**——这一维上"切读会退化"今天没有证据。
- 现网侧：本次读数**反过来**是"Chroma 读路径有缺陷"的证据（21/105 空 top-5、138/1008 自探针不可达）。切读一旦落地，这 21 题的 0 命中就会消失；不切读，客户今天就在承受它。
- 但 §8.8 的规定优先于这份好读数：**29 条无出处未清零之前，本读数不是 R58 判据③ 的验收证据**，只是影子读差集。门禁仍在清零那一单。
- 不需要"先全量重建再比"：两侧条数/id/值/全零/宽度五格全等，重建不改变任何一格；要重建的（如果要）是**现网那 1008 条 Chroma HNSW 索引**，那是遗留件的病，不是镜像的病。

## 7. 交回时要点名的三处"文档/派工词与现场不符"

1. 🔴 `VECTOR_DUAL_WRITE` 现场是 **on**（三进程一致），派工词据 `docker-compose.yml` 的 `:-off` 推成"关着"——compose 默认值不等于现值，这类数必须 `printenv`。
2. 🔴 **退出码契约与实现不符**：脚本 docstring 与 §8.9 写"`2`=前置不满足"，实测六条前置里**只有"距离不一致"那格** `return 2`，其余五格 `raise SystemExit("字符串")` ⇒ 退出码 **1**，与"`1`=有差异"撞车。照 §8.9 用退出码分诊的自动化会把"根本没跑成"读成"跑成了、有差异"。（反向的坑也在：真正会返回 2 的那格，撞上空库时报的因写成"两边排序天然不同"，真因是"库里 0 枚样本可测"——码对、文案错，见 §2。）
3. ⚠ `tests/fixtures/business_evaluation_30.jsonl` 在本基点 `8613dc7` 与主树 HEAD `7e2a0d5` 之间**字节不同**（`fd89f5f7…` vs `9efb9cf6…`），而 `_100.jsonl` 同一枚。本单只用 `_100`，未受影响；评测集被动过这件事请总控核对是否已获授权。

## 8. 复现（逐条只读；容器一律 `--no-deps`）

```bash
DC='docker compose --env-file deploy/.env.server -f docker-compose.yml'
# 三查（只贴 SELECT）
$DC exec -T postgres sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F"|"'   # 见 §1
$DC exec -T backend   printenv VECTOR_DUAL_WRITE     # worker / scheduler 同
# 对照：一次短生命周期容器，生产目录只 stat + cp，绝不打开
$DC run --rm --no-deps -T \
  -v "$PWD/..:/tree:ro" -v "$SCRATCH:/drv" \
  backend sh /drv/driver.sh
#   容器内顺序：sha256(活目录) → cp -a → sha256(快照) 对账
#   → rebuild_index.py --status --json --chroma-dir /tmp/p3snap --chroma-collection enterprise_docs
#   → compare_vector_recall.py --skip-questions --collection enterprise_docs --chroma-dir /tmp/p3snap --k 5 --out …
#   → 同上去掉 --skip-questions、加 --fixture /tree/tests/fixtures/business_evaluation_100.jsonl --all
#   → 同源反证 + metrics → 两枚故意打错的闸 → 收尾再 sha256(活目录) 对账
```

驱动与取证脚本在 `%TEMP%\p3r264\`（`driver.sh`/`driver2.sh`/`driver3.sh`/`p3_harness.py`/`run2.py`/`run3.py`），按单不交回；它们只 import `compare_vector_recall.py` 本体（`connect_read_only` / `read_scope` / `open_chroma` / `resolve_chroma_distance` / `canonical_distance` / `pg_recall` / `_zero_literal`），一个判据都没另抄。

## 9. 需要总控处置的移交项（本班写域外，一律没动）

- 🔴 **现网 Chroma 读路径缺陷**（新立单）：`enterprise_docs` 1008 枚中 138 枚自探针不可达，105 题里 21 题 `query()` 返回空 top-k；`collection.metadata=None`、单 segment `0c4b1056-…`，sqlite mtime 停在 09-25 17:51（容器重启时刻）、HNSW 三件套停在 09-25 09:29。**注意这是用户今天正承受的症状，不是遗留件的归档噪音。**
- 🔴 `deploy/.env.server:56` 双写实际 `on`：§8.10"结论交回后拨回 off"是业主动作，本班不碰；但台账要改口径。
- ⚠ 生产库 head=0013，树上 0014/0015 未上生产 ⇒ 任何 `compose run`（含跑分窗）都必须 `--no-deps`，或先由业主决定要不要补迁移。
- ⚠ `compare_vector_recall.py` 退出码 1/2 契约（§7.2）：属量具，改它要连 §8.9 的读法一起改。