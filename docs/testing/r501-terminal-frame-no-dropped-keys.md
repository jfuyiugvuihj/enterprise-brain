# R501 · 终态帧唯一解码处不再丢 `data` 的其余键（前端块 D 的 G03 那一格）

- 树 `be-r501`，基点 `092fb34`（detached），执行层未 commit／未 push／未建分支。
- 写域内实际动过的只有两枚：`frontend/src/lib/sessions.js`（三行原地改）＋新件
  `frontend/src/lib/__tests__/r501-terminal-read-hands-back-data-keys.test.js`。`app/**` 一行未碰。
- 本单范围经总控更正令缩窄两次：原判据 1–2（G04「会话回得来」那两格）**已落、作废、不再做事**；
  剩下一格就是本文这一格。行号全部自己 `rg -n` 现取，底本 `docs/handoff/2026-09-26-v1-frontend-gap-list.md`
  是 `@ac84f1a` 时点的纸，它的 `lib/sessions.js:478-482`／`terminal_data_filename → EXIT 1` 两行**今天都已过期**
  （现读见下），照抄那本纸会去补一件已经补好的东西。

## 1. 三张账（逐枚现取）

### 1.1 表 A · 后端今天在终态帧里交出哪些键（读 `app/**`，只读）

`request.completed` 在全仓只有两枚出口，两处 `data` 的字面键集**逐枚相等**（新件甲1 钉这件事）：

| 出口 | 现读坐标 | `data` 的键（七枚） |
| --- | --- | --- |
| `POST /ask` 同步道 | `app/api/v1/chat.py:2943`（`data` 体 `:2950-2959`） | `session_id` / `data_filename` / `worker_count` / `elapsed` / `answer_length` / `awaiting_hitl` / `awaiting_steps` |
| `POST /approve` 续跑道 | `app/api/v1/chat.py:3624`（`data` 体 `:3631-3640`） | 同上七枚，一字不差 |

- `data_filename` 的值出自 `app/api/v1/chat.py:362 terminal_data_filename()`：正好一枚交文件名，零枚与多枚都交空串。
- 信封那六枚（`request_id`/`trace_id`/`task_id`/`sequence`/`timestamp`/`status`）出自 `app/api/v1/chat.py:237 canonical_sse_event()` 的 `:250-256`，与本单那枚 `data` 不是同一格。

### 1.2 表 B · 解码处今天读了哪几枚（改前 / 改后）

唯一解码处＝`frontend/src/lib/sessions.js` 里 `createStreamReducer` 的 canonical `request.completed` 分支（现取 `:478-482`）。

| 后端给的键 | 改前（基点 `092fb34` 现读） | 改后（本单） |
| --- | --- | --- |
| `awaiting_hitl` | 抄进 `state.awaitingHitl`（`:479`），消费点 `components/hitl/HitlPendingPanel.vue:562` | 一字未动 |
| `awaiting_steps` | 抄进 `state.pendingSteps`（`:480`），**全仓零消费点** | 抄写未动；整格读数里在场 |
| `data_filename` | 抄成 `state.terminalDataFilename`（`:481`，只在亲眼读到字符串时写），消费点 `components/ChatPanel.vue:698 adoptServerDataRead` → 屏上 `:2063-2064 data-testid="server-data-readout"` | 一字未动 |
| `session_id` | 🔴 **丢** | 交回（`state.terminalRead.data.session_id`） |
| `worker_count` | 🔴 **丢** | 交回 |
| `elapsed` | 🔴 **丢** | 交回 |
| `answer_length` | 🔴 **丢** | 交回 |
| 后端明天新增的任意键 | 🔴 **丢**（白名单抄写） | 交回（抄写式是整份 `data`，不靠名单） |

改后每一枚终态读数长这样，并**按事件各交一张**：`state.terminalRead = { event, seen: Object.keys(data), data: { ...data } }`。

### 1.3 表 C · 契约对这一帧写了哪几枚键（现读 `docs/api/contract-v1.md`，本单未碰它）

