# R647 —— 覆盖面账的端到端分母升到「发」级（10-04 夜班）

执行层席位：本单唯一执行层。树 `C:\Users\fengx\PycharmProjects\be-r647`，基点 `28d1ea4`（内含 `.venv` 的 Junction）。
零提交：`git -C be-r647 rev-list --count 28d1ea4..HEAD` = **0**。并树与提交由总控代做。

## 1. 治的病（总控 22:3x 现取病因，本席在本树复现同一笔）

- 病灶：`scripts/r636_stage_coverage.py::read_inputs` 取 `scripts/r631_stage_sum_delta.py::read_sidecar` 出分母 ——
  那是**题号级折叠视图**（`r631_stage_sum_delta.py::_collect_by_key`：同题多发取 attempt 最大、并列取后一行）。
- 对账基准：`scripts/r636_stage_coverage.py::build_window` 里的 `reference_rows` 取自 `r631_stage_sum_delta.py::collect`，
  R643（并树 `f0c4572`）之后它是**发级真值、按 trace_id 索引**（`r631_stage_sum_delta.py::build_rows`）。
- ⇒ 同题两发的两枚 trace 拿到同一枚折叠分母，逐枚对账当场崩。本席在本树（基点 28d1ea4、未 apply 之前）现取：
  `.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r636_stage_coverage.py` = **5 failed / 26 passed / 16.84 s**，
  红名册与总控纸上五行逐枚同名；红句逐字：
  `MismatchError: 与 R631 现跑读数对不上 2 处 … key=doc-04 / trace_id=trace-a95ea9e4bfaf4db28a91f876cccfe121：end_to_end_ms mine 27490.9 vs r631 27244.6；error_pct mine 31.4064 vs 30.7863`。

## 2. 改法（不造第二套原语，只把取分母那一步挪到在册那条路上）

- `r636_stage_coverage.py::read_inputs` 现在走 `r631_stage_sum_delta.py::read_sidecar_shots` ＋
  `r631_stage_sum_delta.py::read_frames_shots` ＋ `r631_stage_sum_delta.py::trace_sessions_from_events`
  ⇒ `r631_stage_sum_delta.py::_build_shot_leg` ⇒ `r631_stage_sum_delta.py::attribute_shots`，
  即 `r631_stage_sum_delta.py::collect` 里 `E2E_SIDECAR` 那条腿的**同一条装配路、逐枚同参数**
  （同一座桥 `trace_keys_from_events`、同一个 `allow_unjoined=not samples_by_trace`、`join_identities={}`）。
- 分母 = 该腿按 trace 索引的读数，逐发各拿各的：不平均、不取最大、不折一枚装作对上。
- 腿落在非 trace 索引（`keyed != "trace"`，即桥不在位）⇒ `read_inputs` 当场 `InputMissing`（RC=3 那句），不猜配对。
- 新增两枚在册形状的辅助：`r636_stage_coverage.py::_samples_by_trace`（把 `build_window` 里那段内联筛样收成一个函数，
  与 r631 那条路的筛法逐字一致）、`r636_stage_coverage.py::shot_leg_view`（发级账抬头，一枚数都不自算，全读
  `r631_stage_sum_delta.py::summarize_shots` 的现跑读数）。
- `r636_stage_coverage.py::build_window` 多一枚关键字参数 `fold_legacy=False`，只把 `r631_stage_sum_delta.py::_build_shot_leg`
  里已在册的病形复现开关透下去（默认 False）。它不是豁免：翻真只会**当场红**（见 §5 牙②）。
- 印面 `r636_stage_coverage.py::render` 多一行抬头，写明端到端腿按发取、身份分布、同题多发的题号、未归名清单；
  `fold_legacy` 在位时那行末尾带 🔴「折叠视图复现中」。

## 3. 禁区自证（本席现取）

- `git -C be-r647 diff --numstat 28d1ea4 -- scripts/r631_stage_sum_delta.py` = 空 ⇒ r631 一字未动（`read_sidecar` 仍在那件里当对照，
  见牙③ 的 `tests/test_r647_shot_denominators_are_per_shot.py::test_r631_still_owns_the_folded_view`）。
- 两条阈值线 `<1%`／`<0.03%` 未动（字面来自 `r631_stage_sum_delta.py::read_criterion_pct`／`read_alignment_pct` 现读，本件不持有）；
  母集四格 `r636_stage_coverage.py::UNIVERSE_GROUPS` 一字未动；`r636_stage_coverage.py::UniverseError` 那道闸未放宽。
