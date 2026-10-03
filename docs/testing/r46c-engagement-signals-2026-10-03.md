# R46 差格 a · 出处「点击／浏览」半张（2026-10-03）

执行层自号 **C**（＝`docs/handoff/2026-09-30-plan-eight-tickets-recheck.md` §3 名册里代号 C 那一行），单号 **R46 差格 a**。
独占工作树 `C:\Users\fengx\PycharmProjects\be-r46c`，分支 `codex/be-r46c`，基点 `a5ba2d7`。
解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`，cwd 一律 `be-r46c`。

🔴 本单**没有 commit、没有 push、没建主树分支、没动容器、没起 dev server、没打 8001/11434、没跑 `scripts/run_gate.py`、没改 `package.json`**。
开工到收尾，run17 真机跑分窗全程在飞（13:22:18 还在起 `collect_evaluation_answers.py --fixture ... run17-s104`），
所以窗内只做了定向单跑与取证；下面 §7 那两张走查图用的是「不起服务器、不 build 整个应用」的组件级台子（做法与边界逐字写在 §7）。
本纸所有自报数字都只算**执行层自报**，总控须按规矩在 dirty 态与并树后的干净树各亲跑一遍。

## 0. 交回盘面（13:3x 现取）

| 项 | 读数 |
|---|---|
| `git rev-parse --short HEAD` | `a5ba2d7`（按派工词不 commit，HEAD 未动） |
| `git status --porcelain` | 11 枚 ` M` ＋ 6 枚 `??`（含本纸 `docs/testing/r46c-engagement-signals-2026-10-03.md`；清单见下两表，13:40:28 现取） |
| 残留 | `?? data/..persistence.json.lock`（见 §9，执行层无删除权限） |

改动（`git diff --numstat`，全部落在写域内）：

```
277	4	app/api/v1/feedback.py
235	3	app/rag/retriever.py
1	0	frontend/src/components/ChatPanel.vue
125	2	frontend/src/components/SourceCard.vue
183	3	frontend/src/lib/feedback.js
2	1	migrations/manifest.json
5	2	tests/test_r120_clean_install_first_boot.py
3	2	tests/test_r183_184_migration_pair.py
3	3	tests/test_r349_catalog_tail_ledger.py
7	2	tests/test_r509_artifact_lineage_lands.py
17	5	tests/test_r523_prompt_cache_column_migration.py
```

新件与 sha256 前 12（原始字节，`Get-FileHash`）：

```
c4cc8f51103d  migrations/0019_document_engagement_events.sql   6447 B   （未跟踪）
262d898c36e3  migrations/manifest.json                          2056 B   （+1 行＝只加自己那一行）
580b5c668791  app/api/v1/feedback.py                           25146 B
ea2594bd61d5  app/rag/retriever.py                            104718 B
8c09da3a92da  frontend/src/lib/feedback.js        26721 B   （本班末改一处过期注释，改前 33839d296c9a，见 §7）
a972743a622b  frontend/src/components/SourceCard.vue           17300 B
dd390a4a7f3b  frontend/src/components/ChatPanel.vue           146352 B
0f23fce504d2  tests/test_r46c_engagement_signals.py           35062 B   （26 枚，未跟踪）
0460fe354a70  tests/test_r46c_engagement_prior.py             28048 B   （30 枚，未跟踪）
f0e4a493302d  tests/test_r46c_counter_evidence_teeth.py       16186 B   （6 枚件内含 8 把刀，未跟踪）
fa4538669e6f  frontend/src/components/__tests__/r46c-source-engagement.test.js  11999 B （15 枚，未跟踪）
```

行尾自证（新建件一律 CRLF、无 BOM）：`0019` = 80/80/80，三枚后端钉与前端件逐枚 `cr==lf==crlf`
（`test_r46c_*.py` 26/30/6 枚件各逐字节量过；前端新件 258/258/258；本纸收尾时同法自证）。

## 1. 开工前两道前提（本席现取，非照抄）

```
$ git -C be-r46c log --oneline -E --grep 'R519([^0-9]|$)' -- frontend
03cd2eb 并树 R519（施工 Lagrange/...，树 be-r519@97724c5，G03 余下那一格＝队列道屏侧读数）...
rc=0
```
⇒ 前提 1 成立：R519 已在 `frontend` 上并树，本单按复核单 §3「C 排 R519 之后」的顺序开工。

```
$ git -C be-r46c ls-files migrations | Sort-Object | Select-Object -Last 4
migrations/0017_artifact_generation_lineage.sql
migrations/0018_prompt_cache_tokens.sql
migrations/manifest.json
migrations/README.md
rc=0
```
⇒ 前提 2 成立：在册最大 00 号 = **0018**，本单只用 **0019**，`migrations/manifest.json` 只加自己那一行
（`git diff --numstat` = `2 1`：一行新增，一行是 0018 那行被迫补的尾逗号；`0020` 没开，`0018` 没抢）。
这一格另有两枚钉点名钉着：`test_the_new_migration_is_the_ledger_tail_and_manifest_gained_exactly_one_line`
与 `test_the_migration_number_is_reserved_for_this_ticket_and_no_other_was_opened`。

## 2. 判据全文（逐字摘录，先摘后做）

**甲·计划书 §5.2 那一行＝跟进单同一行**（`docs/handoff/2026-09-15-backend-followup-requests.md:517`，逐字）：

> | **R46** | 活动信号回填排序（采纳/驳回/点击 → 相关度先验；对齐 `contracts.py:157 score_type` 已备枚举） | ① 有信号后排序变化可测；② **无信号时与现状一致**；③ 隐私：只存计数不存内容 | 不得把用户问题原文写进新表 |

**乙·复核单给「差格 a」的原文**（`docs/handoff/2026-09-30-plan-eight-tickets-recheck.md:257` 起，逐字）：

> ### R46 活动信号回填排序（计划书 L196／判据原文 LF517）
> 判据原文三格：① 有信号后排序变化可测；② **无信号时与现状一致**；③ 隐私：只存计数不存内容。禁：不得把用户问题原文写进新表。
> 标题里那一路「点击」也在判据字面上（采纳/驳回/点击 → 相关度先验）。
> ...
> - 🔴 差格三条：
>   a) **「点击」半张真欠（零实现）**：`app/api/v1/feedback.py:21` 注释明写那一路要前端埋点、等总控另派。我在 `app/`、`migrations/`、`frontend/src`
>      三层按 `click`/`clicked`/`点击` 现查：0011 表里没有第三枚计数列，端点里没有那一路，前端没有埋点，**也没有找到认领它的具号单**。
>      欠的是：新列（要 migration）＋ 新端点或同端点新枚举 ＋ 前端埋点 ＋ 先验源，不是一行能补完的格子。

**丙·名册里代号 C 那一行**（同文件 `:339`，逐字）：

> | C | R46 差格 a：点击／浏览半张 | `app/api/v1/feedback.py:48-49/157/182`、新 `migrations/0019_*.sql`＋`migrations/manifest.json`、`app/rag/retriever.py:586/665`、`frontend/src/lib/feedback.js`、`frontend/src/components/ChatPanel.vue` |

**丁·R521 裁定（这一格今天为什么算欠）**：R46「部分落地（`eaa9af8`＋`4c11efb`/`509c1c7`＋`484536c`），
**『点击』半张零实现且无具号认领单**、真库强度未证、按人限额待业主裁」。

**戊·业主已给的口径（派工词转述，直接采用）**：演示数据／信号本就是合成数据（原话「那些信息本来就是假的在网上找的」），
授权总控自主裁定 ⇒ 本单口径：**「采纳/驳回」＝ `feedback.py` 在册那两枚动作（0011 那一腿，不动）；「点击/浏览」＝本单新增的半张**；
**按人限额那一格不做**（属 D 组另一格），欠业主什么写在 §8 点名。

派工词给的行号坐标（`retriever.py:586/665`、`feedback.py:48-49/157/182`）全部**现取后作废**：
今天真实坐标是 `retriever.py:587 activity_priors()`／`:665 附近` 已被本单扩成 `:767 engagement_priors()`＋`:847 engagement_prior_value()`，
`feedback.py` 写侧从 `_UPSERT_SQL` 那一族扩到 `:289 _INSERT_ENGAGEMENT_SQL`＋`:445 POST /feedback/engagement`。

## 3. 六格逐格：命令原文 → rc → 读数

统一前缀（下面省略）：`$ PY = C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`，cwd＝`be-r46c`，
单跑参数一律 `-o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r46c*" -q`。

