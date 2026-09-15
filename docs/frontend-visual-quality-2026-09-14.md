# 前端「高级感」落地规范

> 日期 2026-09-14 ｜ 产出方 后端/架构线 Agent ｜ 执行方 前端 Agent
> 适用范围 `frontend/src/**`。本文档只定规格与优先级，不代表功能已实现。
> 数据来源：对当前工作区代码的实测统计（`frontend/src/assets/theme.css` 共 3394 行 + `frontend/src/**/*.vue`），
> 以及会话 01a07eaa（2026-09-08 ~ 09-11）中用户关于前端页面的原话。

## 0. 一句话结论

当前界面**不缺深色、不缺发光**，缺的是**约束**。
一个 3394 行的手写 CSS 里同时存在 134 个不同色值、25 种圆角、28 种字号、5 个空的 `@media` 块和两套并行的命名体系；
而本该撑起整个气质的字体，在客户内网环境里**根本加载不出来**。
高级感 = 一致性 + 克制 + 排版层级 + 留白节奏 + 少数几个精修动效，而不是更多的特效。

## 1. 实测基线（问题的量化证据）

| 指标 | 实测值 | 目标值 | 证据 |
| --- | --- | --- | --- |
| 主题文件规模 | 单文件 61,039 B / 3,394 行 | 拆成 4-6 个文件 | `frontend/src/assets/theme.css` |
| 设计 token 定义数 | 31 | 60-90（含语义层） | 同上 `:root` |
| token 实际被引用数 | 19（`var()` 共 92 次） | 全部 | 同上 |
| 定义后从未使用的 token | 9 个：`--ink` `--radius-sm/md/lg/xl` `--cyan-dark` `--bg-panel-2` `--login-blue` `--login-muted` | 0 | 扫描结果 |
| theme.css 内色值 | 161 处 / **134 个不同值** | ≤ 24 个语义值 | 同上 |
| 不同 `border-radius` 取值 | 25 种 | 3 档 | 全站扫描 |
| 不同 `font-size` 取值 | 28 种 | 5 档 | 全站扫描 |
| `font-size` 声明总数 / 其中 ≤10px | 186 / **40（21.5%）** | ≤10px 归零 | 全站扫描 |
| 空 `@media` 块 | 5 个（`1120px`/`900px`/`720px` 等） | 0 | theme.css 尾部 |
| `@media` 断点体系 | 980/680、1120/760、900/720 三套并存 | 一套 | theme.css |
| `px` 字面量 | 877 处 | ≤ 200 | theme.css |
| 登录位图 | 1,471KB + 847KB + 2,105KB（其中 `login-reference.png` 零引用） | 合计 ≤ 350KB | `frontend/src/assets/` |
| 依赖 `element-plus` `markdown-it` | 已安装，**全项目 0 处 import** | 删掉或真用 | `frontend/package.json` |
| 图标实现 | 35 个内联 SVG path 字符串写进 JS + 7 处 `✅ ✕ ⚠` 文本符号 | 一套线性图标 | `frontend/src/App.vue` `frontend/src/components/ChatPanel.vue` |
| 低对比文本 | `--ink-faint #627390` 在四层表面上 **3.35 / 3.71 / 3.90 / 4.17:1**，全部低于 AA | ≥ 4.5:1 | 计算值 |

### 1.1 同一元素上叠了两套设计体系（最关键的结构性问题）

登录页根节点是 `class="auth-shell reference-login"`（`frontend/src/App.vue:141`）。theme.css 里同时存在：

- 早期体系 `.auth-shell` / `.auth-hero` / `.auth-grid` / `.brand-symbol`（`display:grid` 两列 + CSS 画的圆环与网格底）；
- 后期体系 `.reference-login`，并直接 `display: none` 关掉前面的 `.auth-atmosphere` `.auth-brandbar` `.auth-hero`（theme.css:1933-1937）。

`.reference-login` 系列规则出现 **118 次，跨 1264 → 2339 行**，中间被 `@media` 覆盖三轮（1805、1823、1908、2239）。
结果是：**页面上真正生效的样式埋在三层层叠之上，没人能说清哪条规则在起作用**。
所以「改了好几轮还是不对味」不是审美问题，是可维护性问题——继续往上追加第四轮只会更糟。

## 2. 三条硬红线（来自会话 01a07eaa 用户原话，不得违反）

