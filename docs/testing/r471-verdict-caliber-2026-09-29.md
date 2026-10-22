# R471 · 流式逐字判据尺对「正文出现两遍」豁免过宽 —— 口径修正与影响面（2026-09-29）

- 单号 **R471**（第二令返工）｜ 执行体 `Harvey` ｜ 工作树 `be-r471` ｜ 基点 `d8fca78`（HEAD 未动，零 commit／零 push／零建分支）
- 本单**只治尺子**：判据②（流式逐字无缺）的真源合取里补第七枚腿。产品行为一枚字没碰（`app/**`、`frontend/**` 零写入），读数一枚没改（`docs/testing/sidecar-run*-frames.jsonl`、评测集、看板只读）。
- 台账更正：那句「写域含 `app/api/v1/chat.py` 的 verdict 计算」是**过期坐标，作废**。`_frame_verdict` 全在 `scripts/` 那一族量具里；09-29 现取全仓 `rg`：**`app/**` 里一枚读者都没有**。

## 一、病与真源（09-29 13:5x 现取行号）

| 坐标 | 它是什么 |
| --- | --- |
| `scripts/eval_transport_ask_v2.py:653 _corrective_readings` | R215 那四条豁免（末帧／本轮至多一枚／紧邻 arm／逐字等于终答）。**本单一枚未动** |
| `scripts/eval_transport_ask_v2.py:683 _cross_stream_repeats` | 🔴 本单新增的派生器：从**行内既有那一列** R223 逐帧指纹数「后一条流把先前发过的那份正文又发一遍」有几枚 |
| `scripts/eval_transport_ask_v2.py:725 _frame_readings` | 判据② 的读数层（09-29 现取 14 键，自本单起**一格未多、一格未少**） |
| `scripts/eval_transport_ask_v2.py:778 REPEAT_DELIVERY_UNMEASURED = 0` | 判定视图里缺证词时的缺省，读作「这一格今天没量过」⇒ **不重判** |
| `scripts/eval_transport_ask_v2.py:781 _frame_verdict` | 🔴 真源。改前合取六枚，改后七枚（第八行 822-823 是新增那一腿） |
| `scripts/eval_transport_ask_v2.py:826 _record_frames` | 落盘层：837 `row.update(arrivals)` → 838 `row.update(readings)` → **844 现场派生证词交给判定** → 845 `row["criterion_two_holds"] = _frame_verdict(readings)`（这行字面被 R215 钉着，未挪） |

病形（拿 run9 在册原件逐字复算，非推断）：`chart-04` 的帧账是 `text_frames=47`、`max_stream_frames=46`、`streams=2`、
`prefix_breaks=0`、`uncorrected_breaks=0`、`missing_chars=0`、`extra_chars=0`、`last_frame_covers_answer=true`，
而挂起轮（流 0）第 45/46 帧与批准腿（流 1）第 1 帧的逐帧指纹**同一个 sha**（`32fba0aa`，就是终答那份字）——
屏上此刻已经站着一份 915 字的正文，批准腿又把同一份字交了一遍。六枚合取对这一形**全读绿**（`criterion_two_holds=true`）。
前缀单调只在同一条流内判（`_fold_frames`），跨流重发常常一枚坏形都不长 —— 所以 R215 的豁免不是病根，**缺一枚证词才是**。

## 二、丙案：合取加、落盘列不加（总控 09-29 裁定一）

裁定：**`_frame_verdict` 里加第七枚合取，但 `cross_stream_repeat_frames` 改为读数时从行内既有的 R223 逐帧指纹现场派生，不落成新列。**

理由（现取在册钉，四枚都是「对判，不是子集」的闸）：
- `tests/test_r181_text_frame_ruler.py:433` → `set(got) == JOIN_KEYS | FRAME_READING_KEYS | ARRIVAL_READING_KEYS`；
- `tests/test_r223_frame_arrival_clock.py:612` → `set(row) - (JOIN_KEYS | OLD_CELLS) == NEW_CELLS`；同件 `:637` 再一次对判；同件 `:629` 还钉着 `_frame_readings` 的**返回形状**，`:633` 钉两层键集不相交；
- `tests/test_r259_awaiting_approval_stops_the_watch.py:162` → `set(row) == Q.FRAME_ROW_KEYS`（名单抄本在 `tests/_r259_queue_ruler.py:47/:52/:54`）；
- `tests/test_r447_queue_approval_round_and_evidence.py:393/:420/:453` 三枚金样逐字钉帧账行的字节。

🔴 例外通道**没有开**：派生这枚数要的三个量（`stream` / `chars` / `sha`）全在行内既有那一列里 —— 09-29 现取 run9 某行的
`frames[]` 字段 = `[arrival_at, at, chars, elapsed_ms, prefix_break, sha, stream]`，不需要任何行外或未存的量。

