# R551 · /approve 续跑轮的顺序不变量（2026-09-30）

单号 **R551**（执行层）｜施工树 `C:\Users\fengx\PycharmProjects\be-r551`｜基点 `f312eeb` **已 `merge --ff-only codex/data-file-catalog` 到主树现取 HEAD `59a9506`**｜**零 commit、零 push、零动主树、零起服务、零打模型、零 docker**。
解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`，cwd＝本席树；全程 `-q -p no:cacheprovider -o addopts=`，一次一枚件串行，**没起过 `scripts/run_gate.py`，没起过任何带 `-n`/`--dist` 的 pytest**。

🔴 本单改的是**顺序不变量**，不是文案、不是判据口径：一格终态语义没动、一个稳定码没新增、一枚字段没新造。

| 项 | 命令原文 | 现取读数 |
|---|---|---|
| 并树前基点 | `git -C be-r551 rev-parse --short HEAD` | `f312eeb`（`status --porcelain` 0 行） |
| 并树 | `git -C be-r551 merge --ff-only codex/data-file-catalog` | `Updating f312eeb..59a9506`（21 文件，Fast-forward） |
| 并树后 | `git -C be-r551 rev-parse --short HEAD` ＋ `status --porcelain` | `59a9506` ＋ 0 行 |
| 主树 | `git -C 企业智脑 rev-parse --short HEAD` / `... codex/data-file-catalog` | 两枚都是 `59a9506` |

## 1. 病与机制（行号全部本席现取，派工词未保证行号）

产品道 `app/api/v1/chat.py` 的 `async def _approve_stream`（起点 `:3456`）里，改之前的次序是：

- `agent_future = loop.run_in_executor(_executor, _run)` 在 **`:3527`**（改前是这段的第一行），
- `_record_resumed_lane_trace(...)`（trace 的第三处出口，发 `request.started`／`status="running"`）在 **`:3518`**（改后），改前排在其后（原落点在发帧那一处，现只剩一行指路注释 `:3575`）。

中间**没有任何同步点**，而 `run_in_executor` 一交出去工作线程立刻就动——它不等事件循环。后果链（每一环都现读过）：

1. `app/trace/lifecycle.py:101` 那句 `if terminal_event or not current:` —— **一枚 trace 的第一条事件就把 `agent_runs` 行种出来**，用的就是那条事件自带的 `status`；
2. 工作线程第一条会是检索留痕 `retrieval.completed`，它的 `status` 就是 **`completed`**（发射器 `app/rag/retrieval_pipeline.py`，身份由 `_run` 在线程内 `arm_retrieval_trace` 挂上）；
3. 抢跑之后 `app/trace/lifecycle.py:96` 以 **`terminal_run_regression`**（`:61`）拒掉那枚 `running` 的 `request.started`；
4. 🔴 而这一支**此后再不往 trace 记任何 `request.*` 事件**：`_approve_stream` 函数体内 `record_event` 命中 **0 处**，`request.cancelled`／`request.failed`／`request.completed` 共 7 处全是**只发帧**（`chat.py:3579/3603/3632/3723/3765/3792/3830`）；`app/agents/orchestrator.py` 的 `run_interrupt_stream`（起点 `:1546`）自 `:1546` 之后**一枚 `request.*` 都不记**（对照：`run_with_stream` 起点 `:1337`，在 `:1426/:1481/:1537` 记 started/completed/failed，且记在图起跑之前）。

⇒ **那一轮后来真失败，`agent_runs.status` 也永远停在 `completed`**：不是"晚一点会被改成 failed"，因为根本没人再写它。对照物 `/ask` 没这病，正是因为它的第一枚 `request.started` 排在图起跑之前。

在册件早就把这一格写成了"待别人治"：`tests/test_r536_retrieval_completed_on_product_lane.py::test_a_lone_retrieval_event_seeds_the_run_row_completed_and_says_so` 的原文是"``/approve`` 的第三处出口排在 ``_run`` 提交之后 ⇒ 有竞窗口。治它要动 chat.py 那处出口的次序，越出本单写域 ⇒ 写进读数纸交回总控"。**本单就是那一次治理**，那枚钉的口径按授权改口（见 §4）。

## 2. 改动面（`git diff --numstat` 现取）

```
19	9	app/api/v1/chat.py
7	3	tests/test_r536_retrieval_completed_on_product_lane.py
```

- `app/api/v1/chat.py`：把 `_record_resumed_lane_trace(...)` 那一整块（8 行）**原样上移**到 `loop = asyncio.get_running_loop()` 之前，并补 11 行理由注释；原落点留一行指路注释。函数其它一行未动，`_record_resumed_lane_trace` 本体一行未动。
- `tests/test_r536_...py`：只改那一枚钉的 **docstring**（改口），两条 `project_run` 断言逐字保留——投影层"谁先落第一枚事件谁定种子"这条语义一件没改，改的只是谁先落。
- 🔴 判据⑤ 自查（现取）：`git diff` 的增行里**没有** `@router`、没有 `error_code=`、没有新键名字面量 ⇒ **零新稳定码／零新路由／零新字段**。`docs/api/contract-v1.md` 零字节（`git status --porcelain` 里读不到它）。
- 新纸本枚、新钉 `tests/test_r551_resumed_lane_seeds_before_executor.py`（5 枚断言）。

## 3. 判据逐条（命令原文＋末行）

| 判据 | 命令原文 | 现取末行 |
|---|---|---|
| ① 顺序不变量·两形 | `python -m pytest tests/test_r551_resumed_lane_seeds_before_executor.py -q -p no:cacheprovider --tb=line -o addopts=` | 本窗现取（最终字节 `b40c370c…`＋基点 `4572aa8`）：`5 passed, 4 warnings in 7.24s`（rc=0）——形一 `test_shape_preemptive_worker_still_sees_request_started_first`（同线程 `EagerExecutor` 把最坏交错做成确定性）＋形二 `test_shape_after_server_return_keeps_the_same_order`（真 `_executor`、留痕晚到）＋结构钉。🔴 上一段在 `be396988…` 字节上取的 `…in 7.66s` **作废** |
| ② 失败轮不许显示 completed | 同一枚件现取 | `test_a_failing_continuation_round_does_not_report_completed` 本窗 rc=0：真 `TraceStore`＋真投影落 `agent_runs`，断言 `status != \"completed\"`（停在开放态 `running`）、`terminal_verdict` 两枚旗 `status_is_terminal=False`／`completed_at_is_set=False`，同枚并断这一轮**真失败过**（响应体含 `request.failed` 与 `internal_error`）。摘掉修复即红：K1／K2／K3／K4 四把都把它打红（见 §4） |
| ④ 不退化 | 逐枚 `python -m pytest <件> -q -p no:cacheprovider -o addopts=`（串行，一次一枚） | 见 §5 那张表 |
| ③ 反证刀 | `python %TEMP%\r551_knives2.py`（预检：盘面与备援都必须等于**外部已知** sha `b40c370c958b690f…`；一把一跑＝变异→victim→逐字节写回→**当场校验 sha**→同名件再跑＝正控；另挂 `atexit` 兜底复原） | 五把全咬，逐把 `复原逐字节校验 equal=True`，见 §4 |