- 未摘组、未加豁免；`scripts/r634_category_delta.py` 与 `tests/test_r634_*` 未摸（本席现跑 `tests/test_r634_category_delta.py` = **10 passed / 1.11 s**）。
- 那六枚「契约逐字节前缀」钉（`tests/test_r340_replayable_alerts_open.py`／`test_r366_*`／`test_r367_gate_shape_pins.py`／
  `test_r373_*`／`test_r388_*`／`test_r414_b_terminal_data_filename.py`）一枚未碰 —— 那是 R653 的活。
- `app/**`、`frontend/**`、评测集、容器、镜像、模型、Ollama 零动作；本单全程零网络、零模型、零 PG、零连库。

## 4. 判据逐条自证（纸上写读数）

| 判据 | 本席读数 |
| --- | --- |
| ① 五枚红同名转绿，其余 26 枚同名继续绿，总数 31 不变 | `tests/test_r636_stage_coverage.py` = **31 passed / 0 failed / 6.34 s**（state①）；`--collect-only` 名册 31 枚逐枚与改前同名同序 |
| ② 每一枚 `questions` 的 `end_to_end_ms` 逐枚等于 `reference_rows[trace_id]`；doc-04 两发同时摆 27,244.6 与 27,490.9 | run20k 现取：`doc-04` 两行 = `trace-a95ea9e4bfaf…` → 27244.6／error_pct 30.7863，`trace-1e1e2cf55125…` → 27490.9／error_pct 27.9616；`len({end_to_end_ms}) == 2`；全 106 行逐枚与 `r631_stage_sum_delta.py::collect` 对：不等者 **0 枚**；`data["mismatches"] == []` |
| ③ 常驻牙：折回一枚分母必须当场红 | `tests/test_r647_shot_denominators_are_per_shot.py` = **14 passed / 0 failed / 8.37 s**（state①），内含 `test_folding_shots_back_to_one_denominator_goes_red`（合成窗，环境无关）＋ `test_real_run20k_goes_red_when_the_shots_are_folded`（真窗，导出件不在位即 skip）；两枚都配正控（`test_the_fold_knife_really_folds` 证那把刀真在折，`build_window` 默认路 `mismatches == []`） |
| ④ rc 语义未动，两条线仍全 FAIL | 三窗 CLI `退出码：0 ｜ 账全：逐枚与 R631 对得上、母集＝账本、每条归因有凭据（这不等于判据②翻绿）`；`EXIT_CODE_MEANING` 一字未动。r631 现跑（`scripts/r631_stage_sum_delta.py --window run20k`）= **rc 1**，`< 1.0%`：FAIL、`< 0.03%`：FAIL，FAIL 名册仍含 `doc-04 发1/2, doc-04 发2/2`（一发一判，谁也不替谁过线） |

## 5. 发级账与母集切分的改前后对账（三窗，本席现取）

| 窗 | sidecar 行 → 发 → 落到的 trace | 同题多发的题号 | 母集四格（declared／asked／no_denominator／resumed_head／bare） | `reference_gap` | r636 CLI rc |
| --- | --- | --- | --- | --- | --- |
| run18 | 105 → 105 → 124 | 无 | 144／105／20／19／0 | rows 105、skipped 20、两差皆 0 | 0（改前也是 0） |
| run19 | 105 → 105 → 124 | 无 | 143／105／19／19／0 | rows 105、skipped 19、两差皆 0 | 0（改前也是 0） |
| run20k | 106 → 106 → 125 | `doc-04`: 2 发 | 144／106／19／19／0 | rows 106、skipped 19、两差皆 0 | **0（改前 1 = MISMATCH）** |

- 身份分布：三窗全部 `sidecar_ts_to_frames_session`（帧账 `ts` 桥），`unattributed` = 0 发、`no_positive_span` = 0 发。
- run20k／`doc-04` 发级跨度：27244.6／27490.9 ms，`spread_ms` = 246.3 = 最小一发的 0.904%（判据线 1.0% 的 0.904 倍）——
  这笔差就是折叠一次能从分母上抹掉的量，与 `r631_stage_sum_delta.py::shot_spreads` 同一笔读数。
- 四格枚数改前后逐项相等 ⇒ 本单没动母集切分；改前 run20k 那句 `MismatchError` 是在四格已对之后才抛的（`UniverseError` 那道闸没被绕，也无需绕）。

## 6. 两态数字（同名件，逐枚同数同名）

