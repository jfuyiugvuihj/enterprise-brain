# 计划书代码单台账 · 逐号归真（R262 · 2026-09-26）

- 单号 **R262** · 执行层代号 **Pauli**（自定，与看板 §0 名册一致）· 工作树 `be-r262` · 分支 `codex/be-r262`。
- **本账一律钉在 HEAD `03beca8`**（派工词令：不在基点就停下报告，不许自己追平）。主干今天的读数与本账的分歧逐条记在 §4.4。
- 本文件不产出新功能，产出的是一台**以后每班都能重跑的尺子**：`scripts/audit_plan_ticket_ledger.py`。
  它回答的问题只有一个——「账上写『这单落了 / 这单零提交』，git 树答不答应」。

## 1. 怎么重跑（可复跑性是这单的全部价值）

```
cd C:\Users\fengx\PycharmProjects\be-r262
python scripts\audit_plan_ticket_ledger.py                          # 出账；退出码 0＝自检全过
python scripts\audit_plan_ticket_ledger.py --timing                 # 耗时打到 stderr，stdout 不动
python scripts\audit_plan_ticket_ledger.py --fault R46=LANDED@deadbeef   # 反证：故意注错，看它咬
python scripts\audit_plan_ticket_ledger.py --fault R29=ZERO@             # 反证：把已落单写成零提交
```

- **只读**：脚本只调 `rev-parse / rev-list / log / show / diff-tree / cat-file / merge-base / status`，加读两枚 md；
  不写任何文件、不联网、不起服务、不动容器、不打模型、不跑测试（门在总控手上，不抢 CPU）。
- **逐字**：判据原文不落在脚本里，运行时按锚点从出处现场切段；锚点在窗口内命中数 ≠ 1 就当场 `exit 2`——
  出处漂了宁可不出货（本项目为裸行号与转述判据栽过三次）。
- **稳定**：同一 HEAD、盘上脏项不变时连跑两次 stdout 逐字节相同（无时间戳、路径一律正斜杠、按号排序）。实测两枚 sha256 相同。
  唯一一处不是 HEAD 的纯函数：首行 `worktree=dirty:N` ＝ `git status --porcelain -uall` 的行数，它诚实报告「你现在脚下有几项未提交」——
  本单三枚产物未提交时是 `dirty:4`（计划书 M ＋ 台账 md ＋ 脚本 ＋ 交付报告），总控提交后重跑会变成 `worktree=clean`，
  那一格随之变化，**这是设计如此，不是账漂**；其余每一格只由 HEAD 上的提交与两枚出处 md 决定。
- **会咬**：账里有假话 ⇒ 末行 `RESULT=FAIL` 点名单号＋条号，退出码 1。

## 2. 三档口径（这台尺子的定义，写死在 `self_checks()`）

| 档 | 成立条件 | 机器怎么验 |
|---|---|---|
| `LANDED` | ① 至少一枚提交在**本号名下**带来产品码或契约改动，**且** ② 判据无点名欠账 | C2 提交存在 · C3 `merge-base --is-ancestor` 在祖先链 · C4 提交信息含本号 · C5 点名落点在该提交实改文件里 · C6 实改文件类别 ∈ {产品码, 契约} |
| `PARTIAL` | 产物在树，但欠某一条判据 | C7 必须有产物（否则该判 ZERO）· C8 必须逐字引用欠的那条（出处＋LF 行号） |
| `ZERO` | 本 HEAD 祖先链上全史零产物 | C9 自动归集不得逮到本号名下产物提交 · C10 账上不得挂产物提交 |

- **产物口径**：产品码＝`app/ frontend/ scripts/ tests/ migrations/ deploy/ static/` 与代码类后缀；
  契约＝`docs/api/**` 与 `migrations/manifest.json`；`docs/handoff/**`、`README.md` 一律算**文书**，纯文书记账提交**不算产物**。
  唯一例外在账上具名：R258（总控自办的 runbook 假零订正）交付物本身就是那枚运维手册，判据① 在此不适用，脚本按 `classes=("文书",)` 明写。
- **归属口径**：提交**标题里第一枚单号**＝该提交的归属号。正文里提到某号不算证据（这正是上一格误判的成因）；
  拆单子号（`R26a`/`R43a`/`R254b`）与跨号转单（`R152`＝R46 后端半张、`R195`＝R46 消费侧、`R167`＝R43b）**不自动并号**，
  只在账上逐枚写明"挂在谁的号下、交了什么"。标题含 `catch up／追平／保活` 的提交只记账、不作产物证据（它们带的是别人的 diff）。
- **「判据达不达」这一半的分工**：R25–R52 的逐判据结案早有 `docs/handoff/2026-09-25-plan-ticket-closure.md`
  （单号 R224 · `Seneca` · 纯文书亲验，快照 `866c2f3`）。本账不重做它的物理取证，只把它的人判结论作为 `LANDED` 的第二半输入，
  **产物那一半全部由 git 自证**——这份 md 里 §3 是机器原文，§4 起才是人写。

## 3. 机器账（`scripts/audit_plan_ticket_ledger.py` 一次运行的原样输出）

下面整块是脚本 stdout，一格未改；里面的 §1–§8 是脚本自己的编号。
生成顺序（重要）：本块是在 §5.2 状态词**订正之后**跑的，所以它第 4 节「台账现词」已是**订正后**读数；
订正前的原词见 §4.3 表格第二列，或 `git show 03beca8:docs/handoff/2026-09-17-perf-architecture-plan.md`。

复跑一次应当逐字节相同（`--timing` 只把耗时打到 stderr）。

