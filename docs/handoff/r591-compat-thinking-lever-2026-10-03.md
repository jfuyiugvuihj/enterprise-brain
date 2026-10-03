# R591 · 报告档空正文：兼容腿的关闭思考字段、换腿具名、三格常驻钉

工单：R591（P1）。执行层独占树 `be-r591`，基点 `245315b`。本文只写这一单看见的东西。

签名约定：**[实测]** = 本单在这台机上亲手跑出来的读数（含秒数与 token 数）；**[算术]** = 由[实测]读数直接算出；
**[现读]** = 从在册文件/库里现取的记录，不是转述；未标者 = 代码事实（行号可点）。

## 一、判据① · 每一发的 transport 账

先说结论：**「批准/恢复腿撞上 400 静默退回 compat」这条机制假设被否掉了**，而且是在它自己的量具上否掉的。

取证面两面：

- 服务端那一面：`docker logs --since 2026-10-03T10:45:00 --until 2026-10-03T13:30:00 enterprise-brain-ollama-1`
  → `%TEMP%\evalrun\run1617-ollama.log`（8.1 MB），逐枚 GIN 行解析 **[现读]**。窗口内 POST：
  - `"/api/chat"`（原生腿）192 发，**全部 200，4xx = 0**；
  - `"/v1/chat/completions"`（兼容腿）646 发，641×200 + 5×500，**4xx = 0**；
  - `"/api/embeddings"` 1139 发（与本单无关，列出来是为了说明这份账是全集不是挑的）。
  ⇒ `NATIVE_REQUEST_REJECTED_STATUSES = {400}` 那条退回**在 run16/run17 一次都没发生过**。
  「哪一类请求体触发 400」这个问题的正确答案是「没有」：批准的 chart 腿根本没有走到原生端点，
  所以也就不存在一枚被拒收的体。
- 产品那一面：`model_calls` 548 行（只读取 `%TEMP%\evalrun\r591_model_calls.csv`）逐行按完成时刻 ±5 s
  配到上面那 1977 枚 GIN 行 **[算术]**（脚本 `%TEMP%\evalrun\r591_ledger5.py`，逐行读数在本文§一末）：
  - 528 completed / 15 failed / 5 model_unavailable；
  - 20 枚非 completed 轮**全部**配到 `"/v1/chat/completions"`，**一枚都没有**配到 `"/api/chat"`。

20 枚逐发账（UTC；worker 取自 `model_calls.metadata->>'worker'`，`\N` = 那一格没装东西）：

| started→completed | status | error_code | worker | in / out tok | 服务端那一发 |
|---|---|---|---|---|---|
| 02:50:53.791→02:51:32.673 | failed | no_answer_produced | \N | 796 / **1536** | compat 172.18.0.8 @02:51:32 |
| 03:42:18.408→03:42:58.371 | failed | no_answer_produced | \N | 764 / **1536** | compat 172.18.0.5 @03:42:58 |
| 05:03:15.974→05:03:56.118 | failed | no_answer_produced | \N | 792 / **1536** | compat 172.18.0.6 @05:03:56 |
| 04:08:00.549→04:08:08.970 | failed | no_answer_produced | data | 7948 / 244 | compat 172.18.0.5 @04:08:08 |
| 04:14:37.158→04:14:41.665 | failed | no_answer_produced | data | 8091 / 101 | compat 172.18.0.5 @04:14:41 |
| 04:17:36.597→04:17:38.517 | failed | no_answer_produced | data | 8149 / 43 | compat 172.18.0.5 @04:17:38 |
| 04:23:33.760→04:23:39.018 | failed | no_answer_produced | data | 8046 / 146 | compat 172.18.0.5 @04:23:39 |
| 04:38:22.484→04:38:29.010 | failed | no_answer_produced | chart | \N / \N | compat 172.18.0.5 @04:38:29 |
| 04:41:59.721→04:42:09.103 | failed | no_answer_produced | chart | \N / \N | compat 172.18.0.5 @04:42:09 |
| 04:47:44.898→04:48:00.291 | failed | no_answer_produced | chart | \N / \N | compat 172.18.0.5 @04:48:00 |
| 03:02:58.852 / 03:58:27.773 / 04:37:30.410 / 04:44:46.538 / 05:21:24.299 | failed | internal_error | data×4, chart×1 | \N / \N | compat，各在 0–1 s 内 |
| 上面那 5 枚之后 0.4–0.7 s | model_unavailable | model_unavailable | 同 worker | \N / \N | compat（离线回复那一发） |

