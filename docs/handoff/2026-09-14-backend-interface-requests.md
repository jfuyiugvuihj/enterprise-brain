# 后端接口需求单（前端侧提出，2026-09-14）

提出方：本轮前端工作区走查（依据 `docs/frontend-workspace-audit-2026-09-14.md`，任务映射见 `docs/handoff/2026-09-14-frontend-workspace-fix-tasks.md`）

性质：只提接口契约与验收断言，不要求本单提出人改任何 `app/**` 文件；也未要求改动任何现有行为，除 R1 明确标注的权限语义外

引用口径：**本单全部用符号名、路由、事件名描述**。后端正在被并发编辑，任何行号都会失效
前置约束：SSE 事件冻结与下线前置条件见 `docs/api/contract-v1.md` 的 SSE Event Deprecation Policy 一节，R3 必须遵守

---

## R1 员工级异常读取（优先级最高，阻塞前端 F5b 与总览真实化）

**用户场景**：普通员工登录后要在总览看到“本公司当前有哪些经营异常”，并进入异常列表处理。这是侧栏“洞察”唯一诚实的落地形态。

**当前事实**：

- `app/api/v1/alerts.py` 的 `GET /alerts`、`GET /alerts/rules`、`POST /alerts/check` 都调用 `_require_alert_management()`，要求的是 `alerts:manage`（常量 `ACTION_MANAGE_ALERTS`）。普通员工三个调用全部 403。
- 只有写规则用这个权限是合理的；**读列表被同一权限挡住**，导致“盯异常”只能给管理员看。
- 更麻烦的是数据模型：migrations 中 `alerts` 表只有 `id, rule_id, message, ai_analysis, read, created_at`，`alert_rules` 只有 `id, name, metric, op, threshold, enabled`。**两张表都没有 owner、department、classification 列**，所以直接放开 `resource:view` 等于让全体员工看到全公司告警。
- 而且不能放开：`evaluate_all()` 生成的 `message` 形如“规则名: 指标=数值 (op 阈值)”，数值来自某个数据集文件；`_scan_data_files(principal)` 已经按 principal 过滤可读数据集，因此**同一规则对不同人可能不该显示同一个数值**。现存告警没有记录它来自哪个数据集、算给谁看。

**请求（按方案 B 做，不要走方案 A 的捷径）**：

| 项 | 要求 |
|---|---|
| 迁移 | 给 `alerts` 增加可归属列：`owner_id`、`department_ids`（或等价的 scope 表达）、`classification`、`dataset_name`、`dedup_key`；沿用现有 migrations 风格，允许老行为 NULL 且 NULL 视为仅管理级可见 |
| 写入 | `evaluate_all()` 落库时写入上述归属列，值来自触发它的那次扫描上下文（principal 与数据集名），不得凭空造 |
| 读 | 新增员工侧只读列表：`GET /api/v1/alerts` 在 `resource:view` 下返回**按 principal 过滤后**的告警；保留一个管理级参数或端点用于查看全部（继续要求 `alerts:manage`） |
| 状态 | 新增 `POST /api/v1/alerts/{id}/read`（或 `PATCH` 带 `read` 字段），用于“已处理/已读”流转；`read` 列已存在但没有写入路由 |
| 写权限 | `POST /alerts/rules`、`DELETE /alerts/rules/{id}`、`POST /alerts/check` **保持** `alerts:manage` 不变 |
| 兼容 | 响应外层保持 `{ alerts: [...] }` 形态，前端已按此实现 |

**不要顺带做的事**：不要在本单里合并 insights 与 alerts 两套异常逻辑（`docs/handoff/2026-09-14-consolidated-fix-plan.md` 已记为待决项，合并前不要单边改动），本单只要读权限与归属列。

**验收断言（可用单测表达，本单提出人不负责运行）**：

1. 低权限用户对某数据集无读权限时，`GET /api/v1/alerts` 不返回由该数据集触发的告警行。
2. 同一用户调用 `GET /alerts/rules` 与 `POST /alerts/check` 仍是 403。
3. 标记已读后再次拉取，`read` 为真；未标记的行不受影响。
4. 老数据行（无归属列）对普通员工不可见，对管理员可见且带可辨识的降级标记。