| 契约段名 | 现读行号 | 写了什么 |
| --- | --- | --- |
| `### Compatibility note 2026-09-14 (HITL rounds, terminal-state honesty, legacy chat scope)` | `:1198`，正文 `:1200-1205` | `request.completed`  gained 三枚可加字段 `answer_length`/`awaiting_hitl`/`awaiting_steps` |
| `## R414 · 数据问答那一条腿：终态那一帧必须说得出「这一轮用的是哪份数据文件」` | `:5375` | 键集与三态：`:5385-5386` 交回改前六枚、`:5393-5397` 交回 `data_filename` 的三态表 |
| 同上一节的「今天还没接的两格」 | `:5412-5415` | legacy `done` 帧与队列终态帧**仍不带** `data_filename`（被 `tests/test_r254_sync_lane_terminal.py:151`/`:175` 按名钉住键集） |
| `## Frontend Collaboration Boundary` | `:1191-1195` | 后端不改 `frontend/`，前端消费本契约；界面上的角色检查不是授权闸 |

### 1.4 🔴 两格分开写：「后端给了、界面没读」≠「后端根本没给」

- **给了没读**（本办的那一格，已办）：`session_id`/`worker_count`/`elapsed`/`answer_length` 四枚，两枚出口都在发，解码处丢在半路；另有 `awaiting_steps` 属于「抄进 state 了但屏上零消费点」，本单没替它编脸。
- **后端根本没给**（本办不了，也不许前端推断/补造）：
  - legacy `event: done` 帧（`app/api/v1/chat.py:2269 done_sse_frame()`，键体 `:2291-2298`）里没有 `data_filename`；
  - 队列终态载荷（`app/api/v1/chat.py:2220 build_queue_terminal()`，键体 `:2239-2251`）里也没有；
  - 缓存命中那一腿（`app/api/v1/chat.py:2575 cached_response()`）**整枚 `request.completed` 都不发**，只发 `status`/`text`/`sources`/`done`（`:2576`/`:2578`/`:2589`/`:2605`）；
  - 信封键 `trace_id`/`task_id`/`timestamp`/`status` 与 `data` 里那四枚的「屏上脸」另属一手（见 §6）。
- 这三处在 lib 层的形状已经被钉成「不是同一张脸」：帧没到 → `state` 里连 `terminalRead` 这枚键都不许多出来（新件乙1/乙4）；帧到了但一格没给 → `seen` 是**空数组**而不是没这一枚键（丙2）。把后者写成前者就是「后端没说话」冒充「后端说了空话」，反过来则是丢读数。

## 2. 改动清单

| 文件 | numstat ± | sha256[:16] |
| --- | --- | --- |
| `frontend/src/lib/sessions.js` | 3 / 3（净零行；文件仍 1006 行） | `784651f55ffffa6b` |
| `frontend/src/lib/__tests__/r501-terminal-read-hands-back-data-keys.test.js` | 新件 244 行 | `E321AFA25728A916` |
| `frontend/src/assets/theme.css` | **0 / 0**（没新增任何色值，一行未碰） | 未变 |
| `frontend/src/components/ChatPanel.vue` | **未碰**（屏那一手见 §6） | 与基点逐字节相等 |
| `app/**`／`docs/api/contract-v1.md`／`App.vue`／`router/index.js`／`DashboardPanel.vue`／`lib/dashboard.js`／`devFixtures/**` | 未碰 | `git status` 只剩上面两枚 |

`git status --porcelain` 全文只有两行：` M frontend/src/lib/sessions.js` ＋ `?? …r501-terminal-read-hands-back-data-keys.test.js`。写域外一枚未增删、一枚未改字节。

改前三行（原地替换，行号不漂）：

```
sessions.js:482          return { action: 'terminal' }
sessions.js:484          state.terminal = state.terminal || 'failed'
sessions.js:488          state.terminal = state.terminal || 'cancelled'
```

## 3. 判据实测读数（🔴 全部为**执行层自报**，总控并树后须亲跑一遍）

