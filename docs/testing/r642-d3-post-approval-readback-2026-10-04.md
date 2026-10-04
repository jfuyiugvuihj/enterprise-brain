# R642 · D-3 那半格：批准之后必须再读一次 `/queue/status`（2026-10-04）

一句话结论：**D-3 缺的不是产品结论，是一次读。**`run21b` 那 8 枚队列态读数读的是挂起那一刻的快照，批准动作发生在快照之后，量具一步都没回头再读 ⇒ 那 8 枚只能判「未量到」。本单把「批准之后再读一发」这一格补进量具（默认关的开关 + 一发 GET + 账上一格新读数 + 一把八枚读数的分类器），🔴 一字节产品码都没动，帧账一行的键集一格都没多，拿不到证词的每一枚都记 `None` 而不是 0。

本单零容器、零连库、零模型、零端口。仓库内产物＝这份纸 + `scripts/eval_transport_ask_v2.py` 的改动 + `tests/test_r642_post_approval_terminal_readback.py`。

## 0. 取证面（全部只读，本席现取）

- 原料：`%TEMP%\evalrun\run21b-sidecar-frames.jsonl`（**12 行**＝报告档子集，🔴 不是全量窗）、`run21b-sidecar.jsonl`（4,300 B）、`run21b-answers.jsonl`（140,952 B）、`run21b.shards.json`、`run21b.window.json`。全量窗原料是 `run18`／`run19`／`run20k`（各 105/106 行），本单的对照表**只用 12 行那一本**，因为在册那 8 枚挂起读数就在这一本上。
- 读数件（只读引用，🔴 不在本单写域）：`scripts/eval_lane_readout.py::D-3 出处随答案`那一段。
- 在册尺（只读引用）：`tests/_r259_queue_ruler.py::sources_cell`、`tests/_r259_queue_ruler.py::FRAME_ROW_KEYS`、`tests/test_r259_terminal_readout_lands_in_the_book.py`。
- 参考面（总控 10-04 18:4x 亲取，本单不复现）：7 枚容器 healthy；`backend|worker|scheduler` 内 `MODEL_CONTEXT_TOKENS=8192`／`VECTOR_DUAL_WRITE=on`／`REPORT_LANE_VIA_QUEUE=off`。

## 1. 病灶（为什么那 8 枚只能判「未量到」）

`run21b-sidecar-frames.jsonl` 那 12 行的账上形状，本席现读：

- 4 枚 `kind=queued_polled`：`queue.terminal.state=answered`，`sources_n=14/0/13/0` —— 这一族**没有批准轮**，快照就是终态，读数合法。
- 8 枚 `kind=queued_approved`：`queue.terminal.state` 全是 `awaiting_approval`、`sources_present` 全是 `false`、`sources_n` **全是 0**，账上没有 `post_approval` 这一格。

那枚 0 说的是「挂起的时候当然还没有出处」，不是「批准后出处为零」。批准腿确实把出处交回来了 —— 同一批题在 `run21b-sidecar.jsonl` 上的 `evidence_n` 是 8/14/5/14/5/10/0/9（八枚里七枚非零）。🔴 所以 D-3 欠的只是**批准后那一次终态载荷读数**，本单也因此**没动 evidence 那条腿**（`payload["evidence"]` 一字未改）。

机制在码上是清楚的：`_poll_queue` 读到 `awaiting_approval` 就停表（R259 治白烧那一刀），`transport` 随后把批准轮走到终答（R447 判据①），却一次都没回头读那枚载荷。

## 2. 改了什么（四处，全在量具一侧）

1. **开关**：`POST_APPROVAL_READBACK_ENV = "EVAL_POST_APPROVAL_READBACK"`，经 `_lane_switch` 读表（与 R632 那两枚同一族口径：import 期读一次，一窗之内不重读）。🔴 **缺省关**。
2. **那一发读**：`_read_queue_terminal(request_id)` —— 只一发 GET，不循环、不睡表、一枚 `time.time()` 都不多读，也不复用 `_poll_queue` 那把轮子（停表词表与读表次数一字未动）。
3. **那一格账**：`POST_APPROVAL_CELL_KEY = "post_approval"`，🔴 嵌在 `queue` 那一格**里面**，帧账一行顶层一列都不许多（`tests/_r259_queue_ruler.py` 明文那条纪律）。三次读数一起留档：`read`（有没有读到载荷）／`outcome`（哪一形失败）／`terminal`（`_terminal_readout` 折出来的槽位）。快照那一格 `queue.terminal` 一个字不改 ⇒ 两次读数都在账上，谁也不冒充谁。
4. **那一枚分类器**：`post_approval_sources_readback(row)` 交回八枚互不冒充的读数（下表），`sources_n` 只在三枚读数下才是真数，其余五枚一律 `None`。`summary()` 多发布一格 `post_approval_readback: on|off`，关着就写在盘面上。

