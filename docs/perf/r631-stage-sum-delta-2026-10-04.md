# R631 —— G-R51-1「端到端 vs 分段加总」取证纸（2026-10-04）

欠账原文（机器尺逐字切的那格，本纸不改口径）：

> R51 PARTIAL ｜ G-R51-1 ｜ 出处：跟进单 §21 判据表 ｜ `docs/handoff/2026-09-15-backend-followup-requests.md`
> 第 522 行（按 LF 计数）｜ 原文：② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%）

**本席**：执行层 R631 ｜ 工作树 `C:\Users\fengx\PycharmProjects\be-r631`（分支 `codex/be-r631`，基点 `4da0bad`）
**纪律**：每一枚命令只读。零容器、零 PG、零 Ollama、零模型、零网络。写域只有 `scripts/r631_*`、
`tests/test_r631_*`、`docs/perf/r631-*`；未 commit、未建分支。
**交的三样**：尺 `scripts/r631_stage_sum_delta.py`、牙 `tests/test_r631_stage_sum_delta.py`、本纸。

## 0. 三句话结论

1. **尺到位**：一键复跑、逐题对照、分位数、最大误差题逐枚点名、`<1%` 与 `0.03%` 两条线各判一次、退出码语义写死。
2. **这一格今天不能在离线证掉**：三窗盘上产物只有端到端腿（`wall_ms` 各 105 枚在位），分段腿一枚都不在盘上——
   逐件扫过，见 §4；再往外走到宿主 trace journal，那本是 PG 拒写时的兜底本，三窗时段一条事件都没有，见 §5。
3. **差的不是算力，是一枚导出**：三窗的 `*.finished` 跨度在 PostgreSQL `trace_events` 里，**纯读导出即出数，
   不必重跑模型**；跨钟那条腿的桥本席已查明**自带**（`session_id` 在事件载荷里，见 §7），不用改产品一行码。

## 1. 两条腿的真源（现读，非声明）

分段腿 S —— 本件不自加，只呼在册那把尺：

```powershell
rg -n "def classify_stage|def request_windows_from_events|def samples_from_span_payload|def samples_from_events|def aggregate_stage_latency" app/common/stage_timing.py
```

实取读数：

- `app/common/stage_timing.py:97` `classify_stage` ｜ `:277` `request_windows_from_events` ｜ `:314` `samples_from_span_payload`
  ｜ `:353` `samples_from_events` ｜ `:542` `aggregate_stage_latency`
- 跨度的产生者在边界那一层：`app/trace/spans.py:168` `duration_ms = int((time.monotonic() - self.monotonic_start) * 1000)`；
  `:206` `_observe_stage` 把**同一个** `payload.duration_ms` 交给 R51 账；`:261` `record_stage_event` 亦 `int(duration_ms)`。
- 在册消费方（本件与它同算法，可逐枚对账）：`app/api/v1/observability.py:678-693`
  `_stage_report_from_trace` = `samples_from_events(events)` + `end_to_end_by_trace=request_windows_from_events(events)`。

端到端腿 E —— 三枚候选，各自署名，抬头必须印强度：

| 腿 | 真源 | 时钟 | 与本件分段腿的关系 |
|---|---|---|---|
| `sidecar_wall_ms` | `scripts/eval_transport_ask_v2.py:1278` `wall_ms = round((time.time() - started) * 1000.0, 1)` | 采集器 | **跨钟 ⇒ 强**（分段与端到端不同源） |
| `trace_event_window` | `app/common/stage_timing.py:277` `request_windows_from_events()`（`request.started`→终事件的 `timestamp` 差） | 服务端 epoch | 同一本账两面 ⇒ **弱，但不同数** |
| `frames_event_window` | `runNN-sidecar-frames.jsonl` 里 `request.started`→`request.completed` 的 `elapsed_ms` 差 | 采集器 | 与 sidecar **同钟**，只作互证 |

`latency_ms` 不收当跨度（在册口径 R205a／R595）。同钟证据本席现取：`doc-01` 的 sidecar `wall_ms=59902.6`，
answers 的 `latency_ms=59904.215` —— 差 1.6 ms，两枚出自同一枚采集器钟，**拿它当"第二条独立腿"就是同源**。

