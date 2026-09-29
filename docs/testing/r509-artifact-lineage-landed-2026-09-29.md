# R509 · 成果回读链血缘落地 —— 两枚可空列 + 一处写点真源 + 两张脸（2026-09-29，执行层，基点 `8857a8d`）

## 0. 结论一句话

R503 那条链接上了：`artifacts` 今天有 `session_id` / `request_id` 两枚**可空**列（0017），两枚生产写点
各自把自己那一发的轮身份写进列里，列表行与回读面把登记过的键带回去、没登记的**整格缺席**，屏上
「来自哪一次」与「没登记它是哪一次」是两张脸。在册钉按同形加项改口，牙一枚没减；全量门未跑（明令）。

## 1. 落地形状（四段，逐段可查）

| 段 | 做了什么 | 坐标 |
| --- | --- | --- |
| 列 | `migrations/0017_artifact_generation_lineage.sql`：两枚 `ADD COLUMN IF NOT EXISTS ... TEXT`（都可空、都无 DEFAULT、无回填、无 UPDATE）＋两枚 `CREATE INDEX IF NOT EXISTS`（`artifacts_session_idx` / `artifacts_request_idx`）；`manifest.json` 追加一枚摘要 `b60fd974…` | `migrations/0017_artifact_generation_lineage.sql`，`migrations/manifest.json:18` |
| 记录/写 | `ARTIFACT_COLUMNS` 尾追两枚（表序＝适配器序）；`ArtifactRecord` 两枚可空字段；`register()` / `register_artifact()` 收 `session_id` / `request_id` 关键字实参，空值经 `normalize_lineage()` 折成 `None`；`_to_row()` 逐枚点名；PG 适配器列元组同枚数 | `app/storage/artifacts.py:91`（`ARTIFACT_LINEAGE_COLUMNS`，键名唯一拼装处）、`:140`（`_lineage_value`）、`:152`（`normalize_lineage`）、`:288`（`lineage_payload`）、`:376`（`_to_row`）、`app/storage/persistence.py:318-319` |
| 写点 | 两枚既有生产写点，各只一发：`app/api/v1/data.py::_artifact_response` 递 `request_id=principal.request_id`（直连没有会话 ⇒ 那一格留 NULL）；`app/agents/tools.py::_register_artifact` 递 `_tool_turn(config)` 交回的会话号（`configurable.thread_id`）与 `span_identity()` 的 request_id。**没有新增第三枚写点，没有第二份名字拼装** | `app/api/v1/data.py:513`（`_artifact_response`），`app/agents/tools.py:253`（`_tool_turn`）与 `:268`（`_register_artifact`） |
| 读点 | `_coerce_record()` 经 `**normalize_lineage(raw)` 认这两枚**列**（不看 metadata）；`ArtifactRecord.lineage_payload()` 只交回登记过的那几枚；`app/api/v1/artifacts.py::_artifact_row` 只 `row.update(record.lineage_payload())`，本模块里两枚键名一次都没拼 | `app/api/v1/artifacts.py:172`，`app/storage/artifacts.py:288` |
| 屏 | `ArtifactList.vue` 补 `lineageView()` 与第三格 `.artifact-source`：`lineage` 脸说「来自 问答 <原值> · 请求 <原值>」，`unrecorded` 脸说「这一条没有登记它是哪一次产生的」，face 由 `:class` 分派。零新色值（只借 `--text-2/-3` 既有令牌），`theme.css` 一字未动 | `frontend/src/components/ArtifactList.vue:82`（`lineageView`）、`:478-481`（那一格） |

## 2. 判据逐条凭据

