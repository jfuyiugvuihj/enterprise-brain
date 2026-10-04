# R545 —— 队列道「失败任务可定位与重试」：量具、离线牙、以及容器那一遍还欠什么

工单：R545（V2 #8／#22）。工作树 `C:\Users\fengx\PycharmProjects\be-r545b`，分支 `codex/be-r545b`，基点 `4da0bad`。
交付物三件：`scripts/r545_queue_failure_probe.py`、`tests/test_r545_queue_failure_teeth.py`
＋ `tests/test_r545_counter_evidence_teeth.py`、本纸。

🔴 **本单只交离线半张**：量具能跑、牙在咬、纸把容器那一遍的窗口写清楚——**本单没有交任何一枚容器读数**。
底稿那句「缺的是一次真队列失败读数」到今天**仍然成立**，那一句归总控开窗执行（§10）。
全文每条「命令原文 → 实取读数」都是 2026-10-04 在本树现取；引用别人的历史数字时一律标出处位（不拿旧账当尺）。

---

## 1 盘面自证（命令原文 → 实取读数）

| 命令原文 | 实取读数 |
| --- | --- |
| `git -C C:\Users\fengx\PycharmProjects\be-r545b rev-parse --short HEAD` | `4da0bad` |
| `git -C ... status --porcelain`（本纸写完之前） | `?? scripts/r545_queue_failure_probe.py` / `?? tests/test_r545_counter_evidence_teeth.py` / `?? tests/test_r545_queue_failure_teeth.py`（三枚未跟踪，其余零行） |
| `git -C ... diff --numstat HEAD` | 空输出（无任何跟踪件被改） |
| `git config --get core.autocrlf` | `true` |
| `git ls-files .gitattributes` | 空（本仓无属性文件） |
| `python -c "open('tests/test_reliable_queue.py','rb').read()"` | 工作树样本 164 枚 CRLF / 164 枚 LF ⇒ 检出口径＝CRLF；本单三件产物写完即转 CRLF（`ctrl=0`，见 §12 台账 T13） |
| 解释器 | `C:\Users\fengx\PycharmProjects\be-r545b\.venv\Scripts\python.exe`（Junction → 主树 venv；`sys.version` = 3.11.7 | packaged by Anaconda, Inc.） |

主树 `C:\Users\fengx\PycharmProjects\企业智脑` 全程未写一字节（唯一自证＝§6 的 K 刀影子只在内存＋`test_z9` 按 sha256 复比对跟踪件）。

---

## 2 终态词表与原因码落点（全部由 AST 现派生，零手抄）

派生入口：`scripts/r545_queue_failure_probe.py` 的 `derive_vocabulary()`（:421）——读 `app/common/reliable_queue.py`
（状态键写法 `:230 _status_key`）、`app/api/v1/chat.py`（路由字面量）、`docs/api/contract-v1.md`（契约两档）、
`scripts/eval_transport_ask_v2.py`（在册量具的停表词与散文枚数）。

```
命令原文： python scripts/r545_queue_failure_probe.py 之外的等价现读——
           python -c "import importlib.util,sys;s=importlib.util.spec_from_file_location('p','scripts/r545_queue_failure_probe.py');m=importlib.util.module_from_spec(s);sys.modules['p']=m;s.loader.exec_module(m);v=m.derive_vocabulary();print(v['terminal'],v['non_terminal'],v['route_only'],v['blind_spots'],v['drift'],v['stale_prose'])"
实取读数： terminal = ['done','cancelled','failed','dead','awaiting_approval','expired']   ← 六枚，不是五枚
           non_terminal = ['queued','processing','cancel_requested']
           queue_written = ['awaiting_approval','cancel_requested','cancelled','dead','done','failed','processing','queued']  ← 队列写过 8 枚
           route_only = ['expired']            ← expired 只由路由回答，队列一字节不写它
           blind_spots = []    drift = []      ← 代码面与契约面互相对得上
           stale_prose = [5]   sixth_terminal_named = True
           unreadable = []
```

契约那枚枚举行（命令原文 `rg -n "status\` is one of" docs/api/contract-v1.md`）→
`docs/api/contract-v1.md:598`：`status` is one of `queued, processing, cancel_requested, done, cancelled, failed, dead, awaiting_approval, expired`（九枚：6 终态 + 3 非终态）。
`CONTRACT_ENUM_RE` 对这一行的现取结果＝`contract.enum_line_present = True`（**修后**；修前它在本树这种 CRLF checkout 上静默读成 `False`——那是量具自己的洞，根因与赎罪牙见 §13.1）。逐值分档由 `CONTRACT_BULLET_RE` 从 `## Long Task Status`（:581）那批 `* \`dead\` (terminal, written by the queue): …` 条目抠出 9 枚（6 终态 + 3 非终态），解析器不硬编码值名；枚数与代码面互证靠 `blind_spots/drift` 双双为空。

**状态词写点（逐枚点名，`sites` 实取）**

| 状态词 | 写点（文件:行） |
| --- | --- |
| `queued` | `app/common/reliable_queue.py:268`, `:596` |
| `processing` | `app/common/reliable_queue.py:296` |
| `done` | `app/common/reliable_queue.py:359` |
| `cancelled` | `app/common/reliable_queue.py:284`, `:355`, `:574`, `:614` |
| `failed` | `app/common/reliable_queue.py:289` |
| `awaiting_approval` | `app/common/reliable_queue.py:415`（第六枚，2026-09-25 R259 一族带进来的） |
| `dead` | `app/common/reliable_queue.py:593` |
| `expired` | 队列侧**无写点**；只在路由回答：`app/api/v1/chat.py:5284` `{"status": "expired", "message": "请求已过期，请重新提交"}` |

**原因码／失败账的落点（文件＋函数名，2026-10-04 现取行号）**

| 落点 | 坐标 | 交回什么 |
| --- | --- | --- |
| 失败落账 | `app/common/reliable_queue.py:558 fail_or_retry()` → `:582 data["last_error"] = error` | 原因码原文进 `last_error` |
| 丢弃落账 | `:531 _record_discard()` → `:546 data["last_error"] = f"{RESULT_DISCARDED}:{reason}"` | 前缀 `result_discarded:`（常量 `:59 RESULT_DISCARDED`） |
| 失败读数 | `:647 failure()`（底稿写的 `:498` 已漂） | `{attempts, max_attempts, last_error, status, ...}` |
| 死信判词 | `:628 dead_verdict()` | 那枚判词是「可定位」的第二层证据，量具单独咬（§5） |
| 死信深度 | `:679 dead_letter_depth()`（底稿写的 `:529` 已漂） | `LLEN` 产品自己的 dead 列表 |
| 死信 schema／状态 | `:98 DEAD_TERMINAL_SCHEMA = "queue-dead-v1"`、`:96 DEAD_STATUS = "dead"`、`:74 AWAITING_APPROVAL` | 派生值：`dead_schema = queue-dead-v1`，`discard_prefix = result_discarded:` |
| 稳定码枚举 | `app/agents/contracts.py`（`dict_keys_returned`/`stable_error_codes()` 派生） | **29 枚**在册稳定码，含 `context_limit_exceeded`（`:103 CONTEXT_LIMIT_CODE`、`:604`）——量具不许发明新码 |
| 死信读出口 | `app/api/v1/chat.py:5132 queue_dead_readout()` | 6 枚键：`terminal_schema/terminal_state/reason/retryable/answer_present/terminal_note`（`:5135` 注释点名真机单 `a55ef916eb43486789a9a68f81cb9f7c`：worker 早算出成因，缺的是把它送到读出口） |
| 终态读出口 | `app/api/v1/chat.py:5040 queue_terminal_readout()` | 14 枚键：`result, terminal_schema, terminal_state, answer_present, answer_is_park_notice, worker_status, sources_present, sources, scope_reason_code, sources_error, usage, approval, terminal_note, data_filename` |
| 终态构造 | `app/api/v1/chat.py:2260 build_queue_terminal()` | 契约那批结构化键的生产侧 |
| 在册轮询门 | `app/api/v1/chat.py:5255 @router.get("/queue/status/{request_id}")` | 量具读回就走这一扇（`poll_path` 派生值 `/queue/status/`），**不另开新出口** |
| 在册 cancel 门 | `app/api/v1/chat.py:5316 @router.post("/queue/{request_id}/cancel")` | 派生自代码，纸面抄的值一律不算 |
| 授权腿 | `app/api/v1/chat.py:858 _authorize_queue_task()`（`:890 raise _refused(404, "resource_not_found")`） | 状态键不在时的 404——`expired` 那格够不着的根因（§8 附带发现） |
| worker 侧 | `deploy/queue_worker.py:729 report_failure_record()`、`:759 _fail_report_turn()`、`:827 stream_piece_sink=piece_ledger` | 见 §8 前提①：可注册点今天**在** |

---
## 3 九格量具：每格只有 PASS / FAIL / UNMEASURED 三种说法

`CELLS`（`scripts/r545_queue_failure_probe.py:126`）逐枚点名——这就是「可定位证据」的清单化：

| 格 | 交回的证词 |
| --- | --- |
| `provenance` | `--expect-rev` 与容器 `BUILD_INFO` 的 revision 是否同一枚；不给 expect 就没开窗条件（交 UNMEASURED，不猜） |
| `vocabulary` | 六枚终态／三枚非终态／`route_only`／`blind_spots`／`drift`／逐枚写点 `sites`／在册量具纸面的过期枚数（转出项） |
| `failure_reason` | 每枚失败终态的**原因码字段名**（`reason`／`last_error`）、`last_error` 前缀（`result_discarded:` 在不在）、`attempts/max_attempts`、哪枚终态其实说不出原因 |
| `dead_keys` | 死信行是否带 `terminal_schema=queue-dead-v1`、`terminal_state` 是否逐字回显状态键、`reason` 是否落在 29 枚在册稳定码里、`retryable` 在不在 |
| `retry_budget` | 重试计数是否越界（`attempts <= max_attempts`）、不可重试那一判是否白占了名额 |
| `dead_letter_depth` | 死信深度＝`LLEN` 产品自己的那枚列表（`ReliableQueue.dead_letter_depth()` 同一口径），并核「本轮落了 N 枚 dead，列表只长了 M」 |
| `idempotency` | 幂等键名由 `ReliableQueue._idempotency_key()` 现算（不抄格式），键指向的 `request_id` 是否就是这一枚 |
| `terminal_keys` | 契约那四枚 structured terminal readout 键（`terminal_state`／`answer_present`／`sources_present`／`usage`）逐枚给证词 |
| `none_is_none` | 扫全部读数：`None` 有没有被折成 `0`/空表/空串，哨兵值有没有冒充缺失 |

