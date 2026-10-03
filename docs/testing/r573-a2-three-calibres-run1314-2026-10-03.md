# R573｜A ② 三口径 × run13／run14 两窗的第一份可裁定读数（2026-10-03）

- 执行层：Erdos。工作树 `C:/Users/fengx/PycharmProjects/be-r573`（detached 于 `b85c277`），开工前 `git status --porcelain` 空。
- 本单性质：取证＋出数（零产品码）。判据全文＝派工词五格；本纸逐格给「命令原文 → 末行读数」。
- 🔴 本纸不替总控／业主裁口径：三档 × 两窗的数一起交，一句「该用哪档」都不写（沿用 R565 那条 declare 纪律，刀⑥ 就是钉这一格的）。
- 本文由生成脚本一次性写盘（见 §7 第 9 条命令）。凡表格里的数字都是脚本现取，没有人工转写。

## 0. 盘面、写域核对，以及为什么不写「在册尺够用」

- 本单产物三枚（全新增、未跟踪）：本纸、`scripts/r573_caliber_reconciliation.py`、`tests/test_r573_a2_three_calibres.py`。
- 写域核对：三枚在册量具只调用未改口，摘前摘后逐字节 sha256 全等（§6 末格）；`app/**`、`frontend/**`、`migrations/**`、评测集 `tests/fixtures/business_evaluation_100.jsonl`、`docs/handoff/**`、`deploy/.env.server` 零接触；未 `git add`／`commit`／`push`；未起容器、未打模型、未跑 `scripts/run_gate.py`、未起 `-n`／`--dist`。
- 为什么不判「在册尺够用」（派工词允许不建对账件，但要写明为什么）：
  1. `scripts/eval_frame_caliber_readout.py::main` 只出**两档范围**（105 全量／剔报告档 93），且自己明写「本件不据此改写 criterion_two_holds」；
  2. `scripts/r239_stream_gap_offline_audit.py::summarize` 只出「② 原文两格」与「账上那一格」两列；
  3. `scripts/r565_a2_denominator_buckets.py::_calibers` 出的是**披露口径**（甲＝105 全分母／乙＝B0 分母且三格并列／丙＝只报 B0），与业主这三问（逐片腿适用范围／`no_answer` 挪出分母另立格／`max_stream_frames>1` 算不算）**不是同一组轴**；
  4. ⇒ 现仓没有任何一枚件按窗出过「这三问 × 两窗」的数。对账件因此只做一件事：**调用**上面三枚在册函数（调用点 §3），把三问各自的分母/分子算出来；判则一枚都不复制。

## 1. 输入件现取（派工词前置：件缺或零行就停手，不许用半套件出数）

- 目录＝`~\AppData\Local\Temp\evalrun`（不入仓，本件只读）。

| 件 | 行数 | 字节 | sha256 前 12 |
|---|---|---|---|
| `run13-sidecar-frames.jsonl` | 105 | 874130 | `afc469ae999e` |
| `run13-sidecar.jsonl` | 105 | 54047 | `41f6de001729` |
| `run13-answers.jsonl` | 105 | 480662 | `cd35cdf5c952` |
| `run14-sidecar-frames.jsonl` | 105 | 927286 | `30e433c0362c` |
| `run14-sidecar.jsonl` | 105 | 56805 | `f0b8d386c284` |
| `run14-answers.jsonl` | 105 | 506210 | `d6d6ef0fc1f4` |
| `run13.window.json` | 13 | 427 | `f91de240c3ab` |
| `run13.shards.json` | 1 | 1493 | `9d8207c68c03` |
| `run13-report.json` | 259 | 13719 | `5732109d8d74` |
| `run14.window.json` | 13 | 435 | `80d5a77238b4` |
| `run14.shards.json` | 1 | 1493 | `9d8207c68c03` |
| `run14-report.json` | 259 | 13715 | `3033b8b712b8` |

- 判定：三本账 × 两窗共 6 枚，行数全部＝105（零枚命中「件缺或行数为 0」）⇒ 不触发停手格。逐枚 sha 现取如上，`-report.json` 与 `.shards.json` 一并取，是为了让「同一套题」可比。
- 两窗出处现取（`*.window.json`）：
    - run13：{"container": "enterprise-brain-backend-1", "dry_run": false, "fixture_sha256": "686c564ff2985744e6f050e5ea7639500c99bd80b3e32fc3a85e585f5ecdd79b", "index_backend": "", "probe_errors": [], "probe_ok": true, "probed_at": "2026-10-02 22:36:22", "revision": "fd90f3062144dffe0927d403b43f85b7470695cb", "shard_size": 1, "started_at": "2026-10-02 22:36:22", "transport": "eval_transport_ask_v2:transport"}
    - run14：{"container": "enterprise-brain-backend-1", "dry_run": false, "fixture_sha256": "686c564ff2985744e6f050e5ea7639500c99bd80b3e32fc3a85e585f5ecdd79b", "index_backend": "pgvector", "probe_errors": [], "probe_ok": true, "probed_at": "2026-10-03 00:27:29", "revision": "fd90f3062144dffe0927d403b43f85b7470695cb", "shard_size": 1, "started_at": "2026-10-03 00:27:29", "transport": "eval_transport_ask_v2:transport"}
