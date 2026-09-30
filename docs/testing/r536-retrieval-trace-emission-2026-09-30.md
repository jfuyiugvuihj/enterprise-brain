# R536 · 产品问答道补发 `retrieval.completed`（2026-09-30）

身份：执行层单号 **R536**，独占工作树 `C:\Users\fengx\PycharmProjects\be-r536`，基点 `81784da`
（＝主树 `codex/data-file-catalog` 现取 HEAD，`git rev-parse HEAD` 实取）。🔴 零 commit、零 push、
零新建分支：`git branch --show-current` 现取为空串（`--detach`）。

## 0. 本席跑过什么、没跑什么（先声明，免得下一班误读）

补令写死了窗规矩：主树全量门跑完后紧接着是 run10 真机评测窗（105 题，相 1 约 3.5–4 h），
本机 `MODEL_MAX_CONCURRENCY=1` ⇒ 任何并发争用都会把 p95 读数量成假话。

- **解锁前的静态层**（「只写不跑」那一段）：`py_compile`（五枚文件 exit 0）、AST/正则现取、逐字节行尾与 sha256 清点、以及把在册尺 `scripts/r483_empty_tables_triage.py` 的现扫部分（`SourceIndex` + `analyze` + `product_surface`，不连库、不发语句）在改动前后各读一遍。
- **总控 09-30 解锁令之后亲跑过的**（run10 因外来 CUDA 负载在 32/105 中止，窗已让位）。解释器必须是主树 `.venv`（`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`）：裸 `python` 是 anaconda，没装 `chromadb`，`conftest.py:28` 的 R134 沙盒闸门当场 `ModuleNotFoundError: No module named 'chromadb'`。全部 `-p no:cacheprovider`、不带 `-n`、没跑 `run_gate.py`、没起 docker、没打模型：

| 命令原文（都带 `cd C:\Users\fengx\PycharmProjects\be-r536` 与前缀 `python -m pytest`） | 末行读数 |
|---|---|
| `tests/test_r536_single_emission_point.py -p no:cacheprovider -q` | `7 passed in 16.61s` |
| `tests/test_r536_retrieval_completed_on_product_lane.py -p no:cacheprovider -q` | `11 passed, 4 warnings in 15.01s` |
| `tests/test_r536_counter_evidence_teeth.py -p no:cacheprovider -q` | `8 passed in 7.45s` |
| `tests/test_prefiltering.py -p no:cacheprovider -q` | `32 passed, 1 warning in 2.22s` |
| `tests/test_trace_persistence.py -p no:cacheprovider -q` | `5 passed in 0.31s` |
| `tests/test_retrieval_debug.py -p no:cacheprovider -q` | `2 passed in 1.22s` |
| `tests/test_observability_routes.py -p no:cacheprovider -q` | `24 passed, 36 warnings in 7.42s` |

- 🔴 **没跑出读数的一批**（换席时正跑第一枚就被中止，一件都没落数）：`tests/test_r524_queue_lane_sends_no_second_character.py`、`tests/test_r524_sink_reaches_both_runways.py`、`tests/test_r464_one_terminal_answer_stream_per_round.py`、`tests/test_r483_empty_table_triage_is_derived.py`、`tests/test_r531_worktree_merge_keeps_each_files_eol.py`、`tests/test_r178_retrieval_denial_audit.py`、`tests/test_r112_prompt_packing.py`、`tests/test_r159_cross_scope_matrix.py` ⇒ 代跑形状同上，逐枚一条命令。
- **跑出来的两处真红与本席的修法**（都落在本单写域内，一枚在册钉都没放宽）：
  1. 驱动端点那两枚起手 `2 failed, 9 passed`：病根是本席把 `chat.ask(...)` 直接塞进 `_consume`，拿回来的是协程 ⇒ `AttributeError: 'coroutine' object has no attribute 'body_iterator'`。改用在册同族的两段式（`tests/test_approve_canonical_events.py:219-232`：先 `asyncio.run(chat.ask(...))` 取响应，再 `asyncio.run(_consume(response))`）⇒ 11 passed。
  2. 反证刀起手 `2 failed, 6 passed`：K1 的刀口只切了那枚跨行调用的**第一行**，影子文件剩下悬空实参、`ast.parse` 当场炸（量到的不是「调用点没了」而是「文件坏了」）⇒ 刀口改摘整枚调用语句；K6 里本席新加的那行把链元组又解包一次 ⇒ `ValueError: too many values to unpack`，改回按链判 ⇒ 8 passed（七把刀全咬＋总清点那枚绿）。
