# R590 · A② 逐腿归因：`tool-02`／`scope-05` × run13／run14／run17

判据原文＝跟进单 §157 三（`docs/handoff/2026-09-15-backend-followup-requests.md:5284`，逐字为准）。
量具＝本单新件 `scripts/r590_a2_leg_attribution.py`（只读、离线、零网络、零模型、零容器、零写盘）。
执行层 Lorentz，树 `be-r590`@`03507f3`，交回时 dirty 只含本单两枚新件；**总控验收后代提交**。

🔴 本纸只交数与归因。翻不翻绿、哪一枚腿算产品形状、量具口径要不要改，由总控裁；改判据必须单独报批，本单一枚腿都没放宽。

## 0. 先交的那件事：在册尺的腿清单原文

尺＝`scripts/eval_transport_ask_v2.py::_frame_verdict`（定义在 :791，合取主体 :825-833）。
下面这七枚**逐字抄自源码**，本纸与本量具的逐腿结论只许引用这七个名字：

| 第几腿 | 短名（在册写法） | 操作数原文 | 行号 |
| --- | --- | --- | --- |
| 1 | `text_frames>1` | `readings["text_frames"] > 1` | :825 |
| 2 | `max_stream_frames>1` | `readings["max_stream_frames"] > 1` | :826 |
| 3 | `uncorrected_breaks==0` | `readings["uncorrected_breaks"] == 0` | :827 |
| 4 | `missing_chars==0` | `readings["missing_chars"] == 0` | :828 |
| 5 | `extra_chars==0` | `readings["extra_chars"] == 0` | :829 |
| 6 | `last_frame_covers_answer` | `readings["last_frame_covers_answer"]` | :830 |
| 7 | `cross_stream_repeat_frames==0` | `int(readings.get("cross_stream_repeat_frames", REPEAT_DELIVERY_UNMEASURED) or 0) == 0` | :832 |

支撑坐标（全部现取，行号随改动会漂、符号名不会）：

- 键序真源＝`scripts/r239_stream_gap_offline_audit.py:84-86` 的 `LEDGER_CONJUNCTS`（去掉 `criterion_two_holds` 那第八枚，它是存档读数、不是腿）。
- 在册判器自己写出过的腿名只有两枚：`scripts/r239_stream_gap_offline_audit.py:209-216` 的 `extra_red_conditions` ⇒ `max_stream_frames>1`、`uncorrected_breaks==0`。本量具的短名写法就是照它对齐的（第 5 道闸，见 §6）。
- 第 3 枚的读法来源＝`scripts/eval_transport_ask_v2.py:653-680` `_corrective_readings`（R215 四条豁免，缺一不豁免）。
- 第 7 枚是**派生**读数、不是帧账的一格（丙案，总控 09-29 裁定一）：`scripts/eval_transport_ask_v2.py:683-732` `_cross_stream_repeats`，缺省 `REPEAT_DELIVERY_UNMEASURED = 0` 在 :788；离线复算的同口径分身在 `scripts/r239_stream_gap_offline_audit.py:138-171`。
- 前缀单调的构造语义＝`scripts/eval_transport_ask_v2.py:415-428` `_count_text_frame`：后端每枚 text 帧发的是**截至这一片的累计全文**，后帧不以先帧为前缀即记一次坏形。

量具怎么保证一枚腿名都不自造：`_frame_verdict` 的源码现场 `inspect` + `ast` 拆合取，短名由操作数自己的键与右值生成，键序必须逐枚等于 `LEDGER_CONJUNCTS` —— 对不上当场 REFUSE（`T6` 反证刀咬的就是这一格）。腿的**判**不在量具里重写：把拆出来的那一枚操作数原样 `compile` 后执行；合取整体再叫真尺 `_frame_verdict` 判一次、叫判器 `recomputed_ledger` 复算一次、与账上存档 `criterion_two_holds` 对判一次，四面不同代即 REFUSE。

## 1. 三窗指纹（现读 `*.window.json`，不抄纸面）

```
python scripts/r590_a2_leg_attribution.py --format table
```

| 窗 | revision | index_backend | 起窗 | fixture_sha12 | 帧账件 sha12 |
| --- | --- | --- | --- | --- | --- |
| run13 | `fd90f30` | `''`（＝缺省，遗留 Chroma 读腿） | 2026-10-02 22:36:22 | `686c564ff298` | `afc469ae999e` |
| run14 | `fd90f30` | `pgvector` | 2026-10-03 00:27:29 | `686c564ff298` | `30e433c0362c` |
| run17 | `e6fdeb4` | `pgvector` | 2026-10-03 11:25:48 | `686c564ff298` | `8270df43ff35` |