- 两枚 `.shards.json` 逐字节同 sha（`9d8207c68c03`／`9d8207c68c03`，相等＝True）⇒ 题序一致，不是换了一套题。
- 唯一差量（本单的自证）：`index_backend` run13＝空串（＝遗留 Chroma 读路径），run14＝`pgvector`；`revision` 与 `fixture_sha256` 两枚全等。
- 一句实话：`run13.window.json` 的 `started_at` 与 R571 那次缺省 `--env-file` 裸崩同秒，而 `run13-answers.jsonl` 收在 00:25:56（总控显式补传 `--env-file` 重开）。本件不改这一格的解释，也不拿它当「两窗可比」的凭据——可比凭据是上面那几行 sha。

## 2. 在册主口径现场调用（判据 2：不重抄在册尺）

- 取数方式：`scripts/r573_caliber_reconciliation.py:232` 现场调用 `eval_frame_caliber_readout.main(["--frames", …])`；本纸用同一枚调用、`contextlib.redirect_stdout` 收 stdout，把它打印的 `A② 全量范围（105 枚）` 一节**逐字**嵌入（脚本写盘，零人工转写；§7 第 17 条命令做字节级自证：两窗各 13 行在纸内命中＝True）。
- run13：现场调用 rc=0，stdout 非空行=47，本节摘录 13 行原文：

### A② 全量范围（105 枚）（n=105）
- text_frames >1 枚数=100/105 ｜ =0（空读）枚数=5
- max_stream_frames >1 枚数=99/105 ｜ =0（空读）枚数=5
- prefix_breaks >0 枚数=5 题号=['chat-12', 'data-07', 'metric-10', 'metric-11', 'tool-02']
- uncorrected_breaks >0 枚数=1 题号=['tool-02']
- missing_chars >0 枚数=3 题号=['chart-02', 'chart-04', 'insight-07']
- extra_chars >0 枚数=8 题号=['approval-04', 'chart-02', 'chart-04', 'data-09', 'insight-07', 'report-04', 'scope-02', 'tool-03']
- cross_stream_repeat_frames（R471 第七枚，🔴 派生自 frames 列，不落成新列） >0 枚数=0 题号=无
  - 逐枚重合数=[] ｜ 本件不据此改写 criterion_two_holds（当年读数不重判）
- criterion_two_holds=True 枚数=95/105（在册合取口径=_frame_verdict）
- criterion_two_holds=False 题号=['approval-04', 'chart-01', 'chart-02', 'chart-04', 'data-09', 'insight-07', 'report-04', 'scope-02', 'tool-02', 'tool-03']
- 判据② 原文两格：`text 事件数 >1` 与 `逐字比对无缺字`（缺字=missing_chars）⇒ 缺字枚数=3


- run14：现场调用 rc=0，stdout 非空行=47，本节摘录 13 行原文：

### A② 全量范围（105 枚）（n=105）
- text_frames >1 枚数=102/105 ｜ =0（空读）枚数=3
- max_stream_frames >1 枚数=101/105 ｜ =0（空读）枚数=3
- prefix_breaks >0 枚数=7 题号=['chat-12', 'data-07', 'metric-07', 'metric-10', 'report-06', 'scope-05', 'tool-02']
- uncorrected_breaks >0 枚数=2 题号=['scope-05', 'tool-02']
- missing_chars >0 枚数=3 题号=['chart-02', 'chart-04', 'insight-07']
- extra_chars >0 枚数=6 题号=['chart-02', 'chart-04', 'data-09', 'insight-05', 'insight-07', 'report-04']
- cross_stream_repeat_frames（R471 第七枚，🔴 派生自 frames 列，不落成新列） >0 枚数=0 题号=无
  - 逐枚重合数=[] ｜ 本件不据此改写 criterion_two_holds（当年读数不重判）
- criterion_two_holds=True 枚数=96/105（在册合取口径=_frame_verdict）
- criterion_two_holds=False 题号=['chart-01', 'chart-02', 'chart-04', 'data-09', 'insight-05', 'insight-07', 'report-04', 'scope-05', 'tool-02']
- 判据② 原文两格：`text 事件数 >1` 与 `逐字比对无缺字`（缺字=missing_chars）⇒ 缺字枚数=3


- 两账对照（只交数）：`criterion_two_holds` 全量口径 run13＝95/105、run14＝96/105；上一班实际只交的剔报告档那套＝84/93、85/93。
- 排除条件在本单两窗仍不成立（见上面原文第 2 行）：`队列格非空的报告题数=0/12`、`(text_frames,max_stream_frames)=(1,1) 枚数=0/12`，与 run9 同形。

## 3. 调用点（判据 2 的凭据：调用在册函数，判则一枚都不复制）

- `scripts/r573_caliber_reconciliation.py:83` → `audit.read_rows`（真源现取 ＝scripts/r239_stream_gap_offline_audit.py:107）
- `scripts/r573_caliber_reconciliation.py:89` → `readout.load_rows`
- `scripts/r573_caliber_reconciliation.py:96` → `buckets.read_round`（真源现取 ＝scripts/r565_a2_denominator_buckets.py:363）
- `scripts/r573_caliber_reconciliation.py:112` → `audit.judge_row`（真源现取 ＝scripts/r239_stream_gap_offline_audit.py:273）
- `scripts/r573_caliber_reconciliation.py:116` → `audit.recomputed_ledger`（真源现取 ＝scripts/r239_stream_gap_offline_audit.py:192）
- `scripts/r573_caliber_reconciliation.py:117` → `audit.recomputed_ledger（对内存影子行走同一枚函数＝丙档反事实探针）`（真源现取 ＝同上:192）
- `scripts/r573_caliber_reconciliation.py:185` → `buckets.B1 / buckets.B2（桶名常量）`（真源现取 ＝scripts/r565_a2_denominator_buckets.py:87）
- `scripts/r573_caliber_reconciliation.py:187` → `buckets.B3（桶名常量）`（真源现取 ＝scripts/r565_a2_denominator_buckets.py:87）
- `scripts/r573_caliber_reconciliation.py:232` → `readout.main`
- 对侧还有两枚在册符号在本单被引用为判据出处：`audit.event_count_gt_1`（:174，②-a 那一路）、`audit.schedule_check`（:234，可判性）、`buckets.BUCKET_PRIORITY`（:96，归账优先级）。
- 行号会漂、符号不会：上表每格同时给符号名。对账件里没有一条自写的判帧规则，只把在册返回值按业主三问重新分组。

