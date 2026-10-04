# R653 · 剩下六枚「契约逐字节前缀」钉接到 R645 那一本具名差异账上（2026-10-04）

> 执行层席位：R653／树 `be-r653`@基点 `28d1ea4`。上游＝`docs/testing/r645-contract-difference-ledger-2026-10-04.md`（那一单把 r354 的两枚钉换成薄壳，并把剩下的六枚逐枚点了名）。

## 一、病与凭据（总控现跑，非转述）

`497ac38`（并树 R630）把契约 blockers 表里 `first_token_not_a_stage_sample` 那一行的两枚手抄行号换成了运行时派生锚（`app/trace/spans.py::ExecutionSpan.mark_first_token` 那一族符号名）。那一格改得对 —— 对外契约里烤死过期坐标正是本仓这两天在治的病。错的是「当前契约必须以某一版基点为逐字节前缀」这一族常驻钉：八枚同尺里，R645 治了两枚，**今天仍红六枚**（28d1ea4 上亲跑＝6 failed / 315 passed / 1 xfailed / 145.80 s；干净树复跑同名同数＝148.41 s）。

六枚各自冻的基点（本席现读）与各自那把尺：

| 件::钉 | 自家基点 | 自家把手 | 改后 |
| --- | --- | --- | --- |
| `tests/test_r340_replayable_alerts_open.py::test_the_contract_appends_one_section_and_deletes_nothing` | `e9aac2f` | `_base_file`（`git show`）＋ `CONTRACT` ＋ `startswith` | 薄壳读共用入口；`_base_file` 留给判据庚的零新增错误码那一枚（非契约），原样在 |
| `tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py::test_the_contract_appends_one_section_and_deletes_nothing` | `b291324` | `_git_show` ＋ `BASE` ＋ `startswith` | 薄壳读共用入口；`_git_show`、`BASE`、`import subprocess` 随本单退役（本件再无第二把尺） |
| `tests/test_r367_gate_shape_pins.py::test_the_contract_appends_one_section_and_deletes_nothing` | `b291324` | `_base_file` ＋ `_source(CONTRACT)` ＋ `startswith` | 薄壳读共用入口；`_base_file`／`BASE` 留给判据 3 那枚「探针在基点上就存在」，原样在 |
| `tests/test_r373_the_two_remaining_legs_answer_absence.py::test_the_contract_appends_one_section_and_deletes_nothing` | `796540e` | `_git_show` ＋ `BASE` ＋ `startswith` | 同 r366：把手与锚点退役 |
| `tests/test_r388_read_leg_answers_absence.py::test_the_contract_appends_one_section_and_deletes_nothing` | `b498c88` | `_git_show` ＋ `BASE` ＋ `startswith` | 同 r366：把手与锚点退役 |
| `tests/test_r414_b_terminal_data_filename.py::test_the_registration_is_a_tail_append_over_the_base` | `c0c4bcd`（写在函数体内部的字面量里） | 函数体里现攒 `subprocess` ＋ 现攒契约路径 ＋ `startswith` | 三枚全部摘掉；本件不留任何自家 git 把手 |

红句逐枚相同（五枚）＝「契约不是纯追加：文末之前的每一个字都不许动」，r414_b 那一枚措辞不同但同病＝「契约中段被动过字：本单只许往文末追加」。病根同 r354：六枚各抄一把基点，又不许有人把 R630 那一格登记在册。

## 二、治法，与三条不许走的路

**治法**：六枚钉接到 R645 那一本**具名差异账**上，共用入口 `tests/test_r645_contract_difference_ledger.py::assert_history_matches_ledger`。每件留一枚本地薄壳 `_contract_history_account`，尺与账只有 R645 那一份。每枚钉保住自己那两条**与位置无关**的判据：本单那一节在追加段里恰一枚、`## ` 节数只增不减（r366／r373／r388 另保住「现盘比尺的基点长」这一条）。

🔴 **⚠️ 那个唯一可能的口径冲突点先量过**：六枚读到的是**同一格**（同一个 `first_token_not_a_stage_sample` 行，立案 `R630`），所以走**同一枚登记**，`EXPECTED_DIFFERENCES_TODAY` 仍是等号 1，枚数门一字未动，也没有把形状尺改宽 —— 本单新增的登记枚数＝**0**。这一格由 `tests/test_r653_six_nails_read_the_same_book.py::test_the_book_still_holds_exactly_one_named_difference` 常驻钉着：真长出第二枚，它当场红。

三条不许走的路，一条没走：

