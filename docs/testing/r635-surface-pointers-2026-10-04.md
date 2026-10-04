# R635 · 观测面那族手抄坐标全部改指真锚点，尺子铺到整本盘面（2026-10-04）

本格只收账面与实际不一致，不改任何产品行为。

- 执行层：Huygens／单号 R635／树 `C:\Users\fengx\PycharmProjects\be-r635`（分支 `codex/be-r635`）
- 基点：`497ac38`（R630 并树那一笔）。开工 `git status --porcelain` 为空，交回时只含本单写域。
- 写域：`app/api/v1/observability.py`（只动文案与注释里的坐标）、`tests/test_r635_*.py`（新两枚）、
  本纸、`tests/test_r630_first_token_pointer_is_derived.py`（**纯追加**：新增函数，零行删除）。
- 零行为：路由、返回结构、状态码、字段名一枚未动；未 commit；未跑全量门；不起容器、不连库、不打模型。

## 0. 判据① —— 手抄坐标：替换前后枚数与逐枚去向

现取读数（`rg -o -n` 口径，同一枚文件）：

| 尺 | 替换前（基点 497ac38 现取） | 替换后 |
|---|---|---|
| 派工词点名那枚 `[A-Za-z_/]+\.py:[0-9]+` | 11 | **0** |
| 更宽一枚 `[A-Za-z0-9_./-]+\.py:[0-9]+`（文件名带数字／短横也算） | 11 | **0** |

🔴 **与派工词的枚数差**：派工词写「本文件里仍有 14 枚」。基点现取是 11 枚——差的那 3 枚正是 R630
并树那一笔删掉的（现取凭据：`git show 497ac38 -- app/api/v1/observability.py`，删除行里带坐标形状
3 枚、新增行里 0 枚）。本单不拿 14 当尺，按 11 逐枚点名。

逐枚去向（「纸面主张」一栏是基点那一行原文；「那一行现读是什么」与「真位」都由 AST／文本现取）：

| 基点行 | 纸面主张 | 那一行／那一段现读是什么 | 真位（现取） | 换成了 |
|---|---|---|---|---|
| 383 | `observability.py:333` 的「无条件追加」 | 基点 333 落在 `_module_available`（328-332）身后，是空行 | `_evaluation_report_candidates` = 362-376，追加语句在 372-375 | `app/api/v1/observability.py::_evaluation_report_candidates` |
| 751 | `app/common/performance.py:27-28`「答 0」 | 27-28 正是 `if not sorted_durations: return 0`（今天**没漂**，但仍是手抄） | `PerformanceStats._rank` = 26-30；`report` = 38-51 | `…::PerformanceStats._rank` ＋ `…::PerformanceStats.report`（谁答 0、谁把 0 发出去，分开点名） |
| 779 | `app/trace/spans.py:201-215` 交给账本 stage/tool/tier/worker | 201-215 是 `record_stage_sample(...)` 调用段，落在 `_observe_stage`（184-217）体内（今天没漂） | `ExecutionSpan._observe_stage` = 184-217 | `app/trace/spans.py::ExecutionSpan._observe_stage` |
| 796 | `chat.py:218-243` 盖 canonical SSE 信封 | 218 起是 `_reap_agent_worker` 里的 `_done` 回调，与 SSE 无关；**漂** | `canonical_sse_event` = 238-259 | `app/api/v1/chat.py::canonical_sse_event` |
| 800 | `app/api/v1/chat.py:1191-1215` 缓存命中直接回 StreamingResponse | 1191 起是 `_starts_with_deictic`／追问标记，**完全错位** | 缓存命中的 return 在 2666，宿主是 `ask`（2484-3208） | `app/api/v1/chat.py::ask` |
| 805 | `app/agents/orchestrator.py:1173-1185` 逐 superstep 落 `step.progress` | 1173 起是 `run_orchestrator_queue` 的 configurable 字典，**完全错位** | `step.progress` 记录点在 1450，宿主 `run_with_stream`（1337-1543）；发出走 `_record_trace`（1304-1328） | `…orchestrator.py::run_with_stream` ＋ `…orchestrator.py::_record_trace` |
| 810 | `app/common/stage_timing.py:71` 把 `export_report` 映射为空段 | 71 是 `"query_data": "generate"`，`export_report` 那行在 73；**漂两行** | `TOOL_TO_STAGE` = 68-74 | `app/common/stage_timing.py::TOOL_TO_STAGE` |
| 911 | `app/agents/contracts.py:69 ModelTier`（文档串） | 69 是空行，`class ModelTier` 在 70；**漂一行**（与派工词一致） | `ModelTier` = 70-91 | `app/agents/contracts.py::ModelTier` |
| 912 | `app/common/stage_timing.py:48 CANONICAL_STAGES`（文档串） | 48 正是那行定义（今天没漂） | `CANONICAL_STAGES` = 48 | `app/common/stage_timing.py::CANONICAL_STAGES` |
| 936 | `"owns_the_name": "app/agents/contracts.py:69 ModelTier"`（**对外回执那一格**） | 同 911，69 空行／70 才是 `class ModelTier` | 同上 | `"app/agents/contracts.py::ModelTier"` |
| 1729 | `model_budget.py:769` 里 `origin = "env"` | 769 是一段评测注记的中间行，`origin = "env"` 在 1300；**完全错位** | `clamp_basis` = 1292-1312（出处判定走 `_env_set` = 414-416） | `app/common/model_budget.py::clamp_basis` ＋ 同一句里把裸写的 `model_budget._env_set` 一并写成 `app/common/model_budget.py::_env_set` |

