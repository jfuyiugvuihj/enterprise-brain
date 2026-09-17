# 企业智脑（Enterprise Brain）架构设计文档

> 版本：v2.0 ｜ 日期：2026-09-17 ｜ 分支基线：`codex/data-file-catalog` @ ec0f40b
>
> **文档定位**：本文档是系统的**目标态架构设计文档**。它以当前代码结构为骨架，把 `docs/current-functionality-2026-09-10.md` 记录的现状、以及 `task_plan.md`、`docs/superpowers/plans|specs/`、`docs/frontend-plan-2026-09-14.md`、`docs/handoff/` 中尚未完成但已立项的计划（PGVector 切换、评测平台、Trace 回放、RAG 调试台、配置治理、数据集版本血缘、前端 V3/V4/V6、容器端到端门禁等）**统一按"已纳入设计、按计划交付"的目标形态书写**。
>
> **与 v1.0 的关系**：本文取代 `docs/system-design-2026-09-16.md`（v1.0，已归档保留）。v2.0 收录 2026-09-16 之后合入的一批落地能力：HITL 待审批账本（R12/R13，迁移 0008）、取消按代生效（R18）、总览服务端聚合（R14-A1）、知识图谱口径晋升链路（R15-b，迁移 0009）、语义指标生命周期、RBAC 单一 scoping 来源（C-4）、前端产物列表与真告警链（W6/W7）。
>
> **与现状文档的关系**：现状与完成度以 `docs/current-functionality-2026-09-10.md` 为唯一事实来源；本文不重复追踪清单，只在 §18 给出"设计条目 ↔ 落地基线"对照表，避免把过渡方案误写成生产架构（如 Chroma → PGVector）。

---

## 目录

