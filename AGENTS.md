# 企业智脑 — Enterprise Brain

> **🚨 最高优先级规则：在用户明确的任务范围内，默认连续完成相关步骤并在当前请求内交付完整结果，不再强制每完成一个文件或步骤都停下来等待审核。只有遇到破坏性操作、与其他 Agent 的文件冲突、范围无法判断或缺少关键业务信息时才暂停询问。严禁在未获授权的情况下运行会改变数据或环境的操作。**

## 项目简介
私有化部署的企业 AI 智能分析平台。客户装在自己服务器上，上传公司文档和经营数据，AI 自动知识问答、数据分析、生成图表报告、异常监控。数据永不离开客户机器。

## 技术栈
- 后端: FastAPI + LangGraph + **RAG 检索（读路径 10-03 已切到 PGVector；Chroma 遗留件仍在双写、待 R60 停写退役，见下条）**
- 向量库定案: **PostgreSQL + PGVector 是生产向量库（业主 2026-09-24 定案，不再变更）**；Chroma = **退役中的遗留件**（读路径 10-03 已切走，只剩双写与退役未做），**新代码一律不得新增 Chroma 依赖或新的 Chroma 写点**。其余存储：本地文件存储 + Redis。切换进度唯一事实源 = `docs/handoff/2026-09-17-pgvector-adoption-plan.md`（今天真实位置：双写已开且 NUL 缺陷 R130 已修、全库 1008 枚向量在位；**切读的码已全部并树**（R59 块1 `bee9d01` + 块2 `dbc2047` + 旋钮 R231 `ed9f8b0`，翻默认不再需要改代码），🔴 **默认已于 10-03 08:4x 真翻成 pgvector**（`deploy/.env.server:77` 写 `INDEX_BACKEND=pgvector` ＋ `docker compose --env-file deploy/.env.server up -d --force-recreate backend worker scheduler`；现读三枚容器 `printenv INDEX_BACKEND` 均为 pgvector、backend 进程内 `app.rag.indexing.read_backend()` 为 pgvector、代码缺省 `INDEX_BACKEND_DEFAULT` 仍为 chroma 未改；凭据＝跟进单 §152 与看板 §4EJ 名册行）⇒ **语义读答复今天由 PG 腿给出**，Chroma 只剩「仍在双写、待 R60 停写退役」那一格；计划书 §9.3 格①「服务内端到端走真库」已由 R382 交出读数（并树 `b498c88`：84 问全答、零 bypass、名次重合剔空腿后 0.9378），09-27 第九格之后挡着翻默认的是四格——格②热集让路延迟仍欠一台安静机器重量；格③生产 `department`/`classification` 全空（🔴 判据今天改写成**四件可失败判据**并记 **「未验」**，见计划书 §13；沙盒那 252 枚合成标签只证行为、**不证客户隔离**，不许拿它翻绿；治它的 R387 取证已交回但**整单退回**；复工**不是** R390——该号因执行层 `Popper` 失联已作废（事故 #62，明文不复用免同号双投），实际两笔都在树上：**R400 `69e0035`**（标签血缘三处行号改运行时派生＋A1/A2/A3 回填账）＋ **R409 `5621e8d`**（给 A3 的批准材料配一枚现跑的牙，`merge-base --is-ancestor` 09-28 现取 rc=0）⇒ 格③ 欠的**不是代码**；且 A1／A3／H13 **三件已于 09-28 结案**（`docs/handoff/2026-09-17-human-gates.md:365`＝H13 裁甲、`:373`＝A1「不在真库做、改沙盒 R469」、`:374`＝A3「交付阶段按客户真实密级做，不进 V1/V2 代码路径」；10-03 订正：上一班把这三件列成「待业主」是过期账，见跟进单 §152 二））；查询期 `hnsw.ef_search` 40 vs 遗留引擎实测 100 **今天有码了**（R386 并树 `1b4406a`：PG 读腿在排名语句之前、同一笔事务内 `set_config(...,TRUE)` 钉到真源 100，缺省即与遗留引擎同宽，**默认读后端 10-03 已翻（见上）**），剩两格未清——客户尺寸两档差仍未量（沙盒 1008 枚上"100 与暴力精确解 180/180 全等"**不可外推**：抬宽后索引扫描已≈全库暴力扫量级，且自探针量不到近重复吃预算那一族）。🔴 **10-03 实测再加一刀**：生产现网 1008 枚上规划器**根本不选 HNSW 索引**——`EXPLAIN ANALYZE` 交 `Seq Scan on chunk_vectors` 加 `top-N heapsort` 约 2.4 ms，禁 `enable_seqscan`/`enable_sort` 才走 `Index Scan using chunk_vectors_embedding_idx` 约 44.5 ms（慢 18 倍），`pg_stat_user_indexes` 里 `chunk_vectors_embedding_idx` 的 `idx_scan` 至今为 0；⇒ 那句「PG 索引=精确 105/105」是**平凡真**（量到的是全表精确解，不是图索引），索引腿的质量与拐点改由 **R579** 量。反向凭据仍成立：`vector_scope_pkey` 的 `idx_scan` 单题一问从 1207 涨到 1217，说明读腿真在 PG 上；R386 挖出的那一族**两枚在册量具自己站在窄档 40 上量**，本单一手现读**今天已治**——由 R393 并树 `f509f36` 收掉（R408 09-28 现取：`git cat-file -t f509f36` = commit、`git merge-base --is-ancestor f509f36 HEAD` 成立、`git show --name-only f509f36` 逐一点名`scripts/r59c_sandbox_corpus.py` 与 `scripts/r59_recall_compare.py`，两枚脚本现场调用各自的取档函数都交回 **100**＝真源 `app.rag.pg_store.configured_hnsw_ef_search()` 同一笔读数，两枚脚本里一枚候选宽度数字都没有，凭据 `docs/perf/r393-tool-width-drift-2026-09-27.md`），上面那句「剩两格未清」到今天就只剩**客户尺寸两档差**那一格未量；`INDEX_BACKEND=pgvector` 写进 `deploy/.env.server` 这一步**已执行**（业主 10-02 授权总控代做，10-03 08:4x 落地并现读自证），🔴 它要的是**容器重建、不是镜像重建**——`deploy/.env.server` 走 `docker-compose.yml` 里 `x-runtime` 那格 `env_file:`，它在容器创建那一刻才解析，`docker restart` 不重读，正解 `docker compose up -d --force-recreate`（同口径已由 `tests/test_r255_env_documents_the_conversion.py` 钉着，09-21 runbook P-8 已把旧的"不重建镜像等于没改"自判过宽并改窄；镜像里不带 `.env`；带 `build:` 的只有 `migrate`（它产出后端镜像 `enterprise-brain:local`）与 `frontend` 两格，backend/worker/scheduler 三格共用前者且各自没有 build 段，所以 `docker compose build backend` 当场报 No services to build）
- 模型: 第一版只管理本机 Ollama；远程模型回退必须显式开启，默认关闭
- 前端: Vue 3 + Element Plus
- 数据: pandas + matplotlib
- 部署: setup.sh + Docker