## 4. 六组数（判据 1：三档 × 每档两读 × 两窗；本单不选口径）

- 记法：**primary**＝该档自报主读数键（`ledger` 账上／`recomputed` 在册七枚合取／`without_msf` 摘掉 `max_stream_frames>1`／`literal` 判据② 原文两格）；**四种分子并列**一列都不许省（省了就等于替总控挑口径）。

### run13（读后端＝（空串＝遗留 Chroma 读路径））

| 档 | 分母/总行 | 扣题 | primary | 比值 | 四种分子：账上/复算/摘msf/②原文 | 不可判 |
|---|---|---|---|---|---|---|
| 甲-1 | 105/105 | 0 | ledger=95 | 0.9048 | 95 / 95 / 96 / 97 | 5 |
| 甲-2 | 100/105 | 5 | ledger=95 | 0.9500 | 95 / 95 / 96 / 97 | 0 |
| 乙-1 | 100/105 | 5 | ledger=95 | 0.9500 | 95 / 95 / 96 / 97 | 0 |
| 乙-2 | 97/105 | 8 | ledger=95 | 0.9794 | 95 / 95 / 96 / 97 | 0 |
| 丙-算 | 105/105 | 0 | recomputed=95 | 0.9048 | 95 / 95 / 96 / 97 | 5 |
| 丙-不算 | 105/105 | 0 | without_msf=96 | 0.9143 | 95 / 95 / 96 / 97 | 5 |

- **甲-1**｜在册桶口径：剔 B1 天然短 ∪ B2 无逐片腿
    - 被扣题号＝无｜档内红题（账上）＝approval-04, chart-01, chart-02, chart-04, data-09, insight-07, report-04, scope-02, tool-02, tool-03
    - 不可判＝5 枚（approval-04, data-09, report-04, scope-02, tool-03）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- **甲-2**｜逐帧那一列到底有没有：剔 text_frames==0（②-a 在这些行不可判）
    - 被扣题号＝approval-04, data-09, report-04, scope-02, tool-03｜档内红题（账上）＝chart-01, chart-02, chart-04, insight-07, tool-02
    - 不可判＝0 枚（无）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- **乙-1**｜只把 family=no_answer_produced 那一族挪出分母，另立格（认定走现取预制指纹，与归账桶名无关）
    - 被扣题号＝approval-04, data-09, report-04, scope-02, tool-03｜档内红题（账上）＝chart-01, chart-02, chart-04, insight-07, tool-02
    - 不可判＝0 枚（无）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
    - 另立格 `collector_sentinel`：枚数=3 题号=[chart-02, chart-04, insight-07] 账上绿=0 `text_frames`={'insight-07': 31, 'chart-02': 56, 'chart-04': 34} `answer_sha`=['96a0fc6fc992']（🔴 不蒸发）
    - 另立格 `no_answer_produced`：枚数=5 题号=[approval-04, data-09, report-04, scope-02, tool-03] 账上绿=0 `text_frames`={'data-09': 0, 'approval-04': 0, 'scope-02': 0, 'tool-03': 0, 'report-04': 0} `answer_sha`=['cea11078566e']（🔴 不蒸发）
- **乙-2**｜连采集器哨兵那一族一起挪出（B3 全体），另立格
    - 被扣题号＝approval-04, chart-02, chart-04, data-09, insight-07, report-04, scope-02, tool-03｜档内红题（账上）＝chart-01, tool-02
    - 不可判＝0 枚（无）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
    - 另立格 `collector_sentinel`：枚数=3 题号=[chart-02, chart-04, insight-07] 账上绿=0 `text_frames`={'insight-07': 31, 'chart-02': 56, 'chart-04': 34} `answer_sha`=['96a0fc6fc992']（🔴 不蒸发）
    - 另立格 `no_answer_produced`：枚数=5 题号=[approval-04, data-09, report-04, scope-02, tool-03] 账上绿=0 `text_frames`={'data-09': 0, 'approval-04': 0, 'scope-02': 0, 'tool-03': 0, 'report-04': 0} `answer_sha`=['cea11078566e']（🔴 不蒸发）
- **丙-算**｜分母不动；分子＝在册七枚合取（含 max_stream_frames>1）
    - 被扣题号＝无｜档内红题（账上）＝approval-04, chart-01, chart-02, chart-04, data-09, insight-07, report-04, scope-02, tool-02, tool-03
    - 不可判＝5 枚（approval-04, data-09, report-04, scope-02, tool-03）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- **丙-不算**｜分母不动；分子＝把 max_stream_frames>1 那一枚对每题走反事实探针
    - 被扣题号＝无｜档内红题（账上）＝approval-04, chart-01, chart-02, chart-04, data-09, insight-07, report-04, scope-02, tool-02, tool-03
    - 不可判＝5 枚（approval-04, data-09, report-04, scope-02, tool-03）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- 桶现取＝{'B0': 97, 'B1': 0, 'B2': 0, 'B3': 8}｜`STREAM_PIECE_MIN_CHARS` 闸现取＝20（真源 `app/agents/nodes.py:433`，符号 `STREAM_PIECE_MIN_CHARS`，本单不抄第二份数值）｜同题多轮折叠＝0。
