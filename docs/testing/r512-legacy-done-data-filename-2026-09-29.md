# R512 · G03 屏侧：legacy `done` 那一格要落到屏上（R504 欠的那半）

- 树 `C:/Users/fengx/PycharmProjects/be-r512`，基点 `60a8e01`（开工现取 `git status --porcelain` 为空，dirty=0）。执行层**未 commit／未 add／未 push／未建分支／未动容器／未打模型／未起服务**。
- 写集三枚，收工 `git status --porcelain` 恰好三行（原文见 §5⑤）：`frontend/src/lib/sessions.js`（+2 / -2，原地改）＋新件 `frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js`（23 枚钉）＋本读数件。
- `docs/api/contract-v1.md` **一字未改**（令内禁碰，另一席位占用），口径写进本件 §2。

## 1. 写集原文

### 1.1 `frontend/src/lib/sessions.js`（`git diff` 原文）

```diff
@@ -571,8 +571,8 @@ export function createStreamReducer(msg, state) {
       case 'cancelled':
         state.terminal = state.terminal || 'cancelled'
         return { action: 'cancelled' }
-      case 'done':
-        if (!state.terminal) state.terminal = 'completed'
+      case 'done': if (!state.terminal) state.terminal = 'completed'
+        if (typeof payload?.data_filename === 'string' && payload.data_filename && !state.terminalDataFilename) state.terminalDataFilename = payload.data_filename
         return { action: 'terminal' }
       case 'queued': {
```

改后那一支的三行本体（现读工作树）：

```
574:      case 'done': if (!state.terminal) state.terminal = 'completed'
575:        if (typeof payload?.data_filename === 'string' && payload.data_filename && !state.terminalDataFilename) state.terminalDataFilename = payload.data_filename
576:        return { action: 'terminal' }
```

**为什么是「原地改、一行都不许多」**：`sessions.js` 的总行数由在册件 `r424-terminal-data-on-the-wire.test.js:160` 按【工作树】钉死为 `1006`（`lib.split('\n').length - 1` toBe 1006），`r427-...test.js:386` 又按【HEAD】钉死 `:814` 必须是空行。多插一行 ⇒ 前者在本树上当场红、后者在总并树上红。令内只点了 `:128`／`:529` 两枚锚，实际拦行的是四枚（另两枚＝`:814` 空行与总行数 1006），逐枚点名见 §4 末行与 §5⑤。

### 1.2 新钉件 `frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js`（23 枚，四组）

| 组 | 枚数 | 各钉什么 |
| --- | --- | --- |
| 甲 · 三形各一枚 | 8 | 甲1 非空⇒采纳／甲2 空串⇒不补造／**甲3 空串⇒不得覆盖已有真值**／甲4 缺席⇒一个字不动／甲5 `undefined` 另立一态／甲6 非字符串五形（null 7 {} [] true）／甲7 `payload` 整枚缺席也不崩／甲8 `isCanonicalEvent('done', …)` 现读 false（这一帧确实走 legacy 道） |
| 乙 · 两条道的优先级 | 7 | 乙1 canonical 真值+legacy 空串⇒真值留／乙2 +legacy 缺席⇒真值留／乙3 +legacy 同值⇒不变／乙4 +legacy 异值⇒先到者胜／乙5 canonical 空串+legacy 非空⇒填上名字／乙6 只有 legacy⇒名字照样上屏／乙7 两枚 legacy 重放⇒第一枚赢 |
| 丙 · 真流跑到底 | 5 | 丙1 只发 legacy done 带名字⇒`result.state` 就是那一个名字且 `stopped==='done'`／丙2 canonical→done 同值⇒一枚名字／丙3 canonical 空串→done 缺席⇒键在场且值为空串／丙4 done 缺席⇒键根本不存在／丙5 接缝两边键名逐字一致（lib 写的 == 面板读的） |
| 丁 · 原地改的自证 | 3 | 丁1 行数仍 1006／丁2 六枚在册活坐标（`:128 :524 :529 :531 :625` + `:814` 空行）逐枚现读相等／丁3 `case done` 那一支仍占三行 |

