# R694 · 前端九环浏览器走查＋两张失败脸（V 行从「未验」变成有凭据）

**号**：R694　**基点**＝派工那一刻主树 HEAD 现取（本段落盘之后那一枚；产品码代次＝`4ebfaff`）
**独占工作树**：由总控预配并告知路径。🔴 本单**不改任何被跟踪源文件**，货是证据不是代码。
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取。

## 为什么这一格一直挂着

`docs/version-roadmap-and-requirements-2026-10-05.md` 的 §9 判据 5 要「前端九环走查有截图与断网自证（Network 外部域名请求 0 条）」。账面现状（`docs/testing/v1-cell-closeout-2026-10-05.md` 本班续席更正）：只验过一次真实键盘问答＋SSE 帧账，**九环没逐项打勾**，两张失败脸没拍。第二验证机 `ssh vm` 不可达（`192.168.254.128:22` 现取 False），所以这格只能在本机浏览器做。

## 环境前置（开工先验，不满足就停下回报）

1. `docker ps` 现取必须七枚齐（backend／worker／scheduler／frontend／postgres／redis／ollama，除 frontend 外 healthy）；
2. `docker images` 里 `enterprise-brain:local` 的 `CreatedSince` ≤ 2 小时（总控在派工前重建后端镜像并 `--force-recreate` 三件，走查才对着当代码走）；不满足 ⇒ **停下**，不许自己 rebuild／recreate（那是总控的活）。
3. 前端源码在过去 30 h 零提交、`enterprise-brain-frontend:local` 不落后 ⇒ 前端**不许**重建，也不许改 `frontend/**` 任何文件。
4. 登录凭据：从 `deploy/.env.server` 里按键名取 `AUTH_USERNAME`／`AUTH_PASSWORD_HASH`（走查用浏览器口令，**纸面与截图一律不落明文**，只写「取自 env 键名 X，值未记录」）；若浏览器口令与 hash 对不上（登录失败）⇒ 停下回报，不许改产品码或改 env。

## 九环（每环一枚凭据，缺一枚判负；打不上勾就写「未达＋原因」，不许留空）

| 环 | 要看到什么（可失败判据） | 必交付物 |
|---|---|---|
| 1 登录页 | 地球图在位、字体本地（Network 里 `googleapis`／`gstatic` 请求 **0 条**）、首屏无白屏 | 1440 截图＋Network 计数读数 |
| 2 登录成功进工作台 | 背景四层（base／art／grid／scrim）在 DOM 且 `aria-hidden`，正文卡片实心不透底 | 1440 与 760 两张截图 |
| 3 上传文档 | 传一枚真档（本仓夹具里挑，不许造带字的图），进度态与完成态各自有名，落库后文档计数 +1 | 上传前后计数读数＋截图 |
| 4 文档列表／状态 | 刚传的那枚能列出、状态可读、来源可查回（catalog 面） | 截图＋那一行的字段名册 |
| 5 知识问答（流式） | 真实键盘输入一问，正文**逐帧长出**（帧序号单调增长）、步骤牌与来源卡出现 | 帧账读数（起止秒数）＋两张截图 |
| 6 权限隔离 | 换一个Principal（演示账号）问同一句，可见集不同或明确说明今天不可证；**不许**拿合成标签翻绿 | 两个身份的可见集枚数对照 |
| 7 数据分析 | 触发一次表格分析路径，图能出、数值与来源可对 | 截图＋图的产物路径 |
| 8 报告导出 | 报告档走一次，答案件可查回、导出件字节数 >0 且非空图 | 导出件字节数＋文件名册 |
| 9 HITL／审计 | 待批准那一条能出现并可批准或驳回；批准后答案里引用它（批准失败会倒扣，别当成 0） | 批准前后两态读数 |

## 两张失败脸（注入法，禁改产品码）

- **embedding 缺失**：用 `docker compose exec` 起一次性容器改环境变量让 embedding 后端不可达（**不许动宿主 env 文件、不许动常驻 backend 的配置**；用一次性 `docker compose run` 或临时端口）。UI 必须给出人话的失败面，不是转圈或白屏。
- **无 GPU**：`OLLAMA_REQUIRE_GPU=1` 已在生产 env 里（R673 已并树，两种姿势各自具名）。失败脸取证＝把硬门在位／撤掉两种姿势下的**屏上文案**各拍一张，并核对 `R673 GPU 姿势声明` 那行出现在后端日志。撤门只许在一次性容器里做。
- 两脸拍完必须把栈**恢复**到 §前置 2 的状态，并把恢复读数写进纸。

## 断网自证

DevTools 切 Offline 各刷一次登录页与工作台：不许白屏；Network 外部域名请求 0 条。两张截图。

## 判据（每条可失败）

1. 九环逐环有「达／未达＋读数」，未达的环必须写出差在哪一条、归因到哪个符号。
2. 每张截图落 `docs/testing/walkthrough-2026-10-06/`（新目录，逐枚点名文件名与字节数），纸面引用文件名而不是行号。
3. 🔴 **零源文件改动**：`git diff --numstat HEAD` 对 `app/**`／`frontend/**`／`deploy/**`／`docs/handoff/**`／评测夹具交回空；发现缺陷只立号不改码，把复现步骤写进「缺陷清单」那一节。
4. 恢复自证：走完把临时容器／一次性改动清干净（`docker ps -a` 与 `docker ps` 差集写进纸，临时容器不许留在册），七枚 Up 且 healthy 与 §前置 1 同形。
5. 交付：凭据纸 `docs/testing/walkthrough-2026-10-06/README.md`（读数与秒数，不许形容词）＋`python scripts/tickets_index.py --verify` rc=0＋控制符各 0 枚＋坐标一律 `文件::符号`。
6. 若某环根本走不下去（凭据、代次闸、失败脸注入做不到）⇒ **停下回报**，把走到的位置和卡住的读数交回来，不许用「离线单测绿」冒充「浏览器验过」。

## 写域（只许这些）

`docs/testing/walkthrough-2026-10-06/**`（新目录：纸＋截图）／新增 `scripts/r694_*.py`（Playwright 驱动，只读产品码）／新增 `tests/test_r694_*.py`（只对纸面完整性作离线校验，不 import app、不开浏览器）／`docs/tickets/R694-*.md`

## 禁区（踩线即退回）

`app/**`／`frontend/**`／`deploy/**` 与任何 `.env*` 的值／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`pyproject.toml`／`uv.lock`／`scripts/run_gate.py`／夜窗量具 `scripts/eval_*`·`r57*`·`r59*`·`r63*`·`r674*`／宿主电源设置／主树任何路径／镜像 rebuild·recreate（属总控）。
