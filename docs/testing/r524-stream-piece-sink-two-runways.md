# R524（代号 B）· R31 差格 a/b：stream piece sink 接进「审批续跑道」与「队列道」

施工树 `C:\Users\fengx\PycharmProjects\be-r524`，基点 `28e9d50`（detached，就地改，未 commit / 未 git add）。
派工词：`.tmpfix/r524_dispatch.txt`。本节所有数字均为**执行层自报**，每条后面附命令原文，总控可逐条复跑。

## 1. 结论一览

```r524-verdict
approval_resume_lane=connected
queue_lane=not_applicable
criterion_3_rulers=untouched
criterion_4_no_registrant_branch=unchanged
worker_admission_list=unchanged
```

- **差格 a（审批续跑道）＝已接上**：`run_interrupt_stream` 收 `stream_piece_sink` 形参并把它写进
  `config["configurable"]`；`/approve` 交出自己那枚 `_piece_sink`，队列长出第四种件 `piece`，收端
  有 `kind == "piece"` 那一支。逐片帧能不能上屏由 **R464** 那道闸说了算，本单没改它的裁定。
- **差格 b（队列道）＝本单写域内不可接**：入队那一轮零枚模型调用、零枚 `text` 帧、投递面在两枚帧
  之后即关；真接点在 `deploy/queue_worker.py`（白名单外）。按判据② 交回带凭据的 `not_applicable`，
  并把「未达」归因写实（见 §4）。
- **判据③ 三把尺一字未动**、**判据④ 无人注册那一支形状未动**、`ANSWER_LEG_STREAM_WORKERS` 未放宽。

## 2. 判据逐条：命令 → 读数（执行层自报）

| 判据 | 命令 | 读数 |
| --- | --- | --- |
| ① 字面尺 | `git grep -n stream_piece_sink -- app/agents/orchestrator.py` | 改前 **5** 处（全在 `run_with_stream`），改后 **9** 处；`>=2` 成立，但那把尺改前就绿，所以另立按函数点名的钉（§2.1） |
| ① 承重的尺 | `tests/test_r524_sink_reaches_both_runways.py::test_criterion_one_names_both_runways_not_just_a_hit_count` | 两跑道各一枚 `stream_piece_sink=None,` 形参 + 各一枚 `config["configurable"][STREAM_PIECE_SINK_KEY] = stream_piece_sink`；`text.count(REGISTER_STATEMENT) == 2` |
| ② 队列道 | `python -m pytest tests/test_r524_queue_lane_sends_no_second_character.py -q` | 帧名序列 `["queued","done"]`、`text` 恒 **0** 枚、模型调用 **0** 次、`run_with_stream` **0** 次 ⇒ `not_applicable`（凭据见 §4） |
| ③ 三把尺 | `git grep -n "^STREAM_PIECE_MIN_CHARS\|^STREAM_PIECE_MERGE_SECONDS\|^STREAM_PIECE_STALL_FLOOR_CHARS" -- app/agents/nodes.py` | `:327 = 20` / `:329 = 0.1` / `:332 = 4`（改前逐字同，`git diff` 未碰这三行） |
| ④ R203 负向钉 | `python -m pytest tests/test_r203_sink_reaches_the_leg.py -q`（改码之后、改口之前） | **当场红**：`1 failed, 5 passed`，`FAILED ...::test_the_resume_runway_has_no_place_to_register_a_sink`，红话 `assert 'stream_piece_sink' not in mappingproxy(...('stream_piece_sink', <Parameter "stream_piece_sink=None">)]))`，位置 `tests/test_r203_sink_reaches_the_leg.py:277`（＝`git show 28e9d50:` 那份未改件的坐标；改口后同一枚钉现读 :272）。对账见 §5 |
| ⑤ 无人注册 | `python -m pytest tests/test_r524_sink_reaches_both_runways.py::test_an_unregistered_round_publishes_nothing tests/test_r524_sink_reaches_both_runways.py::test_an_unregistered_resume_round_adds_not_a_single_key -q` | `publish_stream_pieces(无出口 config, [片]) is None`、`answer_leg_stream_target(...) == (None, "")`、`logger.warning` 零调用；续跑道不注册时 `configurable` 里连键都不加 |
| ⑥ 窗内读数 | §3 | 后端日志一行 `[R149] ... 批准续跑轮收到流式片段：pieces=… cumulative=… leg=… call=… dropped=…`，键名与 /ask 那行在册读数**逐字同名**；`FRAME_READING_KEYS`（`tests/test_r181_text_frame_ruler.py:43`）一格未碰 |
| ⑦ 反证刀 | `python -m pytest tests/test_r524_counter_evidence_teeth.py -q` | **22 passed**（执行层自报）：十把刀（七把走影子回挂＋三把动纸面读数/模块常数），每把＝影子端正控＋在册钉本身红（§6） |

