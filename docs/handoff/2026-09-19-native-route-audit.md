# R101 · native 链路为什么在生产用不上（只读调查 · 2026-09-20 · 基线 `3c63658`）

**结论**：native 客户端真实存在，但被 R92 明确圈死在「非流式改写」这一半上；答题腿走 compat 是**双重既有裁定**（R92 划定边界 + R29 排队未放行），不是遗漏，也不是 `deploy/.env.server:7` 那行 URL 决定的——把 `/v1` 删掉照样是 compat。建议 **D14甲 窗口按 A 开（留 compat，时长按 3–4 小时排）**，B（切 native）＝复活 R29，代价是三处「真会坏」加一枚质量前置。

行号口径：全部 `path:line` 以 `\n` 切分（rg / 编辑器一致）。注意 `docs/handoff/2026-09-15-backend-followup-requests.md` 的粘贴证据块含 1363 个裸 `\r`，PowerShell `Get-Content` 会多算同样的行数 ⇒ 引用该文件时**同时给 §号**。

## 1. native 客户端到底存在吗——存在，且只有一处日志出处

- 实现齐备：`app/common/model_handler.py:41` 端点常量、`app/common/model_handler.py:54` 传输名、`app/common/model_handler.py:311` 请求构造、`app/common/model_handler.py:293` 真发 HTTP 的唯一缝 `_native_chat_request`。请求体三件套就是 §42 的有效拼法：`app/common/model_handler.py:327`（`"stream": False`）、`app/common/model_handler.py:328`（顶层 `think:false`）、`app/common/model_handler.py:326`（`options.num_predict` 沿用档位预算）。
- 那行日志的唯一出处：`app/common/model_handler.py:364`。全仓 `rg "应答" app` **恰 1 命中**，兼容腿根本不打「应答」行——所以任何 `[Model] ollama-native 应答` 都必然出自 native 腿，不需要猜。
- 唯一的闸门是**流式与否**，不是模型、不是配置：`app/common/model_handler.py:435` 的 `if not stream:` 之内才调 `app/common/model_handler.py:442`，拿到 `None` 才回落兼容腿（`app/common/model_handler.py:448`）。`stream=True` 连尝试都不会尝试。
- 生产上能打 `stream=False` 的调用者只有两枚，都是改写：`app/rag/retrieval_pipeline.py:214`（`QueryRewriter.rewrite`，`/api/v1/ask` 主链）与 `app/api/v1/chat.py:704`（legacy SSE 的改写段）。
- 由此可判定档位：`app/common/model_handler.py:243` 把非流式一律钉成 `REWRITE`，而 `app/common/model_budget.py:183` 的 REWRITE 上限是 256 tok。**所以 21:21:36 那行 `4.08 s / eval_count=115` 是一发查询改写，不是答题**（`115 <= 256` 自洽；那两发真正的 analysis 调用当时是在 `nodes.py` 的 compat 腿上烧满 120 s 撞死的）。
- 🔴 **订正跟进单 §41.2**（`docs/handoff/2026-09-15-backend-followup-requests.md:1401`，rg 口径 / §41.2 第三条实证）：那条写「模型侧 4 秒就能**答**完」——按上行号它出自 native 腿，而 native 腿在现网只能被改写触发，所以它量的是改写 JSON。同行号下的 (c) 候选因（`:1404`）也是拿改写与答案对比得来的。**这不推翻 §42 的八变体表**（那是同 prompt 直调两端，结论成立），只说明 §41.2 当初那两条证据不可比。
- 排除三个猜测来源：模型发现走 `/api/tags`（`app/common/model_capabilities.py:90`、`app/common/monitoring.py:326`），embedding 走 `/api/embeddings`（`app/rag/retriever.py:252`），启动预热只热 BM25 与 Cross-Encoder（`app/rag/retrieval_pipeline.py:571`）——**没有一处预热会打 `/api/chat`**。

