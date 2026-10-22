# R585｜`dead` 终态在可读面一个键都不交，客户只看到「没字」（P1）·交工纸

- 单号：**R585**（复投棒；上一棒 `Confucius` 死于 provider 429、零落盘）
- 工作树：`C:/Users/fengx/PycharmProjects/be-r585`（detached，基点 `394205a`）
- 日期：2026-10-03（本机 11:1x 收）
- 一句话：**worker 早就算出来的那枚原因码，今天第一次从队列账本走到 `/queue/status` 面上**；
  不新造一套原因码，不治窗口参数。

## 〇、先说死：本单不治的那一格

🔴 **本单不治上下文窗口参数，R586 才是**（R586 已由总控并树 `9c9a0b1`，两半配套 8192 且在册闸
实测 `paired`）。本单没有动 `MODEL_CONTEXT_TOKENS`、`OLLAMA_CONTEXT_LENGTH`、`deploy/.env.server`、
`docker-compose.yml` 任何一处，也没有动 `app/agents/nodes.py:379-387` 那条「不走兜底文案」的判定。
本单只做一件事：窗口不够大这件事**被拒之后**，客户在轮询面上读得到「是被哪一枚在册码拒的」。

## 一、判据⑤ 点名的两条原文（逐字引）

### 1-1 worker 日志原文

出处 `docs/handoff/2026-09-15-backend-followup-requests.md` §155 三（总控 10-03 09:57 现取，真机单子
`request_id=a55ef916eb43486789a9a68f81cb9f7c`）：

```
报告档终态不可重试，不再重投 -> dead: context_limit_exceeded (reason=non_retryable_terminal attempts=1 max_attempts=3)
```

取证口径照实（不冒充现场）：本班 11:0x 复取 `docker logs enterprise-brain-worker-1` 共 **456 行**，
对 `a55ef916eb43486789a9a68f81cb9f7c` 与 `不可重试` 双双**零命中**——那台 worker 容器已随 R586 的
compose 改动 `docker compose up -d --force-recreate`，09:57 那一段日志不在环上。所以上面那一句
引的是**落账原文**，不是本班现读。为了不让判据⑤ 停在抄写上，本班补一枚**影子复现**（自建
`request_id`、FakeRedis、零模型、零生产数据；构造器就是真生产那两台：
`deploy/queue_worker.py::report_failure_record` + `_fail_report_turn`）：

```
[QueueWorker] request_id=6a2ccbc12c984d3a9d9cce712e8757fa 报告档终态不可重试，不再重投 -> dead: context_limit_exceeded (reason=non_retryable_terminal attempts=1 max_attempts=3)
```

除 `request_id` 之外逐字符相等（同一枚 f-string，`app`/`deploy` 两侧都没为它改过一个字）。
跑法：`$env:TEMP\r585work\quote.py`（临时件，不落仓）；仓内同名链路已由
`tests/test_r585_dead_terminal_reason.py::test_a_dead_turn_now_speaks_its_reason_on_the_polling_surface`
逐字钉住（`"-> dead: context_limit_exceeded "` + `"reason=non_retryable_terminal"` 两枚子串）。

### 1-2 `terminal.shape` 读数（逐字）

盘上帧账 `%TEMP%\evalrun\run15-sidecar-frames.jsonl`，`id=report-01`（`kind=queued_dead`、
`session_id=12f1046c692740dab075cd2f094e3bb7`、`answer_chars=18`、`sentinel=True`、
`queue.final=dead`、`queue.last_status='dead'`、`polls=50`、`interval_ms=3000`）里那一格：

```json
{"shape": "no_keys", "usage_present": false, "approval_present": false, "schema": null, "state": null, "answer_present": null, "answer_is_park_notice": null, "worker_status": null, "sources_present": null, "sources_n": null, "sources_error": null, "scope_reason_code": null, "usage": null, "approval_steps": null, "approval_ledger_status": null, "approval_notice_chars": null, "terminal_note": null}
```

