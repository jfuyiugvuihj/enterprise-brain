# R558 交工纸 —— 队列道的逐字片段接上既有轮询面（甲案投递面）

立案与判据出处：跟进单 §142「R558｜甲案投递面半张」（七格）。基点：主树 `be11e51`。
码体由总控线亲手写在其独占工作树 `C:\Users\fengx\PycharmProjects\be-r558`（detached at `be11e51`），
经 `scripts/r531_worktree_merge.py --tree be-r558 --apply <逐枚点名路径>` 落主树，rc=0。
🔴 本单无执行层参与 ⇒ 纸上不出现「执行层自报」这一类数字，全部读数均为总控亲跑。
钟点：`Get-Date` 现取（2026-10-01 17:4x）。

## 0. 一句话

`deploy/queue_worker.py` 里那本只进 worker 进程内存的片段账本（R548 留下的半张），今天从客户端每 3 s
就在读的 `GET /api/v1/queue/status/{request_id}` 上读出**递增增量**。零新路由、零新稳定码、零新状态词，
终态帧／`usage`／`sources`／审计行／答案键一字节未变。

## 1. 逐文件行数与行尾形态（实测）

| 文件 | 增/删 | 磁盘行尾 |
| --- | --- | --- |
| `app/api/v1/chat.py` | +24 / -0 | 全 CRLF（5310 行） |
| `app/common/reliable_queue.py` | +116 / -0 | 全 CRLF（829 行） |
| `deploy/queue_worker.py` | +121 / -5 | 全 CRLF（1201 行） |
| `docs/api/contract-v1.md` | +48 / -0（纯尾追加） | 全 CRLF（5979 行） |
| `frontend/src/components/ChatPanel.vue` | +41 / -2 | 全 CRLF（3176 行） |
| `frontend/src/components/DocPanel.vue` | +1 / -1（陈旧坐标改口，见 §6） | 全 CRLF（1681 行） |
| `tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py` | 新，619 行 | 源 LF → 主树检出 CRLF，blob 仍 LF |
| `tests/fixtures/r558_refutation_driver.py` | 新，344 行 | 同上 |
| `frontend/src/components/__tests__/r558-queue-piece-draft.test.js` | 新，59 行 | 同上 |
| `frontend/src/lib/sessions.js` | **净零行** | `git diff --stat` 空、`git diff --quiet` rc=0 |

## 2. 七格判据逐格对账

### 判据① 端到端真读数（不许「到终态才一次给全」）
- `test_the_polling_body_grows_while_the_turn_is_still_running`：真跑一轮报告档后台执行
  （`deploy.queue_worker.process_one()`，沿用在册夹具 `tests/test_r37_report_lane_worker.py::_install_worker`），
  片由**在册真 merger** `tests/test_r548_...::_merger_pieces` 切，本件不发明片；探针插在**发的中间**，
  每发打一次真门 `GET /api/v1/queue/status/{id}`（`TestClient(fastapi_app)`，HTTP 200，断言读的是 `response.json()`）。
  逐格断言：探针 ≥3 发／每发 `status=="processing"`／`state=="ok"`／`chars` 单调不减且 ≥3 个不同值／
  **首发 `chars>0`**（这一手专门挡「终态一次给全」）／`cursor` 与 `chars` 同涨同停／末发 `text` 非空。
- `test_the_deltas_concatenate_to_every_published_character`：按游标逐发读，拼起来 == 已发布全篇的前缀；
  再把片段表原始批次拼起来 == 全篇，一字不许多不许少。
- 🔴 诚实边界：这一格交的是**同进程真路由真载荷**（FakeRedis + 真 `ReliableQueue` + 真 worker 码体 + 真 HTTP 门），
  不是容器里的真 Redis。容器内一次 `REPORT_LANE_VIA_QUEUE=on` 的真机读数**仍欠**，已排进下一次开窗
  （一题报告档，成本 <2 分钟）；当前本机被外来 CUDA 训练作业 `train.py`（PID 15344，GPU 93%）压住，时延窗开不了。

### 判据② 零新路由／零新稳定码／逐键有名有姓
- `test_no_second_queue_route_and_no_new_status_word`：路由面从 `fastapi_app.openapi()["paths"]` 取——
  🔴 不能用 `app.routes`，它在 import 期只有 18 枚且不含 `/queue`，会把「有门」读成假零。断言队列族路由集合
  与本单之前逐字相等，状态词表零增加。
