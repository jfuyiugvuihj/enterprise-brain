# R693 · 门那格清零：9 枚在册先红逐枚治（段 A′ 的同一手法，扩到剩下四族）

**号**：R693　**基点**＝派工那一刻主树 HEAD 现取（本段落盘之后那一枚；产品码代次＝`4ebfaff`，它之后全是账面件）
**独占工作树**：由总控预配并告知路径，不许换树、不许碰主树。
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取。

## 现取病形（总控 10-06 12:0x 亲跑，不是转述）

主树 `4ebfaff` 上，16 枚同名件一跑＝**9 failed / 268 passed / 26.53 s**。红的逐枚名单（总控亲取）：

| 族 | 枚数 | 红的那几枚（文件::符号） |
|---|---|---|
| r638 指针棘轮 | 3 | `tests/test_r638_pointer_ratchet.py::test_the_stored_baseline_matches_the_rulers_own_reading`／`::test_no_markdown_file_grew_its_paper_coordinates`／`::test_shrink_is_named_not_silently_forgiven` |
| r469 读数件生成 | 2 | `tests/test_r469_readout_is_generated.py::test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits`／`::test_the_cli_is_the_only_way_that_produced_this_table` |
| r492 §9.3 列对派生 | 2 | `tests/test_r492_s93_column_matches_derived.py::test_s9_3_coordinate_column_equals_the_derived_readings`／`::test_teeth_b_swapping_two_cells_turns_red` |
| r595 run9 凭据复现 | 1 | `tests/test_r595_stall_cap.py::test_run9_book_credential_is_reproduced` |
| r498 提及／并树 | 1 | `tests/test_r498_landing_shape_is_not_a_mention.py::test_a_probe_burned_by_a_landing_message_reads_a_mention` |

**这 9 枚先于本单存在**，总控已在干净影子树 `f36de2f`（R688／R673 都未进树）上复跑同名件核对过 r498 那一枚＝1 failed / 60 passed 同一枚同一形状。其余八枚请本单逐枚交「先红 vs 本单造成」二态对照，不许含糊。

## 为什么会堵住 V1

`docs/version-roadmap-and-requirements-2026-10-05.md` §9 判据 4 要的是**全量门红集合为空**，不是「红都能归因」。段 A′ 已把三族派生坐标 39 枚红治到 0（手法＝跑尺自己 `--land` 写回，人手一个数字都不改），这 9 枚是剩下的同族账。

## 判据（每条都可失败，缺一枚判负）

