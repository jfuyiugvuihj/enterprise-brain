# 后端接口跟进单（前端线提出，2026-09-15）

**基线**：`c6c6009`（2026-09-15）。
**核对方式**：读工作树源码。核对时点（08:40）`app/**` 与 `migrations/**` 零未提交改动，因此下列结论即**已提交状态**的结论。
**递交时机**：等本轮 browser e2e 验收收口之后再递，不要中途插进正在跑的任务。

---

## 0. 先订正我昨天的一条误判

- ~~S7 缺 `migrations/0007_metric_definition_sync.sql`~~ —— **不是缺陷**。`metric_definitions` 自 `migrations/0002_execution_data_lineage.sql:72` 就存在，S7 复用现表，不需要新迁移。`definition_version` 已在 `app/semantics/contracts.py` 与 `/semantics/metrics` 暴露，provenance 告警语义也保留了（`app/semantics/registry.py` 的 `_TABLE_WARNING` / `_SEEDED_WARNING`，未伪装成已核对）。**S7 判为完成。**


> **🔴 本表基线为 09-15 的 `c6c6009`，部分行已过期。2026-09-17 在 `ec0f40b` 上复核实测订正如下，勿据此表重复派工**：
> **R2 已完成**（`GET /artifacts` = `app/api/v1/artifacts.py:168`）；**R8 已完成**（artifact DELETE = `artifacts.py:78`、数据集 DELETE = `app/api/v1/data.py:234`、幽灵表清理 = `app/documents/catalog.py:614-618`）；
> **R10 已完成**（`895ee18`）；**R13 已完成**（`GET /hitl/pending` = `app/api/v1/chat.py:1337`，`migrations/0008_pending_approvals.sql` 已存在）；**R1 按裁定 (c) 收口**（后端零改动、403 保持，前端 W7 `9d327d8` 已把「无权限」与「空列表」分开渲染 ⇒ 看板 §2 的 G4「staff 返回 200」这条判据本身作废）。
> **仍未落地**：R3 / R5（`standard_source` 在 `app/**` 0 命中）、R14（`app/api/v1/dashboard.py` 对 `department` 0 命中）、B-6、B-7。
> 性能与架构新单见本文 **§21（R25–R52）**，论据在 `docs/handoff/2026-09-17-perf-architecture-plan.md`。

## 1. 仍未落地的需求（按对前端的阻塞程度排序）

| # | 需求 | 现状证据 | 最小做法 | 阻塞的前端项 |
|---|---|---|---|---|
| **R1 / B-9** | 员工级告警读取 | `app/api/v1/alerts.py` 中 `_require_alert_management` 6 处、`ACTION_VIEW` 0 处 → `GET /alerts`、`GET /alerts/rules`、`POST /alerts/check` 对普通员工 403 | 把「读自己可见的告警」拆到 view 级；规则 CRUD 与 `check` 保持管理权限。**这是唯一改变权限语义的项，建议优先评审** | 「异常与告警」员工视图、总览真实告警计数 |
| R2 / B-1 | `GET /artifacts` 列表 | `app/api/v1/artifacts.py` 只有 `/{artifact_id}/content`、`/{artifact_id}/download`；`ArtifactRegistry` 只有 `register`/`get`/`get_active`/`soft_delete`，无查询 | 按 principal + 类型过滤的分页列表，元数据源 `.artifact-metadata.json` | 「交成果」视图 |
| R3 / B-2 | `/ask` 的 `sources` 事件 | `sources` 只在非流式路径内拼装（`app/api/v1/chat.py` L669-676），SSE 从不发 | 加一个 canonical `sources` 事件；**不得下线任何 legacy 事件名**（契约冻结规则） | 对话引用条、答案可信度 |
| R5 / B-8 | 预审自动取标准 | `standard_source` 全仓 0 命中；`department` 仍由前端传入并被服务端接受 | `ApprovalRequest` 增 `standard_source: auto`，复用 `_approval_worker_node` 的检索与抽取路径；**服务端忽略或拒绝前端传的 `department`**（现可冒任意部门出结论） | 「报销自查」可信度与权限边界 |
| B-6 | 日报路由 | `daily_report()` 仍是函数（`app/api/v1/alerts.py`），该文件路由只有 rules / alerts / check | 先拆推送副作用，再挂只读路由 | 无（可延后） |
| B-7 | 趋势聚合 | `/dashboard` 无时间序列输入，前端才被迫手写乘数线 | 一个最小聚合端点 | 总览趋势线。未落地前前端**不画趋势线**，画空态 |
| **R8 / B-10** | 数据集 / artifact 删除 API | 全仓 `router.delete` 只有 `alerts/rules/{id}`、`users/{id}`、`sessions/{id}`、`documents/{filename}`——**没有** `data-files` 与 `artifacts` 的删除。r8 两轮验收累积残留：5 个 `browser-e2e-*.csv` 数据集 + 4 条 artifact + 33 孤儿会话，另有 PG `documents` 表 5 行指向已删文件而 `document_versions` = 0 | 两个 DELETE 路由 + 级联清理（含 PG 行与磁盘文件）；顺带把只插不删的 `documents` 表接进同一条清理路径 | 「交成果」视图、误传数据清理 |
| **R10 / A 线实测** | 鉴权 401/403 吐稳定码 | `app/main.py:104,109,113`、`app/common/authorization.py:53`、`app/api/v1/auth.py:110` 吐中文散文 → `artifacts.py`/`chat.py`/`alerts.py` 里的 `authentication_required` 在主路上**永不可达** | 见 §8 裁定，状态码不许动 | B 线封闭枚举 / 全站错误文案 |

## 2. 已完成、无需再动

- **R4 / B-3** catalog 解析状态：`parse_status` 全仓 31 处命中 + `migrations/0007_document_chunk_count.sql`。
- **R6 / B-5** 指标目录：`GET /semantics/metrics` 已存在且表驱动。
- **R9 / B-11** `/chart`、`/export` 真状态码：r8 `3e35481` 已落地（400 / 403 / 409 / 422 / 500），前端 F2 的 `response.ok` 检查自此有效，稳定码由 F7 字典接管。
- **S1–S7** 全部合并（`docs/handoff/2026-09-14-consolidated-fix-plan.md`）。

## 3. 明确不要求（防范围蔓延）

- 审批工单模型（C-1）——另立设计，不混在本单。
- insights 与 alerts 两套异常逻辑的合并——`consolidated-fix-plan` §4 已定「合并前不要单边改动」。
- 任何 legacy SSE 事件清理——契约 `SSE Event Deprecation Policy` 冻结规则。
- 改鉴权中间件让图片走 cookie 或签名 query token——前端带 token 取 blob 已可解决。（论据见 §5）

## 4. 前端侧的对等承诺

R1 落地前，前端不会用假数据填充员工视图，会显示「暂无可见异常」；R2 落地前不做「交成果」视图；C-1 落地前不做「办待办」视图。**前端不会替后端把占位页镀第二层**，详见 `docs/handoff/2026-09-15-frontend-hold-notice.md`。

---

## 5. P1-5 反驳：图表不显示不需要后端改鉴权

你在 `docs/current-functionality-2026-09-10-revision-log.md` §13.5 把 P1-5 记为「要动的是签名 URL 或 cookie 作用域，属契约变更」。**这条我不同意**，论据全部实测于 `c6c6009`：

1. **主断点在前端的正则，不在鉴权。** `frontend/src/components/ChatPanel.vue:139` 是
   `const re = /!\[([^\]]*)\]\((\/static\/[^)]+)\)/g` —— 它**只匹配 `/static/` 前缀**，
   所以 `/api/v1/artifacts/.../content` 从来没被解析成图表对象。`content_url` 长什么样根本没机会参与。
2. `<img>` 直接绑 `props.src` 确实带不了 Bearer（`ChartViewer.vue:14-15` 与 `:49`），
   但这是**渲染方式**问题，不是**服务端鉴权**问题。
