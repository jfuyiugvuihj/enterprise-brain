# R523 · 模型上报的 cached 计数落库（2026-09-30，执行层，基点 `28e9d50`；第二道补令后定稿）

## 0. 结论一句话

`model_calls` 那一格建好了，值也一路走进了库里：**承载面已就位**，且判据②要的「写进库再读回来」在本单跑通
（写的是在册内存替身 `tests/_r250_fake_postgres.py` 的表，读回来的也是从那台替身里读，不是内存变量冒充）。
第二道补令之前本单只交到「列有了、值在门口被适配器静默丢掉」，那一格现在由
`app/storage/persistence.py:415` 的列元组尾追补平。**未达仍有一格，且不许读成已办**：E3 档
`cached_tokens > 0` 的真机读数只能开窗量，仍待 run10 —— 本纸没有任何一处把它写成量到了。
落库这一格另牵出一枚在册生成件的坐标位移，已按它自己的出路用 `--sync --live-from-doc` 重跑归位
（零 docker、零 psql、零写库）。全程离线：不起服务、不动容器、不重建镜像、不打模型、不碰生产库，
全量回归门按明令未跑。

## 1. 落地形状（六段，逐段可查）

| 段 | 做了什么 | 坐标 |
| --- | --- | --- |
| 列 | `ALTER TABLE IF EXISTS model_calls` ＋ `ADD COLUMN IF NOT EXISTS cached_tokens INTEGER`，另有一枚 `COMMENT ON COLUMN`。可空、无 `DEFAULT`、无回填、无 `UPDATE`、无索引、无 `CHECK`；全文件恰两枚可执行语句 | `migrations/0018_prompt_cache_tokens.sql:64-65`、`:67-73`，`migrations/manifest.json:19`（摘要 `13672cda…`） |
| 声明 | `TRACE_TABLE_COLUMNS["model_calls"]` 末位追加 `cached_tokens` | `app/trace/schema.py:104-108` |
| 写 | `project_span` 的 `model_calls` 分支带上一格 `_first(summary.get("cached_tokens"), current.get("cached_tokens"))`；没报 ⇒ `None`，报了 0 ⇒ 0 | `app/trace/projections.py:307-309` |
| 递交 | 第二道补令新增：适配器那份列元组尾追 `"cached_tokens"`，`_statement` 拼出的 `INSERT` 从此点上这一列。只动这一处，`_statement` 的拼法与 `retrieval_traces` 那块一字未动 | `app/storage/persistence.py:415`（`model_calls` 块现读 `:394-416`；`retrieval_traces` 因此从 `:417` 位移到 `:418`） |
| 论述 | `spans.py` 里 recheck 纸 §4 第 1 条点名的两句在册假话改口；第二次补令又把这同一处两句的后半段再改一次（原文说「落库那半段没通、写在白名单外」，今天已不成立）。现取真坐标：`model_handler.py:613` 读 `prompt_eval_cached_count`、`:631` 交进 reply、`:248` 默认 `None`、`:266-267` 只在报了时才赋值；`:394-395` 今天是 `default_model_budget()`。新文案把「闭合的是替身上的往返、不是客户机的缓存命中」写死 | `app/trace/spans.py:306-314`、`:362-376` |
| 钉 | 四枚新件：迁移两形与摘要、端到端与 NULL/0/无造数、契约口径、反证刀 | `tests/test_r523_prompt_cache_column_migration.py`（11 枚）、`tests/test_r523_cached_count_lands.py`（13 枚，零 xfail）、`tests/test_r523_counter_evidence_teeth.py`（9 枚）、`docs/testing/r523-prompt-cache-tokens-2026-09-30.md`（本纸） |
| 契约 | 裁定 1：整枚**文末纯追加**一节宣布承载面与待读数的口径，并**点名作废** blockers[] 表里那句旧话；旧句原样留在原地，不靠删除来表态。全节零数字（只许 `run10` 这个名次） | `docs/api/contract-v1.md:1728`（旧句仍在）、`:5848-5869`（文末新增 `## Cached-count carrier for …`，且是文件最后一节） |

## 2. 判据逐条 → 凭命令 → 读数（执行层自报）

