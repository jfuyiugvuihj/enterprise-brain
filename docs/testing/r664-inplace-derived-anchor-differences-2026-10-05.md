# R664 · 两枚在册不变式互斥：`r645` 刀③ 的 escape 集被 R657 归零 —— 裁甲案，差异账旁边立一本「改口账」（2026-10-05，执行层）

## 一句话

`tests/test_r645_contract_difference_ledger.py` 那本具名差异账原来只收**一种**形状（手抄坐标 → `文件::符号` 派生锚），
而 `tests/test_r526_slot_caliber_closure.py::test_the_contract_row_and_the_module_are_the_same_words` 把契约 §4b 那一格与
码面那一枚字段**逐字对判**，强制它只能**原地**改口。R657（并树 `dfc75f0`）依令原地替换之后，「现盘是最近某版契约的纯追加」
不再成立 ⇒ 刀③ 交回的 escape 集变空。这不是 R657 的码错，也不是再登记一笔差异能解决 —— 是两枚在册不变式互斥。
本单按总控裁的**甲案**把尺扩成两本账：差异账（原样不动）＋ **改口账**（新那一类：派生锚行的原地改口），三条硬条件都落在尺上；
四把旧刀一把没摘，另加两把（新刀 A、新刀 B）。契约本体一字节未动。

## 病形（总控亲跑现取，本席在同一棵树上复现）

| 读数 | 值（本席现取） |
| --- | --- |
| 开工基点 `git rev-parse --short HEAD` | `1af37c5`（与派工词那句对账逐字相等） |
| 干净检出 @`1af37c5` 十三枚同名件 | **1 failed / 312 passed / 1 xfailed**（21.63 s）；红的只有 `::test_counter_evidence_3_moving_the_frozen_base_forward_reddens`，红句 `assert escapes` ⇒ `assert []` |
| 现盘那一份与 `HEAD` 那一份 | 逐字相等（`git show HEAD:` 与工作树 blob 同一枚），追加段一字节未动 ⇒ 红是账上的真红，不是施工期脏态 |
| 归零的机理 | 见下一节三枚现取字符位 |

## 机理（逐枚现取，不采信转述）

差异账的尺只做两件事：把「基点 ＋ 账上登记」拼出来，要求现盘以它为**前缀**；剩下的那一截只许长在文末。
刀③ 要证的后门是：把尺的基点前移 ＋ 清空差异账 ＋ 把差异枚数门归零，这扇后门**真的走得通** —— 走法是在最近 8 枚动过契约
的版本里现找一版，使现盘是它的纯追加。今天这几枚读数是它为什么找不到：

- 冻结基点那一版：232665 字符；「基点 ＋ 差异账一枚登记」拼出来的历史前缀：233224 字符；现盘：450017 字符；
  按改口账退回历史态之后：449865 字符。
- R630 那一格（差异账在册）：基点第 112001..112253 字符（第 1723 行，旧文 252 字）→ 现盘第 112001..112812 字符（新文 811 字）。
- R657 那一格（本单新立，改口账在册）：现盘第 426267..427383 字符（第 5877 行，新文 1116 字）→ 历史态到第 427231 字符收尾
  （旧文 964 字）；两侧逐字相等的前缀 852 字 / 后缀 3 字。那一格在 42 万字符处，**远在冻结基点那一版（23 万）之外**，
  所以它压根不在差异账管的「历史区」里 —— 这一点与 R657 自己那张纸的取证一致。
- 于是：`b1a4760`／`497ac38`／`d1118af` 三版都带着**旧** §4b 那一行，而现盘带的是**新**那一行 ⇒ 没有一版是现盘的前缀，
  escape 集空，刀③ 空转 ⇒ 红。本单改造之后同一枚扫描交回 **3 枚 GREEN 候选**（`d1118af`／`b1a4760`／`497ac38`），
  而「两本账一起清」那一条腿交回 **0 枚**（见第五节刀③）。

## 裁定：甲案（总控已定），以及禁路四条

扩的是**账的形状**，不是任何一枚码：本单未动 `app/**`、未动契约本体、未动 `test_r526_slot_caliber_closure.py` 的逐字对判。
四条禁路一条没碰 —— 没撤销 R657 的代码面；没把 r526 的原地要求改成「另起新节」；没把尺的冻结基点前移（`FROZEN_BASE`
仍是那枚字面量，另有常驻钉）；没给刀③ 加 `xfail`（`test_the_ledger_ships_no_skip_or_exemption_list` 现查：本件里
skip／xfail／importorskip 家族零枚，枚数那一格只许写等号）。

