# 前端并行开发与多 Agent 分工（2026-09-15）

**用途**：一次定死「开几个对话、每个对话里再开几个子 Agent、各自能碰哪些文件、怎么合并」。
**新 Agent 开场必读**：§2（独占文件集）、§5（禁止事项）、§6（提示词）。
**上位文档**：`docs/frontend-plan-2026-09-14.md`（为什么）｜`docs/handoff/2026-09-15-frontend-work-checklist.md`（勾什么）｜`docs/frontend-visual-quality-2026-09-14.md`（长什么样）。

---

## 0. 一句话结论

**对话层上限 = 后端 1 + 前端 2**；前端两条按「接线 / 新建文件」切，不按文档切。
**子 Agent 层**：一个对话内最多 3 个子 Agent，且**写入文件集必须两两不相交**。
**并行开始前必须先完成的 step 0**：`frontend/**` 的 19 处未提交归零 + 依赖一次性装完。

---

## 1. 为什么不能"按 ABC 三份文档开三个对话"

那三份文档是**同一计划的三个视角**，不是三个互不相干的范围：计划给裁定、视觉给 token、工单给逐文件勾选项。三个 Agent 各读一份去改代码，会同时改 `App.vue` 与 `assets/theme.css` —— 冲突矩阵（工单 §4）对三条线都成立，等于没分工。

真正的并行边界只有一种：**文件所有权**。

---

## 2. 三条对话线与独占文件集

| 线 | 分支 | 独占可写 | **禁止碰** | 覆盖的步骤 |
|---|---|---|---|---|
| **A 主干（接线）** | `codex/fe-trunk` | `App.vue`、`components/*.vue` 全部既有面板、`assets/theme.css`、`package.json`、`package-lock.json`、`vite.config.js`、`lib/api.js`、新建的 `lib/http.js` `lib/artifacts.js` `lib/sessions.js`、`router/`、`views/` | `app/**`、`docs/handoff/2026-09-15-frontend-work-checklist.md` 之外的计划文档 | F1 F2 F3 F4 F5a F6 F7 V1 V2 V3 V4 |
| **B 叶子（只新建）** | `codex/fe-primitives` | `components/ui/**`、`lib/errcodes.js`、`tests/visual/**`、`playwright.config.js`、`.stylelintrc.json`、`assets/fonts/**`（从 `node_modules` 拷子集）、`vitest` 用例文件 | `App.vue`、任何既有 `*.vue`、`theme.css`、`package.json`、`vite.config.js` | V5 的 6 个纯 CSS 原语、V6 基建、V1 字体资产 |
| **C 后端（已在跑）** | `codex/data-file-catalog` | `app/**`、`scripts/**`、`migrations/**`、`docs/current-functionality-2026-09-10*.md` | `frontend/**` | R1 R2 R8 与 e2 检索裁定 |

A 与 B 的交集 = **空**。合并顺序固定：**B 先合入 A**（纯新增文件，零冲突），A 再在自己的 F7/V5 步骤里"接线"。

---

## 3. Step 0：并行开始前的三件事（① ③ 已完成，② 待做）