- 判据①「解码处对 `data` 里除已知字段外的额外键能交回」：新件甲2 把**当场从 `app/api/v1/chat.py` 派生**的键集原样喂进真 reducer，`seen` 与 `data` 逐枚相等、值逐枚不被改写；甲3 再额外塞一枚 `r501_canary_key`，不改进前端代码也交得回（证明抄写不是白名单）。件读数 `14 passed`。
- 判据②「三态不许并脸」：新件乙组四枚——`request.started`（还在跑）不交读数且 `state.terminal` 仍是 `null`；`request.completed`/`request.failed`/`request.cancelled` 三张读数 `event` 逐枚不同名（`new Set(reads).size === 3`）且 `terminal` 各归各；失败那一张带着自己的 `error_code` 且**不交** `data_filename`；legacy `done` 帧（非 canonical）不造读数。
- 判据③「在册反向钉不许改宽」：`r415-server-data-readout.test.js` 与 `r424-terminal-data-on-the-wire.test.js` **两枚文件一行未改**（`git status` 干净），改前改后 `it(`/`expect(` 逐枚相等：r415 13/38、r424 13/35。全树对账：改前 2344 枚 `it(`／8414 枚 `expect(` → 改后 2358／8466，**LOST 枚数 = 0**，增量全部来自新件（+14 `it(`／+52 `expect(`）。丙组那枚「不许拿发依据填回显」仍原样咬人（刀③ 里它当场红）。
- 判据④「新增件名 `r501-*`」：`frontend/src/lib/__tests__/r501-terminal-read-hands-back-data-keys.test.js`，四组 14 枚。
- 前端套件：`npx vitest run` → **130 files / 2629 tests passed**（基点同树实测 129 files / 2615 passed；差值恰为本件 1 file / 14 tests）。点名件三枚同跑：`r501 14 passed`、`r424 13 passed`、`r415 13 passed`。
- 色值纪律：`npx stylelint "src/**/*.{css,vue}"` → **148 problems (0 errors, 148 warnings)**，与基点同数、仍在预算内；`frontend/package.json:13` 的 `lint:colors` 仍是 `--max-warnings=148`，一个字节没改；`r151-legacy-colors.test.js` 那枚棘轮（`LEDGER.length === 169`／`DELETED.length === 17`／`TOKENS` 54 枚）未改也仍绿。本单**零新增色值**，组件里没有裸 `rgba(`/hex，没有 `text-shadow`。
- 运行时零外部请求：`rg -n 'https://' frontend/src/lib/sessions.js <新件>` → 两枚 EXIT 1（零命中）；本单没起 dev server、没 `npm install`/`npm ci`、没删 `node_modules`（Junction 原样）、没碰 docker、没打模型、没连库写、没跑全量 pytest 门。
- 硬不变量：`rg -c classification_blocked app/` → EXIT 1（0 命中）。零新增 Chroma 依赖/写点。

## 4. 三把刀的红句原文（变异只落本工作树，跑完逐字节还原）

每把刀跑完都现验 `frontend/src/lib/sessions.js` 的 `sha256[:16] == 784651f55ffffa6b`（三次全部 `same=True`）。

**刀① 把解码处退回只抄三格的旧形**（删掉 `state.terminalRead` 那一行、恢复「第五行就是 `return`」）→ 新件 **10 枚红**（r424/r415 仍 26 枚绿，说明这一格正是过去没人咬住的那一格）：

```
AssertionError: 解码处丢掉了后端真给的键：session_id / data_filename / worker_count / elapsed / answer_length / awaiting_hitl / awaiting_steps（这一帧到了，界面一枚都没接住）: expected [ 'session_id', 'data_filename', …(5) ] to deeply equal []
AssertionError: request.completed 没交出自己那一张读数: expected undefined to be truthy
AssertionError: 帧到了却一格没给，与帧没到是两件事，这里必须能分开: expected false to be true
AssertionError: 第五行必须抄写与出口同一行：拆开就多占一行，r424 丁组那五枚坐标全挪位: expected '          return { action: 'terminal…' to contain 'state.terminalRead = { event: 'reque…'
Tests  10 failed | 30 passed (40)
```

**刀② 三态并成一格**（把 `completed` 那一张的 `event` 写成通用的 `terminal`）→ **4 枚红**：

