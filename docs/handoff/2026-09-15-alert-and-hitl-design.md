# 告警可读性与 HITL 挂起态 · 设计评审件（C 线 · C-3）

**性质**：设计评审件。**本文件是本批唯一的产出**——R1 / R13 / R14 三项都含权限语义决策，先审方案再放码，因此本轮未改动任何 `.py`、未新建 `migrations/*.sql`、未碰 `frontend/**` 与 `scripts/**`。文中出现的"改哪个函数""建议 0008"均为**待批提案**，不是已完成的工作。
**取证基线**：工作树 HEAD `f29ec37`（`git log --oneline -1` 亲验），开工时点 `app/**` 与 `migrations/**` 零未提交改动（`git status --porcelain -- app tests docs migrations scripts` 只报 `?? docs/screenshots/`）。**收工复跑同一条命令时，`tests/` 下多出四个脏文件**（`test_data_file_catalog.py`、`test_frontend_login_policy.py`、`test_frontend_request_cancel.py`、`test_frontend_upload_auth.py`）——那是总控认领的合并债正在改，不属本线，本线一件未碰；`git diff --stat -- app migrations` 为空，即**本件确实零代码改动**。
**行号口径**：下列每一处 `file:line` 都是本轮 `rg -n` / 逐行读源码得到的，引用前先读过该行。

**总控复核（2026-09-15 18:4x，`d6dc911` 之后）**：对本件 8 处吃重证据做了独立抽查，**7 处逐字节命中**
——`alerts.py:96/:99/:101-102/:105-106`、`alerts.py:402` 的 `LIMIT 100`、`alerts.py:291` 只 INSERT 三列、
`alerts.py:76-83` 六列 DDL 确无归属列、`permissions.py:13`（staff 无 `alerts:manage`）/`:14`（manager 有）、
`policy.py:70` 为 `visibility` 在 `policy.py` 的**唯一**命中（实测 1 次）、`policy.py:157-158`、
`chat.py:888`/`:1192` 两处 `run_in_executor` **确实丢弃 future**、`orchestrator.py` 全文 `cancel` **0 命中**、
`orchestrator.py:223`、`intelligence.py:73/:82`、`migrations/manifest.json` 实测只列 `0001`–`0007`。
**1 处行号偏移已就地订正**：`authorization_decision(...)` 在 `alerts.py:104`，不是 `:103`
（`:103` 是 401 那行）；§2.1 与 §4.4 两处已改，语义结论不受影响。
本件的 R1/R13/R14/Q4 结论经复核后**由总控采信**，批准记录见 `docs/handoff/2026-09-15-orchestration-board.md` §4F。

## 0. 结论速览

| 项 | 一句话推荐 |
|---|---|
| **R1** | 推荐 **(c) 保持 403 + 前端显式"无权限"**，且把 R1 的范围从"员工"订正为"仅 `staff` 角色"（`manager` 已经能看）；**(a)/(b) 在当前 schema 下无法安全实现**——`alerts` 表没有任何归属列，放开读权限等于把全公司告警发给每个登录者，必须先有 migration。 |
| **R13** | 挂起态目前**只活在 LangGraph checkpoint 里**，`check_interrupt(thread_id)` 需要预先知道 `thread_id` 且无枚举能力，所以"列挂起待办"不可能靠读现状拼出来。推荐**把 R13 与 R12 当同一个状态机做**：新增 `pending_approvals`（建议 `migrations/0008_pending_approvals.sql`）+ `GET /hitl/pending`，并让"取消"真正终止 executor 线程，否则面板列出的是仍在跑的假挂起。 |
| **R14** | 推荐**后端加只读聚合端点**，不推荐前端自己拉 `/documents`+`/data-files`+`/sessions` 现算——后者会把三套可见性判据复制进浏览器，且现成列表端点全部带行数上限（`/alerts` `LIMIT 100`、`/artifacts` `MAX_LIST_LIMIT = 100`），客户端算出来的"总数"必然是错的。 |
| **Q4** | `visibility` **确实从不参与判定**（全 `app/common/policy.py` 只在 `:70` 被搬运一次），标**语义待定**，本轮不改码。附带发现：跨部门 `delete` 回的是 `permission_denied`（`policy.py:209-210`）而不是 `department_scope_denied`，与 `visibility` 一起进同一次语义评审更省事。 |

## 1. 先订正一条开工前提

派单第 3 点写"含权限口径：空部门 admin 现在问不了知识库"。**这条已过期**，e2（`719f29c`）之后：

