# 接班单：V2 挂账一次清（2026-10-08 约 09:0x 交班）

## 10-08 收工接力更新

- 10-09 续验 B21：目标登记提交 `4c6007c`；提交后同名后端与前端复测通过。实际 `git revert -n 4c6007c`＋后端/前端镜像重建＋容器 recreate 后，真浏览器环 20 仍能读欠账，目标列恢复待填（`%TEMP%/evalrun/b21-a-revert-1009`）；原环 20 不核对目标数字，不能把这次绿当作 A 目标在位的证明。装回后另核六枚屏上目标。页面补 `[目标]` 标记、目标机器实测限制及报告 60–120 秒后台查回说明。

- 已接续对话 `01a11909-77ea-77a1-8dc3-baf8873def19`；B18／B19／B22 和 R118 收针已由前班交付。本班在原分支顺序完成 B26 `71e6d16`、B16 `ba4aa8b`、B15 `95c2671`、B13 `ea35969`＋制度摘要订正 `5e6a2d0`。
- 最新正式验收：V1 **9/9 能演示**（`%TEMP%\evalrun\takeover-final-v1b`）；V2 **12/12 能演示**（`%TEMP%\evalrun\takeover-final-v2c`）。每环日志与截图在各目录里，后端与前端新鲜度检查均放行。
- B26 选中表跨批准保留；B15 同一原件进目录、可预览下载，知识库移除保留数据原件，数据删除同步退役目录；B16 上传错误独立显示且列表保留；B13 真图后清理出图拒绝，制度正文与引用保留。各笔实际回滚结果及限制已更新到唯一队列 `docs/backlog.md`。
- 业主已裁 B10：默认 internal、属主按角色密级核验，不增加自读豁免。B16 的前端授权限本班已批准方案；客户真实密级、尺寸与旧残件仍不代改。
- B21 的跨进程样本汇总与分档归属已有 `aee59a9`，本班按业主选择的 policy A 登记六枚产品目标；样本门与真实目标机器测量仍是实测结论的前提。B14 的图与导出内容判据仍见 backlog，不拿存在性演示替它结案。
- 本班继续收 B21/B14：B21 `aee59a9` 让请求与阶段事件带同一 lane/tier，并从持久化 `trace_events` 重放；环 20 真跑三档窗口 1176／638／509，来源为「已落盘的运行事件」，当前窗口按档计数，旧未归属池 3312 枚仍单列并显示 `lane_attribution_absent` 诊断。policy A 目标为问答 10,000、首屏 1,000、缓存命中 999、分析 45,000、进度间隔 15,000、报告 120,000 ms（均为 P95 policy point）；stage 目标仍待定，未经目标机器实测不能对外承诺。B14 `c4ea85b` 将环 7 判据加上真实解码、非默认标题和彩色像素，环 8 判据加上 PDF `/Subtype /Image`；环 7/8 真浏览器复跑均能演示（PNG 43,330 字节／23 枚彩色像素，PDF 93,771 字节／1 枚图）。
- 新增授权边界已并入 `AGENTS.md` 既有安全线：未经业主明确授权，严禁使用重置卡；继续任务、自动续跑、额度不足均不构成授权。没有使用重置卡。

以下为 09:0x 原交班历史，不作为当前待办或读数。

写这枚的原因：上一班（总控）上下文耗尽，V2 的挂账要一整班做完。规矩照 `AGENTS.md`「开发模式」那一节，本单只补**现场事实**，不重复规矩。

## 0. 现在到底在哪
- 分支 `codex/data-file-catalog`，HEAD=`98ceaf6`。本班四笔：`ae27193`（B23／B24）→ `58c18af`（跟账）→ `4ed3939`（B25）→ `98ceaf6`（跟账）。
- **现跑读数（都算数，容器就是这棵码）**：V1 九环 **9/9 能演示**（08:43–08:52，墙钟 497.9 s，out=`%TEMP%\evalrun\v1-b25`）；V2 十二环 **12/12 能演示**（08:52–08:54，墙钟 119.3 s，out=`%TEMP%\evalrun\v2-b25`）。`code_freshness` 两本都放行。
- 环境此刻是干净的：三枚容器带 HEAD 码、ollama 在跑。**不要**再动 `deploy/.env.server`，别再翻 `INDEX_BACKEND`。

## 1. 待办：按「先把演示演砸」排序
每条一枚单＝一个可演示行为＝一棵工作树；本单只给坐标与判据方向，判据要接班的自己写成「屏幕上该看到什么」再动手（判据先于代码）。

1. **B18 同一句话今天走知识库、明天走算数，走算数那次答错了行**（最脏：答非所问的数字）
   - 现读：问句带「数值」⇒ 规划器派给 data 腿，屏上答「这一行的数值为 3，对应数据行：项目=月度差旅194738-01」，把表里第一行当成被点名的那一行，真值 1094738 没答出来。
   - 嫌疑写域：`app/agents/planner.py` 的关键字派腿＋data 腿取行那段。判据方向：同一句被点名的话，两条道答出来的**数**必须一致且等于表里那一行。