- 全程没动 `data/`、`chroma_db/`、`logs/`：新钉里凡是要写 trace 的都接替身或 `tmp_path`，本席还顺手把 `chat.py` 端点自己那几处 `default_trace_store()` 接到替身上。跑测试时 R134 闸门现读 `PersistentClient 调用: 1 次，其中落点被改道出工作树: 1 次`、`工作树 chroma_db 写回告警用例: 0 枚`；R56 闸门现读 `blocked connect attempts to host model port: 0`、`LOCAL_MODEL_NAME = '__eb_test_disabled__'`——两枚闸门自己把「没碰真库真模型」写进了读数。## 1. 症状与口径（现取出处）

- 症状（R534 §3 丙组 D 行、§6 **R536** 行）：全仓发 `retrieval.completed` 的只有
  `app/rag/debug.py`，正常问答链一枚都不发 ⇒ `retrieval_traces` 永远 0 行 ⇒ V2 #12
  「每轮问答可回查检索」没有数据，也是 C 门那半格从沙盒读数升级到生产读数的唯一路径。
- 🔴 口径（`docs/testing/r483-empty-tables-2026-09-29.md:104`，总控 09-29 裁定）：
  `no_seed_path` 不是合法为空，是欠码；且**不许拿 `POST /retrieval/debug` 那一腿冒充产品道**。
  本单据此把「调试面仍旧只发它自己那一枚」也钉成判据（见 §3 的 `..._debug_face_still_emits_exactly_one`）。
- 消费方（只读）：`app/trace/projections.py:321 project_retrieval`，现读 `payload` 的
  `hits` / `query_hash` / `filters` / `index_version_id` / `agent_run_id`（可缺省）与事件层的
  `trace_id` / `sequence` / `request_id` / `status` / `timestamp`；`owner_id` 由
  `app/trace/store.py:239 record_event` 从 `payload["owner_id"]` 读，缺它整行以
  `REASON_OWNER_MISSING` 被拒（`app/trace/store.py` 那处 `_refusal_before_writing`）。
  表列 `query_hash CHAR(64) NOT NULL` 出自 `migrations/0002_execution_data_lineage.sql:170` 那张表。

## 2. 改动清单（`git diff --numstat` 原样）

```
24      0       app/api/v1/chat.py
206     1       app/rag/retrieval_pipeline.py
```

外加三枚新钉与这本纸（`git status --porcelain=v1` 原样见 §8）。

- `app/rag/retrieval_pipeline.py`：末节新增那一整段是**唯一**的发射实现
  （`arm_retrieval_trace` / `reset_retrieval_trace` / `current_retrieval_trace_context` /
  `RetrievalTraceContext` / `_retrieval_query_digest` / `_retrieval_hit_ledger` /
  `_product_trace_store` / `record_retrieval_completed`），调用点只有一枚，在
  `RetrievalPipeline.search_for_principal` 里（`record_retrieval_scope` 之后、`return` 之前）。
- `app/api/v1/chat.py`：只在两枚 `_run` 函数体内挂/交回身份（`/ask` 流式腿 `:2707` 起、
  `/approve` 续跑腿 `:3474` 起，行号为改动后现取），零其它改动。

为什么挂在 `_run` 里而不是端点函数里：chat.py 把图跑在 `loop.run_in_executor(_executor, _run)`，
那枚普通 `ThreadPoolExecutor`（`chat.py:21`）**不复制调用方的 contextvar**；而 langgraph 的同步
执行器会把上下文复制进节点线程（现取 `langgraph/pregel/_executor.py:64 ctx = copy_context()`，
以及 `langchain_core/runnables/config.py:660 get_executor_for_config` →
`langsmith/utils.py:764 ContextThreadPoolExecutor`）。⇒ 挂在工作线程帧内是必要条件，
`test_the_ask_stream_lane_arms_the_worker_thread_it_really_runs_in` 量的就是这一格跨线程传递。

为什么留痕不抄正文：`hits` 那一格只记 `source` / `chunk_index` / `score` / `classification` /
`department`；本轮 400 字摘录已经由证据袋走 SSE 的 `sources` 帧（`chat.py::_document_source_row`），
再抄一份进 trace 表只是同一份资料多存一处。`query_hash` 存 sha256 不存题面，同理。