| 判据 | 结论 | 凭命令 → 读数 |
| --- | --- | --- |
| ① 两条装机路径都不停；列 `IF NOT EXISTS` 且允许 NULL | **做到** | `pytest tests/test_r523_prompt_cache_column_migration.py` → **11 passed**。首装两枚（空账本走完 18 笔并记账）、既有库两枚（`pending == ["0018"]`）、存量行两枚（加列后 `None`，二遍走 `IF NOT EXISTS` 跳过支路且 `warnings == []`）、形状两枚（可空无默认；`kinds == ["ALTER", "COMMENT"]`） |
| ② 一行真数据端到端：reply → counts → 那一列，写进库再读回来 | **做到（第二道补令后转真跑，零 xfail）** | `pytest tests/test_r523_cached_count_lands.py` → **13 passed**。`test_a_reported_count_lands_in_the_column_and_reads_back` 一枚里跑三段：`probe_the_issued_insert_names_the_column`（从替身记下的语句里取出真发给 `model_calls` 的 `INSERT`，列名与参数逐位对齐后断言这一格在、且最后一笔是那枚读数）→ `probe_count_lands_in_the_database_row` → `read_back_the_column`（替身自己那条 `SELECT cached_tokens FROM model_calls WHERE model_call_id = %s`）。转真跑前的咬合也取过读数：补完 `persistence.py` 那格、尚未摘 xfail 时 → **2 failed / 8 passed**（`[XPASS(strict)]` ＋ 明账钉红话 `声明集与适配器列元组差 []，明账写的是 ['cached_tokens']`） |
| ③ NULL 与 0 分得开，任何地方不许写减法 | **做到** | 同上命令：`test_an_unreported_round_is_null_and_a_reported_zero_is_zero` 今天判四段——行上 `None` 对行上 `0`、再从库里读回来仍是 `None` 对 `0`；`test_a_streamed_answer_round_cannot_report_one_and_stays_null`（先复核 R29 流式逐字帧 `"usage" not in frame`，再断言落成 `NULL`）；减法守卫 `test_no_product_source_subtracts_a_cached_reading`（五枚相关件 AST 里带 cached 的 `Sub` 命中 `[]`）＋正控 `test_the_subtraction_guard_bites_on_a_poisoned_copy_of_the_real_source`（命中 `len == 1`） |
| ④ 清单摘要 == loader 用的**文本**摘要 | **做到（裁定 2 已把口径归正）** | 真源 `app/db/migrations.py:176-181` 取的是 `read_text()` 之后的文本再算 sha256，所以判的是文本：`13672cda1ee34adfe3898afdb57694340a42ffa717f70863d72d652e852515ba` == `manifest.json:19` == `MIGRATIONS[...].checksum` == `discover_migrations()` 登记值。原来那枚「字节 == 文本」的判法已撤——它会把**检出形态**当产品判据（本机 `core.autocrlf=true` 且无 `.gitattributes`，落成 CRLF 就假红）。换成两格：字节归一到 LF 后必须与文本同字（只许全 LF 或全 CRLF，不许混排、不许 BOM），另补一把刀 `test_the_digest_survives_both_lf_and_crlf_landings`：同一份内容在临时目录分别落成 LF 与 CRLF，loader 登记摘要仍等于文本摘要；末行反证 CRLF 的**原始字节**摘要与之不等（谁改回字节判法就在这格看见自己判的是形态） |
| ⑤ ≥2 把反证刀，且新守卫先跑正控证明会咬 | **做到（四把刀，九枚件）** | `pytest tests/test_r523_counter_evidence_teeth.py` → **9 passed**。K1 摘 `projections.py` 那格赋值 ⇒ 端到端红且红话点名 `cached_tokens`；K2 把「没报」偷成 `0` ⇒ NULL 探针红；K3 从 `schema.py` 声明集摘列 ⇒ 封条红在 `extra=['cached_tokens']`；**K4（本令新增）从 `persistence.py` 列元组摘列 ⇒ `probe_the_issued_insert_names_the_column` 红，且断言库里那一行确实不再带这一格** —— 这把刀证的正是「半笔不算结案」那一族。每把都配未改源码正控（K4 的正控：同一枚行、同一台干净替身，交给真适配器 ⇒ 探针绿且读回是那枚数）；`test_the_knife_anchors_are_unique_or_the_blade_is_dead` 判四枚锚点各命中 1 枚 |
| ⑥ 真机读数那一格不许造 | **做到** | 见 §0 与 §3：E3 档 `cached_tokens > 0` 的实测格仍欠 run10；分腿口径见 §5。契约三枚钉同咬：`test_the_contract_note_keeps_the_declared_caliber`（旧句**仍在**文内 ＋ 文末那节有作废声明 ＋ 该节是最后一节 ＋ 纯追加 ＋ 零读数）、`test_the_append_teeth_bite_on_synthetic_poisons`（中途插一句 ⇒ 纯追加红；文末后再长一节 ⇒ 「最后一节」红）、`test_the_contract_caliber_guard_bites_on_a_poisoned_note`（塞进 `292 / 543` ⇒ 守卫点名 `["292", "543"]`）。在册那枚 `tests/test_r367_gate_shape_pins.py::test_the_contract_appends_one_section_and_deletes_nothing` 见 §6 |
| 补令自证① 端到端转真跑 | **做到** | 见判据②那一行；INSERT 点名的证据取的是替身记下的**语句字符串与参数逐位表**，不靠「列在 schema 里」推断。另取一枚纯只读直证：对 `PostgresPersistenceAdapter._statement` 直接喂一行（`cached_tokens=257`，连接工厂换成「一旦被调用就抛」的 lambda）→ `列数=18 占位数=18 参数数=18`、`cached_tokens 位序=17` 且对齐到的参数就是 `257`、`ON CONFLICT DO UPDATE` 里含 `cached_tokens = EXCLUDED.cached_tokens`，连接工厂零次调用（所以这条 SQL 没被真发出去过，只是拼出来看） |
| 补令自证② 合跑数（正序与反序） | **做到** | 见 §6 |
| 补令自证③ 行尾清单 | **做到** | 见 §7 |

