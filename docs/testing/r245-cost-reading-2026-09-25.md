# R245 · D 格「代价读数」改口记录（09-25）

> 单号 R245 · 基点 `2ab2369` · 写域只有三枚：`scripts/r218_switch_rehearsal.py`、
> `tests/test_r218_lane_flip_stop_sets.py`、本页。`frontend/**` 全程只读 —— 本页每一个前端数值
> 都是**读**出来的（`ChatPanel.vue` 原件 sha256 前 16 位 `39fd661fa74ca098`，取证时刻 `2026-09-25 16:54:23`）。
> 判据原文＝跟进单 §98.2「R245」四条，逐条对判见 §5。本页所有数字来自当次现场运行，无一手抄。

## 1. 旧口径为什么过期

三段，逐段带出处：

1. **R218 立件那天**（基点 `dea3ee4`）：`watchQueueTurn` 只有 `setInterval` 与两枚 `stop()`，
   件里实测六枚 `DEADLINE_TOKENS` 在函数体中全 0 命中 ⇒ `no_deadline = True`。于是那一族
   "漏停一枚"的代价不是一句秒数，而是 **"永不停"**。后端那族本来就有截止，代价写成了有名读数
   `adapter_waste_per_stalled_watch_seconds`；前端这一侧**没有对应物**，只有"没有截止"这句定性话。
2. **R221 并树**（`9850969`）：`QUEUE_WAIT_DEADLINE_MS` 与 `QUEUE_WAIT_MAX_POLLS` 落进
   `watchQueueTurn` ⇒ `no_deadline` 由 True 翻 False ⇒ "漏停 = 永不停"这句代价口径当场过期。
3. **量具当时只拒绝、不重算**（原 `scripts/r218_switch_rehearsal.py:389-392`）：
   `if not front["no_deadline"]: problems.append(
   "frontend_deadline_appeared_rerun_the_cost_reading")`，注释写的是"宁可当场红，让窗前来人重算"。
   这份"等"后来被 `tests/test_r218_lane_flip_stop_sets.py:91`/`:191` 钉成了**期望值** ——
   于是门是绿的，但 D 格从 R221 起永久红：run8 真开窗时那一格永远拿不到绿，
   那扇 3–5 小时的真机窗白开一次。

⚠️ 口径性质要说清：本格变绿**不是**产品变好了，是量具补了算式。唯一的凭据是 §2 那两枚读数交得出来。

## 2. 新口径的算式

`scripts/r218_switch_rehearsal.py` 新增 `frontend_deadline_cost_reading(text, body, poll_ms)`：
"每条未终结的前端轮询白等多久"由**三跳现读**算出，断在任何一跳就不交读数、只交缺口名。

| 跳 | 读什么（件里的形状，不写死名字之外的值） | 本树现读结果 |
|---|---|---|
| ① | `watchQueueTurn` 函数体里到点自停那一跳 `if (<counter> > <LIMIT>)` | `entry.polls > QUEUE_WAIT_MAX_POLLS` |
| ② | 那枚上限自己的推导式 `const <LIMIT> = <DEADLINE_MS> / <CLOCK>` | `QUEUE_WAIT_MAX_POLLS = QUEUE_WAIT_DEADLINE_MS / QUEUE_POLL_MS` |
| ③ | 分子那枚 `const <DEADLINE_MS> = <十进制字面>` | `300000`（ms） |

两枚有名读数（与后端那枚同命名法、进同一个 `readings` 字典）：

- `frontend_deadline_ms` = 第三跳的原始读数，单位跟原件一致取 ms = **300000**
- `frontend_waste_per_stalled_watch_seconds` = `frontend_deadline_ms / 1000` = **300.0** 秒

另附两格证据，让窗前来人能对判读数从哪长出来：`frontend_deadline_source`
（`counter` / `limit_const` / `deadline_const` / `clock_const` / `polls_before_stop`
= 300000 ÷ 3000 = **100.0** / `enforcement_line` 原文）
与 `frontend_deadline_gaps`。

