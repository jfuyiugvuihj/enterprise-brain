# R598 · 评测集改题收尾（R401 第二刀）交付纸

日期 2026-10-03 ｜ 执行层工单 R598 ｜ 基点 `b78ecd8`（detached）｜ 工作树 `C:\Users\fengx\PycharmProjects\be-r598`
授权链＝业主 10-02「这些你来做一样的」＋业主 10-03「3 批准」（按桶改题，含动评测集本体与钉住它的守卫）
＋总控 10-03 追加（A 桶「语料互斥」由总控代业主裁定，规则＝制度/细则条款 > 会议纪要/FAQ/过渡期安排，可推翻）。
判据全文＝跟进单 §160.4；本纸是该纸的执行版与读数回执。

## 0. 一句话结论

**本单落地的只有一件真修复：`docs/testing/fixtures/r97-shard-{1,2,3}.jsonl` 从主件逐字节重派生 ＋ 一枚常驻钉（含反向刀）。**
19 枚「查无出处」逐枚处置完毕（判据①一枚不落），结论是**全丙、零改题落地**：A 桶两枚逐字对账后判**真互斥**，
按判据③的逃生口保持丙；其余五桶分别属会话内真值 / CSV 主口径（另单）/ 输出形状与拒答（R600）/ 30 行母集冻结。
`doc-17` 的甲案凭据已**全套备好并实测**（影子根 19→18、分母 86→87、派生出处地址唯一、三枚错答全不命中），
🔴 但它要落地必须由总控先授权重录写域外的 `tests/test_r401_unscorable_rows_are_named_not_dropped.py`
（实调取证：6 枚测试函数在甲落地时先红，见 §4）。题源 `tests/fixtures/business_evaluation_100.jsonl`
**一字节未动**（行尾归一后与基点 blob 逐字节相等，已由本单新钉钉住）。

## 1. 三组数（判据⑨：全离线，零模型、零网络、零连库、零起服务）

### 1.1 `python scripts/check_eval_evidence_coverage.py` 全文读数（改前＝改后，逐字相同）

| 格 | 改前（10-03 14:5x 现读） | 改后（收工现读） |
|---|---|---|
| 题源 | 105 行 / 121 个 `must_contain` 词条 | 同（一字节未动） |
| 语料 | `documents/*.txt` 95 篇（主口径） | 同 |
| 查无出处的行 | **19** | **19** |
| 查无出处的词 | **19** | **19** |
| 口径指纹 | 行数 == 词条数，成立 | 成立 |
| 语义口径（件口径之上加严） | 20（唯一分歧 `tool-02` 锚词 `Word`，7 处裸子串全被 `password`/`your_password`/`myopassword123` 吞掉） | 20（同一枚分歧） |
| 退出码 | 0 | 0 |

全文两份留档：`$env:TEMP\r598_before_main.txt` / `$env:TEMP\r598_after_main.txt`（本单不把它们保进仓库，
避免又多两枚手抄账；要复跑见 §11）。

### 1.2 `unscorable_records()` 枚数与逐枚 id（现读，19 枚，与在册名册逐枚相同）

`doc-15 doc-17 chat-02 chat-09 chat-11 chat-12 data-07 data-08 insight-05 insight-06 insight-07
unsupported-01 unsupported-02 unsupported-04 tool-03 report-03 report-07 report-08 report-09`

逐枚 reason / missing_term / pool 齐全（缺一枚 `app/quality/eval.py:242 unscorable_records()` 当场抛），
本单没有改写其中任何一格的文本——丙案铁规（判据④）。

### 1.3 correctness 分母

| 量 | 改前 | 改后 | 影子根（若甲落地，本单**没做**） |
|---|---|---|---|
| 全部题数 | 105 | 105 | 105 |
| 丙案点名扣除 | 19 | 19 | 18 |
| correctness 分母 | **86** | **86** | **87** |

在册规则串（现读）：`answer_correctness_scorable_subset 的分母 = 全部 105 题 − 丙案点名扣除 19 题 = 86；
answer_correctness / evidence_coverage / total 仍按全部 105 题（题没删、锚词没动）。`

## 2. 逐枚处置（判据①：一枚不落，三选一）

台账由 `scripts/r598_disposition_ledger.py` 现读生成（🔴 该件不写死任何一枚数：缺口名册从语料复算、
reason/pool 从题源标记读、分母从 `derive_scorability` 长出来）。归类（桶）是本单新增的人工分析，其余全现读。

| 桶 | 枚 | 处置与去向 |
|---|---|---|
| A 语料互斥（业主裁定域） | `doc-15` `doc-17` | 丙·真互斥（§3 逐字对账）；`doc-17` 另附已实测的待授权甲（§4） |
| B 会话内真值 | `chat-09` `chat-11` `chat-12` `insight-07` | 丙·出处天然不在 95 篇；未找到语料在位且语义等价锚词，故无一枚够格走甲 |
| C CSV/数据侧真值 | `data-07` `data-08` `insight-05` `insight-06` | 丙·主口径「CSV 不算出处」本单一字未动（§1.7 归另单）；假想账见 §2.1 |
| D 产品行为/输出形状 | `tool-03` `report-03` `report-07` `report-08` `report-09` | 丙·必须改判分器才能救 ⇒ 账挂 R600（本单未碰 `app/quality/eval.py`） |
| E 拒答类（考「不编」） | `unsupported-01` `unsupported-02` `unsupported-04` | 丙·同上挂 R600；`unsupported-03` 已在 R401 走甲（具名码），本单未动 |
| F 母集冻结 | `chat-02` | 丙·在 `business_evaluation_30.jsonl` 母集里，改它要业主批准改版（另单） |

按 reason 现读归类的说明：`chat-02` 的不可考是**两重**的（词条「之后」只在备查 PDF 里 ＋ 30 行母集冻结），
故落 F 桶并注明第二重；`chat-11` 的锚词是「800元」这种**会话内注入值**，与 C 桶的「输出形状词」不同源，落 B。

### 2.1 CSV 假想账（判据③第三小节要「算给下一班看数」，本单现算）

采纳 `data/*.csv` 为出处：**救回 0 枚**，分母 **86 → 86**（覆盖度件 `--include-csv` 实测仍 19/19，指纹不破）。
逐枚缺词的命中面（派生腿现算，非引用历史注释）：`前五` / `小计` / `长期未处理` / `超标率` 在
`data/报销明细表.csv` 里 **0 命中**；唯一沾到 CSV 的是 `chat-11` 的第二枚锚词「审批」（它在 37 篇里到处有出处，
缺的是「800元」）。⇒ **结论：C 桶四枚缺的不是数据值而是输出形状词，与 D 桶同族，账应挂 R600，
不该继续挂着「CSV 口径」这条主口径的账。** 主口径（§1.7）本单未动。

