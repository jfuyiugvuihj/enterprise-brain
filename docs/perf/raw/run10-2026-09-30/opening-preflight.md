# run10 开窗前置·原始读数（R513 执行员·2026-09-30）

本件只记原文读数与命令，不记判词。判词在 `docs/testing/run10-readout-2026-09-30.md`。
派工原文：`.tmpfix/r513_dispatch.txt`（含增补一到**增补七**）。

## 0 基点

| 现取 | 命令原文 | 读数 |
|---|---|---|
| 主树 HEAD | `git -C 企业智脑 rev-parse --short HEAD` | `4376648`（branch `codex/data-file-catalog`） |
| 主树 dirty | `git -C 企业智脑 status --porcelain \| Measure-Object -Line` | **22 行**（chroma_db + docs/testing×3 + tests×17 + 未跟踪 .tmpfix 等）＝本窗开窗时**非静默** |
| 跑分树追平 | `git -C be-eval95 merge --ff-only 4376648` | `bcad2a8 → 4376648`，追平后 `status --porcelain` = 空 |
| 跑分树 HEAD | `git -C be-eval95 rev-parse --short HEAD` | `4376648`，dirty=0，零 commit／零 push／未新建分支 |

## 1 P-20 开窗前置闸（跑分树现取）

命令：`.\.venv\Scripts\python.exe scripts\r530_run10_window_preflight.py --need-minutes 300`（12:43:44 +08:00）

```
[P-20] PASS provenance     镜像携带的文件与 HEAD 一致
[P-20] FAIL answer_cache   量具没跑成 rc=2（rc=2 永远不算通过）
[P-20] PASS keep_awake     pid=51320 剩余 606 min >= 需要 300.0 min
[P-20] FAIL gpu_apps       外来进程占着 GPU，A(1) 的 p95 时延读数不可采信：pid=13640 exe=C:\Users\fengx\anaconda3\python.exe
[P-20] FAIL foreign_python 仓库外解释器在跑常驻脚本，先归零再开窗：pid=13640 cmd="C:\Users\fengx\anaconda3\python.exe" train.py --config conf
[P-20] PASS eval_tree      be-eval95 干净且可 --ff-only 追平
[P-20] FAIL env_flags      deploy/.env.server 缺开关：VECTOR_DUAL_WRITE=<未设>, REPORT_LANE_VIA_QUEUE=<未设>
[P-20] verdict: FAIL（4 格 FAIL）
RC=1
```

开窗裁定依据＝**增补七**（P-20 两格 FAIL 照样开窗，A① 记「污染窗、不采信」）。另外两格 FAIL 逐枚复查如下，**都不是事实红，是量具找错了树**：

- `answer_cache` rc=2：`deploy/.env.server` 是 gitignored，跑分树里没有该文件 ⇒ 取不到 `REDIS_PASSWORD`。按量具自己的 `--repo-root` 口径重跑：
  `..\企业智脑\.venv\Scripts\python.exe scripts\eval_window_answer_cache_gate.py --check --repo-root C:\Users\fengx\PycharmProjects\企业智脑`

  ```
  [P-18] 模式=check（只判不清） · 口令=REDIS_PASSWORD len=32 取自 C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server · 容器=enterprise-brain-redis-1
  [P-18] PING = PONG ⇒ 这条命令本身跑成了，接下来的计数才算数
  [P-18] answer:* = 0 枚（dbsize=87）
  [P-18] 旁证·其它键族 清前 = enterprise-brain=87
  [P-18] --check：0 枚，而且是 PING 过之后读到的 0 ⇒ 可以开窗
  [P-18] verdict: PASS
  == rc=0
  ```

- `env_flags`：同一枚 gitignore 的连带（P-20 把 `ROOT/deploy/.env.server` 当作自己的树）。直接现取主树那份：
  `Select-String -Path 企业智脑\deploy\.env.server -Pattern 'REPORT_LANE_VIA_QUEUE|VECTOR_DUAL_WRITE|INDEX_BACKEND'`

  ```
  56: VECTOR_DUAL_WRITE=on
  71: REPORT_LANE_VIA_QUEUE=on
  （INDEX_BACKEND 该文件里没有这一行 ⇒ 读路径仍在 Chroma 遗留件，翻默认是业主动作）
  ```

  容器侧在位与否不是本窗现取（窗内禁动容器），但 provenance 格已交 `MATCH 4376648`，且 compose 的 `project.environment_file` 现取就是主树那份（见 §5）。

## 2 🔴 keep-awake 这一格：P-20 的 606 min 是假数（量具有 +8 h 时区缺陷）

