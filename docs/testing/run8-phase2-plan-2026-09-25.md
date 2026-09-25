# run8 相 2（D 门复测）开窗计划 · 09-25 第八班第二格立（基线 `6b6abcd`）

> 本页只写**相 2 复测**相对 run7 相 2 首测（`run7-readout-sheet-2026-09-24.md` §四，首测即红、一题试点即停窗）的差额。既有 P-步骤一律引用 `docs/handoff/2026-09-17-eval-real-run-runbook.md` 与 run7 判读表 §一/§二/§三，**本页不复制第二份**。

## 0. 首测为什么停窗，以及现在改了哪三样

| run7 相 2 首测的红 | 根因单 | 现在（`6b6abcd`） |
|---|---|---|
| `report-01` 正文真生成 1519 字却被丢弃，客户端拿到 `status=done, result=null` ⇒ 量具判 `blank` 打哨兵 | **R227**（并树 `5830422`）租约丢失即丢结果 + 谎报 `done` | 已改码：不再丢弃、不再谎报 |
| 队列道里 `[Model] concurrency budget exhausted` ×2 ⇒ 查询改写静默退回原问题，且不进任何分数 | **R228**（并树 `5a0fea6`）改写腿 `acquire(wait_seconds=0)` 逢撞必输 | 已给非流式改写支 15 s 上限等待 + ERROR 计数 `leg=rewrite` |
| 量具见 `done` 取不到正文就停表，`cancelled/dead/expired/failed` 分不清 | **R222**（待并，本计划的前提） | 九枚 `queued_*` kind，五终态可区分 |
| 间歇 500 `failed to resolve host 'postgres'`（78 发里 1 发） | **R229**（并树 `e1511cb`）+ **R230**（`ccf8942`）+ **R238**（在途，只造边界不迁调用点） | 鉴权侧已有超时+有界重试+节流重探 |
| 🔴 `budget_unaffordable` ×3（`affordable_max_tokens` 710/816/531 全 `< min_answer_tokens=1536`）+ `room_left=83 fitted=0 dropped=5` | 见本页 §1，**这条才是报告档走不完的那堵墙** | **未解**，且今天能证明它是算术必然、不是运气 |

## 1. 🔴 开窗前必须先量的两枚率（R214 路 A·重标定，非业主偏好）

事实（本班 12:1x 在 `6b6abcd` 现场取，全部零模型调用）：

- `app/common/model_budget.py:223-224` 的**代码默认**是 `PREFILL=35.0 / DECODE=8.0` tok/s，`.env.example:115` 自陈这来源是"**CPU-only floor** measured …35.2 prefill / 8.18 decode，向下取整"；
- 运行中容器里 `MODEL_PREFILL_TOKENS_PER_SECOND` / `MODEL_DECODE_TOKENS_PER_SECOND` / `MODEL_REQUEST_TIMEOUT` **一枚都没设**（`docker exec … env | grep MODEL_` 只出 `VECTOR_DUAL_WRITE=on`）⇒ 进程用的就是这两枚 CPU 地板值；
- 而链路今天**不是 CPU**：`docker exec enterprise-brain-ollama-1 nvidia-smi` 回 `NVIDIA GeForce RTX 4060 Laptop GPU, 0 MiB / 8184 MiB` ⇒ 有卡、且**此刻没有任何模型常驻**（`ollama ps` 空表）。

**算术（不需要跑模型就能下的结论）**：`MODEL_REQUEST_TIMEOUT=120` 是单请求天花板，`MODEL_MIN_ANSWER_TOKENS=1536`（分析档 = `TIER_MAX_TOKEN_DEFAULTS[ANALYSIS]`）是"至少得写完这么多"的下限。decode 按 8 tok/s 算，**光写完 1536 枚就要 1536 ÷ 8 = 192 s**，还没算 prefill ⇒ 在 120 s 天花板下**任何 prompt 长度都付不起**。这正是首测那三条 `budget_unaffordable` 的形状，也是 run7 相 2 只跑一题就停窗的根因。

⇒ 三条路只有三条，且第一条免费：
1. **路 A（本班采纳，先行）**：真量一次 GPU 上的两枚率。两点法——一发"短提示 + 长输出"解出 decode，一发"长提示 + 输出 1 token"解出 prefill；各 3 次取中位，写明模型名/量化/是否常驻/显存占用。**判据是算术不是感觉**：实测 decode > 12.8 tok/s ⇒ 1536 下限在 120 s 内可付，把实测值写进 `deploy/.env.server`（🔴 镜像内/容器 env 改了必须 `--force-recreate`，`docker restart` 读不到新 env，见 `r59c-window-ops-2026-09-25.md` §1）；实测 decode ≤ 12.8 ⇒ 本机**物理上**付不起"分析档 1536 字下限 + 120 s 天花板"这对配置，那就只能三选一（抬 `MODEL_REQUEST_TIMEOUT` / 降该档 `min_answer_tokens` / 换更大的卡），**那一步才是业主决定**，且要带着实测数去问，不许空问。
2. 路 B（承认分析档付不起）：在 A 之前不下这个结论。
3. 假装没这堵墙、把相 2 再跑一遍拿同样的红：**禁止**，那是把同一枚墙再撞一次并称之为进度。

