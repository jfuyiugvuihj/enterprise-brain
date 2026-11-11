# 知识图谱定位裁定与口径晋升路径（R15-a / R15-b）

> 结论先行：**R15-a 选「乙」**——知识图谱是**候选断言采集表**，不是推理引擎；它的唯一出口是把人工核对过的
> 候选关系晋升成 `metric_definitions` 正式口径（R15-b）。两条判据落在同一批改动里，不留"文档说一套、
> 代码留一半"的悬空状态。

## 1. 为什么是乙（甲的入口不在本单，也不在今天的排期里）

跟进单 `docs/handoff/2026-09-15-backend-followup-requests.md` §11.2 给的是二选一，并附两条硬约束：
**不得只改文档不改代码来"对齐"**，也**不得为凑判据写一个没人调用的读取点**；§11.6 又加了一条前置：
选甲之前必须先有 C-4 的检索授权口径落定，否则"Agent 读图谱"要再踩一次"空部门算不算公开"。

| 路线 | 本单能否合法完成 | 说明 |
|---|---|---|
| 甲：Agent 真实读取图谱关系并注入上下文 | **不能** | 判据要求 `git grep -n "KnowledgeGraph" -- app/agents` 有结果**且**有一条"回答依据必须引用该关系"的测试。本单禁止改 `app/agents/**`；且 C-4 检索授权口径未定，写入侧的 scope 语义（空部门、clearance 钳制）在读取侧还没有对应判据 |
| 乙：承认它是采集表，把口径钉死 | **能** | 改的是 §10.4 与 §18 的表述，加的是**真能跑**的晋升链路与测试，不是给文档补一句漂亮话 |

选乙之后如果只写一句"这是一张没人用的表"，等于给答辩递刀子。把晋升路径做实，乙的说法才是完整的：
**这是一条有出口的链路，出口今天已经通了。**

## 2. 现场事实（与代码一致，不含推测）

| 事实 | 权威口径 | 怎么复跑 |
|---|---|---|
| 运行时存储是 JSON 文件，集合 `knowledge_graph_relations` | `app/knowledge_graph/service.py` 的 `_STORE_COLLECTION` 与 `JsonPersistenceAdapter` | `python -m pytest -q tests/test_knowledge_graph_verification.py` |
| 没有任何 `relations`/`entities` 表 | `migrations/0001`–`0009` 全文无该表 | `python -m pytest -q tests/test_semantic_definition_migration.py` |
| 生产未配置 `KNOWLEDGE_GRAPH_STORE_PATH` 即只读 | `KnowledgeGraph.state_for_store`：`storage_mode=unavailable`、`protection=read_only`、detail `KNOWLEDGE_GRAPH_STORE_PATH is not configured; relation writes are refused` | `python -m pytest -q tests/test_knowledge_graph_verification.py::test_production_without_a_store_path_reports_read_only_and_refuses_every_write` |
| 只读落到 HTTP 是 503 `storage_read_only` | `app/api/v1/intelligence.py` 的 `add_relation` 捕获 `ProductionReadOnlyProtection` | `python -m pytest -q tests/test_response_hygiene.py` |
| Agent 侧零消费 | `git grep -n "KnowledgeGraph" -- app/agents` → 0 命中 | 直接执行该命令 |

容器真机口径（订正 2026-09-16 20:56，总控实跑，替掉工单里那条过期快照）：工单随包下达的那句
「真机 = `unavailable` / `read_only`」是**配置变更之前**的读数，已不成立。总控随后在
`deploy/.env.server` 补上 `KNOWLEDGE_GRAPH_STORE_PATH=/app/data/knowledge_graph.json`，此后经 nginx
`GET /api/v1/health/details` 实测 `storage.subsystems.knowledge_graph` 为
`{"storage_mode":"json","durable":true,"protection":"none","detail":"relations persisted to collection
knowledge_graph_relations"}`，`problems` 只剩 `["model_not_available"]`（`knowledge_graph_read_only` 已消失）；
`POST /api/v1/knowledge-graph/relations` 实测 200 且 `status=candidate`，UTF-8 中文往返无损。
所以本节表格要读准成立条件：**未配置该变量的客户环境**才是只读并返 503 `storage_read_only`，
配置了才是可写的候选断言采集表——两种形态都由用例钉住，不存在「文档说一套、代码留一半」。
本单未做任何 Docker/compose 操作，上表最后一列是同一判据分支上的离线复现；真机证据由总控补齐在本段。
`shared_across_processes` 在带外改文件时不可信，见跟进单 R19。

## 3. 晋升链路（R15-b）：状态、权限、稳定码

```
candidate ──(作者 confirm：仅表示记录本身成立)──▶ confirmed
    │                                                │
    │                record_verification(verified, 文档, 段落) 由非作者的 approve 持有者给出
    │                                                ▼
    │                                            verified（status 仍为 confirmed）
    │                                                │
    │                              promote_relation_to_definition(...)
    │                                                ▼
    │                    metric_definitions 一行 verification_state=verified
    │                                                │
    │                                    record_promotion ──▶ status=promoted
    └── record_verification(rejected) ──▶ rejected（verified_document/section 留空）
```

