# 验收发现

> **⚠️ 总控横幅（2026-09-16）**：本文件停在 09-13/09-14，**不能用来判断当前完成度**。
> 权威口径依次是：`docs/handoff/2026-09-15-orchestration-board.md`（三线派发与总控亲验，含 §4I 基线）
> → `docs/current-functionality-2026-09-10.md` + `docs/current-functionality-2026-09-10-revision-log.md`
> → `docs/api/contract-v1.md` → `docs/handoff/2026-09-15-backend-followup-requests.md`（R1–R15）。
> 总控亲跑的最近全绿基线 **771 passed / 22 skipped / 0 failed @ `826d318`**（33.74s，跑前后 `app|tests|migrations` 零脏）。
> 注意 R13 在途采用「红底先行」提交（`ad5ebbf`、`4136e8c`），**中间 HEAD 可能故意是红的**，那不是回归，别据此判定失败。
> 下文按原样保留，仅作历史归档。


## 初始状态

- 后端 `http://127.0.0.1:8001/api/v1/health` 返回 200。
- OpenAPI 暴露认证、用户、资料、会话、聊天、知识库、队列、数据上传、图表、导出和告警接口。
- PostgreSQL 5432 与 Ollama 11434 当前未监听；项目已具备部分降级逻辑。
- 工作区已有大量未提交改动，本轮只针对验收发现的问题进行最小修改。

## 已知风险

- 真实模型回答和 PostgreSQL 持久化需要对应外部服务可用后才能完成完整联调。
- 本轮需要通过受控的测试用户和临时文件验证鉴权与可变更接口，并在结束时清理。

## API 验收结果（2026-09-05）

### 已通过

- 健康检查、JWT 鉴权拦截、错误登录、用户创建/查询/删除、队列状态。
- 文本知识库上传、向量入库、文档列表、离线版本目录、文档删除。
- CSV 数据上传及画像。
- 柱状图、折线图、饼图、甘特图、思维导图生成及静态文件访问。
- PDF/Excel 导出及静态文件访问。

### 确认问题

| 功能 | 现象 | 根因方向 |
|---|---|---|
| 会话列表/详情/提问 | PostgreSQL 离线时返回 500，约等待 4 秒 | `chat.py` 会话函数直接连接 PostgreSQL，缺少内存回退 |
| 用户资料保存 | PostgreSQL 离线时返回 500，约等待 4 秒 | `memory/profile.py` 缺少离线存储回退 |
| 告警列表/规则 CRUD | PostgreSQL 离线时返回 500，约等待 4 秒 | `alerts.py` API 直接调用 PostgreSQL，缺少内存回退 |
| 聊天模型回答 | HTTP 200 但流中为 `Error code: 502`，约 14 秒 | Ollama 11434 未监听，当前模型客户端配置也存在无效端口回退日志；需继续检查模型配置与可用服务 |

### 非缺陷验证限制

- 雷达图请求仅传入 2 个维度，API 正确返回“至少需要 3 个维度”；待用 3 维有效输入复测。
- 告警手动巡检在 PostgreSQL 不可用时返回空列表，未抛出异常；告警规则读取/写入仍需修复离线回退。

### 追加验收（2026-09-05）

- 修复 `/api/v1/ask` 完成时步骤仍为 `running` 的问题：流结束前统一补发 `step done`，并在会话记录中保存 `status=done`。
- 真实中文任务请求已验证 `running -> done -> done` 事件顺序，知识库回答和会话保存均成功。
- 真实普通用户链路已验证：管理员令牌创建临时用户、普通用户登录、资料读写、知识库读取、告警规则 CRUD、队列查询、会话查询。
- 全量测试：`116 passed, 1 skipped`；前端 `npm run build` 通过；`git diff --check` 无空白错误。
- 当前运行环境 PostgreSQL `5432`、Ollama `11434` 未监听，因此真实模型推理和 PostgreSQL 持久化未标记为完整通过；系统已验证离线降级路径。
- 浏览器已有标签页接管接口在本轮不稳定，前端已通过生产构建、源码契约测试和开发服务器 HTTP 可达性验证，未冒充完整浏览器点击验收。
- 已启动本机 Ollama 服务，`11434` 正在监听，`qwen2.5:14b` 和 `nomic-embed-text` 已存在；修复客户端读取 `OLLAMA_BASE_URL` 并规范 `localhost` 为 `127.0.0.1` 后，真实 `/chat` 已返回模型回答。
- 本机未找到 PostgreSQL 服务、`pg_ctl.exe` 或标准安装目录，无法在当前环境直接启动 `5432`；项目继续使用已验证的内存回退。
### 上传进度改造（2026-09-05）

- 原问题：上传请求期间只有旋转图标，用户无法区分文件上传和解析入库。
- 修复：前端展示真实上传百分比；请求完成后显示“解析入库中”；成功后固定显示 `100%` 和“上传完成”。
- 说明：现有后端接口是同步响应，解析阶段暂不伪造精确百分比，因此该阶段使用明确文字和动态图标。

## 2026-09-06 额外发现

- `app/rag/retrieval_pipeline.py` 的 BM25 首次构建在并发首请求下会互相踩状态，能稳定触发 `list index out of range`；已用锁和并发测试修复。
- `/api/v1/ask` 的知识库与数据分析链路都能返回具体内容，前提是输入使用正确 Unicode；本轮早期出现的问号结果来自 PowerShell 传参与输出编码，不是业务接口本身。
- 数据分析接口可正常返回“上海店”利润最高，但首轮对话如果输入被编码污染，模型会退回泛化回答，属于测试输入问题而不是代码缺失。

