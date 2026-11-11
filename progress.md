# 验收进度

> **⚠️ 总控横幅（2026-09-16）**：本文件停在 09-13/09-14，**不能用来判断当前完成度**。
> 权威口径依次是：`docs/handoff/2026-09-15-orchestration-board.md`（三线派发与总控亲验，含 §4I 基线）
> → `docs/current-functionality-2026-09-10.md` + `docs/current-functionality-2026-09-10-revision-log.md`
> → `docs/api/contract-v1.md` → `docs/handoff/2026-09-15-backend-followup-requests.md`（R1–R15）。
> 总控亲跑的最近全绿基线 **771 passed / 22 skipped / 0 failed @ `826d318`**（33.74s，跑前后 `app|tests|migrations` 零脏）。
> 注意 R13 在途采用「红底先行」提交（`ad5ebbf`、`4136e8c`），**中间 HEAD 可能故意是红的**，那不是回归，别据此判定失败。
> 下文按原样保留，仅作历史归档。


## 2026-09-05

- 建立全量功能验收计划。
- 已获取运行后端 OpenAPI 清单、现有测试文件和前端组件范围。
- 已对运行中的 8001 服务执行真实 API 验收，并清理了临时账号、文本、数据及生成文件。
- 已通过：鉴权、用户、知识库、数据上传、部分图表、导出、队列。
- 已发现：会话、资料、告警在 PostgreSQL 离线时未降级；聊天模型因外部模型服务 502 无法生成回答。
- 下一步：先为三个离线 500 问题添加回归测试，再实现内存回退；同时检查模型配置和前端构建。

## 追加记录（2026-09-05）

- 定位并修复 `/ask` 结束时步骤状态永久为 `running` 的问题，新增 `_complete_pending_steps` 和回归测试。
- 真实服务复测：健康检查、临时用户登录、资料读写、知识库、告警规则、队列和会话均返回成功。
- 真实中文 SSE 任务已收到 `step running`、`step done`、`done`，历史会话中的步骤也为 `done`。
- 全量测试：`116 passed, 1 skipped, 16 warnings`。
- 前端构建：`npm run build` 成功。
- `git diff --check`：通过，仅有 Git 的换行符提示。
- 环境限制：PostgreSQL 和 Ollama 未启动；浏览器标签页接管不稳定，未将其记为完整 UI 点击通过。

## 服务启动记录（2026-09-05）

- Ollama 已启动并监听 `127.0.0.1:11434`。
- 本机已有 `qwen2.5:14b` 和 `nomic-embed-text` 模型。
- 修复 `model_handler.py`：使用 `.env` 的 `OLLAMA_BASE_URL`，并将 `localhost/::1` 规范为 IPv4 回环地址；本地模型默认超时调整为 60 秒。
- 真实 `/api/v1/chat` 已返回本地模型回答，耗时约 7.8 秒。
- Docker 未安装；本机未找到 PostgreSQL 安装或服务，因此 `5432` 无法由当前环境启动。
## 上传进度改造（2026-09-05）

- 上传队列项新增真实上传百分比、上传/解析入库阶段和完成状态。
- Axios `onUploadProgress` 将上传阶段映射到 `0% - 70%`；解析入库阶段显示动态处理状态；成功后显示 `100%`。
- 新增前端回归测试，覆盖进度回调、阶段切换和完成状态。
- 前端测试 `4 passed`，生产构建成功。
- 全量测试 `119 passed, 16 warnings`；开发前端和后端健康检查均返回 `200`。
## Local model routing update (2026-09-06)

- Added one internal OpenAI-compatible model configuration for Ollama or an internal vLLM/SGLang endpoint.
- Switched Agent creation, RAG query rewriting, follow-up rewriting, and legacy chat defaults to the internal model.
- Removed the temporary external-model compatibility path before delivery; local inference is now the only model route.
- Added regression tests for endpoint configuration, local routing, and cloud isolation.
- Final verification: `145 passed`, frontend production build passed, and the browser showed `🖥️ 本地模型` with no model switch button.
- 问答跑偏修复（2026-09-06）：定位到 `/ask` 流式适配层错误，子 Agent 的正确结果被监督节点的通用客套话覆盖；现已让 `synthesize()` 和 SSE 结束阶段优先使用 `worker_results`，并新增回归测试。
- 真实接口复测：登录 `200`，`/api/v1/ask` 返回 `200`，SSE 已包含正确的 `500元/晚` 答案和 `done` 事件。
- 全量回归：`147 passed, 18 warnings`；前端 `npm run build` 通过。
- 浏览器 DOM 快照本轮因运行时 `incrementalAriaSnapshot` 兼容性错误未能完成自动点击验收，不能将其标记为浏览器全链路通过。

## 2026-09-06 额外验收

- `pytest -q` 以项目 `.venv` 运行通过，核心回归 `91 passed, 18 warnings`。
- 修复 `app/rag/retrieval_pipeline.py` 的 BM25 首次构建并发竞态，新增并发回归测试 `tests/test_retrieval_pipeline_concurrency.py`。
- 真实 API 验证通过：登录、401、知识库上传/预览/下载/删除、普通账号删文档 403、管理员删文档 200、告警规则 CRUD。
- 真实 `/ask` 验证通过：同会话连续提问不串答，文档问答返回报销流程和审批人，数据分析返回“上海店”利润最高。
- 浏览器 in-app 自动化这轮多次重置，未作为最终验收依据。

## 2026-09-08
- 开放平台入口已放行，	ests/test_open_platform.py 通过。
- 全量 pytest -q 通过（202 passed, 3 skipped）。
- rontend 
pm run build 通过。

## 2026-09-08 前端阶段 5/6/7
- 新增企业后台风格主题和统一工作台壳。
- 完成经营驾驶舱、主动洞察、知识图谱、审批助手前端页。
- 前端 
pm run build 通过。

## 2026-09-08 前端补全
- 文档页、数据页、图表、预览模态统一为深色企业风。
- 聊天页全局皮肤继续统一。
- 前端 
pm run build 通过。

## 2026-09-08 细抛光
- 文档和数据卡片的层级、空态和 hover 再统一了一轮。
- 表格预览和列表项更贴近企业后台。
- 前端 
pm run build 通过。

## 2026-09-08 总览页补全
- 总览页升级成真正的首页驾驶舱，加入模块入口与最新洞察。
- 前端 
pm run build 通过。
## 2026-09-10 多智能体开发计划

