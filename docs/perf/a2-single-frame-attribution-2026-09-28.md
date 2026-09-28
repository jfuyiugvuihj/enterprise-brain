# A② 「整轮只发一片 text」的归因（R456 · 只取证 · 不改产码）

单号 **R456** · 基点 `223fa97` · 工作树 `C:\Users\fengx\PycharmProjects\be-r456` · 2026-09-28
执行层代号 **Faraday**。

本单一行产码没改、一扇窗没开、一次模型没打、一个容器没动。交回物只有：本份报告 ＋ 三枚新钉
（`tests/test_r456_single_frame_shape_is_not_a_pass.py`／
`tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py`／
`tests/test_r456_error_round_is_not_an_answer.py`）。改法另立下一枚，本单不动手（`app/**` 在写域之外）。

## 0. 凭据分层：每一格用的是哪一层的哪个名字

本项目有一条铁规——**零命中不是判据，除非说清在哪一层查的**。所以先把尺子摊在桌上。

| 层 | 名字（文件:行 / 字段） | 本单拿它证明什么 |
|---|---|---|
| 在册产物·帧账 | `docs/testing/sidecar-run9-frames.jsonl` 逐题 28 键：`events`／`frames`／`text_frames`／`max_stream_frames`／`streams`／`per_stream`／`missing_chars`／`extra_chars`／`prefix_breaks`／`corrective_replacements`／`uncorrected_breaks`／`last_frame_covers_answer`／`answer_chars`／`answer_sha`／`first_visible_ms`／`first_visible_event`／`kind`／`criterion_two_holds`／`ts`／`session_id` | 流内形状的唯一事实源（105 行／105 唯一题号） |
| 在册产物·侧车 | `docs/testing/sidecar-run9.jsonl` 的 `wall_ms`／`tool_calls`／`evidence_n`／`kind`／`approved`／`approval_rounds`／`pre_answer_chars` | 收端数到的 `event: step` 枚数（＝`tool_calls`，实现 `scripts/eval_transport_ask_v2.py:340`＋`:1289`），用来判「这一轮到底派没派 worker」 |
| 在册产物·正文 | `docs/testing/answers-run9.jsonl` 的 `answer`／`answer_source`／`evidence`／`latency_ms` | 交回评分器的那一份字节到底是什么 |
| 在册判读件 | `docs/testing/run9-readout-2026-09-28.md`（A2 节 :41-55、两格表 :235-243、族一 :127-135、hitl 格 :115） | 全窗聚合读数与日志族配对；本单**逐格复算并与它等值**（见 §1） |
| 只读源码·后端腿 | `app/api/v1/chat.py` `:2695-2707`（片道）／`:2715-2719`（终答拾取）／`:2757-2788`（具名结局）／`:2792`＋`:2811`（收尾整段帧）；`app/agents/orchestrator.py` `:346`＋`:412`／`:617-618`；`app/agents/nodes.py` `:567-594`／`:875-883`／`:1777-1789`／`:2103-2121` | 一帧是从哪里发出来的、片道为什么可以一个字都不响 |
| 只读源码·收端尺 | `scripts/eval_transport_ask_v2.py` `:394-407` `_count_text_frame`／`:342-355` `_consume` 的 text 支／`:1205-1208` 缓存命中即 raise／`:1227-1228` error→answer 的洗白点；判读函数 `_frame_readings`／`_frame_verdict` | `text_frames` 是**逐帧 += 1**，不折叠、不去重 ⇒ 「一片」只能是后端只 yield 过一次 |
| 新钉（可跑） | `tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py`（15 枚）／`tests/test_r456_single_frame_shape_is_not_a_pass.py`（9 枚）／`tests/test_r456_error_round_is_not_an_answer.py`（6 枚） | §1 的每一格读数、§5 的形状复现、§4 的三腿可分辨 |