## 治法：差异账 ＋ 改口账（工单判据 → 落点）

| 判据 | 落点（`tests/test_r645_contract_difference_ledger.py`） |
| --- | --- |
| ① 逐字点名那一格的差异区间，前缀／后缀必须等值 | `Reword`（`ticket`／`old`／`new`／`reason`／`evidence` 五格全字符串，字段面里**没有位置**那一格，与 `Difference` 同律）；`reword_shape_violations()` 要求两半各是一整行表格行、行首格子名两侧相等（`ROW_NODE`）、一半不许是另一半的开头；`apply_rewords()` 把位置全派生（新文在现盘上唯一命中才是它的位置），`RewordMark` 现交出前缀／后缀逐字等值的长度；`test_the_reword_positions_are_derived_and_the_neighbourhood_is_byte_equal` 再取前后各 200 字符逐字对判 —— 改口不许把邻格一起拖走 |
| ② 改口必须在账面有出处（点名单号 ＋ 凭据纸） | `reword_provenance_problems()`：立案号须是单号那一形（`TICKET_SHAPE`），凭据纸须在 `docs/testing/` 下真实存在且纸里点得出这一单与这一格的格子名；`derive_reword_pair()` 是这本账的**生成件**：拿登记的两半回 git 现校（新文只能改变恰好一版的发生次数，旧行取自那一版的上一版），`test_the_registered_reword_lands_in_a_commit_and_derives_from_it` 把它钉成常驻牙，并验落地那一版与上一版都在 `HEAD` 这条历史线上 |
| ③ 账外一字节仍当场红 | 尺改两段：`audit_history()` 先 `apply_rewords()` 把现盘退回历史态，再拿「基点 ＋ 差异账」比前缀（老句子一字未改，刀① 的红句断言原样）；新增 `committed_appendage_problems()` —— 退回原形（两本账都退）必须仍是**最近那一版在册契约的同一原形 ＋ 文末追加**，否则红句点名「不许就地消失」；两本账的分工按冻结基点划线（旧文若在基点里命中 ⇒ 「它属于差异账」当场红） |
| ④ 今天账上恰好一枚 | 差异账 `EXPECTED_DIFFERENCES_TODAY = 1`（未动）＋ 改口账 `EXPECTED_REWORDS_TODAY = 1`（新枚数门，多一枚少一枚都红）；`_literal_pin_problems()` 由两枚字面量扩到**三枚**（基点 ＋ 两枚门），刀③ 当场演示三枚各自挪走都咬得动 |
| ⑤ 四把旧刀不许摘 | 刀①／刀②／刀④ 的判据一字未改；刀③ 的断言也未改（红句、枚数、`_literal_pin_problems` 三枚反证全留），只补了一条「两本账一起清反而走不通」的新腿。判据件由 15 枚扩到 24 枚：新增 7 枚常驻正控（改口账的账本身、形状与出处、位置派生与邻格等值、两本账不写同一格、落地在提交、枚数门）＋ 2 把新刀 |

账上那一枚改口：`R657_FIRST_TEXT_ROW` —— 旧行取自 `dfc75f0` 那一版的上一版（即 `d1118af`）§4b 名册里 `qa.first_text_p95_ms`
那一整行，新行取自 `dfc75f0` 那一版的同一行，两半逐字（含行尾），立案 R657，凭据纸 `docs/testing/r657-caliber-prerequisite-2026-10-05.md`。
登记文本由本席用生成件同形的取法落笔（从 `git show dfc75f0 -- docs/api/contract-v1.md` 的 diff 里现取那一删一加两行），
未手抄任何字符位、行号或版本号；常驻牙 `test_the_registered_reword_lands_in_a_commit_and_derives_from_it` 每天现校逐字相等。

## 六把反证刀（每把先跑正控；全部只拿内存副本与 `tmp_path` 影子端判，盘上契约一字节不动）

