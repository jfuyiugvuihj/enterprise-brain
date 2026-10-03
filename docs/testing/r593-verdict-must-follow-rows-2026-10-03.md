# R593 · 空表台账的裁定必须跟着现读走（10-03 清障单，零产品码、零写库）

- 执行层席位：R593（本纸作者），工作树 `be-r593`，基点 **`6fcea4f`**＝派工时主树 HEAD。
- 写域（一格没越）：`scripts/r483_empty_tables_triage.py`、
  `tests/test_r483_empty_table_triage_is_derived.py`、`docs/testing/r483-empty-tables-2026-09-29.md`
  （只能由 `--sync` 生成）、本纸。`app/**` 一枚没碰——`app/api/v1/alerts.py` 那 +56 行是 R582 在总控手上的活。
- 这单的性质：总控 10-03 11:1x 现取已经定了缺陷本体，本席只做两件事——**把三格定性按现读重落**，
  以及**把唯一挡住 R582 并树的那枚永久红反证钉改成派生钉**。

## 一、缺陷本体其实是三层，不是一层

1. **假话层**（总控已点名）：`alerts` / `alert_rules` / `retrieval_traces` 三格今天有行，文档里仍写
   `legitimately_empty` / `needs_owner`。这三词每一词都额外断言「此刻这枚表一行没有」。
2. **无出路层**（本席现取补的一层）：那三行 problems 是记账件自己报的，但它给的出路是「重跑
   `--sync`」——而旧 validator 那一腿是无条件的 `if rows != 0:`，它**不看裁定用了哪个词**，
   所以重跑一万次也照报；而词表里根本没有一个词能诚实描述「有行」。
   ⇒ 改判无处可改，报的过期无法被满足：这是一枚**结构上没有出口的牙**。它的存在说明旧盘的
   「0 行」不是判据而是假设。本席在基点复跑同一枚命令取到同一句原话（911→938，见下表），
   两次读数不同而 problems 逐字相同，正是「数在动、结论没动」的铁证。
3. **传染层**：`tests/test_r483_empty_table_triage_is_derived.py::test_blade_c_...` 最后一行
   `assert not any(M.rows_of(READINGS, table)["rows"] for table in M.TARGET_TABLES)`——
   它把「在册目标表此刻全 0 行」当成常驻不变量。这台机器只要真被用过一次，这枚钉就永久红，
   连带把主树全量门钉成一枚不可能出现的绿票。总控 11:1x 复现的 1 failed / 19 passed 就是它。

## 二、现读取证（本席在 `be-r593`@`6fcea4f` 亲手跑，全部只 SELECT）

| 命令 | rc | 交回 |
|---|---:|---|
| `python scripts/r483_empty_tables_triage.py --json`（改判前） | 1 | 三行 problems 原话：`alerts 今天已经有 4 行了，本单的 0 行定性过期，重跑 --sync` / `alert_rules 今天已经有 4 行了，…` / `retrieval_traces 今天已经有 938 行了，…` |
| `python scripts/r483_empty_tables_triage.py --sync`（改判前） | 1 | `problems=3` |
| 同一枚命令（本席改判 + 改 validator 之后，11:5x 落盘 `--sync`） | 0 | `problems=0`；再生件三格裁定已是 `no_longer_empty`（4 / 4 / **979** 行） |
| `--check`（离线逐字节复现） | 0 | `PASS check：八枚表 + 两枚对照 + 现扫写入点全部逐字节复现，problems=0` |

上游归因（只读现取，`docker exec enterprise-brain-postgres-1 psql ... -c "SET default_transaction_read_only = on" -c "<SELECT>"`）：
`alert_rules` 里 4 行全部 `enabled=true`、名字以 `r577-sample-` 起头——是 `scripts/r577_demo_sample_seed.py`
经 **POST /api/v1/alerts/rules** 建的演示样本规则（走的就是本格在册那条写入道，不是道外插的）；
`alerts` 4 行 = 巡检真命中的产物（`status` 里能看到 open/acknowledged/closed 三种处置态，处置那腿是 UPDATE 不加行）；
`retrieval_traces` 从总控 11:1x 的 911 长到本席复跑的 938，`trace_events` 里 `retrieval.completed` 同步在长。
⇒ 三格的行都是**产品道写进来的**，所以本纸不是在替「库被人手改过」找台阶，是在替「这台机器真被人用过」记账。