🔴 **本单不引用的东西**（写了以免下一班误当成凭据）：`%TEMP%\evalrun\` 里那批一次性脚本（不可钉）、`evaluation-report-run9.json`（只有六个聚合键，无逐题 step 载荷）、任何容器日志原文（本单没动容器，日志族只转述判读件里已落仓的那几行）。

## 1. 读数复算：本单自己现场重算，与在册判读件逐格等值

现场重算脚本落在临时目录（不在仓内），读 `docs/testing/sidecar-run9-frames.jsonl` 105 行；
同一批数另有可跑的钉：`tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py::test_the_ledger_is_one_row_per_question_and_the_three_registered_counts_hold`
与 `::test_criterion_two_recomputes_from_the_rows_own_readings`（后者逐枚用**在册量具自己的** `_frame_readings` ＋ `_frame_verdict` 重算 105 次，与 `criterion_two_holds` 键对账，漂移必须为 0 枚）。

| 格 | 本单现算（全 105） | 在册判读件 | 等值？ |
|---|---|---|---|
| `text_frames > 1` | **94** | `run9-readout-2026-09-28.md:237` 全 105 行＝94 | ✅ |
| `text_frames == 1` | **9** | `:4405`（跟进单 §130）点名九枚 | ✅ 题号逐枚相同 |
| `text_frames == 0` | **2** | `:237` 空读＝2 | ✅ `metric-02`／`scope-02` |
| `missing_chars > 0`（缺字） | **0** | `:237`＋`:241`「两档都是 0 枚」 | ✅ |
| `prefix_breaks > 0` | **7**＝`data-07 metric-04 metric-10 metric-11 report-02 report-03 tool-04` | `:237`＝7 | ✅ |
| `uncorrected_breaks > 0`（真断流） | **2**＝`report-02`／`tool-04` | `:237`＝2 枚同名 | ✅ |
| `criterion_two_holds == True` | **91**（False 14 枚） | `:237`＝91 | ✅ |

九枚单片（帧账字段 `text_frames==1` 的题集合，现算）：
`approval-06`、`chat-03`、`chat-06`、`chat-09`、`chat-10`、`data-09`、`doc-07`、`metric-16`、`scope-01`。

十四枚 `criterion_two_holds==False` ＝ 上面九枚 ＋ `metric-02`／`scope-02`（空读）＋ `chart-01`／`report-02`／`tool-04`（帧数够但另有坏形）。

🔴 **一处必须写清的口径差**（不是错误，是两枚数并存）：判据原文的合取是
`text_frames > 1 AND max_stream_frames > 1 AND uncorrected_breaks == 0 AND missing_chars == 0 AND extra_chars == 0 AND last_frame_covers_answer`
（尺子＝`scripts/eval_transport_ask_v2.py::_frame_verdict`）。所以「事件数那一半不过」的**枚数是 94/105**，而「判据② 成立」的**枚数是 91/105**——差的三枚是 `chart-01`（`max_stream_frames==1`）、`report-02`／`tool-04`（`uncorrected_breaks>0`）。两枚数不是同一件事，详见 §8。

## 2. 判据① 逐枚归因表（九枚单片 ＋ 两枚空读）

「腿」的名字取自源码，不用意译：**一次性成文腿**＝`app/agents/orchestrator.py:346 main_agent_node` 里
`:412 main_model.invoke([sys_msg, current_user_msg])` 那一发（不带 `config`，正文是一次性交回来的）；
**工具后终答腿**＝supervisor 先 `dispatch(...)`、worker 跑完、终答由 `app/agents/nodes.py:2103-2121 synthesize`
从 `worker_results`／消息尾部拾取；**具名结局腿**＝`app/api/v1/chat.py:2757-2788`（`_select_final_answer` 三源皆空）。

| 题号 | (a) 走的哪条腿 | (b) `text_frames` 由谁造成 | (c) 失败码 | 凭据（文件 → 字段名） |
|---|---|---|---|---|
| `doc-07` | 一次性成文腿（无派发） | **后端一次 yield**：收尾 `chat.py:2811` | 无（`kind=ok`） | frames→`text_frames=1`/`streams=1`/`max_stream_frames=1`/`events`（`text` 之后紧邻 `request.completed`）；sidecar→`tool_calls=0`/`evidence_n=0`；answers→`answer`(69 字，起「根据对话历史，这个问题已经回答过了」) |
| `chat-03` | 一次性成文腿 | 同上 | 无 | 同上（`answer_chars=320`，`text_frames=1`，`tool_calls=0`） |
| `chat-06` | 一次性成文腿 | 同上 | 无 | 同上（158 字／1 帧／0 step） |
| `chat-09` | 一次性成文腿 | 同上 | 无 | 同上（541 字／1 帧／0 step；正文引「【用户历史记忆】」＝`orchestrator.py:365` 注入的那一格） |
| `chat-10` | 一次性成文腿 | 同上 | 无 | 同上（155 字／1 帧／0 step） |
| `metric-16` | 一次性成文腿 | 同上 | 无 | 同上（101 字／1 帧／0 step） |
| `approval-06` | 一次性成文腿 | 同上 | 无 | 同上（124 字／1 帧／0 step；sidecar→`approved=False`，本题没走闸） |
| `scope-01` | 一次性成文腿 | 同上 | 无 | 同上（158 字／1 帧／0 step） |
| `data-09` | 工具后终答腿（派发过 worker） | **后端一次 yield**：收尾 `chat.py:2811`；片道有没有响**没量到**（见 §7） | 无（`kind=ok`），但交回的 15 字逐字＝内部交接标记 `【data Agent 返回】`＝`orchestrator.py:633-635 agent_return_marker` | frames→`text_frames=1`/`answer_chars=15`/`events`（`step`×2＋`heartbeat`×7 在帧前）；sidecar→`tool_calls=2`/`evidence_n=0`/`wall_ms=108857.0`；answers→`answer` |
| `metric-02` | **具名结局腿**（`chat.py:2757-2788`） | 后端**一枚 text 帧都没 yield**（`chat.py:2792 if full_text:` 不成立）⇒ 收端 `text_frames=0` | 流内：**`error_code=no_answer_produced`**（`chat.py:2776`）；上游成因：**`error_code=context_limit_exceeded`**（`app/agents/contracts.py:102`） | frames→`kind="error_event"`/`text_frames=0`/`frames=[]`/`events` 尾＝`step`,`error`,`request.failed`,`done`/`extra_chars=21`；sidecar→`wall_ms=119577.9`/`tool_calls=2`；answers→`answer`＝21 字兜底句 |
| `scope-02` | 具名结局腿（同上一枚） | 同上 | 同上（两枚同码，`no_answer_produced` ＋ `context_limit_exceeded`） | 同上（`wall_ms=125225.2`/`tool_calls=2`/`extra_chars=21`） |

### 2.1 (a) 的一次性成文腿：代码链条（逐环点名，八枚共用）

1. `app/agents/orchestrator.py:346 main_agent_node` → `:412 resp = main_model.invoke([sys_msg, current_user_msg])`。
   🔴 **这一发不带 `config`**（本文件现读；第二发模型往返的唯一入口就是这一行）。
2. `app/agents/nodes.py:567-594 answer_leg_stream_target(config)`：`if not isinstance(config, dict): return None, ""`。
   ⇒ 这一发拿不到本轮的 `stream_piece_sink`，也拿不到 `worker`（两格必须同时在场，缺一无片）。
3. ⇒ `nodes.py:891 self._answer_leg_tap(config, call_kwargs)` 交回空 tap ⇒ `_ResilientModel.invoke`（`nodes.py:859`）
   走 `primary.invoke`，**没有一个片进过 `chat.py:2544 result_queue.put(("piece", piece))`**。
4. supervisor 这一发的 `resp` 没有 `tool_calls`（`orchestrator.py:418-419` 那句 `logger.info("[Supervisor] → 最终回答")` 就是这一支）
   ⇒ `orchestrator.py:486 route_main` 在 `:617-618` 交回 `"reflect"`（派发集合为空）⇒ **一个 worker 都没跑**。
   收端对称证据：sidecar `tool_calls=0`。`event: step` 只在 `dispatched` 非空时发出（`chat.py:2952-2988`），
   而 `chat.py:2962-2977` 那套关键词兜底同样没命中 ⇒ 零 step 就是「没派发」，不是「派发没被记到」。
5. `nodes.py:1756 reflect_node` 在 `:1777-1789` 从 `final_answer`／`worker_results`／消息尾部拾取正文，
   `:1791-1802` 只判 `redo`；`route_reflect`（`:1816-1820`）不重派则进 `synthesize`。
6. `nodes.py:2103-2121 synthesize`：`worker_results` 为空 ⇒ 走 `:2117-2121` 从消息尾部拾取那发 supervisor 正文，写进 `final_answer`。
7. `chat.py:2715-2719 _select_final_answer(final_answer=..., worker_results=..., candidates=...)`：
   `:1793-1795` 第二顺位 `_answer_body(final_answer)` 命中 ⇒ `full_text` ＝ supervisor 写的那一整段。
8. `chat.py:2792 if full_text:` 成立 ⇒ `:2811 yield text_sse_frame(full_text, live_cache_fields)`。
   **这一枚是本轮唯一的 `event: text`。**

⇒ `text_frames == 1`、`streams == 1`、`max_stream_frames == 1`、`per_stream == [{"frames": 1, ...}]`、
`missing_chars == 0`、`last_frame_covers_answer == True`、末帧 `sha == answer_sha`。
这七格在九枚里逐枚成立（`tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py::test_the_nine_are_a_single_frame_with_no_prefix_break_and_no_missing_char`
与 `::test_the_nine_put_their_only_frame_at_the_very_close_of_the_round`，现场读数：九枚的 `text` 事件都是 `request.completed` 的**前一枚**）。

员工屏上看到的就是判读件 `:4405` 那句话的形状：转圈到最后一次性砸出全文（`first_visible_ms` 6.6–42.9 s，且 ≈ 收窗时刻）。

### 2.2 被本单排除的四种解释（每条都点名查了哪一层）

- **「代码里有一枚短路腿」**：`rg -n "根据对话历史|已经回答过了|已经为您解答过|历史对话记录" app/` 现读**零命中**
  （查的层＝`app/` 全部源码；同四句在 `docs/handoff/2026-09-15-backend-followup-requests.md:4407` 与本单的
  `tests/test_r456_single_frame_shape_is_not_a_pass.py:47` 命中 ⇒ **零命中只对 `app/` 这一层成立**，不是全仓零命中）。
  ⇒ 话是模型自己写的。钉：`test_the_prose_this_pin_drives_is_not_a_short_circuit_baked_in_the_code`。
  话术来源另有其格：`orchestrator.py:359-367` 把长期记忆拼成 `【用户历史记忆】` 塞进 supervisor 的系统消息
  （`chat-09` 正文逐字引了这个名字），加上 `:357 compress_messages` 交回的历史 ⇒ 模型据此「认为自己答过了」。
  🔴 这一格只解释**正文为什么这么说**，不解释**为什么只发一帧**：前者是内容，后者是形状。
- **「答案太短，被合片规则吞了」**：边界对照三枚同尺读数——`chart-01` 16 字发 **2** 帧（`streams=2`：挂起轮一帧＋批准轮一帧，
  `max_stream_frames=1`）、`data-03` 63 字发 **5** 帧、`unsupported-01` 85 字发 **6** 帧；而 `doc-07` **69 字发 1 帧**。
  ⇒ 帧数不由正文长度决定。钉：`test_the_frame_count_is_not_explained_by_the_answer_length`（形状侧）与
  `test_the_frame_count_is_not_bought_with_the_answer_length`（离线复现侧，同一枚 16 字夹具逐片发读绿、整段发读红）。
- **「读法把帧吞了」**：收端 `scripts/eval_transport_ask_v2.py:394-407 _count_text_frame` 每帧 `out["text_frames"] += 1`，
  既不去重也不折叠；`:342-355` 的 text 支对每一枚 `event: text` 都调它一次。钉：
  `test_the_ruler_counts_every_frame_it_receives_and_collapses_nothing`。
- **「命中的是缓存腿」**：`kind=ok` 九枚的 `events[0]` 全是 `status`、且**全部含 `request.started`**（现算 105/105 含 `request.started`），
  命中腿不发 canonical；判据出处 `scripts/eval_transport_ask_v2.py:1205-1208`（命中即 `raise` 停窗），
  在册读数 `run9-readout-2026-09-28.md:105`「kind 含 cache 的计数=0」。钉：`test_the_nine_are_not_the_cache_hit_leg`。
  🔴 注：判读件 `:105` 给的坐标 `scripts/eval_transport_ask_v2.py:1106-1109` 在本树 `223fa97` 现读是**队列轮询的 blip 计数**，
  命中即 raise 那两枚真身在 `:817-818`（队列道）与 `:1205-1208`（前信道）。本单按本树现读报名字。

## 3. 判据①(b)：`text_frames == 1` 是**后端一次 yield**，不是收端读法

三条各自独立、方向一致的证据：

1. **结构等式（源码层）**：`app/api/v1/chat.py` 的 `/ask` 前信道里，`event: text` 只有两个产地——
   `:2695-2707` 片道（`kind == "piece"`，`piece_count += 1` 后 `:2705 yield text_sse_frame(...)`）与
   `:2811` 收尾整段。而 `:2811` 被 `:2792 if full_text:` 护住：只要本轮有正文就**恒发一枚**。
   ⇒ 对任何 `kind=ok` 且有正文的轮次：`text_frames == 1` ⇔ 片道发出的帧数 == 0。
   九枚的 `last_frame_covers_answer=True`＋末帧 `sha==answer_sha` 说明收尾那一枚确实发了、且就是全文。
2. **收端不折叠（量具层）**：见 §2.2 第三条。若读法会吞帧，`data-03`（同一条腿 5 枚累计帧）也会被读成 1。
3. **离线复现（钉层）**：`tests/test_r456_single_frame_shape_is_not_a_pass.py::test_the_untapped_round_issues_exactly_one_text_frame`
   用 `TestClient`（进程内 ASGI，不开端口）打**真** `/api/v1/ask` 路由 ＋ 一枚假编排流 `one_shot_supervisor_stream`
   （交回 `final_answer` 非空、`worker_results` 为空、**一个字都不碰 `stream_piece_sink`**）；
   整条 SSE 里 `event: text` 恰一枚，且带 `request.started`／`request.completed`／`sources`／`done`，无 `error`／`request.failed`。
   再用**在册量具自己那把尺**判它：`_frame_verdict` 读 **False**。

🔴 「一次 yield」说的是**这一轮里后端只交出一枚 text 帧这件事**，不是「模型只被调用了一次」。
supervisor 那一发本身是一次完整的 `invoke`（框架内部仍可能逐 token 收，但那些字节没有出口）——
这一格在 `chat.py` 层不可分，也不需要分：判据② 量的是帧形状。

批准续跑道是**另一条腿**，本单不混进来：`orchestrator.py:1341-1350 run_interrupt_stream` 不收 `stream_piece_sink`
（`nodes.py:558-563` 已明写「这一腿的逐字交付落在写域之外」），`chat._approve_stream` 的队列只有
`event`／`done`／`error` 三件、收端循环没有 piece 一支，整段帧发在 `chat.py:3422`。
⇒ `chart-01` 那 2 帧是「两条腿各一帧」，不是「一条腿发两帧」，所以它 `max_stream_frames == 1` 而 `text_frames == 2`。

## 4. 判据①(c)：`metric-02`／`scope-02` 的失败码（两枚同码，逐层点名）

### 4.1 流内那一层：具名结局码 = `no_answer_produced`

- `event: error` 的 `content` ＝ 21 字「本轮未产出任何结论，请重试或补充数据范围。」（`chat.py:2763` 造文，`:2766` 发出）
- `event: request.failed` 的 canonical 载荷 `data.error_code` ＝ **`"no_answer_produced"`**（`chat.py:2776`）
- `event: done`：`terminal_state="no_answer"`（`:2782`，常量 `TERMINAL_STATE_NO_ANSWER` 定义在 `:1917`）、`answer_present=False`、`sources_present=False`
- 触发条件：`chat.py:2715-2719` 拾取后 `full_text` 为空，且 `:2723-2729 check_interrupt` 交回空（不是挂在闸上），落到 `:2757 if not full_text:`

🔴 同名码还有**第二个产地**：模型边界 `app/common/model_budget.py:1512 NO_ANSWER_CODE = "no_answer_produced"`
（用在 `app/agents/nodes.py:969-997 detect_empty_answer` 那一支，即「模型答了，答的是空」）。
那一支只进 span 与日志，**不上 SSE**。本单说的「流内码 `no_answer_produced`」指的是 `chat.py:2776` 这一支。

### 4.2 `/ask` 前信道今天有三条失败出口，三张脸两两可分辨（钉在 `tests/test_r456_error_round_is_not_an_answer.py::test_the_failure_legs_are_tellable_apart_by_order_code_and_words`）

| 出口 | 事件先后 | `error_code` | legacy `error` 的 `content` | 有无 `done` | 本单判定 |
|---|---|---|---|---|---|
| 空正文具名结局 `chat.py:2757-2788` | **`error` 先于 `request.failed`** | `no_answer_produced` | 21 字兜底句 | 有（`terminal_state=no_answer`） | ✅ 就是这两枚 |
| 线程抛错 `chat.py:2888-2905` | `request.failed` 先于 `error` | `internal_error` | 异常原文（`str(data)`） | 无 | ❌ 排除 |
| 处理时限 `chat.py:2672-2685` | `request.failed` 先于 `error` | `task_timeout` | 「请求超过系统处理时限」（10 字） | 无 | ❌ 排除 |

两条独立旁证支持「不是超时」：帧账 `events` 里 `error` 排在 `request.failed` **之前**（超时腿反之）；
sidecar `wall_ms`＝119577.9／125225.2 ≪ 300 s 请求预算（`run9-readout-2026-09-28.md:119` 记 `one_attempt_envelope_ms=960000.0`、
latency `max=300110.131` 属于别的题）。钉：`test_the_two_empty_reads_carry_the_named_fallback_bytes_and_nothing_else`／
`::test_the_two_windows_closed_well_before_the_request_budget`。

### 4.3 上游那一层：被拒的成因码 = `context_limit_exceeded`

- 码名住 `app/agents/contracts.py:102 CONTEXT_LIMIT_CODE = "context_limit_exceeded"`（`:252` 已入公开词汇表）。
- 抛点 `app/common/model_budget.py:120-129`（异常句**自带** `(error_code=context_limit_exceeded)`、`prompt_tokens=`、
  `required n_ctx=`、`over_by`、`MODEL_CONTEXT_TOKENS=` 五格读数）；拒发在 `:875-883`——
  **provider 还没看到请求**，且那里**故意不走离线回复**（注释逐字：走了会把真实裁决洗成一句客套话）。
- 算术（在册判读件 `:133` 现读，本单不重算容器账）：`tier=analysis`，`prompt_tokens=2687／2769`，
  `required_n_ctx=4223／4305`，`over_by=127／209`。对得上的那把尺是
  `model_budget.py:114 self.required_context_tokens = self.prompt_tokens + self.declared_max_tokens`
  ＋ `:232 ModelTier.ANALYSIS: 1536`／`:303 DEFAULT_MIN_ANSWER_TOKENS = 1536`
  ＋ `:271 DEFAULT_CONTEXT_TOKENS = 4096`：`2687+1536=4223`、`2769+1536=4305`，两者都 `> 4096`。
- 配对凭据：`run9-readout-2026-09-28.md:129-132`——`执行失败(ERROR)=2 行`／`ModelBudget(WARNING)=2 行`，
  时刻 09:43:56→`metric-02`、10:43:19→`scope-02`，`Δt=0.0 s`（帧账 `ts` 现算＝该题最后一枚事件的到达时刻，本单核过）。

### 4.4 两层之间：这句「码」为什么没能到达客户端（**这才是本单真正交回的病灶**）

```
worker 腿（或 supervisor 那一发）的模型调用被预算拒了
  → raise ModelContextLimitExceeded("... (error_code=context_limit_exceeded) ...")
  → app/agents/orchestrator.py:1429 except Exception as e            ← 编排线程自己吞了
       :1445-1452 关键词重试？"timeout/connection/rate limit/server error" 都不在这个串里 ⇒ 不重试
       :1453 logger.error(f"执行失败: {e}")                            ← 判读件族一那 2 行 ERROR
       :1454-1463 _record_trace(event_type="request.failed", payload={"error": str(e)})   ← 只进 trace，不进流
       :1464 yield {"error": str(e)}                                   ← 交回的是「一枚 dict」
  → chat.py:2584 result_queue.put(("event", event))                    ← 它被当成**普通状态更新**入队
  → chat.py:2907-2922 这段处理：msgs=[]、worker_results={}、final_answer 空 ⇒ **一个字都不落**
  → 编排生成器 return ⇒ chat.py:2585 result_queue.put(("done", None))
  → chat.py:2709 kind=="done" ⇒ _select_final_answer 交回空 ⇒ :2757 具名结局 ⇒ 21 字兜底句
