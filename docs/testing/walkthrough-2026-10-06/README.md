# R694 · 前端九环走查＋两张失败脸（2026-10-06）

🔴 **本纸为总控代纸**：执行层席位 `Archimedes`（树 `be-r694`／基点 `6800b4c`）在旧总控线崩溃时被打断（turn=interrupted），
读数与截图已全部落盘，唯独这张 README 没来得及写。下面每一个数字都由脚本从 `ledger.json`／`defects.json` 派生，
执行层亲取、总控代抄纸——不是总控亲跑浏览器。九环逐环读数采集时段＝2026-10-06T13:21:48+08:00 → 2026-10-06T15:05:46+08:00。

## 环境（派生）

- 被测面 `base_url`＝`http://localhost/`，origin host＝`localhost`。
- 凭据只点名不写值：`primary`, `secondary`。
- 夹具：`C:\Users\fengx\PycharmProjects\be-r694\docs\testing\rehearse-run6-summary.txt`，字节数 8308。
- 后端镜像 `created_utc`＝2026-10-06T04:08:16.801750638Z（digest sha256:113870944968）。
- 前置四条现取原文（逐条照抄自 ledger，不缩写）：
  - 条 1 现取（收工那一刻）：`docker ps` 枚数 7，名册 `enterprise-brain-backend-1`、`enterprise-brain-frontend-1`、`enterprise-brain-ollama-1`、`enterprise-brain-postgres-1`、`enterprise-brain-redis-1`、`enterprise-brain-scheduler-1`、`enterprise-brain-worker-1`；除 frontend 外逐枚 health=backend-1=healthy、worker-1=healthy、scheduler-1=healthy、postgres-1=healthy、redis-1=healthy、ollama-1=healthy；frontend 在位=True
  - 条 1 开工那一刻（起手轴取全账最早一枚截图时刻 2026-10-06T13:21:48+08:00，与容器 `State.StartedAt` 现算）：backend-1 已 Up 1.221 h；worker-1 已 Up 1.221 h；scheduler-1 已 Up 1.221 h；frontend-1 已 Up 15.152 h；postgres-1 已 Up 15.152 h；redis-1 已 Up 15.152 h；ollama-1 已 Up 15.152 h
  - 条 2 现取：镜像 `enterprise-brain:local` digest `sha256:113870944968` 建于 2026-10-06T04:08:16（UTC）＝起手那一刻 1.225 小时 达标（≤） 2 小时；收工那一刻同轴读数 3.171 小时。这一条量的是墙钟，不是代码——自产品码代次 `4ebfaff` 起 `app/` 的提交枚数见下一条
  - 条 2 的代次半边现取：`git rev-list --count 4ebfaff..HEAD -- app/` = 0 枚、`-- frontend/` = 0 枚（两枚都是 0 ⇒ 起手那一刻镜像带的就是当前树的产品码与前端码，墙钟漂过 2 小时不改这一格）
  - 条 3 现取：`enterprise-brain-frontend:local` 建于 2026-10-05T07:22:39（UTC）＝起手那一刻 21.986 小时；过去 30 小时 `frontend/` 提交枚数 0；本树 `frontend/` 未提交改动枚数 0；前端未重建（本单没跑任何 build 命令）
  - 条 4 现取：登录走通的那枚读数＝环 2 的 `login_elapsed_s` = 1.046 s 且屏上身份 admin 角色 admin；口令取自 `deploy/.env.server` 键名 ['AUTH_USERNAME', 'DEMO_ADMIN_PASSWORD']（主）与 ['dataowner', 'EB_SEED_OWNER_PASSWORD']（次），值未记录，env 文件未被本单改过一行

## 九环（逐环达／未达，未达写差在哪一条）

