# 企业智脑 版本路线与各版本要求

版本：2026-10-05-**r4**（取代同日 r3；r3 取代 2026-09-22-r2，也取代仓内 `docs/version-roadmap-and-next-week-plan-2026-09-22.md`）
文档性质：V0–V5 的功能边界（长期有效）＋ 截至某一代次的完成现状（易失效，失效条件见 §0.4）
读数代次：主树 HEAD `dd16297`，分支 `codex/data-file-catalog`，2026-10-05 19:2x +08，总控现取（`12aa93c`／`9efff02` 之后的两笔全是 docs-only；r4 那句 `12aa93c` 从此属过期账）
编制口径：**每条现状后面跟着一条可复制的现取命令**；拿不出命令的句子一律不写。旧版的百分比完成度全部作废。

## 0. 这份文档为什么必须重写

### 0.1 r2 里已经被盘面推翻的行（逐条对账）

| # | r2 原话 | 今天现取 | 现取凭据 |
|---|---|---|---|
| 1 | 「主树最后记录 3494 passed／HEAD 4586bb4（09-22）」 | HEAD `c4ec463`，今天已 16 枚提交；最近一次全量门（上一班夜、基点 `9556513`）＝**48 failed／11208 passed／58 skipped／2 xfailed／1592.0 s／exit=1**。48 枚红已归因：46＝派生坐标漂移（R660 在治）＋1＝trace 落盘压在 SSE 临界路径的 P1（R661 在治）＋1＝`r645` 刀③ 两枚不变式互斥（拟 R664） | `python scripts/run_gate.py`、`git log --since=midnight --oneline` |
| 2 | 「`app/rag/indexing.py` 的 `INDEX_BACKEND` 仍为 `chroma`，检索仍走 Chroma」 | 生产三枚容器 `printenv INDEX_BACKEND` **全是 `pgvector`**（10-03 08:4x 翻默认＋`--force-recreate`，凭据＝跟进单 §152、看板 §4EJ）；而代码缺省 `app/rag/indexing.py::INDEX_BACKEND_DEFAULT` **仍是 `chroma`** 未改。两句都成立，**只说一半就是假账**：生产现值≠代码缺省值 | `docker exec enterprise-brain-backend-1 printenv INDEX_BACKEND`、`git grep -n INDEX_BACKEND_DEFAULT -- app/rag/indexing.py` |
| 3 | 「OCR 当前没有扫描 PDF/图片检测、没有 OCR 引擎、没有置信度、没有 OCR 文本入索引链路」 | `app/rag/ocr.py` 通道在树（R298 并树 `e441d10`）；`app/rag/loader.py` 有 `PAGE_SOURCE_OCR`／`PAGE_SOURCE_OCR_EMPTY`／`PAGE_SOURCE_OCR_DEGRADED` 三档页源与降级句前缀，且有「有文本层的页不再重跑 OCR」的判据④；R301 把 `pdf_extraction` 真过 HTTP、R338 把它画进上传回执。⇒ **V2 的 OCR 已提前落地**。未验的那格是「客户真实扫描件的质量」——真扫描件按业主裁定改合成件，所以真实扫描件仍未测过 | `git grep -n PAGE_SOURCE_OCR -- app/rag/loader.py`、`git log --oneline --all --grep R298` |
| 4 | 「Chroma 作为当前过渡读路径」 | 生产向量库已定案 PGVector（业主 09-24 明令），读路径 10-03 已切走。Chroma 今天只剩一格：**仍在双写、停写退役未做**（R60／R633／R639-A 线在树 `2d2680b`，计划书 §16 明令账面写「停写未做」，欠的是生产库现取那一遍）。既不许写成最终架构，也不许写成已下线 | `docker exec enterprise-brain-backend-1 printenv VECTOR_DUAL_WRITE`、`python scripts/r633_dual_write_off_precondition.py` |
| 5 | 「V1 预计 2026-10-04 左右完成」 | **作废**。错法不是"估不准"，是**把一堆从没被量过的格折算成一个日期**。本版改成 §5 逐格表：每格只写「三态／量具／读数／解锁这一步／归谁」，不写单点完成日。 | `git log --oneline -1` |
| 6 | 「V2 完成判据＝PGVector 正式接入读路径」 | 该格已提前达成（见 #2）。V2 真欠的是：停写退役（R60）、客户尺寸校验（R44 真库 37,483 chunk 那一格、R47 同义词题） | `python scripts/audit_plan_ticket_ledger.py` |
| 7 | 「V1 性能门槛＝首字 10 s／完成 30 s（目标）」 | 问答类 p95 **50.1 s**（run22 与 run23 两窗互证，代次 `9556513`），停表帽命中 0 枚（帽值现读 300.0 s）；「首屏 ≤1 s」随阶段 B 移出 V1（本机地板 11.0 s 实测，只吐 1 枚 token 也要 11.0 s）。r2 那句「未经目标机器实测的秒数不能写成对外承诺」**至今仍然没满足**：这台机是 i9-13980HX＋RTX 4060 Laptop 8 GB，不是任何客户机 | `python scripts/r595_latency_readout.py --tag run22 run23` |

### 0.2 r2 里仍然有效、本版不改的要求

- 「有代码」「有测试」「计划里写过」都不等于功能已完成；
- 性能数字必须标 `[实测]`／`[算术]`／`[推算]`／`[目标]`；
- 未经目标机器实测的秒数不能对外承诺；
- 不得为了显示绿色使用 `skip`、`xfail`、假数据或静默降级；
- 每项完成都要有代码、测试或真实环境证据；
- 推进顺序：先功能覆盖 → 内部连续使用 → 生产质量 → 平台增强；
- V0–V5 的版本边界与 §3、§4 的功能要求清单（除 §0.1 点名的两行）。

### 0.3 r2 会持续产生假账的三个结构原因（不改机制，下一版还会漂）