顺带把三处**没有行号但同样解析不到**的名字也改成了锚点（同一族的病，只是形状差一枚冒号）：
`owns_the_name` 里的 `app/agents/nodes.py (LANE_QA / LANE_ANALYSIS / LANE_REPORT)` → 三枚
`app/agents/nodes.py::LANE_QA` 等；`app/common/stage_timing.py CANONICAL_STAGES` →
`…::CANONICAL_STAGES`。字段名与结构一字未动，`frontend/src/lib/slo.js` 只是把这格当文本渲染。

## 1. 判据② —— 每一枚锚点都真解析得到

- 锚点数（`WIDE_ANCHOR` 现取自源文）：基点 **10** 枚 → 现在 **26** 枚，本单新下 16 枚，26/26 解析通过。
- 解析口径：**符号必须真在那枚文件的源码里定义**，点号链逐层下钻（类里的方法也算）。不是「文本里
  出现就算数」——正控见 `test_a_fabricated_symbol_dies_on_both_legs_of_the_ruler`：把一枚在册锚点的
  符号名换成 `…_ghost_symbol`，AST 腿与 R630 的运行时腿（`resolve_symbol`）同判红。
- 为什么走 AST 而不 import：`app/api/v1/chat.py` 在模块级就构造 `DocumentRetriever()`。本单实测
  在 pytest 之外 import 它：耗时以秒计、朝 Postgres 探针发连接（`fe_sendauth: no password supplied`）、
  并且把被 git 跟踪的 `chroma_db/chroma.sqlite3` 写脏（开工时踩过一次，已 `git checkout --` 复原；
  仓库根 `conftest.py` 记的正是这一笔）。派工禁连库、禁动盘面，所以锚点腿读源码。
- 两枚腿不许分叉：`test_the_ast_leg_and_the_runtime_leg_agree_on_every_module_in_memory` 对每一枚
  「模块已在内存里」的锚点逐枚核 `anchor_resolves(...) == resolve_symbol(...)`，并硬要求这一枚用例
  真核到过东西（`assert checked`），防止它空转。

## 2. 判据③ —— R630 那把尺扩覆盖（在册件纯追加）

`tests/test_r630_first_token_pointer_is_derived.py` 追加（`git diff --numstat` = 118 增 / **0 删**，
`git diff` 里以 `-` 开头的行只有 `--- a/…` 那一枚表头）：

- `module_source` / `_defined_names` / `_children` / `_descends` / `anchor_resolves` —— AST 解析腿；
  `overrides` 参数是反证刀的口：刀改的是内存影子，盘上不动。