```
AssertionError: expected 'terminal' to be 'request.completed' // Object.is equality   （甲4／乙2／丁1 各一处）
AssertionError: 第五行必须抄写与出口同一行：拆开就多占一行，r424 丁组那五枚坐标全挪位: expected '          state.terminalRead = { even…' to contain 'state.terminalRead = { event: 'reque…'
Test Files  1 failed | 2 passed (3)
Tests  4 failed | 36 passed (40)
```

**刀③ 把「后端没给」补造成空串**（`terminalDataFilename` 无则写 `''`）→ 三枚在册件同时红，证明反向钉没被放宽：

```
AssertionError: 后端没说话，state 里就不许多出这一枚键: expected true to be false            （r424 甲3）
AssertionError: 形状 null 混进了读数那一格: expected true to be false                        （r424 甲4）
AssertionError: lib 写的键名漂了：面板读不到，那一行永远不画: expected 'import { nextTick, shallowRef } from …' to contain 'state.terminalDataFilename = data.dat…'   （r424 丙2）
× r415 丙3「终态帧整格缺席 → 那一行一枚字都不画；缺席也不许写成「说不准」」
   → expected [ Array(1) ] to deeply equal []      （屏上那一格多出了一句，正是「替后端宣布说不准」）
Test Files  3 failed (3)
Tests  6 failed | 34 passed (40)
```

## 5. 后端那一格若要改：取证与提案（🔴 不由本单执行，归 `app/**` 那一手；`chat.py` 今天归 R497/Bacon 独占）

1. 请裁项（契约 `:5412-5415` 早已登记在册，本单只是复述）：legacy `done` 帧与队列终态载荷要不要也交 `data_filename`。这两处的键集被 `tests/test_r254_sync_lane_terminal.py:151`（**相等**式）与 `:175` 按名钉住，拓宽必须连那枚在册件一起改，属后端一手。
2. 若只做前端一手（不动后端）：缓存命中那一腿今天**不发** `request.completed`，所以「命中轮的用表读数」在线上就是没有。前端不许拿请求值填它（这条已有在册钉），要办只能后端在命中道补发一枚终态帧，或在 `sources`/`done` 里带上同一读数——请总控按 R504/Bacon 的写域裁。
3. 语义提醒：`data_filename` 是**响应方向**（服务端实际算了哪份），`AskRequest.data_filename` 是**请求方向**（调用方点了哪份），两枚同名不同义，契约 `:5387-5389` 已写死「不许互相冒充」。本单交回的整格读数把两枚都留在各自位置，没合并、也没新增字段名。

## 6. 没做到（明写，别读成已收）

- **屏上的脸还没长**：`session_id`/`worker_count`/`elapsed`/`answer_length` 现在只到 `state.terminalRead`（lib 交回），`ChatPanel.vue` 没动一行，屏上仍只有 `data_filename` 那一格（`server-data-readout`，三态在册）。判据里「每一枚后端真给的键都要有一张可辨识的脸」在 lib 侧成立、在屏侧**未做**——要接的是 `adoptServerDataRead` 旁边同一手法的 adopt＋一行 `<p data-testid>`，写域是 `ChatPanel.vue`，另开一手。
- `awaiting_steps` 依旧零消费点（本单只保证它进了整格读数，没替它编一句人话）。
- 信封那六枚键（`trace_id`/`task_id`/`sequence`/`timestamp`/`status`/`request_id`）不在本单交回范围内：`request_id` 另有在册一手（R174），其余五枚本单一枚没接、也没写脸。
- 「后端根本没给」那三处（legacy `done`／队列终态载荷／缓存命中道）本单零改动，只交了取证与提案；屏上那句「服务端没回这一格」的脸也还没长（同第一条）。
- 浏览器仍看不到改动：镜像未重建，本纸全部是文字凭据＋DOM/形状断言口径，没起 dev server、没跑 `npm run build`、没截图。
- 没跑全量 pytest 门（明令）；只跑了前端 `vitest` 与 `stylelint`。`docs/api/contract-v1.md` 一个字未改，§5 那段契约提案只活在本纸里。
