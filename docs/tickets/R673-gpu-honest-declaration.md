# R673 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R673
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `app/common/`
- `app/rag/`
- `tests/test_r673_*.py`
- `docs/tickets/R673-*.md`
- `docs/testing/r673-<今天>.md`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R26::判据（机器可验）"
① 容器内 `nvidia-smi` 有卡；② **拿不到卡必须显式报错 + 稳定码**，不得静默 CPU；③ `/health/details` 能区分"模型太慢"与"机器没 GPU/内存不足"；④ 硬件基线（GPU/显存/最低配置）入文档，与 **R24 ②③ 合并验收**
```

出处谓词＝`S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R26::判据（机器可验）`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

（本枚判据原文里没有点名的文件路径——落点由总控派工时给。）

## 总控亲签段（派工口径·以上「判据原文」逐字块为准）

## 现取病形

- 容器内 `printenv OLLAMA_REQUIRE_GPU` 现取 **rc=1（未设）** ⇒ 今天的真机跑分是 CPU 腿（`OLLAMA_MODEL` 实为 `qwen3:8b`），而 R26② 那条真机判据要的是 GPU 硬门。
- 缺省形状＝**fail-open**：开关不设在，跑分照样跑，只是慢。没人说过这是设计还是漏设——账面两种读法都成立，这就是假账温床。

## 判据（每条都可失败，缺一枚判负）

1. **未设时的行为必须有名字**：启动或首次调用那刻，日志必须打出一行具名声明（现取符号级：谁打的、打的什么串），并说明「此刻走的是 CPU 腿、R26② 类判据在这种形态下不可判」。加一枚离线牙：摘掉那行声明 ⇒ 牙必须红。
2. **设成 on 时必须真硬**：`OLLAMA_REQUIRE_GPU` 为真值时，拿不到 GPU 就地**具名失败**（不许静默降级成 CPU 继续跑）；反证牙双向：把硬门改成静默降级 ⇒ 在册牙必须红，且红的话点名是哪一个符号。
3. 🔴 **不许翻生产缺省**：`deploy/.env.server` 与任何 `.env*` 的当前值一格不许动，翻不翻由业主裁定（看板 §4GG 待业主清单）。本单只证「两种语义各自可失败、且互不混」。
4. 判定口径写进凭据纸一句话：**在 fail-open 形态下测出的所有延迟数，不得用于 R26②**（这一句是给下一班的护栏，不许省）。
5. 交付含：两态同名件数字（窗内禁跑 ⇒ 标 `NOT_RUN_IN_WINDOW`）、牙的红／绿读数、`rev-list`=0 盘面自证、控制符各 0 枚、坐标一律 `文件::符号`。

## 写域（只许这些）

`app/common/`（GPU 探针与开关语义所在符号）／`app/rag/`（仅当探针调用点在此）／新增 `tests/test_r673_*.py`／`docs/tickets/R673-*.md`／新凭据纸 `docs/testing/r673-<今天>.md`

## 禁区（踩线即退回）

`deploy/**` 与任何 `.env*` 值／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／`app/api/v1/chat.py`／评测夹具与判分器／`scripts/run_gate.py`／容器与镜像动作／主树任何路径。

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r673-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R673（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。


---

## 总控追加（10-06 10:5x·派工前写域窄化，与本单原判据同时生效）

- 🔴 **写域窄化到符号级**：只许 `app/common/model_capabilities.py` ＋新增 `tests/test_r673_*.py` ＋ `docs/testing/r673-<开工日>.md`。目录级 `app/common/` 与 `app/rag/` **一律禁碰**——`app/common/model_handler.py` 正由 R690（席位 Pasteur）独占，`app/rag/**` 另有他席；两席同文件＝真写域冲突，退回。
- 现取盘面（派工时）：`OLLAMA_REQUIRE_GPU` 已在 `deploy/.env.server` 里被夜队列**追加**成 `1`（业主 10-05 裁定翻 on），三枚容器 `printenv` 现取＝1，昨夜单题 smoke **rc=0／45.8 s** 未触发回滚。所以本单**不再需要**动容器或动 env——`deploy/.env.server` 属禁区，动它即作废。
- 顺带一格记账（可由本单的证据纸承接，不许改量具）：`tests/test_r453_default_env_baseline.py::test_the_effective_name_set_baseline_when_the_deployment_env_file_is_present` 因那行新键而红（干净树 `wt-r670s2`@`328bfbe` 上不存在未跟踪的 env 件，故对照不红）。这一格的正解是把 `OLLAMA_REQUIRE_GPU` 登记进基线名册，属账面登记，不属改判据；若你判它必须改口径才能绿，停下写进交付由总控裁。
- R26②／A③ 的翻绿**不由本单宣布**：语义钉＋离线反证归本单，「丢卡必报错」的真机演练要一扇不吃外网的窗（Ollama 在 compose 网络内），窗后排。交付里明写哪格待窗，写成达即退回。