## 项目结构
```
企业智脑/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── agents/               # Multi-Agent (Orchestrator + Doc + Data + Chart + Export)
│   ├── api/v1/               # 聊天 API / 文档上传 / 告警
│   ├── models/               # Pydantic schemas
│   ├── common/               # 日志 / 配置
│   ├── rag/                  # 文档解析 / 向量检索
│   └── tools/                # 工具函数
├── frontend/                 # Vue 3
├── static/                   # 生成的图表
├── docs/                     # 文档
├── .env                      # 环境变量
└── pyproject.toml            # uv 依赖管理
```

## 开发流程
按当前任务计划、`docs/current-functionality-2026-09-10.md` 和 `docs/superpowers/` 下的已审核计划执行。不要根据旧的“第一阶段 Day 2”描述判断项目实际完成度；以当前源码、测试、文档和用户最新指令为准。

## 已完成
- 项目骨架、FastAPI 入口、日志、文档加载、Chroma 检索等基础能力已存在；
- 当前完成度、风险和未完成项以 `docs/current-functionality-2026-09-10.md` 为准；
- 不要仅根据历史计划中的“已完成”列表或测试文件名称推断功能已经达到生产可用。

## 核心原则
- 先理解现状和已有改动，再在当前任务范围内一次性完成相关文档或代码工作
- 文档和设计任务可以连续完成；代码任务完成后再统一说明修改、风险和验证结果
- 未经用户明确要求，不运行会启动服务、修改数据库、生成大量数据或改变外部环境的操作
- 测试只在任务需要且环境安全时运行；运行前确认不会覆盖用户数据
- 与其他 Agent 协作时避开对方正在修改的文件；当前前端由其他 Agent 负责，未经明确授权不得修改 `frontend/`
- 跨 Agent 协作优先通过接口、设计文档和数据契约衔接，不复制一套平行实现
- **优先多 Agent 并行开发**：接到一轮工作先判断「它能不能按写集切成几块同时做」。能切就必须切，默认并行度不低于 3；串行是例外，不是默认。
- 并行的唯一边界是**写集**，不是功能名称：两枚 Agent 会改同一入口、同一契约或同一测试文件就必须串行；一枚 Agent 独占一棵工作树，两枚同树即写域冲突。
- 并行不等于放任：一个 block 内只允许一次投递调用，投递报错＝未落地（先取证零写入，不当场补投）；派工一律不得带 model 覆盖，中途换模型会污染消息 id 并使整条线程必死。
- 收席取证的**时效**：「零写入」只在取证那一刻成立——`send_input` 让旧席复工时它随时能再写。收席动作之前必须重跑 `git -C <树> diff --numstat HEAD`＋`ls-files --others`＋`rev-list --count <基点>..HEAD` 三枚，全部在收席那一刻现取；引用几分钟前的旧账就收席＝事故 #107（那样留下的独有牙会被当成零写入扔掉）。
- 并行产出的验收由总控独担：逐条对判据、总控亲自复跑测试，达标才代提交；执行层一律不得 commit。
- 并树验收必须交两次数字：**dirty 态（已 apply 未 commit）跑一遍，`git commit` 之后在干净树复跑同名件再跑一遍**，两次的文件清单逐枚点名（09-29 R496 正是漏了第二遍：一枚拿「施工期盘面脏」当永真判据的钉并树即自毁，事故 #96）；执行层自报的读数只可写「执行层自报」，不得写成总控亲跑（同族事故 #95）；常驻钉不许把「此刻盘面脏不脏」当成判据——要判归因就写态分支＋影子端正控，别把别人的合法手写成本单的罪证。
- 全量回归门一律用 `python scripts/run_gate.py`（**并发数由 `run_gate.py` 按空闲内存自选，纸上不写死 `-n`**：09-28 同树两跑实测自选到 `-n 6`／302.16 s；**枚数不在本文写死**——在册最新绿票是看板 §4DT 那笔 `5963dfe` 时点的 8479 passed / 55 skipped / 1 xfailed / exit=0（507.9 s，同为 `-n 6`），而枚数随每笔并树上涨，所以**判回归一律按同一 HEAD 的复跑数互比、并与看板最新绿票对账，不要拿本文件里的历史数字当尺**；首跑税真实存在，旧账里的 `-n 7`／`-n 8`／218 s／247→85 s／`7722 / 50 / 2` 全部过期）。**不许把 `-n` 写进 `pyproject.toml` 的 `addopts`**：六枚测试件会嵌套起 pytest，全局并行会递归扇出；`loadfile` 不是风格问题，按测试粒度分发会把 29 枚起子进程/容器的件拆成假红。反证钉（`counter_evidence` / `teeth`）**不分层出门**，门再便宜也要全跑。
- 长独占窗口（真机跑分、72 h 长跑等）期间总控**不许空转等待**：窗内只做零 CPU 争用且不改测量条件的活（取证、写判据、排波次、预配工作树），窗内硬禁是并树、跑测试、动容器、打模型；等待一律用阻塞式监视而不是轮询。
- 向量库口径已定：生产方案是 **PGVector**，Chroma 是**待退役的遗留件**。文档与新设计一律按 PGVector 写目标态；Chroma 只允许出现在「遗留 / 退役中 / 尚未切完的读路径」语境，**既不许写成最终架构，也不许写成已下线**——它今天仍然在提供读服务，把它说成已退役同样是假话
- 评测、Agent Trace、RAG 调试和后台配置必须区分“当前已有基础”和“后续目标”
- 私有化部署 = 一台机器一个企业，物理隔离
- 数据不出客户服务器
