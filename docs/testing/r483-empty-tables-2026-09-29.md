<!-- 本文件整枚由 scripts/r483_empty_tables_triage.py 生成（--sync）。
     改文案改生成器，改数重跑读数；手写任何一格，--check 逐字节红。 -->

# R483 · 演示库八枚「当时 0 行」表的逐枚定性（2026-09-29 造册 / 2026-10-03 R593 按现读改口）

本单是取证单：不新建业务闭环、不改产品码，只把「结构在、一行没有」的八枚表逐枚定性，让下一班知道哪枚是真欠码、哪枚本来就该空、哪枚只能等业主。

🔴 **R593（2026-10-03）改口**：上面那句「一行没有」是 09-29 造册时的点名范围，不是今天的读数——八枚里今天已有 3 枚长出行了（`alerts` / `alert_rules` / `retrieval_traces`），裁定由 `validate()` 逼出来逐枚重定性，改判凭据写在各自那一格。这一行与下面每一格都由现读算，本文件不抄上一班的数。

## 口径（四句写死在生成器里，不在别处抄第二份）

- **今日现读**：`docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -At -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only = on" -c "<SELECT>"`。`psql_select()` 里那道 `assert_select_only()` 是唯一读数出口：不是 SELECT 就抛，命中 insert / update / delete / create / alter / drop 一类禁词也抛。🔴 一条写语句、一条 DDL 都没发；除了在册库 `enterprise_brain`，没碰任何别的库。
- **昨日底**：`PROBE_PATH` 里那枚 `rows`，渲染时现读原件，本件不隔夜存这份数。
- **写入点**：现场扫 `app/**` 与 `scripts/**` 的源码得到「哪枚文件哪枚函数往里写」，再顺调用链往上爬，看这条道今天挂在哪个产品面（HTTP 路由 / `add_job`）。🔴 扫不到就写没找到，绝不写「应该由某个定时任务写」。
- 路由串按装饰器原文交回（**不含** router 前缀），坐标一律现扫：🔴 本文件一枚行号都不是抄的。　**裁定只有 4 词**：`no_seed_path` / `legitimately_empty` / `needs_owner` / `no_longer_empty`；裁定与现扫互为牙齿、裁定与现读行数也互为牙齿，谁漂了 `validate()` 报哪一格。
- 取数时刻 `2026-10-03T13:29:00+08:00`；服务端 PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 6…。

结论一句话（四个数由本表现算，一枚不抄）：R483 点名的八枚里，3 枚今天已经有行（`no_longer_empty`）、2 枚压根没有走得通的写入道（`no_seed_path`）、1 枚只能等业主输入（`needs_owner`）、2 枚按设计就该空着等一次真实行为（`legitimately_empty`）；四数之和 8 = 8，本单不留一格含糊——每一格到底还欠什么，只在本格那一节里写，本句不替谁担保。
<!-- R483-TABLE-BEGIN -->

