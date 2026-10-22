# R120 交工（执行层 · 工作树 `be-r120` · 分支 `codex/be-r120` · 基线 `6a70f73`）

状态：**改动全部留在盘上，未 commit**（执行层禁提交）。`git diff --numstat 6a70f73 -- .` 是唯一的
差异口径 —— 中途总控做过一枚保活提交 `ab6d033`，所以 `git status`（对 HEAD）不等于本单的全部改动。
本篇由执行层当场实测生成；凡"前一格报的"都标了来源，不复述未经验证的结论。

## 0. 一句话

四个任务都落地：任务 0 走**"已应用 ⇒ 禁止改 0010"**那条判据，因此 `migrations/**` 一个字没动、
也不需要 0011；任务 1 两件事各修各的并各钉一枚守卫；任务 2 把 `VECTOR_DUAL_WRITE` 透传打通且默认
仍 OFF；任务 3 的 P3 手册已作为 §8 append 进添加计划。**顺带查出并修掉三处会让 P3 第一步就死的
通路缺陷**（见 §4），其中一处是本单自己造的文案漂移。

## 1. 任务 0：判据与凭据

**实测 A —— 原地修改一枚已被应用过的迁移，会不会撞账本？**会。用红用例证明，不靠口头：
`tests/test_r120_clean_install_first_boot.py::test_task0_editing_an_applied_migration_collides_with_the_ledger`
把整个 `migrations/` 拷进 `tmp_path`，只给 `0010` 追加一行**纯注释**，再同步 `manifest.json` 的
SHA-256（⇒ manifest 门过了），然后：

- 对一台**已记旧 digest** 的库跑 `apply_migrations` ⇒ `ValueError: migration checksum mismatch:
  0010`（`app/db/migrations.py` 的 `migration_plan()`），断言逐条钉住：`applied == []`、
  一条 `ALTER DATABASE` 都没发；
- 对一台**还没到 0010** 的库跑同一条命令 ⇒ 顺利完成并落下改后的新 digest。

这个**非对称性**就是"原地改"最阴的地方：下次干净构建看着一切正常，只有已经迁移过的库当场起不来
（`backend/worker/scheduler` 都 `depends_on: migrate`）。要走"原地改 0010"，必须业主同时对**每一台
已应用库**执行 `UPDATE schema_migrations SET checksum = …`。

另一半：改内容不登记 ⇒ `discover_migrations()` 直接拒
（`test_task0_editing_without_the_manifest_dies_at_the_loader`，报错原文
`migration manifest checksum mismatch: 0010_pgvector_chunks.sql`）—— README 那句"漏登记 = loader
直接拒"是真的。

**实测 B —— 真库到底应用过 0010 没有？**

- 唯一可达的库＝宿主原生 PostgreSQL（连接串取主树 `.env`，会话 `read_only=True`，一条写都不发）。
  取证原文：`QUERY_FAILED UndefinedTable 关系 "schema_migrations" 不存在`；
  `current_database=enterprise_brain`、`pg_extension=[plpgsql/1.0]`、public 9 张表里
  **没有** `chunks` / `chunk_vectors` / `vector_scope` / `index_versions`（有 `users` / `documents`）。
  ⇒ 这台开发机的库从来没跑过本项目的迁移，它不是判据的对象。
- compose 里那台真正的 `pgvector/pgvector:pg16`（`services.postgres`）**没有发布宿主端口**
  （全文只有 backend 与 frontend 有 `ports:`），本机不可达，且 docker 属禁碰项 ⇒ **未取到**。
  旁证：`tests/conftest.py:35-37` 自述"Docker 容器根本没发布宿主端口"。
- 历史证据（看板 `docs/handoff/2026-09-15-orchestration-board.md:2534-2538 / :2647 / :2651`）：
  0010 **曾在一次性库 `eb_r90a_probe` / `eb_r90a_after` 成功应用**（`applied=10`、
  `schema_migrations=10 行`，登记的 digest 就是 manifest 里的 `abc4f16d…`），那三枚一次性库
  09-18 已由总控 DROP（`pg_database` 现只剩 `enterprise_brain`）。