- `test_the_contract_names_every_key_the_readout_answers`：读数里出现的每个键必须在契约里有名有姓。
  `docs/api/contract-v1.md` 尾追加一节 “Queue lane streaming pieces (`R558`)”（`+48 / -0`，`git diff --numstat` 无删行），
  逐键写齐「形状／缺席语义／可否为空」三件：`since`（不可解析、负数、超出末序号一律当 0，**永不 4xx、不新造稳定码**）；
  `stream_pieces` 只在 `processing` 下发（`queued`／`awaiting_approval`／`done` 一律**整键缺席**，不是 `null` 不是 `{}`）；
  内部 `state`(`absent`/`ok`/`unreadable`)／`text`／`cursor`／`pieces`／`chars`／`discarded`／`truncated`／`legs`／`reason`。

### 判据③ 每轮一条答案流不倒退
五枚在册钉全部复跑点名（读数见 §5）：`tests/test_r464_one_terminal_answer_stream_per_round.py`／
`tests/test_r203_sink_reaches_the_leg.py`／`tests/test_r524_sink_reaches_both_runways.py`／
`tests/test_r524_queue_lane_sends_no_second_character.py`／`tests/test_r548_queue_lane_registers_the_piece_sink.py`。
本件另加两枚旁证：`test_the_terminal_readout_still_carries_no_piece_keys`（终态载荷不许长出 `stream_pieces`）、
`test_a_queued_turn_answers_nothing_about_pieces`（`queued` 那一格也不发）。

### 判据④ 上限诚实
- 账本上限 512（`QUEUE_PIECE_LEDGER_LIMIT`）超出**只计数不留片**：`test_the_ledger_cap_reports_truncation_not_silence`
  要求读数里 `discarded` 非零、明写丢弃数，不许静默、不许被读成「没有片段」。
- 存储上限 1024（`PIECE_BATCH_LIMIT`）与账本上限是两个不同的数：`test_the_store_cap_is_a_separate_number_from_the_ledger_cap`
  （`discarded` 不扣客户端一个字，`truncated` 扣掉的字只能从终态答案里拿回来）。
- 上限语义今天定死并写进契约：写满之后每发仍推「正文为空、账面数照滚」的批（`truncated` 继续递增），
  **不是「报一次就闭嘴」**；代价是有界行数，随 `result_ttl` 一起过期。

### 判据⑤ 屏上要有脸 + 零新增裸色值 + `sessions.js` 净零行
- `frontend/src/components/ChatPanel.vue` `+41/-2`：轮询把上一发的 `cursor` 原样填回 `since`，把回读的 `text`
  追加到正在长的那一截（`r558-queue-piece-draft.test.js` 钉这条读者面）；零新组件。
- stylelint 实际数字（`npx stylelint "src/**/*.{css,vue}"`，纳入 **51** 枚文件）：**148 problems（0 errors / 148 warnings）**，rc=0；
  `npm run lint:colors`（`--max-warnings=148`）同值 ⇒ 预算一格没动。逐文件：ChatPanel 139／DataPanel 4／DocPanel 3／App.vue 1／ApprovalPanel 1 = 148。
  对 HEAD 版同一把尺复量（临时副本，跑完即删）：ChatPanel **139**、DocPanel **3** ⇒ 本单**零新增裸色值**，差值 0。
- 🔴 顺手记一刀给后人：`npx stylelint "src/**/*.css"` 在本机**匹配 0 枚文件、rc=0、看着像绿**
  （`src/assets/theme.css` 在 `ignoreFiles` 里，其余 `ui/*.css` 恰好零告警）。量色值只准用仓库自己那条 `{css,vue}`。
- `frontend/src/lib/sessions.js` 前后逐字节全等 ⇒ 按行号取档的 `test_r427_*`、`test_r424_*:160` 两处锚点不会歪。

### 判据⑥ 反证刀 ≥5 把、victim 含在册钉、其中一把专打「一次性全量回填」
驱动器 `tests/fixtures/r558_refutation_driver.py`（六把，影子副本道；🔴 必须在工作树里跑，`SOURCE_TREE/.git` 必须是文件，
不许在主树跑——那会去镜像整棵对象库）。`MIRROR_DIRS` 除码体外**还须镜像 `docs/api` 与 `docs/testing`**：
不镜像 `docs/testing` 会让 R524／R548 那四枚「纸上判定词与树上同判」的钉在干净副本里假红。日志 `%TEMP:\r558\driver_run2.log`。
- 干净副本基线：**45 passed**。
- 刀1 `backfill`（把片段增量做成终态一次性全量回填）⇒ **1 红**，victim 正是 `test_the_polling_body_grows_while_the_turn_is_still_running`
  ⇒ 「递增」这个词有牙，不是散文。