- **权限**：复核与晋升都要求 `resource:approve`（manager/admin 持有，staff 不持有），且复核人必须**读得到**这条关系
  （沿用 `app/common/policy.py` 既有作用域判定，不新增权限层级）；
- **四眼原则**：作者不得自核（`self_verification_refused`）。理由与语义层原有不变量同一句：**自证标记不是证据**；
- **核对必须指名道姓**：`verified` 落库要 `verified_document` + `verified_section` + `verified_by` + `verified_at`，
  `0009` 用 CHECK 钉死，读侧再核一遍，证据不全一律按 `unverified` 报；
- **稳定码**：`relation_not_found`、`authentication_required`、`approval_permission_required`、`permission_denied`、
  `self_verification_refused`、`relation_verification_evidence_required`、`relation_verification_outcome`、
  `relation_not_verified`、`relation_definition_id_required`；
- **失败不粉饰**：`register_metric_definition` 返回 `skipped`/`failed`（库不可达或写失败）时，关系**保持
  `confirmed`**、`promoted_definition_id` 留空——没写进表的口径不许声称已晋升。

## 4. 语义层欠账的还法

`app/semantics/registry.py` 的模块文档原本自己承认：`metric_definitions` 没有 display label 与 prose definition 的列，
这些字段躲在 `filters` JSONB 的保留键 `semantics` 里，读的时候再剥出来。`migrations/0009_metric_definition_semantics.sql`
办两件事：

1. **提成真列**：`metric_name` / `definition_text` / `time_granularity` / `origin` / `match_terms`（JSONB 数组列，受
   `jsonb_typeof = 'array'` 约束），并从原镜像做**只补空值**的条件回填；
2. **加核对字段**：`verification_state`（`unverified|verified` 封闭枚举）+ `verified_document` / `verified_section` /
   `verified_by` / `verified_at` + `source_relation_id`，让"未核对"成为可消除的状态而不是一句永久 warning。

读侧顺序：**真列优先，镜像只在真列为 NULL 时兜底**（存量行才读得到标签）；`verification` 一律**不**从 JSONB 读，
回填也不碰核对列。写侧暂时**仍写一份镜像**——`tests/test_business_semantics.py` 钉着"sync 写出的行镜像里要有
`semantics`"，而该文件不在本单允许改动清单内；这也符合"应用可回滚、schema 不跟着回滚"的部署现实。
镜像的删除时机见 §6。

## 5. 答辩不许说的话

- ✗ "图谱提升了问答质量"：Agent 侧零消费（§2 的 grep），没有 A/B，评测平台 §12.3 自标部分落地；
- ✗ "第一版存储用 PostgreSQL 邻接表"：0009 之后仍然没有 `relations`/`entities` 表，这句已从 §10.4 删除；
- ✗ "指标口径都已与制度文件核对"：核对是**逐条**晋升出来的，`metric_catalog()` 的 `verified_against_documents`
  只有在目录里**每一条**都带齐证据时才为真；`definition_verification` 的两个计数并排放着，就是为了让这句话说不出口；
- ✗ "候选关系可以在页面上点一下就变口径"：核对与晋升**尚无 HTTP 入口**（§6）。

## 6. 未做与后继

| 未做项 | 原因 | 归口 |
|---|---|---|
| 核对/晋升的 HTTP 入口（如 `POST /knowledge-graph/relations/{id}/verification`） | 本单禁止改 `app/api/v1/**`；新路由要动契约错误码表，属 W4 的口径面 | 待总控排期 |
| 阈值进配置表（R15-c） | 总控已判定并入 §12.4 配置治理，本单禁改 `app/insights/rules.py`、`app/approval/assistant.py` | §12.4 |
| 图数据库（R15-d） | 已裁定不引入；`tests/test_semantic_definition_migration.py::test_no_graph_database_was_introduced` 把它钉成回归门 | 关闭 |
| 删除 `filters` JSONB 的 `semantics` 镜像写 | 必须同时改 `tests/test_business_semantics.py`（本单禁改） | 下一个允许改该文件的批次 |
| `docs/current-functionality-2026-09-10.md` §16 仍写"内存字典/重启丢失/无删除接口" | 与现状不符，但该文件不在本单允许清单内 | 新发现，交总控记账 |
| 真机/容器复验（0009 在 PG 上回放、晋升后再读 `/health/details`） | 本单禁止一切 Docker/compose 操作 | 待总控复验 |

## 7. 本批判据自证

| 判据 | 落点 |
|---|---|
| 一条测试跑通"候选关系 → 正式定义 → warning 消失"，断言落在真列 | `tests/test_semantic_promotion.py::test_a_verified_relation_becomes_a_definition_the_warning_disappears_from` |
| §10.4 的存储介质描述与 `app/knowledge_graph/service.py` 一致 | 本文 §2 逐行给出符号名与复跑命令；"PG 邻接表是目标态"已删 |
| 全量 pytest 三件数字 | 见本批交付答复（命令、时点、passed/failed/skipped 齐全） |
