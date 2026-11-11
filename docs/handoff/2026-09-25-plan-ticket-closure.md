# 计划书 §5.2 在册 28 号 · 逐单结案核对（R224）

- 单号 **R224** · 执行层代号 **Seneca**（沿用总控原给，不改名，避免再制造「一名多身份」）· 纯文书亲验单，**不改一行产品代码**。
- 本文件是 `docs/handoff/2026-09-17-perf-architecture-plan.md` §5.2 那张 28 号表（R25–R52，其中 **R39 不建**）的**结案核对**：它不推翻「产物在树」这笔账（那笔账 `723550c` 已经订正为「零产物 = 0 枚」，本单复算一致），它回答的是下一个问题——**产物在树之后，逐单的 §21 判据到底达没达**。
- 结论口径只认两样东西：磁盘字节（文件:行号）与命令输出（含 EXIT 码）。**不认名册结案行、不认提交正文里的自述、不认「grep 不到单号」**。

## 0. 口径、快照与取证纪律

### 0.1 快照（必读，行号以此为准）

- 派工单钉的快照是 **`866c2f3`**，本文件**所有行号一律在 `866c2f3` 上实取**。
- 🔴 **行号计数口径（抄用前必读，前两班翻车的一枚隐形根因）**：本文件行号一律是 **按 LF 计数**（即 `git show <rev>:<path>`、`rg -n`、`git grep -n` 得到的那一套）。**不要**拿 .NET `Get-Content` / `[IO.File]::ReadAllLines` 的计数来对：本班实测跟进单 `docs/handoff/2026-09-15-backend-followup-requests.md` = **3070 枚 CRLF + 25 枚 lone LF + 1534 枚 lone CR**（LF 总数 3095），凡是把 lone CR 也当断行的口径，会把 §21 那行 `| **R25** |` 数到 **993** 而不是 **497**。本文件 §1／§2 里的 `L497`…`L523` 全是 LF 计数，本班已逐枚用 `git show 866c2f3:` 复核命中（28／28 命中，见 §5.2）。
- 🔴 **主树是共享树，写作期间一直被别的班改**（本班 12:04:59 实测 `git status --porcelain` 见 ` M app/common/auth.py`、` M scripts/eval_transport_ask_v2.py`、`?? tests/test_r222_*`、`?? tests/test_r223_*`、`?? tests/test_r233_*`×2 等，**均非本单产物、本班零写入**；更早一次实测里还是 ` M app/rag/indexing.py` 与 ` M docs/api/contract-v1.md`，两枚随后被别人并树）。⇒ 本文件行号**一律锚 commit（快照 `866c2f3`）不锚工作树**：`git diff --quiet 866c2f3 HEAD -- <file>` 只比两枚 commit、看不见工作树未提交改动，所以「工作树行号==快照行号」只对未被并发脏化的文件成立。本班已把两枚被脏化过的被引文件按快照重核：`app/rag/indexing.py`（快照 2054 行；引用的 `:15`、`:18`、`:1741`、`:1865` 按快照逐条命中）与 `docs/api/contract-v1.md`（快照 1681 行；`:1370` 在快照上是 `## Three-Tier SLO Contract (2026-09-20, R105 甲半)`，在当时的脏工作树上该行已空 ⇒ 必须按快照读）。
- ⚠️ 取证期间主干**一直在动**，本班末次实测（12:04:59）HEAD = **`73eae8a`**，`git rev-list --count 866c2f3..HEAD` → **25**；`git merge-base --is-ancestor 866c2f3 HEAD` → **EXIT=0**。⇒ 本文件写完的瞬间主干仍可能再前进，但这**不影响本文件任何一条行号**（全部锚 `866c2f3`），只影响「两侧对照」那张表的右列。途中被本班记录并引用到的枚：R227 `5830422`、R221 前端 `9850969`、R59c `d13201f`、R230 `ccf8942`、名册 `237f9e9` / `47b6643`、R220 `20bc26b`、R59 系 `c731356`→`73eae8a`。
  - 其中被改最多的三枚（本班 `git diff --stat 866c2f3..HEAD` 原文读数）：`app/common/reliable_queue.py` **+252**、`deploy/queue_worker.py` **+83**（R227 `5830422`）、`frontend/src/components/ChatPanel.vue` **+67**（R221 `9850969`）。
- 本班把本文引用到的**全部**文件（含只写裸文件名者，按 `git ls-tree -r --name-only 866c2f3` 反查目录补齐去重）收成 **68 枚**，逐枚 `git diff --quiet 866c2f3 HEAD -- <file>` **复算五遍**：`a9dd17e` = 61 SAME / 3 DIFF；`47b6643`、`20bc26b`、`c731356` 三遍均 **61 SAME / 7 DIFF**；`73eae8a` = **60 SAME / 8 DIFF**（新漂的一枚是刚并树的 `app/rag/indexing.py`）。**漂移集合是随时间单调增长的**，所以本文件的引用一律记快照侧。8 枚 DIFF 全集 = `app/api/v1/chat.py`、`app/common/model_handler.py`、`app/common/reliable_queue.py`、`app/rag/indexing.py`、`deploy/queue_worker.py`、`docs/api/contract-v1.md`、`docs/handoff/2026-09-15-orchestration-board.md`、`frontend/src/components/ChatPanel.vue`（末枚是总控账本，仅 §4 勘误引它）。快照侧 LF 计数：`chat.py` 4002 / `model_handler.py` 638 / `contract-v1.md` 1681 / `ChatPanel.vue` 2256 / `reliable_queue.py` 376 / `queue_worker.py` 448 / `indexing.py` 2054。⚠️ 本班初稿曾记「`chat.py` 与 `contract-v1.md` 两侧总行数相同（4003 / 1682）」——**已被现测推翻**（那是含尾空的切分计数，且 `contract-v1.md` 两侧本就不同值）⇒ 作废。逐处左右列对照见 §6 第 8 条。
- 🔴 **对本单结论有实质影响的一枚是 `5830422`（R227）**：它改的正是 R37 判据③ 那面墙（结果丢弃 + 谎报 `done`）。本文件把 R37 判在**快照上的状态（未达）**，并另记 R227 之后的新状态与「必须在 R222 并树后重量一次」这句自陈。

### 0.2 取证纪律（本项目 §91 / §95 两次翻车换来的，本单逐条执行）

1. **绝不拿「某号 grep 不到」当「零提交/零产物」**。每一次报「不存在」，本文件同时给出**三种不同形状的查询**（结构名 / 提交正文单号 / 语义词族），并说明查的是哪一层。
2. **判默认值与开关是否可达，查调用点**，不只看签名（前任就是靠 `, 1)` 这个 grep 形态漏掉 `chat.py` 的 `Form(1)`）。
3. 引用任何数字前先问它有没有被后续实测推翻。本文件里所有分数、覆盖率、秒数**都是本班重跑重读得到的**，逐条附命令。
4. 「达 / 部分达 / 未达 / 需真机」四选一，**「产物在树」不构成「达」**。
5. 解释器一律 `.venv`：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（宿主 anaconda python 无 chromadb，用它跑出的红是假红）。定向件一次一发，**未**跑 `scripts/run_gate.py`、**未**加 `-n`、**未**同时开两发 pytest。
6. 未做（本单硬禁令，不是漏做）：动 Docker/容器/镜像、打模型、连真库、跑评测窗、`/api/v1/ask`。因此凡判据本身要求「墙上时间 / 真机握手 / 真并发」，本单一律写 **需真机** 或把那一格挂进对应门，**不用推测填空**。

### 0.3 逐号四格读法

每枚单给四格：**判据出处**（跟进单 §21 原文小节号 + 行号，不是计划书 §5.2 那行摘要）→ **产物落点**（文件:行 或 并树 sha，注明取读快照）→ **达成/未达成**（本班凭据）→ **凭据原文**（命令 + EXIT + 关键读数）。

---

## 1. 逐号核对（R25 … R52）

### R25 · 开发期热挂载 —— **需真机**

- **判据出处**：跟进单 §21 表 **L497**。原文：「改一行 `app/**` 后不 build 即生效；`verify_container_stack.py --skip-build` 仍能过」；禁改边界「不改生产 compose 的副本语义；挂载只加在 dev override 文件」。
- **产物落点**（`866c2f3`；工作树同值）：`docker-compose.dev.yml:1`（首行自陈 "NOT part of the delivered stack"）、`:34` backend `volumes:`、`:43` `"--reload", "--reload-dir", "/app/app"`、`:55` worker `volumes:`、`:59` scheduler `volumes:`；文档腿 `README.md:33`、`:39`（叠加层用法）；闸门腿 `scripts/verify_container_stack.py:22`（`COMPOSE_FILE = ROOT / "docker-compose.yml"`）、`:104-106`（overlay 拼接）、`:344`（`--skip-build` 开关）、`:370`（`if not args.skip_build`）。并树 sha：`ad85821`（实现）+ `b17b4dd`（合并）。
- **达成/未达成**：**边界那半边达**（生产 compose 零改动，实测到行）；**判据那两句需真机**——「不 build 即生效」和「闸门仍过」都是容器内事实，本单禁动 Docker，不做推测。
- **凭据原文**：
  - `git show --stat ad85821` → EXIT=0：`README.md | 23 +` / `docker-compose.dev.yml | 60 +` / `2 files changed, 83 insertions(+)` ⇒ **`docker-compose.yml` 零行改动**。
  - `git show --stat b17b4dd` → EXIT=0：同上 83/0（合并枚无额外产物）。
  - `rg -n "docker-compose.dev|/app/app" docker-compose.yml` → **EXIT=1**（生产 compose 里没有 dev 挂载）。三种形状均未命中：① 上面的字面挂载点/文件名；② `rg -n "reload-dir" docker-compose.yml` → EXIT=1；③ 结构层：`rg -n "volumes:" docker-compose.yml` 命中的全是数据卷（`chroma_db`/`workspace` 一类），无 bind-mount 到 `/app/app`。
  - `rg -n "reload-dir" docker-compose.dev.yml` → EXIT=0，命中 `:43`。

### R26 · GPU 诚实声明 —— **部分达**

- **判据出处**：跟进单 §21 表 **L498**。原文：「① 容器内 `nvidia-smi` 有卡；② **拿不到卡必须显式报错 + 稳定码**，不得静默 CPU；③ `/health/details` 能区分"模型太慢"与"机器没 GPU/内存不足"；④ 硬件基线（GPU/显存/最低配置）入文档，与 **R24 ②③ 合并验收**」；禁改边界「不许为了"绿"把 healthcheck 改成无条件 ok」。
- **产物落点**（`866c2f3`）：`docker-compose.yml:82-97`（ollama 设备声明；`:90` `driver: nvidia`、`:97` `NVIDIA_DRIVER_CAPABILITIES: compute,utility`）；`app/common/model_capabilities.py:112-152`（`:121` `COMPUTE_GPU`、`:127` `COMPUTE_DEGRADED_CODE = "model_unavailable"`、`:131` `REQUIRE_GPU_ENV = "OLLAMA_REQUIRE_GPU"`、`:144-152` `CPU_FALLBACK_MESSAGE`）；`app/common/monitoring.py:205-218`（`:210` `compute = inference_compute_state()`，`:215-218` 四枚上报键）；文档腿 `README.md:81-136`（「GPU 与算力诚实」）+ `:93`（真机验卡另立 **H11，由业主本人执行**）+ `:141`（机器判据，写「15 项」）。并树 sha（**以拆单子号并的树**）：`118801e`+`11f9b1f`（R26a）、`af027ce`+`6ee2f79`（R26b）。
- **达成/未达成**：**②③④ 达**（② 稳定码 `model_unavailable` + 显式 `OLLAMA_REQUIRE_GPU`；③ `/health/details` 三态在 `monitoring.py:215-218`；④ README 有专章且判据行数与实际用例数对得上）。**① 需真机**（容器内 `nvidia-smi`），且跟进单 README:93 已把它划给业主 H11。⇒ 判 **部分达**。
- **凭据原文**：
  - 四枚祖先校验：`git merge-base --is-ancestor {11f9b1f,118801e,6ee2f79,af027ce} 866c2f3` → 四条全 **EXIT=0**。
  - `.venv\Scripts\python.exe -m pytest tests/test_gpu_compute_honesty.py -q --no-header -p no:cacheprovider` → EXIT=0，**`15 passed in 0.21s`**（与 `README.md:141` 自陈的「15 项」逐字相符）。
  - **R26 独立结论的三种反查形状**（本班重做，不采信任何「查不到并树痕迹」的旧账）：① 提交正文单号 `git log --oneline --all --grep=R26` → EXIT=0，12 命中，其中 `11f9b1f`/`118801e`/`af027ce`/`6ee2f79` 四枚是产物枚，`fd8ae7c`/`c87e1df`/`c571083` 三枚是结案枚；② 拆单子号 `--grep=R26a --grep=R26b` → EXIT=0 命中同四枚；③ 语义词族/结构名 `git log --all -S"reservations" -- docker-compose.yml` 与 `-S"NVIDIA_VISIBLE_DEVICES"` → 各命中 `118801e` 一枚；代码侧 `rg -n "NVIDIA_VISIBLE_DEVICES|NVIDIA_DRIVER_CAPABILITIES" docker-compose.yml` → EXIT=0 命中 `:82-97`。⇒ **「R26 零提交」是字面 grep 的方法错，不成立**；它 09-17 记的结案在代码侧站得住（②③④），只有 ① 是业主格。

### R27 · 确定性计划命中不再发第二发 —— **部分达**

- **判据出处**：跟进单 §21 表 **L499**（原文：「① 第 2 发不再发生（日志计数）；② 先加测试钉住 `orchestrator.py:285-305` 兜底仍能纠正错派；③ 端到端 −≥35 s」；禁改边界「**不得删**兜底路径；不得改 worker 结果结构」）＋ §21.7 **L636-647**（结案与复核账）。
- **产物落点**（`866c2f3`）：`app/agents/orchestrator.py:397-403`（`:397` `if not state.get("redo")`，`:402` 日志 `[Supervisor] 确定性计划命中 → 复读第 1 发 dispatch，跳过第二发模型往返`）、`:311-325` `_deterministic_plan_hit`、`:328-336` `_prior_dispatch_decision`、`:393` 起「R27：确定性计划命中时把第 1 发的决策原样补回消息尾部」注释；兜底路径**仍在**：`:513-560`（关键词纠正，`:513` 注释「保留关键词兜底纠正（与 LLM 决策互为保险）」）、`route_main:479`、`Send` 出口 `:614`、无条件边 `:975-980`。并树 sha：合并 `6a4f02b` / 实现 `ce0b041`（§21.7 L638）。
- **达成/未达成**：**①② 达**，**③ 归业主（需真机）**——跟进单 §21.7 L646 原话「判据③「端到端省 ≥35 s」归业主：打 Ollama 的计时属并发红线」。⇒ 部分达。
- **凭据原文**：
  - `pytest tests/test_supervisor_roundtrip.py` → EXIT=0，**`8 passed, 4 warnings in 4.33s`**；`pytest tests/test_route_fallback_correction.py` → EXIT=0，**`13 passed, 4 warnings in 4.46s`**（判据② 的钉）。
  - `rg -n "跳过第二发模型往返" app/agents/orchestrator.py` → EXIT=0 命中 `:402`。
  - 判据① 的反证（本班未重跑，凭据在跟进单 §21.7 L644：总控在**未打补丁的主树 `fd8ae7c`** 上跑同一文件得 `3 failed, 5 passed`，三处全红在 `assert 2 == 1`）——本班只复核该行号所指的守卫今天确实在树（`:397` 的 `not redo` + `:402` 计数日志）。
  - 禁改边界：`git diff --numstat` 口径无法本班复算（合并枚 `6a4f02b` 的 +66/-0 记在 L640），本班改为直接验「兜底未删」：`rg -n "add_edge\(\"main_tools\", \"supervisor\"\)" app/agents/orchestrator.py` → EXIT=0 命中 `:975`，回路仍在 ⇒ 判错仍能升档那条不依赖被删的边。

### R28 · 多路改写条件触发 + fast/thorough 分档 —— **部分达**