`answer_chars=18` 就是哨兵 `<no-bytes-emitted>` 的长度。**服务端在这一枚终态上压根没交这批键**，
量具只能把十六枚槽全记成 null。同文件里 `report-02`／`report-03` 两枚成功行是
`shape=structured`／`schema=queue-terminal-v1`／`usage_present=true`——这一族今天一个字没动（判据②）。

## 二、现网那枚单子的 Redis 现取（只读，未改一个字节）

口令只从未跟踪 `deploy/.env.server` 的 `REDIS_PASSWORD`（长度现读 **32**）取，一律
`docker exec -e REDISCLI_AUTH=<pw> enterprise-brain-redis-1 redis-cli --no-auth-warning ...`。
🔴 没有用 `EB_EVAL_PASSWORD`（那是 evalbot 的账号口令，拿它连 Redis 会 `WRONGPASS` 后读出假零）。

```
KEYS enterprise-brain:tasks:*:a55ef916eb43486789a9a68f81cb9f7c
→ enterprise-brain:tasks:message:a55ef916eb43486789a9a68f81cb9f7c
→ enterprise-brain:tasks:status:a55ef916eb43486789a9a68f81cb9f7c          # 只有这两枚键
GET  ...status... → "dead"        STRLEN ...status... → 4
GET  ...message... 解出的顶层键 → ['attempts','enqueued_at','last_error','payload','request_id','reserved_at']
     last_error = 'context_limit_exceeded'      attempts = 1
     payload.task_type = 'ask'   payload.message = '生成本月差旅费用分析周报'   payload.lane = 'report'
     payload.username = 'evalbot'  payload.principal.roles = ['admin']
```

生产那枚行**一个字都没被改**：本班全部验证走自建键名（`r585-*` / `idem-r585-*` / `idem-docquote`）
与 FakeRedis 影子对象。

## 三、定位：对派工词的一处订正，以及真缺的两格

派工词写「message 键……**没有 `last_error`**」——**现取不成立**：它有，值就是 `context_limit_exceeded`。
所以「持久面完全没记原因」这个描述要收窄。真缺的是**两格**，两格都在本单写域里：

- **(a) 可读面缺整批终态键**。`app/api/v1/chat.py:5290` 那支 `if status in (AWAITING_APPROVAL, "done")`
  是唯一会交 `terminal_*` 那一族键的入口，`queued` 只交 `position`、`processing` 只交
  `stream_pieces`，而 `dead`／`cancelled`／`failed` 一律零键。成因明明在账上（甚至在**同一枚响应**的
  `failure.last_error` 里），屏上那一枚读数的名字却不叫 `state`、也没有 `reason`，量具与前端都只能记
  「这一枚状态下服务端没说话」→ `no_keys` → 哨兵。**这就是 18 个字的客户可见后果。**
- **(b) 持久面缺那枚终局判定**。`fail_or_retry` 收了 `retryable` 这个关键字（R81 立、R448 消费），
  却只在**日志行**里把它说出去，账本上不留。判据③ 要「不可重试」与「可重试」两种 dead 分得开，
  而**从计数器反推必错**：一枚 `attempts==max_attempts` 且 `retryable=False` 的行，与一枚
  `attempts==max_attempts` 且 `retryable=True` 的行，在 `attempts`／`max_attempts` 上逐字相等。

落点因此正好两处，`deploy/queue_worker.py` **一字未动**（原因码与终局判定本来就在那一头算好了，
本单不重算、不第二把尺）：

1. `app/common/reliable_queue.py:558 fail_or_retry()` —— 真落 dead 的那一次，把
   `{"reason": <交给队列的原始文本>, "retryable": <调用方的终局判定>}` 记进 message 账本的
   `dead_verdict` 那一格（`:587`），且**在写状态键之前**写完；新读法 `:628 dead_verdict()`。
   账本读不到（message 键不在位）仍旧一个字节不盖，与 `_record_discard` 同一口径。