## 2. 分母、口径、真源：写死之前先现读

三处常数都不抄纸面、不写字面，跑起来现读：

```powershell
python -c "import importlib.util;spec=importlib.util.spec_from_file_location('r','scripts/r631_stage_sum_delta.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);print(m.read_criterion_pct());print(m.read_alignment_pct());print(m.probe_inbook_gate())"
```

实取读数：

- 判据线：跟进单**第 522 行（LF 计数）**抠出 `<1%` ⇒ `threshold_pct=1.0`，原文逐字带回：
  `| **R51** | 阶段化 P95 观测（每步耗时进 trace 与 \`/health/details\`） | ① 分类/改写/检索/生成/反思各段 P50/P95 可查；② 端到端与分段加总误差 <1%（对齐 \`docs/perf/latency-budget-2026-09-16.md\` 的 0.03%） | 观测不得改变行为 |`
- 对齐线：`docs/perf/latency-budget-2026-09-16.md:131` ⇒ 印面 `0.03%`，本件用它自己的两枚数复算 `0.02989%`
  （`160.6s` vs `160.552s`），差 `0.00011` 在 `ALIGN_TOLERANCE=0.005` 内 ⇒ 通过；**复算与印面对不上就 RC=5**。
- 在册刀刃（行为探针，不抄 app 的字面）：9 901 ms／10 000 ms 必须绿、9 899 ms／10 000 ms 必须红 ⇒
  `{'r631-knife-pass': True, 'r631-knife-fail': False}` ⇒ literal 夹在 `(0.99, 1.01]`。
  纸上判据若不落进这区间（例：有人把判据改成 `<5%`），`collect()` 直接 `CaliberError` ⇒ **RC=5，不自取口径**。

> 行号尺的坑（本席当场踩过并改对）：跟进单那本件行尾是 `\r\r\n`。`Path.read_text()` 的通用换行会把
> 一行劈成两行，行号当场漂移、第 522 行读成空行。现读一律 `read_bytes().decode()` + 只按 LF 切，
> 与切出这格欠账的那把机器尺同规格。

## 3. 「是不是自加自比」——本席的裁与判死

**裁**：分段腿读 `payload.duration_ms`（单调钟、逐枚 `int()` 地板），`trace_event_window` 那条读事件
`timestamp` 之差（epoch 毫秒）。两枚数出自**不同字段、不同算法**，不是把一枚数拆成两枚 ⇒
`events` 腿不是恒 0 的假绿，但它与分段腿同在一本账里，**只是内部对照**，抬头必须印「弱」。
**真对照优先跨钟**：`--e2e-from auto` 在 join 连得上时选 `sidecar_wall_ms`。

**判死两条签名**（命中任一 ⇒ 判「不可信」，`RC=4`，且印面**不出现 PASS／FAIL**）：

1. **声明同源**：端到端腿署名等于分段腿（`--e2e-from segment_sum` 就是这条；本件故意留这枚选项，好让它可被驱动、可被钉）。
2. **恒零差**：所有可比题 `|分段加总 − 端到端|` 逐位为 0。两种精度、两把钟同时逐位相等不是测量，是自我复述。

实取读数（合成样机，见 §8；同源自证那一跑）：

```
## 🔴 判「不可信」（退出码 4）
- 声明同源：端到端腿署名 segment_sum，分段腿署名 stage_ledger ⇒ 分子就是分母拆出来的一部分，比值恒 0
- 恒零差：3 枚可比题的 |分段加总 - 端到端| 逐位为 0 ⇒ 两把独立的钟不会同时逐位相等，这是自我复述不是测量
- 本件不给 PASS／FAIL：这种绿不需要改一行代码就能永远拿到。
退出码：4
```

## 4. 三窗盘上产物实测：端到端腿在位，分段腿一枚都没有

```powershell
python scripts/r631_stage_sum_delta.py --window run18    # 同法 run19 / run20k
```

实取读数（三窗逐枚）：

