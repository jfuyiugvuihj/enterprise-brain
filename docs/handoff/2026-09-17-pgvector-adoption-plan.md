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
