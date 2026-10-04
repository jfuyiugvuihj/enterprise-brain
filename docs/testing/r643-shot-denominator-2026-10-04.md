# R643 —— R51 判据②凭据件的分母折叠缺陷：逐发改造账（2026-10-04）

工单：R643＝R51 判据②「端到端与分段加总误差 <1%」凭据件的分母折叠缺陷。
写域：`scripts/r631_stage_sum_delta.py`（改）＋ `tests/test_r643_shot_denominator.py`（新）＋ 本纸（新）。
独占工作树 `be-r643`，基点 `02ee2e6`；主树只读；零容器／零连库／零模型／零打 Ollama；
原料只用盘上三本（只读，未重导、未补数）：`%TEMP%\evalrun\run18`／`run19`／`run20k` 的
`-traces.jsonl` ＋ `-sidecar.jsonl` ＋ `-sidecar-frames.jsonl`；未起全量门（`scripts/run_gate.py` 是禁区）。
🔴 两条判据线（`<1%`、`<0.03%`）一字未改：判据线仍由 `read_criterion_pct()` 现读跟进单第 522 行（LF），
对齐线仍由 `read_alignment_pct()` 现读 `docs/perf/latency-budget-2026-09-16.md` 那一格。

## 0. 三句话结论

- 病是真的，但**折叠的形状不是「两发平均」**：旧口径 `scripts/r631_stage_sum_delta.py::read_sidecar`
  是「attempt 最大；并列取**后一行**」。run20k 的 `doc-04` 两发（`attempt` 都是 1）折成一枚分母 27,490.9 ms，
  另一发 27,244.6 ms 整个掉在账外，差 246.3 ms＝最小一发的 **0.904%**——与 `<1%` 线同一数量级。
- 改后：分母升到**发级**（一发一行账、点名第几发），三窗**母集枚数一枚没变**（105／105／106，
  `no_denominator` 20／19／19 照旧逐枚点名），run18／run19 读数逐位不变，run20k 只有一枚分母被纠正——
  **没有任何一题的 FAIL／PASS 归属翻转**：两条线在真窗上仍是彻底 FAIL（过线枚数 0）。
- 🔴 连带发现（不在本单写域，需新单承接）：`scripts/r636_stage_coverage.py` 自己也在按题号折叠分母
  （它只读取那本旧视图 `read_sidecar` 再自行 remap），⇒ 并树后它对 run20k 交回 `rc=1` 的 MISMATCH。
  这不是 R631 算错，是**那把尺撞见了同源的另一枚病**。

## 1. 病形（10-04 本席现取，非声明）

| 项 | 读数 | 怎么取的 |
|---|---|---|
| run20k sidecar 行数／题号枚数 | 106 行／105 枚题号（`doc-04` 两行） | `read_sidecar` 的 `rows_read` 与 `values` 枚数，现跑 |
| 两发各自跨度与 `attempt` | 27,244.6 ms（`ts 10:02:43`，attempt 1）／27,490.9 ms（`ts 10:03:03`，attempt 1） | 只读打开 `-sidecar.jsonl` 逐行 |
| 两发各自 trace | `trace-a95ea9e4…`／`trace-1e1e2cf5…`（各 27 事件） | 事件载荷 `session_id` ↔ 帧账行（`payload.session_id` 那枚在册桥） |
| 旧口径落账的分母 | 两枚 trace 都写 27,490.9 ms | 改前现跑（`--json` 的 `rows[].end_to_end_ms`） |
| 掉在账外的那发 | 27,244.6 ms，一枚都没有 | 改前 `rows` 里 `doc-04` 两枚的分母逐枚相等 |
| 差值与判据线的比 | 246.3 ms＝0.904%＝`<1%` 线的 0.904 倍 | 改后量具现取（`shot_leg.spreads`） |

⇒ 判据②原来的分母是「这道题平均多久」，不是「这一发多久」。这不是美化读数，是判据本身不成立。

## 2. 改的是什么（结构层，不碰阈值）