### ① 写口：点击／浏览各落一行到新表，载荷只有六格身份·名次·枚举·时刻

新表 `migrations/0019_document_engagement_events.sql`（sha12 `c4cc8f51103d`）七列：
`event_id / username / thread_id / filename / result_rank / event_type / occurred_at`。
**没有** query / question / prompt / answer / excerpt / note / snippet，也没有任何一列装得下自由文本；
三枚文本列各带形状 CHECK（`thread_id ~ '^[A-Za-z0-9_.:#-]{1,128}$'`；`username`/`filename` = `btrim` ＋ 长度上界 64/512 ＋ `!~ '[[:cntrl:]]'`），
`result_rank SMALLINT` 夹 1..100，`event_type` 只认 `click`/`view`。隐私判据钉在**存不下**上，不钉在自觉上。

```
$ PY -m pytest tests/test_r46c_engagement_signals.py ... -q
26 passed        rc=0
```
点名钉：`test_the_table_has_no_column_that_could_hold_a_question`（列名清单逐枚点名 9 个禁用词）、
`test_the_payload_has_exactly_four_slots_and_the_identity_is_not_one_of_them`、
`test_a_hundred_thousand_characters_of_body_is_refused_and_lands_no_row`、
`test_a_question_pasted_into_the_thread_id_slot_is_refused_by_shape`、
`test_the_client_cannot_book_a_click_for_someone_else_or_choose_the_clock`（username／时刻都不在请求体里：身份取鉴权主体、时刻由库 `NOW()`）、
`test_the_rejection_log_names_the_field_and_never_the_value`（与在册 `FORBIDDEN_IN_AUDIT` 同形：`tests/test_r176_alert_denial_audit.py:37`、`tests/test_r251_alert_disposal.py:98`）。

