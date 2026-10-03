# R595 —— A① 时延的机器读数：三组数 + 停表帽命中单列（10-03 第十三班·执行层 `Huygens`@`be-r595`，基点 `a5ba2d7`）

量具：`scripts/r595_latency_readout.py`（只读、离线、零模型、零容器、零网络）。
钉子：`tests/test_r595_group_derivation.py`／`tests/test_r595_stall_cap.py`／`tests/test_r595_honest_span.py`（24 枚）。

> 🔴 **本格不判 A① 绿不绿，只把数摆出来**；判绿权在总控。带噪窗（同机多枚执行层在跑）的时延读数按
> **「通过可信／不合格不作结论」**处理——本纸下面每一格都写了它是不是带噪窗。

---

## 一、要治的病（在册原文，本席 11:5x 现取）

`docs/handoff/2026-09-17-perf-architecture-plan.md:383-384`（作者署「R440 口径裁定·总控代业主裁定·可推翻」）钉着两格：

1. `:383` A① 的 V1 时延门槛**只认问答类那一格**（≤90 s／p95／**n 必带**），分析·报告类阈值随阶段 B 另立、V1 内不判；
   整表 p95 只作**每轮必须公布的读数**，不作门槛——「这是 09-20 那格口径的延续，不是新口径」。
2. `:384` 🔴 命中停表帽（`EVAL_QUEUE_STALL_SECONDS`，默认 300 s）的题**必须单列一格报数**，
   既不许从 p95 里悄悄摘掉、也不许混进「正常慢答」当成模型的问题；每轮跑分抬头必须写「停表帽命中 N 枚」。
   凭据：run9 的 `chat-11` `wall_ms=300108.2` 恰等帽值。

而这台机上没有任何一件脚本产出这两格（本席 10-03 11:5x 现取；13:01:14 在同一棵 `be-r595` 树上复取，逐字读数见下）：

```
$ rg -ln 'EVAL_QUEUE_STALL_SECONDS' scripts app tests
scripts\eval_transport_ask_v2.py
tests\test_r222_queue_terminal_stopwatch.py
$ rg -n 'p95' scripts/run_quality_evaluation.py
25:        f"p95_ms={report['latency_ms']['p95']} {format_correctness_rulers(report)}"
$ rg -c 'wall_ms|p95' scripts/r580_per_class_attribution.py
（零命中）
```

🔴 两条订正（13:0x 复取时量到的，不敢沿用 paraphrase）：
① 上面那行原样抄进纸面时把 `run_quality_evaluation.py:24`（`evidence=`）与 `:25`（`p95_ms=`）并成了一行——`rg -n p95` 实际**只命中 :25**，
   此处已换成逐字读数。结论不变：那句只打**整表**一枚 `p95_ms`，既无分群、也无 `n`、更无停表帽那一格。
② 第一枚命令 11:5x 只命中两枚件，**13:01 复取时已四枚**（多出 `scripts\r595_latency_readout.py`＋`tests\test_r595_stall_cap.py`＝本单自己）
   ⇒ 这一格变化本身就是本单的交付：那两格从今天起有件产出了。

⇒ 每班纸上那句「问答类 n=64 avg 30.1／p50 25.8／p95 61.0 s」全是现场手推；本班已为手推的数自纠过两次（跟进单 §157、§159 的 R592）。
本单把那两格变成**同一 HEAD 复跑逐字节相同**的机器读数。

---

## 二、分群派生规则（判据②：不靠猜，从夹具自己的字段现读）

### 2.1 规则本体

唯一事实源 = 计划书 `:352` 那格 **09-20 21:3x 总控代业主裁定**原文（R440 在 `:383` 明写它是延续、不是新口径）：

| 群 | 成员键 = 夹具 `category` 字段 | 本件常量 |
|---|---|---|
| 问答类（A① 唯一门槛格） | `文档问答 + 多轮对话 + 口径冲突 + 无证据问题 + 工具调用 + 跨部门权限` | `QA_CATEGORIES` |
| 分析·报告类（阈值随阶段 B，V1 不判） | `Excel计算 + 报告生成 + 图表生成 + 主动洞察` | `ANALYSIS_REPORT_CATEGORIES` |
| 不入任一群（`:352` 白纸黑字排除） | `审批判断` | `UNGROUPED_CATEGORIES` |
| 整表（只公布不判） | 夹具全部题号 | `GROUP_ALL` |

🔴 **分群键是 `category`，不是 `tier`**。夹具里长出上表三份名单之外的任何 `category` ⇒ 件 rc=`RC_CALIBER`(3) 并逐名点名，
不自创一群、不静默并入（钉子 `test_unknown_category_is_named_and_refuses_to_invent`）。

### 2.2 那笔「6 枚去哪了」的账（本席被要求说清，现答：**说得清，不必停下上报**）

拿在册题集 `tests/fixtures/business_evaluation_100.jsonl`（sha256 前 12 = `686c564ff298`，105 枚，一字节未动）现算：