| 判据 | 结论 | 读数 |
| --- | --- | --- |
| ① 两形都钉住，退回原状必红 | **做到** | 后端 `tests/test_r509_artifact_lineage_lands.py`：`test_a_registered_turn_comes_back_on_the_row`（有血缘→行上报得出会话与请求）、`test_an_unrecorded_row_omits_both_keys_instead_of_filling_a_slot`（没血缘→12 枚就是 12 枚）、`test_blank_lineage_collapses_to_absent_and_never_to_an_empty_string`、`test_lineage_is_recorded_at_generation_not_borrowed_from_the_reader`（同一行在两个账号眼里一字不差）；六把刀 K1–K6 全红且点名。前端两张脸在 `r503-artifact-lineage-face.test.js` 新增的 `R509 · 真渲染：来源那一格的两张脸`（2 枚）里现形，纯函数与模板分支在 `r509-artifact-lineage-face.test.js`（10 枚），三把刀同样点名 |
| ② 存量行为 NULL 且不丢 | **做到** | `test_an_old_row_reads_back_as_the_same_old_row`（十二枚形状的旧行读回来 owner/created_at/metadata/source_version_id 全在，两枚血缘是 `None`，再写一次也不长出血缘）；`test_the_two_columns_actually_land_and_survive_a_new_process`（`FakePostgres` 的 `rows("artifacts")` 里真有两枚值，换一枚登记表还读得回来） |
| ③ 写点只有一处真源 | **做到** | AST 闸：`test_both_production_writers_call_the_one_registry_entry_point_once`（每枚文件恰好一发 `register_artifact(`，字节仍是第一枚位置参数）、`test_the_agent_writer_names_its_own_turn_and_the_direct_writer_its_own_request`、`test_the_tool_turn_reader_is_defined_once_and_used_once`（`_tool_turn` 定义 1 次、调用 1 次）、`test_the_pair_is_assembled_in_the_storage_module_only`（`normalize_lineage` 的调用点集合 == `{app/storage/artifacts.py}`；读点与两枚写点里没有任何字典字面量拼这两枚键名；`app/api/v1/artifacts.py` 里连 `"session_id"` 这个字符串都没有）、`test_the_adapter_names_the_two_columns_or_the_lineage_never_leaves_the_process` |
| ④ metadata 白名单五枚一字未改 | **做到** | `SCOPE_METADATA_KEYS` 常量与 `register()` 里那枚字面量都没动；`test_the_metadata_allow_list_still_carries_exactly_the_five_scope_keys` + `test_lineage_pushed_through_the_metadata_jsonb_is_still_dropped`（jsonb 里塞 `session_id`/`request_id` 仍然读不回任何血缘）；R503 的 K3 与那把刀**一字未改**，仍绿 |
| ⑤ 在册钉只升不降 | **有偏差，见 §3/§4** | 除了点名的两枚件（R248 列对齐、R503 后端件）之外，还有 6 枚在册件必须跟着改口才不红：R256、R349 尾号账本、R120、R183/R184、R299、catalog-sync，前端 2 枚（R503 前端件、artifact-list）。每一枚都是**同形加项或指名加项**，`toEqual` / `set(...) == set(...)` 一枚没换成包含式，删条 0 枚。另有 `app/storage/persistence.py`、`migrations/manifest.json` 两处写域外必要改动（§4） |
| ⑥ 实跑数 | **做到（执行层自报）** | 见 §5 |
| ⑦ 没做到的明写 | **做到** | 见 §6 |

## 3. 在册钉改口清单（改了哪枚件的哪一行、改前 → 改后）

后端：

