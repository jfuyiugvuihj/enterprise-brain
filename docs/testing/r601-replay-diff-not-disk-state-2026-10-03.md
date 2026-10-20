# R601 · 常驻钉不许把「此刻盘面有没有某枚产物」当判据（前后差分那一刀）

日期 2026-10-03（星期六）。执行层席交工纸，单号 **R601（P2）**，独占工作树
`C:\Users\fengx\PycharmProjects\be-r601`，基点 **`3bed8f8`**（开工那刻现读 `git status --porcelain`
= 0 行）。判据原文＝`docs/handoff/2026-09-15-backend-followup-requests.md` 里 `### 160.6`（第 5387 行）
那一节的 R601 格（`rg -n "refuse_inside_repo"` 现取该行在**第 5391 行**，按 LF 计）。
🔴 顺带一枚本席现取的坑：该文件**不是均匀 CRLF**——bytes 1,141,356／CRLF 5,399／LF 5,402／
CR 6,933，即约 1,534 枚裸 CR 混在行尾里。所以同一句原文，`rg`（按 LF）给 5391，
`ReadAllText -split "
"` 给第 5388 枚元素，两个数都"对"、但不同代——派工词点的那枚
「别拿行号当位置」在这里是实取的，不是套话。本单没改这枚件（`docs/handoff/**` 禁区）。
本纸所有读数都是本席亲跑（**执行层自报**），不是转述派工词；未跑的格子逐枚写在 §7 标「未验」。

## 1. 一手成因（本树现取，不是抄派工词）

在册产物凭据：`%TEMP%\eb103\stray\collect-sidecar-frames.jsonl` **26,095 B**，
sha256 `EA1CC7247804AEB7BE489E06FB63025F6F594951ACAC98C519967A8FC8C407B2`，
`LastWriteTime 2026-10-03 08:54:34`。原件本席一个字节没动，也没有删除权（删除权在业主）。

复证（同一枚钉、同一棵树、两枚盘面态，中间不改任何代码）：

