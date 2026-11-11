# R470 · 服务重启演练第一次实测（V2 验收目标 #21「会话、产物、数据和文档重启后可恢复」）

- 日期：2026-09-29 · 执行与验收：总控线（本席）· 施工：无（这是实测单，不是代码单）
- 主树基点：`6fb2fed`（含 R413 / R463 / R465 / R469）· 镜像：`enterprise-brain:local`（本席未重建镜像，容器用的还是 09-28 那版）
- 纪律：只读普查＋应用进程重启；**没有**改任何一行数据、没有清卷、没有重建镜像、没有改 `deploy/.env.server`
- 🔴 下面那张表由 `scripts/r470_restart_diff.py::render_readout()` 生成，改数请重跑 `--sync`，不许手写（`--check` 逐字节核对）

## 一、为什么到今天我才有这一格

09-27 那张 V2 缺口复评对 #21 的裁定是「半」，缺的一格写得明明白白：「此外本轮**没有**做任何重启实测（禁起服务），
故只报静态态」。也就是说 #21 一直靠「表结构在、列在、迁移在」这套静态理由推定通过——本仓入规第七次要杀的正是这种推定。
今天 Docker Desktop 自己起来了（引擎 `29.7.2`，栈里 PG/Redis/Ollama 都 healthy），这一格才第一次真量。

## 二、量具与两形

探针：`%TEMP%\r470_probe.py`（上一席留在纸面的那枚，本席现读 3303 B）——**必须在容器里跑**，宿主 5432 上有一枚野 PG，
从宿主直连会读到假库；且它走 `app.db.connection` 真源取连接配置，自己不拼 URL。本席把它 `docker cp` 进
`enterprise-brain-backend-1:/tmp/` 后用 `/app/.venv/bin/python` 跑（容器里没有可用的 `/usr/local/bin/python`，这条在册）。

读腿探针：`/tmp/r470_api.py`——`POST /api/v1/login` 用 `evalbot` + `EB_EVAL_PASSWORD`（跑分账号定档口令），
再 `GET /api/v1/sessions` 数条数。🔴 登录正路是 `/api/v1/login`（runbook :177，`PUBLIC_PATHS` 免鉴权），
本席一开始拿 `/auth/login` 试了三对口令全 401，那是我用错路径与账号配对，不是凭据坏了——这条记下来免得下一班当成新缺陷。

两形（都只动应用三格 `backend worker scheduler`，PG/Redis/Ollama 不碰）：

1. **① stop/start**：`docker compose --env-file deploy/.env.server stop backend worker scheduler`（进程死透，10:16:14）
   再 `... up -d backend worker scheduler`（10:16:29 起，26 s 后 `healthy`）。
2. **② --force-recreate**：`docker compose --env-file deploy/.env.server up -d --force-recreate backend worker scheduler`
   （容器整体替换，`/tmp` 随容器消失，这一形更接近客户侧「重新部署一次」）。

原始读数六份落盘在 `docs/perf/raw/r470-2026-09-29/`：三形普查 + 三形读腿。
`probe-before-stop-start.json` `40F4C052B8BFAE2C` · 两份 after `6DD0D524BF725878`（逐字节相同）· 三份 api `103C408F6C8E83E1`（逐字节相同）。

## 三、生成表

<!-- R470-TABLE-BEGIN -->
<!-- 本表由 scripts/r470_restart_diff.py::render_readout() 生成，改数请重跑，不许手写。 -->

| 形 | 表枚数 | 行数 | 动了的表 | 主键漂动 | 文件层 | 会话读腿 | 判定 |
|---|---|---|---|---|---|---|---|
| ① stop/start（进程死透） | 35 -> 35 | 146115 -> 146118 | audit_events +3 | 无 | 等值=True | 656 条 | PASS |
| ② --force-recreate（容器替换） | 35 -> 35 | 146115 -> 146118 | audit_events +3 | 无 | 等值=True | 656 条 | PASS |

会话读腿三形读数：[(True, 656), (True, 656), (True, 656)]
文件层基线：{"data_dir": 9, "documents": 101, "static_charts": 82}
redis 基线/末形：{"before": {"dbsize": 109, "ping": true}, "after": {"dbsize": 109, "ping": true}}

问题清单：空
<!-- R470-TABLE-END -->


## 四、判定与它**没证**的东西

判据：核心业务数据（会话、产物、数据、文档）在两形重启后既在库里、也被应用读得回来。⇒ **本单这一格 PASS**，
且它是 #21 第一次有实测，不是把静态推定抄成通过。

🔴 下面这些**没有**被这一格证明，下一班不许顺手扩大解释：

- **没证数据库容器换代后数据还在**：PG 容器全程没重启，卷存活这件事本单没测。要测得 `--force-recreate postgres`，
  风险量级不同，属客户交付演练那一手，本单不越权做。
- **没证清卷后能恢复**：`down -v` 是灾难恢复，不属 #21 的判据。
- **没证半途任务续跑**：worker 在飞任务的重启语义是 R37 判据③（队列失败有终态与原因码）那一格，仍欠真机读数。
- **没证 `GET /sessions` 的可见面过滤对不对**：库里 `sessions` 1020 行，API 对 `evalbot` 回 656 条——本单只验「三形逐枚相等」，
  那 364 条之差是不是 owner/部门过滤的正确行为，是 R78/R35 那一族的账，本单不判、也不许当成本单的附带结论。

两处预期内的读数变化，写清免得被当成丢数据：

- `audit_events` 2426 → 2429（+3）：审计面是 append-only，本演练三次登录各写一条。**只有这一张表被允许变**，
  这一条写死在量具的 `ALLOWED_GROWTH` 里：别的表行数一动就 FAIL，`audit_events` 少了也 FAIL（append-only 不会缩）。
- `redis dbsize` 109 → 109：缓存不是数据源，这一格不动才是对的（动了说明有东西把 Redis 当持久层写）。

## 五、复算命令（全部为本席原文）

```powershell
cd C:\Users\fengx\PycharmProjects\企业智脑
docker cp "$env:TEMP\r470_probe.py" enterprise-brain-backend-1:/tmp/r470_probe.py
docker exec -e PYTHONPATH=/app -w /app -i enterprise-brain-backend-1 /app/.venv/bin/python /tmp/r470_probe.py
docker cp "$env:TEMP\r470_api.py" enterprise-brain-backend-1:/tmp/r470_api.py
docker exec -i enterprise-brain-backend-1 /app/.venv/bin/python /tmp/r470_api.py
docker compose --env-file deploy/.env.server stop backend worker scheduler
docker compose --env-file deploy/.env.server up -d backend worker scheduler
docker compose --env-file deploy/.env.server up -d --force-recreate backend worker scheduler
& .\.venv\Scripts\python.exe scripts/r470_restart_diff.py            # 出表 + RESULT
& .\.venv\Scripts\python.exe scripts/r470_restart_diff.py --check      # 盘上那张表 == 再生件
```

注意 `-e PYTHONPATH=/app`：容器里 `python /tmp/x.py` 的 `sys.path[0]` 是 `/tmp`，不带它会 `ModuleNotFoundError: app`；
`-w /app` 单独用不管事（本席踩过，两次）。

