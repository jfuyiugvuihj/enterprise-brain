# R548 · 队列道补上 `stream_piece_sink` 的**可注册点**（只做注册那一半，投递面一字不碰）

施工树 `C:\Users\fengx\PycharmProjects\be-r548`，基点 `96946f8`（主树 `codex/data-file-catalog` 现取 HEAD，`--detach` 就地改，**未 commit / 未 git add / 未 push**）。
派工词点名的写域：`deploy/queue_worker.py` ＋ 新钉 `tests/test_r548_*.py` ＋ 反证刀 `tests/test_r548_counter_evidence_teeth.py` ＋ 本纸 `docs/testing/r548-*.md`。

🔴 **读数口径先说死**（本纸所有数字分三类，别混着读）：

- **现取**＝静态层亲自取到（`git` / `rg` / `ast` / `py_compile`），命令原文附在每条后面；
- **实取**＝本机 run10 真机评测窗在 32/105 处按污染线中止、总控下解锁令之后，**本席在自己这棵树里真跑出来的末行读数**；
- **未跑**＝今天仍旧欠着的格——只剩**真机端到端**那一格（判据⑤，§5）。本席不起容器、不打模型、不碰 `scripts/run_gate.py`、不开 `-n`。

解释器（本树没有 `.venv`，系统 Python 缺 `chromadb` 会在 `conftest.py:28` 当场 `ModuleNotFoundError`）：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`。

## 1. 结论一览

```r548-verdict
queue_lane_registrable_point=registered_exactly_once
queue_lane_delivery_face=not_applicable
r524_paper_word_queue_lane=not_applicable_untouched
real_machine_readout=owed_to_run11
commits=zero
```

- **判据① 达成**：队列道报告腿现在有一枚收端（`ReportLanePieceLedger`），由 `_drain_report_stream` 交给编排入口 `run_with_stream` 的同名形参，落到 `config["configurable"]`；**注册点恰一枚**（AST 现取，见 §3），且「逐片交」与「一次投喂一整篇」两族形状可区分（拼起来等值、分片数不等值——钉死了枚数不等，不是只钉「调用发生过」）。 🔴 **实取**：`16 passed, 4 warnings in 14.77s`（其中一格先假红过，修法与红因记在 §9）。
- **判据② 达成**：R524 那枚负向钉**改口而非删除**，逐字对账在 §6；判定规则只严不松（唯一收紧处＝「有注册点就算 connected」那一格今天不再单独算数）。R524 交工纸 `queue_lane=not_applicable` 那一格**一字未改**。 🔴 **实取**：退回改口、只留码 ⇒ `4 failed, 5 passed, 4 warnings in 13.61s`（四枚逐枚点名见 §6.2）；改口落地 ⇒ `9 passed, 4 warnings in 13.43s`。
- **判据③ 达成**：终态帧、`usage`、`sources`、审计行、错误码一字节未动；零外溢钉 ＋ §4 点名的在册邻件共守。🔴 **实取**：§4 那 20 枚合跑 `430 passed, 58 warnings in 68.99s (0:01:08)`／exit=0／**零 failed**。
- **判据④ 达成**：反证刀 **10 把**（下限 5），victim 全部是在册钉本身（14 枚，逐枚点名），摘前摘后 sha256 台账在 §7，末一枚总清点钉（`test_z9` / `z9b` / `z9c`）证明所有在册件回到摘刀前字节。 🔴 **实取**：`17 passed, 4 warnings in 9.44s`——十把刀全部真咬红，`test_z9`/`z9b`/`z9c` 三枚总清点同批绿。
- **判据⑤ 按实交回**：`REPORT_LANE_VIA_QUEUE=on` 的端到端读数**欠着**——本单不许起容器、不许打模型、不许跑端到端。交回结论：**码与牙已就位，欠一次队列道真读数**，挂载见 §5（run11）。

## 2. 判据逐格：命令 → 读数

| 判据 | 命令原文 | 读数（口径） |
| --- | --- | --- |
| ① 注册点恰一枚 | `python -c "import ast;t=ast.parse(open('deploy/queue_worker.py',encoding='utf-8').read());print([(n.lineno,n.func.id,k.value.id) for n in ast.walk(t) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) for k in n.keywords if k.arg=='stream_piece_sink'])"` | **现取**：`[(512, 'run_with_stream', 'stream_piece_sink'), (695, '_drain_report_stream', 'piece_ledger')]` ⇒ 交给编排入口的注册点 **1** 枚；另一枚是本轮账本往 `_drain_report_stream` 下递的搬运，进不了 config，由另一枚钉单独点名（§3） |
| ① 调用点没搬家 | `git grep -n "run_with_stream(" -- deploy/queue_worker.py` | **现取**：1 处命中，行 512，宿主函数 `_drain_report_stream`（494–533）——R524 纸 §4 事实 3 点名的就是这一发 |
| ① 逐字流到收端 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r548_queue_lane_registers_the_piece_sink.py -q -p no:cacheprovider --no-header --basetemp=%TEMP%\r548_bt*` | 🔴 **实取**：`16 passed, 4 warnings in 14.77s`；`test_the_pieces_the_producer_stamps_and_publishes_arrive_in_order` 在内 ⇒ 收端真收到 `ledger.count > 1`、`joined_text() == ANSWER`、`legs == ("export",)`、时间戳单调 |
| ① 与「一整篇」可区分 | 同上（`::test_a_whole_dump_is_distinguishable_from_the_piece_run`） | 🔴 **实取**：该枚在 16 枚里绿 ⇒ `whole_dump.count == 1` 且 `piece_run.count > 1` 且两族 `joined_text()` 等值、`len(pieces)` 不等值。**现取**支撑数：ANSWER 字面量 **152** 字、`CHUNK_SIZE = 18`（`tests/test_r203_sse_progressive_frames.py:52`，152/18 ⇒ 9 次 feed）、三把尺 `20 / 0.1 / 4` 未动（`app/agents/nodes.py:327,329,332`） |
| ② 负向钉不静默放宽 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r524_queue_lane_sends_no_second_character.py -q -p no:cacheprovider --no-header --basetemp=%TEMP%\r548_bt*`，两态各跑一遍 | 🔴 **实取**：改码未改口态 `4 failed, 5 passed, 4 warnings in 13.61s`；改口态 `9 passed, 4 warnings in 13.43s`。四枚红的逐枚红话在 §6.2——比上一席纸上写的「两枚」多两枚，多出来的正是判定规则那一格（§6.1） |
| ③ 零外溢 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r548_queue_lane_registers_the_piece_sink.py -q -p no:cacheprovider --no-header --basetemp=%TEMP%\r548_bt*` ＋ §4 那 20 枚合跑 | 🔴 **实取**：16 passed ＋ 430 passed／exit=0／零 failed。三值返回值 arity 未变；`record` 键集逐字相等（只摘 `duration_ms/trace_id/task_id/request_id`，键集本身不摘）；不交收端时 config 连键都不加。错误码面：`git grep -n "stable_code" -- deploy/queue_worker.py` 现取 rc=1（前后同值），`test_the_worker_still_hands_over_no_new_stable_code` 借在册 `ENUM_CODES` 同尺对判 ⇒ worker 与词表交集仍旧只有 `{"internal_error"}` |
| ④ 反证刀 ≥5 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r548_counter_evidence_teeth.py -q -p no:cacheprovider --no-header --basetemp=%TEMP%\r548_bt*` | 🔴 **实取**：`17 passed, 4 warnings in 9.44s`＝10 把刀（7 把影子回挂＋3 把源文侧/判定侧）＋ 4 枚影子端正控 ＋ 3 枚总清点；`EXPECTED_RED_VICTIMS` 那 14 枚在册钉逐枚真咬红，`SHA_LEDGER` 每行 `before == after` |
| ⑤ 真机那一格 | 见 §5 | **未达·按实交回**：本单不起容器、不打模型、不跑端到端 ⇒ 交回「码与牙已就位，欠一次队列道真读数」，挂 run11 |
## 3. 注册点坐标与 AST 点数证据（全部现取，行号由钉自己在运行时取，不抄进码）

`deploy/queue_worker.py`（工作树 sha256 见 §7 台账）里本单新增的四格，坐标一枚一枚点名：

| 坐标 | 内容 | 性质 |
| --- | --- | --- |
| `:421` | `QUEUE_PIECE_LEDGER_LIMIT = 512` | 本轮账本上限；`test_the_ledger_limit_is_the_same_number_on_disk_and_in_memory` 钉「源文字面 == 运行时读数」，漂开就红 |
| `:424`–`:470` | `class ReportLanePieceLedger`（`__call__` `:443`、`count` `:454`、`legs` `:459`、`joined_text` `:463`） | 收端：按到达顺序原样存片，不合并、不改字、不重排；超上限**只计数不留片**，`count` 把截掉的也算进去（不静默少报） |
| `:473`–`:491` | `def _log_report_lane_pieces` | 唯一外部读数，读点前缀 `[QueueWorker][R548]`；**零枚片 ⇒ 一行都不留**（既有日志面逐字不变） |
| `:494`–`:533` | `def _drain_report_stream`，新增 kw-only 形参 `stream_piece_sink=None`（`:496`） | 默认 None ⇒ 全部既有直调形状不变 |
| **`:512`（关键字写在第 520 行）** | 🔴 **唯一注册点**：`run_with_stream(..., stream_piece_sink=stream_piece_sink)` | AST `Call` 关键字，callee == `run_with_stream` ⇒ 这枚才是能决定 `configurable` 长不长出键的地方 |
| `:664`–`:875` | `def _process_report_lane_turn`：`:693` 造本轮账本 → `:704` 下递 → `:719` 读账本落一行日志 | `:704` 那枚关键字 callee 是 `_drain_report_stream`、value 是 `piece_ledger`，是**搬运不是注册**，由另一枚钉单独点名 |

三枚 AST 钉的分工（`tests/test_r548_queue_lane_registers_the_piece_sink.py`，坐标运行时现取）：

1. `test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call`——`registration_points()` 只数 callee == `run_with_stream` 的关键字，`len(...) == 1`；第二处一起就红（那是第二套口径，不是补格）。宿主函数还须现取等于 `_drain_report_stream`。
2. `test_the_drain_is_the_only_place_the_queue_lane_touches_the_graph`——`run_with_stream(` 全文调用点仍 == 1。
3. `test_the_only_other_handoff_carries_the_round_ledger_down`——全文件同名关键字的 callee 集合恰好是 `["_drain_report_stream", "run_with_stream"]`，且下递那枚 value 必须是 `piece_ledger`；出现第三种就是有人又注册了一遍。

`stream_piece_sink` 这一 token 在该文件的行分布（`git grep -n stream_piece_sink -- deploy/queue_worker.py` **现取**）：`425 / 496 / 502 / 520 / 704`——5 行里只有 `520` 是注册（425、502 是散文，496 是形参，704 是搬运）。

## 4. 判据③ 零外溢：点名邻近在册件复跑清单

本单**未跑**（run10 窗内只写不跑）。收窗后由总控代跑，命令原文（一整条，勿拆）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r548
python -m pytest tests/test_r548_queue_lane_registers_the_piece_sink.py tests/test_r548_counter_evidence_teeth.py tests/test_r524_queue_lane_sends_no_second_character.py tests/test_r524_sink_reaches_both_runways.py tests/test_r524_counter_evidence_teeth.py tests/test_r37_report_lane_worker.py tests/test_r37_report_lane_enqueue.py tests/test_r254_queue_terminal_honesty.py tests/test_r514_queue_worker_passes_dataset_files.py tests/test_r81_queue_terminal_retry.py tests/test_r448_deterministic_refusal_no_retry.py tests/test_r294_principal_freeze.py tests/test_r227_discard_is_honest.py tests/test_r227_lease_heartbeat.py tests/test_r32_lane_contract.py tests/test_r149_sse_text_pieces.py tests/test_r203_sink_reaches_the_leg.py tests/test_r459_supervisor_answer_leg_streams.py tests/test_r464_one_terminal_answer_stream_per_round.py tests/test_r504_terminal_frames_carry_data_filename.py -q -p no:cacheprovider --no-header
```

**预期读数**：exit=0、零 failed；枚数以并树后复跑为准（本纸不写死枚数——按根目录 `AGENTS.md` 的口径，回归判据是同一 HEAD 的复跑互比，不是历史数字）。

每枚邻件守的是哪一格（本单不许动的既有读数）：

- **终态帧 / `usage` / `sources`**：`test_r254_queue_terminal_honesty.py`、`test_r37_report_lane_worker.py`、`test_r37_report_lane_enqueue.py`、`test_r504_terminal_frames_carry_data_filename.py`（现取：这一枚不 import worker，仍列入清单——它守的正是终态帧那一格；总控若要把清单并到 R524 那 36 枚邻件一起跑，取并集即可）。
- **数据集文件下递**：`test_r514_queue_worker_passes_dataset_files.py`——它钉 `_drain_report_stream` 的关键字形状，本单新增的形参是 kw-only 带默认值，不该打到它；打到就是本单的错。
- **错误码 / 重试 / 拒答不重试**：`test_r81_queue_terminal_retry.py`（`ENUM_CODES` 词表就是本单借的那把尺）、`test_r448_deterministic_refusal_no_retry.py`。
- **审计与主体冻结**：`test_r294_principal_freeze.py`、`test_r227_discard_is_honest.py`、`test_r227_lease_heartbeat.py`。
- **跑道契约与逐片道**：`test_r32_lane_contract.py`、`test_r149_sse_text_pieces.py`、`test_r203_sink_reaches_the_leg.py`、`test_r459_supervisor_answer_leg_streams.py`、`test_r464_one_terminal_answer_stream_per_round.py`、`test_r524_sink_reaches_both_runways.py`。
- **R524 的两枚在册件**（含它的反证刀）必须一起跑：本单改了它其中一枚钉的判定函数，K6/K6b 那两把刀量的正是这条规则，任何一侧漂开都该当场红。

全量回归门（并树之后，`-n` 由脚本自选，纸上不写死）：`python scripts/run_gate.py`。🔴 本单未跑。
## 5. 判据⑤ 真机那一格：按实交回，挂进 run11

🔴 **本单不起容器、不打模型、不跑端到端**（主树 run10 真机评测窗内，只写不跑）。交回结论一句话：

> **码与牙已就位，欠一次队列道真读数。** R31 差格 b 的「可注册点」那一半已落地并被钉死；「投递面」那一半仍旧没裁，所以队列道**今天依旧不会往屏上多发一个字**——真机读数要证的不是屏，是 worker 进程内那枚账本确实按序收到了片。

**run11 开窗要读的那一行**（唯一外部读数，`deploy/queue_worker.py:473` `_log_report_lane_pieces`）：

```
[QueueWorker][R548] request_id=<rid> 报告档逐片汇 <N> 枚 / <M> 字 / 腿 <worker 名>[ / 超上限丢弃 <K> 枚]
```

开窗前置（都不在本单写域，交总控执行）：

1. `deploy/.env.server` 里 `REPORT_LANE_VIA_QUEUE=on`——这枚旋钮在 `deploy/.env.server`（本单禁入），且 `env_file:` 在**容器创建**那一刻才解析，`docker restart` 不重读，正解 `docker compose up -d --force-recreate`（根目录 `AGENTS.md` 已钉过这条口径，别按 09-21 runbook P-8 那句旧话走）；
2. 后端容器起来、Redis 在位、模型链路按 R37 报告档准入触发一桩挂起轮；
3. 判据（缺一格就是本单的码有问题，不许含糊过）：
   - 该行出现，且 `N > 1`（逐片，不是整篇）；`腿` 落在 `ANSWER_LEG_STREAM_WORKERS` 那三枚之内（`doc/data/chart`），`worker` 名非空；
   - 客户端侧**读数不变**：入队 SSE 仍旧 `["queued","done"]` 两枚帧、`text` 恒 **0** 枚——这不是回归，是投递面未裁的**预期形状**；谁在这一轮之后把 `queue_lane` 写成 `connected`，R524 那枚对判钉当场红；
   - 终态帧、`usage`、`sources`、审计行、错误码与 run9/run10 同口径逐字对齐（`test_r254_queue_terminal_honesty.py` 在册尺）。

**登记位**：run11 的 readout sheet 今天还不存在，而 `docs/handoff/**`、`docs/testing/run*-readout*`、`docs/api/contract-v1.md` 全在本单写域外，所以这一格**先记在本纸**，由总控抄进 run11 待读清单。

## 6. 判据②：R524 那枚在册负向钉的逐字对账（改口，不是删除，不是静默放宽）

取档命令（先取档再改口，与 R524 那笔同一套程序）：

```powershell
git show 96946f8:tests/test_r524_queue_lane_sends_no_second_character.py
```

| 口径 | 字节 | 行 | EOL | sha256 |
| --- | --- | --- | --- | --- |
| 取档件（`96946f8` blob） | 16434 | 351 | LF | `a7f001431bce2d05e9183694a583cae35df941d74e3b8a1f5ef22ad68b98c605` |
| 改后工作树件（本单交回态） | 20598 | 397 | CRLF（396 枚行终止符；`git ls-files --eol` → `i/lf w/crlf`） | `8f22e08c7873d105a6b3bd07094d8f7b2902232fe28ebbdf4ef49a250c8f347f` |

两枚件的字节/行/EOL/sha256 均由 `git show` 取档＋工作树现读得到（同一枚件在库里是 LF blob、在本机盘上是 CRLF，`core.autocrlf=true` 且仓里没有 `.gitattributes`，所以两个指纹各自记录，别互相冒充）。numstat：`56	10`（56 增 / 10 删）。

### 6.1 改口格一：判定函数 `verdict_for`（原件 `:198`）

改前**逐字**：

```python
def verdict_for(facts: dict) -> str:
    """纸上那一格该写哪个词，由盘面事实决定——不由任何人手填。"""
    if facts["sink_points"] or facts["graph_runs"]:
        return "connected"
    if facts["text_frames"] > 1:
        return "connected"
    return "not_applicable"
```

改后（`tests/test_r524_queue_lane_sends_no_second_character.py:208`）三格变两格，`sink_points` 不再单独算 connected。红/绿对照与「只严不松」的论证：

| 盘面事实 | 改前判 | 改后判 | 性质 |
| --- | --- | --- | --- |
| 这一支跑了图（`graph_runs` > 0） | connected | connected | 不变 |
| 这一支发出第二枚字（`text_frames` > 1） | connected | connected | 不变 |
| `text_frames` ≤ 1 且零枚在场执行 | not_applicable | not_applicable | 不变 |
| **只有注册点、没有收端**（＝R548 落地后的真实盘面） | connected | **not_applicable** | 🔴 **唯一收紧处**——把这种状态写成 connected 正是 R545 那行明令禁止的洗绿 |

`facts["sink_points"]` 这格读数**没被删**：它留在事实表里，由本单 `test_a_dead_registration_alone_does_not_read_as_connected_on_the_enqueue_lane` 反向钉着（注册被人退回 ⇒ 那枚钉红），并由 R524 自己的对判钉 `test_the_paper_word_and_the_tree_agree` 与纸面 `queue_lane=not_applicable` 对判。R524 交工纸 `docs/testing/r524-stream-piece-sink-two-runways.md` 的 ```r524-verdict``` 段**一字未改**（那枚钉读它；改成 `connected` 当场红）。

### 6.2 改口格二：`test_there_is_no_place_on_the_queued_lane_to_register_a_sink`（原件 `:275`）

改前**整枚逐字**：

```python
def test_there_is_no_place_on_the_queued_lane_to_register_a_sink():
    """派工词说「queued_response 不注册 sink，与 a 同族」；本钉把这句话钉成机器事实。"""
    enqueue = _function_source(chat, "_enqueue_ask_turn")
    assert "stream_piece_sink" not in enqueue
    assert _sink_registration_points() == [], _sink_registration_points()
```

🔴 **当场红形（实取，解锁令后本席亲跑）**：把本席对 `tests/test_r524_queue_lane_sends_no_second_character.py` 的改口退回
（`git restore --source=HEAD -- tests/test_r524_queue_lane_sends_no_second_character.py`）、只留 `deploy/queue_worker.py` 的改动，
跑 §2 那一行点名的命令 ⇒ **`4 failed, 5 passed, 4 warnings in 13.61s`**。四枚逐枚（坐标取 `96946f8` 那份未改件）：

| 枚（原件坐标） | 红话（现抄自 stderr） | 归因 |
| --- | --- | --- |
| `test_there_is_no_place_on_the_queued_lane_to_register_a_sink`（`:279`） | `AssertionError: ["deploy/queue_worker.py:425", "deploy/queue_worker.py:496", "deploy/queue_worker.py:502", "deploy/queue_worker.py:520", "deploy/queue_worker.py:704"]`／`assert ["deploy/queu...orker.py:704"] == []` | 注册点已经在了，那 5 行正是 §3 里 `git grep -n` 现取的同一串 |
| `test_the_real_hook_for_the_queue_lane_is_outside_this_ticket_write_domain`（`:292`） | `assert "stream_piece_sink" not in """"..."` | 同一格从 worker 源文那一路红：token 已在这本源文里 |
| `test_the_paper_word_and_the_tree_agree`（`:302`） | `assert "connected" == "not_applicable"` | 🔴 旧判定规则会把这一格写成 `connected`，而客户端一个字都收不到——正是 R545 明令禁止的那一种洗绿 |
| `test_a_forged_paper_word_goes_red`（`:315`） | `assert "connected" == "not_applicable"` | 🔴 旧规则下「把纸偷写成 `connected`」再也抓不到 ⇒ 那枚防伪牙当场变成**死牙** |

🔴 上一席纸上写「应当两枚红」，**实取是四枚**：多出来的两枚都红在判定规则那一格（§6.1），这把「`verdict_for` 必须与注册点一起改口」
钉成了事实而不是修辞。跑完立刻把改口件复制回树里并复核 sha256 = `8f22e08c7873d105a6b3bd07094d8f7b2902232fe28ebbdf4ef49a250c8f347f`
（已逐字节复验一致）；改口态复跑 ⇒ `9 passed, 4 warnings in 13.43s`。

改后更名为 `test_the_enqueue_exit_still_registers_no_sink__r548_moved_the_hook_to_the_worker`（`:295`），强度只升：入队出口那一半断言原样留着（`stream_piece_sink not in enqueue`），新加两格——`app/` 侧必须零命中、`deploy/queue_worker.py` 侧必须非空。旧名那枚钉被人恢复（＝注册退回）同样红。

### 6.3 改口格三：`test_the_real_hook_for_the_queue_lane_is_outside_this_ticket_write_domain`（原件 `:282`）

改前**最后两条断言逐字**：

```python
    hits = [n for n, line in enumerate(worker.splitlines(), 1) if "run_with_stream(" in line]
    assert len(hits) == 1, hits
    assert "stream_piece_sink" not in worker
```

🔴 **当场红形（实取）**：`assert "stream_piece_sink" not in ...`，位置取档件 `:292`（整行读数见 §6.2 那张表第二行）。改后更名为
`test_the_real_hook_for_the_queue_lane_is_now_registered__r548`（`:320`），最后一条**反了个方向**并多钉一枚枚数：

```python
    assert "stream_piece_sink" in worker
    assert worker.count("stream_piece_sink=stream_piece_sink,") == 1
```

改前那条原文逐字留在该钉 docstring 里（历史读数一字未改，只改结论）；件名与「本件不 import 也不改 worker」的纪律都留着——它现在只读源文。两枚在册负向钉的本事没缩水：**入队侧一字未松、worker 侧从「零枚」翻成「有且只在 deploy 下」**。

### 6.4 偏差登记（照实写在纸上，不藏）

- R524 交工纸 §4 的**事实 3**（「`deploy/queue_worker.py` 里 `stream_piece_sink` 0 命中，现取 `git grep -c` → rc=1」）与 `git grep -c stream_piece_sink -- deploy/queue_worker.py` 的**今天读数**（rc=0，5 行命中）已经漂开；`docs/handoff/2026-09-15-orchestration-board.md:6040` 那格手抄读数同源陈旧。三处都在本单写域外（`docs/testing/r524-*.md`、`docs/handoff/**`），**交总控落笔**，本单不自行动别人的纸。
- `tests/test_r459_supervisor_answer_leg_streams.py:519` docstring 里「没注册出口的道（队列…）」那句散文同样陈旧；断言不因此红，但登记在册，仍属他人写域，交总控。
- 本单**不碰投递面契约**：`docs/api/contract-v1.md`（在途 Kuhn/R523 写域）一字节未改，`app/api/v1/chat.py`（在途 Euler/R536）一字节未改。R545 那行同族的「失败终态与原因码」那一半本单**没做也不该做**——那是另一枚单。
## 7. 判据④：反证刀十把 ＋ sha256 台账

件：`tests/test_r548_counter_evidence_teeth.py`（17 枚用例：7 把走「影子回挂」＋ 3 把走源文侧/判定侧 ＋ 4 枚影子端正控 ＋ 3 枚总清点）。机械口径照 R524 的先例：摘刀一律在**内存影子**里做——被跟踪件源文在 import 那一刻抄进 `TEXT_AT_IMPORT`，按锚点改一格（命中数 `!= 1` 当场红 ⇒ 死牙不算牙），写进 `tmp_path` 的影子副本，再 `exec` 到模块**活的那本 `__dict__`**（不是 `dict(vars(module))` 的副本——victim 钉跑起来还要 `monkeypatch` 别的模块属性，副本 globals 会让影子看不见那些补丁 ⇒ 正控与摘刀量的就不是同一条链）。仓里一字节不动。

🔴 **与 R524 同一格偏差，写在纸上而不是藏起来**：派工词那句「摘注册 ⇒ 端到端一枚红」里的「端到端」在这一支仍旧取不到真机形态——投递面没裁，客户端没有一条活着的外发流可收片（凭据 §5）。本单交的是**进程内端到端**：真 `run_with_stream` 把出口塞进 config、真 `nodes.publish_stream_pieces` 盖章交片、真 `queue_worker.process_one()` 把这一轮跑完并发布。K1 摘掉注册，红的就是这条链上的钉。

| 刀 | 摘形（锚点 → 替形，全部现取唯一） | 机械 | 影子端正控 | victim（在册钉本身） | 预期红形要点 |
| --- | --- | --- | --- | --- | --- |
| **K1** | `:520` 那一行注册关键字 → 一枚留着当纪念的注释 | 影子回挂 `_drain_report_stream` | `test_k1_positive_control_...` | `test_the_registered_sink_reaches_the_graph_configuration` | 红在 `KeyError: 'stream_piece_sink'`——config 里那枚键不再长出；源文侧同时验 `registration_points() == []`，证明定罪格读 AST 不读注释 |
| **K1b** | 整本源文里 `stream_piece_sink` → `piece_sink_detached_by_r548_teeth`，写进 `tmp_path` 影子文件后把 R524 件的 `WORKER_PATH` 指过去 | 源文侧（R524 K6b 同族） | — | `test_the_real_hook_for_the_queue_lane_is_now_registered__r548`、`test_the_enqueue_exit_still_registers_no_sink__r548_moved_the_hook_to_the_worker` | 两枚改口钉一起红 ⇒ 证明本单对 R524 的改口**不是把断言写死成永远绿**：盘面退回没有注册点的那一刻，它们立刻跟着退回红 |
| 直调亲手取到 `NameError: name "stream_piece_sink" is not defined`；后台那一路被 `_process_report_lane_turn` 收成 error 日志（既有行为），所以两枚在册钉分别红在 `KeyError: "config"` 与「收端没进 config」——两半都得在册（§9.2）
| **K3** | 收端 `__call__` 里 `:448`–`:449` 那两行（`if len(self.pieces) < self.limit:` ＋ `self.pieces.append(piece)`） → 前置一段「并成一枚」的写法（拼起来仍旧等值，分片数被抹平） | 影子回挂 `ReportLanePieceLedger` | `test_k3_positive_control_the_ledger_keeps_the_pieces_apart` | `test_a_whole_dump_is_distinguishable_from_the_piece_run`、`test_the_pieces_the_producer_stamps_and_publishes_arrive_in_order` | 红在 `assert 1 > 1`——派工词点名的「可区分性」那一格的真牙：钝化成整篇投喂，判据① 当场塌 |
| **K4** | `:480` 零片闸门 `if not ledger.count: return` → `if ledger.count >= 0: return`（永不留行） | 影子回挂 `_log_report_lane_pieces` | 同 K4 前置 `k4_control` | `test_a_round_that_flowed_pieces_leaves_exactly_one_readout_line` | 摘了 §5 那枚真机读点就没得读——「流到字就恰有一行」那枚红 |
| **K4b** | 同一格反向钝化 → `if ledger.count < 0: return`（每轮都留行） | 影子回挂 | — | `test_a_quiet_round_adds_not_a_single_readout_line` | 既有日志面被污染：没流到字的轮次也留行 ⇒ 反向那枚红（证明 K4 不是单向死牙） |
| **K5** | `:533` 那行 `return final_answer, agent_results, stream_error` → 前置一段「把片拼进正文」的写法 | 影子回挂 `_drain_report_stream` | `test_k5_positive_control_the_published_readings_are_still_quiet` | `test_the_published_readings_do_not_move_when_pieces_flow` | 判据③ 零外溢的真牙：片一旦参与正文，终态那一层读数就动——本单的绿不是靠「没人读这格」换来的 |
| **K6** | 把 `verdict_for` 退回改前那条「存在注册点就算 connected」 | 判定侧（monkeypatch 规则，纸一字节未改） | `assert verdict_for(facts) == "not_applicable"`（进刀前先站一遍绿） | `test_the_paper_word_and_the_tree_agree`（R524 在册对判钉）、`test_a_dead_registration_alone_does_not_read_as_connected_on_the_enqueue_lane` | 红话含 `connected != not_applicable`——判据② 的「只严不松」由这一把证 |
| **K7** | 收端 `:451` 那行 `self.overflow += 1` → `pass`（超限静默吞片） | 影子回挂 `ReportLanePieceLedger` | `test_k7_positive_control_the_ledger_counts_its_overflow` | `test_the_ledger_counts_pieces_it_cannot_keep` | 「收端到底收到几枚」重新变成看不见的东西 ⇒ 那枚诚实计数钉红 |
| **K8** | 整本源文里 `stream_piece_sink` → `piece_sink_detached_by_r548_teeth`（等于 R548 从未落地），喂给 `nail.worker_source` 的读数 | 源文侧（不 exec） | — | `test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call`、`test_the_only_other_handoff_carries_the_round_ledger_down` | 两枚 AST 钉本身一起红——红的是钉，不是钉旁边的注释 |

派工词点名的正面等价物：**K1**（摘注册 ⇒ 判据① 那枚红）、**K3**（收端钝化成整篇 ⇒ 可区分性那枚红）、**K5**（片漏进发布面 ⇒ 零外溢那枚红）。下限 5 把，本单交 10 把。

### 7.1 sha256 台账（**现取**，进门指纹）

`_record(tag, path, before, after)` 每把刀进刀前后各核一次被跟踪件的 sha256，逐条记进 `SHA_LEDGER`；因为摘刀只作用在内存副本，**每一行都必须 `before == after`**，否则就是刀在被跟踪件上留了写口（`_record` 当场 assert）。总清点三枚：`test_z9`（十把刀各有记录、点名在册钉全真咬红、影子刀全真摘过）、`test_z9b`（六枚被跟踪件仍是进门那一刻的字节 ＋ 仓里不许有影子散件）、`test_z9c`（纸上这枚 worker 指纹与盘面现读一致——纸一个数、盘另一个数就红）。

| 被跟踪件 | 进门 sha256（＝每把刀台账里的 before/after） |
| --- | --- |
| `deploy/queue_worker.py` | `03be6d53ea728d329d9a214b0992d76b921bc10143928d5bab5aae4789502b4d` |
| `tests/test_r548_queue_lane_registers_the_piece_sink.py` | `7f98aaf975e660ad5127900a61062b318c8afda98c13910c0c0af0d41ac22eb3`（§9.1 修完之后；修前 `9c339f69…`，21971→23076 字节） |
| `tests/test_r524_queue_lane_sends_no_second_character.py` | `8f22e08c7873d105a6b3bd07094d8f7b2902232fe28ebbdf4ef49a250c8f347f` |
| `app/agents/nodes.py`（本单未碰） | `657c8f30767b7e4c188887ecafefb3f21255efd884885f4d20fc729e603834d6` |
| `app/agents/orchestrator.py`（本单未碰） | `36def47b87a9d2e67269e863e6f3b1c5cd197b9c9ff0675fdc4f0004d1dde822` |
| `docs/testing/r548-queue-lane-piece-sink-registration.md` | 🔴 自指不能落在自己纸上：本纸的进门指纹由 `test_z9b` 在 import 那一刻抄进 `FINGERPRINT_AT_IMPORT`，跑起来时逐字节复核；交回消息里另附一枚给总控。 |
| 反证刀件自身（不在 `TRACKED`，另记） | `3d6697ae3c5c480a5b24f2f900389e689316997c88a932fb099ab629e0e6ed39`（§9.2 修完之后；修前 `39bd6836…`，22527→23583 字节） |

## 8. 交工、未达格、风险

### 8.1 改动（`git -C C:\Users\fengx\PycharmProjects\be-r548 diff --numstat` 原样）

```
94	1	deploy/queue_worker.py
56	10	tests/test_r524_queue_lane_sends_no_second_character.py
```

未跟踪新增两枚：`tests/test_r548_queue_lane_registers_the_piece_sink.py`（16 枚用例）、`tests/test_r548_counter_evidence_teeth.py`（18 枚用例）＋ 本纸。**零 commit / 零 `git add` / 零 push / 零分支。**

EOL 与编译（**现取**）：`git ls-files --eol -- deploy\queue_worker.py tests\test_r524_queue_lane_sends_no_second_character.py` → 两枚都 `i/lf w/crlf`；两枚新件逐字节 `CRLF == 行数`（主钉 467、刀件 434——§9 那两笔修法各加长了一段，上一版纸上写的 446 / 412 已按现读改写），无 BOM；四枚 .py 全部 `py_compile` 过（产物写进 %TEMP%，不落仓）。🔴 `deploy/queue_worker.py` 从开窗到现在一字节没动（`03be6d53…` 三次现读同值）。

### 8.2 解锁令后本席已跑（run10 于 32/105 中止之后）

| 批次 | 命令原文（解释器统一用主树 venv，见 §9.3） | 末行读数 |
| --- | --- | --- |
| 主钉 16 枚 | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r548_queue_lane_registers_the_piece_sink.py -q -p no:cacheprovider --no-header --basetemp=%TEMP%\r548_bt4` | `16 passed, 4 warnings in 14.77s` |
| 反证刀 17 枚 | 同上，文件换 `tests/test_r548_counter_evidence_teeth.py`（`--basetemp=%TEMP%\r548_bt6`） | `17 passed, 4 warnings in 9.44s` |
| 判据② 红形（改码未改口态） | 同上，文件换 `tests/test_r524_queue_lane_sends_no_second_character.py`（`--basetemp=%TEMP%\r548_bt9`） | `4 failed, 5 passed, 4 warnings in 13.61s` |
| 判据② 改口态 | 同上（`--basetemp=%TEMP%\r548_bt10`） | `9 passed, 4 warnings in 13.43s` |
| §4 那 20 枚邻件合跑 | §4 那条命令原文，前面加同一枚 venv 解释器（`--basetemp=%TEMP%\r548_bt8`） | `430 passed, 58 warnings in 68.99s (0:01:08)`／exit=0／零 failed |
| 终盘合跑（纸定稿之后） | `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r548_queue_lane_registers_the_piece_sink.py tests/test_r548_counter_evidence_teeth.py -q -p no:cacheprovider --no-header --basetemp=%TEMP%\r548_bt12` | `33 passed, 4 warnings in 15.02s`（16＋17，证明上面那两行数字对应的是**现在这版盘面上的字节**） |

🔴 仍然**未跑**：`python scripts/run_gate.py` 全量门（本席受令不碰）、真机端到端（§5）。主树复跑与代提交归总控；并树硬序见 §8.4 那句成对回退。

### 8.3 未达格差的确切条件

| 格 | 差什么 | 补齐要动的写域（本单禁入） |
| --- | --- | --- |
| 判据① 的「交付」那一半 | 片只进本轮 worker 内存账本，客户端一个字都收不到 | 轮询面加增量读数、或新起一条 tail SSE ⇒ 要先裁 `docs/api/contract-v1.md`（在途 R523/Kuhn）＋ `frontend/**` |
| 判据⑤ 真机读数 | 一次 `REPORT_LANE_VIA_QUEUE=on` 的队列道真读数（读 `[QueueWorker][R548]` 那一行） | 需要一台安静机器开一个窗：起容器、打模型——本单硬禁，挂 run11（§5） |
| 判据② 的红形复现 | **已实取**：改码未改口态 4 枚红、改口态 9 枚绿（§6.2） | 无缺口。比上一席纸上「两枚红」多两枚，多出的正是 §6.1 那格判定规则 |
| R524 纸/看板散文陈旧三处 | §6.4 点名的三处手抄读数 | `docs/testing/r524-*.md`、`docs/handoff/2026-09-15-orchestration-board.md`、`tests/test_r459_*.py:519` 均非本单写域，交总控落笔 |

### 8.4 风险（不粉饰）

- **注册之后队列道的模型调用会按 R203/R459 既有准入从 `invoke` 改走 `stream`**——这是「接上」的必然，不是本单新加的开关，也不是本单放宽的准入；`ANSWER_LEG_STREAM_WORKERS` 那三枚未动，`test_the_worker_still_hands_over_no_new_stable_code` 与 R459/R203 在册件共守。若总控判定「报告腿连走法都不许变」，撤回必须是**码＋两枚新件＋R524 改口三件成对**，只回退测试件会把盘面留成红的（R524 §5.1 同一口径）。
- **账本上限 512 枚片**：超出只计数不留片、日志如实带「超上限丢弃 K 枚」，不静默。真要跨轮攒片（例如给 tail SSE 做 backlog），本设计明确不做——它只活一轮，随 `process_one()` 退掉。
- **本单没有真机读数**，任何「队列道逐字流式已可用」的表述都是假话：今天成立的只有「worker 进程里有了可注册点，且它收到的确实是一串而不是「一坨」」。


## 9. 解锁后第一手跑出来的三笔（不粉饰：前两笔都是本席自己的牙有病，不是产品码）

### 9.1 零外溢那枚主格先假红过（判据③）

首跑读数：`1 failed, 15 passed, 4 warnings in 16.38s`，红在 `test_the_published_readings_do_not_move_when_pieces_flow`，
红话 `AssertionError: <zip object at 0x00000219BE3C0240>`——本席把 `zip(...)` 当断言消息写了，等于没写消息。真正的两格原因是比对口径太粗：

1. 日志行里带着每轮必变的裸 `request_id`（`uuid4().hex`），两枚轮的 `[QueueWorker] 处理中 request_id=<rid>: …` 天生不同；
2. `[ASK] 来源事件缺少可用检索范围: code=authorization_unavailable` 这类**进程内一次性告警**只在本进程头一轮吐，先跑的 quiet 轮因此比后跑的 flowed 轮多两行。

修法（**只动钉，产品码一字节未动**）：加 `_normalized_log_lines()`——摘掉本单读点前缀，再把 `\b[0-9a-f]{32}\b` 归一成 `<id>`；
两枚被测轮之前先跑一枚**丢弃轮**把一次性告警榨干；断言先比枚数再比内容，消息交回 `(quiet_lines, flowed_lines)`。修后 `16 passed`。

🔴 这不是放宽：终态 `status`、`result`、`terminal`、`record` 键集与逐条值、会话历史仍旧逐字比，日志面仍旧逐行比——只是不许拿「本轮是哪一枚请求」当判据。
K5（让片漏进正文）修后照样咬红（在那 `17 passed` 里），证明这枚牙没被钝化。

### 9.2 刀 K2 的红因与纸上写的不一样（判据④）

纸面预期「摘形参 ⇒ 真跑红在 `NameError`」。实取：`_process_report_lane_turn` 把后台异常收成 error 日志（在册行为，本单没动它），
于是 victim 从发布面看到的是 `KeyError: "config"`——`NameError` 被吞在上一层。K2 已改成两手都点名：直调亲手取那枚 `NameError`
并断言其消息含 `stream_piece_sink`，再要求两枚在册钉分别红。修后 `17 passed`。

顺带记一笔给 run11 判读用：这层吞异常是**既有产品行为**——若报告腿在 `_drain_report_stream` 之前就炸，日志里只有 `报告档后台执行异常: …`，
**不会**有本单那行 `[QueueWorker][R548]`。所以「没看到那行」不能直接读成「注册没生效」，要先看有没有那枚异常行。

### 9.3 环境（下一位执行层少踩一步）

- 本工作树没有 `.venv`，系统 Python 缺 `chromadb` ⇒ `conftest.py:28` 当场 `ModuleNotFoundError: No module named "chromadb"`；一律用主树 venv 解释器。
- `--basetemp` 指到 `%TEMP%` 下，影子与日志散件都不落仓；`__pycache__` 由 `.gitignore` 兜住，交回前 `git status --porcelain` 复核仍是五项。
- 🔴 `docs/handoff/2026-09-15-orchestration-board.md` 里有 3 处**裸 CR** 换行：用 `python .splitlines()` 数行号会比 `rg`/`git` 的换行计数多 3 格。那枚 R524 bullet（「无可注册点」那句）在 `rg` 口径是 **:6040**，splitlines 会读到 :6043——总控落笔按 :6040。
- 本席自曝一笔：第一版补丁脚本把 CRLF 拼成了字面 `\r\n` 四字符，整本纸被压成一枚长行（261 枚字面标记）。已按字面标记还原并重验 `crlf == 行数`；这条只影响纸，码与两枚新件从未被那次写入碰到。