3. **正确范式本仓库已有**：`DocPanel.vue:88-94` 用 `responseType: 'blob'` 取文件，
   而 `DocPanel.vue:7-9` 装了**全局** `axios.interceptors.request.use` 给每个请求加 `Bearer`。
   前端只要把 `ChartViewer` 的 `<img :src>` 换成「带 Bearer 取 blob → `URL.createObjectURL` → 绑 objectURL」，
   约 8 行，**零后端改动**。这正是 `docs/frontend-plan-2026-09-14.md` F1 的既有范围。

**请求**：不要为 P1-5 动鉴权中间件、不要引入签名 URL。理由三条——
(a) 私有化单机场景下 header-only 是更严的默认，为 `<img>` 开 cookie 作用域等于放宽鉴权面；
(b) 签名 URL 会把 token 泄进浏览器历史与 `Referer`；
(c) 它要解决的场景前端已经能自己解决。

**如果你已经按签名 URL 动手**：先停，把改了哪些文件贴出来。不要既保留 header-only 又新增签名分支——那会变成两套可互相绕过的读路径。

**顺带一条同源发现**：全局 axios 拦截器现在有**两份**（`DocPanel.vue:7` 与 `frontend/src/lib/api.js`）。
这就是审计里「4 套鉴权」中已被量化的两套，F3 会收敛为 1 处，**不需要后端配合**。


---

## 6. 语义裁定：admin 检索已定 e2；「停止」仍待决

### 6.1 三条链现在的 admin 语义（本轮逐调用点核实）

| 调用链 | 判据 | admin（无部门）的结果 |
|---|---|---|
| 数据链 `app/agents/tools.py` → `rbac.filter_dataframe_rows` | `role == "admin"` → 返回整个 df，部门与密级**都不滤** | 看得到全公司数据 |
| 资源链 `app/common/policy.py` → `administrator_scope` | admin 不要求同部门，clearance 仍适用 | 全库目录 / 预览 / 下载都可读 |
| 检索链 `app/rag/filters.py` | 只看有没有部门，**不看 role** | **403 `authorization_unavailable`，问不出任何东西** |
| `rbac.build_where` / `make_pred` / `doc_visible` | admin 放行、空部门 = 公开 | **0 调用者**（死代码；文档里"空部门=公开"那句就来自它） |

「目录看得见、问答查不到」的机械原因：三条活链里只有检索链没接 administrator。

### 6.2 裁定：e2 —— 检索链承认 `administrator_scope`

2026-09-15 用户选定 e2，e1（强制 `AUTH_DEPARTMENT`）不采纳。落地要求 6 条：

1. **判据同源**：复用 `policy.py::_is_administrator`（需要的话提升为公开符号或抽到公共模块），**不要**在 `filters.py` 里再写一遍 `"admin"` 字面量——那会变成第四套判据。
2. **只放开部门**：`classification in range(1, principal.clearance + 1)` 照抄保留，即使当前对 admin 是空操作（见下一条）。
3. **一句话必须写进 docstring**：`Principal.clearance` 取自 `clearance_for(role)`，而 `ROLE_CLEARANCE["admin"] = 3` = 最高密级 → **"保留密级上限"对 admin 当前不产生任何限制**，e2 的真实效果是跨部门 + 跨密级全库可读。日后客户若要"老板不得读机密"，要改的是 `ROLE_CLEARANCE` 映射（或给 admin 单配 clearance），**不是**部门规则。别留给下一个人重新发现。
4. **独立审计**：管理员跨部门检索记 `administrator_scope`（与资源链同名同义），不得记成普通部门命中——`policy.py` 注释里"override 不能被记成 ordinary department match"就是这个意思，检索链要照办。
5. **`AUTH_DEPARTMENT` 保持可选**、预检**继续 warn**：e2 之后"无部门的 admin"是合法状态，把 warn 升 error 会与裁定直接冲突（`0e34a41` 那条需要重新评估）。
6. **配套清理（不阻塞）**：`rbac.py` 里 0 调用者的 `build_where` / `make_pred` / `doc_visible` 标 retired 或删除。

边际风险论据：admin 现在已能通过资源链打开任意部门文档原文、通过数据链算出全公司表数据。**e2 只是让"问答"与这两条已存在的权限对齐**，没有新增特权类别。

### 6.3 e2 不解决的两个洞（前端自己补，零后端，但你们得知道）

- `upload_document` 现在把作用域取 `principal.department`、丢弃表单 `department`。因此**无部门账号上传的文档 `department=""`**，而 `filters.py` 是 `department ∈ 提问者的部门列表` → 空串不在任何人列表里 → **谁都检索不到**，上传界面却显示成功。后端 docstring 自己写了"a document that lands without one can never be found by anyone"。前端会在上传后回显归属并对空部门**当场警告**，但**根因在你们那一侧**：要么拒绝无部门账号上传，要么给这类行一个明确的 `unscoped` 状态。
- 数据链 `filter_dataframe_rows` 对 admin 是 `return df`（部门 + 密级全不滤），比 e2 还宽。既然裁定口径是"跨部门可以、跨密级不行"，这条链的 admin 分支建议一并收紧到按 clearance 过滤，否则"问答查不到机密、数据表却能算出来"会成为新裂缝。

### 6.5 e2 已落地（`719f29c`），但留下三笔新账

| # | 事项 | 事实 | 需要谁 |
|---|---|---|---|
| 1 | 死代码清理要一次授权 | 实现 e2 的那份 diff 顺手删了 `rbac.py` 的 `doc_visible` / `build_where` / `make_pred`，但 `tests/test_phase2_rbac.py` 与 `tests/test_phase7_mcp.py` 还在测它们 → 10 条红。我已把该文件**回退**保持绿灯；"删函数"和"退役它的测试"必须来自同一份授权，不能分两次做 | 用户点头后由后端线一次做完 |
| 2 | `Principal.from_user` 会把 0 级静默抬成 3 级 | `int(user.get("clearance") or clearance_for(role))`——admin 若被配成 `clearance=0/NULL`，`or` 判假 → 落到 `clearance_for("admin")=3`。即"给管理员降级"在配置层无效，且它**不是 e2 引入的**（e2 之后更要紧，因为管理员现在跨密级全库可读） | 后端线：改成 `is not None` 判定 + 一条回归用例 |
| 3 | G3 真机那半缺证据 | 代码与测试都在，但运行中的后端容器是 r8 那版镜像，"开箱 admin 问得出答案"无法在当前栈上证明。重建 `enterprise-brain-backend-1`（上轮 build 因缓存被 GC 花过 ~28 分钟）属于改变环境的重操作，我**没擅自做** | 用户点头 |

### 6.4 ~~仍需你拍板：「停止 = 拒绝挂起动作？」~~（2026-09-15 已裁定：**甲**，见 §9）

前端不阻塞：取消按钮已按「如实读 `cancelled` + 二次确认」排进 F2。但 cancel 是否顺带把挂起的 HITL 动作判为拒绝并写审计，只有你们能定。


## 7. 一条不要求你们改的反馈

- 错误响应体 `detail` 目前有**三种形状**并存：字符串稳定码（`data.py` / `documents.py` / `auth.py`）、`ErrorEnvelope` 对象（`observability.py`、`chat.py::_document_index_error`）、FastAPI 422 数组。前端 F7 会自己归一化，**不占用你们排期**；只是若将来统一到 envelope，请把它写进 `docs/api/contract-v1.md` 而不是靠默契。
- 我们**不需要**后端为 D-1（属主删不掉文档）做任何事：`documents/catalog` 已回 `owner_id` 与 `ownership`，判据齐了，改的是前端按钮的门控。

---

## 8. 总控裁定：鉴权 401/403 改吐稳定码（跟进单 **R10**，C 线批次 C-1）

**为什么要做**：A 线在活栈实测到的是 `请先登录`，不是契约里的 `authentication_required`。根因在 `app/main.py` 的鉴权中间件是**全路径兜底**，先于所有路由返回，所以 `artifacts.py`/`chat.py`/`alerts.py` 里那几处稳定码在「没登录 / token 失效」这条主路上**永远不可达**。B 线的 `frontend/src/lib/errcodes.js` 只认封闭枚举，散文会让 `resolveCode` 把中文原样当 code 吐回界面。