- 在册预制指纹现取（非手抄）：`96a0fc6fc992`＝collector_sentinel/APPROVAL_FAILED_SENTINEL/36字, `cea11078566e`＝no_answer_produced/failure_text/21字, `ec71005139bd`＝collector_sentinel/BLANK_SENTINEL/18字。
- 在册量具自报 diagnostics＝{'tool_calls_unjoinable': [], 'single_frame_without_arrival_coordinates': [], 'ms_reading_sensitivity_rows': [], 'b0_rows_with_no_text_frame': [], 'frames_column_conflicts_summary': ['insight-07', 'chart-02', 'chart-04'], 'sentinel_rows_outside_prefab_set': [], 'ledger_vs_literal_disagreements': ['chart-01', 'tool-02'], 'attempts_collapsed': 0}。

### run14（读后端＝pgvector）

| 档 | 分母/总行 | 扣题 | primary | 比值 | 四种分子：账上/复算/摘msf/②原文 | 不可判 |
|---|---|---|---|---|---|---|
| 甲-1 | 105/105 | 0 | ledger=96 | 0.9143 | 96 / 96 / 97 / 99 | 3 |
| 甲-2 | 102/105 | 3 | ledger=96 | 0.9412 | 96 / 96 / 97 / 99 | 0 |
| 乙-1 | 102/105 | 3 | ledger=96 | 0.9412 | 96 / 96 / 97 / 99 | 0 |
| 乙-2 | 99/105 | 6 | ledger=96 | 0.9697 | 96 / 96 / 97 / 99 | 0 |
| 丙-算 | 105/105 | 0 | recomputed=96 | 0.9143 | 96 / 96 / 97 / 99 | 3 |
| 丙-不算 | 105/105 | 0 | without_msf=97 | 0.9238 | 96 / 96 / 97 / 99 | 3 |

- **甲-1**｜在册桶口径：剔 B1 天然短 ∪ B2 无逐片腿
    - 被扣题号＝无｜档内红题（账上）＝chart-01, chart-02, chart-04, data-09, insight-05, insight-07, report-04, scope-05, tool-02
    - 不可判＝3 枚（data-09, insight-05, report-04）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- **甲-2**｜逐帧那一列到底有没有：剔 text_frames==0（②-a 在这些行不可判）
    - 被扣题号＝data-09, insight-05, report-04｜档内红题（账上）＝chart-01, chart-02, chart-04, insight-07, scope-05, tool-02
    - 不可判＝0 枚（无）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- **乙-1**｜只把 family=no_answer_produced 那一族挪出分母，另立格（认定走现取预制指纹，与归账桶名无关）
    - 被扣题号＝data-09, insight-05, report-04｜档内红题（账上）＝chart-01, chart-02, chart-04, insight-07, scope-05, tool-02
    - 不可判＝0 枚（无）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
    - 另立格 `collector_sentinel`：枚数=3 题号=[chart-02, chart-04, insight-07] 账上绿=0 `text_frames`={'insight-07': 31, 'chart-02': 56, 'chart-04': 34} `answer_sha`=['96a0fc6fc992']（🔴 不蒸发）
    - 另立格 `no_answer_produced`：枚数=3 题号=[data-09, insight-05, report-04] 账上绿=0 `text_frames`={'data-09': 0, 'insight-05': 0, 'report-04': 0} `answer_sha`=['cea11078566e']（🔴 不蒸发）
- **乙-2**｜连采集器哨兵那一族一起挪出（B3 全体），另立格
    - 被扣题号＝chart-02, chart-04, data-09, insight-05, insight-07, report-04｜档内红题（账上）＝chart-01, scope-05, tool-02
    - 不可判＝0 枚（无）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
    - 另立格 `collector_sentinel`：枚数=3 题号=[chart-02, chart-04, insight-07] 账上绿=0 `text_frames`={'insight-07': 31, 'chart-02': 56, 'chart-04': 34} `answer_sha`=['96a0fc6fc992']（🔴 不蒸发）
    - 另立格 `no_answer_produced`：枚数=3 题号=[data-09, insight-05, report-04] 账上绿=0 `text_frames`={'data-09': 0, 'insight-05': 0, 'report-04': 0} `answer_sha`=['cea11078566e']（🔴 不蒸发）
- **丙-算**｜分母不动；分子＝在册七枚合取（含 max_stream_frames>1）
    - 被扣题号＝无｜档内红题（账上）＝chart-01, chart-02, chart-04, data-09, insight-05, insight-07, report-04, scope-05, tool-02
    - 不可判＝3 枚（data-09, insight-05, report-04）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- **丙-不算**｜分母不动；分子＝把 max_stream_frames>1 那一枚对每题走反事实探针
    - 被扣题号＝无｜档内红题（账上）＝chart-01, chart-02, chart-04, data-09, insight-05, insight-07, report-04, scope-05, tool-02
    - 不可判＝3 枚（data-09, insight-05, report-04）｜账与复算不同代＝无｜只因 `max_stream_frames>1` 翻动的题＝chart-01
