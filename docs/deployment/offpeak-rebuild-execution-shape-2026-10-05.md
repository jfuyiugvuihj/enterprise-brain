# 低峰自动重建的执行腿该长成什么形状（R652 · 方案单 · 2026-10-05）

单号 **R652**（计划书 R50 欠账格 G-R50-1 的方案半张）。性质：**纯纸面**——一行代码都没写、
`app/**`／`tests/**`／`frontend/**` 一字未动、没起服务、没动容器与镜像、没打模型、没跑全量门。
本纸唯一的交付物就是这一张纸：`docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md`。

引用口径：全部写 `文件::符号`。按派工词与本仓 R638 那把尺的规矩，纸上**零枚** `某.py:数字`
手抄坐标（可复跑读数见 §0 第 4 条）。

---

## 0. 现读凭据（开工与收工各取一次）

| # | 命令（在工作树根跑） | 读数（1–3 开工取，4–7 收工取） |
| --- | --- | --- |
| 1 | `git rev-parse HEAD` | `d7f1376858ade507294321ad785e7645b03c9a5d`（＝派工词写的基点） |
| 2 | `git status --porcelain \| wc -l` 等价值 | `0` 枚（porcelain=0） |
| 3 | `git ls-files --others --exclude-standard` | 收工现读＝**本纸一枚** |
| 4 | `python scripts/r638_doc_pointer_ruler.py --check-baseline docs/testing/r638-pointer-baseline.json` | 本纸新落、枚数 `0`（棘轮不红，只逐枚点名新落的 .md） |
| 5 | `python scripts/check_vector_wording.py` | EXIT=0，读数「39 枚文档全部通过」（本纸在 `docs/deployment/`，**不在**那把尺的豁免前缀里，所以它是被扫的） |
| 6 | `python -m pytest tests/test_r22_rebuild_cli.py tests/test_r425_offpeak_index_rebuild.py` | **69 passed／EXIT=0**（本席亲跑；执行层自报，非总控亲跑） |
| 7 | 同上两件各自 `--collect-only -q` | 收集读数 `22` 与 `47`；用例函数 `22` 与 `27`（差值＝参数化展开） |

⚠️ 第 3 条的口径：裸 `git ls-files --others`（不带 `--exclude-standard`）会把忽略项一起吐出来——
本树现读 49,874 枚，全部是 `.venv`（指向主树的 Junction）与 `__pycache__`。
判"交付只有这一张纸"只认带 `--exclude-standard` 的那一枚读数，`git status --porcelain` 同样只交回本纸。

三处"今天真相"与派工词给的一致，逐条自验过：机器账判 R50 = PARTIAL（`scripts/audit_plan_ticket_ledger.py::LEDGER_EXTRA`
里那行 `T("R50", ...)`，欠账格是 `S21(50, "②")`）；排程已在树（`app/scheduler/jobs.py::register_jobs`）；
到点只报不动手（`app/scheduler/jobs.py::offpeak_rebuild_window` 交回 `status=refused`）。

---

## 1. 判据① 要求的三枚事实，逐枚现读

### 1.1 R22 判据 3 那枚钉的原文形状：**两遍扫描各查什么**

钉在 `tests/test_r22_rebuild_cli.py`。它不是一枚断言，是一枚检测器加**四枚**直接用它做判据的用例（§3 表把这 4 枚逐枚点名）：

- **第一遍（文本）**：`tests/test_r22_rebuild_cli.py::_IMPORT_PATTERNS` 里七枚字面串——
  `import rebuild_index`、`from scripts.rebuild_index`、`from scripts import rebuild_index`、
  `importlib.import_module("scripts.rebuild_index"`、`rebuild_index.main(`、
  `rebuild_index.run_rebuild(`、`run_rebuild(`。这一遍是 R22 的原样集合，逐字保留。
- **第二遍（AST，R242 加的）**：`tests/test_r22_rebuild_cli.py::automatic_path_hits` 对每枚文件
  `ast.parse`；解析不了 ⇒ 记命中（fail-closed，见
  `tests/test_r22_rebuild_cli.py::test_counter_evidence_a_file_that_will_not_parse_cannot_be_cleared`）；
  然后逐节点走，凡是 `ast.Constant` 且是字符串、内容含 `rebuild_index`、且**不在**
  `tests/test_r22_rebuild_cli.py::_docstring_nodes` 交回的集合（模块/类/函数的第一枚裸串＝文档）里 ⇒ 记命中。
  这一遍存在的理由被钉自己写在注释里：R235 实测 `subprocess.run([sys.executable, "scripts/rebuild_index.py"])`
  这种 argv 列表七枚字面串一枚都不命中，钉绿着，而 docstring 吹的是它拦得住——
  靶子就是 `tests/test_r22_rebuild_cli.py::test_counter_evidence_an_argv_list_subprocess_is_not_a_clear_path`。
- **半径（甲案全立在这一格上）**：两遍都只走 `Path(root) / "app"` 下的 `*.py`。
  `scripts/` 与 `deploy/` **不在扫描半径里**。所以"腿落在 `app/` 之外"这件事，
  这枚钉既不会拦、也不会证明——它只对 `app/**` 说话。
