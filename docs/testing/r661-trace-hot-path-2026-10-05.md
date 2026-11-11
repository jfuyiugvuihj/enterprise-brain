# R661 · trace 事件件的体量不许站在 SSE 逐片直发的临界路径上（2026-10-05）

**数字口径**：本文全部读数为**执行层自报**——由执行层在同一台机器、同一枚 `.venv`（本树的 `.venv` 是指向主树 venv 的 Junction）现取，总控未复跑。工作树 `C:\Users\fengx\PycharmProjects\be-r661`，基点 `96763c4`，交付时本席零 commit。

**本格定性**：买到的是**一条不再随体量长的曲线**＋一枚站得住的常驻牙；**没有**买到"trace 落盘整条写路径都与体量无关"——结算清扫那一腿今天还在整本读件，见§十三，本纸不把它折成零。

## 一、这单治的是哪一格

病形由总控亲取、本席在自己树里复核：`tests/test_r149_sse_text_pieces.py::test_piece_frames_reach_the_wire_while_the_run_is_still_open` **只在主树红、影子树全绿，两边同一个 sha**。差别只有一件——那本 `data/traces/events.jsonl` 的体量（主树 32,038,850 B／44,143 行，影子树 24,498 B）。

本席的复现（判据②）：在**自己的树里**造同量级事件件 `data/traces/events.jsonl` = **32,039,503 B／31,761 行**（均值 1,008 B/行；真件均值 725 B/行），改前复跑红句原文：

```
片被攒成一坨同时发出：[0.125, 0.5, 0.485]
```

正控与反证同批齐：移走该件 3/3 绿、原样复制回来立刻又红。**未碰主树 `data/traces/**`**，**未**从 `trace-quarantine-20261005` 往主树复制任何东西，**未**把事件件写到仓外别处（落点仍是各树自己的 `data/traces/events.jsonl`，这一点由 §七 那一枚 `test_the_fold_never_touches_the_worktree_journal` 钉住）。

收工现读（10-05 午后）：本树那本件已长到 **32,226,229 B／32,031 行**、干净检出那本 **32,185,862 B／31,973 行**（跑一轮测试就多写几行），两边都稳稳站在 32 MB 这一档之上——判据②的条件在收工那一刻仍然成立，不是开工时成立、收工时早已不成立。主树 `data/traces/` 今天**是空的**：那枚 32,038,850 B 的原物在 `trace-quarantine-20261005` 里（mtime 10:13，总控做「移走／复制回」实验时放的位置），本席没有动过任何一侧。

## 二、那一步在哪：临界路径链与具名符号

不是"每片同步重写全件"，是**每次发片前全量扫件**。链逐枚点名：

1. `app/api/v1/chat.py::_FirstVisibleTextMark.note`——第一枚可见 text 帧即将交出去的那一刻；
2. `app/api/v1/chat.py::_record_wire_first_text`——写侧唯一出口；
3. `app/trace/store.py::TraceStore.record_event`——每枚事件都要过；
4. `app/trace/store.py::TraceStore._next_sequence`——发号；
5. 🔴 `app/trace/store.py::TraceStore._file_sequence_floor`——**病根**。旧实现三行：`self._read_events()` → `_journal_records(tolerant=False)` → 整本 `read_text` 再逐行 `json.loads`，只为回答"这本件替这枚 trace 已经发到几号"。

因为第 3、4 步是**每枚事件**都走，所以单价乘在事件的**计数**上，而计数在长跑里不回退（R257 设计如此：已结算的行留在件里不删）。拟合出的单价 ≈ **15.7 ms 每 MB 每枚事件**（32.04 MB → 501.8 ms）。曲线在四档上都量到了（§三），不是推出来的。

## 三、四档曲线（判据①的原始数）

同一进程、同一形状的事件件，四档 `0 B / 1 MB / 8 MB / 32 MB`。`floor_ms`＝第 5 步那一枚函数取一次号的耗时；`record_event_ms`＝一枚事件走完写路径；`first_text_ms`＝首片可见；`gaps`＝逐片间隔（秒，与 shipped 那一格同一把尺）。

**改前（病形）**

| 档位 | 事件件 B | 行数 | floor_ms | record_event_ms | 首片可见 ms | 逐片间隔 s | min(gaps) | ≥0.4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 B | 0 | 0 | 0.108 | 6.183 | 94 | 0.484 / 0.485 / 0.500 | 0.484 | 绿 |
| 1 MB | 1,000,368 | 993 | 12.503 | 14.713 | 78 | 0.438 / 0.484 / 0.563 | 0.438 | 绿 |
| 8 MB | 8,000,414 | 7,936 | 75.356 | 100.463 | 109 | 0.422 / 0.500 / 0.500 | 0.422 | 绿 |
| 32 MB | 32,039,503 | 31,761 | **501.842** | **549.868** | **360** | **0.187** / 0.485 / 0.500 | **0.187** | 🔴 **红** |

