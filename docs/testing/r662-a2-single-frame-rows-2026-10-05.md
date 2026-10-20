# R662 · A②「流式逐字无缺字」四枚红题：单帧行改分片（2026-10-05）

工单：R662 ｜ 基点：`1af37c5`（R661 并树那一枚，开工现取 `git rev-parse --short HEAD` 与投单词对账一致）
工作树：`C:\Users\fengx\.codex\worktrees\r662-a2-stream-pieces\企业智脑`（本席现建，起点干净＝基点）
代次：病形读数出自 run22 帧账（`run22.window.json` 现记 revision `955651345d9995811de5a8fe14b93544b8c42eee`、
`index_backend=pgvector`），总控 10-05 亲跑；本席一律**离线复演**，零模型、零端口、零容器。

> 🔴 本纸所有「执行层自报」＝本席读数，不是总控亲跑。所有帧账读数都用**在册那一把尺**：
> `scripts/eval_transport_ask_v2.py::frame_verdict`（七枚合取）与
> `scripts/r573_caliber_reconciliation.py`（在册三口径），不自造分母、不改夹具、不改判分器。

## 1. 病形（改前读数，逐题点名）

在册合取口径的分子：`criterion_two_holds=True` **102/105**；红的三枚逐题点名（run22 帧账现取）：

| 题号 | kind | text_frames | max_stream_frames | per_stream | missing | extra | 末帧覆盖 | answer_chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `chart-01` | approved_ok | 2 | **1** | [1, 1] | 0 | 0 | 真 | 31 |
| `data-12` | ok | **1** | **1** | [1] | 0 | 0 | 真 | 2858 |
| `tool-04` | approved_ok | 2 | **1** | [1, 1] | 0 | 0 | 真 | 170 |

- 三枚**都不缺字、不多字、末帧覆盖终答、零坏形**：红的只有「不许一坨」那一格。
- 判据② 原文两格口径（`text 事件数 >1` ∧ `逐字比对无缺字`）：**104/105**，那一枚红的就是 `data-12`。
- 第四枚红 `chart-04` 只在 33 题子集窗炸（`run22s1`／`run22s2` 各 **29/33**，红号四枚相同：
  `data-12`／`chart-01`／`chart-04`／`tool-04`）；run22 全表窗同一题 **64 帧全绿** ⇒ 与窗口形状相关。
  🔴 这一枚本单**没修也不归本单**，见 §9。
- 在册量具自己早就把这两行记成证词不一致：`diagnostics.ledger_vs_literal_disagreements`
  现取＝`["chart-01", "tool-04"]`。

## 2. 根因分档（按 r565 在册四桶，不新造桶名）

| 形状 | 在册桶 | 根因（发射层那一格） | 本单动作 |
| --- | --- | --- | --- |
| `data-12`（2858 字一坨） | **B2 无逐片腿** | provider 一枚字都没流就坏 ⇒ `app/agents/nodes.py::_OfflineModel.invoke` 把 ``ToolMessage`` 整段回声当离线回复交回；这段字从来没进过出口，收端只能发一枚帧（收端切整段被 `tests/test_r149_sse_text_pieces.py::test_a_whole_answer_with_no_pieces_still_issues_exactly_one_text_frame` 与 `test_one_oversized_piece_is_never_split_by_the_receiver` 钉死，只能改在生产者侧） | 改（§3 甲） |
| `chart-01`／`tool-04`（批准流各 1 帧） | B0，逐片腿在跑 | 批准续跑那一发**片确实生成了**（日志 `[R203] leg=chart … pieces=2`），但 `app/api/v1/chat.py::_ApprovedAnswerStream.decide` 规则 2 把「与屏上那份不同源的非收尾整段」当第二枚终答流整批 held。屏上此刻挂的只是 37 字挂起说明（`chat.hitl_park_text`），本轮还没有任何终答上过屏 ⇒ 拦下的其实是**第一枚**终答流 | 改（§3 乙） |
| `chart-04`（子集窗） | 采集器那一侧 | 批准腿 `kind=approval_failed`＋`sentinel=True`：采集器把终答换成 36 字哨兵 `<approval-failed-no-terminal-answer>`，而屏上 63 帧交回的是 1258 字 ⇒ `missing_chars=1258`／`extra_chars=36`／末帧不覆盖。发射层在这一行今天就是绿的（63 帧、零坏形） | 🔴 **不动**（禁区，§9） |

