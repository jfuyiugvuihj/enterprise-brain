# R526 · R32 判据① 的数值格 = R105 乙半：本单只钉口径，一枚数都不发（2026-09-30）

施工树 `C:\Users\fengx\PycharmProjects\be-r526`，基点 `28e9d50`（detached，就地改，未 commit / 未 git add）。
解释器 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`，所有命令 cwd = 本树。

🔴 **本文所有数字标注「执行层自报」**，每条附命令原文；总控并树前须亲自复跑对拍（判据③那条尤其要复跑）。
本文不复述上一窗的任何分位数：本单一枚实测秒数都不引用，`docs/testing/sidecar-run9.jsonl` 只被当
「件在不在仓、行里有没有那一格字段」来读，读数一格都不取。

## 0. 一句话交付

契约 `docs/api/contract-v1.md` 的「Three-Tier SLO Contract」一节里，每一枚数字格从今天起有了一条**可机读**
的口径三件（量具在册件 + 原始读数件与取哪一格 + 达成条件），观测面用 `slo_slot_caliber()` 交出同一副表；
`target` 一格都没填，`GET /api/v1/slo` 的字段、错误码、鉴权闸一字未动。

## 1. 落点与写域（两处只增不删，两枚全新件）

| 文件 | 改动 | 内容 |
|---|---|---|
| `app/api/v1/observability.py` | +378 / -0 | R526 口径块：`SLO_EVIDENCE_DIRS`、`SLO_CALIBER_SPINE`、`SLO_REFERENCE_WINDOW`、`SLO_STAGE_QUANTILES`、`SloSlotCaliber`、`SLO_METRIC_CALIBER`、`SLO_STAGE_CALIBER`、`slo_slot_caliber()` |
| `docs/api/contract-v1.md` | +63 / -0 | `### 4b. Caliber cells: the three legs under every number slot (2026-09-30, R526)` ＋ `#### run10 收窗之后的交接` |
| `tests/test_r526_slot_caliber_closure.py` | 全新 628 行 | 19 枚用例：判据①②③④⑥的牙，全部走纯函数 |
| `tests/test_r526_counter_evidence_teeth.py` | 全新 282 行 | 17 个函数 / 21 枚用例：判据⑤九把刀 |

执行层自报 · `git diff --numstat`：

```
378	0	app/api/v1/observability.py
63	0	docs/api/contract-v1.md
```

