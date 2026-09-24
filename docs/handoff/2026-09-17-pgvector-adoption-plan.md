# PGVector 添加计划（可执行版 · 2026-09-17 22:2x · 总控第七班）

> **三份文档的分工**（不一致时以本文件为准）：跟进单 §22 只写「立案与验收判据」，计划书 §5.2 只写「单号索引」，
> **本文件写「怎么加」**。业主两问（为什么还是 Chroma / 怎样不留风险地完成）在第 0 节直答。
> 本文件全部内容基于只读实测，出处一律 `文件:行`；未经复跑的数字不写。

## 0. 两问直答

- **为什么今天还是 Chroma 而不是 PostgreSQL+pgvector？**
  一句话：**PG 侧只有表骨架，向量这条腿三样都不存在——没有可写的定标向量列、没有任何向量索引、运行时没有一个写入方。**
  扩展镜像倒是早拉好了（`docker-compose.yml:48` = `pgvector/pgvector:pg16`），属于「插座装好了，线没接」。
  而切换的**前置两单 R21 / R22 至今零代码提交** `[实测 git log --all --grep]`：向量本身还不可信（失败静默换全零），
  索引版本也没有和 `embedding_model + dimension` 绑定。这两件事不结，迁过去＝**给脏数据换个更贵的存放点**。
- **怎样不留风险地完成？**
  一句话：**先打地基（P0），再走「加列建索引 → 同事务双写 → 影子对比 → 显式切读 → 停写退役」，每一步一个独立回滚点，
  任何一步不过就停在原地**。硬约束是：**任何时候都不允许出现「元数据在 PG、向量在 Chroma」或「向量在 PG、权限过滤还在内存里」这两种中间态过夜**——
  那是唯一会让私有化交付不可回滚的东西。

## 1. 现状事实基线（本班实测，只读）

| 事实 | 出处 |
|---|---|
| PG 扩展镜像在位，但运行时没人用它做向量 | `docker-compose.yml:48` |
| 迁移体系是真的、且 fail-closed：`NNNN_name.sql` + `manifest.json` SHA-256 + advisory lock，缺登记/改内容即拒 | `migrations/README.md:1-27`、`migrations/manifest.json`(9 条)、`app/db/migrations.py`、`scripts/migrate.py` |
| `chunks.embedding` 声明**无维度** ⇒ 既不能建索引，也拦不住混维度 | `migrations/0002_execution_data_lineage.sql:235-243` |
| 旧运行时表存的是 `embedding JSONB`，不是向量类型 | `migrations/0003_legacy_runtime_tables.sql:77` |
| 全仓迁移里 `hnsw` / `ivfflat` **零命中** ⇒ 没有任何向量索引 | `grep migrations/*.sql` |
| 索引层自己承认不写向量：「every row it writes leaves `chunks.embedding` NULL」，chunk 行模型也故意不含 embedding | `app/rag/indexing.py:8`、`app/rag/indexing.py:302` |
| `pgvector` 在 `app/**` 只有两处**元数据级**用法：取值校验 + 存在性探测，都不开 PG 连接做向量读写 | `app/rag/indexing.py:203`、`app/common/monitoring.py:272` |
| 向量读写 100% 走 Chroma，且依赖缺失时静默退化 JSON 文件库 | `app/rag/retriever.py:190`(PersistentClient)、`:246`/`:261`(写)、`:272-273`(读)、`:93-116`(`_JsonCollection`) |
| 维度是**隐式常量**：全仓唯一的维度声明藏在失败兜底里 `[0.0] * 768`，且没有任何地方校验 API 真实返回长度 | `app/rag/retriever.py:46`（模型名 `:23` = `nomic-embed-text`） |
| 失败静默降级为全零向量并照常入库（这就是 R21） | `app/rag/retriever.py:63-65`、`:76` |
| PG 驱动依赖**已经在** pyproject 里，不需要新增包 | `psycopg[binary]>=3.2.0`、`psycopg-pool>=3.2.0` |
| R21 / R22 零代码 | `[实测] git log --all --grep` 仅命中两条 docs 提交 `6c5ccd9`/`497b500` |

## 2. 终态口径与「不得误写生产架构」的解绑条件

- 终态：chunk 元数据 + 向量 + 权限过滤**同引擎**（PostgreSQL + PGVector），Chroma 退役；本地文件存储与 Redis 不变。
- AGENTS.md 明令「当前 Chroma 是过渡向量库，不能在文档或新设计中误写成最终生产架构」。**解绑条件只有一个**：
  P5（R60）结案 **且** 备份恢复演练覆盖 PG 向量列。在那之前，本文件与一切新增文档一律写「过渡中」，
  `docs/current-functionality-2026-09-10.md:1217` 那句「过渡架构」**不许提前改掉**。

## 3. 六个阶段（顺序不可交换，不可并行）

### P0 地基 —— R21 + R22（前置，缺一律不开工）
- **R21**：embedding 失败**不得**静默换全零。落点 `app/rag/retriever.py:51-77`：`_call_api` 失败即抛并留可观测原因；
  写入侧（`:246` 前）拒收全零与长度 ≠ 声明维度的向量。**反证要求**：把 `raise` 改回 `pass`，测试必须红。