## 3. 未达（明写，不遮）

| 格 | 状态 | 差在哪 |
| --- | --- | --- |
| E3 档 `cached_tokens > 0` 的真机读数 | **未达（裁定 5：本单不按达标结案）** | 只有开窗跑真流量才量得到。本单不碰模型、不碰容器，所以不交这一格；替身里每一枚数都来自服务端报数或 R29 逐字帧，本单没造也没有 |
| 真·生产 Postgres 上的同一往返 | **未达（裁定 5：本单不按达标结案）** | `tests/_r250_fake_postgres.py` 的自述写得很清楚：它是 hermetic contract check，不是数据库。同一批断言在册由 `tests/test_r250_pg_trace_source_of_truth.py` 在有 `EB_PG_ACCEPTANCE_URL` 时打真库；那一格今天仍要一台安静机器，本单不起服务 |
| 客户机上一枚非 NULL 的存量回填 | **不算未达** | 0018 明写不回填：老行没有这个数是事实。NULL 与 0 在库里保持两种脸，见 §5 第 3 条 |

## 4. 改口账（12 枚在册红 ＋ 2 枚坐标件，本令内全部落地）

🔴 每枚「改前」一律 `git show 28e9d50:<path>` 现取原文（不手抄历史读数）；「改后」= 盘上今日文本。