**四枚键逐枚说得出口（这是工单点名的硬要求）**。命令原文 → 实取读数（离线重放那一遍，`--offline` §12 台账 T8）：

```
python scripts/r545_queue_failure_probe.py --offline %TEMP%\r545-offline-selfcheck
  terminal_keys  value={"asked": ["terminal_state","answer_present","sources_present","usage"],
                         "rows": [{"posture":"budget","terminal":"dead",
                                    "verdicts":{"terminal_state":"read","answer_present":"read",
                                                "sources_present":"row_cannot_speak","usage":"row_cannot_speak"},
                                    "values":{"terminal_state":"dead","answer_present":false,
                                              "sources_present":null,"usage":null},
                                    "not_derivable":["sources_present","usage"]}],
                         "problems":[]}
```

- `terminal_state`／`answer_present`：**读到了**（死信行由 `queue_dead_readout` 那 6 枚键交出）。
- `sources_present`／`usage`：**这一行说不出**——死信出口的代码里就没有这两枚键（派生自 `queue_dead_readout` 的 `dead_readout_keys` 只有 6 枚），`queue_terminal_readout` 那 14 枚键只在「有正文可发布」的那两态才生产。量具把它记成 `row_cannot_speak` + 值 `None`，🔴 **不折成 `false`/`0`**（「没读到」与「读到零」是两件事）。
- 缺证登记面：`none_is_none` 格实取 `absent_cells=2, folded=[], sentinel_free=true`。
- `expired` 那张脸（`app/api/v1/chat.py:5284`）只交 `status` + `message` 两枚键：`evidence_from_row` 对它的六个失败字段全部交 `_absent()` → `None`；牙 `test_the_expired_row_speaks_nothing_and_the_probe_records_none` 咬住这一点。

---

## 4 注入失败的四枚姿势（写死在参数里，一字节不改产品码）

`POSTURES`（`:148`），`--inject` 可重复，缺省 `expired`：

| 姿势 | 姿势是什么 | armed 条件（现读闸，不满足就**交回命令原文**而不是猜） | 打不打模型 |
| --- | --- | --- | --- |
| `none` | 不注入，只读盘面 | — | 否 |
| `expired` | 拿一枚早已过 TTL 的 `request_id` 去问在册轮询门 | 无（零副作用） | 否 |
| `cancel` | 走 `POST /api/v1/queue/{request_id}/cancel` 请求侧取消 | 需真凭证与在飞的 report 轮次 | **会**（这一枚走真调用腿） |
| `budget` | 把 prompt 撑到超预算：只改**调用方发出去的字**（`--budget-repeat`，缺省 400） | worker 进程 `MODEL_CONTEXT_TOKENS` 必须 < `BUDGET_ARM_CEILING=8192`（`:165`）；读不出整数或不达标 ⇒ 不 armed，交回 `RECIPE_BUDGET` | **不会**：在册预算闸 `app/common/model_budget.py:1534 authorize_call()` 在把请求送上线**之前**就判拒（`:1464` 文档写明 `error_code=context_limit_exceeded`） |
| `endpoint` | 把 worker 进程的 `LOCAL_MODEL_BASE_URL`／`OLLAMA_BASE_URL` 指到一扇没人听的端口 | 需 env 在位；`--probe-tcp` 才让量具自己 tcp 探一下（缺省不连，不污染测量条件） | **会**（这枚就是要它产生真失败） |

旋钮读取姿势（命令原文 → 读数）：`env_witness()`（`:635`）先试 `docker exec <worker> printenv NAME`，拿不到再回落本进程 env，并把「问不到」如实写进 `note`——实测读数（本机，无容器）：`rc` 非 0 ⇒ `note = 容器里问不到（rc=…），回落本进程 env`，`MODEL_CONTEXT_TOKENS` 交不出整数 ⇒ 该遍 `budget` 不 armed，`reason = MODEL_CONTEXT_TOKENS 读不出整数（当前 None）：这一遍注入不出预算失败`。

`--inject bogus` → `error: argument --inject: invalid choice: 'bogus' (choose from 'budget', 'cancel', 'endpoint', 'expired', 'none')`，`rc=2`（台账 T11）。

---

## 5 离线牙（真队列 + 假 Redis + 假时钟，零 socket）

```
命令原文： python -m pytest tests/test_r545_queue_failure_teeth.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r545-pt-a -q
实取读数（终稿）： 30 passed, 8 warnings in 15.90s ／ blocked connect attempts to host model port: 0 ／ offline discovery stub calls (no socket opened): 0
            （行尾修复入库前那一枚同一命令是 29 passed / 85.50s —— 台账 T12 留原读数，不删旧账）

命令原文： python -m pytest tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r545-pt-b -q
实取读数（终稿）： 19 passed in 8.69s ／ blocked connect attempts to host model port: 0
            （§13.1 之前的同一枚读数是 19 passed / 8.85s —— 刀没被行尾修复钝化，枚数与 verdict 都没变）

命令原文： python -m pytest tests/test_r545_queue_failure_teeth.py tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider -q
实取读数（终稿）： 49 passed ＝ 30 ＋ 19（21.63s；blocked connect attempts 仍为 0）——台账 T14 那枚 48 是 §13.1 赎罪牙入库前的旧读数
```

假 Redis 沿用在册那枚 `tests/test_reliable_queue.py::FakeRedis`，本单只补两枚补角（`llen` 数深度、`expire` 续租）；时钟走 `clock=`／`sleeper=` 注入。工单点名的判据与牙的对应：

| 判据 | 牙 |
| --- | --- |
| 失败必带原因码，且原因码在终态载荷里读得出 | `test_a_dead_turn_carries_a_registered_reason_readable_on_the_terminal_payload`、`test_the_reason_code_is_a_registered_stable_code_and_no_new_code_lives_in_the_readout`、`test_the_route_readback_of_a_dead_row_feeds_the_probe_evidence`（走真路由 `TestClient(app)`，同进程零 socket） |
| 缺证记 `None`，不许折成 0/空表 | `test_the_expired_row_speaks_nothing_and_the_probe_records_none`、`test_a_key_that_is_absent_resolves_to_nothing_not_zero`、`test_a_null_key_in_place_is_reported_as_read_not_as_missing`、`test_the_dead_row_answers_all_four_readout_keys_with_an_explicit_verdict` |
| 重试计数不越界 | `test_the_retry_counter_never_exceeds_the_budget_and_dead_lands_at_the_ceiling`、`test_a_non_retryable_verdict_does_not_burn_a_retry_slot` |
| 死信深度数得对 | `test_the_dead_letter_depth_counts_dead_rows_not_attempts`、`test_the_depth_cell_refuses_to_call_a_still_list_unmeasured`、`test_a_dead_row_that_got_no_further_entry_reddens_the_depth_cell` |
| 幂等键生效 | `test_the_idempotency_key_maps_to_exactly_one_request_id`、`test_the_idempotency_cell_says_unavailable_instead_of_inventing_a_key` |
| 摘掉 `data["last_error"]` 那行必须红 | 见 §6 刀 K1（victim 已点名） |
| 终态词表少认一枚必须红 | 见 §6 刀 K2 |
| 词表/停表/路径全由派生而非手抄 | `test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word`、`test_the_stop_words_come_from_the_derived_vocabulary`、`test_the_polling_exit_path_is_derived_not_copied`、`test_the_derivation_says_the_gauge_paper_still_claims_five_terminals` |
| 量具自己的纪律 | `test_the_probe_refuses_an_artifact_directory_inside_the_repo`、`test_zero_never_comes_from_an_empty_window`、`test_the_exit_code_is_two_when_a_cell_cannot_be_measured`、`test_the_budget_and_endpoint_postures_only_arm_on_a_live_knob`、`test_the_probe_only_asks_the_queue_for_readings_never_mutates_it`（AST 自证 Redis 腿只有 ping/GET/LLEN）、`test_the_probe_help_text_renders_and_still_declares_the_exit_codes`（一手踩过的坑：`--help` 曾被一枚字面 `%` 炸死） |

---

## 6 反证刀（七把，逐枚点名 victim；每把先跑正控）

机械沿用 R552/R585：影子只在内存（源文读进字符串→归一 LF→改→`compile`+`exec` 成另一枚模块），绝不写回仓内；影子模块 `ROOT` 指回真仓；每把刀都先跑「同一套机械、`edits=()`」的正控。

| 刀 | 摘掉什么 | victim |
| --- | --- | --- |
| K1 | `fail_or_retry` 里 `data["last_error"] = error` 那一行（**工单词点名的那一枚**） | `test_a_dead_turn_carries_a_registered_reason_readable_on_the_terminal_payload` |
| K2 | 终态词表少认一枚（把写进状态键的 `awaiting_approval` 改成契约里没有的字） | `test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word` |
| K3 | `dead_verdict` 那一笔落账（两枚 dead 被洗成一枚） | `test_the_verdict_lands_on_the_durable_ledger_verbatim` |
| K4 | 把缺证折成零：`_absent()` 交 `0` 而不是 `None` | `test_the_expired_row_speaks_nothing_and_the_probe_records_none` |
| K5 | 摘掉「产物落仓外」那道闸 | `test_the_probe_refuses_an_artifact_directory_inside_the_repo` |
| K6 | 摘掉 `overall()` 里「量不到优先于通过」那一支（rc=2 变 rc=0） | `test_zero_never_comes_from_an_empty_window` |
| K7 | 把「原因码必须是在册稳定码」那一判钝化（发明一枚码也不红） | `test_an_unregistered_reason_code_on_the_readout_reddens_the_dead_cell` |