## 3. 判据① —— 产品问答道确实发出这枚事件

**达成——运行读数本席亲跑：`11 passed, 4 warnings in 15.01s`**（起手 2 枚红已修，见 §0）。三枚运行层证据全在
`tests/test_r536_retrieval_completed_on_product_lane.py`（11 枚用例）：

| 用例 | 它咬的那一格 |
|---|---|
| `test_the_principal_aware_retrieval_leg_emits_one_event` | 一发检索一枚事件；逐字段对 `project_retrieval` 要的入参 |
| `test_the_event_is_what_the_registered_consumer_reads` | 事件喂给**在册真消费方**，折出的那行十列逐格核 |
| `test_the_row_lands_in_retrieval_traces_through_the_real_store` | 真 `TraceStore` + JSON 持久化 ⇒ 行真落在 `retrieval_traces` 上 |
| `test_the_ask_stream_lane_arms_the_worker_thread_it_really_runs_in` | 驱动真 `chat.ask`：图在工作线程里读得到身份，事件 trace 与 SSE 帧同源 |
| `test_the_approval_continuation_lane_emits_too` | 批准续跑腿同样发出；并与 R172 的 `request.started` 挂同一枚 trace |
| `test_the_debug_face_still_emits_exactly_one` | 🔴 口径钉：`/retrieval/debug` 不因为本单变成两行 |
| `test_an_unarmed_retrieval_emits_nothing_and_returns_the_same_hits` | 没挂身份零写入，检索结果一字不变 |
| `test_arm_refuses_to_invent_an_identity` | 缺硬身份不挂、不发（宁可不发，不编 trace） |
| `test_the_identity_does_not_leak_to_the_next_turn_on_a_reused_thread` | 复用的工作线程不串身份（token 必须成对交回） |
| `test_a_dead_trace_backend_does_not_break_the_answer` | 留痕后端炸了不打断这一轮（与 `_record_trace` 同裁定） |
| `test_a_lone_retrieval_event_seeds_the_run_row_completed_and_says_so` | 现状钉：见 §6 那一格竞窗 |

命令原文（本席已亲跑，末行 `11 passed, 4 warnings in 15.01s`；总控请在主树复跑同名件）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r536
python -m pytest tests/test_r536_retrieval_completed_on_product_lane.py -p no:cacheprovider -q
```

## 4. 判据② —— 发射点唯一（读数：`7 passed in 16.61s`，本席亲跑）

尺子住在 `tests/test_r536_single_emission_point.py`（7 枚用例），五格判据合一在 `judge()`。
本席在 `81784da` + 本单改动上亲跑静态尺（不导入 `app.**`、不起服务），实取读数：

```
emitter literals: {'app/rag/debug.py': 1, 'app/rag/retrieval_pipeline.py': 1}
consumer words: 2
emitter calls: [('app/rag/retrieval_pipeline.py', ('search_for_principal',))]
arms:   [('app/api/v1/chat.py', ('ask', '_ask_stream', '_run')),
         ('app/api/v1/chat.py', ('approve', '_approve_stream', '_run'))]
resets: [('app/api/v1/chat.py', ('ask', '_ask_stream', '_run')),
         ('app/api/v1/chat.py', ('approve', '_approve_stream', '_run'))]