- 新增 `docs/superpowers/plans/2026-09-10-enterprise-brain-multi-agent-development-plan.md`。
- 计划覆盖主集成、权限、数据库与迁移、文件处理、RAG、Ollama 与性能、Redis 队列、Trace/评测/后台、业务闭环、部署恢复和只读 Review 共 11 条 Agent 线。
- 已明确每条 Agent 的文件所有权、禁止修改范围、公共 API/SSE 契约、阶段依赖、冲突处理、合并顺序、测试矩阵和发布门槛。
- 已明确当前前端 Agent 继续独占 `frontend/`；本轮未修改前端源码、业务源码、数据库、Redis、Ollama 或部署环境。
- 本轮未运行测试，未启动服务。

## 2026-09-12 Stage 0 completion

- Re-read the execution prompt, AGENTS.md, current functionality document, revision log, multi-agent plan, workspace status, current source and tests.
- Confirmed `frontend/` has other-agent changes and remains untouched.
- Added the frozen public contract models and explicit Agent execution state fields.
- Added API/SSE contract documentation and public contract specification.
- Added `tests/test_public_contracts.py`.
- Targeted tests passed: `14 passed`.
- `git diff --check` passed for the changed tracked file; untracked contract files were syntax-compiled successfully.
- No services started, no external environment changed, no database or model data changed.
- Next: begin stage 1 with isolated storage/version interfaces and Ollama capability discovery, keeping high-conflict integration files untouched.
- Added `docs/api/resource-authorization-matrix.md` as the resource-level integration matrix; it documents required enforcement and does not claim current route coverage.

## 2026-09-12 Stage 1 partial completion

- Public Principal model unified across Agent and common authorization imports.
- Storage contract and model capability modules added with offline tests.
- Authorization default-deny hardening added with targeted tests.
- Verification: `19 passed` plus `8 passed`; no services started and no external data changed.
- Stage 1 remains in progress because route-level resource checks and persistent database integration are still pending.

## 2026-09-12 P0 hardening

- Removed Agent tool admin fallback and wired runtime identity through `RunnableConfig`.
- Replaced direct unrestricted `eval()` entry with AST validation and security regression tests.
- Changed model provider failure output to explicit `model_unavailable` text without a fabricated business conclusion.
- Verification: `28 passed`; `git diff --check` passed for affected files.
- Remaining integration work: structured error propagation through AgentResult/SSE, queue reliability, route-wide authorization, and real persistence.

## 2026-09-12 Stage 1 migration catalog

- Added an immutable SQL migration catalog under `migrations/` with the first PostgreSQL/PGVector control-plane migration.
- `app/db/migrations.py` now discovers versioned SQL files, computes SHA-256 checksums, rejects drift or removed applied versions, and returns the pending migration plan without opening a database connection.
- `0001_core_resource_versions.sql` defines the migration ledger plus generic versioned resource and Artifact metadata with owner, department scope, classification, visibility, status, version, integrity hash, and lifecycle fields.
- Added `migrations/manifest.json` so checked-in SQL is independently checksummed; `migration_plan()` now rejects any applied-migration input that lacks checksum mapping, including empty sets.
- Added explicit `apply_migrations()` for deployment runners that pass a PostgreSQL connection; it acquires a transaction-scoped advisory lock, reads the ledger, applies pending SQL, and records checksums in one transaction.
- Verification: `python -m pytest -q tests/test_storage_contract.py tests/test_model_capabilities.py tests/test_rbac_abac.py tests/test_authorization_api.py tests/test_agent_tool_authorization.py` -> `22 passed`; `python -m compileall -q app/db app/storage` -> success; `git diff --check -- app/db/migrations.py migrations/0001_core_resource_versions.sql migrations/manifest.json migrations/README.md tests/test_storage_contract.py task_plan.md progress.md findings.md` -> success.
- Read-only review found two P1 issues and one P2 issue in the first migration draft; after manifest enforcement, strict checksum mapping, and README update, re-review reported no unresolved Critical or Important findings.
- No PostgreSQL, Redis, Ollama, service, or external environment was started or modified.
- Integration request: route-level Principal/ResourceScope enforcement and static Artifact protection require Agent 0-owned `app/main.py` and `app/api/v1/chat.py`, plus domain-route metadata adapters; those files were not modified.

## 2026-09-12 Stage 1 policy contract alignment

- The API middleware now resolves a token subject to a canonical active `Principal` and attaches it to `request.state`; unknown subjects return `401` and inactive users return `403`. This is identity injection only, not route-wide resource authorization.
- `app/common/policy.py` now accepts frozen `ResourceScope` instances directly, normalizes known classification labels (`public`, `internal`, `confidential`, `secret`, `core`) to the existing numeric clearance levels, and rejects unknown labels.
- The policy layer now returns the frozen `app.agents.contracts.AuthorizationDecision` rather than a parallel local dataclass. It records the correct policy version and matched rules.
- `authorize_resource()` now requires a resource scope; action-only checks still use `authorization_decision(..., resource=None)` explicitly and cannot be mistaken for resource authorization.
- Read-only review found no Critical issue. It confirmed unresolved Important integration risks: public `/static/` Artifact access, the `/api/v1/open/` prefix bypass, filename-addressed resources without stable metadata, and missing route-level scope evaluation.
- Verification: `python -m pytest -q tests/test_rbac_abac.py tests/test_authorization_api.py tests/test_security_operations.py tests/test_agent_tool_authorization.py tests/test_storage_contract.py tests/test_model_capabilities.py` -> `30 passed`; `python -m compileall -q app/common/policy.py app/common/authorization.py app/main.py` -> success; `git diff --check` -> no whitespace errors, with only Git's CRLF conversion notice for shared `app/main.py`.
- No service, database, Redis, Ollama, local data, or `frontend/` file was changed.

## 2026-09-12 Local dependency startup and health verification