| 读数 | 含义 | `sources_n` | 触发形状 |
|---|---|---|---|
| `read_some` | 批准后终态真交回 N 枚出处 | 真数 N>0 | `read=true` 且形状 `structured` 且 `sources_error` 空 |
| `read_zero` | 批准后**成功**而出处为零 | 真数 0 | 同上，N=0 |
| `not_computable` | 服务端明说出处没算成 | 真数（随行） | `sources_error` 非空 |
| `row_cannot_say` | 那一行说不出自己有没有出处 | `None` | 形状 `legacy`／`no_keys`，或 `sources_n=None` |
| `readback_unreadable` | 那一发没读到载荷／送回的不是终态 | `None` | `read=false` 或形状 `not_terminal` |
| `still_parked` | 批准后那一发读回的还是挂起态 | `None` | `terminal.state=awaiting_approval` |
| `no_readback` | 打了批准轮而账上没有批准后终态 | `None` | 缺那一格（历轮原件、开关关着的窗） |
| `not_applicable` | 这一题压根没打批准轮 | `None` | `kind` 不在 `APPROVAL_ROUND_KINDS` |

`still_parked` 是本席在写判据时**现取逼出来的一枚**：拿假出口把「批准后第二发仍送回挂起载荷」那一形喂进分类器，它当初读成了 `read_zero` —— 正是本单要治的那枚假零换了个入口回来。补了这道 guard（状态词与 `_poll_queue` 停表那一条同源，不另起第二把尺）之后，那一形读成 `still_parked`/`None`，方向只变严。常驻牙：`test_a_readback_that_is_still_parked_is_not_read_zero` + 分类器对判表里那枚 `readback-still-parked`。

## 3. 判据① · 改前／改后对照（同一本 run21b 原料，两遍）

命令原文（离线，只读原料；件在 `%TEMP%\r642\d3_before_after.py`）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r642
git show 2103890:scripts/eval_transport_ask_v2.py > $env:TEMP\r642\head_instrument.py
.\.venv\Scripts\python.exe $env:TEMP\r642\d3_before_after.py
```

两遍的差别＝**读法两遍**：改前那遍用在册尺 `sources_cell(row["queue"])`（它只会读 `queue.terminal`，而那一格定格在挂起快照上）；改后那遍用 `post_approval_sources_readback(row)`。原料同一本、一个字节没动。

先交能力差（同一枚 `hasattr` 现读三份件）：

```
改前的量具有没有「批准后重读」这项能力： [False, False, False]
改后的量具： [True, True, True]
改后开关缺省值 RECORD_POST_APPROVAL_TERMINAL = False
```

（三枚名字＝`_read_queue_terminal`／`post_approval_sources_readback`／`POST_APPROVAL_CELL_KEY`。）

12 行逐枚对照（`快照` 那一列是账上原文，非新读数）：

| id | kind | 快照 state/n | 改前读数 | 改前 n | 改后读数 | 改后 n |
|---|---|---|---|---|---|---|
| report-01 | queued_polled | answered/14 | `read_some` | 14 | `not_applicable` | `None` |
| report-02 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-03 | queued_polled | answered/0 | `read_zero` | 0 | `not_applicable` | `None` |
| report-04 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-05 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-06 | queued_polled | answered/13 | `read_some` | 13 | `not_applicable` | `None` |
| report-07 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-08 | queued_polled | answered/0 | `read_zero` | 0 | `not_applicable` | `None` |
| report-09 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-10 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-11 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |
| report-12 | queued_approved | awaiting_approval/0 | `read_zero` | 0 | `no_readback` | `None` |

读数差（现取原文）：

```
改前读数分布： {'read_some': 2, 'read_zero': 10}
改后读数分布： {'not_applicable': 4, 'no_readback': 8}
```

逐枚点名「哪枚为什么拿不到」——八枚 `report-02/04/05/07/09/10/11/12` 拿不到的原因是同一件事，🔴 不是八枚不同的故障：

```
  report-02   queued_approved  -> no_readback  sources_n=None  打了批准轮而账上没有批准后终态 ⇒ 未量到，不许读成零枚出处
  report-04   queued_approved  -> no_readback  sources_n=None  （同上）
  report-05   queued_approved  -> no_readback  sources_n=None  （同上）
  report-07   queued_approved  -> no_readback  sources_n=None  （同上）
  report-09   queued_approved  -> no_readback  sources_n=None  （同上）
  report-10   queued_approved  -> no_readback  sources_n=None  （同上）
  report-11   queued_approved  -> no_readback  sources_n=None  （同上）
  report-12   queued_approved  -> no_readback  sources_n=None  （同上）