| 窗 | sidecar 行数 | 连出题号 | 分段腿件（`runNN-traces.jsonl` / `-trace-events.jsonl` / `.traces`） | 退出码 |
|---|---|---|---|---|
| run18 | 105 | 105 | 三枚件名全部不存在 | **3**（量不到，不是 PASS） |
| run19 | 105 | 105 | 同上 | **3** |
| run20k | 106 | 105 | 同上 | **3** |

`run20k` 那 106→105 不是丢数：`doc-04` 有两行、`attempt` 都是 1、`wall_ms` 分别 27244.6 / 27490.9。
本件不静默折叠，取 `attempt` 最大并**点名**：

```
- 🔴 同题多枚（取 attempt 最大那枚，其余不静默丢）：题号 1 枚已点名 ⇒ doc-04
  （这件读了 106 行、连出 105 枚题号；行数与枚数不等就是这一格）
```

「分段腿不在盘上」这句本席是按名字查的，不是按感觉：

```powershell
# 逐件扫 %TEMP%\evalrun 全部 59 枚文件，四枚分段腿真名
python -c "import glob,os;d=os.path.join(os.environ['TEMP'],'evalrun');n=(b'duration_ms',b'.finished',b'stage_windows',b'stage_timing');t={};[t.setdefault(os.path.basename(p),{}).update({x.decode():open(p,'rb').read().count(x) for x in n if open(p,'rb').read().count(x)}) for p in [q for q in sorted(glob.glob(os.path.join(d,'*'))[:59] if os.path.isfile(q)]];print('命中 =',t or '零枚')"
```

实取读数：`命中 = 零枚`（59 枚文件，四枚名字各 0 次）。⇒ 盘上三本件**只带答案、帧账与整题跨度，不带分段跨度**。

互证一格（同钟，不作第二条腿）：run18 的 `wall_ms` 与帧账 `request.started→request.completed` 窗，105 题共在，
差值 p50=1.6031% ／ p95=80.7084% ／ 最大=91.4383%。差得这么多是因为 `wall_ms` 含排队与首事件之前那一段
（`stream_clock.request_sent_at` 起算）——这条正好说明**跨钟那条腿对不上 0.03% 不是产品的问题，是口径**。

## 5. 再往外走一步：宿主 trace journal（真数据，判语仍是「量不到」）

工作树之外的宿主盘上有一本真 journal：`企业智脑\data\traces\events.jsonl`（`default_trace_store()` 的
缺省落点 `TRACE_STORE_PATH=./data/traces/events.jsonl`，`app/trace/store.py:1253-1265`）。本席**只读**扫了它。

```powershell
# 逐枚数这本 journal 的构成（只读打开）
python -c "import json,collections;p=r'C:\Users\fengx\PycharmProjects\企业智脑\data\traces\events.jsonl';..."
```

实取读数：

- 事件 42 811 行（0 坏行）｜ 不同 `trace_id` 17 556 枚 ｜ 带 `duration_ms` 的 `*.finished` 事件 **7 359 枚**
- `request.started` 覆盖 14 434 枚 trace ｜ **终事件（completed/failed/cancelled）只有 10 枚 trace** ｜
  两端齐全的 10 枚里**带分段跨度 0 枚**
- `payload` 带 `session_id` 的事件 16 407 枚（19 个 session，可连 14 435 枚 trace）——这枚是 §7 那条桥的凭据
- 逐小时覆盖：`2026-10-03T09`/`T10`（run18 时段）＝ **0 枚**；`T11` 有 338 枚但实际落在 `11:44:25Z–11:59:07Z`，
  在 run19 切片（10:26:05–11:34:39Z）**之外**；`2026-10-04T02`/`T03`（run20k 时段）＝ **0 枚**
