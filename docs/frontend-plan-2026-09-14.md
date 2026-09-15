# 企业智脑 前端实施计划（2026-09-14）

**状态**：计划文档。本轮未改动 `frontend/`、`app/`、`chroma_db/` 下任何文件。
**引用口径**：后端一律用符号名 / 路由 / SSE 事件名，不写行号（另一路对话正在实时提交后端）。
**输入依据**：`frontend-workspace-audit-2026-09-14.md`（含 §12 并发订正）、`handoff/2026-09-14-frontend-workspace-fix-tasks.md`、`handoff/2026-09-14-backend-interface-requests.md`、`api/contract-v1.md`、`frontend-visual-quality-2026-09-14.md`、`reference/`（登录页美术实验，可重跑）。

## 目录

- 0. 一页速览
- 1. 角色旅程验证
- 2. 工作区映射表
- 3. 技术栈与依赖决策
- 4. 设计 Token 与视觉规范
- 5. 登录页专项方案
- 6. 分阶段实施计划
- 7. 资产与构建卫生
- 8. 测试策略
- 9. 风险登记表与冲突面
- 10. 不做清单
- 11. 验收清单

---

## 0. 一页速览

**改什么**

- 侧栏 7 个入口收敛为 **5 主视图 + 1 管理视图**：洞察改名「异常与告警」、审批改名「报销自查」、图谱撤下入口降为文档预览的「依据 / 相关制度」子视图。
- 修 5 个 P0 阻断级缺陷：图表必然不显示、切一次侧栏丢会话状态、全站无 401 处理、历史从未上后端且退出即清空、总览用假数字与三个页面互相打脸。
- 登录页与全站视觉重建：四层背景合成 + token 化规范，**位图不再承载任何文字**。
- 移除 Element Plus（查实为死依赖），自建 8 个 token 化 UI 原语。
- 补 `vue-router`、自托管字体、`stylelint`、Playwright 视觉回归。

**为什么**

- 三页"不知道干嘛的"根因：它们是 2026-09-07 升级计划里三个阶段的最小接口占位，被镀层后留在了侧栏。
- 视觉"廉价"根因：文案被烙进位图，`theme.css` 里三轮 `.reference-login` 覆盖与位图对抗，最终把 DOM 文案整段 `display:none`。

**几阶段**：F1→F6（工作区修复）与 V1→V6（视觉与工程）两条线，合成 12 个可验收步骤，见 §6。

**后端影响**：F1–F5a、F6、V1–V6 **全部零后端**。需要后端配合的一律只登记不实现，编号 R1–R6 / B-1…B-9 / C-1…C-3。

**不做什么**：见 §10。

---

## 1. 角色旅程验证

方法：以三个真实角色，各走 2–3 条任务旅程，逐步走**§2 的新视图**，回答三件事——现有裁定接得上吗、在哪一步断、需要哪个 R/B/C。**本节不重做调研，只验证与补漏。**

### 1.1 一线业务员工（财务专员小张）

**J1「住宿 680 一晚超标吗」**

- 走「问一句」：对话主链路真实，`_approval_worker_node` 依次做自然语言抽金额 → 检索制度原文 → `extract_standard()` 抽最严格限额 → `build_precheck`，能出结论。
- 断点 1：结论里的制度原文**不可点击核对**，因为 `/ask` 从不发 `sources` 事件（B-2 / R3）。
- 断点 2：他不会主动去「报销自查」，因为那页要他自己填"标准 500"，比对话更笨。
- 结论：**支持既有裁定**。审批页降级为自查工具成立；"标准自动来自制度"依赖 B-8 / R5，落地前界面必须写明"需手填标准"。

**J2「这个月我部门花超了没」**

- 走「异常与告警」：`GET /alerts`、`GET /alerts/rules`、`POST /alerts/check` 全部经 `_require_alert_management()`，普通员工 **403**（B-9 / R1）。
- 降级方案（R1 未落地时）：非管理员显示「暂无可见异常」+ 一句"异常监控由管理员配置"，**不显示假数据、不显示空规则表**。
- 结论：这条旅程是 R1 优先级最高的直接理由，也是唯一改变**权限语义**的需求。

**J3「把上周那份销量分析再发我一次」**

- 现状：`ArtifactRegistry` 只有 `register` / `get` / `get_active` / `soft_delete`，无查询方法，元数据落在 `.artifact-metadata.json` → 前端只能"重新问一遍"。
- 走「交成果」：依赖 B-1 / R2。
- 结论：**不做假列表**。B-1 落地前该视图不上线。

### 1.2 部门主管（销售总监）

**J4「上周销量为什么掉」**

- 走「问一句」：Data Agent 真实。但他在「数据」页选定的数据表**在对话侧不可见不可改**，AI 用的是另一张表，结论对不上，而他无从纠正。
- 定性：这是**跨视图上下文不共享**，纯前端可修（面板联动 + 顶栏常驻上下文），不依赖后端。
- 结论：**既有裁定未覆盖，本计划补入 V3**。这是老板和主管最容易感知的一类 bug。

**J5「谁把差旅标准改了」**

- 走「管系统」：`/users*`、`/alerts/rules` 现状可用，审计在 `app/common/audit.py`。
- 断点：前端 `isAdmin` 只来自 localStorage 的 `eb_role`（C-3）——主管清一下缓存就能看到管理入口，是**假权限**。
- 结论：界面可先做，但**必须等 C-3 权限下发才能上线**；未上线前对所有人隐藏，并在本文档标注。