- **R22**：索引版本绑定 `embedding_model + dimension`。落点 `app/rag/indexing.py:191-216` 的 `create_version`——
  今天它连 dimension 参数都没有（§1 已证「全仓无 dimension 配置」），所以 R22 的**第一动作是把这个概念引进代码**，
  不是改索引。要求：模型或维度变 ⇒ 产生新 `index_version`；同库禁混维度（跨维度查询 0 命中）；
  给全量重建 CLI，**只许人工触发**。
- **回滚点**：本阶段不改存储，代码级回滚即可。

### P1 定标与建索引 —— R58 之一（真机）
- 新增 `migrations/0010_pgvector_chunks.sql`，并在 `migrations/manifest.json` 登记 SHA-256（**漏登记 = loader 直接拒**，README 明写）。
- 三件事：① `chunks.embedding` 定标为 `vector(<dim>)`；② 加 `CHECK (embedding IS NULL OR vector_dims(embedding) = <dim>)`，
  把 §1 那个隐式 768 变成显式约束；③ 建向量索引。
- **索引选型（已决，写死免得执行层再猜）**：`hnsw`。理由：语料量级小（96 篇）、插入即可用、无需训练样本；
  `ivfflat` 在 `lists` 未训练时召回不稳。若真机 P95 不达标，回来走 §5 的 U2 重评。
- **距离算符（未决 U1）**：必须先实测 Chroma collection 的 distance function，再决定 `<=>`(cosine)/`<->`(L2)/`<#>`(ip)；
  **算符与 Chroma 不一致 = 后面所有召回对比全部作废**，禁止拍脑袋选。
- 存量行 `embedding IS NULL` 对建列与建索引都安全（HNSW 不索引 NULL），但**P1 之前必须先做全零向量普查**（P3 前置动作①，提前跑）。

### P2 同事务双写 —— R58 之二
- 新增 `app/rag/pg_store.py`（用已在树的 psycopg 3）；`DocumentRetriever` 写入路径改为 **Chroma 与 PG 同事务双写**，
  任一失败整体回滚（fail-closed）⇒ 从机制上杜绝 §0 说的第一种危险中间态。
- **禁改**：`app/rag/retrieval_pipeline.py`（R57 已结案文件）、BM25 腿、`_JsonCollection` 之外的降级路径。
  借双写之名顺手改检索编排的单，一律退回。
- 写域与本线在途单**零交叠**（R56=`tests/**`、R62=`app/common/rbac.py`）。

### P3 影子读对比 —— R58 之三（不切流量的唯一验证手段）
- 逐题对比脚本：同一 105 题、同一 query，分别走 Chroma 与 PG，产出 rank/命中差异表。
- **前置动作① 全零向量普查**（Chroma 侧与 PG 侧各一份清单）；**前置动作② 55 条 `must_contain` 无出处清零**
  （本线**未独立复跑**该结论，故第一步是复跑确认，不是照抄）。
- 评测集被 `tests/test_evaluation_report.py` 钉着，**迁移期间禁止为凑绿改 `must_contain`**。

### P4 切读 —— R59（唯一改用户可见行为的一步）
- 开关：默认仍 Chroma，切读必须显式赋值；配置项新增走代码默认值，**Agent 不改 `.env`**。
- 权限过滤下推 PG `WHERE`（`owner_id` / `department` / `classification`）。
  ⚠ **语义等价性硬要求**：R45/R57 已定的口径是「**先按权限过滤，后去重**」（`app/rag/retrieval_pipeline.py`），
  下推后过滤必须发生在**去重之前**的同一位置；R45/R57 全套越权用例逐条平移且全绿，**禁改断言迁就实现**。
- 🔴 **排期冲突（本班新发现，之前没记）**：R59 的写域含 `app/api/v1/chat.py`，而在途 **R35 正在改 `chat.py` 缓存段** ⇒
  **R59 严禁先派，必须等 R35 结案合并**。这是真写域冲突，不是保守。
- 召回不退化以 R36 的 105 题基线为证。

### P5 停写与退役 —— R60
- 停 Chroma 写；`chroma_db` 归档/下线路径写进部署文档与升级手册；一键回滚到上一 `index_version` 演练一次并留证。
- **备份恢复必须覆盖 PG 向量列**（`docs/current-functionality-2026-09-10.md:1217` 至今把这套存储组合定为「过渡架构」，就是因为它没被纳入备份）。
- `chroma_db/**` **至今仍被 git 跟踪** `[实测]`：反跟踪、删除、`.gitignore` 改动**一律业主本人**（H4/H5/H8），Agent 不碰、不 add、不 restore。

## 4. 阶段 ↔ 单号 ↔ 谁执行 ↔ 回滚点