- 没把六枚改成结构级判据（`tests/test_r397_read_legs_refuse_a_missing_table.py` 09-28 被那样改口过一次，强度降了；本单不动它，它今天绿）。
- 没前移尺的基点、没清账、没加豁免名单、没 skip／xfail ——「前移基点＋清账＋枚数门归零」三条腿一起才绕得过去，而那正是本族牙要咬的形状（R645 的刀③ 已当场演示过）。
- 没动契约一字节：`docs/api/contract-v1.md` 在本席树里 `git diff --numstat` 为空，全程只读；`tests/test_r523_cached_count_lands.py::contract_is_pure_append` 那枚只比 `HEAD` 与现盘的钉同样一字未动。

## 三、六枚钉改完之后各自的判据（逐枚点名）

每枚钉现在四到五格，方向一律写死：

1. 走共用入口 ⇒ 现盘 == 尺的基点 ＋ 账上逐枚登记（账外一字节都不许动）。
2. `len(account.records) == EXPECTED_DIFFERENCES_TODAY`，且派生出来的立案名与账上登记的立案名逐枚相等（一枚都不许在基点上定位不到）。
3. `## ` 节数只增不减（比 R645 的尺的基点，不是比自家基点）—— 咬「有人删了别人的节」。
4. 本单那一枚节标题在**追加段**里恰一枚 —— 咬「一单长出两节」。r388 另保住「全文恰一枚」那一格。
5. r366／r373／r388／r414_b 另保住「现盘比尺的基点长」那一格。

🔴 每枚钉同文件里的其它用例一枚没删、一枚没动名册：六枚件 collected 枚数改前改后逐枚相同（见对照表），红逐枚同名。

## 四、四把刀（一律只拿 `tmp_path` 影子端判，不开 overlay 窗）

改动点全部**现派生**：`_punctuation_positions()` 在「账上第一格登记之前」那一段里逐枚取标点，本件不抄任何一枚数字；那一枚标点重写两枚 ⇒ 长度只增不减，所以这一刀只可能咬「账外被动过」那一格。每把刀进出各取一次盘上契约的 sha256 并断言相等。

| 刀 | 形状 | 必红的那一格与红句 |
| --- | --- | --- |
| ① 账外动一个标点 | 影子端把历史区里第 0 枚标点重写两枚 | 六枚同时红，红句**逐枚一字不差**（判据③），且点名「现盘第 … 字符（第 … 行）… 对应基点第 … 字符」；断言红句里**不许**出现「枚数不对」；同一枚影子端跑两遍得给同一份红 |
| ② 每枚钉一把自己的刀 | 落点逐枚不同（第 0..5 枚标点），另有一枚常驻牙断言这六枚落点两两不同、且都在账外 | 该枚钉必红，红句同上；六枚同时红 |
| ③ 把派生出来的位置抄回字面量 | 拿改过的源码文本（内存里，不写盘）现塞三形：一枚真位置、一枚位置串、一枚五位以上裸数字 | 反手抄扫描当场点名；先把干净源码扫一遍证明它不是空转 |
| ④ 谁偷偷再造一把尺 | 现塞五形：自家 `FROZEN_BASE`、自家枚数门写成 6、枚数门写成 `range(3)`、自家 `CONTRACT_DIFFERENCES`、自己攒一枚 `Difference` | 第二把尺扫描逐形点名；干净源码交回空表 |

## 五、对照表（同名件 25 枚；两态亲跑）

state①＝本树 `be-r653` apply 未 commit；state②＝`git worktree add --detach %TEMP%\r653_state2 28d1ea4` 的干净检出 ＋ 只投本单写域。解释器一律 `C:\Users\fengx\PycharmProjects\be-r653\.venv\Scripts\python.exe`，命令一律 `-p no:randomly -q`。

「改前」那一列＝同一枚影子树停在 `28d1ea4` 未投本单件时亲跑（名册只有 24 枚件：本单新件那时还不存在），六枚红的点名与派工词逐枚一字不差：`test_r340`／`test_r366`／`test_r367`／`test_r373`／`test_r388` 各 `test_the_contract_appends_one_section_and_deletes_nothing`，`test_r414_b` 为 `test_the_registration_is_a_tail_append_over_the_base`。