| 分法 | 各群 n | 加总 | 板上原句 |
|---|---|---|---|
| **`category` 维**（`:352` 裁定本体） | 问答 64 ／分析·报告 35 ／未入群（审批判断）6 | **105** ✅ | 看板 `:3480`「问答类 n=64／分析·报告 n=35」逐字复现 |
| **`tier` 维**（夹具另一列） | 问答 50 ／分析 35 ／报告 20 | **105** ✅ | 跟进单 `:4176`（R440 立单原文）「问答档 n=50 p95 125.2 s」 |

- **「6 枚」的去向 = `审批判断` 那一族**（题号 `approval-01…06`），`:352` 原文就写着「`审批判断` n=6 **不入任一群**」⇒ 它不是漏计，是裁定排除。
- 看板 `:3993` 那句「问答 n=64／分析 n=35／报告 n=20」**加总 119 ≠ 105**：它把 `category` 维的 64 与 `tier` 维的 35＋20＝55 **并排印在同一句话里**。
  两维各自都能加总到 105，拼起来就差 14 枚。机器现算这笔账（105 枚一字节未动）：
  |问答类 64| ＋ |`tier` 分析∪报告 55| ＝ 119，而两维并集只有 **98** 枚 ⇒ 105 − 98 ＝ **7 枚谁都没数**
  （`approval-01…06`＝`category` 落在三份名单之外的 `审批判断`、`tier` 问答；`chart-03`＝`category` `图表生成` 在分析·报告名单里、`tier` 却是问答 ⇒ 两维都不数它），
  119 − 98 ＝ **21 枚被两维各数一遍**（`口径冲突` 17 枚＋`工具调用` 4 枚：`category` 在问答类名单里、`tier` 交回分析 13／报告 8）。
  14 ＝ 21 − 7，账是闭合的（钉子 `test_the_two_dimensions_are_not_the_same_partition`）。
  跟进单 `:4176` 已经把这判成「**不同母集**，谁都不许抄谁，计划书 A 行落笔必须带母集数」——本件因此**同时交两维**：
  `category` 维是三组数本体，`tier` 维另立一节并明写「非门槛口径」，这一格从此不再靠人嘴解释（钉子 `test_bank_reproduces_the_two_published_partitions`）。
- 落笔规矩（本件写进纸面的结论）：**A① 那一格必须写「问答类（category 维）n=64」**；写「n=64／分析 35／报告 20」这种混维句子一律视为不可采信。



---

## 三、诚实跨度口径（判据③：只认 sidecar 的 `wall_ms`）

在册口径 = 跟进单 §21 R205a／看板 §4BV：**越出一发量级上限的跨度记 null、原始观测留在 `latency_suspect`，诚实跨度只认帧账 sidecar 的 `wall_ms`**。
本件因此：

- 聚合（avg／p50／p95／max／min）**只由 `wall_ms` 构成**；`answers.latency_ms` 一枚都不参与（纸面固定印「本件一枚都没拿来聚合」那一行）。
- 拿不出 `wall_ms`（sidecar 没这一题／读不成非负毫秒／`wall_ms` 自己越过一发量级上限）⇒ 该题**不计入聚合并逐枚点名**，不拿 `latency_ms` 顶替、不补零。
- 一发量级上限现读 `app/quality/eval.py::latency_envelope_ms()` = `MODEL_REQUEST_TIMEOUT` × 8 = **960000 ms**（缺省环境下的读数），本件不另存这个数。
- `latency_ms` 与 `wall_ms` 的差**用在册那两枚常数判**（`LATENCY_LEDGER_RATIO_TOLERANCE` 1.25 ＋ `LATENCY_LEDGER_SLACK_MS` 2000 ms），
  并顺手把结论交给在册判器 `classify_latency_span()`，本件不复写一套规则。

各窗点名读数（本件现算）：

| 窗 | `answers` 带可用 `latency_ms` | 与 `wall_ms` 差出容忍带 | 拿不出诚实跨度 |
|---|---|---|---|
| run13 | 105 | **0 枚** | 0 枚 |
| run14 | 105 | **0 枚** | 0 枚 |
| run16 | 12 | **0 枚** | 0 枚 |
| run7（在树原件） | 105 | **0 枚** | 0 枚 |
| run9（在树原件） | 105 | **0 枚** | 0 枚 |
| run6（在树原件＝R205a 的病号窗） | 105 | 🔴 **3 枚**：`data-04` 38.2946×／`data-06` 523.2521×／`data-07` 6.4568×，action 全 `repaired_to_frame_ledger` | 0 枚 |

⇒ run6 那三枚倍差与跟进单 §93.9 手算的「38×／523×／6.5×」**逐位复现**，从今起这一格也不用再靠人算。

🔴 **一笔要报的口径差（不是本件算错）**：`run13-report.json` 与 `run14-report.json` 的 `latency_ms.frame_ledger_rows = 0`（现读两枚数），
说明板上 §4EJ 那两句「avg 60.1→63.4 s／p95 151.8→164.7 s」是**拿 `latency_ms` 算的、帧账根本没 join 上**。
本件按 R205a 只用 `wall_ms` ⇒ 同一秩元素上差 2~3 ms（下表逐格点名）。差在本席与在册那把尺的**输入列**，不在算术。

---

## 四、停表帽那一格（判据①后半格）