第二列全为 0 ⇒ 两枚在册文件零删改；`git status --porcelain` 另有两枚未跟踪新测试与本件，施工脚手架
`.tmp-r526\` 交工时已整体移出工作树（见第 7 节第 7 条）。四枚文件字节面（执行层自报 · 逐字节数 `b"\r\n"` / `(?<!\r)\n` / `\r(?!\n)` / 前三字节）：

```
app/api/v1/observability.py             CRLF 1854  bareLF 0  loneCR 0  BOM False
docs/api/contract-v1.md                 CRLF 5909  bareLF 0  loneCR 0  BOM False
tests/test_r526_slot_caliber_closure.py CRLF 627   bareLF 0  loneCR 0  BOM False
tests/test_r526_counter_evidence_teeth.py CRLF 281 bareLF 0 loneCR 0  BOM False
```

## 2. 判据逐条 → 凭命令 → 读数

### 判据① 口径闭环（每枚数字格指向「量具 + 原始读数件 + 达成条件」三件，缺任一件即红）

- 命令：`python -m pytest tests/test_r526_slot_caliber_closure.py tests/test_r526_counter_evidence_teeth.py -q`
- 读数：执行层自报 **40 passed in 3.43s**
- 槽位宇宙由 `slo_tiers()` 派生，纸面不抄枚数：`len(slo_slot_caliber()["slots"])` ＝ 执行层自报 **36**，家族分布
  `A-end-to-end 3 / B-first-text 1 / C-progress-interval 1 / D-cache-hit 1 / E-stage 30`（每档 × 在册五段 × 两枚分位）。
- 缺腿就红的牙：`test_no_slot_is_missing_a_leg`（在册正牙）＋ 反证刀 **K3**（逐列摘腿，参数化 5 例；其中
  `prerequisite` 那一例是**对照**：它不属于三件，摘掉不该红）＋ **K3b**（格子没口径 / 口径挂在已不存在的格子上，两头都咬）。
- 盘面事实：`uncalibrated == []`、`orphan == []`（执行层自报，同一枚 import 探针）。

### 判据② 不许发布数值（未实测的秒数 = 不可承诺）

- 命令：`python -m pytest tests/test_r526_slot_caliber_closure.py -q -k "publishes_no or dead_tooth or this_file"`
- 读数：执行层自报 **3 passed**（`test_the_caliber_publishes_no_measured_number`、
  `test_this_file_itself_publishes_no_numbers`、`test_the_number_scanner_is_not_a_dead_tooth`）
- 判据的形：每枚槽位 `target` 恒为 `None`、`target_status` 恒为 `awaiting_real_samples`（执行层自报：
  `Counter({None: 36})` / `{'awaiting_real_samples'}`）；新增用例里没有任何一条断言具体秒数 / token 数 / 准确率。
- 扫描器自己不许是死牙：`test_the_number_scanner_is_not_a_dead_tooth` 双向验——6 条该咬的字面（秒级、毫秒级、分数、token 量级各一对，全部只存在于钉文件的弹药区，本文一枚都不抄）与 12 条不该咬的字面（`§3`、`run10`、`MIN_SLO_SAMPLES`、版本号一类）。
- 自扫：`test_this_file_itself_publishes_no_numbers` 把同一枚尺对准钉文件自己（`FORGERY_START/END` 两处 `rindex`
  显式排除弹药区，排除之外不许出现量级，并且断言弹药区确实装着会被咬的东西——排除的理由就是它必须被排除）；
  本文与契约纸不在这枚自扫的射程里，它们分别由 `check_no_numbers` 与 K9b 管。

### 判据③ 同源算术（观测面与契约散文同一枚量具名、同一套单位映射，不许第二套）

- **对拍命令**（散文就是从模块渲染出来的，本单一次都没手抄）：
  `python -m pytest tests/test_r526_slot_caliber_closure.py::test_the_contract_row_and_the_module_are_the_same_words -q`
- 读数：执行层自报 **1 passed**；整片 `check_doc_agreement(契约散文, slo_slot_caliber())` 返回**空清单**
  （`test_the_full_suite_of_checks_is_empty_on_the_shipped_tree` ＋ **K9**
  `test_k9_the_untouched_shadow_is_clean_and_the_parser_is_alive` 同时断言解析器真解析到东西，防止「零违规＝解析器没干活」）。
- 共享脊柱只写一次（6 条），样本门只以**名字** `MIN_SLO_SAMPLES` 出现，分位只指 §3 的
  `app/common/performance.py::PerformanceStats (nearest rank: the value at ceil(n * q), 1-based)`（执行层自报：
  `spine 6 / sample_floor 'MIN_SLO_SAMPLES' / percentile_source 'app/common/performance.py::PerformanceStats …'`）。
- 反证刀 **K2a / K2b**：把第二套量具名抄进散文、或只改观测面不动散文，两个方向都咬（同一枚 `check_doc_agreement`）。

### 判据④ 口径格仍 >=1 枚处于「待真机样本」，偷填数字而无 `docs/perf/raw/` 凭据必须红

- 现读命令：`rg -c "待真机样本" docs/api/contract-v1.md` → 执行层自报 **20**（§4 那 16 枚格名册原样在，
  §4b 新增的是口径散文与表格里对它的引用；本单没有减损任何一枚在册「待真机样本」）。
- 同节邻锚未动：`rg -c "gated: needs lane labels" docs/api/contract-v1.md` → 执行层自报 **3**
  （`tests/test_r32_lane_contract.py` 要求恰为 3；本单没碰它，邻件批 A 里它随 168 passed 全绿）。
- 机器面：**36 / 36** 枚槽位 `may_fill_from_window == False`（执行层自报 `fillable: 0`）；`reader_landed == True` **0 / 36**。
- 偷填数字的牙：**K1** 把 §4 的 `qa` 目标格改成 `90 s`（影子端按 CRLF 落真字节再读回）→ 红并点名 victim
  `qa.end_to_end_p95_ms`；**K1b** 反向对照：同一枚数字在三件齐备（读数件落仓 + 件名在册 + 脊柱满）时**放行**，
  证明 K1 不是「凡有数字就红」的假牙。

### 判据⑤ >=2 把反证刀，每把先在影子端跑正控

- 命令：`python -m pytest tests/test_r526_counter_evidence_teeth.py -q` → 执行层自报 **21 passed**
- 派工词点名的两把（K1 偷填无凭据 / K2 观测面与散文分家）都在，另交 7 把；逐把见第 4 节。

### 判据⑥ run10 收窗后的衔接

- 命令：`python -m pytest tests/test_r526_slot_caliber_closure.py -q -k handoff` → 执行层自报 **1 passed**
  （`test_the_run10_handoff_table_is_complete`：五行家族逐行要有「谁 / 先决 / 命令 / 凭据」，缺一即红）
- 牙：**K8**（删掉 D 行 → 红）、**K8b**（E 行的命令格换成散文 → 红）。
- 正文见契约 `#### run10 收窗之后的交接（乙半按这一节落，不用重新发明）` 与本文件第 5 节。

