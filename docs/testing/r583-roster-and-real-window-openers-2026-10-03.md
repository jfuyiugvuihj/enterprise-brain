# R583 · 开窗器名册与真实开窗者脱节（甲案落地 · 凭据纸）

单号 R583｜执行层｜树 `C:\Users\fengx\PycharmProjects\be-r583`｜基点 `1b0534a`（detached，未 commit）
判据全文＝派工词四格。总控裁定走**甲案**（进册 + 同步枚数钉 + 改掉旧解释），本纸不含选择过程。
🔴 以下所有数字都是**执行层自报**，总控在主树亲跑的那一遍不算在本纸里。跑测一律串行 `-q -o addopts=
-p no:cacheprovider`，零 `run_gate.py`、零 `-n`、零容器写、零模型、零 commit、零 push。解释器
`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`。

## 0. 盘面（现取）

```
$ git rev-parse HEAD      -> 1b0534a9a3825f69de833ff4987436f2154127b9
$ git status --porcelain  ->  M tests/_temp_edit_overlay.py
                             M tests/test_r466_mutation_does_not_leak_into_live_module.py
                             ?? tests/test_r583_roster_reconciles_the_inventory.py
                             ?? tests/test_r583_window_inventory.py
                             ?? docs/testing/r583-roster-and-real-window-openers-2026-10-03.md
$ git diff --numstat 1b0534a -> 5 1 tests/_temp_edit_overlay.py
                               210 24 tests/test_r466_mutation_does_not_leak_into_live_module.py
```

sha256 前 12（盘上现字节）：

| 文件 | sha256[:12] | 形制 |
|---|---|---|
| `tests/test_r583_window_inventory.py`（新·派生真源） | `e5fd030f0ed4` | 无 BOM · CRLF 591/591 |
| `tests/test_r583_roster_reconciles_the_inventory.py`（新·对账 + 反证） | `61a88de7b226` | 无 BOM · CRLF 207/207 |
| `tests/test_r466_mutation_does_not_leak_into_live_module.py`（改） | `0ac66a06cfbc` | 无 BOM · CRLF 779/779（基点 `3214a9500824`） |
| `tests/_temp_edit_overlay.py`（改·只动散文） | `f12c2b97ca7c` | 无 BOM · CRLF 275/275（基点 `769ddcca4efd`） |
| `docs/testing/r583-roster-and-real-window-openers-2026-10-03.md`（本纸） | 不自计 | 无 BOM · 单形 CRLF（🔴 自指哈希写下即变，本纸交回时的盘面数以交回消息为准） |

`core.autocrlf = true`：盘上单形 CRLF、入库归 LF，`git diff --numstat` 里没有一枚空白噪声。

## 1. 病（改前现取，不是叙述）

名册在 `tests/test_r466_mutation_does_not_leak_into_live_module.py::WINDOWS`（🔴 **不在**
`tests/_temp_edit_overlay.py`——overlay 只有运行时 `_WINDOWS` 登记表），改前 9 行；在册钉把它钉成
「恰等于那 9 枚」。拿基点那本文本喂今天的派生清单，缺的就是 7 枚：

```
改前名册 9 行 vs 派生 16 枚 -> missing:
  tests/test_r253_shadow_root_holds_the_mutation.py          <- R572（并树 6a2c09b）接的第二扇窗
  tests/test_r303_pg_upsert_leg.py                            （复用 r303 的把手与窗类）
  tests/test_r472_h13_closed_wording.py                       <- R556 迁进 install_mutation
  tests/test_r478_no_closed_gate_as_placeholder.py            <- 同上
  tests/test_r48_headline_never_enters_the_text_ledger.py     （复用 r48 的把手与窗类）
  tests/test_r495_session_owner_namespace_is_declared.py       <- 同上
  tests/test_r497_session_list_read_leg.py                     <- 同上
  extra: []   registered_count=9  derived_count=16
```

写死枚数的钉会**主动阻止**后来者进册——谁进册谁就得同时改钉，于是没人改。这就是脱节的机制。

## 2. 判据 ① — 现取所有真开窗者，沿 AST 派生（零手抄）

复用在册真源：`tests/test_r253_no_test_rewrites_a_tracked_file.py` 的 `suite_sources()`（输入面）
＋ `window_handles()`（34 枚把手）＋ `called_handles()`（交叉核对）。细口径落在新件
`tests/test_r583_window_inventory.py`：窗 = `ShadowEdit` 传递子类；开窗点 = 构造窗或调用会构造窗的
把手（沿调用图传递，**用例本体不作把手**，与在册真源同口径）；装变异腿 = 开窗点体内对
`r466.install_mutation` 的调用；LIVE = 第一参数解析到 `overlay.module_of(...)` 或顶层 import 的活模块。