命令原文 → 读数：`pytest -k "positive_control or each_knife"` 实取 **7 passed / 7 passed**（两枚参数化各自 7 枚；含在 §5 的 19 枚里）。
另有 `test_z8_every_blade_anchor_is_still_exactly_one_hit_in_the_shipped_bytes`（刀口在被砍件里必须仍是**恰好一枚**命中）、
`test_z8b_the_two_deads_stay_tellable_apart_after_the_blade_set`、`test_z9_the_tracked_files_are_byte_for_byte_unchanged`（sha256 复比对跟踪件）、
`test_z9b_no_shadow_artifact_landed_inside_the_repo`、`test_z9c_the_worktree_carries_only_this_tickets_write_domain`（`git status --porcelain` 只允许 `scripts/r545_`／`tests/test_r545_`／`docs/testing/r545-` 三枚前缀）。

---

## 7 退出码语义（写死在 epilog，命令原文 `python scripts/r545_queue_failure_probe.py --help` → rc=0）

- `0` = 九格全 PASS **且**这一遍真读到至少一枚带原因码的失败终态。
- `1` = 至少一格 FAIL（词表漂了／原因码读不出／把缺证折成了零）。
- `2` = 至少一格 UNMEASURED，或量具自己没跑成（缺凭证／Redis 那腿不通／契约读不到／产物目录落在仓内）。
- 🔴 **2 永远不是通过**：`REPORT_LANE_VIA_QUEUE` 没翻、窗没开，正确的结果就是 2。牙 `test_zero_never_comes_from_an_empty_window`、`test_the_exit_code_is_two_when_a_cell_cannot_be_measured` 钉住这一点。
- 闸序（`main()` :1508 起，现读）：`--print-recipe` → 仓外闸（:1517）→ 词表派生（:1522）→ `--offline` 重放（:1527）→ 缺凭证（:1540）→ 才碰 Redis 腿与会话（:1544+）。⇒ 缺凭证/仓内产物目录这两条**在任何一次问出去之前**就返回 2（实测：`--out scripts` → `rc=2` 一行中文拒绝，见台账 T10）。

---
## 8 顶回来的前提（底稿四条口径 + 一条附带发现，全部 2026-10-04 本树现读）

| # | 底稿/纸面怎么写 | 现读实际 | 影响 |
| --- | --- | --- | --- |
| ① | 「`git grep -q stream_piece_sink -- deploy/queue_worker.py` → **rc=1**（无可注册点）」 | 同一条命令今天 **rc=0**；`deploy/queue_worker.py:827 stream_piece_sink=piece_ledger`（另见 `:603/:635` 形参与移交、`:729 report_failure_record()`、`:759 _fail_report_turn()`） | R548 一族已把可注册点并树。⇒ 「#22 流式失败要挂收端」这一半**不再是前置缺失**，本单的 R 刀 K1 才落得下去 |
| ② | 行号 `reliable_queue.py:498 failure()`、`:529`、`:423` | `:647 failure()`、`:679 dead_letter_depth()`、`:582 data["last_error"] = error` | 行号漂（产品码在长）。本纸一律给现取行号，且量具**不写死行号**——全靠 AST 派生，别人一次编辑不会让量具变哑 |
| ③ | 「终态是不是这五枚（done/cancelled/dead/expired/failed）」 | 是**六枚**：第六枚 `awaiting_approval`（`app/common/reliable_queue.py:415` 写点、`:74`/`:84` 常量、契约 `:598` 在册） | 少认一枚就是把「挂起等批准」读成非终态；刀 K2 专钉这一枚 |
| ④ | 在册量具纸面 `scripts/eval_transport_ask_v2.py:56` 「今天五枚终态（done/cancelled/dead/expired/failed）」 | 派生 6 枚 ⇒ 该件**散文与自己的停表码不一致**（它的停表词实际是 6 枚：`gauge.stop_words = [awaiting_approval, cancelled, dead, done, expired, failed]`） | 这是**转出项**（不在本单写域），量具如实交回 `stale_prose=[5]`；vocabulary 格给 **PASS + note**，散文过期不算产品缺陷，但也不许洗成口径一致 |
| ⑤ 附带发现 | 纸面把 `expired` 当一枚可读到的失败终态 | `expired` 只由路由回答（`chat.py:5284`），队列侧零写点；且状态键随 TTL 消失后先撞 `_authorize_queue_task` 的 **404 `resource_not_found`**（`chat.py:890`）——🔴 **在册轮询门很可能根本够不着 `expired` 这张脸** | `--inject expired` 这一枚量的正是这件事：够不着就记 `None`/UNMEASURED（rc=2），**不折成「没有失败所以干净」**。要真拿到失败带原因码的读数，必须跑 `budget` 或 `cancel` 姿势 |

---

## 9 容器那一遍还欠什么（逐枚点名，别当成「翻个开关就绿」）

1. **要哪个开关**：`REPORT_LANE_VIA_QUEUE=on`。入队判定现读＝`app/api/v1/chat.py:2568 if lane == LANE_REPORT and _report_lane_via_queue_enabled():`，env 名 `:1306 REPORT_LANE_QUEUE_ENV`，读法 `:1311-1313`。生产今天仍是 `off`（AGENTS 口径）⇒ 问出去的报告轮次走同步腿，队列里没有行，九格除 `provenance/vocabulary` 外全 UNMEASURED，**正确 rc＝2**。
2. **本树看不到现网 env**：`git check-ignore -v deploy/.env.server` → `.gitignore:11:deploy/.env.server`；`git ls-files --error-unmatch deploy/.env.server` → `did not match any file(s) known to git`。⇒ 翻开关/恢复只在部署机做；本单受「禁动 `.env*`」约束，**没翻、也没提议由执行层翻**。
3. **镜像里没有 `docs/`**：`Dockerfile` 的 COPY 只有 `:51 pyproject.toml uv.lock README.md` 与 `:111-114 migrations/ scripts/ deploy/ app/`。⇒ 容器内 `derive_vocabulary()` 读 `docs/api/contract-v1.md` 会 `OSError` → 当场 rc=2。两条出路（本单都没在真容器里试过，照实写）：把契约那一节带一份副本进容器并用 `--contract-from` 指过去；或在宿主机那棵带 `docs/` 的树里跑、只经 `--base-url` 问容器（此时 Redis 腿必须在容器内，`REDIS_URL` 只在容器 env 里）。
4. **用哪枚解释器**：`/app/.venv/bin/python`（`Dockerfile:16 UV_PROJECT_ENVIRONMENT=/app/.venv`、`:17 PATH=/app/.venv/bin:/usr/local/bin:...` 首位）。显式写 `/usr/local/bin/python` 会拿不到 app 的依赖（python-dotenv 等），量具在 `connect_reliable_queue()` 之前就会 import 失败。
5. **会不会打模型**（逐枚）：`expired` 不会（零副作用）；`budget` 不会（在册闸 `app/common/model_budget.py:1534 authorize_call()` 在送上线之前判拒，`:1464` 文档点名 `error_code=context_limit_exceeded`）；`cancel` **会**（要一枚在飞的轮次）；`endpoint` **会**（这一枚就是让真调用腿撞墙）。⇒ 想「零模型调用的真失败读数」，只要 `budget` 那一枚。
6. **窗口条件**：backend/worker/scheduler 三枚容器**不在 recreate 过程中**（本单读到的一切都不算数）；`--expect-rev` 给主树 HEAD 的 40 位；容器内 `BUILD_INFO` 可读（`provenance` 格靠它）；`budget`/`endpoint` 两枚改完旋钮要**容器重建而非镜像重建**——`docker compose --env-file deploy/.env.server -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --force-recreate backend worker scheduler`（`env_file:` 在容器创建那一刻才解析，`docker restart` 不重读；该口径由 `tests/test_r255_env_documents_the_conversion.py` 钉着，AGENTS 在册）。
7. **跑完必须恢复**：`MODEL_CONTEXT_TOKENS`／`LOCAL_MODEL_BASE_URL` 改回原值并**再 recreate 一次**，否则下一班读到的是歪窗口；`REPORT_LANE_VIA_QUEUE` 若为这一遍翻上去，测完按业主口径决定留不留（本单不代业主决定）。
8. **期望读数长什么样**：`failure_reason` 里至少一枚行的 `reason_code` 落在 29 枚在册稳定码内、`last_error` 非空；`dead_keys` 那枚行带 `terminal_schema=queue-dead-v1`；`dead_letter_depth` 的 `delta` 等于本轮 dead 枚数；`idempotency` 的 `maps_to == request_id`；`terminal_keys` 对 done 行四枚全 `read`、对 dead 行允许两枚 `row_cannot_speak`（那是代码事实，不是缺陷）。**rc=1 才是真缺陷；rc=2 只说明窗没开够。**

---

## 10 总控开窗该用的一行命令原文（`--print-recipe` 现取，rc=0）

```bash
# 主命令（容器内、账号走 env、产物落仓外）
docker exec -e EVAL_USERNAME -e EVAL_PASSWORD enterprise-brain-worker-1 \
  /app/.venv/bin/python scripts/r545_queue_failure_probe.py \
  --inject expired --inject cancel --inject budget \
  --expect-rev <主树 HEAD 40 位>
```

配套两枚旋钮姿势（同一条 `--print-recipe` 交回）：

- `budget`：在 `deploy/.env.server` 把 `MODEL_CONTEXT_TOKENS` 调小（< 8192）→ `docker compose --env-file deploy/.env.server -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --force-recreate backend worker scheduler` → 跑完改回来再 recreate 一次。
- `endpoint`：把 worker 进程的 `LOCAL_MODEL_BASE_URL` 指到一扇没人听的端口（例 `http://127.0.0.1:1`）→ 同一条 recreate 命令生效 → 跑完改回来再 recreate。

离线自证那一遍（**不是容器凭据**，只证明量具自己会算账）：

```bash
python scripts/r545_queue_failure_probe.py --offline %TEMP%\r545-offline-selfcheck                          # rc=2（provenance UNMEASURED：没给 --expect-rev）
python scripts/r545_queue_failure_probe.py --offline %TEMP%\r545-offline-selfcheck \
  --expect-rev cccc…cccc --build-info %TEMP%\r545-offline-selfcheck\BUILD_INFO                               # rc=0，九格全 PASS
```

