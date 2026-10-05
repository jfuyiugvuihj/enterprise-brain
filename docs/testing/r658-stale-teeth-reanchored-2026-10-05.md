# R658 —— 三枚过期牙改挂到 R650 之后的新形状（凭据纸）

- 席位／工作树／基点：执行层 R658 ／ `C:/Users/fengx/PycharmProjects/be-r658` ／ `8a52c5c`（开工现取 `rev-parse HEAD` = `8a52c5cfbc83b26908039a6380fb2aa62f2746a8`，与派工词同一枚基点，盘面零条目）
- 交付两枚：`tests/test_r633_dual_write_off_precondition_teeth.py`（改挂：+226 / -23，现取 995 行／53,840 字节，sha256 前 16 位 `61e7cde810cf443a`）、本件
- 🔴 **必须与 R650 同批并树**：单独并本单（牙按新形状判、码还是搬家前的形状）或单独并 R650（码搬了、牙还钉旧形状）都必红。这不是可选项。
- 一句话：R650 让语料腿的遗留回执从 `retrieval_pipeline.py::build_index` 搬进具名方法 `_legacy_corpus()` 并当场具名抛之后，`read_corpus` **合法地**离开 `waiters`；本单把那三枚钉旧形状的牙改挂到新形状，并补两把刀证明今天的归 0 是真行为、不是量具漏看。
- 全程离线：不连 PostgreSQL、不起服务、不开现役 `chroma_db` 卷、不打模型、不动容器与镜像、不跑全量门。落盘的 `app/**` 一个字节都不动（那两枚是 R650 封存件的施工态副本，不是本席交付）。

## 1 病因（本席在基点＋施工态现跑，不是转述）

施工态＝基点干净树摆进 R650 三枚码件（两枚产品＋一枚测试件），牙件一字未动时现跑 `tests/test_r633_dual_write_off_precondition_teeth.py`：**3 failed / 32 passed**，逐枚同名：

- `::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code` —— 它把三元组 `(read_corpus, app/rag/pg_store.py::switched_corpus, app/rag/retrieval_pipeline.py::build_index)` 当成在册事实；搬家后第三格不再是 `build_index`。
- `::test_a_refusal_on_another_reason_is_not_a_dual_write_leg` —— 刀砍在 `read_topk`，却要求 `read_corpus` 仍在 `waiters`。
- `::test_a_refusal_that_is_not_swallowed_stops_being_a_receipt` —— 同上，反向刀里那句「另一条不该被误伤」也拿 `read_corpus in waiter_legs` 当判据。

三枚都是**过期现场读数**（在册事故 #96 同族）。治法按工单：判据可以换，牙不许摘——不删断言、不 skip／xfail、不改恒真。

## 2 施工态的在册读数（`legacy_receipt_waiters()` 与 `switch_gated_legs()` 全从 AST 现取）

| 面 | 现取内容 |
| --- | --- |
| 拒答腿名册（legs） | `_document_leg_connection`、`document_vector_rows`、`indexed_document_names`、`read_corpus`、`read_topk`（五枚，一枚没少） |
| 吞点（swallows） | `read_corpus` ← `app/rag/pg_store.py::switched_corpus`；`read_topk` ← `app/rag/retriever.py::_pgvector_hits` |
| 等回执（waiters） | **只剩 1 枚**：`(read_topk, app/rag/retriever.py::_pgvector_hits, app/rag/retriever.py::search)` |
| 语料腿那一格 | 在册三元组 = `(read_corpus, app/rag/pg_store.py::switched_corpus, app/rag/retrieval_pipeline.py::_legacy_corpus)` —— 腿还在、吞点还在，答复者是那枚具名方法，但它不在 `waiters` |
| 在册量具端到端现跑 | `--all`（默认一枚库都不连）＝发现 7 条、`read_leg_waits_for_chroma_receipt` 1 条路径（逐枚点名 `read_topk`）、`legs` 五枚、退出码 1＝不可翻 off；产物落 `%TEMP%\r633\r633-precondition-20261005T022244Z.json`（仓外）。与 R650 凭据纸「改前 8 条／改后 7 条」逐枚同数 |

## 3 三枚牙怎么改挂（逐枚：旧判据 → 新判据）

新挂的公共件是本单新增的派生器 `corpus_registration()`：语料腿那一格的三元组，两副面孔取一副——R650 之前「答复由谁给」就写在 `waiters` 里；R650 之后本腿离开 `waiters`，同一问句改由**多走一跳**回答（吞点的调用方委托出去的那枚带遗留读的具名方法）。谓词一律借量具自己的 `swallows` / `_legacy_receipt_calls()` / `_calls_inside()`，本件不自造第二套「什么算遗留读」。取不到唯一一枚时交回现取到的整串名字，等式对不上就红。