### 4.1 帽值现读（不写死）

件用 `ast` 解析 `scripts/eval_transport_ask_v2.py` 里那一枚赋值，取它自己的 env 名与字面默认，再按当前环境算生效值；纸面固定印出源码行＋行号：

```
eval_transport_ask_v2.py:201 → QUEUE_STALL_SECONDS = float(os.getenv("EVAL_QUEUE_STALL_SECONDS", "300"))
```

缺省环境下 ⇒ 帽值 **300000.0 ms（300.0 s）**，带宽 = 一枚轮询间隔（`QUEUE_POLL_INTERVAL`，`:204`，缺省 3.0 s ⇒ 3000 ms）。
钉子 `test_cap_value_is_read_live_from_the_transport_source` 拿一份合成量具件（42 s／7 s）跑同一函数，读数跟着变成 42000／7000 ⇒ **写死 300 的件当场红**。

### 4.2 命中判据（两条路径，一条都不省）

| 路径 | 判据 | 为什么必须有 |
|---|---|---|
| 甲 | `sidecar.kind == "queued_stalled"` | 量具自己宣告停表（`eval_transport_ask_v2.py:1200`）——但**只认这一条会漏掉在册凭据**：`docs/testing/sidecar-run9.jsonl` 里 `chat-11` 的 `kind` 是 `ok` |
| 乙 | `wall_ms ∈ [帽值, 帽值 + 一枚轮询间隔]` | `:199-200` 原话「代价是至多一枚轮询间隔（3 s）」⇒ 带沿 303000 ms；`chat-11` 的 300108.2 落进带内 |

超帽带（`wall_ms > 303000 ms` 而 `kind ≠ queued_stalled`）**另立一格点名且照旧进 p95**——它不是停表帽那一枚，摘它就是假话；
它落在 p95 里也不等于「模型慢」，所以纸面把 kind 一并印出来请总控判。
本件因此同时满足 `:384` 那两句禁令：**没悄悄摘**（含帽的 p95 每群都另印一行，命中逐枚点名），**也没混进正常慢答**（单列那一格＋判据口径 p95 剔掉已确认命中）。

### 4.3 各窗命中读数

| 窗 | 停表帽命中（抬头那句） | 命中题号 ＋ `wall_ms` | 超帽带（不摘） |
|---|---|---|---|
| run13 | **0 枚** | — | 🔴 1 枚：`insight-07` 309301.6 ms，kind=`approval_failed`（`主动洞察`／分析·报告类） |
| run14 | **0 枚** | — | 0 枚（最大 `insight-07` 282052.7 ms） |
| run16 | **0 枚** | — | 0 枚（最大 `report-04` 292102.0 ms，距帽值差 7.9 s ⇒ 不在带上） |
| run9（在册凭据窗） | 🔴 **1 枚** | `chat-11` `wall_ms=300108.2 ms`，kind=`ok`，category=`多轮对话` ⇒ 入群＝问答类 | 0 枚 |

⇒ **R440 那句凭据（跟进单 `:4176`）由机器复现**：本件自己抓到 `chat-11`，不需要人告诉它。钉子 `test_run9_book_credential_is_reproduced` 钉这一格。

---

## 五、三组数与复算对账（判据①＋判据④）

单位：ms（括号内是 s，与板上历史写法可直读比）。三组数 = **问答类／分析·报告类／整表**，每格都带 `n`（母集／有诚实跨度／进 p95 三枚）。
「判据口径」那枚 p95 是**最近秩**（`app/quality/eval.py:628` 同一把），线性插值一并交回但**不是判据口径**。

### 5.1 run13（Chroma 读腿，`started_at=2026-10-02 22:36:22`，rev `fd90f30`，`index_backend=""`，夹具 sha `686c564ff298`）

| 群 | n | avg | p50(最近秩) | **p95(最近秩·判据口径)** | p95(线性·对照) | max | min |
|---|---|---|---|---|---|---|---|
| 问答类 | 64／64／64 | 47729.0 (47.7) | 38840.3 (38.8) | **118337.5 (118.3)** | 116574.8 (116.6) | 244715.3 (244.7) | 9683.4 (9.7) |
| 分析·报告类 | 35／35／35 | 84569.0 (84.6) | 66295.2 (66.3) | **213662.4 (213.7)** | 205000.0 (205.0) | 309301.6 (309.3) | 22586.3 (22.6) |
| 整表 | 105／105／105 | 60095.8 (60.1) | 43052.6 (43.1) | **151747.0 (151.7)** | 150782.8 (150.8) | 309301.6 (309.3) | 9483.7 (9.5) |

对账：整表 avg **60.1 s ＝ 板上 §4EJ `:6478`「avg 60.1」逐位相同**；p95 **151.7 s vs 板上 151.8 s**（报告格 `p95=151750.15`，本件 151747.0）
⇒ 差 **3.15 ms**，同一秩元素，差因＝§三 那句「报告那格的 `frame_ledger_rows=0`，用的是 `latency_ms`；本件用 `wall_ms`」。**当年没算错，是输入列不同。**
问答类／分析·报告类这两格 **板上从未公布过 run13 的分群数**（`:6478` 只印整表）⇒ 本纸是这两格的第一次机器读数。