## 一、读数表（今日现读 / 昨日底 / 写入点现扫 / 裁定）
| 表 | 今日现读 | 昨日底 | Δ | 主键顶值（今日现读） | 写入点（现扫 文件:行 · 函数） | 结构出处 | 裁定 |
|---|---:|---:|---:|---|---|---|---|
| `alerts` | 4 | 0 | +4 | 4 | `app/api/v1/alerts.py:780 · _dispose_alert`, `app/api/v1/alerts.py:1017 · evaluate_all` ＋1 处 | `migrations/0003_legacy_runtime_tables.sql:62` | `no_longer_empty` |
| `alert_rules` | 4 | 0 | +4 | 4 | `app/api/v1/alerts.py:1099 · create_rule`, `app/api/v1/alerts.py:1131 · delete_rule` ＋1 处 | `migrations/0003_legacy_runtime_tables.sql:53` | `no_longer_empty` |
| `notification_states` | 0 | 0 | 0 | None | `app/notifications/states.py:258 · apply_state`, `app/notifications/states.py:213 · apply_state` | `migrations/0016_notification_states.sql:63` | `legitimately_empty` |
| `calculation_runs` | 0 | 0 | 0 | None | 没找到 | `migrations/0002_execution_data_lineage.sql:52` | `no_seed_path` |
| `metric_definitions` | 0 | 0 | 0 | None | `app/semantics/registry.py:742 · _insert_statement`, `app/semantics/registry.py:751 · _insert_statement` ＋2 处 | `migrations/0002_execution_data_lineage.sql:72` | `no_seed_path` |
| `retrieval_traces` | 1032 | 0 | +1032 | trace-ff745171edc84698a1abf6039181f774:… | `app/storage/persistence.py:418`, `app/trace/projections.py:324 · project_retrieval` | `migrations/0002_execution_data_lineage.sql:170` | `no_longer_empty` |
| `user_profiles` | 0 | 0 | 0 | None | `app/memory/profile.py:273 · upsert_profile`, `app/memory/profile.py:240 · upsert_profile` | `migrations/0003_legacy_runtime_tables.sql:83` | `needs_owner` |
| `document_activity_signals` | 0 | 0 | 0 | None | `app/api/v1/feedback.py:49`, `app/api/v1/feedback.py:147 · record_document_signal` | `migrations/0011_document_activity_signals.sql:24` | `legitimately_empty` |

## 二、逐枚：它该走哪条写入道

### `alerts` —— `no_longer_empty`

- 今日现读 4 行（昨日底 0 行，Δ 4），主键 `id` 顶值 `4`。
- 结构出处：`migrations/0003_legacy_runtime_tables.sql:62`；表名在 app/ 与 scripts/ 里现扫到 150 行、18 枚文件。
- 写入点（现扫）：`app/api/v1/alerts.py:780 · _dispose_alert`（sql_write）、`app/api/v1/alerts.py:1017 · evaluate_all`（sql_write）、`app/api/v1/alerts.py:945 · evaluate_all`（declared_writer）。
- 这条道今天挂在产品面上：`POST /alerts/check ← app/api/v1/alerts.py:1173 · check_now`。
- 定时任务这条道现扫到：`app/scheduler/jobs.py:37 → scheduler.add_job(evaluate_all, "interval", minutes=5,`。
- 从写句往上爬过的坐标：`app/api/v1/alerts.py:1173 · check_now`、`app/api/v1/alerts.py:945 · evaluate_all`。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- ⚠ 现扫在这一处 fail closed（解不开就不算通，宁可读成没道）：`调用点在模块级，接不上任何 def：app/api/v1/alerts.py:5`。
- 入口只在测试里被引到：`tests/test_alert_scan_scope.py`、`tests/test_deployment_topology.py`、`tests/test_phase4_alerts.py`、`tests/test_r176_alert_row_scope.py`，另有 4 枚（按判据④，那不算产品有一行真数据）。
- 该走哪条写入道：只有巡检命中才写：告警行唯一出处是 app/api/v1/alerts.py::evaluate_all 里那句 INSERT INTO alerts，规则集取自 alert_rules 里 enabled=TRUE 的行。上表另一枚 sql_write 是处置闭环的 UPDATE（确认 / 转派 / 关闭），它只改状态，不加行。
- 裁定理由：这条道今天真在跑（现扫到的 add_job 注册 + scheduler 日志里的成功行数，两格都进本表）。🔴 原话「空的是它的上游：一枚启用规则都没有，逐规则判定无从命中」已被现读推翻——`alert_rules` 今天有 enabled=TRUE 的行，巡检于是真命中并长出了行；「补一条业主规则它自己会长行」这一句今天不再是假设，是已经发生过的事。无库时的代码兜底规则走的是内存表，不构成本表数据，那一句仍然成立。
- 改判出处：R593（2026-10-03）——基点 6fcea4f 现跑 `python scripts/r483_empty_tables_triage.py --json` 交回 rc=1，本格 problems 原话：「alerts 今天已经有 4 行了，本单的 0 行定性过期，重跑 --sync」（总控 10-03 11:1x 于主树现取，本席在基点复跑同一句逐字对上）。裁定随这条读数改口，不由本席宣布；今天的行数只在上表与第五节读数件里，本段一枚数字都不留。　**本格今日现读 4 行**（这枚数出自 `readout`，与上一句里的历史引用无关）。

