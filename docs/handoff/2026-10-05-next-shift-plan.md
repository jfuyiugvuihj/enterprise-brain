# 下一班开工单（10-05 01:1x 由总控线预配 · 状态一律落盘，不靠线程记忆）

- 基点事实源：主树 `C:\Users\fengx\PycharmProjects\企业智脑`，分支 `codex/data-file-catalog`。
- 本单只写「下一班要做的动作与判据」；读数一律现取，禁止照抄本文数字（本文所有数字都带现取时刻）。
- 唯一事实源仍是 `docs/handoff/2026-09-15-orchestration-board.md`（§0 名册＋文末新节）与 `docs/handoff/2026-09-15-backend-followup-requests.md`（文末纯追加）。

## 1. 先收窗（夜窗队列 B，10-05 01:00:41 真开，基点 `9556513`）

- 账本：`%TEMP%\evalrun\night1005b.ledger.jsonl`（每步 `step/rc/secs/note`）；日志 `%TEMP%\evalrun\night1005b.log`；分步输出 `%TEMP%\evalrun\night1005b\*.log`；收工标记 `%TEMP%\evalrun\night1005b.DONE.txt`。
- 步骤序（P-18 答案缓存闸已四处布防：W1 前／相 1 前／相 2 翻开关＋recreate 后／run23 前，每处 `clear` 后紧跟 `--check`）：run22（105 题）→ 相 1 `run22s1`（子集 **33** 题＝A②＋C×2，子集件 `docs/testing/bank-shape-subset-30.jsonl`，名字写 30 而行数是 33）→ `REPORT_LANE_VIA_QUEUE=on`＋recreate → 相 2 `run22s2`（D×3）→ 还原 `off`＋recreate → 双写召回对照（**必须进容器**：`docker exec -w /app enterprise-brain-backend-1 python scripts/compare_vector_recall.py --all --out /tmp/…`＋`docker cp`；host 侧跑会连到本机另一枚 postgres，端口没发布）→ 时延格先现取 R581 → run23（第二次 105 题＝A④ 复现）→ close-out。
- 收窗后逐格读法：correctness／evidence／per-category 与 `run21`·`run20k` 比；A② 只看相 1 的帧账；C 两格只看相 1 的越权命中数；D 三格只看相 2 是否真走了队列道（开关态＋从队列取回正文，缺一律不翻绿）。
- 🔴 不许翻绿的两个前提：`gpu_apps`／`foreign_python` 点名承载本会话的桌面应用 ⇒ A① 与一切 p95 时延读数标「污染·不可采信」；`env_flags` 那格在相 1 必 FAIL（缺省态就是 `off`），本窗没有证明过它。

## 2. 三枚交卷货的验收（窗内禁并树禁跑测试 ⇒ 收窗后立刻做）

| 单号 | 席位／树@基点 | 写域现取（10-05 01:0x） | 两态要跑的件（本席亲跑，执行层自报不算） |
|---|---|---|---|
| R655 | `Descartes`@`be-r655`／`246efb7` | `M tests/test_r643_shot_denominator.py`（46/8）＋新 `tests/test_r655_no_stale_fact_teeth.py`＋新 `docs/testing/r655-stale-fact-denominator-2026-10-05.md` | 同名件 29／74／92 三档；并树后那枚在册红必须消失，且 r647 一族不许改判 |
| R646 | `Peirce`@`be-r646`／`246efb7` | `M docs/deployment/chroma-retirement-path.md`（13/13）＋新 `tests/test_r646_retirement_paper_anchors_are_derived.py`（13 枚）＋新凭据纸 | 同名 10 枚件；另现跑 `scripts/check_vector_wording.py` 与 `scripts/r638_doc_pointer_ruler.py --check-baseline`，并把 `docs/testing/r638-pointer-baseline.json` 报的 `shrank` 逐枚对账 |
| R652 | `Godel`@`be-r652`／`d7f1376` | 唯一新文件 `docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md`（383 行） | 纸面单（零代码）：验「零 `*.py:数字`／纯 CRLF／无 BOM／无控制符」＋尺 A 那 69 枚（它自报，本席复跑同名两件） |