**改后（同一四档、同一形状）**

| 档位 | 事件件 B | 行数 | floor_ms | record_event_ms | 首片可见 ms | 逐片间隔 s | min(gaps) | ≥0.4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 B | 0 | 0 | 0.047 | 4.388 | 94 | 0.422 / 0.500 / 0.562 | 0.422 | 绿 |
| 1 MB | 1,000,368 | 993 | 5.573 | 4.169 | 15 | 0.500 / 0.547 / 0.500 | 0.500 | 绿 |
| 8 MB | 8,000,414 | 7,936 | 5.694 | 5.107 | 47 | 0.500 / 0.500 / 0.468 | 0.468 | 绿 |
| 32 MB | 32,039,503 | 31,761 | **5.763** | **5.824** | 0 | 0.625 / 0.500 / 0.437 | **0.437** | 绿 |

红→绿逐档点名：**0 B 绿→绿、1 MB 绿→绿、8 MB 绿→绿、32 MB 红→绿**。取号那一腿从 501.8 ms 落到 5.763 ms，且 1 MB→32 MB 之间只差 0.19 ms（8.4 倍体量，1.03 倍耗时）——这条线现在是平的。`first_text_ms` 的 0／15 表示首片在同一毫秒内可见，读数按整毫秒取整。

**复测（不信任 conftest 那格改道，另开一档"大 persistence"）**：`floor_ms` 0.040 / 4.731 / 5.134 / **9.420**，`min(gaps)` 0.500 / 0.500 / 0.469 / **0.484** 全绿。32 MB 档 9.42 ms 里剩下的那一截是 JSON 持久化档整档重写（§十三），不是取号。

## 四、修的是什么、没修的是什么

只改一枚文件：`app/trace/store.py`（130 增、3 删，定稿 1,398 行／77,043 B，CRLF）。

- **改**：`_file_sequence_floor` 不再整本读件，改读按字节游标增量折叠出来的 `self._journal_floors`；新增 `_fold_journal_floors`／`_fold_journal_line`／`_journal_size` 三枚 helper 与常量 `JOURNAL_FLOOR_SEED_BYTES = 1 << 20`；`__init__` 多两枚状态（`_journal_floors`／`_journal_floor_cursor`）；模块 docstring 补"第六格主张"。
- **没改**（语义一字不动）：发号规则仍是 `max(pg, file) + 1`；`_next_sequence`／`record_event`／冲突让号那几步的结构没动；读路径的 strict 侧（`_journal_records(tolerant=False)`，坏行照旧抛）没动；`app/api/v1/observability.py::wire_first_text_readout` 与 `WIRE_FIRST_TEXT_EVENT_TYPE` **一字未改**；`app/api/v1/chat.py` **一字未改**（记账那处不需要动，病不在它身上）；`tests/test_r149_sse_text_pieces.py` **一字未改**——`assert min(gaps) >= 0.4` 原样在，没加 sleep、没 skip／xfail。
- 折叠的三条账（都写在 docstring 里）：首眼看一本不超过 1 MiB 的件＝**整本折**，与旧全扫读到的一模一样；首眼看一本更大的件＝只读**末尾 1 MiB 窗口**，落在半个 JSON 上的起手行不猜、跳过；此后每次调用只付**一次 stat ＋ 自上次折叠以来新增的字节**。件在游标下缩过（被轮转或截断）⇒ 从同一枚有界窗口重建映射。

## 五、语义收窄（本件唯一不证的格子，点名不藏）

种子窗口是有界的，所以有一族读数旧实现能给、新实现给不了：**某枚 trace 的行全部落在末尾 1 MiB 之外**、且**这些行不是本进程写下的**、且**六张表整段不可达**——三件同时成立时，`_file_sequence_floor` 会读到 0 而全扫会读到它发过的号，于是这本件可能重复发出同一枚 `(trace_id, sequence)`。`_merge_events` 以 `{trace_id}:{sequence}` 为键，重复的代价是一枚被重放的事件。

边界是**窗口**不是件：只要这枚 trace 近期写过（本进程自己写的行本来就在游标之后）、或六张表可达（R250 之后表是 ledger），这条都够不到。这一格没有拿测试假装证过——`_file_sequence_floor` 把它念出来而不是折成零。

## 六、病阈现读与常驻牙站的那枚 N