## 3. A 桶逐字对账（判据③；原文全部从 `documents/**` 现读，一字节未改语料）

裁定规则「制度/细则条款 > 会议纪要/FAQ/过渡期安排」在**两位同档对手之间无法仲裁**；
登记表§〇.3（`制度与口径登记表.txt:10`）又明文放弃对「票据要求」作仲裁：

> 3. 本表不改动《费用报销管理制度 V2.1》《差旅费报销细则（2026 版）》《财务管理制度 V2.0》《企业管理制度手册》的实体标准（金额标准、**票据要求**、审批权限）。涉及金额标准、票据要求、审批权限的，一律以既有制度为准……

| 组 | 冲突双方（现读原文） | 判定 |
|---|---|---|
| `doc-15` 电子发票是否需打印 | `费用报销管理制度V2.1.txt:65`「员工无需再打印纸质版提交」 ↔ `企业管理制度手册.txt:65`「电子发票需打印后附在报销单后」 | **真互斥·保持丙** |
| `doc-17` 住宿发票抬头 | `差旅费报销细则_2026版.txt:32`「发票抬头须为公司全称」 ↔ `费用报销管理制度V2.1.txt:51`「抬头为公司全称或员工姓名（仅限差旅、通讯、交通类）」 | **真互斥·保持丙**（甲案凭据已备好，§4） |
| 第三组「住宿超标 需审批 vs 自理」 | `差旅费报销细则_2026版.txt:12`「超出部分自理」 ↔ 金标「需部门负责人审批」侧无据（`细则:30` 那句审批讲的是**超 30 天延期**，不是超标） | 见 §3.1 |

三点必须说白的细节（都影响结论，不是文笔）：
1. **总控提示为真但不改结论**：`V2.1:68`（过渡期 2025-06-30 前纸质仍可报销）与 `V2.1:65`（电子发票无需再打印）
   确是两条不同命题、不互斥；可 `doc-15` 的对手是 `企业管理制度手册:65`，不是 `:68` 那一行 ⇒ 命题换了也不构成仲裁。
2. **`doc-17` 的 t-04 指针不足以翻绿**：登记表 `:42`（t-04「发票抬头**开错**」，依据《差旅费报销细则（2026 版）》）
   事项是「开错怎么办（一律退回重开）」，不是「住宿发票可以开谁的抬头」；加上§〇.3 明文不裁票据要求 ⇒ 不构成对本题的仲裁指针。
3. **不翻绿还是因为它会固化假阳性**：`doc-17` 三跑正文「可以开公司抬头或员工个人抬头」正是 `V2.1:51` 的合法读数；
   把金标钉到 `细则:32` 等于用评测集替业主在两条制度之间选边，并把 `V2.1:51` 判成错答。

### 3.1 第三组现查（判据③点名要查的那一枚）

**「住宿超标 需审批 vs 自理」= `chat-10`，不在 19 枚里。** 一手凭据：`chat-10` 的 `r401` 标记为空（未判丙）、
锚词 `["部门负责人"]` 由派生腿在 10 篇语料里点得出出处（含 `差旅费报销细则_2026版.txt:7/30/31`、
`财务管理制度_V2.0.txt:17/27/28/29/54` 等），覆盖度件判它「有出处」⇒ 它今天照旧进 correctness 分母、照旧得分。
两处出处行号：命题侧 `documents/差旅费报销细则_2026版.txt:12`（超出部分自理）；得分依据侧
`documents/差旅费报销细则_2026版.txt:30`（超 30 天延期的审批，**不是**超标审批）。
⇒ 这是**得分侧的假阳性风险行**，不是丙案。本单不动它（动它＝改一条得分行的历史可比性，且同属业主裁制度那一族）。

## 4. 🔴 域外硬编码把「任何一次 rescue」卡死（一手实调，非读源码猜）

`tests/test_r401_unscorable_rows_are_named_not_dropped.py` 与
`tests/test_r401_anchor_provenance_is_derived.py` 都在 R598 写域外（判据⑤只许动两枚守卫件）。
取证工具 `scripts/r598_out_of_domain_forensics.py`（零写入：只 import 那两枚件的测试函数，
把 doc-17 按待授权账换成甲的**影子行**递进去调用）实测：**对照组（盘面行）全绿，实验组（甲行）6 枚函数先红**——

| 先红的断言行 | 函数 | 那一格钉的是什么 |
|---|---|---|
| `:95` | `test_unscorable_rows_are_present_named_and_untouched` | `assert len(unscorable) == 19` |
| `:140` | `test_main_caliber_reading_now_equals_the_unscorable_count` | `len(missing) == sum(...) == 19` |
| `:150` | `test_correctness_denominator_is_named_and_arithmetic_is_open` | `den["unscorable_n"] == 19` |
| `:249` | `test_fields_that_should_not_move_are_byte_identical_to_the_base` | `changed == set(r401.DETAILS)`（甲必须同时进 R401 的账） |
| `:119` | `test_disposition_ledger_covers_exactly_the_29_in_the_audit_doc` | 处置分布 Counter（甲落地即 `{丙:18,甲:8,乙:3}`） |
| `:299` | `test_unscorable_rows_carry_a_bone_fide_reason_and_a_destination` | `assert len(reasons) == 19`，另 `:306` 钉「语料互斥正好 2 枚」 |

同一批函数里被上面先红**遮蔽**（执行到第一枚 assert 就停，所以本单**没测到**它们各自的红）的后续硬编码，
重录时要一并点名：`:151 == 86`、`:154`（要求分母规则串里同时出现 "105"/"19"/"86"）、
`:165 == 86`、`:184 report["total"] == 86`、`:306 kinds[True] == 2`（那格钉的是「语料互斥正好 2 枚」，
甲落地会变 1 枚），
以及 `scripts/r401_anchor_provenance.py:denominator()` 的规则串（写死「105 − 19 = 86」——那枚脚本在写域内，
但本单没动它，见 §4.1）。另有 2 枚函数（`test_every_resolved_anchor_re_derives_to_the_recorded_address`、
`test_pointer_that_is_not_unique_in_its_line_is_refused`）的参数无法在取证脚本里注入，如实记 skipped，不装绿。