| 枚 | 改前（旧形状） | 改后（新形状） |
| --- | --- | --- |
| `::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code` | `("read_corpus", ...::switched_corpus, ...::build_index) in pairs` | 正面钉四格：五枚腿名册照旧 ⊆ legs；`TOPK_TRIPLE` 照旧在 `waiters`；`read_corpus` **在 legs**（腿没被拆）且 **不在 waiter_legs**；`corpus_registration() == CORPUS_TRIPLE`；`read_leg_waits_for_chroma_receipt` 的 subject 名册恰为 `{read_topk}` |
| `::test_a_refusal_on_another_reason_is_not_a_dual_write_leg` | `read_corpus in leg_names` ＋ `read_corpus in waiter_legs` | `read_corpus in leg_names` ＋ `read_corpus not in waiter_legs`（刀砍 top-k，不许把语料腿的归 0 倒着推回去）＋ `corpus_registration() == CORPUS_TRIPLE` |
| `::test_a_refusal_that_is_not_swallowed_stops_being_a_receipt` | `read_corpus in waiter_legs`（「另一条不该被误伤」） | 同一格改判 `corpus_registration() == CORPUS_TRIPLE`——「没被误伤」现在意味着搬家后的在册三元组照旧，而不是回到 `waiters` |

## 4 刀账（两把新刀，逐把改前 → 改后；每把都有正控）

| 刀 | 刀口（砍在内存源码副本，落盘不动） | 派生读数 |
| --- | --- | --- |
| 正控 | 同一套机械、`edits=()`（刀口不落） | registration = `(read_corpus, ...::switched_corpus, ...::_legacy_corpus)`＝在册；waiters 只有 `read_topk`；发现 7 条 |
| **S1 反向刀** `restore_the_silent_legacy_question()` | 把调用方那枚具名抛改回「退回问遗留目录」：`if all_data is None:` 那一支整段复原成搬家前的「构造 `DocumentRetriever` ＋ 全库 `get()`」 | registration = `(read_corpus, ...::switched_corpus, ...::build_index)`；**`read_corpus` 重新出现在 `waiters`**；`read_leg_waits_for_chroma_receipt` 的 subject 变回 `{read_corpus, read_topk}`；发现 8 条——与 R650 改前那一遍逐枚同数 |
| **S2 形状刀** `misname_the_named_method()` | 只把那枚具名方法改名（def 与调用点各一枚，行为一字不变） | registration = `(read_corpus, ...::switched_corpus, ...::_legacy_corpus_renamed)` ⇒ **在册三元组当场红**；`waiters` 那一格照旧是空的 ⇒ 钉的是名字，不是「waiters 空不空」 |

两把刀各自还钉两格不许误伤：`read_corpus` 仍在 legs（不许顺手拆腿）、`TOPK_TRIPLE` 仍在 `waiters`（吞点与答复点都在本单写域外）。常驻写法：装刀机械只有一枚 `corpus_reading(..., bite=False/True)`——正控**按刀各配一枚**（`test_the_positive_control_reads_the_registered_shape[S1]`／`[S2]`），victim 同参数两枚（`test_each_new_knife_redds_the_registered_corpus_triple[S1]`／`[S2]`），本件因此从 35 枚长成 39 枚。

## 5 判据逐条读数（四件，逐件可失败）

- ① **达标**：三枚改挂后全绿；`read_corpus` 不在 `waiters`、仍在 legs 名册——正面钉在册件里（见 §3 第一枚），并由在册量具端到端现跑旁证（§2 末行）。
- ② **达标**：S1／S2 各红各的格且都点名到位（§4 表），正控先绿；三枚常驻件在同名册两态里逐枚同名。
- ③ **达标**：牙件全文 `porcelain`／`rev-parse`／`numstat`／`ls-files`／`MERGE_HEAD` 命中各 0 枚，且无「盘上字节等于 HEAD blob」那一形（无 `git show`、无 `subprocess`）；派生只看源码文本与 AST，与 git 状态无关。
- ④ **达标**：两态数字见 §6，总枚数相同（300）、名单逐枚相同（JSON id 集合逐枚相等）、红 0 枚。

## 6 两态数字（同名册逐枚点名；state①＝apply 未 commit，state②＝干净检出＋摆货）