同一形状的事件件按枚数扫档，病形与修复后各测一遍（`min(gaps)`，合格线 0.4）：

| 事件枚数 | 件 B | 病形 min(gaps) | 病形判定 | 修复后 min(gaps) |
| --- | --- | --- | --- | --- |
| 4,000 | 4,031,368 | 0.422 | 绿 | 0.500 |
| 8,000 | 8,064,976 | **0.390** | 🔴 红（跨线点） | 0.484 |
| 12,000 | 12,100,920 | 0.375 | 红 | 0.485 |
| 16,000 | 16,136,864 | 0.297 | 红 | 0.500 |
| 24,000 | 24,208,752 | **0.187** | 红（合格线的一半） | 0.485 |

牙站 `R661_JOURNAL_EVENTS = 24_000`。理由：跨线点在 8,000（0.390 已红），但牙不许压在跨线点上——那里红得含糊；24,000 枚时病形掉到 0.187（差线一倍）、修复后同一档读到 0.485，红得没有歧义，且它是**现读到的**、不是拍的。这一枚 N 与跨线点的关系由 `test_every_blade_anchor_hits_exactly_once` 当场钉：`R661_JOURNAL_EVENTS > MEASURED_CROSSING_EVENTS` 且 `MEASURED_CROSSING_EVENTS * 3 <= R661_JOURNAL_EVENTS`；`test_twenty_four_thousand_journal_events_do_not_bunch_the_pieces` 里另有两枚"量的是空气"防呆（行数必须等于 N、字节数必须过 600 B/行）。

## 七、常驻牙名册（`tests/test_r661_trace_journal_hot_path_teeth.py`，定稿 788 行／39,438 B，CRLF；34 枚 cell 全绿）

行为牙（真发片、真计时，合格线与 shipped 同尺）

- `test_twenty_four_thousand_journal_events_do_not_bunch_the_pieces`——24,000 枚事件件之下，逐片直发不许攒成一坨；
- `test_taking_a_number_costs_the_same_at_one_megabyte_and_at_twenty_four`——平性：1 MiB（真件 725 B/行 ⇒ 1,448 枚）与 24,000 枚两档取号耗时之比不许超过 3.0 外加 20 ms。

语义牙（折叠对不对）

- `test_a_fresh_store_continues_the_numbers_the_journal_already_handed_out`——新开的一本必须续上件里已发的号；
- `test_the_floor_folds_a_line_another_writer_appended_after_the_first_look`——别的写者追加的行也要被折叠进来；
- `test_a_line_still_being_written_is_counted_once_it_is_whole`——半行不算、行整了才算，游标不许跨过半行；
- `test_a_receipt_line_hands_out_no_number`——结算收据行不是事件，不许拿它发号；
- `test_a_torn_line_does_not_stop_the_write_path`——坏行拦不住写路径（写侧问的是"我能取几号"，坏行不回答这个问题）；
- `test_the_read_path_still_raises_on_a_torn_line`——读侧照旧抛（静默读短＝说谎），R257 那把 strict／tolerant 的分没搬。

静态闸

- `test_the_number_taking_leg_reaches_no_whole_journal_reader`——沿 AST 从 `_next_sequence` 出发求可达闭包，可达集里不许出现 `_read_events`／`_journal_records`。这一枚不计时，所以机器再快也不至于把它跑绿；
- `test_the_shipped_wire_bar_is_still_the_shipped_bar`——shipped 那道 `assert min(gaps) >= 0.4` 原样在位（本单不许改宽，改宽当场红）；
- `test_the_fold_never_touches_the_worktree_journal`——折叠只碰改道后的落点，仓内那本件一个字节都不许动（路径形状的字面逐枚点名，全件只有一处拿默认账本）。

三道在册闸＋刀

- `test_the_shipped_teeth_are_all_still_here`（名册少一枚即红）／`test_every_blade_anchor_hits_exactly_once`（每把刀的口在源文里唯一命中，且 §六 那两枚 N 关系）／`test_no_tooth_in_this_domain_gates_on_the_checkout_state`（本域牙不许拿"此刻盘面"当判据）；
- `test_the_positive_control_stays_green[K1…K10]`——正控：`edits = ()`，十枚全绿；
- `test_each_knife_reddens_its_named_victim[K1…K10]`——病形：逐把摘刀，victim 逐枚点名（§八）。

## 八、刀账（逐把摘刀 → victim 红句原文；正控 edits=() 十枚全绿）