## 2026-09-12 Stage 0 contract freeze

- The current workspace is dirty and contains existing frontend and backend edits; no cleanup or rollback was performed.
- `app/agents/contracts.py` previously only carried minimal Evidence, MetricContext, AgentResult and ReviewResult fields. It now also defines Principal, ResourceScope, AuthorizationDecision, ModelBudget, ArtifactRef, ErrorEnvelope and AgentContext, while retaining legacy fields for compatibility.
- `app/agents/state.py` now has explicit principal, request_id, trace_id, task_id, resource scope, cancellation and model-budget fields. This is a contract shape only; main orchestration does not yet populate every field.
- `docs/api/contract-v1.md` and `docs/superpowers/specs/2026-09-12-public-contract-freeze.md` freeze the REST/SSE and cross-agent boundary.
- Targeted verification: `python -m pytest -q tests/test_public_contracts.py tests/test_agent_collaboration.py tests/test_quality_platform.py` -> `14 passed`.
- Verification limitation: the `.venv` interpreter did not contain pytest; the workspace Python 3.11 interpreter was used. No service, database, Redis or Ollama was started.
- Static dependency mismatch remains: project metadata declares Python `>=3.14` while AGENTS.md and the implementation plan target Python 3.11. This is a P3 coordination issue until the runtime policy is resolved.
- Existing model routing still lacks real Ollama discovery/capability detection; existing storage still lacks the target PostgreSQL/PGVector/local-file/Redis production chain.

## 2026-09-12 Stage 1 progress

- Added offline database URL validation, migration metadata/lock helpers, and resource-ID based local file storage under `app/db/` and `app/storage/`.
- Added `app/common/model_capabilities.py` for injected-transport Ollama discovery and conservative chat/embedding capability inference. It returns `model_unavailable` instead of pretending discovery succeeded.
- Unified `Principal`: `app/common/identity.py` now re-exports the canonical contract model from `app/agents/contracts.py`; legacy `role`, `department`, `clearance`, and `from_user()` compatibility remain available.
- Hardened resource authorization: unknown request usernames no longer become principals; missing resource classification/department scope is denied; system principals do not bypass scope automatically; ownership only widens view access, not arbitrary actions.
- Targeted verification passed: `19 passed` for public contracts, RBAC/ABAC, authorization API, agent tool authorization, and open-platform tests; `8 passed` for storage/model-capability tests.
- Remaining stage 1 gap: route-level authorization coverage, persistent PostgreSQL schema/migrations, real Redis state, and actual Ollama discovery integration into model selection are not complete.

## 2026-09-12 P0 hardening progress

- `app/agents/tools.py` no longer defaults missing tool identity to an admin principal. `search_docs`, `analyze_data`, and `query_data` require the caller identity from injected `RunnableConfig`; missing identity returns an explicit `authorization_required` tool result.
- `app/common/model_handler.py` no longer returns a normal-looking offline business answer when the local provider fails. It returns a visible `model_unavailable` marker and states that no business conclusion was generated. This is an intermediate compatibility result; the final contract should expose `ErrorEnvelope` to the orchestrator/SSE.
- `app/tools/excel.py` replaced the direct unrestricted query path with AST allow-list validation before the existing evaluator. Unsafe names, private attributes, imports, comprehensions, lambdas, and unsafe methods are rejected.
- Updated tool tests to pass an explicit runtime identity where a successful tool call is intended. Existing direct calls without identity now intentionally exercise the denial path.
- Targeted verification passed: `28 passed` across tool authorization, tools, local model routing, and safe query tests.
- Remaining risk: the orchestrator still has legacy offline worker behavior and does not yet convert the model/tool markers into a single structured `AgentResult.error`; this belongs to the main integration phase.

## 2026-09-12 Stage 1 migration and authorization boundary

- The checked-in migration contract is now concrete but not deployed: `migrations/0001_core_resource_versions.sql` establishes `schema_migrations`, the PGVector extension, canonical `resource_versions`, and controlled `artifacts` metadata. `migrations/manifest.json` pins the SQL checksum, and `apply_migrations()` provides an explicit caller-owned execution path. It has only passed offline fake-connection validation; no PostgreSQL execution, concurrent lock, extension, or rollback test has occurred.
- The existing application still creates several tables at runtime in `app/common/auth.py`, `app/api/v1/chat.py`, `app/api/v1/alerts.py`, `app/documents/catalog.py`, and `app/memory/`. Those paths remain outside this Agent 2 task and must be migrated by their owners before production claims.
- Route-level resource isolation remains a P0/P1 integration gap: middleware now establishes a validated frozen `Principal`, but most routes do not load or evaluate `ResourceScope`; and `/static/` plus filename-addressed preview/download paths remain bypass risks.
- Read-only review on 2026-09-12 confirmed four Important findings: public `/static/` Artifact access, prefix-level anonymous bypass for `/api/v1/open/`, resource endpoints that can still perform action-only authorization when callers omit scope, and the prior local policy decision type/positional-field mismatch. The latter is fixed in `app/common/policy.py`; the first three require Agent 0 and route-owner integration.
- Required integration owners: Agent 0 must replace public static delivery with controlled Artifact access and narrow the open-platform boundary in `app/main.py` / `app/api/v1/chat.py`; data, alerts, intelligence, and open-platform route owners must load stable resource metadata and use `authorize_resource()` (not action-only authorization). No conflicting integration files were edited in this task.
- Local dependency status on 2026-09-12: PostgreSQL `enterprise_brain`, Ollama, FastAPI, and the Vite frontend are reachable. Redis requires authentication but no matching `REDIS_URL` is configured, and the active Python runtime is missing the declared `apscheduler` dependency, so Redis queue and scheduler behavior remain unverified and must not be described as running.
- Migration review residual test gaps: missing real PostgreSQL execution, lock contention, failure rollback, and runtime table migration coverage. These require isolated PostgreSQL/PGVector integration and are not safe to run in the current shared workspace by default.