名单与准入一字未放宽：`app/agents/nodes.py::ANSWER_LEG_STREAM_WORKERS` 仍旧只有
`doc`／`data`／`chart` 三枚（钉在 `tests/test_r203_sink_reaches_the_leg.py`、
`tests/test_r459_supervisor_answer_leg_streams.py`、`tests/test_r524_sink_reaches_both_runways.py`），
尺寸闸三把尺（`STREAM_PIECE_MIN_CHARS`／`STREAM_PIECE_MERGE_SECONDS`／
`STREAM_PIECE_STALL_FLOOR_CHARS`）由 `tests/test_r524_sink_reaches_both_runways.py::RULERS`
钉着，本单现读仍旧 20／0.1／4。

## 3. 改了什么（坐标一律 `文件::符号`）

### 甲 · 生产者侧：成形答复按在册尺寸闸补成逐片

`app/agents/nodes.py`

- 新增 `publish_formed_answer_pieces`：准入走 `answer_leg_stream_target`（名单＋注册出口，
  一格不放宽），切片步长＝`StreamPieceMerger.min_chars`（现读 20，不写死数字），片交给
  同一枚 `publish_stream_pieces` 盖章（`call_id`／`worker`），攒不出第二枚就**一枚都不发**（交回 0）。
  同文两发要分得开，所以 `call_id` 由调用方沿用、缺省现铸。
- 新增 `publish_formed_reply_for_call`：闸门判「这一发有没有字到过」，认的是
  `_AnswerPieceTap.arrived_chars`，不是 `_AnswerPieceTap.published`（取舍理由见下面「一处踩线纠正」）。
- `app/agents/nodes.py::_ResilientModel.invoke` 三处出口接入：预算耗尽那一支、provider 抛错走
  离线回复那一支、正常返回但 `tap.close()` 交回 0 片且未放弃那一支（后者记一行
  `[R662] leg=… pieces=` 日志）。
- `_AnswerPieceTap` 多一枚实例计数 `arrived_chars`（只加读数，不改任何一片的文字与时间戳）。

### 乙 · 收端闸门：屏上只挂挂起说明时，逐片帧一帧一帧上屏

`app/api/v1/chat.py`

- `_ApprovedAnswerStream.decide` 多一枚形参 `opening`，只在新分支「屏上此刻挂的**只是**那句挂起
  说明」时生效：头一枚逐片帧带 R210 那对 `CORRECTION_STEP_TOOL` step 出门整段替换（与规则 3
  同一格，只是走在头一枚片上），此后各片按规则「延续」顺着发；收尾那一枚仍旧比字，同屏不发第二遍。
  规则 1／2／3 本体一字未改，`held` 那本账照旧大声报（`[R464] 批准腿拦下 …`）。
- `approve` 里 `screen_at_open` 现取一次，`screen_holds_notice = is_hitl_park_notice(screen_at_open)`
  ——按 `chat.hitl_park_text` 现构造再逐字比，不抄字面；只把这一枚判定透传给 `kind == "piece"`
  那一支，`terminal` 那三处调用点的形状一格未变（`opening` 只出现一次，钉在
  `tests/test_r662_approved_leg_park_notice_streams.py::test_the_piece_branch_is_the_only_caller_that_passes_the_opening_flag`）。

### 一处踩线纠正（写进交付，不藏）

补片的准入最初按 `published` 判。`_AnswerPieceTap` 的 T2 天生压着最新那枚片等下一枚来证明
「还在写字」，provider 死在半路时 `abandon()` 会把手里那枚整片丢弃 ⇒ 「已经流过半截真话」的
一发 `published` 读数可以是 **0**。按它放行会把 R210 那族「半截真话＋离线话术」的纠正替换
改发成一串成形片——当场打红在册的 `tests/test_r210_frame_ledger_of_a_broken_round.py`
（三枚 `[2] [3] [4]` 参数）。判据改成「到过闸门的字数」（`arrived_chars`）之后复绿，并补一枚
常驻钉 `tests/test_r662_formed_answer_streams_progressively.py::test_a_half_streamed_round_that_delivered_no_pieces_still_publishes_nothing`。