### 2.1 为什么判据① 的字面尺不够用（照实说，不是抬高门槛）

派工词写的是「接上之后 `>=2` 处」。**这一格改前就有 5 处命中**，全住在 `run_with_stream` 里，所以
只数枚数的尺在没接上的盘面上也绿——本单如果只交那枚计数，就是把一枚永绿的尺当判据（与上一班那枚
永不匹配的死牙同族，方向相反、病根相同）。因此：

- 字面尺照抄交回（改前 5／改后 9），**另外**按函数点名：一枚跑道要同时收得到形参、且真把出口写进
  `configurable`，缺一枚即红；
- 摘刀的读数在 §6 刀 K1：把 `run_interrupt_stream` 里那一行注册语句摘进影子，两枚钉当场红。

### 2.2 端到端：审批续跑道上「片真到过收端」的两族形状

`python -m pytest tests/test_r524_sink_reaches_both_runways.py -q` —— 12 枚全绿（执行层自报）。两族形状：

- **屏上无正文**（挂起轮一枚字没交，run9 `chart-01` 那一族）：`text` 事件 **>1**、帧与帧首尾相接是
  单调前缀、逐字拼回 == 本轮交付正文、片段时间戳两两不重叠、除末片外每片 `>= 20` 字、
  `worker` 恒 `chart`、`call_id` 恒一枚、provider 请求体 `stream=true`（注册了出口 ⇒ R203 那套准入
  把这发改走流式）。
- **屏上已有同一份正文**（R464 病历的常态：批准后图把同一条腿重跑一遍）：逐片帧 **0 枚**上屏，
  `text` 帧序列与改前逐字相同，而片仍 `>1` 枚到过收端（只进账不进屏）。

夹具分工：假的只有 `run_interrupt_stream` 那一层（它按真图口径把 `worker` 塞进 `configurable`，
出口用调用方交来的那一枚），真的部分是 `nodes._ResilientModel` + `_AnswerPieceTap` +
`StreamPieceMerger`（判据③ 那三把尺）+ `chat._AnswerPieceStream` 折帧 + `_ApprovedAnswerStream`
闸门 + 真 `/api/v1/approve` 路由。零端口、零模型、零容器。

## 3. 判据⑥：开窗后读哪一行才能证明 sink 真接到了这两条道

**读后端日志这一行**（INFO，logger `enterprise_brain`，模块标签 `[R149]`）：

```
[R149] session=r524-res... 批准续跑轮收到流式片段：pieces=5 cumulative=157 leg=chart call=d85ce7f5dd3d dropped=0（逐片帧上屏 5 枚 / 屏上已含其字而只记账 0 枚）
[R149] session=r524-res... 批准续跑轮收到流式片段：pieces=5 cumulative=157 leg=chart call=11b5493f7509 dropped=0（逐片帧上屏 0 枚 / 屏上已含其字而只记账 5 枚）
```

上面两行是**现取**读数（执行层自报），命令：
`python -m pytest tests/test_r524_sink_reaches_both_runways.py -q --log-cli-level=INFO`——
第一行＝屏上无正文那一族（逐片帧真上屏 5 枚），第二行＝屏上已站着同一份正文那一族（一枚都不上屏，
5 片全进账）。🔴 本纸此前抄的 `pieces=4 cumulative=133` 是**未复核的手抄数**，与现读不符：本轮正文 157 字、按 18 字一 chunk 喂，尺寸闸（20 字）切出 4 枚满片 + 1 枚末片 = 5 片，`cumulative=` 读的是末帧字数 = 157。`call=` 每轮现生成，不许按字面比对。

- 落点：`app/api/v1/chat.py:3657-3668`（`_approve_stream` 的 `done` 分支，紧跟 R464 那行 `held` 告警之后），
  只在 `piece_count > 0` 时才打——没收到片就一行都不多。