| 红线 | 用户原话 | 对当前代码的含义 |
| --- | --- | --- |
| 不堆技术元数据 | 「语义口径模块后面什么来自什么接口更是不能看见」「你只要展现功能就行，不要把一些没用的东西加进去」 | 界面禁止出现接口路径、字段口径来源，以及 `Active Insight` / `Knowledge Graph` / `Approval` 这类英文 eyebrow 装饰小标 |
| 不用廉价渐变、不堆霓虹 | 「不是普通后台模板，不要廉价渐变，不要赛博朋克霓虹过度」「细节精致、层次丰富、边缘清晰、光效克制」 | 同一屏内发光只允许出现在 **1 个焦点态**；禁止多色渐变铺满卡片 |
| 复杂视觉必须切图 | 「右边是带景深、发光粒子、3D 点阵地图和轨道线的渲染图，左边是用简单的 2D SVG 线条硬画的，完全没有体积感和光影」 | 星野/景深/球体一律走图片资产，CSS 只管玻璃卡与交互层；**禁止再用 CSS/SVG 硬画 3D** |

补充事实：用户在 2026-09-09 抱怨的「一片白」在当前版本**已经解决**（`--bg: #040812`）。
当前问题已从「太白」变成「不一致 + 过度发光 + 信息噪声」，**不要再往加更多霓虹的方向走**。

## 3. P0-1 根因：字体在内网必然降级为浏览器默认字体

```css
/* frontend/src/assets/theme.css:1 */
@import url("https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap");
```

实测事实：

- `frontend/**` 下**没有任何字体文件**（`.woff2/.ttf/.otf` 计数为 0），`@font-face` 规则计数为 0；
- `--font-body: Manrope, "PingFang SC", "Microsoft YaHei", system-ui`；`--font-mono: "DM Mono", "Cascadia Code", Consolas`；
- 本项目部署形态是私有化、客户内网、数据不出服务器，`deploy/README.server.md` 甚至写明「现场不要假设能 pull」。

推论：**在真实客户环境里 `fonts.googleapis.com` 不可达，Manrope 与 DM Mono 永远不生效**，
整套排版退化为「微软雅黑 + Consolas」；而 `@import` 是阻塞式外部请求，内网下每次首屏还要白等一次连接超时。

用户 2026-09-10 的原话正是这个现象：「左边用了浏览器默认的无衬线字体，没有描边、没有发光、没有字距调整」。
也就是说：**过去几轮调的字距、字重、层级，在客户机器上被这一行 `@import` 静默抹掉了。**
这一条不修，后面所有排版层面的努力都不落地——所以它是 P0 的第一项。

### 修复规格

1. 删除远程 `@import`，改**自托管 `@font-face`**，文件放 `frontend/public/fonts/`（同源、离线可用）。
2. 中文交给系统字体栈，不随包分发大体积中文字体（成本高、收益低）。拉丁只取 latin 子集：Manrope 4 个字重约 100-120KB。

```css
--font-body: "Manrope", "HarmonyOS Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
--font-mono: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
```

3. 数字必须等宽：KPI 数值、表格金额、时间戳统一 `font-variant-numeric: tabular-nums` + `--font-mono`。
   这是企业软件「高级感」最便宜的一招——数字抖动是「像玩具」的第一诱因。
4. `font-display: swap`，`index.html` 里对首屏字体加 `<link rel="preload">`。
5. 禁止用 `text-shadow` 模拟发光字。标题靠字重与字距，不靠光。

## 4. P0-2 根因：登录页背景图被拉伸 + 卡片用百分比压在图上

当前实现（theme.css:1908 与 theme.css:1664）：

```css
.auth-shell.reference-login {
  background-image: url("./login-background.png");
  background-size: 100% 100%;   /* 强行拉满，不是 cover */
}
.reference-login .auth-panel {
  position: absolute; top: 25.3%; right: 3.8%;
  width: clamp(320px, 24.3vw, 470px); height: 46.1%;   /* 固定高度 */
}
```

实测：`login-background.png` 是 **1672×941，比例 1.777**。

- `background-size: 100% 100%` 意味着任何非 1.777 比例的视口都会**直接把地球和星野拉伸变形**：
  1920×1080（1.778）勉强正常，1440×900（1.6）明显压扁，3440×1440 带鱼屏明显拉长。
  **变形的高级感资产，观感比纯色更差**，这是「一看就是模板」的破绽点。
- 卡片用 `top/right` 百分比 + 固定 `height: 46.1%`：文案一多就溢出边界；
  在 1280×1024 或平板竖屏上会盖到地球主体上，让文字落在低对比区域，可读性随机崩掉。
  也就是说这套登录页**只在设计它时那一档分辨率上成立**，这正是「现场演示时翻车」的典型来源。

### 修复规格

