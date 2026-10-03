# R597 · 散文不许替台账抄答案：裁定词表只许有一处定义

🔴 **本格只收账面与实际不一致，不改任何产品行为。**

- 工单：R597（由 R593 并树 `03507f3` 时如实上报的四处过期散文另立）
- 执行层：R597 席（本席）· 工作树 `C:\Users\fengx\PycharmProjects\be-r597` · 基点 `03507f3`（建树 dirty=0）
- 交付态：零 commit、零 push、零建分支；`app/**` 只改一枚注释行
- 真源（唯一）：`scripts/r483_empty_tables_triage.py` 的 `VERDICTS`（词表）与 `TRIAGE`（逐格裁定），对外由它的 `--json` 交回
- 新钉：`tests/test_r597_verdict_vocabulary_has_one_source.py`（11 枚）

## 一、这一单的病，与它和 R593 的分工

R483 的空表裁定原来只有三个词，每一词都额外断言「此刻这枚表一行没有」。R593 用现读把这病定性成
「把此刻读数当常驻不变量」，加了第四词，并把三格重定性。**词表变四词之后，全仓还有四处散文按旧三词
说话**——它们手抄的是「那一格叫什么」和「那张台账第几行」，两样都不是它们该 own 的事实。

R593 那席点名了四处、一字未动（都在它写域之外）。本单收这四处。分工线画得很直：
R593 治真源（加词、改判、把钉改成两面派生），R597 治**引用真源的散文**。

判据落点：**把散文里手抄的词与结论，改成从真源派生或指向真源。** 一把量「不许手抄词表」的尺如果自己
抄了一份词表，它就是本单要拦的形状——本单现场复现过一次（见 §五 的自咬）。

## 二、① 四处逐一点名（现行号由符号现取，改前/改后逐字对照）

派工词给的行号本席逐枚现取核过：在基点 `03507f3` 上**一枚都没漂**，但落纸仍按符号定位（同一棵树一天能漂 150 行）。

### 处 1 · `app/rag/retrieval_pipeline.py:1053`（产品码，只许改注释、一行为限）

- 改前（基点现取原文一句）：

  ```
  # docs/testing/r483-empty-tables-2026-09-29.md:104 —— no_seed_path 不是合法为空，是欠码；
  ```

- 改后（同一行，仍是注释，行数 1229 → 1229）：

  ```
  # scripts/r483_empty_tables_triage.py::TRIAGE["retrieval_traces"]（裁定词唯一真源，现取用它的 --json；「永远 0 行」是 09-30 陈述）；
  ```

- 这一行同时改掉两处过期：手抄的裁定词、手抄给再生件的行号（`…2026-09-29.md` 第 104 行今天是一枚空行，那一节现居 `:103`，标题里的裁定已改判）。
- 那一处散文的区域＝包住锚语「产品问答道的检索留痕（R536）」的整段注释（现居 `:1047`；区域由锚语现取，行号只是本次读数的注脚，不是判据）。
- 上一行「⇒ `retrieval_traces` 永远 0 行」落在 `:1051`（属「症状（09-30 凭据）」那一段），一行为限改不到它——本单用新注释把它明确标成**历史陈述**，并在 §八 登记为未翻绿的格子。

### 处 2 · `scripts/r577_demo_sample_seed.py:170` 与 `:181`（同一枚闸的散文与拒收消息）

- 改前 `:170`：`这一枚是反证②的牙：needs_owner 那一格真正要拦的是「拿一行无归属的告警冒充闭环」。`
- 改后（函数 `attributed_alerts` 的文档串，函数定义在 `:204`、文档串现居 `:205-210`）：三行，改成按**表名**指那一格 + 声明词一律走把手现取。
- 改前 `:181`：`"拿它走闭环等于把 needs_owner 那一格判绿 —— 拒收，不是放宽")`
- 改后（函数 `require_attributed_alerts`，函数定义在 `:214`、那句拒收消息现居 `:218-221`）：

  ```
  "拿它走闭环等于把 " + GUARDED_TABLE + " 那一格判绿"
  "（该格今天的裁定＝" + guarded_verdict() + "）—— 拒收，不是放宽")
  ```

