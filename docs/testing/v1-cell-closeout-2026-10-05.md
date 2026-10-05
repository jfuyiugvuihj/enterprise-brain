# V1 欠账逐格结案（2026-10-05 第十七班续席 · 总控亲取）

**这张纸存在的唯一理由**：业主令「真欠十格＋五格＋门里另欠，今天晚上写完，写一格填一格，不许拿假账骗我」。
所以每格只准交四样：**判据原文（逐字）／本班现取读数／量具与代次／三态结论**。
三态只有四种写法：**达 · 没达 · 量不到 · 移出 V1**。「大概」「基本完成」「应该没问题」在这张纸上不算字。
🔴 本班把三格**过期账**翻出来了（R25／R37③／R43② 记欠但事实已在树上），也翻出两格**看着能移其实不能移**（R29②／R43②）——
过期账与虚账一样是账错，两头都要当场订正，不为难后人。

## 0. 一句话汇总（十八格）

| 组 | 格 | 本班结论 |
|---|---|---|
| 真欠 10 | R25② R26② R27③ R28③ R31② R37③ R38③ R44① R47① R51② | 达 2（R27③ R37③）· 没达 5（R26② R31② R38③ R44① R51②）· 量不到 2（R28③ R47①）· 没验 1（R25②，码早在树上） |
| 五格改档 | R29② R43② R48① R50② R52① | 该移出的只有 3（R48① R50② R52①）· R29② R43② 是**账过期**，各立重量单 |
| 门里另欠 | C① C④ D×3 前端九环＋两张失败脸 R60 停写 R579 索引腿 | 全条**未验／量不到／没做**，一格都没绿 |

## 1. 真欠十格

### 1.1 R25② 开发期热挂 `app/**` — **没验**（不是没做·订正上一班账）

- 判据原文（跟进单 §21 R25 行逐字）：「改一行 `app/**` 后不 build 即生效；`verify_container_stack.py --skip-build` 仍能过」；边界「不改生产 compose 的副本语义；挂载只加在 dev override 文件」。
- 本班现取·第一件（**这一件推翻上一班**）：`git ls-files` 命中 **`docker-compose.dev.yml` 早已在册**，文件头自陈「Development overlay for 企业智脑 — R25. NOT part of the delivered stack.」，内容把 `./app:/app/app` 挂进 backend／worker／scheduler 三格，backend 的 command 加 `--reload --reload-dir /app/app`；并逐字写明**为什么不叫 `docker-compose.override.yml`**（那名字会被不带 `-f` 的客户命令静默继承，私有化机器上会挂出一棵空目录把 `/app/app` 遮掉），也写明 `scripts/verify_container_stack.py::run_compose` 恒带 `-f docker-compose.yml`，所以容器门 cert 的仍是镜像态。⇒ **边界那条满足**。
- 本班现取·第二件：`docker inspect enterprise-brain-backend-1` 取回**只有五枚命名卷**（appdata／documents／applogs／generated／vectordb），`app/**` 零 bind mount ⇒ 现网跑的是镜像态（生产语义确实没动），但两句判据**都要挂上 overlay 实跑一扇才取得到数**，本机上从没挂过。
- 量具：`git ls-files`＋`Get-Content docker-compose.dev.yml`＋`docker inspect --format {{json .Mounts}}`，代次 10-05 16:5x 现取。
- 结论：**没验**。🔴 上一班那句「R25 真没做，立 R669 写这件文件」是半句假账——文件在树上，缺的是取证。R669 的半径因此从「写文件」改成「**带 overlay 起一扇→改一行看免 build 生不生效→`--skip-build` 复跑仍过→把这三步写进开发文档**」。动容器排在夜窗之后（带 2 是延迟判据，不许碰）。

### 1.2 R26② 拿不到卡必须显式报错 — **没达**（差一次开关，但后果业主看得见）