**J6「每月 5 号给我一份团队日报」**

- `daily_report()` 有实现但**无 HTTP 路由**（B-6），只有定时任务会跑。
- 结论：前端不做日报视图，等 B-6；且 B-6 需先拆分推送副作用，不能直接挂路由。

### 1.3 老板 / 决策者（周总）

**J7「打开电脑给我看今天最该关注的一件事」**

- 现状总览：文档数与数据表数来自真实接口，**洞察数与审批数硬编码，趋势线手写乘数**（P0-5）→ 与三个页面互相打脸。
- 新方案：总览改为每个视图的真实待办计数 + 一条「今天最该看的一件事」，数字全部来自 alerts + catalog + data-files，属 A 档，零后端。
- 断点：真趋势需要 B-7 最小聚合接口。**在 B-7 落地前不画趋势线，画空态**，不用手写乘数冒充。
- 结论：这是信任级问题，**F5 优先于一切美化工作**。

**J8「3440 超宽屏上给客户演示」**

- 现状 `background-size: 100% 100%` → 位图被横向拉伸，文字发糊，地球变形；登录卡 `height: 46.1%` 在 1280×720 上溢出裁切。
- 结论：§4/§5 的四层背景，地球以 `mix-blend-mode: screen` 叠加并保持原始比例，任意分辨率锐利。

**J9「这是内网机器，别给我看转圈的字体」**

- 现状代码里有 Google Fonts 远程 `@import` → 客户内网加载不到，首屏字体抖动甚至白屏。
- 结论：V1 改自托管，Manrope + JetBrains Mono 合计约 95KB，**零远程请求**。这属交付事故，不属风格偏好。

### 1.4 旅程对既有裁定的影响

- J1 / J2 / J3 / J5 / J6 / J8 / J9：**支持**既有裁定，无推翻。
- J4：**补漏**——数据上下文跨视图共享纳入 V3。
- J7：**补一条硬约束**——B-7 未落地前总览不得出现任何趋势线（含空图占位）。
- 需修正的旧表述：图谱持久化本轮已由其他 Agent 补齐（`JsonPersistenceAdapter` + `KNOWLEDGE_GRAPH_STORE_PATH`），**"重启即清空"已失效**；撤下入口的理由收敛为三条：无图形界面、无自动抽取（关系仍需人录）、`confirm()` 无路由无按钮。 **注意限定**：持久化仅在代码层成立，本次部署未配置 `KNOWLEDGE_GRAPH_STORE_PATH`，写入仍返回 503。

---

## 2. 工作区映射表

| 旧入口 | 现状定性 | 新视图 / 改名 | 入口去留 | 后端依赖 | 未上线时的降级显示 |
|---|---|---|---|---|---|
| 总览 | 演示+真实混合 | 保留为默认视图 | 保留 | 趋势线需 B-7 | 真实计数 + 空态，**不画趋势线** |
| 文档 | 已实现+有风险 | 并入「喂料」 | 合并 | 真实进度需 B-3 | 进度改文字态"已提交，解析中"，不用假百分比 |
| 数据 | 已实现+部分 | 并入「喂料」 | 合并 | 无 | 数据上下文选择器常驻顶栏 |
| 洞察 | 演示/骨架 | 改名「异常与告警」 | 保留（改名） | 员工侧 B-9 / R1 | 非管理员显示「暂无可见异常」 |
| 图谱 | 演示/骨架+有风险 | 撤下，降为文档预览「依据 / 相关制度」子视图 | **移除入口** | 独立工作区需 C-2 | 不显示 |
| 审批 | 演示/骨架 | 改名「报销自查」 | 保留（改名） | 自动取标准需 B-8 / R5 | 标注"需手填标准"；**禁止前端传 `department`** |
| 对话 | 已实现+有风险 | 改名「问一句」 | 保留 | 引用条需 B-2 / R3 | 无来源时不显示引用条 |
| （新增） | — | 「交成果」 | 新增 | B-1 / R2 | 不做该视图 |
| （新增） | — | 「办待办」 | 新增 | C-1 工单模型 | 不做该视图 |
| （新增） | — | 「管系统」 | 新增 | C-3 权限下发 | 对所有人隐藏 |

**三个"不知道是干嘛的"页面，一句话答案**

- **洞察**：本该是异常告警的界面，实际是一张要用户手工喂 AI 的表单；真引擎（`evaluate_all()` 遍历 `data/`、`_ai_analysis()` 归因、落 `alerts` 表、IM 推送、`app/scheduler/jobs.py` 定时）早就存在，**唯独没有界面**。
- **图谱**：名字叫图谱，页面上没有图——四个输入框加一个三元组列表，无节点无边无布局无下钻。判断依据：**没有任何员工会手工录入公司关系**。
- **审批**：只做减法的计算器，`build_precheck` **恒返回 `approved: False`**，它不审批任何东西；更强的版本挂在对话里，所以用户会发现"在对话里问比在审批页点按钮更可信"。

---

## 3. 技术栈与依赖决策

### 3.1 保留 / 新增 / 不引入