新增「发级」一层（`scripts/r631_stage_sum_delta.py`，全内容派生）：

- `read_sidecar_shots`／`read_frames_shots`：采集器一行＝一发，不折叠、不平均、不「取最后一行」。
- `trace_sessions_from_events`：`trace_id` → 它自己的 `session_id`（一枚 trace 带两枚 session 也点名）。
- `attribute_shots`：把每一发连到它自己的那枚（或那几枚）`trace`。身份优先级——
  ① 帧账行自带 `session_id`；② `(题号, ts)` 桥到帧账行的 `session_id`；③ `--join` 清单交来的
  `session_id`／`ts`；④ **该题只有这一发**才按题号连（旧口径，只在枚数＝1 时无从折叠）。
  拿不到身份 ⇒ 记 `unattributed` 并逐枚点名；两发抢同一枚 trace ⇒ 一起退回未归属；
  `ts` 撞行（同一 `(题号, ts)` 多行）⇒ 不挑一枚装作看见。绝不折、绝不借、绝不丢。
- `identity_verdict`：任何一发落不到它自己的 trace，或 `--fold-legacy` 在跑 ⇒ 追加一枚「不可信」签名，
  走在册 `RC_UNTRUSTED`（**没新增退出码**，`EXIT_CODE_MEANING` 仍是 0..5）。
- `build_rows` 多发一枚可选入参 `shots_by_trace`；`RequestRow` 多四个字段
  `shot_index`／`shot_count`／`shot_label`／`e2e_identity`；印面表格多一列「发」，
  同题多发印成 `doc-04 发1/2`｜`发2/2`。
- `--fold-legacy`：把旧病形原样复现（分母退回按题号折叠），供反证刀咬；开着就当场判不可信并点名。
- 顺手补一枚在册空转：`render` 在「不可信且零行」时会去摆空表（`quantiles` 为 `None` 当场炸）——
  这条形状在旧口径下走不到，发级身份全丢时可达；已按数据而非状态字面分支（`not data["rows"]`）。
- 旧视图 `read_sidecar`／`read_frames` **原样留着**：它们是「改前」对照，也是 R636 此刻在读的接口。

身份与行位、与文件此刻 sha 无关（R638 那把棘轮的同族病）：`shot_index` 由内容排序（`ts`→`attempt`→跨度→`session`）派生，
牙 `test_shot_identities_do_not_depend_on_row_order` 把三本原料整体倒序重写，逐发账与逐题账必须逐枚相等。

## 3. 改前／改后对照表（三窗全量逐枚 diff，不是手挑）

取法：同一本原料各跑两遍——逐发（默认）与折叠（`--fold-legacy`＝改前口径复现），逐枚比 `rows[].end_to_end_ms`。

| 窗 | 受影响题号 | 改前分母（折叠） | 改后分母（逐发） | 改前判定 `<1%` | 改后判定 `<1%` | 母集 rows／skipped |
|---|---|---|---|---|---|---|
| run18 | 无（0 枚） | — | — | — | — | 105／20 两态逐枚相等 |
| run19 | 无（0 枚） | — | — | — | — | 105／19 两态逐枚相等 |
| run20k | `doc-04 发1/2`（`trace-a95ea9e4…`） | 27,490.9 ms（借了另一发的数） | 27,244.6 ms（它自己的） | FAIL（误差 31.4064%） | FAIL（误差 30.7863%） | 106／19 两态逐枚相等 |
| run20k | `doc-04 发2/2`（`trace-1e1e2cf5…`） | 27,490.9 ms | 27,490.9 ms（恰好是它自己那发被取中的值） | FAIL（27.9616%） | FAIL（27.9616%） | 同上 |

- 🔴 **归属翻转枚数＝0**：三窗 `failing_1pct` 枚数改前改后都是 105／105／106（一题没翻绿），
  `<0.03%` 那条线同样全 FAIL。所以这单**不会**把 G-R51-1 那一格推向绿——它只把「量错了」这件事治好。