- **判据出处**：跟进单 §21 表 **L500**（原文：「① 单跳问题走 fast 时**模型往返数为 0**；② 多块召回时 thorough 行为不变；③ 30 题评测不退化」；禁改边界「不得动 `:59 json.loads` 的失败语义（那是 R23）；不得顺手改检索权重」）＋ §21.6 **L629-633**（结案口径纠偏）。
- **产物落点**（`866c2f3`）：`app/rag/retrieval_pipeline.py:54-70`（档位枚举，`:60` `DEFAULT_TIER = TIER_FULL`，`:74` `ADAPTIVE_REWRITE_MIN_CHARS = 24`）、`:79-99` `resolve_rewrite_tier`、`:102-125` `should_rewrite_query`（`:117` `if len(text) >= ADAPTIVE_REWRITE_MIN_CHARS`）、调用点 `:868-876`（`:870` 条件触发，`:875` 日志 `检索档位 {tier}: 跳过查询改写，本次检索 0 次大模型往返`）；钉：`tests/test_retrieval_rewrite_tier.py:102-110`。并树 sha：合并 `1c0b08b` / 实现 `d2566e1`。
- **达成/未达成**：**①② 达**（默认 `full` ⇒ 现网零改变；`fast` 档跳过那一发阻塞往返并由日志与用例钉住）；**③ 未做**——§21.6 L633 原话「判据③「单跳省 ≥30 s」未跑 ⇒ **R28 不作完全结案**」，且 L631 立了硬闸「`RETRIEVAL_TIER=fast` 在 30 题评测对比跑完之前不得进入任何验收/演示配置」。⇒ 部分达（这一格是跟进单自己留着的话，不是本班加码）。
- **凭据原文**：
  - `pytest tests/test_retrieval_rewrite_tier.py -q --no-header -p no:cacheprovider` → EXIT=0，**`29 passed in 0.97s`**。
  - `rg -n "DEFAULT_TIER = TIER_FULL" app/rag/retrieval_pipeline.py` → EXIT=0 命中 `:60`（⇒ 默认仍是 full，闸门未被绕过）。
  - `rg -n "本次检索 0 次大模型往返" app/rag/retrieval_pipeline.py` → EXIT=0 命中 `:875`。

### R29 · 思考税 —— **未达**

- **判据出处**：跟进单 §21 表 **L501**（**重定义**口径：「`/v1` 上 5 种关思考写法全无效 ⇒ 迁原生 `/api/chat`，或做 `PARAMETER think false` 派生模型」；原文判据：「① `thinking` 字段实测为 0 字；② 生成轮 30.6 s → ≤22 s；③ **前置：R36 质量基线已建立**，制度题准确率不得下降；④ `tool_calls` 报文重做后权限/超时语义全复验」；禁改边界「不许只在 `/v1` 加参数就当完成；不许在无线上端点证据前宣布关掉了思考」）。
- **产物落点**（`866c2f3`）：`tests/test_r29_thinking_tax.py:1-24`（本单的实测结论自陈，D/E/F/G 四段宿主真机帧）、`app/agents/nodes.py:186-202`（thinking 模式一次性公告）、`:815-816`（`"timeout": http_timeout(...)`, `"extra_body": {"max_tokens": ..., **thinking_extra_body()}`）、`app/common/model_handler.py:461`（原生腿 `NATIVE_MAX_TOKENS_FIELD`）；落盘原始帧：`docs/perf/raw/think_off.jsonl`、`docs/perf/raw/rate_think2.jsonl`。并树 sha：`791568c`。
- **达成/未达成**：**未达**，且是**「判据② 被实测否证」级别的未达**：
  - ① 达成但是**空壳**——原生腿 `think:false` 之后 `thinking` 确实 0 字，同一串思考原文整段落进 `content`（`docs/perf/raw/think_off.jsonl` 里 `reasoning_chars: 108` 那一类形状即其证据形）。本班在 `think_off.jsonl` 首枚 JSONL 帧读到 `reasoning_chars=108`、`content_chars=127` ⇒ 「字段为 0」≠「思考已关」。
  - ② **未达**：本班重读 `rate_think2.jsonl` 得同位对照 `think_off_decode300 wall_s=40.700` / `think_on_decode300 wall_s=47.662`；用例文档自陈生产形状 A/B n=8 的中位墙钟比 **0.9981**，把 30.6 s 外推 ⇒ **30.5 s**，距 ≤22 s 差 8.5 s 量级。
  - ④ 未复验通过：两腿 `tool_calls` 报文形状**互斥**（原生只收 `arguments` 对象、兼容只收字符串，两边当场 400）。
  - ③ 前置（R36 基线）在树：见 R36 格。
- **凭据原文**：
  - `pytest tests/test_r29_thinking_tax.py -q --no-header -p no:cacheprovider` → EXIT=0，**`39 passed in 1.71s`**；`pytest tests/test_r147_native_leg_verdict.py` → EXIT=0，**`19 passed in 1.99s`**（这两枚钉的是「为什么不能这么迁」，不是「迁好了」——用例 docstring 第 3-4 行原话）。
  - `.venv\Scripts\python.exe -c`（逐行剥 `JSONL ` 前缀读 `docs/perf/raw/rate_think2.jsonl`）→ EXIT=0，读数：`think_off_prefill383 12.565 / think_on_prefill383 12.213 / think_off_decode300 40.700 / think_on_decode300 47.662`。
  - `rg -n "reasoning_chars|cached_tokens" docs/perf/raw/think_off.jsonl` → EXIT=0，首帧 `prompt_tokens:510, completion_tokens:147, cached_tokens:257, content_chars:127, reasoning_chars:108`。
- **达标所需动作**：换模型或做 `PARAMETER think false` 派生模型（业主裁），再重量一次生成轮墙钟；在 `/v1` 加参数或在原生腿迁一下就宣布达成，都被本单判为无效。

### R30 · `max_tokens` / 超时按档 —— **达**

- **判据出处**：跟进单 §21 表 **L502**（原文：「① 每档有显式 `max_tokens`；② 超时与 prompt 规模相关（按预算或 prefill/decode 分计）；③ 默认值与 `.env.example` 一致；④ `n_ctx=4096` 撞顶有稳定码」；禁改边界「不改并发语义（R23）；不改默认模型名」）。
- **产物落点**（`866c2f3`）：`app/agents/contracts.py:69-75`（`ModelTier`，docstring 明写「A tier with no caller is the same dead contract」并由 `tests/test_r30_model_tiers.py` 钉）、`:102-103`（`CONTEXT_LIMIT_CODE = "context_limit_exceeded"` / `OUTPUT_TRUNCATED_CODE`）、`:129-133`（`tier` / `max_tokens` / `timeout_seconds` 三字段）、`:157-159`（`input_budget_tokens`）、`:166`（`tokens = min(self.max_tokens, STREAM_STALL_TOKENS) if stream else self.max_tokens` ⇒ prefill/decode 分计的入口）、`:195-197`（撞顶 ⇒ 返回稳定码）；超时的唯一读者是 `app/common/model_budget.py` 的 `http_timeout`，**调用点五处（快照）**：`app/agents/nodes.py:815`、`app/agents/nodes.py:1163`、`app/common/model_handler.py:337`、`app/common/model_handler.py:467`、`app/common/model_handler.py:620`（同三枚在 `ccf8942` 上漂到 `:431`/`:561`/`:735`，因该文件 +119 行，本班两侧都实读过）；`.env.example:139 MODEL_MIN_ANSWER_TOKENS=1536`、`:146 MODEL_CONTEXT_TOKENS=4096`。并树 sha：`50aff1a`。
- **达成/未达成**：**四格全达**。④ 的稳定码在 `contracts.py:102`+`:195-197`，③ 由 74 条默认值用例与 `.env.example` 对读钉住，① ② 由 `:129-133`/`:166` 与调用点闭环。
- **凭据原文**：
  - 六件定向件 → 全 EXIT=0：`test_r30_model_tiers.py` **11 passed in 1.08s**、`test_r30_timeout_budget.py` **20 passed, 4 warnings in 4.42s**、`test_r30_config_defaults.py` **74 passed in 1.03s**、`test_r30_context_limit_guard.py` **15 passed in 1.16s**、`test_r204_single_call_ceiling.py` **9 passed in 1.18s**、`test_r74_dead_budget_field.py` **9 passed in 0.33s**（后者钉「字段存在但零赋值零读取」那类死契约今天不存在）。
  - 「三处硬编 `timeout=30` 已拆」三形状反查：① `rg -n "timeout=30" app` → **EXIT=1**；② `rg -n "timeout=3[0-9]" app/agents app/common app/tools` → **EXIT=1**；③ 正向结构名（对 `git show 866c2f3:app/common/model_handler.py` 落盘副本 + `app/agents/nodes.py` 跑）`rg -n "http_timeout\("` → EXIT=0 五命中（`nodes.py:815`、`nodes.py:1163`、快照 `model_handler.py:337`/`:467`/`:620`）⇒ 超时唯一入口是预算函数，不是字面量。
  - 「三处硬编 `timeout=30` 已拆」三形状反查：① `rg -n "timeout=30" app` → **EXIT=1**；② `rg -n "timeout=3[0-9]" app/agents app/common app/tools` → **EXIT=1**；③ 正向结构名 `rg -n "http_timeout\(" app` → EXIT=0 四命中（`nodes.py:815`、`nodes.py:1163`、`model_handler.py:431`、`model_handler.py:561`）⇒ 超时唯一入口是预算函数，不是字面量。
- ⚠️ 顺带一条勘误（见 §4 第 7 条）：计划书 **L180** 与跟进单 **L502** 仍把 `nodes.py:304`/`nodes.py:370`/`tools.py:443` 写成落点，今日零命中——那是立案时的行号。

### R31 · 生成轮流式透传 —— **部分达**

- **判据出处**：跟进单 §21 表 **L503**（原文：「① `text` 事件数 >1；② **片段时间戳不重叠、逐字比对无缺字**；③ 后端每片 **≥20 字或 100 ms 合并，禁单字碎片**；④ 与 legacy 全量重发共存不冲突」；禁改边界「**禁改 `frontend/**`**；禁在 `sessions.js` 里去动 `segments` 语义；必须排在 R27/R29/R30 之后」）。
- **产物落点**（`866c2f3`）：`app/agents/nodes.py:302-321`（片段边界与其两个静默陷阱的自陈）、`:397` `class StreamPieceMerger`、`:598-628`（把框架 `invoke` 内部那一路流接回片段出口）、`:1000-1047`（流式跑一发，`:1047` `piece_merger = StreamPieceMerger()`）；`app/agents/orchestrator.py:1199`（`stream_piece_sink` 契约）、`:1235`（与 `cancel_event` 同通道的原因）；并树 sha `eef642b`。
- **达成/未达成**：**①③④ 达**（出口、合并器、共存各有钉，五件定向件全绿）；**② 未达（A 门）**——本班自己重算 run7 帧账得 **93/105 题 `criterion_two_holds` 为真**，12 枚不成立，其中 **2 枚是「未纠正断流」**（`chart-03`、`tool-04`，各自 `prefix_breaks=1` 且 `corrective_replacements=0`），另 9 枚是 `text_frames=1` 的一次性到达（不是缺字，是没有逐字）。⇒ 判 部分达，收口须 A 门重跑（`chart-03`/`tool-04` 已另立 R225）。
- **凭据原文**：
  - 五件定向件 → 全 EXIT=0：`test_r31_generation_stream_passthrough.py` **13 passed**、`test_r31_stream_pieces.py` **27 passed in 1.03s**、`test_r149_sse_text_pieces.py` **16 passed**、`test_r203_answer_leg_streams.py` **15 passed**、`test_r203_sse_progressive_frames.py` **16 passed**。
  - 判据② 本班重算（只读 `docs/testing/sidecar-run7-frames.jsonl`）→ EXIT=0：`rows=105`；`criterion_two_holds` 真 = **93**；`prefix_breaks` 合计 **4**（其中 2 枚被纠正、2 枚未纠正）、`extra_chars` 合计 **0**、`missing_chars` 合计 **0**；`max_stream_frames>1` 的题 = **95/105**；不成立的 12 枚逐 id：`doc-07 chat-03 chat-06 chat-09 chat-10 metric-17 data-09 chart-01 chart-03 approval-06 scope-01 tool-04`。

### R32 · 三档进契约 + 前端选择器 —— **达**

- **判据出处**：跟进单 §21 表 **L504**（原文：「① 契约写出三档 SLO；② 档位不改变权限判定；③ `/ask` 非法档 → 400」；禁改边界「不得借分档放宽 scope；legacy 事件名一个不许下线」）。
- **产物落点**（`866c2f3`）：`app/api/v1/chat.py:1232`（`ASK_LANE_VALUES = (LANE_QA, LANE_ANALYSIS, LANE_REPORT, "")`）、`:1246-1256`（非法值 ⇒ `HTTPException(400, ErrorEnvelope(code=LANE_ERROR_CODE, ...))`，`:1254-1256` 带 `field/allowed`）、`:1290`、`:1333`（声明档与真相对照）；契约腿 `docs/api/contract-v1.md:1370`（`## Three-Tier SLO Contract (2026-09-20, R105 甲半)`）、`:1380`（明写未实测的数字不许当 SLO 发布）、`:1403`；前端腿 `frontend/src/router/lane-choice.js`（选择器与路由判定）；并树 sha：合并 `8a91f4e`。
- **达成/未达成**：**①②③ 达**。②「档位不改变权限判定」是硬边界，由 67+62 两条契约/行为件合钉；① 的 SLO 数值甲半在树、乙半待 D 门（契约自己写着不许发布未实测数）。
- **凭据原文**：
  - `pytest tests/test_r32_lane_contract.py` → EXIT=0，**`67 passed, 4 warnings in 8.46s`**；`pytest tests/test_r141_lane_behavior.py` → EXIT=0，**`62 passed, 4 warnings in 7.59s`**。
  - `rg -n "Three-Tier SLO Contract" docs/api/contract-v1.md` → EXIT=0 命中 `:1370`。
  - `rg -n "lane must be one of" app/api/v1/chat.py` → EXIT=0 命中 `:1253`（400 分支的文案与 `allowed` 列表同源）。

### R33 · 输入瘦身：无模型裁剪 —— **达**

- **判据出处**：跟进单 §21 表 **L505**（原文：「① 每发 prompt token 有硬上限且日志可见；② 裁剪过程**零模型调用**；③ **与 R36 同批合并**（会改答案内容）」；禁改边界「不许裁掉权限谓词与来源定位串」）。
- **产物落点**（`866c2f3`）：`app/memory/summarizer.py:92-101`（`history_input_budget_tokens`，预算来自真正吃这份历史的档位）、`:104-130`（`trim_history`，确定性裁剪）、`:153-173`（`compress_messages`——`:162-163` 传入 `model` 直接 `TypeError`，`:170-172` 裁剪日志）；调用点 `app/agents/orchestrator.py:342-350`（`:342` 注释「R33 起确定性裁剪，零模型」，`:348` 明写 `ModelTier.COMPRESS` **保留但不进生产路径**，`:350` `compress_messages(all_msgs, tier=ModelTier.ANALYSIS)`）。并树 sha：`9678d21`。
- **达成/未达成**：**①②③ 达**。② 是**结构性**达成（签名层 `model is not None ⇒ TypeError`，不是「今天恰好没传」）；③ 的质量基线在盘（见 R36 格的 run5/run7 分数落盘），故「与 R36 同批」这一排程约束有磁盘凭据而非名册凭据。
- **凭据原文**：
  - `pytest tests/test_r33_zero_model_compression.py` → EXIT=0，**`9 passed, 4 warnings in 4.98s`**；`pytest tests/test_r33_history_guardrails.py` → EXIT=0，**`11 passed`**。
  - `rg -n "ModelTier.COMPRESS 这一档\*\*保留" app/agents/orchestrator.py` → EXIT=0 命中 `:348`（⇒ 老契约未偷偷删，只是移出生产路径）。
  - 禁改边界「不许裁掉权限谓词与来源定位串」是**正面达成**：`rg -n "来源定位|\[来源" app/memory/summarizer.py` → EXIT=0 命中 `:16`（docstring「权限谓词文本与来源定位串**一条都不许少**（既不丢也不截）」）与 `:42-47`（`PROVENANCE_MARKERS: tuple[str, ...] = ("#chunk=", "来源:", "来源：", "[来源: ")`）⇒ 定位串不是被"忽略"，而是被裁剪器登记成常量来守；再由 `tests/test_r33_history_guardrails.py`（11 条）钉住。⚠️ 本班上一条曾把这条 grep 写成「EXIT=1（裁剪器不碰那一层）」，那是**形状选错的假阴性**——裁剪器碰它，而且是为了守住它才碰；此处按实测改正。

### R34 · `keep_alive` 常驻 —— **达**（① 的读数引用 09-19 真机落盘）

