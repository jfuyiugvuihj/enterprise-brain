# R614 · run19 两枚「未校正断裂」的归因（2026-10-03）

一句话结论：**判据② 在 run19 读 False 是量具口径缺陷，不是产品缺陷，也不是环境抖动。**
决定性那一条是 R215 豁免四条件的**第④条**（`scripts/eval_transport_ask_v2.py:676`）：它拿「本轮交回
评分器的那份字」当比对对象，而 `report-09`／`tool-02` 这两枚断裂发生在**挂起轮**（stream 0）里，交回的
那份字来自**批准腿**（stream 1）——两枚断裂帧逐字等于侧车的 `pre_answer`（挂起轮自己交付的终答），却
逐字不等于批准腿的终答，于是**结构性拿不到豁免**。底层那次换源本身属 R149／R203／R210 在册那一族，
且产品侧的受控整段替换**确实执行了**（证据见 §3）。

本单零改码、零改测试、零跑门、零动容器、零打模型；仓库内唯一产物就是本文件。

## 0. 取证面（全部只读，落盘件原文）

- 帧账：`%TEMP%\evalrun\run18-sidecar-frames.jsonl`／`run19-sidecar-frames.jsonl`（各 105 行，一题一行）
- 侧车／答案／报告：`run1{8,9}-sidecar.jsonl`、`run1{8,9}-answers.jsonl`、`run1{8,9}-report.json`
- 窗指纹（两窗逐字相同，除时刻）：`run18.window.json`／`run19.window.json` 均
  `revision=a2bbf133bd80623507e1d6c0a51bb16c13ba5b7d`、`index_backend=pgvector`、
  `fixture_sha256=686c564ff2985744e6f050e5ea7639500c99bd80b3e32fc3a85e585f5ecdd79b`、
  `transport=eval_transport_ask_v2:transport`、`container=enterprise-brain-backend-1`、`probe_ok=true`、`dry_run=false`
- 分析件（仓库外，TEMP）：`%TEMP%\r614\t1.py`…`t5.py`，只做 JSON 读数；派生格直接 import 在册那一把尺
  （`_cross_stream_repeats`），不另起第二把
- 口径真源：`scripts/collect_evaluation_answers.py:32-41`（R215 抬头）、
  `scripts/eval_transport_ask_v2.py:338-372`（`_consume`：`armed` 只在紧邻的上一枚事件上成立）、
  `:415-427`（`_count_text_frame`：前缀单调只在同一条流内判）、`:653-680`（`_corrective_readings` 四条件）、
  `:791-833`（`_frame_verdict` 七枚合取）、`docs/testing/r181-text-frame-readings.md:44-68,96-97`
- 产品侧：`app/api/v1/chat.py:2870-2882`（片帧出口）、`:2890-2931`（终答选择 + `answer_needs_correction`）、
  `:2982-2991`（R210 那对 step 夹着收尾整段帧）、`:1777-1806`（`_AnswerPieceStream.frame_for`／`_open`）、
  `:1919-1949`（`_select_final_answer` 优先 `worker_answers`）、`:3549-3568`（批准腿 `_ApprovedAnswerStream` 武装出口）

## 1. 六枚对照表（两窗并排，读数自相对齐）

### 1A. 判据② 读数（帧账原格，未做任何换算；`extra_chars` 六枚×两窗全为 0）

| 题号 | 窗 | kind | approved | text_frames | max_stream_frames | prefix_breaks | corrective_replacements | uncorrected_breaks | missing_chars | 末事件 | latency_ms | holds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| metric-03 | run18 | ok | false | 3 | 3 | 1 | 1 | 0 | 0 | done | 29654.7 | true |
| metric-03 | run19 | ok | false | 10 | 10 | 1 | 1 | 0 | 0 | done | 31275.7 | true |
| metric-11 | run18 | ok | false | 2 | 2 | 1 | 1 | 0 | 0 | done | 42226.3 | true |
| metric-11 | run19 | ok | false | 2 | 2 | 1 | 1 | 0 | 0 | done | 42976.0 | true |
| report-06 | run18 | ok | false | 21 | 21 | 1 | 1 | 0 | 0 | done | 70611.1 | true |
| report-06 | run19 | ok | false | 21 | 21 | 1 | 1 | 0 | 0 | done | 70472.8 | true |
| report-09 | run18 | approved_ok | true | 115 | 114 | 0 | 0 | 0 | 0 | done | 63461.6 | true |
| **report-09** | **run19** | **approved_ok** | **true** | **5** | **4** | **1** | **0** | **1** | **0** | **done** | **32322.6** | **false** |
| scope-04 | run18 | ok | false | 11 | 11 | 1 | 1 | 0 | 0 | done | 24406.3 | true |
| scope-04 | run19 | ok | false | 5 | 5 | 1 | 1 | 0 | 0 | done | 17260.1 | true |
| tool-02 | run18 | approved_ok | true | 14 | 13 | 0 | 0 | 0 | 0 | done | 20930.9 | true |
| **tool-02** | **run19** | **approved_ok** | **true** | **9** | **8** | **1** | **0** | **1** | **0** | **done** | **25230.2** | **false** |