1. **用百分比表达完成度**（「V1 70%～80%」）：没有分母、不可复核、每班可以自己上调，业主无从分辨。
2. **把测量口径当功能进度**：台账 16 枚 PARTIAL 里有 4 枚的欠账行本身写着「已裁定随 B 行／E 行移出 V1」，档位不改，这个数永远下不去——看着像"又拖一周"，其实是账没结算。
3. **现状句不带代次**：`INDEX_BACKEND` 那句 09-22 写真、10-03 变假，散文还留在文档里，下一班拿它当现状继续派工。

### 0.4 本文件的失效条件（动以下任一项必须同批改这里）

- `INDEX_BACKEND`／`VECTOR_DUAL_WRITE`／`REPORT_LANE_VIA_QUEUE` 任一生产现值变化；
- `scripts/audit_plan_ticket_ledger.py` 的档计数变化（在册数、LANDED／PARTIAL 数）；
- 五道门 A–E 任一格定性变化，或某格的量具改名、改口径；
- 后端镜像 label `org.opencontainers.image.revision` 与主树 HEAD 分家（现在就是分家状态，见 §10）。

本文件里所有数字都必须能被 §11 的命令重算。**拟立 R665（文档事实派生钉）**：把本文件点名的现状数字改成当场派生，取不到或不等就红，散文只留解释——这样"文档过期"从人力问题变成 CI 问题。

## 0.5 r3 里被本班（第十七班续席）推翻或改口的行（逐条对账）

| # | r3 原话 | 今天现取 | 现取凭据 |
|---|---|---|---|
| 1 | 「读法乙未清 **16 号**」＝V1 还差多少 | **11 号**。账尺加了第七档 `OUT`＝移出本版代码半径（🔴 **绝不等于判达**）：R29②／R43②／R48①／R50②／R52① 五格按业主 09-24「B 行与 E 行整行移出 V1 门槛」裁定结档，每格带仓内出处＋判语关键词＋不可达证据，缺一腿 C19／C20／C21／C22 当场红 | `python scripts/audit_plan_ticket_ledger.py`（并树 `12aa93c`） |
| 2 | 「镜像 label `org.opencontainers.image.revision`=`9556513`」 | 现读 **`unknown`**（`BUILD_INFO` 同为 unknown）——傍晚那次重建没带 `GIT_SHA`，`docker-compose.yml::migrate` 的注释写明「忘了带就记 unknown，不记一个看着可信的哈希」。正解＝shell 里先 `GIT_SHA=<40 位>` 再 `build migrate` | `docker inspect enterprise-brain:local --format "{{json .Config.Labels}}"` |
| 3 | 「`MODEL_CONTEXT_TOKENS=4096`（扣掉答案预算只剩 2560 token 给资料）」 | **过期**。容器现读 **8192**；那条 4096 是 `.env.example` 与旧账的话。🔴 但代码缺省 `app/rag/indexing.py::INDEX_BACKEND_DEFAULT` 仍是 `chroma` 那句仍然成立 | `docker exec enterprise-brain-backend-1 printenv MODEL_CONTEXT_TOKENS` |
| 4 | 「D 报告档可查回＝那层从没被测过」 | **半推翻**。`docs/perf/raw/r561-2026-10-01/summary.json` 现取＝10-01 23:38 真容器真 Redis 开关 on 的队列道跑过一遍、六格全 PASS rc=0（`final_kind=queued_polled`／`polls=76`／终态体 16 枚键含 `usage`/`sources`）⇒ **D① 单题有凭据**（代次 `fe166c8`）；但「报告档 100%」那半仍未验 | 结案纸 `docs/testing/v1-cell-closeout-2026-10-05.md` §3.1 |
| 5 | 「今晚已排 3 个 on 相样本可取 D」 | **废样本**。`scripts/eval_transport_ask_v2.py::DECLARE_LANE_TIER` 缺省空串 ⇒ 传输从不发 `lane` ⇒ 只翻容器开关不入队。带 1 已收三扇 on 相（run24s2／24s2b／24s2c）：12 枚报告题正文全在（长 99–2884 字）但 `answer_source` 逐枚是 `eval_transport_ask_v2:transport`、`queued_polled` 零枚，`r573-A2` 逐枚 **rc=2**（量不到）⇒ 量具缺陷，非产品缺陷，立 **R678** | `%TEMP%\evalrun\night1005d.log`＋各窗 `answers.jsonl` 逐枚键集 |
| 6 | 「在途执行层 `Hilbert`／`Lovelace`／`Arendt`」 | 过期名册。现取在飞＝`Erdos`/R662（A② 四枚单帧行，写域含 `chat.py`＋`nodes.py`）；`Bohr`/R666 与 `Zeno`/R672 已验收并树并 close 腾槽 | 看板 §0 名册行 |
| 7 | 「全量门 48 failed／11208 passed／…（基点 `9556513`）」 | 数字**仍然在册但代次更旧**：那之后 R664／R672／R666 已并树，门未重量。新规④口径＝全量门每班开工一次＋冻结前一次＋每并满 5 枚补一次，今夜带 2 静默期不跑 | `python scripts/run_gate.py` |

## 1. 反假账八条（施工与记账都受约束）