## 2026-09-12 Queue and model runtime findings

- The Windows Redis service is bound to `127.0.0.1:6379`, runs in protected mode, and requires authentication. The project `.env` has no `REDIS_URL`; no persistent credential was added to it.
- The legacy active queue remains `app/common/queue.py` plus `deploy/queue_worker.py`, which uses `BLPOP` and does not carry idempotency, leases, ACK, dead-letter, or cancellation semantics. Replacing it requires a coordinated `chat.py` idempotency contract change before activating a worker.
- `app/common/cache.py` imports `redis` only if `REDIS_URL` is present, but the package was absent from both the active environment and project dependencies. The runtime package and `pyproject.toml` declaration are now aligned; `uv.lock` remains blocked by the Python 3.14 metadata mismatch.
- The model handler previously allowed unbounded concurrent local calls. It now applies a configurable `MODEL_MAX_CONCURRENCY` bound, but the orchestrator/trace layer does not yet record queue wait, first-token timing, or structured `ErrorEnvelope` for model admission failures.

## 2026-09-12 RAG authorization findings

- Chroma document chunks use numeric `classification` and a single `department` metadata field. Its transitional local JSON fallback accepts the same `$and` and `$in` filter shapes as the current query path.
- `RetrievalPipeline.search()` already accepts a Chroma `where` filter for semantic recall and a Python predicate for BM25 recall, so Principal-aware access can be added without changing the legacy public search signature.
- A principal's permitted classification range is `1..clearance`; its department scope is the de-duplicated union of `department` and `department_ids`. Empty or inactive scopes must reject before either recall path runs.
- `search_for_principal()` now applies this scope to both current recall branches before RRF. Legacy `search()` remains intact for compatibility until Agent 0 migrates its callers.
- The new TraceStore writes only explicit event payloads, passes them through the existing key-based redactor, and records source names rather than full document excerpts in `retrieval.completed`. It does not replace the planned persistent `AgentRun`/`ModelCall`/`ToolCall` schema.

## 2026-09-12 Middleware boundary findings

- The FastAPI AuthMiddleware previously bypassed all `/static/` paths and every path with the `/api/v1/open/` prefix. Anonymous static reads now require the normal JWT flow, and only the six existing signed open-platform endpoints bypass JWT middleware.
- Open-platform handlers still independently validate application registration, timestamp, action permissions and HMAC signatures. The explicit middleware allowlist prevents future router additions from becoming anonymously reachable by default.
- Static paths remain coarse-grained after authentication. They do not yet load `Artifact` metadata or evaluate `ResourceScope`, so cross-user artifact isolation remains an integration requirement.

## 2026-09-12 Upload route findings

- `POST /api/v1/upload` previously derived its disk name directly from the client filename. It now accepts only the file-security allowlist, validates magic bytes for binary types, stores to a bounded temporary file, then atomically renames to a resource-ID destination.
- Logical document name and physical storage name are intentionally separate. Catalog metadata retains the original display filename and version while `storage_path` resolves the randomized file for preview, download and deletion.
- This is route-level safety integration, not a complete Document resource model: owner, stable document ID, complete classification lifecycle, parsing status and per-route ABAC checks still require the target storage schema integration.

## 2026-09-12 Document route authorization findings

- Document paths now use version metadata as the authorization source rather than treating the logical filename or resolved disk path as proof of access.
- Catalog and indexed document lists use the same `ACTION_VIEW` resource decision as preview; version history rejects an unauthorized document instead of returning an empty but existence-revealing history.
- Download requires `ACTION_DOWNLOAD`, preview requires `ACTION_VIEW`, and delete requires `ACTION_DELETE`; all three use identical classification, department, owner and version inputs.
- Legacy filesystem-only records lack complete scope metadata and are deliberately hidden or rejected. This preserves default-deny behavior but means safe exposure of offline uploads depends on completing the persistent Document/DocumentVersion resource schema.
- The first backend restart command matched its own PowerShell process because its selection used a loose `uvicorn` command-line pattern. The corrected command restricted termination to `python.exe` processes running the exact Uvicorn command; FastAPI restarted successfully without data changes.

## 2026-09-12 Reliable queue integration findings

- The previous overload path called `app.common.queue.enqueue_request()`, while its polling API and worker used a separate legacy `BLPOP` lifecycle. This meant a reliable queue implementation could exist without serving any real request.
- `ReliableQueue` now owns queued, processing, done, cancelled and dead states for overload requests. Results are written before ACK so status polling cannot report done without a stored result.
- Queue task payloads carry an immutable Principal snapshot. Queue status and cancellation are owner-only and reject old tasks that lack owner data rather than letting any authenticated user enumerate request IDs.
- Redis connection is intentionally explicit. Without `REDIS_URL`, the request path reports `queue_unavailable`; it does not use the cache module's fakeredis fallback for tasks.
- The queue worker remains unstarted because the local Redis service is authentication-protected and the credential is intentionally not copied into `.env`. Offline fake-Redis tests cover the worker state machine, but a real Redis crash/recovery run is still required in an isolated deployment environment.

