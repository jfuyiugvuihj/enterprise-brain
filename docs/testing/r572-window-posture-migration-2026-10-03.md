# R572 · r253 一族补迁到在册姿势 ＋ 引用者钉改吃派生名（凭据纸）

单号 R572｜执行层 `Kuhn`｜树 `C:\Users\fengx\PycharmProjects\be-r572`｜基点 `fd90f30`（分支 `codex/be-r572`）
判据全文＝跟进单 §151 三。以下每一条数字都是**执行层自报**，命令原文一并附在格子旁边；
总控在主树亲跑的那一遍不算在本纸里。跑测一律串行 `-q -o addopts= -p no:randomly`，
零 `run_gate.py`、零 `-n`、零容器、零模型、零 commit、零 push。解释器
`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`，工作目录写绝对路径。

## 0. 盘面（现取）

```
$ git -C be-r572 rev-parse --short HEAD          -> fd90f30
$ git -C be-r572 status --porcelain              -> 见 §7（四枚写域文件 + 本纸，一枚不多）
$ git -C be-r572 diff --numstat HEAD             -> 见 §7
```

🔴 **一处例外，主动报备**：改前那轮复现（§1 的 pair run）里 ② 那格半途失败，R53 留下一枚
chroma sandbox，把被跟踪的 `chroma_db/chroma.sqlite3` 顶脏了（字节数不变、内容变）。本单四枚
写域文件一枚都不是它。处置：`git -C be-r572 checkout -- chroma_db/chroma.sqlite3` 还回
HEAD blob（`be3674cd43ec4d46e9bae6dfc9a65a9dbdcae2c2`）。还回之后改后的每一轮点名集复跑
（§3 的 4 轮）`git status --porcelain` 里都不再出现 chroma 条目——**这枚脏是「症状② 半途失败」的
后果，不是本单改动的后果**，这本身也是症状② 的一条旁证。

## 1. 病与四枚症状（改前现取）

| # | 命令原文 | 末行读数（改前） |
|---|---|---|
| 复现 A | `python -X utf8 -m pytest tests/test_r253_shadow_root_holds_the_mutation.py tests/test_r253_no_test_rewrites_a_tracked_file.py -q -o addopts= -p no:randomly` | `2 failed, 13 passed, 10 warnings, 1 error in 21.89s`（另一次 26.15s，同数） |
| 症状① | 同上，`--tb=short` | `tests/test_r253_no_test_rewrites_a_tracked_file.py:507: AssertionError: tests/test_r48_headline_never_enters_the_text_ledger.py 里已经没有 _TempEdit 了` |
| 症状② | 同上 | `tests\test_r253_shadow_root_holds_the_mutation.py:121: assert 'fabricated_note' in {...}` ⇒ `影子字节没被执行：判据 ③ 掉了` |
| 症状③ | `python -X utf8 -m pytest tests/test_r253_shadow_root_holds_the_mutation.py::test_install_source_swaps_the_bytes_not_the_module_object -q -o addopts= -p no:randomly --tb=line` | `1 passed, 1 error in 4.22s` |
| 症状④ | `python -X utf8 -m pytest tests/test_r48_headline_card_lands_on_the_wire.py tests/test_phase9_private_deps.py -q -o addopts= -p no:randomly --tb=no` | `21 passed, 4 warnings, 1 error in 12.91s` |

**派工词的两处归因要订正**（本席现取，非叙述）：

1. 症状③④ 不是「② 那扇窗半途失败的泄漏」。摘掉 ②（`--deselect`）③ 照样红；单跑
   `test_install_source_swaps_the_bytes_not_the_module_object` 就出 ERROR（上表症状③ 那行）。
   真凶是那格自己的窗尾：旧写法 `overlay.install_source(chat, 盘上的字, CHAT_PY)` 里那枚
   `compile` 继承 `tests/_temp_edit_overlay.py` 的 `from __future__ import annotations`
   （本席诊断脚本读数：`ask flags 131 -> 16777347`，即多一枚 `CO_FUTURE_ANNOTATIONS`），
   于是"还原"回来的顶层函数是新对象 **加新码体**——conftest 的在册 R563 守卫比的正是码体
   （`ca.co_code == cb.co_code`），把本件的还原判成跨模块的漏。
