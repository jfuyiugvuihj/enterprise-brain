# R565 · V1 门 A② 的分母拆桶 —— 取证与量具凭据（2026-10-02）

派工：总控线 10-02 17:3x（单号 R565）。执行席独占 worktree `C:\Users\fengx\PycharmProjects\be-r565`。
本纸只交数与出处，**不交结论**；甲／乙／丙三口径全部交回，🔴 本席不替总控选口径。
零 commit（总控代提交）；零动主树；零容器；零打模型；零 `spawn_agent`。

## 0. 盘面与窗态前提现取（命令原文 → 末行）

```
git -C C:\Users\fengx\PycharmProjects\be-r565 rev-parse --short HEAD
git -C C:\Users\fengx\PycharmProjects\be-r565 rev-parse --abbrev-ref HEAD
git -C C:\Users\fengx\PycharmProjects\be-r565 status --porcelain
```
末行读数（17:5x 现取，此后未变）：
- `c9243d4` ／ `codex/be-r565`（＝开工基点，与派工词所给一致）
- `?? scripts/r565_a2_denominator_buckets.py` ＋ `?? tests/test_r565_a2_denominator_buckets.py`（两枚新件；本纸是第三枚）——除这三枚之外 `dirty=0`，一枚在册件都没动。

窗态（🔴 因此本单**一枚读数都没跑**）：

```
Get-ChildItem $env:TEMP\evalrun -File | Select Name,Length,LastWriteTime
Get-Process python | Select Id,StartTime
```
- 17:59:07 现取：`run12-sidecar.jsonl` 13108 B / `run12-sidecar-frames.jsonl` 300600 B，`LastWriteTime=2026/10/2 17:58:29`（38 秒前还在长）⇒ run12 真机窗确实在开。
- 同刻 python 进程 6 枚在飞（14828／32844／35588／37876／41996／42440）。
- 侧车现在 **41 行**（半窗）；`run12-answers.jsonl` 尚未落盘（launcher 收齐才写）。
- 本席对两本 run12 账**只读未写**：没有追加重跑、没有删、没有改；行数只用于判窗态。

解释器：本树无 `.venv` 无 `node_modules`，一律
`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`（绝对路径；PATH 上的 `python` 是 anaconda3，禁用）。
窗内本席只起过 `py_compile` 与 `--help`（派工词明文允许）＋ PowerShell／rg 静态读，**没起过 pytest／vitest／量具**。

## 1. 事实源坐标现取（行号会漂，符号名不会；逐条命令 → 读数）

```
rg -n 'STREAM_PIECE_MIN_CHARS' app/agents/nodes.py
rg -n 'failure_text|no_answer_produced' app/api/v1/chat.py
rg -n '^def event_count_gt_1|^def char_by_char_no_loss|^def judge_row|^def summarize|^def read_rows|^class LedgerSchemaError|^REQUIRED_KEYS' scripts/r239_stream_gap_offline_audit.py
rg -n '^def piece_size_gate|^def rows_by_id|^def _tool_calls_of|^def frames_recount|^def witness_conflict|^NODES_SOURCE' scripts/r518_a2_lane_attribution.py
rg -n '^def _sha12|BLANK_SENTINEL =|APPROVAL_FAILED_SENTINEL =|"answer_sha"' scripts/eval_transport_ask_v2.py
```
现取坐标（10-02，本席亲取）：

