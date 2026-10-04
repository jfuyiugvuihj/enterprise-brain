# R634 —— A 门④「逐类不退化」的归因单：同类目跨窗 delta，噪声底与退化分开算（2026-10-04）

工单：R634（A 门④ 欠的那枚**归因单**，不是门）。工作树 `C:\Users\fengx\PycharmProjects\be-r634`，分支 `codex/be-r634`，基点 `4da0bad`。
执行层：本件。货只留盘上，等总控代提交（本单未 `git commit`、未建分支）。

> 🔴 **本纸不交结论。** 全文只写「量到了什么／量不到什么」。A 门④ 达不达标、逐类不退化成不成立，那两句归业主与总控判。
> 账上凭据：`docs/handoff/2026-09-23-v1-acceptance-record.md:43`（A④ 行末写「需归因单」）、`:53`（「要先归因」）；
> 上一班的两条相关读数：`docs/handoff/2026-09-15-backend-followup-requests.md:5472`（两窗取严，间歇摆动）、
> `:5576`（`r580_per_class_attribution.py` 对同读后端两窗**硬拒 rc=2** ⇒ 它是读后端归因尺，不是 A④ 的尺）。

---

## 0. 一句话交代

盘上今天**没有**任何一枚「跨代次」对子可以判：三扇完整窗（run18／run19／run20k）镜像 `revision` 与题集 `fixture_sha256` **两枚全等**，
所以「逐类 delta」这一把尺今天只能量出**同码两跑之间的摆动**，量不到退化。本件据此交的数是：
**同码摆动底逐类目逐指标一枚一枚的幅度＋搬动的题号**（§4），和**为什么退化那一格是空的**（§5）。

---

## 1. 命令原文 → 实取读数（盘上件清点）

命令（两条，逐层现取，不在一层查不到就宣布另一层也没有）：

    Get-ChildItem -Path $env:TEMP\evalrun -File | Select-Object Name,Length,LastWriteTime
    git ls-files docs/testing

实取读数（层＝`%TEMP%\evalrun` 与仓内 `docs/testing` **两层**）：

| 窗 | report | answers | sidecar | frames | 窗记 | 可用性 |
|---|---|---|---|---|---|---|
| run18 | 13714 B | 105 枚 | 105 枚 | 105 枚 | 在 | ✅ 完整 |
| run19 | 13718 B | 105 枚 | 105 枚 | 105 枚 | 在 | ✅ 完整 |
| run20k | 13708 B | 105 枚 | 105 枚 | 105 枚 | 在 | ✅ 完整（但见 §6：读后端那一格与上两扇不同） |
| run20 | **缺** | **缺** | 2 枚 | 在 | 在 | ❌ 开窗即被拒（见下 REFUSE 原文），不可用 |
| run21 | 缺 | 12 枚 | 12 枚 | 在 | 在 | ❌ 在跑（总控的窗），本件不碰 |
| run21b | 缺 | 12 枚 | 12 枚 | 在 | 在 | ❌ 在跑，本件不碰 |

run20 被拒的原文（`%TEMP%\evalrun\queue20.log` 现取，逐字）：

    REFUSE: 容器 INDEX_BACKEND='chroma'，而这一窗要钉的是 chroma（chroma 这一档要求该变量为空）
    fix: env_file 是在容器创建那一刻才解析的：正解 docker compose up -d --force-recreate，plain docker restart 不重读它

指纹现取两枚（同一枚 log）：

    指纹现取：revision=a2bbf13 backend='pgvector' fixture=686c564ff298 transport=eval_transport_ask_v2:transport probe_ok=True
    指纹现取：revision=a2bbf13 backend='' fixture=686c564ff298 transport=eval_transport_ask_v2:transport probe_ok=True

收册尺跑分命令原文（同两层 log 现取，本件不改它）：

    python scripts/run_quality_evaluation.py --fixture C:\Users\fengx\PycharmProjects\企业智脑\tests\fixtures\business_evaluation_100.jsonl --answers …\run18-answers.jsonl --output …

    evaluated=105 correctness=0.6571 evidence=0.7905 p95_ms=73363.894 answer_correctness_scorable_subset=0.6977 scorable_subset[total_rows=105 deducted_n=19 denominator_rows=86 correct_n=60]
    evaluated=105 correctness=0.6476 evidence=0.7810 p95_ms=70472.751 answer_correctness_scorable_subset=0.6744 scorable_subset[…correct_n=58]
    evaluated=105 correctness=0.6571 evidence=0.8000 p95_ms=69530.419 answer_correctness_scorable_subset=0.6860 scorable_subset[…correct_n=59]