```text
R262 计划书台账归真 · 机器账（只读 git 与工作树；判据原文一律现读现切）
head=03beca81db62d1d1cae6c9fc7d417fb1bccd47bb commits_on_head=786 worktree=dirty:4
三档口径：LANDED＝产物在树且无点名欠账；PARTIAL＝产物在树但点名欠判据；ZERO＝HEAD 祖先链上全史零产物
归属口径：提交标题里第一枚单号＝该提交的归属号（拆单子号 R26a/R43a/R152 一类按账上具名挂靠，不自动并号）；标题含 catch up/追平/保活 的只记账不作产物证据
产物口径：产品码＝app/frontend/scripts/tests/migrations/deploy/static 与代码类后缀；契约＝docs/api/** 与 migrations/manifest.json

## 1. 逐号结论

| 号 | 判定 | 证据提交（归属·实改产物枚数） | 在 HEAD 祖先链 | 一句话依据 | 欠账引用 |
|---|---|---|---|---|---|
| R25 | **PARTIAL** | `ad85821`·施工[1 枚]、`b17b4dd`·并树[1 枚] | 是 | 两句判据都是容器内事实，从未在真机读过 | G-R25-1 |
| R26 | **PARTIAL** | `118801e`·R26a 施工[3 枚]、`11f9b1f`·R26a 并树[3 枚]、`af027ce`·R26b 施工[3 枚]、`6ee2f79`·R26b 并树[3 枚] | 是 | ②③④ 已落码，① 卡业主 H11 真机 | G-R26-1 |
| R27 | **PARTIAL** | `ce0b041`·施工[2 枚]、`6a4f02b`·并树[2 枚] | 是 | ③ 端到端 −≥35 s 等 A 门 | G-R27-1 |
| R28 | **PARTIAL** | `d2566e1`·施工[3 枚]、`1c0b08b`·并树[3 枚] | 是 | ③ 30 题不退化等 A 门 | G-R28-1 |
| R29 | **PARTIAL** | `62c734d`·施工[4 枚]、`791568c`·并树[4 枚] | 是 | 真机 A/B 判负：并的是「不迁腿」这个负结果与契约钉，30.6 s→≤22 s 一分没省 | G-R29-1 |
| R30 | **LANDED** | `3cb563b`·施工[13 枚]、`50aff1a`·并树[14 枚] | 是 | 四条判据逐条有码有钉（结案核对 R224 判「达」） | — |
| R31 | **PARTIAL** | `a7cd9b6`·施工[4 枚]、`eef642b`·并树[4 枚] | 是 | 后端交出合格片序列；② 逐片无缺字等 A 门，端点多发那一半转出 R149 | G-R31-1 |
| R32 | **LANDED** | `0cfd86a`·施工[4 枚]、`8a91f4e`·并树[4 枚] | 是 | ①②③ 达；档位选择器按假控件禁令不交、拆 R141 | — |
| R33 | **LANDED** | `b35e10f`·施工[5 枚]、`9678d21`·并树[5 枚] | 是 | 短期记忆腿自本枚起零模型，①②③ 达 | — |
| R34 | **LANDED** | `b1d185e`·施工[3 枚]、`e4d0c1b`·并树[3 枚] | 是 | ①②③ 达（① 引 09-19 真机落盘读数） | — |
| R35 | **PARTIAL** | `63651f1`·施工[6 枚]、`90d029f`·并树[6 枚] | 是 | ② 跨部门／跨密级 0 条命中待 C 门矩阵 | G-R35-1 |
| R36 | **LANDED** | `ef3d193`·施工[2 枚]、`ac44d00`·并树[2 枚] | 是 | 评测集 105 条在树，①②③ 达 | — |
| R37 | **PARTIAL** | `45b9720`·worker 半程[2 枚]、`0c08209`·并树[4 枚] | 是 | 产物在树、开关默认关；③ 终态原因码由 R227 改码后未重量 | G-R37-1 |
| R38 | **PARTIAL** | `c81fbb5`·施工[5 枚]、`2e6abc6`·并树[5 枚] | 是 | 通路形状已修（原生腿读回 input_tokens、cached 归真）；「抽查一问非零」等真机 D-2 | G-R38-1 |
| R39 | **ZERO** | 无（全史零产物） | — | 裁定不建（沿用 R17）；HEAD 上 R39 名下零提交 | G-R39-1、G-R39-2 |
| R40 | **PARTIAL** | `dc31a44`·施工[4 枚]、`8585315`·并树[4 枚] | 是 | ③ 前端硬编 standard 仍在（写域归 V 前端线） | G-R40-1 |
| R41 | **LANDED** | `e8d3200`·施工[2 枚]、`571e0d6`·并树[2 枚] | 是 | ①②③ 达 | — |
| R42 | **LANDED** | `5ff93cd`·施工[7 枚]、`89965d5`·并树[7 枚] | 是 | 按 §27.2 改判口径达；业主驳回 H15 则本号自动回未达 | — |
| R43 | **PARTIAL** | `4586bb4`·R43a 并树[4 枚]、`839c344`·R43b＝R167 并树[1 枚] | 是 | ① 由 R43a 落码；② 真机 E3 读数与「cached 落库那一列」都还没有 | G-R43-1 |
| R44 | **PARTIAL** | `9940c13`·施工[5 枚]、`39006b8`·并树[5 枚]、`564340e`·总控热修[4 枚] | 是 | ① 的 105/105 是在 379 chunk 小库＋哈希桩上证的，真库 37 483 chunk 未测 | G-R44-1 |
| R45 | **LANDED** | `0276f78`·施工[2 枚]、`640ef08`·并树[2 枚] | 是 | 按 §21.9／§21.10 重定义口径达 | — |
| R46 | **PARTIAL** | `c29ccf5`·R152 施工（后端半张）[8 枚]、`eaa9af8`·R152 并树[9 枚]、`484536c`·R195 并树（消费侧）[4 枚] | 是 | ① 真库/真并发次序未证；按 filename 聚合无身份 ⇒ 强度校准另在 R153 | G-R46-1 |
| R47 | **PARTIAL** | `95a1cd9`·施工[2 枚]、`006c613`·并树[2 枚] | 是 | ① 真实命中改进量 0/105（用例打桩） | G-R47-1 |
| R48 | **PARTIAL** | `0ad3d3e`·并树 R48 路线甲[8 枚] | 是 | ① 首屏 ≤1 s 在本机硬件口径上物理不可达（地板 11.0 s），B 行已整行移出 V1 | G-R48-1 |
| R49 | **PARTIAL** | `8680f43`·施工[6 枚]、`c26afda`·并树[6 枚] | 是 | ②「未索引」那张脸 UI 还没有 | G-R49-1 |
| R50 | **PARTIAL** | `090c820`·施工[4 枚]、`94f7fa1`·并树[4 枚] | 是 | 增量与可续跑在树；「低峰」那半句没挂进排程 | G-R50-1 |
| R51 | **PARTIAL** | `6833140`·施工[9 枚]、`cef08bf`·并树[9 枚] | 是 | ② 加总误差 <1% 未量；rewrite/reflect 两格插桩后置 | G-R51-1 |
| R52 | **PARTIAL** | `8c888c7`·施工[8 枚]、`1b84fb2`·闸门自修[2 枚] | 是 | ①②③ 全是墙上事实，E 行已整行移出 V1 | G-R52-1 |
| R141 | **LANDED** | `1cbd164`·并树[6 枚] | 是 | 档位标签第一次真改派工作腿；看板 §4BF 记「R141 达标并树」 | — |
| R142 | **LANDED** | `19761a5`·施工[5 枚]、`b58a5b9`·并树[5 枚] | 是 | 契约错误码表机械化对账上岗（并树记 +12 用例） | — |
| R143 | **ZERO** | 无（全史零产物） | — | R143 名下全史零提交；它点名的脚本早在 R58 名下就有（`a896cf6`），那一次预跑至今记在 R58③ 真机欠账 | G-R143-1 |
| R144 | **ZERO** | 无（全史零产物） | — | R144 从没立过单——它是业主建议号里被避开的那一枚，也不在计划书 §5.2 表内 | G-R144-1 |
| R145 | **LANDED** | `e2de245`·施工[3 枚]、`f747109`·并树[3 枚] | 是 | 向量镜像集合面对账台上岗（并树记 +91 用例） | — |
| R146 | **LANDED** | `77cd8b4`·施工[2 枚]、`25a08f0`·并树[2 枚] | 是 | cached-token 论述与记账归真（并树记 +16 用例） | — |
| R253 | **PARTIAL** | `ea2a539`·并树[6 枚] | 是 | ④「同一 HEAD 连跑三次 -n 8 零漂移」在本 HEAD 上仍未满 | G-R253-1 |
| R254 | **LANDED** | `8f89def`·并树[11 枚]、`c70548a`·R254b 总控补口[2 枚] | 是 | 六条判据逐条有码有钉（§101.2 记已结案） | — |
| R255 | **LANDED** | `3bf271d`·并树[7 枚] | 是 | 窗口与预算同一处推导，撞顶报错自报差额 | — |
| R256 | **LANDED** | `ff0f4ec`·并树[19 枚]、`d853153`·R256b 总控补口[1 枚] | 是 | 五条判据逐条对账，④ 首次在隔离 PG 真库跑到底并留凭据 | — |
| R257 | **ZERO** | 无（全史零产物） | — | R257 名下全史零提交（工作树 be-r257 停在基点 c70548a） | G-R257-1 |
| R258 | **LANDED** | `6b4f04c`·总控自办[1 枚] | 是 | runbook 三枚假零入册 | — |
| R259 | **ZERO** | 无（全史零产物） | — | 本 HEAD 上零产物；主干 `67ea193`（并树 R259）不在 03beca8 的祖先链上 | G-R259-1 |
| R260 | **ZERO** | 无（全史零产物） | — | R260 名下全史零提交（工作树 be-r260 停在基点 c70548a） | G-R260-1 |
| R261 | **ZERO** | 无（全史零产物） | — | 本 HEAD 上零产物；主干 `c9ad493`（并树 R261）不在 03beca8 的祖先链上 | G-R261-1 |

†＝该提交存在但不在本 HEAD 的祖先链上（未并树或活在别的分支）。

## 2. 证据提交实改文件（`git diff <第一父> <提交>` 逐枚现取）

- **R25**（PARTIAL）
  - `ad85821`（施工，祖先=是）→ 文书:README.md、产品码:docker-compose.dev.yml
  - `b17b4dd`（并树，祖先=是）→ 文书:README.md、产品码:docker-compose.dev.yml
- **R26**（PARTIAL）
  - `118801e`（R26a 施工，祖先=是）→ 文书:README.md、产品码:app/common/model_capabilities.py、产品码:docker-compose.yml、产品码:tests/test_gpu_compute_honesty.py
  - `11f9b1f`（R26a 并树，祖先=是）→ 文书:README.md、产品码:app/common/model_capabilities.py、产品码:docker-compose.yml、产品码:tests/test_gpu_compute_honesty.py
  - `af027ce`（R26b 施工，祖先=是）→ 产品码:app/common/model_config.py、产品码:app/common/monitoring.py、产品码:tests/test_compute_wiring.py
  - `6ee2f79`（R26b 并树，祖先=是）→ 产品码:app/common/model_config.py、产品码:app/common/monitoring.py、产品码:tests/test_compute_wiring.py
- **R27**（PARTIAL）
  - `ce0b041`（施工，祖先=是）→ 产品码:app/agents/orchestrator.py、产品码:tests/test_supervisor_roundtrip.py
  - `6a4f02b`（并树，祖先=是）→ 产品码:app/agents/orchestrator.py、产品码:tests/test_supervisor_roundtrip.py
- **R28**（PARTIAL）
  - `d2566e1`（施工，祖先=是）→ 产品码:.env.example、产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_retrieval_rewrite_tier.py
  - `1c0b08b`（并树，祖先=是）→ 产品码:.env.example、产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_retrieval_rewrite_tier.py
- **R29**（PARTIAL）
  - `62c734d`（施工，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/common/model_budget.py、产品码:app/common/model_handler.py、产品码:tests/test_r29_thinking_tax.py
  - `791568c`（并树，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/common/model_budget.py、产品码:app/common/model_handler.py、产品码:tests/test_r29_thinking_tax.py
- **R30**（LANDED）
  - `3cb563b`（施工，祖先=是）→ 产品码:.env.example、产品码:app/agents/contracts.py、产品码:app/agents/nodes.py、产品码:app/agents/orchestrator.py、产品码:app/agents/tools.py、产品码:app/api/v1/alerts.py、产品码:app/common/model_budget.py、产品码:app/common/model_handler.py、产品码:deploy/.env.server.example、产品码:tests/test_r30_config_defaults.py、产品码:tests/test_r30_context_limit_guard.py、产品码:tests/test_r30_model_tiers.py、产品码:tests/test_r30_timeout_budget.py
  - `50aff1a`（并树，祖先=是）→ 产品码:.env.example、产品码:app/agents/contracts.py、产品码:app/agents/nodes.py、产品码:app/agents/orchestrator.py、产品码:app/agents/tools.py、产品码:app/api/v1/alerts.py、产品码:app/common/model_budget.py、产品码:app/common/model_handler.py、产品码:deploy/.env.server.example、产品码:tests/test_error_code_vocabulary.py、产品码:tests/test_r30_config_defaults.py、产品码:tests/test_r30_context_limit_guard.py、产品码:tests/test_r30_model_tiers.py、产品码:tests/test_r30_timeout_budget.py
- **R31**（PARTIAL）
  - `a7cd9b6`（施工，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/agents/orchestrator.py、产品码:tests/test_r31_generation_stream_passthrough.py、产品码:tests/test_r31_stream_pieces.py
  - `eef642b`（并树，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/agents/orchestrator.py、产品码:tests/test_r31_generation_stream_passthrough.py、产品码:tests/test_r31_stream_pieces.py
- **R32**（LANDED）
  - `0cfd86a`（施工，祖先=是）→ 产品码:app/api/v1/chat.py、契约:docs/api/contract-v1.md、产品码:tests/test_error_code_vocabulary.py、产品码:tests/test_r32_lane_contract.py
  - `8a91f4e`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、契约:docs/api/contract-v1.md、产品码:tests/test_error_code_vocabulary.py、产品码:tests/test_r32_lane_contract.py
- **R33**（LANDED）
  - `b35e10f`（施工，祖先=是）→ 产品码:app/agents/orchestrator.py、产品码:app/memory/__init__.py、产品码:app/memory/summarizer.py、产品码:tests/test_r33_history_guardrails.py、产品码:tests/test_r33_zero_model_compression.py
  - `9678d21`（并树，祖先=是）→ 产品码:app/agents/orchestrator.py、产品码:app/memory/__init__.py、产品码:app/memory/summarizer.py、产品码:tests/test_r33_history_guardrails.py、产品码:tests/test_r33_zero_model_compression.py
- **R34**（LANDED）
  - `b1d185e`（施工，祖先=是）→ 产品码:app/common/model_config.py、产品码:app/common/model_handler.py、文书:docs/handoff/2026-09-19-r34-keep-alive-residency.md、产品码:tests/test_r34_keep_alive_residency.py
  - `e4d0c1b`（并树，祖先=是）→ 产品码:app/common/model_config.py、产品码:app/common/model_handler.py、文书:docs/handoff/2026-09-19-r34-keep-alive-residency.md、产品码:tests/test_r34_keep_alive_residency.py
- **R35**（PARTIAL）
  - `63651f1`（施工，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/common/cache.py、产品码:tests/test_answer_cache_scope.py、产品码:tests/test_chat_cache_safety.py、产品码:tests/test_phase7_signal_line.py、产品码:tests/test_trace_orchestration.py
  - `90d029f`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/common/cache.py、产品码:tests/test_answer_cache_scope.py、产品码:tests/test_chat_cache_safety.py、产品码:tests/test_phase7_signal_line.py、产品码:tests/test_trace_orchestration.py
- **R36**（LANDED）
  - `ef3d193`（施工，祖先=是）→ 产品码:tests/fixtures/business_evaluation_100.jsonl、产品码:tests/test_evaluation_report.py
  - `ac44d00`（并树，祖先=是）→ 产品码:tests/fixtures/business_evaluation_100.jsonl、产品码:tests/test_evaluation_report.py
- **R37**（PARTIAL）
  - `45b9720`（worker 半程，祖先=是）→ 产品码:deploy/queue_worker.py、产品码:tests/test_r37_report_lane_worker.py
  - `0c08209`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:deploy/queue_worker.py、产品码:tests/test_r37_report_lane_enqueue.py、产品码:tests/test_r37_report_lane_worker.py
- **R38**（PARTIAL）
  - `c81fbb5`（施工，祖先=是）→ 产品码:app/common/model_handler.py、产品码:app/trace/spans.py、契约:docs/api/contract-v1.md、产品码:tests/test_r38_cached_tokens_honesty.py、产品码:tests/test_r38_native_input_tokens.py
  - `2e6abc6`（并树，祖先=是）→ 产品码:app/common/model_handler.py、产品码:app/trace/spans.py、契约:docs/api/contract-v1.md、产品码:tests/test_r38_cached_tokens_honesty.py、产品码:tests/test_r38_native_input_tokens.py
- **R40**（PARTIAL）
  - `dc31a44`（施工，祖先=是）→ 产品码:app/api/v1/intelligence.py、产品码:app/approval/assistant.py、产品码:app/common/authorization.py、产品码:tests/test_approval_precheck_standard_source.py
  - `8585315`（并树，祖先=是）→ 产品码:app/api/v1/intelligence.py、产品码:app/approval/assistant.py、产品码:app/common/authorization.py、产品码:tests/test_approval_precheck_standard_source.py
- **R41**（LANDED）
  - `e8d3200`（施工，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:tests/test_sse_sources.py
  - `571e0d6`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:tests/test_sse_sources.py
- **R42**（LANDED）
  - `5ff93cd`（施工，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/agents/orchestrator.py、产品码:tests/test_r42_fallback_upgrade.py、产品码:tests/test_r42_lane_ratio.py、产品码:tests/test_r42_lane_rules.py、产品码:tests/test_r42_numeric_questions.py、产品码:tests/test_r42_zero_model_calls.py
  - `89965d5`（并树，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/agents/orchestrator.py、产品码:tests/test_r42_fallback_upgrade.py、产品码:tests/test_r42_lane_ratio.py、产品码:tests/test_r42_lane_rules.py、产品码:tests/test_r42_numeric_questions.py、产品码:tests/test_r42_zero_model_calls.py
- **R43**（PARTIAL）
  - `4586bb4`（R43a 并树，祖先=是）→ 产品码:app/common/model_handler.py、产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_r43a_native_cached_tokens.py、产品码:tests/test_r43a_rewrite_prefix_reuse.py
  - `839c344`（R43b＝R167 并树，祖先=是）→ 产品码:tests/test_r167_answer_prefix_reuse.py
- **R44**（PARTIAL）
  - `9940c13`（施工，祖先=是）→ 产品码:app/rag/hot_index.py、产品码:app/rag/retriever.py、产品码:tests/test_r44_hot_index_chroma.py、产品码:tests/test_r44_hot_index_coverage.py、产品码:tests/test_r44_hot_index_unit.py
  - `39006b8`（并树，祖先=是）→ 产品码:app/rag/hot_index.py、产品码:app/rag/retriever.py、产品码:tests/test_r44_hot_index_chroma.py、产品码:tests/test_r44_hot_index_coverage.py、产品码:tests/test_r44_hot_index_unit.py
  - `564340e`（总控热修，祖先=是）→ 产品码:app/rag/hot_index.py、产品码:app/rag/retriever.py、产品码:tests/test_r44_hot_index_coverage.py、产品码:tests/test_r44_hot_index_paging.py
- **R45**（LANDED）
  - `0276f78`（施工，祖先=是）→ 产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_prefiltering.py
  - `640ef08`（并树，祖先=是）→ 产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_prefiltering.py
- **R46**（PARTIAL）
  - `c29ccf5`（R152 施工（后端半张），祖先=是）→ 产品码:app/api/v1/feedback.py、产品码:app/main.py、产品码:app/rag/retriever.py、产品码:migrations/0011_document_activity_signals.sql、契约:migrations/manifest.json、产品码:tests/test_document_catalog_sync.py、产品码:tests/test_r120_clean_install_first_boot.py、产品码:tests/test_r46_activity_signals.py
  - `eaa9af8`（R152 并树，祖先=是）→ 产品码:app/api/v1/feedback.py、产品码:app/main.py、产品码:app/rag/retriever.py、产品码:migrations/0011_document_activity_signals.sql、契约:migrations/manifest.json、产品码:tests/test_document_catalog_sync.py、产品码:tests/test_r120_clean_install_first_boot.py、产品码:tests/test_r134_chroma_writeback.py、产品码:tests/test_r46_activity_signals.py
  - `484536c`（R195 并树（消费侧），祖先=是）→ 产品码:frontend/src/components/SourceCard.vue、产品码:frontend/src/components/__tests__/r195-source-feedback.test.js、产品码:frontend/src/lib/__tests__/feedback.test.js、产品码:frontend/src/lib/feedback.js
- **R47**（PARTIAL）
  - `95a1cd9`（施工，祖先=是）→ 产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_retrieval_synonym_expansion.py
  - `006c613`（并树，祖先=是）→ 产品码:app/rag/retrieval_pipeline.py、产品码:tests/test_retrieval_synonym_expansion.py
- **R48**（PARTIAL）
  - `0ad3d3e`（并树 R48 路线甲，祖先=是）→ 产品码:app/api/v1/chat.py、契约:docs/api/contract-v1.md、产品码:frontend/src/components/AnswerHeadlineCard.vue、产品码:frontend/src/components/ChatPanel.vue、产品码:frontend/src/components/__tests__/r48-headline-card.test.js、产品码:frontend/src/lib/sessions.js、产品码:tests/test_r48_headline_card_lands_on_the_wire.py、产品码:tests/test_r48_headline_never_enters_the_text_ledger.py
- **R49**（PARTIAL）
  - `8680f43`（施工，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/documents/catalog.py、产品码:app/documents/index_policy.py、产品码:tests/test_r49_corpus_calibration.py、产品码:tests/test_r49_index_policy_rules.py、产品码:tests/test_r49_upload_contract.py
  - `c26afda`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/documents/catalog.py、产品码:app/documents/index_policy.py、产品码:tests/test_r49_corpus_calibration.py、产品码:tests/test_r49_index_policy_rules.py、产品码:tests/test_r49_upload_contract.py
- **R50**（PARTIAL）
  - `090c820`（施工，祖先=是）→ 产品码:app/rag/indexing.py、产品码:scripts/rebuild_index.py、产品码:tests/test_r50_incremental_index.py、产品码:tests/test_r50_resumable_rebuild.py
  - `94f7fa1`（并树，祖先=是）→ 产品码:app/rag/indexing.py、产品码:scripts/rebuild_index.py、产品码:tests/test_r50_incremental_index.py、产品码:tests/test_r50_resumable_rebuild.py
- **R51**（PARTIAL）
  - `6833140`（施工，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/api/v1/auth.py、产品码:app/api/v1/observability.py、产品码:app/common/performance.py、产品码:app/common/stage_timing.py、产品码:app/trace/spans.py、产品码:app/trace/store.py、产品码:tests/test_r51_observation_is_passive.py、产品码:tests/test_r51_stage_latency.py
  - `cef08bf`（并树，祖先=是）→ 产品码:app/agents/nodes.py、产品码:app/api/v1/auth.py、产品码:app/api/v1/observability.py、产品码:app/common/performance.py、产品码:app/common/stage_timing.py、产品码:app/trace/spans.py、产品码:app/trace/store.py、产品码:tests/test_r51_observation_is_passive.py、产品码:tests/test_r51_stage_latency.py
- **R52**（PARTIAL）
  - `8c888c7`（施工，祖先=是）→ 产品码:deploy/README.server.md、产品码:deploy/docker-compose.tls.yml、产品码:deploy/nginx.https.conf.example、文书:docs/handoff/2026-09-15-backend-followup-requests.md、文书:docs/handoff/2026-09-17-eval-real-run-runbook.md、文书:docs/handoff/2026-09-17-human-gates.md、产品码:scripts/check_airgap_readiness.py、产品码:scripts/check_image_provenance.py、产品码:scripts/provision_bulk_accounts.py、产品码:tests/test_r52_airgap_readiness.py、产品码:tests/test_r96_image_provenance.py
  - `1b84fb2`（闸门自修，祖先=是）→ 产品码:scripts/check_airgap_readiness.py、产品码:tests/test_r52_airgap_readiness.py
- **R141**（LANDED）
  - `1cbd164`（并树，祖先=是）→ 契约:docs/api/contract-v1.md、产品码:frontend/src/components/__tests__/r141-lane-picker.test.js、产品码:frontend/src/router/__tests__/r141-lane-choice.test.js、产品码:frontend/src/router/lane-choice.js、产品码:tests/test_r141_lane_behavior.py、产品码:tests/test_r32_lane_contract.py
- **R142**（LANDED）
  - `19761a5`（施工，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/api/v1/observability.py、契约:docs/api/contract-v1.md、产品码:tests/test_error_code_vocabulary.py、产品码:tests/test_r142_error_code_table_sync.py
  - `b58a5b9`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/api/v1/observability.py、契约:docs/api/contract-v1.md、产品码:tests/test_error_code_vocabulary.py、产品码:tests/test_r142_error_code_table_sync.py
- **R145**（LANDED）
  - `e2de245`（施工，祖先=是）→ 产品码:scripts/audit_vector_mirror_sets.py、产品码:tests/test_r145_vector_mirror_set_audit_is_read_only.py、产品码:tests/test_r145_vector_mirror_set_audit_reads.py
  - `f747109`（并树，祖先=是）→ 产品码:scripts/audit_vector_mirror_sets.py、产品码:tests/test_r145_vector_mirror_set_audit_is_read_only.py、产品码:tests/test_r145_vector_mirror_set_audit_reads.py
- **R146**（LANDED）
  - `77cd8b4`（施工，祖先=是）→ 产品码:app/trace/spans.py、产品码:tests/test_r146_cached_token_ledger.py
  - `25a08f0`（并树，祖先=是）→ 产品码:app/trace/spans.py、产品码:tests/test_r146_cached_token_ledger.py
- **R253**（PARTIAL）
  - `ea2a539`（并树，祖先=是）→ 产品码:tests/_temp_edit_overlay.py、产品码:tests/test_r156_sse_event_surface_sync.py、产品码:tests/test_r253_no_test_rewrites_a_tracked_file.py、产品码:tests/test_r253_shadow_root_holds_the_mutation.py、产品码:tests/test_r48_headline_card_lands_on_the_wire.py、产品码:tests/test_r48_headline_never_enters_the_text_ledger.py
- **R254**（LANDED）
  - `8f89def`（并树，祖先=是）→ 产品码:app/api/v1/chat.py、产品码:app/common/reliable_queue.py、产品码:deploy/queue_worker.py、契约:docs/api/contract-v1.md、产品码:tests/test_r154_provenance_surface.py、产品码:tests/test_r227_discard_is_honest.py、产品码:tests/test_r254_queue_terminal_honesty.py、产品码:tests/test_r254_sync_lane_terminal.py、产品码:tests/test_r37_report_lane_enqueue.py、产品码:tests/test_r37_report_lane_worker.py、产品码:tests/test_reliable_queue_status_api.py
  - `c70548a`（R254b 总控补口，祖先=是）→ 产品码:tests/test_agent_result_records.py、产品码:tests/test_r238_bare_connect_ratchet.py
- **R255**（LANDED）
  - `3bf271d`（并树，祖先=是）→ 产品码:.env.example、产品码:app/agents/contracts.py、产品码:app/common/model_budget.py、产品码:tests/test_r255_answer_floor_is_not_a_window_knob.py、产品码:tests/test_r255_env_documents_the_conversion.py、产品码:tests/test_r255_refusal_says_the_parameters_are_small.py、产品码:tests/test_r255_window_and_budget_derive_together.py
- **R256**（LANDED）
  - `ff0f4ec`（并树，祖先=是）→ 产品码:.env.example、文书:README.md、产品码:app/storage/datasets.py、产品码:app/storage/persistence.py、产品码:migrations/0015_dataset_version_scope_columns.sql、契约:migrations/manifest.json、产品码:tests/test_document_catalog_sync.py、产品码:tests/test_r120_clean_install_first_boot.py、产品码:tests/test_r183_184_migration_pair.py、产品码:tests/test_r190_status_failed_domain.py、产品码:tests/test_r248_artifact_column_alignment.py、产品码:tests/test_r249_dataset_scope_faces.py、产品码:tests/test_r249_dataset_table_columns.py、产品码:tests/test_r251_alert_disposal_migration.py、产品码:tests/test_r256_artifact_deleted_at_lands.py、产品码:tests/test_r256_dataset_version_scope.py、产品码:tests/test_r256_migration_scanners.py、产品码:tests/test_r256_persistence_backend_default.py、产品码:tests/test_r256_pg_migration_acceptance.py、产品码:tests/test_r46_activity_signals.py
  - `d853153`（R256b 总控补口，祖先=是）→ 产品码:tests/test_r238_bare_connect_ratchet.py
- **R258**（LANDED）
  - `6b4f04c`（总控自办，祖先=是）→ 文书:docs/handoff/2026-09-17-eval-real-run-runbook.md

## 3. 欠账与判据原文（机器从出处逐字切段，非转述）

- G-R25-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 497 行（按 LF 计数）｜PARTIAL ｜原文：改一行 `app/**` 后不 build 即生效；`verify_container_stack.py --skip-build` 仍能过
- G-R26-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 498 行（按 LF 计数）｜PARTIAL ｜原文：① 容器内 `nvidia-smi` 有卡
- G-R27-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 499 行（按 LF 计数）｜PARTIAL ｜原文：③ 端到端 −≥35 s
- G-R28-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 500 行（按 LF 计数）｜PARTIAL ｜原文：③ 30 题评测不退化
- G-R29-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 501 行（按 LF 计数）｜PARTIAL ｜原文：② 生成轮 30.6 s → ≤22 s
- G-R31-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 503 行（按 LF 计数）｜PARTIAL ｜原文：② **片段时间戳不重叠、逐字比对无缺字**
- G-R35-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 507 行（按 LF 计数）｜PARTIAL ｜原文：② **跨部门/跨密级命中 0 条**（P0）
- G-R37-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 509 行（按 LF 计数）｜PARTIAL ｜原文：③ 队列失败有终态与原因码
- G-R38-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 510 行（按 LF 计数）｜PARTIAL ｜原文：抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致
- G-R39-1 ｜出处：计划书 §5.2 主表行（一句话列） ｜`docs/handoff/2026-09-17-perf-architecture-plan.md` 第 189 行（按 LF 计数）｜ZERO ｜原文：**不建**，沿用 R17（裁定 5 = 甲）
- G-R39-2 ｜出处：跟进单 §21 裁定 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 491 行（按 LF 计数）｜ZERO ｜原文：每单的**判据与禁改边界**以本节为准。**R39 不建，沿用 R17**（裁定=甲）。
- G-R40-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 511 行（按 LF 计数）｜PARTIAL ｜原文：③ 不再出现前端 `standard: 500` 硬编
- G-R43-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 514 行（按 LF 计数）｜PARTIAL ｜原文：② E3 档实测 `cached_tokens > 0`
- G-R44-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 515 行（按 LF 计数）｜PARTIAL ｜原文：① 覆盖 95% 查询的热集常驻
- G-R46-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 517 行（按 LF 计数）｜PARTIAL ｜原文：① 有信号后排序变化可测
- G-R47-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 518 行（按 LF 计数）｜PARTIAL ｜原文：① 同义词题命中改进
- G-R48-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 519 行（按 LF 计数）｜PARTIAL ｜原文：① 首屏 ≤1 s 有可用结论
- G-R49-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 520 行（按 LF 计数）｜PARTIAL ｜原文：② 被排除文档在 UI 可见为"未索引"
- G-R50-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 521 行（按 LF 计数）｜PARTIAL ｜原文：② 全量重建可中断续跑
- G-R51-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 522 行（按 LF 计数）｜PARTIAL ｜原文：② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%）
- G-R52-1 ｜出处：跟进单 §21 判据表 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 523 行（按 LF 计数）｜PARTIAL ｜原文：① 断网可装可跑
- G-R143-1 ｜出处：计划书 §5.2 行（状态列） ｜`docs/handoff/2026-09-17-perf-architecture-plan.md` 第 330 行（按 LF 计数）｜ZERO ｜原文：待派 🔴 R29 并树这一半锁已解（`791568c`），仍要**非跑分窗口 + 机器空闲**（要 embed ⇒ 打 Ollama）；集合面那一半已拆 R145 先做，其结论即本单开场
- G-R144-1 ｜出处：跟进单 §85 · 一 ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 2137 行（按 LF 计数）｜ZERO ｜原文：- **一、工单来源与性质**：业主亲派，原文 `C:\Users\fengx\PycharmProjects\_peer-starter\handoff\workorder-bg-font-2026-09-21.md`（配套 CSS 提案 `bg-layer-plan-2026-09-21.md` T1/T2）。🔴 **定性＝接线收尾，不是新建背景系统**：五层脚手架早在 `theme.css:1164-1222`，`1191` 那行美术图被注释掉，DOM 侧 `App.vue:212-217` 已就位——所以本单**不许另起炉灶**，实测也确认新增只有 `.app-bg*` 一段与 `App.vue` 四行 div。工单号自定 R148（业主明令避开 R141–R144，那四个是他给的建议号，已被 R141/R142/R143 后端件占掉）。
- G-R253-1 ｜出处：跟进单 §101 · 二（已结案三枚的对账口径） ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 3344 行（按 LF 计数）｜PARTIAL ｜原文：- **R253 `ea2a539`**：反证钉变异只落影子副本，不再就地改写被跟踪文件。🔴 「同一 HEAD 连跑三次 `-n 8` 零漂移」仍未满：`c70548a` 5218/44 一枚、`d853153` 5260/49 一枚。
- G-R257-1 ｜出处：跟进单 §101 · 一（新立单判据原文） ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 3340 行（按 LF 计数）｜ZERO ｜原文：**R257 Trace 兜底两笔**（波次二，施工 `Confucius`@`be-r257`，基点 `c70548a`；写域只 `app/trace/**` ＋ 新钉件；🚫 `docs/**`／`migrations/**`／`chat.py`／`docker-compose.yml`）。甲＝兜底行幂等回填六表；乙＝明说永不回填并把话写到面上（`docs/testing/r59c-window-ops-2026-09-25.md:289` 到今天还把只含兜底行的那卷 jsonl 标成「总账」）。承重两枚不许动：`app/trace/store.py:18-21` sequence 取 `MAX(sequence)`、`:22-24` projection 永不半成功。邻居四枚（`test_r250_local_fallback_is_named`／`test_r250_run_terminal_status_honesty`／`test_postgres_execution_persistence`／`test_redis_worker_recovery`）逐枚复跑，不许放宽。
- G-R259-1 ｜出处：跟进单 §101 · 一（R259 判据原文） ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 3323 行（按 LF 计数）｜ZERO ｜原文：- ① 量具见到 `awaiting_approval` 就**停表**：既不许计成 `queued_stalled`，也不许把挂起的轮当「答完了」记分。🔴 停表条件必须写成 `if status == "awaiting_approval":` 的字面比较——`adapter_stop_vocabulary` 那枚钉用 AST 认字面量，改成查表＝假绿。
- G-R260-1 ｜出处：跟进单 §101 · 一（R260 判据原文） ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 3330 行（按 LF 计数）｜ZERO ｜原文：- ① `frontend/src/components/ChatPanel.vue:852` 的 `const QUEUE_SETTLED = [...]` 必须**仍是数组字面量**——`frontend/src/components/__tests__/r221-queue-deadline.test.js:206` 用正则钉这个形状，改成 `new Set()` 或引用常量＝假绿。消费点在 `:1073` `if (QUEUE_SETTLED.includes(read.status)) stop()`。
- G-R261-1 ｜出处：跟进单 §101 · 一（R261 判据原文） ｜`docs/handoff/2026-09-15-backend-followup-requests.md` 第 3337 行（按 LF 计数）｜ZERO ｜原文：- 判据六条：① 在站点上方插无关行 ⇒ 不咬；② 新增一枚裸 connect ⇒ 仍咬；③ 把已入册站点迁走 ⇒ 仍咬（要求删账）；④ 换皮不改强度：`psycopg.connect`／`psycopg2.connect`／模块别名／`**kwargs` 四形都要被同一条规则逮住；⑤ 记账仍一眼可读（路径可查，不许退化成匿名哈希表）；⑥ 反证自证：身份口径若退化成 path-only，必须让某枚咬合钉红。

## 4. 计划书 §5.2 那行现在的台账词（只列在册行，订正由人写段落笔）

- R141 ｜台账现词：🟢 **已并树 `1cbd164`**（R262 机器账复核：该枚提交实改 6 枚产物文件）｜当时的排队条件（历史）：🔴 锁只剩一道：R29 已并树 `791568c`，剩 R31（`Laplace` 正在写 `nodes.py`+`orchestrator.py`）；仍须在 run6 之前定案。R32 已按假控件禁令拒交选择器，本单不许上「选了不改变任何东西」的控件；🔴 前端半张随业主计划走，业主计划未交前 `frontend/**` 全封
- R142 ｜台账现词：🟢 **已并树 `b58a5b9`**（施工 `19761a5`；R262 机器账：5 枚产物文件；判据 §73 四）｜历史派工：`Hooke`/`01a0c167` @`be-r32` 14:3x 复用派
- R143 ｜台账现词：待派 🔴 R29 并树这一半锁已解（`791568c`），仍要**非跑分窗口 + 机器空闲**（要 embed ⇒ 打 Ollama）；集合面那一半已拆 R145 先做，其结论即本单开场
- R145 ｜台账现词：🟢 **已并树 `f747109`**（施工 `e2de245`；R262 机器账：3 枚产物文件；判据 §73 四）｜历史派工：`Chandrasekhar`/`01a0c18c` @`be-r76` 14:3x 复用派
- R146 ｜台账现词：🟢 **已并树 `25a08f0`**（施工 `77cd8b4`；R262 机器账：2 枚产物文件）｜历史派工：`Erdos`/`01a0bf41` @`be-r119` 14:5x 复用派，判据 §74 二；本单结论是 **R43 判据② 订正**的直接输入，不许为凑数写 0
- 其余在册号在 §5.2 主表里没有状态列——计划书 L468 自己认了这句：这张表**没有结案列**，被抄来抄去会被当成还剩这么多没做

## 5. 反查：主干自动归集（专治「零提交」假账）

- R25 ｜自号产物提交：`ad85821`(1 枚产品文件)、`b17b4dd`(1 枚产品文件) ｜追平/保活（不作证据）：—
- R26 ｜自号产物提交：`118801e`/a(3 枚产品文件)、`11f9b1f`/a(3 枚产品文件)、`6ee2f79`/b(3 枚产品文件)、`af027ce`/b(3 枚产品文件) ｜追平/保活（不作证据）：—
- R27 ｜自号产物提交：`29665da`(1 枚产品文件)、`6a4f02b`(2 枚产品文件)、`9318718`(1 枚产品文件)、`ce0b041`(2 枚产品文件) ｜追平/保活（不作证据）：—
- R28 ｜自号产物提交：`1c0b08b`(3 枚产品文件)、`d2566e1`(3 枚产品文件) ｜追平/保活（不作证据）：—
- R29 ｜自号产物提交：`62c734d`(4 枚产品文件)、`791568c`(4 枚产品文件) ｜追平/保活（不作证据）：—
- R30 ｜自号产物提交：`1eea673`(3 枚产品文件)、`3cb563b`(13 枚产品文件)、`50aff1a`(14 枚产品文件)、`d563007`(1 枚产品文件) ｜追平/保活（不作证据）：`fd546f4`
- R31 ｜自号产物提交：`a7cd9b6`(4 枚产品文件)、`eef642b`(4 枚产品文件) ｜追平/保活（不作证据）：—
- R32 ｜自号产物提交：`0cfd86a`(4 枚产品文件)、`8a91f4e`(4 枚产品文件) ｜追平/保活（不作证据）：—
- R33 ｜自号产物提交：`9678d21`(5 枚产品文件)、`9cdbef2`(1 枚产品文件)、`b35e10f`(5 枚产品文件) ｜追平/保活（不作证据）：—
- R34 ｜自号产物提交：`b1d185e`(3 枚产品文件)、`e4d0c1b`(3 枚产品文件) ｜追平/保活（不作证据）：—
- R35 ｜自号产物提交：`63651f1`(6 枚产品文件)、`90d029f`(6 枚产品文件) ｜追平/保活（不作证据）：—
- R36 ｜自号产物提交：`ac44d00`(2 枚产品文件)、`ef3d193`(2 枚产品文件) ｜追平/保活（不作证据）：—
- R37 ｜自号产物提交：`0c08209`(4 枚产品文件)、`45b9720`(2 枚产品文件) ｜追平/保活（不作证据）：`0770f84`、`2866d91`
- R38 ｜自号产物提交：`2e6abc6`(5 枚产品文件)、`c81fbb5`(5 枚产品文件) ｜追平/保活（不作证据）：—
- R39 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R40 ｜自号产物提交：`8585315`(4 枚产品文件)、`dc31a44`(4 枚产品文件) ｜追平/保活（不作证据）：—
- R41 ｜自号产物提交：`571e0d6`(2 枚产品文件)、`e8d3200`(2 枚产品文件) ｜追平/保活（不作证据）：—
- R42 ｜自号产物提交：`5ff93cd`(7 枚产品文件)、`89965d5`(7 枚产品文件) ｜追平/保活（不作证据）：—
- R43 ｜自号产物提交：`4586bb4`/a(4 枚产品文件) ｜追平/保活（不作证据）：—
- R44 ｜自号产物提交：`39006b8`(5 枚产品文件)、`564340e`/b(4 枚产品文件)、`9940c13`(5 枚产品文件) ｜追平/保活（不作证据）：`0ae3b1e`
- R45 ｜自号产物提交：`0276f78`(2 枚产品文件)、`640ef08`(2 枚产品文件) ｜追平/保活（不作证据）：—
- R46 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R47 ｜自号产物提交：`006c613`(2 枚产品文件)、`95a1cd9`(2 枚产品文件) ｜追平/保活（不作证据）：—
- R48 ｜自号产物提交：`0ad3d3e`(8 枚产品文件)、`efe5461`(1 枚产品文件) ｜追平/保活（不作证据）：—
- R49 ｜自号产物提交：`8680f43`(6 枚产品文件)、`c26afda`(6 枚产品文件) ｜追平/保活（不作证据）：`31d6612`
- R50 ｜自号产物提交：`090c820`(4 枚产品文件)、`94f7fa1`(4 枚产品文件) ｜追平/保活（不作证据）：—
- R51 ｜自号产物提交：`2477522`(1 枚产品文件)、`6833140`(9 枚产品文件)、`cef08bf`(9 枚产品文件) ｜追平/保活（不作证据）：`b3c8b1d`
- R52 ｜自号产物提交：`1b84fb2`(2 枚产品文件)、`8c888c7`(8 枚产品文件) ｜追平/保活（不作证据）：—
- R141 ｜自号产物提交：`1cbd164`(6 枚产品文件) ｜追平/保活（不作证据）：—
- R142 ｜自号产物提交：`19761a5`(5 枚产品文件)、`b58a5b9`(5 枚产品文件) ｜追平/保活（不作证据）：—
- R143 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R144 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R145 ｜自号产物提交：`e2de245`(3 枚产品文件)、`f747109`(3 枚产品文件) ｜追平/保活（不作证据）：—
- R146 ｜自号产物提交：`143bac8`(1 枚产品文件)、`25a08f0`(2 枚产品文件)、`77cd8b4`(2 枚产品文件) ｜追平/保活（不作证据）：—
- R253 ｜自号产物提交：`ea2a539`(6 枚产品文件) ｜追平/保活（不作证据）：—
- R254 ｜自号产物提交：`8f89def`(11 枚产品文件)、`c70548a`/b(2 枚产品文件) ｜追平/保活（不作证据）：—
- R255 ｜自号产物提交：`3bf271d`(7 枚产品文件) ｜追平/保活（不作证据）：—
- R256 ｜自号产物提交：`d853153`/b(1 枚产品文件)、`ff0f4ec`(19 枚产品文件) ｜追平/保活（不作证据）：—
- R257 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R258 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R259 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R260 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—
- R261 ｜自号产物提交：0 枚 ｜追平/保活（不作证据）：—

## 6. 计数

在册 43 号：LANDED=16 · PARTIAL=20 · ZERO=7
- LANDED：R30 R32 R33 R34 R36 R41 R42 R45 R141 R142 R145 R146 R254 R255 R256 R258
- PARTIAL：R25 R26 R27 R28 R29 R31 R35 R37 R38 R40 R43 R44 R46 R47 R48 R49 R50 R51 R52 R253
- ZERO：R39 R143 R144 R257 R259 R260 R261

## 7. V1 判据「计划书代码单清零」的距离

- 读法甲（产物在树即算清）：未清 7 号：R39 R143 R144 R257 R259 R260 R261
- 读法乙（判据全达才算清）：未清 27 号（PARTIAL 20 ＋ ZERO 7）
  - R25（PARTIAL）差：改一行 `app/**` 后不 build 即生效；`verify_container_stack.py --skip-build` 仍能过
  - R26（PARTIAL）差：① 容器内 `nvidia-smi` 有卡
  - R27（PARTIAL）差：③ 端到端 −≥35 s
  - R28（PARTIAL）差：③ 30 题评测不退化
  - R29（PARTIAL）差：② 生成轮 30.6 s → ≤22 s
  - R31（PARTIAL）差：② **片段时间戳不重叠、逐字比对无缺字**
  - R35（PARTIAL）差：② **跨部门/跨密级命中 0 条**（P0）
  - R37（PARTIAL）差：③ 队列失败有终态与原因码
  - R38（PARTIAL）差：抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致
  - R40（PARTIAL）差：③ 不再出现前端 `standard: 500` 硬编
  - R43（PARTIAL）差：② E3 档实测 `cached_tokens > 0`
  - R44（PARTIAL）差：① 覆盖 95% 查询的热集常驻
  - R46（PARTIAL）差：① 有信号后排序变化可测
  - R47（PARTIAL）差：① 同义词题命中改进
  - R48（PARTIAL）差：① 首屏 ≤1 s 有可用结论
  - R49（PARTIAL）差：② 被排除文档在 UI 可见为"未索引"
  - R50（PARTIAL）差：② 全量重建可中断续跑
  - R51（PARTIAL）差：② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%）
  - R52（PARTIAL）差：① 断网可装可跑
  - R253（PARTIAL）差：- **R253 `ea2a539`**：反证钉变异只落影子副本，不再就地改写被跟踪文件。🔴 「同一 HEAD 连跑三次 `-n 8` 零漂移」仍未满：`c70548a` 5218/44 一枚、`d853153` 5260/49 一枚。
  - R39（ZERO）差：**不建**，沿用 R17（裁定 5 = 甲）；每单的**判据与禁改边界**以本节为准。**R39 不建，沿用 R17**（裁定=甲）。
  - R143（ZERO）差：待派 🔴 R29 并树这一半锁已解（`791568c`），仍要**非跑分窗口 + 机器空闲**（要 embed ⇒ 打 Ollama）；集合面那一半已拆 R145 先做，其结论即本单开场
  - R144（ZERO）差：- **一、工单来源与性质**：业主亲派，原文 `C:\Users\fengx\PycharmProjects\_peer-starter\handoff\workorder-bg-font-2026-09-21.md`（配套 CSS 提案 `bg-layer-plan-2026-09-21.md` T1/T2）。🔴 **定性＝接线收尾，不是新建背景系统**：五层脚手架早在 `theme.css:1164-1222`，`1191` 那行美术图被注释掉，DOM 侧 `App.vue:212-217` 已就位——所以本单**不许另起炉灶**，实测也确认新增只有 `.app-bg*` 一段与 `App.vue` 四行 div。工单号自定 R148（业主明令避开 R141–R144，那四个是他给的建议号，已被 R141/R142/R143 后端件占掉）。
  - R257（ZERO）差：**R257 Trace 兜底两笔**（波次二，施工 `Confucius`@`be-r257`，基点 `c70548a`；写域只 `app/trace/**` ＋ 新钉件；🚫 `docs/**`／`migrations/**`／`chat.py`／`docker-compose.yml`）。甲＝兜底行幂等回填六表；乙＝明说永不回填并把话写到面上（`docs/testing/r59c-window-ops-2026-09-25.md:289` 到今天还把只含兜底行的那卷 jsonl 标成「总账」）。承重两枚不许动：`app/trace/store.py:18-21` sequence 取 `MAX(sequence)`、`:22-24` projection 永不半成功。邻居四枚（`test_r250_local_fallback_is_named`／`test_r250_run_terminal_status_honesty`／`test_postgres_execution_persistence`／`test_redis_worker_recovery`）逐枚复跑，不许放宽。
  - R259（ZERO）差：- ① 量具见到 `awaiting_approval` 就**停表**：既不许计成 `queued_stalled`，也不许把挂起的轮当「答完了」记分。🔴 停表条件必须写成 `if status == "awaiting_approval":` 的字面比较——`adapter_stop_vocabulary` 那枚钉用 AST 认字面量，改成查表＝假绿。
  - R260（ZERO）差：- ① `frontend/src/components/ChatPanel.vue:852` 的 `const QUEUE_SETTLED = [...]` 必须**仍是数组字面量**——`frontend/src/components/__tests__/r221-queue-deadline.test.js:206` 用正则钉这个形状，改成 `new Set()` 或引用常量＝假绿。消费点在 `:1073` `if (QUEUE_SETTLED.includes(read.status)) stop()`。
  - R261（ZERO）差：- 判据六条：① 在站点上方插无关行 ⇒ 不咬；② 新增一枚裸 connect ⇒ 仍咬；③ 把已入册站点迁走 ⇒ 仍咬（要求删账）；④ 换皮不改强度：`psycopg.connect`／`psycopg2.connect`／模块别名／`**kwargs` 四形都要被同一条规则逮住；⑤ 记账仍一眼可读（路径可查，不许退化成匿名哈希表）；⑥ 反证自证：身份口径若退化成 path-only，必须让某枚咬合钉红。

## 8. 自检（这台尺子的牙）

C1 判定词只许三档；C2 证据提交必须存在；C3 判 LANDED 的证据必须在 HEAD 祖先链上；C4 提交信息必须含本单号；C5 点名落点必须在该提交实改文件里；C6 LANDED 必须有产品码/契约改动；C7 PARTIAL 必须有产物；C8 PARTIAL 必须逐字点名欠账；C9 ZERO 不得被自动归集逮到产物；C10 ZERO 不得挂产物提交

RESULT=PASS（0 条违规，在册 43 号逐条自证）
```


---

## 4. 人写结论（以下不是机器产出，逐条给可复跑命令）

### 4.1 上一格点名的六枚，逐枚复核

派工词给的六枚 sha 只当起点，逐枚自己复跑 `git show -s --format='%h|%p|%s' <sha>` ＋ `git show --numstat --format= -m --first-parent <sha>`：

| 号 | 派工词给的 sha | 复核结果 | 本账判定 |
|---|---|---|---|
| R29 | `791568c` | 真·并树提交（父 `c770f1f 62c734d`）·实改 4 枚产品文件：`app/agents/nodes.py`、`app/common/model_budget.py`、`app/common/model_handler.py`、`tests/test_r29_thinking_tax.py`(+1079)·HEAD 祖先＝是 | 记它「零提交」＝**假账**；号本身 **PARTIAL**（欠 §21 ②） |
| R31 | `eef642b` | 真·并树（父 `25a08f0 a7cd9b6`）·4 枚产品文件（`nodes.py`＋230、`orchestrator.py`＋14、两枚 r31 测试件）·祖先＝是 | 同上，**假账**；号 **PARTIAL**（欠 ②） |
| R32 | `8a91f4e` | 真·并树（父 `546a93b 0cfd86a`）·`app/api/v1/chat.py`＋47、**契约** `docs/api/contract-v1.md`、两枚测试件·祖先＝是 | **假账**；号 **LANDED** |
| R33 | `9678d21` | 真·并树（父 `aaafdc9 b35e10f`）·5 枚产品文件（`orchestrator.py`、`app/memory/__init__.py`、`summarizer.py`、两枚 r33 件）·祖先＝是 | **假账**；号 **LANDED** |
| R43 | `839c344` | 提交**存在**、是 HEAD 祖先，但标题是「并树 **R167 = R43b**」，实改**只有 1 枚**：`tests/test_r167_answer_prefix_reuse.py`(+715)，交付结论是「本写域可挪字节 = 0」 | **单号错位＝引用假账**：这枚不是 R43 的产物。R43 的真产物在 **`4586bb4`（R43a）** 名下（`app/common/model_handler.py`、`app/rag/retrieval_pipeline.py` ＋ 两枚 r43a 测试件）；号 **PARTIAL**（欠 ②） |
| R48 | `0ad3d3e` | 真·并树（父 `d34bfbc`，非 merge＝总控代提交）·8 枚产物文件：`app/api/v1/chat.py`、契约、4 枚前端（含 `AnswerHeadlineCard.vue`）、2 枚 r48 测试件·祖先＝是 | **假账**；号 **PARTIAL**（欠 ①） |

⇒ 六枚里 **五枚** 是「早已并树却被记进零提交名单」，第六枚（R43）是**单号错位**：它自己的号（R43b/R167）不假，假的是把它算成 R43 的产物。

### 4.2 `af4c22e` / `40e6789` 两枚引用验真 ⇒ **引用假账（sha 不存在）**

```
git cat-file -t af4c22e   → fatal: Not a valid object name 'af4c22e'
git cat-file -t 40e6789   → fatal: Not a valid object name '40e6789'
git rev-parse --disambiguate=af4c22e / =40e6789 → 空（没有任何前缀匹配的对象）
rg -a 'af4c22e|40e6789' docs → 仅命中派工词自己那一行（跟进单 §101.4 的 R262 派工记录），无第二处出处
```

两枚 sha 在本仓**根本不存在**，也就谈不上「含不含该号产物」。它们指向的真事另有凭据，账已改挂真 sha：

- **R38**（计量列不再写零）：施工 `c81fbb5` ＋ 并树 `2e6abc6`，实改 `app/common/model_handler.py`、`app/trace/spans.py`、契约、两枚 r38 测试件。
- **R46**（活动信号回填排序）：后端半张在 **R152** 名下（施工 `c29ccf5` ＋ 并树 `eaa9af8`，含 `migrations/0011_document_activity_signals.sql`、`app/api/v1/feedback.py`、`app/rag/retriever.py`、`tests/test_r46_activity_signals.py`）；消费侧在 **R195** 名下（并树 `484536c`，`frontend/src/lib/feedback.js` ＋ `SourceCard.vue` ＋ 两枚测试件）。

⇒ 计划书 L468 那句「真零产物的只有两枚：R46 的消费侧与 R50」**两头都是假话**：R46 消费侧已并树，R50 名下两枚产物提交（`090c820`／`94f7fa1`）也在主干。这是同一类误判的第三次，订正见 §4.3。

### 4.3 本单在计划书里动了哪几处（只订正状态词，判据原文一字未动）

| 位置 | 台账原词 | 改成 | 凭据 |
|---|---|---|---|
| §5.2 续表 R141 行 | `待派 🔴 锁只剩一道…` | 🟢 **已并树 `1cbd164`** ＋ 保留当时排队条件 | 该提交实改 6 枚产物文件；看板 §4BF 记「R141 达标并树」 |
| §5.2 续表 R142 行 | `**在途**：Hooke@be-r32` | 🟢 **已并树 `b58a5b9`**（施工 `19761a5`）＋ 保留「历史」一句 | 5 枚产物文件；`070f087` 记并树 +12 用例 |
| §5.2 续表 R145 行 | `**在途**：Chandrasekhar@be-r76` | 🟢 **已并树 `f747109`**（施工 `e2de245`） | `scripts/audit_vector_mirror_sets.py` ＋ 两枚测试件 |
| §5.2 续表 R146 行 | `**在途**：Erdos@be-r119` | 🟢 **已并树 `25a08f0`**（施工 `77cd8b4`） | `app/trace/spans.py` ＋ `tests/test_r146_cached_token_ledger.py` |
| §5.2 勘误节末 | （追加一行） | 09-26 复算：「真零产物只剩 R46 消费侧与 R50」作废，逐号机器账见本文件 | `scripts/audit_plan_ticket_ledger.py` C9/C10 |
| §6 V1 门槛那句 | （追加一行） | 「计划书代码单清零」自此有机器读数：三档计数 ＋ 复跑命令 | 同上 |

R143 行**没动**——它的「待派」是真的（名下全史零提交），改它反而是造假。R144 也不在 §5.2 里（见 §4.4）。

### 4.4 四处必须如实上报的口径异常

1. **R144 从没立过单**：`rg -a 'R144' docs` 全仓只命中一处，是跟进单 §85 那句「工单号自定 R148（业主明令避开 R141–R144，那四个是他给的建议号，已被 R141/R142/R143 后端件占掉）」。
   ⇒ 派工词的「R141–R146」里含一枚从未启用的号，且 §5.2 表里也没有 R144 行。本账按实列 `ZERO` 并引这句作依据。
2. **R253–R261 不在 §5.2 表内**：§5.2 续表最后一行是 R155（L341）。本波九号的判据原文在跟进单 **§101.1／§101.2**（同一枚文件，另一节）。
   ⇒ 判据② 指定的两出处（§21／§5.2 行内）覆盖不到它们，本账按「同一文件的实际小节」引用，并在此**具名偏离**，不是转述。
3. **本账钉在 `03beca8`，主干已在 `8051897`**：三枚提交不在本 HEAD 祖先链上——`67ea193`（并树 R259）、`c9ad493`（并树 R261）、`8051897`（记账·R253 判据④ 转绿）。
   复跑：`git log --oneline --all --not HEAD`。⇒ 本账把 R259/R261 记 `ZERO`、R253 记 `PARTIAL` **都对，但只对 `03beca8` 这一枚 HEAD 成立**；下班在更新的主干上重跑，这三格会自动翻档；翻不过去就是尺子咬人，不是账要手改。
4. **词汇撞车（请总控定口径，本单不擅自统一）**：§5.2 行里的「已结案」（R44、R51、R64、R65…）表达的是**并树完成**，与本账 `LANDED`（产物在树**且**判据无点名欠账）不同义。
   现例：R51 台账写「已结案 `cef08bf`」，本账判 `PARTIAL`（欠 §21 ②「端到端与分段加总误差 <1%」，结案核对 R224 同判「部分达」）。这类词若也要归真，需要一次跨文档的口径裁定，不该由执行层改字。

### 4.5 一句话结论：V1 判据「计划书代码单清零」现在距达标还差什么

- **按「产物在树」读法（清 0 号）**：还差 **R143**（双写窗 recall 预跑从未跑，记在 R58③ 真机欠账）、**R257**／**R260**（名下全史零提交）、**R259**／**R261**（产物活在主干 `67ea193`／`c9ad493`，本 HEAD 尚未含），共 **5 号**；**R39**（裁定不建）与 **R144**（从未立单）应从清零口径里**豁免**——挂着不豁免，这条 V1 判据永远不可能绿。
- **按「判据全达」读法（LANDED 才算清）**：还差 **27 号**（`PARTIAL` 20 ＋ `ZERO` 7），其中
  - **只欠读数／门**（不需新代码，13 号）：R25 R26 R27 R28 R31 R35 R37 R38 R44 R46 R47 R48 R52；
  - **欠代码或欠裁定**（要动树才能清，6 号）：R29（业主换无思考模型后重量）、R40③（前端 `standard: 500`，写域在 V 线）、R43②（`cached_tokens` 落库缺列 ⇒ 需一枚迁移单）、R49②（「未索引」那张脸）、R50②（低峰重建没挂进排程）、R51②（`rewrite`/`reflect` 插桩＋加总误差）；
  - **名下零产物**（8 号）：R143 R257 R259 R260 R261 ＋ 豁免候选 R39 R144。
  逐号「差哪一条判据」的原文见本文件 §3 机器账第 7 节，一条一格，带出处行号。

### 4.6 本单没做／不敢做的事（免得下班把它当已做完）

- 未跑任何测试、未跑 `scripts/run_gate.py`、未动容器／镜像／模型（总控在跑门，判据④ 明令不许抢）。
- 未 commit、未 add（执行层禁提交，等总控按盘上交付验收）。
- 未碰 `docs/handoff/2026-09-15-orchestration-board.md` 与 `...-backend-followup-requests.md`（总控独占）；本单对跟进单**只读**。
- 未改 `frontend/**`、`app/**`、`tests/**`、`migrations/**`、`README.md`、`.env*`；未宣布任何「V1 完工」。
- 脚本只出账，不写文件：把它接进 CI／门，得由总控决定并自己落钉。