# R645 · 契约纯追加钉换成「具名差异账」（2026-10-04，执行层·树 be-r645@2d2680b）

## 一句话

`tests/test_r354_delete_audit_shares_the_owner_reader.py` 里那两枚「当前契约必须以基点那一份为逐字节前缀」的常驻钉，
今天改成读一本**具名差异账**：默认仍然逐字节不许动，动过的每一格必须逐字登记在册，且账只收「手抄坐标 → 运行时派生锚」
那一形状；今天账上恰好一枚（R630 那一格）。治法不是撤销 R630，也不是把尺的基点前移。

## 病与凭据（本席现取，不复测）

- 破坏前缀的那一笔是 `497ac38`（并树 R630／执行层 Pasteur）：它把契约 blockers 表里 `first_token_not_a_stage_sample`
  那一整行的两枚手抄行号换成了 `文件::符号` 派生锚。那一格改得对 —— 对外契约里烤死过期坐标，正是本仓这两天在治的病。
- 改前（干净检出 @2d2680b，15 枚同名件）＝ **6 failed / 284 passed / 1 xfailed**，其中两枚红就是这两枚钉。旧钉的红句
  把「从第几个字节起与基点不同」写进句子里 —— 那正是本单要灭的手抄偏移量形状。
- 主树与本树现取 `git status --porcelain docs/api/contract-v1.md` 都为空：红是账上的真红，不是施工期脏态；
  现盘那一份与 `HEAD` 那一份逐字相等。
- 先例（重要）：`tests/test_r397_read_legs_refuse_a_missing_table.py` 的同名钉在 2026-09-28 已被总控改口过一次，
  理由与今天同源 —— 「契约里的过期文字要改口，改口必然动中段字节」。那一次把判据换成了「基点的每枚节标题仍在场、
  相对顺序不变」，也就是**把字节级的钉子换成了结构级的钉子，强度降了**。本单不走那条路：字节级不变式整体保住，
  改写只在账上留名。

## 治法（工单判据 → 落点）

| 判据 | 落点 |
| --- | --- |
| ① 账外逐字节不许动，新内容只许长在文末 | `audit_history()` 用「基点 ＋ 账上登记的逐字替换」拼出历史应当长成的那一份，现盘必须以它为前缀；追加段还须非空（咬「什么都没写」） |
| ② 账只收一种形状，今天恰好一枚 | `shape_violations()`：旧文里必含点 py 冒号紧跟数字的手抄坐标；新文里一枚都不许留（连不带文件名的裸行号那一形也不许），且必含 `文件::符号` 派生锚。枚数另有 `EXPECTED_DIFFERENCES_TODAY = 1` 的门，多一枚少一枚都红 |
| ③ 不许把字节偏移量抄进钉 | `Difference` 的字段面里根本没有位置那一格（ticket／old／new／reason 四格全是字符串），位置一律由 `_occurrences()` 从 `git show` 与盘上现读派生；另由 `test_the_nail_files_copy_no_byte_offsets` 反向扫两枚件：既不许有五位以上的裸数字，也不许让今天派生出来的任何位置或行号以字面量形态活着 |
| ④ 两枚钉同判据 | 两枚钉都只走 `_contract_history_account()` → `assert_history_matches_ledger()`；`test_the_two_r354_nails_read_this_same_book` 沿 AST 现查每枚钉的可达面：不许再碰 `BASE`／`CONTRACT`／`subprocess`／自家 `_git`／`_normalize_eol`／`_first_difference`，不许出现 `show` 或契约相对路径这类字面量，不许对文本变量做 `startswith`（自家前缀等式），且必须能走到共用入口。刀① 还额外断言两枚钉的红句逐字相同 |
| ⑤ 四把刀＋正控，不许 skip／xfail／豁免名单 | 见下一节；另 `test_the_ledger_ships_no_skip_or_exemption_list` 现查两枚件：无 skip／xfail 家族的调用与装饰器，且枚数那一格只许写等号（`<`／`<=`／`>`／`>=` 一律红） |
| ⑥ 改前改后对照表 | 见下面那张表，两态亲跑 |
| ⑦ 只治这两枚钉 | 写域只有三处（文末）；`docs/api/contract-v1.md` 一字节未动，追加成一节来绕开前缀判定更没有做 |

