# R570 · 长跑评测窗的断点保护驱动（分片落盘 + 五项指纹闸）

- 施工席：执行层 Erdos（单模型，未切换）
- 工作树：`C:\Users\fengx\PycharmProjects\be-r565`（分支 `codex/be-r565`，基点 `c9243d4`）
- 解释器：`C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`
- 日期：2026-10-02（本班 20:40 起）
- 状态：**零 commit / 零 push / 未并树**；真窗未开（业主令：今晚之前不许开窗）

## §0 盘面与窗态（先立事实，再谈修法）

| 事实 | 现取读数 |
|---|---|
| run12 报废 | 10-02 19:17:39 rc=1：`GATE FAILED: missing 6 fixture id(s)` → `nothing written to …run12-answers.jsonl`，99/105 题的模型调用全白付。凭据 `git show 0e7ec69` 正文 |
| 病根是在册设计 | 采集器只在覆盖闸全过时一次性写盘（见 §1），中途无断点 ⇒ 断 Docker／断网／休眠／杀进程必然整窗重来 |
| 本班窗态 | 全程零模型调用、零容器/镜像动作、零 `run_gate.py`、零 `-n`；`%TEMP\evalrun` 下 `run12*`／`run13*`／`selftest*`／`deadtest*` 一字节未碰 |
| 自测两条路 | `--dry-run`（走采集器自带假 transport）＋ 自造 6/5 题迷你集（题号 `r570-01…`，绝不用在册题号），产物落 `%TEMP\r570_smoke4`，新 tag `r570smk4` |

## §1 根因坐标（现取，非转述；行号会漂，符号名一起给）

| 事实 | 文件:行 ＋ 符号 | 现取 |
|---|---|---|
| 覆盖闸在前 | `scripts/collect_evaluation_answers.py:279 def assert_coverage` | `rg -n "def assert_coverage|def write_answers"` → `279 / 292` |
| 一次性写盘在后 | `scripts/collect_evaluation_answers.py:292 def write_answers` | 同上 |
| 采集器自述无断点 | `scripts/eval_transport_ask_v2.py:21` | 「采集器只在覆盖闸全过时写字节，中途没有断点」 |
| sidecar 逐题追加 | `scripts/eval_transport_ask_v2.py:1266 def _record` → `:1282 SIDECAR.open("a")` | 一题一行，`EVAL_SIDECAR`（`:228`）指哪写哪 |
| 答案件四键 | `scripts/collect_evaluation_answers.py:92 RUNNER_REQUIRED_KEYS` | `id/answer/evidence/latency_ms`，驱动不自造 |

🔴 **跟进单 §150 不在本树**：`docs/handoff/2026-09-15-backend-followup-requests.md` 在 `c9243d4` 上没有 §150；它此刻只在主树工作副本 `:5066-5111`（总控 10-02 20:3x 追加、未提交）。本班按派工词正文＋上面现取的采集器事实施工，§150 那两条纪律照办：① 探针一律不用在册题号；② 收口口径不因分片改变（sidecar 仍一题一行全账，整片重打会留第二行，`--commit` 必须如实报 duplicate、不许悄悄去重）。

## §2 相对参照件 `C:\Users\fengx\AppData\Local\Temp\eb-rescue\R570\resume_window_driver.py`（376 行）改了哪些

