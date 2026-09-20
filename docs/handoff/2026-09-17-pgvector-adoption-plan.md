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

- **Chroma 侧**（现成件，零改动）：8.4 第一条 `--status --json` 里的 `zero_vectors_before` 与
  `cross_dimension_vectors_before`，出自 `scripts/rebuild_index.py:176-210` 的 `vector_census()`
  （逐文档 `collection.get(where={"filename": ...}, include=["embeddings"])`）。
  `measurable: false` 的意思是"看不了"，不是"没有问题"，交回时原样带上。
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
