# R469 · C 门检索侧沙盒读数（2026-09-28T23:42:16+0800）

单号 **R469**（施工树基点 `9c214907fecf92be1cf13156380b56d52fab48df`，容器镜像 BUILD_INFO `9c214907fecf`）。
驱动 `scripts/r469_sandbox_scope_readout.py`（在 backend 容器里跑，连 compose 网络内的真 PostgreSQL）；本表由 `scripts/r469_readout_lib.py` 从文末围栏 JSON 生成——手写即假账，`validate_readout()` 比字节。

> 🔴 口径：PGVector 是生产向量库（业主 09-24 定案，不再变更），Chroma 是退役中的遗留件。
> 今天真实位置见下面那行「读后端旋钮现读」——本表不抄文档里的开关状态；全部读数都在 pgvector 读腿上取，遗留引擎一条没问。
> 🔴 这一格的边界：沙盒标签只证「谓词按标签行为」，不证客户隔离；生产格③ 欠的是业主侧真实密级回填（A3 已裁「交付阶段按客户真实密级做」）。
> 🔴 这不等于格③ 已翻绿，也不等于 C 门翻绿：格③ 在生产侧仍记「未验」。

语料：`4edc8884381b6c49` 的 72 枚合成行（部门 [fin, hr, ops, exec] × 密级 [1, 2, 3] × 每格 6 枚），dimension=768，来历标签 `r59c-synthetic-lcg`（几何夹具，非嵌入）；锚点 12 枚＝每枚 (部门,密级) 格里 id 最小那一枚，查询向量取该行自己的 embedding（自探针）；每锚点读两臂（带谓词 / 不带谓词），k=5。

整单状态：**SANDBOX_MEASURED_PRODUCTION_UNVERIFIED**

判据本体：scripts/r469_readout_lib.py。逐档判定词表：`MEASURED_WITH_TEETH` / `VACUOUS_EMPTY_SET` / `ZERO_RECALL` / `RED_BREACH` / `RED_CONTROL`。
候选宽度不自带数字：现场向 `app.rag.pg_store.configured_hnsw_ef_search` 取，本班读数 = 100（与生产读腿同一笔调用）。
读后端旋钮现读：本班进程 `pgvector`（env `INDEX_BACKEND` 由 docker exec 注入），摘掉 env 后镜像缺省 `chroma` ⇒ 翻默认仍是业主动作，本表全部读数都在 pgvector 读腿上。

## 一、存量六枚恒量（跑前 / 跑后）

六枚 = `chunk_vectors` / `documents` / `document_versions` / `dataset_versions` / `resource_versions` / `users`。生产库一律只读，写只发生在沙盒库的 `r59c-` 前缀行上。

| 表 | 跑前 | 跑后 | 逐枚 |
|---|---|---|---|
| chunk_vectors | 1008 | 1008 | 相同 |
| documents | 105 | 105 | 相同 |
| document_versions | 100 | 100 | 相同 |
| dataset_versions | 6 | 6 | 相同 |
| resource_versions | 129 | 129 | 相同 |
| users | 3 | 3 | 相同 |

| 生产库附加恒量 | 跑前 | 跑后 | 逐枚 |
|---|---|---|---|
| chunk_vectors 行数 | 1008 | 1008 | 相同 |
| department 为空串的枚数 | 1008 | 1008 | 相同 |
| classification 取值分布 | {'1': 1008} | {'1': 1008} | 相同 |
| users 里 department 非空 | 1 | 1 | 相同 |

六枚复算：`True`（记录值与现场复算一致：`True`）。「取值分布」的键是 PostgreSQL 的 `integer`，不是空串——同一枚词在 `documents`/`document_versions`/`chunk_vectors` 上是 integer、在 `datasets`/`dataset_versions`/`resource_versions` 上是 text，拿空串判 integer 那三张表会当场炸（§133 六末尾那条现场教训）。

## 二、生产/演示臂（库 `enterprise_brain`，池 1008 枚，本臂写入 0 枚）

臂状态：**NOT_MEASURED**

| 主体档 | scope | 池内可召/池 | share | 池外材料 | 读次×交回 | 去重命中 | 越权 | 无谓词对照可越界 | J-3 集合等 | J-3 槽位等 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| staff-fin-l1 | department_scope | 0/1008 | 0.0000 | 1008 | 12×0 | 0 | 0 | 60 | 未判 | 未判 | VACUOUS_EMPTY_SET |
| manager-hr-l2 | department_scope | 0/1008 | 0.0000 | 1008 | 12×0 | 0 | 0 | 60 | 未判 | 未判 | VACUOUS_EMPTY_SET |
| manager-ops-l2 | department_scope | 0/1008 | 0.0000 | 1008 | 12×0 | 0 | 0 | 60 | 未判 | 未判 | VACUOUS_EMPTY_SET |
| exec-l3 | department_scope | 0/1008 | 0.0000 | 1008 | 12×0 | 0 | 0 | 60 | 未判 | 未判 | VACUOUS_EMPTY_SET |
| admin-l3 | administrator_scope | 1008/1008 | 1.0000 | 0 | 12×60 | 6 | 0 | 0 | 未判 | 未判 | VACUOUS_EMPTY_SET |

| §13.一 四件 | 判定 | 读数 | 边界 |
|---|---|---|---|
| (a) 主体侧真带部门 | 未验 | users 表 3 枚里 department 非空 1 枚；admin/evalbot 实测为空 | 本单主体是合成 principal，不代替真账号；真账号那一格未回填 ⇒ (a) 不成立 |
| (b) 语料两维都 selectable | FAIL | 非空 department 0/1008 枚；部门 1 档 [<空串>]；密级 1 档 [1]；(部门,密级) 叉乘 1 格（其中 r59c 合成语料 0 格） | r59c 补的正是密级那一维：沙盒原有标签是 4 部门 × 各 1 档，同部门内跨密级不可判 |
| (c) 该臂召回 > 0 | FAIL | 召回 > 0 的档 1/5：admin-l3 | — |
| (d) 越权 = 0 | 未验 | 逐档全是空集（挡光或全放行），越权 0 条无从判 | 这正是 §133 六那条真账的形状 |

## 三、沙盒臂（库 `eb_r59_sandbox`，池 1080 枚，本臂写入 72 枚）

臂状态：**SANDBOX_MEASURED_PRODUCTION_UNVERIFIED**

| 主体档 | scope | 池内可召/池 | share | 池外材料 | 读次×交回 | 去重命中 | 越权 | 无谓词对照可越界 | J-3 集合等 | J-3 槽位等 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| staff-fin-l1 | department_scope | 6/1080 | 0.0056 | 1074 | 12×60 | 6 | 0 | 59 | 12/12 | 60/60 | MEASURED_WITH_TEETH |
| manager-hr-l2 | department_scope | 12/1080 | 0.0111 | 1068 | 12×60 | 12 | 0 | 48 | 12/12 | 60/60 | MEASURED_WITH_TEETH |
| manager-ops-l2 | department_scope | 12/1080 | 0.0111 | 1068 | 12×60 | 12 | 0 | 51 | 12/12 | 60/60 | MEASURED_WITH_TEETH |
| exec-l3 | department_scope | 18/1080 | 0.0167 | 1062 | 12×60 | 18 | 0 | 42 | 12/12 | 60/60 | MEASURED_WITH_TEETH |
| admin-l3 | administrator_scope | 828/1080 | 0.7667 | 252 | 12×60 | 44 | 0 | 0 | 12/12 | 60/60 | MEASURED_WITH_TEETH |

