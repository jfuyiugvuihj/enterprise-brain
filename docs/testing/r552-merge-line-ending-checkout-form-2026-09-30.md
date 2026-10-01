# R552 —— 铺树器给新件的行尾：从「siblings 猜 blob」改判「git 检出形态」

派工：总控 09-30 23:0x【新令 R552】＋23:1x【裁定·两条都批，附三条边界】。执行席：Erdos（本线程第七枚单）。
工作树：`C:\Users\fengx\PycharmProjects\be-r535`，基点由 `05bec06` 追平到 **`4572aa8`**（detached，零 commit）。
写域：`scripts/r531_worktree_merge.py` ＋两枚新钉 ＋本纸。⑥ 那批在册件只记读数，断言一字未动。

---

## 1. 前提现取（总控让我自己核，不许照你的账修）

| 问句 | 命令原文 | 现取末行 |
|------|----------|----------|
| autocrlf 生效值 | `git config --get core.autocrlf` | `true` |
| 它来自哪一层 | `git config --local --get core.autocrlf`／`--global`／`--system` | local rc=1、global rc=1、**system=true**（总控主树现取同源 `file:C:/Program/Git/etc/gitconfig`） |
| core.eol | `git config --get core.eol` | rc=1（未设 ⇒ git 按 native 算） |
| 有没有 .gitattributes | `git ls-files -- .gitattributes '*/.gitattributes'`；`Test-Path` 主树与本树 | **零命中／两处都 False** |
| 新件路径的属性判定 | `git check-attr text eol -- docs/testing/r552-brand-new-note.md` | `text: unspecified` / `eol: unspecified` |
| 全仓行尾普查 | `git ls-files --eol`（主树，tracked=**1483**） | `i/lf w/crlf` **1048**、`i/lf w/lf` **314**、`i/lf w/mixed` **36**、`i/-text w/-text` **72**、`i/none w/none` **13** |
| 检出实测（不是引用规则） | 本树 `git merge --ff-only` 之后逐枚 `Get-FileHash` vs 仓外备份 | R535 那 7 枚**逐枚字节全等**（含纸：blob 是 LF，检出回盘上仍是同一枚 CRLF 字节） |

⇒ 派工写的前提成立：**文本件的盘上稳定态是 CRLF**（全新检出即 CRLF）。唯一要补一句的是 autocrlf 的来源在 **system** 层，不在 local/global——所以决策函数必须读**生效值**（`git config --get`），读 local 会得到 rc=1「没设」。

## 2. 真因形状：比「siblings 猜错了」更硬一层

`sibling_convention()`（改前 `:72`，现 `:144`）数的是 `blob_convention()` 的返回值，而后者取 `git show HEAD:<path>` 的**字节**＝blob。`core.autocrlf=true` 下文本件的 blob 恒为 LF ⇒ 同目录抽十二枚永远数出 `crlf` 零枚。这不是抽样偏差，是那条链**结构上只会答 LF**。本树现取的铁证（修好后跑的诊断读数）：

```
sibling_convention('tests/test_r552_new_probe.py') -> ('lf', "siblings {'crlf': 0, 'lf': 12} of 596")
checkout_form('tests/test_r552_new_probe.py')      -> ('crlf', '检出形态=crlf（core.autocrlf=true 且无 text/eol 属性 ⇒ 检出补 CR）')
target_convention('app/api/v1/chat.py')            -> ('crlf', '盘上惯例 crlf')
```

缺的概念是 **「blob 的行尾 ≠ 检出后盘上的形态」**。工具自己的模块 docstring（改前 `:7`）把「一律以 blob 行尾为准」写成规则、又把「部分 `docs/**` 盘上是 LF」当成一种要保护的惯例，正是那条多数决看着合理的来源；本纸把这句话说正了（见 §4）。

同一条形状今天在 worktree 侧咬过第二次（`tests/test_r469_readout_is_generated.py` 两枚在册读数件在树里先天红），在并树侧咬了 R547 十二枚——手工归 CRLF 是本器存在理由所要消灭的东西。

## 3. 判据选型（总控要我表态的那一条）