| 件（base 行） | 改前原文（现取） | 改后 | 读数 |
| --- | --- | --- | --- |
| `tests/test_r250_trace_column_alignment.py:36` | `MIGRATION = Path("migrations/0002_execution_data_lineage.sql")` | 加 `MIGRATIONS_DIR` 与 `_ALTER_ADD`，新增 `_added_columns()`：把迁移目录里所有 `ALTER TABLE … ADD COLUMN …` 并进 DDL 靶子（**枚数不写死**，照 R509 对 `test_r248_artifact_column_alignment.py` 的先例） | `pytest tests/test_r250_trace_column_alignment.py` → **17 passed**（原 2 枚 `[model_calls]` 红全闭） |
| `tests/test_r349_catalog_tail_ledger.py:42` | `CATALOG_TAIL_VERSION = "0017"` | 按账本自己的改口流程第 1 步：两枚字面量 → `0018` / `prompt_cache_tokens`，并把 docstring「现号」那一行连主题一起改写（谁排的、给哪张表落了什么、不回填不给默认） | 与 §4 后五行同跑 → **143 passed**（改口前该组 `1 failed / 142 passed`） |
| `tests/test_r183_184_migration_pair.py:367` | `        "0016",` | 名册补 `"0017",`（R509 那一版从未被指名），散文「那五枚」→「那六枚」并把 0017/0018 的归属一起点上 | `pytest tests/test_r183_184_migration_pair.py` → **12 passed** |
| `tests/test_r120_clean_install_first_boot.py:310` | `        "0017",` | 0010 之后的名册补 `"0018"`，加 `forward[7].name == "prompt_cache_tokens"`，英文失败消息同步点名 R523 | `pytest tests/test_r120_clean_install_first_boot.py` → **15 passed** |
| `tests/test_r146_cached_token_ledger.py:292` | `def test_the_model_calls_row_still_has_no_column_for_it(...)` | 按 R146 自己 docstring 的预告改口（「谁加了列，这条就该红，届时一起改掉」）：改名 `…_carries_the_column_now`，断言反转为 `row["cached_tokens"] == cached` 且列名仍在声明集里，`metadata` 不许当第二本账那句保留 | `pytest tests/test_r146_cached_token_ledger.py` → **16 passed** |
| 绑账本 6 枚（`test_document_catalog_sync` / `test_r190` / `test_r251` / `test_r299`×2 / `test_r46_activity_signals`） | 它们的期望值来自账本 import，文本未改 | 零改动，随账本改口自然回绿 | 同上 **143 passed** 组内；另把 `test_r175_failed_turn` / `test_r183_declared_lane_column` 两枚同族 importer 一起跑，也是 143 passed 那次 |
| `tests/test_r509_artifact_lineage_lands.py:442` | `assert MIGRATIONS[-1] is entry, "0017 必须是当前最新一版，否则并树顺序错了"` | 末位主张交回唯一账本；本件改钉「0017 之后只许站着 `("0018", "prompt_cache_tokens")`」，多一枚仍当场红 | `pytest …::test_the_migration_is_registered_and_loads` → **1 passed** |
| `tests/test_r483_empty_table_triage_is_derived.py`（2 枚） | 生成件里钉的是 `app/trace/projections.py:321` ＋ `app/storage/persistence.py:417` | **顺序按补令走的**：先补 `persistence.py` 列元组，再跑生成器。坐标现扫归位为 `:324` / `:418` | 改前 `--check` → `FAIL … 逐字节不符`，`rc=4`；`--sync --live-from-doc` → `synced … bytes=23108 problems=0`（那枚 bytes 是生成器自己按 LF 汇报的；盘上现形见 §7，内容同一份）；改后 `--check` → `PASS … problems=0`，`rc=0`；`pytest tests/test_r483_empty_table_triage_is_derived.py` → **20 passed** |
| `docs/api/contract-v1.md:1728` | 句中含 `` `model_calls` has no cached column `` | 裁定 1 的形状：本单**不再中间改写**，旧句留在原地，由文末新增的 `## Cached-count carrier for `model_calls`, and the reading it does not yet carry` 点名作废（写「此句自本节起作废，真源见本节」）。回放形状：`@@ -1728 +1728 @@` 与 `@@ -1733,0 +1734,12 @@` 两枚 hunk **已撤销**，现在只剩 `@@ -5846,0 +5847,23 @@` 一枚文末追加（锚点前文 = 文件原最后一行，命中 1 枚），不与主树 `81784da` 的「4b 移到文末」位移争行 | 同上 §2 判据⑥那行；`git diff --numstat` 现取为 `23 0 docs/api/contract-v1.md`（纯追加：零删除；hunk 头现取 `@@ -5846,0 +5847,23 @@`，全文件只此一枚） |

`--sync --live-from-doc` 为什么是这个形状：`--sync` 单跑会 `collect_live_readings(docker_bin)` 起 `docker exec … psql`，
本单明令不许动容器；`--live-from-doc` 是这枚生成器自带的离线复现开关（读数取自文档第五节那份原件），
所以库侧数字沿用已落盘那一次、源码坐标今天现扫。这一点在本纸里写死，不许读成「今天重读过生产库」。

## 5. 分腿口径（判据⑥要求的两句，出处照派工词）

1. **流式答案腿无 usage 可取**：兼容腿流式那一发的逐字帧里根本没有 `usage` 对象（`tests/test_r29_thinking_tax.py`
   D 段；`app/common/model_budget.py:377-379` 的本机复测同形）。所以 `model_calls.input_tokens` / `output_tokens` /
   `cached_tokens` 在流式轮次上都是 `NULL`——「这发说不出来」，不是「缓存没命中」。分腿口径出处：跟进单 §74 四、§81。
2. **非流式形状才有 cached 可取**：原生腿 `done` 帧报 `prompt_eval_cached_count`，兼容腿非流式报
   `usage.prompt_tokens_details.cached_tokens`。两枚都在 0018 之前就被 `spans.model_token_counts` 取到，
   本单补的是从那一格一直走进库里的承载面。
3. `NULL` 与 `0` 是两种读数，并且今天两种脸一路带到库里（`read_back_the_column` 分别读回 `None` 与 `0`）：
   迁移没给默认值、投影没做减法、`_first` 不把 0 折成 `None`，三件事合起来才让它们在库里还是两种脸。