1. [产品概述](#1-产品概述)
2. [总体架构](#2-总体架构)
3. [核心设计原则](#3-核心设计原则)
4. [身份与权限体系](#4-身份与权限体系)
5. [数据与存储设计](#5-数据与存储设计)
6. [文档知识库与 RAG 检索管线](#6-文档知识库与-rag-检索管线)
7. [多 Agent 编排引擎](#7-多-agent-编排引擎)
8. [HITL 人机协同](#8-hitl-人机协同)
9. [数据分析与产物体系](#9-数据分析与产物体系)
10. [经营智能子系统](#10-经营智能子系统)
11. [模型接入与路由](#11-模型接入与路由)
12. [可观测性与质量平台](#12-可观测性与质量平台)
13. [安全设计](#13-安全设计)
14. [API 契约设计](#14-api-契约设计)
15. [前端设计](#15-前端设计)
16. [部署与运维](#16-部署与运维)
17. [测试与验收体系](#17-测试与验收体系)
18. [附录：设计条目与落地基线对照](#18-附录设计条目与落地基线对照)

---

## 1. 产品概述

### 1.1 产品定位

企业智脑是**私有化部署**的企业 AI 智能分析平台：客户将系统安装在自己的服务器上，上传公司文档与经营数据，由 AI 提供知识问答、数据分析、图表报告生成与异常监控。**数据永不离开客户机器**——私有化的定义是"一台机器一个企业，物理隔离"，不是多租户 SaaS。

### 1.2 目标用户与角色

| 角色 | 密级 | 典型使用 |
|---|---|---|
| `staff`（员工） | 1 | 上传/检索自己可见的文档，提问，报销自查 |
| `manager`（管理者） | 2 | 部门数据看板、异常洞察、告警配置、图表报告 |
| `admin`（管理员） | 3 | 用户管理、系统配置、检索调试、评测、审计、运维 |

密级模型：`staff=1 / manager=2 / admin=3`，与文档密级 `1-3`（public/internal/confidential）比较，叠加部门匹配。

### 1.3 核心场景

1. **知识问答**：员工上传制度/流程文档后自然语言提问，系统走 RAG 混合检索 + 流式回答，答案带证据溯源。
2. **经营数据分析**：管理者上传 Excel/CSV，系统完成画像、统计、排名、分组分析，生成图表。
3. **图表与报告**：柱/折线/饼/雷达/甘特/思维导图六类图表与 PDF/Excel 报告导出，副作用动作必须经人工确认（HITL），待确认任务可在审批面板集中处理。
4. **异常监控**：阈值/环比规则持续巡检，异常写告警并通知，总览页四数字 + 洞察页呈现。
5. **审批辅助**：费用/业务申请预审（金额 vs 标准，全 Decimal，缺失标准不臆造）；报销自查作为独立工作区。

### 1.4 功能地图

```
企业智脑
├── 登录与用户管理（JWT / SSO / 首管理员播种 / 个人画像）
├── 文档知识库（上传→安全校验→解析→切块→向量化→版本化索引发布；目录/预览/下载/删除）
├── RAG 检索问答（查询改写→多路召回→RRF→重排→权限前置过滤→SSE 流式回答+证据）
├── 多 Agent 编排（Supervisor + Doc/Data/Chart/Export/Approval 五类 Worker，LangGraph，
│   取消按"代"生效，HITL 挂起落账本）
├── 数据分析（数据集上传/画像/预览；pandas 结构化查询 DSL）
├── 图表与报告（Artifact 鉴权访问体系 + 产物列表面板，无公开 /static）
├── 经营智能（总览聚合 /dashboard/summary ｜ 主动洞察 ｜ 告警与定时任务 ｜ 语义指标层
│   ｜ 知识图谱候选账本与口径晋升 ｜ 审批助手）
├── HITL 审批（图表/导出中断确认，/hitl/pending 账本 + /approve 恢复）
├── 开放平台（/api/v1/open/*，API Key HMAC 签名）+ MCP Server（stdio 本地）
├── 可观测性与质量（执行账本 Trace / 检索调试台 / 评测平台 / 配置治理 / 性能统计）
└── 运维（迁移门禁 0001–0009 / 备份恢复 / 健康检查 / 容器端到端验收）
```

---

## 2. 总体架构

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  前端  Vue 3 + Vite（Nginx 托管 SPA，仅代理 /api/）             │
│    工作区面板 × 统一 UI 原语 × lib 数据模块 × 错误码字典          │
├─────────────────────────────────────────────────────────────┤
│  API 层  FastAPI /api/v1（10 组路由器）                         │
│    AuthMiddleware（全站鉴权→Principal）                         │
├─────────────────────────────────────────────────────────────┤
│  授权层  Principal → policy(default-deny) → 审计 三段式         │
│    单一 scoping 来源：文档可见性只在 rag/filters.py 判定一次      │
├─────────────────────────────────────────────────────────────┤
│  编排层  LangGraph 多 Agent 图                                 │
│    classify_intent → plan → supervisor → Send 并行 Worker       │
│    → reflect(critic) → synthesize；interrupt_before=[chart,export]│
│    取消按 (session_id, epoch) 一代一标记，HITL 挂起写待审批账本    │
├─────────────────────────────────────────────────────────────┤
│  能力层  RAG 管线 ｜ 数据分析 DSL ｜ 图表/导出 ｜ 洞察 ｜ 图谱 ｜ 审批助手 │
├─────────────────────────────────────────────────────────────┤
│  模型层  本机 Ollama（fast/standard/complex/embedding/rerank 分层）│
│    模型预算 + 并发闸 + Resilient/Offline 双层降级               │
├─────────────────────────────────────────────────────────────┤
│  基础设施  PostgreSQL(+PGVector) ｜ Redis(可靠队列/缓存) ｜ 本地文件  │
│    迁移门禁 ｜ 审计持久化 ｜ 备份恢复 ｜ 执行账本 ｜ 待审批账本     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 部署拓扑（私有化单机）

Docker Compose 七服务，一条命令 `docker compose --env-file deploy/.env.server up -d`：

| 服务 | 镜像/职责 | 关键约束 |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 业务数据 + 向量统一存储；健康检查门 |
| `redis` | `redis:7-alpine` | 密码 + AOF；可靠队列与缓存 |
| `ollama` | 本地模型运行时 | volume 持久化模型权重 |
| `migrate` | 一次性任务 `scripts/migrate.py` | 成功后其余服务才启动（迁移门禁） |
| `backend` | uvicorn :8001 | 仅绑 127.0.0.1；`SCHEDULER_ENABLED=false` |
| `worker` | `deploy/queue_worker.py` | 从 Redis 可靠队列取任务跑 Multi-Agent |
| `scheduler` | `deploy/scheduler.py` | 独占告警巡检/日报等定时副作用（单实例） |
| `frontend` | node:20 构建 → `nginx:1.27-alpine` | 80 端口对内网开放；`client_max_body_size 30m` |

边界约束：
- **无公开 `/static`**：图表/报告一律走鉴权的 `/api/v1/artifacts/{id}/content|download`。
- Nginx 仅代理 `/api/`，动态 resolver 防后端迁移后 502，SSE 长连接透传。
- 后端镜像 `python:3.11-slim` + `uv sync --frozen --no-dev`，非 root（uid 10001）运行，装 `fonts-wqy-microhei` 保证图表/PDF 中文渲染；上传文件只进 volume 不进镜像。

### 2.3 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11+（uv 管理）、FastAPI、Pydantic v2、LangChain + LangGraph（含 Postgres checkpointer） |
| 向量 | **PostgreSQL + PGVector（目标态统一存储）**；Chroma 仅为迁移期过渡（见 §5.2） |
| 数据 | pandas、matplotlib、openpyxl/xlsxwriter、fpdf2 |
| 检索 | jieba + rank-bm25、sentence-transformers（Cross-Encoder 重排）、Ollama embedding |
| 前端 | Vue 3.5 + Vite 8 + vue-router 4（无 TS、无 Pinia/Element Plus）、markdown-it + DOMPurify |
| 部署 | Docker Compose、Nginx、APScheduler |
| 观测 | 自建执行账本（Postgres）、LangSmith 可选、性能统计中间件 |

---

## 3. 核心设计原则

1. **数据不出客户服务器**：第一版只管理本机 Ollama；远程模型回退必须显式开启，默认关闭。
2. **默认拒绝（default-deny）**：所有资源访问经 `Principal → policy → 审计` 三段式；工具层 fail-closed（拿不到 Principal 即抛 `authorization_required`，不猜身份）。
3. **单一身份主体**：`Principal` 是跨 API/Agent/审计边界的唯一身份模型，任何模块不得发明第二套身份。
4. **单一 scoping 来源**：对"谁能看见什么"不允许存在两种答案——文档可见性只在 `app/rag/filters.py` 判定一次，禁止第二套判定复活（§4.5）。
5. **副作用必须 HITL**：图表、导出等产生交付物的动作，执行前强制中断等待人工确认；挂起状态落账本，面板读的是真话。
6. **可溯源**：每个 worker 运行挂证据袋（Evidence Bag），答案必须能回答"依据哪份文档/哪个数据集/哪个指标/哪次工具调用"；图谱断言晋升为指标定义必须带核对证据。
7. **诚实降级**：模型不可用、检索不可用、存储不可用都要显式报错（503 `storage_unavailable`），不假装修复；"面板空了"不能看起来像"没有待办"；进度必须真实。
8. **契约先行**：`app/agents/contracts.py` + `docs/api/contract-v1.md` 冻结公共契约；错误码枚举、SSE 事件、授权判断均为版本化契约，前后端各自有词汇表守卫测试。
9. **过渡方案显式标注**：Chroma、内存审计等过渡实现必须在文档与代码中标注，不得写成最终架构。
10. **迁移门禁**：数据库变更只经 `migrations/NNNN_name.sql` + manifest SHA-256 校验 + advisory lock 执行，禁止运行时漂移建表。

---

## 4. 身份与权限体系

### 4.1 Principal（身份主体）

```python
# app/agents/contracts.py（冻结契约）
class Principal(BaseModel):
    user_id: str
    username: str
    roles: list[str]              # ["staff"|"manager"|"admin"]
    permissions: list[str]        # 由角色映射展开
    department: str
    department_ids: list[str]
    clearance: int                # 1/2/3
    clearance_label: str
    status: str                   # 非 active 一律 403
    auth_source: str              # "local" | "sso"
    is_system: bool
    request_id: str
```

- 来源：`AuthMiddleware` 解析 Bearer JWT → 构造 Principal → 写入 `request.state`；SSO 走头部身份提取/角色归一（`app/common/sso.py`）。
- Agent 上下文：`AgentContext{principal, request_id, trace_id, ...}`，工具从 LangGraph config 取 Principal，缺失即 fail-closed。

### 4.2 权限动作与角色映射

`app/common/permissions.py` 定义动作常量与角色→权限映射，关键动作：

`resource:view / resource:upload / resource:download / resource:delete / resource:analyze / resource:export / resource:approve / users:manage / retrieval:debug / evaluations:manage / config:publish / audit:read / observability:read ...`

### 4.3 RBAC + ABAC 混合判定

规范来源：`docs/superpowers/specs/`（RBAC+ABAC 混合权限设计，核心规范）。

```
请求 → ①认证（AuthMiddleware：JWT 有效？status=active？）
     → ②路由级授权（capability check：角色是否持有该动作权限）
     → ③资源级授权（app/common/policy.py，显式 default-deny）：
         ResourceScope{resource_type, owner_id, department_ids,
                       classification, visibility, version_id, status}
         判定顺序：owner 匹配 → 部门匹配 → 密级比较 → 可见性规则
     → ④AuthorizationDecision{allowed, reason_code, policy_version, matched_rules}
     → ⑤审计（每个业务资源请求逐条落审计，含拒绝原因）
```

- 检索层同判：`app/rag/filters.py` 将授权范围转成向量库 where 过滤 + BM25 候选前置过滤，保证"检索得到 = 有权看到"。
- **开放平台不豁免**：`/api/v1/open/*` 全部经 API Key HMAC 验签 → 映射为受限 Principal（最小权限、独立审计通道），不存在"整体绕过认证"的路径。

### 4.4 会话与资源归属

- 会话（sessions）落库带 `owner_id`，所有会话路由做 owner 校验；Agent 历史隔离按 Principal 过滤（`test_orchestrator_history_isolation.py`）。
- 文档、数据集、产物、告警规则、图谱关系、指标定义全部带归属（owner/department），删除级联校验归属（`test_resource_delete_cascade.py`）。
- 管理员身份回退路径被禁止：Agent 内部不得在没有 Principal 时回退为 admin。

### 4.5 单一 scoping 来源（C-4，已落地）

`app/common/rbac.py` 已收敛为两个纯职责：角色→密级映射（`ROLE_CLEARANCE/clearance_for/allowed_levels`）和表格数据行级过滤 `filter_dataframe_rows`。

- **文档可见性的唯一判定**是 `app/rag/filters.py::resolve_document_retrieval_scope`：一次产出下推向量库的 `filters` 与本地复核的 `allows`，同源于一个 scope 对象；`search_for_principal` 只调它一次，因此对"谁能看见什么"不可能有两种答案。
- 已删除的第二套判定（旧 `doc_visible/build_where`）编码了与线上相反的口径（"空部门文档=公开"），属危险冗余；`tests/test_rbac_single_scoping_source.py` 作为守卫测试禁止其复活，并钉死三条事实：
  1. administrator 不受部门限制；
  2. 普通账号无部门 → 直接拒（`authorization_unavailable`）；
  3. 部门为空的文档对普通账号不可见（fail-closed）。
- **已知待决 R17**：表格行级过滤（`filter_dataframe_rows`）仍是旧口径（空部门行对同密级可见，与文档链相反）；修改它等于改变客户数据可见范围，留待业务确认后对齐。

---

## 5. 数据与存储设计

### 5.1 存储矩阵（目标态）

| 数据类别 | 存储 | 说明 |
|---|---|---|
| 用户/会话/文档目录/告警/长期记忆/审计/执行账本/**待审批账本**/指标定义 | PostgreSQL | 迁移 0001–0009 建立的核心与运行时表 |
| **向量（文档块 Embedding）** | **PostgreSQL + PGVector** | 与业务数据同库同事务；索引发布原子化 |
| 文档原始文件 / 数据集文件 / 图表与报告产物 | 本地文件存储（volume） | 不可变物理文件名；元数据在 PG |
| 任务队列 / 缓存 / 限流 | Redis（AOF） | 可靠队列原语；缓存键绑定权限范围 |
| 检查点（LangGraph checkpointer） | PostgresSaver（连接池） | HITL 中断恢复的持久化基础 |
| 知识图谱候选账本 | 本地存储文件（`KNOWLEDGE_GRAPH_STORE_PATH`） | 生产进程未配置即拒绝写入 |

### 5.2 向量库：Chroma → PGVector（目标态设计）

- **现状**：Chroma 是当前唯一运行时向量读写方，为**过渡方案**；PGVector 仅有 schema 骨架（迁移 0001）。
- **目标态设计**（本设计文档纳入并按计划交付）：
  1. 统一存储：文档向量随业务数据同库，事务内保证"元数据可见 ⇔ 向量可检索"，消除双写窗口。
  2. 迁移绑定 Embedding 模型版本：`embedding_model + dimension` 作为索引元数据，禁止混维度共存；模型升级 = 新索引版本 + 全量重建 + 原子切换，不做在线混拼。**已知缺口 R22（已立项）**：当前尚无"切换 embedding 模型时自动触发索引重建"的路径，切换前必须手工全量重建。
  3. 权限过滤下推：PGVector `WHERE` 子句直接承载 `owner/department/classification` 过滤（替代 Chroma where），检索与授权同引擎。
  4. 原子发布与回滚：复用索引版本化发布机制（本地 JSON 元数据 + PG 事务镜像，`app/rag/indexing.py`），新版本可一键回滚到上一版本。
  5. Chroma 退役路径：双读验证（Chroma vs PGVector 召回对比进评测平台）→ 切读 PGVector → 停写 Chroma → 归档下线。评测报告作为切换门禁证据。

### 5.3 迁移体系

- 文件：`migrations/NNNN_name.sql` + `migrations/README.md`，manifest.json 登记 SHA-256；loader **fail-closed**（缺文件/改名/未登记/内容漂移即拒）；`scripts/migrate.py` 于部署期一次性执行，PG advisory lock 防并发，`schema_migrations` 事务记账。
- 现有迁移：
  - 0001 core_resource_versions（账本 + PGVector）
  - 0002 execution_data_lineage（执行账本五实体）
  - 0003 / 0004 legacy runtime（users/sessions/alerts 等 + 兼容层）
  - 0005 audit_events
  - 0006 document_ownership
  - 0007 document_chunk_count
  - **0008 pending_approvals**：HITL 待审批账本，状态机 CHECK 钉死（§8.2）
  - **0009 metric_definition_semantics**：指标语义字段从 JSONB 保留键提成真列 + 核对证据列 + 幂等回填（§10.3）
- 红线：业务代码禁止运行时 `CREATE TABLE IF NOT EXISTS` 式漂移建表；迁移只前进，回滚靠兼容镜像（如 0009 在 JSONB 中保留一版标签作回滚兜底）。

### 5.4 Redis 可靠队列（ReliableQueue）

`app/common/reliable_queue.py` 提供任务队列原语，替代 BLPOP：

- `reserve / ack` 两段式消费；**租约**（lease）过期自动回收，worker 崩溃任务可再投递；
- 重试计数与**死信队列**；幂等键去重；取消信号传播（配合按代取消，§7.5）。
- 请求路径：`POST /api/v1/ask` 入队 → worker 取任务跑 Agent 图 → SSE 按请求 ID 推流；状态查询走独立 API。
- 验收基线：迁移、执行账本落库、worker 恢复、备份恢复已在隔离环境（PG 5433 + 临时鉴权 Redis）全量验证（443 passed）。

---

## 6. 文档知识库与 RAG 检索管线

### 6.1 文档生命周期

```
上传 → 安全校验（大小/MIME/魔数/路径，app/documents/file_security.py）
     → 解析（PDF/DOCX/DOC/TXT/MD，app/rag/loader.py）
     → 切块（父子块：父块保上下文，子块保召回粒度）
     → Embedding（Ollama embedding，维度绑定模型版本）
     → 版本化索引发布（原子：新版本就绪才切换；可回滚）
     → 目录登记（app/documents/catalog.py：Postgres 元数据 + 版本 + chunk_count + owner）
```

- 上传安全：扩展名/MIME/魔数三重校验，大小上限，拒绝路径穿越与客户端可控文件名；文档归属 owner + department + classification。
- 文档预览（`app/documents/preview.py`）与下载均走鉴权路由并审计。
- 删除：目录状态置删 + 向量索引版本重发布 + 级联清理。

### 6.2 检索管线（Agentic RAG）

`app/rag/retrieval_pipeline.py`：

```
用户问题 → 查询改写（指代消解、术语归一）
        → 子问题拆分（复杂问题多路）
        → 并行召回：语义向量（PGVector）＋ BM25（jieba 分词）＋ 子问题扩展
        → RRF 融合（vector / bm25 / rrf 分数独立记录）
        → Cross-Encoder 重排（sentence-transformers，rerank 分数独立记录）
        → 权限前置过滤（resolve_document_retrieval_scope，先过滤后拼 Prompt）
        → 上下文组装 → 模型生成 → 答案附证据引用（文档名/位置/得分）
```

- 分数治理：每阶段独立分数类型（`vector/bm25/rrf/rerank`）随 RetrievalTrace 落账本，杜绝"分数覆盖失真"。
- 查询分级：**快速 / 标准 / 深度**三档——简单问题短路直答，复杂问题走完整管线；分级结果写入 Trace 以便评测口径分组。
- 并发与降级：检索管线并发受控（`test_retrieval_pipeline_concurrency.py`）；Embedding/重排模型不可用时显式降级并标注 `retrieval_unavailable`，不静默空结果。

### 6.3 检索调试台（目标态）

`app/rag/debug.py`（已有授权版有界报告）之上，设计完整调试台：

- **入口**：`GET /api/v1/observability/retrieval/debug`（仅 `retrieval:debug` 权限，admin）。
- **能力**：
  - 多套检索策略并排对比（同一问题 × N 策略 × 各阶段耗时/候选数/过滤原因/排序变化）；
  - 每个候选的分数字段全部展开（vector/bm25/rrf/rerank），标注"被哪条规则过滤"；
  - 父子块展开视图（命中子块 → 所属父块上下文预览）；
  - 权限过滤试算：以指定 Principal 身份试算可见集合，验证"检索得到=有权看到"；
  - 报告有界（候选上限、时长上限），防止调试台本身成为性能风险。
- **落库**：每次调试会话写入 Trace（`kind=retrieval_debug`），可回放、可关联评测条目。

---

## 7. 多 Agent 编排引擎

### 7.1 图结构（LangGraph）

`app/agents/orchestrator.py`：

```
classify_intent
 ├─ chat（闲聊/简单问答）→ respond → END（短路，不进编排）
 └─ task → load_memory（短期压缩 + 长期记忆 + 用户画像注入）
         → plan（规则确定性 DAG，纯 Python，不额外调 LLM）
         → supervisor（唯一工具=dispatch(workers)）
              ├─ Send() 并行派发就绪层 worker
              │    doc      （工具: search_docs）
              │    data     （工具: analyze_data, query_data）
              │    chart    （工具: analyze_data, generate_chart）
              │    export   （工具: export_report）
              │    approval （工具: 报销预审 build_precheck）
              ├─ reflect（critic 规则审查 AgentResult；不通过且 retry<1 → 回 supervisor 重做；
              │          retry≤1、reflect≤1，防止无限循环）
              └─ synthesize（聚合 worker_results → final_answer）
```

- **依赖分层**：chart 依赖 doc/data，export 依赖 doc/data/chart；每轮只派发就绪层（`_UPSTREAM` 表），保证"图先于报告、数据先于图"。
- **Worker 实现**：四个业务 worker 为 `create_react_agent` 预构建子图，各自带 checkpointer；planner 计划与 LLM 决策互为保险，含关键词兜底与《文件名》引用剥离防误判。
- **意图路由边界**：`test_planner_routing_boundaries.py` + `test_routing_intent_and_terminal_state.py` 锁定路由行为；范围外问题显式"不接单"而非幻觉执行。

### 7.2 状态与契约

- `AgentState`（TypedDict）：消息 `add_messages` 追加；`agent_results/worker_results` 自定义 reducer 支持并行 worker 合并（可 reset）；plan、review_result、retry_count、reflect_count、final_answer 等。取消标记**不再**进入 State/Context（R18 已删除 `cancellation_token` 字段，见 §7.5）。
- `contracts.py` 冻结：`Principal / ResourceScope / AuthorizationDecision / ModelBudget / ErrorEnvelope / AgentContext / ArtifactRef / AgentResult`。
- **AgentResult** 由证据袋聚合生成：

```
Evidence Bag（每次 worker 运行一个，随 config 传递）
  ├─ record_document_hits(...)   # 命中的文档与位置
  ├─ record_dataset(...)         # 使用的数据集与版本
  ├─ record_metric(...)          # 引用的语义指标
  ├─ record_artifact(...)        # 产出的产物引用
  └─ record_tool_status(...)     # 每次工具调用的状态
→ build_agent_result() → AgentResult{evidence, artifacts, terminal_state, ...}
```

### 7.3 工具层与授权

`app/agents/tools.py` 5 个工具，全部执行统一三段式：

1. 从 config 取 Principal（缺失 → `authorization_required`，fail-closed）；
2. 创建产物前检查动作权限（`ACTION_ANALYZE / ACTION_EXPORT`）；
3. 工具执行结果写入证据袋 + Trace 的 ToolCall span。

### 7.4 记忆体系

- **短期**：supervisor 节点内 `compress_messages` 压缩历史，防止上下文爆炸；
- **长期**：跨会话事实与偏好落 PG（`app/memory/`），load_memory 注入；
- **画像**：用户部门/关注指标/常用数据集，驱动个性化检索与看板默认值；
- **隔离**：长期记忆与会话历史按 owner 隔离，管理员也不越权读取他人会话内容。

### 7.5 取消语义：按"代"（epoch）生效（R18，已落地）

**问题**：取消必须只命中"当前这一轮生成"，且不得抹掉先到的取消、不得跨代泄漏。

**设计**：新类型 `CancelGeneration(threading.Event)`——它**就是"这一代"本身**：

- 自带身份 `(session_id, epoch)`，epoch 取自进程内单调计数器，同会话两代永不复用标识；
- 原样穿过 `config["configurable"]` 进入编排，orchestrator 的 `_is_cancelled` 每个检查点读到的天然是本代标记——不可共享、不可复用，跨代泄漏在传参一步堵死；
- 生命周期：
  1. `register_request` 开一代并登记到 `_REQUESTS[(session_id, epoch)]`；**先到的取消在此一次性消费**（`_PENDING_CANCELLATIONS` 中的一次性标记直接置位本代）——修掉旧实现"无条件换新 Event 抹掉先到的取消"；
  2. `cancel_request` 只置位当前在飞的最新一代；无在飞运行则留下"待下一代消费"的一次性标记并返回 False（不假装成功）；
  3. `release_request` 在 `finally` 里只弹出自己那一代；注册与弹出留在 `generate()` 同一帧（`aclosing` 包流），正常收尾 / 异常 / 取消 / 客户端断连四个出口全部覆盖，`_REQUESTS` 只反映在飞运行。
- SSE 侧：`/ask` 每步按 `is_request_cancelled(thread_id, epoch=本代)` 比对，取消即发 `request.cancelled` 事件并收流；`/approve` 恢复路径同构。
- 守卫：`tests/test_cancellation_epoch.py`（468 行）+ `tests/test_request_cancellation.py`（521 行）。

---

## 8. HITL 人机协同

### 8.1 中断与恢复（LangGraph 原生）

1. **编译期声明**：图编译时 `interrupt_before=["chart", "export"]`——这两个副作用 worker 执行前整体中断。
2. **中断呈现**：`check_interrupt` 返回 pending 动作列表；`/ask` SSE 推送确认事件，前端弹确认框（图表预览/导出内容摘要）。
3. **恢复入口**：`POST /api/v1/approve` → `run_interrupt_stream(approved=True)` → `Command(resume={"approved": True})` 从 PostgresSaver 检查点恢复；**恢复时重新注入 Principal**，缺失即 fail-closed（防止恢复链路身份漂移）。
4. **拒绝路径**：拒绝时把"已取消"写入对应 worker 的 `worker_results` 再回到 supervisor，防止重复触发同一副作用。
5. **取消与 HITL 的交点**：停在 HITL 的会话若用户先按了"停止"，随后再批准——批准路径会拿到一个生来置位的取消标记，编排第一个检查点连 resume 都不发起，直接按取消收场（R18 语义）。

### 8.2 待审批账本（R12/R13，已落地，迁移 0008）

**设计动机**：LangGraph 的挂起态只活在 checkpoint 里，`check_interrupt` 必须先给 thread_id 才能问，没有枚举能力——审批面板此前"无真话可读"。因此引入显式账本：

**数据模型**（`app/storage/pending_approvals.py` + 0008）：
- `session_id`（刻意等同 graph thread_id）、`owner_user_id`、`parked_steps`（JSONB 数组，值域限 `_HITL_PARKED` 常量）、`request_id/trace_id/task_id`、`created_at/expires_at/decided_at`；
- **状态机**：`awaiting → resumed | refused | abandoned | stale`，0008 用 CHECK 钉死。`abandoned` 只在协作取消后写入；`stale` 吸收 MemorySaver 降级/重启后图对不上的情况；
- TTL 默认 24h（`PENDING_APPROVAL_TTL_HOURS`），过期行读侧报 stale 但**不删除**（保审计）；
- partial unique 索引保证一会话同时只有一条 `awaiting`，新挂起先把旧行改 stale。

**读写路径**：
- 写侧：`/ask` 挂起时写一行 `awaiting`（记账失败只留痕，不打断回答流）；`/approve` 闭合为 `resumed/refused`，取消则标 `abandoned` 并发 `request.cancelled`；
- 读侧：`GET /api/v1/hitl/pending` 分页（默认 50、硬上限 200，下推进 SQL），**逐行调 `check_interrupt` 复核**——账本不是权威，图才是；对不上就地判 stale，复核失败该行不列也不改判；归属沿用会话判定（别人的会话 404 而非 403）。

**存储语义（诚实降级）**：
- PG 就绪时用真表；**缺表抛 `PendingApprovalStoreMissing` → 503 `storage_unavailable`**，绝不悄悄降级内存——"面板报错"不能看起来像"没有待办"；
- 无 PG 的开发态才退进程内账本。

### 8.3 审批助手术语区分

Approval Worker 是"报销预审"业务能力（金额 vs 标准，全 Decimal），与 HITL 审批中断是两个概念，文档与 UI 术语严格分开：前者是「报销自查」工作区，后者是图表/导出前的确认动作。

---

## 9. 数据分析与产物体系

### 9.1 数据集（Dataset）

- 上传：Excel/CSV → 安全校验 → 存本地（不可变物理文件名）→ Postgres 登记元数据与 owner。
- 画像/预览：列类型推断、统计摘要、分页预览，全部经资源级授权（`test_dataset_route_authorization.py`）。
- **版本与血缘（目标态，纳入设计）**：
  - `DatasetVersion`：同一数据集多次上传形成版本链，分析任务绑定具体版本，保证结果可复现；
  - 源版本血缘：分析产物（图表/报告）记录"消费了哪个 DatasetVersion"，形成 产物→数据集→文档 的证据链；
  - 生命周期：过期标记 + 物理清理 Worker（定期回收无引用的旧版本文件），元数据保留血缘。

### 9.2 数据分析执行（结构化 DSL，取代 eval）

- **红线**：禁用 `safe_query()` 式 `eval`/`exec` 沙箱。
- **设计**：结构化查询 DSL——前端/Agent 产出受限操作树（`select/filter/groupby/agg/sort/limit/join` 预定义算子），后端白名单算子解释执行；未知算子一律拒绝；列名经 schema 校验；聚合结果全 Decimal/float 边界显式。
- 行级过滤：表格数据经 `filter_dataframe_rows`（rbac 收敛后保留的行级能力）；口径对齐待决 R17（§4.5）。
- 产出：分析结果（表格）+ 可选可视化，一并写入证据袋与 Trace。

### 9.3 产物（Artifact）体系

- 图表（柱/折线/饼/雷达/甘特/思维导图）与报告（PDF/Excel）统一注册为 Artifact；
- **访问**：`/api/v1/artifacts/{id}/content|download` 鉴权 + 审计；无公开 `/static` 路径；
- **前端产物列表面板（已落地）**：`frontend/src/components/ArtifactList.vue`（含 1000+ 行组件测试），提供产物浏览、鉴权取流与删除入口；
- **持久化（目标态，纳入设计）**：JSON 过渡注册表 → PostgreSQL 落库，含 TTL 过期与物理清理 Worker；产物文件不可变，删除走归属校验 + 级联；
- 图表质量：标签防重叠、企业配色、无头后端（Agg）、中文字体（镜像内置 wqy-microhei）。

### 9.4 报告导出

- Export Worker 依赖 doc/data/chart 三层就绪后才派发（依赖分层）；
- PDF 报告含证据附录（引用文档清单 + 数据集版本 + 指标口径）；导出内容 HITL 确认后执行，Excel 导出防公式注入（单元格前缀转义）。

---

## 10. 经营智能子系统

### 10.1 总览聚合 `/dashboard/summary`（R14-A1，已落地）

`app/api/v1/dashboard.py`（独立只读路由器）一次往返返回总览页四个数字，**只按登录者可见范围计算**：

| 数字 | 来源 | 关键约束 |
|---|---|---|
| `documents` | `chat.list_document_catalog`（`_visible_document_rows → authorization_decision` 同一条权限链） | 复用列表端点的判定，**不建第二套权限** |
| `datasets` | `data.list_data_files` | 同上 |
| `pending_approvals` | 待审批账本 `open_items(owner_user_id=caller)`，与 `GET /hitl/pending` 同一读法 | 不逐行向图复核（列表页才复核） |
| `alerts`（total/unread） | 告警存储**全集**直查（非 `GET /alerts` 的最新 100 条页） | 先过 `alerts._require_alert_management`；**403 时整个键省略**——返回 0 会被渲染成"健康租户"，也是绕过 R1 的后门 |

- 鉴权走 `intelligence._authorized(request, ACTION_ANALYZE)`；响应带 `NO_STORE`（逐主体答案不可缓存）；
- 账本缺表 → **整个响应 503 `storage_unavailable`**：部分数字的 200 等于谎报健康；
- 消费者：前端 DashboardPanel 四个数字（W6 接线，消灭零消费者端点）。
- 注意：`app/dashboard/service.py::build_dashboard`（客户端送行聚合，`/intelligence/dashboard`）仍独立存在，与新端点不共用聚合逻辑。

### 10.2 主动洞察与告警

- 规则引擎 `app/insights/rules.py`：阈值、环比增长（>20% 可配）两类判定，规则式、可解释；
- 告警（`app/api/v1/alerts.py`）：规则 CRUD + 手动检查 + 定时巡检（scheduler 独占单实例）；异常写告警 + AI 归因；通知渠道经 `app/common/notifications.py`；
- 数据源口径：巡检读取的数据集/指标经权限过滤（`test_alert_scan_scope.py`），员工视角 403 语义由后端保证（前端 W7 已按"四张脸"区分呈现，§15.3）。

### 10.3 语义指标层（0009 落地后的生命周期）

- `app/semantics/registry.py`：指标名称/公式/单位/周期/匹配词的注册与匹配，统一"营收/毛利率"等口径，分析、看板、洞察、告警共用同一 MetricContext；
- **定义生命周期**：`(owner_id, metric_id, definition_version)` 唯一键下的注册/修订；`origin` 枚举 `code_registry | operator` 区分代码种子与人工/晋升写入；
- **核对语义（诚实）**：`verified_against_documents` 只在「状态词 + 证据齐全」时为 True（模块自己复核证据，不信状态词本身）；`verified_at` 强制 ISO-8601，不可解析即报错，不许留下缺证据的 verified 行；
- **存储（0009）**：`metric_name/definition_text/time_granularity/origin/match_terms` 从 filters JSONB 保留键提成真列，加 `verification_state` + 四个证据列 + `source_relation_id`；CHECK 强制 verified 必须有具名证据（单向：unverified 可留旧证据）；幂等回填只补空值，**证据列永不从 JSONB 回填**（防止行给自己开证明）；JSONB 保留键继续写一版作回滚兼容镜像，仅读兜底、verification 一律不读 JSONB；
- 读侧降读：「声称 verified 但证据不全」的行如实降读为 unverified 并告警；`metric_catalog` 输出两态计数；
- 指标注册与修订走配置治理（§12.4）版本化，口径变更可回滚。

### 10.4 知识图谱：候选断言账本与口径晋升（R15，已落地）

**定位（选乙）**：图谱只是**候选断言账本**——不做图推理，Agent 回答时不读它；它唯一有产出的出口是**晋升**（把核对过的关系沉淀为正式指标定义）。

- **双状态机**（`app/knowledge_graph/service.py`）：
  - 关系记录生命周期：`candidate → confirmed → promoted | rejected`；
  - `verification_state`（人工核对维度）：`unverified | verified | rejected`——与生命周期**分离**：作者 confirm 只说明格式良好，永不冒充"已与制度文件核对"；
- **验证门槛**（`record_verification/reviewable`）：`resource:approve` 权限 + 作用域可读 + **作者不得自核** + 证据必须含文档与段落 locator；生产进程未配置 `KNOWLEDGE_GRAPH_STORE_PATH` 时所有写直接拒绝；
- **晋升流程**（`app/knowledge_graph/promotion.py`）：
  1. `reviewable()` 先答三个问题：存在？可读？可批？
  2. 经 `registry.register_metric_definition` 落成正式定义行（默认进 `system` namespace，携带核对证据四元组 + `source_relation_id` 回指图谱关系）；
  3. **账本在目录行确实写成功之后才闭合**——没落行就保持 verified-but-unpromoted，不许夸大出处；
  4. 同一关系按新 `definition_version` 重晋升即修订；拒绝（rejected）只属于候选关系，不进指标目录；
- 前端 GraphPanel 只消费真实 relations API，无演示假数据。

### 10.5 审批助手

- `app/approval/assistant.py`：费用/业务申请预审；金额全 Decimal；公司标准缺失时显式"无标准可依"，不臆造结论；
- 前端「报销自查」工作区（W7 后定位收口）；经 MCP/Open 平台同样可用，身份与过滤同源。

---

## 11. 模型接入与路由

### 11.1 本机 Ollama 为唯一默认模型源

- 私有化默认关闭远程模型回退；远程回退必须显式配置开启，且开启事实在 UI 与日志中显式呈现（不静默外发数据）。

### 11.2 模型自动发现与能力验证（目标态，纳入设计）

- **发现**：启动/定时任务调用 Ollama `/api/tags` 枚举本机模型，写入本地模型注册表；
- **能力验证**：对每个候选模型跑标准探针（短生成、embedding 维度校验、rerank 打分冒烟），登记能力矩阵 `app/common/model_capabilities.py`；
- **按用途绑定**：`fast / standard / complex / embedding / rerank` 五类用途分别绑定模型；配置写 `MODEL_*` 环境变量或注册表，禁止代码写死模型名；
- **并发与预算**：`model_budget.py` 整机预算（max_calls/tokens/timeout/max_concurrency）+ 排队等待，防止 14B 级模型并发踩踏（`test_model_concurrency.py`）；
- **已知缺口 R22**：切换 embedding 模型无自动索引重建路径（§5.2）；**R23/R24（已立项）**：模型真跑通全过程的延迟根因量化与后续优化。

### 11.3 降级策略（诚实降级）

```
ResilientModel：provider 失败 → 本地备选 → 仍失败 → 显式 model_unavailable
OfflineModel：  离线关键词路由兜底（确定性选 worker / 直答骨架），
                回答显式标注"离线降级，未经完整检索"，不假装修复
```

- 模型调用每次写 ModelCall span（时长/tokens/结果状态）入执行账本。

---

## 12. 可观测性与质量平台

### 12.1 执行账本（Agent Trace）

**五类实体**（迁移 0002 execution_data_lineage）：

| 实体 | 内容 |
|---|---|
| `AgentRun` | 一次完整编排运行：request_id / trace_id / task_id / Principal / 终态 |
| `AgentStep` | 图节点级步骤：classify/plan/supervisor/worker/reflect/synthesize |
| `ToolCall` | 工具调用：名称、入参摘要、状态、耗时 |
| `ModelCall` | 模型调用：用途层、模型名、tokens、状态 |
| `RetrievalTrace` | 检索：策略、各阶段分数、命中、过滤原因 |

- 适配链：JSONL 过渡适配器 → **PostgresPersistenceAdapter 真实落库**（已落地）；
- `/ask` 生成稳定 `request_id / trace_id / task_id` 并按规范 SSE 事件发射；取消事件 `request.cancelled` 同链路（R18）；
- 敏感字段脱敏（`app/common/tracing.py`）。

### 12.2 Trace 读取与回放 API（目标态，纳入设计）

- `GET /api/v1/observability/traces/{trace_id}`：按实体树返回完整 Trace；
- **资源级授权**：trace 归属运行发起者；`observability:read` 权限者可读全量，owner 仅可读自己的 Trace；逐条审计；
- **回放**：步骤时间线可视化（含每步输入摘要/输出摘要/分数），支持从 Trace 跳转到证据原文（文档预览/数据集版本）；
- 回放数据与评测平台互通：任一评测条目失败可一键打开对应 Trace。

### 12.3 评测平台（目标态，纳入设计）

- **评估集**：30–50 条业务评估集（已建 30 条），覆盖 10 类场景：文档问答、多轮追问、Excel 计算、口径冲突、权限越权、范围外拒答、图表正确性、导出完整性、降级诚实性、取消语义；
- **指标**：
  - 任务级：回答正确率、证据覆盖率（答案引用/应引用）、工具选择准确率；
  - 检索级：召回率、排序质量、忠实度、相关性（独立分数，不互相覆盖）；
  - 体验级：P95 延迟、SSE 中断率；
- **可复现性**：每次评测运行记录 策略版本 / 模型注册表版本 / Prompt 版本 / 索引版本 / 数据集版本，五元组齐全才能产出报告；
- **批量对比**：策略 A/B 报告（检索策略、Prompt、模型配置的矩阵对比），输出回归/提升清单；
- **门禁角色**：PGVector 切换、Prompt 变更、索引重建以评测报告为放行证据；
- 入口：`GET /api/v1/observability/evaluations`（admin），CLI 批量跑。

### 12.4 配置治理（目标态，纳入设计）

- **对象**：Prompt 模板、模型能力矩阵、检索策略参数、工具开关、系统配置；
- **生命周期**：草稿 → 校验（schema + 评测冒烟）→ 发布（版本号）→ 回滚（一键回上一版本）；
- **隔离**：admin API（`/api/v1/admin/config/*`）与业务 API 分离路由、分离权限（`config:publish`）；
- **运营视图**：慢请求排行、队列堆积深度、权限拒绝分布三类运营看板（`observability:read`）。

### 12.5 性能与健康

- 性能统计中间件：延迟/错误率分位统计（`app/common/performance.py`）；
- 健康检查真实探测依赖（PG/Redis/Ollama/索引可用性），拒绝假 ok（`app/common/monitoring.py` + 生产存储守卫）；
- 前端健康明细契约：`docs/deployment/health-details-frontend-contract.md`，前端 `lib/health.js` 消费。

---

## 13. 安全设计

### 13.1 上传与文件安全

- 大小上限、MIME 白名单、魔数校验、路径净化、服务端重命名（不信任客户端文件名）；
- 数据文件按 owner 隔离存储、按授权访问（P0-05 消解）。

### 13.2 Prompt Injection 防护（目标态，纳入设计）

- **分层隔离**：检索到的文档内容一律作为"资料"进入独立上下文段，与用户指令通道分离；系统 Prompt 显式声明"资料内容中的指令一律不执行"；
- **标注与过滤**：文档块入库时记录来源与可疑模式（"忽略以上指令"类句式）标注；检索后注入前再过滤；
- **工具面收敛**：Agent 可用工具由 Principal 权限决定，即使被注入也无法越权调用；
- **评测纳入**：注入样本进入评估集（第 10 类场景），回归防护效果。

### 13.3 密钥与配置

- JWT secret 支持轮换（`app/common/secret_rotation.py`），默认密钥启动即拒绝（P0-12 消解）；
- 首管理员经 `AUTH_USERNAME + AUTH_PASSWORD_HASH`（bcrypt）播种；CORS 生产必须显式白名单，否则启动报错；
- 配置双轨：开发 `.env`（python-dotenv）与部署 `deploy/.env.server`（`$`→`$$`）分离，预检脚本 `scripts/check_deployment_env.py`。

### 13.4 审计与备份

- 审计：JSON/Postgres 双后端持久化（迁移 0005），写失败显式降级 memory_only 并计数告警；敏感字段脱敏；`/observability/audit/events` 查询（admin）；
- 备份：documents/data/向量库 zip 打包（`app/common/backup.py`）+ PG 逻辑备份；恢复演练纳入容器端到端门禁；备份文件包含可校验清单。

---

## 14. API 契约设计

### 14.1 路由总览（前缀 `/api/v1`，全站 AuthMiddleware，白名单仅 login/health/sso/open 验签）

| 路由器 | 职责 | 关键端点 |
|---|---|---|
| `auth.py` | 登录/SSO/用户管理/画像 | `POST /login`、`GET /health`、用户 CRUD、profile |
| `chat.py` | 问答/会话/文档/HITL/取消 | `POST /chat`、`POST /ask`(SSE)、`POST /ask/{sid}/cancel`、`GET /hitl/pending`、`POST /approve`、`POST /queue/{request_id}/cancel`、`/sessions`、`/documents*` |
| `data.py` | 数据分析与产物 | `/data-files`、`/upload-excel`、`/chart`、`/export` |
| `artifacts.py` | 产物鉴权访问 | `/{id}/content`、`/{id}/download`、列表/删除 |
| `dashboard.py` | 总览聚合（R14-A1，只读） | `GET /summary` |
| `intelligence.py` | 经营智能 | `/dashboard`、`/insights/detect`、`/alerts*`、`/semantics/match`、图谱 relations、provenance 摘要 |
| `alerts.py` | 告警规则与巡检 | 规则 CRUD、`/alerts/check`、日报 |
| `open_platform.py` | 开放平台 + 应用注册 | `/open/` 六个端点（query、analyze、insights、approval/preview、dashboard、provenance-summary）、apps CRUD |
| `observability.py` | 只读运维面 | `/retrieval/debug`、`/traces/{id}`、`/evaluations`、`/audit/events` |
| `admin/*`（目标态） | 配置治理 | config 草稿/发布/回滚 |

### 14.2 统一错误信封（冻结枚举，18 码）

```python
class ErrorEnvelope(BaseModel):
    code: Literal[
        "authentication_required", "permission_denied", "authorization_unavailable",
        "account_unavailable", "resource_not_found", "validation_error", "conflict",
        "rate_limited", "queue_unavailable", "model_unavailable", "retrieval_unavailable",
        "task_timeout", "task_cancelled", "unsupported_file", "parse_failed",
        "index_publish_failed", "storage_unavailable", "internal_error",
    ]
    message: str
    retryable: bool = False
    details: dict = {}
```

- `storage_unavailable`（v2.0 新增入约）：存储账本缺表等"不可悄悄降级"的场景统一 503；
- 前端 `lib/errcodes.js` 维护同源错误码字典（含人类可读文案），后端 `tests/test_error_code_vocabulary.py` 与前端 `errcodes.test.js` 双向守卫词汇表一致性。

### 14.3 SSE 事件契约（`/ask` 与 `/approve`）

- 事件序列：`queued → progress(step) → sources(证据) → token(增量) → confirmation_required(HITL) → done | error`；
- 取消：`request.cancelled` 事件（带 request_id/trace_id/task_id），按代取消语义（§7.5）；
- 每事件携带 `request_id` + 单调 `sequence`，前端按 sequence 重组与断线提示；不做静默重放假流。

### 14.4 开放平台鉴权

- API Key + HMAC 请求签名（`app/common/open_platform.py`），时间窗防重放；应用注册/吊销走 apps_router；
- 开放身份映射为**受限 Principal**（最小权限集合），与本地用户同一授权/审计管线（P0-13 消解）。

### 14.5 MCP Server

- `app/mcp_server.py`：stdio 本地传输（可选 token），暴露检索/分析/洞察/看板/溯源 5 类能力；
- 复用同一 Principal 过滤与审计；不提供绕过权限的"裸工具"。

---

## 15. 前端设计

### 15.1 技术栈与分层

- Vue 3.5 + Vite 8 + JavaScript（无 TS）、vue-router 4（已装未启用）、axios、markdown-it + DOMPurify、lucide 图标、自托管字体（Manrope / JetBrains Mono）；测试 vitest + Playwright；样式 stylelint。
- **无 Pinia/Element Plus**：状态就地组件管理 + `lib/` 数据模块 + `components/ui/` 原语，保持轻量。

### 15.2 工作区结构（目标态）

```
App.vue
├── 登录分支（四层背景视觉，V2 重建）
└── 侧栏 + 工作区（V3 目标态：vue-router 路由化，URL 可分享/刷新保持）
     ├── 总览    DashboardPanel   —— 四数字读 /dashboard/summary（W6 已接线）
     ├── 知识库  DocPanel          —— 上传/目录/预览（"喂料"视图：真实解析-索引进度）
     ├── 问答    ChatPanel         —— SSE + HITL 确认 + sources 证据卡 + 模型状态
     ├── 数据    DataPanel         —— 数据集上传/画像/版本
     ├── 成果    ChartViewer + ArtifactList —— 产物列表/鉴权取流/删除（已落地）
     ├── 待办    InsightPanel「异常与告警」—— /alerts* 真链路（W7 已接线）
     ├── 自查    ApprovalPanel「报销自查」—— 审批助手定位收口（W7）
     └── 系统    管理视图（用户/配置/评测，目标态）
```

### 15.3 关键设计点

- **UI 原语层**（V5，全部带 vitest 用例）：UiButton/Field/Select/Table/Dialog/Toast/Tabs/Upload/EmptyState/ErrorState/**LoadingState**（v2.0 新增）+ focus-trap/table-sort/toasts/upload-rules 逻辑模块；新面板禁止绕过原语自绘。
- **lib 数据模块**：`http.js`（唯一 axios 实例 + 401 处理 + 会话过期监控）、`api.js`、`sessions.js`、`artifacts.js`、`alerts.js`（v2.0 新增，告警四态模型）、`dashboard.js`（v2.0 新增）、`health.js`（v2.0 新增）、`errcodes.js`（错误码字典 + 文案）。
- **告警"四张脸"**（W7）：无权限 / 无告警 / 有告警 / 加载失败四态分开呈现——403 显示"无权限查看"而不是伪装成"暂无告警"（与后端"403 时省略 alerts 键"的契约对齐，§10.1）。
- **真实进度**：上传/解析/索引进度由后端事件驱动（解析、切块、Embedding、发布各阶段百分比），禁止前端自增假进度。
- **面板状态原语**（B-4）：loading/error/empty 三态统一由原语承载（`panel-states.test.js` 守卫）。
- **token 纪律**（B-2/V4）：设计 token 集中管理 + ratchet 只减不增（当前 334 处，v2.0 从 337 继续下降）；`no-bare-code.test.js` 静态守卫裸色值/裸错误码；theme.css 目标 ≤40KB。
- **不做假数据**：`v7-fake-data.test.js` 守卫演示数据只存在于显式标注的 devFixtures；后端能力未上线的前端项明确"等待"而非用演示数据占位。

### 15.4 前端计划收口

| 计划项 | 内容 | 状态 |
|---|---|---|
| W6/F5a | Dashboard 四数字接 `/dashboard/summary` | **已落地** |
| W7/F5 | InsightPanel 接 `/alerts*` 真链路（四态分开） | **已落地** |
| W7/F4(部分) | 审批页定位「报销自查」 | **已落地** |
| 产物列表 | ArtifactList 组件 + 组件测试 | **已落地** |
| V3 | shallowRef 切页 → vue-router 路由化 | 目标态 |
| F2 | ChatPanel 切换新 SSE 契约（request_id/sequence 全量事件） | 部分落地 |
| F4(其余) | 侧栏命名全部收敛、图谱入口撤下 | 目标态 |
| 趋势接口 B-7 | 总览趋势序列 | 目标态（后端契约项） |
| V4/V6 | theme.css 瘦身（当前 334 色值）+ Playwright 视觉基线补全 | 进行中 |

---

## 16. 部署与运维

### 16.1 部署流程（迁移门禁）

```
配置预检（scripts/check_deployment_env.py：JWT 密钥/CORS/PG/Redis/Ollama 必填校验）
→ docker compose --env-file deploy/.env.server build
→ migrate 服务一次性执行 scripts/migrate.py（advisory lock，0001–0009，失败即整体不启动）
→ backend / worker / scheduler / frontend 依健康检查顺序拉起
→ 首管理员播种（users 表为空时，AUTH_USERNAME + AUTH_PASSWORD_HASH）
```

### 16.2 容器端到端验收（目标态，纳入设计）

`scripts/verify_container_stack.py` 一键门禁，验收清单：

1. Docker daemon 等待就绪
2. env 预检
3. config/build/up 全绿
4. 容器内 migrate 成功
5. pgvector 与执行账本表校验
6. `nginx -t` 通过
7. 真实健康探测（非假 ok）
8. Scheduler 全局单实例
9. 模型来源诚实（Ollama 本机，无静默远程回退）

环境适配说明：本机 WSL2/Docker daemon 不可用时，走非 Docker 等效路径（uvicorn + worker + scheduler + 隔离 PG 5433 + 本地 Ollama）完成同清单验收；生产 5432 切换需操作者显式指定目标库。

### 16.3 升级与备份

- 升级：镜像 tag 固定 digest；升级前自动备份（PG 逻辑备份 + 文件 zip）；migrate 幂等重放安全；
- 备份：定时 + 手动；恢复演练纳入门禁；备份含清单校验；
- 升级中心（可选后置项）：`/api/v1/upgrade` 版本查询与升级向导，目标态预留契约。

---

## 17. 测试与验收体系

### 17.1 测试矩阵

| 层 | 手段 |
|---|---|
| 单元/集成 | pytest 220+ 文件：编排、权限、队列、检索、迁移、备份、告警、图谱、评测、取消、HITL 账本、总览聚合 |
| 契约 | `test_public_contracts.py`（ErrorEnvelope/Principal/AgentResult）+ `test_error_code_vocabulary.py`（错误码词汇表，与前端双向对齐） |
| 权限守卫 | `test_rbac_single_scoping_source.py`（禁止第二套 scoping 复活 + 三条口径钉死）、各资源 `*_route_authorization.py` |
| 取消语义 | `test_cancellation_epoch.py`（468 行，按代生效全矩阵）+ `test_request_cancellation.py`（521 行） |
| HITL 账本 | `test_hitl_pending.py`（660 行）+ `test_pending_approvals_migration.py`（状态机 CHECK/分区/TTL） |
| 语义与图谱 | `test_semantic_definition_migration.py`、`test_semantic_promotion.py`（493 行）、`test_knowledge_graph_verification.py` |
| 总览聚合 | `test_dashboard_summary.py`（531 行：权限复用/403 省略键/503 语义） |
| 前端 | vitest 组件与 lib 测试（artifact-list 1002 行、insight-alerts 971 行、dashboard-summary 369 行、panel-states 466 行、no-bare-code 538 行等）+ Playwright 场景脚本 |
| 生产安全门禁 | `test_deployment_guards.py`、`test_deployment_env_check.py`、`test_phase13_private_enterprise.py` |

### 17.2 门禁分级

- **默认线**：全量回归（不依赖 Docker）。
- **四门禁开启线**：容器运行门 + 真实依赖门（PG/Redis/Ollama）+ 浏览器 E2E 门 + 评测回归门（评估集指标不低于基线）。
- 评测门与 §12.3 五元组可复现要求绑定：策略/Prompt/索引变更必须附评测报告。

---

## 18. 附录：设计条目与落地基线对照

> 下表区分"已落地（有代码与测试佐证）"与"本设计纳入、按计划交付（目标态）"，避免把过渡实现误读为最终架构。完成度追踪以 `docs/current-functionality-2026-09-10.md` 为准。

| 设计条目 | 章节 | 落地基线 |
|---|---|---|
| Principal/契约冻结/ErrorEnvelope（18 码） | §4/§7/§14 | **已落地**（contracts.py + 双端词汇表守卫） |
| RBAC+ABAC、资源级授权、审计三段式 | §4 | **核心已落地**，全路由覆盖按计划收口 |
| 单一 scoping 来源（文档可见性唯一判定） | §4.5 | **已落地**（C-4 + 守卫测试；表格行级口径 R17 待决） |
| 可靠队列（租约/死信/幂等/取消） | §5.4 | **已落地**（隔离环境验收 443 passed） |
| 迁移门禁（manifest/advisory lock）0001–0009 | §5.3 | **已落地**（0008 待审批账本、0009 指标语义为 v2.0 新增） |
| 多 Agent 图/Send 并行/依赖分层/Reflect | §7 | **已落地** |
| 证据袋与 AgentResult | §7.2 | **已落地** |
| 取消按代（epoch）生效 | §7.5 | **已落地**（R18，双守卫测试） |
| HITL interrupt_before=[chart,export] | §8.1 | **已落地** |
| HITL 待审批账本（状态机/TTL/复核/503） | §8.2 | **已落地**（R12/R13 + 迁移 0008 + 660 行测试） |
| 总览服务端聚合 `/dashboard/summary` | §10.1 | **已落地**（R14-A1 + 前端 W6 接线） |
| 语义指标生命周期（真列/证据/降读） | §10.3 | **已落地**（迁移 0009） |
| 知识图谱候选账本 + 口径晋升链路 | §10.4 | **已落地**（R15-b + promotion.py） |
| 前端产物列表 ArtifactList | §9.3/§15 | **已落地**（含 1002 行组件测试） |
| 前端告警真链路（四态） | §15 | **已落地**（W7 + lib/alerts.js） |
| Chroma → PGVector 统一向量 | §5.2 | **目标态**（Chroma 为过渡，PGVector schema 已建；R22 索引重建路径立项中） |
| 结构化查询 DSL 取代 eval | §9.2 | **目标态**（P0-07） |
| Prompt Injection 分层防护 | §13.2 | **目标态**（P0-08） |
| Artifact/Dataset PostgreSQL 持久化 + DatasetVersion 血缘 + TTL 清理 | §9.1/§9.3 | **目标态**（现为 JSON 过渡注册表） |
| Trace 读取/回放 API（资源级授权） | §12.2 | **目标态**（Trace 已真实落库，读 API 待暴露） |
| 检索调试台完整版 | §6.3 | **部分落地**（有界调试报告已实现） |
| 评测平台（50 条集/批量对比/五元组可复现） | §12.3 | **部分落地**（30 条集与分类报告已建） |
| 配置治理（草稿→发布→回滚 + 运营视图） | §12.4 | **目标态** |
| Ollama 自动发现 + 能力矩阵 | §11.2 | **目标态**（显式配置 + 注册表发现已有基础；延迟量化 R23/R24 立项中） |
| 开放平台受限 Principal 全覆盖 | §14.4 | **目标态**（HMAC 验签已落地，白名单治理待收口） |
| 前端 V3 路由化 / F2 新 SSE 全量 / F4 其余收敛 / V4·V6 | §15 | **目标态**（W6/W7/ArtifactList/UiLoadingState 已落地） |
| 容器端到端验收门 | §16.2 | **目标态**（脚本已备，Docker daemon 环境阻塞） |
| 升级中心 | §16.3 | **可选后置** |

### 术语表

| 术语 | 含义 |
|---|---|
| Principal | 跨 API/Agent/审计的唯一身份主体 |
| HITL | Human-in-the-loop：副作用动作执行前的人工确认中断 |
| 待审批账本 | pending_approvals 表：一次挂起一行、带终态的事件记录（awaiting→resumed/refused/abandoned/stale） |
| 取消代（epoch） | CancelGeneration：(session_id, epoch) 唯一标识一轮生成，取消只命中本代 |
| Evidence Bag | worker 运行期间的证据收集袋，聚合成 AgentResult |
| ReliableQueue | Redis 两段式可靠队列（reserve/ack/租约/死信） |
| Artifact | 图表/报告等交付物的统一注册与鉴权访问单元 |
| DatasetVersion | 数据集版本链，分析结果可复现的锚点（目标态） |
| 口径晋升 | 图谱候选关系经核对后沉淀为正式指标定义的唯一产出路径 |
| 执行账本 | AgentRun/Step/ToolCall/ModelCall/RetrievalTrace 五类实体的持久化 Trace |
| 迁移门禁 | SQL 迁移 + SHA-256 manifest + advisory lock 的强制变更通道 |
| 单一 scoping 来源 | 文档可见性只在 rag/filters.py 判定一次的收敛原则（C-4） |

### v2.0 相对 v1.0 的主要变更

1. 新增落地章节：待审批账本（§8.2）、按代取消（§7.5）、`/dashboard/summary`（§10.1）、口径晋升（§10.4）、语义指标生命周期（§10.3）、单一 scoping 来源（§4.5）；
2. 错误码枚举 17→18（`storage_unavailable` 入约）；SSE 补 `request.cancelled` 与 `/approve` 同构；
3. 迁移清单 0001–0007 → 0001–0009；路由器 9→10 组（dashboard.py）；
4. 前端：新增 ArtifactList/UiLoadingState 与 lib/alerts、dashboard、health 模块；W6/W7 收口更新前端计划表；色值棘轮 337→334；
5. 立项登记：R17（表格行级口径）、R22（embedding 切换索引重建）、R23/R24（模型延迟量化）。

---

*本文档由多源梳理生成：`docs/current-functionality-2026-09-10.md`（现状唯一事实来源）、`task_plan.md`、`progress.md`、`docs/superpowers/plans|specs/`、`docs/frontend-plan-2026-09-14.md`、`docs/api/contract-v1.md`、`docs/handoff/`（2026-09-15/16 票据与 R 清单）、`docker-compose.yml`、`migrations/0001–0009`、`app/` 源码结构、git 基线 ec0f40b。若与现状文档冲突，以现状文档为准。*