## 2026-09-12 Artifact controlled-delivery findings

- Generated chart/report files are no longer exposed through `/static/charts` or `/static/exports`. Content and download are resolved by a stable Artifact ID, an active-record check, and the common ResourceScope policy.
- The registry validates that both persisted and newly registered file paths remain inside its configured root. Metadata writes use a temporary file plus atomic replace; file contents are integrity-hashed at registration time.
- Chart creation requires `resource:analyze`; report creation requires `resource:export`. Agent and MCP entry points receive the identity through `RunnableConfig`; missing identities are rejected and are not substituted with `admin`.
- This is a transitional local implementation. It is not a substitute for the planned PostgreSQL Artifact table, source-version lineage, background expiry/physical deletion, distributed locking, or retention/backup erasure.

## 2026-09-12 Dataset access findings

- The old data-file route family authenticated callers but still treated the local directory and client filename as authority. It now requires a registered Dataset record and ResourceScope policy evaluation before list, preview, download, or Agent analysis opens a file.
- Legacy data files without registry metadata are deliberately hidden from protected routes and Agent data analysis. This is default-deny behavior; operators need a future reviewed registration/migration workflow before historical files can reappear.
- Upload parsing happens before dataset metadata publication, so a parse failure cannot leave a listed active dataset. Duplicate active logical filenames are rejected until the planned DatasetVersion model replaces compatibility filename routing.
- This remains an interim JSON registry. It has no PostgreSQL transaction, durable cross-process locking, schema/period/source metadata, version history, physical storage randomization, or lifecycle cleanup.

## 2026-09-12 Trace orchestration findings

- The previous trace adapter could only record events when callers invoked the retrieval debug helper directly. The live `/ask` orchestration now creates one request/trace/task identity tuple and records the redacted lifecycle to JSONL.
- Trace payloads intentionally store only session ID, worker names, result lengths, counts, terminal status, and errors. They do not copy request messages, model output, full document content, or tool result bodies into the lifecycle events.
- Canonical request SSE is additive during migration: `/ask` emits `request.started` plus one of `request.completed`, `request.failed`, or `request.cancelled`; existing `status`, `step`, `text`, and `done` payloads remain unchanged for the current frontend.
- The integration does not make Trace production-ready: the JSONL store lacks a resource authorization boundary, retention worker, cross-process write coordination, PostgreSQL queryability, per-model/per-tool spans, and source Evidence linkage.

## 2026-09-12 Principal-aware RAG Agent findings

- `search_docs` previously rebuilt a legacy role/department filter locally and called `pipeline.search()`, so the new default-deny `search_for_principal()` contract existed without protecting the primary Agent document tool.
- The document Agent path now consumes the same canonical Principal object that `/ask` passes into LangGraph. When only legacy config fields are present, they are converted into the canonical Principal for compatibility.
- The remaining retrieval observability gap is persistence depth, not route selection: live Agent retrieval now uses the permission-scoped entry point, but the resulting Evidence/RetrievalTrace is not yet stored in PostgreSQL or linked to an AgentRun row.

## 2026-09-12 Session owner isolation findings

- Session endpoints were authenticated by middleware but did not load a stable session owner, so a caller who knew another session ID could access its history or delete it.
- New authenticated sessions are bound to the active Principal in a transitional local registry. The session routes now filter and authorize by that registry, while unregistered legacy sessions are hidden by default.
- The new owner registry does not replace the target Session/SessionMessage database schema. Historical-session access requires a reviewed migration/import process instead of guessing owners from message content or session IDs.

## 2026-09-13 Final verification findings

- The second migration is manifest-pinned and covers execution, data lineage,
  retrieval, and index publication metadata. Only offline SQL-contract execution
  has been verified.
- Trace persistence now receives an explicit owner from orchestration, while the
  JSON adapters remain transitional and do not replace production PostgreSQL rows.
- Python metadata is aligned to the active 3.11 runtime and `uv lock --check`
  succeeds after regeneration.
- Full offline verification is green: `333 passed, 3 skipped`; skips remain
  environment-dependent and are not production integration proof.
- Redis authentication was not copied into `.env`; the reliable worker remains
  stopped. No shared PostgreSQL migration or destructive data operation ran.

## 2026-09-13 Migration execution gate

- The explicit migration runner is now available at `scripts/migrate.py` and is
  covered by three offline tests.
- The configured local PostgreSQL connection was reachable, but migration
  execution rolled back because PGVector is not installed in the PostgreSQL 16
  server. `schema_migrations`, `resource_versions`, and `datasets` remain absent.
- Docker is unavailable, so there is no safe local way to provision an isolated
  PostgreSQL+PGVector environment in this workspace. This remains the primary
  external blocker for production storage and PGVector retrieval acceptance.
- The post-change FastAPI restart was independently confirmed by process command
  line, startup logs, and a fresh HTTP health response. Scheduler startup is
  now verified locally; Redis Worker remains intentionally stopped because its
  authenticated URL is not configured.

## 2026-09-13 Legacy schema completion

- The remaining runtime-created compatibility schemas are now represented in
  `0003_legacy_runtime_tables.sql`; offline fallback behavior remains unchanged.