- 检索链已放行：`app/rag/filters.py:86-95`，管理员命中即去掉 department 谓词，`reason_code="administrator_scope"`，与 `app/common/policy.py:197-202` 同名同义。无部门 admin **现在可以问知识库**。
- 仍然拒绝无部门 admin 的是**写入/注册侧**，不是读侧：`app/storage/datasets.py:135-136`（`dataset owner must have a department scope`）、`app/storage/artifacts.py:175-176`（同一措辞），以及把它们提前到 HTTP 层的 `app/api/v1/data.py:346-354` `_require_artifact_scope`（调用点 `:362` / `:400`）。
- 影响本文件的程度：R14 讨论的是"总览页读聚合"，走的是读侧，因此**不受该前提影响**；R13 的挂起待办面板要写库（谁批准的、属于哪个会话），owner 取的是 `principal.user_id` 而非部门，同样**不受影响**。所以下文不再依赖这条前提。

## 2. R1 · 员工到底该不该看告警

### 2.1 403 的完整链路（五道门同一个判据）

| 环节 | 证据 |
|---|---|
| 判据函数 | `app/api/v1/alerts.py:96` `_require_alert_management`；`:99` `request is None` 直接返回 `None`（离线/内部调用后门）；`:101-102` 无 principal → 401 `authentication_required`；`:104` `authorization_decision(principal, None, action=ACTION_MANAGE_ALERTS)`；`:105-106` 拒绝 → 403 `detail=decision.reason_code` |
| 被它保护的五个路由 | `:341` `POST /alerts/rules`、`:370` `GET /alerts/rules`、`:381` `DELETE /alerts/rules/{rule_id}`、`:395` `GET /alerts`、`:406` `POST /alerts/check` |
| 拒绝时的码从哪来 | `app/common/policy.py:157-158`：`if action not in permissions: return _decision(False, "permission_denied")` —— 403 的 `permission_denied` 就是这一行，与部门、密级、`visibility` 都无关 |
| 权限定义 | `app/common/permissions.py:10` `ACTION_MANAGE_ALERTS = "alerts:manage"`；`:13` staff = {view, upload, analyze}（**无 alerts:manage**）；`:14` manager **有**；`:15` admin 有；`:21` 未知角色回落 staff |

**订正派单的一处口径**：R1 说"员工 403"是对的，但**`manager` 不 403**——`permissions.py:14` 已含 `alerts:manage`，而 `alerts.py:103` 传的是 `resource=None`，`policy.py:159-162` 在无资源时只要 action 命中权限就放行。所以缺口是"`staff` 连只读都没有"，不是"非管理员都看不到"。这直接影响取舍：任何"给员工开只读"的设计都必须保持 manager/admin 行为不变（`tests/test_alert_route_authorization.py:30` 已钉住 manager 可管理，`:7` 已钉住 staff 不可管理规则）。

### 2.2 致命前提：`alerts` 行里没有归属

`GET /alerts` 的返回是 `SELECT * FROM alerts ORDER BY id DESC LIMIT 100`（`app/api/v1/alerts.py:402`），而表结构两处一致且**都没有归属列**：

- 运行期 DDL：`app/api/v1/alerts.py:76-83` → `id, rule_id, message, ai_analysis, read, created_at`
- 生产 migration：`migrations/0003_legacy_runtime_tables.sql:62-68` → 同六列，`rule_id` 外键 `ON DELETE SET NULL`（`:64`）

更关键的是**写路径把归属丢了**：`app/api/v1/alerts.py:291` 只 `INSERT INTO alerts (rule_id, message, ai_analysis)`，而 `msg` 的构造（`:278`）只含"规则名 + 指标 + 数值 + 阈值"，**连数据集名都没进去**。数据集名其实在同一个循环里就在作用域内（`:273` `for dataset_name, df in dfs`），但只用于去重日志（`:281`）就被丢弃了。

结论：**"本部门可读"当前无据可依**——一行告警无法回答"它是哪个数据集/哪个部门产生的"。

### 2.3 三个方案的取舍

| 方案 | 要改的函数（提案，未实施） | `department` 会不会泄露给无权限者 | 评 |
|---|---|---|---|
| **(a) 读权限降为"本部门可读"，写仍管理员** | 拆 `_require_alert_management`（`alerts.py:96`）为读/写两个门；`GET /alerts`（`:395`）与 `GET /alerts/rules`（`:370`）改判 `ACTION_VIEW`；`SELECT * FROM alerts`（`:402`）加归属过滤；`evaluate_all` 的 INSERT（`:291`）加归属列；`_ensure()` DDL（`:76-83`）+ 新 migration | **会**，如果不做 migration 的话。`message` 文本本身不含部门字样，所以泄露的不是"部门"这个字符串，而是**"某部门的某指标越线了"这一事实**——`:402` 无过滤地把全表最新 100 行交给任何过门者。当前唯一的隔离就是那道 403 | 语义最正，但**必须先有 migration**，否则 (a) = 主动造泄漏。落地成本最高 |
| **(b) 新增员工只读端点**（如 `GET /alerts/mine`） | 新路由 + 与 (a) 相同的归属过滤；现有五个门（`:341/:370/:381/:395/:406`）**一字不动** | **不会额外泄露**（老门还在），但**新端点若不加过滤就等同于 (a) 的漏洞**；且要防"两个端点两套判据"漂移 | 兼容性最好（`GET /alerts` 语义不变），但仍受 2.2 所限：没有归属列就筛不出"我的" |
| **(c) 保持 403，前端明确显示"无权限"而非空白** | `app/**` 零改动。要动的是前端把 403 与"空列表"分开渲染 | **不会**。这是三案中唯一当前就不引入泄露面的 | 不是回避问题：它把"需要 migration + 语义评审"的改动挡在门外，同时立刻消除"面板空白 = 坏了"的误判。`permission_denied` 已是 canonical 码（`app/common/policy.py:158` 产出），前端可直接映射文案 |