- **已知局限（钉自己声明的，不许替它遮丑）**：把文件名拆成碎片（`"rebuild_" + "index.py"`）
  两遍都不咬。⇒ 任何"用这枚钉证明外面那条腿不存在"的写法都是假话，腿要靠 §4 尺 C 那三条读数定罪。
- **相邻的交叉钉（不是 R22 家，但同一条边）**：`tests/test_r425_offpeak_index_rebuild.py` 里
  `test_the_r22_pin_still_clears_the_whole_tree` 复用同一枚检测器扫真树；
  `test_the_scheduler_files_hold_no_spawn_or_socket_shape_at_all` 另钉 `app/scheduler/` 的 import 根集合
  （`ALLOWED_IMPORT_ROOTS`，不含 `subprocess`/`socket`）与调用名黑名单（`FORBIDDEN_CALLS`：
  `system`/`popen`/`Popen`/`run`/`check_output`/`exec`/`execv`/`execve`/`startfile`/`connect`/`send`）；
  `test_the_refusal_does_not_smuggle_the_pinned_command_name` 连"把那枚命令名写进日志字符串"都算命中。

### 1.2 `scripts/rebuild_index.py` 的真实 CLI 形状

参数面（`scripts/rebuild_index.py::_parser`，`prog="rebuild_index.py"`）：
`--status`（只看不动）、`--apply`、`--confirm-scope`、`--document`（可重复）、`--only-stale`、
`--metadata-path`、`--documents-dir`、`--incremental`、`--max-documents`、`--time-budget-seconds`、
`--census-page-size`、`--census-list-limit`、`--census-report`、`--chroma-dir`、`--chroma-collection`、`--json`。
其中 `--max-documents` 与 `--time-budget-seconds` 的帮助文案明写 **requires --apply**。

判定顺序（`scripts/rebuild_index.py::main`，全部发生在打开 registry / catalog / store 之前）：

1. 给了 `--apply` 才走三关：`scripts/rebuild_index.py::scope_from_text` 解析确认串（必须
   `"<model>/<dimension>"` 形状，否则 `RebuildRefused`）→ 与 `app/rag/indexing.py::configured_embedding_scope`
   的 `key` **逐字相等**（不等 ⇒ `EXIT_USAGE=2`，stderr 含 `is not the configured profile`）→
   `scripts/rebuild_index.py::invoked_by_human`（不成立 ⇒ `EXIT_USAGE=2`，stderr 含
   `only runs when scripts/rebuild_index.py is invoked as a command`）。三关全过才把 `manual=True`。
2. `--confirm-scope` 没配 `--apply` ⇒ 用法错；负数预算／负数 `--max-documents` 先判（"broken invocation
   无论带不带 --apply 都必须拒"），再判"只有 --apply 才有意义"。
3. 退出码面：`EXIT_OK=0` / `EXIT_USAGE=2` / `EXIT_EMBEDDER_UNUSABLE=3` / `EXIT_REBUILD_FAILED=4`；
   `report["aborted"]` 非空 ⇒ `4`，`report["failed"]` 非零 ⇒ `4`。

**人的闸到底是什么形状**（甲、乙两案都绕不开这一枚）：
`scripts/rebuild_index.py::invoked_by_human` 的实现是 `Path(argv0).name == Path(__file__).name`。
它挡住的是"import 之后伸手够 `run_rebuild`"（pytest runner、`server.py` 这类入口、改名/软链副本一律 False，
见 `tests/test_r22_rebuild_cli.py::test_a_server_entry_point_is_not_a_human_invocation`）；
它**挡不住**一条把该文件当程序运行的宿主计划任务——那条腿 argv[0] 就是它自己，天然 True。
所以"人决定的"这件事在这台机器上从来不是由 `invoked_by_human` 承担的，而是由
① 有没有人把那条腿装进日历、② `--confirm-scope` 那枚串是不是当前口径 承担的。
另一处必须写实：`app/rag/indexing.py::_configured_dimension` 在 `EMBEDDING_DIMENSION` 未声明时
**回落** `app/rag/indexing.py::DEFAULT_EMBEDDING_DIMENSION`（不 fail-closed），因此无人值守的腿
唯一拦得住"按猜的宽度重写库"的就是上面那枚逐字相等。

**remaining 归零语义**（`scripts/rebuild_index.py::run_rebuild`）：

- 预算只在**文档之间**检查：`time_budget_seconds is not None and (clock() - started) >= float(time_budget_seconds)`
  ⇒ 写 `report["stopped_at"] = "time_budget_seconds=<N>"` 后 `break`；`--max-documents` 同一形状写 `stop_after=<N>`。
  一枚文档是"打断也不能留半截"的最小单位（`scripts/rebuild_index.py::rebuild_document` 内部不吃预算）。
- 增量判定为"与源一致"的文档走 `PLAN_REASON_MATCHES` 分支，计入 `unchanged` 而**不吃预算也不计 attempted**
  （注释原话：便宜的答案才是常见答案，不许它花预算）。
- 收口读数：`report["remaining"] = max(0, len(targets) - report["attempted"] - report["unchanged"])`，
  且**失败的文档算 remaining**（"因为它本来就是 remaining"）。