旁格（同一批行，一并摊开以免只给结论）：`streams` 六枚在两窗都是 1/1/1/2/1/2——`report-09`／`tool-02` 两窗**同样是挂起后批准**（各两条流），差别只在挂起轮里长没长出坏形；
`attempt` 全 1，`sentinel` 全 false，`last_frame_covers_answer` 全 true；
R215 恒等式 `prefix_breaks == corrective_replacements + uncorrected_breaks` 在两窗**各 105 行**上零违反；
派生格 `cross_stream_repeats`（R471 第七枚，从行内逐帧指纹现算）这六枚全为 0。

### 1B. 断裂落在哪一条流、那一枚帧到底是什么字

| 题号 | 窗 | per_stream 帧数 | 断裂所在流/序号 | ①该流末帧 | 断裂帧 字数/sha | 侧车 `pre_answer` 字数/sha | 终答 字数/sha | 上一片帧→断裂帧 |
|---|---|---|---|---|---|---|---|---|
| metric-03 | run18 | [3] | s0 #3 | 是 | 369/`2bdf4744e2a7` | 无（非挂起轮） | 369/`2bdf4744e2a7` | 23.39 s |
| metric-03 | run19 | [10] | s0 #10 | 是 | 342/`50aedfd7f62d` | 无 | 342/`50aedfd7f62d` | 23.57 s |
| metric-11 | run18 | [2] | s0 #2 | 是 | 912/`6fe3af42ab10` | 无 | 912/`6fe3af42ab10` | 32.93 s |
| metric-11 | run19 | [2] | s0 #2 | 是 | 906/`c9318cd4e241` | 无 | 906/`c9318cd4e241` | 34.70 s |
| report-06 | run18 | [21] | s0 #21 | 是 | 2131/`2c1492fe1f40` | 无 | 2131/`2c1492fe1f40` | 36.15 s |
| report-06 | run19 | [21] | s0 #21 | 是 | 2544/`e49cbcda1d49` | 无 | 2544/`e49cbcda1d49` | 41.04 s |
| report-09 | run18 | [114, 1] | 无断裂 | — | — | 2364/`82f3ba9d0729` | 2417/`c28000a2d4f5` | — |
| **report-09** | **run19** | **[4, 1]** | **s0 #4** | **是** | **636/**`3d572eff169a`**＝`pre_answer`** | **636/**`3d572eff169a` | **689/**`9a52943ae2d8` | **21.35 s** |
| scope-04 | run18 | [11] | s0 #11 | 是 | 374/`0c933077b3e9` | 无 | 374/`0c933077b3e9` | 17.14 s |
| scope-04 | run19 | [5] | s0 #5 | 是 | 374/`0c933077b3e9` | 无 | 374/`0c933077b3e9` | 12.91 s |
| tool-02 | run18 | [13, 1] | 无断裂 | — | — | 225/`f42f05809da2` | 278/`cf1c4c36b875` | — |
| **tool-02** | **run19** | **[8, 1]** | **s0 #8** | **是** | **225/**`f42f05809da2`**＝`pre_answer`** | **225/**`f42f05809da2` | **278/**`cf1c4c36b875` | **9.93 s** |

两枚红字里最要命的一格：**断裂帧的 sha 与侧车 `pre_answer`（挂起轮交付的那份字）逐字相同**。
`sha256(pre_answer)[:12]` 现算：report-09 为 `3d572eff169a`（636 字），tool-02 为 `f42f05809da2`（225 字）；
对照同一行的 `answer_sha`：`9a52943ae2d8`（689 字）／`cf1c4c36b875`（278 字）——**不同**。
⇒ 那枚换源的帧**就是**挂起轮交付的终答，它只是不等于批准腿交回评分器的那份字。

