# 服务器部署

统一拓扑在仓库根目录的 `docker-compose.yml`：PostgreSQL(+PGVector)、Redis(带密码)、
本机 Ollama、迁移一次性任务、API、队列 Worker、独立 Scheduler、Nginx+前端。

## 启动

```bash
cp .env.server.example .env.server   # 填写 JWT、数据库、Redis 口令与 CORS 白名单
python ../scripts/check_deployment_env.py .env.server
docker compose --env-file deploy/.env.server config          # 只做插值校验，不构建
docker compose --env-file deploy/.env.server build migrate   # 应用镜像，单独一次
docker compose --env-file deploy/.env.server build frontend  # 前端镜像，单独一次
docker compose --env-file deploy/.env.server up -d --wait --no-build
```

**构建必须一个服务一次。** Docker Desktop 29.7 + Compose 5.5 在同一次调用里构建两个镜像时，
会让自己的 BuildKit 会话元数据损坏，报
`failed to dial gRPC ... header key "x-docker-expose-session-sharedkey" contains value with
non-printable ASCII characters`，在任何一层被读取之前就失败。这不是 Dockerfile 的问题，
`COMPOSE_BAKE=false` 也绕不过去；逐服务构建在实测中连续成功。因此启动命令里也不要再用
`up -d --build`：把构建和启动分开，构建证据才立得住。

国内网络下构建阶段还需要镜像源，`deploy/.env.server` 里的 `APT_MIRROR` / `PIP_INDEX_URL`
会被两个 `build:` 块读取（默认留空 = 走上游源）。应用镜像的 `uv sync` 已挂
`--mount=type=cache,target=/root/.cache/uv`，改代码重建不会重下依赖。
09-19 起依赖层与源码层已经分开：`uv sync` 排在源码 COPY 之前，并且取消了 `chown -R /app`
（那一层实测是 5.78 GB 的 copy-up，取消后镜像虚体积从 18.4 GB 降到 9.6 GB）。所以改一行代码
重建只要秒级——本机实测全层 CACHED 用时 **1.5 s**；换 `uv.lock` 才会重造那 ~5.8 GB 的依赖层。

重建时顺手把「这一版镜像是从哪个 commit 建的」写进镜像，否则事后无法证明容器里跑的是哪版代码：

```powershell
$env:GIT_SHA  = (git rev-parse --short HEAD)        # 工作树不干净就自己加 "+dirty"
$env:BUILT_AT = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
docker compose --env-file deploy/.env.server build migrate
docker compose --env-file deploy/.env.server up -d --wait --no-build backend worker scheduler
python scripts/check_image_provenance.py            # P-8：镜像自报来源，不等即判死
```

`check_image_provenance.py` 取代了「拿镜像 `Created`（UTC）去比 commit 时间（本地）」的老办法。
它只在两种情况下放行：标签等于被测 rev；或 rev 是 HEAD 的祖先、且中间那些提交**只动了镜像不携带的文件**
（文档、测试）。工作树脏时一律回落到逐文件 sha256 比对，不接受任何 commit id 的说辞。

### 首个管理员账号

平台不内置任何账号。生产拓扑下 `migrations/0003` 建出的 `users` 表是空的，而后端在
**首次连接**时用 `AUTH_USERNAME` + `AUTH_PASSWORD_HASH` 播种首个管理员：只在表为空时
写入，表非空即不再触碰（因此被运维删除的账号不会被复活），三个常驻进程同时探测也只会有
一行落地。两者必须成对给出，缺任何一个都拒绝建号；上面的预检会在构建之前就把缺项报出来，
否则现象是「部署完成但没有任何人登录得进去，且只报 401」。