**推荐**：**先 (c)**，(a) 排在 migration 之后。(b) 只在"必须让 staff 看到点什么"成为硬需求时才做，且要与 (a) 共用同一个归属列，不另起判据。
**反对现在就上 (a)/(b) 的理由**：`alerts` 表 0 列可过滤 + 写路径 0 处归属（2.2），意味着此时放开读权限，效果必然是"放开为全公司可读"。这与 e2 那种"跨部门全库可读"的**有意**放宽不同——这里没有任何裁定支撑它。

### 2.4 `alerts` 0 行会让验收变空跑吗——会，而且真数据只有两个来源

- **唯一自动生产者**是调度器：`app/scheduler/jobs.py:16-17`（每 5 分钟 `evaluate_all`）+ `:18-19`（每日 8:00 `daily_report`）。进程内启动受 `app/main.py:167-175` 与 `_scheduler_enabled()`（`app/main.py:36`）控制，关掉时由独立 scheduler 进程负责（`app/main.py:171` 日志即此意）。
- **调度器的巡检没有身份**：`evaluate_all(principal=None)`（`alerts.py:245` 默认值）→ `_scan_data_files(None)`（`:220`）→ `:234-237` 三元式在 `principal is None` 时走 `_directory_data_files(root)`，**绕过登记表与策略**；只有带 principal 时（即 `POST /alerts/check`，`:406` → `:411` `evaluate_all(principal=principal, ...)`）才走 `_permitted_dataset_files`（`:186`，逐条 `ACTION_ANALYZE` + `require_resource_scope=True`，`:198-206`）。
  → 由此产生一条**必须记进设计的不对称**：5 分钟自动巡检覆盖 `DATA_DIR` 里**每个**数据文件（包括未登记、无归属、任何 staff 都读不到的文件），而手动"立即巡检"只覆盖调用者有权 analyze 的数据集。**先给 staff 开读权限、后补归属列**的顺序会正好把这条不对称暴露成事故。
- **`/insights/detect` 不产告警**：`app/api/v1/intelligence.py:82` 只对客户端传入的 `data.rows` 调 `detect_insights`（`:84`），既不读库也不写 `alerts`。派单里把它列为候选来源，可以排除。
- **验收要出真行需同时满足**：存在 `enabled` 规则（`:266`）＋ 该规则的 `metric` 列在某文件的 dataframe 里存在（`_metric_value` 取不到即 `continue`，`:274-276`）＋ 阈值命中（`:277`）。**模型不可用不会挡住写库**：`_ai_analysis`（`:129-141`）失败时返回 `""`（`:140-141`），INSERT 照做。但它在写路径上、每次触发都调一次 `_make_model(timeout=30)`（`:137`），所以真机验收一批命中会拖到分钟级——这是验收成本，不是正确性问题。
- 因此**任何 R1 验收都必须自带造数据步骤**（上传含规则指标列的数据集 + 建一条会命中的规则 + 调 `POST /alerts/check`），否则 0 行会让"改了没改"看起来一模一样。用 `POST /alerts/check` 而不是等调度器：前者带 principal，才会走 `_permitted_dataset_files` 这条与将来归属过滤同构的路。
- 摘要不回服务端路径：`:239` 只放 `path.name`，`:219` docstring 明说"不含服务端路径的扫描摘要"，`/alerts/check` 的 `scan_scope`（`:412`）因此不构成路径泄露。
## 3. R13 · 「挂起 HITL 待办」端点，与 R12 是同一个状态机

### 3.1 挂起态到底存在哪：只活在 checkpoint 里