| 步 | 命令原文 | rc | 读数 |
| --- | --- | --- | --- |
| ① 盘面干净（本树起点） | `python -X utf8 -m pytest tests/test_r181_text_frame_ruler.py::test_the_replay_produces_no_bytes_inside_the_repo -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r601-base0 -q` | 0 | `1 passed in 0.47s` |
| ② 把上面那枚产物按字节摆进 `scripts/` | `Copy-Item $TEMP\eb103\stray\collect-sidecar-frames.jsonl → be-r601\scripts\`；`Get-FileHash` | — | `EA1CC7247804AEB7…`（逐字节相等），`git status --porcelain` → `?? scripts/collect-sidecar-frames.jsonl` |
| ③ 同一枚钉再跑（**旧判法**） | 同 ① 的命令，basetemp=`r601-repro1` | 1 | `AssertionError: assert [WindowsPath('…/scripts/collect-sidecar-frames.jsonl')] == []` ＋ `1 failed in 0.43s` |
| ④ 搬回仓外 | `Move-Item …\scripts\collect-sidecar-frames.jsonl → %TEMP%\r601-selfcheck\` | — | 仓内 `Test-Path` = False；搬走后 sha 仍 `EA1CC7247804AEB7…`；`git status --porcelain` = 0 行 |

⇒ 「与任何改动无关的恒红」在本树被复现一次。10-03 总控并 R590 时被它挡的那次，全过程记在主树
commit `b78ecd8` 的 subject（`git merge-base --is-ancestor b78ecd8 HEAD` 本席现取 rc=0）。

**派工词要订正一格**：判据原文写「落点为什么相对 `cwd`」。本席查的是 `scripts/` 这一层的写点，
用的名字是那一层的真名：`scripts/eval_transport_ask_v2.py:228`

    SIDECAR = Path(os.getenv("EVAL_SIDECAR") or str(Path(__file__).with_name("collect-sidecar.jsonl")))

它不相对 `cwd`，相对**脚本自己**——比相对 cwd 更硬：无论从哪里起窗，`EVAL_SIDECAR` 不设就一律落进
`scripts/`，帧账（`:236 frame_ledger_path()`，同名加 `-frames` 尾缀）跟着它。runbook
`docs/handoff/2026-09-17-eval-real-run-runbook.md:415` 早就把这条脚枪记在账上（「不设环境变量就是往仓内写」），
只是没有人拦。今天漏进仓里的正是这一对：`collect-sidecar.jsonl` ＋ `collect-sidecar-frames.jsonl`。

## 2. 判据①：钉改成前后差分

`tests/test_r181_text_frame_ruler.py` 新增四枚把手（`:629` 起，`FRAMES_SCAN` 那一行）与常驻钉本体
（`:671`）；fixture 的十二行构造拆成公共把手 `build_adapter`（`:172`），fixture 只做一次转调（两枚
影子反证要用同一个 adapter，不许手抄第二份）。

- `FRAMES_SCAN = "scripts/*frames*.jsonl"` —— **扫描面一个字未缩**，与 10-03 那条 glob 同名同形；
- `frames_inventory(root)` —— 名字 → `(字节数, sha256)`；读不到的件如实记 `unreadable`，不静默剔；
- `new_frames_since(before, after)` —— 只回**多出来**的名字。🔴 被删掉的原有产物**不进判据**：
  业主今天把那枚 26 KB 搬进 `%TEMP%\eb103\stray\` 正是这种合法动作，拿它当罪证就是重犯本单要治的病；
- `repo_write_judgment(root, run)` —— 跑前拍清单、跑后算差分，回 `(跑前清单, 新增清单, 绿不绿)`。
  常驻钉与两把影子反证**共用这一枚尺**（`tests/test_r496_forbidden_pin_scope.py` 立的规矩：两棵树不许各拿一把尺）；
- 常驻钉本体：`assert green` 之外补一刀落点检查——`SIDECAR` / `frame_ledger_path()` / 答案件三枚路径
  必须一路在仓外。「覆写一枚盘上已有的同名件」这一形差分读不出来（枚数没变），由这枚落点检查兜住，
  写在纸上当已知边界，不假称差分万能。

没做的事（判据① 明令）：没改成 `skip`，没加豁免名单，没缩小扫描面。`test_the_treated_files_carry_no_downgrade_marker`
把「零降级记号」也钉住了（治的件与本单新钉两份都查）。

## 3. 判据②：落点把手——哪几处漏了，逐枚点名

**本单补上的两处：**

1. `scripts/collect_evaluation_answers.py`（采集器那条腿，从前**一枚闸都没有**）——新码在
   `:101 LandingSpotError` / `:312 LANDING_REMEDY` / `:316 EVAL_TRANSPORT_MODULE` /
   `:319 refuse_inside_repo` / `:339 transport_evidence_module` / `:346 window_landing_spots` /
   `:365 refuse_landing_spots`，`main()` 里那道闸在 `collect_answers` 之前。
   - `refuse_inside_repo(path, what, root=None)`：与 driver 同名同语义同一枚文案（「落在仓内：」）；
   - `window_landing_spots(output, transport)`：答案件 + 侧车 + 帧账，两枚证据件的落点**从已加载的
     transport 模块现问**（`SIDECAR` / `frame_ledger_path()`），不靠本件自己记名字；
   - `refuse_landing_spots(...)`：`--transport` 落点是 `eval_transport_ask_v2` 而两枚证据件问不着 ⇒
     按「问不到」拒（与 driver 的 `--env-file` 同一口径），不许当通过；
   - `main()`：真窗与 dry-run **两条路都在写第一个字节之前**过闸，拒则 `REFUSED:` + 正解文案，rc=2。
2. `scripts/eval_window_shard_driver.py`（只补落点把手，分片与收窗逻辑一字未动）——新码在
   `:153 refuse_inside_repo(..., root=None)` / `:176 LANDING_SPOTS` / `:181 is_git_tree` /
   `:189 refuse_landing_spots` / `:442 EVAL_FRAME_LEDGER`（`collector_env` 的 env 瓶里）。
   - `refuse_inside_repo(..., root=None)` 多了 `root`；新增 `is_git_tree()` 与 `refuse_landing_spots(P, repo)`；
   - 从前只闸八枚落点里的**两枚**（产物目录、合并件），现在 `LANDING_SPOTS` 八枚逐枚点名：产物目录／
     分片目录／指纹件／分片计划件／侧车／帧账／合并件／驱动日志；
   - 从前只拿**本件自己的** `REPO_ROOT` 比 ⇒ `--repo` 指另一棵真树（跑分树那形）时，往那棵树漏产物无人拦。
     现在两棵都比，但第二道只在 `--repo` 确实是 git worktree（`.git` 在位，目录或文件两形都算）时才走：
     在册 `tests/test_r570_window_shard_driver.py` 两枚钉把 `--repo` 指成一枚临时目录用，临时目录脏不了
     任何一棵树，把它当仓库拒＝拿假罪证拦真窗（本席先按「一律比」写过，`test_a_missing_env_file_refuses_instead_of_crashing`
     ＋ `test_an_existing_env_file_still_supplies_the_password` 双双翻红 2 枚，现读为改窄后的 47 passed；
     这一枚形状是量出来的，不是想出来的）；
   - `collector_env(..., frames=None)` 现在**显式**把 `EVAL_FRAME_LEDGER` 钉给采集器（缺 `frames` 时按
     transport 同一把命名派生），帧账不再靠「跟着 SIDECAR 走」这一句推理。

**仍然漏着的（本单未治，逐枚点名，不许宣布家族清零）：**

| # | 位置 | 缺什么 | 为什么本单没动 |
| --- | --- | --- | --- |
| 1 | `scripts/eval_transport_ask_v2.py:228` | `SIDECAR` 仓内缺省本身，无把手 | 出写域（写域只给了 collector/driver 两件）。现由上游两条腿拦 |
| 2 | `scripts/eval_transport_ask_v2.py:235-245` | `frame_ledger_path()` 跟随缺省，无把手 | 同上 |
| 3 | `scripts/eval_transport_ask_v2.py:1281-1283`（`_record` 的 `mkdir`+`open("a")`）与 `_record_frames` 的帧账写点 | 写点自身不判落点 | 同上；写点拦＝改 transport，出写域 |
| 4 | 不经 `main()` **裸用** `transport()` 的第三方驱动（`--transport` 由别的模块装载并直接调用） | 两条腿的闸都在这条路之外 | 未穷举有几个这种调用方 ⇒ 见 §7「未验」 |
| 5 | `scripts/run_quality_evaluation.py --output docs/testing/…` | 仓内落点 | **设计如此**（在册被跟踪报告件），不算这一族；它别的落点本席未查 |
| 6 | `scripts/` 里另外 ~55 枚 `Path(__file__).resolve().parents[1]` 派生 REPO 的量具 | 逐枚落点名册 | 本席只扫了两层（§5 说清了是哪两层、用的什么名字），其余未验 |
| 7 | `app/**`（产品写路径：`static/`、`data/`、`chroma_db/`） | 与本单无关 | 禁区，一字未碰 |

两条腿**没有物理合并**成一枚函数：driver 件头 `:16` 与 `:376` 自己写明「本件不改采集器、不 import 采集器、
不复制它的任何判读」，而 `app/**` 是禁区、没有第三个公共家可放。本单把它做成**同名同语义同文案**，并用
`HANDLE_CASES` 八格形状矩阵 + 文案钉各证一遍「同一份盘面 ⇒ 同一个判决」；要真并成一枚把手得先裁
「driver 能不能 import 采集器」这一句，那条裁量归总控（§7）。

## 4. 判据③：两把反证（三列 sha + 红色回显 + 还原自证）

被摘的件都是 `tests/test_r181_text_frame_ruler.py`（sha 取前 12 位，全程 `git status` 之外的写只有这一枚件，
还原由脚本内 `write_bytes(pristine)` 完成）。命令一律
`python -X utf8 -m pytest <nodeid> -o addopts= -p no:cacheprovider --basetemp=<TEMP 下独有名> -q --tb=line`。

**牙 (a) 新落一枚 `*frames*.jsonl` 进 `scripts/` ⇒ 本钉必红**（摘形：把差分的牙摘瞎，`new_frames_since` 恒回 `[]`）

| 列 | 值 |
| --- | --- |
| 摘前 sha | `eeca5d4c29b9` |
| 摘后 sha | `29a226ff9c6b` |
| 摘后读数 | rc=1，`AssertionError: 新落一枚而差分没点名：[]`，`1 failed in 0.45s` |
| 还原后 sha | `eeca5d4c29b9`（`全等 True`，逐字节） |
| 还原后读数 | rc=0，`1 passed in 0.42s` |

泄漏本体不是手摆的道具：影子根里跑的是**真的** 105 题重放（`build_adapter` + `_replay`），
`SIDECAR` 绑到 `<影子根>/scripts/collect-sidecar.jsonl`，帧账由 `frame_ledger_path()` 按在册缺省命名
自己落在 `<影子根>/scripts/collect-sidecar-frames.jsonl`，落盘字节与 `frames_inventory` 的
`(size, sha256)` 两枚读数逐一对上。

**牙 (b) 原有产物在场时本钉必须绿**（今天缺的那半边；摘形：把常驻钉的判法**摘回**「此刻盘面 == 空集」）

盘面 = 把 §1 那枚 26,095 B 真产物按字节摆进 `scripts/`（跑完再按字节搬回 `%TEMP%\r601-selfcheck\`）。

| 列 | 值 |
| --- | --- |
| 摆进仓内的产物 | sha `ea1cc7247804…`，26,095 B |
| 摘前 sha | `eeca5d4c29b9` |
| 新判法 + 原有产物在场 | rc=0，`1 passed in 0.56s` ← **这一格就是 10-03 欠的那半边** |
| 摘后 sha | `292a0c694a81` |
| 旧判法 + 同一份盘面 | rc=1，`AssertionError: assert [WindowsPath('…/scripts/collect-sidecar-frames.jsonl')] == []`，`1 failed in 0.51s` |
| 还原后 sha | `eeca5d4c29b9`（`全等 True`，逐字节） |
| 还原后读数（产物仍在场） | rc=0，`1 passed in 0.47s` |
| 搬走产物后读数 | rc=0，`1 passed in 0.39s`；`%TEMP%\eb103\stray\` 原件 sha 仍 `ea1cc7247804…`（未动、未删） |

同一把尺还多钉了三格：`test_the_delta_is_not_an_exemption_list`（原有 1 枚 + 新落 2 枚 ⇒ 新增清单逐枚点名
两枚，证「差分不是豁免名单」）、`test_z_the_knives_left_the_real_repo_byte_identical`（真仓产物清单 +
四枚被治件的字节指纹，跑完必须与 import 那一刻全等）、`test_the_resident_pin_reads_a_delta_and_no_longer_the_live_disk_state`
（AST：常驻钉本体里 `glob`/`rglob` 零枚、「清单 == 空集」零枚、判定只能出自 `repo_write_judgment`）。

## 5. 家族扫描（先报查的是哪一层、用的是哪一层的名字）

- 层 1 = `tests/**` 的全部 `.py`，名字 = 对**工作树**做 glob 后断言空集（`ROOT.glob` / `REPO.glob` /
  `REPO_ROOT.glob` / `SCRIPT_DIR.glob` / `rglob` 五枚写法都查过）。同族命中逐枚：
  - `tests/test_r181_text_frame_ruler.py`（旧 613-614 行）—— 本单治；
  - `tests/test_r579_synthetic_provenance.py:155` `assert list(ROOT.glob("**/r579_corpus_*.tsv")) == []`
    —— 同族，且比 r181 更宽（整棵树递归）；**未治**（不在写域）。谁哪天留一枚 `r579_corpus_*.tsv` 在盘上，
    它就恒红，形状与今天一模一样；
  - `tests/test_r524_counter_evidence_teeth.py:439`、`test_r533:309`、`test_r535:637`、`test_r548:424-425`、
    `test_r578:295` —— `rXXX_shadow_*.py` 残件名册：一次崩在中途的跑就留残件，此后那枚常驻钉恒红 ⇒
    同一族形状，**未治**（不在写域）；
  - 不算这一族（报出来免得被当成漏点）：`tmp_path` 系断言空集的那些
    （`test_file_upload_security.py`、`test_document_*`、`test_r248_json_writepoints.py:282`、
    `test_r239:240`、`test_r391_*`、`test_r579_readout_teeth.py:534`、`test_r145_*` 的 `source = tmp_path / "chroma_db"`）
    —— 那枚目录由用例自己造，盘面就是被测对象的行为；`test_r382_untouched_defaults_pins.py:46-50` 拿
    `REPO.glob(".env*")` 定**扫描面**（它自己写明「只扫在场的那些」），不是「空集判据」；
    `test_r453_cloud_eval_override.py` / `test_r496_forbidden_pin_scope.py` 的 `git status --porcelain`
    那一族 R496 已治过一回，本单沿用它的影子根 + import 指纹全等两条规矩。