另一枚旁证：`tool-02` 的挂起轮文本在两窗**逐字相同**（`f42f05809da2`/225 字），终答也**逐字相同**
（`cf1c4c36b875`/278 字）。同一份字，run18 是 13 帧一路累计上来的（无坏形），run19 是 7 帧停在 136 字、
第 8 帧直接跳到 225 字（长出一枚坏形）。⇒ 两窗之差落在**实时腿追到哪一帧**，不落在这轮交付了什么。

## 2. R215 豁免四条件逐条判定（只判 `report-09`／`tool-02`，run19）

四条件真源＝`scripts/eval_transport_ask_v2.py::_corrective_readings`（`:653-680`），纸面＝
`docs/testing/r181-text-frame-readings.md:56-60`，口径写死处＝`scripts/collect_evaluation_answers.py:32-41`。
四条**同时**成立才豁免一枚。

| 条件 | report-09（run19） | tool-02（run19） |
|---|---|---|
| ① 是**这一条流**的最后一枚 text 帧（`:672`） | **满足**——帧账原文 `{"stream":0,"at":4,"chars":636,"sha":"3d572eff169a","prefix_break":true}`，同行 `per_stream[0].frames`=4 | **满足**——`{"stream":0,"at":8,"chars":225,"sha":"f42f05809da2","prefix_break":true}`，`per_stream[0].frames`=8 |
| ② 本轮至多一枚（`:667`） | **满足**——该行 `prefix_breaks`=1，唯一候选 | **满足**——同上 |
| ③ 前面紧邻一枚 `step(tool=answer_correction, status=running)`（`:674`，认脸在 `:431-439`） | **满足（推定，盘上读不到 payload）**——`events` stream 0 尾部：`at=10 step`→`at=11 text`→`at=12 step`→`at=13 hitl` | **满足（同限定）**——`at=11 step`→`at=12 text`→`at=13 step`→`at=14 hitl` |
| ④ 它的正文与最终交付的 `answer` 逐字相等（`:676`） | 🔴 **不满足**——断裂帧 636/`3d572eff169a` ≠ 终答 689/`9a52943ae2d8`；而这枚帧逐字等于挂起轮交付的 `pre_answer` | 🔴 **不满足**——225/`f42f05809da2` ≠ 278/`cf1c4c36b875`；同样逐字等于 `pre_answer` |

**run19 里没满足的就是第④条，一条，且只有这一条。** ①② 是账上一手读数；③ 是「码路＋账上紧邻 step＋
与已豁免行同形」三条推定——`_note_event_arrival`（`:497-503`）只落事件名与类别，不落 `data`，
所以 payload 里的 `tool`/`status` 在盘上不可读（这一格进 §5）。

③ 敢推定的三条凭据：

1. 码路：`app/api/v1/chat.py:2984-2991` 是 `step(running)` → `text_sse_frame(full_text)` → `step(done)`，
   两枚 yield 之间只有 `await asyncio.sleep(0)`，同一条生成器不可能在中间插入别的事件；而收端 `armed`
   的语义（`scripts/eval_transport_ask_v2.py:351-371`）恰好就是「上一枚事件是不是那枚 step」。
2. 账形：这两枚的 `step → text → step` 三明治与两窗里**被量具自己豁免过**的四枚完全同形
   （metric-03 run19 `15 step→16 text→17 step`；scope-04 run19 `8 step→9 text→10 step`）。
3. 内容：断裂帧逐字等于该轮交付的 `pre_answer`，正是 `:2987` 那一枚收尾整段帧才会有的形状
   （`:2966` 先 `_save_message`，`:2987` 再发同一份 `full_text`；批准腿读屏那一行由 `:1891-1910`
   `_round_screen_answer` 承担）。

**结构性那一刀（不是巧合，全账可算）**：两窗各 19 轮挂起后批准（`kind=approved_ok`），**19/19** 满足
「终答以挂起轮那份字为前缀且严格更长」，**0/19** 出现「终答逐字等于挂起轮那份字」。
样本：run19 report-09 636→689、run18 report-09 2364→2417、两窗 tool-02 225→278。
⇒ 只要换源发生在**挂起轮**里，第④条必然不满足（批准腿多吐一个字都判红），这一族的
`uncorrected_breaks` 恒等于 `prefix_breaks`。这不是「这次运气差」，是口径的覆盖范围。