## 2. 三形与优先级怎么定的（现读调用点，不看签名）

### 2.1 线上那两枚形状**不同源**，所以第二枚读法照的是口径而不是字面

| 环节 | 现读坐标（改前取证，均为调用点/构造点本体） | 读数 |
| --- | --- | --- |
| 取值 | `app/api/v1/chat.py:362-369` `terminal_data_filename` | 正好一枚交名字；零枚与多枚都交空串 |
| 落键（唯一挂载件） | `app/api/v1/chat.py:372-386`，本体在 `:384-385` `if data_filename: payload["data_filename"] = data_filename` | 空串⇒**整格不落键**；键是**平铺**在 payload 顶层 |
| legacy `done` 出口 | `app/api/v1/chat.py:2335-2344`（八键字面量）+ `:2345` 挂载并 `sse_event("done", …)` | 载荷里就是 `payload.data_filename`，没有中间那层 `data` |
| canonical 出口 | `app/api/v1/chat.py:2995-3012`（/ask）与 `:3678-3695`（/approve）的 `data={… "data_filename": terminal_data_filename(dataset_files) …}` | 键嵌在 `payload.data` 里 |
| 收端分流 | `frontend/src/lib/sessions.js:459` `if (isCanonicalEvent(event, payload))`，闸门本体 `:425-430`；legacy 白名单 `:240`/`:508`，legacy `switch` 本体 `:516` | `done` 走 legacy 道（甲8 把它钉成活判据，不靠注释） |
| canonical 采纳（在册） | `frontend/src/lib/sessions.js:474` `const data = payload?.data \|\| {}` → `:481` `typeof data.data_filename === 'string'` | 本单**一字未动** |
| legacy 采纳（本单） | `frontend/src/lib/sessions.js:575` `typeof payload?.data_filename === 'string'` | 字段名 `data_filename`、state 键名 `terminalDataFilename`、`typeof === 'string'` 三重闸门的第一重，逐字照 `:481`；只有取值路径从 `data.data_filename` 换成 `payload.data_filename`——**这是线上形状决定的，不是另起一炉** |
| 屏侧交接 | `frontend/src/components/ChatPanel.vue:698-703` `adoptServerDataRead` 读 `result?.state?.terminalDataFilename`，`typeof read !== 'string'` 就 return；调用点 `:1060`（send 腿收尾）与 `:1186`（approve 腿收尾） | 两枚调用点都在 `consumeSseStream` 返回之后**无条件**执行 ⇒ legacy 道一旦把键写进 `state`，面板那一行自己就有脸，**本单不需要碰 `ChatPanel.vue`**（它在禁碰清单上） |
| 屏侧三张脸 | `frontend/src/components/ChatPanel.vue:683-691` `serverDataOf` | `null`⇒不画／`''`⇒「这一轮说不准是哪张表…」／非空⇒「这一轮算数用的表：X」 |

### 2.2 三形（代码闸门 → state → 屏上脸 → 钉）

| 形 | 线上怎么来 | 被哪一重闸门挡／放 | `state` 结果 | 屏上 | 钉 |
| --- | --- | --- | --- | --- | --- |
| 给了非空值 | `chat.py:384-385` 落键 | 三重闸门全通过 | 写键＝那一个名字 | 「这一轮算数用的表：X」 | 甲1 乙5 乙6 乙7 丙1 丙2 |
| 给了空串 | 今天 legacy 道交不出（挂载件只在非空落键）；本单按假想形状照防 | 第二重 `payload.data_filename` 假⇒挡；第三重也挡覆盖 | 不写键；**已有非空真值原样保留** | 不画（屏上也不许冒出「说不准」） | 甲2 甲3 乙1 丙3 |
| 整格缺席 | 零枚／多枚（`terminal_data_filename` 交空串）、缓存腿 `chat.py:2656-2663` 压根不交 `dataset_files`、比树落后的镜像 | 第一重 `typeof` 假⇒挡（缺席读出 `undefined`） | 不写键，一个字都不动 | 不画 | 甲4 甲5 甲6 甲7 乙2 丙4 |