- 按三窗时间切（本地 +08 换 UTC，切片件写 `%TEMP%\r631-journal\`）：`时段内 trace 枚数 = {}`、`切片事件枚数 = {run18:0, run19:0, run20k:0}`

拿整本 journal 跑尺（真数据，只读）：

```powershell
python scripts/r631_stage_sum_delta.py --window journal --dir $env:TEMP --traces "C:\Users\fengx\PycharmProjects\企业智脑\data\traces\events.jsonl" --e2e-from trace_event_window
```

实取读数：

- `分段腿真源：stage_ledger ｜ trace 2437 枚 / 跨度 7359 枚`
- `端到端腿真源：trace_event_window ｜ 读数 10 枚`
- `## 量不到：一题都对不上（退出码 3）` —— `分段 trace 2437 枚 ｜ 端到端读数 10 枚 ｜ 可比 0 枚`，逐枚原因 `no_denominator`
- `退出码：3`

**判语**：这本不是完整事件流，是 PostgreSQL 拒写时的兜底本——`app/trace/store.py:364` `_write_fallback`
的注释写得很白（「since R250 this file holds *only*…」），跑成功的窗其事件进表不进本。
所以拿它出数＝拿残缺母集冒充整窗，本件宁可 RC=3 也不给这个数。**离线能走的路到这里走完了。**

## 6. `<1%` 与 `0.03%` 这两条线，今天各差多少（算术，不靠猜）

分段每枚跨度在产品边界处被 `int()` 地板一次（`app/trace/spans.py:168`），所以分段加总**系统性偏小**，
本件把界摆进表里（`truncation_bound_ms = 加总段数 × 1 ms`，均值界取 0.5 ms/段）。用三窗真 `wall_ms` 的分位数落这个界：

```powershell
python $env:TEMP\r631_span_stats.py
```

实取读数（`wall_ms`，ms）：

| 窗 | n | min | p50 | p95 | max | 10 段 ×0.5 ms 落在 min | 落在 p50 |
|---|---|---|---|---|---|---|---|
| run18 | 105 | 8 206.8 | 34 592.1 | 73 359.8 | 287 835.5 | **0.0609%** | 0.0145% |
| run19 | 105 | 5 917.1 | 32 488.1 | 70 471.0 | 279 563.5 | **0.0845%** | 0.0154% |
| run20k | 106 | 6 128.0 | 29 317.5 | 69 526.3 | 287 946.0 | **0.0816%** | 0.0171% |

**判语两条**：

- `<1%` 那一格：一枚 10 ms 量级的地板界对 30 s 的题是 0.03% 以下，对 6 s 的题也不到 0.1% ⇒ **百分数门本身不构成障碍**。
- `0.03%` 那一格：**只在服务端内部对照（events 腿）里有可能对**；跨钟那条腿（采集器 `wall_ms`）光排队与
  首事件之前那一段就吃掉 1.6%–91%（§4 互证读数），`int()` 地板再叠 0.06%–0.08% ⇒ 拿跨钟去对 0.03% 是**问错了对象**。
  跟进单这句「对齐 latency-budget 的 0.03%」今天仍然只有 09-16 那一次手摆表的凭据（`tests/test_r51_stage_latency.py:186-198` 钉着 0.0299%）。

## 7. 这格现在能不能离线证掉：**不能**。差的确切条件（三条，全在总控手里）

| # | 差什么 | 确切条件 | 要不要打模型 |
|---|---|---|---|
| ① | **一窗的 `trace_events` 导出** | 分段腿只在 PG 表里（`PERSISTENCE_BACKEND=postgres`，`app/trace/store.py:1253` 的兜底本不全覆盖，§5）。纯读导出即可 | **不要**。三窗早就跑完，跨度已在表里 |
| ② | **trace_id ↔ 题号的桥** | 题号**不进** trace（`app/api/v1/observability.py:776-793` SLO_BLOCKERS `lane_attribution_absent`：no request event carries the question），但 **`session_id` 进**：`app/agents/orchestrator.py:1193/1430/1502/1518` 把它写进事件载荷，`app/trace/projections.py:160` 再折进 `agent_runs.session_id`；采集器一题一枚 session（`scripts/eval_transport_ask_v2.py:864` 发进请求体、`:843` 记进帧账）。⇒ 导出件带那些载荷，本件**自动派生 join**（`--e2e-from auto` 走跨钟强腿），零改产品码。交来 `--join <trace_id,id>` 清单同样认，且**清单优先** | 不要 |
| ③ | **母集要诚实** | 缓存命中不发 `request.started`（SLO_BLOCKERS `cache_hits_are_not_traced`）⇒ 这类题分母为 0，本件逐枚点名 `no_denominator`，**不许从母集里悄悄摘掉**；同理 `unresolved_overlap_pairs` 非 0 的题不许靠百分数蒙混过关 | 不要 |