- 层 2 = `scripts/**` 的写点（名字 = `Path(__file__)` 派生 / `with_name` / `SIDECAR` / `DEFAULT_OUTPUT`），
  只逐枚查了评测窗三件（transport / collector / driver），结果见 §3 表。其余 ~55 枚 `Path(__file__).parents[1]`
  量具**未逐枚查落点**（§7）。

## 6. 复跑数字（执行层自报，全部本席亲跑）

| 范围 | 命令要点 | 读数 |
| --- | --- | --- |
| 本单新钉 | `pytest tests/test_r601_replay_diff_not_disk_state.py …` | `25 passed in 0.60s` rc=0 |
| 被治的常驻钉全件 | `pytest tests/test_r181_text_frame_ruler.py …` | `21 passed in 0.68s` rc=0 |
| 评测窗家族 38 件（含 r181/r601/r570/r123/r205a/r215/r223/r447/r456/r464/r471/r520/r580/r595/r496…） | `rg -l "eval_window_shard_driver|eval_transport_ask_v2|collect_evaluation_answers" tests` 的 38 枚全跑 | `684 passed / 4 skipped / 74 warnings in 93.40s` rc=0（4 枚 skip 属在册件自带条件跳过，非本单引入；本单新钉零 skip） |
| 单件先跑（driver + collector） | `pytest tests/test_r570_window_shard_driver.py tests/test_collect_evaluation_answers.py …` | `47 passed in 2.87s` rc=0（改窄 `is_git_tree` 之前是 `2 failed / 45 passed`，见 §3） |

