# R688 后续 · 五段里剩下的两条腿（retrieve / rewrite）

**来源**：R688（`docs/tickets/R688-stage-event-production-leg.md`）并树后仍欠的两段。本文件**不自派工号**——号、基点、写域由总控开单时定；这里只交「哪两条腿、为什么本单不能修、正确的修法形状是什么」。

## 现状（10-06 现读，执行层亲验）

R688 落地的三段各有一枚可指认的生产发点（`app/agents/nodes.py::classify_intent`／`::plan`／`::respond`／`::reflect_node`／`::synthesize`，读数见 `docs/testing/r688-2026-10-06.md`）。剩下两段：

| 段 | 今天的真实边界 | 为什么 R688 不能动 |
| --- | --- | --- |
| retrieve | `app/agents/tools.py::search_docs`（工具跨度）／`app/rag/retrieval_pipeline.py::RetrievalPipeline.search_for_principal` | 两枚文件都在 R688 写域外；`app/rag/**` 另有 R673（QUEUED）与 R676/R677 在飞 |
| rewrite | `app/rag/retrieval_pipeline.py::QueryRewriter.rewrite`／`app/api/v1/chat.py::_rewrite_followup`，两者都落到 `app/common/model_handler.py` | `app/common/model_handler.py` 是 R690 的在飞写域（对方把 `app/agents/nodes.py` 列成它的禁区）；`app/api/v1/chat.py` 刚被 R670 加过 108 行 |

## 🔴 一条必须先裁的岔路：retrieve 不许照抄「加一行」

`retrieve` 今天**不是零账**：`search_docs` 的工具跨度已经带 `tool_call.finished`，`app/common/stage_timing.py::TOOL_TO_STAGE` 把它归进 retrieve 段（r636 真窗 run18：retrieve 74/105 产账）。再在同一区间发一枚 `stage.finished`，就是**同一段两把尺**——`aggregate_stage_latency` 只剔「严格包含」的那一侧，等长区间会记进 `unresolved_pairs`，`within_one_percent` 从此永闭。这正是 R51② 那一格的死法。

所以 retrieve 只有两条正解，请总控二选一后另立单：

- 甲（推荐，零新件）：**承认工具跨度就是 retrieve 段的账**，把判据① 的口径从「五段各有 ≥1 枚 stage 事件」写成「五段各有 ≥1 枚段账（stage 事件或已归段的跨度）」，读侧（`scripts/r631_stage_sum_delta.py`／R674 导出）相应把 tool/model 跨度并进五段视图。app/** 一字节不动。
- 乙（发 stage 件，但要搬家）：把 retrieve 的**唯一**记账权交给 `stage_account`，同时让 `app/agents/tools.py::search_docs` 的工具跨度不再归段（改 `TOOL_TO_STAGE` 或摘掉那条映射）。这会动在册归因表与在册钉，代价明显大于甲。

## rewrite：这条腿是真的没有尺，但也真的接不了 `config`

`app/api/v1/chat.py::_rewrite_followup` 与 `app/rag/retrieval_pipeline.py::QueryRewriter.rewrite` 的签名里**都没有 config/主体**，两者都走 `app/common/model_handler.py` 的非流式 `chat()`，而 r636 的 AST 读数证明 `model_handler.py` 里 `start_model_call`／`start_tool_call`／`ExecutionSpan`／`record_stage_event` 一枚都没有。于是这一腿既没有跨度，也没有身份 —— `stage_account` 给它发件只会撞「无主不记」那条规矩（写零字节）。

要落地需要三件事一起（缺一即静默失效）：

1. 把身份送进去：给 `_rewrite_followup`／`QueryRewriter.rewrite` 加一个可选 `config`（或 `principal`）形参，调用点把本轮 config 传下去；
2. 在边界上开一枚 `app/trace/spans.py::stage_account(config, stage="rewrite")`——这一段区间今天没有第二把尺，所以**不会**双记；
3. 与 R690（`model_handler.py` 的 stream usage）错开写域：要么等它并树，要么由总控把这三处切成一枚独立单。

验收判据的形状（给未来的单照抄）：`stage_emit_points()` 现读必须交回 `rewrite` 段 ≥1 枚 `文件::符号`；`tests/test_r688_stage_accounts_are_landed.py::assert_stage_accounts` 里 retrieve/rewrite 那一格「没落地的段必须零枚」会当场红并点名——那正是本单留下的可失败钉，红了就说明账要跟着改口径。

## 不许顺手做的事

- 不许在 `app/**` 之外（tests／scripts／评测夹具）发 stage 件来凑五段：`scripts/r636_stage_coverage.py::call_sites_of` 只认 `app/**`，派工侧也写明「tests／scripts 里的调用点不算产品道」。
- 不许改 `scripts/r636_stage_coverage.py` 的在册谓词来「让账面一致」：那是夜窗量具。R688 并树后它有一条散文谓词已经过期（见交付纸「尺与钉的冲突」那一格），归总控裁。