三行 `out=1536` 就是报档那一形：`app/agents/orchestrator.py:473 main_model.invoke([sys_msg, current_user_msg])`，
`main_model` 在 `app/agents/orchestrator.py:272` 由 `_make_model(ModelTier.ANALYSIS).bind_tools([dispatch])` 造出来 ——
**一条兼容腿**，工具那一发不是原生 `/api/chat`，也不是「原生被拒后退回」。
三行 `worker=chart` 的空正文（04:38:29 / 04:42:09 / 04:48:00）与 run17 侧车那三枚批准失败
（`chart-01` / `chart-02` / `chart-04`，`approve_http_status:200` 而「恢复流里没有 text 事件」）同一时刻同一名册：
批准返回 200，恢复腿照常问了一发，服务端答了，正文是零。
四行 `worker=data` 更直白：`out` 分别 244 / 101 / 43 / 146 token，**可见正文仍为 0 字** —— 预算没吐满也会空，
所以「1536 全吃满」只是这一族的一个特例，不是它的定义。

读得出与读不出：这一层今天**只能靠 join 外部日志**反推腿。产品侧唯一自报腿的读数在
`app/common/model_handler.py:617`（`[Model] ollama-native 应答: ... content_chars=... thinking_chars=...`），
而兼容腿从头到尾没有一个字说自己是谁。**这就是本案真正没被钉住的那一格**，判据③ 的第二半补它。

一台机三个内网 IP（172.18.0.5 / .6 / .8）分别发了 495+118、96+43、55+31 枚；backend/worker/scheduler 共用
同一枚镜像，而 13:47 那次 `--force-recreate` 之后没留 IP→容器名册 **[现读-限制]**，
所以本文不把 IP 认成容器 —— 腿的判定不依赖它（每条 IP 上都既有 compat 也有 native）。

## 二、判据② · compat 腿在思考模型上必然空正文

总控 14:0x 三臂 **[实测]**（`%TEMP%\r591-probe.txt`）：

| 臂 | 秒 | finish | content | reasoning | generated |
|---|---|---|---|---|---|
| compat + `thinking:{type:"disabled"}` | 73.49 | length | 0 | 5554 | 1536 |
| compat 不带该字段 | 53.36 | length | 0 | 6041 | 1536 |
| native `/api/chat` + `think:false` | 12.35 | stop | 804 | 0 | 486 |

本单 14:2x 补四臂 **[实测]**（`%TEMP%\evalrun\r591-compat-lever.txt`，同一容器同一模型 qwen3.5:9b，
经 `Get-Content -Raw | docker exec -i enterprise-brain-backend-1 python -` 跑，量具
`%TEMP%\evalrun\r591_compat_lever_probe.py`）：

| 臂 | 秒 | finish | content | reasoning | generated |
|---|---|---|---|---|---|
| compat + `reasoning_effort:"none"`（cap 1536，同时带 `thinking`） | 8.48 | **stop** | **572** | **0** | 338 |
| compat + `reasoning_effort:"none"`（cap 96，只带这一枚） | 7.91 | **stop** | 14 | 0 | 10 |
| compat 什么都不带（cap 96） | 2.65 | length | 0 | 329 | 96 |
| compat 只带 `thinking:{type:"disabled"}`（cap 1536，总控臂 1 的复跑） | 37.86 | length | **0** | 5675 | 1536 |

两张表合起来只说一句话：**分岔不在那枚字段，在端点**。
`thinking` 在 `/v1` 上是惰性的（第四行复跑与总控第一行同形，73.49 s vs 37.86 s 的差是服务端当时冷不冷，
不是正文差 —— 两枚都是 0 字）**[算术]**；`reasoning_effort` 是这条腿唯一读进去的那一枚，带上它就
`finish=stop` + 正文非空 + reasoning 归零。原生腿 `think:false` 仍然最快最省（12.35 s / 486 tok vs 8.48 s / 338 tok
同形出正文），但换端点不是本案必需的修法（见§三）。

## 三、判据③ · 修法（两处都做了，由§一 的证据选）