**硬约束（越界即返工）**：

1. **HTTP 状态码一个都不许改**：缺 token / 坏签名 / 过期 / 用户不存在 = 401；账号停用 = 403。白名单路径与 `/open*` 的行为一字不动。
2. **只改 `detail` 的值**：`请先登录` → `authentication_required`（4 个表达式：`app/main.py:104`、`app/main.py:109`、`app/common/authorization.py:53`、`app/api/v1/auth.py:110`）；`账号不可用` → `account_unavailable`（`app/main.py:113`）。
3. **两个码都要登记进 `docs/api/contract-v1.md`**，`account_unavailable` 是新码，必须写明 canonical 与触发条件。
4. **可选、允许、不许扩散**：把「token 过期/坏签名」从 `authentication_required` 里拆出 `token_expired`，让前端能显示「登录已过期，请重新登录」。前提仍是 401 不变、一次改完、不顺手动别的分支。
5. 全仓 `git grep` 复核：**没有任何测试断言中文原文**，所以这是一次零红口改动；但**要新增**断言每个站点各吐自己的码。
6. 前端 `LEGACY_ALIASES` 里的 `请先登录 → authentication_required` **不许删**——它是用来对接「尚未重建镜像的旧栈」的，旧栈仍会吐中文。
7. 真机验证仍受「重建后端镜像」那条待拍板事项约束：不重建则这条只能停在代码绿。

## 9. 用户已拍板（2026-09-15 下午）：「停止」按甲裁定；同时新增跟进单 **R12**

**裁定（④甲）**：`cancel` 只管流，`approve` 只管动作。契约写在 `docs/api/contract-v1.md` 新增小节
`R11: cancellation detaches the stream, it does not stop the work`。后端**不改语义**、前端**不改代码**，两条线都不返工。
`docs/handoff/2026-09-15-orchestration-board.md` §5 的这条待拍板项已闭合。

### 9.1 我核这条时顺手查出的真缺陷（不属于任何一份报告，已实测）

`/ask` 与 `/approve` 都把 agent 图跑在 executor 线程里，主循环只在排空队列时检查 `cancel_event.is_set()`；
命中就发一个 `cancelled` 事件然后 `break` —— **工作线程照旧跑到完**，把结果写进一个再没人读的队列。
`is_request_cancelled` 全仓只有 `app/api/v1/chat.py` 引用，`run_interrupt_stream`（`app/agents/orchestrator.py:949`）
与任何 worker 都不看取消标记。

用户可触发的形状：点「批准」之后前端会重新置 `loading = true`（`frontend/src/components/ChatPanel.vue:330`），
停止药丸再次出现；此时按「停止」→ 界面显示已取消，而**被批准的动作仍在执行并落库**。

### 9.2 跟进单 R12：让执行真正可取消（P1，建议排进 C 线批次）

1. 取消标记要能被 worker 侧读到（给 `run_interrupt_stream` 传 `should_cancel` 回调或等价物），
   在**每个 worker 边界**协作式检查，不是硬杀线程。
2. 检查点必须落在"有副作用的动作之前"：导出、写文件、删除类动作一旦已批准，要么跑完要么显式拒绝，
   不允许"半执行"。
3. 事件口径要能区分「动作未执行的真取消」与「只断流的取消」，前者不落库、后者只断流；
   落库口径变化必须同步 `docs/api/contract-v1.md` 与 `docs/current-functionality-2026-09-10.md`。
4. 不许顺手改 `/cancel` 的响应形状：`{"cancelled": bool}` 已是事实值（那一条是本轮定的，别回退）。
5. 测试要求：批准流中途取消 → 断言动作是否落库与第 3 条选定方向一致，
   并断言队列里遗留的无人读取的执行结果不会被后续请求误用。

## 10. 真机走查照出的两条后端需求：**R13**（挂起待办只读端点）、**R14**（服务端聚合行）

来源：总控用探针账号在部署栈上把 7 个工作区走完一轮（`scripts/live_acceptance.cjs`，控制台报错 0、失败请求 0），发现 `总览/洞察/图谱/审批` 四个面板**一次接口都不调**，显示的是组件里写死的常量。逐条读了后端实现后的结论：

- **图谱能立刻接真**：`app/api/v1/intelligence.py:133` `GET /knowledge-graph/relations` 已读库且按 Principal 收窄。**这条不需要你们动**。
- **R13（P1）**：全仓没有任何端点能列出**当前挂起的 HITL 待办**。`GET /api/v1/sessions/{sid}` 只回单会话状态，审批页因此只能造假。需求：一个只读的"待我审批"列表（谁发起、动作类型、依据、创建时间、按部门与角色收窄、分页）。**不要**顺手改 `/approve` 的语义。
- **R14（P2）**：`POST /dashboard`、`POST /insights/detect` 是**由客户端喂 rows 的算法端点**（`intelligence.py:73`、`:82`），既不查库也不取数据集。真实使用中前端拿不到"按部门聚合的经营行"，只能继续造假或把整表上传给浏览器算。需求：服务端出聚合行的只读端点（来源＝已登记的 datasets / catalog），或者明确写进契约「这两条就是客户端自备 rows 的纯计算端点，不适合做总览数据源」。
- 顺带一条已实测的现状：`GET /api/v1/alerts` 真读库，但 `_require_alert_management` 使 staff 得 `403 permission_denied` —— 就是跟进单 R1／看板 G4，你们已在排期内，无需重开。
- 前端侧承诺：R13/R14 落地前，这三块**必须显式标「演示数据」**，不许以权威结论样式呈现；图谱接真。总控已把这条裁定写进看板 §4D.4。

## 11. 排期外的一条线：跟进单 **R15**（知识即程序 / 图谱），排在 R13、R14 之后、C-5 之前

来源：另一条工作线交来一份"图谱这条线在批准计划里一条都没排"的判断。我逐条核过，**四条全部属实**，
但它同时报错了一条（见 §11.4），并漏了两条文档硬伤（§11.5）。以下所有行号我都实读过，非转述。

### 11.1 已实测的现状（这条线为什么"计划做完也不会变好"）

| 事实 | 证据 |
|---|---|
| 运行时存储是 JSON，不是 PG | `app/knowledge_graph/service.py:77` 导入、`:79` 构造 `JsonPersistenceAdapter` |
| 生产环境未配置即**拒写** | `:29-30` 只认 `KNOWLEDGE_GRAPH_STORE_PATH`；`:104-111` 无路径 + `_is_production_environment()` → `storage_mode=unavailable`／`protection=read_only`／detail `relation writes are refused` |
| 拒写落到 HTTP | `app/api/v1/intelligence.py:121-124` 捕获 `ProductionReadOnlyProtection` → **`503 storage_read_only`**，并 `record_audit(... "denied")` |
| 四处配置全缺 | `.env`／`.env.example`／`docker-compose.yml`／`deploy/.env.server` 搜 `KNOWLEDGE_GRAPH` **均 0 命中** |
| Agent 侧零消费 | `git grep -n "KnowledgeGraph" -- app/agents` → **0 命中** |
| 无落库位置 | `migrations/0001`–`0007` 建了 30 张表，**无 relations / entities 任何一张**；语义层占了 `0002:72` `metric_definitions` |
| 图谱在交付追踪里不存在 | 设计文档 §18 表 `docs/system-design-2026-09-16.md:702-721` 共 20 行，**没有知识图谱这一行** |

⇒ 收口后的真实形态：**人肉录关系 + `GraphPanel.vue` 一个列表 + Agent 不读 + 生产只读**。
"图谱提升了问答质量"这句话在答辩时不能说：没有 Agent 侧消费、没有 A/B、评测平台 §12.3 自标"部分落地（30 条集）"。

### 11.2 R15-a｜图谱定位收口（P2，最便宜，二选一，不许悬空）