---

## 2. 分代列表（🔴 两代数字不进同一张比较表）

### 2A. 今天这三扇：代次**可证**，且同代

命令：

    .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --window run19 --window run20k --format json --out %TEMP%\r634-run18-19-20k.json

实取读数（`windows[].fingerprint`，逐字取自各窗 `<tag>.window.json`）：

| 窗 | revision | index_backend | fixture_sha256 | transport | shard | started_at | 与落盘报告对账 |
|---|---|---|---|---|---|---|---|
| run18 | a2bbf13…5b7d | "pgvector" | 686c564f…d79b | eval_transport_ask_v2:transport | 1 | 2026-10-03 17:12:40 | 全格对上（42 格） |
| run19 | a2bbf13…5b7d | "pgvector" | 686c564f…d79b | 同上 | 1 | 2026-10-03 18:26:05 | 全格对上（42 格） |
| run20k | a2bbf13…5b7d | "" | 686c564f…d79b | 同上 | 1 | 2026-10-04 10:01:33 | 全格对上（42 格） |

题集现读：`tests/fixtures/business_evaluation_100.jsonl` sha256=`686c564ff2985744e6f050e5ea7639500c99bd80b3e32fc3a85e585f5ecdd79b`，105 枚。
⇒ 三扇的**代次**（revision ∧ fixture_sha256）**同一枚**；差异只在 `index_backend` 那一格（§6）。

### 2B. 仓内历窗落盘件：代次**不可证**

命令：

    git ls-files docs/testing          # 逐枚现取，不猜
    .venv\Scripts\python.exe -X utf8 -c "逐枚读 evaluation-report*.json 的键与格"

实取读数：

| 件 | total | 有第二把尺 | 有分母账 | 有批准格 | 带 revision/fixture_sha 格 | 类目数 |
|---|---|---|---|---|---|---|
| evaluation-report-run5.json | 105 | 无 | 无 | 无 | **无此格** | 11 |
| evaluation-report-run7.json | 105 | 无 | 无 | **有** | **无此格** | 11 |
| evaluation-report-run8p2.json | **20** | 无 | 无 | 无 | **无此格** | 3 |
| evaluation-report-run9.json | 105 | 无 | 无 | 无 | **无此格** | 11 |
| evaluation-report.json | 105 | 无 | 无 | 无 | **无此格** | 11 |

answers／侧车枚数现读：`answers-run6.jsonl` 105 · `answers-run7.jsonl` 105 · `answers-run8p2.jsonl` **20** · `answers-run9.jsonl` 105；
四本的题号集合都落在今天 105 枚之内（「今天没有的号」＝空）。另两枚迷你题集：`bank-run8p2-subset20.jsonl` 20 枚、`bank-shape-subset-30.jsonl` 33 枚。

读法与限制（不猜、不补）：
- 这些报告**没有** `revision`／`fixture_sha256` 任何一格 ⇒ 代次读不出来；号集相同**不等于**锚词相同代（R401 处置与锚词是 09-28 之后才回灌题源的，`docs/handoff/2026-09-15-backend-followup-requests.md` 记着这条线）。
- 它们也**没有**第二把尺那一格 ⇒ 尺本身就是 R438 之前的形状，与今天三扇不同代尺。
- `run8p2` 只有 20 枚，与 105 枚在册判据范围**可证地**不同题集。
- ⇒ 本件对这些窗**只列读数、不重算、不对账、不进任何比较表**（工具里 `measured=false`＋`代次不可证` 那一格明写原因）。
  同族假账（`runbook:413` 三片不同代）就是栽在把两代数字塞进同一张表，本纸不重犯。