**为什么不是「先落一半」**：半落地会让 R401 件自己的对账 `r401.verify()` 立刻红（题源与账不同代），
而 `:107/:110-113` 正是「丙案铁规」钉——它明文封死「丙案行偷偷带 `anchor_provenance`」这条路。
所以任何非零的 rescue 都必须与那两枚件的重录同批并树，这属总控授权面。

### 4.1 本单为「将来要落甲」备好的东西

* 待授权账：`scripts/r598_pending_jia.py` 的 `PENDING_JIA["doc-17"]`（answer「住宿发票抬头须为公司全称」、
  锚词 `["须为公司全称"]`、`replaced_term` **从现算缺口取**、被替换原因、去向）。
* 出处**派生**（判据③禁手抄）：走 R401 那把现成的派生腿 `r401_anchor_provenance.py:provenance_for_row` →
  `documents/差旅费报销细则_2026版.txt:32`，归一化字节区间 `(2305, 18)`，行内命中 1 次、**全库唯一命中**。
* 收紧凭据：锚词取 6 字「须为公司全称」而不是 4 字「公司全称」——4 字那枚在 `企业管理制度手册.txt:65`、
  `费用报销管理制度V2.1.txt:45/51` 也命中（`V2.1:51` 正是**相反那一侧**的句子），会固化假阳性。
* 反证样本 3 枚（喂**真判分器** `app/quality/eval.py:_is_correct` 全不命中）：
  「住宿发票可以开公司抬头，也可以开员工个人抬头。」／「未找到关于住宿发票抬头类型的规定。」／
  「发票抬头一律为员工姓名，差旅类除外。」
* 影子根全套数（`--proof`，仓库盘面零写入）：19→18、行数==词条数成立、行数==丙案枚数成立、
  守恒漂移为空、改题枚 `[doc-17]`、丙案被动枚 `[]`、分母 86→87。
* 🔴 `scripts/r401_anchor_provenance.py` **本单已回退到基点（`git diff --numstat HEAD` 里它不在列）**：
  上一轮我曾把 doc-17 从它的 `UNSCORABLE` 挪进 `DETAILS`，实跑即打出 §4 那张红单；
  既然甲不落地，那本账必须留在「R401 那一刀的 19 枚」原状，否则就是半落地。
## 5. 三片重派生 ＋ 常驻钉（判据⑦：本单落地的正事）

改前一手读数（`scripts/r598_shard_sync.py --check`，退出码 1）与重派生后（`--write`，退出码 0）：

| 片 | 改前盘上 | 从主件应派生 | 改后盘上 | 本单变更行数 |
|---|---|---|---|---|
| `r97-shard-1.jsonl` | 7,552 B / `56df0c9a5c0b05b9` | 13,239 B / `b68511475045b221` | 13,239 B / `b68511475045b221` | 9 |
| `r97-shard-2.jsonl` | 9,324 B / `23ff1bd257b28e32` | 12,270 B / `fb8464de32ff5f40` | 12,270 B / `fb8464de32ff5f40` | 6 |
| `r97-shard-3.jsonl` | 7,470 B / `74bf5c493e02c181` | 16,432 B / `7e64b38eebfea6dd` | 16,432 B / `7e64b38eebfea6dd` | 14 |
| 三片拼接 | 24,346 B / `2230b2b45be18bfb` | 41,941 B / `686c564ff2985744` | **逐字节等于主件** | — |
| 主件 | 41,941 B / `686c564ff2985744` / 105 行 / 无 BOM / CRLF | 同（未动） | 同 | 0 |

两处交叉印证（不是巧合，是同一件事的两面）：`9 + 6 + 14 = 29` 行，与总控 10-03 现读的
「三片与主件 **29 行**内容不一样」逐枚对上；三片行数仍是 35/35/35、id 顺序与主件全同，差的只有内容
（缺 `anchor_provenance`、`answer`/`must_contain` 是 R401 之前的旧词）。

钉：`tests/test_r598_r97_shards_are_derived.py`（**14 枚**）。🔴 派生腿读**主件**，不是「把盘上三片互相比一下」的永真式：
`test_reverse_knife_only_the_master_moved` 只改主件一个词、三片原样不动 ⇒ 必红；
`test_legitimate_rederivation_still_passes` 把主件与三片按同规则一起派生 ⇒ 照绿（钉跟着事实走，没把某一天的字节冻成牢）。
钉里两边 sha256 前 16 逐枚打印（判据⑦要求的读数形态），并把「拼接比主件多/少字节」当场记账。

🔴 交工自证抓到的一枚**本单自身缺陷**（如实记，不含糊）：第一版把 `main()` 的出口名写成不存在的
`EXIT_OK`，而钉里 13 枚断言**全部直接调 `compare()`／`write_shards()`，从没走过 CLI 的 `return`**
⇒ 件照样全绿，`scripts/r598_shard_sync.py --check` 却当场 `NameError`（rc=1）。已改回 `EXIT_MATCH`，
并补上第 14 枚 `test_cli_exit_code_tracks_the_byte_verdict`：绿态必须返 `EXIT_MATCH`、手改片 1 必须返
`EXIT_MISMATCH`、两侧 sha256 前 16 必须真打出来。这枚新牙自己也验过：把出口名再改坏一次 ⇒ 该枚当场红；
回滚后脚本哈希与动手前逐字节相同（`55f6ae34a64b661a`）。⇒ 「量具有病而读数全绿」这一族从此在本单有据。

三片在代码里**零读者**（`git grep -l r97-shard -- scripts tests` 只回 `eval_window_shard_driver.py` 那族
**运行时**分片，与这三枚冻结件无关）⇒ 重派生不撞任何测试；被撞的是文档抄本，见 §5.1。

### 5.1 在册台账里需要总控订正的抄本（`docs/handoff/**` 与计划书是 R598 禁区，我一字节未动）

| 位置 | 现在写的是 | 本单后的真值 |
|---|---|---|
| `docs/handoff/2026-09-17-eval-real-run-runbook.md:413` | 已被总控 10-03 14:22 就地作废（假绿） | 可改判「✅ 重派生后逐字节相等：41,941 B / `686c564ff2985744`」，凭据 `scripts/r598_shard_sync.py --check` rc=0 |
| `docs/handoff/2026-09-20-eval-window-rehearsal.md:37` 与 `:358` | `concat bytes 24346` / `sha256 2230b2b4...` / `byte-equal: True` | 那条命令今天重跑给 `41941` / `686c564f...` / `True`；旧串是**当时那一代**为真，建议标「09-20 代」字样，别删（删了就把分叉的证据也删了） |
| `docs/handoff/2026-09-15-orchestration-board.md:3149` | `78b8507` 入仓登记 24,346 B / `2230b2b45be18bfb` 逐字节相等 | 三段账：入仓当时为真 → R401(`baef92e`) 后不同代 → R598 重派生后再次相等 |
| `docs/handoff/2026-09-17-human-gates.md:320` | 「逐字节**等长**的三片」 | 旧三片比主件短 17,595 B，「等长」从来不成立；重派生后成立 |
| `docs/handoff/2026-09-15-backend-followup-requests.md:1555` | 「已核验逐字节等于夹具、前缀 `2230b2b45be18bfb`」 | 同上，属旧代凭据 |
| `docs/handoff/2026-09-17-pgvector-adoption-plan.md:557` | 「三片与题源不同代，欠重派生＋一枚逐字节钉」 | **本单结清**，可改写为已还 |

