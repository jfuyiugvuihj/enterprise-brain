# R655｜把 r643 那格「拿过期事实当判据」的钉升格——读数与凭据

- 工单：R655（升格 tests/test_r643_shot_denominator.py::test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator）
- 工作树：C:\Users\fengx\PycharmProjects\be-r655，基点 246efb7（＝R647 并树那一笔，`git rev-parse HEAD` 现取 246efb755f5a1efaa2e871853bcf48267927b684）
- 交付时三枚现取（本席 10-05 在收工那一刻亲取，含本文自身）：
  - `git rev-list --count 246efb7..HEAD` = 0（本席零 commit，总控代提交）
  - `git diff --numstat HEAD` = 一枚：`tests/test_r643_shot_denominator.py` 46 加 / 8 减
  - `git ls-files --others --exclude-standard` = 两枚：`tests/test_r655_no_stale_fact_teeth.py`、`docs/testing/r655-stale-fact-denominator-2026-10-05.md`（本文）
  - `git status --porcelain` = 3 枚，与「一枚改动＋两枚新增」逐枚对上，没有第四路
- 跑测试只用本树解释器：`C:\Users\fengx\PycharmProjects\be-r655\.venv\Scripts\python.exe -m pytest -p no:randomly -q …`（anaconda 系统 python 一次都没用）

## 1 病因（现取，不是转述）

改前在 246efb7 干净树合跑同名三件（29＋31＋14＝74 枚）：**1 failed / 73 passed / 20.25 s**，唯一红逐字：

```
tests/test_r643_shot_denominator.py::test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator
Failed: DID NOT RAISE MismatchError
```

与总控 10-05 00:2x 亲跑的读数同一枚、同红句（那一跑 1 failed / 73 passed / 20.87 s）。

病因不在 R647：那格把「R643 并树之后 r636 仍然把同题多发折成一枚分母 ⇒ 与 r631 分歧」这枚**现场读数**当成了判据钉住；R647 的目的正是摘掉那枚红（`scripts/r636_stage_coverage.py::read_inputs` 的发级分母改走 `scripts/r631_stage_sum_delta.py::collect` 那条路），红没了，这格就当场变成拿过期事实当真理的假红，且它在全量门里非 skip ⇒ 门固定红这一枚。

## 2 现取读数（升格后这格断的两半）

| 腿 | 现取（真料在 %TEMP% 下 evalrun 三本件） |
| --- | --- |
| `scripts/r631_stage_sum_delta.py::collect`（run20k，缺省） | doc-04 两发：`trace-a95ea9e4bfaf4db28a91f876cccfe121` → 27244.6 ms／error_pct 30.7863；`trace-1e1e2cf5512548de928e8a5fede8672b` → 27490.9 ms／27.9616；`shot_leg.spreads` 只 doc-04 一枚：shots_ms [27244.6, 27490.9]、spread 246.3 ms、spread_pct_of_min 0.904 |
| `scripts/r636_stage_coverage.py::build_window`（run20k，缺省＝正形） | `mismatches` = 空；`reference_gap` = rows 106／skipped 19／asked_minus_rows 0／no_denom_minus_skipped 0；`shot_ledger.fold_legacy` = False；doc-04 两行逐枚等于 r631 那两枚分母 |
| `scripts/r636_stage_coverage.py::read_inputs`（run20k，fold_legacy=True＝病形） | 两发分母一起被押到 27490.9；`legacy_conflicts` 点名「doc-04 发1/2」：shot_wall_ms 27244.6 vs used_ms 27490.9，delta 246.3 |
| `scripts/r636_stage_coverage.py::build_window`（run20k，fold_legacy=True＝病形） | 当场抛 `MismatchError`：2 处 —— end_to_end_ms（mine 27490.9／r631 27244.6，`trace-a95ea9e4bfaf4db28a91f876cccfe121`）与 error_pct（mine 31.4064／r631 30.7863） |

升格后的形状（实现自选，两半都断）：正形把 `mismatches` 与空列表比＋把两发的分母以 [27244.6, 27490.9] 字面量在册（并加「不许平均（27367.75 不在其中）」「不许取最大（27490.9 只出现一次）」「逐枚 trace 对得上」三枚锚）；病形把 `pytest.raises(MismatchError)` 只包住带 `fold_legacy=True` 的那一条路，并断言红句点名那枚 trace 与两个数字。格名保留原样：按字面读，它今天说的就是「只在折回一枚分母时才与覆盖面账分歧」。

## 3 判据逐条交读数