- 判据原文（跟进单 §21 R26 行逐字）：「② **拿不到卡必须显式报错 + 稳定码**，不得静默 CPU」。
- 本班现取：`app/common/model_capabilities.py::require_gpu_enabled` 现读 `return (os.getenv(REQUIRE_GPU_ENV) or "").strip().lower() in _TRUE_VALUES`，docstring 自己写着「Unset keeps today's warning-only behaviour」＝**未设即 fail-open**；`docker exec enterprise-brain-backend-1 printenv OLLAMA_REQUIRE_GPU` 交回 **rc=1（键不存在）**，`deploy/.env.server` 里也没有这一行。
-  ⇒ 「丢卡必报错」这条在生产配置上**到今天一次都没走通过**：真拔掉卡它会静默落 CPU 继续答，正是判据②要禁止的形状。A③ 因此只算**半格**（容器内 `nvidia-smi` 有卡 ✅／丢卡必报错 ❌）。
- 结论：**没达**。解锁＝把 `OLLAMA_REQUIRE_GPU=1` 写进 `deploy/.env.server`＋`--force-recreate` 三枚容器。🔴 这会**改生产行为**（无卡客户机当场起不来），本班不擅自翻，列进 §4 待业主那一格；同时立 **R673**：把开关语义钉死（设了＝fail-closed 带稳定码；没设＝逐字保持今天行为），两枚反证牙各红一次。

### 1.3 R27③ 端到端 −≥35 s — **达**（本班可结案）

- 判据原文（跟进单 §21 R27 行逐字）：「① 第 2 发不再发生（日志计数）；② 先加测试钉住…兜底仍能纠正错派；③ 端到端 −≥35 s」。
- 本班现取：基线 **160.552 s**（`docs/perf/latency-budget-2026-09-16.md`）→ 问答类 p95 **50.1 s**（`scripts/r595_latency_readout.py`，run22 与 run23 两窗互证，读数代次 `9556513`）＝**降 110.4 s ≥ 35 s ✅**。
- 判据① 的凭据本班日志现取：`[Supervisor] 确定性计划命中 → 复读第 1 发 dispatch，跳过第二发模型往返`。判据② 的兜底测试早先已判达——凭据＝账尺自己那行欠账只逐字点名了 ③（`R27（PARTIAL）差：③ 端到端 −≥35 s`），①② 不在欠账里。
- 结论：**达**。解锁：并 R666 之后由总控把台账从 PARTIAL 改 LANDED（尺的 C7/C8 必须仍 PASS，不许手改判定词）。

### 1.4 R28③＝A④ 30 题评测不退化 — **量不到**（同码复跑，跨代次对子 0 枚）

- 判据原文（跟进单 §21 R28 行逐字）：「③ 30 题评测不退化」。
- 本班现取：run22→run23 五项指纹全等＝**同码复跑**，`scripts/r634_category_delta.py` 要的正是**跨代次**对子，本班取到 0 枚 ⇒ 逐类不退化今天**量不到**，不是达。上一班曾在 run4 抓到过一次真退化（文档问答 0.6842→0.6316，就是 `doc-19` 一枚），run5 又收回，所以这句历史上也只算「有条件成立」。
- 本班另取一件事：`scripts/r634_category_delta.py` 吃 `runXX-report.json`，窗只产 `-quality.json`——`run22-report.json`／`run23-report.json` 本班已用 `scripts/run_quality_evaluation.py --output` 离线重出在盘（各 13,718／13,714 B）。
- 解锁＝今晚夜队列带 2（run25–28 四扇同码 105 窗）＋带 3（跨窗对子＋逐类）。🔴 若带 3 仍是零对子，就必须拿两枚**不同代次**的窗来比才叫「不退化」，不许用同码复跑冒充。

### 1.5 R31② 流式逐字无缺字 — **没达**（红四枚有名有姓，治它的单在飞）

- 判据原文（跟进单 §21 R31 行逐字，②那一半）：「**片段时间戳不重叠、逐字比对无缺字**」。
- 本班现取（代次 `9556513`，夜窗外离线复演 `%TEMP%\evalrun\run22-sidecar-frames.jsonl` 994 KB／105 行）：在册七枚合取 **102/105（0.9714）**，②原文两格口径 **104/105**。红四枚逐枚＝`chart-01`／`tool-04`（各只发 1 帧）、`data-12`（2858 字一帧发完）、`chart-04`（`missing_chars=1258`／`extra_chars=36`，只在 33 题子集窗炸，全表窗同题 64 帧全绿＝**形状相关不是随机**）。
- 承接：**R662**（执行层 Erdos 在飞，写域 `app/agents/nodes.py`＋`app/api/v1/chat.py`；本班 16:4x 现取该树已长出两枚新牙 `tests/test_r662_formed_answer_streams_progressively.py`／`tests/test_r662_approved_leg_park_notice_streams.py`）。
- 结论：**没达**，等 R662 交卷验收。

