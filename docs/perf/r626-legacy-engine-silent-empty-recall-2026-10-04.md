# R626 · 遗留引擎静默空召回：把"21 题交回空列表"变成一枚会红的复跑件（2026-10-04）

- **单号**：R626（交付三件＝量具 + 牙 + 本纸；修 Chroma 与翻默认都不在本单，业主 10-03 已裁「默认不翻」）。
- **执行者**：执行层 `Feynman`，树 `be-r626`，分支 `codex/be-r626`，基点 `8c99251`。验收与提交由总控代做，本席零 commit。
- **现取时刻**：2026-10-04 10:2x（`Get-Date` 直读）。🔴 本席**没跑容器、没连 PG、没开卷、没打模型**——§1 的现网数字全部是总控 10-04 09:45 现取，本席只做派生对账（题号集合、分母、sha16）与离线装牙。
- **口径出处**：生产向量库是 PostgreSQL + PGVector（业主 09-24 定案）；Chroma 是**退役中的遗留件**，今天的真实位置是「写已停、本机读已切、退役未完」（`docs/handoff/2026-09-17-pgvector-adoption-plan.md` §15），本纸不写第四种说法。

## 0. 结论（四句）

1. **症状形状**：同一份题集、同一枚 k=5、同一批查询向量，PGVector 腿 105/105 每问交回 5 名；遗留引擎腿对其中 **21 问交回空列表**，零报错、零异常、零警告。
2. 🔴 **今天这 21 枚题号与 R269 在 09-26 固化的那张表逐枚同一份**（本席现比：`docs/perf/chroma-unreachable-root-cause-2026-09-26.md` §3 表里 chroma5=0 且 chroma50=0 的 21 枚 qid，与今天读到的 21 枚 qid 集合相等，差集两向皆空）。⇒ 八天过去、双写已停、本机读已切之后，**同一批题仍然同一批**：这是固化在持久图里的一格状态，不是抖动，也不是当天运气。
3. **客户可见面**：出厂默认仍是遗留件（`INDEX_BACKEND_DEFAULT`，业主 10-03 裁「默认不翻」，本单一字未动）。没在 `deploy/.env.server` 写 `INDEX_BACKEND=pgvector` 的装机，语义读答复走的就是这条会静默交空的腿——所以本单按 **P1 证据**交付，不按旧账处理。
4. **本单交的是量具不是修复**：`scripts/r626_legacy_engine_silent_empty_probe.py`（零变异、只读快照、退出码 1 专指静默空召回）＋ `tests/test_r626_legacy_silent_empty_teeth.py`（23 枚确定性钉，含两把反证刀与一枚真子进程钉）＋ 本纸。

## 1. 现象与逐字读数（全部标出处）

### 1.1 今天的对账读数（总控 10-04 09:45 现取，backend 容器内）

| 格 | 读数 | 出处 |
|---|---|---|
| pg 腿 | 105/105 题各返回 5 条 | 总控 10-04 09:45 现取（R143 recall 对账） |
| chroma 腿 | **21 题返回空列表**，其余 84 题返回 5 条 | 同上 |
| mean overlap@5 | **0.7238** | 同上 |
| 完全一致 | **55/105** | 同上（"一致"的两种拼法见 §1.3 第 2 条） |
| 空表题号 | doc-09 doc-13 metric-04 metric-05 metric-10 metric-11 metric-13 metric-18 metric-19 data-08 insight-02 insight-06 chart-04 approval-06 scope-01 scope-03 scope-05 scope-06 tool-01 tool-04 report-12 | 同上 |

按类分布（分子＝上面点名的空表题，分母＝**本席现读**题集里各类行数，不是抄来的）：
metric 7/19、scope 4/6、doc 2/19、insight 2/7、tool 2/4、data 1/12、chart 1/4、approval 1/6、report 1/12；合计 21，与题号清单逐枚对得上。
🔴 这一格只给分布，不给因果——为什么偏偏是 metric 与 scope 两族吃空，本单没证（§6.3）。