```

⇒ 客户端读到的码是**最后一层**的 `no_answer_produced`（「这一轮没产出结论」这个事实），
而真正能治的那个码 `context_limit_exceeded`（「为什么没产出」）只在 `logger.error` 与 trace 里。
🔴 这不是「报错了」，是**两次不同的具名，中间那一次在跨层交接处被降级成了一枚没人认领的 dict**。
`("error", ...)` 那一支（`chat.py:2888`）只在 `_run()` 自己 `except` 时才会用到（`chat.py:2586-2588`），
而 `run_with_stream` 已经先把异常吃掉了，所以那支今天**结构上到不了**这里。

### 4.5 那 21 字为什么占了 correctness 分母（只点名，不动口径）

洗白发生在收端一处：`scripts/eval_transport_ask_v2.py:1227-1228`
`if not answer.strip() and out["error_text"].strip() and not from_queue: answer, kind, evidence = out["error_text"], "error_event", []`。
分母口径（`run9-readout-2026-09-28.md:115` 那句「分母恒=105」）在 R438／R401 名下，**本单一格没碰**。
本单只钉形状：`kind=error_event` 的轮次不许被读成「答完 21 字」——
`tests/test_r456_error_round_is_not_an_answer.py::test_the_named_outcome_round_has_no_text_frame_under_the_registered_ruler`
（同一把在册尺下 `text_frames==0`、观测桶 `answer==""`、只有 `error_text` 装着那 21 字），
`::test_the_washed_shape_is_not_the_recorded_shape`（把兜底句当终答**发出去**的那一枚有 `request.completed`、有一枚 text 帧、无 `request.failed` ⇒ 与在册读数不同形，判别断言当场红）。

## 5. 复现路径（下一枚改法单可以直接抄；全程离线、零开窗、零打模型）

跑法（本树没有 `.venv`，用主树解释器、在本树内执行；**必须点名文件**）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r456
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' `
  -m pytest tests/test_r456_single_frame_shape_is_not_a_pass.py `
             tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py `
             tests/test_r456_error_round_is_not_an_answer.py `
  -o addopts= -p no:cacheprovider -q
```