全量回归门（`python scripts/run_gate.py`）**没跑**：派工明令归总控。并树后的第二态（`git commit` 之后在干净树
复跑同名件）本席无 commit 权，也交不出 ⇒ 那一遍归总控，别把本纸的数当第二态。

## 7. 未验清单（逐枚点名，宁可写未验）

1. **真机窗未跑**：不动容器、不起服务、不打模型 ⇒ 采集器/driver 两枚闸在**真双写窗**里的效果只有代码级证据，
   真机未证。翻默认已是 pgvector 那一串读数与本单无关。
2. **裸用 transport 的调用方未穷举**（§3 表第 4 行）：本席只证明「经 `main()` 开窗」这一条路被拦，
   没证明「除 driver 之外无人绕过 `main()`」——那要先有一枚全仓调用方名册，本单没造。
3. **~55 枚 `scripts/r*.py` 量具的落点未逐枚查**（层 2 只查了三件）。
4. **两条腿物理未合并**：是否允许 driver `import` 采集器（件头现写不许）——待总控裁；本单只钉了同名同语义同判决。
5. **主树盘面只读了一格**：`企业智脑\scripts\*.jsonl` 现读 0 枚（本席只读，未改主树一字）；主树全树残件名册
   （看板 §6539 那行还记着仓根的 `0001-processing.json`…`0076-done.json` 等）**未查**，处置权不在本席。