| 事实 | 证据 |
|---|---|
| 唯一真相是图的 `state.next` | `app/agents/orchestrator.py:1017` `def check_interrupt(thread_id: str)`；`:1018-1019` 用**单个** `config` 调 `multi_agent_graph.get_state(config)`；`:1020` 看 `state.next`；`:1021` 只保留落在白名单里的节点；`:1022-1026` 返回 `{pending, labels}` |
| 挂起集合是编译期常量 | `app/agents/orchestrator.py:223` `_HITL_PARKED = ("chart", "export")`；`:225` `_HITL_LABELS`；`:626` `interrupt_before=list(_HITL_PARKED)` |
| **没有任何枚举能力** | `check_interrupt` 的入参就是 `thread_id`（`:1017`），必须先知道是哪个会话才能问"它挂起没有"。全仓没有 `list_interrupts`/等价物 |
| 能否跨进程重启恢复 | **取决于 checkpointer**：`app/agents/orchestrator.py:57` `_make_checkpointer()`，`:61` 2 秒探活成功后 `:63-65` 建 `PostgresSaver` 并 `cp.setup()` → 挂起态可跨重启；探活失败则 `:68-71` 降级 `MemorySaver` → **重启即全丢**。选择在 import 期一次性定死（`:74` `_checkpointer = _make_checkpointer()`） |
| checkpoint 表不在受控 migration 里 | `migrations/manifest.json` 只有 `0001`–`0007`；checkpoint 表由 `orchestrator.py:65` 的 `cp.setup()` 在运行期自建，与 `migrations/README.md:3`（"Runtime imports must not create tables"）的精神相悖。属既有状况，本件只登记不处置 |
| 服务端**没有**把"挂起"写进任何持久层 | `awaiting_hitl` 全仓只出现三处：`app/api/v1/chat.py:1037`（SSE `request.completed` 的 data 字段）、`frontend/src/lib/sessions.js:288`（前端把它存进内存态）、`tests/test_routing_intent_and_terminal_state.py:106`（断言的也就是那个 SSE 字段）。**没有一行服务端代码把挂起态写进库或文件** |
| 会话消息表里也没有 | `app/api/v1/chat.py:380-403` `_save_message` 只写 `role/content/steps/created_at`（INSERT 在 `:393`），`steps` 是步骤日志，不含"在哪个节点前 park 了" |
| 但**归属是有的**，不必新造 | `/ask` 每轮都记 owner：`app/api/v1/chat.py:755` `thread_id = request.session_id or uuid.uuid4().hex`、`:764` `session_registry.bind(thread_id, request_principal)`、`:767` `_ensure_session(thread_id, str(request_principal.user_id))`；PG 侧 `migrations/0003_legacy_runtime_tables.sql:14-19`（`sessions.user_id TEXT NOT NULL`）+ `:26` `(user_id, created_at DESC)` 索引；文件侧 `app/storage/sessions.py:90-91`（`SESSION_REGISTRY_PATH`，默认 `./data/.session-metadata.json`）、`app/storage/sessions.py:85` `is_owned_by` |

### 3.2 一条会让审批面板"合法地造假"的陷阱

`/queue/*` 那一组端点的词汇表里就有 `pending`：`app/api/v1/chat.py:1932-1933` `queue.redis.lrange(queue.pending_key, ...)`、`:1906` `GET /queue/status/{request_id}`、`:1943` `POST /queue/{request_id}/cancel`、`:1964` `GET /queue/stats`。**那是 Redis 请求排队队列，与 HITL 挂起无关**。若"挂起待办"面板误接这组端点，显示出来的是"排队等开跑的请求"，而不是"跑了一半等你批准图表/导出的会话"——从 UI 上看都像"待办列表"，这是最容易造假成功的地方。写文档时点名，是为了让评审时一眼能否掉这条捷径。

### 3.3 R12 让「挂起」这个词当前是假的（必须先修，否则面板说谎）

| 环节 | 证据 |
|---|---|
| 图跑在 executor 线程 | `app/api/v1/chat.py:18` `_executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="ezn_")`；`/ask` 侧 `:888` `loop.run_in_executor(_executor, _run)`；`/approve` 侧 `:1192` 同型 |
| **future 被丢弃** | `:888` 与 `:1192` 两处都不接返回值 → 没有任何句柄可用于取消，工作线程必然跑到 `_run` 结束 |
| 取消只中断了 SSE 消费循环 | `/ask` 取消分支 `:921-933`：`if cancel_event.is_set()` → yield `request.cancelled` + legacy `cancelled` → `break`；`/approve` `:1203-1207` 同型（yield + break）。**break 的是生成器，不是工作线程** |
| 取消标记只存在于 HTTP 层 | `app/api/v1/chat.py:85-89` `register_request`（`_REQUESTS[session_id] = threading.Event()`）、`:92-105` `cancel_request`（`:95-98` docstring 明说"marker is armed either way"、返回值只在真的 in-flight 时才 `True`）；取消入口 `:741-745` `POST /ask/{session_id}/cancel`（`:744` 先 `_authorize_session_request` 证明归属） |
| **工作线程侧完全没有取消概念** | `rg -c "cancel" app/agents/orchestrator.py` → **0 命中**；`run_with_stream` 形参（`app/agents/orchestrator.py:814-823`）里没有任何取消/event/token 钩子 |

后果：用户点"取消"或关掉页面后，图仍会继续跑完，`chart`/`export` 一旦被批准路径放行就会真的落盘产物。**在这个事实被修好之前上线"挂起待办列表"，列出的必然是仍然在跑、或已经被用户放弃的假挂起**。因此 R13 与 R12 必须一起设计。