- **甲**：在 `app/agents/` 建立一处**真实读取**（worker 或 synthesize 阶段按实体查已核对关系注入上下文），
  并加一条测试钉死"问题里含该关系时，回答的依据必须引用该关系"。判据：`git grep -n "KnowledgeGraph" -- app/agents` 有结果 **且**该测试存在。
- **乙**：承认它是"候选断言采集表、不是推理引擎"。则 `docs/system-design-2026-09-16.md:428` 那句
  "第一版存储用 PostgreSQL（邻接表）"**必须删**，改为与 `service.py:79` 一致的表述，并在 §18 补一行 `知识图谱存储与消费 | §10.4 | 目标态（现为 JSON，生产未配置即只读）`。
- **禁改边界**：不得只改文档不改代码来"对齐"，也不得为凑判据写一个没人调用的读取点。选甲就必须有测试证明 Agent 真读。

### 11.3 R15-b｜candidate → 正式口径的晋升路径（P2，这条才是护城河）

现状：`Relation.status=candidate` 由作者 clearance 定级（`intelligence.py:116-119`），但**没有任何一条路**把
被人工核对过的候选关系变成正式指标口径。语义层这边 `app/semantics/registry.py:22-24` 模块文档**自陈欠账**：
`metric_definitions` 没有 display label 与 prose definition 的列，二者被塞进 `filters` JSONB 的保留键
`semantics`（`:49-50` `SEMANTICS_KEY`），读取时再剥出来。

要求（一条 `0009` 迁移办两件事，按 `migrations/README.md:7-8` 登记 `manifest.json` + SHA-256，fail-closed）：

1. 把 display label／prose definition 从保留键**提成真列**，`registry.py` 停止"偷渡"读法，保留一次向后兼容读；
2. 给候选关系加"已核对：<文档> <段落>"字段，使未核对状态成为**可消除的枚举**而非永久 warning。

判据：一条测试跑完整链路"写入 candidate 关系 → 人工核对 → 落成正式 metric definition → warning 消失"。
不得引入新向量库、不得改 `Principal`/RBAC 语义（那是 C-4 的地盘）。

### 11.4 我核下来发现的**报告报错的一条**

报告称"看板记录的是 `895ee18` 时点 727 passed，R12 之后还没复跑"。**不成立**：我在 `826d318`（R12 已合入的当前 HEAD）
跑过两次，`771 passed / 22 skipped / 0 failed`，最近一次 2026-09-16 09:47:52 起、33.74s 结束，
跑前跑后 `git status --porcelain -- app tests migrations` 均为 0 行（可归因于该提交）。
权威口径请以 **771@`826d318`** 为准，别再用 727。

### 11.5 报告没抓到、我另外核出的两处文档口径问题

- `docs/system-design-2026-09-16.md:392` 写"无公开 `/static` 路径"，但 `app/main.py:133` **仍然 mount 了 `/static`**；
  准确表述是：`main.py:126-127` 对 `charts/`、`exports/` 一律回 404，生成物只能走 Artifact 路由，其余非生成物仍由该 mount 提供。
  这是"安全边界写严了"，答辩时容易被一句"那 /static 是什么"问塌。
- `:245` 与 §18 `:704` 两处仍写"隔离环境验收 **443 passed**"。该数字在它记录的时点是真的，但已被 `771@826d318` 取代；
  一份自称完成度对照的文档里挂着过期基线，就是下一个"我以为只有 443 条测试"的来源。
- 补一条与 R15 无关但同属迁移现状的事实：幽灵表 `documents` 由 `migrations/0004_legacy_runtime_compatibility.sql:30` 建立，
  不是运行期野生的，收口时要连迁移一起记账。

### 11.6 排期与前置

R15 不动权限语义、不改契约错误码、不碰 `frontend/**`，冲突面最小，可插队；但**仍排在 R13、R14 之后**，
且 R15-a 选甲之前必须先有 C-4 的检索授权口径落定，否则"Agent 读图谱"又要踩一次"空部门算不算公开"。
本批一律不做真机验证（Docker Desktop 未运行，见看板 §4H.3）。

## 12. 跟进单 **R16**：后端自己违反了"裸码名不进正文"，而且把污染**永久存进了历史消息**（P1）

来源：B 线做码表对账时扫到"后端自己就在违反我给它定的政策"。我按当前主树重定位后**逐行实读确认**
（B 给的 `:997-999` 是它自己树里 `chat.py` 的旧行号，主树已移动；实质成立，行号以下面为准）：

- `app/api/v1/chat.py:1026-1029` 造出 `failure_text = "本轮未产出任何结论（error_code=no_answer_produced），请重试或补充数据范围。"`；
- `:1030` `_save_message(thread_id, "assistant", failure_text, steps_log)` —— **这句进了会话历史**，不是一次性流；
- `:1032` 同句作为 legacy `error` 事件的 `content` 直推；
- 而 `:1033-1044` 的 canonical `request.failed` **已经**在 `data.error_code` 里带了 `no_answer_produced`（`:1042`）。

⇒ 结论：正文里那个码名是**冗余**的，且因为是存库文本，前端任何渲染期清洗都只能救新消息，**救不了历史行**。
这与我给前端的"用户可见文案不得夹裸码名"是同一条政策，后端不能豁免。

### 12.1 要求

1. `:1027` 只留人话句子，删掉 `（error_code=…）`；码继续走 `:1042` 的 `data.error_code`，**零信息损失**。
2. 不动 `:1030` 的落库时机与 `:1032` 的事件名（R11 冻结规则：legacy 保留是设计，不是待清理的残留）。
3. 存量历史行里的这句**不做数据迁移**（改库里的文本 = 篡改会话历史）。改由前端渲染期清洗，
   且这条清洗**必须**和 R16 同时登记，否则"历史里还有"会被读成"没修干净"。
4. 判据（机器可验证，缺任一不算完成）：
   - 一条测试断言 `no_answer_produced` 触发时，`_save_message` 收到的字符串**不含** `error_code=` 与 `no_answer_produced`，
     而 canonical `request.failed.data.error_code == "no_answer_produced"`；
   - `git grep -n "error_code=" -- app/api/v1/chat.py` 只允许出现在**结构化字段赋值**处，不允许出现在中文字符串字面量内；
   - 全量 pytest 基线不得倒退（当前权威 **771 passed / 22 skipped @ `826d318`**；R13 采用红底先行，中间 HEAD 可能故意红，不算倒退）。
5. 排期：R13 收完之后再做，**不并进 R13**（R13 已含接口变更登记，混进来会让契约账目对不上单）。

## 13. 跟进单 **R17**（做 C-4 时新查出）：数据行仍用「部门为空＝人人可见」，与文档链相反（P1，待业务裁定）

C-4 的实测结论先记在这里，防止有人重提「统一两套文档规则」：**文档链其实只有一套**。
`app/common/rbac.py` 的 `doc_visible` / `build_where` / `make_pred` 在删除时**零生产调用点**，
只被 `tests/test_phase2_rbac.py` 与 `tests/test_phase7_mcp.py` 养着；线上唯一判定是
`app/rag/filters.py::resolve_document_retrieval_scope`，它一次产出下推 `filters` 与本地 `allows`，
二者同源（`app/rag/retrieval_pipeline.py` 的 `search_for_principal` 只调一次），不可能各说各话。
这条已按 e2 收口（提交 `6589bbc`），守卫在 `tests/test_rbac_single_scoping_source.py`。

**但同一个模块里还活着一条反向规则**：`filter_dataframe_rows`（被 `app/agents/tools.py:372`、`:453` 调用）
判定数据行是否可见时用的是 `values.isin(("", dept))` —— **部门列为空的行，对任何同密级账号都可见**。
文档链现在恰好相反：`{"department": {"$in": [...]}}` 不含空串，所以部门为空的文档对普通账号不可见（fail-closed）。

于是同一个用户问同一份材料，会得到两种口径：文档查不到、数据行查得到。
这不是实现疏忽能一句话定性的，它是**产品规则**：企业里「没标部门的表」到底是公开还是私有，只有业务能答。

要求（二选一，不许继续悬空）：