顺带一枚本单撞到的既有红（不是本单引入，见 §10.2）：计划书 §8 第 557 行那处
``docs/testing/fixtures/r97-shard-{1,2,3}.jsonl`` 的反引号引用，被
`tests/test_r120_p3_collection_default.py` 的 `PATH_CITATION` 截成
`docs/testing/fixtures/r97-shard-`（正则字符类不吃 `{`），于是
`test_every_repository_path_named_in_the_runbook_exists` 判它「引用了不存在的路径」。
两种修法都在我禁区外（把计划书里那处写成三枚字面路径，或让那枚件认 `{1,2,3}` 大括号引用为 glob），交总控裁。

## 6. 反证刀总表（判据⑧：≥5 把，摘哪一把 → 哪枚红）

| # | 摘的这把刀 | 红了的那枚 | 在哪个件 |
|---|---|---|---|
| 1 | 甲案锚词换成语料不存在的词（`须为个人抬头`） | `test_T5_unresolvable_replacement_anchor_still_gets_named`：缺口不降且 `doc-17` 仍被指名、指名的是**新词** | `tests/test_r598_ledger_teeth.py` |
| 1b | 成对正刀：换成**在位**那枚（`须为公司全称`） | `test_T5b_...`：19→18 才算救援（两把对照，防「换词即救题」） | 同上 |
| 2 | 置空某枚 `must_contain`（`doc-01`） | `test_T1_...`：`StructureDrift` 拒绝出数，不是给一个更小的数 | 同上 |
| 3 | 删一行 105→104 | `test_T2_...`：尺子抛 + 守恒账非空 | 同上 |
| 4 | 甲案出处指针造假（同篇 `:31` / 另一篇 `手册:65`） | `test_T4_...`：派生腿 `DerivationError` ⇒ 钉的是**地址**不是「这词存在过」 | 同上 |
| 5 | `doc-01` 的 category 挪一档 | `test_T3_...`：分布那一格 + 逐枚那一格同时指名 | 同上 |
| 6 | 三片里偷改一个词（片 2） | `test_knife_a_...`：只有片 2 红，且拼接 != 主件 | `tests/test_r598_r97_shards_are_derived.py` |
| 7 | 少一片 | `test_knife_b_...`：`FileNotFoundError`，拒绝出数不装绿 | 同上 |
| 8 | 片序漂移（1↔2） | `test_knife_c_...`：片 1＋片 2 一起指名 | 同上 |
| 9 | 给片 1 加 BOM | `test_knife_d_...`：片 1 红 + 拼接多出 3 字节当场记账 | 同上 |
| 10 | 行尾 CRLF→LF（片 3） | `test_knife_e_...`：片 3 红（前提断言防刀空转） | 同上 |
| 11 | 少一行（片 3 尾行） | `test_knife_f_...`：片 3 红 | 同上 |
| 12 | **反向刀**：只改主词、三片不动 | `test_reverse_knife_only_the_master_moved`：必红 ⇒ 证明派生腿真读主件（永真式的凭据） | 同上 |
| 13 | 派生器收 104 行主件 | `test_derive_refuses_when_the_master_line_count_is_not_105` | 同上 |
| 14 | 派生把 BOM/LF「顺手规整」 | `test_derivation_preserves_bom_and_bare_lf`（合成 105 行主件） | 同上 |
| 15 | 从归桶账里摘掉一枚（`doc-15`） | `test_T6_...`：处置表抛「没归桶：判据①一枚不落」 | `tests/test_r598_ledger_teeth.py` |
| 16 | 归桶账里留一枚幽灵 id | `test_T7_...`：抛「已不在缺口名册上」 | 同上 |
| 17 | `replaced_term` 手抄错一个字 | `test_T8_...`：现算缺口对账抛 | 同上 |
| 18 | 待授权账里那枚已被别人落地 | `test_T8b_...`：拒绝继续出数而不是继续算它的账 | 同上 |
| 19 | CLI 出口写错名字／返错码（**本单第一版真踩过**） | `test_cli_exit_code_tracks_the_byte_verdict`：绿态必须 `EXIT_MATCH`、手改片 1 必须 `EXIT_MISMATCH`，且两侧 sha16 必须真打出来 | `tests/test_r598_r97_shards_are_derived.py` |

每把刀都自带「咬不到肉就自杀」的前提断言（例如刀a 若在同一批行里抠不到汉字、反向刀若抠不到「住宿」，
函数自己先抛），防止刀退化成空转——这是 R120 那族「假绿文案」的同族防线。

## 7. 可比性声明与逐枚 diff（判据⑩）

**可比性声明（照 R401 格式，但本单的实际内容不同，必须如实改口）**：
本单**没有**把任何一枚丙案改成甲/乙 ⇒ 评测集与 R401 并树后**同一代**，
`run13 / run14 / run16 / run17` 及以前的 correctness / evidence **仍可与今天直接比对**，
不存在「新锚词基线要从下一扇窗起」这件事。若总控随后批准落 `doc-17` 那枚甲，届时才需要 R401 那句原文：
「新锚词基线自本次改题后第一扇窗起，`run13/14/16/17` 及以前的 correctness/evidence 不可与新集直接比对。」
唯一与历史读数无关但要说清的：三片重派生只动文档冻结件（代码零读者），
历史窗吃的始终是主件（`window.json` 里 `fixture_sha256` 逐枚＝主件，总控已现读在册）⇒ 分数不受影响。

**逐枚 diff 表（105 行）**：全部 105 枚「一字节未动」。凭据两向同钉，都在
`tests/test_r598_eval_ledger_invariants.py`：
* 字节级：盘面题源与基点 `b78ecd8` 的 blob（行尾归一后）`sha256` 相等；
* 字段级：`conservation()` 逐枚比 `question/answer/must_contain` ⇒ `retitled_ids == []`，
  并逐列比 `tier/category/requires_evidence/conflict_pair/metric/department` ⇒ 违规表为空。