| 刀 | 做法 | 必红的句子（本席现取） |
| --- | --- | --- |
| ① 账外手改历史区一个标点 | 影子端把 `**on the wire**` 换掉 | 「契约的历史在差异账之外被动过」＋派生的字符位、行号、映射回基点的字符位；两枚钉红句逐字相同（原样，一字未改） |
| ② 塞一枚形状不合的差异 | 影子端把一句结论换掉并登记进差异账 | 「这形状不收：旧文里一枚手抄坐标都没有」，且红句里不许出现「在差异账之外被动过」「枚数不对」（原样） |
| ③ 前移尺的基点 | `FROZEN_BASE` 换成 `HEAD`；再叠「清空差异账 ＋ 差异枚数门归零」 | 两枚钉各报「命中 0 处……基点被前移过」；escape 扫描现交回 3 枚走得通的候选 ⇒ 字面量钉不是空转；**新增第二条腿**：两本账一起清 ⇒ 候选集为 0（追加段那条腿还盯着）；三枚字面量各自挪走都被 `_literal_pin_problems()` 报回 |
| ④ 半截派生 | 把登记的新文改回仍留一枚手抄坐标 | 「半截派生」＋两枚钉「登记的新文在现盘上命中 0 处」（原样） |
| A 无出处的原地改口（新） | 影子端把 §4b 那一行里的 `app/api/v1/observability.py::wire_first_text_readout` 原地换成另一枚在册符号，改口账一格不登记 | 「不许就地消失」＋那一格自己的派生行号；并断言红句里**不许**出现「在差异账之外被动过」（那一格在追加段，前缀尺本来就管不到它 —— 这一刀只能由新腿咬）。第二条腿：登记了但凭据纸不存在 ⇒「没有出处：凭据纸不存在」；立案号空 ⇒「必须在账面点名单号」 |
| B 把改口伪装成纯追加（新） | 账面侧：拿「旧行 ＋ 一行空行」当改口登记；盘上侧：改口做了、账不登记、文末再补一行空行撑长度 | 账面侧「这形状不收：……文末追加伪装成改口」；盘上侧「不许就地消失」且红句里不许出现「没长东西」（正控现证：只补一行空行、账不动 ⇒ 尺全绿且长度腿确实被撑过了 —— 蒙混骗得过长度腿，骗不过追加段那一腿） |

## 三态读数（同名件逐枚；本席亲跑，非执行层自报）

十三枚同名件的**清单**三态逐枚相同；枚数只在判据件那一枚上差 9 枚（本单新增 7 枚正控 ＋ 2 把新刀）：

| 件 | 基点 @`1af37c5` | state①（apply 未 commit，主树） | state②（`1af37c5` 干净检出 ＋ 只投本单两枚件） |
| --- | --- | --- | --- |
| tests/test_r645_contract_difference_ledger.py | 15 | 24 | 24 |
| tests/test_r354_delete_audit_shares_the_owner_reader.py | 18 | 18 | 18 |
| tests/test_r340_replayable_alerts_open.py | 47 | 47 | 47 |
| tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py | 24 | 24 | 24 |
| tests/test_r367_gate_shape_pins.py | 23 | 23 | 23 |
| tests/test_r373_the_two_remaining_legs_answer_absence.py | 39 | 39 | 39 |
| tests/test_r388_read_leg_answers_absence.py | 56 | 56 | 56 |
| tests/test_r414_b_terminal_data_filename.py | 12 | 12 | 12 |
| tests/test_r523_cached_count_lands.py | 13 | 13 | 13 |
| tests/test_r523_counter_evidence_teeth.py | 9 | 9 | 9 |
| tests/test_r526_slot_caliber_closure.py | 19 | 19 | 19 |
| tests/test_r526_counter_evidence_teeth.py | 21 | 21 | 21 |
| tests/test_r653_six_nails_read_the_same_book.py | 18 | 18 | 18 |
| 合计 | 314 枚（312 passed／1 failed／1 xfailed） | 323 枚（322 passed／0 failed／1 xfailed） | 323 枚（322 passed／0 failed／1 xfailed） |

- 基点跑那一枚红逐字同名：`::test_counter_evidence_3_moving_the_frozen_base_forward_reddens`。
- state② 的干净树取法与本单写域内的取证同律：`git clone --shared` 到临时目录再 `checkout --detach 1af37c5`。
  🔴 派工词点名的 `git archive <基点>` 那份导出**没有 `.git`**，而这一族钉全都要 `git -C <树> show <rev>:docs/api/contract-v1.md`
  取两侧原文（尺的两侧一律读 git 对象而不是工作树副本，这是 R645 立下的），纯导出会让整族当场报错而不是复跑；
  故本席改用同内容的干净克隆，**未在主树里 commit、未建分支**。
