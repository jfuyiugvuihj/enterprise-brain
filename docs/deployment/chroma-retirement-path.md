# Chroma 的归档与下线路径（R60 停写之后）

> 定案口径（业主 2026-09-24 定案，AGENTS.md 同条）：生产向量库是 PostgreSQL + PGVector；
> Chroma 是**退役中的遗留件**。本页只回答两件事：它今天还在替谁干活，以及它按什么顺序退。
> 🔴 既不许把它写成已下线，也不许把它写成最终架构 —— 那一档今天还在提供读服务。

切换进度的唯一事实源是 `docs/handoff/2026-09-17-pgvector-adoption-plan.md`（总控写域），本页是**运维视角的路径图**：
它写工序、判据与回滚点，不替代那本账。

## 1. 今天的真实位置（2026-10-03 现取）

| 腿 | 现在的形状 | 现读凭据 |
| --- | --- | --- |
| 语义读答复 | 走 PostgreSQL 那一腿，本机生产部署把旋钮拨在 pgvector | 主树 `deploy/.env.server:77`；服务内端到端读数 `docs/perf/r382-readpath-2026-09-27.md` |
| 新行落点 | **停写已生效**：PGVector 主写下遗留库不接新行；代码留在原地，由开关管 | `app/rag/retriever.py:1442` `_write_batch`、`app/rag/retriever.py:1496` `_writes_go_to_pgvector` |
| 删除 | 行住在哪一库就问哪一库；两腿都持有就两腿都删，不留孤儿行 | `app/rag/retriever.py:1522` `_document_rows_by_leg`、`app/rag/retriever.py:2053` `delete_document` |
| 回滚通路 | `INDEX_BACKEND=chroma` 那一档读与写都照旧：遗留库仍给这一档提供读服务，也照常接新行 | `app/rag/indexing.py:50` 出厂缺省仍是 chroma；演练账里 `rollback-knob` 那一臂 |

在册量：`chunk_vectors` 1008 枚，双写开（主树 `deploy/.env.server:56`）。

第④格那对增量（沙盒库 `eb_r575_drill` 现取，演示库 `enterprise_brain` 一行未动）：

- 停写态 `INDEX_BACKEND=pgvector`：写一枚新文档 → PG 1009 → **1010**（+1），遗留集合计数 1 → **1**（+0）。
- 回滚档 `INDEX_BACKEND=chroma`：同一份码同一套件，只拨开关 → PG 1008 → **1009**（+1），遗留集合 0 → **1**（+1）。
- 删除两形：只住 PG 的文档 → PG −1、遗留 ±0；两腿都持有的文档 → PG −1、遗留 **−1**。

账本 `docs/testing/r60-chroma-writeoff-ledger-2026-10-03.json`，判器 `tests/test_r60_rollback_drill_ledger.py`。

## 2. 为什么停写是开关，不是删码

`_writes_go_to_pgvector()` 只问两枚在册判定加一枚自有条件，缺一都不算主写：

1. `stores_vectors` —— 离线 `_JsonCollection` 后端没有向量列，那个 JSON 文件就是它的全部；
2. `pg_store.dual_write_enabled()`（`VECTOR_DUAL_WRITE`，`app/rag/pg_store.py:175`）—— 双写关着就没有 PG 腿可交行，此时把遗留腿一起关掉不是停写，是**零写**；
3. `indexing.pgvector_writes_are_primary()`（`app/rag/indexing.py:2098`）—— 拨的就是读路径那把既有 `INDEX_BACKEND`，同一处解析（`read_backend()`），**没有**第二把名字里带 BACKEND 的环境变量。

停写态下 `add_document` / `delete_document` 里那句「问不全就拒答」也是同一族：PG 腿问不出行时报
`vector_mirror_unavailable`，不退回「只问遗留腿」——那会报一次根本没找到行的删除，而且报的是成功。

## 3. 回滚（两把，外加它们的代价）

**第一把：拨开关（分钟级，只改部署，不改代码）**

```bash
# 主树 deploy/.env.server 把 INDEX_BACKEND 改回 chroma，然后重建容器（不是重建镜像）：
docker compose --env-file deploy/.env.server up -d --force-recreate backend worker scheduler
```

`env_file:` 在容器创建那一刻才解析，`docker restart` 不重读（口径由 `tests/test_r255_env_documents_the_conversion.py` 钉着）。

🔴 这把回滚的代价要写明：停写期间新写的行**只住在 PostgreSQL**。旋钮拨回 `chroma` 之后，读侧看的是遗留库，那份文档读不到；而删除在回滚档只问遗留腿（判据①要求那一档行为一字不改），所以停写窗口里的 PG 行会留在 `chunk_vectors` 里，等旋钮再拨回 pgvector 时重新出现。补法两条：拨回之后先跑一次 `python scripts/audit_vector_mirror_sets.py` 做两腿差集，再按需用 `python scripts/rebuild_index.py --apply` 重建（后者要重新嵌入＝打模型，得由总控开量测窗）。

**第二把：库级全量恢复（真跑过一次，可复用）**

```bash
python scripts/r575_vector_restore_drill.py full --keep --queries 20 --top-k 10
```