生成 bcrypt 哈希（明文口令不要落进文件、命令历史或日志）：

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'<你的口令>', bcrypt.gensalt()).decode())"
```

输出里的每一个 `$` 都要写成 `$$` 再填进 `deploy/.env.server`：

```
AUTH_USERNAME=<管理员用户名>
AUTH_PASSWORD_HASH=$$2b$$12$$<哈希正文>
AUTH_DEPARTMENT=<可选：该账号的部门>
```

`AUTH_DEPARTMENT` **建议必填**。留空的账号仍能登录、管用户，并能检索**任意部门**的文档——
检索链对管理员不设部门条件（`app/rag/filters.py` 的 e2 裁定，跨部门检索在审计里单独记
`administrator_scope`，不记成普通部门命中）。它仍会被拒的两条是数据集归属与成果归属
（`app/storage/datasets.py`、`app/api/v1/data.py`，都是 `403 department_scope_required`；
`3e35481` 起 `/chart`、`/export` 不再以 HTTP 200 回错误串）。还有一条更疼的：它上传的文档
部门为空，而检索谓词要求部门精确匹配，所以**除管理员外任何人都找不到它**，界面却会显示上传
成功。留空时预检会打一行 `warn`（不阻断启动），因为另一条合法路线是登录后用
`POST /api/v1/users` 建一个带部门的账号做日常使用。
部门不能事后修改（`PUT /api/v1/profile` 写的是用户画像，不是 `users.department`），换部门
只能重建账号。

用这个口令登录之后，应立刻通过 `PUT /api/v1/users/password` 改密。

任何必需的密钥缺失时 Compose 会直接拒绝启动，不会退回默认口令。

**`deploy/.env.server` 是唯一被容器读取的环境文件**，仓库根的 `.env` 只用于本地直跑。
两者的转义规则不同：Compose 会对 env 文件做变量替换，所以这里的字面 `$` 必须写成 `$$`
（例如 bcrypt 的 `AUTH_PASSWORD_HASH`）；而 python-dotenv 会把 `$$` 原样交给应用。
写错不会报错，只会让登录静默失效，因此启动前必须跑一次上面的预检命令。

### 上传目录的卷属主（老卷升级）

命名卷只在**创建时**从镜像里的同名目录继承属主。若 `documents` 卷是在旧镜像时期建好的，
它是 `root:root`，而容器以 uid 10001 运行，于是每一次 `POST /api/v1/upload` 都返回 500
（写临时文件 `PermissionError`），而健康检查全绿。新装不受影响（`Dockerfile` 已创建并 chown
`/app/documents`）；已有环境升级时执行一次：

```bash
docker run --rm --user root --entrypoint chown -v enterprise-brain_documents:/d \
  enterprise-brain:local -R 10001:10001 /d
```

验证不必登录：跑 `python scripts/verify_container_stack.py`，看
「the API process can write into every mounted volume」一项——它以应用真实的 uid 在每个卷
里写入并删除一个探针文件。

## 服务器加固层（可选）

日志轮转、掉电自启与 PostgreSQL 连接上限由 `deploy/docker-compose.server.yml` 叠加，
它复用同一份 `deploy/.env.server`：

```bash
docker compose --env-file deploy/.env.server -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --build
```

## 拉模型

第一版只使用本机 Ollama。未显式配置 `LOCAL_MODEL_NAME` 时，平台会从本机模型注册表
发现具备对话能力的模型；发现不到就返回“模型不可用”，不会使用任何内置模型名。

```bash
docker compose exec ollama ollama pull <你的模型标签>
```

## 迁移

`migrate` 是一次性任务，`backend`/`worker`/`scheduler` 都等待它成功退出后才启动。
运行时会话、文档、数据集与执行账本都依赖这些表，禁止用运行时建表替代。

```bash
docker compose run --rm migrate
```

## 备份

```bash
docker compose run --rm backend python scripts/backup_database.py --output /app/data/backups/brain.dump
docker compose run --rm backend python scripts/backup_workspace.py --output /app/data/backups/workspace.zip
```

数据库口令只通过容器环境变量传递，不会出现在命令行或日志里。

## 访问

- `http://你的服务器IP/`
- `http://你的服务器IP/api/v1/health`

## 说明

- Nginx 只代理 `/api/`。图表和报告通过 `/api/v1/artifacts/{id}/content|download`
  经过权限判定后交付，**不存在公开的 `/static/` 交付路径**。
- 客户上传、生成文件、Trace、日志和过渡向量库都挂在命名卷上，重建镜像不会丢失。
- 客户机器只运行这一个栈，数据不出服务器。
- 不部署 Docker 时，用 `deploy/start_workers.sh` 起多个 API 进程，并单独运行一次
  `python deploy/scheduler.py` 作为唯一的调度进程（生产 APP_ENV 下 API 不再内嵌调度器）。


## 离线交付（客户现场通常不放外网）

这台开发机实测：`registry-1.docker.io`、`auth.docker.io`、`production.cloudflare.docker.com`
直连超时、经代理 TLS 失败；`github.com` 与 `dl.delivery.mp.microsoft.com` 同样不可达。
结论是**任何"现场再拉"的假设都不能写进交付方案**，包括 WSL 安装包本身。

离线包至少要带四样：