**结论（走的判据）**：交付形态是"任何跑过 `scripts/migrate.py` 的客户库都会在账本里记下
`0010 = abc4f16d…`"，而本机无法证明业主真机没跑过 ⇒ **按"已应用"处理，禁止改 0010**。
本单所有修法都在 Python / compose / 文档面上，**不需要前滚 0011**（没有一处需要改 SQL 或 schema）；
`test_task0_left_the_migrations_directory_alone` 把这句话说死成可查证据：digest 仍是
`abc4f16d25fec72e174305c95589c1cb9475245856be0ab0035082279176d6d3`，且不存在 `version > 0010` 的迁移。

**残留（不属本单修法）**：`migrations/0010_pgvector_chunks.sql:216` 那句 `RAISE … 'ALTER DATABASE %I …'`
里的 `%I` 仍是错的（RAISE 不认 `%I`，会原样印出来）。它已被 R90a 的 Python 门**挡在受支持通路之外**
（`test_criterion_1_the_stop_is_a_python_gate_that_runs_before_any_migration_sql` 证明：缺那对变量时
0010 的 SQL 一个字都没送到服务端），只有手动 `psql -f 0010…` 才可达。要修它就等于"原地改 0010"，
必须业主出手（见 §7）。本单用 `test_0010_raise_prefix_defect_is_grandfathered_and_may_not_spread`
钉住存量：**全仓 RAISE 里带 `%I/%s/%L/%O` 的文件集合 == {"0010_pgvector_chunks.sql"}**，再写一处立刻红。

## 2. 任务 1 ①：干净环境首次安装必停

**停在哪一句（静态推演 + 用例固化，未起容器、未建库）**：停在 SQL 之前。链条是

1. 操作者照 `deploy/README.server.md` 复制 `deploy/.env.server.example` → `deploy/.env.server`；
2. 示例里**原本没有** `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION`（基线实测：`KeyError`），而 compose
   写的是 `EMBEDDING_DIMENSION: ${EMBEDDING_DIMENSION}`（无默认）⇒ 插值成空串；
3. `scripts/migrate.py` → `app/db/migrations.py::declared_embedding_profile()` 当场抛
   `EmbeddingProfileError`（基线原文见 §5 的红集），`migration_plan()` 与 0010 的 SQL 都还没开始；
4. migrate `rc=1` ⇒ backend / worker / scheduler 三个 `depends_on: service_completed_successfully`
   的进程全部起不来 ⇒ **整套栈停摆**。

它守的是 `0010:215-218` 那句"没声明宽度就停，不猜"——**该停的地方停得对**，错的是"照你文档装一台
干净机器就必然停"。修法：给部署示例补上那对变量（含"改模型就连宽度一起改、改完必须手动
`scripts/rebuild_index.py`"那句），Python 门与 0010 的判断逻辑一字不改。
`test_criterion_1_a_clean_first_boot_reaches_0010_with_no_hand_written_guc` 是修复证明：只按示例文件
声明的环境跑一遍 `apply_migrations`，0010 真被执行、`ALTER DATABASE` 由 runner 自己下发两条 GUC、
不需要任何人手工 ALTER。

## 3. 任务 1 ②：补救指引指错库

R90a 那句文案有两处指错：① 结尾 `see .env.example` —— 容器根本不读那份（compose 顶部注释
`:7-12` 与 `tests/test_deployment_topology.py::test_containers_read_the_deployment_env_file` 都写明
只读 `deploy/.env.server`）；② `ALTER DATABASE %I` 渲染出库名带尾巴（三次真机现场：看板
`:2536 / :2575 / :2647`，操作者被指去改一个叫 `eb_r90a_probeI` 的不存在的库）。