### 5.2 run14（pgvector 读腿，`started_at=2026-10-03 00:27:29`，rev `fd90f30`，`index_backend=pgvector`，夹具 sha `686c564ff298`）

| 群 | n | avg | p50 | **p95(判据口径)** | p95(线性) | max | min |
|---|---|---|---|---|---|---|---|
| 问答类 | 64／64／64 | 51291.2 (51.3) | 40261.6 (40.3) | **128268.3 (128.3)** | 126849.5 (126.8) | 195701.0 (195.7) | 9844.2 (9.8) |
| 分析·报告类 | 35／35／35 | 88979.5 (89.0) | 78269.9 (78.3) | **188934.3 (188.9)** | 171939.6 (171.9) | 282052.7 (282.1) | 28457.1 (28.5) |
| 整表 | 105／105／105 | 63379.7 (63.4) | 47846.4 (47.8) | **164656.1 (164.7)** | 161783.2 (161.8) | 282052.7 (282.1) | 9627.8 (9.6) |

对账：整表 avg **63.4 ＝ 板上 63.4** ✓；p95 **164.7 ＝ 板上 164.7**（报告格 164660.591 vs 本件 164656.1，差 4.5 ms，同一秩元素，差因同上）✓。
分群两格同样是第一次有机器读数。



### 5.3 run16（D 格复测专窗，12 枚报告档子集，`started_at=2026-10-03 10:48:09`，rev `9c9a0b1`，`index_backend=pgvector`）

件在盘上的是**分片**（`run16.shards\run16-s0NN-fixture.jsonl` 十二枚），本席拼成一份 12 行件放在**自己的** `%TEMP%\r595snap\run16-fixture-12.jsonl`（`%TEMP%\evalrun` 一字节未动）；
拼出来的件 sha256 前 12 = **`a9af15ea81c2`**，与 `run16.window.json` 里记的 `fixture_sha256` **逐位相同** ⇒ 拼接件与当年那枚夹具是同一份字节（这条本身就是复算的可信度凭据）。

| 群 | n | avg | p50 | **p95(判据口径)** | p95(线性) | max | min |
|---|---|---|---|---|---|---|---|
| 问答类 | 0／0／0 | 🔴 无量可算（这一窗根本没跑问答类） | — | — | — | — | — |
| 分析·报告类 | 12／12／12 | 106855.7 (106.9) | 81583.9 (81.6) | **292102.0 (292.1)** | 206336.2 (206.3) | 292102.0 (292.1) | 39972.4 (40.0) |
| 整表 | 12／12／12 | 106855.7 (106.9) | 81583.9 (81.6) | **292102.0 (292.1)** | 206336.2 (206.3) | 292102.0 (292.1) | 39972.4 (40.0) |

对账：**板上 §4EK `:6576` 那一串是 `wait_ms`（队列轮询等待），不是整题 `wall_ms`**——两枚量不同名，不许互抄（`wait_ms` p50 62.6 s／p95 127.6 s vs 本件 `wall_ms` p50 81.6 s／p95 292.1 s）。
板上 §4EK `:6575` 说 `report-04`「首片 rc=−1（10.7 s，零产出），第 2 轮补片 292.6 s 成功」；
本件读 `run16-sidecar.jsonl`：`report-04` **只有一行**（`attempt=1`，`kind=queued_approved`，`wall_ms=292102.0 ms = 292.1 s`）⇒ 折叠规则在这里没有可折的第二行，
driver 层那句 292.6 s 与本件 292.1 s 差 **0.5 s**（driver 报的是那一枚分片进程的时间，含起进程与收尾；sidecar 报的是 transport 那一发自己的跨度）。这一格点名，不改数。
🔴 `292102.0 ms` 距帽值 300000 ms 差 7.9 s ⇒ **不是停表帽命中**，也没落超帽带（带沿 303000 ms 之上才谈超带）。

🔴 **空群那一格怎么说**（首班交回单已把它列为**唯一未完项**，但它的 patcher 卡在自己多写的一条断言上，到 12:3x 一个字都没落；本席 12:4x 落码）：这一窗问答类 `n=0`，纸面印「无量可算」；
而在册那把尺 `build_latency_cell([])` 对空集交回的是 `p95=0`，本件交回 `None` ⇒ 「尺一致性自证」那一格**不许**对本群印 `agree=True`
（那等于拿一枚 `0` 冒充「两把尺在同一枚测到的跨度上同数」）。改前本件正是这么印的：`"agree": ... or (not used and inbook["p95"] == 0)`。
现在：空群 ⇒ `empty=True`／`agree=False`，纸面改印「这一格空群 ⇒ 两把尺都说不出数…**不拿「相等」冒充「同数」**」，
钉子 `test_an_empty_group_never_claims_the_two_rulers_agree` 钉这一格。

### 5.4 run9＝R440 凭据窗（在树原件 `docs/testing/answers-run9.jsonl`＋`sidecar-run9.jsonl`，sha `e879075f4083`／`cb972fd93fa9`）