| 阶段 | 单号 | 主要写域 | 执行人 | 过判据（详 §22.2） | 回滚点 |
|---|---|---|---|---|---|
| P0 | R21 | `app/rag/retriever.py` | 执行层可写，总控代提交 | ①②③ | 代码级 revert |
| P0 | R22 | `app/rag/indexing.py` | 同上 | ①②③ | 代码级 revert |
| P1 | R58① | 新 `migrations/0010_*.sql` + `manifest.json` | **业主真机**（H12） | ① | 迁移向前不破坏数据；快照回滚靠 H4 备份 |
| P2 | R58② | 新 `app/rag/pg_store.py`、`retriever.py` | 执行层 | ② | 关双写开关＝回到 P1 前 |
| P3 | R58③ | 只读脚本 + 评测 | 执行层跑只读，跑分需真机 | ③④ | 无（不改流量） |
| P4 | R59 | `retrieval_pipeline.py`、`chat.py` | 执行层，**等 R35 结案** | ①②③ | 开关拨回 Chroma＝秒级回退 |
| P5 | R60 | `retriever.py`、`docker-compose.yml`、`deploy/**`、`docs/**` | 执行层改文档，业主执行下线 | ①②③ | 上一 `index_version` 全量恢复 |

## 5. 未决项（先定后动，不许边写边猜）

- **U1 距离算符**：未实测 Chroma distance function 前，P1 的索引 SQL 不许落笔。
- **U2 索引类型**：暂定 `hnsw`；真机 P95 不达标才回来评估 `ivfflat`。
- **U3 存量脏向量**：全零向量普查结果决定 P3 是否要求一次全量重建（大概率要）。
- **U4 dimension 注册落点**：R22 引入的新配置放在哪（`app/rag/indexing.py` 还是配置层）未定，影响 P0/P1 两单写域是否交叠。
- **U5 🔴 密级口径（H13）**：`classification` 缺省到底算公开还是算不可见**业主未裁**，
  ⇒ **P4 的下推 SQL 里 classification 分支今天写不出来**。这是一条**硬阻塞**，不解决就只能切「非密级维度」的半个读路径，
  那属于 §0 禁止的第二种中间态，**不允许**。

## 6. 红线摘要（越界即退回）

- 这三单一律**不占腿①/腿③串行位**，不进性能队列；开工需业主另行点头。
- 迁移期间**禁止**以「换 embedding 模型 / 上 reranker 来提速」为名夹带（计划书 §7 已列入明确不做）。
- 总控与执行层一律不跑改数据 / 起服务 / 建库 / 重建镜像 / push 的命令。
- 真机闸门：H12（`docker compose build migrate`，镜像落后主树 21h）、H11（容器重启才真拿到 GPU）、H4/H5/H8（备份与垃圾清理）、H13（密级口径）。

## 7. 关联

- 判据原文：跟进单 §22（`docs/handoff/2026-09-15-backend-followup-requests.md` L738-773）
- 单号索引：计划书 §5.2 / §7 / §8（`docs/handoff/2026-09-17-perf-architecture-plan.md`）
- 派工事实源：看板 §0 名册 + §4AI.9 + 本轮 §4AK

## 8. P3 执行手册（R120 · 2026-09-20 落笔 · **本班一行真库都没跑**）

> 执行人＝业主（真机）；判读人＝总控；执行层只写这一节，不代跑。
> P3 到今天一次都没跑过的原因不是脚本缺，而是**开关根本没有受支持的开法**：`VECTOR_DUAL_WRITE`
> 既不在 `deploy/.env.server`，`docker-compose.yml` 也从不透传它。R120 把透传补齐，出厂默认仍写
> `off` ⇒ 从没提过这个变量的安装，行为一字不变。

### 8.0 全文只用一条命令前缀

    docker compose --env-file deploy/.env.server -f docker-compose.yml

下面每处 `$DC` 都把它整条展开再敲。`--env-file` **不是可选装饰**：compose 的 `${VAR}` 插值只认
这一个文件（`docker-compose.yml:7-12` 顶部注释同口径），漏了它 `POSTGRES_USER:?` 会当场拦住整套栈，
`VECTOR_DUAL_WRITE` 同样不生效。开工前 `$DC ps`：postgres / redis / ollama 三个在跑即可。

### 8.1 先取证，不改动（一个只读 psql 会话）

    $DC exec -it postgres sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

进去以后逐条贴，只贴 SELECT：

    SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version;
    SELECT embedding_model, dimension, distance_function FROM vector_scope WHERE schema_version = 1;

- 列名取自 `app/db/migrations.py:37-42`，抄错的 SQL 只会得到一个"没跑过"的假结论。
- 第一条里**必须有 `0010` 这一行**（64 位 checksum 一并抄走交回）。没有 ⇒ 先 `$DC run --rm migrate`
  （它自带 `env_file: deploy/.env.server`，并且会在应用 0010 前自己 `ALTER DATABASE` 下发那对
  GUC —— R90a），再回这条重查。
- 第二条的三个值就是本库唯一口径（R22）：后面 `--confirm-scope`、U1、U3 全部以它为准，不许用配置文件
  里的数代替。取不到这一行＝0010 没成，P3 到此为止。

### 8.2 停写：目录锁决定了 P3 只能串行

`chromadb.PersistentClient` 对同一目录是**单写者锁**。脚本自己列的 4 条前置
（`scripts/compare_vector_recall.py:14-21`）第 1 条就是它：应用侧不停写，要么报锁错误、要么读到
半写状态，读出来的差集不作数。

    $DC stop backend worker scheduler

