# R636 分段账覆盖面归因 —— 三窗逐枚点名、三型凭据、修复单判据草案

- 工单 R636 ｜ 代号 Lorentz ｜ 基点 `473235f`（分支 `codex/be-r636`）｜ 落纸日 2026-10-04
- 本单**不改产品码**：`app/**` 零字节。这纸上的每个数字都由 `scripts/r636_stage_coverage.py` 现场跑出来，无一处手抄；复现命令见 §11。
- 原料（只读）：`%TEMP%\evalrun\run18|run19|run20k` 的 `-traces.jsonl` / `-sidecar.jsonl` / `-sidecar-frames.jsonl`。零容器、零 PG、零 Redis、零模型、不起服务、不重建镜像、不重导。
- 尺的边界：本纸**只摆覆盖面与型别，不判 G-R51-1 绿不绿**，判语权在总控。
- 派生尺走源码 AST，不 import 产品模块（import `app/api/v1/chat.py` 会发 Postgres 探针并写脏被跟踪的 `chroma_db/chroma.sqlite3`）。
- 引用坐标一律 `文件::符号`，不抄行号。

## 0 四条结论
1. **两条腿整条不产账，不是零散少了几段。** rewrite 与 reflect 在 `app/**` 里没有跨度产生点：AST 现读 `app/trace/spans.py::record_stage_event` 调用点 0 枚；三窗 105／105／106 枚题**全部**缺这两段（§2、§6）。classify 三窗满产。
2. **`no_denominator` 那批不是「缓存命中不发 `request.started`」。** 现读形状：批准续跑的工作腿挂在**另一枚 trace** 上——`app/api/v1/chat.py::_approve_stream` 调 `app/agents/orchestrator.py::run_interrupt_stream` 时一个身份参数都不传，`_execution_ids()` 另铸一枚 trace_id，于是那枚 trace 有跨度、无 `request.started`、session_id 也不在本窗帧账里。三窗各 20／19／19 枚，跨度合计 505855.0／489411.0／496856.0 ms（§5、§8）。
3. **真正「只有一枚 `request.started`」的是续跑头，而 R631 既不列 rows 也不列 skipped——那是一格静默。** 三窗各 19／19／19 枚（§5 第二组）。在册原因码 `cache_hits_are_not_traced` 把两组混成了一个名字。
4. **净缺口里能立刻归位的只有孤儿那一刀。** 补齐后仍剩 15.47%／14.98%／13.31% 的端到端占比没有任何在册账可指认它是哪一段——那部分今天**没有时长读数**（腿没插桩），降幅只能落地后量，不能预算。算术见 §10。

## 1 尺与原料
- 尺：`scripts/r636_stage_coverage.py`（只读、离线，逐枚复算分段加总／段数／缺段／误差，再与 R631 现跑读数比）。
- 牙：`tests/test_r636_stage_coverage.py`（31 枚 = 合成 18 枚 + 真窗对账 13 枚，清单见 §11.2）
- 分段腿原料 = `-traces.jsonl`；端到端腿原料 = `-sidecar.jsonl`；`-sidecar-frames.jsonl` 只用来把孤儿 trace 经 session_id 归名到题号。
- 母集四组（一枚 trace 只进一组）：`asked`＝有分母且有跨度（= R631 的 rows）；`no_denominator`＝有跨度无分母（= R631 的 skipped）；`resumed_head`＝有分母零跨度（R631 两本都不列）；`bare_trace`＝两者都无。
- 死法与退出码：对不上 R631 → `MismatchError`(1)；母集≠账本 → `UniverseError`(2)；原料读不到 → `InputMissing`(3)；归因没凭据 → `EvidenceError`(4)；AST 与在册常量分家 → `DerivedError`(5)。
- 三窗现跑切分差（判据①的正控，必须全 0）：
  - run18 → {"asked_minus_rows": 0, "no_denom_minus_skipped": 0, "rows": 105, "skipped": 20, "skipped_reasons": ["no_denominator"]}｜母集 144 = 点名 144
  - run19 → {"asked_minus_rows": 0, "no_denom_minus_skipped": 0, "rows": 105, "skipped": 19, "skipped_reasons": ["no_denominator"]}｜母集 143 = 点名 143
  - run20k → {"asked_minus_rows": 0, "no_denom_minus_skipped": 0, "rows": 106, "skipped": 19, "skipped_reasons": ["no_denominator"]}｜母集 144 = 点名 144

## 2 三型四形（每一枚缺账都必须落到这里并带凭据）
型别：`in_ledger` 进账／`no_event` 一个事件都没发（A）／`unrecognized_event` 发了但 `app/common/stage_timing.py::samples_from_events()` 不认（B）／`nested_excluded` 发了但被嵌套/重叠剔除（C）。型 A 再分四形，每一形对应一枚可现读的源码形状：

| 型/形 | 含义 | 凭据形状（现读点） | run18 | run19 | run20k |
|---|---|---|---|---|---|
| no_event/a0_path_not_taken | A/a0 这一题这条路径根本没走 | 本题事件名册（含未登记时长件在内）没有任何能名该段的记录；该段在 `app/**` 别处是有跨度产生点的 | 62 | 66 | 60 |
| no_event/a1_call_site_no_identity | A/a1 跑了但调用点不带身份 | AST 现读 `identityless_model_sites`：`_make_model(...).invoke(...)` 不传 `config`，那一发天生不落本题 trace | 10 | 13 | 11 |
| no_event/a2_leg_has_no_span | A/a2 这条腿整条没插桩 | `app/trace/spans.py::record_stage_event` 在 `app/**` 调用点 0 枚（reflect 有入口无调用点） | 179 | 177 | 182 |
| no_event/a3_event_on_sibling_trace | A/a3 事件发在同胞 trace 上 | 本题 trace 名册无该段，配对孤儿 trace 里有；归名靠 session_id/头 trace 桥 | 2 | 2 | 2 |

- **型 B / 型 C 在三窗真件里命中 0 枚**，这不是「没有重叠计时」，是两件事：
  - 剔除确实存在：run18 有 10 枚「题-段」带 `excluded_count>0`，合计 48816.0 ms；但它们同段仍有别的跨度进账，所以状态是 `in_ledger`。型 C 只统计「整段一条不剩」的那种，逐枚点名：
  - 「发了但尺不认」那一族今天被本件另立成**未登记并行账**（§6 第 5 条），与在册跨度**重叠**，不许相加，也不许冒充型 B 缺账。

| 题号 | 段 | 被剔 ms | 被剔枚数 | 状态 |
|---|---|---|---|---|
| scope-02 | retrieve | 7984.0 | 1 | in_ledger |
| metric-11 | generate | 1467.0 | 1 | in_ledger |
| report-02 | retrieve | 4917.0 | 1 | in_ledger |
| approval-02 | retrieve | 8309.0 | 1 | in_ledger |
| report-06 | generate | 829.0 | 1 | in_ledger |
| unsupported-02 | retrieve | 6053.0 | 1 | in_ledger |
| doc-15 | retrieve | 4800.0 | 1 | in_ledger |
| doc-01 | retrieve | 7928.0 | 1 | in_ledger |
| data-07 | generate | 1106.0 | 1 | in_ledger |
| report-12 | retrieve | 5423.0 | 1 | in_ledger |

## 3 三窗账（尺子印面原文，非手抄）
### 3.1 窗 run18
```text
## 抬头（这格欠的不是再量一次误差，是覆盖面）
- R631 现跑：measured ｜ 判据线 < 1.0% ｜ 对齐线 < 0.03%
- 母集＝账本：144 枚 trace 全部点名（asked 105 ／ no_denominator 20 ／ resumed_head 19 ／ bare 0）｜ 与 R631 切分差 = {"rows": 105, "skipped": 20, "skipped_reasons": ["no_denominator"], "asked_minus_rows": 0, "no_denom_minus_skipped": 0}
- Σ端到端 4248907.7 ms ｜ Σ分段进账 3085078.0 ms ｜ Σ缺口 1163829.7 ms（27.39%）
- 缺口拆账：配对孤儿 trace 505855.0 ms（加得进）｜ int() 地板界 490.0 ms ｜ 残差 657484.7 ms（占端到端 15.47%，这笔没有任何在册账可归）｜ 未登记并行账 worker 腿 2600956.0 ms、检索腿 1023001.3 ms（与在册跨度**重叠**，不许相加）

## 逐段覆盖面（题数按母集 105 枚）
- classify：产账题数=105 ／ 缺账题数=0 ｜ 进账 305709.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={}
- rewrite：产账题数=0 ／ 缺账题数=105 ｜ 进账 0.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={"no_event/a2_leg_has_no_span": 74, "no_event/a0_path_not_taken": 31}
- retrieve：产账题数=74 ／ 缺账题数=31 ｜ 进账 1252997.0 ms ｜ 被剔 45414.0 ms ｜ 缺账型别={"no_event/a0_path_not_taken": 31}
- generate：产账题数=93 ／ 缺账题数=12 ｜ 进账 1507036.0 ms ｜ 被剔 3402.0 ms ｜ 缺账型别={"no_event/a3_event_on_sibling_trace": 2, "no_event/a1_call_site_no_identity": 10}
- reflect：产账题数=0 ／ 缺账题数=105 ｜ 进账 0.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={"no_event/a2_leg_has_no_span": 105}
```

### 3.2 窗 run19
```text
## 抬头（这格欠的不是再量一次误差，是覆盖面）
- R631 现跑：measured ｜ 判据线 < 1.0% ｜ 对齐线 < 0.03%
- 母集＝账本：143 枚 trace 全部点名（asked 105 ／ no_denominator 19 ／ resumed_head 19 ／ bare 0）｜ 与 R631 切分差 = {"rows": 105, "skipped": 19, "skipped_reasons": ["no_denominator"], "asked_minus_rows": 0, "no_denom_minus_skipped": 0}
- Σ端到端 3816262.8 ms ｜ Σ分段进账 2754568.0 ms ｜ Σ缺口 1061694.8 ms（27.82%）
- 缺口拆账：配对孤儿 trace 489411.0 ms（加得进）｜ int() 地板界 466.0 ms ｜ 残差 571817.8 ms（占端到端 14.98%，这笔没有任何在册账可归）｜ 未登记并行账 worker 腿 2416030.0 ms、检索腿 1009826.7 ms（与在册跨度**重叠**，不许相加）

## 逐段覆盖面（题数按母集 105 枚）
- classify：产账题数=105 ／ 缺账题数=0 ｜ 进账 266041.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={}
- rewrite：产账题数=0 ／ 缺账题数=105 ｜ 进账 0.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={"no_event/a2_leg_has_no_span": 72, "no_event/a0_path_not_taken": 33}
- retrieve：产账题数=72 ／ 缺账题数=33 ｜ 进账 1105419.0 ms ｜ 被剔 145838.0 ms ｜ 缺账型别={"no_event/a0_path_not_taken": 33}
- generate：产账题数=90 ／ 缺账题数=15 ｜ 进账 1364243.0 ms ｜ 被剔 16734.0 ms ｜ 缺账型别={"no_event/a3_event_on_sibling_trace": 2, "no_event/a1_call_site_no_identity": 13}
- reflect：产账题数=0 ／ 缺账题数=105 ｜ 进账 0.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={"no_event/a2_leg_has_no_span": 105}
```

### 3.3 窗 run20k
```text
## 抬头（这格欠的不是再量一次误差，是覆盖面）
- R631 现跑：measured ｜ 判据线 < 1.0% ｜ 对齐线 < 0.03%
- 母集＝账本：144 枚 trace 全部点名（asked 106 ／ no_denominator 19 ／ resumed_head 19 ／ bare 0）｜ 与 R631 切分差 = {"rows": 106, "skipped": 19, "skipped_reasons": ["no_denominator"], "asked_minus_rows": 0, "no_denom_minus_skipped": 0}
- Σ端到端 3765735.4 ms ｜ Σ分段进账 2767171.0 ms ｜ Σ缺口 998564.4 ms（26.52%）
- 缺口拆账：配对孤儿 trace 496856.0 ms（加得进）｜ int() 地板界 485.0 ms ｜ 残差 501223.4 ms（占端到端 13.31%，这笔没有任何在册账可归）｜ 未登记并行账 worker 腿 2444940.0 ms、检索腿 969071.9 ms（与在册跨度**重叠**，不许相加）

## 逐段覆盖面（题数按母集 106 枚）
- classify：产账题数=106 ／ 缺账题数=0 ｜ 进账 238876.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={}
- rewrite：产账题数=0 ／ 缺账题数=106 ｜ 进账 0.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={"no_event/a2_leg_has_no_span": 76, "no_event/a0_path_not_taken": 30}
- retrieve：产账题数=76 ／ 缺账题数=30 ｜ 进账 1077080.0 ms ｜ 被剔 105755.0 ms ｜ 缺账型别={"no_event/a0_path_not_taken": 30}
- generate：产账题数=93 ／ 缺账题数=13 ｜ 进账 1435670.0 ms ｜ 被剔 4231.0 ms ｜ 缺账型别={"no_event/a1_call_site_no_identity": 11, "no_event/a3_event_on_sibling_trace": 2}
- reflect：产账题数=0 ／ 缺账题数=106 ｜ 进账 0.0 ms ｜ 被剔 0.0 ms ｜ 缺账型别={"no_event/a2_leg_has_no_span": 106}
```

## 4 逐枚覆盖面账（车道 × 题号，三窗全量 316 枚）
列意：`缺口ms` = 端到端 − 分段进账 − 配对孤儿；`误差%` = 缺口 ÷ 端到端（与 R631 同名读数逐枚相等）；`缺段` 每枚都带型/形，凭据见 §2 与尺内 `claims`；`配对孤儿ms` = 归到本题名下但挂在另一枚 trace 上的跨度合计；`未登记账` = 发了但 `FINISHED_EVENTS` 不认的时长件（与在册跨度重叠，**不许相加**）。