- 误差分布只动了被纠正的那一枚：run20k `p50` 31.4064% → **31.0382%**（`p95` 73.6662%／`p99` 82.8806%／
  最大 97.505%／均值 31.1% 未动）；run18／run19 全部逐位未动（`p50` 32.9612%／29.7976%，与 R631 纸 §11 账面相等）。
- 折叠在真窗上没翻判据，不代表它无害：合成端同一本原料，折叠把一枚 1.4851% 的 FAIL 折成 0.5% 的 PASS
  （牙 `test_knife_five_folding_can_flip_a_fail_into_a_pass`）——旧口径连「会不会翻车」都不保证。
- §11 那三行账面（p50 等）归总控改，本席不动 `docs/perf/**`。

## 4. 母集对账：与 `scripts/r636_stage_coverage.py` 逐窗解释得通

| 窗 | R631（改后）rows／skipped | R636 asked／no_denominator／resumed_head／bare（母集 trace） | 采集器行数＝发枚数 | 分母落到的 trace 枚数 | 逐窗说法 |
|---|---|---|---|---|---|
| run18 | 105／20 | 105／20／19／0（144） | 105 | 124 | 105 发＋19 枚「一发摊在两 trace（同工同 session 的头＋工作腿）」＝124；那 19 枚正是 R636 的 `resumed_head` |
| run19 | 105／19 | 105／19／19／0（143） | 105 | 124 | 同上，逐枚相等 |
| run20k | 106／19 | 106／19／19／0（144） | 106 | 125 | 106 发（`doc-04` 两发各一枚）＋19 枚＝125；没有一把说 105、另一把说 104 |

- `no_denominator` 那一族照旧**逐枚明账**（20／19／19，枚枚带 `trace_id`），一枚没从母集摘掉——
  R631 纸 §7 第③条纪律（缓存命中不发 `request.started`）在发级口径下原样成立。
- 量具互查：发枚数（105／105／106）＝采集器行数，`attributed`＝发枚数，`unattributed`＝0——
  三窗没有一发需要靠折叠或借用出数；身份构成三窗全是 `sidecar_ts_to_frames_session`（106／105／105 枚）。
- 🔴 **对不上的那一格，写得清清楚楚**：R636 对 run20k 现在 `rc=1`，MISMATCH 恰 2 处，
  全在 `doc-04` 同一枚 trace 的 `end_to_end_ms`（它 27,490.9／R631 27,244.6）与 `error_pct`（31.4064／30.7863）；
  run18／run19 的 R636 仍 `rc=0`。⇒ 需新单让覆盖面那把尺改用发级读数（`read_sidecar_shots` ＋ `attribute_shots`），
  本席无权动它（写域禁区）。牙 `test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator`
  钉的就是「分歧只允许出现在同题多发的分母上、母集枚数照旧相等」——它修好后这枚牙仍成立（不会反过来锁死旧病）。

## 5. 牙与反证（`tests/test_r643_shot_denominator.py`：25 个函数 / 29 枚实例，两态全绿）

口径：19 枚跑在 `tmp_path` 影子原料上（全合成，**零真数当钉**），10 枚跑盘上三本真料（`%TEMP%\evalrun` 缺件即 `skipif`，不假装绿）。
派工点名的四把刀全在，另加第五把「折叠会不会翻判据」。

**正控（先证尺子在健康原料上不报警，才配谈反证）**
- `test_two_shots_of_one_question_get_two_denominators` —— 同题两发各得一枚分母（合成 1,010／1,000 ms），两行账都在位。
- `test_the_ledger_names_which_shot_each_row_is` —— 账上点名它是第几发（`shot_index`／`shot_count`／`shot_label`）。
- `test_no_denominator_is_the_average_of_the_two_shots` —— 平均／借用／丢弃三条路一起堵死：两枚分母逐枚等于采集器落的那两行数。
- `test_the_frames_leg_is_also_counted_per_shot` —— 分段腿同样逐发计，不共享一题的分母。
- `test_exit_code_contract_is_unchanged` —— 本单不新增退出码：折叠病走在册「不可信」那一格（rc=4）。