| # | 改动 | 为什么 |
|---|---|---|
| 1 | 硬编码绝对路径 → `EB_EVAL_TMP_DIR`／`EB_EVAL_PYTHON` ＋ `--tmp-dir/--repo/--python/--env-file` | 入库件不能带一台机器的路径 |
| 2 | `die()→SystemExit(0)` → 一切「不肯干」走 `Refuse`，REFUSE 一律 rc=2 | 总控要能程序化判；参照件那枚 `exit 0` 派工词明令不许沿用 |
| 3 | `docker exec … printenv INDEX_BACKEND` → `printf SET=%s "$INDEX_BACKEND"` | `printenv` 在变量未设时 rc=1，把「读到空（chroma 的正形）」误报成「问不着」⇒ 判据 ⑦ 的 chroma 半轴现场必假拒 |
| 4 | `hash(tag)` → `sha256(tag)` | `hash()` 受 `PYTHONHASHSEED` 支配，跨进程算不出同一枚端口 ⇒ 单实例闸形同虚设 |
| 5 | 删死码 `write_plan` | 那条路径没人调 |
| 6 | 新增：`--commit` 处指纹复核／dry-run 样本件拒当基线（要 `--allow-sample-merge`）／产物指进仓内当场拒／早停闸在 dry-run 也生效 | 判据 ⑤ 的收口门、④ 的「样本≈满分不许拼基线」、纪律「仓内零写口」、⑥ 要在演练里也能量到 |
| 7 | **本班新撞两处（参照件带过来的真缺陷）**：`scripts/eval_window_shard_driver.py:480` 补跑轮取集 `index not in failed` → `index in failed`；`invoke_collector` 未接 `OSError` ⇒ 改成返回 `(127, …起不来…)` 交早停闸判 | 前者让 `--retries` 整条成死码（补跑轮只重排队已成功的片，随即被 `shard_is_done` 过滤空 ⇒ 失败片永不补）；后者是 `EB_EVAL_PYTHON` 打错时唯一诚实的形状：零产出⇒停窗 rc=3、已完成片留盘，而不是把整窗炸成 traceback |

## §3 七格读数（命令原文 → 末行；同一解释器、串行、`-o addopts= -p no:cacheprovider`）

`T = tests/test_r570_window_shard_driver.py`；命令前缀一律是
`& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8 -m pytest`（下略 `PYTEST`）。

🔴 传输层坑记一笔：本班两次撞同一枚——命令里打「反斜杠＋r570…」会被吃掉反斜杠并把 `r` 变成回车，纸上的路径因此一度断行。修法一律是先写占位符 `@BS@`、落盘前再换成一个反斜杠；纸面自查在**原始字节**上做，不用文本模式（文本模式会先把 CRLF 翻译掉，查不出行尾问题）。

| 格 | 命令原文 | 末行 |
|---|---|---|
| ① 断点粒度到题＋分片不多写一行 | `PYTEST T::test_shard_size_default_is_one_question_per_shard T::test_sharding_writes_exactly_one_sidecar_row_per_question T::test_the_real_collector_is_driven_one_shard_per_question -o addopts= -p no:cacheprovider --basetemp=%TEMP\r570_cells_bt -q` | `3 passed in 3.64s` rc=0 |
| ② 幂等 `to run=0` | `PYTEST T::test_rerun_reports_to_run_zero_and_reasks_nothing …（同参）` | `1 passed in 0.76s` rc=0 |
| ③ 局部失败局部补 | `PYTEST T::test_only_the_missing_shards_get_repaired T::test_a_shard_that_answered_empty_is_not_counted_as_done T::test_a_failed_shard_is_repaired_in_the_next_round …` | `3 passed in 1.28s` rc=0 |
| ④ 合并走覆盖闸／拒合并非零 | `PYTEST T::test_merge_follows_fixture_order T::test_a_short_shard_refuses_merge_non_zero T::test_an_empty_answer_row_refuses_merge T::test_a_duplicate_answer_row_across_shards_refuses_merge T::test_dry_run_samples_are_refused_as_a_baseline T::test_the_exit_code_and_default_tables_are_pinned …` | `6 passed in 1.78s` rc=0 |
| ⑤ 五项指纹闸 | `PYTEST T::test_each_of_the_five_fingerprint_keys_gates_reuse T::test_the_fingerprint_gate_covers_the_merge_door_too T::test_a_closed_docker_still_lets_a_finished_window_be_committed …` | `3 passed in 1.22s` rc=0 |
| ⑥ 连续失联早停保进度 | `PYTEST T::test_dead_streak_stops_the_window_and_keeps_progress T::test_a_collector_that_cannot_spawn_stops_the_window_not_the_driver …` | `2 passed in 1.24s` rc=0 |
| ⑦ 读路径双向真拦＋补法文案 | `PYTEST T::test_expect_backend_pgvector_refuses_when_container_is_empty T::test_expect_backend_chroma_refuses_when_container_is_pgvector T::test_the_read_path_pin_passes_when_it_is_true T::test_an_unreachable_container_is_not_read_as_chroma T::test_a_real_run_refuses_before_touching_the_collector …` | `6 passed in 1.41s` rc=0（枚数 6＝参数化那枚交 pgvector/chroma 两档） |
| 整件 | `PYTEST T -o addopts= -p no:cacheprovider --basetemp=%TEMP\r570_bt_final -q` | `32 passed in 4.92s` rc=0（同数另三遍：`pin1` → `32 passed in 5.07s`、`pin2` → `5.15s`、摘刀正控 → `5.12s`；连跑五遍 `4.71–4.94s` 全绿） |