Python 这侧（①）的修法：`app/db/migrations.py` 新增四个真源常量
（`MIGRATE_ENV_FILE="deploy/.env.server"`、`MIGRATE_ENV_SAMPLE_FILE="deploy/.env.server.example"`、
`HOST_ENV_FILE=".env"`、`MIGRATE_COMPOSE_COMMAND="docker compose --env-file deploy/.env.server
-f docker-compose.yml run --rm migrate"`），文案改成"在跑 `scripts/migrate.py` 的那个环境里设上面
那一个变量 …（部署形态的机器上是 `deploy/.env.server`）"，并且**缺谁只印谁**（不印另一个的值、
不印 768、不拿字符串拼库名）。库名那一半走服务端渲染：`_PROBE_EMBEDDING_PROFILE_SQL` 把
`current_database()` 作为 `database_name` 读回来，`_FORMAT_ALTER_DATABASE_SQL` 用
`format(%s::text, current_database(), %s::text)` 让**服务端**拼引号。

守卫用例（防再漂，任务 ② 要求的钉子）：
`test_criterion_2_every_path_and_command_in_the_guidance_matches_its_truth_source` —— 文案里的文件名
必须 == `migrate` 服务真正的 `env_file`；命令里的服务名/子命令必须 == compose 里那条
`command: ["python", "scripts/migrate.py"]`；示例文件必须真带着那对变量；宿主那句必须和
`scripts/migrate.py` 里 `load_dotenv(".env")` 一致。外加
`test_criterion_2_the_default_database_the_stack_creates_is_the_one_named`（compose 那台
`pgvector/pgvector:pg16` 的 `POSTGRES_DB:-enterprise_brain` 就是文案里的默认库名）与
`test_criterion_2_the_named_database_is_what_the_server_said_not_a_string_join`
（拿 `'ops"; DROP DATABASE brain; --'` 当库名，渲染必须整串带引号原样出现 ⇒ 不是 Python 拼的）。

## 4. 任务 2 + 任务 3：透传与 P3 手册（含三处顺手修掉的通路缺陷）

**任务 2**：`docker-compose.yml` 在 backend / worker / scheduler 各加一行
`VECTOR_DUAL_WRITE: ${VECTOR_DUAL_WRITE:-off}`（+ 注释说明为什么 migrate 不给）；
`deploy/.env.server.example` 与 `.env.example` 各加一段同口径说明，值写 `off`。
migrate / postgres / redis / ollama / frontend 一律不给。`deploy/.env.server` 一字未动。
默认 OFF 由 14 枚用例钉住，其中三条最关键：不设它的安装 ⇒ `vector_mirror()` 返回 None 且
一条 PG 语句都没发；设成 `YE S`/`maybe` 这类不认识的值 ⇒ 走 `pg_store.dual_write_enabled()`
既有那条 `[VectorMirror] … is not recognised` 告警并当关（不新造第二套判定）；三处拼法必须
**一模一样且共 3 次**。

**任务 3**：§8《P3 执行手册》已 append 进 `docs/handoff/2026-09-17-pgvector-adoption-plan.md`
（`git diff --numstat 6a70f73` = **180/0**，纯 append + 我自己那节内的小改，原文 124 行一字未动）。
含：脚本自身 4 条前置、`$DC` 唯一命令前缀、停写→开双写→`printenv` 三处验证→人工全量重建→
逐集合差→带题对比→判读→交回清单→收尾拨回 off→失败对照→红线。U1 给的是**只读实测取法**
（PG 读 `vector_scope.distance_function`，Chroma 读 collection metadata 的 `hnsw:space`，
依据在 `0010:36-56`），U3 给的是两侧（PG 用脚本现拼的零字面量 + 一段服务端自拼 dim 个 0 的 SQL 拿
逐行清单；Chroma 用现成的 `rebuild_index.py --status --json` 的 `zero_vectors_before`）。
本单不切读、不动 `app/rag/retrieval_pipeline.py`、没跑过一次 `compare_vector_recall.py`。

