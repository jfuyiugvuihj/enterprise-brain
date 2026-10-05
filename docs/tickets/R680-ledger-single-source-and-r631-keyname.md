# R680 · 账尺改读工单目录 + r631 判据按键名查（病根第二刀·总控裁定·窗后执行）

**基点**：本单开工时现取主树 HEAD（必须在 R666 并树之后，写集含 `scripts/audit_plan_ticket_ledger.py`，与在飞的 Bohr 冲突 ⇒ 现在不许投）。**独占工作树**：由总控预配并告知路径，不许换树、不许碰主树。

## 为什么有这一单

两件事各自都是「两本账 / 手抄坐标」这一族病根的最后两处：

1. **双真源**：`docs/tickets/**`（R679 刚落地的机器可读工单目录）与账尺 `scripts/audit_plan_ticket_ledger.py`（读跟进单＋看板散文）都对「逐号状态」发言。本班会话已推翻四枚过期账（R25②／R29②／R37③／R43②），双真源正是那类误判的放大器。若 `docs/tickets/**` 没有消费方，它就是 write-only 目录——只多一本要钉的账，不减任何成本。
2. **手抄行号**：`scripts/r631_stage_sum_delta.py::CRITERION_LINE_LF` 写死一个 LF 位去跟进单里取判据那一行，同名的 `read_alignment_pct()` 早已改成内容搜索——**正例就在同一枚文件里**。这类坐标漂一次就产出一整枚纯返工单（在册：R660 重锚 46 枚、R646 换 15 枚、R638 棘轮返工、R630/R635 改派生锚）。

## 判据（每条都可失败，缺一枚判负）

1. **账尺以 `docs/tickets/**` 为状态唯一真源**：`scripts/audit_plan_ticket_ledger.py` 的 LANDED／PARTIAL／ZERO／OUT 档计数改为从工单目录派生；跟进单与看板**不再被读成状态来源**（仍可被读作叙事出处与凭据指针）。跑改前／改后两遍，六档计数必须逐档相等或有逐档说明；不等即退回。
2. **反证牙**：把某一枚 `docs/tickets/RNNN.md` 的状态字段改掉（在盘上改、跑完还原）⇒ 账尺必须非零退出并点名那一号；🔴 不许把「此刻盘面脏不脏」写进判据（R496／事故 #96 同族）。
3. **r631 改按键名查**：`CRITERION_LINE_LF` 那枚写死的 LF 位删除，判据行改用文本谓词在跟进单里定位；新加一枚「判据文本全档唯一命中」的针——命中 0 次或 ≥2 次都算红。
4. **钉的形状**：新增校验钉照 `tests/test_r132_contract_followup_sync.py`（只用 `ast`／`re`／`pathlib`、不 import `app`、全离线），单跑秒数写进凭据纸；不许照 `tests/test_r302_*`／`test_r491_*` 那一族抄。
5. **不许碰窗**：夜窗在跑 ⇒ 本单在**无窗空档**执行；窗内硬禁并树、跑测试、动容器、打模型。
6. **成本读数**：给出「每班开工必读字节数」改前／改后两枚实测数（口径＝R679 判据 6），并点名账尺改读后不再读跟进单全文这一事实。

## 写域（只许这些）

`scripts/audit_plan_ticket_ledger.py`／`scripts/r631_stage_sum_delta.py`／`tests/test_r680_*.py`（新）／`docs/tickets/R680-*.md`／`docs/testing/r680-<今天>.md`（新，凭据纸）

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`docs/handoff/**` 正文（只文末追加，前置行号一格不许改）／`docs/api/contract-v1.md`／评测夹具与 `tests/test_evaluation_report.py`／`scripts/run_gate.py`／`pyproject.toml`／`deploy/.env.server`／`AGENTS.md`／任何镜像与容器动作／主树任何路径。

## 不许做

commit／建分支／push／起服务／动容器／rebuild 镜像／打真模型／跑全量门。

## 交付必须含

1. 三态数：基点干净检出／state① 已 apply 未 commit／state② 干净检出投本单货；同名件清单逐枚相同、总数相同；执行层读数标「执行层自报」。
2. 判据 1／2／3／6 的**实际读数**（档位计数、退出码、字节数、单跑秒数），不许形容词。
3. 坐标一律 `文件::符号`，🔴 禁止 `文件:数字` 形态行号。
4. 写文本一律走字节通道（`git diff --output=<file>`；含反引号或中文的正文走单引号 here-string），写完现读＋扫 `0x00/07/08/0b/0c`＝0＋U+FFFD 与源相等。

## 重复投递声明

本单可能被机械重复送达，重复送达按一次处理，产物只写同一批文件。