落地形态（谁都不往账上添格子）：
- 落盘层 `_record_frames:844` 在判定那一刻把 `arrivals["frames"]`（＝ `row["frames"]` 同一列表）交给 `_cross_stream_repeats`，
  把枚数塞进**判定视图** `readings` 再调 `_frame_verdict(readings)`。帧账那一行的键集一格未多：109 枚基线 + 15 枚件 217 枚全绿即自证。
- 🔴 顺序是判据的一部分：那一行必须排在 `row.update(readings)` 之后（排前面就会被写进落盘行）。本件把它钉在
  `tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:212 test_the_frame_row_gains_no_column_for_the_new_conjunct`：
  期望键集**由尺子自己交回的两层读数现算**（不抄第二份名单），疾病行走完真落盘 ⇒ `cross_stream_repeat_frames not in row` 且判定 `is False`。
- 名单只升级一处：`tests/test_r218_ruler_self_calibration.py:81` 的 `verdict_key_set` 6 名 → 7 名（返工令第 2 项，别处不抄）。
  为接住这枚升级，`scripts/r218_switch_rehearsal.py:829 _readings_keys` 现在也收 `readings.get("...")` 那种取用（`:856 verdict_reads` 的证词面），
  否则新腿会从名单里静默溜走 = 假牙。现取读数：`verdict_key_set = [cross_stream_repeat_frames, extra_chars, last_frame_covers_answer,
  max_stream_frames, missing_chars, text_frames, uncorrected_breaks]`，`reads_prefix_breaks=false`、`reads_uncorrected_breaks=true` 未变。

## 三、裁定二：同一条流内的同文收尾不算「出现两遍」（原话，署名总控）

> 「同一条流内末片帧与收尾帧同文」不判成「出现两遍」：R215 那四条例外（末帧／本轮至多一枚／紧邻 arm／逐字等于终答）裁的就是这一形，
> 收它等于推翻在册裁定；且 A② 要治的是缺字与断流，跨流重复才是 R464 治的批准腿病形。 —— **总控裁定（2026-09-29）**

这条边界写进尺子的口径纸（`_cross_stream_repeats:691` 起第一条边界）与两枚复算件，并钉在
`test_an_identical_closing_frame_in_one_leg_stays_a_pass`（合成形）与
`test_the_boundary_is_pinned_against_the_recorded_window`（真证据形）。真证据侧的账（09-29 现取 run9 那 105 行）：

- 带「同一条流里两枚非空帧同文」这一形的行 = **66 枚**，其中在册读绿 = **64 枚** ⇒ 一刀定罪就砍掉 64 枚在册绿，那是误伤；
- 带「跨流逐帧指纹重合」的行 = **3 枚**（`chart-04`／`insight-07`／`tool-04`），其中在册读绿 = **2 枚**（`tool-04` 当年已因真断流读红）。

## 四、新口径（第七枚合取）

```
_frame_verdict(readings) 今天合取七枚：
    text_frames > 1  且  max_stream_frames > 1  且  uncorrected_breaks == 0
    且  missing_chars == 0  且  extra_chars == 0  且  last_frame_covers_answer
    且  cross_stream_repeat_frames == 0        # R471 新增第七枚
```

第七枚的口径（`_cross_stream_repeats`）：沿折进账的到达顺序逐枚走，一枚**非空**帧的 `sha` 若在**更早的一条流**里出现过，记一次。三条边界不许放宽：

1. 🔴 只算跨流（裁定二）；同流同文是既有合法形状。
2. 空帧（`chars == 0`）不携带正文，谈不上重复，不参与。
3. 没指纹（`sha` 为空）就没证词，不参与 —— 与 R215 判据①「不许拿缺证词当证据」同一条纪律。

🔴 **派生而非另起一把尺**：证词只用 R223 那一列现成读数。把 `_count_text_frame` 摘瞎，`row["frames"]` 跟着空，这一枚一起归零 ——
与 `tests/test_r223_frame_arrival_clock.py:639`（派生而非另数）同一纪律；`_cross_stream_repeats([]) == 0` 也钉在件里。

🔴 **不重判当年读数**：判定视图里缺证词时按 `REPEAT_DELIVERY_UNMEASURED = 0` 读，既没资格追加定罪，也不许把当年的红字洗白 ——
同 `scripts/r239_stream_gap_offline_audit.py` 拿老账退回 `prefix_breaks` 那一条纪律。两枚复算件同样处理：账里没有 `frames` 那一列
（R223 并树之前的窗），或有那一列却枚枚为空（量具被摘瞎那一形），一律回 `None` 并**明写派生不出**，不许报 0 冒充量过。

## 五、谁读这枚尺（09-29 13:5x 全仓现取，`rg -n "_frame_verdict|cross_stream_repeat|_corrective_readings" scripts tests docs app`）