- User explicitly authorized local service startup. PostgreSQL was already listening on `5432` and a direct `psql` query confirmed database `enterprise_brain` is reachable.
- Redis was already listening on `127.0.0.1:6379`, but unauthenticated `redis-cli ping` returned `NOAUTH Authentication required`; the project `.env` does not configure `REDIS_URL`, so no worker was started against an unknown or fallback queue.
- Started Ollama locally; `GET /api/tags` confirmed `qwen2.5:14b` and `nomic-embed-text:latest`.
- Started FastAPI on `127.0.0.1:8001`; `GET /api/v1/health` returned `200` with `{"status":"ok"}`.
- Started the Vite frontend on `127.0.0.1:5173`; both the SPA root and the `/api/v1/health` development proxy returned `200`.
- The FastAPI startup log reports `No module named 'apscheduler'`, so the scheduler did not start. `apscheduler` is declared in `pyproject.toml` / `uv.lock`, but it is absent from the active Python environment. No package installation, database migration, or queue mutation was performed.

## 2026-09-12 Stage 2 queue and model runtime progress

- Added cancellation terminal-state coverage to `ReliableQueue`: a queued cancelled task is not reserved, and a cancelled processing task is not retried.
- Added `connect_reliable_queue()` with an explicit `QueueConnectionError`; it requires `REDIS_URL`, verifies `PING`, and surfaces missing client/auth/network failures instead of returning an unchecked queue.
- Installed `redis==5.3.1` in the active Python 3.11 environment and declared `redis>=5.0,<6.0` in `pyproject.toml`. `uv.lock` was not regenerated because the checked-in project metadata still requires Python `>=3.14`, while the active runtime is Python 3.11.
- A real Redis verification used the local service authentication configuration only in process memory, used a random `enterprise-brain:verify:*` key prefix, completed `enqueue -> reserve -> ack`, and deleted all test keys. It did not change `.env` or start a worker.
- Added a default one-slot local-model concurrency budget in `ModelHandler`; a held stream causes a visible `error_code=rate_limited` response, and the slot releases on stream completion or provider failure.
- Verification: `python -m pytest -q tests/test_reliable_queue.py` -> `9 passed`; `python -m pytest -q tests/test_model_concurrency.py tests/test_private_model_routing.py tests/test_model_capabilities.py` -> `12 passed`; compilation and `git diff --check` passed for the changed queue/model files (Git emitted only an existing CRLF conversion warning).
- Remaining integration: `app/api/v1/chat.py` does not send an idempotency key and `deploy/queue_worker.py` still consumes the legacy `BLPOP` queue, so the reliable queue has not replaced the active request path.

## 2026-09-12 Stage 3 retrieval authorization start

- Added `app/rag/filters.py`, which converts an active canonical `Principal` into a default-deny Chroma-compatible document filter. Anonymous, inactive, unscoped, and zero-clearance callers receive explicit retrieval scope error codes.
- Verification: `python -m pytest -q tests/test_retrieval_permissions.py` -> `3 passed`; `python -m pytest -q tests/test_retrieval_pipeline_fallback.py tests/test_retrieval_pipeline_concurrency.py tests/test_rbac_abac.py` -> `13 passed`; compile and whitespace checks passed.
- Local service recheck: FastAPI `8001`, Vite `5173`, and Ollama `11434` returned HTTP `200`. The running FastAPI process is PID `18612`.
- Next: add a Principal-aware retrieval pipeline entry point so semantic and BM25 recall both consume the same scope before querying.

## 2026-09-12 Stage 3 retrieval and trace contracts

- Added `RetrievalPipeline.search_for_principal()`. It builds the default-deny Chroma filter before running either semantic or BM25 recall, then derives the BM25 predicate from that same scope.
- Added `app/rag/debug.py` with a bounded retrieval debug report: it carries the permission filter, index/strategy versions, query rewrites, candidate counts, result locators and a redacted `retrieval.completed` Trace event.
- Added `app/trace/store.py`, an append-only local JSONL trace adapter with redaction, per-trace ordering and replay. It is an interim adapter, not PostgreSQL trace persistence.
- Verification: `python -m pytest -q tests/test_retrieval_debug.py tests/test_retrieval_permissions.py tests/test_trace_persistence.py` -> `9 passed`; `python -m pytest -q tests/test_retrieval_pipeline_fallback.py tests/test_retrieval_pipeline_concurrency.py tests/test_quality_platform.py tests/test_quality_runner.py tests/test_evaluation_report.py` -> `12 passed`; compilation and whitespace checks passed.
- Remaining integration: `chat.py` and Agent orchestration still use legacy retrieval/trace paths, so this stage is not complete and must not be presented as production persistence.

## 2026-09-12 P0 middleware boundary hardening

- Replaced the `/api/v1/open/` prefix bypass with an explicit allowlist of signed open-platform routes. Future routes under that prefix now require normal authentication unless explicitly added and individually signed.
- Removed the `/static/` anonymous bypass. Static charts, exports and files now pass through the normal JWT authentication boundary.
- Verification: `python -m pytest -q tests/test_security_operations.py tests/test_open_platform.py` -> `12 passed`; `python -m pytest -q tests/test_authorization_api.py tests/test_rbac_abac.py tests/test_agent_tool_authorization.py` -> `16 passed`; compilation and whitespace checks passed.
- Scope limitation: authenticated static delivery is a material P0 improvement, but it is not yet resource-level Artifact authorization; per-artifact owner/scope checks still require the planned Artifact registry and controlled download handler.

## 2026-09-12 Stage 2 upload route integration

- The document upload route now validates filename and file signature before persisting, writes in bounded chunks, and returns `400` for unsafe client names or unsupported headers and `413` after cleaning up an over-limit upload.
- Physical document storage now uses a random `resource_id` plus validated extension. The original safe filename remains the logical catalog and retrieval key; existing preview/download resolution continues to use the catalog `storage_path`.
- Successful uploads include `resource_id` and a resource-ID `stored_name`; no client filename is used as the physical storage path.
- Verification: `python -m pytest -q tests/test_document_upload_resilience.py tests/test_file_upload_security.py tests/test_file_preview.py` -> `24 passed`; `python -m pytest -q tests/test_document_delete_catalog.py tests/test_document_catalog_sync.py tests/test_retrieval_permissions.py` -> `9 passed`; compilation and whitespace checks passed.
- Remaining integration: document owner and complete ResourceScope metadata are not yet persisted into the catalog, and document read/preview/download routes do not yet call the resource policy for each document.

## 2026-09-12 Document route authorization integration