### 1.2 两把归因探针（总控 09:45 现取，逐字抄录）

- **探针①**：`collection.count() = 1008`；`collection.get(include=["embeddings"])` 取回 1008 枚向量；查询向量 768 维、非有限值 0 枚；`n_results=5` 与 `n_results=20` **都返回 0 条**，`error=None`。
- **探针②**：把这 1008 枚向量原样 `add` 进一枚 `chromadb.Client()` 临时集合（同 `l2` 空间），**同样的查询立刻返回 5 条**。

⇒ 数据在、向量在、口径在；坏的是持久卷里那枚 HNSW 索引，它静默交空。R269 §0.2 当年已证 `k=50` 也交 0 行，所以这一族**不能**由候选宽度（`ef_search`）解释；截断只会给不满 k 行，给不出 0 行。

### 1.3 两处口径必须钉在纸上（引用之前先看这两条）

1. 🔴 **题数是 105，不是 135**。`compare_vector_recall.py` 的 `DEFAULT_FIXTURES` 是 `tests/fixtures/business_evaluation_30.jsonl` ＋ `business_evaluation_100.jsonl` 两份，实读 30 行＋**105 行**＝135 枚（文件名写 100 而盘上是 105 行；sha256 前 16 位 `686c564ff2985744`，就是计划书 §14 那枚"主件"），而 scope-01／scope-02 在两份里**各出现一次**。⇒ 复跑今天这一格必须显式 `--fixture tests/fixtures/business_evaluation_100.jsonl`，否则分母不是 105，任何"平均分母"的对比都读错。
2. **"一致"有两把尺**：`compare_vector_recall._compare` 用 `pg_ids == chroma_ids`（逐名次），R269 §3 用的是集合相等。R626 把两把并排交回而不互相替换——`exact_leg_agreement` 取逐名次口径（含 definition 字段自报），`mean_overlap_at_k` 取「交集枚数 ÷ k」。总控那句"55/105 集合完全一致"落在哪把尺上，本席无法从读数反推，**按未定处理**；复跑时两列同屏，一次就分得开。

## 2. 它站在哪些在册件旁边（不重复立案、不平行实现）

| 在册件 | 与本单的关系 |
|---|---|
| `docs/perf/chroma-unreachable-root-cause-2026-09-26.md` §9.2 | 那句「症状 B（21 题 0 行）没交得出可请求复现的最小复现物」——本单交的就是这枚复跑件；R269 的诊断本身照旧有效，本纸不重述它的图结构推断。 |
| 同纸 §9.7 | 教训「抖动量不许当回归门」（`ann_miss >= 1` 那枚把 1/7 抖动率当了门，主树首跑即红）⇒ 本单的牙**全部走确定性假腿**，不拿真库浮动当判据；真读数归总控的容器窗。 |
| 同纸 §0.2／§3 | 「`k=50` 仍 0 行」与那 21 枚 qid 的原表，是本单 §0.2 派生对账的另一半凭据。 |
| `scripts/r382_empty_leg_probe.py`／`r382_leg_compare.py` | 09-27 的一次性 12 问探针：题面硬编码、原地开卷（`R382_CHROMA_DIR`）、把空折进 overlap 百分比里。本单不动它们也不 import 它们；差别就在「判空格 + 退出码 + 快照零变异 + 题集走在册主件」。 |
| `scripts/compare_vector_recall.py` | 被本量具**装载复用**的那一枚（`connect_read_only`／`open_chroma`／`resolve_chroma_distance`／`read_scope`／`corpus_drift`／`load_questions`／`pg_recall`／`fail_precondition`），不抄第二份实现。🔴 两枚的 1 号语义不同：在册件 1＝「跑成了、检出差异」，本量具 1＝「静默空召回」——两份产物不许塞进同一张分诊表（写在 epilog 与码上，有牙）。 |
| `tests/test_r238_*`／`tests/test_r134_*` | 本量具因此不许自己开 `PersistentClient`、不许自己裸 connect：全仓 15 枚裸 connect 与开库收口名册都是"枚数全等"账，多一枚落点就红。这枚约束由 §4 的第 17 号钉显式盯住，不靠自觉。 |

