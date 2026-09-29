# R504 · G03 后端那半格：legacy `done` 与队列终态都要交得出「这一轮用的哪份数据文件」（`app/api/v1/chat.py`，2026-09-29）

工作树 `be-r497`，基点 `405cacb`（本席复位后 dirty=0 起工）。主树 `企业智脑` 一行未碰。
执行时间：2026-09-29。所有行号一律 `rg -n` 现取；改前基线只从 `git show 405cacb:<path>` 取，
🔴 没有拿 `git show HEAD:` 的内容当「改前」（HEAD 恰为 `405cacb`，取法仍按本单口径点名）。

## 1. 开工第一步（派工词点名的那本账，先看判定行再看它自己的改口节）

| 现读点 | 坐标 | 读到什么 |
| --- | --- | --- |
| G03 判定行 | `docs/handoff/2026-09-26-v1-frontend-gap-list.md:155` | 🟡 半。界面那一半已收；「服务端那一半今天两格都欠」：① `rg -n terminal_data_filename app`；② `lib/sessions.js` 的解码处只抄两枚键 |
| §7.3 排法表 | 同文件 `:251` | 第 3 位＝块 D 的 D1 半（G04 + G03），明写「G03 仍半，缺的两格今天写明在后端终态帧与 `lib/sessions.js:478-482`，不在界面」 |
| §7 顺序表（另一版） | 同文件 `:259` | 同一条，理由栏写「data_filename 上行已有、只差回显」——🔴 这一句与 `:251` 不同源，`:155` 与 `:251` 才是今天的口径 |
| §10.1 现读三态 | 同文件 `:304` | 半 2 枚：G03（缺的两格在后端终态帧 + 解码处） |
| §10.4 两本账对不上 | 同文件 `:337` | G03/T10 三本账都说「半」但缺的不是同一格；照 R265 派会去补一件已补好的东西 |
| R501 取证原文 | `docs/testing/r501-terminal-frame-no-dropped-keys.md` §5（`:127` 起）＋ §1.4 | 三处「后端根本没给」：legacy `done`、队列终态、缓存命中腿整枚不发 `request.completed`；§5.1 把前两枚列为请裁项，理由是键集被 `tests/test_r254_sync_lane_terminal.py:151`（相等式）与 `:175` 按名钉住 |

`rg -n terminal_data_filename app` 今天现取（改前基线，`git show 405cacb`）：只在 `app/api/v1/chat.py` 里
3 处——`362 def terminal_data_filename`、`2975`（`/ask` 的 `request.completed`）、`3656`（`/approve` 的同名出口）。
⇒ 派工词里说的三条欠账成立，且 G03 判定行的 ① 那一格（R414 未并）已不再是欠账。

## 2. 本单动了什么（键与形状）

三枚终态构造点各收一枚 `dataset_files`（同一枚在册收集器的 sink），取值一律出自在册那枚函数：

| 出口 | 现取坐标（改后） | `data_filename` 的形状 |
| --- | --- | --- |
| `terminal_data_filename`（在册，未动） | `app/api/v1/chat.py:362` | 正好一枚才交名字；零枚与两枚及以上一律交空串 |
| `attach_terminal_data_filename`（本单新增的唯一挂载件） | `app/api/v1/chat.py:372`，落键 `:385` | 空串 ⇒ **整格缺席**；非空 ⇒ `payload["data_filename"]` |
| legacy `done` 唯一构造点 | `:2313 def done_sse_frame`，`:2345 return sse_event("done", attach_...)` | 同上（第八格） |
| 三条出口共用的 done 帧 | `:2348 def done_frame_for_turn`，`:2381` 转发 | 同上 |
| 队列终态唯一构造点 | `:2259 def build_queue_terminal`，参数 `:2269`，`:2296 return attach_...` | 同上 |
| `/queue/status` 的终态投影 | `queue_terminal_readout`，`:5031 readout["data_filename"]` | 载荷里有才照说；没有 ⇒ 读数里也不出现（「照载荷说，一格都不添」原口径不变） |

`dataset_files` 实交点（六枚 done 出口逐枚点名，行号现取）：