- 全量门未跑（本单禁区），未起服务、未动容器、未打模型；`-p no:randomly` 只为让三态的失败清单可比。



## 复跑（本席在飞的三笔他人并树落地之后 @`b5b67b5`，本席现取）

- 开工基点 `1af37c5` 之后主树又落下三笔（`798dbdf` R660 并树、`58e084c` 与 `b5b67b5` 两笔第十七班账）——本席未参与，
  且这三笔**一字节未动** `docs/api/contract-v1.md`（现取 `git log -1 --format=%h -- docs/api/contract-v1.md` 仍是 `dfc75f0`）
  ⇒ 尺读的那本契约与在册那一枚改口都没有搬家；上一节的读数按原样留着不改史，本节只补同一批件在新盘面上的复跑。
- 同名件由十三枚扩到**十四枚**：补进 `tests/test_r367_dashboard_refuses_a_store_that_is_not_there.py`（与 gate-shape 那枚同族，
  同样读这一本账）。三态的**清单逐枚相同**，枚数只在判据件那一枚上差 9 枚（15 → 24）。

| 件 | 干净检出 @`b5b67b5`（零本单件） | state①（主树 apply 未 commit） | state②（`b5b67b5` 干净检出＋只投本单两枚件） |
| --- | --- | --- | --- |
| tests/test_r645_contract_difference_ledger.py | 15 | 24 | 24 |
| tests/test_r340_replayable_alerts_open.py | 47 | 47 | 47 |
| tests/test_r354_delete_audit_shares_the_owner_reader.py | 18 | 18 | 18 |
| tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py | 24 | 24 | 24 |
| tests/test_r367_dashboard_refuses_a_store_that_is_not_there.py | 29 | 29 | 29 |
| tests/test_r367_gate_shape_pins.py | 23 | 23 | 23 |
| tests/test_r373_the_two_remaining_legs_answer_absence.py | 39 | 39 | 39 |
| tests/test_r388_read_leg_answers_absence.py | 56 | 56 | 56 |
| tests/test_r414_b_terminal_data_filename.py | 12 | 12 | 12 |
| tests/test_r523_cached_count_lands.py | 13 | 13 | 13 |
| tests/test_r523_counter_evidence_teeth.py | 9 | 9 | 9 |
| tests/test_r526_counter_evidence_teeth.py | 21 | 21 | 21 |
| tests/test_r526_slot_caliber_closure.py | 19 | 19 | 19 |
| tests/test_r653_six_nails_read_the_same_book.py | 18 | 18 | 18 |
| 合计 | 343 枚（341 passed／**1 failed**／1 xfailed） | 352 枚（351 passed／0 failed／1 xfailed） | 352 枚（351 passed／0 failed／1 xfailed） |

- 病形在新盘面上**一比一复现**：干净检出零本单件，红的只有 `::test_counter_evidence_3_moving_the_frozen_base_forward_reddens`，
  红句仍是 `assert escapes` 交回空集。
- 刀③ 的候选扫描同一棵树现取：窗内 8 枚 = `dfc75f0`／`d1118af`／`b1a4760`／`497ac38`／`5477645`／`b2d82a0`／`81784da`／`efc5c50`；
  只清差异账 ⇒ escape 交回 `d1118af`／`b1a4760`／`497ac38` 三枚（字面量钉不空转）；两本账一起清 ⇒ **0 枚**（本单新那条腿咬得住）。
  字符位现取：冻结基点 232665／现盘 450017／按改口账退回 449865／再按差异账退回 449306。
- 🔴 顺带取证一枚**非本单造成**的既有红：`tests/test_r638_pointer_ratchet.py` 三枚＋`tests/test_r302_docs_utf8_guard.py` 一枚，
  在 `b5b67b5` 的干净检出（零本单件）里逐枚同名复现。根因在别人的账上：`798dbdf` 把 `docs/testing/r483-empty-tables-2026-09-29.md`
  的重锚坐标改了盘面，而 r638 那本存量基线没跟着记账（现读 77 对 记账 75）；第十七班往跟进单追加正文后，r302 的控制符记账（12）与现盘不符。
  这两本账（r638 的基线件、`docs/handoff/**`）都在本单禁区，本席一字未动，只把读数交给承接的单。