---

## 11 诚实边界（本单没做的事）

- **一枚容器读数都没交**：没动容器、没动 Redis、没打模型、没连 PG；`--inject` 任何一枚都没真跑过一次（工单明写「本单不许真跑它，只交出来」）。
- 九格里 `provenance/failure_reason/dead_keys/retry_budget/dead_letter_depth/idempotency/terminal_keys` 的 PASS **只来自离线重放**（伪造 `BUILD_INFO`、假 Redis 行、单枚合成 dead 行），它证的是「算账逻辑对」，不证「现网能读到」。
- §8⑤ 那条「`expired` 够不着」目前是**读码推论**，真机那一遍才算数。
- 死信深度、幂等键的**枚数**只在假 Redis 上量过；现网列表里本就有历史 dead 行时，量具按 `delta`（本轮增量）判，不按绝对值判——这一条已在 `judge_dead_depth` 写死并有牙。
- `app/api/v1/observability.py` 按规避原则处理：一次全仓 `rg` 的输出里扫到过它的两行文件名，**未据它写任何判据**，也未打开该文件。
- 🔴 本单自己炸过一次：一次性脚本的非法 `newline` 参数把唯一副本截成 0 字节，已按四枚正控影子副本的 sha256 互证恢复回位（全程见 §13.2）；量具的一枚 CRLF 假阴性也由这次事故顺手揪出并修掉（§13.1）。
- 没跑 `scripts/run_gate.py`；只跑本单两枚测试件。没 commit、没建分支、没改评测集。

---
## 12 命令台账（命令原文 → 实取读数；均为 2026-10-04 在本树跑过的那一遍）

| # | 命令原文 | 实取读数 |
| --- | --- | --- |
| T1 | `git -C <树> rev-parse --short HEAD` | `4da0bad` |
| T2 | `git -C <树> status --porcelain` | `?? scripts/r545_queue_failure_probe.py` `?? tests/test_r545_counter_evidence_teeth.py` `?? tests/test_r545_queue_failure_teeth.py`（本纸追加前） |
| T3 | `git -C <树> diff --numstat HEAD` | 空（跟踪件零改动） |
| T4 | `git grep -q stream_piece_sink -- deploy/queue_worker.py; echo rc=$LASTEXITCODE` | `rc=0`（底稿记 rc=1，已过期 → §8①） |
| T5 | `python scripts/r545_queue_failure_probe.py --print-recipe` | `rc=0`，三行命令原文逐字见 §10 |
| T6 | `python scripts/r545_queue_failure_probe.py --help` | 修前：`ValueError: unsupported format character T (0x54) at index 9`，`rc=1`；修后：`rc=0`，渲染出来是单枚 `%TEMP%`（牙已并树 → §5 末行） |
| T7 | `python -c "…derive_vocabulary()…"`（脚本原文见 §2） | `terminal` 六枚、`non_terminal` 三枚、`queue_written` 八枚、`route_only=[expired]`、`blind_spots=[]`、`drift=[]`、`unreadable=[]`、`stable_codes=29`、`dead_schema=queue-dead-v1`、`discard_prefix=result_discarded:`、`poll_path=/queue/status/`、`dead_readout_keys` 6 枚、`terminal_readout_keys` 14 枚、`stale_prose=[5]` |
| T8 | `python scripts/r545_queue_failure_probe.py --offline %TEMP%\r545-offline-selfcheck` | `rc=2`：`provenance UNMEASURED`（没给 `--expect-rev`），其余八格 PASS；`failure_reason` 行读数 `reason=context_limit_exceeded / last_error=context_limit_exceeded / attempts=1 / max_attempts=3`；`dead_letter_depth` `before=0 after=1 delta=1`；`idempotency` `maps_to=request_id` `matches=true` |
| T9 | 同 T8 加 `--expect-rev cccc…cccc --build-info %TEMP%\r545-offline-selfcheck\BUILD_INFO` | 九格全 PASS，`rc=0`（🔴 这是**伪造 rev 的离线重放**，不是容器凭据） |
| T10 | `python scripts/r545_queue_failure_probe.py --out scripts` | `rc=2`：`产物目录 scripts 落在仓库内：这一单的写域只有 scripts/tests/docs 三处，证据件必须落仓外（%TEMP% 或 --out）` |
| T11 | `python scripts/r545_queue_failure_probe.py --inject bogus` | `rc=2`：`invalid choice: bogus (choose from budget, cancel, endpoint, expired, none)` |
| T12 | `python -m pytest tests/test_r545_queue_failure_teeth.py -o addopts= -p no:cacheprovider --basetemp=… -q` | `29 passed, 8 warnings in 85.50s` ／ `blocked connect attempts to host model port: 0` ／ `offline discovery stub calls (no socket opened): 0` |
| T13 | `python -m pytest tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider --basetemp=… -q` | `19 passed in 8.85s`（终稿复跑 `8.69s`，见 T24 之后 T25） ／ `blocked connect attempts to host model port: 0` |
| T14 | 合跑两枚件同口径 | `48 passed`（＝29＋19；转 CRLF 后复跑） |
| T15 | 行尾归一＋控制字符扫描（脚本逐枚点名 `bytes/lines/ctrl/backtick/tab/BOM`） | `r545_queue_failure_probe.py 85612/1570/ctrl=0/16/tab=0/无BOM`、`test_r545_queue_failure_teeth.py 32426/619/ctrl=0/24/tab=0/无BOM`、`test_r545_counter_evidence_teeth.py 12739/246/ctrl=0/22/tab=0/无BOM`、本纸（§12 追加前）`28106/256/ctrl=0/791/tab=0/无BOM`；扫描逐枚点名 → 见终稿复扫（`0x00/07/08/0B/0C` 合计 0；本纸自身每追加一段字节数就变，故只把 `ctrl=0` 当稳定判据） |
| T16 | `git check-ignore -v deploy/.env.server` ／ `git ls-files --error-unmatch deploy/.env.server` | `.gitignore:11:deploy/.env.server` ／ `error: pathspec … did not match any file(s) known to git`（现网 env 不在版本库，本单看不到） |
| T17 | `rg -n "COPY" Dockerfile` | `:51 pyproject.toml uv.lock README.md`、`:111 migrations`、`:112 scripts`、`:113 deploy`、`:114 app` ⇒ **没有 `docs/`**；`:16 UV_PROJECT_ENVIRONMENT=/app/.venv`、`:17 PATH=/app/.venv/bin:/usr/local/bin:…` |
| T18 | `rg -n "status\` is one of" docs/api/contract-v1.md` | `:598` 九枚枚举行；`## Long Task Status` 在 `:581`，结构化终态键表在 `:647-:704`（含 `usage` 那格「读不到就交 null 不许交 0」的原文） |
| T19 | `rg -n "def failure|def fail_or_retry|def dead_verdict|def dead_letter_depth|def _record_discard|last_error" app/common/reliable_queue.py` | `:531/:546/:558/:582/:628/:647/:679/:230/:59/:74/:96/:98`（逐枚点名见 §2 表） |
| T20 | `rg` 现取 `app/api/v1/chat.py` 与 `deploy/queue_worker.py` 坐标 | chat `:858/:890/:1306/:1311/:2260/:2568/:2847/:5040/:5132/:5255/:5284/:5316`；worker `:729/:759/:813/:827/:844/:846`；budget 闸 `app/common/model_budget.py:1534`（`:1464` 文档点名 `context_limit_exceeded`）、`app/agents/contracts.py:103/:604` |
| T21 | `python -m pytest tests/test_r545_queue_failure_teeth.py -k "line_endings" -o addopts= -p no:cacheprovider -q` | `1 passed, 29 deselected in 4.70s` ／ blocked connect 0（§13.1 那枚赎罪牙） |
| T22 | `python -c`：分别喂 LF 原文与 `read_source()` 读数给 `contract_status_table` | 修前：`src has CR: 5979` ／ `enum False`（直接 `read_text` 那份＝True）⇒ 洞在量具侧不在纸面；修后：`enum_line_present: True`，且 `terminal/non_terminal/by_route` 与修前逐枚相等 |
| T23 | `Get-FileHash SHA256` 对 `%TEMP%` 里四枚正控影子副本 ＋ 回位后的 `scripts/r545_queue_failure_probe.py` | 五枚同为 `4C09E3A54E47FFF7901A5F060C0B6130098809BC2D0765E31CF525BBECE05D1F`（§13.2 的恢复凭据） |
| T24 | `python -m pytest tests/test_r545_queue_failure_teeth.py tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider -q` | `49 passed in 21.63s`（终稿）／ `blocked connect attempts to host model port: 0` ／ `offline discovery stub calls: 0` |
| T25 | 终稿逐枚分跑（同一口径，两枚件各一遍） | `30 passed, 8 warnings in 15.90s` ＋ `19 passed in 8.69s` ＝ 49；两遍各自 `blocked connect attempts to host model port: 0` |
| T26 | 终稿扫描（逐枚点名 `bytes/lines/ctrl/backtick/tab/BOM`）＋ `Get-FileHash SHA256` | `r545_queue_failure_probe.py 86155/1579/ctrl=0/29/tab=0/无BOM`、`test_r545_queue_failure_teeth.py 33657/638/ctrl=0/33/tab=0/无BOM`、`test_r545_counter_evidence_teeth.py 12739/246/ctrl=0/22/tab=0/无BOM`、本纸 `39281/322/ctrl=0/1153/tab=0/无BOM`；sha256 前缀：探针 `F71B94C66583A654`、牙 `DCE927F97A58A202`、反证刀 `92D82E038269B778`、本纸 `4CB4FBF9B44DB583` |
| T27 | 行尾修复后复验离线重放与闸 | `--offline … --expect-rev cccc… --build-info …` ⇒ 九格全 PASS、`rc=0`（与修前逐格同）；`--help rc=0`、`--out docs rc=2`、`--print-recipe rc=0`；`rg -n "def normalize_newlines" scripts/r545_queue_failure_probe.py` ⇒ `:183`（`read_source :191`、`contract_status_table :360` 里再兜一道 `:362`） |

---

## 13 本单自纠的两件事（一手踩的，照实写在纸上）