### 4.1 窗 run18（105 枚）
| 题号 | 车道 | tier | 端到端ms | 分段进账ms | 缺口ms | 误差% | 段数 | 缺段（型/形） | 配对孤儿ms | 未决 | 未登记账 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| chat-01 | qa | chat | 30845.4 | 21177.0 | 9668.4 | 31.3447 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:20694.0/{"step.finished": 1} ｜ retrieve:3345.6/{"retrieval.completed": 1} |
| data-10 | analysis | analysis | 24432.7 | 14151.0 | 10281.7 | 42.0817 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14226.0/{"step.finished": 1} |
| chart-02 | analysis | analysis | 121405.2 | 32373.0 | 89032.2 | 73.3348 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 69952.0 | 0 | generate:32635.0/{"step.finished": 1} |
| chat-12 | qa | chat | 27063.4 | 17192.0 | 9871.4 | 36.4751 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16426.0/{"step.finished": 1} ｜ retrieve:3135.9/{"retrieval.completed": 1} |
| metric-07 | analysis | analysis | 37026.7 | 37742.0 | -715.3 | 1.9318 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:25425.0/{"step.finished": 1} ｜ retrieve:17118.6/{"retrieval.completed": 3} |
| approval-03 | qa | chat | 29388.5 | 24536.0 | 4852.5 | 16.5116 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:19014.0/{"step.finished": 1} ｜ retrieve:12721.6/{"retrieval.completed": 2} |
| chart-03 | qa | chat | 17475.4 | 4046.0 | 13429.4 | 76.8475 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 4372.0 | 0 | generate:3012.0/{"step.finished": 1} |
| metric-19 | report | analysis | 37289.5 | 40583.0 | -3293.5 | 8.8322 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:25060.0/{"step.finished": 1} ｜ retrieve:19592.8/{"retrieval.completed": 3} |
| data-12 | analysis | analysis | 58506.7 | 39564.0 | 18942.7 | 32.377 | 17 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:47722.0/{"step.finished": 1} |
| scope-02 | qa | chat | 60150.5 | 52248.0 | 7902.5 | 13.1379 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 6022.0 | 2 | generate:40985.0/{"step.finished": 1} ｜ retrieve:22297.6/{"retrieval.completed": 3} |
| metric-09 | analysis | analysis | 35460.0 | 41355.0 | -5895.0 | 16.6244 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:24937.0/{"step.finished": 1} ｜ retrieve:21414.9/{"retrieval.completed": 3} |
| approval-05 | qa | chat | 46438.8 | 45400.0 | 1038.8 | 2.2369 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:31222.0/{"step.finished": 1} ｜ retrieve:21841.8/{"retrieval.completed": 3} |
| chart-01 | analysis | analysis | 94651.1 | 2632.0 | 92019.1 | 97.2193 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a3_event_on_sibling_trace] reflect[no_event/a2_leg_has_no_span] | 72065.0 | 0 | — |
| chat-04 | qa | chat | 29036.9 | 19466.0 | 9570.9 | 32.9612 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19338.0/{"step.finished": 1} ｜ retrieve:3399.2/{"retrieval.completed": 1} |
| chat-05 | qa | chat | 15101.7 | 9485.0 | 5616.7 | 37.1925 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| chat-09 | qa | chat | 18677.9 | 10889.0 | 7788.9 | 41.7012 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| insight-04 | analysis | analysis | 46334.5 | 48660.0 | -2325.5 | 5.0189 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:34407.0/{"step.finished": 1} ｜ retrieve:20700.2/{"retrieval.completed": 3} |
| doc-06 | qa | chat | 43017.8 | 48702.0 | -5684.2 | 13.2136 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:32257.0/{"step.finished": 1} ｜ retrieve:21839.9/{"retrieval.completed": 3} |
| metric-17 | report | analysis | 27970.2 | 15640.0 | 12330.2 | 44.0833 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15061.0/{"step.finished": 1} ｜ retrieve:4665.9/{"retrieval.completed": 1} |
| data-11 | qa | chat | 27478.2 | 21362.0 | 6116.2 | 22.2584 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| chat-03 | qa | chat | 15956.2 | 8149.0 | 7807.2 | 48.9289 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| report-09 | report | analysis | 63457.2 | 50129.0 | 13328.2 | 21.0034 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 3269.0 | 0 | generate:49756.0/{"step.finished": 1} ｜ retrieve:5624.1/{"retrieval.completed": 1} |
| metric-16 | report | analysis | 46815.0 | 54778.0 | -7963.0 | 17.0095 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:35905.0/{"step.finished": 1} ｜ retrieve:29802.6/{"retrieval.completed": 3} |
| unsupported-01 | qa | chat | 21651.8 | 13562.0 | 8089.8 | 37.3632 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13406.0/{"step.finished": 1} ｜ retrieve:4360.6/{"retrieval.completed": 1} |
| metric-11 | qa | chat | 42224.3 | 43409.0 | -1184.7 | 2.8057 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:51076.0/{"step.finished": 2} ｜ retrieve:15548.9/{"retrieval.completed": 1} |
| report-04 | report | analysis | 64986.8 | 60412.0 | 4574.8 | 7.0396 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 9990.0 | 3 | generate:44515.0/{"step.finished": 1} ｜ retrieve:19297.4/{"retrieval.completed": 3} |
| chat-11 | qa | chat | 34381.4 | 23921.0 | 10460.4 | 30.4246 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:23693.0/{"step.finished": 1} |
| insight-06 | analysis | analysis | 22271.9 | 12615.0 | 9656.9 | 43.3591 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12255.0/{"step.finished": 1} |
| report-08 | qa | chat | 17543.2 | 11278.0 | 6265.2 | 35.713 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| doc-14 | qa | chat | 48943.7 | 47690.0 | 1253.7 | 2.5615 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:36353.0/{"step.finished": 1} ｜ retrieve:19754.8/{"retrieval.completed": 3} |
| doc-11 | qa | chat | 44124.8 | 35649.0 | 8475.8 | 19.2087 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:30997.0/{"step.finished": 1} ｜ retrieve:9603.8/{"retrieval.completed": 2} |
| report-02 | report | analysis | 57461.2 | 43921.0 | 13540.2 | 23.5641 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 10776.0 | 2 | generate:36164.0/{"step.finished": 1} ｜ retrieve:18140.1/{"retrieval.completed": 3} |
| report-03 | report | analysis | 15307.9 | 8542.0 | 6765.9 | 44.1987 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| metric-15 | qa | chat | 45673.0 | 44911.0 | 762.0 | 1.6684 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:38143.0/{"step.finished": 2} ｜ retrieve:18211.4/{"retrieval.completed": 3} |
| scope-01 | qa | chat | 32824.5 | 21063.0 | 11761.5 | 35.8315 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:21090.0/{"step.finished": 1} ｜ retrieve:6040.2/{"retrieval.completed": 1} |
| insight-07 | analysis | analysis | 83394.2 | 38446.0 | 44948.2 | 53.8985 | 16 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 25214.0 | 0 | generate:44624.0/{"step.finished": 1} |
| data-02 | analysis | analysis | 19789.9 | 8750.0 | 11039.9 | 55.7855 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:9758.0/{"step.finished": 1} |
| chat-02 | qa | chat | 26886.6 | 16227.0 | 10659.6 | 39.6465 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16281.0/{"step.finished": 1} ｜ retrieve:3353.8/{"retrieval.completed": 1} |
| doc-10 | qa | chat | 30599.2 | 16942.0 | 13657.2 | 44.6325 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16757.0/{"step.finished": 1} ｜ retrieve:4163.0/{"retrieval.completed": 1} |
| doc-05 | qa | chat | 23372.9 | 14117.0 | 9255.9 | 39.601 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13584.0/{"step.finished": 1} ｜ retrieve:2204.0/{"retrieval.completed": 1} |
| chat-08 | qa | chat | 34592.1 | 24181.0 | 10411.1 | 30.0968 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:24520.0/{"step.finished": 1} ｜ retrieve:4500.0/{"retrieval.completed": 1} |
| metric-05 | qa | chat | 55395.3 | 62584.0 | -7188.7 | 12.9771 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:55206.0/{"step.finished": 2} ｜ retrieve:29103.8/{"retrieval.completed": 3} |
| doc-19 | qa | chat | 24466.7 | 14156.0 | 10310.7 | 42.1418 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13717.0/{"step.finished": 1} ｜ retrieve:3560.3/{"retrieval.completed": 1} |
| insight-03 | analysis | analysis | 54781.5 | 57528.0 | -2746.5 | 5.0136 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:41952.0/{"step.finished": 1} ｜ retrieve:23793.2/{"retrieval.completed": 3} |
| scope-03 | qa | chat | 15265.9 | 7759.0 | 7506.9 | 49.1743 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| unsupported-03 | qa | chat | 25244.6 | 13641.0 | 11603.6 | 45.9647 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14501.0/{"step.finished": 1} ｜ retrieve:4836.9/{"retrieval.completed": 1} |
| approval-04 | qa | chat | 47154.1 | 41904.0 | 5250.1 | 11.1339 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:32608.0/{"step.finished": 1} ｜ retrieve:15608.8/{"retrieval.completed": 2} |
| approval-02 | qa | chat | 62233.1 | 56595.0 | 5638.1 | 9.0596 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:51516.0/{"step.finished": 2} ｜ retrieve:24520.2/{"retrieval.completed": 4} |
| chart-04 | analysis | analysis | 66646.5 | 27367.0 | 39279.5 | 58.9371 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 24641.0 | 0 | generate:27609.0/{"step.finished": 1} |
| doc-09 | qa | chat | 25089.2 | 15525.0 | 9564.2 | 38.1208 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15070.0/{"step.finished": 1} ｜ retrieve:3393.8/{"retrieval.completed": 1} |
| data-08 | analysis | analysis | 37423.8 | 29680.0 | 7743.8 | 20.6922 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:26376.0/{"step.finished": 1} ｜ retrieve:9111.9/{"retrieval.completed": 2} |
| doc-03 | qa | chat | 35137.8 | 27024.0 | 8113.8 | 23.0914 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:24019.0/{"step.finished": 2} ｜ retrieve:13017.5/{"retrieval.completed": 3} |
| metric-03 | qa | chat | 29653.7 | 17845.0 | 11808.7 | 39.822 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:17434.0/{"step.finished": 1} ｜ retrieve:4833.0/{"retrieval.completed": 1} |
| unsupported-04 | qa | chat | 31316.3 | 29003.0 | 2313.3 | 7.3869 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:23106.0/{"step.finished": 1} ｜ retrieve:13531.5/{"retrieval.completed": 2} |
| data-03 | analysis | analysis | 25402.1 | 13739.0 | 11663.1 | 45.9139 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14286.0/{"step.finished": 1} |
| report-06 | report | analysis | 70608.4 | 86634.0 | -16025.6 | 22.6964 | 8 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 7 | generate:90461.0/{"step.finished": 2} ｜ retrieve:27026.9/{"retrieval.completed": 3} |
| metric-02 | qa | chat | 28665.8 | 17131.0 | 11534.8 | 40.2389 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:17564.0/{"step.finished": 1} ｜ retrieve:5310.8/{"retrieval.completed": 1} |
| data-05 | analysis | analysis | 33858.4 | 20315.0 | 13543.4 | 40.0001 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19602.0/{"step.finished": 1} ｜ retrieve:4828.3/{"retrieval.completed": 1} |
| metric-08 | analysis | analysis | 33432.2 | 34530.0 | -1097.8 | 3.2837 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:22417.0/{"step.finished": 1} ｜ retrieve:16965.0/{"retrieval.completed": 3} |
| doc-17 | qa | chat | 26241.6 | 15899.0 | 10342.6 | 39.413 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16817.0/{"step.finished": 1} ｜ retrieve:3511.6/{"retrieval.completed": 1} |
| unsupported-02 | qa | chat | 34142.0 | 35130.0 | -988.0 | 2.8938 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:24502.0/{"step.finished": 1} ｜ retrieve:23912.0/{"retrieval.completed": 3} |
| metric-12 | analysis | analysis | 50336.4 | 54209.0 | -3872.6 | 7.6934 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:48944.0/{"step.finished": 2} ｜ retrieve:23432.2/{"retrieval.completed": 3} |
| doc-15 | qa | chat | 33349.3 | 25061.0 | 8288.3 | 24.853 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:24776.0/{"step.finished": 1} ｜ retrieve:9936.2/{"retrieval.completed": 2} |
| metric-13 | analysis | analysis | 39261.8 | 25206.0 | 14055.8 | 35.8002 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:36673.0/{"step.finished": 2} ｜ retrieve:5000.6/{"retrieval.completed": 1} |
| doc-07 | qa | chat | 8206.8 | 2787.0 | 5419.8 | 66.0404 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| data-01 | analysis | analysis | 23772.1 | 13350.0 | 10422.1 | 43.8417 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13053.0/{"step.finished": 1} |
| tool-03 | report | analysis | 45679.8 | 50407.0 | -4727.2 | 10.3486 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 2670.0 | 3 | generate:32893.0/{"step.finished": 1} ｜ retrieve:24656.8/{"retrieval.completed": 3} |
| chat-06 | qa | chat | 9739.2 | 4294.0 | 5445.2 | 55.9101 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| scope-05 | report | analysis | 287835.5 | 47308.0 | 240527.5 | 83.5642 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 224506.0 | 3 | generate:33362.0/{"step.finished": 1} ｜ retrieve:17255.8/{"retrieval.completed": 3} |
| doc-04 | qa | chat | 32592.1 | 22435.0 | 10157.1 | 31.1643 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22469.0/{"step.finished": 1} ｜ retrieve:4978.4/{"retrieval.completed": 1} |
| metric-01 | qa | chat | 28511.5 | 17989.0 | 10522.5 | 36.9062 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:17360.0/{"step.finished": 1} ｜ retrieve:5918.1/{"retrieval.completed": 1} |
| chat-10 | qa | chat | 16065.4 | 4260.0 | 11805.4 | 73.4834 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:2887.0/{"step.finished": 1} |
| scope-06 | qa | chat | 34599.7 | 31239.0 | 3360.7 | 9.7131 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:24820.0/{"step.finished": 1} ｜ retrieve:13444.4/{"retrieval.completed": 2} |
| doc-01 | qa | chat | 59902.6 | 39021.0 | 20881.6 | 34.8593 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:27841.0/{"step.finished": 1} ｜ retrieve:19379.7/{"retrieval.completed": 3} |
| metric-10 | qa | chat | 39911.3 | 25106.0 | 14805.3 | 37.0955 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:30205.0/{"step.finished": 2} ｜ retrieve:5887.0/{"retrieval.completed": 1} |
| doc-12 | qa | chat | 34158.5 | 18983.0 | 15175.5 | 44.4267 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19771.0/{"step.finished": 2} ｜ retrieve:6556.5/{"retrieval.completed": 2} |
| metric-04 | qa | chat | 73359.8 | 65342.0 | 8017.8 | 10.9294 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:102016.0/{"step.finished": 2} ｜ retrieve:10921.7/{"retrieval.completed": 2} |
| doc-08 | qa | chat | 31835.5 | 26490.0 | 5345.5 | 16.791 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:21192.0/{"step.finished": 1} ｜ retrieve:10943.3/{"retrieval.completed": 2} |
| doc-13 | qa | chat | 36195.8 | 38209.0 | -2013.2 | 5.562 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:25748.0/{"step.finished": 1} ｜ retrieve:19150.6/{"retrieval.completed": 3} |
| metric-18 | report | analysis | 40879.8 | 46750.0 | -5870.2 | 14.3597 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:28440.0/{"step.finished": 1} ｜ retrieve:25641.8/{"retrieval.completed": 3} |
| scope-04 | qa | chat | 24404.1 | 10133.0 | 14271.1 | 58.4783 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:6985.0/{"step.finished": 1} |
| data-04 | analysis | analysis | 24351.4 | 14269.0 | 10082.4 | 41.4038 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13841.0/{"step.finished": 1} ｜ retrieve:3248.9/{"retrieval.completed": 1} |
| report-05 | report | analysis | 37075.6 | 18406.0 | 18669.6 | 50.3555 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 4137.0 | 0 | generate:18040.0/{"step.finished": 1} ｜ retrieve:2498.0/{"retrieval.completed": 1} |
| tool-01 | report | analysis | 26510.3 | 6628.0 | 19882.3 | 74.9984 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 8876.0 | 0 | generate:5352.0/{"step.finished": 1} |
| doc-02 | qa | chat | 29243.4 | 22432.0 | 6811.4 | 23.2921 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:19041.0/{"step.finished": 1} ｜ retrieve:6768.1/{"retrieval.completed": 2} |
| tool-04 | report | analysis | 19258.0 | 3791.0 | 15467.0 | 80.3147 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a3_event_on_sibling_trace] reflect[no_event/a2_leg_has_no_span] | 4747.0 | 0 | — |
| data-09 | analysis | analysis | 31948.9 | 20638.0 | 11310.9 | 35.4031 | 6 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19748.0/{"step.finished": 1} |
| approval-06 | qa | chat | 8338.8 | 2180.0 | 6158.8 | 73.8571 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| data-07 | analysis | analysis | 52155.0 | 75779.0 | -23624.0 | 45.2958 | 8 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 6 | generate:54960.0/{"step.finished": 2} ｜ retrieve:40223.8/{"retrieval.completed": 3} |
| report-01 | report | analysis | 76718.5 | 83621.0 | -6902.5 | 8.9972 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:65852.0/{"step.finished": 1} ｜ retrieve:32351.1/{"retrieval.completed": 3} |
| chat-07 | qa | chat | 36781.6 | 26544.0 | 10237.6 | 27.8335 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:26925.0/{"step.finished": 1} ｜ retrieve:5502.7/{"retrieval.completed": 1} |
| report-07 | report | analysis | 44515.7 | 41432.0 | 3083.7 | 6.9272 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 6629.0 | 3 | generate:26158.0/{"step.finished": 1} ｜ retrieve:21105.5/{"retrieval.completed": 3} |
| report-11 | report | analysis | 53045.5 | 25263.0 | 27782.5 | 52.3748 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 15556.0 | 0 | generate:25556.0/{"step.finished": 1} |
| doc-16 | qa | chat | 33978.6 | 28583.0 | 5395.6 | 15.8794 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:22321.0/{"step.finished": 1} ｜ retrieve:10323.5/{"retrieval.completed": 2} |
| doc-18 | qa | chat | 31729.1 | 21612.0 | 10117.1 | 31.8859 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22139.0/{"step.finished": 1} ｜ retrieve:3836.2/{"retrieval.completed": 1} |
| insight-01 | analysis | analysis | 38579.6 | 25115.0 | 13464.6 | 34.9008 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:24437.0/{"step.finished": 1} |
| metric-14 | qa | chat | 61030.9 | 66457.0 | -5426.1 | 8.8907 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:64973.0/{"step.finished": 2} ｜ retrieve:23663.5/{"retrieval.completed": 3} |
| data-06 | analysis | analysis | 47196.4 | 53961.0 | -6764.6 | 14.3329 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:34665.0/{"step.finished": 1} ｜ retrieve:24870.8/{"retrieval.completed": 3} |
| approval-01 | qa | chat | 37446.0 | 31160.0 | 6286.0 | 16.7868 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:26694.0/{"step.finished": 2} ｜ retrieve:16532.5/{"retrieval.completed": 3} |
| report-10 | report | analysis | 38735.2 | 26734.0 | 12001.2 | 30.9827 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 5135.0 | 1 | generate:22537.0/{"step.finished": 1} ｜ retrieve:8421.2/{"retrieval.completed": 2} |
| insight-05 | qa | chat | 49823.3 | 52888.0 | -3064.7 | 6.1511 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:36410.0/{"step.finished": 1} ｜ retrieve:26907.7/{"retrieval.completed": 3} |
| insight-02 | analysis | analysis | 37682.7 | 24714.0 | 12968.7 | 34.4155 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:25106.0/{"step.finished": 1} |
| metric-06 | analysis | analysis | 35734.2 | 41613.0 | -5878.8 | 16.4515 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:23829.0/{"step.finished": 1} ｜ retrieve:21394.7/{"retrieval.completed": 3} |
| report-12 | report | analysis | 43335.6 | 25987.0 | 17348.6 | 40.0331 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 3297.0 | 0 | generate:27366.0/{"step.finished": 1} ｜ retrieve:12705.8/{"retrieval.completed": 2} |
| tool-02 | report | analysis | 20928.5 | 6808.0 | 14120.5 | 67.4702 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 4001.0 | 0 | generate:5510.0/{"step.finished": 1} |

