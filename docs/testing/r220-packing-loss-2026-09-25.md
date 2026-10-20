# R220 · top-k 里有、进 prompt 没有 —— 首份读数（2026-09-25）

- 量具：`scripts/r220_packing_loss.py`（孤本，09-24 在 `be-r220` 登记，从没跑过、从没进过任何文档）
- 基点：`36c9973`（主树当前 HEAD），工作树 `be-r220b`
- 执行：`Fermi`（总控验收与代提交）
- 离线：零模型调用、零容器、零 `/api/v1/ask`、对仓内跟踪件零写入。R56 端口闸门实测
  `blocked connect attempts to host model port: 0`，R134 闸门实测
  `PersistentClient 调用: 0 次`。

## 0. 一句话结论

**量具能跑通，不变式成立，但它今天只答得出一半问题**：105 题 / 420 行 top-k 里
**375 行（89.3%）没进 prompt**；三桶 = 房不够 **6** + 名次侧 **93** + 判不了 **276**，
并起来正好等于 375。**73.6% 的损失行判不了**，而这 276 枚里 187 枚的成因是同一件事：
`deploy/workspace-seed.json` 在册、本机 `documents/` 无料的那几枚文件（`test_corpus_parity`
今天已经把它们钉成 `SERVER_ONLY_ROWS`）。⇒ **这份读数今天不能用来宣布"装箱只吃掉 6 行"**，
它只能宣布"在拿到那几枚文件之前，装箱那一格最多只能排除 6 行"。

## 1. 交付的三枚字节

| 文件 | sha256 |
|---|---|
| `scripts/r220_packing_loss.py`（改后） | `D651DE1FDD70CF25FF3ABBF840D668D66AC52B60AE7F11FCD7F2513E7CC7506E` |
| `tests/test_r220_packing_loss.py`（新） | `04C85BB08AF457128D34285923B66788BA2535BAEB967299B70516AF82D1397E` |
| 本报告 | 不自钉（自己写自己的 sha 必然对不上）；交付时由总控 `git status` 与字节数核对 |

改前 sha256 = `48AD3B5180A620DF4DBD429E2581CBDD6AAFF2191050F9B8D1EDF63822F22EF9`，与
`be-r220` 原件逐位相同（开工第一动作实测；比对全程只读取哈希，未向 `be-r220` 写一个字节）。

### 1.1 为什么非改不可：那两枚读点从没读到过数

孤本在 `36c9973` 上**跑不通**——四枚按真源取的数里，两枚就地 `LookupError`：

| 读点 | 原读法 | 在 `36c9973` 上的真源形状 | 定性 |
|---|---|---|---|
| `top_k` | `call_keyword_int`：只认 `f(top_k=<int>)` 这种**关键字实参** | `app/agents/tools.py:941-943` 先落 `retrieval_kwargs = {"top_k": 5,}`，`:947` 再以 `**retrieval_kwargs` 展开进 `search_for_principal(...)` | **漂移**：R112（`287c628`，2026-09-20）把它从关键字实参改成字典键 + `**` 展开 |
| 召回深度 | `call_positional_int`：只认 `self.semantic.search(q, 8, where)` 这种 **`Call.func` 直接调用**的第 1 号位 | `app/rag/retrieval_pipeline.py:891` = `futures[ex.submit(self.semantic.search, q, 8, where)]`：被调方是**一等对象**，降在 `ex.submit` 的 0 号实参位，深度 `8` 因此在 2 号位 | **出生即读不到**（不是漂移）：`git log -S 'ex.submit(self.semantic.search'` 只命中 `88b9430`（2026-06-24），这一行从未换过形状 |

两枚读法各改为**同时认两种形状**，并把"命中的是哪一种"变成读数本身（`top_k_shape` /
`recall_depth_shape`，进 `--json`、进 §0 表、被钉子钉住）。三条硬约束守住了：