- 格式：本树 venv 里没有 `ruff`（现取 `No module named ruff`），本席未自行安装；判据件与本纸的行尾与控制符复扫仍为纯 CRLF、
  `0x00`／`0x07`／`0x08`／`0x0b`／`0x0c` 零枚、无 BOM、全篇零枚手抄行号坐标。

## 一条腿被本单自己的新刀抓出来（设计迭代，如实记）

追加段那条腿第一版写成「退回原形必须是最近某几版契约里**任意一版**的纯追加」。新刀 A 第一跑就把它打穿：
一枚**旧而短**的版本（`5477645`，44 万字符）会白让追加段里那处账外改口过关 —— 因为篡改点落在它长度之外，
「纯追加」按定义成立。第二版改成只认**最近那一版**在册契约（`committee_revision()` 现取 `dfc75f0`，版本号不抄进账），
并把两本账同时退回后再比 —— 新刀 A、新刀 B 双双转红为绿，正控（只补一行空行）仍全绿。这一条就是本单为什么
必须带两把新刀：光有正控，这条腿会一直假绿。

## 残留与限度（不许写成「永远抓住」）

- **差异账那一侧的量程没变**：历史区由冻结基点永久盯着，账外一字节在任何一版上都红。
- **追加段那一侧的量程是「每次现跑」**：未登记的原地改口在并树之前必红（每一次跑尺都量）；一旦它被**并进 `HEAD`**
  而账面始终没登记，这一条腿的对照面就跟着搬新家，不再点名那一笔 —— 那时撞它的是别的在册钉（`test_r526_slot_caliber_closure.py`
  的逐字对判、`test_r523_cached_count_lands.py` 拿 `HEAD` 比现盘那枚），不是这一条。这是本单换掉「任意一版」那条腿之后
  仍然存在的真实限度，写在纸上是留给下一班的账，不是本单没做完的活。
- 刀③ 的候选扫描窗仍是「最近 8 枚动过契约的提交」，本单没放宽它。今天交回 3 枚候选；若有一天文末追加断了档
  （最近 8 枚全是原地改口），这枚刀会再红一次 —— 那一次的读数是「后门走不通了，字面量钉在空转」，处置是取证而不是改尺。
- §4b 那一格「家族 B 交接表」里那句旧话仍按 R657 的记录留在原地（本单写域外）。

## 写域自查

改动只有两处：`tests/test_r645_contract_difference_ledger.py`（判据件本体，含它自己的账本生成件 `derive_reword_pair()`）
与本纸。禁区一字未动：`docs/api/contract-v1.md` 现取 `git diff --numstat` 为空、工作树与 `HEAD` 同一枚 sha；
`app/**`、`frontend/**`、评测夹具、`docs/handoff/**`、`scripts/run_gate.py`、`pyproject.toml`、`deploy/.env.server`、
`chroma_db/**` 零枚触及；未 commit、未建分支、未 push、未起服务、未动容器、未 rebuild 镜像、未打真模型、未跑全量门。
本纸与判据件同律：坐标一律 `文件::符号`，全篇零枚 `*.py` 冒号紧跟数字；写完现读扫 `0x00`／`0x07`／`0x08`／`0x0b`／`0x0c` 枚数＝ 0，
行尾纯 CRLF（与主树在册行尾一致），无 BOM。

## 下一班怎么再登记一枚原地改口（生成件口径，不必手抄整行）

1. 那一格必须**已经在册为派生锚行**（旧行里就有 `文件::符号`），且它不在冻结基点的历史区里（旧文在基点里命中 0 处）——
   否则它属于差异账那一类，走 R630 那条形状，不走这本账。
2. 拿 `Reword(ticket=单号, old=旧整行, new=新整行, reason=为什么收它, evidence="docs/testing/<这一单的凭据纸>")` 入账，
   两半逐字含行尾；`CONTRACT_REWORDS` 与 `EXPECTED_REWORDS_TODAY` 一起加一枚（枚数门是等号，不许松成阈值）。
3. 跑 `derive_reword_pair()` 同形的取法核对：新文只能改变恰好一版契约的发生次数，旧行取自那一版的上一版，逐字与登记相等。
4. 两把新刀不许摘：无出处（单号或凭据纸拿不出）与伪装成追加（补空行）各红一次，才叫这一格登记得有价值。