| 件 | collected | 改前 passed／failed | state① passed／failed | state② passed／failed |
| --- | --- | --- | --- | --- |
| tests/test_r253_no_test_rewrites_a_tracked_file.py | 9 | 9／0 | 9／0 | 9／0 |
| tests/test_r253_shadow_root_holds_the_mutation.py | 6 | 6／0 | 6／0 | 6／0 |
| tests/test_r302_docs_utf8_guard.py | 8 | 8／0 | 8／0 | 8／0 |
| tests/test_r340_replayable_alerts_open.py | 47 | 46／**1** | 47／**0** | 47／**0** |
| tests/test_r342_trend_undated_exit.py | 25 | 25／0 | 25／0 | 25／0 |
| tests/test_r354_delete_audit_shares_the_owner_reader.py | 18 | 18／0 | 18／0 | 18／0 |
| tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py | 24 | 23／**1** | 24／**0** | 24／**0** |
| tests/test_r367_gate_shape_pins.py | 23 | 22／**1** | 23／**0** | 23／**0** |
| tests/test_r373_the_two_remaining_legs_answer_absence.py | 39 | 38／**1** | 39／**0** | 39／**0** |
| tests/test_r381_outlet_answers_the_absent_approval_ledger.py | 32 | 32／0 | 32／0 | 32／0 |
| tests/test_r388_read_leg_answers_absence.py | 56 | 54／**1**（另 1 枚 strict xfail） | 55／**0**（同） | 55／**0**（同） |
| tests/test_r397_read_legs_refuse_a_missing_table.py | 31 | 31／0 | 31／0 | 31／0 |
| tests/test_r414_b_terminal_data_filename.py | 12 | 11／**1** | 12／**0** | 12／**0** |
| tests/test_r466_mutation_does_not_leak_into_live_module.py | 20 | 20／0 | 20／0 | 20／0 |
| tests/test_r504_terminal_frames_carry_data_filename.py | 25 | 25／0 | 25／0 | 25／0 |
| tests/test_r514_queue_worker_passes_dataset_files.py | 12 | 12／0 | 12／0 | 12／0 |
| tests/test_r523_cached_count_lands.py | 13 | 13／0 | 13／0 | 13／0 |
| tests/test_r545_counter_evidence_teeth.py | 24 | 24／0 | 24／0 | 24／0 |
| tests/test_r563_live_module_callables_do_not_leak.py | 5 | 5／0 | 5／0 | 5／0 |
| tests/test_r583_roster_reconciles_the_inventory.py | 5 | 5／0 | 5／0 | 5／0 |
| tests/test_r583_window_inventory.py | 4 | 4／0 | 4／0 | 4／0 |
| tests/test_r630_counter_evidence_teeth.py | 13 | 13／0 | 13／0 | 13／0 |
| tests/test_r635_counter_evidence_teeth.py | 13 | 13／0 | 13／0 | 13／0 |
| tests/test_r645_contract_difference_ledger.py | 15 | 15／0 | 15／0 | 15／0 |
| tests/test_r653_six_nails_read_the_same_book.py（本单新增） | 18 | 件不存在 | 18／0 | 18／0 |
| **合计** | 479 → 497 | **472／6／1 xfailed** | **496／0／1 xfailed** | **496／0／1 xfailed** |
| 用时 | — | 181.75 s（与一枚 collect-only 并发，不可与前两态比） | 85.70 s | 88.04 s |

读法：六枚由红转绿，新件 18 枚全绿，**其余十八枚件逐枚一枚没变**；两态 collected 枚数逐枚相同（497），两态红清单逐枚相同（空），1 xfailed 逐态同一枚（`test_r388` 那枚 strict xfail，本单没碰）。

🔴 **本席自己引入过一次红，逐枚点名并记档**：第一遍 state①（同一份名册）＝**3 failed / 493 passed / 1 xfailed / 99.99 s**，红逐枚点名 —— `tests/test_r367_gate_shape_pins.py::test_the_files_this_ticket_touched_keep_the_repo_line_ending`、`tests/test_r373_the_two_remaining_legs_answer_absence.py::test_every_delivered_file_keeps_the_repository_line_endings`、`tests/test_r388_read_leg_answers_absence.py::test_every_delivered_file_keeps_the_repository_byte_shape[pins]`。罪证是命令通道：编辑器补丁把新增行按 LF 写进一枚纯 CRLF 的在册件，八枚交付件因此混进 36～48 枚 lone LF。治法不是把三枚守卫改口（那是把别人的牙拔了换本单的清白），而是把八枚交付件归一回纯 CRLF：`lone LF=0`、`lone CR=0`、`BOM=无`、`U+FFFD=0`、控制字符 `0x00/0x07/0x08/0x0b/0x0c` 枚数＝0。本表的 state①／state② 两列就是**归一之后的复跑**（同一份名册、同一枚解释器、同一条命令），两态逐枚同数、红清单同为空；那三枚守卫在改前基线里本就绿，归一后仍绿。

两处顺手记档：① 归一前另跑过一遍 state②（八枚件里测试件已归一、doc 仍为 LF）＝496／0／1 xfailed / 81.83 s，与最终遍同数；本单的 doc 落在 `docs/testing/**`，名册里没有一枚件读它（`tests/test_r302_docs_utf8_guard.py` 管的是 `docs/handoff/**` 那本账），故 doc 的行尾不改变任何一枚读数 —— 仍归一了才投最终遍。② 两枚件的 `from tests import ...` 排在本件既有 `from tests.test_* import ...` 之后（`tests/test_r340_replayable_alerts_open.py`、`tests/test_r414_b_terminal_data_filename.py`），本仓没有 lint 门，纯样式；不改口是因为改一行就要重跑两态，不值当拿清白换整齐。