- 桶现取＝{'B0': 99, 'B1': 0, 'B2': 0, 'B3': 6}｜`STREAM_PIECE_MIN_CHARS` 闸现取＝20（真源 `app/agents/nodes.py:433`，符号 `STREAM_PIECE_MIN_CHARS`，本单不抄第二份数值）｜同题多轮折叠＝0。
- 在册预制指纹现取（非手抄）：`96a0fc6fc992`＝collector_sentinel/APPROVAL_FAILED_SENTINEL/36字, `cea11078566e`＝no_answer_produced/failure_text/21字, `ec71005139bd`＝collector_sentinel/BLANK_SENTINEL/18字。
- 在册量具自报 diagnostics＝{'tool_calls_unjoinable': [], 'single_frame_without_arrival_coordinates': [], 'ms_reading_sensitivity_rows': [], 'b0_rows_with_no_text_frame': [], 'frames_column_conflicts_summary': ['insight-07', 'chart-02', 'chart-04'], 'sentinel_rows_outside_prefab_set': [], 'ledger_vs_literal_disagreements': ['chart-01', 'scope-05', 'tool-02'], 'attempts_collapsed': 0}。

### 六组数之间的关系（只述算术，不作裁定）

- run13：甲-1 与 丙-算 同分母 105、分子差＝0；丙-不算 − 丙-算 ＝ 1 枚（chart-01）；乙-2 分母降到 97 后比值 0.9794 仍非 1.0000 ⇒ 挪分母不改变「仍有红题」这个事实（红题＝chart-01, tool-02）。
- run14：甲-1 与 丙-算 同分母 105、分子差＝0；丙-不算 − 丙-算 ＝ 1 枚（chart-01）；乙-2 分母降到 99 后比值 0.9697 仍非 1.0000 ⇒ 挪分母不改变「仍有红题」这个事实（红题＝chart-01, scope-05, tool-02）。
- 甲-2 与 乙-1 在 run13 同为 100/105、run14 同为 102/105 且扣的是同一批题号——这不是巧合：两窗 `text_frames==0` 的行恰好就是 `no_answer_produced` 那一族（§5 逐枚点名）。**这条等价只在这两窗成立，不是恒等式**，甲-2 剔的是「②-a 不可判」，乙-1 剔的是「答案是预制串」，判据来源不同。

## 5. 不可判 ≠ 绿（判据 3；run6 那遍把「0 枚可判行」抄成绿的教训）

| 窗 | 行级到达键在位 | 在册 `schedule_check` 可判 | 不可判枚数＝题号 | 不可判依据原文 | `text_frames==1` | `text_frames==0` |
|---|---|---|---|---|---|---|
| run13 | 105/105 | 100/105 | 5 枚＝approval-04, data-09, report-04, scope-02, tool-03 | `帧账无逐帧到达/逐帧字数（R223 并树之前的账，run7 即此形）` | 0 | 5 |
| run14 | 105/105 | 102/105 | 3 枚＝data-09, insight-05, report-04 | `帧账无逐帧到达/逐帧字数（R223 并树之前的账，run7 即此形）` | 0 | 3 |

- 🔴 层界：`arrival_keys`（`scripts/r239_stream_gap_offline_audit.py:293`，符号 `ARRIVAL_KEYS`）量**行级**键在不在（`frames`/`events`/`stream_clock`/`queue`/`first_visible_at`/`first_visible_event`/`first_visible_ms`），两窗 105/105 全在位；`schedule_check`（同件 `:234`）量**逐帧**到达坐标与逐帧字数在不在。前者在位不等于后者可判。执行层先前用手探键名去数、读出 0/105，那是**探针用错层**（键名猜错），不是账的形状；以在册函数读数为准（上表）。
- 不可判＝逐帧那一列派生不出 ⇒ 一律记「不可判」并给枚数与题号：**不并入分子，也不并入分母的红题**。甲-1 分母仍＝105（不可判≠被扣），另报 5/3 枚。
- B2（`text_frames==1` 且与 `request.completed` 同毫秒）在两窗**天然为空**（上表＝0 枚），不是量具摘瞎：同表 `text_frames==0`＝5/3 枚，与「不可判」逐枚对齐，形状自洽。
- B3 内部两形不同，不许混为一谈：`no_answer_produced`（`answer_sha=cea11078566e`）`text_frames` 全＝0 ⇒ 落「不可判」；`collector_sentinel`（`APPROVAL_FAILED_SENTINEL`，`answer_sha=96a0fc6fc992`）三枚 `text_frames`＝31/56/34、账上绿＝0 ⇒ **有逐片腿但答案是预制串**，属「判得出、判为红」。两族在乙档另立格逐枚点名，一枚都不蒸发。
- R471 第七枚 `cross_stream_repeat_frames`：在册尺 >0 枚数＝0（§2 原文），但它在 `text_frames==0` 那 5/3 枚上派生不出（`frames` 列为空）⇒ 这一格本单是「部分未量」，不许写成「零重合＝通过」。
- run6 对照（只记形状，不复算旧账）：那遍是「逐帧到达可判行=0」却被抄成绿；本单两窗可判 100/102 枚，不可判那 5/3 枚逐枚点名进另立格，两格不许互顶。

## 6. 反证刀（判据 4；七把，victim 全是在册件本身或在册读数）

- 摘刀方式一律＝**内存影子**（改 `audit` / `buckets` 的模块属性，跑完当场复原），盘上零写口；需要写盘的三形（截断／零字节／翻转）全写在仓外 `C:\Users\fengx\AppData\Local\Temp\r573_knife_out`，原账一字节不动。
- 摘前 sha：在册件 {"r239_stream_gap_offline_audit.py": "9ddeaccacd91", "r565_a2_denominator_buckets.py": "40ccb50fd1cc", "eval_frame_caliber_readout.py": "de3b786c41be"}；六本账 {"run13-sidecar-frames.jsonl": "afc469ae999e", "run13-sidecar.jsonl": "41f6de001729", "run13-answers.jsonl": "cd35cdf5c952", "run14-sidecar-frames.jsonl": "30e433c0362c", "run14-sidecar.jsonl": "f0b8d386c284", "run14-answers.jsonl": "d6d6ef0fc1f4"}