1. **逐枚归因**：9 枚每枚写清「先红／本单造成」，凭据＝在基点干净树与本单树上的同名件二态对照读数（清单逐枚相同、总数相同）。
2. **零摘牙**：红集合变空只许靠「跑派生尺自己写回」或「修那把身份坏掉的尺」，不许 `xfail`／`skip`／删用例／改判据口径凑绿。摘牙＝退回。🔴 若某枚必须改在册判据的**口径**（不是数值）才能绿，停下写进交付由总控裁，不许自改。
3. **r638 那一族的具体病**（总控已诊断，供少走弯路）：棘轮尺自己的恒等式断了——`after − before == len(added)` 在现盘上不成立（实测形如 `before=75 after=77 added=31`）。要么修恒等式（含 `added` 的重复计数口径），要么按尺自己的输出重落基线；**判据是尺的读数与钉的期望同源**，不是某个具体数字。
4. **夜窗量具只读**：`scripts/eval_*`／`scripts/r57*`／`scripts/r59*`（含 `scripts/r595_*`）／`scripts/r63*`（含 `scripts/r631_*`／`r634_*`／`r636_*`／`r638_*`）／`scripts/r674*`／`scripts/run_gate.py`——**只许读、不许改**。r595／r638 的洞若确在尺身上，交回总控裁，别自己动刀。
5. **不许跑全量门**：夜窗今晚要跑，且此刻另有三席在跑测试。本单只跑自己点名的同名件（16 枚起），全量门由总控在窗后独跑。
6. **交付**：凭据纸 `docs/testing/r693-<开工日>.md`（判据实际读数：枚数／字节数／退出码／秒数，不许形容词）＋两态同名件数字＋`rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋控制符 `0x00/07/08/0b/0c` 各 0 枚＋坐标一律 `文件::符号`（出现 `*.py:数字` 即本单作废）＋`python scripts/tickets_index.py --verify` rc=0。

## 写域（只许这些）

`tests/test_r469_readout_is_generated.py`／`tests/test_r492_s93_column_matches_derived.py`／`tests/test_r498_landing_shape_is_not_a_mention.py`／`tests/test_r638_pointer_ratchet.py`／`tests/test_r595_stall_cap.py`／新增 `tests/test_r693_*.py`／新增 `scripts/r693_*.py`（若要新量具）／它们各自派生写回的 `docs/**` 读数件（**靠尺写回，不靠手改**）／`docs/tickets/R693-*.md`／`docs/testing/r693-<开工日>.md`

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`deploy/**` 与任何 `.env*`／评测夹具 `tests/fixtures/**` 与 `tests/test_evaluation_report.py`／`docs/handoff/**`／`docs/api/contract-v1.md`／`pyproject.toml`／`uv.lock`／`scripts/run_gate.py`／容器·镜像·模型动作／主树任何路径。

---

## 执行层交回（派工词只送指针，席位名未告知故不落名／独占树 be-r693／基点 6800b4c·2026-10-06 12:5x 现取）

* **九枚全先红**：基点态同名 14 枚件一跑＝9 failed／225 passed／234 collected／20.66 s，红的名与本单点名逐枚对上；本单态＝0 failed／244 passed／244 collected（同名 234 枚名册一一枚相同，另加本单 10 枚牙）；提交后干净树复跑＝0 failed／244 passed／20.30 s。
* **手法只有在册那两形**：跑派生尺自己写回（r469 出表口／r492 补的 §9.3 写回口／r638 按尺自己的读数重落基线 4102→4165）＋修那把身份坏掉的钉（r595 出处坐标改由 `stall_cap` 现场取／r498 取证从 note 展示串改走 `landing_hits` 证据清单）。零摘牙：无 xfail／skip／删用例／改口径。
* **本单造成一枚新红（写域外，请并树时一并裁）**：手抄坐标棘轮要重取基线 95→94，降的是 `tests/test_r595_stall_cap.py` 那一枚字面坐标；牙 `tests/test_chase_lint_names_every_hand_copy.py::test_the_live_tree_sits_exactly_on_the_ratchet` 因此红。常量在 `scripts/lint_hand_copied_coordinates.py::HAND_COPY_BUDGET`，本单未动。
* **另三件交回**：① r469 那两枚的根因是 `core.autocrlf=true` 的工作副本行尾而非账，主树窗后需再跑一次同一条出表口命令（并树带不走盘面行尾）；② r638 的 `ratchet_diff` 恒等式在 grew 那一格不落 `removed`（尺在夜窗只读名单，本单没动刀）；③ `tests/test_r483_empty_table_triage_is_derived.py` 两枚同名件外先红，纯 LF 基点影子树单跑复现，治法是它自己的 `--sync`，写域外。
* **凭据纸**：`docs/testing/r693-emptying-the-gate-red-set-2026-10-06.md`（判据 1～6 逐条读数）。新量具 `scripts/r693_land_s93_column.py` ＋牙件 `tests/test_r693_land_s93_column.py`。两笔提交 `7cb7945`（货）＋`9b41738`（本纸补记读数）；本段追加为第三笔。
* **夜窗纪律**：没跑全量门；`app/**`／`frontend/**`／`deploy/**`／夹具／`docs/handoff/**`／`pyproject.toml`／`uv.lock`／只读量具／主树——一枚未碰。