- **判据出处**：跟进单 §21 表 **L506**（原文（截断处以表为准）：「① 连续 5 问无重复冷启动；② 空闲后内存回收策略…**客户机内存有限**」；落点行：「现**全仓 0 命中**；冷加载 6.4–6.9 s/发」）。
- **产物落点**（`866c2f3`）：`app/common/model_config.py:30-43`（`:30` `KEEP_ALIVE_ENV = "LOCAL_MODEL_KEEP_ALIVE"`、`:31` `DEFAULT_KEEP_ALIVE_SECONDS = 5 * 60`）、`:66-84` `parse_keep_alive_seconds`、`:87-97` `resolve_keep_alive`（上限截断 + 日志带原因）；`app/common/model_handler.py:69`（`KEEP_ALIVE_FIELD`）、`:400-411`（`_keep_alive()`）、`:462`（**下发到原生腿 payload**）、`:525`（日志 `keep_alive=...`）、`:596-597`（兼容腿同一策略）；`app/agents/nodes.py:215`（`_KEEP_ALIVE_MODE_LOGGED`）。并树 sha：`2e6abc6`（R34 族）；文档：`docs/handoff/2026-09-19-r34-keep-alive-residency.md`。
- **达成/未达成**：**①② 达**，但本班把话说清：①「连续 5 问无重复冷启动」的**墙上读数是 09-19 那班在本机实测落盘的**（该文档 §2：A1 冷 `4.951 s`，A2–A5 `0.001–0.003 s`，B6 空档 `4.410 s`），本班**不许打模型故未重跑**；② 有上限档与截断在树（`model_config.py:87-97` + 文档 `:125` 记 `KEEP_ALIVE_CEILING_SECONDS = 1800`）。⇒ 判 达（代码格 + 落盘真机格），并把它同时挂进 **A 门指针**，总控若要现值可 A 门顺手重量。
- **凭据原文**：
  - `pytest tests/test_r34_keep_alive_residency.py -q --no-header -p no:cacheprovider` → EXIT=0，**`47 passed in 1.34s`**。
  - `rg -n "DEFAULT_KEEP_ALIVE_SECONDS" app/common/model_config.py` → EXIT=0 命中 `:31`（值 `5 * 60` = 300 s）。
  - `rg -n "LOCAL_MODEL_KEEP_ALIVE" .env.example` → **EXIT=1**（⇒ 运维开关未进 `.env.example`；三形状：字面变量名、`KEEP_ALIVE`、`keep_alive` 在该文件均零命中）。这是**待补的文档面**，不是行为缺陷（默认值由代码给，见 `:31`），已记进 §3「文书欠」。
- ⚠️ 勘误：`docs/handoff/2026-09-19-r34-keep-alive-residency.md:157` 写「离线用例 46 条」，本班实测 **47 passed**。

### R35 · 真缓存两件事 —— **部分达**

- **判据出处**：跟进单 §21 表 **L507**（原文含两处改造点：「① 门槛 `chat.py:936 use_answer_cache = not bool(request.session_id)` 改成 scope 相等即可命中；② 死代码 `cache.py:150-176`…删除或按 Redis+向量+scope 重建」；判据：「① 多轮对话内重复问题命中且**标注"缓存结果·生成于"**；② **跨部门/跨密级命中 0 条**（P0）；③ 淘汰策略可测」；禁改边界「不许无 scope 上线；不许伪装成实时答案；命中必须是 UI 第四张脸」）。
- **产物落点**（`866c2f3`）：`app/common/cache.py:17`（`DEFAULT_ANSWER_CACHE_TTL_SECONDS = 1800`）、`:31` `answer_cache_ttl_seconds`、`:144-152` `answer_cache_scope`（`:150` 自陈「同一账号换了部门之后…必须换 scope」）、`:187-195` `_scope_part`、`:243-252` `answer_cache_origin`（供「缓存结果 · 生成于」）、`:256-258`（旧语义缓存那套已删的自述）；`app/api/v1/chat.py:1983`（`use_answer_cache = bool(answer_scope)` —— **判据① 的旧式已被替掉，实测到行**）、`:1984-2002`（命中路径 + `:1989` 「不许伪装成实时答案」+ 三个 UI 字段）、`:2325`（写缓存）；前端腿 `frontend/src/lib/provenance.js:217`（`缓存结果 · 生成于 ${moment}`）。
- **达成/未达成**：**①③ 达**（scope 相等即命中 + 出处标注 + TTL 淘汰均可测）；**② 的 P0 格未收**——跨部门/跨密级命中 0 条要真并发矩阵，计划书 **L379** 至今把 **C 行**列为未收口 ⇒ 判 部分达。
- **凭据原文**：
  - `pytest tests/test_answer_cache_scope.py` → EXIT=0，**`21 passed, 4 warnings in 9.43s`**；`pytest tests/test_chat_cache_safety.py` → EXIT=0，**`3 passed, 4 warnings in 6.95s`**。
  - `rg -n "use_answer_cache = " app/api/v1/chat.py` → EXIT=0 唯一命中 `:1983 use_answer_cache = bool(answer_scope)` ⇒ 跟进单 L507 点名的旧写法（`not bool(request.session_id)`）**已不在**（另两形状：`rg -n "not bool\(request.session_id\)" app` → EXIT=1；`rg -n "session_id" app/common/cache.py` → EXIT=1，scope 计算不读 session）。

### R36 · 三屏 SLO + 评测集 30→≥100 —— **达**

- **判据出处**：跟进单 §21 表 **L508**（原文：「① 每档有可跑的分层评测集（含**同指标两部门口径冲突**成对题）；② P95 计算样本 ≥100；③ 基线分数落盘供 R29/R33/R35 对比」；禁改边界「不得用演示语料充当评测集」）。
- **产物落点**（`866c2f3`）：`tests/fixtures/business_evaluation_100.jsonl`（**105 条**，带 `tier` 列：问答 50 / 分析 35 / 报告 20；`category` 11 类，其中 **口径冲突 19 条**、**跨部门权限 6 条**）、`tests/fixtures/business_evaluation_30.jsonl`（旧 30 条，仍在树供对照）；P95 样本门槛 `app/api/v1/observability.py:692-701`（`:696` `MIN_SLO_SAMPLES = 100`、`:701` `SLO_TARGET_PENDING = "awaiting_real_samples"`）；判据件 `tests/test_evaluation_report.py:84-277`（`:210-244` 成对判别）；采集器 `scripts/collect_evaluation_answers.py`；落盘分数 `docs/testing/evaluation-report.json`、`-run7.json`、`-run5.json`、`answers-run6.jsonl`、`answers-run7.jsonl`。并树 sha：`3f10b26` 立案 → R36 合并见 §21.4 L543。
- **达成/未达成**：**①②③ 达**——分层（tier 三档 50/35/20）、成对（口径冲突 19 条）、样本门槛（100）、基线落盘（run5 与 run7 两套分数在场，供 R29/R33/R35 对比）全部是本班读出来的磁盘事实。⚠️ 「不得用演示语料」这一条本班只能证到「题面是业务口径 + `must_contain` 期望证据」的形状，语料真实性属业主侧。
- **凭据原文**：
  - `.venv\Scripts\python.exe -c`（读两个 fixture 计数）→ EXIT=0：`business_evaluation_30.jsonl rows= 30`；`business_evaluation_100.jsonl rows= 105`、`category {文档问答:19, 多轮对话:12, 口径冲突:19, Excel计算:12, 主动洞察:7, 图表生成:4, 审批判断:6, 跨部门权限:6, 无证据问题:4, 工具调用:4, 报告生成:12}`、`tier {问答:50, 分析:35, 报告:20}`、`q len min/max/mean= 8 20 13.1`。
  - `pytest tests/test_evaluation_report.py -q --no-header -p no:cacheprovider` → EXIT=0，**`8 passed in 0.17s`**。
  - `.venv\Scripts\python.exe -c`（读报告 JSON）→ EXIT=0：`evaluation-report.json total=105 answer_correctness=0.5333 evidence_coverage=0.7905 unsupported_claim_rate=0.0 latency_ms.count=105 p95=127405.91`；`evaluation-report-run5.json answer_correctness=0.4762 evidence_coverage=0.6857`。

### R37 · report 档进可靠队列 —— **未达**（快照上；R227 已改码但未重量）

- **判据出处**：跟进单 §21 表 **L509**（原文：「① 关页面后任务继续；② 结果可查回；③ **队列失败有终态与原因码**」；禁改边界「不改 `/ask` 现有同步档行为；不得丢 HITL 语义」）＋ §35.1 **L1262-1272**（①–⑨ 接续判据全文，含「⑥ 队列失败要有终态 + 原因码（原 §21 判据 ③），dead 态可查」与「⑨ 取证日志不许入库」）。
- **产物落点**：入队侧（`866c2f3`，工作树同值）`app/api/v1/chat.py:1191-1223`（档位名第二处落地，真相在 `nodes.py` 的 `LANE_REPORT`）、`:1955-1956`（`lane = _queue_lane(request)` + `lane == LANE_REPORT and _report_lane_via_queue_enabled()`，**双条件，默认关**）、`:1960`（`_enqueue_ask_turn`）。worker 侧（🔴 **必须读快照**，HEAD 已被 R227 改过）：`deploy/queue_worker.py@866c2f3:87`（R37 段落头）、`:286-300`（park ⇒ `chat.record_hitl_awaiting` 三笔账）、`:306-313`（`if not queue.complete(request_id, answer)` → 记一条「结果已丢弃」并 `return True`）；队列内核 `app/common/reliable_queue.py@866c2f3:204-215`（`complete()`：`:210` 判 `is_cancelled() or _lease_lost()` → `:211` 删结果键 → `:212` **仍调 `ack()`** → `return False`）、`:189-202`（`ack()`：`:201` `set(status, "done")`）、`:67`（`lease_seconds: int = 300`）、`:178`（`set(lease_key, "1", ex=self.lease_seconds)` —— **全文件唯一租约写点**）。HEAD 之后：`deploy/queue_worker.py@a9dd17e:366-373`（丢弃支）、`:394-397`（心跳），并树 sha `5830422`。
- **达成/未达成**：**判据③ 在快照上未达，且是被现场证伪的未达**：租约（默认 300 s）在长跑中**从不续租** ⇒ 一条 311 s 的报告档必然落进 `:210` 那一支，而该支 `ack()` 在 `:201` 把状态写成 **`done`**、同时 `:211` 删掉结果键 ⇒ 客户端读到「跑完了、正文空」。这既违「③ 队列失败有终态**与原因码**」（`failure.last_error` 为 `null`），也构成谎报终态。①② 成立（入队、接单、正文真生成均在现场日志里）。R227（`5830422`）已按「续租 + 租约支不再 `ack()` + 写 `last_error=result_discarded:lease_lost`」改码，**但该提交自己写着「D-1 必须在 R222 并树后重量一次才许宣布」** ⇒ 本号今天收不了，判 **未达**（并注：R227 之后应重判为「部分达·待 D 门收口」）。
- **凭据原文**：
  - 快照逐行数租约写点：`git show 866c2f3:app/common/reliable_queue.py` → 唯一写点 `:178`（`set(_lease_key, "1", ex=self.lease_seconds)`，默认值在 `:67 lease_seconds: int = 300`）。🔴 「运行途中零续租」三形状**一律对快照副本跑**（在现 HEAD 上同两条命令会变 EXIT=0，因为 R227 已经加了续租——这正是要写清的差别）：① `rg -n "expire\(|renew" <快照 reliable_queue.py> <快照 queue_worker.py>` → **EXIT=1**；② 语义族 `rg -n "lease" <快照 queue_worker.py>` → **EXIT=1**（改前 worker 侧根本不认识租约）；③ 结构名 `rg -n "def .*lease" <快照 reliable_queue.py>` → EXIT=0 只有 `_lease_key:123` 与 `_lease_lost:181` 两枚**读**点。对照现 HEAD：同 ① → EXIT=0，命中 `reliable_queue.py:82 lease_renew_budget`、`:235 def renew_lease`、`queue_worker.py:83 renewals=` ⇒ R227 的改动确实落地。
  - 现场读数（不是本班跑的，是指纹级落盘文件）：`docs/testing/run7-readout-sheet-2026-09-24.md:89-91` D-1 格 —— `report-01` 09:26:57 发 → 09:27:01 `[QueueWorker] 处理中 request_id=3d37af0e…` → 09:32:12 `[doc] 完成 status=success 结果 1519 字` → 全程 **311 s**；`:92` D-2 未量到；`:93` D-3 未量到；`:94` 另抓到一枚间歇 500（`psycopg … failed to resolve host 'postgres'`，每请求新建连接）。
  - `pytest tests/test_r37_report_lane_enqueue.py` → EXIT=0，**`14 passed, 4 warnings in 6.92s`**；`pytest tests/test_r37_report_lane_worker.py` → EXIT=0，**`14 passed, 14 warnings in 9.04s`**（落盘日志原文），本班又在 **`47b6643`** 工作树复跑同一件 → EXIT=0，**`14 passed, 14 warnings in 8.17s`**。两次 **passed 计数同 14** ⇒ 该件既有断言未被 R227 放宽（R227 是加件不是改件）。
  - R227 之后的新钉（本班实测，用以说明「改码在场、结论未收」）：`pytest tests/test_r227_discard_is_honest.py` → EXIT=0，**`19 passed, 14 warnings in 15.36s`**；`pytest tests/test_r227_lease_heartbeat.py` → EXIT=0，**`16 passed in 0.43s`**。

### R38 · 核实 `usage` 真值 —— **需真机**

- **判据出处**：跟进单 §21 表 **L510**（原文判据只有一句：「抽查一问，`input_tokens/output_tokens` 非零且**与 Ollama 自报一致**」；禁改边界「不得估算冒充实测 token 数」；落点：「计量列在 `migrations/0002:147`…链路 `app/trace/spans.py` → `app/trace/store.py:171`；现 `cached_tokens=0`」）。
- **产物落点**（`866c2f3`）：`migrations/0002_execution_data_lineage.sql:147-165`（`CREATE TABLE IF NOT EXISTS model_calls`，含 `input_tokens/output_tokens/duration_ms/first_token_at/queue_wait_ms`）；`app/common/model_handler.py:508-519`（`:517 input_tokens = body.get("prompt_eval_count")`、`:518 output_tokens = body.get("eval_count")`、`:519 cached_tokens = body.get("prompt_eval_cached_count")` —— 三枚全部**直读服务端自报**，符合「不得估算」）；`app/trace/spans.py:329-340`（`model_token_counts`）、`:342-371`（`cached_tokens` 只在真报数时才进键）；`app/trace/store.py:270-272`（只有 `input_tokens`/`output_tokens` 在场才写列）。并树 sha：`2e6abc6`（R38 族）。
- **达成/未达成**：**需真机**。判据本体是「抽查一问…与 Ollama 自报一致」，只能打模型；本单硬禁。本班能证的只是**通路形状**：读的是自报字段、无估算兜底、缺值不写列；而 run7 的帧账里**根本没有 token 列**，所以那一格今天仍然空着（D-2）。
- **凭据原文**：
  - `pytest tests/test_r38_cached_tokens_honesty.py` → EXIT=0，**`4 passed in 0.84s`**；`pytest tests/test_r38_native_input_tokens.py` → EXIT=0，**`11 passed in 1.01s`**。
  - 「run7 帧账无 token 列」三形状：① `rg -n "input_tokens" docs/testing/sidecar-run7.jsonl` → **EXIT=1**；② `rg -n "prompt_eval" docs/testing/sidecar-run7.jsonl` → **EXIT=1**；③ 结构层（读 `sidecar-run7-frames.jsonl` 首行键集）→ EXIT=0，键集为 `answer_chars answer_sha attempt corrective_replacements criterion_two_holds extra_chars id kind last_frame_chars last_frame_covers_answer last_frame_sha max_stream_frames missing_chars per_stream …`，无 token 族。
  - `migrations` 里无 cached 列三形状：① `rg -n "cached" migrations` → **EXIT=1**；② `rg -n "cached_tokens" app/trace/store.py` → EXIT=0 仅出现在「有读数才写」的分支说明中，列白名单不含它；③ `rg -n "CREATE TABLE" migrations/0002_execution_data_lineage.sql` → EXIT=0 命中 `:147`，该表列内无缓存族。⇒ R43 的「缓存命中」今天**落不了库**，见 R43 格。

### R39 · —— **不建**