之后每一步都是 `$DC run --rm backend python ...` 起一个一次性进程：**等它退出再做下一步**，两个
`run` 同时在跑就是自己跟自己抢锁。`run` 会先满足 `depends_on: migrate`，所以那对 `EMBEDDING_*`
没声明时每条 `run` 都停在 migrate 上 —— 那是设计好的 fail-closed，不是新故障。

### 8.3 打开双写（**业主动作；本班不碰 `deploy/.env.server`，也不写任何真值**）

- 在 `deploy/.env.server` 写一行 `VECTOR_DUAL_WRITE=on`。别处没有第二条受支持的通路：compose 只在
  backend / worker / scheduler 三处透传 `VECTOR_DUAL_WRITE: ${VECTOR_DUAL_WRITE:-off}`（能写向量的
  就这三个进程；migrate 只跑 DDL，不嵌向量，所以不给它）。
- 取值口径只在 `app/rag/pg_store.py:146-162` 一处：`1/true/yes/on` 开；`0/false/no/off` **与从没写过**
  都是关；拼错的名字只打一条 `[VectorMirror] ... is not recognised` 告警然后当关，不自造第二套判定。
- 环境变量在容器启动时固化 ⇒ 改完要 `$DC up -d backend worker scheduler` 重建，再验一眼真传进去了：

      $DC exec backend printenv VECTOR_DUAL_WRITE
      $DC exec worker printenv VECTOR_DUAL_WRITE
      $DC exec scheduler printenv VECTOR_DUAL_WRITE

  三行都该是 `on`。有一条不是就是 `--env-file` 用错了文件，停下别往下跑。

### 8.4 人工触发一次全量重建

开关打开之前写进去的向量只存在于 Chroma，不重建就永远是"两边数量天然不等"（脚本前置第 3 条）。

    $DC run --rm backend python scripts/rebuild_index.py --status --json
    $DC run --rm backend python scripts/rebuild_index.py --apply --confirm-scope "<8.1 的 model>/<8.1 的 dimension>"

- `--confirm-scope` 要的是原样 `<model>/<dimension>` 字符串，必须等于 8.1 第二行；对不上脚本自己拒
  （`scripts/rebuild_index.py:775`）。
- 先把 `--status` 报告里的 `zero_vectors_before` / `cross_dimension_vectors_before` 抄下来（省掉
  `--json` 时这两项印作 `cross_dimension_vectors before=…` 与 `zero_vectors_before=…`）：那是 U3 的
  Chroma 半边（8.6），也是"要不要再来一次重建"的判据。

### 8.5 U1 距离算符：两侧都只读实测，不许猜

- PG 侧＝8.1 第二行的 `distance_function`，取值只可能是 `l2|cosine|ip`（`0010:154` 的 CHECK）。
- Chroma 侧＝collection 自己记的 metadata，键名 `hnsw:space`：

      $DC run --rm backend python -c "import chromadb;print(chromadb.PersistentClient(path='/app/chroma_db').get_collection('enterprise_docs').metadata)"

- 两侧对同一件事有两种拼法（库里记 `ip`，Chroma 与脚本用 `inner_product`），脚本在 8.7 里用
  `canonical_distance()`（`scripts/compare_vector_recall.py:200-206`）统一拼法**之后**再比，
  人读原始输出时别拿字面相等当结论。
- 依据与实测记录在 `migrations/0010_pgvector_chunks.sql:36-56`：本 build 的 chromadb 默认 `space=l2`
  ⇒ pgvector `<->` + `vector_l2_ops`；索引参数 m=16 / ef_construction=100 是照抄实测的
  `max_neighbors` / `ef_construction`，不是拍的。可覆盖入口是 GUC `app.vector_distance_function`
  （`0010:170/194/248`）。
- 两侧不一致 ⇒ 8.7 直接退出码 2。**这种时候不许"先出一份差异表看看"**：两边排序算术都不同，
  表上每一行都是噪声。

### 8.6 U3 全零向量普查：两侧各一份

- **Chroma 侧**（R125 之后才有这两枚；在那之前 `--status` 压根不普查，字段不存在，照本节执行 U3
  会取到空）：8.4 第一条 `--status --json` 交出 `zero_vectors_before`（全零）与
  `cross_dimension_vectors_before`（跨维），普查是 `scripts/rebuild_index.py` 里的
  `library_vector_census()`：整库分页扫（`collection.get` 带 `limit`/`offset`，窗口由
  `--census-page-size` 定，默认 200 枚），只发读、不叫 embedder、不写向量；全量清单另落在
  `census_report_path` 指的仓外临时文件（默认系统临时目录，`--census-report` 可改）。逐文档那枚
  `vector_census()` 仍在原位、仍由重建路径用，两侧共用同一条 `_is_zero_vector()` 判据。