🔴 同一条读数在本文写作的三分钟内从 938 长到 979（问答窗还在跑）：**这就是本单把数字交给渲染、
不留进裁定的现场理由**。谁把「911」「938」「979」里任何一枚抄进结论句，下一班就只能等它变成假话。

## 三、改了什么（逐格点名）

### 生成器 `scripts/r483_empty_tables_triage.py`

- 裁定词表加第四词 `no_longer_empty`，并派生两堆常量：`ZERO_ROW_VERDICTS`（预设 0 行的那三词）与
  `NONZERO_ROW_VERDICT`。**加词而不是把旧词改宽**——旧三词各自还钉着自己的判据（欠码 / 本该空 / 只能等业主），
  把它们改成「空不空都算」等于把这族钉的牙拔了。
- `validate()` 第一族牙改形：`rows != 0 就报过期` → **裁定用词与现读行数互为牙齿，两个方向都咬**
  （0 行词配非 0 行 → 点名；`no_longer_empty` 配 0 行 → 同样点名）。点名统一带钥匙串
  `ROW_MISMATCH_PHRASE = "定性过期"`，反证钉按它找点名，改措辞就得一起改钉。
- 产品面那一腿从 `verdict in ("legitimately_empty", "needs_owner")` 改成 `verdict != "no_seed_path"`：
  新词照样要道——有行却爬不到产品面，是「行是道外写的」那一格疑点，不是可以放过的一格。
  🔴 措辞里保留「应改判 no_seed_path」原句：`tests/test_r550_counter_evidence_teeth.py` 那六把刀就按这四个字找点名。
- 三格 `TRIAGE` 各加 `re_ruling` 字段，凭据＝上面那三行 problems 原话（带时刻与基点号），
  并把 `why` 里已被现读推翻的句子就地点名作废（alerts 那句「一枚启用规则都没有」、
  alert_rules 那句「演示库从没建过规则」、retrieval_traces 那句「这轮行为还没留下痕」）。
  🔴 `alert_rules` 的 `why` 明确留着没被推翻的那半句：样本规则不是业主口径，**业主欠的那一次录入并没有被
  演示种子替它满足**，只是它不再是「表是空的」这件事。
- `render_per_table()` 把 `re_ruling` 与「**本格今日现读 N 行**」渲染在同一行：数字出自 `readout`，
  不在裁定散文里过夜。历史引用可以留数，但必须与今天的数并排、且标明是引用。
- `_emptiness_claim()` 新函数：V2 三句自述那句「今天没有一行××」改由现读决定；#11 的推论句
  （「挡在前面的是业主一条启用规则」）与 #17 的 (乙) 边界同样跟着行数翻面。
  🔴 非空那一支的措辞里刻意不含「没有一行」四个字——`test_the_three_v2_sentences_...` 就是按这四个字的
  出现与否来验话术与读数同面的。
- 文档头部：标题改「八枚『当时 0 行』表」，加一行由 `len(nonzero)` 现算的 R593 改口声明；
  「裁定只有三词」改成 `str(len(VERDICTS))`；「结论一句话」改成四词计数 + `四数之和 = 8` 的自证。

### 测试件 `tests/test_r483_empty_table_triage_is_derived.py`（20 枚 → 22 枚，一枚没放宽）

- `test_blade_c_an_empty_scan_root_names_every_table_that_lost_its_basis`：最后一行那句全零断言
  换成**两面对打的派生腿**——面 A 把任一表现读翻到与裁定相反的一面 → validator 必须点名；
  面 B 翻回相合的一面 → 同一张表必须不再被点名。两面都不引用「今天的数是多少」，
  所以库长到多少行、被谁清过，这枚钉量的还是同一件事。前半段（空扫描根 → 每张失去依据的表被点名）
  原样保留，并把「失去依据」的判据从「裁定在三词里」改成「裁定不是 no_seed_path」，覆盖面只增不减。
