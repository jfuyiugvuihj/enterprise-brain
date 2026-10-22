# 并行工作进程工单包（2026-09-16 11:4x）

执行载体说明：本会话 `multi_agent_v1__send_input` / `wait_agent` / `spawn_agent` 全部返回 unsupported call，
因此并行开发改用**本地 Codex CLI 工作进程**：`codex exec --sandbox danger-full-access -C <树> -`，
提示词经 `cmd /c ... < 工单文件` 从 stdin 注入（直接对 `codex.cmd` 用 `-RedirectStandardInput` 会得到
`No prompt provided via stdin.`）。总控只认 commit 与自己重跑的闸门，不采信任何自述。

| 进程 | 树 / 分支 | 工单 | 写集（互斥，越界即回滚） |
|---|---|---|---|
| W1 | `C:/Users/fengx/PycharmProjects/fe-trunk` · `codex/fe-trunk` | 跟进单 A-6 三件：补 `storage_unavailable`、删 `theme.css` 全局死规则 `.empty-state`、把码表三列对账改成 `git show` 读真源 | `lib/errcodes.js`、`lib/errcodes.test.js`、`assets/theme.css`、`package.json` |
| W2 | `C:/Users/fengx/PycharmProjects/fe-artifacts` · `codex/fe-artifacts` | 补两条悬空未接：`GET /artifacts` 列表进界面、`DELETE /artifacts/{id}` 与 `DELETE /data-files/{filename}` 的删除入口（含两步内联确认） | `components/ArtifactList.vue`（新建）、`components/DataPanel.vue`、其测试、必要时 `panel-states.test.js` |
| W3 | `C:/Users/fengx/PycharmProjects/be-r14` · `codex/be-r14` | R14-A1 服务端聚合端点 `GET /dashboard/summary`；告警计数须再过 `_require_alert_management`，无权限则**省略字段**；待审批数复用 R13 同一存储与部门口径 | `app/api/v1/dashboard.py` 与注册点、`tests/` 新文件 |

三者的共同禁令：禁 `git add -A`；色值锚只准降；不许改 `app/common/rbac.py`（刚被 C-4 收敛）；
不许碰主树。fe-trunk 与 fe-artifacts 的 `node_modules` 是指向同一份的目录联接，只读共享。

---

## 工单原文

你是前端执行者 W1。工作树固定 C:/Users/fengx/PycharmProjects/fe-trunk（分支 codex/fe-trunk，HEAD=033a11e）。主树只读，用来查文档；不许在别的树里写。

先读：C:/Users/fengx/PycharmProjects/企业智脑/docs/handoff/2026-09-15-frontend-startup-prompts.md 第 7 节「跟进单 A-6」（本单全文与判据），以及同目录 2026-09-15-orchestration-board.md 的 4L.5、4M、4O 三节。

任务＝A-6 的 ①②③，逐任务一个 commit，前缀 fix(frontend/A-6-n) / test(frontend/A-6-n)。