| 项 | 决策 | 理由 |
|---|---|---|
| Vue 3.5 + Vite 8 + JavaScript | 保留，**不全量转 TS** | 7 个面板 + 60KB CSS 的重写风险大于收益；用 JSDoc 与 `vitest` 覆盖关键逻辑即可 |
| `vue-router@4` | 新增 | 现在 7 个工作区靠 `shallowRef` 手切，**没有 URL**：刷新回总览、无法把某个会话或告警发给同事、浏览器后退键失效 |
| `@fontsource-variable/manrope`、`@fontsource-variable/jetbrains-mono` | 新增 | 约 95KB 自托管，替换远程 `@import`（见 J9） |
| `lucide-vue-next` | 新增 | 现在图标来源混杂：emoji、手写 SVG、硬编码函数（DocPanel 里还有按公司文件名分支的图标函数） |
| `markdown-it` + `dompurify` | 新增 | 替换 `ChatPanel.vue` 手写的 `renderMd`。现状虽已转义 `&<>`，但 `[x](javascript:alert(1))` 仍是洞 |
| Tailwind / CSS-in-JS / SCSS | **不引入** | §4 的 token 体系已够；引入等于把样式真源从 `theme.css` 搬走，与"清覆盖债"目标相反 |
| Pinia | **不引入** | 单 store 场景是额外抽象层。用模块级 `shallowRef` store + router query 即可承载"当前数据上下文"（J4） |
| `stylelint` / `@playwright/test` / `vitest` | 新增 | 见 §8 |
| Element Plus | **移除** | 见 3.2 |

### 3.2 Element Plus 移除的证据链

1. `frontend/src/main.js` 全文只有 `createApp(App).mount('#app')` 与 `import './assets/theme.css'`，**未注册** Element Plus。
2. `frontend/src/**` 内对 `element-plus` / `El*` 组件的引用：**0 命中**。此前统计到的 9 个 `el-*` 是 `panel-grid`、`panel-footer`、`panel-status` 等类名的正则误伤。
3. `frontend/dist/assets/*.js` 中 `element-plus|ElMessageBox|el-button`：**0 命中** → 它从未进入产物。
4. 结论：它唯一的作用是挂在 `package.json` 依赖里，让 Docker 的 `node:20-alpine` 阶段 `npm ci` 多装几十 MB、拉长构建。

### 3.3 替代方案：8 个自研 token 化原语

放 `frontend/src/components/ui/`。

| 原语 | 覆盖场景 | 难度 | 边界说明 |
|---|---|---|---|
| `UiButton` | 全站 | 低 | 变体 primary / ghost / danger；禁用态与 loading 态 |
| `UiField` | 登录、筛选、自查表单 | 低 | label + 前置图标 + 错误位 + `:focus-within` 环 |
| `UiSelect` | 部门 / 指标 / 告警规则选择 | 中 | 键盘导航、类型搜索、无障碍列表 |
| `UiTable` | 数据预览、告警列表、catalog | 中 | 排序 + 空态 + 行操作；**不做虚拟滚动** |
| `UiDialog` | 确认弹窗、文档预览 | 中 | 焦点陷阱、Esc 关闭、`role="dialog"`；修掉现有确认弹窗乱码 |
| `UiToast` | 401 提示、上传结果 | 低 | 队列 + 语义色，替代 `alert()` |
| `UiTabs` | 喂料视图（文档/数据）、版本切换 | 低 | 与 router query 同步，可分享链接 |
| `UiUpload` | 文档与数据上传 | 中 | 拖拽 + 真实进度（真实进度依赖 B-3） |

**必须写进排期的代价**

- 表格虚拟滚动、日期选择器键盘导航若将来需要，要自己写，约 **3–5 人日**。
- 判断依据：DataPanel 的表格是"查询结果预览"，不是在线 Excel，不需要万行虚拟滚动。
- 退路（不推荐）：只按需引 Element Plus 的 `Table` + `DatePicker`。副作用：它的浅色后台审美与深色 token 体系天然对立，`theme.css` 里那三轮 `.reference-login` 覆盖就是同类对抗留下的债，会重演。
- **默认假设（待确认）**：按"自研 8 原语"排期。若你希望省这 3–5 人日，只需说明，我把退路方案补成正式条目。

---

## 4. 设计 Token 与视觉规范

所有值进 `:root`，组件里不出现裸值；由 `stylelint` 的 `color-no-hex` + `declaration-strict-value` 强制。

### 4.1 色板

| 用途 | Token | 值 |
|---|---|---|
| 表面 | `--surface-0` | `#05080f` |
| 表面 | `--surface-1` | `#0a1120` |
| 表面（玻璃卡） | `--surface-2` | `rgba(13, 30, 54, .60)` |
| 表面（浮层） | `--surface-3` | `rgba(255, 255, 255, .045)` |
| 文字 | `--text-hi` / `--text` / `--text-mute` | `#eef3fb` / `#a8b7cc` / `#8494ab` |
| 描边 | `--line` / `--line-strong` | `rgba(150,174,208,.14)` / `rgba(150,174,208,.26)` |
| 强调 | `--accent` / `--accent-hi` / `--accent-ink` / `--accent-ring` | `#2ea8e6` / `#57c4f5` / `#02121e` / `rgba(46,168,230,.20)` |
| 语义 | `--ok` / `--warn` / `--danger` | `#37c08c` / `#d9a33c` / `#f0687c` |

**单一强调色**是硬规则：全站只有 `--accent` 一个品牌色，语义色只用于状态，不做装饰。

### 4.2 尺度