- Added route-level document authorization for catalog list, indexed list, version history, preview, download and delete paths in `app/api/v1/chat.py`.
- The route layer now derives one resource scope from document version metadata and sends it through the shared `authorization_decision()` policy. Missing classification/department scope is denied instead of treated as public.
- Cross-department principals cannot list, preview, download or inspect versions for unauthorized documents; matching department/classification metadata remains readable.
- Verification: `python -m pytest -q tests/test_document_route_authorization.py tests/test_document_catalog_sync.py tests/test_document_delete_catalog.py tests/test_document_upload_resilience.py tests/test_file_preview.py tests/test_authorization_api.py tests/test_rbac_abac.py` -> `39 passed`.
- Runtime service reloaded after the upload hardening and route authorization changes; FastAPI on `127.0.0.1:8001` returned `200` for `/api/v1/health`, and startup logs show APScheduler started.
- Remaining limitation: upload success in offline catalog mode still cannot persist owner and full ResourceScope metadata, so newly uploaded files without database-backed version rows cannot be safely exposed by preview/download until the target document resource schema is active.

## 2026-09-12 Reliable queue request-path integration

- The overloaded `/ask` path now requires an idempotency key and enqueues through `ReliableQueue`; it carries the rewritten request, session, username and frozen Principal payload. It no longer invokes the legacy `BLPOP` queue adapter.
- Missing idempotency key returns `400 idempotency_key_required`. Verified Redis connection failures return `503` with the frozen `queue_unavailable` error code rather than silently falling back to an in-memory or legacy queue.
- Added `ReliableQueue.complete()` / `result()` so workers store their result before ACK. `deploy/queue_worker.py` now uses reserve, lease recovery, ACK, retry/dead-letter and cancellation transitions without starting the worker.
- Queue status, statistics and cancellation API paths now use the same reliable queue backend. Status and cancellation are owner-only: the queued Principal is checked against the authenticated requester, and tasks without an owner Principal are rejected by default.
- The public `ErrorEnvelope` and API contract now include `queue_unavailable`.
- Verification: `python -m pytest -q tests/test_reliable_queue_status_api.py tests/test_reliable_queue_request_path.py tests/test_queue_worker_reliability.py tests/test_reliable_queue.py tests/test_performance_runtime.py` -> `20 passed`; focused queue/auth run after owner isolation -> `17 passed`.
- Remaining limitation: the active Redis instance still requires an explicit `REDIS_URL` credential that is not stored in project configuration. The worker was intentionally not started; it must first receive the same explicit Redis URL in a controlled deployment environment.

## 2026-09-12 Artifact hardening started

- Re-read the multi-agent implementation plan, current functionality record, authorization matrix, persistent work ledger, source code, tests, and live service health.
- Confirmed FastAPI (`127.0.0.1:8001`), Vite (`127.0.0.1:5173`), and Ollama (`127.0.0.1:11434`) are reachable. Redis remains authentication-protected without a configured project `REDIS_URL`, so the worker remains intentionally stopped.
- Added first Artifact access tests for controlled content/download, cross-department denial, expiry/soft-delete denial, controlled chart response URLs, and removal of the legacy static bypass. The expected initial failure is pending because `app.storage.artifacts` does not yet exist.

## 2026-09-12 Artifact controlled-delivery completion

- Added `app/storage/artifacts.py`: a JSON-backed transitional Artifact registry with stable IDs, owner and department scope, classification, content SHA-256, soft deletion, expiry, and registry-root path validation.
- Added authenticated `GET /api/v1/artifacts/{artifact_id}/content` and `/download` routes. Reads resolve active metadata first, evaluate the shared ResourceScope policy, audit the decision, and return `404` for missing, expired, or soft-deleted Artifacts.
- `POST /api/v1/chart`, `POST /api/v1/export`, Agent chart/export tools, export fallback, and MCP tool calls now return controlled Artifact URLs. Generation requires the corresponding action permission before the file is created.
- `/static/charts/...` and `/static/exports/...` are blocked even after JWT authentication; the static mount remains only for non-Artifact assets.
- Updated Artifact-related tests to use temporary files and registry metadata rather than creating unregistered files under the shared `static/` directory.
- Verification: `python -m pytest -q tests/test_artifact_access.py tests/test_artifact_tool_urls.py tests/test_approval_stream.py tests/test_chart_agent_types.py tests/test_tools.py tests/test_security_operations.py tests/test_public_contracts.py` -> `34 passed`; `python -m compileall -q app\storage app\api\v1\artifacts.py app\api\v1\data.py app\agents\tools.py app\agents\orchestrator.py app\main.py app\mcp_server.py` -> success; scoped `git diff --check` -> no whitespace errors.
- Restarted the authorized FastAPI service. Fresh runtime checks: `GET http://127.0.0.1:8001/api/v1/health` -> `200 {"status":"ok"}`; authenticated `GET /static/charts/not-an-artifact.png` -> `404`. The active backend process is PID `18836`; startup logs show APScheduler started and the RAG preload used its normal CrossEncoder-to-RRF fallback.
- Remaining limitation: Artifact metadata is not yet persisted in the planned PostgreSQL `artifacts` table, no scheduled expiry/physical retention worker exists, and generated content does not yet require a DatasetVersion or CalculationRun source reference. MCP deployments must explicitly set an active `MCP_USERNAME`; no username is denied instead of falling back to an administrative identity.

## 2026-09-12 Dataset route and Agent access hardening

- Added `app/storage/datasets.py`, a JSON-backed transitional registry that attaches stable dataset and version IDs, owner, department scope, classification, status, and content SHA-256 to local files.
- `GET /data-files`, preview, and download now resolve a registered active Dataset before opening a local file. Lists filter records by `resource:view`; preview uses `resource:view`; download uses `resource:download`; unmanaged legacy directory files are hidden.
- `POST /upload-excel` requires `resource:upload`, rejects a duplicate active logical filename with `409 dataset_filename_conflict`, parses the file before publication, and removes the temporary file when parsing or registration fails.
- Agent `analyze_data` and `query_data` now resolve `data_filename` and unselected file enumeration through the same Dataset registry and `resource:analyze` policy; they can no longer scan unregistered files from the shared `data/` directory.
- Verification: `python -m pytest -q tests/test_dataset_route_authorization.py tests/test_data_file_catalog.py tests/test_tools.py tests/test_agent_tool_authorization.py tests/test_phase3_analysis.py tests/test_artifact_access.py tests/test_artifact_tool_urls.py tests/test_approval_stream.py tests/test_chart_agent_types.py tests/test_security_operations.py tests/test_public_contracts.py` -> `55 passed`; compilation and scoped whitespace checks passed.
- Restarted the authorized FastAPI service after the Dataset change. Fresh runtime checks: `GET http://127.0.0.1:8001/api/v1/health` -> `200 {"status":"ok"}` and authenticated `GET /api/v1/data-files` -> `200 {"files":[]}` because the current local data directory has no registered Dataset metadata. The active backend process is PID `2068`.
- Remaining limitation: metadata is transitional JSON rather than PostgreSQL; physical data files still use compatibility filenames, and there is not yet DatasetVersion history, source period/schema metadata, lifecycle cleanup, or a safe legacy-file registration workflow.