---

## R2 产物列表 `GET /api/v1/artifacts`（对应 B-1，阻塞“交成果/报告历史”视图）

**场景**：用户要找回上周生成的报告和图表。现在只能靠对话气泡里的链接，链接一旦划走就再也找不到。

**当前事实**：`app/storage/artifacts.py` 的 `ArtifactRegistry` 只有 `register`、`get`、`get_active`、`soft_delete` 加私有 `_load`/`_save`（走 `build_persistence_adapter()`），**没有任何列举或查询方法**；`app/api/v1/artifacts.py` 只有 `/{id}/content` 与 `/{id}/download` 两个路由。已知每条记录的可见性信息都在 `ArtifactRecord.resource_scope` 上（owner、department_ids、classification、visibility、status、expires_at）。

**请求**：

- 给 registry 增加一个按 principal 过滤的查询方法，复用已有的 `authorization_decision`（与 `_authorized_artifact` 同一套判定，不要新写一套）。
- 路由 `GET /api/v1/artifacts?type=&limit=&cursor=`，响应条目直接用 `ArtifactRecord.public_payload()` 的现有字段（`artifact_id`、`artifact_type`、`content_url`、`download_url`、`expires_at`），再补 `created_at`、`filename`、`status`。
- 已过期与 `soft_delete` 的记录默认不返回；返回时不得泄露他人产物的 `content_url`（前端拿到 URL 也拿不到内容，但列表本身就不该出现别人的条目）。

**验收断言**：A 用户上传并导出报告后，B 用户调 `GET /api/v1/artifacts` 看不到 A 的条目；`type=chart` 与 `type=report` 能分别过滤；`expires_at` 已过的默认不出现。

---

## R3 `/ask` 的来源事件（对应 B-2，受 SSE 冻结约束）

**场景**：员工问“这个数字出自哪份文件”，答案旁边应能点开来源。现在流式回答完全没有来源，只有非流式的 `POST /chat` 内部把来源拼进文本。

**当前事实**：`/ask` 的两条通道都不发来源；`app/api/v1/chat.py` 里拼装 `sources` 的逻辑只在非流式 `POST /chat` 响应路径上。`/provenance/summary` **不能替代**：它要求调用方回传 `results`，响应里明确写 `provenance_source = client_provided`、`server_verified = False`，等于把可信度问题推给前端。

**请求（严格按契约的加性原则）**：

1. 在 `/ask` 上增发一个 canonical 事件，名字用契约里已有的 `retrieval.completed` 或 `evidence.available` 之一，载荷至少含 `source`、`version_id`、`locator`（文件+chunk 或行号）、`score_type`、`permission_checked`。
2. **同一提交里不得删除或改写 legacy 的 `step` / `text` / `hitl` / `done`**，见契约 Freeze rules 第 1、2 条。
3. 数据源用已有的 `retrieval_traces`，不要另起一套记录口径。
4. 检索为空或被权限裁掉时必须显式发 `reason`（例如 `no_hits`、`all_hits_filtered_by_permission`），不要静默省略事件——省略会被前端读成“没有来源信息”，而不是“没有可用来源”。

**验收断言**：一次文档问答能收到 1 个来源事件且字段完整；无权检索任何内容的用户收到 `reason` 而不是空流；legacy 事件序列与改动前逐字节一致。

---

## R4 文档解析状态（对应 B-3，阻塞真实上传进度）

**场景**：DocPanel 现在用定时器假造进度，用户不知道文件到底解析完没有。

**当前事实**：`GET /documents/catalog` 已经返回 `filename`、`version`、`classification`、`department`、`storage_path`、`created_at`，**没有** `size`、`parse_status`、`chunk_count`、`uploader`；`app/documents/catalog.py` 的 `record_document_version` 签名里也没有 principal，所以拿不到上传者（与 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 第 1 节的删除权限根因是同一条链）。