## 3. 定性结论（三选一）：**量具口径缺陷**

判据② 的豁免账只认得**单流轮**里的受控纠正。R215 写四条时的在册用例全是「一条 /ask 流」的形状
（`tests/test_r215_recognizing_a_controlled_correction.py:127-139` 正向用例＝单流；`:210-221` 那枚唯一
的多流用例里，两条流的末帧**都**逐字等于同一个 `REPLY`，所以④ 恰好能过）。
「挂起轮换源＋批准腿再交付」那一形（`streams=2`、断裂在 stream 0、终答来自 stream 1）**在册用例一枚
都没覆盖**；纸面 `docs/testing/r181-text-frame-readings.md:96-97` 对挂起后批准那 18 枚只写了「跨流不比
前缀，所以坏形仍读 0」，默认挂起轮内部不会长坏形。A② 第一次拿到读数，就撞上这个未覆盖形。

### 3.1 为什么不是产品缺陷（收尾真做了受控校正）

- 断裂帧逐字等于该轮交付的 `pre_answer`（sha 现算对上），账上是 `step → text → step` 三明治
  （`app/api/v1/chat.py:2984-2991` 的形状），屏上落的是整段替换而不是拼接。R210 的设计意图达成
  （并树 `fe5b180`：断流轮屏上不再把「半截真话 + 离线话术」拼成一句）。
- 轮级一致性四格全绿：`missing_chars=0`、`extra_chars=0`、`last_frame_covers_answer=true`、派生
  `cross_stream_repeats=0`；终答 689/278 字与批准腿末帧同一枚 sha（`9a52943ae2d8`/`cf1c4c36b875`）
  ——屏上最后一格站的就是评分器看到的那份字。
- 批准腿也没漏：stream 1 同样是 `step → text → step`（R464 的 `_ApprovedAnswerStream` 武装出口，
  `:3549-3568`），且 `answer.startswith(pre_answer)` 为真——跨闸是**前缀延长**，不是屏上第二份答案。
- 产品侧真正发生的是 R149／R203／R210 在册那一族「片与终答不同源」（`:2905-2922` 大声记 error 日志，
  附 `leg`/`call`/`dropped` 三格归因）。那一族的**屏后果**已被 R210 治掉；把它的**发生**再算成 A② 的新罪，
  等于推翻 R215 已经裁过的「受控纠正不是断流」。本单不许它算新产品罪，也不许它洗成没事：见 §4 末段。

### 3.2 为什么不是环境抖动（逐条排除，不拿「只出现一次」当证据）

1. 两窗修订、评测主件、传输件、容器**逐字相同**（§0 那四枚指纹），两窗各 105/105、`attempt` 全为 1、
   `sentinel` 全为 false、`kind` 分布完全相同（86 枚 `ok` + 19 枚 `approved_ok`）、零帧题 0 枚。
   ⇒ 全程没有一次 HTTP 重试、没有一次断线、没有 `error_event`／`blank`／`approval_failed`。后端重启或
   连接被切会当场断流，落盘形状是重试或哨兵，而不是「两条流都跑到 `done` 且末帧＝终答」。
2. 这两枚的两条流都到终局：stream 0 尾部 `hitl → request.completed → sources → done`，
   stream 1（批准腿）`request.started → step → text → step → request.completed → sources → done`。链路完整。
3. 内容侧否掉「丢字节」：run19 的断裂帧是**完整**的 636/225 字且逐字等于该轮交付文本；tool-02 那份
   225 字与 run18 那枚 225 字**同一个 sha**。网络丢字不可能留下两份逐字完整且相同的文本。
4. 「腿停顿 → 收尾换源」这一形在两窗**同量级**，不是 run19 独有的慢：run19 两枚的上一片帧→断裂帧间隔
   21.35 s／9.93 s，两窗都被量具正常豁免的四枚是 12.91–41.04 s。run19 独特点的只有「停顿恰好落在挂起轮」。
5. 四枚稳定复现的断裂（metric-03／metric-11／report-06／scope-04）在两窗**同题号、同形状、同豁免结果**，
   量具对单流轮的行为是确定的；红与不红的分界落在 `streams` 那一格上，与随机无关。

### 3.3 反证自查（本单立论之前先被在册牙咬过一遍）