### 1.6 R37③ 队列失败有终态与原因码 — **达**（过期账订正·附一条点名例外）

- 判据原文（跟进单 §21 R37 行逐字）：「③ 队列失败有终态与原因码」。
- 本班现取·三件：① `app/common/reliable_queue.py::fail_or_retry` 在真落 dead 那一支把 `{reason, retryable}` 写进同一本 message 账（键 `dead_verdict`），🔴 且**排在写状态键之前**（反过来就留一瞬「状态已叫 dead、账上还答不出为什么」）；② `deploy/queue_worker.py` 共**八处**调 `fail_or_retry`，本班逐枚点开实参：七枚交稳定码——`::_refuse_identity` 一枚、`::_fail_report_turn` 两枚（其 `code` 现读派生自 `record["error"]["code"]`，取不到落 `record["status"]`，再兜底 `internal_error`）、`::_process_reserved` 四枚（其中两枚 `code`、一枚字面 `authorization_required`、一枚常量 `NO_MODEL_CALL_READOUT = "no_model_call_recorded"`），剩一枚交 `str(e)`；③ 在册牙本班亲跑 `tests/test_r585_dead_terminal_reason.py`＋`tests/test_r545_queue_failure_teeth.py`＋`tests/test_r254_queue_terminal_honesty.py` ＝ **99 passed / 0 failed / 37.39 s**。R585 并树 `1f0f0f2` 的提交词自陈「dead 这枚终态第一次带原因码进持久面」。
- ⇒ 台账那句「R37（PARTIAL）差：③ 队列失败有终态与原因码」是**过期账**：R585 已把它兑现，没人改档。
- 🔴 例外本班逐字点名、不藏进「达」里：八枚里唯一交 `str(e)` 的是 `deploy/queue_worker.py::_process_reserved` 收尾那一支——异常原文进账，读的人拿不到可比的码。主路径全覆盖且有牙，判据按「失败有终态与原因码」成立；这一枚例外另立 **R675** 补码（连同 `authorization_required`／`no_model_call_recorded` 两枚私有字面一起收进中心词表），**不许**因为它就把已兑现的格子继续挂欠，也**不许**因为挂了这一枚就把「达」写成「完全达」。
- 结论：**达**（例外已点名并立单）。

### 1.7 R38③ token 计量与自报一致 — **没达**（差两件事，落纸收不了）

- 判据原文（跟进单 §21 R38 行逐字）：「抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致」。
- 本班现取：`model_calls` 五列齐、`/ask` 路径**有行且非零**（3955／245／467，含 `cached_tokens` 非零）；🔴 **`/chat` 旧路径打完模型不落 `model_calls` 行**（受控抽查：16:23 那一问之后，表里最新一行仍是 07:34:49 UTC）；`metadata` 只有 `{"worker":"doc"}`，**没存 Ollama 原始 usage** ⇒ 一对一「与自报一致」在库内**证不了**。仓内 `rg 'INSERT INTO model_calls'` 零命中（走通用 persist），所以这不是改个常量能收的。
- 结论：**没达**，承接 **R670**（上一班已口头立过，本班正式沿用：① /chat 落行 ② 把 Ollama 自报 usage 原样存进去）。判据那条边界「不得估算冒充实测 token 数」＝这一格最怕拿派生数凑绿，验收逐条对。

### 1.8 R44① 热集常驻覆盖 95% 查询 — **没达**（驱动件不在盘上）

- 判据原文（跟进单 §21 R44 行逐字，①那一半）：「覆盖 95% 查询的热集常驻」；边界「**不许**因提速牺牲部门/密级过滤（pre-filter 先于热集）」。
- 本班现取：`app/rag/hot_index.py` 在树上，但账上点名的**让路驱动件已丢**；在册承接是 **R663／R654** 两枚同源单（先对写集再择一投）。本格还欠第二次读数：95% 覆盖率要在真机量，不是有文件就算。
- 结论：**没达**。今晚不投它（写域与 R659 那一族都碰检索侧，槽位也给执行层收尾单）；明早排波次。