等式为什么成立（件里不另立第二把尺）：首枚 `tick()` 在 t=0 打，此后每 `QUEUE_POLL_MS` 一枚，
数到第 `MAX_POLLS + 1` 枚收表 ⇒ 收表时刻 = `MAX_POLLS × QUEUE_POLL_MS` = 那枚截止本身。
所以"单条白等时长 = 截止本身"这句，与后端 `adapter_waste_per_stalled_watch_seconds
= 900.0`（= 它自己的 deadline）是同一形状的读法。

两件刻意不做的事：

- **不乘题数**：后端那格另交 `adapter_worst_case_minutes_if_every_question_stalls`（105
  题全撞上的天花板，且带 `worst_case_is_upper_bound_not_expectation` 旗标）；前端不交天花板，
  因为 105 题里真在浏览器侧起轮子的枚数离线读不出来，乘它就是重犯 `900 × 105` 那笔账。
- **不读墙钟**：那一族到点数的本来就是枚数（前端注释明写"不读系统时间"），件里跟着它数。

有界判据（替换原 :389-392，"过期就红"的纪律原样保留）：

- 有截止（`no_deadline = False`）⇒ **必须**有有名读数；`gaps` 非空 ⇒
  `problems.append("frontend_deadline_cost_reading_unbounded=" + gaps)`；
  缺口名逐枚有名：`enforcement_not_wired` / `deadline_ms_unreadable` / `deadline_ms_not_finite`
  / `deadline_ms_not_positive` / `poll_clock_unreadable`。
- 反向半条：`no_deadline = True` 却有名读数交得出一个有界秒数 ⇒
  `problems.append("frontend_deadline_cost_reading_contradicts_no_deadline")` ——
  件里不许同时存着两份互相矛盾的代价口径。
- 旧字符串 `frontend_deadline_appeared_rerun_the_cost_reading` 不再当占位复用。

## 3. 前后两版 D 格读数对照（现场产物）

**改前**（基点 `2ab2369` 的脚本原件，在 %TEMP% 对照根上现跑；`git show` 只读取 blob，零写工作树）：

```json
{
 "cell": "D-报告档翻开关与轮询停表",
 "problems": [
  "frontend_deadline_appeared_rerun_the_cost_reading"
 ],
 "readings": {
  "adapter_deadline_env": "EVAL_QUEUE_POLL_SECONDS",
  "adapter_deadline_seconds": 900.0,
  "adapter_stops": [
   "cancelled",
   "dead",
   "done",
   "expired",
   "failed"
  ],
  "adapter_unhandled_final": [],
  "adapter_waste_per_stalled_watch_seconds": 900.0,
  "adapter_worst_case_minutes_if_every_question_stalls": 1575.0,
  "backend_answers": [
   "cancel_requested",
   "cancelled",
   "dead",
   "done",
   "expired",
   "failed",
   "processing",
   "queued"
  ],
  "citation_drift": [],
  "final_statuses": [
   "done",
   "cancelled",
   "failed",
   "dead",
   "expired"
  ],
  "frontend_deadline_tokens_seen": {
   "Date.now": 0,
   "Deadline": 2,
   "clearTimeout": 0,
   "deadline": 0,
   "elapsed": 0,
   "setTimeout": 0
  },
  "frontend_http_stoppers": [
   "401:authentication_required",
   "403:authorization_unavailable",
   "403:permission_denied",
   "404:resource_not_found"
  ],
  "frontend_poll_ms": 3000,
  "frontend_settled": [
   "cancelled",
   "dead",
   "done",
   "expired",
   "failed"
  ],
  "frontend_stop_actions": [
   [
    1073,
    "if (QUEUE_SETTLED.includes(read.status)) stop()"
   ],
   [
    1092,
    "entry.timer = setInterval(tick, QUEUE_POLL_MS)"
   ]
  ],
  "frontend_unhandled_final": [],
  "frontend_watch_has_no_deadline": false,
  "inflight_statuses": [
   "queued",
   "processing",
   "cancel_requested"
  ],
  "lane_flip": {
   "default_off": true,
   "flip_off_literal": true,
   "flip_on": true,
   "lane_predicate": {
    "": "",
    "REPORT": "",
    "analysis": "",
    "qa": "",
    "report": "report"
   }
  },
  "question_count_read_from_fixture": 105,
  "worst_case_is_upper_bound_not_expectation": true
 },
 "verdict": "RED"
}
```