- 没动 `app/**` 一个字节（`git diff --stat -- app frontend tests docs` 空）。
- 没抄字面量：两枚读法仍然从**调用点**取值，字典那一支还额外要求该变量真的以 `**` 展开进
  同一函数体里的调用，否则读的是死变量。取不到就 `LookupError`，失败面比改前更大不是更小。
- 值本身没变：`top_k` 仍是 5，召回深度仍是 8 —— 变的是"读法跟不上形状"，不是"数变了"。

逐字节差分：`git diff --no-index` 对 temp 里的原件副本 = **+79 / -16 行**，全部落在
模块抬头 1 行、两枚读点函数、`pack_numbers()` 取数三行、`render()` 真源列两行。

## 2. 那四枚真源在 `36c9973` 上的复核结论（逐处给行号）

| 数 | 值 | 真源 | 结论 |
|---|---|---|---|
| 容量 | 2560 | `app/agents/contracts.py:157` `ModelBudget.input_budget_tokens`（= n_ctx 4096 − 该档 max_tokens 1536，`app/common/model_budget.py:231` / `:192`） | **成立**（现场算，未抄） |
| 壳预留 | 456 | `app/rag/retrieval_pipeline.py:596` | **成立** |
| 历史预留 | 906 | `app/rag/retrieval_pipeline.py:607` | **成立** |
| 最终 top-k | 5 | `app/agents/tools.py:942`（经 `:947` 的 `**retrieval_kwargs` 到达调用点） | **形状漂移，值未变** ⇒ 读点已修（见 §1.1） |
| 召回深度 | 8 | `app/rag/retrieval_pipeline.py:891` | **读点出生即坏，值未变** ⇒ 已修（见 §1.1） |
| 附带三枚 | `analysis` / 500 字 / 5 槽 | `retrieval_pipeline.py:611` / `:617` / `:276` | **成立** |

另核两把尺与产品同源（不然"房不够"那一句不成立）：量具的 `room` 与
`retrieval_pipeline.py:628 context_pack_room()` 同算式，实测相等；量具计枚用的
`estimate_text_tokens` 就是产品 `text_pack_tokens`（`retrieval_pipeline.py:636-640`）转发的同一枚函数。
两笔都由测试钉住，不靠本段话自证。

## 3. 跑通并出数（判据①）

命令原文（解释器按派工单指定的主树 venv；`be-r220b` 下无独立 venv）：

```text
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe
    C:\Users\fengx\PycharmProjects\be-r220b\scripts\r220_packing_loss.py
```

- **EXIT = 0**，stderr 0 字节
- **墙钟 6.1 s**（另两次复跑 6.3 s / 6.4 s）
- 确定性：连跑两次 `--out` 到 temp，产物 sha256 逐位相同 =
  `1e57b2f095c8ce1a7b0477e56608228d0d52bdfd23adee97298ee7b404070231`

读数用的数（量具自己 §0 表，一枚都不是抄的）：

| 项 | 值 |
|---|---|
| 装箱档 | `analysis` |
| n_ctx / 该档输出上限 | 4096 / 1536 |
| 容量 input_budget | 2560 |
| 预留 = 壳 + 历史 | 456 + 906 = 1362 |
| **本轮房 room** | **1198** |
| 单条正文上限 | 500 字 |
| 最终 top-k | 5（命中形状 `dict_splat`） |
| 多路 query 槽位 / 单路召回深度 | 5 / 8（命中形状 `submitted_callee`） |

只读原件指纹（量具自己记的那一枚）：

- `r59b-recall-comparison-2026-09-24.json` = `4214eaff36fcc84e1f651a7bfc3bb63b30d153448774ee731c71785b11f62d5d`
- `answers-run6.jsonl` = `d50c2f9805ffa2dfed7154115ebfc9f173c954f07d26ff0776b6fb1637b5bb5a`
- `business_evaluation_100.jsonl` = `2230b2b45be18bfbb19f2f58a5ba55a5b36b444060886a30dcf073a81d678bab`

**三桶逐桶枚数与总损失行**：

