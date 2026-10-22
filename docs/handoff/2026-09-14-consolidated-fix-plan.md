# 整合修复计划（交 01a099da 派发子 Agent 执行）

生成时间：2026-09-14 10:55（Asia/Shanghai）
生成方式：对 `01a09db5` 架构图结论 + `01a099da` 派生 e2e 审计结论 + 本轮全量源码核对，三源去重合并
权威口径：本文件只列**已用当前工作区源码复核过**的缺陷，未复核的断言不写入

---

## 0. 执行前置（不可跳过）

1. **先提交快照**。当前 `git log -1` 仍是 `765aeca docs: add complete enterprise brain upgrade plan`，工作树几十处 M 未提交，含 `app/api/v1/chat.py`、`app/agents/*`、`app/common/auth.py`。任何切片开工前先落一个 checkpoint 提交。
2. **Wave 2/3 必须等主 thread 的 P0-1 收口提交完成**。S1、S4 要改 `app/api/v1/chat.py`，该文件此刻正被主 thread 写入。
3. **禁止修改 `frontend/`**。S6 的前端部分只产出接口约束文档。
4. **禁止**未经批准启动服务、连生产库、执行 `scripts/migrate.py` 实跑、跑 `verify_container_stack.py`。迁移验证一律用隔离库或离线断言。
5. 每个 Worker 都**不是独自在这棵代码树上工作**：不得回退或覆盖他人改动，冲突时停下来报告，不要强解。

---

## 1. 已核实的根因链（S1 的靶心）

```
record_document_version(filename, classification, department, storage_path, version)
  -> app/documents/catalog.py:128  签名里没有 principal / owner_id
documents / document_versions 两张表都只有 filename + classification + department
  -> migrations/0004_legacy_runtime_compatibility.sql:30
  -> migrations/0003_legacy_runtime_tables.sql:39
  -> app/documents/catalog.py 全文 0 次出现 owner
_document_authorization_decision 读 version.get("owner_id")  ->  恒为 None
  -> app/api/v1/chat.py:153
policy owner_match 只在 action == ACTION_VIEW 时生效
  -> app/common/policy.py:94
delete 走不到 owner -> 落到部门交集 -> admin 无部门则 principal_departments 为空集
  -> app/common/policy.py:107 department_scope_denied
结论：任何人都删不掉文档（owner 403 permission_denied / admin 403 department_scope_denied）
连带阻塞：删除级联、资源生命周期、TTL、备份清理全部无法端到端验证
```

## 2. 已被代码推翻的旧断言（派发时随任务下发，防止 Worker 回退修复）

| 旧说法 | 当前事实 | 证据 |
|---|---|---|
| queue_worker 用 BLPOP，无 ACK/租约/死信 | 已用 ReliableQueue | `deploy/queue_worker.py:26` |
| P0-1 会话归属未校验 | 已修，4 个入口都校验 | `app/api/v1/chat.py:666,1087,1210,1224` |
| P0-2 `/chat` 越权检索 | 已修，下推+本地复核 | `chat()` docstring + `_source_in_scope` |
| MCP 可用 `MCP_ROLE=admin` 伪造 | 已改为 `MCP_USERNAME` 必须命中已注册用户 | `app/mcp_server.py:24,62` |
| 孤岛模块“没有任何调用方” | 准确表述：实现完整 + 单测通过 + 生产链路零接入 | `tests/test_index_publication.py`、`tests/test_retrieval_debug.py` |

---

## 3. 切片任务

### Wave 1（4 片互不重叠，可立即并行）

**S5 契约与解析器一致性** — 低风险，先打通验收信心
- Write set：`app/rag/loader.py`、`app/documents/file_security.py`、`docs/api/contract-v1.md`、`docs/current-functionality-2026-09-10.md`、`tests/test_file_upload_security.py`
- 缺陷 A：白名单 `.md .xlsx .csv` 能过 `inspect_upload_header`，但 `load_document()`（`app/rag/loader.py:59`）只处理 `pdf/docx/doc/txt`，结果删文件后抛 500「文档解析失败」（`app/api/v1/chat.py:1284`）
- 处置：知识库白名单收敛为 `pdf/txt/md/docx`；`loader` 补 `.md`（直读即可）；`xlsx/csv` 从知识库链路移除，只走 `/upload-excel` 数据集链路
- 缺陷 B：`docs/api/contract-v1.md` 写了 `POST /api/v1/ask-queue`，源码全仓无此路由（真实行为是 `/ask` 超限自动入队）。**改文档，不新增路由**
- 缺陷 C：文档 §19「没有发现 PGVector 扩展」是错的——`migrations/0001:4` 有 `CREATE EXTENSION IF NOT EXISTS vector`，`0002:235` 有 `chunks(... embedding vector ...)`。订正为「schema 骨架已入库，无维度、无 HNSW/IVFFlat 索引、无写入方，向量读写 100% 走 Chroma `app/rag/retriever.py:190`」
- Accept：`.md` 上传成功入库；`.xlsx` 走 `/upload` 得 `400 unsupported_file` 而非 500；grep 全仓无 `ask-queue`；契约/文档 §19 与迁移一致