- `tests/test_r215_recognizing_a_controlled_correction.py:178-190` 的 ① 只在**中途**坏形上不豁免；
  今天这两枚的 `at` 恰等于所在流帧数 ⇒ ① 不构成拦阻，拦阻只可能来自 ④。
- `:224-243` 的 ③ 四枚反例都要求打掉「紧邻」，而账上这两枚紧邻着 `step`；③ 不是分界点。
- `:245-260` 的 ④ 反例（终答被 `APPROVAL_FAILED_SENTINEL` 替换、屏上那份没成交付）与今天**方向相反**：
  今天是「挂起轮那份字确实交付过（`pre_answer` 为凭），只是交付之后又被批准腿的更长终答取代」。
  🔴 这枚反例的存在正是 §4 甲案必须带 (c) 前缀条、且不许松的原因。

## 4. 下一步该动哪个文件的哪一腿（只写位置与判据，本单不动手）

主修位置：**`scripts/eval_transport_ask_v2.py::_corrective_readings` 的第④条（`:676`）——比对对象从轮级换成流级**。
它现在比的是「本轮交回评分器的那份字」（`_record_frames:844` 传进来的 `answer`），而要治的坏形住在
**某一条流**里。两套候选，供总控裁定：

- **甲案（改量具）**：④ 改为「断裂帧逐字等于本轮终答，**或**同时满足 (a) 断裂所在流不是最后一条流、
  (b) 断裂帧逐字等于**它所在那一条流的交付文本**、(c) 本轮终答以它为前缀」。
  (c) 就是今天账上的形状（19/19 成立），也是「不许把屏上第二份字洗白」那道闸——`_ApprovedAnswerStream`
  规则 1（`app/api/v1/chat.py:1827-1831`）靠逐字相等不发第二枚流，加了 (c) 才不会反向放行同文重发
  （那一形由 R471 的派生格 `cross_stream_repeats` 管，`scripts/eval_transport_ask_v2.py:683-732`，两格不许互抄）。
  落地代价：`_fold_frames` 折 `per_stream` 那一处（`:634-635`）要多带**每条流交付文本的指纹**；
  🔴 只能带 sha，不许带正文（`docs/testing/r181-text-frame-readings.md:41` 那条「不把客户正文抄进
  第二份文件」的纪律）。这一动会碰 `per_stream` 元素键集与帧账行键集两道闸
  （`tests/test_r181_text_frame_ruler.py:50` 的 `FRAME_READING_KEYS`、`:449` 的键集**对判**），
  而 `scripts/eval_transport_ask_v2.py:614-616` 明文写着那一格的键集被逐字钉着——**纸与键集钉归总控改**，
  执行层不许自开（R518 名下已记「帧账加格即红」）。
- **乙案（零新列，只读判据侧）**：`scripts/eval_frame_caliber_readout.py::caliber_block` 把 `streams > 1`
  那一族单列一档，逐枚点名「断裂住在第几条流、该流几帧」，并明写「挂起轮内的断裂在 R215 口径下
  结构性不可豁免 ⇒ A② 对这一族记 `not_applicable`／另立可见格」。这与总控 09-28 的裁定同族
  （`b9fd2fc`：②只适用于确有逐片腿的轮，够不到的格记 `not_applicable` 且另立可见格，两读并列不许只印一格）。
  🔴 乙案不改 `criterion_two_holds` 的落盘值，只改读数怎么摊开——今天这两枚仍如实显示 `uncorrected_breaks=1`。
- 推荐：**先落乙案**（今天就能落地、不动键集、不重判当年读数），**甲案**留给带键集钉改动的正式口径单。

配套（无论甲乙）：

- 纸面：`docs/testing/r181-text-frame-readings.md:56-60` 四条件原文与 `:96-97` 那句「挂起后批准 18 枚
  坏形仍读 0」都要补「挂起轮内换源」的处置；`scripts/collect_evaluation_answers.py:32-41` 的 R215 抬头随之同步。
- 牙（新用例的形状，两枚）：`tests/test_r215_recognizing_a_controlled_correction.py` 里加
  ① park 轮换源用例——stream 0 ＝ `_text(短片) → _arm() → _text(挂起轮终答 225 字)`，
  stream 1 ＝ `_text(更长终答 278 字)`，`answer=278` 那份：走甲案断言 `uncorrected_breaks == 0`
  （按今天口径跑必得 1，即这枚牙落地当场红，正是它该红）；
  ② 守门用例——同一批帧但 `answer.startswith(break frame)` **不成立**，断言仍 `== 1`（防甲案 (c) 被放宽）。
  反向不许松：`:245-260` 那枚哨兵反例必须继续红，改完现跑这一枚件确认没被洗白。