三枚复现器（`tests/test_r456_single_frame_shape_is_not_a_pass.py`，都是「挂到真 `/api/v1/ask` 路由上的假编排流」，
夹具沿用 `tests/test_approve_canonical_events.py::_patch_offline`）：

| 想要的形状 | 驱动函数 | 关键动作 | 在册尺读数 |
|---|---|---|---|
| 九枚单片里那八枚 | `one_shot_supervisor_stream` | 只交回 `final_answer`，`worker_results={}`，**不碰 `stream_piece_sink`** | `text_frames=1`、`max_stream_frames=1` ⇒ `_frame_verdict` **False** |
| 反证（逐片发） | `piece_by_piece_stream` | 同一份字、同一把尺，先把 `INCREMENTS` 逐枚交给 sink | `text_frames=len(INCREMENTS)+1` ⇒ **True** |
| 长度无关对照 | `short_answer_streams_pieces`／`short_answer_whole_stream` | 同一枚 16 字正文，一个逐片发、一个整段发 | 前者 True／后者 False |
| 两枚空读 | `named_outcome_stream`（`tests/test_r456_error_round_is_not_an_answer.py`） | 交回 `final_answer=""` ＋ 一条带 `dispatch` 的 `AIMessage` | `text_frames=0`、`kind=error_event`、`error_code=no_answer_produced` |