2. **B17 文档腿可以零检索答话、还编出处**（现在靠档位绕开，不是治了）
   - 现读凭据：`trace_events` 里那一轮只有一次模型往返、零枚工具调用，屏上却报出一枚产品里不存在的文件名。
   - 要裁的是政策级：文档腿要不要「先检索再说话」的硬规矩。裁完才动码，别先写针。
3. **B19 选了「问答档」步子牌仍写「📊 分析数据」**（屏上自相矛盾）
   - 嫌疑：`app/api/v1/chat.py` 里按关键词回写 `dispatched` 那一串（`data_kw` 那一排）。要么牌子跟档位，要么档位不写死。
4. **B22 改了前端，新鲜度拦门不响**（流程漏洞，会让以后任何前端结论假绿；上一班正要做，被中断，未落地）
   - 事实：`scripts/smoke_v1.py::CONTAINERS`（当时只列 backend／worker／scheduler），`code_freshness` 只比最新 `app` 提交与这三枚的 `StartedAt`。`frontend` 是另一枚镜像（`enterprise-brain-frontend:local`，`docker-compose.yml::services.frontend` 用 `frontend/Dockerfile` 构建，不在 `migrate` 那条道上），改 `frontend/**` 既不重建也不拦门。
   - 现读：`enterprise-brain-frontend-1 Up 12 hours`——屏上跑的前端比 10-07 那两笔前端修复（`2a5e0a6`／`a5c258a`／`5c8cae5`）新还是旧，今天**量不出来**。
   - 改法：把「最新 `frontend` 提交时刻」与 frontend 容器的 `StartedAt` 也放进 `code_freshness` 的合取里（同一把尺、同一句措辞，拿不到读数照样门红）；顺带在册面上写清前端要 `docker compose build frontend` 才换码。
5. **B15／B16／B10／B13 四枚要业主裁或要点点头**（B16、B13 动 `frontend/**`；B15／B10 是归属与档位政策）——开工前先把这四条摆给业主，别自己裁。
6. **B21 SLO 屏量不到毫秒**（样本池每进程内存、重启清零、跨容器不汇；分档归属已由 `aee59a9` 接通）。policy A 目标已登记在目标列，当前仍只显示真实样本的欠账；这条属「读数」不属「对外承诺」，环 20 已钉「说得清欠多少」，别为它开新演示面。

## 2. 本班欠的两件小事（接班顺手收掉）
- `tests/test_r118_subgraph_memory.py` 有一笔**只暂存没并树**的改动（上一班遗留，把 B17 那枚放宽的针改回严格等式，现跑 6 枚全绿）。要么单独一笔收掉，要么问业主。提交一律走 pathspec 形式，别 `git add -A`。
- 工作区脏件（**别提交**）：`chroma_db/chroma.sqlite3`、`docs/testing/r469-*`、`docs/testing/shape-window-*`、`.zcodeignore 0 _p7.py _p8.py _p9.py tests/*.r695stray 词条实践-对象建模-企业智脑/`。

## 3. 这一班踩过的坑，接班直接复用
- **降级演练的办法**（B25 就是这么真演的）：`docker stop enterprise-brain-ollama-1` 再单跑环 7，屏上就出降级那一格；撤下态＝`git revert -n <那笔 sha>`＋重建＋recreate＋重跑同一环。凭据：装回 `%TEMP%\evalrun\b25down`（1,854 字、两处当场点名）／撤下 `%TEMP%\evalrun\b25rev2`（5,027 字原始材料、零句点名）。
- 🔴 **`docker compose up -d ... backend worker scheduler` 会把 ollama 一起带起来**（backend `depends_on` 它）。停完模型去做降级演练，之后任何一次 recreate 都会偷偷恢复它——演练读数取完就别再 recreate。
- 🔴 rg 的 `-r` 是「替换」标志：写成 `rg -rn -e pat` 等于 `-r n`，命中会被替换成字母 n，看着就像「根本没命中」。模式一律紧跟在 `-e` 后面，别裸写第二个位置参数。
- 长读数用 `Start-Process -RedirectStandardOutput` 落文件＋`Wait-Process -Id`，命令 30 s 上限；`--out` 给 `%TEMP%\evalrun\<名>`。环 7 单跑 265–410 s，V1 九环 ≈498 s，V2 十二环 ≈119 s。
- 全量同名件两态（本班 B25 那套）：脏态 8 枚文件＝140 passed＋新钉 4 枚单独绿；commit 后干净态 141 passed。跑 `tests/test_r729_offline_never_dumps_raw_material.py tests/test_offline_runtime_fallbacks.py tests/test_r99_budget_selfconsistency.py tests/test_r210_break_replaces_the_screen.py tests/test_r210_frame_ledger_of_a_broken_round.py tests/test_r459_supervisor_answer_leg_streams.py tests/test_r703_reply_never_fakes_a_chart.py tests/test_r203_answer_leg_streams.py` ≈ 27 s。
- 派工在这台机上仍开不出新线程（百炼 `at_` 那病），V2 这几枚单**自己 sequential 做**比等席位快。

## 4. 收工口径（别改）
- 只报四行：能演示几条／9 与几条／12、不能演示的各差哪一行码、今天合了哪几条、要业主做什么。
- 每班开工与收工各跑一次 `python scripts/dev_metrics.py`，只贴它交回的那几行。