2. `app/api/v1/chat.py:5302`（`queue_status` 新增的 `elif status == reliable_queue.DEAD_STATUS` 分支）
   → `:5132 queue_dead_readout()`。交回 `terminal_schema=queue-dead-v1`、`terminal_state=dead`、
   `reason`、`retryable`、`answer_present`、`terminal_note` 六格。

影子读数（同一台 `report_failure_record` + `_fail_report_turn` 链路跑出来的，11:19 现取）：

```
{'terminal_schema': 'queue-dead-v1', 'terminal_state': 'dead', 'reason': 'context_limit_exceeded',
 'retryable': False, 'answer_present': False,
 'terminal_note': '队列判定这一枚失败重试也不会变，首发即落 dead，没有占用重试名额。'}
```

## 四、改动清单（写域点名，逐枚 sha256 前 12）

| 文件 | numstat(+/-) | sha256 前12 | 这一枚做什么 |
|---|---|---|---|
| `app/common/reliable_queue.py` | 35/1 | `D719AB0AE32C` | 持久面：`fail_or_retry` 落 `dead_verdict`；新 `dead_verdict()` 读法；三枚常量 `DEAD_STATUS`／`DEAD_TERMINAL_SCHEMA`／`DEAD_VERDICT_LEDGER_KEY`（`:96`、`:98`、`:100`） |
| `app/api/v1/chat.py` | 44/0 | `69BEED879B3E` | 可读面：`STABLE_ERROR_CODES`（枚举投影，`:5126`）＋ `DEAD_REASON_FALLBACK`（`:5129`）＋ `queue_dead_readout()`（`:5132`）＋ `queue_status` 的 `dead` 分支（`:5302`）；另加一枚 `from typing import get_args` |
| `tests/test_r585_dead_terminal_reason.py` | 新件 478 行 | `F50EE8D12FB0` | 25 枚用例（判据①②③④ 全落钉，含三把刀的锚点钉与零 skip/xfail 自检） |
| `docs/testing/r585-dead-terminal-reason-2026-10-03.md` | 本纸 | 见交回盘面段 | 判据⑤ |

字节恒量（本纸自证）：三枚 .py 与本纸一律纯 CRLF、无 BOM、无裸 CR、无裸 LF、无 NUL、无 U+FFFD；
`app/common/reliable_queue.py` CRLF=863、`app/api/v1/chat.py` CRLF=5354、
`tests/test_r585_dead_terminal_reason.py` CRLF=478。

`deploy/queue_worker.py` **未改**（sha256 前12 `9A29A5990F24`，即基点值）。

🔴 **一笔本班事故（照实登记，不改口）**：`chroma_db/chroma.sqlite3` 那枚 ` M` 是**接手前就在
盘面上的既存脏**（本班第一条命令 `git status --porcelain` 就只有它；mtime 10:46:11、当时 sha256
前12 `C43C3E8A950A`），但本班 11:19 为取判据⑤ 那句日志原文跑了一枚**绕开 pytest/conftest 的
临时件**（`$env:TEMP\r585work\quote.py`，只为 `import app.api.v1.chat` 走一次
`report_failure_record` + `_fail_report_turn`），那一腿没带上 R134 那枚「把 PersistentClient
落点改道出工作树」的闸门，于是**又写了这台工作树的 chroma**：现读 mtime 11:19、size 6,262,784 B、
sha256 前12 由 `C43C3E8A950A` 漂成 `71431BC7237A`。HEAD 那枚 blob 是 `be3674cd`，本班**没有**
`git checkout --` 回去——回去会把接手前那笔既存脏一起抹掉，而那既不属本单写域、也不该由本单
决定；并树时 `chroma_db/**` 一律不取即可（它本来就不在写域里）。同批六次 pytest 各自都记着
`PersistentClient 调用: 1 次，其中落点被改道出工作树: 1 次` 与 `工作树 chroma_db 写回告警用例: 0 枚`，
所以这笔漂移只来自那一枚临时件——本纸收笔前又复跑一批 pytest，那一枚 sha256 仍旧是
`71431BC7237A`（纹丝不动）。教训一句话：**取证脚本一律走 pytest 那套夹具，别裸 import。**