实取读数（执行层自报）：

```
[r583] 判据① 派生：LIVE 16 枚 · 隔离腿 1 枚 · 只开窗不装变异 6 枚 · 窗类 24 枚
[r583] 四族枚数 live=16 isolated=1 exec=2 no_install=6；直接构造窗的 23 枚家全部落族
[r583] 在册真源派生把手 34 枚；本件开窗者 23 枚全部落在其射程内
```

开窗总家 25 = live 16 + isolated 1 + exec 2 + no_install 6；另 2 枚（`test_r303_pg_upsert_leg`／
`test_r48_headline_never_enters_the_text_ledger`）只经 import 进来的把手开窗，不落「直接构造」那一档。

## 3. 判据 ② — 名册与派生清单逐枚对账

改后（盘上名册 16 行 vs 派生 16 枚）：`missing: []`、`extra: []`、`registered_count=16`、
`derived_count=16`。逐枚如下（`式`＝派生给出的进册理由）：

| 开窗者的家 | 名册 key | 窗类@定义件 | 式 |
|---|---|---|---|
| tests/test_r253_shadow_root_holds_the_mutation.py | r253 | _TempEdit@r156;_TempEdit@r48_card | 甲式 |
| tests/test_r303_notification_pins.py | r303 | _R303Edit@r303_notification_pins | 甲式 |
| tests/test_r303_pg_upsert_leg.py | r303-pg | _R303Edit@r303_notification_pins | 甲式 |
| tests/test_r310_owner_lookup_cost.py | r310 | _R310Edit@r310 | 甲式 |
| tests/test_r337_owner_receipt_cost_and_knives.py | r337 | _R337Edit@r337 | 甲式 |
| tests/test_r353_degradation_note_caps_reason_classes.py | r353 | _R353Edit@r353 | 甲式 |
| tests/test_r354_delete_audit_shares_the_owner_reader.py | r354 | _R354Edit@r354 | 甲式 |
| tests/test_r373_the_two_remaining_legs_answer_absence.py | r373 | _R373Edit@r373 | 甲式 |
| tests/test_r381_outlet_answers_the_absent_approval_ledger.py | r381 | _R381Edit@r381 | 甲式 |
| tests/test_r388_read_leg_answers_absence.py | r388 | _R388Edit@r388 | 甲式 |
| tests/test_r472_h13_closed_wording.py | r472 | _ShadowWordEdit@r472 | 甲式 |
| tests/test_r478_no_closed_gate_as_placeholder.py | r478 | _SpanEdit@r478 | 甲式 |
| tests/test_r48_headline_card_lands_on_the_wire.py | r48 | _TempEdit@r48_card | 甲式 |
| tests/test_r48_headline_never_enters_the_text_ledger.py | r48-ledger | _TempEdit@r48_card | 甲式 |
| tests/test_r495_session_owner_namespace_is_declared.py | r495 | _Knife@r495 | 乙式 |
| tests/test_r497_session_list_read_leg.py | r497 | _R497Edit@r497 | 甲式 |

三族**不进册**的照实点名（不许静默失踪，由 `test_the_families_outside_the_roster_are_named_not_lost`
逐枚交回）：

| 族 | 家 | 为什么不进册 | 看管人 |
|---|---|---|---|
| isolated | `test_r499_the_ownership_predicate_survives_any_file_order.py` | 腿走 `_load_view()` 现造的隔离副本 | R583 派生点名 |
| exec | `test_r482_registered_ceiling_is_the_ceiling.py::_ClampEdit` | 旧 `execs_module` 姿势，越界不迁 | `test_r556_window_posture_is_installed_not_executed.py` |
| exec | `test_r553_counter_evidence_teeth.py::_Probe` | 它量的就是 exec 姿势本身 | 同上 |
| no_install | `test_r156` / `test_r457` / `test_r467_classification_default` / `test_r467_delivery_gate` / `test_r508` / `test_r516`（6 枚） | 只开窗落影子根，从不往活模块装变异 | R583 派生点名 |

补齐名册带来一处**尺子**的活要一起做：三扇窗的刀落在模块级字面值上（`DEFERRED_CODES`／
`MAX_CLEARANCE_NOTE`／`USER_LOOKUP_COLUMNS`），而 `live_view` 只收带码体的那几枚（R553 甲腿原话）。
所以本件新加 `literal_bindings()` 与出窗那格 `stuck_values`——先让尺子能量常量腿，否则进册即假红。
🔴 `live_view` 本体一枚没放宽。

## 4. 判据 ③ — 枚数钉与真实枚数同数 + 旧解释改掉

钉名改掉枚数，判据改成吃派生读数（下面那两把刀驱动的就是同一枚本体）：

