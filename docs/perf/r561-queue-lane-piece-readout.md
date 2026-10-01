# R561 凭据纸 · 队列道「逐字片段」的容器内读数：量具＋离线钉＋判读口径

- 落笔时刻：2026-10-01 19:26:19（`Get-Date` 现取，不继承任何上游班的钟点）
- 执行层单号：R561（复用 `be-r551` 这棵树）／基点：主树 `codex/data-file-catalog` 现取 HEAD `518314c`
- 本单写域（零越界）：新脚本 `scripts/r561_queue_lane_piece_readout.py`（898 行，sha256 前缀 `275b6c174f44e04f`）
  ＋新钉 `tests/test_r561_readout_calibre_and_teeth.py`（1459 行，sha256 前缀 `fa2b6bb27a2ea0ef`）＋本纸。
  🔴 零 commit／零 push／零动主树／零起容器／零打模型／零网络。`app/**`、`frontend/**`、`deploy/**`、
  `docs/api/contract-v1.md`、`migrations/**`、评测集、看板与跟进单一枚未碰。
- 🔴 **本单只交「能去跑容器那一遍的东西」，不宣布容器那一遍跑过了。** 容器读数是总控在开窗条件满足时代跑并回填本纸。

## 一、来历（为什么不是记账错，而是真欠一格读数）

R558（甲案投递面，已并树 `5477645`）把队列道的逐字片段接到了客户端每 3 s 就在读的
`GET /api/v1/queue/status/{request_id}` 上。它的判据① 只交到「**同进程**真路由真载荷」那一半，
在册凭据纸现取两句：

- `docs/testing/r558-queue-lane-piece-delivery.md:42`——「容器内一次 `REPORT_LANE_VIA_QUEUE=on` 的真机读数**仍欠**，已排进下一次开窗」
- `docs/testing/r558-queue-lane-piece-delivery.md:174`——「判据① 的容器＋真 Redis 读数欠（见上）」

上一班（同一族的前一格）因为把「纸面形状」当成「容器里也这么走」烧掉一整扇窗（run10 作废），
所以这一格不留给纸：量具必须在真回执上跑，且判读必须在**读不到**的时候拒绝交数。

## 二、判据编号映射（🔴 派工词与跟进单的编号不同，本单两处都点名）

派工词 ①–⑤ ↔ 跟进单 `docs/handoff/2026-09-15-backend-followup-requests.md` §143 三（`:4883-4894`）1–5：

| 派工词 | 跟进单 §143 三 | 本体 | 本单怎么落 |
|---|---|---|---|
| ① | 1 与 2 的后半 | ≥3 发 `processing` 且 `state=="ok"` 且 `chars` 递增过／`discarded`＝`truncated`＝0／终态那发不许出现片段键 | 三格：`growing`／`caps_zero`／`terminal_no_pieces` |
| ② | 3 | provenance 逐字符相等才开窗，否则交「落后几枚＋清单」 | `provenance` 格＋`behind_report()` |
| ③ | 2 的前半 | 零 bypass／零 unreadable／零重试逐枚点名，`reason` 只许闭集内三枚 | `zero_bypass_unreadable_retry` 格 |
| ④ | 4 | 离线可自测＋反证 ≥2 把 | 本纸第五、六节（七把刀） |
| ⑤ | 5 | 容器那一遍归总控；执行层不起容器 | 本纸第七节＋未达格点名 |

🔴 差异写明：`discarded`/`truncated` 两枚上限在**派工词**归 ①、在**跟进单**归 2。本纸按派工词行文，两处坐标都印在上面那行里。

## 三、判读口径（六格；每一个字面都由钉现取推导）

口径表本体在契约节 `## Queue lane streaming pieces (R558)`（🔴 只引节名，不引行号）。钉侧的规矩：
**抄来的字面一律现取推导比对**——`tests/test_r561_readout_calibre_and_teeth.py` 里没有一处写死上游的键名、
状态词、阈值数字或 `file:line` 坐标，全部从 `git show HEAD:` 那份字节里当场抠出来再比：

