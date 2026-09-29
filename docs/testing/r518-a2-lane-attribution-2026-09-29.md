# R518 · A② 甲案的机械落地：尺子自己说清「这一轮到底有没有逐片腿」（2026-09-29）

> 执行层 R518 · 2026-09-29 · 工作树 `C:\Users\fengx\PycharmProjects\be-r518`，基点 `403db3d`（开工 `git -C` 现取复验＝`403db3d`，`git status --porcelain` 空）
> 🔴 本件**只新增四枚文件**（三枚件 + 本纸），没改任何在册件：`scripts/r518_a2_lane_attribution.py`、`tests/test_r518_a2_lane_attribution.py`、`tests/test_r518_counter_evidence_knives.py`、本件。
> 没 commit、没 push、没跑全量门；`app/**`、`frontend/**`、`docs/handoff/**`、评测集与 `tests/fixtures/**`、
> `scripts/eval_frame_caliber_readout.py`、`scripts/eval_transport_ask_v2.py` 一枚未动（🔴 帧账的键集一格未添）。
> 本节全部读数＝**执行层自报**。

## 1. 一句话

甲案读**可以机械派生**：拿帧账与 sidecar 里今天就存在的六枚键（`text_frames`、`max_stream_frames`、
`frames`、`events`、`answer_chars`、`kind`/`queue`，外加 sidecar/answers 的 `tool_calls`），
run9 那 105 行**逐枚**落格，复现上 `docs/testing/r506-a2-reading-2026-09-29.md` §4 那张三堆分诊表：
堆一 8 枚 + 天然短 1 枚 = 9 枚 `not_applicable`、堆二 2 枚进 `no_answer`、`chart-01` 单列、
`tool-04`/`report-02` 照旧红、`insight-07`/`chart-04` 记「不重判」。**一枚都不需要新键。**
两件事今天仍然派生不出，本件照实交账而不是拿它换绿：**腿名**（0/105）与**没有到达坐标的那两扇旧窗**
（run6 85 枚、run7 9 枚落 `undecidable`）。

## 2. 两读并列（run9，件=`scripts/r518_a2_lane_attribution.py`）

下面这段取自**读数件的原样输出**：数字、名单与算式一字未改；为省纸只略去表头那三行
（路径／sha256 读前读后／行数与尺寸闸）与两行零计数（`[not_applicable/队列道] 0 枚`、
`[有腿证词与逐帧列对质不上] 0 枚`），末两枚长注缩成短语。完整原样输出用 `--rows`／`--format json` 取。

```
读 1 · ②原文全分母（历史可比那把尺；件=scripts/r239_stream_gap_offline_audit.py::judge_row）
   绿 94/105  红 11 枚：approval-06,chat-03,chat-06,chat-09,chat-10,data-09,doc-07,metric-02,metric-16,scope-01,scope-02
   合格线：②-a text_frames > 1（audit.event_count_gt_1）∧ ②-b 逐字无缺

== 读 2 · 甲案分腿读（计划书 §6 追加节 09-29 裁定：②只适用于确有逐片腿的轮）
   分母算式：rows = in_scope + not_applicable + no_answer + self_added + undecidable
   105 = in_scope_has_leg 93 + not_applicable 9 + no_answer 2 + self_added_cell_only 1 + undecidable 0  守恒=True
   · 甲案②原文两格读：93/93  红=—
   · 甲案严读（②原文 ∧ 账上 criterion_two_holds）：91/93  红=report-02,tool-04
   [not_applicable/无逐片腿] 8 枚：approval-06,chat-03,chat-06,chat-09,chat-10,doc-07,metric-16,scope-01
   [not_applicable/短过尺寸闸] 1 枚：data-09
   [no_answer] 2 枚：metric-02,scope-02
   [self_added_cell_only] 1 枚：chart-01
   [undecidable] 0 枚：—
   不重判：chart-04,insight-07　　腿名可派生行数：0/105
```

分母怎么算的（甲案读那一枚）：`105 − 9（不适用） − 2（本轮没交付终答） − 1（自加格单列） − 0（派生不出）＝ 93`，
即**只有机械派生出「某条流自己攒出了第二枚文本帧」的轮**进分母；分子两枚并列，一枚只看②原文两格，
一枚再与账上那枚 `criterion_two_holds` 合取。🔴 读 1 那枚 94/105 与 r506 §0 逐字同数，本件一枚数都没动它
（它调的就是 r239 判器的 `judge_row`，不是本件重算的第二把尺）。