**判据 1（r643 单件 29 枚全绿，枚数不变）**：25 枚 test 函数一枚不少（在册 25 枚格名已由 `tests/test_r655_no_stale_fact_teeth.py::test_the_denominator_file_ships_every_named_cell_unmarked` 逐枚点名，删格当场红）。单件合跑：state① 29 passed / 7.70 s；state② 29 passed / 7.22 s。加格全部落在新文件，r643 的 29 枚一字未动。

**判据 2（与 R647 两枚同名件同跑）**：

| 组 | 枚数 | state①（本树 apply 未 commit） | state②（246efb7 干净检出＋同名件） |
| --- | --- | --- | --- |
| r643 单件 | 29 | 29 passed / 0 failed / 7.70 s | 29 passed / 0 failed / 7.22 s |
| r655 单件 | 18 | 18 passed / 0 failed / 29.84 s | 18 passed / 0 failed / 30.63 s |
| 三件合跑（r643 29＋r636 31＋r647 14） | 74 | 74 passed / 0 failed / 19.16 s | 74 passed / 0 failed / 20.80 s |
| 四件合跑（＋r655 18） | 92 | 92 passed / 0 failed / 47.19 s | 92 passed / 0 failed / 51.79 s |

两态总枚数相同（74／92），红逐枚同名（两态都 0 红）。state② 的树是 `git archive 246efb7` 导出的干净检出，只把本席这两枚测试文件复制进去；`import app` 现读解析到导出树内的 app 包（不是主树）。两态都用 be-r655 的 `.venv`。

**判据 3（新增常驻牙）**：`tests/test_r655_no_stale_fact_teeth.py`，18 枚，逐枚点名：

- `test_the_honest_leg_is_not_wrapped_in_pytest_raises`（形状闸：裸调用与 raise 的分家）
- `test_the_positive_leg_compares_and_the_two_numbers_are_pinned`（对账闸：比空列表、禁自比、禁 assert 字面真值、两枚分母与红句两个数字在册）
- `test_the_denominator_claim_is_today_s_live_fact`（现读闸：数字从两把尺自己嘴里取；账面字面量与今日现读分家即红并要人重算）
- `test_the_fold_switch_is_off_by_default_in_the_shipped_ruler`（`scripts/r636_stage_coverage.py::read_inputs` 与 `::build_window` 的 `fold_legacy` 缺省必须是 False）
- `test_the_denominator_file_ships_every_named_cell_unmarked`（25 枚在册格名＋那格只剩真窗 skipif 一枚标记＋全文无 skip／xfail）
- `test_every_blade_anchor_hits_exactly_once_in_the_shipped_bytes`（锚点漂移即红，不许默默失刀）
- `test_no_tooth_in_this_domain_gates_on_the_checkout_state`（本域四枚源文里不许出现盘面探针，也不许起子进程摸盘面——在册事故 #96／#107／#113 同族）
- `test_the_shape_control_stays_green[S1｜S2]`、`test_each_shape_knife_reddens_its_named_victim[S1｜S2]`
- `test_the_ruler_control_stays_green[K1｜K2｜K3]`、`test_each_ruler_knife_reddens_its_named_victim[K1｜K2｜K3]`
- `test_the_shadow_machinery_leaves_its_tracks_under_tmp_only`（影子只落 tmp_path；跑完两枚源文一字节未动，仓内不留影子件）

真窗三本件不在位时，本件里 7 枚跳过（现读闸 1＋ruler 正控 3＋ruler 刀 3），其余 11 枚照跑照判——与 r643 在册的「不在位即 skip，不改判语」同一口径。

**判据 4（逐把改前／改后红绿数）**：victim 逐枚点名，「改前」＝同一套影子机械、`edits=()` 的正控读数，「改后」＝刀口落下去后 victim 的读数（本席用仓外驱动 `r655_knife_ledger` 直接跑 victim 取数，与文件里的正控／刀项互证）。

