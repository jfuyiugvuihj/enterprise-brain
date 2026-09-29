# R496 · 禁域自护钉的作用域（2026-09-29）

被治的件：`tests/test_r453_cloud_eval_override.py`。刀：`tests/test_r496_forbidden_pin_scope.py`。
基点 438d67d，树 be-r496，本回合全部读数亲自现跑；影子副本道，盘上零写入。

## 1. 两枚钉各自真正在主张什么（返工前的原样）

- **钉 A**（原 `:396-400`，`test_forbidden_domain_files_are_unmodified_in_this_worktree`）
  标题与判据④要的主张：「**R453 没有写过禁域**」。它实际用的量具：`dirty_forbidden_paths(git_status_porcelain())`
  ＝「**这棵树此刻相对 HEAD，在 `FORBIDDEN_PATHS` 之下没有受跟踪的改动**」。
- **钉 B**（原 `:427-430`，`test_registered_in_book_files_carry_no_modification_or_deletion`）
  主张：「**R453 没有顺手改别人的在册件**」。量具同样是盘面：`REGISTERED_FILES` 里任何一枚呈 M/D/R/C/T。

主张的主语是本单，量具的主语是这棵树。两者只在一条纪律下等价：**一棵施工树只有一枚 Agent 的手**
（AGENTS.md：并行的边界是写集，一枚 Agent 独占一棵工作树）。这条纪律一破，或者盘面里混进别人已提交的历史，
这两枚钉就会把别人的合法施工读成本单的罪证。

「工作树此刻相对 HEAD 干净」为什么不是正确量具——它漏的不是边缘情况，而是归因本身：

1. **不区分作者**。09-29 主树并 R471：R471 合法改过在册量具 `scripts/eval_transport_ask_v2.py`，
   改前 32 枚读物者里只有这两枚红，原文 `AssertionError: 在册件被改动：['M scripts/eval_transport_ask_v2.py']`。
   那两枚红指控错了当事人，对本单不构成任何证据。
2. **不区分「是否已落进版本控制」**。越界一旦随交付提交，盘面立刻干净、两枚钉当场转绿（同一枚钉 09-29 提交后复跑即绿）。
   这枚绿不是结论，只是量具失效——常驻钉最容易变绿的形，恰是它唯一守不住的那个形。
3. **不区分「本单在此树有没有写过字」**。主树常年挂着业主的永久脏项与并存别的单的新文件（本件 09-28 就为这条退回过一次：
   把任何未跟踪条目判成越界＝并树即永久红）。盘面干净与否从来不属于本单名下。

归因需要的信息是「这一笔是谁的手」，它不在 `git status` 里；只在两个地方：**本单自己的名字有没有动**（活体），
**提交号挂在谁名下**（历史）。

## 2. 返工后的形状：归因两层＋实质一层

| 层 | 判决函数 | 量具 | 何时开口 |
| --- | --- | --- | --- |
| 归因·活体 | `forbidden_overreach_verdict`／`registered_overreach_verdict` | `construction_fingerprint`＝`DELIVERED_FILES`（含写域前缀下新未跟踪钉）在本树相对 HEAD 有没有手 | 指纹非空（本单正在此树施工）；指纹为空 ⇒ 沉默＝不适用，不是告警、不是 skip、不是降级 |
| 归因·历史 | `signed_commit_overreach_verdict` | subject 开头挂本单号 R453 的并树提交，逐枚 `git show --name-only --no-renames -m --first-parent` 取落点 | 交付件已进 HEAD 时恒开：名册读空要红（防号格式漂），落点撞禁域要红 |
| 实质 | `evaluation_set_verdict`／`gate_verdict`／`foreign_surface_verdict` | 现读盘上文本与题数 | 任何树、任何时刻，与本单有没有施工无关 |

`FORBIDDEN_PATHS` 12 枚、`REGISTERED_FILES` 12 枚**一枚未删**，两枚活体钉的红句照样点名文件，
没有 assert→warning 的降级，没有 skip，没有 `xfail`。

## 3. 为什么不选另一案

- **只用甲案（作用域化）**：能把 09-29 的假红治干净，也守得住 09-28（原地改真树 `docker-compose.yml`）那一形；
  但它对「越界随交付一起提交」完全沉默——也就是把旧钉唯一真正的盲点原样留下。不够。
- **只用乙案（提交链归因）**：归因比甲案干净（后来合法并树不会记到本单头上），但并树之前那一整段施工期它读不到任何提交，
  而真越界恰恰发生在这一段。不够。