## 3. 今天盘面的硬事实（写口径前逐条现取，不许改口径来迁就它）

| 事实 | 命令（cwd = be-r526） | 执行层自报读数 |
|---|---|---|
| run9 逐发台账在仓，且**没有**任何档位键 | `python .tmp-r526\probe_data.py` | `docs/testing/sidecar-run9.jsonl` 105 行；含 `wall_ms` 105、含 `kind` 105；含 `lane`/`tier`/`effective*` 键 **0 行** |
| run9 帧账在仓，首屏与「第一个可见事件」不同量 | 同上 | `docs/testing/sidecar-run9-frames.jsonl` 105 行；带 `events` 105、含 `text` 事件 **103**、含 `step` 事件 95；`first_visible_event == "step"` **95 行**；`queue` 非空 **0 行** |
| 评测夹具只有**声明档** | 同上 | `tests/fixtures/business_evaluation_100.jsonl` 105 行，`tier ∈ {问答, 分析, 报告}` |
| 分段读数件 / 窗内驱动未落仓 | `rg -ln "stage_latency_readout|samples_from_events|lane_by_trace|stage-latency" scripts/` | **rc=1，零命中** |
| 交接表点名的三枚读数件今天不存在 | `Test-Path scripts/eval_slo_lane_readout.py` 等 | `eval_slo_lane_readout.py`／`eval_slo_wire_readout.py`／`eval_cache_hit_probe.py` **MISS**；`eval_transport_ask_v2.py`／`eval_frame_caliber_readout.py`／`eval_cloud_window_readout.py`／`eval_window_answer_cache_gate.py`／`perf_probe_run5_ledger.py` **OK** |
| runbook §7 确有 A/B/C 三步（交接表引 B、C） | `rg -n "^#{1,3} " docs/handoff/2026-09-17-eval-real-run-runbook.md` | `## 7. 执行序列（三步，一条一个退出码）`，其下为 `# A. 结构预检：零模型` / `# B. 真采集：串行 105 题` / `# C. 评分：正式落盘物是报告，进 docs/testing/` |

⇒ 这一栏就是 §4b 最后一列「落数前欠」的出处：档位 join、窗内驱动、首屏/进度名册格、缓存预热探针四样都还没有，
所以乙半不能在本单口径之外自创第二套算法；本单把它们逐格登记成欠项，而不是把格子留空当已交。
## 4. 判据⑤ · 反证刀清单（每把都先在影子端跑正控，再验它咬，并点名 victim）