🔴 `app/**` 里**一枚读者都没有** —— 台账那句「`chat.py` 的 verdict 计算」是假坐标，本单对 `chat.py` 一枚字未碰。

| 坐标（现取） | 它在量什么 | 改后它的读数口径变没变 |
| --- | --- | --- |
| `scripts/eval_transport_ask_v2.py:781 _frame_verdict` | 真源：判据② 的合取 | 🔴 六枚 → **七枚**（唯一变严处） |
| `scripts/eval_transport_ask_v2.py:683 _cross_stream_repeats` | 第七枚的证词派生器 | 本单新增 |
| `scripts/eval_transport_ask_v2.py:653 _corrective_readings` | R215 四条豁免 → `uncorrected_breaks` | **一枚未动** |
| `scripts/eval_transport_ask_v2.py:725 _frame_readings` | 帧账那 14 格读数 | 形状未动（新格不落账） |
| `scripts/eval_transport_ask_v2.py:845` | 落盘处产出 `criterion_two_holds` | 调用式一字未改，只在 `:844` 多递一枚派生证词 |
| `scripts/r218_switch_rehearsal.py:829 _readings_keys` / `:856 verdict_reads` | 读代码取 `_frame_verdict` 到底读哪几格 | 名单 6 名 → **7 名**（`:829` 起多收 `readings.get(...)` 取用） |
| `scripts/r218_switch_rehearsal.py:900 frame_shape` | 三种坏形形状的 verdict | 口径随真源升七枚；本单的三种形都不重发正文 ⇒ 读数不变（在册 `test_r218` 9 枚照绿为凭） |
| `scripts/eval_frame_caliber_readout.py:35 RAW_CELLS` | 逐档摊开的原始格 | **没加新格**（丙案：那一格不在账上） |
| `scripts/eval_frame_caliber_readout.py:61/:105` `_repeats_of_records`/`derived_repeats` | 读数时从行内 `frames` 现场派生第七枚 | 本单新增；`:154-158` 明写「派生不出 ⇒ 不重判当年读数」 |
| `scripts/r239_stream_gap_offline_audit.py:84 LEDGER_CONJUNCTS` | 在册合取名单副本 | 六枚 → **七枚** |
| `scripts/r239_stream_gap_offline_audit.py:138 cross_stream_repeat_frames` | 同一枚证词的独立复算 | 本单新增；派生不出回 `None` |
| `scripts/r239_stream_gap_offline_audit.py:188/:202 recomputed_ledger` | 「账与尺同代」的复算腿 | 加第七枚（`None` 不参与定罪） |
| `scripts/r239_stream_gap_offline_audit.py:278/:306/:308` | 逐题新格 + 重合行与「量不出」计数 | 本单新增；`render_table` 尾行多两格 |
| `tests/`（12 枚在册件，逐枚见下面那张子表） | 拿这把尺判绿的在册钉 | 键集类对判一枚未动；判定类随真源升七枚 |
| `docs/testing/r181-text-frame-readings.md` | 判据② 口径纸 | 🔴 纸由总控改，本单未动（见第十一节） |

测试侧读者逐枚（09-29 现取，只列伸进这枚尺的那几枚）：

| 件:行号 | 它在量什么 | 改后读数口径 |
| --- | --- | --- |
| `test_r181_text_frame_ruler.py:238/:248/:258/:268/:314/:465/:475/:498` | 判据② 的五种形 + 两枚常驻反证 | 全绿：这些形都不重发正文 ⇒ 第七枚为 0 |
| `test_r181_text_frame_ruler.py:433`（FRAME_READING_KEYS 对判） | 帧账一行的键集 | 🔴 未动，照绿（丙案不落列） |
| `test_r203_sse_progressive_frames.py:283/:295` | 逐帧流式那一形 | 不变（0 重合） |
| `test_r210_frame_ledger_of_a_broken_round.py:82/:157/:163` | 断流轮与豁免轮 | 不变 |
| `test_r215_recognizing_a_controlled_correction.py:139/:156/:172/:296` | R215 三枚绿钉 + 落盘调用式钉 | 🔴 一枚未改宽，照绿 |
| `test_r215_recomputing_run6_frames.py:103/:153` | run6 那 105 行逐行复算 | 不变（run6 账无逐帧指纹 ⇒ 派生不出 ⇒ 不重判） |
| `test_r218_ruler_self_calibration.py:81/:84/:115-123/:188` | 尺子自校名：名单在此升级 6→7 | 🔴 本单唯一改过的在册件，且只改 :81 一处 |
| `test_r223_frame_arrival_clock.py:608/:612/:620/:629/:633/:637/:780` | 键集、两层形状的对判、历史账无新列 | 全绿：账上一格未多 |
| `test_r259_awaiting_approval_stops_the_watch.py:162` + `_r259_queue_ruler.py:47/:52/:54` | 队列道的键集对判与名单抄本 | 🔴 未动，照绿 |
| `test_r447_queue_approval_round_and_evidence.py:393/:420/:453` | 三枚金样逐字节钉帧账行 | 🔴 未动，23 枚照绿（见第十节） |
| `test_r456_run9_frame_ledger_recomputes_the_verdict.py:91` | 拿在册**行**直接喂 `_frame_verdict` ⇒ 0 漂 | 🔴 这枚就是「不重判当年读数」的在册凭据 |
| `test_r456_single_frame_shape_is_not_a_pass.py:187`、`test_r456_error_round_is_not_an_answer.py:223` | 单帧形与错误轮 | 不变 |
| `test_r459_ask_direct_answer_frames.py:299/:541/:573/:625` | 直答轮与摘掉三枚前置那一形 | 不变（那些形不跨流重发） |
| `test_r464_one_terminal_answer_stream_per_round.py:41/:472/:762` | 明文「不拿 _frame_verdict 当定罪证据」，并把 R471 挂在册上 | 未动，照绿 |
| `test_r48_headline_never_enters_the_text_ledger.py:117/:155/:235/:260/:340` | 卡片不许进帧账那几枚 | 不变 |
| `test_r471_second_copy_of_the_answer_body_is_not_a_pass.py`（本单新钉 16 枚） | 疾病形／孪生形／裁定二边界／丙案不落列／同代自证／两枚常驻刀 | 本单新增 |