1. 每个结论只能取三态之一：`码在树`／`真机验过`／`量不到`。后两态不许互相换措辞，"量不到"不许写成"已完成"或"不影响"。
2. 完成度唯一口径＝`python scripts/audit_plan_ticket_ledger.py` 的档计数（"读法乙：判据全达才算清"）。百分比表达作废。
3. 合成标签、沙盒语料、影子库读数**不得**当成客户隔离或客户尺寸的证据；演示库打合成标签只证行为，不证隔离。
4. 性能数字六件套：机器、模型、冷/热启动、并发数、口径（avg/p50/p95）、读数代次 sha。缺任一件＝不可对外、不可入验收结论。
5. 执行层自报只作对照不作数；并树必须交三态数（基点跑／state① apply 未 commit／state② 干净树复跑同名件，文件清单逐枚相同）。
6. 禁 `skip`／`xfail`／放宽断言／静默降级翻绿；反证牙只许增不许摘，摘牙＝退回。
   🔴 **「摘牙」的定义（业主 2026-10-05 裁定 G1 甲，见跟进单 §160.5）**：让一枚断言**不再可失败**才算摘牙——`skip`／`xfail`／删文件／放宽断言／静默降级都算。把断言目标从**散文**换成**同一事实的机器源**（生成器 diff／派生索引／schema）**不算摘牙**，但必须同时满足三件事：① 新针先落且当场证得过红；② 旧针文件不删、单号不复用；③ 每枚换靶留一行「原断言 ↔ 新断言」对账（由量具机器生成，不许手写）。换靶后已无从核对的旧针改判 `retired-but-present`：仍在套件里跑、断言「该散文段已由 X 派生、且两者逐字节相等」。
7. 「未做」与「码在树」两头必须同时说：写未完成要点名欠的那一格，写已完成要给现取命令。
8. 常驻牙不许把「此刻盘面脏不脏」「盘上字节是否等于 HEAD blob」当判据（事故 #96／#107／#113 同族病）。

## 2. 现在的账（全部现取，代次 `dd16297`；R686 结算两格后由 11→9）

| 项 | 现取读数 | 命令 |
|---|---|---|
| 在册单号 | 43 号＝LANDED 24／PARTIAL 11／**OUT 5**／CLOSED 1／FOREIGN 1／NOTBUILT 1／ZERO 0 | `python scripts/audit_plan_ticket_ledger.py` |
| 「产物在树即算清」未清 | **0 号** | 同上（读法甲） |
| 「判据全达才算清」未清 | **9 号**：R25 R26 R28 R31 R35 R38 R44 R47 R51 | 同上（读法乙） |
| 移出的 5 格（🔴 不算完成） | R29② R43② R48① R50② R52①，逐格带仓内出处＋判语关键词＋不可达证据 | 同上（`OUT` 那一段） |
| 全量门（最近一次总控亲跑） | 48 failed／11208 passed／58 skipped／2 xfailed／1592.0 s／exit=1，**基点 `9556513`**；此后 R664／R672／R666 已并树，门未重量（新规④：每班开工一次＋冻结前一次＋每并满 5 枚补一次） | `python scripts/run_gate.py` |
| 体量 | `app` py 120、`tests` py 697（其中 **564 枚叫 `test_r*.py`**＝按单号生成的针）、`scripts` py 108、`docs` md 205、docs 共 9,180,484 B | `Get-ChildItem app -Recurse -Filter *.py` 等逐目录计数 |
| 台账搬运成本 | 跟进单 1,335,486 B／7,577 行；看板 7,050 行——**每班整本重读**，这是病根，处置见 `docs/engineering/multi-agent-project-rules-2026-10-05.md` | `Get-Item docs/handoff/2026-09-15-backend-followup-requests.md` |
| 向量库 | 全库 **1008** 枚向量在位；双写 **on**；读路径 **pgvector**（容器现值）；**停写未做**（R60）；双写召回腿 135 题里 **67 题 top-5 不一致**、Chroma 侧 **24 题空召回**、`drift` 零差集＝今夜 r58-recall 复核仍成立 | `docker exec enterprise-brain-backend-1 printenv INDEX_BACKEND`、`docker exec enterprise-brain-postgres-1 psql -U postgres -d enterprise_brain -c "select count(*) from chunk_vectors"` |
| 生产开关现值 | `INDEX_BACKEND=pgvector`／`VECTOR_DUAL_WRITE=on`／`REPORT_LANE_VIA_QUEUE=off`／🔴 `OLLAMA_REQUIRE_GPU` **未设**（`printenv` rc=1＝fail-open）／`MODEL_CONTEXT_TOKENS=8192`／`MODEL_MAX_CONCURRENCY=1` | `docker exec enterprise-brain-backend-1 printenv <键名>`（键名查，别记行号） |
| 镜像代次 | label `org.opencontainers.image.revision`=**`9efff02585a2feb659784991feace7d83445bc54`**（18:57 带 `GIT_SHA` build、19:0x `--force-recreate backend worker scheduler`、`scripts/check_image_provenance.py` 交 **PASS／DOCS-ONLY**）⇒ 今夜带 2 量的就是含 R662 的这一代 |
| 评测集 | **105** 题，题源 `tests/fixtures/business_evaluation_100.jsonl` 一字节未动且被 `tests/test_evaluation_report.py` 钉着；改题收尾＝19 枚全丙、零改题 | `python scripts/check_eval_evidence_coverage.py`、`python scripts/r598_shard_sync.py --check` |
| 今夜真机窗（带 1，不判延迟） | run24s1／24s2／24s1b／24s2b／24s1c／24s2c 六扇收窗 rc=0；三扇 on 相的 `r573-A2` 逐枚 **rc=2**（D 门取不到数，根因＝量具 R678）；r58-recall rc=1＝量具设计内的「不能翻」读数；R575 备份—恢复演练 rc=0（62.3 s） | `%TEMP%\evalrun\night1005d.log`、`night1005d.ledger.jsonl` |
| 在途执行层 | `Erdos`／R662（A② 四枚单帧行，写域含 `chat.py`＋`nodes.py`）；`Bohr`／R666 与 `Zeno`／R672 已验收并树、已 close 腾槽 | 看板 §0 名册行 |
| 待派池（按写集排） | R679（工单落文件＋派生索引）· R680（账尺以 `docs/tickets/**` 为状态唯一真源＋r631 判据按键名查）· R681（契约生成化）· R682（KPI 量具）· R683（棘轮双向＋预算）· R684（写域所有权表）· R686（把 R27③／R37③ 的「达」落进账尺）；V1 侧 R677（R44①）· R670（R38③，须等 `Erdos` 收席）· R674（R51②）· R676（R47①）· R678（D 门量具）· R669（R25②，动容器⇒窗后）· R673（R26② 开关语义） | `docs/tickets/`＋看板 §0 |
## 3. 版本边界与功能要求（保留 r2 的要求，只改被盘面推翻的两行）

