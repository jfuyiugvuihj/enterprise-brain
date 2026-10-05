# R650 —— 切读态语料腿的配置性拒答：从静默改成就名（凭据纸）

- 席位／工作树／基点：执行层 R650 ／ be-r650 ／ f904295（并完 R638-R 的主树）
- 交付四枚：app/rag/pg_store.py（只加）、app/rag/retrieval_pipeline.py（调用方）、tests/test_r650_corpus_leg_names_its_refusal.py（新增 11 枚牙）、本件
- 一句话：pg_store::switched_corpus 的三答契约一字未动，治的是调用方 retrieval_pipeline::BM25Searcher.build_index。它现在把「旋钮说这条腿本来就不该问」与「真连不上」分开：前者当场成就名拒答、不改问遗留向量库；后者维持 R59b 的 availability-first 并留下绕行账。
- 全程零模型调用、零端口、零容器与镜像、零全量门、零连库（在册量具按默认一枚库都不连那一遍跑的）。

## 1 病因（本席在基点现读，不是转述）

- app/rag/pg_store.py::switched_corpus 的 except 支把 read_corpus 抛出的 VectorReadRejectedError 记 diagnostics、note_read_bypass、logger.warning，然后交回 None；而这枚 None 的 docstring 承诺是「去问遗留库」。
- 调用方 app/rag/retrieval_pipeline.py::BM25Searcher.build_index 只看「all_data 是 None」就打开遗留读（DocumentRetriever().collection.get()），于是「VECTOR_DUAL_WRITE 关着」这一枚**配置性拒答**与「真连不上」走的是同一条退路：答复仍由那台待退役的引擎给出，而账面只写了一句「这一腿没答」。
- 在册量具 scripts/r633_dual_write_off_precondition.py::legacy_receipt_waiters 把这一形点名为 finding read_leg_waits_for_chroma_receipt，派生全从 AST 现取（腿 → 吞掉拒答的那句 except → 该调用方的遗留读）。

## 2 量具两遍读数（同一枚树、同一枚命令、量具与它的牙一字未改）

命令：.venv/Scripts/python.exe scripts/r633_dual_write_off_precondition.py --all（默认不连库；产物落仓外 %TEMP%）

| 读数 | 改前（基点零改动） | 改后（apply 未 commit） |
| --- | --- | --- |
| 发现总枚数 | 8 | 7 |
| read_leg_waits_for_chroma_receipt | 2（read_corpus ＋ read_topk） | 1（只剩 read_topk） |
| 隐式等 Chroma 回执路径 | 2 条 | 1 条 |
| chroma_write_gate_reopens | 1 | 1 |
| delete_set_blind_to_pg_only_rows | 2 | 2 |
| question_rehomes_to_legacy_store | 3 | 3 |
| 退出码 | 1＝不可翻 off | 1＝不可翻 off |

- 改前那一遍的产物：r633-precondition-20261004T161226Z.json；改后那一遍：r633-precondition-20261004T162802Z.json（同一枚 revision f904295 的树上，只差本席那两枚产品码）。
- 判据① 的「归 0」落在**本席写域那一半**：read_corpus 那枚已归零；read_topk 那半枚的吞点 app/rag/retriever.py::_pgvector_hits 与答复点 app/rag/retriever.py::search 都在禁区（Singer／R648 写域），本席一字未碰，量具仍逐枚点名它。
- 🔴 工单写「现取枚数 1」，本席在基点现跑是 **2**（逐枚点名见上表）。R639-A 的凭据纸对这一格自身也不合：§14.2 那两遍是「8 条里含 2 枚 read_leg_waits_for_chroma_receipt」，跟进单 §一 记成 2→1。本席按现跑取信，不迁就纸面。
- 量具仍判「不可翻 off」，属实：另有 chroma_write_gate_reopens／delete_set_blind_to_pg_only_rows／question_rehomes_to_legacy_store／read_topk 四族挡着，本单一枚没治。

## 3 正解形状（只加不改；治的是调用方）