出口 `POST /api/v1/feedback/engagement`（`app/api/v1/feedback.py:445`）：载荷**恰四键**
（`DocumentEngagement`：`filename / event: Literal["click","view"] / thread_id / rank`，`extra="forbid"`，
外面再包一枚 `_reject_extra_engagement_fields` ⇒ 多一个键整条 422，日志只落字段名不落值）。
写语句 `:289` 带 `ON CONFLICT (username, thread_id, filename, event_type) DO NOTHING RETURNING event_id`，
交回 `deduplicated` 读数。🔴 `rank` 本单从 `int` 收成 **`StrictInt`**：本机 pydantic 2.13.4 实测宽松模式会把
`True`→1、`"3"`→3、`3.0`→3 静默折算，那等于替用户记一笔他没打过的账（钉：`test_the_rank_slot_refuses_anything_that_is_not_a_position`）。

### ② 读侧派生：先验从那张表现读派生，代码里零道题目写死

`app/rag/retriever.py`：`engagement_priors()`（`:767`，TTL 30 s／退避 10 s／**fail-open**）→
`engagement_prior_value()`（`:847`）→ `merge_signal_priors()`（`:875`）→ `signal_prior_value()`（`:889`）→
`rank_hits_by_activity()` 唯一改动是把 strength 从 `activity_prior_value` 换成 `signal_prior_value`；
`_apply_activity_prior`（五条读腿出口共用那一枚）用 `getattr` 守第二路读取方，老载体不带这一路照样跑。

冷启动口径（派工词点名要说的这一段）：
- **默认值＝0.0＝不动名次**，且这一路**只抬不压**（返回值恒在 `[0, 界]`）——「没人点过」绝不读成负分，新文档不会被永久压死；
  「两枚计数都是 0」与「这篇压根不在表里」给出同一个 0.0，而它与「读不通」在观测面上分得开（`source` = `store` / `error`）。
- **样本数下限＝`ENGAGEMENT_MIN_SAMPLES = 5`**：`confidence = min(1, (clicks+views)/5)` 按比例往中性收缩，
  攒够之后恒为 1，不再随样本变 ⇒ 第一枚点击的权重必然小于第五枚（钉：`test_the_first_click_is_weaker_than_the_fifth`）。
- 形状：`raw = cap * evidence/(evidence+5) * confidence`，`evidence = 1.0*clicks + 0.5*views`（view 弱于 click），界不放宽。
- 🔴 代码里没有任何一道题的先验：钉 `test_the_snapshot_never_falls_back_to_a_built_in_default_for_a_known_question`
  与 `test_the_prior_depends_on_counts_only_and_not_on_which_document`（换文档名不改分数）。

```
$ PY -m pytest tests/test_r46c_engagement_prior.py ... -q
30 passed        rc=0
```
端到端两枚（不是只测函数）：`test_end_to_end_one_click_moves_the_next_ranking_and_a_control_does_not`、
`test_the_search_call_itself_reorders_when_a_source_was_clicked`（走 `search()` 真调用）。
判据②「无信号＝与现状一致」按在册口径交回**同一对象**：`test_no_signal_returns_the_very_same_list_object_in_the_click_leg_too`；
界不放宽按腿宽 5/12/40 各量：`test_the_shift_stays_one_place_at_leg_widths_5_12_and_40` ＋ `test_the_merge_never_widens_the_shift_cap`。
「不许把读不到冒充没信号」：`test_zero_rows_and_an_unreadable_table_are_two_different_readings`、
`test_a_missing_0019_leaves_the_order_alone_and_says_why`、`test_an_unreadable_click_leg_does_not_erase_the_activity_leg`。
「读腿不带身份」：`test_the_aggregate_statement_carries_no_identity_column`（列清单只有 `filename` ＋ 两枚 `COUNT`）。
「不给 Chroma 新增依赖」：`test_the_click_leg_is_not_a_new_dependency_on_the_vector_store`。

### ③ 权限与越权：点读不到的出处必拒且留账；跨用户读账同治

```
$ PY -m pytest tests/test_r46c_engagement_signals.py -k "denied or refusal or ledger or owner or anonymous or department" -q
（含在下面 26 枚之内）  rc=0
```
- 写侧越权：`app/api/v1/feedback.py:470` 走与在册同一族形状 —— `record_audit(principal, ACTION_VIEW, "failure", resource=filename, reason=reason_code)`
  之后 `raise HTTPException(403, "permission_denied")`；成功那一支 `:472` 才落 `success`。
  钉：`test_clicking_a_source_the_caller_cannot_read_is_refused_and_audited`（403＋拒绝账点名）、
  `test_the_denial_ledger_carries_no_body_and_no_scope_values`（拒绝账里正文／部门值／密级值一个字节都没有）、
  `test_anonymous_and_unlisted_are_refused_with_their_own_codes`、`test_a_principal_without_any_department_refuses_with_authorization_unavailable`
  （**没有部门 ≠ 全都能看**：授权读不出来时拒，不 fail-open 成放行）。