| 群 | n（母集／跨度／进 p95） | avg | p50 | **p95(判据口径·剔帽)** | p95(线性) | 含帽 p95(最近秩) | max | min |
|---|---|---|---|---|---|---|---|---|
| 问答类 | 64／64／**63**（剔 1 枚命中） | 43909.6 (43.9) | 39271.9 (39.3) | **106477.3 (106.5)** | 106135.4 (106.1) | 119577.9 (119.6) | 125225.2 (125.2) | 7927.9 (7.9) |
| 分析·报告类 | 35／35／35（本群零命中） | 94157.1 (94.2) | 77853.7 (77.9) | **224651.3 (224.7)** | 192076.2 (192.1) | 224651.3 (224.7) | 291578.9 (291.6) | 27040.9 (27.0) |
| 整表 | 105／105／**104**（剔 1 枚命中） | 61741.6 (61.7) | 45432.8 (45.4) | **140878.8 (140.9)** | 140557.2 (140.6) | 154509.1 (154.5) | 291578.9 (291.6) | 7927.9 (7.9) |

对账（这一窗是判据①后半格的**凭据**，所以逐格摆）：

| 已公布值（出处） | 本件复算 | 差 |
|---|---|---|
| 「整表 n=105 p95 **154.5 s**」（跟进单 `:4176`，R440 立单原文） | 154509.1 ms（含帽那一格，最近秩） | **逐位相同** ✅ |
| 「问答档 n=50 p95 **125.2 s**」（跟进单 `:4176`＋`docs/testing/run9-readout-2026-09-28.md:23`） | tier=问答 含帽 125225.2 ms | **逐位相同** ✅ |
| `run9-readout:23` tier=问答 `n=50 p50=31746.1 p95=125225.2 max=300108.2 min=7927.9` | 本件 tier=问答：p50 31746.1 ／含帽 p95 125225.2 ／min 7927.9；max 剔帽 127991.4 | p50／p95／min 逐位；max 差的那一枚**就是 `chat-11` 300108.2** ⇒ :384 禁的正是「混进正常慢答」 |
| `run9-readout:24` tier=分析 `p50=65434.5 p95=224651.3 max=291578.9 min=27040.9` | 本件同格：65434.5／224651.3／291578.9／27040.9 | **四枚逐位相同** ✅ |
| `run9-readout:25` tier=报告 `p50=51948.5 p95=140878.8 max=174562.7 min=12008.9` | 本件同格：51948.5／140878.8／174562.7／12008.9 | **四枚逐位相同** ✅ |
| 「`chat-11` `wall_ms=300108.2` 恰等帽值 ⇒ 停表帽命中」（:384 凭据） | 本件抬头「停表帽命中 1 枚」＋逐枚点名 `chat-11 300108.2 ms`，路径＝帽带（`kind=ok`） | **命中判据复现** ✅ |

### 5.5 run6／run7（更早两窗，原件在树）——含**对不上的一格，照实登记**

| 群 | run6 复算（判据口径 p95／线性／max／p50） | run6 已公布（看板 `:3993`） | 判定 |
|---|---|---|---|
| 问答类 n=64 | 73153.3／72862.2／81947.5／27372.3 | 「median 27.9 s／p95 **68.9 s**／max **80.9 s**」 | 🔴 **对不上**（p95 差 +4.0~4.3 s，max 差 +1.0 s，median 差 −0.5 s）。本席试过八种组合都复现不出 68.9：{`category` 问答类 64｜`tier` 问答 50} × {`wall_ms`｜`latency_ms`} × {最近秩｜线性}，再试「剔批准腿 `approved_ok`（n=59，max 正好 80897.0＝80.9 s，但 p95 线性 71.4／最近秩 73.2）」「只留 `kind=ok`（n=58，线性 58.0／最近秩 71.2）」「剔 `error_event`（n=63，线性 69.7／最近秩 71.2）」——**没有一种给出 68.9**。⇒ 登记**待查**：当年那一格用的是第三套母集还是第三把尺，本席说不清就不硬编原因，**不改自己的分群去凑 published 数**。 |
| 分析·报告类 n=35 | 270887.3／**212064.3**／272208.8／59824.8 | 「分析档 n=35 p95 **212.1 s**」 | ✅ **线性插值那一把逐位复现**（212064.3 ms = 212.1 s） |
| 整表 n=105 | 145746.0／**143790.0**／272208.8／34763.6 | 「整表 p95 **143.8 s**」 | ✅ 同上（143790.0 ms = 143.8 s） |
| tier=报告 n=20（对照维） | 145746.0／**146621.7**／163260.2／45942.0 | 「报告档 n=20 p95 **146.6 s**」 | ✅ 同上（146621.7 ms = 146.6 s） |

| 群 | run7 复算 | run7 已公布（看板 `:5398`） | 判定 |
|---|---|---|---|
| 问答类 n=64 | 判据口径 68767.0／线性 **68023.5** | 「问答档 p95 **68.0 s** ≤ 90 s ⇒ A① 成立」 | ✅ **线性那一把逐位复现**（68023.5 ms = 68.0 s；最近秩给 68.8 s） |
| 整表 n=105 | 127403.6／**127148.2** | 「整表 **127.1 s** 只公布、不判绿也不判红」 | ✅ 同上 |