- 非 `source_missing` 的失败会写 `report["aborted"]` 并当场停，不再把同一刀落到后面的文档上。
- ⇒ "这一轮真的跑完了"的唯一读数是 `remaining == 0` **且** `aborted == ""` **且** `failed == 0`；
  这条语义由 `tests/test_r50_resumable_rebuild.py::test_the_first_run_stops_at_two_documents_and_reports_the_four_left`、
  `test_the_second_run_only_does_the_remaining_four`、`test_a_third_run_finds_nothing_to_do_and_knocks_on_no_door`、
  `test_a_time_budget_stops_between_documents_and_never_inside_one` 四枚钉着（该件现读 20 枚用例）。

### 1.3 `app/scheduler/index_rebuild_config.py` 里 `schedulable` 的判定链

链上每一环只有一个读者（这是 R425 判据③ 的形状，不是风格）：

1. `app/scheduler/index_rebuild_config.py::resolve_index_rebuild_window` 一次性读三枚旋钮
   （env 名 `SCHEDULE_ENV` / `TIME_BUDGET_ENV` / `AT_ENV`，出厂读数 `DEFAULT_SCHEDULE_ENABLED=False` /
   `DEFAULT_TIME_BUDGET_SECONDS=1800` / `DEFAULT_AT="03:30"`）。
2. `_read_switch` 只认 1/true/yes/on 与 0/false/no/off（与 `app/main.py` 读 `SCHEDULER_ENABLED` 同一套拼法），
   别的拼法记进 `notes` 并**留在 off**；`_read_budget` 非数字/零/负 ⇒ 回落出厂默认并记 `notes`；
   `_read_moment` 不是 `HH:MM` 或越界 ⇒ 回落 `DEFAULT_AT` 并记 `notes`。
3. 判定在 `app/scheduler/index_rebuild_config.py::IndexRebuildWindow.schedulable`：
   `bool(self.enabled) and self.budget_seconds > 0`。为什么必须两枚都真——"无预算＝整库一口气重嵌"，
   正是这枚旋钮存在的理由，所以 `notes` 之外还有一道 `schedulable` 复检；
   解释"为什么没上日历"的话术在 `app/scheduler/index_rebuild_config.py::IndexRebuildWindow.unschedulable_reason`。
4. 消费方两处，且**开关在 `add_job` 那一刻定**：`app/scheduler/jobs.py::register_jobs` 里
   `if window.schedulable:` 才 `add_job(..., id=REBUILD_JOB_ID, max_instances=1, coalesce=True)`，
   否则只 log 一句不排；`app/scheduler/jobs.py::offpeak_rebuild_window` 到点**再读一遍**（纵深，不是那道闸），
   交回 `status=skipped`（那时才判开关）或 `status=refused`＋`budget_seconds`＋`window`。
5. 把闸挪进回调、`add_job` 无条件＝在册钉当场红：
   `tests/test_r425_offpeak_index_rebuild.py::test_the_shipped_default_registers_two_jobs_only`（TOOTH 1）与
   同件 `test_an_unset_or_unreadable_switch_still_registers_nothing`（TOOTH 2 形状）。
   名册那两枚的"逐字全等"还被邻居件钉着：`tests/test_r457_audit_retention_execution_leg.py`
   里那句"第四枚 job 要走 host 层的 `register_audit_sweep`，要搬进名册就先改在册钉"。

> 链条的终点就是本单的病：`schedulable` 为真只能让**一枚会报不会动手的 job** 上日历；
> 动手那半句被 §1.1 的半径关在 `app/` 之外。
---

## 2. 甲案：执行腿落在 `app/` 之外——那枚钉**不动**能不能兑现

先给结论，再给凭据：**能兑现"钉不动"，但兑现不了"人决定"**，除非把这条腿的出厂状态钉成
"不存在"。甲案今天有三种落点，逐枚对：

**甲-1 部署侧独立 rebuilder 服务（compose 里多一枚容器）**
- 钉不动：成立。半径是 `app/**`，新服务跑的是 `scripts/rebuild_index.py`，`automatic_path_hits` 交回 `[]`。
- 代价（在册件点名）：`tests/test_deployment_topology.py` 那族会动——名册那枚是子集断言
  （`{"postgres","redis","migrate","backend","worker","scheduler","frontend"} <= set(services)`）所以不咬新增，
  但同一件里还钉着 `services["scheduler"]["command"] == ["python","deploy/scheduler.py"]`、
  overlay 不得引入孤儿服务（`unknown = set(overlay["services"]) - set(base["services"])` 必须为空）、
  `must stay on the internal network`（各服务不得有 `ports`）、以及 `_env_file_entries(overlay) == {}`。
  ⇒ 一枚会改库的容器要么逼着改这几枚断言，要么必须以"非常驻、不联网、无端口"的形状挤进去。
- 更硬的一条反对：出厂即开＝**这台机器的 GPU 与知识库被产品订走了**。跟进单 §18 订正段的原话是
  "真正的全量重算**必须人工触发**（H 闸门级动作），私有化机器上没有『偷偷重建』这条路，这正是设计意图"；
  `.env.example` 那一段英文口径同样是 "Rewriting a knowledge base while nobody is watching is not
  something this product is allowed to do to a customer's machine"。