## 6. 判据② 三把钉与摘守卫读数

🔴 下刀方式：临时 pytest 插件 `%TEMP%\r456\knife_plugin.py`（`-p knife_plugin` ＋ env `R456_KNIFE`），
在 `pytest_collection_finish` 里**只改内存、不动盘**，仓内文件一字节未改。落点从 `item.module.ruler` 反查
（那把尺是 importlib 现场加载的，不在 `sys.modules` 里）。三刀各跑一次三本合跑（30 枚用例）。

### (a) 单片形状钉 —— `test_the_single_frame_round_is_read_as_a_fail_under_criterion_two` 等 9 枚

**刀一 · 摘 verdict**：把 `_frame_verdict` 换成去掉 `text_frames>1` 与 `max_stream_frames>1` 两枚合取项的版本。
⇒ **`3 failed, 27 passed`**（基线 30 passed）。红的三枚：
`test_r456_single_frame_shape_is_not_a_pass.py::test_the_single_frame_round_is_read_as_a_fail_under_criterion_two`、
`::test_the_frame_count_is_not_bought_with_the_answer_length`、
`test_r456_run9_frame_ledger_recomputes_the_verdict.py::test_criterion_two_recomputes_from_the_rows_own_readings`。
红句首行（逐字）：

```
E   AssertionError: 判据② 在 text_frames=1 max_stream_frames=1 这一枚形状上读成 True，而形状要求的读数是 False
E   AssertionError: 复算与在册件漂移 10 枚：['approval-06', 'chart-01', 'chat-03', 'chat-06', 'chat-09', 'chat-10', 'data-09', 'doc-07', 'metric-16', 'scope-01']
```