- `test_retrieval_traces_...`：改名并摘掉第一行那句 `verdict == "legitimately_empty"`——那是把 09-30 的
  读数当判据，与 blade_c 同一枚病。产品道必须真在 / 跨跳必须带事件标签 / 调试面不许冒充 / 豁免必须用得上 /
  09-29 那句必须被点名作废：五格一手没动，另加「把现读翻面 validator 必须点名」一手。
- `test_the_three_v2_sentences_say_plainly_what_is_missing`：`assert "没有一行" in line` 换成
  `("没有一行" in line) == 本 chain 点名的目标表全为 0 行`。逐表名 + 逐表行数「N 行」的原断言照旧。
- `test_the_verdict_vocabulary_is_closed_and_all_three_words_have_instances` → `..._every_word_has_an_instance`：
  词表封闭 + 每词有实例照旧，另钉「新旧两堆不许并成一堆」。
- 新增 `test_a_verdict_word_must_match_whether_that_table_has_rows_today`（判据①的正面：逐格验词与数同面）
  与 `test_every_re_ruled_cell_carries_the_problems_line_that_forced_it`（判据①的反面：改判必须带 problems
  原话凭据，且凭据那一行必须与今日现读同屏渲染；没改判的格不许私留改判凭据）。
  🔴 这枚新钉同时是反证 K2 的靶子：手把某表裁定按回与现读矛盾的词，它当场红。

## 四、反证三把（判据④）

| 刀 | 摘掉的那一步 | 摘前 sha12 | 摘后 sha12 | 现场读数（本席亲跑） | 逐字节还原 |
|---|---|---|---|---|---|
| **K1** | `validate()` 里「裁定词 vs 现读行数」那一腿整段摘掉（两个方向的点名一起没） | `3c13154d008f`（生成器＝交付态） | `5f537ead1bd7` | `tests/test_r483_empty_table_triage_is_derived.py -k blade_c` → rc=1｜**1 failed**, 21 deselected（43.96 s） | `restored=3c13154d008f`＝摘前，逐字节等 |
| **K2** | `TRIAGE["alerts"]["verdict"]` 手写成与现读（4 行）矛盾的 `legitimately_empty` | `3c13154d008f`（生成器＝交付态） | `f3843b18f278` | 本族 `-k verdict_word_must_match or re_ruled_cell` → rc=1｜**2 failed, 20 deselected**（词与数不同面那枚 + 改判凭据那枚，各自独立红）；**变异仍挂在盘上时**再跑邻族 `tests/test_r550_event_hop_climb_is_generic.py -k pristine_readings or ruling_word` → rc=1｜**1 failed, 1 passed**（`test_the_pristine_readings_report_no_problems` 红＝在册读数件当场拒绝这份裁定） | `restored=3c13154d008f`＝摘前（本族 34.02 s、邻族 37.08 s） |
| **K3** | `blade_c` 换回改前那句全零断言 `assert not any(M.rows_of(READINGS, table)["rows"] …)`（派生腿照旧留着，只把旧断言按回来） | `d1138da730c2`（测试件） | `29e9bbf8345a` | `-k blade_c` → rc=1｜**1 failed, 21 deselected**（99.60 s）——旧断言在本单改判后的盘面上**不再恒绿**，它红在 `alerts` / `alert_rules` / `retrieval_traces` 三枚非 0 读数上 | `restored=d1138da730c2`＝摘前 |

🔴 本单还自纠了一处自己写出来的假话：`render_document()` 那句「结论一句话」的第一版把
`alert_rules` 的业主口径缺口塞进了 `needs_owner` 那一堆——它今天已经不在那堆里了。本席在交回前
现读文档时抓到，改回四词纯计数 + 「每格到底还欠什么只在本格那一节写」，并再生一次（`--sync` rc=0、
`problems=0`）、22 枚重跑。写这条不是表功：**这枚病的 recurrence 就是「我以为我在引用读数，其实我在引用上一班」**。

