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

`app/api/v1/chat.py`（仅出口那一格与必要的导入）／`app/agents/evidence.py`（只许搬运函数，不许动判定）／`docs/api/contract-v1.md`／新增 `tests/test_r702_*.py`／`docs/tickets/R702-*.md`／`docs/testing/r702-<开工日>.md`

## 禁区（踩线即退回）

`app/quality/**`（判分器）／评测夹具／`scripts/collect_evaluation_answers.py`（采集器只许读不许改）／`frontend/**`／`app/agents/orchestrator.py`／`app/trace/spans.py`／`app/common/stage_timing.py`（R695 刚并树的那些格，除非取证证明必须且先停下交回）／夜窗量具 `scripts/eval_*`·`r57*`·`r63*`·`r674*`／`pyproject.toml`／容器·镜像·模型动作／主树任何路径。

## 这一枚为什么存在

R699 把 claims 造出来了却没接出去，C④ 那一格今晚的窗还是会量到零分母；这一腿不并，run32／run33 白跑一扇（同一扇窗 1.9 小时，是这台机上最贵的资源）。