- **窗口判据的读法**：`run10` 里凡是走过 `/approve` 的题，看到这行 = 续跑道的 sink 真接到了、
  字真从模型那一路进过出口；`pieces=0` 或整行缺席 = 那条腿今天没字（挂起腿仍是确定性拼的那一格）。
  `leg=` 给腿名（这正是 R518 交回的「腿名 0/105 派生不出」那一格今天唯一能落地的读法：
  `docs/testing/r518-a2-lane-attribution-2026-09-29.md` 明写要证腿名「只能读后端日志里的
  `leg=`/`call=`/`dropped=`」），`call=` 给那一发的身份，`dropped=` 给收端折掉的枚数。
- **队列道那一侧读什么**：读不到任何逐片读数，而且这是事实而不是缺码——`queued_response` 那一支
  `text` 帧恒 0 枚，所以帧账上 `text_frames` 对那一发 HTTP 就该读 0（在册量具
  `scripts/eval_transport_ask_v2.py` 的 `text_frames` 键，`FRAME_READING_KEYS` 里已有，本单没加键）。
  窗口里若看到「报告档题的 `text_frames>1` 伴随一次 `/approve` 而 `/queue/status` 无终态」，那是
  另一格病，不是这一格被接上了的证据。
- **没有新键**：本行用的 `session=` / `pieces=` / `cumulative=` / `leg=` / `call=` / `dropped=`
  六枚名字与 /ask 那行在册读数（`app/api/v1/chat.py:2900-2908`）逐字同名，由
  `test_those_key_names_are_actually_registered_on_the_ask_reading_line` 钉住；
  `test_the_window_reading_adds_no_key_nobody_consumes` 把运行时真到手的读数行拆成字段，键集与
  在册词汇**对判**（不是子集），多一枚就是没人消费。R518 的 `FRAME_READING_KEYS` 本单一格未碰。

## 4. 差格 b：`not_applicable` 的凭据，与「未达」的归因

四条事实（`tests/test_r524_queue_lane_sends_no_second_character.py` 逐枚钉着，全部离线夹具）：

1. **两枚帧**：真走 `chat.ask` 的报告档入队支（`REPORT_LANE_VIA_QUEUE=on`）与超限支
   （`check_rate_limit` 拒），帧名序列都是 `["queued", "done"]`，`text` 帧 **0** 枚。
2. **零枚模型调用**：`_make_model` 被调用就当场抛（spy 直接 raise），实测 **0** 次；
   `run_with_stream` **0** 次；`done` 帧 `terminal_state=queued` / `answer_present=false` / `usage=null`。
3. **可注册点今天已在树上（09-30 由 R548 补；本条前半句仍成立，后半句翻面）**：
   `_enqueue_ask_turn` 源文（含嵌套的 `queued_response`）里 `stream_piece_sink` 仍然 **0** 命中——
   入队那一支自己确实不收片；但 `deploy/queue_worker.py` 里现取 **5 行命中**（:425/:496/:502/:520/:704，
   注册点 :520），`git grep -c stream_piece_sink -- deploy/queue_worker.py` 已由 rc=1 无匹配变 **rc=0**。
   那一发 `run_with_stream(` 在该文件里仍只有一处（`_drain_report_stream` 那一腿，行号由
   `test_the_real_hook_for_the_queue_lane_is_now_registered__r548` 现取；旧名
   `..._is_outside_this_ticket_write_domain` 随改口作废）。🔴 这一格今天只欠**投递面**（见下一条），
   不欠可注册点。原文那句「没有可注册的地方」在 R548 并树后就是假话，改口由总控代笔——
   施工方按裁定没碰本纸，它只交回了坐标与原文。
4. **投递面已关**：入队那条 SSE 在两枚 chunk 之后就 `StopAsyncIteration`，此后的读数只从轮询面
   `GET /api/v1/queue/status/{request_id}` 回来——即使 worker 进程注册了出口，也没有一条活着的流收它。

**因此判据② 的那三条（`text` >1 / 片段不重叠 / 逐字拼回无缺字）在这一支没有主语**，按派工词写成
`not_applicable` 交回总控裁，不伪造逐片。

🔴 **未达格明写**：差格 b 的「接上」本单**没做到**，差在两处，两处都不在写域里：

- 注册点：`deploy/queue_worker.py::_drain_report_stream` 那一发 `run_with_stream`（`deploy/**` 不在
  本单白名单，本单一字节未改它）；