真机读数（2026-10-03，`C:\Users\fengx\PycharmProjects\r575-drill\r575-drill-reading-20261003T062557Z.json`）：
rc=0 / status=PASS；归档 79 869 035 B，dump sha256 `cc64359e6894…`；恢复库 `eb_r575_drill` 里 1008 行、
向量指纹与源库同值；七项对账 14 项全等、differences=[]；召回对账 20 题 top-k 10，`only_in_*` 两枚皆 0、
`max_rank_shift`=0；收尾演练库已删（`drill_dropped=true`）、生产库前后行数同值。
🔴 备份必须连**库级 GUC 成对产物**一起备（`*.globals.json` / `*.globals.sql`，恢复时在任何校验之前重新施加），
这一格由 `tests/test_r587_globals_pair_gates_the_e_gate.py` 钉着，不许降回「照实上报」。

`index_version` 那一层另有指针：`IndexRegistry.rollback` 能回到上一版并把落盘账里 restored/superseded 两格改口；
但数据库侧 `index_registry.current_version_id` **今天没有一键回退入口**，本单只取证未自造 UPDATE。

## 4. `chroma_db` 的归档与下线路径（按阶段，未做到的阶段不许提前当已完成）

| 阶段 | 动作 | 过判据才许进下一格 | 回滚点 | 谁有权做 |
| --- | --- | --- | --- | --- |
| S0 停写 | 旋钮拨到 pgvector，新行只落 PG | 第④格那对现取增量（+1 / +0）进纸 | 拨回 chroma | 已完成（本单） |
| S1 观察窗 | 现网三枚容器 `printenv INDEX_BACKEND` 全 pgvector，且无人拨回 | 连续窗口内零次回滚；`scripts/rebuild_index.py --status` 普查两腿差只增不减 | 拨回 chroma + 一次重建 | 运维 |
| S2 最后一次带遗留库的全量归档 | 仍趁 `chroma_db` 在备份范围里做全量备份并校验 sha256，离线保存 | 归档件可独立恢复；`scripts/backup_workspace.py` 交回的清单里有 `chroma_db` | 不需要 | 运维 |
| S3 把 `chroma_db` 摘出备份范围 | 改 `app/common/backup.py:12` 的 `DEFAULT_BACKUP_DIRS`，同步改口 `tests/test_postgres_backup_recovery.py` 的落点名册 | 摘完之后整库恢复仍能重建出可检索的语料（走 PG 那一腿） | 还原那一行 | 另开工单（代码变更） |
| S4 目录与卷离场 | 命名卷 `vectordb`（`docker-compose.yml:44`，容器内 `/app/chroma_db`）、开发机 `./chroma_db`（`app/rag/retriever.py:1018` 的缺省目录）离线归档后删除；仓库里那枚目录反跟踪 | 删除前 S2 的归档件在异机验过一次 | 从归档件恢复 | 🔴 业主本人（H4/H5/H8，`docs/handoff/2026-09-17-human-gates.md:43`、`docs/handoff/2026-09-17-human-gates.md:55`、`docs/handoff/2026-09-17-human-gates.md:76`）；本单一枚文件没删、`.gitignore` 没改、容器没下线 |
| S5 代码退役 | 遗留腿那几支才谈删除：`_write_batch` 里的 `collection.add`、`_document_rows_by_leg` 的遗留问句、`app/rag/retriever.py:1110` 那处 `PersistentClient` 构造。🔴 同批必须重排 `stores_vectors` 的判定 —— 今天只有 chromadb 不可导入才落到离线 `_JsonCollection`（`app/rag/retriever.py:1027`），遗留客户端一旦不装，这条判定会把「该走 PostgreSQL」误读成关键词降级 | 在册件全绿且回滚档确认不再需要 | `git revert` | 另开工单，且必须晚于 S4 |

S3/S4/S5 之间的顺序不能倒：备份范围先摘、目录后删，代码最后退役。反过来做，就会出现「代码已不写、归档里也没有、
回滚档无货可回」这一形状 —— 那才是真的把退路拆了。

## 5. 今天还会打开遗留目录的量具（退役时逐枚改口，别一次删掉）

- `scripts/rebuild_index.py:282` `open_census_store()` —— `--status` 普查读 `CHROMA_DIR`，缺省 `./chroma_db`；
- `scripts/audit_vector_mirror_sets.py:1133`、`scripts/compare_vector_recall.py:102` —— 两腿集合与召回对照；
- `scripts/diag_r162_chroma_zero_rows.py:63`、`scripts/r382_*` 那一族探针 —— 历史取证件；
- `tests/test_r58_pgvector_dual_write.py`、`tests/test_r120_dual_write_passthrough.py` —— 它们的绿里包含「回滚档两腿照写」这一格，S5 之前不许为了省事摘掉；`tests/test_r59_chroma_untouched_on_pg_reads.py` 管的是另一格（读走 PG 时不许碰遗留目录），也别混作一枚。

## 6. 本页没证的格子（诚实清单）

- 客户尺寸的召回差未量（索引腿与暴力解的拐点由 R579 在量）；生产 `department`/`classification` 仍全空，密级隔离那一格**未验**。
- 第④格与全量恢复都跑在沙盒库 `eb_r575_drill` 上，不是在演示库；演示库那 1008 枚由别的单在数。
- S1 之后的每一阶段今天都没执行，本页写的是路径，不是完成度。
- 真机读数与别的执行层同时在跑（`be-r590`/`be-r596`/`be-r597`），时间类量测受同机争用影响，行数类读数不受。

## 7. 谁钉着这页

- `tests/test_r60_write_path_unique_under_pgvector.py`：判据①②③（含「停写是开关不是删码」那枚 AST 常驻钉）。
- `tests/test_r60_rollback_drill_ledger.py`：判据⑤＋⑦第三把（演练账少一步就红）。
- `scripts/check_vector_wording.py`：口径扫描；本页**不在**它的豁免清单内，措辞越线当场红。