## 五、判据五格逐条

### ① 死终态在可读面交回 `state=dead` ＋ 一枚**在册**稳定码 —— **达标**

- `reason` 的词表**不是本单造的**：`STABLE_ERROR_CODES = frozenset(get_args(ErrorEnvelope.model_fields["code"].annotation))`
  是从 `app/agents/contracts.py:588` 那枚封闭枚举派生的投影（唯一真源，与
  `app/agents/evidence.py:21 _enum_error_codes()` 同法，不抄第二份手抄码表）。
  `test_the_fallback_is_the_one_registered_code_and_no_new_code_lives_in_the_readout` 里
  `chat.STABLE_ERROR_CODES == frozenset(ENUM_CODES)` 逐字对账（`ENUM_CODES` **借自**在册件
  `tests/test_r81_queue_terminal_retry.py`，本纸不复制）。
- 兜底那枚是 `internal_error`（枚举成员，`app/agents/contracts.py:639`），认不出枚举就折到它，
  **原文一个字不丢**：同一枚响应的 `failure.last_error` 仍旧是账本原文。十枚形状的读数由
  `test_the_reason_is_a_registered_code_for_every_ledger_shape` 逐枚钉：在册四枚
  （`context_limit_exceeded`／`model_unavailable`／`queue_unavailable`／`internal_error`）原样交回；
  不在册的（`lease_expired`、`authorization_required`、`no_model_call_recorded`、
  `result_discarded:lease_lost`、裸异常文本、空串）一律 `internal_error`。
- 面上那枚 `state` 的名字：`terminal_state="dead"`，**逐字回显**状态键上那枚词
  （`"terminal_state": status,`，全仓仅此一处这种写法），不在读侧第二次拼写它。
- 点名的尺已跑：`tests/test_error_code_vocabulary.py` → **全绿**（见第六节批次 B）。
  本单**零新增码**：`RATIFIED`／`DEFERRED_CODES`／`BARE_CODES_OUTSIDE_THE_ENUM` 三张表一行没动，
  `contracts.py` 枚举行也没动——那正是「禁新造码」的可执行形状。

### ② 成功终态形状一字不改 —— **达标**

- `build_queue_terminal()` 与 `queue_terminal_readout()` **一个字节未改**（diff 里那 44 行全在
  新函数、两个常量、一枚 import 与 `dead` 分支上）。
- 两把冻结钉：`list(payload) == SUCCESS_TERMINAL_KEYS`（十枚，含 `dataset_files` 时末格
  `data_filename`）与 `list(body) == DONE_RESPONSE_KEYS`（`done` 响应十六枚，顺序逐字）。
- `dead` 那一支只在 `elif` 上说话：`test_a_done_answer_still_answers_the_frozen_key_sequence`
  额外钉 `"reason" not in body` 与 `"retryable" not in body`——新格不许往成功形状里漏。
- 反向也钉：`test_the_dead_readout_invents_no_source_usage_or_approval_slot` 钉死终态**不抄**
  `sources`／`usage`／`approval`／`worker_status`／`scope_reason_code`／`result` 那一族空值
  （R254 口径：交空表就是把「没说」洗成「说了零」）。

### ③ 不可重试与可重试两种 dead 分得开 —— **达标**

- `retryable` 那一格**沿用 R448 的口径**：它是调用方交给队列的关键字（`is_non_retryable_error`
  只认显式 `error["retryable"] is False`），本单把它原样冻进 `dead_verdict`，不重新判定、不从
  `attempts` 反推。
- 最硬的一枚是 `test_two_deads_with_identical_counters_stay_tellable_apart`：两枚
  `attempts=1 / max_attempts=1` 的 dead，`failure` 那一格**逐字相等**，面上仍交回
  `retryable=False` 与 `retryable=True` 两种读数、两枚不同的 `terminal_note`。