2. 症状④ 与本单无关：上表最后一行里两枚文件（`test_r48_headline_card_lands_on_the_wire.py`、
   `test_phase9_private_deps.py`）**都不在本单写域**，合跑照样出那枚 ERROR。机理（诊断脚本，
   非产品面）：`importlib.reload(app.api.v1.chat)` 之后 `upload_document.__defaults__`
   是新造的 `File()/Form()` 实例——`code-eq=True` 而 `defaults-eq=False`
   （types `('File','Form','Form','NoneType')`），而 `_eb_r563_same` 第四腿比 `__defaults__ ==`
   ⇒ 只要有任何一枚更早的件把 `app.api.v1.chat` 带进 `sys.modules`，phase9 那格收工就恒漂。
   单跑绿是因为那时基线里还没有 chat（`before` 交不回那一格，比对被跳过）。

## 2. 改了什么（四格，全部只在写域内）

1. `tests/test_r253_shadow_root_holds_the_mutation.py`
   - ② 那扇窗 `_TempEdit(CHAT_PY, ...)` → 借在册开窗器 `_chat_window([...])`
     （＝影子副本落变异 ＋ `r466.install_mutation` 只装变了的那一枚绑定），不抄第二份；
     新增一格 `info.get("installed_bindings") == ["_headline_card_data"]` 钉住"装的是绑定不是整片"。
   - `test_install_source_swaps_the_bytes_not_the_module_object` 窗尾改走骨架自己交回的
     `overlay.restore_namespace(chat, live_before)`（按对象身份倒回，R553 乙腿同一口径），
     并新增两格：`chat.ask is ask_before`（还回原来那一枚）与 `"ask" in diverged`（这一手真在倒回）。
   - 模块 docstring 的 ①③ 两格随之改口（写明牙长在 `install_mutation` 那一腿上）。
2. `tests/test_r253_no_test_rewrites_a_tracked_file.py`
   - 末尾那枚引用者钉的判法：`assert "_TempEdit(" in source` ⇒ `window_handles(sources)` 沿 AST
     从**两枚真源**派生把手名（`tests/_temp_edit_overlay.py` 的公开上下文管理器类 ＋
     `tests/test_r466_...` 的公开 `@contextmanager`），再闭包到「继承骨架的类」与「体内 `with`
     调到已认把手的顶层函数」。派生不到 ⇒ 红；射程内某枚件不再调用任何把手 ⇒ 红并指名。
   - 判据本体拆成 `assert_homes_still_ship_their_counter_proofs(sources, handles)`，
     用例只剩一行驱动——反证用的是**同一枚**逻辑，不是第二份判据。
   - 反证件名下限（5/3/1）与扫描口径一枚没放宽。
3. 新钉 `tests/test_r572_window_handles_are_derived_not_transcribed.py`（4 枚用例）。
4. 新钉 `tests/test_r572_the_migrated_window_still_has_teeth.py`（6 枚用例）。
5. 本纸。

## 3. 判据逐格读数（执行层自报）

