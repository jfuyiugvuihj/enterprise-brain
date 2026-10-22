# 全量功能验收计划

> **⚠️ 总控横幅（2026-09-16）**：本文件停在 09-13/09-14，**不能用来判断当前完成度**。
> 权威口径依次是：`docs/handoff/2026-09-15-orchestration-board.md`（三线派发与总控亲验，含 §4I 基线）
> → `docs/current-functionality-2026-09-10.md` + `docs/current-functionality-2026-09-10-revision-log.md`
> → `docs/api/contract-v1.md` → `docs/handoff/2026-09-15-backend-followup-requests.md`（R1–R15）。
> 总控亲跑的最近全绿基线 **771 passed / 22 skipped / 0 failed @ `826d318`**（33.74s，跑前后 `app|tests|migrations` 零脏）。
> 注意 R13 在途采用「红底先行」提交（`ad5ebbf`、`4136e8c`），**中间 HEAD 可能故意是红的**，那不是回归，别据此判定失败。
> 下文按原样保留，仅作历史归档。


## 目标
对企业智脑当前可运行版本完成端到端功能验收，修复自动化验证发现的代码问题，并明确外部服务未部署造成的功能限制。

## 阶段

| 阶段 | 状态 | 内容 |
|---|---|---|
| 1 | 已完成 | 盘点 OpenAPI、现有测试、前端组件和运行服务 |
| 2 | 已完成 | 执行后端 API 功能验收与鉴权边界验证，修复离线 500 问题；全量回归通过 |
| 3 | 已完成 | 前端生产构建、源码契约测试、开发服务器可达性；使用真实浏览器完成登录、七个模块切换、文档/数据页面与移动端视觉验收 |
| 4 | 已完成 | 已验收上传、数据分析、图表、导出、告警与会话链路 |
| 5 | 已完成 | 修复离线回退、模型异常处理和 `/ask` 步骤收口，并运行完整回归 |
| 6 | 已完成 | 输出验收结果与外部依赖限制；Ollama 已启动，PostgreSQL 因本机未安装暂不能启动 |
| 7 | 已完成 | 切换统一内部模型接口，删除外部模型入口、配置、密钥和专用依赖，完成浏览器及全量回归 |

## 验收规则

- 不修改或回滚用户已有的无关变更。
- 测试数据使用临时命名并在可行时清理。
- PostgreSQL、Ollama、外部模型未运行时，记录为环境限制，不把未实际验证的路径标为通过。
- 只有拿到新鲜命令或浏览器证据后，才标记功能通过。

## 2026-09-12 Multi-agent upgrade execution

| Stage | Status | Evidence |
|---|---|---|
| 0. Baseline and public contract | completed | Workspace ownership recorded; public contract models and API/SSE contract added; 14 targeted tests passed |
| 1. Permission and storage foundation | completed for the code/storage boundary | Canonical Principal injection, ResourceScope-aware default-deny policy, local resource-ID storage, owner-scoped session registry, Ollama discovery contract, immutable migration catalog; migrations `0001`-`0004` applied and asserted against the isolated PostgreSQL+PGVector server (7 live tests); production `5432` switch deliberately deferred |
| 2. File safety, queue, Ollama | completed and accepted on authenticated Redis | Reliable queue with lease expiry, retry/dead-letter, cancellation, idempotency and `failure` diagnostics; real `deploy/queue_worker.py` process verified against a temporary authenticated Redis (5 live tests); local-model concurrency budget; default-deny when no Principal is present |
| 3. RAG and Trace | completed with real PostgreSQL rows | Document retrieval keeps the default-deny Principal filter contract; `/ask` propagates stable request/trace/task IDs, emits canonical SSE events, and AgentRun/AgentStep/ToolCall/ModelCall/RetrievalTrace/AgentResult now persist through `PostgresPersistenceAdapter` against live rows (two P1 write-path defects found and fixed by that acceptance). |
| 4-5. Business, quality, deployment | code + static gates completed, container gate pending | Stage 4 business closure (metrics, provenance-backed reports, unified insights/alerts, approval assistant, knowledge graph) and stage 5 management/deployment topology rewritten to match the code (Dockerfile, Compose, Nginx, scheduler ownership, backup/restore drill); `tests/test_deployment_topology.py` 14 passed offline; `docker compose`/browser verification blocked on a Docker Desktop install that needs a reboot |
| 6-7. Integration and final review | in progress | Offline and real-dependency review done (`429 passed, 3 skipped` with the opt-in gates); `frontend/` untouched; the end-to-end browser run over the container stack plus Ollama-honesty and restart drills remain open until the Docker gate clears |

## 2026-09-13 Identity and runtime DDL hardening

- [x] Remove anonymous `"default"` memory reads and writes from the Agent path.
- [x] Require production migrations instead of runtime DDL for users, memories,
  profiles, document versions, alert rules, alerts, sessions, messages, and
  document metadata.