- 持久面直读：`test_the_verdict_lands_on_the_durable_face_verbatim` 解 message 键原文，钉
  `{"reason": "context_limit_exceeded", "retryable": False}`，并钉 `last_error` 那格没被搬走。
- 「还在重投的这一轮不是终态」：`test_a_failure_that_is_still_retrying_records_no_terminal_verdict`
  钉 `status=queued` 时 `dead_verdict` 那格**压根不写**。
- 旧行不假造：`test_a_row_recorded_before_this_change_says_the_reason_but_not_the_verdict`
  （HTTP 走真路由）复现生产 `a55ef916…` 的形状——剥掉 `dead_verdict` 后面上仍读得到
  `reason=context_limit_exceeded`，而 `retryable` 交回 `null` 并明写「这一行落在 R585 之前」，
  **不拿 False 冒充不可重试**。

### ④ 反证三把 —— **达标**（各交摘前/摘后 sha256 前 12）

摘改一律由临时脚本 `$env:TEMP\r585work\knives.py` 完成，每把刀跑完**立刻复原**并核 sha256 等值；
生产码里不留任何摘改痕迹。三枚锚点由
`test_the_three_counter_evidence_anchors_are_still_in_place` 逐字钉在位（锚一漂刀就砍空）。

| 刀 | 下刀处 | 摘前 sha256 | 摘后 sha256 | 复原后 | 红的钉 |
|---|---|---|---|---|---|
| K1 摘掉 reason 装配 | 删 `chat.py` 里 `"reason": raw if raw in STABLE_ERROR_CODES else DEAD_REASON_FALLBACK,` 一整行 | `69beed879b3e` | `db17ef0a51c3` | `69beed879b3e` ✓ | **17 failed / 8 passed**（判据① 全族：`test_a_dead_turn_now_speaks_its_reason_on_the_polling_surface`、十枚词表形状、`test_a_dead_row_without_a_verdict_...`、`test_a_broken_ledger_...`、`test_two_deads_...`、`test_a_row_recorded_before_...`、锚点钉、`test_the_dead_readout_invents_no_source_...`） |
| K2 在册码换成现编字符串 | `DEAD_REASON_FALLBACK = "internal_error"` → `"queue_dead_uncoded"` | `69beed879b3e` | `c4e05c40919e` | `69beed879b3e` ✓ | **9 failed / 16 passed**（含字面量钉 `test_the_fallback_is_the_one_registered_code_and_no_new_code_lives_in_the_readout`：`DEAD_REASON_FALLBACK == "internal_error"`、成员资格、R585 段字面量集合 `== {"internal_error"}` 三头都红） |
| K3 成功终态多塞一键 | `build_queue_terminal` 的 payload 里在 `approval` 之后插一枚 `"worker_note": ""` | `69beed879b3e` | `d36cd5485c57` | `69beed879b3e` ✓ | **4 failed / 118 passed**：本单的 `test_the_success_terminal_payload_key_order_is_frozen`，**另两枚是别人家的在册钉**——`tests/test_r254_sync_lane_terminal.py:162::test_the_two_lanes_share_one_readout_key_set`（两道键集合必须逐名相等）与`tests/test_r504_terminal_frames_carry_data_filename.py:201::test_the_pinned_queue_key_set_is_untouched_when_nothing_was_read`；再加本单的锚点钉 |

K3 的红不止在本单：在册那两枚（两道键集合相等、零读时键集合不动）**同样咬红**，说明这格形状本来
就有两道钉，本单没有把它稀释。

### ⑤ 交工纸逐字引日志与 `terminal.shape`，并明写不治窗口 —— **达标**

本纸第一节两条逐字引（含盘上帧账那枚十六槽 JSON 原文）、第〇节写死「本单不治窗口参数，
R586 才是」。

## 六、命令原文 → rc → 末行读数（执行层自报）