1. app/rag/pg_store.py（只新增，三答契约与那枚 None 的承诺一字未动）
   - CONFIGURAL_READ_REFUSAL_REASONS：配置性拒答那一族的在册稳定码（vector_read_without_dual_write ＋ vector_read_table_unrecognised）。连接类那一枚 vector_read_failed 必须在族外。
   - corpus_configural_refusal_reason()：纯读两枚旋钮，不开连接、不发 SQL、不写任何一本账。加它的理由＝工单要本席现读的那一格：vector_corpus_diagnostics() 分辨不出两类——它的 reason 字段是「异常名＋正文」，正文给人看不给调用方分支（拿正文子串做判定正是 R437 点名的病），所以按授权补这一枚只读 accessor。
2. app/rag/retrieval_pipeline.py::BM25Searcher.build_index：拿到 None 之后先问那枚 accessor；落在配置族里就当场抛 pg_store.VectorReadRejectedError（reason 用在册稳定码，本单零枚新造码），不改问遗留库；否则交给下面那枚具名方法。
3. app/rag/retrieval_pipeline.py::BM25Searcher._legacy_corpus：遗留读单独一枚具名方法，只有「没切」与「连不上」两种 None 走得进来。取数面仍是不带 where 的全库 get()，那一枚形状由 tests/test_classification_fail_closed.py 钉着，本单不改它。
4. 抛出去为什么不会把服务带崩（三处既有收口，本席一枚都没改）：app/rag/retrieval_pipeline.py::RetrievalPipeline.search 的按腿 try（记一句具名日志、另一条腿照旧答）、app/api/v1/chat.py 给 rebuild_bm25 那枚 future 的 done-callback、app/main.py::_preload_sync 的 try。矛盾档里今天的实际形状是「关键词腿具名失败、语义腿仍答」，而不是静默改问退役引擎。

## 4 判据②：两族在册牙改前改后逐枚同数（一字未改、零 skip／xfail）

| 件 | 改前（干净检出 f904295） | 改后（state①） |
| --- | --- | --- |
| tests/test_r330_vector_legs_reach_the_health_outlet.py | 15 passed ／ 0 failed ／ 21.40 s | 15 passed ／ 0 failed ／ 21.67 s |
| tests/test_r592_one_knob_one_default.py | 5 passed ／ 0 failed ／ 11.46 s | 5 passed ／ 0 failed ／ 11.63 s |

- 那两枚以「assert pg_store.switched_corpus() is None」为前置的反证牙照旧绿：switched_corpus 在配置性拒答那一格照旧交回 None，改的是调用方读不读那句 None。
- 本席另补一枚 ::test_switched_corpus_still_gives_its_three_answers，从本席这一侧替那两族牙看住三答契约，不留「靠邻居件不红来证明没越界」的空白。

## 5 🔴 判据① 与三枚在册牙互斥（交总控裁；本席不动禁区、不补投）

- tests/test_r633_dual_write_off_precondition_teeth.py 里三枚牙把「三元组 (read_corpus, app/rag/pg_store.py::switched_corpus, app/rag/retrieval_pipeline.py::build_index) 仍在场」当断言，其中两枚还拿 read_corpus 在不在 waiter_legs 当判据：
  - ::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code
  - ::test_a_refusal_on_another_reason_is_not_a_dual_write_leg
  - ::test_a_refusal_that_is_not_swallowed_stops_being_a_receipt
- 这枚派生整个从 AST 现取：build_index 里只要还留着一枚 .collection.get()，read_corpus 那半格就还在册。所以「判据① 归 0」与这三枚牙**不能同绿**。三条路本席都过了一遍：
  - 让 switched_corpus 的 except 支里出现 raise ⇒ 半格归零，但 tests/test_r330_vector_legs_reach_the_health_outlet.py 那两枚前置当场红（工单写明一字不许改）——排除；
  - 只在 build_index 里加判定、把遗留读留在原地 ⇒ 三枚牙绿，判据① 红——排除；
  - 调用方只做判定、遗留读另立具名方法（本席交的形状）⇒ 判据① 绿、test_r330 与 test_r592 逐枚同数，只有这三枚 r633 牙过期。