| 维度 | 阶梯 |
|---|---|
| 间距（8pt） | 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 |
| 圆角 | 6 / 10 / 16 / 999 四档 |
| 字阶 | `clamp(30px, 2.6vw, 44px)` / 20 / 14 / 13 / 12，**最小 12px** |
| 行高 | `--lh-body: 1.65` |
| 阴影 | 3 档（卡片 / 浮层 / 弹层） |
| 动效 | 120ms / 200ms，`cubic-bezier(.2, .7, .3, 1)` |

### 4.3 字体

- `--ff-sans: "Manrope", "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei", system-ui, sans-serif`
- `--ff-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace`
- 数字一律 `font-variant-numeric: tabular-nums`（表格、计数、金额对齐的关键，也是"专业感"最便宜的一招）。
- **自托管，禁止远程 `@import`。**

### 4.4 交互与无障碍

- `:focus-visible { outline: 2px solid var(--accent-hi); outline-offset: 2px }`
- 输入框 `:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-ring) }`
- 断点：`1180` / `960`（单列，卡 max-width 420px）/ `640`（竖向遮罩、收 padding）/ `max-height: 720`（压缩卡内间距，治笔记本溢出）。
- 支持 `prefers-reduced-motion`；**不留空 `@media`**。
- 表单错误用 `role="alert"`，不用颜色单独承载信息。

### 4.5 禁用清单（写死，stylelint 与 review 双重把关）

- 按钮渐变（主按钮用纯色 `--accent` + `inset 0 1px 0 rgba(255,255,255,.22)` 提亮）
- `text-shadow` 发光字
- 彩色描边呼吸、多色霓虹阴影
- 装饰性动画（动效只用于状态反馈）
- 组件里出现裸 hex / 裸 px 间距

---

## 5. 登录页专项方案

### 5.1 现状解剖（证据）

| 问题 | 证据 | 后果 |
|---|---|---|
| 文案烙进位图 | `login-background.png` 1672×941 含品牌锁定、主标题、副标题、三个能力图标、三张玻璃数据卡、右上 tagline、ENTERPRISE BRAIN 进度条 | 文案不可改、不可本地化、改一个字要重出图 |
| 位图被强制拉伸 | `background-size: 100% 100%` | 非 16:9（含 3440×1440）必糊、地球变形 |
| DOM 文案是死的 | `theme.css` 三轮 `.reference-login` 覆盖，末段 `display:none` 掉 `auth-atmosphere` / `auth-brandbar` / `auth-hero` | 60KB CSS 里养着一堆永不显示的节点 |
| 卡片固定比例定位 | `top:25.3%; right:3.8%; width:clamp(320px,24.3vw,470px); height:46.1%` | 1280×720 溢出裁切 |
| 死资源进包 | `login-reference.png` 2.1MB 零引用但被打进 dist | 部署包变肥 |

### 5.2 美术方向裁定：A3 做底 + 地球做元素

不是三选一，因为三个都各自有天花板：

- **纯 A3（全 CSS）**：做不出点阵地球，品牌识别度归零 → 视觉上限最低。
- **纯 A1 / A2（整张位图当背景）**：位图必然同时承担美术与文字，非 16:9 就得糊或裁 → 上限被位图锁死。
- **拆开（采用）**：CSS 负责色与形，位图只负责"光"。

A1 与 A2 的关系：A2（模型重生无字原图）需要图像 API 密钥，当前环境不可用；A1 唯一缺陷是去字区的涂抹残影，而**该残影位于左侧文字区，裁成地球元素时被整块丢掉，缺陷被方案本身吸收**。故用 A1 产物裁切，A2 留作将来有密钥时的升级路径。

### 5.3 四层背景（分辨率无关）

| 层 | 选择器 | 职责 | 关键实现 |
|---|---|---|---|
| L0 | `.bg__base` | 纯 CSS 渐变基底，永远不糊 | 深色 radial 光 + 竖向 linear，`#070d18 → --surface-0 → #02040a` |
| L1 | `.bg__art` | 地球位图，只负责"光" | `mix-blend-mode: screen`；`background-size: auto 104%`；**绝不 `100% 100%`** |
| L2 | `.bg__grid` + `.bg__noise` | 版面骨架与质感 | 网格用 `mask-image` 只落在文字侧；噪点用内联 SVG `feTurbulence`（去饱和 + `overlay` + opacity≈.05）打散渐变色带 |
| L3 | `.bg__scrim` | **只负责文字对比度** | 左侧横向压暗 + 渐晕；不再负责藏图 |

`mix-blend-mode: screen` 会吃掉黑色，**等于免抠图**：不需要 alpha 通道，位图直接叠在任意 CSS 基底上都能融合。`.bg` 上加 `isolation: isolate` 把混合限制在背景容器内。

噪点这一步是暗色大面积不显廉价的关键，成本是一个约 300 字节的数据 URI。

### 5.4 页面结构

```
main.login
├── div.bg            （aria-hidden，五层背景）
├── header.brand      六边形 mark + 企业智脑 + 竖线 + 等宽 Enterprise Brain
├── div.stage         grid: minmax(0,1fr) auto
│   ├── section.pitch 2px 强调色短横 + h1 + 副句
│   └── section.card  玻璃卡：radius 16 / border rgba(0,200,255,.20) / blur(20) saturate(120%)
│                     宽 384px、padding 48px 32px、高度由内容决定
│       h2 欢迎回来 · p 使用企业账号登录工作台
│       .alert[hidden] · 2×.field（图标 + 眼睛）· .row（记住我 / 忘记密码）
│       .submit 纯色强调色 · .card__foot 联系管理员开通
└── footer.foot       左：绿色盾 badge「本机部署 · 数据不出内网」+「企业内网专用」
                      右：等宽 v0.9.3 + 节点 EB-01
```