| 刀 | 摘的是什么 | victim | 病形红句原文 |
| --- | --- | --- | --- |
| K1 | 把 `_file_sequence_floor` 折回"整本读件"旧实现（**回撤形状就是这一把**） | `…do_not_bunch_the_pieces` | `片被攒成一坨同时发出（事件件 20321088 B / 24000 枚）：[0.25, 0.5, 0.484] assert 0.25 >= 0.4` |
| K2 | `JOURNAL_FLOOR_SEED_BYTES` 抬到 `1 << 46`（首眼就把整本读进来） | `…costs_the_same_at_one_megabyte_and_at_twenty_four` | `事件件从 1224432 B 涨到 20321088 B，取号这一步从 8.1 ms 涨到 118.8 ms：它还在随体量长` |
| K3 | 首眼之后再也不读这本件 | `…folds_a_line_another_writer_appended_after_the_first_look` | `另一本写进去的行没被折叠进来：a 又发了一个 2 assert 1 == 3` |
| K4 | 半行也把游标推过去 | `…a_line_still_being_written_is_counted_once_it_is_whole` | `写完的行没被算进来：游标跨过了半行 assert 0 == 77` |
| K5 | 首眼不看已落盘的行（游标直接落到件尾） | `…a_fresh_store_continues_the_numbers_the_journal_already_handed_out` | `新开的一本把这件已经发过的号又发了一遍：[1, 2, 3] assert 1 == 4` |
| K6 | 收据行也拿来发号 | `test_a_receipt_line_hands_out_no_number` | `收据行被当成事件发了号：这一本件从此在数自己的收据 assert 100 == 2` |
| K7 | 写侧遇坏行改抛 | `test_a_torn_line_does_not_stop_the_write_path` | `JSONDecodeError: Invalid control character at: line 1 column 19 (char 18)` |
| K8 | `_journal_records` 的 `tolerant` 缺省翻真 | `test_the_read_path_still_raises_on_a_torn_line` | `Failed: DID NOT RAISE ValueError` |
| K9 | 形状刀，同一把 K1 的编辑喂给 AST 闸 | `…reaches_no_whole_journal_reader` | `取号那条腿够到了整本读件者：['_journal_records', '_read_events']` |
| K10 | 把 shipped 那道线改宽成 0.1 | `…the_shipped_wire_bar_is_still_the_shipped_bar` | `shipped 那道线不在了或被改写了 assert 0 == 1`（对 `assert min(gaps) >= 0.4` 的命中计数） |

每把刀的正控（`edits = ()`）都在同一轮里跑过并绿；刀只落在影子模块（`tmp_path` 里 compile＋exec，`__file__` 指回真仓），**仓内字节一个都没动**。

## 九、回撤形状（判据③点名要的那句话）

把这枚修复改回"同步全件重写"＝**K1**，牙当场红，红句原文见 §八第一行；同一形状喂给静态闸＝**K9**，`取号那条腿够到了整本读件者：['_journal_records', '_read_events']`。两枚一起红、且只有该红的会红，就是这枚牙咬得住病形的凭据。

## 十、两态数字（判据④；全部执行层自报）

跑法三批统一：`-p no:randomly -q --no-header -o addopts= -W ignore`，两态之间串行跑、不并发，免得争 CPU 把计时判据跑成假红。

**state①（apply 未 commit，本树脏态）**／**state②（干净检出复跑：clone 主树 → 分离 HEAD 到 `96763c4` → 只落本席这三枚交付文件 → 造 32 MB 事件件）**

| 批次 | 件数 | state① | state② |
| --- | --- | --- | --- |
| A：`test_r149_sse_text_pieces`（16 cell）＋`test_r661_trace_journal_hot_path_teeth`（34 cell） | 2 | **50 passed**（18.76 s） | **50 passed**（18.82 s） |
| B：trace 家族 12 枚件 | 12 | **96 passed, 9 skipped**（13.26 s） | **96 passed, 9 skipped**（13.02 s） |
| C：相邻 23 枚件 | 23 | **367 passed, 4 skipped**（78.43 s） | **367 passed, 4 skipped**（77.14 s） |

上表是**定稿字节**（CRLF，含删除三枚临时探针之后）在两态各跑一遍的读数；A 批这一轮是 r149 的 16 枚与新牙的 34 枚同跑，分开跑过也是 16 passed／34 passed。三枚交付文件在两态**逐枚同 SHA256**（`app/trace/store.py` 77,043 B、`tests/test_r661_trace_journal_hot_path_teeth.py` 39,438 B，本纸在两态也是同一枚哈希——它自己的字节数不在自己体内报，那枚数每改一字就漂），不是"差不多"。