| 事实 | 文件:行 | 符号 | 读数 |
| --- | --- | --- | --- |
| 尺寸闸 | `app/agents/nodes.py:433` | `STREAM_PIECE_MIN_CHARS` | `= 20`（本件不落这枚数，经 `r518.piece_size_gate` 现取） |
| 预制句真源 | `app/api/v1/chat.py:2937` | `failure_text` | `"本轮未产出任何结论，请重试或补充数据范围。"`（2938 `_save_message` 入历史、2940 `sse_event("error", …)` 发成 content；2950 `"error_code": "no_answer_produced"`） |
| ②-a | `scripts/r239_stream_gap_offline_audit.py:174` | `event_count_gt_1` | `return int(row["text_frames"]) > 1` |
| ②-b | `scripts/r239_stream_gap_offline_audit.py:179` | `char_by_char_no_loss` | 不缺字 ∧ 不多字 ∧ `last_frame_covers_answer`（`breaks_count_as_loss` 开关另算） |
| ② 合取 | `scripts/r239_stream_gap_offline_audit.py:273` | `judge_row` | `verdict = event_ok and char_ok`；同行交回 `ledger_criterion_two_holds`／`disagreement` |
| 合数 | `scripts/r239_stream_gap_offline_audit.py:298` | `summarize` | `criterion_two_holds_literal` / `criterion_two_fails_literal` |
| 读账 | `scripts/r239_stream_gap_offline_audit.py:107`／`:95`／`:80` | `read_rows`／`LedgerSchemaError`／`REQUIRED_KEYS` | 缺键当场抛，不补零 |
| 尺寸闸把手 | `scripts/r518_a2_lane_attribution.py:124` | `piece_size_gate` | 取不到 ⇒ `SizeGateError`（真源路径 `:69 NODES_SOURCE`） |
| 读账/折叠 | `scripts/r518_a2_lane_attribution.py:136` | `rows_by_id` | 同题多轮取最大 `attempt` |
| tool_calls | `scripts/r518_a2_lane_attribution.py:168` | `_tool_calls_of` | sidecar 优先→answers→`None`（🔴 缺不是 0） |
| 证词冲突 | `scripts/r518_a2_lane_attribution.py:223` | `witness_conflict` | 两列不同代 ⇒ 点名 |
| 短指纹口径 | `scripts/eval_transport_ask_v2.py:401` | `_sha12` | `sha256(text.encode("utf-8")).hexdigest()[:12]`；落账在 `:774 "answer_sha": _sha12(answer)` |
| 哨兵两枚 | `scripts/eval_transport_ask_v2.py:205`／`:222` | `BLANK_SENTINEL`／`APPROVAL_FAILED_SENTINEL` | 默认字面 `<no-bytes-emitted>`／`<approval-failed-no-terminal-answer>` |
| 分母口径依据 | `docs/testing/run9-readout-2026-09-28.md` | 「A② 的判据范围 = 全 105 枚」 | 本件当**对账尺**（`DENOMINATOR_IN_BOOK=105`），不当结论 |

## 2. 在册账本先读（⚠️ 手工 rg／PS 口径，**不是本件量具的读数**）

这一节只用来钉死前提形状；分桶与三口径的正式读数见 §5（未跑）。

```
foreach($f in 三本 run9 账, 三本 run11c 账, -p2 帧账){ (Get-Content -LiteralPath $f -ReadCount 0).Count }
rg -o --no-line-number -- '"text_frames": 1[,}]' <帧账> | Measure-Object   # 同法数 tf0 / tool_calls / answer_sha / sentinel
```
- 行数：run9 帧账／sidecar／answers = **105 / 105 / 105**；run11c 三本 = **105 / 105 / 105**；`sidecar-run11c-p2-frames.jsonl` = **12**（半窗样本，留给牙 f）。
- run9（帧账）：`text_frames==1` **9 枚** = doc-07／chat-03／chat-06／chat-09／chat-10／metric-16／data-09／approval-06／scope-01；`text_frames==0` **2 枚** = metric-02／scope-02。
- run9：这 2 枚的 `answer_sha` 都是 **`cea11078566e`**、`answer_chars=21`；answers 书里逐字文本 = `本轮未产出任何结论，请重试或补充数据范围。`（21 字）⇒ 与 §1 现取的 `chat.py:2937 failure_text` 同串。
- run9：`tool_calls==0` **10 枚**（doc-07／chat-03／chat-06／chat-09／chat-10／metric-16／approval-06／scope-01／tool-04／report-02），这 10 枚里 `answer_chars` **最小 69** ⇒ 按 B1 判据 run9 的天然短是 **0 枚**（69 ≥ 尺寸闸 20）。
- run9 同毫秒证词（逐枚现取 `frames[0].arrival_at` vs 终局 `request.completed.arrival_at`）：9 枚单帧题的 `request.completed` 都只有 1 枚；8 枚 delta=0.000 ms（两读都真），**唯 data-09 delta=−0.612 ms** ⇒ `|Δ|<1ms` 为真、`ms 格相等` 为假。这枚就是 §7 里那格敏感性。
- run11c（帧账）：`text_frames==1` **1 枚** = chart-01（delta 0.000，两读皆真）；`tool_calls==0` **27 枚**；`sentinel==true` **4 枚**（insight-07 tf=8／chart-01 tf=1／chart-02 tf=64／chart-04 tf=37），四枚 `answer_sha` 都是 **`96a0fc6fc992`**、`answer_chars=36`；其中 2 枚 `tool_calls==0 ∧ answer_chars=17 < 20` = metric-02／approval-05（两枚 tf=2）。
- 预制串指纹**现取**（只读源件、不读账，经本件自身函数 `chat_prefab_texts`／`harness_sentinel_texts`／`prefab_fingerprints`）：