### V0 技术原型版（已过）
链路证明用：FastAPI＋Vue 起得来、本地账号登录、文档上传与基础解析、检索问答、Excel/CSV 基础读取、基础图表、PDF/Excel 导出、Multi-Agent 基础调度、SSE 或等价的"处理中"状态。允许内存/JSON 回退、固定演示数据、单用户、权限不完整。
主线：登录 → 上传文档 → 提问 → 回答；上传 Excel → 分析 → 图表 → 导出。

### V1 核心功能演示版（当前目标）

定位：把核心业务功能做成**可连续演示**的版本。性能、生产安全、长时间运行不阻塞本版本。

主线：登录 → 工作台 → 上传制度文档 → 文档问答并看到来源 → 上传 Excel/CSV → 指标统计与数据问答 → 生成图表 → 导出报告 → 看到一条异常或告警结果（或明确的暂无结果）。

功能要求（逐条要可复现，不接受"有代码"）：

- 登录与工作台：登录页可用；演示账号或本地账号可用；工作台有明确的文档／数据／问答入口；无死链、空白页、技术异常串；无数据显示空态，**不许用假数字填真实业务区**。
- 文档知识库：支持 PDF 普通文本、DOCX 普通文本、TXT、Markdown；上传状态、文档列表、搜索、预览、下载、删除；基于文档提问；回答能看到文件名或来源；上传失败／解析失败／索引失败有稳定错误态。
- 数据分析：Excel/CSV 上传、列表、预览；字段／行数／列数／缺失值／基础统计；合计、均值、排名、分组、趋势；自然语言出结论；**只分析用户明确选择或系统明确绑定的数据文件**。
- 图表与报告：至少柱状／折线／饼图；能在对话或结果区显示；图表可下载；可生成 PDF 或 Excel 报告；报告至少含标题、数据来源、结论、图表、生成时间。
- Multi-Agent：至少体现问题分类、文档 Agent、数据 Agent、图表 Agent、结果汇总；页面显示当前步骤／处理中／成功／失败／等待确认；长任务不无限等待；用户可取消或离开当前流，回来不拿到另一轮的错误结果。
- 异常与告警：至少有简单规则；支持手动执行检查；能展示异常结果或明确暂无结果；**不用固定异常数字冒充真实检测**。

允许的技术边界（本版按现取改口）：

- 单机、单企业、单租户；本地 Ollama；本地文件存储；PostgreSQL/Redis 只在已有链路需要时使用；基础角色权限；基础日志与部分 Trace；复杂任务可入队列；可用演示数据但**必须标明是演示数据**。
- 🔴 向量库：**生产向量库＝PostgreSQL＋PGVector（业主 09-24 定案），读路径已于 10-03 切走**；Chroma＝**仍在双写、停写与退役未做**的遗留件。新代码不得新增 Chroma 依赖或新 Chroma 写点。
- 🔴 OCR：r2 那句"没有 OCR 链路"已作废——扫描页检测＋本地 OCR 通道＋页源三档＋上传回执上屏都在树（属 V2 提前落地）；但**客户真实扫描件质量未验**（按业主裁定用合成件代测）。

V1 明确不做（不变）：PDF 表格识别、复杂 Word 表格结构化、Excel/CSV 进知识库索引、完整知识图谱工作区、审批工单与审批流、多租户 SaaS、高可用集群、完整灾备、完整 RAG 调试台、完整评测平台、生产级安全认证、任何未经实测的"所有问题几秒返回"承诺。
（r2 里"PGVector 全量切读"这一条已从"不做"改成"已做读路径、未做停写退役"，见 §0.1 #2/#6。）

### V2 功能完整开发版
新增：`Document/DocumentVersion`、`Dataset/DatasetVersion`、`Artifact`/`CalculationRun`；所有资源有稳定 ID、owner、生命周期；staff/manager/admin/auditor 权限统一；文档、数据、报告、告警资源级隔离；PostgreSQL 成为主要业务存储；Redis 队列的重试、死信、幂等、失败原因完整；会话／产物／数据／文档重启后可恢复；Dashboard 用真实期间与真实数据；告警至少部分闭环（确认／转派／关闭）；管理员可看一次运行的关键 Trace。
新增能力：OCR 与扫描 PDF、PDF/Word 表格解析、Excel/CSV 知识库模式、Dashboard 真实数据、知识图谱／审批助手／通知基础能力、PGVector 正式读路径与 Chroma→PGVector 迁移验证。
验收目标：10～30 名内部用户；跨部门跨密级越权命中 0；重启不丢核心业务数据；失败任务可定位可重试；页面主要数据不依赖固定演示值。

### V3 内部试用版
一个部门或小范围员工连续使用；资源级权限与跨部门隔离；会话／文档／数据集／产物重启可恢复；队列重试／死信／幂等／失败原因完整；真实数据 Dashboard、告警处理、Trace 查询闭环。暂不要求完整生产安全与 72 h 验证。

### V4 生产交付版
安全初始化密钥与管理员；上传大小／真实 MIME／魔数／解压资源限制；Prompt Injection 隔离；全部 API 与产物统一授权；PostgreSQL＋PGVector 生产读写；Chroma 迁移、校验、回滚；备份恢复、新机器部署、容器重建验收；日志脱敏、监控、健康探针、调度器单实例；并发／超时／队列／资源限制；安全测试、恢复演练、72 h 运行验证。

