# 当前功能文档修订记录

## 1. 修订信息

- 项目：企业智脑
- 主文档：[current-functionality-2026-09-10.md](./current-functionality-2026-09-10.md)
- 修订版本：2026-09-10-r3
- 修订日期：2026-09-10
- 修订性质：基于生产级静态审计的文档口径修正
- 本轮修改代码：否
- 本轮修改 `frontend/`：否
- 本轮运行测试：否
- 本轮启动服务：否

## 2. 修订目的

上一版功能文档已经包含权限、文件处理、RAG、评测、Agent 可观测性、后台管理、Ollama、PGVector 和查询速度等主要方向，但仍有一部分审计结论没有写入，或者只写成了后续目标，没有明确当前源码的真实状态。

本次修订的目标是：

1. 让当前功能文档以源码事实为第一依据；
2. 明确区分“源码已有基础”“实现不完整”“设计目标”和“静态无法确认”；
3. 把生产级风险写入对应功能章节，而不是只放在计划文档里；
4. 避免后续继续把演示数据、固定值或测试记录当成真实业务闭环；
5. 为后端 Agent、前端 Agent 和后续实现提供统一的资源、权限、状态和验收口径。

## 3. 本次修改的主要内容

### 3.1 权限和资源隔离

补充并明确：

- 会话缺少 `owner_id`，不能认为已经完成会话隔离；
- 文档、数据文件、图表、报告、Trace 和 Agent 工具都需要资源级授权；
- Agent 缺少身份时当前代码存在默认 `admin` 路径，该行为必须改为拒绝或显式最小权限系统主体；
- 文件名、URL、`session_id` 和 `data_filename` 不能单独作为授权依据；
- `auditor` 角色在权限定义和用户创建入口之间存在不一致；
- 前端隐藏按钮不构成后端安全边界。

### 3.2 文件上传和文件处理

补充并明确：

- 上传接口存在一次性读取整个文件的风险；
- 当前没有统一的大小、数量、真实 MIME、魔数、压缩展开规模、页数、行数和解析时长限制；
- 文档和数据文件没有统一的所有者、Dataset/Document ID 和生命周期；
- 文件系统、解析、索引和目录登记没有原子发布；
- 文档版本记录不等于历史版本可检索；
- 删除没有统一清理原文件、向量、缓存、Artifact、Trace 和评测引用。

### 3.3 RAG、Agent 和 Prompt Injection

补充并明确：

- 检索片段和表格内容必须被视为不可信数据，不能直接作为指令；
- 当前没有完整的 Prompt Injection 防护和 Tool Gateway 授权边界；
- 语义、BM25、RRF 和重排分数没有独立稳定保存；
- 当前 Chroma 是主要向量检索实现，PGVector 仍是目标架构；
- 当前取消请求不保证停止后台副作用；
- 查询缓存需要绑定权限、知识库版本、数据集版本、Prompt、模型和查询模式；
- 本地 14B 模型的线程数、调用次数、总超时和资源预算还没有统一闭环；
- AgentResult、Evidence、Tool Call、Model Call 和 Retrieval Trace 尚未完整持久化。

### 3.4 数据分析和业务可信度

补充并明确：

- 数据文件当前仍主要按文件名定位，不是完整的数据资产；
- Dashboard、洞察和审批不能使用固定 rows、固定金额、固定标准、固定部门或固定阈值冒充真实业务；
- `safe_query()` 使用 `eval()`，字符串黑名单不能作为生产级沙箱；
- 金额、时间期间、单位、指标公式和数据截止时间需要统一口径；
- 图表和报告必须绑定 DatasetVersion、CalculationRun、MetricDefinition 和来源记录。

### 3.5 队列、数据库、部署和恢复

补充并明确：

- Redis `BLPOP` 不提供可靠 ACK、租约、重试、死信和幂等；
- 多模块运行时建表和加列不能替代版本化数据库迁移；
- 多个模块直接连接 PostgreSQL，连接池和事务边界不统一；
- 健康检查可能固定返回 `ok`，不能证明依赖真实可用；
- Web 进程启动 Scheduler 可能造成多实例重复执行；
- Compose、Nginx、Worker 和 Scheduler 的拓扑存在不一致；
- 备份脚本不能单独证明 PostgreSQL、权限、Trace、评测和完整业务可以恢复；
- 默认 JWT 密钥、默认管理员和初始密码日志属于生产风险；
- `ollama/ollama:latest` 和部分依赖版本没有完整锁定。

## 4. 主文档新增内容

主文档本次新增或强化了：

- 第 3 节：主体缺失、默认拒绝、静态资源授权和角色一致性；
- 第 6 节：上传安全、资源所有权、索引原子发布和 Prompt Injection 边界；
- 第 7 节：Agent 身份、检索分数、缓存、取消、队列和 Chroma/PGVector 状态；
- 第 8 节：会话所有权、thread 映射和删除级联；
- 第 9 节：Dataset 生命周期和安全查询沙箱；
- 第 12 节：Scheduler、健康检查和队列可靠性；
- 第 14 节：Artifact 所有权、来源和受控下载；
- 第 19 节：迁移、连接池、审计和完整备份恢复边界；
- 第 20 节：Ollama 自动发现尚未实现以及部署一致性验证；
- 第 21 节：开放平台认证不能只依赖前缀豁免；
- 第 22 节：队列、审计、健康检查、迁移、备份和资源生命周期状态；
- 第 37 节：本轮生产级静态审计的证据等级、P0/P1 对照、修复阶段、验收标准和 Agent 协作边界。

## 5. 当前统一口径

### 当前已存在

- FastAPI、JWT、基础用户管理；
- PDF/DOCX/DOC/TXT 基础文本处理；
- XLSX/XLS/CSV 基础数据读取和分析；
- Chroma 向量检索；
- BM25、RRF、查询改写和重排基础；
- SSE、多 Agent 和 LangGraph 基础；
- 基础图表、PDF、Excel 导出；
- PostgreSQL、Redis、本地文件和 Docker 基础。

### 当前不应宣称已经完成

- 完整 RBAC/ABAC；
- 会话和资源所有权隔离；
- 生产级文件上传安全；
- 生产级 Python 数据查询沙箱；
- Prompt Injection 防护；
- 可靠 Redis 任务队列；
- 完整 PGVector 生产检索；
- 完整 Agent Trace 落库；
- 完整四指标评测平台；
- 真实审批工作流；
- 真实数据驱动的 Dashboard 和洞察闭环；
- 完整备份恢复和多实例部署。

### 后续目标

- PostgreSQL + PGVector + 本地文件存储 + Redis；
- Ollama 本机模型自动发现和能力检测；
- 统一资源、版本、权限、指标、证据和 Artifact 模型；
- 可靠任务队列；
- 结构化 Agent Trace；
- RAG 调试台和完整评测闭环；
- 受控审批、洞察、告警和经营数据闭环。

## 6. 后续文档使用规则

后续任何功能设计、代码实现或前端联调，都必须先回答：