> **2026-09-15 已执行**：worktree 与快照基线已建好，事实如下，后续 Agent 不要重复做，也不要怀疑它们不存在。
>
> - `C:\Users\fengx\PycharmProjects\fe-trunk` → 分支 `codex/fe-trunk`；`C:\Users\fengx\PycharmProjects\fe-prims` → `codex/fe-prims`；两者基线同为 **`13e808d`**。
> - **建 worktree 时发现的真问题**：`codex/data-file-catalog` 的 HEAD 里 `frontend/src` 只有 9 个文件——7 个面板中的 5 个（`InsightPanel` `ApprovalPanel` `GraphPanel` `DashboardPanel` `DocumentPreviewModal`）、`assets/theme.css`、`lib/api.js`、`frontend/Dockerfile` **全是未跟踪文件**，只活在工作目录里。也就是说任何一次 clone 或 `git clean -fd` 都会拿到一个**三面板的旧应用**，而我此前所有文档描述的都是那七面板的现状。
> - 处置：先整目录备份到 `C:\Users\fengx\PycharmProjects\frontend-wip-backup-2026-09-15`（35 文件 / 4.60 MB），再用一次**不改任何文件内容**的快照提交把它们纳入版本控制（`13e808d`，17 个文件）。刻意排除两项：`src/assets/login-reference.png`（2.06 MB、源码 0 引用）与 `browser_data_quick.js`（一次性 Playwright 探针，硬编码 `C:/tmp/pwtest`），两者都只在备份目录里。
> - 构建实证（主树 `npm run build`）：`vite 8.0.16` / **82 modules / 314 ms** / `index.js` 185.30 kB（gzip 66.91）/ `index.css` 83.08 kB（gzip 16.78）；**两张登录页 PNG 共 2.37 MB 进了产物**（V2 换成 `login-earth.webp` 后可回收，见 §7 资产卫生）；产物里没有 `element-plus`，再次印证它是死依赖。
> - **两条线各自开工前的第一件事**：worktree 里**没有** `node_modules`，也**没有** `.env`（未跟踪文件不随 worktree 复制）。所以各线先 `cd frontend; npm ci`（**别用 `npm i`**，会改 lockfile），并且**不要**在 worktree 里连真后端跑 `npm run dev`——没有 `.env` 就没有后端配置，验收一律按工单 §8.1 用 Playwright 从磁盘 fulfill。
> - 主树的 `git status --porcelain -- frontend` 由 **19 → 2**（就是上面刻意排除的两个文件）。
> - 授权：用户 2026-09-15 已授权 A / B 两条线修改 `frontend/**`；`app/**` 仍然禁止。

1. ✅ **归零未提交**（已完成，见上面的快照 `13e808d`）。若将来再出现"多条线各自未提交"的局面，规矩不变：**先提交再并行**，因为未跟踪文件既不可 diff 也不可合并。
2. ⬜ **依赖一次装完，只此一次**（**待做**，A 线在 `fe-trunk` 里执行；B 线等它合过来）：
   - 运行期：`vue-router@4` `@fontsource-variable/manrope` `@fontsource-variable/jetbrains-mono` `lucide-vue-next` `dompurify`（`markdown-it` 已在依赖里，**不用装，要用起来**）
   - 开发期：`stylelint` `@playwright/test` `vitest`
   - 卸载：`element-plus`（死依赖，`main.js` 未注册、源码零引用、dist 产物零命中）
   - 顺手补 script 入口（当前 `scripts` 只有 `dev` / `build` / `preview`）：`lint`→stylelint、`test`→vitest、`test:e2e`→playwright。**没有这三条，§7 的护栏跑不起来。**
   - 装完立刻提交 `package.json` + lockfile，B 线 rebase 取用。**B 线若发现缺包，交清单给 A，不许自己装。**
3. ✅ **每线独立 worktree**（已建，见顶部）。旧闲置 worktree `C:\Users\fengx\.codex\worktrees\c99b\企业智脑`（detached 在 `765aeca`，工作树干净）**未动**，要回收由你确认后再 `git worktree remove`。

```powershell
cd C:\Users\fengx\PycharmProjects\企业智脑
git worktree add ..\fe-trunk -b codex/fe-trunk
git worktree add ..\fe-prims -b codex/fe-prims
# 闲置的旧 worktree（detached 在 765aeca，工作树干净）可回收：
# git worktree remove "C:\Users\fengx\.codex\worktrees\c99b\企业智脑"
```

每个 worktree 里各自 `npm ci`（**不要用 `npm i`**，会改 lockfile）。

---

## 4. 对话内多 Agent：能拆的与不能拆的

**判据（一句话）**：两个子 Agent 的**写入集不相交**，且合并后**不需要第三个 Agent 改接口**——两条里缺一条就别拆。
默认它们**共享同一工作目录**，所以写入集不相交是硬要求，不是建议。

### 4.1 适合拆（各写各的文件，合并即完整）

| 拆法 | 子 Agent 1 | 子 Agent 2 | 子 Agent 3 |
|---|---|---|---|
| B 线原语 | `UiButton` `UiField` `UiTabs` + 用例 | `UiTable` `UiDialog` + 用例 | `UiToast` + 过渡动画 + 用例 |
| 错误码字典 | `errcodes.js` 鉴权类码（`authentication_required`/`permission_denied`/`authorization_unavailable`） | 数据与文件类码（`invalid_filename`/`unsupported_chart_type`/`dataset_*`/`parse_failed` …） | 任务类码（`task_timeout`/`task_cancelled`/`queue_unavailable`/`model_unavailable` …） |
| 视觉基线 | 登录页五档 | 总览 + 喂料五档 | 问一句 + 异常五档 |
| 调研类 | 只读审计（不改文件） | —— | —— |