- Real application migration is still blocked by the missing PGVector extension,
  not by the new SQL catalog.

## 2026-09-13 Dependency readiness visibility

- Detailed health now distinguishes service reachability from production
  readiness. The current live response confirms Ollama is reachable, while the
  PostgreSQL server lacks PGVector and has no migration ledger because the
  migration transaction rolled back.
- Redis is listening locally but the application has no configured `REDIS_URL`;
  the probe therefore reports `not_configured` and the reliable Worker remains
  stopped.
- Probes are read-only, use short timeouts, and return exception type names
  rather than connection details or secrets.

## 2026-09-13 Redis environment gate

- A real Redis run found and fixed a production-relevant blocking defect:
  `reserve(timeout=0)` previously delegated to Redis `BRPOPLPUSH` with a zero
  timeout, which means block forever rather than poll immediately.
- The corrected implementation uses `RPOPLPUSH` for zero-timeout polling and
  preserves blocking behavior for positive timeouts.
- The isolated real Worker acceptance passed. The protected system Redis
  remains unavailable to the project because no authorized `REDIS_URL` is
  configured; no password was guessed or extracted.

## 2026-09-13 PGVector installation gate

- PostgreSQL 16.15 is installed and running, but its extension directories still lack
  `vector.dll`, `vector.control`, and the PGVector SQL upgrade scripts; this is the
  direct reason the formal migration transaction rolls back at `CREATE EXTENSION vector`.
- Official pgvector `v0.8.1` source was checksum-verified and compiled locally for
  the installed PostgreSQL 16 x64 server. The built artifact and SQL set are ready,
  but system installation requires an Administrator-approved copy into the PostgreSQL
  installation directories.
- A pre-migration database backup was produced and verified before attempting the
  system installation. The backup utility does not expose credentials in command-line
  arguments.
- The elevated installation script was launched through the normal Windows UAC path
  on 2026-09-13. The request exited with code `1`; no extension file appeared, so the
  server and project database remain unchanged. This is an external administrative
  gate, not a source-code failure and not a condition that should be bypassed.
- Current running services after fresh inspection: PostgreSQL service is running,
  Ollama responds at its local API, and FastAPI is listening on `127.0.0.1:8001`.
  Redis Worker remains intentionally stopped because the project has no authorized
  Redis connection URL for the protected service.
- Fresh authenticated health details and a direct PostgreSQL metadata probe agree:
  the server is reachable, but PGVector and the migration ledger are absent. This
  confirms the migration gate is external installation authorization rather than
  a database connection, checksum, or migration-runner defect.

## 2026-09-13 Isolated PGVector acceptance and legacy migration finding

- Windows administrator approval successfully installed the PGVector extension files.
  The original PostgreSQL account still cannot create the extension because its
  configured role is not a database superuser and the `postgres` superuser credential
  is unavailable. This distinction is intentional and must not be bypassed.
- A fully isolated PostgreSQL 16 cluster with the restored backup passed the complete
  target storage gate: PGVector `0.8.1`, migrations `0001` through `0003`, a vector
  operator query, and authenticated FastAPI dependency health all succeeded.
- The isolated run found a migration bug that offline tests had missed: prior runtime
  `sessions` tables may lack `user_id`. Migration `0003` now explicitly adds a
  nullable column before its owner index. It does not manufacture ownership for
  historical rows, preserving default-deny handling at the application layer.
- The isolated cluster is an acceptance environment. The live `5432` database and
  FastAPI process have not been redirected to it, so production switchover remains
  an operator decision rather than an implied side effect of testing.

## 2026-09-13 Identity and runtime DDL findings

- `load_memory()` and `synthesize()` had a shared `"default"` user fallback. This
  could mix unauthenticated work across requests and has been replaced with an
  explicit `authorization_required` memory boundary.
- The production-auth fix was incomplete because memory, document catalog, alerts,
  and chat still created schemas at runtime. These modules now validate the expected
  migrated tables instead of issuing runtime DDL when `APP_ENV` is `production` or
  `prod`.
- The migration catalog itself exposed a compatibility gap: `sessions` needed
  `title` and `updated_at`, `session_messages` needed `steps`, and chat's document
  metadata table had no formal migration. New migration `0004` adds those structures
  without assigning ownership to historical sessions.
- The active chat request now supplies the authenticated `Principal.user_id` when
  creating a PostgreSQL session. Anonymous session writes are rejected; legacy
  offline fallback remains confined to its process-local store.

## 2026-09-13 Trace persistence expansion

- The prior trace adapter wrote ordered redacted JSONL events and, when configured,
  only a `trace_events` record. It did not project lifecycle state into the already
  migrated AgentRun/AgentStep/ToolCall/RetrievalTrace entities.
- The new projection is intentionally conservative: a worker completion is recorded
  as a tool-like execution summary because this layer cannot truthfully reconstruct
  individual LangChain tool arguments. Live model spans and rich Evidence still need
  explicit instrumentation at their owning boundaries; they are not fabricated.


## 2026-09-13 Real-dependency acceptance and deployment-topology audit

### Defects that only a live PostgreSQL/Redis/container path exposed

- `PostgresPersistenceAdapter` read rows with `dict(row)` while the connection
  returns plain tuples. The first trace event of a request happened to survive, but
  every subsequent write raised `PersistenceWriteError`, i.e. the whole execution
  ledger would have failed silently in production. Fixed with `_as_record()`
  (Mapping -> dict, otherwise `zip(cursor.description, row)`). No offline test could
  have caught this because the JSON adapter never touches a driver.