### 4.2 窗 run19（105 枚）
| 题号 | 车道 | tier | 端到端ms | 分段进账ms | 缺口ms | 误差% | 段数 | 缺段（型/形） | 配对孤儿ms | 未决 | 未登记账 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| chat-12 | qa | chat | 25652.2 | 15979.0 | 9673.2 | 37.709 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15997.0/{"step.finished": 1} ｜ retrieve:3381.6/{"retrieval.completed": 1} |
| scope-01 | qa | chat | 24700.1 | 15312.0 | 9388.1 | 38.0083 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15568.0/{"step.finished": 1} ｜ retrieve:7402.8/{"retrieval.completed": 1} |
| insight-04 | analysis | analysis | 49599.9 | 51225.0 | -1625.1 | 3.2764 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:40254.0/{"step.finished": 1} ｜ retrieve:24343.1/{"retrieval.completed": 3} |
| tool-04 | report | analysis | 10979.0 | 1792.0 | 9187.0 | 83.6779 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a3_event_on_sibling_trace] reflect[no_event/a2_leg_has_no_span] | 3555.0 | 0 | — |
| metric-08 | analysis | analysis | 36498.4 | 44074.0 | -7575.6 | 20.756 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:27396.0/{"step.finished": 1} ｜ retrieve:22869.1/{"retrieval.completed": 3} |
| report-05 | report | analysis | 27906.9 | 15000.0 | 12906.9 | 46.2499 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 3228.0 | 0 | generate:14692.0/{"step.finished": 1} ｜ retrieve:2938.8/{"retrieval.completed": 1} |
| metric-07 | analysis | analysis | 33534.2 | 37705.0 | -4170.8 | 12.4375 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:24496.0/{"step.finished": 1} ｜ retrieve:18167.0/{"retrieval.completed": 3} |
| metric-01 | qa | chat | 30617.2 | 21197.0 | 9420.2 | 30.7677 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:20577.0/{"step.finished": 1} ｜ retrieve:5658.6/{"retrieval.completed": 1} |
| data-01 | analysis | analysis | 19947.7 | 13000.0 | 6947.7 | 34.8296 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:11022.0/{"step.finished": 1} |
| metric-04 | qa | chat | 79443.4 | 73730.0 | 5713.4 | 7.1918 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:109601.0/{"step.finished": 2} ｜ retrieve:15352.8/{"retrieval.completed": 2} |
| chat-08 | qa | chat | 23084.2 | 14458.0 | 8626.2 | 37.3684 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14223.0/{"step.finished": 1} ｜ retrieve:4604.6/{"retrieval.completed": 1} |
| chat-02 | qa | chat | 11343.1 | 5865.0 | 5478.1 | 48.2946 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| doc-19 | qa | chat | 26790.0 | 17485.0 | 9305.0 | 34.7331 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16770.0/{"step.finished": 1} ｜ retrieve:5643.3/{"retrieval.completed": 1} |
| approval-05 | qa | chat | 38511.5 | 43712.0 | -5200.5 | 13.5038 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:28708.0/{"step.finished": 1} ｜ retrieve:20845.3/{"retrieval.completed": 3} |
| report-12 | report | analysis | 34771.3 | 29465.0 | 5306.3 | 15.2606 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 3092.0 | 1 | generate:22690.0/{"step.finished": 1} ｜ retrieve:13603.7/{"retrieval.completed": 2} |
| metric-15 | qa | chat | 39448.8 | 45386.0 | -5937.2 | 15.0504 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:35886.0/{"step.finished": 2} ｜ retrieve:20406.8/{"retrieval.completed": 3} |
| scope-06 | qa | chat | 18572.4 | 14080.0 | 4492.4 | 24.1886 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| data-05 | analysis | analysis | 27958.9 | 17903.0 | 10055.9 | 35.9667 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:18258.0/{"step.finished": 1} ｜ retrieve:3324.8/{"retrieval.completed": 1} |
| metric-14 | qa | chat | 55381.1 | 59722.0 | -4340.9 | 7.8382 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:62581.0/{"step.finished": 2} ｜ retrieve:25226.2/{"retrieval.completed": 3} |
| doc-17 | qa | chat | 32879.0 | 20399.0 | 12480.0 | 37.9574 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:20620.0/{"step.finished": 1} ｜ retrieve:4928.9/{"retrieval.completed": 1} |
| approval-02 | qa | chat | 62290.8 | 60868.0 | 1422.8 | 2.2841 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:51502.0/{"step.finished": 2} ｜ retrieve:25716.1/{"retrieval.completed": 4} |
| report-04 | report | analysis | 54694.9 | 43104.0 | 11590.9 | 21.1919 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 9412.0 | 2 | generate:36350.0/{"step.finished": 1} ｜ retrieve:15520.9/{"retrieval.completed": 3} |
| chat-10 | qa | chat | 14207.8 | 3846.0 | 10361.8 | 72.9304 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:2678.0/{"step.finished": 1} |
| chat-01 | qa | chat | 31345.2 | 18981.0 | 12364.2 | 39.4453 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19708.0/{"step.finished": 1} ｜ retrieve:4388.7/{"retrieval.completed": 1} |
| doc-07 | qa | chat | 7363.4 | 2832.0 | 4531.4 | 61.5395 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| doc-16 | qa | chat | 38339.8 | 33040.0 | 5299.8 | 13.8232 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:26065.0/{"step.finished": 1} ｜ retrieve:14921.2/{"retrieval.completed": 2} |
| doc-03 | qa | chat | 37204.6 | 28959.0 | 8245.6 | 22.1629 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:24788.0/{"step.finished": 2} ｜ retrieve:13317.1/{"retrieval.completed": 3} |
| report-06 | report | analysis | 70471.0 | 79747.0 | -9276.0 | 13.1629 | 8 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 7 | generate:85700.0/{"step.finished": 2} ｜ retrieve:23671.3/{"retrieval.completed": 3} |
| metric-16 | report | analysis | 38381.4 | 31140.0 | 7241.4 | 18.867 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:30637.0/{"step.finished": 1} ｜ retrieve:26704.8/{"retrieval.completed": 3} |
| report-03 | report | analysis | 11009.8 | 6409.0 | 4600.8 | 41.7882 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| data-11 | qa | chat | 12356.2 | 8810.0 | 3546.2 | 28.6998 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| scope-03 | qa | chat | 10161.2 | 5713.0 | 4448.2 | 43.7763 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| chart-02 | analysis | analysis | 118322.7 | 31008.0 | 87314.7 | 73.7937 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 69234.0 | 0 | generate:31266.0/{"step.finished": 1} |
| insight-01 | analysis | analysis | 33660.8 | 24120.0 | 9540.8 | 28.3439 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:24148.0/{"step.finished": 1} |
| chart-03 | qa | chat | 16800.6 | 3994.0 | 12806.6 | 76.227 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 4404.0 | 0 | generate:2988.0/{"step.finished": 1} |
| doc-18 | qa | chat | 32488.1 | 23258.0 | 9230.1 | 28.4107 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:23411.0/{"step.finished": 1} ｜ retrieve:4707.6/{"retrieval.completed": 1} |
| unsupported-02 | qa | chat | 34265.5 | 33494.0 | 771.5 | 2.2515 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:23292.0/{"step.finished": 1} ｜ retrieve:18896.8/{"retrieval.completed": 3} |
| doc-13 | qa | chat | 33640.1 | 41742.0 | -8101.9 | 24.0841 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:24869.0/{"step.finished": 1} ｜ retrieve:22238.4/{"retrieval.completed": 3} |
| chart-01 | analysis | analysis | 89069.4 | 1886.0 | 87183.4 | 97.8826 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a3_event_on_sibling_trace] reflect[no_event/a2_leg_has_no_span] | 70487.0 | 0 | — |
| insight-02 | analysis | analysis | 32003.2 | 22467.0 | 9536.2 | 29.7976 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22604.0/{"step.finished": 1} |
| report-01 | report | analysis | 69706.2 | 79229.0 | -9522.8 | 13.6613 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:61883.0/{"step.finished": 1} ｜ retrieve:22811.8/{"retrieval.completed": 3} |
| approval-04 | qa | chat | 28404.0 | 25953.0 | 2451.0 | 8.6291 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:21236.0/{"step.finished": 1} ｜ retrieve:10588.4/{"retrieval.completed": 2} |
| metric-13 | analysis | analysis | 34724.9 | 22843.0 | 11881.9 | 34.2172 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:34002.0/{"step.finished": 2} ｜ retrieve:4016.9/{"retrieval.completed": 1} |
| doc-09 | qa | chat | 25380.1 | 15222.0 | 10158.1 | 40.0239 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15414.0/{"step.finished": 1} ｜ retrieve:4957.1/{"retrieval.completed": 1} |
| data-02 | analysis | analysis | 15444.9 | 7686.0 | 7758.9 | 50.236 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:7780.0/{"step.finished": 1} |
| chat-03 | qa | chat | 12912.0 | 6902.0 | 6010.0 | 46.5458 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| chat-06 | qa | chat | 29047.7 | 26208.0 | 2839.7 | 9.776 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:19785.0/{"step.finished": 1} ｜ retrieve:10819.6/{"retrieval.completed": 2} |
| unsupported-03 | qa | chat | 18706.6 | 12355.0 | 6351.6 | 33.9538 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:11592.0/{"step.finished": 1} ｜ retrieve:4045.0/{"retrieval.completed": 1} |
| data-09 | analysis | analysis | 25673.9 | 17991.0 | 7682.9 | 29.9249 | 6 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:17919.0/{"step.finished": 1} |
| doc-01 | qa | chat | 32203.7 | 30084.0 | 2119.7 | 6.5822 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:24275.0/{"step.finished": 1} ｜ retrieve:18091.5/{"retrieval.completed": 3} |
| chat-11 | qa | chat | 30162.6 | 21681.0 | 8481.6 | 28.1196 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22101.0/{"step.finished": 1} ｜ retrieve:6248.1/{"retrieval.completed": 1} |
| metric-02 | qa | chat | 23350.1 | 15171.0 | 8179.1 | 35.0281 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14587.0/{"step.finished": 1} ｜ retrieve:4520.0/{"retrieval.completed": 1} |
| doc-08 | qa | chat | 33446.7 | 29356.0 | 4090.7 | 12.2305 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:22720.0/{"step.finished": 1} ｜ retrieve:14696.7/{"retrieval.completed": 2} |
| data-07 | analysis | analysis | 43852.6 | 52840.0 | -8987.4 | 20.4946 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 5 | generate:48936.0/{"step.finished": 2} ｜ retrieve:34508.4/{"retrieval.completed": 3} |
| chat-09 | qa | chat | 9885.9 | 3821.0 | 6064.9 | 61.349 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| scope-02 | qa | chat | 53360.4 | 38304.0 | 15056.4 | 28.2164 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 5142.0 | 1 | generate:38356.0/{"step.finished": 1} ｜ retrieve:25188.7/{"retrieval.completed": 3} |
| chat-07 | qa | chat | 36464.5 | 27138.0 | 9326.5 | 25.5769 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:27209.0/{"step.finished": 1} ｜ retrieve:4676.7/{"retrieval.completed": 1} |
| approval-06 | qa | chat | 5917.1 | 2147.0 | 3770.1 | 63.7153 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| metric-09 | analysis | analysis | 36455.5 | 38567.0 | -2111.5 | 5.792 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:24990.0/{"step.finished": 1} ｜ retrieve:17718.7/{"retrieval.completed": 3} |
| metric-19 | report | analysis | 30959.7 | 33095.0 | -2135.3 | 6.897 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:23339.0/{"step.finished": 1} ｜ retrieve:23105.8/{"retrieval.completed": 3} |
| metric-11 | qa | chat | 42974.4 | 34968.0 | 8006.4 | 18.6306 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:55801.0/{"step.finished": 2} ｜ retrieve:18703.5/{"retrieval.completed": 1} |
| scope-05 | report | analysis | 279563.5 | 44354.0 | 235209.5 | 84.1346 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 221450.0 | 3 | generate:31008.0/{"step.finished": 1} ｜ retrieve:20834.9/{"retrieval.completed": 3} |
| scope-04 | qa | chat | 17258.2 | 7776.0 | 9482.2 | 54.9432 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:6413.0/{"step.finished": 1} |
| chat-04 | qa | chat | 33689.9 | 24209.0 | 9480.9 | 28.1417 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:24411.0/{"step.finished": 1} ｜ retrieve:7255.4/{"retrieval.completed": 1} |
| doc-15 | qa | chat | 33486.9 | 31185.0 | 2301.9 | 6.874 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:24706.0/{"step.finished": 1} ｜ retrieve:11426.5/{"retrieval.completed": 2} |
| data-06 | analysis | analysis | 35950.3 | 25670.0 | 10280.3 | 28.5959 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:26175.0/{"step.finished": 1} ｜ retrieve:18978.8/{"retrieval.completed": 3} |
| report-10 | report | analysis | 36473.8 | 22954.0 | 13519.8 | 37.0672 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 5348.0 | 0 | generate:22213.0/{"step.finished": 1} ｜ retrieve:11447.5/{"retrieval.completed": 2} |
| report-08 | qa | chat | 13288.1 | 8724.0 | 4564.1 | 34.3473 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| chart-04 | analysis | analysis | 63899.5 | 24965.0 | 38934.5 | 60.9308 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 25372.0 | 0 | generate:25080.0/{"step.finished": 1} |
| metric-17 | report | analysis | 25477.0 | 16247.0 | 9230.0 | 36.2288 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15422.0/{"step.finished": 1} ｜ retrieve:4058.7/{"retrieval.completed": 1} |
| data-12 | analysis | analysis | 46875.2 | 34129.0 | 12746.2 | 27.1918 | 17 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:40061.0/{"step.finished": 1} |
| doc-10 | qa | chat | 28050.6 | 18994.0 | 9056.6 | 32.2867 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:18938.0/{"step.finished": 1} ｜ retrieve:6140.7/{"retrieval.completed": 1} |
| data-03 | analysis | analysis | 20333.3 | 13004.0 | 7329.3 | 36.0458 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12600.0/{"step.finished": 1} |
| tool-03 | report | analysis | 47330.1 | 42262.0 | 5068.1 | 10.708 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 2185.0 | 2 | generate:35278.0/{"step.finished": 1} ｜ retrieve:25310.1/{"retrieval.completed": 3} |
| chat-05 | qa | chat | 16696.2 | 9434.0 | 7262.2 | 43.4961 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| report-09 | report | analysis | 32320.4 | 19108.0 | 13212.4 | 40.8794 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 2466.0 | 0 | generate:18354.0/{"step.finished": 1} ｜ retrieve:4268.1/{"retrieval.completed": 1} |
| doc-02 | qa | chat | 33497.6 | 30638.0 | 2859.6 | 8.5367 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:23287.0/{"step.finished": 1} ｜ retrieve:10545.0/{"retrieval.completed": 2} |
| metric-10 | qa | chat | 30444.8 | 17417.0 | 13027.8 | 42.7915 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22266.0/{"step.finished": 2} ｜ retrieve:4940.0/{"retrieval.completed": 1} |
| insight-05 | qa | chat | 39691.1 | 37523.0 | 2168.1 | 5.4624 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:30709.0/{"step.finished": 1} ｜ retrieve:21642.1/{"retrieval.completed": 3} |
| insight-06 | analysis | analysis | 17522.5 | 10115.0 | 7407.5 | 42.2742 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:10235.0/{"step.finished": 1} |
| approval-01 | qa | chat | 36790.1 | 26435.0 | 10355.1 | 28.1464 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:27988.0/{"step.finished": 2} ｜ retrieve:15521.8/{"retrieval.completed": 3} |
| metric-06 | analysis | analysis | 37277.9 | 36229.0 | 1048.9 | 2.8137 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:27842.0/{"step.finished": 1} ｜ retrieve:24147.6/{"retrieval.completed": 3} |
| doc-12 | qa | chat | 36505.8 | 22694.0 | 13811.8 | 37.8345 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:23360.0/{"step.finished": 2} ｜ retrieve:10894.4/{"retrieval.completed": 2} |
| data-10 | analysis | analysis | 20501.4 | 12644.0 | 7857.4 | 38.3262 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12813.0/{"step.finished": 1} |
| metric-12 | analysis | analysis | 49811.8 | 56315.0 | -6503.2 | 13.0555 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:48987.0/{"step.finished": 2} ｜ retrieve:27899.8/{"retrieval.completed": 3} |
| report-07 | report | analysis | 59828.6 | 54667.0 | 5161.6 | 8.6273 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 6407.0 | 2 | generate:43786.0/{"step.finished": 1} ｜ retrieve:24904.2/{"retrieval.completed": 3} |
| tool-02 | report | analysis | 25227.5 | 6673.0 | 18554.5 | 73.5487 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 3518.0 | 0 | generate:4760.0/{"step.finished": 1} |
| tool-01 | report | analysis | 24506.6 | 6382.0 | 18124.6 | 73.958 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 9324.0 | 0 | generate:4967.0/{"step.finished": 1} |
| insight-03 | analysis | analysis | 42326.8 | 38307.0 | 4019.8 | 9.4971 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:32820.0/{"step.finished": 1} ｜ retrieve:22291.4/{"retrieval.completed": 3} |
| data-08 | analysis | analysis | 34507.1 | 31271.0 | 3236.1 | 9.3781 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:26493.0/{"step.finished": 1} ｜ retrieve:8942.4/{"retrieval.completed": 2} |
| report-11 | report | analysis | 48485.7 | 24374.0 | 24111.7 | 49.7295 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 14078.0 | 0 | generate:24183.0/{"step.finished": 1} |
| doc-11 | qa | chat | 41799.2 | 35082.0 | 6717.2 | 16.0702 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:30690.0/{"step.finished": 1} ｜ retrieve:12057.6/{"retrieval.completed": 2} |
| insight-07 | analysis | analysis | 71012.1 | 33301.0 | 37711.1 | 53.1052 | 16 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 21741.0 | 0 | generate:38497.0/{"step.finished": 1} |
| metric-05 | qa | chat | 54994.0 | 62513.0 | -7519.0 | 13.6724 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:57710.0/{"step.finished": 2} ｜ retrieve:28049.6/{"retrieval.completed": 3} |
| approval-03 | qa | chat | 6211.9 | 2208.0 | 4003.9 | 64.4553 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| metric-18 | report | analysis | 6411.1 | 2189.0 | 4222.1 | 65.8561 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| unsupported-01 | qa | chat | 18916.3 | 11849.0 | 7067.3 | 37.3609 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:10502.0/{"step.finished": 1} ｜ retrieve:3499.3/{"retrieval.completed": 1} |
| metric-03 | qa | chat | 31272.4 | 16719.0 | 14553.4 | 46.5375 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15594.0/{"step.finished": 1} ｜ retrieve:3744.7/{"retrieval.completed": 1} |
| unsupported-04 | qa | chat | 29269.7 | 27269.0 | 2000.7 | 6.8354 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:21540.0/{"step.finished": 1} ｜ retrieve:10902.5/{"retrieval.completed": 2} |
| data-04 | analysis | analysis | 23272.5 | 14347.0 | 8925.5 | 38.3521 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13469.0/{"step.finished": 1} ｜ retrieve:4108.3/{"retrieval.completed": 1} |
| report-02 | report | analysis | 50478.6 | 44163.0 | 6315.6 | 12.5114 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 8968.0 | 3 | generate:31583.0/{"step.finished": 1} ｜ retrieve:17207.4/{"retrieval.completed": 3} |
| doc-06 | qa | chat | 46990.4 | 52929.0 | -5938.6 | 12.6379 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:38034.0/{"step.finished": 1} ｜ retrieve:22027.3/{"retrieval.completed": 3} |
| doc-05 | qa | chat | 24319.4 | 14454.0 | 9865.4 | 40.566 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14506.0/{"step.finished": 1} ｜ retrieve:4175.3/{"retrieval.completed": 1} |
| doc-04 | qa | chat | 30686.4 | 21858.0 | 8828.4 | 28.7697 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:21888.0/{"step.finished": 1} ｜ retrieve:4821.2/{"retrieval.completed": 1} |
| doc-14 | qa | chat | 48281.2 | 56520.0 | -8238.8 | 17.0642 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:35592.0/{"step.finished": 1} ｜ retrieve:24306.8/{"retrieval.completed": 3} |