三形之间**没有并脸**：缺席与空串在两形上都表现为「不写键」，但本单把它们各钉一枚——判据用 `Object.prototype.hasOwnProperty.call(state, 'terminalDataFilename')`（甲2/甲4/甲5/甲6/甲7/丙4），`undefined` 另立一枚甲5（不经 `JSON.stringify`，因为 JSON 会把 `undefined` 洗成缺席，走 `reduceObject` 直喂对象才能单独验它）。

### 2.3 优先级：先到者胜（现读次序后定死）

流上次序的证据不是签名而是 yield 次序：`chat.py:2995` 先发 canonical `request.completed`，`chat.py:3014-3016` 的注释明写「位置在 request.completed 之后、legacy done 之前：done 仍是流结束的唯一信号」，legacy `done` 在 `:3040`（/ask）与 `:3722`（/approve）才发。所以：

- **canonical 在前，legacy `done` 是流末尾那一枚**；规矩定死为「先到者胜，后到的 legacy 只填还没人说过的那一格」。
- 「后到的 legacy 空值不得覆盖先到的 canonical 真值」由两重闸门共同保证：非空闸门让空串根本走不到赋值，先到者胜闸门（`!state.terminalDataFilename`）让**任何**后到的 legacy 值都改不了已在位的真值。乙1 是令里点名那一枚，乙2/乙3/乙4/乙7 是它的同族补强。
- 唯一一处「后到改先到」：canonical 先交**空串**（键在场，屏上「说不准」）而 legacy 后交**非空**名字 ⇒ 名字把空串填上。今天这条不可达（两枚同源，都出自同一枚 `terminal_data_filename(dataset_files)`：它交空串时挂载件根本不落键），乙5 把它钉成显式决定而不是巧合，并写明取舍理由是「非空读数优先于一句说不准」。若总控判定这条也要先到者胜，改一柄闸门即可，本件不擅自收紧。

### 2.4 令内两条互相冲突的口径怎么裁的（明写，请总控复裁）

工单既要「照 `:481` 那枚在册写法同一口径同一字段名」，又要「缺席判据用 `Object.prototype.hasOwnProperty.call(payload, 'data_filename')`」——而 `:481` 本体不带 `hasOwnProperty`。本单裁法：**写侧**照 `:481` 的 `typeof === 'string'` 口径（缺席经 `payload?.data_filename` 得 `undefined`，天然不是 string，写侧再加 `hasOwnProperty` 是死重条件，且本单为一行都不许多），**判据侧**把 `hasOwnProperty` 用在它真正吃劲的地方（区分「没这一格」与「这一格是空串」）。如果总控要求写侧也带 `hasOwnProperty`，请给一行预算或允许把带它的顶层件落在 `:814` 之后——本席不自作主张插行。

## 3. 三把反证刀（各跑一次，逐字节还原）

三把刀都只改 `sessions.js:574-575` 那一支，行数恒为 1006。还原口径：`Buffer.compare(备份, 现文件) === 0` 记 `same=True`。