（为什么要点名「两向同钉」：上一族病就是只有字段级凭据，字节级漂移——BOM/行尾——读不出来。）

若甲落地，diff 只有那一枚（现读影子根实测，非纸面）：

| id | 字段 | 现值（盘面，未动） | 待授权值（影子已实测） |
|---|---|---|---|
| `doc-17` | `answer` | 一律开具公司抬头 | 住宿发票抬头须为公司全称 |
| `doc-17` | `must_contain` | `["公司抬头"]`（95 篇 0 命中） | `["须为公司全称"]`（全库唯一命中 `细则:32`） |
| `doc-17` | `r401.disposition` | 丙（missing_term=公司抬头） | 甲（带 `pre` 三列留痕 + `anchor_provenance`） |

## 8. 题源读者清单（开工前 `git grep -l` 列全；逐枚为何免改）

一手计数：**19 枚 `scripts/*.py` ＋ 35 枚 `tests/*.py` ＋ 2 枚 `app/**` ＝ 56 枚代码读者**（另 `tests/fixtures/business_evaluation_100.jsonl` 本身）。
免改的总理由只有一条：**本单没动题源一个字节**（§7 两向凭据），所以任何按 id／行序／字段读它的件读数不变；
下面是逐枚点名（按读法分组，组内每枚都点名）。

* **覆盖度／丙案／分母那一族**（读的正是本单出数的这三组）：`scripts/check_eval_evidence_coverage.py`、
  `scripts/r401_anchor_provenance.py`、`scripts/r438_correctness_denominator.py`、
  `tests/test_r94_eval_evidence_coverage.py`、`tests/test_r401_anchor_provenance_is_derived.py`、
  `tests/test_r401_teeth.py`、`tests/test_r401_unscorable_rows_are_named_not_dropped.py`、
  `tests/test_r437_anchor_word_boundary_not_bare_substring.py`、
  `tests/test_r438_correctness_denominator_is_wired_and_both_calibers_publish.py`
  ⇒ 读数逐枚与基点相同（19/19/86 未变），实跑点名见 §10.1。`check_eval_evidence_coverage.py` 本单**未加一行**：
  它的派生能力（`derive_term_provenance` / `derive_provenance_for_rows` / `--provenance`）R401 已建齐，§1.4/§1.5/§1.7 一字未动。
* **跑分窗与采集器**：`scripts/eval_window_planner.py`、`scripts/eval_window_shard_driver.py`、
  `scripts/collect_evaluation_answers.py`、`scripts/rehearse_eval_window.py`、`scripts/compare_vector_recall.py`、
  `scripts/r59_recall_compare.py`、`scripts/r59c_recall_compare.py`、`scripts/r595_latency_readout.py`、
  `scripts/r580_per_class_attribution.py`、`scripts/r561_queue_lane_piece_readout.py`、`scripts/r590_a2_leg_attribution.py`、
  `scripts/run_quality_evaluation.py`、`tests/test_collect_evaluation_answers.py`、
  `tests/test_r454_readout_is_generated.py`、`tests/test_r454_shape_subset.py`、`tests/test_r454_window_planner.py`、
  `tests/test_r595_group_derivation.py`、`tests/test_r595_stall_cap.py`、`tests/test_r44_hot_index_coverage.py`
  ⇒ 它们吃**主件**不吃三片，且主件未变；`--shard-*` 那套是运行时自切分片，与三枚冻结件不同名同路径不同物。
  🔴 `scripts/run_quality_evaluation.py` 与判分器同格，属本单「不改判分器」禁区，连读都没动它。
* **题面/档位/口径消费族**：`tests/test_evaluation_report.py`、`tests/test_r123_approval_ledger_report.py`、
  `tests/test_r123_hitl_approval.py`、`tests/test_r123_real_probe.py`、`tests/test_r126_rewrite_prev_turn.py`、
  `tests/test_r42_lane_rules.py`、`tests/test_r42_lane_ratio.py`、`tests/test_r42_numeric_questions.py`、
  `tests/test_r42_zero_model_calls.py`、`tests/test_r453_cloud_eval_override.py`、
  `tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py`、`tests/test_r520_declare_lane_env_leg.py`、
  `tests/test_r520_report_lane_contract.py`、`tests/test_r206_caliber_quotes.py`、`tests/test_r206a_caliber_kb_leg.py`、
  `tests/test_r216_clause_side_selection.py`、`tests/test_r181_text_frame_ruler.py`、`tests/test_r112_prompt_packing.py`、
  `tests/test_r120_p3_collection_default.py`、`tests/test_r219_tier_compare_teeth.py`、`tests/test_r220_packing_loss.py`、
  `tests/test_observability_routes.py`、`tests/test_r49_corpus_calibration.py`、`scripts/r218_switch_rehearsal.py`、
  `scripts/r219_rewrite_tier_compare.py`、`scripts/r220_packing_loss.py`、`scripts/audit_plan_ticket_ledger.py`
  ⇒ 按 id 取题面/按行数取夹具，字段与行序未变 ⇒ 免改。
* **`app/**` 两枚**：`app/api/v1/chat.py:1166`（注释里引那枚夹具做命中率对照）、
  `app/api/v1/observability.py:61`（默认评测集路径指向 `business_evaluation_30.jsonl`）⇒ `app/**` 是禁区，且都未受影响。
* **本单新增的读者**（只读主件／派生，不写仓库）：`scripts/r598_disposition_ledger.py`、
  `scripts/r598_pending_jia.py`、`scripts/r598_out_of_domain_forensics.py`、`scripts/r598_shard_sync.py`。
* 🔴 三片本身的读者：**零**（`git grep -l r97-shard -- scripts tests` 无命中，只有 `docs/handoff/**` 五处抄本 ⇒ §5.1）。
  ⇒ 没有任何一件需要跟着三片改；需要跟着改的全在文档，而那归总控。
## 9. 交付检查项（判据③点名要写的那句，加上随它一起裁的格）

1. 🔴 **客户真实制度若相反，改的是语料不是金标。** 这一条适用于 A 桶两枚与 §3.1 那枚得分侧：
   * `doc-15`：业主裁「电子发票归档后是否仍需打印附单」——`V2.1:65` 与 `手册:65` 相反；
   * `doc-17`：业主裁「住宿发票抬头可否为员工姓名」——`细则:32`（须为公司全称）与 `V2.1:51`（差旅/通讯/交通类可为员工姓名）相反；
   * `chat-10`：业主裁「住宿超标是自理还是走审批」——`细则:12`（超出部分自理）与金标（需部门负责人审批）相反。
   三处若业主采「另一侧」，**动作是改语料那一行并复跑覆盖度件**，不是把金标拧过去追正文。