1. `background-size: cover` + `background-position: center`，禁止 `100% 100%`。
2. 卡片改为**流内定位**：容器 `display: grid`，`grid-template-columns: minmax(0,1fr) clamp(360px,32vw,460px)`，
   右列放卡片、`align-items: center`。地球留在背景图里，卡片位置由布局决定，与视口比例解耦。
3. 卡片高度交给内容（`height: auto` + `padding`），不要 `46.1%`。
4. 出图规格：一张 **2560×1440 WebP（≤ 220KB，q≈82）** 作通用底图；
   另出 `@media (max-aspect-ratio: 4/3)` 使用的纵向构图版；靠构图解决适配，不靠拉伸。
   `login-mobile-atmosphere.png` 从 847KB 压到 ≤120KB；`login-reference.png`（2.1MB、零引用）删除。
5. 卡片下方必须有**局部低对比兜底**：给卡片背后加一层 `radial-gradient` 遮罩
   （DOM 里已有 `.login-visual-backdrop` 节点可用），而不是依赖图片刚好留了块空地。
6. 玻璃卡按用户 2026-09-10 给定规格落地（这套值直接采纳，但收敛成 token）：

```css
.auth-panel {
  background: rgba(13, 30, 54, .60);
  backdrop-filter: blur(20px) saturate(140%);
  border-radius: 16px;
  border: 1px solid rgba(0, 200, 255, .20);
  box-shadow: 0 20px 50px rgba(0, 0, 0, .50), inset 0 0 20px rgba(0, 200, 255, .05);
  padding: 40px;
}
```

7. `backdrop-filter` 全站从 7 处降到 **登录卡 + 抽屉 2 处**。
   深底 + 大模糊半径会糊字、掉帧，且必须提供 `@supports not (backdrop-filter: blur(1px))` 纯色降级。


## 5. P0-3 根因：没有设计系统，只有 3394 行手写 CSS

31 个 token 对 134 个写死色值，等于没有 token；9 个 token 定义后从未使用，说明定义与实现是两轮各写各的。
25 种圆角、28 种字号意味着**相邻两个卡片可能圆角不一样、标签字号不一样**——人眼说不出的别扭，就是这么来的。

### 5.1 令牌表（建议直接落成 `frontend/src/assets/tokens.css`，替换现在的 31 个）

```css
:root {
  /* 表面：只用这 4 档，靠色差分层，不靠边框线 */
  --surface-0: #05080f;   /* 页面底 */
  --surface-1: #0a1119;   /* 面板 */
  --surface-2: #111b26;   /* 卡片 */
  --surface-3: #18242f;   /* 悬浮/下拉 */

  /* 文本：3 档正文 + 1 档反白 */
  --text-1: #e8eef6;
  --text-2: #a9b6c6;
  --text-3: #7c8896;      /* 由 --ink-faint 提亮，见 5.2 */
  --text-invert: #05080f;

  /* 描边：2 档，弱到几乎看不见，只用于分隔不用于装饰 */
  --border-1: rgba(232, 238, 246, .07);
  --border-2: rgba(232, 238, 246, .14);

  /* 单一强调色 + 语义色（全站彩色总量受 5.3 预算约束） */
  --accent: #2f9bff; --accent-hover: #4facff; --accent-press: #1d84e0;
  --success: #35b47f; --warning: #cf9a35; --danger: #e0596b;

  /* 尺度：8pt 栅格 */
  --s-1: 4px; --s-2: 8px; --s-3: 12px; --s-4: 16px; --s-5: 24px; --s-6: 32px; --s-7: 48px; --s-8: 64px;
  --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-pill: 999px;
  --t-xs: 12px; --t-sm: 13px; --t-md: 14px; --t-lg: 16px; --t-xl: 20px; --t-2xl: 28px;
  --shadow-1: 0 1px 2px rgba(0,0,0,.4);
  --shadow-2: 0 8px 24px rgba(0,0,0,.45);
  --shadow-3: 0 20px 50px rgba(0,0,0,.5);
  --motion-fast: 120ms cubic-bezier(.2,.8,.28,1);
  --motion-slow: 200ms cubic-bezier(.2,.8,.28,1);
}
```

### 5.2 对比度（当前不达标的地方必须改）

| 前景 | 背景 | 实测 | 要求 | 结论 |
| --- | --- | --- | --- | --- |
| `--ink-faint #627390` | `--bg #040812` | 4.17:1 | 4.5:1 | 不达标 |
| `--ink-faint` | `--bg-raised #081224` | 3.90:1 | 4.5:1 | 不达标 |
| `--ink-faint` | `--bg-panel #0b1730` | 3.71:1 | 4.5:1 | 不达标 |
| `--ink-faint` | `--bg-panel-2 #102041` | 3.35:1 | 4.5:1 | 不达标 |

