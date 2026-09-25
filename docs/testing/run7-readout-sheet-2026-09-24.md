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


## 附：开窗后补钉的 A① 量尺口径（09-24 22:5x，第八班，🔴 不改上面任何一格判据，只补"怎么量"）

本班把 run6 的 sidecar 原件（`docs/testing/sidecar-run6.jsonl`）用类别组合反解了一遍，结果是：**板上 A① 那三个数（`median 27.9 / p95 68.9 / max 80.9`）只有用 {文档问答+多轮对话+口径冲突+审批判断+无证据问题+工具调用} 才复现得出来**（线性插值，误差 0.06），而本节上面 A① 那行写的成员、以及看板 §4BQ 正文写的成员是 {…+跨部门权限}（**不含审批判断**）——那一组实测是 `p50 27.5 / p95 72.9 / max 81.9`。⇒ **纸面上两处口径与它自己的读数对不上**（同一枚 n=64 有两套成员，都是 64 题，纯属巧合）：

- 口径来源核对：`pct(linear)` 与 nearest-rank 两种都试过，只有 linear + 上面第一组能逐位复现板上读数；`主动洞察 p95 231.3`、`图表生成 p95 254.0` 两格本班逐位复现成功 ⇒ 类别映射本身没错（错的是成员清单）。

**本班裁定（写死，不给下一个人留挑口径的空间）**：run7 的 A① **两套成员都算，两套都 `p95 ≤ 90 s` 才记绿**；任一套越线就照实写"问答档越线，且两套成员分别是多少"。整表 p95 与分析/报告档照旧**只写数不写绿**（业主项 ⑦ 未裁）。量尺：本班用仓外 `%TEMP%\evalrun\readout7.py`（只读，产物不入树），先拿 run6 原件自校再量 run7。
---

## 三、run7 相 1 读数（09-25 09:2x 总控亲算；测量基线 `8b86f4c`；产物 `docs/testing/{answers-run7,sidecar-run7,sidecar-run7-frames,evaluation-report-run7,evaluation-report}.json(l)` + `run7p1.stamp.txt` + `corpus_before/after.csv`）

**窗形**：开窗 22:36:19 → 收窗 00:06:29（**1 h 30 m 10 s**），`COLLECT_EXIT=0 / SCORE_EXIT=0`，**105/105 全收**、`attempts_gt1=0`（零重试）、`sentinel=0`、`first_token_at null=0`、sidecar kinds = `ok` 84 + `approved_ok` 21、`evidence_n_sum=328`、`tool_calls>0` 93 题。

| 格 | run7 实测 | 判 |
|---|---|---|
| **A① 问答档** | QA64-A `n=64 p50 30.9 / p95 68.0 / max 270.2`；QA64-B `n=64 p50 30.5 / p95 68.0 / max 270.2`。🔴 按本班钉死的"两套成员都算、两套都 ≤90 s 才绿"⇒ **绿**（run6 是 A 68.9 / B 72.9） | ✅ 绿 |
| A① 整表/分析/报告 | 整表 `n=105 p50 36.5 / p95 127.1 / max 270.2`（run6 107.9 ⇒ **变差 19.2 s**）；报告生成 `p95 142.0`；最贵一族=主动洞察 `p95 229.0 / max 268.7`、图表生成 `p95 183.7`、多轮对话 `p95 185.6` | **只写数不写绿**（业主项 ⑦ 未裁） |
| **A② 流式逐字** | 帧账 `criterion_two_holds` **93/105 为真**（run6 是 **0/105**），>0 且逐题可解释：9 枚 `text_frames=1` 整段一次性到达（`doc-07/chat-03/chat-06/chat-09/chat-10/metric-17/data-09/approval-06/scope-01`）、1 枚 `chart-01`（2 帧分属 2 流、每流 1 帧 ⇒ `max_stream_frames>1` 不满足）、**2 枚真断流**：`chart-03`（16 帧/2 流，`prefix_breaks=1 uncorrected_breaks=1`，断在第 2 流第 2 帧）、`tool-04`（3 帧/2 流，同形状）。两枚断流都 `missing_chars=0 extra_chars=0 last_frame_covers_answer=true` ⇒ **最终正文完整，断的是中间连续性**（客户端会看到一次重写），不是丢字 | 判读表字面判据**成立**；🔴 但"流式逐字无缺"这句产品语义今晚**不宣布**，2 枚未纠正断流另立案 **R225** |
| **A③ GPU 落点** | `qwen3.5:9b` 100% GPU / ctx 4096、`nomic-embed-text` 100% GPU、`inference compute library=CUDA name=CUDA0`（RTX 4060 Laptop 8 GB）——凭据是**开窗前**的现场（跟进单 §94 表）；🔴 相 1 窗内没单独留 `load_tensors` 档，本班不冒充"窗内亲验"。旁证：相 1 首题 `doc-01` 28.0 s 与全表 p50 同档（热机生效，没吃加载） | ✅（凭据时点如实标注） |
| **A④ 逐类不退化** | run6→run7：`口径冲突 0.3158→0.6842` UP(+0.3684)、`主动洞察 0.5714→0.7143` UP、`Excel计算/图表生成/工具调用/报告生成` 持平、🔴 `多轮对话 0.4167→0.3333`、🔴 `审批判断 0.8333→0.5`、🔴 `文档问答 0.6842→0.6316`、🔴 `无证据问题 0.25→0`、🔴 `跨部门权限 0.1667→0`；逐类 `total` 两侧 **11/11 全等**（同一把尺、同 105 行） | ❌ **红**（5 类退化） |
| **C-1 缓存显式标注** | 替代口径：开窗前 `answer:*`=0，相 1 全程零命中、零停窗 | ✅（按替代口径） |
| **C-2 分数不退化** | `correctness 0.5143→**0.5333**`、`evidence 0.7143→**0.7905**`、`unsupported_claim_rate 0.0`（六连零）；审批腿 `19-19-0 → 21-21-0`，批准失败仍 0 | 总分两格 ✅；🔴 但 C-2 后半句"逐类见 A④"是红的 ⇒ **C 行不翻绿** |
| **越权 0 条** | `scope-*` 引证集合对 run6：`scope-01/03/04/05` 两侧均 0 条、`scope-06` 两侧均 6 条一致；🔴 `scope-02` 漂移（5 条→4 条，其中 2 条 run6 未引：`GB-T 22239-2019…等保三级要求.txt`、`信息资产管理规范.txt`）⇒ 判据后半句"一致或更严"**字面不满足**。两条都是同一 principal 本来可见的语料 ⇒ "不许出现不该看的正文"= 0 条成立；越权格正式凭据仍是 R193 矩阵 51 格真红 0（`eef676c`） | ✅ 越权 0 条；另记一笔"引证集合不稳"＝R59c ① 要量的东西 |
| **P-15 查询改写失败** | **0** 条（同窗 backend 日志 5983 行，是活读数不是空读） | ✅ |
| **P-17 语料零变化** | `corpus_before/after` 各 97 枚，`Compare-Object` 差异 **0** | ✅ |
| 首片正文到达 | 客户端收到第一枚非空 `event:text` 相对该题起点：`n=105 p50 24.3 / p95 121.4 / max 269.6 s` ⇒ B 门"首屏 ≤1 s"按这把尺**判红**；R48 首屏卡的到达时刻今晚仍无量具（=R223） | ❌ 红（B 门首屏格） |