### 4.3 窗 run20k（106 枚）
| 题号 | 车道 | tier | 端到端ms | 分段进账ms | 缺口ms | 误差% | 段数 | 缺段（型/形） | 配对孤儿ms | 未决 | 未登记账 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| metric-06 | analysis | analysis | 31629.5 | 29640.0 | 1989.5 | 6.29 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:24651.0/{"step.finished": 1} ｜ retrieve:19370.4/{"retrieval.completed": 3} |
| doc-11 | qa | chat | 35345.4 | 27842.0 | 7503.4 | 21.2288 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:24712.0/{"step.finished": 1} ｜ retrieve:6271.5/{"retrieval.completed": 2} |
| doc-15 | qa | chat | 26867.7 | 19881.0 | 6986.7 | 26.0041 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19250.0/{"step.finished": 1} ｜ retrieve:8758.3/{"retrieval.completed": 2} |
| chart-03 | qa | chat | 17209.8 | 4417.0 | 12792.8 | 74.3344 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 4533.0 | 0 | generate:4094.0/{"step.finished": 1} |
| approval-01 | qa | chat | 37510.8 | 32120.0 | 5390.8 | 14.3713 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:27659.0/{"step.finished": 2} ｜ retrieve:12787.3/{"retrieval.completed": 3} |
| approval-05 | qa | chat | 39615.0 | 37195.0 | 2420.0 | 6.1088 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:29721.0/{"step.finished": 1} ｜ retrieve:25102.0/{"retrieval.completed": 3} |
| insight-02 | analysis | analysis | 37554.7 | 23704.0 | 13850.7 | 36.8814 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:24792.0/{"step.finished": 1} |
| metric-18 | report | analysis | 36433.6 | 41687.0 | -5253.4 | 14.4191 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:25349.0/{"step.finished": 1} ｜ retrieve:23611.0/{"retrieval.completed": 3} |
| unsupported-01 | qa | chat | 19763.7 | 12122.0 | 7641.7 | 38.6653 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:11897.0/{"step.finished": 1} ｜ retrieve:3982.5/{"retrieval.completed": 1} |
| metric-05 | qa | chat | 42546.4 | 42683.0 | -136.6 | 0.3211 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:46910.0/{"step.finished": 2} ｜ retrieve:19199.3/{"retrieval.completed": 3} |
| scope-06 | qa | chat | 33638.3 | 30363.0 | 3275.3 | 9.7368 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:24245.0/{"step.finished": 1} ｜ retrieve:13236.1/{"retrieval.completed": 2} |
| insight-06 | analysis | analysis | 20944.5 | 12547.0 | 8397.5 | 40.0941 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12191.0/{"step.finished": 1} |
| doc-04 | qa | chat | 27490.9 | 19804.0 | 7686.9 | 27.9616 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19799.0/{"step.finished": 1} ｜ retrieve:3485.1/{"retrieval.completed": 1} |
| metric-03 | qa | chat | 20949.9 | 14050.0 | 6899.9 | 32.9352 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13846.0/{"step.finished": 1} ｜ retrieve:3850.9/{"retrieval.completed": 1} |
| chat-04 | qa | chat | 31098.0 | 23758.0 | 7340.0 | 23.6028 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:23774.0/{"step.finished": 1} ｜ retrieve:5280.8/{"retrieval.completed": 1} |
| doc-12 | qa | chat | 26724.4 | 15419.0 | 11305.4 | 42.3037 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:15818.0/{"step.finished": 2} ｜ retrieve:5813.5/{"retrieval.completed": 2} |
| metric-04 | qa | chat | 69295.9 | 60309.0 | 8986.9 | 12.9689 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:99573.0/{"step.finished": 2} ｜ retrieve:14600.8/{"retrieval.completed": 2} |
| data-05 | analysis | analysis | 33195.1 | 21611.0 | 11584.1 | 34.897 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:21080.0/{"step.finished": 1} ｜ retrieve:4297.4/{"retrieval.completed": 1} |
| data-09 | analysis | analysis | 29327.9 | 19701.0 | 9626.9 | 32.8251 | 6 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:20555.0/{"step.finished": 1} |
| doc-18 | qa | chat | 24864.6 | 18017.0 | 6847.6 | 27.5396 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:17491.0/{"step.finished": 1} ｜ retrieve:3415.2/{"retrieval.completed": 1} |
| metric-13 | analysis | analysis | 30442.0 | 21276.0 | 9166.0 | 30.1097 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:31113.0/{"step.finished": 2} ｜ retrieve:3253.9/{"retrieval.completed": 1} |
| chart-02 | analysis | analysis | 118995.8 | 31194.0 | 87801.8 | 73.7856 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 69696.0 | 0 | generate:30695.0/{"step.finished": 1} |
| chat-10 | qa | chat | 6128.0 | 2499.0 | 3629.0 | 59.22 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| approval-04 | qa | chat | 36697.5 | 33005.0 | 3692.5 | 10.062 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:28087.0/{"step.finished": 1} ｜ retrieve:12569.3/{"retrieval.completed": 2} |
| chat-11 | qa | chat | 34524.9 | 26812.0 | 7712.9 | 22.3401 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:26253.0/{"step.finished": 1} ｜ retrieve:6008.2/{"retrieval.completed": 1} |
| doc-03 | qa | chat | 40379.8 | 20803.0 | 19576.8 | 48.4817 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:21274.0/{"step.finished": 2} ｜ retrieve:11221.9/{"retrieval.completed": 3} |
| chat-09 | qa | chat | 8128.5 | 4000.0 | 4128.5 | 50.7904 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| metric-07 | analysis | analysis | 29063.8 | 29747.0 | -683.2 | 2.3507 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:21718.0/{"step.finished": 1} ｜ retrieve:18343.3/{"retrieval.completed": 3} |
| doc-01 | qa | chat | 31338.1 | 35915.0 | -4576.9 | 14.6049 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:24236.0/{"step.finished": 1} ｜ retrieve:18569.3/{"retrieval.completed": 3} |
| doc-14 | qa | chat | 40622.1 | 42990.0 | -2367.9 | 5.8291 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:30427.0/{"step.finished": 1} ｜ retrieve:18284.7/{"retrieval.completed": 3} |
| unsupported-02 | qa | chat | 36880.2 | 40122.0 | -3241.8 | 8.7901 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:25076.0/{"step.finished": 1} ｜ retrieve:19510.5/{"retrieval.completed": 3} |
| metric-16 | report | analysis | 44130.9 | 55410.0 | -11279.1 | 25.5583 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:34980.0/{"step.finished": 1} ｜ retrieve:31589.4/{"retrieval.completed": 3} |
| data-11 | qa | chat | 14753.1 | 9853.0 | 4900.1 | 33.214 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| doc-17 | qa | chat | 25121.6 | 16597.0 | 8524.6 | 33.9333 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16146.0/{"step.finished": 1} ｜ retrieve:3575.1/{"retrieval.completed": 1} |
| tool-01 | report | analysis | 25120.9 | 6936.0 | 18184.9 | 72.3895 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 9311.0 | 0 | generate:5289.0/{"step.finished": 1} |
| metric-01 | qa | chat | 20136.1 | 13247.0 | 6889.1 | 34.2127 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12599.0/{"step.finished": 1} ｜ retrieve:4608.6/{"retrieval.completed": 1} |
| metric-19 | report | analysis | 34475.6 | 37822.0 | -3346.4 | 9.7066 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:24292.0/{"step.finished": 1} ｜ retrieve:18511.1/{"retrieval.completed": 3} |
| chat-02 | qa | chat | 19034.5 | 12459.0 | 6575.5 | 34.5452 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:11615.0/{"step.finished": 1} ｜ retrieve:2864.9/{"retrieval.completed": 1} |
| report-12 | report | analysis | 38103.8 | 31339.0 | 6764.8 | 17.7536 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 3703.0 | 1 | generate:24994.0/{"step.finished": 1} ｜ retrieve:13164.0/{"retrieval.completed": 2} |
| report-04 | report | analysis | 77113.7 | 67351.0 | 9762.7 | 12.6601 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 9168.0 | 2 | generate:58023.0/{"step.finished": 1} ｜ retrieve:21497.6/{"retrieval.completed": 3} |
| data-10 | analysis | analysis | 23693.5 | 14695.0 | 8998.5 | 37.9788 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14341.0/{"step.finished": 1} |
| data-12 | analysis | analysis | 53086.9 | 38170.0 | 14916.9 | 28.099 | 17 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:45925.0/{"step.finished": 1} |
| chat-07 | qa | chat | 29317.5 | 22661.0 | 6656.5 | 22.7049 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22181.0/{"step.finished": 1} ｜ retrieve:3764.6/{"retrieval.completed": 1} |
| data-01 | analysis | analysis | 20101.4 | 12266.0 | 7835.4 | 38.9794 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12223.0/{"step.finished": 1} |
| report-08 | qa | chat | 9084.3 | 4147.0 | 4937.3 | 54.3498 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| scope-04 | qa | chat | 17247.3 | 8173.0 | 9074.3 | 52.6129 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:6630.0/{"step.finished": 1} |
| chat-06 | qa | chat | 23932.5 | 20460.0 | 3472.5 | 14.5096 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:16791.0/{"step.finished": 1} ｜ retrieve:8263.1/{"retrieval.completed": 2} |
| unsupported-03 | qa | chat | 22347.3 | 12958.0 | 9389.3 | 42.0154 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12523.0/{"step.finished": 1} ｜ retrieve:3484.0/{"retrieval.completed": 1} |
| report-01 | report | analysis | 69526.3 | 77667.0 | -8140.7 | 11.7088 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:61181.0/{"step.finished": 1} ｜ retrieve:24950.4/{"retrieval.completed": 3} |
| doc-19 | qa | chat | 19889.6 | 12880.0 | 7009.6 | 35.2425 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:11982.0/{"step.finished": 1} ｜ retrieve:3547.7/{"retrieval.completed": 1} |
| metric-02 | qa | chat | 21922.7 | 14351.0 | 7571.7 | 34.5382 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13733.0/{"step.finished": 1} ｜ retrieve:4680.2/{"retrieval.completed": 1} |
| report-11 | report | analysis | 48491.7 | 23744.0 | 24747.7 | 51.0349 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 13656.0 | 0 | generate:23603.0/{"step.finished": 1} |
| doc-10 | qa | chat | 23488.2 | 15172.0 | 8316.2 | 35.4059 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:14682.0/{"step.finished": 1} ｜ retrieve:3557.5/{"retrieval.completed": 1} |
| tool-04 | report | analysis | 11133.6 | 1906.0 | 9227.6 | 82.8806 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a3_event_on_sibling_trace] reflect[no_event/a2_leg_has_no_span] | 3659.0 | 0 | — |
| report-09 | report | analysis | 36019.5 | 21147.0 | 14872.5 | 41.2901 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 2441.0 | 0 | generate:19499.0/{"step.finished": 1} ｜ retrieve:4746.7/{"retrieval.completed": 1} |
| doc-09 | qa | chat | 20162.6 | 12996.0 | 7166.6 | 35.544 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12623.0/{"step.finished": 1} ｜ retrieve:3307.2/{"retrieval.completed": 1} |
| doc-07 | qa | chat | 6224.5 | 2500.0 | 3724.5 | 59.8361 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| scope-02 | qa | chat | 49481.2 | 47242.0 | 2239.2 | 4.5254 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 5477.0 | 3 | generate:34392.0/{"step.finished": 1} ｜ retrieve:17370.7/{"retrieval.completed": 3} |
| approval-03 | qa | chat | 6658.9 | 2314.0 | 4344.9 | 65.2495 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| report-02 | report | analysis | 54236.7 | 41106.0 | 13130.7 | 24.21 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 9453.0 | 2 | generate:35501.0/{"step.finished": 1} ｜ retrieve:20807.3/{"retrieval.completed": 3} |
| data-02 | analysis | analysis | 16188.8 | 9262.0 | 6926.8 | 42.7876 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:8560.0/{"step.finished": 1} |
| approval-06 | qa | chat | 6175.1 | 1932.0 | 4243.1 | 68.7131 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| metric-08 | analysis | analysis | 29105.2 | 26485.0 | 2620.2 | 9.0025 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:21763.0/{"step.finished": 1} ｜ retrieve:17201.7/{"retrieval.completed": 3} |
| chat-01 | qa | chat | 26034.7 | 19244.0 | 6790.7 | 26.0833 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:18749.0/{"step.finished": 1} ｜ retrieve:2820.2/{"retrieval.completed": 1} |
| chart-01 | analysis | analysis | 96434.1 | 2406.0 | 94028.1 | 97.505 | 1 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a3_event_on_sibling_trace] reflect[no_event/a2_leg_has_no_span] | 73539.0 | 0 | — |
| data-07 | analysis | analysis | 44308.6 | 66120.0 | -21811.4 | 49.2261 | 8 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 6 | generate:49264.0/{"step.finished": 2} ｜ retrieve:32947.8/{"retrieval.completed": 3} |
| data-03 | analysis | analysis | 20773.2 | 13531.0 | 7242.2 | 34.8632 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:12871.0/{"step.finished": 1} |
| doc-08 | qa | chat | 23114.3 | 20652.0 | 2462.3 | 10.6527 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:16582.0/{"step.finished": 1} ｜ retrieve:9019.7/{"retrieval.completed": 2} |
| doc-02 | qa | chat | 27818.9 | 25368.0 | 2450.9 | 8.8102 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:20188.0/{"step.finished": 1} ｜ retrieve:9470.6/{"retrieval.completed": 2} |
| data-04 | analysis | analysis | 21476.9 | 14282.0 | 7194.9 | 33.5006 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13644.0/{"step.finished": 1} ｜ retrieve:3790.6/{"retrieval.completed": 1} |
| tool-03 | report | analysis | 44226.6 | 48429.0 | -4202.4 | 9.502 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 1950.0 | 3 | generate:32307.0/{"step.finished": 1} ｜ retrieve:23183.0/{"retrieval.completed": 3} |
| doc-04 | qa | chat | 27490.9 | 18857.0 | 8633.9 | 31.4064 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19064.0/{"step.finished": 1} ｜ retrieve:3248.3/{"retrieval.completed": 1} |
| report-03 | report | analysis | 11316.0 | 6359.0 | 4957.0 | 43.8052 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| insight-01 | analysis | analysis | 34303.0 | 23267.0 | 11036.0 | 32.1721 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:22925.0/{"step.finished": 1} |
| chat-05 | qa | chat | 12493.3 | 8151.0 | 4342.3 | 34.757 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| insight-03 | analysis | analysis | 44959.9 | 49439.0 | -4479.1 | 9.9624 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:33953.0/{"step.finished": 1} ｜ retrieve:22803.2/{"retrieval.completed": 3} |
| doc-13 | qa | chat | 29770.5 | 33875.0 | -4104.5 | 13.7871 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:21344.0/{"step.finished": 1} ｜ retrieve:16704.7/{"retrieval.completed": 3} |
| chart-04 | analysis | analysis | 64264.4 | 24276.0 | 39988.4 | 62.2248 | 4 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 25234.0 | 0 | generate:24527.0/{"step.finished": 1} |
| report-10 | report | analysis | 30684.8 | 17033.0 | 13651.8 | 44.4904 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 5328.0 | 0 | generate:16265.0/{"step.finished": 1} ｜ retrieve:6295.0/{"retrieval.completed": 2} |
| data-08 | analysis | analysis | 33839.5 | 30618.0 | 3221.5 | 9.5199 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:25596.0/{"step.finished": 1} ｜ retrieve:10595.6/{"retrieval.completed": 2} |
| chat-03 | qa | chat | 11278.5 | 6167.0 | 5111.5 | 45.3207 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| report-06 | report | analysis | 65538.9 | 82756.0 | -17217.1 | 26.27 | 8 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 7 | generate:84186.0/{"step.finished": 2} ｜ retrieve:27626.4/{"retrieval.completed": 3} |
| chat-08 | qa | chat | 21304.0 | 14207.0 | 7097.0 | 33.313 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:13646.0/{"step.finished": 1} ｜ retrieve:4119.5/{"retrieval.completed": 1} |
| metric-17 | report | analysis | 27061.2 | 18036.0 | 9025.2 | 33.3511 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:17167.0/{"step.finished": 1} ｜ retrieve:6318.9/{"retrieval.completed": 1} |
| scope-01 | qa | chat | 26854.3 | 16314.0 | 10540.3 | 39.25 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16083.0/{"step.finished": 1} ｜ retrieve:5476.5/{"retrieval.completed": 1} |
| insight-05 | qa | chat | 43029.6 | 51244.0 | -8214.4 | 19.0901 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:34821.0/{"step.finished": 1} ｜ retrieve:22837.7/{"retrieval.completed": 3} |
| metric-12 | analysis | analysis | 42404.7 | 36943.0 | 5461.7 | 12.8799 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:44275.0/{"step.finished": 2} ｜ retrieve:19820.4/{"retrieval.completed": 3} |
| doc-06 | qa | chat | 39579.0 | 32264.0 | 7315.0 | 18.482 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:32007.0/{"step.finished": 1} ｜ retrieve:17233.6/{"retrieval.completed": 3} |
| metric-14 | qa | chat | 49009.7 | 48696.0 | 313.7 | 0.6401 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:56344.0/{"step.finished": 2} ｜ retrieve:22821.4/{"retrieval.completed": 3} |
| metric-11 | qa | chat | 32014.9 | 28306.0 | 3708.9 | 11.5849 | 7 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:46702.0/{"step.finished": 2} ｜ retrieve:3856.3/{"retrieval.completed": 1} |
| insight-07 | analysis | analysis | 83011.1 | 39763.0 | 43248.1 | 52.0992 | 16 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 23137.0 | 0 | generate:46074.0/{"step.finished": 1} |
| chat-12 | qa | chat | 26917.8 | 18563.0 | 8354.8 | 31.0382 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:18014.0/{"step.finished": 1} ｜ retrieve:3949.6/{"retrieval.completed": 1} |
| doc-16 | qa | chat | 28827.3 | 20545.0 | 8282.3 | 28.7308 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:19820.0/{"step.finished": 1} ｜ retrieve:8608.7/{"retrieval.completed": 2} |
| tool-02 | report | analysis | 24975.5 | 6577.0 | 18398.5 | 73.6662 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] reflect[no_event/a2_leg_has_no_span] | 4072.0 | 0 | generate:4438.0/{"step.finished": 1} |
| scope-05 | report | analysis | 287946.0 | 51164.0 | 236782.0 | 82.2314 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 222267.0 | 3 | generate:35927.0/{"step.finished": 1} ｜ retrieve:24870.6/{"retrieval.completed": 3} |
| insight-04 | analysis | analysis | 69036.8 | 81906.0 | -12869.2 | 18.6411 | 8 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 7 | generate:98556.0/{"step.finished": 2} ｜ retrieve:23204.6/{"retrieval.completed": 3} |
| scope-03 | qa | chat | 12709.5 | 7780.0 | 4929.5 | 38.7859 | 2 | rewrite[no_event/a0_path_not_taken] retrieve[no_event/a0_path_not_taken] generate[no_event/a1_call_site_no_identity] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | — |
| data-06 | analysis | analysis | 38785.7 | 43428.0 | -4642.3 | 11.9691 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:27560.0/{"step.finished": 1} ｜ retrieve:23663.4/{"retrieval.completed": 3} |
| report-05 | report | analysis | 28488.2 | 14726.0 | 13762.2 | 48.3084 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 3353.0 | 0 | generate:15090.0/{"step.finished": 1} ｜ retrieve:3257.8/{"retrieval.completed": 1} |
| metric-10 | qa | chat | 23629.2 | 14553.0 | 9076.2 | 38.4109 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:16946.0/{"step.finished": 2} ｜ retrieve:3653.9/{"retrieval.completed": 1} |
| metric-09 | analysis | analysis | 31376.1 | 32998.0 | -1621.9 | 5.1692 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:23725.0/{"step.finished": 1} ｜ retrieve:22926.9/{"retrieval.completed": 3} |
| approval-02 | qa | chat | 58284.0 | 59991.0 | -1707.0 | 2.9288 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 3 | generate:47448.0/{"step.finished": 2} ｜ retrieve:23636.6/{"retrieval.completed": 4} |
| unsupported-04 | qa | chat | 28472.4 | 26466.0 | 2006.4 | 7.0468 | 5 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 1 | generate:21172.0/{"step.finished": 1} ｜ retrieve:11322.4/{"retrieval.completed": 2} |
| metric-15 | qa | chat | 36694.1 | 37109.0 | -414.9 | 1.1307 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 2 | generate:34090.0/{"step.finished": 2} ｜ retrieve:21547.6/{"retrieval.completed": 3} |
| report-07 | report | analysis | 46351.0 | 52340.0 | -5989.0 | 12.921 | 6 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 6879.0 | 3 | generate:30010.0/{"step.finished": 1} ｜ retrieve:32406.1/{"retrieval.completed": 3} |
| doc-05 | qa | chat | 18134.0 | 11941.0 | 6193.0 | 34.1513 | 4 | rewrite[no_event/a2_leg_has_no_span] reflect[no_event/a2_leg_has_no_span] | 0 | 0 | generate:11203.0/{"step.finished": 1} ｜ retrieve:2719.7/{"retrieval.completed": 1} |