**有意删掉**：三个能力图标、ENTERPRISE BRAIN 进度条、DOM 手绘地球与三圈 orbit。理由：它们不承载功能，且正是三轮 CSS 覆盖的成因。
**保留**：三张数据卡作为美术装饰（已定），烙在地球元素里，不参与布局、不接后端。

### 5.5 资产规格

| 资产 | 规格 | 预算 |
|---|---|---|
| `login-earth.webp` | 1020×941，实测 **81KB** | ≤220KB |
| `login-mobile-atmosphere` | 移动端单独裁切 | ≤120KB |
| `login-background.png` | **退役**，由 earth 取代 | — |
| `login-reference.png` | **删除**（零引用） | — |
| `hero.png` | 343×361 旧图，确认无引用后删除 | — |

生成脚本已可重跑：`docs/reference/make_plate.py`（去字底图）→ `docs/reference/make_element.py`（裁地球 + 羽化 + WebP）。参考稿 `docs/reference/login-v2.html` 与五档截图 `docs/reference/shots/v2-*.png` 已产出，可作为 V2 的实现基线。

### 5.6 后端影响

**零。** `isLoggedIn = shallowRef(false)`，登录页无需后端即可完整渲染。唯一会牵扯后端的选项（把假指标换成真实部署信息）**已明确不做**。

---

## 6. 分阶段实施计划

### 6.1 串行约束（不可违反）

- F2 / F3 / F4 / F6 都要改 `frontend/src/App.vue`；F4 与 F5 都要动 `InsightPanel.vue`。
- **按 F1 → F2 → F3 → F4 → F5 → F6 串行合入，不得并行开分支改同一文件。**
- 只允许改 `frontend/src/**` 与 `frontend/vite.config.js`、`frontend/package.json`；**不修改 `app/**` 下任何文件**。需要后端配合的项只登记不实现。
- 不得回退或覆盖他人改动，遇到冲突停下来报告，不要强解。

### 6.2 合并工单表（F 线 = 工作区修复，V 线 = 视觉与工程）

| 步 | 线 | 目标 | 涉及文件 | 完成定义（可验证） | 需后端 | 前置 | 风险 / 回滚 |
|---|---|---|---|---|---|---|---|
| 1 | F1 | 图表恢复显示 | `components/ChartViewer.vue`、`lib/artifacts.js`(新) | 对话生成图表后 100% 可见；带 token 取 blob 渲染成功 | 否 | 无 | 放宽正则可能误匹配非图表 URL / 回滚正则 |
| 2 | F2 | 对话页生命周期 | `App.vue`、`components/ChatPanel.vue` | 切走再回来会话与滚动位置不丢；`approve()` 状态复位；所有请求检查 `response.ok` | 否 | 无 | 与 V3 的 router 迁移冲突 / 先保留 `shallowRef` 切页 |
| 3 | F3 | 统一鉴权与 401 | `lib/http.js`(新)、`App.vue`、各面板 | 4 套鉴权收敛为 1 个 axios 实例；401 → 清会话 + Toast + 回登录；`expires_in` 到期前提示 | 否 | 无 | 漏改某面板导致双轨 / 保留旧封装一版 |
| 4 | V1 | Token 与字体落地 | `assets/theme.css`、`assets/fonts/`、`vite.config.js` | `:root` 全量 token；`stylelint` 零违例；**零远程字体请求** | 否 | F3 | 变量重命名波及全站 / 保留旧名别名一版 |
| 5 | V2 | 登录页重建 | `App.vue`(auth 分支)、`assets/login-earth.webp` | 五档截图无裁切无拉伸；**位图不含任何文字**；文案 100% 来自 DOM | 否 | V1 | `screen` 混合在旧浏览器降级 / 加纯色回退 |
| 6 | V5 | 8 个 UI 原语 | `components/ui/*`、`package.json` | 原语可用且有 vitest 用例；`package.json` 无 `element-plus` | 否 | V1 | 日期/虚拟滚动将来要补 / 记入 §10 |
| 7 | F4 | 三页定位与改名 | `App.vue`、`InsightPanel.vue`、`ApprovalPanel.vue`、`GraphPanel.vue` | 洞察→「异常与告警」接 alerts 路由；审批→「报销自查」；图谱撤入口降为预览子视图；**三页去掉自动提交** | 否（员工读需 R1） | V1、V5 | 撤入口引发"功能消失"质疑 / 保留路由做重定向 |
| 8 | V3 | 接 router + 上下文常驻 | `router/`(新)、`views/`、`App.vue` | 每个视图有 URL；刷新保持；后退可用；**当前数据上下文显示在顶栏且可改** | 否 | F2、F4 | 深链鉴权时序 / 未登录统一跳登录 |
| 9 | V4 | 清 `theme.css` 覆盖债 | `assets/theme.css` | `.reference-login` 三轮覆盖清零；行数下降 ≥30%；无孤立选择器 | 否 | V2 | 误删在用样式 / 逐段删除 + 截图比对 |
| 10 | F5a | 总览真实化 + 管理端告警 | `views/Alerts.vue`、`DashboardPanel.vue` | 无硬编码数字；计数来自 alerts + catalog + data-files；**B-7 未落地前不画趋势线** | 否 | F4、V3 | alerts 为空时看起来"没功能" / 显式空态文案 |
| 11 | F5b | 员工端告警读取 | 同上 | 员工能看到自己的异常 | **是：R1 / B-9** | 后端 | 权限语义变更需评审 / 未落地前显示「暂无可见异常」 |
| 12 | F6 | 历史会话上后端 | `components/ChatPanel.vue`、`lib/sessions.js`(新) | 历史读 `/sessions*`；**退出登录不再清空历史**；标题用后端 `title` 不自行推导 | 部分（重命名需 `PATCH /sessions/{id}`，可选） | V3 | 本地 `localStorage` 迁移 / 一次性导入后清除 |
| 13 | V6 | 视觉回归与锁色值 | `playwright.config.js`、`tests/visual/`、`.stylelintrc` | 五档基线入库；CI 阻断裸色值与裸间距 | 否 | V2、V4 | 基线抖动 / 固定字体与动画关闭 |