解释器一律 `C:/Users/fengx/PycharmProjects/企业智脑/.venv/Scripts/python.exe -X utf8`
（Python 3.11.7），参数一律 `-o addopts= -p no:cacheprovider --basetemp=... -q`。
**未跑全量门 `scripts/run_gate.py`（本单禁止）**；未打模型；未 `git add/commit/push`；容器侧只做了**只读**取证（`docker exec … redis-cli KEYS/GET/STRLEN`、`docker logs`），未 recreate、未重启、未写任何一枚键。

| 批次 | 目标 | rc | 末行 |
|---|---|---|---|
| A（本单钉） | `tests/test_r585_dead_terminal_reason.py` | 0 | `25 passed, 14 warnings in 5.41s` |
| B（尺与形状） | `tests/test_error_code_vocabulary.py` `tests/test_r254_queue_terminal_honesty.py` `tests/test_r254_sync_lane_terminal.py` `tests/test_r232_queue_status_vocabulary_sync.py` `tests/test_reliable_queue_status_api.py` `tests/test_reliable_queue.py` | 0 | `129 passed, 60 warnings in 12.61s` |
| C（队列与终局判定） | `tests/test_r81_queue_terminal_retry.py` `tests/test_r448_deterministic_refusal_no_retry.py` `tests/test_r578_queue_lane_reports_the_failure_terminal.py` `tests/test_r578_counter_evidence_teeth.py` `tests/test_r548_queue_lane_registers_the_piece_sink.py` `tests/test_r227_discard_is_honest.py` `tests/test_r227_lease_heartbeat.py` `tests/test_r142_error_code_table_sync.py` | 0 | `128 passed, 14 warnings in 20.42s` |
| D（读面／归属／报告腿） | `tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py` `tests/test_r259_terminal_readout_lands_in_the_book.py` `tests/test_r295_queue_owner_readback.py` `tests/test_r37_report_lane_worker.py` `tests/test_r504_terminal_frames_carry_data_filename.py` `tests/test_r514_queue_worker_passes_dataset_files.py` `tests/test_r132_contract_followup_sync.py` `tests/test_r561_readout_calibre_and_teeth.py` `tests/test_r222_queue_terminal_stopwatch.py` `tests/test_r447_queue_approval_round_and_evidence.py` | 0 | `243 passed, 50 warnings in 23.80s` |
| E（三把刀） | 见第五节④ 表 | 各自 rc=1 | `17 failed / 8 passed`、`9 failed / 16 passed`、`4 failed / 118 passed`，复原后 sha256 逐把等值 |
| F（文档三本账） | `tests/test_r585_dead_terminal_reason.py`（复跑） `tests/test_r302_docs_utf8_guard.py` `tests/test_r408_docs_say_what_the_tree_does.py` `tests/test_r398_three_guard_ledgers.py` ＋ `scripts/check_no_bom.py` | 0 / 0 | `56 passed, 16 warnings in 14.06s`（收笔前复跑同数：`56 passed in 18.98s`）；`check_no_bom: scanned 1370 tracked text file(s)` 全绿（2 枚既存白名单，与本单无关） |
| G（同写域相邻在册件） | `tests/test_r194_queue_denials_and_flat_list.py` `tests/test_r199_anonymous_probe_audit.py` `tests/test_r181_text_frame_ruler.py` `tests/test_r229_connect_retry.py` `tests/test_r524_queue_lane_sends_no_second_character.py` `tests/test_r384_migrations_first_refuses_at_the_ask_exit.py` `tests/test_r456_error_round_is_not_an_answer.py` `tests/test_public_contracts.py` `tests/test_agent_result_records.py` `tests/test_r155_queue_capacity_readout.py` | 0 | `152 passed in 20.21s` |