（第二句那 10 枚＝九枚单片＋`chart-01`：`chart-01` 在册 False、摘刀后读 True ⇒ 一并漂移，正是「钉子咬形状」的旁证。）

### (b) 反证 —— `test_the_same_pin_turns_green_when_the_driver_publishes_pieces`

**同一枚断言函数、同一把尺**，只把驱动器从 `one_shot_supervisor_stream` 换成 `piece_by_piece_stream`：
基线下 `readings["text_frames"] == len(INCREMENTS) + 1` 且 `_frame_verdict` 读 **True**，与 (a) 一起绿。
反证的反证也做了：**刀二 · 折帧**——把 `_count_text_frame` 包一层「累计帧折成同一枚」
⇒ **`3 failed, 27 passed`**，红的正是逐片那一枚、长度对照那一枚，加上一枚自证尺子的
`test_the_ruler_counts_every_frame_it_receives_and_collapses_nothing`（红句 `E   AssertionError: assert 1 == 2`）。
首句：`判据② 在 text_frames=1 max_stream_frames=1 这一枚形状上读成 False，而形状要求的读数是 True`。
⇒ 转绿不是运气：折叠一处，「逐片发」就被读成单片，钉子当场红。

### (c) 兜底句形状钉 —— `test_the_named_outcome_round_has_no_text_frame_under_the_registered_ruler` 等 6 枚