### 13.1 量具自己被 CRLF checkout 咬了一口（已修 + 已下牙）

- **症状**：契约那格交出 `enum_line_present = False`，而 `docs/api/contract-v1.md:598` 明明写着九枚枚举行（T18 的 `rg` 读数就是它）。
- **根因**：`read_source()` 走 `path.read_bytes().decode("utf-8")`，本仓 `core.autocrlf = true` ⇒ 检出来是 CRLF；枚举行正则 `^\`status\` is one of .+\.$` 要求**最后一个字符是字面 `.`**，而 MULTILINE 的 `$` 落在 `\n` 之前，那枚 `\r` 卡在中间 ⇒ **静默失配**。同族的 `CONTRACT_BULLET_RE` 结尾是 `(?P<prose>.+)$`，`.` 把 `\r` 吞了照旧命中——所以这个洞不会自己喊出来，只会悄悄少一张面孔。
- **修法**：加 `normalize_newlines()`（`scripts/r545_queue_failure_probe.py:183` 起），挂在 `read_source()` 这唯一咽喉上，并在 `contract_status_table()` 里再兜一道（`--contract-from` 带进容器的那份副本走的是另一条读法）。派生面从此与检出口径无关。
- **赎罪牙**：`test_the_derivation_does_not_depend_on_the_checkout_line_endings`——同一份契约喂 CRLF 与喂 LF 必须逐枚相等，且 `enum_line_present is True`、`read_source` 交回的文本 `chr(13) not in` 它（实取 T21 `1 passed, 29 deselected in 4.70s`）。
- **影响面**：只影响**量具自己的证词**，一字节产品码未动；修前修后 `terminal`／`non_terminal`／`route_only`／`blind_spots`／`drift`／`unreadable` 六项读数逐枚相同（T22），变的只有那枚 bool（假阴 → 真）。§2 表里那句「契约在册九枚」的读数从头到尾是对的。

### 13.2 命令通道把量具截成 0 字节（已按凭据恢复，无凭据就该停手）

- **起因**：一次性编辑脚本里写了 `Path.write_text(text, encoding="utf-8", newline="\\n")`——多一个反斜杠让 `newline` 成了非法值；`open("w")` 在**校验参数之前**就把唯一副本 truncate 了，`ValueError` 抛出时文件已是 0 字节。这是 AGENTS「命令通道写文本」那族坑的又一枚变体：🔴 与反引号无关，规矩是**任何「先截断、后校验」的写句柄都不许对着唯一副本开**。
- **恢复凭据**：反证刀的**正控影子**（`edits = ()`，即一字未改的源文留痕）在 `%TEMP%` 三跑独立目录里留下四枚副本，与回位后的目标文件五枚 sha256 全等：`4C09E3A54E47FFF7901A5F060C0B6130098809BC2D0765E31CF525BBECE05D1F`（T23）。取的是 `r545-pt-final` 那一枚——它来自最后一次交回 `48 passed` 的那一遍，所以回位物就是被牙验过的那份。
- **回位自证**：`bytes=85612 lines=1570 ctrl=0 backtick=16 tab=0 无BOM`、`--help rc=0`、`--out scripts rc=2`、`%%TEMP%%` 在位、`git status --porcelain` 无越界条目、`.new/.final/.newc/.finalc` 逐枚清扫后 `glob` 只剩目标文件本身。
- **之后所有写入姿势**：`.final` 落盘 → `py_compile.compile(doraise=True)` → `os.replace()` 原位替换；目标文件的写句柄永不在校验前打开。
- **顺序说明**：13.2 的回位发生在 13.1 打补丁**之前**，所以行尾修复是打在已验文件上的；两件事叠加后的终稿＝`30 ＋ 19 ＝ 49 passed`（T24）。

---

### 复跑口径（给总控照抄）

```powershell
cd C:\Users\fengx\PycharmProjects\be-r545b
.\.venv\Scripts\python.exe -m pytest tests/test_r545_queue_failure_teeth.py tests/test_r545_counter_evidence_teeth.py `
  -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r545-pytest" -q