- 刀2 `drop_tail`（摘掉收窗那一发）⇒ 2 红。刀3 `silent_discarded`（丢弃改静默）⇒ 2 红。刀4 `silent_store_cap`（存储上限静默吞）⇒ 1 红。
- 刀5 `terminal_leak`（把片段漏进终态帧）⇒ 3 红。
- 刀6 `unregister_sink`（撤掉队列道的 sink 注册）⇒ **13 红**，victim 含两枚**在册钉**：
  `tests/test_r548_queue_lane_registers_the_piece_sink.py::test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call`、
  `tests/test_r524_sink_reaches_both_runways.py::test_the_real_hook_for_the_queue_lane_is_now_registered__r548`。
- 收尾：6 枚 `RESTORED=True`；**真树写口记账 0 枚**（驱动器对每一次指向 `SOURCE_TREE` 的写口逐枚算账）。
- 盘内常驻另有 3 把 `test_counter_evidence_*`（parametrize），与驱动器不重复。

### 判据⑦ 两态数字
见 §5。dirty 态已交；干净树复跑数字随下一笔提交补进本节（两遍的文件清单逐枚点名，含行尾形态）。

## 3. 施工期抓到的四处真缺陷（均为总控亲跑抓到，不是执行层自述）

1. `deploy/queue_worker.py::flush()` **正常路径从不 `_pending.clear()`** ⇒ 每次汇流把已经交过的字再交一遍，
   这是当时 9 枚红的共同根因。改为「成功才清、失败不回填」（同序号重交由存储侧按批次序号去重兜住），
   并删掉 `return` 之后的死代码与vestigial `_cap_reported`。这条错形状只有「按游标拼接 == 全篇」那一枚钉能抓，
   所以那一枚不是装饰。
2. `app/common/reliable_queue.py` 的常量块被锚点工具**重复插入了 3 遍**、`_pieces_key` 重复定义 3 次 ⇒ 已去重。
   任何后续用锚点改这枚文件的单，动手前先数一遍重复块。
3. TTL 那一手在无 Redis 的测试面上会炸：`tests/test_reliable_queue.py::FakeRedis` **根本没有 `expire`**
   （它只有 `__init__ get set delete exists rpush brpoplpush rpoplpush lrem lrange`）。无条件打
   `self.redis.expire(...)` 会在每次汇流抛 AttributeError 并被记成一条告警——
   **R548 那枚在册钉「日志面逐字相等」正是这样把它抓红的**（好牙）。现在改成
   `getattr(self.redis, "expire", None)` 问着打；TTL 真在位仍由
   `test_the_incremental_store_expires_with_the_result_ttl` 盯着，不许因为夹具缺手就把 TTL 删掉。
4. `piece_readout` 在 `since > 最大序号` 时回落到 0（整段重讲），而不是给出一个永久为空的 `text`——
   空 `text` 会把屏冻在谁也推不动的游标上。契约同口径改口（见 §2 判据② 那一行）。
   另：量具自己两处错也已修——`test_this_file_adds_no_skip_and_no_xfail` 的 banned 字面量原来自指（改为拼接），
   重试那一枚原来复用同一 `request_id` 导致台账行数 3≠1（另起 `r558-retry-ledger` 键）。

## 4. 顺手抓到的一枚陈旧红（不是本单造成，本单也没躲它）

`frontend/src/components/DocPanel.vue` 的注释写着 `classification: int = Form(1)（app/api/v1/chat.py:4470）`，
而**HEAD 现取该行在第 4506 行**（先前若干笔后端并树把 4470 之前推进了 36 行），在册钉
`frontend/src/components/__tests__/r538-hand-copied-coordinates.test.js` 要求注释里的行号与树上真相一致
⇒ **这枚钉今天本来就红，与本单无关**。本席抓出来并把注释改口为 `:4506`（`+1/-1`，保持钉要求的形状）。
🔴 这类「注释里手抄的行号」每并一次树就烂一次：`R400`（`69e0035`）已把三处坐标改成运行时派生，这是第四处，还照旧手抄。

## 5. 两态数字