**刀三 · 洗白**：让 `_consume` 交回前把 `error_text` 的字填进 `answer`（＝把在册量具 `:1227-1228` 那一步提前到尺子里）。
⇒ **`1 failed, 29 passed`**。红句逐字：

```
E   AssertionError: '本轮未产出任何结论，请重试或补充数据范围。' == ''
```

⇒ 本单只钉「不许把 error 形状读成答案」这一件事；分母口径一格没动（那格在 R438／R401 名下）。

三本合跑末行原文见 §11。

## 7. 没量到的格子（明写「没量到」，不外推）

1. **片道的实际枚数不在任何在册件里**。`stream_piece_sink` 交了几片、`_AnswerPieceStream.dropped`
   （`chat.py:1735`）涨没涨、`closed`（`:1734`）有没有被 T1「两条腿同时在写」关死——帧账只记**发出去的帧**，
   不发帧的片不留痕。⇒ `data-09` 的 (a) 能定到「工具后终答腿」，但「worker 交回的是空正文」与
   「tap 被关死所以有字也没发」这两格**本单分不开**。
2. **被预算拒掉的那一发属于谁**。`metric-02`／`scope-02` 的 `context_limit_exceeded` 只给出 `tier=analysis`
   （`run9-readout-2026-09-28.md:133`），而 supervisor 第二发与 analysis 档的 worker 腿**同档同名**；
   在册件里没有逐题的 leg 归属。⇒ 「是 supervisor 那一发」不成立，「是 worker 那一发」也不成立，只有「analysis 档的某一发」是数。
3. **step 的载荷不可读**。sidecar `tool_calls` 是**枚数**（`event: step` 计数，`eval_transport_ask_v2.py:340`＋`:1289`），
   `running`／`done` 之分与派了哪个 worker 都不在册件里。⇒ `metric-02`／`scope-02`／`data-09` 那「2 枚 step」
   到底是「一发 running ＋ 一发 done」还是「两发 running」，本单答不上来。
4. **九枚单片没有逐题服务端日志佐证**。判读件族三（`:157-164`）的 `[R149]` 只覆盖 5 枚题号
   （`data-07`／`metric-04`／`metric-10`／`metric-11`／`report-03`），九枚一枚都不在里面；
   `[Supervisor] → 最终回答` 那行的逐题计数判读件没交回。⇒ §2.1 那条链是**源码层结构证明 ＋ 帧账/sidecar 对称读数**，
   不是「每题一行日志点名」。
5. **`data-09` 在 223fa97 上会读成什么，没测**。R439（`b4ce04e`，2026-09-28 12:19:39 并树）晚于 run9 整窗
   （九枚 `ts` 最晚 10:41:14、`data-09` 10:07:38、判读件生成 11:10:31；本单核过帧账 `ts` == 该题最后一枚事件的 `arrival_at`，即收窗时刻），本单没开窗复验。
   可检验的预测：下一扇窗 `data-09` 这一类**要么**逐片多帧、**要么**读成 `text_frames=0` ＋ `error_code=no_answer_produced`，
   **不可能**再是「1 帧 × 15 字标记」——因为 `orchestrator.py:652-664 agent_return_message` 现在正文为空就不包装，
   而 `chat.py:1815-1824 _recorded_final_answer` 不收只剩标记的那一发。

## 8. 本单认为总控这单判据写得不准的地方（两处，都只订正措辞，不改结论）

1. **「事件数那一半不过＝94/105」与「判据② 成立＝91/105」是两枚数，不能并排写成同一件事。**
   判据② 的合取里除了 `text_frames>1` 还有 `max_stream_frames>1`、`uncorrected_breaks==0`
   （尺＝`scripts/eval_transport_ask_v2.py::_frame_verdict`）。本单现算：`text_frames>1`＝94、
   `criterion_two_holds==True`＝**91**，差的三枚＝`chart-01`（批准轮那条腿只有 1 帧）、`report-02`、`tool-04`（真断流）。
   ⇒ 「九枚单片＋两枚空读＝11 枚拖住了事件数那一半」这句**对**；但如果下一班把「94/105」读成
   「判据② 有 94 枚绿」，就会漏掉另外三枚坏形。在册判读件 `:237` 自己两枚数都给过，本单只是把口径写死在报告里。
2. **`run9-readout-2026-09-28.md:115` 那格引的坐标 `app/quality/eval.py:401-402` 在本树指错了地方。**
   现读 `:401-402` 是**第二把尺的越界校验**（`raise ScorabilityDerivationError(f"第二把尺 {number} 越出 [0, 1]...")`）。
   「分母恒＝全部题数」的真实读点是 `app/quality/eval.py:16`（`total = len(rows)`）／`:124`＋`:143-147`
   （甲案旧口径那把尺）／`:293-306`（丙案三数算式）／`:688`（R438 那句「分母不因甲案而变」）。
   分母口径本身**不用改**，本单也没动它；要改的是那两行坐标。同类坐漂还有 `:105` 引的
   `scripts/eval_transport_ask_v2.py:1106-1109`（见 §2.2 末条）。