- 🔴 **先读 `census_measurable`，再读那两个数**：只有它是 `true` 时两枚计数才算测过。`false` 时两枚
  都是 `null`（不是 0），原因写在 `census_reason`——服务还在写（Chroma 一个目录一个写者）、目录不
  存在、`chromadb` 取不到、扫描没覆盖 `collection.count` 的总数，全算"看不了"，都不等于"没有全零
  向量"。所以这一步要在 8.2 停写之后跑；省掉 `--json` 时同一份报告印 `zero_vectors_before=unmeasurable`。
- 🔴 「只读」说的是这条路径不发写调用：没有 `add`/`upsert`/`delete`，不调 embedder，也不碰 `--apply` 那条通路；
  跑完之后 1008 枚向量的逐枚摘要与总数一字不变。但它不等于目录字节不动——Chroma 只要被一个新进程打开就会自己把索引和 sqlite 重写一遍（尺寸相同；
  实测连不带普查的裸 `collection.get` 也一样重写），在服务还持着这个目录时抢开属于未知状态。所以这一步只在 8.2 停写之后跑；
  真被写者占着，`census_measurable` 直接给 `false` 并把原因写进 `census_reason`，那一次就没有数，别当成 0。
- 具名清单各给前 10 条（`--census-list-limit` 可改）：`zero_vector_documents` 与
  `cross_dimension_vector_documents`（带 `widths`）；目录在册而库里一枚向量都没有的文档进
  `unmeasurable_documents`，那是"没东西可看"，不是"干净"。
- **PG 侧**：8.7 输出的 `drift.all_zero_rows`。零字面量由脚本按 `vector_scope.dimension` 现拼
  （`scripts/compare_vector_recall.py:118`），手抄 768 个数一定会数错。要逐行清单就在 8.1 那个会话里贴：

      WITH z AS (
        SELECT '[' || string_agg('0.0', ',') || ']' AS zero
        FROM generate_series(1, (SELECT dimension FROM vector_scope WHERE schema_version = 1))
      )
      SELECT vector_id, filename, chunk_index, index_version_id
      FROM chunk_vectors, z
      WHERE embedding = z.zero::vector
      ORDER BY vector_id LIMIT 200;

  （`chunk_vectors` 没有 `chunk_id` 列，主键口径是 `vector_id` + `UNIQUE (filename, chunk_index)`。）
- 判读：任一侧非零 ⇒ 按 §3 P3 的口径，P3 结论作废，先全量重建再重跑 8.4 起的全部内容。

### 8.7 第一轮：逐集合差（不算向量，不需要模型在场）

    $DC run --rm backend python scripts/compare_vector_recall.py --skip-questions \
      --collection enterprise_docs --chroma-dir /app/chroma_db --k 5 \
      --out /app/data/r58_drift.json

- `--collection` 默认值已由 R120 修成 `enterprise_docs`（原先抄的是 Postgres 库名 `enterprise_brain`，
  而写入侧的名字在 `app/rag/retriever.py:484`）：默认写错时第一步就会死在"取不到 collection"。
  手册仍显式写出来，是为了让日志里能看见当时用的是哪一个。
- `--out` 落在 `/app/data/`（`appdata` 卷）而不是 `/tmp`：`run --rm` 的容器一退出，`/tmp` 就没了。
- 脚本连上即 `connection.read_only = True`，一条写都不发；Chroma 侧只 `get` / `query`。
- 判读只看三个数：`pg_vectors` 与 `chroma_vectors` 是否相等、`only_in_pg` / `only_in_chroma` 是否为空、
  `wrong_width` 是否为空。`index_version_id_null` **不是故障**：retriever 不知道索引版本，双写时留
  NULL 等发布回填（R22 口径，脚本 docstring 也写了），它是待回填计数。
- ⚠ R76 把这半句里的「等发布回填」变成了事实，读法跟着变（仍不是故障）：回填落在
  `app/rag/indexing.py` 的 `IndexMirrorSession.tag_vector_index_version` —— 一条
  `UPDATE chunk_vectors SET index_version_id = <本次发布的版本 id>`，与 `mark_published` 同一个事务、
  同一次 commit。所以双写开着、0010 已跑、且这枚文档此后**发布过一次**（上传，或
  `scripts/rebuild_index.py:749` 的逐文档重建，两者走同一个 publisher）⇒ 该行就带上版本 id；
  还留 NULL 的只剩「写进镜像之后没再发布过」的存量，它掉不回 0 也不代表坏，别按新故障判读。
- R76 在发布侧另给了两枚读数：上传回执（`PublicationOutcome.as_dict()`）里的 `vector_rows_tagged`
  与 `vector_rows_missing`，用来指名这次回填走没走到、有多少 id 在镜像里没有行。它们不在本脚本的
  `--out` JSON 里，两边对不上先查 `VECTOR_DUAL_WRITE` 与 0010 有没有跑。
- 换 embedding 模型的那道闸也落在同一步：镜像里存着的行如果 `embedding_model` / `embedding_dimension`
  与本次发布的口径不符，发布**整笔拒绝**（R22 的 `embedding_model_drift` / `embedding_dimension_drift`，
  失败阶段名 `vector_index_version`），不留「主索引新模型、镜像旧模型」的半张脸。重建窗口里看到这一条
  报错是预期行为，正确处置是把这一枚文档的向量腿补重做，不是改发布代码。

