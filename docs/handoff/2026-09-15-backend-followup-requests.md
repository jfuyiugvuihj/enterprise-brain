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

## 2. 已完成、无需再动

- **R4 / B-3** catalog 解析状态：`parse_status` 全仓 31 处命中 + `migrations/0007_document_chunk_count.sql`。
- **R6 / B-5** 指标目录：`GET /semantics/metrics` 已存在且表驱动。
- **S1–S7** 全部合并（`docs/handoff/2026-09-14-consolidated-fix-plan.md`）。

## 3. 明确不要求（防范围蔓延）

- 审批工单模型（C-1）——另立设计，不混在本单。
- insights 与 alerts 两套异常逻辑的合并——`consolidated-fix-plan` §4 已定「合并前不要单边改动」。
- 任何 legacy SSE 事件清理——契约 `SSE Event Deprecation Policy` 冻结规则。
- 改鉴权中间件让图片走 cookie 或签名 query token——前端带 token 取 blob 已可解决。

## 4. 前端侧的对等承诺

R1 落地前，前端不会用假数据填充员工视图，会显示「暂无可见异常」；R2 落地前不做「交成果」视图；C-1 落地前不做「办待办」视图。**前端不会替后端把占位页镀第二层**，详见 `docs/handoff/2026-09-15-frontend-hold-notice.md`。