- 投递面：队列道没有活着的 SSE。要真交付逐字，得先决定「片送到哪一面」——轮询面加增量读数或新起
  一条 tail SSE，两者都要动 `docs/api/contract-v1.md`（R526 写域）与前端（`frontend/**` 本单禁碰）。
  按派工词「越界即停并回报」，这一格只写在本纸里交总控落笔，本单没有自行动纸。

**建议**：另派一枚含 `deploy/**` + `app/common/reliable_queue.py` 写域的单，并把契约改口排在它之前；
在那之前，R31 差格 b 在计划书上应记「未达·写域外＋需契约裁定」，不该记「已接」。

## 5. 判据④：R203 那枚负向钉的改口对账

- 取档命令：`git show 28e9d50:tests/test_r203_sink_reaches_the_leg.py`
- 取档件读数（执行层自报）：**13248 字节 / 317 行 / LF**，
  sha256 = `725a8e7144ab5d35804da603f2d797bf4ac461cfd0f49c90c5ade9cd832d9dcd`
- 当场红的原文（§2 表 ④ 那一行）与钉的坐标：`tests/test_r203_sink_reaches_the_leg.py:277`——那是 `28e9d50` 取档件上的坐标；改口后同一枚钉更名为下一条那枚，现读 `tests/test_r203_sink_reaches_the_leg.py:272`
- 改口落点：同名测试更名为 `test_the_resume_runway_now_registers_a_sink__r524_rewrites_the_verdict`，
  改前四条断言**逐字抄在该枚钉的 docstring 里**（历史读数一字未改，只改结论），新读数为
  「三格翻面 + 一格仍成立」：形参收了 / config 塞了 / 词汇表长出 `piece`，而
  `ANSWER_LEG_STREAM_WORKERS` 仍旧是 `{doc, data, chart}`。
- 同源散文（本单写域内的两处注释）一并改口：
  `app/agents/nodes.py` 名单块里「挂起之后从 `/approve` 续的那一跑道结构上接不到 sink」那一段、
  `app/agents/orchestrator.py:360` `_supervisor_answer_tap` 准入条件①「只有 `chat._ask_stream` 注册它」。
  🔴 计划书散文（`docs/handoff/2026-09-30-plan-eight-tickets-recheck.md` §2 R31 差格 a/b、
  以及计划书 L486/L503 那一格）与 `docs/api/contract-v1.md` 不在本单写域，**交回总控落笔**。

### 5.1 另两枚在册钉也被本单接线当场打红（在白名单之外，交总控复裁）

判据 4 只预先点名了 `tests/test_r203_sink_reaches_the_leg.py`，但接线一落地，另外两枚在册钉也**当场红**。
两枚都属于「钉的前提被本单正当改变」那一形，不是病；两枚都按同一程序留了对账（先取档，再改口，历史读数
逐字抄进件里，不手改）。

1. `tests/test_approval_stream.py::test_approve_stream_emits_worker_result_when_no_plain_ai_message`
   - 当场红读数（执行层自报）：`AssertionError: assert [] == ['图表已生成：/static/chart.png']`
     ——那条腿一条 `text` 都没交。
   - 根因（复现：把一枚同签名假件按真调用方式叫一遍）：`TypeError: fake() got an unexpected keyword
     argument 'stream_piece_sink'`。件里那枚 `fake_run_interrupt_stream(thread_id, approved, user=None,
     cancel_event=None)` 是按**改前**真签名 mirror 的假件，`_approve_stream` 现在多交一枚出口，假件不收
     ⇒ 整条腿被 `_run` 的 `except` 报成 error。
   - 改法（最小）：假件签名补 `stream_piece_sink=None` 并把它记进 `seen`；另加一枚
     `assert callable(seen["stream_piece_sink"])`——从「没被打到」改成「确实收过出口」，强度只升。
   - 取档件：`git show 28e9d50:tests/test_approval_stream.py` = 7002 字节 / 196 行 / LF /
     sha256 `3f17f8b38a406be5143b14d49ecce3d8de1ee84e6e1cd80330720cb24c7d9d48`；改后 numstat 6/1。