**dirty 态**（已 apply 未 commit，主树 `C:\Users\fengx\PycharmProjects\企业智脑`，HEAD 仍 `be11e51`）：
`153 passed / 0 failed / 68 warnings in 60.45 s`，rc=0。
尺子：主树 `.\.venv\Scripts\python.exe -X utf8`，`-p no:cacheprovider --basetemp=...`，`OMP_NUM_THREADS=1`。
文件清单（9 枚，逐枚点名，磁盘全 CRLF）：
`tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py`、
`tests/test_r548_queue_lane_registers_the_piece_sink.py`、
`tests/test_r524_sink_reaches_both_runways.py`、
`tests/test_r524_queue_lane_sends_no_second_character.py`、
`tests/test_r203_sink_reaches_the_leg.py`、
`tests/test_r464_one_terminal_answer_stream_per_round.py`、
`tests/test_r254_queue_terminal_honesty.py`、
`tests/test_r37_report_lane_worker.py`、
`tests/test_reliable_queue.py`。
同一族在 `be-r558` 上先跑过一遍：`153 passed`（23.02 s）。
前端 dirty：`npx vitest run` ⇒ **147 files / 2950 tests 全绿**，rc=0。

**干净树第一遍**（R558 已 commit 为 `5477645`，除 `chroma_db/chroma.sqlite3` 这枚按规矩永不提交的数据件外无内容差）：`153 passed / 68 warnings in 59.97 s`，rc=0，文件清单与上面那九枚逐枚相同（全 CRLF）。⇒ **两态数字对平**：dirty 153／clean 153，耗时 60.45 s 对 59.97 s，没有「并树即自毁」的钉。

**前端两态**：dirty（R558 apply 未 commit）与第二遍之间夹了一枚真红，见 §4b——改口之后`npx vitest run` ⇒ **147 files / 2950 tests passed**，rc=0（9.97 s）。干净树第二遍（`b10a7d0`，本单全部改动已 commit、除 `chroma_db/chroma.sqlite3` 外无内容差）：`npx vitest run` ⇒ **147 files / 2950 tests passed**，rc=0（11.4 s，17:53 现取）⇒ **前端两态也对平**。

## 4b. 干净树第二遍抓到的那一枚红——是本单造成的，不是陈旧的（与 §4 那枚要分开记）

`npx vitest run` 在 R558 并树后的干净树上报 **1 failed / 2949 passed**：
`src/components/__tests__/r427-borrowed-name-and-live-coordinates.test.js` 戊组
`r293:46 声称 :1518 的 queueFace(msg.queue)`。

- **根因是本单**：`ChatPanel.vue` 那一发 `+41/-2` 里，第一处改动是在第 1229 行**插了一行**
  （`const queueReads = ref({})` 那格的注释），于是它下面所有行号整体 +1。r293 的注释手抄着
  `ChatPanel.vue:1509 那条守卫`／`:1517 就把落盘那一格…交给 queueFace`，而 r427 戊组是**现读 `git show HEAD:` 推导**再比对，
  推导值今天变成 1510／1518 ⇒ 声称 ≠ 推导 ⇒ 红。
- **HEAD 现取真值**（`git show HEAD:frontend/src/components/ChatPanel.vue`，逐行点名）：
  `1510|   } else if (read && !QUEUE_SETTLED.includes(read.status)`、
  `1513|   } else if (!read) {`、`1518|     face = msg.queue ? queueFace(msg.queue) : null`。
- **改口**：`src/components/__tests__/r293-cancel-requested-persist.test.js` 两处 `:1509→:1510`、`:1517→:1518`
  （第 6 行与第 46 行各一处；替换前后都数过 `count==1`，并断言件里不再残留 `:1509`/`:1517`）。
  🔴 本单没碰任何断言，只改注释里的坐标——这一类改口一律成对交两态，不许借改口放宽钉。
- **为什么这一枚比 §4 那枚更值得写**：§4 那枚是别人欠的旧账，这一枚是**本席自己刚推进的行号**。
  两道钉（r538 手抄坐标 / r427 戊组）今天各自抓到一次，指向同一件事：`ChatPanel.vue` 与 `chat.py` 里
  「被注释手抄的行号」是每并一次树就烂一次的活雷。`R400`（`69e0035`）已把后端三处改成运行时派生，
  前端今天已有 r427 那种「现读 HEAD 推导」的治法——**剩下的手抄处数应当排一枚单收干净**，别一单一单地撞。
- **改口之后**：`npx vitest run` ⇒ 147 files / 2950 tests 全绿（rc=0，见上面前端两态那一行）。

## 5b. 全量门抓到的 13 枚连带红（全是 R558 并树的账，总控代修，逐枚归因）

门跑在 `518314c`（`-n 6 --dist loadfile`，`700.6 s`，`13 failed / 9695 passed / 52 skipped / 2 xfailed`）。
🔴 13 枚红**没有一枚是投递面本身写错了**，全是「别的在册量具把 R558 的行号／字节／尾追加形状当成了自己的判据」：