| 出口 | 坐标 | 交不交 |
| --- | --- | --- |
| 入队回执那一发 `done`（本轮一个模型都没打） | `:2452` | 🔴 不交（真没产出 ⇒ 缺席） |
| 答案缓存命中那一发 | `:2656` | 🔴 不交（腿 3，本单未治，见 §5） |
| `/ask` 无正文失败腿 | `:2942`＋`:2947` | 交（那一轮确实算过那份文件，「没结论」≠「没跑数据」） |
| `/ask` 正文道 | `:3040`＋`:3046` | 交 |
| `/approve` 无正文失败腿 | `:3650`＋`:3655` | 交 |
| `/approve` 续跑道 | `:3722`＋`:3728` | 交 |

收集器与 sink 的既有两枚写点未动：`:2791`（`/ask`）、`:3509`（`/approve`）；
`_collect_dataset_filenames(agent_results, dataset_files)` 仍只出现两枚（`:3091`、`:3778`，AST 面由本单新钉复点）。

形状表（读的人要区分的是这三张脸，不许并）：

| 这一轮实际算了 | legacy `done` / 队列终态 | canonical `request.completed` |
| --- | --- | --- |
| 正好一枚 | `data_filename` = 那枚文件名 | 同值 |
| 零枚 | 键不出现 | 键在位，值 `""` |
| 两枚及以上 | 键不出现 | 键在位，值 `""` |

## 3. 改动清单（numstat 与磁盘字节 sha256[:16]）

| 文件 | numstat ±（删除数） | sha256[:16] | 字节 |
| --- | --- | --- | --- |
| `app/api/v1/chat.py` | 53 / 14 | `EEE05C4BFAD37DE5` | 262229 |
| `tests/test_r504_terminal_frames_carry_data_filename.py` | 新件（未纳入 index，numstat 无行） | `5E40C764064E3415` | 22429 |
| `docs/api/contract-v1.md` | 45 / **0**（纯字节尾追加；追加前 `rg -c "## R504"` → EXIT 1，追加后命中 1） | `2EB2FC3572BCEAA6` | 466267 |
| `docs/testing/r504-g03-terminal-frames-data-filename.md` | 本纸（新件，未纳入 index） | 🔴 哈希不能自指：本纸最后一笔落盘后的 sha256[:16] 与行数见交回单 | — |

`git status --porcelain` 全文只有这四枚（前三枚 + 本纸）：`M app/api/v1/chat.py`、`M docs/api/contract-v1.md`、
`?? tests/test_r504_…`、`?? docs/testing/r504-…`。🔴 在册件一枚未改：`frontend/**`、`app/agents/orchestrator.py`、
`scripts/dispatch_preflight.py`、`tests/test_r491_*`、`app/storage/sessions.py`、`docs/handoff/2026-09-15-*` 全部零字节。
没 commit、没 `git add`、没 push、没起服务、没动容器、没打模型、没连库（读写都没有）。

## 4. 判据实测读数（🔴 全部为「执行层自报」，总控并树时须亲跑同名件）

解释器：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（本工作树无 `.venv`，只借用主树解释器读字节，未在主树落任何文件），`python -X utf8 -m pytest … -p no:cacheprovider`。

| 批 | 文件清单 | 读数 |
| --- | --- | --- |
| 一（本单新钉） | `tests/test_r504_terminal_frames_carry_data_filename.py` | **25 passed**，exit 0，10.29 s |
| 二（在册终态四枚） | `tests/test_r254_sync_lane_terminal.py`、`tests/test_r414_b_terminal_data_filename.py`、`tests/test_r254_queue_terminal_honesty.py`、`tests/test_r295_queue_owner_readback.py` | **96 passed**，exit 0，14.06 s |
| 三（终态＋缓存＋队列扩样六枚） | 批二四枚 + `tests/test_r259_terminal_readout_lands_in_the_book.py`、`tests/test_r154_provenance_surface.py` | **141 passed**，exit 0，16.23 s |
| 四（队列/终态/缓存/取消/SSE 扩样 23 枚） | `tests/test_answer_cache_scope.py`、`test_r181_text_frame_ruler.py`、`test_r194_queue_denials_and_flat_list.py`、`test_r199_anonymous_probe_audit.py`、`test_r222_queue_terminal_stopwatch.py`、`test_r227_discard_is_honest.py`、`test_r227_lease_heartbeat.py`、`test_r229_connect_retry.py`、`test_r232_queue_status_vocabulary_sync.py`、`test_r37_report_lane_enqueue.py`、`test_r37_report_lane_worker.py`、`test_r439_terminal_answer_never_shows_the_marker.py`、`test_r456_error_round_is_not_an_answer.py`、`test_r464_one_terminal_answer_stream_per_round.py`、`test_r64_row_scope_error_codes.py`、`test_reliable_queue_status_api.py`、`test_request_cancellation.py`、`test_cancellation_epoch.py`、`test_r149_sse_text_pieces.py`、`test_r218_cache_hit_observability.py`、`test_r294_principal_freeze.py`、`test_agent_result_records.py`、`test_trace_orchestration.py` | **377 passed**，exit 0，61.99 s |
| 五（三刀复跑，见 §5） | 每刀：`tests/test_r504_terminal_frames_carry_data_filename.py`＋`test_r254_sync_lane_terminal.py`＋`test_r414_b_terminal_data_filename.py`（共 65 枚） | 刀① 17 failed / 48 passed；刀② 9 failed / 56 passed；刀③ 15 failed / 50 passed |