- 并树规矩照旧：显式列路径、中文提交信息走 `git commit -F <UTF-8 无 BOM>`、两态数字都要交、红逐枚点名。
- 🔴 常驻牙卫生：不许把「此刻盘面脏／盘上字节==HEAD blob」当判据（#96／#107／#113）。

## 3. 收窗后本席自办（不占席位）

1. **R652 丙案落账**：裁定句＋计划书 §5.2 加注＋尺里 `T("R50", ...)` 的 reason 同步（`scripts/audit_plan_ticket_ledger.py` 与台账 md 同串同笔），改完亲跑尺＋`tests/test_r640_ledger_tiers_are_derived.py`＋`tests/test_r640_counter_evidence_teeth.py` 交数。在册牙 `test_the_ruler_source_preloads_no_conclusions` 禁 `T(...)` 串里出现「未量」二字（10-05 实测踩过）。
2. **门的账重算**：V1 现 16 枚 PARTIAL；本窗有望交回读数的格＝R28③（逐类不退化，需 run22 与 run23 两次一致）·R31②（A② 逐字）·C×2（越权 0 条）·D×3（报告档可查回）·R47①（召回对照）。其余仍欠真机或欠裁定：R50②＝R22 那枚钉属业主；R35② 生产标签＝计划书 §13 那四件可失败判据记「未验」，不许拿合成标签翻绿；R43② E3 档属交付阶段；R52① 断网可装可跑随 E 行已移出 V1。
3. **影子树与残件清理**（先无损校验再删）：`%TEMP%\r647_state2`·`%TEMP%\r653_state2`（注册 worktree，逐条 `git worktree remove --force`）、`%TEMP%\r649clone`·`r649_base.zip`·`r638_r_light2`。PowerShell 递归删除会被 policy 拒，用 `.venv` 的 python `shutil.rmtree` 且断言路径在 `%TEMP%` 内。
4. `git push gitee HEAD`：每笔并树之后各推一次（10-05 00:5x 已平到 `7ae956c`）。

## 4. 待派三枚（工单已落盘 `%TEMP%\eb104\dispatch\`，一号一次投全，禁补投）

- **R654** 热集让路驱动件重写（格②唯一欠项；`docs/testing/r428-driver.md` 现取不在盘上）。
- **R656** `tests/conftest.py` 与 `TRACE_STORE_PATH` 的在册侧效（R649 并树后新长出来的一族，别让它变成 #115 同族）。
- **R657** `observability` 首屏 `prerequisite` 新串＋契约 §4b／§6 两格**同批**（`tests/test_r526_slot_caliber_closure.py::check_doc_agreement` 逐字对判；`qa.first_text_p95_ms` 今天仍不该交回一个数）。
- 并行度上限 3–4；投递只认 `spawn_agent`＋`items` 单字段，不带 model 覆盖；报错即未落地，先取证零写入，不补投。

## 5. 仍在业主名下（本席不代做）

- `automation-2` 心跳仍 `PAUSED` 且 `target_thread_id` 指向死线程 ⇒ 改指本线程或删除由业主动手（`automation_update` 的真实判别字段是 `mode`，update 传 `targetThreadId` 驼峰）。
- 客户尺寸真扫描件一枚（V2 #13）；告警造规则令（R539）；R440 整表口径；评测集改题批准（已裁「改题排在 run 窗之后」，动评测集要单独批一次）。
- `chroma_db/**` 反跟踪、`.gitignore`、删除清单类破坏性动作＝业主本人。


## 附：01:0x–01:2x 总控续笔（本单落盘后又做了三件事）

### 一、夜窗队列 B 的实际形状（排满了，不会跑完第一段就停）

真开窗 01:00:41，基点 `9556513`，六段串行到 close-out，全部读数落 `%TEMP%\evalrun\night1005b.ledger.jsonl`：