JUDGE: []
```

钉死的五格，每格都长牙（再长出第二枚发射点/第二处调用点/把挂点挪出 `_run` 都当场红）：

1. 发射实现只有一枚函数，且住在 `app/rag/retrieval_pipeline.py`；
2. 调用点集合恰好 `{("app/rag/retrieval_pipeline.py", "search_for_principal")}`；
3. 全仓 `app/**` 里 `event_type=` 交这枚事件名的行 = 本模块 1 枚 + 调试面遗留 1 枚，多一枚即红；
4. 消费方 `app/trace/projections.py` 里 `retrieval.completed` 那两枚字眼一处不变（它读事件，不发事件；
   R523 那一席要是改了消费方，本钉立刻把参照物的漂移报出来）；
5. `chat.py` 挂/交回成对（2/2）且两枚挂点都在 `_run` 函数体内，`chat.py` 里零发射实现、零调用点。

🔴 事件名刻意写成字面量而不是常量：`scripts/r483_empty_tables_triage.py::event_emitters`
按 `event_type="<名字>"` 的字面形状找发射点，藏进常量等于把新发射点从在册台账的视野里抹掉。

## 5. 判据③ —— 反证刀七把（读数：`8 passed in 7.45s`，本席亲跑）

`tests/test_r536_counter_evidence_teeth.py`（8 枚用例：七把刀 + 一枚总清点）。🔴 七把刀**全部只在
`tmp_path` 的影子副本上动手**，真盘面每把刀前后各核一次 sha256，最后一枚 `test_the_roster_is_back_at_the_bytes_recorded_before_every_blade` 逐字节算总账。

| 刀 | 摘掉的那一格 | victim（在册钉本身） |
|---|---|---|
| K1 | `search_for_principal` 里的发射调用 | `test_r536_single_emission_point.py::test_the_product_call_site_is_exactly_one` |
| K2 | 「没挂身份就不发」那道闸（改成编一枚身份） | `..._on_product_lane.py::test_an_unarmed_retrieval_emits_nothing_and_returns_the_same_hits`（并让调试面开始冒充产品道） |
| K3 | payload 的 `owner_id` | `..._on_product_lane.py::test_the_principal_aware_retrieval_leg_emits_one_event` |
| K4 | `_retrieval_query_digest` 的 sha256（改回吐题面） | 同上（64 位十六进制那一格 + 「不许把正文抄进 trace」） |
| K5 | payload 的 `hits` | `..._on_product_lane.py::test_the_event_is_what_the_registered_consumer_reads` |
| K6 | `/approve` 那一腿的挂点 | `test_r536_single_emission_point.py::test_arms_live_inside_the_worker_thread_bodies` |
| K7 | `/approve` 那一腿的 token 交回 | `test_r536_single_emission_point.py::test_chat_py_arms_both_lanes_and_holds_no_emitter` |

每把刀动手前都断言锚点在真盘面命中恰好一枚、动手后断言字节确实变了（切空气的刀当场红）。
七把每把都带「先正控」那一半：K1/K2/K3/K4/K5/K6 在摘刀前各在同一场判断上断言它是绿的，K7 断言聚合尺的「挂/交回对数」那一格为空，摘刀之后才要求它红。K6 额外证明切的就是 victim 钉自己那一格（影子盘面上的挂点数从 2 掉到 1，剩下的那一枚仍坐在 `_run` 里）。
锚点命中数本席已现取：`CALL 1 / GATE 1 / OWNER 1 / HITS 1 / DIGEST 1`（pipeline），
`APPROVE_ARM 1 / APPROVE_RESET 1 / ARM_CALL 2 / RESET_CALL 2`（chat.py）。

命令原文（本席已亲跑：刀那枚 `8 passed in 7.45s`、静态尺 `7 passed in 16.61s`）：

```powershell
cd C:\Users\fengx\PycharmProjects\be-r536
python -m pytest tests/test_r536_counter_evidence_teeth.py -p no:cacheprovider -q
python -m pytest tests/test_r536_single_emission_point.py -p no:cacheprovider -q
python -m pytest tests/test_r536_retrieval_completed_on_product_lane.py -p no:cacheprovider -q
```

摘刀前的逐字节 sha256（本席现取，`ROSTER` 那五枚就是总清点钉的账目对象；这一遍是在本席最后一次动字节——给五枚文件补上文末 `CRLF`——之后**重取**的（含 §0 那两处修码后的字节），与本单交回的最终盘面逐字一致）：

```
app/api/v1/chat.py                                         sha256 386eb09f572061277420b661257123cb39ca800cbaf996435f336076d29cd278  bytes 267490  CRLF 5274  loneLF 0  loneCR 0  BOM 无  末字节 CRLF
app/rag/retrieval_pipeline.py                              sha256 487160315b9ee57cb398fe20e4b89ba727bb24fcd3f4a1c1dde00963a3e688b7  bytes 63867   CRLF 1228  loneLF 0  loneCR 0  BOM 无  末字节 CRLF
tests/test_r536_retrieval_completed_on_product_lane.py     sha256 35a6a944fa96ffbd689c4ccdebf4a7028a4b87692ecac7c10b5a46be96f6814c  bytes 23901   CRLF 502   loneLF 0  loneCR 0  BOM 无  末字节 CRLF
tests/test_r536_single_emission_point.py                   sha256 930751625e2b1a5f2e52a0f1289da8c6d7e14177beeb4f89a9f71560e313a8a9  bytes 8390    CRLF 191   loneLF 0  loneCR 0  BOM 无  末字节 CRLF
tests/test_r536_counter_evidence_teeth.py                  sha256 076cd6fd817f3e3a5878da4bf66e0e5601b6c081f5d4e39b3cdfd844de425850  bytes 13421   CRLF 291   loneLF 0  loneCR 0  BOM 无  末字节 CRLF
```

## 6. 判据④ —— 今天还是量不到什么（写死，不许下一班当成已达成）

- 🔴 **`retrieval_traces.rows > 0` 这一格本单交不回**。它需要一次真问答窗（真模型、真向量库、
  真 HTTP 面），而本单明令不许起服务、不许打模型、不许动容器。⇒ 码与牙已就位，
  欠的是「一次安静机器上的真问答读数」，由总控在 run10 之后的窗里取；取数口径建议直接
  `SELECT count(*) FROM retrieval_traces` 按 `trace_id` 点清，并核 `GET /api/v1/traces/{trace_id}`
  能不能在「检索」那一块看到行（前端 `TracePanel.vue` 与 `observability.py` 的读腿都在册）。
- **留痕的枚数是「一发检索一枚」，不是「一轮问答一枚」**：唯一调用点坐在 `RetrievalPipeline.search_for_principal` 上，而一轮真问答可以多次进这一层。图里那两处产品内调用方（AST 现取 enclosing 函数，非推断）：`app/agents/tools.py:1109`（在 `search_docs` 那枚工具里，文档腿）、`app/agents/orchestrator.py:1024`（在 `_approval_worker_node` 里，审批预审在图里的那一发）——两条都跑在同一枚已挂身份的工作线程内 ⇒ **审批预审那一轮会留两枚痕**，各一发检索一枚。同一枚调用点今天还被图外三方按到、而三方都没挂身份 ⇒ 都不发：`app/rag/debug.py:40`（调试面，口径钉着不许当产品道）、`app/mcp_server.py:48`、`app/approval/assistant.py:234`（`resolve_standard_from_knowledge_base` 的默认 reader，由 `app/api/v1/intelligence.py:158` 与 `app/api/v1/open_platform.py:218` 两枚 HTTP 端点驱动，不经图）。本单 §3 用例里的 `len(events) == 1` 钉的是「假编排只跑一发检索」这一场，不是每轮恒等于 1 的契约。

- **排队道（`REPORT_LANE` / 限流入队）今天仍不发**：那一腿在 `deploy/queue_worker.py` 的进程里跑，
  本单写域不含它，也没人给它挂身份。要补它，需要那一枚进程在自己的工作线程里
  `arm_retrieval_trace(...)`（一次两行的接线，判据② 的尺会自动把它的调用点算成在册）。
- **旧版 `/chat` 那一腿今天仍不发**（R534 现读坐标 `:1669-1671`，本单现取仍是那三行）：它走
  `app/rag/retriever.py::DocumentRetriever.search`，不经检索管线，所以本单那一枚调用点碰不到它。
  补它要么在 `chat.py` 长出第二枚发射调用点（🔴 与判据② 直接冲突，本单不干），要么把这腿改走
  管线（那是换检索语义，越出本单范围）。⇒ 记「未覆盖」，不记「已达成」。
- **MCP 面（`app/mcp_server.py:48`）今天不发**：同一枚原因（没人挂身份），同一格补法。
- **`index_version_id` 这一列今天必是 NULL**：产品检索腿不带这格（在册真源在
  `app/rag/indexing.py` 的 registry，取它要在每发检索多问一次库），而 `run_retrieval_debug`
  那一腿这格本来就是调用方传进来的字符串。⇒ 留 NULL 是诚实的空白，本单不拿假值填绿
  （`test_the_event_is_what_the_registered_consumer_reads` 里明确钉了「不许凭空填一格」）。
- 🔴 **`/approve` 那一腿的两枚 trace 编号今天不同源**：`chat.py` 生成 `request_id/trace_id/task_id`
  给自己那三处出口用，却从不把它们交给 `run_interrupt_stream`（后者在 `_execution_ids` 里另生成
  一套）。本单的留痕挂在**调用方看得到的那一枚 trace** 上（与 SSE 帧、与 R172 的
  `request.started` 同源），代价是图自己那批事件仍在另一枚 trace 上。并成一枚要改 `chat.py` 那处
  调用参数，属另一格决定，本单不动。
- 🔴 **`/approve` 那一枚竞窗（本单按现状钉交回，总控 09-30 已裁「本单不动、另立单号治」**
  · **现状（逐枚现取坐标）**：`_approve_stream` 这枚 async generator（`app/api/v1/chat.py:3456-3874`）里，把工作线程起来的 `agent_future = loop.run_in_executor(_executor, _run)` 坐在 `:3507`，而第三处出口 `_record_resumed_lane_trace(...)`（定义 `:1464`）坐在 `:3559`——**同一条函数体，提交在先、记 `request.started` 在后**。工作线程从 `:3507` 那一刻就开跑，`:3559` 只是事件循环上下一步才走到的语句，两者之间没有任何同步点 ⇒ 本单那枚检索留痕完全可能成为这一枚 trace 的**第一枚**事件。落库形状由 `app/trace/lifecycle.py:101` 那格的 `if terminal_event or not current:` 分支定：「一枚 trace 的第一枚事件就把 run 行种出来」，而 `project_run` 递给它的 `status` 就是本单事件的 `completed` ⇒ 那枚 run 在轮次还没结束之前已经是 `completed`。`/ask` 碰不到这一支（那条道的 `request.started` 记在 `app/agents/orchestrator.py:1421`，在 `run_with_stream`（定义起于 `:1337`）体内，而图要到 `:1435` 的 `_cancellable_stream(...)` 才起跑 ⇒ 本单那枚留痕在这条道上排不到第一枚）。现状钉：`test_a_lone_retrieval_event_seeds_the_run_row_completed_and_says_so`（两半：单发留痕确实种成 `completed`；而 `request.started` 在先时这一枚留痕一个字都不改那枚 run 的结论）。
  · **为什么今天这不算一处错报**：`retrieval_traces` 那一行本身说的都是真话——trace/request/task 三枚 id 是客户端这一轮真拿到的那三枚（SSE 帧同源），`hit_count`/`query_hash`/`filter_snapshot` 出自真检索真判定，`agent_run_id` 走在册 `run_id_for(trace_id)` 的派生而不是编的。脏的是**它顺带种出来的那枚 run 行的 status**，不是这一行留痕。而且种下去之后 `is_terminal_status(current)` 那一道闸会拒绝任何后续降级（`app/trace/lifecycle.py:96` ⇒ `REFUSAL_TERMINAL_REGRESSION`），所以真出事的是**那一轮后来失败了却仍写着 `completed`**：run 行的结论从此改不动。本单不去治它，因为治它要动的是出口次序而不是发射点。
  · **治它要挪的那一处**：把 `app/api/v1/chat.py:3559` 那一枚 `_record_resumed_lane_trace(...)` 调用整体挪到 `:3507` 的 `loop.run_in_executor(_executor, _run)` **之前**（同一枚 `_approve_stream` 体内，早于任何一帧发出，也就早于工作线程起来），这样第一枚事件永远是 `request.started`、run 行按真状态起步，本单那枚留痕只会往已经在跑的 run 行上追加一格。另有一处更彻底的解法与本单那格「两枚 trace 不同源」是同一件事：把 `:3485-3492` 那枚 `run_interrupt_stream(...)` 调用补上 `request_id/trace_id/task_id` 三枚实参（`app/agents/orchestrator.py:1546-1556` 的签名本来就收，缺省时 `:1572 _execution_ids()` 自己另生成一套）⇒ 图那一侧的事件与调用方的留痕并成一枚 trace。两笔都在 `app/api/v1/chat.py` 的非检索腿格子里，越出本单写域 ⇒ 本席一字未动，等总控另立的单号。
- 📌 **在册散文改口＝待总控落笔（总控 09-30 裁定 1）**：`docs/testing/r483-empty-tables-2026-09-29.md:103-104` 与 `scripts/r483_empty_tables_triage.py` 里 `TRIAGE["retrieval_traces"]["why"]` 那句「正常问答链一枚都不发」，从今天起是假话——**本席一字未动**（那枚文件此刻在在途 Kuhn/R523 写域里，它 `--sync` 重生成过一次，两席同写必撞）。建议措辞按裁定原样留着：**「道已接通、欠一次真窗读数」**，`retrieval_traces` 的裁定应从 `no_seed_path` 挪到那一档。改口由总控在 R523 并完之后统一落。
- 每发检索多一次 trace 写入（同一枚进程级 `TraceStore` + `trace_events` 与投影行的两次 upsert），
  量级与既有 canonical 事件同级；**它对 p95 的真实影响本单没量**，属 run10 之后的窗读数。

## 7. 在册账面副作用：R483 那本现扫台账（现取 before/after）

同一枚尺（`scripts/r483_empty_tables_triage.py` 的 `SourceIndex` + `analyze` + `product_surface`，
只读源码、不连库）在改动前后各读一遍：

| 读数 | 改前（`81784da` 干净树） | 改后（本树 dirty 态） |
|---|---|---|
| `event_emitters("retrieval.completed")` | 1 处：`app/rag/debug.py:72 run_retrieval_debug` | **2 处**：加 `app/rag/retrieval_pipeline.py:1222 record_retrieval_completed` |
| 产品面路由（`product_surface()["routes"]）` | `[]` | `[]`（BFS 5 跳按**符号名**爬，图内那条道不姓 `/ask`） |
| 调试面豁免 | `POST /retrieval/debug` | 同（豁免仍在用，没成后门） |
| BFS 节点数 / surface problems | 2 / `[]` | **10 / `[]`** |

本席（收窗前第二遍现取，只读源码）另记两条 raw 读数：`surface["nodes"]=10`、`surface["problems"]=[]`，而 `surface["trail"]` 13 处里点名了 `app/agents/tools.py:1085 · search_docs`、`app/agents/orchestrator.py:962 · _approval_worker_node`、`app/rag/retrieval_pipeline.py:959 · search_for_principal`。⇒ `routes == []` 说的是「BFS 按 HTTP 路由装饰器/add_job 的形状找脸，而图里那一腿不姓路由」，**不是**「产品问答走不到这枚调用点」——走到走不到的证据在 trail 里，那一格今天是有名字的。

⇒ 结论两条：① 那把尺的**牙今天咬不到这一格**（`validate()` 的「裁为 no_seed_path 但现扫已能从
产品面走到它」这一条不会触发，`tests/test_r483_empty_table_triage_is_derived.py:187` 那枚在册钉
不会因为本单变红）；② 但它的**散文过期了**：`TRIAGE["retrieval_traces"]["why"]` 那句「发这枚事件
的只有一处：app/rag/debug.py……正常问答链路的检索腿一枚都不发」，与
`docs/testing/r483-empty-tables-2026-09-29.md:103-104` 那两句，从今天起是假话。这两处都在本单
禁入清单里 ⇒ 本席一字未动，**交回总控改判**（`retrieval_traces` 的裁定应从 `no_seed_path` 挪到
「道已接通、欠一次真窗读数」那一档），别让下一本复评拿旧散文当口径。

## 8. 本席自查

- 写域：`git status --porcelain=v1` 原样 ——
  ```
   M app/api/v1/chat.py
   M app/rag/retrieval_pipeline.py
  ?? tests/test_r536_counter_evidence_teeth.py
  ?? tests/test_r536_retrieval_completed_on_product_lane.py
  ?? tests/test_r536_single_emission_point.py
  ?? docs/testing/r536-retrieval-trace-emission-2026-09-30.md
  ```
  逐枚点名：两枚在册件全在写域白名单内；三枚新钉与这本纸全在 `tests/test_r536_*.py` /
  `docs/testing/r536-*.md` 两个命名形状内。🔴 禁入清单里那十一处
  （`app/trace/**`、`app/storage/persistence.py`、`migrations/**`、`docs/api/contract-v1.md`、
  `docs/testing/r483-empty-tables-2026-09-29.md`、`frontend/**`、`deploy/.env.server`、
  `.env.example`、`tests/test_evaluation_report.py`、评测集数据、`app/agents/**`、`pyproject.toml`）
  零接触：`git diff --name-only` 只有那两枚文件，未跟踪件只有那四枚。
  过程里曾在树根留过一枚临时脚本 `tmp_r536_eol.py`（行数清点用），已删除，现不在盘上。
- 行尾：这台机 `core.autocrlf=true` 且无 `.gitattributes`。三枚新钉全部 **CRLF 落盘**，
  逐枚现取 `loneLF=0 / loneCR=0 / 无 BOM`（见 §5 那五行表）；
  `git ls-files --eol --others --exclude-standard -- tests` 三枚都报 `w/crlf`。
  两枚被改文件写回时按「读 LF → 改 → 以 `newline="\r\n"` 写」处理，改后仍是纯 CRLF
  （chat.py CRLF 5274 / pipeline CRLF 1228，loneLF 0 / loneCR 0）。
  📌 施工中途本席一度把 pipeline 的文末换行弄丢过（`git diff` 于是打出 `\ No newline at end of file`，与 `81784da` 那版原字节多出一格差异），现已补回：五枚在册件＋这本纸逐枚现取**文末都是 `CRLF`**，`git diff -- app/rag/retrieval_pipeline.py` 末三行不再带那枚标记（现取）。
  📌 一处派工词与盘面不符，按实交回：本单被要求对齐的那枚行尾钉，名字不是
  `tests/test_r366_*_keeps_the_repository_line_endings`（现取 `git ls-files tests | rg r366` 只有
  `test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py`，与行尾无关）；树里那枚行尾尺
  是 `tests/test_r531_worktree_merge_keeps_each_files_eol.py`（尺本体 `scripts/r531_worktree_merge.py`），
  它对「新件」的要求是同目录在册件多数决 —— `tests/**` 盘上多数是 CRLF，本席按 CRLF 落，一致。
- sha：§5 那五行是摘刀前的字节账，也是本单交回的最终字节——本席**最后一次动字节是补文末换行**，补完即重取整表，所以这张表对着的是交回态，不是施工中途的某一格。
- 语法：五枚文件 `py_compile` 全过（exit 0）。**没有任何测试读数**，见 §0。
- 零 commit：`git log -1 --format=%h` 现取 `81784da`；`git branch --show-current` 现取空串。
- 第二班（09-30 13:1x）复取，全部静态层、零运行：
  · 判据② 那把尺在本树重跑一遍，五格读数一字未变（`JUDGE: []`；emitters `{'app/rag/debug.py': 1, 'app/rag/retrieval_pipeline.py': 1}`；调用点 `[('app/rag/retrieval_pipeline.py', ('search_for_principal',))]`；arms/resets 各 2 且链同前）；
  · 七把刀的 7 处锚点在盘上逐枚复取命中数＝1（另外 4 处是替换体，不参与命中判定）；
  · 五枚在册件的文末换行补齐后重取 sha 表（就是 §5 那五行），并逐枚回读纸表核对：5/5 逐字一致；
  · `scripts/r483_empty_tables_triage.py` 的现扫部分（`SourceIndex` + `analyze` + `product_surface`，不连库）复取：`nodes=10`、`problems=[]`、`routes` 只有被豁免的 `POST /retrieval/debug`，与 §7 同值；
  · contextvar 跨线程那一格的参照物在**实装包**里现取确认：`C:\Users\fengx\anaconda3\Lib\site-packages\langgraph\pregel\_executor.py:64 ctx = copy_context()`（同步 `BackgroundExecutor.submit` 用 `ctx.run` 提交），而 `chat.py:21` 那枚 `_executor` 是裸 `ThreadPoolExecutor`（不复制上下文）⇒ 挂点必须落在 `_run` 体内这件事有实装出处，不是推断。

## 9. 交给总控的复跑次序

1. 窗收令之后，先跑三枚新钉（§3 / §5 的命令原文，定向、`-p no:cacheprovider`、不带 `-n`）；
2. 再跑会被本单波及的两枚在册件（它们今天盘上仍是 `81784da` 的原字节，摘刀零沾）：
   ```powershell
   python -m pytest tests/test_prefiltering.py tests/test_trace_persistence.py tests/test_retrieval_debug.py tests/test_observability_routes.py -p no:cacheprovider -q
   ```
   预期绿的道理：未挂身份时发射器直接返回 `None`（K2 就是量这一格的），所以那四枚在册件的
   形状一字没动；`test_r112_prompt_packing.py` 那一族的子类替身不经过本层发射点，同样零影响。
3. 最后 `python scripts/run_gate.py` 全量门（本席按补令未跑）。🔴 并树验收两遍（dirty 与 commit 后）
   都要跑，两遍的文件清单逐枚点名 —— 本单没跑过任何一枚，所以两遍都得总控亲取。
