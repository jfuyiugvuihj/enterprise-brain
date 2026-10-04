# R649 · 把「首屏 X ms」从"只有口径"做成"线上量得到"（2026-10-04）

**本格定性**：这一格买到的是**能量**——线上现在有一枚可由账本派生的首屏读数；**没有**买到"好数"。
`app/api/v1/observability.py` 里那一枚 `first_text_p95_ms` 槽位照旧回答不可测、照旧没有 p50／p95、
target 照旧待乙半按三件凭据写。计划书 R48 那一行的判据①（给客户报档位那一格）不在本单半径内，
本单不替它宣布任何东西，也不改它的措辞——账面理由句由总控落，本单只交逐字建议。

## 一、这单的账从哪一格起步

R48 在 V1 内只交三样。前样（线索卡本体）与次样（卡片未获补齐那张失败脸）都已在树；
第三样"一个量得到首屏毫秒的线上口径"今天之前**只有口径没有数**，凭据就是它自己那两枚 blocker——
其中一枚的原文写着 `app/api/v1/chat.py::canonical_sse_event` 给 canonical 信封盖了戳却
**nothing persists them**，所以从 wire 侧算出来的任何一枚数都只是 proxy。本单治的就是这一格。

## 二、记录点为什么站在"发了屏"那一侧

`app/api/v1/chat.py::_FirstVisibleTextMark` 的 `note` 只在**帧即将交出去**的那一刻调用，
三处调用点逐枚点名，且每一处都紧跟在一枚 `app/api/v1/chat.py::text_sse_frame` 的 yield 之前
（这一条由 `tests/test_r649_first_screen_ms_is_measurable_on_the_wire.py::frame_yield_record_points`
沿 AST 现读，不靠叙述）：

- 逐片道 `app/api/v1/chat.py::_AnswerPieceStream.frame_for` 之后：交不回帧而 `continue` 的那一片
  屏上一个像素都没变，不记账；
- 收尾道 `ask` 里那一枚整段正文：没有逐片的一轮，它就是屏上第一行；
- 批准道 `app/api/v1/chat.py::_ApprovedAnswerStream.decide` 判 `skip` 之后：被闸门拦下的那份字
  没上屏，不记账。

🔴 token 与帧在流式里不等价，混了就是假读数。模型侧第一个 token 有它自己的账
（`app/trace/spans.py::ExecutionSpan.mark_first_token` 落的是 `model_calls.first_token_at` 那一列），
它与本单这一格谁也不许顶谁——blocker `first_token_not_a_stage_sample` 说的正是那一族，本单留着它。

闸门状态住在 per-round 对象里，**不落盘、不进帧账**：`prefix_breaks` 与 `per_stream` 那两本在册账
一列都没多（R642 刚把 A② 甲案落在内存态，本单不给它添格子）。

## 三、账为什么是"已在册的那本"，不是第三本

写侧只有一枚出口：`app/api/v1/chat.py::_record_wire_first_text` 走
`app/trace/store.py::TraceStore.record_event`，事件名由观测面那一侧署名
（`app/api/v1/observability.py::WIRE_FIRST_TEXT_EVENT_TYPE`，写侧迟 import，不抄第二份）。
`sequence` 与 `timestamp` 两枚戳都由那本账自己盖——本单不带第二枚时钟。
读侧 `app/api/v1/observability.py::wire_first_text_from_events` 只做一件事：把
`request.started` 与最早那一枚可见 text 帧的两枚已在册的戳交给
`app/common/stage_timing.py::to_epoch_ms` 相减，与那本账算端到端同一枚换算、同一个分母
（`app/common/stage_timing.py::request_windows_from_events`），所以首屏与端到端不可能各说一套。

三条取值纪律逐条拦假读数：一个 trace 只认最早那一枚；帧必须排在起点之后（续跑轮会再记一枚
`request.started`，每个起点重新开一窗）；算不出就是 `None`，不折成 `0`。

读回形状：`GET` 那枚按 trace 折叠的阶段报告只多一格 `first_text`，三态分开署名——
`measured` / `no_wire_first_text_event` / `wire_first_text_without_request_window`。
键名册与"帧名一枚没多、载荷闭集一字未动"两格都由测试件逐枚点名，本文件不抄第二份清单。

## 四、命中道为什么故意不记

`app/api/v1/chat.py::ask` 里 `cached_response` 那一腿没有 canonical 事件、也不该有 run 行。
每一枚 trace 事件都会刷新 `agent_runs` 那一行（`app/trace/projections.py` 的投影每事件都写），
为命中腿补一枚 wire 事件等于给一轮压根没跑过的编排造证据。这一格的缺席继续由
blocker `cache_hits_are_not_traced` 说着，读回来的那一面是具名的
`wire_first_text_without_request_window`（窗口没开），不是 shortage of samples。

## 五、blocker 账：摘了哪一枚、凭据是什么、哪两枚仍挡着