- run13 与 run14 **同一枚 revision**，唯一不同是读后端 ⇒ 判据③ 那格只能靠"内容是否逐字相同"来判，不能靠 revision。
- 开窗器现读：`launch_run13.py` 未设 `EVAL_DECLARE_LANE_TIER`；`launch_run17.py` 设了 `EVAL_DECLARE_LANE_TIER="报告"` ⇒ run17 报告档 20 枚走队列道（`metric-16..19`／`tool-01..04`／`report-01..12`），run13/run14 零枚。这一格是 run17 形状变化的**唯一**开窗差因，见 §5。
- 在册尺 `eval_transport_ask_v2.py` 与判器 `r239_stream_gap_offline_audit.py` 在 `fd90f30..03507f3` 之间 `git log` 交回**零笔** ⇒ 三窗的账与今天这把尺同代；实测四面同代对判 315 行**零枚漂移**（`drift=0`，见 §6 的 T5 那条是影子、不是真账）。
- 三本账输入件 sha12 由量具现算并列进机读面（`--format json`）。

### 1.1 工单引数逐字对账（硬规矩 5：引用任何数字前先查它有没有被后续实测推翻）

工单 §157 三自己引了一组数。本单先拿**原始帧账**（`runNN-sidecar-frames.jsonl` 逐行现读，不经本单量具转手）对它：

| 工单原文引数 | 现读原始帧账 | 判定 |
| --- | --- | --- |
| `tool-02` run13 `text_frames=20 / max_stream_frames=19 / answer_chars=561 / first_visible_event=step / first_visible_ms=37340.1 / kind=approved_ok` | 20 / 19 / 561 / step / 37340.1 / approved_ok | ✅ 逐字符合 |
| `tool-02` run14 同形，`first_visible_ms=41127.4` | 20 / 19 / 561 / step / 41127.4 / approved_ok | ✅ 逐字符合 |
| `scope-05` run13 `text_frames=31 / max_stream_frames=30 / answer_chars=612` | 31 / 30 / 612 | ✅ 逐字符合 |
| `scope-05` run14「**同值**」 | 🔴 **7 / 6 / 612** | ❌ **帧数那一格被推翻**（只有 `answer_chars=612` 符合） |

- 🔴 抄账请改数：`scope-05` run14 = `text_frames=7 / max_stream_frames=6 / prefix_breaks=1 / uncorrected_breaks=1 / answer_chars=612`，逐帧原文见 §3.1 那张帧级表。
- 这一改**不动判据① 的结论**（run14 `scope-05` 仍只红在第 3 枚 `uncorrected_breaks==0`），也不动判据②③ 的方向；但工单那句「两枚都不是『没逐片腿』——**片数在几十枚**」对这一格不成立：它这一窗只有 7 枚逐片帧（仍 >1，仍算有逐片腿，但不是几十枚）。
- 与本单量具对判：`r590_a2_leg_attribution` 交回的 7/6/612 与原始帧账逐字同 ⇒ 不是量具读错，是工单那一格引数过期。


## 2. 判据①：逐腿点名（三窗 × 两枚题）

```
python scripts/r590_a2_leg_attribution.py --format table
```