- **甲（与文档链对齐）**：`filter_dataframe_rows` 改成只认本部门，空部门行仅 `administrator_scope` 可见。
  代价：现场演示/客户历史数据里那些没填部门列的表会突然看不见，必须配一条迁移期提示与灰度开关。
- **乙（承认数据行更宽）**：把这条差异写进 §12 与前端空态文案，并补一条测试钉住「空部门数据行对同密级可见」是有意的，
  防止将来有人"顺手统一"把它改成 fail-closed。

判据：`git grep -n 'isin(("", dept))' -- app` 的结果与所选口径一致，且存在一条命名自解释的测试。

## 14. 跟进单 **R18**（2026-09-16 总控实测）：取消标记按「代」生效，别再跨请求泄漏，也别留死字段

R12 已经把「停止 = 拒绝挂起动作」这条语义定了（§9 甲裁定），业务面不再悬空。但它底下的**实现**还缺三件，
今天逐条实测过，都不是推断：

1. **覆盖即丢取消**。`app/api/v1/chat.py:86-93` 的 `register_request` 无条件 `_REQUESTS[session_id] = threading.Event()`，
   于是先到的 `cancel_request` 把旧 Event `set()` 之后，新一轮 `register_request` 换上一个**干净的** Event，
   那次取消就被抹掉。这里的注释（`:87-89`）自己写着「本批不修，属 R13 状态机」——那就是它欠着的账。
2. **跨代泄漏**。`app/api/v1/chat.py:96-111` 的 `cancel_request` 在**没有**在飞运行时也会新建一个 Event、`set()` 后留在表里。
   下一次同会话的运行在 `register_request` 之前被 `is_request_cancelled`（`:114-117`）读到，就会被判成"已取消"。
   这条与 r8 记的「会话停在 HITL 挂起时按停止返回 200 但不清挂起」同因：**标记的生命周期不跟着一次运行走**。
3. **表只涨不消**。`git grep -n "_REQUESTS.pop\|del _REQUESTS\|_REQUESTS.clear" -- app` **零命中**（本轮实测 exit=1）。
   每个会话号永久占一个 `threading.Event`，只有重启才清——单租户长进程下是慢泄漏，不是理论问题。
4. **`cancellation_token` 是死字段**。全仓只有两处：`app/agents/contracts.py:135`（`= None`）与 `app/agents/state.py:38`（类型声明），
   `app/**` 与 `tests/**` 再无第三处引用，即**既不写也不读**。它给人「取消已经有代际标识」的错觉，比没有更坏。
   订正交接件里的行号：是 `contracts.py:135`，不是 `:121`。

**要做的事**（一次做完，别拆成两次改语义）：

- 取消状态以 **(session_id, epoch)** 为键。`register_request` 递增/生成 epoch 并返回句柄；
  `is_request_cancelled` 与 orchestrator 每步的取消检查都按**本代**判断。
  不带 epoch 的 `cancel_request` 允许保留"取消当前这一代"的语义，但**不得**把标记留给下一代。
- 一次运行结束（正常 / 异常 / 取消）必须在 `finally` 里弹出本代条目，使 `_REQUESTS` 只反映在飞的运行。
- `cancellation_token` 二选一：真当 epoch 载体用起来（写入 = 本代标识，读取 = 每步比对），或者删字段。
  **不许保留既存在又没人读的名字。**

**判据**（每条都要能机器复验）：

- 新增一条测试钉住窗口：`cancel_request(sid)` → `register_request(sid)` → 该次运行必须能观察到这次取消；
  或者反过来明确"取消只对本代有效"并把它写进 `docs/api/contract-v1.md` 的 cancel 一节。**不许继续两头都不认。**
- 新增一条测试：跑完 N 个完整问答后 `len(_REQUESTS) == 0`。
- `git grep -n "cancellation_token" -- app` 命中数要么 ≥3（有读有写）要么 0（删净），中间态算未完成。
- 业务面复验（真机）：会话停在 HITL 挂起时按「停止」→ 随后点批准 → **被停的动作不得执行**（这是甲裁定的落地判据，不是新功能）。

**禁改边界**：不动 SSE 事件枚举与 `docs/api/contract-v1.md` 已冻结的 26 条码表；不碰 `frontend/**`；
不改 R12 已定的「停止 = 拒绝挂起动作」语义，只补它缺的实现。**优先级**：排在 R13/R14 之后、C-5 之前（与 R15 同级）。

## 15. 跟进单 **R19**（2026-09-16 总控实测）：`shared_across_processes` 这个口径在带外改文件时是假的

`GET /api/v1/health/details` 给每个存储子系统报三个字段：`storage_mode` / `durable` / `shared_across_processes`。
今天把图谱切到文件持久化之后，我实测到这条断言只对一半：

- 我按 `shared_across_processes=true` 的说法，在容器内直接改 `/app/data/knowledge_graph.json` 删掉一条脏记录；
  **文件层面已经是 1 条**，但 `GET /api/v1/knowledge-graph/relations` 仍返回 **2 条**。
- 更要紧的是：下一次 `POST` 关系会把整个内存视图**写回文件**，于是我刚删掉的脏记录**又回来了**。
  必须重启进程才认文件。

所以 `shared_across_processes: true` 的真实含义只是「进程启动时读得到别人写过的文件」，
**不承诺**「多方并发写安全」，也**不承诺**「带外修改可见」。这三件事在客户现场是同一个词，但只有第一件成立。

**为什么算缺陷而不是文档措辞**：这个字段的用途就是让运维判断「我能不能同时跑两个 worker / 能不能手工修数据」。
按现在的答案它会说"能"，而实际两个进程各自缓存、后写者覆盖前写者（last-writer-wins 整份文件）。
`KNOWLEDGE_GRAPH_STORE_PATH` 一旦配上，`durable=true` 也会一起报出来，两条加起来读起来像"数据库"。

**要求（三选一，选完必须和代码一致，不许留悬空口径）**：

1. **改字段语义**（最便宜）：把 `shared_across_processes` 换成能表达三档的值，
   例如 `startup_read_only_shared` / `concurrent_safe`，或加 `single_writer: true`；`/health/details` 的 consumers 一起对齐。
2. **改实现**：写入走文件锁 + 每次读穿透文件（或迁进 PostgreSQL 表，与 §10.4 的目标态并轨，但那是 R15 的盘子）。
3. **明确禁止带外修数据**：把它变成产品约束——运维只准通过 API 改，脚本改文件必须紧跟一次滚动重启，
   并在 `docs/deployment/` 写死这条，字段保持现名但注释讲清。

**判据**：一条测试（或一段可粘贴的实测记录）证明「带外改文件之后，GET 的返回与文件一致」
或「字段名/文档已经不再承诺这个能力」；两种收敛都算完成，**维持现状不算**。
**优先级**：与 R15 同批讨论（R15-b 若把关系晋升做成 DB 表，这条会顺带消解）。

---

## 16. 跟进单 **R20**（2026-09-16 总控实测）：跑全量 pytest 会写宿主数据库，还在清理里 `DELETE`

**事实（W5 报出，总控复述其判据并认可）**：`tests/test_auth.py:163` 的 `TestUserCRUD` 直连宿主
PostgreSQL（`.env` 里 `DATABASE_URL=postgresql://fengx:***@localhost:5432/enterprise_brain` 实测存在），
用例收尾执行 `DELETE FROM users WHERE username LIKE 'test_%'`。可复现的红：20:50:51 全量
`test_duplicate_user` 失败（期望 `ok`，实为 `True`），20:51:22 同一份代码全量绿。未证实的机制猜测
（不在本单结论里）：`app/common/auth.py::create_user` 逐调用决定走 PG 还是内存，同名用户可能在两个
后端各建一份，唯一性只在单个后端成立。

**为什么不能留**：AGENTS.md 明令「未经用户明确要求，不运行会修改数据库或改变外部环境的操作」。
这条让「跑一次验收」本身变成写操作——每次我报 `N passed` 都顺带改了这台机器的库。