| | 枚数 |
|---|---|
| 题 | 105 |
| top-k 行（分母） | 420 |
| **总损失行** | **375**（= 420 的 89.3%） |
| `lost_by_room` 房不够 | **6** |
| `lost_before_packing` 名次侧 | **93** |
| `lost_unattributed` 判不了 | **276** |
| 三桶并起来 | 6 + 93 + 276 = **375** ✓ |

族表（量具 §1 原文，按损失行倒序）：

| 族 | 题 | top-k 行 | 损失行 | 损失率 | 房不够 | 名次侧 | 判不了 | 袋中外来行 | 复算不干净题 | run6 判对率 |
|---|---|---|---|---|---|---|---|---|---|---|
| 文档问答 | 19 | 85 | 73 | 85.9% | 2 | 9 | 62 | 58 | 17 | 68.4% |
| 多轮对话 | 12 | 60 | 56 | 93.3% | 1 | 17 | 38 | 28 | 11 | 41.7% |
| Excel计算 | 12 | 55 | 51 | 92.7% | 0 | 1 | 50 | 12 | 11 | 58.3% |
| 报告生成 | 12 | 55 | 49 | 89.1% | 0 | 14 | 35 | 38 | 8 | 50.0% |
| 口径冲突 | 19 | 60 | 47 | 78.3% | 0 | 22 | 25 | 30 | 6 | 31.6% |
| 主动洞察 | 7 | 25 | 24 | 96.0% | 1 | 9 | 14 | 10 | 5 | 57.1% |
| 审批判断 | 6 | 25 | 20 | 80.0% | 1 | 5 | 14 | 25 | 5 | 83.3% |
| 无证据问题 | 4 | 20 | 20 | 100.0% | 0 | 7 | 13 | 10 | 3 | 25.0% |
| 图表生成 | 4 | 15 | 15 | 100.0% | 1 | 8 | 6 | 0 | 3 | 75.0% |
| 工具调用 | 4 | 10 | 10 | 100.0% | 0 | 0 | 10 | 0 | 2 | 75.0% |
| 跨部门权限 | 6 | 10 | 10 | 100.0% | 0 | 1 | 9 | 11 | 2 | 16.7% |


## 4. 不变式成立且被钉住（判据②）

量具自述的口径是"三桶互斥、并起来正好等于损失行"。这句话**由代码结构保证**：
`replay()` 的 `kept` / `dropped_room` / `unattributed` 三者对这一发名次是**划分**（要么整段
送到底，要么在"取不到块长"或"房顶穿"那一枚就地停并把后缀整段归给一边），
`analyze()` 再按 if/elif 链给每个损失块唯一一桶。

🔴 所以"只读量具自己写的桶标签"的断言是**恒真的**，摘掉任一桶它都不会红。测试件因此
不复用量具的结论，三样都自己取：名次集合直读 `r59b` 那份 json 的 `chroma_ids`、进场集合
直读证据袋的 `source_id` 字面（量具走 `source` + `chunk_index` 那条**另一条**拼接路，两路必须同解）、
装箱调**产品函数** `pack_prefix_by_rank` 而不是量具里那份副本。`tests/test_r220_packing_loss.py` 里
承担这一枚的是：

- `test_the_three_buckets_survive_an_independent_recomputation` —— 逐题逐桶对判，§7 反证实测它红。
- `test_the_three_lost_buckets_are_mutually_exclusive_per_question` —— 钉"桶与桶不重叠"，
  外加"四桶覆盖满这一发名次"。
- `test_the_three_buckets_sum_exactly_to_the_loss_rows` —— 逐题与全表两级 `sum(三桶) == lost_n`。
- `test_local_packing_copy_matches_the_product_function` —— 兑现量具自述那句"等价性不是嘴上说的"：
  7 形态（房=0、第一枚就装不下、恰好装满、后缀整段丢、零成本块打头、空输入、8 枚恰满）
  与产品函数逐向量同解。

## 5. 276 枚"判不了"的成分 —— 这份读数的真实分辨率