**写手册时查出并修掉的三处通路缺陷**（都在 P3 的必经之路上，不在禁碰清单里）：

1. `scripts/compare_vector_recall.py` 的 `--collection` 默认是 **`enterprise_brain`** —— 那是
   Postgres 的**库名**，Chroma 生产集合叫 `enterprise_docs`（`app/rag/retriever.py:484`）。照手册
   第一步就会死在 `open_chroma()`"取不到 collection"，退出码 2。已改默认值，并钉
   `tests/test_r120_p3_collection_default.py`（默认值 == 写入侧 AST 字面量、不等于 compose 的
   `POSTGRES_DB` 默认、交付面没有任何地方改这两个名）。
2. 同一个脚本把 PG 的 `ip` 与自身/Chroma 的 `inner_product` 直接字符串比较 ⇒ 一台真用 ip 的库会得到
   一条**假的**"[前置不满足] …先核对 0010"。新增 `canonical_distance()` 统一拼法后再比（认不出的值
   原样返回 ⇒ 仍走"不一致 ⇒ 退出码 2"，绝不凑出一个算符继续比）。默认口径 l2 行为一字不变。
   钉法：把 0010 的 CHECK 允许集 `{l2, cosine, ip}` 当成真源逐个映射到 `DISTANCE_OPERATORS`。
3. **本单自己造的漂移**：我往 `deploy/.env.server.example` 补了那对变量，于是
   `docker-compose.yml` migrate 服务上方那句"deploy/.env.server.example … does not yet carry the two
   lines"当场变成假话（操作者照它做会去翻 `.env.example`，而容器不读那份）。已改注释，并钉
   `test_compose_comments_do_not_claim_the_sample_still_lacks_the_pair`。

**两个数字更正**（都是"手册不说清就会被读错"的）：

- 逐题对比默认吃**两份**题集 = 30 + 105 = **135 题**，不是 §3 P3 说的"105 题"。§8.8 显式带
  `--fixture tests/fixtures/business_evaluation_100.jsonl`，并把这件事写在手册里。
- §3 P3 / 跟进单 §22.1 的"55 条 `must_contain` 无出处"是旧数：本树 09-20 用常驻件
  `scripts/check_eval_evidence_coverage.py` **实测 29 行 / 29 词**（主口径 `documents/*.txt` 95 篇，
  退出码 0）。§8.8 要求交回前先复跑，并明写：只要这个数非零，带题那轮就还是影子读的技术差集，
  **不是 R58 判据③ 要的验收证据**。

## 5. 文件清单

| 文件 | numstat | sha256 |
|---|---|---|
| `app/db/migrations.py` | +48/−6 | `49a7253feacc69ad9aaad570a989307aca1bfff4811e56ea45faa44d15289bb8` |
| `docker-compose.yml` | +14/−2 | `28dad09d4713b4ad39cc27e923fb023631b422e2d4f7c9261fa8d5aaa57cd890` |
| `deploy/.env.server.example` | +30/0 | `e169b52bb9fa22cd14b2573dc25829d607c16ea6b2269d52b77786f443d8b6e2` |
| `.env.example` | +15/0 | `17fb6bb40a11f4edc9a4872cedc6f08d204a0b82c6089d9eb12ae89fce9d6472` |
| `scripts/compare_vector_recall.py` | +16/−2 | `ecfffa43cf2408028f30ea2ec362c49632d3aecfd511c8d63eff57221a35380d` |
| `docs/handoff/2026-09-17-pgvector-adoption-plan.md` | +180/0 | `fad854bcea466f29b513ba54f00c2bf963d8bae9f01be490adb53c30f7fd767e` |
| `tests/test_r120_clean_install_first_boot.py` | +531/0（新） | `a440b548069680c06232b3e7742ec091a2a93544097be7e51a0d067256f4a9c2` |
| `tests/test_r120_dual_write_passthrough.py` | +241/0（新） | `7ff80318224e0b6068170691ac5c59c84798a06d02dab9e5a02ccedb461f0cb9` |
| `tests/test_r120_p3_collection_default.py` | +258/0（新） | `d5ad83b02516e21dd8f79e81ae35c7b3638f7ae9273a2a9f4d7ce430b283b12f` |
| 本篇 | 新文件（未跟踪） | — |