退出码 `1`（D 格红）。

**改后**（本树 `python scripts/r218_switch_rehearsal.py --json` 的 D 格原文）：

```json
{
 "cell": "D-报告档翻开关与轮询停表",
 "not_covered_offline": [
  "NOT_COVERED_OFFLINE 队列 worker 真取回（deploy/queue_worker.py 要真 Redis + 真进程；离线只能判状态字面，判不了 done 之后 result 真不真）",
  "NOT_COVERED_OFFLINE 报告档整轮端到端（入队→worker 跑完→/queue/status 取回正文要真容器）"
 ],
 "problems": [],
 "readings": {
  "adapter_deadline_env": "EVAL_QUEUE_POLL_SECONDS",
  "adapter_deadline_seconds": 900.0,
  "adapter_stops": [
   "cancelled",
   "dead",
   "done",
   "expired",
   "failed"
  ],
  "adapter_unhandled_final": [],
  "adapter_waste_per_stalled_watch_seconds": 900.0,
  "adapter_worst_case_minutes_if_every_question_stalls": 1575.0,
  "backend_answers": [
   "cancel_requested",
   "cancelled",
   "dead",
   "done",
   "expired",
   "failed",
   "processing",
   "queued"
  ],
  "citation_drift": [],
  "final_statuses": [
   "done",
   "cancelled",
   "failed",
   "dead",
   "expired"
  ],
  "frontend_deadline_gaps": [],
  "frontend_deadline_ms": 300000,
  "frontend_deadline_source": {
   "clock_const": "QUEUE_POLL_MS",
   "counter": "entry.polls",
   "deadline_const": "QUEUE_WAIT_DEADLINE_MS",
   "enforcement_line": "if (entry.polls > QUEUE_WAIT_MAX_POLLS) {",
   "limit_const": "QUEUE_WAIT_MAX_POLLS",
   "polls_before_stop": 100.0
  },
  "frontend_deadline_tokens_seen": {
   "Date.now": 0,
   "Deadline": 2,
   "clearTimeout": 0,
   "deadline": 0,
   "elapsed": 0,
   "setTimeout": 0
  },
  "frontend_http_stoppers": [
   "401:authentication_required",
   "403:authorization_unavailable",
   "403:permission_denied",
   "404:resource_not_found"
  ],
  "frontend_poll_ms": 3000,
  "frontend_settled": [
   "cancelled",
   "dead",
   "done",
   "expired",
   "failed"
  ],
  "frontend_stop_actions": [
   [
    1073,
    "if (QUEUE_SETTLED.includes(read.status)) stop()"
   ],
   [
    1092,
    "entry.timer = setInterval(tick, QUEUE_POLL_MS)"
   ]
  ],
  "frontend_unhandled_final": [],
  "frontend_waste_per_stalled_watch_seconds": 300.0,
  "frontend_watch_has_no_deadline": false,
  "inflight_statuses": [
   "queued",
   "processing",
   "cancel_requested"
  ],
  "lane_flip": {
   "default_off": true,
   "flip_off_literal": true,
   "flip_on": true,
   "lane_predicate": {
    "": "",
    "REPORT": "",
    "analysis": "",
    "qa": "",
    "report": "report"
   }
  },
  "question_count_read_from_fixture": 105,
  "worst_case_is_upper_bound_not_expectation": true
 },
 "verdict": "MEASURED_GREEN"
}
```

键位差分（机器算出，非手抄）：

新增键（只出现在改后）：`frontend_deadline_gaps`, `frontend_deadline_ms`, `frontend_deadline_source`, `frontend_waste_per_stalled_watch_seconds`