- 读侧越权：`GET /api/v1/feedback/engagement`（`:499`）严格自读 —— SQL 里 `WHERE username = %s` 那一格就是隐私边界本身，
  参数只从鉴权主体取（请求体没有 username 这一格），并且**读到别人的行当场 403 关掉这次读**。
  钉：`test_the_read_leg_has_no_slot_for_another_identity`、`test_the_ledger_only_shows_the_callers_own_reading_history`、
  `test_a_ledger_row_belonging_to_someone_else_closes_the_read`（这一枚就是「跨用户读别人的点击账」的反证位）。
- 去重按人：`test_the_dedup_key_is_per_person_not_global` ＋ 真库 P20（同一行 boss 再点 ⇒ 3 行，不是全局 1 行）。

### ④ 前端接线：真发得出这半张事件；零外部请求；零新依赖；色值预算不调

```
$ cd frontend && node_modules\bin\vitest run src/components/__tests__/r46c-source-engagement.test.js
Tests  15 passed (15)      rc=0     （13:23:45 与 13:3x 各跑一次，第二次是改注释之后）
```
`frontend/src/lib/feedback.js` 的 ENGAGEMENT 一族：`ENGAGEMENT_BODY_KEYS = ['filename','event','thread_id','rank']`，
**不发 username、不发送时间戳**，失败不重试（重试会把「一次动作」刷成多枚账）。
`SourceCard.vue`：click 包在**既有那枚** `@click="emit('preview', row)"` 上（不新增按钮、不改原语闭集，R307 在册钉照绿），
view 走原生 `<details>` 的 `@toggle`；`ChatPanel.vue:2179` 只加一处 `:thread-id="turnKey(msg, i)"`（净 +1 行）。
在册四枚前端件本席亲跑：`r307-sourcecard-uibutton 21 passed` / `r195-source-feedback 20 passed` /
`r197-turn-key-inheritance 16 passed` / `r151-legacy-colors 10 passed`，各 rc=0（合计 67）。

色值预算（现取，不调）：
```
$ rg -n 'max-warnings' frontend/package.json
13:    "lint:colors": "stylelint \"src/**/*.{css,vue}\" --max-warnings=148"      rc=0
$ rg -n 'max-warnings' .github -g '!node_modules'
rg: ...github: 系统找不到指定的文件 (os error 2)                                  rc=2   （本树没有 .github）
$ cd frontend; npx stylelint "src/**/*.vue"          # 改后（现树）
‼ 148 problems (0 errors, 148 warnings)                                          rc=0
$ # 改前：git archive a5ba2d7 frontend/src frontend/.stylelintrc.json | tar -x -C %TEMP%\r46c-lint-base2
$ #      ＋ node_modules 联接（mklink /J），在同一台子上跑同名命令
‼ 148 problems (0 errors, 148 warnings)                                          rc=0
```
⇒ 改前 **148** / 改后 **148**，与 `--max-warnings=148` 恰好相等 ⇒ 本单新增裸色值 **0** 条，预算一个字没调。
零外部域名（静态腿）：
```
$ rg -n 'https?://' frontend/src/lib/feedback.js frontend/src/components/SourceCard.vue frontend/src/components/__tests__/r46c-source-engagement.test.js
rc=1（无命中）
```
运行时腿（组件级，非全站）读数在 §7：请求日志 5 枚、唯一 host = `eb-walk.local`、被拦外部域名 **0** 条。
`package.json`／`frontend/package.json`／`frontend/src/lib/sessions.js`／`theme.css` 全部零字节（`git diff --numstat` 空，rc=0）。

### ⑤ 零改动守住既有口径

```
$ git diff --numstat HEAD -- 'tests/test_r203_*' 'tests/test_r548_*' tests/fixtures
（空）                                                                            rc=0
$ git diff --numstat HEAD -- app/api/v1/chat.py app/common/reliable_queue.py tests/test_r466_* tests/test_r583_* tests/conftest.py tests/test_r253_* scripts/eval_lane_readout.py app/rag/loader.py app/rag/ocr.py app/rag/tables.py app/rag/spreadsheets.py app/trace scripts/r483* docs/handoff pyproject.toml package.json frontend/package.json docker-compose.yml deploy chroma_db .gitignore
（空）                                                                            rc=0
```
🔴 **申报（不是自改）**：本单动了 **5 枚在册件**，全部是「迁移尾号登记动作」，逐处 diff 见 §6。
它们不在派工词点名的不可动清单（`test_r203_*`／`test_r548_*`／评测集／`tests/fixtures/**`）里，
且改法是被 `tests/test_r349_catalog_tail_ledger.py` 自己 docstring 的**四步改口流程**规定的那一条路
（第 1 步改账本两枚字面量＋主题行；第 3 步回各件点名册登记版本号与主题名；第 2/4 步＝import 方与本件主题常量都不动）。
除此之外没动任何一枚在册件的口径，没删钉、没改弱钉、没 skip、没 skipif。

