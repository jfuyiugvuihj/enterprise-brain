# R717 · `deploy/queue_worker.py` 三处 `chat.build_queue_terminal` 不递 `claims`（R702 交回，队列那一行今天仍「缺席」）

**号**：R717　**性质**：总控亲签（R702 执行层停下交回件 ①）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R702 执行层 Confucius 现读，凭据纸 `docs/testing/r702-2026-10-06.md`）

- R702 已经把问答腿与队列**构造点**都接上：`app/api/v1/chat.py::claims_for_egress` → `done_frame_for_turn` → `done_sse_frame`，队列侧 `build_queue_terminal` 与读数面 `queue_terminal_readout` 同名同位同缺席语义。
- 🔴 但真正把 `claims`／`claims_error` 递进构造点的调用方在 `deploy/queue_worker.py`，三处调用一个都没递 ⇒ 队列那一行今天仍然只是「缺席」，D 相（`REPORT_LANE_VIA_QUEUE`）拿不到分母。
- 形状与在册先例 **R504→R514** 同族（那一族就是靠承接单把发布腿补齐的）。

## 判据（每条可失败）

1. 三处调用逐枚点名递进 `claims`／`claims_error`，语义与 R702 构造点完全一致：交不出只发码，**绝不发空 `claims`**；空正文与挂起轮两格都不发。
2. 离线驱动一次队列终态（假 worker、零容器）断言读数面 `queue_terminal_readout` 与 SSE 终态**同名同位**——两形的键集合差只许落在具名格里（`data_filename`／`claims`／`claims_error`），第四枚新键不许过。
3. 反证牙两枚：摘一处 `claims` 投递 ⇒ 该钉必红并点名是哪一处；把稳定码换成空 `claims` ⇒ 必红（不许退化成 R699 拒绝的那枚假绿）。
4. 🔴 **本单与 R719 同一枚契约面**：动 `docs/api/contract-v1.md` 之前先读 R719 的判据 1（那本改口账不登记，`tests/test_r645_contract_difference_ledger.py` 的反证牙就红），两单不许各自原地插一遍。
5. 卫兵不许坏：`tests/test_r37_report_lane_worker.py`／`tests/test_r702_claims_reach_the_terminal_exits.py`／`tests/test_r504_terminal_frames_carry_data_filename.py` 复跑仍绿；`tickets_index.py --verify` rc=0；控制符各 0。
6. 交付：同名件两态读数＋凭据纸 `docs/testing/r717-<开工日>.md`；**C④／D 门仍待窗**，写成达即退回。

## 写域（只许这些）

`deploy/queue_worker.py`／新增 `tests/test_r717_*.py`／`docs/tickets/R717-*.md`／`docs/testing/r717-<开工日>.md`；`docs/api/contract-v1.md` **只许文末追加一格**且必须先与 R719 对齐登记形状。

## 禁区（踩线即退回）

`app/**`（构造点已在树，不许二次改动）／`app/api/v1/chat.py`／`frontend/**`／夜窗量具 `scripts/eval_*`（归 R718）／主树任何路径／容器 rebuild。