**推荐执行顺序**：`F1 → F2 → F3 → V1 → V2 → V5 → F4 → V3 → V4 → F5a → F6 → V6`，F5b 与 B-1/B-2/B-3 等后端项**并行等待**，不阻塞前端交付。

### 6.3 后端需求登记（只登记，不实现）

| 顺序 | 编号 | 需求 | 阻塞的前端项 | 规模 |
|---|---|---|---|---|
| 1 | R1 / B-9 | 员工级告警读取（`GET /alerts` 等现走 `_require_alert_management()`） | F5b、总览真实化 | 迁移 + 两个路由 + 写入点；**唯一改变权限语义的项，优先评审** |
| 2 | R4 / B-3 | catalog 补 `size`、`parse_status`、`chunk_count`、`uploader` | 真实上传进度 | 增列 + `record_document_version` |
| 3 | R6 / B-5 | `GET /metrics` 只读指标目录 | 洞察去手填阈值后的口径来源 | 一个只读路由（表已在 migrations 建好） |
| 4 | R2 / B-1 | `GET /artifacts` 分页列表 | 「交成果」视图 | 查询方法 + 路由 |
| 5 | R3 / B-2 | `/ask` 的 `sources` 事件 | 对话引用条 | 一个加性事件 |
| 6 | R5 / B-8 | precheck 自动取标准 + 禁止前端传 `department` | 报销自查 | 参数 + 复用 `_approval_worker_node` 路径 |
| 7 | B-6 | 日报路由 | 无 | 需先拆分推送副作用 |
| 8 | B-7 | 趋势最小聚合接口 | 总览趋势线 | 未落地前**不画趋势线** |
| 9 | R8 / B-10 | 数据集删除 API | 误传的数据集永久留存（其首轮验收自建 3 个 `browser-e2e-*` 数据集就删不掉） | 一个 DELETE 路由 + 级联清理 |
| 10 | R9 / B-11 | `/chart`、`/export` 以 HTTP 200 返回业务失败 | F2 的 `response.ok` 抓不到假成功 | 改状态码与 `ErrorEnvelope`，**属契约变更** |

### 6.4 SSE 双轨（唯一必须跨端签字的点）

`POST /ask` **同时**发两套事件：canonical（`request.started` / `request.cancelled` / `request.failed`，envelope 含 `request_id`、`trace_id`、`task_id`、`sequence`、`timestamp`、`status`、`data`）与 legacy（`queued`、`status`、`step`、`hitl`、`error`、`done`、`cancelled`、`heartbeat`）。前端目前只处理 legacy 且直接读 `payload.content` → **后端任何一次"下线 legacy"都会让对话页瞬间空白且不报错**。

要求（已作为独立一节追加到 `api/contract-v1.md`，未改动其他 Agent 正在编辑的段落）：

1. 冻结期后端不下线 legacy 事件名，或显式声明 `protocol_version` 并同时发两个字段。
2. 前端解析器改为「canonical envelope 为主、legacy 兜底、未知事件丢弃不崩溃」——归入 F2。
3. 禁止单边改动事件名。

### 6.5 并入项（2026-09-15，来自后端首轮浏览器端到端验收）

后端线在 `docs/current-functionality-2026-09-10-revision-log.md` §13（r8）登记了首轮**经 nginx** 的 Playwright 验收：45 项 → 通过 24 / 失败 12 / 未覆盖 4 / 部分 1 / 事实 2。判给前端的项并入本计划，**保留其 P 号以便对账**：

| 来源 | 缺陷 | 归属 | 处置 |
|---|---|---|---|
| P1-5 | `content_url` 是 header-only 相对 URL，`<img src>` 带不了 Bearer → 图表界面上不可能显示 | **F1** | 前端带 Bearer 取 blob。**不需要后端改鉴权**，论据见 `handoff/2026-09-15-backend-followup-requests.md` §5 |
| P1-1 | `DashboardPanel.vue` 硬编码 `demoRows` 被 `POST /api/v1/dashboard` **回显**成趋势线与 3 条异常 | **F5a** | 先剪断「前端造数据 → POST → 回显」这条回路，再谈真实计数 |
| P1-4 | 界面把 `storage_read_only` 原样渲染给用户 | **V4** | 走 `UiToast` + 语义色，文案改成人话 |
| P2-2 | `DocPanel.vue` 源码乱码（实测 `澶辫触` 1 处、连续 `?` 4 处） | **F4** | UTF-8 精确读取后重写文案；与确认弹窗乱码同源 |
| P2-4 | 顶栏搜索/通知是无处理函数的死控件；退出按钮无可及名称 | **V3** | 要么接上要么删除，**不留死控件**；补 `aria-label` |
| 新发现 | 全局 axios 拦截器装了两份（`DocPanel.vue:7`、`lib/api.js`） | **F3** | 收敛为 1 处，零后端 |