而 `#627390` 目前大量用在 9-11px 的小字上（≤10px 的字号声明有 40 处）。
**「小字 + 低对比」是老板在会议室投屏上第一个抱怨的点**：投影仪一打就看不见。
要求： tertiary 文字最低 `#7c8896`，且禁止用于正文；全站最小字号 12px，正文 14px。

### 5.3 彩色预算（把「克制」变成可验收的数字）

- 一个工作区内，非中性色（含强调色与语义色）出现的**独立色相 ≤ 3**；
- 发光（`box-shadow` 带彩色、`drop-shadow`、`text-shadow`）**同屏最多 1 处**，且只给当前焦点：主按钮 hover、选中导航项，二选一；
- 渐变只允许出现在**背景层与登录卡**，卡片正文区一律纯色 `--surface-2`；
- 语义色只表达状态（成功/待处理/风险），**禁止**拿青色紫色当装饰描边。

## 6. P1：排版层级——高级感 70% 来自这里

1. 字阶 6 档封顶（见 `--t-*`），删除现有 28 种字号中的 22 种。
   中文正文 **14px / 行高 1.65**；表格 **13px / 行高 1.5**；标签 12px；面板标题 16px；页标题 20px；KPI 数值 28px。
2. 标题字距 `letter-spacing: -.01em`，中文小字号（≤13px）字距归零并**加** 0.01em；
   禁止再用 `letter-spacing: .18em` 的英文 eyebrow 大字距装饰（theme.css 里 `.eyebrow` 的现状），那是「AI 模板味」最强的元素之一。
3. 层级靠**尺寸 + 字重 + 颜色**三件事同时表达，而不是靠边框和发光。
   一个数值卡片里：标签 `--text-3`/12px/500，数值 `--text-1`/28px/700/mono，辅助 `--text-2`/12px/400，够了。
4. 中文行长 30-38 字（约 60-75 拉丁字符）；对话面板正文容器 `max-width: 68ch`。
5. 留白节奏：卡片内边距 `--s-5`(24px)，卡片间距 `--s-4`(16px)，面板区隔 `--s-6`(32px)；
   **一个屏幕的内容块 ≤ 4 个**。现在 `panel-grid` 里 6-9 个卡片同权重堆叠，视线没有落点。
6. 删掉所有非信息的英文字段：`.eyebrow`、`.panel-kicker` 的 `Active Insight`/`Knowledge Graph`/`Approval`，
   以及任何「来自 /api/…」「口径来源」类元数据（红线一）。

## 7. P1：背景分层——用图层代替 CSS 画 3D

采纳用户 2026-09-10 的结论：**渲染交给图，交互交给 CSS**。三层结构：

| 层 | 内容 | 实现 |
| --- | --- | --- |
| L0 背景层 | 星野、景深、地球、光晕 | 一张预渲染 WebP（登录页用），或极淡的 `radial-gradient` 团（工作台用） |
| L1 结构层 | 网格线、面板底 | 纯色 `--surface-*` + 1px `--border-1`，`opacity ≤ .5` |
| L2 内容层 | 卡片、表格、文字 | 不透明 `--surface-2`，阴影分层不做模糊 |

- 登录后工作台**不要再用图片背景**（会干扰读数据），只用两层极淡的 `radial-gradient` 光团 + 纯色面板；
  现在 `body` 上有 3 层渐变叠加，`auth-shell::before` 还有一层网格，实际效果是「到处都在发亮、没有重点」。
- 需要更高级的登录视觉时，**去生成一张图**（本项目已有图像能力），而不是继续加 CSS。
- `App.vue:147-200` 里那个手绘 SVG 地球（含 `globe-halo`、`globe-dots`、`globe-glow` 滤镜）属于用户点名的「2D 硬画」路线，
  且当前主题里它已经被 `display: none` 关掉（`.reference-login .auth-atmosphere`），**是死代码**：直接删除，减负。

## 8. P2：质感细节——拉开与模板差距的地方

1. **图标统一**：35 个写死在 JS 数组里的 SVG path 字符串 + 7 处 `✅ ✕ ⚠` 文本符号，
   换成一套 24×24、1.5px 线宽、`currentColor` 的线性图标（内联 `<svg>` 组件或 `@element-plus/icons-vue`）。
   混用「图标字体风格 + emoji + 手绘 path」是廉价感最直接的信号（`ChatPanel.vue:537-538` 的 `✅ 确认执行`、`✕ 取消` 优先处理）。