### 8.8 第二轮：带题对比（前置第 4 条：Ollama 在位、模型与 `EMBEDDING_MODEL` 同一个）

    $DC run --rm backend python scripts/compare_vector_recall.py \
      --collection enterprise_docs --chroma-dir /app/chroma_db --k 5 \
      --fixture tests/fixtures/business_evaluation_100.jsonl \
      --out /app/data/r58_recall_diff.json

- 不带 `--fixture` 时默认吃**两份**题集（`business_evaluation_30.jsonl` 30 题 + `_100.jsonl` 105 题
  ＝135 题）。§3 P3 说的"同一 105 题"是后一份，所以这里显式指定；两件事别混着读。
- 题向量由生产侧同一个 embedder 产出（`OllamaEmbeddings`），脚本不改模型、不改维度、不加重排。
- 判读：`summary.differing / summary.questions`，以及每条 DIFF 的 `first_diff_rank`。
- **交回前必做的一件事**：先在真机上复跑
  `$DC run --rm backend python scripts/check_eval_evidence_coverage.py`。
  §3 P3 的"前置动作②"写的是 55 条 `must_contain` 查无出处，而 R94 常驻件在本工作树 09-20 实测是
  **29 行 / 29 词**（主口径 `documents/*.txt` 95 篇）⇒ 那个 55 是旧数。这 29 行的正确答案按设计是
  "语料无据 ⇒ 该拒答"，它们的 top-k 差异**不能**记在镜像账上；带题那轮的差异必须按这份清单切一刀再判读。
- ⚠ 只要复算仍给非零，这一轮就还是**影子读的技术差集**，不是跟进单 §22.2 R58 判据③ 要的验收证据
  （那条明写"无出处清零在先"，并自述"本班未独立复跑"）。要拿它当切换门禁的证据，得先走清零那一单。

### 8.9 跑完交什么给总控

- 两份 `--out` JSON 原文件（`scope{embedding_model,dimension,distance_function,column_type}`、
  `k`、`drift{pg_vectors,chroma_vectors,only_in_pg,only_in_chroma,wrong_width,all_zero_rows,
  index_version_id_null,chunks_rows,chunks_with_backfilled_embedding}`、带题那轮的
  `questions[]` 与 `summary{questions,differing,corpus_gap}`）。
- 两次运行的 **stdout 全文**（`_print_drift` 那 9 行是给人看的摘要，JSON 是给机器算的，两份都要）与**退出码**。
- 8.1 两条 SELECT 的结果（含 0010 的 checksum）、8.5 两侧距离算符原文、8.6 两侧全零计数、
  8.8 的 `check_eval_evidence_coverage.py` 输出。
- 每一步实际敲的命令（尤其 `--confirm-scope` 那串、有没有带 `--env-file`）。
- 退出码含义：`0`＝逐题 top-k 全一致且两侧无集合差；`1`＝有差异（**这是正常结论**，交人判读）；
  `2`＝前置不满足，此时脚本一个召回结论都不产出，不许把它的输出当差异表交上来。

### 8.10 收尾：结论交回之后，把开关拨回 `off`（除非总控裁定直接进 R59）

双写是 fail-closed 同事务：PG 那侧挂掉，上传/重建整笔回滚（§3 P2）。挂在生产上不开对比＝白担一份
可用性风险。镜像停更期间积累的差异，靠"重新 `on` + 再来一次 8.4 全量重建"补，不靠猜。

### 8.11 常见失败长这样（都不是召回差异，别混进判读）

- `[前置不满足] vector_scope 里没有 schema_version=1 这一行` ⇒ 0010 没跑成，回 8.1。
- `[前置不满足] chunk_vectors.embedding 实际类型 …/不存在` ⇒ 列宽与声明不符，或表没建。
- `[前置不满足] 库里口径 … 与运行时不一致` ⇒ R22 口径漂移，先按 §3 P0 重建，再谈对比。
- `[前置不满足] collection 距离=…，vector_scope 声明=…` ⇒ U1 未定，回 8.5。
- `[前置不满足] 取不到 collection 'enterprise_docs'` ⇒ 目录/集合名不对（换机器跑时最常见）。
- `[前置不满足] Chroma 目录不存在` ⇒ `--chroma-dir` 指错了；**不要新建目录**，新建出来的是空库。
- 锁报错 / 读到半写状态 ⇒ 8.2 没做干净，或有第二个 `run` 还活着。

### 8.12 红线（越界即退回）

- 本手册**只读**：一条 UPDATE / INSERT / ALTER 都不许顺手加。
- **不切读**：Chroma 仍是唯一读路径。切读是 R59（§3 P4），前置就是 8.7/8.8 这两轮的结果。
- 不动 `app/rag/retrieval_pipeline.py`，不借对比之名改检索编排；"先按权限过滤，后去重"的口径不许漂。
- 评测集与 `must_contain` 不许为凑绿改动（`tests/test_evaluation_report.py` 钉着）；8.8 的复跑只是
  取数，不是清理。
- 跑分窗口在跑时不排这一串（它要独占 Ollama 与 Chroma 目录）。