- The same adapter ordered `agent_runs`, `agent_steps`, `tool_calls`, `model_calls`
  by a `created_at` column those tables do not have. `list()` therefore raised on
  real rows. Fixed with a per-table `order_column` (`started_at` for those four).
- `Dockerfile` was `FROM python:3.14-slim`, which contradicts
  `requires-python = ">=3.11,<3.14"`, and `uv sync` installed into `/app/.venv` while
  `CMD` ran a bare `uvicorn`. It also never copied `migrations/` or `scripts/`, so a
  container could not migrate or back itself up, and it baked `documents/`, `data/`,
  `chroma_db/`, `static/` into the image. All fixed plus a non-root `USER`.
- Compose used `postgres:16-alpine`, which has no `vector` extension, so migration
  `0001`'s `CREATE EXTENSION vector` could never succeed on a fresh install.
  Replaced with `pgvector/pgvector:pg16`.
- `deploy/nginx.conf` was a complete `http { ... }` file copied into
  `conf.d/default.conf`, which fails `nginx -t`. Inside it: `location /static/` with
  `alias` served generated charts and exports straight off disk, bypassing the
  Principal-scoped artifact routes (boundary rule 15); `/health` answered a literal
  `200 "OK"` from nginx, i.e. a permanent false green; `upstream` pointed at
  `127.0.0.1:8001..8008`, unreachable between containers; `limit_req 10r/m` would
  have cut off the frontend's 3s status polling; and paths were placeholders.
- Two Compose files each carried their own copy of the stack and had already
  diverged. The root file is now the single authoritative topology and
  `deploy/docker-compose.server.yml` is an overlay (logging, restart policy,
  `POSTGRES_MAX_CONNECTIONS`) sharing one `.env`.
- The scheduler was started inside the FastAPI `startup` hook. With a backend
  replica, a worker, and `start_workers.sh` launching eight instances, the periodic
  evaluation and daily report would have run many times concurrently. Ownership now
  sits in `deploy/scheduler.py`, gated by `SCHEDULER_ENABLED` (off in production,
  on for development so existing behaviour is preserved).
- Boundary rule 9 (no fixed model names) was violated in code:
  `app/common/model_config.py` defaulted to `"qwen2.5:14b"` and
  `app/common/monitoring.py` repeated the same fallback in the health snapshot. Both
  now resolve configured -> discovered from the local Ollama `/api/tags` -> none, and
  report `model_source`. An empty model name yields the honest offline model rather
  than a guessed one.
- `app/main.py` had `allow_origins=["*"]`, which for a private deployment with
  cookie/Bearer auth is a data-exfiltration surface. Replaced by the
  `CORS_ALLOW_ORIGINS` allowlist that fails startup in production when unset.
- `/api/v1/queue/status/{id}` reported terminal `dead`/`failed` states without any
  reason, breaking the "long tasks must expose a failure cause" rule.
  `ReliableQueue.failure()` now returns attempts/last_error/max_attempts on every
  branch.
- Pytest collected `tmp/*_test.py` scratch files, producing three collection errors
  that could mask a real regression; `testpaths = ["tests"]` pins discovery.

### Lessons to keep

- Acceptance against live servers must be opt-in (`EB_PG_ACCEPTANCE_URL`,
  `EB_REDIS_ACCEPTANCE_BIN`) and must refuse any target that is not the isolated
  database name/port, otherwise a routine `pytest` could hit the customer database.
- Secrets stay out of argv, out of logs, and out of the repo: DPAPI-protected secret
  files for PostgreSQL, a private `requirepass` config for throwaway Redis, and
  credentials injected only into child-process environments.
- `data/pgdata` in this repository is a real PostgreSQL data directory; it is now in
  `.dockerignore` so it can never be copied into an image.
- `app/agents/orchestrator.py:61` opens a `ConnectionPool(max_size=50)` per process;
  replicas x 50 must stay under PostgreSQL `max_connections`, which the server
  overlay now exposes instead of leaving implicit.
- Registry-side checksum verification was not possible from this machine
  (Docker Hub API and the desktop checksum endpoint returned 403/TLS errors through
  the local proxy), so installer trust rests on a valid Authenticode signature from
  `CN=Docker Inc` plus an MD5 equal to the CDN `ETag`. This is a weaker guarantee
  than a published digest and should be re-verified where the network allows.
- Container health must be real: nginx proxies `/api/v1/health`, the Compose
  `migrate` one-shot gates the application services, and nothing claims readiness
  that it does not probe.


## 2026-09-13 Compose interpolation silently corrupts credentials

- Compose performs variable substitution inside `env_file` values, while
  python-dotenv reads them literally. Verified with a throwaway fixture:
  `HASH=$2b$12$SALTVALUE$31rest` reached the container as `$$2b$$12$$31rest`
  (the unset `$SALTVALUE` was replaced with nothing), and only the doubled form
  survived intact.
- The repository `.env` therefore could not be the Compose source: its bcrypt
  `AUTH_PASSWORD_HASH` has three bare `$`, so a compliant-looking deployment would
  ship a broken hash and login would fail closed with no error text anywhere.
  `scripts/check_deployment_env.py` now reports the offending key and column
  without printing the value, and the Compose stack reads `deploy/.env.server`
  (gitignored) instead.
- Lesson: `docker compose config` returning 0 proves the file parses, not that the
  resulting environment is what the operator wrote. Interpolation needs its own gate.