消失的键：（无）

同键改值：（无）

```json
{
 "added_only_in_after": [
  "frontend_deadline_gaps",
  "frontend_deadline_ms",
  "frontend_deadline_source",
  "frontend_waste_per_stalled_watch_seconds"
 ],
 "removed_only_in_before": [],
 "value_changed": {}
}
```

汇总：改前退出码 `1`（D 格红），改后退出码 `0`；三格 verdict = D=MEASURED_GREEN / C=MEASURED_GREEN / A②=MEASURED_GREEN。

## 4. 这格与 run8 相 2 的 D-1 / D-2 / D-3 的对应

出处：`docs/testing/run8-phase2-plan-2026-09-25.md` §3 那张表。

| 相 2 判据 | 本格现在替它挡住哪一块 | 本格**不**担保、仍须在窗内现场判 |
|---|---|---|
| **D-1** 12 题：入队 → worker 跑完 → `/queue/status` **取回正文**；停表分得清五终态；`queued_done_no_bytes` 出现即红 | 两族停表收全五枚终态 ⇒ `frontend_unhandled_final` / `adapter_unhandled_final` 两枚空表；开关三枚 True ⇒ `lane_flip` 离线判得动；`frontend_deadline_ms = 300000` 给"漏停最晚到点收表"的界（旧口径那句"永不停"从今天起是**假话**，读数替它作证） | 真 worker、真 Redis、整轮端到端取回正文 —— 那两条 `NOT_COVERED_OFFLINE` 一个字没消（原文见 §7）。⚠️ 相 2 采集走的是**适配器**那条腿：每道未终结轮询付的是 `adapter_waste_per_stalled_watch_seconds` = 900.0 s，**不是**前端那 300.0 s。两枚读数分别管浏览器与采集器，报表抬头必须写清用的哪一枚 |
| **D-2** `usage` 逐题非零（sidecar） | 无 —— 本格不产 usage | 全在窗内量；不许拿截止读数当它的替身 |
| **D-3** `sources` 在流里、逐题可追（evidence 段） | 无 —— 本格不产 sources | 那一格有自己的尺（C 格命中腿 + A② 帧账），本格不越界 |

⇒ 这一格修完，run8 开窗时 D 格**能**拿绿；但 D 格绿只等于"D-1 的离线前置齐了"，不等于 D-1 过。

## 5. §98.2 四条判据逐条对判

| 判据（§98.2 原文摘要） | 落点 | 达标 |
|---|---|---|
| ① 前端交两枚有名读数，数值从 `ChatPanel.vue` 现读，写字面量即判未完成 | `readings.frontend_waste_per_stalled_watch_seconds` = `300.0`、`readings.frontend_deadline_ms` = `300000`（与 adapter 那枚同命名法、同字典）；算式 `frontend_deadline_cost_reading` 三跳现读 | 达标 |
| ② `:389-392` 换成有界判据，保留过期即红的纪律，换新名字 | `frontend_deadline_cost_reading_unbounded=<gaps>`（正向）与 `frontend_deadline_cost_reading_contradicts_no_deadline`（反向半条）；旧字符串在仓里 grep 只剩钉与本页的历史叙述，判据路径上零引用 | 达标 |
| ③ 预授权翻转 `:91`/`:191`，新断言仍判恰等 | 两枚都成 `== []`（恰等空表），另加 5 组恰等断言（两枚读数、`gaps`、`source` 三跳、`live_ms` 等式）；零 assert 删除、零 skip/xfail | 达标（同枚钉的 `:88` verdict 与两段过期注释一并改口，文件头逐字列出） |
| ④ 两枚反证钉 + sha256 自证不写脏树 | 实交 5 枚，见 §6 表 | 达标 |
| 硬禁：ruler 件保持零改动，但 `:272` 因本单换掉的旧口径而变红 | `tests/test_r218_ruler_self_calibration.py` 未改（`git diff --exit-code` = 0），定向跑 `1 failed, 43 passed` | **未达标**（见 §6 末段） |