### 1.9 R47① 同义词题命中改进 — **量不到（零分母）** ← 这一格要业主出手

- 判据原文（跟进单 §21 R47 行逐字）：「① 同义词题命中改进；② 改写仍走规则不新增模型往返」。
- 本班现取·码：`app/rag/retrieval_pipeline.py::expand_query_synonyms` 在树上（术语/同义词扩展，纯规则，`SYNONYM_EXPANSION_MAX_QUERIES = 3`），判据② 由代码形状满足（不新增模型往返）。
- 本班现取·分母（**这才是卡点**）：评测集 `tests/fixtures/business_evaluation_100.jsonl` 现读 105 行，类别计数逐枚＝文档问答 19／口径冲突 19／多轮对话 12／Excel计算 12／报告生成 12／主动洞察 7／审批判断 6／跨部门权限 6／图表生成 4／无证据问题 4／工具调用 4。**里面没有「同义词」这一类**（`rg` 全库唯一命中"同义"字样的是 `data-07` 的题干）。⇒ 「同义词题命中改进」**没有题可命中**，与 C④ 的 `claims` 零分母同族。
- 结论：**量不到**。解锁只有两条路，都在业主手里：**(甲) 批准往评测集加 12 枚同义词题**（评测集被 `tests/test_evaluation_report.py` 钉着，改题必须单独批）；**(乙) 把判据① 改写成现集能量的形状**——同义扩展开／关两档的 top-5 变化率（不新增题，只新增量具）。承接 **R676**（等裁；本班不自作主张改评测集）。

### 1.10 R51② 端到端与分段加总误差 <1% — **没达**（分子缺，本班亲跑出数）

- 判据原文（跟进单 §21 R51 行逐字）：「① 分类/改写/检索/生成/反思各段 P50/P95 可查；② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%）」；边界「观测不得改变行为」。
- 本班亲跑 `scripts/r631_stage_sum_delta.py`：默认道 run22 与 run23 各 **退出码 3＝量不到**，理由逐字——分段跨度只在持久化 trace 事件里（`*.finished` 的 `payload.duration_ms`），盘上三份产物一件都没这枚字段；端到端腿 105 枚在位＝**有分母没分子，比值算不出来**。
- 本班又试第二道：把本班隔离的 32 MB 历史事件件喂 `--traces`，分段腿**取到 trace 2447 枚／跨度 7405 枚**，但同一份读数里 🔴 **整窗未出现的段＝classify／rewrite／retrieve／generate／reflect 五段全缺**、可比 0 枚 ⇒ 那件是 R117 探窗形状（`trace-r117-*`），**不可用作分子**。`scripts/r636_stage_coverage.py --window run22` 同样 RC=3（原料缺失 `run22-traces.jsonl`）。
- 判据① 的真源本班现读在 `app/common/stage_timing.py::CANONICAL_STAGES`（五段名册），读出面 `app/api/v1/observability.py`。⇒ ① 有码、② 欠量具。
- 结论：**没达**，承接 **R674**：让评测窗按题导出 trace 事件（`runXX-traces.jsonl`），R631／R636 才有分子。零模型改动、不动测量条件，排得进今晚带 2 之后的维护拍。

## 2. 五格改档：只有三格该移出，两格是账过期

账尺五号（`scripts/audit_plan_ticket_ledger.py` 写死的 reason）逐枚现读，对照本班盘面：