## 2026-09-12 Trace orchestration integration

- `run_with_stream()` now creates one stable `request_id`, `trace_id`, and `task_id` per execution (or consumes caller-provided values), stores them in the Agent state, and propagates them to every worker configuration.
- The active `/api/v1/ask` path generates those IDs once and passes them into the orchestrator. It emits canonical `request.started` followed by exactly one canonical terminal event while retaining legacy `status`, `step`, `text`, and `done` events for the existing frontend.
- The JSONL `TraceStore` now records redacted `request.started`, `step.progress`, worker `tool.completed`, and terminal lifecycle events for streamed orchestration. It records lengths and counts rather than response text.
- Verification: `python -m pytest -q tests/test_trace_orchestration.py tests/test_trace_persistence.py tests/test_public_contracts.py tests/test_agent_collaboration.py tests/test_chat_cache_safety.py tests/test_approval_stream.py tests/test_agent_tool_authorization.py` -> `21 passed, 28 warnings`; `python -m compileall -q app/agents/orchestrator.py app/api/v1/chat.py app/trace/store.py` -> success; scoped `git diff --check` -> success (only existing CRLF conversion notices).
- Fresh runtime health check: `GET http://127.0.0.1:8001/api/v1/health` -> `200 {"status":"ok"}`.
- Remaining limitation: Trace is still an unauthorised transitional JSONL adapter. It does not persist the planned AgentRun/AgentStep/ToolCall/ModelCall/RetrievalTrace entities to PostgreSQL and does not yet attach resource scope/owner metadata.

## 2026-09-12 Principal-aware RAG Agent integration

- Agent `search_docs` now resolves the canonical runtime `Principal` from LangGraph config, including pre-built Principal objects/dicts passed from `/ask`, and calls `RetrievalPipeline.search_for_principal()` instead of constructing a separate legacy RBAC `where`/predicate pair.
- Worker configs now carry `principal`, `request_id`, `trace_id`, and `task_id` into child graphs, so document retrieval, tools, and Trace share the same execution identity tuple.
- Verification: `python -m pytest -q tests/test_agent_tool_authorization.py tests/test_retrieval_permissions.py tests/test_tools.py` -> `20 passed, 23 warnings`; broader run `python -m pytest -q tests/test_trace_orchestration.py tests/test_trace_persistence.py tests/test_retrieval_permissions.py tests/test_retrieval_debug.py tests/test_agent_tool_authorization.py tests/test_tools.py tests/test_public_contracts.py tests/test_chat_cache_safety.py tests/test_approval_stream.py tests/test_artifact_access.py tests/test_dataset_route_authorization.py` -> `42 passed, 28 warnings`; compile and scoped whitespace checks passed.
- Restarted the authorized FastAPI service after the RAG/Trace changes. Fresh runtime health check: `GET http://127.0.0.1:8001/api/v1/health` -> `200 {"status":"ok"}`. The active backend process is PID `28244`.
- Remaining limitation: this does not yet create PostgreSQL RetrievalTrace rows, and unauthorized Trace replay/read APIs are still not exposed or protected by resource policy because the target trace schema is not in place.

## 2026-09-12 Full offline regression after RAG and Trace integration

- `python -m pytest -q` completed with `320 passed, 3 skipped, 28 warnings` in approximately 76 seconds.
- The skipped cases remain environment-dependent coverage and are not treated as completed PostgreSQL/PGVector, Redis worker recovery, or production deployment validation.

## 2026-09-12 Session owner isolation

- Added `app/storage/sessions.py`, a JSON-backed transitional owner registry. Authenticated `/ask` calls bind new session IDs to the active Principal; attempting to reuse another owner's ID is denied.
- `GET /sessions`, `GET /sessions/{session_id}`, and `DELETE /sessions/{session_id}` now require the registered owner. Lists exclude unregistered/legacy sessions; cross-owner details and deletion return `404 resource_not_found` to avoid existence disclosure.
- Verification: `python -m pytest -q tests/test_session_route_authorization.py tests/test_trace_orchestration.py tests/test_trace_persistence.py tests/test_retrieval_permissions.py tests/test_agent_tool_authorization.py tests/test_tools.py tests/test_public_contracts.py tests/test_chat_cache_safety.py tests/test_approval_stream.py tests/test_artifact_access.py tests/test_dataset_route_authorization.py tests/test_offline_runtime_fallbacks.py` -> `55 passed, 28 warnings`; compilation and scoped whitespace checks passed.
- Restarted the authorized FastAPI service. Fresh health check: `GET http://127.0.0.1:8001/api/v1/health` -> `200 {"status":"ok"}`. The active backend process is PID `36764`.
- Remaining limitation: this is a JSON transition registry, not the planned PostgreSQL Session resource/version model. It has no session retention, admin audit workflow, migration/import tool for historical sessions, or trace linkage.

## 2026-09-13 Storage and final verification

- Added `migrations/0002_execution_data_lineage.sql` for Dataset/DatasetVersion,
  CalculationRun, MetricDefinition, AgentRun/Step, ToolCall, ModelCall,
  RetrievalTrace, IndexRegistry/IndexVersion, Chunks, and Artifact source lineage.
- Updated `migrations/manifest.json`; both migrations are now discovered and
  checksum-verified. No shared production database migration was executed.
- Trace events now inherit the caller owner ID during streamed orchestration.
- Aligned the project to Python 3.11: `.python-version` is `3.11`,
  `pyproject.toml` requires `>=3.11,<3.14`, and `uv.lock` was regenerated.
- Fresh verification: `python -m pytest -q` -> `333 passed, 3 skipped`;
  `npm run build` -> success; `uv lock --check` -> success;
  compileall and `git diff --check` -> success.