命令与实取（把不可证的窗与可证的窗混给，看工具是否守住）：

    .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --report docs/testing/evaluation-report-run9.json --report docs/testing/evaluation-report-run8p2.json --out %TEMP%\r634-mixed-generations.txt

    rc=4 —— 判不了｜盘上没有跨代次对子
    代次不可证：run9 —— 窗记未交或窗记里读不出 revision／fixture_sha256 ⇒ 本件不重算、不对账，只把报告里已有的读数列进分代列表，不进任何比较表
    代次不可证：run8p2 —— 同上

---

## 3. 三扇真窗的逐类目读数（在册尺现算，且逐格与落盘报告对账）

命令同 §2A。逐类目 correctness：

| 类目(题数) | run18 | run19 | run20k |
|---|---|---|---|
| 文档问答(19) | 0.7368 | 0.7895 | 0.7895 |
| 多轮对话(12) | 0.3333 | 0.3333 | 0.4167 |
| 口径冲突(19) | 0.9474 | 0.7895 | 0.8421 |
| Excel计算(12) | 0.6667 | 0.6667 | 0.6667 |
| 主动洞察(7) | 0.5714 | 0.7143 | 0.7143 |
| 图表生成(4) | 1.0000 | 1.0000 | 1.0000 |
| 审批判断(6) | 0.8333 | 0.6667 | 0.5000 |
| 跨部门权限(6) | 0.3333 | 0.1667 | 0.3333 |
| 无证据问题(4) | 0.2500 | 0.2500 | 0.2500 |
| 工具调用(4) | 0.7500 | 1.0000 | 1.0000 |
| 报告生成(12) | 0.5000 | 0.5833 | 0.5000 |

evidence_coverage／unsupported_claim_rate／p95_ms 三张表同命令交回（太长，落在 `%TEMP%\r634-run18-19-20k.txt` 第二节，逐格可复现）。
全局四格现读：correctness 0.6571／0.6476／0.6571，evidence 0.7905／0.7810／0.8000，ucr 0.0／0.0／0.0，p95 73363.9／70472.8／69530.4 ms。
第二把尺（可判子集，105−19＝86 枚）：0.6977／0.6744／0.6860。

对账口径（不是自证漂亮，是本件的硬闸）：每扇窗现算的 `total`／三数／第二把尺／时延四格／**11 枚类目 ×3 格** 一律与它自己那份落盘 report 逐格比，
42 格全等才出数；任一格不平 ⇒ `rc=3` 明写「取不到可信读数」。这一闸由 `tests/test_r634_category_delta.py::test_report_numbers_that_disagree_with_the_ruler_are_refused` 钉着（把报告里 correctness 改高 0.2 就被拒）。

---

## 4. 🔴 噪声底：同码两跑之间本来就有多大逐类摆动（主交付）

底只从**五项指纹全等**的复跑对子里长出来。今天盘上这样的对子只有一枚：**run18 → run19**。
命令：

    .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --window run19 --window run20k --out %TEMP%\r634-run18-19-20k.txt
    （读数取第二、三、五节；JSON 面在 .json 那份的 summary.noise_floor.cells）

实取读数（摆动量＝该格跨两窗差值的绝对值；方向不计——同码复跑里方向是随机的）：

| 类目(题数) | correctness 摆动 | evidence 摆动 | ucr 摆动 | p95 摆动(ms) | 搬动的题（correctness） |
|---|---|---|---|---|---|
| 文档问答(19) | **0.0527** | 0.0000 | 0.0000 | 11620.9 | doc-06（收分） |
| 多轮对话(12) | **0.0000**（净额） | 0.0833 | 0.0000 | 320.3 | chat-01 掉 ＋ chat-08 收 ⇒ **相消** |
| 口径冲突(19) | **0.1579** | 0.0526 | 0.0000 | 6082.3 | metric-07／metric-15／metric-17（全掉） |
| Excel计算(12) | 0.0000 | 0.0000 | 0.0000 | 11633.6 | 无 |
| 主动洞察(7) | **0.1429** | 0.0000 | 0.0000 | 12382.4 | insight-03（收分） |
| 图表生成(4) | 量到 0.0000，样本不足不判 | 量到 0.0000，不判 | 量到 0.0000，不判 | 3082.4（仅存档） | 无 |
| 审批判断(6) | **0.1666** | 0.1666 | 0.0000 | 58.1 | approval-03（掉） |
| 跨部门权限(6) | **0.1666** | 0.1667 | 0.0000 | 8272.7 | scope-01（掉） |
| 无证据问题(4) | 量到 0.0000，样本不足不判 | 量到 0.0000，不判 | 量到 0.0000，不判 | 121.7（仅存档） | 无 |
| 工具调用(4) | **量到 0.2500**，样本不足不判 | 量到 0.0000，不判 | 量到 0.0000，不判 | 1649.1（仅存档） | tool-03（收分） |
| 报告生成(12) | **0.0833** | 0.0000 | 0.0000 | 6248.0 | report-10（收分） |