| 环 | 名称 | 结论 | 取证时刻 | 截图枚数 | 读数键 |
|---|---|---|---|---|---|
| 1 | 登录页 | **达** | 2026-10-06T13:21:48+08:00 | 1 | `body_chars`, `document_fonts_status`, `globe_art_layer`, `login_page_present`, `requests_external`, `requests_font_cdn`, `requests_total`, `visible_cards`, `white_screen_guard` |
| 2 | 登录成功进工作台 | **达** | 2026-10-06T13:21:52+08:00 | 2 | `app_bg_layers`, `app_bg_wrapper`, `art_bleed`, `art_bleed_after_scroll`, `art_bleed_first_screen`, `bleed_mean_limit`, `bleed_worst_mean`, `body_cards`, `expected_layer_names`, `layer_count`, `layer_names_seen`, `login_elapsed_s`, `role_shown`, `user_shown`, `viewport_760_workspace_chars` |
| 3 | 上传文档 | **达** | 2026-10-06T13:21:56+08:00 | 3 | `count_delta`, `counts_after`, `counts_before`, `fixture_already_in_corpus_before_upload`, `fixture_bytes`, `fixture_name`, `row_present`, `row_text_after`, `tile_source`, `upload_state_transitions` |
| 4 | 文档列表／状态 | **达** | 2026-10-06T13:21:57+08:00 | 1 | `catalog_api_status`, `catalog_keys`, `catalog_row`, `catalog_top_level_keys`, `row_fields`, `row_present` |
| 5 | 知识问答（流式） | **达** | 2026-10-06T13:22:28+08:00 | 2 | `answer_chars_from_frames`, `asked_at`, `charts_on_screen`, `distinct_frame_counts`, `distinct_screen_lengths`, `elapsed_s`, `final_chars`, `finished_epoch_s`, `frame_count_total`, `growth_sample_count`, `growth_samples`, `hitl`, `question`, `reloaded_to_read_screen`, `rows_live_before_reload`, `runtime_faces`, `screen_probe`, `sequence_first_last`, `sequence_monotonic`, `sources_cards`, `started_epoch_s`, `steps_cards`, `streams`, `text_frame_count`, `text_frame_curve` |
| 6 | 权限隔离 | **达** | 2026-10-06T13:23:00+08:00 | 1 | `answer_chars_from_frames`, `answer_identical_to_principal_a`, `asked_at`, `catalog_restricted`, `catalog_status`, `catalog_visible_count`, `charts_on_screen`, `distinct_frame_counts`, `distinct_screen_lengths`, `elapsed_s`, `final_chars`, `finished_epoch_s`, `frame_count_total`, `growth_sample_count`, `growth_samples`, `hitl`, `mid_shot`, `principal_a_catalog_count`, `principal_a_sources`, `principal_b_department`, `principal_b_role`, `principal_b_user`, `question`, `reloaded_to_read_screen`, `restricted_face`, `rows_live_before_reload`, `runtime_faces`, `screen_probe`, `sequence_first_last`, `sequence_monotonic`, `source_names_visible`, `sources_cards`, `started_epoch_s`, `steps_cards`, `streams`, `text_frame_count`, `text_frame_curve` |
| 7 | 数据分析 | **未达** | 2026-10-06T14:42:39+08:00 | 4 | `after_approve`, `answer_chars_from_frames`, `artifact_leg_error`, `artifacts_before`, `asked`, `asked_at`, `chart_artifact`, `charts_on_screen`, `decision`, `department_probe`, `distinct_frame_counts`, `distinct_screen_lengths`, `elapsed_s`, `final_chars`, `finished_epoch_s`, `frame_count_total`, `growth_sample_count`, `growth_samples`, `hitl`, `input_wait_s`, `question`, `reloaded_to_read_screen`, `rows_live_before_reload`, `runtime_faces`, `screen_probe`, `sequence_first_last`, `sequence_monotonic`, `sources_cards`, `started_epoch_s`, `steps_cards`, `streams`, `table_choice`, `text_frame_count`, `text_frame_curve` |
| 8 | 报告导出 | **未达** | 2026-10-06T14:46:55+08:00 | 4 | `after_approve`, `answer_chars_from_frames`, `artifact_leg_error`, `artifact_rows_after`, `artifacts_before`, `asked`, `asked_at`, `charts_on_screen`, `decision`, `disk_newest_pdf`, `distinct_frame_counts`, `distinct_screen_lengths`, `elapsed_s`, `exported_piece`, `final_chars`, `finished_epoch_s`, `frame_count_total`, `growth_sample_count`, `growth_samples`, `hitl`, `input_wait_s`, `question`, `reloaded_to_read_screen`, `report_artifact`, `rows_live_before_reload`, `runtime_faces`, `screen_probe`, `sequence_first_last`, `sequence_monotonic`, `sources_cards`, `started_epoch_s`, `steps_cards`, `streams`, `table_choice`, `text_frame_count`, `text_frame_curve` |
| 9 | HITL／审计 | **达** | 2026-10-06T15:05:46+08:00 | 3 | `after_reject`, `approval_screen_after_reject`, `artifacts_before`, `audit`, `fresh_session`, `hitl_in_chat`, `parked_asked`, `parked_blocked_probe`, `parked_blocked_reason`, `parked_elapsed_s`, `parked_question`, `rejection` |