**判据**：该文件不再触达任何真实 `DATABASE_URL`（显式跳过并写明条件，或注入临时库），并且全量
连跑两遍结果一致。**只加一句「偶发，忽略」不算完成**。

**优先级**：P1。不阻塞演示，但污染每一次回归数字的可信度。

---

## 17. 跟进单 **R21**（2026-09-16 总控实测）：embedding 失败被静默换成**全零向量**，向量检索整条腿空转

**事实（逐条读码，含我上一版写错的地方）**：`_fallback_embedding()` 返回的是
`[0.0] * 768`（`app/rag/retriever.py:46-47`）——**全零向量**，不是哈希伪向量；我前一份记录里写的
「哈希假向量」是凭印象，特此订正。触发面比 404 更宽：`_call_api` 的 `except Exception` 什么异常都吞
（`retriever.py:64-67`），并且默认 `OLLAMA_EMBED_TIMEOUT=1` 秒（`retriever.py:42`）——模型正在被加载、
机器正忙时 1 秒很容易不够，同样静默变零向量；一旦失败还会 `self._disabled_until = now + 30s`，
冷却期内**连 API 都不再尝试**，直接批量发零向量（`retriever.py:49-51`）。
维度恰好也是 768，所以零向量能顺利写进 Chroma 而不报任何形状错误。
本机 ollama 里 `nomic-embed-text` 从未被拉取，`docker logs` 实测 21:13:16 / 21:16:19 / 21:18:24
三次 `Ollama embedding fallback: HTTP Error 404`。`/api/v1/health/details` 的 `problems` 里没有
任何 embedding 项（21:49 实测 `problems=[]` 而当时向量全是零），界面与探针都看不出。

**后果**：所有降级 chunk 的向量**彼此完全相同**（零向量夹角无定义），向量这一路不再提供任何排序信息——
不是提供劣质排序，而是**根本不在场上**。此前 G3「admin 问得出知识库答案」那次命中，是检索管线里
BM25 / 关键词那条腿在干活。任何一台没预置该模型的客户机开箱都是这个形态，而文档口径写的是向量检索。
**已实测的对照**（2026-09-16 21:55，删除重传同一份 252 字节文件后读库）：
`chroma://enterprise_docs` 里 `demo-policy.md_0` 为 `dim=768 / nonzero=768 / norm=20.144491`，
即模型就位后向量确实是真向量——问题不在检索代码，在**失败时不许静默换零**。

**判据**：① `/health/details` 增加 embedding 探测，缺失时 `problems` 给出稳定码（如
`embedding_model_missing`）；② fallback 生效时答案侧带可区分的降级提示，不许静默；③ 一条测试钉住
「404 不得被当成正常路径」。三条缺一不算完成；**先把模型装上**是运维动作，不替代本单。

**优先级**：P0（演示前至少要做到「看得见」，否则我们讲的检索质量与机器上跑的检索不是一回事）。

---

## 18. 跟进单 **R22**（2026-09-16 总控实测）：换了 embedding 之后，库里的旧向量没有任何重建路径

**事实**：`EMBED_MODEL` 是一个模块级常量（`app/rag/retriever.py:23`），改它或换模型之后，已经写进
Chroma 的向量**不会重算，也没有任何入口让它重算**——全仓 `app/` 与 `scripts/` 对 `reindex`、
`rebuild_index`、`reset_index` 一律 0 命中（2026-09-16 实跑）。系统也不会提示口径已经变了：
`/health/details` 里没有「向量与当前 embedding 模型不一致」这类判据。

**今天怎么绕过去的**：靠 `DELETE /api/v1/documents/{filename}` 再重新上传。这条链路本身是对的——
它先 `retriever.delete_document(filename)` 回滚索引，回滚失败就**不删文档**并答 `index_rollback_failed`，
不会假装删干净（`app/api/v1/chat.py:2087` 起）。实测删除返回 `index_retirement.status=retired`，
重传后库内只剩 1 条真向量，没有留下新旧双份。但这是人工兜底，不是能力。

**为什么不能留**：私有化交付一定会遇到「客户换了模型 / 我们升级了 embedding」。届时知识库会拿
旧模型算的向量去配新模型算的查询向量，检索质量**静默塌陷**，而界面显示一切正常——这是比 404 更难的坑。

**判据**：① 向量集合里记录并可比对「产生该向量的模型标识」；② 模型标识与当前配置不一致时，
`/health/details` 出稳定码（如 `embedding_model_drift`）并在回答侧可见；③ 提供一条真正的重建入口
（接口或 `scripts/` 命令，带可验证的完成判据），且重建期间旧向量不会被当成新口径的结果使用。
三条缺一不算完成；**只在文档里写一句「请删库重传」不算**。

**优先级**：P1（演示不阻塞；上生产前必须至少有 ①②）。

---

## 19. 跟进单 **R23**（2026-09-16 总控实测）：并发预算不足时**先发请求再撞墙**，24 秒零产出且静默降级

**事实**：`MODEL_MAX_CONCURRENCY` 默认 **1**（`app/common/model_budget.py:53`）。真实链路里多路查询改写
并发发模型请求，拿不到预算的那几发留下 `[Model] local model concurrency budget exhausted`，随即被
`app/rag/retrieval_pipeline.py:63` 吞成 `查询改写失败，返回原始问题: Expecting value: line 1 column 1 (char 0)`
（2026-09-16 21:59:03 实测两条）。日志时间戳显示其中一发耗掉 **24.1 秒**——即请求已经发出去并把模型占住
了一段时间，最后仍按"改写失败"退回。

**为什么不能留**：① 用户视角是"改写这个功能存在"，实际在预算=1 的部署上它**经常什么都没做**；
② 24 秒是纯浪费，不是成本；③ 异常文本 `Expecting value: line 1 column 1` 被拼进降级原因，若哪天
冒到界面上就是原始异常泄漏（与本仓 R8 那条"不许编造、不许裸泄异常"同一口径）。

**判据**：① 预算取不到时**不发起请求**（先拿令牌再打模型），或明确排队且排队时长可见；② 降级原因
是稳定码而非异常文本（如 `query_rewrite_skipped_no_budget`）；③ 一条测试钉住"预算耗尽不得产生一次
真实的模型往返"。改默认值（>1）不算完成本单——默认值该由客户机硬件决定，见 R24。

**优先级**：P1（不阻塞功能，但它是"慢且没结果"的直接来源）。

---

## 20. 跟进单 **R24**（2026-09-16 总控实测）：单次模型超时 60 秒与真实上下文长度冲突，客户库一大就必然报错

**事实**：`MODEL_REQUEST_TIMEOUT` 默认 **60** 秒（`app/common/model_handler.py:50`）。本机实测
`qwen3.5:9b` 在**纯 CPU** 下 prefill 只有 **35.2 token/s**、decode **8.18 token/s**（2026-09-16 22:2x，
容器内直连 `http://ollama:11434/api/chat`：2199 token 输入 / 6 token 输出的单发请求耗时 **69.8 秒**，
其中 `prompt_eval_duration` 62.5 秒）。也就是说**一次上下文超过约 2000 token 的请求，光读题就超过 60 秒**，
必然在生成前被自家超时掐掉。今晚真实链路最长的一次生成 50.6 秒，**余量只剩 15%**。

**为什么不能留**：私有化客户机常常是无独显的 Xeon，比笔记本 CPU 更慢；而客户知识库规模远大于今晚的
1 篇文档。这两个方向都让同一个 60 秒从"勉强够用"变成"必炸"。而炸掉的表象是 error，不是慢——
销售口径写的却是"支持私有化部署"。

**判据**：① 超时值不得是与上下文长度无关的常数（要么按 prompt 规模给预算，要么把 prefill/decode 分开计时）；
② 超时被触发时，`/health/details` 与回答侧要能区分"模型太慢"与"机器没 GPU/内存不够"，给出稳定码；
③ 文档必须写出**硬件基线**：现在 `README`、`docs/system-design-2026-09-16.md`、`deploy/*.md` 里对
GPU/显存/最低配置**零命中**（2026-09-16 实搜），即"客户这台机器能不能跑"目前无人能答。
**关联**：W8（`codex/perf-lab`）正在出量化预算表，本单的 ②③ 应引用它的实测行，不得各写一套数。