拆完由**父对话统一跑** `npm run test / lint / build`，再一次性提交。子 Agent 不许各自 `git commit`。

### 4.2 不能拆（同一件事的两半，拆开必返工）

- `lib/http.js` 的 401 分支 ↔ 各面板的接线（F3）
- `router/` 建表 ↔ `App.vue` 的侧栏与视图切换（V3）
- `ChatPanel.vue` 的图片正则 ↔ `ChartViewer.vue` 的 blob 绑定（F1）
- `theme.css` 的 token 改名 ↔ 全站引用（V1 / V4）——单 Agent 一次改完
- 任何"甲定义 schema、乙按 schema 写消费方"的成对改动
- F2 / F4 / F6 之间（都要 `App.vue`，见工单 §4 矩阵）

### 4.3 别指望并行更省事的

F1、F2、F6、V1、V2、V4 的**关键路径性质**决定单 Agent 串行最快：它们的产物互相依赖，拆开的协调成本高于收益。

---

## 5. 跨对话通用禁止事项

- 不 `git add -A`、`git reset --hard`、`git checkout .`、`git clean -fd`（会毁掉别的 Agent 的未提交工作，git 不可恢复）。
- A/B 线不写 `app/**`；C 线不写 `frontend/**`。需对方配合的项**只登记不实现**，写进 `docs/handoff/`。
- 引用后端只用**路由 / 符号名 / 稳定码**，不写行号（后端实时提交，行号必过期）。
- 不装新依赖（B 线）、不改 lockfile（B 线）、不跑迁移、不连生产库、不用真实文档做删除实验。
- 不做假数据、假删除、假权限；`admin` 判据不许来自 localStorage（C-3）。
- 子 Agent 报告的"新发现"必须能 `Test-Path` 且时间戳实取，否则不进任何文档（沿用后端 §13.5 的教训）。
- 冲突即停并报告，不强解、不覆盖对方改动。

---

## 6. 开场提示词（已外置，避免两份真源）

四条对话线（A 主干 / B 叶子 / C 后端交接 / D 独立验收）与子 Agent 派发模板全部在 `handoff/2026-09-15-frontend-startup-prompts.md`，路径与基线 commit 已填成实值，复制即用。
本文件只负责"谁能写哪些文件"；提示词只负责"怎么开工"。两边都改时，以本文件的独占集为准。

## 7. 合并协议（B → A → 主干）

1. B 线自测：`npm run build`（现存）+ `npm run test` / `npm run lint`（**由 step 0 补上 script 入口才存在**；没补就用 `npx vitest run` / `npx stylelint "src/**/*.{css,vue}"` 顶一次）→ 提交到 `codex/fe-prims`。
2. A 线 `git merge codex/fe-prims`（预期零冲突，因为文件集不相交）。
3. A 线做"接线"提交：V5 用原语替换面板原生控件；F7 用 `lib/errcodes.js` 替掉 7 处 `{{ error }}`。
4. 护栏必须当场跑：`stylelint`（裸色值/裸间距）+ Playwright 五档基线 + `vitest`（SSE canonical/legacy/未知事件、401 分支、XSS）。**视觉基线是唯一能在合并当场发现两条线互相打脸的手段**，不许跳过。
5. 若 A 需要 B 范围内改动（例如原语 props 不合用）：**A 提 issue 给 B，由 B 改**，A 不越界代写。

---

## 8. 并行度收益预估（诚实版）

| 阶段 | 可并行 | 说明 |
|---|---|---|
| step 0（1–2 天） | ❌ | 归零未提交 + 装依赖，天然串行 |
| F1→F3→V1（约 4–6 天） | ❌ | 全在 `App.vue` / `theme.css` 上 |
| V5 原语 + V6 基建（2–3 天） | ✅ | **B 线与 A 线唯一的重叠窗口**，约省 2 天 |
| F4→V3→V4→F5a→F7（5–7 天） | 部分 | 面板间可按「异常/自查/喂料」拆子 Agent，但都碰 `App.vue`，需 A 线内部串行 |
| F6 + V6 收尾（1–2 天） | ✅ | `lib/sessions.js` 与视觉基线互不相干 |

净收益：**约 2–3 天**，代价是多一套 worktree 协调与合并风险。所以「值得并行」的只有 B 线那一块，别为并行而并行拆三条前端线。