| 刀 | 改法原文（替换进 `:574-575`） | 改时 sha256[:16]（字节） | 实测红 |
| --- | --- | --- | --- |
| 刀一 把那一支改回改前这形（一个字不读 payload） | `case 'done':` / `if (!state.terminal) state.terminal = 'completed'` | `784651f55ffffa6b`（46888 B；与改前工作树逐字节相同，正好自证刀一＝改前形状） | **7 枚**：甲1 乙5 乙6 乙7 丙1 丙5 丁3（`7 failed \| 16 passed (23)`，vitest exit=1） |
| 刀二 逐字照 `:481` 抄成「是字符串就采纳」（连带摘掉非空与先到者胜两枚闸门） | `if (typeof payload?.data_filename === 'string') state.terminalDataFilename = payload.data_filename` | `d938e96f6fe9df10`（46987 B） | **5 枚**：甲2 甲3 乙1 乙4 乙7（`5 failed \| 18 passed (23)`，vitest exit=1） |
| 刀三 缺席也补造成空值（无条件赋值） | `state.terminalDataFilename = typeof payload?.data_filename === 'string' ? payload.data_filename : ''` | `5ffea75aed2c7488`（46989 B） | **13 枚**：甲2 甲3 甲4 甲5 甲6 甲7 乙1 乙2 乙4 乙7 丙4 丙5 丁3（`13 failed \| 10 passed (23)`，vitest exit=1） |

红字原文（每把摘一枚代表）：

```text
刀一 · 甲1   AssertionError: expected undefined to be 'sales.xlsx' // Object.is equality
             - Expected: "sales.xlsx"
             + Received: undefined
             ❯ src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js:95:29

刀二 · 甲2   AssertionError: 空串被采纳了：屏上会凭空多出「说不准」那一句: expected true to be false // Object.is equality
             - false
             + true
             ❯ …r512-legacy-done-adopts-data-filename.test.js:96:93
刀二 · 乙1   AssertionError: expected '' to be 'sales.xlsx' // Object.is equality   ← 令里点名那一枚：后到的 legacy 空值覆盖了先到的 canonical 真值
             ❯ …r512-legacy-done-adopts-data-filename.test.js:142:29

刀三 · 甲4   AssertionError: 后端没说话，state 里就不许多出这一枚键: expected true to be false // Object.is equality
             - false
             + true
             ❯ …r512-legacy-done-adopts-data-filename.test.js:109:93
```

逐字节还原（三把各一次，全 `same=True`）：

```text
knife one    -> sha=784651f55ffffa6b  restore same=true  sha=3bf755f07d4cbdd6
knife two    -> sha=d938e96f6fe9df10  restore same=True  sha=3bf755f07d4cbdd6
knife three  -> sha=5ffea75aed2c7488  restore same=True  sha=3bf755f07d4cbdd6
```

## 4. 交总控的改口账（本单一字未碰，全是禁碰件）

| 声称位置 | 今天成假话的那半句 | 备注 |
| --- | --- | --- |
| `docs/api/contract-v1.md:5796-5797` | 「**前端解码处今天只读 canonical 那一发**：`sessions.js` 里 `done` 分支只置终止状态、不读载荷键（`:574-576`）」 | 本单正是去治它的；行号 `:574-576` 仍然对得上（原地改，未增删行），过期的只有那半句措辞。契约由另一枚 Agent 占用，请总控转该席位 |
| `frontend/src/components/ChatPanel.vue:598-599` | 「线上到屏上那一截由 R424 接上：**终态帧唯一的解码处**是 `lib/sessions.js` 里 `createStreamReducer` 的 `request.completed` 分支」 | 现在解码处有两枚（`:481` canonical 与 `:575` legacy）。禁碰件 |
| `frontend/src/lib/__tests__/r424-terminal-data-on-the-wire.test.js:96` | 用例**标题**「legacy done 帧（非 canonical）不造读数：旧后端那一格今天仍然只能「不画」」 | 用例**体**仍真：它喂的是 `{"content":""}`，压根没有那一格 ⇒ 断言照旧绿（本单 2744 全绿为凭）。只有标题那半句过期。不在本单写集 |
| `frontend/src/lib/__tests__/r501-terminal-read-hands-back-data-keys.test.js:164` | 同名标题「legacy done 帧（非 canonical）不造读数」 | **无需改口**：它钉的是 `terminalRead`（终态那四枚读数键），legacy `done` 今天仍不交那四枚，本单没碰它。列出来只为免得总控重复立案 |
| `docs/handoff/2026-09-26-v1-frontend-gap-list.md:155`（G03 行）与 `docs/handoff/2026-09-15-backend-followup-requests.md` 的 R424 条目 | 「终态帧唯一解码处 `lib/sessions.js:478-482`」 | `docs/handoff/**` 禁碰；G03 屏侧那半今天落了一半（done 帧），队列道仍欠（见 §5「没做到」1） |
| 工单本身（不属仓库件，但直接影响下一单的存活） | 「必须落在 `:529` 之下」只给了 `:128`/`:529` 两枚锚 | 实际拦行的还有 `:814` 空行（`r427:386`，按 HEAD 读，只在总并树上炸）与 **总行数 1006**（`r424:160`，按工作树读，本树就炸）。守「`:529` 之下」不够，**必须净零行** |