```
改前 L431  def test_the_roster_is_nine_windows_and_none_of_them_execs_the_live_module():
改前 L432      """R466 的九扇在册 + R556 的名单清空：`execs_module is True` 这一族今天必须是空集。
改后 L573  def test_the_roster_is_the_windows_that_install_on_a_live_module():
改后 L574      """R583 甲案：名册＝派生清单点名的那本账，枚数由派生给；`execs_module` 那一族仍是空集。
```

🔴 旧钉名在树上**没有代码引用者**（基点现取：`git grep -n test_the_roster_is_nine_windows 1b0534a` 只命中这枚钉自己的 `def` 那一行 ＋ `docs/handoff` 里三段历史叙述/派工词），改名安全；R466 当年那句「不许摘，只许按名单清空改写并留一枚名单不许反弹的牙」也照办了——钉没摘，反弹那格原样留着。
`docs/handoff/**` 属历史记录、不在写域，本单一字未动。

overlay 文件头那句陈旧枚数口径一并改掉（只动散文，行为零改）：

```
改前 L20  报错原文的措辞全部留在调用方那两枚 ``_TempEdit`` 子类里——摘掉守卫会红的那一格，改完还在同一格红。
改后 L20  报错原文的措辞全部留在调用方那些 ``ShadowEdit`` 子类里——摘掉守卫会红的那一格，改完还在同一格红。
改后 L21-24  🔴 R583：本件不登记「谁开了窗」，也不写枚数——开窗者逐枚点名在派生清单
          ``tests/test_r583_window_inventory.py``（沿 AST）与名册
          ``tests/test_r466_mutation_does_not_leak_into_live_module.py::WINDOWS`` 那本账里。
          这里的散文若再出现「那两枚／那九枚」这类账面枚数，就是给下一班撒完的假账。
```

同数读数（执行层自报）：

```
[r583] 名册 16 枚 = 派生 LIVE 16 枚；不进册三族 isolated=1 exec=2 no_install=6；execs_module 空集 · 姿势逐枚 shadow_swap
[r583] 判据③ 名册 16 行 = 派生 LIVE 16 枚（旧账 9 枚）· 钉名已改口 · 旧解释已作废
```

留着的那三格下限原样未放松：R466 那 9 枚不许反弹、`execs_module is True` 仍须空集、`posture`
逐枚仍须 `shadow_swap` 且与真读数一致。

🔴 **照实交回一处**：派生清单里唯一一枚写死的名字表是 `test_r583_window_inventory.HISTORICAL_NINE`
（R466 那 9 枚的 rel 路径），它是**下限锚**而不是名册的来源——名册枚数与成员全部由 `inventory()` 派生，
这 9 枚只用来拦「名单反弹」。今天它同时被两格量着：`test_the_inventory_is_derived_and_keeps_the_historical_nine`
（派生认得出这 9 枚）与对账本体里那句「R466 那 9 枚里有 %s 离开了名册」。谁要再加一枚窗，仍不必动这枚常量。

## 5. 判据 ④ — 反证两把（只摘输入面，盘上全程只读）

**刀一 · 新增一扇不进册的窗必须红**：往输入面塞一枚合成件
`tests/test_r583_injected_second_window.py`（真开 `ShadowEdit` 子类、真把变异装到
`overlay.module_of("app/api/v1/chat.py")` 的活模块上），名册不动 ⇒ 派生 17 枚、名册 16 行，
红在「没进册」并逐枚点名那一家。

```
摘前 输入面 sha256[:12] = 5c07229015f9（LIVE 16）
摘后 输入面 sha256[:12] = edb6a712aadd（LIVE 17）
盘上名册 sha16           = d75aaacf3f46d54d 未变（摘前摘后各读一次，逐字节相等）
```

**刀二 · 把名册里一枚真删掉必须红**（两面同删：文本面剪掉那枚 dict 字面量 + 活对象去掉该行）：

```
名册文本 摘前 sha12 = d75aaacf3f46
删 r472   摘后 sha12 = 88cbe221fc39（15 行）-> 红在「没进册」
删 r310   摘后 sha12 = c622596c8765（15 行）-> 红在「名单不许反弹」
盘上名册 sha16      = d75aaacf3f46d54d 未变
```

补一刀（形状牙）：只剪文本面、活对象不动 ⇒ 红在「只改了其中一面」（`88cbe221fc39`）。
这一格挡的是账面与对象再度分叉——正是本单那枚病的另一种发作形状。

## 6. 命令原文 → rc → 末行读数（执行层自报）

