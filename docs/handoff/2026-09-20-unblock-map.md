# 未开工单解锁图（2026-09-20）

> 🔴 **行号口径声明（全文统一）**：本文所有 `file:line` 一律按 **`git grep -n` 口径 = 只按 LF 断行**计数。
> 依据：跟进单里有 **1364 处 `\r\r\n`**，PowerShell `Select-String` / 部分编辑器会把孤立 CR 也当换行，
> 同一枚 §21 标题在两种口径下分别是 **L487（git grep）** 与 **L973（Select-String）**，全文行数分别是 **1859** 与 **3223**。
> 复核请一律用 `git grep -n <模式> -- <文件>` 或 `python -c`（rb 读入后 `replace(b"\r\n",b"\n")` 再 split），不要拿 IDE 的行号对账。
>
> 判据来源（唯一）：`AGENTS.md`、`docs/handoff/2026-09-15-orchestration-board.md`（§0 名册 L1184-1312、§4AQ.9 L2235-2244、§4BD L2708-2731、§4BH.8-11 L2995-3076）、`docs/handoff/2026-09-17-perf-architecture-plan.md`（§5.1/§5.2 L162-321、§6 L324-349、§7 L353-364、§8 L366-382）、`docs/handoff/2026-09-17-human-gates.md`（H1-H19、D1-D14 L307-355）、`docs/handoff/2026-09-15-backend-followup-requests.md`（§21 L487-534、§49/§51/§52/§55/§55A/§57/§58/§61）。
> **未采信**：`task_plan.md`、`progress.md`、`findings.md`（计划书 §10 L405 明令已过期）。
> 工作树：`codex/data-file-catalog` @ `2f965c1`。全部源码结论由 `git grep` / `git show` / `git diff --name-only` 与实读得出，**未照抄计划书正文的落点描述**。

## 0. 一句话结论（先给总控看这条）

总控派工单里「20 枚零提交」这个前提**不成立**：其中 **12 枚（R30 R34 R35 R37 R40 R42 R44 R47 R49 R50 R51 R52）在 09-18～09-19 就已并树**，28 枚候选哈希逐枚 `git merge-base --is-ancestor <c> HEAD` 全部通过。
真正零提交的是 **8 枚**：**R29 R31 R32 R33 R38 R43 R46 R48**（R31/R32/R38/R48 在 `git log --all` 的 subject+body 全文里命中 **0 次**；R33/R43/R46 各命中 1 次且全在文档提交正文；R29 命中 13 次但全是决策文本，无一枚实现提交）。
新单里 **R110（`9b4154d`）与 R113（`9de5e89`）也已落地**，未开工的是 **R105 乙半、R118、R119、R123**。
⇒ 待派集合从"26 枚"缩到 **8 枚老单 + 4 枚新单**，其中**只有 4 枚今天可派且不卡业主**（见 §D）。

---

## A. 逐单表

### A-1 未开工的 8 枚老单（真正需要解锁的）

| 单号 | 一句话目标 | 判据出处 | 它会改的确切文件（全部由源码实查，非抄计划书） | 与其它单的文件交集 | 前置单 | 业主闸门 | 现在能不能派 |
|---|---|---|---|---|---|---|---|
| **R29** | 消灭思考税：答案腿走原生 `/api/chat` 或 `think:false` 派生模型 | 跟进单 §21 表 L501；计划书 L179；边界条款 跟进单 L1298/L1300 | `app/common/model_handler.py:414 chat()`（`:435 if not stream:` ⇒ 原生腿只服务非流式）、`:311/:327 _native_chat` 写死 `"stream": False`、`app/agents/nodes.py:606 _make_model`（答案腿建的是 `ChatOpenAI`）、`app/common/model_budget.py:413 resolve_model_thinking`、`:460 thinking_extra_body`、`app/agents/nodes.py:204 _with_thinking_field`、`.env.example` + `deploy/.env.server.example` | 与 R31/R33/R43/R118 共占 `nodes.py`+`orchestrator.py`；与 R38 共占 `model_handler.py` | R36（判据③ 真机基线，run3/run4 已出分）、R92（`ebfb1c9` 已并树，L1300 明写"R92 之后才允许派 R29"）、R34 未覆盖的那半（§44.4 L1519 退回本单） | 🔴 卡裁定：09-20 文档提交正文有「本窗口留 compat；B=复活 R29 且前置倒置，不做」；判据②④ 需真机（H12 形态已改由总控重建，见 H12 结案 L327-336） | **等业主/等裁定**（先撤"不做"这句才谈得上派） |
| **R31** | 生成轮流式透传 + 片段边界规则（每片 ≥20 字或 100 ms 合并，禁单字碎片），前端零改动 | 跟进单 §21 表 L503；计划书 L181；§8 风险条款 4 L379 | `app/api/v1/chat.py:1399`（当前**整段一次**发单枚 `text`）、`:1230-1238`（`run_with_stream` 消费点）、`:1204-1209`（缓存命中路径同表单枚）、`app/agents/orchestrator.py:699 stream_mode="values"`、`:1095 run_with_stream`、`:1163/:1312/:1340` 三处 `_cancellable_stream`、`app/agents/nodes.py:483 _ResilientModel.stream`（生成器已存在但生产答题腿未被消费） | `nodes.py`（R29/R33/R38/R43/R118）、`orchestrator.py`（R33/R43/R118）、`chat.py`（R32/R48/R35/R37/R49 已并） | R27（`6a4f02b`）、R30（`50aff1a`）已并；R29 未结 ⇒ §8 L372 链条上 R31 仍被压 | 判据②④ 需真机端到端计时（窗口内禁改码、禁 `up/down`，§21 L493） | **等前置**（R29 先定端点形状；验收等窗口） |
| **R32** | 问答/分析/报告三档进契约 + 前端选择器，默认问答档 | 跟进单 §21 表 L504；计划书 L182；§6.1 L345 | `app/api/v1/chat.py:754 AskRequest`、`:759 lane: str = ""`、`:765 LANE_REPORT`、`:776-786 _queue_lane`（**只认 report，非法档不拒 400**）、`app/agents/nodes.py:696-700 LANE_QA/ANALYSIS/REPORT`、`:782 classify_route`、`docs/api/contract-v1.md:752-757`（三行 `gated: needs lane labels`）、`frontend/**`（选择器，禁改） | `chat.py`（R31/R48/R35/R37/R49）、`contract-v1.md`（R105乙/R48/R111 已并）、`frontend/**`（前端线独占） | R42（`89965d5` 已并，判别器已在 `nodes.py`）；R37（`0c08209` 已把 `lane` 字段占掉） | D13=甲（业主 09-19 22:5x 已授权动 `frontend/**`，human-gates L354），但 AGENTS.md 与本单铁规把前端划给其他 Agent | **判据已失效·需改写后派**（见 G-3；不改写就是让下一班重复发明 `lane`） |
| **R33** | 输入瘦身：每发 prompt token 硬上限 + **零模型**裁剪 | 跟进单 §21 表 L505；计划书 §8 风险条款 1 L375 | `app/agents/orchestrator.py:50`（`from app.memory import compress_messages`）、`:342 all_msgs = compress_messages(all_msgs, _make_model(ModelTier.COMPRESS))` ⇒ 裁剪本身仍**多发一发模型**、`app/memory/summarizer.py:37`、`:49`、`app/agents/contracts.py:81-82 ModelTier.COMPRESS` | `orchestrator.py`（R31/R43/R118）、`nodes.py`（`_make_model` 调用面） | R36（同批改同批验，§8 L375-376） | 密级/H13 无关；需真机验收"改答案内容不退化" | **判据大半已失效**（上限由 R30、零模型装箱由 R112/R117/R122 落了；见 G-4 改写草案）⇒ 改写后可派 |
| **R38** | 核实 `usage` 真值，计量列不再写零 | 跟进单 §21 表 L510；计划书 L188、§2.5 L63 | `app/agents/nodes.py:300-302`、`:435-437 model_token_counts(response)`、`app/trace/spans.py:269-278`、`:77/:85-86/:174 first_token_at`、`app/trace/store.py:259/:270-271`、`migrations/0002_execution_data_lineage.sql:147-165 model_calls`、缺口在 `app/common/model_handler.py:360 output_tokens=eval_count`（**不读 `prompt_eval_count`**） | `spans.py`（R51 已并 `cef08bf`、R105乙 读侧）、`model_handler.py`（R29/R34 已并） | R51（`cef08bf` 已并，账本形状已定） | 判据「抽查一问」需真机读数 ⇒ 窗口内禁 docker/HTTP | **等窗口**（代码半可即刻派，读数半等收窗） |
| **R43** | system prompt 前缀复用、可变内容后置（配前缀缓存） | 跟进单 §21 表 L514；计划书 L193 | `app/agents/orchestrator.py:203-207`（`DOC_PROMPT/DATA_PROMPT/CHART_PROMPT/EXPORT_PROMPT` 四枚字面量）、`app/memory/summarizer.py:49`（把【历史摘要】塞进 **SystemMessage 首位** ⇒ 前缀天然不稳定）、`app/api/v1/chat.py:899-909`（参考文档拼在指令之前）、`app/rag/retrieval_pipeline.py:203 rewrite()` 提示、`app/agents/nodes.py:991 synthesize` | `orchestrator.py`（R31/R33/R118）、`chat.py`（R31/R32/R48）、`retrieval_pipeline.py`（R46/R119） | R30（已并）、R33（前缀里是否还有摘要由它定） | 🔴 判据②「E3 档实测 `cached_tokens > 0`」属 **H1**（E2/E3 定档实测，仅业主；H1 L15 附「H11 探针通过则本条暂缓」，H11 已 🟢 结案 L300） | **等业主**（H1 未做则判据② 永远不可验） |
| **R46** | 活动信号回填排序（采纳/驳回 → 相关度先验） | 跟进单 §21 表 L517；计划书 L196 | `app/rag/retrieval_pipeline.py:466 rrf_fusion`（融合即排序点，`:478 1/(k+rank)`）、`app/agents/contracts.py:314 score_type`（`Literal[...] "rerank"` 枚举已备）、`app/agents/evidence.py:82/:192`、`app/api/v1/chat.py:267`、信号源候选 `migrations/0008_pending_approvals.sql:33`、`app/semantics/registry.py:61`（rejected 态）、新表 ⇒ `migrations/0011_*.sql` + `migrations/manifest.json` + `app/db/migrations.py` | `retrieval_pipeline.py`（R119 改 `:591/:616`；R47 已并 `006c613`）、`migrations/**`（R88 卡 D8、R90b→R120 已并） | R45（`0276f78` 已并，pre-filter 必须先于排序）、R44/R79（热集读源已并） | 若需新表 ⇒ **业主侧执行迁移**（R88/R90 同口径，human-gates L349-350 D8 按住）；可复用 `query_hash`（`migrations/0002:176`）免存原文 ⇒ 那半不必 migration | **等前置+等业主**（除非判据改写成"只挂 JSONB 计数、不建表"） |
| **R48** | 首屏结论卡片 + 来源，正文后台补 | 跟进单 §21 表 L519；计划书 L198 | `app/api/v1/chat.py:1399`（今天首屏＝最后一个 `text`，无早期结论可插）、`:1204-1209`（缓存命中的单枚 `text`）、`app/trace/spans.py:77/:85-86`（`first_token_at` 已有，但 `contract-v1.md:787` 自陈它不是 stage 样本）、`app/api/v1/observability.py:732-744/:868`（R105甲 已把"首屏=流上第一个 text 事件"钉成口径）、`docs/api/contract-v1.md:753/:787-788`、`app/tools/export.py` + `app/api/v1/artifacts.py`（正文后台补齐的产物面）、`frontend/**`（卡片渲染，禁改） | `chat.py`（R31/R32）、`contract-v1.md`（R32/R105乙）、`frontend/**`（前端线） | R105甲（`3a67367` 已并，口径已定）、R31（没有分片就没有"首屏 vs 正文"之分）、R37（report 档队列化已并） | D13=甲已授权前端，但前端写域归其他 Agent | **等前置**（R31 未落地 ⇒ 判据① 无法验）；前端半张单转前端线 |