§一 把「400 静默换腿」证否了，所以本案的病不是腿被换错，而是**这条腿从来没问过它该问的话**。
据此做的不是端点迁移（那要把 LangChain 的流式与工具一发都重写，且原生腿会把思考链直接流进客户窗口，
`app/common/model_budget.py` §42/R29 那两笔已经量过这个代价），而是：

1. **兼容体带上端点真读的字段**（`app/common/model_budget.py`）：`disabled` 那一档的
   `ThinkingPolicy.wire` 现在是两枚字段 —— `thinking:{"type":"disabled"}`（R100 钉过的字节，留着）
   **加** `reasoning_effort:"none"`（本案的新增，`REASONING_EFFORT_REQUEST_FIELD` /
   `REASONING_EFFORT_DISABLED_VALUE`）。发问腿与恢复腿共用 `_ResilientModel`，两腿都从
   `nodes.py:_with_boundary_fields` / `_budget_kwargs` 拿这一枚片段，所以**一处改，两腿同带**；
   第二条兼容出口 `app/common/model_handler.py`（rewrite / 非流式退回那一发）原先只带 `keep_alive`，
   现在也带同一枚片段 —— 这一枚是「腿不退役但一发退回 compat」那条路真正会踩到的洞。
   `MODEL_THINKING=enabled` 仍然一个字都不发（= R100 之前的字节），所以运维手里只有一枚旋钮，
   而它是本案新字段的退路。
2. **换腿与拒收都必须具名，不许静默**：
   - `{400}` 退回兼容腿现在除 R147 的实例读数之外，还进**全进程账**
     （`record_budget_event("native_body_rejected")`，随 `model_budget_readout()["events"]`
     经 `app/common/monitoring.py` → health 快照 publish 出去），那一行日志同时带上
     `no_think_fields=` 与 `transport=`；
   - 空正文那一行（run16/run17 事后唯一读得到的两行之一）现在写明
     `transport=openai-compat no_think_fields=thinking|reasoning_effort`，
     「我们没问」与「我们问了而这台机没答」从此不共享一行日志；
   - 新增一枚码 `LEVER_REJECTED_CODE = "thinking_lever_rejected"`（`app/common/model_budget.py:
     lever_rejection_code`）：服务端因为这两枚字段拒收时（`does not support thinking` /
     点名 `reasoning_effort` 那一族句子），两条边界都打这一枚码、进 `lever_rejected` 计数、
     并把名字写进 span 的 `summary.lever_rejection_code`。**裁定一个字都不改**：仍然是离线回复、
     仍然 `model_unavailable`、仍然 `failed`。窗口超长那一族继续由 `context_error_code` 先赢。
   - 🔴 没有做任何兜底文案：`app/agents/nodes.py:379-387` 那条原则原样守住，空正文仍然交回空正文
     （`test_an_empty_body_is_never_repaired_with_a_friendly_sentence` 就是替这条原则站岗的，K5 摘刀即红）。
3. **读数**：`model_budget_readout()["thinking"]` 新增 `request_fields`（这一档到底带了哪几枚字段名）
   与 `compat_lever`（`{"field":"reasoning_effort","value":"none"}`），`request_field` 原样保留。

## 四、判据④ · 常驻钉

- `tests/test_r591_compat_thinking_lever.py` —— **24 枚，默认出门，一条真 socket 都不开**。钉：
  请求体形状（invoke 与 stream 两形）、字段真落到 HTTP 顶层（`httpx.MockTransport` 抓 SDK 实发的
  JSON，防「langchain 把 extra_body 吃了」这一类稻草人）、`enabled` 两枚都不带、调用方自己写的值仍然赢、
  原生体仍然只有 `think:false` 不被污染、`{400}` 退回进账、拒收字段那一族有自己的码且裁定不变、
  空正文那一行点名腿与字段、空正文不许被成品句掩盖、三格 AND 的读法本身。
- `tests/test_r591_live_thinking_off.py` —— **2 枚真打模型的钉，默认 skip**，门是
  `tests/_live_model.py`（`EB_OLLAMA_ACCEPTANCE=1` 且端点答得出模型名才跑），与
  `tests/test_r540_*` 「离线那半格常驻、真打那半格显式开」同一先例。判据要求的三格在
  `thinking_off_verdicts()` 里是一枚 AND：**正文非空 ∧ reasoning 为空 ∧ finish=stop**，
  失败时点名是哪一格倒的。第二枚只证两格（正文与 finish），因为实测
  `langchain_openai` 1.3.2 把 `message.reasoning` 整通道丢掉 —— 走产品对象根本看不见思考链，
  这一格只能读服务端原始帧；这个限制本身写在文件头上，不藏。
