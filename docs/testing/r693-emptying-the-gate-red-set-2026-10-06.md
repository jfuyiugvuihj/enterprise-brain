# R693 · 凭据纸——门那格清零（9 枚在册先红逐枚治）

**号** R693　**基点** `6800b4c`（派工那一刻主树 HEAD 现取）　**独占树** `be-r693`
**状态** 不由本纸携带：`python scripts/tickets_index.py --verify` 现取。
**开工日** 2026-10-06　**交回时刻读数** 见 §6 逐条。

## 0　一句话

9 枚在册先红归零，手法只有工单给的两形：**跑派生尺自己写回**（r469／r492／r638）与
**修那把身份坏掉的钉**（r595／r498）。零摘牙：没有 xfail、没有 skip、没有删用例、没有改
任何在册判据的口径。本单造成一枚新红（手抄坐标棘轮要重取基线），已连读数写进 §7 交总控裁。

## 1　判据 1——逐枚归因（基点态 vs 本单态，二态对照）

* 基点态：HEAD=`6800b4c`、`git status --porcelain` 空、同名 14 枚件一跑＝**9 failed / 225 passed / 234 collected / 20.66 s**。
* 本单态：同名 14 枚件＋本单新增 1 枚＝**0 failed / 244 passed / 244 collected / 18.08 s**。
* 提交后干净树复跑（HEAD=`7cb7945`、`git status --porcelain` 空）＝**0 failed / 244 passed / 244 collected / 20.30 s**。
* 清单逐枚相同、总数相同：两态那 14 枚件的逐枚收集数一一对上——
  11／15／25／10／11／11／17／61／20／8／8／8／15／14（合计 234），本单只往新文件里加了 10 枚。

| 族 | 枚数 | 红的那几枚（`文件::符号`） | 归因 | 手法 |
|---|---|---|---|---|
| r469 读数件生成 | 2 | `tests/test_r469_readout_is_generated.py::test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits`／`::test_the_cli_is_the_only_way_that_produced_this_table` | 先红（环境性，见 §7-2） | 跑在册出表口 `scripts/r469_readout_lib.py::cmd_render` 写回盘上那份 |
| r492 §9.3 列对派生 | 2 | `tests/test_r492_s93_column_matches_derived.py::test_s9_3_coordinate_column_equals_the_derived_readings`／`::test_teeth_b_swapping_two_cells_turns_red` | 先红 | 新写回口 `scripts/r693_land_s93_column.py`（数字全部走 `scripts/r387_label_lineage.py::resolve_site`） |
| r595 run9 凭据复现 | 1 | `tests/test_r595_stall_cap.py::test_run9_book_credential_is_reproduced` | 先红 | 修钉：出处坐标改由 `scripts/r595_latency_readout.py::stall_cap` 现场取；命中枚数与帽值照旧冻死 |
| r498 提及／并树 | 1 | `tests/test_r498_landing_shape_is_not_a_mention.py::test_a_probe_burned_by_a_landing_message_reads_a_mention` | 先红 | 修钉：取证从 note 展示串改走 `scripts/dispatch_preflight.py::Ruler.landing_hits` 的证据清单 |
| r638 指针棘轮 | 3 | `tests/test_r638_pointer_ratchet.py::test_the_stored_baseline_matches_the_rulers_own_reading`／`::test_no_markdown_file_grew_its_paper_coordinates`／`::test_shrink_is_named_not_silently_forgiven` | 先红 | 按尺自己的输出重落基线（`--write-baseline`），见 §3 |

九枚全部**先红**：基点态那一跑就是把这九枚逐枚点名跑出来的，本单没有制造任何一枚「假先红」。

## 2　判据 2——零摘牙（可失败的读数）

* 本单 diff 里新增行含 `xfail`／`skip`／`filterwarnings` 的枚数＝**0**。
* 用例枚数不减反增：234 → 244（同名 14 枚件 234 枚原样在位，逐枚数见 §1）。
* 在册判据的口径一字未改：改的只有「数值从哪取」（`stall_cap` 现场取／`landing_hits` 证据清单取），没有改「判什么」。
* 若某枚必须改口径才能绿，本单会停下交裁——实际没有发生；§7 那几件是写域外的账，不是本单的判据。

## 3　判据 3——r638 那一族的具体病（洞在尺身，本单没动刀）