### ⑥ 反证三把（交回八把）

派工词要三把（摘写口／把派生改成写死／摘权限门），实际交了 **8 把**，台账与机械见 §5。
```
$ PY -m pytest tests/test_r46c_counter_evidence_teeth.py -q
6 passed        rc=0
```
其中 `test_two_of_the_victims_are_in_register_nails_not_self_written_ones` 钉住「victim 里必须有在册钉」，
`test_the_tracked_files_are_still_the_bytes_we_came_in_on` 钉住「八把刀跑完，盘上字节与开工时逐字节相同」。

## 4. 真库那一腿（自建库，本席 13:25 亲跑，用完即 drop）

🔴 生产库 `enterprise_brain` **只读纪律**：0019 没在现网跑过，一次都没有。下面全部落在自建库 `eb_r46c_probe2`。

```
$ docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d postgres -v ON_ERROR_STOP=1 -q `
    -c "DROP DATABASE IF EXISTS eb_r46c_probe2" -c "CREATE DATABASE eb_r46c_probe2 OWNER enterprise_brain"   create_rc=0
$ docker cp migrations/0019_document_engagement_events.sql enterprise-brain-postgres-1:/tmp/r46c_0019.sql     cp1_rc=0
$ docker cp $env:TEMP\r46c_probe.sql enterprise-brain-postgres-1:/tmp/r46c_probe.sql                          cp2_rc=0
$ docker exec enterprise-brain-postgres-1 psql -U enterprise_brain -d eb_r46c_probe2 -v ON_ERROR_STOP=1 -q -f /tmp/r46c_0019.sql
migrate_rc=0     ⇒ 迁移在真 PG 上干净落地（ON_ERROR_STOP=1 下不红）
$ docker exec ... psql -d eb_r46c_probe2 -f /tmp/r46c_probe.sql                                               probe_rc=0
$ docker exec ... psql -d postgres -v ON_ERROR_STOP=1 -q -c "DROP DATABASE eb_r46c_probe2"                    drop_rc=0
$ docker exec ... psql -d postgres -Atc "select datname from pg_database where datname like 'eb_%'"
eb_r59_sandbox   ⇒ 本单的库已回收（那一枚是别人的，未动）
```

结构清单（现取）：`columns=7`；约束 7 枚 = 5 枚 CHECK（rank 1..100 / event_type ∈ {click,view} /
thread_id 形状 / username btrim·1..64·无控制字符 / filename btrim·1..512·无控制字符）＋ PK ＋
`UNIQUE document_engagement_events_once_per_actor_turn_source`；索引 4 枚（pkey、unique、filename_idx、username_idx）。

P01–P21 读数（全文捕获 `C:\Users\fengx\AppData\Local\Temp\r46c-pg-probe2.txt`）：

| 探针 | 读数 |
|---|---|
| P01 合法 click | `INSERT 0 1` |
| P02 同人同题同出处同动作重打（带 ON CONFLICT） | **`INSERT 0 0`** ⇒ 去重在库里成立，刷不出第二行 |
| P03 view 是第二枚动作 | `INSERT 0 1` |
| P04–P15 十二枚非法形状 | **12 枚全部被具名 CHECK 拒**：rank_check ×2（0／101）、event_type_check ×1（`hover`）、thread_id_check ×4（含空格／中文题原文／换行／129 字）、filename_check ×4（换行／前导空格／513 字／**十万字正文**）、username_check ×1（制表符） |
| P16 落行数 | `landed_rows = 2` ⇒ 被拒的十二枚**没留下半行** |
| P17 排序侧那条聚合 SELECT 逐字跑 | `finance-q3.txt \| clicks=1 \| views=1` |
| P18 自读账腿（alice） | 2 行（view + click，带 rank 2） |
| P19 别人的账腿（bob） | `bob_rows = 0` |
| P20 boss 再点同一枚 | `INSERT 0 1` → `rows_after_boss = 3` ⇒ 去重**按人不全局** |
| P21 没人点过那一格 | `clicks=2 views=1 untouched=f` ⇒ 无动作与有动作在聚合读腿上分得开 |

🔴 十万字正文塞进 filename 那一格：被 `filename_check` 拒，且 P16 证明它没落库 —— 判据①「正文一个字都进不来」是**结构成立**，不靠自觉。
（P08 那一枚「中文题原文塞 thread_id」同理被 `thread_id_check` 拒。）

## 5. 反证台账（八把，摘前→摘后 sha256 前 12 逐字节相同）

机械：`install_mutation`（借自在册 `tests/test_r466_*` 那一族，只替换变了的那几枚顶层绑定）＋ `overlay.ShadowEdit`；
K7 走 R253 的影子根（盘上 `.sql` 全程只读）。每把刀都先跑正控（不摘任何刀时 victim 必须绿），锚点命中数 ≠ 1 当场红。

| 刀 | 落点（摘什么） | victim | 摘前 → 摘后 |
|---|---|---|---|
| K1 | `feedback.py` 写口：`if not unexpected: return` 改成恒 return（四格以外的字段不再被拦） | `w1.rejection_log_names_fields` | `580b5c668791 → 580b5c668791` |
| K2 | `retriever.py` 派生改成写死：`clicks = 7 / views = 3` | `w2.neutral_when_nobody_clicked`、**在册 `r46::no_signals_returns_the_same_object`** | `ea2594bd61d5 → ea2594bd61d5` |
| K3 | 权限门摘掉：`if not scope.allows(row)` → `if False` | `w1.denial_is_refused_and_audited`、**在册 `r46::cross_department_batch_is_denied`** | `580b5c668791 → 580b5c668791` |
| K4 | 跨用户闸摘掉：别人的行回来了也不关账 | `w1.foreign_ledger_row_closes_the_read` | `580b5c668791 → 580b5c668791` |
| K5 | 样本数下限摘掉：`confidence = 1.0`（第一枚点击就替整篇定序） | `w2.first_click_weaker_than_fifth` | `ea2594bd61d5 → ea2594bd61d5` |
| K6 | 合并后界放宽成两名：`cap = ... * 2` | `w2.merge_keeps_one_place_cap` | `ea2594bd61d5 → ea2594bd61d5` |
| K7 | 0019 那枚 `CHECK (result_rank >= 1 AND result_rank <= 100)` → `CHECK (1 = 1)` | `w1.check_family_pairs_with_0011` | `c4cc8f51103d → c4cc8f51103d` |
| K8 | 写完不作废快照：`pass`（回执与排序两本账分家） | `w2.fresh_click_invalidates_snapshot` | `580b5c668791 → 580b5c668791` |

派工词只要三把（摘写口／把派生改成写死／摘权限门）＝ K1／K2／K3，其余五把是同一机械顺手加的。
八把跑完另有两枚自证：`test_the_tracked_files_are_still_the_bytes_we_came_in_on`（盘上字节没变）、
`test_the_live_module_is_back_to_the_disk_behaviour_after_every_window`（内存里的模块回到盘上行为）。

## 6. 在册件登记动作（五处，逐处点名）

全部按 `tests/test_r349_catalog_tail_ledger.py` docstring 里那套四步改口流程走：第 1 步改账本两枚字面量＋主题行；
第 3 步回各件点名册登记；第 2 步（import 方一个字不动）与第 4 步（各件自己的主题版常量不跟尾号改）照守。

| 件 | 改了什么 |
|---|---|
| `tests/test_r349_catalog_tail_ledger.py` | `CATALOG_TAIL_VERSION "0018"→"0019"`、`CATALOG_TAIL_NAME prompt_cache_tokens→document_engagement_events`、docstring「现号」那一行换成本版主题（唯一账本，按设计就该由它记尾号） |
| `tests/test_r120_clean_install_first_boot.py` | 首装前滚名册加 `"0019"` 一枚，并把 `forward[8]` 的表名点上（`document_engagement_events`）；注释「八枚→九枚」 |
| `tests/test_r183_184_migration_pair.py` | 「0012 之后只许站着被指名的那六枚」改成七枚并点上 0019（R46c） |
| `tests/test_r509_artifact_lineage_lands.py` | 0017 之后的名册由一枚变两枚：`[("0018", prompt_cache_tokens), ("0019", document_engagement_events)]`，失败消息同步点名 |
| `tests/test_r523_prompt_cache_column_migration.py` | pending／applied 名册加尾号那一枚（`[NEW_VERSION, CATALOG_TAIL_VERSION]`）＋ import 账本；函数名 `test_a_database_at_0017_has_0018_as_its_only_pending_step` 里的 only 语义在 docstring 里改窄成「0018 之前不夹别人」并记账 —— **没改名**（本席现取 `rg -n only_pending_step --glob '!node_modules'` 全仓只两处：定义处 `tests/test_r523_prompt_cache_column_migration.py:133` 与本纸；上一班纸面那句「改名会牵动 r509/r523 交工纸坐标」**不可复现，已在本文更正**） |

本席亲跑这五枚＋同族连续性批（12 枚件，含 `test_document_catalog_sync`／`test_r183_declared_lane_column`／
`test_r190_status_failed_domain`／`test_r251_alert_disposal_migration`／`test_r299_notification_states`／`test_r523_*` 三枚）：

```
$ PY -m pytest tests/test_document_catalog_sync.py tests/test_r349_catalog_tail_ledger.py tests/test_r120_clean_install_first_boot.py `
    tests/test_r183_184_migration_pair.py tests/test_r183_declared_lane_column.py tests/test_r190_status_failed_domain.py `
    tests/test_r251_alert_disposal_migration.py tests/test_r299_notification_states.py tests/test_r509_artifact_lineage_lands.py `
    tests/test_r523_prompt_cache_column_migration.py tests/test_r523_counter_evidence_teeth.py tests/test_r523_cached_count_lands.py `
    -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r46cA2" -q