- 本席按最后一形交付，禁区两枚件（量具与它的牙）一个字节未动。三枚过期牙请总控按 R639-A 那笔先例代改（那一笔的形状是：钉改名成「只在……还在册时才判」一类，并补成三向有牙：现取归零／改名同判据／把遗留回执包回 build_index 必须复现）。本席不代改。

## 6 三态数字（同名件逐枚点名；两态总枚数相同、红逐枚同名）

- 三态定义：改前＝影子干净检出 f904295（16 枚件，本件尚未存在）；state①＝be-r650 已 apply 未 commit（17 枚件）；state②＝干净检出＋逐枚 sha256 等值摆进本席三枚货（17 枚件）。
- 枚数不变式：共用 16 枚件在改前是 254 passed ／ 0 failed；加本席新增的 11 枚＝265 枚。state① 与 state② 都是 262 passed ／ 3 failed ／ 265 枚，且红逐枚同名（三枚全在 tests/test_r633_dual_write_off_precondition_teeth.py，见 §5）。
- 影子检出根：%TEMP%\eb104\r650_base2；摆进影子树的三枚货与本树 sha256 逐枚相等。秒数只作参考（state② 那一遍另一席位 be-r655 同时在跑，争用真实存在）。

| 件 | 改前 passed／failed／s | state① passed／failed／s | state② passed／failed／s |
| --- | --- | --- | --- |
| tests/test_r650_corpus_leg_names_its_refusal.py | —（新增件） | 11／0／12.21 | 11／0／17.95 |
| tests/test_r330_vector_legs_reach_the_health_outlet.py | 15／0／21.40 | 15／0／21.67 | 15／0／28.79 |
| tests/test_r592_one_knob_one_default.py | 5／0／11.46 | 5／0／11.63 | 5／0／14.55 |
| tests/test_r59_chroma_untouched_on_pg_reads.py | 12／0／12.92 | 12／0／12.96 | 12／0／19.87 |
| tests/test_r59_pg_zero_rows_degrade.py | 10／0／11.26 | 10／0／12.40 | 10／0／21.33 |
| tests/test_r59b_pg_read_switch.py | 24／0／11.59 | 24／0／11.67 | 24／0／18.35 |
| tests/test_r60_write_path_unique_under_pgvector.py | 17／0／9.33 | 17／0／10.06 | 17／0／17.99 |
| tests/test_r625_chroma_write_sites_are_named_one_by_one.py | 23／0／12.99 | 23／0／13.40 | 23／0／20.28 |
| tests/test_r633_dual_write_off_precondition_teeth.py | 35／0／48.07 | 32／3／47.82 | 32／3／70.74 |
| tests/test_r638_pointer_ratchet.py | 14／0／14.33 | 14／0／14.70 | 14／0／22.19 |
| tests/test_r398_three_guard_ledgers.py | 8／0／17.04 | 8／0／14.14 | 8／0／16.27 |
| tests/test_r437_anchor_word_boundary_not_bare_substring.py | 23／0／13.05 | 23／0／12.24 | 23／0／12.58 |
| tests/test_r648_gauge_default_off.py | 21／0／9.53 | 21／0／9.82 | 21／0／9.67 |
| tests/test_classification_fail_closed.py | 8／0／11.43 | 8／0／9.83 | 8／0／10.81 |
| tests/test_prefiltering.py | 32／0／11.49 | 32／0／10.25 | 32／0／11.36 |
| tests/test_retrieval_pipeline_fallback.py | 5／0／11.93 | 5／0／9.75 | 5／0／9.93 |
| tests/test_retrieval_pipeline_concurrency.py | 2／0／14.48 | 2／0／11.60 | 2／0／12.71 |
| 合计 | 254／0／242.28（16 枚件） | 262／3／246.15（17 枚件） | 262／3／335.38（17 枚件） |