## 3. 逐枚复现 r506 §4 的对照（14 枚 + 天然短 1 枚）

| 题号 | r506 §4 那一堆 | 本件派生的格/理由 | 证词（用了哪枚既有键） | 一致 |
|---|---|---|---|---|
| `doc-07` `chat-03` `chat-06` `chat-09` `chat-10` `metric-16` `approval-06` `scope-01` | 堆一·无逐片腿（8 枚） | `not_applicable` / `no_piece_leg_witness` | `text_frames==1` ∧ `sidecar.tool_calls==0` ∧ `events` 一枚 `step` 都没有 | ✅ 8/8 逐枚点名 |
| `data-09` | 天然短（1 枚，15 字） | `not_applicable` / `below_size_gate` | `answer_chars=15 < 尺寸闸 20`（数值现取 `app/agents/nodes.py:327`） | ✅ |
| `metric-02` `scope-02` | 堆二·无终答轮（2 枚） | `no_answer` | `text_frames==0`（一帧 `event: text` 都没发过），`kind=error_event` | ✅ 2/2 |
| `chart-01` | 堆三·自加格（裁定项） | `self_added_cell_only` | `text_frames=2` 而 `max_stream_frames=1`（两条流各一枚整段帧），红因只有 `max_stream_frames>1` | ✅ |
| `tool-04` `report-02` | 堆三·批准腿重发（不许裁绿） | `in_scope_has_leg` **且红** | `max_stream_frames=2 / 43 > 1` ⇒ 有腿证词在位；红因 `uncorrected_breaks==0` | ✅ 2/2 |
| `insight-07` `chart-04` | 堆三·R471 翻面（不重判） | `in_scope_has_leg` + 明记 `not_rejudged` | 账上 True、现尺复算 False（`ledger_drift`）⇒ 不追加定罪也不裁绿 | ✅ 2/2 |

**复现不上的：run9 这一窗零枚。** 另三窗本件也现跑了，但它们复现的是 r506 §3 那张三形对照，
不是 §4 那张表 —— 差异逐枚点名在 §6。

## 4. 派生规则（写死在 `scripts/r518_a2_lane_attribution.py:238` `derive_lane_state`）

三态（`:78-81`）：`has_piece_leg` / `no_piece_leg` / `undecidable` —— 🔴 没有第四枚取值，
也没有「派生不出就当有腿」或「当没腿」这一读。落格五枚（`:84-89`）互斥且守恒。

判定顺序（`:246`起，一枚都不许改序 —— 改序就是把一格抹进另一格）：

1. `text_frames == 0`：`kind` 以 `queued` 起或 `queue` 格非空 ⇒ `not_applicable/queue_path_no_sink`；
   否则 ⇒ `no_answer`（本轮根本没交付终答，与流式无关）。
2. **对质**（`:259`，`witness_conflict` :223）：拿同行 R223 逐帧列 `frames` 自己重算 `(流数, 单流最大帧数)`，
   与汇总格 `streams`/`max_stream_frames` 对不上 ⇒ `undecidable/witness_conflict_on_frames`。
3. `max_stream_frames > 1`（:266）⇒ **`has_piece_leg`**（唯一的正面证词：有一条流自己攒出第二枚文本帧，
   只有 sink 在逐片喂它才做得到）。
4. `text_frames > 1` 而 `max_stream_frames <= 1`（:274）⇒ `undecidable`：多枚帧分属多条流、
   没有一条流在逐片累计 ⇒ 既无有腿证词也不足以断言无腿。若此时严读的红因**只有** `max_stream_frames>1`
   那一枚自加格 ⇒ 落 `self_added_cell_only` 单列（:344）。
