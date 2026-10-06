# 2026-10-06 总控线交接纸（旧线上下文吃满，新线从这一张接手）

🔴 本纸**不携带逐号状态**（AGENTS ⑨）：号→状态→写域→基点只认 `docs/tickets/index.tsv`（脚本派生，禁手改）；
逐号判据只认 `docs/tickets/RNNN-*.md`。本纸只承接：在飞席位、排班、读数现状、业主动作、本班新学的坑。
禁止依据 `task_plan.md`／`progress.md`／`findings.md` 判进度（计划书 §10 明令过期）。

## 0. 一句话现状（10-06 16:2x 现取）

- 分支 `codex/data-file-catalog`，主树 `C:\Users\fengx\PycharmProjects\企业智脑`；本班已并树序列（旧→新）：
  `c545084` R701 · `3112842` 账 · `a816857` R699 · `3bfe5d7` 账 · `ebf53ea` 工单 · `0e53db3` R704 · `0739736` 账 ·
  `5984c78` 工单 · `78a6568` **R695** · `54e1f53` **R707** · `468fe3b` 账 · `9ea7e97` R702 写域收窄 ·
  `7810f73` **R703** · `760c5e2` 账 · `dd70ee1` 立 R708/R709/R710 · `4147b6d` R707 补记 · `2baba78` 账。
- V1 口径唯一尺＝`python scripts/audit_plan_ticket_ledger.py`（现取 RESULT=PASS／0 违规／在册 43 号）。
  读法乙「判据全达才算清」**未清 9 号**：R25 R26 R28 R31 R35 R38 R44 R47 R51；另有 5 格 `OUT`
  （R29② R43② R48① R50② R52①）——🔴 移出 V1 门槛**不等于判达**，不算完成。
- 那 9 号里**只有 R25②／R35②／R44① 需要非本机的东西**（overlay 容器取证要窗后动容器；生产密级标签属交付阶段；
  真库 37,483 chunk 本机只有 1,008 枚）。其余 6 号的欠项是**同一扇夜窗的读数**（见 §3）。

## 1. 在飞席位（4 枚＝硬上限，别再新投；收一枚腾一槽）

| 席位 | agent_id | 单号 | 独占树／基点 | 交付状态与验收要点 |
|---|---|---|---|---|
| `Archimedes` | `01a10f67-0bb8-7882-8023-6137e87063dc` | R694 前端九环走查＋两张失败脸 | `be-r694`@`6800b4c` | ledger 现取：环 **达 1-6、9**，**未达 7、8**；`faces` **4 枚**（`blank_screen=false`，降级横幅逐枚点名：健康读数取不到／本机模型连不上／没走加速设备×2）；截图 30 枚在 `be-r694/docs/testing/walkthrough-2026-10-06/`。验收＝把 `docs/testing/walkthrough-2026-10-06/**`＋`scripts/r694_*.py` 并树，环 7 的 Data 腿已由 R703 治、环 8 由 R710 治；🔴 它占模型与 GPU，**窗必须排在它结案之后** |
| `Newton` | `01a11008-a453-78b3-82de-be1df50708eb` | R706 r496 自读钉态分支 | `be-r706`@`5984c78` | 施工笔 `478b569`（`tests/test_r496_forbidden_pin_scope.py` 175/17、`tests/test_r453_cloud_eval_override.py` 76/11、新增 `tests/test_r706_state_branch_disk_pins.py` 236/0）。tests-only 写域，验收＝同名件两态＋「静止态那条红今天该红还得红」不许被放宽成「脏就跳过」 |
| `Schrodinger` | `01a11026-a3cc-7040-9292-56da2e4bd6ba` | R702 claims 接出口（C④ 分母） | `be-r702`@`9ea7e97` | 刚投。判据原文与禁区在工单；🔴 `app/agents/evidence.py` 已就地收窄成**只 import 禁改**；不许顺手改路由（那一格归 R709） |
| `Noether` | `01a11032-054e-7103-b223-dea26d22fdd0` | R710 导出腿登记＋答复诚实 | `be-r710`@`dd70ee1` | 刚投。一手读数已嵌进工单：`[export] 完成 status=failed 结果 51 字`、`report_artifact.found=false`、`artifact_rows_after=[]`、`/api/v1/artifacts` 零枚在册；禁区含 `chat.py`（R702 在飞）与 `orchestrator.py` |