### 4.4 题号重复的那一格（分母按题号折叠，账按 trace 点名）
- run18：端到端腿 105 行 = 105 枚题号，`sidecar_duplicates` 空 ⇒ trace 粒度与题号粒度同数。
- run19：端到端腿 105 行 = 105 枚题号，`sidecar_duplicates` 空 ⇒ trace 粒度与题号粒度同数。
- **run20k／doc-04**：端到端腿 106 行只折成 105 枚分母（在册 `sidecar_duplicates` 已点名这枚），本尺按 trace 摆 2 行，两行都吃同一枚分母 27490.9／27490.9 ms；各发真读数是 27244.6／27490.9 ms（attempt 1／1，ts 10:02:43／10:03:03）。
  - 折叠规则现读自 `scripts/r631_stage_sum_delta.py::_collect_by_key`：同题取 attempt 最大，attempt 相等时取**末行** ⇒ 27490.9 ms 进账，27244.6 ms 掉到账外，差 246.3 ms（占该题端到端 0.9%）。
  - 判语：这格不是本席推的，是 R631 自己登记的重复；但它让 run20k 的 **106 行 ≠ 106 枚分母**。单这一枚就差 246.3 ms，量级已到 `1%` 线的同一数量级（§10 的 1% 目标 ms 为 37657.4 ms）——把覆盖面补齐之后还得分清「一题两发」该按几枚算，否则分母与分段不同源。

## 5 两组明账（一枚都不从母集里悄悄摘掉）
R631 纸面 §7 第③条的纪律：不参与的题也要点名。三窗母集 144／143／144 枚 = asked 105／105／106 ＋ no_denominator 20／19／19 ＋ resumed_head 19／19／19 ＋ bare_trace 0／0／0。「账本枚数 = 母集枚数」由尺当场自证，差一枚即 `UniverseError`。

### 5.1 窗 run18 第一组：`no_denominator`（有跨度无分母 = R631 的 skipped）
```text
## no_denominator 逐枚点名（明账，一枚不摘）
- trace-0786f6f2ecd94eb9ba6550caa8a7bcf6 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3297.0 ms ｜ worker=export ｜ 归题=report-12（头 trace-44e895d9db354d2c）
- trace-1039953c9cf74520a234c7710a3c2772 ｜ 原因码 no_request_started ｜ 跨度 14 枚合计 24641.0 ms ｜ worker=chart ｜ 归题=chart-04（头 trace-70dfb59bb9ae4647）
- trace-20a508a59d9e43b8939405617355c080 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 9990.0 ms ｜ worker=export ｜ 归题=report-04（头 trace-3f6465065ad247a3）
- trace-332e81f87aba48a083514ba74f7597cb ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 5135.0 ms ｜ worker=export ｜ 归题=report-10（头 trace-cd8d387465134d5d）
- trace-3b1932846c7b495ba64632ffdaacbf59 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 6629.0 ms ｜ worker=export ｜ 归题=report-07（头 trace-67f13849d9c444f3）
- trace-436e494496c24f169671d595aad71f1a ｜ 原因码 no_request_started ｜ 跨度 4 枚合计 8876.0 ms ｜ worker=export ｜ 归题=tool-01（头 trace-64eab546b5bc4771）
- trace-5cc47479dfea45bcb0c4b05ee6673eaf ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3269.0 ms ｜ worker=export ｜ 归题=report-09（头 trace-3826ca4b6e7f4510）
- trace-5f9bec54ebff4a669509b1637a72519f ｜ 原因码 no_request_started ｜ 跨度 24 枚合计 69952.0 ms ｜ worker=chart ｜ 归题=chart-02（头 trace-8a187ff8bb7b440b）
- trace-62628520834c45fc83804da70ca46bfa ｜ 原因码 no_request_started ｜ 跨度 55 枚合计 224506.0 ms ｜ worker=export ｜ 归题=scope-05（头 trace-7f93b62d12ea4829）
- trace-70380b63ae8b4e819d6cd1c27293c189 ｜ 原因码 session_absent_from_frames ｜ 跨度 6 枚合计 37991.0 ms ｜ worker=doc ｜ 归题=未归名（头 —）
- trace-7611eeb97a67491a95f22fede4859a26 ｜ 原因码 no_request_started ｜ 跨度 7 枚合计 25214.0 ms ｜ worker=chart ｜ 归题=insight-07（头 trace-8f5823ef94da43fa）
- trace-7b3805f2f249419c80be5f4c52049ec6 ｜ 原因码 no_request_started ｜ 跨度 4 枚合计 15556.0 ms ｜ worker=export ｜ 归题=report-11（头 trace-00e9d6887db24370）
- trace-8357f12da8ef466ba4e90ca11b07e94b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 10776.0 ms ｜ worker=export ｜ 归题=report-02（头 trace-dce357461972477b）
- trace-959a5dce740644e9915eb102c4706e6a ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 2670.0 ms ｜ worker=export ｜ 归题=tool-03（头 trace-acd870538b2f436c）
- trace-9e08833cd7f44e89a005165c87093050 ｜ 原因码 no_request_started ｜ 跨度 32 枚合计 72065.0 ms ｜ worker=chart ｜ 归题=chart-01（头 trace-c6725197b8be4aa7）
- trace-a0301880f5b443abba3f809a3693c56b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 6022.0 ms ｜ worker=export ｜ 归题=scope-02（头 trace-829f186bfb1b4349）
- trace-a22d332e369045cb9aa44cd0097dd9ad ｜ 原因码 no_request_started ｜ 跨度 1 枚合计 4372.0 ms ｜ worker=chart ｜ 归题=chart-03（头 trace-369404b6afa24b4f）
- trace-c1d798af80ad4ec3976f00eb4202bf2b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 4001.0 ms ｜ worker=export ｜ 归题=tool-02（头 trace-e6200f37df7347b9）
- trace-c9b6b7102aac4cac8fb2aba01eb20979 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 4137.0 ms ｜ worker=export ｜ 归题=report-05（头 trace-b75d3fe017724b35）
- trace-f4c6a1d4ad9a46a493d216dec754bdc8 ｜ 原因码 no_request_started ｜ 跨度 1 枚合计 4747.0 ms ｜ worker=chart ｜ 归题=tool-04（头 trace-91e1ad40d6a14440）
- 未归名列数 = 1；原因分布 = {"no_request_started": 19, "session_absent_from_frames": 1}
```

