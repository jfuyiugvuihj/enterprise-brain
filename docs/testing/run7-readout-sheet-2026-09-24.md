# run7 判读表（09-24 16:5x 开窗前写好，收窗只填数——不许现场再想口径）

**为什么预先写**：run5→run6 那次 `evidence 0.7143` 掉了 0.067，事后才逐题对账发现是 R122 装箱诚实的**预期代价**；A④ 第一次抓到真退化（run4 `doc-19`）也是事后才归因。⇒ 读数与判据必须**开窗前**钉死，收窗只做填数。

**开窗前置已实测三格**（09-24 16:1x，总控亲跑，不是引用）：`scripts/seed_workspace.py --check` → `RESULT ok documents=100 datasets=1 owners=1` **exit 0** ｜ Redis `answer:*` → **0**（⚠️ runbook 第 8 步原文那条命令跑不通：容器内 `$REDIS_PASSWORD` 展开成空值 ⇒ `NOAUTH`；可用写法是 `docker exec -e RG=<deploy/.env.server 里的口令>` 再 `-a "$RG"`）｜ 保活 `%TEMP%\\ka.txt` = `16:18:44 SET=0x80000003`（新鲜、240 s 一续）。🔴 三格**开窗时复跑一遍**，早上的数不算今晚的数。

**基线 = run6 已并树原件** `docs/testing/evaluation-report.json`（sha256 前缀 `5b9d59018f4b9a2b`，3004 B，并树 `4dcbd30` 09-24 09:17）：`answer_correctness 0.5143`（甲案）／`旧口径 0.5238` ｜ `evidence_coverage 0.7143`（两口径同值）｜ `unsupported_claim_rate 0.0` ｜ `total 105` ｜ 审批腿 `19 题取得终答 / 批准失败 0` ｜ 🔴 `latency_ms.average 351121.76 / p95 163262.073` = **冻结污染值，不采信**（R205a `0997489` 之后新窗不再产生；见 runbook §17 第 14 步最后一条）。

## 一、逐格判据（相 1 = 全 105 题，`REPORT_LANE_VIA_QUEUE` 保持默认关）

| 格 | 判据（pass 条件，写死） | 读哪一格 / 哪个文件 | run6 基线 | 谁判 |
|---|---|---|---|---|
| **A①** | 问答档 `n=64` 的 `p95 ≤ 90 s` | sidecar `wall_ms`，按 id 前缀 `doc/chat/metric/...` 里问答档那 64 题（🔴 不许读 `answers.latency_ms`） | `median 27.9 / p95 68.9 / max 80.9` ✅ 二连 | 总控亲算 |
| **A①整表** | **口径未定 ⇒ 不判**（业主项 ⑦） | 整表 p95、分析档、报告档三行照实写数，**不写绿也不写红** | 整表 143.8 / 分析 212.1 / 报告 146.6 | 等业主 |
| **A②** | 帧账 105 行里 `criterion_two_holds` 为真的题数 **> 0 且逐题能解释**；受控纠正轮必须读 `uncorrected_breaks == 0 → verdict True` | `sidecar-runN-frames.jsonl`（六条件：`text_frames>1 且 max_stream_frames>1 且 uncorrected_breaks==0 且 missing_chars==0 且 extra_chars==0 且 last_frame_covers_answer`） | run6 **0/105** ❌（整段一次性到达，`text_frames=1`） | 总控亲算 + `rehearse_eval_window.py --switches` 在**最终 HEAD** 上先复跑（R218 窗内第 7 格） |
| **A③** | 容器内看得见卡 | `docker logs ollama-1` 的 `load_tensors: CUDA0` | ✅（H11 已拿到） | 直读 |
| **A④** | **11 类逐类 correctness 一类都不许低于 run6** | `evaluation-report.json.category_metrics` | 文档问答 .6842／多轮 .4167／**口径冲突 .3158**／Excel .5833／洞察 .5714／图表 .75／审批 .8333／跨部门 .1667／无证据 .25／工具 .75／报告 .5 | 总控逐类亲算 |
| **A④归因纪律** | 涨了要写清是谁救的；**R206b 的离线预测**是口径冲突族 `.3158 → .4737`、全库答对 `54 → 57`（离线复算，非真机）；R216 只救 `metric-08` 那一枚「选错边」 | 逐题 `answers-runN.jsonl` × `_is_correct` 现算，再与 `category_metrics` 对表（不吻合 = 判分器被改过） | — | 总控 |
| **C-1 缓存命中显式标注** | 🔴 **R218 已离线判为「不可测」**：`payload` 与 `sidecar` 里零枚含 cache 标记，命中腿在 `transport:467` 是硬抛停整 shard ⇒ **只能按「开窗前 `answer:*`=0 + 一旦命中即停窗」判**，不许去 `answers-run7.jsonl` 找那一列（它不存在） | Redis + 窗内日志 | — | 窗内现场 |
| **C-2 评测集分数不退化** | `answer_correctness ≥ 0.5143` **且** `evidence_coverage ≥ 0.7143` **且** 逐类见 A④（🔴 两格合判，不许只报总分涨） | `evaluation-report.json` | 0.5143 / 0.7143 | 直读 + A④ |
| **越权 0 条** | `跨部门权限` 族不许出现不该看的正文；`scope-*` 逐题引证集合与 run6 一致或更严 | 逐题 + R193 矩阵件 | 越权 0 格 | 总控 |
| **谎报率** | `unsupported_claim_rate` 必须仍为 **0** | 报告直读 | 0.0（run2–run6 五连 / 加本轮六连） | 直读 |