### `alert_rules` —— `no_longer_empty`

- 今日现读 4 行（昨日底 0 行，Δ 4），主键 `id` 顶值 `4`。
- 结构出处：`migrations/0003_legacy_runtime_tables.sql:53`；表名在 app/ 与 scripts/ 里现扫到 13 行、3 枚文件。
- 写入点（现扫）：`app/api/v1/alerts.py:1099 · create_rule`（sql_write）、`app/api/v1/alerts.py:1131 · delete_rule`（sql_write）、`app/api/v1/alerts.py:1077 · create_rule`（declared_writer）。
- 这条道今天挂在产品面上：`POST /alerts/rules ← app/api/v1/alerts.py:1077 · create_rule`。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 从写句往上爬过的坐标：`app/api/v1/alerts.py:1077 · create_rule`。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- 入口只在测试里被引到：`tests/test_offline_runtime_fallbacks.py`、`tests/test_r359_alerts_refuse_a_store_that_is_not_there.py`、`tests/test_r371_the_conversion_is_narrow_and_stays_at_the_exit.py`（按判据④，那不算产品有一行真数据）。
- 该走哪条写入道：app/api/v1/alerts.py::create_rule（HTTP 建规则那一腿）→ INSERT INTO alert_rules。
- 裁定理由：规则的三要素（指标 / 运算符 / 阈值）就是一家企业的口径，代码替业主编一条就是假账——这一句没有被推翻。今天在册的是演示样本种子经 POST /api/v1/alerts/rules 建的样本规则（名字以 r577-sample- 起头，指标列名取自数据集画像）：它把「这张表空不空」翻成了非空，**没有**把「业主口径」翻绿，真业务规则依旧等人录。所以 09-29 那句 needs_owner 在当时成立（那时它 0 行），今天按现读改判 no_longer_empty，业主欠的那半移进本段留名。
- 改判出处：R593（2026-10-03）——同一条 `--json` 现读交回 rc=1，本格原话：「alert_rules 今天已经有 4 行了，本单的 0 行定性过期，重跑 --sync」；行是从本格在册的那条 POST 建规则道写进去的（写入点与坐标由本表现扫，见上表）。行数同上，只归读数件管。　**本格今日现读 4 行**（这枚数出自 `readout`，与上一句里的历史引用无关）。

### `notification_states` —— `legitimately_empty`

- 今日现读 0 行（昨日底 0 行，Δ 0），主键 `id` 顶值 `None`。
- 结构出处：`migrations/0016_notification_states.sql:63`；表名在 app/ 与 scripts/ 里现扫到 2 行、1 枚文件。
- 写入点（现扫）：`app/notifications/states.py:258 · apply_state`（write_via_table_constant）、`app/notifications/states.py:213 · apply_state`（declared_writer）。
- 这条道今天挂在产品面上：`POST /notifications/read ← app/api/v1/notifications.py:213 · mark_notifications_read`、`POST /notifications/dismiss ← app/api/v1/notifications.py:219 · dismiss_notifications`。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 从写句往上爬过的坐标：`app/api/v1/notifications.py:136 · _apply`、`app/api/v1/notifications.py:213 · mark_notifications_read`、`app/api/v1/notifications.py:219 · dismiss_notifications`、`app/notifications/states.py:213 · apply_state`。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- 入口只在测试里被引到：`tests/test_r299_notification_inbox.py`、`tests/test_r303_pg_upsert_leg.py`、`tests/test_r376_gate_shape_pins.py`、`tests/test_r376_notifications_refuse_a_store_that_is_not_there.py`，另有 1 枚（按判据④，那不算产品有一行真数据）。
- 该走哪条写入道：app/notifications/states.py::apply_state（表名走本文件的 TABLE 常量拼进写句）→ POST /notifications/read 与 /notifications/dismiss 两条腿共用它。
- 裁定理由：按设计只有真人点「已读 / 忽略」才写这一行，收件箱本身不开第四本账（三条源全从已有的账现读）。所以 0 行的准确说法是：铃铛挂上之后没人点过一次。要补的是端到端行为读数，不是接口。