5. `text_frames == 1`：队列道 ⇒ 不适用；**帧账不带 `events` 列** ⇒ `undecidable/no_arrival_coordinates`
   （:289，🔴 拿「列不存在」当「没跑腿」就是用缺证词当证据）；join 不到 `tool_calls` ⇒
   `undecidable/no_tool_calls_join`；`tool_calls==0` ∧ 无 `step` ⇒ `no_piece_leg`（:301；
   这一形在码上就是无 sink 路径一次性交付整段 —— `app/api/v1/chat.py:2973` `yield text_sse_frame(full_text, ...)`）；
   `answer_chars < 尺寸闸` ⇒ `below_size_gate`（:308）；剩下那一形（腿跑过却只到一枚帧、答案又不短）⇒
   `undecidable/piece_or_drop_indistinguishable`（:321，见 §5）。

每枚落格都带回 `evidence[]`（人话证词）与 `keys_used[]`（用了哪枚键）；本件读的键全在
`:111 FRAME_KEYS_USED`／`:114 SIDECAR_KEYS_USED` 两份名单里，钉在
`tests/test_r518_a2_lane_attribution.py:276::test_b3_...` —— 要用了账里没有的键，那枚钉当场红。

## 5. 🔴 今天仍机械派生不出的形状（本单最有价值的产出，照实列）

| 形状 | 为什么派生不出 | 本件交回什么 | 要治它得动什么 |
|---|---|---|---|
| **腿名**（哪条腿交付的终答） | 帧账一行没有 `worker`/腿名列：`scripts/eval_transport_ask_v2.py:735` 的 `_frame_readings` 返回值里就没有（🔴 坐标漂移：r506 纸面写作 `:725`，本树基点 `403db3d` 现取 `:735`，差 10 行，见本节末），且那枚键集受 `tests/test_r181_text_frame_ruler.py:43` `FRAME_READING_KEYS` 甲案钉约束（加格＝当场红） | `leg_names.derivable_rows = 0/105`，纸面明写「只断言 sink 腿之有无，不断言腿名」（`r518:472`） | 后端日志 `[R149] ... leg=... call=... dropped=...`（`app/api/v1/chat.py:2900-2908`，🔴 r506 纸面写作 `:2851-2857`，本树现取漂移 +49 行）或现场复跑；🔴 不是给帧账加键 |
| **run6 / run7 那两窗的 85 + 9 枚单帧轮** | 那两本在册帧账不带任何 R223 到达坐标（键集实测 19/21 枚，无 `events`/`frames`）⇒ `step` 证词与逐帧对质都不存在。r506 §5 第 5 条早已记过这一笔 | `undecidable/no_arrival_coordinates`，并把「这一格里②原文仍红」的枚数与题号单独印一行（🔴 不裁绿） | 不可治：那是当年没记的账，永远不可判 |
| **`dropped > 0` 那一族**（片到过收端、被 `_AnswerPieceStream.frame_for` 折掉） | SSE 上没出现过的帧不留任何证词 ⇒ 「非白名单腿」与「片被折掉」在两本在册账里**不可分**（r506 §2.A 第 8 条） | `undecidable/piece_or_drop_indistinguishable`（run9 这一窗 0 枚；形已落码并钉在 `r518:321` + `test_d4`） | 收端日志那三枚计数（`leg=`/`call=`/`dropped=`，`app/api/v1/chat.py:2906-2907`；折片的码在 `app/api/v1/chat.py:1776` `frame_for`），不是帧账 |
| **被人整本重造的账**（连 `frames` 逐帧列一起改） | 对质件只能证「两列自洽」，不能证「账没被人改过」 | 分诊逐枚对不上 ⇒ 钉红（`test_d2b`），但**不假称已封**；防线是 sha256 + 自洽对质 | 属取证域，不属读数件 |
| **队列道那一窗（run8p2）** | 这一格**能**派生（`kind`/`queue` 两枚既有键），落在 `not_applicable/queue_path_no_sink` ⇒ 20/20 整窗不适用，甲案分母 0 | 已派生，不算欠账 | —— |

`data-09` 那一格本件**故意不在**「无腿」那一格：`lane_state` 仍交回 `undecidable`（腿是否白名单腿不可知），
只有**格子**落 `not_applicable/below_size_gate` —— 它主张的是「这一轮攒不出第二枚帧」，不是「这一轮没有腿」。
同理，尺寸闸那一格排在地 5 条的后半（要先有到达坐标与 `tool_calls`）：`answer_chars < 20` 单独一枚
不足以把「没腿」与「天然短」分开，所以 run6/run7 的 `data-09` 只能落「派生不出」，不许借尺寸闸抢答。

