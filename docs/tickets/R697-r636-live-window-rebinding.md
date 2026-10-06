# R697 · 把 r636 真窗对账组接到存活窗（13 枚 skip 变绿的唯一正解）

**号**：R697　**基点**＝派工那一刻主树 HEAD 现取　**执行时机**：🔴 **必须在夜窗之后**——本单要改 `tests/test_r636_stage_coverage.py` 的 `WINDOWS`  tuple，并要靠今晚 run32／run33 交出的导出件当分母。

## 现取病形（总控 10-06 12:5x 亲读）

- `tests/test_r636_stage_coverage.py::WINDOWS` 现取＝`("run18", "run19", "run20k")`；`real_inputs` 那组 skipif 要求每扇窗三本件齐（`<w>-traces.jsonl`／`<w>-sidecar.jsonl`／`<w>-sidecar-frames.jsonl`）。
- 盘上现取：`%TEMP%\evalrun` 只有 run30／run30d／run31 的 sidecar 两本，`*-traces.jsonl` 枚数＝**0**；`docs/perf/raw` 只有 p3-2026-09-26／r470-2026-09-29／r561-2026-10-01／run10-2026-09-30／run11c-2026-10-01 五枚目录，`*-traces.jsonl` 枚数＝**0**。⇒ 那 13 枚 skip 与今天的代码无关，是**账钉在已经不存在的窗上**。
- 后果：R51② 与 R44① 的真窗那半**永远量不到**（组不参与判语＝不会红也不会绿，这正是假账温床）。

## 判据（每条可失败）

1. `WINDOWS` 换成存活窗名（今晚起＝`run32`／`run33`／`run32d` 里实际有导出件的号），逐枚点名换进去哪几枚、为什么剔掉 run18／19／20k（剔由「盘上没件」这个事实驱动，不许写成「这些窗作废」这种没有凭据的话）。
2. 🔴 **不许摘牙**：那 13 枚必须是**跑起来了**（passed 或有名读数），不是被改成 skip／xfail／删掉。交付里给改前改后的 `passed／skipped／failed` 三枚计数。
3. **导出件在位谓词自己写**：新加一枚钉，断言每台在册窗的三本件存在且字节 >0；任何一本缺失 ⇒ 那枚钉红并点名缺哪本、在哪个目录。这把「窗名」与「盘上件」绑死，下一班就不会再拿不存在的窗当分母。
4. **不动尺的谓词**：`scripts/r636_stage_coverage.py` 本体属夜窗量具，只读取证；若必须同步改尺才绿，停下写进交付由总控裁。
5. **交付**：两态同名件数字＋今晚两枚窗的真读数（逐枚 rc／秒数）＋控制符各 0＋坐标 `文件::符号`＋凭据纸 `docs/testing/r697-<开工日>.md`＋`python scripts/tickets_index.py --verify` rc=0。

## 写域（只许这些）

`tests/test_r636_stage_coverage.py`／新增 `tests/test_r697_*.py`／`docs/testing/r697-<开工日>.md`／`docs/tickets/R697-*.md`

## 禁区

`app/**`／`frontend/**`／`deploy/**` 与任何 `.env*`／评测夹具与判分器／`docs/handoff/**`／`docs/api/contract-v1.md`／`scripts/run_gate.py`／夜窗量具 `scripts/eval_*`·`r57*`·`r59*`·`r63*`·`r674*`／容器·镜像·模型动作／主树任何路径。