## 2. 为什么生产答题走 compat——是裁定，而且不是那行 URL 决定的

- 全仓唯一一处「像路由」的判断其实只是日志标签：`app/agents/nodes.py:548` 的 `provider = "ollama" if ":11434" in settings.base_url else "local-openai-compatible"`。它只喂给 span 的 `provider` 字段（`app/agents/nodes.py:562` → `app/agents/nodes.py:237`），**不改变请求形态**。
- 真正决定腿的是客户端类别：`app/agents/nodes.py:551` 构造 `ChatOpenAI(base_url=settings.base_url, ...)`。OpenAI SDK 只会打 `/v1/chat/completions`，所以答案腿的传输在**类型层面**就已经定了。
- 环境文件不是闸门：`app/common/model_config.py:138` 无条件补 `/v1`（`get_local_model_settings` 的 docstring 自己写着 "the internal **OpenAI-compatible** endpoint"）。⇒ `deploy/.env.server:7` 那个 `/v1` 是**冗余的**，删掉仍然是 compat；而 native URL 是从 base_url 反推出来的（`app/common/model_handler.py:261`）。**「改 env 把答题切到 native」这条路不存在。**
- 是一次显式裁定，不是历史遗留：R92（跟进单 §36.2 = `docs/handoff/2026-09-15-backend-followup-requests.md:1292`）的实现提交 `e84ad84` 在 message 里逐字写了「`stream=True` 遗留答案口逐字节不变」，并被两枚测试钉住：`tests/test_r92_rewrite_thinking.py:243`（用例名 `test_streaming_call_never_touches_the_native_leg`）与 `tests/test_r92_rewrite_thinking.py:259`（断言串「stream=True 不许尝试原生腿」）。
- 更关键：**「把答案腿迁到 native」早就立过单，单号 R29。** 计划书 `docs/handoff/2026-09-17-perf-architecture-plan.md:141` 已把它重定义为「迁原生 `/api/chat` 或做 `PARAMETER think false` 派生模型」，并当场写明代价＝`tool_calls` 报文重做 + **必须先有质量基线**，「不许当快赢卖」；依赖链 `docs/handoff/2026-09-17-perf-architecture-plan.md:314` 是硬规矩 `R36 → R29 / R33 / R35`；风险条款 `docs/handoff/2026-09-17-perf-architecture-plan.md:317` 规定它会**改变答案内容**，必须与 R36 同批改同批验。现状：`docs/handoff/2026-09-15-orchestration-board.md:2755` 记着 R29 因 `orchestrator.py` 归 R98 独占而按住。
- 一句话回答本问：**compat 是有据的中间态，且它的放行条件已经写好了**——不需要新裁定，需要的是让 R36 先出基线。

## 3. 把 analysis 档切到 native 会破坏什么——逐条判定