**S2 审计持久化（原 P1-5）**
- Write set：`app/common/audit.py`、`migrations/0005_audit_events.sql`（新）、`migrations/manifest.json`、`tests/test_security_operations.py`
- 现状：`app/common/audit.py:3` 模块级 `_events` 列表 + `Lock`，重启即丢，S1 那批 403 完全不可追溯
- 改造：走 `app/storage/persistence.py:build_persistence_adapter()`，复用既有 JSON/Postgres 双后端，**不新造一套平行存储**；事件补 `request_id`、`resource_scope`、`policy_version`、变更前后摘要、保留期；沿用 `app/common/tracing.py:sanitize_trace_event()` 脱敏
- 边界：写失败必须显式可观测，不得静默丢弃后返回成功
- Accept：判定链可跨进程回放；`record_audit` 全部调用点（`app/api/v1/artifacts.py:28`、`app/api/v1/intelligence.py:58` 等）签名不变或同步更新

**S3 管理面只读 HTTP（原 P2-5，把孤岛接出来）**
- Write set：`app/api/v1/observability.py`（新）、`app/main.py`（仅挂载一行）、`tests/test_observability_routes.py`（新）
- 现状：`app/rag/debug.py:run_retrieval_debug` 全仓**调用方为 0**；`TraceStore.replay()` 无路由；评测只 CLI（`scripts/run_quality_evaluation.py`）；审计无读接口
- 路由：`POST /api/v1/retrieval/debug`（Principal 强制、top_k 上限、有界报告）、`GET /api/v1/traces/{trace_id}`、`GET /api/v1/evaluations`、`GET /api/v1/audit/events`
- 权限：trace/audit 要求 `audit:read`（auditor 可读），retrieval debug 要求 `resource:view`，evaluations 要求 admin；错误体一律 `ErrorEnvelope`；无 Principal → `401 authentication_required`，**不降级 admin**
- 约束：`AuthMiddleware` 白名单不得扩大；这些路径必须是已鉴权路径
- Accept：`openapi.json` 出现上述 path；越权与匿名用例返回稳定 code

**S6 内存回退与多实例边界收口（含死代码）**
- Write set：`app/knowledge_graph/service.py`、`app/common/open_platform.py`、`app/memory/long_term.py`、`app/memory/profile.py`、`app/common/queue.py`、`app/common/auth.py`、`tests/test_deployment_guards.py`、`docs/deployment/`
- 缺陷：生产环境仍允许内存回退且伪装成正常状态——知识图谱字典、开放平台 `_APP_REGISTRY`、无库用户表、记忆表
- 改造：生产缺依赖时启动失败或进入只读保护；`/health/details`（`app/common/monitoring.py:build_health_snapshot`）如实报告每个子系统的 `storage_mode`
- 死代码：`app/common/queue.py`（BLPOP 版）现仅剩 `tests/test_reliable_queue_request_path.py:18` 引用 → 删除或显式标 deprecated 并把该测试改为只测 ReliableQueue
- 开放平台补 `POST /api/v1/apps` 注册面（admin + 强制审计），替换“只能代码内 `register_application()`”
- Accept：生产模式无库时 `/health/details` 不得报 `ok`；`frontend/` 零改动

### Wave 2（等主 thread 提交）

**S1 文档所有权与授权根因（原 P1-1 + P2-6，一条链一次修完）**
- Write set：`app/documents/catalog.py`、`migrations/0006_document_ownership.sql`（新）、`migrations/manifest.json`、`app/common/policy.py`、`app/api/v1/chat.py`（仅文档授权helper与上传/删除路径）、`tests/test_document_route_authorization.py`、`tests/test_document_delete_catalog.py`
- 步骤：① `record_document_version()` 接 Principal 并写 `owner_id`；② 两张表补 `owner_id` 并入 manifest 校验和；③ `policy.py:94` owner_match 放开到全部动作；④ admin 显式超级语义，不再要求部门交集（用独立 reason_code，不要复用 `department_scope_match`）；⑤ 存量 `owner_id IS NULL` 必须显式决定处置策略并记入文档，**禁止默认视为公开**
- 注意 S1 与 S5 都会碰上传路径，但 S5 只改 `loader/file_security` 白名单，`chat.py` 写入权归 S1
- Accept：owner 删自己文档 200；admin 删任意文档 200；跨部门 staff 得 `clearance_insufficient` 或 `permission_denied`（不是 `department_scope_denied`）；删除级联 + 索引回滚 + 物理清理 + 审计四段可端到端验证

