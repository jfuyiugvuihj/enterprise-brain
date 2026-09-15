# 前端并行开工看板（2026-09-15）

**规则**：每条对话 / 每个子 Agent 开工前只读 §1 找自己那一行 + §4 看闸门颜色。**闸门不绿就不许做任何写操作**，只许只读准备。
**翻绿的唯一凭据是 commit**：翻闸人自己提交、自己把 commit 号写进 §4，并在自己 worktree 里 `git merge --ff-only codex/data-file-catalog` 让全树看到。**不靠记忆、不靠默契、不靠"我觉得做完了"。**

---

## 1. 门禁表（各角色看自己一行）

| 角色 | 目录 / 分支 | 开工前置 | 第一件事 | 完成后要翻的闸 |
|---|---|---|---|---|
| **C 后端** | `企业智脑`（主树）/ `codex/data-file-catalog` | 无 | 实现 e2 检索（六条要求见 handoff 跟进单 §6.2），再做 R1 员工告警 | **G3**、**G4** |
| **A 主干** | `fe-trunk` / `codex/fe-trunk` | G0 | Step 1 = 依赖 + script 入口，单独提交 | **G1**，随后每步翻 **G-A-n** |
| **B 叶子** | `fe-prims` / `codex/fe-prims` | **G1** | G1 前只做只读准备；G1 后写 `lib/errcodes.js` + 6 个纯 CSS 原语 | **G2** |
| **D 验收** | `fe-trunk` | **G-A-3 且 G2** | 逐条复测工单 §6 证据 | 验收报告（不改代码） |
| 子 Agent（E 模板） | 由父对话派出 | 父对话已绿自己那一行 | 只写派单里列的文件 | 不翻闸，回报给父对话 |

---

## 2. 闸门定义（可机器验证，别靠感觉）

| 闸 | 绿的条件 | 自证命令（在对应目录跑） |
|---|---|---|
| **G0** | 七面板应用已在版本控制里 | `git log --oneline -1 -- frontend/src/assets/theme.css` 有结果 |
| **G1** | `fe-trunk` 出现含 `chore(deps)` 的提交，且 `package.json` 有 `lint` / `test` / `test:e2e` 三个入口、无 `element-plus` | `npm pkg get scripts dependencies --prefix frontend` |
| **G2** | `components/ui/` ≥ 6 个组件 + `lib/errcodes.js` 存在 + `npx vitest run` 全绿 | `npx vitest run` |
| **G3** | `app/rag/filters.py` 出现 administrator 判据，且**真机** admin 能问出知识库答案 | `git grep -c "administrator" -- app/rag/filters.py` ≥ 1 |
| **G4** | `GET /alerts` 对 staff 返回 200 而非 403 | 用 staff 探针账号打一次，记状态码 |
| **G-A-n** | A 线第 n 步（F1/F2/F3/V1…）的 commit，且工单 §6 对应证据已改 | `git log --oneline -1` + 工单 diff |

**G3 一翻绿，立刻做两件事**：① 撤掉工单 §0.2 与计划 §8.1 的「必须带部门账号」前置；② 让 D 补一条 admin 开箱用例。G4 一翻绿，F5b 从"阻塞"变"可做"。

---

## 3. 放行顺序（就按这个来，别抢跑）

```
现在 ──┬── C：e2 → R1（最长的一条腿，先派）
       └── A：Step 1 deps ──→ G1 绿
                    │
                    ├────→ B 开工（G1 前它只能只读）
                    └────→ A 继续 F1 → F2 → F3 → V1 → V2 …（不等 B）
                                  │
C 的 G3 / G4 ────────────────────┘（改的是后端行为，A 每步开工前 merge 主树即可拿到）

B 交完 G2 ──┐
A 交完 G-A-3 ┴──→ D 开工（复测）
A 走到 V5(接线) 之前必须等到 G2，否则停下等，不要自己造原语
```

唯一会返工的接缝 = **A 到 V5 时 G2 还没绿**。所以 B 的排期要压在 A 的 F1→F2→F3→V1→V2 这段时间内完成。

---

## 4. 状态板（谁翻谁写，一行一证据）