- **判据出处**：跟进单 §21 引言 **L491** 原话：「**R39 不建，沿用 R17**（裁定=甲）」；计划书 §5.2 **L189** 该行已划删除线并写「**不建**，沿用 R17（裁定 5 = 甲）」。
- **产物落点**：无（本节不要求产物）。
- **达成/未达成**：**不适用**——本号从未立成独立单，结论随 R17。本班仍按纪律反查了三形状确认「代码里没有一枚 R39 的私有产物」，以防「不建」只是文书口径：
  - ① 结构层：`rg -n "\bR39\b" app tests scripts deploy` → **EXIT=1**；
  - ② 提交正文：`git log --all --grep=R39 --oneline` → EXIT=0，但命中全部落在 `docs/handoff/**`（跟进单 L491、看板两处「零提交单/结案单」清单），**无产物枚**；
  - ③ 语义词族：`rg -n "沿用 R17" docs/handoff/2026-09-15-backend-followup-requests.md` → EXIT=0 命中 `:491`（唯一口径源）。
- **凭据原文**：如上三条，EXIT 码分别 `1 / 0（仅文档）/ 0`。

### R40 · `standard_source` 自动取标准 + 拒绝前端部门 —— **部分达**

- **判据出处**：跟进单 §21 表 **L511**（原文：「① 不传部门也能出结论；② 传错部门被拒且是稳定码；③ **不再出现前端 `standard: 500` 硬编**」；禁改边界「不改审批动作的权限判定」；落点「现 `app/**` **0 命中**」）。
- **产物落点**（`866c2f3`）：`app/api/v1/open_platform.py:77-86`（`:77` 注释「不写就是 `auto_from_knowledge_base`」、`:86` `standard_source: str = STANDARD_SOURCE_AUTO`）、`:158`（`department = verify_department_self_report(...)`）、`:187`；`app/api/v1/intelligence.py:21`（`resolve_standard_source`）、`:26`（同 `verify_department_self_report` 同源）、`:58-66`（`:66` `standard_source: str = STANDARD_SOURCE_EXPLICIT`）、`:143-144`。🔴 判据③ 的**违反点仍在**：`frontend/src/devFixtures/approval-demo.js:7` `standard: 500,`，被 `frontend/src/components/ApprovalPanel.vue:5`（import）、`:10`（`ref({ ...demoForm })` 播种）、`:39`（`onMounted(submitCheck)` —— 挂载即 POST）、`:43`（`data-demo="fixtures"`）、`:61`（屏上自陈参数来自前端常量）使用。并树 sha：R75 收口 `69b0553`。
- **达成/未达成**：**①② 达**（后端默认 auto + 自报核验 + 稳定码，三件定向件 25/23/96 全绿）；**③ 未达**——判据是字面「不再出现前端 `standard: 500` 硬编」，今天磁盘上还有一枚，且它不只是显示常量：`onMounted` 会把它打进请求。它是 demo 标注的、有屏上说明（`:61`），但**按判据原文这格是红的**。⇒ 部分达，缺的那条属 **V 前端线**（改 demo 播种面）。
- **凭据原文**：
  - `pytest tests/test_approval_precheck_standard_source.py` → EXIT=0，**`25 passed in 0.46s`**；`pytest tests/test_r67_department_self_report.py` → EXIT=0，**`23 passed, 6 warnings in 5.09s`**；`pytest tests/test_r75_standard_source_single_source.py` → EXIT=0，**`96 passed, 6 warnings in 6.15s`**。
  - 判据③ 的命中（本班不是「grep 不到」而是「grep 得到」）：`rg -n "standard: 500" frontend/src` → **EXIT=0** 命中 `approval-demo.js:7`；`rg -n "demoForm" frontend/src/components/ApprovalPanel.vue` → EXIT=0 命中 `:5`、`:10`。
  - 「`app/**` 0 命中」这句立案口径今天已过期（正向）：`rg -n "standard_source" app | Measure-Object -Line` → EXIT=0，命中集含 `open_platform.py`、`intelligence.py` 与 `app/common/authorization*` ⇒ 跟进单 L511 的「0 命中」描述的是改前状态，引用时须带日期。

### R41 · SSE canonical `sources` —— **达**（附两条披露）

- **判据出处**：跟进单 §21 表 **L512**（原文：「① 流里出现 `sources`；② legacy 全保留；③ 前端引用条可点回原文」；禁改边界「**一个 legacy 事件名都不许下线**（契约冻结规则）」）＋ §21.8 **L665-672**（结案与 legacy 超集证明）。
- **产物落点**（`866c2f3`）：`app/api/v1/chat.py:226`（`def canonical_sse_event(`）、`:303-371`（`_collect_document_sources`：从 agent 结果收集并 `sink` 出 `sources`）、`:470`（判据②：给每行出处补「当前生效的那一版索引何时发布」）、`:566`（命中腿**不许**发空 `sources` 充数）；前端腿 `frontend/src/lib/sessions.js:255-278`（`EVENT_CLAIMS` 认领表，`:274` `'answer.headline': 'render'`）、`:490`（`case 'answer.headline'`）；`frontend/src/components/SourceCard.vue:96`（`@click="emit('preview', row)"`）→ `frontend/src/components/ChatPanel.vue@866c2f3:1098`（`preview.open = true`）。并树 sha：实现 `e8d3200` / 合并 `571e0d6`。
- **达成/未达成**：**①②③ 达**。② 有结构性证明（§21.8 L669：`git show --numstat` = **89/0 `chat.py` + 363/0 `tests/test_sse_sources.py`**，纯新增零删除 ⇒ legacy 事件面不可能被削减）；③ 到行（点击链两级都读到）。
- **凭据原文**：
  - `pytest tests/test_sse_sources.py -q --no-header -p no:cacheprovider -rs` → EXIT=0，**`14 passed, 4 skipped, 12 warnings in 8.53s`**；skip 原因实测打印：`SKIPPED [4] tests\test_sse_sources.py:206: SSE_EVENT_INVENTORY_OUT not set; this test only records evidence` ⇒ 那 4 枚是**取证记录枚**（需要真机事件名清单落盘才跑），不是被绕过的断言。
  - `rg -n "preview.open = true" frontend/src/components/ChatPanel.vue` → EXIT=0，但**行号随快照变**：`866c2f3` 上是 `:1098`，`a9dd17e` 上是 `:1161`（R221 `9850969` +67 行）。本文件按快照记 `:1098`。
- **披露两条**：① `/approve` 未被 `sources` 覆盖 ⇒ 已转 **R55**（§21.8 L672 记）；② 队列道（report 档）里 `sources` 的真机读数仍空（`run7-readout-sheet-2026-09-24.md:93` D-3「未量到」），那是 **R37 的账**，不在本号重开。

### R42 · 快慢判别器 —— **达**（按 §27.2 改判后的判据；附 H15 风险）

- **判据出处**：跟进单 §21 表 **L513**（原文：「① 判别零模型调用；② 判错时兜底仍能升档；③ 问答档占比 ≥60%（对齐 70:25:5）」）**＋ §27.2 L892-897 的当场改判**：③ 降级为报告值不再判红（实测 fixture = 问答 50/分析 35/报告 20 = 47.6%:33.3%:19.0%，「③ 在这份题面上永远红」；真因 = 把生产流量形状与难题加权写成了一条判据），成本占比门**移交 R51**；新增 **⑤ 硬门（不可放宽）**「快道不得接任何"要求算出一个数"的题」；新增 **⑥**「精度 ≥70%、召回 ≥90% 两个字都不许动」（当时实测 快道精度 49/65 = 75.4%、召回 49/50 = 98%）。
- **产物落点**（`866c2f3`）：`app/agents/nodes.py:1209-1337`（判别器本体，`:1337` 日志 `[R42] '<题面前 30 字>' → lane=… tier=…`）、`:1372-1405`（与 R32 取值闸的分工说明；`:1405` `LANE_SOURCE_R42 = "r42"`）；`app/agents/orchestrator.py:565-572`（只在「supervisor 弃权 + 计划为空 + 关键词一条不命中」这一种局面接管）。并树 sha：`c8c9b57` 前后族（R42/§27 记于 L875 那格）。
- **达成/未达成**：**改判后的四格全达**——① 零模型（纯规则，件名即 `zero_model_calls`）、② 兜底升档（`fallback_upgrade`）、⑤ 数字题硬门（`numeric_questions`，32 条）、⑥ 精度/召回双阈值（`lane_ratio` 5 条）。③ 的原口径按总控裁定不判红 ⇒ 本号判达，但**这一格是总控改判的结果，业主可一句话驳回（H15）**；若驳回，R42 立刻回到「未达（③ 恒红）」。
- **凭据原文**：
  - 五件全 EXIT=0：`test_r42_zero_model_calls.py` **10 passed**、`test_r42_lane_rules.py` **29 passed in 1.03s**、`test_r42_fallback_upgrade.py` **10 passed**、`test_r42_lane_ratio.py` **5 passed in 1.06s**、`test_r42_numeric_questions.py` **32 passed in 1.09s**。
  - fixture 侧本班复算（用来复核 §27.2 L894 那三个数）：`.venv\Scripts\python.exe -c` 读 `business_evaluation_100.jsonl` → `tier {问答:50, 分析:35, 报告:20}` ⇒ **50/105 = 47.6%**，与 L894 逐字一致。

### R43 · system prompt 前缀复用 —— **部分达**

- **判据出处**：跟进单 §21 表 **L514**（原文：「① 同一前缀字节级稳定（无时间戳/无随机顺序）；② E3 档实测 `cached_tokens > 0`」；禁改边界「不许把权限信息塞进可复用前缀」）＋ **§74 四（L2126 起）与 §81 一（L2350）作废重写**：判据② 改**分腿口径**（改写腿与答案腿分别量，不许再拿一个笼统的「E3 档」当唯一入口）。
- **产物落点**（`866c2f3`）：`app/rag/retrieval_pipeline.py:40`（可变内容后置的常量说明——改前 `{question}` 夹在两段固定指令**中间**）；`app/common/model_handler.py:154`（`cached_tokens: int | None = None` 形参）、`:168-173`（默认必须是 `None` 的钉，不许写 0）、`:519`（`cached_tokens = body.get("prompt_eval_cached_count")`）、`:537`（把读数交给 reply）；`app/trace/spans.py:292-326`（`_cached_token_count` 三来源）、`:342-371`（`cached_tokens` 只在服务端真报数时进键）；R43b（答案腿）＝ **R167**，并树 sha `839c344`；R43a 并树 sha `4586bb4`。
- **达成/未达成**：**① 达**（两腿前缀后置都在树、各有 12/29 条钉，含「字节级稳定」的正反用例）；**② 分腿口径下只到「落盘帧有读数」，未落库、未在本班实测**：`docs/perf/raw/think_off.jsonl` 9 枚带 usage 的帧全部报 `cached_tokens=257`（对 506–510 的 prompt），`docs/perf/raw/prodpath.jsonl` 报 `292/543`、`257/769` 与一枚诚实的 `0/116` ⇒ 「>0」在**历史落盘帧**上成立；但 **`migrations/` 里没有任何 cached 列**（三形状见 R38 格，`rg -n "cached" migrations` → EXIT=1）⇒ 分数侧读不到、无法回答「今天这一发的命中率」。⇒ 部分达；E3 档真机实测归 **B 门**。
- **凭据原文**：
  - 三件全 EXIT=0：`test_r43a_native_cached_tokens.py` **10 passed in 1.15s**、`test_r43a_rewrite_prefix_reuse.py` **12 passed in 0.77s**、`test_r167_answer_prefix_reuse.py` **29 passed, 4 warnings in 14.70s**。
  - `.venv\Scripts\python.exe -c`（读落盘帧）→ EXIT=0：`think_off.jsonl` 首枚 JSONL 帧含 `prompt_tokens:510, cached_tokens:257`；`app/trace/spans.py:301-303` 那段注释自陈的读数（「all 9 usage-bearing rows of think_off.jsonl report cached_tokens 257 against a 506--510 prompt」）本班逐字复核成立。
- ⚠️ 勘误（见 §4 第 4 条）：`app/trace/spans.py:306-310` 的 docstring 还说「`model_handler.py:394-395` 只拷 `prompt_eval_count`/`eval_count`，所以今天没有任何东西给它赋值」——这句话已经被 `:519`+`:537` 推翻，代码注释自己是旧的。

### R44 · 热集进程内检索索引 —— **部分达**

- **判据出处**：跟进单 §21 表 **L515**（原文：「① 覆盖 95% 查询的热集常驻；② 与 Chroma 结果一致性有测试」；禁改边界「**不许**因提速牺牲部门/密级过滤（pre-filter 先于热集）」）＋ 计划书 **L194** 的结案口径订正（本班读原文：结案 `39006b8` + 总控热修 `564340e`，并明订「105/105 覆盖是在 379 chunk 小库上量的」）。
- **产物落点**（`866c2f3`）：`app/rag/hot_index.py:1`（模块自陈「一层可丢弃的加速缓存，不是第二个事实源」）、`:45` `HOT_INDEX_ENV = "HOT_INDEX_ENABLED"`、`:55`（实测教训：37 483 chunk 的库整库 get 会报 "too many SQL variables"）、`:60`（分页行数上限只为止步）、`:153`（**默认关**的读法）、`:190`（37 483 chunk 量级的成本说明）；钩子 `app/rag/retriever.py:934-967`（`:936` `_hot_scope_key`，backend+模型+维度同口径）、`:1151-1152`（`index.rank(query_embedding, k, where=where, pred=pred, ...)` —— **pre-filter 先于热集**，判据边界满足）、`:1456-1464`（`:1457` 热集腿、`:1462` R59b 的 pgvector 腿、异常即整体回落外部库 `:1153-1155`）；观测 `app/common/monitoring.py:269-271`。
- **达成/未达成**：**①② 有测试**，但**①的覆盖面结论不能按字面收**——本班亲跑覆盖率件，输出里两行自陈就是天花板：语料只有 **379 个 chunk（常驻 379 / 冷表 0）**，且 **embedding 是确定性哈希桩**（4/105 能直接看到 `must_contain` 期望证据，注释即写「不计入判据」）。⇒ 判 部分达：结构达成，**真实语料（37 483 chunk）与延迟结论未证**（计划书 L194 自己把延迟那笔交给 R79④）。
- **凭据原文**：
  - `pytest tests/test_r44_hot_index_unit.py` → EXIT=0 **17 passed in 0.15s**；`test_r44_hot_index_chroma.py` → EXIT=0 **18 passed in 3.45s**（判据② 的一致性）；`test_r44_hot_index_paging.py` → EXIT=0 **7 passed**；`test_r79_hot_index_defaults.py` → EXIT=0 **24 passed in 0.49s**（默认关）；`test_r79_hot_index_observability.py` → EXIT=0 **11 passed, 20 warnings**；`test_r59b_pg_read_switch.py` → EXIT=0 **24 passed in 0.65s**。
  - 覆盖率件带 `-s` 本班实测 → EXIT=0，stdout 关键行逐字：
    `[R44 判据①] 分母 = 评测集 distinct question = 105 题`
    `[R44 判据①] 语料 = documents/*.txt 95 篇 → 向量库 379 个 chunk，其中常驻 379，冷表 0`
    `[R44 判据①] 热集覆盖率 = 105/105 (100.0%)  判据 ≥95% (≥101/105)`
    `[R44 判据②] 与外部向量库逐条同序同 id = 105/105`
    以及 caveat 的源文件位置：`tests/test_r44_hot_index_coverage.py:7-12`。

### R45 · Pre-filtering —— **达**（按 §21.9/§21.10 重定义口径）

- **判据出处**：跟进单 §21 表 **L516** 原文（「① 过滤在向量计算**之前**；② 严格权限下召回不为空（对比 post-filter 退化用例）；③ 检索 P95 不升」）**已被 §21.9（L713）与 §21.10（L724）取代**：① 判为「早已满足、不许再动」；必改只剩 **D1 召回饥饿**（截断前必须先套谓词）；**D2 两腿谓词不对称**为纵深防御；**判据③ 明令改为不实测**（L720/L742：打 Ollama 计时属并发红线，改交结构性论证，墙上 P95 属业主侧）；§21.10 L737 定了修法顺序 **「先过滤、后去重」** 并要求恢复语义腿去重。
- **产物落点**（`866c2f3`）：`app/rag/retrieval_pipeline.py:439-463`（`BM25Retriever.search(query, k, pred=None)`，`:451-455` 注释即 D1 的病与旧写法，`:463` `if pred and not pred(document): continue` —— **谓词作用在截断之前**）、`:849`（`search_for_principal(..., where, pred, tier)`）、`:892`（BM25 腿把 `pred` 传进 `search`）、`:906-918`（语义腿：`:918` `all_semantic = _deduplicate(_retain_permitted(all_semantic, pred))`，与 §21.10 L737 **逐字同形**）、`:1002-1010`（`_retain_permitted`：`if not pred: return hits` ⇒ `pred=None` 时逐字等价旧实现）；`app/rag/retriever.py:1079`（`where` 下推给向量库，两条腿都是先筛后截名次）、`:1439`（注释「chunk 排进名次里再丢掉，那正是 R45 裁掉的召回饥饿形态」）。并树 sha：`0276f78`。
- **达成/未达成**：**达**（按重定义后的交付判据：① `tests/test_prefiltering.py` 全绿；③ `pred=None` 回归等价由 `_retain_permitted` 的短路 + 用例钉住；原判据①「过滤在向量计算之前」由 `:463`/`:918`/`retriever.py:1079` 三处闭环）。**原③（P95）不是本班能证的，也不是判据要求证的**——§21.9 L720 明令禁止实测，本单尊重该裁定，同时把它记进 §3「真机验收欠」清单以免被读成「已测」。
- **凭据原文**：
  - `pytest tests/test_prefiltering.py -q --no-header -p no:cacheprovider` → EXIT=0，**`32 passed, 1 warning in 1.75s`**。
  - `rg -n "_deduplicate\(_retain_permitted" app/rag/retrieval_pipeline.py` → EXIT=0 命中 `:918`（唯一命中 ⇒ 顺序未被改回）。
  - 交付判据② 的反证（「把 D1 改回原样必须看到失败」）属总控反证格：本班**没有当场把它改红**，只证到正向结构（谓词先于截断 + 去重恢复 + `pred=None` 等价），如实记缺。