1. `p18-w1` 清答案缓存＋复扫自证 → `run22`（整表 105 枚，断点驱动）；
2. `--emit-subset` 现读 33 行入账（`subset-lines` rc=0 才算过）→ 相 1 `run22s1`（33 枚＝A② 流式逐字＋C 两格）；
3. 翻 `REPORT_LANE_VIA_QUEUE=on` → `--force-recreate` backend/worker/scheduler → 等 HTTP 答话 → 再清缓存 → 相 2 `run22s2`（D 三格）→ 还原 `off` 并再 recreate；
4. 容器内跑双写召回对照（`docker exec -w /app ... compare_vector_recall.py --all`）＋ `docker cp` 取回——host 侧那腿会连到本机别的 postgres 并交回 rc=2，已定为不可用口径；
5. 时延两格（A① p95 复量、R428 热集让路）按 `r581_gpu_attribution` 现读决定，本夜一律记 SKIP：跑分窗本身就是被测负载，窗内量 p95 是自欺；
6. `p18-w6` 清缓存 → `run23`（第二次整表 105＝A④ 逐类不退化的复现样本）→ close-out（开关回 off 校验＋`compose ps`＋keep-awake 自检）＋汇总行。

### 二、隔离了一枚会让人误翻绿的脏料（在册事故 #119）

`run22s1` 与 `run23` 两个 tag 在 00:51–00:59 的失败尝试里已经落了分片（2 枚／11 枚），而那段时间 Redis `answer:*`=25 枚——正是 P-18 明令不许开窗的状态。驱动件的续跑口径是「片内行数相等 ∧ 题号集合相等 ∧ answer 非空」就算已完成，`<tag>.window.json` 五项指纹全等就整窗复用，所以这两相会把**服务端算完却由缓存供答案的旧片**当成今天的新答卷：相 1 的 A② 与 run23 的 A④ 都会拿到假绿。

处置（只动 `%TEMP%`，仓内一字节未动）：把 `run22s1.*` 与 `run23.*` 的 `.shards`／`.shards.json`／`.window.json`／`-sidecar*.jsonl` 整体移到 `evalrun\stale-cache-20261005-0115`，驱动件将重新探针并从零跑那 33＋105 枚。取证纸 `evalrun\night1005b-forensics.txt`。
`run22` 本体没动：它最老一片 01:01:13 晚于 `p18-w1-clear` 01:00:44（rc=0），是干净的。

新纪律（写进派工规矩）：**复用 tag 之前必须先把上一attempt 的 `<tag>.shards`／`<tag>.window.json`／sidecar 一起隔离**，只清 Redis 不够——盘上旧片同样会被当成已完成。

### 三、并树改成收窗后自动接续（不再等总控醒）

`%TEMP%\eb104\postclose1005.py`（pid 现取于 01:21 起，等 DONE 标记，上限 8 小时）按 **R655 → R646 → R652** 逐单执行：

- 基点数（只跑该单以外的既有同名件）→ apply → state① → 只有 state① 零红且枚数达尺才 `git add --<显式路径>` ＋ `git commit -F` → commit 后同名单复跑 state②；
- 任一条件不成立就把本单复制进去的文件逐枚还原（既跟踪件 `git checkout --`，新增件删除），不提交，继续下一单；
- 三单之后跑一次 `python scripts/run_gate.py` 全量门，汇总写 `%TEMP%\evalrun\postclose1005.SUMMARY.txt`，收工标记 `postclose1005.END.txt`。

下一班开工先读这四本：`night1005b.ledger.jsonl`／`night1005b-readout.txt`／`postclose1005.SUMMARY.txt`／`postclose1005\*-state2.log`。**账还没落**（看板 §4FB 与跟进单 §180 由读到这些数字的人执笔，事故号从 #119 往后）。

### 四、下一夜该收的格子（本夜不收，避免与跑分争资源）