1. 资源是什么，稳定 ID 是什么；
2. 所有者、部门、密级和可见范围是什么；
3. 数据来自哪个版本，截止时间和单位是什么；
4. 任务处于什么状态，失败、取消和重试如何处理；
5. Agent 使用了什么模型、工具、Prompt 和权限；
6. 结果有哪些证据、警告、来源和可复现信息；
7. 删除、过期、备份和恢复如何处理；
8. 是否误用了固定金额、部门、指标、阈值、模型名或演示数据。

如果源码、测试、计划和文档发生冲突，优先以当前源码核对结果为准，并在主文档的“当前状态”中明确记录差异。

## 7. r3 二次补齐内容

本次根据“提升提示词”的完整要求，对 r2 文档再次检查并补齐：

### 7.1 P0/P1 问题字段补齐

原来的 P0/P1 表已经有问题、证据、风险、文档状态、Agent 冲突、修复阶段和验收标准，但没有单独列出“是否需要真实环境验证”。

r3 已为每个 P0/P1 问题补充该字段，并区分：

- 只需静态设计即可确认；
- 需要真实 Token、跨部门资源或多用户验证；
- 需要真实 PostgreSQL、Redis、Ollama、Nginx、Docker 或文件样本验证；
- 需要真实浏览器 SSE 断线、取消和重连验证。

### 7.2 P2/P3 问题完整化

r3 新增主文档第 37.7 节，按统一字段补充：

- 金额精度和 Decimal；
- 时间、时区和指标期间；
- Excel 公式注入；
- Artifact 生命周期；
- 分页；
- 查询和图表资源限制；
- 取消后的后台副作用；
- 缓存权限和版本隔离；
- 依赖和镜像锁定；
- CORS；
- PDF/OCR/Word/Markdown 缺口；
- Chroma 到 PGVector 迁移；
- API/SSE 错误契约；
- 删除、归档和备份一致性；
- 配置草稿、发布和回滚；
- 文档和版本口径冲突；
- 测试证据边界；
- 内存回退；
- 审计脱敏和保留期；
- 慢请求和资源竞争运营视图。

每项均包含问题、证据、风险、文档状态、Agent 冲突、修复阶段、验收标准和真实环境验证要求。

### 7.3 功能设计字段统一化

r3 新增主文档第 37.8 节，对主要功能统一补充：

- 用户想完成什么；
- 当前入口和代码位置；
- 当前是否可靠；
- 当前缺口和风险；
- 后续设计；
- 修复阶段；
- 验收标准。

覆盖登录、文档、文件处理、RAG、会话、数据分析、Dashboard、洞察、告警、图表、报告、审批、知识图谱、指标语义、Agent Trace、评测、后台、存储、部署和恢复。

### 7.4 当前文档的最终定位

r3 明确主文档同时包含：

1. 当前功能盘点；
2. 生产风险清单；
3. 后续设计输入。

三者不再混写。源码存在入口，只能说明有基础；设计文档存在，只能说明已规划；测试或历史记录存在，只能说明有辅助证据，不能替代当前代码和真实环境验收。

## 8. r3 执行边界

- 修改文件：`docs/current-functionality-2026-09-10.md`、`docs/current-functionality-2026-09-10-revision-log.md`
- 未修改业务源码；
- 未修改 `frontend/`；
- 未修改测试文件；
- 未修改 Docker、Compose、Nginx、环境变量或部署脚本；
- 未运行测试；
- 未启动服务；
- 未修改数据库、Redis、Ollama 或其他外部环境。

## 9. r4（2026-09-13）真实依赖验收与部署拓扑修订

- 主文档变更：新增第 38 章；37.8 对照表中“存储、部署和恢复”“Agent Trace、评测和后台”两行口径更新；第 34 章禁止项补充本轮清除结果。
- 修订性质：从静态审计转为真实依赖取证。此前写为“静态无法确认”的 PostgreSQL、PGVector、Redis 与备份恢复结论，现在给出可重复命令与用例数。
- 本轮修改代码：是（`app/storage/persistence.py`、`app/common/reliable_queue.py`、`app/api/v1/chat.py`、`app/common/model_config.py`、`app/common/monitoring.py`、`app/main.py`、`app/scheduler/jobs.py`、`app/agents/nodes.py`、`Dockerfile`、`docker-compose.yml`、`deploy/`、`scripts/`、`pyproject.toml`）。
- 本轮修改 `frontend/`：否。
- 本轮运行测试：是。`python -m pytest -q` -> `443 passed, 3 skipped`（打开 `EB_*` 验收开关）；默认离线运行下真实依赖用例自动 skip；`docker compose config` 对基座与叠加层均返回 0。
- 本轮数据库影响：仅隔离库 `enterprise_brain_accept`（`127.0.0.1:5433`）及其恢复兄弟库，测试后清理；`5432` 生产库与 `6379` Redis 未改动。

### 9.1 r4 的关键口径

1. “能连上真实数据库”与“离线能跑”是两件事。本轮两个存储层缺陷（元组行按 `dict(row)` 读取、按不存在的 `created_at` 排序）只在真实 PostgreSQL 上暴露，离线用例结构上不可能发现它们。
2. 验收门必须显式开启并带目标校验，否则一次普通 `pytest` 就可能写到客户库。
3. 部署配置的“存在”不等于“可用”：`postgres:16-alpine` 不含 pgvector、整份 `http{}` 被塞进 `conf.d`、健康检查返回常量 `200`，三者都能通过肉眼审阅但都会在真实 `docker compose up` 上失败。
4. 配置文件“能被解析”也不等于“语义正确”：`docker compose config` 对 root 与叠加层都返回 0，但同一条命令暴露出 `.env` 中的 bcrypt 哈希会被 Compose 变量替换吞掉，属于静默改坏凭据。为此把容器环境文件与开发环境文件分家，并新增 `scripts/check_deployment_env.py` 预检。
5. 仍未通过 Docker 运行门和浏览器端到端，因此 r4 不把项目标为生产试运行就绪。
## 10. r5（2026-09-14）S5 契约与解析器一致性订正