## 3. 可复跑命令

🔴 别在宿主机跑这组（计划书 §9.4 那条纪律仍然有效：宿主 5432 可能挂着另一台野 PostgreSQL，且 `%TEMP%` 下的临时卷与生产 1008 枚不是一批东西）。要么在 backend 容器里跑，要么别跑。

```bash
# 前置（全部是总控动作，本席没执行；cp 进的是容器可写层，不是镜像重建，容器 --force-recreate 即没）
#  1) 量具与在册量具必须落在同一棵树里，否则按前置码 2 退（它按 ROOT/scripts/ 装载兄弟件）
docker cp scripts/r626_legacy_engine_silent_empty_probe.py enterprise-brain-backend-1:/app/scripts/
#  2) 镜像里没有 tests/，题集（105 枚主件）要先 cp 进 /tmp，再用绝对路径交给 --fixture
docker cp tests/fixtures/business_evaluation_100.jsonl enterprise-brain-backend-1:/tmp/eb105.jsonl

# 复跑：源卷只被 copytree 读，绝不原地打开；前后各做一次内容清单对账
docker exec enterprise-brain-backend-1 /app/.venv/bin/python /app/scripts/r626_legacy_engine_silent_empty_probe.py \
    --snapshot-from /app/chroma_db --staging /tmp \
    --fixture /tmp/eb105.jsonl --k 5 \
    --min-mean-overlap 0.0 --out /tmp/r626.json --md /tmp/r626.md

docker cp enterprise-brain-backend-1:/tmp/r626.json  %TEMP%\\r626\\
docker cp enterprise-brain-backend-1:/tmp/r626.md    %TEMP%\\r626\\
```

- 🔴 解释器必须是 **`/app/.venv/bin/python`**：`/usr/local/bin/python` 缺 dotenv，import 当场死（跟进单 §166 二那格订正，R143/R428 每班读成"欠一台安静机器"的真因就是这条）。
- 退出码读法：**今天这一格应当以 1 收**（静默空召回被检出，不是崩）；2 ＝ 量具没跑成（含腿抛异常、口径不符、快照指到现役卷被拒、源卷内容清单前后不等）；3 ＝ 没有空召回但重合率低于 `--min-mean-overlap`；0 只允许在这条腿不再交空时出现。
- 🔴 **复制与打开是两件事，本量具只禁后者**：`--snapshot-from` 的源**可以**是现役卷（`/app/chroma_db` 正是本单要快照的那一枚，复制只是读）；`--chroma-dir` 是"要交给客户端打开的那一枚"，指到仓根/容器根的 `chroma_db` 一律按前置码 2 拒。两把口子都不给也按 2 拒——本量具没有「打开默认卷」这一档。
  （本席第一版把这条写成"现役卷一律拒"，结果当场废掉派工词要求的那条配方：容器里 `ROOT=/app`，`/app/chroma_db` 就是现役卷，被自己的守卫挡在复制这一步。已改判并钉住，见 §4 第一行那枚用例的注释。）
- 快照落点不许落在源卷里面（自抄会把"零变异"变成自写），落点已存在也不覆盖——三条都是前置码 2。
- 为什么非要快照而不只是"只读打开"：一是零变异（§9.3 格⑤ 那条"只读打开会不会推进 mtime"至今既未证成也未证否，量具因此不宣称机制，只用前后两枚 sha256 清单把这一格变成每次复跑自查）；二是 chroma 对同一目录是单写者锁，服务在跑时原地打开要么撞锁、要么读到半写状态（计划书 §8.2）。