另记一笔（不是异议，是免重复）：`docs/handoff/2026-09-15-backend-followup-requests.md:4405-4408` 已有一段同题归因，
其中引用的旧坐标（如 `chat.py:1026-1029`／`:1329-1355`）在本树 `223fa97` 现读为 `:2763`／`:2757-2788`。
本单不重复印那一段，只在坐标对不上的地方按本树现读报名字。

## 9. 哪些结论只有沙盒／在册产物支撑，不能当客户事实

- **整窗都在本机**：run9 的 105 题跑在本机容器 `enterprise-brain-backend-1` ＋ 1008 枚语料上；
  本单的归因读的是那一窗的产物，**不是任何客户机**。
- `MODEL_CONTEXT_TOKENS=4096`／analysis 档 `max_tokens=1536` 是本机读数（`app/common/model_budget.py:271`／`:232`／`:303`）。
  ⇒ 「`metric-02`／`scope-02` 是客户会遇到的失败」这句**本单不写**；本单只写「在本机这一档窗口预算下，
  2687／2769 枚 prompt token 触发了拒发，并且那一句码在跨层交接处丢了」。窗口尺寸与 `num_ctx` 的配套是业主裁量项
  （跟进单 §129 五把它列在「不许动」清单里）。
- §2.1 那条链是**源码结构证明**（对本树 `223fa97` 成立），不是对客户环境实测。R439 之后 `data-09` 的形状变了没有，
  要靠下一扇窗（§7 第 5 条给了可检验预测）。
- 「模型认为自己答过了」只解释正文措辞，不解释帧数（§2.2）。把这两件事混成一格，就会得出
  「改提示词能修 A②」这种假结论——本单不支持。

## 10. 下一枚改法单的锚点（本单不动手，只点名）

按「改动面积／是否触碰别人名下文件」排序，三条互相独立：

1. **让 supervisor 终答那一发接上片段出口**：`app/agents/orchestrator.py:412` 那一发不带 `config` ⇒
   `app/agents/nodes.py:567-594 answer_leg_stream_target` 恒交回 `(None, "")`。八枚（九枚里除 `data-09`）都卡在这一行。
   这一处不在 `chat.py`，**不与 Carson 名下返工冲突**。
2. **把跨层那句具名码送到客户端**：`orchestrator.py:1464 yield {"error": str(e)}` 交回的 dict 在
   `chat.py:2907-2922` 不被认领。要么让它走 `chat.py:2888` 那支（真码 `internal_error` ＋ 原文），
   要么给编排层一枚可上流的结局码。这一处**在 `chat.py`**，要与 R404 串行。
3. **`metric-02`／`scope-02` 本体是窗口预算，不是编排缺陷**：治它的是抬 `MODEL_CONTEXT_TOKENS` ＋ Ollama `num_ctx`
   配套（业主裁量），或让 prompt 装箱在拒发之前先削（`app/common/model_budget.py` 的 `window_plan`）。
   ⚠️ 本单**不推荐**在本机抬——一抬就和客户尺寸脱钩，会把这一窗的数变成另一件事。

## 11. 本单文件账（`git status --porcelain -uall` 现取；基点 `223fa97` 之外零改动）

```
?? docs/perf/a2-single-frame-attribution-2026-09-28.md
?? tests/test_r456_single_frame_shape_is_not_a_pass.py
?? tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py
?? tests/test_r456_error_round_is_not_an_answer.py
```

`git diff --numstat` 对未跟踪文件交回空账，故逐枚给字节／行数（新件，numstat 等价于 `0/新增行数`）：

| 文件 | 字节 | 行数 | 换行 | BOM | U+FFFD | NUL | 裸 LF | 孤独 CR |
|---|---|---|---|---|---|---|---|---|
| `docs/perf/a2-single-frame-attribution-2026-09-28.md` | 36817 | 377 | CRLF | 无 | 0 | 0 | 0 | 0 |
| `tests/test_r456_single_frame_shape_is_not_a_pass.py` | 16998 | 343 | CRLF | 无 | 0 | 0 | 0 | 0 |
| `tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py` | 13398 | 258 | CRLF | 无 | 0 | 0 | 0 | 0 |
| `tests/test_r456_error_round_is_not_an_answer.py` | 14341 | 276 | CRLF | 无 | 0 | 0 | 0 | 0 |

`docs/perf/**` 在册三本模板（`eval-must-contain-lineage-2026-09-28.md`／`p3-recall-compare-2026-09-26.md`／
`latency-budget-2026-09-16.md`）现读全部＝**CRLF／无 BOM／零裸 LF／零孤独 CR**，本报告照此写盘。
四枚新件都无尾 newline；`tests/**` 在册件在本机盘面同为 CRLF／无 BOM／零裸 LF／零孤独 CR
（`tests/test_r302_docs_utf8_guard.py` 178 行／无尾 newline、`tests/test_r439_assembly_never_fakes_a_label.py` 217 行，现读），
本报告与三枚新钉照此对齐。行数＝`count(换行符) + （末尾无换行则记 1 行）`。