前一格建的 `tests/test_r120_clean_install_first_boot.py` / `tests/test_r120_dual_write_passthrough.py`
已被保活提交 `ab6d033` 收录（那枚提交共 6 枚文件）；`tests/test_r120_p3_collection_default.py` 与
本篇**当前仍是 untracked** ⇒ 总控提交时记得 `git add` 这两枚。
另：`ab6d033` 给 `docker-compose.yml` 补了一枚仓库原本没有的行尾换行，本单按基线还原（末尾无换行），
这是它对 HEAD 显示 `M` 的唯一原因之外的全部内容。

## 6. 用例与实跑计数

本单三枚文件 43 条，全绿（下面是全部用例全名，实跑计数在每行文件名后）：

    tests/test_r120_clean_install_first_boot.py  — 15 条
      · test_task0_editing_an_applied_migration_collides_with_the_ledger
      · test_task0_editing_without_the_manifest_dies_at_the_loader
      · test_task0_left_the_migrations_directory_alone
      · test_criterion_1_the_deployed_sample_declares_the_pair_the_migrate_step_needs
      · test_criterion_1_the_two_samples_do_not_disagree_about_the_profile
      · test_criterion_1_the_sample_says_a_new_model_moves_the_width_and_rebuilds
      · test_criterion_1_a_clean_first_boot_reaches_0010_with_no_hand_written_guc
      · test_criterion_1_the_stop_is_a_python_gate_that_runs_before_any_migration_sql
      · test_criterion_2_the_refusal_names_the_real_database_the_real_file_and_the_real_command
      · test_criterion_2_the_named_database_is_what_the_server_said_not_a_string_join
      · test_criterion_2_every_path_and_command_in_the_guidance_matches_its_truth_source
      · test_criterion_2_the_default_database_the_stack_creates_is_the_one_named
      · test_0010_raise_prefix_defect_is_grandfathered_and_may_not_spread
      · test_0010_is_still_right_about_the_refusal_it_only_renders_the_name_wrong
      · test_compose_comments_do_not_claim_the_sample_still_lacks_the_pair
    tests/test_r120_dual_write_passthrough.py  — 14 条
      · test_compose_passes_the_switch_to_every_process_that_writes_vectors
      · test_compose_does_not_leak_the_switch_where_it_does_nothing
      · test_the_pass_through_is_one_spelling_three_times_and_invents_no_value
      · test_the_resolved_default_is_the_state_every_release_shipped_before_this_one
      · test_an_operator_who_says_on_reaches_all_three_processes_unchanged
      · test_no_compose_file_turns_the_mirror_on_by_default
      · test_an_install_that_sets_nothing_issues_no_postgres_statement
      · test_an_unrecognised_value_warns_and_stays_off
      · test_an_empty_value_is_off_without_a_warning
      · test_the_switch_is_read_at_call_time_so_the_pipethrough_is_useful
      · test_only_the_spelling_the_code_reads_is_promised_anywhere
      · test_both_env_samples_ship_the_switch_as_off
      · test_the_samples_say_what_turning_it_on_means
      · test_the_runbook_the_samples_point_at_exists
    tests/test_r120_p3_collection_default.py  — 14 条
      · test_the_write_path_creates_exactly_one_collection_name
      · test_the_scripts_default_collection_is_the_one_the_writer_creates
      · test_the_default_collection_is_not_the_postgres_database_name
      · test_the_scripts_default_chroma_dir_is_the_directory_the_writer_opens
      · test_nothing_in_the_delivery_surface_renames_those_two_defaults
      · test_every_distance_function_0010_allows_has_an_operator_here
      · test_the_script_and_the_library_disagree_by_spelling_not_by_arithmetic
      · test_an_unrecognised_distance_function_cannot_invent_an_operator
      · test_the_default_fixture_list_is_the_two_shipped_question_sets
      · test_the_runbook_names_every_step_that_has_to_happen_in_order
      · test_the_runbook_order_is_stop_write_then_rebuild_then_compare
      · test_the_runbooks_command_prefix_is_the_one_compose_documents
      · test_every_repository_path_named_in_the_runbook_exists
      · test_the_runbook_keeps_the_read_path_out_of_this_ticket