- **所以取甲＋乙＋实质层。** 当场证据（§5 第五把刀，同一棵影子树同一时刻）：盘面 0 条读数 ⇒ 活体两层全绿，
  历史层红 `['47619330 scripts/run_gate.py']`。这一形旧钉一辈子读不出来。
- 判据④要求的那句「真有人在这棵树里动了 `app/**`，钉会不会红」：
  本单在此树施工 ⇒ 红（甲案层，实测 2 枚判决皆红且点名）；本单在此树零写入 ⇒ 活体层沉默，
  而本单没写过一个字时任何指控都是假话——`app/**` 的保护那时由它自己的那族件与总控的 apply 检查承担，不该由一枚 R453 的常驻钉代管。
  两案在这一点上没有实质差别，甲案至少不把假红当成保护。

## 4. 实质保护一枚没丢（新增的内容不变量）

- **`tests/test_evaluation_report.py` 对评测集的保护** ⇒ `evaluation_set_breaches`：口径调用（`evaluate_evaluation_set`）在场、
  `def test_` ≥8 枚、100 行集 ≥100、沿用 30 行集 ≥30 且其 id 一枚不许从 100 行集里消失、行七字段齐、三档（问答／分析／报告）各 ≥20、
  同指标两部门成对题 ≥6 对。R36 的地板数写死在本件，谁裁瘦谁红，与盘面无关。
- **`scripts/run_gate.py` 的保护** ⇒ `regression_gate_breaches`：ast 现读 `BASE_ARGS` 字面列表，默认参数里不许出现
  `-m <标记表达式>`／`-k`／`--deselect`／`--ignore`／`-G`，不许把目标写死成子集（全量门不许退化成定向门），
  `loadfile` 必须在场（否则嵌套 pytest／起子进程容器的件被拆成假红），
  且 `pyproject.toml` 的 `addopts` 里不许落下 `-n`／`--dist`／`-p`（AGENTS.md：全局并行会递归扇出）。
- **`app/**`·`frontend/**` 对本单的越界保护** ⇒ 除了上面两枚活体钉与历史层，另有 `foreign_surface_reaches`：
  这页 override 一旦长出 `volumes`／`build`／`env_file`／`depends_on`／`image`／`command`／`entrypoint`／`ports`
  或出现 `./app:/…`·`/frontend:…` 这类 bind-mount 形状就红（注释里引用 `app/agents/nodes.py` 不误伤：只读非注释行）。

## 5. 刀表（全部走 `shadow_repo` 影子副本道；每把末尾现读真树全集摘要，与 import 那一刻逐字相等）

| # | 刀 | 期望 | 实测 |
| --- | --- | --- | --- |
| ④甲 | 本单交付件干净＋`scripts/eval_transport_ask_v2.py` 相对 HEAD 为 `M`（R471 那一形） | 活体两层沉默；不套闸门的旧读数必须红，否则「沉默」是空响 | 盘面 1 条；施工指纹 `[]`；旧形状禁域红 1 枚／在册件红 1 枚＝`['M scripts/eval_transport_ask_v2.py']`；`forbidden_dirt_reading`/`registered_dirt_reading`＝`([], [])`，两枚 verdict 均 GREEN；名册 `[]`、`signed_commit_overreach` `[]`（不替别人喊狼） |
| ④甲′ | 别人在这棵树动了 `app/agents/nodes.py`，本单零写入 | 活体层沉默＋历史层不记本单头上 | 旧形状读 1 条红；施工指纹 `[]`；两枚 verdict GREEN；`signed_commit_overreach` `[]` |
| ⑤乙 | 动一枚交付件（施工指纹为真）＋`app/agents/nodes.py` 为 `M` | 两枚活体钉红且点名 | 指纹 `['M deploy/compose.cloud-eval.yaml']`；两枚 RED，红句原文含 `['M app/agents/nodes.py']`（全文见回执刀表） |
| ⑤乙′ | 同上＋`tests/test_evaluation_report.py` 为 `M` | 必须红 | 禁域钉 RED、在册件钉 RED，均点名该件 |
| ⑤乙″ | 同上＋`scripts/run_gate.py` 为 `M`；同 parametrized 共 9 枚路径逐枚来一次 | 必须红 | 9 枚 victim 逐枚红（`docs/testing/evaluation-30.md` 与 `frontend/.gitignore` 等按各自名单分配：在册件名册里没有的，只有禁域钉红，实测 1 枚） |
| ⑤新钉日 | 并树前第一天：交付件全是未跟踪新件＋`app/common/model_config.py` 为 `M` | 闸门不许把本单的手读成别人家 | 施工指纹非空，禁域钉 RED 点名该件 |
| 补盲点 | 越界随交付一起提交（subject 挂 R453）后跑同一枚钉 | 盘面已干净 ⇒ 活体绿；历史层必须红 | 盘面 0 条，两枚活体 GREEN，`signed_commit_overreach`＝`['47619330 scripts/run_gate.py']`，verdict RED |
| 名册归因 | 别人挂号的提交（`并树 R471 …`）动了同一枚在册量具 | 不进本单名册 | `ticket_landing_commits`＝`[]`；名册空而交付件在 HEAD ⇒ verdict 红（「静默空响」那一支），证明它不会静默通过 |