🔴 没有跑 `scripts/run_gate.py` 全量门（明令禁止），因此本单**没有**全量绿票数字可交；批一至批四的
同名件在 `405cacb` 干净树上的对照数本单也没跑（跑不了：那要在树外另起一棵工作树）。
按 AGENTS 那条「dirty 一遍＋commit 后干净树复跑」的第二遍，归总控并树时补。

## 5. 三把刀（变异只落本工作树，跑完逐字节还原）

三把刀都改 `app/api/v1/chat.py`，跑完 `Copy-Item` 还原并以 SHA256 比对基线：三枚都 **`same=True`**，
最终 `git diff --numstat -- app/api/v1/chat.py` 仍为 `53 14`。

| 刀 | 变异（原文 → 变异文） | 红句原文（首枚） | 读数 |
| --- | --- | --- | --- |
| ① 补造 | `data_filename = terminal_data_filename(list(dataset_files or []))` → 尾部加 ` or "sales-2026.xlsx"` | `AssertionError: 这一轮真没跑数据，那一格必须整枚缺席，实际读到 'sales-2026.xlsx'` | 17 failed / 48 passed，exit 1＝本单新钉 10 枚 + `test_r254_sync_lane_terminal` 6 枚 + `test_r414_b_terminal_data_filename` 1 枚（`test_the_legacy_done_frame_key_set_is_untouched`） |
| ② 摘键 | `return sse_event("done", attach_terminal_data_filename(payload, dataset_files))` → `return sse_event("done", payload)` | `AssertionError: legacy done 又不说用的哪份文件了。键集合：['answer_present', 'approval', 'sources', 'sources_error', 'sources_present', 'terminal_state', 'type', 'usage']` | 9 failed / 56 passed，exit 1，红面全部由本单新钉交（含 AST 面 `test_only_the_two_terminal_constructors_mount_the_cell`）；🔴 两枚在册件在这一刀下全绿——摘掉 legacy `done` 那一道不碰它们钉的形状，说明这一格读数是本单新长的牙，不是借别人的钉凑数 |
| ③ 并脸 | `if data_filename:` → `if True:`（等于永远落一格空串） | `AssertionError: 这一轮真没跑数据，那一格必须整枚缺席，实际读到 ''` | 15 failed / 50 passed，exit 1＝本单新钉 8 枚 + `test_r254_sync_lane_terminal` 6 枚（`test_the_done_frame_never_leaves_a_key_off` 五枚全红＋`test_the_two_lanes_share_one_readout_key_set`）+ `test_r414_b` 1 枚（`test_the_legacy_done_frame_key_set_is_untouched`） |

刀③的红面里那两枚在册件是本单最想交的数字：**把缺席并成空串，动的不是我的新钉，是别人钉过的形状**。

## 6. 判据③：名字同源（AST 面的账）

`app/api/v1/chat.py` 里把值交给 `data_filename` 这一格的地方，改后共**五处**（AST 现取，函数名运行时派生）：