## 6. 执行层自报：跑过的命令与读数

单件（上一批各自独立跑的读数；本批 15 枚合跑 228 passed / rc=0 已把这 15 枚文件全部覆盖一遍，下面逐枚那几行是更早一批的单件数，标注为「上一批」，不与本批混报）：

```
pytest tests/test_r523_prompt_cache_column_migration.py            -> 11 passed
pytest tests/test_r523_cached_count_lands.py                        -> 13 passed（补 persistence 之前：2 failed / 8 passed，见 §2 判据②）
pytest tests/test_r523_counter_evidence_teeth.py                    -> 9 passed
pytest tests/test_r250_trace_column_alignment.py                    -> 17 passed
pytest tests/test_r183_184_migration_pair.py                        -> 12 passed
pytest tests/test_r120_clean_install_first_boot.py                  -> 15 passed
pytest tests/test_r146_cached_token_ledger.py                       -> 16 passed
pytest tests/test_r483_empty_table_triage_is_derived.py             -> 20 passed in 53.20s
pytest tests/test_r509_artifact_lineage_lands.py::test_the_migration_is_registered_and_loads -> 1 passed
pytest <账本组 9 枚（r349 / document_catalog_sync / r175 / r183_declared_lane / r183_184 / r190 / r251 / r299 / r46）> -> 143 passed in 14.36s
python -m pytest tests/test_r367_gate_shape_pins.py tests/test_r523_cached_count_lands.py \
                 tests/test_r523_counter_evidence_teeth.py tests/test_r523_prompt_cache_column_migration.py \
                 -q -p no:randomly   -> 56 passed in 8.03s（rc=0；裁定 1 点名的合跑，本枚纸定稿后取）
同一条命令更早一跑：`1 failed, 55 passed in 6.25s` —— 那枚红不是判据红，是本单自己把契约重写成 LF，
撞上 r367 那枚在册字节钉（`test_the_files_this_ticket_touched_keep_the_repo_line_ending[docs/api/contract-v1.md]`，
报「5869 枚 lone LF」）；归位过程见 §10，归位后同一条命令转 56 passed。
```

合跑（补令自证②：三枚 r523 件 ＋ 12 枚改口件 ＋ 2 枚坐标件 = 15 枚文件）：

```
本批现取（§10 行尾归位之后、**本纸最终文本**上跑的这两序；两序的秒数是最后一批的真数，跑完之后本纸只剩这两枚秒数被改过，没有任何测试读秒数）：

```
正序：python -m pytest tests/test_r523_cached_count_lands.py tests/test_r523_counter_evidence_teeth.py
      tests/test_r523_prompt_cache_column_migration.py tests/test_r250_trace_column_alignment.py
      tests/test_r349_catalog_tail_ledger.py tests/test_r183_184_migration_pair.py
      tests/test_r120_clean_install_first_boot.py tests/test_r146_cached_token_ledger.py
      tests/test_document_catalog_sync.py tests/test_r190_status_failed_domain.py
      tests/test_r251_alert_disposal_migration.py tests/test_r299_notification_states.py
      tests/test_r46_activity_signals.py tests/test_r509_artifact_lineage_lands.py
      tests/test_r483_empty_table_triage_is_derived.py -q -p no:randomly
      -> 228 passed, 44 warnings in 146.31s (0:02:26)，rc=0
反序：同一批文件倒过来喂（数组 Reverse 后原样再喂一次）
      -> 228 passed, 44 warnings in 156.00s (0:02:35)，rc=0
```

枚数从上一批的 226 涨到 228 = 本席按裁定 1(c) 与裁定 2 各补了一把刀：
`test_the_append_teeth_bite_on_synthetic_poisons`（中间改写 / 文末又长一节，两把合成毒）与
`test_the_digest_survives_both_lf_and_crlf_landings`（同一份内容分别落 LF 与 CRLF，摘要仍相等）。
两把都先拿毒跑过正控，不是永不匹配的死牙。44 枚 warnings 是这批文件里既有的 deprecation 噪声，非本单新增断言。
```

同一批更早还取过一趟（226 枚时点）：正序 226 passed in 85.90s、反序 226 passed in 69.15s——枚数与结论一致，
那之后只校正过 §7 里 `spans.py` 的字节数与 §1 契约段行号两处坐标（不动判据）。再往前一次是纸仍写着
补令前文本时取的：`1 failed, 225 passed in 71.99s`，那枚红正是本纸自己的口径钉——红得对，
它抓的就是「纸还没跟着第二道补令改口」。