**优先级**：P0（交付能力问题，不是体验问题）。

---

## 21. 性能与架构线正式立单 **R25–R52**（2026-09-17 总控，基线 `ec0f40b`）

**为什么要移到这里**：性能改造的**登记处**是本文，**论据与编排**在
`docs/handoff/2026-09-17-perf-architecture-plan.md`（下称《计划书》）。人日、分层、依赖链看《计划书》§5；
每单的**判据与禁改边界**以本节为准。**R39 不建，沿用 R17**（裁定=甲）。
**共同判据（2026-09-17 09:45 订正，根因见看板 §4V.3）**：R20 未修之前**任何腿禁止跑全量 pytest**——实测它会 `DELETE` 宿主原生 PG 的 `users` 行（`tests/test_auth.py:163`、`tests/test_phase2_rbac.py:45`），属未授权的数据写操作；合并前只跑**本单指定单文件**并记**当前 HEAD** 的数字，全量回归由用户另开的独立对话在 R20 修完后统一复跑。**任何历史 HEAD 的 passed 数字一律不得当现状引用**（`895ee18` 的 727/903 与 `826d318` 的 771/22 均已过期）。
端到端计时期间禁止 `up/down/restart`；GPU 档必须先在容器内 `nvidia-smi` 自证，否则整轮作废。

| 单号 | 内容与落点 | 判据（机器可验） | 禁改边界 |
|---|---|---|---|
| **R25** | 开发期把 `app/**` 挂进容器，免每轮 28 min 重建。`docker-compose.yml` | 改一行 `app/**` 后不 build 即生效；`verify_container_stack.py --skip-build` 仍能过 | 不改生产 compose 的副本语义；挂载只加在 dev override 文件 |
| **R26** | GPU 诚实声明。`docker-compose.yml:78`（ollama 现无设备声明）、`README`、`deploy/*.md` | ① 容器内 `nvidia-smi` 有卡；② **拿不到卡必须显式报错 + 稳定码**，不得静默 CPU；③ `/health/details` 能区分"模型太慢"与"机器没 GPU/内存不足"；④ 硬件基线（GPU/显存/最低配置）入文档，与 **R24 ②③ 合并验收** | 不许为了"绿"把 healthcheck 改成无条件 ok |
| **R27** | 确定性计划命中即跳过 Supervisor **两发**（现白花 43.728 s）。`app/agents/orchestrator.py:201` | ① 第 2 发不再发生（日志计数）；② 先加测试钉住 `orchestrator.py:285-305` 兜底仍能纠正错派；③ 端到端 −≥35 s | **不得删**兜底路径；不得改 worker 结果结构 |
| **R28** | 多路改写改条件触发 + fast/thorough 分档（现白花 41.581 s）。`app/rag/retrieval_pipeline.py:271`（无任何前置条件）、`:50 rewrite` | ① 单跳问题走 fast 时**模型往返数为 0**；② 多块召回时 thorough 行为不变；③ 30 题评测不退化 | 不得动 `:59 json.loads` 的失败语义（那是 R23）；不得顺手改检索权重 |
| **R29** | 思考税。**重定义**：`/v1` 上 5 种关思考写法全无效（W8 §5.4 `[实测]`）⇒ 迁原生 `/api/chat`，或做 `PARAMETER think false` 派生模型 | ① `thinking` 字段实测为 0 字；② 生成轮 30.6 s → ≤22 s；③ **前置：R36 质量基线已建立**，制度题准确率不得下降；④ `tool_calls` 报文重做后权限/超时语义全复验 | 不许只在 `/v1` 加参数就当完成；不许在无线上端点证据前宣布关掉了思考 |
| **R30** | `max_tokens` / 超时按档。`app/agents/contracts.py:72`（字段存在但**全仓零赋值**）；三处硬编 `timeout=30`：`nodes.py:304`、`nodes.py:370`、`tools.py:443`；`model_handler.py:50` 默认 60 vs `.env.example:38` 的 120 | ① 每档有显式 `max_tokens`；② 超时与 prompt 规模相关（按预算或 prefill/decode 分计）；③ 默认值与 `.env.example` 一致；④ `n_ctx=4096` 撞顶有稳定码 | 不改并发语义（R23）；不改默认模型名 |
| **R31** | 生成轮流式透传。改 **HTTP 出口 2 处**：`nodes.py:174` / `:193`；graph 级 `orchestrator.py:709`（`stream_mode="values"` 在 `:491`）。**前端零改动** | ① `text` 事件数 >1；② **片段时间戳不重叠、逐字比对无缺字**；③ 后端每片 **≥20 字或 100 ms 合并，禁单字碎片**（原因见《计划书》§2.7 两个静默陷阱）；④ 与 legacy 全量重发共存不冲突 | **禁改 `frontend/**`**；禁在 `sessions.js` 里去动 `segments` 语义（那是前端线的）；必须排在 R27/R29/R30 之后 |
| **R32** | 问答/分析/报告三档进契约 + 前端选择器，默认问答档 | ① 契约写出三档 SLO；② 档位不改变权限判定；③ `/ask` 非法档 → 400 | 不得借分档放宽 scope；legacy 事件名一个不许下线 |
| **R33** | 输入瘦身：每发 prompt token 上限 + 无模型裁剪（现 `compress_messages` 自己要多发一模型，`orchestrator.py:158`） | ① 每发 prompt token 有硬上限且日志可见；② 裁剪过程**零模型调用**；③ **与 R36 同批合并**（会改答案内容） | 不许裁掉权限谓词与来源定位串 |
| **R34** | `keep_alive` 常驻（现**全仓 0 命中**；冷加载 6.4–6.9 s/发） | ① 连续 5 问无重复冷启动；② 空闲后内存回收策略写进文档；③ 原生端点上生效（`/v1` 传参无效） | 不得设成永不卸载（客户机内存有限） |
| **R35** | 真缓存两件事：① 门槛 `chat.py:936 use_answer_cache = not bool(request.session_id)` 改成 scope 相等即可命中；② 死代码 `cache.py:150-176`（字符集合 Jaccard、进程内 dict、无 TTL/淘汰/scope，**`app/**` 零调用者**）删除或按 Redis+向量+scope 重建 | ① 多轮对话内重复问题命中且**标注"缓存结果·生成于"**；② **跨部门/跨密级命中 0 条**（P0）；③ 淘汰策略可测 | 不许无 scope 上线；不许伪装成实时答案；命中必须是 UI 第四张脸 |
| **R36** | 三屏 SLO + 评测集 **30 → ≥100 条** | ① 每档有可跑的分层评测集（含**同指标两部门口径冲突**成对题）；② P95 计算样本 ≥100；③ 基线分数落盘供 R29/R33/R35 对比 | 不得用演示语料充当评测集 |
| **R37** | report 档进可靠队列（通道现成：`app/common/reliable_queue.py` + `deploy/queue_worker.py` 已跑 `run_orchestrator_result` 并 `queue.complete`） | ① 关页面后任务继续；② 结果可查回；③ 队列失败有终态与原因码 | 不改 `/ask` 现有同步档行为；不得丢 HITL 语义 |
| **R38** | 核实 `usage` 真值（计量列在 `migrations/0002:147`：`input_tokens/output_tokens/duration_ms/first_token_at/queue_wait_ms`；链路 `app/trace/spans.py` → `app/trace/store.py:171`；现 `cached_tokens=0`） | 抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致 | 不得估算冒充实测 token 数 |
| **R40** | `standard_source` 自动取标准（承接 R5，现 `app/**` **0 命中**）；服务端**拒绝**前端传入的 `department` | ① 不传部门也能出结论；② 传错部门被拒且是稳定码；③ 不再出现前端 `standard: 500` 硬编 | 不改审批动作的权限判定 |
| **R41** | SSE canonical `sources` 事件（承接 R3/B-2；现 `sources` 只在 `chat.py:764-768` 非流式路径拼装） | ① 流里出现 `sources`；② legacy 全保留；③ 前端引用条可点回原文 | **一个 legacy 事件名都不许下线**（契约冻结规则） |
| **R42** | 快慢判别器（规则优先，学 Glean 的 Waldo 但**不再花一发模型**）。落点 `orchestrator.py:285-305` 兜底 + `nodes.py:304` 分类结果 | ① 判别零模型调用；② 判错时兜底仍能升档；③ 问答档占比 ≥60%（对齐 70:25:5） | 不许引入新的模型往返来做路由 |
| **R43** | system prompt 前缀复用、可变内容后置（配合前缀缓存；外部锚 llm-d TTFT p90 0.542 s vs 94.865 s） | ① 同一前缀字节级稳定（无时间戳/无随机顺序）；② E3 档实测 `cached_tokens > 0` | 不许把权限信息塞进可复用前缀 |
| **R44** | 热集进程内检索索引（外部锚：进程内 HNSW ≈0.0015 ms vs 外部库 1–5 ms） | ① 覆盖 95% 查询的热集常驻；② 与 Chroma 结果一致性有测试 | **不许**因提速牺牲部门/密级过滤（pre-filter 先于热集） |
| **R45** | Pre-filtering：权限与部门谓词先缩小候选集再算向量 | ① 过滤在向量计算**之前**；② 严格权限下召回不为空（对比 post-filter 退化用例）；③ 检索 P95 不升 | 不得复用 `cache.py` 那套无 scope 逻辑 |
| **R46** | 活动信号回填排序（采纳/驳回/点击 → 相关度先验；对齐 `contracts.py:157 score_type` 已备枚举） | ① 有信号后排序变化可测；② **无信号时与现状一致**；③ 隐私：只存计数不存内容 | 不得把用户问题原文写进新表 |
| **R47** | 术语/同义词接进改写（`metric_definitions.match_terms` 已有） | ① 同义词题命中改进；② 改写仍走规则不新增模型往返 | 不改 `metric_definitions` 语义（R15-b 刚收口） |
| **R48** | 首屏结论卡片 + 来源，正文后台补齐 | ① 首屏 ≤1 s 有可用结论；② 后台补齐失败有明确标注 | 不得先渲染结论再"纠正"成不同答案（前端 `_correcting` 路径要避开） |
| **R49** | 索引瘦身：草稿/模板/超小文档不入索 | ① 有排除规则且上传时给出原因；② 被排除文档在 UI 可见为"未索引" | 不得静默丢弃用户上传 |
| **R50** | 增量索引 + 低峰全量重建 | ① 单文档增量 <2 s；② 全量重建可中断续跑 | 重建期间不得出现"检索结果忽有忽无" |
| **R51** | 阶段化 P95 观测（每步耗时进 trace 与 `/health/details`） | ① 分类/改写/检索/生成/反思各段 P50/P95 可查；② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%） | 观测不得改变行为 |
| **R52** | 断外网自检 + 内网证书（私有化形态，非性能） | ① 断网可装可跑；② 内网域名 + HTTPS 通过；③ 批量建 50 账号可登录且权限正确 | 不得为过检临时放宽 TLS 校验 |