2. `chat-10` 不在丙案名册却在得分：它靠一枚到处有出处的锚词（`部门负责人`）过关。要治它得先有业主裁定，
   再作为**得分行改版**立案（会动 correctness 历史可比性），不属本单。
3. C 桶（`data-07` `data-08` `insight-05` `insight-06`）实测**采纳 CSV 也一枚救不回**（§2.1）⇒
   请把它们从「CSV 口径」那一格迁到 D/E 那一族（输出形状词），账挂 R600；主口径 §1.7 本单未动。
4. D/E/C 三桶共 12 枚的出路都在**判分器形状**（拒答形状、输出形状、计算/洞察题的第二把尺），
   本单遵守判据⑤「不改判分器」，一枚未偷偷放宽 substring 去凑数。
5. `chat-02` 的母集（`tests/fixtures/business_evaluation_30.jsonl`）改版需业主批准（另单）。
6. **未接线要说在前面**（沿用 R401 那句）：判分器在 `app/quality/eval.py`（本单禁区），
   它算的 `answer_correctness` 仍按 105 分母出；86 是**账**与可跑子集夹具，不是现网分数。
7. §5.1 那六处文档抄本要跟着订正（尤其别把旧代 `2230b2b45be18bfb` 的 ✅ 再抄回 runbook）。
8. 若要落 `doc-17` 那枚甲：先重录 §4 点名的 6＋5 处硬编码（含 `scripts/r401_anchor_provenance.py:denominator()`
   的规则串），再跑 `scripts/r598_pending_jia.py --apply-to <副本路径>` 取全套数，**不许半落地**。

## 10. 写域账、验收件清单与未验格

### 10.1 本单动了什么（判脏凭 `git diff --numstat HEAD`，不用 `git status`）

| 文件 | 状态 | 行数 | 说明 |
|---|---|---|---|
| `docs/testing/fixtures/r97-shard-1.jsonl` | M | 9 | 从主件重派生（35 行不变） |
| `docs/testing/fixtures/r97-shard-2.jsonl` | M | 6 | 同上 |
| `docs/testing/fixtures/r97-shard-3.jsonl` | M | 14 | 同上 |
| `scripts/r598_shard_sync.py` | 新增 | — | 派生器／对账器（判据⑦派生腿） |
| `scripts/r598_disposition_ledger.py` | 新增 | — | 逐枚处置台账（零写死枚数） |
| `scripts/r598_pending_jia.py` | 新增 | — | 待授权甲案＋影子根试跑＋现算缺口对账 |
| `scripts/r598_out_of_domain_forensics.py` | 新增 | — | 域外硬编码实调取证（零写入） |
| `tests/test_r598_r97_shards_are_derived.py` | 新增 | **14 枚** | 三片逐字节钉＋6 把刀＋反向刀＋CLI 出口牙＋刀谱自己的牙 |
| `tests/test_r598_eval_ledger_invariants.py` | 新增 | 8 枚 | 台账不变式（关系而非数字） |
| `tests/test_r598_ledger_teeth.py` | 新增 | 10 枚 | 台账与待授权账的 10 把刀 |
| `docs/testing/r598-eval-retitling-2026-10-03.md` | 新增 | — | 本纸 |

**没动的（逐组点名，防"顺手"**：`tests/fixtures/business_evaluation_100.jsonl`（0 字节）、
`documents/**`（0 字节，未新增任何 txt ⇒ B 案未采纳）、`app/**` 全境（含判分器两枚文件）、
`data/**`、`migrations/**`、`docs/handoff/**`、`tests/_temp_edit_overlay.py`、
`scripts/check_eval_evidence_coverage.py`（派生能力已在，§1.4/1.5/1.7 一字未动）、
`scripts/r401_anchor_provenance.py`（**上一轮的改动已回退到基点**，见 §4.1）、
`frontend/**`，以及在飞四枚的写域（R591 / R60 / R597 / R596 列出的那些文件）。
🔴 判据⑤那两枚允许重录的守卫件 `tests/test_evaluation_report.py`、
`tests/test_r94_eval_evidence_coverage.py` **一字节未动**，理由：本单零改题落地，
覆盖度读数、丙案枚数、分母、语义口径分歧全部与基点相同（§1.1/§1.2/§1.3），三片在代码里零读者 ⇒
没有任何一格需要"为了让门绿"而重录。**守卫重录格数＝0**，这就是判据⑤「最小化」的下界。

🔴 四枚新量具的**写盘点已逐枚自审**（`Select-String write_bytes|write_text|mkdir|rmtree|copytree`）：
`--json` 目标（调用方给的路径）、影子根（系统临时目录，用完 `rmtree`）、`--apply-to` 副本（默认拒绝盘面）、
以及 `r598_shard_sync.py --write` 只写那三枚在册分片——**没有任何一条路径能写到题源、`documents/` 或 `app/`**。

### 10.2 本单跑过什么（全部 `-o addopts= -p no:cacheprovider --basetemp=$env:TEMP\r598* -q`）

| 跑的是什么 | 文件数 | 读数 |
|---|---|---|
| 本单三枚新件（含新补的 CLI 牙） | 3 | **32 passed**（14／8／10） |
| 评测族全清单：`test_evaluation_report`、`test_r94_*`、R401 三枚、`test_r438_*`、`test_r49_*`（3 枚）、`test_collect_evaluation_answers`、R123 三枚、`test_r126_*`、R454 三枚、`test_r570_*`、`test_r595_stall_cap` ＋ 本单三枚新件 | 22 | **356 passed / 0 failed / 4 skipped**（30.94 s，收工终版；此前一次 18 枚件窄口径为 300 passed，已被本行取代） |
| `business_evaluation_*` 读者全族（`tests/*.py` 逐枚 35 枚，含 `test_r437_*`、`test_r471_*`、R42 四枚、R520 两枚、R206 两枚、`test_observability_routes` 等） | 35 | 676 passed / **1 failed** / 4 skipped（63.2 s） |
| 卫生族定向（`test_r233`／`test_r238` 两枚／`test_r246`／`test_r253`／`test_r349`／`test_r376`／`test_r115`／`test_r357`／`test_r30`／`test_deployment_guards`） | 11 | 250 passed / **14 failed**（14 枚全在一枚件里，基点既有红，见 §10.2.1） |
| 全量回归门 `python scripts/run_gate.py` | 全仓 | 见 §10.5（本单亲跑，读数与门禁状态逐枚点名） |