- 新增把手（`scripts/r577_demo_sample_seed.py:188`）：`guarded_verdict()` —— 现取 `TRIAGE[那一格]["verdict"]`，并核它仍在 `VERDICTS` 里；**取不到就抛，绝不回落成手抄词**。
- 拒收语义零变化：判据、分支、`MIN_ALERTS` 下界、抛出的异常类型（`ValueError`）、退出码契约一字未动；变的只有那句解释里的「那一格叫什么」的出处。

### 处 3 · `tests/test_r577_demo_sample_seed.py:431`（在册钉的文档串）

- 改前：`"""``alerts.department`` 为空的行就是「无归属」：拿它冒充闭环＝把 needs_owner 判绿（反证②正控）。"""`
- 改后：文档串改口 + 在册断言**只加不减**（现居 `:447`）。逐字对照见 §三。

### 处 4 · `tests/test_r536_retrieval_completed_on_product_lane.py:5` 与 `tests/test_r536_single_emission_point.py:16`

- 改前（lane 件 `:5`）：`⇒ ``retrieval_traces`` 永远 0 行（裁定原文 ``docs/testing/r483-empty-tables-2026-09-29.md:104``）。`
- 改后：五行，把「永远 0 行」写成 09-30 的历史陈述，坐标改成 `scripts/r483_empty_tables_triage.py::TRIAGE["retrieval_traces"]`，并写明「再生件行号会漂，本文件不引行号」。
- 改前（single 件 `:16`）：`（口径出处 ``docs/testing/r483-empty-tables-2026-09-29.md:104``）。`
- 改后：坐标改成 `…::TRIAGE["retrieval_traces"]["debug_only_surface"]`（即「调试面不算产品道」那条豁免的真源那一格），同样不引行号。
- 🔴 本席核过（与 R593 §七同一判据）：两枚件都不读那张再生件的内容，旧引用是**散文指针**不是断言，所以改掉它不牵动任何在册读数。

## 三、② 在册断言：一枚都没放宽

- 没有任何 `==` / `assertIn` 被换成包含式；没有加 `skip` / `xfail`；定长名单没改成「至少 N」。
- 在册件里唯一动过的断言是 `tests/test_r577_demo_sample_seed.py::test_unattributed_alert_rows_are_refused`，**连名带断言改口**（按 R593／R582 先例），逐字如下：
  - 改前（全部）：

    ```
    with pytest.raises(ValueError) as refused:
        seed.require_attributed_alerts(rows)
    assert "无归属" in str(refused.value)
    ```

  - 改后（前两行逐字未动，后面四枚是新增）：

    ```
    with pytest.raises(ValueError) as refused:
        seed.require_attributed_alerts(rows)
    assert "无归属" in str(refused.value)

    message = str(refused.value)
    verdict = str(TRIAGE.TRIAGE[seed.GUARDED_TABLE]["verdict"])
    assert verdict in TRIAGE.VERDICTS, (verdict, TRIAGE.VERDICTS)
    assert seed.GUARDED_TABLE + " 那一格判绿" in message, message
    assert "今天的裁定＝" + verdict in message, message
    ```

- 函数名未改（它不含裁定词，改了会牵动 `tests/test_r577_counter_evidence_teeth.py` 的 `PINS` 名册）。
- 反证 K2（摘掉归属过滤）打的那枚钉正是这一枚：刀下它仍变哑——`tests/test_r577_counter_evidence_teeth.py` 五把在交付态全绿（§七）。
- 其余三枚在册族（`tests/test_r536_*.py` 三件、`tests/test_r483_*.py`、`tests/test_r550_*.py`）本单一枚未改、未放宽。

## 四、③ 新钉：词表只有一处定义（全仓扫描读数）

尺子住在 `tests/test_r597_verdict_vocabulary_has_one_source.py`。**它自己一枚裁定词都不拼**：词表
（`WORDS`）、词的数量（`len(WORDS)`）、词的形状（首段/末段）全部从真源现取。