底有多宽（把上面折成一句话）：**同一枚镜像、同一套题、同一台机、同一读后端，两跑之间逐类 correctness 在可判类目里最大摆 0.1666**
（6 枚题那一族掉 1 枚）；19 枚那一族摆 **0.1579**（掉 3 枚）；p95 那一格两跑之间能差到 **12.4 秒**。
三族 4 枚题的类目里还量到过 **0.2500**（工具调用，tool-03 一枚收分）——那一格只存档不判，因为它过不了样本闸。

三条必须一起读的限定：
1. **底只有一枚对子**（n=1）。它是摆动的**下界观测**，不是分布。真实底很可能比这更大。
2. **净额会把摆动看成零**：多轮对话 correctness 两跑都是 0.3333，里面却是一枚掉一枚收（chat-01 掉「审批」、chat-08 收「按单人标准」）。
   ⇒ 只看类目均值差，这一格的底会被记成 0.0000；题级翻面枚数才是它的真摆动。本件把两枚都点名，就是为了这一格不许被抹平。
3. **4 枚题的三族（图表生成／无证据问题／工具调用）本件一律拒判**（样本闸＝5 枚）。它们的「一枚题＝0.25」粒度比任何跨代次变化都粗，
   工具对这三族写的是 `insufficient_sample`，**不写绿也不写红**——这一条由 `::test_three_question_category_is_refused_not_green` 钉着。
   样本闸只管**判定**、不管**记录**：这三族的 p95 摆动本件照样量出来存档（3082.4／121.7／1649.1 ms），但一枚都不拿它当底去判任何一格。

与在册账的交叉核对（不是我另造的第二把尺）：上一班总控在 `docs/handoff/2026-09-15-backend-followup-requests.md:5472` 手写的七格方向
（向差：口径冲突 .9474→.7895／审批判断 .8333→.6667／跨部门权限 .3333→.1667；向好：工具调用 .75→1.0／主动洞察 .5714→.7143／报告生成 .5→.5833／文档问答 .7368→.7895）
与本件现读**逐格同号同数** ⇒ 这把底是可复算的，不是本单新起的一套口径。

---

## 5. 拿这把底去判跨代次那一组：**量不到**（本节不交退化，因为盘上没有可判组）

命令（同 §4，看 `summary`）：

    .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --window run19 --window run20k --format json --out %TEMP%\r634-run18-19-20k.json

实取读数：

    "cross_generation_pairs": 0
    "judged_cross_generation_cells": 0
    "regressions": []
    "verdict_tally": {"noise_floor_input": 32, "insufficient_sample": 36, "not_a_generation_step": 64}
    rc=4 —— 判不了：底没量出来、或没有跨代次对子、或全部格样本不足（非绿灯）
    为什么是这个码：盘上没有跨代次对子：所有可测对子的 revision 与题集 sha 全等（同码复跑或换了条件） ⇒ 逐类不退化这件事今天量不到，不是没退化

三条交代：
- **64 格 `not_a_generation_step`** ＝ run18/19 各自对 run20k 的两枚对子：同代次、换过 `index_backend`，本件按定义**不判退化**（§6）。
- **32 格 `noise_floor_input`** ＝ run18→run19 那枚对子里的可判格：它们**就是底本身**，不进退化那一栏。
- **36 格 `insufficient_sample`** ＝ 三族 4 枚题 ×4 指标 ×3 对子。
⇒ 「A 门④ 的退化那一格今天能不能判」的答案是**不能**：不是「判了没退化」，是**根本没有两代窗可比**。
  要判它，得等一枚**不同 revision**（或不同题集 sha）的完整窗收口，再与今天这枚底对撞。这枚缺的是**对照物**，不是代码。