| 族 | 枚数 | 真因 | 治法（走工具与在册先例给的那条路，不手算） |
|---|---|---|---|
| `test_r455_gapdoc_coordinates_are_derived` ＋ `test_r455_hand_fudged_numbers_and_wrong_layers_both_redden` | 6 | R558 在 `app/api/v1/chat.py` 净插 `+24` 行 ⇒ 缺口单 G06 那一格印的 `chat.py:5248` 漂到 **5272** | 跑钉自己点名的 `python scripts/r455_gapdoc_coordinates.py --emit-doc-cells` 取现读值重落地（`upload_form=4506／queue_cancel=5272／sessions_route=4008`），复跑 `--check` **rc=0**、行内引用等值 **5/5** |
| `test_r453_nested_pytest_selection_guard` | 2 | 本单新驱动件 `run_pytest()` 的目标来自 spread 而**没有空选择拒绝** ⇒ 空参数会回落成全量收集 | 补 `if not targets: raise AssertionError(…)`；补完「现场病灶 == 名册」重新相等，本件不再进 `UNGUARDED_DEBT` |
| `test_r449_nested_pytest_basetemp_contract` | 2 | 同一枚驱动件的嵌套会话助手没按在册形状命名（`_nested_basetemp` ≠ `r449_nested_basetemp`），且新起的嵌套点没进名册 | 改名 `r449_nested_basetemp(parent_scratch)` ＋ 在 `ROSTER` 登记 `"tests/fixtures/r558_refutation_driver.py": (("shadow",), 1)`；登记后**重跑整台驱动器**：干净副本 45 passed、六把刀逐枚咬红、6 枚 `RESTORED=True`、真树写口记账 0 枚 |
| `test_r548_counter_evidence_teeth::test_z9c` | 1 | R548 交工纸钉着 `deploy/queue_worker.py` 的进门指纹，而 R558 给那枚件 `+121/-5` ⇒ 纸一个数、盘另一个数 | 按钉的口径在 §7.1 台账**补一行 10-01 现读** `905d3a58b6a15aec…`；历史那行 `03be6d53…` 原样留着不追改 |
| `test_r523_cached_count_lands` | 2 | 🔴 **这一族是全仓的形状缺陷，不是 R558 的错**：该件同时要求「HEAD 那版必须是新版的前缀」（`contract_is_pure_append`）与「本节必须是最后一节」（`rindex`）。两枚合起来等于宣布 append-only 的跨栈契约**从此不许再有第二枚 `## ` 尾追加**，与总控 §142 裁定①「契约只许尾追加」直接对冲——任何下一单都会撞 | 按同族在册先例改口（`tests/test_r397_read_legs_refuse_a_missing_table.py:571`，09-28 总控对同一枚病的原话：「把『我是最后一节』换成『我的前身是谁』」）：本节之后只许出现**更晚立案**的节，也不许多出不报工单号的节；取节改为在下一枚 `## ` 前收口。合成刀由两把增到四把（中途改写红／更晚尾追加**不许**红且不被并进本段／更早的节被挪到后面红／尾追加不报号红） |

改口之后同一把尺复跑：**66 passed／16.49 s**（`test_r523`＋`test_r453`＋`test_r449`＋`test_r455` 两枚）与
**170 passed／60.35 s**（`test_r548_counter_evidence_teeth` ＋ R558 那九枚同族），两批 rc=0。
🔴 这 13 枚记在 R558 名下，不记在量具名下：本席并树前只复跑了同名九件与前端，**没有把「行号／字节／尾追加」这三族在册闸扫一遍**。
下次并 `chat.py` 这种大件，门前的靶子应当是「凡引用过 `chat.py`/`queue_worker.py` 坐标或指纹的量具清单」，不是本单的同名件——这一条已写进派工纪律。

## 6. 不翻绿的话（一条都不许替它翻）

- **A② 流式逐字无缺：不翻绿**。run11c 读数 `criterion_two_holds` 88/105、缺字 4 枚（`chart-01/02/04`、`insight-07`）、
  `uncorrected_breaks>0` 13 枚。本单动的是**队列道**的增量投递面，与 SSE 同步道是两码事，不许混着认领。
- **D 门（报告档 100% 可查回）：仍不翻绿**。run11c 相 2 的 `sources_present` 只有 8/12（`report-03/06/08` ev=0）。
- 判据① 的容器＋真 Redis 读数欠（见上）。
- 那 4 枚 `approval_failed` 原文逐枚相同——`approve 200 仍无终答：artifact owner must have a department scope`
  （HTTP 全 200、`approved` 真、rounds 1）⇒ 它是计划书 §13 **格③／业主侧 A1（`users.department` 全空）**的真机读数，
  **不是投递面缺陷**，本单不冒充治了它。