```

（PowerShell 里 `%TEMP%` 不展开，实跑要写 `$env:TEMP` 或绝对路径；`-o addopts=` 是为绕开全局并行递归扇出，与本单无关的在册规矩。）

**一句话交接**：量具与牙已到位且能自证「缺证 ≠ 通过」；`docs/testing` 之外零写点；**这一格真正欠的那枚读数仍欠着**——要 `REPORT_LANE_VIA_QUEUE=on` 的窗口 + `budget` 姿势（不打模型那一枚），由总控开窗跑，期望 rc＝0（拿到带在册原因码的死信行）或 rc＝1（真缺陷），rc＝2 只说明窗没开够。

---

# R641 续写（同一张纸，2026-10-04；基点已从 `4da0bad` 前移到 `df90ea0`）

工单：R641 = R545 的返工单。树 `C:\Users\fengx\PycharmProjects\be-r545b`，分支 `codex/be-r545b`，
基点 **`df90ea0`**（§1–§13 的读数是在 `4da0bad` 现取的，本续写把受影响的面孔重新量过，见 §18）。

## 14 返工缘由、病因现形、同型病自查（逐枚点名函数）

### 14.1 退回的那一枚（本席亲跑，不是转抄）

| 命令原文 | 实取读数 |
| --- | --- |
| 总控 10-04 在主树亲跑 `tests/test_r545_*.py` | **1 failed / 48 passed / 22.96 s**，红在 `tests/test_r545_counter_evidence_teeth.py::test_z9c_the_worktree_carries_only_this_tickets_write_domain` |
| 本席在 `be-r545b@df90ea0` 返工前复跑同两件 | **49 passed / 22.68 s**（同一枚牙在自己的树里绿 = 病的全部症状） |

病因（源码级）：旧 `test_z9c` 执行 `git -C <此刻所在的树> status --porcelain`，然后断言**每一条**未提交条目都必须
落在本单写域内。这就是把「整棵工作树此刻干不干净」当常驻判据——而它判的其实不是本单的货。

### 14.2 病因现形（同一枚判据在三枚树上的读数；全部只读取证）

驱动：`%TEMP%\r641_probe_its.py`（`git -C <树> ls-files --others --exclude-standard` ∪ `diff --name-only HEAD`，
再按写域前缀过滤；均带 `-c core.quotePath=false`）。

| 树 | 全盘未提交条目 | 其中写域外 | 清单 |
| --- | --- | --- | --- |
| 主树 `企业智脑`（**只读**，只跑了 git 三枚只读命令） | 10 枚 | **10 枚** | `.zcodeignore`、`chroma_db/chroma.sqlite3`（被跟踪件被改）、`课堂实践-对象建模-企业智脑/` 里 8 枚业主作业件 |
| 本站 `be-r545b`（返工后） | 4 枚 | 0 枚 | 只有本单四枚货 |
| 影子树 `df90ea0` 干净检出 + 只投本单货 + 复现主树那种脏 | 7 枚 | **3 枚** | `.zcodeignore`、`chroma_db/chroma.sqlite3`、`作业目录/对企建模块-企业智脑.md` |

⇒ 旧那一判在主树与在复现树都会红，而红的原因是**别人的脏**，不是本单的货写越界。这就是同族病第三次
（#96 拿施工期盘面脏当永真判据／#107 拿旧账收席／R545 `test_z9c`）。

另记一笔口径差：旧牙读的是 `status --porcelain`——未跟踪**目录**被折叠成一枚条目（主树三行）；返工后判定面走
`ls-files --others --exclude-standard`，逐枚点名到文件（主树十枚）。工单点名的正是后者。

### 14.3 返工写法（`tests/test_r545_counter_evidence_teeth.py`）

判定面从「此刻盘面」搬到 `tmp_path` 里的**受控影子仓**，三态各自点名（`test_z9c` 参数化）：

| 态 | 影子里摆什么 | 判定面读数 | 这一格证明什么 |
| --- | --- | --- | --- |
| `goods_in_domain` | 只有本单四枚货（未提交，全在写域内）+ 一枚被 `.gitignore` 遮住的 `build/r545_mutant_probe_K1.py` | 全盘写域外 `[]`；货逐枚 `exists=true / inside_write_domain=true`；`--exclude-standard` 确实把 ignored 挡在清单外 | 正控：判定面绿得起来，且它看的是货不是全盘 |
| `poison_outside_domain` | 同上 + `app/poison.py` | 全盘写域外 **`["app/poison.py"]`**；货那一读仍 `[]` | **活牙**：往写域外塞一枚必红（旧牙拿它当唯一判据才是病） |
| `foreign_dirt_like_the_main_tree` | 同上 + 被跟踪 `chroma_db/chroma.sqlite3` 被改 + 未跟踪 `.zcodeignore` + 未跟踪 `作业目录/` | 全盘写域外点名三枚；**货判据仍 `offenders == []`** | 病治好了：主树那种脏进来，本单的货判定不跟着红 |

配套改动（都是把判据从盘面搬到受控端／静态端）：

- `test_z9c_the_write_domain_is_proved_on_a_controlled_shadow_repo`（新三态）取代旧「整棵树零越界」那一判；
  旧写法里的「`git status --porcelain` + 要求每条都落在 `scripts/r545_`／`tests/test_r545_`／`docs/testing/r545-`」
  已删除。写域前缀按本单原文扩到六枚（`scripts/r545_`、`scripts/r641_`、`tests/test_r545_`、`tests/test_r641_`、
  `docs/testing/r545-`、`docs/testing/r641-`）。
- 判定面拆成可测的纯函数：`untracked_entries()`／`tracked_modifications()`／`uncommitted_entries()`／
  `domain_violations()`／`shipment_check()`／`shadow_artifact_leaks()`／`live_checkout_gates()`／
  `repo_rooted_writes()`／`_top_level_functions()`——每一枚都收 `repo_dir`/`source` **参数**，不吃全局树。
- `test_z9_the_shadow_machinery_leaves_its_tracks_under_tmp_only`（返工）：旧 `test_z9` 的
  `TRACKED` 名册 + `FINGERPRINT_AT_IMPORT` + `_sha()` 三枚机械整块删除——那是「被跟踪件**此刻**的 sha」
  当判据，别的班并一枚产品码就假红，同族。返工后：AST 静态证明本件所有写句柄都不指仓根
  （`repo_rooted_writes()`），活性靠 `_top_level_functions()` 现形（毒必须落成**一枚真函数**，不数串，
  免得把字面量算成毒——本席第一版就是这么误判过一次），再加一枚动态正控：影子模块确实落在 `tmp_path` 里。
- `test_z9b_the_leak_scanner_is_proved_on_a_controlled_root`（返工，双态 `clean_shadow_root`／
  `planted_shadow_leak`）：旧写法 `rglob` **此刻的** `scripts/tests/docs` 找影子名，是把此刻仓内文件清单
  当判据（别人放一枚同名片段就假红）。返工后扫描器只对着受控根跑，摆货必红、不摆必绿。
- `test_z9d_no_checker_may_gate_on_the_live_checkout_state`（新增，反同族病的**常驻闸**）：AST 扫本件与在册钉件，
  凡盘面状态读取器（`STATE_READERS`）或带 `--porcelain`／`ls-files`／`diff`／`rev-list` 旗标的 `subprocess` 调用
  把 `REPO`／`PROBE_PATH` 当参数喂进去，当场点名行号与方法；再对本件源文打一针毒（注入一枚
  `domain_violations(uncommitted_entries(REPO))` 的函数）证明这枚闸自己会咬。以后谁再把盘面当判据，红在并树前。
- `test_z9e_the_named_shipment_is_present_and_inside_the_domain`（新增）：逐枚点名本单四枚货「在位 + 在写域内」，
  外加判定面的两枚边界读数（`app/poison.py` 等三枚必须被点名；`scripts/r641_*` 等三枚必须放行）。
  这一格在任何一棵树上同色——它不看盘面有多少条目。
- 🔴 没做的事（照工单词执行）：没给 `chroma_db/chroma.sqlite3` 之类加豁免名单，没 `pytest.skip` 掉这一格。
  唯一的 skip 分支是「机器上没有 `git` 二进制」这种环境缺件，且明写在 `_git()` 里，不参与写域判定。

### 14.4 其余三枚草稿的同型病自查（逐枚点名）

| 件 | 符号 | 是不是拿「此刻盘面／全盘状态」当判据 | 处置 |
| --- | --- | --- | --- |
| 反证刀 | `tests/test_r545_counter_evidence_teeth.py::test_z9c_the_worktree_carries_only_this_tickets_write_domain` | **是**（退回的那一枚） | 已返工成 §14.3 的三态影子仓 |
| 反证刀 | 旧 `::test_z9_the_tracked_files_are_byte_for_byte_unchanged`（`TRACKED`/`_sha`/`FINGERPRINT_AT_IMPORT`） | **是**（被跟踪件此刻的 sha；跨班一改产品码就假红） | 机械删除，换成 `::test_z9_the_shadow_machinery_leaves_its_tracks_under_tmp_only` |
| 反证刀 | 旧 `::test_z9b_no_shadow_artifact_landed_inside_the_repo` | **是**（此刻仓内文件清单） | 换成 `::test_z9b_the_leak_scanner_is_proved_on_a_controlled_root` |
| 反证刀 | `::test_z8_every_blade_anchor_is_still_exactly_one_hit_in_the_shipped_bytes` | 否——判的是被跟踪件的**字节内容**（刀口失配本该红） | 保留，设计内 drift 牙 |
| 反证刀 | `::test_z8b_the_two_deads_stay_tellable_apart_after_the_blade_set` | 否（假 Redis 内存账） | 保留 |
| 反证刀 | `::_arm`／`::_shadow_repo`／`::_exec_module` | 否：影子只写 `tmp_path`；影子模块 `ROOT` 指回真仓（只读） | 保留，活性由 `::test_z9_the_shadow_machinery...` 静态 + 动态双证 |
| 离线牙 | `tests/test_r545_queue_failure_teeth.py::test_the_probe_refuses_an_artifact_directory_inside_the_repo` | 否：`REPO` 只是喂给纯函数 `resolve_out_dir()`/`is_inside_repo()` 的**参数**（路径算术，不 `exists`、不扫盘） | 保留；state② 影子树复跑同色 |
| 离线牙 | `::test_the_probe_only_asks_the_queue_for_readings_never_mutates_it` | 否：`ast.parse(PROBE_PATH 源文)` 读内容不读状态 | 保留 |
| 离线牙 | `::test_the_derivation_does_not_depend_on_the_checkout_line_endings`、`::test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word`、`::test_the_derivation_says_the_gauge_paper_still_claims_five_terminals` | 否：派生自被跟踪件**内容**（内容与词表若漂，红得有道理） | 保留；df90ea0 复量读数见 §17 T30 |
| 离线牙 | `::_route_body` → `app/api/v1/chat.py::queue_status` 那一扇门（`TestClient` 同进程） | 否；`chroma_db` 写回被在册 `conftest.py` 的 R134 闸门改道出工作树（每次跑都交回「落点被改道：1 次／原路径 0 个」） | 保留——本席据此自证没把被跟踪的 `chroma_db/chroma.sqlite3` 写脏 |
| 量具 | `scripts/r545_queue_failure_probe.py::derive_vocabulary`／`::contract_status_table`／`::read_source`／`::stable_error_codes`／`::gauge_stop_words` | 否：全部是从源文 AST／正则派生 | 保留 |
| 量具 | `::resolve_out_dir`／`::is_inside_repo`／`::default_out_dir` | 否：纯路径算术（`Path.resolve()` 不要求存在）；产物缺省 `%TEMP%\r545-<date>` | 保留；`--out scripts` 实测 rc=2（T33） |
| 量具 | `::docker_printenv` | 只在 `env_witness(names, container=…, runner=…)` 显式接线时才问；两枚牙全部走 `environ=` 注入 | 离线牙**零 docker 调用**（本席全程零容器，见 §19） |
| 取证纸 | §1／§12 的 base 与手抄 `:NNN` 坐标 | 否（账面问题，不是牙） | 由 §15／§16／§18 订正：坐标改 `文件::符号`，base 改 `df90ea0` |

自查里顺手揪出的一枚**判定面自身的疯牙**（本席第一版，已修）：`repo_rooted_writes()` 把
`str.replace()`／`decode().replace("\r\n","\n")` 当成写句柄，于是把在册 `_text()` 里那一枚行尾归一误点名为
「往仓根写文件」（读数 `['94:replace(REPO)']`）。修法：写句柄分两族——路径方法
（`write_text`／`write_bytes`／`mkdir`／`touch`／`unlink`／`rmdir`）与 `os`／`shutil` 宿主下的文件系统函数，
`str.replace` 不再算数。这枚误报若留下，判定面自己就成了下一班要返工的那一枚。

## 15 坐标订正：纸面里的手抄 `:NNN` 一律作废，改按 `文件::符号` 或派生入口读

工单硬纪律：引用坐标一律 `文件::符号`，不许手抄行号。**§2／§7／§8／§9 里那些 `:582`／`:5284`／`:56` 之类
全部作废**，按下表读（右列全部是 `df90ea0` 本席 AST 现取，不是从旧纸誊的）。凡量具能派生的，坐标就写派生入口 + 读数键。

| 旧纸面的手抄坐标 | 现在该怎么指 | df90ea0 现取 |
| --- | --- | --- |
| `reliable_queue.py:582 data["last_error"] = error` | `app/common/reliable_queue.py::ReliableQueue.fail_or_retry`（刀 K1 的锚点原文由 `test_z8` 逐字钉住） | 锚点仍恰好一枚命中 |
| `reliable_queue.py:546 last_error = f"{RESULT_DISCARDED}:{reason}"` | `::ReliableQueue._record_discard` | 前缀 `result_discarded:` |
| `reliable_queue.py:498/647 failure()` | `::ReliableQueue.failure` | 交 `{attempts, max_attempts, last_error, status}` |
| `reliable_queue.py:628 dead_verdict()` | `::ReliableQueue.dead_verdict` | 账本键 `DEAD_VERDICT_LEDGER_KEY = 'dead_verdict'` |
| `reliable_queue.py:529/679 dead_letter_depth()` | `::ReliableQueue.dead_letter_depth` | `LLEN` 产品自己的 dead 列表 |
| `reliable_queue.py:230 _status_key` | `::ReliableQueue._status_key` | 幂等键另由 `::ReliableQueue._idempotency_key` 现算 |
| `reliable_queue.py:59/74/96/98` 四枚常量 | `::RESULT_DISCARDED`／`::AWAITING_APPROVAL`／`::DEAD_STATUS`／`::DEAD_TERMINAL_SCHEMA` | `'result_discarded'`／`'awaiting_approval'`／`'dead'`／`'queue-dead-v1'` |
| `reliable_queue.py:268/:296/:359/:284/:355/:574/:614/:289/:415/:593` 十枚状态词写点 | 不指行号——指量具派生面 `derive_vocabulary()['sites']`，再按 `::方法名` 读 | `queued`→`::ReliableQueue.enqueue`+`::ReliableQueue.fail_or_retry`；`processing`／`cancelled`／`failed`→`::ReliableQueue.reserve`；`cancelled`→`::ReliableQueue.ack`/`::ReliableQueue.cancel`/`::ReliableQueue.fail_or_retry`；`done`→`::ReliableQueue.ack`；`failed`→`::ReliableQueue.reserve`；`awaiting_approval`→`::ReliableQueue.complete`；`dead`→`::ReliableQueue.fail_or_retry`；`cancel_requested`→`::ReliableQueue.cancel` |
| `chat.py:5255 @router.get("/queue/status/{request_id}")` | `app/api/v1/chat.py::queue_status`（路径由 `derive_vocabulary()['poll_path']` 现取） | `/queue/status/` |
| `chat.py:5316 @router.post("/queue/{request_id}/cancel")` | `::cancel_queued_request`（`derived_cancel_path()` 现取） | `/api/v1/queue/{request_id}/cancel` |
| `chat.py:5284` 那一枚 `{"status": "expired", ...}` | `::queue_status` 里的早退分支（派生键 `vocab['faces']['early_returns']`） | `expired` 只由路由回答，队列侧零写点 |
| `chat.py:5132 queue_dead_readout()` / `:5040 queue_terminal_readout()` / `:2260 build_queue_terminal()` | `::queue_dead_readout`／`::queue_terminal_readout`／`::build_queue_terminal` | 派生读数 `dead_readout_keys` 6 枚、`terminal_readout_keys` 14 枚 |
| `chat.py:858/:890 _authorize_queue_task()` | `::_authorize_queue_task`（404 `resource_not_found` 分支在该函数体内） | §8⑤ 那条附带发现的根因位 |
| `chat.py:2568` 入队判定 / `:1306 REPORT_LANE_QUEUE_ENV` | `::_report_lane_via_queue_enabled` + 模块级 `::REPORT_LANE_QUEUE_ENV` | 常量值 `'REPORT_LANE_VIA_QUEUE'` |
| `contracts.py:103 CONTEXT_LIMIT_CODE`、`:604` | `app/agents/contracts.py::CONTEXT_LIMIT_CODE`、`::ErrorEnvelope` | `'context_limit_exceeded'`；在册稳定码由 `stable_error_codes()` 派生 **29 枚** |
| `model_budget.py:1534 authorize_call()`、`:1464` | `app/common/model_budget.py::authorize_call`；出码侧 `::context_error_code`／`::ModelContextLimitExceeded` | 预算闸在送上线之前判拒 ⇒ `budget` 姿势不打模型 |
| `queue_worker.py:729/:759/:827/:431/:603/:610/:635` | `deploy/queue_worker.py::report_failure_record`、`::_fail_report_turn`、装配点 `::_process_report_lane_turn`（`stream_piece_sink=piece_ledger`） | `git grep -q stream_piece_sink -- deploy/queue_worker.py` 仍 **rc=0** |
| `contract-v1.md:598` 枚举行 / `:581` 分档节 | 不指行号——指 `::CONTRACT_SECTION`（`## Long Task Status`）+ `::CONTRACT_ENUM_RE`，读数取 `contract_status_table()['enum_line_present']` | `True`（§13.1 那枚 CRLF 洞已修并有牙） |
| `scripts/eval_transport_ask_v2.py:56` 那句「今天五枚终态」 | 不指行号——指 `::gauge_stop_words()` 的派生读数 | `stop_words` 六枚、`prose_counts=[5, 5]` ⇒ `stale_prose=[5]`（转出项，不在本单写域） |
| `Dockerfile:16/:17/:51/:111-114` | 按指令点名：`Dockerfile::ENV UV_PROJECT_ENVIRONMENT=/app/.venv`、`Dockerfile::ENV PATH`、`Dockerfile::COPY pyproject.toml uv.lock README.md ./`、四枚 `Dockerfile::COPY --chown=10001:10001 migrations/scripts/deploy/app`、`Dockerfile::RUN printf 'revision=…' > /app/BUILD_INFO` | 镜像**不带 `docs/`**（§9 第 3 条成立）；`BUILD_INFO` 由那次 `RUN` 产出 |
| 量具自家常量坐标（`:126 CELLS`、`:148 POSTURES`、`:165`、`:183`、`:191`、`:360`、`:421`、`:635`、`:1508`、`:1517`…） | 改指符号：`scripts/r545_queue_failure_probe.py::CELLS`、`::POSTURES`、`::BUDGET_ARM_CEILING`、`::normalize_newlines`、`::read_source`、`::contract_status_table`、`::derive_vocabulary`、`::env_witness`、`::resolve_out_dir`、`::main` | 本件 `test_z8`／`test_z9d` 全程按符号与锚点原文判定，不认行号 |