### 5.1 窗 run18 第二组：`resumed_head`（有分母零跨度 = R631 两本都不列的静默格）
```text
## 有分母却零跨度（R631 既不列 rows 也不列 skipped 的那一组）
- trace-00e9d6887db243708913e680ddb75a82 ｜ 题号 report-11 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-369404b6afa24b4f95f806d4950580af ｜ 题号 chart-03 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-3826ca4b6e7f451081ef95abdffe6c7d ｜ 题号 report-09 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-3f6465065ad247a39176c3616edcfbfb ｜ 题号 report-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-44e895d9db354d2c8b13a1baecd41c7f ｜ 题号 report-12 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-64eab546b5bc47718ad33ffce62886ba ｜ 题号 tool-01 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-67f13849d9c444f3a63ae85d997ac1f0 ｜ 题号 report-07 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-70dfb59bb9ae4647843058e251024dcf ｜ 题号 chart-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7f93b62d12ea48298cd065b611b14250 ｜ 题号 scope-05 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-829f186bfb1b43498d81110024ab9edc ｜ 题号 scope-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-8a187ff8bb7b440ba150a38bfc8d7253 ｜ 题号 chart-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-8f5823ef94da43fa996501e96742ada6 ｜ 题号 insight-07 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-91e1ad40d6a14440ba2d024cf1ae913d ｜ 题号 tool-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-acd870538b2f436c9d970efa2bc68bb5 ｜ 题号 tool-03 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-b75d3fe017724b359988a45c5ed532ba ｜ 题号 report-05 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-c6725197b8be4aa7945cd1fec598cec3 ｜ 题号 chart-01 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-cd8d387465134d5d95ed7a1616d10742 ｜ 题号 report-10 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-dce357461972477ba1338939bc9fabf3 ｜ 题号 report-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-e6200f37df7347b996064e5d9cbf29e9 ｜ 题号 tool-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
```

### 5.2 窗 run19 第一组：`no_denominator`（有跨度无分母 = R631 的 skipped）
```text
## no_denominator 逐枚点名（明账，一枚不摘）
- trace-083d84a3408e48829321538dbd79476b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 5142.0 ms ｜ worker=export ｜ 归题=scope-02（头 trace-f81fb96a46714419）
- trace-0c461234ea1844e39c6684ac9041e42e ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 2185.0 ms ｜ worker=export ｜ 归题=tool-03（头 trace-c2a60afc9c804c02）
- trace-0cad1cacc77d4fdd915f614b60b4fd4b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 6407.0 ms ｜ worker=export ｜ 归题=report-07（头 trace-a23fbefec1174450）
- trace-0f282b239b854b3aa479ee48d42cf705 ｜ 原因码 no_request_started ｜ 跨度 24 枚合计 69234.0 ms ｜ worker=chart ｜ 归题=chart-02（头 trace-7c2e17c96a47453d）
- trace-1200ef6ee48040d5918292e343c31b59 ｜ 原因码 no_request_started ｜ 跨度 14 枚合计 25372.0 ms ｜ worker=chart ｜ 归题=chart-04（头 trace-f39d0eb32fa04dd6）
- trace-23e4925b12b7408dabe3b67a80a319b0 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 2466.0 ms ｜ worker=export ｜ 归题=report-09（头 trace-4832e9c2dd6640e1）
- trace-2a765d554c374965af731c0e7bb4ebb9 ｜ 原因码 no_request_started ｜ 跨度 7 枚合计 21741.0 ms ｜ worker=chart ｜ 归题=insight-07（头 trace-928a117fc6454fe4）
- trace-4a64249168cc4d2e8f7371748979bb33 ｜ 原因码 no_request_started ｜ 跨度 4 枚合计 9324.0 ms ｜ worker=export ｜ 归题=tool-01（头 trace-a8b250ae80034cb9）
- trace-525b0bdd784845f292ac8da8d313e8dd ｜ 原因码 no_request_started ｜ 跨度 32 枚合计 70487.0 ms ｜ worker=chart ｜ 归题=chart-01（头 trace-55bf05a3ae0c4e0d）
- trace-599409ed90bb453fa534db23633ef6ee ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 8968.0 ms ｜ worker=export ｜ 归题=report-02（头 trace-36a763d8ff0448f0）
- trace-702c9b65ebde4f91b64eed69874f1d9f ｜ 原因码 no_request_started ｜ 跨度 1 枚合计 4404.0 ms ｜ worker=chart ｜ 归题=chart-03（头 trace-f7a49045aab94b31）
- trace-7d7f886191d34afe8d7550debc90f2ee ｜ 原因码 no_request_started ｜ 跨度 55 枚合计 221450.0 ms ｜ worker=export ｜ 归题=scope-05（头 trace-77624a2cbdf14113）
- trace-8f39efc40b4b4a99b04543d2084f48f1 ｜ 原因码 no_request_started ｜ 跨度 4 枚合计 14078.0 ms ｜ worker=export ｜ 归题=report-11（头 trace-31f63936922f403e）
- trace-b069767f2e054af79854e428b7e7bfaa ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3518.0 ms ｜ worker=export ｜ 归题=tool-02（头 trace-e5819e6e53ce408c）
- trace-c4add1c803c4480b95eddf1db369ab2b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3228.0 ms ｜ worker=export ｜ 归题=report-05（头 trace-cf2189f141a24ed0）
- trace-ce713be56a6747e9b2cb8ac1ec7bc99b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 5348.0 ms ｜ worker=export ｜ 归题=report-10（头 trace-d5e83b08852a406c）
- trace-da8ad54ea4214109aae4be7201fb45a3 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3092.0 ms ｜ worker=export ｜ 归题=report-12（头 trace-efdf8d43c27143b4）
- trace-e8aafc2346794efea60e2df50f9cc1ce ｜ 原因码 no_request_started ｜ 跨度 1 枚合计 3555.0 ms ｜ worker=chart ｜ 归题=tool-04（头 trace-0810a3835dfa402d）
- trace-f0a43504c6a8465c907149b15ecc318b ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 9412.0 ms ｜ worker=export ｜ 归题=report-04（头 trace-26dd6ae59a7c4dd1）
- 未归名列数 = 0；原因分布 = {"no_request_started": 19}
```

### 5.2 窗 run19 第二组：`resumed_head`（有分母零跨度 = R631 两本都不列的静默格）
```text
## 有分母却零跨度（R631 既不列 rows 也不列 skipped 的那一组）
- trace-0810a3835dfa402da86331f4ccbdd353 ｜ 题号 tool-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-26dd6ae59a7c4dd1b6d97a967837fa79 ｜ 题号 report-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-31f63936922f403e95793a66a0371cb1 ｜ 题号 report-11 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-36a763d8ff0448f0a999a07057df20bd ｜ 题号 report-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-4832e9c2dd6640e19356fd8d0f7b9f45 ｜ 题号 report-09 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-55bf05a3ae0c4e0da0a629125f9f87ec ｜ 题号 chart-01 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-77624a2cbdf14113b4b64bf78ac50dc9 ｜ 题号 scope-05 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7c2e17c96a47453db66cbd33901a6887 ｜ 题号 chart-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-928a117fc6454fe49d6f158f47ee083a ｜ 题号 insight-07 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-a23fbefec1174450b83c70b93a9c9bc1 ｜ 题号 report-07 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-a8b250ae80034cb986fbd70874af2fc0 ｜ 题号 tool-01 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-c2a60afc9c804c0284549da3e806ea53 ｜ 题号 tool-03 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-cf2189f141a24ed0bcdbaeadb81e5bb7 ｜ 题号 report-05 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-d5e83b08852a406c95c569380820e11c ｜ 题号 report-10 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-e5819e6e53ce408c918141047ac557de ｜ 题号 tool-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-efdf8d43c27143b4bf7f3753123c9858 ｜ 题号 report-12 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-f39d0eb32fa04dd6a17bd661b5dcb9d2 ｜ 题号 chart-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-f7a49045aab94b31baef6c7dc993127a ｜ 题号 chart-03 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-f81fb96a4671441992467f87e362e6b9 ｜ 题号 scope-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
```

### 5.3 窗 run20k 第一组：`no_denominator`（有跨度无分母 = R631 的 skipped）
```text
## no_denominator 逐枚点名（明账，一枚不摘）
- trace-06780f3329b045c38150c506575417c5 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 1950.0 ms ｜ worker=export ｜ 归题=tool-03（头 trace-307f0747f2574944）
- trace-18c690f6e65e48bc8ea127aa12fbcad6 ｜ 原因码 no_request_started ｜ 跨度 4 枚合计 9311.0 ms ｜ worker=export ｜ 归题=tool-01（头 trace-c7c03b45eea8405d）
- trace-27232be3326c4a8eb3914924d5ee3db1 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 6879.0 ms ｜ worker=export ｜ 归题=report-07（头 trace-ce914fe4341f49a2）
- trace-43265c658f6b4ee2aa6777f564297bb3 ｜ 原因码 no_request_started ｜ 跨度 4 枚合计 13656.0 ms ｜ worker=export ｜ 归题=report-11（头 trace-695fdc9f97a045f2）
- trace-5108846c79604b47b282d06f1328f7bf ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 4072.0 ms ｜ worker=export ｜ 归题=tool-02（头 trace-6de5d9f2258f4bfa）
- trace-67edf274e0264129996cee7d21bd722f ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3353.0 ms ｜ worker=export ｜ 归题=report-05（头 trace-7e3f3d9321554c4f）
- trace-76a55790ff574c1586da4999bd27bd1e ｜ 原因码 no_request_started ｜ 跨度 1 枚合计 4533.0 ms ｜ worker=chart ｜ 归题=chart-03（头 trace-7a0524789d61491f）
- trace-832cb993502e43df9af7c91544e56ac2 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 9168.0 ms ｜ worker=export ｜ 归题=report-04（头 trace-643c181d91134890）
- trace-89726731397a4122a7f220ea7774a4d1 ｜ 原因码 no_request_started ｜ 跨度 55 枚合计 222267.0 ms ｜ worker=export ｜ 归题=scope-05（头 trace-ebf6af6ca40f4a34）
- trace-8c0b0b8d785f48af852a0933a123365a ｜ 原因码 no_request_started ｜ 跨度 24 枚合计 69696.0 ms ｜ worker=chart ｜ 归题=chart-02（头 trace-7b4d404d44d14c8d）
- trace-90bda36a8bfc44d896146ddc601bafdd ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 5477.0 ms ｜ worker=export ｜ 归题=scope-02（头 trace-d69034afe6ed4f89）
- trace-9996893b4973433ea51e56a273ccbe1c ｜ 原因码 no_request_started ｜ 跨度 32 枚合计 73539.0 ms ｜ worker=chart ｜ 归题=chart-01（头 trace-90fcf7b5ad284ca7）
- trace-af278ad07e4e43fa917bf29d54182cf5 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 5328.0 ms ｜ worker=export ｜ 归题=report-10（头 trace-6923c8fd66294e76）
- trace-b312fd865d314679aab05bab7919cd0d ｜ 原因码 no_request_started ｜ 跨度 14 枚合计 25234.0 ms ｜ worker=chart ｜ 归题=chart-04（头 trace-b045a0939fba4fe8）
- trace-cdb371b874854886a856e493653a49f1 ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 2441.0 ms ｜ worker=export ｜ 归题=report-09（头 trace-fa206a504d514638）
- trace-d02ef08c066d41f6a01fc9f343f16bf0 ｜ 原因码 no_request_started ｜ 跨度 7 枚合计 23137.0 ms ｜ worker=chart ｜ 归题=insight-07（头 trace-31ef956a354148c0）
- trace-db4d57135b41480faefdea6963398d55 ｜ 原因码 no_request_started ｜ 跨度 1 枚合计 3659.0 ms ｜ worker=chart ｜ 归题=tool-04（头 trace-7a7746d988f147f0）
- trace-fdb3d9f618bc47d6b646b9962eacfdbd ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 9453.0 ms ｜ worker=export ｜ 归题=report-02（头 trace-7a90cefef2ca4456）
- trace-fe9bbb5ed545409fadd4e4b71358d9af ｜ 原因码 no_request_started ｜ 跨度 2 枚合计 3703.0 ms ｜ worker=export ｜ 归题=report-12（头 trace-a40435dd0d8549b8）
- 未归名列数 = 0；原因分布 = {"no_request_started": 19}
```

### 5.3 窗 run20k 第二组：`resumed_head`（有分母零跨度 = R631 两本都不列的静默格）
```text
## 有分母却零跨度（R631 既不列 rows 也不列 skipped 的那一组）
- trace-307f0747f257494495fe82f16c7ed38b ｜ 题号 tool-03 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-31ef956a354148c0aae771ac8ab41ac0 ｜ 题号 insight-07 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-643c181d91134890a820469ac0e2a128 ｜ 题号 report-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-6923c8fd66294e769c2b91c193f9adb8 ｜ 题号 report-10 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-695fdc9f97a045f2904e44dae79cbc20 ｜ 题号 report-11 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-6de5d9f2258f4bfabb4eef429e9dcf19 ｜ 题号 tool-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7a0524789d61491fb6c5c4ae2017e6a5 ｜ 题号 chart-03 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7a7746d988f147f0af0ca6fa51759822 ｜ 题号 tool-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7a90cefef2ca4456acede615f666fe30 ｜ 题号 report-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7b4d404d44d14c8da9be9bc7f527097e ｜ 题号 chart-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-7e3f3d9321554c4fac4092fe46a3c4ba ｜ 题号 report-05 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-90fcf7b5ad284ca793dc427c845902cd ｜ 题号 chart-01 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-a40435dd0d8549b8bbe55c6a5a118c43 ｜ 题号 report-12 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-b045a0939fba4fe8acb52e305a76c183 ｜ 题号 chart-04 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-c7c03b45eea8405da8fd7816d5da94a9 ｜ 题号 tool-01 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-ce914fe4341f49a2bf4944815245e309 ｜ 题号 report-07 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-d69034afe6ed4f89a792e216d1f14a22 ｜ 题号 scope-02 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-ebf6af6ca40f4a34b0e1aaa738afd685 ｜ 题号 scope-05 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
- trace-fa206a504d514638a11c8c298d8db147 ｜ 题号 report-09 ｜ lane='' lane_source=resumed ｜ 事件名册=request.started
```

