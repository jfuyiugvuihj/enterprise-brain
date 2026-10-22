# run8 相 2 真机窗判读（队列道 · 报告档 20 题 · 2026-09-25 17:51:42–18:18:00）

> 本班（第八班第五格）全部读数**现取**：账件见 §六，每个数字都能从仓内那五枚文件 + `docker exec … psql -Atc` 复算。
> 计划与前置条件在 `docs/testing/run8-phase2-plan-2026-09-25.md`；本文只写**测到了什么**与**判据翻不翻**。

## 0. 窗口形状（先钉口径，后谈判决）

- 开关：`REPORT_LANE_VIA_QUEUE=on` + `MODEL_PREFILL_TOKENS_PER_SECOND=1200` + `MODEL_DECODE_TOKENS_PER_SECOND=40`（三枚都在 backend/worker/scheduler 三容器进程里逐枚复取命中；`deploy/.env.server` 被 `.gitignore:11` 忽略，跟踪态凭据只有本文与计划第五章）。
- 样本：仓外 20 题子集，`tier` 字段实测全为「报告」（report-01..12 / metric-16..19 / tool-01..04），已按 run7 惯例入仓为 `docs/testing/bank-run8p2-subset20.jsonl`。分类计数：报告生成 12 / 口径冲突 4 / 工具调用 4。
- 时长 26 min 18 s（首行 ts 17:52:36、末行 ts 18:18:00），20/20 收齐，`attempt>1` = **0**，哨兵 = **1**（`report-04`）。
- 🔴 被测镜像 revision = `75d9a6d`，落后当时主树六枚 ⇒ **本窗读数是「行为级」证据，不是验收级**；镜像重建后 D 三格必须复测（尤其 R246 之后 `auth.py` 变了）。
- 争用条件（毫秒级读数一律带这句）：与四枚 Agent 并发施工同窗。采样 25 次，同机 python 进程 4→**30**，空闲内存最低 **2.8 / 31.6 GB**；两枚 500 与 `report-04` 重投都落在争用段内。

## 1. 五格判决

| 格 | 判决 | 实测凭据 |
|---|---|---|
| **D-1** 队列终态 | 🟡 **形状过 / 内容不过** | `queue.final`：done **19** / stalled **1**（`report-04`：`context_limit_exceeded` 连败两轮 + 载荷静默 300 s 撞 `QUEUE_STALL_SECONDS`，正文 18:09:03 才到）。`polls` 合计 519（median 17.5 / max 126）、`blips` **2**（真 500，`psycopg.errors.ConnectionTimeout` ⇒ R222 判据② 按设计生效）、`relogins` **0**、`wait_ms` median **49,942.9** / max **441,591.7**。内容：20 题只有 **8 题交回真正文**，**11 题交回同一句 37 字挂起文案**，1 题 `<no-bytes-emitted>` |
| **D-2** usage 可读 | 🔴 **不过** | 客户可读面**根本没有 `usage`**：sidecar 16 键无该尺，frames 28 键无该尺，`app/api/v1/chat.py` 全文 `total_tokens`/`usage` **各 0 命中**，`done` 载荷写死 `{'type': 'done'}`（**两处**：`chat.py:1838` 与 `chat.py:2017`），`/queue/status`（`chat.py:3910`）只回 `{status,request_id,result,failure}`。服务端补尺（真库 `model_calls`，按本班那 20 个 request_id 查）：**70 行 / 19 个 request_id / 2 行 token 为 NULL / 68 行双非零**，`status` completed 68 + failed 2，`error_code` `context_limit_exceeded` ×2，Σinput **91,271** / Σoutput **18,859** |
| **D-3** 出处随答案 | 🔴 **不过** | `events[]` 直方图只有 `{queued:20, done:20}`；含 `sources` 的行 **0/20**，`evidence_n>0` **0/20**，answers 里 `evidence` 非空 **0**。根因读码定死：worker 落终态只写正文字符串——`deploy/queue_worker.py:366` 与 `:471` 都是 `queue.complete(request_id, answer)`，`sources` 折进 `aggregate_agent_result` 之后再没回到客户端 ⇒ **队列道在契约上就没有出处** |
| **A②** 流式逐字 | ⚪ **本窗物理判不了**（不是通过） | 帧账已换代（28 键/行，run7 是 21；新增 `frames/events/stream_clock/queue/first_visible_at/first_visible_event/first_visible_ms` 在 20/20 齐），但 `frames[]` **20/20 为空**、`text_frames>1` **0/20**、`criterion_two_holds` **0/20** ⇒ 单字碎片 0、<20 字帧 0、最大帧间隔无量可算，**这三格是空集**。对照：同这 20 个 id 在 run7 同步道 `text_frames>1` = **19/20**、`criterion_two_holds` 18/20，而那 20 行零枚有 arrival 键 ⇒ runbook §14 那句「A② 与 D 三格同轮互斥」成立，判它必须另开一扇 `REPORT_LANE_VIA_QUEUE=off` 的窗 |
| **A④** 逐类不退化 | 🔴 **三格全退化** | 基线 = run7 同步道 ∩ 同 20 行：correctness **0.55→0.30**、evidence **0.85→0.40**。分类：报告生成 12 行 0.50→0.3333（ev 0.8333→0.00）／口径冲突 4 行 0.50→0.25（ev 0.75→0.00）／工具调用 4 行 0.75→0.25（ev 0.25→0.00）。🔴 **0.40 是假分数**：`app/quality/eval.py:140` 用 `has_evidence or not requires_evidence`，这 20 行里 **8 行 `requires_evidence=false`**（tool-01..04、report-05、report-08、report-09、report-10），0.40 = 8/20 全来自不要求证据的行 ⇒ **真交回出处 0/12** |
| **B** 首屏 | 🟡 **补上尺，不翻绿** | `first_visible_ms` n=**20/20**（run7 无此列）：median **73.7 ms** / p95 **394.0 ms** / ≤1000 ms **19/20**。但 20/20 的首屏事件都是 `queued`（回执卡）⇒ 量的是「回执上屏」不是「正文上屏」，与 run7 那套量正文的 p50 24.3 s / p95 121.4 s **不可比**；且按计划书 §6 的 09-24 裁定，「首屏 ≤1 s」属 B 行、已移出 V1 门槛 |