155 passed, 16 warnings in 11.19s      rc=0
```

另两批（前一班 13:12／13:13 跑，本席未复跑，只算执行层自报）：
批 B1（`test_r46_*`／`test_r152_*`／`test_r153_*`／`test_r191_*`／`error_code_vocabulary`／`test_r525_*` 六枚）= **187 passed / 2 skipped** rc=0；
批 B2（`test_r203_*` 四枚／`test_r548_*` 两枚／`test_r251_alert_disposal`／`test_r299_notification_inbox`）= **178 passed** rc=0。

## 7. 前端两张走查图 + 运行态请求日志（组件级台子，边界写清楚）

台子（一次性，全在 `%TEMP%\r46c-walk\`，**没往工作树里落一个字节**）：
`vite build --config`（lib 模式，只打 `SourceCard.vue` ＋ `lib/provenance.js` ＋ `theme.css` 这一枚入口，
outDir 指 TEMP，`built in 194ms`，总 CPU 秒级）⇒ Chromium 里 `context.route` 从磁盘 fulfill，
**不起 dev server、不 build 整个应用、不登录、不打 8001**；`/api/**` 由 `page.route` fulfill 后端真实回执形状。
组件是**真件**（`SourceCard.vue` 真模板、真 scoped 样式、真 `lib/feedback.js` 真字节），
只有父级布局是 harness 给的固定宽度壳子。

```
$ node shot.mjs $env:TEMP\r46c
requestCount      = 5
uniqueHosts       = ["eb-walk.local"]        ⇒ 外部域名 0 条
blockedExternalHits = []
apiRequests       = ["POST .../api/v1/feedback/engagement", "POST .../api/v1/feedback/engagement"]
postBodies        = [{filename:"差旅费报销制度-2026.pdf", event:"click", thread_id:"s-42#3", rank:1},
                     {filename:"采购管理办法.docx",       event:"view",  thread_id:"s-42#3", rank:2}]
previewEmitLog    = ["差旅费报销制度-2026.pdf"]           ⇒ 既有那枚 preview 照旧发得出（记账没挡用户看原文）
shot_rc=0
```
🔴 两枚 POST 的载荷**各自只有四枚键**，问句／答案／命中句／部门值／密级值一个字节都不在里面；时刻与身份都不在前端手里。

两张图（点击前后各一张，走查用）：

![点击前：三行出处，每行一枚「展开这处详情」折叠头与既有两枚评价按钮](C:\Users\fengx\AppData\Local\Temp\r46c\engagement-before-click.png)

![点击后：第一行「打开原文」已发出 click，第二行 details 已展开并落 view（本轮第 2 名／出处 doc-purchase／相关度）](C:\Users\fengx\AppData\Local\Temp\r46c\engagement-after-click.png)

改前／改后各一处的说明：`click` 那枚**故意不画新的可见态**（不新增按钮、不新造可见文案，R307 那枚原语闭集钉着），
所以第二张图上的可见变化只有第二行展开；第一行点击的可见效果在父级原文抽屉里，不在本台子范围内 —— 它的字节证据就是上面那枚 postBody。

本班另修一处**过期注释**（不是行为改动）：`frontend/src/lib/feedback.js` 里那句「而后端那一格是 `rank: int`」
在后端收成 `StrictInt` 之后成了假话，已改成「`rank: StrictInt`，宽松 int 会把 `True`／`"3"`／`3.0` 静默折成整数」。
sha12 `33839d296c9a → 8c09da3a92da`，numstat 仍 `183 3`，行尾 CRLF 546/546/546 无 BOM；
改后同名前端件复跑 15 passed rc=0，`stylelint "src/**/*.vue"` 不吃 `.js`，148 那个数不受影响（已复量）。