相关回归（禁全量，故取选择集）：

    -k "r120 or r90a or r58 or migration or deployment or r30_config or phase8 or rebuild
        or r21 or r22 or container_stack or deploy"
      ⇒ 406 passed, 2 skipped, 2355 deselected        （2 skip 是既有条件跳过，非本单引入）
    定向集合 r120×3 + r90a + r58 + migration_runner + deployment_guards + pending_approvals
      ⇒ 137 passed
    python scripts/check_no_bom.py ⇒ exit 0（611 枚跟踪文本文件，2 枚白名单）

**基线红（先红后绿的取证）**：把 `app/db/migrations.py`、`docker-compose.yml`、`.env.example`、
`deploy/.env.server.example`、`scripts/compare_vector_recall.py` 五枚还原成 `6a70f73`，只留测试，
实跑得 **14 failed / 15 passed**（全文 `%TEMP%\r120_red_thiscell.txt`）。红名单：

    criterion_1_the_deployed_sample_declares_the_pair_the_migrate_step_needs  KeyError: 'EMBEDDING_DIMENSION'
    criterion_1_the_two_samples_do_not_disagree_about_the_profile             assert {'…':'768'} == {'…':None}
    criterion_1_the_sample_says_a_new_model_moves_the_width_and_rebuilds      assert 'same edit' in '…'
    criterion_1_a_clean_first_boot_reaches_0010_with_no_hand_written_guc      KeyError: 'EMBEDDING_MODEL'
    criterion_2_the_refusal_names_the_real_database_the_real_file_and_the_real_command
            AttributeError: module 'app.db.migrations' has no attribute 'MIGRATE_ENV_FILE'
    criterion_2_the_named_database_is_what_the_server_said_not_a_string_join
            AssertionError: the prose must quote exactly what the server answered
    criterion_2_every_path_and_command_in_the_guidance_matches_its_truth_source
            AttributeError: module 'app.db.migrations' has no attribute 'MIGRATE_ENV_FILE'
    compose_comments_do_not_claim_the_sample_still_lacks_the_pair             EMBEDDING_MODEL must stay in …example
    compose_passes_the_switch_to_every_process_that_writes_vectors            assert 'VECTOR_DUAL_WRITE' in {…}
    the_pass_through_is_one_spelling_three_times_and_invents_no_value         assert 0 == 3
    the_resolved_default_is_the_state_every_release_shipped_before_this_one   KeyError: 'VECTOR_DUAL_WRITE'
    an_operator_who_says_on_reaches_all_three_processes_unchanged             KeyError: 'VECTOR_DUAL_WRITE'
    both_env_samples_ship_the_switch_as_off                                   KeyError: 'VECTOR_DUAL_WRITE'
    the_samples_say_what_turning_it_on_means                                  AssertionError: .env.example

基线上那句 R90a 的原文（任务 1② 要修的文案，一字未改地抓下来）：

    EmbeddingProfileError: Migration 0010 needs a declared embedding profile, and EMBEDDING_MODEL,
    EMBEDDING_DIMENSION are not declared. This runner will not guess a vector width either, so
    DEFAULT_EMBEDDING_DIMENSION is not substituted for the missing value. Set the variable(s) above
    in the environment that runs scripts/migrate.py -- the pair also has to travel together,
    see .env.example -- then migrate again.