| 口径 | 现取自 | 钉 |
|---|---|---|
| 片段读数九枚键与**顺序** | `app/common/reliable_queue.py::piece_readout()` 里那份 `empty = {…}` 字面键表 | `test_the_piece_key_table_is_derived_from_the_live_readout` |
| 三态 `absent`/`ok`/`unreadable` | 同文件的 `PIECE_ABSENT/PIECE_OK/PIECE_UNREADABLE` | `test_the_three_states_are_the_stores_three_states_and_nothing_else` |
| `reason` 闭集（只三枚） | `piece_readout()` 里 `reason=` 的关键字实参 | `test_the_closed_reason_vocab_is_exactly_the_stores_reasons` |
| 下发片段的唯一状态守卫 | `app/api/v1/chat.py::queue_status()` 里**写了 `stream_pieces` 的那一扇 if** 所比的状态 | `test_the_field_name_and_its_only_guarding_status_are_the_products` |
| 五枚终态＋一枚挂起（停表词） | `scripts/eval_transport_ask_v2.py::_poll_queue()` 与 `status` 作过的比 | `test_the_stop_words_are_the_pollers_stop_words` |
| 三门径（login/ask/approve/status） | 上游那把冻结传输量具走过的门 | `test_the_three_route_doors_are_the_ones_the_frozen_transport_tool_uses` |
| 两枚上限的名字与数值 | `deploy/queue_worker.py::QUEUE_PIECE_LEDGER_LIMIT` 与 `reliable_queue.PIECE_BATCH_LIMIT` | `test_the_two_cap_names_are_the_live_names_and_the_quoted_numbers_are_the_live_numbers` |
| 「至少 3 发」那枚下界 | 在册钉 `tests/test_r558_...py` 里的 `len(seen) >= N` | `test_the_minimum_three_poll_floor_is_the_registered_pin_floor` |
| kind 词表（终账那一族名） | `_poll_queue` 那把量具的 `queued_*` 全族 | `test_the_kind_names_are_all_upstream_names_beyond_the_one_declared_new` |
| 3 s／到点／卡死三枚节奏数 | 上游量具的 `float(os.getenv(...))` 缺省 | `test_the_cadence_numbers_on_the_cli_are_the_upstream_tools_own_readings` |
| 两枚容器名／镜像名／label | `docker-compose.yml` 与 `Dockerfile` 现取 | `test_the_two_containers_the_image_is_made_of_are_named_from_the_compose` |
| `failure` 那一格的键表 | `reliable_queue.py::failure()` 的返回字面字典 | `test_the_readout_reads_only_the_failure_keys_it_claims` |

三态与退出码（🔴 `2` 永远不是通过）：`PASS`／`FAIL`／`UNMEASURED` → `rc=0/1/2`，优先级写死：
任何一格 `UNMEASURED` 存在 ⇒ `rc=2`（**即便同时有 FAIL 也交 2**，理由：一次 FAIL 不许把「这一格压根没量」顶掉，
见 `test_the_rc_ladder_never_folds_a_missing_reading_into_zero`）。

`zero_bypass_unreadable_retry` 那一格内部还有一条：**坏读数优先于量不到**——bypass／unreadable／词表外 reason／
真重试任何一枚在场都是 FAIL（那是量到了的坏东西）；只有「其余都干净、而 `failure` 一发都没带回来」才落 UNMEASURED
（`test_a_genuine_bad_reading_outranks_a_missing_reading`、`test_no_failure_reading_at_all_is_unmeasured_not_zero_retries`）。

🔴 **量不到不等于干净**（P-20 那句）在本单有三处落点：一发片段读数都没取到 ⇒ `caps_zero` 交 UNMEASURED 而不是「两枚上限都是 0」；
这一遍没读到终态那一发 ⇒ `terminal_no_pieces` 交 UNMEASURED 而不是「终态没有片段键」；三条 provenance 路全哑 ⇒ 拒绝开窗并交 UNMEASURED。

## 四、与 R558 在册钉的唯一一处有意不同

R558 那枚同进程钉还断「末发 `text` 非空」。**本单故意不搬这一格**：同进程是逐帧立刻读，容器里客户端每 3 s 才发一发，
`state=="ok"` 而 `text` 为空（那一截里没新字）是契约允许的读数——照搬就会把**节奏差**读成假红。
契约 R558 节原话：`text` 是 "legitimately empty when `ok` and nothing new arrived since the cursor"。
本单改为要求 `chars` 与 `cursor` **两串都各有 ≥3 个不同值、单调、且同涨同停**（`grew_chars == grew_cursor`），
这一格比「末发有没有字」更硬，且不依赖节奏。正身钉：`test_an_ok_face_with_an_empty_delta_is_still_a_real_reading`。

## 五、离线自测四形（现取末行；本单一次容器都不碰）