影子端＝`tmp_path` 上按 CRLF 落真字节再原样读回的契约副本，或口径 dict 的深拷贝：真盘面一个字都不动。
`materialize()` 内建两条正控（`read_back.count("\r\n") == text.count("\n")`、读回归一后与送进去的字节逐字相同），
所以「刀切了空气」在这一层就露馅。九把刀全部与在册牙共用同一批纯函数，不存在「刀有牙、钉没牙」。

| 刀 | 怎么切 | 正控 | 咬在 | victim（执行层自报点名） |
|---|---|---|---|---|
| K1 | §4 目标格里 `qa` 那一格偷填 `90 s`，三件一件不给 | 该针行今天在且唯一（`len(hits)==1`），未动手时 `check_no_numbers` 返空 | 判据④ | `qa.end_to_end_p95_ms` · 凭据 |
| K1b | 反向对照：同一枚 `90 s`，读数件落仓 + 件名在册 + 脊柱满 | 三件齐 ⇒ `fillable(...) is True` | 证明 K1 不是「凡数字就红」的假牙 | 同上格 |
| K2a | 第二套量具名（`scripts/eval_transport_ask_v3.py`）抄进散文 | 影子字节落地校验 | 判据③ | `qa.end_to_end_p95_ms` · 量具 |
| K2b | 同一处分家从另一边进：只改观测面不动散文 | `shadow.original` 未动仍绿 | 判据③ | 同上 |
| K3 | 逐列摘腿：`instrument` / `raw_readout` / `raw_field` / `condition` 各摘一次 | 摘之前该格完备 | 判据① | 三档各一枚（A/B/E） |
| K3 对照 | 同参数化里摘 `prerequisite` | 它不属于三件 ⇒ 必须**不**红 | 防假牙 | — |
| K3b | 名册新格没口径 / 口径挂在已消失的格子上 | 两头的名字都现场造 | 判据① | 未寻址格 + `uncalibrated/orphan` |
| K4 | 数值格挂上云端 shape 格 `frame_shape` | R453 名册由 `importlib` 现读 | 判据①（族不能串） | `qa.end_to_end_p95_ms` · 时延族 |
| K5 | 名册里根本不存在的枚名 `p99_wall_ms` | 同上 | 判据① | 同上 · 名册里不存在 |
| K6 | 本格自写排名规则（「分位取线性插值，不看在册那枚件」） | 未动手时 `check_spine_is_one` 空 | 判据③（禁第二套算术） | `qa.first_text_p95_ms` · 脊柱 |
| K6b | 再抄一遍样本门（哪怕抄的是同一枚名字） | 同上 | 判据③ | 同上 |
| K7 | 量具件不在仓内（`scripts/eval_transport_ask_v9.py`） | 该路径 `Test-Path` 为假 | 判据① | `report.stage.generate.p95_ms` · 不在仓内 |
| K7b | 散文里的量具路径不存在（只改那枚字符串） | 同上 | 判据①③ | `qa.end_to_end_p95_ms` · 仓外/不存在 |
| K7c | 字段空头支票：说「取这一格」，run9 真件里逐行没有它 | 参照件真字节现读 | 判据① | `qa.end_to_end_p95_ms` · 并不产出 |
| K8 | 交接表删掉 D 行 | 针行唯一 + 未动手 `check_handoff` 空 | 判据⑥ | 家族 `D` |
| K8b | E 行的命令格换成散文（无可执行命令） | 同上 | 判据⑥ | 家族 `E` |
| K9 | 不切：整片对拍 | 未动手盘面零违规 **且** 解析器真解析到东西（防死牙总闸） | 判据①③ | 全 36 格 |
| K9b | 弹药只准待在影子里 | 契约纸 / 观测面 / 脊柱三处都不许出现伪造串 | 判据② | — |

命令与读数：`python -m pytest tests/test_r526_counter_evidence_teeth.py -q` → 执行层自报 **21 passed**；
合跑 `python -m pytest tests/test_r526_slot_caliber_closure.py tests/test_r526_counter_evidence_teeth.py -q`
→ 执行层自报 **40 passed in 3.43s**。

## 5. run10 收窗之后：哪一格由谁按什么命令填、要附什么凭据