| 不变量 | 判定 | 证据 |
|---|---|---|
| 工具调用 | **真会坏** | `app/agents/orchestrator.py:259` supervisor 的 `_make_model(ModelTier.ANALYSIS).bind_tools([dispatch])`；`app/agents/orchestrator.py:212`–`app/agents/orchestrator.py:215` 四张 ReAct 子图全部吃 analysis 档；`app/agents/nodes.py:210` 的 `bind_tools` 整段委托给 ChatOpenAI；判定工具轮靠 LangChain 形态（`app/common/model_budget.py:857`–`app/common/model_budget.py:864`）。而 `app/common/model_handler.py` 全文**零** `tool` 字样 ⇒ native 腿今天不支持工具 |
| 流式首字与 `mark_first_token` | **真会坏** | native 腿写死 `app/common/model_handler.py:327`；首字打点在流式循环里（`app/agents/nodes.py:456`），非流式没有首字可言。计时口径也一起变：夹取逻辑对流式刻意免算（`app/common/model_budget.py:645`，依据 `app/agents/contracts.py:98` 的 stall 口径）⇒ 换成非流式 native 等于把「夹答案不夹钟」从 chunk 间 stall 换成整答墙钟 |
| `prompt_tokens`/`eval_count` 与计费口径 | **真会坏（可补）** | 答案 span 的 token 只从 LangChain `usage_metadata`/`usage` 读（`app/trace/spans.py:255`），经 `app/agents/nodes.py:373` 落库到 `app/trace/store.py:271`、`app/storage/persistence.py:408`。native 的 `eval_count` 只进 `ModelReply.output_tokens`（`app/common/model_handler.py:110`），而该属性**全仓零读取** ⇒ 直接换腿则两列变 NULL。好消息：`app/common/model_budget.py:456` 已经同时认 `done_reason`，截断检测不用重造 |
| `keep_alive`（R34 常驻） | **不会坏，反而补一条旧账** | `docs/handoff/2026-09-19-r34-keep-alive-residency.md:56`–`docs/handoff/2026-09-19-r34-keep-alive-residency.md:61` 实测 `/v1` **忽略**该字段（UNTIL 299.3 s），`:149` 明写「答案腿缩短窗口」留给 R29 解；native 腿会发（`app/common/model_handler.py:329`）。另查一条现状：`app/agents/nodes.py` 全文零 `keep_alive` ⇒ `deploy/.env.server:50` 的 `15m` **目前只在改写腿生效** |
| R51 观测点 | **不会坏（但要放行改测试）** | 段归属按 tier 不按腿（`app/common/stage_timing.py:59` analysis→generate、`app/common/stage_timing.py:57` rewrite→rewrite），换腿不改归属；provider 标签来自 `app/agents/nodes.py:548` 的字符串。阻力只有一处自禁：`tests/test_r51_stage_latency.py:632` 写着本单不得改 `model_handler.py` |
| R98/R99 预算与 span 记账 | **不会坏** | 并发槽在模型客户端之外（`app/agents/nodes.py:305` 取、`app/agents/nodes.py:372` 还），native 腿同样成对释放（`app/common/model_handler.py:442`–`app/common/model_handler.py:448`）；R99 的空正文守卫读的是**可见字符数**（`app/agents/nodes.py:502`），换腿仍然咬——不会给「未获授权把空正文算成功」开门 |
| embedding 链 | **不会坏** | 独立端点 `app/rag/retriever.py:252`，不经任何 chat 腿；R90a 的 GUC 下发与传输无关 |
| AGENTS.md「只管理本机 Ollama」/「远程回退默认关闭」 | **不会坏** | native URL 由已配置的 base_url 剥 `/v1` 得来（`app/common/model_handler.py:261`–`app/common/model_handler.py:276`），非 `OpenAI` 客户端一律返回空串（＝不给自己发明第二条出口）；全仓无任何 `REMOTE_*` 回退代码（grep 零命中）。切 native **不新增外呼面** |
| 依赖面 | **未知→需补单** | 实取 venv：无 `langchain_ollama`，`langchain_community/chat_models/ollama.py` 不存在；`pyproject.toml:27` 的 `ollama` SDK 全仓零 import ⇒ 要么加依赖，要么在 httpx 上手写 NDJSON 流式读 |
| 既有测试钉 | **真会坏（三枚，须逐条改判）** | `tests/test_r92_rewrite_thinking.py:243`/`:259`（流式禁走 native）、`tests/test_r34_keep_alive_residency.py:201`（兼容腿请求字段全集 `{model,messages,stream,max_tokens,timeout,extra_body}`）、`tests/test_private_model_routing.py:85`（断言 `root_client.base_url` 以 `/v1/` 结尾） |

- 文档漂移顺手记一条：`app/common/model_budget.py:207` 仍写着候选因 (c)「NOT SUPPORTED / 两端在同一量级」，而 §42 结论 2 已推翻「compat 更慢不成立」。两者其实不矛盾——(c) 的对照**双方都在生成思考链**——但代码注释少了这个限定，下一班读到会再猜一次。