顺带把「按 delta 判退化」这把尺本身的毛病量出来了：账上登记过的两笔真退化，
`文档问答 0.6842→0.6316`（19 题掉 1 枚＝**0.0526**，`docs/handoff/2026-09-15-orchestration-board.md:3488`，`doc-19`，run5 已收回）与
`口径冲突 0.4211→0.3158`（19 题掉 2 枚＝**0.1053**，同文件 `:4041`，A④ 判红那一笔，`docs/handoff/2026-09-23-v1-acceptance-record.md:43`），
**都落在今天量出的同类摆动（0.1579＝掉 3 枚）以内**。⇒ 只拿「逐类 delta 是否 < 底」当判据，这两笔都证不了。
这不是替历史翻案（那两笔有逐题翻面为证），而是本件量到的一个口径事实：**类目均值的 delta 判据在该题数量级下分辨不出「1～2 枚题的退化」**。
要么按题级翻面枚数取严（上一班 §5472 那句「两窗取严」正是这个方向），要么把底改成多窗分布而不是单枚对子。这一格归总控与业主裁。

---

## 6. run20k 与上两扇那一组为什么不算退化（现读，不假设）

窗记现读：run20k `index_backend=""`，run18／run19 `index_backend="pgvector"`；`revision` 与 `fixture_sha256` 三扇相同。
在册那条口径（`scripts/eval_window_shard_driver.py` 与 `scripts/r580_per_class_attribution.py` 都写着）：
**空串＝`INDEX_BACKEND` 未设＝缺省 Chroma 读腿**；驱动还留着一枚 REFUSE（§1 原文）证明这一档是真拦得住的。
另现读一枚 `%TEMP%\evalrun\env.server.bak-1004-0957`：名字写 1004-0957，**CreationTime＝2026-10-04 09:57:57**、
LastWriteTime＝2026-10-03 10:32:04（拷贝保留源件写时间就是这个形状），时序上夹在 run20 被拒（09:56–09:59）与 run20k 开窗（10:01:33）之间。
本件只记录这个时序，**不解释因果**，也不据它改任何一格判定。

⇒ run20k 与 run18/19 之间那把差值是**读后端那一刀**，唯一变量不是代次：本件对它只列差值、给判定 `not_a_generation_step`，
**不许**写成退化，也**不许**写成没退化。那一刀的量具是 `scripts/r580_per_class_attribution.py`（它对同读后端两窗硬拒 rc=2，对这一组正合适）。

列出来给 R580/总控用的数（现取，不改）：run18→run20k correctness 差值——口径冲突 −0.1053、审批判断 −0.3333、跨部门权限 0.0000、
文档问答 +0.0527、多轮对话 +0.0834、报告生成 0.0000；翻分题 10 枚（含 approval-04 掉「部门负责人」、report-04 掉「来源」）。
run19→run20k 另有一组 7 枚。逐枚细节在 `%TEMP%\r634-run18-19-20k.txt` 第四节。

---

## 7. 翻分题逐枚点名（本单要的第四样）

命令同 §4，读数取第四节。run18 → run19 全部 11 枚（6 掉 5 收，净 −1 枚，与全局 0.6571→0.6476 吻合）：

