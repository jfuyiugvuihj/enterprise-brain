# R118 · 子图 checkpointer 定策纸（只读单，不施工）

> **口径声明（本纸开头第一行 required）**：本纸引用的跟进单 / 计划书 / 解锁图 / 看板行号一律按 **LF 口径**数（`2026-09-15-backend-followup-requests.md` 内有 **1364 处 `\r\r\n`**，PowerShell `Select-String` 会数出完全不同的行数）。本纸所有 commit subject / 含 `|` 的 git format 一律走 **python subprocess 参数列表**，无一枚经 PowerShell 字符串（看板 §4BH.12 五 / 跟进单 §62 一 L1868 立的规矩）。

**工单事实**

- 工单 R118（只读定策单）· 工作树 `C:\Users\fengx\PycharmProjects\be-r118` · 分支 `codex/be-r118` · HEAD `7736302`
- 立案原文 跟进单 §55 **L1729-1731**；解锁图 `docs/handoff/2026-09-20-unblock-map.md` **§G L401**（"未被推翻；R117 结案使它从等 R117 变可定策"）
- 真实共占按跟进单 §62 一 **L1867** 的更正账：`app/agents/orchestrator.py` = **R33 + R118（+ R31 视方案）**。前任那句"R30/R31/R33/R42/R38 五单共占"是假冲突，本纸不据此立冲突。
- 前置已成立：R117 并树 `f29a020`（计划书 §5.2 追登表 **L311**）⇒ §55 L1731"排 R117 结案之后再定"到期。
- 本单**不施工**：`app/**`、`tests/**` 全程只读；唯一新建文件 = 本纸。基线两值 2759 passed / 35 skipped（看板 §4BH.11 **L3046**）未由本单跑（`be-r116`/`be-r125` 两枚 Agent 在兄弟树施工，全量会互相踩）。

---

## 0. 结论

**推荐乙案**（显式承认知情失忆 + 把注释与文档改对），并把它切成两步：**乙-1** 零风险改注释/文档/契约一句话，**乙-2** 撤掉四腿那份"只写不读"的 checkpointer 并补回收。

三条理由，每条都有本机实测凭据，不靠文档转述：

1. **甲案的收益是零**：真机评测道**结构上不存在跨轮**（采集器一题一个新 `session_id`），所以修好 resume 在 run3→run4→run5 这类跑分上**一分都不会动**（§3 量给你看）。收益为零的选项不该付"重开 R117 + 涨回 room 压力"的代价。
2. **甲案的代价是可算的**：run5 实测单发满装 `packed_tokens` 中位 **1254** ⇒ 若子图真 resume，第 3 轮光旧检索串就 **2508 枚 = 整条 input budget 2560 的 0.98 倍**（§2 表）。这不是"再优化一下"的量级，是撞墙。
3. **乙案还倒吐预算**：`CONTEXT_HISTORY_RESERVE_TOKENS=322`（`app/rag/retrieval_pipeline.py:591`）预留的正是"最多两轮同会话历史的问答文字"（同文件 `:571-572`、`:584-586`），而它要兜的东西**证明不会出现在 prompt 里** ⇒ 这 322 枚 = 当前 room 1606 的 **20.1%**。数归 R119 定，本纸只指出"乙案使 R119 有 322 枚可谈"。

---

## 1. 判据 1 · 事实钉死（源码行号 + 探针，不照抄文档）

### 1-1 装配形状

- `app/agents/orchestrator.py:198` `_checkpointer = _make_checkpointer()`：模块导入期就建。run5 日志亲证生产态是 **`[Orchestrator] 使用 PostgresSaver 持久化`**（`%TEMP%\evalrun\backend-run5.log` 21:17:56；该日志是 **UTF-16 LE**，按 utf-8 读会得到完全不同的结果）。
- `:212-215` 四张子图 `create_react_agent(_make_model(ModelTier.ANALYSIS), [...], prompt=DOC/DATA/CHART/EXPORT_PROMPT, checkpointer=_checkpointer)` —— **`checkpointer=` 确实传了**，传的是与父图同一枚对象。
- `:882-885` `_builder.add_node("doc", _make_worker_wrapper(doc_graph, "doc"))`（data/chart/export 同形）。
- **线程身份从哪来**：`:551` `parent = parent_conf.get("thread_id", "default")` → `:557` `child_conf = {"thread_id": f"{parent}:{name}"}`。这是**确定性**拼接 ⇒ 同一会话内**跨轮恒定**。父 `thread_id` 来自 `app/api/v1/chat.py:1103` `thread_id = request.session_id or uuid.uuid4().hex` ⇒ **前端带 session_id 就稳定，不带就每请求新**（生产道稳定；评测道每问一新，见 §3-1）。
- **每轮到底送什么进去**：`:580-587` 从父 state 挑**最后一条** `HumanMessage` → `:607` `graph.invoke({"messages": [user_msg]}, config=child_cfg)`。
- `:559-573` 那份透传清单（username/role/department/data_filename/principal/request_id/trace_id/task_id/cancel_event）+ `:574-577`（worker/evidence_bag/step_id）里**没有 `checkpoint_ns`**。