P3 那一族另有 5 枚在基线红（还原 `scripts/compare_vector_recall.py` 一枚即得，全文
`%TEMP%\r120_p3_red.txt`）：
`test_the_scripts_default_collection_is_the_one_the_writer_creates`（`assert 'enterprise_brain' ==
'enterprise_docs'`）、`test_the_default_collection_is_not_the_postgres_database_name`
（`assert 'enterprise_brain' != 'enterprise_brain'`）、以及三枚 `canonical_distance` 用例
（`AttributeError: module … has no attribute 'canonical_distance'`）。

## 7. 反证（改坏真源 ⇒ 指名用例与断言原文）

下面 9 枚都是本班当场跑的：临时改坏一个真源 ⇒ 跑选定用例 ⇒ 立刻按 sha256 还原并校验
（每行末尾的 `restored True` 是真的）。

| # | 改坏的地方 | 红的用例 | 断言原文 |
|---|---|---|---|
| A | compose 注释还原成"example … does not yet carry the two lines" | `compose_comments_do_not_claim_the_sample_still_lacks_the_pair` | `compose 还在说示例没带那两行："example is outside this ticket's write domain, so it does not yet\ncarry"` |
| B | `retriever.py` 集合名 → `enterprise_docs_v2` | `the_scripts_default_collection_is_the_one_the_writer_creates` | `assert 'enterprise_docs' == 'enterprise_docs_v2'`（钉子读的是真源，不是抄两份常量） |
| C | §8 里 `$DC stop backend worker scheduler` → `… backend only` | `runbook_names_every_step…`、`runbook_order_is_stop_write…` | `§8 少了照着做就跑不通的一步：['$DC stop backend worker scheduler']`、`ValueError: substring not found` |
| D | §8 里 `app/rag/retriever.py:484` → `retriever_gone.py` | `every_repository_path_named_in_the_runbook_exists` | `§8 引用了不存在的路径：['app/rag/retriever_gone.py']` |
| R1 | `MIGRATE_ENV_FILE` 值改坏 | `criterion_2_every_path_and_command…` | `the guidance names a file the migrate service must actually read` |
| R2 | backend 那行 `:-off` → `:-on` | 3 枚（`one_spelling…` / `resolved_default…` / `no_compose_file_turns_the_mirror_on_by_default`） | `assert 2 == 3`、`('backend', 'on') assert 'on' == 'off'`、`assert 'on' in FALSY_VALUES` |
| R3 | 示例删掉 `EMBEDDING_DIMENSION=` | 3 枚（`deployed_sample_declares_the_pair…` / `two_samples_do_not_disagree…` / `clean_first_boot_reaches_0010…`） | `KeyError: 'EMBEDDING_DIMENSION'` ×2、`assert {'…':'768'} == {'…':None}` |
| R4 | `MIGRATE_COMPOSE_COMMAND` 的 `run --rm migrate` → `backend` | `criterion_2_every_path_and_command…` | `assert ' run --rm migrate' in 'docker compose … run --rm backend'` |
| R5 | compose migrate 的 `env_file` → `deploy/.env.alt` | `criterion_2_every_path_and_command…` | 同 R1 那句 |
| R6 | 示例宽度 768 → 512 | 2 枚（`deployed_sample_declares_the_pair…` / `two_samples_do_not_disagree…`） | `assert '512' == '768'` |
| R7 | 原地改 0010（纯注释）**并同步 manifest** | `task0_left_the_migrations_directory_alone` | `assert 'd33c86942a67…' == 'abc4f16d25fe…'`（另两枚任务 0 用例仍绿：它们量的不是这件事） |