### 另一处踩线纠正（卫生）

两枚被改的文件最初被命令通道写成了纯 `LF`，而本机 `core.autocrlf=true`（检出＝CRLF）。
四枚在册反证件按**原始字节**在 `chat.py` 里找锚（`\r\n` 字面），于是当场红了三枚
（`tests/test_r48_headline_never_enters_the_text_ledger.py::test_d1_…`、
`tests/test_r649_counter_evidence_teeth.py::test_counter_evidence_a_…`、
`tests/test_r156_sse_event_surface_sync.py::test_counter_evidence_losing_the_always_present_row_field_turns_red`）。
两态复跑之前已把两枚文件恢复成 CRLF；这一格记在这里，是因为它证明「锚点件读的是字节，不是语义」。
## 4. 四枚红题：改前读数 → 改后读数（同一把在册尺，影子复演）

改后读数怎么来的：本单不许打真模型，也不许改测量条件。做法是**影子复演**——把两枚新用例
里过真发射件（真 `_ResilientModel`／真 `StreamPieceMerger`／真收端闸门）交回的 SSE 字节，
喂进在册量具那几件真函数（`scripts/eval_transport_ask_v2.py::_consume`／`_fold_frames`／
`_frame_readings`／`_arrival_readings`／`_cross_stream_repeats`／`_record_frames`），
落成一枚与 run22 逐列同形的帧账行；再把这枚行替换回 run22 那 105 行里对应的三行，
其余 102 行原样不动，交给 `scripts/r573_caliber_reconciliation.py` 读数。
字节由这枚常驻件在开关下落下：
`tests/test_r662_formed_answer_streams_progressively.py::test_record_the_shadow_wire_of_the_offline_fallback_round`
与 `tests/test_r662_approved_leg_park_notice_streams.py::test_record_the_shadow_wire_of_the_parked_approval_round`
（缺省 skip，与 `tests/test_sse_sources.py::SSE_EVENT_INVENTORY_OUT` 同一分工）。
🔴 **这是复演，不是新窗**：翻绿要总控在真窗复跑；复演件与影子账本都落仓外（`%TEMP%\r662-shadow\`）。

| 题号 | 判据 | 改前（run22 在册行） | 改后（影子复演行） |
| --- | --- | --- | --- |
| `data-12` | ① 不许一坨 | text_frames=1／max_stream_frames=1 | **144／144** |
| | ② 递增不重叠 | 无从判（一坨） | 144 枚片区间两两不重叠，逐帧到达时刻非减 |
| | ③ 逐字比对 | missing=0／extra=0（本来就绿） | missing=0／extra=0，且逐字拼接＝2858 字终答 |
| | ④ 末帧覆盖 | 末帧＝整段（平凡真） | 末帧 2858 字＝终答全文，covers=真 |
| | 合取 | **false** | **true** |
| `chart-01` | ① 不许一坨 | text_frames=2／max_stream_frames=1／per_stream=[1,1] | **3／2／[1,2]**（批准流 2 枚逐片帧） |
| | ② | 屏上只有一坨 | 2 枚片（20＋11 字）区间不重叠，call_id 同一枚 |
| | ③ | 0／0 | 0／0，拼接＝31 字终答 |
| | ④ | covers=真 | covers=真，末帧逐字＝终答 |
| | 合取 | **false** | **true** |
| `tool-04` | ① 不许一坨 | text_frames=2／max_stream_frames=1／per_stream=[1,1] | **10／9／[1,9]** |
| | ②③④ | 同上（只有 ① 红） | 全部成立；uncorrected_breaks=0、cross_stream_repeat_frames=0 |
| | 合取 | **false** | **true** |
| `chart-04` | ① | 子集窗 63 帧（这一格本来就绿） | **不变**：63 帧 |
| | ④ 末帧覆盖 | **假**（missing=1258／extra=36，`kind=approval_failed`＋`sentinel=True`） | **不变（仍旧假）** ⇒ 见 §9 |

🔴 一枚取舍写清楚，别把它读成「本单把 31 字那一族也一并洗绿了」：片数由在册尺寸闸（20 字）
说了算，不由本单挑。`chart-01` 那 31 字要交回 **2** 枚片，前提是 provider 逐 token 吐字
（本件按 4 字一枚打帧）。同一句字若被打包成 18 字一枚（`tests/test_r524_sink_reaches_both_runways.py::_answer_frames`
那枚病历形状），merger 只撞响一枚尺寸闸 ⇒ 屏上仍旧一枚帧。真窗复跑时如果这一行还红，
红的不是闸门，是「这一发的字到没到过尺寸闸第二格」——那要请总控裁定尺寸闸本身，本单不动它。

## 5. 在册口径投影（`scripts/r573_caliber_reconciliation.py`，三口径并列，本席不替总控挑）

| 口径 | 改前（run22 帧账） | 改后（run22＋三行影子复演） |
| --- | --- | --- |
| 四桶（r565） | B0=104／**B2=1**／B1=0／B3=0 | **B0=105／B2=0**／B1=0／B3=0 |
| `text_frames >1` | 104/105 | **105/105** |
| `max_stream_frames >1` | 102/105 | **105/105** |
| `criterion_two_holds`（在册七枚合取） | **102/105＝0.9714**，红号 `chart-01`／`data-12`／`tool-04` | **105/105＝1.0000**，红号无 |
| 甲-1（剔 B1∪B2） | 分母 104/105（扣 1 枚）／分子 102＝0.9808 | 分母 105/105（扣 0 枚）／分子 105＝1.0000 |
| 甲-2（剔 `text_frames==0`） | 105/105／102＝0.9714 | 105/105／105＝1.0000 |
| 丙-算（含 `max_stream_frames>1`） | 102＝0.9714 | 105＝1.0000 |
| 丙-不算（反事实探针） | 104＝0.9905，丙档翻动题号 `chart-01`／`tool-04` | 105＝1.0000，**翻动题号=无** |
| ② 原文两格（②-a∧②-b） | 104/105 | 105/105 |
| 剔报告档 93 枚 | 90/93 | 93/93 |

- 33 题子集窗（`run22s1`／`run22s2`）：改前 29/33，红号四枚；本单能修三枚（`data-12`／
  `chart-01`／`tool-04`），第四枚 `chart-04` 根因在采集器 ⇒ 复演口径下子集窗投影 32/33，
  真窗仍须总控复跑。
- 输入件指纹（改前）：`sha12(frames)=8b024d3f6865`、`sha12(sidecar)=2ecabb6fa8a8`、
  `sha12(answers)=1252531d276c`；影子账本 `sha12(frames)=23913fa06027`（sidecar／answers 原样，
  本单没换）。

## 6. 反证牙（四枚，全落在常驻用例里）

| 刀 | 用例件::用例 | 读数 |
| --- | --- | --- |
| A 摘掉分片本体 | `tests/test_r662_formed_answer_streams_progressively.py::test_knife_a_dropping_the_formed_piece_producer_goes_red_naming_the_row[data-12]` | text_frames=1／max_stream_frames=1、其余六枚合取照旧全绿 ⇒ verdict=false。红的只有判据① 那一格 |
| B 挪出名单（准入） | `tests/test_r662_formed_answer_streams_progressively.py::test_knife_b_the_admission_gate_is_what_makes_the_row_green[data-1／export-1]` | `data` 走片>1、帧>1；`export` 走 0 片、1 帧、verdict=false ⇒ 绿的因落在准入，不落在「调了函数」 |
| C 摘掉 `opening` 那一格 | `tests/test_r662_approved_leg_park_notice_streams.py::test_knife_c_dropping_the_opening_cell_goes_red_naming_the_rows[chart-01／tool-04]` | 回到 run22 那一形：per_stream=[1,1]、text_frames=2、max_stream_frames=1，日志 `[R464] 批准腿拦下 2 枚`／`拦下 9 枚`，verdict=false |
| D 末帧少一个字 | `tests/test_r662_approved_leg_park_notice_streams.py::test_knife_d_a_last_frame_that_misses_the_tail_goes_red_on_the_tail[1／5／40]` | extra_chars=1／5／31、`last_frame_covers_answer=false`、verdict=false，而 text_frames／max_stream_frames 一格不动 ⇒ `chart-04` 那形的判据单独有牙 |

三枚方向钉（把「放宽」钉在原地上，不许它多走一步）：

- `tests/test_r662_approved_leg_park_notice_streams.py::test_the_piece_branch_stays_shut_when_the_screen_already_holds_the_answer`
  —— 屏上挂着**真答复**时批准流仍旧 0 枚帧、无 `[R464]` 误报（护住 run22 那 19 枚 `approved_ok`）；
- `tests/test_r662_formed_answer_streams_progressively.py::test_a_naturally_short_formed_answer_still_issues_exactly_one_frame`
  —— 短过尺寸闸的一枚都不补；同件另钉 `..._publishes_not_a_single_piece`（1／7／19／20 字四档）；
- `tests/test_r662_formed_answer_streams_progressively.py::test_a_half_streamed_round_that_delivered_no_pieces_still_publishes_nothing`
  —— 半截真话那一族仍旧走 R210 的纠正替换，不被洗成一串片。

## 7. 零等待（硬约束的钉法）

`tests/test_r662_formed_answer_streams_progressively.py::test_the_producer_contains_no_wait_of_any_kind`
按 AST 走一遍**调用名**：`sleep`／`*.sleep`／`*.wait`／`Timer`／`Lock.acquire`／`Queue`／`put`／`join`
一枚都不许出现（docstring 里提到 sleep 不算，因为读的是 `ast.Call` 不是文本）。
同件 `..._is_synchronous_so_a_wait_cannot_hide_in_it` 钉这两枚函数非协程、体内无 `await`——
结构上就发不出「等一会儿再发下一片」。片与片之间的间隔只来自发射本身：一片一次 `sink(piece)`
进队列，收端那一枚在册 `await asyncio.sleep(0)` 一格未动。

🔴 `tests/test_r149_sse_text_pieces.py` 的 `assert min(gaps) >= 0.4` 一字未动（该文件不在本单
写域，`git status` 现读无改动）；`app/trace/store.py` 一格未碰。

## 8. 两态数字（执行层自报，同名件清单逐枚相同）

件清单（45 枚，逐枚）：

| `tests` 下的件 | 归属 | 改前（收/红/跳） | state①（收/红/跳） | state②（收/红/跳） |
| --- | --- | --- | --- | --- |
| **合计（45 枚 / 43 枚）** | 本单 + 在册 | 661 / 0 / 12 | **712 / 0 / 15** | **712 / 0 / 15** |
| `test_answer_cache_scope.py` | 在册 | 21 / 0 / 0 | 21 / 0 / 0 | 21 / 0 / 0 |
| `test_approve_canonical_events.py` | 在册 | 57 / 0 / 8 | 57 / 0 / 8 | 57 / 0 / 8 |
| `test_hitl_pending.py` | 在册 | 27 / 0 / 0 | 27 / 0 / 0 | 27 / 0 / 0 |
| `test_r123_hitl_approval.py` | 在册 | 17 / 0 / 0 | 17 / 0 / 0 | 17 / 0 / 0 |
| `test_r149_sse_text_pieces.py` | 在册 | 16 / 0 / 0 | 16 / 0 / 0 | 16 / 0 / 0 |
| `test_r156_sse_event_surface_sync.py` | 在册 | 13 / 0 / 0 | 13 / 0 / 0 | 13 / 0 / 0 |
| `test_r181_text_frame_ruler.py` | 在册 | 21 / 0 / 0 | 21 / 0 / 0 | 21 / 0 / 0 |
| `test_r203_answer_leg_streams.py` | 在册 | 15 / 0 / 0 | 15 / 0 / 0 | 15 / 0 / 0 |
| `test_r203_no_double_delivery.py` | 在册 | 7 / 0 / 0 | 7 / 0 / 0 | 7 / 0 / 0 |
| `test_r203_sink_reaches_the_leg.py` | 在册 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| `test_r203_sse_progressive_frames.py` | 在册 | 16 / 0 / 0 | 16 / 0 / 0 | 16 / 0 / 0 |
| `test_r210_break_replaces_the_screen.py` | 在册 | 8 / 0 / 0 | 8 / 0 / 0 | 8 / 0 / 0 |
| `test_r210_frame_ledger_of_a_broken_round.py` | 在册 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| `test_r215_recognizing_a_controlled_correction.py` | 在册 | 15 / 0 / 0 | 15 / 0 / 0 | 15 / 0 / 0 |
| `test_r215_recomputing_run6_frames.py` | 在册 | 4 / 0 / 0 | 4 / 0 / 0 | 4 / 0 / 0 |
| `test_r218_cache_hit_observability.py` | 在册 | 3 / 0 / 0 | 3 / 0 / 0 | 3 / 0 / 0 |
| `test_r218_egress_gate_placement.py` | 在册 | 4 / 0 / 0 | 4 / 0 / 0 | 4 / 0 / 0 |
| `test_r218_lane_flip_stop_sets.py` | 在册 | 21 / 0 / 0 | 21 / 0 / 0 | 21 / 0 / 0 |
| `test_r218_ruler_self_calibration.py` | 在册 | 9 / 0 / 0 | 9 / 0 / 0 | 9 / 0 / 0 |
| `test_r223_frame_arrival_clock.py` | 在册 | 30 / 0 / 0 | 30 / 0 / 0 | 30 / 0 / 0 |
| `test_r259_awaiting_approval_stops_the_watch.py` | 在册 | 16 / 0 / 0 | 16 / 0 / 0 | 16 / 0 / 0 |
| `test_r259_terminal_readout_lands_in_the_book.py` | 在册 | 21 / 0 / 0 | 21 / 0 / 0 | 21 / 0 / 0 |
| `test_r31_generation_stream_passthrough.py` | 在册 | 13 / 0 / 0 | 13 / 0 / 0 | 13 / 0 / 0 |
| `test_r31_stream_pieces.py` | 在册 | 27 / 0 / 0 | 27 / 0 / 0 | 27 / 0 / 0 |
| `test_r353_degradation_note_caps_reason_classes.py` | 在册 | 26 / 0 / 0 | 26 / 0 / 0 | 26 / 0 / 0 |
| `test_r439_assembly_never_fakes_a_label.py` | 在册 | 8 / 0 / 0 | 8 / 0 / 0 | 8 / 0 / 0 |
| `test_r439_terminal_answer_never_shows_the_marker.py` | 在册 | 11 / 0 / 0 | 11 / 0 / 0 | 11 / 0 / 0 |
| `test_r459_supervisor_answer_leg_streams.py` | 在册 | 18 / 0 / 0 | 18 / 0 / 0 | 18 / 0 / 0 |
| `test_r464_one_terminal_answer_stream_per_round.py` | 在册 | 23 / 0 / 0 | 23 / 0 / 0 | 23 / 0 / 0 |
| `test_r471_second_copy_of_the_answer_body_is_not_a_pass.py` | 在册 | 16 / 0 / 0 | 16 / 0 / 0 | 16 / 0 / 0 |
| `test_r48_headline_card_lands_on_the_wire.py` | 在册 | 20 / 0 / 0 | 20 / 0 / 0 | 20 / 0 / 0 |
| `test_r48_headline_never_enters_the_text_ledger.py` | 在册 | 6 / 0 / 0 | 6 / 0 / 0 | 6 / 0 / 0 |
| `test_r506_a2_ledger_required_keys.py` | 在册 | 17 / 0 / 0 | 17 / 0 / 0 | 17 / 0 / 0 |
| `test_r506_a2_single_frame_not_green.py` | 在册 | 7 / 0 / 0 | 7 / 0 / 0 | 7 / 0 / 0 |
| `test_r518_a2_lane_attribution.py` | 在册 | 22 / 0 / 0 | 22 / 0 / 0 | 22 / 0 / 0 |
| `test_r518_counter_evidence_knives.py` | 在册 | 11 / 0 / 0 | 11 / 0 / 0 | 11 / 0 / 0 |
| `test_r524_queue_lane_sends_no_second_character.py` | 在册 | 9 / 0 / 0 | 9 / 0 / 0 | 9 / 0 / 0 |
| `test_r524_sink_reaches_both_runways.py` | 在册 | 12 / 0 / 0 | 12 / 0 / 0 | 12 / 0 / 0 |
| `test_r635_counter_evidence_teeth.py` | 在册 | 13 / 0 / 0 | 13 / 0 / 0 | 13 / 0 / 0 |
| `test_r635_surface_pointers_are_derived.py` | 在册 | 12 / 0 / 0 | 12 / 0 / 0 | 12 / 0 / 0 |
| `test_r649_counter_evidence_teeth.py` | 在册 | 5 / 0 / 0 | 5 / 0 / 0 | 5 / 0 / 0 |
| `test_r649_first_screen_ms_is_measurable_on_the_wire.py` | 在册 | 14 / 0 / 0 | 14 / 0 / 0 | 14 / 0 / 0 |
| `test_r662_approved_leg_park_notice_streams.py` | 本件新增 | — | 16 / 0 / 2 | 16 / 0 / 2 |
| `test_r662_formed_answer_streams_progressively.py` | 本件新增 | — | 35 / 0 / 1 | 35 / 0 / 1 |
| `test_sse_sources.py` | 在册 | 18 / 0 / 4 | 18 / 0 / 4 | 18 / 0 / 4 |

三态各自是什么（执行层自报，两态复跑用同一枚 `--junit-xml` 逐件计数比对）：

- **改前基线（不含本单货）**：`git archive 1af37c5` 解出的干净检出（现取 1713 枚文件），
  只跑那 43 枚在册件 ⇒ 661 collected／0 红／12 跳（跳的是 `tests/test_approve_canonical_events.py`
  与 `tests/test_sse_sources.py` 那族「不设 env 只收证据」的在册件，与本次改动无关）。
  🔴 检出 emulation：本机 `core.autocrlf=true`，`git archive` 交的是索引里的 `LF` 字节，
  而四枚在册反证件按原始字节找 `\r\n` 锚——解出后按同一规则把文本文件抬成 CRLF，
  否则红在解包工件上而不是红在代码上（§3 末节那一格就是这条的现形）。
- **state①＝本树已 apply 未 commit**：45 枚同名件 ⇒ 712／0／15。
- **state②＝`git archive <基点>` 干净检出＋只投本单货**：投进 5 枚（
  `app/agents/nodes.py`、`app/api/v1/chat.py`、
  `tests/test_r662_formed_answer_streams_progressively.py`、
  `tests/test_r662_approved_leg_park_notice_streams.py`、本纸）⇒ 712／0／15。
- 另跑一枚**贴边回归面**（36 枚件，凡源码里出现 ``_ResilientModel``／``_AnswerPieceTap``／
  ``on_llm_new_token``／``publish_stream_pieces``／``answer_leg_stream_target`` 的在册件，
  含 ``tests/test_r102_stream_slot_release.py``、``tests/test_r204_budget_refusal.py``、
  ``tests/test_r30_context_limit_guard.py``、``tests/test_r548_queue_lane_registers_the_piece_sink.py``、
  ``tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py`` 那族额度／队列道件）：
  现读 **695 passed／2 skipped／0 failed**（执行层自报）。
- 同名件清单逐枚相同、总数相同：按件比对**无一枚漂移**（上表三列逐枚对得上），
  本单新增 51 枚 collected＝两枚新用例件 35 枚＋16 枚，其中三枚复演件缺省 skip（已计入 15 跳）。
- 🔴 交卷那一刻按同一 HEAD 现跑复账（执行层自报）：干净检出 × 43 枚在册件 = **661／0／12**
  （连跑两遍同数）；state① = **712／0／15**；state②（投本单 5 枚货，逐枚 SHA256 与本席树相同）
  = **712／0／15**；`--collect-only -q` 逐枚比对两态 = **零漂移**，两态 collected 总数同为 712。

## 9. 本单没修的与请裁定

1. 🔴 **`chart-04` 的 33 题子集窗那一枚红，本单不动。** 取证：那一行 `kind=approval_failed`、
   `sentinel=True`、`answer_chars=36`——批准腿零帧（`per_stream=[63, 0]`），采集器
   （`scripts/eval_transport_ask_v2.py` 里的 `APPROVAL_FAILED_SENTINEL`）把终答换成 36 字哨兵，
   于是末帧（1258 字）不覆盖终答（36 字）：`missing_chars=1258`／`extra_chars=36`。
   发射层在这一行今天是绿的（63 帧、零坏形）。要翻绿只有两条路，两条都在禁区：改采集器
   （不许改评测夹具与判分器），或让批准腿把同一份字再发一遍（那是 R464／R471 定义的病形）。
    ⇒ 请总控裁：这一行属 A 门那一格，还是属「批准失败」那一格（后者本就不该进 A② 分母）。
2. **尺寸闸那一格（§4 末节）**：答案短到只撞得响一枚尺寸闸时，逐片腿交不回第二枚片。
   本单按在册闸走，不硬切凑多发。真窗若在此红，请裁的是闸门本身，不是分片。
3. **复演≠新窗**：§5 的 105/105 全三行都是影子复演。翻绿要总控在安静机器上复跑真窗，
   并按仓库规约做并树前后两遍（dirty 态＋干净树各跑同名件）。
4. **`app/agents/nodes.py::_ResilientModel.invoke` 的 provider 抛错那一支在 `_offline_fallback`
   之后 return，没走 `slot.release()`**——本单一格未动它（既有形状，与本单无关）。
   若属实是漏放额度，那是另一枚单的事，这里只如实点名。

## 10. 写域、禁区与盘面自证

- 写域内动过：`app/agents/nodes.py`、`app/api/v1/chat.py`、两枚新用例件、本纸。共 5 枚。
- 禁区一格未碰（`git status --porcelain` 现取为证）：`app/trace/store.py`、`app/rag/**`、
  `docs/handoff/**`、`docs/api/contract-v1.md`、`tests/fixtures/business_evaluation_100.jsonl`、
  `tests/test_evaluation_report.py`、`scripts/run_gate.py`、`pyproject.toml`、
  `deploy/.env.server`、`chroma_db/**`、`frontend/**`；零 commit、零分支、零 push、
  零服务、零容器、零镜像、零真模型、零全量门。
- 盘面自证（本席树，收席那一刻现取）：`git status --porcelain` 恰 5 枚 —— `M app/agents/nodes.py`、`M app/api/v1/chat.py`、`?? docs/testing/r662-a2-single-frame-rows-2026-10-05.md`、`?? tests/test_r662_approved_leg_park_notice_streams.py`、`?? tests/test_r662_formed_answer_streams_progressively.py`；`git rev-list --count 1af37c5..HEAD`＝0；`git diff --cached --name-only`＝空。
- 交卷时主树 HEAD 一直在前进（开工现取＝基点 ``1af37c5``；收席那一刻连读两次分别是 ``b0404c7`` 与 ``bbef9ad``）：本席树
  一格未 rebase，并树与两遍复跑（dirty 态＋干净树）归总控；本纸 §8 那三态数全部打在基点
  ``1af37c5`` 上，请按同一 HEAD 互比，别拿别的 HEAD 的枚数当尺。
- 控制字符卫生：本纸与两枚用例件现扫 `0x00`／`0x07`／`0x08`／`0x0b`／`0x0c` 全为 0 枚；
  坐标一律 `文件::符号`，全文不含 `*.py:数字` 那种手抄行号。
- 收席复跑（执行层自报，收席那一刻现取）：干净检出 × 43 枚在册件 = **661 / 0 / 12**（连跑两遍同数）；state① 45 枚 = **712 / 0 / 15**；state② 同名 45 枚 = **712 / 0 / 15**；
  `--collect-only -q` 按件比对 state① 与 state② **零漂移**（45 枚逐枚计数相同、总数 712 相同）。
- 🔴 **主树盘面旁证（非本席货，请总控自辨）**：收席那一刻现读主树 `git status --porcelain`，
  `docs/testing/shape-window-readout-2026-09-28.md` 挂着 `M`，但 `git diff --numstat` 交回**空**——
  现取字节 = 542 枚裸 `LF` / 0 枚 `CRLF`，与索引里的内容逐字相同，只差行尾（本机
  `core.autocrlf=true` 的换行卫生）。本席的测试与脚本全部落在工作树或影子检出目录里
  （§8 那三态数的 pytest 输出路径即为证），主树 `app/` 与 `tests/` 现读干净；主树另有
  `M chroma_db/chroma.sqlite3` 与未跟踪 `.zcodeignore` / `0` / 课程实践目录一枚，同样与本单无关。