导出命令（本席无权跑——本单禁连 PG；写在这里给总控，列名逐枚取自 `app/trace/schema.py:32-43`）：

```powershell
# 窗边界用 sidecar 的 ts（本地 +08 换 UTC）：run20k = 2026-10-04 02:01:33Z .. 03:07:53Z
cmd /c "docker exec -i enterprise-brain-postgres-1 psql -U %POSTGRES_USER% -d enterprise_brain -c ""\copy (SELECT trace_id, request_id, task_id, sequence, event_type, status, owner_id, payload, created_at FROM trace_events WHERE created_at >= '2026-10-04 02:01:33+00' AND created_at < '2026-10-04 03:07:53+00' ORDER BY trace_id, sequence) TO STDOUT WITH (FORMAT JSON, ARRAY TRUE)"" > %TEMP%\evalrun\run20k-traces.json"
python scripts/r631_stage_sum_delta.py --window run20k --dir %TEMP%\evalrun
```

读数件形状说明：`FORMAT JSON, ARRAY TRUE` 交回一整枚 JSON 数组，本件的 `_json_rows` 认数组也认 JSONL；
`created_at` 当 `timestamp` 的别名收、`payload` 是字符串时解一次（同 `app/trace/run_reader.py:184-200`
`TraceDatabase._as_event` 那份契约，本件不另立）。**只读这一条 SQL，不动 env、不 recreate、不写库。**

要哪一枚窗：**建议下一枚新窗**（导出最省事，帧账与表同时新鲜）；若 run20k 的行仍在表里，那一窗也能直接出数——
本席没连表，所以「还在不在」这句话本席不替总控判。**这一格欠的从来不是算力，是一枚导出。**

## 8. 合成样机读数（🔴 不是 run18／run19／run20k 的真数，只为证明这把尺会咬）