- state①＝本树 apply 未 commit；state②＝`git -C C:\Users\fengx\PycharmProjects\企业智脑 worktree add --detach %TEMP%\r647_state2 28d1ea4`
  的干净检出（建后 `status --porcelain` 为 0 枚）＋ **只投本单两枚货**（`scripts/r636_stage_coverage.py` 覆盖 ＋
  `tests/test_r647_shot_denominators_are_per_shot.py` 新文件），`.venv` 挂主树 venv 的 Junction。
- 跑法（两态同一命令，只用各树自己的 venv 解释器；系统 python 是 anaconda，用了就是假绿）：
  `.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r636_stage_coverage.py tests/test_r647_shot_denominators_are_per_shot.py`

| 件 | state① | state② |
| --- | --- | --- |
| `tests/test_r636_stage_coverage.py` | **31 passed / 0 failed / 6.34 s** | 同名 31 枚在合跑内 |
| `tests/test_r647_shot_denominators_are_per_shot.py` | **14 passed / 0 failed / 8.37 s** | 同名 14 枚在合跑内 |
| 两件合跑（同一命令） | **45 passed / 0 failed / 14.43 s** | **45 passed / 0 failed / 23.50 s** |
| 邻件 `tests/test_r643_shot_denominator.py`（不参与本单判语） | 1 failed / 28 passed / 8.10 s | 1 failed / 28 passed / 9.03 s |

- 两态总枚数相同：**是（45 = 45）**；红：**两态各 0 枚** ⇒「红必须逐枚同名」在本单是空集；邻件那枚红两态同名同数一枚：见 §8。
- 用时不参与判语（同一枚解释器、同一台机器；state② 走影子树偏慢）。
- 🔴 state② 的取法照在册教训：**不用 `git archive`**（那棵树没有 `.git`，本族件全靠 `git show` 取历史版，实测 20 枚假红）。
- 临时检出 `%TEMP%\r647_state2` **留在原地未删**，交总控处置。

## 7. 写域与零越界（收席那一刻现取）

- `git -C be-r647 status --porcelain`（收席那一刻现取）只有三行，全在写域之内：
  ` M scripts/r636_stage_coverage.py`／`?? tests/test_r647_shot_denominators_are_per_shot.py`／
  `?? docs/testing/r647-r636-shot-denominators-2026-10-04.md`
  （`tests/test_r636_stage_coverage.py` **未改一字** —— 判据① 要求总数 31 不变，加牙会挪走那把尺的户口，故新牙全落 `tests/test_r647_*.py`）。
- 零提交现取：`git rev-list --count 28d1ea4..HEAD` = **0**；`git diff --numstat HEAD` = `80 16  scripts/r636_stage_coverage.py`。
  本席未 add／commit／建分支／push，并树与提交由总控代做。
- 编码与 EOL 现校（`core.autocrlf=true`，本树工作副本惯例是 CRLF）：三枚文件 BOM=False、LF-only=0、
  `0x00/07/08/0b/0c` 枚数各 0；CRLF 枚数 = r636 件 1460、r647 件 281、本纸 145。
  反引号枚数 = 52／0／344（全成对，没有一枚被命令通道啃成 FF／BEL／CR）。
  EOL 归一前后 `git diff --numstat HEAD` 都是 `80 16` ⇒ 提交后 blob 仍 LF，没出现「整本文件重写」的假账。

## 8. 🔴 写域外连带账（本席不治、不改判语、不加豁免，交总控另落一格）

- 红名一枚：`tests/test_r643_shot_denominator.py::test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator`。
- 红因（现取）：那枚牙把「R643 并树后 r636 **仍然红**」当成判据钉住（`pytest.raises(coverage.MismatchError)` 现报 `DID NOT RAISE`）。
  本单正是来摘这枚已知红的 ⇒ 它必须跟着升格。本席写域不含该件，一字未动。
- 建议处置（由总控裁）：把那格翻成「`build_window` 逐枚对得上 ＋ `fold_legacy` 才红」，或直接由
  `tests/test_r647_shot_denominators_are_per_shot.py::test_real_run20k_goes_red_when_the_shots_are_folded` 承接后删该格。
- 影响面：这枚红**在**全量回归门里（它不是 skip 件，真窗导出件在位）。⇒ 门在 R647 并完之后仍会红这一枚，除非同一笔并树里把 §8 那格一起升格。
- 本单之外无新增红：`tests/test_r636_stage_coverage.py` 与 `tests/test_r647_shot_denominators_are_per_shot.py` 两态共 45 枚全绿。