- 修订性质：契约文档、上传白名单与解析器三者口径对齐，外加第 19 章一处事实性纠错。
- 主文档变更：第 19 章把“未发现 PGVector 扩展 / PGVector 向量表”订正为“schema 骨架已入库、无维度、无 HNSW/IVFFlat 索引、无写入方，向量读写 100% 走 Chroma”，并新增 5 条取证要点与 1099 行表格状态；第 6.2 节文件能力表更新 Markdown 行与 Excel/CSV 进入知识库行两处口径。其余章节未重写，第 39 章收尾未触碰。
- 本轮修改代码：是。`app/rag/loader.py` 新增 `load_md()` 并在 `load_document()` 增加 `.md` 分支；`app/documents/file_security.py` 知识库上传白名单由 `pdf/txt/md/docx/xlsx/csv` 收窄为 `pdf/txt/md/docx`。
- 本轮修改契约：`docs/api/contract-v1.md` 删除仓库中并不存在的“独立入队端点”，改为“`POST /api/v1/ask` 超限自动入队，SSE `queued` 事件返回 `request_id`”；另追加 2026-09-14 兼容性说明，未改写主 thread 已写的 2026-09-14 段落。
- 本轮修改测试：`tests/test_file_upload_security.py` 由 7 个用例增至 29 个（含参数化）。新增白名单与 `load_document()` 分支一致性的防漂移用例、`.xlsx`/`.csv` 拒绝用例、以及 `TestClient` 走 `POST /api/v1/upload` 的路由层用例。原路径穿越、双扩展、伪造文件头断言全部保留。
- 路由层错误体口径（与主 thread 同日收口一致）：不支持的扩展名返回 `400`，`detail` 恰为稳定码 `unsupported_file`；人类可读原因只进服务器日志，不进响应体，测试不得断言日志文本。同级码还有 `413 upload_too_large`、`500 document_parse_failed`、`500 document_index_failed`、`415 unsupported_preview`。
- 本轮运行测试：`python -m pytest tests/test_file_upload_security.py -q` -> `29 passed`。未运行全量套件，因并行 Worker 正在改动其它文件。
- 事实依据：`migrations/0001_core_resource_versions.sql:4`、`migrations/0002_execution_data_lineage.sql:235`、`migrations/0002_execution_data_lineage.sql:243`、`app/rag/retriever.py:190`、`docker-compose.yml:48`、`app/common/monitoring.py:56`；`git grep "INSERT INTO chunks"` 零命中，全仓无 HNSW/IVFFlat。
- 本轮未做：未启动服务、未连 5432/6379/11434、未跑 `scripts/migrate.py`、未改 `frontend/`、未改 `app/api/v1/chat.py`。
- 遗留与需主 thread 决策：`.md` 预览返回 `415 unsupported_preview`（`app/documents/preview.py` 不在本切片写集）；`frontend/src/components/DocPanel.vue:351` 的 accept 列表仍含 `.doc`（后端会 400）且缺 `.md`；文档上传那批稳定码尚未纳入 `REST Error Envelope` 列表。

## 11. r6（2026-09-14）Wave 1 四片并行收口与主 thread 同源修复

- 修订性质：按 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 的三波依赖关系派发子 Agent，Wave 1 的 S5/S2/S3/S6 四片并行完成并合树；主 thread 同期的 `chat.py` 收口、缓存 scope 与容器门实证修复一并登记。
- 派发前置（§0）：先落 checkpoint 提交 `de13e90`，四片 write set 严格不重叠；Wave 2 的 S1 与 Wave 3 的 S4 需要写 `app/api/v1/chat.py`，等到主 thread 收口提交 `5db955c` 之后才放行；`frontend/` 全程零改动。
- S5 契约与解析器一致性（`d67987a`）：内容见第 10 章 r5，本轮无补充。
- S2 审计持久化（`ab19199`）：`app/common/audit.py` 由模块级 `_events` 列表 + `Lock` 改为走 `app/storage/persistence.py` 的 `build_persistence_adapter()`，未新造平行存储；新增 `migrations/0005_audit_events.sql` 并同步 `migrations/manifest.json` 校验和；事件补 `request_id`、`resource_scope`、`policy_version`、变更前后摘要与保留期，脱敏复用 `app/common/tracing.py:sanitize_trace_event()`；写失败显式可观测，不再静默丢弃后返回成功。
- S3 管理面只读 HTTP（`df9ba13`）：新增 `app/api/v1/observability.py` 与 `tests/test_observability_routes.py`，`app/main.py` 只增加挂载一行；四条路由为 `POST /api/v1/retrieval/debug`、`GET /api/v1/traces/{trace_id}`、`GET /api/v1/evaluations`、`GET /api/v1/audit/events`；匿名一律 `401 authentication_required`，不降级为 admin；`AuthMiddleware` 白名单未扩大。
- S6 内存回退与多实例边界（`1cd8827`）：`/health/details` 逐子系统如实报告 `storage_mode` 与 `problems`；生产环境缺少依赖时启动失败或进入只读保护，不再伪装正常；删除 BLPOP 版死代码 `app/common/queue.py` 并把 `tests/test_reliable_queue_request_path.py` 改为只测 `ReliableQueue`；开放平台补 `POST /api/v1/apps` 注册面（admin + 强制审计）。
- 主 thread 同期收口：`5db955c` 把 no-store 与稳定错误码覆盖到其余已鉴权响应体（新增 `app/common/no_store.py`）；`7962c30` 丢弃 worker 已不再持有的结果并稳定文档错误码；`508abbc` 把告警扫描限定在租户数据目录、目录与产物响应不再回显服务器路径；`cc3cd99` 给答案缓存与调度缓存键加入调用方 scope（**加性改动，`chat.py` 尚未接线，默认空 scope 沿用历史键**）；`1a9b97b` 复原被一次 UTF-8/GBK 往返损坏的中文串；`9c27421` 是容器门实证修复。
- 容器门实证（run1）：daemon、env 预检、`docker compose config`（基座 + 叠加）、frontend 构建、migrate 全部通过，`postgres`/`redis`/`ollama`/`worker`/`scheduler` healthy；唯 backend 启动失败——镜像内无 `models/`，reranker 联网下载 `Connection refused` 重试数分钟后异常逃出 FastAPI startup，进入重启循环。根因在 `9c27421` 修复：reranker 只用 `RERANKER_MODEL_DIR` 本地目录，联网下载必须显式 `RERANKER_ALLOW_DOWNLOAD`，加载失败锁存 `unavailable_reason` 且不抛错，`_preload_sync` 改为 best-effort。顺带发现镜像内无任何字体，图表中文全为方框、PDF 无法嵌字体，故补 `fonts-wqy-microhei`。修复后的复验尚未通过（run2 因 `APT_MIRROR` 镜像源 502 在 apt 层构建失败，未取到有效证据）。
- 契约文档（`docs/api/contract-v1.md`）：登记 no-store 覆盖范围、catalog `storage_path` 去路径化、`.md` 预览、`/alerts/check` 的 `scan_scope`、逐子系统 `storage_mode`/`problems`、四条 observability 只读路由与 `POST /api/v1/apps`。`migrations/README.md` 补 0004/0005。
- 本轮运行测试：Wave 1 合树后的全量 `python -m pytest -q` -> `558 passed, 25 skipped`（r4 时基线为 `443 passed, 3 skipped`）。逐片自证：`tests/test_retrieval_pipeline_fallback.py` 5 例、`tests/test_deployment_guards.py` 22 例。`9c27421`/`cc3cd99` 之后的全量重跑在 S1 合树后统一执行，见第 12 章。
- 本机环境事实（影响验收口径）：未安装 `fakeredis`，`get_redis()` 在无 `REDIS_URL` 时实际走进程内 `_MemoryRedis`；宿主机 `5432/6379/11434` 均有进程监听，compose 只发布 `127.0.0.1:8001` 与 `:80`，不构成端口冲突。
- 本轮未做：未改 `frontend/`；未连生产库执行业务写入；未跑 `scripts/migrate.py` 实跑；`tmp/e2e/REPORT.md` 的 P0-1 结论订正另行登记。
- 遗留与需主 thread 决策：`_is_production_environment()` 在 chat/alerts/auth/monitoring 重复实现；`tests/conftest.py` 未隔离 `PERSISTENCE_FALLBACK_PATH`，跑测试会写真实 `./data/.persistence.json`；`app/scheduler/jobs.py:17` 裸调 `evaluate_all()` 无 Principal；`DATA_DIR` 权威定义两处；`app/tools/excel.py:258` 白名单 `eval()`；审计 `request_id` 仍普遍为空；reranker 不可用目前只进日志与 `unavailable_reason`，未进 health。计划 §4 四项（Dashboard rows 由客户端提供、会话三份状态、checkpointer 降级 `MemorySaver`、alerts 与 insights/rules 双实现）仍是决策未执行。
- 口径：容器门与浏览器端到端均未通过，r6 不把项目标为生产可用。
## 12. r7（2026-09-14）Wave 3 收口、真实服务器验收与容器门首次全绿