件在 `%TEMP%\r631-synth-demo\`（三题：一题照 latency-budget 那十行的毫秒版、一题闲聊两枚段、一题故意缺一枚 `reflect`）：

```powershell
python scripts/r631_stage_sum_delta.py --window r631demo --dir %TEMP%\r631-synth-demo --e2e-from sidecar_wall_ms --join %TEMP%\r631-synth-demo\join-demo.jsonl
```

实取读数：

- `误差分位数：p50=19.6235% ｜ p95=39.2157% ｜ 最大=39.2157% ｜ 均值=19.67%`
- 最大误差题逐枚点名：`chat-07=39.2157%, doc-02=19.6235%, doc-01=0.1853%`
- `< 1.0%：FAIL`（点名 `chat-07, doc-02`）｜ `< 0.03%：FAIL` ｜ `退出码：1`
- 台账合并后 `重叠：pairs=0 ｜ 未决=0 ｜ 嵌套剔除=0.0 ms`（本席先写的是整窗 pooled 一次，10-04 实测
  `pairs=13／未决=9／生成段被误剔 2 980 ms`——那是**并发请求的区间被当成嵌套**，已改成逐题报告相加，
  并补一枚钉 `test_concurrent_traces_do_not_lose_segments_to_each_other`）
- `--e2e-from trace_event_window`（服务端内部对照）那一跑：`p50=20.2217%`、最大 `26.1905%`、`退出码 1`
- `--e2e-from segment_sum`（同源自证）那一跑：`退出码 4`，见 §3 那段原样印面

## 9. 牙与反证（全合成，37 枚）

```powershell
python -m pytest tests/test_r631_stage_sum_delta.py tests/test_r51_stage_latency.py -q
```

实取读数：`79 passed, 10 warnings`（其中 R631 36 枚、R51 43 枚＝未受本单影响的旁证）。
**末笔又补了一枚牙（第 37 枚，本节末点名）**，同名件复跑为 `80 passed` —— 以 §10 的收笔读数为准。

本文件的刀（逐枚点名，均在 `tests/test_r631_stage_sum_delta.py`）：摘一枚段误差必须变（`test_dropping_one_segment_changes_the_error`）、
某段翻倍比值必须动（`test_doubling_one_segment_moves_the_ratio`）、塞成同源必判不可信**两枚**
（`test_declaring_the_segment_sum_as_end_to_end_is_judged_untrusted` 声明路 ＋
`test_a_tautological_sidecar_is_caught_although_it_claims_a_client_clock` 恒零差路）、无货必 RC=3 且不印判语
（`test_a_window_without_the_segment_leg_says_no_measurement`、`test_an_empty_directory_is_no_measurement`）、
交叉重叠 0.01% 也不许绿（`test_a_crossing_overlap_cannot_pass_even_at_a_hundredth_of_a_percent`）、
逐题不许互相抵消（`test_two_wrong_requests_cannot_cancel_each_other_out`）、真源三枚函数不许换成本地副本
（`test_the_three_sources_are_the_instrumented_ones_not_a_local_copy`）、分位数用在册那把最近秩
（`test_quantiles_come_from_the_inbook_nearest_rank`）、`latency_ms` 拒收当跨度
（`test_the_ruler_reads_wall_ms_not_the_self_reported_latency_ms`）、重题不许静默折叠
（`test_the_same_question_twice_is_named_not_folded`）、清单优先于派生
（`test_an_explicit_manifest_wins_over_the_payload_derived_bridge`）。

**第 37 枚（末笔补的牙，治的是这把尺自己的一句假话）**：run18 现跑 `--e2e-from segment_sum` 时真码是 4
（同源判死优先于无货），可小标题「量不到：分段腿无货」硬写着 `退出码 3` —— 印面与末行打架，下一班照纸追债
就会追错格子（同源判死与缺导出是两件事）。`render` 改成从 `decide_rc(data)` 取同一枚数，牙钉
`test_the_printed_exit_code_never_disagrees_with_the_real_one` 断言印面出现的**每一枚**退出码都等于真码；
反证见下表 D 行。

**四枚反证变异**（本席逐枚改源、逐枚跑、逐枚还原）：

| 变异 | 实取读数 |
|---|---|
| A 摘掉判据常量（`within_threshold=True`） | `5 failed, 31 passed` |
| B 摘掉对齐常量（`within_align=True`） | `5 failed, 31 passed` |
| C 整枚摘掉同源判死（`return []`） | `4 failed, 32 passed` |
| D 把印面同源改回硬码（小标题写死 3） | `1 failed`：`AssertionError: 印面里每一枚退出码都必须等于真码：[3, 4]`（`test_the_printed_exit_code_never_disagrees_with_the_real_one`） |
| 还原 | `restored: True`（还原后逐枚 sha256 与变异前相同；且 `rg -c MUTATION` 零命中） |

另有两枚「常量在承重」的行为证：`build_rows` 只把 `threshold_pct` 摘成 1e9 ⇒ 同一本分段账、同一个误差，
红的当场变绿（`test_refutation_removing_the_criterion_constant_turns_red_into_green`）；
对齐常量同理（`test_refutation_removing_the_alignment_constant_turns_red_into_green`）。

## 10. 写域与纪律自证（收笔现取：2026-10-04 17:25 起，末笔 17:31 +08）

三枚 git 读数全部在 `C:\Users\fengx\PycharmProjects\be-r631` 现取，不是引用几分钟前的旧账：

- 命令原文：`git status --porcelain`
  → 实取读数：`?? docs/perf/r631-stage-sum-delta-2026-10-04.md` ／ `?? scripts/r631_stage_sum_delta.py` ／ `?? tests/test_r631_stage_sum_delta.py`
  —— 三枚 untracked，逐枚都在写域内；` M `（tracked 改动）零枚。
- 命令原文：`git diff --numstat HEAD` → 实取读数：**空输出**（tracked 文件零改动）
  旁证 `git diff --name-only HEAD | Measure-Object -Line` → `0`
- 命令原文：`git ls-files --others --exclude-standard` → 同上三枚（无第四枚漏在写域外）
- 命令原文：`git rev-list --count 4da0bad..HEAD` → 实取读数：`0`（**未 commit**，货只留盘上）
- 命令原文：`git rev-parse --abbrev-ref HEAD` ／ `git rev-parse --short HEAD`
  → 实取读数：`codex/be-r631` ／ `4da0bad`（未新建分支、未换分支；`git branch --list 'codex/*'` 的 `*` 只落在 `codex/be-r631`）

零环境副作用（本单硬规逐条自证）：

- 一枚 `docker` 都没调、一枚容器没动；一次 Ollama 都没打；一次 PostgreSQL 都没连（含只读）。
  §4 的盘上产物扫描与 §5 的宿主 journal 全是**只读打开**——总控在跑测量窗，容器 env 随时被 recreate，本席不读它。
- 未跑全量门 `scripts/run_gate.py`；只跑本单两枚测试件。
- `tests/fixtures/business_evaluation_100.jsonl` 未碰：`git status --porcelain` 里它连 ` M ` 都没出现。
- 主树 `C:\Users\fengx\PycharmProjects\企业智脑` 只读。其盘面 ` M AGENTS.md`、` M chroma_db/chroma.sqlite3`
  等条目属总控/他席，非本席所写；本席只在主树里只读扫过 `data\traces\events.jsonl` 一本件。

最终验证读数（收笔再跑一遍的现读数，非 §8／§9 的旧账）：

- 命令原文：`.\.venv\Scripts\python.exe -m pytest tests/test_r631_stage_sum_delta.py tests/test_r51_stage_latency.py -q`
  → 实取读数：`80 passed, 10 warnings in 7.42s`，`rc=0`
  —— 37 枚 R631 新牙 + 43 枚 R51 在册牙同跑，R51 一枚都没被本单咬红（补牙之前那跑是 `79 passed`）。
- 命令原文：`python scripts/r631_stage_sum_delta.py --window run18 --dir %TEMP%\evalrun`（`run19`／`run20k` 同名换窗）
  → 实取读数：三枚窗各 `rc=3`（量不到），每枚印面的退出码字样＝`3,3`（小标题与末行同一枚数）。
  「两条线各判一次」整节不印 ⇒ 判语行 `：PASS`／`：FAIL` 零枚；`PASS` 二字只出现在「这不是 PASS」那句自警里
  （逐窗命中 2 行，原样点名：`## 量不到：分段腿无货（退出码 3 —— 这不是 PASS）` ＋ 末行 `退出码：3 ｜ 量不到…—— 这不是 PASS`）。
  补跑 `--e2e-from segment_sum` 于 run18：`rc=4`，印面字样＝`4,4,4`，同判「不可信」，与 §3 那条一致。