**请求**：`document_versions` 增列 `size_bytes`、`parse_status`（`pending`/`parsing`/`ready`/`failed`）、`chunk_count`、`owner_id`；`record_document_version` 接收 principal 并写入；catalog 响应原样带出。

**验收断言**：上传一个解析失败的文件，`parse_status` 为 `failed` 而不是消失；成功文件 `chunk_count` 与实际入库片段数一致；前端不再需要假进度条。

---

## R5 报销预审自动取标准（对应 B-8）

**场景**：现在的“审批”页要用户自己填制度标准，用户要么乱填要么去翻 PDF。而对话里已经有一条更聪明的路径：`app/agents/orchestrator.py` 的 `_approval_worker_node` 会从自然语言抽金额、检索制度、用 `app/approval/assistant.py` 的 `extract_standard` 从原文取最严限额。

**请求**：给 `POST /approval/precheck` 增加 `standard_source`（`explicit` 默认 / `auto_from_knowledge_base`）。取 `auto` 时复用 worker 已有的检索与抽取函数，响应额外返回 `standard_evidence`（来源文件 + 定位）与 `matched_expense_type`；**同时停止接受前端传入的 `department`**，一律取 principal 的部门。

**边界**：抽不到标准时保持现有的 `unknown` / “无法确认”语义，不得回落成 0 或默认阈值（`build_precheck` 现在就是这么诚实的，别改）。

**验收断言**：不给 `standard` 只给“住宿费 680”，`auto` 模式能返回从制度抽出的标准与出处；抽不到时 risk 为 `unknown` 且 `approved` 仍为 False；前端伪造 `department` 无效。

---

## R6 指标口径与日报两个只读端点（对应 B-5、B-6）

- **指标目录**：前端洞察/总览需要“可选的指标 + 口径”，现在只有 `POST /semantics/match`（按问题匹配单个指标）。最省事的方案是 `GET /api/v1/semantics/metrics`，直接返回 `app/semantics/registry.py` 里那份 `_METRIC_RULES` 加 `DEFINITION_VERSION`（代码表即可，不必等数据库）；如果要做进 `metric_definitions` 表，请连同 `docs/handoff/2026-09-14-consolidated-fix-plan.md` 第 104 行那条一起排，不要拆成两次改动。
- **日报**：`app/api/v1/alerts.py` 的 `daily_report()` 有实现但无路由。**注意**它内部会 `send_im_notification(...)`：做成 `GET` 路由时不能每次页面打开都推一次 IM。建议拆成“生成文本”和“推送”两个函数，`GET /api/v1/alerts/daily-report` 只生成，或加 `dry_run`/缓存参数。

---

## R7 本单明确不要求的项

| 项 | 为什么不要 |
|---|---|
| 审批工单模型（C-1） | 需要单独设计，不混在本单里 |
| insights 与 alerts 合并 | 已被 consolidated-fix-plan 标为“合并前不要单边改动” |
| 任何 legacy SSE 事件清理 | 契约 Freeze rules 第 1、2 条 |
| 图片用 cookie 或签名 query token 免 Authorization | 属于改动鉴权中间件，前端侧用带 token 取 blob 已可解决（见 F1） |

---

## 排序与影响

| 顺序 | 需求 | 阻塞的前端任务 | 规模 |
|---|---|---|---|
| 1 | R1 员工级告警读取 | F5b、总览真实化 | 迁移 + 两个路由 + 写入点 |
| 2 | R4 文档解析状态 | 真实上传进度 | 增列 + catalog 字段 |
| 3 | R6 指标目录（代码表版） | 洞察去手填阈值 | 一个只读路由 |
| 4 | R2 产物列表 | 交成果视图 | 查询方法 + 路由 |
| 5 | R3 来源事件 | 对话可信度展示 | 一个加性事件 |
| 6 | R5 预审自动标准 | 报销自查 | 参数 + 复用既有函数 |
| 7 | R6 日报端点 | 无 | 需先拆分推送副作用 |

前三项落地后，前端 F1-F6 才算完整闭环；R1 是唯一会改变**权限语义**的项，建议优先评审。