2. **焦点与可达性**：全站自定义控件（卡片按钮、导航项、标签页）必须有 `:focus-visible` 环，
   统一 `outline: 2px solid var(--accent)` + `outline-offset: 2px`；侧栏 7 个工作区补 `role="tablist"`/`aria-selected`。
3. **动效只做 3 类**，时长 120-200ms：hover 时 `translateY(-1px)` 或 `opacity`；面板切换 `opacity + 6px` 位移；
   数字 count-up（KPI 首次出现 600ms）。其余一律不加。补 `prefers-reduced-motion` 全量降级。
   注意：theme.css 目前 transition 时长**只有 2s 一档**（用于登录装饰动画），工作台区间没有微交互时长体系——快慢混着，就会显得不利落。
4. **真实数据组件**：表格用真 `<table>` + sticky 表头 + 斑马纹 `--border-1` + 等宽数字；
   长列表加虚拟滚动。现在多处用 div 拼表格，宽度一变就错位。
5. **空态/加载态**：骨架屏（`--surface-3` 微光扫过）而不是转圈；
   空态给一句人话 + 一个主操作按钮，例如审批工作区空态应是「今天没有需要你确认的高风险动作」+「查看已归档」。
6. **细节**：细滚动条（`scrollbar-width: thin`）、`::selection` 配色、按钮 `active` 有 1px 下压、
   数字用 `--font-mono`，输入框高度统一 40px（现 32/38/40/50 混用）。

## 9. 资产与性能（「高级感」的隐形杀手）

| 项 | 现状 | 处理 |
| --- | --- | --- |
| `login-reference.png` | 2,105KB，代码中零引用（设计参考稿） | 从 `frontend/src/assets/` 删除，需要留档就移到 `docs/` |
| `login-background.png` | 1,471KB PNG | 重导出 ≤220KB WebP |
| `login-mobile-atmosphere.png` | 847KB | 压到 ≤120KB |
| 远程字体 `@import` | 内网必然失败 + 阻塞渲染 | 自托管（§3） |
| `element-plus`、`markdown-it` | 在 `dependencies` 里，全项目 0 import | 要么删依赖，要么真用它做表格/弹层；否则 `ChatPanel.vue:402-424` 的手写 `renderMd` 与它并存是长期风险 |
| 无路由 | 手工 tab 切换（`App.vue:365-372`） | 加 `vue-router`，让每个工作区有可分享 URL（老板会「把链接发到群里」） |

## 10. 落地顺序（给前端 Agent 的执行清单）

| 步 | 内容 | 影响后端 | 验收 |
| --- | --- | --- | --- |
| V1 | 字体自托管 + 删 `@import` | 否 | 断网刷新，字形不变 |
| V2 | 建 `tokens.css`，全站替换写死色值/圆角/字号 | 否 | `grep -c "#[0-9a-f]" theme.css` 从 161 → ≤30；圆角种类 25 → ≤4 |
| V3 | 登录页改 `cover` + grid 流内卡片 + 压图 | 否 | 1440×900 / 1920×1080 / 3440×1440 / 768×1024 四档截图不出现拉伸与遮挡 |
| V4 | 删死代码（手绘地球 SVG、被 `display:none` 的旧体系、空 `@media`、未用 token） | 否 | theme.css 行数 3394 → ≤1800 |
| V5 | 排版层级 + 信息噪声清理（英文 eyebrow、「来自接口」类文案） | 否 | 7 个工作区逐屏截图，无元数据文案 |
| V6 | 图标统一 + 焦点环 + 动效三件套 | 否 | 键盘 Tab 走查一遍有可见焦点；hover 不超 200ms |
| V7 | 空态/骨架屏/真表格 | 是（需要空态数据，接口已具备） | 断言/审批/图谱空态各一张截图 |

V1-V6 **全部是前端资产与样式层，不需要改后端**；V7 只需要现有接口返回空数组，也不需要新增接口。
（图表不显示那条是独立缺陷，见 `docs/frontend-workspace-audit-2026-09-14.md` 的 P0 清单，同样纯前端可修。）

## 11. 明确不要做的事（避免又一轮返工）

- 不要换配色方案、不要再「跳一种风格」。深色 + 蓝青的方向已经定了，问题在执行的一致性，不是选错颜色。
- 不要引入 CSS-in-JS / Tailwind / 新 UI 库来「重做一遍」。当前是收敛问题，换技术栈只会再来一轮 3000 行。
- 不要用 CSS 画地球、星空、粒子（用户已明确否掉，见 §2 红线三）。
- 不要把界面做成设计稿截图：每步必须用真实浏览器截图验收（用户 2026-09-10 已为此发过火）。
- 不要在 `theme.css` 尾部追加第四轮覆盖层。要做就按 V2/V4 先删后立。


