# run10 相 1 停手时点·原始读数（未跑完，整窗作废）

取证件，不是基线。**这一扇没有产出任何一格的可判读数**：相 1 只跑到 32/105 就按增补七的污染停手线收窗。
本件的全部用途是把「污染可证」这一条落到字节上，交总控用在册量具复算与裁定。

- 点火：2026-09-30 12:50:25 +08:00（PID 49768）
- 停手：2026-09-30 13:31:35 +08:00（`Stop-Process -Id 49768 -Force`）
- 相 1 已跑时长：**41.2 min**；其间外来 CUDA 负载在场 **41.2 min** ⇒ 污染占比 **100%**
- `answers-real.jsonl`：**没落盘**（采集器只在覆盖闸全过时写字节；`Test-Path` = False）⇒ 本轮零伪造产物

## 1 覆盖自证（原始计数，不换算）

| 格 | 读数 |
|---|---|
| fixture 行数 | 105 |
| sidecar 行数 | **32** |
| 帧账行数 | **32** |
| join 缺／多 | 无／无（32 枚逐枚对齐） |
| `kind` 直方图 | `{'ok': 31, 'error_event': 1}` |
| `sentinel=true` | 0 枚 |
| `attempt>1` | 0 枚 |
| `tool_calls_gt0` | **28/32** |
| `evidence_n` 合计 | 101 |
| `answer_chars` 合计 | **13381**（逐枚取值在 sidecar 的 `answer_chars` 列，本件不折算成率） |
| 缺题枚数 | **73**（逐枚点名见 §5） |

件与哈希（sha256 前 16 位，原件在同目录）：`sidecar-run10.jsonl` = `09ba66a44e996d0d` ／ `sidecar-run10-frames.jsonl` = `d0d149f2b7fb1efa`

## 2 超时与未答逐枚点名（相 1 已跑段）

```
id=chat-11  kind=error_event  wall_ms=300065.2  category=多轮对话  answer_chars=10  evidence_n=0
```
⇒ 这是本段唯一一枚非 `ok`，形状＝撞上 `CHAT_REQUEST_TIMEOUT=300 s` 应用超时（run9 整窗只有 2 枚 `error_event`，本段 32 枚里已出 1 枚）。其余 31 枚均 `ok`，无 sentinel、无空正文。

## 3 时延（部分窗；A① 已按增补七记「污染窗、不采信」，此处只作污染量化用）

按 `wall_ms`（帧账 sidecar 口径，不用 `answers.latency_ms`）：

```
逐类别  cat=文档问答  n=19  p50= 67309.4  max= 85003.1  min=13651.9
        cat=多轮对话  n=12  p50= 70927.9  max=300065.2  min=16454.1
        cat=口径冲突  n= 1  p50= 58191.0  max= 58191.0  min=58191.0
逐档    tier=问答     n=31  p50= 67309.4  p95=192677.7  max=300065.2
        tier=分析     n= 1  p50= 58191.0
整表    (部分)        n=32  p50= 64786.7  max=300065.2
```

同档对照 run9（`docs/testing/run9-readout-2026-09-28.md` §A1，干净窗）：

| 类别 | run10 部分窗 p50 / max | run9 p50 / max | 倍数（p50） |
|---|---|---|---|
| 文档问答 | 67.3 s / 85.0 s | 30.7 s / 50.4 s | **2.19×** |
| 多轮对话 | 70.9 s / 300.1 s | 36.3 s / 300.1 s | **1.95×** |

⇒ 污染不是推测：同一类别的中位时延在争用下翻倍，且 300 s 超时在 32 枚里已经出现 1 枚。这两件事同时打穿 A①（时延）与 A②④（完成度／逐类分数），正是增补七设 >50% 停手线要防的形状。

## 4 帧账（部分窗，只报形状不作判词）

```
frames_rows=32  unique=32  text_frames: n=32 min=0 max=46
single_frame(=1) 枚数=0 题号=[]
```
⇒ A② 的分母应是 105，本扇只有 32 ⇒ 这一格**没量到**，不许拿这 32 枚对表 run9 的 11 枚红名单。

## 5 缺题逐枚点名（73 枚，按夹具顺序）