## 8. 没验的格子（如实列，不猜过去）

1. 🔴 **全站 SPA 运行态那一腿未量**：派工词禁 dev server／禁 build 整个应用／禁动容器，所以 §7 只到**组件级**运行态。
   本席 13:41:03 现取：run17 已收（`run17.shards` 末笔 13:23:28，`Get-CimInstance` 里 eval/`launch_run17`/`eval_window_shard_driver` 进程数 = **0**），
   但同机此刻有**另一枚执行层在跑 pytest**（13:40:37 起 `tests/test_r583_roster_reconciles_the_inventory.py` 等，正是本单禁碰的 `test_r583_*` 那一族）
   ⇒ 机器不算安静，本席仍不在这台子上做 build／全站走查；这一腿留给总控或下一班，取法照下面两行。
   全站腿的正解（窗口收后）：`cd frontend && npm run build` ⇒ 走在册 `frontend/tests/visual/support/static-site.js`
   （`hostDistFromDisk` 从磁盘 fulfill、`BLOCKED_HOSTS` abort、`/api/**` 喂 401），
   在真登录态里走一遍「问一题 → 点出处 → 展开详情」，同时交回 `page.on('request')` 的 host 名册与两张图。
   **不需要**起 dev server，也不需要打后端。
2. **真库强度校准**（复核单差格 b，D 组那一格）：本单只证到「新表在真 PG 上的形状／去重／聚合读腿」（§4），
   没量真并发打点次序、没量先验在客户尺寸语料上的效果。