| 钉 | 咬什么 |
|---|---|
| `test_the_product_tree_and_the_gate_name_no_verdict_word` | `app/**` 与那把闸件的源码里出现任何一枚裁定词 ⇒ 红 |
| `test_every_named_prose_spot_points_at_the_true_source` | ① 四处散文（按符号取区域）：不含词、不引再生件行号、必须指向真源或把手 |
| `test_no_source_file_hands_out_its_own_word_list` | 同一行／同一枚字符串字面量／同一枚容器里拼 ≥2 枚不同的词 ⇒ 红 |
| `test_only_the_true_source_defines_the_vocabulary` | 全仓把 ≥2 枚词写成字面量容器的文件只许有真源；真源散文那句词表计数必须等于 `len(VERDICTS)` |
| `test_a_file_may_mention_the_words_only_by_pointing_at_the_true_source` | `app/**` 零提及；`scripts/**` 除真源零提及；`tests/**` 提及者必须指名真源 |
| `test_no_word_of_the_verdict_shape_is_outside_the_true_vocabulary` | 不许第五个自造词（形状从词表派生）；射程自检不许空转 |
| `test_no_source_file_cites_a_line_of_the_generated_ledger` | 代码层不许写「那张台账第几行」 |
| `test_the_gate_reaches_the_word_only_through_its_handle` | 结构钉：那把闸碰 `TRIAGE`/`VERDICTS` 的函数只许 `guarded_verdict` 一枚，且调用点只许在 `require_attributed_alerts` 里一枚 |
| `test_a_shadow_that_hands_out_its_own_word_list_is_the_only_one_named` | 反证④第一把（常驻） |
| `test_dropping_a_word_from_the_true_source_blinds_every_reference` | 反证④第二把（常驻） |
| `test_the_paper_declares_the_header_and_names_every_spot` | ⑤ 本纸：抬头那句在场、① 逐枚点名、四层读数点名 |

扫描读数（交付态 `words_by_layer()` 现取；`mentions` = 四枚词的提及枚数）：

- `app/**`：**零枚文件、零枚提及**（处 1 改掉之后）
- `scripts/**`：`scripts/r483_empty_tables_triage.py` 46 枚（真源本身）——除它零枚
- `tests/**`：`tests/test_r483_empty_table_triage_is_derived.py` 6 枚、`tests/test_r550_counter_evidence_teeth.py` 7 枚、`tests/test_r550_event_hop_climb_is_generic.py` 2 枚；三枚**全部指向真源**，且没有一枚拼词表清单
- `docs/**`：`docs/testing/r483-empty-tables-2026-09-29.md` 28 枚（真源的再生件）、`docs/testing/r593-verdict-must-follow-rows-2026-10-03.md` 20 枚、`docs/testing/r550-event-hop-climb-2026-09-30.md` 14 枚、`docs/handoff/2026-09-30-v2-gap-recheck-3.md` 9 枚、`docs/handoff/2026-09-15-orchestration-board.md` 5 枚、`docs/handoff/2026-09-15-backend-followup-requests.md` 4 枚、`docs/testing/r536-retrieval-trace-emission-2026-09-30.md` 4 枚、`docs/handoff/2026-09-29-v2-gap-recheck-3.md` 3 枚、`docs/testing/r577-demo-sample-2026-10-03.md` 1 枚、本纸（逐字对照必引原文）
- 🔴 docs 层本单**只点名不出红**：纸面要留改前原文做逐字对照，把「引用旧坐标」判成罪证会直接毁掉判据② 的对照表；两枚不指向真源的 docs（`docs/handoff/2026-09-30-v2-gap-recheck-3.md`、`docs/testing/r577-demo-sample-2026-10-03.md`）在总控写域，本席一字未动 → 见 §八

## 五、④ 反证两把（sha256 前 12，三枚一轮，还原逐字节全等）

### 刀一 · 往散文里塞回手抄词表（物理落盘面：本单写域内那枚注释行）

把 `app/rag/retrieval_pipeline.py:1053` 那一行整枚换成「`…2026-09-29.md`:104 —— 词表只有 三词」
的手抄旧散文，跑交付态全集（6 件 70 枚），随后原字节还原：

| 段 | sha256 前 12 |
|---|---|
| 摘前（交付态） | `34ac4fd6113e` |
| 摘后 | `236b27e9f06f` |
| 还原 | `34ac4fd6113e`（`byte_equal_restored_to_before = true`，逐字节全等） |

刀下读数：`6 failed, 64 passed in 118.31 s`（rc=1）。六枚红**逐枚点名，全在**
`tests/test_r597_verdict_vocabulary_has_one_source.py` 之内——**在册族 64 枚零红**：