| 格 | reason 原句（节选） | 本班现取 | 结论 |
|---|---|---|---|
| R48① 首屏 ≤1 s | 本机地板 11.0 s | 计划书原文「只吐 1 枚 token 也要 **11.0 s**」（`docs/perf/raw/rate_prefill.jsonl` `prefill_chars_520`）；这句本就写在 **B 行**不是 A 行 | 🔵 **移出 V1**（物理不可达，属给客户报配置档位的交付活） |
| R50② 可中断续跑 | 丙案裁定句 | 结案裁定已在 `docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md`：判据② 按现读证据判达、「低峰自动触发」半句移出 | 🔵 **移出 V1**（台账只是没落这一档） |
| R52① 断网可装可跑 | E 行整行 | E1–E6 属上线实施清单，开发机上既不能证实也不能证伪 | 🔵 **移出 V1** |
| R43② E3 档 `cached_tokens>0` | 「真机 E3 读数与 cached 落库那一列都还没有」 | 🔴 **账过期**：本班现读 `model_calls.cached_tokens` **已非零**（467／369／493）⇒「cached 落库那一列」已到位；只剩「E3 档」那半属 B 行（换推理引擎） | 🟠 **拆两半各归各档**，不许整格混进 OUT 凑数 |
| R29② 生成轮 30.6→≤22 s | 「`/v1` 上五种关思考写法全无效⇒迁原生 `/api/chat`」 | 🔴 **账过期**：本班日志现证今天已在走原生腿（`[Model] ollama-native 应答 … prompt_eval_count=95 eval_count=157 … thinking_chars=0`）⇒ 迁腿那一半**已达成**，②只差一次重量 | 🟠 **改回 PARTIAL＋立重量单**，不许 OUT |

⇒ 对执行层 **Bohr／R666** 的验收裁定（它的工单写死「只许把这 5 号标 OUT」）：`OUT` 只放行 **R48① R50② R52① 三枚**；R29② R43② 由总控改回 PARTIAL 并各立重量单。🔴 本班**不给 Bohr 发长消息改判据**（在册致命通道，事故 #112／#113 两枚执行层都死在收长消息那一刻）——机制它交，哪几号进 OUT 由总控验收时定。

## 3. 门里另欠（这些不在 16 号里，但 V1 完工判据要）

| 格 | 本班结论 | 现取凭据 | 还差的那一步 |
|---|---|---|---|
| C① 越权 0 条 | **未验**（不许翻绿） | 生产库 `users.department`／`classification` 全空；R193 那 51 格今日真红 0 但都在沙盒／合成侧；沙盒 252 枚合成标签**只证行为不证客户隔离**；A1／A3／H13 三件 09-28 已结案，欠的**不是代码** | 客户真实密级回填＝交付阶段，本机不可证 |
| C④ 无依据断言率 | **量不到（零分母）** | `unsupported_claim_rate=0.0`，但三窗 315 行里带 `claims` 键＝**0 行**；本班复核 `run22-answers.jsonl` 首行键集现取＝answer／answer_source／evidence／first_token_at／id／latency_ms／thinking_chars／tool_calls——**没有 claims**（坐实上一班那句） | 欠一枚「把 claims 落进答案件」的量具升级单 |
| D 报告档三格 | **未验** | `REPORT_LANE_VIA_QUEUE` 仍 off；r573 明写报告档 12 枚**队列可读面键数=0**＝那层从没被测过 | 今晚夜队列带 1 的 1b／2b 两扇就是开关 on 的样本，第一次有机会取到 D 的读面数；跑完必须还原 off |
| A② 三口径 | **没达** | 见 §1.5：在册合取 102/105，红四枚有名 | R662 交卷＋验收 |
| 前端九环走查＋两张失败脸 | **没做** | 本班只验过一次界面真实键盘问答（步骤牌＋来源卡＋正文逐帧长出）＋SSE 经 nginx 帧账（0s status→3.8s step→15.1s heartbeat→20.4s 起 21 枚 text 帧单调增长→done）；九环清单**没逐项打勾**；embedding 缺失／无 GPU 两张失败脸没拍 | 子 agent 开窗逐环拍图（不占本机模型窗，走浏览器） |
| pgvector R60 停写 | **没达** | 双写召回腿已跑成：135 题里 **67 题 top-5 不一致**、**Chroma 侧 24 题空召回**（PG 侧均给 5 条）、`drift` 零差集＝停写的正面论据；但停写前置量具 r633 五枚要先重锚（=R672） | R672（Zeno 在飞）→ 再 R60 |
| R579 索引腿 | **没达** | 生产现网 1008 枚上规划器**根本不选 HNSW**：`EXPLAIN ANALYZE` 交 `Seq Scan on chunk_vectors`＋top-N heapsort ≈2.4 ms，禁 seqscan/sort 才走 `Index Scan using chunk_vectors_embedding_idx` ≈44.5 ms（慢 18 倍），`pg_stat_user_indexes` 里该索引 `idx_scan` 至今 0 ⇒ 那句「PG 索引=精确 105/105」是**平凡真** | R579 量索引腿质量与拐点 |

