# 前端三页冻结提示（2026-09-15）

**致**：后端线会话（正在跑 browser e2e 验收的那条）
**发出**：前端计划线
**一句话**：你验收清单里的 `insights` / `graph` / `approval` 三页已经裁定处置，**请不要再就地修补**。

---

## 1. 为什么要冻结

2026-09-15 08:37 的验收截图产物包含七个页面，其中三页在 2026-09-14 的工作区审计里已被判定为「升级计划的最小接口占位被镀层后留在侧栏」。再修一轮就是镀第二层。

依据：`docs/frontend-plan-2026-09-14.md` §2、`docs/frontend-workspace-audit-2026-09-14.md` §4。

## 2. 三页的裁定与禁区

| 页面 | 已裁定 | **不要做** |
|---|---|---|
| 洞察 `InsightPanel.vue` | 改名「异常与告警」，改为消费 `GET /alerts`、`GET/POST/DELETE /alerts/rules`、`POST /alerts/check`；**删除手填五格表单** | 不要给手填表单补校验、补演示数据、补图表；不要把 `app/insights/rules.py` 做成真引擎 |
| 图谱 `GraphPanel.vue` | 撤下侧栏入口，降级为文档预览里的「依据 / 相关制度」子视图（`GET /knowledge-graph/relations` 已支持 `source_entity`、`relation` 过滤） | 不要补可视化、不要补三元组录入表单、不要给 `confirm()` 加按钮 |
| 审批 `ApprovalPanel.vue` | 改名「报销自查」，界面写明这是自查工具；工单系统另立计划（C-1） | 不要补待办列表、不要补审批按钮与状态流转、不要在 `build_precheck` 上贴皮 |

## 3. 请照此调整验收结论

- 这三页的"缺陷"若属于上表禁区，请在报告里标 `out-of-scope: 已裁定撤下/降级`，**不要开修复任务**。
- 真正需要后端配合的项已单列在 `docs/handoff/2026-09-15-backend-followup-requests.md`，按阻塞程度排好序。

## 4. 一个文件级风险（与三页无关，但请顺手注意）

`frontend/**` 有 **19 处自 09-10 起未提交的改动**：面板文件 mtime 停在 09-10，`src/lib/`、`src/assets/login-*.png`、`Dockerfile` 仍是未跟踪状态。

请不要执行 `git checkout .`、`git reset --hard`、`git add -A`——会把这批改动扫掉，或混进后端的提交里。前端改动由前端线自己提交。

## 5. 如果你已经改了这三页

**不要回退**，那会连带回退别人的东西。把改了哪些文件贴出来即可，我在计划里合并或标废。