## 六、历史帧账逐档表（09-29 现取四份在册原件；`text_frames > max_stream_frames` 那一格）

口径：`tf>msf` 是**换源形状**（病历点名的必要条件），不是尺子；尺子读的是**逐帧指纹重合**。逐档分开报，不报总数。

| 窗 | 档 | 行数 | `tf > msf` | 逐帧指纹重合 | 若据新口径重判会翻绿 | 当年在册 `criterion_two_holds=True` |
| --- | --- | --- | --- | --- | --- | --- |
| run6 | 问答 | 50 | 4 | 派生不出（账无逐帧指纹，R223 之前） | 0 | 0 |
| run6 | 分析 | 35 | 4 | 派生不出 | 0 | 0 |
| run6 | 报告 | 20 | 11 | 派生不出 | 0 | 0 |
| run7 | 问答 | 50 | 4 | 派生不出 | 0 | 42 |
| run7 | 分析 | 35 | 4 | 派生不出 | 0 | 33 |
| run7 | 报告 | 20 | 13 | 派生不出 | 0 | 18 |
| run8p2 | 报告 | 20 | 0 | 量不出（`frames` 列在而枚枚为空） | 0 | 0 |
| run9 | 问答 | 50 | 2 | 0 | **0** | 42 |
| run9 | 分析 | 35 | 4 | 2（`chart-04`／`insight-07`） | **2** | 32 |
| run9 | 报告 | 20 | 12 | 1（`tool-04`） | **0**（当年已红） | 17 |
| run9 | 合计 | 105 | 18 | 3 | 2 | 91 |

🔴 **已经交的 run2→run9 四次完整收窗读数算不算被重新判定：不算。** 那四份账由当年的尺子判完就封在盘上，本单**一枚不改、一列不加、一题不改判**；
上表「若据新口径重判会翻绿」那列是**纯算术的影响面**，不是新读数。三处后果写清楚：

1. 如果哪天有人拿新口径去重判 run9，翻脸只可能落在 **run9 分析档 2 枚**（`chart-04`／`insight-07`）：问答 0／分析 2／报告 0；
   `tool-04` 虽然同形重合，但它当年就因真断流（`uncorrected_breaks=1`）读红 —— 同一枚红不因新口径改名字。
2. `scripts/r239_stream_gap_offline_audit.py` 拿带逐帧指纹的账（run9）复算时会把这 2 枚列进 `ledger_drift`，读作**「这份账与今天这把尺不同代」**
   并当场点名，而**不是**替它改写（09-29 实跑：run9 `drift=[insight-07, chart-04]`，run7 `drift=NONE`）。这正是本单要的自证：账上那格是当年判的。
3. 🔴 阶段 A 的判据② **依旧「从没宣布验过」**，本单不把它验成绿，也不验成红 —— 只治尺子。

### run9 那三枚逐字点名（09-29 现取 `docs/testing/sidecar-run9-frames.jsonl`）

| 题号 | 档位 | kind | tf/msf/st | pb/cr/ub | mc/ec/covers | 重合证据（行内 `frames` 逐帧指纹） | 当年在册判定 | 新口径判 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `chart-04` | 分析 | `approved_ok` | 47/46/2 | 0/0/0 | 0/0/true | 流 0 第 45、46 帧（915 字，`sha=32fba0aa`）+ 流 1 第 1 帧（915 字，同 `sha`）＝跨流重合 1；`answer_sha=32fba0aa` | **True** | **False** |
| `insight-07` | 分析 | `approved_ok` | 31/30/2 | 0/0/0 | 0/0/true | 流 0 第 29、30 帧（590 字，`sha=5883685e`）+ 流 1 第 1 帧同文 ＝ 跨流重合 1 | **True** | **False** |
| `tool-04` | 报告 | `approved_ok` | 3/2/2 | 1/0/1 | 0/0/true | 流 0 第 1 帧（239 字，`sha=c555fa93`）与流 1 第 1 帧同文 ＝ 跨流重合 1 | False（真断流） | False |

