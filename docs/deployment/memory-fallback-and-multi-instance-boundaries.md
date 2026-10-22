# 内存回退与多实例边界（S6 收口）

生成：2026-09-14（Asia/Shanghai）　适用：`de13e90` 之后的工作树
范围：知识图谱、开放平台应用注册、用户表、长期记忆、用户画像、请求队列、`/health/details`
本文只描述**已在源码中生效**的行为；未接线的部分单列在文末，不写成已完成。

## 1. 决策：缺依赖时拒启，而不是统一只读

生产环境（`APP_ENV=production|prod`）缺持久化依赖时，按子系统分两类处理，而不是一刀切：

| 子系统 | 缺持久化存储时的处置 | 理由 |
| --- | --- | --- |
| 用户表（`app/common/auth.py`） | **拒绝启动**（`enforce_production_storage_guard()` 抛 `RuntimeError`） | 登录本身是写路径（建用户、SSO 同步、改密）。用户表在进程内存里时，两个 worker 会各自认定不同的用户集，重启后连管理员都不剩；只保留读没有可用形态，退化服务比不服务更危险 |
| 长期记忆、用户画像 | **只读保护**（写返回 `False`，读继续） | 只丢失增量派生状态，不影响已入库文档的问答；可观测、可通过补库恢复，不必回滚发布 |
| 知识图谱关系 | **只读保护**（写抛 `ProductionReadOnlyProtection`） | 关系是"带来源断言"，写进进程字典会让不同实例给出不同答案；宁可拒绝写入也不给出看似成功的假象 |
| 开放平台应用注册表 | **只读保护**（注册返回 503） | 注册凭据只活在一个进程里等于没有注册；跨实例不可用、重启即丢 |
| 请求队列 | **保持 fail-closed**（`ReliableQueue` 无 Redis 直接 503） | 现网行为已正确，只修正健康检查里的错误上报 |

开发环境（默认）不变：仍允许进程内字典，方便离线开发与测试，但 `storage_mode` 会如实标成 `memory`，不再伪装成正常持久化。

## 2. 子系统存储模式

`storage_mode` 取值：`postgres` / `json` / `redis` / `memory` / `unavailable`。
每个子系统同时上报 `durable`（重启是否保留）、`shared_across_processes`（多实例是否可见）、`protection`（`none` / `read_only` / `refuse_start` / `disabled`）、`detail`（人读原因）。

| 子系统 | 上报函数 | 持久后端 | 生产缺后端时 | 开发默认 |
| --- | --- | --- | --- | --- |
| `users` | `app.common.auth.user_storage_state` | `postgres` | `unavailable` + `refuse_start` | `memory` |
| `memories` | `app.memory.long_term.memory_storage_state` | `postgres` | `unavailable` + `read_only` | `memory` |
| `user_profiles` | `app.memory.profile.profile_storage_state` | `postgres` | `unavailable` + `read_only` | `memory` |
| `knowledge_graph` | `app.knowledge_graph.service.knowledge_graph_storage_state` | `json`（`KNOWLEDGE_GRAPH_STORE_PATH`） | `unavailable` + `read_only` | `memory` |
| `open_platform_apps` | `app.common.open_platform.app_registry_storage_state` | `json`（`OPEN_PLATFORM_APP_STORE_PATH`） | `unavailable` + `read_only` | `memory` |
| `queue` | `app.common.monitoring.queue_storage_state` | `redis`（`REDIS_URL`） | `unavailable` + `disabled` | 同生产口径 |

### 新增环境变量

| 变量 | 作用 | 未设置时 |
| --- | --- | --- |
| `KNOWLEDGE_GRAPH_STORE_PATH` | 知识图谱关系的 JSON 持久文件（collection `knowledge_graph_relations`） | 开发：进程字典；生产：写被拒 |
| `OPEN_PLATFORM_APP_STORE_PATH` | 开放平台应用注册表 JSON 文件（collection `open_platform_apps`，含签名密钥） | 开发：进程字典；生产：注册返回 503 |

两者都复用 `app/storage/persistence.py:JsonPersistenceAdapter`（原子写 + `os.replace`），不新造存储层。文件落在数据卷上（例：`/app/data/knowledge_graph.json`），因此同一台机器上的多个 API 进程读写同一份，重启不丢。

