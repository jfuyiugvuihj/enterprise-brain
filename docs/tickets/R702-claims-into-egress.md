# R702 · 把 claims 接出进出口：C④ 从「没有分母的 0」变成真读数（egress 腿）

**号**：R702　**性质**：总控亲签承接单（R699 并树后暴露的第二腿）　**基点**＝开工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。
**执行时机**：🔴 **必须排在 R695 并树之后**——写域含 `app/api/v1/chat.py`，该文件在飞期间归 Bacon（R695），两席同文件即写域冲突。

## 病形现取（总控 10-06 14:0x）

- R699 已在树（`a816857`）：`app/agents/evidence.py::build_answer_claims` 造 claims、`require_measured_claims_denominator` 拒零分母、`eval_payload_for_answer` 是出货前唯一投影——但 **`rg -F eval_payload_for_answer app` 现取只命中定义本身，`app/**` 零调用点**。
- `app/api/v1/chat.py` 现取 `rg -F claims` 只命中两行前端注释（`frontend/src/lib/r150-event-claims.test.js` 的认领门），一格出口键都没有；`done_sse_frame`（定义在 `app/api/v1/chat.py::done_sse_frame`，调用点四处）交出的 payload 里没有 `claims`。
- 采集侧是「有就带走」：`scripts/collect_evaluation_answers.py::build_answer` 里 `for optional in ("claims", "confidence", "confidence_label"): if optional in payload`。⇒ 出口不给，真机采集件三窗 315 行里带 claims 的行永远是 0 行，C④ 的 `unsupported_claim_rate=0.0` 仍是没有分母的 0。

## 判据（每条可失败，缺一枚判负）

1. **出口真带键**：问答与队列两条终态出口都必须把 `claims`（`Claim.model_dump()` 列表）放进采集器在读的那枚 payload；判据形态＝离线驱动一次 `/chat`（假模型/`ModelHandler` 桩），断言响应体或落库的 answer 件里 `claims` 键存在且逐枚带 `text/supported/evidence_refs`。🔴 反证牙：把出口那一行摘掉 ⇒ 该钉必红并点名是哪条腿没带。
2. **零分母不许静默**：答案有正文却交不出断言时，出口必须把 `ClaimsDenominatorError` 记成可指认的失败形状（稳定错误码或终态原因码），不许退化成「不带 claims 键」——那正是 R699 拒绝的那枚假绿。
3. **契约不破**：`docs/api/contract-v1.md` 里 SSE done 帧／答案件形状必须同步新键（在册同步尺 `tests/test_r132_contract_followup_sync.py` 同族），前端不认新键也要照常渲染——`frontend/**` 一字节不许改，响应形状向后兼容（只增键不改键不删键）。
4. **热路径不付新税**：在册热路径钉 `tests/test_r149_sse_text_pieces.py`／`tests/test_r661_trace_journal_hot_path_teeth.py` 必须仍绿，读数逐枚贴进交付；出口不许新增同步 IO（claims 已在 `build_agent_result` 里算完，出口只做搬运）。
5. **不许翻绿 C④**：真读数由今晚 run32／run33 判；本单交付里明写「C④ 仍待窗」，写成达即退回。
6. **交付**：同名件两态读数（dirty／干净检出各一遍，清单逐枚相同）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋控制符各 0 枚＋坐标一律 `文件::符号`＋凭据纸 `docs/testing/r702-<开工日>.md`＋`python scripts/tickets_index.py --verify` rc=0。

## 写域（只许这些）

`app/api/v1/chat.py`（仅出口那一格与必要的导入）／`app/agents/evidence.py`（🔴 10-06 收窄：只许 import 调用，一字节不许改——该文件此刻由 R703 在飞席持有；投影函数 `eval_payload_for_answer` 已在树，本单无需再动它）／`docs/api/contract-v1.md`／新增 `tests/test_r702_*.py`／`docs/tickets/R702-*.md`／`docs/testing/r702-<开工日>.md`

## 禁区（踩线即退回）

`app/quality/**`（判分器）／评测夹具／`scripts/collect_evaluation_answers.py`（采集器只许读不许改）／`frontend/**`／`app/agents/orchestrator.py`／`app/trace/spans.py`／`app/common/stage_timing.py`（R695 刚并树的那些格，除非取证证明必须且先停下交回）／夜窗量具 `scripts/eval_*`·`r57*`·`r63*`·`r674*`／`pyproject.toml`／容器·镜像·模型动作／主树任何路径。

## 这一枚为什么存在

R699 把 claims 造出来了却没接出去，C④ 那一格今晚的窗还是会量到零分母；这一腿不并，run32／run33 白跑一扇（同一扇窗 1.9 小时，是这台机上最贵的资源）。

## 追加（总控 10-06 15:4x）· 基点、席位与边界

- 基点＝派工那一刻主树 HEAD 现取；独占席树 `C:\Users\fengx\PycharmProjects\be-r702`（detached checkout），不许换树、不许碰主树、不许 commit（并树归总控）。
- `app/agents/evidence.py` 一字节不许改（见上，写域已就地收窄）。需要的东西 R699 都造好了：`Claim`／`atomize_answer_claims`／`claim_support_scan`／`require_measured_claims_denominator`／`eval_payload_for_answer`。
- 与 R703 的边界：R703 交回那一格 `app/api/v1/chat.py::_should_use_data_context` 用「报销」落 `document_terms` 否掉 `data_filename`（连带 `route_main` 的 `has_data` 与 `_authorized_dataset_files` 退化成全量可见）**不归本单**，由 R709 承接。本单只把 claims 接出出口；顺手改路由＝两单读数混账，判负。
- 判据 3 写字段落点时只准 `文件::符号`，禁 `文件:行号`（在册尺 `scripts/lint_hand_copied_coordinates.py`）。

