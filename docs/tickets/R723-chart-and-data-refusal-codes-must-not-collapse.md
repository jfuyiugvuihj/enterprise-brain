# R723 · 同一轮两条腿各拒一次时，图腿的码不许被折成一条（R715 交回件 1，总控亲签）

**号**：R723　**性质**：执行层 R715 就地报回、写域在 R715 之外，按规矩另立单承接　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R715 执行层现读，凭据纸 `docs/testing/r715-2026-10-06.md`）

- `app/agents/evidence.py::_terminal_status` 把 `rejected/permission_denied` 排在最前；图腿 worker 同轮还带 `analyze_data`（`app/agents/orchestrator.py::chart_graph`）。
- 于是数据闸与图闸各拒一次时，`AgentResult.error.code` 折成单一 `permission_denied`，答复侧（`app/agents/nodes.py::_carry_chart_leg_truth`）按「表外闭嘴」不出声 ⇒ 屏上只剩「没有图」，因由丢了。

## 判据（每条可失败）

1. 造一轮「数据腿拒 + 图腿拒（属主无部门）」的合成件 ⇒ 答复正文必须说得出图腿那一格的具名码，且读数面 `agent_results[chart].error.code` 与正文同源；不许再折成单一条。
2. 单腿失败的老形状一字不动：只有一条腿拒时，既有正文与码逐字符不变（`tests/test_r703_*.py`／`tests/test_r710_*.py`／`tests/test_r715_*.py` 复跑仍绿）。
3. 公开码名册不许两本：同一因由在闸码与正文两处必须同名，或按 `app/agents/contracts.py` 的既有映射写明为何不同名；判据形态＝`rg` 谓词现取，不许写行号。
4. 反证牙两枚：① 把折叠顺序退回「rejected 排最前」⇒ 本单新针必红；② 把正文改成硬编码 `permission_denied` ⇒ 同源那枚针必红。摘牙即退回。
5. 交付：同名件两态（dirty ＋ `git worktree add --detach` 干净检出）逐枚清单相同＋凭据纸 `docs/testing/r723-<开工日>.md`＋`tickets_index.py --verify` rc=0＋控制符各 0。

## 写域（只许这些）

`app/agents/evidence.py`（仅 `_terminal_status` 的取码次序/同源）／`app/agents/contracts.py`（仅公开码名册）／`app/agents/nodes.py`（仅 `_carry_chart_leg_truth` 取码那一格）／新增 `tests/test_r723_*.py`／`docs/tickets/R723-*.md`／`docs/testing/r723-<开工日>.md`

## 禁区（踩线即退回）

`app/api/v1/**`／`app/agents/tools.py`（R715 已并）／`frontend/**`／评测夹具与夜窗量具／任何判据阈值与反证钉的存在性／`docs/api/contract-v1.md` 原地改口／主树任何路径。