```

为什么是这一枚读数而不是别的：`run21b` 那扇窗收在**本单开关装上之前**，量具当时没有能力打那一发重读，账上压根没有 `post_approval` 这一格。🔴 那一格不存在 ≠ 批准后出处为零，也 ≠ 读失败 —— 它只能是 `no_readback`。四枚 `queued_polled` 读成 `not_applicable` 也是同一件事的另一半：它们没打批准轮，快照就是终态，D-3 在它们身上照旧用 `sources_cell` 读，本单不拿「不适用」去顶掉合法读数。

合格线核对：八枚从「未量」（被折成 `read_zero` 的那枚假零）变成分明的**诚实 `None`**，逐枚有名有因。🔴 「变绿」这一形在本表里不存在：没有任何一枚改后被读成 `read_some`/`read_zero`。

## 4. 「量到」那一支今天能不能走到（假出口演示，🔴 非 run21b 读数）

命令原文（同一件的第二段；件在 `%TEMP%\r642\d3_full.py`）：

```powershell
.\.venv\Scripts\python.exe $env:TEMP\r642\d3_full.py
```

现取读数（假出口＝`tests/_r259_queue_ruler.py::Transport`，一题走「入队 → 读到挂起 → 批准到终答 → 批准后重读」）：

```
开关=off : 状态读几发=1 kind=queued_approved 快照state=awaiting_approval 快照n=0 批准后那一格=不存在
          读数=no_readback sources_n=None
开关=on  : 状态读几发=2 kind=queued_approved 快照state=awaiting_approval 快照n=0 批准后那一格=在位
          读数=read_some sources_n=3 note=批准后终态真交回 3 枚出处 | 交回正文=26 字
          那一格原文={"read": true, "outcome": "read", "terminal.state": "answered", "terminal.sources_present": true, "terminal.sources_n": 3}
```

这一段只证明「量到」那一支真能走到、开关开着才多那一发；数字来自假出口夹具，🔴 不许当成任何一扇窗的读数。**真机读数由总控在 run22／D 相 2 的窗里取。**

八枚形状一次跑全（同件第四段重做，件在 `%TEMP%\r642\d3_shapes.py`；注入走在册假出口的正规入口 —— `statuses` 列表里的 `BaseException` 会被直接抛出，🔴 不改在册件、不 monkeypatch 它的实例）：

```powershell
.\.venv\Scripts\python.exe $env:TEMP\r642\d3_shapes.py
```

现取读数（同一本假出口，开关一律开着；「快照」那一列证明挂起快照在八枚形状里一次都没被顶掉，也没被拿来冒充批准后终态）：

```
  批准后那一发 HTTP 500    read=False outcome=http_500         shape=not_terminal  -> 读数=readback_unreadable    sources_n=None  | 快照仍=awaiting_approval/0
  批准后那一发连不上          read=False outcome=URLError         shape=not_terminal  -> 读数=readback_unreadable    sources_n=None  | 快照仍=awaiting_approval/0
  批准后那一发解不成对象        read=False outcome=JSONDecodeError  shape=not_terminal  -> 读数=readback_unreadable    sources_n=None  | 快照仍=awaiting_approval/0
  批准后那一发仍是挂起态        read=True  outcome=read             shape=structured    -> 读数=still_parked           sources_n=None  | 快照仍=awaiting_approval/0
  批准后读到 legacy 旧行    read=True  outcome=read             shape=legacy        -> 读数=row_cannot_say         sources_n=None  | 快照仍=awaiting_approval/0
  服务端说出处没算成          read=True  outcome=read             shape=structured    -> 读数=not_computable         sources_n=0     | 快照仍=awaiting_approval/0
  批准后成功而出处为零         read=True  outcome=read             shape=structured    -> 读数=read_zero              sources_n=0     | 快照仍=awaiting_approval/0
  批准后真交回三枚出处         read=True  outcome=read             shape=structured    -> 读数=read_some              sources_n=3     | 快照仍=awaiting_approval/0