- 修订性质：`docs/handoff/2026-09-14-consolidated-fix-plan.md` 的三波依赖关系全部走完。Wave 3 两片（S4 索引发布接线、S7 指标语义事实层）合树；主 thread 在逐条复核中新发现并修掉一个只在真实 PostgreSQL 上暴露的缺陷、一个边缘代理可靠性缺陷，并把 S4 缺的第四张表补完。提交：`b9a0d6b`(S4) / `c0fdd21`(S7) / `79714ff`(psycopg3 真服务器) / `0f64cf1`(nginx 边缘代理) / `21a0572`(契约文档)。
- 派发过程中的失误（如实记录）：同一份 S4 任务书被重复下发两次，其中第二次因模型参数不被支持而自动终止，未形成双写；S7 的协调消息也重复了一次（内容相同，无害）。计划书自身只定义 Wave 1/2/3，此前口径里出现的“Wave 4/S8”不在文档内，已撤回不作为交付承诺。
- 对计划书的三处核实更正：① S7 任务中“让 `MetricContext` 暴露 `definition_version`”与“`/semantics/match` 返回带 `definition_version`”在 HEAD 上已经成立（`app/agents/contracts.py:153` 已有该字段，端点返回 `context.model_dump()`），改派为真实工作；② 要求 S7 新建 `migrations/0007_metric_definition_sync.sql` 并改 `manifest.json` 是错误的——`metric_definitions` 已在 `migrations/0002:72` 建好且列够用，且 0007 编号归 S4，S7 实际交付零迁移；③ 计划书给 S4 的 write set 未包含迁移，但 `chunks.owner_id` 原为 `NOT NULL` 与 S1“无主老文档不得伪造 owner”直接冲突，S4 的 `0007_document_chunk_count.sql` 是计划书漏写的必需品，予以保留。
- S4 交付：上传与删除经 `create_version → validate → publish` 驱动一次发布，镜像表在同一事务内写入，任一步失败即 `abort` 并把 registry 指针回滚，失败答案 `500 index_publish_failed` 且带 `details.stage`。`retriever.py` 只做“回读 Chroma 实际持有的 chunk”而非重新切分，Chroma 仍是唯一读路径，`chunks.embedding` 不写。计划 Accept 点名的第四张表 `resource_versions` 在 Worker 交付中**零写入方**（其 Agent 中途终止、未交报告），导致 `chunks.resource_version_id` 指向一个从不存在的版本行；主 thread 补上该写入、把 `owner_id` 可空扩到这张表（扩展 0007 并重算校验和）、并把 `resource_versions` 纳入回滚参数化用例。
- S7 交付：`metric_definitions` 为权威来源、代码表退为兜底、命中来源三态可区分（运维行 / 代码同步行 / 代码兜底）、`definition_version` 取表内真实值；`verified_against_documents` 是**无法被存储 JSON 设置的属性常量 False**，因此表里的行不能伪装“已与制度文件核对”；新增 `GET /api/v1/semantics/metrics`（前端需求单 R6）。**遗留**：`sync_code_definitions()` 与 `register_metric_definition()` 在应用内没有生产调用点（GET 路由不应写库），所以“`metric_definitions` 不再恒 0 行”在真实部署里尚未成立，本轮只交付了写入能力与其证明。
- 真实服务器验收（本轮最重要的新增证据；此前两片只在测试桩件上验过）：`app/rag/indexing.py` 有两处是按桩件而非按 psycopg3 写的。① `table_name = ANY(%s)` 传的是 Python tuple，psycopg3 会把它适配成 row constructor，真服务器上抛 `InvalidTextRepresentation`，于是**每一次真实发布镜像都静默降级、一行都不写**，而全量测试始终全绿；② `connection.executemany` 在 psycopg3 里不存在（该方法属于 cursor），于是作为本切片核心命题的 chunk 批量写入必抛 `AttributeError`。两处均已修复，且桩件已**主动删除** `connection.executemany` 应答，使同类 psycopg2 遗留下次直接在测试里失败。
- 同一验证在容器内真实 PostgreSQL 上重跑的结果：一次上传得到 `chunks=3 / index_registry=1 / index_versions=1 / resource_versions=1`；无主文档真实写入 `owner_id IS NULL`（0007 的可空语义在服务器上成立，未伪造主体）；退役后 `resource_versions.status=retired` 且 `superseded_at` 置位、只清除属于该文档的 chunk；失败路径下四张表仍为 0 行（回滚不留半发布状态）。计划里 S4 的 Accept 由此首次成立。
- S7 的同一验证：真库播种 2 行、二次播种幂等（`inserted=0`）、命中来源正确标为 `metric_definitions` 并区分“代码同步来的”与“运维录入的”、**免改码新增「毛利率」并以表内 `finance-2026q4-v1` 命中**、探针退出前把库清回 0 行。S7 自述的“真库端到端未验”由本轮补齐（readiness 标志由 `app/common/auth.py:207-229` 的探测设置，与容器实际状态一致）。
- 容器门：run7 是在**已提交树**（`21a0572`）上的权威运行，结果 **22 passed / 0 failed**，证明 `0f64cf1` 之后边缘代理确实不再因 backend 换址而 502。run5 首次 22/22 全绿（r6 当时只有 backend 崩溃的失败证据）；run6 暴露 `nginx proxies /api/v1/health` 返回 502，根因是 nginx 只在加载配置时解析一次 `upstream` 内的主机名，backend 被重建换址后代理一直拨旧地址（`0f64cf1` 改为变量 + Docker 内嵌 DNS 运行时重解析，并实机证明：用占位容器占走旧地址、让 backend 移到 `172.18.0.9` 后，代理在完全不重载不重启的前提下仍返回 200）。其余关键事实：`ledger=7 tables=26 vector=1`（0001-0007 在真库上应用、pgvector 在位）、迁移幂等重跑 `applied=0`、`nginx -t` 通过、`/static` 与运行时目录在边缘被拒（403/404）、后端 `/api/v1/health` 200、匿名 `/health/details` 401、单调度器进程、队列 worker 存活、模型来源如实（`configured True`）。
- 环境事实（影响可复现性）：用 `Stop-Process` 硬杀 Docker Desktop 会让 `%LOCALAPPDATA%\Docker\run\sailor-ingest.sock` 与 `%LOCALAPPDATA%\docker-secrets-engine\engine.sock` 成为“系统无法访问此文件”的孤儿条目，下次启动时 rename 成 `.stale` 失败导致 backend 崩溃并弹错误框；这些条目单文件删不掉，只能整体改名目录绕开（恢复脚本 `tmp/docker_recovery.ps1`）。结论：今后必须用优雅退出而不是强杀。
- apt 网络定案：容器内 `HTTP_PROXY` 为空之后实测 tuna 3.7MB/s、USTC 0.8MB/s、官方源 4MB/s，全部 `rc=0`，r6 中必挂的 9.6MB `trixie/main/binary-amd64/Packages.gz` 已能正常下载。`deploy/.env.server` 的 `APT_MIRROR=mirrors.tuna.tsinghua.edu.cn` **无需修改**；r6 记录的 502 与大文件断连是坏代理注入造成的瞬时故障，不是镜像源问题。
- 测试基线：权威口径 `.venv\Scripts\python.exe -m pytest -q` -> **653 passed, 22 skipped**（r6 为 602/22），全量约 31 秒。裸 `python`（anaconda3）缺 chromadb/rank_bm25/jieba/sentence-transformers，会静默 skip 掩盖真失败，不可作为口径。
- 并发与测试隔离：`app/storage/persistence.py:431` 的持久化回落默认写仓库内 `./data/.persistence.json`，本轮 L1 落地前实证该文件已被测试写到 877KB；两个 Worker 在同一棵树上并行跑全量时必须各自设私有 `PERSISTENCE_FALLBACK_PATH`，S7 亦主动披露一次冒烟漏设该变量而污染了共享文件。`tests/conftest.py` 的会话级隔离（L1）本轮已落地（`eb0c7cc`）：变量必须写在 conftest 顶层而不是 fixture 里，因为 `_PERSISTENCE` 在 import 期就固化；全量跑完后该文件保持 880373 字节与 19:49:31 的时间戳不变，实证不再被测试污染。
- 构建成本事实：`docker compose build migrate` 约 5m43s，主要开销是 18GB 镜像层导出与最后一层 `chown -R /app`（124 秒，每次改代码都要重跑）；`Dockerfile` 用的是定向 `COPY app ./app` 而非 `COPY . .`，`.dockerignore` 已排除 `.venv`(1.3GB)/`chroma_db`(191MB)/`data`(97MB)/`tests`(61MB) 等。注意 `APT_MIRROR` 取值变化会重建 apt 层（run3 与 run5 之间为此多花约 3 分钟），预热与正式构建必须用同一个值。
- 订正 r6 的两处转述：① `_is_production_environment()` 实际有 **8** 份副本（`app/common/auth.py`、`app/api/v1/chat.py`、`app/api/v1/alerts.py`、`app/documents/catalog.py`、`app/memory/profile.py`、`app/memory/long_term.py`、`app/knowledge_graph/service.py`、`app/common/open_platform.py`），r6 写的“chat/alerts/auth/monitoring”不准确——monitoring 里并没有该函数，另外还漏了四处；② reranker 不可用并非完全没有出口，它在 `app/api/v1/observability.py:68` 的 `_RETRIEVAL_CAPABILITIES` 能力表中（`sentence_transformers / reranker / cross_encoder / rrf_only`），但确实不进 `/api/v1/health`。
- 由转述升级为实证的遗留：`app/` 内不存在任何 `X-Request-ID` 处理，`app/main.py` 也不出现 `request_id`，中间件从不设置 `Principal.request_id`（默认 `""`），因此 `app/common/audit.py` 的 `_resolve_request_id()` 在绝大多数调用上只能回落到空串。另外实测 `app/common/cache.py` 的 `cache_dispatch` / `get_cached_dispatch` / `cache_semantic_answer` / `get_semantic_cached_answer` 在 `app/` 内**零调用方**，是四座孤岛。
- S1 遗留仍未动（本轮无授权范围变更）：`policy_version` 仍为 `resource-policy-v2`；`POST /upload` 只记录 principal 未强制 `resource:upload`；`/api/v1/*` 无 token 时 401 报文仍是中文 `请先登录` 而非 `authentication_required`（容器门本轮实测复现）；未实现“认领无主文档”的写操作。
- 本轮未做：未改 `frontend/`；未在宿主库跑 `scripts/migrate.py`（宿主 PG 里 `metric_definitions` 表尚未建立）；`tmp/e2e/REPORT.md` 的 P0-1 结论订正仍未做；浏览器端到端未做。
- 口径：容器门已首次全绿，但浏览器端到端、Dataset/Artifact/会话历史落 PG、Chroma→PGVector、配置中心草稿-校验-发布-回滚、镜像 digest 锁定仍未完成，**r7 不把项目标为生产可用**。

