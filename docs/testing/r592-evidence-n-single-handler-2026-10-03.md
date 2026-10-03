# R592 · `evidence_n` 在判读件里只许一枚取数把手（2026-10-03）

- 单号：R592（执行层自取代号 **Curie**）｜ 基点 `a5ba2d7` ｜ 工作树 `C:\Users\fengx\PycharmProjects\be-r592b`（分支 `codex/be-r592b`）
- 写域：`scripts/eval_lane_readout.py` ＋ 本件 ＋ `tests/test_r592_evidence_n_single_handler.py`
- 全程离线：只读 `docs/testing/` 在册样本与 `%TEMP%\r592-sample\` 的 run16 只读副本；零模型（8001/11434 一枚都不去）、零容器、零库、不跑全量门；主树 `企业智脑\` 一个字节未写，`%TEMP%\evalrun\run17.*` 一枚未读。
- 🔴 路径让路：派工词指定的 `be-r592` 目录 10-03 11:3x 现读已被 9-26 那枚旧 R592（＝R59 块2，`dbc2047` 已并树）占用，其分支 `codex/be-r592` 停在 `d194d99`，树内还有三枚未跟踪 `test_r592_*.py`（内容已在 `a5ba2d7` 树里）。本席不删别人的树，改用 `be-r592b`／`codex/be-r592b`，同号双投的坑如实记这一笔。

## 1 缺陷本体与取证（判据①：先取证再改）

同键名 `evidence_n`，两处把手读的是**两本不同的账**（行号＝基点 `a5ba2d7` 的 `scripts/eval_lane_readout.py`）：

| 位置 | 原文形状 | 读的是哪本账 | 对错 |
|---|---|---|---|
| `:201`（+`:202` 打印） | `[(str(r["id"]), r.get("evidence_n")) for r in frames if int(r.get("evidence_n") or 0) == 0]` | **帧账行**（`frames = load_jsonl(frames_path)`，`:111`；件名 `sidecar-<label>-frames.jsonl`，`:101`） | 🔴 错 |
| `:224-228`（打印在 `:229`） | `[(str(r["id"]), r.get("evidence_n"), len(answers[...])) for r in frames ...]` | **帧账行** | 🔴 错＝那行「两本账不等」 |
| `:246`（逐枚表 `evidence_n` 列） | `(sidecar.get(str(r["id"])) or {}).get("evidence_n")` | **sidecar 行**（`sidecar = {...load_jsonl(sidecar_path)}`，`:112`；件名 `sidecar-<label>.jsonl`，`:102`） | ✅ 对 |

⇒ 两处不是「键名不同」，而是**行对象不同本**：`evidence_n` 只住在 sidecar 行里，帧账行从来没这一格。现读计数（本席亲取）：

- run16 副本：sidecar 行 `evidence_n` **12/12 有**，帧账行 **0/12 有** ⇒ 错的那两处恒读 `None`，`int(None or 0)` 恒等于 0。
- 在册 `docs/testing/sidecar-run9.jsonl`：**105/105 有**；`sidecar-run9-frames.jsonl`：**0/105 有**。两本文件共享 `id/kind/attempt/sentinel/answer_chars` 那一截同形字段，这就是把手串本的可乘之处。

`None` 冒充零枚造成的两格假话，在两本账上同样成立（改前读数原样留在 `%TEMP%\r592-sample\run9-before.txt`）：

| 读数 | run16（12 枚） | 在册 run9（105 枚） |
|---|---|---|
| `侧车 evidence_n ↔ answers.evidence 枚数不等` | 11 枚，逐枚带 `None` | 72 枚，72 个 `None` |
| `sidecar.evidence_n=0 的题号` | 全 12 枚（真零只有 `report-11` 一枚） | 全 105 枚（真零只有 33 枚） |

而两本账**本来就是齐的**：run16 逐枚 `sidecar.evidence_n` 与 `len(answers.evidence)` 12/12 相等（14/6/9/14/9/14/12/5/10/13/0/14）；在册 run9 逐枚对判真不等 **0 枚**。同一件程序的表格列当时打印的正是 14/6/9——两处互打脸。

## 2 为什么必须治（这族假话的害处是具体的）

那行打印是「立案线索」形状的：下一班照它抄进跟进单，就会立一枚**根本不存在的**「sidecar 与 answers 两本账口径不齐」，并顺着去查一台没病的账。同族转抄假话今天已是本班第二次（跟进单 §157 刚自纠一枚），AGENTS.md 明写引用数字前先查有没有被后续实测推翻——所以这单不是「顺手改个显示」，是把把手钉成只有一枚。

## 3 修法（判据②：同一枚取数把手只留一处）

`scripts/eval_lane_readout.py`（新行号）：

- `:74` `SIDECAR_EVIDENCE_KEY = "evidence_n"` ＋ `:76-80` 五枚状态名（`EV_OK / EV_NO_ROW / EV_NO_KEY / EV_NULL / EV_NOT_INT`）。
- `:83-100` `sidecar_evidence_n(sidecar_rows, row_id) -> (枚数, 状态)`：全件唯一把手。缺行／缺键／值为 null／值不是整数一律交 `None` 并点名状态；真读到 0 才交 0。`bool` 明写不吃（`True` 不许冒充 1 枚）。
- `:158-159` `ev_readings = {rid: sidecar_evidence_n(sidecar, rid) for rid in sorted(set(sidecar) | set(answers) | set(by_id))}` —— 全件只在这一处取一次。
- 四处消费同一份读数，不许再各自把手：`:246` `=0` 名册、`:247-250` 新增的「取不到」名册、`:272-280` 两本账对判、`:293`/`:298` 逐枚表那一列。
- 判词形状没放宽：`:276` 那枚 `continue` 只跳过「取不到」的题号，而它们已由 `:249` 逐枚点名——既不冒充「不齐」，也不冒充「齐」，更不折算成零枚；`None` 也不算齐（`:277-278` 值在而数目不等照旧逐枚点名 `(题号, 侧车枚数, 交回枚数)`）。那一行打印本身一字未改，只改它读的键来自哪本账。
- 表格列取值改为：读到数打数字，取不到打状态名（不再是暧昧的裸 `None`）——run16/在册 run9 逐枚有值，两枚表格字节一字未动（见 §6）。

## 4 常驻牙：`tests/test_r592_evidence_n_single_handler.py`

五格，全部离线，只读在册样本，变异落 `tmp_path` 或件内自造样本，被跟踪文件一个字不改：

- ① 在册 run9 三件套正面：`不等` 必须 `无` 且整行不许出现 `None`；`=0 的题号` 必须逐枚等于文件里真零那 33 枚（不许全列点名）；`取不到` 必须为 `无`。样本前提也钉死：sidecar 逐枚有这一格、帧账一枚都不带、两本账逐枚全等——样本哪天变了，钉先自曝，不静默改口径。
- ② 同源：逐枚表 `evidence_n` 那一列 105 枚逐枚等于 sidecar 原文读数（表格列与那行「不等」同取 `ev_readings`）。
- ③ 真缺必须如实报缺：件内自造最小 sidecar 行（`MISSING_SIDECAR_ROWS`，report-02 那一行压根不写这一格）⇒ 点名 `('report-02', 'sidecar 缺 evidence_n 格')`，且 `=0` 名册必须为空、`不等` 必须为 `无`、表格那一格必须打状态名而不是裸 `None`。另 6 枚参数化钉逐一点名把手的五种状态（含 `0` 读成零、`3.0`/`True` 不吃）。
- ④ 判据不许放宽：把交回侧削掉一枚 ⇒ `不等` 必须正好 `[('report-01', 14, 13)]`。
- ⑤ 结构钉（AST）：全件 `evidence_n` 的取数只许出现在那一枚把手的行区间内（第二处即红）；把手只许被调用一次且只喂 `sidecar` 那本账（喂 `by_id`＝原缺陷的语义等价形，直接红）；`ev_readings` 至少被四处 Load。

在册样本＝件内不复制、不生成、不改写：跑的是 `docs/testing/sidecar-run9.jsonl` / `sidecar-run9-frames.jsonl` / `answers-run9.jsonl`。

## 5 反证三把（判据④：摘前/摘后 sha256 前 12 ＋ 逐字节还原）

命令：`python -X utf8 %TEMP%\r592_knife.py`（每把＝快照字节→变异→跑同名件→写回快照→复算 sha）。原文与红绿清单落 `%TEMP%\r592-sample\knives.txt`。

| 刀 | 文件 | 摘前 sha12 | 变异后 sha12 | 还原后 sha12 | rc | 末行（原文） |
|---|---|---|---|---|---|---|
| K1a 整件退回错的那一版（`git show a5ba2d7:scripts/eval_lane_readout.py`） | `eval_lane_readout.py` | `87cc31b5dd70` | `c8c80e17e8cb` | `87cc31b5dd70` ✅ | 1 | `12 failed, 1 passed in 0.83s` |
| K1b 把手留着但喂帧账行（`sidecar_evidence_n(by_id, rid)`） | 同上 | `87cc31b5dd70` | `d718dfcc71e1` | `87cc31b5dd70` ✅ | 1 | `6 failed, 7 passed in 0.85s` |
| K2 从正面样本真删 `evidence_n`（`SIDECAR_ROWS[0]` 那一枚） | `test_r592_...py` | `e2b759096fe2` | `d7c6c587f57e` | `e2b759096fe2` ✅ | 1 | `2 failed, 11 passed in 0.60s` |

- **K1a 红 12 枚**（逐枚点名）：`test_in_book_run9_prints_no_evidence_n_as_missing`、`test_a_present_value_is_never_printed_as_missing`、`test_a_dropped_cell_is_reported_as_missing_not_as_zero_or_unequal`、`test_a_real_difference_is_still_named_per_id`、`test_only_one_handler_in_the_whole_script_reads_evidence_n`、`test_the_handler_is_fed_the_sidecar_book_and_used_from_one_reading`、`test_the_handler_names_why_it_cannot_read[×6]`。🔴 **唯一一枚绿的也如实记下**：`test_table_column_and_the_mismatch_line_share_one_reading` 在错版本里照旧绿——因为旧代码的表格列本来就取对了 sidecar。这正证明「只钉表格列」拦不住这枚假话，①②两枚必须成对存在。
- **K1b 红 6 枚**：`test_in_book_run9_...`、`test_a_present_value_...`、`test_a_dropped_cell_...`、`test_a_real_difference_...`、`test_table_column_...`、`test_the_handler_is_fed_the_sidecar_book_and_used_from_one_reading`。它**绿的 7 枚**＝结构钉 `test_only_one_handler_in_the_whole_script_reads_evidence_n` ＋ 参数化 6 枚：这一刀没动把手本身，只把喂给它的那本账换掉，所以「只许一枚把手」与「五种状态」两枚都不该红，也确实没红。两把刀各咬一侧：K1a 咬「不许有第二处把手」，K1b 咬「把手只许吃 sidecar」。
- **K2 整件红 2 枚**：`test_a_present_value_is_never_printed_as_missing`（＝「不许打印成缺失」那一枚，**该红**）与 `test_a_real_difference_is_still_named_per_id`（它的样本也从 `SIDECAR_ROWS` 取，属预期连带红）。
- **K2 分格点名**（各带 `-k` 单跑同一份变异）：`test_a_dropped_cell_is_reported_as_missing_not_as_zero_or_unequal`（「如实报缺」那一枚）＝**绿**，`1 passed, 12 deselected in 0.58s`，rc=0；`test_a_present_value_is_never_printed_as_missing` ＝ **红**，`1 failed, 12 deselected in 0.59s`，rc=1。
- 三把刀之后 `git status --porcelain` 与 sha 均回到交回态：`scripts/eval_lane_readout.py` = `87cc31b5dd70`，`tests/test_r592_evidence_n_single_handler.py` = `e2b759096fe2`（`CLEAN sha` 行原文见 `knives.txt` 末行）。
## 6 改前 / 改后：对同一份 run16 **只读副本**的打印差

副本自证（原件只读复制，一枚未写）：`run16-sidecar.jsonl` `cd7278bd7bcf`、`run16-answers.jsonl` `d4635dd0c1fe`、`run16-sidecar-frames.jsonl` `7d8fee83cf6b`——原件与副本 sha256 前 12 逐枚全等，交回前（12:0x）又现取复比对一遍，仍全等。读数原文留 `%TEMP%\r592-sample\readout-before.txt` / `readout-after.txt`。

```diff
@@ run16 读数（--sidecar/--answers/--frames 指向 %TEMP%\r592-sample）@@
-- sidecar.evidence_n=0 的题号=['report-01', 'report-02', 'report-03', 'report-04', 'report-05', 'report-06', 'report-07', 'report-08', 'report-09', 'report-10', 'report-11', 'report-12']
+- sidecar.evidence_n=0 的题号=['report-11']（真读到 0 枚才算零，共 1 枚）
+- sidecar.evidence_n 取不到的题号=无（取不到≠零枚，也≠两本账不齐，共 0 枚）
-- 侧车 evidence_n ↔ answers.evidence 枚数不等=[('report-01', None, 14), ('report-02', None, 6), ('report-03', None, 9), ... 共 11 枚]
+- 侧车 evidence_n ↔ answers.evidence 枚数不等=无（两本账说的必须同一件事）
```

整件输出 57 行 → 58 行，差异**只有**上面这四行（新增那行取不到名册 ＋ 改写的两行）；16 列逐枚表字节一字未动，`evidence_n` 那一列改前改后都是 14/6/9…。在册 run9 同形：`不等` 由 72 枚（72 个 `None`）→ `无`，`=0` 名册由 105 枚全列 → 真零 33 枚。

## 7 复跑凭据（脏态；命令原文照抄可跑）

工作目录一律 `C:\Users\fengx\PycharmProjects\be-r592b`，解释器读主树 `.venv`：

```powershell
$py = 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe'
# 新钉（两遍各跑一次，防状态泄漏）
& $py -X utf8 -m pytest tests/test_r592_evidence_n_single_handler.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\final1" -q   # rc=0 → 13 passed in 0.73s
& $py -X utf8 -m pytest tests/test_r592_evidence_n_single_handler.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\final2" -q   # rc=0 → 13 passed in 0.42s
# 在册邻居（同件判据⑥那三格读数钉）
& $py -X utf8 -m pytest tests/test_r447_queue_approval_round_and_evidence.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\final3" -q   # rc=0 → 23 passed in 0.73s
# 两档同进程共跑（防读数件 import 串状态）
& $py -X utf8 -m pytest tests/test_r592_evidence_n_single_handler.py tests/test_r447_queue_approval_round_and_evidence.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\final4" -q   # rc=0 → 36 passed in 2.75s
# 读数件本体两本账各跑一次（离线，只读）
& $py -X utf8 scripts/eval_lane_readout.py --dir docs/testing --label run9   # rc=0，151 行：不等=无 / 取不到=无 / =0 名册 33 枚
& $py -X utf8 scripts/eval_lane_readout.py --label run16 --sidecar "$env:TEMP\r592-sample\run16-sidecar.jsonl" --answers "$env:TEMP\r592-sample\run16-answers.jsonl" --frames "$env:TEMP\r592-sample\run16-sidecar-frames.jsonl"   # rc=0，58 行：不等=无 / 取不到=无 / =0 名册 1 枚
```

- 🔴 时间线自证（`Get-ChildItem | Sort-Object LastWriteTime` 现取）：反证刀组的最后一写在 11:52:32（脚本还原）／11:53:24（钉件还原＋`knives.txt` 落盘），交回态两枚文件的 mtime 就是这两笔——sha 也回到摘前值（`87cc31b5dd70`／`e2b759096fe2`）；**上面四道复跑与追加那枚全部落在 12:02:13–12:05:26，严格晚于反证**，留痕逐笔点名：`final-pin1.txt`／`final-pin2.txt`／`final-r447.txt`／`final-both.txt`／`h1.txt`（都在 `%TEMP%\r592-sample\`），末行原文 `13 passed in 0.73s`／`13 passed in 0.42s`／`23 passed in 0.73s`／`36 passed in 2.75s`／`13 passed in 0.82s`。11:47–11:51 那一批（`pin-run*`／`t-run*`／`z*`／`both`／`pin-clean`）不再引用：它们跑在纸面与钉件定稿前的旧字节上，属字节漂移，不是被反证刀污染。
- 上面四个数字是在**交回态字节**上现取的：`scripts/eval_lane_readout.py` sha256 前 12＝`87cc31b5dd70`（18643 字节），`tests/test_r592_evidence_n_single_handler.py`＝`e2b759096fe2`（15058 字节）；本纸 sha12 见交回盘面。
- 反证之后又追加一枚复跑（`--basetemp=$env:TEMP\h1`）＝`13 passed in 0.82s`，rc=0：同一份字节第三遍仍绿。
- 编码自证：`scripts/eval_lane_readout.py` CR=LF=CRLF=306、无 BOM；`tests/test_r592_evidence_n_single_handler.py` CR=LF=CRLF=280、无 BOM；`py_compile` 两枚 rc=0。
- 邻居写域一枚未碰：`scripts/eval_window_shard_driver.py`、`scripts/collect_evaluation_answers.py`、`scripts/eval_transport_ask*.py`、`tests/fixtures/**`、`app/**`、`tests/conftest.py`、`frontend/**`、`deploy/**`、`docs/handoff/**` 全部零改动（`git status --porcelain` 只有上面两枚）。

## 8 没验的格子（如实列出）

1. **干净树复跑未做**：本席按规矩不 commit，第二遍（`git commit` 之后同名件复跑）交回总控做——两态文件清单＝`scripts/eval_lane_readout.py` ＋ `tests/test_r592_evidence_n_single_handler.py` ＋ 本纸。
2. **全量回归门未跑**（派工词禁止）：`scripts/run_gate.py` 一枚都不欠；并树时由总控按同一 HEAD 复跑数与看板最新绿票对账。
3. 反证只验到「新钉红/绿」这一层，**没验**其它件会不会跟着改口径：`tests/test_r447_*`（23 枚）与读数件其它段落只做到复跑全绿，未逐格重判。
4. run16 副本只验了「两本账逐枚全等」这一格，**没验** run16 的 D-3 判词本身（`report-11` 出处为零那格仍归 R591/R582 的账，不属本单）。
5. `%TEMP%\evalrun\run17.*`（在跑产物）一枚未读、未引为凭据；在册 run9 与 run16 副本之外没有第三本账可比。