1. `tests/test_r248_artifact_column_alignment.py:26`、`:70-77`（点名单）——靶子从「只有 0001 的 CREATE TABLE」改成「0001 建表体 + 0017 的 ALTER」：新增 `LINEAGE_MIGRATION` 常量与 `_added_columns()`，`_artifact_columns()` 末尾 `declarations.update(_added_columns())`。改前该函数只解析 `CREATE TABLE IF NOT EXISTS artifacts (...)`；改后仍解析同一枚建表体，再按 `ALTER TABLE IF EXISTS artifacts\s+ADD COLUMN IF NOT EXISTS (\w+)` 点名追加列，两枚都记成「可空、无默认」。`:80-84` 的双向 `==` 与 `:126` 的 `set(row["metadata"]) == set(SCOPE_METADATA_KEYS)` **原文未动**，枚数由 12→14 是派生结果而不是把等式换成包含式。
2. `tests/test_r503_artifact_lineage_keys.py`（点名单）——
   - `LINEAGE_KEYS` 七枚名字一枚不减，新增 `LINEAGE_ROW_KEYS = {"session_id","request_id"}`（0017 已有列的那两枚）与 `UNBACKED_LINEAGE_KEYS`（仍然无列的五枚）；
   - `probe_no_generating_key_on_the_row` 判的从「七枚里出现任何一枚」换成「仍然无列的那五枚里出现任何一枚」，**红句照旧点名**；这两枚键另由两把新尺管：新增 `probe_backed_lineage_matches_the_record`（行上值必须逐字等于该行存储的列值）与 `probe_lineage_absent_when_unrecorded`（列是 NULL ⇒ 键不许出现）；
   - `probe_row_field_set` 的 `extra` 从 `set(row) - ROW_KEYS` 换成 `set(row) - ROW_KEYS - LINEAGE_ROW_KEYS`，`missing` 那一半与 `ROW_KEYS` 十二枚原文未动；
   - 刀②（`test_blade_k2_...`）改判据不改性质：注入同一枚假 request_id，仍必红，红的尺换成上面两枚新钉（`assert` 两条都要红），docstring 写清「R503 那把 K2 刀原来判的是名字不许出现，今天升级成值必须等于列值」；
   - `test_the_row_publishes_exactly_the_fields_that_have_a_column` 与 `test_no_key_on_the_row_names...` 各加一行反向钉调用，`assert set(row) == set(ROW_KEYS)` 原文未动；对照件 `test_control_the_real_modules_pass_every_probe` 加了一形「登记过的记录必须真回到行上」。
3. `tests/test_r256_artifact_deleted_at_lands.py:81` → `:85`：`assert len(columns) == len(declared) == 12` → `== 14`（枚数继续写死，不从任何一处派生；上面两格名字比对原文未动），docstring 第 4 行补「R509 之后是 14 枚」。
4. `tests/test_r349_catalog_tail_ledger.py:15`、`:42`、`:43`：尾号账本按它自己写在头上的改口流程走 —— `CATALOG_TAIL_VERSION "0016"→"0017"`、`CATALOG_TAIL_NAME notification_states→artifact_generation_lineage`、「现号」那一行换成本版主题。派生式没写，形状钉原文未动。
5. `tests/test_r120_clean_install_first_boot.py:287`、`:300`、`:310`、`:322`：0010 之后的名册从六枚加到七枚（`"0017"` 一项 + `forward[6].name == "artifact_generation_lineage"`），错误消息补 R509。
6. `tests/test_r183_184_migration_pair.py:365-371`：`> NEW_VERSION` 名册补 `"0016"` 一项并把尾号那枚指名成 R509 的 0017；`:530+` 的摘要对账与「一 SQL 一枚目」钉原文未动。
7. `tests/test_r299_notification_states.py:180-182`：原先一条断言同时判两件事（0016 被 apply ＆ 0016 是目录尾号），拆成 `NEW_VERSION in session.applied` + `session.applied[-1] == CATALOG_TAIL_VERSION`，两条都钉，尾号只由账本判。
8. `tests/test_document_catalog_sync.py:166-169`：docstring 的名册 prose 补 0017（断言本来就从 `CATALOG_TAIL_VERSION` 派生，未动）。

前端：