### 刀①｜摘掉在册 ②-a 那一路（victim＝`audit.event_count_gt_1`，真源 `r239_stream_gap_offline_audit.py:174`）

- 摘前：甲-1 `literal`（②原文两格分子）＝97，`ledger`＝95
- 摘后：甲-1 `literal`＝0（判据 4-①「甲档数必须变」达标），`ledger`＝95（账上列**不该被带走**，实测未被带走）
- 复原：函数同一性＝True；盘上 sha 复验见本节末。

### 刀②｜摘掉在册复算（victim＝`audit.recomputed_ledger`，真源 `:192`）

- 摘前：丙-算 primary＝95（复算列＝95，红题 10 枚）
- 摘后：丙-算 primary＝105（复算列＝105，复算红题＝0 枚），丙档翻动＝无
- 这一刀证明丙档分子真由在册七枚合取现算、不是硬编码常数。复原＝True。

### 刀③｜摘掉在册归账优先级（victim＝`buckets.BUCKET_PRIORITY`，真源 `r565_a2_denominator_buckets.py:96`）

- 摘前：乙-2 分母＝97（扣 8 枚）｜乙-1 分母＝100（扣 5 枚）
- 摘后：乙-2 分母＝105（扣 0 枚）｜乙-1 分母＝100（扣＝approval-04, data-09, report-04, scope-02, tool-03）
- 🔴 关键形状：乙-1 **不随桶名归零**——它的认定走现取 `answer_sha` 指纹（`buckets.prefab_fingerprints`，真源 `:165`），与 `BUCKET_PRIORITY` 无关；乙-2 走桶归账，摘了就漏。⇒ 判据 4-②「预制句不许被并进 B0」不是只靠一把刀撑着。另立格摘后仍＝{"collector_sentinel": 3, "no_answer_produced": 5}（不蒸发）。复原＝True。

### 刀④｜翻一枚在册 `criterion_two_holds`（victim＝帧账里的账上读数本身）

- 改动枚数＝1（只动 `doc-01` 一行，写仓外副本）
- 摘前 → 摘后：`ledger` 95 → 94｜`recomputed` 95 → 95｜`without_msf` 96 → 96｜`literal` 97 → 97
- 甲-1 primary 95 → 94｜丙-算 primary 95 → 95｜丙-不算 primary 96 → 96
- 判据 4-② 达标：手翻账上读数 ⇒ 依赖账上的那一路跟着动，而**复算那一路纹丝不动**（`doc-01` 进账上红题＝True，进复算红题＝False）。
- 原帧账 sha 复验：afc469ae999e ＝ 摘前 `afc469ae999e` ⇒ True（本刀不写原账）。
- ⚠️ 一处易误读，纸上说明白：`%TEMP%/r573_knife_real.py` 那版在同样这一步打印的「丙-算=94」取的是 `green_ledger`（账上列），不是该档 primary；本节的四列对照才是准数（复算列摘后仍 95）。

### 刀⑤｜截断／零字节帧账 ⇒ 必须 REFUSE，不许报「无缺字」

- 🔴 这枚刀**第一版没有牙**，订正记录在案：原先把截断点定成「末行取前 8000 字符」，而 `run13-sidecar-frames.jsonl` 末行实长＝**7959 字符** ⇒ 切片等于没切，`rc=0`、照常出完整表（表里还带着「无缺字」字样）。是复核 `rc=0` 时才发现的。**教训**：截断类反证只能按「行长 − N」定，不许写死字符数。
- 真截断（末行 7959 → 去尾 300 字，keep=7659）：rc=**2**；末行＝`[r573][REFUSE] 帧账读不动（截断或形状不对）：Expecting ':' delimiter: line 1 column 7660 (char 7659)`
    含 `Traceback` 字样＝False（必须 False）；含假绿文案「无缺字」＝False（必须 False）
- 真截断（末行 7959 → 去尾 20 字，keep=7939）：rc=**2**；末行＝`[r573][REFUSE] 帧账读不动（截断或形状不对）：Unterminated string starting at: line 1 column 7932 (char 7931)`
    含 `Traceback` 字样＝False；含「无缺字」＝False
- 零字节副本：rc=**2**；末行＝`[r573][REFUSE] 输入件零字节：frames=C:/Users/fengx/AppData/Local/Temp/r573_knife_out/run13-empty-frames.jsonl ⇒ 不可判，拒绝出数`
    含 `Traceback` 字样＝False；含「无缺字」＝False
- 常驻化对照：本单钉 `test_missing_empty_and_truncated_ledgers_all_refuse` 的截断法＝「整本之后再接半行」（`good + good[:40]`，合成窗），不依赖某一行多长，因此不受上面那枚「固定字符数＝没切」的坑影响；同钉还带正控复原 rc=0。判据 4-③ 在这一形上是**盘上副本**取证（不写原账）。
- 文案通道现取：`REFUSE`／`拒宣布` 一律 `print(..., file=sys.stderr)`（`scripts/r573_caliber_reconciliation.py:357`／`:360`）——只捕 stdout 的探针会读成「空输出」，本单两路同捕才拿到上面那行。

### 刀⑥｜拿单一口径宣布翻绿 ⇒ 当场拒