| §13.一 四件 | 判定 | 读数 | 边界 |
|---|---|---|---|
| (a) 主体侧真带部门 | PASS_SYNTH_ONLY | 4/5 档带部门谓词（管理员那档 departments=None 不计，§13.一 原话） | 只证「主体带部门时谓词的行为」，不证客户侧真有人被回填了部门 |
| (b) 语料两维都 selectable | PASS | 非空 department 1080/1080 枚；部门 7 档 [engineering/exec/fin/finance/hr/ops/sales]；密级 4 档 [1/2/3/4]；(部门,密级) 叉乘 16 格（其中 r59c 合成语料 12 格） | r59c 补的正是密级那一维：沙盒原有标签是 4 部门 × 各 1 档，同部门内跨密级不可判 |
| (c) 该臂召回 > 0 | PASS | 召回 > 0 的档 5/5：staff-fin-l1/manager-hr-l2/manager-ops-l2/exec-l3/admin-l3 | — |
| (d) 越权 = 0 | PASS | 越权 0 条；池外可漏材料逐档 1074/1068/1068/1062/252 枚，无谓词对照命中里本可越界逐档 59/48/51/42/0 条（合计 200 条） | 合成标签上的行为读数，不证客户隔离 |

## 四、逐档命中集合（沙盒臂）

- `staff-fin-l1`（staff / 部门 fin / 密级 ≤1，谓词 `department_scope`）：交回 60 条、去重 6 枚，命中项 (密级,部门) 去重清单 `(1,fin)`，越权 0 条 → **MEASURED_WITH_TEETH**。
  - 池内该档可召的 r59c 行（6 枚）：`r59c-fin-l1-000` `r59c-fin-l1-001` `r59c-fin-l1-002` `r59c-fin-l1-003` `r59c-fin-l1-004` `r59c-fin-l1-005`
  - 实际命中的 vector_id（去重 6 枚）：`r59c-fin-l1-000` `r59c-fin-l1-001` `r59c-fin-l1-002` `r59c-fin-l1-003` `r59c-fin-l1-004` `r59c-fin-l1-005`
- `manager-hr-l2`（manager / 部门 hr / 密级 ≤2，谓词 `department_scope`）：交回 60 条、去重 12 枚，命中项 (密级,部门) 去重清单 `(1,hr)` `(2,hr)`，越权 0 条 → **MEASURED_WITH_TEETH**。
  - 池内该档可召的 r59c 行（12 枚）：`r59c-hr-l1-000` `r59c-hr-l1-001` `r59c-hr-l1-002` `r59c-hr-l1-003` `r59c-hr-l1-004` `r59c-hr-l1-005` `r59c-hr-l2-000` `r59c-hr-l2-001` `r59c-hr-l2-002` `r59c-hr-l2-003` `r59c-hr-l2-004` `r59c-hr-l2-005`
  - 实际命中的 vector_id（去重 12 枚）：`r59c-hr-l1-000` `r59c-hr-l1-001` `r59c-hr-l1-002` `r59c-hr-l1-003` `r59c-hr-l1-004` `r59c-hr-l1-005` `r59c-hr-l2-000` `r59c-hr-l2-001` `r59c-hr-l2-002` `r59c-hr-l2-003` `r59c-hr-l2-004` `r59c-hr-l2-005`
- `manager-ops-l2`（manager / 部门 ops / 密级 ≤2，谓词 `department_scope`）：交回 60 条、去重 12 枚，命中项 (密级,部门) 去重清单 `(1,ops)` `(2,ops)`，越权 0 条 → **MEASURED_WITH_TEETH**。
  - 池内该档可召的 r59c 行（12 枚）：`r59c-ops-l1-000` `r59c-ops-l1-001` `r59c-ops-l1-002` `r59c-ops-l1-003` `r59c-ops-l1-004` `r59c-ops-l1-005` `r59c-ops-l2-000` `r59c-ops-l2-001` `r59c-ops-l2-002` `r59c-ops-l2-003` `r59c-ops-l2-004` `r59c-ops-l2-005`
  - 实际命中的 vector_id（去重 12 枚）：`r59c-ops-l1-000` `r59c-ops-l1-001` `r59c-ops-l1-002` `r59c-ops-l1-003` `r59c-ops-l1-004` `r59c-ops-l1-005` `r59c-ops-l2-000` `r59c-ops-l2-001` `r59c-ops-l2-002` `r59c-ops-l2-003` `r59c-ops-l2-004` `r59c-ops-l2-005`
- `exec-l3`（manager / 部门 exec / 密级 ≤3，谓词 `department_scope`）：交回 60 条、去重 18 枚，命中项 (密级,部门) 去重清单 `(1,exec)` `(2,exec)` `(3,exec)`，越权 0 条 → **MEASURED_WITH_TEETH**。
  - 池内该档可召的 r59c 行（18 枚）：`r59c-exec-l1-000` `r59c-exec-l1-001` `r59c-exec-l1-002` `r59c-exec-l1-003` `r59c-exec-l1-004` `r59c-exec-l1-005` `r59c-exec-l2-000` `r59c-exec-l2-001` `r59c-exec-l2-002` `r59c-exec-l2-003` `r59c-exec-l2-004` `r59c-exec-l2-005` `r59c-exec-l3-000` `r59c-exec-l3-001` `r59c-exec-l3-002` `r59c-exec-l3-003` `r59c-exec-l3-004` `r59c-exec-l3-005`
  - 实际命中的 vector_id（去重 18 枚）：`r59c-exec-l1-000` `r59c-exec-l1-001` `r59c-exec-l1-002` `r59c-exec-l1-003` `r59c-exec-l1-004` `r59c-exec-l1-005` `r59c-exec-l2-000` `r59c-exec-l2-001` `r59c-exec-l2-002` `r59c-exec-l2-003` `r59c-exec-l2-004` `r59c-exec-l2-005` `r59c-exec-l3-000` `r59c-exec-l3-001` `r59c-exec-l3-002` `r59c-exec-l3-003` `r59c-exec-l3-004` `r59c-exec-l3-005`