**甲-2 宿主计划任务（Windows 任务计划 / systemd timer）**
- 钉不动：成立，且**不需要动 compose**——腿在宿主上，`app/**` 一个字节都不长。
- `invoked_by_human` 天然为 True（argv[0] 就是那枚脚本文件名），所以"人跑的"这一层由**装任务的那双手**承担，
  不由代码承担。这一点必须写在纸上而不是含糊过去：甲-2 把 R22 的保护对象从"代码里没有自动路径"
  换成"这台机器的日历上有没有那一格"，而后者今天**没有任何在册牙在量**——`tests/test_r22_rebuild_cli.py`
  不看宿主日历，`tests/test_r425_offpeak_index_rebuild.py` 只看 `app/scheduler/`。
- 唯一还留在机器里的闸是 §1.2 那枚逐字相等：腿上烘焙的 `--confirm-scope "<model>/<dim>"` 一旦与
  当时 `configured_embedding_scope` 不等，那条腿自己以 `EXIT_USAGE=2` 拒跑。这是甲案最值钱的可失败读数，
  也是"改口径当晚不许无人值守重写库"目前**唯一**的机械证明。
- 谁负责：一台机器一个企业、物理隔离 ⇒ 宿主计划任务的所有权在**客户方 IT**，不在产品。我方能交的是
  一段可抄写的配方（命令串＋预算数字＋口径串怎么取）和一条自证命令，不能交一个装好的 timer。

**甲-3 `setup.sh` 装的 timer**
- 今天**没有这条路**：`git ls-files` 现读，仓内没有 `setup.sh`，安装面是 `deploy/docker-compose.server.yml`
  ＋ `deploy/README.server.md` ＋ `deploy/start_workers.sh` / `deploy/start_workers.ps1`
  ＋ `scripts/install_pgvector_windows.ps1`。⇒ AGENTS.md 那句"部署: setup.sh + Docker"是过期账，
  甲-3 若被选中，落点只能是 `deploy/README.server.md` 里新增一节（那是文书写域，属总控派单）。
- 同一件还提醒一件事：`deploy/README.server.md` 是 R467 判据③ 认定的"客户装机时手里那一份"，
  往里加配方在**册面上**是被鼓励的（`tests/test_r467_delivery_gate_classification_item.py` 钉的就是它必须是可执行的一条）。

**甲案要不要和 R22 钉打架**：不打架（半径不重叠，见 §4 尺 C 第 ① 条）。但"不打架"要分两半说——
如果那条腿被写成 `app/**` 里的一枚 job／一枚 subprocess，`automatic_path_hits` 立刻红，**不需要**改钉就能定罪；
如果它被写进 `scripts/` 且按目录开 Chroma 那类工厂，撞的是
`tests/test_r134_chroma_writeback.py::DIRECTORY_FUNNEL_LEDGER` 那枚"收口清单枚数"钉（现读 8 处，多一处即红）；
如果它被写进 `deploy/`，那两枚钉都不咬——**那是绕过，不是达标**，本纸不许把它写成"验证过了"。

---

## 3. 乙案：改 R22 判据 3——代价逐枚上账

**为什么当初钉（原文三处，一字不改地引）**

- 跟进单 §21 立单表 R22 行③：`给出全量重建 CLI，**只许人工触发，禁止自动执行**`。
- 跟进单 §18 订正段："真正的全量重算必须人工触发（H 闸门级动作），私有化机器上没有『偷偷重建』这条路，
  这正是设计意图"。
- `.env.example` 窗口那一段：`no scheduler job may import, call or spawn the rebuild`（这句同时被
  `tests/test_r425_offpeak_index_rebuild.py::test_the_window_block_says_what_the_tree_actually_does`
  当 prose 钉逐字读，和 `R22 判据 3` 这枚锚一起）。

**拆了以后哪些在册牙要改判（可点名清单，不写"影响可控"）**

| 在册件 | 用例函数／收集读数（本席现跑） | 乙案下要改判的具体牙齿 |
| --- | --- | --- |
| `tests/test_r22_rebuild_cli.py` | 22 枚函数＝22 枚收集 | `test_nothing_in_the_application_can_reach_the_rebuild_command`（主钉）＋三枚 `test_counter_evidence_*`（argv 列表 / docstring 豁免 / unparsable）——它们的靶子是"半径内不许有自动路径"，判据一拆，这枚主钉加三枚反证＝**4 枚**量的东西一起消失；`test_importing_the_command_does_not_run_anything`、`test_a_server_entry_point_is_not_a_human_invocation`、`test_apply_without_a_human_latch_refuses_before_touching_anything` 三枚量的是 `invoked_by_human`／`manual` 闸，**不随判据 3 死**，但若同时把 `manual` 也放宽就一起作废 |
| `tests/test_r425_offpeak_index_rebuild.py` | 27 枚函数＝47 枚收集 | `test_the_r22_pin_still_clears_the_whole_tree`、`test_the_scheduler_files_hold_no_spawn_or_socket_shape_at_all`、`test_registering_a_job_runs_no_command`、`test_firing_the_window_starts_no_process_and_writes_nothing`、`test_the_refusal_names_the_budget_and_the_flags_an_operator_needs`（回调交回的 `reason` 那句"应用侧不许触发索引重建"是它的断言）、`test_the_refusal_does_not_smuggle_the_pinned_command_name`、`test_the_window_block_says_what_the_tree_actually_does` 共 7 枚直接改判；另外 `app/scheduler/jobs.py::offpeak_rebuild_window` 的 docstring 与模块 docstring 里那两句"到点只报不动手"要重写，它们是 §3 上面那张表的语义来源 |
| `tests/test_r457_audit_retention_execution_leg.py` | — | 名册"逐字全等"那一族（`ids(fake) == NAMED_SURFACE_IDS`）。第三枚会动手的 job 进名册后，R457 那句"第四枚 job 要走 host 层 `register_audit_sweep`"的依赖前提变了，`test_no_host_can_register_jobs_without_the_sweep` 的 AST 腿要重量 |
| `scripts/audit_plan_ticket_ledger.py` | — | 判据原文一律**运行时按锚点逐字切段**（脚本头写明"锚点不唯一就当场停"，出处错走 `exit=2`）。§21 R22 行那句原文被改写 ⇒ R22 名下 `T("R22", LANDED, ...)` 与 R50 的 `S21(50, "②")` 两处引用要重量，本纸不动它，只点名 |
| `tests/test_r276_vector_wording_pin.py` / `tests/test_r638_pointer_ratchet.py` | — | 不随乙案改判（它们量的是口径措辞与纸面坐标，与触发方式无关） |