🔴 **坐标漂移点名（本纸现取，与 r506/r507 纸面不同）**：`_frame_readings` 本树在
`scripts/eval_transport_ask_v2.py:735`（r506 §5 第 2 条写 `:725`）；`[R149]` 那行日志在
`app/api/v1/chat.py:2900-2908`（r506 §2.A 第 8 条写 `:2851-2857`）；`_AnswerPieceStream.frame_for` 在
`app/api/v1/chat.py:1776`（同条写 `:1737`）。三处都是他单并树之后的行号漂移，**不是本件改的**
（`git diff --numstat` 对全仓为空，`app/api/v1/chat.py` 与 `scripts/eval_transport_ask_v2.py` 一枚未动）。

## 6. 另外三扇窗的读数（同一枚件、同一套键，现跑）

| 帧账 | 读 1（②原文） | 105=? 五格守恒 | 甲案②原文读 | 甲案严读 | 派生不出 | 与 r506 §3 的差异点名 |
|---|---|---|---|---|---|---|
| run7 | 96/105 | 105 = 95 + 0 + 0 + 1 + 9 | 95/95 | 93/95（红 `chart-03`、`tool-04`） | 9 枚 | §4 那族同名九枚（`doc-07 chat-03 chat-06 chat-09 chat-10 data-09 approval-06 scope-01 metric-17`）**没复现成 `not_applicable`**，全部落 `undecidable/no_arrival_coordinates` —— 那本账 21 枚键里没有 `events`/`frames`，`step` 证词与逐帧对质都不存在（§5 第 2 行） |
| run6 | 19/105 | 105 = 0 + 0 + 1 + 19 + 85 | 0/0 | 0/0 | 85 枚 | `no_answer` 1 枚＝`tool-03`（该窗唯一 `text_frames==0`）；19 枚落 `self_added_cell_only`（那 19 枚 `approved_ok` 都是两条流各一枚整段帧）；85 枚单帧轮＝`undecidable`（无到达坐标）。🔴 本件对 run6 **一枚 `not_applicable` 都不派生** —— 与 r506 §3「那一窗屏上从来没有过第二条片」一致，但那是**腿还没接上**，不是本件证到了无腿 |
| run8p2 | 0/20 | 20 = 0 + 20 + 0 + 0 + 0 | 0/0 | 0/0 | 0 枚 | 20/20 全落 `not_applicable/queue_path_no_sink`（`kind=queued_polled`×19 / `queued_stalled`×1、`queue` 格枚枚非空、`text_frames` 全 0）⇒ 复现上 r506 §3「A② 对整窗不适用，20/20 红是道不对，不是字丢了」 |

完整原始输出（含 sha256 读前读后、逐枚名单）在 `--rows`／`--format json` 两种视图里，件名同上；
本件的读数以 `docs/testing/sidecar-run9-frames.jsonl`（sha256 全值
`016e9525121c2c6af41da52c199ef843a1425fe853664324137440599823ec18`，读完再取＝同值，未改动）为准。

## 7. 反证刀（六把，逐枚点名被摘那条腿与红数）

跑法：把下面每一枚改动**临时**落到 `scripts/` 里那一枚函数体上，跑两枚新钉（33 枚），
再把文件逐字节还原（`sha256[:16]` 与基线复验相同；`scripts/r239_stream_gap_offline_audit.py`
终态与 `403db3d` 逐字相同）。全部读数＝**执行层自报**。

