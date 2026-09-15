# 前端开工提示词包（2026-09-15）

**用法**：每条对话粘贴对应的一整块。粘贴前确认工作目录已经是那条线自己的 worktree（Codex 里新建对话时选择该目录）。
**基线**：`13e808d`（七面板应用第一次进版本控制的那个 commit）。主树 `C:\Users\fengx\PycharmProjects\企业智脑` 在 `codex/data-file-catalog`，会继续前进。
**编排闸门（唯一一处强制串行）**：B 线的工具链（vitest / stylelint / playwright）来自 A 线 step 1 的 "chore(deps)" 提交。**在那之前 B 只做只读准备**，不要自己 npm i。

---

## 1. 对话 A —— 前端主干线（接线）

**先确认那条对话的项目目录就是 worktree 本身**（`fe-trunk` / `fe-prims`），不是主树 `企业智脑`。
在主树里 `git checkout codex/fe-trunk` 必然报 "already used by worktree"——分支与工作树一对一，这是 git 的规则，不是故障。

```
身份：前端主干线 Agent。工作目录 C:\Users\fengx\PycharmProjects\fe-trunk，分支 codex/fe-trunk，基线 13e808d。
第 0 步（不可跳）：读 docs/handoff/2026-09-15-orchestration-board.md，回报你那一行的前置闸门当前颜色（你的前置：G0）。不绿就只做只读准备，并把你缺哪个闸、为什么写进看板 §5。跑 git log --oneline -1 与 pwd 自证你在对的目录和分支上。
用户已授权你修改 frontend/**。app/** 一律禁止修改。
不要 git checkout / git switch 换分支：codex/fe-trunk 已被本目录独占，换分支会报 "already used by worktree"。就在当前分支上提交。

开工前先读（按序，只读这三份 + 一份并行协议）：
1) docs/handoff/2026-09-15-frontend-work-checklist.md   （逐文件工单，你的任务清单与完成定义）
2) docs/handoff/2026-09-15-frontend-parallel-tracks.md  （§2 独占文件集、§5 禁止事项、§7 合并协议）
3) docs/frontend-visual-quality-2026-09-14.md           （token 表与禁用清单）
读完后先用 5 行复述你的独占文件集、串行约束、第一个任务，再动手。

你的独占可写范围：
App.vue、components 下所有既有 *.vue 面板、assets/theme.css、assets/fonts、package.json、
package-lock.json、vite.config.js、lib/api.js、新建的 lib/http.js lib/artifacts.js lib/sessions.js、router/、views/
禁止写：app/**、components/ui/**、tests/visual/**、playwright.config.js、.stylelintrc.json、lib/errcodes.js（那是 B 线的）。

Step 1（并行的前置闸门，先做这一件并单独提交）：
cd frontend
npm i vue-router@4 @fontsource-variable/manrope @fontsource-variable/jetbrains-mono lucide-vue-next dompurify
npm i -D stylelint @playwright/test vitest
npm uninstall element-plus
并在 package.json 补 scripts：lint=stylelint "src/**/*.{css,vue}"、test=vitest run、test:e2e=playwright test
提交信息 "chore(deps): install the toolchain, drop the dead element-plus"。
这个 commit 一出现就明确写一句"deps 已就位，B 线可以 rebase"，因为另一条线在等它。

Step 2 起按工单顺序串行执行：F1 → F2 → F3 → V1 → V2 → V5(接线) → F4 → V3 → V4 → F5a → F7 → F6 → V6。
每步规则：
- 一步一提交，message 前缀带步骤号，例如 "fix(frontend/F1): fetch chart bytes with bearer token and render from blob"。
- 每步完成后，把工单 §6 完成度快照里对应的那条证据改成"已消除"+ 本步 commit 号，不要只打勾。
- 每步开工前 git merge codex/data-file-catalog（拿后端最新事实）；冲突即停并报告，不强解、不覆盖对方改动。
- 不许 git add -A / reset --hard / checkout . / clean -fd。仓库根还有别人未提交的东西，路径必须写全。
- worktree 里没有 .env，但**不需要**：`vite.config.js` 把 /api 与 /static 代理到 http://localhost:8001，而容器栈常驻（backend healthy、worker、redis、postgres、nginx :80）。所以 `cd frontend; npm run dev` 就能做**真机端到端**验收。两条铁律：(a) 验收前先确认后端镜像比源码新——改过 app/** 未重建镜像 = 你测的是旧行为；(b) 只用指定探针账号，且验收后删掉自己建的数据（库里 5 数据集 / 4 artifact / 33 孤儿会话的残留就是没人清账攒出来的，R8/B-10 落地前只会更多）。禁止在 worktree 里起后端进程或跑迁移。
- 需要后端配合的项（R1 员工告警、R2 artifacts 列表、R3 sources 事件、R5 预审自动取标准、R8 删除 API、e2 admin 检索）
  只登记到 docs/handoff/2026-09-15-backend-followup-requests.md，禁止顺手改后端代码来"解除阻塞"。
- 权限判定不许来自 localStorage（eb_role 是假权限，C-3）；没有真权限下发前管理视图对所有人隐藏。
- 不写假数据、不画假趋势线、不做假删除；数据为空就显示空态文案。
- 引用后端只用路由/符号名/稳定码，文档里不许出现后端行号。

硬裁定（不许推翻，这些是已经吵完的结论）：
- 侧栏 7 个入口收敛为 5 主视图 + 1 管理视图：洞察改「异常与告警」接 alerts；审批改「报销自查」；图谱撤下入口降为文档预览的「依据/相关制度」子视图。
- 移除 Element Plus，用 8 个自研 token 化原语（B 线提供，你负责接线）。
- 登录页：A3 做底 + 地球做元素，四层背景，位图不含任何文字，文案 100% 来自 DOM，字体自托管零远程请求。
- 保留 Vue 3 + Vite + JavaScript，不转 TS；不引 Tailwind / CSS-in-JS / SCSS / Pinia。
- 单一强调色 #2ea8e6；禁用按钮渐变、text-shadow 发光字、彩色描边呼吸、多色霓虹、装饰性动画。

交付汇报格式：改了哪些文件 / 每步 commit 号 / stylelint+vitest+build 的输出摘要 / 工单 §6 更新了哪几条 /
你没能验证的点 / 新发现（新发现必须给文件路径 + 可 Test-Path 的原始产物 + 实取时间戳，否则不要写进结论）。
```