🔴 三把刀都在**自纠后的交付字节**上重跑过一遍（sha 对与读数即上表）；首轮读数是 `7966bdb3ada4` /
`940dbf656dbe` / `29e9bbf8345a`——K3 那枚摘后 sha 两轮相同，因为那把刀只动测试件，本席的自纠只动了生成器。
还原后 `--check` 再跑：rc=0。三把刀都做在盘上真件、跑完即还原，K2 那一把特意把邻族 `test_r550` 一起挂着跑：**手改裁定不但本族红，
连「原始读数不该报 problem」那枚在册钉也红**——这一族的钉是一张网，不是单点。
K3 交的是判据④要的第三件事：旧断言既不是被删掉、也没换成 `assert True`，它在改判后的盘面上自己站不住。

## 五、结构性教训：一枚病的三个面

这一族的错法不是「数抄错了」，是**把此刻的盘面读数当成了判据本身**。同一枚病在本仓有三个面：

1. **假红**（本单的 blade_c）：判据 = 一次读数 ⇒ 世界一动它就红。它红得「有理」，于是每台被真用过的机器
   都长出一枚不可能消除的红，全量门永远凑不出干净绿票。
2. **假话**（本单的三格定性）：结论 = 一次读数 ⇒ 世界一动它就是假话。更坏的是记账件**自己知道**
   （problems 报了），却没有任何出口能满足那条报——因为词表里没有描述「有行」的词。
3. **假绿**（R587 那一格）：一次演练的绿 = 常驻结论 ⇒「备份恢复演练通过」这句在缺库级 GUC 的证据上
   照样发绿。方向与 1、2 相反（多信 vs 少信），病根同源：**把一次性读数当成不会变的性质**。

AGENTS.md 已经有两条同治的规矩，本单是第三次踩、第一次踩在**测试件**上：

- `AGENTS.md:53`「常驻钉不许把『此刻盘面脏不脏』当成判据」——同一枚病的 dirty 态版本（R496 事故 #96）。
- `docs/handoff/2026-09-15-orchestration-board.md:966`「引用数字前先查后续实测有没有推翻它」——
  本单第二节那枚 911→938 就是这条规矩的现场版。

⇒ **落进代码的口径**（后续任何生成件 / 台账件都按这三条写）：
① 判据只写**关系**（读数 ↔ 裁定 / 生成物 ↔ 现扫 / 演练产物 ↔ 源库），不写读数；
② 读数永远现取，散文里一枚数都不留；非要留（历史引用）就必须与今天的数**同屏并排**并标明是引用；
③ 词表 / 结论 / 门的每一条措辞，都要能回答「世界变了它说什么」——答不上来的措辞就是假话预备役。

## 六、R582 与 R587 各被这一族伤在哪一格

- **R582（告警处置三写口不落审计账，`app/api/v1/alerts.py`，在总控手上待并）被挡的正是 `test_blade_c_...`
  那最后一行**。总控在主树跑过一次 `--sync` 之后，19 passed / 1 failed，唯一的红就是它——它与 R582 的
  改动内容无关，只与「这台机器被用过了」有关，所以 R582 无论怎么改都绕不过：并树被一枚假红挡死。
  另两格坐标红（总控在主树现取到的 `alerts.py:724→780`、`957→1017`）不是本单的事，那是跟进单 §157 记明的
  「R582 并树后必须重跑 `--sync`」——生成件不许手抄，红了就是让你重跑。
- **R587（库级 GUC 不在 `pg_dump` 里，恢复库 `app.embedding_dimension` 变 MISSING）被牵连的是同一格病 + 一枚传染**：
  ① 它的本体就是「把一次演练的绿当常驻结论」（本文第五节第 3 面），与本单的 ①② 面同源；
  ② 它的判据④ 要交三把反证（摘掉施加那一步第③格必须红 / 改源库一枚值必须红 / 恢复库为空必须红），
     判 E 门与 R60 ⑤ 那格回滚演练都以「同名件能给出可信绿」为前提——而 blade_c 这枚永久红挂在主树全量门里，
     任何一班想出示干净绿票都得先解释一枚与自己无关的红。**传染的是绿票的可信度，不是文件。**