结构钉 `test_the_record_call_site_is_textually_before_the_executor_handoff` 是判据① 的静态那一面：用 AST 在 `_approve_stream` 函数体里比 `RECORD_CALL` 与 `run_in_executor` 的行号，**不靠运行时抢窗口**，也不写死绝对行号（行号会漂、符号不会）。

## 4. 反证刀与 sha256 台账（chat.py 现值 `b40c370c958b690f`）

victim 一律 `tests/test_r551_resumed_lane_seeds_before_executor.py`；每把都改一处盘上真件、跑 victim、**立刻逐字节写回**，再跑同名件当正控。摘前另存一份 `%TEMP%\r551_chat_original.bytes` 作备援。

- 🔴 **自曝一（操作事故，非产品缺陷）**：五把刀原先放在一枚脚本里连跑，脚本在刀窗口内被中断、`finally` 没跑到 ⇒ 盘上 `chat.py` 停在 **K1 变异体**。本席接手时读到它的 sha256 前缀 `903558d732125671`，与本窗用同一份基线现算出的 K1 变异体前缀**逐字节相同**，等于把事故根因钉死。已用备援 `%TEMP%\r551_chat_original.bytes` 逐字节救回并复验：sha256 前缀 `b40c370c958b690f`、268830 字节、`crlf=5286`、`loneLF=0`、`loneCR=0`、无 BOM；AST 现取 `async def _approve_stream` 体内出口行 3518 早于提交行 3527。**教训写死**：刀不许连跑——一把一跑、每把跑完立刻校验 sha；备援的 sha 必须是**外部已知**值（旧脚本拿盘面自证备援＝盘面已脏时备援一起脏）。

