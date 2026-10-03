# R589｜射程内测试件集合不许把解析不了的文件静默跳过（凭据纸）

- 单号 **R589**（跟进单 §157 二）· 执行层席 · 工作树 `C:\Users\fengx\PycharmProjects\be-r589` · 基点 **`245315b`**（起线 dirty=0）
- 写域逐枚：`tests/_temp_edit_overlay.py`（该族派生器，新增 R589 段）＋ `tests/test_r516_the_dataset_stubs_stay_on_the_class.py::_all_rows`（该口径直接服务的射程内派生件）＋ 新钉 `tests/test_r589_unparseable_files_cannot_shrink_the_range.py` ＋ 本纸。
- 禁碰清单逐枚点名，全部一字节未动：`app/**`、`tests/fixtures/business_evaluation_100.jsonl`、`docs/testing/fixtures/r97-shard-*.jsonl`、`tests/test_r253_*`（只读它取证）、`migrations/**`、`chroma_db/**`、`.gitignore`、`frontend/**`、`scripts/`、`docs/handoff/**`。
- 零容器、零模型（8001／11434 未碰）、零起服务、零写库；测试一律 `-o addopts= -p no:cacheprovider --basetemp=%TEMP%\…  -q`，🔴 未跑全量门 `scripts/run_gate.py`（本单禁跑）。

## 1 病与机理

总控现场复现（跟进单 §157 二）：验 R584 时把 13 枚名单集反序跑，第一次 **156 passed／1 failed**，红在
`tests/test_r253_no_test_rewrites_a_tracked_file.py::test_the_three_pins_this_ticket_moved_still_ship_their_counter_proofs`；
当时盘上正有一枚本席自己刚写、带语法错误的 `tests/test_r586_*.py`。把那枚修好，反序复跑 **157 passed／0 error**。

本席在同一枚基点上独立复现（命令原文见 §3.1）：射程内放一枚两行的错件，`tests/test_r253_no_test_rewrites_a_tracked_file.py`
单跑当场 **3 failed / 6 passed**，红字是

```
E   File "<unknown>", line 2
E       module = (:
E             ^
E   SyntaxError: invalid syntax
..\..\anaconda3\Lib\ast.py:50: SyntaxError
```

机理两条，都在盘上现取到实码：

1. **静默缩集**（集合无声少一枚）：射程内「解析失败还继续走」的形状，全族 AST 现量 **1 处**——
   `tests/test_r516_the_dataset_stubs_stay_on_the_class.py::_all_rows:L355`，码体 `except SyntaxError: continue`。
   一枚解析不了的件被摘出集合，它名下的账从此不在射程里，而每一枚在册钉全绿。
2. **红得没法照着改**（把别人的手抖读成一次回归）：`tests/test_r253_no_test_rewrites_a_tracked_file.py:559`
   那手 `ast.parse(text)` 不收 `filename`，抛出去的原文只报 `<unknown>`；同一枚病同时红三格（`suite_sources()`
   被三枚判据各自吃一遍）。下次它会同样把**真漏**读成「不在射程」。

`assert handles` 那一族守卫只在**集合为空**时红：射程从 641 枚缩到 640 枚它一路绿（本钉丙格把这格演成了读数）。

## 2 治法：一枚口径三家用（落在 `tests/_temp_edit_overlay.py` R589 段）

| 把手 | 交回什么 | 挡的是哪一手 |
| --- | --- | --- |
| `in_range_test_paths()` / `in_range_test_rels()` | 射程 = `tests/**.py`（去编译缓存）的唯一枚举口径 | 别处再 `rglob` 一份＝第二份真源，两份一分叉「射程内」就按人各异 |
| `parse_in_range(texts=None)` | `rel -> (文本, AST)`；解析不了 ⇒ **一次红全**，逐枚点名 文件/第几行/第几列/原文/错误类与错误句；`texts` 给了就是合成输入面（盘上不动）；收尾 `set(parsed) == set(texts)` | 静默跳过、以及把不带文件名的原文直接端上去 |
| `describe_parse_failure()` | 单枚失败的一行读数（行列取自 `SyntaxError.lineno/offset`） | 「红是红了，但照着改不了」 |
| `assert_covers_the_range(keys, scope, where)` | 逐枚差集：缺哪枚点名哪枚，并把「哪一枚派生者交回的面」写进红字 | 「集合为空才红」救不了「集合少一枚」 |