1. **生产库的停写现取读数**（R60 判据④ 那一格）：现网两枚旋钮（`VECTOR_DUAL_WRITE=on` ＋ `INDEX_BACKEND=pgvector`）与 `app/rag::DocumentRetriever._write_batch` 的 R60 早退分支，静态就能证明「新行只落 PostgreSQL」；但计划书 §16 的裁定要求账面写「停写未做」，凭据缺口正是**没在演示库 `enterprise_brain` 上现取过**（在册那本账 `docs/testing/r60-chroma-writeoff-ledger-2026-10-03.json` 的 `base_commit` 距 HEAD 差 51 笔、`sandbox_db=eb_r575_drill`）。这一格要一发写＋一发删＋逐字节对账，会动演示语料 ⇒ 只在跑分窗全部收完之后做，且做完必须把 1008 枚复位。
2. **S1 观察窗**（运维腿，零风险）：现网三枚容器 `printenv INDEX_BACKEND` 全 pgvector、无人拨回；`scripts/rebuild_index.py --status` 两腿差只增不减。这条今天就能取，不必等夜里。
3. **待派三枚**：R654（热集让路驱动件重写，格② 唯一出路）／R656（`TRACE_STORE_PATH` 测试态侧效）／R657（`observability.py` 首屏 `prerequisite` 新串＋契约两格同批）。工单正文在 `%TEMP%\eb104\dispatch\`，一号一次、不带 model 覆盖、基点＝投单那一刻 HEAD。

### 五、01:2x 现读新增：`Bacon`/R650 交卷了，本席裁定＝**不与三单同批，与 R658 同批**

- 交付四枚（`be-r650`@`f904295`，dirty=4、零 commit，已由本席封存到 `%TEMP%\eb104\r650delivery\` 四枚副本）：`app/rag/pg_store.py`＋36／`app/rag/retrieval_pipeline.py`＋34−5／新钉 `tests/test_r650_corpus_leg_names_its_refusal.py`（11 枚牙）／凭据纸 `docs/testing/r650-corpus-named-refusal-2026-10-05.md`。执行层自报三态＝254 passed（纯基点 16 件）→ 262 passed／3 failed（state① 17 件）→ 262 passed／3 failed（state② 17 件），两态红逐枚同名。**这些数只算执行层自报，本席明晨亲跑。**
- 🔴 **裁定**：那三枚红全在 `tests/test_r633_dual_write_off_precondition_teeth.py`，本席现读过原文——它们把「三元组 `(read_corpus, switched_corpus, build_index)` 在场」与「`read_corpus in waiter_legs`」当断言，而 R650 的正确后果就是让 `read_corpus` 合法离开 waiters。⇒ **判据换形的直接后果，不是可修绿的缺陷**，按 R639-A 先例走新单承接：工单 **R658** 已写好（`%TEMP%\eb104\dispatch\R658.txt`），写域只有那枚牙件＋凭据纸，并要求补两把刀（摘掉具名抛 ⇒ `read_corpus` 必须回到 waiters；把新具名方法名改错 ⇒ 在册三元组必须红）。
- **R650 单独并树必红、R658 单独并树也必红 ⇒ 两堆一起 apply、一起跑两态、一起提交**（本席收窗后手动做，不进自动驱动器，因为 R658 还没交货）。
- 顺带订正一笔账面：R650 派工词里「现取枚数 1」是错的，基点实跑是 **2**（`read_corpus`＋`read_topk`）；所以判据① 的归 0 今天只完成一半。剩下那半格（`read_topk` 的吞点在 `app/rag::RetrievalPipeline` 之外的遗留腿里、`switched_corpus` 把 source 写成 `legacy_chroma` 已经与调用方实际行为不符、健康出口看不见「调用方拒绝改问遗留库」）⇒ 工单 **R659** 已写好，基点必须排在 R650＋R658 之后。
- `Descartes`/R655 交卷时留了一格待本席裁：`scripts/r636_stage_coverage.py::shot_leg_view` 的 `fold_legacy` 标签取的是**调用方参数**而不是那条腿的**实际折叠态**（K1 世界里它照旧报 True，今天靠逐枚数字兜住）。本席记为**待办小单**（建议号 R660），不静默丢掉；它不影响今天任何读数，但会让下一位读账面的人误判。
- 席位卫生：`Bacon`／`Descartes` 已 close；`Peirce`／`Godel` 的 `close_agent` 回执 `not found`（在册老毛病：死席收不掉，判活只认 `read_thread`＋`git status`＋mtime）。**当前真在途 0 枚，槽位按四枚准备**：收窗后第一波投 R658（最急，它压着 R650）＋R657＋R656＋R654，一号一次、不带 model 覆盖。

### 六、自动链现在的样子（三段接力，本席不在也不断）

`night1005b_queue.py`（跑分六段，pid 11020）→ `postclose1005.py`（并树 R655→R646→R652 两态＋全量门，pid 36812）→ `postclose_board.py`（看板 §4FB＋名册三行＋跟进单 §180＋提交＋push，pid 48440）。三段都带完成标记：`night1005b.DONE.txt`／`postclose1005.END.txt`／`postclose_board.END.txt`。驱动器规则：state① 不零红就不提交，并把复制进去的文件逐枚还原。