## 4. 牙（23 枚，逐枚点名；除那枚真子进程出口钉之外全程离线）

`tests/test_r626_legacy_silent_empty_teeth.py`，假腿由用例注入，真腿（`ChromaLeg`／`PgLeg`）在件里只按形状检查、不调用。

| 形 | 用例 |
|---|---|
| ① 空列表＝红且要点名 | `test_empty_leg_with_corpus_present_is_flagged_and_exits_one`、`test_the_human_output_names_which_questions_came_back_empty`、`test_both_legs_empty_is_still_one_red_not_two_halves` |
| ② 两腿全等＝绿 | `test_identical_legs_are_clean_at_any_threshold`、`test_order_makes_difference_and_is_reported_separately_from_overlap`、`test_overlap_definition_is_intersection_over_k_not_union` |
| ③ 反证刀（摘掉判空那格必红） | `test_the_pin_holds_on_the_real_source`、`test_knife_removing_the_empty_check_launders_the_symptom`、`test_knife_dropping_the_size_floor_blends_scarcity_into_red` |
| 稀缺≠坏了 | `test_scarcity_is_not_read_as_silent_empty` |
| 崩溃≠空召回 | `test_a_raising_leg_is_a_precondition_not_a_silent_empty` |
| 阈值是参数 | `test_threshold_is_a_parameter_and_todays_reading_is_not_baked_in`（0.7238／0.72／0.9378 三串都不许出现在码体里） |
| 两份产物齐 | `test_machine_and_human_artifacts_carry_every_named_column` |
| 零变异（复制与打开分家） | `test_the_live_volume_may_be_copied_but_is_never_opened`、`test_the_opened_directory_is_refused_when_it_is_the_live_volume`、`test_snapshot_copies_and_the_source_stays_the_same_bytes`、`test_a_snapshot_may_not_land_inside_its_own_source`、`test_there_is_no_default_volume_to_fall_into` |
| 命令行出口真子进程 | `test_the_command_line_refuses_a_default_volume_without_a_database`（没连库也要问得出拒开这一格） |
| 不平行实现／不收口变长 | `test_the_gauge_opens_no_store_and_connects_nothing_itself`、`test_the_exit_codes_stay_homologous_with_the_registered_gauge` |
| 退役量具不进产品 | `test_product_code_does_not_import_the_retirement_gauge`、`test_the_gauge_does_not_read_the_backend_switch` |

两把刀各摘 `is_silent_empty()` 的一半承重条件：摘掉 `returned == 0` 那半（整格返回 False）⇒ 21 枚空列表被折成"零差异"，① 那枚钉失守；摘掉 `leg_size >= k` 那半 ⇒ 库容不足 k 的正常空被洗成"引擎坏了"，② 反向那枚钉失守。两把都在 tmp 的源码副本上做，真树一个字节不写。

## 5. 这一格对切换链的意义（照计划书口径，不自立验收）