| 判据 | 命令原文 | 末行读数（改后） |
|---|---|---|
| ① 同名集全跑（正序） | `python -X utf8 -m pytest tests/test_r253_shadow_root_holds_the_mutation.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r572_window_handles_are_derived_not_transcribed.py tests/test_r572_the_migrated_window_still_has_teeth.py tests/test_r466_mutation_does_not_leak_into_live_module.py tests/test_r48_headline_card_lands_on_the_wire.py tests/test_r48_headline_never_enters_the_text_ledger.py tests/test_r303_notification_pins.py tests/test_r310_owner_lookup_cost.py tests/test_r353_degradation_note_caps_reason_classes.py tests/test_r373_the_two_remaining_legs_answer_absence.py tests/test_r563_live_module_callables_do_not_leak.py tests/test_phase9_private_deps.py -q -o addopts= -p no:randomly --tb=no` | `157 passed, 98 warnings, 1 error in 65.32s (0:01:05)` |
| ① 同名集全跑（反序，逐枚倒过来点） | 同上，文件顺序 `[Array]::Reverse` 后传入（13 枚，首 `test_phase9_private_deps.py`、末 `test_r253_shadow_root_holds_the_mutation.py`） | `157 passed, 96 warnings, 1 error in 59.96s`（再早一遍同数：`157 passed, 96 warnings, 1 error in 64.89s`） |
| ① 症状①②③ | 只点两枚改过的件 | `15 passed, 13 warnings in 26.75s`（改前同一条命令：`2 failed, 13 passed, ..., 1 error`） |
| ④ 新钉各自 | `pytest tests/test_r572_window_handles_are_derived_not_transcribed.py` / `pytest tests/test_r572_the_migrated_window_still_has_teeth.py` | `4 passed` / `6 passed` |
| ② | 见 §1 症状② 与 §4 刀一/刀二：迁完 `fabricated_note` 真从影子字节跑出来（`15 passed`），摘掉变异本体或 `install_mutation` 那一腿 ⇒ 同一枚在册钉当场红 | 达标 |
| ③ | `[r572] 派生把手 33 枚；射程内读数：{'tests/test_r156_sse_event_surface_sync.py': (5, ['_TempEdit']), 'tests/test_r48_headline_card_lands_on_the_wire.py': (3, ['_TempEdit', '_chat_window', 'install_mutation']), 'tests/test_r48_headline_never_enters_the_text_ledger.py': (1, ['_chat_window'])}` ＋ §4 刀乙/刀丙/丁 | 达标 |
| ⑤ | 见 §6 | 达标 |
| ①（症状④） | — | **未达**，见 §5 |

同名字段里那枚 `1 error` 全程只有 phase9 一个名字（`ERROR tests/test_phase9_private_deps.py::
TestOptionalPsycopgImports::test_chat_and_alerts_import_without_psycopg`），正序反序同数。

## 4. 反证刀清单（五把，victim 全是 `fd90f30` 上在册的钉）

每把都逐字节核过六枚相关文件的 sha256（摘前＝摘后）。这六枚在末轮现取为：
`chat.py=8969a64ebc249a07`、`_temp_edit_overlay.py=c268be519cdd820c`、
`test_phase9_private_deps.py=f656edb61a17b5cc`、
`test_r253_no_test_rewrites_a_tracked_file.py=0b6e8c042ee82a09`、
`test_r253_shadow_root_holds_the_mutation.py=05a14edcf669be13`、
`test_r466_mutation_does_not_leak_into_live_module.py=308959b3d707d61b`
（打印自 `tests/test_r572_the_migrated_window_still_has_teeth.py::test_a_...` 正控，行内断言
`digests() == before` 才是判据，这里只是把值抄给总控对账）。