⇒ 🔴 **第一处更正：失忆不是因为"生产路径上 thread_id 每轮变"。** thread_id 恒定，读不回来另有真凶。

### 1-2 真凶 = langgraph 给嵌套 invoke 注入的 `checkpoint_ns` 逐轮换 uuid（本机探针实测）

探针：`%TEMP%\r118_probe\probe_keys.py` / `probe_solo.py` / `probe_shapes.py`。零模型（子图模型换成假 echo）、零容器、不碰仓、**不 import `orchestrator`**（`:198` 在导入期就会连 PG 并可能跑 `setup()` 迁移，那是改数据）。子图用**真 `create_react_agent` + 真 `DOC_PROMPT`**（实测 62 枚 token），只复刻 wrapper 的 config 形状。langgraph 1.2.5 / langgraph-checkpoint 4.1.1 / langchain-core 1.4.7。

| 形状 | 子图每轮进模型的 prompt 条数 | 结论 |
|---|---|---|
| 生产形状（父节点内手工 invoke，父线程恒定，3 轮） | **2 / 2 / 2**（= `[SystemMessage, HumanMessage]`） | 失忆 |
| 同一枚子图**脱离父图单跑** 4 轮 | **2 / 4 / 6 / 8** | checkpointer + 稳定 thread_id **本身完全可用** |
| 生产形状 + 子图换独立 saver | 2 / 2 / 2 | 不解决 |
| 生产形状 + 显式 `child_conf["checkpoint_ns"]=""` | 2 / 2 / 2 | 🔴 **不解决**（写入位置确实挪到根 ns，`get_state_history` 从 0 条变 9 条，但**回读仍然不发生**） |
| 子图直接作节点 `add_node("doc", child_graph)` | **2 / 4 / 6 / 8** | 真 resume |
| wrapper 内 invoke 前 `var_child_runnable_config.set(None)` | **2 / 4 / 6 / 8** | 真 resume |

存储层的直接证据：生产形状跑完后 `MemorySaver.storage` 里子线程 `sess:doc` 下的 ns 是 `doc:c13ce76c…` / `doc:82918e67…` / `doc:24bc0859…` —— **每轮一枚新 uuid**，父任务 id 注进来的。`.venv/Lib/site-packages/langgraph/checkpoint/postgres/base.py:55` 的 `PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)` 说明这件事与 saver 无关：**测试态 MemorySaver 与生产态 PostgresSaver 同一个键**，结论两态同形。

⇒ ✅ **§55 的定性成立**：`orchestrator.py:201` 那句"带 checkpointer，可持久化"**与事实不符**。
⇒ 🔴 **第二处更正：不是"形同虚设"，是"只写不读"。** 写入真发生了，而且写进的是 PG。

### 1-3 是否"只有某一腿失效"

否。doc/data/chart/export 四腿在 `:212-215` 同形建立、`:607` 同形调用 ⇒ **四条一起失效**。第五枚 worker `approval`（`:729-743`）**不是子图**，它直接调 `_get_pipeline().search_for_principal`（`:791-795`），与本单无关 —— §55 那句"doc/data 腿"该扩成"四腿"，并应把 approval 明确排除，免得下一班去修一枚不存在的东西。

### 1-4 比 §55 说得更狠的一处：父层那句【doc Agent 返回】也没进过任何模型

§55 L1731 的原话是"跨轮记忆只剩父层那句【doc Agent 返回】"。实测**那句也只落 state、不进 prompt**：

- `:646` worker 节点返回 `AIMessage(content=f"【{name} Agent 返回】\n{answer}")`，靠 `app/agents/state.py:31` 的 `add_messages` 进父 state，且 `:920-926` 每轮只 reset `worker_results`/`agent_results`，**不 reset `messages`** ⇒ 父线程的消息**确实跨轮累积**（探针里父 `messages` 1/3/5/7）。
- 但 `main_agent_node` 在 `:397` 只送 `main_model.invoke([sys_msg, current_user_msg])`；`:362-379` 算出来的 `filtered`（本意是"挑哪些历史进 prompt"）**建了 5 行、全仓零读取 = 死代码**；`:342` 那发 `ModelTier.COMPRESS` 的返回值只被 `:354-358` 拿去挑最后一条 HumanMessage。R27 的注释在 `:286-288` 自己就写着"worker 结果一个字都不进上下文"。
- `nodes.py:991-1009` `synthesize` 取的是 `worker_results`（本轮的），不是历史消息。