9. `frontend/src/components/__tests__/r503-artifact-lineage-face.test.js`：`VIEW_KEYS` 由 8 枚同形加到 11 枚（`sessionId`/`requestId`/`lineage`），`toEqual` 仍是精确等式；`FORBIDDEN` 拆成「仍然无列的四枚 + 会话出口」原样禁 + 新增 `BACKED`/`probeLineageOnlyFromTheRow`（这两枚键名在组件里只许出现在读行那两行，出现次数 == 名单长度，且 face 不许由 owner/created_at 决定）；P1 第二枚用例从「喂假 session_id 一枚都不搬」改口成「无列的生成键一枚不搬、有列的两枚照原样搬」并新增反向钉；三把刀刀口不变，刀②的红句换到新尺；新增 `R509 · 真渲染：来源那一格的两张脸`（2 枚）。
10. `frontend/src/components/__tests__/artifact-list.test.js:222-232`：`toEqual({...8 枚})` 里同形加三项（`sessionId: ''`、`requestId: ''`、`lineage: {face:'unrecorded',...}`），等式性质未变；点名导入加 `LINEAGE_UNRECORDED_TEXT`。

## 4. 写域越界（每一处都是「不改就假绿」的那种，逐枚点名请总控裁）

1. `app/storage/persistence.py:318-319` —— `_TABLES["artifacts"].columns` 追加两枚列名。**不改就是假绿**：
   `_statement()` 只按这枚元组建 INSERT，多余的 key 被 `values.get(column, {})` 静默丢掉，于是血缘写得进
   内存夹具、写不进生产库。R256 那件（`tests/test_r256_artifact_deleted_at_lands.py:73`）今天就钉着
   「适配器列元组 == `ARTIFACT_COLUMNS`（顺序也算）」，不改它本单一开工就红。改法严格附加：只加两个名字。
2. `migrations/manifest.json:18` —— 新迁移必须登记摘要，否则 `app/db/migrations.py:154` fail closed，
   0017 在客户机上根本不会被 apply（README:7-8 同一句）。纯追加一枚条目，其余 16 行逐字节未动。
3. §3 的 3–10 六枚在册件不在点名范围内，但加两枚真列必然让它们红；每一枚的改口都在上面逐行列出，
   没有一处把等式换成包含式、没有删条、没有 skip。

## 5. 实跑数（**执行层自报**，总控须按同一 HEAD 复跑对账）

后端（点名 31 枚件，`-p no:warnings --tb=line`，Python = 主树 `.venv`，工作树 be-r494）：

```text
tests/test_r509_artifact_lineage_lands.py                     23 passed（本单新钉，含 K1–K6 六把刀）
点名 31 枚合跑                                            335 passed / 10 skipped / 0 failed  in 32.32s
邻域复跑（tests/ 里文件名含 artifact/persistence/migration/contract/catalog 的 46 枚 + 本单件，共 47 枚）
                                                    651 passed / 12 skipped / 0 failed  in 112.84s
```

10 枚 skip（点名跑）逐枚现读为 `EB_PG_BIN_DIR` / `EB_PG_ACCEPTANCE_URL` 未设而跳的 live-PG 件；邻域跑的 12 枚同类。

点名清单：`test_r509_artifact_lineage_lands`、`test_r503_artifact_lineage_keys`、`test_r248_artifact_column_alignment`、
`test_r248_artifact_table_source`、`test_r248_artifact_scope_matrix`、`test_r248_json_writepoints`、
`test_r256_artifact_deleted_at_lands`、`test_artifact_list`、`test_artifact_access`、`test_artifact_tool_urls`、
`test_chart_agent_types`、`test_persistence_adapter`、`test_r84_persistence_cross_process_lock`、
`test_r183_184_migration_pair`、`test_pending_approvals_migration`、`test_r120_clean_install_first_boot`、
`test_storage_contract`、`test_r132_contract_followup_sync`、`test_resource_delete_cascade`、`test_response_hygiene`、
`test_r159_cross_scope_matrix`、`test_r349_catalog_tail_ledger`、`test_document_catalog_sync`、
`test_r299_notification_states`、`test_r175_failed_turn`、`test_r251_alert_disposal_migration`、
`test_r249_dataset_table_columns`、`test_r303_pg_upsert_leg`、`test_postgres_execution_persistence`、
`test_postgres_backup_recovery`、`test_r470_restart_readout_is_derived`。
10 枚 skip 全是按设计跳的 live-PG 件（与基点同类），非本单新增。