### `calculation_runs` —— `no_seed_path`

- 今日现读 0 行（昨日底 0 行，Δ 0），主键 `calculation_run_id` 顶值 `None`。
- 结构出处：`migrations/0002_execution_data_lineage.sql:52`；表名在 app/ 与 scripts/ 里现扫到 0 行、0 枚文件。
- 写入点（现扫）：**没找到**（app/ 与 scripts/ 里没有任何写这张表的语句）。
- 这条道今天没挂在任何产品面 HTTP 路由上（现扫零枚）。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- 该走哪条写入道：没找到：app/ 与 scripts/ 里现扫不到任何一条写这张表的语句。
- 裁定理由：结构在（现扫到的 CREATE TABLE 出处进本表），表名在 app/ 与 scripts/ 里一次都没出现，连读路径都没有。V2 第 3 句里「Artifact 绑 CalculationRun」那一格今天仍是后续目标，不是已有能力。

### `metric_definitions` —— `no_seed_path`

- 今日现读 0 行（昨日底 0 行，Δ 0），主键 `metric_definition_id` 顶值 `None`。
- 结构出处：`migrations/0002_execution_data_lineage.sql:72`；表名在 app/ 与 scripts/ 里现扫到 15 行、4 枚文件。
- 写入点（现扫）：`app/semantics/registry.py:742 · _insert_statement`（write_via_table_constant）、`app/semantics/registry.py:751 · _insert_statement`（write_via_table_constant）、`app/semantics/registry.py:791 · sync_code_definitions`（declared_writer）、`app/semantics/registry.py:816 · register_metric_definition`（declared_writer）。
- 这条道今天没挂在任何产品面 HTTP 路由上（现扫零枚）。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 从写句往上爬过的坐标：`app/knowledge_graph/promotion.py:47 · promote_relation_to_definition`、`app/semantics/registry.py:791 · sync_code_definitions`、`app/semantics/registry.py:816 · register_metric_definition`。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- 入口只在测试里被引到：`tests/test_business_semantics.py`、`tests/test_semantic_promotion.py`（按判据④，那不算产品有一行真数据）。
- 该走哪条写入道：写句在树：app/semantics/registry.py::_insert_statement / ::_store_row（表名走 TABLE_NAME 常量）。入口是 register_metric_definition 与 sync_code_definitions。
- 裁定理由：两条入口从产品面都爬不到：register_metric_definition 唯一的调用者是 app/knowledge_graph/promotion.py::promote_relation_to_definition，而后者在 app/ 与 scripts/ 里现扫零调用者；sync_code_definitions 同样零调用者。tests/ 里能调到它——按判据④那不算产品数据。读侧此刻靠代码兜底口径作答，所以这是「写的那半没接上」，不是整条链不存在。
- 道断在：`app/knowledge_graph/promotion.py:47 · promote_relation_to_definition`（现扫调用者 0 枚：调用者或产品面一出现，这一句与 `validate()` 同时红）。
- 裁定出处：总控 2026-09-29 裁定——本轮**不加 HTTP 面**（promotion 出口挂哪张脸属 V2 语义层的决定），保持 no_seed_path；本格不再挂待裁。