账上那一枚：`R630_FIRST_TOKEN_ROW` —— 旧文是基点 blockers 表里那一整行（逐字，含行尾），新文是现盘那一整行（逐字）。
两串都由本席从 `git show a7ac040:docs/api/contract-v1.md` 与盘上现读取回后原样录入，立案号 R630。

## 四把刀（每把先跑正控；盘上契约全程只读）

| 刀 | 做法 | 必红的句子 |
| --- | --- | --- |
| ① 账外手改一个标点 | 影子端把历史区某句里的一个字母换掉 | 「契约的历史在差异账之外被动过」＋现读的字符位、行号、以及映射回基点的字符位；两枚钉都红且红句逐字相同 |
| ② 塞一枚形状不合的登记 | 影子端真把一句结论换掉，并把它登记进账（枚数门一起放到两枚） | 「这形状不收：旧文里一枚手抄坐标都没有」；同时断言红句里**不许**出现「在差异账之外被动过」「枚数不对」——保证这一刀是形状尺咬住的，不是别的判据撞巧 |
| ③ 前移尺的基点 | 把 `FROZEN_BASE` 换成较新的一版（本刀直接用 `HEAD`，不抄 sha） | 两枚钉都红：「旧文在基点里命中 0 处……要么尺的基点被前移过 —— 后者是灭红，不是改账」。另有常驻字面量钉 `_literal_pin_problems()`，本刀拿改过的源码文本反证它咬得动；并当场演示「前移基点＋清空账＋枚数门归零」三条腿一起才真能绕过尺 —— 所以那两枚字面量是尺的一部分 |
| ④ 半截派生 | 把登记的新文改回「仍然留着一枚手抄坐标」那一形（数字从旧文里现取，不新抄） | 形状尺：「新文里还留着 N 枚手抄坐标（半截派生，那一格明年照样过期）」；两枚钉：「登记的新文在现盘上命中 0 处」 |

正控：`test_the_disk_state_is_green_with_exactly_one_named_difference` 现跑现盘 —— 必须绿，且 `len(records) == EXPECTED_DIFFERENCES_TODAY == 1`，立案名逐枚点名；
`test_the_ledger_holds_exactly_one_difference_today` 还从反方向撑这一格：把账撑到两枚（合成一枚同样合格形状的登记）必报「账上登记 2 枚，今天应当恰好 1 枚」，把账清空必报「账上登记 0 枚……」。

刀全部只拿 `tmp_path` 下的影子副本判：`_shadow_copy()` 读盘上契约 → 内存里改 → 按盘上原行尾写回 `tmp_path`，每把刀进出各取一次盘上契约的 sha256 并断言相等。
**不开 overlay 窗**，所以不牵动 `tests/test_r466_mutation_does_not_leak_into_live_module.py` 与 `tests/test_r583_window_inventory.py` 那两本名册（都在本单写域外）。

## 对照表（同名件逐枚；两态亲跑）

state①＝本树 apply 未 commit；state②＝干净检出 @2d2680b ＋ 只投本单两枚件。