### V5 平台增强版
统一来源定位与解析质量状态、指标语义层、完整知识图谱、审批助手、通知中心、配置发布与回滚、RAG 调试台、批量评测、Agent Trace 回放、企业微信／钉钉／内部系统集成。

## 4. V1 到底还差多少（读法乙 9 格，逐格三态，别再混成一团）

唯一分母＝账尺读法乙的 11 号。每格只许四种写法之一：**达／没达／量不到／没验**，并且必须带量具名与读数代次。

| 号 | 欠的那一格（尺子点名） | 三态 | 现取凭据（量具＋代次） | 解锁这一步 | 归谁 | 墙钟 |
|---|---|---|---|---|---|---|
| R25 | 两句判据都是容器内事实，从未在真机读过 | **没验** | 🔴 推翻上一班「真没做」：`docker-compose.dev.yml` 早在在册（文件头自陈 R25，`./app:/app/app` 热挂进 backend／worker／scheduler，backend 带 `--reload-dir`，并写明为何不用 `docker-compose.override.yml`）；`docker inspect` 现取在跑容器只 5 枚命名卷、零 bind mount | 带 overlay 实跑一取证（动容器⇒窗后）＝**R669** | 我 | 20–40 分 |
| R26 | ② 丢卡必须显式报错 | **没达** | `app/common/model_capabilities.py::require_gpu_enabled` 未设即 fail-open；容器 `printenv OLLAMA_REQUIRE_GPU` **rc=1** | 翻 `OLLAMA_REQUIRE_GPU=1`＋recreate＝**改生产行为**（待业主），语义钉＝**R673** | 业主＋我 | 30–60 分 |
| R27 | ③ 端到端 −≥35 s | **达**（已落账尺 `e99681e`，读法乙 11→9） | 160.552 s 基线 → 问答类 p95 **50.1 s**（`scripts/r595_latency_readout.py`，run22／run23 两窗互证，代次 `9556513`）＝−110.4 s | 把这一格的达落进账尺＝**R686** | 子 agent | 15 分 |
| R28 | ③ 30 题评测不退化 | **量不到** | `scripts/r634_category_delta.py`：run22→run23 五项指纹全等＝同码复跑，要的**跨代次对子 0 枚**（rc=4） | 今夜带 2 四扇同码窗＋12 枚对子 | 我＋窗 | 一夜一窗 |
| R31 | ② 逐片时间戳不重叠、逐字无缺字 | **没达**（R662 的码已于 19:0x 并树 `9efff02`，两态各 697 passed／0 failed／15 skipped＝140.23 s／138.63 s；🔴 这一格仍是没达——分片复演不等于真窗，翻绿要带 2 读数） | 在册七枚合取 102/105；红四枚有名有姓＝`chart-01`／`tool-04`（各只发 1 帧）、`data-12`（2858 字一帧）、`chart-04`（missing 1258／extra 36，只在 33 题子集窗炸＝形状相关）；帧账 `run22-sidecar-frames.jsonl` 可离线复演 | **R662 在飞**（`Erdos`） | 子 agent | 0.5–1 人日 |
| R35 | ② 跨部门／跨密级 0 条命中（P0） | **量不到** | 生产库 `department`／`classification` 全空；沙盒 252 枚合成标签只证行为、**不证客户隔离**（业主 A3 已裁「交付阶段按客户真实密级做」） | 判据已改写成四件可失败判据并记「未验」；不许拿合成标签翻绿 | 客户交付阶段 | — |
| R37 | ③ 队列失败有终态与原因码 | **达**（已落账尺 `e99681e`，读法乙 11→9） | 🔴 推翻上一班「R227 后一次没重量」：R585 已并树 `1f0f0f2`；八处 `fail_or_retry` 逐枚点开＝七枚稳定码＋一枚 `str(e)`（`deploy/queue_worker.py::_process_reserved` 收尾，例外另立 **R675**）；在册牙亲跑 99 passed／0 failed／37.39 s | 落进账尺＝**R686** | 子 agent | 15 分 |
| R38 | ③ 抽查一问 `input_tokens/output_tokens` 非零且与 Ollama 自报一致 | **没达** | `/ask` 有行非零（3955／245／467，cached 467／369／493）；🔴 `/chat` 打完模型**不落 `model_calls` 行**，`metadata` 只 `{"worker":"doc"}`、没存原始 usage | **R670**（写域含 `chat.py`⇒必须等 `Erdos` 收席） | 子 agent | 0.5 人日 |
| R44 | ① 覆盖 95% 查询的热集常驻 | **没达** | `app/rag/hot_index.py` 在树；账上点名的**让路驱动件不在盘上**（与在册 R663／R654 同源） | **R677** 重写＋一台安静机器重量 | 子 agent＋窗 | 1 人日＋窗 |
| R47 | ① 同义词题命中改进 | **量不到（零分母）** | 码在树（`retrieval_pipeline.py::expand_query_synonyms`）；105 题类别分布现取**零枚同义词题** ⇒ 分子永远为空 | 业主裁甲（加 12 枚题，评测集被钉钉过）或乙（改 top-5 变化率口径）＝**R676**；本班默认乙 | 待裁＋子 agent | 0.5 人日 |
| R51 | ② 端到端与分段加总误差 <1% | **没达** | 本班亲跑 `scripts/r631_stage_sum_delta.py --window run22 run23` 各 **rc=3＝量不到**；喂 32 MB 隔离事件件取到 trace 2447／跨度 7405，但 classify／rewrite／retrieve／generate／reflect **五段全缺**、可比 0 枚（`scripts/r636_stage_coverage.py` 同 RC=3） | **R674**（窗按题导出 `runXX-traces.jsonl`）；顺带 **R680** 把 r631 的手抄 LF 位改成按键名查 | 子 agent | 1 人日 |

**读成三句话**：