- **§9.3 格⑥ 从此有量具**：那句「那 24/135 题空答复要不要作为切读前的基线缺陷单独追（它同时是今天生产的读路径症状）」追到今天，读数变成 **21/105**，而"要不要单独立案追"仍是业主线裁定，不是本单能结的案。本单做的事只有一件：把这句话从每班手写变成一条命令。
- **分母账不新立**：24/135（09-24 r59b）、21/105（09-26 R269 §3）、21/105（10-04 总控现取）三格分母不同源——计划书 §11 第三条已把「召回对比默认并集 135 题 vs 与跑分基线对齐要显式锁 105 题」定成在册口径。本量具缺省沿用 `compare_vector_recall.DEFAULT_FIXTURES`（＝135），所以**要复现今天这一格必须显式 `--fixture` 指 105 枚主件**（§1.3 第 1 条），两本账不许混着引用。
- **R382 那句"剔空腿之后 0.9378"**：计划书 §12 记的格① 服务内端到端读数，是把交空的那条腿剔掉之后再算名次重合——也就是说格① 之所以能交出 84 问全答、零 bypass，前提正是这一族症状**被剔掉了**。本单把这一格从"被剔掉"变成"单独量、单独红"，🔴 但**不推进也不撤销格①**：它已由 R382（并树 `b498c88`）交出，口径归计划书。
- **格②／格③ 不因本单动一格**：热集让路延迟仍欠一台安静机器；生产 `department`／`classification` 全空那一格按 §13 的四件可失败判据仍记「未验」，本单没取生产标签读数，也没拿沙盒合成标签去翻绿。
- **与 R579 分账**：R579 量的是 PG 索引腿的拐点与近重复预算（1008 枚规模上规划器根本不选 HNSW）；本单量的是遗留引擎的持久图交空。两枚量具互不解释，谁也不许替谁交作业。
- **对"要不要快切 PG"的既有裁定**：R269 §0.4 早已一句话裁定「这病在 Chroma 的读路径上，切读即愈」；本单不重裁、不推翻，只补一句今天的位置：本机读腿已按 §15 走 PG，而**退役未完**（S1-S5 欠着），所以没翻旋钮的装机仍然站在这条腿上。这不构成把遗留件写成已下线的凭据，也不构成继续拖 S1-S5 的理由。

## 6. 未证（明写，不许被本纸读成"已修"或"已结案"）

1. 🔴 **没证这枚索引坏态会在客户真装机上重现**。本机这枚卷是 09-18 建、经多代同 id 重传与双写历史的卷（R269 §2 那套墓碑/代际账）；客户首灌出来的新库是另一件事。要证它需要一台真客户机或一份"从零重建"的对照读数，本单没有。
2. 🔴 **没证 PG 腿在这 105 枚题上召回质量更好**。空召回只证"这条腿交回 0 名"，不证对面那 5 名是对的——质量那一格归计划书格①／格②与 R579，本单不越界取结论。R269 §3 那行"brute5 头名＝pg5 头名"是本纸唯一能借的对照，它比的是**名次一致性**，不是答案正确性。
3. **没证为什么恰好是这一族题**（metric 7/19、scope 4/6 只有相关性读数，没有机制）。本单也没证这 21 枚与 09-26 那 21 枚同集合是否只是"同一枚没被动过的卷"——卷没重建过，题号自然不变；这一点恰恰要求 S2 那次归档前后的两遍复跑。
4. **没证坏态由哪一次写入写出**：R269 §9.2 复现到"这种状态存在、写出来就固化"，没复现到"什么顺序必然写出它"（6 遍只出 1 遍，抖动率约 1/7）。本单没有开刀，也就没有新机制可报。
5. **没证"只读打开会不会推进 mtime"**（§9.3 格⑤ 仍欠拍板，既不许记已证会写、也不许记已证不写）。量具只报"源卷前后内容清单是否全等"这一枚事实，不宣称机制。
6. **本席没跑真腿**：容器、PG、`chroma_db` 卷、Ollama 全部零接触，§1 所有现网数字都是引用总控 09:45 的读数；`ChromaLeg`/`PgLeg` 在真环境上的第一遍读数要由总控在容器窗里取。
7. **今天的 0.7238／55／21 三格尚未由本量具复算**：R626 量具在真卷上还没跑过第一遍。下一遍若仍交出同一批 21 枚 qid，§0.2 那句才从"两篇文档的题号集合相等"升级为"两枚独立量具同读数"。

## 7. 交回读数（本席亲跑，dirty 态＝已 apply 未 commit）