一条口径修正：**图谱持久化代码已具备，但本次部署未配置 `KNOWLEDGE_GRAPH_STORE_PATH`，写入返回 503**。§1.4 与 §2 中「持久化已补齐」的表述限定为**代码层**，不构成生产承诺。

---

## 7. 资产与构建卫生

| 项 | 现状 | 动作 | 归属 |
|---|---|---|---|
| `dist/assets/` | 累积约 100 个旧 hash 文件（含 2.1MB 零引用的 `login-reference-yTDS-6fk.png`） | `vite.config.js` 开 `emptyOutDir: true` | V1 |
| `login-reference.png` | 2,155,854 B，源码零引用但进包 | 删除 | V2 |
| `login-background.png` | 1,506,634 B，被 earth 元素取代 | 退役（保留一份于 `docs/reference/art/` 作美术源） | V2 |
| 图像预算 | 登录页位图 1.5MB | 全部 WebP，单图 ≤220KB，登录页位图合计 ≤250KB | V2 |
| 字体 | 远程 Google Fonts `@import` | 自托管 variable woff2，约 95KB | V1 |
| `theme.css` | 源码 60KB / 构建后约 81KB | 三轮覆盖清零后目标 ≤40KB | V4 |
| 依赖 | `element-plus` 空挂 | 从 `package.json` 移除 | V5 |
| Markdown 渲染 | `ChatPanel.vue` 手写 `renderMd` | 换 `markdown-it` + `dompurify`，删除手写实现 | F2 |

---

## 8. 测试策略

### 8.1 Playwright 视觉回归

五档固定视口：`1440×900`、`1920×1080`、`3440×1440`、`1280×720`、`768×1024`。

- **不起真实服务器**：用 `context.route("**/*", …)` 从磁盘 fulfill，MIME 覆盖 html/js/css/png/svg/webp/woff2。
- **必须 abort 掉 `fonts.googleapis.com` / `fonts.gstatic.com` / CDN**，模拟客户内网；否则"字体缺失"这类缺陷会被测不出来。
- `/api/*` fulfill 401 JSON，用于验证 F3 的鉴权分支。
- `deviceScaleFactor: 1` 保证基线可比；关闭动效后截图。
- 每档断言：无横向溢出、登录卡完整可见、标题不被裁切、`document.fonts.check()` 命中本地 Manrope。
- 参考实现已在 `docs/reference/capture.cjs`（CommonJS + `NODE_PATH`，ESM 不认 `NODE_PATH`）。

### 8.2 stylelint

- `color-no-hex`：组件里禁止裸 hex，只允许 `:root` 出现。
- `declaration-strict-value`：`font-size` / `margin` / `padding` / `gap` / `border-radius` / `box-shadow` / `transition-duration` 必须走 token。
- 禁止空 `@media` 块。

### 8.3 vitest

优先级从高到低：SSE 解析器（canonical 为主 / legacy 兜底 / 未知事件不崩）、`lib/http.js` 的 401 与过期分支、Markdown 渲染的 XSS 用例（含 `[x](javascript:alert(1))`）、`UiTable` 排序与空态、`UiSelect` 键盘导航。

### 8.4 手工验收

每个 F/V 步骤给一条点击路径。验收一律用手工点击或本地 mock：**不跑迁移、不连生产库、不用真实文档做删除实验**。

---

## 9. 风险登记表与冲突面

| # | 风险 | 影响 | 应对 |
|---|---|---|---|
| R-1 | 后端下线 legacy SSE 事件名 | 对话页瞬间空白且**不报错** | §6.4 冻结 + 解析器 canonical 优先；V6 加内网字体同理的事件契约用例 |
| R-2 | 撤下图谱入口被理解为"砍功能" | 干系人阻力 | 明确它是占位页、无人工录入的可能；保留路由做重定向到「问一句」 |
| R-3 | 员工侧 alerts 403 未解（R1 未落地） | 「异常与告警」对员工是空页 | 显式「暂无可见异常」+ 说明文案，**不放假数据** |
| R-4 | 自研原语低估工作量 | V5 延期 | 已记 3–5 人日；退路见 §3.3，需你拍板才启用 |
| R-5 | `mix-blend-mode: screen` 在旧浏览器不支持 | 登录页背景异常 | 纯色 `--surface-0` 回退 + `@supports` 渐进增强 |
| R-6 | 与后端 Agent 同时改 `App.vue` 邻接逻辑 | 合并冲突 | 前端只碰 `frontend/src/**`；`App.vue` 改动串行；冲突即停并报告 |
| R-7 | 文档中的行号过期 | 误导实施 | 后端引用一律符号名/路由/事件名；前端行号视为上午快照 |
| R-8 | 两条线对 P1-5 开不同药方（后端主张签名 URL / cookie，前端主张带 Bearer 取 blob） | 后端可能顺手放宽鉴权面，扩大爆炸半径 | 已回论据（`handoff/2026-09-15-backend-followup-requests.md` §5）；**动鉴权前须等前端确认** |

**正被其他对话改动的后端文件**（引用时只用符号名 / 路由 / 事件名）：`app/api/v1/chat.py`、`app/api/v1/alerts.py`、`app/api/v1/artifacts.py`、`app/documents/catalog.py`、`app/common/auth.py`、`app/common/audit.py`、`app/main.py`、`app/storage/persistence.py`、`app/knowledge_graph/service.py`。