### §3bis 现场冒烟（真采集器 `--dry-run`，零模型调用；docker 只走 `cat`／`printf` 两枚只读探针）

`PY = & C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`；
`$A = PY scripts\eval_window_shard_driver.py --tag r570smk4 --fixture %TEMP\r570_smoke4\mini6.jsonl --tmp-dir %TEMP\r570_smoke4 --repo .`

| 步 | 命令 | 实取读数 |
|---|---|---|
| S1 | `$A --plan` | `ids=6 shard_size=1 shards=6 done=0 todo=6`；`指纹现取：revision=5e626c5 backend='' probe_ok=True fixture=a1b65223b226 transport=eval_transport_ask_v2:transport`（现取容器 `INDEX_BACKEND` 确为空＝Chroma 读路径） |
| S2 | `$A --run --dry-run` | 六片逐片 `rc=0 collected=1 of 1`，收 `run finished: 6/6 shards complete, 0 open`，rc=0 |
| S3 | 复跑同命令 | `shards=6 already complete=6 to run=0` ＋「一题都不重打（判据 ②）」，rc=0 |
| S4 | 摘掉 `s001`／`s005` 两片 answers 再 `$A --run --dry-run` | `already complete=4 to run=2`，且**只**跑这两片：`[shard 001 r570-02]` `[shard 005 r570-06]`（删除走 python 精确删本席 `%TEMP\` 冒烟产物；PowerShell `Remove-Item` 被本机策略连挡两次） |
| S5 | `$A --commit` | **REFUSE rc=2**：「盘上的片是 dry-run 样本（`answer_source=dry-run`）：样本≈满分，绝不许拼成质量基线」 |
| S6 | `$A --commit --allow-sample-merge` | `committed 6 answers → …\r570smk4-answers.jsonl（顺序 == fixture 原序）`，id 序 `r570-01…06`、`answer` 逐行非空；`sidecar rows=0 unique=0 duplicate=0`；明写「DRY RUN 合并件：结构演练，NOT 质量基线」 |
| S7 | `$A --plan --expect-backend pgvector` | **REFUSE rc=2**：「容器 `INDEX_BACKEND=''`，而这一窗要钉的是 pgvector」＋ fix：「`env_file` 是在容器创建那一刻才解析的：正解 `docker compose up -d --force-recreate`，plain `docker restart` 不重读它」（判据 ⑦ 的补法文案） |
| S8 | `$A --plan --expect-backend chroma` | rc=0，`backend=''` 与 chroma 档一致（空值＝Chroma，不误拒） |
| S9 | 换 `mini5.jsonl`（同 tag）跑三扇门 | `--plan` 只念账不拒：`matches live: NO -> fixture_sha256`；**`--run` REFUSE rc=2**：「`fixture_sha256` 记为 `a1b65223b226…`／现取 `848ec5f2beae…` ⇒ 这些片是在另一种条件下采的，不许复用到 r570smk4」＋「半窗混库拼成一条基线比丢一窗更坏」；**`--commit --allow-sample-merge` REFUSE rc=2**：「合并前指纹复核不过：`fixture_sha256` …」 |

## §4 钉清单（32 枚 ↔ 七格）

① 3（含真采集器 `--dry-run` 端到端一枚）｜② 1｜③ 3（补跑轮那枚含 `--retries 0` 负控）｜④ 6（含覆盖闸三形：短片／空 answer／跨片重复）｜⑤ 3（五枚指纹钥匙逐枚 ＋ 收口门 ＋ 死后端只比三枚离线指纹）｜⑥ 2｜⑦ 5（参数化一枚交两档）｜退出码与默认值口径 1｜单实例闸 1｜件头映射自证 1｜反证牙 a–f 6 ＝ 合计 32。
件头那张「七格 ↔ 用例」表由 `test_the_header_mapping_names_only_real_cases` 双向自证：表里点了不存在的用例⇒红，用例没进表⇒红（R560/R562 那族「手抄引用会漂」的病不许在这枚件上复发；本班第一次重写件头时就抓出两枚不存在的用例名）。

## §5 反证牙

在册 `counter_evidence` 口径 6 枚 ＋ 两枚机械闸（件内内存影子摘刀，仓内不落影子件）：
`PYTEST T::test_counter_evidence_a_blinding_the_fingerprint_gate_reigns_a_mixed_baseline T::test_counter_evidence_b_the_dead_streak_threshold_is_load_bearing T::test_counter_evidence_c_no_refusal_ever_exits_zero T::test_counter_evidence_d_the_driver_never_writes_inside_the_repo T::test_counter_evidence_e_this_file_carries_no_downgrade_marker T::test_counter_evidence_f_no_test_here_shells_out_to_docker T::test_the_header_mapping_names_only_real_cases T::test_the_same_tag_cannot_be_claimed_twice -o addopts= -p no:cacheprovider -q`
→ **`8 passed in 2.19s` rc=0**

物理摘刀 4 把（摘前 → 摘 → victim 红 → 逐字节复原 → sha 复验；备份 `%TEMP\r570_knife2\driver.orig`，并树结案前不删）：

| 刀 | 摘的那一格 | 摘后 sha | victim（在册钉本身） | victim 读数 | 复原 |
|---|---|---|---|---|---|
| K1 | `:480` 补跑轮取集 `in failed`→`not in failed` | `7f4e5f4ab8fc854b` | `test_a_failed_shard_is_repaired_in_the_next_round` | rc=1 `1 failed in 0.99s` | `RESTORED=True` |
| K2 | `invoke_collector` 的 `except OSError` | `d5d243e43ff7d112` | `test_a_collector_that_cannot_spawn_stops_the_window_not_the_driver` | rc=1 `1 failed in 1.19s` | `RESTORED=True` |
| K3 | 全窗单枚 sidecar → 每片各一枚 | `a5ac6b252ca5bf88` | `test_sharding_writes_exactly_one_sidecar_row_per_question` | rc=1 `1 failed in 1.00s` | `RESTORED=True` |
| K4 | `--commit` 处指纹复核摘成 `bad = []` | `a8f50faac26c9c57` | `test_the_fingerprint_gate_covers_the_merge_door_too` | rc=1 `1 failed in 0.94s` | `RESTORED=True` |

摘前与终值同为 `49269a07cb886271`（`equal: True`）；正控（全件复原复跑）**`32 passed in 5.12s` rc=0**。

## §6 邻件不退化（本单借的四族在册件，同解释器同参逐枚末行）

| 件 | 末行 | rc |
|---|---|---|
| `tests/test_collect_evaluation_answers.py` | `12 passed in 0.90s` | 0 |
| `tests/test_r123_hitl_approval.py`（`:205` payload 键集／`:243` sidecar 九键＋甲案七键） | `17 passed in 1.00s` | 0 |
| `tests/test_r181_text_frame_ruler.py` | `21 passed in 1.70s` | 0 |
| `tests/test_r205a_latency_source.py` | `6 passed in 0.79s` | 0 |
| `tests/test_r447_queue_approval_round_and_evidence.py` | `23 passed in 1.44s` | 0 |
| `tests/test_r565_a2_denominator_buckets.py`（本席上单产物，一字节未动） | `20 passed in 1.56s` | 0 |

conftest 自带闸门每次报 `blocked connect attempts to host model port: 0`——没有一发朝模型端口伸手。

🔴 **不消的那笔账**：本班 20:51 前后有一次整件跑出 `3 failed, 28 passed`（点名 `test_dead_streak_stops_the_window_and_keeps_progress`／`test_the_header_mapping_names_only_real_cases`／`test_counter_evidence_e_this_file_carries_no_downgrade_marker`），其中第一枚报出一个常量表里根本不存在的 `5`。随后连跑 5 遍＋摘刀正控＋§3 八组逐格全绿，**未复现**。本班不拿「复跑绿」当结论，做了一件实在事：新增 `test_the_exit_code_and_default_tables_are_pinned`，把退出码表（0/2/3/4）与 `DEFAULT_SHARD_SIZE=1`／`DEAD_STREAK_DEFAULT=4`／五枚与三枚指纹键的**绝对值**钉死——那种「加载到的模块常量 ≠ 盘上源码」的形状，靠 `rc != 0` 这类相对断言抓不到。判定：**未复现、未定因**；若总控复跑再撞，按名取证。

## §7 欠账（未达格逐条点名，不写「基本完成」）

1. **判据 ① 的「分片不多写 sidecar 行」用的是注入假采集器**：它每行只写 3 枚键，作用是计数器；在册九键的口径仍由 `tests/test_r123_hitl_approval.py:243` 钉，本件不复钉也不改它。真采集器在 `--dry-run` 下假 transport **不产 sidecar**，所以 S6 那个 `rows=0` 是「假 transport 无逐题腿」的读数，不许读成「分片没多写」。这一格在真窗上**待量**。
2. **真窗（不带 `--dry-run`）从未跑过**：业主令今晚之前不许开窗。判据 ⑥ 的「死后端」来自桩与坏解释器两条道，不是真断 Docker；`docker exec` 两路全走注入单点（牙 f 证零 docker）。
3. **单实例闸只演了 `acquire_tag_lock` 本身**（同 tag 拒／换 tag 不互挡／端口映射跨进程稳定），两串驱动真并发没演。
4. **`--retries` 退避默认 45 s 在用例里传 0**：真实等待时长没量。
5. **帧账第二件（`-frames.jsonl`）只做了「同名同枚、零增行」的账**（S6 `rows=0`）；逐题分片会不会让帧账多写一行，只在 dry-run 结构上成立，真窗那格欠。
6. **覆盖闸「105 枚唯一 id」只在 6/5 题迷你集上证过形状**；105 全量那一格要么等窗、要么由总控按 §8 代跑。

## §8 代跑清单（窗开／并树之后按原文跑；本席零真窗读数）

批 1 · 本件 32 枚：
`& C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_r570_window_shard_driver.py -o addopts= -p no:cacheprovider --basetemp=%TEMP\r570_bt_final -q` → 期望 `32 passed`，rc=0

批 2 · 邻件（§6 前五行那批在册件）：
`… -m pytest tests\test_collect_evaluation_answers.py tests\test_r123_hitl_approval.py tests\test_r181_text_frame_ruler.py tests\test_r205a_latency_source.py tests\test_r447_queue_approval_round_and_evidence.py -o addopts= -p no:cacheprovider --basetemp=%TEMP\r570_bt_nb -q` → 期望 `79 passed`（12+17+21+6+23），rc=0

批 3 · 真窗三步（**只在窗开、且明写非 dry-run 时**）：
`… python.exe -X utf8 scripts\eval_window_shard_driver.py --tag run13 --shard-size 1 --expect-backend pgvector --plan`
`… 同上 --run`（连续 4 片零产出 ⇒ rc=3 停窗，已完成片留盘；环境修好再 `--run`，最后 `--commit`）
`… 同上 --commit`（覆盖闸不过 ⇒ rc 非 0，绝不静默拼半窗）
判读口径：`revision`／容器 `INDEX_BACKEND`／`fixture_sha256`／transport／`shard_size` 五项任一不符，`--run` 与 `--commit` 两扇门都要拒；`sidecar rows` 应为 105、`duplicate` 应为 0。

## §9 交付形态自查（在原始字节上判；主树 blob 是 LF、盘上是 CRLF，本单按盘上口径落）

| 件 | 行数 | 字节 | CRLF | 裸 CR | BOM | 末行换行 | sha256 前缀 |
|---|---|---|---|---|---|---|---|
| `scripts/eval_window_shard_driver.py` | 690 | 35956 | 690 | 0 | False | True | `49269a07cb886271` |
| `tests/test_r570_window_shard_driver.py` | 736 | 40756 | 736 | 0 | False | True | `4bbb739ef4ccb62d` |
| `docs/testing/r570-window-shard-driver-2026-10-02.md` | 本纸不自我冻结：写下自己的 sha 就会改变它——交回正文给数，并树时由总控现取复核 |