```
$ python -X utf8 -m pytest tests/test_r583_roster_reconciles_the_inventory.py \
    -o addopts= -p no:cacheprovider --basetemp=$TEMP/r583bt -q -s
  rc=0   5 passed, 3 warnings in 6.54s

$ python -X utf8 -m pytest tests/test_r583_window_inventory.py \
    tests/test_r583_roster_reconciles_the_inventory.py \
    tests/test_r466_mutation_does_not_leak_into_live_module.py \
    -o addopts= -p no:cacheprovider --basetemp=$TEMP/r583bt -q --tb=short
  rc=0   29 passed, 12 warnings in 38.65s        （= 派生 4 + 对账/反证 5 + r466 20）

$ python -X utf8 -m pytest tests/test_r115_doc_content_limit_is_single_source.py \
    tests/test_deployment_guards.py \
    -o addopts= -p no:cacheprovider --basetemp=$TEMP/r583bt -q --tb=line
  rc=0   31 passed, 8 warnings in 9.68s          （新增文件不犯在册的全盘扫描钉）

# 正序 16 件点名集
$ python -X utf8 -m pytest tests/test_r583_window_inventory.py \
    tests/test_r583_roster_reconciles_the_inventory.py \
    tests/test_r466_mutation_does_not_leak_into_live_module.py \
    tests/test_r48_headline_card_lands_on_the_wire.py \
    tests/test_r48_headline_never_enters_the_text_ledger.py \
    tests/test_r253_shadow_root_holds_the_mutation.py \
    tests/test_r303_notification_pins.py tests/test_r303_pg_upsert_leg.py \
    tests/test_r472_h13_closed_wording.py tests/test_r478_no_closed_gate_as_placeholder.py \
    tests/test_r495_session_owner_namespace_is_declared.py tests/test_r497_session_list_read_leg.py \
    tests/test_r556_window_posture_is_installed_not_executed.py \
    tests/test_r572_window_handles_are_derived_not_transcribed.py \
    tests/test_r572_the_migrated_window_still_has_teeth.py \
    tests/test_r253_no_test_rewrites_a_tracked_file.py \
    -o addopts= -p no:cacheprovider --basetemp=$TEMP/r583btF -q --tb=line
  rc=0   172 passed, 66 warnings in 228.38s

# 反序同名件（逐枚倒过来交）
$ python -X utf8 -m pytest <同上 16 件反序> \
    -o addopts= -p no:cacheprovider --basetemp=$TEMP/r583btR -q --tb=line
  rc=0   172 passed, 64 warnings in 221.25s
```

两向**同数**：172 = 172。同名 16 件的点名集本席跑过**两对**（每对都正序＋反序各一遍）：
第一对 `172 passed in 140.04s`（正）／`172 passed in 127.79s`（反）未带 `rc` 落纸，第二对就是上面带 `rc=0` 的那两行。外加一枚只跑三件核对的 `29 passed in 38.65s`、一枚只跑反证件的 `5 passed in 6.54s`，与一把横扫 `tests/test_r302_docs_utf8_guard.py tests/test_r115_doc_content_limit_is_single_source.py tests/test_deployment_guards.py` 的 `68 passed in 45.36s`（rc=0，证明新增两枚在册件不犯全盘扫描类钉）。

## 7. 未验格 · 照实

- 🔴 **未跑全量门**：本单明令禁 `scripts/run_gate.py`，所以「并树后全库绿」不在本纸凭据里，
  交总控在主树复跑（并树第二遍按规矩要在干净树复跑同名件）。
- **派生口径的射程是文本**：判据 ① 认的是「源码里真开窗真装变异」，动态 getattr／exec 造出来的
  窗认不到。三族里若藏着一枚动态开法，本件会把它落进 `no_install` 并逐枚点名，不会静默失踪。
- 🔴 **反证两把只演了「缺册」与「删行」两个方向**：对账本体里那句「名册里这些行在派生清单里找不到对应的活模块窗」（`extra`）今天**没有单独一刀**——它是被 §5 刀一的同一次调用顺路带着的（派生 17 枚 / 名册 16 行时，`extra` 为空、红只可能来自 `missing`）。要拿它拦人，得再加一枚「在册行指向一枚不装变异的窗」的合成件；本单写域没这枚，照实记成一格欠牙，不谎称四格满贯。
- **合成件只活在输入面**：`tests/test_r583_injected_second_window.py` 不落盘（本纸交回前后
  `Test-Path` 为假），所以它不进今天的派生清单；这既是「反证只摘输入面」的纪律，也意味着刀一
  量的是「判据认不认得这形状」，不是「盘上真多了一枚窗」。
- `isolated`／`exec_posture` 两族的看管交接不在本单写域：r482／r553 那两枚 exec 窗今天仍由
  R556 那枚钉登记，本单只保证它们不被塞进 LIVE 名册。
- 枚数 16 是**今天这棵树的派生读数**，不是新的账面常量：下一次谁再接进 `install_mutation`，
  钉会先要求进册、枚数自动跟上，不许再来改一个数字。