| 闸门 | 状态 | commit / 命令输出 | 时间（实取） | 翻闸人 |
|---|---|---|---|---|
| G0 | 🟢 | `13e808d` | 2026-09-15 | 计划线 |
| G1 | 🟢 | `e000bef`（`fe-trunk`：deps + `lint`/`test`/`test:e2e` 入口，`element-plus` 已摘；`npm run build` 286ms 通过；`fe-prims` 已 ff 到同 commit） | 2026-09-15T12:32:53 | 总控 |
| G2 | 🟢 | `978ce6a`（`lib/errcodes.js`：16 蓝本码 + 7 个 `data.py` 码 + 10 条历史别名 + HTML/`[object Object]` 防线）、`3c46e66`（**9 个**原语，超 ≥6 要求）、`d451a2c`+`0a2a214`+`c028837`。总控亲验：`npx vitest run` → **93 passed / 0 failed**（475ms）；`npx playwright test` → **30 passed / 15 skipped**（27.6s，跑在 `dist` 上，**不需要后端**）；`git ls-files frontend/src/components/ui` → 9 个 `.vue` | 2026-09-15T16:13:43 | 总控 |
| G3 | 🟡 **代码绿，真机待验** | `719f29c`：`app/rag/filters.py` 复用 `policy.is_administrator`；全量 `713 passed / 22 skipped / 0 failed`。**缺口**：运行中的容器是旧镜像，"开箱 admin 问得出答案"必须重建后端镜像才能证（约 28 分钟，待用户点头） | 2026-09-15T12:52:02 | 总控 |
| G4 | ⚪ | | | |
| G-A-1 (F1) | 🟡 **代码绿，真机未验** | `d9b1dcc`：新增 `lib/artifacts.js`（走统一实例取 blob + `baseURL:''` 防 `/static/` 被改写 + 4xx JSON 错误体解码 + `revoke()` 幂等），`ChartViewer.vue` 四态含失败占位卡与「重新取图」。总控亲验：全仓 `import axios` 只剩 `lib/http.js:1`。**缺**：要一张真图 100% 可见 + Network 带 `Authorization` → 无探针账号 | 2026-09-15T16:13:43 | 总控 |
| G-A-2 (F2) | 🟡 **代码绿，真机未验** | `2bee141` + 补漏 `c5a61b1`：`lib/sessions.js` 模块级 store + canonical(`request.*`/`request_id`+`sequence` 信封) 优先、legacy 兜底、未知丢弃，`default:` 由 0 → 3；取消读 `body.cancelled`：`true`/`false`/缺字段三条文案各不相同 | 2026-09-15T16:13:43 | 总控 |
| G-A-3 (F3) | 🟡 **代码绿，真机未验** | `a07294f` + 补漏 `bd38c00`：单实例 + 请求/响应拦截 + 3s 去重 + `expiring`/真过期共用收尾；`DocPanel`、`DataPanel` **两份**重复全局拦截器都删；`rg '\?{4}' src` 0 命中、`rg 'window.alert' src` 0 命中 | 2026-09-15T16:13:43 | 总控 |
| **G-INT** | 🟢 **两线合并可用** | `c12b698`（`fe-prims` merge `codex/fe-trunk`，**零冲突**，写入集确实不相交）→ `07ff441`。合并树三门全绿：`npm run build` 276ms、`npx vitest run` 93 passed、`npm run lint` exit 0 | 2026-09-15T16:13:43 | 总控 |

---

## 4A. 总控亲验：本轮新发现（不采信子 Agent 自述，全部自己复跑）

### 4A.1 锁色闸门原先是**空的**（已修，`07ff441`）

B 线交上来的 `.stylelintrc.json` 把 `**/*.vue` 放进了 `ignoreFiles`——理由成立（stylelint 17 缺 `postcss-html` 解析不了 SFC），后果是**它自建的 V6 锁色闸对面板一行都不生效**：351 处硬编码色全在 `.vue` 的 `<style>` 里，闸门只盖住 B 自己那 9 个 `ui/*.css`（本来就干净）。