## 6. 数字（本回合亲自跑）

- ① `def test_` 29 → 39（只升）；`assert` 66 → 113；逐族 LOST 为空（`compare:Eq` 35→48、`not name` 11→15、`boolop:And` 4→10、
  `other:Name` 1→4，其余各族不减，新增 `Is`／`Gt`／`LtE`／`evaluation_set_breaches`／`regression_gate_breaches` 等族）。
  对照基准＝HEAD blob 字节（`git show 438d67d:tests/test_r453_cloud_eval_override.py`）对磁盘字节，不是同源对照。
- ② `FORBIDDEN_PATHS` 改前 12 枚／改后 12 枚，逐字等值，LOST＝空、GAINED＝空；`REGISTERED_FILES` 同样 12→12。
- ③ 干净树基线：本树只动了它自己 ⇒ `tests/test_r453_cloud_eval_override.py` **58 passed**（0 failed／0 skipped）。
- ⑥ 邻居同跑：`test_r453_cloud_shape_caliber` 48 passed／`test_r453_default_env_baseline` 11 passed 2 skipped／
  `test_r453_nested_pytest_selection_guard` 18 passed（这枚件按名字认 `test_r453_cloud_eval_override.py`，见它 `:422`）／
  `test_r471_second_copy_of_the_answer_body_is_not_a_pass` 16 passed／
  `test_r218_ruler_self_calibration` 9 passed／`test_r496_forbidden_pin_scope` 16 passed；七枚件同跑＝**176 passed, 2 skipped**（改前改后同数：
  那两枚 skip 是该件自带的 acceptance 形，与本单无关；同前缀那三枚在册件与本件之间零 import——
  `rg "import .*test_r453|cloud_eval_override" tests` 现取，除本单新刀外无一枚件按模块载被治件）。
- 行尾：本机 `core.autocrlf=true`，三枚文件盘上统一 CRLF（与仓库 checkout 同形），`git diff --numstat` 因此是 458/15，不含行尾噪声。
- ⑦ `rg -c classification_blocked app/` 现取 0 命中（rg exit 1）；本单两枚件里 `chroma` 零命中，未新增向量库依赖或写点（生产向量库＝PGVector，Chroma 是退役中的遗留件）。
- 写域：`git status --porcelain -uall` ＝ ` M tests/test_r453_cloud_eval_override.py` ＋ `?? tests/test_r496_forbidden_pin_scope.py`
  ＋本文档；`scripts/**`·`app/**`·`frontend/**`·`pyproject.toml`·同前缀那三枚 `test_r453_*`·`tests/test_evaluation_report.py` 一字未动。
- 刀件枚数：`tests/test_r496_forbidden_pin_scope.py` ＝ 8 枚 `def test_`／16 枚 collected（其中那枚 parametrized 带 9 把 victim）。
- 邻侧卫生件（会扫 `tests/` 全集的那族，怕的是新件给它们添假红）：
  `test_r253_no_test_rewrites_a_tracked_file`＋`test_r238_bare_connect_ratchet`＋`test_r238_connect_boundary_policy`＋
  `test_r233_undefined_root_names`＋`test_r449_nested_pytest_basetemp_contract`＋`test_r449_shared_temp_root_is_the_hazard`＋
  `test_r379_stale_bytecode_cannot_lie`＋`test_r376_gate_shape_pins` 同跑＝**136 passed, 8 warnings, 0 failed**（87.63 s）；
  本单两枚件另跑一次 `-W error`＝72 passed 2 deselected（`-k "not nothing"` 那两枚被我自己筛掉），即两枚件里零告警。
  影子根全落 `tmp_path`，真树摘要每把自证与 import 那一刻逐字相等。

## 7. 今天没做到的（明写）