断点在 `scripts/r638_doc_pointer_ruler.py::ratchet_diff`：grew 分支只记 `added` 不落 `removed`，
而它自己的自证要求 `after − before == len(added) − len(removed)`。正文一 splice，行文本哈希整批轮转，
同一枚 doc 就会读成形如 `before=75 after=77 added=31`（removed 那一堆根本没进 cell）——恒等式当场断，
`ratchet_diff` 直接抛 AssertionError，三枚钉一起红。总控诊断与实测同形。

本单走工单给的**第二支**：按尺自己的输出重落基线。

* `--write-baseline` rc=**0**，交回 files=**128**／total_pointers=**4165**，基线件 **439,694 B**（LF，控制符 0 枚）。
* 旧基线 total=**4102** ⇒ 本次一次性把 **+63** 枚「别人家的纸上坐标」折进基线。那不是本单长的，是上一笔落基线之后各单账面动作的累计；宽免一次，读数在此留档。
* 重落之后 `--check-baseline` 交回 grew／shrank／shifted／forged／offenders 全空，三枚钉连同牙件共 29 passed／8.93 s。
* 🔴 恒等式那一刀归总控：把 `removed` 一并记进 grew 那一格，改的是 `scripts/r63*` 只读名单里的件，本单未动一个字节。

## 4　判据 4——夜窗量具只读（本单动了谁）

`git status --porcelain` 交回的清单（写域内七枚＋本纸）：