另有一趟邻件扫（防改口带出连带红，20 枚 persistence / trace / 迁移同族件，含 r469）：
`2 failed, 267 passed, 1 skipped in 26.73s` —— 两枚红全是 §8 明令不碰的 `test_r469_readout_is_generated.py`
（CRLF 检出形态），零枚归本单。

## 7. 行尾清单（补令自证③，`git ls-files --eol` ＋ 盘上字节现取；本表由脚本现生成，非手抄）

| 文件（本树 `be-r523`） | `ls-files --eol` | 本树盘上 | 主树盘上（只读对照） |
| --- | --- | --- | --- |
| `app/storage/persistence.py` | `i/lf w/crlf` | 26671 字节 / 全 CRLF（672 枚）/ 无 BOM | 26641 字节 / 全 CRLF（671 枚）/ 无 BOM |
| `app/trace/projections.py` | `i/lf w/crlf` | 17093 字节 / 全 CRLF（393 枚）/ 无 BOM | 16811 字节 / 全 CRLF（390 枚）/ 无 BOM |
| `app/trace/schema.py` | `i/lf w/crlf` | 6287 字节 / 全 CRLF（195 枚）/ 无 BOM | 5708 字节 / 全 LF（190 枚 lone LF）/ 无 BOM |
| `app/trace/spans.py` | `i/lf w/crlf` | 23405 字节 / 全 CRLF（509 枚）/ 无 BOM | 22052 字节 / 全 CRLF（494 枚）/ 无 BOM |
| `migrations/manifest.json` | `i/lf w/crlf` | 1946 字节 / 全 CRLF（20 枚）/ 无 BOM | 1843 字节 / 全 CRLF（19 枚）/ 无 BOM |
| `docs/api/contract-v1.md` | `i/lf w/crlf` | 471799 字节 / 全 CRLF（5869 枚）/ 无 BOM | 492900 字节 / 全 CRLF（5908 枚）/ 无 BOM |
| `docs/testing/r483-empty-tables-2026-09-29.md` | `i/lf w/crlf` | 23389 字节 / 全 CRLF（281 枚）/ 无 BOM | 23129 字节 / 全 LF（282 枚 lone LF）/ 无 BOM |
| `tests/test_r120_clean_install_first_boot.py` | `i/lf w/crlf` | 29143 字节 / 全 CRLF（572 枚）/ 无 BOM | 28907 字节 / 全 CRLF（568 枚）/ 无 BOM |
| `tests/test_r146_cached_token_ledger.py` | `i/lf w/crlf` | 18982 字节 / 全 CRLF（375 枚）/ 无 BOM | 18423 字节 / 全 CRLF（367 枚）/ 无 BOM |
| `tests/test_r183_184_migration_pair.py` | `i/lf w/crlf` | 31546 字节 / 全 CRLF（606 枚）/ 无 BOM | 31513 字节 / 全 CRLF（605 枚）/ 无 BOM |
| `tests/test_r250_trace_column_alignment.py` | `i/lf w/crlf` | 8797 字节 / 全 CRLF（211 枚）/ 无 BOM | 7035 字节 / 全 LF（180 枚 lone LF）/ 无 BOM |
| `tests/test_r349_catalog_tail_ledger.py` | `i/lf w/crlf` | 12833 字节 / 全 CRLF（233 枚）/ 无 BOM | 12807 字节 / 全 CRLF（233 枚）/ 无 BOM |
| `tests/test_r509_artifact_lineage_lands.py` | `i/lf w/crlf` | 28136 字节 / 全 CRLF（593 枚）/ 无 BOM | 27417 字节 / 全 CRLF（582 枚）/ 无 BOM |
| `docs/testing/r523-prompt-cache-tokens-2026-09-30.md` | `i/ w/lf`（未跟踪） | **本纸，自指不报字节数**（这张表本身就在正文里，任何一次编辑都会让它过期）；形态现读：全 LF、无裸 `CR`、无 BOM |
| `migrations/0018_prompt_cache_tokens.sql` | `i/ w/lf`（未跟踪） | 5214 字节 / 全 LF（73 枚 lone LF）/ 无 BOM |
| `tests/test_r523_cached_count_lands.py` | `i/ w/lf`（未跟踪） | 24805 字节 / 全 LF（533 枚 lone LF）/ 无 BOM |
| `tests/test_r523_counter_evidence_teeth.py` | `i/ w/lf`（未跟踪） | 10918 字节 / 全 LF（233 枚 lone LF）/ 无 BOM |
| `tests/test_r523_prompt_cache_column_migration.py` | `i/ w/lf`（未跟踪） | 12545 字节 / 全 LF（250 枚 lone LF）/ 无 BOM |