| # | 归属函数 | 形状 | 落的对象 | 取值表达式 |
| --- | --- | --- | --- | --- |
| 1 | `_ask_stream` | dict 键（canonical `request.completed` 的 `data`，`:3005`） | canonical 终态 | `terminal_data_filename(dataset_files)` |
| 2 | `_approve_stream` | dict 键（同上，`:3688`） | canonical 终态 | `terminal_data_filename(dataset_files)` |
| 3 | `attach_terminal_data_filename` | 下标赋值 `:385` | `payload`（done / 队列终态共用） | 同名局部量，绑定唯一来源＝`terminal_data_filename(...)` |
| 4 | `queue_terminal_readout` | 下标赋值 `:5031` | `readout`（`/queue/status` 投影） | `data.get("data_filename")`——纯搬运，不重新判定、不从载荷之外取值 |
| 5 | `ask` | 下标赋值 `:2548` | `user_ctx` | `request.data_filename`——🔴 请求方向，既有，只喂图，没进任何一枚终态帧 |

由此交出的钉（全在 `tests/test_r504_terminal_frames_carry_data_filename.py`，25 枚里占 8 枚）：

- `test_every_terminal_value_for_the_cell_comes_from_the_one_registered_function`：交值处数 == 5；
  dict 形只许两枚且都直接调在册函数、且归属函数名逐字 == `_approve_stream` / `_ask_stream`；
  下标形只许 `payload` / `readout` / `user_ctx` 三枚；全表内不许出现 f-string 或字符串拼接造名字。
- `test_the_mount_helper_delegates_and_never_assembles`：挂载件里唯一的取值表达式是 `terminal_data_filename(...)`，
  且 `basename` / `.join(` / `.format(` 一枚都不许出现。
- `test_the_readout_projection_only_copies_the_payload_cell`：搬运件的右值必须是 `data.get("data_filename")`。
- `test_only_the_two_terminal_constructors_mount_the_cell`：`attach_terminal_data_filename(...)` 的调用方
  只许 `build_queue_terminal` 与 `done_sse_frame` 两枚。
- `test_the_three_constructors_all_take_the_collector_sink`：三枚构造点都收 `dataset_files`，
  且**谁都不许收一枚现成的 `data_filename`**（那正是第二处拼名字的起点）。
- `test_the_collector_is_still_the_only_dataset_sink_feeder`：`_collect_dataset_filenames` 仍只一枚定义、两枚写点。
- `test_the_registered_function_is_defined_exactly_once_and_still_assembles_nothing`：在册函数一枚定义，
  且它自己不拼名字。

行为面同源证据：`test_the_done_frame_and_the_canonical_terminal_never_disagree`（`/ask` 与 `/approve` 两道都钉）
——同一轮的 legacy `done` 与 canonical `request.completed` 交回的文件名逐字相等，两枚出口一旦分家就红。

## 7. 判据④：零新错误码 / 零新增外部请求 / 零 Chroma

- `rg -c classification_blocked app/` → **EXIT 1（0 命中）**（改后现取）。
- 新增行里没有任何外部请求或写点：`git diff -U0 -- app/api/v1/chat.py` 的 `+` 行扫描
  `requests|httpx|socket|urllib|redis|chroma|open\(|connect\(` → **0 命中**。
- `chat.py` 全文 `chroma`（大小写不敏感）→ 0 命中（改前也是 0，本单没引入）。
- 错误码字面集（`"error_code": "…"`）改前（`git show 405cacb`）与改后逐字相同，三枚：
  `internal_error` / `no_answer_produced` / `task_timeout`；本单新增 0 枚，由
  `test_the_change_added_no_error_code_no_chroma_and_no_new_exit` 钉住，同一枚件还钉
  `yield done_sse_frame(` == 3、`yield done_frame_for_turn(` == 3、`"type": "done"` == 1（六枚 done 出口一枚不多一枚不少）。

## 8. 腿 3（答案缓存命中不发 `request.completed`）——🔴 本单未治，只做取证

那一腿今天到底交回什么（现取坐标，全部在 `app/api/v1/chat.py`）：