## 2. 这扇窗真正的收获：三处地基缺陷被量出来了

1. **队列道没有 HITL 恢复路径（P1 产品缺陷）**。worker 侧 20 行终态：`status` success 17 / partial 3，`awaiting_hitl` **True 12** / False 8。那 12 枚里 11 枚把 37 字挂起文案当正文交回（「本轮在「📋 导出报告」前等待你确认…」×10 + 「📈 生成图表」×1），第 12 枚是 `report-04` 的零字节。同步道靠客户端 `APPROVAL_ROUNDS` 顶过去，**队列道顶不过去**——`/queue/status` 的回载里没有可批准的东西。这不是慢，是**报告档在队列道里根本走不完**。
2. **零枚模型调用却报终态**。request_id `64c3ef3b49174fc4b03994af7b0364a6`（题面「把上面那张图表插进正文」，tool 档）在 `model_calls` 里**一枚都没有**，worker 记 `status=partial awaiting_hitl=True`，而队列侧 `final=done`。与 R37 立的「谎报终态」同一形状，只是换了一条道。
3. **标定改判是对的，新墙换到了位置**（R214 判据本班复核全过）：`budget_unaffordable` **0**（相 2 首测曾 3）、`concurrency budget exhausted` **0**（曾 2）、关键词召回退化 0、查询改写失败 0、`resolve host 'postgres'` 0；`rewrite_payload_unparseable` 2。换尺后放行成功的那一跳在日志里读得到：`prompt_tokens=1908 budget_verdict=fits affordable_max_tokens=4110`。撞上的新墙是**上下文顶**：`prompt_tokens=2691` 与 `2778` 各一次 `context_limit_exceeded`（`+ max_tokens=1536 > n_ctx=4096`），两次都在同一个 request_id `edf880c8…8af1e62db40ede58`，即 `report-04` ⇒ 就是给业主讲过的「口子二」第一次拿到**真机发生率**。

## 3. 三处口径陷阱（本班现场踩到，写下来给下一班）

- **PG 存 UTC，日志是本地**。用 `started_at between '2026-09-25 17:51' and '18:19'` 查 `model_calls` 得到 **0 行**——那是假零。正确写法：`09:51Z–10:19Z`，或干脆按 request_id 集合查（本文所有真库读数用的是后者）。
- **`\$REDIS_PASSWORD` 在 `docker exec … sh -lc` 里不回展开**（runbook P-18），`wc -l` 于是给出第二个假零。正确形态：`docker exec -e RG=<pw> … redis-cli -a "$RG"`，本机清前 0 / 清后 0 / `dbsize` 3。
- **常驻 keepalive 会死**（runbook P-19）：`%TEMP%\ka.txt` 停在 12:59:15、零枚 python 常驻 ⇒ 开窗前必须自己重挂 `SetThreadExecutionState` 并每 240 s 续一次，否则机器一睡整窗作废。