⇒ **真正的跨轮通道只有两条**：① `chat.py:687-745` `_rewrite_followup`（**改写问题**，不喂料）；② `nodes.py:854-879` `load_memory` → `recall(user_id, q, k=3)`，经 `:348-352` 拼成【用户历史记忆】进 `sys_msg`（按 **user** 记，不按会话记）。**"子图 resume 不 resume"根本不在关键路径上** —— 这才是本单给总控的最重要一句事实。

---

## 2. 判据 2 · 两案成本与收益

### 2-1 留档核账（先做的，结论：字节零漂移，但语义前提不成立）

| 文件 | 登记值（跟进单 §55 L1720） | 本机实测 | 判定 |
|---|---|---|---|
| `%TEMP%\r114_probe\r114_orchestrator.patch` | 12 680 B / `5b19838a…` | **12 680 B / `5b19838ab8597dd891e0c4aed1357f8cf0ffd14ca6dd8a1828f16488e6c4f386`** | ✅ 对得上 |
| `kept_test_r114_history_tool_pruning.py` / `r114_tests_preserved.py` | 20 169 B / `4f63f495…` | 两枚**同字节** 20 169 B / 同哈希 `4f63f49522a58bcd88db783f4988979cc719a6d8d738ea4914efe71b6f5842c3` | ✅ 对得上（两枚互为副本） |
| `git apply --check`（**只 check，未 apply 到任何树**） | 登记"通过" | 在 HEAD `7736302` 上 **exit 0**，stderr 仅 `Checking patch app/agents/orchestrator.py...` | ✅ 无 apply 期漂移 |

**但"能干净落地"不等于"续用"** —— 这是本纸对 §55 那句"若 R118 认定子图应当 resume 则上面那两份留档的 patch/用例续用"的更正：

- patch 只做一件事：把四腿的 `prompt=<str>` 换成 `prompt=_make_worker_prompt(<str>)`，在**组装点**裁掉"已被后续轮次覆盖的 `ToolMessage` 正文"（`AGED_TOOL_ROOM_SHARE=0.5`，room 只问 `context_pack_room()`，读不到就一个字不裁）。它**不含任何形状修正**。
- 11 枚用例的符号依赖（本机静态分类）：**10 枚需要 patch 的新符号**（`_make_worker_prompt` / `_aged_tool_boundary` / `_trim_aged_tool_bodies` / `AGED_TOOL_STUB_MARKER`），只有 `test_pruning_site_carries_no_copied_window_numbers`（L397）patch-free。
- 登记态 6 passed / 5 failed 的成因也对得上：那 5 枚的前提是"**上一轮的检索串这一轮还在历史里**"，而 §1-2 证明它**永远不在** ⇒ 只 apply patch 不修形状，那 5 枚**照旧红**，且红得合情合理。
- 🔴 结论：**甲案 = 形状修正（留档里没有）+ patch 续用（可用）+ 11 枚用例续用（可用，其中 5 枚要等形状修完才转绿）**。三件缺一不可，别把"`apply --check` 通过"读成"甲案已经做完一半"。

### 2-2 甲案（修装配让子图真 resume）

**形状只能选两种**（§1-2 表里只有它们转 RESUMES）：

- **shape 1：子图直接当节点**（`add_node("doc", doc_graph)`）。**代价最大**：`_make_worker_wrapper` 里那些东西会整体失去落点 —— `:556/:575` evidence_bag、`:591-605` 与 `:633-642` 两枚 `step.started`/`step.finished` trace、`:550/:617` 取消检查点 2/3、`:621-631` `build_agent_result`/`summarize_agent_result`、`:643-647` 的 `worker_results` 契约。这些各有既有用例（`tests/test_agent_result_records.py:35/:56`、`tests/test_cancellation_epoch.py:137`、`tests/test_r37_report_lane_worker.py:104`）⇒ **等于重写一层壳**。
- **shape 2：wrapper 内 invoke 前清掉继承的父 config**（`var_child_runnable_config.set(None)`，前后配 `reset` 防泄漏）。**形状改动小得多**，壳与账全部原地不动。但它是一把**私有 contextvar 的手术**（`langgraph.config` 内部名，无兼容承诺），且要新增"不得泄漏到兄弟任务"的用例。
- 🔴 两者都要**新增**一枚"子图本轮 prompt == [system, 本轮问题]"或"== 跨轮累积"的断言 —— 今天没有任何用例看得见这件事（见 §4-3 反证一）。

**甲案的量化代价**（run5 实测尺：单发满装 `fitted=5` 共 41 发，`packed_tokens` 中位 **1254**、p90 1498、max 1595）：

| 轮次 | 若 resume，历史旧检索串 | 占 room 1606 | 占 input budget 2560 |
|---|---|---|---|
| 第 2 轮 | 1254 | 0.78× | 0.49× |
| 第 3 轮 | 2508 | **1.56×** | **0.98×** |
| 第 4 轮 | 3762 | 2.34× | 1.47× |