前一格（同一工作树，09-20 18:5x-19:1x）另跑过 compose 默认值、命令、env_file、示例宽度、0010 原地改
五枚反证，结论与上表 R1/R2/R4/R5/R6/R7 逐条对得上（记录 `%TEMP%\r120_refute*.py`）。本班重跑后
未发现出入，未沿用未经验证的数字。

## 8. 未决项 / 必须业主出手

1. **真机 `deploy/.env.server` 补两行**（本班依令不碰该文件）：`EMBEDDING_MODEL=nomic-embed-text`、
   `EMBEDDING_DIMENSION=768`（以真机实际 embedder 为准）；要做 P3 时再加 `VECTOR_DUAL_WRITE=on`。
   没这两行，新装机器照文档装必然停在 migrate。
2. **P3 真机跑一遍**（§8 手册），含 H12（`docker compose build migrate`，镜像落后主树）、
   H11（容器重启才真拿到 GPU）。本班只写手册，一次都没跑。
3. **R58 判据④：备份恢复演练覆盖 PG 向量列** —— 至今没做过，这是"能不能切读"的硬 gate 之一。
4. **`0010:216` 那句 `%I`**：要修就得授权"原地改 0010 + 同步 manifest + 对每一台已应用库补一条
   `UPDATE schema_migrations SET checksum=…`"。本班的建议是**不修**（受支持通路已不可达，改一次的
   代价是把已迁移客户机变成砖）。
5. **`chroma_db/**` 仍被 git 跟踪** —— 反跟踪/删除/`.gitignore` 一律业主本人（H4/H5/H8）。
6. **`must_contain` 无出处清零**：实测 29 条（不是 55）。清零属评测线＋业主，不清零则 §8.8 那轮
   只能当影子读差集，不能当 R58 判据③ 的验收证据。
7. **R59（切读）前置**＝本手册 §8.7/§8.8 的结果；另记一条：`chunk_vectors.classification` 允许
   NULL（`0010:140/161-162`，为镜像 Chroma 缺失的 metadata 键），而 D4=甲裁定"未标注密级按 1 级
   入库"是契约口径。两者在**写入侧**是否已经一致，R59 下推 SQL 之前必须先钉死，本班未查、也没动。
8. **本单没使用 D9 给的 `migrations/**` 授权**（任务 0 判据 ⇒ 改 0010 会让已迁移库当场起不来；
   所有修法都在 Python/compose/文档面上），因此 D9 说的"与 D8 同批、省一次迁移演练"这一条对本单
   **不成立**：本单不需要迁移演练。D8（R88 审计发号）仍按裁定按到窗口之后。

## 9. 边界自证（没做什么）

- 没 commit、没建分支、没 `git add`；没碰 `deploy/.env.server`、没写任何真值/口令。
- 没起容器、没建库、没连真库执行写：唯一一次连库是 §1 那条只读取证（`read_only=True`，
  连接串取主树 `.env`），结果是 `UndefinedTable`。
- 没跑全量 pytest、没跑 `perf_probe_rounds.py` / `collect_evaluation_answers.py` /
  `run_quality_evaluation.py` / `compare_vector_recall.py`（跑分窗口 PID 66588 在跑）。
  跑过 `scripts/check_eval_evidence_coverage.py` 一次：它是只读取证件（零模型/零网络/零连库/
  零起服务，产物只在显式 `--json` 落盘，我没给）。
- 禁碰清单逐条未越：`tests/fixtures/**` 只读（为核 30/105 行数与 121 词条，未改一字节）、
  `frontend/**`、`app/api/v1/chat.py`、`app/agents/tools.py`（含 `_get_pipeline()`，一次都没进）、
  `app/mcp_server.py`、`app/rag/retrieval_pipeline.py`、`app/agents/orchestrator.py`、`.gitignore`、
  `chroma_db/**`（`git status` 里它连一次都没出现过）。
- 反证与基线还原全部按 sha256 校验还原，工作树最终状态 == 交付清单那 9 枚。