- 两枚件互不重复：常驻件用 `_live_reader()` 把 live 件的读法拿来，用今天两枚**已记录**的服务端帧
  （带字段 / 不带字段）跑一遍，所以「三格 AND」的逻辑在全量门里就是活的，不必为它花 GPU。

## 五、判据⑤ · 反证（逐把「摘哪一把 → 哪枚红」）

| 刀 | 摘法 | 红掉的钉 | 读数 |
|---|---|---|---|
| K1 | 从 `ThinkingPolicy.wire` 删掉 `reasoning_effort` 那一行（回到 R100 那唯一拼法） | 本单 9 枚 + `test_r100` 12 枚 + `test_r34` 1 枚 | 22 failed / 84 passed **[实测]** |
| K2 | 摘掉 `{400}` 退回里的 `record_budget_event("native_body_rejected")`（退回重新变静默） | `test_a_native_400_downgrade_is_counted_not_only_logged` | 1 failed **[实测]** |
| K3 | 把新字段换成 §42 表 #7 那枚惰性拼法（`"think": False`） | `test_the_near_miss_spellings_stay_out_of_both_bodies` | 1 failed **[实测]** |
| K4 | 把三格 AND 放宽成只看正文（删 `reasoning_not_empty` 那两行） | `test_the_inert_field_fails_the_same_verdict_on_all_three_counts` | 1 failed **[实测]** |
| K5 | 用一句客套话掩盖空正文（在 `empty_answer_code` 之前替换 `response.content`） | `test_an_empty_body_is_never_repaired_with_a_friendly_sentence` | 1 failed **[实测]**；那一行日志同时证明码与腿仍被读出 |
| K6 | 摘掉空正文那一行的 `**self._leg_fields()`（不点名腿） | `test_an_empty_answer_line_names_the_leg_and_the_fields_it_sent` | 1 failed **[实测]** |

六把都不是稻草人：K1/K3 摘的是**产品代码里那枚字段**，K2/K6 摘的是**具名那一半**，K4 摘的是**判据的形状**，
K5 摘的是工单明写的禁区。每把都在自己那枚钉上红，且没有一把靠删测试得来。
反证跑完 `git diff --numstat HEAD` 回到原状（已核）。

## 六、跑了什么、没跑什么

- **[实测]** 受影响切片（48 枚在册件，`ModelBudget` / `_ResilientModel` / `extra_body` /
  `no_answer_produced` / `native_leg_readout` / `model_budget_readout` 六个名字全 grep 出来的并集）：
  **956 passed / 11 skipped / 0 failed，62.51 s**，`blocked connect attempts to host model port: 0`。
- **[实测]** 交机时定向复跑（本单新增 2 枚＋改判 2 枚＋同域 6 枚＝10 枚件，见§八）：
  **261 passed / 2 skipped / 0 failed，22.73 s**，`blocked connect attempts to host model port: 0`
  （那 2 枚默认 skip 的是真打件，只有 `EB_OLLAMA_ACCEPTANCE=1` 才打）。
- **[实测]** 全量门 `python scripts/run_gate.py` 两遍，都在本单 dirty 树（apply 未 commit），终态与初值同一串数字：
  - 第一遍（`r591_gate.log` 落盘 15:22:59）：`xdist -n 5 --dist loadfile`，638.24 s，**64 failed / 10323 passed / 58 skipped / 2 xfailed / 2667 warnings**，exit=1；
  - 交机前终态那遍（`r591_gate_final.log` 落盘 16:13:59）：`run_gate` 按空闲内存自选**降成 serial (1 worker)**（报因原文「headroom 3.1 GB is under one worker's 4 GB」，
    同机另有在飞 Agent），1693.62 s（28:13），**64 failed / 10323 passed / 58 skipped / 2 xfailed / 2603 warnings**，exit=1；
    两份 `FAILED` 清单逐枚相等（差集 **0**），也顺手否掉了「64 枚是并发抖出来的假红」这一读法。