## 16 两态亲跑对账（判据②：枚数必须相同，文件清单逐枚点名）

| 态 | 树 | 命令原文 | 读数 |
| --- | --- | --- | --- |
| state①（脏态本站树） | `be-r545b@df90ea0`，盘面挂着本单四枚 `??` | `.\.venv\Scripts\python.exe -m pytest tests/test_r545_queue_failure_teeth.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r641-pt-nails" -q` | **30 passed** in 17.11 s |
| state① | 同上 | `... -m pytest tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r641-pt-b" -q` | **24 passed** in 10.73 s |
| state① | 同上 | `... -m pytest tests/test_r545_queue_failure_teeth.py tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r641-pt-a" -q` | **54 passed**, 8 warnings in 24.05 s；`blocked connect attempts to host model port: 0`；`offline discovery stub calls (no socket opened): 0` |
| state②（`df90ea0` 干净检出 + 只投本单货） | `%TEMP%\r641-state2\tree` | `git -C be-r545b worktree add --detach %TEMP%\r641-state2\tree df90ea0` → 投货前 `status --porcelain` **零行** → 投四枚货 → 同一命令两件复跑 | **54 passed**, 8 warnings in 26.05 s（枚数与 state① 相同） |
| state②′（state② 同一枚树 + 复现主树那种脏） | 同上 | 改 `chroma_db/chroma.sqlite3`（被跟踪件）+ 新建 `.zcodeignore` + 新建 `作业目录/` → 盘面 7 枚条目 → 同一命令复跑 | **54 passed**, 8 warnings in 24.47 s（返工牙在这里也绿 = 病已治） |
| 逐枚点名（判据①的活性） | state① 与 state②′ 各一遍 | `... -m pytest tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider -v -k z9` | 两态**同一批 8 枚同名用例**逐字相同：`test_z9c...[goods_in_domain]`／`[poison_outside_domain]`／`[foreign_dirt_like_the_main_tree]`／`test_z9d_no_checker_may_gate_on_the_live_checkout_state`／`test_z9_the_shadow_machinery_leaves_its_tracks_under_tmp_only`／`test_z9b...[clean_shadow_root]`／`[planted_shadow_leak]`／`test_z9e_the_named_shipment_is_present_and_inside_the_domain`；各 `8 passed, 16 deselected` |

文件清单逐枚点名（state① 与 state② 同一批，无一枚差集）：

- `scripts/r545_queue_failure_probe.py`
- `tests/test_r545_queue_failure_teeth.py`
- `tests/test_r545_counter_evidence_teeth.py`
- `docs/testing/r545-queue-failure-probe-2026-10-04.md`（本纸）

枚数分解：`30 + 24 = 54`（返工前是 `30 + 19 = 49`；新增的 5 枚全在写域／影子那一格，产品码一字节未动）。

## 17 R641 命令台账（续 §12 的编号；全部 2026-10-04 在 `be-r545b@df90ea0` 现取）

| # | 命令原文 | 实取读数 |
| --- | --- | --- |
| T28 | `git -C <树> rev-parse --short HEAD` / `status --porcelain` / `diff --numstat HEAD` / `rev-list --count df90ea0..HEAD` | `df90ea0`／四枚 `??`（本单货）／空输出／`0` |
| T29 | 返工前 `pytest` 两件合跑（本席） | `49 passed` in 22.68 s（旧 `test_z9c` 在本站绿——同一枚牙在主树红） |
| T30 | `python -c "...derive_vocabulary()..."`（脚本同 §2） | `terminal` 六枚（含 `awaiting_approval`）、`non_terminal` 三枚、`queue_written` 八枚、`route_only=[expired]`、`blind_spots=[]`、`drift=[]`、`unreadable=[]`、`stale_prose=[5]`、`sixth_terminal_named=True`、`stable_codes=29`、`dead_schema=queue-dead-v1`、`discard_prefix=result_discarded:`、`poll_path=/queue/status/`、`dead_readout_keys` 6 枚、`terminal_readout_keys` 14 枚、`contract.enum_line_present=True` ⇒ 与 §2 在 `4da0bad` 的读数**逐枚相等** |
| T31 | `python scripts/r545_queue_failure_probe.py --print-recipe` | `rc=0`，三行命令原文（容器主命令／budget 重建／endpoint 重建）逐字同 §10 |
| T32 | `python scripts/r545_queue_failure_probe.py --help` | `rc=0`（渲染出单枚 `%TEMP%`，`%%` 已被插值吃掉） |
| T33 | `python scripts/r545_queue_failure_probe.py --out scripts` | `rc=2`：`[R545] rc=2 产物目录 scripts 落在仓库内：…证据件必须落仓外（%TEMP% 或 --out）` |
| T34 | `python scripts/r545_queue_failure_probe.py --offline %TEMP%\r545-offline-selfcheck` | `rc=2`：`provenance UNMEASURED --expect-rev 没给`，其余八格 PASS；`failure_reason` 行 `reason_code=context_limit_exceeded / last_error=context_limit_exceeded / attempts=1 / max_attempts=3`；`dead_keys` `terminal_schema=queue-dead-v1 / reason_is_stable_code=true / stable_code_count=29`；`dead_letter_depth before=0 after=1 delta=1`；`idempotency matches=true`；`terminal_keys` 四枚键＝`read/read/row_cannot_speak/row_cannot_speak` 且两枚说不出值的记 `null`；`none_is_none absent_cells=2 folded=[] sentinel_free=true` |
| T35 | T34 加 `--expect-rev cccc…（40 位） --build-info %TEMP%\r545-offline-selfcheck\BUILD_INFO` | `rc=0`，九格全 PASS（🔴 伪造 rev 的离线重放，**不是**容器凭据） |
| T36 | T34 加 `--expect-rev <本站 HEAD> --build-info …\BUILD_INFO`（镜像里那枚仍是 `cccc…`） | `rc=1`：`provenance FAIL 镜像里的 rev 与 --expect-rev 不相等：先 … --force-recreate …，不要 docker compose build backend` ⇒ rc=1 那一档也真走得通 |
| T37 | `git -C be-r545b worktree add --detach %TEMP%\r641-state2\tree df90ea0`；`git -C <影子> status --porcelain`；`rev-list --count df90ea0..HEAD` | `rc=0`；投货前零行；`0`（影子树是 `--detach` 检出，本席没建任何分支） |
| T38 | state①／state②／state②′ 三遍同名两件 | `54 / 54 / 54 passed`（见 §16） |
| T39 | `%TEMP%\r641_probe_its.py`（病因现形三树对照） | 主树 全盘 10 枚／写域外 10 枚；本站 4／0；影子+脏 7／3（明细见 §14.2） |
| T40 | `git worktree remove --force <影子>` + `git worktree prune` | `rc=0`；本站盘面回到 `?? ` 四枚，`scripts/`、`docs/`、`tests/` 里没漏下任何一枚证据件或影子件 |