**失败面**：拆钉之后最贵的失败从"某个人误跑了一条命令"变成"**每一次部署都可能自动改写客户的知识库**"。
那两枚保命牙（`scripts/rebuild_index.py::probe_embedder` 先于任何删除、
`scripts/rebuild_index.py::verify_embedding_set` 逐文档自证宽度与非零）仍然在位，但它们防的是
"embedder 坏了会把库删空"，**不防**"没人要求"。这两件事以前由 `manual` 闸＋半径共同兜住，拆一件就少一件。

**回滚**：账面回滚是一行（判据原文复原），代码回滚不是——一旦名册里长出第三枚会动手的 job，
`add_job` 的形状、`status=refused` 的语义、`.env.example` 那四句 prose 钉、以及"缺省不排"这条出厂状态
必须同时倒回，且倒回之前 V1 已经宣称过"低峰自动重建达标"。⇒ 乙案是一条**单向门**，
这正是它被写成"业主的决定"而不是执行层细节的原因。本席按规矩不先斩后奏，只交代价。
---

## 4. 推荐案：**丙**（V1 内裁定结案；甲-2 降级为交付阶段配方，不进产品、不进出厂状态）

推荐只有一枚：**丙**。甲-1／甲-3／乙 三枚都不推荐（甲-1 与 compose 那族拓扑钉对冲且把 GPU 订走；
甲-3 的落点今天不存在；乙 是单向门且需业主裁）。丙 的"交付阶段可选配方"用的是甲-2 的形状——
它是同一枚推荐的实施面，不是第二枚推荐。

**为什么是丙（三句，全部可核）**

1. R50 的两条判据今天**都在树上且有牙**：① 增量在 `app/rag/indexing.py::plan_index_refresh`
   与 `tests/test_r50_incremental_index.py`（15 枚，其中
   `test_one_document_incremental_step_stays_under_two_seconds_offline` 自己声明"不含模型推理那一半"）；
   ② 可中断续跑在 `scripts/rebuild_index.py::run_rebuild` 的 `remaining` 语义与
   `tests/test_r50_resumable_rebuild.py`（20 枚）。⇒ 欠的那半句严格来说是"**自动触发**"，
   不是"续跑"，也不是"预算"。账面的理由句（`scripts/audit_plan_ticket_ledger.py` 里 R50 那行）
   今天写的正是这一格。
2. "自动触发"这件事的正当性不由产品单方决定：一台机器一个企业、数据不出机器 ⇒
   半夜重嵌属于**业主/客户那一侧的授权行为**（见下面判据④ 的回答）。把它做成 V1 产物，
   等于替客户做那个他没说过的决定。
3. 与 B 行／E 行同判的先例是现成的形状，不是新造的口径：计划书"门的归属裁定"那一族
   （`docs/handoff/2026-09-17-perf-architecture-plan.md` 里" **B 行与 E 行整行移出 V1 门槛**"那段）
   用的就是"这格验的不是产品功能／前提不在 V1 技术栈里 ⇒ 移出门槛，原文保留不删"。
   R50 的自动触发半句同构：前提（客户授权＋宿主日历）不在 V1 交付面里。

**裁定句草案（给总控落账用；本席不碰计划书/跟进单/台账那三本账）**

> R50 判据②「全量重建可中断续跑」**达**（凭据＝`scripts/rebuild_index.py::run_rebuild` 的
> `remaining`／`stopped_at` 语义 ＋ `tests/test_r50_resumable_rebuild.py` 20 枚 ＋
> `tests/test_r50_incremental_index.py` 15 枚）。计划书单号里「**低峰**全量重建」的**自动触发**半句，
> 按 2026-10-05 裁定**移出 V1 门槛**，登记为**交付阶段动作**：由客户方在其宿主日历上自行安装
> `scripts/rebuild_index.py --apply --incremental --confirm-scope "<model>/<dim>" --time-budget-seconds <N>`
> 这一条腿（配方落 `deploy/README.server.md`，我方交配方＋自证命令，**不交装好的 timer**）；
> 产品侧**不新增服务、不新增宿主进程、不改 R22 判据 3**——`app/scheduler/jobs.py::offpeak_rebuild_window`
> 保持到点 `status=refused`，那是设计而非欠账。连带效果：G-R50-1 这格从"欠代码"改记为"欠一条客户授权＋
> 配方"，台账里 R50 那行的理由句随本裁定同步改口（`scripts/audit_plan_ticket_ledger.py::LEDGER_EXTRA`，总控执笔）。