`2560 = context_limit_tokens(4096) − max_tokens(1536)`（`app/agents/contracts.py:157-159`）；实测 `context_pack_capacity()=2560`、`context_pack_room()=1606 = 2560−632−322`。问答文字另计（R119 口径每轮 403-429）。⇒ **第 3 起就是"要么撞 `context_limit_exceeded` 当场拒答、要么靠 R114 的裁剪把上一轮的关键数字删掉"**。§55A 那 28 枚 `room_left=0 → fitted=0, dropped=5` 与 run5 那 17 枚 `stub=refused`（doc 12 + data 5，本机复算一致）都说：残料本来就紧张，甲案是往火上添柴。

**甲案还会反开 R117**：R117 判据 a 立的是"**跨轮不得扣房**"，理由白纸黑字写在 `app/agents/tools.py:396-398` 与 `app/rag/retrieval_pipeline.py:587-589`——"子图每轮冷启动，上一轮检索串这一轮不在 prompt 里"。甲案把这句话的前提**推翻**，那两处注释与 `_pack_ledger_key`（`tools.py:451`）的口径必须改回跨轮账，否则装箱与 prompt 真相不一致（这次是**少扣**，即撞墙）。🔴 注意形状：`test_four_rounds_in_one_thread_keep_the_first_round_room_balance`（`tests/test_r117_ledger_turn_scoped.py:190`）在甲案下**仍会绿**（它量装箱账，不量 prompt 体积），所以它**挡不住**这次回退 —— 必须写进施工单。

**甲案的收益**：真实客户多轮会话里，doc 腿能自己记得上一轮检索到的原文（追问"那第二条呢"不必重检）。这条收益**今天无法用任何分数证明**（§3），只能靠新评测道量。

### 2-3 乙案（承认知情失忆 + 把注释与文档改对）

**代价**：产品上**什么都不变**，客户多轮追问继续每次重新检索（今天的真实行为，也是 run3/4/5 已被验收的行为）。丢的是"以后想省一次检索"这条路。

**乙-1 清单（零生产代码）**：`orchestrator.py:201` 注释（那句"带 checkpointer，可持久化"）、`:557` 旁补一句"子线程号稳定但 `checkpoint_ns` 逐轮换 ⇒ 跨轮不回读"。`retrieval_pipeline.py:584-591` 与 `tools.py:396-398` 两处注释**已经是乙案口径**（R117 落的），只需 R119 再校数。

**乙-2 清单（生产代码，建议单独批）**：撤 `:212-215` 的 `checkpointer=_checkpointer`，让四腿"无 checkpointer"与事实一致，并停止往 PG 写永不回读的子线程 checkpoint。**先确认三件事**：① 全仓没有一枚用例断言子图带 checkpointer（`git grep -n checkpoint_ns -- tests` = **0 命中**，本机实测）；② `scripts/perf_probe_rounds.py:16` 的 `doc_react_1` 探针量的是 `create_react_agent(doc_graph)` —— 那是 **R116 在写的文件**，乙-2 要与 R116 错开；③ `clear_session`（`:1352-1361`）只对父线程 `put` 一枚空 checkpoint，删会话（`chat.py:2038-2047`）不回收 `<sid>:doc` 这些子线程 ⇒ 撤之前先回答"已落库的旧子线程行怎么清"。

**用例/契约要跟着改的**：既有用例**一枚都不必改**（没有一枚看得见这件事）；新增 1 枚形状钉（子图本轮 prompt == [system, 本轮问题]）+ 修 `tests/test_r109_rewrite_offline_guard.py:78-85` 那枚 autouse fixture（§4-3 反证二）。

**`docs/api/contract-v1.md` 要不要加一句：要。** 本机实测该文件对"多轮 / 记忆"**0 命中**（只有 `session_id` 的归属 / 取消 / HITL 语义，L172 / L181 / L196 / L360-363 / L570-577），而 `AskRequest.session_id`（`chat.py:756`）是公开字段 ⇒ 集成方完全有理由假设"带 session_id 就会记得上文"。建议加一条**散文语义**（不动 schema、不 bump 版本）：会话内跨轮保证的是"**触发词命中的问题改写** + **按用户召回的长期记忆**"，**不保证**"worker 内部检索历史"；要追问细节请重述条件。这条也正是乙案的诚实本体。

---

## 3. 判据 3 · 拿真机分数量"失忆能不能解释 0.4167 钉死"

**能给出结论：不能解释 —— 因为这套评测里根本不存在"跨轮"。** 四步，全部本机自量。

### 3-1 采集器每题一个新线程（结构性）

