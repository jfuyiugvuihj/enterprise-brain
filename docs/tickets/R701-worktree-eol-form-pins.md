# R701 · 盘形行尾钉：同一棵树被要求两种相反的行尾，每次并树都要重新误红一次

**号**：R701　**性质**：总控亲签（本轮由总控亲写亲跑，不再占执行层席位——夜窗之前每一笔并树都要付这笔误红税）　**基点**＝开工那一刻主树 HEAD 现取

## 现取病形（总控 10-06 13:4x 亲测，四条读数）

- 机器口径：`git config --get core.autocrlf` ＝ `true`，仓库**没有** `.gitattributes`（`git check-attr text eol --` 对下面两本都回 `unspecified`）。
- 钉 A（要求盘上纯 LF）：`tests/test_r469_readout_is_generated.py::test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits` 里 `assert b"\r" not in raw`；钉 B（要求盘上成对 CRLF）：`tests/test_r492_s93_column_matches_derived.py::read_rows` 里 `assert raw.count("\r") == raw.count("\n")`。两枚读的是**不同的两本**，但要求的是**相反的盘形**。
- 现场字节读数（`git archive HEAD` 解到临时目录，本机 autocrlf 生效）：`docs/perf/r387-label-lineage-2026-09-27.md` 交 CR=947／LF=947（钉 B 绿、钉 A 若读它必红）；`docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 交 CR=7194／LF=7194（钉 A 当场红，报错形如 `At index 66 diff: b"\r" != b"\n"`）。
- 主树今天之所以两枚都绿，只因为总控在**盘上**把 r469 那本手工改成 LF（`git diff` 为空＝并树带不走）：重新 checkout 一次它就再红。这就是 R693 state① 那两枚「行尾环境件」真红的全部成因——不是货坏。
- 在册同形共 4 枚：`scripts/r547_scope_verdict_gauge.py::read_rows`、`tests/test_r490_live_reads_match_derived.py::read_rows`、`tests/test_r492_s93_column_matches_derived.py::read_rows`（这三枚读盘，受害），`tests/test_r693_land_s93_column.py` 那一枚读的是内存里显式 `newline=` 生成的文本（**不受害，一字节不动**）。

## 判据（每条可失败，缺一枚判负）

1. **只治盘形，不松真判据**：行尾断言一律改成「要么纯 LF（CR 枚数＝0），要么成对 CRLF（CR 枚数＝LF 枚数），混了就红」。文本内容的相等比较不许放松——把 r469 表里任一数字改一位，钉必须红。
2. **两种盘形都要绿**：同一笔货在（a）主树当前盘形与（b）`git archive HEAD` 干净检出（autocrlf 生效）两种盘形下，同名件读数必须同为全绿；两态数字逐枚贴进凭据纸。
3. **反证牙**：新增 `tests/test_r701_counter_evidence_teeth.py` 至少三枚，全离线、零 `app` import——① 喂一段混行尾（CR 枚数既不＝0 也不＝LF 枚数）⇒ 谓词必红；② 把生成件里一位数字改掉 ⇒ r469 的相等比较必红；③ 把盘上那份强制换成 CRLF ⇒ 谓词仍绿（因为成对）。
4. **卫兵不许坏**：复跑 `python scripts/lint_hand_copied_coordinates.py --check`（rc=0）与 `python scripts/tickets_index.py --verify`（rc=0）；本单不得新增 `文件:数字` 形态坐标；交付自带控制符（00/07/08/0b/0c）＝0 枚自证。
5. **不许借这一单做全仓 renormalize**：`.gitattributes` 与 `git add --renormalize` 属**业主裁定**（改的是所有人的 checkout 形状），本单一枚都不许碰。
6. **交付**：凭据纸 `docs/testing/r701-<开工日>.md` ＋ `git rev-list --count <基点>..HEAD` ＋未跟踪逐枚点名 ＋坐标一律 `文件::符号`。

## 写域（只许这些）

`scripts/r701_eol_form.py`（新增谓词单一真源）／`scripts/r547_scope_verdict_gauge.py`／`tests/test_r490_live_reads_match_derived.py`／`tests/test_r492_s93_column_matches_derived.py`／`tests/test_r469_readout_is_generated.py`／新增 `tests/test_r701_*.py`／`docs/tickets/R701-*.md`／`docs/testing/r701-<开工日>.md`／`docs/tickets/index.tsv`

## 禁区（踩线即退回）

`.gitattributes`／任何 renormalize／`app/**`／`frontend/**`／`docs/handoff/**`／`docs/perf/**` 与 `docs/testing/**` 里被钉的那些本体的**内容**（只许改测试件里的行尾断言）／评测夹具与判分器／夜窗量具 `scripts/eval_*`·`r63*`·`r674*`·`r634*`·`r636*`·`r631*`／`scripts/run_gate.py`／`pyproject.toml`／容器·镜像·模型动作／主树外的任何树。

## 这一枚为什么存在

每一笔并树都要付「先红 vs 我造成」的归因税，而这两枚钉天天在量**本机 checkout 的行尾**而不是产品行为。不治好，今晚 R695／R699／R700 三笔并树各要再付一次。