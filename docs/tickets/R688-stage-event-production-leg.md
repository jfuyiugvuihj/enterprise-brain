# R688 · 五段事件的生产腿（R51② 的真病根）

**号**：R688　**基点**：现取主树 HEAD（派工时写进名册）
**写域**：`app/agents/nodes.py`／`app/common/stage_timing.py`／`app/trace/spans.py`／新增 `tests/test_r688_*.py`／`docs/tickets/R688-*.md`／`docs/testing/r688-<开工日>.md`
**禁区**：`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与 `tests/test_evaluation_report.py`／`scripts/run_gate.py`／`pyproject.toml`／`deploy/.env.server`／`scripts/eval_*`／`scripts/r57*`／`scripts/r59*`／`scripts/r63*`／`scripts/r674*`／任何容器镜像模型动作／主树任何路径。

## 现取病形（总控 10-06 亲验，不是执行层转述）

`rg -n "record_stage_event" --glob "*.py" app tests scripts` 现取：`app/**` 里只有两处——`app/trace/spans.py::record_stage_event` 的定义与 `__all__` 里那一行；`stage_window` 同样只有 `app/common/stage_timing.py` 的定义与 `__all__`。**产品道零调用点**。⇒ 五段事件（`app/common/stage_timing.py::CANONICAL_STAGES` 现取＝classify／rewrite／retrieve／generate／reflect）从来没被发过，`r631 --window` 对 run22／run25／run30 各 rc=3 是空输入，不是导出器缺件（导出器已由 R674 并树 `ef42b6b`）。

## 判据（每条可失败，缺一判负）

1. 行为钉：走一次生产问答（离线夹具、零真模型、`LOCAL_MODEL_NAME` 哨兵口径不变），答案件落地后 `events.jsonl` 里**五段各有至少一枚** stage 事件，且段名逐枚等于 `CANONICAL_STAGES` 的字面（自造段名必须被拒）。
2. 同笔给一枚反证牙：把其中一段的发点摘掉 ⇒ 判据 1 的钉当场红并点名那一段；这条是防「只补了三段也算过」。
3. 🔴 **在册口径必须同批改口、且不许摘牙**：`scripts/r636_stage_coverage.py` 现在把「`app/**` 里 `record_stage_event` 调用点枚数 == 0」当事实写进取证纸，`tests/test_r636_stage_coverage.py` 有一枚钉断言 `call_sites_of(...) == []`。R688 并树会让那枚钉红——这是**设计内的口径迁移**：把那条断言改成「调用点枚数 >= 1 且每段发点可指认」，改口写进交付并逐枚点名改了哪一枚断言、为什么。🔴 但 `scripts/r636_stage_coverage.py` 本体属**夜窗量具**，今晚在跑——本单**不许动它**，只许改那枚钉；钉与尺若必须同步改才绿，停下写进交付由总控裁，不许偷偷改尺凑绿。
4. 分段加总与端到端误差 <1% 这一格**不在本单翻绿**：翻它要真窗读数（`r631`），本单只交「五段有生产发点」这一半。明写「R51② 仍待窗」，不许写成达。
5. 计时纪律：五段计时不得阻塞热路径（`app/agents/nodes.py` 里逐片直发那一段已有计时钉 `tests/test_r149_sse_text_pieces.py`／`tests/test_r661_trace_journal_hot_path_teeth.py` 守着，安静串行必须仍然绿；读数逐枚贴进交付）。
6. 交付：同名件两态读数（dirty／干净检出各一遍，文件清单逐枚相同）、`rev-list --count <基点>..HEAD`、未跟踪逐枚点名、控制符 `0x00/07/08/0b/0c` 各 0 枚、坐标一律 `文件::符号`（出现 `*.py:数字` 即本单作废）。

**派工词只送指针**：读 `docs/tickets/R688-*.md` 照做。规格住在文件里，不住在消息里。