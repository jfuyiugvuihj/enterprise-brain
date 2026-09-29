# R510 · 终态帧其余四枚键的屏侧脸（R501 欠的那一半）

- 树 `be-r502`（**改道令执行**：原工单写的是 `be-r501`，那棵树与在途的 Pascal/R507 撞写域，本席在 `be-r501` 全程只读未写，现取 `git status --porcelain` 为空即为凭），基点 `8857a8d`，执行层**未 commit／未 push／未建分支**。
- 写集只有两枚：`frontend/src/components/ChatPanel.vue`（+76 / -0）＋新件 `frontend/src/components/__tests__/r510-terminal-read-faces.test.js`（25 枚钉）。
- `frontend/src/assets/theme.css` **一行未动**（四枚新脸复用在册的 `.lane-readout`，零新增色值），`lib/sessions.js`／`lib/profile.js`／`ArtifactList.vue`／`router/**`／`app/**`／`scripts/**` 一枚未碰。

## 1. 接的是哪一格（手法照 `adoptServerDataRead`，不自建第二套）

| 环节 | 现取坐标（本单落地后） | 这一格说什么 |
| --- | --- | --- |
| 后端交 | `app/api/v1/chat.py:2972-2981`（/ask）与 `app/api/v1/chat.py:3653-3662`（/approve） | 两枚出口各交七枚键，本单那四枚都在场 |
| lib 抄 | `frontend/src/lib/sessions.js:482/484/488` `state.terminalRead = { event, seen, data }` | R501 已并树（`c39f926`），本单**一字未改** |
| 面板抄 | `frontend/src/components/ChatPanel.vue:756 adoptTerminalReads`，调用点 `:1061`（/ask 收尾）与 `:1187`（批准续跑收尾），紧跟在册的 `adoptServerDataRead` | 只抄【亲眼在场】的键：`hasOwnProperty` 守卫，缺席的键不写进袋子 |
| 袋子 | `frontend/src/components/ChatPanel.vue:1226 const terminalReads = ref({})` | 与 `serverDataReads` 同一枚 `turnKey`／`storeBag`／`readTurn` 手法 |
| 落盘 | `frontend/src/components/ChatPanel.vue:767 msg.terminalReadData` | 随会话落盘，刷新复原（丙4 钉） |
| 屏上 | `frontend/src/components/ChatPanel.vue:2137-2140` 四条 `<p data-testid>` | 一枚键一张脸，各 21 枚 DOM 断言逐枚点名 |

四张脸（`frontend/src/components/ChatPanel.vue:725-730` 的 `TERMINAL_READ_SHAPES`）：

| 键 | testid | 给了那一句 |
| --- | --- | --- |
| `session_id` | `terminal-session-readout` | 这一轮后端报的会话号：<值> |
| `worker_count` | `terminal-worker-readout` | 这一轮后端报的分析工因数：<值> 枚 |
| `elapsed` | `terminal-elapsed-readout` | 这一轮后端报的耗时：<值> 秒 |
| `answer_length` | `terminal-answer-readout` | 这一轮后端报的答案长度：<值> 个字符 |

## 2. 三形各一张脸（判据①）

| 形 | 屏上 | 钉 |
| --- | --- | --- |
| 后端给了 | 那枚值原样上屏；**0 也是值**（`worker_count: 0` 报「0 枚」） | 甲1／甲5 |
| 后端给了空串（或 `null`） | 「这一轮后端报的 X：后端这一格交回的是空值（它开了口，但没给内容）」 | 甲3 |
| 整格缺席 | **该条 `<p>` 一枚字都不画**，testid 也不出现在 DOM 里 | 甲2／甲8／乙2／乙3／丙3 |
| 键在而值是 `undefined` | 屏上无话可说（既不冒充「交了空值」，也不冒充缺席读数） | 乙5 |

三形两两不并脸由 甲4 逐枚钉（`it.each` 四枚各跑一遍：给了≠空值、缺席=零句）。四枚不许揉成一句由 甲7 钉（四句互不相同＋任一句不许含另一枚的值＋屏上不许出现「本轮读数」这种合并句）。