## 七、本席现取到的、不属于本单的一格（如实报，未动）

干净基点 `6fcea4f` 上，`test_the_in_tree_document_is_the_regenerated_one_byte_for_byte` **本来就是红的**：
盘上那份文档的「表名在 app/ 与 scripts/ 里现扫到 N 行 / M 枚文件」与我这棵树的现扫不一致
（`alerts` 116/17 → 146/18、`alert_rules` 9/2 → 13/3、`user_profiles` 19/5 → 20/6）。
⇒ 有人在没有重跑 `--sync` 的情况下把文档提交进树了（同一枚 commit 里文档比扫描现场旧）。
本单最后一次 `--sync` 顺带把它对齐了；**归因不在 R593，本席不认领也不替谁认领，请总控按并树史自取**。
另：`tests/test_r536_retrieval_completed_on_product_lane.py:5` 与 `tests/test_r536_single_emission_point.py:16`
把「口径出处」写成 `docs/testing/r483-empty-tables-2026-09-29.md:104`——那是散文指针不是断言（本席核过，
两枚件都不读文档内容），但再生件行号会漂，这类「文档第几行」的引用天生是过期账，
不在本单写域，留给总控裁定要不要换成锚词。
- 还有一处同类过期账（本席现取，未动）：`scripts/r577_demo_sample_seed.py:170` 与 `:181`、
  `tests/test_r577_demo_sample_seed.py:431` 把「拦无归属告警冒充闭环」这件事称作『`needs_owner` 那一格』。
  那一格今天已按现读改判 `no_longer_empty`——R577 那把闸的**语义**一点没变（它拦的是 `alerts.department`
  为空的行），但引用词过期了。三枚文件都不在本单写域，报总控，本席一字未动。

## 八、复跑（本单全部读数都能这样重取）

```powershell
# 现读 PG + 现扫源码，回写整枚文档（改判后应 rc=0、problems=0）
python scripts/r483_empty_tables_triage.py --sync
# 离线逐字节复现（不碰库）
python scripts/r483_empty_tables_triage.py --check
# 本族 22 枚钉
python -m pytest tests/test_r483_empty_table_triage_is_derived.py -o addopts= -p no:cacheprovider --basetemp=$env:TEMP\r593x -q
# 邻族在册件（本单没改它们，但它们吃同一枚生成器）
python -m pytest tests/test_r550_event_hop_climb_is_generic.py tests/test_r550_counter_evidence_teeth.py ``
                 tests/test_r498_landing_shape_is_not_a_mention.py tests/test_r536_retrieval_completed_on_product_lane.py ``
                 tests/test_r536_single_emission_point.py -o addopts= -p no:cacheprovider -q
```

本席亲跑的读数（`be-r593`@`6fcea4f`，交付态）：`--sync` → rc=0 `problems=0`；`--check` → rc=0；
`--check --verify-live` → **rc=7 报漂**（`retrieval_traces` 979 → 994，`sessions` / `trace_events` / `agent_runs`
同窗齐涨）——这不是缺陷，是这面尺子该报的话：**问答窗此刻还在跑**。它同时把本单的论证实测了一遍：
谁的文档里写着「979」，谁在十分钟后就有一句假话；三格裁定 `no_longer_empty` 对 994 与 979 同真。
`tests/test_r483_empty_table_triage_is_derived.py` → **22 passed**（改前 20 枚）；
邻族在册件 `tests/test_r550_event_hop_climb_is_generic.py` + `tests/test_r550_counter_evidence_teeth.py` +
`tests/test_r498_landing_shape_is_not_a_mention.py` + `tests/test_r536_retrieval_completed_on_product_lane.py` +
`tests/test_r536_single_emission_point.py` → **101 passed**（本单没改它们，它们吃同一枚生成器）。
🔴 没跑的：全量门 `scripts/run_gate.py`（派工令禁跑）。

