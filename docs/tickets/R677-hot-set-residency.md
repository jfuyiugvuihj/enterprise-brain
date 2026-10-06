# R677 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R677
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `app/rag/hot_index.py`
- `tests/test_r677_*.py`
- `scripts/`
- `docs/tickets/R677-*.md`
- `docs/testing/r677-<今天>.md`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R44::判据（机器可验）"
① 覆盖 95% 查询的热集常驻；② 与 Chroma 结果一致性有测试
```

出处谓词＝`S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R44::判据（机器可验）`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

（本枚判据原文里没有点名的文件路径——落点由总控派工时给。）

## 总控亲签段（派工口径·以上「判据原文」逐字块为准）

## 现取病形

- `app/rag/hot_index.py` **在树上**（覆盖 95% 查询的热集那一半有码）；账上点名的**让路驱动件不在盘上**——与在册 R663／R654 同源（首任 429 死席、重写席 `Pauli` 亦 429 死，`be-r654` 零写入已取证）。
- 🔴 判据 R44① 今天仍**没达**，而且不许拿「文件在树」当达：让路没件，热集就是只进不出的常驻，冷查询与热查询争同一份预算。

## 判据（每条都可失败，缺一枚判负）

1. **让路腿存在且可失败**：热集占用达到在册阈值时，必须有一条真实代码路径让冷查询走非热集腿；把这条腿摘掉 ⇒ 在册牙必须红、补回必须绿（摘牙定义见版本文档 §1 第 6 条）。判据只认现取符号名，不许写「应有让路机制」。
2. 重量必须落在**一台安静机器**上：给出热集命中前后两组读数（同一 HEAD 复跑互比），并点名当时机器上有没有窗在跑——🔴 夜窗内不许重量，见 `docs/tickets/WINDOW-2026-10-05.md`。
3. 覆盖 95% 这一句必须有**分母**：用现取查询日志或在册评测集算出热集实际覆盖率读数；拿不到分母就写 `NOT_MEASURED`，🔴 不许造数、不许沿用账面旧数。
4. 若结论是「R44① 需要的量具今天不存在」⇒ 停下回报，由总控另立量具单；不许为了翻绿去改计划书判据原文。
5. 交付含：两态同名件数字、让路腿的符号级坐标（`文件::符号`，禁 `*.py:数字`）、`rev-list`=0 盘面自证、控制符各 0 枚。

## 写域（只许这些）

`app/rag/hot_index.py` 及其直接调用点／新增 `tests/test_r677_*.py`／`scripts/` 里新增的本单量具／`docs/tickets/R677-*.md`／新凭据纸 `docs/testing/r677-<今天>.md`

## 禁区（踩线即退回）

`app/api/v1/chat.py`／`app/agents/**`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`scripts/run_gate.py`／`deploy/**`／容器与镜像动作（除总控明令的重建窗口）／主树任何路径。

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r677-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R677（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。

---

## 总控派工段（10-06 13:1x·基点 `c82208c`·席位自拟名并回报）

- **基点改口**：本文头部写的 `9efff02` 已过期，派工基点＝主树现取 `c82208c`（含 R690 与 CHASE 三笔）。工作树＝`C:\Users\fengx\PycharmProjects\be-r677`（总控已 `git worktree add --detach` 备好，独占）。
- **解释器**：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（裸 python 无 chromadb，conftest 会当场 ImportError）。
- **写域追加一格**（原判据四格之外，派工即生效）：`app/rag/hot_index.py` ＋ `tests/test_r677_*.py` ＋ 新量具 `scripts/r677_hot_set_yield.py` ＋ 凭据纸 `docs/testing/r677-2026-10-06.md`。🔴 不许写整本 `scripts/`（原判据那一格太宽，会撞别人），只许新增你自己那一枚脚本；改任何在册脚本即退回。
- **禁区**：`app/agents/nodes.py`／`app/trace/**`／`app/common/stage_timing.py`（R688 在飞独占）、`app/common/model_capabilities.py`（R673 在飞独占）、`app/api/v1/chat.py`、评测夹具与 `tests/test_evaluation_report.py`、`frontend/**`、`docs/handoff/**`、容器／镜像／模型调用、`git push`、主树 commit（**你可以在你这棵树里自提交**，主树由总控代并）。
- **本班窄化**：本单只交**代码＋离线牙**。真机重量（安静机器 + 让路延迟）今晚在夜窗里由 `run32` 顺带取数，**本单不许起窗、不许打模型、不许动容器**；交付里明写「离线达／重量待窗」，写成达即退回。
- **判据（可失败）**：① 让路驱动件在位且有牙——热集命中路径与让路路径两条都能离线跑出来，且有一枚反证证明「摘掉让路 ⇒ 某枚计数必变」；② 与遗留引擎一致性那半句照原判据「有测试」；③ 凭据纸逐枚点名判据、两态数字（dirty 与自提交后干净树，文件清单逐枚相同）、未验清单。
- **回报**：交回 patch 路径 + SHA-256 + `git diff --numstat <基点>..HEAD` 逐枚点名 + 两态读数；执行层自报的数只作对照，总控亲跑才算。