前端（`cd frontend`）：

```text
npx vitest run                       Test Files 1 failed / 134 passed (135)   Tests 3 failed / 2706 passed (2709)
npx stylelint "src/**/*.{css,vue}"   148 problems (0 errors, 148 warnings)，--max-warnings=148 exit=0（预算未动）
```

唯一红源是 `src/components/__tests__/r315-artifacts-screen.test.js` 的三枚「ArtifactList.vue 必须与锚点
`d609165` 逐字节相同」钉 —— 本单奉命改这一枚组件，而该件的自我处置写明「把 `BASE_COMMIT` 推进到最后一枚
并写明哪一单授权动了它」（`:90`）。**这一枚常量只能由总控在并树之后落**（现在指向一个还不存在的 commit
就是假绿），本单不替它重录内容或 sha。除此之外前端全绿；新件三枚：`r509-artifact-lineage-face.test.js` 10 枚、
`r503-artifact-lineage-face.test.js` 11 枚（原 8 枚 → P1 一枚改口成两枚 + 新增两张脸 2 枚）、`artifact-list.test.js` 77 枚（枚数未变，只把等式同形加三项）。
改前基线取自 `git show 8857a8d:<path>`，没有拿当前 HEAD 当时针前的形。

## 6. 没做到（不许读成已收）

- **「点得回那一次问答」的出口没接**：会话号已经能上屏，但组件里没有跳 `GET /sessions/{id}` 的链接——
  `frontend/src/router/**` 与 `lib/sessions.js` 在禁碰清单里，硬拼就是 R503 刀③那根假链接。今天屏上只有
  「问答 <原值> · 请求 <原值>」这串身份，不可点。
- **「产物 → 计算」那一腿没碰**：`calculation_runs` 全仓零写点（R503 §3.4），它欠的是生产方不是列，另开单。
- `source_version_id` 仍恒 null：两枚生产写点都没喂它（本单 AST 钉继续把它当"没喂"钉住，谁喂了要回来改钉）。
- 真机迁移没跑、真库没连、容器没碰、`scripts/run_gate.py` 没跑、没 commit、没 `git add`、没 `npm install`；
  0017 只在夹具里被 loader 读过（`test_the_migration_is_registered_and_loads`），落库腿走 `FakePostgres`。
- 全量门没跑 ⇒ 除点名 31 枚 + 邻域 47 枚之外是否有别的件因这两枚列而红，未验证。`r315` 之外应该没有（红点全部来自
  「artifacts 列数/字段数/尾号名册」这三族，三族都已点名改口），但这是推理不是读数。
- 前端两张脸的**视觉层次**只做到「类名与文案都不同 + 一张加粗一张斜体」，没做对比度实测。

## 7. 卫生与不变量（本单实际执行过的）

- 主树 `C:\Users\fengx\PycharmProjects\企业智脑` 零写入；所有改动都在 `be-r494`（`git status --short` 见 §3/§4 清单）。
- `rg -c classification_blocked app/` → 0 命中；`tests/test_r509_...::test_no_new_chroma_writepoint_and_no_classification_blocked` 同判；
  本单不碰向量库，无新 Chroma 依赖或写点。
- `docs/api/contract-v1.md` 纯尾追加 45 行、0 删除（`git diff --numstat` = `45 0`），并树前验过文件里没有 `## R509`。
- `frontend/src/assets/theme.css` 一字未动（新色值为 0，`.artifact-source` 只用 `var(--text-2/-3)`、`var(--t-xs)`）。
- 没起服务、没打模型、没动容器、没连 5432；测试全部走内存 app 与既有 `FakePostgres` double。