### A④ 红的逐题归因（本班用**同一把判分尺** `app/quality/eval.py:_is_correct` 对两份 answers 重算，零模型调用）

由对转错 **6** 题：`doc-08`(锚词`分开列示`)、`chat-11`(锚词`审批`)、`approval-03`(`无需超额审批`)、`approval-06`(`不允许拆分`)、`scope-06`(`不可以`)、`unsupported-01`(`无法确认`)。由错转对 **8** 题：`metric-04/05/10/11/13/14/18` + `insight-03` ⇒ 净 +2 题，与总分 0.5143→0.5333 对得上。

🔴 **6 题里只有 `chat-11` 是真产品退化**：run7 正文 340 字自陈"多次查询尝试未能成功获取 800 元金额的具体记录"（工具腿没算出来），且它就是全表那枚 270.2 s 尾巴。其余 **5 题语义仍然对，只是没逐字命中锚词**：`approval-03` 写"不需要走超额审批/无需提交超额审批流程"、`scope-06` 写"不能绕过"（锚词要"不可以"）、`approval-06` 走缓存写"不能拆分"（锚词要"不允许拆分"）、`doc-08` 写"需要分别开具发票"（锚词要"分开列示"）、`unsupported-01` 写"知识库中没有相关信息"（锚词要"无法确认"）。⇒ **A④ 这一红主要是判分尺的措辞敏感性，不是五处产品倒退**。这条正好是业主待批"改评测集"那格的现场证据：逐字 `must_contain` 会把语义正确的答案判成错。

### 本班三笔现场订正（不许下一个人接着抄错的）

1. 🔴 **P-15 第一遍是假绿**：09:0x 本班第一次量到 0，是因为当时 **Docker 引擎根本不在**，`docker logs` 走的是错误流、`Select-String` 数了个空。09:2x 复量（同窗 5983 行）才是真数。**教训**：任何"从容器日志数出来的 0"必须同时报"日志总行数"，否则等于没测。
2. 🔴 **00:06 收窗到 09:07 之间机器停过一次**：Docker Desktop 起不来，报 `%LOCALAPPDATA%\Docker\run\sailor-ingest.sock` 与 `%LOCALAPPDATA%\docker-secrets-engine\engine.sock` 两枚 **0 字节悬空重解析点** 改名失败（`fsutil` 读它们报 1920"系统无法访问此文件"）——同一枚病在这台机上已复发多次（那两个目录里留着 `.bak-192551 / .dead-220330 / .gone99 / .dead212755` 六枚历史归档）。`Remove-Item`/`Move-Item`/`.File::Delete` 对悬空条目全部失败，唯一可行的是**给父目录改名**（不需要打开子项），本班按同法归档成 `run.stale0925` / `docker-secrets-engine.stale0925`，引擎随即恢复 `29.7.2`，七件容器 recreate 全 healthy，相 1 产物零损失。🔴 **绝不点弹窗里的 "Reset to factory defaults"**——那会连镜像带卷一起清（`8b86f4c` 后端镜像 + 已播种工作区）。
3. 🔴 **相 1 与相 2 之间隔了 9 小时**（不是连跑）：`ollama ps` 已空、Redis `DBSIZE=0`。本班重挂保活（`keepawake.ps1`，但 `SetThreadExecutionState` 这次返回 `0x80000000` 而不是昨晚稳态 `0x80000003`，`powercfg /requests` 要管理员权限量不了）⇒ 改用可查的两条硬前置兜住：`standby-timeout-ac = 0x0`（永不）、`HYBERNATEIDLE` 无此项、插电 100%。相 2 开窗前复量 P-18 = `DBSIZE=0 / answer:*=0 / noeviction` ✅。