- **改前的 passed 数没由我亲自跑**：48 这枚数是工单给的凭据（同基点干净树 be-r491），本单无权 `restore` 在册件去复现改盘面。
- **全量门没跑**：同机多枚 Agent 在跑＝事故 #81；本回执里所有数字都是定向件读数，不代表全量门。
- **作用域化依赖一条纪律，不是依赖证明**：若同一棵施工树里同时有两枚 Agent 写字（写集冲突），指纹为真时活体钉会把别人的手记到本单头上。
  这枚钉治不了纪律，只能把误伤面从「整棵树的历史脏项」收窄到「本单正在施工的那一段」。
- **历史层依赖总控的提交号格式**：subject 开头那枚 `RNNN`（两式：`R453 并树…`／`并树 R453 …`）。格式一漂，
  这枚钉是红而不是静默通过（`名册为空 ⇒ 喊「静默空响」那一支），届时改 `LEADING_TICKET`，不许关掉它。
- **没动的两格**：`ENVIRONMENT_NOISE` 那本名册、`RETIRED_ALLOWED_PREFIXES` 旧值，与本次返工无关，原样留着。

## 返工（09-29 17:5x，总控自修；先例＝#77 由总控动手修成 `72bdf96`）：第三枚「落地即自毁」的钉

- **病与凭据**：`tests/test_r496_forbidden_pin_scope.py::test_the_real_tree_reads_its_own_construction_fingerprint`
  无条件 `assert fingerprint`。本单并树（`ec5dfef`）之后，总控在**干净主树**现跑
`1 failed / 15 passed`，原文「AssertionError: R496 正在改这枚件，施工指纹却读空：那下面三枚
  「本单在施工」的断言全是空响」＋ `assert []`（件内 :238）。它指控的是「总控把本单提交了」这件合法的事，
  与本单要治的那两枚冒名判红同一种病（同族：#77／R491 探针那一格）。
- **返工时又量出一格（同族病）**：原那两条**无闸门裸读数**断言（禁域零脏／在册零改）挂在真树上同样会咬假红——
`docs/testing` 本身就在 `FORBIDDEN_PATHS` 里，而总控每一次并树都要往那儿写验收凭据；
`frontend/**` 更直接：R494 并树窗里 `M frontend/src/router/index.js` 会让它当场翻红。
  盘面脏是别人的手，不是本单的罪证——这正是 R496 立单的论题，本枚常驻钉不能自己违背它。
- **改形**：三条永真 ＋ 两形各一刀。
  永真＝实质层三面（评测集／回归门／override，与盘面无关）＋ 历史层（名册非空、挂号提交零越界）
  ＋ 闸门形状（两枚活体钉在这棵树读的指纹必须等于 `construction_fingerprint`，不许各拿一把尺）。
  形甲（指纹非空）＝归因只认在册交付件或写域前缀下的新未跟踪钉，且闸门读数必须等于裸读数，
  裸禁域／裸在册必须零脏（＝原那两条断言，只是移进态分支，一条没删）。
  形乙（指纹读空）＝空读必须「合法」：交付件已在 HEAD ＋ 盘上齐件 ＋ **同一把尺在影子根里对着一只真手
  必须当场读得出指纹**（正控内置在本枚钉里，尺一瞎就红，不许拿「已并树」当遮羞布）。
  原「被治件必在指纹里」那一句不是被删而是**换了层**：那是历史事实，由
`test_r453_cloud_eval_override.py::test_counter_evidence_the_landing_roster_is_two_way_and_not_vacuous`
  那枚「名册落点并集 ⊇ DELIVERED_FILES」的常驻钉守着。
- **强度只升（AST 现取，HEAD blob 对磁盘内容）**：`def test_` 8→8（LOST=[]，一枚在册 test 没删），
  test 函数体内 `assert` 34→42，降级命中 `pytest.skip`／`warnings.warn`／`@pytest.mark.skip`／`xfail` 全 0。
- **现跑读数（总控亲跑，主树解释器＋cwd＝主树）**：分支＝形乙，`fingerprint=[]`，`forbidden_dirt_reading=([], [])`，`registered_dirt_reading=([], [])`，
`deliverables_tracked_in_head=True`，`missing_on_disk=[]`；影子端正控
`construction_fingerprint=['M deploy/compose.cloud-eval.yaml']` 且 `tracked_in_head(control)=True`。
- **机械事实（供后续班用）**：本仓 `core.autocrlf=true` 且无 `.gitattributes` ⇒ **库内 blob 是 LF、盘面是 CRLF**
  （现取 `git show HEAD:tests/test_r496_forbidden_pin_scope.py` = crlf 0／lf 251）。
  所以「源树磁盘字节 ↔ 主树磁盘字节逐枚等值」是有效对照，而「HEAD blob ↔ 磁盘字节」对文本件永远差一层 EOL，
  只可用于 AST／计数类对照，不许当成等值判据。