```
metric-02 metric-03 metric-04 metric-05 metric-06 metric-07 metric-08 metric-09 metric-10 metric-11
metric-12 metric-13 metric-14 metric-15 metric-16 metric-17 metric-18 metric-19
data-01 data-02 data-03 data-04 data-05 data-06 data-07 data-08 data-09 data-10 data-11 data-12
insight-01 insight-02 insight-03 insight-04 insight-05 insight-06 insight-07
chart-01 chart-02 chart-03 chart-04
approval-01 approval-02 approval-03 approval-04 approval-05 approval-06
scope-01 scope-02 scope-03 scope-04 scope-05 scope-06
unsupported-01 unsupported-02 unsupported-03 unsupported-04
tool-01 tool-02 tool-03 tool-04
report-01 report-02 report-03 report-04 report-05 report-06 report-07 report-08 report-09 report-10 report-11 report-12
```
已跑完的 32 枚：`doc-01..doc-19 chat-01..chat-12 metric-01`。
⇒ 按派工原文「缺题就整轮重来，不许手工补行」，本扇不进评分（`run_quality_evaluation.py` 一次都没跑，`evaluation-report-run10.json` 不存在，也不该存在）。

## 6 三枚 nvidia-smi 官方采样（原样）

### 采样 #1 开窗前 2026-09-30 12:43:44

```
$ nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv
pid, used_gpu_memory [MiB], process_name
13640, [N/A], C:\Users\fengx\anaconda3\python.exe
---
$ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
memory.used [MiB], memory.total [MiB], utilization.gpu [%]
2993 MiB, 8188 MiB, 99 %
```

### 采样 #2 相 1 中段（停手时点）2026-09-30 13:31:18

```
$ nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv
pid, used_gpu_memory [MiB], process_name
13640, [N/A], C:\Users\fengx\anaconda3\python.exe
4, [N/A], [Insufficient Permissions]
---
$ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
memory.used [MiB], memory.total [MiB], utilization.gpu [%]
7930 MiB, 8188 MiB, 90 %
```

### 采样 #3 收窗后 2026-09-30 13:31:35

```
$ nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv
pid, used_gpu_memory [MiB], process_name
13640, [N/A], C:\Users\fengx\anaconda3\python.exe
4, [N/A], [Insufficient Permissions]
---
$ nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
memory.used [MiB], memory.total [MiB], utilization.gpu [%]
7930 MiB, 8188 MiB, 94 %
```

⇒ 三枚采样都在，外来进程 **13640 从头到尾没走过**；显存从 2993 MiB 涨到 7930/8188 MiB（被测腿 `qwen3.5:9b` 5.3 GB ＋ `nomic-embed-text` 323 MB ＋ 外来训练），只剩 258 MiB 余量。

## 7 低频采样器（`gpu_sampler.log`，每 120 s 一行，PID 23680，已停）

```
采样枚数=20  首=2026-09-30 12:51:49  末=2026-09-30 13:29:55
外来进程在场样本=20／20   NONE 样本=0
污染期 X=41.2 min ／ 干净期 Y=0.0 min（相 1 已跑 41.2 min）
```
逐行原件：本目录 `gpu_sampler.log`。

外来负载归属（`Get-CimInstance Win32_Process`，13:29 现取，父链完整）：

```
pid=13640  ppid=42412  created=12:40:50
  "C:\Users\fengx\anaconda3\python.exe" train.py --config configs/_local_fog6.yaml --device cuda --resume
pid=42412  powershell.exe created=12:40:48
  & "C:\Users\fengx\Desktop\路面缺陷检测\swda-repro\scripts\run_local.ps1" -Jobs fog6
pid=42368  powershell.exe created=11:58:31   ← 链头
  -File C:\Users\fengx\Desktop\路面缺陷检测\swda-repro\_xfer\night_b002.ps1
pid=49252  powershell.exe created=12:40:49
  -File ...\swda-repro\_xfer\night_awake.ps1 -StopAfterH 20 -Tag held-by-run_local
＋ 4 枚 multiprocessing 子工（55344／33432／58220／33648，parent_pid=13640）
```
`night_b002.ps1` 文件头原话（业主自己的注释，只读取证）：
> Night chain, all-local variant: make the 2975 beta=0.02 TRAIN renders on this box, then finish 4.2 cell 6 (70K) on the 4060, then hand the GPU to 4.1 (night_cl3).