### 3.4 建议的「挂起」持久化形状（**待批，本件不写码、不建 migration**）

把一次挂起看成一行有终态的记录，而不是一个可查询的瞬时状态：

| 字段 | 来源（现有证据） |
|---|---|
| `session_id` | 与 `thread_id` 同值（`app/api/v1/chat.py:755`），故**一列即可**，但要在 COMMENT 里写明这层等价关系来自哪 |
| `owner_user_id` | `principal.user_id`（`app/api/v1/chat.py:767` 已有同款写入）；权限判定即可 JOIN `sessions.user_id`（`migrations/0003_legacy_runtime_tables.sql:14-19`） |
| `parked_steps` | `check_interrupt(...)["pending"]`，其取值域受 `app/agents/orchestrator.py:223` 白名单约束 |
| `request_id` / `trace_id` | SSE 已在携带（`app/api/v1/chat.py:1027-1029`），落库后可反查 trace |
| `status` | `awaiting` / `resumed` / `refused` / `abandoned` / `stale` 五态。`refused` 语义**已存在**：`app/agents/orchestrator.py:987` 取 `declined`、`:989` 回 "已取消，未执行：" + labels，正是"拒绝=不执行这些节点" |
| `created_at` / `decided_at` | 面板要排序、要过期清理 |

写入与清理点（全部是**提案**）：

1. **写 `awaiting`**：`/ask` 的 `if intr:` 分支处（`app/api/v1/chat.py:1021`），与 SSE `event: hitl` 同源同时刻，避免出现"事件发了、表里没写"的分叉。
2. **改 `resumed`/`refused`**：`/approve`（`app/api/v1/chat.py:1164`）结束时，按 `request.approved` 分派。
3. **改 `abandoned`**：R12 修好之后，`cancel_request` 真正终止工作线程时落这一态。**R12 未修前不要实现这一步**，否则会把"其实跑完了"的会话标成 abandoned，比现在还糟。
4. **列端点必须自带复核**：`GET /hitl/pending` 在返回前对每条 `awaiting` 调 `check_interrupt(session_id)`（`app/agents/orchestrator.py:1017`）；实不符即就地标 `stale` 并排除。这是唯一能让"表"与"图"两个真相长期一致的保险，也顺带消化了 `MemorySaver` 降级（`app/agents/orchestrator.py:69-71`）导致重启后图里啥都没有的情形。
5. **migration 命名**：`migrations/0008_pending_approvals.sql`，按 `migrations/README.md:7-8`（`NNNN_descriptive_name.sql` + 必须在 `manifest.json` 里带 SHA-256，缺失/改动一律 fail-closed）。**本轮不建**：派单禁止，且它需要评审。生产期读路径建议沿用 `app/api/v1/alerts.py:58-62` 那种"缺表即显式报错"的口径，不要再加一层静默降级到内存。

### 3.5 端点与权限口径（不新增语义）

- 列表只回自己的挂起项：归属判定复用 `app/storage/sessions.py:85` `is_owned_by`，与 `/approve` 现有的 `_authorize_session_request`（`app/api/v1/chat.py:213-217`）**同一个谓词**。
- 访问他人会话按现仓既有惯例回 **404 `resource_not_found`**（`app/api/v1/chat.py:216`），**不是 403**——这条是本仓对"会话属主"的既有选择，列端点照抄即可，别引入第二种口径。
- **批准动作不改**：仍走 `/approve`（`app/api/v1/chat.py:1164`）与 `ACTION_APPROVE`（`app/common/permissions.py:14`/`:15`）。列挂起是"读自己的东西"，不构成新的权限档，因此 R13 不需要像 R1 那样做语义评审——**它需要的是状态机设计评审**。

**推荐**：R12 → R13 顺序做，且 R13 的"列端点"必须与第 4 条的复核同批落地。若总控要拆票，建议拆成 `R12 协同退出`（改 `run_with_stream`/`_run` 与两处 SSE 循环）与 `R13 挂起表 + 列表端点`（新 migration + 新读路由），两条各自可回退。
## 4. R14 · 总览页接真数据

### 4.1 现状：两个端点确实不查库

| 事实 | 证据 |
|---|---|
| `POST /dashboard` 吃客户端 rows | `app/api/v1/intelligence.py:73` 路由，`:75` `_authorized(request, ACTION_ANALYZE, "dashboard")`，`:76` `build_dashboard(data.rows, data.insights)`，`:77-78` 只补 `generated_for` / `row_count` |
| 输入模型自证 | `app/api/v1/intelligence.py:30-32` `class DashboardRequest: rows: list[dict] = []; insights: list[dict] = []`；`:35-36` `InsightsRequest` 同样只有 `rows` |
| `POST /insights/detect` 同样不查库 | `app/api/v1/intelligence.py:82` 路由，`:85` `detect_insights(data.rows)` |
| 聚合逻辑纯内存 | `app/dashboard/service.py:1` `def build_dashboard(rows, insights)`；`:4-12` 对传入的每行按 `row["metric"]` / `row["department"]` 累加；`:15` 返回 `{metrics, departments, insights}` |
| 权限档本身没坏 | `app/api/v1/intelligence.py:62-70` `_authorized` → `authorization_decision(principal, None, action=...)`（`:66`）；staff/manager/admin 三角色都有 `analyze`（`app/common/permissions.py:13`/`:14`/`:15`），所以谁都调得通。**问题不是 403，是喂进去的数据是客户端造的** |