`lost_unattributed` 不是一个桶，是两种东西混在一起，必须拆开才不许越界：

| 成因 | 枚数 |
|---|---|
| 这一枚块长本身就取不到（就地停的那一枚） | **187** |
| 块长取得到、但被前一枚缺料的块整段拖进"判不了"（就地停 ⇒ 往后一律判不了） | **89** |
| 合计 | 276 |

那 187 枚逐文件点名（`--out` 报告里 `corpus_missing_files` 三枚）：

- `深度学习入门：基于Python的理论与实现.pdf` —— **181 枚**（一本文档吃掉全库损失行的 48%）
- `六级作文模板.docx` —— 4 枚
- `browser_acceptance_policy.txt` —— 2 枚

这三枚**不是新发现的丢失**：`deploy/workspace-seed.json` 在册、本机 `documents/` 无料，
`tests/test_corpus_parity.py:23` 早把它们连同 `深度学习技术栈学习路线.pdf` 钉成
`SERVER_ONLY_ROWS`（该件注释原话：加宽即承认数据丢失）。R220 只是第一次量出**这个已知缺口
值多少钱**：它把这份量具在本机的分辨率压到 99/375 = **26.4%**。
`test_the_unattributed_bucket_is_only_the_known_server_only_gap` 把这条因果钉死 —— 哪天
`documents/` 里文件还在、块号却取不到（splitter 换参数 / 向量库与磁盘不同源），那一枚会红，
而不是静默把这几枚算进"房不够"或"名次侧"任何一边。

## 6. 逐题可追 + 三行手工复算（判据③）

损失表每一行都带 `题号 + 被丢的 source_id + 落点桶`（`detail` 逐格给名次、块号、字数、
正文枚数、含行头枚数、桶、以及"这块在别的题上进过几次袋"）。
`test_every_loss_row_is_traceable_to_a_question_a_block_and_a_bucket` 钉住
`detail 非 in_prompt 的集合 == lost_ids` 且 `lost_n + evidence_n - foreign_n == top_k`。

抽三行手工复算（房 = 1198 枚；复算就是"按名次累加，第一次顶穿就停"）：

**`approval-04`（审批判断，混两桶）** —— 名次 1..5 的正文枚数：323 / 368 / 278 / 134 / 255。
累加 323 → 691 → 969 → 1103 → **1358 > 1198** ⇒ 前 4 枚装得进、第 5 枚起装不进。
证据袋 6 行里没有一条 top-k（外来行 6），所以 5 枚全算损失：房不够 1（第 5 名
`年度经营报告2026H1.txt_3`）+ 名次侧 4 + 判不了 0 = 5 ✓ 与量具逐位相同。

**`metric-07`（口径冲突，纯名次侧）** —— 枚数 112 / 24 / 104 / 140 / 297，累加 112 → 136 → 240 →
380 → **677 ≤ 1198** ⇒ 整发都装得进，房不够应为 0。证据袋 **0 行** ⇒ 5 枚全损失且全在名次侧：
0 + 5 + 0 = 5 ✓。这一行也说明"名次侧"那一桶装的是什么：不是装箱丢的，是**那一发压根没把这
5 枚当候选**（与 §94 A④"8/13 是派工里根本没有 doc 腿"同一形状；本批 31 题是 `袋空 ∧ 腿不空`）。

**`data-01`（Excel计算，纯判不了）** —— 第 1 名 `深度学习入门：基于Python的理论与实现.pdf_50`
本机无料 ⇒ 就地停 ⇒ 从第 1 名往后整段判不了，即便第 2、3 名（24 枚 / 112 枚）取得到块长。
房不够 0 + 名次侧 0 + 判不了 5 = 5 ✓。这一行是 §5 那 89 枚"被拖进判不了"的现场样本。

## 7. 反证真做并还原（判据④）

按派工单给的例子，**把 `lost_by_room` 的判据摘掉、强行并进"没损失"**：在 `analyze()` 里
`present = present | by_room` 并清空 `by_room`（临时 3 行，用完即还原）。