## 2026-09-13 Toolchain trap: PowerShell pipes to python are ASCII

- `$OutputEncoding` on this host is `us-ascii`. Piping a here-string into
  `python -` silently replaces every non-ASCII character with `?`, so Chinese
  document content got written as runs of `?` and no command reported an error.
- Every file write with non-ASCII content must go through a here-string plus
  `[System.IO.File]::WriteAllText(..., UTF8)` into a `.py` file that is then
  executed, with `PYTHONIOENCODING=utf-8`. Two documentation sections were
  rewritten after this was found; `?{2,}` scans across the touched files are now
  part of the closing checks.


## 2026-09-13 Post-reboot findings

- The WSL2 platform cannot be provisioned on this host. After the reboot
  `Get-WindowsOptionalFeature` reports `VMP=Enabled WSL=Enabled`, but `wsl --status`
  and `wsl --update` still answer "the Windows Subsystem for Linux is not installed",
  and `wsl --install --web-download` exits 1 with "unable to connect to the server"
  (decoded from the UTF-16 output: `无法与服务器建立连接`). The legacy kernel MSI from
  `wslstorestorage.blob.core.windows.net` downloads fine (16.31 MB, Authenticode valid,
  `CN=Microsoft Corporation`) but installs with `1603` on this build. The Docker daemon
  therefore cannot start here: `failed to connect to the docker API at
  npipe:////./pipe/dockerDesktopLinuxEngine`.
- Network reachability on this machine is split: Azure/GitHub-codeload style endpoints
  work, `api.github.com` fails the TLS handshake through the local proxy
  (`127.0.0.1:7897`), and every download was ~800 KB/s or worse until the operator
  enabled the proxy. Tooling that needs GitHub/Store feeds cannot be assumed available at
  a customer site either, which is a delivery constraint worth designing around: ship
  offline artifacts (the Compose image set as a tarball, models as files) instead of
  requiring the target machine to reach a registry.
- `tests/test_orchestrator.py::TestEndToEnd` was not hermetic: it called
  `run_orchestrator()` against whatever happened to be listening, so the suite turned red
  purely because a reboot stopped the local model server. It is now gated by
  `EB_OLLAMA_ACCEPTANCE=1` *and* a live `/api/tags` probe
  (`tests/_live_model.py`), matching how `EB_PG_ACCEPTANCE_URL` and
  `EB_REDIS_ACCEPTANCE_BIN` already behave.
- `tests/_live_model.py` first used `settings.model`, which does not exist on
  `LocalModelSettings` (`model_name` is the field), so the gate silently skipped real
  acceptance. Field-name guesses are exactly what a live run catches and a static read
  does not; the same wrong attribute was fixed in the container gate probe.
- The isolated `5433` cluster is a process, not a service, so it dies on reboot; the new
  `scripts/start_isolated_pgvector.ps1` proved that by hanging on its own verification
  step: `psql` without `PGPASSWORD` waits for an interactive password. It now reads the
  DPAPI secret file and clears the variable in a `finally` block.
- `OLLAMA_MODELS` is set to `E:\Ollama\models` in this user's environment while the
  actual model store is `C:\Users\fengx\.ollama\models` (the E: directory is empty).
  A server started with the environment variable reports zero models, so "model
  unavailable" here was a configuration artefact, not a code defect. Anything that owns a
  model registry must state the path explicitly -- which is what the in-stack Ollama
  volume in `docker-compose.yml` does.


## 2026-09-13 Why WSL cannot be installed here (root cause, measured)

- Windows 11 Home China, build 26100.8655. Since 24H2 the WSL implementation is a
  separate distributable: the optional features only *permit* it. Measured on this box,
  `C:\Program Files\WSL`, `wslservice.exe`, `wslhost.exe`, `libwsl.dll`,
  `lxss\tools\kernel` and the `LxssManager` service are all absent; only the
  `wsl.exe` / `wslapi.dll` stub remains. That is why DISM says `Enabled` while
  `wsl --status` says "not installed" -- they are answering different questions.
- The Store channel is hijacked at the network layer, not by the proxy certificate store.
  The leaf certificate served for `dl.delivery.mp.microsoft.com` is
  `CN=default.chinanetcenter.com, O=网宿科技股份有限公司厦门分公司`, issued by
  `DigiCert Basic OV G2 TLS CN RSA4096 SHA256 2022 CA1`. A valid DigiCert chain for the
  wrong host name is exactly what makes WinHTTP/.NET report "could not establish trust",
  and what `wsl.exe --install` surfaces as "unable to connect to the server". An earlier
  guess that Clash Verge's GUID-named MITM root was responsible is ruled out: that CA is
  not in this chain.
- The GitHub channel is unreachable in both directions: through `verge-mihomo`
  (`127.0.0.1:7897`) the TLS handshake dies in ~0.2s (curl exit 35); forced direct
  connections fail with exit 7, including `raw.githubusercontent.com`. So
  `--web-download` cannot work either.
- The only reachable artifact is `wsl_update_x64.msi` on Azure Blob storage, which is the
  legacy Windows 10 kernel drop for the old in-box implementation. Installing it on 24H2
  fails with `1603` because there is no in-box implementation to attach to; its signature
  is valid, so the failure is about the wrong package, not a corrupt download.