🔴 铁顺序：**先落读数件（写域 `scripts/`，本单不许建），再由 R105 乙半按 §4b 交接表填 `target`**。
件没落仓 ⇒ 那一格照旧读「待真机样本」，那是正确答案，不是没干活。凭据一律四件齐：件路径 + `sha256`、
`caliber=local-full`、抬头开关态（`MODEL_MAX_CONCURRENCY`／`VECTOR_DUAL_WRITE`／`REPORT_LANE_VIA_QUEUE`／`INDEX_BACKEND`）、
一枚反证钉。仓外（Temp）产物不算凭据——run9 那张分档表就是这么没人钉住的。

| 家族 · 格 | 谁 | 按什么命令 | 交回时必须附 |
|---|---|---|---|
| A（`qa`/`analysis`/`report` 的 `end_to_end_p95_ms`，3 枚） | 先：读数件落仓单；后：R105 乙半 | 开窗照 runbook §7 B、C 步（件名换成 run10）；出数 `python scripts/eval_slo_lane_readout.py --window run10`（件落仓之前这条**跑不起来**，跑不起来＝取不到，不许手算） | `docs/testing/sidecar-run10.jsonl` 路径+`sha256`；`caliber=local-full`；抬头四枚开关态；`python scripts/eval_cloud_window_readout.py --readouts <件>` 退出码 0；档位取服务端生效档（`[R42] lane=`）而非夹具 `tier` |
| B（`qa.first_text_p95_ms`，1 枚） | 先：给 R453 名册补一枚 wire 首屏格的单（`first_visible_ms` **不算**它）+ 读数件；后：乙半 | `python scripts/eval_frame_caliber_readout.py --frames docs/testing/sidecar-run10-frames.jsonl`（事件在场性自证）＋ `python scripts/eval_slo_wire_readout.py --window run10` | frames 件路径+`sha256`；`caliber=local-full`；抬头开关态；一句署名：读数出自采集器侧外部观察，产品仍不落 wire 事件（§6 `wire_first_text_not_recorded` 未关） |
| C（`analysis.progress_interval_p95_ms`，1 枚） | 同 B 的名册单 + 读数件；后：乙半 | `python scripts/eval_slo_wire_readout.py --window run10 --surface progress`（待落仓；落仓之前这格照旧读「待真机样本」） | frames 件路径+`sha256`；`caliber=local-full`；抬头开关态；**分母写相邻 gap 数而不是题数**（§5 逐格开自己的门） |
| D（`qa.cache_hit_p95_ms`，1 枚） | 另立一扇预热探针窗的单（**不是**跑分窗，也不是乙半） | `python scripts/eval_window_answer_cache_gate.py`（跑分窗**禁止**取这格：P-18 要求开窗前 `answer:*` 归零，命中即 raise 停窗） | `docs/perf/raw/{window}/cache-hit-probe.jsonl` 路径+`sha256`；`caliber=local-full`；探针窗自己的抬头开关态；run10 交回时这格仍读「待真机样本」 |
| E（每档每段两枚分段格，30 枚） | 先：窗内驱动落仓（写域 `scripts/`）；后：乙半 | `python scripts/eval_slo_lane_readout.py --window run10 --surface stage`（同一枚读数件的另一条道；分档走 `stage_latency_readout(lane_by_trace=…)` 那条离线道） | `docs/perf/raw/{window}/stage-latency.jsonl` 路径+`sha256`；`caliber=local-full`；每行随身的 `coverage_error_pct` / `gap_ms` 与未归属段计数——报告档的 export 腿无段（§6 `export_leg_has_no_stage`），**五段之和不许当成该档端到端** |

机器面对得上：36 枚槽位里 `window_admissible == False` 的正是家族 D 那一枚（`qa.cache_hit_p95_ms`），
其余 35 枚「本窗可取材」为真但 `may_fill_from_window` 仍为假——缺的是 `reader_landed`，不是数字。
## 6. 邻件定向复跑（按硬规矩：不跑全量门）