⚠️ 别把 R219 那枚 "10.2×" 当标定：它是一发**改写调用**（200 prompt token、输出很短）的端到端比值，prefill 主导，**拆不出 decode**。4060 8 GB 装 14B 必然部分层留在 CPU，decode 实测很可能就在 8-20 tok/s 之间——所以 A 必须先量再改。

## 2. 开窗前置（在 runbook P-步骤之上加的三格）

- **P-新 1**：§1 的两枚率量完并落 `deploy/.env.server` + `--force-recreate backend worker scheduler`，容器内复读 `env` 与 `read_backend()` 同批取凭据（R231 请的那发零副作用凭据在此补齐）。
- **P-新 2**：热机。`ollama ps` 今天空表 ⇒ 冷启每问都要付模型载入（相 1 整表 p95 107.9 s 的一部分就在这里）。用 `keep_alive` 常驻，窗内每分钟复核一次常驻还在（掉一次就把该题标注重测）。
- **P-新 3**：🔴 相 2 双旋钮**必须同时设**——`REPORT_LANE_VIA_QUEUE=on` **且** `EVAL_DECLARE_LANE_TIER=报告`。少设后者，12 道报告题根本不入队，R222 那 9 枚新 `queued_*` kind 一枚都量不到（run7 历轮就是这个形状：`chat.py:1955-1956` 要 `lane=='report'` 且开关 on 同时成立，而量具从前零个 `lane`）。
- 既有硬前置照旧：`powercfg /change standby-timeout-ac 0`（09-24 夜机器休眠冻住四枚 Agent 一整夜）、Redis `answer:*`=0（两相之间复跑 P-18，否则相 2 命中缓存＝队列道根本没走过）、P-17 语料 before/after、P-19 keepawake 5 min 内续租。

## 3. 一窗拿全（别再分三扇窗）

| 格 | 判据 | 读数来源 | 本页新增什么 |
|---|---|---|---|
| D-1 | 12 题：入队 → worker 跑完 → `/queue/status` **取回正文** | `answers-run8b.jsonl` + worker 日志 | 停表分得清五终态（R222）；`queued_done_no_bytes` 出现即 D-1 红，**不许**再判成 blank 哨兵 |
| D-2 | `usage` 逐题非零 | sidecar | — |
| D-3 | `sources` 在流里、逐题可追 | `answers-run8b.jsonl` evidence 段 | — |
| B-首屏 | 首屏可见 ≤ 1 s | 帧账 `first_visible_ms`（R223 新列） | 🔴 **本班裁定：run8 报表加 `first_visible_ms` 与断流窗口列**。B 门"首屏 ≤1 s"到今天为止**根本没有尺**——run7 的 p50 24.3 s / p95 121.4 s 量的是正文；R223 之后 `frames[].arrival_at` 才现成可导。新列不追溯历史，run6/run7 报表缺这 7 列是事实，抬头必须写"适配器已换代" |
| A-④ | 逐类不退化 | 与 run5/run7 同尺对账 | 只报实测，**不许**抄上一班那句"逐类不退化"（run4 抓到过一次真退化 `doc-19`） |
| R228 专项 | 改写不再被自己的闸门挡死 | worker 日志 `leg=rewrite` 行枚数相对 run7 相 2 基线的**下降** + stage ledger `rewrite` 段 p95 | 15 s 排队会让 `rewrite` 段 p95 **变长**——那是读数变诚实，不是产品变慢；两处口径同页写明 |

## 4. 收窗动作

1. 产物同批并树：`answers-run8b.jsonl` / 报告 / sidecar（含帧账）/ `corpus_before|after.csv` / `run8p2.stamp.txt`。
2. `deploy/.env.server` 的相 2 两行**删除并 recreate 还原**，容器 env 复量留凭据（run7 相 2 首测就是这么还原的，照抄）。
3. 逐格判读追加成 run7 判读表的新节，不改本页与 §二文字。
4. 🔴 §1 的两枚实测值无论涨跌都落文档；若走"本机付不起"分支，把**实测数 + 三条路的算术**一起交给业主，不空问。
5. 缺任一格照实写"V1 尚不能宣布"——阶段 A 目前只有 ①（问答档口径）与 ③ 绿，② 从未验过，④ 有条件；B/C/D/E 四门全未验。