### 21.1 优先级（不按优先级排期会出事的地方只有一处）
- **P0（阻塞交付能力）**：R25、R26（含 R24 ②③）、R36、R42/R45 中的权限侧、R52。
- **P1（决定"能不能用"）**：R27、R28、R29、R30、R31、R33、R34、R35。
- **P2（体验与规模上限）**：R32、R37、R38、R40、R41、R43、R44、R46–R51。
- **唯一"顺序错了就白干"**：R36 必须早于 R29/R33/R35；R27/R29/R30 必须早于 R31；R25 必须最早。

### 21.2 本节明确不要求（防蔓延）
Neo4j / 图数据库、"三柱图谱"叙事、多租户与 SaaS 化、legacy SSE 清理、换 embedding 或上 reranker 来提速
（检索本体只占 **0.242 s**，见《计划书》§7）。**宣称"知识图谱提升问答质量"同样禁止。**

### 21.3 与前端线的接口
《计划书》§6.1 已核对：洞察→「异常与告警」、审批→「报销自查」、四张脸分开、Element Plus 移除 —— **均已完成**
（`0d57886` / `9d327d8`，`frontend/package.json` 已无 `element-plus`）。性能线对前端**只新增两条要求**：
① **图谱撤一级入口**（`frontend/src/App.vue:48`、`:56`），降为文档预览的"依据 / 相关制度"子视图；
② R32 的**档位选择器**与 R35/R26 的**降级第四张脸**。**除此之外本线不得改 `frontend/**`。**

---

## 21.4 本轮（09-17 上午）执行状态：R25 / R27 前置 / R36 已合并，R20 在途

| 单号 | 状态 | 落点 | 总控独立复核结论（不采信自述） |
|---|---|---|---|
| **R25** | ✅ 已合并 `b17b4dd` | 新增 `docker-compose.dev.yml` + `README.md` 一节 | 挂载点 `/app/app` 经容器内 `import app.main` 实测；`verify_container_stack.py:105` 确认一律显式 `-f` ⇒ 容器门仍验镜像语义；`git status --porcelain -- docker-compose.yml deploy app frontend` 为空 |
| **R25 命名裁定** | ✅ 采纳，**偏离原单默认名** | 故意**不叫** `docker-compose.override.yml` | 原单默认名有缺陷：`README.md:13` 的客户命令不带 `-f`，自动合并会让私有化栈绑定挂载运维机代码树；实测临时改名后 `config` 出现 `bind entries auto-merged: 3` |
| **R25 真机生效** | ⏸ **待用户独立对话** | 双 `-f` `up -d` + 改一行看 `WatchFiles ... Reloading` | 会重建在跑的 3 个容器（与验收栈同名、已 healthy 12 h），属端到端门禁 |
| **R27 前置测试** | ✅ 已合并 `29665da` | 新增 `tests/test_route_fallback_correction.py`（13 例） | 总控亲跑 `13 passed in 2.40s` [实测 09:52]；变异验证后 `orchestrator.py` 工作文件 blob 哈希 == HEAD（`cdec7d2`）无残留；跑后 `chroma_db` 未被写 |
| **R36** | 🟡 **部分完成**，已合并 `ac44d00` | `tests/fixtures/business_evaluation_100.jsonl`（105 条）+ `test_evaluation_report.py`（+216 行） | 判据①达成：总控独立统计 105 条 / id 唯一 105 / 问答 50·分析 35·报告 20 / 成对冲突 8 对 16 条 / **沿用原 30 条 question·answer·must_contain 零漂移**（`DRIFT_COUNT=0`）；亲跑 `8 passed` [实测 09:58]，三单合并后复跑 `21 passed` [实测 09:59] |
| **R36 判据②③** | ⏸ **待用户独立对话** | 基线分数落盘供 R29/R33/R35 对比 | 跑分必须打 Ollama（`n_ctx=4096` 单点红线），本轮零模型调用。**未落真机分数不算 R36 完成**，R29/R33/R35 的"质量基线已建立"前置**仍未满足** |

**顺带钉出的两条既有缺陷（不计入 R36 完成度）**：

1. `insight-02` 期望值 `上升`，金标答案却是「返回趋势异常」⇒ **它过不了自己的 `must_contain`**。本轮为保持与历史 30 条可比而未改，已锁进 `KNOWN_INCONSISTENT_INHERITED_IDS`（扩大即红），基线落盘后再收紧。
2. **R20 范围必须再扩一条**：任何导入 `app.agents.orchestrator` 的测试，若解释器装有 `psycopg_pool`，会在 **import 期**连宿主 PG 并执行 `PostgresSaver.setup()` 建表。当前 `C:\Users\fengx\anaconda3\python.exe` 实测 `ModuleNotFoundError: psycopg_pool` [实测 09:52] 才幸免 ⇒ **这是环境巧合，不是设计保证**，R20 的隔离必须同时覆盖 `app.common.auth` 与 `PostgresSaver` 两条 import 期路径。