1. **镜像**：必须在一台能联网的机器上**先构建再导出**。`docker compose pull` 只能拿到
   第三方基础镜像，`enterprise-brain:local` 与 `enterprise-brain-frontend` 是本仓库构建
   出来的，不构建就没有东西可导出。

   ```bash
   # bash / Git Bash
   docker compose --env-file deploy/.env.server build
   docker compose --env-file deploy/.env.server pull --ignore-buildable || true
   docker save -o images.tar $(docker compose --env-file deploy/.env.server config --images | sort -u)
   ```

   ```powershell
   # PowerShell（逐服务构建，原因见"启动"一节）
   docker compose --env-file deploy/.env.server build migrate
   docker compose --env-file deploy/.env.server build frontend
   $images = docker compose --env-file deploy/.env.server config --images | Select-Object -Unique
   docker save -o images.tar $images
   ```

   `config --images` 会为每个使用该镜像的服务各列一行（`enterprise-brain:local` 出现四次
   属于正常现象），所以必须去重。现场用 `docker load -i images.tar` 导入。
2. **镜像版本凭据**：`docker image inspect --format '{{.RepoTags}} {{index .RepoDigests 0}}' <image>`
   的结果存档，交付记录必须到 digest，不能只写 `latest`（计划书 P3 的版本锁定项就落在这里）。
3. **模型**：`ollama pull` 之后打包模型目录（`blobs/` + `manifests/`），现场解压到指定路径并
   **显式设置 `OLLAMA_MODELS`**。这台机器就吃过它的亏：用户环境变量指向空的
   `E:\Ollama\models`，而模型实际在 `~/.ollama/models`，于是服务报"零模型"，看起来像代码故障。
4. **Windows 客户机的 WSL**：GitHub Release 里的 `wsl.<版本>.x64.msi`（**不是**
   `wsl_update_x64.msi`，那个是 Windows 10 旧实现的内核包，24H2 上装它必 `1603`）。
   `msiexec /i wsl.<版本>.x64.msi /quiet` 之后 `C:\Program Files\WSL` 与 `LxssManager` 才存在。


## 基础镜像的获取（实测过的一条路）

2026-09-14 这台开发机的实测结论比"访问不了 Docker Hub"更具体：`registry-1.docker.io`
只有走代理才应答（HTTP 401 属于正常未认证应答），直连超时；而 `auth.docker.io` 在代理
客户端的规则模式下**直连和走代理都拿不到 token**。表现就是 `docker pull` 解析完清单之后
停在 `Pulling fs layer`，容器引擎侧的接收字节数为 0（`wsl -d docker-desktop -u root cat
/proc/net/dev` 两次采样 rx=0），而且这条假死的传输会被后续同一个层 digest 的拉取复用，
不重启引擎就一直卡住。

可用的取镜像方式是**绕开守护进程**，在主机侧按官方 digest 取，再 `docker load`：

```powershell
# 1) 从 Docker Hub 公开 API 取官方 amd64 清单 digest（这个接口不需要 auth.docker.io）
curl.exe -s --noproxy '*' "https://hub.docker.com/v2/repositories/ollama/ollama/tags/latest"
#    -> images[] 里 architecture=amd64 的 digest，例：sha256:aa6f86f01fee264c81f1edd9083ebfb07c8116d95d8bedd1ad470874b66a40b4

# 2) 用带自有认证域（m.daocloud.io）的镜像源按 digest 拉取，导出为 tar
crane.exe pull --platform=linux/amd64 "docker.m.daocloud.io/ollama/ollama@sha256:aa6f86f0..." ollama.tar

# 3) 导入并按 compose 期望的名字打标签
docker load -i ollama.tar
docker tag docker.m.daocloud.io/ollama/ollama:latest ollama/ollama:latest
```

按 digest 拉取的意义：镜像源是第三方，但内容寻址保证拿到的层与发布方公布的 digest 逐字节一致，
所以这仍然是一次可核验的获取，不是"随便从镜像源捞一个"。`crane` 本身来自
`google/go-containerregistry` 发布物，交付时把它和 `docker save` 的 tar 一起放进离线包，
现场只需要 `docker load`。

同一个道理适用于compose 里的其它基础镜像（`pgvector/pgvector:pg16`、`redis:7-alpine`、
`nginx:1.27-alpine`、`node:20-alpine`、`python:3.11-slim`）：现场不要假设能 `pull`，
一律离线包里带 tar。

现场上机顺序：

```text
1) docker load -i images.tar
2) python scripts/check_deployment_env.py deploy/.env.server
3) docker compose --env-file deploy/.env.server up -d --wait
4) python scripts/verify_container_stack.py --skip-build
```

`--skip-build` 在离线场景是必须的：现场既不重建镜像，也没有构建镜像所需的外网。
导出前请确认联网机器与目标机同为 `linux/amd64`，否则镜像层里的原生依赖不匹配。