- 今天**已经量到达、只差把账落进尺子**的有 2 格（R27③／R37③）——落完读法乙从 11 变 9，这一格归 **R686**；
- 真欠代码或欠一次重量的 5 格：R26②／R31②／R38③／R44①／R51②；
- 剩下 4 格**不是代码问题**：R25② 欠一次带 overlay 的真机取证、R28③ 欠跨代次对子（今夜窗）、R35② 属客户交付阶段、R47① 是零分母要先裁口径。

**移出的 5 格（`OUT`，🔴 不算完成）**：R29② 真机判负一分没省／R43② 要换推理引擎／R48① 本机地板 11.0 s 物理不可达／R50② 丙案裁定句已落／R52① 断网可装可跑属交付阶段。出处逐格现取（业主 09-24「B 行与 E 行整行移出 V1 门槛」原文在计划书，R50 在 `docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md`），锚点不唯一／文书没进主干／证据只剩形容词，账尺当场红。

另加不在 11 号里、但 V1 完工判据要求的三格：前端**九环浏览器走查**、embedding 缺失／无 GPU **两张失败脸**、`claims` 落进答案件后 C／D 才从「零分母」变成「有牙的测试」。
## 5. 五道门逐格现状（三态＋量具＋代次）

| 门·格 | 三态 | 量具 | 现取读数 | 代次 | 解锁这一步 |
|---|---|---|---|---|---|
| A① 端到端时延 | **达**（口径＝只认问答类 n=64 ≤90 s，整表只公布不判；口径未定死之前阶段 A 不许整体翻绿） | `scripts/r595_latency_readout.py` | 问答类 p95 50.1／50.1 s（两窗互证）、停表帽命中 0；公布读数分析·报告类 85.5／85.6 s、整表 67.6／63.8 s | `9556513` | 带 2 四扇同码窗复算 |
| A② 流式逐字无缺字 | **没达** | `scripts/r573_caliber_reconciliation.py` | 在册七枚合取 102/105、②原文两格 104/105；红四枚点名见 §4 R31 行 | `9556513` | R662 **已并树 `9efff02`**（生产者可成形答复补逐片＋收端挂起说明屏放行逐片帧，两态各 697／0／15）⇒ 解锁只剩带 2 真窗复跑，影子复演不算翻绿 |
| A③ 有卡可见／丢卡必报错 | **没达**（旧写法「半格」不精确） | `docker exec … printenv`＋`app/common/model_capabilities.py::require_gpu_enabled` | ollama 容器 `nvidia-smi` 交 RTX 4060 Laptop 8188 MiB ✅；`OLLAMA_REQUIRE_GPU` 现取**未设**（rc=1）＝fail-open，正是判据③要禁止的形状 | 10-05 现取 | 设 true＋recreate＋跑一次「卡不可见必报错」＝R673（改生产行为，待业主） |
| A④ 逐类不退化 | **量不到**（不是「达」） | `scripts/r634_category_delta.py` | 跨代次对子 **0 枚**（rc=4）；run22→run23 指纹全等＝同码复跑；历史教训＝run4 抓到过一次真退化（文档问答 0.6842→0.6316，`doc-19` 一枚），run5 收回 ⇒ 这句只能算「有条件成立」 | `9556513` | 今夜带 2 四扇＋12 枚对子 |
| B 上卡定档 | **移出 V1**（账尺已进 `OUT` 档，不再挂欠账） | — | 本机地板 11.0 s；「首屏 ≤1 s」前提＝换档位／引擎，与 V1「只管理本机 Ollama」冲突 | 计划书 09-24 裁定 | 给客户报档位时属交付实施 |
| C① 越权 0 条 | **未验** | R481 口径＋R193 矩阵＋R469 沙盒臂 | R193 51 格真红 0 格（沙盒／合成侧）；生产库标签全空；R487 只到账号面（30 枚演示号 role×department 16/16，检索面在演示库仍是空集）🔴 不许拿合成标签或 R487 翻绿 | 10-03 | 客户真实密级回填（交付阶段） |
| C② 缓存命中显式标注 | **达** | 见看板 §4EN | 命中来源在答案面显式可指认 | 10-03 | 无 |
| C③ 评测分数不退化 | **待重量** | `scripts/run_quality_evaluation.py` | run17 成立；R598 改题收尾＝19 枚全丙、零改题、题源一字未动 ⇒ 需在当前集重跑一扇 | 今夜窗 | run25–run28 |
| C④ 无依据断言率 | **量不到（零分母）** | 质量件 `claims` 键 | `unsupported_claim_rate=0.0`，但三窗 315 行里带 `claims` 键 **0 行**＝没有分母的 0，不是「没有幻觉」 | `9556513` | 欠一枚「把 claims 落进答案件」的量具升级单 |
| D 报告档可查回 | **未验**（订正：单题有凭据，整档没有） | `scripts/r561_queue_lane_piece_readout.py`＋`scripts/r573_caliber_reconciliation.py` | ✅ 10-01 真容器队列道六格全 PASS rc=0（`final_kind=queued_polled`／`polls=76`／终态体含 `usage`/`sources`）＝D① 单题代次 `fe166c8`；🔴 今夜三扇 on 相（run24s2／2b／2c）`queued_polled` **零枚**、`answer_source` 逐枚 `eval_transport_ask_v2:transport`＝**废样本**（根因＝`DECLARE_LANE_TIER` 缺省空串）；D②/D③ 键名在册、值没留 | 12aa93c | **R678** 修量具后重开一扇 on 相窗（跑完必须还原 off） |
| E 企业形态 | **移出 V1**（账尺已进 `OUT` 档） | 环境矩阵 E1–E6 | 72 h 长跑／备份恢复／改时钟验 JWT 属上线实施清单；唯一产品级判据「双身份越权 0 条」由 C① 承担 | 计划书裁定 | 交付阶段；R575 备份演练今夜 rc=0（62.3 s） |
| V 前端 | **未验** | Playwright＋人工走查 | 登录页地球图、字体本地化、工作台背景四层已并树；九环走查与两张失败脸（embedding 缺失／无 GPU）没做 | 待做 | 子 agent 开窗＋截图 |
## 6. 多 Agent 并发施工（这台机上的真实机制，不是愿望）

