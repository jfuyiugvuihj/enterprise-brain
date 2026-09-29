# R514 · G03 队列道：三处 `build_queue_terminal` 现在传 `dataset_files`（`deploy/queue_worker.py`，2026-09-29）

工作树 `be-r514`，基点 HEAD=`60a8e01`（总控 09-29 现取，dirty=0）。本单一枚 commit 都没打，产物留在树上。
写集只有三处：`deploy/queue_worker.py`（改）、本读数件（新建）、`tests/test_r514_queue_worker_passes_dataset_files.py`（新建）。
`docs/api/contract-v1.md` 一字未改（他席占用），口径写在本件 §2，交回后请总控统一补契约。

## 1. 三处调用点逐枚现读（判据①）

改前行号取自我在本树现跑的 `rg`（基点 `60a8e01` 干净态）：三处都是 `terminal = chat.build_queue_terminal(`，一处 `dataset_files` 都没传。

| 处 | 改前 | 改前那一支实际递了什么 | 拿不拿得到数据文件账 | 改后 |
| --- | --- | --- | --- | --- |
| 挂起腿 | `:695`（`_process_report_lane_turn` 内 `if parked:`） | `terminal_state=AWAITING_APPROVAL / answer_present=False / worker_status / sources=[] / scope_reason_code="" / sources_error="" / usage / approval=hitl_approval_handle(...)`，**无 `dataset_files**`** | 🔴 拿得到：`agent_results` 是 `_drain_report_stream` 在这一轮之前已经收回来的证据袋（`:444-445` 从顶层快照 `state["agent_results"]` 搬进来），本处只读它，一次索引台账都不打 | `:703` 调用，`:711` 递 `dataset_files=dataset_files` |
| 正文腿 | `:740`（同函数 `else` 支） | `terminal_state=ANSWERED / answer_present / worker_status / sources=visible_sources / scope_reason_code / sources_error / usage`，**无 `dataset_files**` | 🔴 拿得到：同一只 `agent_results`（`chat.queue_turn_sources(agent_results, principal)` 在 `:737` 已经拿它折出处，用的是同一只袋子） | `:749` 调用，`:757` 递 `dataset_files=dataset_files` |
| 老腿 | `:897`（`_process_reserved` 无 interrupt 的 `queue_graph` 支） | `terminal_state=ANSWERED / answer_present / worker_status / sources=visible_sources / scope_reason_code / sources_error / usage`，**无 `dataset_files**` | 🔴 拿得到：`record = agent_result.model_dump()`，而 `run_orchestrator_queue`（`app/agents/orchestrator.py:1165`）里那句 `aggregate_agent_result(result.get("agent_results") or {}, ...)`（`app/agents/evidence.py:371`）把各 worker 的 `evidence` 逐条 `extend` 进同一枚 canonical 记录（`:400-401`）。`:893` 早已拿 `{"orchestrator": record}` 喂 `queue_turn_sources`，同一只袋子同一个键名形状 | `:913` 调用，`:921` 递 `dataset_files=dataset_files` |

**判据②（某一处本来就拿不到账）没有触发**：三处都拿得到，所以本单没有「只取证不改」的那一支。
这条结论不是从签名读的，是从调用点读的——取数可达性逐枚查了上游搬运点（`:444-445` / `:737` / `:893` + `app/agents/evidence.py:400-401`），
并在 §3 用三枚真跑的钉各证一次（挂起腿那枚尤其不是推理：它跑的是真 `StateGraph`，`data` 节点真算了、真停在 `export` 之前）。

## 2. 取数口径（真源指名）