### A-2 新单里的 4 枚（R105 乙半、R118、R119、R123）

| 单号 | 一句话目标 | 判据出处 | 它会改的确切文件（源码实查） | 交集 | 前置单 | 业主闸门 | 能不能派 |
|---|---|---|---|---|---|---|---|
| **R105 乙半** | 把真实分布填进甲半留下的空位，并落一份基线分数供 R29/R33/R35 对比（R36 判据③） | 跟进单 §51 L1641；计划书 §5.2 L250、§6.1 L345 | `docs/api/contract-v1.md:744-757`（**九枚空位全写「待真机样本」，其中 3 枚标 `gated: needs lane labels`**）、`tests/test_r105_slo_contract.py`（22 枚钉，甲半落的口径不许改）、`app/api/v1/observability.py:778-868`（行构造器与 `lane_attribution_absent` 段）、`app/common/performance.py:12/:47` | `contract-v1.md`（R32/R48）、`observability.py`（R51 已并） | R104（`caa4cd1`）、R105甲（`3a67367`）、R110（`9b4154d`）**三条前置今日全部成立**（run3/run4 各 105 样本 + R110 已并树 ⇒ 缺尾偏差已消） | 无新闸门；但 3 枚 gated 槽位要 lane 落盘，`git grep -n lane -- app/trace/` **0 命中** ⇒ 需另立单（跟进单 §28.5 原文：要落 lane 须改 `app/trace/records.py`，另立单不夹带） | **可派（半）**：6 枚非 gated 槽位现在就能填；3 枚 gated 槽位**等 lane 落盘单** |
| **R118** | doc 腿每轮冷启动 ⇒ 跨轮失忆：改装配形状让子图真 resume，或承认失忆并把注释与文档改对 | 跟进单 §55 L1729-1731；计划书 §5.2 L312 | `app/agents/orchestrator.py:201`（注释仍写「带 checkpointer，可持久化」——与 §55② 实测矛盾）、`:212-215` 四张 worker 子图 `checkpointer=_checkpointer`、`:198 _make_checkpointer()`、真装配 `:607`（§55 探针所指） | `orchestrator.py`（R31/R33/R43） | R117（`f29a020` 已并树 ⇒ 计划书 L312「可定策」的前置成立） | 无（产品级取舍，属总控/业主可选两案，不属 H/D 在册闸门） | **可派**（只读定策单；`%TEMP%\r114_probe\` 那份 12680 B patch + 11 枚用例若选"让子图 resume"可直接续用） |
| **R119** | `CONTEXT_HISTORY_RESERVE_TOKENS=322` 只够 0.75 轮真问答，按实测校准 | 跟进单 §55 L1733-1735；计划书 §5.2 L313 | `app/rag/retrieval_pipeline.py:591`（常数本体）、`:616`（`context_pack_capacity - SHELL - HISTORY`）、`app/agents/tools.py:658/:694`（消费点）、`tests/test_r112_prompt_packing.py:260-268`（`test_history_reserve_covers_the_pinned_number_of_turns` 会跟着咬）、`:271-275`（"整十整百即拍脑袋"反证钉） | 🔴 与 **R116** 共占 `tests/test_r112_prompt_packing.py`（R116 要把 46 枚参数化钉桩升级成实测复算）⇒ 同批只能一派 | R117（`f29a020`）、R112（`6a70f73`）均已并树 | 无 | **可派**（数须来自实测：run4 `[ModelBudget]` 604 枚日志已在盘，§4BH.11 L3045） |
| **R123** | 评测里 `kind=hitl` 的题没答完却仍占 `correctness` 分母（18/105=17%） | 跟进单 §57 L1788-1793；计划书 §5.2 L317 | `scripts/eval_transport_ask_v2.py:109/:127-128/:222-223`（`hitl` 归类处）、`app/quality/eval.py:113`（`bucket["correctness"] = correct/total` ← 分母撒谎就这一行）、`:123`（`answer_correctness`）、`app/api/v1/chat.py:1414`（hitl 事件源）、新用例 | `app/quality/**`、`scripts/eval_transport_ask_v2.py` 与其余全部候选单**零交集** | R112/R117/R122 已并树（hitl 从 9 涨到 18 是它们的结果，§4BH.11 L3053） | 🔴 甲案（采集器有权批准）卡业主：它是业主侧账号，属 D 项；D10 的"改分母须另开 D 项"同样适用（L1858-351） | **等前置/等业主（半）**：乙案（分母 87 + 双数并报）与丙案（夹具标注不可终答）**不卡业主、可即刻派**；甲案等确认 |

### A-3 已并树的 14 枚（判据失效，只留索引，凭据见 §F）

| 单号 | 结案凭据（详见 §F） | 结论 |
|---|---|---|
| R30 R34 R35 R37 R40 R42 R44 R47 R49 R50 R51 R52 | 各有**非 merge 的实现提交**，`app/**` 改动清单见 §F | 销账；R34 留一笔（见 §C-1） |
| R110 R113 | `9b4154d`（nodes.py+spans.py+`tests/test_r110_stream_drop_closes_span.py`）、`9de5e89`（只改 `tests/test_observability_routes.py`） | 销账；总控清单里这两枚**不该出现** |

---

## B. 冲突簇（按真实共占文件归簇，理由只写依赖与写域大小）

### 簇 1 —— `app/agents/orchestrator.py` + `app/agents/nodes.py`（两文件一族，今天最紧的锁）
- 未开工占人：**R29 R31 R33 R43 R118**（R38 **不占** orchestrator.py；R32 **不占** 这两枚文件的必要改动）。
- 已并树占人（同族，构成"历史写域"证据）：R30（`50aff1a`：`orchestrator.py +14/-6`、`nodes.py +138`）、R42（`89965d5`：`nodes.py +161`、`orchestrator.py +13/-1`，落在 `route_main` `:511` 附近）、R51（`nodes.py`）、R110（`nodes.py`）。
- 🔴 **对总控原话的订正**：交集不是「R30/R31/R33/R42/R38 五单」，而是「R30/R42 已并树出域 + R31/R33/R43/R118 四单在域 + R29 视方案」；**R38 从来不在这一簇**（它的写域是 `model_handler.py`/`trace/*`）。计划书 §5.1 L167「六单全改 orchestrator.py/nodes.py」同样偏保守：R32 与 R38 都不改这两枚。
- **建议串行顺序：`R118 → R33 → R31 → R43`，R29 若裁定复活则插在 R31 之前（`R118 → R33 → R29 → R31 → R43`）。**
  1. **R118 第一**：它决定 `orchestrator.py:201/:212-215` 的子图到底 resume 不 resume，而 R33 要裁的正是"跨轮上下文"，R118 若选"承认失忆"则 R33 的裁剪面从"历史"缩到"本轮检索料"——**先定形状再定尺寸**，反过来做会白改一次 `:342`。
  2. **R33 第二**：它摘掉 `:342` 那发 `ModelTier.COMPRESS` 模型调用，直接改变 `synthesize`/`main_agent_node` 送给模型的消息列表；R31 的判据②「片段时间戳不重叠、逐字比对无缺字」必须在**已定型的消息列表**上验，否则验收样本本身还在动。
  3. **R29（若派）压在 R31 前**：这是计划书 §8 L372 硬依赖链原文 `R27 / R29 / R30 → R31`，理由是"给一条还要重排的管子做皮"；且 R29 改端点会重做 `tool_calls` 报文（§8 风险条款 4 L379），权限/超时语义复验必须在分片之前。
  4. **R31 第三**：写域横跨 `nodes.py`（`:483` 生成器）+ `chat.py`（`:1399` 出口）+ `orchestrator.py`（`:699/:1163/:1312/:1340`），是三文件交点，**必须独占**——它与 R32/R48 在 `chat.py` 另成一簇（簇 3）。
  5. **R43 最后**：它的前缀切分要按 R33（有无摘要段进 system 位）与 R31（流式下 system 段只能发一次）的结果来定；且判据② 卡 H1，早做也只能停在半验收态。

### 簇 2 —— `app/api/v1/chat.py`
- 未开工占人：**R31 R32 R48**（R123 只读它 `:1414`，不改）。
- 已并树占人：R35（`chat.py`+`cache.py`）、R37（`chat.py`）、R49（`chat.py`+`documents/**`）。
- **建议串行顺序：`R32 → R31 → R48`。** 理由：R32 定的是**请求面**（`lane` 字段、非法档 400、默认问答档），R31 的分片事件必须携带已定名的 lane 归属（`contract-v1.md:752-757` 三行 gated 槽等的就是这个标签），R48 的"首屏卡片 + 正文后台补"同时消费这两者（没有分片就没有首屏/正文之分，没有 lane 就没有分档 SLO 归属）。写域大小也同向：R32 ≈ 字段与校验、R31 = 出口重写、R48 = 出口 + 产物 + 前端。

### 簇 3 —— `docs/api/contract-v1.md`
- 未开工占人：**R32（三档 SLO 行）R105乙（九枚「待真机样本」空位）R48（`:753/:787-788` 首屏定义）**。
- 已并树占人：R111（`ae16fb2`，错误码分色登记）、R105甲（`3a67367`，把行结构与 22 枚钉落进 `tests/test_r105_slo_contract.py`）。
- **建议串行顺序：`R32 → R105乙 → R48`**：R32 先补 lane 行，R105乙 才有 3 枚 gated 槽可填（另 6 枚不受阻，可先行），R48 最后改首屏定义（它一旦动 `:753`，R105乙 刚填的 `first_text_p95_ms` 就要重算）。

### 簇 4 —— `app/rag/retrieval_pipeline.py`
- 未开工占人：**R46（`:466 rrf_fusion`）R119（`:591` 常数）**。已并树占人：R28/R45/R47（`006c613`）/R59 订正/R112（`:563-616` 装箱真源）。
- **建议串行顺序：`R119 → R46`**：R119 改的是"装得下多少"的尺，R46 改的是"谁先出来"的序；尺先定，R46 的判据②「无信号时与现状一致」才有一枚可比对的现状基线（反过来做，R46 结案当天 R119 的 room 复算就得重跑）。

### 簇 5 —— `tests/test_r112_prompt_packing.py`
- 未开工占人：**R119**（校准 `:260-268` 断言的上界）**R116**（把 46 枚参数化钉桩升级成按实测 `prompt_tokens` 复算 room）。
- 🔴 **这两枚不能同批派**，二选一或严格串行（建议 **R119 先**，R116 的"实测复算"要拿 R119 校准后的常数当输入）。

### 簇 6 —— `app/trace/**`
- 未开工占人：**R38**（`spans.py:269-278`、`store.py:259/270-271`）＋ R105乙 的 lane 落盘缺口（`app/trace/records.py` `git grep -n lane` **0 命中**，须另立单，跟进单 §28.5）。
- **建议：R38 先**，lane 落盘单在 R38 结案后再立（否则"记真值"和"加新字段"混在一次改里，R51 的被动观测护栏 `tests/test_r51_observation_is_passive.py` 会同时咬两单）。

### 簇 7 —— `migrations/**` + `deploy/**`（业主侧执行面）
- 未开工占人：**R46**（若要建计数表 ⇒ `0011_*` + `migrations/manifest.json` + `app/db/migrations.py`）、**R88**（在册，D8=**按住** L349）。
- 已并树：R90b→R120（`27c676f`，且 §4BH.11 L3066 亲验 `migrations/**` 零改动）。
- **建议：这两枚都不进并行批**，合并成一次"迁移演练"批次（human-gates L350 D9 的既有裁定就是"两单同文件族，一次迁移演练"），且必须业主放行（H12 已结，但"发布需业主侧执行迁移"这条对 `migrations/**` 仍生效）。

### 簇 8 —— `frontend/**`（本线不得写）
- 未开工占人：**R32 前端半、R48 卡片半**。已并树：R103（`3ecdcb4`）、R104（`caa4cd1`）、R89（`7c66397`）。
- **建议**：本图只出契约与数据形状，两枚的前端半张单**转前端线**（D13=甲已授权，AGENTS.md 禁本线改）。

---

## C. 死单 / 假单（只登记，未改任何原文档）

1. **R34「已结案」是半张单**——凭据：`git grep -n 'keep_alive\|KEEP_ALIVE' -- app/agents` **0 命中**（keep_alive 只在 `app/common/model_config.py`(3)、`model_handler.py`(11)、`model_budget.py`(1)），即**答题腿从未下发常驻**；跟进单 §44.4 L1519 原文自己写着「R34『keep_alive 常驻』的完成度要把这一半退回 R29，**不得记成 R34 已结案**」。**建议：改写**——R34 记为「已结案（仅 native/改写腿）」，剩余半并入 R29 判据，不另立新号。
2. **R44 的"真机延迟收益"是假结论（代码本身是活的）**——凭据：计划书 L194 自纠原文（105/105 覆盖是在 **379 chunk 小库 + 确定性哈希桩**上测的，真实 `documents/` 是 **37 483 chunk**；0.0015 ms 的前提是 HNSW，现实现为精确全量扫描）+ `git show --stat 39006b8`（实现提交 `9940c13` 只动 `app/rag/hot_index.py`/`retriever.py`，无真机规模数据）。**建议：作废的只是"收益已证"这句话**，代码保留，复测已转 R79④（`a704387`）。
3. **R45 的「`pred` 未接线」是假单**——凭据：计划书 L204 本班自纠（`retrieval_pipeline.py:314/:461/:558` 三处 pred 全部已接线，R45 已并 `0276f78`，247 行现为空行）。**建议：已就地撤销，无需动作**，登记防复抄。
4. **R33 判据大半失效**——凭据：① 上限半已由 R30 落地（`50aff1a`：`model_budget.py` +363 行、`context_limit_exceeded` 在**发请求前**拒，`nodes.py:379-387` 现在就是那条路）；② "零模型裁剪"半已由 R112/R117/R122 落地（`retrieval_pipeline.py:563-616` 装箱、`tools.py:658/694` 扣房、`[PromptPack]` 台账），全是纯算术无模型调用；③ 唯一还活着的缺陷是 `orchestrator.py:342` 那发 `ModelTier.COMPRESS` 模型调用（`git grep -n compress_messages -- app` 只此一处生产调用）。**建议：改写**为"摘掉 compress 腿的模型调用"（草案见 §G-4）。
5. **R38 判据前提过期**——凭据：`git grep -rn cached_tokens -- app migrations` **0 命中**（只在 `scripts/perf_probe_think.py:64`、`scripts/bench_model_throughput.py:259` 里作为探针读数），链路 `nodes.py:437 → spans.py:269-278 → store.py:270-271 → migrations/0002:161-162` **已在树**。**建议：改写**为"真机核值 + native 腿补读 `prompt_eval_count`"（草案见 §G-5）。
6. **R32 判据与 R37 的既成事实冲突**——凭据：`git diff --name-only 0c08209^1 0c08209 -- app` = `app/api/v1/chat.py`，而今天 `chat.py:759 lane: str = ""` + `:776-786 _queue_lane` 已存在且只认 report；照抄"三档进契约"会让下一班重复发明 `lane` 并与 `tests/test_r37_report_lane_enqueue.py` 打架。**建议：改写**（草案见 §G-3）。
7. **计划书 §6 阶段表（L328-331）把 13 枚已并树单仍列为待办**——凭据：§F 的 14 枚实现提交 + `merge-base --is-ancestor` 全通过。**建议：改写阶段表**，否则"阶段 B/C/D 没过"会被下一班读成"这十几枚没做"。特别地：阶段 B 内容列 `R29+R30+R31+R33+R34` 里只剩 R29/R31/R33 未落地。
8. **计划书 §5.2 L284 与 L279 自相矛盾**——L284 说「R21/R22 两单至今零代码提交」，L279 同节自纠说 R21/R22 前置已实测落码（`retriever.py:49/196/204`、`indexing.py:10-11`）⇒ P0 已清。**建议：作废 L284 那句**（实测：`git grep -n` 可复核这两处行号已在树）。
9. **计划书 §6 阶段 A 判据① 的"分档口径"只在工作区、未入库**——凭据：`git diff --stat docs/handoff/2026-09-17-perf-architecture-plan.md` = `1 file changed, 1 insertion(+), 1 deletion(-)`，唯一改动是 L328 那一行（09-20 21:3x 总控代业主裁定）。**建议：总控自行入库**；在此之前引用"问答类 p95 71.8 s ✅"必须注明它来自脏工作树。
10. **跟进单 §28.7 L988「R51 半占 ⇒ R31/R32/R33 挂起」是过期挂起令**——凭据：R51 已并树 `cef08bf`（`merge-base --is-ancestor` 通过）。**建议：作废该条**，别让下一班据此按住三枚单。

---

## D. 下一班可同批派出、彼此**零文件交集**的最大集合

派前提醒：跑分窗口在跑（窗口内禁 pytest/docker/HTTP/并树），下面的"可派"指**可以投简报开工写码**，验收动作一律压到收窗后。名册（§0）与 §4BH.11 一致：R111/R122/R120 三棵树已全并，**当前没有任何执行层 Agent 占树**。

| # | 单号 | 它独占的树 | 写域（逐枚点名） | 与其它批次成员的交集 |
|---|---|---|---|---|
| 1 | **R118** | `be-r118`（自 `2f965c1` 新建 `codex/be-r118`） | `app/agents/orchestrator.py`（`:198/:201/:212-215` 定策与注释/装配形状）、新 `tests/test_r118_*.py` | 无（本批唯它碰 orchestrator.py） |
| 2 | **R119** | `be-r119` | `app/rag/retrieval_pipeline.py:591/:616` 常数、`tests/test_r112_prompt_packing.py:260-275` 跟随校准、新 `tests/test_r119_*.py` | 无（本批唯它碰 retrieval_pipeline.py 与 test_r112 钉） |
| 3 | **R123 乙案** | `be-r123` | `app/quality/eval.py:113/:123`、`scripts/eval_transport_ask_v2.py:109/:127-128/:222-223`、新 `tests/test_r123_*.py`；🔴 禁碰 `tests/fixtures/**` 与 `tests/test_evaluation_report.py`（L1793） | 无（`app/quality/**` 与 `scripts/eval_*` 本批无人碰） |
| 4 | **R105 乙半（仅 6 枚非 gated 槽）** | `be-r105b` | `docs/api/contract-v1.md:744-757` 填数、`tests/test_r105_slo_contract.py`（加断言不改 22 枚钉的口径）、必要时 `app/api/v1/observability.py:778-868` 的行标签 | 无（本批唯它碰 contract-v1.md 与 observability.py） |
| 5 | **R38 代码半** | `be-r38` | `app/common/model_handler.py:356-377`（补读 `prompt_eval_count`）、`app/trace/spans.py:269-278`、`app/trace/store.py:259-271`、`app/agents/nodes.py:300-302/:435-437`、新 `tests/test_r38_*.py` | 无（本批唯它碰 model_handler/spans/store）；真机读数半等收窗 |

- 🔴 **不能塞进这批的**：R116（与 R119 共占 `tests/test_r112_prompt_packing.py`，簇 5）、R31/R32/R48（共占 `app/api/v1/chat.py`，簇 2）、R33/R43（共占 `orchestrator.py`，簇 1）、R46（`migrations/**` 卡业主 + 与 R119 共占 `retrieval_pipeline.py`）、R29（卡裁定，见 §A）。
- 建议规模：**5 枚**已是零交集上界（再多就会踩簇 1/簇 2）。若要第 6 枚，唯一无冲突候选是把 R123 拆出的"评分器把 hitl 单列"独立成 `app/quality/**` 内的第二棵——同文件，不成立。

---

## E. 与文档说法不符的地方（逐条：原话 → 实测 → 取证命令）

| # | 文档原话（或派工前提） | 我实测到的 | 取证命令（`git grep -n` 口径） |
|---|---|---|---|
| 1 | 总控派工：「R29 R30 R31 R32 R33 R34 R35 R37 R38 R40 R42 R43 R44 R46 R47 R48 R49 R50 R51 R52 共 20 枚在**整个仓库历史里零提交**，已用 `git log --all --oneline --grep='RNN'` 复核」 | 其中 **12 枚有实现提交且全在 HEAD 祖先链**：R30 `50aff1a`、R34 `e4d0c1b`、R35 `90d029f`、R37 `0c08209`、R40 `8585315`、R42 `89965d5`、R44 `39006b8`、R47 `006c613`、R49 `c26afda`、R50 `94f7fa1`、R51 `cef08bf`、R52 `8c888c7`。真零提交的只有 8 枚。**你的 grep 口径至少有两处会漏/会误**：① `--grep='R44'` 会同时命中 `R446`/分支名/别的单号（子串匹配），② 只看 subject 会漏 body（`git log --pretty=%s`）——但反过来，只看 subject 也**不会**把这 12 枚判成零提交，说明更可能是**在另一棵树/另一个 rev 上查的**（`git log --all` 只覆盖本机 ref，未 fetch 的远端分支不在内） | `git log --all --pretty='%h\|%ad\|%s\|BODY:%b' >%TEMP%\alllog_full.txt` 后用 `(?<![A-Za-z0-9])R44(?![0-9])` 词边界扫 subject+body；`git merge-base --is-ancestor <hash> HEAD`（28 枚候选逐枚，exit 0 = 在链上） |
| 2 | 计划书 §5.2 L194/L201 把 R44/R51 标「已结案 `39006b8` / `cef08bf`」 | 与 git 一致 ⇒ **是总控清单错，不是计划书错** | 同上 |
| 3 | 看板 §4AQ.9 L2240（09-18 18:5x）「仍零代码 11 单：R29 R31 R32 R33 R34 R38 R43 R46 R48 R50 R52」 | 在 09-18 当天成立；R34 `b1d185e`(09-19 17:49)、R50 `090c820`(18:06)、R52 `8c888c7`(20:43) 之后已并树 ⇒ 该节不可再当现状引用 | `git log --no-merges --grep` 逐号 + `--date=format` 看时序 |
| 4 | 看板 §4BD.2 L2723「计划书在册 27 单里最后一张零代码单 ⇒ **R25–R52 全部有码**」 | **过头**：R31/R32/R38/R48 四枚在 `git log --all` 的 subject+body 里**一次都没出现**，R33/R43/R46 各只出现 1 次且全在同一行文档正文（§4BB.2 派工面）⇒ "全部有码"当结论用会派错工 | 同 E-1 的词边界普查 |
| 5 | 跟进单 §21 R34 行 L506「`keep_alive` 现**全仓 0 命中**」 | 现状：`app/common/model_config.py` 3 处、`model_handler.py` 11 处、`model_budget.py` 1 处，**`app/agents/**` 0 处** ⇒ 常驻只覆盖 native/改写腿，答题腿从未下发；跟进单 §44.4 L1519 已自认这一半要退回 R29 | `git grep -c 'keep_alive' -- app`；`git grep -n 'keep_alive\|KEEP_ALIVE' -- app/agents` |
| 6 | 跟进单 §21 R38 行 L510「现 `cached_tokens=0`」 | `app/**`、`migrations/**`、`tests/**` 里 `cached_tokens` **零命中**，只存在于两枚 `scripts/perf_probe_*.py` 探针；写链已通 ⇒ R38 的真实缺口是"没做真机核值 + native 腿不读 `prompt_eval_count`" | `git grep -rn cached_tokens -- app migrations tests`；`git grep -n model_token_counts -- app` |
| 7 | 跟进单 §21 R32 行 L504「三档进契约 + 前端选择器」 | `lane` 字段已被 R37 落地一半（`chat.py:759`），但 `_queue_lane`（`:776-786`）**只认 `report`，非法档不拒 400**；`frontend/src/{lib,composables}` 里 `lane` 零命中（我只扫了这两个目录，未扫全 `frontend/src`，故"前端无选择器"只对这两目录成立） | `git grep -n 'lane\|LANE_\|tier' -- app/api/v1/chat.py app/agents/contracts.py`；`git grep -n 'lane' -- frontend/src/lib frontend/src/composables` |
| 8 | 跟进单 §28.7 L988「R51 半占（只许 span 创建路径）⇒ R31/R32/R33 挂起」 | R51 已并树 `cef08bf` ⇒ 挂起令过期 | `git merge-base --is-ancestor cef08bf HEAD` |
| 9 | 计划书 §5.2 L296/L299 与总控清单冲突：R110 写「✅ **已并树 `9b4154d`**」、R113 写「✅ 总控亲做 `9de5e89`」，但总控把 R110/R113 列为"未开工"；同节 L250/L310 又把 R105 乙半/L310 的 R116 写成 ⏸待派 | R110 落地即在源码里可见：`app/agents/nodes.py:600-603` `span.finish("cancelled", record_evidence=False)`，且 `tests/test_r110_stream_drop_closes_span.py` 在树；R113 = `tests/test_observability_routes.py` 单文件 | `git show --name-only 9b4154d`；`git diff --name-only 9b4154d^1 9b4154d`；`git ls-files tests \| Select-String r110` |
| 10 | 计划书 §5.2 L250 说 R105 乙半「必须等 D14甲 窗口，且压在 R110 之后」 | 两条前置今日**都已成立**（run3 18:59 收窗、run4 20:55 收窗 105/105，§4BH.11 L3045；R110 `9b4154d` 已并），但**新的阻塞换了位置**：3 枚 gated 槽需要 lane 落盘，而 `app/trace/**` 里 `lane` 零命中、`observability.py:732-735` 自陈"所有在线样本归 `lanes.unknown`" ⇒ 不是"等窗口"，是"等一枚尚未立号的 lane 落盘单" | `git grep -n lane -- app/trace/`；`git grep -n 'gated: needs lane labels' -- docs/api/contract-v1.md`（命中 3 行） |
| 11 | 计划书 §6 L328 阶段 A 判据①（含"问答类 p95 ≤90 s、run4 71.8 s ✅"） | 这段口径**只存在于未提交的工作区**（HEAD 的 L328 仍是未分档版本）⇒ 拿它当"文档已裁定"引用会引用到脏数据 | `git diff --stat -- docs/handoff/2026-09-17-perf-architecture-plan.md`；`git diff -U0 -- <同文件>`（唯一改动就是 L328） |
| 12 | 跟进单/计划书通篇的行号引用 | 同一枚 §21 标题在 `git grep -n`（LF 口径，全文 1859 行）是 **L487**，在 PowerShell `Select-String`（孤立 CR 也断行，全文 3223 行）是 **L973** ⇒ 两口径混用会造出"查不到这行"的假缺陷。跟进单里 **1364 处 `\r\r\n`** 是根因 | `git grep -c '' -- <文件>`；`python -c` 普查 `CR/LF/CRLF/\r\r\n` 计数 |
| 13 | 我上一轮自己的错话（一并登记，防你按它派工）：「R42 没落 `orchestrator.py`，真身全在 `nodes.py`」 | **错**。R42 同时改了 `orchestrator.py +13/-1`（落点在 `route_main`，今天的注释块在 `:511` 附近），`nodes.py +161` | `git diff --numstat 89965d5^1 89965d5 -- app/agents/orchestrator.py app/agents/nodes.py`；`git diff -U3 89965d5^1 89965d5 -- app/agents/orchestrator.py` |

---

## F. 逐枚落地凭据表（已判「并树」的 14 枚）

格式：`git show -s --format=%h|%ad|%s` 原文（日期为 author date），下接该提交实际改动的 `app/**` 清单，末行明写「实现提交 / 合并提交 / 仅提及单号」。

### R30

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `50aff1a|2026-09-18 12:56|merge(R30 Sartre): 7 model tiers each carry an explicit max_tokens delivered on the request; read timeout = clamp(margin*(prefill+decode)) with the 4 httpx phases split; context_limit_exceeded refused before sending and never laundered through the offline fallback; both .env samples generated from one source. Orchestrator re-verify: 111 + 194 passed/7 skipped on the caught-up base; independent knife on the stream-stall billing (2 failed, restored). Also completes 3 call sites the earlier wip left as TypeError. Pre-existing suite-ordering landmine reproduced identically on main tree -> ticketed separately, not this tickets regression.`
  - 该次并入落地的 `app/**`：`app/agents/contracts.py`、`app/agents/nodes.py`、`app/agents/orchestrator.py`、`app/agents/tools.py`、`app/api/v1/alerts.py`、`app/common/model_budget.py`、`app/common/model_handler.py`
  - 同批非 app 文件：`.env.example`、`deploy/.env.server.example`、`tests/test_error_code_vocabulary.py`、`tests/test_r30_config_defaults.py`、`tests/test_r30_context_limit_guard.py`、`tests/test_r30_model_tiers.py`、`tests/test_r30_timeout_budget.py`
- 实现侧：
  - `1eea673|2026-09-18 11:50|wip(R30): 总控代提交保住执行层(Descartes)因 429 中断的盘上改动 —— max_tokens/超时按档，待接续完成`
  - 该提交 `app/**` 清单：`app/agents/contracts.py`、`app/agents/nodes.py`、`app/common/model_budget.py`
  - 定性：**实现提交**
- 实现侧：
  - `3cb563b|2026-09-18 12:43|wip(R30 Sartre): per-tier max_tokens + prompt-sized split timeouts + stable context_limit_exceeded + env samples single-sourced; also completes 3 call sites the earlier wip left broken`
  - 该提交 `app/**` 清单：`app/agents/contracts.py`、`app/agents/nodes.py`、`app/agents/orchestrator.py`、`app/agents/tools.py`、`app/api/v1/alerts.py`、`app/common/model_budget.py`、`app/common/model_handler.py`
  - 定性：**实现提交**
- 实现侧：
  - `d563007|2026-09-18 12:56|test(R30 总控代补): RATIFIED 追认 context_limit_exceeded 出处 app/common/model_budget.py（写域在执行层之外，Sartre 已披露此欠账）`
  - 该提交 `app/**` 清单：**无**
  - 定性：只提及该单号的文档/测试提交
- 祖先链自证：`git merge-base --is-ancestor 1eea673 HEAD` → **在链上（exit 0）**

### R34

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `e4d0c1b|2026-09-19 17:49|Merge branch codex/be-r34b (R34 keep_alive 常驻) into codex/data-file-catalog`
  - 该次并入落地的 `app/**`：`app/common/model_config.py`、`app/common/model_handler.py`
  - 同批非 app 文件：`docs/handoff/2026-09-19-r34-keep-alive-residency.md`、`tests/test_r34_keep_alive_residency.py`
- 实现侧：
  - `b1d185e|2026-09-19 17:49|feat(R34): keep_alive 常驻进码 —— 连续问答不再每过一轮就重付一次冷加载`
  - 该提交 `app/**` 清单：`app/common/model_config.py`、`app/common/model_handler.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor b1d185e HEAD` → **在链上（exit 0）**

### R35

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `90d029f|2026-09-18 10:43|merge(R35): 答案缓存作用域与淘汰策略收口并入主树（总控复跑 147 passed / 12 skipped + 全局键反证成立）`
  - 该次并入落地的 `app/**`：`app/api/v1/chat.py`、`app/common/cache.py`
  - 同批非 app 文件：`tests/test_answer_cache_scope.py`、`tests/test_chat_cache_safety.py`、`tests/test_phase7_signal_line.py`、`tests/test_trace_orchestration.py`
- 实现侧：
  - `63651f1|2026-09-18 10:43|perf(R35): 答案缓存按授权输入投影作用域+内存回退补 TTL/LRU；总控收口订正门槛注释为真实语义并补全局键守门用例(反证:摘掉scope即泄漏) 147 passed`
  - 该提交 `app/**` 清单：`app/api/v1/chat.py`、`app/common/cache.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 63651f1 HEAD` → **在链上（exit 0）**

### R37

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `0c08209|2026-09-18 22:03|merge(R37 Mendel): 报告档进可靠队列（入队侧 9e50e60 + worker 侧 45b9720）—— 总控亲跑 2132 passed / 35 skipped / 0 failed 后并树；默认开关 REPORT_LANE_VIA_QUEUE 关，现网路径逐字节不变`
  - 该次并入落地的 `app/**`：`app/api/v1/chat.py`
  - 同批非 app 文件：`deploy/queue_worker.py`、`tests/test_r37_report_lane_enqueue.py`、`tests/test_r37_report_lane_worker.py`
- 实现侧：
  - `9e50e60|2026-09-18 20:54|wip(r37): 总控保活提交——Gauss 线蒸发(事故 #30)前的盘上活。入队侧已写完(AskRequest.lane + _queue_lane 纯规则零模型往返 + _enqueue_ask_turn 回执带 lane/reason + hitl_park_text/save_session_turn/record_hitl_awaiting 三个与同步路径同源的共用件)；🔴 worker 侧**从未落地**：tests 期望 queue_worker.REPORT_LANE / _report_lane_requested，而 deploy/queue_worker.py 一字未动 ⇒ 自证日志 _r37_before_red.txt 19:18:30 实取 **23 failed / 5 passed**。本提交只保数据，**不入主干、不作结案**；接续判据见跟进单 §35.1`
  - 该提交 `app/**` 清单：`app/api/v1/chat.py`
  - 定性：**实现提交**
- 实现侧：
  - `45b9720|2026-09-18 22:03|feat(R37): 报告档进可靠队列的 worker 半程 —— 载荷自声明档位才走能挂起的图, 跑完补写会话历史`
  - 该提交 `app/**` 清单：**无**
  - 定性：**实现提交（零 app/**，只动 tests/deploy/scripts）**
- 祖先链自证：`git merge-base --is-ancestor 9e50e60 HEAD` → **在链上（exit 0）**

### R40

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `8585315|2026-09-18 11:35|merge(R40): 费用预审标准自动取数并入主树 —— 总控独立复跑 84 passed + 自下 4 刀反证(4 failed/7 failed/1 failed/1 failed)全部被咬住，字节级还原`
  - 该次并入落地的 `app/**`：`app/api/v1/intelligence.py`、`app/approval/assistant.py`、`app/common/authorization.py`
  - 同批非 app 文件：`tests/test_approval_precheck_standard_source.py`
- 实现侧：
  - `dc31a44|2026-09-18 11:26|feat(R40): 费用预审标准自动取数 —— 部门取会话不取请求体(伪造即 403 department_override_denied+审计) + standard_source 非法拼写拒 400 invalid_standard_source + auto 模式无条件覆盖前端数字与出处(取最严限额, 无数字则 standard=None 不编造) + 检索不可问回退 503 不续算; 总控复跑 84 passed`
  - 该提交 `app/**` 清单：`app/api/v1/intelligence.py`、`app/approval/assistant.py`、`app/common/authorization.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor dc31a44 HEAD` → **在链上（exit 0）**

### R42

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `89965d5|2026-09-18 14:08|merge(R42 Planck): 快慢双道判别器按 ⑤ 收窄结案 —— 规则优先、零模型往返；③ 占比降级为报告值(实测天花板 47.6%，原写死的 60% 与生产流量形状混了源)，新增硬门 ⑤ 快道不得接任何'口径词+取值动词'的求数题(闭集词表独立成文反假绿 + metric-06 锚题 + 恰好 6 条战果名单 + 反向不误伤门 + 已知缺口不扩大)，⑥ 重算水位 精度 75.4%->83.05% / 召回 98% 不变(门槛 70%/90% 一字未动)；scope-05 是唯一召回例外。Orchestrator re-verify on a tree caught up to 8d69ee6: 86 passed 五件合批(与自述逐字) / 自下 2 刀均咬住(⑤ 规则降级到最后 => 12 红; ⑤ 由 AND 改 OR => 5 红) / FULL suite 1663 passed 35 skipped 0 failed; 十刀反证与两次字节 sha 恒等由 worker 自证、总控复核其还原`
  - 该次并入落地的 `app/**`：`app/agents/nodes.py`、`app/agents/orchestrator.py`
  - 同批非 app 文件：`tests/test_r42_fallback_upgrade.py`、`tests/test_r42_lane_ratio.py`、`tests/test_r42_lane_rules.py`、`tests/test_r42_numeric_questions.py`、`tests/test_r42_zero_model_calls.py`
- 实现侧：
  - `5ff93cd|2026-09-18 14:01|wip(R42 Planck 交工待验): 判据③ 降级为报告值 + 新硬门⑤(快道不得接'要算出一个数'的题, 闭集词表+元断言反假绿) + ⑥ 水位重算(精度 75.4->83.05%, 召回 98% 不变)；十刀反证全按字节还原；r36q/ 属业主删除清单未入库`
  - 该提交 `app/**` 清单：`app/agents/nodes.py`、`app/agents/orchestrator.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 5ff93cd HEAD` → **在链上（exit 0）**

### R44

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `39006b8|2026-09-18 15:12|merge(R44 Tesla): 热集进程内检索索引(默认关, HOT_INDEX_ENABLED 未知值一律当关) - app/rag/hot_index.py 新模块 511 行 + retriever 挂子(写钩子在 _write_batch 成功之后, 全库唯一入库入口未变, 不长第三条腿), pre-filter 逐条先于截断(R45 裁定同构), 每条 HotChunk 自带 scope_key=(INDEX_BACKEND,模型,维度,索引版本) 且口径变更整体作废(宁慢不错), 冷表未覆盖/花名册过期/无向量/异常一律退回外部向量库且结果逐条一致; Orchestrator re-verify on be-r37 caught up to 69b0553: 全量 1828 passed 35 skipped 0 failed(= 主树 1791 + 本单净增 37, --collect-only 1826 vs 1863 对账吻合, 相对主树净改动恰 5 文件), 105 题覆盖率 105/105 且同预算塌到 3 chunk 时覆盖率当场塌成 0/105(证明 100% 不是自证); 总控另下三把不在 worker 八把刀列表里的刀且全部咬住: N1 把权限谓词从截断前搬到截断后 => 恰 2 红(两条 prefilter_before_truncation, 而「外来文档不可见」那几条仍然绿 => 次序只被这两条钉住, R45 硬门有牙), N2 把热层异常兜底改成 raise => 恰 1 红(可丢弃加速层不许把检索问出异常), N3 让 bypass 也计一次 hot hit => 恰 1 红(观测账实), 三把均 sha256 恒等还原(79b7efda/b6097103)后 git status 干净; 结案口径订正: 判据①的 100% 覆盖与 0 次外部往返是在确定性哈希桩 embedding 上测的, 只证明「热集能服务且与外部库逐项相等」, **不构成真机延迟收益结论**(本实现是精确全量扫描 O(常驻条数), 计划书那句 0.0015 ms 的前提是 HNSW), 真机收益待 H11/H12 后复测; 执行层五件待裁总控已裁并转新单 R79(诊断挂 /health/details + TTL/MAX_CHUNKS 两个默认值钉用例 + 向量 float32 省 8 倍) 与订正 R59(切读 PGVector 必须连热集读源一起迁, 且 retrieval_pipeline.py:247 要么真传 pred 要么删掉这个只被用例驱动的入参); 执行层自曝 TTL 默认值 0 红记为 R79 判据`
  - 该次并入落地的 `app/**`：`app/rag/hot_index.py`、`app/rag/retriever.py`
  - 同批非 app 文件：`tests/test_r44_hot_index_chroma.py`、`tests/test_r44_hot_index_coverage.py`、`tests/test_r44_hot_index_unit.py`
- 实现侧：
  - `9940c13|2026-09-18 15:05|wip(R44 Tesla 交工待验): 热集进程内检索索引 - app/rag/hot_index.py 新模块 + retriever 挂子(写钩子/读源/失效), pre-filter 先于截断, 每条带 scope_key(backend/模型/维度/索引版本); 新增 37 条用例(17 unit + 18 chroma + 2 coverage) + 8 把反证刀(K8 TTL 默认值 0 红已如实报告)`
  - 该提交 `app/**` 清单：`app/rag/hot_index.py`、`app/rag/retriever.py`
  - 定性：**实现提交**
- 实现侧：
  - `564340e|2026-09-18 16:05|fix(rag): R44b hot index must page the roster read and back off on warm failure`
  - 该提交 `app/**` 清单：`app/rag/hot_index.py`、`app/rag/retriever.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 9940c13 HEAD` → **在链上（exit 0）**

### R47

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `006c613|2026-09-18 11:39|merge(R47): 术语/同义词接入检索改写并入主树 —— 总控独立复跑检索邻域 123 passed + 自下 5 刀反证(9/2/1/7/1 failed 全咬住)；R28 兼容边界经实测裁定保留长度门槛(评测集 0/105 题面≥24 字)`
  - 该次并入落地的 `app/**`：`app/rag/retrieval_pipeline.py`
  - 同批非 app 文件：`tests/test_retrieval_synonym_expansion.py`
- 实现侧：
  - `95a1cd9|2026-09-18 11:37|feat(R47): 术语/同义词接进检索改写 —— 命中指标定义的 match_terms 做纯规则扩展(零模型往返), 只填 MAX_RECALL_QUERIES 剩余槽位, 扩展 query 复用同一 where/pred 不绕权限预过滤, owner 口径与 orchestrator 一致; 总控复跑邻域 123 passed`
  - 该提交 `app/**` 清单：`app/rag/retrieval_pipeline.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 95a1cd9 HEAD` → **在链上（exit 0）**

### R49

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `c26afda|2026-09-18 12:45|merge(R49 Fermat): index slimming by content features - upload answers a stable reason before any embedding spend; refused uploads are never silently deleted; index_status as orthogonal sidecar field (parse_status CHECK in migrations/0006 untouched). Orchestrator re-verify: 10+24+14=48 passed on real corpus (97 docs, 0 excluded), neighborhood 245 passed, plus one independent knife not in the workers list (title-punctuation escape -> ratio 0.5 to 0.6471, calibration red, restored byte-exact)`
  - 该次并入落地的 `app/**`：`app/api/v1/chat.py`、`app/documents/catalog.py`、`app/documents/index_policy.py`
  - 同批非 app 文件：`tests/test_r49_corpus_calibration.py`、`tests/test_r49_index_policy_rules.py`、`tests/test_r49_upload_contract.py`
- 实现侧：
  - `8680f43|2026-09-18 12:41|wip(R49 Fermat): index slimming by content features; exclusion returns stable reason; index_status as orthogonal sidecar field (no parse_status change: migrations/0006 CHECK pins 4 values); refuses to delete non-duplicate uploads`
  - 该提交 `app/**` 清单：`app/api/v1/chat.py`、`app/documents/catalog.py`、`app/documents/index_policy.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 8680f43 HEAD` → **在链上（exit 0）**

### R50

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `94f7fa1|2026-09-19 18:06|Merge branch codex/be-r50 (R50 增量索引与可续跑重建) into codex/data-file-catalog`
  - 该次并入落地的 `app/**`：`app/rag/indexing.py`
  - 同批非 app 文件：`scripts/rebuild_index.py`、`tests/test_r50_incremental_index.py`、`tests/test_r50_resumable_rebuild.py`
- 实现侧：
  - `090c820|2026-09-19 18:06|feat(R50): 索引重建改增量 + 可续跑 —— 换一次 embedding 不再需要清空整个窗口`
  - 该提交 `app/**` 清单：`app/rag/indexing.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 090c820 HEAD` → **在链上（exit 0）**

### R51

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `cef08bf|2026-09-18 16:17|merge(R51 Darwin): 阶段化 P50/P95 观测账本（观测不改行为，开关 STAGE_TIMING_ENABLED）`
  - 该次并入落地的 `app/**`：`app/agents/nodes.py`、`app/api/v1/auth.py`、`app/api/v1/observability.py`、`app/common/performance.py`、`app/common/stage_timing.py`、`app/trace/spans.py`、`app/trace/store.py`
  - 同批非 app 文件：`tests/test_r51_observation_is_passive.py`、`tests/test_r51_stage_latency.py`
- 实现侧：
  - `6833140|2026-09-18 16:16|feat(observe): R51 Darwin: 阶段化 P50/P95 账本(不改行为) - stage_timing 把 span 折成五段(classify/rewrite/retrieve/generate/reflect)+按 lane/tier 分组回读 R42 成本占比`
  - 该提交 `app/**` 清单：`app/agents/nodes.py`、`app/api/v1/auth.py`、`app/api/v1/observability.py`、`app/common/performance.py`、`app/common/stage_timing.py`、`app/trace/spans.py`、`app/trace/store.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor 6833140 HEAD` → **在链上（exit 0）**

### R52

- **无合并提交**：直接在主树 `codex/data-file-catalog` 上落码（总控亲做/直提）
- 实现侧：
  - `8c888c7|2026-09-19 20:43|feat(R52): 断外网自检成机器闸 + 内网 HTTPS 配置面 + 批量账号验收件（默认 dry-run）`
  - 该提交 `app/**` 清单：**无**
  - 定性：**实现提交（零 app/**，只动 tests/deploy/scripts）**
- 祖先链自证：`git merge-base --is-ancestor 8c888c7 HEAD` → **在链上（exit 0）**

### R110

- 并入主树（**合并提交**，本身不写产品代码，只把下面的实现提交带进 HEAD 祖先链）：
  - `9b4154d|2026-09-20 16:24|Merge branch codex/be-r110 (R110 流被丢弃时用 cancelled 收口 span 且不进证据袋) into codex/data-file-catalog`
  - 该次并入落地的 `app/**`：`app/agents/nodes.py`、`app/trace/spans.py`
  - 同批非 app 文件：`tests/test_r110_stream_drop_closes_span.py`
- 实现侧：
  - `f7971d3|2026-09-20 15:26|R110 保活提交（总控代做，尚未验收）：流被消费方丢弃时用 cancelled 收口 span，且不进证据袋`
  - 该提交 `app/**` 清单：`app/agents/nodes.py`、`app/trace/spans.py`
  - 定性：**实现提交**
- 祖先链自证：`git merge-base --is-ancestor f7971d3 HEAD` → **在链上（exit 0）**

### R113

- **无合并提交**：直接在主树 `codex/data-file-catalog` 上落码（总控亲做/直提）
- 实现侧：
  - `9de5e89|2026-09-20 16:22|R113（总控亲做·测试卫生）：入库第一份真机分数后 no_reports 那枚用例必须同时中和随镜像发布的 DEFAULT_EVALUATION_REPORT_FILES——路由在配置目录之后无条件追加默认件（observability.py:332），用例钉的「配置为空即无报告」在默认件存在后不再自洽。主树复跑 24 passed`
  - 该提交 `app/**` 清单：**无**
  - 定性：**实现提交（零 app/**，只动 tests/deploy/scripts）**
- 祖先链自证：`git merge-base --is-ancestor 9de5e89 HEAD` → **在链上（exit 0）**


### F-2 销账 / 留账判定（总控按这一栏动手）

| 单号 | 判定 | 依据（§F 里的具名凭据） |
|---|---|---|
| R30 R35 R37 R40 R42 R44 R47 R49 R50 R51 R110 | **销账（有实现提交，`app/**` 有真实改动）** | `3cb563b` / `63651f1` / `9e50e60`+`45b9720` / `dc31a44` / `5ff93cd` / `9940c13`+`564340e` / `95a1cd9` / `8680f43` / `090c820` / `6833140` / `f7971d3` |
| R34 | **销账但留一笔** | `b1d185e` 只动 `model_config.py`/`model_handler.py`，`app/agents/**` 零命中 keep_alive ⇒ 答题腿那半转 R29（§C-1） |
| R52 | **销账（代码件），真机三半留账** | `8c888c7` 零 `app/**`，写域在 `scripts/`+`deploy/`+`tests/`；看板 §4BD.2 L2722 标题自己写着「真机三半挂账」 |
| R113 | **销账（纯测试件）** | `9de5e89` 只改 `tests/test_observability_routes.py` ⇒ 别记成产品改动 |
| R44 | **销账 + 结论作废** | 代码在树（`39006b8`），但"真机延迟收益"结论被计划书 L194 自纠推翻 ⇒ 转 R79④ |
| —— |  |  |

---

## G. 未落地的单（逐枚：判据原文位置 → 当前源码行号 → 是否被推翻）

### G-1 R29（未落地，零实现提交）
- 判据原文：跟进单 §21 表 **L501**（四判据：① `thinking` 字段实测为 0 字；② 生成轮 30.6 s → ≤22 s；③ 前置 R36 质量基线；④ `tool_calls` 报文重做后权限/超时全复验；禁改边界「不许只在 `/v1` 加参数就当完成」）；边界条款跟进单 **L1298**（🔴 不许碰 `nodes.py`/`_make_model`，那是 R29 的边界）、**L1300**（R92 并树之后才允许派 R29）。
- 当前源码行号：`app/common/model_handler.py:414 chat()`、**`:435 if not stream:`**（原生腿只在非流式分支被尝试）、`:311/:327 _native_chat`（payload 写死 `"stream": False`）、`:450-467` 兼容腿（含 `:466 if stream: return self._release_after_stream(...)`）；答案腿 `app/agents/nodes.py:606 _make_model` 建的是 `ChatOpenAI`（`:635-643`），思考策略在 `app/common/model_budget.py:413 resolve_model_thinking`、`:460 thinking_extra_body`，落请求体在 `app/agents/nodes.py:204 _with_thinking_field`。
- 是否被推翻：**部分改写、未推翻**。R92（`ebfb1c9`→`9626b7d`）把**改写腿**迁到原生 + `think:false`，R100（`158259f`→`82c42b4`）让**兼容腿真的带 thinking 字段**，R34（`b1d185e`）把 keep_alive 送进两条腿 ⇒ 判据① 在改写腿已可验、**答题腿仍未验**；判据③ 的 R36 真机基线今日已成立（run3 `correctness 0.4571` / run4 同分，§4BH.11 L3047）。**真剩的活**：答题腿的端点选择 + 常驻半张单（§C-1）。
- 🔴 另一处必须写进派工词：**09-20 有一条"不做"裁定**（文档提交正文：「本窗口留 compat；B=复活 R29 且前置倒置，不做」，出自 R101 结案那批，跟进单 §42.2 L2812）。要派 R29，总控得先显式撤这条裁定。

### G-2 R31（未落地，全仓 subject+body 零提及）
- 判据原文：跟进单 §21 **L503**（① `text` 事件数 >1；② 片段时间戳不重叠、逐字比对无缺字；③ 每片 ≥20 字或 100 ms 合并、禁单字碎片；④ 与 legacy 全量重发共存；🔴 禁改 `frontend/**`）；计划书 L181、§2.7 L77（两个静默陷阱）。
- 当前源码行号：`app/api/v1/chat.py:1399`（**单枚** `event: text` 携 `full_text`）、`:1204-1209`（缓存命中路径同样单枚）、`:1230-1238`（`run_with_stream` 消费点）、`:911-918`（**只有 legacy `/chat` 明文端点**逐字流，且 `:921` 自己提示"改用 /api/v1/ask"）；`app/agents/orchestrator.py:699 stream_mode="values"`、`:1095 run_with_stream`、`:1163/:1312/:1340`；生成器本体 `app/agents/nodes.py:483`（`:525 for chunk in self.primary.stream(...)`、`:593-603` 是 R110 的丢弃收口）。
- 是否被推翻：**未推翻，但"全仓没流式"这句不准**：生成器与 R110 收口都在树，缺的是**答题腿不消费它**（跟进单 §43 **L1474** 原话：所有生产调用点都用 `.invoke()`，「只是产品面还没上线流式」）。⇒ 判据① 今天仍不可验。

### G-3 R32（判据需改写，不是照抄）
- 判据原文：跟进单 §21 **L504**（① 契约写出三档 SLO；② 档位不改变权限判定；③ `/ask` 非法档 → 400；边界「不得借分档放宽 scope」「legacy 事件名一个不许下线」）。
- 当前源码行号：`app/api/v1/chat.py:754 class AskRequest`、`:759 lane: str = ""`、`:765 LANE_REPORT`、`:776-786 _queue_lane`、`:1158 lane=""`、`:1162-1163`（唯一消费者，且 `== LANE_REPORT` 才生效）；`app/agents/nodes.py:696-700 LANE_QA/LANE_ANALYSIS/LANE_REPORT`、`:782 classify_route`、`:805 _route_rules`；`app/api/v1/observability.py:804 lanes = (LANE_QA, LANE_ANALYSIS, LANE_REPORT)`、`:817 bridge_from_product_lane`；`docs/api/contract-v1.md:752-757`（三行 `gated: needs lane labels`）。
- 是否被推翻：**已被 R37（`0c08209`）+ R42（`89965d5`）+ R105甲（`3a67367`）联合改写**：字段名 `lane` 已定、服务侧判别器已定、三档行结构已定；剩下的真身只有"客户端可选 + 非法档 400 + 三档 SLO 数值"。
- **可执行的判据草案（改写版，建议照抄进新简报）**：
  1. `AskRequest.lane` 取值集合扩到 `{"" , "qa", "analysis", "report"}`，**空串＝服务端按 R42 判别器自选**（保持 `classify_route` 为唯一自选口，不许前端传了就绕过判别）；非法值 → **`400` + 稳定码**（码走 `app/agents/contracts.py` 的 `ErrorEnvelope.code` 封闭枚举，先在 `tests/test_error_code_vocabulary.py` 的 RATIFIED 表挂号，不许现造裸串）。
  2. 反证两枚：把 `_queue_lane`（`:776-786`）的"只认 report"改成"三值透传"后，`tests/test_r37_report_lane_enqueue.py` 与 `tests/test_r42_lane_rules.py` **必须仍绿**（档位标签不得改变入队判定）；非法档不返 400 ⇒ 新用例当场红。
  3. 判据②：同一题在 qa/analysis/report 三个 lane 标签下，`resolve_document_retrieval_scope` 的入参与命中集合**逐字节相同**（用 `app/rag/filters.py` 的 scope 断言，不许只看响应文案）。
  4. 契约半：`docs/api/contract-v1.md:752-757` 三行的 `gated: needs lane labels` 撤掉 gating 的前提 = `app/trace/records.py` 真的落 lane（当前 `git grep -n lane -- app/trace/` **0 命中**）⇒ **本单不许顺手落 lane**，另立单（跟进单 §28.5 既有裁定）。
  5. 前端半张单**移出本单**，转前端线（AGENTS.md 禁本线改 `frontend/**`）。

### G-4 R33（判据需改写）
- 判据原文：跟进单 §21 **L505**（① 每发 prompt token 有硬上限且日志可见；② 裁剪过程**零模型调用**；③ 与 R36 同批合并；禁改「不许裁掉权限谓词与来源定位串」）；计划书 §8 风险条款 1 L375。
- 当前源码行号：`app/agents/orchestrator.py:50`（import）、**`:342 all_msgs = compress_messages(all_msgs, _make_model(ModelTier.COMPRESS))`**；`app/memory/summarizer.py:37 compress_messages`、`:49`（造 `【历史摘要】` 的 `SystemMessage`）；上限侧已在树：`app/agents/contracts.py:157 input_budget_tokens`、`app/common/model_budget.py` 的 `authorize_call`/`context_limit`（R30 `3cb563b`），装箱侧已在树：`app/rag/retrieval_pipeline.py:563-616`、`app/agents/tools.py:658/:694`。
- 是否被推翻：**判据① 已被 R30 满足、判据② 的检索料半已被 R112/R117/R122 满足**；只剩"消息历史裁剪仍要花一发模型"。
- **改写草案**：把判据收窄成三条可机器验的：① `app/agents/orchestrator.py` 内 `ModelTier.COMPRESS` **零调用点**（AST 级用例，摘掉即红），且 `ModelTier.COMPRESS` 枚举本身保留或删净必须与 `app/common/stage_timing.py:51-60` 的分段标签表同时订正（那张表把 `compress` 归到"五段之外"）；② 新的历史裁剪必须是纯确定性（按 `input_budget_tokens` 保留最近 N 条 + 中间条按字符截断），**零 provider 调用**，用例用计数桩钉（复用 `tests/test_r42_zero_model_calls.py` 的桩形）；③ 硬护栏：裁剪后消息列表里 `where`/`pred` 用到的权限谓词文本与 `[来源: ...]` 定位串**一条不许少**（正反用例各一枚，反例文本从 `app/rag/filters.py` 与 `app/agents/evidence.py:82` 取）。

### G-5 R38（判据需改写）
- 判据原文：跟进单 §21 **L510**（「抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致」；禁改「不得估算冒充实测 token 数」）；计划书 L188 与 §2.5 L63（已把"零写入"降级为"待核实"）。
- 当前源码行号：`app/agents/nodes.py:300-302`（离线腿）、`:435-437`（正常腿 `summary = dict(model_token_counts(response))`）；`app/trace/spans.py:269-278`、`:77/:85-86/:174`；`app/trace/store.py:259`（`first_token_at` 合并）与 `:270-271`（两列写入）；`migrations/0002_execution_data_lineage.sql:147-165`；`app/storage/persistence.py:404`（列白名单）。
- 是否被推翻：**推翻的是"列写零"这个说法，不是缺陷本身**。缺口收敛到两处可指名的：① `app/common/model_handler.py:356-377` 的 native 应答只取 `eval_count`（`:360`），**没读 `prompt_eval_count`** ⇒ 原生腿的 `input_tokens` 永远是 `None`；② 兼容腿取的是 LangChain `usage_metadata`（`spans.py:270`），与 Ollama 自报是否一致**从未抽查**。
- **改写草案**：① native 腿 `ModelReply` 增设 `input_tokens`（取 `prompt_eval_count`），并在 `:363` 那行日志同侧打出来，**不许用 `estimate_prompt_tokens` 顶包**（`app/common/model_budget.py` 里那把估算尺与真值必须同时打印以便对照，估算值不得进 `model_calls` 列）；② 一条对账用例：桩化一份带 `prompt_eval_count` 的 `/api/chat` 响应 ⇒ 落进 `model_calls.input_tokens` 的数逐枚等于它；③ 真机抽查半：等收窗后从容器日志/库里取 ≥20 发对账（本图不跑，属窗口后动作）；④ 护栏：`tests/test_r51_observation_is_passive.py`（R87 改造后的 20 枚）**不许变红**，本单不得改其行为。

### G-6 R43（未落地，全仓 subject+body 仅 1 次文档提及）
- 判据原文：跟进单 §21 **L514**（① 同一前缀字节级稳定（无时间戳/无随机顺序）；② E3 档实测 `cached_tokens > 0`；禁改「不许把权限信息塞进可复用前缀」）；计划书 L193（外部锚 llm-d TTFT）。
- 当前源码行号：`app/agents/orchestrator.py:203-207`（四枚 worker prompt）、`app/memory/summarizer.py:49`（摘要进 SystemMessage 首位）、`app/api/v1/chat.py:899-909`（参考文档拼在指令前）、`app/rag/retrieval_pipeline.py:203 rewrite()`、`app/agents/nodes.py:991 synthesize`。
- 是否被推翻：**未推翻，但判据② 现在不可验**（H1 未做）⇒ 建议把 ② 降级为报告值、①升格为硬门（AST/字节级"同一问两发的公共前缀长度 ≥ 全 prompt 的 X%"断言），并在派工词里写死"禁止把 `department`/scope 文本挪进可复用前缀"（现 `filters.py` 的 where 构造即为反例锚）。

### G-7 R46（未落地，仅 1 次文档提及）
- 判据原文：跟进单 §21 **L517**（① 有信号后排序变化可测；② 无信号时与现状一致；③ 只存计数不存内容；禁改「不得把用户问题原文写进新表」）。
- 当前源码行号：`app/rag/retrieval_pipeline.py:466 rrf_fusion`（`:478 rrf_score = 1.0/(k+rank)` 是要挂先验的唯一乘子位）、`app/agents/contracts.py:314 score_type`（`"rerank"` 枚举已备）、`app/agents/evidence.py:82/:192`、`app/api/v1/chat.py:267`；信号源候选 `migrations/0008_pending_approvals.sql:33`、`app/semantics/registry.py:61`（rejected 态）。
- 是否被推翻：**未推翻**，但"新表"这一半**未必要**：`migrations/0002:170-182 retrieval_traces` 已有 `query_hash CHAR(64)` 与 `result_summary JSONB`，判据③ 的"不存原文"由 `query_hash` 天然满足 ⇒ 建议判据加一条前置问句：**先答"能否用 `result_summary` JSONB 承载计数"**，能则本单不碰 `migrations/**`、不卡 D8/H12 那类业主闸门；不能才立 `0011`（届时与 R88 同批做迁移演练，human-gates L350）。

### G-8 R48（未落地，全仓零提及）
- 判据原文：跟进单 §21 **L519**（① 首屏 ≤1 s 有可用结论；② 后台补齐失败有明确标注；禁改「不得先渲染结论再纠正成不同答案，前端 `_correcting` 路径要避开」）。
- 当前源码行号：`app/api/v1/chat.py:1399`（首屏当前等于终态，无早发结论位）、`:1204-1209`；口径已在树但**只是口径**：`app/api/v1/observability.py:732-744`（`lane_attribution_absent` 等三枚 known-gap）、`:868 label_zh="首屏（第一个 text 事件）"`、`docs/api/contract-v1.md:753/:787-788`；`first_token_at` 记录点 `app/trace/spans.py:77/:85-86/:174`（`contract-v1.md:787` 自陈它不是 stage 样本）。
- 是否被推翻：**未推翻，但判据① 的前提（R31 分片）未落地**，且判据② 的"标注"需要一处新事件名 ⇒ 与 legacy 事件冻结规则（计划书 §7 L360、跟进单 §21 L512「一个 legacy 事件名都不许下线」）同族，派工词必须写明"只加 canonical 事件、不动 legacy"。

### G-9 新单四枚的现状核对
- **R105 乙半**：判据 跟进单 §51 **L1641**；落点 `docs/api/contract-v1.md:744-757`（九枚空位、其中 3 枚 gated）、`tests/test_r105_slo_contract.py`（22 枚 `def test`）、`app/api/v1/observability.py:778-868`、`app/common/performance.py:12/:47`。**被推翻的是"等窗口"这个前置**（run3/run4 已各 105 样本，§4BH.11 L3045），**新立的是 lane 落盘缺口**（`app/trace/records.py` 零 `lane`）。
- **R118**：判据 跟进单 §55 **L1729-1731**；落点 `app/agents/orchestrator.py:201`（注释与事实不符，实测在 §55② 探针）、`:212-215`。未被推翻；R117（`f29a020`）结案使它从"等 R117"变"可定策"。
- **R119**：判据 跟进单 §55 **L1733-1735**；落点 `app/rag/retrieval_pipeline.py:591`、`:616`、`app/agents/tools.py:658/:694`、`tests/test_r112_prompt_packing.py:260-275`。未被推翻；🔴 与 R116 共占 `tests/test_r112_prompt_packing.py`（簇 5）。
- **R123**：判据 跟进单 §57 **L1788-1793**；落点 `app/quality/eval.py:113/:123`、`scripts/eval_transport_ask_v2.py:109/:127-128/:222-223`。未被推翻；§4BH.11 L3053 的 run4 复算（`hitl→hitl` 18 枚照旧）反而**加强**了它。甲案卡业主，乙/丙案可即刻派。

---

## 调查员自报

**本单未跑任何 pytest / docker / HTTP**：未执行任何 `pytest`（含单文件与 `-k` 子集）、未执行 `docker` / `docker compose` 任何子命令、未向 `127.0.0.1:8001` 或 Ollama（`:11434`）发过任何请求、未启动或重启任何服务、未跑 `npm`/`vitest`/`verify_container_stack.py`/`check_*` 任何门禁件；未 `git add`、未 `commit`、未 push、未建分支或 worktree。
**未改本文件以外的任何路径**：`chroma_db/**`、`documents/**`、`data/**`、`docs/testing/**`、`frontend/**`、`static/**` 一字未动；接手时工作树既有的脏项（`chroma_db/**` 6 枚 M、`docs/handoff/2026-09-17-perf-architecture-plan.md` 1 行 M、6 枚未跟踪件）本单**未触碰、未清理**。全部取证为只读；临时产物只落在 `%TEMP%`（`alllog.txt`、`alllog_full.txt`、`lfdump.py`、`mk_f.py`、`um_1.md`、`um_f.md`）。

### 实际跑过的命令清单

- `git rev-parse --abbrev-ref HEAD`、`git rev-parse --short HEAD`、`git status --porcelain`
- `git diff --stat -- docs/handoff/2026-09-17-perf-architecture-plan.md`、`git diff -U0 -- <同上>`
- `git log --all --oneline --grep='<单号>'`（子串口径，即总控误判来源）
- `git log --all --pretty='%h %ad %s' --date=format:...`、`git log --all --pretty='%h|%ad|%s|BODY:%b'`（导出到 `%TEMP%` 后做词边界正则普查）
- `git merge-base --is-ancestor <hash> HEAD`（28 枚候选哈希逐枚）
- `git show --stat --oneline <hash>`（`1eea673 3cb563b d563007 50aff1a b1d185e 090c820 8c888c7`）
- `git show -s --date=format:%Y-%m-%d %H:%M --format=%h|%ad|%s <hash>`（F 节 22 枚）
- `git show --name-only --format= <hash> -- app`（F 节逐枚 `app/**` 清单）
- `git log --no-merges --pretty='%h %s' <merge>^1..<merge>^2`（13 枚合并提交，定位实现提交）
- `git diff --name-only <merge>^1 <merge> [-- app]`（13 枚，"实际落进主干"的文件面）、`git diff --numstat`、`git diff -U3 ... -- app/agents/orchestrator.py`
- `git ls-files`（根、`tests`、`migrations`、`scripts`、`app/quality`、`app`、`frontend/src`）、`git grep -c ""`（行数普查）
- `git grep -n` 模式（全部只读）：`^## 21\.`、`^### 4BH`、`^### 51\.|^### 49\.|^## 55\.|^### 57\.`、`^## 0\.`、`4AQ\.9|零代码`、`^# 性能与架构改造计划`、`keep_alive`、`lane`、`think|ollama-native|/api/chat`、`stream_mode|astream|\.stream\(`、`compress_messages|input_budget_tokens`、`usage|model_token_counts|prompt_tokens=`、`cached_tokens`、`first_token_at`、`score_type`、`首屏`、`role.*system`、`CREATE TABLE`、`CONTEXT_HISTORY_RESERVE_TOKENS`、`gated: needs lane labels`、`hitl|requires_approval|correctness`、`待真机样本`、`compress_messages`
- `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe` 跑 `%TEMP%` 里的三枚只读脚本：`lfdump.py`（按 LF 口径打印区间）、行尾普查（`CR/LF/CRLF/\r\r\n` 计数）、`mk_f.py`（`subprocess` 调 git 生成 §F）——三者均不落盘到仓库