## 4. 建议：本窗口选 A（留在 compat）

- **A 的内容**：答题腿不动，等 R100 给 compat 加 `thinking:{type:"disabled"}`（§42 里现网链路唯一能出正文的拼法，#6）。**前提：R100 尚未落地**——`rg MODEL_THINKING app` 零命中，本文基线上这一发还发不出去。
- **A 的代价（如实登记）**：单题 ≈ 75–112 s（#6 的 37.3 s × 每题 2~3 发 analysis）＋ 一发改写 ⇒ **105 题按 3–4 小时排**，与 §42 自估的 2–4 h 同区间；`clamped=yes` 的噪声仍在（CPU 标定常数与 120 s 天花板仍矛盾，(a) 未结），但它不咬流式腿。**跑分窗口的时长是 A 的唯一实际代价。**
- **B 的内容与代价**：需要改 ① 一个会流式的 native chat model（自建或加 `langchain-ollama`）② `tool_calls`/`tool_call_chunks` 双向映射 ③ `eval_count`→span token 映射 ④ 答案腿下发 `keep_alive` ⑤ 解掉 §3 表末那三枚钉 ⑥ 复验权限与超时语义（`docs/handoff/2026-09-17-perf-architecture-plan.md:320` 点名）。收益是 §42 #2 的 1.9 s/发 ⇒ 窗口 <20 min。
- **为什么本窗口不选 B**：B 的硬前置 R36（≥100 条质量基线）**正是这个窗口要产出的东西**。先切 B 再跑基线＝拿一条已经改变答案内容的链路给自己发合格证，那是 `docs/handoff/2026-09-17-perf-architecture-plan.md:317` 明令禁止的顺序；而且 `orchestrator.py` 此刻归 R98 独占，B 无处落笔。**慢可以接受，先有基线再谈换腿。**

## 5. 总控需要据此做的决定

1. **改窗口时长登记**：runbook 的 `105 × 41.6 s ≈ 73 min` 与 §14 的单题 262.3 s 都作废，D14甲 按 **3–4 小时**开（留 4 h 余量）。这是 A 的全部代价，别让下一班再估一次。
2. **确认 A 的放行顺序**：D14甲 前置 R100（本文基线上它还不存在）。R100 判据 2 的重标定必须**同时产出两行**——compat + `thinking:disabled`（#6：1328 tok / 37.3 s）与 native + 顶层 `think:false`（#2：46 tok / 1.9 s），否则地板仍会按「思考开着」时代测出的 1537 定。
3. **裁定文档漂移**：`app/common/model_budget.py:207`–`app/common/model_budget.py:210` 的 (c) 那句要不要补「仅指双方都在生成思考链时」的同批限定。它落在 R100 写域（`model_budget.py`）内，可并单，也可另立一行注释小单。
4. **订正 §41.2**：把 `:1401` 的「模型侧 4 秒就能答完」改判为「4 秒是一发改写」，并给 `:1404` 的候选因 (c) 加一句「其证据不可比」。§42 的八变体表不受影响。
5. **确认 R29 未被本文改判**：native 答案腿 = R29，放行条件仍是「R36 基线 + `orchestrator.py` 空出来」。若业主希望为了跑分窗口跳过质量前置，那是推翻风险条款 1，需要业主点头，不在总控与本单权限内。
6. **给 R34 补一条未结账**：答案腿从未下发 `keep_alive`（本文实测 `app/agents/nodes.py` 零命中），所以 `LOCAL_MODEL_KEEP_ALIVE` 现在只有改写腿吃到——这条该挂在 R29/后续单上，**不要记在 R34 已完成**。
7. **写域备案**：本文只引用未修改 `app/agents/nodes.py`、`app/common/model_budget.py`、`app/agents/orchestrator.py`（R99 在途 / R98 在途 / R100 独占候选）；名册上无人与本单的读取面冲突。