## 二、相 2 = 只跑报告档 12 题（`REPORT_LANE_VIA_QUEUE=on`）

🔴 **为什么不能与相 1 同轮**：报告档一旦走队列道，回答是取回整段、不逐片累计 ⇒ 帧账必然 `(1,1)`，会把 A② 洗成假红。两判据同轮物理互斥（runbook §17 第 14 步）。

| 格 | 判据 | 读哪 | 前置动作 |
|---|---|---|---|
| **D-1** | 12 题端到端：入队 → worker 跑完 → `/queue/status` **取回正文**（不是只取到状态字面） | `answers-run7b.jsonl` + 容器日志 | 🔴 **两相之间复跑 P-18 清 `answer:*`**，否则相 2 命中缓存、队列道根本没走过 = D 三格假绿 |
| **D-2** | `usage` 非零（逐题，不是平均） | sidecar / 报告 `usage` 列 | — |
| **D-3** | `sources` 在流里（逐题能追到引证集合） | `answers-run7b.jsonl` evidence 段 | — |
| **D-漏停** | 收窗时 `queueWatches` 计时器全部停干净；🔴 R218 离线抓到 `frontend_unhandled_final=[dead]`、`adapter_unhandled_final=[cancelled,dead]` ⇒ 窗内若出现 `dead`，逐题核 `kind=queued_polled` 的 `wall_ms` 是否贴近整段 deadline（贴 = 白花） | 前端 + 适配器日志 | 现场判，别拿最坏情形当期望值写进结论 |

## 三、收窗动作（同批，缺一格就是白跑）

1. `answers-run7.jsonl` + `evaluation-report.json`（+ 相 2 的 `answers-run7b.jsonl` / 报告）**同批并树进 `docs/testing/`**（runbook §17 第 13 步：不留逐题判定 = 下次只能判红不能判因）。
2. `P-17` 语料快照 `corpus_before.csv` ↔ `corpus_after.csv` `Compare-Object` 无输出。
3. 逐格判读**填进本页表格的「run7 读数」列**（收窗后追加一节，不改本节文字）。
4. 🔴 只有 A①（问答档）+ A② + A④ + C-2 + D 三格全绿、且**业主项 ⑦ 整表口径已裁**，才允许写「阶段 A 通过」；缺任一格就照实写「V1 尚不能宣布」。