```

读这张表的三条口径，逐枚都对得上：拿不到证词的五枚（前三枚 + `still_parked` + `row_cannot_say`）`sources_n` 一律 `None`，🔴 一枚都没被折成 0；只有后三枚才是真读数；`still_parked` 那一枚是「载荷交回了 0 而本单仍不读成零」的唯一一格 —— 它读的就是账上那枚诱饵零，被 guard 拦在门外（§2 末段）。常驻牙同名四路：`test_a_failed_readback_is_none_never_zero_and_never_the_snapshot`（`http-503 / connection / undecodable / not-object`）。

顺手记一条取证时的自撞：第一版注入想把假出口的 `__call__` 换成会抛 500 的那一枚，**没生效** —— Python 解析 `__call__` 走的是类型而不是实例（跟进单 §命令通道那族「以为改了其实没改」的又一枚）。改走 `statuses` 里塞 `BaseException` 的正规入口之后才读到上面的表。另一枚副产品：`_read_queue_terminal` 故意**不**捕 `AssertionError` ⇒ 假出口那句「状态全读完了还在轮」会照直炸穿量具，而不是被 `except` 咽掉。🔴 这是有意的：多打一发与读失败是两件事，后者才许记 `read=False`；把前者的证词咽下来就等于给自己造了一枚假绿。

## 5. 开窗口径（🔴 这一条是给总控的硬要求）

`EVAL_POST_APPROVAL_READBACK=on` **必须写进 run22／D 相 2 那扇窗的环境**，否则 D-3 那一格在整窗账上读成 `no_readback`，也就是「这一格今天没量过」—— 那不是判红也不是判绿。缺省关的理由有三条，全是量具自己的纪律：

1. 假出口按**发数**说话：在册件（`tests/test_r259_awaiting_approval_stops_the_watch.py`、`tests/test_r222_queue_terminal_stopwatch.py`、`tests/test_r223_frame_arrival_clock.py`、`tests/test_r181_text_frame_ruler.py`）里那批 `Transport` 把状态读的发数当判据，默认多打一发会当场打断历轮复放（`drive_queue` 的 `statuses` 耗尽即抛）。
2. 历轮字节可比：默认开着会把 `post_approval` 长进每一扇新窗的账上，而历轮原件里没有这一格 ⇒ 复算件要分两种形状说话。
3. 那一发是真打服务的：本单红线是零容器零连库，默认关让「装上」与「用上」分两步，用上由总控开窗那一刻决定。

开关状态随 `summary()` 交回（`post_approval_readback: on|off`），收窗自查一眼可见。

## 6. 不变量与禁区自证

- 🔴 零产品码：`app/**` 一字节没动（本单只改 `scripts/eval_transport_ask_v2.py`）；`deploy/**`、`.env*`、`docker-compose.yml`、`frontend/**`、`tests/fixtures/**`、`docs/handoff/**`、`docs/api/contract-v1.md`、`scripts/run_gate.py`、`pyproject.toml`/锁文件、在册件 `scripts/r631_*`／`r633_*`／`r634_*`／`r636_*`／`r638_*` 及其 tests —— 全部零手。收席五枚见 §8。
- 🔴 帧账一行的键集一格不多：`set(row) == FRAME_ROW_KEYS` 那枚**对判**在册钉没动，本单的新格嵌在 `queue` 里（`test_the_extra_cell_is_the_only_shape_change_in_the_queue_book`：开着与关着两跑对照，`queue` 那一格只多 `post_approval` 一名，其余逐格同数，`criterion_two_holds` 同值）。
- 🔴 不折 0、不冒充：快照那一格仍然在账上、仍然读 `awaiting_approval`，没有被顶掉也没有被拿来当批准后终态（`test_a_failed_readback_is_none_never_zero_and_never_the_snapshot` 最后一条断言）。
- 🔴 钟的纪律：那一发 GET 一次表都不许多读（`test_the_readback_costs_not_a_single_extra_clock_read`：开关开／关两跑 `time.reads` 相同）；`_poll_queue` 的停表词表按 AST 现读，一字未动（`test_the_stop_vocabulary_did_not_move`）。
- 🔴 一条腿一件事：D-3 读的是**可读面终态载荷**；流内 `sources` 事件那一格属流内层（`scripts/eval_lane_readout.py` 自己写着「两层不许互抄」），本单没往里抄任何东西（`test_the_ruler_keeps_one_measuring_leg_per_job`）。
- 在册件字节自证：`tests/_r259_queue_ruler.py` 与各在册 test 全部零手；两枚新 test 跑完现读被跟踪量具的 sha256，必须与 import 那一刻逐字节相同（`test_the_tracked_ruler_is_byte_identical_after_every_run`）。

## 7. 交回总控的账面项（🔴 本单不落地）

1. `docs/handoff/2026-09-15-backend-followup-requests.md` §167 二／§172 二 需补记：D-3 那半格已由本单装上能力，**账面结论仍未量**；run22／D 相 2 开窗必带 `EVAL_POST_APPROVAL_READBACK=on`，不带则该格记「未量到」而不是零枚。
2. `docs/handoff/2026-09-15-orchestration-board.md` 名册行：本席工单号 R642、树 `be-r642`、基点 `2103890`。
3. 读数件那一段若要改吃新读数（`scripts/eval_lane_readout.py::D-3`），🔴 那枚文件不在本单写域，本单没动它 —— 建议的接法是「approval 轮走 `post_approval_sources_readback`，其余照旧走 `sources_cell`，两枚读数分列点名」，具体替换句请总控落纸后本席不复述行号。
4. 契约没漂：`/api/v1/queue/status/{request_id}` 的请求与响应形状一字未改（本单只是**多打一发同一枚 GET**），`docs/api/contract-v1.md` 无需追加句 —— 请总控复核这一句是否成立。

## 8. 两态亲跑与收席

判据④ 两态同数（同名件 32 枚 test 文件，逐枚点名见 §9）：

- state①＝本树 apply 未 commit：`528 passed`，零 failed，零 error。
- state②＝`%TEMP%\r642\clean_state2`：`git archive 2103890` 解出干净检出 + 只投本单货（改后的量具 + 两枚新 test），跑**同名件**：`528 passed`。
- 🔴 两态的逐枚文件计数 `Compare-Object` 差集为空。

排除件与理由（不跑它们不是躲，是它们把「此刻盘面脏不脏」当判据）：`tests/test_r496_forbidden_pin_scope.py::test_the_real_tree_reads_its_own_construction_fingerprint` 与 `tests/test_r623_content_caliber_disk_pins.py::test_counter_evidence_existence_in_porcelain_is_not_evidence` —— 两枚都对被放掉/被点名的禁域候选要求「盘上字节 == HEAD blob」，而 `scripts/eval_transport_ask_v2.py` 正在那两枚件的名单里，任何合法改它的动作都会当场红（#96／#107／#113 同族）。🔴 这一句本席没有停在断言上：现取两枚的读数——脏树（本单货在盘上）`2 failed, 36 passed in 79.23s`，失败文案逐字是「闸门放掉了真改动：scripts/eval_transport_ask_v2.py（读数 M …）」与「说谎刀的前提不成立（这枚文件真与 HEAD 不同）：… 盘上字节与 HEAD blob 不等＝改过 | HEAD=100644:9cbddbd2f0 index=100644:9cbddbd2f0」；同一枚基点 `2103890` 克隆一份干净树（`%TEMP%\r642\clean_clone`，`status --porcelain` 空）再跑同名两枚件：`38 passed in 81.05s`。⇒ 红与绿只跟着「此刻盘面脏不脏」走，与本单的货对不对无关；并树即自绿，本单不代改在册件。
## 9. 判据④ · 同名件 32 枚逐枚点名（两态同数）

命令原文（两态各跑一遍，件清单＝`$env:TEMP\r642\samenam_files.txt`，`--collect-only` 逐枚计数 + 实跑总数）：

```powershell
# state①：本树 apply 未 commit
cd C:\Users\fengx\PycharmProjects\be-r642
.\.venv\Scripts\python.exe -m pytest -p no:randomly -q <同名件 32 枚>
# state②：干净检出 + 只投本单货
git archive --format=tar -o $env:TEMP\r642\base.tar 2103890
tar -xf $env:TEMP\r642\base.tar -C $env:TEMP\r642\clean_state2
#   投货：scripts/eval_transport_ask_v2.py（改后）+ tests/test_r642_a2_stream_level_exemption.py
#         + tests/test_r642_post_approval_terminal_readback.py
C:\Users\fengx\PycharmProjects\be-r642\.venv\Scripts\python.exe -m pytest -p no:randomly -q <同名件 32 枚>
```

现取读数：state① `528 passed, 32 warnings in 75.67s` ｜ state② `528 passed, 32 warnings in 80.78s`。
逐枚计数（枚数＝该件 collected＝passed，两态 `Compare-Object` 差集为空）：

```
21  tests/test_r181_text_frame_ruler.py                 16  tests/test_r456_error_round_is_not_an_answer.py
 8  tests/test_r210_break_replaces_the_screen.py        15  tests/test_r456_run9_frame_ledger_recomputes_the_verdict.py
 6  tests/test_r210_frame_ledger_of_a_broken_round.py    9  tests/test_r456_single_frame_shape_is_not_a_pass.py
15  tests/test_r215_recognizing_a_controlled_correction 16  tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py
 4  tests/test_r215_recomputing_run6_frames.py          17  tests/test_r506_a2_ledger_required_keys.py
 3  tests/test_r218_cache_hit_observability.py           7  tests/test_r506_a2_single_frame_not_green.py
 4  tests/test_r218_egress_gate_placement.py             8  tests/test_r507_blind_instrument_returns_none.py
21  tests/test_r218_lane_flip_stop_sets.py              31  tests/test_r515_frame_caliber_blind_instrument_returns_none.py
 9  tests/test_r218_ruler_self_calibration.py            8  tests/test_r595_group_derivation.py
39  tests/test_r222_queue_terminal_stopwatch.py          8  tests/test_r595_honest_span.py
30  tests/test_r223_frame_arrival_clock.py               8  tests/test_r595_stall_cap.py
16  tests/test_r259_awaiting_approval_stops_the_watch.py 25  tests/test_r601_replay_diff_not_disk_state.py
21  tests/test_r259_terminal_readout_lands_in_the_book.py 27  tests/test_r619_a2_break_tiers_are_a_reading_tier_not_an_exemption.py
23  tests/test_r447_queue_approval_round_and_evidence.py  6  tests/test_r632_reader_help_smoke.py
                                                          39  tests/test_r632_slo_lane_readout.py
                                                          29  tests/test_r632_transport_lane_switches.py
                                                          20  tests/test_r642_a2_stream_level_exemption.py
                                                          29  tests/test_r642_post_approval_terminal_readback.py
```

在册件里那枚「帽值现读自量具某一行」的派生坐标钉（`tests/test_r595_stall_cap.py::test_run9_book_credential_is_reproduced`）在本单改动后仍然绿：那一枚把 `QUEUE_STALL_SECONDS` 在量具里住在哪一行当成判据，所以本单所有 hunk 一律落在 `DECLARE_LANE_PER_TIER`／`RECORD_LANE_READOUT` 那一片之后 —— `git diff -U0 HEAD` 交回的首枚 hunk 也在那里，那一行一个字节都没被推走。

## 10. 未验清单（做不到的格子，不拿「应该」凑）

1. 🔴 **真机批准后终态读数＝未验**。本单红线是零容器零连库，那一发 GET 一次都没打过真服务；「量到」那一支只有假出口演示（§4）。要验就得开 run22／D 相 2 那扇窗，且必带 `EVAL_POST_APPROVAL_READBACK=on`。
2. 🔴 **那 8 枚的历史结论＝不重判**。`run21b` 原件里 8 枚的 `queue.terminal` 仍是挂起快照，本单不回头改写历轮读数（与 R471「当年读数一律不重判」同一条纪律）；§3 的对照表只证「读法换了会怎样」，不证那 8 枚批准后到底交回几枚出处 —— 后者是第 1 条。
3. **全量门＝未跑**（本单不跑，避免 CPU 争用与脏树噪声；两态亲跑见 §9，反证钉不分层已含在同名件里）。
4. **`eval_lane_readout.py` 那段接法＝未落地**：不在写域，§7 第 3 条交回总控。