2. `tests/test_r464_one_terminal_answer_stream_per_round.py::test_the_guard_touches_exactly_two_yield_sites_in_the_approve_leg`
   - 当场红读数（执行层自报）：`AssertionError: 批准腿的守卫调用点不是两枚` / `assert 3 == 2`。
   - 为什么必须多一枚：差格 a 把续跑道的逐片帧接进**同一道** R464 闸门（多出来的调用点是
     `_emit_answer(frame_text, terminal=False)`），而不是另造第二套片账——那正是该件自己那条「同源纪律」
     要求的形状。枚数 2→3、`terminal` 分布 `[False, True]`→`[False, False, True]`，`ask()` 侧仍旧零枚
     ⇒ 一格没放宽，只改枚数与结论。
   - 改法：该枚钉更名为
     `test_the_guard_touches_three_yield_sites_in_the_approve_leg__r524_adds_the_piece_branch`，
     改前整枚 22 行**逐字**抄进该函数体内的注释块作对账。取档件：
     `git show 28e9d50:tests/test_r464_one_terminal_answer_stream_per_round.py` = 59458 字节 / 1011 行 /
     LF / sha256 `f78ae09e1067fa295a9f61efcfe588b79208b8c231f4d4cd2e96bc79f324fe57`；改后 numstat 37/6。
   - 🔴 复裁口径：若总控判定这两枚不该由本单动（白名单只给了 R203），撤回必须**成对**——本单代码回退到
     不交出口（判据① 随之退回「未达」），不能只回退这两枚钉，否则盘面就是红的。

## 6. 反证刀（判据⑦）—— 十把，每把先在影子端跑正控

件：`tests/test_r524_counter_evidence_teeth.py`；跑法
`python -m pytest tests/test_r524_counter_evidence_teeth.py -q` ⇒ **22 passed**（执行层自报）。

机械口径：摘刀一律在**内存影子**里做——被跟踪文件的源文在 import 那一刻抄进内存，按锚点改一格，
写进 `tmp_path` 的影子副本，再 `exec` 回挂到模块上（`monkeypatch` teardown 复原）。影子的
`__globals__` 用模块**活的那本 dict**，不是 `dict(vars(module))` 的副本：victim 钉在跑的过程里还要
`monkeypatch` 模块属性（`orchestrator._cancellable_stream`、`nodes.logger`），副本 globals 会让影子
看不见那些补丁 ⇒ 正控与摘刀量的就不是同一条链。每把刀进刀前后各核一次被跟踪文件 sha256，最后一枚
用例总清点四枚指纹（`test_z9b_...`）⇒ **仓里一字节未动**。