### `retrieval_traces` —— `no_longer_empty`

- 今日现读 1032 行（昨日底 0 行，Δ 1032），主键 `retrieval_trace_id` 顶值 `trace-ff745171edc84698a1abf6039181f774:18`。
- 结构出处：`migrations/0002_execution_data_lineage.sql:170`；表名在 app/ 与 scripts/ 里现扫到 21 行、9 枚文件。
- 写入点（现扫）：`app/storage/persistence.py:418`（write_by_registry）、`app/trace/projections.py:324 · project_retrieval`（declared_writer）。
- 这条道今天挂在产品面上：`POST /ask ← app/api/v1/chat.py:2483 · _run`、`POST /approve ← app/api/v1/chat.py:3425 · _run`。
- 🔴 现扫确实爬到一枚脸，但它是**调试面**，按本单显式豁免不算产品道：`POST /retrieval/debug ← app/api/v1/observability.py:528 · retrieval_debug`。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 从写句往上爬过的坐标：`app/agents/orchestrator.py:962 · _approval_worker_node`、`app/agents/tools.py:1085 · search_docs`、`app/api/v1/chat.py:2707 · _run`、`app/api/v1/chat.py:3474 · _run`、`app/api/v1/observability.py:528 · retrieval_debug`、`app/approval/assistant.py:225 · retrieve_expense_hits`，另有 48 枚。
- 跨「发射点 → 订阅 / 投影 → 写句」那一跳的边（现扫，逐枚可复核）：`declared_event retrieval.completed：TRIAGE 声明 → app/rag/debug.py:24 · run_retrieval_debug`；`declared_event retrieval.completed：TRIAGE 声明 → app/rag/retrieval_pipeline.py:1177 · record_retrieval_completed`；`gate_token retrieval.completed：app/rag/retrieval_pipeline.py:1177 · record_retrieval_completed → app/rag/retrieval_pipeline.py:1107 · arm_retrieval_trace`；`publish retrieval.completed：app/trace/projections.py:353 · project_event → app/rag/debug.py:24 · run_retrieval_debug`；`publish retrieval.completed：app/trace/projections.py:353 · project_event → app/rag/retrieval_pipeline.py:1177 · record_retrieval_completed`；`event_guard retrieval.completed：app/trace/projections.py:382 → app/trace/projections.py:324 · project_retrieval`。
- ⚠ 现扫在这一处 fail closed（解不开就不算通，宁可读成没道）：`调用点在模块级，接不上任何 def：scripts/r220_packing_loss.py:13`。
- 入口只在测试里被引到：`tests/test_r536_retrieval_completed_on_product_lane.py`、`tests/test_r550_event_hop_climb_is_generic.py`（按判据④，那不算产品有一行真数据）。
- 该走哪条写入道：app/trace/projections.py::project_retrieval（collection 走 _PostgresTable 注册）← 同文件 project_event 在 `if event_type == "retrieval.completed"` 守卫里派发 ← app/trace/store.py 收事件落投影；发这枚事件的是 app/rag/retrieval_pipeline.py::record_retrieval_completed，它缺 arm_retrieval_trace 挂进执行上下文的那枚身份就直接走开，所以闸门真挂在问答脸上。
- 裁定理由：写入道今天两格都在：写句在（投影注册在册），产品面也在（现扫从问答道沿 retrieval.completed 这枚标签跨过来）。🔴 原话「于是 0 行的准确说法是『这轮行为还没留下痕』」已是过去式——痕真留下了，见上表与第四节事件面那一叠数。于是本格要量的不再是空不空，而是道通不通：道今天通；一旦摘掉发射腿，validate() 会重新报「应改判 no_seed_path」，那才是它该回去的时候。库里那枚行数由本表现读交回，本段一个数字都不写。
- 裁定出处：总控 2026-09-29 裁定——当时唯一发射点在 RAG 调试面（app/rag/debug.py 发 retrieval.completed ← POST /retrieval/debug），正常问答链一枚都不发 ⇒「有表、有写句、但没有喂它产品的道」。**那半句话已经过期**：R536（09-30 并树）把发射实现接到产品问答道（app/rag/retrieval_pipeline.py::record_retrieval_completed，挂点是 POST /ask 与 /approve 续跑轮）。当时本格仍暂不翻，理由是本量具认的「道」只从写语句往上爬到 HTTP 路由或 add_job，跨不过事件投影那一跳——那是量具的盲区。R550 已把这一跳补成通用的沿边传递（表名不当分支），所以裁定按现扫改口；改口的凭据不是本段散文，是 validate() 那两枚自洽腿与摘腿的刀。
- 改判出处：R593（2026-10-03）——总控 10-03 11:1x 在主树现跑 `python scripts/r483_empty_tables_triage.py --json` 交回 rc=1，本格原话：「retrieval_traces 今天已经有 911 行了，本单的 0 行定性过期，重跑 --sync」；本席在基点 6fcea4f 复跑同一条命令，同一句里是另一枚更大的数（问答窗还在往里加行）。两枚数都只算历史引用、不算今天的事实——现读以本表与第五节读数件为准，这正是本格把数字交给渲染而不写进裁定的理由。　**本格今日现读 1032 行**（这枚数出自 `readout`，与上一句里的历史引用无关）。