## 5. 判据 ①–⑥ 读数

**① 新钉枚数与三形清单**：新件 1 枚，23 枚 test（甲8／乙7／丙5／丁3）。三形各至少一枚：非空＝甲1（+乙5 乙6 丙1 丙2）、空串＝甲2（不补造）+**甲3（不得覆盖已有真值，令里点名那一枚）**+乙1（不得覆盖 canonical 真值）、缺席＝甲4（+甲5 `undefined` 独立态、甲6 非字符串五形、甲7 载荷整枚缺席、乙2 丙4）。

**② 三把刀**：见 §3。各跑一次，红 7／5／13 枚，vitest exit 均 =1；三把各还原一次，`same=True`，还原后 sha 三枚都是 `3bf755f07d4cbdd6`。

**③ 全量前端套件两次**：

| 态 | 命令 | 读数 |
| --- | --- | --- |
| 改前基点（dirty=0，`git status --porcelain` 空） | `npx vitest run` | **135 files passed (135) / 2721 tests passed (2721)**，exit=0，Duration 22.20 s |
| 改后（dirty 态，已 apply 未 commit） | `npx vitest run` | **136 files passed (136) / 2744 tests passed (2744)**，exit=0，Duration 20.67 s |
| 差值 | — | +1 file / **+23 tests ＝ 本单新增 test 枚数**，一枚不多一枚不少 |

干净树复跑本席交不出（不许 commit），见 §6 第 3 条。

**④ `npx stylelint "src/**/*.{css,vue}"`**：`148 problems (0 errors, 148 warnings)`，exit=0；`npm run lint:colors`（即 `--max-warnings=148`）同样 exit=0。本单零 CSS/`.vue` 改动，告警数与在册预算 148 持平，未越界。

**⑤ 产物 sha256[:16] 与磁盘字节口径**：sha 一律按**磁盘字节**算（`readFileSync` 不带 encoding 的 Buffer）。工作树是 CRLF（`core.autocrlf=true`，blob 存 LF），所以同一枚文件有两个口径两个 sha，下表逐枚点名，勿混比：

| 件 | 口径 | 字节 | sha256[:16] |
| --- | --- | --- | --- |
| `frontend/src/lib/sessions.js` | `git show HEAD:` 的 blob（LF，1006 行） | 45882 | `a6f206334d334eda` |
| `frontend/src/lib/sessions.js` | 改前工作树（CRLF，1006 行） | 46888 | `784651f55ffffa6b` |
| `frontend/src/lib/sessions.js` | **改后工作树（CRLF，1006 行）** | 47043 | `3bf755f07d4cbdd6` |
| `frontend/src/lib/__tests__/r512-…test.js` | 工作树（CRLF，253 行，末尾带换行） | 15573 | `790b3247139fb534` |
| 本读数件 | 工作树 | 见收工 `git status` | 自陈 sha 会自我循环，**故意不内联**，由总控现取 |