另有两枚**本单未碰**、但你自证③会扫到的在册件，行尾纯属检出层：`tests/test_r483_empty_table_triage_is_derived.py`
（`i/lf w/crlf`，13056 字节含 `CR`）、`docs/testing/r469-sandbox-scope-readout-2026-09-28.md`（同形，那两枚红就落在这里，
按裁定 4 不立案、本席未取证）。

🔴 裁定 2 的分工不变：**五枚本单新件不由我转 CRLF**，并树时由总控走 `scripts/r531_worktree_merge.py` 归位；
本单只保证摘要/口径判据与行尾形态脱钩（全部按 `read_text()` 判，见 §2 判据④与 §10）。

一句话给总控：13 枚**已跟踪在册件**已回到本树原生 `w/crlf` 形（与 951 枚未碰件同形，`numstat` 逐行不变），
5 枚**新件**按明令留在 `w/lf` 等你归位；本单交的是 blob 内容，两形都不改变任何产品读数——理由与证据在 §10。

## 8. 本单没做的

- 没 commit、没 `git add`、没 `git checkout` 覆盖任何人的改动。
- 没跑全量回归门（明令）；没动容器、没起服务、没重建镜像、没打模型、没写生产库；`--sync` 走的是自带的
  `--live-from-doc` 离线开关，零 docker、零 psql。
- 没碰 `app/agents/**`、`app/api/**`、`frontend/**`、评测集、`migrations/0001..0017`、四把 A② 尺。
- **没碰 `tests/test_r469_readout_is_generated.py` 与 `docs/testing/r469-*.md`**（补令第二条）。那两枚红
  仍在，归因维持第一次交工的三条现读证据（本树 `i/lf w/crlf`、主树同文件 `i/lf w/lf`、红在字节 66 的 `\r`），
  由总控在主树侧处理。
- `spans.py` 仍只动 recheck §4 第 1 条点名的那两句（本令内第二次改口也落在同一处）；`:349` 那句
  `nodes.py:370/:505` 的错位不在授权两句之内，本单未改，仍欠一次改口。

## 9. 六条裁定的落地（第三道解锁令，本席做完的与没做的）

| 裁定 | 做了什么 | 没做什么 |
| --- | --- | --- |
| 1 契约文末追加＋旧句作废 | 撤销两枚中间 hunk，整份文件先回到 `HEAD` 原文，再追加 `## Cached-count carrier…` 一节（作废声明点名 `native_leg_reports_no_cached_tokens` 那一行）；`test_the_contract_note_keeps_the_declared_caliber` 从「旧句不许出现」翻成「旧句仍在 ＋ 文末作废 ＋ 最后一节 ＋ 纯追加」四格同咬，并补 `test_the_append_teeth_bite_on_synthetic_poisons` 两把合成刀 | 未删任何旧话；未动 blockers[] 那行 |
| 2 摘要按文本 | 撤「字节 == 文本」判法，改「字节归一后 == 文本」＋两形刀 `test_the_digest_survives_both_lf_and_crlf_landings`（临时目录各落一枚，loader 摘要相等；反证 CRLF 原始字节摘要不等） | **未把五枚新件转 CRLF**（归总控 `r531`） |
| 3 r483 生成件 | 不再碰；本席那份 `--sync` 产物留在盘上等主树复跑覆盖 | 未为它改生成件里任何行号 |
| 4 r469 两枚红 | 不立案、不取证 | 未新建 worktree（越界） |
| 5 E3 与真库腿 | §0/§3/§5 的「未达」文字保持原样，两格状态行加裁定号 | 未改成「已闭合」 |
| 6 `app/trace/spans.py:349` | 不动 | 未顺改 |

## 10. §7 行尾归位（第四道裁定后本席新取的一笔，含一枚自我红）

§7 原本写着「本单写过的每一枚文件都是 LF，与 blob 同形」。**那句话现在作废**，因为它把一件事当了归位：

1. 本树未碰的在册文本件检出形态是一致的 CRLF——现取：`git ls-files --eol` 全树分布里 `(i/lf, w/crlf)` 共 **1342** 枚，
   而 `app|tests|docs|migrations|scripts` 五棵里本单未碰的文本件 **w/crlf = 951 / w/lf = 0**。