P-20 `keep_awake` 用 `(Get-Process -Id <pid>).StartTime.Ticks` 换算 epoch，而 `StartTime` 是**本地时间**，减掉 1601-01-01 之后被当成 UTC ⇒ 本机（Asia/Shanghai，UTC+8）**多算 480 min**。现取证（`%TEMP%\evalrun\ka_probe.py`，只读）：

```
now 2026-09-30 12:47:22 epoch=1790743643
pid=53768 start_local=07:50:36 minutes=420.0 | tool_epoch=1790754636 true_epoch=1790725836 | tool_left=603 min true_left=123 min | expires=09-30 14:50:36
pid=51320 start_local=07:50:36 minutes=420.0 | tool_epoch=1790754636 true_epoch=1790725836 | tool_left=603 min true_left=123 min | expires=09-30 14:50:36
```

⇒ 现场那两枚 `.tmpfix\keep_awake.py shift6-window 420`（pid 53768／51320）**14:50:36 到期**，只剩 ~2 h，而相 1＋相 2 估 2.5–3 h 以上。增补四 D)「约 14:50 到期」是**对的**；增补五据 P-20 把这句判为「作废」，读的是被 +480 min 污染的那个数。
后果：本窗会跑过 14:50，而 AC 睡眠 0x0 在本机**已被两次实测证明不足以防睡**（runbook §17 订正二前的 #77 案），所以按派工原文第 3 步补上在册临时锁：

```
Start-Process ..\企业智脑\.venv\Scripts\python.exe scripts\window_keep_awake.py --loop --interval 240   （12:50 起，常驻，PID=53144）
python scripts\window_keep_awake.py --check
  [P-19] stamp=C:\Users\fengx\AppData\Local\Temp\enterprise-brain-window-keep-awake.txt
  [P-19] 上一次调用交回 PREV=0x80000000（非 0＝成功），6 s 前续过，PID=53144
  [P-19] verdict: PASS
  rc=0
```

该件按构造**一行电源设置都不改**（只调 `SetThreadExecutionState(ES_CONTINUOUS|ES_SYSTEM_REQUIRED|ES_DISPLAY_REQUIRED)`，进程退出即释放）。`powercfg` 本窗一个字没动。量具缺陷只报不改（禁令：不许改 `scripts/` 任何量具）。

## 3 P-8 镜像溯源

`python scripts\check_image_provenance.py --expect-container`（跑分树）

```
tree          : 4376648 (build inputs clean)
image label   : org.opencontainers.image.revision=4376648
BUILD_INFO    : revision=4376648 | built_at=unknown
verdict       : MATCH -- image revision equals 4376648
provenance gate: PASS      rc=0
```

开窗三步（build migrate → up -d --no-build → P-8）由总控做完，本执行员未 build／未 restart／未 recreate。

## 4 P-18 / 凭据 / P-14

| 格 | 命令原文 | 读数 | rc |
|---|---|---|---|
| 凭据 P-7 | `python scripts\seed_workspace.py --check --env-file C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server` | `manifest workspace-seed.json: documents=100 datasets=1` ／ `server http://127.0.0.1:8001: 100 indexed documents, 1 datasets` ／ `plan 96 already in, 0 to upload` ／ `WARN on the server but not on disk ... browser_acceptance_policy.txt, 六级作文模板.docx, 深度学习入门：基于Python的理论与实现.pdf, 深度学习技术栈学习路线.pdf` ／ `owner dataowner present department=财务部` ／ `RESULT ok documents=100 datasets=1 owners=1` | 0 |
| P-14 端点 | `Select-String %TEMP%\evalrun\eval_transport_ask_v2.py -Pattern 'api/v1/ask','api/v1/chat'` | 真发请求只有一枚：`:872 with _open("/api/v1/ask", payload)`；其余 `api/v1/chat.py` 命中全是注释里的产品坐标（:8/:25/:132/:208/:212…）。⇒ 打的是 `/ask`，没走旧 `/chat` | — |
| 跑分账号可见语料 | 只读探针 `%TEMP%\evalrun\smoke_nologin.py`（`POST /api/v1/login` + `GET /api/v1/documents`，零模型调用） | `login ok · evalbot sees /documents n= 100`；`health= {'status': 'ok'}` | 0 |

语料形状（P-17 抬头口径）：盘上 `Get-ChildItem documents -File` = **97 枚**，`seed_workspace --check` 在册 **100 枚**，差的 4 枚盘上没有文件（上表 WARN 逐枚点名）；与增补（09-29）那笔一致，不去「补齐」。

## 5 被测栈现场