r2 那张 A–F 并发组表已废（它按功能名称分组，而并行只能按写集切）。现行规则：

- **并行度 3–4 枚**。🔴 10-05 实测：报 `agent thread limit reached` 的真实原因不是 provider 天花板，而是**已结案但没 close 的尸体席位在占名额**——关掉 2 席后连投 2 枚全部成功。⇒ 每班开工第一动作＝关死席与结案席。
- **一个子 agent 独占一棵工作树**；两枚同树＝真写域冲突。写集重叠（同入口、同契约、同测试文件）一律串行。
- **一个 block 内只允许一次投递调用**，`spawn_agent` 与 `send_input` 二选一。投递报错＝未落地：先取证（`dirty=0`／`untracked=0`／`rev-list --count <基点>..HEAD`=0／sessions 目录无新线程）确认真的零线程产生，再投，按"首次成功投递"记账，**不是补投**；不取证就重投＝事故族（#14／#15 同型）。
- 🔴 **对已存在的执行层席位发长消息是致命通道**（#112／#113：一枚收订正令、一枚收返工令，都死在投递本身、零写入）⇒ 派工词**一次投全**；之后要改前提或改判据，一律落账面由**新单承接**。
- **执行层禁 commit**，总控代提交；主树提交显式列路径，禁 `git add -A`；中文提交词写 UTF-8 无 BOM 文件再 `git commit -F`。
- **验收独由总控担**：逐条对 §21 判据＋亲自复跑测试，并树交三态数（基点／state①／state②，文件清单逐枚相同）；执行层自报只写"执行层自报"。10-05 亲跑抓出一枚自报假话（R657 那句"并树即回绿"只兑现一半）。
- **全量门**用 `python scripts/run_gate.py`，并发数由脚本按空闲内存自选，**不许把 `-n` 写进 `pyproject.toml` 的 `addopts`**（六枚测试件会嵌套起 pytest，全局并行会递归扇出；`loadfile` 不是风格问题）。反证钉不分层出门。
- **编号卫生**：写「事故 #N」或新单号前先 `rg` 取 max（10-05 18:2x 现取：事故 max #122、单号 max 至 R686）；引用任何数字前先查有没有被后续实测推翻；判断一个默认值是否可达必须查调用点，不能只看签名。
- **长独占窗口期间总控不许空转等待**：窗内只做零 CPU 争用且不改测量条件的活（取证、写判据、排波次、预配工作树）；窗内硬禁并树、跑测试、动容器、打模型。等待用阻塞式监视，不用轮询，**不设心跳/automation**（心跳注入的 `at_` 条目会永久毁线程）。
- 🔴 **命令通道转义坑**：往文件写含反引号的正文一律走单引号 here-string 或编辑器通道；写完现读＋扫 `0x00/07/08/0b/0c` 枚数＝0＋数反引号成对。本文 §0.1 #4 那 4 枚历史控制符就是这么来的（已复原）。
- **夜间无网边界**：跑分窗打的是本机 Ollama（`OLLAMA_BASE_URL=http://ollama:11434`，无远程键）⇒ **窗不吃网**；总控与子 agent 推理、`docker build`、`git push` 全吃网 ⇒ 夜里**只测不建**，镜像必须傍晚有网时重建。

## 7. 性能事实（每条都带六件套）

| 事实 | 标记 | 条件 |
|---|---|---|
| 复杂文档问答曾达 160.6 s | `[实测]` | 本机、Ollama、优化前基线、单人、非缓存、完整结束、单样本（见 `docs/perf/latency-budget-2026-09-16.md`） |
| 一次问答里模型往返约占总时长 99.5%；检索本体约 0.24 s | `[实测]` | 同上 ⇒ **换向量库不是提速手段**，这条纪律保留 |
| 只吐 1 枚 token 也要 11.0 s（prefill 地板） | `[实测]` | 本机、纯 CPU/8 GB 卡、520 字输入（`docs/perf/raw/rate_prefill.jsonl`）⇒ 首屏 ≤1 s 在 V1 硬件上不可达 |
| 问答类端到端 p95 50.1 s | `[实测]` | 本机 i9-13980HX＋RTX 4060 Laptop 8 GB、Ollama、单人串行、n=64、完整结束、代次 `9556513`、两窗互证 |
| 分析·报告类 p95 85.5／85.6 s；整表 67.6／63.8 s | `[实测]` | 同上，n=35／n=105；**整表只公布不判** |
| 全量门稳态 218 s（首跑 437 s） | `[实测]` | 同树同 HEAD 复跑；"首跑税"归因（冷缓存＋杀软扫 temp）**待证** |
| `MODEL_MAX_CONCURRENCY=1` ⇒ 第 2 人之后拿离线兜底 | `[实测]` | 门外等待上限 60 s；单请求 160 s 时 2/3/5 人全超时；**R27＋R28 把 160 s 压到 75 s 仍然 >60 s**，唯一让 5 人都排到的解是单请求 13.3 s |
| `MODEL_CONTEXT_TOKENS=4096`（扣掉答案预算只剩 2560 token 给资料） | `[实测]` | 报告类场景已撞过一次 4402 token ⇒ 撞顶是**发请求前就拒**，客户看到的是"处理不了"，不是慢。窗口与显存**必须配套改** |
| 客户硬件上的任何秒数 | **无一条** | r2 那句"未经目标机器实测不得对外承诺"到今天仍然一个字都不能对外 |

## 8. V2 现状（按 r2 的 V2 要求逐格，别把 V1 的门当成 V2）