命令一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8 scripts\r561_queue_lane_piece_readout.py …`，cwd＝`be-r551`。

1. **重放一扇有字的窗**（`--offline`，夹具存档落在 `%TEMP%`，🔴 不落仓）：
   `cell=growing verdict=PASS value={"chars": [3, 6, 9], "cursors": [1, 2, 3], "distinct_chars": 3, "processing_ok_polls": 3} note=递增成立：chars [3, 6, 9] / cursor [1, 2, 3]`
   末行 `[R561] rc=0 headline=PASS`；首行横幅 `[R561] 离线重放：下面六格读的是存档里那一遍记下的东西（provenance 也是当时存的），不是此刻容器里的读数`
   ——这一行是本单加的**防误读闸**：离线重放不许冒充容器凭据（钉：`test_the_offline_entry_replays_a_saved_window_and_answers_the_same_code`）。
2. **存档读不到**：`[R561] rc=2 存档读不出：FileNotFoundError: 存档里没有 polls.jsonl：…（读不到就是读不到，绝不折成「零发」或「都干净」）`，`rc=2`，且**一枚 `cell=` 都不印**。
3. **存档是空的**：`[R561] rc=2 存档读不出：ValueError: 存档是空的（polls.jsonl 零行）：…`，`rc=2`。
4. **生产臂入口给不到环境**（`EVAL_USERNAME`/`EVAL_PASSWORD` 空）：
   `[R561] rc=2 量具没跑成：EVAL_USERNAME/EVAL_PASSWORD 没给（缺凭证不是缺读数，这一遍一枚都没问，绝不交任何一格的数）`，`rc=2`。
   🔴 这条就是「DSN/环境由外面给、给不到就 rc=2 并点名原因」那一格：**量具不许自己把宿主 5432 当生产库**（计划书 §9.4 抓过的那枚假读数）。

## 六、反证刀（判据④ 要求 ≥2 把，本单交七把）

每把都走同一套：原件下那一格必须非 `PASS`（刀有可咬的东西）→ 摘掉守卫后必须被 witness 认出变化（默认＝变成 `PASS`）
→ 点名的 victim 用例必须抛 `AssertionError` → 出窗逐字节复验 sha256 且真树写口记账 0 枚（审计钩 `sys.addaudithook`）。
变异只落**一次性隔离命名空间**，原件字节与活模块都不碰（沿 R253 那条口径）。七枚末行现取（`-k knife -s`）：

```
[R561-KNIFE] G1 摘掉递增判读 victim=test_three_polls_that_never_move_are_red 摘前=FAIL 摘后=PASS outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
[R561-KNIFE] G2 摘掉终态不许带键这一格 victim=test_a_terminal_face_carrying_the_piece_field_is_red 摘前=FAIL 摘后=PASS outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
[R561-KNIFE] G3 把量不到折成 0 victim=test_a_lane_that_answered_nothing_about_pieces_is_unmeasured_not_zero 摘前=UNMEASURED 摘后=PASS outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
[R561-KNIFE] G4 把没入队折成零片 victim=test_a_turn_that_never_entered_the_queue_is_named_bypass_not_zero_polls 摘前=FAIL 摘后=PASS outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
[R561-KNIFE] G5 放开 reason 词表 victim=test_a_reason_outside_the_closed_vocab_is_named_a_new_calibre 摘前=FAIL 摘后=FAIL outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
[R561-KNIFE] G6 没读数也开窗 victim=test_the_head_without_a_provenance_reading_at_all_is_unmeasured 摘前=UNMEASURED 摘后=PASS outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
[R561-KNIFE] G7 停在挂起也算账齐 victim=test_a_window_that_stopped_at_the_park_fails_its_own_bookkeeping 摘前=FAIL 摘后=PASS outcome=RED RESTORED=True 真树写口=0 sha256=275b6c174f44e04f..275b6c174f44e04f
```

G5 那一把特别说明（🔴 不是折中）：摘掉 `reason not in PIECE_REASON_VOCAB` 这一格之后，那一枚判词的 `verdict` **仍是 FAIL**——
因为 `state=="unreadable"` 本身就在场，那是量到了的坏读数，一把摘词表的刀没有权利把它一起抹掉。所以这一把的牙看 evidence：
`invented_reasons` 从「点名了那枚第四字」变成「什么都没点」⇒ 才算咬到（witness `_bite_emptied_the_invented_list`）。

## 七、容器那一遍：开窗条件与总控窗内命令（本席不执行）

开窗条件（四件都要，缺一不开）：

1. `scripts/r530_run10_window_preflight.py` 全绿 `rc=0`（跟进单 §143 三 判据 5 点名的那把尺）；
2. 本量具的 `provenance_gate()` 交 `PASS`（两枚容器的 rev 与主树 HEAD **逐字符**相等）；
3. 容器侧 `REPORT_LANE_VIA_QUEUE=on`；
4. answer cache 清零（否则读到的是上一遍的正文，不是这一轮的增量面）。

总控窗内命令原文（🔴 存档必须落 `docs/perf/raw/r561-<今天>/`，且同目录不许叠第二遍）：

```
python scripts/r561_queue_lane_piece_readout.py --id report-01
python scripts/r561_queue_lane_piece_readout.py --offline docs/perf/raw/r561-<今天>
```

第二遍是**复判**（读同一份存档），不是重新开窗；本席那枚同名钉此后串行复跑一次，交末行。

provenance 那一路的实情（🔴 纸上必须写清，否则就是又一枚「纸面形状当容器形状」）：
`Dockerfile` 只 COPY `app/migrations/scripts/deploy` 并 `RUN printf revision=… > /app/BUILD_INFO`，
所以容器里 `git rev-parse HEAD` **很可能**报 `not a git repository`。那一形既不是「镜像落后」也不是「镜像在位」，
是**这一条路量不到**。量具因此按三条路依次试：容器内 `git` → `/app/BUILD_INFO` 的 `revision=` → OCI label
`org.opencontainers.image.revision`；三条全哑 ⇒ `UNMEASURED` 并**拒绝开窗**。
缩写（7–40 位十六进制）先收下，由 `resolve()` 用 `rev-parse <rev>^{commit}` 解成 40 位**再**逐字符比；
`revision=unknown`（没传 `GIT_SHA` 的旧做法）与 `latest`/`v1.2`/`main` 这种非十六进制串一律读成「量不到」，
绝不让它冒充一枚 head（钉：`test_an_unknown_stamp_is_never_read_as_a_head`）。

两条出口（判据② 点名，措辞与在册口径同源）：

- ✅ 改了 `deploy/.env.server` 要的是**容器重建**：`docker compose --env-file deploy/.env.server up -d --force-recreate`
  ——`env_file:` 在容器创建那一刻才解析，`docker restart` 不重读；这条口径由 `tests/test_r255_env_documents_the_conversion.py:80` 钉着
  （本单的 `test_the_two_remediation_exits_are_the_composes_and_the_r255_calibre` 现取复钉：从 compose 的 `services:` 段逐块读带 `build:` 的服务，
  实取只有 `migrate` 与 `frontend` 两格，`backend` 不在其内）。
- 🔴 不要 `docker compose build backend`：它当场报 `No services to build`（`build:` 只在 `migrate` 与 `frontend` 两格，
  backend/worker/scheduler 三格共用 `migrate` 产出的 `enterprise-brain:local`）。

## 八、口径边界（不越界、不借绿）

🔴 本单不动 C 门那四件判据的任何一个名次。计划书 `docs/handoff/2026-09-17-pgvector-adoption-plan.md` 现取三处：

- `:383`（R547 改口那一格）：「沙盒那一份跨部门/跨密级语料**已经在册并跑过**……它证的是谓词按标签的行为，**不证客户隔离**」
- `:500`：「沙盒 `eb_r59_sandbox`（4×4×252 合成标签）只证行为、**不证客户隔离**，不许拿它替 C 翻绿」
- `:508`（业主原话括注）：「合成标签只证行为、不证客户隔离」

同一句「**沙盒那 252 枚合成标签只证行为、不证客户隔离**」在本单语境里的用处只有一个：别拿任何一份沙盒／离线读数
去顶替容器里那一遍。**投递面（本单）与隔离面（格③）是两本账**：`docs/testing/r558-queue-lane-piece-delivery.md:173`
现取「D 门（报告档 100% 可查回）：仍不翻绿。run11c 相 2 的 `sources_present` 只有 8/12」，`:175` 现取那 4 枚
`approval_failed` 原文逐枚相同——`approve 200 仍无终答：artifact owner must have a department scope`，
那是计划书 §13 格③／业主侧 A1 的账，**不是投递面的账**，本单不据此翻任何一格。

## 九、两态数字

- **dirty 态（本席，已 apply 未 commit）**：见本纸末节现取末行。文件清单三枚：`scripts/r561_queue_lane_piece_readout.py`（新，全 CRLF）／
  `tests/test_r561_readout_calibre_and_teeth.py`（新，全 CRLF）／`docs/perf/r561-queue-lane-piece-readout.md`（新，全 CRLF，无 BOM，结尾有换行）——
  行尾形态由钉 `test_the_new_files_are_crlf_and_unbommed` 在**原始字节**上判（先归一再问「原来是 CRLF 吗」是恒假条件）。
- **干净树那一遍**：🔴 由总控在并树后复跑同名件并回填本节；本席不 commit，也不把执行层读数写成总控亲跑。

## 十、未达格逐枚点名（不许用「基本完成」）

1. **判据①／②／③ 的容器读数：未达**。差的是那扇窗，不是码：
   ① 宿主 `postgres` 与容器读数是两回事，执行层铁规禁 docker；② `enterprise-brain-backend-1`/`worker-1` 的镜像 rev 未经现取，
   `provenance_gate()` 此刻只能交 `UNMEASURED`；③ 开窗前置 `scripts/r530_run10_window_preflight.py` 本席无权执行。
   🔴 这三条都不许写成「库里没有数据」或「跑出来是空集」。按判据⑤，这一遍由总控代跑并回填本纸第五、七节。
2. **判据④ 的两态第二遍：未达**（按规矩由总控在并树后复跑；本席交 dirty 那一遍）。
3. 其余判据（①②③④ 的**形状与判读口径**部分）：达成，末行见第九节与 `git diff --numstat` 交回。

## 十一、自曝（本席亲手写坏的、以及写坏又被钉抓住的）

1. 🔴 **上一席落盘的一枚编码事故**：`scripts/r561_queue_lane_piece_readout.py` 里有 **16 行中文被 here-string 打成了 `?`**
   （`KINDS_WITH_BYTES` 注释块、`judge_bookkeeping` 的 docstring 与两条判词、`main` 里两条 `rc=2` 打印、`summary` 注释块）。
   本席按逐行锚点整块修回（`py_compile` rc=0，全文件 `??` 归零，只剩拼 URL 那枚正当的 `?since=`）。
   后果不止难看：`judge_bookkeeping` 的两条**判词**曾经是问号串——那就是「量具自己说不出它判了什么」。
2. 🔴 **`judge_counts` 认不出 `Path.open("a")` 那一类写口**：写面审计钉原先只看 `args[1]`，把 `self.index.open("a", …)` 的模式位
   漏掉了 ⇒ 「量具只写存档那三处」这条钉当时是**空牙**（摘掉 `open("a")` 也不会红）。本席把模式位改成位置相关的解析
   （`_open_mode()`），钉才真的咬到。
3. **`container_head()` 只认 40 位十六进制**：容器里 `git` 那一读路交回 7 位缩写会被当成「这条路哑了」，接着往下试别的门——
   而钉（`test_an_abbreviated_container_rev_is_resolved_before_the_character_test`）要求的是「缩写先解成 40 位再逐字符」。
   本席改成 7–40 位都收下、由 `resolve()` 解全后再比，并给 `BUILD_INFO`／label 两路加同一形状闸（`rev_shape()`），
   非十六进制的 `latest`/`v1.2`/`main` 从此读成量不到而不是 head。
4. **三条读数路的返回值原先是裸字面**（`"git"`/`"BUILD_INFO"`/`"label"`），钉只能拿 `TOOL.LABEL` 去比一个压根不相等的东西。
   本席把它们收进 `ROUTE_GIT`/`ROUTE_BUILD_INFO`/`ROUTE_LABEL` 三枚常数，并把「下发片段那一态」也收成 `LIVE_STATUS`，
   使钉能拿**量具自己的词**去比产品的词，而不是在钉里抄任何一枚字面。
5. 上一席留下的三笔（本席复核仍成立，未翻案）：自创的第五枚 kind 名 `unreadable_body` 已摘；`summary.json` 双写账已并；
   终账黑名单已改成 `KINDS_WITH_BYTES` 闭集。

## 十二、他席在途问题（只交坐标，不动手）

1. `docs/handoff/2026-09-15-backend-followup-requests.md:4896` 标题里留着一枚未替换的表达式：`### 四、待投队列现状（' + now + ' 现取）`
   ——文本缺陷，跟进单是总控独占写域，本席不改。