- 判语：**第一组的跨度是真工作**（`paired_to` 逐枚归名到题号，run18 除 1 枚 `session_absent_from_frames` 外全归上名）；**第二组才是「缓存/续跑头」**（只有 1 枚 `request.started`、`lane=''`、`lane_source=resumed`，跨度 0 枚）。在册原因码 `cache_hits_are_not_traced` 盖的是第二组的形状，却挂在第一组的名字上。
- 尺的机读位置：`named.no_denominator[]` / `named.resumed_head[]` / `orphans.paired[]` / `orphans.unpaired[]` / `orphans.reasons`。

## 6 今天压根不产分段账的车道（每条都给机器可判定谓词）
| 车道/形状 | 不产的段 | 谓词（可机判） | run18 | run19 | run20k |
|---|---|---|---|---|---|
| 全线（reflect 段在任何车道都不产） | reflect | app/** 里 record_stage_event 的调用点枚数 == 0 | 105 | 105 | 106 |
| 车道：批准续跑的头（lane_source=resumed） | classify,rewrite,retrieve,generate,reflect | 该 trace 只有 1 枚 request.started，且 payload.lane == "" 且 payload.lane_source == "resumed" | 19 | 19 | 19 |
| 车道：批准续跑的工作腿（孤儿 trace） | classify,rewrite,retrieve,generate,reflect | 该 trace 的跨度样本 > 0，但窗内既无 request.started 也无本窗帧账认得的 session_id | 20 | 19 | 19 |
| 车道：闲聊直答（无 worker 腿、也无同胞账） | generate | 该题 generate 段 measured_count == 0 且 trace 内没有 step.started 且 orphan_traces 为空 | 10 | 13 | 11 |
| 车道：批准续跑（generate 的账在同胞 trace 上，本题 trace 不产） | generate | 该题 generate 段 measured_count == 0 且 trace 内没有 step.started 且 orphan_traces 非空 | 2 | 2 | 2 |
| 并行账（发了但在册尺不认） | generate,retrieve | 事件名不在 FINISHED_EVENTS（AST 现读 = ['model.finished', 'stage.finished', 'tool_call.finished']）而载荷带 duration | 93 | 90 | 93 |

每条谓词的现读凭据（`文件::符号` + 读数）：
- 【全线（reflect 段在任何车道都不产）】
  - `app/trace/spans.py::record_stage_event` ← 现读调用点 0 枚：（零枚）
  - `app/agents/nodes.py::reflect_node` ← 复审是规则过，不发 model／tool 跨度；STAGE_DESCRIPTIONS 自己就写着「当前为纯规则」
- 【车道：批准续跑的头（lane_source=resumed）】
  - `app/api/v1/chat.py::_record_resumed_lane_trace` ← 现读命中 19 枚：chart-01, chart-02, chart-03, chart-04, insight-07, report-02, report-04, report-05, report-07, report-09, report-10, report-11, report-12, scope-02, scope-05, tool-01, tool-02, tool-03, tool-04
  - `app/common/stage_timing.py::samples_from_events` ← trace 里没有任何 *.finished ⇒ 分段腿对这一枚题交回空
- 【车道：批准续跑的工作腿（孤儿 trace）】
  - `app/agents/orchestrator.py::run_interrupt_stream` ← 签名收 request_id/trace_id/task_id（关键字参数），但 app/api/v1/chat.py 那一处调用一个都不传 ⇒ _execution_ids() 另铸一枚 trace_id
  - `app/common/stage_timing.py::CANONICAL_STAGES` ← 现读孤儿 20 枚、跨度合计 543846.0 ms（reason 分布见 orphans.reasons）
- 【车道：闲聊直答（无 worker 腿、也无同胞账）】
  - `app/agents/nodes.py::respond` ← AST 现读：_make_model(ModelTier.CHAT).invoke(...) 不带 config ⇒ 那一发天生不落
- 【车道：批准续跑（generate 的账在同胞 trace 上，本题 trace 不产）】
  - `app/agents/orchestrator.py::run_interrupt_stream` ← 本题 trace 交回空，但配对孤儿 trace trace-9e08833cd7f44e89a005165c87093050, trace-f4c6a1d4ad9a46a493d216dec754bdc8 里确有跨度 ⇒ 这一枚不许叫「直答」
  - `app/common/stage_timing.py::samples_from_events` ← 跨度挂在另一枚 trace_id 上，本题事件名册里自然没有 generate
- 【并行账（发了但在册尺不认）】
  - `app/common/stage_timing.py::FINISHED_EVENTS` ← 只认 model.finished / tool_call.finished / stage.finished 三枚事件名
  - 未登记账 `retrieval.completed`（时长取 duration_ms）产生点：`app/rag/debug.py::run_retrieval_debug`, `app/rag/retrieval_pipeline.py::record_retrieval_completed`；窗内命中 74 枚题
  - 未登记账 `step.finished`（时长取 summary.duration_ms）产生点：`app/agents/orchestrator.py::_approval_worker_node`, `app/agents/orchestrator.py::node`, `app/trace/projections.py::<module>`；窗内命中 93 枚题

- 三窗逐枚命中数（同一谓词在另外两窗的读数）：
  - run19: {"全线（reflect 段在任何车道都不产）": 105, "并行账（发了但在册尺不认）": 90, "车道：批准续跑的头（lane_source=resumed）": 19, "车道：批准续跑的工作腿（孤儿 trace）": 19, "车道：批准续跑（generate 的账在同胞 trace 上，本题 trace 不产）": 2, "车道：闲聊直答（无 worker 腿、也无同胞账）": 13}
  - run20k: {"全线（reflect 段在任何车道都不产）": 106, "并行账（发了但在册尺不认）": 93, "车道：批准续跑的头（lane_source=resumed）": 19, "车道：批准续跑的工作腿（孤儿 trace）": 19, "车道：批准续跑（generate 的账在同胞 trace 上，本题 trace 不产）": 2, "车道：闲聊直答（无 worker 腿、也无同胞账）": 11}

## 7 合成样机（真窗命不中的型别也要有牙）
- 三窗真件里型 B／型 C 命中 0 枚，所以这两型改在合成窗里钉：`tests/test_r636_stage_coverage.py::synth`——doc-01（三段落账＋两本未登记时长账）／chart-01（工作挂在孤儿 trace，型 A/a3）／scope-09（generate 整段嵌在 retrieve 里，型 C）／doc-04（只有 `retrieval.completed`、没有 `search_docs` 跨度，型 B）／trace-orphanloose（进不了任何题的孤儿）。
- 合成窗现读：母集 {"asked": 4, "bare_trace": 0, "no_denominator": 2, "resumed_head": 1}，缺账型别 {"nested_excluded/-": 1, "no_event/a0_path_not_taken": 3, "no_event/a1_call_site_no_identity": 1, "no_event/a2_leg_has_no_span": 6, "no_event/a3_event_on_sibling_trace": 1, "unrecognized_event/-": 1}，与 R631 复算差 []。
- 样机刻意不带 `payload.question`：带着它 `samples_from_span_payload` 会去 import `app/agents/nodes` 问 R42 判别器，离线牙不该把产品路由拖进来。

## 8 三把反证刀（真窗现跑，各配正控）
刀的落点都在尺的入口参数上（`recognizer` / `omit_groups` / `validate_claims`），所以刀不必改盘面——这正是不许把「此刻工作树脏不脏」当判据的那条纪律的正面写法。

### 刀 a：把 retrieve 段的识别摘掉 ⇒ 与 R631 现跑读数逐枚对不上
- run18：`MismatchError` ← 与 R631 现跑读数对不上 341 处，前若干枚：[{"key": "chat-01", "trace_id": "trace-00ccd5e5f1384e96847f48838d0e46a7", "field": "segment_sum_ms", "mine": 16556.0, "r631": 21177.0}, {"key": "chat-01", "trace_id": "trace-00ccd5e5f1384e96847f48838d0e46a7", "field": "segments", "min
- run19：`MismatchError` ← 与 R631 现跑读数对不上 329 处，前若干枚：[{"key": "chat-12", "trace_id": "trace-0460e48bee6340b7aa14c22a17429212", "field": "segment_sum_ms", "mine": 11354.0, "r631": 15979.0}, {"key": "chat-12", "trace_id": "trace-0460e48bee6340b7aa14c22a17429212", "field": "segments", "min
- run20k：`MismatchError` ← 与 R631 现跑读数对不上 346 处，前若干枚：[{"key": "metric-06", "trace_id": "trace-00a8d43659eb4004ad9757b83fdcc046", "field": "segment_sum_ms", "mine": 13396.0, "r631": 29640.0}, {"key": "metric-06", "trace_id": "trace-00a8d43659eb4004ad9757b83fdcc046", "field": "segments", 
- 正控（同原料不注入假尺）：三窗 `mismatches` 枚数 = {"run18": 0, "run19": 0, "run20k": 0}。

### 刀 b：把 `no_denominator` 从母集摘掉 ⇒ 母集与账本枚数当场不等
- run18：`UniverseError` ← 母集 144 枚 vs 账本点名 124 枚（摘掉的组：no_denominator）⇒ 有人被悄悄摘掉，本件不出数
- run19：`UniverseError` ← 母集 143 枚 vs 账本点名 124 枚（摘掉的组：no_denominator）⇒ 有人被悄悄摘掉，本件不出数
- run20k：`UniverseError` ← 母集 144 枚 vs 账本点名 125 枚（摘掉的组：no_denominator）⇒ 有人被悄悄摘掉，本件不出数
- 正控：不摘组即一枚不丢，母集 = 点名 = {"run18": [144, 144], "run19": [143, 143], "run20k": [144, 144]}。

### 刀 c：把一道「没发事件」的缺失手写成型 C（无剔除读数）⇒ 归因当场被拒
- run18：`EvidenceError`（受害题 data-10）← data-10/retrieve 声称「被嵌套/重叠剔除」，但该题自己那份报告 excluded_count=0、measured_count=0 ⇒ 没有剔除这回事，改回它该有的型别
- run19：`EvidenceError`（受害题 tool-04）← tool-04/retrieve 声称「被嵌套/重叠剔除」，但该题自己那份报告 excluded_count=0、measured_count=0 ⇒ 没有剔除这回事，改回它该有的型别
- run20k：`EvidenceError`（受害题 chart-03）← chart-03/retrieve 声称「被嵌套/重叠剔除」，但该题自己那份报告 excluded_count=0、measured_count=0 ⇒ 没有剔除这回事，改回它该有的型别
- 型 C 的正控落不到真窗（{"run18": 0, "run19": 0, "run20k": 0} 枚），所以正控在合成窗：`scope-09` 的 generate 整段嵌在 retrieve 里，`validate_claims` 收下并点名 1 枚；这条形状由 `tests/test_r636_stage_coverage.py::test_knife_c_type_c_without_exclusion_reading_goes_red` 钉住。
- 第四把（顺手）：归因一条凭据都不带、或型别写成自造词 ⇒ `EvidenceError`；AST 与在册常量分家 ⇒ `DerivedError`；影子树里种一枚 `record_stage_event` 调用点，派生尺必须检出（`test_derived_ruler_detects_a_planted_call_site`）。

## 9 修复单判据草案（本单不改产品码，这六条是给总控派工用的）
每条都给：动哪一处（`文件::符号`）／验收读数（尺的机读字段名，收货时本席会亲跑复现）／反证形状。编号 R-636-1…6 只表依赖顺序，不占工单号。

### R-636-1 把批准续跑的身份传下去（先修这个，后面每条的读数才干净）
- 动点：`app/api/v1/chat.py::_approve_stream` 调 `app/agents/orchestrator.py::run_interrupt_stream` 时把 `request_id` / `trace_id` / `task_id` 传进去（或让 `_execution_ids()` 复用外层身份，不再另铸）。
- 验收读数：20 枚孤儿／19 枚孤儿／19 枚孤儿 → **0**；即 `named.no_denominator` 空、`orphans.unpaired` 空、`orphans.reasons` 空；R631 的 `skipped` 由 20／19／19 → **0**；`totals.orphan_ms`（505855.0／489411.0／496856.0 ms）整笔转进 `segment_sum_ms`。
- 逐枚下限：这 20／19／19 枚归名的题，其 `error_pct` 降幅 ≥ 0.9 ×（该题 `orphan_ms` ÷ 该题 `end_to_end_ms`）。不许用「少了几枚」代替「每枚都降」。
- 反证形状：① 只传 `trace_id` 不传 `session_id` ⇒ 尺仍报 `session_absent_from_frames`（run18 已有 1 枚这形状）；② 把 `no_denominator` 从母集摘掉冒充修好 ⇒ 刀 b 当场 `UniverseError`；③ 重复发 `request.started` 把孤儿缝上 ⇒ 必触 `app/trace/lifecycle.py::terminal_run_regression`（在册回归钉，改法必须避开它）。

### R-636-2 reflect 段：先交「走过 reflect」的可判痕迹，再谈加跨度
- 动点：`app/agents/nodes.py::reflect_node`（现读为纯规则，不发 model/tool 跨度；`app/trace/spans.py::record_stage_event` 在 `app/**` 调用点 0 枚）。
- 前置（不许跳）：今天无法从 trace 判某一题跑没跑过 reflect，所以修复单第一枚交付必须是**可判痕迹**（节点级计数或 `stage.finished` 事件），qa 直答不进 reflect——不许把 105／105／106 枚全填成「跑过」。
- 验收读数：`stage_rollup.reflect.producing_questions` == 独立痕迹数（两者必须同源于同一枚可判痕迹，不许一个来自 trace、一个来自人写的期望值）；`stage_rollup.reflect.missing_types` 里 `a2` → **0**；`record_stage_event` 调用点枚数 ≥ 1（派生尺的 `a2` 判据会随这枚自动改口径）。
- 反证形状：把 reflect 无条件记 0 ms ⇒ `producing_questions` 涨而 `ledger_ms` 仍 0，本尺会以「进账 0 ms」点名它——判据必须同时要求 `ledger_ms` > 0 与「痕迹枚数 == 进账枚数」。

### R-636-3 rewrite 段加跨度（覆盖面里最大的一整块）
- 动点：`app/common/model_handler.py::ModelHandler._call_budget` 非流式那一发是 `ModelTier.REWRITE`，而 `app/common/stage_timing.py::TIER_TO_STAGE` 早已把 rewrite 档记成 rewrite 段——缺的只是跨度产生点。
- 验收读数：逐枚「本题 rewrite 进账枚数 == 该题 `retrieval.completed` 载荷 `rewrite_count`」；期望总枚数 = 224／213／229，题数 = 74／72／76；`stage_rollup.rewrite.producing_questions` 由 0 → 74／72／76。
- 口径未定的那一格（须总控先裁）：`rewrite_count == 0` 的 31／33／30 枚是真没改写，判据不许把它们算成缺账（现在它们已是 `a0_path_not_taken`，改完后应彻底退出缺账列表）。
- 反证形状：把 `retrieval.completed` 整枚时长塞进 rewrite ⇒ 与 retrieve 腿重叠，`gap_ms` 会变负（over-attribution），本尺的「正向缺口/超信封」两栏（§10）会当场分叉。
- 待裁：`queue_wait` 含不含。含则 worker 腿排队时间有了归属；不含则即便 rewrite/reflect 补齐，仍有不可归的等待时间——这本账现在只能量出它有 657484.7／571817.8／501223.4 ms，不能替它取名。

### R-636-4 三处不带身份的模型调用点补 `config`
- 动点（AST 现读 4 枚，本单只点名其中在 ask 路径上的 3 枚）：["app/agents/nodes.py::plan", "app/agents/nodes.py::respond", "app/agents/tools.py::_llm_pandas_code", "app/api/v1/alerts.py::_ai_analysis"]。
- `app/api/v1/alerts.py::_ai_analysis`（`ModelTier.ALERT`）**不在 ask 路径**，本单一律点名不动，别顺手改。
- 验收读数：`source_facts.identityless_model_sites` 由 4 → **1**（只剩 ALERT）；`stage_rollup.generate.missing_types` 里 `a1` 由 10／13／11 → **0**；「闲聊直答」车道由 10／13／11 → **0**。
- 反证形状：只补 `config` 不补 stage 归属 ⇒ `tier_to_stage` 里 chat/analysis/code 都已记 generate，若仍不落账说明事件没带 tier——判据要落在 `samples_from_events` 的入参形状上，不是「代码里看起来传了」。

### R-636-5 未登记时长账（`step.finished` / `retrieval.completed`）纳不纳：本席不代裁
- 现状：这两本账三窗命中 93／90／93 枚题，worker 腿 Σ 2600956.0／2416030.0／2444940.0 ms、检索腿 Σ 1023001.3／1009826.7／969071.9 ms，与在册跨度**重叠**。
- 若要纳：必须先交「重叠计时归属规则」（同段取 max / 取外层 / 显式拆 queue+work），验收 = 三窗 `gap_ms` 无一枚为负，且 §4「未登记账」列改由在册事件名给出。
- 反证形状：直接把事件名塞进 `app/common/stage_timing.py::FINISHED_EVENTS` = over-attribution，`<0.03%` 对齐线红得更快；`test_derived_ruler_goes_red_when_the_tables_split` 那把影子刀会先红（AST 与在册常量分家即 `DerivedError`）。

### R-636-6 R631 的静默格补原因码（唯一动 R631 的一条，需总控授权）
- 现状：`resumed_head` 19／19／19 枚「有分母零跨度」在 R631 里既不列 rows 也不列 skipped——账面静默。
- 验收读数：R631 输出的 `skipped_reasons` 出现 `no_segments`，枚数 = 19／19／19；本尺的 `reference_gap.skipped` 随之从 20／19／19 变成 39／38／38，`asked_minus_rows` 仍 0。
- 反证形状：拿「把它们并入 rows」冒充补账 ⇒ 分母在而分段空，R631 的误差会变成 100% 的假信号；本尺的刀 b 保证任何「从母集摘掉」的动作当场红。

## 10 判语：把覆盖面补齐也到不了 `<1%`（算术，不是意见）
| 量 | 定义 | run18 | run19 | run20k |
|---|---|---|---|---|
| Σ端到端 | 分母 | 4248907.7 | 3816262.8 | 3765735.4 |
| Σ分段进账 | 在册跨度加总 | 3085078.0 | 2754568.0 | 2767171.0 |
| 净缺口 | Σ端到端 − Σ进账 | 1163829.7 | 1061694.8 | 998564.4 |
| 净缺口占比 | 净缺口 ÷ Σ端到端（= R631 的 <1% 线） | 27.39% | 27.82% | 26.52% |
| 正向缺口 | Σ 逐枚 gap>0 | 1287081.4 | 1158879.4 | 1124863.6 |
| 正向占比 | 正向缺口 ÷ Σ端到端 | 30.29% | 30.37% | 29.87% |
| 超信封枚数 | 分段加总 > 端到端 的题数（多计一侧） | 22 | 16 | 21 |
| 超信封 ms | Σ 逐枚 gap<0 的绝对值 | 123251.7 | 97184.6 | 126299.2 |
| 配对孤儿 | 挂在同胞 trace 上的跨度 | 505855.0 | 489411.0 | 496856.0 |
| 孤儿占比 | 孤儿 ÷ Σ端到端 | 11.91% | 12.82% | 13.19% |
| 归位后净缺口 | (净缺口 − 孤儿) ÷ Σ端到端 | 15.49% | 15.0% | 13.32% |
| int() 地板界 | 在册时长取整的下界 | 490.0 | 466.0 | 485.0 |
| 残差 | 归位后 − 地板界（今天无任何在册账） | 657484.7 | 571817.8 | 501223.4 |
| 未决配对 | 孤儿未缝上头 trace 的枚数 | 109 | 92 | 104 |
| 1% 目标 ms | 0.01 × Σ端到端（判据②要达的绝对量） | 42489.1 | 38162.6 | 37657.4 |

四条判语：
1. **能预算的只有一刀**：R-636-1 把孤儿缝回头，净缺口从 27.39／27.82／26.52% 降到 15.49／15.0／13.32%——离 1% 还差一个数量级，目标绝对量是 42489.1／38162.6／37657.4 ms。
2. **rewrite／reflect 的降幅无法预算**：这两段今天一条时长读数都没有（§6 第 1 条、R-636-2/3）。能给的上界是「残差」那格——657484.7／571817.8／501223.4 ms，它同时是「补齐后最多能吃掉多少」与「今天说不清它是不是段时长」的同一枚数。把它当成可归零，就是把假设写成测量。
3. **多计的一侧已经在漏**：三窗「分段加总 > 端到端」的题各 22／16／21 枚，合计 123251.7／97184.6／126299.2 ms（表里「超信封」两行）。缺口不是单向下漏，所以任何「为了过 <1% 而多加账」的改法都会把这批题推得更负，`<0.03%` 对齐线尤其敏感。
4. 所以判语：**R-636-1 是必要不充分；R-636-3/4 是覆盖面主体；R-636-2/5/6 缺「口径」不缺码**。六条里 R-636-1／3／4 是码、R-636-2／5／6 是口径，任何一件没落地，G-R51-1 判据② 都不该被写成翻绿；本席据尺拒写「已达标」。

## 11 复现：命令原文 + 两态亲跑 + 卫生扫描
- 全部命令在树 `C:\Users\fengx\PycharmProjects\be-r636` 内执行；解释器一律 `./.venv/Scripts/python.exe`，不用系统 python（anaconda 缺 chromadb 会在 conftest 当场炸）。
- 原料缺失时真窗组自动 skip（不参与判语），合成组照跑；三本件**只读**，本单不重导、不连库。
### 11.1 命令原文（本席亲跑，逐条可复现）

| # | 命令 | 读数 |
|---|---|---|
| 1 | `.\.venv\Scripts\python.exe scripts/r636_stage_coverage.py --window run18 --window run19 --window run20k` | 退出码 0（账全），三窗印面即 §3 |
| 2 | `.\.venv\Scripts\python.exe scripts/r636_stage_coverage.py --window run18 --window run19 --window run20k --json` | 全量机读账 2,548,301 字节（§4/§5/§6 的原料） |
| 3 | `.\.venv\Scripts\python.exe -m pytest tests/test_r636_stage_coverage.py -v -p no:cacheprovider --no-header` | state① 31 passed in 6.58s |
| 4 | 影子端正控（state②）：`git archive 473235f` 解到 `%TEMP%\r636state2` ＋只投本单三枚件 ＋ 同一枚 venv 解释器跑同名件 | state② 31 passed in 7.13s |
| 5 | 三把刀逐窗现跑：`ruler.build_window(w, recognizer=blind)` / `ruler.build_window(w, omit_groups=(GROUP_NO_DENOM,))` / `ruler.validate_claims(forged, rows, CANONICAL_STAGES)` | 读数在 §8 |
| 6 | 本纸由临时件 `gen1.py`…`gen4.py` 现读拼装（生成器不进树，纸进树） | 现 801 行 |

### 11.2 两态亲跑（AGENTS.md 两态纪律）

- state①（apply 未 commit，现树 `be-r636`，基点 `473235f`）：**31 passed in 6.58s**
- state②（`473235f` 干净检出 `%TEMP%\r636state2` ＋只投本单三枚件）：**31 passed in 7.13s**
- 两态 passed **枚数**相同：**是（31 = 31）**；用时 6.58s vs 7.13s（影子树走同一枚解释器，用时差不参与判语）；state① 点名 31 枚、state② 点名 31 枚，同名件清单逐枚一致：**是**

| # | 同名件（state① 与 state② 逐枚同名同序） |
|---|---|
| 1 | `tests/test_r636_stage_coverage.py::test_synthetic_window_is_measured_and_cross_checked` |
| 2 | `tests/test_r636_stage_coverage.py::test_per_question_numbers_are_r631_own_readings` |
| 3 | `tests/test_r636_stage_coverage.py::test_universe_names_every_trace_once` |
| 4 | `tests/test_r636_stage_coverage.py::test_missing_stages_split_into_three_types_with_evidence` |
| 5 | `tests/test_r636_stage_coverage.py::test_orphan_pairing_uses_the_resumed_head_bridge` |
| 6 | `tests/test_r636_stage_coverage.py::test_no_denominator_items_are_named_not_dropped` |
| 7 | `tests/test_r636_stage_coverage.py::test_render_declares_it_does_not_judge_the_gate` |
| 8 | `tests/test_r636_stage_coverage.py::test_knife_a_recognizer_losing_a_stage_goes_red` |
| 9 | `tests/test_r636_stage_coverage.py::test_knife_b_dropping_no_denominator_goes_red` |
| 10 | `tests/test_r636_stage_coverage.py::test_knife_c_type_c_without_exclusion_reading_goes_red` |
| 11 | `tests/test_r636_stage_coverage.py::test_claim_without_evidence_is_rejected` |
| 12 | `tests/test_r636_stage_coverage.py::test_derived_ruler_detects_a_planted_call_site` |
| 13 | `tests/test_r636_stage_coverage.py::test_identityless_detector_reads_the_two_real_sites` |
| 14 | `tests/test_r636_stage_coverage.py::test_identityless_detector_ignores_a_site_that_passes_config` |
| 15 | `tests/test_r636_stage_coverage.py::test_derived_ruler_goes_red_when_the_tables_split` |
| 16 | `tests/test_r636_stage_coverage.py::test_unregistered_stage_of_refuses_to_invent_a_stage` |
| 17 | `tests/test_r636_stage_coverage.py::test_main_exit_codes` |
| 18 | `tests/test_r636_stage_coverage.py::test_real_window_ledger_matches_r631_row_by_row[run18-105-20]` |
| 19 | `tests/test_r636_stage_coverage.py::test_real_window_ledger_matches_r631_row_by_row[run19-105-19]` |
| 20 | `tests/test_r636_stage_coverage.py::test_real_window_ledger_matches_r631_row_by_row[run20k-106-19]` |
| 21 | `tests/test_r636_stage_coverage.py::test_real_window_every_missing_stage_is_type_named_and_evidenced[run18]` |
| 22 | `tests/test_r636_stage_coverage.py::test_real_window_every_missing_stage_is_type_named_and_evidenced[run19]` |
| 23 | `tests/test_r636_stage_coverage.py::test_real_window_every_missing_stage_is_type_named_and_evidenced[run20k]` |
| 24 | `tests/test_r636_stage_coverage.py::test_real_window_approved_resume_is_the_paired_orphan_lane[run18]` |
| 25 | `tests/test_r636_stage_coverage.py::test_real_window_approved_resume_is_the_paired_orphan_lane[run19]` |
| 26 | `tests/test_r636_stage_coverage.py::test_real_window_approved_resume_is_the_paired_orphan_lane[run20k]` |
| 27 | `tests/test_r636_stage_coverage.py::test_real_windows_do_not_silently_drop_the_unpaired_orphan` |
| 28 | `tests/test_r636_stage_coverage.py::test_lane_names_cannot_overreach` |
| 29 | `tests/test_r636_stage_coverage.py::test_real_window_direct_lane_is_disjoint_from_sibling_traces[run18]` |
| 30 | `tests/test_r636_stage_coverage.py::test_real_window_direct_lane_is_disjoint_from_sibling_traces[run19]` |
| 31 | `tests/test_r636_stage_coverage.py::test_real_window_direct_lane_is_disjoint_from_sibling_traces[run20k]` |

- 第二遍（干净树复跑）不是走过场：本单的牙只吃**仓外三本导出件**＋**影子树 AST**，所以并树前后必须同数；谁把「此刻盘面脏不脏」写成判据，state② 就会红（在册事故 #96／#107 的同族预防）。

### 11.3 卫生扫描（写完自查，现值）

| 文件 | LF | CRLF | 孤 CR | 0x00/07/08/0b/0c 枚数 | 反引号枚数 | AST parse |
|---|---|---|---|---|---|---|
| `scripts/r636_stage_coverage.py` | 1395 | 0 | 0 | 0 {"0x0": 0, "0x7": 0, "0x8": 0, "0xb": 0, "0xc": 0} | 52（偶数·配对） | OK |
| `tests/test_r636_stage_coverage.py` | 475 | 0 | 0 | 0 {"0x0": 0, "0x7": 0, "0x8": 0, "0xb": 0, "0xc": 0} | 0（偶数·配对） | OK |
| `docs/testing/r636-stage-coverage-2026-10-04.md` | 801 | 0 | 0 | 0 {"0x0": 0, "0x7": 0, "0x8": 0, "0xb": 0, "0xc": 0} | 610（偶数·配对） | —（非码） |

- 正文手抄行号扫描（`xxx.py:123` 形状）：0 处（判据要求 `文件::符号`，必须 0）
- 坐标形状扫描（`文件::符号`）：30 处
- 中文正文写入通道：全部经 Python 以 UTF-8 落盘（PowerShell 只负责把生成器本身写成 .py），未用 `Set-Content -Encoding ascii`，未出现 `` `f ``→FF、`` `r ``→CR 那一族转义啃噬。
- 收席盘面（2026-10-04 19:24 现取，不是几分钟前的旧账）：`git status --porcelain` → ?? docs/testing/r636-stage-coverage-2026-10-04.md ⏎ ?? scripts/r636_stage_coverage.py ⏎ ?? tests/test_r636_stage_coverage.py
  - `git diff --numstat HEAD` → (空：改动均为未跟踪新件)
  - `git ls-files --others --exclude-standard` → docs/testing/r636-stage-coverage-2026-10-04.md ⏎ scripts/r636_stage_coverage.py ⏎ tests/test_r636_stage_coverage.py
  - `git rev-list --count 473235f..HEAD` → 0（本席未 commit，总控代提交）

### 牙的设计纪律（今日在册事故，逐条避开）
- 不拿「此刻工作树脏不脏」当判据：刀的落点是 `recognizer` / `omit_groups` / `validate_claims` 三枚入口参数，AST 自证走**影子树**（`tmp_path` 下种调用点再检出），正控是「真实 `app/**` 今天仍 0 枚」的现读，不是全盘洁净断言。
- 引用坐标一律 `文件::符号`：尺内所有凭据都是 `symbol` 字段 + 现读 `reading`；行号不入库。
- 派生尺只 parse 源码、不 import 产品模块：`app/api/v1/chat.py` 被 import 会发 Postgres 探针并写脏 `chroma_db/chroma.sqlite3`。

## 12 留给总控
- **要裁的四件**：① `queue_wait` 含不含（决定 R-636-3 的口径，也决定残差那格能不能有个名字）；② `step.finished` / `retrieval.completed` 纳不纳（R-636-5，本席不代裁）；③ reflect 的「走过痕迹」该长什么形状（R-636-2 前置）；④ R-636-6 要动 `scripts/r631_stage_sum_delta.py`，本单禁区，需授权另立。
- **派工切法建议**（按写集，不按功能名）：R-636-1 先行（写集 `app/api/v1/chat.py` + `app/agents/orchestrator.py`）；R-636-3（`app/common/model_handler.py`）与 R-636-4（`app/agents/nodes.py` + `app/agents/tools.py`）可并行；R-636-2 与 R-636-5 都碰 `app/common/stage_timing.py` 的口径，必须串行。
- **账面**：跟进单 §168 与计划书 §6 第四格归总控写，本单未碰 `docs/handoff/**`。
- **盘面**：本席未 commit、未建分支、未 push；`git rev-list --count 473235f..HEAD` = 0，收货盘面四读在收席那一刻现取，见本节末（由总控收货时复现）。
- 本纸自证：`docs/testing/r636-stage-coverage-2026-10-04.md` 由生成器现读拼出，重跑命令即可整纸复现（§11）。