`scripts/eval_transport_ask_v2.py:184` —— `out = _stream_once(str(row["question"]), uuid.uuid4().hex, uuid.uuid4().hex)`，第 2 个实参就是 `session_id`（`:107` 签名、`:110` payload）。⇒ **105 题 = 105 个线程 = 105 个全新 `thread_id`**，§55A L1744 那句"采集器每问一个新 thread"在代码里就是这么写的。父线程新 ⇒ `<sid>:doc` 也新 ⇒ **无论子图 resume 与否，"第二轮"都不存在**。修 resume 在这套评测上是**恒零效应**的改动。

### 3-2 判分复算：三枚官方数我逐字复现了

按 `app/quality/eval.py:60-66`（`_is_correct`）+ `:100-115`（分桶）的口径，拿 `answers-run{3,4,5}.jsonl`（`%TEMP%\evalrun\`）对 `tests/fixtures/business_evaluation_100.jsonl` 重算：overall **0.4571 / 0.4571 / 0.4762**，多轮对话 **5/12 = 0.4167（三枚一致）**，与三份 report 的 `category_metrics` 逐字相同（文档问答 0.6842/0.6316/0.6842、报告生成 0.3333 全对上）⇒ 下面这张表可信。

### 3-3 "钉死"本身是两枚翻面互相抵消，不是同一批题稳定

逐题矩阵（1=过）：

| id | r3 | r4 | r5 | `must_contain` |
|---|---|---|---|---|
| chat-01 我昨晚住了650元，能报多少？ | 1 | 1 | 1 | 500元, 审批 |
| **chat-02 那财务是在部门负责人之前还是之后？** | **1** | **0** | **1** | 之后, 财务 |
| chat-03 把刚才的结论说得更简单一点 | 0 | 0 | 0 | 500元 |
| chat-04 如果换成出差申请呢？ | 1 | 1 | 1 | 申请 |
| **chat-05 请给我一个管理层能看懂的总结** | **0** | **1** | **0** | 审批 |
| chat-06 那市内交通有单日上限吗？ | 0 | 0 | 0 | 200元 |
| chat-07 换成国际出差呢？ | 1 | 1 | 1 | 总经理 |
| chat-08 两个人合住一间，标准可以叠加吗？ | 0 | 0 | 0 | 不叠加 |
| chat-09 这和你前面说的矛盾吗？ | 0 | 0 | 0 | 不矛盾 |
| chat-10 只给我结论，不要引用条款 | 0 | 0 | 0 | 部门负责人 |
| chat-11 把金额换成800元再算一遍 | 1 | 1 | 1 | 800元, 审批 |
| chat-12 这个标准去年是多少？ | 0 | 0 | 0 | 无法确认 |

通过的**集合**在 r4 换过一次人（chat-02 出、chat-05 进），0.4167 只是**恰好抵消**。六枚永久 0（chat-03/06/08/09/10/12）的 `must_contain` 是"不叠加 / 不矛盾 / 无法确认 / 部门负责人 / 500元 / 200元"这一类**语料查无出处**的断言词 ⇒ 正是跟进单 §24 L817 那"桶 C：出处概念不适用（多轮对话指代、行为断言类）16 条"的复发。

### 3-4 两枚翻面的成因都查到了，都不是子图记忆

`backend-run{3,4,5}.log`（run5 是 **UTF-16 LE**，`raw[:2]=b'\xff\xfe'`；run3/run4 是 UTF-8）里的 `[REWRITE]` 行，每份**各 5 条**：

```
run3 17:53:40  '那财务是在部门负责人之前还是之后？' → '您指的财务流程是在部门负责人之前还是之后？'                     ⇒ chat-02 PASS
run4 19:47:17  '那财务…？' → '您刚才询问了财务与部门负责人的先后顺序，这具体是指流程审批的先后，还是指岗位职级的高低？' ⇒ chat-02 FAIL（答的是"A 还是 B"，全文无"之后"）
run5 21:26:45  '那财务…？' → '您是指财务审批流程发生在部门负责人审批之前，还是之后？'                                   ⇒ chat-02 PASS
```

chat-02 的三面翻面**与改写产物逐字同形**。而改写腿之所以会编出"您刚才询问了…"这种并不存在的上文，根因在代码里：`chat.py:1116` 先 `_save_message(thread_id, "user", request.message)`，`:1125` 才 `_rewrite_followup(...)`，而 `:693` 取的是 `prev_user[-1]` —— **本会话最后一条 user 消息 = 刚存进去的当前问题**。⇒ 发给模型的模板（`:698-703`）永远是"上一问: X / 当前: X"，它只能靠想象补语境（run5 chat-12 那句"上一问中提到的那个标准"是同一件事；run5 chat-06 直接原样回吐，那题三轮全 0）。**这跟子图 checkpointer 无关，甲案一点也治不到它。**

chat-05（"请给我一个管理层能看懂的总结"，无触发词、不改写）：r3 答成经营数据、r4 答成"审批流程顺序=谁先签字"（**恰好是从同一 user 的上一题串过来的话题**）、r5 答成绩效考核。`must_contain=["审批"]` 在这里是一枚抽奖符。串题的通道也是实测的：run5 日志 `[LoadMemory] user=evalbot 召回 3 条` **105/105 全是 3 条**（`Counter({3: 105})`）⇒ 105 道互不相干的题共用同一个 evalbot 的长期记忆（`nodes.py:869 recall(user_id, q, k=3)`）。

### 3-5 所以答案

**量不出来，缺的 X 是一枚真正跨轮的评测道**：现在没有任何一份样本能区分甲/乙（结构上 105 个线程各 1 轮）。要验收 R118，得先建"**同一 `session_id` 连问 ≥3 轮 + 按轮判分**"的道（`_pace()` 每问 ≥15 s ⇒ 12 题 3 轮约 9 分钟，可塞进一扇窗的一角）。在此之前的任何 run，多轮对话分数对本案**零信息量**。附带一句硬话：**不许**把 0.4167 当甲案的验收判据，也不许把它当乙案已经"没退化"的证据。

---

## 4. 判据 4 · 推荐与落地前提

### 4-1 推荐

**乙案**，切两刀：**乙-1 立即做**（注释 + 契约一句话 + 1 枚形状钉），**乙-2 单独批**（撤四腿 checkpointer + PG 旧子线程回收口径）。甲案**关闭但留门**（§5）。

补一条 §55 没提的：**本案真正的产品缺陷不在子图，在改写腿。** `prev_user[-1]` 取到当前问（`chat.py:693` vs `:1116`）+ 触发词是 `startswith` 白名单（`:688-690`；12 枚多轮题只命中 4 枚：chat-02/06/07/12，本机实测）⇒ 它是**唯一**带"上文"字样的通道，却既可能不改、也可能改了造假语境。建议总控**另立一单**（写域 `app/api/v1/chat.py`，落解锁图 §B 簇 2，与 R31/R32/R48 同文件族 ⇒ 排在那三枚之前或之后独占），判据直接用 §3-4 那三行 `[REWRITE]` 原文。这单比甲案便宜得多，而它**今天正在掉分**。

### 4-2 若批准乙案，下一班的施工单长这样

- **写域**：`app/agents/orchestrator.py`（乙-1 只改 `:201` 与 `:557` 旁注释；乙-2 另改 `:212-215` 去掉 `checkpointer=`，并给 `clear_session` 一个子线程回收口径或写明"撤后不再产生"）、`docs/api/contract-v1.md`（新增一段散文语义，不动 schema / 不 bump 版本）、新 `tests/test_r118_subgraph_memory.py`。**不碰** `scripts/perf_probe_rounds.py`（R116 写域）。
- **判据**：① 形状钉 —— 真装配（`orchestrator._make_worker_wrapper` + 真 `create_react_agent` + 稳定 thread，形如 `tests/test_r117_ledger_turn_scoped.py:142-184`）连跑 3 轮，断言**子图每轮看到的 prompt == [system, 本轮问题]**（直接复用 `_nested_session` 已在收集、但今天没人断言的 `model.seen`，`tests/test_r117_ledger_turn_scoped.py:116`）。② 注释与事实同色 —— `:201` 改成"带 checkpointer，**仅本轮内**可持久化；跨轮不回读（`checkpoint_ns` 逐轮换）"，用例名或注释里必须指名 R118，防再被写回"可持久化"。③ 契约句存在且可读 —— 那一段要同时说清"保证什么 / 不保证什么"。④ 若批乙-2：断言四腿 `checkpointer is None`，并补一枚"同会话连问 3 轮，PG 侧不新增 `<sid>:<worker>` 子线程行"的**桩**用例（不许连真库）。⑤ 反证：把 `:201` 注释改回"可持久化" ⇒ ②当场红；给子图加回 `checkpointer=` ⇒ ④当场红。
- **必须仍绿**：`tests/test_r117_ledger_turn_scoped.py`（本单实测 passed）、`tests/test_r122_stub_honesty.py`、`tests/test_r112_prompt_packing.py`、`tests/test_agent_result_records.py`、`tests/test_cancellation_epoch.py`、`tests/test_r37_report_lane_worker.py`、`tests/test_r98_checkpointer_backend.py`（🔴 它管的是**父图**那条"不许谎报降级"，乙案不许顺手动 `:198` 的装配决策）、`tests/test_r109_rewrite_offline_guard.py`。全量两值以 **2759 / 35** 起算只增不减，既有断言一条不许弱化。
- **不许碰**：`app/rag/retrieval_pipeline.py`（322 那枚归 R119）、`app/agents/tools.py`（R117/R122 刚落）、`tests/fixtures/**`（改评测集 = 改分数定义）、`migrations/**`、`deploy/**`、`.env*`、`frontend/**`、`scripts/perf_probe_*`（R116 在写）。

### 4-3 两处具名反证（本纸的承重墙）

**反证一 —— "子图跨轮不回读"（§1-2 的核心断言）：没有现成用例能钉住它。** 凭据：`git grep -n checkpoint_ns -- tests` = **0 命中**；`_nested_session` 的假模型 `self.seen.append(list(messages))`（`tests/test_r117_ledger_turn_scoped.py:116`）把逐轮 prompt 记了下来，**但全文件没有一枚断言读 `model.seen`**。⇒ 这句话今天**完全靠注释活着**（`tools.py:396-398`、`retrieval_pipeline.py:587-589`）。把它摘掉，2759 枚用例**一枚都不会红** —— 这句话本身就是交付：**R118 的结论必须自带一枚新形状钉，否则下一班改装配时无人报警。**

**反证二 —— "`_rewrite_followup` 的『上一问』在生产路径上就是当前问题"（§3-4 的根因）：现有用例不但钉不住，还反向奖励它。** 凭据：`tests/test_r109_rewrite_offline_guard.py:78-85` 那枚 **autouse** fixture `one_turn_of_history` 把 `chat._get_session_messages` 直接换成 `lambda _session_id: [{"role": "user", "content": PREVIOUS_QUESTION}]`，docstring 自己写着"绕开 session 存储，不碰数据库"—— 而生产是 `chat.py:1116` 先存当前问、`:1125` 才读。⇒ 真路由上那个 `[-1]` 取值**永不被 exercised**；这 12 枚用例今天全绿（本单定向实测 r109 + r117 + r122 = **30 passed**）。更要紧的是：若有人把 `:693` 改成取真上一条（`[-2]`），这枚只含 **1 条**历史的 fixture 会当场 `IndexError` 打红一片 —— **现有套件在惩罚正确的修法**。这就是"该改 fixture，而不只是该改注释"的证据。

### 4-4 会不会与 R33 撞车 / 串行要不要改

- **会撞，但是"同文件串行"，不是"判据冲突"**：R33 的真身在 `orchestrator.py:50`（`from app.memory import compress_messages`）+ `:342`（那发 COMPRESS 模型调用）；R118乙 只碰 `:201`/`:557` 注释（乙-2 才碰 `:212-215`）——**行级零交集，文件级共占** ⇒ 按簇 1 规矩串行即可。别再引用"五单共占"那笔假账（§62 一 L1867 已更正）。
- **顺序建议**：解锁图 **§B 簇 1 L60** 的 `R118 → R33 → R31 → R43` 我**复核后照单接受**，理由与它写的一致但更硬一层："先定形状再定尺寸"（L61）。乙案把话说死后，R33 的裁剪面**从"历史"缩到"本轮检索料"**，而 §1-4 那两处死物（`:362-379` 的 `filtered` 死代码、`:342` COMPRESS 的唯一消费者只是"挑最后一条 HumanMessage"）让 R33 可以**删**而不是**改写** ⇒ R118 先结，R33 省事。解锁图 L105"R33 判据大半失效"与本纸结论同向。
- **建议插一枚**：`R118乙 → R119 → R33 → R31 → R43`。R119 的 `CONTEXT_HISTORY_RESERVE_TOKENS=322` 在校准前必须**先知道"历史到底进不进 prompt"**，那是 R118 一句话的产物；反过来（先校 322）会白校一次。R29 若复活仍按计划书 §8 **L372** 硬依赖链压在 R31 前。
- **与在途两枚的关系**：`be-r116`（`scripts/perf_probe_*`、装箱参数化）—— 乙-2 若撤 checkpointer 会改变 `perf_probe_rounds.py:16` 那个 `doc_react_1` 的形状 ⇒ **排 R116 结案之后再批乙-2**；`be-r125`（`scripts/rebuild_index.py`、pgvector §8.6）—— 零交集。

---

## 5. 反悔条款（出现下列新证据，本案必须重开）

1. **建了真跨轮评测道**（同 `session_id` ≥3 轮、按轮判分）且乙案口径下分数显著低于"resume 后"对照组 ⇒ 甲案立刻复活，且以 **shape 2**（清 `var_child_runnable_config`）起做；shape 1 要先过"壳重写"评估。
2. **langgraph 升级后 `checkpoint_ns` 不再逐轮换 uuid**（复跑 `%TEMP%\r118_probe\probe_keys.py`，看 `sess:doc` 下的 ns 是否恒定）⇒ §1 整段作废，注释与文档按"真 resume"重写，R117 的跨轮账口径同时反开。
3. **业主明确把"多轮追问省一次检索"写进对外承诺** ⇒ 产品级重开，届时 R114 那两份留档（哈希已验，§2-1）直接续用作裁剪半边。
4. **改写腿那单修好之后多轮对话分数动了**（尤其 chat-02/06/12 的翻面消失）⇒ 证明失忆确实不是变量，甲案**永久关闭**。
5. **实测证明 PG 里 `<sid>:<worker>` 子线程 checkpoint 是负担**（行数/体积量出来）⇒ 乙-2 从"建议"升 P1。本单**没有**跑这条（见 §6-1）。
6. 任何人**只 apply R114 的 patch 而不修形状** ⇒ 立即回退：那 5 枚用例（含 `test_round_three_still_answers_the_figure_from_round_one_material`）会红，且红在一枚不存在的机制上。

---

## 6. 三笔自报（诚实账）

1. **没查到的**：① PG `checkpoints` / `checkpoint_blobs` 里 `<sid>:<worker>` 子线程的**真实行数与体积**（要连真库或 `docker exec psql`，本单按"不许动数据 / 镜像"的边界放弃，只给代码级论证）；② 11 枚 R114 用例**今天**实际的 passed/failed 分布 —— 静态分类给了"10 枚依赖 patch 符号 / 1 枚 patch-free"（§2-1），但真跑要么把文件放进 `tests/`（越写域），要么放 `%TEMP%`（拿不到 `tests/conftest.py:126-143` 的模型哨兵与 `:234-268` 的宿主端口闸，跑出来的红绿不可信），故**未执行**，登记态 6/5 只作转述引用；③ 前端在会话切换时是否真的复用 `session_id`（`frontend/**` 禁碰，未查）。
2. **顺手改到的写域外字节**：**无**。仓内新建仅本纸一枚；探针与分类脚本全部落在仓外 `%TEMP%\r118_probe\`（新建目录，未覆盖任何既有文件；`%TEMP%\r114_probe\` 与 `%TEMP%\evalrun\` 全程只读，其中 `r114_probe\trace` 一枚条目 `PermissionError`，未动）。**未 commit / 未 add / 未建分支或 worktree / 未碰 docker / 未打 127.0.0.1:8001 与 Ollama / 未 apply 任何 patch（只 `--check`）。**
3. **§55 判据本身我认为错的地方**（三条，都有上文凭据）：
   - L1720"若 R118 认定子图应当 resume，则这两枚留档**可直接续用**"写得太乐观 —— patch 与用例只覆盖**裁剪**半边，**不含形状修正**；只 apply 它们的后果正是"5 枚红 + 全仓多一层永不触发的裁剪代码"，也就是 §55 自己作废 R114 的理由。措辞该改成"甲案 = 形状修正（另写）+ 这两枚续用"。
   - "**形同虚设**"定性不准 —— 实测是**只写不读**：PG 里真的在长行，而 `clear_session`（`:1352-1361`）不回收子线程。这半句漏掉了一条**当前仍在发生的成本**，也正是乙-2 的全部理由。
   - "跨轮记忆只剩父层那句【doc Agent 返回】"**高估了父层** —— 那句从没进过 supervisor 的 prompt（`:397` 只送 `[sys_msg, current_user_msg]`；`:362-379` 的 `filtered` 是死代码；R27 注释 `:286-288` 早已自陈）。真正的通道只有改写腿与按 user 召回的长期记忆 ⇒ 本单的取舍更该写成"**要不要给 worker 一条会话记忆，还是继续只靠改写 + 用户级记忆**"。

---

## 7. 取证命令（原样，含解释器绝对路径与环境变量行）

```powershell
$env:LOCAL_MODEL_NAME='__eb_test_disabled__'
& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest tests/test_r109_rewrite_offline_guard.py tests/test_r117_ledger_turn_scoped.py tests/test_r122_stub_honesty.py -q -p no:cacheprovider   # 30 passed
& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe $env:TEMP\r118_probe\probe_ns.py       # 生产形状 2/2/2；单跑 2/4/6/8
& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe $env:TEMP\r118_probe\probe_keys.py    # 子线程 ns 逐轮换 uuid；钉 ns 无效
& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe $env:TEMP\r118_probe\probe_shapes.py  # shape1/2/4 RESUME，shape3 AMNESIA
& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe $env:TEMP\r118_probe\probe_shape1.py  # 真 DOC_PROMPT 干净复测 2/4/6/8
& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe $env:TEMP\r118_probe\classify.py      # 11 枚用例：10 需 patch / 1 patch-free
git apply --check --verbose $env:TEMP\r114_probe\r114_orchestrator.patch                                  # exit 0（只 check，未 apply）
# ↑ 这一枚与全部 git grep / git log / sha256 一样，实际是经 python subprocess 参数列表执行的（cwd = 本树），未落任何写入；含 | 的 git format 一律不经 PowerShell 字符串。
```

判分复算、日志解析（先嗅 `raw[:2]==b'\xff\xfe'` 再按 **UTF-16 LE** 解码）、sha256 与 `git grep` 一律走 python；`backend-run*.log` 按 utf-8 硬读会得到全零假阴性。