## 13. r8（2026-09-15）浏览器端到端首轮、复验轮与五个真实缺陷收口

- 修订性质：本轮做四件事——① 首轮**经 nginx 边缘**的浏览器端到端验收（子 Agent 执行，主 thread 逐条复核原始日志）；② 对它报出的每个 P0/P1 独立定位并修复；③ 第二轮定点复验 + 镜像重建后端到端复验；④ 处置子 Agent 的两轮**不实发现**。`docs/handoff/2026-09-14-consolidated-fix-plan.md` 三波仍是唯一权威计划，Wave 1/2/3 已全部合树，本轮属计划外缺陷收口，未新增波次。
- 测试基线：`.venv\Scripts\python.exe -m pytest -q` -> **690 passed, 22 skipped**，约 31 秒。轨迹 665（r7 收口）→ 679（`e216e5b`，09:46 实测）→ 682（`84af113` +3）→ 690（`3e35481` +8）。口径必须是该 venv 的 python，裸 `python` 是 anaconda3，会静默 skip 掉整套依赖真实库的用例。
- 容器门：run8 **23/0**、run9 **24/0**、run10 **24/0**（树 `c6c6009`）、run11 **24/0**（树 `84af113`）、run12 **24/0**（树 `3e35481`，10:45 完成；本轮构建因 buildkit 缓存被 GC 而重装整套依赖，耗时约 28 分钟，run11 同一门 6 分钟），日志 `tmp/container_gate_run{8..12}.log`。run11/run12 的镜像内容用容器内 grep 直接核对（例：`grep -c '已取消，未执行' /app/app/agents/orchestrator.py`=1、`grep -c '图表生成时直接使用' /app/app/agents/tools.py`=0），不靠"应该已经重建"推断。

### 13.1 首轮浏览器端到端（45 项）与逐条复核