钉的是**「新件落盘行尾＝这枚 blob 被 git 检出之后盘上会长成的那一版」**，不是「新件一律 CRLF」。三条反例就是理由：往 `docs/` 铺一张图（本仓已有 **72** 枚 `-text`，硬塞 CR 等于改坏文件）；将来业主加 `.gitattributes`（`*.md text eol=lf`）；换一台 `core.autocrlf=input` 的机器。一律 CRLF 只是把今天的读数抄进代码，摘掉修复还照样绿——不可证伪。今天这台机上，这条不变式**算出来就是 CRLF**，所以总控要的行为一分不差。

`sibling_convention()` 按裁定**不删、降级为诊断**：新件那一格照样叫它一次，把 tally 原样打进 `note`（`…；siblings → {'crlf': 0, 'lf': 12} of N（只作诊断，不决策）`），既保住在册钉 `tests/test_r531_worktree_merge_keeps_each_files_eol.py:66`，又留下这枚病的痕证。

## 4. 修法（坐标现取，改后盘面）

`git diff --numstat` → **`86 9 scripts/r531_worktree_merge.py`**；`git ls-files --eol` → `i/lf w/crlf`；文件 274 行全 CRLF、裸 LF 0。

- 新增（`scripts/r531_worktree_merge.py:62` 起）：`native_form()`／`git_attr()`／`git_config()`／`checkout_form()`（`:88`）。`checkout_form` 照 git 的口径分支：前 8000 字节含 NUL ⇒ `asis`；`-text` ⇒ `asis`；显式 `eol=crlf|lf|native` 优先；无 eol 时由**生效的** `core.autocrlf` 支配（`true`⇒crlf、`input`⇒lf、false/未设⇒`asis`）；显式 `text`（set/auto）而无 eol 时取 `core.eol`（缺省 native）。git 问不到（仓外、check-attr 报错）⇒ 交回 `(None, 理由)`，`apply_paths` 那一格照旧 **REJECT，不许猜**。
- 新件那一格换血：`listable()` 的 `:184`、`apply_paths()` 的 `:236`；诊断留痕 `:241`；`asis` 分支 `:243-244`（原样字节写，不进 `normalize`）；自证改判 `:249`（`ok = back == (detect(data) if asis else conv)`）。
- 在册件那一格（`:208-212`）**一字未动**：盘上是什么行尾就铺成什么行尾。
- 模块 docstring `:7` 从「一律以 blob 行尾为准」改成「在册件按盘上那一版，新件按检出形态，blob 行尾不等于检出形态」。
- 没动：`tests/test_r469_readout_is_generated.py`、`tests/test_r531_*`、`tests/test_r547_*` 的**任何断言**；`scripts/r455_gapdoc_coordinates.py::land_cells` 那套落表器（判据③）；任何在册件的现有行尾。

## 5. 🔴 欠账（裁③ 要求的这一节：同病未治，别当成已修好）

`scripts/r531_worktree_merge.py:213` 那一格——`conv = conv = blob_convention(path)` ⇒ 命中就 `return conv, "blob 惯例 " + conv + "（盘上读不到）"`——**和 siblings 是同一枚病**：拿 blob 的行尾冒充检出的形态。触发条件是「文件在 HEAD 里、盘上却读不到」（在册件被删/首次铺到没这枚文件的树上），今天没咬人是因为并树时在册件都在盘上。

- **这轮为什么不治**：那一格被在册钉明文保护着——`tests/test_r531_worktree_merge_keeps_each_files_eol.py:104` 的 `test_f_a_new_file_still_falls_back_to_the_blob_then_the_siblings` 断言 `target_convention("app/new.py") == ("lf", "blob 惯例 lf（盘上读不到）")`。本单判据③ 写死「不许改任何在册件现有行尾／不许动 ⑥ 那批的断言」，改这一格必然同时改那枚钉——那是总控的写域。
- **谁接手**：总控。出路两条，二选一：① 把那一格也换成 `checkout_form(path, <blob 字节>)`，同时把 `:104` 那枚钉改成「按检出形态」；② 保留 blob 惯例但只在 `checkout_form` 交回 None 时兜底。顺带请一起收掉 `:213` 那枚既存的 `conv = conv = blob_convention(path)` 双写赋值（既存形状，非本单引入，本单没碰那行）。
- 另记一枚**仍在树上的活口**（属总控写域，本席不伸手）：主树 `docs/testing/r536-retrieval-trace-emission-2026-09-30.md` 现取 `i/lf w/lf`——R536 那本新纸是铺树器按旧规则铺的，没被归正；谁哪天删了它 `git checkout --`，它变 CRLF，拿「换行符成对」当判据的钉会当场翻面。全仓另有 **314** 枚同形（`i/lf w/lf`），按判据⑤「零历史改动」本席一枚都不回写。