- 盘面：树 `be-r626`，基点 `8c99251`，本单新增三枚文件，产品码零改动、`deploy/**` 零改动、`.env*` 零改动、`frontend/**` 零改动。
- 牙：`tests/test_r626_legacy_silent_empty_teeth.py` **23 passed／0 failed／17.53 s／exit=0**（`.venv` 串行，`-p no:cacheprovider --no-header`；那 17 s 是枚真子进程出口钉的装载成本，其余 22 枚合计 <1 s）；反证刀两把各交红/绿一次——真源同一份夹具下判 EMPTY 并非零退出，摘格的副本判 0（钉失守），两形都在 tmp 副本上做完即丢。
- 同族与常驻钉一起复跑（13 枚件，本单三枚文件的终态现取）：**248 passed／0 failed／192.60 s／exit=0**（`.venv` 串行）。点名清单＝`tests/test_r626_legacy_silent_empty_teeth.py`·`test_r60_write_path_unique_under_pgvector.py`·`test_r625_chroma_write_sites_are_named_one_by_one.py`·`test_r59_chroma_untouched_on_pg_reads.py`·`test_r120_p3_collection_default.py`·`test_r269_exit_codes.py`·`test_r276_vector_wording_pin.py`·`test_r253_no_test_rewrites_a_tracked_file.py`·`test_r238_bare_connect_ratchet.py`·`test_r134_chroma_writeback.py`·`test_r389_r382_connects_go_through_the_boundary.py`·`test_r233_undefined_root_names.py`·`test_r115_doc_content_limit_is_single_source.py`。
  ⇒ 量具不自开 `PersistentClient`、不自裸 connect、不新增 SQL：两枚全仓账（15 枚裸 connect＝app 14／scripts 1，开库收口名册）枚数一字未变。R134 那层改道闸门的读数按席分开写，不借花献佛：本单牙单独跑时 `PersistentClient 调用: 0 次`；13 枚件同席复跑时该层报 **20 次，落点被改道出工作树 20 次（2 个原路径）**——那 20 次全是 test_r134 自己的用例在改道，一枚都没落进树里的 `chroma_db`。
- 口径钉独立复跑：`python scripts/check_vector_wording.py` ⇒ 36 枚文档全部通过（含本纸）。
- 字节卫生：三枚文件 CR=0／纯 LF、无 BOM、无 0x00/07/08/0B/0C，末尾各一个换行（本单走的是单引号 here-string 直写字节，反引号计数与正文预期相符：量具 40 枚、牙 22 枚、本纸 250 枚）。
- 口径钉：`scripts/check_vector_wording.py` 对全仓扫描结果见跟进单交回段（本纸按「生产向量库＝PGVector／遗留件退役中·退役未完」写，两头的假话都没写）。
- 🔴 并树时的第二态：本席不 commit，`git commit` 之后请在**干净树**复跑同名件一遍再记数（AGENTS.md 两态规矩；dirty 态那一列不许当永真判据）。

### 7.1 施工期一次自我更正（写下来防第二遍）

守卫第一版把"零变异"读成"现役卷一律不许碰"，于是 `snapshot_volume()` 也拒现役卷——那一版
把 §3 的容器配方挡死在复制这一步（容器里 `ROOT=/app`，`/app/chroma_db` 命中 `is_live_volume`）。
本单的口径只有打开客户端这一层有害，复制是纯读，所以正解是分家：源可以是它、开的必须不是它、
前后各做一枚 sha256 内容清单对账。改完的凭据＝§4 那五枚零变异用例，以及一次真读数的自证：
本席在 `be-r626` 上对**被跟踪的工作树卷** `chroma_db`（6 枚文件／8,300,742 B）在整场 CLI 冒烟前后
各做一遍 `volume_inventory()`，两遍摘要全等（`08d535f782b24f3b…`）——全程只有读，没有开。

**本单不做的三件事**（免得下一班误读）：不修 Chroma、不停 Chroma 写（S0 已随 R60 并树完成，见计划书 §15）、不翻 `INDEX_BACKEND_DEFAULT`（业主 10-03 裁定，属交付阶段项）。