- 命令（批 A，契约与口径同族）：
  `python -m pytest tests/test_r105_slo_contract.py tests/test_r32_lane_contract.py tests/test_r132_contract_followup_sync.py tests/test_r156_sse_event_surface_sync.py tests/test_r276_vector_wording_pin.py tests/test_r38_cached_tokens_honesty.py tests/test_r78_unearned_claims.py tests/test_r253_no_test_rewrites_a_tracked_file.py tests/test_r253_shadow_root_holds_the_mutation.py -q`
  → 执行层自报 **168 passed, 26 warnings in 106.84s**
- 命令（批 B，观测面同族）：
  `python -m pytest tests/test_r51_stage_latency.py tests/test_r51_observation_is_passive.py tests/test_observability_routes.py tests/test_r461_answer_cache_gate.py -q`
  → 执行层自报 **106 passed, 1 skipped, 40 warnings in 13.57s**
- 本单两件：`python -m pytest tests/test_r526_slot_caliber_closure.py tests/test_r526_counter_evidence_teeth.py -q`
  → 执行层自报 **40 passed in 3.43s**（19 + 21）
- 只读参照件一根子未松：`tests/test_r32_lane_contract.py` 在批 A 内全绿，本单一字未改它。

## 7. 未达 / 本单故意不做 / 登记给总控（不许读成已收）

1. 🔴 **数值格未交**（判据①只达成「口径」那一半）：36 / 36 枚槽位 `may_fill_from_window` 仍为 `False`，
   `target` 全为 `None`。这一格记在 R105 乙半名下、压在跑分窗，**不许记进 R32/R526**。
2. 🔴 **观测面与散文的一句在册矛盾（本单没写、也没改，登记）**：
   - `rg -n "belong to no lane" app/api/v1/observability.py` → 执行层自报命中 `slo_units()` 的 `bridge_note`：
     `... and six of the` / `seven budget tiers belong to no lane at all`；
   - `rg -n "of the seven budget tiers" docs/api/contract-v1.md` → 执行层自报：
     `Five of the seven budget tiers (`plan` `compress` `rewrite` `code` `alert`) are named by no lane`；
   - 现源派生（`python -c` 走 `slo_units()`）：`ModelTier` 成员 7 枚，lane 桥值 `{analysis, chat}` ⇒ 无档之名 **5** 枚
     ＝ `{alert, code, compress, plan, rewrite}`，与散文逐字一致 ⇒ **散文对、模块那句多一**。
   - 它在基点上就这样：`git show 28e9d50:app/api/v1/observability.py | rg -n "belong to no lane"` → 同一句。
     本单写域是「只准加口径那一小面」，改这句＝改 `/slo` 回执里的一串（形状变更），故**不动**；
     今天也没有在册牙咬它（`tests/test_r105_slo_contract.py` 自己算 unlaned 计数，不读这句话）。
     建议另立一单：把这句改成派生（`len(members - {桥值})`）或由总控带口径改口，改完补一枚对拍牙。
3. **口径没接进回执**：`slo_slot_caliber()` 不被 `slo_readout` / `read_slo` 引用，加键＝改形状（牙：
   `test_the_observation_surface_does_not_reach_into_the_response`）。接进去要另立单。
4. **交接表点名的三枚读数件未落仓**：`scripts/eval_slo_lane_readout.py`、`scripts/eval_slo_wire_readout.py`、
   `scripts/eval_cache_hit_probe.py`。写域是 `scripts/`，本单不许建，且 be-r525 正读 `scripts/`。
   家族 A/E 的落数**必须先有第一枚**，B/C 必须先有第二枚，D 必须先有第三枚。
5. **R453 名册缺两格**：首屏（wire 侧 `text` 事件，`first_visible_ms` 不算）与进度间隔。名册现读
   （`importlib` 加载 `scripts/eval_cloud_window_readout.py::CELLS`）里家族 B/C/D/E 的 `roster_cell` 均为空串，
   只有家族 A 的 3 枚对上 `p95_wall_ms`——这不是漏钉，是 `check_roster_cells` 允许「在册格名可空 + 落数前欠写明」。