### `user_profiles` —— `needs_owner`

- 今日现读 0 行（昨日底 0 行，Δ 0），主键 `user_id` 顶值 `None`。
- 结构出处：`migrations/0003_legacy_runtime_tables.sql:83`；表名在 app/ 与 scripts/ 里现扫到 20 行、6 枚文件。
- 写入点（现扫）：`app/memory/profile.py:273 · upsert_profile`（sql_write）、`app/memory/profile.py:240 · upsert_profile`（declared_writer）。
- 这条道今天挂在产品面上：`PUT /profile ← app/api/v1/auth.py:281 · update_my_profile`。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 从写句往上爬过的坐标：`app/api/v1/auth.py:281 · update_my_profile`、`app/memory/profile.py:240 · upsert_profile`。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- 入口只在测试里被引到：`tests/test_deployment_guards.py`、`tests/test_offline_runtime_fallbacks.py`、`tests/test_r296_department_is_read_only_derived.py`、`tests/test_r377_migrations_first_family_is_contained_at_the_store_layer.py`，另有 2 枚（按判据④，那不算产品有一行真数据）。
- 该走哪条写入道：app/memory/profile.py::upsert_profile ← app/api/v1/auth.py 的 PUT /api/v1/profile。
- 裁定理由：这格里该躺的是员工自报的职位与偏好，只能业主侧录。department 那一列已被 R296 钉成只读派生值，写入道今天明确不收它——所以「回填 department」不算这条道的填法。

### `document_activity_signals` —— `legitimately_empty`

- 今日现读 0 行（昨日底 0 行，Δ 0），主键 `filename` 顶值 `None`。
- 结构出处：`migrations/0011_document_activity_signals.sql:24`；表名在 app/ 与 scripts/ 里现扫到 11 行、3 枚文件。
- 写入点（现扫）：`app/api/v1/feedback.py:49`（sql_write）、`app/api/v1/feedback.py:147 · record_document_signal`（declared_writer）。
- 这条道今天挂在产品面上：`POST /feedback/document ← app/api/v1/feedback.py:182 · submit_document_feedback`。
- 定时任务这条道现扫为零（🔴 所以本单不写「应该由某个定时任务写」这种话）。
- 从写句往上爬过的坐标：`app/api/v1/feedback.py:147 · record_document_signal`、`app/api/v1/feedback.py:182 · submit_document_feedback`。
- 本表这一跳不需要跨边：写句往上爬就直接见脸，或根本爬不到脸，两种都不靠事件标签撑道。
- 该走哪条写入道：app/api/v1/feedback.py::record_document_signal ← POST /feedback/document（前端正脸在 frontend/src/lib/feedback.js 与 components/SourceCard.vue）。
- 裁定理由：只有采纳 / 驳回一次才加一次计数，演示库没有真人点过。读侧今天把「读成功而零行」当作一种独立状态记账（app/rag/retriever.py 的活动先验诊断格为此留了名目），所以零行不等于读不到。