| 刀 | 落点 | victim | 改前 | 改后 | 红因（逐字首句） |
| --- | --- | --- | --- | --- | --- |
| K1 折返开关被摸成恒不折 | `scripts/r636_stage_coverage.py::read_inputs` 里 `fold_legacy` 一路压成 False | r643 那格 | 1 passed／0 failed | 0 passed／1 failed | Failed: DID NOT RAISE MismatchError（病形不红＝判据哑） |
| K2 缺省就把两发折成一枚分母 | 同处压成 True | r643 那格 | 0 failed | 1 failed | MismatchError：与 R631 现跑读数对不上 2 处…doc-04／`trace-a95ea9e4…`／mine 27490.9 vs r631 27244.6（正形当场抛，绿不了） |
| K3 连对账基准也一起折 | `::build_window` 里 `reference_rows` 那一路也带 fold_legacy=True（与 K2 叠投） | r643 那格 | 0 failed | 1 failed | AssertionError：两发的逐枚分母不再等于在册读数…（现读 [27490.9, 27490.9]）——此时 `mismatches` 交回空列表、账面自洽，只有逐枚数字这一枚锚能救 |
| S1 把那格改回「拿旧红当判据」 | r643 那格的 raise 套回缺省那条路、折返开关摘掉 | 本件的形状闸 | 1 passed | 0 passed／1 failed | AssertionError：那格两半都要在位：不带折返开关 2 枚、带 fold_legacy=True 0 枚 |
| S2 正形断言被摸成永真 | `mismatches` 与空列表比 改成一枚自比 | 本件的对账闸 | 1 passed | 1 failed | AssertionError：正形那半枚不再与空列表比 ⇒ 对账被摸成了永真 |

正控：`test_the_shape_control_stays_green` 两枚、`test_the_ruler_control_stays_green` 三枚，在交付态（本树两文件为最终字节）全部 passed ⇒ 五把刀的红都是被咬中，不是机械自己红。

## 4 实弹反证（把旧写法放回干净检出）

`git archive 246efb7` 再导一棵树，只放本席新增的 `tests/test_r655_no_stale_fact_teeth.py`，`tests/test_r643_shot_denominator.py` 保持 HEAD 那枚旧写法，两件合跑 47 枚：**12 failed / 35 passed / 34.87 s**。逐枚点名：

- 旧格自己红：`test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator`（Failed: DID NOT RAISE MismatchError）
- 本件形状闸红：`test_the_honest_leg_is_not_wrapped_in_pytest_raises`
- 本件对账闸红：`test_the_positive_leg_compares_and_the_two_numbers_are_pinned`
- 本件锚点闸红：`test_every_blade_anchor_hits_exactly_once_in_the_shipped_bytes`（旧字节里没有折返开关那一枚调用，装刀当场炸，不静默失刀）
- 五把刀的正控全红（`test_the_shape_control_stays_green[S1｜S2]`、`test_the_ruler_control_stays_green[K1｜K2｜K3]`）＝「改前必须绿」这条纪律在替说话
- `test_each_shape_knife_reddens_its_named_victim[S1｜S2]` 红＝装刀炸在锚点上
- **`test_each_ruler_knife_reddens_its_named_victim[K2]` 红**：旧写法在「缺省就把两发折成一枚分母」的世界里反而判绿——这正是工单点名的「仍判绿」那一族的现行证据；升格后 K2 咬得住（见上表）。

⇒ 「把这格改回拿旧红当判据那种写法必须当场红」不是纸面承诺：旧写法一放回，门里当场 12 枚红，其中 8 枚是本件替它作的证。

## 5 写域与禁区自证

- 本席只动三路：`tests/test_r643_shot_denominator.py`（改）、`tests/test_r655_no_stale_fact_teeth.py`（新）、`docs/testing/r655-stale-fact-denominator-2026-10-05.md`（新，即本文）。
- `scripts/r631_stage_sum_delta.py` 一字未动（`git diff --numstat HEAD` 不点名它）；`scripts/r636_stage_coverage.py`、`tests/test_r647_shot_denominators_are_per_shot.py` 只读；`app/api/v1/chat.py`／`observability.py`、六枚契约前缀钉、`app/rag/**`、`docs/api/contract-v1.md`、`docs/handoff/**`、`docs/perf/**`、评测集、`scripts/run_gate.py`、`frontend/**` 零接触。
- 零 commit／零 add／零建分支／零 push；零模型调用；不起服务；不动容器与镜像；不跑全量门；主树一律只读，影子与干净检出全在 %TEMP% 下；GPU 一枚都没占。

## 6 留给总控的两条口径

1. `scripts/r636_stage_coverage.py::shot_ledger_view` 的 `fold_legacy` 标签取的是调用方参数，不是那条腿的实际折叠态：在 K1 的世界里它照旧报 True。本单靠逐枚分母数字兜住这个空洞，标签口径本身不在本单写域，要不要治由总控定。
2. 现读闸（`tests/test_r655_no_stale_fact_teeth.py::test_the_denominator_claim_is_today_s_live_fact`）不抄账面，判据若再换（比如 r636 的分母腿又搬家），它会先红并要求重算字面量——别把它改成「跑通就行」，那正是本单要摘掉的那枚病。