3. **`result_rank` 今天不进先验**：名次那一列只进账（供审计与走查），聚合语句里没有它 —— 这是刻意的，
   否则「谁被点到第几名」会自我强化。要用它得另立判据。
4. **保留期与按人限额欠业主一枚裁定**：本表按事件流水长，「一个人一日可记几枚动作」与「留多久」都是隐私×调参的取舍，
   属业主闸门（复核单 `:257` c) 与计划书 L339 已明写不在执行层单里）。本单**没做**，纸面点名在这里。
5. **生产库未跑 0019**（只读纪律）⇒ 现网读腿**应当**走 fail-open（进程内钉住的形状：`source="error"`、
   `reason == "UndefinedTable"`、连注记都不长、交回**同一对象**）。这一格只由 `test_a_missing_0019_leaves_the_order_alone_and_says_why` 用**真异常型 `psycopg.errors.UndefinedTable`** 在进程内钉住，**没有在现网观测过**（生产库只读、0019 没跑）——总控若要拿它当上线前判据，需在自建库上亲量一次。
   并树后要不要真跑 0019，请总控按 `migrations/README.md` 那套前滚口径裁定，别由执行层决定。
6. **全量门未跑**（`scripts/run_gate.py`，派工词禁止）。所以本纸所有数字都还欠总控两态亲跑：
   dirty 态一遍、`git commit` 之后干净树再一遍，两次的文件清单逐枚点名（R496 那一刀的规矩）。
7. 后端批 B1／B2 的读数只算**前一班自报**（本席未复跑），本席亲跑的是 §3 那三枚新钉（62 passed）、§6 连续性批（155 passed）、§7 前端四枚在册件（21/20/16/10）。

## 9. 残留待总控处置（执行层无删除权限）

- `be-r46c/data/..persistence.json.lock`（未跟踪、未被 `.gitignore` 覆盖，会出现在 `git status` 里）。
  来历：13:02 一枚在 pytest 之外跑的 K3 探针（`%TEMP%\r46c_probe_k3.py`）长出来的；同名探针曾把
  `chroma_db/chroma.sqlite3` 写过一版，**已 `git checkout HEAD --` 恢复**，现在 `git status` 里不再出现它。
  `data/.persistence.json`（2450 B）已被 ignore，不脏盘面。并树前请 `rm` 掉那枚 lock。
- 主树另有一枚 `?? 0019-processing.json`（258 B，**创建时间 2026-10-01 23:39:29**，内容是一枚文档处理态桩）——
   🔴 **不是本单产物**（本单在 10-03 才开工，且从不写主树），只是号与迁移 0019 撞名，别把它当本单痕迹；本席只读取证，未动它。
- `%TEMP%` 下的取证物（不入库，供复验）：`r46c-pg-probe2.txt`（§4 全文）、`r46c_probe.sql`（P01–P21 原文）、
  `r46c-walk\`（§7 台子：`entry.js`／`vite.config.mjs`／`index.html`／`shot.mjs`／`dist\`，其中 `node_modules` 是指向工作树前端的**联接**，删之前先 `rmdir` 联接本身，别递归删）、
  `r46c-lint-base2\`（改前 stylelint 基线树，`node_modules` 同样是联接）、`r46c-batch*.txt`、`r46c\*.png`。

## 10. 给总控的复跑清单（照抄即可）

```powershell
$PY = 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe'
cd C:\Users\fengx\PycharmProjects\be-r46c
# 三枚新钉（62）＋ 反证台账（-s 才印八把）
& $PY -X utf8 -m pytest tests/test_r46c_engagement_signals.py tests/test_r46c_engagement_prior.py tests/test_r46c_counter_evidence_teeth.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r46cv" -q
& $PY -X utf8 -m pytest tests/test_r46c_counter_evidence_teeth.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r46cv" -q -s
# 在册连续性批（155）
& $PY -X utf8 -m pytest tests/test_document_catalog_sync.py tests/test_r349_catalog_tail_ledger.py tests/test_r120_clean_install_first_boot.py tests/test_r183_184_migration_pair.py tests/test_r183_declared_lane_column.py tests/test_r190_status_failed_domain.py tests/test_r251_alert_disposal_migration.py tests/test_r299_notification_states.py tests/test_r509_artifact_lineage_lands.py tests/test_r523_prompt_cache_column_migration.py tests/test_r523_counter_evidence_teeth.py tests/test_r523_cached_count_lands.py -o addopts= -p no:cacheprovider --basetemp="$env:TEMP\r46cv" -q
# 前端定向（15 + 21 + 20 + 16 + 10）与色值两态
cd frontend; node_modules\bin\vitest run src/components/__tests__/r46c-source-engagement.test.js
npx stylelint "src/**/*.vue"        # 期望 148 problems (0 errors, 148 warnings)
```