- 卫生扫描（逐件 `python -c`，AST + 字节）：
  - `scripts/r631_stage_sum_delta.py` → bytes=50491 ／ LF=1051 ／ CRLF=0 ／ BOM=False ／ 控制字符（0x00 0x07 0x08 0x0b 0x0c）**零枚** ／ AST OK ／ 反引号 46 枚
  - `tests/test_r631_stage_sum_delta.py` → bytes=32785 ／ LF=650 ／ CRLF=0 ／ BOM=False ／ 控制字符**零枚** ／ AST OK ／ 反引号 8 枚
  - 命令原文：`rg -c MUTATION scripts/r631_stage_sum_delta.py tests/test_r631_stage_sum_delta.py` → `rc=1`（**零命中**：§9 那四枚反证变异已全部还原并逐枚 sha256 核验）

**留给总控的一句话**：本单不产绿票。G-R51-1 的判语停在「量不到（RC=3）」——差的是**一枚 `trace_events` 纯读导出**
（导出件名与列名见 §7），不是算力、不是模型、不需要重跑；`<1%` 与 `0.03%` 两条线在拿到那本账之前都不许翻绿。

## 11. 总控补判（10-04 19:2x 前后）：导出已交，三窗真读数

本席亲取，全程只读：未写库、未动 env、未 recreate、未打模型。