## 18 顶回来的前提（`df90ea0` 复量版；点名推翻它的并树笔）

| # | 前提 | 在 `df90ea0` 的复量结果 |
| --- | --- | --- |
| ① | 「`deploy/queue_worker.py` 里 `stream_piece_sink` 零命中（rc=1）」 | **仍推翻**：`git grep -q stream_piece_sink -- deploy/queue_worker.py` rc=0，装配点在 `::\_process_report_lane_turn`。推翻它的并树笔：R548／R578 一族（`4da0bad` 之前已在树） |
| ② | 底稿那批手抄行号 | 已由 §15 整体作废改符号坐标；`app/common/reliable_queue.py`／`app/api/v1/chat.py`／`app/agents/contracts.py`／`deploy/queue_worker.py`／`app/common/model_budget.py` 在 `4da0bad..df90ea0` **一字节未动**（`git diff --name-only 4da0bad df90ea0` 的 29 个名里没有它们），所以 §15 的读数与本纸 §2 在旧基点的读数同源 |
| ③ | 终态是六枚不是五枚 | **仍成立**（T30 派生）：`awaiting_approval` 住在 `::ReliableQueue.complete`，刀 K2 钉它 |
| ④ | 在册量具 `scripts/eval_transport_ask_v2.py` 纸面写「五枚终态」 | **仍成立但源文已被改过**：`4da0bad..df90ea0` 里它被 **`497ac38`（R630 并树）** 与 **`b1a4760`（R635 并树）** 动过；本席复量派生面 `gauge_stop_words()` 交回 `stop_words` 六枚 + `prose_counts=[5, 5]` ⇒ `stale_prose=[5]` 未变，转出项照旧如实登记 |
| ⑤ | `expired` 只由路由回答、很可能够不着 | **仍成立**：写点在 `::queue_status` 早退分支，队列侧零写点；够不着就记 `None`/UNMEASURED（rc=2），不折成「没有失败所以干净」 |
| ⑥ | 契约文（本单禁区的同文） | `docs/api/contract-v1.md` 被 **`d1118af`（10-04 契约文末追加）** 动过；本席复量 `contract_status_table()`：分档九枚与枚举行 `enum_line_present=True` **未变**（追加发生在文末，`## Long Task Status` 那节没被改写）。本席没动该文件一字节 |

## 19 R641 诚实边界与纪律自证

- 🔴 **容器内那一遍仍然欠着，本单一枚容器读数都没交**。还欠的东西逐枚点名（继承 §9，`df90ea0` 复核未变）：
  ① 开关 `REPORT_LANE_VIA_QUEUE`——生产仍 `off`（常量名 `app/api/v1/chat.py::REPORT_LANE_QUEUE_ENV`，读法
  `::_report_lane_via_queue_enabled`）；不翻开关 ⇒ 九格里除 `provenance`／`vocabulary` 外全 UNMEASURED，**正确 rc=2**。
  ② 窗口：backend/worker/scheduler 三枚容器不在 recreate 过程中；`--expect-rev` 给主树 HEAD 的 40 位；容器内
  `BUILD_INFO` 可读（由 `Dockerfile::RUN printf 'revision=…'` 产出）；镜像不带 `docs/` ⇒ 契约那张脸要么带副本进
  `--contract-from`，要么在宿主机带 `docs/` 的树里跑。③ 会不会打模型：`expired` 不会、`budget` 不会（在册闸
  `app/common/model_budget.py::authorize_call` 在上线前判拒）、`cancel` 会、`endpoint` 会 ⇒
  想「零模型调用的真失败读数」只要 `budget` 那一枚。④ 旋钮改动要**容器重建不是镜像重建**，跑完必须改回再 recreate。
  ⑤ 期望：`rc=0` 才算拿到带在册原因码的死信行；`rc=1` 是真缺陷；`rc=2` 只说明窗没开够。
- 总控开窗那一句原文（T31 `--print-recipe` 现取，逐字）：

  ```bash
  docker exec -e EVAL_USERNAME -e EVAL_PASSWORD enterprise-brain-worker-1 /app/.venv/bin/python scripts/r545_queue_failure_probe.py --inject expired --inject cancel --inject budget --expect-rev <主树 HEAD 40 位>
  ```

- 本席零容器／零连库／零打模型／不起服务／不改 env：全程没跑 `docker exec`（`::docker_printenv` 只在显式接线时才问，
  两枚牙都走 `environ=` 注入，见 §14.4），没碰 PG 与 Redis，没动 `deploy/**`、`.env*`、`app/**`、`frontend/**`、
  `docs/api/contract-v1.md`、`docs/handoff/**`、`tests/fixtures/**`、`scripts/run_gate.py`、`pyproject.toml`／锁文件。
- 主树 `C:\Users\fengx\PycharmProjects\企业智脑` 只读：本席对它只跑了 `git status --porcelain`／
  `rev-parse --short HEAD`／`ls-files --others --exclude-standard`／`diff --name-only HEAD` 四枚只读命令（§14.2 的对照读数）。
  写全部发生在 `be-r545b` 与 `%TEMP%`；离线牙里 `conftest.py` 的 R134 闸门把 `chroma_db` 的写回改道出工作树
  （每遍交回「落点被改道：1 次／原路径 0 个」），所以被跟踪的 `chroma_db/chroma.sqlite3` 在本树始终一字节未动
  ——T28 那枚 `diff --numstat HEAD` 空输出就是它的自证。
- 没 `git commit`、没建分支、没 push、没跑全量门（`scripts/run_gate.py` 一次都没跑），只跑本单点名两件。
- 影子机械全程只写 `%TEMP%`（state② 的 worktree 建在 `%TEMP%\r641-state2`，用完 `remove --force` + `prune` 拆掉）；
  仓内三处写域没漏下一枚影子件（`::test_z9b` 双态 + 本席 T40 现取盘面互证）。
- 写盘姿势：中文正文含反引号一律走**单引号 here-string** 落 `%TEMP%`，再由脚本读入、`compile()` 校验语法、
  写 `.final` 后 `os.replace()` 原子替换——唯一副本的写句柄从不在校验之前打开（§13.2 那件事不再来一遍）。
  写完现读并扫控制字符，读数见 §20。

## 20 R641 终稿复跑与交付读数（本纸最后一节；命令原文 → 实取读数）

| # | 命令原文 | 实取读数 |
| --- | --- | --- |
| T41 | 终稿四枚重投 `%TEMP%\r641-state2\tree`（state②′，盘面挂着 ` M chroma_db/chroma.sqlite3` + `?? .zcodeignore` + `?? 作业目录/`）后：`<影子树>\` 内跑 `C:\Users\fengx\PycharmProjects\be-r545b\.venv\Scripts\python.exe -m pytest tests/test_r545_queue_failure_teeth.py tests/test_r545_counter_evidence_teeth.py -o addopts= -p no:cacheprovider -q` | `rc=0`，**54 passed**, 8 warnings in 23.24 s（终稿含本节那一遍；§20 追加前同一命令读数 22.96 s，枚数未变） |
| T42 | 同一条命令在 `be-r545b`（本站脏态树，终稿）复跑 | `rc=0`，**54 passed**, 8 warnings in 20.69 s（终稿含本节那一遍；§20 追加前同一命令读数 23.31 s，枚数未变） |
| T43 | `git -C be-r545b worktree remove --force %TEMP%\r641-state2\tree` + `git -C be-r545b worktree list` | `rc=0`；名册里已无该影子路径（本席建的影子是 `--detach` 检出，全程没建分支） |
| T44 | 交付盘面四枚（现取）：`git -C be-r545b rev-parse --short HEAD` / `status --porcelain` / `diff --numstat HEAD` / `ls-files --others --exclude-standard` / `rev-list --count df90ea0..HEAD` | `df90ea0` ／ `?? docs/testing/r545-queue-failure-probe-2026-10-04.md`、`?? scripts/r545_queue_failure_probe.py`、`?? tests/test_r545_counter_evidence_teeth.py`、`?? tests/test_r545_queue_failure_teeth.py` ／ **空输出**（被跟踪件一字节未动）／ 同那四枚逐枚点名（无第五枚）／ **`0`** |
| T45 | 写域清扫（`scripts`/`tests`/`docs` 里找 `r545_mutant|shadow-repo|shadow_repo|_r545_probe_K`） | `hits = []` —— 影子机械一枚都没漏进仓 |
| T46 | 终稿字节扫描（控制字符＝`0x00/07/08/0b/0c` 枚数） | `scripts/r545_queue_failure_probe.py` 86155 B / 1579 行 / CRLF 1579 / ctrl=0 / 反引号 29 / tab=0 / 无 BOM；`tests/test_r545_queue_failure_teeth.py` 33657 B / 638 行 / CRLF 638 / ctrl=0 / 反引号 33 / tab=0 / 无 BOM；`tests/test_r545_counter_evidence_teeth.py` 27401 B / 494 行 / CRLF 494 / ctrl=0 / 反引号 36 / tab=0 / 无 BOM；本纸（§20 追加前）67704 B / 533 行 / ctrl=0 / tab=0 / 无 BOM / 围栏行成对（`​```bash` 与 `​```` 各一枚，R641 段奇数反引号行只有那一处围栏） |

一句话交接（R641）：**病牙已拔掉了病因而不是牙**——写域自证搬到受控影子仓三态（摆货绿／`app/poison.py` 红／主树那种脏不参与），
同族病由 `test_z9d` 常驻闸顶着，以后谁再拿「此刻盘面」当判据就红在并树前；量具与离线牙的判据一枚没减
（`30 + 24 = 54`，返工前 `30 + 19 = 49`）。**这一格真正欠的那枚容器读数仍欠着**：要
`REPORT_LANE_VIA_QUEUE=on` 的窗 + `budget` 姿势（不打模型那一枚），一行命令原文见 §19；期望 `rc=0`
（拿到带在册原因码的死信行）或 `rc=1`（真缺陷），`rc=2` 只说明窗没开够。