- rc=3（要求非 0＝RC_GREEN 那枚拒）；末行＝`[r573][拒宣布] 本件不选口径：甲／乙／丙 三档 × 两窗必须一起交。单独拿「丙-不算」宣布 A② 翻绿＝分母被人挪过 ⇒ 拒。要裁定请由总控拿着六组数下条，记进看板。`

### 刀⑦｜只读自证：量具与被量的账都不许被本单写过

- 三枚在册件摘前/摘后逐字节全等＝True：{"r239_stream_gap_offline_audit.py": "9ddeaccacd91", "r565_a2_denominator_buckets.py": "40ccb50fd1cc", "eval_frame_caliber_readout.py": "de3b786c41be"}
- 六本账摘前/摘后逐字节全等＝True：{"run13-sidecar-frames.jsonl": "afc469ae999e", "run13-sidecar.jsonl": "41f6de001729", "run13-answers.jsonl": "cd35cdf5c952", "run14-sidecar-frames.jsonl": "30e433c0362c", "run14-sidecar.jsonl": "f0b8d386c284", "run14-answers.jsonl": "d6d6ef0fc1f4"}
- 内存影子复原核对：event_count_gt_1=True, recomputed_ledger=True, BUCKET_PRIORITY=True
- 常驻化：本单钉里同一形状由 `test_counter_evidence_1..5` 在合成窗上守着（含 `test_counter_evidence_5_the_instrument_itself_never_writes_its_inputs`）；真窗读数只落本纸，不入钉（账在 `%TEMP%`，钉不许依赖它）。

## 7. 本单跑过的命令（原文 → 退出码 → 末行读数）

- 解释器一律 `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8`，cwd＝本树；无一条 `-n`／`--dist`，无一条 `scripts/run_gate.py`。