- `test_the_product_tree_and_the_gate_name_no_verdict_word`
- `test_every_named_prose_spot_points_at_the_true_source`
- `test_no_source_file_hands_out_its_own_word_list`
- `test_a_file_may_mention_the_words_only_by_pointing_at_the_true_source`
- `test_no_source_file_cites_a_line_of_the_generated_ledger`
- `test_a_shadow_that_hands_out_its_own_word_list_is_the_only_one_named`

🔴 最后一枚在刀下必红的原因如实记：它的**影子端正控**拿「未变异的副本」当基准，而此刻盘面原件已被
塞回手抄词表——刀占了基准，不是尺漏咬；同一把刀的常驻形态（影子端自证）见 §八 之外另述。

还原后同选集复跑：`70 passed in 213.06 s`（rc=0）。同机多枚在飞，绝对时长不可比，**枚数才是判据**。

### 刀二 · 把真源里那一枚在册词删掉（物理落 `%TEMP%` 影子副本：真源在禁域，一字节未动）

| 段 | sha256 前 12 |
|---|---|
| 摘前（影子副本＝真源交付态） | `3c13154d008f` |
| 摘后（`VERDICTS` 去掉那一格在册的那枚词） | `6320c53dbdf7` |
| 还原 | `3c13154d008f`（逐字节全等；**盘面真源全程恒为 `3c13154d008f`**） |

刀下读数：`guarded_verdict()` 当场抛（消息点名 `r483_empty_tables_triage.py` 与「不在它自己的词表」）；
把在册钉 `test_unattributed_alert_rows_are_refused` 指到刀下那把闸上跑 ⇒ `RuntimeError` 逃出
`pytest.raises(ValueError)`，**引用处一起红**；未变异的影子端同一枚钉跑通（正控）。
这一把同时常驻在 `test_dropping_a_word_from_the_true_source_blinds_every_reference` 里——上面那串 sha
与这枚钉在 pytest 内的自证是同一次动作的两种取法。
🔴 引用不是摆设：删词之后没有任何一处能靠手抄把消息拼回去，把手 fail-closed，宁可那句拒收发不出去。

### 本席被自己的尺咬过一次（如实记，不遮）

新钉第一版在**它自己的注释里**写了「两段的词（`legitimately_empty`／`needs_owner`）」，
`test_no_source_file_hands_out_its_own_word_list` 当场把
`tests/test_r597_verdict_vocabulary_has_one_source.py:66` 点名。改法：那句话改成按段数指代，不再拼词。
量「不许手抄词表」的尺自己抄了一份词表，正是本单要拦的形状——这一枚红是尺对，不是人错。

## 六、「产品行为零变化」的凭据

- `app/rag/retrieval_pipeline.py`：改前改后 `ast.dump` 逐字相等（sha256 前 12 双枚同为 `c6626a11b403`）、
  行数 1229 → 1229、差异行数 = 1、且那一行改前改后都是注释（`all_comments = True`）。判定分支零改动。
- `scripts/r577_demo_sample_seed.py`：新增的是取词把手与散文；`require_attributed_alerts` 的分支、
  `MIN_ALERTS` 下界、异常类型与退出码契约未动，`attributed_alerts` 那一行（`tests/test_r577_counter_evidence_teeth.py`
  K2 的锚点）逐字未动 ⇒ 五把锚点仍现取唯一。
- 同一组在册钉改前改后同数（§七）。

## 七、复跑（全部标「执行层自报」，总控须自行复跑才算验收）