> **🔴 09-24 定案补记（第四十四班，业主原话「chroma 不在用改成 pgvector 你把文档也改了，上次我就说要换了」）**：本文件的**方向**从「目标态设计 / 待评估」升格为**已定案**——生产向量库 = PostgreSQL + PGVector，Chroma 进入退役轨道。三份治理文档已同步改口（`AGENTS.md` 技术栈与核心原则、`docs/system-architecture-2026-09-17.md` §存储条、`docs/system-design-2026-09-16.md` 同条、`docs/version-roadmap-and-next-week-plan-2026-09-22.md` 两条）。
>
> **但定案不等于已切换，本节把今天的事实钉住**（免得改口改出一句假话）：① **双写在跑**——`VECTOR_DUAL_WRITE=on` 在 `deploy/.env.server` 里就是 on，PDF 抽取带 NUL 那枚 P1 已由 **R130**（落树 `cdc5ead`）修掉，全库 **1008 枚向量**在位；② **读路径今天仍在 Chroma**——`app/rag/retriever.py` / `retrieval_pipeline.py` / `app/documents/catalog.py` 尚未切；③ **P3 召回对比从未跑过一次** ⇒ 切过去会不会悄悄变差，这一格目前零读数，**R59（切读）已于 09-24 提到第一批派工**（`be-r59`），它的第一判据就是把那份读数做出来，在做出来之前**不许把任何生产路径的默认读后端翻成 PGVector**；④ **H20（距离下限口径）业主未裁**，本班按「不新增人为下限、top-k 与阈值沿用现值」代裁推进，**可推翻**。
>
> 三枚用例钉着本文件（`tests/test_r120_dual_write_passthrough.py:43`、`tests/test_r120_p3_collection_default.py:31`、`tests/test_r125_status_vector_census.py:25`）⇒ 本节是**追加**，未改动任何既有行；改这份文件的人必须复跑那三件。
---

## 9. R59b 切读复测收口（2026-09-24 落笔 · **默认值未翻，读路径仍在 Chroma**）

本节只追加，不改上面任何一行。落笔人：R59b（执行层）。判据由总控复跑，不在此自宣达成。

### 9.1 今天真实位置

- 双写在开，镜像逐枚齐：`chunk_vectors` 1008 行 vs collection `enterprise_docs` count 1008，
  **id 集合逐枚相等**（`only_in_pg=0`、`only_in_chroma=0`）；两侧向量本体最大逐位差
  `2.1679687467468511e-07`（float32 重嵌入噪声底），两库各自精确算的 top-5 **135/135 全等**。
- 读路径**仍在 Chroma**（遗留件，今天仍在提供读服务）。`INDEX_BACKEND` 的字面量一字未动，仍是 `chroma`。
- 已落地的是一副**接好但没合闸**的读腿：`app/rag/indexing.py` 认 `chroma`/`pgvector` 两个值并交出
  `read_backend()` / `pgvector_reads_enabled()`；`app/rag/pg_store.py` 交出
  `sql_scope_filter` / `search_vectors` / `read_topk`（谓词翻不出来就拒答，绝不退化成「没有 WHERE」）；
  `app/rag/retriever.py` 在遗留腿之前挂 `_pgvector_hits()`，开关关着时**一个 SQL 都不发**。
- 用例：`tests/test_r59b_pg_read_switch.py`（24 枚）。11 枚变异逐条复验全部能让点名用例变红。

### 9.2 读数结论（k=5，135 题，PG 腿＝真库读，无估算腿）

众数遍次：**68/135 题两侧 top-5 集合一致，67 题不一致**。分歧归因是单向的：

- PG 腿 `pg_index_vs_exact_same_set` = **135/135**：索引腿＝全表精确腿，HNSW 近似性在本库这个规模上
  不产生成员差也不产生名次差（当时会话 `hnsw.ef_search=40`，未扫参）。**没有一题是 PG 答得比精确解差。**
- `exact_sides_same_set` = **135/135**：两库精确算逐题全等 ⇒ 分歧不来自向量本体。
- 67 题不一致 = Chroma 索引腿 ≠ **Chroma 自己在同一批向量上的精确解**：43 题成员对称换入换出，
  24 题 Chroma 整条交回 0 行（PG 侧全部交 5 行）。`mean_kendall_tau` 恒 1.0 ⇒ 分歧全在「谁进 top-5」。
- 机制（本轮结掉的部分）：Chroma 的元数据段 1008 行、集合水位 seq 78696，而 HNSW 向量段水位只到
  seq 77968 —— 中间 729 条日志（657 put / 72 delete）从未回放进索引，段里只剩 422 枚活标签；
  `sync_threshold=1000` 大于未消费数，所以它不会自己追平。一次要回全库只捞得出 878 枚，
  **约 130 枚向量在生产库里有、在它的 ANN 里不可达**。
- 未结：Chroma 对 24 题交 0 行的字节层成因（与谓词/`ids` 白名单/`n_results` 大小/远近都无关，只量到形状）。
- 跨进程稳定性：同一份输入、同一枚脚本，`same_set` 在 68–92 之间摆，**会摆的只有 Chroma 那条腿**
  （`query_sha`、`pg_ids`、`pg_exact_ids`、`chroma_exact_ids` 全程 0 变化）。

