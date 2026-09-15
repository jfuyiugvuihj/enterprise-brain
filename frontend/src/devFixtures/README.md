# devFixtures —— 编造的演示数据

本目录里**每一个常量都是编的**：不来自任何接口，不代表任何客户的真实经营情况。
它们存在的唯一理由是对应的后端端点还没落地，界面需要一个能跑起来的形状。

三条规矩：

1. 引用本目录的面板必须显式挂「演示数据」徽标并写一行说明，且**禁止**套用 `critical` / `warning`
   这类权威语义样式（红三角、琥珀色告警条都会让人以为出了真事故）。
2. 后端把真实端点补上后，逐格删掉对应常量并把面板切回真数据，**不要**留着兜底。
3. 上线前本目录必须清空：在 `frontend/` 下跑 `git grep -n devFixtures -- src`，
   除了本 README 之外应当零命中。

| 文件 | 喂给谁 | 在等哪个后端 |
| --- | --- | --- |
| `dashboard-demo.js` | `DashboardPanel.vue` 的趋势卡、异常卡、`审批任务` KPI | R14：`/dashboard` 与 `/insights/detect` 目前都是客户端喂 rows 的算法端点，不查库 |
| `insights-demo.js` | `InsightPanel.vue` → `POST /insights/detect` 的入参 | R14：同上 |
| `approval-demo.js` | `ApprovalPanel.vue` → `POST /approval/precheck` 的入参 | R13：列挂起 HITL 待办的端点尚不存在 |
| `login-demo.js` | **已删除**，登录页不得出现任何未溯源数字 | 不等端点：文件与三张装饰卡已一并移除，见下方注 2 |

> 注 2：登录页原先有三张装饰数据卡（`数据 1.2M+` / `洞察 +42%` / `知识 300K+`），连同
> `login-demo.js` 一起**删除**。私有化单机部署的登录页没有营销受众：员工或老板在还没登录时看到
> `1.2M+` 只会读成"我们公司有多少数据"，而库里实测 documents=5、datasets=5、alerts=0。
> 现在登录页的说明文案是 `App.vue` 里 `login-capabilities` 那三个**不含数字**的定性能力词
> （数据安全 / 知识沉淀 / 智能分析）。**登录页不得再出现任何未溯源数字。**
> 本行原先写的"总控已裁定保留"是一条未经确认的结论，已按总控 2026-09-15 复核订正删除。

> 注：`GraphPanel.vue` 里那组写死的关系表单值不属于本目录——图谱的列表数据是
> `GET /api/v1/knowledge-graph/relations` 真读库并按 Principal 收窄的（`app/api/v1/intelligence.py:133`），
> 所以那组假预填值在 V7-1 里直接删掉了，而不是搬进来。