2. 主树残留 `app/api/v1/__pycache__/chat.cpython-311.pyc`（在 `.gitignore` 内，`status` 仍零行）；删除属动主树，本席不做。
3. 主树此刻的全量门交回 `13 failed`（`%TEMP%\gate_518314c_run1.log`，18:11:59，`-n 6`，exit=1）：红的是
   `tests/test_r455_*`（坐标族）／`test_r453*`／`tests/test_r449_nested_pytest_basetemp_contract.py`（两枚）／R548 的 z9c／R523 契约——
   全部属他席在途，不是本单的账，本席一枚未碰。


## 十三、容器那一遍的读数（🔴 总控代跑，不是执行层自报）

- **时刻**：2026-10-01 23:38:32 开窗 → 23:41:23 收窗，`rc=0`，`headline=PASS`（`wait_ms` 现取 230,802.9 ms ≈ 3 分 51 秒）。
- **环境**：镜像 `enterprise-brain:local` 重建后 id `8d484a6133dc`，容器 `--force-recreate`（不是 `docker restart`，env_file 只在容器创建那一刻解析）；腿＝默认本机腿 `qwen3.5:9b` @ `http://ollama:11434/v1`；`REPORT_LANE_VIA_QUEUE=on`／`VECTOR_DUAL_WRITE=on`；题＝`report-01`，`final_kind=queued_polled`，76 发轮询，`approval_rounds=0`、`blips=0`、`relogins=0`。
- **一格一句读数**（六格逐格，值取 `docs/perf/raw/r561-2026-10-01/summary.json`）：
  · `provenance` **PASS**——两枚容器的 rev 与主树 HEAD **逐字符等 40**，走的是 `/app/BUILD_INFO` 那二路（`git rev-parse` 在容器里必然 128，`.git` 不进镜像）。
  · `growing` **PASS**——`processing_ok_polls=20`，`chars` 从 21 一路涨到 1490（19 枚互不相同的值，`distinct_chars=19`），`cursors` 同步从 1 推到 23。⇒ **「不许到终态才一次给全」这一格第一次在容器＋真 Redis 上拿到读数**，不再是同进程夹具里的推断。
  · `caps_zero` **PASS**——75 发带片段的轮询里 `max_discarded=0`／`max_truncated=0`，非零发数 0（账本 512／存储 1024 两枚上限都没碰到，这一题的字数远在下限内）。
  · `terminal_no_pieces` **PASS**——终态那一发（第 76 发，`status=done`）键面 16 枚里没有片段键，非 `processing` 的每一发也没有 ⇒ 片段不是第二条流。
  · `zero_bypass_unreadable_retry` **PASS**——`bypass=false`、`invented_reasons=[]`、`retried_polls=[]`、`unreadable_polls=[]`，且 `retry_measurable=true`（三枚都是**量到了**的 0，不是没量）。
  · `poll_bookkeeping` **PASS**——终账 `queued_polled`（有正文那一型），零重登、零闪烁、零审批轮。