- Consequence: Docker Desktop has no WSL2 backend and Windows Home has no Hyper-V, so the
  container gate cannot run on this host. Fixing it means either a genuinely
  overseas-exiting path (TUN plus a working node for `*.mp.microsoft.com` and
  `github.com`) or an offline copy of the modern `wsl.<version>.x64.msi`.


## 2026-09-13 Network reachability matrix (measured on this host)

| Endpoint | direct | via verge-mihomo :7897 | meaning |
|---|---|---|---|
| `cdn.jsdelivr.net` | - | HTTP 200 | proxy path itself is alive for domestic CDNs |
| `www.google.com/generate_204` | - | TLS failure (curl 35) after 5s | the selected node does not actually exit overseas |
| `github.com`, `api.github.com` | refused (curl 7) | TLS failure (35) | double-blocked: see hosts note below |
| `raw.githubusercontent.com`, `objects.githubusercontent.com` | refused | TLS failure | WSL release assets unreachable |
| `registry-1.docker.io/v2/`, `auth.docker.io`, `production.cloudflare.docker.com` | timeout (28) | TLS failure (35) | Docker Hub pulls are impossible from here |
| `desktop.docker.com` | TLS failure | HTTP 403 on `/` | host reachable; the installer path worked earlier, a bare path is refused |
| `dl.delivery.mp.microsoft.com` | cert name mismatch (60) | cert name mismatch (60) | served by `default.chinanetcenter.com` (Wangsu CDN) |

- `C:\Windows\System32\drivers\etc\hosts` (50 active entries, modified 2026-09-13
  19:15 by the installed Steam/game accelerators) maps **every GitHub domain, including
  `githubusercontent.com` and `api.github.com`, to `127.0.0.1`**. Nothing listens on
  local 443, so those names are dead-blocked rather than accelerated. Go-based clients
  such as mihomo still consult the hosts file, which is why the proxy route fails with a
  TLS error instead of reaching an upstream node.
- Practical consequence for delivery, independent of this laptop: a private deployment
  cannot assume the target machine can reach Docker Hub, GitHub or the Microsoft Store.
  Offline artifacts (image tarballs, the modern `wsl.<version>.x64.msi`, model files,
  locked wheels) are a delivery requirement, not an optimisation.


## 2026-09-14 Container engine bring-up (the 09-13 blockers are gone)

- WSL 2.7.14 installed from `wsl.2.7.14.0.x64.msi` after the accelerator entries in
  `hosts` were removed (backup `hosts.backup.orig`), and Docker Desktop 29.7.2 now reports
  Compose v5.5.1 with the `dockerDesktopLinuxEngine` pipe present. The 09-13 conclusion
  "this host cannot run the container gate" is superseded: it can, and it did.
- Compose v5.5 on this machine corrupts its own BuildKit session metadata whenever a
  single invocation builds two images: every build in that invocation dies before a layer
  is read with `failed to dial gRPC: header key
  "x-docker-expose-session-sharedkey" contains value with non-printable ASCII characters`.
  Building one service per invocation (`compose build migrate`, then
  `compose build frontend`) succeeds repeatedly, so the defect is in the desktop
  compose/buildx plumbing, not in `Dockerfile` or `frontend/Dockerfile`.
  `COMPOSE_BAKE=false` does not avoid it, and disabling the Docker AI hooks does not
  either (they were restored to their original state afterwards).
- An earlier `nvidia-container-cli: failed to start all plugins` error came from stale
  state inside the running desktop VM; a full engine restart cleared it and it has not
  recurred across three later builds.
- Cold build evidence: `enterprise-brain:local` built with `APT_MIRROR=mirrors.tuna...`
  and the new `--mount=type=cache,target=/root/.cache/uv`; `uv sync` alone took 719s the
  first time. The resulting image is 18.4 GB because `uv.lock` resolves the CUDA builds of
  the ML wheels, which a CPU-only private deployment does not need (recorded as P2).
- Docker Hub reachability is asymmetric and it is what stalled every `docker pull`:
  `registry-1.docker.io` answers (HTTP 401) through the system proxy at `127.0.0.1:7897`
  and times out without it, but `auth.docker.io` fails in **both** directions in the
  client's rule mode, so no pull token can be minted. The daemon therefore resolves the
  manifest, prints `Pulling fs layer`, and then downloads nothing - `/proc/net/dev` inside
  `docker-desktop` sampled 0 rx bytes twice over 12-15 s. A stalled transfer is also
  reused: a second pull of the same layer digest over a different registry inherited the
  dead session until the engine was restarted.
- The working acquisition path is host-side and needs no Docker Hub token:
  `crane pull --platform=linux/amd64 docker.m.daocloud.io/ollama/ollama@sha256:aa6f86f0...`
  (the mirror has its own auth realm `m.daocloud.io`), then `docker load` and retag. The
  digest is the official amd64 manifest digest taken from the Docker Hub API
  (`https://hub.docker.com/v2/repositories/ollama/ollama/tags/latest`,
  `last_updated 2026-09-10T06:09:32Z`, amd64 3703.3 MB), so pulling through a third-party
  mirror is still content-addressed against the publisher's digest. `crane` 0.22.1 came
  from GitHub (now reachable again after the hosts cleanup); the downloaded archive hashes
  to `0E073EA8192C3B8442EC8AAF44D53C1050A09084669FAE3A6CEB0F2026CF8B21`.
- Delivery consequence, now with a proven procedure rather than an inference: the installer
  must carry base images as digest-pinned `docker save` tarballs and load them offline.
  Assuming `docker pull` works on a customer machine is not acceptable.