红色恰好落在 ②/③ 那两枚钉上，**别格一枚没牵连**：

```text
FAILED ...::test_the_three_buckets_survive_an_independent_recomputation
FAILED ...::test_the_three_buckets_sum_exactly_to_the_loss_rows
FAILED ...::test_the_shipped_reading_is_this_batch_end_to_end
FAILED ...::test_a_spot_question_carries_exactly_the_hand_recomputed_buckets[approval-04]
4 failed, 18 passed in 1.29s
```

第一枚的红色指名到块，不是空响：

```text
AssertionError: 量具的桶与自己复算的桶对不上（前 3 条）：
  [('approval-04', 'lost_by_room', [], ['年度经营报告2026H1.txt_3']),
   ('approval-04', 'in_prompt',    ['年度经营报告2026H1.txt_3'], [...]),
   ('chart-02',    'lost_by_room', [], ['员工绩效考核办法V1.0.txt_4'])]
```

第二、三枚报 `assert 369 == 375`（摘掉 6 行"房不够"后损失行少记 6）—— 这正是 §4 说的"恒真钉
抓不到、独立复算钉抓得到"。保持绿的 18 枚含：装箱副本等价（7 形态）、两枚预留常数、
真源读点形状、桶互斥、语料缺口归因、离线 import 闸、三份输入指纹。

还原凭据：从 temp 里 mutation 前的副本回写，还原后 sha256 =
`D651DE1FDD70CF25FF3ABBF840D668D66AC52B60AE7F11FCD7F2513E7CC7506E`，与改前逐位相同；
`rg -F "反证 R220" scripts/r220_packing_loss.py` **零命中**（证明没有残渣），
复跑 `tests/test_r220_packing_loss.py` = **22 passed in 1.35 s**。

## 8. 边界：这条读数不能用来宣布什么（判据⑥）

**产物在树 ≠ 判据达成。** 下面每一条都是这份读数**说不了**的：

1. **它不回答"分数为什么是这个数"。** 它只回答"top-k 里有多少没进 prompt"。`correct` 列是量具
   自己拿 `app.quality.eval._is_correct` 对 run6 答案重算的 54 对 / 51 错，**不是** run6 的官方
   `correctness/evidence`，两把尺不许互换。
2. **`top-k` 是"纯向量腿、原题 query、k=5、无 where 下推"的名次**（取自
   `r59b-recall-comparison-2026-09-24.json` 的 `chroma_ids`），**不是产品链路最终那 5 条**。
   两集合的差同时混着名次侧与装箱侧，本件只做了拆桶这一半。
3. **⓪ 那一格（工具 query）今天量不到。** `answers-run6.jsonl` 的证据行字段里没有 `query`，
   doc 腿那一发模型自己填的串无从复原 ⇒ "改写/词表扩展没把它挤掉"这类话**不能排除**。
4. **"房不够 = 6"是下界，不是结论。** 复算用的是**正文**尺子（`body[:500]`）与**整发满房**，
   而产品 `tools.py:962-966` 装的是**带行头的整段**（`[i] 来源:… 相关度:…\n正文`）、
   到 `tools.py:972-974` 才交装箱；且房不是满房，是 `context_pack_room() 减去本轮已记账`
   （`tools.py:851-857`，R117 按轮记）。两处偏差
   同向：真实房不够 **≥ 6**，真实名次侧 **≤ 93**。含行头那把尺也量了（`top5_unit_tokens`），
   5 枚房不够题两把尺都超房（如 `approval-04` 正文 1358 / 含行头 1459 vs 房 1198）。
   产品的 `keep_first_truncated` 与 R122 `PACK_MIN_STUB_BODY_TOKENS` 门槛复算一概没有。
