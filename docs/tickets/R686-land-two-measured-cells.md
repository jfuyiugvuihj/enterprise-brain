# R686 · 把 R27③／R37③ 两格已量到的「达」落进账尺（读法乙 11 → 9）

**基点**：开工时现取主树 HEAD 写进交付。**独占工作树**：总控告知路径，不许换树、不许碰主树。

## 为什么有这一单

版本文档 r4 §4 现取：读法乙未清 11 号里有 **2 格其实已经量到达**，只是账没结算——挂着的后果就是业主每班看到「还差 11」，而真实欠账是 9。这不是「凑数把格子翻绿」：两格各有当场可复算的量具与读数代次。

- **R27③「端到端 −≥35 s」**：基线 160.552 s → 问答类 p95 **50.1 s**（降 110.4 s ≥ 35 s），`scripts/r595_latency_readout.py`，run22 与 run23 **两窗互证**，读数代次 `9556513`。
- **R37③「队列失败有终态与原因码」**：R585 已并树 `1f0f0f2`，`fail_or_retry` 真落 dead 那支把 `{reason, retryable}` 排在写状态键**之前**进账；总控 10-05 亲跑在册牙 **99 passed／0 failed／37.39 s**（件＝`tests/test_r585_dead_terminal_reason.py`＋`tests/test_r545_queue_failure_teeth.py`＋`tests/test_r254_queue_terminal_honesty.py`）。八处调用点逐枚点开＝**七枚稳定码＋一枚 `str(e)`**（`deploy/queue_worker.py::_process_reserved` 收尾），那一枚例外已另立 **R675**，不许算进 R37 的欠账，也不许拿它挡判达——**若账尺的 C8／C15 因此咬住，就停下写进交付，由总控改判据，不许硬翻**。

## 判据（每条都可失败，缺一枚判负）

1. `scripts/audit_plan_ticket_ledger.py` 里 R27 与 R37 两行由 `PARTIAL` 改判 `LANDED`，理由句必须带**量具名＋读数＋代次 sha**，不许形容词；其余 41 号**一字不许动**（含五格 `OUT` 与另九格 `PARTIAL`）。
2. 账尺整跑 `RESULT=PASS`（0 条违规），计数变成 LANDED 26／PARTIAL 9／OUT 5／CLOSED 1／FOREIGN 1／NOTBUILT 1／ZERO 0，读法乙未清从 11 变 **9**；把改前／改后两枚计数逐档贴进交付。
3. 🔴 **两把牙必须还在咬**（摘牙＝退回）：C15「取证纸已判达不许仍挂欠账」与 C8「PARTIAL 必须逐字点名欠账」原样保留。新增或复用一枚反证牙：把 R27 改回 `PARTIAL` 却**留着欠账句不点名** ⇒ 尺子必须非零退出并点名那一号。
4. 「达」的依据必须**在仓内可查**：结案纸 `docs/testing/v1-cell-closeout-2026-10-05.md` 里那两行的读数与代次必须能对上；对不上就在交付里写明差哪半句，不许改结案纸来迁就尺子。
5. 派生校验：跑 `tests/test_r640_ledger_tiers_are_derived.py`＋`tests/test_r640_counter_evidence_teeth.py`＋`tests/test_r666_out_of_scope_tier.py` 同名件，改前／改后两遍，**一枚不许新红**。

## 写域

`scripts/audit_plan_ticket_ledger.py`／它自己的用例件（`tests/test_*ledger*`，必要时新增 `tests/test_r686_*`）／`docs/tickets/R686-*.md`／`docs/testing/r686-<今天>.md`（新，凭据纸）

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／`docs/testing/v1-cell-closeout-2026-10-05.md`（只读依据，不许反过来改）／评测夹具与 `tests/test_evaluation_report.py`／`scripts/run_gate.py`／`scripts/r595_latency_readout.py`／`pyproject.toml`／`deploy/.env.server`／`AGENTS.md`／`chroma_db/**`／任何镜像与容器动作／**主树任何路径**。若结论是「非改禁区不可」，停下写进交付。

## 不许做

往主树 commit／建分支／push／起服务／动容器／rebuild 镜像／打真模型／跑全量门。**可以在自己的树里 commit 自己的货**（新规⑦），主树并树仍由总控验收后代提交。夜窗 20:00 起为延迟判据窗：窗内只做零 CPU 争用的活，秒数只作正确性佐证不作延迟判据。

## 交付必须含

1. 三态数：基点干净检出／state① 已 apply 未 commit／state② 干净检出投本单货；同名件清单逐枚相同、总数相同；执行层读数一律标「执行层自报」。
2. 判据 2 的改前／改后逐档计数原文，判据 3 的反证牙红绿两枚读数，判据 5 的两遍数字。
3. 盘面自证（收席那一刻现取）：`rev-list --count <基点>..HEAD`、staged、未跟踪清单逐枚点名、`diff --numstat HEAD`。
4. 坐标一律 `文件::符号`，🔴 禁止 `文件:数字` 形态行号。
5. 写文本一律走字节通道（`git diff --output=<file>`；含反引号或中文的正文走 `Set-Content` 单引号 here-string），写完现读＋扫 `0x00/07/08/0b/0c`＝0＋U+FFFD＝0。

## 重复投递声明

重复送达按一次处理，产物只写同一批文件。