- `trace_events` 现取 69,106 行；列型现取 `created_at` = `timestamp with time zone`、`payload` = `jsonb`，`current_setting('TimeZone')` = `Etc/UTC`。
- 窗界 = sidecar `ts`（采集器本地 +08）换算 UTC：run18 `2026-10-03 09:12:40+00 .. 10:26:37+00`｜run19 `2026-10-03 10:25:37+00 .. 11:32:39+00`｜run20k `2026-10-04 02:01:15+00 .. 03:07:53+00`（三窗各自 `min/max(created_at)` 现取，均落在界内）。
- 🔴 §7 那条 `\copy ... WITH (FORMAT JSON, ARRAY TRUE)` 本席原样跑过，三窗各报 `ERROR: syntax error at or near "FORMAT"`（通道 = `docker exec -i … psql -At -c`）。本席改用它法逐行导出，本件 `_json_rows` 认 JSONL：
  `SELECT row_to_json(sub)::text FROM (SELECT trace_id, request_id, task_id, sequence, event_type, status, owner_id, payload::text AS payload, (created_at AT TIME ZONE 'UTC')::text AS created_at FROM trace_events WHERE <窗界> ORDER BY trace_id, sequence) sub`
  `payload` 交回字符串正是 §7 说的「解一次」那条契约；`stage_timing.py::_to_ms` 对无时区读数按 UTC 收，与 server 钟同源。
- 导出件（`%TEMP%\evalrun\`）：run18 3,515 行／144 枚 trace／2,280,344 B｜run19 3,427／143／2,219,774 B｜run20k 3,511／144／2,278,467 B。

| 窗 | status | 母集 n | 分段腿（trace/样本） | 端到端腿（请求） | p50 | p95 | p99 | 最大 | 均值 | 未参与对照 | 退出码 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| run18 | measured | 105 | 125 / 672 | 124 | 32.9612% | 73.8571% | 83.5642% | 97.2193% | 32.18% | `no_denominator` 20 | 1 |
| run19 | measured | 105 | 124 / 655 | 124 | 29.7976% | 73.7937% | 84.1346% | 97.8826% | 32.05% | `no_denominator` 19 | 1 |
| run20k | measured | 106 | 125 / 672 | 125（重题号 `doc-04`） | 31.4064% | 73.6662% | 82.8806% | 97.505% | 31.1% | `no_denominator` 19 | 1 |

- 两条线各判一次：三窗 `< 1.0%` 全 **FAIL**、`< 0.03%` 全 **FAIL**，且 `failing_1pct` 枚数 = 母集枚数（105／105／106）⇒ **没有一题过线**，不是抽样噪声。
- ⇒ 订正本纸 §7 那句「这格现在能不能离线证掉：**不能**」：**能证，证出来的结论是不达标**。G-R51-1 的判语从「量不到（RC=3）」改为「量到了，三窗全 FAIL（RC=1）」。这一格**继续不翻绿**——翻绿的前提是分段账覆盖面被修，不再是再导一次账。
- 病形（读数给的形状，归因待开单）：缺段集中在 `rewrite,retrieve,generate,reflect`。最坏一枚 `chart-01` 端到端 94,651 ms 只有 1 段进账 2,632 ms（三窗同形：run19 1,886 ms／run20k 2,406 ms）；`scope-05` 已进 6 段仍差 240,527 ms。⇒ 分段账只吃到端到端的一小片，`chart / tool / report / insight` 那一族尤其薄。
- 母集诚实性核对：`no_denominator` 逐枚点名在册（缓存命中不发 `request.started`，`cache_hits_are_not_traced`），未被悄悄摘除；`untrusted_reasons` 三窗皆空；`client_clock_agreement` 那本互证（wall_ms 对帧账，p50 1.3–1.6%／p95 80–81%）只作互证不作第二腿。