## 9. 本单新增牙名册（14 枚，逐枚点名）

| # | 牙 | 咬什么 |
| --- | --- | --- |
| 1 | `test_two_shots_of_one_question_get_two_denominators` | 合成窗同题两发各得一枚分母（1,000／1,500），两值不许相等，`mismatches == []` |
| 2 | `test_every_denominator_equals_the_r631_shot_reading` | 逐枚等于 `r631_stage_sum_delta.py::collect` 的发级读数（`end_to_end_ms` 与 `error_pct` 都对） |
| 3 | `test_denominators_never_average_or_take_the_max` | 不许平均（1,250）、不许取最大顶替、键空间必须是 trace_id |
| 4 | `test_read_inputs_names_the_multi_shot_question` | 发级账抬头：`keyed=trace`、枚数、`multi_shot_questions`、`spreads` 与 `发1/2 发2/2` 名册、未归名 0 |
| 5 | `test_universe_split_is_still_the_four_groups` | 本单不动母集四格（asked 3／其余 0） |
| 6 | `test_folding_shots_back_to_one_denominator_goes_red` | 🔴 判据③主牙：折回一枚分母 ⇒ 当场 `MismatchError`，并点名 `t-04-a`／`end_to_end_ms`／`error_pct`／两个数；配默认绿正控 |
| 7 | `test_the_fold_knife_really_folds` | 反控：`fold_legacy` 必须真把两发折成一枚（否则第 6 枚的红就不是折叠咬的），且 `legacy_conflicts` 有账 |
| 8 | `test_render_prints_the_shot_leg` | 印面写明按发取、同题多发的题号，并继续 declare 不判绿（不出现 ：PASS／：FAIL） |
| 9 | `test_render_flags_the_folded_view` | 折叠复现时印面必须留名（🔴 折叠视图复现中） |
| 10 | `test_r636_no_longer_reads_the_folded_view` | AST 现读：`r636_stage_coverage.py` 里一枚 `read_sidecar` 引用都没有，`read_sidecar_shots`／`read_frames_shots`／`trace_sessions_from_events`／`_build_shot_leg` 四枚都在；影子端正控（同一段老形状源码喂进去必被认出，且 `read_sidecar_shots` 不误判成 `read_sidecar`） |
| 11 | `test_r631_still_owns_the_folded_view` | 禁区反证：折叠视图仍在 r631 那件里（`keyed=question`、`duplicates` 点名 doc-04），本单没顺手删对照 |
| 12 | `test_real_run20k_doc04_keeps_both_shot_denominators` | 真窗原形状：doc-04 两行同时摆 27,244.6 与 27,490.9，逐枚等于 r631 读数；**不抄 trace_id 字面**（这族病就是手抄坐标） |
| 13 | `test_real_run20k_goes_red_when_the_shots_are_folded` | 真窗折叠 ⇒ 红句里同时出现 27490.9 与 27244.6（事故原读数复现） |
| 14 | `test_real_windows_still_do_not_pass_the_gate` | 判据④：三窗账全（rc=0 那句），两条线仍 FAIL（`r631_stage_sum_delta.py::decide_rc` 非 `RC_OK`，且 FAIL 枚数 == 母集枚数） |

牙不吃盘面状态：14 枚里没有一枚把「此刻 dirty／盘上字节 == HEAD blob」当判据（同族事故 #96／#107／#113）。
12／13／14 三枚走 `skipif`（`%TEMP%\evalrun` 三本导出件不在位即 skip，不改判语）；1–11 枚全合成，环境无关。

## 10. 跑法原文（复算用）

```
cd C:\Users\fengx\PycharmProjects\be-r647
.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r636_stage_coverage.py tests/test_r647_shot_denominators_are_per_shot.py
.\.venv\Scripts\python.exe -m pytest -p no:randomly -q tests/test_r643_shot_denominator.py
.\.venv\Scripts\python.exe scripts/r636_stage_coverage.py --window run18 --window run19 --window run20k
.\.venv\Scripts\python.exe scripts/r631_stage_sum_delta.py --window run20k
```

## 11. 与在册纸的关系（本席不改别人的一行）

- `docs/testing/r636-stage-coverage-2026-10-04.md` 里那格「两行都吃同一枚分母 27490.9／27490.9」自本单起是**改前账**；
  `docs/perf/r631-stage-sum-delta-2026-10-04.md` 末格那句「由 R647 承接」本单已交。两纸都在别人写域，本席一字未动，请总控升格。