草案里三枚"不许"是有理由的，不是谨慎：

- 不许写成 `NOTBUILT` 档。台账 C13 那把尺要求"计划书把该行划了删除线"**且**"跟进单 §21 里读得到
  『不建，沿用』那句裁定"**两句同时在场**（缺一即不可判定，当场红）。R50 整行不建是假话——两枚产物提交
  （施工／并树）都在主干。
- 不许写成 `CLOSED` 档。`CLOSED` 要求句形为 `R50 结案（R<量具> …）` 且那枚量具的货在仓内、
  同笔带一枚 `docs/perf/` 或 `docs/testing/` 取证纸（`scripts/audit_plan_ticket_ledger.py` 头部口径）。
  本纸在 `docs/deployment/`，**不认领** `G-R50-1`，也不能替结案笔存在。
- 不许把 `INDEX_REBUILD_SCHEDULE_ENABLED` 翻成出厂开。名册"缺省恰两枚"那族钉
  （§1.3 第 5 条点名的 TOOTH 1／TOOTH 2）会当场红，而那枚红代表的是"产品替客户做了决定"。

**§5.2 那行怎么改口（计划书表格行，总控执笔）**

今天那一行是 `| R50 | 增量索引 + 低峰全量重建 | L3 | 1.0 |`。草案改法：句子本体不删（§5.2 那张表
没有结案列，删行会让下一班重新数出"还剩一枚"），改成行内加注的形状——
`| R50 | 增量索引 + 低峰全量重建（🔴 自动触发半句 2026-10-05 移出 V1 门槛，见 §5.2 之后"门的归属裁定"新增条；V1 内判据①② 达，凭据见跟进单 §21 R50 行）| L3 | 1.0 |`，
并在"门的归属裁定"那一段追加一条 bullet，与 B／E 两条并列。

### 4.1 这一案怎么被量出来：三把可失败的尺

**尺 A｜V1 内"不许假装"的自证（本纸推荐案的承重尺）**

- 读数：`python -m pytest tests/test_r22_rebuild_cli.py tests/test_r425_offpeak_index_rebuild.py`
  ⇒ 必须 EXIT=0。分母两笔都要现读，只报一笔就是假数：用例函数 **22 ＋ 27 ＝ 49 枚**（`rg -c '^def test'` 于两枚文件），`--collect-only -q` 展开成收集读数 **22 ＋ 47 ＝ 69 枚**（差值是参数化那族）。本席收工亲跑＝**69 passed／EXIT=0**（执行层自报，非总控亲跑）。
- 判红条件（任一即红，且红就是本纸的失败）：收集读数少于一枚（分母 69）、或任何一枚转红；
  特别是 `tests/test_r425_offpeak_index_rebuild.py::test_the_shipped_default_registers_two_jobs_only`
  与 `test_the_r22_pin_still_clears_the_whole_tree` 同时红 ⇒ 说明有人既动了名册又动了钉。
- 与 R22 钉打架吗：**不打**。这把尺就是拿那枚钉当量具的。

**尺 B｜人工腿的合格线（"跑完"的唯一定义，也是 V1 内 R50 ② 的日常读数）**

- 读数（同一条命令跑两枚窗口，`--json` 取 stdout）：
  `python scripts/rebuild_index.py --apply --incremental --confirm-scope "<model>/<dim>" --time-budget-seconds 1800 --json`
  - 窗口 1（没收口）：`stopped_at` 必须以 `time_budget_seconds=` 开头，且 `remaining > 0`，EXIT=0；
  - 窗口 2（收口）：`remaining == 0` 且 `aborted == ""` 且 `failed == 0`，EXIT=0。
- 判红条件（可失败，全是数字）：EXIT=2（口径串与 `configured_embedding_scope` 不等／预算为负／
  非人调用）；EXIT=3（`scripts/rebuild_index.py::probe_embedder` 或逐文档那枚 `scripts/rebuild_index.py::verify_embedding_set` 交回非空理由 ⇒ `run_rebuild` 抛 `scripts/rebuild_index.py::EmbedderUnavailable`，`main` 捕获后落 `EXIT_EMBEDDER_UNUSABLE=3`）；
  EXIT=4（`aborted` 非空或 `failed > 0`）；`remaining` 在连续 K 枚窗口上不小于上一枚
  （K 由总控定，建议 3）⇒ 腿坏了或 catalog 与 registry 打架，不许写成"重建在跑"。
- 与 R22 钉打架吗：**不打**。它要求的是人敲命令，`invoked_by_human` 正是为它保留的形状；
  反过来，若这把尺改建成"由 app 里的 job 自己去读这些数字"，`automatic_path_hits` 会先红。

**尺 C｜交付阶段那条腿（甲-2）如果哪天真被装起来，必须同时满足的三条**