B 批清单：`test_r250_local_fallback_is_named`／`test_r250_pg_trace_source_of_truth`／`test_r250_trace_column_alignment`／`test_r257_fallback_journal_is_settled`／`test_r257_journal_says_it_is_not_the_ledger`／`test_r263_unproven_sequence_never_borrows_an_id`／`test_r272_live_sequence_race`／`test_trace_persistence`／`test_trace_orchestration`／`test_postgres_execution_persistence`／`test_r649_first_screen_ms_is_measurable_on_the_wire`／`test_r236_trace_store_logger`。

C 批清单：`test_r149_sse_text_pieces`／`test_r661_trace_journal_hot_path_teeth`／`test_sse_sources`／`test_r156_sse_event_surface_sync`／`test_answer_cache_scope`／`test_routing_intent_and_terminal_state`／`test_r203_answer_leg_streams`／`test_r203_no_double_delivery`／`test_r203_sink_reaches_the_leg`／`test_r203_sse_progressive_frames`／`test_r31_generation_stream_passthrough`／`test_r31_stream_pieces`／`test_r172_lane_across_hitl`／`test_observability_routes`／`test_r146_cached_token_ledger`／`test_agent_result_records`／`test_model_call_spans`／`test_cancellation_epoch`／`test_r294_principal_freeze`／`test_r37_report_lane_enqueue`／`test_r523_cached_count_lands`／`test_r250_run_terminal_status_honesty`／`test_r250_run_readout_permissions`。

**红逐枚同名**：本席在两态都没有红。改前的红只在病形条件下取得，逐枚点名：`test_r149_sse_text_pieces.py::test_piece_frames_reach_the_wire_while_the_run_is_still_open`（3/3 红，红句见 §一）与新牙件的 K1／K2／K9（§八）。

## 十一、判据①—⑤ 逐条回执

- ① 四档曲线原始数（每档 `min(gaps)` 与首片可见 ms）已交，红→绿逐档点名——见 §三，含大 persistence 复测档。
- ② `tests/test_r149_sse_text_pieces.py` 在本席自己树里 32,039,503 B 事件件条件下复跑全绿（16 passed），合格线一字未改（`assert min(gaps) >= 0.4` 原样，并由 `test_the_shipped_wire_bar_is_still_the_shipped_bar` 钉住），无 sleep、无 skip／xfail。
- ③ 常驻牙 34 枚 cell 全绿；十把刀逐枚红得点名、正控 `edits = ()` 十枚先绿；回撤形状写进 §九。
- ④ 两态数字见 §十，同名件同数、清单逐枚点名、执行层自报。
- ⑤ **未治**，点名见 §十二。

## 十二、判据⑤（R656 · `TRACE_STORE_PATH` 改道）差哪一格

缺的是 `tests/conftest.py` 里一枚 session 级夹具：`setenv("TRACE_STORE_PATH", <tmp>)` ＋ `reset_default_trace_store()`（`tests/conftest.py:22-26` 今天只把 `PERSISTENCE_FALLBACK_PATH` 改道，trace 事件件没改）。本席写域是"新增测试件"，`conftest.py` 不在里面，所以**没动它**，也**没有**为了让测试变绿把事件件写到仓外别处。代价照实说：各树的 `data/traces/events.jsonl` 会继续长（本树已被本单造到 32 MB 当证据），而 §二那条腿一旦随体量长，这枚病就在每一轮长跑里回来。

## 十三、留给下一格

1. **结算清扫那一腿还在整本读件**：`backfill_fallback_journal` 每次都 `_journal_records(tolerant=True)` 全扫（现读 24,211,196 B／24,004 行 → **351.4 ms**），且永远从第 1 行起重扫 `events[:2000]`；`maybe_backfill_fallback_journal` 也在 `record_event` 入口被调用。⇒ 生产形态（PostgreSQL 在位且欠账开着）里首枚事件与每次 armed 清扫仍会 stall。本单没动它——R257 的牙压在这条腿上，动它要先重锚那一族。
2. **`JsonPersistenceAdapter.upsert` 整档读＋fsync 重写**：现读 908,302 B 档 **41.4 ms/行**。`PERSISTENCE_BACKEND=json`（dev／笔记本形态）下每枚事件要付数行这个价；测试路径上因 conftest 把落点改道到 tmp 沙盒而只剩 4—8 ms，所以本单没被它挡住。属 `app/storage/persistence.py`，在 R661 写域外。
3. **判据⑤**（§十二）：`tests/conftest.py` 的 `TRACE_STORE_PATH` 改道。
4. **读路径**（`replay`／`read_run`／`_local_only_gap`）仍整本读件：那是管理面读数、不在客户等答案的临界路径上，本单没动，但别把它当已治。