## 6. 反证刀台账（`tests/test_r552_counter_evidence_teeth.py`，167 行）

机械同 R524/R535：影子只走内存、源文落 pytest `tmp_path` 留痕、`_bite` 接 `BaseException`、每把刀**先正控后摘刀**、被跟踪件摘前摘后按 sha256 自证、末了扫仓内影子件残留。影子模块的 `ROOT` 一律指回真仓，免得红得没有道理。

| 刀 | 摘掉的那一格 | victim | 摘前 sha256（被跟踪件，16 位前缀） |
|----|--------------|--------|-----------------------------------|
| K1 | 新件那一格退回 `sibling_convention` 决策（今天的病） | 本单钉 `test_c_a_landed_new_file_is_exactly_what_checkout_would_give` | 工具 `3ffe42b24af2c894` |
| K2 | `core.autocrlf=true ⇒ crlf` 钝化成 `asis` | 本单钉 `test_a_decision_equals_observed_checkout_in_every_shape` | 钉件 `e4cbe66e4a97540c` |
| K3 | 摘掉在册件「盘上那一版优先」（`:209`） | 🔴 在册钉本身 `test_r531_worktree_merge_keeps_each_files_eol.test_e_a_tracked_file_keeps_the_eol_it_has_on_disk_not_the_blob` | 在册钉 `e635d8b3223fe159` |
| K4 | 判出 `asis` 却硬去 `normalize` | 本单钉 `test_d_binary_and_minus_text_new_files_land_verbatim` | 刀件 `a27adde1074845c8` |

另两枚总清格：`test_z5_the_ledger_names_every_knife_and_every_victim`（表↔刀↔victim 三方对齐，且至少一把咬在册钉本身）、`test_z6_the_tracked_files_are_byte_for_byte_untouched`（八枚被跟踪件逐枚 sha 等值＋仓内 `r552_shadow_*.py` 零残留）。

被跟踪八枚的进门指纹：工具 `3ffe42b24af2c894`、r531 钉 `e635d8b3223fe159`、r469 钉 `01725985ce01f807`、本单钉 `e4cbe66e4a97540c`、本单刀 `a27adde1074845c8`、`r455` 落表器 `1b6648034b160d78`、r547 两枚钉 `b09763f5a3ff55ae`／`da6e95466d885ea3`。

- 订正：刀件在写完后就地修掉一枚自写的断言 bug（`test_z5` 把 `"test_k1"` 拿去全名集合里找成员，恒假＝假红），
## 7. 判据④ 的自洽形状（钉怎么算「等于检出」）

`tests/test_r552_new_files_land_in_checkout_form.py`（147 行，离线，全在 `tmp_path` 里造仓）：

- `test_a_…in_every_shape`：六枚盘面（`core.autocrlf` ∈ true/input/false × 属性 ∈ 无／`-text`／`text eol=lf`／`text eol=crlf`）逐枚在 fixture 里**实测**「删掉→`git checkout --`→数 CR」，再问 `checkout_form`；`asis` 那两枚按「检出＝源件字节」比对。每格都把 `merger.ROOT` 指到当枚 fixture——否则决策与正解根本不在同一枚仓里问（本席第一版就写歪在这一处，静态自查抓到后已改）。
- `test_b_this_boxs_effective_rules_reproduce_the_decision`：把**本仓真实生效**的那套规则（`git_config("core.autocrlf")`）搬进 fixture 复算，钉的是「决策与这台机的规则同形」，不是「今天等于 crlf」。
- `test_c_a_landed_new_file_is_exactly_what_checkout_would_give`：端到端走 `apply_paths`，把那枚新件**入库、删掉、`git checkout --`**，再拿字节与铺树器落下的那份逐字节比——这就是判据④ 那句话本身。
- `test_d_binary_and_minus_text_new_files_land_verbatim`：`asis` 那一格必须一字节不动。
- `test_e_siblings_stay_a_diagnosis_and_the_in_book_rule_still_wins`：在册件盘上优先仍生效（判据③），且 `note` 里留着 siblings 的诊断读数。