- C-①：`automatic_path_hits(REPO_ROOT)` 交回 `[]`（腿没进 `app/**`）。复跑法＝
  `python -m pytest tests/test_r425_offpeak_index_rebuild.py -k the_r22_pin` 或直接调用那枚检测器。
  判红＝返回非空并指名那一枚 `app/**` 文件。
- C-②：出厂服务名册不变。读数＝解析 `docker-compose.yml` 的 `services` 键集合，与开工快照
    **逐枚相等**：`docker-compose.yml` 的 `services` 键今天交回 8 枚
    （`backend`／`frontend`／`migrate`／`ollama`／`postgres`／`redis`／`scheduler`／`worker`），
    `deploy/docker-compose.server.yml` 交回 7 枚（无 `migrate`）⇒ 多一枚即红。
    🔴 注：在册那枚断言只是子集判断（`<= set(services)`），它**不咬**新增，所以这把尺是本纸自定的，
    不许写成「已经有牙替我看住了」（那正是 §2 甲-1 那条反对意见的形状）。
  这条拦的是"偷偷加一个会改库的容器"，也正是甲-1 今天不能入选的原因。
- C-③：宿主腿上烘焙的确认串必须逐字等于当时的 `configured_embedding_scope`。
  读数＝那条腿自己下一晚的退出码：不等 ⇒ EXIT=2 且 stderr 含 `is not the configured profile`；
  这枚"拒跑"是**期望行为**，它证明改口径当晚不会无人值守重写库。等 ⇒ 允许写，
  且窗口收口读数按尺 B 那两枚数字交回。
- 打架判：**三条都不碰 `app/**`，与 R22 钉零冲突**；但 C-① 只证明"腿不在半径里"，
  不证明"腿不存在"——半径外的验证只有 C-②（服务名册）与 C-③（宿主腿自己的退出码）两枚，
  本纸不许把 C-① 单独写成"甲案已验证达标"。

### 4.2 判据④ 那句话的回答

**客户装在自己机器上、数据不出机器，半夜重嵌是否属于"没人要求就改数据"？**

答：**当它是产品出厂行为时，属于；当它是那一台机器的事主自己写进宿主日历的一行命令时，不属于。**
分界不是修辞，是三个可点名的落点：

- 出厂即开（`INDEX_REBUILD_SCHEDULE_ENABLED` 默认翻 on、或 compose 多一枚会动手的容器）＝**属于**。
  这正是跟进单 §18 订正段那句"私有化机器上没有『偷偷重建』这条路，这正是设计意图"要挡的东西，
  也是 `.env.example` 里那句"不是这台机器的主人说的，就别写进日历"的英文原话所对的形状。
- 产品到点只报不动手（今天 `app/scheduler/jobs.py::offpeak_rebuild_window` 交回 `status=refused`）＝**不属于**，
  因为没有任何一个字节的库被改写，且它把该做的那条命令连同预算数字打印给看日历的人。
- 客户方 IT 自己按 `deploy/README.server.md` 的配方装一条宿主腿＝**不属于**，
  决定在那一刻由一个有名有姓的人做出；这台机器上唯一有权半夜重嵌自己知识库的就是他。
  ⚠️ 边界条件要写全：`invoked_by_human` 对这条腿天然为 True（§1.2），
  所以"是客户装的"这件事**只能**由 C-②／C-③ 两枚尺兜住，不能由代码兜住。

---

## 5. 影响面矩阵（逐枚点名；空格＝一字不动）

| 在册件（现读：函数／收集） | 甲（腿在 `app/` 之外） | 乙（改判据 3） | **丙＝推荐** |
| --- | --- | --- | --- |
| `tests/test_r22_rebuild_cli.py`（22 函数＝22 收集） | 0 枚改判（半径只 `app/**`） | **4 枚改判**（主钉＋三枚反证，§3 表点名）；另 3 枚要同时放宽 `manual` 闸才作废 | 0 枚改判 |
| `tests/test_r425_offpeak_index_rebuild.py`（27 函数＝47 收集） | 0 枚（前提：腿不进 `app/scheduler/`）；若进 ⇒ 至少 7 枚 | 7 枚改判（§3 表点名） | 0 枚改判（名册仍两枚、回调仍 `refused`） |
| `tests/test_r457_audit_retention_execution_leg.py` | 0 枚 | 名册全等一族重排（第三枚会动手的 job 进名册即触发） | 0 枚 |
| `tests/test_deployment_topology.py` | 甲-1 ⇒ 改判（`services[...]["command"]`、overlay 孤儿、`ports`、`_env_file_entries` 四枚断言按 §2 逐条）；甲-2／甲-3 ⇒ 0 枚 | 0 枚 | 0 枚 |
| `tests/test_r134_chroma_writeback.py`（`DIRECTORY_FUNNEL_LEDGER` 现读 8 处） | 腿脚本落 `app/` 或 `scripts/` 且按目录开库 ⇒ 枚数钉红；落 `deploy/` ⇒ 不咬（＝绕过，本纸判为不达标） | 同左（与乙无关） | 0 枚 |
| `scripts/audit_plan_ticket_ledger.py`（R50 那行 `T(...)`＋`S21(50,"②")`） | reason 格随"腿存在"改写（总控执笔） | 逐字锚点要重量（§3） | **reason 格与档位随裁定句同步**（§4 草案给了文字；仍由总控落账） |
| `docs/handoff/2026-09-17-perf-architecture-plan.md` §5.2 R50 行＋"门的归属裁定"段 | 需加注（"腿在交付侧"） | 需加注（"判据已改"） | 需加注＝§4 给的那两笔（加注，不删行） |
| `tests/test_r276_vector_wording_pin.py` / `scripts/check_vector_wording.py` | 本纸被扫 ⇒ 必须 EXIT=0（现读 §0 第 5 条） | 同左 | 同左（本纸已按口径写，未把任何存储说成最终态或已退役） |
| `tests/test_r638_pointer_ratchet.py` | 本纸 0 枚 `*.py:数字` ⇒ 棘轮不红，只点名新落 .md | 同左 | 同左 |
| `scripts/run_gate.py` 全量门枚数 | 甲-1 若加服务＋加牙 ⇒ 枚数上账，由并树那班重记 | 改判 12 枚在册用例 ⇒ 枚数与名册同笔重记 | **零变化**（本单一行代码不写、一枚测试不增） |
| `app/**`／`tests/**`／`frontend/**` | 甲按定义要写代码（另派执行单） | 要写代码＋改钉（另派） | **一字不动** |
---