| 刀 | 摘掉的那枚腿 | 红数 | 红的是哪几枚钉 |
|---|---|---|---|
| K1 | 无腿判据里 sidecar 那枚合取 `tool_calls == 0`（`r518:301` 只剩 `events` 无 `step`） | **1** | `test_d1a`（伪造 `tool_calls` 不再被察觉 ⇒ 甲案读不再当场红） |
| K1b | 无腿判据里帧账那枚合取「`events` 无 `step`」（`r518:301` 只剩 `tool_calls==0`） | **1** | `test_d1c`（往 `events` 塞一枚 `step` 不再被察觉） |
| K2 | 有腿证词的对质件（`r518:223` `witness_conflict` 直接回 `None`） | **2** | `test_d2a`、`test_c5`（只改汇总格就蒙混成「有腿」） |
| K4 | 「无到达坐标＝派生不出」那一读，改读成「无腿＝不适用」（`r518:289` 的取值改判） | **3** | `test_c1`、`test_c3`、`test_d4`（拿缺证词当证据：run6/run7 那 94 枚被整块裁成不适用） |
| K5 | 尺寸闸那一格（`r518:308` 的 `answer_chars < min_chars` 短路成永不成立） | **6** | `test_a1`、`test_a3`、`test_a8`、`test_d0`、`test_d1a`、`test_d2c`（`data-09` 从 `not_applicable` 被挤成派生不出，天然短与无腿并脸） |
| K3 | ②原文那枚合格线：`r239:174` `event_count_gt_1` 从 `> 1` 手改宽成 `>= 1` | **14** | `test_a1`、`test_a2`、`test_b1`、`test_b2`、`test_c1`、`test_c3`、`test_c8`、`test_d0`、`test_d1a`、`test_d1c`、`test_d2a`、`test_d2c`、`test_d3b`、`test_d4`（94/105 立刻变 103/105：改宽合格线＝把 9 枚单帧轮直接判绿） |

派工词点名的三把都在：**刀一**＝K1/K1b/`test_d1a`/`test_d1c`（改 sidecar 既有键 `tool_calls` 或帧账 `events`
把无腿轮伪造成有腿 ⇒ 甲案读当场红，且伪造者一枚绿都买不到）；**刀二**＝`test_d2a`/`test_d2b`/`test_d2c`
＋K5（`not_applicable` 那一格整块抹成绿：改汇总格被对质拦下、连逐帧列一起改则分诊逐枚对不上、把落码里
那道闸摸掉则分母 93→102、红 2→11）；**刀三**＝K3/`test_d3`/`test_d3b`（合格线从 `>1` 改宽成 `>=1` ⇒
读 1 那枚 94/105 当场漂、钉当场红，另钉一枚「甲案分母不跟合格线走」）。
既有断言一枚未改弱：`tests/test_r506_*`、`test_r507_*`、`test_r471_*`、`test_r239_*`、`test_r181_*`
与本单两枚钉同跑 **116 passed**（无改判器、无 skip/xfail）。

## 8. 命令原文与读数（执行层自报）

```
cd C:\Users\fengx\PycharmProjects\be-r518
PY=C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe

# 出数（四扇窗，全 rc=0；含 sha256 读前/读后未改动与五格守恒两道自证）
$PY scripts/r518_a2_lane_attribution.py
$PY scripts/r518_a2_lane_attribution.py --frames docs/testing/sidecar-run7-frames.jsonl --sidecar docs/testing/sidecar-run7.jsonl --answers docs/testing/answers-run7.jsonl
$PY scripts/r518_a2_lane_attribution.py --frames docs/testing/sidecar-run6-frames.jsonl --sidecar ... --answers ...
$PY scripts/r518_a2_lane_attribution.py --frames docs/testing/sidecar-run8p2-frames.jsonl --sidecar ... --answers ...
$PY scripts/r518_a2_lane_attribution.py --format json
$PY scripts/r518_a2_lane_attribution.py --rows

# 自验（逐枚点名文件；未跑全量门）
$PY -m pytest tests/test_r518_a2_lane_attribution.py tests/test_r518_counter_evidence_knives.py -q
  → 第一遍 33 passed / 0 skipped（1.42 s）；第二遍 33 passed / 0 skipped（1.37 s）
  → 纸面改坐标/补身份码之后复跑：33 passed / 0 skipped（2.03 s、9.65 s、2.18 s、1.68 s、1.21 s）
  → 本纸**末次改字之后**再跑两遍：33 passed / 0 skipped；同名八件 116 passed / 0 skipped
$PY -m pytest tests/test_r239_stream_gap_offline.py tests/test_r506_a2_single_frame_not_green.py \
    tests/test_r506_a2_ledger_required_keys.py tests/test_r507_blind_instrument_returns_none.py \
    tests/test_r181_text_frame_ruler.py tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py \
    tests/test_r518_a2_lane_attribution.py tests/test_r518_counter_evidence_knives.py -q
  → 116 passed / 0 skipped（3.04 s）
  → 复跑同名八件：116 passed / 0 skipped（21.35 s；同机两枚兄弟在写，耗时上浮，枚数未变）
  → 四扇窗复跑读数件：run9 / run7 / run6 / run8p2 全 rc=0，读数与本纸 §2、§6 逐字相同
```