2. 在册钉 `tests/test_r367_gate_shape_pins.py:411` 直接看原始字节，对 `docs/api/contract-v1.md` 要求
   `lone LF == 0` 且 `
` 枚数大于 0；它的 `REPO = Path(__file__).resolve().parents[1]` 恰恰指向本工作树。
3. 本单这 13 枚被替换过的在册件全部是先前席位用脚本整份重写的，落盘形态全是 lone LF——也就是说：**是本单把它们写漂移了**，
   不是检出层的事。红就红在这里，而且红得对。

处置：把这 13 枚**已跟踪的在册件**恢复成本树原生的 CRLF（逐枚 assert：归位前无裸 CR、`bytes.replace(CRLF, LF)` 往返相等，
再现取 `git diff --numstat` 逐行与归位前一字不差，命令内原话 `numstat_before_eq_after = True`）。
**五枚本单新件不转**（裁定 2 原话，归总控 `scripts/r531_worktree_merge.py` 归位），它们仍是 `w/lf`。

两条限定说清楚，别读过：

- 这一笔**不是产品判据**，是检出形态。本单所有摘要/口径钉已全部改按 `read_text()` 判（裁定 2），
  再怎么落行尾都不会改变一个产品读数。
- 主树盘上同名文件的形态并不统一（只读现取，本席未碰主树）：`app/trace/schema.py`、
  `docs/testing/r483-empty-tables-2026-09-29.md`、`tests/test_r250_trace_column_alignment.py` 三枚在主树是 lone LF，
  其余十枚是 CRLF。§7 逐行给了这两侧的数，铺树时按文件各自归位即可，**本单交的是 blob 内容，不是盘上形态**。

补一刀记在册上（本席自己撞的，不是检出层）：§10 那段补丁落盘后，本纸自己变成过 `w/mixed`——一枚多余 `CR`
混在 191 枚 lone LF 里，git 现读为 `i/ w/mixed`。来源是纸上的补丁文本，不是产品件；已按「全 LF」清干净
（清完现读 `crlf=0`、无裸 `CR`），本表「本纸」那一行是清完之后重取的。这枚恰好印证裁定 2 的说法：**行尾是检出/落盘层的事，
一旦哪枚钉去看原始字节，它就会红**——本单所有判据因此一律走 `read_text()`。

## 11. 契约那枚 hunk 的可重放形状（给总控并树用，本席未碰主盘）

- 改动枚数：全文件**一枚** hunk，零删除 ⇒ 纯追加：`git diff --numstat` 现取 `23 0 docs/api/contract-v1.md`。
- hunk 头现取：`@@ -5846,0 +5847,23 @@ mounted faces added to \`r503-artifact-lineage-face.test.js\`.`
- 插入点：本树 base（`28e9d50`）那份 blob 共 **5846** 行，末行 = `mounted faces added to \`r503-artifact-lineage-face.test.js\`.`；
  本单的 23 行（首行空行，次行 `## Cached-count carrier for \`model_calls\`, and the reading it does not yet carry`）追加在它之后。
- 🔴 与主树 `81784da` 的关系（只读现取，主树 HEAD 现为 `7e1c221`）：主树那份 blob 共 **5908** 行，
  `81784da` 移过来的 R526 那节标题 `### 4b. Caliber cells: …` 正落在 **5848** 行，末行 =
  `` \`tests/test_r526_counter_evidence_teeth.py\`，每把都先在影子端正控跑绿再咬。 ``——
  **两边都往同一处尾点插**，`git merge-file` 在这里必然给你一枚 conflict，不是内容冲突，是同一位置两次追加。
- 建议解法（保序即可，两边一个字都不必改）：**§4b 在前、本单这 23 行在后**，hunk 重新锚成
  `@@ -5908,0 +5909,23 @@`，锚点前文 = 主树现末行那句 `...影子端正控跑绿再咬。`，命中 1 枚。
  次序理由：本单守卫 `contract_cached_note()` 钉的是「本单那一节是文件里最后一枚 `## ` 级节」
  （`text.rindex("\n## ") == start`），而 §4b 是 `### ` 级——`
## ` 四枚字符匹配不上 `
### `，
  所以两序都不咬本单；但把本单放在最后，任何日后新加的「最新一节在文末」钉都不会被本单踩红。
- 主树盘上形态对照（只读）：`docs/api/contract-v1.md` 主树 `i/lf w/crlf`、492900 字节 / 5908 枚 CRLF、无 BOM；
  本树归位后同形（`i/lf w/crlf`）⇒ 这一枚不出现「CRLF 混进 LF 本」。