## 6. 反证钉（5 枚）与"没写脏工作树"

| 反证钉 | 作用（全在临时根副本上） | D 格 verdict | problems（恰等） | deadline_ms | waste_s | gaps | no_deadline |
|---|---|---|---|---|---|---|---|
| `test_counter_evidence_deadline_token_drift_is_caught` | (e) 改名到 `DEADLINE_TOKENS` 认不出 ⇒ 两份口径打脸 | `RED` | `["frontend_deadline_cost_reading_contradicts_no_deadline"]` | `300000` | `300.0` | `[]` | `True` |
| `test_counter_evidence_removing_the_deadline_moves_the_cell_to_the_other_side` | (a) 摘掉到点自停那半条（定义 + 那一跳），常数留在原位 | `MEASURED_GREEN` | `[]` | `None` | `None` | `["enforcement_not_wired"]` | `True` |
| `test_counter_evidence_retyping_the_deadline_moves_the_reading` | (d) 原件截止改大 +45000 ms ⇒ 读数必须跟着走（专打字面量） | `MEASURED_GREEN` | `[]` | `345000` | `345.0` | `[]` | `False` |
| `test_counter_evidence_unbounded_deadline_limit_goes_red_here` | (c) 上限换成无界形状 `Number.POSITIVE_INFINITY` | `RED` | `["frontend_deadline_cost_reading_unbounded=enforcement_not_wired"]` | `None` | `None` | `["enforcement_not_wired"]` | `False` |
| `test_counter_evidence_unparseable_deadline_goes_red_here` | (b) 第三跳换成不可解析形状 `Number.NaN` | `RED` | `["frontend_deadline_cost_reading_unbounded=deadline_ms_unreadable"]` | `None` | `None` | `["deadline_ms_unreadable"]` | `False` |

每枚钉的骨架 `_panel_cell` 自带四道自证：跑前取 `_tree_sha()` → 只写临时根里的 `ChatPanel.vue`
副本 → 跑 D 格 → 再取一次 `_tree_sha()` 逐枚比对 → `shutil.rmtree` 之后再核一次，最后把**原件文本
逐字**对照（写法照抄 `tests/test_r233_undefined_root_names.py` 里 R236 那枚"反证钉不许动工作树"）。
钉里另有一枚 `assert mutated != original`：反证作用不到东西上就当场报错，不留假钉。

**未结案（如实记，不当绿交回）**：`tests/test_r218_ruler_self_calibration.py:272`
`assert R.cell_lane_flip(overlay)["verdict"] == R.RED`（注释"且红的原因不是它"）从本单起读
`MEASURED_GREEN` —— 那枚 overlay 只改适配器，D 格从前在它上面红，红的正是本单换掉的这句旧口径。
该文件在本单**禁改清单**里、保持零字节改动，所以定向跑四枚文件的结果是
`1 failed, 43 passed`（失败仅这一枚）。要清它只需一行：`== R.RED` → `== R.GREEN`，
由总控裁定后代改或另立一单；本单不代改，也不靠放宽自己的判据把它蒙过去。

## 7. 窗内仍然判不动的（原文照抄，一条没消）

- `NOT_COVERED_OFFLINE 队列 worker 真取回（deploy/queue_worker.py 要真 Redis + 真进程；离线只能判状态字面，判不了 done 之后 result 真不真）`
- `NOT_COVERED_OFFLINE 报告档整轮端到端（入队→worker 跑完→/queue/status 取回正文要真容器）`

## 8. 写域与改口量

| 文件 | 行数 | sha256（前 12） |
|---|---|---|
| `scripts/r218_switch_rehearsal.py` | 869 | `adc54e0dab6f` |
| `tests/test_r218_lane_flip_stop_sets.py` | 391 | `dd6b2319b72d` |
| `docs/testing/r245-cost-reading-2026-09-25.md`（本页） | 363 | 本页不自测 sha，交回时由总控现取 |


取证时刻 `2026-09-25 16:54:23`（本地）。