| 题号 | 类目 | 方向 | 归类 | 形状信号 | 丢/收的锚词 | 字数 | evidence_n | tool_calls | kind | 在册扣除(丙案) |
|---|---|---|---|---|---|---|---|---|---|---|
| doc-06 | 文档问答 | 收分 | 答得不同 | 形状未变 | 收「行程单」 | 691→1043 | 12→12 | 2→2 | ok→ok | 否 |
| chat-01 | 多轮对话 | 掉分 | 答得不同 | 形状未变 | 丢「审批」 | 707→476 | 5→5 | 2→2 | ok→ok | 否 |
| chat-08 | 多轮对话 | 收分 | 答得不同 | 答案缩过半 | 收「按单人标准」 | 819→227 | 5→5 | 2→2 | ok→ok | 否 |
| metric-07 | 口径冲突 | 掉分 | 答得不同 | 形状未变 | 丢「销售额含增值税」 | 453→360 | 8→9 | 2→2 | ok→ok | 否 |
| metric-15 | 口径冲突 | 掉分 | 答得不同 | 形状未变 | 丢「库存周转按结转营业成本计算」 | 710→621 | 12→12 | 2→2 | ok→ok | 否 |
| metric-17 | 口径冲突 | 掉分 | 答得不同 | 形状未变 | 丢「回款以验收单确认」 | 322→553 | 5→5 | 2→2 | ok→ok | 否 |
| insight-03 | 主动洞察 | 收分 | 答得不同 | 形状未变 | 收「建议」 | 1350→962 | 14→13 | 2→2 | ok→ok | 否 |
| approval-03 | 审批判断 | 掉分 | 答得不同 | 证据清零、工具调用清零、答案缩过半、短答无出处 | 丢「限额内据实报销」 | 166→79 | 6→**0** | 2→**0** | ok→ok | 否 |
| scope-01 | 跨部门权限 | 掉分 | 答得不同 | 答案缩过半 | 丢「权限」 | 506→202 | 5→5 | 2→2 | ok→ok | 否 |
| tool-03 | 工具调用 | 收分 | 答得不同 | 形状未变 | 收「重新生成」 | 700→997 | 14→15 | 4→4 | approved_ok→approved_ok | **是** |
| report-10 | 报告生成 | 收分 | 答得不同 | 形状未变 | 收「原因」 | 629→633 | 8→9 | 4→4 | approved_ok→approved_ok | 否 |

四型归类今天只出现一型（答得不同）。理由逐枚点名，且侧车现读可佐证：三扇窗 `kind` 分布＝run18 `ok` 86＋`approved_ok` 19、run19 同、run20k `ok` 87＋`approved_ok` 19；
`sentinel=True` **0 枚**、`approval_error` 非空 **0 枚**、answers 里没有缺行。⇒ 今天这一格的摆动**全部**长在「同一发回答写成另一串字」上，
不在「没答／哨兵／批准失败」那一族里。那一族的四型各一枚由合成样本钉住（`::test_the_four_ways_a_question_can_lose_a_point_are_named`），
真窗里今天没有它们的实例——这句是读数，不是猜测。

一枚值得转给归因下一手的形状读数：`approval-03` 在 run19 那一发是 **79 字／引证 0 条／工具调用 0 次／kind 仍 ok**，
run18 是 166 字／6 条引证／2 次调用。它归在「答得不同」是因为在册 kind 说它答完了；形状那一列说的是它**像一条没出处的短兜底**。
本件不据此判它是检索塌还是生成塌（那需要 `r580` 的引证血缘与 parity 量具，本单写域外、也不属本单判据）。

---

## 8. 量不到的清单（照规矩写「量不到」，不编绿灯）

1. **跨代次退化**：量不到。盘上零枚跨代次对子（§5）。缺的是对照物——一枚不同 revision 的完整窗。
2. **`unsupported_claim_rate` 这一格三扇恒 0**：那是**没量**，不是「没有无据断言」。现读：三扇 answers 的键集为
   `answer/answer_source/evidence/first_token_at/id/latency_ms/thinking_chars/tool_calls`，**带 `claims` 的枚数 0/105**；
   在册尺 `evaluate_provenance` 只从 `claims` 里数无据断言 ⇒ 载荷不带它就恒 0。这一格在今天的产物上**不具判据能力**（工具把 `claims_carried_n=0` 一起报出，就是为了不许把它读成绿）。
   🔴 尺子本体冻结，本件不改它；这句是**交回总控**的口径问题。
3. **逐类目 p95 的可解释性**：4 枚题的类目里 p95＝该类目最大值（`build_latency_cell` 的 rank＝ceil(n×0.95)），单枚题就能推动整格。
   实测：图表生成两跑 p95 差 3082.4 ms＝4 枚题里的抖动；无证据问题差 121.7 ms。⇒ 小题量类目的 p95「退化」读数近乎不可解释，本件对它同样落样本闸。
4. **三族样本不足**（图表生成／无证据问题／工具调用各 4 枚）：既判不了退化，也判不了「底」，一律 `insufficient_sample`。
5. **仓内历窗（run5／run6／run7／run8p2／run9／未名那份）与今天不可同表**：它们不带 `revision`／`fixture_sha256`，代次不可证（§2B）。
   要把它们并进来，缺的是**当年报窗记**——那是采集侧的件，本件不补造。
