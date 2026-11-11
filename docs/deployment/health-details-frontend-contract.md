# `/api/v1/health/details` 前端接口约束（S6）

面向前端 Agent 的**接口契约**，不含前端实现（本切片未改 `frontend/` 任何文件）。
数据源：`app/common/monitoring.py:build_health_snapshot`，路由 `app/api/v1/auth.py:42`（需登录，`GET /api/v1/health/details`）。

## 1. 字段变化

新增：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `environment` | string | 归一化后的 `APP_ENV`，如 `development` / `production` |
| `storage` | object | 存储真值表，见下 |
| `problems` | string[] | 稳定 code 列表；生产非空时 `status` 一定不是 `ok` |

变更（破坏性，需前端跟进）：

- `queue` 不再是 `{"backend": "redis"|"memory"}`。现在是
  `{"backend": "redis"|"none", "storage_mode": "redis"|"unavailable", "durable": bool, "shared_across_processes": bool, "protection": "none"|"disabled", "detail": string}`。
  旧值 `backend: "memory"` **从未反映真实行为**（`ReliableQueue` 无 Redis 直接 503），已删除，请勿再按 `memory` 渲染"本地队列可用"。
- `status` 在 `environment == "production"` 且 `problems` 非空时为 `"degraded"`（此前恒为 `"ok"`）。开发环境行为不变。

未变：`timestamp`、`disk`、`model`、`dependencies`（仍是 `ollama`/`postgres`/`redis` 三键，`status` 可为 `ok`/`degraded`/`unavailable`/`not_configured`）、`performance`。

## 2. `storage` 结构

```json
{
  "subsystems": {
    "users": {"storage_mode": "postgres", "durable": true, "shared_across_processes": true, "protection": "none", "detail": "users table served by PostgreSQL"},
    "memories": {"storage_mode": "memory", "durable": false, "shared_across_processes": false, "protection": "none", "detail": "development in-process dictionary"},
    "user_profiles": {"storage_mode": "postgres", "durable": true, "shared_across_processes": true, "protection": "none", "detail": "user_profiles table served by PostgreSQL"},
    "knowledge_graph": {"storage_mode": "json", "durable": true, "shared_across_processes": true, "protection": "none", "detail": "relations persisted to collection knowledge_graph_relations"},
    "open_platform_apps": {"storage_mode": "unavailable", "durable": false, "shared_across_processes": false, "protection": "read_only", "detail": "OPEN_PLATFORM_APP_STORE_PATH is not configured; application registration is refused"},
    "queue": {"storage_mode": "redis", "durable": true, "shared_across_processes": true, "protection": "none", "backend": "redis", "detail": "REDIS_URL configured"}
  },
  "durable": ["users", "queue"],
  "read_only_protected": ["open_platform_apps"],
  "refuses_startup": [],
  "single_instance_only": ["memories"]
}
```

- `subsystems` 键集合固定为 `queue`、`users`、`memories`、`user_profiles`、`knowledge_graph`、`open_platform_apps`；请**按 key 遍历**而不是写死顺序或数量，后端可能新增子系统。
- `storage_mode` 枚举：`postgres` / `json` / `redis` / `memory` / `unavailable`。
- `protection` 枚举：`none` / `read_only` / `refuse_start` / `disabled`。
- `detail` 是给人看的英文原因串，**不要**用它做逻辑判断，判定请用 `storage_mode` / `durable` / `protection` / `problems`。
- 健康接口不返回任何密钥、连接串或用户名口令（`open_platform_apps` 只有存储状态，应用清单需走 `GET /api/v1/apps`）。

## 3. `problems` code 表

| code | 触发 | 前端建议文案 |
| --- | --- | --- |
| `users_store_not_persistent` | 生产无可用 `users` 表 | 身份存储不可用，实例应停止接收流量 |
| `memories_read_only` / `user_profiles_read_only` | 生产无 `memories`/`user_profiles` 表 | 记忆/画像只读，写入会被拒绝 |
| `knowledge_graph_read_only` / `open_platform_apps_read_only` | 未配置对应 JSON store 或写失败 | 该功能只读，请配置 `KNOWLEDGE_GRAPH_STORE_PATH` / `OPEN_PLATFORM_APP_STORE_PATH` |
| `queue_unavailable` | 无 `REDIS_URL` | 削峰队列不可用，超载请求将返回 503 |
| `postgres_*` / `redis_*` / `ollama_*` | 依赖探测非 `ok`（后缀即探测状态，如 `postgres_not_configured`） | 对应依赖未就绪 |

## 4. 开放平台管理面（前端如需接入）

- `POST /api/v1/apps`：body `{app_name, allowed_actions[], allowed_departments[], max_clearance, description}`；`200` 返回 `{app_id, secret, app_name, storage_mode}`，`secret` **只在该次响应出现一次**，请提示用户当场保存；`401` 未登录、`403` 非 admin、`400` 参数非法（`app_name_required` / `allowed_actions_required`）、`503` 注册表不可持久化（`open_platform_registry_read_only` / `open_platform_store_write_failed`）。
- `GET /api/v1/apps`：返回 `{applications: [{app_id, app_name, allowed_actions, allowed_departments, max_clearance, enabled, description}], storage: {...}}`，不含 `secret`。
- 两接口都要求登录且具备 `users:manage`（admin），调用会被审计（`open_platform:app_register`）。
- 注意：路由需在 `app/main.py` 挂载后才生效（见 `memory-fallback-and-multi-instance-boundaries.md` §5，该片未改 `app/main.py`）。

## 5. 兼容性小结

- 只读展示型页面（磁盘/模型/性能）无需改动。
- 任何把 `status == "ok"` 当作"一切正常"的仪表盘必须改成同时看 `problems`，否则生产 `degraded` 会被渲染成绿色。
- 任何读 `queue.backend == "memory"` 的代码必须删除该分支。