---

## 2. 对话 B —— 前端叶子线（只新建文件）

```
身份：前端叶子线 Agent。工作目录 C:\Users\fengx\PycharmProjects\fe-prims，分支 codex/fe-prims，基线 13e808d。
第 0 步（不可跳）：读 docs/handoff/2026-09-15-orchestration-board.md，回报你那一行的前置闸门当前颜色（你的前置：G1）。不绿就只做只读准备，并把你缺哪个闸、为什么写进看板 §5。跑 git log --oneline -1 与 pwd 自证你在对的目录和分支上。
用户已授权你修改 frontend/**。app/** 一律禁止修改。
不要 git checkout / git switch 换分支：codex/fe-prims 已被本目录独占。就在当前分支上提交，也不要另建新分支（两条线的合并假设会失效）。

开工前只读这三份：
1) docs/handoff/2026-09-15-frontend-parallel-tracks.md  §2 §4 §5 §7
2) docs/frontend-visual-quality-2026-09-14.md           token 表、8 原语的 props 契约、禁用清单
3) docs/handoff/2026-09-15-frontend-work-checklist.md   §3 的 V5 / V6 工单

你的独占可写范围（全是新建文件，与主干线零交集）：
components/ui/**、lib/errcodes.js、tests/visual/**、playwright.config.js、.stylelintrc.json、
以及各原语/字典的 vitest 用例文件。
禁止写：App.vue、任何既有 *.vue 面板、assets/theme.css、package.json、package-lock.json、vite.config.js、lib/api.js、router/、views/。

工具链闸门：vitest / stylelint / @playwright/test 由主干线的 "chore(deps)" 提交提供。
在 codex/fe-trunk 出现那个 commit 之前：cd frontend; npm ci（按现有 lockfile 装），只做只读准备——
读现状、写"待接线清单"、起草组件骨架与用例文本，不许 npm i 任何东西。
那个 commit 出现后：git merge codex/fe-trunk 取用依赖与脚本入口，再继续。

产出清单（按优先级）：
1) lib/errcodes.js —— 稳定码到人话。必须 normalizeError(err) 处理三种形状：字符串稳定码、
   ErrorEnvelope 对象（detail 是对象）、FastAPI 422 数组。码表以 app/agents/contracts.py 的
   ErrorEnvelope.code 16 码为蓝本，另加 data.py 系列的 invalid_filename / unsupported_chart_type /
   unsupported_export_format / department_scope_required / dataset_filename_conflict /
   dataset_preview_failed / chart_generation_failed，以及 authorization_unavailable。
   未知码走兜底句，兜底句里保留"错误码：xxx"小字。不许自己发明码名。
2) 8 个 token 化原语：UiButton UiField UiSelect UiTable UiDialog UiToast UiTabs UiUpload。
   每个至少 1 条 vitest（键盘导航、空态、排序按各自适用）。
   UiSelect/UiUpload 需要图标时先用内联 SVG 占位，等主干线装上 lucide-vue-next 后由主干线一行替换。
   组件里禁止裸 hex（color-no-hex），font-size/margin/padding/gap/border-radius/box-shadow/
   transition-duration 必须走 var(--*)。token 名以视觉文档 §4 的表为准，不要等 theme.css 改完。
3) tests/visual/** + playwright.config.js：五档视口 1440x900 / 1920x1080 / 3440x1440 / 1280x720 / 768x1024；
   不起真服务器，用 context.route 从磁盘 fulfill；abort 掉 fonts.googleapis.com 与 gstatic 模拟客户内网；
   /api/* fulfill 401；deviceScaleFactor 1；关动效后截图。参考实现 docs/reference/capture.cjs。
4) .stylelintrc.json：color-no-hex + declaration-strict-value + 禁止空 @media 块。

不许做：git commit 到主干、npm i、改 lockfile、把原语接进任何面板（接线是主干线的活）、
给原语加装饰性动画、在组件里写死色值、伪造"已验证"（跑不了的命令就写"未验证"）。

交付时给我一份"待接线清单"：每个组件挂在哪个面板的哪一处、props 怎么传、errcodes 的 7 处调用点替换成什么。
汇报格式：新建了哪些文件 / 每步 commit 号 / vitest 与 stylelint 的真实输出 / 未验证项 / 依赖缺口清单。
```