🔴 **不许回显请求值**：会话号界面自己就有（`activeId`），答案长度本地数得出（`msg.content.length`），耗时界面自己能掐表。丙2 故意让帧里的读数与界面那几枚**不同名不同值**（帧 `srv-side-01`／界面 `r510-local-session`；帧 `2048`／本地正文 9 字），四句必须报帧里那一份；丁4 从源码抠 `terminalReadFace` 的函数体，断它不含 `activeId`／`content.length`／`dataFilename`／`Date.now`。

## 3. 哪一枚今天真能上屏、哪一枚上不了（🔴 不造）

- **今天能上屏**：`session_id`／`worker_count`／`elapsed`／`answer_length` 四枚**全能**。依据是本单现读的 `app/api/v1/chat.py`：两枚 `yield canonical_sse_event("request.completed",` 出口（`:2965-2982` 与 `:3646-3663`）的 `data` 字面里逐枚写着这四枚键，丁3 钉「出口数必须等于 2、每一枚出口的 data 块里必须逐枚含这四枚键名」——后端哪天不再交，这枚钉自己先红，屏侧那句话就不许再说。
- **今天上不了屏的场合**（都是「后端根本没给」，界面一律整格不画，不补空串、不补 0、不写「说不准」）：
  - **缓存命中那一腿**：`app/api/v1/chat.py:2597 cached_response()` 只发 `status`／`text`／`sources`／`done`，**整枚 `request.completed` 都不发**，所以命中轮的这四格线上就没有读数（乙2 钉的就是这个形状：`result.state` 里连 `terminalRead` 都不许多出来）。
  - **队列终态载荷**：`app/api/v1/chat.py:2242 build_queue_terminal()` 的键集里没有这四枚（R501 §1.4 已取证，本单未碰后端）。
  - **legacy `done` 帧**：`app/api/v1/chat.py:2291 done_sse_frame()` 同样不带。
  - **比树落后的镜像／旧后端**：帧不带这四枚 ⇒ 四句一句都没有（丙3 钉）。
- **本单没编脸的键**：`awaiting_steps`（R501 交回但零消费点）、信封那五枚（`trace_id`／`task_id`／`sequence`／`timestamp`／`status`）都不在写域里，本单一枚没接。

## 4. 数字（执行层自报）

| 项 | 读数 |
| --- | --- |
| `npx vitest run`（本单落地后） | **135 files / 2721 tests / exit=0**（10.0 s） |
| 基点复取（同名件全量、仅排除本单新件） | **134 files / 2696 tests / exit=0** |
| 差值 | +1 file / **+25 tests**，逐枚等于本单新钉枚数（甲 11＋乙 5＋丙 4＋丁 5=25，另 甲4 是 `it.each` 展开成 4 枚已计入 11） |
| 在册反向钉复跑 | `r415`(13)／`r424`(13)／`r150-chat-panel`(20)／`r427`／`r501`／`no-bare-code`／`r208`×2 合 **8 files / 123 tests 全绿**，一枚未改宽 |
| `npx stylelint "src/**/*.{css,vue}"` | **148 problems (0 errors, 148 warnings)**，与在册预算 `--max-warnings=148` **同数**（零新增色值、`theme.css` 未动） |
| 运行时外部请求 | 本单零新增请求（四枚脸只读 `state.terminalRead`，无 `http`/`fetch` 调用） |
| 位图 | 本单没产图 |

## 5. 三把刀（变异只落本工作树，跑完逐字节还原）

三把刀跑完都现验 `frontend/src/components/ChatPanel.vue` 的 `sha256[:16] == 35ad37fa7e67b2cb`，三次全部 **same=True**。每把刀都跑「新件＋r415＋r424＋r150」四枚件（71 枚）。

**刀① 把缺席补造成「说不准／空值」**（`terminalReadFace` 里「整格缺席 ⇒ 返回空串」那一支改成返回空值那一句）→ **11 枚红**（`r424`/`r415`/`r150` 仍全绿，红全在本件）：