解释器 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`；单跑一律
`-o addopts= -p no:cacheprovider --basetemp=… -q`；🔴 禁跑全量门 `scripts/run_gate.py`——本单**没跑**它。
选集（下称「全集」）＝新钉 11 枚 + `tests/test_r536_single_emission_point.py` 7 枚 +
`tests/test_r536_counter_evidence_teeth.py` 8 枚 + `tests/test_r536_retrieval_completed_on_product_lane.py` 11 枚 +
`tests/test_r577_demo_sample_seed.py` 26 枚 + `tests/test_r577_counter_evidence_teeth.py` 7 枚 ＝ **70 枚**。

| # | 命令要点 | rc | 读数 |
|---|---|---|---|
| 1 | 改前基线（基点 `03507f3`，未改动态，四枚在册件） | 0 | **52 passed** in 19.06 s |
| 2 | 中间态：`test_r577_demo_sample_seed.py` + `test_r577_counter_evidence_teeth.py` | 0 | 33 passed in 0.86 s |
| 3 | 新钉单跑（本纸尚未落盘） | 1 | 10 passed / **1 failed**——红的正是纸面那枚，登记不遮 |
| 4 | 交付态全集（六件） | 0 | **70 passed** in 91.18 s |
| 5 | 刀一下（同全集） | 1 | 6 failed / 64 passed in 118.31 s（六枚全在新钉，见 §五） |
| 6 | 刀一还原后（同全集） | 0 | **70 passed** in 213.06 s |
| 7 | 邻族（本单未改，吃同一枚真源）：`test_r483_empty_table_triage_is_derived.py` +
|   | `test_r550_event_hop_climb_is_generic.py` + `test_r550_counter_evidence_teeth.py` + | 1 | **104 passed / 1 failed**（唯一那枚红由本单造成，§八 第一格） |
|   | `test_r498_landing_shape_is_not_a_mention.py` |  | 389.24 s |
| 8 | 另三枚扫 `app/**` 源码文本的在册件（`test_r78_unearned_claims.py`／`test_r115_doc_content_limit_is_single_source.py`／`test_r563_live_module_callables_do_not_leak.py`） | 0 | 33 passed in 10.13 s |
| 9 | 产品码 AST 对账：`git show 03507f3:app/rag/retrieval_pipeline.py` vs 盘面 | 0 | `ast_equal=True`，`ast_sha` 双枚同 `c6626a11b403`，差异行数 1，`all_comments=True`，1229→1229 |
| 10 | 取证：同一把 r483 尺在基点副本 vs 本树（`--check`，离线） | 0 / 4 | 基点 `git archive` 副本 **PASS problems=0**；本树 **FAIL 逐字节不符**（两枚现扫数被本单散文推走，§八 第一格） |
| 11 | 本纸落盘后再跑全集（定稿读数） | 0 | **70 passed** in 31.76 s |

🔴 改前 #1 的 52 枚＝r536 三件 26 枚 + `tests/test_r577_demo_sample_seed.py` 26 枚；改后同一批在册件在 #4/#6/#11 里
逐枚同数（外加新钉 11 枚与 r577 刀件 7 枚＝70）——产品行为零变化的凭据是「同数 + AST 逐字相等」，不是「跑过了」。

## 七之二、续席复跑（同名件、同选集、同一把尺；全部标「执行层自报」）

第二遍由本单续席现场重取。判据按同一 HEAD 的枚数互比，绝对时长受同机争用支配，不作判据。

| # | 选集（沿用 §七 的行号） | rc | 本席复跑读数 |
|---|---|---|---|
| 1 | 改前基线：四枚在册件跑在 `03507f3` 的 `git archive` 副本上（零写动态） | 0 | **52 passed** in 23.56 s |
| 4/6/11 | 交付态全集（六件 70 枚） | 0 | **70 passed** in 31.95 s |
| 5 | 刀一下（手抄词表物理落盘面注释行，同全集） | 1 | **6 failed / 64 passed** in 47.96 s——六枚逐枚点名仍全在 `tests/test_r597_verdict_vocabulary_has_one_source.py`，在册族 64 枚零红 |
| 6 | 刀一还原后（同全集） | 0 | **70 passed** in 39.24 s |
| 7 | 邻族四件（`test_r483_empty_table_triage_is_derived.py`／`test_r550_*` 两件／`test_r498_landing_shape_is_not_a_mention.py`） | 1 | **1 failed / 104 passed** in 365.60 s——红的仍是 `test_the_in_tree_document_is_the_regenerated_one_byte_for_byte`，差异逐字读回「现扫到 13 行 → 14 行、3 枚文件不变」（§八 第 0 格） |
| 8 | 另三枚扫 `app/**` 源码文本的在册件 | 0 | **33 passed** in 7.98 s |
| 9 | 产品码 AST 对账（驱动器落 `%TEMP%`，只读） | 0 | `ast_equal=True`、`ast_sha` 双枚同 `c6626a11b403`、`all_comments=True`、1229 → 1229、unified diff 交出 `-`/`+` 各一枚（`git diff --numstat`＝1/1） |
| 10 | 同一把 r483 尺 `--check`：本树 / 基点副本 | 4 / 0 | 本树 **FAIL 逐字节不符**；基点 `git archive` 副本 **PASS problems=0** |

刀一（物理落盘面那枚注释行）的 sha 轮次由本席重新交出，与 §五 逐枚同数：摘前 `34ac4fd6113e` → 摘后 `236b27e9f06f` → 还原 `34ac4fd6113e`，`byte_equal_restored_to_before = true`。刀下六枚红的名字逐枚对过 §五 那份名单，一枚不多一枚不少。

刀二（影子端 `%TEMP%`，真源禁域一字节未动）也在同一遍里重新交出：摘前 `3c13154d008f` → 摘后 `6320c53dbdf7` → 还原 `3c13154d008f`，`byte_equal = true`；被删的那枚词现取为 `no_longer_empty`（＝那把闸守的 `alert_rules` 今天的裁定），刀下 `guarded_verdict()` 抛 `RuntimeError`、在册钉 `test_unattributed_alert_rows_are_refused` 跟着红。盘面真源刀前刀后各读一次恒为 `3c13154d008f`，一字节未动（禁域自证）。

🔴 顺手登记一枚会咬人的形状：**影子端那一把刀一**（只在 `%TEMP%` 副本上塞手抄词表）交出的是 `848cfc9a4f82`，与 §五 盘面那把的 `236b27e9f06f` 不同——差别只在线结束符（影子端 `write_text(..., newline="")` 把 CRLF 折成 LF），不是第二种改法。§五 的判据取盘面那把，影子那把是它的常驻形态；两枚 sha 都写在这里，是不让下席拿「sha 对不上」当新病立案。

🔴 **取数通道的一枚坑（本席现场踩过，如实记）**：用不落 `USERNAME` 的通道（`child_process.spawn` 一类）起这枚解释器时，`getpass.getuser()` 回落到 posix 的 `pwd`（Windows 无此模块）⇒ `torch._dynamo` 半死重入，报 `AssertionError: Artifact of type=precompile already registered`，凡 `import app.rag.retrieval_pipeline` 的在册件在**收集阶段**就红。本席先在基点 `git archive` 副本上跑到同一枚红，一度按「环境损坏」立案；现读 `sys.path` 里没有第二枚 torch、site-packages 无当日装包痕迹，改走带 `USERNAME` 的 PowerShell 解释器路径后同一选集当场绿——**这是取数通道的病，不是仓库的病，更不是本单改动造成的**。落纸记这一条是因为它的形状与本单同族：读数对不上时先证尺与量法，再谈账面。

## 八、没验的格子（逐枚点名，不遮）

0. 🔴 **本单把 r483 台账的现扫读数推走了两格**——唯一一枚由本单造成的在册红，写在最前面：
   - 红在 `tests/test_r483_empty_table_triage_is_derived.py::test_the_in_tree_document_is_the_regenerated_one_byte_for_byte`；
   - 归因**已取证**：同一把尺在基点 `03507f3` 的 `git archive` 副本上 `--check` rc=0（problems=0），
     在本树 rc=4 ⇒ 这枚红是本单引起的，不是 R593 留下的过期账，本席不推给别人；
   - 逐字差异只有两行（两份渲染件 299 行对 299 行，diff 8 行；数字为现取而非推理：
     `SourceIndex.references()` 对 `docs/testing/r483-empty-tables-2026-09-29.md` 里那两句原文逐格比，
     同一次读数里 `alerts` 150 行/18 枚、`user_profiles` 20 行/6 枚**未动**）：
     `alert_rules` 那格「表名在 app/ 与 scripts/ 里现扫到 **13 行 → 14 行**（3 枚文件不变）」，
     `retrieval_traces` 那格「**21 行 → 22 行**（9 枚文件不变）」；
   - 来源逐枚点名：`scripts/r577_demo_sample_seed.py:172` 新增 `GUARDED_TABLE = "alert_rules"`；
     `app/rag/retrieval_pipeline.py:1053` 新注释按表名指那一格。两处都是**判据① 要求的坐标**，
     改成别的说法就不再指向真源，本席不为躲红把引用改虚；
   - 本单**没有**重跑 `--sync`：那枚文档在禁域（R593 写域），硬规矩④又写明被 `--sync` 再生的文档不许顺手提交
     （它要现读库）。正解＝总控并树之后按 R593 §八同一口径跑一次 `python scripts/r483_empty_tables_triage.py --sync`——
     那是这枚钉设计好的出路，不是新缺陷（跟进单 §157 已记同一口径）；
   - 顺手证了本单自己的论点：现扫数真的会漂，所以「那张台账第几行」根本不该被散文引用。
1. `app/rag/retrieval_pipeline.py:1051` 那句「⇒ `retrieval_traces` 永远 0 行」——一行为限改不到它，
   本单只在新注释里把它标成 09-30 的历史陈述。要改到字面需要产品码里第二枚注释行，超出本单授权。
2. PG 现读：本单**没有**为翻任何判据去读库；今日行数只在真源的 `--json`／`--sync` 读数里，那是 R593/总控的活。
3. 全量门未跑（派工令禁跑）；新钉与在册族的绝对时长受同机争用支配，纸里只按枚数互比。
4. docs 层两枚不指向真源的散文（`docs/handoff/2026-09-30-v2-gap-recheck-3.md`、
   `docs/testing/r577-demo-sample-2026-10-03.md`）在总控写域：本单只点名、不出红、未动。
5. 「第五个自造词」那把尺的射程只覆盖三段及以上的词形状；词表里两段的词落在射程外（理由钉在尺的注释里：
   `no_owner` 在别处是合法在册词组，把它判成裁定词就是「用一把量不到的尺宣布达标」）。
   本席现取了放宽到两段的代价：同一把形状尺一放开中间段，代码层当场交出 **4 枚**射程外命中——`tests/test_r492_live_claim_boundary.py:132/133/134` 三枚与本钉自己 `:67` 那一枚，全是那枚两段的合法词组；「射程只到三段及以上」不是偷懒，是不拿这 4 枚误报当罪证的代价换来的。
6. 反证刀一的常驻形态里，「影子端正控」与「盘面已被塞词表」不能同真——刀在盘面时那一枚必红，
   纸里已单独点名；不在盘面时（交付态）该枚跑通。

## 九、交付盘面（零 commit：`git -C be-r597 diff --numstat HEAD` + 未跟踪原文）

```
1	1	app/rag/retrieval_pipeline.py
42	2	scripts/r577_demo_sample_seed.py
5	2	tests/test_r536_retrieval_completed_on_product_lane.py
2	1	tests/test_r536_single_emission_point.py
31	1	tests/test_r577_demo_sample_seed.py

?? docs/testing/r597-prose-must-derive-from-the-verdict-source-2026-10-03.md
?? tests/test_r597_verdict_vocabulary_has_one_source.py
```

字节账（`.py` 一律 CRLF 单形、无 BOM、无裸 CR——CR=LF=CRLF 三计数相等；本纸 LF 单形、CR=0）：
「行数」按 `text.split("\n")` 计（末段为空串），故它比真行枚数（＝CR 计数）大一；两列并列写出，不靠人猜。

| 件 | sha256 前 12 | 字节 | 行数 | 三计数 | BOM |
|---|---|---:|---:|---|---|
| `app/rag/retrieval_pipeline.py` | `34ac4fd6113e` | 63920 | 1229 | CR=LF=CRLF=1228 | 无 |
| `scripts/r577_demo_sample_seed.py` | `58cc5fa9e013` | 34553 | 622 | CR=LF=CRLF=621 | 无 |
| `tests/test_r536_retrieval_completed_on_product_lane.py` | `aa427a0d3411` | 24643 | 510 | CR=LF=CRLF=509 | 无 |
| `tests/test_r536_single_emission_point.py` | `416f415247a1` | 8548 | 193 | CR=LF=CRLF=192 | 无 |
| `tests/test_r577_demo_sample_seed.py` | `c8850233ab68` | 31896 | 666 | CR=LF=CRLF=665 | 无 |
| `tests/test_r597_verdict_vocabulary_has_one_source.py`（新） | `8d48ecd98719` | 23207 | 447 | CR=LF=CRLF=446 | 无 |
| 本纸（新） | 见回执（自指 sha 由交回时现取） | — | — | LF 单形，CR=0 | 无 |

禁域自证（本单全程只读）：`scripts/r483_empty_tables_triage.py` 恒为 `3c13154d008f`／97612 字节，
`docs/handoff/**` 零写入，`migrations/**`、评测集、`chroma_db/**`、`frontend/**`、`deploy/.env.server`、
`app/api/v1/chat.py`、`app/rag/retriever.py` 一字节未动；主树 `C:\Users\fengx\PycharmProjects\企业智脑` 未碰。