- **摘**：`wire_first_text_not_recorded`。摘之前先交现跑凭据——一轮真发帧的流（离线
  `httpx.MockTransport` 假腿，零打模型）落进账里那一枚 `wire.first_text`，读回的
  `first_text_ms` 非 `None`、且落在 `request.started` 与帧真正交出去那一刻之间，
  读数等于两枚戳之差本身。凭据面见
  `tests/test_r649_first_screen_ms_is_measurable_on_the_wire.py::test_the_positive_control_reads_a_non_none_first_screen_off_a_real_frame`。
- **留着**：`lane_attribution_absent`——它要的是"stage 样本与 request 事件都说不出这一轮被判进了
  哪一档"，本单既不裁归因、也不许用一枚旁路事件把它糊过去；`first_token_not_a_stage_sample`——
  第一个 token 依然不是一枚 stage 样本，那一族由 `app/common/stage_timing.py` 的词表自己说。
- **不空绿**：`tests/test_r649_counter_evidence_teeth.py::first_text_bookkeeping_problems`
  把"blocker 摘了而账里无数"与"账里有数而 blocker 还挂着"两形都判成红，正控是真驱动一轮后交回空清单。

槽位那一格今天仍走 `app/api/v1/observability.py::_slo_not_measurable`：`slo_readout` 的读数面没被
本单改动，在册那枚"没有量具的槽位仍回答没有一个数"的钉照旧绿。

## 六、`prerequisite` 与契约 §4b 为什么这单不动它

`app/api/v1/observability.py::SLO_METRIC_CALIBER` 里首屏那一格的 `prerequisite` 散文仍提
`wire_first_text_not_recorded`，**这不是遗漏**：`tests/test_r526_slot_caliber_closure.py` 的
`check_doc_agreement` 把契约 §4b 那一行与这一枚字段**逐字对判**，只改码面不改契约会当场红，
而 `docs/api/contract-v1.md` 在本单禁区里。同理，契约 §6 那枚列着它的格子也要与码面同批处置。
⇒ 需要总控把"契约 §4b 那一格 + §6 那一格 + `prerequisite` 新串"落在一批里，本单已在交付里给出逐字建议。

## 七、反证三把（常驻牙）

每把进门先跑正控，红必须红在读数上并点名到那一枚；刀与绿测共用同一把尺
（`visible_frame_problems` 与 `frame_yield_record_points`），刀这边不另造判据。

| 刀 | 变异／输入 | 红的读数 |
|---|---|---|
| A | 把 piece 腿的记账点搬到折帧闸之前、按 token 记 | 结构面点名那一枚 `note(..., leg='token')`；读回点名"记账的腿不是发了屏那一族" |
| B | 采集器那本帧账的一行（`scripts/eval_transport_ask_v2.py::_first_screen_reading` 的 `first_visible_ms`）冒充线上；再给它贴上 trace_id 与事件名；再往真事件塞假 `first_text_ms`；再喂模型侧 `model.finished` + `first_token_at` | 派生一律交回空／`no_wire_first_text_event`，`first_text_ms` 恒 `None`；真事件上的假数字顶不掉由戳派生的那一枚 |
| C | 掐掉记账出口而 blocker 已摘；以及账里有数却仍挂着 blocker | 分别点名"空绿"与"过期账" |

刀 A 的姿势要记清：变异只落影子副本（`tests/_temp_edit_overlay.py` 的在册骨架），活模块上只临时
改绑派生点名的那一枚顶层绑定、出门按对象身份装回，并核对活的 router 上端点枚数与盘上字节未变。
本件因此**不走** `r466.install_mutation` 那一腿——装变异到活模块的那一族由
`tests/test_r466_mutation_does_not_leak_into_live_module.py` 的在册名册逐枚点名，名册与派生清单
（`tests/test_r583_window_inventory.py`）互为牙齿，而名册住在别人的写域里。按那一件自己的派生口径，
本件落在"只开窗、不装变异"那一族，不进名册，也不会静默失踪。

## 八、帧账差分与两态复跑

判据④ 要的不是叙述：点名 `tests/test_r642_a2_stream_level_exemption.py`／
`tests/test_r642_post_approval_terminal_readback.py` 与
`tests/test_r215_recognizing_a_controlled_correction.py`／
`tests/test_r215_recomputing_run6_frames.py` 两族，加上 transport 那一族在册件，
按**同一份清单**在两种盘面各跑一遍——本席树上（已 apply 未 commit）与
`git archive` 解出的干净检出＋只投本单货——同名件逐枚枚数相等、整批 exit 零。
改前基线取干净检出的原样（不含本单货）同一份清单。具体读数随本单交付回报总控，本文件不落枚数，
免得下一次并树就把这页纸变成假话。

## 九、这格之后还欠什么

- 归因：`lane_attribution_absent` 没被本单动过，按档读首屏仍要 `app/agents/nodes.py::classify_route`
  那一侧的样本与 request 事件接得上；
- 分布：要出 p50／p95，得先有 `MIN_SLO_SAMPLES` 那一枚下限点名的真样本量，且数值必本机；
- 安静机器：热集让路延迟那一格仍欠一台不被别席争用的机器重量。
本单把"量得到"这一格填平，仅此一格。