- **1** `git -C be-r573 rev-parse --short HEAD ｜ git status --porcelain ｜ git diff --numstat HEAD` → rc=0 → 末行：`b85c277` ＋三枚 `??`（本单三产物）＋ numstat 空
- **2** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 scripts/eval_frame_caliber_readout.py --help` → rc=0 → 末行：usage 原文，`--frames FRAMES` 一枚参数（零网络零模型，可安全读）
- **3** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 scripts/r573_caliber_reconciliation.py --help` → rc=0 → 末行：usage 原文（`--evalrun`/`--tag`/`--frames`/`--expect-denominator`/`--format`/`--no-rows`/`--declare-green`）
- **4** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 scripts/eval_frame_caliber_readout.py --frames %TEMP%/evalrun/run13-sidecar-frames.jsonl` → rc=0 → 末行：`criterion_two_holds=True 枚数=95/105（在册合取口径=_frame_verdict）`
- **5** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 scripts/eval_frame_caliber_readout.py --frames %TEMP%/evalrun/run14-sidecar-frames.jsonl` → rc=0 → 末行：`criterion_two_holds=True 枚数=96/105（在册合取口径=_frame_verdict）`
- **6** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 scripts/r573_caliber_reconciliation.py --no-rows` → rc=0 → 末行：stdout 208 行；两窗六档齐，见 §4
- **7** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 scripts/r573_caliber_reconciliation.py --format json --no-rows` → rc=0 → 末行：rc=0，`reports` 两枚 × `groups` 六枚（§4 由这笔计算直写）
- **8** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 %TEMP%/r573_knife_real.py（刀①④⑤⑥⑦ 旧版）` → rc=0 → 末行：`AFTER sha(run13 frames)=afc469ae999e 未变=True`
- **9** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 %TEMP%/r573_knife_add.py（刀④四列对照）` → rc=0 → 末行：`甲-1 … 翻doc-01后: ledger=94 recomp=95 woMSF=96 literal=97 primary=94`
- **10** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 %TEMP%/r573_knife_real2.py（刀②③⑦）` → rc=0 → 末行：`盘上自证：三枚在册件 sha 全等=True ｜ 六本账 sha 全等=True`
- **11** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 -m pytest tests/test_r573_a2_three_calibres.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%/r573btF -q` → rc=0 → 末行：`14 passed in 0.45s`（另两遍 `0.54s`／`0.55s`，同 rc=0）
- **12** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 -m pytest tests/test_r239_stream_gap_offline.py tests/test_r518_a2_lane_attribution.py tests/test_r518_counter_evidence_knives.py tests/test_r565_a2_denominator_buckets.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%/r573btH -q` → rc=0 → 末行：`67 passed in 2.59s`
- **13** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 -m py_compile scripts/r573_caliber_reconciliation.py tests/test_r573_a2_three_calibres.py` → rc=0 → 末行：rc=0
- **14** `AST 现取（`ast.parse` 两枚件）` → rc=0 → 末行：`scripts/…ast-ok funcs= 15`／`tests/…funcs= 24`
- **15** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 %TEMP%/r573_doc_full1b.py（重建本纸 §0–§4）` → rc=0 → 末行：`STAGE1 rewritten bytes= 14744`
- **16** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 %TEMP%/r573_doc_full2.py（写本纸 §5–§6）` → rc=0 → 末行：`STAGE2 ok bytes= 7987 total= 28523`
- **17** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 %TEMP%/r573_verb2.py`（重跑逐字自证，收紧摘录边界后）→ rc=0 → 末行：`VERBATIM run13 rc= 0 lines= 13 in-paper= True`／`VERBATIM run14 rc= 0 lines= 13 in-paper= True`
- **18** `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8 -c`（对本纸做原始字节形态校验：数 CRLF／裸CR／裸LF／BOM＋sha256）→ rc=0 → 末行读数见交回正文（本纸不自记，理由见上一格）

- 🔴 `%TEMP%` 在 PowerShell 里不展开：`--basetemp=%TEMP%\r573btX` 那形会 `FileNotFoundError`，本单一律写 `--basetemp="$env:TEMP/r573btX"`（上表为可读性还原成 `%TEMP%`，实跑原文用 `$env:TEMP`）。
- 🔴 本机两枚工具坑，本单各踩一次，记在这里免得下一班重踩：① `apply_patch` 在此通道一律 `Invalid patch`，本单全程用 here-string＋`[IO.File]::WriteAllText(..., UTF8Encoding(false))` 落脚本；② 追写长文件时 `io.open(P,"wb").write(io.open(P,"rb").read() + body)` **会先求值 `"wb"` 而清空文件**——本纸 §0–§4 曾因此丢过一次，已用生成脚本整篇重建（这也是本纸「单源生成、无人工转写」的直接原因）。
- 未跑清单：全量门 `scripts/run_gate.py` 未跑（总控独占）；`tests/test_r239_*` 之外没有任何点名件以外的 pytest 被起过。

## 8. 未验格（照实写，不洗绿）

- ① 三档裁定本身**未裁**：本单只交六组数，甲／乙／丙谁算 A② 由总控＋业主下条。
- ② 全量回归门**未跑**（`scripts/run_gate.py` 属总控独占；同波两枚在飞）。本单只跑了自己那枚钉（14 枚）与点名的邻件四枚（67 枚）。
- ③ 容器内实际生效的读路径**未现取**：`index_backend` 只证到 `window.json` 里写的那一格（run13 空串／run14 pgvector），没进容器读环境变量，因为禁动容器 ⇒ 「run13＝Chroma、run14＝pgvector」是本单的前提而非实测。
- ④ 逐帧合并节奏（≥20 字或 100 ms 合并／禁单字碎片）本单只取了「可判／不可判」两态枚数，没把 `min_increment_chars`／`single_char_fragments` 逐题摊开——那是另一格，不在本单判据里。
- ⑤ R471 第七枚 `cross_stream_repeat_frames`：在册尺 >0 枚数＝0，但在 `text_frames==0` 那 5/3 枚上派生不出 ⇒ 该格是「部分未量」，不许当「零重合＝通过」（§5 已点名）。
- ⑥ 真窗六组数**只在纸上**：帧账在 `%TEMP%`，不入仓，钉不许依赖它 ⇒ 仓内常驻钉（§9 那 14 枚）只钉形状与算术守恒，同一份数若日后 `%TEMP%` 被清，只有本纸能复现；复现命令见 §7 第 6/7 条。
- ⑦ `sidecar`／`answers` 两本账的键集（R123 那枚九键＋甲案七键）未逐枚核——它们不吃 A② 分母，本单只用其题号与终答 sha。
- ⑧ `run13.window.json` 的 `started_at`（2026-10-02 22:36:22）与 R571 裸崩同秒这一格**未解释**：本单不改解释、也不拿它当两窗可比的凭据（可比凭据＝§1 那三行 sha）。

## 9. 三枚产物自证（判据 5：行尾与纸面）

- `scripts/r573_caliber_reconciliation.py`：行数=374 字节=22738 CRLF=374 裸CR=0 裸LF=0 BOM=False sha256前12=`d94a77b13684`
- `tests/test_r573_a2_three_calibres.py`：行数=383 字节=21345 CRLF=383 裸CR=0 裸LF=0 BOM=False sha256前12=`b74a6dbdf4b7`
- `docs\testing\r573-a2-three-calibres-run1314-2026-10-03.md`（本纸）：🔴 自指豁免——本行若写死自己的行数/sha，任何一次后续修订都会把它变成假话，故本纸**不记**自身行数/字节/sha；最终三枚数值由 §7 第 18 条命令在**最后一次写盘之后**现取，读数落在交回正文（不落本纸）。本节写入时那一笔的形态自证已核：单形 CRLF、无裸 CR、无裸 LF、无 BOM（同一枚校验脚本）。
- 行尾单形自证：三枚件均「CRLF 枚数 == 行数、裸 CR=0、裸 LF=0、无 BOM」⇒ 单形 CRLF 成立（新件也按本班规矩落 CRLF：这台机 `core.autocrlf=true` 且无 `.gitattributes`，盘上稳定态是 CRLF）。
- 判据 3 的自证：`tests/test_r573_a2_three_calibres.py` 里 skip／xfail／`xit`／`describe.skip` 计数现取＝0（0 才算不降级）；同文件另有常驻钉 `test_this_file_carries_no_downgrade_marker`。
- 14 枚钉名单（`pytest --collect` 同源，全绿）：`test_six_groups_exist_and_conserve_every_row`／`test_jia_deducts_by_bucket_in_one_reading_and_by_missing_leg_in_the_other`／`test_yi_moves_the_prefab_out_and_still_names_every_one_of_it`／`test_bing_numbers_differ_by_exactly_the_max_stream_conjunct`／`test_unmeasurable_rows_are_listed_and_never_counted_green`／`test_missing_empty_and_truncated_ledgers_all_refuse`／`test_a_quietly_smaller_window_is_refused_unless_the_denominator_says_so`／`test_declaring_green_with_one_calibre_is_refused`／`test_this_file_carries_no_downgrade_marker`／`test_counter_evidence_1..5`（五把合成窗刀）。
- 本纸由脚本单源生成：§2 是从在册 `main()` 的 stdout 逐字嵌入（边界见 §7 第 4/5 条），§4/§5 由 `build_report()` 直写，§6 由当场重跑的七把刀直写 ⇒ 纸面数字与盘面读数之间没有人抄这一环。

