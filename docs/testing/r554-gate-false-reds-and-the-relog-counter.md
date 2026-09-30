# R554 · 全量门里那 15 枚假红，与最后 1 枚真红的牙（09-30 夜·总控亲修）

## 1. 病

同一条链上两枚门连红 25 枚、21 枚。本班逐枚单跑之后拆成两族：

- **6 枚真红**：同一根因 —— `7c798e4`（R535）在 `app/agents/contracts.py` 上方新插一枚 import 行，
  把 §1 表里那枚锚顶下一行（38 → 39）。血缘纸 `docs/perf/r387-label-lineage-2026-09-27.md` §8.7
  那句「未漂移的引用逐枚现读」因此不再是派生值。治法＝按 `test_r490_live_reads_match_derived` 的
  成对叙述口径把那一枚写成「旧 `:38`／派生今值 `:39`」——今值取自 `resolve_site` 现场交回，正文不手取。
- **15 枚假红**：全是内存／提交电荷争用，不是产品外溢。同一枚门日志现取凭据：`MemoryError` 19 次、
  `OSError [WinError 1455]`（页面文件太小）2 次、`OpenBLAS error: Memory allocation still failed
  after 10 retries` 3 次；红面全落在「起子进程／冷导入／读整本大纸」那一族件上。
  反证：同一批 22 枚在安静机上单跑，只红那 6 枚，其余 16 枚全过。

## 2. 🔴 一枚差点被写进假账的红

`tests/test_r408_docs_say_what_the_tree_does.py` 在门里报「R337 现查零提交（`git log --all --grep=R337`
空读数），第 37 行没写「零提交」」。照它改，就等于把
`docs/handoff/2026-09-26-v2-wave3-dispatch-plan.md`／`…wave4…` 里 R337 的并树账改成零提交。主树现取：
同一枚 grep **6 枚命中**，`aefa3ce` 是 commit 且在 HEAD 祖先里。⇒ 那个「空读数」是 git 子进程在内存
饿死时起不来（同 §1 第二族），不是树里没提交。

**立规矩**：量具报「查无」之前，先证明它自己起得来。`AGENTS.md` 那句「报某物不存在前先确认自己在
哪一层查」今天多一个失败形状——层是对的，工具没跑起来。

## 3. 最后 1 枚真红＝钉自己不干净（本单治它）

`tests/test_r548_queue_lane_registers_the_piece_sink.py::test_the_published_readings_do_not_move_when_pieces_flow`
在 gate4／gate5／gate6 三门连红，形状固定：比较面多出一行
`[Trace] trace_local_fallback: ... occurrences=100 ...`，而那一行的主语是**别的 request_id**。

根因：`app/trace/durability.py` 的 `note_local_fallback()` 在 `count == 1` 与 `count % _RELOG_EVERY == 0`
各吐一行 WARNING，而那枚 `count` 是**进程全局**。同一枚 xdist worker 里前头的件把它推过边界，本单那句
「日志面逐字相等」就凭空多一行。R548 交付时只备了「一次性告警靠 warm-up 轮榨干」那一手，没覆盖
「每 N 枚重登」这一手——所以它在自己那枚 worker 的第一枚进程里绿、在满门的第 100 枚边界上红。

治法（不放宽判据）：`_run_round()` 每轮之前 `durability.reset_durability_ledger()`。这本是
r250／r257／r263／r272 那一族在册件的既有纪律（前后各括一次归零），R548 漏了。比较面一字不动：
两族日志仍然逐字比，只是不再把别人的计数器当成自己的读数。

## 4. 牙（摘掉修复必红）

- `test_teeth_the_ledger_reset_is_what_keeps_the_relog_out`：先把进程计数顶到边界前一格
  （`_RELOG_EVERY` 现读自 durability，不抄 50），不归零跑一轮 ⇒ 窗口里必出现 `occurrences >= interval`
  那一行；归零跑同一轮 ⇒ 那行不许出现。两跑的本片流枚数必须相等（证明摘掉的只是噪声）。
- `test_teeth_the_ledger_reset_leaves_the_round_ledger_alone`：归零只归那枚计数器，账（枚数／字数／
  终态／历史）一格不许跟着动——防的是有人拿「归零」把读数一起洗掉。

## 5. 读数（全部总控主树亲跑，执行层零参与）

| 跑法 | 结果 |
|---|---|
| 安静机＋线程上限（`OMP`／`OPENBLAS`／`MKL`／`NUMEXPR`＝1），`run_gate.py -n 4` | **1 failed / 9638 passed / 57 skipped / 1 xfailed / 432.84 s（门 441.1 s）**，内存族三样计数全 **0** |
| 治完之后本件单跑 `-o addopts=` | **18 passed / exit=0** |
| 邻件族合跑（r524×3／r548×2／r203／r37／r464／approval_stream／r250／r257，dirty 态） | **143 passed / 1 skipped / exit=0 / 55.18 s** |
| 血缘三件（r490／r492／r493）单跑 | **30 passed / exit=0** |

🔴 **未做的对照**：安静机与线程上限是**两个变量同时改**，没做单变量 A/B ⇒ 只能报「这两样之中（或共同）」
消灭了内存族，不许写成「线程上限治好了它」。上限是否写进 `scripts/run_gate.py` 另立单：要落它，
得在真实争用形状（门与执行层自验同跑）下取数，而那条恰好是本板明令避免的撞机形状。

## 6. 数门口径（沿用上一节，别改回去）

`-m pytest` 的枚数 **除以 2** 才是门的枚数：`.venv` 每起一枚就长出一枚同名 `anaconda3\python.exe` 子进程。
窗口时间闸一律写「门 exit 之前」，不写死分钟。