前两枚就是总控要的那一形：**旧六枚全过、坏形一枚不长（`prefix_breaks=0`，豁免压根没出场）、屏上摆着两份答案**。
🔴 同一条流里的同文收尾（`chart-04` 流 0 的第 45/46 帧正是这一形）一枚都不定罪 —— 见第三节裁定二。

## 七、两形夹具的字段级原始读数（真收端 `_consume` + 真落盘 `_record_frames`，不靠模型不靠容器）

| 形 | tf | msf | st | pb | cr | ub | mc | ec | covers | 第七枚证词（派生） | 账上有这一格吗 | `criterion_two_holds` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 疾病形：批准腿收尾把已上屏的正文**重发一遍** | 3 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | true | **1** | 否 | **False** |
| 孪生形：同一副夹具只换字不重发 | 3 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | true | 0 | 否 | **True** |
| 带 arm 的重发形（R215 四条全中仍重发） | 4 | 2 | 2 | 1 | 1 | 0 | 0 | 0 | true | **1** | 否 | **False** |
| 带 arm 的只换字形（在册绿形） | 4 | 2 | 2 | 1 | 1 | 0 | 0 | 0 | true | 0 | 否 | **True** |
| 同一条流内收尾同文（裁定二那一形） | 3 | 3 | 1 | 0 | 0 | 0 | 0 | 0 | true | 0 | 否 | **True** |

两形的 `answer_sha`／`last_frame_sha`：疾病形同字（末帧 sha 与终答 sha 相同）；孪生形两形其余格逐字相同，只差「重发」这一枚事实。
疾病形与孪生形都让**旧六枚合取全过**（件里 `_old_six_hold` 摊开对判）⇒ 翻红的唯一来处就是第七枚。

## 八、R215 那三枚在册钉：一枚没改宽（现取凭据）

| 钉 | 现读坐标 | 表达式 | 本单动过吗 |
| --- | --- | --- | --- |
| 受控纠正轮读绿 | `tests/test_r215_recognizing_a_controlled_correction.py:139` | `assert ruler._frame_verdict(readings) is True` | **未动** |
| 带线上证词那份读绿 | 同件 `:156` | `assert ruler._frame_verdict(from_wire) is True` | **未动** |
| 真 /ask 断流轮读绿 | 同件 `:172` | `assert ruler._frame_verdict(readings) is True` | **未动** |
| 落盘那一行的调用式 | 同件 `:296` | `assert 'row["criterion_two_holds"] = _frame_verdict(readings)' in source` | **未动**（丙案不改这一行，只改它上面那一层） |

同件另外六枚 `is False`（腰上坏形／本轮第二次纠正／没武装／没上屏／末帧多字／单帧与两枚单帧）也**一枚未放宽**。

- 🔴 字节级凭据：`git diff --name-only d8fca78 -- tests docs` 现取只回一枚文件 —— `tests/test_r218_ruler_self_calibration.py`，
  而它只改了 `:81` 那枚 `verdict_key_set` 名单（6 名 → 7 名，返工令第 2 项）。R215 两件、`test_r181`、`test_r223`、`test_r259_awaiting_approval`、
  `_r259_queue_ruler`、r447 三枚金样 **diff 为空，逐字未动**。
- 「把新口径摘掉→旧三枚仍绿」的实跑：见第十节刀一（摘掉第七枚合取）那一轮，R215 两枚件 **19 枚照绿**，红名全在本单新钉里。
- 单跑现取：`tests/test_r215_recognizing_a_controlled_correction.py` **15 passed / 7.89 s**；
  `tests/test_r215_recomputing_run6_frames.py` **4 passed / 0.33 s**（后者是 run6 那 105 行的复算钉，`criterion_two_holds` 逐行不漂）。
- 另两枚同族在册钉照绿：`test_r456_run9_frame_ledger_recomputes_the_verdict.py:84`（拿在册**行**直接喂 `_frame_verdict`，
  0 漂、不 KeyError）与 `test_r223_frame_arrival_clock.py:608/:620`（键集与两层形状的对判）—— 这就是丙案「不落列」的机读证明。
- 本回合（13:5x）现取复核：`git diff --name-only d8fca78 -- tests docs` 依旧**只回一枚** `tests/test_r218_ruler_self_calibration.py`；
  R215 两件逐枚单跑现取 **15 passed / 9.07 s** 与 **4 passed / 0.38 s**（`--tb=line`，0 failed）⇒ 三枚 `is True` 钉与那枚调用式钉改前＝改后。