⇒ 这是一串**夜间批**（2975 张渲染 → cell 6 训练 → 把卡交接给 `night_cl3` 的 cl1→cl5→cl4，`night_awake.ps1 -StopAfterH 20`），不是会自己几分钟结束的冒烟。污染在窗内**不会**自行归零，这正是 >50% 停手线的适用场景。

## 8 收窗侧读数

| 格 | 命令原文 | 读数 |
|---|---|---|
| P-17 语料未动 | `Compare-Object (Import-Csv corpus_before.csv) (Import-Csv corpus_after.csv)` | **无输出**（97 枚名单与 SHA256 逐字节相同）；before=12:49:23／after=13:32:34，两件绝对路径＝本目录 `corpus_before.csv`／`corpus_after.csv` |
| 停手后 `answer:*` | `python scripts\eval_window_answer_cache_gate.py --check --repo-root C:\Users\fengx\PycharmProjects\企业智脑` | `PING = PONG`／`answer:* = 33 枚（dbsize=121）`／`verdict: FAIL rc=1` ⇒ 这 33 枚是本扇 32 题留下的，**下一扇开窗前必须不带 `--check` 真清零** |
| P-8 溯源（停手后复跑） | `python scripts\check_image_provenance.py --expect-container` | `tree 4376648`／`label revision=4376648`／`verdict MATCH`／`rc=0` ⇒ 本窗全程测的是 4376648 这枚镜像 |
| 主树基点 | `git -C 企业智脑 rev-parse --short HEAD` ＋ `git show --name-only --format= 96946f8` | 窗内主树 `4376648 → 96946f8`（第八班看板落账，**只动 `docs/` 一枚文件**，`app/`／`deploy/` 零命中 ⇒ 下一扇 P-8 会交 `DOCS-ONLY`，仍算 PASS，**不必重建镜像**，只需把跑分树 ff 到 96946f8） |
| 容器 | 本窗未动（零 build／零 restart／零 recreate／零 `docker compose up`）；只读 `docker inspect`／`docker ps`／`docker exec ... ollama ps`／`docker logs` | backend／worker／scheduler `Up (healthy)`，redis／postgres／ollama `Up 25 hours (healthy)` |
| 产品码 | 本窗零改动；跑分树 `git status --porcelain` 只有 `?? docs/perf/raw/run10-2026-09-30/` 与 `?? docs/testing/run10-readout-2026-09-30.md` | 零 commit／零 push／未新建分支 |

## 9 阻塞式监视的终局读数与停手后复核

监视件（派工纪律「等待一律用阻塞式监视而不是轮询」）：`powershell -File %TEMP%\evalrun\monitor_phase1.ps1`，内部 `Wait-Process -Id 49768`，原样交回：

```
MONITOR-START 12:52:01 waiting PID=49768
MONITOR-EXIT 13:31:32
sidecar_lines=32
answers_bytes=0        # answers-real.jsonl 从未存在（Get-Item 取不到 ⇒ 记 0，不是空文件）
--- phase1 stdout tail ---     （空）
--- phase1 stderr tail ---     （空）
```

停手 11 分钟后复核（`nvidia-smi`，13:42:21 +08:00）：

```
13640, [N/A], C:\Users\fengx\anaconda3\python.exe
4, [N/A], [Insufficient Permissions]
7930 MiB, 8188 MiB, 90 %      # 与停手时点同形，外来进程仍在场
```

⇒ 自 12:40:50 起算，外来 CUDA 负载已连续在场 **> 61 min**，与 `night_b002.ps1` 那条夜间链的自述一致（渲染 2975 张 → cell 6 训练 → 交卡给 `night_cl3`）。本执行员起的两枚进程已收尾：采集 PID 49768 已停、低频采样器 PID 23680 已停；`window_keep_awake.py --loop`（PID 41772／53144）**有意保留**（防交接期机器睡，零电源设置改动，释放＝`Stop-Process -Id 41772,53144`）。