5. **"零损失 22 题"里有 21 题是假零损失。** 那 21 题 `chroma_ids` 本身为空（向量腿返回 0 行 ——
   就是 R59/P3 那一格，`r59b` summary 记 `chroma_zero_rows: 24`）。**真正"top-5 全进了袋"的
   只有 `metric-06` 一枚。** 量具的 `全表 … 零损失题：22 / 105` 这句**不许**被引用成
   "装箱在 22 题上没掉链子"。这条边界已被钉：`SHIPPED["clean_questions"] == ["metric-06"]`。
6. **名次源是退役中的那一枚引擎。** 分母取 Chroma 腿名次，而生产向量库已定 PGVector。
   同判据把名次源换成 `pg_ids` 复算：**525 行 top-k / 472 行损失（89.9%）/ 房不够 10 /
   名次侧 133 / 判不了 329**，`top_k==0` 题数 21 → **0**，零损失题 22 → **1**。损失率两腿
   几乎相等（89.3% vs 89.9%），但**"21 题空腿"在 PG 侧不存在** ⇒ §5 的边界 5 是引擎属性，
   不是检索属性。这条是复算结论，不是产品结论：切读完成后 R220 必须换名次源重出，
   否则它量的是遗留件的形状。
7. 两份输入不同期：run6 开窗 09-23 22:42:07 → 收窗 09-24 08:56:35（`docs/testing/run6.stamp.txt`），
   `r59b` 那份 json 生成于 09-24 12:38:34（收窗后 3.7 h）。中间双写是否落进过新料，本班无法证明。

## 9. 只报不动（写域外）+ 请总控定夺

1. **跟进单的行号引用对不上。** 派工单说立项原文在
   `docs/handoff/2026-09-15-backend-followup-requests.md` "约 L4513-4525"；该文件实测**全文 2266 行**，
   §94 四真身在 **L2979-2981**（`### 四、R220 正式登记`）。已按 L2979 全文读。总控若还有别的
   单引用那套行号，值得核一次。
2. **同节记的"520 行孤本"与实际不符。** 实测该件 587 行（非空 509 行），且原件行尾是
   **586 枚 LF + 末行一枚 CRLF** 的混体。前者是登记笔误，后者是本仓"并树行尾"事故 #37 的老形状；
   本班按零行尾改动处理（改后仍是 1 枚 CRLF），要不要统一由总控定。
3. **`probe()` 那句"剩 -160 枚空房"会被读成房是负的。** 实义是"top-5 正文合计比房多 160 枚"。
   措辞不在本班改判据范围内，留给总控裁定是否改字（改 `render()` 一行，不动桶）。
4. **判不了那一桶今天吃掉 73.6% 的损失行。** 两个可选解法都在本班写域外，且都会改判据：
   (a) 就地停改成"跳过取不到块长的块继续算"（会把 89 枚从判不了挪进可判）；
   (b) 让量具读得到那三枚 server-only 文件（要容器卷或业主补料）。**要哪个请总控落笔。**
5. **名次源要不要现在就换 PG。** §8 边界 6 说明它决定 R220 长期量的是哪一枚引擎。
6. 交付面：`scripts/r220_packing_loss.py`（改）、`docs/testing/r220-packing-loss-2026-09-25.md`（新）、
   `tests/test_r220_packing_loss.py`（新）。**零枚既有测试件被改，`app/**` 零改动。**
   本班未 commit / 未 add / 未建分支 / 未跑全量门 / 未动容器 / 未打模型 / 未发 `/api/v1/ask`，
   `be-r220` 全程只读取哈希。

## 10. 定向复跑清单（总控复验用，全部零模型零容器）

```text
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r220_packing_loss.py -q        -> 22 passed
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_corpus_parity.py tests/test_r112_prompt_packing.py -q
                                                                            -> 86 passed
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r116_measured_room.py tests/test_r119_reserve_ruler.py -q
                                                                            -> 51 passed
C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe scripts/r220_packing_loss.py                        -> EXIT=0 / 6.1 s
```

解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（宿主 `python` 是 anaconda，无 chromadb）。全量门未跑，按派工单留给总控：`python scripts/run_gate.py`。

—— `Fermi`