| 件 | collected | 改前 passed／failed | state① passed／failed | state② passed／failed |
| --- | --- | --- | --- | --- |
| tests/test_r253_no_test_rewrites_a_tracked_file.py | 9 | 9／0 | 9／0 | 9／0 |
| tests/test_r302_docs_utf8_guard.py | 8 | 8／0 | 8／0 | 8／0 |
| tests/test_r337_owner_receipt_on_both_exits.py | 12 | 12／0 | 12／0 | 12／0 |
| tests/test_r353_degradation_note_caps_reason_classes.py | 26 | 26／0 | 26／0 | 26／0 |
| tests/test_r354_delete_audit_shares_the_owner_reader.py | 18 | 16／**2** | 18／**0** | 18／**0** |
| tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py | 24 | 23／1 | 23／1 | 23／1 |
| tests/test_r373_the_two_remaining_legs_answer_absence.py | 39 | 38／1 | 38／1 | 38／1 |
| tests/test_r388_read_leg_answers_absence.py | 56 | 54／1（另 1 枚 strict xfail） | 54／1（同） | 54／1（同） |
| tests/test_r414_b_terminal_data_filename.py | 12 | 11／1 | 11／1 | 11／1 |
| tests/test_r466_mutation_does_not_leak_into_live_module.py | 20 | 20／0 | 20／0 | 20／0 |
| tests/test_r523_cached_count_lands.py | 13 | 13／0 | 13／0 | 13／0 |
| tests/test_r545_counter_evidence_teeth.py | 24 | 24／0 | 24／0 | 24／0 |
| tests/test_r583_window_inventory.py | 4 | 4／0 | 4／0 | 4／0 |
| tests/test_r630_counter_evidence_teeth.py | 13 | 13／0 | 13／0 | 13／0 |
| tests/test_r635_counter_evidence_teeth.py | 13 | 13／0 | 13／0 | 13／0 |
| tests/test_r645_contract_difference_ledger.py（本单新增） | 15 | 件不存在 | 15／0 | 15／0 |
| **合计** | 291 → 306 | **284／6／1 xfailed** | **301／4／1 xfailed** | **301／4／1 xfailed** |
| 用时 | — | 173.77 s | 169.95 s | 168.14 s |

读法：两枚钉从红转绿（18／0），新件 15 枚全绿，**其余十三枚件逐枚一枚没变**；剩下的 4 枚红是本单写域外的同族前缀钉（下一节），改前改后同数。
两态 passed 枚数相同（301），失败清单逐枚相同（r366／r373／r388／r414_b 各一枚）。

## 新件里的常驻牙（15 枚，逐枚一句话）

- `test_the_disk_state_is_green_with_exactly_one_named_difference` · 正控：现盘绿，且恰好一枚具名差异。
- `test_the_derived_positions_match_the_verbatim_ledger_text` · 派生位置上的那一段与登记的逐文字一模一样，前后各 200 字符的上下文两侧不许被一起拖走。
- `test_the_difference_record_carries_no_position_field` · 结构防线：`Difference` 没有位置字段，四个字段全是字符串。
- `test_the_ledger_entries_are_the_accepted_shape` · 账上每一枚都逐枚过形状尺。
- `test_the_frozen_base_is_pinned_by_literal_and_lands_in_history` · 基点与枚数门是字面量，且 `a7ac040` 真在这条历史线上。
- `test_the_registered_difference_is_committed_not_a_dirty_fluke` · 那一格在提交里（新文在 `HEAD` 那版恰一处、旧文零处），并现查是哪几笔动过它 —— 读 git 对象，不读「此刻工作树脏不脏」。
- `test_the_ledger_holds_exactly_one_difference_today` · 枚数门双向：撑到两枚、清到零枚都要红，且红句点名「枚数不对」。
- `test_the_two_r354_nails_read_this_same_book` · 判据④ 的 AST 钉（见上表）。
- `test_the_ledger_module_is_a_single_object_under_both_names` · 顶层名与 `tests.` 点名必须是同一个模块对象：否则刀架在这一份、钉读那一副看不见 ＝ 假绿。
- `test_the_nail_files_copy_no_byte_offsets` · 反手抄位置钉（判据③ 的反向扫描）。
- `test_the_ledger_ships_no_skip_or_exemption_list` · 无 skip／xfail／阈值化枚数。
- 四把刀 `test_counter_evidence_1..4_*` · 见上节。

## 同族账（本单写域外，一字未动）

今天仍红的另外六枚「逐字节前缀」钉，同源同病，各自冻的基点（现读）：