## 4. 要业主出手的（本班不自作主张，共三件）

1. **`OLLAMA_REQUIRE_GPU=1` 翻不翻**（§1.2）：翻了以后无卡客户机**当场起不来**（这正是判据②要的），但也意味着演示机一掉卡就白屏。本班默认**不翻**，等一句话。
2. **R47① 走甲还是乙**（§1.9）：甲＝批准往评测集加 12 枚同义词题（评测集被钉着，改题单独批）；乙＝判据改写成现集能量的形状（同义扩展开／关两档 top-5 变化率）。本班默认**走乙**（不动题源、不新增模型往返），但甲乙都改判据口径，得点头。
3. **`git push gitee HEAD`**：今天 24 枚提交未推（现取 `Your branch is ahead of 'gitee/codex/data-file-catalog'`），本机是唯一副本，H6 未结。本班不 push（在册规矩：push 属业主）。

## 5. 本班新立／沿用单（编号卫生：投单前已 `rg` 取 max，docs 里 R6xx 最大到 R668，事故 max #121）

| 单号 | 内容 | 状态 |
|---|---|---|
| R669 | R25② 带 dev overlay 实跑取证＋开发文档接线（**半径已从"写文件"订正成"取证"**） | 待派 |
| R670 | R38③ 计量两缺：`/chat` 落 `model_calls` ＋原样存 Ollama usage（**沿用上一班口头号**） | 待派（写域含 `chat.py`，须等 R662 收席） |
| R671 | /ask 体验欠账（上一班口头号·一问 41.6 s vs /chat 6.2 s，多路改写三子问题串行）——**号已占，本班不重定义** | 待派 |
| R672 | R659 item① 并树收尾：重锚 r633 五枚（三族必须在场＋第四族必须缺席且摘牙可复现） | 🟡 已投 · 执行层 Zeno |
| R673 | R26② 开关语义钉死（设了 fail-closed 带稳定码／没设逐字不变）＋两枚反证牙 | 待派 |
| R674 | R51② 分段腿导出：窗按题产 `runXX-traces.jsonl`，喂 R631／R636 | 待派 |
| R675 | R37③ 那条点名例外：`queue_worker.py` 收尾兜底传 `str(e)` 改稳定码 | 待派（小单） |
| R676 | R47① 零分母处置（甲加题／乙改形状，等裁） | 等业主 |
| R677 | R44① 热集让路驱动件（与在册 R663／R654 同源，先对写集择一） | 待派 |

🔴 另记 **R667**（在册沿用：R659 item② 语料腿三值化，与 7 枚字面值 `legacy_chroma` 正面互斥，形状同 R664）——本班不改它内容，只登记它仍欠。

🔴 **编号卫生补一句给下一班**：本班 16:5x 现取 docs 里 `R6xx` 最大到 **R668**，所以 R669 起才是空地。上一班在会话里口头浮过 R669／R670／R671 三个号但**一个都没落进 docs**——本班照其原意沿用 R669（R25）与 R670（R38③），并把 R671 留给它本来的 /ask 那笔，**不自带第二套编号**，以免同号双投。

## 6. 本班记的两笔自己的错（不藏）

- **事故 #122**（本班新撞）：总控为了批量杀掉自己误起的 pytest，按命令行模式 `Stop-Process`，**连执行层正在跑的 state② 复跑一起杀了**（受害 pid 32980／20316，属 Erdos/R662 的 45 枚同名件复跑）。根因是本班自己把 `Get-ChildItem -Filter` 传了数组，`$f` 变空 ⇒ pytest 退化成全量收集，本班为了止损扩大化杀进程。
  订正规矩：**只按自己会话的 pid 杀，绝不按命令行模式批杀**；写文件枚举一律 `Where-Object { $_.Name -match ... }` 或先列清单再验枚数＝预期。受害单已由其执行层自行重试（本班 16:4x `read_thread` 现读 Erdos 状态 active、在重投 state②）。
- **过期账三枚**（R25②／R37③／R43②＋R29②）：上一班把「文件不存在／判据欠」当成结论，实际是**没现取到层与名字**。本班已逐枚现读取证并写在上面各格里。