## 六、新件里的常驻牙（`tests/test_r653_six_nails_read_the_same_book.py`，逐枚一句话）

- `test_the_book_still_holds_exactly_one_named_difference` · 六枚读的是同一格：账上仍一枚、立案名 `R630`、枚数门仍等号 1、R645 那两枚字面量没被挪。
- `test_the_six_nails_are_green_on_the_disk_today` · 判据① 正控：六枚钉现跑现盘全绿（同名转绿）。
- `test_the_six_nails_read_this_same_book` · 判据②：逐枚 AST 现查可达面 —— 只走共用入口，`BASE`／`CONTRACT`／`_git_show`／`_base_file`／`_source`／`subprocess`／契约路径字面量／对文本变量做 `startswith` 一枚不许留，签名零参数。
- `test_the_ledger_handle_is_one_object_in_all_six_files` · 六枚件拿到的账本必须是同一个模块对象：否则刀架在这一份、钉读那一副看不见＝假绿。
- `test_the_six_files_ship_no_second_ruler` · 判据③ 的封口：六枚件里不许出现自家基点、自家枚数门、自家登记。
- `test_the_six_nails_ship_no_escape_hatch` · 判据「不许 skip／xfail／豁免名单」：可达面里逃生口零枚，枚数那一格不许从等号松成阈值。
- `test_the_six_nails_keep_their_own_non_position_teeth` · 接线不等于摘牙：每枚钉改完仍得留住 ≥4 格断言，其中必有枚数等号与 `.count(` 那一类与位置无关的牙。
- `test_no_nail_copies_a_derived_position` · 判据④ 两条扫描：全文扫今天派生出来的字符位与行号（六枚件＋本件）；可达面扫五位以上裸数字。
- `test_the_six_knives_edit_six_different_bytes` · 六把刀各改各的那一枚字节，两两不同且都在账外。
- `test_counter_evidence_1..4_*` · 见上节（② 逐枚参数化六枚）。

🔴 **判据④ 那条「五位以上裸数字」为什么只按可达面扫**：六枚件全文里今天活着两枚五位以上数字 —— `test_r366_...`／`test_r388_...` 里的假告警号 `alert:999999`、`test_r366_...` 首段里立案的 sha `4382443`。两者都不是位置；把它们逐枚剔出去就成了豁免名单（那正是判据禁的一条路），所以这一条扫「位置真正可能被用起来的那一格」＝钉的可达面，而**全文**扫的是「今天派生出来的那些数字」一枚都不许成字面量。这一格强度由刀③ 现证：把一枚真位置或任意五位数字塞进钉的第一行，扫描当场点名。

## 七、环境与纪律自证

- 零容器、零连库、零打模型、不起服务、不改 env、不动 powercfg、不动 `deploy/**`；**没起全量门**（本机另有席在跑），只跑同名件 25 枚。
- 反证刀**不开 overlay 窗**（`tests/_temp_edit_overlay.py` 一枚没用），所以不牵动 `tests/test_r466_mutation_does_not_leak_into_live_module.py`、`tests/test_r563_live_module_callables_do_not_leak.py`、`tests/test_r583_roster_reconciles_the_inventory.py`、`tests/test_r583_window_inventory.py` 那四本名册。
- 写域只有八处：六枚 `tests/test_r340_*.py`/`test_r366_*.py`/`test_r367_gate_shape_pins.py`/`test_r373_*.py`/`test_r388_*.py`/`test_r414_b_*.py`，新 `tests/test_r653_six_nails_read_the_same_book.py`，本 doc。禁区（`scripts/r636_stage_coverage.py`、`app/rag/retriever.py` 等三枚、`scripts/r633_*`、`app/api/v1/chat.py`、`app/api/v1/observability.py`、`scripts/audit_plan_ticket_ledger.py`、`docs/perf/**`、`docs/handoff/**`、评测集、`frontend/**`）一字未动；未 commit、未 add、未建分支、未 push。
- state② 用 `git worktree add --detach`，**不用** `git archive`：那棵树没有 `.git`，本族件全靠 `git show <基点>:<文件>`，实测 20 枚假红，tar 解中文文件名还报 Invalid empty pathname。跑完临时检出留在 `%TEMP%\r653_state2` 原地，由总控处置。
- 中文正文一律走单引号 here-string 写盘，写完现读并扫 `0x00/0x07/0x08/0x0b/0x0c` 枚数＝0、反引号枚数与预期相符（AGENTS.md 命令通道转义坑）。