## 4. 从这扇窗立的单（编号已排，避开预留的 R240/R241）

| 单 | 内容 | 独占写域 | 一句话判据 |
|---|---|---|---|
| **R253** | 反证钉 overlay 化：不许就地改写被跟踪文件 | `tests/test_r48_headline_*.py`、`tests/test_r156_*.py` | 同一 HEAD 连跑三次 `-n 8` 门，`chat.py` 系钉零漂移；反证强度一枚不许掉 |
| **R254** | 队列道客户端可见契约三格（HITL 可批准出口 + `sources` 回客户端 + `usage` 上可读面 + 零模型调用不得报 `done`） | `app/api/v1/chat.py`、`deploy/queue_worker.py`、`app/queue/**`、`docs/api/contract-v1.md` 队列节 | 20 题里 `awaiting_hitl=True` 的那 12 枚必须能批准续跑并交回真正文；`done` 载荷必须带 `usage`；带出处的题必须能在客户端读到 `sources`；`model_calls` 为零的 run 不得 `final=done` |
| **R255** | 报告档上下文顶（`MODEL_CONTEXT_TOKENS=4096`） | `app/agents/contracts.py`、`app/common/model_budget.py`、`.env.example` | 2691/2778 这两类 prompt 尺寸在本窗那题上不再 `context_limit_exceeded`，且窗口抬升与并发预算配套（只改一头判红） |
| **R256** | 今天欠的三列：`artifacts.deleted_at` 未落列、`dataset_versions` 无 scope 列、裸机路径缺省 `PERSISTENCE_BACKEND=json` 致登记重启即失 | `migrations/0015_*.sql`（**唯一持迁移者**）、`migrations/manifest.json`、`app/storage/persistence.py`、四枚目录尾号引信件 | 列落库 + 尾号引信四枚连名带断言一起改口 + 真库执行一次 |
| **R257** | Trace 兜底两笔（兜底窗口事件未回填六表、`TRACE_STORE_PATH` 卷此后只含兜底行） | `app/trace/**` | 拟由 `Poincare` 续做，波次二 |
| **R258** | runbook 两处假零 + 相 2 账件入仓惯例（本文 §3、§6） | `docs/testing/2026-09-17-eval-real-run-runbook.md` | 总控自办，不占 Agent |

## 5. 阶段门口径的净变化（看板 §4CF 以本节为准）

- **A②**：仍不翻绿，且**新增一条硬前置**——判它必须另开一扇 `REPORT_LANE_VIA_QUEUE=off` 的小窗，本窗结构上判不了。
- **D**：三格全红，红因已点到文件名与行号（`queue_worker.py:366/:471`、`chat.py:1838/:2017`、`chat.py:3910`），可开工，等 R254。
- **A④**：本窗不成立（三格退化），且退化主因是 D-1 那条挂起文案顶掉正文 ⇒ R254 并树后必须先复测 D-1 再谈 A④。
- **B**：多了一枚 `first_visible_ms` 尺（回执口径），V1 门槛不变（B 行已移出）。
- **C**：本窗未采证（越权 0 条那一格仍属未验）。

## 6. 账件（sha256 前 16 位，全部入仓）

- `docs/testing/sidecar-run8p2.jsonl` — 6,997 B — `8b0e58a146bda412`（16 键，无 `usage`）
- `docs/testing/sidecar-run8p2-frames.jsonl` — 24,827 B — `c861ae6bbc22f14e`（28 键/行，`frames[]` 20/20 空）
- `docs/testing/answers-run8p2.jsonl` — 18,007 B — `1e35827a0c0a1610`（`evidence` 非空 0/20）
- `docs/testing/evaluation-report-run8p2.json` — 968 B — `ef6bd49c…`（correctness 0.30 / evidence 0.40 / unsupported 0.0 / latency avg 78,874.57 ms、p95 154,618.314 ms、max 441,674.643 ms）
- `docs/testing/bank-run8p2-subset20.jsonl` — 5,109 B — `a138beb8edbb52bd`（20 题原文，`tier` 全「报告」）
- run7 对照基线（前一班已入仓）：`docs/testing/evaluation-report-run7.json`、`docs/testing/sidecar-run7-frames.jsonl`
- 语料未动：本班现取主树 `git status --porcelain` 除容器自写的 `chroma_db/chroma.sqlite3` 外**零脏项**，被跟踪的语料与评测集一枚没变（前一班记的 P-17 before/after 差 0 / 97 文件与此一致）。