⇒ **方向支持切读**；本轮**不翻默认**。

### 9.3 翻默认之前还差的格子

1. 服务内端到端没在真库上跑过（今天只在 fake connection 用例下绿过）。
2. 热集让路的代价没量：切读态下 `_hot_hits` 整层让路（`app/rag/hot_index.py` 新原因码
   `hot_index_read_backend_switched`），延迟与命中分布两侧对比无数据。
3. 选择性权限过滤没量：本库 `classification` 全=1、`department` 全=`''`，谓词只能全命中或全不命中。
   全命中谓词两侧答案不变、零命中谓词两侧一致地空（**PG 侧没有漏放行**），但「选择性强过滤下的
   召回差」这一格**没量到**，要量得先在沙盒库里造一份跨部门/跨密级语料。
4. 双写开满一轮全量重建未确认（§3 P3 的语义前置）。
5. 遗留库仍在被写要拍板：`chroma.sqlite3` 的 mtime 会随**只读**进程前进（静置 128 s 不动，每开一遍读动一次）。
6. 那 24/135 题空答复要不要作为切读前的基线缺陷单独追（它同时是今天生产的读路径症状）。

### 9.4 一条取证纪律（这次的坑，写给下一个跑对比的人）

**别在宿主机上跑这组对比。** 5432 上可能挂着另一台野 PostgreSQL（没有 `vector_scope`），连上去
`vector_scope` 不存在，脚本就会把 PG 腿降级成估算腿（numpy 代替真库）——产物看着一应俱全，其实只有一条腿。
同理别用 `%TEMP%` 下的临时 Chroma 目录当样本：那一遍读数是 401 枚的沙盒，与生产 1008 枚不是一批东西。
要么在 backend 容器里跑（`/app/chroma_db` 是生产卷、`postgres` 是内网 DNS），要么别跑。
真 DSN 的原文不入文档，只走环境变量。

复现与逐题明细：`docs/testing/r59b-recall-reading-2026-09-24.md`、
`docs/testing/r59b-recall-comparison-2026-09-24.json`、`docs/testing/r59b-stability-2026-09-24.json`。
量具：`scripts/r59_recall_compare.py`。上一遍作废说明：`docs/testing/r59-recall-reading-2026-09-24.md`。

## 10. 总控独立复算 R59b 那份对照（2026-09-24 14:0x，主树 `fe5b180`）：Chroma 向量腿的缺陷面第一次有了题号清单

复算对象是已并树的只读原件 `docs/testing/r59b-recall-comparison-2026-09-24.json`（135 题、k=5、两侧各 1008 枚、无估算腿），**没有重跑容器、没有采信任何自述**，只是把那份 JSON 重新数了一遍：

| 读数 | 值 |
|---|---|
| `chroma_rows == 0` 的题 | **24**（族分布：口径冲突 7／跨部门权限 5／主动洞察 3／工具调用 3／文档问答 2／图表 1／Excel 1／审批 1／报告 1） |
| 这 24 题里 `chroma_exact_ids` 有货的 | **24/24** ⇒ **数据在 Chroma 自己的集合里，是它的 ANN 不交**，不是没入库 |
| PG 侧同题 `pg_rows` | 全部 5；`pg_index_vs_exact_same_set` **135/135** |
| `pg_rows == 0` 的题 | **0** |
| 两侧结果集不一致的题 | 67，其中 `exact_sides_same_set` 为真 **67/67** ⇒ 分歧**全部**落在索引腿，两侧精确解完全一致 |

- 题号清单（按 `id` 去重后 21 枚）：`metric-04` `metric-05` `metric-10` `metric-11` `metric-13` `metric-18` `metric-19` ／ `scope-01` `scope-03` `scope-05` `scope-06` ／ `insight-02` `insight-06` ／ `tool-01` `tool-04` ／ `doc-09` `doc-13` ／ `chart-04` ／ `data-08` ／ `approval-06` ／ `report-12`。
- 🔴 **一条必须写小的边界**：这 24 题不等于"客户今天答不出这 24 题"。生产读路径除向量腿外还有 BM25／改写／多路召回，run6 里 `metric-05`／`metric-10`／`metric-18`／`metric-19` 都拿到了引证。诚实说法是：**"向量腿单腿交 0 行 24 题，其中 11 题在 run6 同时读成零引证"**（交集：`chart-04` `insight-02` `insight-06` `metric-04` `metric-11` `metric-13` `scope-01` `scope-03` `scope-05` `tool-01` `tool-04`）。
- 本节对 §9.3 那六格的作用：**不消任何一格**，但给第 ⑥ 格（24 题空答复要不要当基线缺陷）一份定量答案——**它是 Chroma 的缺陷、不是我们数据的缺陷、更不是 PG 的缺陷**（PG 侧 135/135 索引=精确、零空答复）。⇒ **R211 裁定"不修 Chroma、由切读吸收"至此有题号级凭据**；反过来，若切读 on 之后这 21 枚里有谁仍交空集，R211 的裁定当场作废、另立新单。