| V2 要求 | 三态 | 现取凭据 |
|---|---|---|
| PGVector 正式接入读路径 | **码在树＋生产已切** | `printenv INDEX_BACKEND`=pgvector（10-03）；欠停写退役＋客户尺寸校验 |
| OCR 与扫描 PDF | **码在树** | `app/rag/ocr.py`＋`loader.py` 三档页源（`e441d10`）；真扫描件质量未验 |
| PDF/Word 表格解析 | 半 | `app/rag/tables.py` 模块＋契约在树，**端到端待接线**（R300 `72a9bdc`） |
| `Artifact`／`CalculationRun` | 半 | `app/api/v1/artifacts.py` 4 枚路由＋9 枚专名测试件；`CalculationRun` 侧未逐格验收 |
| 权限统一／资源级隔离 | 半 | `auth.py` 11 枚路由、`restricted.py`、R193 矩阵 51 格真红 0；生产标签那一格按 §5 C① 记"未验" |
| 知识图谱 | 有入口 | `app/knowledge_graph/service.py`＋`intelligence.py` 8 枚路由＋2 枚专名测试件；定位纸在 `docs/design/knowledge-graph-positioning.md` |
| 审批助手／通知 | 有入口 | HITL 批准链在 `chat.py`；`notifications.py` 6 枚路由＋5 枚专名测试件 |
| Dashboard 真实数据 | 有入口 | `dashboard.py` 2 枚路由＋4 枚专名测试件；"不依赖固定演示值"未逐格验 |
| Excel/CSV 知识库模式 | 未做 | `app/documents/file_security.py` 顶部注释点名 `POST /upload-excel` 的边界仍未并进知识库索引 |
| 队列重试／死信／幂等／失败原因完整 | 半 | `deploy/queue_worker.py`＋R37 ③ 未重量（见 §4） |
| 重启不丢核心数据 | 半 | R575 备份—恢复演练 10-05 首次真跑到底；🔴 R587 抓到库级 GUC 不在 pg_dump 里（E 门备份假绿） |

## 9. V1 完工判据（可复核清单，不是形容词）

V1 只有在下面每一条都能被现取命令复算时才叫完成：

1. 主线九步在**冻结镜像**上连续跑通（登录 → … → 告警），失败可解释；
2. §5 里 A②／A④／C③／D 四格从"没达／量不到"变成有代次的"达"，且 C④ 的零分母先治好；
3. §4 表里 9 格全部落定：达 2 格已落进账尺（R686 并树 `e99681e`）、没达 5 格逐个治（R677／R670／R674／R662／R673）、量不到 4 格先解口径或对子（R676／带 2 窗／带 overlay 取证）；OUT 5 格与 R35 不再计入 V1 欠账；
4. 全量门在同一 HEAD 上 exit=0，且红集合为空（不是"红都能归因"）；
5. 前端九环走查有截图与断网自证（Network 外部域名请求 0 条）；
6. 账面不出现被 §0.1 那类推翻的旧话——即 §0.4 失效条件当轮已同步；
7. 明确不许冒充已完成：客户真实密级隔离、客户尺寸检索质量、断网可装可跑、72 h 长跑、生产级安全认证、任何客户机秒数。

## 10. 现在真正堵在业主手里的（就三条，别的我自己推）

1. **`OLLAMA_REQUIRE_GPU` 翻不翻**：这是**改生产行为**（翻上去之后，客户机一旦丢卡就从「静默走 CPU」变成「显式报错」）。不翻则 R26②／A③ 永远记「没达」，我不会拿 fail-open 的现值翻绿。
2. **R47① 走甲还是乙**：甲＝往评测集加 12 枚同义词题（那本集子被 `tests/test_evaluation_report.py` 钉着，要动它得单独批一次）；乙＝把判据改成「同义词扩展使 top-5 变化率 ≥X」这种零分母也能量的形状。本班默认走乙并另立 R676，你不同意再改。
3. **`git push gitee HEAD`**：今天已 31 枚提交未推，本机是唯一副本（H6 那条一直没结，崩一次全丢）。

其余陈年杂务已授权我办、我照「删前先沙盒模拟」执行：影子树与残件删除清单、`.gitignore`、`chroma_db` 反跟踪、`automation-2` 仍 `PAUSED` 且指向死线程。
## 11. 现取命令（复制即用，本文所有数字都由这些命令产出）

```
git -C . rev-parse --short HEAD
python scripts/audit_plan_ticket_ledger.py
python scripts/r595_latency_readout.py --tag run22 run23
python scripts/r573_caliber_reconciliation.py --tag run22 run23 --no-rows
python scripts/r634_category_delta.py --dir %TEMP%\evalrun run22 run23
python scripts/check_eval_evidence_coverage.py
python scripts/r598_shard_sync.py --check
docker exec enterprise-brain-backend-1 printenv INDEX_BACKEND
docker exec enterprise-brain-backend-1 printenv VECTOR_DUAL_WRITE
docker exec enterprise-brain-backend-1 printenv OLLAMA_REQUIRE_GPU
docker exec enterprise-brain-ollama-1 nvidia-smi --query-gpu=name,memory.total --format=csv
docker exec enterprise-brain-ollama-1 sh -c "ollama ps"
docker inspect enterprise-brain:local --format "{{json .Config.Labels}}"
python scripts/verify_container_stack.py --skip-build
python scripts/run_gate.py
```

窗口成本（用来判断"要跑多久"，不是承诺）：一扇 105 题全表窗在本机 CPU 档约 3–5 小时；33 题子集窗约 1–1.5 小时；报告档 12 题另需一张 `REPORT_LANE_VIA_QUEUE=on` 的相 2 窗（约 25 分钟，跑完必须还原 off）。四扇同码窗＋12 枚对子是 A④ 与 C③ 的最小集，一夜排得下，但**一夜只能排一次**，因为它独占 GPU/模型，窗内禁止并树与跑测试。