- PostgreSQL `5432`, Redis `6379`, FastAPI `8001`, Vite `5173`, and Ollama
  `11434` were listening; FastAPI health and Ollama discovery returned 200.
- Remaining blockers are isolated-deployment work: configured Redis credentials
  for starting the worker, real PostgreSQL/PGVector migration and retrieval,
  backup/restore drill, and browser end-to-end acceptance.

## 2026-09-13 Migration runner and environment gate

- Added `scripts/migrate.py`, an explicit deployment-only migration entry point
  that loads `.env`, validates `DATABASE_URL`, closes connections, and reports
  transaction failures without swallowing them.
- Added migration runner tests: missing configuration, successful invocation, and
  connection failure reporting all pass.
- Attempted the authorized local migration against the configured PostgreSQL
  database. It rolled back at `CREATE EXTENSION vector` because the local
  PostgreSQL 16 installation does not contain PGVector (`vector.control` and
  `vector.dll` are absent). A direct catalog query confirmed no migration tables
  were left behind.
- Docker is not installed on this workstation, so an isolated PGVector/Redis
  Compose acceptance run cannot be performed here.
- Updated migration documentation to make PGVector an explicit deployment
  prerequisite. No schema bypass, SQLite substitution, destructive operation, or
  secret output was used.
- Final verification after these changes: `337 passed, 3 skipped`; compileall,
  `git diff --check`, and `uv lock --check` passed; frontend production build
  passed.
- Restarted the authorized FastAPI process using the exact Uvicorn command.
  Fresh process startup logs show RAG preload and APScheduler started, and
  `GET /api/v1/health` returned `200 {"status":"ok"}`.

## 2026-09-13 Legacy schema completion

- Added `migrations/0003_legacy_runtime_tables.sql` and manifest checksum for
  users, sessions, session messages, document versions, alert rules, alerts,
  memories, and user profiles.
- Updated migration contract tests; full verification is now `337 passed,
  3 skipped`, with compileall, lock check, and diff check passing.
- Re-ran `python scripts/migrate.py`; it still rolls back before any migration
  is recorded because the local PostgreSQL 16 server lacks PGVector.

## 2026-09-13 Dependency readiness visibility

- Added read-only probes in `app/common/monitoring.py` for Ollama, PostgreSQL,
  PGVector/migration-ledger state, and Redis authentication reachability.
- `/api/v1/health/details` now reports structured dependency status without
  exposing connection strings or credentials.
- Restarted FastAPI and verified a fresh response:
  Ollama `ok`, PostgreSQL `degraded` with `pgvector=false` and
  `migration_ledger=false`, Redis `not_configured`.
- Targeted verification passed: `16 passed`; compileall passed.

## 2026-09-13 Redis environment gate

- The existing Redis service on `127.0.0.1:6379` requires authentication and was
  left untouched.
- Started a temporary isolated Redis 5 instance on `127.0.0.1:6380` for real
  acceptance. Fixed a queue bug where `reserve(timeout=0)` could block forever
  by switching immediate polling to `RPOPLPUSH`.
- Queue regression passed: `17 passed`.
- Real Redis acceptance passed for idempotency, completion/result persistence,
  retry/dead-letter, cancellation, non-blocking empty polling, and lease expiry.
- Real `deploy/queue_worker.py` process acceptance passed: one queued task reached
  `done` with a stored result. Temporary Redis was then stopped; only 6379 remains.

## 2026-09-13 PGVector installation preparation

- Downloaded pgvector `v0.8.1` from the official codeload endpoint with normal TLS
  validation. The archived source checksum is
  `61182a6afd6fb94c0e7740c037a7d3c36a8cab1cc581ae5bd9b7b2cfd789bdfc`.
- Built the extension with PostgreSQL 16's Windows build files and the installed
  Visual Studio 2022 x64 toolchain. The generated `vector.dll` is x64 and has checksum
  `c0f2e09a499e8be903dba6f7f2e4c49e3ab3eba853941202565b1a2188997955`.
- Added `scripts/backup_database.py` with a focused regression test. PostgreSQL
  credentials are passed only through the child process environment, never in
  `pg_dump` arguments. A migration-precondition backup was created and validated with
  `pg_restore --list`.
- Added `scripts/install_pgvector_windows.ps1`. It validates the compiled DLL, control
  file and complete extension SQL set before copying, and it requires an explicit
  `-Force` before overwrite.
- A standard UAC launch was attempted on 2026-09-13. It returned exit code `1`, and
  `C:\Program Files\PostgreSQL\16\lib\vector.dll` plus
  `C:\Program Files\PostgreSQL\16\share\extension\vector.control` remain absent.
  No Windows security control was bypassed and no PostgreSQL system file was changed.
- Fresh offline verification: `python -m pytest -q` -> `339 passed, 3 skipped`;
  `python -m compileall -q app deploy scripts tests migrations`, `uv lock --check`,
  and `git diff --check` all exited successfully.
- Fresh authenticated `GET /api/v1/health/details` from the running FastAPI service
  reports Ollama `ok`, PostgreSQL `degraded` with `pgvector=false` and
  `migration_ledger=false`, and Redis `not_configured`. A direct project connection
  probe reported the same PostgreSQL state without printing connection credentials.
- The pre-migration custom dump remains readable by PostgreSQL 16's `pg_restore`
  (`66` table-of-contents entries). The compiled DLL's x64 architecture was
  revalidated with the actual installed Visual Studio `dumpbin.exe`; an initial
  verification command had referenced a non-existent MSVC version directory and was
  corrected without modifying any artifact.

## 2026-09-13 Isolated PGVector migration acceptance

- The existing PostgreSQL database role is the database owner but not a superuser.
  The only local superuser is `postgres`, and no password cache or environment
  credential was available. No authentication bypass or control-file privilege change
  was used.
- Created a separate PostgreSQL 16 cluster at `tmp/pgvector-isolated-5433` bound only
  to `127.0.0.1:5433`. Its generated service credential is stored only as a
  current-user DPAPI-encrypted file under `tmp/`; it was never printed or placed in
  `.env`.
- Restored `tmp/pre-pgvector-2026-09-13.dump` into the isolated `enterprise_brain`
  database. The first migration attempt exposed a real compatibility defect: old
  `sessions` tables can lack `user_id`, while migration `0003` created an index on it.