- 若要咬底层那一族（片与终答不同源，不是 A② 的格）：最小可复现判据**离线**即可——用
  `scripts/r239_stream_gap_offline_audit.py` 那类件复算帧账，统计「`streams>1` 且 stream 0 末帧为断裂帧」
  枚数（run18＝0/19，run19＝2/19）；成因那三格（`leg`/`call`/`dropped`）要等下一扇窗把 backend 容器日志
  一起收窗（§5 第 2 条）。不跑全量门也能判。

## 5. 诚实清单（今天取不到的格，以及为什么）

1. **③ 的 payload 一手读数取不到**：帧账 `events` 只落事件名与类别（`_note_event_arrival:497-503`），不落
   `data`，`tool`/`status` 在盘上不可证。本单用码路＋账形＋内容三条推定，没有一手凭据。
2. **`[R149]` 后端日志不在盘上**：run18／run19 只收了 driver 与 worker 日志，没收 backend 容器日志
   （盘上只有 `run17-backend.log`），这两枚换源的 `leg`/`call`/`dropped` 三格**今天没量过**；
   「实时腿为什么停在 60/136 字」只能停在推测——两条候选成因都够得着这一形：`frame_for` 在 `call_id`
   变化或 `base` 变化时重开（`app/api/v1/chat.py:1777-1806`），`_select_final_answer` 优先取
   `worker_answers` 而非流式腿那份（`:1919-1949`）。铁规禁动容器，本单没去补捞日志。
3. **断裂帧正文只有 sha12**：帧账不落正文（纪律如此）。④ 与 `pre_answer` 的相等是按 `sha256[:12]` 对齐＋
   字数相同双重判的；`pre_answer` 那一侧本单拿到全文并现算了 sha，所以「挂起轮那份字＝断裂帧」是可复核的，
   但「非挂起轮那四枚的断裂帧＝终答」同样只有 sha 一级证据。
4. **枚数不可外推**：2/19 与 0/19 是**两扇窗**，量不出这一族的频率，也量不出它与负载/模型的相关；
   今天能证的只有「挂起轮内换源 ⇒ 必然判红」这条结构性。
5. **答案内容两窗本身在漂**：report-09 终答 2417 字→689 字，report-06 换了季度（Q1→Q2），metric-03 用词微调；
   窗级 `answer_correctness` 0.6571→0.6476、`evidence_coverage` 0.7905→0.7810（`run1{8,9}-report.json`）。
   这属本机 Ollama 生成方差，本单没有据把它判成退化，也没有格去判它——但它限制了「同修订两窗必同读数」
   这条隐含预期，判据② 的复现率要连着多窗才谈得上。
6. **本单没跑任何测试**：主树在跑全量门，铁规禁跑；§4 里所有「牙」都只是位置与判据，没有一枚是今天实跑过的红色。
7. **侧车只有 `pre_answer` 一枚流级交付格**：它只在 `pre_kind=hitl` 时写（`scripts/eval_transport_ask_v2.py:1379`），
   非挂起轮没有这一格——这也是甲案必须落 sha 新列、不能拿现成格复算的原因。

## 6. 一句话交回总控

A② 第一次拿到读数，读出的是**量具在挂起轮那一族失明**，不是产品把收尾做坏了：`report-09`／`tool-02`
的断裂帧逐字等于挂起轮交付的 `pre_answer`，R210 的 `step→整段替换→step` 确实发到了屏上，而 R215 第④条
拿轮级终答去比一条流内的末帧，两窗 19/19 挂起轮都是「终答严格长于挂起轮那份字」，豁免结构性拿不到。
建议先落乙案（读侧分档、零新列、与 `b9fd2fc` 那条裁定同口径），甲案留给带键集钉改动的正式口径单；
底层那一族（片与终答不同源）另案，收窗时把 backend 日志一起收。
***
- 交回件：`docs/perf/r614-uncorrected-break-attribution-2026-10-03.md`（本树唯一新增文件，未 commit、未 push）
- 施工席：R614（执行层），基点 `4896e97`，分支 `codex/be-r614`
