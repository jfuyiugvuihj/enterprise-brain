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