### R46 · 活动信号回填排序 —— **部分达**

- **判据出处**：跟进单 §21 表 **L517**（原文：「① 有信号后排序变化可测；② **无信号时与现状一致**；③ 隐私：只存计数不存内容」；禁改边界「不得把用户问题原文写进新表」）＋ **§95 L3042-3052**（本班据以纠正「R46 零产物」那笔假账，并明写「已确证还开着的一格就是 R46」）。
- **产物落点**（`866c2f3`）：`app/rag/retriever.py:462-507`（R46 段落 + `:507 ACTIVITY_PRIOR_SMOOTHING = 3.0`）、**`:676`** 先验算式 `raw = ACTIVITY_PRIOR_SIGNAL_GAIN * (accepted - rejected) / (total + ACTIVITY_PRIOR_SMOOTHING)`（`:673-674` `total <= 0 ⇒ 0.0`；`:675`/`:677` 位移上界）、`:722` `def rank_hits_by_activity(...)`、`:751-755`（`carrier["activity_prior"] = {accepted, rejected, shift_ranks, rank_score ...}`）、`:769-770`（`new_rank`）、`:548-575` `_read_activity_signal_rows`、`:1456`/`:1523`（召回出口统一走 `_apply_activity_prior`）；表 `migrations/0011_document_activity_signals.sql:24-44`（`:44` `CHECK (accepted_count + rejected_count > 0)`，**无内容列、无问题原文列**）；出口 `app/api/v1/feedback.py:1-16`、`:101`（拒收未登记字段，只记字段名不记值）、`:166`、`:181-182`（`POST /feedback/document`）、`:211`（入账日志只带 filename/signal/计数）；挂载 `app/main.py:89`；前端腿 `frontend/src/lib/feedback.js:24`（`FEEDBACK_PATH`）、`:38`（`FEEDBACK_BODY_KEYS = ['filename', 'signal']`）、`frontend/src/components/SourceCard.vue:121`/`:130`（采纳/驳回按钮）。并树 sha：后端排序与出口 09-21 已并（§95 L3049），强度上界 `509c1c7`（R153），前端腿 **R195 `484536c`**。
- **达成/未达成**：**②③ 达**（`:722` docstring 把判据② 写成返回语义：无信号时交回**同一个对象**，不依赖浮点比较；③ 表与出口只有计数，前端只发 `filename`+`signal` 两个键）；**① 未完全达**——§95 L3052 原话：判据①「排序真的会变」今天**只证到离线形状（假连接/假表）**，真 PG 并发打点、真 chroma 次序未证明；且计数表按 **filename** 聚合不存身份 ⇒ 同一个人连点能把一篇刷进窗口首位（上界 0.01、无节流无冷却），**是否按人限额属业主裁定**。⇒ 部分达。
- **凭据原文**：
  - `pytest tests/test_r46_activity_signals.py` → EXIT=0，**`40 passed, 34 warnings in 5.10s`**；`pytest tests/test_r152_activity_feedback_docs.py` → EXIT=0，**`8 passed in 0.17s`**。
  - `rg -n "ACTIVITY_PRIOR_SMOOTHING|activity_prior" app/rag/retriever.py` → EXIT=0 命中 `:507`/`:751`/`:769`。禁改边界「不得把用户问题原文写进新表」的三形状：① `rg -n "question" migrations/0011_document_activity_signals.sql` → EXIT=0，但**唯一命中是 `:5` 的自陈注释**（「两列计数、两列时间，没有 query / question / answer / excerpt / note…」）——那是「声称没有」，本班不拿它当证明；② 结构层列清单 `rg -n "TEXT|VARCHAR|CHAR" migrations/0011_document_activity_signals.sql` → EXIT=0 **只有 `:25 filename TEXT PRIMARY KEY`** 一枚文本型列（其余 `:32`/`:33` 是 `BIGINT`），文件名不是内容；③ `rg -n "CREATE TABLE" migrations/0011_document_activity_signals.sql` → EXIT=0 唯一命中 `:24`，表体 `:25-44` 里确无正文列 ⇒ 边界由**列清单**正面证明。
- ⚠️ 勘误：§95 L3042 用「`:728`」指代 `activity_prior` 的键集合，今日 `:728` 是 docstring 的正文行，赋值在 **`:751-755`**（`new_rank` 在 `:769-770`），函数定义在 `:722`；同节引的 **`:676` 先验算式正确**（本班逐字对读）。

### R47 · 术语/同义词接进改写 —— **部分达**

- **判据出处**：跟进单 §21 表 **L518**（原文：「① 同义词题命中改进；② 改写仍走规则不新增模型往返」；禁改边界「不改 `metric_definitions` 语义（R15-b 刚收口）」）。
- **产物落点**（`866c2f3`）：`app/rag/retrieval_pipeline.py:260-331`（R47 纯规则扩展段；`:272` `SYNONYM_EXPANSION_MAX_QUERY_CHARS = ADAPTIVE_REWRITE_MIN_CHARS`，`:301` docstring「用命中定义的 `match_terms` 给检索追加几条纯规则的改写 query」，`:324-325` 长度门槛判定）；调用点 `:882` `all_queries += expand_query_synonyms(query, all_queries, owner_id=owner_id)`，位置在模型改写**之后**（`:878-881` 注释：只填模型没花掉的召回槽位，且「权限口径不受影响：扩展出来的 query 走的还是下面同一个 where/pred」）。并树 sha：`006c613`。
- **达成/未达成**：**② 硬达**（零新增往返，且 `:267` 明写与 R28 用同一把尺）；**① 只能判部分**——本案用例自己声明打的是桩（`tests/test_retrieval_synonym_expansion.py:3` 起「打桩边界（每处都写清楚，免得被读成"测试自己造了个改进"）」、`:13`「全程不建 PersistentClient、不打 Ollama、不连库、不写盘」、`:269` 起是「判据① 前后对比」）。而「改进」的墙上含义要真 embedding：本班实测评测集 **0/105 题面达到 24 字门槛**（题面长度 min 8 / max **20** / mean 13.1），⇒ 门槛对基线**零影响**（与看板 L2084 记的保留理由一致），真实语料上的命中改进量只能真机。⇒ 部分达。
- **凭据原文**：
  - `pytest tests/test_retrieval_synonym_expansion.py -q --no-header -p no:cacheprovider` → EXIT=0，**`22 passed, 1 warning in 1.53s`**。
  - 题面长度（本班 `python -c`，读数见 R36 格）→ `q len min/max/mean= 8 20 13.1`；配套判定：`len(question) >= 24` 的题数 = **0/105**。
  - `rg -n "SYNONYM_EXPANSION_MAX_QUERY_CHARS" app/rag/retrieval_pipeline.py` → EXIT=0 命中 `:272`、`:324-325`。

### R48 · 首屏结论卡片 + 来源 —— **部分达**

- **判据出处**：跟进单 §21 表 **L519**（原文：「① 首屏 ≤1 s 有可用结论；② 后台补齐失败有明确标注」；禁改边界「不得先渲染结论再"纠正"成不同答案（前端 `_correcting` 路径要避开）」）＋ **§93.6 L2828 定案（路线甲）** 六格：① 卡片走 canonical 信封、绝不写 `msg.content`、绝不发成 `event: text` 帧（否则会把判据② 从「诚实的红」翻成**假绿**）；② 加事件名必须同批改 `sessions.js` 的 `EVENT_CLAIMS`（`:255`）与 switch；③ 「首屏卡片未获补齐」是新脸，不许复用 `done-no-result` 文字；④ 🔴 **判据①「首屏 ≤1 s」本班不宣布达成**（机测地板：只吐 1 枚 token 也要 **11.0 s**，最短真实产品腿 **27.5 s**）；⑤ 卡片不许叫"结论"；⑥ 硬门（npm / `lint:colors` / build / 后端总数只增）。
- **产物落点**（`866c2f3`）：`app/api/v1/chat.py:332-405`（R48 路线甲段落；`:359` `_headline_card_data`、`:380` `_answer_headline_frame`、`:405` 事件名 `"answer.headline"`）、`:226`（复用 `canonical_sse_event` ⇒ 带 `sequence`+`timestamp`）、`:2161`（`headline_emitted = False`）、`:2448-2456`（有 `source_rows` 才发卡，且只发一次）；前端腿 `frontend/src/lib/sessions.js:274`（`'answer.headline': 'render'` 认领）、`:490`（`case 'answer.headline':`）、`frontend/src/components/AnswerHeadlineCard.vue:13` / `:70`（`kind: 'unfilled'` = 补齐失败那张新脸）、`frontend/src/components/ChatPanel.vue@866c2f3:919-924`（`headlineOf` + 「没发卡」与「发了卡但正文没补齐」是两张脸）、`:1308-1314`（挂载点，没事件不渲染）。并树 sha：`0ad3d3e`。
- **达成/未达成**：**②/③ 达**（`unfilled` 新脸在组件与面板两侧都在，未复用旧文案）；**判据① / §93④ 明确不宣布达成**，且本班独立复算支持那个「不宣布」：`docs/perf/raw/rate_prefill.jsonl` 里 `prefill_chars_520`（562 字符 prompt、`num_predict=1` 形状）`total_s = 11.020`、`prefill_s = 11.014`、`decode_s = 0.0` ⇒ **1 枚 token 也要 11.0 s**；`docs/perf/raw/rounds.jsonl` 十枚里最短的产品腿 `supervisor_decide_mem total_s = 27.534` ⇒ **1 s 之内不存在任何已生成的结论**。⑤⑥ 属前端线/硬门（本单禁改 `frontend/**`，本班只读行号不判分）。⇒ 部分达。
- **凭据原文**：
  - `pytest tests/test_r48_headline_card_lands_on_the_wire.py` → EXIT=0，**`20 passed, 4 warnings in 10.93s`**；`pytest tests/test_r48_headline_never_enters_the_text_ledger.py` → EXIT=0，**`6 passed, 4 warnings in 7.53s`**（后者正是 §93① 防假绿的那道钉：卡片绝不进 `text` 账）。
  - `.venv\Scripts\python.exe -c` 逐帧读两份 raw（剥 `JSONL ` 前缀）→ EXIT=0：`rate_prefill: prefill_chars_520 total_s=11.02 prefill_s=11.014 decode_s=0.0`；`rounds: min total_s=27.534, max total_s=101.028`。
  - `rg -n "answer\.headline" frontend/src/lib/sessions.js` → EXIT=0 命中 `:274`、`:339`、`:490`；`rg -n "\"answer.headline\"" app/api/v1/chat.py` → EXIT=0 命中 `:405`。

### R49 · 索引瘦身 —— **部分达**

- **判据出处**：跟进单 §21 表 **L520**（原文：「① 有排除规则且上传时给出原因；② 被排除文档在 UI 可见为"未索引"」；禁改边界「不得静默丢弃用户上传」）。
- **产物落点**（`866c2f3`）：`app/documents/index_policy.py:1`（模块自陈「草稿骨架 / 填空模板 / 超小正文不入知识库索引」）、`:40` `REASON_NO_TEXT = "no_text_content"`、`:41` `REASON_TOO_SMALL = "below_minimum_size"`、`:48` 起 `POLICY_REASONS`（稳定原因码集合）；`app/api/v1/chat.py:3512`（注释「R49 索引瘦身：值不值得入索引，在这里判、在花钱之前判。判定只看正文特征，不看文件名」）、`:3398`（docstring：`R49 gives a skipped upload the same fields as an indexed one on purpose` ⇒ 判据①「给出原因」与禁改边界「不静默丢弃」同一处证明）。🔴 判据②：前端只有**上传结果行**的 `⏭️`——`frontend/src/components/DocPanel.vue:191`（`item.status = res.data.status === 'ok' ? 'done' : 'skipped'`）、`:356`（图标三元）；**没有**「这篇已在库里但未被索引」的状态列。
- **达成/未达成**：**① 达**（规则 + 稳定原因码 + 上传回执同字段，三件全绿）；**② 未达（字面）**——三形状反查「UI 有没有『未索引』这一面」：① `rg -n "未索引" frontend/src` → **EXIT=1**；② `rg -ni "index_status|indexState|indexed|excluded" frontend/src` → **EXIT=1**；③ 近邻语义词族 `rg -n "skipped" frontend/src/components/DocPanel.vue` → EXIT=0 只有 `:191`、`:356` 两枚，语义是「上传这一步被跳过」，不是「文档在库内的索引状态」。⇒ 部分达，缺的那条是**前端一张脸**（V 前端线），不是缺机器。
- **凭据原文**：
  - `pytest tests/test_r49_index_policy_rules.py` → EXIT=0，**`24 passed in 0.17s`**；`pytest tests/test_r49_upload_contract.py` → EXIT=0，**`14 passed in 3.77s`**；`pytest tests/test_r49_corpus_calibration.py` → EXIT=0，**`10 passed in 2.24s`**。
  - `rg -n "REASON_" app/documents/index_policy.py` → EXIT=0 命中 `:40`、`:41`、`:48`。

### R50 · 增量索引 + 低峰全量重建 —— **部分达**

- **判据出处**：跟进单 §21 表 **L521**（原文：「① 单文档增量 <2 s；② 全量重建可中断续跑」；禁改边界「重建期间不得出现"检索结果忽有忽无"」）。
- **产物落点**（`866c2f3`）：`app/rag/indexing.py:15-20`（🔴 `:10-22` 是模块 docstring：`:14-15` 「the only thing that creates one at scale is the manual rebuild command (``scripts/rebuild_index.py``)」，`:17-19` 「``plan_index_refresh`` answers "which documents actually need new vectors"」——§95 L3048 把它写成「`app/rag/indexing.py:18` 原话『只挑真要新向量的记录』」，那是**中文转述**，磁盘上那两行是英文；语义对，引用形态不对，已记进 §4 第 15 条（R50 增量规划段落）、`:1865`（`"""Embedding calls this plan predicts. Zero is the incremental result."""`）；`scripts/rebuild_index.py:28`（「没有手工删表的窗口、不会出现库半空」⇒ 正面对应禁改边界）、`:31`（`--apply --incremental --time-budget-seconds 1800` 用法）、`:41`（`--status` ⇒ 可续跑的可查面）、`:810`（「低峰窗口是一个秒数，跑不完的重建…」）；用例自限披露：`tests/test_r50_incremental_index.py:12`（「关于计划书那句"单文档增量 <2 s"：本文件测的是**不含模型推理**的那一半」）与 `:510-511`（函数名与 docstring 各再说一遍）。并树 sha：`090c820`（实现）+ `94f7fa1`（合并 `codex/be-r50`）。
- **达成/未达成**：**② 达**（增量规划 + 时间预算 + `--status` 续跑面在树，20 条可续跑用例绿）；**① 只到「不含推理那一半」**——用例自己写明含推理那一半归总控真机 ⇒ 判 部分达。🔴 另外，单号里「**低峰**全量重建」这半句今天**没有排程产物**：`app/scheduler/jobs.py:14-20` 的 `register_jobs` 今天只声明两枚 job——`:17` `evaluate_all`（interval 5 min，id `alert_check`）与 `:19` `daily_report`（cron 8:00），**没有一枚是重建**。三形状均未命中——① `rg -n "rebuild" app/scheduler` → **EXIT=1**；② 结构名 `rg -n "add_job" app/scheduler/jobs.py` → EXIT=0 只有上述 `:17`/`:19` 两枚（无重建）；③ 语义族 `rg -n "time_budget|off-peak|低峰" app scripts` → EXIT=0 四枚全在 `scripts/rebuild_index.py`（`:28`/`:808`/`:810` 是 docstring 文案、`:787` 是形参 `time_budget_seconds`），**`app/**` 零命中** ⇒ 预算这一腿有实现、没人排程。⇒ 这一格**需要新立一张单**（把 `--apply --incremental --time-budget-seconds` 挂进 scheduler），不是缺一台机器。
- **凭据原文**：
  - `pytest tests/test_r50_incremental_index.py` → EXIT=0，**`15 passed in 2.12s`**；`pytest tests/test_r50_resumable_rebuild.py` → EXIT=0，**`20 passed in 4.06s`**。
  - `git merge-base --is-ancestor 090c820 866c2f3` → EXIT=0；`git merge-base --is-ancestor 94f7fa1 866c2f3` → EXIT=0（⇒ §95 L3048 那笔「双双 IN-HEAD」本班复核成立）。