- [x] Add migration `0004` for legacy chat-session compatibility and apply it
  to the isolated PGVector acceptance database on `127.0.0.1:5433`.
- [x] Persist lifecycle-derived AgentRun, AgentStep, ToolCall, and
  RetrievalTrace records through the configured persistence adapter.
- [x] Replace raw worker strings with canonical `AgentResult` records and
  record model-call spans from the live model boundary.
- [x] Complete route-level authorization for remaining business resources.
- [ ] Run the container and browser recovery gate (blocked: Docker Desktop
  installation requires elevation and a host reboot).

## 2026-09-12 Artifact access hardening

| Stage | Status | Content |
|---|---|---|
| Artifact registry and controlled delivery | completed | Principal-scoped JSON-backed Artifact registry, controlled content/download routes, expiry/deletion checks, permission checks before chart/export generation, and blocked `/static/charts` / `/static/exports` bypasses. PostgreSQL lifecycle persistence and source-version lineage remain pending. |

## 2026-09-12 Dataset route access hardening

| Stage | Status | Content |
|---|---|---|
| Dataset registry and access enforcement | completed | Registered Dataset records now control list, preview, download, upload collision handling, and Agent analysis. Unregistered legacy files are hidden. PostgreSQL Dataset/DatasetVersion persistence, immutable physical names, schemas, periods, and lifecycle remain pending. |

Stage 0 constraints: existing uncommitted changes are preserved; `frontend/` and
high-conflict integration files remain protected; PostgreSQL, Redis and Ollama were
not started by this turn.

## 2026-09-13 Continuation Status

| Area | Status | Evidence |
|---|---|---|
| Database migration catalog | completed offline | `0001`-`0003` SQL catalog, manifest checksums, storage tests |
| Trace owner propagation | completed | orchestration and persistence regression tests |
| Python/dependency alignment | completed | Python 3.11 pin, lock check, APScheduler/Redis imports |
| Backend regression | completed offline | `333 passed, 3 skipped` |
| Frontend production build | completed | `npm run build` |
| Local service health | verified | PostgreSQL/Redis/Ollama/FastAPI/Vite checks |
| Production database migration | pending isolated environment | not run against shared database |
| Redis Worker real run | pending explicit credential | worker intentionally not started |
| Redis Worker isolated acceptance | completed | temporary authenticated-free Redis on 127.0.0.1:6380; real Worker process completed a task |
| Backup/restore and browser E2E | pending deployment environment | not claimed as passed |
| Dependency readiness visibility | completed locally | detailed health now probes Ollama, PostgreSQL/PGVector, migration ledger, and Redis without mutating state |

The overall plan is not marked production-ready while the environment-dependent
items above remain unverified. No frontend files were modified in this continuation.

## 2026-09-13 Migration Gate

- [x] Added explicit migration runner and offline runner tests.
- [x] Attempted configured local PostgreSQL migration with transaction rollback.
- [x] Confirmed rollback left no partial migration tables.
- [x] Install/provide isolated PostgreSQL + PGVector environment.
- [x] Run Redis authenticated Worker crash/recovery acceptance.
- [x] Run the PostgreSQL backup/restore drill in an isolated environment.
- [ ] Run the full browser E2E in the deployment environment.

Final local verification on 2026-09-13: `337 passed, 3 skipped`, frontend build,
compileall, lock check, diff check, and fresh FastAPI/Ollama health checks passed.

## 2026-09-13 Continuation

- [x] Formalize remaining legacy runtime table schemas in migration `0003`.
- [x] Pin migration `0003` in the immutable manifest and update contract tests.
- [x] Re-run full offline verification after the schema addition.
- [x] Apply migrations in PostgreSQL with PGVector installed.
- [x] Run authenticated Redis Worker crash/recovery acceptance.
- [x] Run the backup/restore drill against a live `pg_dump` archive.
- [ ] Run the full deployment browser E2E.

## 2026-09-13 Dependency readiness visibility

- [x] Add read-only dependency probes to `/api/v1/health/details`.
- [x] Expose PostgreSQL connectivity, PGVector presence, and migration-ledger state.
- [x] Expose Redis configuration/authentication reachability without returning secrets.
- [x] Verify the running FastAPI process after restart reports current dependency state.
- [x] Install PGVector and apply the migration catalog in an isolated environment.
- [x] Provide an authorized Redis URL and run Worker crash/recovery acceptance.

## 2026-09-13 Environment gate continuation

- [x] Start an isolated temporary Redis instance on port `6380` without changing
  the existing protected `6379` service.
- [x] Fix `ReliableQueue.reserve(timeout=0)` to use non-blocking `RPOPLPUSH`.
- [x] Verify real Redis idempotency, completion, retry/dead-letter, cancellation,
  and lease-expiry recovery.