**一个必须点名的同名陷阱**：`app/dashboard/service.py:6` 的 `department` 是**被喂进来的那行业务数据里的一个列名**（经营数据的部门维度），与登录者 `principal.department`（权限域）不是同一个东西。后端聚合端点如果用调用者的部门去过滤业务数据，会把"按部门维度统计"偷偷变成"只看本部门数据"。聚合端点因此只按**可见性**过滤资源行，不改统计维度口径。

### 4.2 路线 A：后端加查库聚合端点（**推荐**）

1. **可见性判据只有一处，且已经在服务端**。现成列表端点各自都已过滤：`/data-files` `app/api/v1/data.py:131-138`（逐条 `authorization_decision(..., require_resource_scope=True)`，不允许就 `continue`）、`/documents/catalog` `app/api/v1/chat.py:1695-1697` 经 `_visible_document_rows`（`app/api/v1/chat.py:232`）、`/sessions` `app/api/v1/chat.py:1282-1290`（`:1289` `is_owned_by`）、`/artifacts`（R2 新增，`app/api/v1/artifacts.py:172`/`:187`）。前端"现算"要么在浏览器里复刻这四套判据（做不到：判据要读 PG 行与 principal 密级），要么退化成"拿列表长度当统计"。
2. **列表端点全都有行数上限，长度不是总数**：`/alerts` `LIMIT 100`（`app/api/v1/alerts.py:402`）、`/artifacts` `DEFAULT_LIST_LIMIT = 20` / `MAX_LIST_LIMIT = 100`（`app/api/v1/artifacts.py:147-148`，夹逼于 `:187`）。数据一多，客户端算出的"总数"必然静默偏小——这是最坏的一类错：它看起来是对的。
3. **密级/部门信息不该下发给浏览器再让它过滤**：判据依赖 `principal.clearance`（`app/common/policy.py:188-189`）与部门交集（`:191-213`）。把这些交给前端过滤等于把策略实现复制一份到不受控环境，将来 `policy.py` 一改，前端必漏改。
4. 聚合要的是 SQL 层 `GROUP BY` / `COUNT`（文档数、数据集数、会话数、未读告警数），前端拿不到未截断的集合，根本算不出来。

### 4.3 路线 B：前端自己拉三个列表现算（**不推荐**）

只有在"总览页只要三四个数字，且接受 100 条上限"时勉强可用；但那个前提下正确做法仍是给每个列表端点补 `total` 字段——依然是后端改动。所以 B 声称的"省事后端"是假的，它只是把判据漂移风险从后端搬到了前端。

### 4.4 推荐与一处与 R1 的耦合（必须同批决策）

**推荐 A**：新增只读聚合端点（建议 `GET /dashboard/summary`：无 body、不接 rows），逐源复用 4.2 里点名的**同一批**过滤函数，权限沿用 `ACTION_ANALYZE`（`app/api/v1/intelligence.py:66`），不新增权限档。

**耦合点**：总览页想显示"告警数"，而 R1 的结论是当前 `staff` 读 `alerts` 必须 403（§2）。若聚合端点无条件把告警计数放进去，它就成了 R1 的后门——用一次 `ACTION_ANALYZE` 绕过了 `ACTION_MANAGE_ALERTS`（`app/api/v1/alerts.py:104`）。因此设计上有两个可批的版本：

- **A1（保守，推荐）**：聚合端点里"告警数"这一项**再过一次** `_require_alert_management` 的判据（`app/api/v1/alerts.py:96-108`），不过就把该字段整个省略（不回 0，回 0 也是假数据）。
- **A2**：总览页先不含告警数，等 R1 的 migration 落了再加。

**无论 A1/A2，都不许"因为要接总览"而顺手放开 `alerts` 的读权限。**

## 5. Q4 · `visibility` 从不参与判定（语义待定，本轮不改码）