```
docker inspect enterprise-brain-backend-1 --format '{{json .HostConfig.Binds}}'
["enterprise-brain_vectordb:/app/chroma_db:rw","enterprise-brain_appdata:/app/data:rw","enterprise-brain_documents:/app/documents:rw","enterprise-brain_applogs:/app/logs:rw","enterprise-brain_generated:/app/static:rw"]
labels: com.docker.compose.project=enterprise-brain
        com.docker.compose.project.config_files=C:\Users\fengx\PycharmProjects\企业智脑\docker-compose.yml
        com.docker.compose.project.environment_file=C:\Users\fengx\PycharmProjects\企业智脑\deploy\.env.server
        com.docker.compose.project.working_dir=C:\Users\fengx\PycharmProjects\企业智脑
        org.opencontainers.image.revision=4376648
```

⇒ 生产语料在 named volume（`enterprise-brain_documents`），宿主 `documents/` 只是 P-17 的留档面；被测栈的 env 真源＝主树 `deploy/.env.server`。

```
docker ps --format {{.Names}}\t{{.Status}}   （12:49:4x）
enterprise-brain-worker-1    Up 8 minutes (healthy)
enterprise-brain-backend-1   Up 8 minutes (healthy)
enterprise-brain-scheduler-1 Up 8 minutes (healthy)
enterprise-brain-frontend-1  Up 14 hours
enterprise-brain-redis-1     Up 25 hours (healthy)
enterprise-brain-postgres-1  Up 25 hours (healthy)
enterprise-brain-ollama-1    Up 25 hours (healthy)
```

## 6 nvidia-smi 采样（污染可证：开窗前／相 1 中段／收窗后）

### 采样 #1 开窗前 2026-09-30 12:43:44 +08:00

```
$ nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv
pid, used_gpu_memory [MiB], process_name
13640, [N/A], C:\Users\fengx\anaconda3\python.exe
---
$ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
memory.used [MiB], memory.total [MiB], utilization.gpu [%]
2993 MiB, 8188 MiB, 99 %
```

外来进程归属现取（`Get-CimInstance Win32_Process`，12:47:22）：pid **13640** 起于 **12:40:50**，命令行
`"C:\Users\fengx\anaconda3\python.exe" train.py --config configs/_local_fog6.yaml --device cuda --resume`，
外加 4 枚 `--multiprocessing-fork` 子工（pid 55344／33432／58220／33648，12:40:57–12:41:05，parent_pid=13640）。
与增补七点名的 12:28 那枚 pid 20144 已是**换过的第二枚**（业主链式冒烟，配置名 `_local_fog6.yaml`）；keep-awake 的两枚 python（53768／51320）与本项目无关的路径是 `anaconda3`，但命令行指向 `.tmpfix\keep_awake.py`，属在册常驻。

另起一枚低频采样器（`%TEMP%\evalrun\gpu_sampler.ps1`，**PID=23680**，每 120 s 一行 → `%TEMP%\evalrun\gpu_sampler.log`）用来定「外来进程消失的那一刻」，为的是把窗切成污染期／干净期，不参与任何时延读数。

## 7 相 1 点火

| 现取 | 值 |
|---|---|
| 点火时刻 | `2026-09-30 12:50:25 +08:00`（`%TEMP%\evalrun\phase1_start.txt`） |
| 采集进程 | PID **49768**（`Start-Process`，解释器＝主树 venv `...企业智脑\.venv\Scripts\python.exe`，P-2 纪律；工作目录＝跑分树） |
| 命令 | `python scripts\collect_evaluation_answers.py --transport eval_transport_ask_v2:transport --fixture tests\fixtures\business_evaluation_100.jsonl --output %TEMP%\evalrun\answers-real.jsonl` |
| stdout / stderr | `%TEMP%\evalrun\run10-phase1.out` / `run10-phase1.err`（重定向，不占控制台） |
| 进程 env（只记名与值来源，不抄口令） | `EVAL_BASE_URL=http://127.0.0.1:8001`（宿主直连后端，绕过 nginx，与 run9 同形）／`EVAL_USERNAME=evalbot`／`EVAL_PASSWORD=取自 deploy\.env.server:EB_EVAL_PASSWORD`／`PYTHONPATH=%TEMP%\evalrun`／`EVAL_SIDECAR=%TEMP%\evalrun\sidecar-run10.jsonl`／`EVAL_FRAME_LEDGER=%TEMP%\evalrun\sidecar-run10-frames.jsonl`／`PYTHONIOENCODING=utf-8` |
| 相 1 开关态 | `EVAL_DECLARE_LANE_TIER` **不设**（`Remove-Item Env:\...` 显式删除）⇒ 12+8 枚报告题走同步道 |
| 量具件 | `scripts\eval_transport_ask_v2.py`（100114 bytes，树内件）复制为 `%TEMP%\evalrun\eval_transport_ask_v2.py` 供 `PYTHONPATH` 导入 |
| 未跑的前置 | 门基线 `python scripts/run_gate.py`（原文第 2 步）**没跑**——被本窗「不跑 pytest／run_gate.py」硬禁覆盖，按编号靠后者为准；此格记「没量到」 |