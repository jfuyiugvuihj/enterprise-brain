# R696 · retrieve 段甲案落地（读侧并段，`app/**` 一字节不动）

**号**：R696　**基点**＝派工那一刻主树 HEAD 现取　**执行时机**：🔴 **排在夜窗之后**——本单要改 `scripts/r631_stage_sum_delta.py` 与 `scripts/r674_window_trace_export.py`（夜窗量具），窗内禁动；且它的验收需要今晚 run32／run33 交出的真窗导出件当分母。

## 现取病形（总控 10-06 亲读）

retrieve 今天**不是零账**：`app/agents/tools.py::search_docs` 的工具跨度已带 `tool_call.finished`，`app/common/stage_timing.py::TOOL_TO_STAGE` 已把它归进 retrieve 段（r636 真窗 run18＝retrieve 74/105 产账）。但 `scripts/r631_stage_sum_delta.py` 只认 stage 事件，不认「已归段的跨度」⇒ 五段视图少一段。

## 为什么不能改成「再发一枚 stage 件」（总控已裁定，别再试）

同一段放两把尺：`aggregate_stage_latency` 只剔**严格包含**的那一侧，等长区间会记进 `unresolved_pairs`，`within_one_percent` 从此永闭——**这正是 R51② 那一格的死法**。所以甲案是唯一零新件的解。

## 判据（每条可失败）

1. **两栏并报，不撤原口径**：`r631` 的读数必须同时交回「stage 事件口径」与「段账口径（stage 事件 ∪ 已归段跨度）」两栏，原口径那一栏的数字**一字不改**（改口径＝自改判据，退回）。🔴 判据原文 `S21CELL::跟进单 §21::R51::②` 那格仍然按原口径判，本单只加一栏并写明差异。
2. **双记必须被拒**：新加一枚反证牙——同一段既有 stage 事件又有归入同一区间的跨度时，并段逻辑不得把区间算两次；把去重那一行摘掉 ⇒ 牙必须红。
3. **今晚读数当分母**：对 `%TEMP%\evalrun\run32`／`run33` 的导出件各跑一遍，两栏覆盖段数逐枚点名（retrieve 在段账口径下应从「缺」变「有」）；<1% 那一格由这两枚读数判，本单**不许**拿离线合成件宣布达。
4. **R674 导出器同步**：`scripts/r674_window_trace_export.py` 的窗按题导出必须带得上跨度归段所需的字段；缺字段 ⇒ 明写「未测」，不许静默补零。
5. **夜窗纪律**：本单执行时窗必须已结束；改完必须复跑 `tests/test_r636_stage_coverage.py`／`tests/test_r631_*` 与账尺 `scripts/audit_plan_ticket_ledger.py`（RESULT=PASS）。
6. **交付**：两态同名件数字＋今晚两枚窗的真读数（逐枚点名 rc／秒数）＋控制符各 0＋坐标 `文件::符号`＋凭据纸 `docs/testing/r696-<开工日>.md`。

## 写域（只许这些）

`scripts/r631_stage_sum_delta.py`／`scripts/r674_window_trace_export.py`／新增 `tests/test_r696_*.py`／`docs/testing/r696-<开工日>.md`／`docs/tickets/R696-*.md`

## 禁区

`app/**` 全部（甲案的要点就是产品码零动）／`frontend/**`／评测夹具与判分器／`docs/handoff/**`／`docs/api/contract-v1.md`／`scripts/run_gate.py`／`pyproject.toml`／容器·镜像·模型动作／主树任何路径。