- `WIDE_ANCHOR` + `shape_violations` —— 通用形状尺（零字段专属判断）：一枚 `.py:数字` 都不许有，
  每一枚 `::` 锚点都要解析得到。R630 原来那枚 `prose_shape_violations` 带着 `first_token_at` 的
  「经手／不经手」语义，只能量那一格；这一枚才能铺满整本。
- `surface_texts` —— 落点清单：整本 `SLO_BLOCKERS`（6 格，含没随回执对外的那几格）＋
  `slo_readout()` 的全部字符串叶子（现取 **195** 枚）。两路合起来 **201** 枚，逐枚点名，不靠注释吹。
- `surface_shape_violations` —— 一把抓：源文整本 ∪ 名册每一格 ∪ 回执每一枚叶子。
- `surface_roster_offenders` —— 复用在册 `roster_count_offenders`，只是喂进去的东西从「对外回执」
  扩成「回执 ＋ 整本名册」，再加下面这一条新腿。
- `derived_reading_offenders` —— **本单实测补出来的新腿**：派生读数 published 出来那一格，必须等于
  拿现取名册（`r533.budget_roster()` / `r533.lane_bridge()`）重建的那一句。补它的凭据不是想象：
  K9 那一刀（把桥话冻成「今天恰好抄对」的常量，再往名册注一档）在**在册旧尺上全绿**——旧尺只判
  「数字撞不撞得进派生读数集合」，桥话里抄来的 `5` 撞上了 stage 名册的 `5`。K9 现在硬断言
  「红必须来自新腿、旧腿此时必须空」，两头都钉死。
- 装配把手 `BRIDGE_NOTE_ASSEMBLY_AT_IMPORT` 在 import 那一刻抄下来：否则刀把模块属性换成常量时，
  重建腿与读数一起被糊。
- 与 R533 的关系：R533 已有「句子随名册变」那一格与源文调用点那枚钉（`_slo_bridge_note(...)` 必须
  是调用不是字面），本单不抄它，只把**回执叶子级**的重建对做成常驻的一腿。残余盲区写清：
  ① 名册没动时，同值抄本仍然看不见（R533 K1b 早已点名同一格）；② 谁把装配函数本体改成常量，
  这一腿也看不见，归 R533 的纯函数面那枚钉。

## 3. 判据④ —— 反证刀（`tests/test_r635_counter_evidence_teeth.py`，全程内存）

| 刀 | 摘掉的那一格 | 红来自哪一支 | 正控 |
|---|---|---|---|
| K1 | 一枚锚点退回行号坐标、**改漂一行**（行号由 AST 现取＋1） | 「抄了行号坐标」（源文整本＋名册那一格同红） | 不摘刀：`surface_shape_violations() == []` |
| K2 | 一枚锚点退回行号坐标、**行号抄对了** | 同一支——按形状失败，不按准确性失败（并硬断言这枚红不来自「解析不到」） | 同上 |
| K3 | 锚点的目标符号从它自己的文件里**被删走** | 「锚点 …::… 现读解析不到」 | 同上；并核目标文件 sha256 未变 |
| K4 | 同一枚符号被**改名** | 同一支（牙认的是符号名） | 同上 |
| K5 | 锚点把文件换成另一枚真文件（`spans.py::TOOL_TO_STAGE`） | 同一支，且点名的是 `spans.py` | 同上 |
| K6 | **派生读数改成手写常量**（桥话装配被替成常量句） | 整本名册那把枚数尺：错数字与英文词两种伪装都红 | 改回后 `surface_roster_offenders() == []`；observability sha256 未变 |
| K7 | 手写枚数躲进**不随回执对外**的名册格子 | 名册整本那一支；并硬断言「只喂回执」那半把尺在这一刀下**必须仍为空**（这就是被补上的盲区） | 同左那条空表 |
| K8 | 一枚坐标**只出现在注释里**（每一格散文都干净） | 源文整本那一支；并硬断言违规行全部以 `source ` 开头（证明散文腿没帮忙） | 同上 |
| K9 | 派生读数冻成「今天抄对了」的常量，再让名册长一档 | 新增的重建腿；并硬断言旧尺此时必须空 | 名册未动时重建腿必须先绿 |