- `admin-l3`（admin / 部门 — / 密级 ≤3，谓词 `administrator_scope`）：交回 60 条、去重 44 枚，命中项 (密级,部门) 去重清单 `(1,exec)` `(1,fin)` `(1,hr)` `(1,ops)` `(2,exec)` `(2,fin)` `(2,hr)` `(2,ops)` `(3,exec)` `(3,fin)` `(3,hr)` `(3,ops)`，越权 0 条 → **MEASURED_WITH_TEETH**。
  - 池内该档可召的 r59c 行（72 枚）：`r59c-exec-l1-000` `r59c-exec-l1-001` `r59c-exec-l1-002` `r59c-exec-l1-003` `r59c-exec-l1-004` `r59c-exec-l1-005` `r59c-exec-l2-000` `r59c-exec-l2-001` `r59c-exec-l2-002` `r59c-exec-l2-003` `r59c-exec-l2-004` `r59c-exec-l2-005` `r59c-exec-l3-000` `r59c-exec-l3-001` `r59c-exec-l3-002` `r59c-exec-l3-003` `r59c-exec-l3-004` `r59c-exec-l3-005` `r59c-fin-l1-000` `r59c-fin-l1-001` `r59c-fin-l1-002` `r59c-fin-l1-003` `r59c-fin-l1-004` `r59c-fin-l1-005` `r59c-fin-l2-000` `r59c-fin-l2-001` `r59c-fin-l2-002` `r59c-fin-l2-003` `r59c-fin-l2-004` `r59c-fin-l2-005` `r59c-fin-l3-000` `r59c-fin-l3-001` `r59c-fin-l3-002` `r59c-fin-l3-003` `r59c-fin-l3-004` `r59c-fin-l3-005` `r59c-hr-l1-000` `r59c-hr-l1-001` `r59c-hr-l1-002` `r59c-hr-l1-003` `r59c-hr-l1-004` `r59c-hr-l1-005` `r59c-hr-l2-000` `r59c-hr-l2-001` `r59c-hr-l2-002` `r59c-hr-l2-003` `r59c-hr-l2-004` `r59c-hr-l2-005` `r59c-hr-l3-000` `r59c-hr-l3-001` `r59c-hr-l3-002` `r59c-hr-l3-003` `r59c-hr-l3-004` `r59c-hr-l3-005` `r59c-ops-l1-000` `r59c-ops-l1-001` `r59c-ops-l1-002` `r59c-ops-l1-003` `r59c-ops-l1-004` `r59c-ops-l1-005` `r59c-ops-l2-000` `r59c-ops-l2-001` `r59c-ops-l2-002` `r59c-ops-l2-003` `r59c-ops-l2-004` `r59c-ops-l2-005` `r59c-ops-l3-000` `r59c-ops-l3-001` `r59c-ops-l3-002` `r59c-ops-l3-003` `r59c-ops-l3-004` `r59c-ops-l3-005`
  - 实际命中的 vector_id（去重 44 枚）：`r59c-exec-l1-000` `r59c-exec-l1-001` `r59c-exec-l1-003` `r59c-exec-l1-005` `r59c-exec-l2-000` `r59c-exec-l2-001` `r59c-exec-l2-002` `r59c-exec-l2-004` `r59c-exec-l3-000` `r59c-exec-l3-002` `r59c-exec-l3-003` `r59c-exec-l3-005` `r59c-fin-l1-000` `r59c-fin-l2-000` `r59c-fin-l2-004` `r59c-fin-l3-000` `r59c-fin-l3-002` `r59c-fin-l3-004` `r59c-hr-l1-000` `r59c-hr-l1-002` `r59c-hr-l1-003` `r59c-hr-l1-004` `r59c-hr-l1-005` `r59c-hr-l2-000` `r59c-hr-l2-003` `r59c-hr-l2-005` `r59c-hr-l3-000` `r59c-hr-l3-001` `r59c-hr-l3-003` `r59c-hr-l3-004` `r59c-hr-l3-005` `r59c-ops-l1-000` `r59c-ops-l1-004` `r59c-ops-l1-005` `r59c-ops-l2-000` `r59c-ops-l2-001` `r59c-ops-l2-002` `r59c-ops-l2-003` `r59c-ops-l2-004` `r59c-ops-l3-000` `r59c-ops-l3-001` `r59c-ops-l3-002` `r59c-ops-l3-003` `r59c-ops-l3-004`

## 五、沙盒清理账

| 格 | 读数 |
|---|---|
| 写入方式（唯一写点） | `INSERT INTO chunk_vectors（唯一写点，只写 r59c- 前缀行，不带 ON CONFLICT：撞键整笔回滚，不覆盖别人那一行）` |
| 造出的行数 | 72 |
| 删除语句真源 | `app.rag.pg_store._DELETE_VECTOR_SQL` |
| 删除点名枚数 | 72 |
| 删除后 `vector_id LIKE 'r59c%'` 残留 | 0 |
| 沙盒库行数（跑前 → 跑后） | 1008 → 1008 |
| 沙盒库标签分布复现 | {'1': 252, '2': 252, '3': 252, '4': 252} → {'1': 252, '2': 252, '3': 252, '4': 252} |
| 恒量复现 | 相同 |

处置：`r59c-` 行按点名 id 删除（不是 `LIKE` 扫删），删后立即复扫前缀残留必须为 0；沙盒库不 VACUUM、不 REINDEX——HNSW 页里会留下已删条目的悬挂边，这是沙盒的代价，不是生产库的，本表不声称清到字节级。

## 六、反证钉（本单交的牙，逐把点名）

| 编号 | 咬什么 | 落在哪枚测试 |
|---|---|---|
| T1 | 把产品那道 `allows()` 摘成恒 True ⇒ 每档的 control 格当场红（判定失去可判性） | `test_counter_evidence_neutered_allows_turns_the_control_red` |
| T2 | 拿「无谓词那一臂」的命中冒充「有谓词那一臂」（＝下推谓词被旁路）⇒ 越权条数 > 0 | `test_counter_evidence_bypassed_predicate_reports_breaches` |
| T3 | 把标签抹成同值（全空部门、全 1 档密级）⇒ 逐档退回空集真、整单 NOT_MEASURED | `test_counter_evidence_homogeneous_labels_lose_selectivity` |
| T4 | 存量六枚恒量任一枚前后不同 ⇒ validate 拒出表 | `test_counter_evidence_invariant_drift_is_refused` |
| T5 | 手改表格里的任一枚读数 ⇒ 与再生件字节不符 | `test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits` |
| T6 | 生产臂被写成「有牙读数」（而 §133 六实测标签全同值）⇒ validate 直接拒 | `test_counter_evidence_a_fabricated_production_cell_is_refused` |
| T7 | 驱动里长出裸 `psycopg.connect`、或生产连接上读只标志没先落地 ⇒ 纪律钉红 | `test_the_driver_reaches_the_database_only_through_the_boundary` |
| T8 | 候选宽度/前缀/模型名等真源量在驱动里被抄成第二份字面量 ⇒ 抄数钉红 | `test_no_ticket_carries_a_second_copy_of_a_true_source_number` |
| T9 | 把记录下来的 `match: true` 当数用（现场复算与它不符）⇒ 仍拒：恒量只信现场复算 | `test_counter_evidence_a_recorded_match_flag_is_not_believed` |
| T10 | 沙盒里残留一枚 `r59c-` 行没清干净 ⇒ 拒，不许把没扫过的库交给下一班 | `test_counter_evidence_the_leftover_sandbox_row_is_refused` |

## 七、诚实边界（不许删，也不许抄成删过了）