- 环 5（达）：屏上正文取自刷新之后的同一会话（刷新前 .msg-row 枚数见 rows_live_before_reload）；帧账与逐帧字符取自刷新之前的取帧器。
- 环 6（达）：两枚身份的可见集枚数已对照；生产库 department/classification 全空那一格不由本环翻绿，合成标签也不作为本环凭据。
- 环 7（未达）：未达差在「图能出」那半条：图登记这一腿交回的读数记在 artifact_leg_error，对照读数记在 department_probe（同一句问话、一枚部门非空的账号）。
- 环 8（未达）：未达差在「导出件可查回」这一条：文件已在容器盘上落出来，但产物登记那一腿交回的是 artifact_leg_error 那一行读数，所以 /api/v1/artifacts 里零枚在册。
- 环 9（达）：批准那一腿的凭据在环 7 与环 8（各自批掉自己挂起的那一枚）；这一环补的是驳回那一腿与审计面。

🔴 环 7／环 8 未达**不是走查没做完**，是这两条腿真在报错。归因（照 `defects.json` 与账面既有单号）：
- 环 7 数据分析那一腿＝计划书 R51① 那一格，治它的是 **R703**（已于 10-06 并树 `7810f73`，分析档带表那一轮必须真看见这张表）；本走查的取证时刻在并树之前，所以读数仍是旧形状。
- 环 8 报告导出那一腿＝产物登记没落账（`/api/v1/artifacts` 零枚在册），治它的是 **R710**（在飞，席位 `Noether`）。
- 两格在 R710 结案并复走之前一律写「未达」，不许提前翻绿。

## 两张失败脸（注入法，产品码零改动）

| 案 | 屏上白屏 | 截图 | 一次性后端 | 一次性前端 | 假 Ollama 门面 | 注入只写进临时后端 env |
|---|---|---|---|---|---|---|
| embedding | False | `{'bytes': 565440, 'file': 'r694-face-embedding.png', 'sha256_8': '21dfaa39', 'taken_at': '2026-10-06T15:29:08+08:00', 'viewport': {'height': 900, 'width': 1440}}` | {'command_rc': 0, 'start_elapsed_s': 0.731, 'started_at': '2026-10-06T15:25:26+08:00', 'stderr_tail': ' Container r694-embedding Creating \n Container r694-embedding Created \n'} | {'command_rc': 0, 'stderr_tail': ''} | {'command_rc': 0, 'embeddings_probe': {'rc': 1, 'stderr_tail': ' File "/usr/local/lib/python3.11/urllib/request.py", line 643, in http_error_default\n    raise HTTPError(req.full_url, code, msg, hdrs, fp)\nurllib.error.HTTPError: HTTP Error 503: Service Unavailable\n', 'stdout_tail': ''}, 'fake_name': 'r694-fake-embedding', 'in_container_probe': {'rc': 0, 'stderr_tail': '', 'stdout_tail': '{"status": 200, "body": {"models": []}}\n'}, 'stderr_tail': ''} | {'OLLAMA_BASE_URL': 'http://r694-fake-embedding:11434'} |
| embedding-unreachable | False | `{'bytes': 568915, 'file': 'r694-face-embedding-unreachable.png', 'sha256_8': 'a2167651', 'taken_at': '2026-10-06T15:31:27+08:00', 'viewport': {'height': 900, 'width': 1440}}` | {'command_rc': 0, 'start_elapsed_s': 0.76, 'started_at': '2026-10-06T15:29:09+08:00', 'stderr_tail': ' Container r694-embedding-unreachable Creating \n Container r694-embedding-unreachable Created \n'} | {'command_rc': 0, 'stderr_tail': ''} | None | {'OLLAMA_BASE_URL': 'http://127.0.0.1:1'} |
| gpu-failopen | False | `{'bytes': 573747, 'file': 'r694-face-gpu-failopen.png', 'sha256_8': 'c93b272e', 'taken_at': '2026-10-06T15:48:14+08:00', 'viewport': {'height': 900, 'width': 1440}}` | {'command_rc': 0, 'start_elapsed_s': 0.853, 'started_at': '2026-10-06T15:47:16+08:00', 'stderr_tail': ' Container r694-gpu-failopen Creating \n Container r694-gpu-failopen Created \n'} | {'command_rc': 0, 'stderr_tail': ''} | {'command_rc': 0, 'embeddings_probe': {'rc': 1, 'stderr_tail': '  File "/usr/local/lib/python3.11/urllib/request.py", line 643, in http_error_default\n    raise HTTPError(req.full_url, code, msg, hdrs, fp)\nurllib.error.HTTPError: HTTP Error 405: Method Not Allowed\n', 'stdout_tail': ''}, 'fake_name': 'r694-fake-gpu-failopen', 'in_container_probe': {'rc': 0, 'stderr_tail': '', 'stdout_tail': '{"status": 200, "body": {"models": [{"name": "qwen3.5:9b", "model": "qwen3.5:9b", "size": 5500000000, "digest": "r694-fake-cpu-digest", "details": {"family": "qwen2", "parameter_size": "9B", "quantization_level": "Q4_K_M"}, "processor": "cpu", "device_type": "cpu", "expiry": "1970-01-01T00:00:00.000000Z", "used_memory": 5500000000}]}}\n'}, 'stderr_tail': ''} | {'LOCAL_MODEL_BASE_URL': 'http://r694-fake-gpu-failopen:11434/v1', 'LOCAL_MODEL_NAME': '', 'OLLAMA_BASE_URL': 'http://r694-fake-gpu-failopen:11434', 'OLLAMA_MODEL': '', 'OLLAMA_REQUIRE_GPU': ''} |
| gpu-hard | False | `{'bytes': 573860, 'file': 'r694-face-gpu-hard.png', 'sha256_8': 'f7012047', 'taken_at': '2026-10-06T15:47:13+08:00', 'viewport': {'height': 900, 'width': 1440}}` | {'command_rc': 0, 'start_elapsed_s': 1.058, 'started_at': '2026-10-06T15:46:30+08:00', 'stderr_tail': ' Container r694-gpu-hard Creating \n Container r694-gpu-hard Created \n'} | {'command_rc': 0, 'stderr_tail': ''} | {'command_rc': 0, 'embeddings_probe': {'rc': 1, 'stderr_tail': '  File "/usr/local/lib/python3.11/urllib/request.py", line 643, in http_error_default\n    raise HTTPError(req.full_url, code, msg, hdrs, fp)\nurllib.error.HTTPError: HTTP Error 405: Method Not Allowed\n', 'stdout_tail': ''}, 'fake_name': 'r694-fake-gpu-hard', 'in_container_probe': {'rc': 0, 'stderr_tail': '', 'stdout_tail': '{"status": 200, "body": {"models": [{"name": "qwen3.5:9b", "model": "qwen3.5:9b", "size": 5500000000, "digest": "r694-fake-cpu-digest", "details": {"family": "qwen2", "parameter_size": "9B", "quantization_level": "Q4_K_M"}, "processor": "cpu", "device_type": "cpu", "expiry": "1970-01-01T00:00:00.000000Z", "used_memory": 5500000000}]}}\n'}, 'stderr_tail': ''} | {'LOCAL_MODEL_BASE_URL': 'http://r694-fake-gpu-hard:11434/v1', 'LOCAL_MODEL_NAME': '', 'OLLAMA_BASE_URL': 'http://r694-fake-gpu-hard:11434', 'OLLAMA_MODEL': '', 'OLLAMA_REQUIRE_GPU': '1'} |