| 刀 | 摘哪一格（锚点现取唯一） | 影子端正控 | 摘刀读数（victim 全是**在册钉本身**） |
| --- | --- | --- | --- |
| K1 | `run_interrupt_stream` 里那枚注册语句换成 `pass` | `test_k1_positive_control_*` 两枚绿 | `test_the_resume_runway_registers_the_very_sink_the_caller_handed_in` 红在 `KeyError: 'stream_piece_sink'`；源文侧谓词 True→False，而 `run_with_stream` 那枚照旧 True（只咬审批道）。摘成整行删掉会只剩注释 ⇒ SyntaxError，那是机械坏了不是牙咬到 |
| K1b | 同一跑道的形参 `stream_piece_sink=None,` 整行摘掉（半接线） | 同上 | 同一枚钉红在 `TypeError: run_interrupt_stream() got an unexpected keyword argument 'stream_piece_sink'`；注册语句计数仍旧 2 ⇒ 文本谓词查的是「两格齐不齐」而不是单格 |
| K2 | `chat.approve` 调用点 `stream_piece_sink=_piece_sink,` | 端到端绿 | `test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing` 红：`续跑道一枚逐片帧都没上屏（text 事件 >1 不成立）：[]`。源码里「注册点」那几行注释原样留着也照红 ⇒ 定罪格不看注释 |
| K3 | 收端 `if kind == "piece":` 那一支的入口 | 帧与窗内读数两枚绿 | 两枚一起红：逐片定罪（同上）+ `test_the_resume_runway_reports_the_round_in_the_registered_log_keys`（`assert 0 == 1`，判据⑥ 那行整行缺席） |
| K4 | 「屏上已含其字 ⇒ 只记账」守卫的方向：`startswith`→`endswith` | R464 侧账干净（零帧零告警） | `test_the_resume_runway_does_not_re_deliver_text_already_on_screen` 红在告警账：`批准腿拦下 N 枚非延续整段（第二枚流）` ⇒ 屏上看着没变而 R464 的账已被逐片帧灌满 |
| K5 | 同一格写钝成「一概不发」（守卫条件换 `True`） | 端到端绿 | 逐片定罪红 ⇒ 本单的绿不是靠「永不发帧」换来的 |
| K6 | 纸上 `queue_lane=not_applicable` 偷写成 `connected`（伪造落在 `paper_verdict` 的读数上，本纸一字节未改） | 纸与盘同词，在册对判钉绿 | `test_the_paper_word_and_the_tree_agree` 红：`not_applicable != connected` |
| K6b | 反方向：盘面真接上字（影子 `_enqueue_ask_turn` 发两枚 `text` 帧）而纸不改口 | 同 K6 | 同一枚对判钉红（`text_frames` 由 0 翻 2、`verdict_for(facts)=='connected'` 而纸还写 `not_applicable`）⇒ 对判不是单向死牙 |
| K7 | 判据③ 尺寸闸 `STREAM_PIECE_MIN_CHARS = 20`→`= 2` | 三把尺现读 20 / 0.1 / 4，字面钉绿 | 两半都红：源文侧字面谓词不再成立 + 同一枚钉红在 `assert 2 == 20`。`test_k7b_...` 另量一格事实：钝尺下 157 字正文切 9 片（在册口径切 5 片），每片都 <20 字而端到端形状断言全放行 ⇒ **字面钉不是装饰**；另记机械事实——`StreamPieceMerger.__init__` 的默认值在类定义期绑定，运行时改模块常数改不动默认值，所以字面钉必须读源文 |
| K8 | `nodes.publish_stream_pieces` 里 `if sink is None: return` 那一格 | 未注册钉绿 | `test_an_unregistered_round_publishes_nothing` 红：无人注册的轮次走到 `sink(piece)` 抛 `TypeError` 并被兜住记进 `logger.warning` ⇒ 判据④⑤ 要的「默认整个特性关掉的样子」没了 |

派工词点名的三把：**K1**（摘审批道注册 ⇒ 判据① 那枚红）与 **K6**（把 `not_applicable` 偷写成已过 ⇒
对应枚红）照字面交回；**「摘掉队列道注册 ⇒ 端到端枚红」这一把照字面构造不出来**——那一支今天没有注册
可摘（`deploy/queue_worker.py` 里 `stream_piece_sink` 0 命中，唯一真接点在 `deploy/**`，白名单外），
所以交回**等价的两把双向牙** K6 + K6b，偏差同时写在 §4 与本节开头，不藏。

## 6.1 邻件清单（本单点名跑过的在册件，36 枚）

跑法：`python -m pytest <下面 36 个路径> -q -p no:cacheprovider --no-header`
读数（执行层自报，改口全部落地之后的最后一遍）：**648 passed / 12 skipped / 0 failed / exit=0，157.78 s**。
🔴 未跑全量回归门（硬规矩），这份清单就是本单点名的全部邻件；耗时随机器负载浮动（同树另有三枚 Agent 在跑），
枚数不随之变。

- 本单三枚新件：`tests/test_r524_sink_reaches_both_runways.py`（12 枚）、
  `tests/test_r524_queue_lane_sends_no_second_character.py`（9 枚）、
  `tests/test_r524_counter_evidence_teeth.py`（22 枚）；
- 逐片道与同一条链：`test_r203_sink_reaches_the_leg.py`、`test_r203_sse_progressive_frames.py`、
  `test_r203_answer_leg_streams.py`、`test_r149_sse_text_pieces.py`、`test_r31_stream_pieces.py`、
  `test_r31_generation_stream_passthrough.py`、`test_r210_break_replaces_the_screen.py`、
  `test_r464_one_terminal_answer_stream_per_round.py`、`test_r459_ask_direct_answer_frames.py`、
  `test_r459_supervisor_answer_leg_streams.py`、`test_r456_error_round_is_not_an_answer.py`、
  `test_r456_run9_frame_ledger_recomputes_the_verdict.py`、`test_r456_single_frame_shape_is_not_a_pass.py`、
  `test_r181_text_frame_ruler.py`（`FRAME_READING_KEYS` 那枚甲案钉，本单未碰）；