## 三、V2 三条自述：今天有没有一行真数据
- **#11 告警闭环**：今天**已经有真数据**（R483 造这一句时这里是零，那句今天只算历史引用） —— 现读 `alert_rules` 4 行、`alerts` 4 行。代码侧不是空转：`add_job` 现扫到 1 枚注册（连触发参数与行号进上面那张表），`enterprise-brain-scheduler-1` 日志尾部现数到 24 次 `evaluate_all` executed successfully（间隔现读 `0:05:00`）。⇒ 启用规则今天已在册（这两格的裁定与改判出处见上表），这条链缺的不再是行也不是码，而是**业主口径的规则**——演示样本种子建的那几条不算，见 `alert_rules` 那一格的 why。
- **#17 通知基础能力**：今天**没有一行行为数据** —— 现读 `notification_states` 0 行。收件箱本身有账可列（现读 `pending_approvals` 290 行、`documents` 105 行、`users` 33 行），但没有任何一次已读/忽略落表；告警那一枚候选源今天有账可数（`alerts` 4 行）。⇒ 接口与前端正脸在树，端到端行为读数为零，这句只能报 (乙)。
- **#3 CalculationRun（执行数据血缘）**：今天**没有一行真数据** —— 现读 `calculation_runs` 0 行，且表名在 `app/` 与 `scripts/` 里现扫 0 处引用（连读路径都没长）。⇒ 「每个 Artifact 绑 DatasetVersion、CalculationRun、MetricDefinition」那句仍是后续目标；同一句里的 `metric_definitions` 现读 0 行、`retrieval_traces` 现读 1032 行（库里 `retrieval.completed` 事件 1032 条）。

## 四、尺子自证（已知非空的表跟着进同一张读数表）
| 对照表 | 今日现读 | 昨日底 | 主键顶值（今日现读） | 尺子自证 |
|---|---:|---:|---|---|
| `chunk_vectors` | 1008 | 1008 | 高新技术企业认定管理办法_摘录.txt_2 | 非空，读数件不是空转 |
| `sessions` | 1631 | 1020 | r8-same-dept-a86604 | 非空，读数件不是空转 |

事件面现读（`trace_events` 按 event_type 分组，只 SELECT）：
- `step.progress`：24268 条
- `model.started`：6281 条
- `model.finished`：6280 条
- `tool_call.finished`：5568 条
- `tool_call.started`：5568 条
- `step.started`：1831 条
- `request.started`：1817 条
- `step.finished`：1744 条
- `tool.completed`：1691 条
- `request.completed`：1551 条
- `retrieval.completed`：1032 条
- `agent.result.recorded`：99 条
- `request.failed`：81 条
- 其中 `retrieval.completed`（`retrieval_traces` 今天唯一的闸门事件）：1032 条