- Added a failing regression test, then updated `0003_legacy_runtime_tables.sql` to
  add the nullable legacy `sessions.user_id` column before the index. Historical rows
  remain unowned rather than being assigned an invented Principal. Updated the
  manifest checksum.
- Focused migration tests: `10 passed`. Real isolated migration then applied all
  three entries successfully. Database verification returned PGVector `0.8.1`,
  ledger `0001`/`0002`/`0003`, and vector distance `1.0`.
- A short-lived FastAPI instance on `127.0.0.1:8002`, configured only through its
  child-process environment, reported PostgreSQL `ok`, `pgvector=true`, and
  `migration_ledger=true`; it was stopped after the health check. The original
  service on port `8001` and the original database connection were not switched.
- Full regression after the migration compatibility fix:
  `python -m pytest -q` -> `340 passed, 3 skipped`; compileall, lock validation, and
  whitespace diff checks also passed.

## 2026-09-13 Identity and runtime DDL hardening

- Re-ran the complete regression after the production-auth hardening:
  `python -m pytest -q` -> `343 passed, 3 skipped`.
- Agent memory now resolves only a canonical `Principal.user_id` or an explicit
  legacy `user_id`. Anonymous requests no longer recall or persist data under a
  shared `"default"` identity; they return `memory_error=authorization_required`.
- Production runtime schema helpers in memory, profiles, document version catalog,
  alerts, and chat now check migrated tables with `to_regclass` and refuse missing
  schema rather than issuing `CREATE`/`ALTER` statements.
- Added manifest-pinned migration `0004_legacy_runtime_compatibility.sql` for the
  chat adapter's `sessions.title`, `sessions.updated_at`, `session_messages.steps`,
  and `documents` table.
- Applied `0004` only to the isolated `127.0.0.1:5433` acceptance database. Its
  migration ledger now contains `0001` through `0004`; the original `5432`
  database and project `.env` remain unchanged.
- Targeted verification: `6 passed` for anonymous-memory/production-memory checks;
  `41 passed` for catalog/alert compatibility; `26 passed` for chat/migration/session
  coverage. The full regression and final service restart remain to be repeated after
  the remaining trace and resource-authorization work.

## 2026-09-13 Trace persistence expansion

- Expanded the explicit persistence adapter mapping to the migrated
  `agent_runs`, `agent_steps`, `tool_calls`, `model_calls`, and
  `retrieval_traces` tables. PostgreSQL errors remain explicit; the local
  atomic JSON adapter remains the intentional offline fallback.
- `TraceStore.record_event()` now writes a minimal structured execution projection
  whenever an event has an explicit owner: request lifecycle -> `AgentRun`,
  worker completion -> `AgentStep` and `ToolCall`, retrieval completion ->
  `RetrievalTrace`. It stores IDs, state, timing, counts, filter snapshots and
  redacted summaries, not model output or document body.
- Targeted persistence/orchestration verification:
  `python -m pytest -q tests/test_persistence_adapter.py tests/test_trace_persistence.py tests/test_trace_orchestration.py`
  -> `12 passed`.


## 2026-09-13 Real-dependency acceptance + stage 5 deployment closure

### Isolated PostgreSQL (127.0.0.1:5433, PGVector 0.8.1)

- Created a throwaway `enterprise_brain_accept` database and applied
  `scripts/migrate.py` for migrations `0001`-`0004`: 25 tables, `vector` extension
  present, ledger checksums matching the immutable catalog. Credentials were passed
  only through the child-process environment.
- New `tests/test_postgres_execution_persistence.py` -> `7 passed`. It asserts the
  ledger checksum equals the catalog, `<=>` / `<->` nearest-neighbour queries work,
  the adapter writes and reads back all eight ledger record kinds, a record without
  an owner raises `ValueError`, a foreign key rejects an orphan step,
  `record_agent_result()` puts the summary into `agent_runs.metadata` without storing
  answer text, and a multi-event lifecycle projects correctly. Rows are cleaned up by
  owner afterwards (post-run counts verified back to zero).
- This run found and fixed the two `PostgresPersistenceAdapter` defects described in
  `findings.md`.

### Authenticated Redis Worker crash/recovery (127.0.0.1, throwaway port)

- New `tests/_redis_worker_driver.py` runs the real `deploy/queue_worker.process_one`
  and only replaces the model boundary with an explicit stand-in, so the local 14B
  model is never loaded by the test suite.
- New `tests/test_redis_worker_recovery.py` -> `5 passed` against a temporary
  `redis-server` whose `requirepass` lives in a private config file (an anonymous
  connection is asserted to raise `AuthenticationError`). Covered: SIGKILL of a
  worker followed by lease-expiry requeue (attempts 1 -> 2), retry then dead-letter,
  a successful job reaching `done` with its result and exactly one `agent_run`, a
  task with no Principal being refused without emitting a business conclusion
  (`failure.last_error == "authorization_required"`), and idempotency plus
  cancellation.
- Gap this exposed and fixed: `ReliableQueue.failure()` plus every
  `/api/v1/queue/status/{id}` branch now carry attempts/last_error/max_attempts.
  `tests/test_reliable_queue_status_api.py` updated (2 equality assertions corrected,
  2 new cases) and `docs/api/contract-v1.md` gained a "Long Task Status" section with
  a 2026-09-13 compatibility note.

### Backup / restore drill

- New `scripts/restore_database.py` (`list_backup()` TOC, `restore_database()` with
  `--no-owner --exit-on-error`, URL validated before the archive is touched,
  credentials env-only) plus `tests/test_postgres_backup_recovery.py` -> `3 passed`:
  seed datasets/AgentRun/vector chunks, `pg_dump`, TOC check, restore into a sibling
  `*_restore` database, then compare ledger checksum, row counts, `vector` extension,
  `<=>` results, owner/confidentiality/department arrays and foreign keys.
- `docs/deployment/backup-restore.md` updated with the verified isolated drill.

### Deployment topology (static gates green, container runtime pending)

- Rewrote `Dockerfile`, root `docker-compose.yml`,
  `deploy/docker-compose.server.yml` (now an overlay), `deploy/nginx.conf`,
  `.dockerignore`, `.env.example`, `deploy/.env.server.example`, `README.md`,
  `deploy/README.server.md`.