- 件清单不是手数：按「tests 下引用 retrieval_pipeline／BM25Searcher／build_index／switched_corpus／_legacy_corpus／r633／r625／read_corpus 任一名字」现取派生（命中 66 枚），本表取其中与本单写域真有行为交集的 17 枚； hygiene 两枚 tests/test_r563_live_module_callables_do_not_leak.py 与 tests/test_r233_undefined_root_names.py 亦已现跑＝31 passed。
- 全量门未跑（按令）。三枚红的定性见 §5：它们是判据① 的直接后果，不是本席写域里的缺陷，也不是可以再「修绿」一下的东西——除非把静默改问遗留库那半格放回去。

## 7 判据③：新增 11 枚牙（tests/test_r650_corpus_leg_names_its_refusal.py）

| 枚 | 名字 | 它钉的是哪一格 |
| --- | --- | --- |
| 1 | ::test_a_configural_refusal_names_itself_and_never_asks_the_legacy_leg | 双写关＋切读开：抛具名拒答、reason 是在册码、DocumentRetriever 一次都不构造、遗留 get 零次、两本账照旧 |
| 2 | ::test_a_connection_failure_still_buys_the_corpus_from_the_legacy_leg | 反向那枚：双写开＋连不上 ⇒ 仍退回遗留库，且 last_bypass 的原因码是 vector_read_failed（不许把可用性一并治没） |
| 3 | ::test_the_shipped_gear_builds_from_the_legacy_leg_and_opens_nothing | 出厂默认档逐字不变：问遗留库、不发 SQL、不抛、语料照旧建得起来 |
| 4 | ::test_the_production_gear_with_dual_write_on_takes_no_new_branch | 判据④ 的现跑形状：双写 on＋切读 on ⇒ accessor 交空串、语料从 PG 取、新分支一步不走 |
| 5 | ::test_switched_corpus_still_gives_its_three_answers | 三答契约（没切／拒答／答出行）一字未动，替 r330 与 r592 看门 |
| 6 | ::test_the_accessor_reads_the_knobs_and_opens_nothing | 新 accessor 四档各有答复，且不动任何一本账、不开连接（只读 accessor 的资格自证） |
| 7 | ::test_the_refusal_family_is_made_of_registered_read_codes | 族里每一枚都是 pg_store 自己登记的读码（零枚新造），且 vector_read_failed 不在族内 |
| 8 | ::test_build_index_holds_no_legacy_receipt_while_the_caller_still_decides | 形状：build_index 里一枚 .collection. 都不许有；switched_corpus／accessor／具名抛／self._legacy_corpus 四件事都在位 |
| 9 | ::test_the_shipped_gauge_no_longer_names_the_corpus_leg_as_a_chroma_waiter | 判据① 的常驻化：在册量具现跑，read_corpus 不在 waiters、腿仍在册、read_topk 那半格必须仍被点名 |
| 10 | ::test_k1_dropping_the_named_refusal_brings_the_silent_receipt_back | 刀一（内存影子）：摘掉那枚具名抛 ⇒ 静默回执复现；同一套机械的正控必须仍绿 |
| 11 | ::test_k2_an_accessor_blind_to_the_gear_redds_only_the_config_family | 刀二（内存影子）：让 accessor 认不出配置档 ⇒ 只有配置那一格退回静默，连接那一格照旧绿（两族分家不是同一根线） |