- 🔴 **自曝二（读数事故，本席自己的工具用法错）**：窗口开头我用 `[IO.File]::ReadAllBytes('app\api\v1\chat.py')` 配相对路径量长度，.NET 用的是**进程 CWD（主树）**，同一条命令里的 `Get-FileHash` 用的却是 PowerShell location（本席树）⇒ 两枚数不在同一枚文件上，第一次那句「长度 267490」是**主树 chat.py** 的数，作废。同一处失误让一枚失败的 `py_compile` 往主树 `app/api/v1/__pycache__/chat.cpython-311.pyc` 写了枚缓存；删除被沙箱按「禁动主树」拦下，本席不绕行——该目录在 `.gitignore:2`，主树 `git status --porcelain` 仍零行，但**这枚残留要记在账上**。纪律：跨树读数一律绝对路径。

摘前基线（逐把相同）：`app/api/v1/chat.py` sha256 前缀 `b40c370c958b690f`、268830 字节、纯 CRLF、无 BOM。
| 刀 | 变异体 sha256 前缀 | 红的钉（victim＝本席派生钉） | victim 末行 | 复原后正控末行 |
|---|---|---|---|---|
| K1 顺序改回提交之后 | 903558d732125671 | 结构钉(①静态)／形一／形二／②正控 | rc=1 ｜ 4 failed, 1 passed, 4 warnings in 7.46s | rc=0 ｜ 5 passed, 4 warnings in 7.34s |
| K2 第三处出口整个哑掉 | accb17fda84f97c7 | 结构钉(①静态)／形一／形二／②正控／缺口点名钉 | rc=1 ｜ 5 failed, 4 warnings in 10.18s | rc=0 ｜ 5 passed, 4 warnings in 7.50s |
| K3 started 自带终态种子 | 7c629a733e9f1b2c | 形一／②正控 | rc=1 ｜ 2 failed, 3 passed, 4 warnings in 7.39s | rc=0 ｜ 5 passed, 4 warnings in 7.13s |
| K4 事件名不再叫 request.started | c926f2d0bf9e630a | 形一／形二／②正控／缺口点名钉 | rc=1 ｜ 4 failed, 1 passed, 4 warnings in 7.39s | rc=0 ｜ 5 passed, 4 warnings in 7.21s |
| K5 started 用了词表外的状态词 | aad45ca331b05a2e | 形一 | rc=1 ｜ 1 failed, 4 passed, 4 warnings in 7.49s | rc=0 ｜ 5 passed, 4 warnings in 7.47s |