```
PREFAB cea11078566e no_answer_produced  failure_text               app\api\v1\chat.py            21 字
PREFAB 96a0fc6fc992 collector_sentinel  APPROVAL_FAILED_SENTINEL   scripts\eval_transport_ask_v2.py 36 字
PREFAB ec71005139bd collector_sentinel  BLANK_SENTINEL             scripts\eval_transport_ask_v2.py 18 字
count=3
```
⇒ 派工词点名的 run9 那枚 `cea11078566e` **由源件现算命中**，不是从纸上抄的；账上两枚 `answer_sha` 与之逐字相等（§2 上文）。

## 3. 四桶判据 → 代码出处（本件符号:行 ＋ 上游真源）

量具＝`scripts/r565_a2_denominator_buckets.py`（现取 545 行，纯 CRLF，UTF8 无 BOM，`py_compile rc=0`）。

| 桶 | 判据（照 R506 定性） | 本件出处（符号:行） | 上游真源（符号:行） |
| --- | --- | --- | --- |
| B3 预制句 | `answer_sha ∈ 现取的预制串指纹集合` | `chat_prefab_texts:135`／`harness_sentinel_texts:146`／`prefab_fingerprints:165`／`short_sha:126`／`check_prefab_fingerprints:179`／`bucket_of_row:261` | `chat.py:2937 failure_text`、`eval_transport_ask_v2.py:205/:222` 两枚哨兵、`_sha12:401`（账上落点 `:774`） |
| B2 无逐片腿 | `text_frames == 1` ∧ 那一枚帧与 `request.completed` 同一毫秒到达 | `single_frame_witness:211`（两读并排：`within_one_ms`／`same_ms`，`_arrival_ms:206`）／`bucket_of_row:261` B2 腿 | 帧账的 `frames[]`／`events[]`；`r518.witness_conflict:223` |
| B1 天然短 | `tool_calls == 0`（真值 0，`None` 不算） ∧ `answer_chars < STREAM_PIECE_MIN_CHARS` | `tool_calls_of:253`／`bucket_of_row:261` B1 腿 | `r518._tool_calls_of:168`、`r518.piece_size_gate:124` ← `nodes.py:433` |
| B0 其余 | 上面三格都没命中 ⇒「本轮应当有逐片流」的分母 | `BUCKET_PRIORITY:96`／`bucket_of_row` 归账行／`BUCKET_ORDER:94` | — |

逐枚都带 `also_matched`（命中过的格全留）：优先级 **B3 > B2 > B1 是呈现，不是判据**（run11c 的 chart-01 同时命中 B3 与 B2，正控 `test_b3_wins_the_row_yet_b2_stays_written_down`）。
守恒：`read_round:363` 末尾 `raise CaliberError("四桶不守恒…")`（`:407`），桶计数合计 != 题数就拒绝出数。
② 的判据**一个字都没重写**：`r239.judge_row:273` 直接调用，逐题表里的 `2a/2b/②/led` 四列即 `event_count_gt_1`／`char_by_char_no_loss`／`verdict`／`criterion_two_holds`，`disagreement` 单列。