- 刀全部砍在内存影子（源文读成字符串、AST 改一刀、compile＋exec），落盘的 app/** 一个字节不动；两把刀都有正控。
- 牙一律不拿「此刻盘面脏不脏／盘上字节==HEAD blob」当判据（事故 #96／#107／#113 同族）：形状牙读的是被测模块自己的源码文本，行为牙跑的是真函数，两样都与 git 状态无关。

## 8 判据④：默认双写 on 时这条改口对生产零影响（现读，不只讲道理）

- 部署声明原文（主树 deploy/.env.server，本席只读未动）：VECTOR_DUAL_WRITE=on 与 INDEX_BACKEND=pgvector 两行都在册。
- 本树代码缺省现读：indexing.INDEX_BACKEND_DEFAULT 是 chroma；env 未设时 pg_store.dual_write_enabled() 交回 False、indexing.read_backend() 交回 chroma、read_backend()＝pgvector 只在部署声明里说的时候才成立。
- 在「双写 on ＋ 切读 on」那一档现跑（第 4 枚牙）：corpus_configural_refusal_reason() 交回空串，build_index 从 PG 取语料（vector_corpus_diagnostics 的 source 是 pgvector），既不抛也不碰遗留库 ⇒ 新分支一步都没走。
- 在出厂默认档现跑（第 3 枚牙）：问遗留库、不发一条 SQL、不抛 ⇒ 与改动前逐字一致。
- ⇒ 本单的改口只在「切读开而双写关」这一枚矛盾档里才落地；今天没有任何一处在册声明写这一枚矛盾档（翻默认那一格本身也还欠着计划书 §13 那四件判据）。

## 9 写域与卫生自证（逐枚点名）

- M app/rag/pg_store.py：+36 −0（只加：一族在册稳定码 ＋ 一枚只读 accessor；三答契约、diagnostics、bypass 那几行一字未动）
- M app/rag/retrieval_pipeline.py：+34 −5（调用方分家＋_legacy_corpus 具名方法＋build_index 的 docstring 订正；删掉的 5 行是原地那三行遗留读与两行过期 docstring）
- ?? tests/test_r650_corpus_leg_names_its_refusal.py：21,494 B，418 行 CRLF、无 BOM、控制符 0 枚
- ?? docs/testing/r650-corpus-named-refusal-2026-10-05.md：本件，零枚手抄坐标（一律写 文件::符号；本件落盘之后复跑 tests/test_r638_pointer_ratchet.py＝14 passed／0 failed，见 §6 那一行）
- 禁区零写入（本树 git status --porcelain 现取只有上面四枚）：app/rag/retriever.py、app/api/v1/chat.py、app/api/v1/observability.py、scripts/r633_dual_write_off_precondition.py、tests/test_r633_dual_write_off_precondition_teeth.py、评测集（tests/test_evaluation_report.py 钉着的那族）、frontend/** ——一枚字节都没碰
- 零 commit／add／分支／push：git rev-list --count f904295..HEAD 现取＝0，HEAD 仍是 f904295 那一笔
- 主树一律只读：本席一枚字节没往主树写。在席期间主树被总控自己动过——现取 git status --porcelain 多出 scripts/audit_plan_ticket_ledger.py 与 docs/handoff/plan-ticket-ledger-2026-09-26.md 两枚条目（mtime 现取 00:40:04），主树并已并完 R653 与 R649 两笔；与本席零关系。现读那两笔的 numstat 与本席写域零交集（app/api/v1/*、app/rag/retriever.py 之外都没碰），并树时不会与本单撞写域。
- GPU 今晚归跑分窗，本席一枚都没占：全程零模型调用、零端口、零容器、零镜像。

## 10 留给新单的账（本席不顺手治）

1. read_topk 那半格：吞点 app/rag/retriever.py::_pgvector_hits、答复点 app/rag/retriever.py::search。就是 R639-B 那一笔的形状，写域在 retriever.py（Singer／R648 的邻域）。
2. switched_corpus 在配置性拒答那一格仍把 vector_corpus_diagnostics 的 source 写成 legacy_chroma：三答契约在册、r330 两枚牙以此为前置，本单不许动。从本单起这句账与调用方的实际行为不再一致（调用方已不改问遗留库）。要不要给它第三种 source，属 pg_store 语义改动，归新单裁。
3. tests/test_r633_dual_write_off_precondition_teeth.py 三枚过期牙待总控代改（§5 逐枚点名，本席不动禁区）。
4. 工单「现取枚数 1」与基点实数 2 不合（§2）；账面建议按现跑订正，并按 R639-A 的先例把「代改过期牙」写进并树那笔的说明里。
5. 健康出口那三格（app/common/monitoring.py 读 vector_corpus_diagnostics／vector_read_diagnostics）今天看得见 bypass 码，看不见「调用方拒绝改问遗留库」这一格——那是 R330 那一族的后续，不在本单写域。

## 11 收席复跑（收席那一刻本席亲手再取一遍，不引用 §2／§6 旧账）

- 影子树：%TEMP%\eb104\r650_state3\tree，由 git archive --format=tar f904295 ＋ Python tarfile.extractall 摆出（bsdtar 丢中文名那一格在册）。名册级对账＝**缺 0 枚**（影子 1693 枚 == git ls-tree -r f904295 的 1693 枚），摆货后多出的两枚正是本席新增件。
- state② 摆进影子树的是本席四枚，逐枚 sha256 前 16 位与本体相等且字节数相等：app/rag/pg_store.py ac9440030fba598d（59,498 B）、app/rag/retrieval_pipeline.py cd643626993e0896（66,444 B）、tests/test_r650_corpus_leg_names_its_refusal.py 6b514d56f410313a（21,494 B）、本件 796de5a935448b29（17,991 B）。
- 三态复跑用同一枚命令形状：.venv/Scripts/python.exe -B -m pytest -p no:randomly -q --no-header，并统一 PYTHONDONTWRITEBYTECODE=1（连主树 .venv 的 Junction 也不留字节码，越界写入这一格不留口子）。

| 态 | 件数 | passed | failed | 总枚数 | 秒 |
| --- | --- | --- | --- | --- | --- |
| 改前（纯基点影子树） | 16 | 254 | 0 | 254 | 112.71 |
| state①（be-r650 apply 未 commit） | 17 | 262 | 3 | 265 | 117.32 |
| state②（干净检出＋四枚摆货） | 17 | 262 | 3 | 265 | 123.95 |

- 两态总枚数相同＝265，三枚红**逐枚同名**，且全在 tests/test_r633_dual_write_off_precondition_teeth.py：::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code、::test_a_refusal_on_another_reason_is_not_a_dual_write_leg、::test_a_refusal_that_is_not_swallowed_stops_being_a_receipt（定性见 §5，禁区一字未动）。
- 量具读数这次在**两枚影子树各现取一遍**，不引用 §2：纯基点树＝发现 8 枚、read_leg_waits_for_chroma_receipt 2、隐式回执路径 2（waiters 为 read_corpus 与 read_topk）、exit 1；摆货后的树＝发现 7 枚、该 finding 1（只剩 read_topk；read_corpus 已离 waiters 但仍在 legs 名册上）、exit 1。与本席 §2 那两遍逐枚同数。
- r638 棘轮基线对账现跑：scripts/r638_doc_pointer_ruler.py --check-baseline docs/testing/r638-pointer-baseline.json ＝ grew 空、forged 空、exit 0；输出里的 shrank 两档属于别的席位改过的 docs（docs/perf/r387-label-lineage-2026-09-27.md 与 docs/handoff/2026-09-15-orchestration-board.md），与本单无关，本件坐标枚数仍为 0。
- §9 那句主树盘面是 00:5x 现取的，收席再取已变：scripts/audit_plan_ticket_ledger.py 与 docs/handoff/plan-ticket-ledger-2026-09-26.md 两枚已被总控并树。主树现取四条：chroma_db/chroma.sqlite3（mtime 10-04 17:04）、.zcodeignore（09-24）、课堂实践-对象建模-企业智脑/（09-24）、docs/handoff/2026-10-05-next-shift-plan.md（01:08，总控交接纸）。四枚都不在本席写域，本席对主树零写入：写只发生在 be-r650 的四枚货与仓外 %TEMP% 的探针／影子树。
- 收席那一刻现取：git rev-parse HEAD = f904295、git rev-list --count f904295..HEAD = 0、git status --porcelain 恰四枚、git diff --numstat HEAD = 36 0 与 34 5。零 commit／add／分支／push，等总控代提交。
