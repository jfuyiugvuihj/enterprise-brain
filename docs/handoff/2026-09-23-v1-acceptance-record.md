# V1 完工判定表（2026-09-23 · 总控线）

证据基线：主树分支 `codex/data-file-catalog` HEAD `c3ea42f`（产品代码基线 `f515494`）。
可跑读数（今天全部由总控亲自复跑，不采信执行层自述）：后端 **3641 passed / 39 skipped / 0 failed**（全量，211 s）· 前端 **761 passed / 36 files** · `lint:colors` **148 problems（0 errors）** · `npm run build` **EXIT=0** · 空气隔离闸门 7 格全 PASS + 3 格 PENDING。

三态口径（沿用 R169 那一套）：**有证据** = 有可机读的断言在跑；**补不了** = 本机定义之外（真容器 / 真浏览器 / 真模型 / 真机计时）；**缺** = 今天确实没有。

## 1. V1 业务主线（逐条）

| 主线环节 | 状态 | 证据 / 缺口 |
|---|---|---|
| 登录 | 有证据（前端 9 格新补 + 后端 `POST /api/v1/login` `app/api/v1/auth.py:63`） | L1–L9 见 `frontend/src/components/__tests__/r169-login-screen.test.js`；L10 真账号真停用真 JWT = **补不了（真容器）** |
| 工作台 | 有证据 | 10 屏路由在 `frontend/src/router/index.js`；`ui/__tests__/states.test.js` 钉住空态不是打断 |
| 上传制度文档 | 有证据 | `POST /api/v1/chat/upload` `app/api/v1/chat.py:2896`；解析器 `app/rag/loader.py`（pdf / docx / txt / md）；上传与索引失败有稳定状态（R21 / R79 族用例） |
| 文档问答并看到来源 | 有证据（Q5） | `r150-chat-panel.test.js` + `lib/r150-event-claims.test.js` 钉住"一条命中：文件名可点、卡片带版本/密级/部门/相关度"，后端不发 sources 就不画出处卡 |
| 上传 Excel/CSV | 有证据 | `app/api/v1/data.py` 上传/列表/预览；`r169-data-chart.test.js` D1–D4 四张脸 |
| 指标统计与数据问答 | 有证据，🔴 有一枚已立单缺陷 | D3 统计取画像不取样例行长度；🔴 **只有一行表头的 CSV 会让数据面板渲染期抛错** → R170 在修（`app/tools/excel.py:106` → `app/api/v1/data.py:115` → `DataPanel.vue:310`） |
| 生成图表 | 有证据 | `app/tools/chart.py` 支持 bar / line / pie / radar；对话内出图只走带 Bearer 的 blob 通道（C1–C4）；C5 真像素 + 真落盘 = **补不了（真容器 + 真浏览器）** |
| 导出报告 | 有证据 | `app/tools/export.py` 出 PDF（含标题 / 日期 / 图表 / 生成时间 / 数据来源句）与 Excel；R2 / R3 格钉住"报告先经确认门、非图片产物另存仍是 blob:"；R4 真报告内容落真文件 = **补不了（真容器 + 真模型）** |
| 一条异常或告警结果 | 有证据 | 规则 CRUD 与手动巡检：`app/api/v1/alerts.py:342/371/382/396/407`；`test_phase4_alerts.py` / `test_alert_scan_scope.py`；🔴 但**跨部门 manager 能读到别部门告警正文**（R163 A 类）→ R176 在修 |

## 2. V1 功能要求里"看不见摸不着"的那几条

| 要求 | 状态 | 说明 |
|---|---|---|
| 页面显示当前步骤 / 处理中 / 成功 / 失败 / 等待确认 | 有证据 | R168 把「等待确认」从对话流抽成一屏真待办（七张脸互不相同，零假行由赋值出口枚举钉死）`frontend/src/components/hitl/HitlPendingPanel.vue` |
| 用户可以取消或离开当前流，回来后不拿到另一轮的错误结果 | 有证据（今天补上） | `r169-chat-panel.test.js` Q7 取消两步四回执 + `lib/__tests__/r169-cancel-stream.test.js` Q5 读流层 7 枚；后端 `/ask/{id}/cancel` `chat.py:1522`、`/queue/{id}/cancel` `:3423` |
| 长任务不会无限等待 | **补不了** | 真机项，等 run6（阶段 A 判据①）；离线只有 `MODEL_CONCURRENCY_WAIT_SECONDS` 与档位超时用例 |
| 不出现明显死链接 / 空白页 / 技术异常串 | 有证据 | `lib/errcodes.test.js`(84) + `lib/no-bare-code.test.js`(17) + `insight-alerts.test.js` W7 四张脸两两不同；🔴 一枚文案位缺口（会话失效被踢回登录页零提示）→ **R171 排队**（等 `App.vue` 解锁） |
| 无数据用空态、不许假数字填真实业务区域 | 有证据 | `ui/__tests__/states.test.js` + R168 的零假行机制；位图侧旧地球图已换（假统计烤死像素那事已结） |
| Multi-Agent 体现分类 / 文档 / 数据 / 图表 / 汇总 | 有证据 | `test_agent_collaboration.py` 族 + trace 载荷出口（R141 三处读数） |
| 演示数据必须明确是演示数据 | 有证据 | 评测与演示集命名 + 语料侧 `96 篇` 明写；🔴 105 题里 55 条 `must_contain` 在语料搜不到出处，改题要动评测集 = **业主单独批** |

## 3. 🔴 这一条现在压着 V1 的宣布

R163 的越权矩阵（51 格，13 格真红）实测出 **3 格 A 类内容越权**：数据文件预览无行级过滤 / 跨部门 manager 读到别部门告警正文 / 知识图谱 `visibility=private` 写而不读。⇒ 计划书与旧看板里「阶段 C 越权命中 0 条」**已作废**，在 R176 / R177 / R178 / R180 四枚修复件并树之前，V1 不具备对客户宣布"权限这一层可以演示"的条件。这不是措辞问题，是三条可复现的读路径。

## 4. 只有业主本人能做的（V1 收口的必要条件）

1. **起 Docker Desktop**（若再崩先清 `engine.sock.stale`）。它一并卡住：阶段 A 真机复验、run6 跑分窗、pgvector 双写窗重开（等 R130）、R161 供数、R162 容器那 1008 枚的正向缺口、R177 容器侧 private 存量读数。
2. **前后端镜像线上态**：镜像落后主树，演示前需 `docker compose build migrate frontend backend` + `up -d`（业主侧动作，配置在镜像里 ⇒ 改了 `.env` 不重建等于没改）。
3. **改评测集**（55 条无出处）需业主单独批；run6 开窗前需 `powercfg /change standby-timeout-ac 0`（昨晚机器休眠冻住四枚 Agent 一整夜）。
4. 裁 **R61 甲/乙**（部门列普查读数已交，本机净影响 0 枚）、**H20**、**D14 之后的新增闸门**。
5. 主树 8 项未跟踪垃圾删除、心跳 automation-2 的 `target_thread_id` 改指本线程。

## 5. 一句话结论

**V1 的离线部分今天见顶**：功能件与证据都在树上（3641 + 761 枚用例），R169 把前端拆成 40 格后 34 格有可机读证据；剩下的 6 格 + 长任务计时 + 演示路径 = 真机，越权 3 格 = 在修。**下一次总控主动开口只可能是两种**：要么越权族修完 + 真机窗口跑完 ⇒ 可以宣布 V1；要么卡在业主侧动作上动不了。