| 事实 | 证据 |
|---|---|
| 全仓唯一读点只是"搬运" | `app/common/policy.py:62` `_resource_attributes(...)` 在 `:70` 把 `resource.visibility` 放进属性字典。`rg -n "visibility" app/common/policy.py` 的**全部命中就是这一行** |
| 判定函数不读它 | `app/common/policy.py:127` `def authorization_decision(...)`：依次只看 owner（`:143`、`:149-155`）、action∈permissions（`:157-158`）、无资源时的 scope 要求（`:159-162`）、legacy 无主文档（`:171-175`）、classification/department 元数据齐不齐（`:178-183`）、密级（`:188-189`）、部门交集（`:191-213`）、admin 放行（`:197-202`）。**没有一处出现 `visibility`** |
| 字段真实存在且有默认值 | `app/agents/contracts.py:55` `visibility: str = "private"` |
| 现状后果 | 标 `public` 不会让资源对同部门之外的人多可见一分（仍受 classification/department 约束）；标 `private` 也不会比同部门同事更少可见。**它当前是纯装饰字段**，但它已随审计 scope 落盘（`app/common/policy.py:70`），一旦让它参与判定，审计记录形状与既有可见集合同时改变 |
| 相邻的既有断言（说明这不是新发现） | `tests/test_artifact_list.py`、`tests/test_resource_delete_cascade.py` 里按现有判据钉住的行为（R2/R8 时写的）。改 `visibility` 语义会牵动这两支，需连带评审 |

**附带发现（建议与 `visibility` 同一次评审）**：跨部门的**控制类动作**（`upload`/`export`/`approve`/`delete`，见 `app/common/policy.py:42` `_CONTROLLING_ACTIONS`）在部门不交集时回的是 `permission_denied`（`:209-210`），而非控制类才回 `department_scope_denied`（`:211`）。这正是我 R8 时选"按现仓惯例回 403 + 策略自带 reason"的依据（`app/api/v1/data.py:69-91` `_authorized_dataset` 把 `decision.reason_code` 原样作 detail），但两个 reason 的分工本身值得评审：审计里"越权"与"跨部门"被并成了同一个码，事后追查分不出是哪一种。

**处置**：本项**标语义待定，不改码**。理由是 `visibility` 一旦参与判定，§2（谁能看告警）与 §4（聚合端点该看到多少）的可见集合会同时变化，三件事分三批改必然互相打脸。
## 6. 本件没做与没验证的（诚实清单）

- **没改任何代码**：本批按派单只产出这一个文件。未跑 pytest（无代码变更可验），未起服务、未连库、未执行任何 `docker` 子命令、未新建 `migrations/*.sql`。
- **"PG `alerts` 0 行"我**没有**实测**：派单禁止连真库，我只 `rg` 了 DDL 与 INSERT。所以上文全部论证都**不依赖行数**——即使表里有几百行，§2.2"无归属列故无法做部门级过滤"照样成立。
- **§3.1"没有任何端点能列出挂起动作"是静态取证**，依据是 `check_interrupt` 的签名（`app/agents/orchestrator.py:1017`）、`app/api/v1/chat.py` 路由清单（`/approve` `:1164`、`/queue/*` `:1906`/`:1943`/`:1964`）与 `awaiting_hitl` 全仓三处命中。**未在运行时穷尽**其它可能的枚举路径（例如直接对 langgraph state API 的第三方调用）。
- **checkpoint 表的实际集合未核对**：只知道它由 `app/agents/orchestrator.py:65` 的 `cp.setup()` 在运行期创建、且不在 `migrations/manifest.json`（该文件实测只列 `0001`–`0007`）。若采纳 §3.4 的建议，真机验收时要顺便确认 `PostgresSaver` 建的表是否与 `0008` 存在命名冲突。
- **§2.4 的"一批命中会拖到分钟级"是从 `timeout=30`（`app/api/v1/alerts.py:137`）推的量级，不是实测耗时**。

## 7. 建议的批拆顺序（供总控排期）

1. **R1 只做 (c)**：`app/**` 零改动，前端把 403 与空列表分开渲染。可与"给 `/alerts` 补归属列的 migration 设计"并行评审，但**不许先放读权限**。
2. **R12 单独成批**：协同退出（工作线程侧要能观察取消）。它是 R13 的前置。
3. **R13 两批**：`0008_pending_approvals.sql` + 写入/复核 → 再 `GET /hitl/pending`。
4. **R14 走 A1**：`GET /dashboard/summary`，告警计数复用 `_require_alert_management` 判据、不过则省略字段（`app/api/v1/alerts.py:96-108`）。
5. **Q4 + reason 码分工**：`visibility` 与 `permission_denied`/`department_scope_denied`（`app/common/policy.py:209-211`）合一次语义评审，放在 R1/R14 之后。

## 8. 证据索引（本件引用的全部 `file:line`）