- 路径：`http://localhost/`（nginx 1.27.5）同源反代 `/api/v1`，**未直连 8001**；Playwright + Chromium headless。报告与 121 份证据在 `tmp/browser_e2e/`（`tmp/` 被 `.gitignore:13` 忽略）。
- 结果：B1–B6 共 45 项 -> 通过 24 / 失败 12 / 未覆盖 4 / 部分 1 / 事实 2；P0×3、P1×6、P2×5，另按 `docs/frontend-plan-2026-09-14.md` §2 单列 4 条迁移注意事项（洞察→「异常与告警」、审批→「报销自查」、图谱撤入口，三页不就地镀层）。
- 我独立接受并修的：P0-1 卷属主（`Dockerfile` 未建 `/app/documents`，命名卷继承 root:root，每次 `POST /upload` 死在写临时文件而健康检查全绿）、P0-3 恢复流丢主体（`app/agents/orchestrator.py:947` 只带 `thread_id`）、P1-3 健康检查假绿灯（`app/common/monitoring.py:196` 只看 HTTP 状态）。
- 我订正的：P0-2 原引用 `logs/B4_chart_response.json` 作"admin 出图失败"证据，但该文件是**成功**响应（25823 字节 PNG）。真实缺陷是 `/chart`、`/export` 把失败兜成 **HTTP 200 + `{"error": …}`**（见 13.4）。
- 我撤回的（均为我自己的判断失误）：① 指控子 Agent"删引导 admin 并重启 backend"——`docker inspect` 显示 `Created=9/14 14:41Z`、`StartedAt=9/15 00:08:44Z`，那次是**我**为 `docker cp` 做的**重启**而非重建，`users.id=1` 正是那次播种产生的，访问日志里 `DELETE /api/v1/users/1` 是 **403**；② 同一凭据的 401 是 PowerShell `Invoke-RestMethod` 的 body 编码副作用；③ 由②派生的 r7「`AUTH_PASSWORD_HASH` 非默认口令」推断作废，它就是 `bcrypt("admin123")`。

### 13.2 复验轮（09:29–09:56，树 `c6c6009` 运行栈）新增并成立的四条

- **R-新1（P0，已修）** 文档检索结构性不可达：无部门账号提问 → `authorization_unavailable`；带部门账号上传成功后提问 → `未找到`。根因不是检索侧而是**写入侧**：作用域取自前端表单（`department: str = Form("")`），全仓又没有事后改元数据的接口（只有 `/users/password` 与 `/profile`，后者写用户画像不是 `users.department`），于是每个文档都以空部门入库、任何谓词都滤掉它。实证：`tmp/browser_e2e/logs/RV_B3_chroma_filter_proof.txt` 三段对照（原谓词 0 命中 / 放宽空部门 2 命中 / 只留密级 2 命中），存储元数据实测 `department: ''`。修复见 13.3。
- **R-新2（P1，已修）** 内部提示脚手架进用户可见回答：`app/agents/tools.py` 把 `用户查询: {query}` 和一句写给模型的「图表生成时直接使用上述数据样本中的字段名和数值」拼进工具返回值，而模型不可达时该返回值**就是**答案。源头修，不在展示层打补丁。
- **R-新3（P1，已修）** 「取消」不产生任何差别：批准与取消两条流的 `text` 事件**逐字相同**，且被拒动作照样执行。定位与实测见 13.3。
- **R-新4（P2，已修）** `/chart`、`/export` 以 HTTP 200 返回业务失败，与 `/upload-excel` 已改 403 的口径不一致。实测（run11 镜像，经 nginx）：admin `POST /chart` → `200 {"error":"artifact owner must have a department scope","path":null}`；`POST /export {"format":"docx"}` → `200 {"error":"不支持格式: docx"}`。见 13.4。
- 同时被复验确认为**已修**的：P0-1 上传→列表→解析→预览→删除五步在容器里全通（`POST /api/v1/upload` 200、`parse_status:ready`、`index_publication:published`、预览出正文、删除后 catalog 归零且 Chroma 0 chunk）；P0-3 恢复流不再报鉴权错且执行并产出与分析一致的数字；`a38faf5` 的新错误码 `403 department_scope_required` 与「失败不留孤儿文件」；`c6c6009` 的 `degraded` 上报（`{"status":"ok","model_count":0,"model_present":false}` + `problems=["knowledge_graph_read_only","open_platform_apps_read_only","model_not_available"]`）。
- 复验轮另一条**运维事实**：`/health/details` 在边缘不是裸路径——nginx 只反代 `/api/` 与 `/api/v1/health`（`deploy/nginx.conf:50`、`deploy/nginx.conf:68`），`http://localhost/health/details` 落到 SPA 兜底返回 `200 text/html`；看详情必须走 `/api/v1/health/details` 且带 Bearer（不带 → 401，正确）。

### 13.3 本轮修复（五处，逐处给判据）

- **`c21c342` 上传文档的作用域由上传者决定**：`app/api/v1/chat.py:1554` 从认证主体派生 `department`，并在响应里回显（`:1683`），不再取前端表单。这同时堵住另一半问题——原先前端能把文档"投"进任意部门的结果集。无主体的历史调用仍记为无主（legacy）行，不猜归属。
- **`0e34a41` 预检要说实话**：`scripts/check_deployment_env.py` 在 `AUTH_DEPARTMENT` 为空时打 `warn`（不阻断，rc 仍 0），因为无部门的首管理员登录得进来却上传不了数据、出不了图、也检索不了文档。README 同时列全三条被拒路径，并撤掉我上一轮写错的"事后再补部门"指引。
- **`70792ce` 统计摘要不再假 N/A**：`_answer_query` 向 `describe()` 要 `sum`，而 `describe()` 根本不产 sum 行，于是每次回答都是「合计: 金额: N/A」，而同一次上传的 profile 早就报了真合计。合计改为直接从帧取（`app/agents/tools.py:243`）；`describe()` 给不出的其它统计仍如实 N/A，不编数。
- **`84af113` 拒绝必须真的拒绝**：恢复流的取消分支只做 `update_state(消息)` + `Command(goto="supervisor")`，而被挂起的 worker 从没被标记完成，于是 supervisor 把它**重新派发并执行**，会话还**再次挂起**。我隔离复现（`tmp/probe_hitl_paths.py`，强制 MemorySaver、不连宿主 PG）：修复前 `workers=['chart']` 且 `check_interrupt` 在取消后仍返回 `pending=['chart']`；修复后取消分支为每个被拒节点写入结果（`app/agents/orchestrator.py:987-996`），`workers=['chart']` 的内容变成「已取消，未执行：📈 生成图表」且不再挂起。
- **`3e35481` 失败要有状态码、没评分不许编**：`/chart`、`/export` 先查归属前置条件（`app/api/v1/data.py:270`，与 `/upload-excel` 同一个 `department_scope_required`），不支持的类型/格式给 400 稳定码，意外失败记日志并回 500 码而非把异常串吐给客户端（全仓无调用方读那个 200 body：前端两处路由零引用，实测 `rg 'v1/chart|v1/export' frontend/src` 无命中）。同时 `相关度` 两处编造被收：聊天侧 `d.get("_score", "?")` 让无评分命中显示成 `相关度:?`，MCP 侧 `d.get('_score', 0)` 把同一件事报成"相关度 0.00"，统一走 `app/rag/retrieval_pipeline.py:332` `format_relevance()` → 无评分显示「未评分」。