## 6. 本纸没做的事（诚实边界，写给下一班而不是写给自己）

1. **零代码、零测试、零容器**：判据① 那三枚事实是**静态现读**（读源码与其在册牙），不是运行时证明。
   `remaining` 归零那把尺（尺 B）在本单**没有被跑过**——跑它要打 embedder、要动真库，属禁区。
   纸面上它是一把**待复跑的尺**，不是已达标的读数。
2. **未量的东西**：客户尺寸库上一枚 1800 s 窗口能推进多少文档（`attempted`／`remaining` 的真实比值）；
   `--time-budget-seconds` 在 Ollama 冷启（`LOCAL_MODEL_KEEP_ALIVE` 那枚旋钮的口径）下的实际吞吐；
   宿主计划任务在本机的真机行为（本机没装，也不许本单装）。
3. **半径外的盲区要重复一遍**：`tests/test_r22_rebuild_cli.py` 看不见宿主日历，
   `tests/test_r425_offpeak_index_rebuild.py` 只读 `app/scheduler/`。⇒ 甲案"腿不存在"这件事
   今天**没有任何一枚在册牙能证明**，只有尺 C 那三条读数能各证一角；把 C-① 单独写成达标＝假绿。
4. **裁定笔不在本席写域**：§4 的裁定句与 §5.2 加注、台账 `T("R50", ...)` 那行的 reason 同步，
   三处都属总控的账（`docs/handoff/**` 与 `scripts/audit_plan_ticket_ledger.py`）。
   本纸只把**文字与档位卫生**交回：不许写进 `NOTBUILT`、不许冒充 `CLOSED`、不许翻出厂开关。
5. **编号卫生**：本纸通篇没写"事故 #N"。按 AGENTS.md 的规矩，写那类编号之前要先 `rg` 取 max，
   本单不需要它，也就不制造它。

## 7. 复跑清单（任何一班都能自己验本纸的四个关键读数）

| 想验的话 | 命令 | 期望读数 |
| --- | --- | --- |
| 钉只扫 `app/**` | 读 `tests/test_r22_rebuild_cli.py::automatic_path_hits` 里 `(root / "app").rglob` 那一行 | 根是 `app`，不是仓库全集 |
| 到点只报不动手 | `python -m pytest tests/test_r425_offpeak_index_rebuild.py -k "firing_the_window or r22_pin"` | EXIT=0；回调交回 `status=refused` |
| CLI 判定顺序 | 读 `scripts/rebuild_index.py::main` 里 `if args.apply:` 那一段 | 三关：解析串 → 逐字相等 → `invoked_by_human` |
| 两枚件的分母 | `rg -c '^def test' tests/test_r22_rebuild_cli.py tests/test_r425_offpeak_index_rebuild.py`，再逐件 `pytest --collect-only -q` | 函数 `22`／`27`，收集 `22`／`47`（尺 A 用**收集数**当分母） |
| 机器账那一格 | `python scripts/audit_plan_ticket_ledger.py` | R50 = PARTIAL，欠账格 `G-R50-1`（丙案裁定后 reason 改口，档位由总控定） |
| 本纸不脏棘轮／不脏口径 | `python scripts/r638_doc_pointer_ruler.py --check-baseline docs/testing/r638-pointer-baseline.json`；`python scripts/check_vector_wording.py` | 前者不红（新落 .md 只点名）；后者 EXIT=0 |

**收工凭据**（本席交纸那一刻现取，与开工同一口径）：`git rev-parse HEAD` 仍为 `d7f1376`；
`git status --porcelain` 交回**一枚**，内容就是 `?? docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md`；
`git ls-files --others --exclude-standard` 同样只有本纸一枚（裸 `--others` 的 49,874 枚全是忽略项，见 §0 第 3 条）。
主树 `C:\Users\fengx\PycharmProjects\企业智脑` 本席**零写入**（只读过它的文件内容），
其上 `status --porcelain` 那 5 枚是开工前就在的总控账（含 `scripts/audit_plan_ticket_ledger.py` 与 `chroma_db/`），
与本单无关，本席未碰。本席**未** commit。
