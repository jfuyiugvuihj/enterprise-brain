# R719 · R702 已带货落地，但 `tests/test_r645_contract_difference_ledger.py` 的反证牙 #3 为红：文末追加那一截要怎么进那本账

**号**：R719　**性质**：总控亲签（第二十一班 R702 验收现场）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 今天的完整经过（凭据＝总控亲跑，两枚影子树单跑读数）

1. R702 并树笔 `4e280f1` 之后，`test_counter_evidence_3_moving_the_frozen_base_forward_reddens` 现取 **1 failed**（红句：两本账一起清还走得通 `['dfc75f0']`——那追加段那一条腿就是空转）；执行层交回时预言「提交后自己排除」，**这句没兑现**。
2. 总控当时 `revert` 了那笔货（`6deca3c`），同一 nodeid 复跑仍 **1 failed／64 passed** ⇒ 定性：这枚红**不是内容红，是历史红**——该刀认「最近一枚动过契约的提交」，而 `revert` 自己就是这样一枚（它把契约改短了），所以**退与不退同一枚红**。
3. 结论＝带货严格优于退回，故 `620aef5` 把货重新落地，红留在盘上、点名交本单。🔴 归因记在**契约登记这一格**，不记在 R702 的出口腿上（出口腿的同名件两态 142 passed，仅这一枚红）。

## 判据（每条可失败）

1. 先取证后动刀：现读那本账的三条腿各在咬什么——`FROZEN_BASE` 的字面量钉、差异账枚数门（`EXPECTED_DIFFERENCES_TODAY`）、追加段那一条腿（正例见 `tests/test_r645_contract_difference_ledger.py::latest_contract_commit` 那一族）。逐条写出「R702 那一节进不进账、进哪一本」的理由，缺一条不许动尺。
2. 治法只许三形：① 按那本账自己的形状把 `## R702` 那一节**登记**进去（单号＋凭据纸出处，`docs/testing/` 下的 .md，缺一枚必红）；② 证明 `FROZEN_BASE` 必须前移并给出前移凭据（前移是改坐标系，不是洗红，理由必须落在纸上）；③ 把契约那一节的形状改成那本账不需要登记的形态。**不许**把 `EXPECTED_DIFFERENCES_TODAY` 手改数字凑绿，**不许摘刀**，**不许**把反证牙改成 skip。
3. 结案读数：`tests/test_r645_contract_difference_ledger.py` 全件 **0 failed**，且反证牙 #3 仍会咬——本单必须交一枚「造一次无出处原地改口 ⇒ 必红」的复证（刀没坏的证据），不许只交「它绿了」。
4. 顺带收掉同一族第三枚：`docs/api/contract-v1.md` 今天被 R702 文末追加过，R717 还要追加一格 ⇒ 本单必须写清**后续契约追加的标准登记法**，落进契约文末或本单结案纸，别让下一班再撞一次。
5. 卫兵不许坏：`tests/test_r504_terminal_frames_carry_data_filename.py`／`tests/test_r702_claims_reach_the_terminal_exits.py`／`tests/test_r701-worktree-eol-form-pins` 那族同名件复跑仍绿；`tickets_index.py --verify` rc=0；控制符各 0；坐标一律「文件::符号」。
6. 交付：同名件两态读数＋凭据纸 `docs/testing/r719-<开工日>.md`；**C④ 仍待窗**（量具那一半归 R718）。

## 写域（只许这些）

`tests/test_r645_contract_difference_ledger.py`（登记与尺的形状）／`docs/api/contract-v1.md`（**只许文末追加登记说明**，不许原地改一字）／新增 `tests/test_r719_*.py`／`docs/tickets/R719-*.md`／`docs/testing/r719-<开工日>.md`

## 禁区（踩线即退回）

`app/**`／`deploy/**`／评测夹具与夜窗量具（归 R718）／`docs/handoff/**`／`scripts/run_gate.py`／主树任何路径。

## 为什么排第一

红集合里它现在是**有名有姓的一枚**，而 §9 判据 4 要「红集合为空」——R712 那 15 枚是量具过期，本单这枚是登记缺口，两本账分开治，不许混成一格含糊过去。
