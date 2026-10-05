# R682 · KPI 量具：四个数加一条红线（病根复盘 §D 落地·总控裁定）

**基点**：开工时现取主树 HEAD 写进交付。**独占工作树**：总控告知路径，不许换树、不许碰主树。

## 为什么有这一单

规矩已改成「判进度只看四个数」（`docs/engineering/multi-agent-project-rules-2026-10-05.md` §D），但这四个数今天**没有一把尺**，全靠每班手抄现取——手抄就是下一本假账。这一单把它变成一条命令产出一张机器账。

## 判据（每条都可失败，缺一枚判负）

1. 新 `scripts/meta_health.py`，一条命令打印**四数一红线**，每行都要带「量具名＋现取读数」，不许形容词：
   - ① 产品面：`app/**` py 文件枚数与近 200 笔新增行数、`tests/**` py 文件枚数、API 路由枚数；
   - ② 验证墙钟：读 `docs/testing/**` 与看板里在册的同 HEAD 复跑数（取不到就打印 `NOT_MEASURED`，🔴 不许造数、不许留空）；
   - ③ 每轮必读台账字节数：跟进单＋看板逐枚字节数；
   - ④ 并树/日：按 `git log --since` 现算近 7 天逐日「并树」提交数；
   - 🔴 红线：**读 markdown 的用例占比**——按 `ast` 扫 `tests/**`，统计函数体内出现 `Path(...)/open(...)` 且路径落在 `docs/**`／`*.md` 的用例枚数 ÷ 全集枚数，分子分母都要打印。
2. **零 import `app`、零起服务、零动容器、零打模型**；全离线，整把尺自跑墙钟 ≤ 60 s，读数写进凭据纸。
3. 新 `tests/test_r682_*.py` 照 `tests/test_r132_contract_followup_sync.py` 的形状（只用 `ast`／`re`／`pathlib`，不 import `app`，全离线）：至少三枚牙——(a) 缺列即红；(b) 造数即红（喂一个把 ② 写成常量的桩，必须点名）；(c) 分母为零时不许打印百分比，必须打 `NOT_MEASURED`。
4. 输出一段「与上一班对账」的机器可读行（`key=value` 逐行），便于以后直接 diff，不再手抄进散文。

## 写域

`scripts/meta_health.py`（新）／`tests/test_r682_*.py`（新）／`docs/tickets/R682-*.md`／`docs/testing/r682-<今天>.md`（新，凭据纸）

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与 `tests/test_evaluation_report.py`／`scripts/run_gate.py`／`scripts/audit_plan_ticket_ledger.py`／`pyproject.toml`／`deploy/.env.server`／`AGENTS.md`／`chroma_db/**`／任何镜像与容器动作／**主树任何路径**。

## 不许做

commit 到主树／建分支／push／起服务／动容器／rebuild 镜像／打真模型／跑全量门。可以在**自己的树**里 commit 自己的货（新规 A6·业主 10-05 授权），主树并树仍由总控验收后代提交。

## 交付必须含

1. 三态数（基点干净检出／state① 已 apply 未 commit／state② 干净检出投本单货），同名件清单逐枚相同、总数相同；执行层读数标「执行层自报」。
2. 判据 1 的**实际输出全文**（四数一红线逐行）。
3. 坐标一律 `文件::符号`，🔴 禁止 `文件:数字`。
4. 写文本走字节通道（`git diff --output=<file>`；含反引号或中文的正文走单引号 here-string），写完现读＋扫 `0x00/07/08/0b/0c`＝0＋U+FFFD＝0。

## 重复投递声明

重复送达按一次处理，产物只写同一批文件。