6. **侧车帧账没被在册尺吃过**：三份 report 的 `latency_ms.frame_ledger_rows` 现读**全为 0**，且 report 里没有 `approval_ledger` 那一格
   ⇒ 收窗跑分那条命令当时没设 `EVAL_APPROVAL_LEDGER`／`EVAL_SIDECAR`。⇒ 「p95 与逐发帧账对过」这句在这三扇上**不成立**；
   本件逐类目 p95 因此**沿用报告同口径**（只吃 answers 的实测跨度），不另起一把——工具把这条写在 `reconcile.notes` 里。
   甲案那把可判子集尺不受影响（它读题源里的 R401 处置，现读 deducted_n 19／分母 86，与账上两句数一致）。
7. **引证血缘**（`provenance_status` 与「29 条无出处」那一族，`docs/handoff/2026-09-23-v1-acceptance-record.md:53` 问的就是它）：本件**不测**。
   它需要在册血缘量具，属 R580／血缘那一格。本纸只在 §7 里把 approval-03 的形状读数递过去。

---

## 9. 交付物与复现命令（三条，全部只读）

- 量具：`scripts/r634_category_delta.py`（只读数、不改数；退出码写死 0 干净／2 检出退化／3 取不到／4 判不了；产物缺省落 stdout，`--out` 指进仓内直接拒）。
- 离线牙：`tests/test_r634_category_delta.py` 10 枚，全合成样本，真窗数一枚都不当钉。

      .venv\Scripts\python.exe -X utf8 -m pytest tests/test_r634_category_delta.py -p no:randomly -q
      ..........                        [100%]        ← 实取：10 passed；R56 端口闸门 blocked connect attempts 0（全程离线）

- 本纸全部数字的复现命令：

      .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --window run19 --window run20k --out %TEMP%\r634-run18-19-20k.txt      # rc=4
      .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --window run19 --window run20k --format json --out %TEMP%\r634-run18-19-20k.json  # rc=4
      .venv\Scripts\python.exe -X utf8 scripts/r634_category_delta.py --window run18 --report docs/testing/evaluation-report-run9.json --report docs/testing/evaluation-report-run8p2.json --out %TEMP%\r634-mixed-generations.txt   # rc=4

- 牙各自钉的那一条：① 跨代次掉题必须判退化并点名到题号；② 同窗喂两遍必须零摆动；③ 3 枚题的类目必须落样本不足不许落绿；
  ④ 件缺一枚必须 rc=3 并明写「取不到」；⑤ 底没量出来时跨代次那一组也不许宣布退化；⑥ 与报告对账破必须 rc=3；
  ⑦ 判分必须长在在册尺上（把 `_is_correct` 换成常真，本件的数跟着变）；⑧ 只读不改数＋`--out` 指进仓内直接拒；⑨ 掉分四型（答得不同／没答／哨兵／批准失败）逐枚点名。

## 10. 结论（只写量到了什么／量不到什么）

- 量到了：**同码同条件两跑之间，逐类 correctness 的摆动底最大 0.1666（6 枚题那一族掉 1 枚＝0.1666；19 枚那一族掉 3 枚＝0.1579）**，
  逐类目逐指标的底在 §4，逐枚搬动的题在 §4/§7；p95 两跑之间差到 12.4 秒；类目净零会抹掉头尾相消的两枚翻面。
- 量到了：**今天三扇里翻分 11 枚全部是「答得不同」**，「没答／哨兵／批准失败」三型实例为 0 枚（侧车与 answers 现读）。
- 量不到：**任何一格跨代次退化**——盘上没有第二代窗。工具对整张表交回 `rc=4 判不了`，不是 `rc=0 干净`。
- 量不到：`unsupported_claim_rate`（载荷不带 `claims`）、三族 4 枚题的类目、仓内历窗的代次、逐类目 p95 在小题量类目上的解释力、引证血缘。
- 🔴 本纸**不写**「A④ 达标」，也**不写**「逐类不退化成立」，也不写「不成立」。那一句归业主与总控判；
  上一班那句「别再抄上一班那句逐类不退化」在本班同样成立：**这一格的底没量稳之前，任何一句「不退化」都是抄的**。