**刀① 抹掉某一发的身份 ⇒ 尺必须红并点名**
- `test_knife_one_erasing_a_shots_identity_turns_the_ruler_red` —— 正控是两发各有 `ts` 桥；抹掉第一发的 `ts` ⇒ 它不得再借兄弟发的数，尺当场红。
- `test_knife_one_fold_legacy_reproduces_the_disease_and_goes_red` —— `--fold-legacy` 退回题号折叠 ⇒ 同一本原料当场判不可信并逐枚点名。
- `test_knife_one_manifest_bridged_shots_beat_the_missing_frames` —— 没有帧账时 `--join` 清单交来的 `ts` 是唯一的桥：各发仍各算各的。
- `test_knife_one_manifest_without_shot_identity_refuses_to_fold` —— 清单只交题号而原料有两发 ⇒ 一枚都认不出来：不许折，只许点名。

**刀② 从原料删一枚 trace 行 ⇒ 母集必须掉一枚并被抓住**
- `test_knife_two_deleting_a_trace_row_names_the_orphan_shot` —— 删掉一发对端的 trace 行 ⇒ 那一发落 `unattributed` 并被点名，母集当场少一枚，不许静默通过。
- `test_knife_two_orphan_question_row_is_named_not_dropped` —— 单发同理：题号在 trace 侧一枚都连不上 ⇒ 记未归属，不许从母集悄悄摘掉。

**刀③ 手改阈值线 ⇒ 在册牙必须红**
- `test_knife_three_the_one_percent_line_governs_the_shot_rows` —— 承重证明：同一本原料，线留在 1.0% 是 FAIL、手抬到 5.0% 才绿 ⇒ 线不是装饰。
- `test_knife_three_hand_moving_the_paper_to_five_percent_is_refused` —— 把跟进单那一行手抄成 `<5%` 的影子纸：现读读到 5.0，但本件拒绝自取口径。

**刀④ 两发故意造成相同 ms ⇒ 不许被折成一发（折叠病最像「没病」的形态）**
- `test_knife_four_two_shots_with_identical_ms_are_not_folded` —— 跨度逐位相等时旧口径折起来不留痕迹；新账照样交两行。
- `test_knife_four_identical_content_shots_refuse_to_pick_one` —— 内容逐位相同（同 `ts` 同 ms）＝真分不清哪发对哪枚 trace ⇒ 两发一起退未归属，不挑一枚装作看见。
- `test_attribute_shots_never_overwrite_one_another` —— 两发抢同一枚 trace ⇒ 一起退 `unattributed`：折叠与借用都不许发生。

**加刀⑤ 折叠到底会不会翻判据**
- `test_knife_five_folding_can_flip_a_fail_into_a_pass` —— 同一本合成原料，旧口径把一枚 1.4851% 的 FAIL 借来 1,000 ms 分母后当场变成 0.5% 的 PASS。

**与 R638 同族病（身份不得含行位／不得含文件此刻 sha）**
- `test_shot_identities_do_not_depend_on_row_order` —— 三本原料的行序整个倒过来写，逐发账与逐题账必须逐枚相等。
- `test_the_folded_view_would_have_lost_one_shot` —— 把在册旧视图（R636 仍在读它那本）的病留档作正证：两行折成一枚题号级分母，另一行整个不在值里。

**真窗组（10 枚实例，原料只读）**
- `test_real_window_attributes_every_shot_on_the_books[run18-105-20 / run19-105-19 / run20k-106-19]` —— 三窗 `attributed`＝发枚数、`unattributed`＝0、`no_positive_span`＝0。
- `test_real_run20k_doc04_shots_are_each_measured_against_their_own_span` —— `doc-04 发1/2`→27,244.6 ms（误差 30.7863%）、`发2/2`→27,490.9 ms（27.9616%），各判各的（本席交回前又现跑一遍逐字复现）。
- `test_real_single_shot_windows_are_byte_for_byte_unchanged[run18-32.9612 / run19-29.7976]` —— 没有同题多发的两窗逐位不变（改动不外溢）。
- `test_real_no_denominator_family_is_still_named_item_by_item` —— 20／19／19 枚 `no_denominator` 仍逐枚带 `trace_id` 明账，一枚没从母集摘掉。
- `test_real_universe_reconciles_with_the_coverage_ledger[run18 / run19]` —— 母集与 R636 对同一本原料的读数逐窗对账（§4 那张表）。
- `test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator` —— 分歧只允许出现在同题多发的分母上，母集枚数照旧相等。