- 🔴 **本席在这扇窗上撞了一次在册陷阱并记下来**：第一遍 `docker compose --env-file deploy/.env.server build migrate` **没带 `GIT_SHA`/`BUILT_AT`** ⇒ `/app/BUILD_INFO` 老实写着 `revision=unknown` ⇒ 量具判 `provenance=UNMEASURED` 并**拒绝开窗**（`rc=2`，"量不到不等于干净"）。正解是构建前 `$env:GIT_SHA=(git rev-parse HEAD)`；这条不是缺陷，是设计在起作用——忘传的操作员拿到的是真话 `unknown`，不是一个看着可信的错 hash。
- 还撞了第二枚更普通的：容器刚 `--force-recreate` 完 8 秒就打第一发 ⇒ `RemoteDisconnected`，`rc=2`。正解是先等 healthcheck 翻 `healthy`（`start-period=45s`）再开窗。这两条都进 §五 P-21 那类前置清单，别再让下一班重新发现一次。
- **口径边界（不许越读）**：这一遍只证**形状**（片段在容器里确实逐发递增、终态不带片段、上限没吃刀）。它**不是**时延读数，也不是 A② 的翻绿凭据——同一题在争用机上走了 230.8 s，而此刻本机有 4 枚 Agent 在跑自己的测试、GPU 上还有外来训练进程。A②（88/105）与 D 门（sources_present）两格**仍不翻绿**。
- **结案效果**：R558 判据① 欠的那半张（容器＋真 Redis）与 R561 判据⑤ **同一笔账，两格一并清**。R558／R561 至此没有欠账。