- state①：本树＝基点 `8a52c5c` ＋ R650 三枚码件 ＋ 本单牙件 ＋ 本件，全部未 commit。命令统一 `.venv/Scripts/python.exe -B -m pytest -p no:randomly -q --no-header`，统一 `PYTHONDONTWRITEBYTECODE=1`。
- state②：影子树 `%TEMP%\eb105\r658_state2\tree`，由 `git archive --format=tar 8a52c5c` ＋ Python `tarfile.extractall` 摆出（bsdtar 丢中文名那一格在册）。名册级对账＝**缺 0 枚**（在册 1706 枚全部落位），摆货后只多 1 枚＝R650 新增的测试件；四枚施工件逐枚 sha256 等值摆进。
- 对账机器：两态各出一份 junit XML → `%TEMP%\r658_state1.json`／`r658_state2.json`，`ids_sorted` 逐枚相等（只在① 0 枚、只在② 0 枚），每枚件计数亦逐枚相等。

| 件 | state① | state② |
| --- | --- | --- |
| `tests/test_r633_dual_write_off_precondition_teeth.py` | 39／0 | 39／0 |
| `tests/test_r650_corpus_leg_names_its_refusal.py` | 11／0 | 11／0 |
| `tests/test_r330_vector_legs_reach_the_health_outlet.py` | 15／0 | 15／0 |
| `tests/test_r592_one_knob_one_default.py` | 5／0 | 5／0 |
| `tests/test_r59_chroma_untouched_on_pg_reads.py` | 12／0 | 12／0 |
| `tests/test_r59_pg_zero_rows_degrade.py` | 10／0 | 10／0 |
| `tests/test_r59b_pg_read_switch.py` | 24／0 | 24／0 |
| `tests/test_r60_write_path_unique_under_pgvector.py` | 17／0 | 17／0 |
| `tests/test_r625_chroma_write_sites_are_named_one_by_one.py` | 23／0 | 23／0 |
| `tests/test_r638_pointer_ratchet.py` | 14／0 | 14／0 |
| `tests/test_r398_three_guard_ledgers.py` | 8／0 | 8／0 |
| `tests/test_r437_anchor_word_boundary_not_bare_substring.py` | 23／0 | 23／0 |
| `tests/test_r648_gauge_default_off.py` | 21／0 | 21／0 |
| `tests/test_classification_fail_closed.py` | 8／0 | 8／0 |
| `tests/test_prefiltering.py` | 32／0 | 32／0 |
| `tests/test_retrieval_pipeline_fallback.py` | 5／0 | 5／0 |
| `tests/test_retrieval_pipeline_concurrency.py` | 2／0 | 2／0 |
| **同名册 17 枚小计** | **269／0** | **269／0** |
| `tests/test_r563_live_module_callables_do_not_leak.py`（卫生） | 5／0 | 5／0 |
| `tests/test_r233_undefined_root_names.py`（卫生） | 26／0 | 26／0 |
| **合计 19 枚件** | **300 passed／0 failed** | **300 passed／0 failed** |

- 与 R650 那三态表的差额可解释：本单把同名册从 265 枚抬到 269 枚（牙件 35→39，其余 16 枚件逐枚同数），红从 3 枚归 0——归的正是 §1 那三枚。
- 复跑账（逐遍点名，不含糊）：纸落盘前两遍＝299／0，纸落盘后一遍＝299／0，正控按刀配齐之后再各一遍＝**300／0**；差的那一枚是正控从一枚长成两枚（`[S1]`／`[S2]`），红始终 0 枚。上表是**定稿字节**那一遍：两态 300／0、同名册 269／0，两份 JSON 的 id 名单逐枚全同、每枚件计数逐枚相等。牙件在两树各 39／0，r638 棘轮在两树各 14／0——本件零枚手抄坐标，棘轮不因这张纸改口：在册尺 `scripts/r638_doc_pointer_ruler.py --check-baseline docs/testing/r638-pointer-baseline.json` 在本树现跑 exit=0（grew 空、forged 空；shrank 那两档是他席 docs 的账，本席不接手）。

## 7 施工态与封存件的六枚哈希（逐枚现取）

R650 四枚货由总控封存于 `%TEMP%\eb104\r650delivery`。本席把前三枚复制进树当施工态（第三枚测试件要与牙件同跑），收工前逐枚 sha256 比对：