- 总清点：`test_every_knife_ran_and_bit_and_nothing_on_disk_moved` 要求 9 枚刀**全部真跑过且全部真咬红**，
  少一枚当场拒；并对 17 枚被跟踪文件逐枚核 sha256 与 import 时刻同判（含 `docs/api/contract-v1.md`、
  `app/api/v1/chat.py`、`app/agents/orchestrator.py` 这些禁区原件）。
- 本件自扫：`test_this_file_itself_copies_no_coordinate` 一枚坐标形状都没有（伪造坐标全部运行时拼），
  量级尺（R526）零命中，件内自己写的锚点也枚枚解析得到。
- 越域证明见 §6。

## 4. 判据⑤ —— 两态亲跑（同名件逐枚点名）

同名件清单（两态逐枚一致，共 13 枚文件）：
`tests/test_r635_surface_pointers_are_derived.py`、`tests/test_r635_counter_evidence_teeth.py`、
`tests/test_r630_first_token_pointer_is_derived.py`、`tests/test_r630_counter_evidence_teeth.py`、
`tests/test_r533_bridge_note_is_derived.py`、`tests/test_r533_counter_evidence_teeth.py`、
`tests/test_r526_slot_caliber_closure.py`、`tests/test_r520_counter_evidence_teeth.py`、
`tests/test_r105_slo_contract.py`、`tests/test_r523_cached_count_lands.py`、
`tests/test_observability_routes.py`、`tests/test_error_code_vocabulary.py`、
`tests/test_r597_verdict_vocabulary_has_one_source.py`。

| 态 | 盘面 | 读数 |
|---|---|---|
| ① apply 未 commit | 本树工作区（`M` 两枚 ＋ `??` 三枚：两枚新件＋本纸） | **199 passed**, 60 warnings, **25.79 s** |
| ② 干净树 ＋ 只投本单货 | `497ac38` 完整检出（导出时 `status --porcelain` 为空）＋ 本单 5 枚货 | **199 passed**, 60 warnings, **26.03 s** |

同名件前后共跑过四轮（state① 25.91 / 27.85 / 25.79 s，state② 27.56 / 27.65 / 26.03 s）：
**每一轮都是 199 passed、0 failed**，只有秒数随机器抖动 ⇒ 牙不把「此刻盘面脏不脏」当判据。

两态枚数逐枚相同 ⇒ 牙没有把「此刻盘面脏不脏」当判据。
🔴 state② 的取法订正：`git archive 497ac38 | tar -x` 在本机取不出**中文名的数据文件**
（`documents/…`、`data/…` 报 `Invalid empty pathname`），且那棵树没有 `.git`，
`test_r523_cached_count_lands.py::contract_is_pure_append` 会因为 `git show HEAD:` 直接假红
（两枚 failed，与本单无关）。故 state② 改用 `git clone -s` ＋ `checkout --detach 497ac38` 的完整树，
再投货——这才是「干净树 ＋ 只投我的货」。

## 5. 交总控落地：契约文（禁区，本单未动一字节）

`docs/api/contract-v1.md` 的 SLO blockers 表与名册表里那六行，今天仍是**已经漂了的旧坐标**。
若判到必须同文，请由总控原样替换（本单已把这些句子逐字核对过真源）：

- L1568 预算档那一格：`| \`app/agents/contracts.py:69\` \`ModelTier\`; chosen by the call site that asks for a budget |`
  → `| \`app/agents/contracts.py::ModelTier\`; chosen by the call site that asks for a budget |`
- L1722：`\`app/trace/spans.py:201-215\` hands the ledger stage` → `\`app/trace/spans.py::ExecutionSpan._observe_stage\` hands the ledger stage`
- L1724：`canonical envelopes are stamped (\`chat.py:222-243\`) but not persisted`
  → `canonical envelopes are stamped (\`app/api/v1/chat.py::canonical_sse_event\`) but not persisted`
- L1725：`a cache hit returns before any \`request.started\` (\`chat.py:1191-1215\`)`
  → `a cache hit returns before any \`request.started\` (\`app/api/v1/chat.py::ask\`)`