### R51 · 阶段化 P95 观测 —— **部分达**

- **判据出处**：跟进单 §21 表 **L522**（原文：「① 分类/改写/检索/生成/反思各段 P50/P95 可查；② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%）」；禁改边界「观测不得改变行为」）＋ §29.2 **L1028-1030**（R51 交工链：`rewrite`/`reflect` 两段的插桩被记为后置、lane/tier 不落库）＋ §27.2 L895（R42 的成本占比门移交 R51）。
- **产物落点**（`866c2f3`）：`app/common/stage_timing.py:1`（模块自陈 "one ledger, five named segments, no behaviour change"）、`:48`（`CANONICAL_STAGES = ("classify", "rewrite", "retrieve", "generate", "reflect")`）、`:59`/`:90`（段名→落点与人话说明，`:59` 明写 `rewrite` 段就是 `model_handler.py` 那次非流式 chat）、`:444`（`_stats` ⇒ P50/P95 聚合）、`:547-556`（lane 维度读入面）、`:702`（`missing_stages` ⇒ 哪一段没数据当场可见）、`:744-761`（kill switch；**`:755-757` 未设环境变量时 `return True` ⇒ 今天默认开**）；出口 `app/api/v1/observability.py:625`（把一枚持久 trace 折进账，只用记录字节）、`:653`（`GET /stage-latency`）、`:666`（要审计权才读）；健康面 `app/common/monitoring.py:222-241`（`build_health_snapshot(..., performance=...)`，`:241` `"performance"` 键）。并树 sha：R51 族（§29.2 记）。
- **达成/未达成**：**① 部分达**——五段的名字、聚合、缺格告警都在，但按 §29.2 L1030 记的口径 `rewrite`/`reflect` 两段插桩**后置**，且 lane/tier 维度不落库 ⇒ 「五段都可查」今天只能证到「三段实数据 + 两段有尺没数」；**② 未达（需真机）**——误差 <1% 是加总比对，要在跑分窗里同时有端到端与分段数；本班实测到的一条现场事实支持这个判法：`scripts/r219_rewrite_ledger.py:343` 打印「R51 的 rewrite 段有尺，**run6 没开 STAGE_TIMING_ENABLED** ⇒ 见交回的缺格清单」。⇒ 部分达，收口在 **D 门**（默认今天已开，下一轮天然有数）。
- **凭据原文**：
  - `pytest tests/test_r51_stage_latency.py` → EXIT=0，**`43 passed, 10 warnings in 5.71s`**；`pytest tests/test_r51_observation_is_passive.py` → EXIT=0，**`22 passed in 3.88s`**（钉禁改边界「观测不得改变行为」）。
  - `rg -n "STAGE_TIMING_ENABLED" app/common/stage_timing.py` → EXIT=0 命中 `:755`；`rg -n "run6 没开 STAGE_TIMING_ENABLED" scripts/r219_rewrite_ledger.py` → EXIT=0 命中 `:343`。

### R52 · 断外网自检 + 内网证书 + 批量账号 —— **需真机**

- **判据出处**：跟进单 §21 表 **L523**（原文：「① 断网可装可跑；② 内网域名 + HTTPS 通过；③ 批量建 50 账号可登录且权限正确」；禁改边界「不得为过检临时放宽 TLS 校验」）。
- **产物落点**（`866c2f3`）：`scripts/check_airgap_readiness.py:1-12`（模块自陈 "can this product be installed and run with no internet at all?"）、`:26-28`（`INTERNAL_HOSTS` 白名单，含 `worker`/`scheduler`/`enterprise-brain-ollama-1`）、`:30-36`（`NAMESPACE_LITERAL`：XML 命名空间这种「恰好拼成 URL」的标识符不算外联）、`:37-40`（`NETWORK_CLIENT_IMPORTS` 词族，含 `subprocess…curl|wget` 形状）；TLS 面 `deploy/docker-compose.tls.yml:1`（叠加层）、`deploy/nginx.https.conf.example:20`（🔴 `server_name _;` **占位符**）、`:29`（`ssl_certificate /etc/ssl/brain/fullchain.pem`）；账号面 `scripts/provision_bulk_accounts.py:1`（自陈 "R52 criterion 3"）、`:78`（`--apply` 开关）、`:84`（不给 `--apply` 就什么都不建 ⇒ 默认干跑，符合「未授权不改环境」）。并树 sha：R52 族（跟进单 §40 立案）。
- **达成/未达成**：**三条全需真机**，本班能确证的只有「自检件在场」：断网安装/运行、内网域名 TLS 握手、50 账号真实登录与权限，全是墙上事实，本单禁动容器与模型。另两条如实记录：① nginx 模板今天还是 `server_name _;` 占位 ⇒ ②是「配置面已给、验收未做」；② 计划书 **L377** 已把 **E（企业形态 E1–E6）移出 V1 门槛**，所以本号判「需真机」不等于「V1 未达」，两件事不许混。⇒ 判 需真机（既不判达，也不判未达）。
- **凭据原文**：
  - `pytest tests/test_r52_airgap_readiness.py -q --no-header -p no:cacheprovider` → EXIT=0，**`22 passed in 1.58s`**。
  - `rg -n "server_name" deploy/nginx.https.conf.example` → EXIT=0 命中 `:20 server_name _;`（占位符，未落客户域名）。双向校验：`rg -n "ssl_verify_client" deploy` → EXIT=0，但唯一命中 `deploy/nginx.https.conf.example:39` 是**注释行**（`    # ssl_verify_client on;`）⇒ mTLS 今天未启用。⚠️ 本班上一条命令曾把这条写成「零命中」，此处按实测改正：**零命中与「命中一枚注释行」不是一回事**，禁改边界「不得为过检临时放宽 TLS 校验」之所以没被违反，是因为还没到过检那一步，不是因为校验已开。

---

## 2. 逐号结论汇总表（28 行）

| 号 | §21 小节 | 主要落点（`866c2f3`） | 达成 | 未达成（差哪条） | 需要什么动作 |
|---|---|---|---|---|---|
| R25 | L497 | `docker-compose.dev.yml:34,43,55,59`；`verify_container_stack.py:344,370` | 边界（生产 compose 零改动） | 「不 build 即生效」「闸门 --skip-build 仍过」 | 真机容器栈（E 门） |
| R26 | L498 + §21.8 | `docker-compose.yml:82-97`；`model_capabilities.py:112-152`；`monitoring.py:205-218` | ②③④ | ① 容器内 `nvidia-smi` 有卡 | 业主 H11 真机（已挂号） |
| R27 | L499 + §21.7 | `orchestrator.py:397-403,311-336,513-560` | ①② | ③ 端到端 −≥35 s | A 门跑分窗 |
| R28 | L500 + §21.6 | `retrieval_pipeline.py:60,79-125,868-876` | ①② | ③ 30 题评测不退化 | A 门（fast 档对比窗） |
| R29 | L501 | `test_r29_thinking_tax.py:1-24`；`nodes.py:186-202,815-816` | ③ 前置在场 | ① 空壳、② 30.5 s、④ 报文互斥 | 业主换模型／派生模型，再重量 |
| R30 | L502 | `contracts.py:69-75,102,129-133,157-197`；`nodes.py:815` | ①②③④ | — | 无（只欠一条旧行号勘误） |
| R31 | L503 | `nodes.py:302-321,397,598-628,1000-1047`；`orchestrator.py:1199,1235` | ①③④ | ② 逐片无缺（93/105；chart-03／tool-04 断流） | A 门 + R225 |
| R32 | L504 | `chat.py:1232,1246-1256,1333`；`contract-v1.md:1370` | ①②③ | 乙半 SLO 数值未发布 | D 门（契约自陈不许发布未测数） |
| R33 | L505 | `summarizer.py:92-130,153-173`；`orchestrator.py:342-350` | ①②③ | — | 无 |
| R34 | L506 | `model_config.py:30-97`；`model_handler.py:69,462,525,596` | ①②（① 引 09-19 落盘） | 现值未在本班重测；`.env.example` 缺开关 | A/D 门顺手重量；补一行文档 |
| R35 | L507 | `cache.py:17,31,144-258`；`chat.py:1983-2002,2325`；`provenance.js:217` | ①③ | ② 跨部门／跨密级命中 0 条（P0） | C 门真并发矩阵 |
| R36 | L508 | `business_evaluation_100.jsonl`(105)；`observability.py:696`；`evaluation-report*.json` | ①②③ | — | 无 |
| R37 | L509 + §35.1 | `chat.py:1955-1960`；`queue_worker.py@866c2f3:306-313`；`reliable_queue.py@866c2f3:204-215` | ①②（现场成立） | ③ 队列失败终态＋原因码（谎报 `done`、丢 1519 字正文；311 s>300 s 租约） | D 门：R227 之后 + R222 并树后重量 D-1 |
| R38 | L510 | `migrations/0002:147-165`；`model_handler.py:508-519`；`spans.py:329-340` | 通路形状（读自报、无估算、缺值不写列） | 「抽查一问非零且与 Ollama 一致」 | 真机 D-2 |
| R39 | L491（不建） | — | 不适用 | 不适用 | 无 |
| R40 | L511 | `open_platform.py:77-86,158`；`intelligence.py:21-66` | ①② | ③ 前端 `standard: 500` 仍在且被 `onMounted` 发出 | V 前端线改 demo 播种面 |
| R41 | L512 + §21.8 | `chat.py:226,303-371,470,566`；`sessions.js:255-278,490`；`SourceCard.vue:96`→`ChatPanel.vue@866c2f3:1098` | ①②③ | 队列道 D-3 真机读数（属 R37）；`/approve` 缺口（→R55） | D 门读一次；R55 另单 |
| R42 | L513 + §27.2 | `nodes.py:1209-1337,1372-1405`；`orchestrator.py:565-572` | ①②⑤⑥（改判口径） | ③ 原口径恒红（已降级为报告值） | 业主若驳回 H15 ⇒ 立刻回未达 |
| R43 | L514 + §74四／§81一 | `retrieval_pipeline.py:40`；`model_handler.py:154,168-173,519,537`；`spans.py:292-371` | ①；② 到「历史帧有读数」 | ② 真机 E3 实测；命中率**落不了库**（无 cached 列） | B 门 + 一枚 migration 单 |
| R44 | L515 + 计划书 L194 | `hot_index.py:1-190`；`retriever.py:934-967,1151,1456-1464`；`monitoring.py:269` | ①② 有测试 | ① 只在 379-chunk 小库 + 哈希桩 embedding 上证；延迟未证 | C 门（真实语料 + 延迟） |
| R45 | L516 + §21.9／§21.10 | `retrieval_pipeline.py:439-463,892,906-918,1002-1010`；`retriever.py:1079,1439` | D1、D2、去重恢复、`pred=None` 等价 | 原③ P95（§21.9 L720 明令不实测）；反证刀本班未复跑 | 墙上值属业主侧；反证属总控格 |
| R46 | L517 + §95 | `retriever.py:676,722-770,548-575,1456-1523`；`migrations/0011`；`feedback.py:181-211`；`feedback.js:24,38` | ②③ | ① 真库／真并发次序未证；按 filename 聚合无身份 ⇒ 无节流 | C 门 + 业主裁「是否按人限额」 |
| R47 | L518 | `retrieval_pipeline.py:260-331,882` | ② | ① 真实命中改进量（0/105 题面达门槛；用例打桩） | C 门（真 embedding 对比） |
| R48 | L519 + §93.6 | `chat.py:332-405,2161,2448-2456`；`sessions.js:274,490`；`AnswerHeadlineCard.vue:13,70`；`ChatPanel.vue@866c2f3:919-924,1308-1314` | ②标注、防假绿、认领表、新脸 | ① 「首屏 ≤1 s」（地板 11.0 s／产品腿 27.5 s） | 业主裁口径 + B／E3 换引擎才有数 |
| R49 | L520 | `index_policy.py:1,40-48`；`chat.py:3512,3398` | ① | ② UI「未索引」那张脸 | V 前端线（不欠机器） |
| R50 | L521 | `indexing.py:1741-1865`；`rebuild_index.py:28,31,41,810` | ② | ① 含推理的墙上 <2 s；「低峰排程」零产物 | C 门量 ①；**新立一张排程单** |
| R51 | L522 + §29.2 | `stage_timing.py:1-761`；`observability.py:625,653`；`monitoring.py:222-241` | 三段有数 + 聚合／告警面在场 | ① `rewrite`／`reflect` 插桩后置、lane／tier 不落库；② 加总误差 <1% | D 门（今天默认已开）+ 一枚插桩单 |
| R52 | L523 | `check_airgap_readiness.py:1-40`；`nginx.https.conf.example:20,29`；`provision_bulk_accounts.py:78,84` | 自检件在场 | ①②③ 三条全墙上事实 | E 门（计划书 L377 已移出 V1） |

**结论计数**：达 **8**（R30 R32 R33 R34 R36 R41 R42 R45）· 部分达 **14**（R26 R27 R28 R31 R35 R40 R43 R44 R46 R47 R48 R49 R50 R51）· 未达 **2**（R29 R37）· 需真机 **3**（R25 R38 R52）· 不建 **1**（R39）。合计 28。
---

## 3. 还欠哪些真活

### 3.1 代码欠（写集明确，不欠机器）

1. **R40 判据③**：`frontend/src/devFixtures/approval-demo.js:7` 的 `standard: 500` 与 `ApprovalPanel.vue:5,10,39` 的「import + 播种 + 挂载即 POST」。写集 = `frontend/src/**`（V 前端线）。
2. **R49 判据②**：UI 缺「文档已在库但未索引」那张脸。写集 = `frontend/src/components/DocPanel.vue`（＋可能一枚只读状态列）；后端字段今天在 `chat.py:3398` 已有（`skipped` 与 `indexed` 同字段）。
3. **R50 的「低峰」半句**：把 `scripts/rebuild_index.py --apply --incremental --time-budget-seconds N` 挂进 `app/scheduler/jobs.py:14-20` 的 `register_jobs`（今天那里只有 `evaluate_all`（5 min）与 `daily_report`（8:00），无重建 job）。写集 = `app/scheduler/**` + 新 `tests/test_r2xx_*`。
4. **R43 落库面**：`cached_tokens` 没有列 ⇒ 需要一枚 migration（`migrations/` 新增一版）+ `app/trace/store.py:270-272` 的列白名单。写集 = `migrations/**`（历史上属 R90 拆单范畴，须由总控开串行锁）。
5. **R51 插桩两格**：`rewrite`／`reflect` 两段的真实插桩 + lane/tier 落库。写集 = `app/common/stage_timing.py` + `app/trace/**`（与 R228 写域相邻，派工前先核 `model_budget.py`/`model_handler.py` 归属）。
6. **R46 的身份维度**（若业主裁「按人限额」）：`migrations/0011_document_activity_signals.sql` 的聚合键 + `app/api/v1/feedback.py` 的节流。⚠️ 这条**先要裁定再动码**，本班不代裁。

### 3.2 文书 / 验收欠（不改产品代码）