- 🔴 **64 枚红没有一枚是本单造成的**，凭据是四态红名单逐枚相等：

  | 取数态 | 跑的件 | 红数 |
  |---|---|---|
  | 本单 dirty 树 | 全量门（10323+64 枚） | 64 |
  | 本单 dirty 树 | 那 11 枚红件单跑 | 64 |
  | **基点 `245315b` 干净工作树**（`git worktree add --detach`，零改动） | 同名 11 枚件单跑 | 64（146.97 s / 186 passed） |
  | 本单 dirty 树（终态，含本纸 §六 补写之后） | 全量门 serial (1 worker) | 64（1693.62 s / 10323 passed） |

  四份 `FAILED` 清单逐枚比对，`Compare-Object` 两两差集 **0**（`%TEMP%\evalrun`，
  文件名 `r591_base_failed.txt`／`r591_dirty_failed.txt`／`r591_gate.log`／`r591_gate_final.log`）。
- **[实测]** 这 64 枚按报因分两族，**处置权都在本单写域之外**，交总控：
  - **族 A · 在册坐标/账本没随上游并树重落地＝61 枚。**
    - 两枚**未入册的裸 `psycopg.connect`**：`app/rag/retriever.py::_read_engagement_rows`（现读 `app/rag/retriever.py:753`，
      随基点这笔 **R46** 进来）与 `scripts/r579_index_crossover_readout.py::Db.open`（现读 `:460`，随 **R579 `e6fdeb4`** 进来）
      ⇒ 棘轮读数 `15 → 17`，红在 `test_r238_bare_connect_ratchet`（14）、
      `test_r346_line_ledger_is_derived_not_copied`（23）、
      `test_r389_r382_connects_go_through_the_boundary`（1）、
      `test_r400_derived_ledger_shift_and_silence_pins`（1）＝ 39 枚。这两处文件的写域是 R60/`Aquinas`（在飞）与已并树的 R579。
    - `app/api/v1/chat.py` 现读坐标比在册文档格 **+1**（个别格 +44），`app/api/v1/feedback.py:56` 那枚新口进了空表分诊账
      ⇒ 红在 `test_r455_gapdoc_coordinates_are_derived`（8）、
      `test_r455_hand_fudged_numbers_and_wrong_layers_both_redden`（3）、
      `test_r387_label_ruler_teeth`（7）、`test_r492_s93_column_matches_derived`（2）、
      `test_r483_empty_table_triage_is_derived`（2）＝ 22 枚。报因自己带路：
      `python scripts/r455_gapdoc_coordinates.py --emit-doc-cells` / `python scripts/r387_label_lineage.py --emit-doc-cells`
      / 生成件 `--sync` 重落地，不许手改数字；最近一笔动 `app/api/v1/chat.py` 的是 **R585 `1f0f0f2`（10-03）**（`[实测]` `git log`）。
      本单一个字节没改 `app/api/v1/chat.py`，也没改那些文档。
  - **族 B · 工作树落盘换行符形态＝3 枚。** `test_r469_readout_is_generated`（2）、
    `test_r256_dataset_version_scope`（1，报因原文「0015 按 LF 落盘：混进 CR 会让 manifest 的 sha256 与磁盘脱钩」）。
    本树是新 `git worktree add` 出来的，`core.autocrlf=true` ⇒ 落盘带 CRLF；现读字节对比：
    `docs/testing/r469-sandbox-scope-readout-2026-09-28.md` 与 `migrations/0015_dataset_version_scope_columns.sql`
    在**本树与基点树都是 CRLF**（244675 / 6011 字节），在**主树是 LF**（237481 / 5932 字节）；这两枚钉拿磁盘字节
    与再生件逐字节对，于是形态即罪证。⇒ `[算术]` **并树回主树后这 3 枚应为绿，预期主树干净态门红数是 61**；
    本单没在主树跑过测试（不属本单写域）。
    在册的归位机制就是 **R531 铺树器** `scripts/r531_worktree_merge.py`：它按「每枚文件各自的行尾惯例」落盘，
    其文档字符串点名的正是这两枚逐字节钉，且它记的数与本次现读**逐位相同**（blob 237481 无 CR vs 盘上 244675）；
    本单交工纸里那些 `:753`/`:460`/`:56` 与§一 的腿行号都是**这一时刻的现读照片**，行号会随上游并树漂移：
    它们是取证记录，不是账本，后续任何钉都不许把它们当坐标来对；并树请仍按 R531 逐枚搬，不许整片拷贝。
