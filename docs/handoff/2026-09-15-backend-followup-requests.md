# 后端接口跟进单（前端线提出，2026-09-15）

**基线**：`c6c6009`（2026-09-15）。
**核对方式**：读工作树源码。核对时点（08:40）`app/**` 与 `migrations/**` 零未提交改动，因此下列结论即**已提交状态**的结论。
**递交时机**：等本轮 browser e2e 验收收口之后再递，不要中途插进正在跑的任务。

---

## 0. 先订正我昨天的一条误判

- ~~S7 缺 `migrations/0007_metric_definition_sync.sql`~~ —— **不是缺陷**。`metric_definitions` 自 `migrations/0002_execution_data_lineage.sql:72` 就存在，S7 复用现表，不需要新迁移。`definition_version` 已在 `app/semantics/contracts.py` 与 `/semantics/metrics` 暴露，provenance 告警语义也保留了（`app/semantics/registry.py` 的 `_TABLE_WARNING` / `_SEEDED_WARNING`，未伪装成已核对）。**S7 判为完成。**

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

### 6.4 仍需你拍板：「停止 = 拒绝挂起动作？」

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