* 改：**5** 枚 —— `docs/perf/r387-label-lineage-2026-09-27.md`／`docs/testing/r469-sandbox-scope-readout-2026-09-28.md`（盘面行尾，`git diff` 空）／`docs/testing/r638-pointer-baseline.json`／`tests/test_r498_landing_shape_is_not_a_mention.py`／`tests/test_r595_stall_cap.py`
* 新增：**3** 枚 —— `scripts/r693_land_s93_column.py`／`tests/test_r693_land_s93_column.py`／本纸
* `scripts/eval_*`／`scripts/r57*`／`scripts/r59*`（含 `r595_*`）／`scripts/r63*`（含 `r631_*`／`r634_*`／`r636_*`／`r638_*`）／`scripts/r674*`／`scripts/run_gate.py`：**零枚改动**（逐枚都不在上面那份清单里）。
* 禁区一枚未碰：`app/**`／`frontend/**`／`deploy/**`／`.env*`／`tests/fixtures/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／`pyproject.toml`／`uv.lock`／容器·镜像·模型动作／主树任何路径。

## 5　判据 5——没跑全量门

本单只跑点名的同名件＋受影响面复跑两遍（本纸落盘前、落盘之后各一遍，两遍名册与读数相同）：

* 18 枚读文档的账面钉，落盘前：**3 failed / 222 passed / 1 xfailed / 256.08 s**。
* 同一份 18 枚件，本纸落盘之后：**3 failed / 222 passed / 1 xfailed / 257.93 s**——同三枚、同名、同数，本纸没踩红别处。
* 三枚红的归因：一枚本单造成（§7-1），两枚同名件外先红且写域外（§7-4）。全量门留给总控窗后独跑（判据 5）。

## 6　判据 6——交付读数（只有枚数／字节数／退出码／秒数）

* **r469**：写回前那份 **244,675 B**（CR **7,194**＝全片 CRLF）→ 写回后 **237,481 B**（CR **0**／LF **7,194**，差额恰为 CR 枚数）。证据件 `extract_evidence` 交回 **105,617 B**；`render` rc=**0**、`validate` rc=**0**（状态 SANDBOX_MEASURED_PRODUCTION_UNVERIFIED／有牙格 5 枚／未过判据 4 条）；写回后与 HEAD blob 逐字节同：`git hash-object` = `git rev-parse HEAD:…` = `efba7c71b82fb0d6e7f3dee33ddaa15b0c2e58f3`，`git diff --numstat` 交回**空**；同名件 **15 passed / 0.78 s**。
* **r387 §1**：在册写回口 `--land` rc=**0**，报「那些格已经是现读，一枚字节都不必动」。
* **r492 §9.3**：新写回口 `--check` rc=**5**「会改写 9 格」→ `land` rc=**0**「机械改写 9 格」→ 复跑 `--check` rc=**0**「会改写 0 格」（幂等）。文档 **101,269 B** 前后同数，CR **947**＝LF **947**（成对行尾原样还原）；同名件 **11 passed / 0.40 s**。
* **r638**：见 §3；两枚同名件 **29 passed / 8.93 s**。
* **r595**：**8 passed / 0.64 s**；那枚钉现在由 `stall_cap` 取坐标，`cap_ms == 300000.0` 与 `cap_line > 0` 另立一格明钉。
* **r498**：**61 passed / 3.64 s**。
* **r693 牙件**（`tests/test_r693_land_s93_column.py`）：**10 passed / 0.27 s**，全离线、不 import `app`、盘上零写入。
* **`python scripts/tickets_index.py --verify` rc=0**（工单文件 24 枚／索引 159 行／逐字块 14 枚；判据 1～5 逐条「过」）。
* 控制符扫描（逐枚交付件）：`0x00`／`0x07`／`0x08`／`0x0b`／`0x0c` 各 **0** 枚。
* 坐标口径：本纸与两枚新件的源码里「`文件.py` 冒号紧贴数字」那一形字面量各 **0** 枚（新件按在册反证钉同一手法用拼接造形状，牙件 `test_the_lander_and_this_pin_carry_no_hand_copied_coordinate` 钉着）。
* `git rev-list --count 6800b4c..HEAD` = **1**（首笔 `7cb7945`：7 枚文件／+730 −95）；本纸补记这些读数是第二笔，只改本纸这一枚。
* 未跟踪逐枚点名（提交前三枚）：`scripts/r693_land_s93_column.py`／`tests/test_r693_land_s93_column.py`／本纸。首笔之后 `git status --porcelain` = **空**。
* 提交后复取：`tickets_index.py --verify` rc=**0**；`lint_hand_copied_coordinates.py --check` 现取 **94**／预算 95／越界文件 **29**／rc=**0**。

## 7　交回总控裁的四件事（本单一律不自改）

**7-1　手抄坐标棘轮要重取基线 95 → 94（本单唯一一枚「造成」的红）**

* 尺：`python scripts/lint_hand_copied_coordinates.py --check` → 现取 **94**／预算 95／越界文件 **29**／判定 WITHIN／rc=**0**。
* 牙：`tests/test_chase_lint_names_every_hand_copy.py::test_the_live_tree_sits_exactly_on_the_ratchet` **1 failed**——它是双向棘轮，降了不重取基线也红。
* 降的是谁，逐枚点名：`tests/test_r595_stall_cap.py` 里那枚把 `scripts/eval_transport_ask_v2.py` 帽带行号抄进断言的字面量（本单改为 `stall_cap` 现场取）。全仓仅此一枚，越界文件数由 30 降到 29 同一枚。
* 那枚常量在 `scripts/lint_hand_copied_coordinates.py::HAND_COPY_BUDGET`——本单写域外，未动一个字节。**并树时把这枚常量改成 94 即闭合**（AGENTS.md 病根处置⑭写的正是这个流程：改预算要逐枚点名）。

**7-2　r469 那两枚红的根因是工作副本行尾，不是账**

* 事实：仓库里**没有** `.gitattributes`，本机 `core.autocrlf=true`；blob 是 LF（**237,481 B**／CR 0），checkout 把盘面铺成 CRLF（**244,675 B**／CR 7,194），而那枚钉逐字节比盘 ⇒ 天天误红。跑一次出表口就绿（本单已跑），但那是**盘面动作**：`git diff` 空，并树带不走。
* ⇒ 今晚窗后请总控在**主树**跑同一条命令，门那格才真绿：
  `python scripts/r469_readout_lib.py render --evidence <由 extract_evidence 现取的证据件> --out docs/testing/r469-sandbox-scope-readout-2026-09-28.md`
* durable 的两条路都在本单写域外，请裁：① 给仓库补 `.gitattributes`；② 改 `tests/test_r492_s93_column_matches_derived.py::read_rows` 里那枚「CR 枚数＝LF 枚数」的成对断言——它是按 CRLF 盘形写的，纯 LF 树会当场炸（在册 R531 一族已把这形记过账）。**注意 ① 单独做会把 ② 那枚钉打红**：两枚钉对行尾的要求今天正好相反，不是一句「全仓 LF」收得住的。

**7-3　r638 尺身恒等式**（见 §3：`ratchet_diff` 的 grew 分支不落 `removed`；那把尺在只读名单里，本单没动）

**7-4　同名件之外、本单写域之外的两枚先红（r483 那一族）**

* `tests/test_r483_empty_table_triage_is_derived.py::test_the_in_tree_document_is_the_regenerated_one_byte_for_byte` 与 `::test_the_coordinates_printed_in_the_document_are_the_ones_the_scanner_finds_now`。
* 归因凭据：用 `git archive 6800b4c` 现铺一棵**纯 LF 的基点影子树**单跑这两枚＝**2 failed**，红因是纸面冻在旧偏移、尺现读已前移 26 行（与行尾无关，病在 `app/trace/projections.py::project_retrieval` 那一格）。**先红，且与本单零关系**。
* 治法与本单同族：跑 `scripts/r483_empty_tables_triage.py` 自己的 `--sync`。那本 docs 与那枚 tests 都在本单写域外，本单没碰。

## 8　本单的写集（并树时逐枚对 SHA-256）

| 文件 | 动作 | 行数 |
|---|---|---|
| `docs/perf/r387-label-lineage-2026-09-27.md` | §9.3 最后一列机械改写 9 格 | +5 −5 |
| `docs/testing/r638-pointer-baseline.json` | 按尺自己的读数重落基线（total 4102 → 4165） | +178 −85 |
| `docs/testing/r469-sandbox-scope-readout-2026-09-28.md` | 出表口写回（盘面行尾归 LF，`git diff` 空） | 0 |
| `tests/test_r595_stall_cap.py` | 出处坐标改由尺现场取 | +12 −2 |
| `tests/test_r498_landing_shape_is_not_a_mention.py` | 取证改走证据清单（同族那枚绿的钉一并加固，见 §9） | +24 −3 |
| `scripts/r693_land_s93_column.py` | 新增：§9.3 机械写回口 | 新增 |
| `tests/test_r693_land_s93_column.py` | 新增：写回口自己的 10 把牙 | 新增 |
| `docs/testing/r693-emptying-the-gate-red-set-2026-10-06.md` | 新增：本纸 | 新增 |

## 9　复跑时刻的机器状态（现取）

* 解释器：独占树自己不带 `.venv`，本单所有跑件走主树那份 venv（只读它的 site-packages，没装也没改任何东西）。
* 跑件时机上另有约 12 枚 python 在飞（别的席在跑件），所以本节秒数只作同机对照、不作判据：同一枚清单在 dirty 态与本单提交态各跑一遍，244 枚名册逐枚相同。
* 夜窗纪律照 §5：本单没跑全量门，也没动容器·镜像·模型。
* 三态同名件读数全在同一台机、同一枚解释器上取：基点态（开工第一跑，`git status --porcelain` 空）9 failed／225 passed／234 collected／20.66 s → 本单态 dirty 0 failed／244 passed／18.08 s → 首笔提交后干净树 0 failed／244 passed／20.30 s → 工单追加之后 0 failed／244 passed／18.68 s。九枚红在两态之间逐枚点名相同，与工单那枚表一字不差；同名 14 枚件的逐枚收集数（11／15／25／10／11／11／17／61／20／8／8／8／15／14）两态完全相同——这就是「没摘牙」的那个数。
* `git archive 6800b4c` 现铺的**纯 LF**影子树里单跑 §7-4 那两枚＝**2 failed**，红因是纸面冻在旧偏移、尺现读已前移 26 行，与行尾无关；同一棵树里 r469 那两枚本单**没有跑过**，所以「纯 LF 会绿」只是 §7-2 那条字节账（blob LF／checkout CRLF）推出来的读法，不作为凭据写进判据。
* 工单文末追加了一段交回摘要（`docs/tickets/R693-gate-red-set-to-zero.md`，正文一字未动，只追加）。
* 工单文末追加了一段交回摘要（`docs/tickets/R693-gate-red-set-to-zero.md`，+9 行，在册正文一字未动）。

## 10　一处主动加固（判据没要求，本单仍做了）

`tests/test_r498_landing_shape_is_not_a_mention.py::test_the_landing_commit_of_one_ticket_is_only_a_mention_for_the_numbers_it_names`
今天**绿**，但它与那枚红的钉共用同一条坏通道（note 那一串只印最新一枚提及）。别的席再点一次
R475 的名，它就红——正是本单治的那一形。已一并改走 `landing_hits` 证据清单，档位／凭据枚数／
「别人的落地绝不允许升成本号凭据」三条一条没松；改后该件 61 枚全绿（读数见 §6）。