**`app/api/v1/alerts.py`** — `:58-62`（生产期缺表即 `RuntimeError`）、`:76-83`（运行期 alerts DDL）、`:96`/`:99`/`:101-102`/`:103`/`:105-106`（`_require_alert_management`）、`:129-141`（`_ai_analysis`，`:137` 模型 30s、`:140-141` 失败回 `""`）、`:186`/`:198-206`（`_permitted_dataset_files`）、`:219`（摘要 docstring）、`:220`（`_scan_data_files`）、`:234-237`（principal=None 走目录扫描）、`:239`（只回文件名）、`:245`（`evaluate_all` 默认 principal）、`:266`（enabled 规则）、`:273`（`dataset_name` 在作用域内）、`:274-276`（指标缺失即跳过）、`:277`（命中判定）、`:278`（msg 内容）、`:281`（去重日志）、`:287`（AI 归因）、`:291`（INSERT 三列）、`:317`/`:321`（daily_report 同样无 principal）、`:341`/`:370`/`:381`/`:395`/`:402`/`:406`/`:411`/`:412`（五个路由与其查询）
**`app/common/policy.py`** — `:42`（`_CONTROLLING_ACTIONS`）、`:62`/`:70`（`visibility` 唯一读点）、`:93`/`:98`/`:107`（`_is_administrator` 与公开 `is_administrator`）、`:127`（`authorization_decision`）、`:143`、`:149-155`（owner_match）、`:157-158`（permission_denied）、`:159-162`（resource None）、`:171-175`（legacy_ownership）、`:178-183`（scope 缺失）、`:188-189`（clearance）、`:191-195`（部门交集准备）、`:197-202`（administrator_scope）、`:204-207`、`:209-211`（两码分工）、`:213`（department_scope_match）
**`app/common/permissions.py`** — `:10`、`:13`、`:14`、`:15`、`:21`
**`app/agents/orchestrator.py`** — `:57-71`（`_make_checkpointer`，`:63-65` PG / `:68-71` MemorySaver，`:65` `cp.setup()`）、`:74`（import 期定死）、`:223`/`:225`（`_HITL_PARKED` / `_HITL_LABELS`）、`:626`（`interrupt_before`）、`:814-823`（`run_with_stream` 形参，无取消钩子）、`:949`（`run_interrupt_stream`）、`:987`/`:989`（拒绝路径）、`:1017-1026`（`check_interrupt`）；**`rg -c "cancel"` 命中 0**
**`app/api/v1/chat.py`** — `:18`（executor）、`:85-89`（`register_request`）、`:92-105`（`cancel_request`）、`:213-217`（`_authorize_session_request` → 404）、`:232`（`_visible_document_rows`）、`:380-403`（`_save_message`，`:393` INSERT）、`:741-745`（cancel 路由）、`:753`/`:755`/`:764`/`:767`（`/ask` 与其 owner 写入）、`:867`/`:888`/`:921-933`（`/ask` 的 executor 与取消分支）、`:973-976`（`check_interrupt` 调用点）、`:1021-1022`（`event: hitl`）、`:1027-1029`（trace ids）、`:1037-1038`（`awaiting_hitl`）、`:1164`/`:1168`/`:1174`/`:1192`/`:1203-1207`（`/approve` 同型）、`:1282-1290`（`/sessions`）、`:1682-1697`（`/documents` 与 catalog）、`:1906`/`:1932-1933`/`:1943`/`:1964`（Redis 队列，非 HITL）
**`app/api/v1/intelligence.py`** — `:30-32`、`:35-36`、`:62-70`、`:73-78`、`:82-85`
**`app/dashboard/service.py`** — `:1`、`:4-12`、`:15`（`:6` 业务维度 `department`）
**`app/storage/datasets.py`** `:113`/`:135-136`；**`app/storage/artifacts.py`** `:152`/`:175-176`；**`app/storage/sessions.py`** `:23-24`（JSON-backed）、`:32`/`:44`、`:61`/`:81`/`:85`、`:90-91`（registry 路径）
**`app/api/v1/data.py`** — `:43`（`OWNER_SCOPE_REQUIRED = "department_scope_required"`）、`:69-91`（`_authorized_dataset`）、`:121`/`:131-138`（列表过滤）、`:189`、`:234`（R8 DELETE）、`:346-354`（`_require_artifact_scope`）、`:362`/`:400`（调用点）
**`app/rag/filters.py`** — `:86-95`（e2 管理员分支，`reason_code="administrator_scope"`）、`:128-137`（只对该 reason 记审计）
**`app/main.py`** — `:36`（`_scheduler_enabled`）、`:167-175`（进程内调度器门）；**`app/scheduler/jobs.py`** — `:16-17`、`:18-19`
**`migrations/`** — `README.md:3`（导入期禁建表）、`:7-8`（命名与 manifest 校验 fail-closed）；`manifest.json`（实测 `0001`–`0007`）；`0003_legacy_runtime_tables.sql:14-19`/`:22-23`/`:26`（sessions+user_id+索引）、`:62-68`（alerts 无归属列）
**`app/agents/contracts.py`** — `:55`（`visibility: str = "private"`）
**`tests/`** — `test_alert_route_authorization.py:7`（staff 不可管理规则）、`:30`（manager 可）、`test_routing_intent_and_terminal_state.py:106`（断言的是 SSE 字段，非持久态）
**`frontend/src/lib/sessions.js`** — `:288`（`awaiting_hitl` 的唯一消费点，只存内存态）