| 帧 | 坐标 | 载荷里有什么 |
| --- | --- | --- |
| `event: status` | `:2627` | 一句人读的「📋 缓存命中，直接返回」 |
| `event: text` | `:2629`（`cache_fields` 在 `:2614`） | 正文 + `cached: True` + `cache_generated_at` + `cache_note` 三枚缓存脸 |
| canonical `sources` | `:2640`，仅当 `_cached_source_manifest(...)`（`:2624`）读得出清单 | `session_id` / `sources` / `hit_count` / `unauthorized_count` / `scope_reason_code` |
| `event: done` | `:2656`（🔴 本单**没**给它 `dataset_files`） | 八格里缺 `data_filename`；清单读不出时 `sources_error == "answer_cache_without_manifest"`（`:2087`） |
| canonical `request.completed` | **零枚** | — |

⇒ 屏上少掉的那一格：`data_filename`（「本轮答的是哪张表」的回显脸，`ChatPanel.vue` 的 `server-data-readout`，
R501 §1.2 在册）。更准确地说，命中轮缺的不止那一格——`state.terminalRead` **整枚不出现**，
于是 `session_id` / `worker_count` / `elapsed` / `answer_length` / `awaiting_*` 五枚也一并没有脸；
R501 已把「帧没到」与「帧到了但那一格没给」钉成两张脸（`terminalRead` 键都不许多出来 vs `seen` 是空数组），
本单沿用同一口径，没有把两者抹平。

对还是错（本席的判断，写给总控裁，不写成结论）：

- **对的一半**：命中轮不发终态帧，就没有任何一枚假读数上屏——这与「宁缺不猜」同向；
  前端在册钉也已经禁止拿请求值（`AskRequest.data_filename`）填这一格，所以屏上是「服务端没回这一格」那张脸，
  不是「服务端说用了 A」。
- **错的一半（病根不在「不发」，在「没落账」）**：`_cache_source_manifest`（`:605`）存的是
  `_collect_document_sources` 折出来的**文档**证据行，dataset 那一格从来没进过缓存条目；
  `_cached_source_manifest`（`:633`）今天也读不出用表读数。所以即便现在给命中道补发一枚
  `request.completed`，那一格仍只能是空串/缺席——**补发不等于补得上读数**。
- 影响面今天**没量到**（差在哪：要量得读答案缓存的条目数与命中分布，本单明令不许连库写、不许起服务，
  也没有现网 Redis 读数；`cache_answer` 在测试里是桩位，交不出真实条目计数）。⇒ 属独立立案（先量影响面）
  或归 R505 那一族，本单一行产品行为都没改，只在钉里钉住现状：
  `test_the_cache_hit_leg_hands_back_no_terminal_frame_at_all`（帧序逐枚点名 + `data_filename` 缺席 +
  `sources_error` 具名 + `terminal_state == answered`），并在件里写明「若命中道开始发 canonical，本枚要跟着改口并另案」。

两条出路（都超出本单写域，只登记）：
甲＝给缓存条目加一枚只读的 dataset 落账（写集在 `app/common/cache.py` 与 `_cache_source_manifest` 旁边，
影响面是已存在的每一条条目都读不出它 ⇒ 仍要保留缺席态）；
乙＝命中道补发 canonical `request.completed` 并把那一格明写「无从核对」（写集在 `chat.py` 的 `cached_response`）。
两枚都要先量影响面，都不许拿请求方向填。

## 9. 没做到（明写，别读成已收）

1. 🔴 **队列道的读数当时仍然交不出来**（R504 交单口径；今天已治，见本条末订正）：`build_queue_terminal` 的键已备好，但三处调用方
   `deploy/queue_worker.py:695 / :740 / :897` 都还没把 `_collect_dataset_filenames` 的 sink 传进来
   （那枚文件不在本单写域）。所以队列这一腿交的是「形状在位、读数为空」= 载荷里没有那一格。
   一处一线、不新增第二份收集器，改法已在契约 R504 节登记。
   🔴 **R517 订正（2026-09-29）**：这一腿已由 R514 并树（`333d728`）治完——现读 `deploy/queue_worker.py` 三处调用在 `:703 / :749 / :913`，各在 `:711 / :757 / :921` 递进 `dataset_files=dataset_files`，收集只走在册那枚 `chat._collect_dataset_filenames`（`:681` 报告档两腿共用、`:912` 老腿），一处一线、没添第二份收集器；零枚与多枚折成空串 ⇒ 整格缺席。上面那三枚坐标（`:695 / :740 / :897`）是交单当时的现读，今天已漂，按「不改历史读数」原样留着。