- 真源两枚：**`app/api/v1/chat.py::attach_terminal_data_filename`**（`:372`，只有 `terminal_data_filename` 一枚取值来源，空串就整格不发）与
  **`terminal_data_filename`**（`:362``，`dataset_files[0] if len(dataset_files) == 1 else ""`）。本单一个字都没改它们。
- 收集器口径：**`chat._collect_dataset_filenames`**（`:344`）→ 逐 worker 读 `record["evidence"]`，只认 `source_type == "dataset"`，
  文件名出自 **`_chat_dataset_evidence_filename`**（`:329`）：先 `locator.filename`（`app/agents/evidence.py::record_dataset` 落的结构化那一格），
  再 `source_name` 兜底，最后取 `basename`。
- worker 侧因此**只加两枚取数点**（`:681` 报告档、`:912` 老腿），交的就是这两枚在册件，没有新造取数路径、没有第二枚收集器、
  没有第二处拼名字（钉在 §4 的结构钉里：worker 源文件里 `terminal_data_filename` / `attach_terminal_data_filename` 出现 0 次，`def _collect` 出现 0 次）。
- 报告档那一枚取数放在 `if parked:` **之前**（`:674-681`），与 `usage` 同一格、两腿共用同一份读数；
  R254 那句「挂起这一轮不取出处」管的是 `queue_turn_sources` → `_authorized_source_rows` 要现取检索范围（打台账），
  与本处纯内存搬运无关，这一点在源码注释里也写明了。
- 🔴 **零枚与多枚一律不传**，缺席说的是「这一格说不清」；
  **绝不回显请求方向**：队列载荷里根本没有 `data_filename` 那一格（`app/api/v1/chat.py:2419-2425` 的 `payload` 只有
  `task_type/message/session_id/username/principal`（+ `lane/write_back_session`）），worker 全文改前改后都读不到它，
  本单也没有加 `payload.get("data_filename")`（钉在 §4 最后一枚）。

## 3. 新钉清单（`tests/test_r514_queue_worker_passes_dataset_files.py`，12 枚）

判据②四形全部按「一枚道真跑」驱动：报告档用 `_run_with_stream` 替身 + 真 `ReliableQueue(FakeRedis)`，挂起腿用**真 `StateGraph`（`interrupt_before=["export"]`）**，
老腿替身 `run_orchestrator_result` 交回真 `AgentResult`。文件名一律只经工具边界唯一的写入口 `record_dataset` 进证据袋，不从正文反推。

| 形 | 用例 | 钉的是 |
| --- | --- | --- |
| 一份 ⇒ 带名字 | `test_the_answered_report_lane_names_the_one_file_it_computed_from` | 正文腿 `:749` |
| 一份 ⇒ 带名字 | `test_the_parked_report_lane_names_the_file_it_read_before_parking` | 挂起腿 `:703`（同轮还钉 `terminal_state=awaiting_approval / answer_present=False / sources=[]`，即「没正文」与「算过哪份」两件事并存） |
| 一份 ⇒ 带名字 | `test_the_legacy_lane_names_the_one_file_it_computed_from` | 老腿 `:913` |
| 零枚/多枚 ⇒ 键不出现 | `test_a_report_round_that_cannot_single_out_one_file_omits_the_cell[`report-zero` / `report-two`]` | 正文腿两形 |
| 零枚/多枚 ⇒ 键不出现 | `test_a_parked_round_that_cannot_single_out_one_file_omits_the_cell[`parked-zero` / `parked-two`]` | 挂起腿两形（挂起不是补造的口子） |
| 零枚/多枚 ⇒ 键不出现 | `test_a_legacy_round_that_read_two_files_omits_the_cell` | 老腿多枚形 |
| 缺席≠整轮消失 | `test_the_zero_file_leg_still_publishes_a_terminal_and_an_answer` | 零枚那一腿仍交 `answered` + 正文（防「把整腿关掉」这种假绿） |
| 不回显声明值 | `test_a_declared_filename_in_the_payload_never_becomes_the_terminal_cell` | 载荷带 `data_filename` 而本轮没跑数据 ⇒ 键仍不出现；并现读源码断言没有 `payload.get("data_filename")` |
| 结构 | `test_the_worker_builds_three_terminals_and_all_three_take_the_sink` | AST 现取 `build_queue_terminal` 调用点恰好 3 处，逐枚带 `dataset_files` 关键字 |
| 结构 | `test_the_worker_feeds_the_sink_only_from_the_registered_collector` | 在册收集器 2 枚取数点、`dataset_files=dataset_files,` 恰 3 枚、无第二处拼名字、无 `def _collect` |

用 `NO_CELL` 哨兵分清「没有这一格」与「这一格是空串」，两形分开断言。

## 4. 反证刀（判据③）——四把，逐把逐字节还原

每把都是「现取 `deploy/queue_worker.py` 文本→单点替换（锚全文唯一，命中数必须为 1）→跑新件→从内存里那一份原字节写回」。
还原后 sha256[:16] 与基线 `f9d645528492a8a8` 逐次相等：四把全部 `same=true`。

| 刀 | 改法 | 红字（`FAILED` 原文 + 计数） |
| --- | --- | --- |
| 刀一·A | 挂起腿 `:711` 那行删掉（改回不传） | `FAILED ...test_the_parked_report_lane_names_the_file_it_read_before_parking`、`FAILED ...test_the_worker_builds_three_terminals_and_all_three_take_the_sink`、`FAILED ...test_the_worker_feeds_the_sink_only_from_the_registered_collector` ⇒ **3 failed, 9 passed** |
| 刀一·B | 老腿 `:921` 那行删掉（改回不传） | `FAILED ...test_the_legacy_lane_names_the_one_file_it_computed_from` + 上面两枚结构钉 ⇒ **3 failed, 9 passed** |
| 刀二·A | 报告档取数之后补一句 `dataset_files = dataset_files or ["报销明细表.csv"]`（零枚也传） | `FAILED ...test_a_parked_round_that_cannot_single_out_one_file_omits_the_cell[parked-zero-filenames0]`、`...test_a_report_round_that_cannot_single_out_one_file_omits_the_cell[report-zero-filenames0]`、`...test_the_zero_file_leg_still_publishes_a_terminal_and_an_answer`、`...test_a_declared_filename_in_the_payload_never_becomes_the_terminal_cell` ⇒ **4 failed, 8 passed** |
| 刀二·B | 报告档那行收集器删掉（不取证、空列表照传） | `FAILED ...test_the_answered_report_lane_names_the_one_file_it_computed_from`、`FAILED ...test_the_parked_report_lane_names_the_file_it_read_before_parking`、`FAILED ...test_the_worker_feeds_the_sink_only_from_the_registered_collector` ⇒ **3 failed, 9 passed** |

补一句口径差：「拿空列表也传」按字面执行（传 `[]` 而不传）在字节上与不传**等价**（`attach_terminal_data_filename` 对 `[]` 与 `None` 都整格不发），
任何一枚钉都不会因此红——所以刀二交了两形：`·A` 拿一枚名字补造（红 4 枚）、`·B` 摘掉取证（红 3 枚）。这两形才是这一判据真正能咬住的两件事。

## 5. 判据④ 读数（dirty 态）

树：`60a8e01` + 本单三处改动，`git status --porcelain` = `M deploy/queue_worker.py` / `?? tests/test_r514_queue_worker_passes_dataset_files.py`（`17 insertions(+), 0 deletions(-)`）。
解释器 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（本工作树没有 `.venv`，`chromadb 1.5.9` 只在那一具里）。

| 集合 | 枚数 | 读数 |
| --- | --- | --- |
| 新件单跑 | 12 | **12 passed**，exit 0，11.64 s |
| 点名 6 枚（新件 + `test_r254_sync_lane_terminal` + `test_r254_queue_terminal_honesty` + `test_r504_terminal_frames_carry_data_filename` + `test_r259_awaiting_approval_stops_the_watch` + `test_r259_terminal_readout_lands_in_the_book`） | 146 | **146 passed**，30.95 s（同一集合另两次独立复跑：**146 passed / 19.62 s** 与 **146 passed / 19.69 s**） |
| 扩样 9 枚（`test_r37_report_lane_worker`、`test_r414_b_terminal_data_filename`、`test_queue_worker_reliability`、`test_r227_discard_is_honest`、`test_r227_lease_heartbeat`、`test_r222_queue_terminal_stopwatch`、`test_r232_queue_status_vocabulary_sync`、`test_r294_principal_freeze`、`test_r81_queue_terminal_retry`） | 181 | **181 passed**，exit=0，55.81 s |
| 15 枚合跑（点名 6 + 扩样 9） | 327 | **327 passed in 43.98 s**，`exit=0`（146 + 181 = 327，两集合相加逐枚吻合，无假绿重叠） |

口径说明：上面三行全是 `deploy/queue_worker.py` 真跑出来的读数（挂起腿走真 `StateGraph`，不是只读签名的取证）。

- `python scripts/run_gate.py` 全量门：**本单没跑**（明令不许自行开窗/全量；AGENTS 那条「dirty 一遍 + commit 后干净树复跑」的第二遍本席交不了，因为本席不许 `git commit`）。
  🔴 干净态由总控 `git commit` 之后复跑同名 15 枚件，并与看板最新绿票对账。
- `rg -c classification_blocked app/` → 无输出、exit=1（**0 命中**）；本单没碰 `app/**`。
- 零新错误码：diff 新增行里 `error_code` / `raise` / `requests.` / `httpx` 命中 0（`git diff | Select-String` 空）。
- 零新增外部请求：只加两枚纯内存搬运（读已收回来的证据袋），一次台账都不打。
- 零 Chroma：`deploy/queue_worker.py` 里 `chroma` 仍只有改前那两枚注释（`:41`、`:373`），diff 里 `chroma` 命中 0。
- 三枚在册件（`test_r254_sync_lane_terminal` / `test_r254_queue_terminal_honesty` / `test_r504_terminal_frames_carry_data_filename`）**一枚字都没改**，只升不降成立。

## 6. 没做到 / 留给总控（明写）

1. 🔴 **没 commit、没干净树复跑**（本席禁 commit），§5 的 327/146/181 全是 dirty 态读数；干净态同名件复跑归总控。
2. 🔴 **没跑 `scripts/run_gate.py` 全量门**，没有全量绿票数字。
3. **`docs/api/contract-v1.md` 一字未改**（他席占用）：§2 的口径需要总控补进契约 R504 节那一格——
   那里今天还写着「`deploy/queue_worker.py` 的三处 `chat.build_queue_terminal(...)` 调用还没传 `dataset_files`」，本单之后这句过期了。
   同处请一并改口 `docs/testing/r504-g03-terminal-frames-data-filename.md` §9 第 1 条（归台账，本单一行没动）。
4. **屏上那一格仍不由队列道驱动**：`/queue/status` 投影（`chat.queue_terminal_readout`，`:5029-5031`）今天会把载荷里这一格原样搬运出来，
   但 `frontend/src/lib/sessions.js` 的 `done` 分支不读载荷键（R504 §9 判据②原账）——两道新读数上屏属前端线。
5. **缓存命中腿那一格仍未治**（R504 §8 独立立案那一族）：本单只治队列道三处调用点，没碰缓存条目缺 `dataset` 落账那件事。
6. 真机没量：本件全部是字节 + 载荷形状口径，没起服务、没打模型、没动容器。