- `embedding` 屏上读数：{"degraded_banner_count": 2}
  后端日志命中枚数＝{"line_count": 10, "lines": ["2026-10-06 15:27:51,506 [ERROR] enterprise_brain: Ollama embedding 失败 [server_error] model=nomic-embed-text: {\"error\": \"r694-injected: embedding backend unreachable\", \"code\": \"embeddi；注入说明：只掐 /api/embeddings（假门面交回 503），/api/tags 与 /api/ps 原样转发：算力档保持真
- `embedding-unreachable` 屏上读数：{"degraded_banner_count": 4}
  后端日志命中枚数＝{"line_count": 41, "lines": ["2026-10-06 15:30:54,736 [ERROR] enterprise_brain: Ollama embedding 失败 [connection_refused] model=nomic-embed-text: <urlopen error [Errno 111] Connection refused>", "2026-10-06 15:30:54,736 [；注入说明：OLLAMA_BASE_URL 指到没人听的端口：embedding 与 registry 两条腿一起不可达
- `gpu-failopen` 屏上读数：{"degraded_banner_count": 4}
  后端日志命中枚数＝{"line_count": 0, "lines": [], "log_bytes": 9657, "log_lines_total": 80, "marker": "R673 GPU 姿势声明", "marker_line_count": 1, "marker_lines": ["2026-10-06 15:47:27,518 [WARNING] enterprise_brain: R673 GPU 姿势声明：posture=fail；注入说明：同一枚假读数，撤掉硬门（R673 fail_open 那一档）；撤键同上
- `gpu-hard` 屏上读数：{"degraded_banner_count": 4}
  后端日志命中枚数＝{"line_count": 11, "lines": ["2026-10-06 15:46:45,145 [WARNING] enterprise_brain: R673 硬门触发（require_gpu）：确证 CPU 腿，发现结果就地不可用并带稳定码 model_unavailable，不降级、不静默继续跑。 探测读数：cpu", "2026-10-06 15:46:56,180 [WARNING] enterprise_brai；注入说明：假 /api/ps 报 cpu 且不给 size_vram，硬门在位（R673 require_gpu 那一档）；另在临时 backend 里把 LOCAL_MODEL_NAME／OLLAMA_MODEL 撤成空值，逼 app/common/model_config.py::get_local_model_settings 走 discovered 那一腿

## 断网自证（派生）

- 取证时刻：2026-10-06T15:52:12+08:00
  - `external_blocked`：外部域名请求 0 条，失败请求 - 条，document_host＝-
  - `hard_offline`：外部域名请求 0 条，失败请求 - 条，document_host＝-

## 恢复自证（判据 4）

- 本单建过的一次性容器名册（逐枚点名）：`r694-fake-gpu-hard`, `r694-gpu-hard`, `r694-ui-gpu-hard`, `r694-fake-gpu-failopen`, `r694-gpu-failopen`, `r694-ui-gpu-failopen`
- 停掉动作与 rc：{"r694-fake-gpu-failopen": 0, "r694-fake-gpu-hard": 0, "r694-gpu-failopen": 0, "r694-gpu-hard": 0, "r694-ui-gpu-failopen": 0, "r694-ui-gpu-hard": 0}
- `r694_leftover`（残留在册枚数）＝[]
- `docker ps` 对 `docker ps -a` 差集＝["enterprise-brain-migrate-1"]（一次性容器一枚不许留，这一枚是 migrate 单向件）
- 取证时刻：2026-10-06T15:48:28+08:00
- **总控 今日独立现取**（代笔于执行层读数之外）：`docker ps -a` 共 8 行＝7 枚 Up（backend／worker／scheduler healthy、frontend Up、redis／ollama／postgres healthy）＋`enterprise-brain-migrate-1` Exited(0)；`r694-*` 零枚在册。后端 env 现取 `INDEX_BACKEND=pgvector`、`OLLAMA_BASE_URL=http://ollama:11434`、`LOCAL_MODEL_NAME=qwen3.5:9b`、`OLLAMA_REQUIRE_GPU=1`＝假门面未残留。

## 缺陷清单（只立号不改码，逐枚归因到符号）

### #1【P1】流式期间新起的气泡不落屏：帧账一路长、屏上零字，刷新之后才有正文
- 现象：环 5／6／7 三枚新会话里，SSE 帧账分别长到 38／13／299 枚，同一时间窗内屏上 .msg-row 枚数恒为 0、正文字数恒为 0；刷新（同一会话再进一次）之后正文立刻可读（环 5 拿到 824 字）。同一台机的环 8 那一枚会话却不同：刷新前就有 4 行、字数从 0 逐格长上去（distinct_screen_lengths 从 0 一路到 1000+）。判据原文要的是「正文逐帧长出」，本单是在刷新之后才读到「长出」，所以这条只能记成「达（取数经刷新）」。
- 复现：用 new-session 开一枚全新会话（左侧会话列表最上面那枚）。 ／ 真实键盘敲一句知识问答并按 chat-send 发出。 ／ 在 done 帧之前每 0.2 s 取一次 document.querySelectorAll('.msg-row').length 与 .msg-content 的字数，同时读 window.__r694.streams 的帧账。 ／ 读数：帧账在长、屏上枚数与字数恒 0（见账本 rings 里 ring=5／6／7 的 rows_live_before_reload 与 distinct_screen_lengths）。 ／ 刷新页面重进同一会话：正文与来源卡都在（环 5 reloaded_to_read_screen=true、final_chars=824）。
- 符号：`frontend/src/components/ChatPanel.vue::TransitionGroup name="msg"`, `frontend/src/components/ChatPanel.vue::v-for="(msg, i) in messages" :key="i"`, `frontend/src/components/ChatPanel.vue::.msg-row`
- 指针：`ledger.json::rings[ring=5].readings.rows_live_before_reload`, `ledger.json::rings[ring=5].readings.distinct_screen_lengths`, `ledger.json::rings[ring=7].readings.frame_count_total`, `ledger.json::rings[ring=8].readings.rows_live_before_reload`, `图 r694-r5-stream-mid.png／r694-r7-stream-mid.png`
- 处置：只立号，本单不改 frontend/**（禁区）。要前端席位复损的是：index 当 :key 配 TransitionGroup 动效，是否让首枚流式气泡的挂载停在 enter 阶段；以及环 8 与环 5／6／7 的形状差在哪。

### #2【P1】产物登记拒「主身份没有部门」：admin 的 department 为空 ⇒ 出图与导出件全数进不了册
- 现象：ArtifactRegistry.register 在 principal 交不出部门时当场 raise ValueError("artifact owner must have a department scope")。生产库 users 现读：admin 的 department 为空、dataowner 的 department 才是财务部。于是环 7 的图与环 8 的 PDF 都跑到了腿的尽头，但 /api/v1/artifacts 交回 total=0（等了 151.508 s 与 151.4 s 各一轮，found=false）；PDF 本身已在容器盘上落出来（report_a8e1bc3666.pdf，57 322 字节，可读），产物面里却零枚在册。屏上没有任何一句人话说这一格。
- 复现：psql 现读 select username, nullif(coalesce(department,''),'<empty>') from users（admin 那行为空）。 ／ 用 admin 问「按月份统计报销金额，并画一张柱状图」，并批准 📈 生成图表 那一枚待批。 ／ 打开产物面（GET /api/v1/artifacts）：total=0（账本 rings[ring=7].readings.chart_artifact.wait_s=151.508、found=false）。 ／ 再问「请生成一份 2026 年上半年经营情况分析报告，并导出成报告文件」并批准 📋 导出报告：PDF 落盘 57 322 字节，产物面仍 total=0。 ／ 对照读数：同一句画图问话换一个 department 非空的账号（dataowner）问一遍，记在 rings[ring=7].readings.department_probe。
- 符号：`app/storage/artifacts.py::ArtifactRegistry.register`, `app/agents/tools.py::_artifact_urls`, `app/agents/tools.py::_artifact_principal`
- 指针：`ledger.json::rings[ring=7].readings.chart_artifact`, `ledger.json::rings[ring=7].readings.department_probe`, `ledger.json::rings[ring=8].readings.report_artifact`, `ledger.json::rings[ring=8].readings.disk_newest_pdf`, `ledger.json::rings[ring=7].readings.artifacts_before`
- 处置：只立号。两笔账各归各处：屏上该说一句「这一位的部门为空、产物进不了册」（现在的形状是静默零枚），以及计划书 §13 那一格里生产 department/classification 全空的回填口径（属业主，不属本单）。

### #3【P2】出图失败全被折成一句 validation_error：异常文本只进返回值、不落日志
- 现象：app/agents/tools.py::generate_chart 的收尾判法是「返回值不以『图表已生成』开头就 span.finish(failed, error_code=validation_error)」，而 _generate_chart 里 except Exception as e: return f"图表生成失败: {e}" 把真异常折成一句字符串返回，既不记 logger 也不带栈。库里 tool_calls 现读：generate_chart failed/validation_error 457 枚（今天两小时内 40 枚，标题「按月统计的报销金额」，arguments 里 label_count=6／value_count=6 看着是齐的）、generate_chart failed/internal_error 13 枚；export_report failed/internal_error 620 枚。result_summary 一律空 {}，事后无从分辨「参数没验过」与「画图函数抛了」。
- 复现：用 admin 问「按月份统计报销金额，并画一张柱状图」并批准 📈 生成图表。 ／ psql 现读 select tool_name, status, error_code, count(*) from tool_calls where tool_name in ('generate_chart','export_report') group by 1,2,3。 ／ 在后端日志里搜「图表生成失败」：0 枚命中（这句话只进工具返回值，交给模型消化）；屏上 charts_on_screen=0。 ／ 读数指针见账本 rings[ring=7].readings.charts_on_screen 与 rings[ring=7].readings.artifact_leg_error（[data] 完成 status=failed 结果 0 字）。
- 符号：`app/agents/tools.py::generate_chart`, `app/agents/tools.py::_generate_chart`, `app/agents/contracts.py::validation_error`
- 指针：`ledger.json::rings[ring=7].readings.charts_on_screen`, `ledger.json::rings[ring=7].readings.artifact_leg_error`, `ledger.json::rings[ring=8].readings.artifact_leg_error（[export] 完成 status=failed 结果 51 字）`, `tool_calls 表（psql 现读，本单只读不写）`
- 处置：只立号。稳定的错误码词汇（app/agents/contracts.py 那一本）不该被一句返回值判成 validation_error；要归因得先让抛错那一腿把话写进日志。

### #4【P2】待批行退出屏幕的时延三档差两个数量级：批准 91.436 s／29.687 s，驳回 1.437 s
- 现象：点「批准执行」之后，那一行从待批列表里消失要等 91.436 s（环 7）或 29.687 s（环 8）；点「驳回」只要 1.437 s（环 9）。屏上期间没有任何过渡态（既不是「已提交，等待落账」也不是进度），用户会当成没点到而重复点。形状差得起来的原因按读数看是腿不同：批准要把挂起的那一轮重新跑下去（POST /api/v1/approve 交整段流），驳回只改一次状态。
- 复现：问一句会挂待批的话（画柱状图／导出报告），等 📈 生成图表 或 📋 导出报告 那行出现在待批面板。 ／ 点批准，轮询那一行的枚数直到它消失，记秒数（读数 rings[ring=7].readings.decision.decide_wait_s=91.436、rings[ring=8]=29.687）。 ／ 另开一轮同样挂待批，点驳回，同样记秒数（rings[ring=9].readings.rejection.decide_wait_s=1.437）。 ／ 期间盯屏：待批行原地不动，无过渡态文案（outcome_faces_after=[]、outcome_codes=[]）。
- 符号：`app/api/v1/chat.py::approve`, `app/api/v1/chat.py::APPROVE_ROUTE_PATH`, `app/api/v1/chat.py::GET /hitl/pending`, `frontend/src/components/ApprovalPanel.vue::GET /hitl/pending 那一块的行渲染`
- 指针：`ledger.json::rings[ring=7].readings.decision.decide_wait_s`, `ledger.json::rings[ring=8].readings.decision.decide_wait_s`, `ledger.json::rings[ring=9].readings.rejection.decide_wait_s`, `图 r694-r7-approval-face.png／r694-r9-hitl-rejected.png`
- 处置：只立号。屏上缺的是「已批准，正在续跑」那一枚具名过渡态；时延本身属续跑那一腿，不由本单判快慢。

### #5【P2】同一句问话命中答案缓存：注入的两条腿整个被跳过（首版四张脸因此全是假读数）
- 现象：第一版失败脸四案都打同一句「费用报销需要经过哪些审批环节？」，四案全部在 1.2–1.7 s 内答复完成，后端日志里本轮注入的失败词零条命中——因为 app/common/cache.py::get_cached_answer 按「问话＋scope」命中 TTL 1800 s 的缓存答复，压根不碰 embedding 与算力两条腿。作废读数留档在 ledger-attempt-2.json。改法是把本轮编号敲进问句（问句形如「…（脸编 HHMMSS）」），四案才拿到真脸。
- 复现：在线问一句 A（等它答完并入缓存）。 ／ 同一 scope 下原样再问一次 A：秒表读数 ~1.2 s，SSE 帧数远小于首答，且后端日志本轮零条新词。 ／ 把 A 改成带本轮编号的 A′ 再问：才走真腿（本案四张脸的 elapsed_s 44.243／180.162／17.081／36.563 各档都能对上是哪一条腿在跑）。
- 符号：`app/common/cache.py::get_cached_answer`, `app/common/cache.py::answer_cache_ttl_seconds`, `app/common/cache.py::answer_cache_scope`, `app/api/v1/chat.py::答案缓存命中那一格的 done 帧`
- 指针：`ledger-attempt-2.json::faces[*].ask.elapsed_s（作废留档）`, `ledger.json::faces[*].ask.question（问句带脸编）`, `ledger.json::faces[*].backend_logs.line_count`
- 处置：只立号（走查判据不是缓存判据）。建议在一切「注入腿」类取证里默认给问句加轮次盐，并把这条写进失败脸量具的 docstring——本单已照此改。

### #6【P2】GPU 两档姿势在屏上是同一句话：require_gpu 与 fail_open 的脸分不出来
- 现象：两档都用同一枚假 /api/ps（processor/device_type=cpu、不给 size_vram）。日志侧两档各归各处：require_gpu 那一档命中「R673 GPU 姿势声明：posture=require_gpu（硬门在位）」＋「R673 硬门触发」，health/details 交回 model_source=none／inference_compute=cpu；fail_open 那一档命中「posture=fail_open（缺省放行）」＋「R673 确证 CPU 腿」，model_source=discovered／model_name=qwen3.5:9b。但屏上两张脸的文案逐字相同（runtime_faces 与 degradation-banner 都是「本机服务降级：没走加速设备」那一句），两枚截图 sha256 前 8 位分别 f7012047 与 c93b272e，差异只在答复帧账与秒数（17.081 s 对 36.563 s）。读代码的人能从日志分档，看屏的人分不出：硬门到底有没有把服务拦下来，屏上没有那一句。
- 复现：起一次性 backend（docker compose run -d --rm --no-deps）＋一次性假 Ollama 门面，把 LOCAL_MODEL_BASE_URL／OLLAMA_BASE_URL 指到门面，并在同一枚临时 backend 里把 LOCAL_MODEL_NAME／OLLAMA_MODEL 撤成空值（不撤就没有探针：见本单方法论）。 ／ 档一：OLLAMA_REQUIRE_GPU=1，屏上发问 → 拍 r694-face-gpu-hard.png，docker logs 现取两行声明。 ／ 档二：OLLAMA_REQUIRE_GPU 撤成空值，同一枚门面同一句问话（换编号） → 拍 r694-face-gpu-failopen.png。 ／ 对照两张脸的屏上文案：逐字相同；对照 health/details 的 model_source：none 对 discovered。
- 符号：`app/common/model_capabilities.py::POSTURE_DECLARATION_REQUIRE_GPU`, `app/common/model_capabilities.py::POSTURE_DECLARATION_FAIL_OPEN`, `app/common/model_capabilities.py::annotate_inference_compute`, `app/common/model_config.py::get_local_model_settings`, `frontend/src/components/ChatPanel.vue::runtime-face 那一张牌`
- 指针：`ledger.json::faces[case=gpu-hard].posture_reading`, `ledger.json::faces[case=gpu-failopen].posture_reading`, `图 r694-face-gpu-hard.png／r694-face-gpu-failopen.png`
- 处置：只立号。R673 交回的是「日志两档各说各话」这一半，屏上那一半（把 posture 也送到 runtime-face 的文案里）没做——判据「两种姿势各自具名」今天只在日志侧成立。

## 文件名册（判据 2：逐枚点名文件名与字节数）

| 文件 | 字节 |
|---|---|
| `defects.json` | 12893 |
| `ledger-attempt-2.json` | 276202 |
| `ledger.json` | 343226 |
| `r694-face-embedding-unreachable.png` | 568915 |
| `r694-face-embedding.png` | 565440 |
| `r694-face-gpu-failopen.png` | 573747 |
| `r694-face-gpu-hard.png` | 573860 |
| `r694-offline-blocked-login-1440.png` | 1184592 |
| `r694-offline-blocked-workbench-1440.png` | 674531 |
| `r694-offline-login-1440.png` | 5851 |
| `r694-offline-workbench-1440.png` | 5851 |
| `r694-r1-login-1440.png` | 1184592 |
| `r694-r2-workbench-1440.png` | 690252 |
| `r694-r2-workbench-760.png` | 421708 |
| `r694-r3-upload-after.png` | 764421 |
| `r694-r3-upload-before.png` | 791533 |
| `r694-r3-upload-progress.png` | 794160 |
| `r694-r4-catalog.png` | 762748 |
| `r694-r5-answer-final.png` | 514578 |
| `r694-r5-stream-mid.png` | 607603 |
| `r694-r6-principal-b-chat.png` | 516600 |
| `r694-r7-analysis-parked.png` | 458721 |
| `r694-r7-approval-face.png` | 684135 |
| `r694-r7-approval-screen.png` | 615831 |
| `r694-r7-chart-face.png` | 459740 |
| `r694-r7-stream-mid.png` | 623632 |
| `r694-r7b-department-account.png` | 759017 |
| `r694-r8-approval-face.png` | 818878 |
| `r694-r8-report-face.png` | 405087 |
| `r694-r8-report-parked.png` | 529866 |
| `r694-r8-stream-mid.png` | 276294 |
| `r694-r9-after-approve.png` | 322896 |
| `r694-r9-audit-events.png` | 620627 |
| `r694-r9-hitl-before-approved.png` | 819044 |
| `r694-r9-hitl-rejected.png` | 819624 |
| `r694-r9-stream-mid.png` | 626020 |
- 合计 36 枚（本纸不计），另有本 README 共 37 枚。
- 截图枚数按环对照：环 1-9 逐环 shots 枚数＝1 环 1, 2 环 2, 3 环 3, 4 环 1, 5 环 2, 6 环 1, 7 环 4, 8 环 4, 9 环 3

## 这一单为什么不是「零改动」的例外

- 判据 3 的口径由本纸自证：`git diff --cached --name-only` 对本次并树的 52 枚逐枚点名后，`app/**`／`frontend/**`／`deploy/**`／`docs/handoff/**`／评测夹具交回空——走查只新增纸与量具（`scripts/r694_*.py` 16 枚），零产品码。
- 量具 16 枚里 `scripts/r694_failure_faces.py` 已把「问句加轮次盐」写进 docstring（缺陷 #5 的正解），`scripts/r694_revert.py` 负责一次性容器回收。