装上 `postcss-html` 并加 `**/*.vue` override 后实测：**351 处违规 / 8 个文件**——
`ChatPanel.vue` 143、`DocPanel.vue` 76、`DataPanel.vue` 74、`DocumentPreviewModal.vue` 28、`ChartViewer.vue` 25、`InsightPanel.vue` 3、`App.vue` 1、`ApprovalPanel.vue` 1。`GraphPanel.vue` 与 `DashboardPanel.vue` 干净。
抽 3 条行号回读源码逐条对上（`ChatPanel.vue:557 #303133`、`:565 #909399`、`:570 #409eff`），证明解析器真在读 `<style>`，不是刷数字。

处置=**单向棘轮**，不是"全修完再开闸"：
- `npm run lint` 里这两条色规在 `.vue` 内降为 `severity: warning` → CI 不因存量债假红，但每次跑都打印 351。
- 新增 `npm run lint:colors` = `stylelint ... --max-warnings=351` → **只准降不准升**。已实证：临时塞一个 `color: #123456` 就 `Max warnings exceeded: 352 found. 351 allowed`、exit 2（探针文件已删并 `Test-Path` 复验 False）。
- V1/V2 每清一个文件就把这个数字改小，改小是进度、改大是失败。
- 顺手订正：配置里引用的 `src/assets/tokens.css` **不存在**，token 文件实名 `src/assets/theme.css`（A 已建，含 91 处 `var(--*)`）。已统一按 `theme.css`，它仍在 `ignoreFiles` 内（token 定义文件本来就该允许 hex）。

### 4A.2 401 契约真相：中间件吞掉了稳定码（跨线缺口，待补）

`app/main.py` 的鉴权中间件是**全路径兜底**：除 `/api/v1/login`、`/health`、`/sso/login`、`/open*`、`/`、`/docs`、`/openapi.json` 白名单外一律先过它，缺 token / token 过期 / 用户不存在 → **`{"detail": "请先登录"}`**（中文散文），账号停用 → **403 `{"detail": "账号不可用"}`**。

因此 `app/api/v1/artifacts.py`、`chat.py`、`alerts.py` 里那几处 `detail="authentication_required"` 在"没登录/token 失效"这条主路上**永远不可达**（A 线实测活栈拿到的就是 `请先登录`，报告属实）。影响：

1. **B 线待补**：`lib/errcodes.js` 只认稳定码，`请先登录` 走 `resolveCode` 会掉进未知码分支 → `{code:'请先登录', message: FALLBACK}`，把"封闭枚举"这条不变量在实战里破掉。需加一张**散文别名表**（`请先登录`→`authentication_required`，`账号不可用`→ 新码 `account_unavailable`）。
2. **后端跟进单待记**：中间件应改吐稳定码（`authentication_required`/`account_unavailable`）而非散文，这是契约层修正，动它要过一次全量回归，排到 C 线下一轮。
3. 前端 UX 暂不受阻：401 由 `lib/http.js` 拦截器直接收口（清会话 + 回登录），不经过字典。

### 4A.3 A 线两项真机验收卡在同一个前置

F1「一张真图 100% 可见 + Network 带 Authorization」、F3「改坏 token 走一遍点击链」都只能标 **未验证**——A 如实标注、没有替自己宣称绿。它另用只读请求向 `:8001` 取到真 401 事实、并跑了协议层复现（F2 33 例、F3 16 例）作替代。**唯一缺口 = 探针账号**，见 §5 待拍板 ①。

### 4A.4 A 线两项补漏（我派的，已亲验）

- **跨账号泄露（安全）**：`bd38c00` 加 `resetSessions()`，挂在 `App.vue:148 goToLogin()` 这个**唯一出口**上，手动登出与 401/过期共用。A 还查出一个我没料到的点：正文按会话拆在 `eb_msg_<id>` 独立键里，**只清 `SESSIONS_KEY` 会把上一位用户问过的话整包留在磁盘**，故另加 `clearStoredSessions()` 扫前缀清理；且它先 `abortStream()` 再清态，避免在跑的回答把内容清回来。我原先估"约 6 行"，实际 34 行，低估了。
- **F2 完成定义拆半**：`rememberScroll()` 原先只在 `onUnmounted` 调用，而 ChatPanel 现被 `v-show` 常驻永不卸载 → 切工作区这条路再也不写 `scrollTop`。所以 F2 的"会话/滚动不丢"当时**只成立一半**：会话不丢 = 达成，整页刷新后的滚动位置 = 未达成。`c5a61b1` 改为滚动去抖落盘（400ms）+ `visibilitychange:hidden` 兜一次，监听器 `onMounted:141` 注册、`onUnmounted:155` 摘除，已核无重复注册。
- 仍待 A 收尾：删 `DocPanel.vue:144` 死代码 `uploadFiles`（与 `:190` 重复、不走 `createUploadItem` 会触发 TransitionGroup key 警告）。