已 close（不占槽）：`Laplace` `Goodall` `Curie` `Sartre` `Dirac` `Mill` `Bacon` `Lagrange`。

🔴 **下一条线接这四枚席位的正确通道**：它们是**旧总控线**用 `spawn_agent` 开出来的子线，新线程手里没有它们的 multi_agent 句柄，别去 `wait_agent`／`close_agent`。
正解＝`list_threads` 找到它们（按上表的 `agent_id` 对号）→ `read_thread` 取进度 → 要下指令用 `send_message_to_thread`，
且**措辞照 AGENTS 的短消息规矩**（长消息是致命通道，#112／#113 两枚执行层死在投递本身）；要返工就落成账面（工单文末追加＋新单承接），不发长令。
交付到货后由**新总控**在主树验收并树（`git apply` patch＋逐枚 SHA-256 对盘），席位不碰主树。

## 2. 待派池（按写集排，串行理由逐格点名）

- **R709** `chat.py::_should_use_data_context` 因「报销」落 `document_terms` 否决本轮 `data_filename`（连带 `route_main` 的 `has_data` 与 `_authorized_dataset_files` 退化成全量可见＝越权面）——🔴 **等 R702 并树**（同文件）。
- **R708** `docs/api/contract-v1.md` 三处过期（R306 节／S5 注记／Dataset File Delivery 该点名 `app/api/v1/data.py::guard_dataset_name_conflict`，伪造 `.xlsx` 真读数 400 而账面留 500）——docs-only，总控亲写即可，🔴 也**等 R702**（同文件）。
- **R711** 索引只从提交标题里的「并树」字面认落地号（本班实测自撞，见 §7）——scripts＋tests-only。
- **R712** 门那格：派生坐标族当前 HEAD **15 failed／358 passed**（逐枚点名在工单里）——docs 再生＋量具派生两形。
- **R696／R697** retrieve 段甲案（读侧并段）与 r636 活窗接绑（13 枚 skip 变绿的唯一正解）——🔴 **必须排在今夜窗之后**，两枚都要 run32／run33 的导出件当分母，且窗内禁碰量具。
- **R669** R25② 带 overlay 真机取证——要动容器，窗后。
- 账面与流程类（不挡 V1 门，别在窗前提它们）：R665 R667 R668 R675 R680 R681 R683 R684 R687。
- 共抢咽喉文件的串行事实：`chat.py`＝R702→R709；`contract-v1.md`＝R702→R708；`app/agents/orchestrator.py`＝R30/R31/R33/R42/R38 那一族，R710 明令禁碰。

## 3. 夜窗排班（一扇没开；这是今晚唯一能把 6 号翻绿的东西）

- 队列：`scripts/day1006_queue.py`（已含 R704 的 claims 覆盖率读数口＋band5 `r677_hot_index` 覆盖率）。band 构成：
  band0 代次闸（不合规自动 `docker compose build migrate` ＋ `--force-recreate backend worker scheduler`）→
  `run32` 全 105（≈1.9 h，一次拿 A② 流式逐字／A④ 逐类不退化／C③ 分数／C④ 分母／R26② 归因／R51② `<1%`／R38③ usage／R47① 真实命中）→
  `run32d` 33 题 D 相（≈35 min；分母凭据 `docs/testing/bank-shape-subset-30.jsonl`＝33 行）→
  `run33` 同代次第二扇（A④ 跨代对子从今天起算，run22／run23 的证据件已被事故 #124 清掉）→
  band4 `scripts/r634_category_delta.py` 配对 → band5 覆盖率。
- 🔴 昨夜 `run30d` 是**废样本**：队列把环境变量名写成 `DECLARE_LANE_TIER=report`，而量具真读 `EVAL_DECLARE_LANE_TIER`，取值名册是 `报告/分析/问答`。`scripts/night1006_queue.py` 已就地修，`day1006_queue.py` 自带 `--expect-denominator 33` 与 `--expect-lane-phase on`。
- 起法（自带账本，断联/重启即跳过 rc=0 的步骤）：
  `Start-Process -FilePath .venv\Scripts\python.exe -ArgumentList "scripts\night1006_watchdog.py","--tag","day1006","--queue","day1006_queue.py","--max-relaunch","8" -WindowStyle Hidden`
  账本＝`%TEMP%\evalrun\night1006.ledger.jsonl`；交还机器前现取三枚读数（队列 pid 在／账本行数在涨／下一条 step 已排队）——AGENTS ⑪。