## 九、反证：三把刀照**改后终态**重挥（事故 #83 的教训：刀要照基线造，不照 after 自己造）

点名基线（同一组 7 枚件、同一台机器、离线）：
`test_r181`（21）＋ `test_r215`×2（15＋4）＋ `test_r218_ruler_self_calibration`（9）＋ `test_r223`（30）＋
`test_r239_stream_gap_offline`（14）＋ `test_r471`（16）⇒ 基线 **109 枚 / 11.17 s**（三刀挥完还原后再跑：**109 枚 / 11.02 s**，字节级还原凭
`git diff` 与真源 sha 等值）。🔴 每一刀只改一处真源，跑完当场还原并校验。

| 刀 | 摘掉什么 | 实读尾行 | 红名（逐枚） |
| --- | --- | --- | --- |
| 刀一 | `_frame_verdict:822-823` 那第七枚合取整块摘掉（旧六枚） | **9 failed / 100 passed / 13.10 s** | `test_a_second_copy_of_the_body_in_the_same_round_is_not_a_pass`、`test_the_armed_replacement_that_re_sends_the_body_is_not_a_pass`、`test_the_frame_row_gains_no_column_for_the_new_conjunct`、`test_an_empty_frame_carries_no_body_so_it_cannot_be_a_second_copy`、`test_knife_one_blinding_the_new_reading_leaves_the_disease_green`、`test_knife_two_degrades_the_fixture_without_touching_any_assertion`、`test_the_ruler_does_not_rejudge_a_ledger_that_carries_no_witness`（对照腿：递进证词也不定罪）、`test_the_live_ruler_and_the_offline_audit_agree_on_the_new_conjunct`（账与尺当场不同代）、`test_the_ruler_now_has_teeth_on_both_shapes_at_once`（r218 那枚 7 名名单钉跟着红）|
| 刀二 | `_cross_stream_repeats` 里「只算跨流」那枚边界摘掉（同一条流里的同文帧一起定罪） | **3 failed / 106 passed / 11.47 s** | `test_an_identical_closing_frame_in_one_leg_stays_a_pass`（裁定二那一形被误伤）、`test_the_boundary_is_pinned_against_the_recorded_window`（66/64 那格对不上）、`test_the_coincidence_is_the_witness_not_the_frame_counts`（重合题号从 3 枚涨到一大片）|
| 刀三 | `_record_frames:844` 那一只手摘掉（不再把派生证词交给尺子） | **8 failed / 101 passed / 11.23 s** | 疾病形与带 arm 重发形等 8 枚：`test_a_second_copy_of_the_body_in_the_same_round_is_not_a_pass`、`test_the_armed_replacement_that_re_sends_the_body_is_not_a_pass`、`test_the_frame_row_gains_no_column_for_the_new_conjunct`、`test_an_empty_frame_carries_no_body_so_it_cannot_be_a_second_copy`、`test_the_live_ruler_and_the_offline_audit_agree_on_the_new_conjunct`、`test_knife_one_blinding_the_new_reading_leaves_the_disease_green`、`test_knife_two_degrades_the_fixture_without_touching_any_assertion`、`test_the_exemption_four_criteria_and_the_verdict_call_site_are_untouched`（那一行没了指纹）|

三把刀各咬不同的格：刀一咬「合取里有没有这一腿」，刀二咬「只算跨流这一侧边界」，刀三咬「落盘那一只手有没有把证词递进判定视图」。
另两件常驻机读刀留在件里，不靠手工：`test_knife_one_blinding_the_new_reading_leaves_the_disease_green`（进程内把派生器归零 ⇒ 疾病形翻绿，
证明定罪来自这一格而非别的格）与 `test_knife_two_degrades_the_fixture_without_touching_any_assertion`（疾病形退化成只换字不重发 ⇒ 绿，
两形逐格对判只差一枚事实，删断言做不出这一枚）。

- 🔴 本回合（13:5x）**第四次重挥**，同一组 7 枚件、同一丙案终态：基线 **109 passed / 11.39 s**｜刀一 **9 failed / 100 passed / 11.90 s**｜
  刀二 **3 failed / 106 passed / 12.46 s**｜刀三 **8 failed / 101 passed / 13.91 s**｜还原 **109 passed / 13.71 s**；红名与上表**逐字相同**
  （凭 `C:\Users\fengx\AppData\Local\Temp\r471_blades_self.txt`，驱动仍为 `r471_blades.py`：每刀只动真源一处、`count!=1` 即 abort、跑完字节校验还原）。
  四挥（13:05／13:11／13:22／13:5x）红数一枚不差 ⇒ 红不是刀的偶然，也不是 after 自造的假牙（事故 #83）。