- Added `deploy/scheduler.py`, extracted `register_jobs()` / `run_forever()` into
  `app/scheduler/jobs.py`, added `SCHEDULER_ENABLED` and `CORS_ALLOW_ORIGINS`, and
  removed hard-coded model defaults in favour of
  configured -> discovered -> none with `model_source`.
- New `tests/test_deployment_topology.py` -> `14 passed` (offline consistency gate)
  and `tests/test_model_discovery_selection.py` -> `7 passed`.
- Updated stale expectations in `tests/test_phase8_deployment.py` (service `web:` ->
  `backend`/`worker`/`scheduler`/`migrate`) and `tests/test_upgrade_baseline.py`
  (no dependence on a guessed model name).
- `pyproject.toml` gained `[tool.pytest.ini_options] testpaths = ["tests"]`.

### Verification commands

- `python -m compileall -q app deploy scripts tests migrations` -> rc 0.
- `uv lock --check` -> rc 0 (198 packages resolved).
- `git diff --check` -> rc 0 apart from repo-wide CRLF noise.
- Full regression with the three opt-in environment variables set is re-run at the
  end of this entry; the previous pass was `429 passed, 3 skipped`.

### Blocked / not yet done

- Docker Desktop is not installed and WSL is absent. `wsl --status` reports the
  subsystem is not installed. The downloaded installer
  `tmp/docker-desktop-installer.exe` (576.9 MB, v4.90.0.238679, Authenticode valid
  for `CN=Docker Inc`) is ready, but enabling `VirtualMachinePlatform`/WSL2 and
  installing require elevation, and the session cannot continue without a host
  reboot. Until then `docker compose config`, the image build, `up -d`, and
  `nginx -t` inside the container remain unverified, and stage 6/7 browser
  end-to-end acceptance cannot start.
- The FastAPI process listening on `:8001` since 14:29 predates this round's code, so
  any manual browser check against it would be stale evidence.


## 2026-09-13 Evening: Docker Desktop installed, container gate partially opened

- Enabled `VirtualMachinePlatform` and `Microsoft-Windows-Subsystem-Linux` through an
  elevated DISM run: success, exit code `3010` (restart required).
- Installed Docker Desktop from the verified local installer
  (`tmp/docker-desktop-installer.exe`, Authenticode valid for `CN=Docker Inc`):
  `C:\Program Files\Docker\Docker` present, `docker --version` -> `29.7.2`,
  `docker compose version` -> `v5.5.1`.
- Client-side validation that does not need the daemon:
  `docker compose -f docker-compose.yml config --no-interpolate --quiet` -> rc 0 and
  the same for the server overlay -> rc 0.
- Those runs surfaced the credential-corruption defect described in `findings.md`,
  which is why the Compose stack now reads `deploy/.env.server` and why
  `scripts/check_deployment_env.py` exists.
- Still blocked on the WSL2 reboot: `docker compose build`, `up -d`, in-container
  `nginx -t`, in-container `migrate`, and the stage 6/7 browser pass.
- The `config` runs surfaced the bcrypt/`$$` interpolation defect; the follow-up fix
  (separate `deploy/.env.server`, `scripts/check_deployment_env.py`, five new topology
  gates, nine new checker tests) was verified with:
  - `python scripts/check_deployment_env.py deploy/.env.server` -> `ok`, rc 0;
  - `docker compose --env-file deploy/.env.server -f docker-compose.yml config -q` -> rc 0;
    same for the server overlay -> rc 0;
  - rendered JSON shows the doubled hash collapsing back to the exact value the
    development `.env` holds, so login keeps working inside the container;
  - `python -m pytest -q tests/test_deployment_env_check.py tests/test_deployment_topology.py`
    -> `28 passed`;
  - `python -m compileall -q app deploy scripts tests migrations` -> rc 0;
    `uv lock --check` -> resolved 198 packages; `git diff --check` -> only the
    pre-existing repo-wide CRLF warnings (34 lines), no new whitespace errors;
  - full regression with the acceptance gates on -> `443 passed, 3 skipped` (90.50s).
- Pre-reboot self-test of the new gate: `python scripts/verify_container_stack.py --down`
  -> `FAIL compose down -> failed to connect to the docker API at
  npipe:////./pipe/dockerDesktopLinuxEngine`, rc 1. That is the expected behaviour while
  WSL2 is enabled-but-not-active, and it proves the gate records real evidence instead of
  assuming success.
- `deploy/.env.server` (gitignored, untracked) now carries generated
  `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET` and the escaped
  `AUTH_PASSWORD_HASH`, so the post-reboot container run needs no further secrets work.
  The pre-existing `LANGSMITH_TRACING=false` was checked: tracing is off by default in
  `app/common/tracing.py:21`, so nothing leaves the machine.


## 2026-09-13 Post-reboot verification matrix

The reboot cleared the 5433 cluster, the 8001 API and the local Ollama, so this entry
records the commands that bring them back and the numbers each gate produces.

- `powershell -File scripts/start_isolated_pgvector.ps1` -> `isolated PostgreSQL started
  on 127.0.0.1:5433` (verified from a cold stop, not only the already-running path).
- `E:\Ollama\ollama.exe serve` with the default model store -> `/api/tags` reports
  `qwen2.5:14b` (8.37 GB) and `nomic-embed-text` (0.26 GB).
- All four gates on (`EB_PG_ACCEPTANCE_URL`, `EB_REDIS_ACCEPTANCE_BIN`,
  `EB_PG_BIN_DIR`, `EB_OLLAMA_ACCEPTANCE`):
  `python -m pytest -q` -> `443 passed, 3 skipped` (70.81s).
- Default offline run with no gates: `python -m pytest -q` -> `421 passed, 25 skipped`
  (21.15s) -- 15 real-dependency tests plus the 10 now explicitly gated (7 live model,
  3 pre-existing).
- `python -m pytest -q tests/test_orchestrator.py` with `EB_OLLAMA_ACCEPTANCE=1` ->
  `19 passed` in 46.46s, i.e. the live-model path really executes rather than passing by
  stubbing.
- `python -m compileall -q scripts tests/_live_model.py` -> rc 0.
- Container gate remains environment-blocked: `python scripts/verify_container_stack.py
  --down` still reports the missing `dockerDesktopLinuxEngine` pipe, and WSL2 cannot be
  installed on this host (see `findings.md`).