上面 A–G 全是**脏态**（本单改动已 apply、未 commit）读数。批次 B/C/D/G 合起来 **652 枚在册用例**（129＋128＋243＋152）、
加本单 25 枚 = **677 枚，0 failed**（批次 F 里那 25 枚是复跑，不重复计数）。🔴 第二遍（干净树复跑同名件）按仓规是总控并树后的动作，
执行层不得 commit，所以本班交不出那一遍——这一格照实挂在第七节。

## 七、未验格（照实，不写达标）

1. **干净树复跑未做**：执行层禁 `git commit`，AGENTS.md 那「两遍数字」的第二遍只能由总控并树后
   亲自复跑同名 A–G 七批。本纸第六节所有数字一律是**执行层自报**、且一律是脏态。
2. **真机端到端未验**：改动还没进容器（禁动容器／禁重建镜像）。所以「现网那枚 `a55ef916…` 打上
   新代码后 `/queue/status` 会读出 `reason`」这一条只有**影子链路 + FakeRedis 的等价证明**，
   没有现网 HTTP 读数。🔴 并且它**永远不会**自己变好：生产那一行是**在位旧行**，账上没有
   `dead_verdict`，翻上新代码后读到的会是 `reason=context_limit_exceeded` ＋ `retryable=null`
   （第三、五节那枚旧行钉钉的就是这个形状），不是 `retryable=false`。
3. **`terminal.shape` 会翻成什么未复量**：按 `scripts/eval_transport_ask_v2.py:1003 _terminal_shape`
   的读法，本单之后 `dead` 行的 `terminal_schema`／`terminal_state` 都不再是空 ⇒ 形状从
   `no_keys` 变成 **`structured`**，而 `sources_present`／`sources_n`／`sources_error` 三枚仍读回
   `null`（键不在位，**不是** 0/空表），`usage_present=false`。这一格是**推出来的**，要在下一个
   跑分窗（run16/17）现读才算数；量具与 D 格判绿口径不在本单写域，未改。
4. **前端后果未验**：`frontend/**` 禁碰。屏上那枚 `<no-bytes-emitted>` 哨兵**今天仍然会显示**——
   面上有了 `reason`，前端读不读是另一格（转出项见第八节）。
5. **`cancelled`／`failed` 两类没接**：判据只钉 `dead`。同一支路由的 `cancelled` 今天仍旧零键
   （同一个病族的另一格），本单不顺手扩，免得把写域撑进别人的钉。
6. **`attempts` 那一格本单没动，只澄清读法**：账面数由 `reserve()` 抬（`app/common/reliable_queue.py:292`），`fail_or_retry` 一个字都不抬——所以日志里 `attempts=1 max_attempts=3` 说的是「本轮是第 1 发、还留 2 个名额」，**不是**「已重投 1 次」。
   本单把 `retryable` 记进账本，正是为了让这枚计数与那枚终局判定各说各的话；影子复现里 `attempts` 逐字仍是 1（未验的是：现网那一台翻上新代码后的日志读数）。

## 八、转出项（不在本单写域，登记给别人）

- **契约未同步**：`docs/api/contract-v1.md` 不在本单写域。`dead` 那一支新增的六格
  （`terminal_schema=queue-dead-v1`／`terminal_state`／`reason`／`retryable`／`answer_present`／
  `terminal_note`）目前只有代码与本纸两处记着。要落契约请点 `## Long Task Status` 与
  `### Structured terminal readout (2026-09-25, R254)` 两节，并注意
  `tests/test_r232_queue_status_vocabulary_sync.py` 那枚 AST 同步钉（它只跟踪 `status` 键的字面量
  写入，本单没加新状态词，所以它今天绿）。
- **前端**：`frontend/src/components/ChatPanel.vue::QUEUE_SETTLED` 那族停表名单读到 `dead` 时，
  现在**有的读了**（`reason` 与 `terminal_note`）。要不要把它画成一句人话，属前端席位。
- **同一病族另两格**：`cancelled`、以及现网那枚在位旧行的 `retryable` 缺席，见第七节 2／5。
- **R586 已并树 `9c9a0b1`**：窗口参数这一格由它负责，本纸不重复判绿。