7. **R34 的 `.env.example` 一行**：`LOCAL_MODEL_KEEP_ALIVE` 未进示例配置（代码默认 300 s 在 `model_config.py:31`）。属文档面缺项，不是行为缺陷。
8. **R37 / D-1、R38 / D-2、R41 / D-3 三格在判读表上仍空**（`docs/testing/run7-readout-sheet-2026-09-24.md:91-93`）。这三格是**验收欠**，不是代码欠——R227 已把 D-1 的缺陷改码，但「不许用改码冒充量过」。
9. **R27③／R28③／R31② 三句判据**（端到端 −≥35 s、fast 档 30 题不退化、逐片无缺）只等 A 门，不等任何新代码；R31 已另立 **R225**（`chart-03`/`tool-04` 两枚未纠正断流）。
10. **R42 的 H15 风险**：③ 是总控改判，业主一句话驳回 ⇒ 本号的「达」自动翻回「未达」。这一格必须在名册上保持**可回溯**，不许沉淀成既成事实。
11. **计划书 §5.2 缺结案列**：计划书 **L468** 已自认「这张表没有结案列，所以被抄来抄去会被当成还剩这么多没做」。本班附议，并给出可执行修法（见 §4 第 7 条）——**由总控落笔，本单不改**。
12. **R45 反证刀**（§21.9 L721 交付判据②）：属总控反证格，本班按禁令没有当场改红（见 §6 第 4 条）。

### 3.3 未达 / 待真机项按「要不要真机」分桶 → 归门

- **桶一 · 不需要真机**（代码或裁定）：R40③、R49②、R50 排程半句、R43 落库列、R51 `reflect`/`lane` 插桩、R46 身份限额（**先裁后写**）、R29（**业主换模型**，不是机器问题）、R42③ 与 R45③（H15/裁定风险）。
- **桶二 · 需要真机 / 跑分窗**，按门归位（**阶段 A 的格已有读数，本班不重验**）：
  - **A 门**（只留指针）：R27③、R31②（= R225）、R28③、R34①（现值）。
  - **B 门**：R29②④（换模型后的 A/B）、R43②（E3 档 `cached_tokens>0` 实测）、R48①（若 1 s 口径不裁，必撞 B）。
  - **C 门**：R35②（跨部门／跨密级 0 条矩阵）、R44①（真实语料 37 483 chunk 覆盖 + 延迟）、R46①（真 PG 并发 + 真库次序）、R47①（真 embedding 命中对比）、R50①（含推理的单文档 <2 s）。
  - **D 门**：R37（D-1，且 R227 提交自陈「必须在 R222 并树后重量一次」）、R38（D-2）、R41 队列道（D-3）、R51①②（分段加总误差 <1%）、R32 乙半 SLO 数值、R42 移交来的成本占比门。
  - **E 门**（计划书 L377 已移出 V1）：R25①②、R52①②③、R26①（H11，已在业主卡上）。

---

## 4. 与现台账的分歧 / 勘误清单（**只列不改**）

**先说一致的部分**：计划书 §5.2 在册 28 号「**零产物 = 0 枚**」（跟进单 §95 L3052 的自纠）**本班逐号复核成立**——每一号都既有自号或拆单号的并树 sha，又有一枚 §21 里点名的交付件（测试件文件名 / 路由名 / 列名 / 开关名 / 事件名），本班未复现「grep 不到单号 ⇒ 零提交」这第三次错。`7375390` 那句「真零产物只剩 R46 消费侧与 R50」确实是假话，`723550c` 的自纠方向正确。

**本班的不同意见只有一条，但对结论有分量**：现台账（§95 L3054、看板 L2084 一族）把这件事表述成「欠的是一道文书活」；本班逐号四格做完后的读数是——**28 号里没有一枚能仅靠文书收口**：8 枚达、14 枚部分达、2 枚未达、3 枚需真机，其中「部分达」有 9 枚缺的正好是判据里那句**墙上时间/真并发**（R27③ R28③ R31② R35② R43② R44① R46① R47① R50①），所以**结案的瓶颈仍在跑分窗（A/B/C/D 门），不在核对**。文书活的产出是「把缺口从模糊变成可排期」，不是「把 28 号清零」。

以下为文实不符，逐条「文句 → 实际代码 → 该改哪份文件哪一节」：

1. **§21.9 标题 L713**「本节取代 §21 表中 R45 行（**L510**）」→ 实际 R45 行现在在 **L516**（**L510 是 R38**）。跟进单多次插入内容使表格整体下移。→ 改 `docs/handoff/2026-09-15-backend-followup-requests.md` §21.9 标题；同族漂移：§21.8 之前那处「L486」（现 +6）。
2. **§21.9 L715-719 的代码锚点全部过期**：`app/rag/retriever.py:270-276`（今日 `:268-275` 是 HTTP 错误正文辅助函数，`:163-168` 是 embedding 诊断块）、`retrieval_pipeline.py:201-215`（今日 `:201` 落在 `QueryRewriter.rewrite` 里）、`:360`/`:361`/`:396-399`（今日对应位置是 `:849` 签名 / `:892` BM25 腿 / `:912-918` 语义腿）。R45 的真实落点是 `:439-463` 与 `:906-918`。→ 改 §21.9 那三条锚点，或在节末追加「行号以 §21.10 L737 的表达式为唯一引用口径」。
3. **计划书 §5.2 R59 行 L204**：「R44/R44b 的花名册读源、写钩子（`app/rag/retriever.py:548-571`）」→ `:548-575` 今日是 **R46 的 `_read_activity_signal_rows`**，热集写钩子在 `:934-967` 与 `:1456-1464`；同行「三处 `pred`（`:314`/`:461`/`:558`）」→ 今日是 `:463` / `:892` / `:912-918`。→ 改 `docs/handoff/2026-09-17-perf-architecture-plan.md` §5.2 第 L204 行。
4. **`app/trace/spans.py:306-310` 的代码内注释过期**：「`app/common/model_handler.py:394-395` 只拷 `prompt_eval_count` 和 `eval_count` 进 `ModelReply`，所以今天没有任何东西给它赋值」→ 今日 `model_handler.py:517-519` 已拷第三枚 `prompt_eval_cached_count`，`:537` 把它交进 reply，`:168-173` 钉默认 `None`。→ 该改 `app/trace/spans.py`（代码单，不在本单写域）。
5. **§21 R27 行 L499 与 §21.7 L640-643 的 `orchestrator.py` 锚点漂移**：`app/agents/orchestrator.py:201`（今日是空行，`:203` 才是 `_checkpointer`）、`:285-305`（今日段落标题在 `:286`、短路守卫在 `:397-403`）、`:688-693`/`:754-759`（今日无条件边在 `:975-980`）、`:381-393`（今日该区间是消息过滤 + `:393` 的 R27 注释）。→ 改跟进单两处；引用口径建议改为函数名 `_deterministic_plan_hit:311` / `route_main:479`。
6. **`docs/handoff/2026-09-19-r34-keep-alive-residency.md:157`**：「离线用例 `tests/test_r34_keep_alive_residency.py`（**46 条**…）」→ 本班实测 **`47 passed`**。→ 改该行数字。
7. **计划书 §5.2 L180 与跟进单 L502**：「拆掉 3 处硬编 `timeout=30`（`nodes.py:304`、`nodes.py:370`、`tools.py:443`）」→ 今日三种形状全零命中（`rg -n "timeout=30" app` → EXIT=1），超时唯一入口已是 `http_timeout(...)`（四处调用点）。配合计划书 **L468** 自认的「无结案列」→ 建议给 §5.2 增结案列，并在 L468 追加「R30 行的三个行号已过期」的点名。
8. **跟进单 §95 L3042**：「命中条目带 `activity_prior`（…，`:728`）」→ `:728` 落在 `rank_hits_by_activity` 的 **docstring** 里，键集合赋值在 **`:751-755`**（`new_rank` 在 `:769-770`），函数定义在 `:722`。同行引的 **`:676` 先验算式正确**（本班逐字复核）。→ 改 §95 那处行号。
9. **计划书在 L1634 附近引用的 `stage_timing.py:443` / `:550`** → `:443` 今日是空行（`_stats` 在 `:444`），`:550` 是 docstring 文本。→ 改该行引用（引函数名更稳）。
10. **跟进单 §21 R46 行 L517 的 `contracts.py:157 score_type`** → 今日 `contracts.py:157` 是 `input_budget_tokens`，`score_type` 那枚已备枚举在 **`app/agents/contracts.py:314`**（消费点在 `app/agents/evidence.py:82,192` 与 `app/api/v1/chat.py:286`）。→ 改 L517 锚点（语义本身成立：枚举确实在 `contracts.py` 里备着）。
11. **看板 `docs/handoff/2026-09-15-orchestration-board.md:2074（快照 `866c2f3` 行号；同一句在现 HEAD `20bc26b` / `c731356` 上均为 `:2089`，本班先前记的 `:2084` 是**按现工作树取的、且取歪了一行**，此处按快照改直）`**：「评测集 105 题题面**全 8–18 字**、0 题 ≥24 字」→ 本班实测 **min 8 / max 20 / mean 13.1**；「0 题 ≥24 字」仍对，但「全 8–18 字」漏了 19、20 两档。→ 改该行数字（门槛结论不变）。
12. **§93.6 L2828 判据② 锚点**：「同批改 `frontend/src/lib/sessions.js` 的 `EVENT_CLAIMS`（`:255`）与 `:443-466` 的 switch」→ `:255` 今日**仍对**（`export const EVENT_CLAIMS = {`），但 switch 分支体今日在 `:470-500`（`case 'answer.headline':` 在 `:490`），`:443-446` 已是聚合初始值。→ 改该处第二个锚点。
13. **计划书 L194 与跟进单 L515 的口径关系**：计划书已把「105/105 覆盖」订正为「379 chunk 小库 + 哈希桩 embedding」，跟进单 L515 的判据原文仍是「覆盖 95% 查询的热集常驻」——**两处都不算错但连读会误收**。建议 L515 行尾加一句「结案口径见计划书 L194」。（本单不改。）
14. **看板 `docs/handoff/2026-09-15-orchestration-board.md:1973（快照 `866c2f3` 行号；同一句在现 HEAD `20bc26b` / `c731356` 上均为 `:1988`，本班先前记的 `:1983` 同样取歪，此处按快照改直）` 那行「零提交单：R29 R30 R31 R32 R33 R34 R37 R38 R40 R42 R43 R44 R46」** → 本班逐号在树复算：这 **13 号全部有产物**（本文件 §1 给了路径:行与并树 sha），该行是假账。它已被后续 §91 四（L2780）、§94 二（L2950）、§95 三（L3052）三次订正，但**原文仍留在 L1983**，任何下班从那里起读都会拿到旧账。→ 建议总控在该行就地加「已过期，见 §95 L3052 / 见 `2026-09-25-plan-ticket-closure.md`」的指路。（本单不改。）同文件 **`:2340`** 的「结案 15 单」方向与本文件不冲突，但它是**名册账**——本单按纪律一律不采信其结论，只采信磁盘字节。
15. **跟进单 §95 L3048**「`app/rag/indexing.py:18` 原话"只挑真要新向量的记录"」→ 该行今日是**英文** docstring（`:17-19` `plan_index_refresh answers "which documents actually need new vectors"`），中文串在 `app/**` 里零命中（`rg -n "只挑真要新向量的记录" app` → EXIT=1；该串只命中跟进单自己）。→ 改 §95 该格引用形态（语义成立，改成「意译 `:17-19`」即可）。
---

## 5. 命令全录（本班实测 EXIT 码）