- 🔴 **在册钉原先抓不到这枚病（现取，`r551_registered_probe.py`）**：把盘上 `chat.py` 逐字节改回 K1（变异体 sha256 前缀 `903558d732125671`，与 §4 台账那把同一份字节），两枚最相关的在册件**双双仍绿**——`tests/test_r536_retrieval_completed_on_product_lane.py` rc=0／`11 passed, 4 warnings in 7.27s`，`tests/test_approve_canonical_events.py` rc=0／`49 passed, 8 skipped, 12 warnings in 10.32s`；同一份变异体下本席新钉 rc=1／`4 failed, 1 passed`。⇒ 判据③ 的 victim 只能落在**本席派生钉**上，这不是回避：它正是本单存在的理由——顺序不变量原先零在册覆盖。复原后 `chat.py` 复验 `b40c370c958b690f`，在册件正控 rc=0／`11 passed in 7.17s`。
🔴 台账只记**第四类形状**没做、也解释为什么不做：把 `app/trace/lifecycle.py:101` 那条"第一条事件就种行"改掉能灭掉这一族病，但 `app/trace/**` 是本单禁入写域，且那条语义是 R250 两枚禁行钉子钉着的——本单只在**自己那条道**上把"谁先落"摆正。

## 5. 判据④ 那批邻件（逐枚现取，串行）

| 件 | 本席这一遍为什么跑它 | 末行（rc） |
|---|---|---|
| `tests/test_approve_canonical_events.py` | 同一支三处出口/canonical 归属，改顺序最容易撞它（本单禁碰，必须证明没撞） | `49 passed, 8 skipped, 12 warnings in 12.99s`（rc=0，21.3s） |
| `tests/test_r464_one_terminal_answer_stream_per_round.py` | 续跑轮「一轮只一枚终态答案」，出口挪位会改帧序 | `23 passed, 4 warnings in 14.78s`（rc=0，22.9s） |
| `tests/test_r203_answer_leg_streams.py` | 答案腿投送，`/approve` 走同一条腿 | `15 passed in 2.28s`（rc=0，10.6s） |
| `tests/test_r203_no_double_delivery.py` | 防双投——上移出口若把留痕发两遍，这枚该红 | `7 passed, 4 warnings in 7.52s`（rc=0，15.9s） |
| `tests/test_r203_sink_reaches_the_leg.py` | sink 到腿的注册，与 `_record_resumed_lane_trace` 同一一处出口族 | `6 passed, 6 warnings in 7.53s`（rc=0，16.2s） |
| `tests/test_r203_sse_progressive_frames.py` | SSE 帧序，`request.started` 发帧位置没动，必须仍绿 | `16 passed, 4 warnings in 8.30s`（rc=0，17.0s） |
| `tests/test_r536_counter_evidence_teeth.py` | R536 反证钉族——本单动的是同一处留痕上游 | `8 passed in 6.50s`（rc=0，15.9s） |
| `tests/test_r536_retrieval_completed_on_product_lane.py` | ④点名授权改口那枚所在件（枚数须与改口前一致） | `11 passed, 4 warnings in 7.44s`（rc=0，16.4s） |
| `tests/test_r536_single_emission_point.py` | 单发射点，防「上移变成第二处发射」 | `7 passed in 6.06s`（rc=0，14.0s） |
| `tests/test_r548_counter_evidence_teeth.py` | R548 反证钉族（派工词写三件，现取此族仅 2 件，按 2 件跑） | `17 passed, 4 warnings in 8.40s`（rc=0，17.0s） |
| `tests/test_r548_queue_lane_registers_the_piece_sink.py` | 队列腿注册 piece sink，与 `_approve_stream` 共享 executor 语义 | `16 passed, 4 warnings in 7.82s`（rc=0，16.3s） |
| `tests/test_r178_dataset_visibility_faces.py` | R172/R178 三处出口同读数一族（本单补的正是第三处出口） | `16 passed in 1.35s`（rc=0，9.5s） |
| `tests/test_r178_retrieval_denial_audit.py` | 检索留痕审计，种子事件就是它 | `9 passed in 1.02s`（rc=0，9.1s） |
| `tests/test_r551_resumed_lane_seeds_before_executor.py` | 本席新钉在最终字节上的自验 | `5 passed, 4 warnings in 7.24s`（rc=0，15.6s） |