```
AssertionError: session_id: expected [ Array(1) ] to deeply equal []
AssertionError: expected [ '这一轮后端报的耗时：后端这一格交回的是空值（它开了口，但没给内容）' ] to deeply equal []
AssertionError: 后端没说话，消息对象里就不许多这一枚键: expected true to be false
 Test Files  1 failed | 3 passed (4)
      Tests  11 failed | 60 passed (71)
```

**刀② 把四枚揉成一句**（四条 `<p>` 换成一条 `terminal-readout-all`，四句用「｜」拼起来）→ **16 枚红**：

```
AssertionError: session_id: expected [] to deeply equal [ '这一轮后端报的会话号：srv-9' ]
AssertionError: 界面自己的会话号是 r510-local-session，不许冒充后端读数: expected [] to deeply equal [ '这一轮后端报的会话号：srv-side-01' ]
AssertionError: terminal-session-readout: expected '<script>\n/**\n * R174 · 冷启动深链：`/chat…' to contain 'data-testid="terminal-session-readout"'
AssertionError: expected [] to deeply equal [ '这一轮后端报的分析工因数：0 枚' ]
 Test Files  1 failed | 3 passed (4)
      Tests  16 failed | 55 passed (71)
```

**刀③ 拿请求值回显**（缺席那一支改成交回 `activeId.value`／`msg.content.length`／本地掐的表）→ **12 枚红**：

```
AssertionError: session_id: expected [ '这一轮后端报的会话号：r510-local-session' ] to deeply equal []
AssertionError: expected [ '这一轮后端报的答案长度：9 个字符' ] to deeply equal []
AssertionError: expected [ '这一轮后端报的耗时：0.1 秒' ] to deeply equal []
AssertionError: 回显了 activeId：那就是把界面自己的数冒充成后端读数: expected 'function terminalReadFace(msg, index,…' not to contain 'activeId'
 Test Files  1 failed | 3 passed (4)
      Tests  12 failed | 59 passed (71)
```

⚠️ 施工自陈：刀①与刀③各有一次**变异体本身**写成 `shape.label`（该变量在同一函数里声明于守卫之后），跑出来是 ReferenceError 而不是判据红。两把都改用 `TERMINAL_READ_SHAPES[key].label` 重跑，上面贴的是重跑的读数；第一次的产物已丢弃，不作为凭据。

## 6. 没做到／请总控裁

- **没建第二套判据**：四枚脸只从 `result.state.terminalRead.data` 取数，值不做单位换算（`elapsed` 后端给几秒就报几秒，不毫秒化）、不做四舍五入、不做「约/近」修饰。要做单位本地化得改 `lib/provenance.js`，那在本单禁碰清单里。
- **措辞住的地方**：`ChatPanel.vue:1216-1219` 那段分工写死「lib/sessions.js 读事实、lib/provenance.js 说人话、本面板只挂元素」。同屏在册的 `serverDataOf`（R415）与 `laneFaceText` 两枚**已经在面板里说话**，本单照同一先例落在面板；把四枚措辞后挪 `provenance.js` 是另一手，请裁。
- **`null` 与空串并脸**：本单把「键在而值为 `null`」与「键在而值为空串」交给**同一句**「后端这一格交回的是空值」。今天两枚后端出口都不可能交 `null`（`str()`／`len()`／`round()` 造出来的），所以不在线上任一路径上；工单只要求「给了／缺席／空串」三形分开，这一格若要 `null` 另配一张脸，说一声，本单补。
- **浏览器仍看不到改动**：镜像未重建（明令不许碰容器），本纸全部是文字凭据＋DOM/源码断言口径，没起 dev server、没跑 `npm run build`、没截图。
- **没跑全量 pytest 门**（明令不许 `scripts/run_gate.py`）；`docs/api/contract-v1.md` 一个字未改。
- **后端那一半本单一行未碰**：缓存命中道不发 `request.completed`、队列终态载荷不带这四枚键——那两格要真上屏得后端补发，属 `app/**` 那一手（R501 §5 已提案，本单复述不重提案）。