- **[实测]** 改判的旧钉两枚（不是弱化，是它们钉的字节已被证伪）：
  `tests/test_r100_thinking_switch.py`（`DISABLED_BODY` 由一枚字段改两枚字段，
  `test_only_the_measured_spelling_goes_on_the_wire` → `..._spellings_...`；文件头把「唯一拼法」那句改成
  本案的六臂读数）；`tests/test_r34_keep_alive_residency.py`
  （`test_residency_is_the_only_thing_either_leg_added` →
  `test_the_two_legs_add_residency_and_nothing_else_beyond_their_own_budget`，另三枚逐字节断言补上新片段；
  原生腿那半边的形状一字未动，那些钉原样成立）。
- **没跑**：
  - 真打模型那一腿（`EB_OLLAMA_ACCEPTANCE=1`）：本案要证的读数已由 8 枚臂（总控 3 + 本单 4 +
    控制臂 1）在花完，再打一次是打模型，不是取证。容器名册与跑法写在§四，总控要收那一格时在
    backend 容器里 `EB_OLLAMA_ACCEPTANCE=1 pytest tests/test_r591_live_thinking_off.py`（宿主
    `127.0.0.1:11434` 会被 R56 闸门拦下，这一腿天然只能在 `OLLAMA_BASE_URL=http://ollama:11434` 那种
    非回环名上跑）。
  - 批准恢复的端到端复现（run18 那一轮评测）：禁区内（动评测集会写数据），只做到了同一时刻同一腿的取证。
  - 任何容器/服务/真库动作：一个都没做，只 `docker logs` 与只读 `psql` 取过数。

## 七、未验风险（如实）

1. `reasoning_effort` 在非思考模型上的行为**没量**（本机 ollama 只装了 qwen3.5:9b / qwen2.5:14b /
   nomic-embed-text；为这一格去加载 9 GB 的第二个模型会动到正在跑别的线的机器，不做）。
   兜住它的不是假设而是具名：那台机若因这枚字段回 400，`thinking_lever_rejected` 会进日志、进计数、进
   span，而裁定仍与今天一致；`MODEL_THINKING=enabled` 是现成的退路。
2. 远程 OpenAI 兼容服务（vLLM 那一类）会不会校验这枚字段，同样没量，同一条兜法。
3. 本案**不解决**「思考模型在 compat 上慢 4–6 倍」这一格：字段带上了只是让正文出得来，
   8.48 s vs 73.49 s 的差里有多少属于字段、多少属于当时机器冷不冷，本文不裁定。
4. run17 三枚 chart 批准失败仍欠一次现复现（本文给的是时刻与腿的对账，不是那一轮的复跑读数）。

## 八、总控验收需要跑哪几枚件

1. 新增两枚：`tests/test_r591_compat_thinking_lever.py`、`tests/test_r591_live_thinking_off.py`
   （后者默认 2 skipped 才是对的）。
2. 改判的两枚旧钉：`tests/test_r100_thinking_switch.py`、`tests/test_r34_keep_alive_residency.py`。
3. 同域在册件：`tests/test_r29_thinking_tax.py`、`tests/test_r92_rewrite_thinking.py`、
   `tests/test_r99_budget_selfconsistency.py`、`tests/test_r147_native_leg_verdict.py`、
   `tests/test_r228_rewrite_slot_wait.py`、`tests/test_r30_model_tiers.py`。
4. 反证钉按规矩**不分层出门**：全量 `python scripts/run_gate.py` 一遍；并树请交两次数字
   （apply 未 commit 的 dirty 态一遍，`git commit` 后干净树复跑同名件再一遍），
   逐枚点名文件清单以 `git diff --numstat HEAD` 为准。
5. 翻默认之外的事本案没碰：`deploy/.env.server`、容器、评测集、`migrations/**` 一字节未动。
6. **门数字请按 §六 的账对**：本单 dirty 树全量门 **64 failed / 10323 passed / 58 skipped / 2 xfailed**，
   64 枚与基点 `245315b` 干净树的红名单**逐枚相等**（差集 0），族 A 61 枚属上游坐标/账本未重落地
   （R46、R579、R585 名下写域），族 B 3 枚是本树 `core.autocrlf` 的 CRLF 形态，回主树应为绿 ⇒ 主树干净态预期 **61 failed**。
   本单没动 `app/api/v1/chat.py`、`app/rag/retriever.py`、`scripts/r579_*` 与那批文档，一字节都没动。