**待确认（已给默认假设）**

1. Element Plus 走"自研 8 原语"还是"按需保留 Table + DatePicker" → 默认自研。
2. 「办待办」是否在本版预留入口 → 默认不预留（C-1 未建模）。
3. 登录页是否保留三张装饰数据卡 → 默认保留（已定"看看就行"）。
4. 管理视图对谁的可见性 → 默认等 C-3 前全员隐藏。

---

## 10. 不做清单

- 不全量迁移 TypeScript。
- 不引入 Tailwind / CSS-in-JS / SCSS / Pinia。
- 不做审批工单模型（C-1），**不在现有 `precheck` 上贴皮**假装有待办系统。
- 不做知识图谱独立工作区与自动抽取（C-2）。
- 不做 insights 与 alerts 的逻辑合并（consolidated-fix-plan 已定"合并前不要单边改动"）。
- 不做任何 legacy SSE 事件清理。
- 不改鉴权中间件（不用 cookie 或签名 query token 免 `Authorization`；前端带 token 取 blob 已够）。
- 不把 Chroma 写成最终架构（过渡方案，目标存储为 PostgreSQL + PGVector）。
- 不做虚拟滚动表格、日期选择器（除非 §3.3 退路被启用）。
- 不追求登录页指标真实性（已定：装饰）。
- 本轮不修改 `frontend/` 与 `app/` 任何文件。

---

## 11. 验收清单

**视觉与资产**

- [ ] 登录页在 `3440×1440` 与 `1280×720` 两档无裁切、无拉伸、卡片完整可见
- [ ] 页面文案 100% 来自 DOM，位图不含任何文字
- [ ] 页面零远程字体/CDN 请求（内网模拟下截图与 `document.fonts.check()` 双证）
- [ ] 登录页位图合计 ≤250KB；`login-reference.png` 已删除；`emptyOutDir` 生效
- [ ] `theme.css` 行数下降 ≥30%，`.reference-login` 三轮覆盖清零
- [ ] `stylelint` 零违例（无裸 hex、无裸间距、无空 `@media`）
- [ ] 主按钮无渐变、全站无 `text-shadow` 发光字、强调色只有一个

**工作区与信息架构**

- [ ] 侧栏入口数量与 §2 一致；图谱不再是独立工作区
- [ ] 洞察显示为「异常与告警」且数据来自 alerts 路由，无手填五格表单
- [ ] 审批显示为「报销自查」，界面写明"需手填标准"或"标准来自制度"
- [ ] 三个页面不再自动提交
- [ ] 总览无硬编码数字；B-7 未落地时**没有趋势线**
- [ ] 每个视图有 URL，刷新保持、后退可用
- [ ] 「数据」页选中的表在「问一句」里可见且可改

**工程与安全**

- [ ] `element-plus` 从 `package.json` 消失，产物体积不增
- [ ] 对话页切换工作区后状态不丢；`approve()` 复位正确
- [ ] 401 统一处理，`expires_in` 到期前提示
- [ ] 退出登录不再清空历史；历史来自 `/sessions*`
- [ ] `[x](javascript:alert(1))` 在渲染后不可执行（vitest 用例）
- [ ] 文档明确声明"未改动 `app/**`"，所有需后端项均带 R/B/C 编号

**跨端**

- [ ] SSE 事件废弃策略在 `api/contract-v1.md` 中由双方签字
- [ ] R1（员工级告警读取）进入后端评审队列

**2026-09-15 并入项**

- [ ] `DashboardPanel.vue` 不再向 `POST /api/v1/dashboard` 提交任何前端构造的行
- [ ] 图表经 `Authorization` 头取 blob 渲染，且**后端未因此改动鉴权中间件**
- [ ] `ChatPanel.vue` 的图表正则同时接受 `/static/` 与 `/api/v1/artifacts/` 两种前缀
- [ ] `DocPanel.vue` 无 GBK 乱码残留（`澶辫触`、连续 `?` 均为 0）
- [ ] 顶栏无死控件；退出按钮有可及名称
- [ ] `storage_read_only` 不再原样出现在界面上
- [ ] 全局 axios 拦截器只剩 1 处

---

## 12. 附：被本计划取代或限定的旧计划

四份旧文档已在开头加标注，后续 Agent **不得按它们开工**：

| 旧计划 | 处置 |
|---|---|
| `docs/superpowers/plans/2026-09-09-enterprise-brain-frontend-visual-upgrade.md` | **整体作废**，由本计划 §5/§6 与 `frontend-visual-quality-2026-09-14.md` 取代 |
| `docs/superpowers/plans/2026-09-10-enterprise-brain-reference-ui-alignment.md` | 视觉部分作废；「业务数字均来自现有 API 或空态」一条**仍有效**，由 F5a 承接 |
| `docs/superpowers/plans/2026-09-07-enterprise-intelligence-upgrade.md` | 设计目标仍有效（审计的「证据 D」）；完成度不得按其自述判断；阶段 8 前端部分被本计划取代 |
| `docs/superpowers/plans/2026-09-10-enterprise-brain-multi-agent-development-plan.md` | 完成度未核实，不得作为现状依据；仅作为设计意图存档 |

原则：判断完成度只用当前源码、测试与 `docs/current-functionality-2026-09-10.md`，不用历史计划里的“已完成”列表。