## 6. 两态亲跑（同数已达成）＋ 🔴 连带账

| 件 | state①（本树 apply 未 commit） | state②（`02ee2e6` 干净检出＋只投本单货） |
|---|---|---|
| `tests/test_r643_shot_denominator.py` | 29 passed | 29 passed |
| `tests/test_r631_stage_sum_delta.py` | 37 passed | 37 passed |
| `tests/test_r51_stage_latency.py` | 43 passed | 43 passed |
| 三件合跑（同名件） | **109 passed** | **109 passed** |

- state② 的投货只有两件，尺寸与本树逐字节相同：`scripts/r631_stage_sum_delta.py` 80,296 B、`tests/test_r643_shot_denominator.py` 30,866 B；解包目录 `%TEMP%\r643\state2`。
- 两态合跑用的都是本树 venv 的解释器（`-p no:randomly`），R56／R134 两枚闸门在两次跑里都记 0 次越界、0 枚告警。

🔴 **连带账（必须交给总控，不由本单修）**
- `tests/test_r636_stage_coverage.py`：**纯基点**（`git archive 02ee2e6` 解 `%TEMP%\r643\state0`，不含本单货）＝ **31 passed**；投本单货后两态同为 **5 failed／26 passed**（31 枚总数不变）。
- 5 枚红的报错**逐字相同，且只有这一条**：`与 R631 现跑读数对不上 2 处` ⇒ `doc-04`／`trace-a95ea9e4…` 的 `end_to_end_ms`（r636 27,490.9／R631 27,244.6）与 `error_pct`（31.4064／30.7863）。名头逐枚：
  `test_real_window_ledger_matches_r631_row_by_row[run20k-106-19]`、
  `test_real_window_every_missing_stage_is_type_named_and_evidenced[run20k]`、
  `test_real_window_approved_resume_is_the_paired_orphan_lane[run20k]`、
  `test_real_windows_do_not_silently_drop_the_unpaired_orphan`、
  `test_real_window_direct_lane_is_disjoint_from_sibling_traces[run20k]`。
- 归因（现取，不是推断）：这 5 枚红**不是副作用**——r636 的 `read_inputs` 自取题号级折叠视图再比对；母集／`no_denominator`／`resumed_head` 三格全对得上，否则报错会是别的键、别的数。
- ⇒ **本单不可单独并树**：并了就有 5 枚在册牙红。出路两条，由总控定序——① 与本单的后续单（让 r636 改吃 `read_sidecar_shots` ＋ `attribute_shots`）**同批并树**；② 或先并后续单再并本单。`scripts/r636_stage_coverage.py` 及其牙在本单写域禁区，本席无权动。

## 7. 未验／边界（做不到的一律写「未验」，不用「应该」凑数）

- 🔴 **判据② 没有因为这单而翻绿**：三窗改前改后都是 `status=measured`、`rc=1`，`<1%` 与 `<0.03%` 两条线**全 FAIL、过线枚数 0**，
  归属翻转枚数 0。挡在 G-R51-1 前面的是**分段账覆盖面**，不是分母——这单只把「量错了」治好。