## 8. 代跑清单（命令原文；解释器一律 venv，PATH 上的 `python`/`pytest` 是 anaconda3）

```powershell
# 批 1：本单两枚件
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' -m pytest tests/test_r552_new_files_land_in_checkout_form.py tests/test_r552_counter_evidence_teeth.py -q -p no:randomly -o addopts=
# 批 2：判据⑥ 点名族（今天被这条形状咬过的三族）
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' -m pytest tests/test_r531_worktree_merge_keeps_each_files_eol.py tests/test_r469_readout_is_generated.py tests/test_r547_coordinates_and_arms_are_derived.py tests/test_r547_gauge_fails_loudly_when_readings_are_unobtainable.py -q -p no:randomly -o addopts=
# 批 3：静态层（不跑测也能交的读数）
& 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe' -m py_compile scripts/r531_worktree_merge.py tests/test_r552_new_files_land_in_checkout_form.py tests/test_r552_counter_evidence_teeth.py
```

- 批 1 两枚件互不重叠：钉件 collect=**5**，刀件 collect=**6**（四把刀 ×（正控＋摘刀）合成在同一枚 `_pair` 里跑，加两枚总清格）。批 2 是在册三族，**断言一字未动**，红了就是本单的问题。
- 全量门（`python scripts/run_gate.py`）属总控独占，本席不跑也不请求代跑；本席全程零 `-n`、零 `--dist`、零 docker、零打模型、零 commit/push、未动主树。

## 9. 本席跑测状态（照实，不洗绿）

- 追平序列（裁① 备份道）已交完读数：`status --porcelain` 追平前 7 项 → 追平后 **0 行**；HEAD `05bec06` → **`4572aa8`**（detached）；七枚逐枚 sha256 盘上 vs 备份**全等**；备份目录 `C:\Users\fengx\PycharmProjects\be-r535-backup` **保留未删**。
  - 一处偏离原案要报备：`Remove-Item` 被本机策略挡了两次（destructive 拦截），所以三枚 `??` 没走「删除」，改走**零删除**的道——`git add -- <三枚>` 把与 `4572aa8` 逐枚同 blob（`64a74acb…`／`223a6b4c…`／`24c73e03…`）的文件记进索引，`merge --ff-only` 视其为 uptodate 后一次通过（rc=0）。全程无 `reset --hard`／`clean -fd`／`git checkout .`，无 `git stash`（不造 refs/stash 对象）。副作用：这三枚从此在本树里是**已跟踪**（追平后 index==HEAD，`status` 干净）。
- **批 1／批 2 未跑（等窗）**：23:19:51 现取主树仍有 `python.exe -m pytest …\tests\test_r408_docs_say_what_the_tree_does.py`（venv＋anaconda 各一枚）在跑，总控门未点名收窗 ⇒ 本席一枚 pytest 都没起。允许的静态自查全跑过：`py_compile` 三枚 rc=0、EOL 逐枚 CRLF（纸/钉/刀/工具均裸 LF=0）、`git ls-files --eol`、`rg` 读数、以及 §2 那三枚决策函数的**现取调用**（`importlib` 直调，非 pytest）。
- 交回时**没有任何「N passed」出自本席**。达不到的格：判据④ 的「摘刀必须红」与判据⑥ 的「在册族不退化」两格**待跑**（命令见 §8），由总控收窗后代跑或点名窗口给本席。

## 10. 盘面终值（23:2x 现取）

```
$ git -C be-r535 diff --numstat              $ git -C be-r535 status --porcelain
86   9   scripts/r531_worktree_merge.py       M scripts/r531_worktree_merge.py
                                            ?? tests/test_r552_new_files_land_in_checkout_form.py
                                            ?? tests/test_r552_counter_evidence_teeth.py
                                            ?? docs/testing/r552-merge-line-ending-checkout-form-2026-09-30.md
```