- 沙盒标签只证「谓词按标签行为」，不证客户隔离；生产格③ 欠的是业主侧真实密级回填（A3 已裁「交付阶段按客户真实密级做」）。
- 🔴 这不等于格③ 已翻绿，也不等于 C 门翻绿：格③ 在生产侧仍记「未验」。
- 本单**没过**的判据（逐条，含为什么没过）：
  - `production` 臂 (件 a_subject_department) 判定 **未验**：users 表 3 枚里 department 非空 1 枚；admin/evalbot 实测为空；本单主体是合成 principal，不代替真账号；真账号那一格未回填 ⇒ (a) 不成立
  - `production` 臂 (件 b_corpus_labels) 判定 **FAIL**：非空 department 0/1008 枚；部门 1 档 [<空串>]；密级 1 档 [1]；(部门,密级) 叉乘 1 格（其中 r59c 合成语料 0 格）；r59c 补的正是密级那一维：沙盒原有标签是 4 部门 × 各 1 档，同部门内跨密级不可判
  - `production` 臂 (件 c_recall_positive) 判定 **FAIL**：召回 > 0 的档 1/5：admin-l3
  - `production` 臂 (件 d_zero_breach) 判定 **未验**：逐档全是空集（挡光或全放行），越权 0 条无从判；这正是 §133 六那条真账的形状
- 量到的是**库层读腿**（下推谓词 + 真库索引扫描 + 产品 `allows()` 复核）。**没量**端到端 `RetrievalPipeline`：那条腿要先 embed 查询句 ⇒ 打模型，本单硬禁；也没量 `DocumentRetriever._pgvector_hits` 的零行降级分支——它要 `DocumentRetriever`，而本单一行新 Chroma 依赖都不许加（AGENTS.md 向量库口径）。
- 合成向量是**几何夹具**不是嵌入（`r59c-synthetic-lcg`）：它只证谓词算术与索引召回，不许被引成「pgvector 的语义召回比遗留引擎好/差」。
- 沙盒池 1080 枚 ≪ 客户尺寸：J-3 在这一档全等**不可外推**，§13.二 那两句禁令（抬宽后索引扫描已≈全库暴力扫量级；自探针量不到近重复吃预算那一族）原样生效，客户尺寸两档差那一格仍未量。
- 沙盒库 `eb_r59_sandbox` 原有 1008 枚是**生产向量副本 + R59 合成标签**，标签形状是 4 部门 × 各 1 档；本班加的 72 枚 r59c 行补的正是同部门内跨密级那一维。两批标签都是合成的，都不证客户隔离。

## 八、机器证据（围栏 JSON＝本表唯一事实源）

本表由 `render_readout(evidence)` 生成；`evidence` 由 `scripts/r469_sandbox_scope_readout.py` 在容器里现取，口令一律 mask，`DATABASE_URL` 原文不入文档不入日志。
钉盯的是「手改表格」，不防「重造一份自洽的假证据」——后者要靠现场六枚恒量与容器日志对账，本单不宣称防住。