- **客户尺寸下同题多发的比例：未验**。三本料里只有 1 枚题号有两发（`doc-04`），样本一枚；246.3 ms＝0.904% 这个数**不外推**成客户机上的普遍量级。
- **run20k `p50` 31.4064% → 31.0382% 只是被纠正的那一枚样本在动**，不可读成「误差变小了」；`p95`／`p99`／最大／均值逐位未动。
- **`--join` 交发级身份那条路只在合成上证过**：真三窗靠 `(题号, ts) → 帧账 session` 桥（身份构成 106／105／105 枚全 `sidecar_ts_to_frames_session`）。现网导出器能否稳定供给发级 `session_id` 的清单形状：**未验**（本单禁区不许重导原料）。
- **`no_denominator` 那一族的归因未动**：仍按 R631 纸 §7 第③条（缓存命中不发 `request.started`）逐枚明账；本单只保证它不被摘掉、不被折。
- **一发摊两 trace 的那 19 枚**（R636 的 `resumed_head`）沿用在册「同工同 session 的头＋工作腿」口径，本单不改它的配对规则；它与折叠病的边界只由 §4 那张表解释。
- **覆盖面那把尺（r636）改发级读数＝待新单**，本席写域禁区（见 §6 连带账）。
- **全量门未跑**：`scripts/run_gate.py` 是本单禁区，且本机此刻另有席位在跑。两态只跑了 §6 那三枚同名件 ＋ r636 的牙作连带取证。
- 三本原料之外的窗（run20 系列其它名）**未跑**——盘上只有 `run18`／`run19`／`run20k` 三本，缺什么如实记缺。

## 8. 命令原文（本席亲手跑过，逐字抄）

```powershell
$py = "C:\Users\fengx\PycharmProjects\be-r643\.venv\Scripts\python.exe"
$root = "C:\Users\fengx\PycharmProjects\be-r643"
$d = "$env:TEMP\evalrun"          # 只读原料：run18/run19/run20k 的 -traces / -sidecar / -sidecar-frames

# 改后（默认＝逐发）三窗
& $py "$root\scripts\r631_stage_sum_delta.py" --window run18  --dir $d        # rc=1
& $py "$root\scripts\r631_stage_sum_delta.py" --window run19  --dir $d        # rc=1
& $py "$root\scripts\r631_stage_sum_delta.py" --window run20k --dir $d        # rc=1
& $py "$root\scripts\r631_stage_sum_delta.py" --window run20k --dir $d --json # rows=106 skipped=19，doc-04 两发各一行

# 折叠复现（＝改前口径的告示面）
& $py "$root\scripts\r631_stage_sum_delta.py" --window run18  --dir $d --fold-legacy   # rc=4
& $py "$root\scripts\r631_stage_sum_delta.py" --window run19  --dir $d --fold-legacy   # rc=4
& $py "$root\scripts\r631_stage_sum_delta.py" --window run20k --dir $d --fold-legacy   # rc=4

# 改前（纯基点原码现跑，留档 %TEMP%\r643\before0_<w>.md）
New-Item -ItemType Directory -Force -Path "$env:TEMP\r643\state0" | Out-Null
git -C $root archive 02ee2e6 | tar -x -C "$env:TEMP\r643\state0"
foreach ($w in "run18","run19","run20k") { & $py "$env:TEMP\r643\state0\scripts\r631_stage_sum_delta.py" --window $w --dir $d }   # 三窗均 rc=1

# 覆盖面那把尺（只读）
& $py "$root\scripts\r636_stage_coverage.py" --window run20k --dir $d         # rc=1，MISMATCH 2 处
foreach ($w in "run18","run19") { & $py "$root\scripts\r636_stage_coverage.py" --window $w --dir $d }   # rc=0

# 同名件：state①（apply 未 commit）
Push-Location $root
& $py -m pytest -p no:randomly -q tests\test_r643_shot_denominator.py tests\test_r631_stage_sum_delta.py tests\test_r51_stage_latency.py
& $py -m pytest -p no:randomly -q tests\test_r636_stage_coverage.py           # 5 failed / 26 passed
Pop-Location

# state②：干净检出 + 只投本单货
New-Item -ItemType Directory -Force -Path "$env:TEMP\r643\state2" | Out-Null
git -C $root archive 02ee2e6 | tar -x -C "$env:TEMP\r643\state2"
Copy-Item "$root\scripts\r631_stage_sum_delta.py" "$env:TEMP\r643\state2\scripts\r631_stage_sum_delta.py"
Copy-Item "$root\tests\test_r643_shot_denominator.py" "$env:TEMP\r643\state2\tests\test_r643_shot_denominator.py"
Push-Location "$env:TEMP\r643\state2"
& $py -m pytest -p no:randomly -q tests\test_r643_shot_denominator.py tests\test_r631_stage_sum_delta.py tests\test_r51_stage_latency.py
& $py -m pytest -p no:randomly -q tests\test_r636_stage_coverage.py           # 5 failed / 26 passed
Pop-Location

# 纯基点上的连带账基准（证明那 5 枚红是本单货带来的，不是在册旧病）
Push-Location "$env:TEMP\r643\state0"
& $py -m pytest -p no:randomly -q tests\test_r636_stage_coverage.py           # 31 passed
Pop-Location

# 改前/改后逐枚 diff 表（§3 那张表的生成器；产物落 %TEMP%\r643\diff_table.txt）
& $py "$env:TEMP\r643\diff_table.py" $root
```