那 1 枚 failed 与本单无关，一手定位：`test_r120_p3_collection_default.py::
test_every_repository_path_named_in_the_runbook_exists` 红在 `docs/testing/fixtures/r97-shard-`
这枚「不存在的路径」，来源是计划书 §8 第 557 行的带大括号引用（§5.1 末段），
根因笔是总控 10-03 14:22 那笔 runbook 作废（`e750d5c`），不是本单；本单未动那两枚文件，
也未动题源，改它要动的两枚都在禁区。**在本单写域外的既有红，本单不代修、也不掩盖。**

### 10.2.1 基点既有红（不是本单引入，逐枚点名，也不代修）

`tests/test_r238_bare_connect_ratchet.py` 整件 14 枚红。红话术逐字（本单亲跑）：

> 边界之外裸 connect 从 **15 枚涨到 17 枚**；多出来的是 `app/rag/retriever.py::_read_engagement_rows#0`
> → `app/rag/retriever.py:753`，`scripts/r579_index_crossover_readout.py::Db.open#0`
> → `scripts/r579_index_crossover_readout.py:460`

一手定位（都在基点 `b78ecd8` 的 blob 里，本单一个字节没碰这两枚文件）：

| 多出来的裸 connect | 引入笔 | 写域归谁 |
|---|---|---|
| `app/rag/retriever.py:753`（`with psycopg.connect(url) as connection`） | `245315b`（R46，10-03） | `retriever.py` 在册归 **R60**（在飞） |
| `scripts/r579_index_crossover_readout.py:460`（`psycopg.connect(self.url, autocommit=True, **kwargs)`） | `e6fdeb4`（R579，10-03） | `r579`/`r577` 在册归 **R597**（在飞） |

⇒ 这道 ratchet 抓的是**别人今天并的两笔树**，与本单无关；修法两选一（改走 `app/db/connection.py` 的边界，
或向总控申请入册），都在我禁区里。本单不代修、不掩盖，也不因为它给自己的件开后门。
同理 `test_r120_p3_collection_default.py` 那一枚（§5.1 末段）也是基点既有红。
🔴 因此「今天这棵树上门是绿的」这句话本单不能说：见 §10.5 的门读数。

### 10.3 总控验收要跑哪几枚件、预期多少枚

| 件 | 预期 |
|---|---|
| `tests/test_r598_r97_shards_are_derived.py` | **14 passed**（第 14 枚是 CLI 出口牙，见 §5） |
| `tests/test_r598_eval_ledger_invariants.py` | 8 passed |
| `tests/test_r598_ledger_teeth.py` | 10 passed |
| `tests/test_r401_unscorable_rows_are_named_not_dropped.py` ＋ `tests/test_r401_anchor_provenance_is_derived.py` ＋ `tests/test_r401_teeth.py` | 全绿（本单回退 r401 脚本后它们未受影响；今天实测 R401 三件 0 failed） |
| `tests/test_r94_eval_evidence_coverage.py` ＋ `tests/test_evaluation_report.py` | 全绿（两枚守卫未重录，读数与基点相同） |
| `python scripts/check_eval_evidence_coverage.py` | 19 / 19、指纹成立、rc=0 |
| `python scripts/r598_disposition_ledger.py` | rc=0；违规「无」；分母 105−19=86 |
| `python scripts/r598_shard_sync.py --check` | rc=0；三片与拼接全部「逐字节相等」 |
| `python scripts/r598_pending_jia.py --proof` | rc=0；影子根 19→18、分母 86→87、守恒漂移为空、三枚错答全不命中 |
| `python scripts/r598_out_of_domain_forensics.py` | rc=0；输出 6 枚「对照绿→实验红」清单（这是 §4 那句结论的复跑凭据） |
| `python scripts/run_gate.py` | 本树实测 **66 failed / 10327 passed / 56 skipped / 2 xfailed**；65 枚已在 §10.5 用纯基点拷贝逐枚证明为既有红，1 枚（`test_r570_...::test_an_existing_env_file_still_supplies_the_password`）单跑两棵树都绿。枚数以同一 HEAD 复跑数互比（不拿本纸历史数字当尺） |

### 10.4 未验的格子（如实列，不含糊）

* 全量回归门：**已跑完**，终数与逐枚归因见 §10.5（66 failed，其中 65 枚实测为基点既有红、1 枚为套件上下文假红）。🔴 「安静机上的全绿门」这一格仍**未验**，须总控复跑；本单没有绿票可交。
* 真模型跑分窗（105 题 correctness/evidence 的新窗读数）：本单禁打模型，**未验**；
  因本单零改题，历史窗仍代表同一集，下一扇窗的意义只在三片重派生之外，不新增可比性账。
* 生产 `department`/`classification` 与 HNSW 索引腿质量：与本单无关，计划书 §13 那四件判据的账不在这里。
* §4 那 6 枚域外断言的**修复**：只验了「它们会红」，没验「怎么改才对」——那要总控授权后由能动那两枚件的人裁。
* `tests/test_r401_anchor_provenance_is_derived.py` 里 2 枚函数无法在取证脚本里注入参数（`shadow` 等 fixture），
  实调时记为 skipped ⇒ 那 2 枚对甲落地的反应**未实测**（按源码读点它依赖 `r401.DETAILS`，会与 :249 同批红）。
* `scripts/r598_pending_jia.py --apply-to` 只验了「拒绝写仓库题源」那条闸，未真往第二枚路径落过一次盘（避开多余脏件）。

## 10.5 全量门（`python scripts/run_gate.py`）终数与逐枚归因

* 起跑 15:20:31／收工 15:48:01，本单亲跑；`run_gate.py` 这次**自选成串行**（命令行里没有 `-n`），用时 **1619.10 s**。
* 终数：**66 failed / 10327 passed / 56 skipped / 2 xfailed**（2582 warnings）。
* 🔴 所以「今天这棵树的门是绿的」这句话本单**不能说**；下面交的是「这 66 枚是不是本单引入」的**实测**答案，不是推断。

66 枚落在 13 枚文件里。对照办法：把 `b78ecd8` 的 tracked 内容导出成一枚**纯基点拷贝**（`git archive` ＋ python `tarfile`；无本单三片改动、无本单任何未跟踪件），同一批 13 枚件在那棵树上复跑，再取两集合差：