🔴 **并树之后必做的一格**：本纸与文档里的坐标（`alerts.py:724` / `:957`）是**基点态 `6fcea4f` 的现扫**，
不是主树。R582 一并，`app/api/v1/alerts.py` 净插几十行（跟进单 §157 记的那一档是 +60）⇒ 哨兵区两枚坐标必然漂——总控 11:1x 在主树现取到的是 `alerts.py:724→780` 与 `957→1017`，本席这棵树里仍是基点态 `:724` / `:957`，两枚都出自现扫，一枚没抄，正解是再跑一次 `--sync`——
那是这枚钉设计好的出路，不是新缺陷（跟进单 §157 已记同一口径）。
## 九、交付盘面（本席亲取，`be-r593`，HEAD 仍是基点 `6fcea4f`＝零 commit）

| 件 | sha256 前 12 | 字节 | 换行 | BOM |
|---|---|---:|---|---|
| `scripts/r483_empty_tables_triage.py` | `3c13154d008f` | 97612 | CRLF 单形（与基点同形） | 无 |
| `tests/test_r483_empty_table_triage_is_derived.py` | `d1138da730c2` | 21694 | CRLF 单形 | 无 |
| `docs/testing/r483-empty-tables-2026-09-29.md` | `057f282228e0` | 29917 | LF 单形（`--sync` 用 `newline="\n"` 写，天然 LF） | 无 |
| `docs/testing/r593-verdict-must-follow-rows-2026-10-03.md` | 本纸（自指 sha 由回执交回） | — | LF 单形 | 无 |

`git diff --numstat HEAD`：`docs/testing/r483-empty-tables-2026-09-29.md 73/67`、
`scripts/r483_empty_tables_triage.py 145/47`、`tests/test_r483_empty_table_triage_is_derived.py 117/16`；
未跟踪仅本纸一枚。**`app/**` 零写入**（`alerts.py` 那 +60 行是 R582 的，本席没碰）。

读数一览（交付态文档里现读的三格）：`alerts` 4 行、`alert_rules` 4 行、`retrieval_traces` 979 行，
三格裁定 `no_longer_empty`；其余五格仍按 09-29 的三词定性（`no_seed_path` ×2、`legitimately_empty` ×2、
`needs_owner` ×1）。对照表两枚（`chunk_vectors` / `sessions`）非空，尺子没空转。

复跑次数（本席亲跑，不是执行层自报口径之外的东西——本纸全部数字都出自这些现场读数）：

- `--sync` 三次：改判前 rc=1 `problems=3`（取证）→ 改判后 rc=0 `problems=0` → 结论句自纠后再 sync，rc=0。
- `--check` 三次（改判后交付态 / 自纠再生后 / 三把刀还原后）：均 rc=0，末次 `PASS check：… problems=0`。
- `--check --verify-live`：rc=7 报漂（979→994 等四格）——如实记，见第八节。
- 本族 `tests/test_r483_empty_table_triage_is_derived.py`：**22 passed** 四遍——239.43 s（首次改判后）/
  214.70 s（sync 之后）/ 222.98 s 与 180.59 s（**交付态最终字节**，自纠 + 第三次 sync 之后）。
- 邻族五件：`tests/test_r550_event_hop_climb_is_generic.py`、`tests/test_r550_counter_evidence_teeth.py`、
  `tests/test_r498_landing_shape_is_not_a_mention.py`、`tests/test_r536_retrieval_completed_on_product_lane.py`、
  `tests/test_r536_single_emission_point.py`：**101 passed** 两遍——486.34 s（改判后、自纠前）与
  436.93 s（12:34:46→12:42:22 现取，**交付态最终字节 + 三把刀还原之后**）。
- 🔴 **没跑的格子（如实）**：全量门 `scripts/run_gate.py`（派工令禁跑，按令未跑）；
  `tests/test_r577_demo_sample_seed.py` 与 `tests/test_r251_alert_disposal.py` 未跑——本单写域外，
  且 r577 那件依赖活的评测环境，本席不代跑；`scripts/r484_session_read_leg_ledger.py`、
  `scripts/r525_activity_prior_readout.py` 只是引用本单房规的旁支生成器，未跑（只核对它们不 import 本单生成器）。