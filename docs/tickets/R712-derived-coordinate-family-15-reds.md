# R712 · 门那格真账：派生坐标族在当前 HEAD 仍 15 枚红（r455 一族为主），全量门读数已过期

**号**：R712　**性质**：总控亲签（10-06 16:1x 亲跑，不是执行层自报）　**基点**＝派工那一刻主树 HEAD 现取

## 读数现取（同一片受影响件，主树 `.venv\Scripts\python.exe`）

- 命令口径：`python -m pytest -q --no-header` ＋ 17 枚点名件（r460／r455×2 件／r387×2 件／r492／r483／r469×3 件／r400／r496／r498），**212.68 s**。
- 结果：**15 failed／358 passed**，rc=1。逐枚点名（用例 id 全写，别只报总数）：
  - `tests/test_r455_gapdoc_coordinates_are_derived.py`：param `[T2]`／`[G04]`／`[G06]`／`[G08]`／`[\u00a7遗留]` ＋ `::test_no_hand_copied_coordinate_lives_outside_the_history` ＋ `::test_the_tool_catches_a_brand_new_copied_coordinate` ＋ `::test_the_check_command_answers_zero_on_a_clean_tree`
  - `tests/test_r455_hand_fudged_numbers_and_wrong_layers_both_redden.py`：三枚（`::test_bumping_a_cell_by_one_the_offset_math_trick_goes_red`／`::test_retouching_a_historical_table_is_red_and_only_the_freeze_tooth_sees_it`／`::test_a_wrong_layer_cite_stays_red_even_when_the_number_matches`）
  - `tests/test_r483_empty_table_triage_is_derived.py::test_the_in_tree_document_is_the_regenerated_one_byte_for_byte`
  - `tests/test_r492_s93_column_matches_derived.py`：两枚（`::test_s9_3_coordinate_column_equals_the_derived_readings`／`::test_teeth_b_swapping_two_cells_turns_red`）
  - `tests/test_r400_derived_ledger_shift_and_silence_pins.py::test_only_the_hops_that_cite_the_shifted_file_go_red`
- 对照：上一班记的那次 **57 failed／11438 passed／978.29 s** 属更旧的代次，**已过期**；r460／r387／r469／r496／r498 那几族在本次复跑里已绿（R693 清零笔 `d2bd779`＋R701 行尾根治 `c545084` 起了作用）。§9 判据 4「红集合为空」⇒ **门那格今天仍不绿**。

## 判据（每条可失败）

1. 先归因后动刀：逐枚交出「这 15 枚红是被测对象真变了，还是量具自己过期」的分栏——r455 那批按名字就写着 gap-doc 坐标派生，先现取那本 gap 文档的坐标列与派生读数各是多少，点名差在哪几格；不许用「都是同一类」含糊过去。
2. 治法只许两种形：① 文档侧那本 gap 表的坐标格**由脚本再生**（照 `tests/test_r469_readout_is_generated.py` 的在册正例：in-tree 文档＝再生成物，逐字节相等）；② 量具侧过期判据改按 `文件::符号` 派生。**不许**手抄新数字进文档凑绿，**不许**摘牙。
3. 反证钉不许分层出门：修完复跑同名 17 枚必须 **0 failed**，且 `python -m pytest -q -m "counter_evidence or teeth" <这 17 枚>` 的读数必须逐枚点名（`tests/test_r455_hand_fudged_numbers_and_wrong_layers_both_redden.py` 那三枚本身就是牙，它们红说明盘面与账不一致，不是牙坏了）。
4. 收口口径：本单结案判据＝「受影响面 0 failed」＋「一次全量门 `python scripts/run_gate.py` 在当前 HEAD 交回 exit=0」；两枚都要总控亲跑，墙钟只当样本。
5. 交付：两态读数＋分栏表＋凭据纸 `docs/testing/r712-<开工日>.md`。

## 写域（只许这些）

`docs/perf/**`（那本 gap 文档的坐标列，且只许由再生脚本写）／`scripts/**`（本单点名到的派生尺，禁碰夜窗量具）／`tests/test_r455_*.py`／`tests/test_r483_*.py`／`tests/test_r492_*.py`／`tests/test_r400_*.py`／新增 `tests/test_r712_*.py`／`docs/tickets/R712-*.md`／`docs/testing/r712-<开工日>.md`

## 禁区

`app/**`／`frontend/**`／评测集与判分器／`scripts/night1006_queue.py`·`scripts/day1006_queue.py`·`scripts/r631_*`·`scripts/r636_*`（窗在跑就一格不许动）／`docs/handoff/**` 既有前置行／容器·镜像·模型·GPU。