### 13.4 run11 与 run12 上的端到端实证（我自己打的，非转述）

- **run11（树 `84af113`，10:10–10:12，脚本 `tmp/probe_r8_e2e.py`，输出 `tmp/r8_e2e_out2.txt`）** —— 经 nginx `http://localhost/api/v1`，建两个同权限不同部门的临时账号：
  - 作用域实证（`c21c342` 的唯一缺证据项）：甲部账号上传 → `POST /upload` 200，`GET /documents/catalog` 返回 **`department='R8甲部'`、`owner_id='r8-probe-a'`**（此前恒为 `null`）。
  - 检索实证（R-新1 闭环）：同部门提问「打车报销上限是多少元？」→ **命中 473**，带来源 `[1] 来源:r8-scope-….txt`；乙部同问 → `未找到`（不跨部门泄露）；admin → `authorization_unavailable`（13.6 第一条）。
  - HITL 实证（`84af113` 闭环）：批准流文本 = 「暂无数据文件…」（节点真执行），取消流文本 = 「已取消，未执行：📈 生成图表」，**两条不再逐字相同**；取消后再批准不会重复挂起。
  - 当轮回答里仍显示 `相关度:?`，这正是 13.3 里 `3e35481` 要收的那个默认值。
- **run12（树 `3e35481`，10:49，脚本 `tmp/probe_r8_e2e2.py`，输出 `tmp/r8_e2e2_out.txt`）** —— 上面四项全部复现，另有：
  - `相关度:未评分`（不再是 `?`）；批准/取消两条流里既无 `【…Agent 返回】` 前缀也无内部提示串。
  - `POST /chart`：无部门主体 → **403 `department_scope_required`**；不支持类型 → **400 `unsupported_chart_type`**；`POST /export` 不支持格式 → **400 `unsupported_export_format`**（同轮 run11 上这三例实测仍是 200 带 `error`）。
  - **新测出的遗留（不是推断）**：会话停在 HITL 挂起时按停止键 `POST /ask/{sid}/cancel` → 200 `{"cancelled":true}`，但**挂起没被清**；随后 `POST /approve {"approved":true}` → 被"停止"的动作照样执行。待定语义见 13.6。
  - 收尾：我建的 2 个账号与 3 个文档全部删除，复验 `GET /users` 仅剩 `admin`、`GET /documents/catalog` 为 `[]`。
- 容器内只读清点（`docker exec … /app/.venv/bin/python`，跑 `SELECT count(*)`，不写）：`users` **1**、`documents` 5、`document_versions` **0**、`datasets` 5、`sessions` 33、`session_messages` 86、`artifacts` 4、`index_registry` 5、`trace_events` 791、`retrieval_traces` **0**、`metric_definitions` **0**。两个 0 各是一条真实遗留：`retrieval_traces` 的写入方只在 `app/rag/debug.py:68`，未接进 `/ask` 主链路；`metric_definitions` 空因 S7 写入方至今无生产调用点。`documents` 5 而 `document_versions` 0 说明**删除只清了版本表，PG `documents` 表没有 DELETE 语句**（全仓该表只有一处 INSERT UPSERT，`app/api/v1/chat.py:497`，无人读），留下一批引用已删文件的幽灵行。
- 运维事实：run12 的 `docker compose build migrate` 因 buildkit 缓存被 GC（`docker system df` 显示 36GB 缓存 / 23.45GB 可回收）而重装依赖，耗时约 28 分钟（run11 同一门 6 分钟）。门本身不受影响，但重建时间不能按 6 分钟预估。

### 13.5 子 Agent 后期不实内容的四轮处置（一律不采信，附我实测）

- **图谱 503 泄露宿主机信息**：不成立。`app/api/v1/graph.py` 不存在、`git grep KG_EXTRA_PATH` 无命中；图谱路由在 `app/api/v1/intelligence.py:106/133`，写失败抛的是常量 `detail="storage_read_only"`（`app/api/v1/intelligence.py:124`）。我实测经 nginx：匿名 `POST` → **401 `请先登录`**，admin `POST` → **503 `{"detail":"storage_read_only"}`**。响应体不含 IP/端口/用户目录。它引用的 `logs/GRAPH_503_detail_leak.txt`、`data/admin_token.json` 全盘不存在。
- **空部门文档跨部门泄露**：不成立为"检索泄露"。`app/rag/filters.py` 在 `c6c6009..HEAD` 零改动，部门谓词 `{department: {$in: departments}}` 的 `departments` 明确剔除空值（`app/rag/filters.py:27-34`），空部门调用方直接 `authorization_unavailable`。它引用的 `logs/B3_cross_department_leak.txt`、`logs/B3_delete_permission.txt` 不存在，`chat.py:1688 can_manage` 这个函数全仓没有。我在 run11/run12 上实测：甲部文档 473 命中，乙部同问 `未找到`（见 13.4）。**但**它指向的语义冲突是真的：`app/common/rbac.py:34` `doc_visible` 把 `department == ""` 视为公开，与检索侧相反——登记为未决（见 13.6 问 (e)），不按 P1 记。
- **「admin `/chart` 返回 503 `chart_generation_failed`」与「`【chart Agent 返回】` 前缀仍可见」**：不成立且不可能成立。`chart_generation_failed` 是我 10:12 才写进 `data.py` 的字符串，而容器内 `grep -c chart_generation_failed /app/app/api/v1/data.py` = **0**；它给的捕获时间（10:01–10:04、10:25–10:27）当时宿主时钟分别是 09:56 与 10:24。它引用的 `tmp/bug_1026_chart_text.txt`、容器 `/tmp/bug*`、`/tmp/rv_chart_latest.py` 在我两次实取（10:23:28、10:24:24）均为"不存在"。`用户查询` 现在全仓只出现在一句注释里（`app/agents/tools.py:424`），`nodes.py` 命中 0。前缀 `【…Agent 返回】` 由 `orchestrator.py:428` 写进图消息，但两条 SSE 出口都显式跳过它（`app/api/v1/chat.py:1158`、`app/api/v1/chat.py:1276`），我的探针输出里也确实没有。
- 它还把我 10:12 的 `3e35481`（已提交）三个文件说成"另一个 Agent 的未提交改动"，并称在自己"停手"期间跑了主机 pytest。**该子 Agent 自 10:0x 起的追加报告一律不采信**，我只采信其 09:30 与 09:51 两轮中我逐条读过原始日志的部分（那些原始文件确实存在且内容与结论一致）。
- 同轮它报的「残留」也对不上：browser-e2e-rv-237.txt（82 字节）、3 个 r8-e2e-*.csv、11 个 artifact、9 个孤儿会话——我实测 catalog 为空、数据集 5 个、artifacts 表 4 行（13.4 末段）。它唯一可信的计数是 users 仅剩 admin。
- 我自己的流程失误：把第一轮结果交给它复验时，没有先要求"证据文件必须 `Test-Path` 通过 + 实取时钟"，导致两轮假发现进入我的待整合队列（各消耗一轮复核）。已在 13.6 的遗留里记下方法约束：任何新发现必须先给出可 `Test-Path` 的原始文件与实际 `Get-Date` 时间戳，否则不进入计划。