- 前置：机器永不睡（`powercfg /change standby-timeout-ac 0` 已在位，别改回）；`%TEMP%\evalrun` 现取在位窗＝`run30`／`run30d`／`run31`；🔴 窗内禁并树、禁跑测试、禁动容器、禁打模型（AGENTS ⑬／⑮）。

## 4. 门那格（最贵的真账，别当成绿）

- 上一班那次 **57 failed／11438 passed／94 skipped／2 xfailed／978.29 s** 已过期。本班 16:1x 亲跑的**受影响面**复跑＝
  17 枚派生坐标族 **15 failed／358 passed／212.68 s**（逐枚点名在 `docs/tickets/R712-*.md`）。
- 全量门在新 HEAD 上**还没跑过**；按 AGENTS ④ 的节奏＝每班开工一次＋冻结前一次＋每并满 5 枚补一次，`python scripts/run_gate.py`（并发自选，纸上不写 `-n`）。
- §9 判据 4「红集合为空」⇒ 门那格不绿之前，任何「V1 验收通过」的说法都不成立。

## 5. 只有业主本人能做（我不代做）

1. `git push`——本班 20 枚全部未推，本机仍是**唯一副本**（H6 到今天没结）。
2. `automation-2` 的 `target_thread_id` 仍指向死线程 `01a0acfb…`（状态 `PAUSED`）。字段口径：判别用 `mode`，update 传 `targetThreadId`（camelCase）。
3. `.gitignore`／`chroma_db` 反跟踪／删除陈旧工作树：`git worktree list` 里十余枚 temp worktree（`r676_*`／`r647`／`r653`／`eb104`／`be-r695`／`be-r703` 等，部分 prunable）＋主树未跟踪残件 `tests/test_r695_rewrite_stage_accounts.py.r695stray`（对盘无丢件，见 §7）。**删之前先在沙盒模拟**。
4. R35②／C① 需要**客户真实密级回填**（本机不可证，不许拿合成标签翻绿）；R44① 需要客户尺寸真库（37,483 chunk）。
5. H11 那一格要真机容器重启后才有 GPU 读数（A③ 的语义钉归 R673，码已并）。

## 6. 本班新学的坑（下一条线别再付一遍学费）

- **#127（总控自伤）**：改盘上一枚件时用切片拼接 `t[:i]+new+seg[cut:]`，把 446 行的 `tests/test_r688_stage_accounts_are_landed.py` 截成 37 行，连带三枚件收集 ERROR。已 `git checkout --` 恢复并按**精确整串替换**（`count(old)==1` 断言在前）重做。🔴 规矩补一条：改文件只许整串替换或编辑器通道，**禁切片拼接**。
- **#128（串台件）**：执行层把半件写进主树 `tests/test_r695_rewrite_stage_accounts.py.r695stray`（9,922 B，SHA `c46d3a4c…`）。对盘：主树与席树终版同为 `386d00f4…`（＝R695 凭据纸 §8 现取值）⇒ **无丢件**；残件待业主按 §5.3 处理。
- **索引判据缺口（→ R711）**：`scripts/tickets_index.py::landing_numbers` 只从提交标题里的「并树」字面认落地号 ⇒ 我标题写「R707 订正…」的真并树笔被判 QUEUED。我没改标题洗状态，而是把两态读数作凭据追加进工单（`4147b6d`）。
- **自指要跑两遍**：并树笔刚落地那一刻生成的索引仍写旧状态（`--write` 读的是生成时的 `git log`），必须**再一笔账提交**才转蓝（`2baba78`）。每并一枚就跟一笔，别攒。
- **解释器**：主树 `.venv\Scripts\python.exe` 才是能跑测试的那枚；`C:\Users\fengx\anaconda3\python.exe` 缺 `chromadb`，只能跑纯 stdlib 脚本（conftest 当场 ImportError）。
- **`Start-Process -ArgumentList` 只吃单串**：传数组会报「Cannot convert System.Object[]」；正确写法是把 `"-m pytest -q --no-header <文件串>"` 拼成一整串。别信 `Start-Sleep` 阻塞式等待——exec 通道 30 s 就 yield，长批一律 `Start-Process` ＋ 日志尾读。
- **state② 的树形状**：`git archive` 出的树没有 `.git`，状态敏感钉（r496／r688 一族）连收集都过不去；干净态一律 `git worktree add --detach` 跑，用完 `git worktree remove`（AGENTS ⑮ 的正解）。