| 件（门里 FAILED 行数） | 本树门 | 纯基点拷贝 | 归因 |
|---|---|---|---|
| `tests/test_r346_line_ledger_is_derived_not_copied.py` | 23 | 23 | 在册「行号账＝派生投影」族，红在别人今天的树上 |
| `tests/test_r238_bare_connect_ratchet.py` | 14 | 14 | §10.2.1：`retriever.py:753`（归 R60）＋ `r579_index_crossover_readout.py:460`（归 R597）两笔裸 connect |
| `tests/test_r455_gapdoc_coordinates_are_derived.py` | 8 | 10 | 拷贝多出的 2 枚红在 `git show HEAD:...`（拷贝没有 `.git`）；本树那 8 枚逐枚同源 |
| `tests/test_r387_label_ruler_teeth.py` | 7 | 7 | 在册标签尺（R400 血缘行号族），与本单写域无关 |
| `tests/test_r455_hand_fudged_numbers_and_wrong_layers_both_redden.py` | 3 | 3 | 同 r455 族 |
| `tests/test_r469_readout_is_generated.py` | 2 | 2 | 「在册读数须由 CLI 生成」族，红在文档抄本漂移 |
| `tests/test_r483_empty_table_triage_is_derived.py` | 2 | 2 | 同上族 |
| `tests/test_r492_s93_column_matches_derived.py` | 2 | 2 | 同上族 |
| `tests/test_r120_p3_collection_default.py` | 1 | 1 | §5.1 末段／§10.2 末段：计划书第 557 行的大括号引用被截成 `docs/testing/fixtures/r97-shard-`（根因笔＝总控 `e750d5c`） |
| `tests/test_r256_dataset_version_scope.py` | 1 | 1 | 数据集版本账族，本单未动 `data/**` |
| `tests/test_r389_r382_connects_go_through_the_boundary.py` | 1 | 1 | R382 边界账族，随 r238 那两笔一起红 |
| `tests/test_r400_derived_ledger_shift_and_silence_pins.py` | 1 | 1 | R400 派生账族 |
| `tests/test_r570_window_shard_driver.py` | 1 | 0 | 🔴 唯一没被对照证实的一枚，见下段 |

* 集合差实测：**只在门里红＝0 枚**、只在拷贝里红＝29 枚。29 枚拆成两笔取证产物：r455 那 2 枚是拷贝缺 `.git`；r570 那 27 枚是**我自己把 `--basetemp` 落在了拷贝树内部**，触发驱动「产物不许落仓内」守卫——把 basetemp 挪出拷贝树后该件 **35 passed / 0 failed**。
  ⇒ 上表 13 行里 12 行（合计 65 枚）是**基点既有红**，id 级对齐，不是本单引入。
* 剩下那 1 枚如实挂账：`tests/test_r570_window_shard_driver.py::test_an_existing_env_file_still_supplies_the_password`
  在**两棵树里单跑都绿**（本树 35 passed、纯基点拷贝 35 passed），只在整扇门里红 ⇒ 本单判为**套件上下文假红**（同机多枚在飞＋全量顺序所致）。
  🔴 但本单不拿它冒充「已用对照证明的基点既有红」。该件也不读本单写域：对 `r97-shard|business_evaluation_100|check_eval_evidence_coverage|r401_anchor_provenance|r598_` 的 grep 命中数＝0。
* 本单写域（题源一字节未动 ＋ 三片重派生）在这 66 枚里的占比：**0**。
* 三组定向数与门**同时**跑在同一台不安静的机器上：评测族 22 枚件 **356 passed / 0 failed / 4 skipped**、读者族 35 枚件 676 passed / 1 failed、卫生族 11 枚件 250 passed / 14 failed。
* 要真收掉「门绿」这一格只剩一个办法：**在安静的机器上复跑同名门**，并与看板最新绿票的同一 HEAD 读数互比（AGENTS.md：枚数随每笔并树变，别拿历史数字当尺）。
  本单交的是上面的逐枚归因，加一句：那 65 枚的账归各单，本单不代修、不掩盖，也不因为它们给自己的件开后门。

## 11. 复跑命令（逐条可直接贴；解释器用主树 venv，只读）

```powershell
$PY = "C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe"
$W  = "C:\Users\fengx\PycharmProjects\be-r598"
Set-Location $W
& $PY -X utf8 scripts/check_eval_evidence_coverage.py                 # 19 / 19，rc=0
& $PY -X utf8 scripts/check_eval_evidence_coverage.py --include-csv     # CSV 假想账：仍 19
& $PY -X utf8 scripts/r598_shard_sync.py --check                       # rc=0（改前 rc=1）
& $PY -X utf8 scripts/r598_disposition_ledger.py                       # 逐枚处置 + 分母
& $PY -X utf8 scripts/r598_pending_jia.py --proof --workdir $env:TEMP\r598probe
& $PY -X utf8 scripts/r598_out_of_domain_forensics.py                  # 6 枚「对照绿→实验红」
& $PY -X utf8 -m pytest tests/test_r598_r97_shards_are_derived.py tests/test_r598_eval_ledger_invariants.py tests/test_r598_ledger_teeth.py -o addopts= -p no:cacheprovider --basetemp=$env:TEMP\r598 -q   # 32 passed
& $PY -X utf8 scripts/run_gate.py                                      # 全量门（-n 自选）

# 基点既有红的对照（§10.5 用的取证法；两处坑已点名）
$T = Join-Path $env:TEMP "eb598_probe"
New-Item -ItemType Directory -Path $T -Force | Out-Null
git archive -o (Join-Path $T "base.tar") b78ecd8
& $PY -X utf8 -c "import tarfile,os;tarfile.open(os.path.join(r'$T','base.tar')).extractall(os.path.join(r'$T','base'))"
# 🔴 不要用 tar.exe：它把这批中文文件名解坏（32 篇 documents/*.txt 直接损失）
# 🔴 --basetemp 必须落在拷贝树之外，否则 r570 整件被「产物不许落仓内」守卫拒掉（本单踩过）
Push-Location (Join-Path $T "base")
& $PY -X utf8 -m pytest tests/test_r570_window_shard_driver.py -o addopts= -p no:cacheprovider --basetemp="$T\bt" -q   # 35 passed
Pop-Location
```

判分器与覆盖度件之间没有第三把尺：本单的三枚新件全部复用 `app/quality/eval.py:_is_correct`
与 `scripts/check_eval_evidence_coverage.py` 那两把在册尺子，未复刻平行实现（AGENTS.md 跨 Agent 协作条）。