## 五、原始读数（机器件，勿手改；`--check` 就用它复现上面每一格）
<!-- R483-READOUT-BEGIN -->
```json
{
  "alert_sweep_log": {
    "container": "enterprise-brain-scheduler-1",
    "days_seen": [
      "2026-10-03"
    ],
    "rc": 0,
    "successful_sweeps_in_tail": 24,
    "trigger_interval": "0:05:00"
  },
  "command": "docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d enterprise_brain -At -v ON_ERROR_STOP=1 -c \"SET default_transaction_read_only = on\" -c \"<SELECT>\"",
  "readout": {
    "agent_runs": {
      "pk": "agent_run_id",
      "pk_max": "trace-ffda51cc5f2645d1ad9495d687d290cf:orchestrator",
      "rows": 2009
    },
    "alert_rules": {
      "pk": "id",
      "pk_max": "4",
      "rows": 4
    },
    "alerts": {
      "pk": "id",
      "pk_max": "4",
      "rows": 4
    },
    "calculation_runs": {
      "pk": "calculation_run_id",
      "pk_max": null,
      "rows": 0
    },
    "chunk_vectors": {
      "pk": "vector_id",
      "pk_max": "高新技术企业认定管理办法_摘录.txt_2",
      "rows": 1008
    },
    "document_activity_signals": {
      "pk": "filename",
      "pk_max": null,
      "rows": 0
    },
    "documents": {
      "pk": "id",
      "pk_max": "131",
      "rows": 105
    },
    "metric_definitions": {
      "pk": "metric_definition_id",
      "pk_max": null,
      "rows": 0
    },
    "notification_states": {
      "pk": "id",
      "pk_max": null,
      "rows": 0
    },
    "pending_approvals": {
      "pk": "id",
      "pk_max": "290",
      "rows": 290
    },
    "retrieval_traces": {
      "pk": "retrieval_trace_id",
      "pk_max": "trace-ff745171edc84698a1abf6039181f774:18",
      "rows": 1032
    },
    "sessions": {
      "pk": "id",
      "pk_max": "r8-same-dept-a86604",
      "rows": 1631
    },
    "trace_events": {
      "pk": "event_id",
      "pk_max": "trace-ffda51cc5f2645d1ad9495d687d290cf:9",
      "rows": 57811
    },
    "user_profiles": {
      "pk": "user_id",
      "pk_max": null,
      "rows": 0
    },
    "users": {
      "pk": "id",
      "pk_max": "52",
      "rows": 33
    }
  },
  "server": {
    "container": "enterprise-brain-postgres-1",
    "database": "enterprise_brain",
    "db_user": "enterprise_brain",
    "server_addr": "local",
    "version": "PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit"
  },
  "taken_at": "2026-10-03T13:29:00+08:00",
  "trace_event_types": {
    "agent.result.recorded": 99,
    "model.finished": 6280,
    "model.started": 6281,
    "request.completed": 1551,
    "request.failed": 81,
    "request.started": 1817,
    "retrieval.completed": 1032,
    "step.finished": 1744,
    "step.progress": 24268,
    "step.started": 1831,
    "tool.completed": 1691,
    "tool_call.finished": 5568,
    "tool_call.started": 5568
  }
}
```
<!-- R483-READOUT-END -->
读数出处：`enterprise-brain-postgres-1` / 库 `enterprise_brain` / 账号 `enterprise_brain` / 服务端地址 `local` / PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 6…；取数时刻 `2026-10-03T13:29:00+08:00`。🔴 宿主 127.0.0.1:5432 上另有野 PG，本件从不直连它。
<!-- R483-TABLE-END -->

## 六、怎么重跑（同一把尺子，两面对）

- 现读 PG + 现扫源码并回写本文件：`python scripts/r483_empty_tables_triage.py --sync`
- 逐字节核盘上这张表（离线，用第五节那份原始读数复现每一格）：`python scripts/r483_empty_tables_triage.py --check`
- 核完再比一遍库里现值，漂了就说漂（要容器在跑）：`python scripts/r483_empty_tables_triage.py --check --verify-live`
- 只打读数不写文件：`python scripts/r483_empty_tables_triage.py --print`；机器可读：`python scripts/r483_empty_tables_triage.py --json`

🔴 本件零产品码：除这枚生成器、本文件与 `tests/test_r483_empty_table_triage_is_derived.py` 三枚新件，全仓零写入。测试件：`tests/test_r483_empty_table_triage_is_derived.py`。