## 4. 三口径（本席不选口径，三档全交）

出处：`_calibers:316`（三档同时算出）、`declare:411`（拒绝权）、`render:440`（逐题表＋桶计数＋三档数＋七格留痕）、`main:497`（rc 语义）。

- **甲**＝105 全分母，与 `r239.summarize` 现算逐字可比（钉：`test_the_literal_caliber_is_r239s_own_read`）。
- **乙**＝B0 作分母，**且 B1/B2/B3 三格单独报数（枚数＋其中②真／②红＋逐枚题号）**，三格不许蒸发。`discloses_excluded_cells=True`。
- **丙**＝只报 B0、不提三格；`discloses_excluded_cells=False`。🔴 `declare(..., "丙", green=True)` **一律当场拒**（`CaliberError`，消息里点名三格枚数与被腾出的题号）。
- rc 语义：`0` 正常；`2` 分母与在册尺对账不上（打印「[r565][对账不上]」并点名，不静默按小窗出数）；`3` 宣布翻绿被拒。
- 留痕（`_diagnostics:342`，七格点名＋第八格折叠枚数）：`tool_calls_unjoinable`／`single_frame_without_arrival_coordinates`／`ms_reading_sensitivity_rows`／`b0_rows_with_no_text_frame`／`frames_column_conflicts_summary`／`sentinel_rows_outside_prefab_set`／`ledger_vs_literal_disagreements`／`attempts_collapsed`。

## 5. 代跑清单（三批命令原文；🔴 读数一律未取，等总控发「窗已收」）

批① 默认靶 run9（105 枚全表）：
```
& "C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe" -X utf8 "C:\Users\fengx\PycharmProjects\be-r565\scripts\r565_a2_denominator_buckets.py"
```
末行读数：**未跑（等窗）**

批② run11c 另一窗（换三本账指到 run11c，含哨兵串与天然短同时在场）：
```
& "C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe" -X utf8 "C:\Users\fengx\PycharmProjects\be-r565\scripts\r565_a2_denominator_buckets.py" --frames "C:\Users\fengx\PycharmProjects\be-r565\docs\perf\raw\run11c-2026-10-01\sidecar-run11c-frames.jsonl" --sidecar "C:\Users\fengx\PycharmProjects\be-r565\docs\perf\raw\run11c-2026-10-01\sidecar-run11c.jsonl" --answers "C:\Users\fengx\PycharmProjects\be-r565\docs\perf\raw\run11c-2026-10-01\answers-run11c.jsonl"
```
末行读数：**未跑（等窗）**

批③ 本单同名钉（串行、`-o addopts=`、零 `-n`）：
```
& "C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe" -X utf8 -m pytest "C:\Users\fengx\PycharmProjects\be-r565\tests\test_r565_a2_denominator_buckets.py" -o addopts= -p no:cacheprovider
```
末行读数：**未跑（等窗）**

批④ run12 收窗后另跑（半窗期禁止；`--expect-denominator 0` 才能量不足 105 枚的窗）：
```
& "...\python.exe" -X utf8 "...\scripts\r565_a2_denominator_buckets.py" --frames "C:\Users\fengx\AppData\Local\Temp\evalrun\run12-sidecar-frames.jsonl" --sidecar "C:\Users\fengx\AppData\Local\Temp\evalrun\run12-sidecar.jsonl" --answers "C:\Users\fengx\AppData\Local\Temp\evalrun\run12-answers.jsonl" --expect-denominator 0
```
末行读数：**未跑（等窗，且 answers 书尚未落盘）**

### 手工先读推得的**预测**（🔴 未由量具确认，不许当读数用）