| 题 | 窗 | kind | 红在第几腿=短名（读数） | 该腿单独摘成合格值会不会翻绿 | tf/msf/streams | 队列格 | 首屏 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tool-02` | run13 | approved_ok | **第 3 枚 `uncorrected_breaks==0`（值=1）** | 会（sole_blocker=True） | 20/19/2 | 0 | step @ 37340.1 ms |
| `tool-02` | run14 | approved_ok | **第 3 枚 `uncorrected_breaks==0`（值=1）** | 会（sole_blocker=True） | 20/19/2 | 0 | step @ 41127.4 ms |
| `tool-02` | run17 | queued_approved | **第 1 枚 `text_frames>1`（值=1）＋第 2 枚 `max_stream_frames>1`（值=1）** | 都不会（两枚同挡，单摘一枚仍红） | 1/1/2 | 10 | queued @ 69.9 ms |
| `scope-05` | run13 | approved_ok | 无（这一格绿） | — | 31/30/2 | 0 | step @ 12013.5 ms |
| `scope-05` | run14 | approved_ok | **第 3 枚 `uncorrected_breaks==0`（值=1）** | 会（sole_blocker=True） | 7/6/2 | 0 | step @ 42023.6 ms |
| `scope-05` | run17 | approved_ok | 无（这一格绿） | — | 30/29/2 | 0 | step @ 9465.3 ms |

三格里第 4／5／6／7 枚在**这两枚题的六个读数上全部合格**（`missing_chars==0`、`extra_chars==0`、`last_frame_covers_answer`、`cross_stream_repeat_frames==0`，且第七枚在三窗都有逐帧指纹、不是未量）⇒ 本单点名到的红腿只有三种：第 1、第 2、第 3 枚。

## 3. 判据②：每一枚红腿是产品形状还是量具口径

### 3.1 第 3 枚 `uncorrected_breaks==0`＝**产品形状**（不许放宽）

凭据＝量具 §4 面「帧正文与终答的关系」（用真尺自己的 `_sha12` 现算，逐帧那一列只有 sha+chars，本件不另起指纹尺）：

| 题 / 窗 | 累计帧枚数 | 与终答的关系计数 | 断流那一枚 |
| --- | --- | --- | --- |
| `tool-02` run13 | 20 | 不在终答里 18 ／ 终答前缀 1 ／ 终答逐字 1 | 第 19 帧（该流末帧）508 字 `40a89c73d70f`＝**终答前缀** |
| `tool-02` run14 | 20 | 不在终答里 18 ／ 终答前缀 1 ／ 终答逐字 1 | 同上，同一枚 sha |
| `tool-02` run17 | 1 | 终答逐字 1 | 无断流（队列道前台零帧） |
| `scope-05` run13 | 31 | 终答前缀 30 ／ 终答逐字 1 | 无断流 |
| `scope-05` run14 | 7 | 不在终答里 5 ／ 终答前缀 1 ／ 终答逐字 1 | 第 6 帧（该流末帧）559 字 `c0bf3ebffe39`＝**终答前缀** |
| `scope-05` run17 | 30 | 终答前缀 29 ／ 终答逐字 1 | 无断流 |

读法：三枚红行都是同一形——挂起轮先流出了**若干枚从未进入交付的正文**（`不在终答里`＝sha 与终答的任何内截切片都不等，量具逐枚扫过全部起点），末帧再整段换成终答的那一份前缀。这就是 `_count_text_frame`（`scripts/eval_transport_ask_v2.py:415-428`）注释里点名的坏形本身（"片与终答不同源，或流被截断"），也是 A② 存在的理由。⇒ **第 3 枚读的是真发生过的一次屏上改写，不是尺子口径造出来的假红。**

**帧级逐字凭据**（原始帧账 `stream:at:chars:sha12` 现读摘录，不经量具转手；「关系」那一列由量具用真尺自己的 `_sha12` 逐枚扫全部内截切片现算）：

| 题 / 窗 | 挂起轮（stream 0）逐帧 | 批准轮（stream 1） |
| --- | --- | --- |
| `scope-05` run13 | 30 枚，chars 20→40→60→81→100→121→141→161→181→200→221→242→260→283→304→324→332→352→370→393→413→432→453→474→495→514→536→557→**559→559**，`prefix_breaks=0`，全部是终答的前缀 | 612 `0f6854a2e2a7` |
| `scope-05` run14 | 6 枚：21 `3b778b3f4412` → 42 `38460929bbdb` → 62 `da45c100da16` → 82 `7546272c2a1f` → 92 `3e3c6d129977` → **559 `c0bf3ebffe39`（`prefix_break=True`）**；前 5 枚逐枚都不是终答的内截切片，第 6 枚整段换成终答的 559 字前缀 | 612 `0f6854a2e2a7` |
| `scope-05` run17 | 29 枚：**前 16 枚与 run13 逐字同 sha**（`1667494d1280`…`deae5d287a97`），中段分片边界漂（342/366/385/411 对 run13 的 332/352/370/393），432 字起**重新逐字合流**，末两枚同为 `c0bf3ebffe39`，`prefix_breaks=0` | 612 `0f6854a2e2a7` |
| `tool-02` run13 | 19 枚：chars 20→41→62→…→370 共 18 枚草稿（**逐枚都不是终答的内截切片**）→ **508 `40a89c73d70f`（`prefix_break=True`＝终答前缀）** | 561 `38984a1f5a10` |
| `tool-02` run14 | 同形同位；18 枚草稿的 sha 与 run13 **逐枚不同**（首枚 20 字即 `436e9a613f5d` ≠ run13 的 `906e0cde103a`），第 19 枚仍是 **508 `40a89c73d70f`**（与 run13 逐字同） | 561 `38984a1f5a10` |
| `tool-02` run17 | **挂起轮零 text 帧**（`per_stream[0].frames=0`；stream 0 的 `events` 只有 `queued` @69.9 ms + `done`） | 561 `38984a1f5a10`（全窗唯一一枚，队列道整段交付） |

只有逐帧面才看得到的三条读数：

1. **断流点之后那份正文跨窗逐字同**：`c0bf3ebffe39`（559 字，`scope-05` 三窗同一枚）与 `40a89c73d70f`（508 字，`tool-02` run13/run14 同一枚）⇒ 换进来的那一枚与读后端无关，三窗里会变的只有断流点**之前**那份草稿。
2. **草稿本身逐跑抽签**：同一枚题、同一 revision 的 run13／run14，`tool-02` 的 18 枚草稿 sha 逐枚不同；而 `scope-05` 在读后端**不同**的 run13／run17 却交出前 16 枚逐字同的挂起轮帧 ⇒ 「挂起轮草稿是否恰好与终答同源」既不是窗内恒定量，也不是读后端的确定性函数。🔴 这两组对照都**没有控制变量**（两两同时差着 revision 或后端），所以只够否掉「红＝后端的确定性映射」这一读法，不够给任何一侧定因果（见 §8 第 12 格）。
3. **`prefix_break` 记的是改写、不是重复**：run13 `scope-05` 末两枚 sha 相同（同一份 559 字发过两遍），在册尺没把它记成坏形（相等即前缀单调成立）⇒ 第 3 枚读的是"屏上正文被换掉"这件事；"同一份正文交两遍"归第 7 枚 `cross_stream_repeat_frames==0` 管。

### 3.2 同一格里确实有一枚量具口径缺口，但**不在第 3 枚腿上**，在它的豁免账里 —— 本单不改，另立报批

R215 四条豁免（`scripts/eval_transport_ask_v2.py:653-680`）逐条对这三枚红行现判：

| 题 / 窗 | ① 是该流末帧 | ② 本轮至多一枚 | ③ 紧邻 `step(tool=answer_correction, status=running)` | ④ 逐字等于终答 |
| --- | --- | --- | --- | --- |
| `tool-02` run13 | 成立（19==19） | 成立（`prefix_breaks=1`） | 🔴 **账上取不到** | 不成立（508 ≠ 561） |
| `tool-02` run14 | 成立（19==19） | 成立（`prefix_breaks=1`） | 🔴 **账上取不到** | 不成立（508 ≠ 561） |
| `scope-05` run14 | 成立（6==6） | 成立（`prefix_breaks=1`） | 🔴 **账上取不到** | 不成立（559 ≠ 612） |

- 不豁免的**充分理由已经证到**：④ 不成立，四条缺一就不豁免，与 ③ 无关。
- ③ 今天在这本账上**判不了**：帧账一行只有 `prefix_breaks`／`uncorrected_breaks` 两枚派生格，`break_frames[].armed` 与那枚武装 step 的载荷（tool/status）都没落盘——`_consume:351-371` 只在内存里判 `armed`，`_note_frame_arrival:511-527` 只往逐帧那一列抄 `sha`/`chars`/`prefix_break`，`events` 那一列只存事件名。⇒ 这一格按 R580 的词表算**量具取不到**，既不算检索腿、也不能拿来给产品无罪。
- 🔴 需要总控裁的那一格是：**在 HITL 挂起轮这一形上，豁免 ④ 结构性不可满足**——park 交回的是批准之前的草稿（508／559 字），终答是批准之后补完的全文（561／612 字），两者按定义不等。若业主/总控认定"park 时的整段替换属设计意图"，那要改的是**豁免那一格**（另立单、单独报批、配套图钉），不是第 3 枚腿本身；本单一枚腿、一条豁免都没动。

### 3.3 第 1 枚 `text_frames>1` ＋第 2 枚 `max_stream_frames>1`（`tool-02` run17）＝队列道那一形，产品与口径两层必须分开裁

- **产品那一层是真的**：队列道前台那条流一枚 text 帧都没发（`per_stream[0].frames=0`；那一程的 `events` 只有 `queued` + `done`），交付靠轮询——账上 `queue` 格 10 枚键现读 `final=awaiting_approval`、`terminal.state=awaiting_approval`、`answer_present=false`、`polls=8`、`wait_ms=21233.1`；批准腿那一程只交一枚整段 561 字。客户在这一道里**看不到任何逐片增量**，A② 在这一道是"没有这条腿"，不是"量具没量到"。
- **口径那一层待裁**：这样的行该不该进 A② 分母，正是 R573 甲档两读在争的事（`scripts/r573_caliber_reconciliation.py:15-16` 原文：甲-1 按在册桶剔 B1∪B2／甲-2 按逐帧那一列到底有没有、剔 `text_frames==0`）。🔴 本件不选口径、不放宽第 1／第 2 枚，只交数。
- 两枚腿在这行**同时**挡路（`sole_blocker` 都为 False＝单摘任何一枚都不翻绿）⇒ 不许把这格写成"只是 `max_stream_frames` 的口径问题"。在册尺为什么单列第 2 枚，源码自己答了（`eval_transport_ask_v2.py:776-778`）："挂起轮 + 批准轮各一帧时 `text_frames=2` 而 `max_stream_frames=1`"——判据② 要的是**一条流真在逐片累计**。

## 4. 判据③：`scope-05` 只在 run14 红，这一格与切读有没有关系

**答（三层，抄这一格必须三层一起抄，只抄第一句就是假话）：**

- **机制层——没有关系（这一句可以判死）**：红的那枚腿是第 3 枚 `uncorrected_breaks==0`，它的全部输入是 SSE 累计帧的前缀单调（`prefix_breaks`）加 R215 四条豁免账（`scripts/eval_transport_ask_v2.py:653-680`），通路里没有向量库；它读的是"屏上正文被整段换掉"这件事本身。
- **账面层——没有任何相关凭据**：既看不到「pgvector 更爱红」，也看不到「切读改过这两枚题的任何一份交付」。下面六条读数按强弱排。
- **🔴 间接层——未证否（这一格留在纸上）**：红不红取决于"挂起轮那份草稿是否恰好与终答同源"，而草稿由模型生成、模型输入里可能有检索上下文；离线两引擎对照给这枚题的真差恰恰是 **`chroma_rows=0` → `pg_rows=5`**。在册账上没有任何运行期检索量能判这一格（第 6 条），所以**本单只判到「无凭据相关」，不判「已证明与切读无关」**。要关掉这一格需要一次受控 A/B（见 §8 第 11 格）。

六条读数：

1. **同一枚 pgvector 后端，两窗一红一绿**：run14 与 run17 的窗指纹都是 `index_backend=pgvector`（现读），`scope-05` 在 run14 红、在 run17 绿 ⇒ pgvector 不是这一枚红的充分条件；把红归给切读，先被 run17 否掉。按第 3 枚的全窗枚数看是 **run13（遗留读腿）1 枚／run14（pgvector）2 枚／run17（pgvector）0 枚**——两枚 pgvector 窗一枚 2 一枚 0，三窗样本量本身也构不成相关性。
2. **交付字节三窗逐字相同，连断流点之后那一枚也逐字同**：终答 612 字 sha `0f6854a2e2a7`（`answers` 与帧账两处一致，三窗同一枚）；替换进去的那一枚 559 字 sha `c0bf3ebffe39` 三窗同一枚，`tool-02` 那一枚 508 字 sha `40a89c73d70f` 两窗同一枚 ⇒ 切读没有改到这两枚题的任何一份交付正文。
3. **`tool-02` 是这条判据上最干净的一枚对照，它的红判得死**：离线两引擎对照里 `tool-02` = `chroma_rows=5`／`pg_rows=5`／`overlap=5`／`same_set=true`／`same_order=true`／`jaccard=1.0`／`kendall_tau=1.0` ⇒ 两把引擎给它的 top-5 **一枚都不差**，而它在 run13（遗留读腿）与 run14（pgvector）**两窗都红同一枚腿** ⇒ 这一枚的红不存在"可继承的后端差"，与切读无关可以判死；run17 它仍红但换到第 1／2 枚，那一格的原因是全窗唯一一次开窗器差集 `EVAL_DECLARE_LANE_TIER="报告"`（§5），不是后端。
4. **红腿的输入面里没有检索**（机制层那句的展开）：`uncorrected_breaks` 由 `_corrective_readings` 从帧列与终答算出，读的是前缀单调；账上 run14 的差异只出现在"挂起轮流出的头 5 枚帧不在终答里"，这条通路上没有向量库的读数。
5. **A④ 那一维三窗同分**（在册评分尺 `app/quality/eval.py:67` `_is_correct` 现场调用，量具 §5 面）：`tool-02` True／True／True，`scope-05` False／False／False ⇒ 这两枚题**都不在 R580 那 10 枚退步集合里**（退步要求分数翻转）。
6. **运行面的检索痕三窗同样为空，所以这本账里没有任何可归给读后端的差异**：`scope-05` 的 `answers.evidence` 三窗都是空数组、`tool_calls` 三窗都是 4；PG 只读现取（`SET default_transaction_read_only = on` 走 `docker exec enterprise-brain-postgres-1 psql`）沿 `agent_runs.session_id → trace_id → retrieval_traces` 查这六枚 session：**各 0 行检索痕**（同 trace 的 `trace_events` 各 18 行，事件类型·顺序·payload 键集三窗逐枚相同；join 键 `trace_id` 有值 ⇒ "0 行"不是 join 落空）。🔴 读法要收窄：三窗**同为 0** 只说明这本账里没有可比的差，**不证明**检索腿没执行——这张表在这条通路上根本不记，所以第 3 层那句「未证否」正是被这一条卡住的。

🔴 同时必须写清**切读确实改过的那一面**，否则这一格会被抄成"切读对这枚题毫无影响"这句假话：
离线两引擎对照探针（`%TEMP%\evalrun\p3-parity.json`，件 sha12 `b63d008b7536`，由在册件 `scripts/r59_recall_compare.py` 于 2026-10-03 00:27:01 现生成，k=5／l2／候选宽度钉到真源 100）里，`scope-05` 是 **`chroma_rows=0` → `pg_rows=5`**（`chroma_zero_rows=true`，它属于 Chroma 单腿空返回那 21 枚，`docs/perf/r580-a4-per-class-2026-10-03.md:73-78` 已逐枚点名；同处 `chroma_index_vs_exact_same_set=false` 而 `chroma_exact_ids` 有 5 枚 ⇒ 空的是 Chroma 的**索引腿**，不是它的暴力腿）。
⇒ 精确表述是：**读后端改的是这一枚题的索引层命中数（0→5 行），没改它的运行时引证（0/0）、没改交付字节（逐字同）、没改 A④ 分数（同分），也没有输入通路进到第 3 枚腿；但"0→5 命中行会不会间接改变挂起轮那份草稿"这一格，在册账上量不到。** 这一枚对照是**离线同题两腿现查**，不是 run13/run14 窗内流量，引用时不许混写成"窗内检索面变了"。

### 4.1 与 R580 那句的对账

R580 原文（`docs/perf/r580-a4-per-class-2026-10-03.md:14`）：

> 🔴 **退步 10 枚里，一枚都没有证到"检索腿"**：`生成措辞 4`＋`量具取不到 6`＋`检索腿 0`＋`分母口径 0`。

- **不冲突**：R580 量的是 A④ 的分数翻转集合，本单量的是 A② 的流式合取；`scope-05`／`tool-02` 两窗同分 ⇒ 根本不在它那 10 枚里，两处读的是不同的事，不存在互相抵账。
- **相互加强**：R580 把 `scope-05` 记在"两窗运行时都零引证的 8 枚"里（`:189`），本单独立测到它的终答与 park 帧两窗逐字相同——同一个事实的两条独立读数。
- 🔴 **本单不推翻那句，也不许拿那句给 A② 翻绿**：R580 的"检索腿 0 枚"是**分数**侧归因，不能读成"A② 的红腿与检索无关所以可以放过"；A② 那三枚红是流式形状，独立成立。

## 5. 全窗逐腿普查（判据① 的背景格，题号逐枚点名）

```
python scripts/r590_a2_leg_attribution.py
```

| 窗 | n | 绿 | 红 | 第1枚 `text_frames>1` | 第2枚 `max_stream_frames>1` | 第3枚 `uncorrected_breaks==0` | 第4枚 `missing_chars==0` | 第5枚 `extra_chars==0` | 第6枚 `last_frame_covers_answer` | 第7枚 红／未量 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| run13 | 105 | 95 | 10 | 5 | 6 | 1（`tool-02`） | 3 | 8 | 8 | 0／5 |
| run14 | 105 | 96 | 9 | 3 | 4 | 2（`scope-05`,`tool-02`） | 3 | 6 | 6 | 0／3 |
| run17 | 105 | 79 | 26 | 25 | 25 | **0** | 3 | 14 | 14 | 0／11 |

- run17 红从 9～10 涨到 26，**全部增量在队列道**：现读 `red ∩ queued = 20/20`（`metric-16..19`／`tool-01..04`／`report-01..12`，kind ∈ `queued_approved`／`queued_polled`），非队列的红只有 6 枚（`chart-01`,`chart-02`,`chart-04`,`data-02`,`data-09`,`data-12`）；run13/run14 的 queued 枚数都是 0。⇒ **这一格的暴涨与读后端无关，与 `EVAL_DECLARE_LANE_TIER="报告"` 有关**（`launch_run17.py` 现读）。
- 第 3 枚在 run17 **归零**（0 枚）：`tool-02` 在这一窗走了队列道，挂起轮一枚 text 帧都没流出来，"改写"那一形没有发生的机会 ⇒ 第 3 枚的枚数会随**道**漂，这是它今天最脆的一格（在册件 `r573` 丙档那两读的同一族问题）。
- 第 7 枚三窗全 0 红；未量枚数 5／3／11 全部落在 `text_frames==0` 的空读行上（帧列为空 ⇒ 派生不出证词，按在册纪律不追加定罪也不洗白），与 `r573_caliber_reconciliation` 甲-2 剔的那一族同形。
- 四面同代对判在 315 行上**零枚漂移**（逐行：操作数合取 ∧ `_frame_verdict` ∧ `recomputed_ledger` ∧ 存档 `criterion_two_holds`）。

## 6. 反证：四把刀全砍在本单新量具自己的闸门上（逐枚三枚 sha，还原后逐字节全等）

尺件＝`scripts/r590_a2_leg_attribution.py`。快照＝`%TEMP%\r590_probe\snapshot_clean.py`（修回后取的干净态，见下面那条事故自述）。
每把刀：只把那一枚**闸门**的条件式换成恒假，其余一字不动；跑完立刻按快照还原，并核"还原后与快照逐字节全等"。
刀不许只证红了——下面逐枚写明**漏拦的是哪一格、点名到哪枚题哪枚腿**。

| 刀 | 摘掉的那一格 | 摘前 sha12 | 摘后 sha12 | 还原 sha12 | 逐字节全等 | rc | 漏拦的那一格（题/腿点名） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| K1 | 四面同代对判（`_frame_verdict`∧操作数合取∧`recomputed_ledger`∧存档） | `d8a7f57e82a0` | `983f2b204296` | `d8a7f57e82a0` | True | 2 | `T5`：翻一枚 **run13 `scope-05`** 的存档 `criterion_two_holds` ⇒ 放过了假同代（该题第 1–7 枚全合格、唯一被翻的是存档那一列） |
| K2 | 腿序对判（与 `LEDGER_CONJUNCTS` 逐枚对） | `d8a7f57e82a0` | `c67d056f4506` | `d8a7f57e82a0` | True | 2 | `T6`：键序换一枚仍放行 ⇒ 真尺加/换腿时本件会按自己一套腿名出数 |
| K3 | 第 7 枚腿的未量分家 | `d8a7f57e82a0` | `0168944ea5e0` | `d8a7f57e82a0` | True | 2 | `T4`：把 **run13 `scope-05`** 的逐帧那一列摘掉 ⇒ `cross_stream_repeat_frames==0` 不再报未量、`unmeasured=[]`（R507 那一族假零复发一次） |
| K4 | 在册腿名子集对判（`extra_red_conditions`） | `d8a7f57e82a0` | `32e21eed8af6` | `d8a7f57e82a0` | True | 2 | `T7`：把本件短名漂一枚（`uncorrected_breaks==0` → `<>`）⇒ 仍出数，且**红腿归属会静默改名**（该形落在 run14 `scope-05` 第 3 枚腿） |

四把刀的共同读数：摘刀之后**归因表逐字未变**（`Compare-Object` 对 §2 那张表交回 0 处差异），也就是说刀没有让任何一枚题的读数变样——它只让"拦住假的那一格"失效。这正是本单要的形态：**归因靠在册尺，拦假靠闸，两者分家。**

🔴 事故自述（不许抹平）：第一轮刀跑因驱动件里 `$logf.err` 被 PS 解析成属性访问而中途抛错，K1 那一刀**留在盘上没还原**（发现时 `if False:` 计 1 处）。处置：先把那一行逐字改回原判据式，再取干净态快照，此后全部 sha 以该快照为基准；最终态复核 `rc=0`、影子正控 7/7 全过、sha=`d8a7f57e82a0` 与快照全等。同族教训＝"此刻盘面"不能当判据（R593 今日同款）。

三条**真件真数据**的 REFUSE（不落影子，零写入）：

| 命令原文 | rc | stderr 原文（要点） |
| --- | --- | --- |
| `python scripts/r590_a2_leg_attribution.py --fixture docs/testing/bank-shape-subset-30.jsonl --no-census` | 2 | `fixture 与窗指纹不同代：… 现算 sha256=823ec81f… 而 run13.window.json 记的是 686c564f…` |
| `python scripts/r590_a2_leg_attribution.py --expect-denominator 104 --no-census` | 2 | `run13 分母对不上：去重后=105 要求=104（要出小窗就显式改 --expect-denominator）` |
| `python scripts/r590_a2_leg_attribution.py --ids tool-99 scope-05 --no-census` | 2 | `run13 帧账里读不到题号 tool-99 ⇒ 拒绝按半套窗出归因（先确认这一窗收没收全）` |

另附一形（不是反证，是口径声明）：`--tag run13 run14` 交回 `rc=0`——本件允许只交历史两窗，但**本单按派工把 run17 一并交了**，不许拿"能少交"当"可以少交"。

## 7. 常驻钉复跑（**执行层自报**，非总控亲跑）

```
$env:PY = C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe
$PY -X utf8 -m pytest -o addopts= -p no:cacheprovider --basetemp=$env:TEMP\lorentzpt -q <下面十枚件>
```

`tests/test_r181_text_frame_ruler.py`、`tests/test_r215_recomputing_run6_frames.py`、`tests/test_r215_recognizing_a_controlled_correction.py`、`tests/test_r223_frame_arrival_clock.py`、`tests/test_r218_ruler_self_calibration.py`、`tests/test_r239_stream_gap_offline.py`、`tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py`、`tests/test_r507_blind_instrument_returns_none.py`、`tests/test_r565_a2_denominator_buckets.py`、`tests/test_r573_a2_three_calibres.py`

→ **151 passed / 4 warnings / rc=0**（首跑 11.78 s；本纸落盘后终检复跑同数 **151 passed / rc=0**、11.72 s；conftest 的模型端口闸两次都交回 `blocked connect attempts to host model port: 0`）。
另：在册三口径对账件现场复跑 `python scripts/r573_caliber_reconciliation.py --tag run13 run14 run17 --no-rows` 交回 **rc=0**（三窗 × 六档全交，本单不据它选口径）。
🔴 本单**未**跑全量门 `scripts/run_gate.py`（总控独占，本席禁跑）。

## 8. 没验的格子（逐枚点名，不许抄成"已排除"）

1. **run14 那 5 枚"不在终答里"的帧到底是什么字**：帧账只落 sha + chars，正文不落盘 ⇒ 未量。因此分不清两形：(a) 模型侧那份被丢弃的草稿；(b) 一条**没有** `answer_correction` 武装的整段替换。这一格只能由产品侧落盘（或在窗内多存一枚 armed 证词）才能判，属另单。
2. **R215 豁免第③条（紧邻 armed step）在三枚红行上成不成立**：账上取不到（§3.2 已点名原因）⇒ 记"量具取不到"，不记"产品无罪"也不记"豁免应生效"。
3. **豁免第④条该不该在 HITL 挂起轮这一形上改写**：本单只证到它**结构性不可满足**（508≠561、559≠612），改不改是**报批题**，本席不动、也不建议"顺手放宽"。
4. **队列道那 20 枚的逐帧形状**：本单逐枚读的是 `tool-02`／`scope-05` 两枚题；其余 18 枚只交了 `kind` 与逐腿枚数（§5），没逐枚读它们的 `queue` 格与 `per_stream`。
5. **run17 里第 3 枚归零是不是"改写那一形真的没发生"**：只证到"前台零帧 ⇒ 该形在本窗没机会发生"。同一枚题换同步道会不会仍红，需要一扇不声明 lane 的 pgvector 窗——今天没有这扇窗 ⇒ 未量。
6. **run14 开窗期的机器争用**：`queue_v2.out.log` 现读 S1→S2→S3 串行，六枚 REFUSE 全是对 run13 的锁（未双驱），S2 对照探针 00:27:01–00:27:03 完成、run14 驱动 00:27:29 起 ⇒ 已排除**同机另一枚 eval 驱动**争用；**未排除**其它进程（GPU 影子那格由 R581 在途，本单不接）。
7. **窗内检索面**：这两枚题的 `retrieval_traces` 三窗各 0 行 ⇒ 交不出文件名#chunk 级窗内差异；§4 那条 0→5 是**离线两引擎对照**，不是窗内读数，两者不许互换。
8. **`tool-02` run17 的 `tool_calls 4→2`、latency 37.9 s（对 69.2／77.4 s）**：只记数，未归因；与 A② 三枚红腿没有证到的通路。
9. **`scope-05` 三窗都被判错**（`_is_correct` False×3）：这是 A④ 那一侧的格子，本单只用来对账"两窗同分"，没治它。
10. **run6／run9 等历史窗**未纳入本单 ⇒ 本纸里任何一句都不许外推成历史结论。

11. **「切读会不会间接改变挂起轮那份草稿」这一格未证否**（§4 第三层）：在册账上没有运行期检索量可判（`retrieval_traces` 三窗各 0 行、`evidence` 三窗全空），而离线对照给过这枚题真实的一差（索引腿 0→5 行）。关掉它需要一次受控 A/B——同 revision、同 fixture、只翻 `INDEX_BACKEND`、两跑，并把挂起轮帧正文一并落盘；本席禁打模型（8001／11434），没做，也不在写域内。
12. **§3.1 那两条跨窗对照都没有控制变量**：run13 vs run17 同时差着 revision（`fd90f30` vs `e6fdeb4`）与后端；run13 vs run14 差着后端且 `scope-05` 帧数 31 vs 7。⇒ 它们只够否掉「红＝读后端的确定性映射」，**不够**给"后端无关"或"后端有关"任何一侧定因果；本纸里凡引用这两条的地方都已按这个宽度写。
13. **帧正文本身不落盘**（帧列只有 `sha`/`chars`/`prefix_break` 三枚键，`events` 列只存事件名）⇒ 第 1 格里那 5 枚（`scope-05` run14）／18 枚（`tool-02` 两窗）"不在终答里"的帧到底写了什么，今天**任何人都读不出来**，只能证它不等；「草稿分叉与上下文的关系」因此不可判，这是 §8 第 11 格卡住的直接原因。

## 9. 盘面自证（写域与行尾）

- 树＝`C:\\Users\\fengx\\PycharmProjects\\be-r590`，基点 `03507f379a73d4bb01901e13e666c6b145e5a262`（现取 `git rev-parse HEAD`），开工时 `dirty=0`；本席全程未 `commit`／`push`／建分支。
- 写域只有两枚新增：`scripts/r590_a2_leg_attribution.py`（新量具）与本纸 `docs/perf/r590-a2-leg-attribution-2026-10-03.md`，一字节都没碰在册件／`app/**`／评测集／`frontend/**`／`docs/handoff/**`；主树 `C:\Users\fengx\PycharmProjects\企业智脑` 零改动。

## 10. 随文自证（行尾单形 · 写域 · 命令原文）

- 行尾单形自证（本纸自己的字节数，写盘后现算）：`count('\r')=264`、`count('\n')=264`、`count('\r\n')=264` ⇒ **三者全等**（单形 CRLF，无孤立 \r、无裸 \n），且件首无 BOM（首字节十进制 35 = `0x23` = `#`）。
- 同目录既有件对照：`docs/perf/r580-a4-per-class-2026-10-03.md` 现读同为 CRLF 单形无 BOM ⇒ 本纸跟随所在目录既有件形制。
- 新量具件形制：`scripts/r590_a2_leg_attribution.py` CRLF 单形、无 BOM、`sha256` 前 12 = `d8a7f57e82a0`（与 §6 四把刀的共同快照同一枚，摘刀后已逐字节还原）。
- 写域（`git -C C:\Users\fengx\PycharmProjects\be-r590` 现取，本纸落盘后）：

```
$ git diff --numstat HEAD
（空——零枚在册件被改）
$ git ls-files --others --exclude-standard
docs/perf/r590-a2-leg-attribution-2026-10-03.md
scripts/r590_a2_leg_attribution.py
```

- 全树 `git status --porcelain` 现取只列上面两枚 `??`（零枚在册件）；运行期生成的 `scripts/__pycache__` 由 `.gitignore:2` 的 `__pycache__/` 覆盖（`git check-ignore -v scripts/__pycache__` 命中、rc=0），不入库。
- 本单**没有** `commit`/`push`/建分支；没有跑 `scripts/run_gate.py`；没有打模型端口、没有动容器、没有起服务；PG 只走 `docker exec … psql` 且带 `SET default_transaction_read_only = on`。