## 十、r447 金样那一格（上一席 ⑤-2：补片后没重跑就退回）

上一席曾代总控试过「往名单里补一个名字」，那片补了 run9 两枚金样后**没重跑就 `git restore` 退回** ⇒ 那句「补片后仍有一枚 r447 金样红」到今天**没有复验凭据**。

🔴 丙案之后这一格**整块消失**：本单一枚名单都没补（`FRAME_READING_KEYS`／`OLD_CELLS`／`_r259_queue_ruler` 三份抄本逐字未动，r447 三枚金样也逐字未动），
所以不存在「补片后未复验」的悬案。当前终态实测：`tests/test_r447_queue_approval_round_and_evidence.py` 在册 **23 枚全绿**
（它不在上面那 109 枚基线里，但含在第十一节 217／233 枚读数里，09-29 单跑 23 枚亦全绿）。

## 十一、验收读数一览（主树 venv 逐枚全名点名，零通配）

- 命令形：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest <逐枚全名> -o addopts= -p no:cacheprovider -q --tb=line`
- 🔴 15 枚名单（逐枚全名、零通配；与上一席「217」基线同一副名单）：`test_r181_text_frame_ruler`／`test_r203_sse_progressive_frames`／
  `test_r210_frame_ledger_of_a_broken_round`／`test_r215_recomputing_run6_frames`／`test_r215_recognizing_a_controlled_correction`／
  `test_r218_ruler_self_calibration`／`test_r223_frame_arrival_clock`／`test_r447_queue_approval_round_and_evidence`／
  `test_r456_error_round_is_not_an_answer`／`test_r456_run9_frame_ledger_recomputes_the_verdict`／
  `test_r456_single_frame_shape_is_not_a_pass`／`test_r459_ask_direct_answer_frames`／`test_r464_one_terminal_answer_stream_per_round`／
  `test_r48_headline_never_enters_the_text_ledger`／`test_r259_awaiting_approval_stops_the_watch`
  （`test_r239_stream_gap_offline` 不在这 15 枚里 —— 它是返工令第 1 项那枚复算件，按点名另跑，215−14＋16＝217 就是这么对上的）。
- 本回合（13:5x）丙案终态亲自复跑：**SET15 ＝ 0 failed / 217 passed / 31.33 s**｜**SET16（15＋本单新钉）＝ 233 passed / 31.89 s**｜
  **SET17（15＋新钉＋`test_r239`）＝ 247 passed / 30.81 s**。改前基线 217 passed / 29.05 s ⇒ 回到**同一个 217／0 failed**，
  这就是丙案的自证：派生格不碰键集，在册一枚没少、没多、没漂。
- 逐枚全名单跑（同一回合，每枚单独一次进程，`-o addopts= -p no:cacheprovider -q --tb=line`），尾行逐枚：
  `r181` **21 passed/0.98 s**｜`r203` **16/10.13 s**｜`r210` **6/9.34 s**｜`r215_recomputing` **4/0.38 s**｜`r215_recognizing` **15/9.07 s**｜
  `r218_ruler_self_calibration` **9/5.39 s**｜`r223` **30/0.66 s**｜`r239_stream_gap_offline` **14/0.30 s**｜`r447` **23/0.67 s**｜
  `r456_error` **6/11.01 s**｜`r456_run9` **15/0.28 s**｜`r456_single` **9/10.57 s**｜`r459` **18/17.33 s**｜`r464` **23/12.05 s**｜
  `r48` **6/9.18 s**｜`r259_awaiting_approval` **16/0.55 s**｜`r471`（本单新钉）**16/0.56 s** —— 逐枚 **0 failed**（凭 `Temp\r471\named_final.txt`）。
- 🔴 读数只出自判据⑥ 规定的那条通道（主树 venv `python.exe`，由 PowerShell 起）。本回合另用一条通道（node 直接 spawn、venv 路径拼写成正斜杠）跑
  同一组件时，`r456_error`／`r456_single`／`r459` 三枚报出 **29 枚假红**，错文逐字为
  `torch/compiler/_cache.py:74: AssertionError: Artifact of type=precompile already registered in mega-cache artifact factory`
  （同一进程里 torch 被两套路径拼写各载一次所致），与本单的尺子无关：同一组件在 PowerShell 通道逐枚 0 failed。这一格留在纸上，免得下一席误账。
- 🔴 没跑 `scripts/run_gate.py`，没跑全量门（同树另有 Agent 在跑，事故 #81）；没起服务、没打模型、没动容器、真库零语句。

## 十二、立案与本单**没做**的事（交总控裁）

1. 🔴 **立案：run9 那一窗产品真发了两遗，不是尺子看错。** 证据是账上现取的逐帧指纹 —— `chart-04` 流 1 第 1 帧与流 0 第 45/46 帧
   `sha`/`chars` 全同（915 字），`insight-07` 同形（590 字）。本单按判据⑤**只立案不修产品**：`app/**` 一枚字没碰。
   R464 并树（`d8fca78`）治的正是批准腿这一形（同字不再发第二枚终答流），所以**下一扇窗理应当变绿**；
   要确认「产品侧真治了 + 尺子侧真拦得住」，需要一扇新窗的实测，而那一格不在本单权限内（不起服务、不打模型）。
2. 没改 `docs/testing/r181-text-frame-readings.md`：判据② 口径纸自 R215 起明文「纸由总控改」，本单只留本件这张影响面纸。
3. 没重判 run2→run9 那四次收窗的任何一格读数；没宣布阶段 A 判据② 验过（它依旧「从没宣布验过」）；没动看板、评测集、`tests/test_evaluation_report.py`、
   `docs/api/contract-v1.md`、`frontend/**`、`app/**` 与第二节列出的别人在途写域。
4. 没 commit／没 push／没建分支／没删文件／没改 `.gitignore` 与 git 配置。交回时工作树 `be-r471` 基点 `d8fca78` 未动。

## 十三、没过哪格与为什么

1. 🔴 **全量门没过，也不能过**：判据⑥ 明禁 `scripts/run_gate.py` 与全量门（同树另有三枚 Agent 在跑，两跑同窗会假红，事故 #81），
   事故 #89 还证明交回通道本身不可依赖 ⇒ 本单的凭据只有第十一节那几副点名件与第九节三把刀，**没有整仓回归数**。
   判回归请按同一 HEAD 的复跑数，别把这里的 217／233／247 读成全量。
2. 🔴 **云端窗没重跑**：判据⑥ 不起服务、不打模型、不动容器、真库零语句 ⇒ 第十二节第 1 条那格「产品真发了两遗」只有
   **离线夹具**（第七节两形）与**历史账复算**（第六节 run9 三枚）两种证据，**没有新窗实测**。R464 并树（`d8fca78`）之后产品侧
   是否真的不再发第二枚终答流，要总控另排一扇窗。⇒ 阶段 A 判据①／② 都没被本单验成绿，也没被验成红，「从没宣布验过」照旧。
3. **口径纸未改**：`docs/testing/r181-text-frame-readings.md` 判据② 那段一字未动（R215 明文「纸由总控改」）。第七枚的成文已在
   `_frame_verdict` 的 docstring（`scripts/eval_transport_ask_v2.py:798-813`）与 `_record_frames:839-843` 头注里备好，可直接抄。
4. **键集那四枚闸没开（丙案）**：`test_r181_text_frame_ruler.py:433`／`test_r223_frame_arrival_clock.py:612`／
   `test_r259_awaiting_approval_stops_the_watch.py:162`／`tests/_r259_queue_ruler.py:54` 逐字未动，帧账一行仍是那 14 格读数＋既有列，
   `cross_stream_repeat_frames` 只在判定那一刻活在 `readings` 里 ⇒ 例外通道（加列＋改四枚对判钉）**没触发也不需要**：
   行内既有那一列 R223 逐帧指纹足够派生，一枚行外/未存的量都不欠。
5. **唯一派生不出的地方已明写，没有偷偷补存**：run6／run7 的账在 R223 之前、不带逐帧指纹，run8p2 的 `frames` 列在而枚枚为空 ⇒
   三档一律读 `REPEAT_DELIVERY_UNMEASURED` 并**不重判当年读数**（第六节那句）。这不是「量出来是 0」，纸上一枚字都没这么说。
6. **run8p2 问答／分析两档的 0/0 是账本就没有**：那份原件只有报告档 20 行，不是测得 0 枚。
7. **`tests/_r259_queue_ruler.py:47/:52/:54` 那枚合取抄本没去动**（不在本单写域）：它只服务队列道自己的键集对判，不产 `criterion_two_holds`；
   补到七枚的那份在册副本是 `scripts/r239_stream_gap_offline_audit.py:84`，它在写域内且已自证「账与尺同代」（第六节第 2 点）。
8. **写域外一枚未碰**：`app/**`（含 `chat.py`）、`frontend/**`、评测集、`tests/test_evaluation_report.py`、`docs/api/contract-v1.md`、
   看板、`docs/handoff/*`、Hooke／R466 那九枚件、Ohm／R478 那六枚件 —— `git diff --name-only d8fca78` 现取只有第五节那五枚文件。
9. **零 commit／零 push／零建分支／零删文件／零改 `.gitignore` 与 git 配置**；基点 `d8fca78` 未动，改动全在工作树里等总控代提交。
10. **上一席 ⑤-2 那格「补片后没重跑就退回」在丙案下不存在**（一枚名单没补，第十节）；本回合 `test_r447_queue_approval_round_and_evidence.py`
    单跑 **23 passed / 0.67 s** 是现取，不是转抄。