| 刀 | victim（在册钉本体） | 摘掉的那一手 | 红了哪一条（当场报错原文） | 所在件 |
|---|---|---|---|---|
| 刀一 | `tests/test_r253_shadow_root_holds_the_mutation.py::test_a_live_counter_evidence_window_opens_no_write_on_the_tracked_file` | 变异本体：`C1_MUTANT` 换成不含 `fabricated_note` 的同形变异（进程内 monkeypatch） | `影子字节没被执行：判据 ③ 掉了` | `tests/test_r572_the_migrated_window_still_has_teeth.py::test_knife_one_neutralising_the_mutation_body_reddens_the_pin` |
| 刀二 | 同一枚 victim | `r466.install_mutation` 那一腿：`_chat_window` 换回裸 `_TempEdit`（今天 `execs_module = False`） | `影子字节没被执行：判据 ③ 掉了` ⇒ 钉住"迁姿势不许迁成没牙" | 同上 `::test_knife_two_dropping_the_install_leg_reddens_the_pin` |
| 刀三 | `tests/test_r253_shadow_root_holds_the_mutation.py::test_install_source_swaps_the_bytes_not_the_module_object` ＋ conftest 的在册 R563 守卫 | 窗尾按身份倒回：`overlay.restore_namespace` 换成空转 | 先红在钉自己（`窗尾没把活模块的顶层值装回进门那一刻…`），守卫再红：`R563：本模块出门把活模块的顶层可调用绑定换成了自己的假身，没还回去。 - app.api.v1.chat._reap_agent_worker…` | `::test_knife_three_dropping_the_identity_restore_leaks_the_live_module`；正控 `::test_the_pinned_install_source_case_leaves_no_drift_behind`（同一条守卫驱动，不红） |
| 刀四 | `tests/test_phase9_private_deps.py::TestOptionalPsycopgImports::test_chat_and_alerts_import_without_psycopg`（症状④ 的形状） | 先照"旧窗尾"造一次漏（`install_source` 只 exec 不还身份），再让那枚在册件照原样 `reload` | `R563：本模块出门把活模块的顶层可调用绑定换成了自己的假身…  - app.api.v1.chat._reap_agent_worker…`（红在 phase9 身上 ⇒ 证明"单跑绿、合跑红"的机理，与本纸 §1 的订正对上） | `::test_knife_four_a_leaked_live_module_reddens_the_next_module` |
| 刀乙 | `tests/test_r253_no_test_rewrites_a_tracked_file.py::test_the_three_pins_this_ticket_moved_still_ship_their_counter_proofs` | 射程内某枚件的把手调用（只摘输入面文本，盘上不动） | `tests/test_r48_headline_never_enters_the_text_ledger.py 里已经没有在册反证窗把手了：从真源派生到 33 枚名字（…），这一枚一件都没被调用` | `tests/test_r572_window_handles_are_derived_not_transcribed.py::test_yi_a_home_that_stops_calling_any_handle_goes_red` |
| 刀丙 | 同一枚 victim | **两枚派生源**一起摘掉 | `从真源（tests/_temp_edit_overlay.py ＋ tests/test_r466_mutation_does_not_leak_into_live_module.py）派生不到任何一枚窗把手名：引用者钉瞎了…` | 同上 `::test_bing_stripping_the_derivation_sources_goes_red` |
| 刀丁 | 同一枚 victim（合成件正控） | 换一份名字全是现编的输入面（`ZephyrWindow`／`fit_mutation`／`_zed_window_*`），再把合成件的开窗摘掉 | 认得出：`assert_homes…` 交回三枚读数；摘掉后红在 `tests/test_r156_sse_event_surface_sync.py 里已经没有在册反证窗把手了：从真源派生到 2 枚名字（ZephyrWindow, fit_mutation）…` ⇒ 判据吃的是派生，不是手抄名单 | 同上 `::test_ding_a_synthetic_corpus_with_invented_names_is_still_recognised` |

七把（≥3 已满足）。每把都有同件内的正控配对：刀一/刀二 ↔ `test_a_the_migrated_window_passes_before_any_knife`；
刀三 ↔ `test_the_pinned_install_source_case_leaves_no_drift_behind`；刀乙丙丁 ↔
`test_jia_the_derived_set_names_both_postures_and_stops_at_the_window`。

## 5. 未达的格子（不洗绿）

**判据① 的第 4 枚症状：未达。** 差的确切条件：
`tests/test_phase9_private_deps.py::TestOptionalPsycopgImports::test_phase9…` 的收工 ERROR
在同名集全跑里仍然存在（正序反序都在，`157 passed / 1 error`）。它不在本单写域里，本席也没法
在写域内治它——治法只有两处，都在禁碰清单上：
`tests/conftest.py` 的 `_eb_r563_same` 第四腿（拿 `__defaults__ ==` 比 FastAPI 的 `File()/Form()`
实例，`importlib.reload` 之后恒不等），或 `tests/test_phase9_private_deps.py` 自己在用例尾
`reload` 回去／改走 `monkeypatch`。请总控裁：① 把其中一枚开一格写域给本席，或 ② 另立单
（本席建议另立单，这条属 R563 §145 那一族的尺子过窄，与 r253 姿势无关）。
本席按派工词只做了一件：把它从"疑似本单泄漏"里摘出来，给了可复现的最小证（§1 症状④ 那行）。

现取原文（同一枚最小证，`--tb=long`，`21 passed, 4 warnings, 1 error in 13.01s`）：

```
R563：本模块出门把活模块的顶层可调用绑定换成了自己的假身，没还回去。
  - app.api.v1.chat.upload_document：盘上那一版 app.api.v1.chat.upload_document 被换成 app.api.v1.chat.upload_document
活模块已还回基线（下一模块不再当受害者），但红必须留在本模块自己身上：
```