新钉 8 格（甲·乙·丙·丁×3·戊·己）＋ `test_r516::_all_rows` 改走该口径。本节不写枚数：射程枚数由
`in_range_test_rels()` 现量（基点 245315b 实测 640 枚，加本钉 641 枚）。

## 3 判据逐格（命令原文 → rc → 读数）

解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`，工作目录 `be-r589`。

### 3.1 改前取证（病在盘上的样子）

```
# 射程内放一枚两行错件（tests/test_zz_r589_probe_broken.py: module = (: ）
python -X utf8 -m pytest tests/test_r253_no_test_rewrites_a_tracked_file.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r589probept -q
rc=1   3 failed, 6 passed in 25.04s
红字：File "<unknown>", line 2 … SyntaxError: invalid syntax（不点名文件）
```

```
# 全族 AST 现取「解析失败还继续走」的形状（起点）
rc=0   HITS 1
tests/test_r516_the_dataset_stubs_stay_on_the_class.py::_all_rows:L355 SyntaxError -> continue
```
（放宽到 `Exception/BaseException/裸 except` 同一条规则再跑一遍，仍只有这一处；`app/**` 那把尺子（`test_r478::_units` 的
`except SyntaxError: tree = None`）射程不是测试件，本单不改，登记在 §8。）

### 3.2 判据①：解析不了 ⇒ 直接红并点名文件与行列

```
python -X utf8 -m pytest tests/test_r589_unparseable_files_cannot_shrink_the_range.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r589pt -q
rc=0   8 passed, 18 warnings in 40.29s        （干净树，甲…己八格全绿）
rc=0   -s 读数：
  [r589] 甲 射程 641 枚全解析 · 严格口径覆盖 extra=0 · R253 派生面覆盖 extra=0 · 口径使用者 3 枚 · 盘上指纹 af7755235632
  [r589] 乙 合成弹药 tests/test_r589_synthetic_piece_that_does_not_parse.py -> 红字点名 第 2 行 第 9 列（invalid syntax）；盘上射程 af7755235632 一枚未动
  [r589] 丙 摘掉 tests/test_upgrade_baseline.py：输入面 641 -> 640 枚（旧那格只看把手非空，仍绿：37 枚把手），逐枚对账红着点名它
  [r589] 戊 射程 641 枚里「解析失败还继续走」的形状 0 处
```
坏件真进射程时（§3.4 第一把刀）红字原文：

```
E   AssertionError: 射程内有 1 枚件解析不了（R589 判据①）：……逐枚点名 文件/行/列/原文/错误：
E     tests/test_zz_r589_probe_broken.py:第 3 行 第 9 列  PROBE = = 2  SyntaxError: invalid syntax
E   判据落点 tests/test_r589_unparseable_files_cannot_shrink_the_range.py，机理与两趟对照读数 docs/testing/r589-…….md
```

丙格是「少一枚」那一半的正面回答：摘掉一枚件之后，`window_handles()` 仍交回 37 枚把手（旧守卫绿），
`assert_covers_the_range` 红并点名那一枚 ⇒ 集合少一枚从此量得到。

### 3.3 判据②：与 R583 那枚名册钉不许互相掩盖

```
python -X utf8 -m pytest tests/test_r589_unparseable_files_cannot_shrink_the_range.py -o addopts= -p no:cacheprovider -q -s
rc=0   -s 读数：
  [r589] 丁② 塞一枚解析不了的件：①红着点名它，②读数一字不变（名册 16 行 = 派生 LIVE 16 枚）
  [r589] 丁② 名册剪掉 key=r253：②红在「没进册」并点名 tests.test_r253_shadow_root_holds_the_mutation；①一枚未动（射程 641 枚全在面上）
  [r589] 丁·结构 两枚本体互不引用（①41 行 / ②24 行源码），词表不相交
  [r589] 己 合法不开窗的合成件落 no_install（8 枚）· LIVE 仍 16 枚 · 名册对账读数不变
```
- 两枚判据各驱动各自的本体：①是 `overlay.parse_in_range`／`assert_covers_the_range`，②是
  `test_r583_window_inventory.assert_roster_matches_the_inventory`。本钉不另造近似判据（R583 同规矩）。
- 互不掩盖是**分别触发**演出来的：塞一枚解析不了的件 ⇒ ①红、②的 `rows/derived/keys/gap` 读数逐字段相等；
  名册剪一行 ⇒ ②红在「没进册」、①对整段射程仍绿且仍覆盖。
- 结构格再钉一层「不许缝成一枚断言」：两枚本体的源码互不引用（`parse_in_range` 里找不到
  `assert_roster_matches_the_inventory`/`WINDOWS`，反之找不到 `parse_in_range`/`assert_covers_the_range`），
  红字词表不相交（「射程内有」∉②、「没进册」∉①）。
- 🔴 如实登记：坏件**真在盘上**时，②那一枚（与 r572／r466）也会红——但红的是 r253 那条不带文件名的原文，
  不是②自己的判据。这一半本单治不了（`tests/test_r253_*` 在禁碰清单里），改法逐字对照在 §6，等总控批。

## 4 反证窗名册（派生，不手抄）与两把刀

名册来源：射程内「调用严格口径的件」（AST）∪「定义/调用射程与名册本体的件」（`suite_sources`／
`window_handles`／`assert_roster_matches_the_inventory`／`inventory`／`scan_suite`／`parse_sources`）∪
「两枚派生源 + `COUNTER_PROOF_HOMES` + r466 名册 16 行」——交回 **25 枚**，清单摘要
sha12 `488abe1ce697`（脚本 `%TEMP%\r589_knifelist.py`，逐枚点名在交回里）。

| 趟 | 命令 | rc | 读数 |
| --- | --- | --- | --- |
| 摘前基线色 | `pytest <25 枚名册> -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r589kpt -q --tb=no -rf` | 0 | 380 passed / 1 xfailed / 0 failed（379.33 s） |
| **刀一**（塞一枚语法坏的件） | 同一枚名册 | 1 | 30 failed / 350 passed / 1 xfailed（299.79 s） |
| **刀二**（塞一枚合法却不该进集的件） | 同一枚名册 | 0 | 380 passed / 1 xfailed / 0 failed（401.03 s）＝摘前逐数同 |

刀一里 30 枚红的成色（按红字归类，`--tb=line` 现取）：

| 成色 | 枚数 | 落点 |
| --- | --- | --- |
| 带点名的红（`_temp_edit_overlay.py:228: AssertionError: 射程内有 1 枚件解析不了 … 第 3 行 第 9 列`） | 14 | `test_r589_*` 7 枚 ＋ `test_r516_*` 7 枚 |
| 仍是 `ast.py:50: File "<unknown>", line 3` 的原文 | 16 | `test_r253_*` 3 ＋ `test_r572_*` 3 ＋ `test_r583_window_inventory` 4 ＋ `test_r583_roster_*` 5 ＋ `test_r466_*` 1 |

判据③的三列 sha（256 前 12；摘前 → 摘后 → 还原；探针件本身另记）：

| 刀 | 路径 | 摘前 | 摘后 | 还原 |
| --- | --- | --- | --- | --- |
| 一 | 射程集合摘要（641/642/641 枚逐字节） | `af7755235632` | `9ee010ba53ec` | `af7755235632` ✅全等 |
| 一 | `tests/test_zz_r589_probe_broken.py` | ABSENT | `1397695d7325` | ABSENT ✅ |
| 二 | 射程集合摘要 | `af7755235632` | `0f20fdc55178` | `af7755235632` ✅全等 |
| 二 | `tests/test_zz_r589_probe_quiet.py` | ABSENT | `5b23bdf863f7` | ABSENT ✅ |

两把刀期间，在册九枚（口径与名册本体件：`_temp_edit_overlay`／`test_r253_*`×2／`test_r516`／
`test_r583_*`×2／`test_r466`／`test_r572_window_handles`）sha12 逐枚一字未动：
`fa53196f65d4 / 0b6e8c042ee8 / 05a14edcf669 / 22c8f4e2c1f1 / e5fd030f0ed4 / 61a88de7b226 / 0ac66a06cfbc / 9d1932fa4668 / 459f3a36ce7d`。

- **刀一达标**：红在①那枚新钉上，且红字点名 `tests/test_zz_r589_probe_broken.py:第 3 行 第 9 列 PROBE = = 2
  SyntaxError: invalid syntax`（单钉复跑：`7 failed / 1 passed`，只跑甲格那一格 `rc=1 · 1 failed in 4.09s`）。
  连带那 16 枚红是本单治不了的一半，见 §6。
- **刀二达标**：合法探针进射程（642 枚）、解析得了、被派生认成开窗者，但**落 `no_install`**
  （`{'windows': ['_ZzQuietEdit@test_zz_r589_probe_quiet.py'], 'open_sites': ['_zz_quiet_window:L16']}`），
  🔴 不进 LIVE（仍 16 枚）、不进名册（`rows=16 derived=16 missing=[] extra=[]`），25 枚名册逐数同摘前——
  没有一枚在册钉因此变绿或变红第二枚。常驻形同格在新钉己格（合成输入面）里天天跑。

## 5 改前／改后：同一枚名单集的正序＋反序（R583 立的规矩）

名单集派生自「import 严格口径/窗骨架的件 ∪ r583 四族 ∪ r466 名册 16 行 ∪ 八枚锚件」＝**37 枚**，
清单摘要 sha12 `5d5db160157a`（正序）；反序用同一份清单倒排。`tests/_temp_edit_overlay.py` 满仓在册件 import 它，
所以这四趟是同口径对照，不是各跑各的。

| 趟 | 正序 | 反序 |
| --- | --- | --- |
| 改前基线（245315b，未动一字节） | **548 passed / 1 xfailed / 0 failed**，rc=0，857.07 s | **548 passed / 1 xfailed / 0 failed**，rc=0，376.03 s |
| 改后同集（三件已落盘） | **548 passed / 1 xfailed / 0 failed**，rc=0，396.64 s | **548 passed / 1 xfailed / 0 failed**，rc=0，415.66 s |

改后新增（不在 37 枚集合里，单列）：`tests/test_r589_unparseable_files_cannot_shrink_the_range.py` 8 passed。
四趟枚数一字不变 ⇒ 本单没有把任何一枚在册钉改色；用时差异只反映同机三枚在飞单（`be-r590`／`be-r596`／`be-r597`）抢 CPU。

## 6 没治完的那一半：`tests/test_r253_*` 的改口草案（逐字对照，等总控批）

🔴 本席**未动**那个文件，下面只是草案。批了才落地；不批，则盘上出现坏件时仍会有 16 枚红报的是不带文件名的原文。

草案一（`tests/test_r253_no_test_rewrites_a_tracked_file.py:559-564`，把解析收进族内唯一口径）——

改口前（逐字）：
```python
def parse_sources(texts: dict) -> dict:
    """rel -> 文本 的合成输入面 -> rel -> (文本, 已解析 AST)。

    反证拿它喂**同一枚**派生与**同一枚**判据：盘上一字节不动，摘的只是输入。
    """
    return {rel: (text, ast.parse(text)) for rel, text in texts.items()}
```
改口后（逐字草案）：
```python
def parse_sources(texts: dict) -> dict:
    """rel -> 文本 的合成输入面 -> rel -> (文本, 已解析 AST)。

    反证拿它喂**同一枚**派生与**同一枚**判据：盘上一字节不动，摘的只是输入。
    🔴 R589：解析走该族唯一的严格口径 `overlay.parse_in_range`——解析不了的文件既不许静默跳过
    （射程会无声少一枚），也不许把那条不带文件名的原文直接端上来（那会把别人的一枚手抖读成一次回归）。
    """
    return overlay.parse_in_range(texts)
```
配套（同件 import 段 `L40-42` 之后加一行）：`from tests import _temp_edit_overlay as overlay`
（无环：`_temp_edit_overlay` 不 import 任何测试件；名字沿用族内既有写法，r583／r516 都是这手）。

草案二（同件 `L479-482`，写口数量那格的射程也走唯一口径）——
改口前：
```python
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
```
改口后（草案）：
```python
    for _path, (_text, tree) in overlay.parse_in_range().items():
```
（`total` 的累加体不变；现量 303 枚写口的下限 200 不必动。）

草案三（同件 `L246`，让合成源码之外的原文红也带文件名）——
改口前：`    tree = ast.parse(source)`
改口后（草案）：`    tree = ast.parse(source, filename=label)`
（`label` 就是 `scan_suite()` 逐枚交回的仓内相对路径，`tests/test_r253_...py:345`；合成源码那几格 `label` 缺省
`"<source>"`，形状不变。这一手只把「不点名文件」修掉，不放宽任何判据。）

## 7 盘面（交回原文见本席最后一条消息）

```
git -C be-r589 diff --numstat HEAD
119     0   tests/_temp_edit_overlay.py
10      6   tests/test_r516_the_dataset_stubs_stay_on_the_class.py
git -C be-r589 ls-files --others --exclude-standard
tests/test_r589_unparseable_files_cannot_shrink_the_range.py
```
- 未 commit／未 push／未建分支；基点 `245315b`；`git status --porcelain` 只余这三件（外加本纸）。
- 三件行数与 sha256 前 12（盘上工作树，CRLF）：`_temp_edit_overlay.py` 394 行 `fa53196f65d4`（基点 blob 275 行
  `0d7cc6ab6a27`，LF 归一）；`test_r516_...py` 892 行 `22c8f4e2c1f1`（基点 blob 888 行 `a54cc92d7b66`）；
  新钉 `test_r589_...py` 355 行 `459f3a36ce7d`（摘前 ABSENT＝本单新增）。
- 编码自证（规则 4）：三件均 `count(b"\r\n") == count(b"\n") == count(b"\r")`，无 BOM、无裸 CR——
  overlay 394/394/394、r516 892/892/892、新钉 355/355/355、本纸同口径（落盘后计数见交回）。

## 8 没验的格子（逐枚点名）

1. 全量门未跑（本单禁跑 `scripts/run_gate.py`）：改后数字只有 37 枚同集两趟＋25 枚名册一趟＋新钉单跑。
2. §6 三处改口没落地 ⇒ 「盘上坏件时 ②／r572／r466 红的是 r253 那条不带文件名的原文」这一半今天仍在；
   刀一那 16 枚连带红只取了一次，没做第二次复现。
3. `app/**` 那把尺子的同族形状未治：`tests/test_r478_no_closed_gate_as_placeholder.py::_units:L188-191`
   `except SyntaxError: tree = None`（射程是 `app/**`，不是测试件），只报不改，等单号。
4. 新钉甲格下限 600 枚是贴着基点现量 641 的纸面下限，没在别的机器／别的树上量过。
5. `test_r516` 的运行期审计腿在坏件下只取到「7 枚红带点名原文」，没逐枚核对它自己那张 12 枚名册是否也在同一格红。
6. 刀二只演了「开窗不装变异」这一种不该进集的件；「装变异却不进册」那一半是 R583 刀一在管，本单没重演。
7. `parse_in_range` 对非 UTF-8／读不出文本那一手（`OSError`／`UnicodeDecodeError`）没有盘上反证——
   合成面只演了 SyntaxError 那一族；那一路径今天只有码，没有读数。