- [x] Start the real `deploy/queue_worker.py` process against isolated Redis and
  verify a queued task reaches `done` with a stored result.
- [x] Stop and clean the temporary Redis acceptance instance.
- [x] Provision an isolated PostgreSQL 16 + PGVector 0.8.1 server on
  `127.0.0.1:5433`; the system `5432` service stays intentionally untouched.

## 2026-09-13 PGVector installation preparation

- [x] Download and checksum-verify the official pgvector `v0.8.1` source archive.
- [x] Build the PostgreSQL 16 x64 extension locally with the installed Visual Studio
  toolchain and verify the resulting `vector.dll` architecture.
- [x] Add a deployment-only database backup script and create a verified pre-migration
  PostgreSQL backup without placing credentials on the command line.
- [x] Add an elevated Windows installation script that validates source artifacts and
  refuses to overwrite installed extension files unless explicitly forced.
- [ ] Installing PGVector into the *system* PostgreSQL service still needs an
  elevated session. This is now a deployment choice, not an acceptance blocker: the
  Compose stack ships `pgvector/pgvector:pg16`, and acceptance runs on `5433`.
- [x] Apply migrations `0001` through `0004` and verify PGVector plus the migration
  ledger checksum against the isolated PostgreSQL+PGVector acceptance database.

## 2026-09-13 Isolated PGVector acceptance

- [x] Create an isolated PostgreSQL 16 cluster on `127.0.0.1:5433` without modifying
  the existing `5432` service or the project `.env`.
- [x] Restore the verified pre-migration backup into the isolated database.
- [x] Apply migrations `0001` through `0003` as the isolated cluster superuser.
- [x] Verify PGVector `0.8.1`, migration ledger entries, and a vector-distance query.
- [x] Start a temporary FastAPI instance against the isolated database and verify
  authenticated health details report PostgreSQL `ok`, `pgvector=true`, and
  `migration_ledger=true`.
- [ ] Switch the persistent production service configuration only after an operator
  chooses the isolated database as its target or supplies the original PostgreSQL
  superuser credential. The original `5432` database remains unmodified.

Fresh offline verification after this preparation:
`python -m pytest -q` -> `339 passed, 3 skipped`; `compileall`, `uv lock --check`,
and `git diff --check` all completed successfully.


## 2026-09-13 Real-dependency acceptance (this continuation)

| Gate | Status | Evidence |
|---|---|---|
| Canonical `AgentResult` records + model spans from the live boundary | completed | `app/agents/evidence.py`, `app/trace/spans.py`, `app/trace/records.py`; `tests/test_agent_result_records.py`, `tests/test_model_call_spans.py`; live rows asserted in `tests/test_postgres_execution_persistence.py` |
| Route-level authorization for the remaining business resources | completed | `app/api/v1/intelligence.py:60`, `app/knowledge_graph/service.py:51`, `app/approval/assistant.py`; `tests/test_intelligence_route_authorization.py`, `tests/test_knowledge_graph.py`, `tests/test_approval_worker_honesty.py` |
| Isolated PostgreSQL + PGVector acceptance | completed | fresh `enterprise_brain_accept` on `127.0.0.1:5433`; `scripts/migrate.py` applied `0001`-`0004`; `tests/test_postgres_execution_persistence.py` -> `7 passed` |
| Authenticated Redis Worker crash/recovery acceptance | completed | throwaway `redis-server` with `requirepass` from a private config file; `tests/test_redis_worker_recovery.py` -> `5 passed` |
| Backup and restore acceptance | completed | `scripts/restore_database.py` + `tests/test_postgres_backup_recovery.py` -> `3 passed` (dump, TOC, restore into a sibling database, row/owner/vector parity) |
| Deployment topology consistency | static gates completed, container runtime pending | `tests/test_deployment_topology.py` -> `14 passed`; Dockerfile, both Compose files, `deploy/nginx.conf`, scheduler/worker entrypoints aligned |
| Docker Desktop runtime validation (`compose config`, build, `up`, `nginx -t`) | blocked on a host reboot | installer `tmp/docker-desktop-installer.exe` 576.9 MB, Authenticode valid (CN=Docker Inc, DigiCert), MD5 equals the CDN ETag; WSL2/VirtualMachinePlatform require elevation plus a reboot |
| Browser end-to-end acceptance on the container stack | pending | requires the stack above to run |

Full regression with the opt-in acceptance gates enabled: `python -m pytest -q` ->
`429 passed, 3 skipped`. Without `EB_PG_ACCEPTANCE_URL` / `EB_REDIS_ACCEPTANCE_BIN`
those files report as skipped, so the default offline run never touches a live server.

## 2026-09-13 Deployment topology rewrite (this continuation)