- `tests/test_r340_replayable_alerts_open.py::test_the_contract_appends_one_section_and_deletes_nothing` — 基点 `e9aac2f`
- `tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py::` 同名片段 — 基点 `b291324`
- `tests/test_r367_gate_shape_pins.py::` 同名片段 — 基点 `b291324`
- `tests/test_r373_the_two_remaining_legs_answer_absence.py::` 同名片段 — 基点 `796540e`
- `tests/test_r388_read_leg_answers_absence.py::` 同名片段 — 基点 `b498c88`
- `tests/test_r414_b_terminal_data_filename.py::test_the_registration_is_a_tail_append_over_the_base` — 基点 `c0c4bcd`，且这枚把基点写在函数体内部的字面量里

建议另立一单把这六枚接到同一本账上（尺已现成：`assert_history_matches_ledger()`，各件只需交回自己那一格的逐字登记）。
两处顺手记档：`tests/test_r397_read_legs_refuse_a_missing_table.py` 那枚 09-28 已被改口成结构级判据、今天绿，但它的注释里抄进过一处字符位置；
`tests/test_r523_cached_count_lands.py::contract_is_pure_append` 比的是 `HEAD` 那版与现盘，不冻旧基点 ⇒ 今天绿，本单不动它。

## 环境与纪律自证

- 零容器、零连库、零打模型、不起服务、不改 env、不动 powercfg；**没起全量门**（本机有别的席在跑），只跑同名件。
- 跑测试一律 `C:\Users\fengx\PycharmProjects\be-r645\.venv\Scripts\python.exe -m pytest -p no:randomly -q`。
- 写域只有三处：`tests/test_r354_delete_audit_shares_the_owner_reader.py`（两枚钉＋私有 helper＋模块 docstring 判据⑦ 那三行）、
  新 `tests/test_r645_contract_difference_ledger.py`、本 doc。禁区一字未动；未 commit、未建分支、未 push。
- state② 的「干净检出」是用 `git worktree add --detach %TEMP%\r645_state2 2d2680b` 做的，**不是** `git archive` 解包，原因记档：
  archive 出来的那棵树里没有 `.git`，而本族同名件全靠 `git show <基点>:<文件>` 取历史那一版 —— 实测当场 20 枚假红
  （`fatal: not a git repository`），另外 `tar -x` 解中文文件名还会报 `Invalid empty pathname`。同一棵树先跑改前（15 枚件）、
  再把本单两枚件投进去复跑（16 枚件），两态只差这两枚件。那枚临时 worktree 留在 %TEMP% 供复现，总控可 `git worktree remove` 处置。
- 本 doc 里不写「点 py 冒号跟数字」那一形的手抄坐标，也不写任何字节／字符偏移量。

## 交付盘面（收席那一刻现取，2026-10-04 22:5x）

- `git rev-parse --short HEAD` = **2d2680b**（本席基点，未动）
- `git status --porcelain` = 三行：`M tests/test_r354_delete_audit_shares_the_owner_reader.py`、
  `?? tests/test_r645_contract_difference_ledger.py`、`?? docs/testing/r645-contract-difference-ledger-2026-10-04.md`
- `git diff --numstat HEAD` = 只有一枚件：`39  39  tests/test_r354_delete_audit_shares_the_owner_reader.py`
- `git ls-files --others --exclude-standard` = 上面那两枚新件（货全在盘上，未打包、未挪出仓）
- `git rev-list --count 2d2680b..HEAD` = **0**（未 commit、未建分支、未 push，并树由总控代做）
- 禁区自证：`git status --porcelain docs/api/contract-v1.md` 为空，盘上字节数 503,243 与开工时现取的读数相同；
  `git diff --name-only HEAD` 只点名 `tests/test_r354_delete_audit_shares_the_owner_reader.py` 一枚。
- 终态复跑（本树，同名 5 枚件）：**72 passed in 26.26 s** —— r354 18 枚、新件 15 枚、r630 牙 13 枚、r635 牙 13 枚、r523 13 枚。