收工 `git status --porcelain` 全文（恰好三行）：

```text
 M frontend/src/lib/sessions.js
?? docs/testing/r512-legacy-done-data-filename-2026-09-29.md
?? frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js
```

**⑥ 零新增色值／零外部请求／零 Chroma／`classification_blocked`**：

- 色值：`rg -n -i "#[0-9a-f]{3,8}\b|rgb\(|hsl\(|color:|theme.css" frontend/src/lib/sessions.js frontend/src/lib/__tests__/r512-…test.js` ⇒ **EXIT=1，零命中**；`assets/theme.css` 一枚未碰。
- 外部请求：`rg -n "https?://|fetch\(|XMLHttpRequest|new WebSocket|axios"` 对新测试件 ⇒ **EXIT=1，零命中**；`sessions.js` 那两枚新增行只是属性读取。
- Chroma：`rg -n -i "chroma"` 对两枚件 ⇒ **EXIT=1，零命中**（本单不新增任何向量库依赖或写点）。
- `rg -c classification_blocked app/` ⇒ **EXIT=1，零命中**（本席没碰 `app/**`，该口径不因此单出现）。

活坐标改后真实行号（令内点名格式）：**`sessions.js:128` 改后仍为 `:128`／现为 `:128`**；**`sessions.js:529` 改后仍为 `:529`／现为 `:529`**。两枚都未漂移，所以 `r427` 头部注释、`r197-turn-key-inheritance.test.js:293`、`tests/test_r210_break_replaces_the_screen.py:6` 三处声称的数字**一枚都不需要改**（本席也未碰这三枚件）。同族另外五枚一并现取为证：`:209` `controller = new AbortController()`、`:219` `export function abortStream()`、`:524` `} else if (state.segments.includes(chunk)) {`、`:531` `        }`、`:625` `  if (!response.ok) {`、`:814` 仍是空行、总行数仍 1006。

## 6. 没做到（明写）

1. **队列终态那一格屏侧仍没有读者**：后端 `chat.py:2282-2296` 已经把 `data_filename` 挂进队列终态载荷，但屏侧读它的那两枚件（`components/ChatPanel.vue` 的排队脸、`lib/provenance.js`）都在禁碰清单，本单写域只到 `done` 帧。G03 屏侧今天落了一半。
2. **缓存命中那一腿屏上仍不说**：`chat.py:2656-2663` 的 `done_frame_for_turn(...)` 压根不交 `dataset_files` ⇒ 那一帧 `data_filename` 整格缺席 ⇒ 屏上照旧「不画」。这是 R504 明写未治的账（缓存条目当年没落 dataset 读数），本单不越界，也没在测试标题里替它画成「已上屏」。
3. **并树验收只交了一遍**：AGENTS.md 要求 dirty 态与 `git commit` 后的干净树各跑一遍同名件；本席禁止 commit ⇒ 只交出 dirty 态那一遍（136/2744/exit=0）与改前基点那一遍（135/2721/exit=0）。**请总控并树后在干净树复跑 `r512`＋`r424`＋`r427`＋`r501`＋`r415`＋`r510` 六件**（本席已在 dirty 态跑过后五件：86 passed）。
4. `docs/api/contract-v1.md` 一字未改（令内），本单口径只写进本件。
5. 写侧没带 `Object.prototype.hasOwnProperty`，理由与复裁入口见 §2.4。
6. **真机端到端没跑**（真后端 + 真浏览器把那一行画上屏）：令内禁止起服务／动容器／打模型，本单判据全在单测与源码坐标层。`adoptServerDataRead` 那两枚调用点（`:1060`/`:1186`）是现读来的，不是跑出来的。
7. 未 commit／未 push／未建分支；主树 `C:/Users/fengx/PycharmProjects/企业智脑` 一行未写（本树 `frontend/node_modules` 是从主树**只读复制**得来，`node_modules/` 在册忽略项，不进 `git status`）。