## 追加（执行层 R702 席位 10-06 交回）· 落地的形状、三手欠账、一枚须 widen 的针

凭据纸＝`docs/testing/r702-2026-10-06.md`（逐枚读数、两把反证刀的摘除-还原 sha 复证、盘面卫生全在那儿）。下面只记账。

**已落地（席树 `C:\Users\fengx\PycharmProjects\be-r702`，基点 `9ea7e97`，`rev-list --count 9ea7e97..HEAD`＝0，未 commit）**

- 问答腿：`app/api/v1/chat.py::done_frame_for_turn` 收本轮 `agent_results`，经
  `app/api/v1/chat.py::claims_for_egress`（只搬运：逐枚 `coerce_agent_result` ＋ 唯一投影
  `app/agents/evidence.py::eval_payload_for_answer`，一枚都不重算、零 IO）交给唯一构造点
  `app/api/v1/chat.py::done_sse_frame`；三处出口点（`/ask` 正文、`/approve` 续跑、答案缓存命中）逐枚表态。
- 队列腿（构造点那一半）：`app/api/v1/chat.py::build_queue_terminal` 收同名两枚参数，写的键与 legacy 帧
  逐字相同；`app/api/v1/chat.py::queue_terminal_readout` 照载荷搬运，一格都不添。
- 零分母不静默（判据 2）：三枚稳定原因码由 `app/api/v1/chat.py` 顶层 `CLAIMS_ERROR_*` 给出——
  `claims_denominator_zero`／`claims_record_unavailable`／`answer_cache_without_claims`。
  交不出断言那一轮**只发原因码、绝不发一枚空 `claims`**；空正文与挂起那一轮两枚槽位都不发。
- 契约：`docs/api/contract-v1.md` **文末追加一枚 `## R702` 一节**（+61 行、删除 0 行）。
  🔴 第一版曾把三段话插在 §Structured Agent Result／队列状态键表／done 帧正文里，被
  `tests/test_r645_contract_difference_ledger.py` 的差异账（`EXPECTED_DIFFERENCES_TODAY = 1`）判红——
  登记原地差异要改那本账所在文件，而那枚文件不在本单写域。走契约的货**只能文末追加**，这条已写进凭据纸。
- 钉：新增 `tests/test_r702_claims_reach_the_terminal_exits.py` 17 枚（判据 1・2・3・4 各有落点，
  反证名册 `test_the_counter_evidence_anchors_name_both_legs` 按腿登记）。
- 判据 4 读数：`tests/test_r149_sse_text_pieces.py` 16 passed、
  `tests/test_r661_trace_journal_hot_path_teeth.py` 34 passed、本单新增件 17 passed、
  上游 `tests/test_r699_claims_in_answer_payload.py` 11 passed；三十八枚同名件整批 dirty 态
  3 failed／867 passed／1 xfailed（三枚红的归因逐枚在凭据纸，其中两枚是盘面态自造成、并树后转绿）。

**三手欠账（逐枚点名，都落在本单写域之外，不许本席顺手做）**

1. **队列发布侧**：`app/api/v1/chat.py::build_queue_terminal` 在 `app/**` 里零调用点，唯一搬运方是
   `deploy/queue_worker.py` 那三处调用——今天递 `dataset_files`（R514 在册）而不递 `claims`／`claims_error`，
   所以队列那一行这两格今天仍是「缺席」。**形状与 R504 → R514 完全同族，建议照那一族另立承接单。**
   ⇒ 判据 1 里「队列那条腿」今天只并到构造点那一半。
2. **夜窗量具读不到**：`scripts/eval_transport_ask_v2.py::transport` 那枚载荷的键集合由
   `tests/test_r181_text_frame_ruler.py` 按名以**相等**钉死（五枚，不含 `claims`），它的读流没有 `done` 分支。
   采集侧 `scripts/collect_evaluation_answers.py::build_answer` 的「有就带走」今天已经能用，但针不给就带不走。
   ⇒ **本单并树之后 run32／run33 量到的 C④ 仍是 `NOT_MEASURED`**；要翻绿得连那枚五键针一起改，属夜窗量具单。
   **C④ 仍待窗，本单不翻绿。**
3. **一枚在册针需要 widen**：`tests/test_r504_terminal_frames_carry_data_filename.py::test_the_two_shapes_are_not_the_same_face`
   拿「缺席那一形 == `{"type"} | SHARED_READOUT_KEYS`」做相等判，而判据 2 要的正是多交一枚具名格
   （现取红字 `Extra items in the left set: 'claims'`）。两枚要求不可能同时绿， widen 归总控落笔；
   建议改成子集判：既有七格一枚不许少，新格只许在 `data_filename`／`claims`／`claims_error` 里。

**另记一件（取证，不动手）**：`app/agents/evidence.py` 的断言算在**剥皮之前**的 worker 正文上，
而交付正文走 `app/api/v1/chat.py::_answer_body` 剥内部交接标记，于是 `claims[].text` 里可能出现
「【doc Agent 返回】」那一句中转。本单口径是出口只搬运、不跨腿重判（与
`app/agents/evidence.py::aggregate_agent_result` 反着来）；治它要么改 `app/agents/evidence.py`
（此刻在飞，归 R703），要么改剥皮时机（归编排单），都不在本单写域。