| 树内路径 | 封存件 | sha256 | 等值 |
| --- | --- | --- | --- |
| `app/rag/pg_store.py` | `__pg_store.py` | `ac9440030fba598dea6fa1dc5d0926c5ae37be0715d5fe7464f9fd2e090306f1` | 是 |
| `app/rag/retrieval_pipeline.py` | `__retrieval_pipeline.py` | `cd643626993e089616ac07cb0b4267a9f6d68acad395582e4691aba0d9798f1e` | 是 |
| `tests/test_r650_corpus_leg_names_its_refusal.py` | `__test_r650_corpus_leg_names_its_refusal.py` | `6b514d56f410313a4349e9cea33e9e41ce0921e8bfb47e18bae0bb252ef971b7` | 是 |

- 🔴 本席**不交回**这两枚产品件与 R650 的测试件：并树时由总控从 be-r650 原货取，防两席各改一份漂移。本席交付只有 §抬头那两枚。
- R650 的凭据纸（`__r650-corpus-named-refusal-2026-10-05.md`）本席未落进自己的树：那是别人的账面，本席不替它负责对位；两态影子树亦同。

## 8 禁区与写域自证

- 写域只有两枚：`tests/test_r633_dual_write_off_precondition_teeth.py`（改）、`docs/testing/r658-stale-teeth-reanchored-2026-10-05.md`（新增）。
- `scripts/r633_dual_write_off_precondition.py`（判定语义一字未改，现取 1012 行／54,967 字节、不在改动清单里）、`scripts/run_gate.py`、`pyproject.toml`、`frontend/**`、`docs/handoff/**`、评测夹具、`deploy/.env.server`、`chroma_db/**` 全部零字节。`app/**` 只有那两枚施工态副本（内容与封存件逐枚等值，非交付）。
- 本单不需要改量具：它在施工态树上现读就是「`legs` 五枚、`swallows` 两枚、`waiters` 一枚」，判据① 的归 0 由派生自己给出——**没碰到「非改不可就停下回报」那一格**。

## 9 留给下一格的账（本席不顺手治）

1. `read_topk` 那半格（R639-B 形状）：吞点 `app/rag/retriever.py::_pgvector_hits`、答复点 `app/rag/retriever.py::search`，两枚都在写域外。它仍是 `waiters` 上唯一一枚，也是「不可翻 off」现在还站得住的那一格。
2. 语料腿的在册三元组是**名字敏感**的：将来谁再搬 `_legacy_corpus()` 或改它的名，S2 那一族当场红——并树的人要么带上牙件改挂，要么给出等价的可证形状。R658 之后「搬家」不再是免检动作。
3. `switched_corpus` 在配置性拒答那一格仍把 `vector_corpus_diagnostics` 的 source 写成 `legacy_chroma`，而调用方已不改问遗留库（R650 §10 第 2 条原话）。本席按牙看：三答契约今天仍由 R650 第 5 枚牙钉着，那一格语义改判属 `pg_store`，归新单裁。
4. 派工词里那句「在册那枚三元组」若由后续单升成常驻钉（写进名册件），建议连带把本件的 `corpus_registration()` 一起搬过去，别在名册件里再抄一套「什么算遗留读」。
5. 施工副本纪律：本席树里那两枚产品件与 R650 测试件是**影子态**，收席后不该被当成写域；若总控并完 R650 想让 be-r658 继续活着，需重新对基点。

## 10 收工自证（收席那一刻现取）

- `git -C C:\Users\fengx\PycharmProjects\be-r658 rev-parse HEAD` = `8a52c5cfbc83b26908039a6380fb2aa62f2746a8`（与派工词基点同枚）
- `git rev-list --count 8a52c5c..HEAD` = **0**（零 commit、零分支、零 push）
- `git diff --cached --numstat` = 空（staged 零条目）
- `git status --porcelain` = 5 枚条目，逐枚：`M app/rag/pg_store.py`、`M app/rag/retrieval_pipeline.py`（R650 施工态副本）、`M tests/test_r633_dual_write_off_precondition_teeth.py`（交付一）、`?? tests/test_r650_corpus_leg_names_its_refusal.py`（R650 施工态副本）、`?? docs/testing/r658-stale-teeth-reanchored-2026-10-05.md`（交付二＝本件）
- `git diff --numstat HEAD` = `36 0`／`34 5`（R650 两枚产品件，逐枚与 R650 凭据纸所记同数）＋ `226 23`（本单牙件）
- 施工脚本与产物一律在仓外：`%TEMP%\r658_blocks_*.py`、`%TEMP%\r658_apply.py`、`%TEMP%\r658_shadow.py`、`%TEMP%\r658_read.py`、`%TEMP%\r658_state*.xml|json`、`%TEMP%\r633\r633-precondition-*.json|md`、`%TEMP%\eb105\r658_state2\tree`。主树 `C:\Users\fengx\PycharmProjects\企业智脑` 一个字节未写。