- /approve 面（凡真打这条路由或 stub `run_interrupt_stream` 的件全数点名——实测只有两枚被接线打到，见 §5.1）：
  `test_approval_stream.py`、`test_approve_canonical_events.py`、`test_hitl_pending.py`、
  `test_request_cancellation.py`、`test_cancellation_epoch.py`、`test_r123_hitl_approval.py`、
  `test_r123_real_probe.py`、`test_r172_lane_across_hitl.py`、`test_r175_failed_turn.py`、
  `test_r179_chat_denials.py`、`test_r223_frame_arrival_clock.py`、
  `test_r259_awaiting_approval_stops_the_watch.py`、`test_r414_b_terminal_data_filename.py`、
  `test_r447_queue_approval_round_and_evidence.py`、`test_r504_terminal_frames_carry_data_filename.py`、
  `test_session_ownership_guards.py`、`test_supervisor_roundtrip.py`；
- 队列道邻侧：`test_r37_report_lane_enqueue.py`、`test_r32_lane_contract.py`——R520 记的那格
  「`test_r32_lane_contract.py` 在别的树上曾红」在本树**未复现**，合跑里绿。

## 7. 交工与风险（执行层自报）

- 改动（`git -C C:\Users\fengx\PycharmProjects\be-r524 diff --numstat` 原样，执行层自报）：

  ```
  9	6	app/agents/nodes.py
  19	2	app/agents/orchestrator.py
  51	0	app/api/v1/chat.py
  6	1	tests/test_approval_stream.py
  35	16	tests/test_r203_sink_reaches_the_leg.py
  37	6	tests/test_r464_one_terminal_answer_stream_per_round.py
  ```

  后两枚 `tests/` 件就是 §5.1 那两格改口；`chroma_db/chroma.sqlite3` 见下面那条副作用，已复原，
  所以不在这张表里。
- 新增件（未跟踪，`git status --porcelain` 里四个 `??`；字节 / 行数 / sha256 前 8 / 换行）：
  `tests/test_r524_sink_reaches_both_runways.py` 24150 / 470 / `5d6f9351` / CRLF、
  `tests/test_r524_queue_lane_sends_no_second_character.py` 16784 / 351 / `e3752c81` / CRLF、
  `tests/test_r524_counter_evidence_teeth.py` 26967 / 440 / `1a412abb` / CRLF、
  本纸（`docs/testing/r524-stream-piece-sink-two-runways.md`）。
  未 commit、未 `git add`、未跑全量门、未动容器／服务／模型、未碰别的树。
- 跑测试的机器副作用一格（**不属本单写域，写在这里免得总控误判**）：本树任意一次 pytest 都会把**被跟踪的**
  `chroma_db/chroma.sqlite3` 写脏（实测 mtime 落在跑测那一刻；主树同名件同样 dirty ⇒ 那是夹具/conftest 的
  落点，不是本单的写）。本单跑完已 `git checkout -- chroma_db/chroma.sqlite3` 复原到 `28e9d50`；
  总控在自己的树上复跑后会看到同一格脏，别把它算进本单的 diff。
- 风险一：注册了出口之后，续跑道上被挂起的那条腿（`chart`）那一发 `invoke` 会改走流式（R203 的既有
  准入，不是本单新造的开关）。这是「接上」的必然结果，也是今晚窗口要量的形状；如果 provider 在半路
  死掉，R210/R464 的纠正替换那一支照旧接管，屏上不拼半截真话。
- 风险二：本单**只**给续跑道接了出口，没有改 R464 的裁定，所以「批准腿的逐片流有没有整段换源资格」
  仍是未裁格——今天的答案是「没有」，屏上形状与改前逐字相同。要改，请先裁 R464。
- 风险三（判据⑥ 的读法，今晚 run10 要看清的那一格）：同一段逐片字，**屏上此刻站着什么**决定它发不发——
  `on_screen` 为空（挂起轮一枚字没交，run9 `chart-01` 那一族）⇒ 逐片帧真上屏；`on_screen` 已含那份正文
  ⇒ 一枚都不发、只进账。分辨它们就看本纸 §3 那行日志括号里的两枚计数：`逐片帧上屏 N 枚 / 屏上已含其字
  而只记账 M 枚`。两枚计数都是**在册键之外**的散文，键集仍旧只有 `session/pieces/cumulative/leg/call/dropped`
  六枚，由 `test_the_window_reading_adds_no_key_nobody_consumes` 按**相等**对判（不是子集）。