- run9：B3=2（metric-02／scope-02）、B2=9（含 data-09，取 `within_one_ms` 读法）、B1=0、B0=94；`also_matched` 另记 B2=9／B3=2／B1=0。
- run11c：B3=4、B2=0（chart-01 被 B3 抢走归账，`also_matched` B2=1）、B1=2（metric-02／approval-05）、B0=99。
- 甲口径的绿数＝`r239.summarize` 现算值（本件不落数字；派工词所引「②真=94／②红=11」本席**未独立现算**，只核到 run9 有 11 枚 `text_frames<=1`，而 ②-a 就是 `text_frames>1`）。

## 6. 反证牙清单（10 枚，在册 `counter_evidence` 命名；一枚都不分层出门）

| 牙 | 钉名（`tests/test_r565_a2_denominator_buckets.py`） | victim | 摘刀形状 | 期望 |
| --- | --- | --- | --- | --- |
| a | `test_counter_evidence_a_blinding_the_prefab_set_folds_the_canned_rows_into_b0:275` | 本件 B3 腿 | 把预制集合指到一枚不含 `failure_text` 的影子源 | 那两枚占位串被并进 B0（分母被偷大）⇒ 红 |
| a2 | `test_counter_evidence_a2_a_source_without_the_canned_literal_is_refused:293` | `chat_prefab_texts:135` | 影子真源里删掉那枚字面 | `PrefabSourceError` 当场抛，不是少归几枚 |
| b | `test_counter_evidence_b_the_size_gate_is_read_live_not_copied:304` | B1 腿的尺寸闸 | `--nodes-source` 指到 1000000 那档影子真源；另一路删掉那行 | 前者 `hit==zero`（B1 枚数随真源动）；后者 `SizeGateError` |
| c | `test_counter_evidence_c_fingerprint_drift_is_refused_not_dropped:321` | `check_prefab_fingerprints:179` | 账上文本与现取串不等 | `FingerprintDriftError` 拒出数 |
| d | `test_counter_evidence_d_the_millisecond_half_of_b2_is_load_bearing:338` | `single_frame_witness:211` 的 ms 那一半 | 把 `request.completed` 推后 50 ms | 该题不再进 B2 ⇒ 落 B0 ⇒ 红 |
| e | `test_counter_evidence_e_a_missing_tool_calls_is_not_treated_as_zero:363` | `tool_calls_of:253` | sidecar **与** answers 两本都删 `tool_calls` | 不许当成 0：不进 B1，且被 `tool_calls_unjoinable` 点名 |
| f | `test_counter_evidence_f_a_smaller_window_does_not_slip_past_the_denominator:384` | `main:497` 对账格 | 拿 12 枚的 `-p2` 半窗账本跑 | rc=2 ＋「对账不上」，不静默按小窗出数 |
| g | `test_counter_evidence_g_this_file_carries_no_downgrade_marker:393` | 钉文件自己 | 扫 skip／skipif／xfail／only | 一枚降级记号都不许有 |
| h | `test_counter_evidence_h_the_instrument_never_writes_its_inputs:401` | 只读纪律 | `io.open` 记账＋三本账 sha256 前后 | 无写模式；sha256 逐枚全等 |
| ＋ | `test_b3_prefab_rows_are_never_folded_into_b0:204`／`test_buckets_are_exclusive_and_conserve_the_whole_window:130`／`test_caliber_c_denies_itself_the_green_claim:156` | 派工点名的三格正判据 | — | 四桶互斥且并集恰为整窗；B3 不并 B0；丙口径宣布翻绿当场拒 |

摘刀一律走**仓外影子件**（pytest 的 `tmp_path`）：在册三本账与 `app/**`／`scripts/**` 真源一字节都不写——这件事由牙 h 自证（`io.open` 记账＋三本账 sha256 跑前跑后逐枚全等）。每把牙在同一枚 test 内成对交「正控读数＋摘刀后 victim 红」（例：牙 d 的 `tests/test_r565_a2_denominator_buckets.py:360` 正控断言、牙 b 的 `:314` 枚数比对、牙 a 的 `:280` 摘前 B3 非空），所以没有「复原」这一步要做——盘上本来就没动过。跑测读数：**未跑（等窗）**。