- 交回前又用**纯基点原码**（`git archive 02ee2e6` 解 `%TEMP%\r643\state0`，不含本单货）现跑 `--window run20k --dir %TEMP%\evalrun --json`：`doc-04` 两枚 trace 的分母**都是 27,490.9 ms**（误差 31.4064%／27.9616%），`p50=31.4064`、`failing_1pct=106` ⇒ §3「改前」那一列是现跑读数，不是转述。
- 同一趟 `diff_table.py` 现跑复核：run18／run19「受影响（分母逐枚不等）枚数＝0」、分位数两态逐位相等；run20k 受影响枚数＝1（`trace-a95ea9e4…`／`doc-04 发1/2`／27,490.9→27,244.6），`spreads` 记 246.3 ms＝最小一发的 0.904%，两态 `failing_1pct` 都是 106 枚 ⇒ 判定归属零翻转。

## 9. 写域与纪律自证 ＋ 收席盘面五枚

**写域（`git status --porcelain` 现读，逐枚点名，一共三件）**
- ` M scripts/r631_stage_sum_delta.py`（改，`+553 / -30`）
- `?? tests/test_r643_shot_denominator.py`（新）
- `?? docs/testing/r643-shot-denominator-2026-10-04.md`（新，本纸）
- 禁区一把没动：`git diff --name-only HEAD` 只列 `scripts/r631_stage_sum_delta.py`；`app/**`／`frontend/**`／`deploy/**`／`.env*`／`docker-compose.yml`／`tests/fixtures/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／`docs/perf/**`／`scripts/r636_stage_coverage.py` 及其牙／`scripts/r633_*`／`r634_*`／`r638_*`／`r642_*`／`scripts/eval_transport_ask_v2.py`／`scripts/run_gate.py`／`pyproject.toml`／锁文件——零字节。
- 主树 `C:\Users\fengx\PycharmProjects\企业智脑` 全程只读。

**环境红线（现读自证）**
- 零容器、零连库、零模型、零重新导出：全程只有 `python scripts/*.py` 与 `pytest`。同名件跑完后 R56「宿主模型端口闸门」记 `blocked connect attempts to host model port: 0`，R134「工作树 Chroma 写回闸门」记 `PersistentClient 调用 … 落点被改道出工作树: 1 次（0 个原路径）`、`工作树 chroma_db 写回告警用例: 0 枚`——盘上 `chroma_db/chroma.sqlite3` 没被写脏（`status --porcelain` 里没有它）。
- 全量门未跑（`scripts/run_gate.py` 是禁区，且本机另有席位在跑）。

**卫生自查（现读）**
- 三件新/改文件：无 BOM、CR＝0、`0x00/07/08/0b/0c` 各 0、无 `???`。
- 手抄坐标：`rg -n "\.py:[0-9]" docs/testing/r643-shot-denominator-2026-10-04.md tests/test_r643_shot_denominator.py` 零命中；`git diff -U0` 里本单**新增**的 r631 行同样零命中（基点那本纸里既有的旧坐标不属本单写域，未动）。
- 身份设计一律**内容派生**（`session_id`／`trace_id`／`(题号, ts)` 桥），与行位无关、与文件此刻 sha 无关——R638 那把棘轮的病没往这单带。

**刀与正控配对（现读测试代码核实，不是转述）**
- 刀①：`test_knife_one_fold_legacy_reproduces_the_disease_and_goes_red` 同一枚牙里先跑 honest 正控（`shot_leg.fold_legacy is False`、rc 不是 4），再证 folded 当场红并点名 `doc-04 发1/2`（`legacy_conflicts[0]`：`shot_wall_ms` 1,010／`used_ms` 1,000／`delta_ms` 带符号）。
- 刀②：`test_knife_two_deleting_a_trace_row_names_the_orphan_shot` 先 `full`（2 枚 trace、rc＝`RC_GATE`）作正控，再删行 ⇒ `trimmed`（1 枚 trace、rc＝`RC_UNTRUSTED`、`unattributed` 恰 1 枚且带 `wall_ms`）。
- 刀③：`test_knife_three_hand_moving_the_paper_to_five_percent_is_refused` 正控＝在册纸现读 `threshold_pct == 1.0`；影子纸改成 5.0 时本件抛 `CaliberError`（「落不进在册刀刃」），**拒绝自取口径**。
- 刀④：`test_knife_four_two_shots_with_identical_ms_are_not_folded` 两发跨度逐位相等（27,490.9）时 `rows_read == shots == 2`、两枚 `shot_label` 都在、`spreads[0].spread_ms == 0.0` 且 `decide_rc` 不判不可信；`test_knife_four_identical_content_shots_refuse_to_pick_one` 证内容全同 ⇒ 两发一起退 `unattributed`。
- 刀⑤：`test_knife_five_folding_can_flip_a_fail_into_a_pass` 同一本合成原料逐发跑是 FAIL（1.4851%）、折叠跑成 PASS（0.5%），前后对照在枚内。

**常驻牙纪律（本周 #96／#107／#113 同族病）**
- 本单 29 枚牙**没有一枚**把「此刻工作树脏不脏／盘上字节等不等于 HEAD」当判据：合成端全在 `tmp_path` 影子原料，真窗组只用 `%TEMP%\evalrun` 只读原料 ＋ 缺件 `skipif`。两态（脏态 / 干净检出）亲跑同为 109 passed，正是这条纪律的读数（见 §6）。

**收席盘面五枚（交回那一刻现取，本席 2026-10-04 21:4x；21:43 复跑同名件仍 109 passed、五枚逐字相同）**

```
$ git -C C:\Users\fengx\PycharmProjects\be-r643 rev-parse --short HEAD
02ee2e6

$ git -C C:\Users\fengx\PycharmProjects\be-r643 status --porcelain
 M scripts/r631_stage_sum_delta.py
?? docs/testing/r643-shot-denominator-2026-10-04.md
?? tests/test_r643_shot_denominator.py

$ git -C C:\Users\fengx\PycharmProjects\be-r643 diff --numstat HEAD
553     30      scripts/r631_stage_sum_delta.py

$ git -C C:\Users\fengx\PycharmProjects\be-r643 ls-files --others --exclude-standard
docs/testing/r643-shot-denominator-2026-10-04.md
tests/test_r643_shot_denominator.py

$ git -C C:\Users\fengx\PycharmProjects\be-r643 rev-list --count 02ee2e6..HEAD
0
```

- 没 commit、没建分支、没 push、没打包；交付货留在盘上（两枚 untracked ＋ 一枚 tracked-modified）。
- `diff --numstat` 那行 git 附带的 `LF will be replaced by CRLF` 是 `core.autocrlf` 对盘上 LF 的提示；本单落盘统一 LF，未碰任何 `.gitattributes`。