- [x] `Dockerfile` pinned to `python:3.11-slim` to match `requires-python`, installs
  the project venv via `UV_PROJECT_ENVIRONMENT`, copies `migrations/` and `scripts/`,
  runs as a non-root uid, and keeps customer data (`documents/`, `data/`,
  `chroma_db/`, `static/`) out of the image.
- [x] `postgres:16-alpine` replaced with `pgvector/pgvector:pg16` (plain alpine has no
  `vector` extension, so migration `0001` could never have run).
- [x] `deploy/nginx.conf` rewritten as a real `conf.d` fragment: no public `/static`
  or `alias`, sensitive runtime directories denied, `/api/v1/health` proxied instead
  of a fake `return 200`, request-rate limit relaxed so the frontend poll survives.
- [x] Root `docker-compose.yml` is now the single authoritative stack
  (`postgres`/`redis`/`ollama`/one-shot `migrate`/`backend`/`worker`/`scheduler`/
  `frontend`); `deploy/docker-compose.server.yml` is an overlay, not a copy.
- [x] Scheduler ownership fixed: `SCHEDULER_ENABLED` gates the in-process scheduler
  (off in production) and `deploy/scheduler.py` runs exactly one scheduler.
- [x] Hard-coded model names removed; defaults now resolve
  configured -> discovered from local Ollama -> none (`model_source` is reported).
- [x] `CORS_ALLOW_ORIGINS` replaces `allow_origins=["*"]` and fails startup when
  unset in production.
- [x] Offline consistency gate `tests/test_deployment_topology.py` -> `14 passed`.
- [ ] `docker compose config`, image build, `up -d`, and `nginx -t` inside the
  container remain unverified until Docker Desktop can run.


## 2026-09-13 Evening container gate progress

- [x] Enable VirtualMachinePlatform + WSL (DISM rc 3010, reboot required).
- [x] Install Docker Desktop from the verified installer (docker 29.7.2, compose v5.5.1).
- [x] `docker compose config` passes for the base stack and the server overlay (client side).
- [x] Separate the Compose environment file (`deploy/.env.server`) from the development
  `.env`, because Compose substitution silently corrupts bcrypt hashes in `.env`.
- [x] Add `scripts/check_deployment_env.py` pre-flight plus README/deploy docs.
- [x] Fresh full regression after the env-file fix: `443 passed, 3 skipped`.
- [x] Add `scripts/start_isolated_pgvector.ps1`: the `5433` acceptance cluster is a plain
  process (`postgres.exe -D tmp/pgvector-isolated-5433 -p 5433 -h 127.0.0.1`), not a
  Windows service, so it does not survive a reboot and must be started again before the
  `EB_PG_ACCEPTANCE_URL` tests can run.
- [x] Add `scripts/verify_container_stack.py`: one command that runs the whole container
  gate (daemon wait, env pre-flight, `config` for base and overlay, build, `up -d --wait`,
  service states, in-container `migrate`, `pgvector` + ledger + table count, `nginx -t`,
  no `/static`/`alias`, real health probe, anonymous `health/details` refused, proxy path,
  runtime directories refused at the edge, single scheduler, live worker, honest model
  source) and writes a credential-redacted log to `tmp/container_gate.log`.
  Self-tested on the `--down` path: it fails cleanly with the real daemon error before a
  reboot. `--down --purge` tears the stack down again.
- [x] Rebooted. `VMP`/`WSL` report `Enabled`, but the WSL package itself cannot be
  provisioned here: `wsl --install --web-download` -> "无法与服务器建立连接", the Azure
  kernel MSI installs with `1603`, and `docker info` still cannot reach the daemon pipe.
  The container gate is therefore blocked by this host, not by the code.
- [x] Restored the acceptance environment after the reboot and re-measured the whole
  matrix: `443 passed, 3 skipped` with all four gates on; `421 passed, 25 skipped` by
  default offline; the live-model file alone runs `19 passed`.
- [x] Fixed `scripts/start_isolated_pgvector.ps1` (it hung asking for a password) and
  gated the non-hermetic `TestEndToEnd` behind `EB_OLLAMA_ACCEPTANCE` + a live registry
  probe (`tests/_live_model.py`).
- [ ] Run stage 6/7 browser end-to-end on the non-Docker path (uvicorn + queue worker +
  scheduler + isolated 5433 + local Ollama), which needs no container engine.
- [ ] Run the container gate wherever Docker actually works (or after this host gets an
  offline WSL package), then switch `PERSISTENCE_BACKEND`/ports for real.

Old sequence kept for reference:
  `powershell -File scripts/start_isolated_pgvector.ps1` ->
  `python -m pytest -q` (with `EB_*`) -> `python scripts/verify_container_stack.py`.
- [ ] Stage 6/7 browser end-to-end against the running stack.