🔴 如实记一句：本纸**自己**最后一次改字（就是这段）不可能被「改字之后」的复跑覆盖，所以本件按
「代码与两枚钉定稿后、上面逐笔点名的那几遍各 33 passed / 0 skipped」记（另有 §7 反证刀
期间的临时跑，那次盘面是**故意脏**的，不计入）；末次改字只动纸面文字，一枚 .py 未动
（`git diff --numstat` 全仓为空，三枚产物的 sha256 见下）。

钉的分布：`tests/test_r518_a2_lane_attribution.py` 22 枚（a 组逐枚复现分诊 8 枚、b 组两读与「不加键」6 枚、
c 组三态与另三窗 8 枚），`tests/test_r518_counter_evidence_knives.py` 11 枚（d0 基线、刀一 2 枚、刀二 3 枚、
刀三 2 枚、假零防线 3 枚）。两枚钉都**只读**在册四本账与自己的 ``tmp_path`` 副本，零网络、零容器、零模型。

本单产物身份码（**纸面定稿之后现取**，供总控并树前复验；本纸自己的 sha 由总控取，本件不自封）：

| 产物 | 行数 | 字节 | sha256 前 16 位 |
|---|---|---|---|
| `scripts/r518_a2_lane_attribution.py` | 604 | 34051 | `e21961483787f64d` |
| `tests/test_r518_a2_lane_attribution.py` | 420 | 24189 | `7d0f1b79cabf95bc` |
| `tests/test_r518_counter_evidence_knives.py` | 280 | 14912 | `18153795e2c43a61` |

## 9. 本件没做什么（禁碰自证）

- 没给帧账加任何键、没改 `scripts/eval_transport_ask_v2.py` 与 `scripts/eval_frame_caliber_readout.py`
  （`git diff --numstat` 对全仓为空；未跟踪的新件只有本件那四枚产物）。
- 没改 `scripts/r239_stream_gap_offline_audit.py`（派工词允许改它的读数面，本件不需要：读 1 直接调它的
  `judge_row`，改它反而会让 94/105 那枚历史可比数失去同代性）。
- 没改 `app/**`、`frontend/**`、`docs/handoff/**`、评测集与 `tests/fixtures/**`；没动计划书那节（只引用）。
- 没跑 `scripts/run_gate.py`（同机兄弟在写＋本席今晚四小时真机窗，门交总控）。
- 没 commit、没 `git add`、没 push、没起服务/容器/模型、没连库。
- `tests/test_r506_a2_single_frame_not_green.py` 那枚「零文本帧行必须继续占住②分母」的钉**照旧成立**：
  读 1 里 `metric-02`/`scope-02` 仍红（r518 不改判器，只在**甲案读**里把它们挪进 `no_answer` 格并逐枚点名）。

## 10. 写给下一班（别把本件读成 A② 已绿）

1. **甲案读 91/93 ≠ 翻绿**：那两枚红（`tool-04`/`report-02`）是批准腿跨流重发，只有产品码能吸收
   （R464 已并树 `d8fca78`）⇒ run10 必重测这两枚，绿了挂凭据、红了立回归单。
2. **腿名那一格今天仍欠**：要证到腿名只有两条路 —— 读后端 `[R149] ... leg=... call=... dropped=...`
   日志（本树现取 `app/api/v1/chat.py:2900-2908`，见 §5 末），或现场复跑。🔴 第三枚「给帧账加一列
   `worker`」这条路本件**没走**，也不该走（`FRAME_READING_KEYS` 那枚甲案钉就是拦这个的，且加了也没消费者）。
3. **run6/run7 那两窗永远不可判**（账里没记到达坐标）⇒ 任何「§2.7 那条合并约束已在三形对照上核过」
   的说法都不成立，只有 run8p2/run9 两窗带坐标。