- 解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -m pytest <单文件> -q --no-header -p no:cacheprovider`（**一次一发**，未并行、未加 `-n`、**未跑 `scripts/run_gate.py`**）。
- 快照读取：`git show 866c2f3:<path>` 落 `%TEMP%` 后按 `\n` 分行取行号；工作树读取一律 `[System.IO.File]::ReadAllText(f) -split "\n"`（与 `rg -n` 的编号同源）。

### 5.1 定向件（**64 枚文件 / 66 枚次** → 全 EXIT=0）

账目：三份循环日志合计 **63 枚文件 / 63 枚次（零重复）**；表内第 64 枚 `test_r33_history_guardrails` 为班内单跑一枚次；另两枚次是**记录在格内**的追跑（`test_r44_hot_index_coverage` 的 `-s` 取 stdout、`test_r37_report_lane_worker` 在 `47b6643` 的复跑）⇒ 63 + 1 + 2 = **66 枚次**。

| 件（`tests/`） | 末行读数 | 用于 |
|---|---|---|
| test_gpu_compute_honesty | 15 passed in 0.21s | R26 |
| test_supervisor_roundtrip | 8 passed, 4 warnings in 4.33s | R27 |
| test_route_fallback_correction | 13 passed, 4 warnings in 4.46s | R27 |
| test_retrieval_rewrite_tier | 29 passed in 0.97s | R28 |
| test_r29_thinking_tax | 39 passed in 1.71s | R29 |
| test_r147_native_leg_verdict | 19 passed in 1.99s | R29 |
| test_r30_model_tiers | 11 passed in 1.08s | R30 |
| test_r30_timeout_budget | 20 passed, 4 warnings in 4.42s | R30 |
| test_r30_config_defaults | 74 passed in 1.03s | R30 |
| test_r30_context_limit_guard | 15 passed in 1.16s | R30 |
| test_r204_single_call_ceiling | 9 passed in 1.18s | R30 |
| test_r74_dead_budget_field | 9 passed in 0.33s | R30 |
| test_r31_generation_stream_passthrough | 13 passed, 4 warnings in 8.51s | R31 |
| test_r31_stream_pieces | 27 passed in 1.03s | R31 |
| test_r149_sse_text_pieces | 16 passed, 4 warnings in 9.17s | R31 |
| test_r203_answer_leg_streams | 15 passed in 1.94s | R31 |
| test_r203_sse_progressive_frames | 16 passed, 4 warnings in 7.72s | R31 |
| test_r32_lane_contract | 67 passed, 4 warnings in 8.46s | R32 |
| test_r141_lane_behavior | 62 passed, 4 warnings in 7.59s | R32 |
| test_r33_zero_model_compression | 9 passed, 4 warnings in 4.98s | R33 |
| test_r33_history_guardrails | 11 passed, 4 warnings in 8.46s | R33 |
| test_r34_keep_alive_residency | 47 passed in 1.34s | R34 |
| test_answer_cache_scope | 21 passed, 4 warnings in 9.43s | R35 |
| test_chat_cache_safety | 3 passed, 4 warnings in 6.95s | R35 |
| test_evaluation_report | 8 passed in 0.17s | R36 |
| test_r37_report_lane_enqueue | 14 passed, 4 warnings in 6.92s | R37 |
| test_r37_report_lane_worker | 14 passed, 14 warnings in 9.04s （本班又在 47b6643 工作树复跑同件 → 14 passed, 14 warnings in 8.17s；两次同 14 passed ⇒ 该件既有断言未被 R227 放宽） | R37 |
| test_r38_cached_tokens_honesty | 4 passed in 0.84s | R38 |
| test_r38_native_input_tokens | 11 passed in 1.01s | R38 |
| test_approval_precheck_standard_source | 25 passed in 0.46s | R40 |
| test_r67_department_self_report | 23 passed, 6 warnings in 5.09s | R40 |
| test_r75_standard_source_single_source | 96 passed, 6 warnings in 6.15s | R40 |
| test_sse_sources | 14 passed, 4 skipped, 12 warnings in 8.73s （skip 原因实测打印 test_sse_sources.py:206: SSE_EVENT_INVENTORY_OUT not set） | R41 |
| test_r42_zero_model_calls | 10 passed, 4 warnings in 4.30s | R42 |
| test_r42_lane_rules | 29 passed in 1.03s | R42 |
| test_r42_fallback_upgrade | 10 passed, 4 warnings in 4.20s | R42 |
| test_r42_lane_ratio | 5 passed in 1.06s | R42 |
| test_r42_numeric_questions | 32 passed in 1.09s | R42 |
| test_r43a_native_cached_tokens | 10 passed in 1.15s | R43 |
| test_r43a_rewrite_prefix_reuse | 12 passed in 0.77s | R43 |
| test_r167_answer_prefix_reuse | 29 passed, 4 warnings in 14.70s | R43 |
| test_r44_hot_index_unit | 17 passed in 0.15s | R44 |
| test_r44_hot_index_chroma | 18 passed in 3.45s | R44 |
| test_r44_hot_index_coverage | 2 passed in 6.92s （另以 -s 复跑一枚取判据 stdout，见 R44 格） | R44 |
| test_r44_hot_index_paging | 7 passed in 3.16s | R44 |
| test_r79_hot_index_defaults | 24 passed in 0.49s | R44 |
| test_r79_hot_index_observability | 11 passed, 20 warnings in 27.48s | R44 |
| test_r59b_pg_read_switch | 24 passed in 0.65s | R44 |
| test_prefiltering | 32 passed, 1 warning in 1.75s | R45 |
| test_r46_activity_signals | 40 passed, 34 warnings in 5.10s | R46 |
| test_r152_activity_feedback_docs | 8 passed in 0.17s | R46 |
| test_retrieval_synonym_expansion | 22 passed, 1 warning in 1.53s | R47 |
| test_r48_headline_card_lands_on_the_wire | 20 passed, 4 warnings in 10.93s | R48 |
| test_r48_headline_never_enters_the_text_ledger | 6 passed, 4 warnings in 7.53s | R48 |
| test_r49_index_policy_rules | 24 passed in 0.17s | R49 |
| test_r49_upload_contract | 14 passed in 3.77s | R49 |
| test_r49_corpus_calibration | 10 passed in 2.24s | R49 |
| test_r50_incremental_index | 15 passed in 2.12s | R50 |
| test_r50_resumable_rebuild | 20 passed in 4.06s | R50 |
| test_r51_stage_latency | 43 passed, 10 warnings in 5.71s | R51 |
| test_r51_observation_is_passive | 22 passed in 3.88s | R51 |
| test_r52_airgap_readiness | 22 passed in 1.58s | R52 |
| test_r227_discard_is_honest | 19 passed, 14 warnings in 15.36s | R37（改码在场） |
| test_r227_lease_heartbeat | 16 passed in 0.43s | R37（改码在场） |

日志落 `%TEMP%\r224_a.log` / `r224_b.log` / `r224_c.log`（单循环顺序执行，一枚跑完才起下一枚；三份合计 **63 枚文件 / 63 行读数、零重复**，本班已逐行核过）。上表「末行读数」列由本班脚本**按文件名从这三份日志原文机械回填**（非手抄），与日志逐字一致；未进那三份循环的单枚复跑（`test_r33_history_guardrails` → `11 passed, 4 warnings in 8.46s`、`test_r37_report_lane_worker@47b6643` → `14 passed, 14 warnings in 8.17s`）已在格内注明来源。总控可直接复跑任一单文件核对。

### 5.2 只读 git / rg / 计算类（用途 + EXIT）

- `git log --oneline -3` → **0**（本班末次读到首行 `73eae8a`，时间戳 12:04:59）；`git rev-parse --short HEAD` → `73eae8a`；`git rev-list --count 866c2f3..HEAD` → **25**；`git log --oneline -1 866c2f3` → **0**；`git merge-base --is-ancestor 866c2f3 HEAD` → **0**。
- `git diff --stat 866c2f3..HEAD -- app frontend deploy scripts tests docs` → **0**。本班按时间序取了三次同一命令：`20bc26b` = 29 files / +9305 / −105；`c731356` = 29 files / +9307 / −105；**`73eae8a`（末次）= 34 files / +10226 / −118**。⇒ 这列数字**天生不可复现**（主干在动），只有快照侧的可复现；与本班引用行号有关的仍只是 §0.1 第 4 条那 8 枚。
- 逐文件 `git diff --quiet 866c2f3 HEAD -- <file>` 复算五遍（同一份 68 枚被引清单）：`a9dd17e` 61/3、`47b6643` 61/7、`20bc26b` 61/7、`c731356` 61/7、`73eae8a` **60/8** ⇒ 结论「漂移集合随时间增长，右列不可复现属正常，左列（快照）恒可复现」。七枚 DIFF 的快照 LF 计数与现值见 §0.1 第 4 条。
- §21 判据行命中核对（本班实跑）：把 §1／§2 里 `R25`…`R52` 各自引用的 `L497`…`L523`／`L491`，对 `git show 866c2f3:docs/handoff/2026-09-15-backend-followup-requests.md` 逐枚取该行、比对是否以 `| **R<号>** |` 开头（R39 比对 `L491` 那句「R39 不建，沿用 R17」）→ **28／28 命中，EXIT=0**。⚠️ 反例教训：先用「行内是否含 `R25` 子串」判命中会**假阳性**（`L497` 处含 R25 的散文行不止一处，同一文件里 `| **R25** |` 还出现在 `L547`）——上表用的是行首锚，不是子串。
- 跟进单／看板的行尾构成（`.venv` python 字节级计数，EXIT=0）：跟进单 `2026-09-15-backend-followup-requests.md` = CRLF **3070** / lone LF **25** / lone CR **1534**（LF 总 3095）；看板 `2026-09-15-orchestration-board.md` = CRLF **0** / lone LF **4062** / lone CR **2**；计划书 `2026-09-17-perf-architecture-plan.md` = CRLF **467** / lone LF **0** / lone CR **0**。⇒ 派工单说的「跟进单 3070 CRLF + 25 lone LF 混体」为真，且另含 1534 枚 lone CR（派工单未提）；**本文件不以任何一份混体文档为行尾模板**，自产 522 枚行尾 100% CRLF、lone CR = 0、无 BOM。
- 工作树并发脏化核对（本班实跑，EXIT=0）：`git status --porcelain` → 见上条清单；对被引且被脏化的两枚按 `git show 866c2f3:<path>` 与 `python` 读工作树**两侧各取一次行文本**比对 ⇒ `app/rag/indexing.py` 的 `:15`/`:18` 两侧 SAME，`docs/api/contract-v1.md:1370` 两侧 DIFF（快照有标题、脏工作树为空行）⇒ 印证「必须按 commit 锚，不能按工作树锚」。
- 看板引用行号的口径订正（本班自查出、已改进 §4 勘误条 11／14）：`零提交单：R29…` 一句在快照 `866c2f3` 是 **L1973**、在现 HEAD（`20bc26b` / `c731356` / `73eae8a` 三枚同值）是 **L1988**；`题面全 8–18 字` 一句快照 **L2074**／现 HEAD **L2089**（三枚现 HEAD 同值）。本班初稿曾记 `1983`／`2084`（既不等于快照口径也不等于现口径）⇒ 已按快照改直并两侧并列。
- `git merge-base --is-ancestor <sha> 866c2f3`：`11f9b1f`/`118801e`/`6ee2f79`/`af027ce`（R26a/b）与 `090c820`/`94f7fa1`（R50）→ 全 **0**。
- `git show --stat ad85821`、`git show --stat b17b4dd` → 0，各 `2 files changed, 83 insertions(+)`（R25 边界：生产 compose 零行）。
- `git log --oneline --all --grep=R26` → 0（12 命中，产物枚 4）；`--grep=R26a --grep=R26b` → 0（4 命中）；`git log --all -S"NVIDIA_VISIBLE_DEVICES" -- docker-compose.yml` → 0（`118801e`）；`-S"reservations" -- docker-compose.yml` → 0（同 `118801e`）。
- `git log --oneline --all --grep="R25"` → 0（`ad85821`/`b17b4dd`/`9389afd`/`9ebddad`）。
- `git show 866c2f3:app/common/reliable_queue.py` / `deploy/queue_worker.py` / `frontend/src/components/ChatPanel.vue` → 0；快照行号事实：租约唯一写点 `reliable_queue.py:178`（`ex=self.lease_seconds`，默认 `:67 = 300`）、`ack()` 写 `done` 在 `:201`、`complete()` 丢弃支 `:204-215`（`:210` 判 → `:211` 删结果 → `:212` 仍 `ack()`）、worker 丢弃点 `queue_worker.py:306-313`、`ChatPanel.vue:919-924`/`:1098`/`:1308-1314`（R48/R41 前端腿）。
- `rg` 正向命中（各 **EXIT=0**，注明快照/工作树者按该副本跑）：`DEFAULT_TIER = TIER_FULL`、`本次检索 0 次大模型往返`、`跳过第二发模型往返`、`ModelTier.COMPRESS 这一档\*\*保留`（orchestrator `:348`）、`来源定位|\[来源`（summarizer `:16`/`:42-47`，见 R33）、`_deduplicate\(_retain_permitted`、`ACTIVITY_PRIOR_SMOOTHING|activity_prior`、`TEXT|VARCHAR|CHAR`（0011 只 `:25`）、`question`（0011 只 `:5` 注释）、`standard: 500`、`demoForm`、`Three-Tier SLO Contract`、`use_answer_cache = `、`http_timeout\(`（五处，见 R30）、`STAGE_TIMING_ENABLED`、`return True`（stage_timing `:757`）、`run6 没开 STAGE_TIMING_ENABLED`、`SYNONYM_EXPANSION_MAX_QUERY_CHARS`、`answer\.headline`（快照 `chat.py:405`；前端 `sessions.js:274/:339/:490`）、`REASON_`、`lease`（快照 reliable_queue）、`ssl_verify_client`（注释行，见 R52）、`server_name`、`reload-dir`（dev `:43`）、`skipped`（DocPanel `:191/:356`）、`add_job`（jobs `:17`/`:19`）、`CREATE TABLE`（0011 唯一 `:24`；0002 多枚，其中 `:147` = `model_calls`）、`time_budget|off-peak|低峰`（四枚全在 `scripts/rebuild_index.py`）、`preview.open = true`、`SSE_EVENT_INVENTORY_OUT`、`R26`、`R25`、`R39`（仅 docs）、`沿用 R17`、`只挑真要新向量的记录`（只命中跟进单，不命中代码）。
- `rg` 零命中（各 **EXIT=1**，均已按三形状配平，**不用于推「零产物」**）：`timeout=30`、`timeout=3[0-9]`（app/agents app/common app/tools）、`docker-compose.dev|/app/app`（生产 compose）、`reload-dir`（生产 compose）、`not bool\(request.session_id\)`、`session_id`（`cache.py`）、`\bR39\b`（`app tests scripts deploy`）、`未索引`（frontend/src）、`index_status|indexState|indexed|excluded`（frontend/src，`-i`）、`cached`（migrations）、`只挑真要新向量的记录`（app）、`input_tokens` 与 `prompt_eval`（`docs/testing/sidecar-run7.jsonl`）、`rebuild`（`app/scheduler`）、`expire\(|renew` 与 `lease`（对 `866c2f3` 快照副本；现 HEAD 命中 R227 的 `renew_lease`）、`LOCAL_MODEL_KEEP_ALIVE`（`.env.example`）。
- `.venv\Scripts\python.exe -c`（只读计算，各 EXIT=0）：① 两个评测 fixture 计数 → `rows=30` / `rows=105`、`tier {问答:50, 分析:35, 报告:20}`、`category` 11 类（口径冲突 19、跨部门权限 6）、`q len min/max/mean= 8 20 13.1`；② 三份 `evaluation-report*.json` → run7 `answer_correctness=0.5333 evidence_coverage=0.7905 total=105 latency_ms.count=105 p95=127405.91`，run5 `0.4762/0.6857`；③ `docs/testing/sidecar-run7-frames.jsonl` 帧账 → `rows=105`、`criterion_two_holds` 真 **93**、`prefix_breaks` 合计 **4**、`extra_chars` **0**、`missing_chars` **0**、`max_stream_frames>1` **95**、12 枚不成立题的 id 全列（`chart-03`/`tool-04` 各 `prefix_breaks=1` 且 `corrective_replacements=0`）；④ `docs/perf/raw/rate_prefill.jsonl` → `prefill_chars_520 total_s=11.020 prefill_s=11.014 decode_s=0.0`，`rounds.jsonl` → `min total_s=27.534 / max 101.028`；⑤ `rate_think2.jsonl` → `think_off_decode300 40.700 / think_on_decode300 47.662 / think_off_prefill383 12.565 / think_on_prefill383 12.213`。
- 落盘件行号/结构核对（各 EXIT=0）：`migrations/0002_execution_data_lineage.sql:147-165`、`migrations/0011_document_activity_signals.sql:24-44`、`docs/testing/run7-readout-sheet-2026-09-24.md:83-97`、`docs/api/contract-v1.md:1370/1380/1403`、`deploy/nginx.https.conf.example:20/29`、`pyproject.toml:47-51`（`[tool.pytest.ini_options]` 内**无** `addopts`，与 AGENTS.md 那条铁规一致）。

---

## 6. 本班没做完 / 没验的部分（明写，不用推测填空）

1. **未跑全量回归门**（`scripts/run_gate.py`）——按硬禁令。因此本文件不对「R25–R52 之外有无连带回归」下任何结论，也不引用任何历史全量 passed 数字（§21 L492 共同判据：历史 HEAD 的数字一律不得当现状引用）。
2. **未打模型、未连真库、未动容器/镜像**——所以 R25①②、R26①、R27③、R28③、R29②④、R31②、R34①、R35②、R37 现场值、R38、R43②、R44 真实语料、R46①、R47①、R48①、R50①、R51①②、R52①②③ **没有一项被本班重量过**，本文件只给「代码格 + 门指针」。
3. **R37 §35.1 判据⑧ 本班未验**：那条要求「追平主干后亲跑全量，对 2104/35/0 只增不减」，需要全量门 ⇒ 属禁令。这一格缺的是**一次全量回归读数**，不是代码。①–⑦⑨ 本班逐条对到了磁盘。
4. **R45 交付判据②（反证刀）本班未复跑**：§21.9 L721 要求「把 D1 改回原样必须看到失败」。本班只验了正向结构（`:918` 唯一命中 + `_retain_permitted` 的 `pred is None` 短路 + `:463` 谓词先于截断），没有当场制造红。这一格归总控反证账。
5. **前端硬门未验**（R48⑥、R40 的 `npm test` / `lint:colors` / `npm run build`）：本单写域不含 `frontend/**` 的改动，也未获授权跑前端套件 ⇒ 前端那三条硬门本班只做到「读行号、看是否认领」。
6. **R30 交付判据里的「不改并发语义（R23）」本班只做了静态核对**（`http_timeout` 四处调用点 + `MODEL_MAX_CONCURRENCY` 未被 R30 触碰），未跑并发用例。
7. **R26①／R34①／R52 的原始读数引用的是落盘文档**（`README.md:93`、`docs/handoff/2026-09-19-r34-keep-alive-residency.md` §2、计划书 L377）——本班如实标注为「引用」，不冒充本班实测。
8. **一处快照账必须写清（免得被当成抄错）**：派工单钉 `866c2f3`；本班取证期间主干从 `a9dd17e` → `ccf8942` → `47b6643` → `20bc26b` → **`c731356`** 持续推进（`866c2f3..HEAD` = 23 枚；`47b6643` 与 `20bc26b` 两枚都发生在本班落盘之前）。本班把**所有引用行号重新按 `866c2f3` 逐枚取过**：7 枚被改文件走 `git show 866c2f3:` 副本，其余 61 枚经 `git diff --quiet` 证明两侧同值。同一族内容在快照与现 HEAD 的对照（按行文本匹配得出，不靠手感）：
   - `frontend/src/components/ChatPanel.vue`：「两张脸」注释 `866c2f3:920` ↔ `a9dd17e:943`；`function headlineOf` `:923` ↔ `:946`；`preview.open = true`（R41 引用条点回原文）`:1098` ↔ `:1161`；「R48 路线甲 · 首屏那张卡」挂载点 `:1308` ↔ `:1371`。**本文件一律记左列**。
   - `app/common/model_handler.py`（快照 638 LF → `20bc26b` 753 LF）：R30 / R43 引用的 `http_timeout` 三枚调用点 `866c2f3:337` ↔ `20bc26b:431`、`:467` ↔ `:561`、`:620` ↔ `:735`（本班按文本 `timeout=http_timeout(` 两侧各取全命中列表：快照 `[337, 467, 620]` / 现 `[431, 561, 735]`）；`cached_tokens=cached_tokens` `:537` ↔ `:631`。R34 / R38 / R43 另引的 `:69`、`:154`、`:462`、`:525`、`:596` **两快照逐字同值**（本班对读到行文本）。`app/api/v1/chat.py`（4002 → 3986 LF）：字面量 `answer.headline` `:405` ↔ `:406`、`use_answer_cache = bool(answer_scope)` `:1983` ↔ `:1966`；另 `:226` / `:286` / `:332` / `:936` / `:1191` / `:1232` / `:1955` / `:3398` / `:3512` 本班逐枚对读同值。**本文件一律记左列（快照）**。
   - `deploy/queue_worker.py`（448 → 527 LF）与 `app/common/reliable_queue.py`（376 → 622 LF）：R37 丢弃点 `866c2f3:306-313`，`:306` 原文 `if not queue.complete(request_id, answer):`；`reliable_queue.py` 租约唯一写点 `:178`（默认值 `:67 lease_seconds: int = 300`）、`ack()` 写 `done` 于 `:201`、`complete()` 丢弃支 `:204-215`（`:204` 原文 `def complete(self, request_id: str, result: str) -> bool:`、`:215` 原文 `return self.ack(request_id)`）——全部按快照取。这几处在现 HEAD 已被 R227 `5830422` 改写（新增续租、租约支不再一律 `ack()`）⇒ 本班对 R37 下的结论**是快照上的结论**，总控在新 HEAD 复跑时请按右列对照，勿判成本班行号漂移。