2. 🔴 **屏上那一格当时仍只由 canonical 那一发驱动**（R504 交单口径；legacy 那一发今天已接上，见本条末订正）：`frontend/src/lib/sessions.js:574-576` 的 `done` 分支只置
   终止状态、不读载荷键；`/queue/status` 的读数只喂排队那张脸（`components/ChatPanel.vue:1499` 的 `queueReads`
   与 `lib/provenance.js:247`）。本单交的是后端侧字节，两道新读数要上屏属前端线一手（写域禁碰 `frontend/**`）。
   🔴 **R517 订正（2026-09-29）**：legacy 那一发已由 R512 并树（`131df9b`）接上——现读 `sessions.js:575` 把 `payload.data_filename` 抄成 `state.terminalDataFilename`（那一支 `:574-576` 未漂，漂的是「不读载荷键」那半句），非空才抄、空串不覆盖不补造、缺席一字不动，先到者胜；屏侧读者仍只 `adoptServerDataRead`（`ChatPanel.vue:698-703`）。`/queue/status` 那一腿今天仍只喂排队那张脸：`queueReads` 现读 `ChatPanel.vue:1228`（上面那枚 `:1499` 已漂）、`lib/provenance.js:247` 未漂——队列那一格屏侧还没读者。
3. 没跑 `scripts/run_gate.py` 全量门（明令），也没有全量绿票数字；AGENTS 那条「dirty 一遍＋commit 后干净树复跑」
   的第二遍本单交不了（本席不许 commit），同名件的干净树对照数也没在树外另起工作树去取。
4. 腿 3 的影响面没量（见 §8）；§5 的三把刀只跑在册终态三枚件那 65 枚，没跑全量的反证面。
5. 没起服务、没 `npm run build`、没截图——浏览器里看不到改动，本纸全部是字节 + 帧形状口径。
6. `docs/handoff/2026-09-26-v1-frontend-gap-list.md` 的 G03 判定行（`:155`）与 `:251`/`:259` 仍写「服务端两格都欠」；
   `docs/testing/r501-…` §5 的请裁项与 §6 的「后端根本没给」三处也需要同步改口（现在剩腿 3 一处）。
   🔴 台账归总控写，本单一行没动。

## 10. 请总控裁的点名清单（本单自己一枚在册件都没改）

| 点名 | 现状 | 为什么要裁 |
| --- | --- | --- |
| `tests/test_r254_sync_lane_terminal.py:151`（`set(frame) == {"type"} \| SHARED_READOUT_KEYS`，相等式） | 未改，仍绿 | 本单选「说不清⇒整格缺席」才保住了它；若业主要 legacy `done` 恒带这一格（键在位、值可空串），就必须连这枚件一起改口，那是**改宽**，本单不做 |
| 同文件 `:175`（`set(payload) - SHARED_READOUT_KEYS == {"schema","worker_status","scope_reason_code"}`） | 未改，仍绿 | 同上：队列终态载荷的键集相等式，靠缺席保住 |
| `tests/test_r414_b_terminal_data_filename.py:210` `test_the_legacy_done_frame_key_set_is_untouched` | 未改，仍绿 | 它说的是「R414 那一单没往 done 里塞格」；今天塞格这件事由 R504 做了，但只在真读得出时塞。件名与判据读起来容易过期，是否给它补一句「R504 之后仍无读数时不许塞」请裁 |
| `docs/handoff/2026-09-26-v1-frontend-gap-list.md` G03 行 / §7.3 `:251` / §7 表 `:259` | 未改 | 派工词与本纸的实测口径不同源，`:259` 那句「只差回显」今天仍是过期账 |
| 本纸 §8 的腿 3（命中道不发终态 + 缓存条目没落账） | 未治 | 要么独立立案（先量影响面），要么归 R505 那一族；本单按派工词只取证，没顺手改 |
| 派工词与本纸的一处口径差 | 本单多改了 `queue_terminal_readout`（`/queue/status` 投影） | 不改它，队列道即使将来传了 `dataset_files` 也到不了客户端；改法是纯搬运（不新增判定）。请裁这算不算腿 2 应有之义 |