### 4A.5 B 线一次写越界事故（已复原，我复验）

B 自报：中途 `cd` 进尚不存在的 `ui/` 失败，PowerShell 停在默认 cwd，把 `list-nav.js`、`focus-trap.js` 写进了**主树根** `企业智脑/`，已 `Move-Item` 挪回。它的自查命令带了 `-- frontend` 路径过滤，**照不到仓库根**，所以我另跑：主树 `git status --porcelain`（无路径过滤）+ 根目录 `list-nav|focus-trap` 名单匹配 + 根级 `.js/.css` 清点 → **零残留**。B 主动上报而非隐瞒，记为正分。

### 4A.6 主树卫生（新照出来的，比原先记的更脏）

无路径过滤地看主树：**377 行**未提交条目。除已知的 `tests/browser_*`（约 70）、`static/exports/*.pdf`（约 100）、根级 `kb_*.{csv,txt}`、`logs/*`、`data/*`、`documents/*` 之外，最要紧的是
**`chroma_db/` 处于「已被 git 跟踪 + 运行时写脏」状态**（`data_level0.bin`、`header.bin`、`index_metadata.pickle`、`chroma.sqlite3` 全为 ` M`）——向量库二进制进了版本控制，任何一次问答都会污染工作树 diff。见 §5 待拍板 ③。

---

## 5. 冲突仲裁与全局停写

- 需要别人范围内改动：**在 §4 加一行「请求：…」，不代写**。谁的文件谁改。
- 需要用户拍板（**只有这 4 条**，其余总控已自行裁定并记在 §4B）：
  1. **探针账号**：谁能建、建几个、跑完谁清。缺它只卡两类验收——G3 真机那半、A 线 F1/F3 的真机点击链（`4A.3`）。B 线那套 serverless 视觉套件证明**不需要后端**也能拦白屏与弹对象，所以卡住的面没有想象大。
  2. **重建后端镜像**（约 28 分钟）以证 G3 真机那半。不重建则 G3 永久停在 🟡。
  3. **仓库卫生**：`chroma_db/` 已被跟踪且每次问答都写脏（`4A.6`），另有 377 行 `tests/browser_*`、`static/exports/*.pdf`、根级 `kb_*` 等产物。要不要 `.gitignore` + `git rm --cached chroma_db`？这会改版本控制范围，属破坏性，必须点头。
  4. **「停止」是否等于拒绝 HITL 挂起动作**（后端语义）。前端已按"不等于"实现成**显式保留待确认卡 + 标注已中断**（`ChatPanel.vue`），两种裁定都不会白做，但裁定相反时要翻成显式清除。
- **全局停写条件**：主树 `app/**` 或任一 worktree `frontend/**` 出现未提交改动（除主树那 2 个刻意保留项）→ 全线停手先归属。本轮真实教训：e2 早在后端线工作树里写完却**未提交**，且 `chat.py` 缺 import 使成功路径抛 `NameError`——差一天就没人知道。
## 4B. 总控已自行裁定（不必再问用户）

