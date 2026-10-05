# R684 · 写域所有权表：把「谁在抢 chat.py」变成一张机器能拒的表（提速前置）

**基点**：开工时现取主树 HEAD。**独占工作树**：总控预配。**零产品码**，本单只治派工。

## 现取病形（成本，不是口味）

- 并行度名义 3～4、实际 1～2：写集高度集中在三枚咽喉——`app/api/v1/chat.py`、`app/agents/nodes.py`、`docs/api/contract-v1.md`（现读 506 KB／215 枚指针）。台账自己就记着串行理由：「R670 必须等 Erdos 收席因写域含 chat.py」「这两堆必须一起并」。
- R666 一枚单被投给两枚席（#14 同族，本次 10-05 又撞一次：`Lovelace` 429 死、`Bohr` 并树，两份实现并存）；两枚席同抢一枚单＝写域冲突的另一种形态，现表不拦。

## 判据（每条都可失败，缺一枚判负）

1. 新 `docs/architecture/write-ownership.yaml`：逐枚咽喉文件列 `路径 → 所有者单号 → 分片方案（按符号切还是必须整枚串行）`。表里每条路径与符号必须**现取存在**（断头即红）。
2. 一把派生校验针（全离线、不 import `app`、单跑秒数写进凭据纸，形状照 `tests/test_r132_contract_followup_sync.py`）：喂一条「两个在飞单号写集相交」的桩 ⇒ 尺子必须非零退出并点名相交的那条路径与两枚单号。
3. 三枚在册咽喉（`app/api/v1/chat.py`／`app/agents/nodes.py`／`docs/api/contract-v1.md`）**必须各有分片方案**，写不出分片方案的必须显式记成 `SERIAL_ONLY` 并附一句为什么（不许留空、不许写「暂时」）。
4. 🔴 **本单不改 AGENTS.md**：规矩条文由总控落；本单只交表＋尺＋牙。若结论是「必须有规矩改动才能落地」，停下写进交付。
5. 交付含：两态同名件数字（窗内禁跑 ⇒ 标 `NOT_RUN_IN_WINDOW`）、桩件红／绿读数、`rev-list`=0 盘面自证、控制符各 0 枚。

## 写域（只许这些）

`docs/architecture/write-ownership.yaml`（新）／`scripts/`（新增一张只读校验尺，命名带 r684）／新增 `tests/test_r684_*.py`／`docs/tickets/R684-*.md`／新凭据纸 `docs/testing/r684-<今天>.md`

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`AGENTS.md`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`scripts/run_gate.py`／`pyproject.toml`／`deploy/**`／容器与镜像动作／主树任何路径。