6. **§6 blockers 一枚都没关**（本单只引用在册枚名，一个都不新造；牙：`test_the_caliber_never_invents_a_blocker`）：
   `lane_attribution_absent` 挂 35 / 36 枚；家族 B 另挂 `first_token_not_a_stage_sample` + `wire_first_text_not_recorded`；
   家族 C 另挂 `wire_step_events_are_not_recorded`；家族 D 独挂名册里的 `cache_hits_are_not_traced`（本单一枚名字都没新造）；`report.*` 11 枚另挂 `export_leg_has_no_stage`。
7. **本文 §3 里的 `python .tmp-r526\probe_*.py` 是施工期一次性探针**，交工已把它们整体移出工作树
   （现在落在 `%TEMP%\r526-scaffold`，工作树内 `.tmp-r526\` 已不存在，沙盒不许在工作树里做删除）；
   同一批读数的可复现命令见第 8 节，总控按第 8 节复跑即可，不必再依赖那批探针。

## 8. 读数复现（全部零依赖、可重跑；cwd = `C:\Users\fengx\PycharmProjects\be-r526`）

| 要复跑的读数 | 命令 | 期望（执行层自报） |
|---|---|---|
| 本单两件 | `python -m pytest tests/test_r526_slot_caliber_closure.py tests/test_r526_counter_evidence_teeth.py -q` | 40 passed |
| 判据③对拍单点 | `python -m pytest tests/test_r526_slot_caliber_closure.py::test_the_contract_row_and_the_module_are_the_same_words -q` | 1 passed |
| 口径格仍在「待真机样本」 | `rg -c "待真机样本" docs/api/contract-v1.md` | 20 |
| r32 邻锚未增损 | `rg -c "gated: needs lane labels" docs/api/contract-v1.md` | 3 |
| run9 台账有 `wall_ms`、无档位键 | `rg -c "wall_ms" docs/testing/sidecar-run9.jsonl`；`rg -c -e "lane" -e "tier" -e "effective" docs/testing/sidecar-run9.jsonl` | 105；rc=1 零命中 |
| run9 帧账首屏≠首个可见事件 | `rg -c "\"event\": \"text\"" docs/testing/sidecar-run9-frames.jsonl`；`rg -c "\"event\": \"step\"" …`；`rg -c "\"first_visible_event\": \"step\"" …`；`rg -c "\"queue\": \{\}" …` | 103；95；95；105（`queue` 全空 ⇒ 家族 C 的分母没有窗内来源） |
| 夹具只有声明档 | `rg -c "tier" tests/fixtures/business_evaluation_100.jsonl` | 105 |
| 分段读数未落仓 | `rg -ln "stage_latency_readout|samples_from_events|lane_by_trace|stage-latency" scripts/` | rc=1 零命中 |
| 交接表三枚件名不存在 | `Test-Path scripts/eval_slo_lane_readout.py, scripts/eval_slo_wire_readout.py, scripts/eval_cache_hit_probe.py` | False × 3 |
| 桥注那句在册矛盾 | `rg -n "belong to no lane" app/api/v1/observability.py`；`rg -n "of the seven budget tiers" docs/api/contract-v1.md` | `six of the` / `Five of the seven` |

**卫生（执行层自报）**：未 commit、未 `git add`、未跑全量门、未动容器、未起服务、未打模型。
上面每条 pytest 头部闸门读数：`blocked connect attempts to host model port: 0`、`offline discovery stub calls (no socket opened): 0`、
`R134 工作树 Chroma 写回闸门 … PersistentClient 调用: 0 次 … 写回告警用例: 0 枚`——本单全程只 import
`app.api.v1.observability`，一次都没 import `app.api.v1.chat`（那会真打 Postgres）。
主树未被本单写过：`git -C C:\Users\fengx\PycharmProjects\企业智脑 status --porcelain -- app/api/v1/observability.py docs/api/contract-v1.md`
→ 执行层自报 **空输出（rc=0）**，且主树里 `tests/test_r526_*.py` / `docs/testing/r526-*.md` 枚数为 0。