- L1726：`\`step.progress\` is persisted per graph superstep (\`orchestrator.py:1173-1185\`)`
  → `\`step.progress\` is persisted per graph superstep by \`app/agents/orchestrator.py::run_with_stream\` through \`app/agents/orchestrator.py::_record_trace\``
- L1727：`\`TOOL_TO_STAGE["export_report"]\` is empty (\`stage_timing.py:71\`)`
  → `\`app/common/stage_timing.py::TOOL_TO_STAGE\` maps \`export_report\` to the empty segment`

🔴 上面这六行**必须同文**的理由：观测面那本名册今天就是这六行的真源，纸不改口就会与
`slo_readout()` 逐字对不上；而 `test_r523_cached_count_lands.py` 那两枚钉要求契约「只许文末追加」，
所以这不是本单能顺手做的事，只能交总控落。

## 6. 写域与越域核对（sha256 现取）

交回时 `git status --porcelain` 只有写域内那四枚（读数见 §8），四类写域之外的文件一字节未动。
R635 的刀另有一份 17 枚被跟踪文件的 import／末了双核对
（`test_every_knife_ran_and_bit_and_nothing_on_disk_moved`），禁区原件（`chat.py`／`orchestrator.py`／
`contract-v1.md` 等）逐枚同判，摘刀没落到盘上。

## 7. 现取到但本单没办（交总控定夺）

1. `slo_units()` 的文档串里还躺着**两枚手抄的名册成员枚举**（`chat/plan/compress/rewrite/code/alert/analysis`
   与 `classify/rewrite/retrieve/generate/reflect`）。今天逐枚与真源核过**都是对的**（`ModelTier`
   现取 = chat/plan/compress/rewrite/code/alert/analysis；`CANONICAL_STAGES` 现取 =
   classify/rewrite/retrieve/generate/reflect），但它们是「名册一改就成假话」的同一族。它不是坐标、
   也不在对外散文里，超出本单判据① 的形状，故未动——建议另开一枚「回执与文档串里的名册枚举改派生」的单。
2. 契约文除 §5 那六行之外另有 9 处 `chat.py:`／`orchestrator.py:` 旧坐标（L368／395／398／401／414／426
   ／1265／1474／1542），不在本单射程（禁区 ＋ 不是观测面的真源），只点名不办。
3. 全量门未跑（派工禁），两态数字只覆盖 §4 那 13 枚同名件；`scripts/run_gate.py` 一字节未动。

## 8. 读数块（交回那一刻现取）

```
coord_narrow_before=11  coord_narrow_after=0   coord_broad_before=11  coord_broad_after=0
anchors_base=10  anchors_now=26  anchors_unresolvable=0
ruler_inputs: book_cells=6  readout_leaves=195  total=201
git_status_after_delivery= M observability / M test_r630_pointer / ?? 两枚 r635 件 / ?? 本纸
surface_shape_violations=[]   surface_roster_offenders=[]
state1=199 passed / 25.79s    state2=199 passed / 26.03s（两态枚数同）
```

写域四枚的 sha256（交回那一刻现取；本纸自己的那一枚不列，列了就自指）：

```
app/api/v1/observability.py.............................. dfd2f094d290f97ccb367a70abbe79a1c136f577fda16db516ffeacd866ecb72
tests/test_r630_first_token_pointer_is_derived.py........ 9a2809faba65eee909eae1a9766ac73f2addf2b7357d5eb3348ebb63b1f3752e
tests/test_r635_surface_pointers_are_derived.py.......... 0116611f75b9a8ff092203b8cd8ed13d6c7e892a5154fdc3f57f60e51e821d06
tests/test_r635_counter_evidence_teeth.py................ 3ed72c0e99c0fe860f466a33f7af39d6ae5b3517b467b3281f79fbe06a860a0f
```

🔴 这四枚哈希在最后一轮改动（K9 加分支断言 ＋ 去掉两枚未用形参与件内 import）之后现取，本纸
落定即冻结代码；总控并树前若要以盘面为准，`Get-FileHash -Algorithm SHA256 <文件>` 现取逐枚对
一次即可（哈希与本纸正文互相除外，免得自指）。