### 13.6 仍存缺陷与遗留（登记，未顺手修）

- **需你决策的语义（唯一阻断"开箱可用"的一条）**：默认 `admin` 没有部门，因此**不能对知识库提问**（`app/rag/filters.py:34-38` 硬拒 → 界面显示 `文档检索不可用（error_code=authorization_unavailable）`），也不能上传数据、出图（403）。两条路：(e1) 引导管理员必须配 `AUTH_DEPARTMENT`（预检已 warn，但生产上仍可能是空）；(e2) `role=admin` 在检索侧走 `policy.py` 的 `administrator_scope` 全部门可见。现在 `rbac.py:34`（空=公开）与 `filters.py`（空=拒绝）是**两套相反语义**，不统一就会一直出现"目录里看得见、问答里查不到"。
- 后端：数据集与 artifact **没有删除 API**（P1-6），验收残留已经攒到 5 个数据集、4 条 artifact、33 个会话 / 86 条消息、PG 「documents」表 5 行幽灵行（见 13.4 末段实测）；`data.py` 里两处 200-带-error 已收（实测全仓再无 HTTP 路由返回 `{"error": str(e)}`），同族写法只剩流内与工具内两处：`app/agents/orchestrator.py:945` 仍把异常串 `yield {"error": str(e)}` 给上层、`app/tools/visualize.py:152` 以 `{"error": str(e), "path": None}` 记失败；HITL 挂起时按停止键 `POST /ask/{sid}/cancel` 只翻转在跑流的取消位，**不清 Graph 挂起**——实测见 13.4「停止后再批准」一行，已在 run12 上实测（13.4），语义待定：「停止」到底等于「拒绝该动作」还是只停当前流；`app/scheduler/jobs.py` 无 Principal；`DATA_DIR` 双份 import 期解析；`app/tools/excel.py:258` 白名单 `eval()`；无 `X-Request-ID` 中间件 → `Principal.request_id` 恒空；S1 遗留（`policy_version=resource-policy-v2`、`POST /upload` 未强制 `resource:upload`、401 报文中文）；`app/common/cache.py` 四函数零调用方；`_is_production_environment()` 8 份副本；`data/0008_…sql` 草稿仍在你手上。
- 跨端契约：P1-5 artifact 内容 URL 只认 Bearer 头，`<img src>` 带不了，故界面永远看不到图（`app/storage/artifacts.py:56-62`）——要动的是签名 URL 或 cookie 作用域，属契约变更，未动。
- 前端线（未经授权不改）：`DocPanel.vue:444` 删除按钮 `v-if="isAdmin"` 而后端允许 owner 删（`app/common/policy.py:36` 列了 `ACTION_DELETE`）→ 非管理员上传的文档在界面上删不掉，只能走 API；`DocPanel.vue` 乱码 `澶辫触` 1 处（另 4 处 `?` 经前端线核实是字面量兜底串），以及 `app/agents/tools.py` 之外的 `??????` 已由前端计划 F7 的错误码字典接管——三页按 §2 裁定不镀层。
- 环境事实：本机 Ollama **零模型**（`model_count:0`、`model_present:false`），任何需要 LLM 生成/归因/`_ai_analysis()` 的路径未经受控验证，本轮所有"回答"都是确定性工具输出；宿主 PG 未跑 `scripts/migrate.py`（故 `metric_definitions` 缺表），这是我有意没做。

- 两条我自己查出来的新遗留（不属任何报告）：**「停止」不清 HITL 挂起**（13.4 run12 实测）；**PG「documents」表被写成只插不删的幽灵表**（5 行指向已删文件，删除路径清的是 document_versions，全仓该表无任何读点，app/api/v1/chat.py:497）。

### 13.7 本轮环境扰动（如实）

- 我（主 thread）的写操作：提交 `c21c342`/`0e34a41`/`70792ce`/`84af113`/`3e35481` 五个修复与 8 个新用例；跑 run11、run12 两次容器门（各重建镜像并 `up -d`）；两次端到端探针建的 2 个临时账号 + 3 个临时文档**已全部删除并复验**；容器内只跑 `SELECT count(*)` 与 `grep/md5sum` 只读命令。未改 `frontend/` 任何文件。
- 未能清掉的残留（都是"没有删除面"导致，即 P1-6）：5 个 `browser-e2e-*.csv` 数据集、4 条 artifact 记录、33 个会话与 86 条消息（含已删账号的孤儿会话，`GET /sessions` 只认本人，我无法从 API 清）、PG `documents` 表 5 行幽灵行。
- 子 Agent 的写集仅 `tmp/browser_e2e/**`；它自 10:0x 之后报告的三处"新发现"、三处"残留"（`browser-e2e-rv-237.txt` 82 字节、3 个 `r8-e2e-*.csv`、11 个 artifact、9 个孤儿会话）**我实测均不存在或与计数不符**（catalog 为 `[]`、数据集 5 个、artifacts 4 条），一律未采信、未写入结论。
- 我自己的失误（如实）：① 首轮把"复验"整体外包给子 Agent 且未要求"证据文件必须 `Test-Path` 通过 + 实取 `Get-Date`"，导致三轮不实发现进入我的待整合队列，各花掉一轮复核；② `4427231` 首次提交信息写了未实证结论，已 `--amend` 撤下；③ 一次 `io.open(p,"w",newline=...)` 参数错误在抛异常前已截断 `tests/test_file_upload_security.py`，用 `git checkout --` 恢复后重放补丁，净损失为零但属真实事故；④ 一次 docker 输出把含口令的 `DATABASE_URL` 打进终端，后续脚本已加脱敏；⑤ 给同一子 Agent 重复发送过同一条纠偏消息。
- 工作树噪音（非本轮制造，未处置）：`tests/` 下 60+ 个未跟踪的 `browser_*.png/.cjs/.json` 是历史浏览器验收产物落在跟踪目录里；`chroma_db/*` 是被宿主侧跑测试/探针弄脏的跟踪二进制。两者都建议由你决定是 `git rm --cached` + 忽略，还是提交，我没有动。

### 13.8 口径

- 容器门 24/0 + 两轮浏览器端到端 + run11/run12 定点实证 = **「装得上、登得进、传得上、查得到、拒绝算拒绝」在部署栈上被验证过**；不等于生产可用：仍缺真实模型链路、Dataset/Artifact/会话历史落 PG、Chroma→PGVector、配置中心草稿-校验-发布-回滚、镜像 digest 锁定，且 13.6 第一条（管理员检索语义）未决时，开箱唯一账号的知识问答仍不可用。