### Wave 3（依赖 S1）

**S4 索引发布接线 + chunks 落库**
- Write set：`app/api/v1/chat.py`（上传/删除链路）、`app/rag/retriever.py`、`app/rag/indexing.py`、`tests/test_index_publication.py`、`tests/test_document_catalog_sync.py`
- 现状：25 张迁移表运行时实际读写 17 张，空转 6 张 —— `chunks`、`index_registry`、`index_versions`、`resource_versions`、`metric_definitions`、`calculation_runs`；`tmp/e2e/REPORT.md:28` 实测上传-检索-删除全流程后恒 0 行。上传实际走 `rebuild_bm25()` 直连，绕过 `IndexRegistry.publish()`
- 步骤：① 上传/删除后 `create_version → validate → publish`，失败返回 `index_publish_failed` 并 `rollback`；② 同窗口写 `chunks`（带 `resource_id / version_id / owner_id / classification / department`）；③ **本切片不改检索实现**，Chroma 仍是唯一读路径
- Accept：e2e 探针那四张表不再恒 0 行；发布失败可回滚且不留半发布状态

**S7 指标语义事实层（依赖 S4 的 chunks/version 语义）**
- Write set：`app/semantics/registry.py`、`migrations/0007_metric_definition_sync.sql`（新）、`manifest.json`、`tests/test_business_semantics.py`
- 现状：`metric_definitions` 无人写入，因为 `app/semantics/registry.py` 是硬编码别名表（只有住宿费标准、差旅费两条），且每条都自带「未与已上传制度文件核对」告警
- 步骤：把定义落到 `metric_definitions` 并在 `MetricContext.definition_version` 暴露版本；`semantics/match` 读表、代码表退为兜底；保留 provenance 告警语义，不得伪装成已核对
- Accept：`/api/v1/semantics/match` 返回的定义带 `definition_version`；新增指标不需要同改代码

---

## 4. 未纳入本计划的既有事实（需主 thread 决策，不要静默修）

- **Dashboard / 洞察数据闭环**：`app/api/v1/intelligence.py:29` 的 `DashboardRequest.rows`、`InsightsRequest.rows` 由请求体提供；改成读已登记数据集会牵动前端契约，属跨 Agent 决策
- **会话三份状态**：前端 `ChatPanel.vue` localStorage + `session_messages` 表 + LangGraph checkpointer。后端侧 `SessionRegistry` 归属已收口，前端缓存权威化需前端 Agent 配合
- **checkpointer 降级后果**：`_make_checkpointer()` 探活 2s 失败退 `MemorySaver`，此后会话断、HITL 挂起态丢。是否改为生产直接拒绝启动，属部署决策
- **告警与洞察两套异常逻辑并存**（`app/api/v1/alerts.py` vs `app/insights/rules.py`），合并前不要单边改动

---

## 5. 验收命令（Worker 自证用）

```powershell
scripts\run_backend_tests.ps1                      # 全量后端
python -m pytest tests\test_document_route_authorization.py tests\test_file_upload_security.py -q
python -c "import app.main"                        # 导入不得需要活的依赖
python -c "import sys;sys.path.insert(0,'.');from app.db.migrations import MIGRATIONS,migration_plan;print([m.name for m in MIGRATIONS]);print([m.version for m in migration_plan({})])"   # 离线校验 manifest，不连库
```

迁移文件新增后必须同步 `migrations/manifest.json` 校验和，否则 `migration_plan()` 会拒绝漂移。

补充一条会影响 S3/S4 验收的环境事实：`tmp/e2e/REPORT.md:21` 记录该 e2e 环境缺 `chromadb / rank_bm25 / jieba / sentence_transformers`，检索实际退化成 JSON 兜底 + 朴素分词。因此 **S3/S4 验收前必须先确认依赖装齐**，否则「恒为 0 行」与「调试报告为空」两类结论都会失真。

## 6. 每个 Worker 的任务下发模板

```
你是 S<n> Worker。你负责的文件：<write set>。
不要碰其他文件；app/api/v1/chat.py 的写入权归 <S1/S4>，若冲突立即停止并上报。
你不是这棵代码树上唯一的 Agent，禁止回退他人改动。
先读 docs/handoff/2026-09-14-consolidated-fix-plan.md 对应切片 + 靶心行号，
再实现，最后输出：改动文件清单、Accept 项逐条自证、未解决风险。
禁止启动服务、连生产库、改 frontend/。
```