```json
{
  "arms": {
    "production": {
      "database": "enterprise_brain",
      "live_breaches": 0,
      "pool_labels": {
        "classification_distribution": {
          "1": 1008
        },
        "dept_empty": 1008,
        "distinct_classifications": [
          "1"
        ],
        "distinct_departments": [
          ""
        ],
        "distinct_pairs": 1,
        "nonempty_department": 0,
        "r59c_classifications": [],
        "r59c_departments": [],
        "r59c_distinct_pairs": 0,
        "r59c_rows": 0,
        "rows_total": 1008
      },
      "pool_total": 1008,
      "tiers": [
        {
          "admitted_total": 0,
          "clearance": 1,
          "department": "fin",
          "departments": [
            "fin"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "fin"
                  ]
                }
              }
            ]
          },
          "label": "staff-fin-l1",
          "levels": [
            1
          ],
          "outside_sample": {
            "classification": 1,
            "department": "",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1008,
          "r59c_admitted_ids": [],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            }
          ],
          "role": "staff",
          "scope_reason": "department_scope",
          "username": "r59c_staff_fin"
        },
        {
          "admitted_total": 0,
          "clearance": 2,
          "department": "hr",
          "departments": [
            "hr"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1,
                    2
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "hr"
                  ]
                }
              }
            ]
          },
          "label": "manager-hr-l2",
          "levels": [
            1,
            2
          ],
          "outside_sample": {
            "classification": 1,
            "department": "",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1008,
          "r59c_admitted_ids": [],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            }
          ],
          "role": "manager",
          "scope_reason": "department_scope",
          "username": "r59c_manager_hr"
        },
        {
          "admitted_total": 0,
          "clearance": 2,
          "department": "ops",
          "departments": [
            "ops"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1,
                    2
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "ops"
                  ]
                }
              }
            ]
          },
          "label": "manager-ops-l2",
          "levels": [
            1,
            2
          ],
          "outside_sample": {
            "classification": 1,
            "department": "",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1008,
          "r59c_admitted_ids": [],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            }
          ],
          "role": "manager",
          "scope_reason": "department_scope",
          "username": "r59c_manager_ops"
        },
        {
          "admitted_total": 0,
          "clearance": 3,
          "department": "exec",
          "departments": [
            "exec"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1,
                    2,
                    3
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "exec"
                  ]
                }
              }
            ]
          },
          "label": "exec-l3",
          "levels": [
            1,
            2,
            3
          ],
          "outside_sample": {
            "classification": 1,
            "department": "",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1008,
          "r59c_admitted_ids": [],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            }
          ],
          "role": "manager",
          "scope_reason": "department_scope",
          "username": "r59c_exec"
        },
        {
          "admitted_total": 1008,
          "clearance": 3,
          "department": "",
          "departments": null,
          "expect": "level-only",
          "filters": {
            "classification": {
              "$in": [
                1,
                2,
                3
              ]
            }
          },
          "label": "admin-l3",
          "levels": [
            1,
            2,
            3
          ],
          "outside_sample": null,
          "pool_total": 1008,
          "r59c_admitted_ids": [],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_255"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": null,
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_340"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_256"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "产品技术手册.txt_2"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习技术栈学习路线.pdf_10"
                },
                {
                  "classification": 1,
                  "department": "",
                  "id": "深度学习入门：基于Python的理论与实现.pdf_246"
                }
              ]
            }
          ],
          "role": "admin",
          "scope_reason": "administrator_scope",
          "username": "r59c_admin"
        }
      ],
      "writes": 0
    },
    "sandbox": {
      "database": "eb_r59_sandbox",
      "live_breaches": 0,
      "pool_labels": {
        "classification_distribution": {
          "1": 276,
          "2": 276,
          "3": 276,
          "4": 252
        },
        "dept_empty": 0,
        "distinct_classifications": [
          "1",
          "2",
          "3",
          "4"
        ],
        "distinct_departments": [
          "engineering",
          "exec",
          "fin",
          "finance",
          "hr",
          "ops",
          "sales"
        ],
        "distinct_pairs": 16,
        "nonempty_department": 1080,
        "r59c_classifications": [
          "1",
          "2",
          "3"
        ],
        "r59c_departments": [
          "exec",
          "fin",
          "hr",
          "ops"
        ],
        "r59c_distinct_pairs": 12,
        "r59c_rows": 72,
        "rows_total": 1080
      },
      "pool_total": 1080,
      "tiers": [
        {
          "admitted_total": 6,
          "clearance": 1,
          "department": "fin",
          "departments": [
            "fin"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "fin"
                  ]
                }
              }
            ]
          },
          "label": "staff-fin-l1",
          "levels": [
            1
          ],
          "outside_sample": {
            "classification": 1,
            "department": "sales",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1080,
          "r59c_admitted_ids": [
            "r59c-fin-l1-000",
            "r59c-fin-l1-001",
            "r59c-fin-l1-002",
            "r59c-fin-l1-003",
            "r59c-fin-l1-004",
            "r59c-fin-l1-005"
          ],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": [
                "r59c-fin-l1-004",
                "r59c-fin-l1-003",
                "r59c-fin-l1-000",
                "r59c-fin-l1-002",
                "r59c-fin-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-004"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-001"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": [
                "r59c-fin-l1-000",
                "r59c-fin-l1-002",
                "r59c-fin-l1-004",
                "r59c-fin-l1-005",
                "r59c-fin-l1-003"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": [
                "r59c-fin-l1-002",
                "r59c-fin-l1-000",
                "r59c-fin-l1-003",
                "r59c-fin-l1-005",
                "r59c-fin-l1-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": [
                "r59c-fin-l1-000",
                "r59c-fin-l1-001",
                "r59c-fin-l1-002",
                "r59c-fin-l1-005",
                "r59c-fin-l1-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": [
                "r59c-fin-l1-004",
                "r59c-fin-l1-002",
                "r59c-fin-l1-001",
                "r59c-fin-l1-003",
                "r59c-fin-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": [
                "r59c-fin-l1-004",
                "r59c-fin-l1-000",
                "r59c-fin-l1-002",
                "r59c-fin-l1-001",
                "r59c-fin-l1-003"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-002"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-002"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": [
                "r59c-fin-l1-005",
                "r59c-fin-l1-002",
                "r59c-fin-l1-003",
                "r59c-fin-l1-000",
                "r59c-fin-l1-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": [
                "r59c-fin-l1-001",
                "r59c-fin-l1-004",
                "r59c-fin-l1-003",
                "r59c-fin-l1-000",
                "r59c-fin-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": [
                "r59c-fin-l1-000",
                "r59c-fin-l1-003",
                "r59c-fin-l1-004",
                "r59c-fin-l1-005",
                "r59c-fin-l1-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": [
                "r59c-fin-l1-003",
                "r59c-fin-l1-004",
                "r59c-fin-l1-002",
                "r59c-fin-l1-001",
                "r59c-fin-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": [
                "r59c-fin-l1-002",
                "r59c-fin-l1-005",
                "r59c-fin-l1-000",
                "r59c-fin-l1-001",
                "r59c-fin-l1-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-001"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": [
                "r59c-fin-l1-000",
                "r59c-fin-l1-005",
                "r59c-fin-l1-002",
                "r59c-fin-l1-003",
                "r59c-fin-l1-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-005"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-002"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-003"
                },
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-004"
                }
              ]
            }
          ],
          "role": "staff",
          "scope_reason": "department_scope",
          "username": "r59c_staff_fin"
        },
        {
          "admitted_total": 12,
          "clearance": 2,
          "department": "hr",
          "departments": [
            "hr"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1,
                    2
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "hr"
                  ]
                }
              }
            ]
          },
          "label": "manager-hr-l2",
          "levels": [
            1,
            2
          ],
          "outside_sample": {
            "classification": 1,
            "department": "sales",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1080,
          "r59c_admitted_ids": [
            "r59c-hr-l1-000",
            "r59c-hr-l1-001",
            "r59c-hr-l1-002",
            "r59c-hr-l1-003",
            "r59c-hr-l1-004",
            "r59c-hr-l1-005",
            "r59c-hr-l2-000",
            "r59c-hr-l2-001",
            "r59c-hr-l2-002",
            "r59c-hr-l2-003",
            "r59c-hr-l2-004",
            "r59c-hr-l2-005"
          ],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": [
                "r59c-hr-l1-004",
                "r59c-hr-l2-003",
                "r59c-hr-l2-004",
                "r59c-hr-l2-002",
                "r59c-hr-l2-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-004"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-001"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": [
                "r59c-hr-l2-005",
                "r59c-hr-l1-001",
                "r59c-hr-l1-000",
                "r59c-hr-l1-003",
                "r59c-hr-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-001"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": [
                "r59c-hr-l1-004",
                "r59c-hr-l1-005",
                "r59c-hr-l2-000",
                "r59c-hr-l2-002",
                "r59c-hr-l2-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": [
                "r59c-hr-l1-003",
                "r59c-hr-l2-004",
                "r59c-hr-l1-002",
                "r59c-hr-l2-003",
                "r59c-hr-l2-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-004"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": [
                "r59c-hr-l1-000",
                "r59c-hr-l2-000",
                "r59c-hr-l2-002",
                "r59c-hr-l1-002",
                "r59c-hr-l2-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": [
                "r59c-hr-l1-002",
                "r59c-hr-l1-000",
                "r59c-hr-l2-002",
                "r59c-hr-l2-000",
                "r59c-hr-l1-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-002"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-002"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": [
                "r59c-hr-l1-000",
                "r59c-hr-l1-002",
                "r59c-hr-l1-004",
                "r59c-hr-l2-003",
                "r59c-hr-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": [
                "r59c-hr-l2-000",
                "r59c-hr-l1-004",
                "r59c-hr-l2-002",
                "r59c-hr-l1-001",
                "r59c-hr-l2-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-001"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": [
                "r59c-hr-l1-005",
                "r59c-hr-l2-002",
                "r59c-hr-l1-002",
                "r59c-hr-l1-000",
                "r59c-hr-l1-003"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": [
                "r59c-hr-l1-004",
                "r59c-hr-l1-002",
                "r59c-hr-l2-002",
                "r59c-hr-l2-001",
                "r59c-hr-l2-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-001"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": [
                "r59c-hr-l2-003",
                "r59c-hr-l1-005",
                "r59c-hr-l1-003",
                "r59c-hr-l1-004",
                "r59c-hr-l2-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": [
                "r59c-hr-l1-004",
                "r59c-hr-l2-004",
                "r59c-hr-l2-000",
                "r59c-hr-l2-003",
                "r59c-hr-l1-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-004"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-004"
                }
              ]
            }
          ],
          "role": "manager",
          "scope_reason": "department_scope",
          "username": "r59c_manager_hr"
        },
        {
          "admitted_total": 12,
          "clearance": 2,
          "department": "ops",
          "departments": [
            "ops"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1,
                    2
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "ops"
                  ]
                }
              }
            ]
          },
          "label": "manager-ops-l2",
          "levels": [
            1,
            2
          ],
          "outside_sample": {
            "classification": 1,
            "department": "sales",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1080,
          "r59c_admitted_ids": [
            "r59c-ops-l1-000",
            "r59c-ops-l1-001",
            "r59c-ops-l1-002",
            "r59c-ops-l1-003",
            "r59c-ops-l1-004",
            "r59c-ops-l1-005",
            "r59c-ops-l2-000",
            "r59c-ops-l2-001",
            "r59c-ops-l2-002",
            "r59c-ops-l2-003",
            "r59c-ops-l2-004",
            "r59c-ops-l2-005"
          ],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": [
                "r59c-ops-l2-000",
                "r59c-ops-l2-003",
                "r59c-ops-l2-004",
                "r59c-ops-l1-002",
                "r59c-ops-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-002"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-004"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-001"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": [
                "r59c-ops-l1-005",
                "r59c-ops-l1-004",
                "r59c-ops-l2-002",
                "r59c-ops-l1-001",
                "r59c-ops-l1-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": [
                "r59c-ops-l2-001",
                "r59c-ops-l2-002",
                "r59c-ops-l2-003",
                "r59c-ops-l2-004",
                "r59c-ops-l2-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": [
                "r59c-ops-l1-001",
                "r59c-ops-l1-004",
                "r59c-ops-l2-003",
                "r59c-ops-l2-001",
                "r59c-ops-l2-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": [
                "r59c-ops-l2-005",
                "r59c-ops-l2-004",
                "r59c-ops-l2-003",
                "r59c-ops-l1-003",
                "r59c-ops-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-005"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-003"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": [
                "r59c-ops-l1-003",
                "r59c-ops-l1-000",
                "r59c-ops-l1-005",
                "r59c-ops-l2-004",
                "r59c-ops-l2-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-003"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-002"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-002"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": [
                "r59c-ops-l2-003",
                "r59c-ops-l2-004",
                "r59c-ops-l1-002",
                "r59c-ops-l2-001",
                "r59c-ops-l2-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": [
                "r59c-ops-l2-003",
                "r59c-ops-l1-000",
                "r59c-ops-l2-001",
                "r59c-ops-l1-002",
                "r59c-ops-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-002"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": [
                "r59c-ops-l1-002",
                "r59c-ops-l1-005",
                "r59c-ops-l2-001",
                "r59c-ops-l1-001",
                "r59c-ops-l2-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-002"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-001"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": [
                "r59c-ops-l1-000",
                "r59c-ops-l1-005",
                "r59c-ops-l2-003",
                "r59c-ops-l2-002",
                "r59c-ops-l1-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": [
                "r59c-ops-l2-000",
                "r59c-ops-l1-003",
                "r59c-ops-l2-002",
                "r59c-ops-l2-004",
                "r59c-ops-l2-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": [
                "r59c-ops-l2-002",
                "r59c-ops-l1-001",
                "r59c-ops-l2-004",
                "r59c-ops-l2-003",
                "r59c-ops-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-001"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-004"
                }
              ]
            }
          ],
          "role": "manager",
          "scope_reason": "department_scope",
          "username": "r59c_manager_ops"
        },
        {
          "admitted_total": 18,
          "clearance": 3,
          "department": "exec",
          "departments": [
            "exec"
          ],
          "expect": "department+level",
          "filters": {
            "$and": [
              {
                "classification": {
                  "$in": [
                    1,
                    2,
                    3
                  ]
                }
              },
              {
                "department": {
                  "$in": [
                    "exec"
                  ]
                }
              }
            ]
          },
          "label": "exec-l3",
          "levels": [
            1,
            2,
            3
          ],
          "outside_sample": {
            "classification": 1,
            "department": "sales",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_0"
          },
          "pool_total": 1080,
          "r59c_admitted_ids": [
            "r59c-exec-l1-000",
            "r59c-exec-l1-001",
            "r59c-exec-l1-002",
            "r59c-exec-l1-003",
            "r59c-exec-l1-004",
            "r59c-exec-l1-005",
            "r59c-exec-l2-000",
            "r59c-exec-l2-001",
            "r59c-exec-l2-002",
            "r59c-exec-l2-003",
            "r59c-exec-l2-004",
            "r59c-exec-l2-005",
            "r59c-exec-l3-000",
            "r59c-exec-l3-001",
            "r59c-exec-l3-002",
            "r59c-exec-l3-003",
            "r59c-exec-l3-004",
            "r59c-exec-l3-005"
          ],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": [
                "r59c-exec-l1-000",
                "r59c-exec-l1-005",
                "r59c-exec-l3-004",
                "r59c-exec-l3-001",
                "r59c-exec-l3-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-004"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-001"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": [
                "r59c-exec-l2-000",
                "r59c-exec-l2-002",
                "r59c-exec-l3-001",
                "r59c-exec-l3-005",
                "r59c-exec-l2-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": [
                "r59c-exec-l3-000",
                "r59c-exec-l3-002",
                "r59c-exec-l2-004",
                "r59c-exec-l1-001",
                "r59c-exec-l2-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": [
                "r59c-exec-l3-003",
                "r59c-exec-l1-003",
                "r59c-exec-l2-000",
                "r59c-exec-l3-001",
                "r59c-exec-l3-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": [
                "r59c-exec-l1-003",
                "r59c-exec-l2-004",
                "r59c-exec-l2-001",
                "r59c-exec-l3-000",
                "r59c-exec-l2-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": [
                "r59c-exec-l2-004",
                "r59c-exec-l2-003",
                "r59c-exec-l1-004",
                "r59c-exec-l3-003",
                "r59c-exec-l2-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-002"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-002"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": [
                "r59c-exec-l3-005",
                "r59c-exec-l2-003",
                "r59c-exec-l3-003",
                "r59c-exec-l2-000",
                "r59c-exec-l3-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": [
                "r59c-exec-l1-003",
                "r59c-exec-l1-001",
                "r59c-exec-l2-005",
                "r59c-exec-l1-005",
                "r59c-exec-l3-000"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": [
                "r59c-exec-l3-003",
                "r59c-exec-l1-003",
                "r59c-exec-l1-005",
                "r59c-exec-l2-002",
                "r59c-exec-l2-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": [
                "r59c-exec-l2-003",
                "r59c-exec-l3-001",
                "r59c-exec-l2-000",
                "r59c-exec-l2-001",
                "r59c-exec-l2-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": [
                "r59c-exec-l2-001",
                "r59c-exec-l3-004",
                "r59c-exec-l1-000",
                "r59c-exec-l1-002",
                "r59c-exec-l3-003"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-002"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": [
                "r59c-exec-l1-000",
                "r59c-exec-l2-000",
                "r59c-exec-l3-001",
                "r59c-exec-l2-001",
                "r59c-exec-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-004"
                }
              ]
            }
          ],
          "role": "manager",
          "scope_reason": "department_scope",
          "username": "r59c_exec"
        },
        {
          "admitted_total": 828,
          "clearance": 3,
          "department": "",
          "departments": null,
          "expect": "level-only",
          "filters": {
            "classification": {
              "$in": [
                1,
                2,
                3
              ]
            }
          },
          "label": "admin-l3",
          "levels": [
            1,
            2,
            3
          ],
          "outside_sample": {
            "classification": 4,
            "department": "hr",
            "id": "2025-2026中国企业协同办公市场研究报告.txt_3"
          },
          "pool_total": 1080,
          "r59c_admitted_ids": [
            "r59c-exec-l1-000",
            "r59c-exec-l1-001",
            "r59c-exec-l1-002",
            "r59c-exec-l1-003",
            "r59c-exec-l1-004",
            "r59c-exec-l1-005",
            "r59c-exec-l2-000",
            "r59c-exec-l2-001",
            "r59c-exec-l2-002",
            "r59c-exec-l2-003",
            "r59c-exec-l2-004",
            "r59c-exec-l2-005",
            "r59c-exec-l3-000",
            "r59c-exec-l3-001",
            "r59c-exec-l3-002",
            "r59c-exec-l3-003",
            "r59c-exec-l3-004",
            "r59c-exec-l3-005",
            "r59c-fin-l1-000",
            "r59c-fin-l1-001",
            "r59c-fin-l1-002",
            "r59c-fin-l1-003",
            "r59c-fin-l1-004",
            "r59c-fin-l1-005",
            "r59c-fin-l2-000",
            "r59c-fin-l2-001",
            "r59c-fin-l2-002",
            "r59c-fin-l2-003",
            "r59c-fin-l2-004",
            "r59c-fin-l2-005",
            "r59c-fin-l3-000",
            "r59c-fin-l3-001",
            "r59c-fin-l3-002",
            "r59c-fin-l3-003",
            "r59c-fin-l3-004",
            "r59c-fin-l3-005",
            "r59c-hr-l1-000",
            "r59c-hr-l1-001",
            "r59c-hr-l1-002",
            "r59c-hr-l1-003",
            "r59c-hr-l1-004",
            "r59c-hr-l1-005",
            "r59c-hr-l2-000",
            "r59c-hr-l2-001",
            "r59c-hr-l2-002",
            "r59c-hr-l2-003",
            "r59c-hr-l2-004",
            "r59c-hr-l2-005",
            "r59c-hr-l3-000",
            "r59c-hr-l3-001",
            "r59c-hr-l3-002",
            "r59c-hr-l3-003",
            "r59c-hr-l3-004",
            "r59c-hr-l3-005",
            "r59c-ops-l1-000",
            "r59c-ops-l1-001",
            "r59c-ops-l1-002",
            "r59c-ops-l1-003",
            "r59c-ops-l1-004",
            "r59c-ops-l1-005",
            "r59c-ops-l2-000",
            "r59c-ops-l2-001",
            "r59c-ops-l2-002",
            "r59c-ops-l2-003",
            "r59c-ops-l2-004",
            "r59c-ops-l2-005",
            "r59c-ops-l3-000",
            "r59c-ops-l3-001",
            "r59c-ops-l3-002",
            "r59c-ops-l3-003",
            "r59c-ops-l3-004",
            "r59c-ops-l3-005"
          ],
          "reads": [
            {
              "anchor": "r59c-exec-l1-000",
              "exact": [
                "r59c-exec-l1-000",
                "r59c-fin-l2-004",
                "r59c-ops-l3-001",
                "r59c-hr-l3-003",
                "r59c-exec-l1-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-004"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-001"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-004"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-001"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-003"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-005"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l2-000",
              "exact": [
                "r59c-exec-l2-000",
                "r59c-exec-l2-002",
                "r59c-hr-l2-005",
                "r59c-ops-l1-005",
                "r59c-ops-l1-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-000"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-002"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-exec-l3-000",
              "exact": [
                "r59c-exec-l3-000",
                "r59c-hr-l1-004",
                "r59c-exec-l3-002",
                "r59c-ops-l2-001",
                "r59c-exec-l2-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l1-000",
              "exact": [
                "r59c-fin-l1-000",
                "r59c-ops-l3-004",
                "r59c-hr-l3-001",
                "r59c-exec-l3-003",
                "r59c-ops-l3-003"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "fin",
                  "id": "r59c-fin-l1-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l2-000",
              "exact": [
                "r59c-fin-l2-000",
                "r59c-hr-l3-000",
                "r59c-exec-l1-003",
                "r59c-exec-l2-004",
                "r59c-exec-l2-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-fin-l3-000",
              "exact": [
                "r59c-fin-l3-000",
                "r59c-ops-l3-002",
                "r59c-hr-l3-001",
                "r59c-exec-l2-004",
                "r59c-fin-l3-002"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-002"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-002"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-002"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-004"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-002"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l1-000",
              "exact": [
                "r59c-hr-l1-000",
                "r59c-hr-l1-002",
                "r59c-ops-l2-003",
                "r59c-ops-l2-004",
                "r59c-exec-l3-005"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-002"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-003"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-004"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-005"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l2-000",
              "exact": [
                "r59c-hr-l2-000",
                "r59c-hr-l3-005",
                "r59c-exec-l1-003",
                "r59c-hr-l1-004",
                "r59c-exec-l1-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-005"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-001"
                }
              ]
            },
            {
              "anchor": "r59c-hr-l3-000",
              "exact": [
                "r59c-hr-l3-000",
                "r59c-hr-l1-005",
                "r59c-fin-l2-000",
                "r59c-ops-l3-003",
                "r59c-exec-l3-003"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 2,
                  "department": "fin",
                  "id": "r59c-fin-l2-000"
                },
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-003"
                },
                {
                  "classification": 3,
                  "department": "exec",
                  "id": "r59c-exec-l3-003"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l1-000",
              "exact": [
                "r59c-ops-l1-000",
                "r59c-fin-l3-004",
                "r59c-hr-l3-001",
                "r59c-ops-l1-005",
                "r59c-hr-l1-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-000"
                },
                {
                  "classification": 3,
                  "department": "fin",
                  "id": "r59c-fin-l3-004"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-001"
                },
                {
                  "classification": 1,
                  "department": "ops",
                  "id": "r59c-ops-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l2-000",
              "exact": [
                "r59c-ops-l2-000",
                "r59c-hr-l2-003",
                "r59c-hr-l1-005",
                "r59c-hr-l1-003",
                "r59c-exec-l2-001"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ],
              "unscoped": [
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-000"
                },
                {
                  "classification": 2,
                  "department": "hr",
                  "id": "r59c-hr-l2-003"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-005"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-003"
                },
                {
                  "classification": 2,
                  "department": "exec",
                  "id": "r59c-exec-l2-001"
                }
              ]
            },
            {
              "anchor": "r59c-ops-l3-000",
              "exact": [
                "r59c-ops-l3-000",
                "r59c-hr-l1-004",
                "r59c-ops-l2-002",
                "r59c-exec-l1-000",
                "r59c-hr-l3-004"
              ],
              "k": 5,
              "scoped": [
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-004"
                }
              ],
              "unscoped": [
                {
                  "classification": 3,
                  "department": "ops",
                  "id": "r59c-ops-l3-000"
                },
                {
                  "classification": 1,
                  "department": "hr",
                  "id": "r59c-hr-l1-004"
                },
                {
                  "classification": 2,
                  "department": "ops",
                  "id": "r59c-ops-l2-002"
                },
                {
                  "classification": 1,
                  "department": "exec",
                  "id": "r59c-exec-l1-000"
                },
                {
                  "classification": 3,
                  "department": "hr",
                  "id": "r59c-hr-l3-004"
                }
              ]
            }
          ],
          "role": "admin",
          "scope_reason": "administrator_scope",
          "username": "r59c_admin"
        }
      ],
      "writes": 72
    }
  },
  "cleanup": {
    "delete_sql_source": "app.rag.pg_store._DELETE_VECTOR_SQL",
    "deleted": 72,
    "inserted": 72,
    "leftover_prefixed_rows": 0,
    "vacuum_or_reindex": false,
    "write_shape": "INSERT INTO chunk_vectors（唯一写点，只写 r59c- 前缀行，不带 ON CONFLICT：撞键整笔回滚，不覆盖别人那一行）"
  },
  "corpus": {
    "anchors": [
      "r59c-exec-l1-000",
      "r59c-exec-l2-000",
      "r59c-exec-l3-000",
      "r59c-fin-l1-000",
      "r59c-fin-l2-000",
      "r59c-fin-l3-000",
      "r59c-hr-l1-000",
      "r59c-hr-l2-000",
      "r59c-hr-l3-000",
      "r59c-ops-l1-000",
      "r59c-ops-l2-000",
      "r59c-ops-l3-000"
    ],
    "chunks": 72,
    "classifications": [
      1,
      2,
      3
    ],
    "corpus_sha": "4edc8884381b6c49",
    "departments": [
      "fin",
      "hr",
      "ops",
      "exec"
    ],
    "dimension": 768,
    "distance_function": "l2",
    "embedding_model": "r59c-synthetic-lcg",
    "ordinals_per_cell": 6,
    "schema": "r59c-sandbox-3",
    "tool": "scripts/r59c_sandbox_corpus.py",
    "top_k": 5,
    "vector_id_prefix": "r59c-"
  },
  "generated_by": "scripts/r469_sandbox_scope_readout.py",
  "invariants": {
    "core_six": {
      "after": {
        "chunk_vectors": 1008,
        "dataset_versions": 6,
        "document_versions": 100,
        "documents": 105,
        "resource_versions": 129,
        "users": 3
      },
      "before": {
        "chunk_vectors": 1008,
        "dataset_versions": 6,
        "document_versions": 100,
        "documents": 105,
        "resource_versions": 129,
        "users": 3
      },
      "match": true,
      "tables": [
        "chunk_vectors",
        "documents",
        "document_versions",
        "dataset_versions",
        "resource_versions",
        "users"
      ]
    },
    "production_accounts": {
      "non_admin_accounts_with_department": 1,
      "rows": [
        {
          "department": "<NULL>",
          "role": "admin",
          "username": "admin"
        },
        {
          "department": "财务部",
          "role": "staff",
          "username": "dataowner"
        },
        {
          "department": "<NULL>",
          "role": "admin",
          "username": "evalbot"
        }
      ],
      "users_total": 3,
      "users_with_department": 1
    },
    "production_labels": {
      "after": {
        "classification_distribution": {
          "1": 1008
        },
        "dept_empty": 1008,
        "distinct_classifications": [
          "1"
        ],
        "distinct_departments": [
          ""
        ],
        "distinct_pairs": 1,
        "nonempty_department": 0,
        "r59c_classifications": [],
        "r59c_departments": [],
        "r59c_distinct_pairs": 0,
        "r59c_rows": 0,
        "rows_total": 1008,
        "users_with_department": 1
      },
      "before": {
        "classification_distribution": {
          "1": 1008
        },
        "dept_empty": 1008,
        "distinct_classifications": [
          "1"
        ],
        "distinct_departments": [
          ""
        ],
        "distinct_pairs": 1,
        "nonempty_department": 0,
        "r59c_classifications": [],
        "r59c_departments": [],
        "r59c_distinct_pairs": 0,
        "r59c_rows": 0,
        "rows_total": 1008,
        "users_with_department": 1
      },
      "match": true
    },
    "sandbox": {
      "after": {
        "classification_distribution": {
          "1": 252,
          "2": 252,
          "3": 252,
          "4": 252
        },
        "dept_empty": 0,
        "distinct_pairs": 4,
        "nonempty_department": 1008,
        "prefixed_rows": 0,
        "rows_total": 1008
      },
      "before": {
        "classification_distribution": {
          "1": 252,
          "2": 252,
          "3": 252,
          "4": 252
        },
        "dept_empty": 0,
        "distinct_pairs": 4,
        "nonempty_department": 1008,
        "prefixed_rows": 0,
        "rows_total": 1008
      },
      "match": true
    }
  },
  "renderer": "scripts/r469_readout_lib.py",
  "run": {
    "base_commit": "9c214907fecf92be1cf13156380b56d52fab48df",
    "container": "875a42c45a1e",
    "cwd": "/app",
    "database_url_masked": {
      "production": "postgresql://enterprise_brain:***@postgres:5432/enterprise_brain",
      "sandbox": "postgresql://enterprise_brain:***@postgres:5432/eb_r59_sandbox"
    },
    "dual_write": "on",
    "embedding_model_env": "nomic-embed-text",
    "finished_at": "2026-09-28T23:42:36+0800",
    "hnsw_ef_search": 100,
    "hnsw_ef_search_source": "app.rag.pg_store.configured_hnsw_ef_search",
    "image_revision": "9c214907fecf92be1cf13156380b56d52fab48df",
    "mode": "full",
    "production_identity": {
      "database": "enterprise_brain",
      "server_addr": "172.18.0.7/32",
      "server_port": 5432,
      "transaction_read_only": "on",
      "user": "enterprise_brain",
      "version": "PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit"
    },
    "production_identity_after": {
      "database": "enterprise_brain",
      "server_addr": "172.18.0.7/32",
      "server_port": 5432,
      "transaction_read_only": "on",
      "user": "enterprise_brain",
      "version": "PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit"
    },
    "production_read_leg_note": "生产侧取证与读数都只 SELECT：取证走本件那枚会话级 READ ONLY；读腿自己的连接由 pg_store.read_topk 管，它 finally 里 close 且从不 commit（那件里 Reads never commit 那句在册注释就是这件事的凭据）",
    "python": "/app/.venv/bin/python",
    "r59c_path": "/app/scripts/r59c_sandbox_corpus.py",
    "r59c_sha256": "dd1dda14f4af3fa53c8c75f2139efae9c0a83455b89c25dc5669dedcad087882",
    "read_backend": {
      "env_name": "INDEX_BACKEND",
      "shipped_default": "chroma",
      "this_process": "pgvector"
    },
    "sandbox_identity": {
      "database": "eb_r59_sandbox",
      "server_addr": "172.18.0.7/32",
      "server_port": 5432,
      "transaction_read_only": "off",
      "user": "enterprise_brain",
      "version": "PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit"
    },
    "started_at": "2026-09-28T23:42:16+0800",
    "vector_scope": {
      "dimension": 768,
      "distance_function": "l2",
      "embedding_model": "nomic-embed-text"
    }
  },
  "schema": "r469-scope-readout-1",
  "ticket": "R469"
}
```
