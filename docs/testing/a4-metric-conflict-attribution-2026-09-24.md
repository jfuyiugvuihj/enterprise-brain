# A④ 归因：『口径冲突』族 run5→run6 真退化的逐题凭据（2026-09-24，主树 `7f78dd0`，run6 现场产物）

> 判分口径与客户看到的那份报告是**同一个函数**（`app.quality.eval._is_correct`，逐字子串匹配），总控在主树现算，没有另造第二套判分器。

## 0. 三条结论，每条都可证伪

1. **这枚退化是真的，不是尺子坏。** 本族 19 题的 `must_contain` 词条，**19/19 全部在语料里存在**（`documents/*.txt` 共 140609 字）⇒ 没有一道是「字面永远对不上」的死题。全量 105 题里带不可达词条的有 **30 题**，但它们**一道都不在本族**（分布在 Excel计算／主动洞察／多轮对话／审批判断／工具调用／报告生成／文档问答／无证据问题／跨部门权限）。
2. **复算与正式报告逐位吻合**：本文重算 `6/19 = 0.3158`，报告 `category_metrics.口径冲突.correctness = 0.3158` ⇒ 下面那张题号表是报告的同源读数。
3. **失败模式高度结构化**：13 道失败题里，缺的都是**语料中那枚「口径原话」**（例如 `费用以发生月归属` 与 `费用以入账月归属` 是一对）。模型把口径的**意思说对了、字面换了**，按逐字匹配就判错。⇒ 病灶在「**答案没把检索到的那句口径原文带进正文**」，不在检索没找到：本族 `evidence_coverage` 同期**上升** 0.3684 → 0.5263、`correctness` **下降** 0.4211 → 0.3158，两条反向一起动，正是这个形状。

## 1. 逐题表（19 题全列）

| 题号 | 判定 | 答案字数 | 引证数 | `answer_source` | 缺失的 `must_contain` 原话 | 原话在语料里？ |
|---|---|---|---|---|---|---|
| `metric-01` | ✅ 对 | 311 | 3 | `eval_transport_ask_v2:transport` | — | — |
| `metric-02` | ✅ 对 | 757 | 0 | `eval_transport_ask_v2:transport` | — | — |
| `metric-03` | ✅ 对 | 371 | 3 | `eval_transport_ask_v2:transport` | — | — |
| `metric-04` | 🔴 错 | 410 | 0 | `eval_transport_ask_v2:transport` | `活跃客户按成交客户数` | ✅ 在 |
| `metric-05` | 🔴 错 | 749 | 3 | `eval_transport_ask_v2:transport` | `活跃客户按登录活跃客户数` | ✅ 在 |
| `metric-06` | ✅ 对 | 441 | 6 | `eval_transport_ask_v2:transport` | — | — |
| `metric-07` | 🔴 错 | 473 | 0 | `eval_transport_ask_v2:transport` | `销售额含增值税` | ✅ 在 |
| `metric-08` | 🔴 错 | 450 | 6 | `eval_transport_ask_v2:transport` | `退款不冲减销售额` | ✅ 在 |
| `metric-09` | ✅ 对 | 462 | 4 | `eval_transport_ask_v2:transport` | — | — |
| `metric-10` | 🔴 错 | 962 | 4 | `eval_transport_ask_v2:transport` | `费用以入账月归属` | ✅ 在 |
| `metric-11` | 🔴 错 | 162 | 0 | `eval_transport_ask_v2:transport` | `费用以发生月归属` | ✅ 在 |
| `metric-12` | 🔴 错 | 1010 | 0 | `eval_transport_ask_v2:transport` | `人均产值分母为在册人数` | ✅ 在 |
| `metric-13` | 🔴 错 | 531 | 0 | `eval_transport_ask_v2:transport` | `人均产值分母为发薪人数` | ✅ 在 |
| `metric-14` | 🔴 错 | 606 | 0 | `eval_transport_ask_v2:transport` | `库存周转按出库成本计算` | ✅ 在 |
| `metric-15` | 🔴 错 | 695 | 0 | `eval_transport_ask_v2:transport` | `库存周转按结转营业成本计算` | ✅ 在 |
| `metric-16` | 🔴 错 | 434 | 3 | `eval_transport_ask_v2:transport` | `回款以银行到账确认` | ✅ 在 |
| `metric-17` | 🔴 错 | 200 | 0 | `eval_transport_ask_v2:transport` | `回款以验收单确认` | ✅ 在 |
| `metric-18` | 🔴 错 | 314 | 5 | `eval_transport_ask_v2:transport` | `里程碑以提交验收视为完成` | ✅ 在 |
| `metric-19` | ✅ 对 | 337 | 6 | `eval_transport_ask_v2:transport` | — | — |

## 2. 配对结构（这一族为什么天生容易踩字面）

本族每题问的都是「同一个词有两套冲突口径，哪套算数」，所以题号成对、缺的原话也成对：

- **人均产值分…**：`metric-12`←`人均产值分母为在册人数`　`metric-13`←`人均产值分母为发薪人数`
- **库存周转按…**：`metric-14`←`库存周转按出库成本计算`　`metric-15`←`库存周转按结转营业成本计算`
- **活跃客户按…**：`metric-04`←`活跃客户按成交客户数`　`metric-05`←`活跃客户按登录活跃客户数`

## 3. 这张表推出什么、不推出什么

- **推出**：修法是让**答案必须携带被引证的那句口径原文**（装箱 / `synthesize` 腿），不是去放宽 `must_contain`——放宽词条＝改评测集，那是业主单独批的动作，本班不动。
- **不推出「run6 比 run5 到底翻了哪两题」**：**run5 的逐题答案没有留档**（`docs/testing/` 只剩 `evaluation-report-run5.json` 那份聚合件，`%TEMP%` 里 run5 的现场早被覆盖），所以本文只能定到机制、定不到具体两题。⇒ **记一笔欠账**：以后每扇窗的 `answers-runN.jsonl` 必须留档进 `docs/testing/`，否则逐类退化永远只能判红、不能判因。
- **待办**：立案 **R206**（口径原话必须进正文）。它要动 `app/agents/nodes.py` 的 `synthesize` 腿 ⇒ 与在途 R203 撞同一文件，**排 R203 之后**，不许并行。