🔴 **本席由此量到一枚纸面没钉过的口径差，请总控裁（本件不改判据、不自作主张翻案）**：
`:352`／`:383` 只写「p95」，**没写排名规则**。而盘上历史读数里两把尺都在用——run6／run7 那几格是**线性插值**算的，
`app/quality/eval.py:628` 的报告格与 `docs/testing/run9-readout-2026-09-28.md:21` 是**最近秩**算的。
两把尺在这一批窗上差 0.2~0.9 s 量级（run7 问答类 68.0 vs 68.8；run13 整表 150.8 vs 151.7），**不足以翻 90 s 那条线的绿红**，
但「同一句 p95 不同尺」这件事从今天起有机器数可查：本件**两把都印**，并把判据口径钉成在册报告那把（最近秩），逐群自证两把尺同数（🔴 只有**非空**那几格才算 `agree=True`；空群那一格不拿在册那把尺对空集交回的 `0` 冒充「同数」，见 §5.3）。



---

## 六、复跑命令（全部只读；本席 10-03 12:0x–12:2x 逐条真跑、12:4x–12:5x 改码后又逐窗复跑一遍等值的原文）

工作目录 = `C:\Users\fengx\PycharmProjects\be-r595`；`$py = C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`。

```powershell
# 6.1 两扇主窗（run13／run14；%TEMP%\evalrun 只读，一个字节都没写回去。sidecar 不写 ⇒ 由件名同规律推出 run1N-sidecar.jsonl)
& $py -X utf8 scripts\r595_latency_readout.py --answers "$env:TEMP\evalrun\run13-answers.jsonl" `
      --fixture tests\fixtures\business_evaluation_100.jsonl --label run13
& $py -X utf8 scripts\r595_latency_readout.py --answers "$env:TEMP\evalrun\run14-answers.jsonl" `
      --fixture tests\fixtures\business_evaluation_100.jsonl --label run14

# 6.2 run16 只有分片，先拼一份 12 行的夹具副本放到自己的目录（拼出来 sha12=a9af15ea81c2，与 run16.window.json 逐位相同）
$fx = Get-ChildItem -LiteralPath "$env:TEMP\evalrun\run16.shards" -File |
      Where-Object Name -like '*-fixture.jsonl' | Sort-Object Name |
      ForEach-Object { Get-Content -LiteralPath $_.FullName }
[IO.File]::WriteAllText("$env:TEMP\r595snap\run16-fixture-12.jsonl", (($fx -join "`r`n") + "`r`n"),
                        (New-Object System.Text.UTF8Encoding $false))
& $py -X utf8 scripts\r595_latency_readout.py --answers "$env:TEMP\evalrun\run16-answers.jsonl" `
      --fixture "$env:TEMP\r595snap\run16-fixture-12.jsonl" --label run16