你的写集只有这四个文件：frontend/src/lib/errcodes.js、frontend/src/lib/errcodes.test.js、frontend/src/assets/theme.css、frontend/package.json。其余全部只读。特别注意：DataPanel.vue 与 components/** 正被另一个进程 W2 修改，你碰就是冲突。

硬约束：
1. storage_unavailable 的文案不许与 storage_read_only 共用（表不存在 与 只读降级 修的不是同一件事）。
2. 删 theme.css 的 .empty-state 之前，必须实跑 git grep -nE 'class="[^"]*\bempty-state\b' -- frontend/src 证明零引用；判据不满足就停下报告，禁止改测试凑绿。
3. 对账测试取后端枚举必须用 git show codex/data-file-catalog:app/agents/contracts.py（worktree 共享 object DB）。禁止 readFileSync 本树 app/**——那里停在分支点、只有 17 码，会假绿。取不到 ref 或解析失败必须显式 fail，禁止 skip。
4. 色值锚 --max-warnings 只准降，降完必须等于实测值。
5. 验证只用 cd frontend 后 npm run test / npm run lint / npm run lint:colors；不要跑 npm run build（可能与 W2 抢资源）。
6. 提交一律显式列路径，禁 git add -A。每个 commit 附测数、色值实测/锚两个数、判据命令原始输出。


---

你是前端执行者 W2。工作树固定 C:/Users/fengx/PycharmProjects/fe-artifacts（分支 codex/fe-artifacts，HEAD=033a11e）。该树 frontend/node_modules 是指向 fe-trunk 的目录联接，只读使用：不要 npm install、不要删它。

背景（演示在即，这两条属"后端已交付、界面用不到"的悬空，看板 §4O.2 记着）：
① GET /api/v1/artifacts 分页列表已交付，但前端 0 消费者；
② DELETE /api/v1/artifacts/{id} 与 DELETE /api/v1/data-files/{filename} 已交付，但前端没有任何删除入口。

要求：
1. 新建 frontend/src/components/ArtifactList.vue：拉 /artifacts（query: limit/offset；响应字段 artifacts / total / returned / limit / offset / has_more / artifact_type；行字段 artifact_id、artifact_type、filename、content_url、download_url、expires_at、created_at），展示文件名/类型/时间，提供「打开」与「删除」。打开必须走 ../lib/artifacts 的 fetchArtifactBlob（产物地址要带 Bearer，不许直链 img src 或 window.open 裸地址）。删除用两步内联确认（点一下变「确认删除？」再点执行），禁止 window.confirm。
2. 把它挂进 frontend/src/components/DataPanel.vue 的「数据文件」区之后。
3. DataPanel 增加「删除所选数据文件」：只对当前 dataFile 调 DELETE /data-files/{filename}，成功后清掉表状态并重载列表；同样两步内联确认。
4. 四态必守：进行态 UiLoadingState；错误态 UiErrorState + errorDetail + isPermissionDenied，且「无权限」与「空列表」必须分开渲染；空态 UiEmptyState。正文里禁止出现裸 snake_case 错误码名。样式优先复用 theme.css 既有类；确需新规则只准用 var(--...) 令牌，不许写任何裸色值，也不许改 theme.css 与 package.json（W1 占用）。
5. 新建 frontend/src/components/__tests__/artifact-list.test.js 覆盖：加载中 / 无权限 / 空 / 有数据 / 删除二次确认 / 失败文案；并给 DataPanel 的删除入口补测。
6. 写集只有：components/ArtifactList.vue、components/DataPanel.vue、components/__tests__/artifact-list.test.js、components/__tests__/panel-states.test.js（仅在必要时补断言）。lib/**、assets/**、package.json、主树、be-r14 一律禁改。
7. 验证：cd frontend 后 npm run test / npm run lint / npm run lint:colors（不要 build）。色值实测若超过锚 339，说明你写了裸色值——改代码，不许抬锚。
8. 提交显式列路径，前缀 feat(frontend/W2-n)，commit message 写清判据与测数。


---

你是后端执行者 W3。工作树固定 C:/Users/fengx/PycharmProjects/be-r14（分支 codex/be-r14，HEAD=6589bbc）。本树没有 .venv，跑测试用主树解释器：C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -m pytest -q（必须在本树目录下执行，这样 import app 解析到本树）。不许去主树写任何文件。

先读：C:/Users/fengx/PycharmProjects/企业智脑/docs/handoff/2026-09-15-backend-followup-requests.md 第 10 节（R14）与 orchestration-board.md §4O.1。

任务 R14-A1：给总览页一个服务端聚合端点（此前前端被迫自己手写乘数线）。
- 新增内部只读端点 GET /api/v1/dashboard/summary，按登录者可见范围返回真实聚合：文档数、数据文件数、待我审批数、告警计数。
- 硬约束一：告警计数必须先过 app/api/v1/alerts.py 里 _require_alert_management 那道判定（约 :96-108）；无该权限时**省略该字段**（不返回 0、不返回 null）。把「无权限」和「没有告警」混成一个 0 就是假健康。
- 硬约束二：待审批数复用 R13 的 /hitl/pending 同一存储与同一部门口径，不许新造第二套判定；缺表沿用 R13 的 503 storage_unavailable 语义——要么整体 503 要么省略该字段，二选一但必须有测试钉住你选的这条。
- 只准走既有 storage/registry 与授权判定；不许新增错误码，确需新增先停下报告理由。
- 红底先行：测试先写（含「staff 无告警权限时响应里没有 alerts 这个键」），再实现。
- 写集：app/api/v1/dashboard.py（或路由注册的合适位置）+ 注册点 + tests/ 新文件。禁改 app/common/rbac.py（刚被 C-4 收敛）、app/rag/filters.py、app/api/v1/chat.py、frontend/**、docs/**。
- 收尾给出全量数字（基线 830 passed / 22 skipped / 0 failed）与该端点的鉴权矩阵（匿名/staff/manager/admin 各返回什么）。
- 提交显式列路径，前缀 feat(backend/R14-n)。