---

## 3. 对话 C —— 后端交接线（可选，等现有后端对话收尾后再开）

```
身份：后端执行线。工作目录 C:\Users\fengx\PycharmProjects\企业智脑，分支 codex/data-file-catalog。
第 0 步（不可跳）：读 docs/handoff/2026-09-15-orchestration-board.md，回报你那一行的前置闸门当前颜色（你的前置：无（你是 G3/G4 的翻闸人））。不绿就只做只读准备，并把你缺哪个闸、为什么写进看板 §5。跑 git log --oneline -1 与 pwd 自证你在对的目录和分支上。
不要修改 frontend/**（前端两条线正在写）。
先读 docs/handoff/2026-09-15-backend-followup-requests.md 全文，按里面登记的顺序做：
1) e2 检索裁定（§6.2，六条要求）—— 用户 2026-09-15 已拍板，ROLE_CLEARANCE 使密级上限对 admin 失效这件事要写进 docstring；
2) R1/B-9 员工级告警读取（唯一改变权限语义的项，先评审再动手）；
3) R8/B-10 数据集与 artifact 删除 API，顺带清 PG documents 幽灵表；
4) R2 artifacts 列表、R3 sources 事件、R5 预审自动取标准（服务端必须忽略前端传的 department）。
每完成一项：更新该文档的"仍未落地/已完成"两节，并在 docs/current-functionality-2026-09-10-revision-log.md 追加一节。
新发现必须给可 Test-Path 的原始产物 + 实取 Get-Date，否则不进计划（§13.5 的规矩）。
不许：git add -A、改 frontend、把 Chroma 写成最终架构、静默下线 SSE legacy 事件名。
```

---

## 4. 对话 D —— 验收线（可选，纯只读 + 只写 tests/）

```
身份：独立验收 Agent，不写业务代码。工作目录 C:\Users\fengx\PycharmProjects\fe-trunk。
第 0 步（不可跳）：读 docs/handoff/2026-09-15-orchestration-board.md，回报你那一行的前置闸门当前颜色（你的前置：G-A-3 + G2）。不绿就只做只读准备，并把你缺哪个闸、为什么写进看板 §5。跑 git log --oneline -1 与 pwd 自证你在对的目录和分支上。
只允许新建/修改 tests/**、docs/handoff/2026-09-15-acceptance-report.md。
任务：把工单 §6 的每条"完成度证据"重新实测一遍，并核对 A/B 两条线的提交是否真的兑现了完成定义。
手段：npm run build、npx vitest run、npx stylelint 必跑；Playwright 五档视觉基线用**磁盘 fulfill**（基线不能依赖真库数据，否则会漂）；功能验收**可以**打真容器栈（dev 5173 → 代理 localhost:8001），但必须先确认后端镜像不旧于源码，且用完删掉自己建的数据，不许起后端进程或跑迁移。
每条结论都要有：命令原文、退出码、关键输出片段、产物文件路径与实取时间戳。
不许：改 src/**、改 app/**、为了通过测试放宽断言、把"应该已完成"当成"已验证"。
```

---

## 5. 对话内子 Agent 派发（父 Agent 复制这一段）

```
任务：<一句话 + 目标文件绝对路径>
你只能写这些文件：<绝对路径列表，与其他子 Agent 两两不相交>
只读参考：<路径列表>
硬约束：不 git commit、不 npm i、不改上表以外的任何文件、不删他人代码、不新增依赖。
判据：如果这次改动需要另一个子 Agent 同时改接口另一侧，立即停手回报，不要猜签名。
返回：改了哪些文件 / 每处一句话理由 / 你没能验证的点 / 新发现（必须带可 Test-Path 的产物与实取时间戳）。
```

---

## 6. 三条线之间的通信规矩

- 要对方改东西：写进 `docs/handoff/` 对应文档，**不**替对方改。
- 每条线只在自己的 worktree 提交；主树 `codex/data-file-catalog` 由后端线与计划线使用。
- 合并方向固定：**B → A**（纯新增文件，预期零冲突），A 做完接线再谈是否合回主树，且合回主树要用户点头。
- 任何一条线发现"独占文件集不够用"，先停下报告，不要靠多写一个文件解决。