# 6.3 四扇在树原件（run6/run7/run9 用来对 R205a 与 R440 两枚凭据）
foreach ($w in 'run6','run7','run9') {
  & $py -X utf8 scripts\r595_latency_readout.py --answers "docs\testing\answers-$w.jsonl" `
        --fixture tests\fixtures\business_evaluation_100.jsonl --sidecar "docs\testing\sidecar-$w.jsonl" --label $w
}

# 6.4 机器可读的整份读数（复算对账表就是从这倒出来的）
& $py -X utf8 scripts\r595_latency_readout.py --answers "$env:TEMP\evalrun\run13-answers.jsonl" `
      --fixture tests\fixtures\business_evaluation_100.jsonl --label run13 --json `
      > "$env:TEMP\r595snap2\run13.json"
#   ⇒ run14／run6／run7／run9 同一形状（只换 answers／label；sidecar 由件名同规律推），run16 另换 --fixture
#   六窗的 --json 全部重倒进 %TEMP%\r595snap2\，与 12:2x 的旧副本逐字段比过（见 §6.6）

# 6.5 同名件（禁止跑全量门；本单只跑这三枚件）
& $py -X utf8 -m pytest tests\test_r595_group_derivation.py tests\test_r595_stall_cap.py `
      tests\test_r595_honest_span.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r595pt" -q
```

退出码契约：`0` 正常交数；`2` 件取不到／读不通（🔴 包括「sidecar 取不到 ⇒ 没有诚实跨度可算，**不许拿 `latency_ms` 顶替**」）；
`3` 夹具里有 `:352` 名单之外的 `category`（要改纸面，不由本件自创群）；`4` 在册自洽闸 `guard_latency_cell` 当场炸（这一窗读数不可用）。
`--sidecar` 缺省时按件名同规律推（`answers-X.jsonl → sidecar-X.jsonl`，与 `scripts/eval_lane_readout.py:102` 同源），认不出就 rc=2 明说，不猜。

### 6.6 改码后等值复跑（12:4x，判据④的复算表在这一步重新验了一遍没被改坏）

把 12:3x 那处改码（空群那一格不再冒充 `agree`）落进件里之后，六扇窗**逐窗重跑 `--json`**，与改码前的副本（`%TEMP%\r595snap\*.json` → `%TEMP%\r595snap4\*.json`）逐字段比：
`cells`／`tiers`／`hits`／`above`／`drift`／`rejects`／`ledger_error` **五扇全等**（run13／run14／run6／run7／run9），
唯一差异＝`scale.<群>.empty` 这一枚**新增的键**（五扇的 `empty` 全为 `false`；run16 改码前没留 `--json` 副本 ⇒ 不入逐字段比对，只以 §5.3 两行文本读数对账，它那一格现在是 `empty=true`／`agree=false`）。
⇒ 这处改动**没动过任何一枚数**，它只把「说不出数」那一格从假 `agree=True` 改成明写说不出数。

**确定性（同一 HEAD、同一批只读件）**：`run13`／`run9` 两窗各跑**两遍文本读出**，输出 sha256 前 12 两两全等
（run13 `fbd1f9593afe` ＝ `fbd1f9593afe`；run9 `f3437a2ac03f` ＝ `f3437a2ac03f`，12:59:29 现取）⇒ 「每班手推一次一个数」这件事从本件起不可能再发生。



---

## 七、常驻钉与两把反证（判据⑤）

三枚件共 **24 枚用例**，样本全部件内自造（`tmp_path` 里现写现用），**没往 `tests/fixtures/**` 塞一个字节**；
读到的真实件只有两枚在册只读原件：题集 `tests/fixtures/business_evaluation_100.jsonl`（判据②要它复现历史 n）
与 `docs/testing/{answers,sidecar}-run9.jsonl`（判据①后半格的凭据窗）。

| 件 | 枚数 | 钉住什么 |
|---|---|---|
| `tests/test_r595_group_derivation.py` | 8 | 三份名单逐字等于 `:352`；`category` 维 64／35／6 与 `tier` 维 50／35／20 各自复现板上历史 n；两维并排印那句的账闭合（21 枚重数 − 7 枚漏数 = 14）；名单外的 `category` ⇒ rc=3 点名不并群；**n 必带**（空群也印 `n=0`）；判据口径 p95 = 最近秩且与 `build_latency_cell` 同数（🔴 **空群不许冒充**：`build_latency_cell([]).p95` 是 `0` 而本件是 `None` ⇒ 印「两把尺都说不出数」而不是 `agree=True`）；🔴 **改派生规则就红**（`test_derivation_moves_a_row_when_the_rule_moves` 现场把「主动洞察」挪群，成员数与 `n` 跟着变） |
| `tests/test_r595_stall_cap.py` | 8 | 帽值现读（合成量具件 42 s／7 s ⇒ 读数跟着走；env 名与字面默认也从那份件读）；env 覆盖生效；命中单列进抬头；**命中不进判据口径 p95、含帽 p95 仍在纸面**；命中数只在**本群成员**里数（拿全局数冒充＝红）；`kind=queued_stalled` 即使远低帽值也算；超帽带不摘；run9 凭据 `chat-11` 由机器自己抓到且三枚 p95 逐位复现 |
| `tests/test_r595_honest_span.py` | 8 | 🔴 **`latency_ms` 被拒收当跨度**（run6 那三枚几十倍假数逐枚点名、聚合里一枚都不许出现）；两列同带时点名零枚但聚合仍只用 `wall_ms`；sidecar 缺行 ⇒ 明写「不许顶替」并点名，不补；`wall_ms` 自己越出一发量级上限 ⇒ 不计入；`wall_ms` 读不成毫秒 ⇒ None 不是 0；同题多轮取最大 `attempt`；sidecar 缺件 ⇒ rc=2 不猜；**只读纪律**（三本件跑前跑后 sha256＋mtime 一字不动，旁边不落新件） |

两把反证（逻辑摘除 ⇒ 跑同名件 ⇒ 逐字节还原；驱动器 `%TEMP%\r595_mutate.py`，快照 `%TEMP%\r595snap\pristine-r595.py`）：

| 反证 | 摘法 | 摘前 sha12 | 摘后 sha12 | 同名件读数 | 还原后 sha12 |
|---|---|---|---|---|---|
| 甲：**摘掉命中单列**（抬头那句＋`### 停表帽命中` 那一整格） | 从 `render()` 里删掉这两段 | `0151caf15659` | `a145787f9577` | 🔴 **3 failed / 21 passed，rc=1**：`test_cap_hit_is_listed_and_out_of_the_caliber_p95`／`test_above_band_is_named_but_never_removed`／`test_run9_book_credential_is_reproduced` | `0151caf15659`（与快照**逐字节全等 True**，35910 B／603 行） |
| 乙：**把跨度换成 `latency_ms`**（`collect()` 里 `spans[row_id] = span_ms(...latency_ms) or span`） | 一行 | `0151caf15659` | `23ffd1ec88fb` | 🔴 **4 failed / 20 passed，rc=1**：`test_wall_ms_is_the_only_span_that_reaches_the_aggregate`／`test_zero_drift_when_the_two_columns_agree`／`test_same_question_multiple_attempts_takes_the_largest_attempt`／`test_run9_book_credential_is_reproduced` | `0151caf15659`（同上 True，35910 B） |

干净树复跑：**24 passed**（`-o addopts= -p no:cacheprovider --basetemp=…\r595pt -q`，rc=0；conftest 的 R56 闸门报 `blocked connect attempts to host model port: 0` ⇒ 全程零网络）。
按规矩**没跑全量门**，执行层不 commit。

---

## 八、没验的格子（如实列，不当达成）

1. 🔴 **本格不判 A① 绿不绿**（判据⑥）。纸面只到「三组数＋命中单列摆清楚」为止；90 s 那条线的裁权在总控。
   本件交出的 run13／run14 问答类 p95 是 118.3／128.3 s，**这两格会不会被总控判成 A① 的红灯，本席不猜**——它们也从未被公布过（板上 `:6478` 那两窗只印整表）。
2. **带噪窗**：run17 正在跑（11:25:48 开窗，§4EM 记「同机四枚在途」）⇒ 本席**没打 8001／11434、没动容器、没起服务、没写 `%TEMP%\evalrun`**（conftest 的 R56 闸门读数 0 枚 blocked attempt 是旁证）。
   复算用的 run16 窗本身就是带噪窗（§4EK 记同机多枚），它的时延读数按**「通过可信／不合格不作结论」**处理；run13／run14 的窗记只带 `probe_ok=true`，本件不替它们声明安静。
3. **`tier` 那维不是门槛口径**：它只被用来把「n=64 还是 n=50」这笔账摆成机器数。拿 `tier=问答 n=50` 去判 A① ＝ 换母集换绿红，:4176 已禁，钉子也钉了。
4. **p95 排名规则纸面没钉死**（§5.5 最后一段）：最近秩 vs 线性插值两把尺历史混用，本件按在册 `build_latency_cell` 取最近秩当判据口径、线性一并印出。**这一格请总控裁**，本席不动 `:352`／`:383` 的字。
5. **run6 的「问答档 p95 68.9 s」复现不出来**（§5.5 表第一行，试过 8＋3 种组合，点名 max 那一枚是 `scope-02 81947.5 ms / kind=approved_ok`）⇒ 登记**待查**，不是已澄清。
6. **run5 及更早的窗不可复算**：`%TEMP%\evalrun` 只剩 run13／run14／run16 三扇＋在树的 run6／7／8p2／9。
   板上 `:3480`（run5）那句「问答类 n=64 avg 30.1／p50 25.8／p95 61.0 s」与 `:352` 的 run4 读数**没有原件可复算**，本件只登记「不可复算」，不判它对错。
7. **帽带这一档的真窗凭据只有一扇**：run9 的 `chat-11`。run13／run14／run16 三窗零命中，「命中不进 p95」这一格因此只有 ①合成样本 ②run9 原件 两种证据；
   等下一扇真出现 `queued_stalled` 的窗再补第三种（`queued_deadline`／`queued_no_status` 那两族今天**没接**，本件只认 `queued_stalled`＋帽带，别的未识别终态一律落进「超帽带点名」那一格，不冒充命中也不冒充慢答）。
8. **没量到的形状**：`EVAL_QUEUE_STALL_SECONDS` 被改成非 300 的现网窗（本件只用合成件验过 env 覆盖）；`wall_ms` 为 `null` 与整行缺失两种形状在真窗里都没出现，只有钉子用例覆盖；
   `analysis`／`report` 分道（`REPORT_LANE_VIA_QUEUE`）开着跑的那一窗＝run16，它没有问答类成员 ⇒ 三组数里「问答类空」这一格只在 run16 上有真窗证据。
9. **本件不改任何既有量具**：`scripts/eval_*`、`run_quality_evaluation.py`、`r580*` 一字未动（写域所限）；`run_quality_evaluation.py:25` 那句只打整表 `p95_ms=` 的窄读数**仍在**，要靠人改用本件才交三组数——这一格是总控的取舍，不在本单写域。
10. **本单中途改过一次码**（12:4x，本席复接入席时干的活；🔴 不是总控纠的，也不是本席首班量出的新病——首班交回单已把这格列成「唯一未完项」，
    只是它那台 patcher 卡在自己多写的一条 `assert` 上，到交回时一个字都没落）。改的是：首班把那一格写成 `agree or (not used and inbook["p95"] == 0)`，
    等于拿在册那把尺对空集交回的 `0` 冒充「两把尺同数」。
    改码＋补钉（第 24 枚 `test_an_empty_group_never_claims_the_two_rulers_agree`）＋六窗等值复跑（§6.6）＋两把反证重跑（§七那三列 sha 全是改码后的新值）。
    交回的 sha12＝`0151caf15659`／35910 B／603 行。🔴 登记这一格是为了不自带「一次通过」的假凭据——本纸 12:2x 那批读数**之前**的盘面是 `fba0851f9730`。

### 一句话交回

`:383`／`:384` 那两格从今天起有机器读数：**三组数（问答类／分析·报告类／整表，每格带 n）＋「停表帽命中 N 枚」抬头＋逐枚命中清单**，
帽值现读、跨度只认 `wall_ms`、分群派生规则改了会红；R205a 的三枚倍差与 R440 的 `chat-11` 凭据都被本件自己复现到逐位。