## 3. 多实例边界的诚实结论

- 已跨实例：`users`/`memories`/`user_profiles`（PostgreSQL）、`knowledge_graph`/`open_platform_apps`（配置 JSON store 后）、`queue`（Redis + ACK/租约/死信）。
- 仍是进程内单例（配置 store 后不再受影响，未配置时只读保护）：`KnowledgeGraph._relations` 缓存、`open_platform._APP_REGISTRY` 缓存、`auth._MEM_USERS`、`long_term._MEMORY`、`profile._MEM_PROFILES`。`storage_mode=memory` 时 `shared_across_processes=false`，`/health/details` 的 `storage.single_instance_only` 会逐个列出。
- 已知残余风险（不在本片范围，见 §6）：`app/common/cache.py:get_redis()` 在无 `REDIS_URL` 时静默换 `fakeredis`/进程内 `_MemoryRedis`，限流与缓存在多实例下各自为政；`app/rag/retriever.py` 的 Chroma 与 BM25 索引仍是每进程一份。

## 4. `/health/details`

`app/common/monitoring.py:build_health_snapshot` 新增 `environment`、`storage`、`problems` 三个字段，并修正 `queue`。生产口径：只要存在非持久子系统或未就绪依赖，`status` 由 `ok` 变 `degraded`，`problems` 给出稳定 code：

`users_store_not_persistent`、`memories_read_only`、`user_profiles_read_only`、`knowledge_graph_read_only`、`open_platform_apps_read_only`、`queue_unavailable`、`postgres_<status>`、`redis_<status>`、`ollama_<status>`。

前端渲染契约见同目录 `health-details-frontend-contract.md`。

## 5. 开放平台注册面

- `POST /api/v1/apps`：`users:manage`（admin）+ 强制审计（`open_platform:app_register`，允许/拒绝都记），返回一次性 `secret`；参数非法 400；注册表不可持久化 503（detail 带原因 code）。
- `GET /api/v1/apps`：同权限，返回脱敏列表（无 `secret`）+ `storage` 状态。
- 路由定义在 `app/api/v1/open_platform.py:apps_router`，**需要主 thread 在 `app/main.py` 增加一行挂载**：`app.include_router(open_platform.apps_router, prefix="/api/v1")`。该片不改 `app/main.py`。
- `app/common/open_platform.py:register_application()` 仍保留（内部/测试用），但生产环境下无 store 时抛 `ProductionReadOnlyProtection`，不再静默写内存。
- 该路径**不在** `PUBLIC_PATHS`、也不在 `AuthMiddleware` 的 open 白名单里：未登录 401、非 admin 403，默认拒绝语义未放宽。

## 6. 死代码

删除 `app/common/queue.py`（旧 BLPOP 版队列）。判据：`Select-String` 全仓复核（`app/`、`deploy/`、`tests/`、`scripts/`、`docs/`）后仅剩 `tests/test_reliable_queue_request_path.py` 引用，而该引用本身就是"断言遗留队列不能被调用"。保留一个 deprecated 壳没有价值：它依赖 `app/common/cache.get_redis()`，会把超载请求塞进一个没有 worker 会消费的进程内假队列，还对客户端返回 `queued`。`tests/test_reliable_queue_request_path.py` 改为只测 `ReliableQueue`（幂等键、SSE `queued` 帧、无 Redis 时 503 fail-closed）。

## 7. 待接线与未验证

- **未接线**：`enforce_production_storage_guard()` 目前没有被 FastAPI 启动钩子调用（`app/main.py` 归 S3）。在它挂线之前，生产无库实例仍会启动，但：`/health/details` 报 `degraded` 且 `users` 为 `refuse_start`，且 `auth` 在运行时逐请求拒绝身份操作（默认拒绝），因此不会静默放行。
- **未验证**：本文所有结论来自离线单测与代码核对（`tests/test_deployment_guards.py`）。**没有**在容器、PostgreSQL、Redis 或 Ollama 实跑验证，也不声称已通过生产验收。
- 建议的补库顺序：`DATABASE_URL` + `scripts/migrate.py` → 配 `KNOWLEDGE_GRAPH_STORE_PATH`/`OPEN_PLATFORM_APP_STORE_PATH` → 配 `REDIS_URL` → 复查 `/health/details` 的 `problems` 清空。
