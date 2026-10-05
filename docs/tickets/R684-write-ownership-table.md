# R684 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R684
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `docs/architecture/write-ownership.yaml`
- `scripts/`
- `tests/test_r684_*.py`
- `docs/tickets/R684-*.md`
- `docs/testing/r684-<今天>.md`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="LINE::docs/handoff/2026-09-15-backend-followup-requests.md::- **R684**："
- **R684**：`docs/architecture/write-ownership.yaml` 逐咽喉文件列分片方案与所有者；针＝表里每条路径与符号必须现取存在（断头即红）；「同一单号写集相交」的派工必须被这张表当场拒。
```

出处谓词＝`LINE::docs/handoff/2026-09-15-backend-followup-requests.md::- **R684**：`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

- `docs/architecture/write-ownership.yaml`

## 总控亲签段（派工口径·以上「判据原文」逐字块为准）

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

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r684-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R684（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。