## 7. 已知残留与欠账（本单不治，写明不藏）

1. **B2 的毫秒口径有两读**：`|Δ|<1ms`（`within_one_ms`）与 `ms 格相等`（`same_ms`）并存，逐题并排交回，本件不替总控定哪一读为准。run9 唯一切分歧是 **data-09**（Δ=−0.612 ms）：按 `within_one_ms` 它进 B2、按 `same_ms` 它进 B0——而它 ② 必红（tf=1），所以**这一枚决定了「换小分母会不会把一枚真红藏进 B0」**。替代分桶本件不重算，只点名题号。
2. **B3 > B2 > B1 是呈现顺序**，不是第三条判据；改它改的是归账表，不是 ② 的读数。多命中全部留在 `also_matched` 里。
3. **prefab 集合按源件默认字面取**：`BLANK_SENTINEL`／`APPROVAL_FAILED_SENTINEL` 走 `os.getenv(...)` 的默认值；若某轮采集器设了环境变量覆盖，账上串会与源件默认不等 ⇒ `check_prefab_fingerprints` 会 `FingerprintDriftError` 拒出数，而不是静默少归。这一格今天没有实测反例，属**已知未验**。
4. **多次 `request.completed` 取终局那一枚**（`max(arrival_at)`）：run9/run11c 每枚单帧题都只有 1 枚 completed，这条分支今天没被走到（`completed_events` 逐题落纸）。
5. **`--expect-denominator` 默认 105**：半窗／缺题的窗要显式给 0 才出数，否则 rc=2。run12 收窗前是 41 行，属此形。
6. **`text_frames==0` 的两枚**在 run9 同时是 B3；若哪天出现「tf==0 且不是预制句」的题，它会进 B0 并由 `b0_rows_with_no_text_frame` 点名（今天 run9 该格=0，因为两枚都被 B3 接走）。
7. 本件**不改 ② 判据、不改缺省值、不并树**；A② 该按哪一口径对外说，归总控裁。

## 8. 本班自纠（三处，落盘为据）

1. 牙 g 的降级记号表里原有一枚 `"pytest.mark." + "parametrize" u".略"`——拼出来是 `pytest.mark.parametrize.略`，**永不命中**，是上一班遗留的装饰。已换成真的 `"pytest.mark." + "skipif"`（拼接写法是为躲自匹配），钉头注释同步写 `skip / skipif / xfail / only`。
2. `test_caliber_c_denies_itself_the_green_claim` 原本把两枚**未验的经验预测**写成永久断言（`cell_c["red"] == 0` 与 `甲红 == 105 − 丙分母`）。已改成结构恒等：②-a=`text_frames>1` ⇒ 一切 `tf<=1` 必红；`甲红 == 丙红 + 三格红`（分桶守恒的直接推论）；`三格红 > 0`。R496 那类「并树即自毁」的形状不在这儿重演。
3. 头注释与 `:75` 原把纸上的 `②真=94／②红=11` 抄进代码，与「不许抄任何纸上的数」相冲——已撤下，改为「甲口径与 `r239.summarize` 现算逐字可比」。另外修了 `_diagnostics`/`render` 里「六格留痕」与实际七格点名的文案不符，并给两枚新件补了行尾换行（原缺，会在 diff 里留 `\ No newline at end of file`）。

## 9. 哪几格没做到（照实写）

- **四桶枚数与甲乙丙三个数：未跑**（run12 窗在开，判据第 2 条的交付读数全部欠着；命令原文见 §5）。
- **`npx`／pytest 一枚都没起**，`py_compile`＋`--help`＋静态 rg／PS 读是本班全部执行过的动作。
- 判据第 2 条要求的「105 行逐题表实际输出形态」未经机器确认，只确认了代码形状与 run9 题数=105（§2）。
- §5 批④ 依赖 run12 的 answers 书落盘；本纸写完时它还不存在。
