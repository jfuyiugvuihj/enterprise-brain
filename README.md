# 企业智脑

私有化部署的企业 AI 智能分析平台。数据只留在客户自己的服务器上。

## 一条命令启动

先配置一次部署环境（必需的密钥缺失时 Compose 会拒绝启动，不会退回默认口令）。
容器只读 `deploy/.env.server`；仓库根的 `.env` 只服务本地直跑，两者转义规则不同：

```bash
cp deploy/.env.server.example deploy/.env.server   # 填写 JWT、数据库、Redis 口令与 CORS 白名单
python scripts/check_deployment_env.py deploy/.env.server   # 预检：字面 $ 必须写成 $$
docker compose --env-file deploy/.env.server up --build -d
```

启动后访问：

- `http://localhost/` — 前端与 API 的统一入口（Nginx）
- `http://127.0.0.1:8001/api/v1/health` — 后端真实健康检查
- `http://localhost/api/v1/health` — 经代理的同一健康检查

栈内服务：PostgreSQL(+PGVector)、Redis(带密码)、本机 Ollama、一次性 `migrate`、
`backend`(API)、`worker`(队列)、`scheduler`(唯一定时任务进程)、`frontend`(Nginx)。

服务器加固层（日志轮转、掉电自启、连接上限）叠加同一份 `deploy/.env.server`：

```bash
docker compose --env-file deploy/.env.server -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --build
```

## 交付物

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `deploy/`（Nginx 片段、服务器叠加层、Worker 与 Scheduler 入口、服务器说明）

## 量化价值

- 单机一键拉起 API + Worker + Scheduler + Redis + PostgreSQL/PGVector + 前端
- 迁移是显式的一次性步骤，运行时不再建表，服务在迁移成功后才启动
- 客户上传与生成文件只存在于命名卷与数据库里，重建镜像不会丢失或外泄
- 新环境部署从“手工装依赖”降为“拉镜像 + 启动服务”

## 不使用 Docker 时

本地直跑读仓库根的 `.env`（`cp .env.example .env`），python-dotenv 按字面解析，
不需要 `$$` 转义；这份文件不会被 Compose 读取。

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
uv run python deploy/queue_worker.py
uv run python deploy/scheduler.py     # 生产 APP_ENV 下 API 不再内嵌调度器，需要单独起一个
```