漂移名单里**只有 `upload_document` 一枚**——这与症状③ 那枚「窗尾泄漏」的签名不同（后者一次点名
五枚：`_reap_agent_worker`／`_authorize_queue_task`／`ask`／`approve`／`upload_document`，
见本纸 §1 改前 pair run 的 teardown 原文）。两枚签名不同＝两回事：前者是 `__defaults__` 里
`File()/Form()` 的实例身份，后者是码体被未来标志换过。本单治掉了后者，前者不在写域。

其余三枚症状：达标（§3）。**未验的格子（明写「没跑」，不写成「跑了没过」）**：
`-n` 并行下的共置（本单一律串行）；全量门（禁跑，归总控）；干净树 commit 后复跑（本席无 commit
权，那一遍归总控）。

## 6. 行尾纪律（判据⑤）

```
$ git -C be-r572 ls-files --eol -- <四枚在册邻件/两枚改口件>
i/lf    w/crlf  attr/    tests/test_r253_no_test_rewrites_a_tracked_file.py
i/lf    w/crlf  attr/    tests/test_r253_shadow_root_holds_the_mutation.py
i/lf    w/crlf  attr/    tests/_temp_edit_overlay.py            （未动，只派生）
i/lf    w/crlf  attr/    tests/test_r466_mutation_does_not_leak_into_live_module.py（未动）
i/lf    w/crlf  attr/    tests/test_r48_headline_card_lands_on_the_wire.py        （未动）
i/lf    w/crlf  attr/    tests/test_r48_headline_never_enters_the_text_ledger.py  （未动）
i/lf    w/crlf  attr/    tests/test_r156_sse_event_surface_sync.py                （未动）
i/lf    w/crlf  attr/    tests/test_phase9_private_deps.py                        （未动）
```

三枚新落盘的文件未跟踪，故 `ls-files --eol` 不列；本席在落盘当场按**原始 bytes**判过（先判再写，
不是归一之后回头问）：整档 CRLF、无 BOM、无 lone CR，行数与 crlf 数相等（末轮现取）——

```
tests/test_r572_window_handles_are_derived_not_transcribed.py  lines=157 crlf=157 loneCR=0 bom=False sha=9d1932fa46683868
tests/test_r572_the_migrated_window_still_has_teeth.py         lines=186 crlf=186 loneCR=0 bom=False sha=0536e34fbac6765e
docs/testing/r572-window-posture-migration-2026-10-03.md       lines=174 crlf=174 loneCR=0 bom=False sha=38b2ec8f6058e639
```

两枚改口件同样单形：referrer 670 行 / crlf 670 / sha `0b6e8c042ee82a09`；
shadow 237 行 / crlf 237 / sha `05a14edcf669be13`。`py_compile` rc=0；
`ruff check --select F,E9`（只检这四枚 .py）`All checks passed!` rc=0。

## 7. 盘面读数（末轮现取）

见交回正文的 `git diff --numstat` 与 `git status --porcelain` 原样粘贴（本纸与它同一次取数）。

## 8. 待总控复跑的命令原文

```
# 同名集（dirty 态；本席已跑，两向同数）
python -X utf8 -m pytest tests/test_r253_shadow_root_holds_the_mutation.py \
  tests/test_r253_no_test_rewrites_a_tracked_file.py \
  tests/test_r572_window_handles_are_derived_not_transcribed.py \
  tests/test_r572_the_migrated_window_still_has_teeth.py \
  tests/test_r466_mutation_does_not_leak_into_live_module.py \
  tests/test_r48_headline_card_lands_on_the_wire.py \
  tests/test_r48_headline_never_enters_the_text_ledger.py \
  tests/test_r303_notification_pins.py tests/test_r310_owner_lookup_cost.py \
  tests/test_r353_degradation_note_caps_reason_classes.py \
  tests/test_r373_the_two_remaining_legs_answer_absence.py \
  tests/test_r563_live_module_callables_do_not_leak.py \
  tests/test_phase9_private_deps.py -q -o addopts= -p no:randomly
# 症状④ 的独立最小证（两枚都不是本单写域）
python -X utf8 -m pytest tests/test_r48_headline_card_lands_on_the_wire.py \
  tests/test_phase9_private_deps.py -q -o addopts= -p no:randomly
# commit 后的干净树那一遍（本席无 commit 权，未跑）
```