逐枚串行、零 `-n`／零 `--dist`／零 `run_gate.py`；命令原文一律 `python -m pytest <件> -q -p no:cacheprovider --tb=line -o addopts=`，解释器 `企业智脑\.venv\Scripts\python.exe`，cwd＝本席树（基点 `4572aa8`）。这一遍共 **14 枚件**：14 枚 rc=0、0 枚 rc!=0；跑前跑后 `chat.py` 都复验为 `b40c370c958b690f`（start/end 两个时间戳 23:35:29／23:39:06）。

R536 那枚被授权改口的件改完复跑 **11 passed**（枚数与改口前一致：只动 docstring）。

## 6. 未达与缺口（照实点名，不顺手补）

- 🔴 **这一支没有终态记账**：顺序修好之后，`/approve` 续跑轮的 `agent_runs.status` 停在**开放态 `running`**——不是 `completed`（本单治掉了），但也**不是"已失败"**。补它＝给 `run_interrupt_stream` 记 `request.completed`/`request.failed`，那改的是 canonical 归属，会撞 `tests/test_approve_canonical_events.py` 一族（现取 49 passed／8 skipped）与前端 `frontend/src/lib/sessions.js` 的 `lastSequence` 闸门。**业主未裁，本席一件没动**，坐标交回：`app/agents/orchestrator.py:1546` 起 `run_interrupt_stream` 无 `request.*` 记账；`app/api/v1/chat.py:3579/3603/3632/3723/3765/3792/3830` 七处只发帧。本席把它钉成可失败形状：`test_this_lane_still_records_no_terminal_request_event`（谁偷偷补上，这枚就红）。
- **形二不是抢窗口那一形**（它用真线程池，改前也大概率绿）：它的用处是防"把出口挪到更后面／整块删掉"这一族过治与哑火——K2／K4 两把它都红了，形二就是证据。
- 本席**没跑**全量门（禁），所以"其余在册件不受影响"这句本单不交；交的是 §5 那批点名件 ＋ 反证刀。
- 派工词坐标不符一处（本班第三起）：写"**R548 那三件**"，本席现取 `tests/` 里 `*r548*` 只有 **2 枚**（`test_r548_counter_evidence_teeth.py`、`test_r548_queue_lane_registers_the_piece_sink.py`），本席按现取两枚跑，没去凑第三枚。

## 7. 写域与两态交回

- 只动四样：`app/api/v1/chat.py`（一处上移）、`tests/test_r536_retrieval_completed_on_product_lane.py`（④点名授权的那一枚 docstring 改口）、新钉 `tests/test_r551_resumed_lane_seeds_before_executor.py`、本纸。
- 禁入件一枚没碰：`app/trace/**`、`app/agents/**`、`docs/api/contract-v1.md`、`migrations/**`、`frontend/**`、看板与跟进单。
- 行尾：四枚件在**原始 bytes** 上判，全部 `loneLF=0`、`loneCR=0`、无 BOM（新钉 290 枚 CRLF、`chat.py` 5286 枚、r536 件 506 枚、本纸 87 枚（本纸自量：写完再读回同一批 bytes）。这台机 `core.autocrlf=true` 且无 `.gitattributes` ⇒ 盘上必须 CRLF。
- 🔴 **两态交回**：以上是**dirty 态（已改未 commit）**跑出来的，点名文件清单＝`app/api/v1/chat.py`、`tests/test_r536_retrieval_completed_on_product_lane.py`、`tests/test_r551_resumed_lane_seeds_before_executor.py`、`docs/testing/r551-resumed-lane-order-2026-09-30.md`。**干净树那一遍请总控并树后复跑同名件**（本席无 commit 权限，跑不了那一遍）。