6. `app/quality/runner.py` 读 `EVAL_SIDECAR` 那一腿（`APPROVAL_LEDGER_ENV_KEYS`）在本单新钉的
   `EVAL_FRAME_LEDGER` 之下会不会改口：未查（`app/**` 禁区）。
7. 落点检查里的「覆写一枚原有同名件」：差分按枚数读不出来，本单用「三枚落点必须在仓外」补，
   但**没有**证「任何覆写路径都能被这枚补刀抓到」——已知边界，写在 §2 不当作已通过。

## 8. 交回盘面

改件四枚（全部 CRLF、无 BOM、`count(CRLF)==count(LF)==count(CR)` 逐枚自证，读数见本纸末尾的交回表）：
`tests/test_r181_text_frame_ruler.py`、`tests/test_r601_replay_diff_not_disk_state.py`（新）、
`scripts/collect_evaluation_answers.py`、`scripts/eval_window_shard_driver.py`；本纸
`docs/testing/r601-replay-diff-not-disk-state-2026-10-03.md`。
`app/**`、评测集与其 jsonl、`frontend/**`、`migrations/**`、`docs/handoff/**`、`chroma_db/**` 一字未动；
没 commit、没建分支、没改 `.gitignore`、没 pip install、没动容器；测试产物一律落 `--basetemp` 或 `%TEMP%`。

## 9. 交回表（编码逐枚自证：`count(CRLF) == count(LF) == count(CR)`，BOM 全 False）

| 件 | sha256[:12] | 字节 | CRLF | LF | CR | BOM | 行数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tests/test_r181_text_frame_ruler.py` | `eeca5d4c29b9` | 35,498 | 689 | 689 | 689 | False | 690 |
| `tests/test_r601_replay_diff_not_disk_state.py`（新） | `aeda35716eca` | 22,146 | 408 | 408 | 408 | False | 409 |
| `scripts/collect_evaluation_answers.py` | `449d8373285e` | 25,618 | 512 | 512 | 512 | False | 513 |
| `scripts/eval_window_shard_driver.py` | `91600a8a178d` | 40,787 | 762 | 762 | 762 | False | 763 |

（本纸自己的 sha 不自点，免得纸改一字表就自毁；行号一律是本纸写完那一刻在树上 `rg -n` 现读的。）