| 事项 | 裁定 | 理由 |
|---|---|---|
| 401 后聊天内存态残留 | **做**，已落 `bd38c00` | 同机换人是私有化部署常态，属跨账号数据泄露，不是收尾洁癖 |
| `rememberScroll` 只在卸载触发 | **做**，已落 `c5a61b1` | F2 完成定义只成立一半，必须补齐或降级 |
| 死代码 `uploadFiles`（`DocPanel.vue:144`） | **删**，单独一个 commit，动手前 `git grep -n "\buploadFiles\b"` 自证 0 引用 | 与 `uploadFilesParallel` 只差名，正则必须带词边界，误删才是事故 |
| `errorDetail` 不认 Blob | **不做，记我账** | 错误字典是 B 独占文件，A 去 async 化必在合并时撞车；留 TODO 指向 `errcodes.js`，G2 合并后统一处理 |
| HITL 语义未决期间 | **保持显式保留** | 见 §5 待决 ④，UI 两种结果都不返工 |
| 加 `jsdom` + `@vue/test-utils` | **暂不加** | B 已用 `@vue/server-renderer` 出真 HTML + 纯函数单测 + Playwright 真按键，行为覆盖已有；再加是把同一件事测第三遍 |
| 加 `stylelint-declaration-strict-value` | **暂不加** | 内置 `declaration-property-value-allowed-list` 已能拦裸 hex/字号/间距/圆角/阴影，实测有效（`4A.1`） |
| token 文件名 `tokens.css` vs `theme.css` | **定 `theme.css`**，`tokens.css` 这个引用作废 | `theme.css` 已在主干存在且含 91 处 `var(--*)`；为一个名字去重命名文件是纯 churn |
| `rbac.py` 死代码 + 它的测试一起退役 | **自授，做**（C-4） | 删源码与删测它的断言必须同一份授权、同一个 commit；纯源码改动，git 可回退，不属破坏性操作 |
| `data.py:278` 字面量换常量 | **自授，做**（并入 C-2） | 零行为差异，但要多花 28 分钟重建镜像才能证真机，故与 C-2 同批，不为它单独重建 |
| 存量 351 处色债怎么还 | **单向棘轮**（`lint:colors --max-warnings`），不许一次改完也不许长期关闸 | 一次改完会淹没 V1/V2 的真改动；关闸等于没有闸门 |

**写入集变更（重要）**：`frontend/package.json`、`frontend/package-lock.json`、`frontend/.stylelintrc.json` 在 `07ff441`（`codex/fe-prims`）里被我改过——加 `postcss-html`、加 `lint:colors`、`.vue` 纳入解析。A 线若要动依赖，**必须先把 `codex/fe-prims` 合回 `codex/fe-trunk` 再改**，别在旧 lockfile 上叠。集成方向已定：`prims` 含 `trunk`，最终 `trunk` 可直接 ff 到 `prims`。

- 一个分支只属于一个工作树：不许 `git checkout` 别人那条线的分支，要开工就换目录。


---

## 4C. C 线（后端）排期——总控直派，**串行**

**为什么后端不能并行开多个对话**：C-1..C-5 全都要写 `app/api/v1/*` 与 `tests/`，而一个分支只能被一个工作树 checkout（主树 `codex/data-file-catalog` 是唯一持有 `app/**` 的树）。两个 Agent 同写一棵树 = 必然撞车 + 未提交工作互相看不见（本轮 e2 就是这么差一天被埋掉的）。故 C 线一次只跑一个 Agent、一次只放 1–2 项。

| 批次 | 内容 | 为什么这个顺序 | 边界 |
|---|---|---|---|
| **C-1** | 鉴权 401/403 改吐稳定码（见跟进单 §8） | 唯一卡住 B 线「封闭枚举」的一条；状态码零变化、全仓无测试断言中文原文 → 零红口 | 只改 `detail` 值 + 登记契约 + 新增断言；不许碰白名单与 `/open*` |
| **C-2** | R2 `GET /artifacts` 列表 + R8 数据集/artifact DELETE + 级联清理（含 PG `documents` 幽灵表）；顺带 `data.py:278` 字面量换 `OWNER_SCOPE_REQUIRED` | 前端「交成果」视图与误传清理同时解锁；纯增量，不改权限语义 | 禁删真实数据、禁跑迁移、禁连真库写 |
| **C-3** | R1 员工级告警读取 = 闸门 **G4** | 唯一改权限语义的接口项 → **先交评审，评审通过前只读不写** | `alerts.py` 单文件 |
| **C-4** | `Principal.from_user` 的 `or` 抬级 + `rbac.py` 死代码**与其测试**一并退役 | 两笔已记账的账，小且独立 | 见 §4B 新增行：总控已自授，须同一个 commit 交付 |
| **C-5** | R3 SSE canonical `sources` 事件 + B-7 趋势聚合端点 | 契约冻结规则下只准增量，放最后 | 不得下线/改名任何 legacy 事件 |

