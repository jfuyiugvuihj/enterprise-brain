# R639 取证纸 —— off 态那四支静默能不能在这一枚文件里改成显式失败

- 席位：执行层 R639　树：`C:\Users\fengx\PycharmProjects\be-r639`　基点：`45d5f55`（分支 `codex/be-r639`）
- 收货结论先放这儿：**派工词判据①那三族「各归零」在本席写域（`app/rag/retriever.py` ＋ 新 `tests/test_r639_*` ＋ 新 `docs/testing/r639-*`）内做不到，而且不是"没找到形状"——两族已被实测证明与在册件互斥，第三族（写落点）与 R625 名册是同读一份 `may_feed_ids` 的镜像命题。本席按硬纪律「发现派工词前提是假的／要扩写域 → 停下来回报」收席，盘上产品码一字未留（blob 现校复原）。**
- 本席做了什么：把候选产品码补丁（11 处 edit，逐字见 `docs/testing/r639-candidate-product-code.diff`）**投到盘上真跑了两遍量具与逐文件在册件**，跑完立刻复原。所有数都是这一遍现取的，没有一处转抄 R633 纸。
- 🔴 **账面订正（10-04 21:14，本席收席那一刻）：上面两句「盘上产品码一字未留／候选不是收货物」已过期。** 总控裁「签 R639-A：把补偿切片做成正式收货物」，补偿那一支的产品码就在盘上（`app/rag/retriever.py` 七处、`62 增 25 删`）＋ 新钉 13 枚 ＋ 全套读数见 §14（§14.8＝全量门归因，§14.9＝需总控落的坐标账面）。§4 那枚 11-edit 候选补丁与 §9 那八把刀属前一档席位的设计账，现行货一律以 §14 为准；另两族与读腿按裁决不动三枚在册钉，转新单。

---

## 1. 盘面四枚（收席那一刻现取）

现取（2026-10-04 21:14 收席那一刻，树 `C:\Users\fengx\PycharmProjects\be-r639`）：这一节**覆盖** 19:5x 那笔旧读数——旧账判的是「候选投盘后已复原」那一档，货经总控裁「签 A」后已落成收货物，现行货见 §14.1。四枚盘面之外另附两枚本席亲自跑的校验：

| 命令 | 读数 |
| --- | --- |
| `git status --porcelain` | ` M app/rag/retriever.py` ＋ 五枚未跟踪件（逐枚点名见下行）；除此之外零已跟踪改动 |
| `git diff --numstat HEAD` | `62` 增 `25` 删，只此一行：`app/rag/retriever.py` |
| `git ls-files --others --exclude-standard` | `docs/testing/r639-a-product-code.diff`、`docs/testing/r639-candidate-patchlib.py`、`docs/testing/r639-candidate-product-code.diff`、`docs/testing/r639-off-state-explicit-failure-2026-10-04.md`、`tests/test_r639_undo_survives_a_missing_pg_leg.py` |
| `git rev-list --count 45d5f55..HEAD` | `0`（本席未 commit，执行层禁 commit，由总控代提交） |
| `git rev-parse --short HEAD` | `45d5f55`（基点未动） |
| `git hash-object app/rag/retriever.py` | `b9c0fa7dc90a5a5ff1763606c9831790057f81fb`（与 state② 干净检出投货后逐字相等）；基点原文 `0f9eebf9fa85d352c4fe5a477fe7ec402d48e423` ＝ `git rev-parse 45d5f55:app/rag/retriever.py` |
| `chroma_db/chroma.sqlite3` | 没被写脏——porcelain 里没有这一行。全程用 `.venv\Scripts\python.exe`，零枚 import 触碰 `app/api/v1/chat.py`（本周两枚执行层踩过的那格） |

---

## 2. 改前读数（R633 量具，静态两面，一枚库都没连）

命令原文：

```
.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_before
```

`exit=1`，**10 条发现**，逐枚原因码现取：

| code | 枚数 | 落点（量具原句里的身份） |
| --- | --- | --- |
| `chroma_write_gate_reopens` | 1 | `app/rag/retriever.py::DocumentRetriever._write_batch::add(documents, embeddings, ids, metadatas)` |
| `compensation_needs_a_leg_it_wont_have` | 2 | `...::_undo_vector_write::delete(ids)`、`...::_undo_vector_write::add(documents, embeddings, ids, metadatas)` |
| `delete_set_blind_to_pg_only_rows` | 2 | `...::add_document::delete(ids)`、`...::delete_document::delete(ids)` |
| `question_rehomes_to_legacy_store` | 3 | `DocumentRetriever._document_rows_by_leg`、`DocumentRetriever.list_documents`、`DocumentRetriever.document_chunks` |
| `read_leg_waits_for_chroma_receipt` | 2 | `read_topk`（吞点 `app/rag/retriever.py::DocumentRetriever._pgvector_hits`）、`read_corpus`（吞点 `app/rag/pg_store.py::switched_corpus`） |

枚数与 R633 纸 §7 相等（10 条、五族 1/2/2/3/2）⇒ 这一版量具没漂，本席的对照面站得住。

---

## 3. 四支静默的调用点证据（硬纪律：判可达性必须查调用点）

### ① 读腿（两跳派生，**两半各在一处，只有一半在写域**）

- 吞点：`app/rag/retriever.py::DocumentRetriever._pgvector_hits` —— `except Exception` 把 `app/rag/pg_store.py::read_topk` 在 off 态发出的 `REASON_VECTOR_READ_WITHOUT_DUAL_WRITE` 吞成"这一腿没答"（交回 `None`），并记一枚 `note_read_bypass`。
- 唯一调用点：`app/rag/retriever.py::DocumentRetriever.search` —— `pg_hits = self._pgvector_hits(...)` 之后 `if pg_hits is not None: return ...`，否则**直落** `self.collection.query(**kwargs)`。⇒ off 态语义答复真的由遗留引擎给出。
- 另一半在写域外：`app/rag/pg_store.py::switched_corpus` 吞 `app/rag/pg_store.py::read_corpus` 的拒答 ⇒ `app/rag/retrieval_pipeline.py::BM25Searcher.build_index` 用 `r.collection.get()` 建语料。`pg_store.py` 本席被要求"先停下来回报"，`retrieval_pipeline.py` 被派工词明确划在射程外。⇒ **判据里"①读腿不许悄悄交回遗留腿"这句话，一枚 `retriever.py` 只能治一半。**

### ② 删除问句

- 病根：`app/rag/retriever.py::DocumentRetriever._document_rows_by_leg` 顶部那枚早退 `if not self._writes_go_to_pgvector(): return legacy_ids, legacy_metadatas, []` ⇒ off 态 PG 那一格恒空。
- 调用点两枚（现取，非签名推断）：`DocumentRetriever.add_document`（同名重传的 `stale_ids` 由它派生）、`DocumentRetriever.delete_document`（`stored_ids` 空就 `return`——**不报错、原样返回**）。
- 端点那一层：`app/api/v1/chat.py` 的删除只在 `retriever.delete_document(filename)` 抛异常时才判 `index_rollback_failed`；不抛就报删除成功。本席未改端点（射程外），只取证。

### ③ 名单 / 按文档读回

- `app/rag/retriever.py::DocumentRetriever.list_documents`、`app/rag/retriever.py::DocumentRetriever.document_chunks` 各拿 `self._writes_go_to_pgvector()` 当唯一分岔，判定为假时整句改问遗留目录（`self.collection.get()` / `self.collection.get(where={'filename': filename})`）。
- 消费点：`app/api/v1/chat.py::list_documents`（`retriever.list_documents()` 拿去过滤可见文档）、`app/api/v1/chat.py` 里 `getattr(retriever, "document_chunks", None)` 那一处发布读回。

### ④ 补偿（这一族是本席唯一能诚实清零的）

- `app/rag/retriever.py::DocumentRetriever._undo_vector_write` 的两枚调用点（`add_document`、`delete_document` 的 `except` 支）**各自站在 `if mirror is not None:` 之内**；`mirror` 的生产者是 `DocumentRetriever._open_vector_mirror` → `app/rag/pg_store.py::vector_mirror`，off 态恒 `None` ⇒ 整支不可达。
- 撤销能力本身在码上不缺：`self.collection.delete(ids=list(written_ids))` 的闸门是 `written_ids and not self._writes_go_to_pgvector()`（off 态为真）。**它缺的不是逻辑，是"进得来"。** 本族归零 = 把调用点那道"要一条拿不到的腿"的门摘掉，并让函数自己容得下 `mirror=None`。


---

## 4. 候选产品码补丁（11 处 edit）与改后读数 —— 🔴 前一档席位的设计账，现行货见 §14.1（七处）

总闸只翻**一枚矛盾档**，另三档一字不改：

```
_pg_is_declared_without_a_leg = stores_vectors
                              and indexing.pgvector_writes_are_primary()   # 部署说 PG 是本体
                              and not pg_store.dual_write_enabled()        # 旋钮把那条腿关了
```

| 档 | `INDEX_BACKEND` | `VECTOR_DUAL_WRITE` | 候选补丁的答复 | 与今天的关系 |
| --- | --- | --- | --- | --- |
| 出厂默认 | chroma | off | 遗留腿照旧接行、问句照旧只问遗留 | **一字不改**（整套在册件都跑在这一档） |
| S0 双写 | chroma | on | 两腿照旧双写 | **一字不改**（`dual_write_enabled()` 为真 ⇒ 总闸恒 False） |
| 生产现态 | pgvector | on | PG 收行、遗留不接 | **一字不改**（同上） |
| 矛盾档 | pgvector | off | 写／问删／名单／读回四支一律 `raise VectorWriteRejectedError(reason="vector_leg_off_but_switched")`；读腿那枚 `vector_read_without_dual_write` 拒答不再被吞；补偿调用点不再要求一条拿不到的腿 | **本单要改的就这一档** |

改后读数（同一枚量具、同一条命令，只换盘上的产品码；跑完 `finally` 里立刻复原并现校 blob）：

```
.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_after
```

| 面 | 改前 | 改后（候选投盘） |
| --- | --- | --- |
| 发现总枚数 | 10 | **7** |
| `chroma_write_gate_reopens` | 1 | 1 —— 未动，成因见 §5.1 |
| `compensation_needs_a_leg_it_wont_have` | 2 | **0** |
| `delete_set_blind_to_pg_only_rows` | 2 | 2 —— 未动，成因见 §5.2 |
| `question_rehomes_to_legacy_store` | 3 | 3 —— 未动（判据没要求它归零，本席也没绕它） |
| `read_leg_waits_for_chroma_receipt` | 2 | **1**：`read_topk` 半格消掉，`read_corpus` 半格原样在册（吞点与答复点都在写域外） |
| 变异写点／名册 | 6 枚、`roster_findings=0` | 6 枚、`roster_findings=0`（逐枚身份仍对得上） |
| `void`（读数可信度） | 空 | 空 |
| 退出码 | 1 | 1（还有发现 ⇒ 仍判"不可翻"，本席不拿 7 条冒充 0 条） |

要点三条：

1. `compensation_needs_a_leg_it_wont_have` **2 → 0**，且 `roster_findings=0`、`void=0` ⇒ 这一族的归零不是绕量具：名册逐枚点名的六枚写点身份、闸门、id 来源全对得上，量具自己也没报"读数不可信"。
2. `read_leg_waits_for_chroma_receipt` **2 → 1**：`read_topk` 那一半消掉（吞点里有了 `raise` 就不再是"吞"），`read_corpus` 那一半原样在册——它的吞点与答复点都在写域外（§3①）。
3. `chroma_write_gate_reopens` 1 → 1、`delete_set_blind_to_pg_only_rows` 2 → 2、`question_rehomes_to_legacy_store` 3 → 3：**四支拒收全数落地，这三族一条都没少**。§4 附表给出逐切片归因，§5 给出为什么。

---

## 5. 三族为什么锁死：不是"没找到形状"，是与在册件互斥（全部实测）

### 5.1 `chroma_write_gate_reopens` 与 R625 名册读的是同一句话

- R625 名册给 `app/rag/retriever.py::DocumentRetriever._write_batch::add(documents, embeddings, ids, metadatas)` 登记的在册语义是 `role="primary"`、`requires_false=(_writes_go_to_pgvector,)`；它的常驻钉 `tests/test_r625_chroma_write_sites_are_named_one_by_one.py::test_each_write_site_declares_its_own_gate` 与 `::test_no_new_row_write_is_reachable_while_pgvector_is_primary` 判的就是"这一枚必须被判定挡在 False 那一侧"。
- R633 的 `write_site_face` 对**同一个 `WriteSite.may_feed_ids`** 派生 verdict：`_writes_go_to_pgvector` 出现在 falsy ⇒ `reopens_when_off` ⇒ 报这一族。
- ⇒ **R625 绿 ⟺ 这一族红**。两条判据读同一枚合取闸门，一个要它在、一个要它不在。
- 实测（variantA：把 `_write_batch` 里那道判定套进一层新名字，让 falsy 里不再出现 `_writes_go_to_pgvector` 这几个字）：这一族 1 → 0，同时 `roster_findings` 交回 **2 条红句**（`_gate_findings` 报"在册闸门必须假 `_writes_go_to_pgvector`"落空、`_primary_leg_findings` 报"这一枚把新行交给遗留腿，却没有任何判定挡着它"），`roster_cross_check` 因此进 `void` ⇒ 量具按**退出码 2「读数不可信」**收，不是绿。
- 唯一"既不改名册又不改量具"的归零姿势是真把那枚遗留写点摘掉——那叫停写/退役，本单明令不做（「本单不拨旋钮、不停写、不做退役」），而且 R625 的在册理由已经先把这条路堵了：「停写靠的是判定，不是把这枚写点摘掉——摘掉就把回滚通路拆了」。

### 5.2 `delete_set_blind_to_pg_only_rows` 只认名字，不认拒收

- 判据形状（量具现取）：`add_document` / `delete_document` 里那两枚 `delete` 写点，只要**所在函数直呼过 `_document_rows_by_leg`** 这一枚名字就报，与那句问句内部会不会拒收无关。
- 实测：候选在问句顶部插了拒收（`branch_delete`）之后，这一族仍 2 → 2；把这一支单独摘掉（drop-delete）与全量候选的读数**逐枚相同**。⇒ 插闸门改的是行为，改不了量具看到的名字。
- 实测（variantB：在两枚调用点与问句之间加一层纯转发 `_reupload_targets`）：这一族 2 → 0、名册仍 0 红、`void` 仍 0 ——**而这正是判据①禁的那一格**：转发层一个字的行为都没加，off 态照旧交回空的 PG 那一格，量具只是看不见名字了。本席不交这一形。
- 要让这一族诚实归零，只能让 `_document_rows_by_leg` 在**所有** off 态都不再早退（含出厂默认 `chroma + off`）——那一档正是 §5.3 两枚 R60 钉硬钉住的地方。

### 5.3 政策冲突：矛盾档里"遗留腿必须仍写"是两枚在册钉明写的判据

候选补丁在盘上真跑，最先红的不是 R633 的牙，而是 R60／R625 的钉：

- `tests/test_r60_write_path_unique_under_pgvector.py::test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write` —— docstring 原文：「判据②反证第二把的形状：**开关在 pgvector 而双写关着，遗留腿必须仍写**。谁都不写是本单最贵的错：上传报成功、两库里都没有这份文档的向量。」断言 `ok is True` ＋ 遗留腿行数 ＋ PG 零行。
- `tests/test_r60_predicate_terms_and_leg_parity.py::test_the_stop_write_branch_is_inside_the_pg_leg` —— 「判定为真而 PG 腿不存在时（`mirror is None`）不许演成零写……谁把停写判定挪到 `if mirror is not None` 之外，零写当场红」。断言 `ok is True`、一条 SQL 都不发、`collection.adds == [IDS]`。
- `tests/test_r625_chroma_write_sites_are_named_one_by_one.py::test_dropping_one_term_of_the_write_predicate_is_a_lie[dual_write_enabled]` —— 同一档里断言 `_document_rows_by_leg` **不许**去问 PG（`"doc_rows" not in connection.log`），而 `_writes_go_to_pgvector` 答 False。
- 这三枚钉反对的正是判据要的四支拒收：在矛盾档 raise，就是它们点名的"零写"。而 R633 纸把同一件事叫"悄悄搬家"。**「零写更坏」还是「搬家更坏」是业主/总控的政策裁决，不是执行层可以在一枚文件里同时满足的两条判据。** 本席把两侧原文都摆在这儿，不代裁。
- 顺带补一刀证据：本单派工词自己引了 `_writes_go_to_pgvector` 的 docstring——「双写关着就没有 PG 腿可交行。那时把遗留腿一起关掉不是『停写』，是**零写**……判据②第二把反证刀钉的就是这一格」。也就是说，派工词在立下"四支一律显式失败"的判据时，同一张纸里就写着这枚钉的存在。二者不能同时收货。

---

## 6. 逐切片红点归因（每枚切片单独投盘、每个在册件单独跑，跑完即复原）

逐切片单跑（每枚切片单独投盘 → 每个在册件单独起一次 pytest → `finally` 立刻复原并现校 blob）。
本席第一轮那张 cumulative 表作废（成因见 §11 那枚自记的错），这张是重测的：

| 切片 | 投了什么 | r60_write | r60_parity | r625 | r633 | 量具 |
| --- | --- | --- | --- | --- | --- | --- |
| 不改（基点 45d5f55） | 无 | 17 passed | 9 passed | 23 passed | 35 passed | 10 条 / exit 1 |
| `comp`（判据④那一族） | `_undo_vector_write` 三处摘腿门 | 17 passed | 9 passed | 23 passed | **2 failed / 33 passed** | **8 条**，compensation 2→0 |
| `read`（判据①的写域半格） | `_pgvector_hits` 不吞 `vector_read_without_dual_write` | 未单跑 | 未单跑 | 未单跑 | **2 failed / 33 passed** | **9 条**，waiters 2→1 |
| `all`（四支拒收＋读腿＋补偿全投） | 11 处 edit | **1 failed / 16 passed** | **1 failed / 8 passed** | **1 failed / 22 passed** | **7 failed / 28 passed** | **7 条**，roster=0、void=0 |
| `all` 同一次跑九枚件 | 同上 | 合计 **10 failed / 175 passed / 40.04 s**；另 r58 21 passed、r59b 24 passed、r44_hot_index_chroma 18 passed、r21 两枚 23＋15 passed |||

`all` 那一行的 10 枚红点逐枚点名（与逐文件单跑的和集**完全相同**，说明这一遍没有跨文件污染）：

1. `tests/test_r60_write_path_unique_under_pgvector.py::test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write` —— 政策冲突（§5.3）
2. `tests/test_r60_predicate_terms_and_leg_parity.py::test_the_stop_write_branch_is_inside_the_pg_leg` —— 政策冲突（§5.3）
3. `tests/test_r625_chroma_write_sites_are_named_one_by_one.py::test_dropping_one_term_of_the_write_predicate_is_a_lie[dual_write_enabled]` —— 政策冲突（§5.3）
4. `tests/test_r633_dual_write_off_precondition_teeth.py::test_turning_the_switch_off_is_measured_as_a_loss_not_a_green` —— 这枚牙要求五族全在场，而 compensation 已归零
5. 同文件 `::test_dropping_the_stores_vectors_early_return_is_named` —— **候选补丁自己的缺陷**（§9 末段），不是判据冲突
6. 同文件 `::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code` —— 这枚牙把 `read_topk` 的吞点钉成在册事实
7. 同文件 `::test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have` —— 同 4
8. 同文件 `::test_answers_move_back_to_the_legacy_engine_while_the_switch_is_off` —— 这枚动态牙现跑的就是"答复由 Chroma 给"
9. 同文件 `::test_a_row_written_after_the_flip_is_undeletable_and_off_the_list_when_the_switch_is_off` —— 这枚动态牙现跑的就是"删不掉、名单里没有、且不报错"
10. 同文件 `::test_a_reupload_while_the_switch_is_off_leaves_the_previous_version_behind` —— 这枚动态牙现跑的就是"off 态上传成功且新行全进遗留腿"

⇒ 除第 5 枚是候选自身的毛病，其余 9 枚全是"在册件把现状钉成了期望"。这就是判据①与判据⑤不能同时收货的那道缝。

一句话读法：**没有任何一枚切片能只改产品码而不碰在册件。** 最干净的 `comp` 切片也要红两枚 R633 静态牙；`read` 切片红两枚（一枚静态牙＋一枚动态现跑）；四支拒收那一刀同时红两枚 R60 钉与一枚 R625 刀。

本席另记一枚在册件的脆弱面（不作为判据，只作为落地提示）：`tests/test_r633_dual_write_off_precondition_teeth.py` 的两枚静态牙（`::test_turning_the_switch_off_is_measured_as_a_loss_not_a_green`、`::test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have`）**单独跑这枚文件时是绿的，与其余八枚在册件同一次跑时是红的**——同一枚产品码、同一条命令、两种读数。本席第一轮那张"4 红"的归因表就是被这个跨文件状态污染的，已在表里改判为不可信。落地时建议把静态三面与动态现跑两枚拆成两枚文件，别让它们的读数互相依赖。

---

## 7. 若裁决"照 R633 那一侧改"，需要同批落地的在册件（逐字清单，交总控）

本席无权动这些件（写域外／禁区），此处只给逐字位置：

1. `tests/test_r625_chroma_write_sites_are_named_one_by_one.py::CHROMA_WRITE_ROSTER` —— `_write_batch` 那枚 `role="primary"` 的 `requires_false` 语义（5.1）。不改这里，`chroma_write_gate_reopens` 永不归零；改了这里，判据③"pgvector 主写时新行只许落 PG"那枚常驻钉要重写。
2. `scripts/r633_dual_write_off_precondition.py::write_site_face` / `off_state_findings` —— 量具要认得"拒收闸门"才能把 5.1／5.2 两族从"结构在场"降为"已被显式失败治过"（本单明令量具是禁区）。
3. `tests/test_r633_dual_write_off_precondition_teeth.py` —— 这枚文件把"现状"钉成了期望。候选实测红 6 枚：`::test_turning_the_switch_off_is_measured_as_a_loss_not_a_green`、`::test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have`、`::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code`、`::test_answers_move_back_to_the_legacy_engine_while_the_switch_is_off`、`::test_a_row_written_after_the_flip_is_undeletable_and_off_the_list_when_the_switch_is_off`、`::test_a_reupload_while_the_switch_is_off_leaves_the_previous_version_behind`。另有一枚 `::test_dropping_the_stores_vectors_early_return_is_named` 红在候选自己的毛病上（§9 末段），不算判据冲突。还有两枚今天仍绿、但归零 §5.1／§5.2 两族必定要动的：`::test_the_questions_that_move_back_to_the_legacy_directory_are_named`（候选保住了早退与两处 `positive_branch` 的形状，所以它没红）与 `::test_the_registered_write_site_roster_is_green_before_any_knife`（名册那一枚是 R625 的镜像，见 §5.1）。
4. `tests/test_r60_write_path_unique_under_pgvector.py::test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write` 与 `tests/test_r60_predicate_terms_and_leg_parity.py::test_the_stop_write_branch_is_inside_the_pg_leg`、`tests/test_r625_...py::test_dropping_one_term_of_the_write_predicate_is_a_lie[dual_write_enabled]` —— 这三枚是政策裁决本身（5.3），要么本单判据改窄（矛盾档仍允许遗留腿接行，只把"账"记响），要么这三枚连同它们的在册理由一起重写。**这一格必须业主/总控点头，执行层不能自己把"零写"判成合法。**
5. 契约面：新码 `vector_leg_off_but_switched` 落在 `app/rag/retriever.py::EMBEDDING_REASON_LABELS` 那一格里，`docs/api/contract-v1.md` 现取只登记端点级码（`document_index_failed`／`index_rollback_failed`），本单不改契约；若总控要把内部码也登记进契约，按文末追加纪律由总控落，本席交回的逐字句在 `docs/testing/r639-candidate-product-code.diff` 里。

---

## 8. 建议的拆单姿势（按写域与裁决权切，不按功能名切）

| 单 | 内容 | 写域 | 归零哪一族 | 需要先决条件 |
| --- | --- | --- | --- | --- |
| R639-A | 补偿调用点摘掉"要一条拿不到的腿"，`_undo_vector_write` 自己容 `mirror=None` | `app/rag/retriever.py` 三处 | `compensation_needs_a_leg_it_wont_have` 2→0 | 同批改第 7 节第 3 项里那枚静态牙 |
| R639-B | 矛盾档四支拒收（写／问删／名单／读回）＋读腿不吞拒答 | `app/rag/retriever.py` 五处 | `read_leg_waits_for_chroma_receipt` 2→1 | 第 7 节第 4 项的政策裁决 |
| R639-C | 语料腿那一半（`switched_corpus` 吞点＋`BM25Searcher.build_index` 的遗留读） | `app/rag/pg_store.py`、`app/rag/retrieval_pipeline.py` | `read_leg_waits_for_chroma_receipt` 1→0 | 新的一枚派工词（本席写域不含这两件） |
| R639-D | 让量具与名册认得"拒收闸门"，或真停写摘码 | `scripts/r633_*`、`tests/test_r625_*`（或 `app/rag/retriever.py` 写点本体） | 另两族 | 先决定"停写"与"退役"要不要并到一单 |

## 9. 判据③那八把刀（设计，未收货——写这一节时盘上没有产品码，刀无处挂） —— 🔴 已收货的那 13 枚（4 动态＋3 正控＋3 静态牙＋3 反证刀）见 §14.5，判据③的字典钉实测见 §14.10

- ①读腿：刀＝把 `_pgvector_hits` 的 `raise` 换回 `return None` ⇒ `read_topk` 的 waiter 复现、`test_answers_move_back_to_the_legacy_engine_while_the_switch_is_off` 同族复绿；正控＝`vector_read_failed`（连不上）那一枚原因仍照旧降级，在册 `tests/test_r59b_pg_read_switch.py` 不许红。
- ②问删：刀＝把拒收换回静默 `return legacy_ids, legacy_metadatas, []` ⇒ 本席新钉红；正控＝`chroma + off` 那一档 `_document_rows_by_leg` 仍一次 `collection.get(where=...)`、一条 SQL 都不发（这条正是 R625 那枚刀在管的，两枚钉在正控里必须同时绿）。
- ③名单/读回：刀＝摘掉 `list_documents` 的拒收 ⇒ 名单交回一张两腿混合或纯遗留的表；正控＝`pgvector + on`（生产现态）名单与读回仍只来自 PG。
- ④补偿：刀＝把调用点重新包进 `if mirror is not None:` ⇒ `compensation_needs_a_leg_it_wont_have` 复现 2 条；正控＝把 `written_ids and not self._writes_go_to_pgvector()` 里的判定摘成 `written_ids` ⇒ 在册 `tests/test_r625_...::test_the_compensation_delete_only_undoes_a_write_that_happened` 立刻红（证明这族的闸门与名册还活着）。
- 错误码那枚钉：把 `REASON_VECTOR_LEG_OFF_BUT_SWITCHED` 的**值**改一个字，或把**常量名**改成不以 `REASON_` 开头 ⇒ `tests/test_r21_answer_side_degradation.py::test_the_reason_labels_cover_every_stable_code` 必红（那枚钉扫的是 `vars(retriever)` 里 `REASON_` 前缀的枚枚常量，缺一行文案就红）。
- 一形必须写进落地说明：候选里总闸那句 `if not self.stores_vectors: return False` 与判定里那句**逐字相同**，`tests/test_r633_...::test_dropping_the_stores_vectors_early_return_is_named` 的 `source.count(segment) == 1` 因此炸（实测红）。落地时把总闸的早退写成不同文字（或干脆让总闸不分叉、由调用方分支），这一枚红与本单判据无关，属候选补丁自己的缺陷。

## 10. 派工词两处前提订正

1. 「错误码进在册字典（`app/common/**` 里那本错误码字典的既有机制）」——本席在 `app/common/**` 逐文件现取：那里只有 rbac／policy／audit／reliable_queue 各自散用的 `reason_code` 字符串与两枚 `DISCARD_REASON_*`，**没有向量/写库口径的错误码字典**。真正的在册字典是 `app/rag/retriever.py::EMBEDDING_REASON_LABELS`（消费点 `app/rag/retriever.py::retrieval_degradation_notice`），它的钉是 `tests/test_r21_answer_side_degradation.py::test_the_reason_labels_cover_every_stable_code`。新码进这一格才是"用既有机制"，本席候选就这么做。
2. 「R633 纸面 P1／P9 明写『要消掉必须改产品码』」——成立，但那一张纸同时把"现状"钉成了牙（第 7 节第 3 项七枚）。所以"改产品码"这一步在物理上必然连带改在册件；把这两件事写成两枚判据（①归零＋⑤两态在册件全绿）时，缺了"谁改在册件"这一格。本席据此停下来回报，不自行扩权。

## 11. 反向凭据、不可外推、与本席犯过的错

- 一枚库都没连（量具两次都是静态两面，语料面"未取数"，退出码 1 而非 0/3）、零容器、零模型、零服务、零 env 改动、零 commit/branch/push。
- 本表所有枚数来自 45d5f55 这一版盘；候选补丁是**取证投盘**，不是收货物：判据②的 on 态差分、判据⑤的两态同名件同数，本席都没跑成收货形状（原因见第 5、6、7 节）。
- 全量回归门未跑。候选不是收货物，不该占门；等裁决之后再由落地那一遍跑 `python scripts/run_gate.py`。
  （这一条与上一条都是**前一档席位**的账面：判据② 的 on 态差分已由 §14.3 交出（改前 201 passed／0 failed，改后 199 passed／2 failed，唯一两枚红＝总控签好代改的 R633 过期牙），判据⑤ 的两态同名件同数已由 §14.4 交出（两态都是 212 passed／2 failed），全量门已由 §14.8 交出并逐枚归因。）
- 本席犯过一次并发错误：两枚 runner 同抢 `app/rag/retriever.py`（一枚定向归因、一枚诊断），导致其中一轮 delete/list 切片的读数被污染、且盘上一度留下半态。已按规矩不采信那两行读数，并在每次投盘的 `finally` 里现校 blob，最后一枚读数是 `0f9eebf9…`＝基点那一份原文，`git status --porcelain` 空。
  （本条 blob 已过期：收席那一刻 `app/rag/retriever.py` 的盘上 blob ＝ `b9c0fa7d…`，基点原文 `0f9eebf9…`，逐枚盘面四枚见 §1。）
- 本席没有把任何一句派工词照抄成读数：10 条发现、五族枚数、名册 6 枚写点、红点清单，全部现取。

---

## 12. 续席复验（第二枚席位独立亲读＋亲跑，2026-10-04）

- 本席是接手的续席（同一工单 R639），只补一件事：**把 §5.3 那三枚在册钉逐字亲读**，并把量具的改前读数**重跑**一遍——总控的裁决全押在「这三枚真的存在、真的断言了这些」上，不能靠上一段的转述。
- `tests/test_r60_write_path_unique_under_pgvector.py::test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write`（亲读）：档是 `backend=indexing.PGVECTOR_BACKEND` ＋ `dual="off"`，跑 `instance.add_document("b.txt", ...)`，断言三句 `ok is True` ＋ `instance.collection.count() == 2` ＋ `len(table.rows) == 0`。docstring 原文：「判据②反证第二把的形状：开关在 pgvector 而双写关着，遗留腿必须仍写」「谁都不写是本单最贵的错：上传报成功、两库里都没有这份文档的向量」。
- `tests/test_r60_predicate_terms_and_leg_parity.py::test_the_stop_write_branch_is_inside_the_pg_leg`（亲读）：同档＋`stores=True`，断言 `_writes_go_to_pgvector() is False`、`ok is True`、`connection.statements == []`、`instance.collection.adds == [IDS]`；docstring 明写「谁把停写判定挪到 `if mirror is not None` 之外，零写当场红」。
- `tests/test_r625_chroma_write_sites_are_named_one_by_one.py::test_dropping_one_term_of_the_write_predicate_is_a_lie`（亲读，parametrize 三枚合取项）：off 档里两枚断言——先 `instance._document_rows_by_leg("a.txt")` 后 `"doc_rows" not in connection.log`；再 `instance._write_batch(..., mirror=instance._open_vector_mirror())` 后 `instance.collection.adds == [["a.txt_0"]]`，失败句原文「既没落 PG 也没落遗留腿 = 零写：客户上传的文档在两个库里都不存在」。
- 🔴 **本席新增的一格（§5.2 末句的加强）**：那枚 R625 钉不只钉写点，它把「off 态不许去问 PG」也写成了断言。⇒ §5.2 留的那条"诚实归零姿势"（让 `_document_rows_by_leg` 在 off 态也问 PG，好把只住在 PG 的旧行纳进删除集合）**同样当场红**。于是 `delete_set_blind_to_pg_only_rows` 三面全堵：改名字＝判据①禁的豁免（实测 2→0 而行为一字未改）；改行为＝红 R625；不改＝族不归零。
- 量具改前读数由本席重跑（不是转抄 §2）：命令 `.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_before2`，`exit=1`、**10 条发现**、`void=[]`、`corpus` 未取数；`revision` 现取 `45d5f559c170c6e57d4b99d1841f691494d3766a`＝基点；五族枚数 **1/2/2/3/2** 与 §2 逐族相等；写点面 **6 枚**，`verdict` 分布 `reopens_when_off` 2 ＋ `switch_independent` 4，其中 `reads_the_doc_rows_question` 为真 2 枚（`add_document::delete(ids)`、`delete_document::delete(ids)`）、`blocked_by_missing_leg` 为真 2 枚（`_undo_vector_write::delete(ids)`、`_undo_vector_write::add(documents, embeddings, ids, metadatas)`）——与 §2 那五族的落点逐枚对得上。
- 裁决用的对照表（哪一族被哪一枚钉的**哪一句**挡住，逐句点名，本席不代裁）：

| 族 | 唯一诚实的归零动作 | 第一枚会红的在册钉（具体到断言句） |
| --- | --- | --- |
| `compensation_needs_a_leg_it_wont_have` | 摘掉两枚调用点的 `if mirror is not None`，让 `_undo_vector_write` 自己容 `mirror=None`（off 态里 `written_ids and not self._writes_go_to_pgvector()` 那一支是真会执行的撤销点） | 只有 `tests/test_r633_dual_write_off_precondition_teeth.py` 的两枚静态牙；R60／R625 全绿（§6 `comp` 切片实测 17／9／23 passed） |
| `chroma_write_gate_reopens` | off 态摘掉遗留腿接行＝真停写（本单明令不做），或写前拒收 | `test_a_pg_leg_that_is_not_there_never_becomes_a_zero_write` 的 `ok is True` 与 `collection.count() == 2`；`test_the_stop_write_branch_is_inside_the_pg_leg` 的 `collection.adds == [IDS]`；R625 那枚的 `collection.adds`；名册 `requires_false=(_writes_go_to_pgvector,)`（§5.1） |
| `delete_set_blind_to_pg_only_rows` | 无（见上一格） | R625 那枚的 `"doc_rows" not in connection.log` ＋ 名册那一枚镜像命题 |
| `read_leg_waits_for_chroma_receipt` | 写域那一半（`_pgvector_hits` 不吞拒答）可做；语料那一半在 `pg_store.py`／`retrieval_pipeline.py`（射程外） | `tests/test_r633_...::test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code`、`::test_answers_move_back_to_the_legacy_engine_while_the_switch_is_off` |

- 续席没有新增投盘实验：盘上产品码仍等于基点那份（blob 见 §1 表），本席只重跑了静态量具与逐字读码。

## 13. 续席亲跑：补偿切片独立复损（2026-10-04，收席前最后一遍）

- 这一遍是本席自己投的盘，不是复述 §6：`docs/testing/r639-candidate-patchlib.py` 的 `VARIANTS["comp"]` 三处 edit（`comp_body` ＋ `comp_add_call` ＋ `comp_del_call`）投上盘 → 跑量具 → 逐枚单跑四件在册件 → `finally` 写回原字节。
- 投盘后的 diff 面：`git diff --numstat HEAD` ＝ `8 9 app/rag/retriever.py`（本席这一版基线 113,630 字节 CRLF；写回后逐字节相等，`git status --porcelain` 只剩三枚未跟踪件）。
- 量具：`.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_comp2` ⇒ `exit=1`、**8 条发现**、`roster_findings=[]`、`void=[]`；逐族 `compensation_needs_a_leg_it_wont_have` **0**、`chroma_write_gate_reopens` 1、`delete_set_blind_to_pg_only_rows` 2、`question_rehomes_to_legacy_store` 3、`read_leg_waits_for_chroma_receipt` 2。与 §6 `comp` 那行**逐枚相同**⇒ 补偿那一族可以在一毫米不碰量具、一毫米不碰名册、一字不改产品码名字的前提下归零。
- 四枚在册件（逐枚单跑，同一份切片）：`test_r60_write_path_unique_under_pgvector.py` **17 passed**、`test_r60_predicate_terms_and_leg_parity.py` **9 passed**、`test_r625_chroma_write_sites_are_named_one_by_one.py` **23 passed**、`test_r633_dual_write_off_precondition_teeth.py` **2 failed / 33 passed**。⇒ 与 §6 那行一致：**R60 两枚与 R625 全绿**，红的只有 R633 那两枚把现状钉成期望的静态牙（`::test_turning_the_switch_off_is_measured_as_a_loss_not_a_green`、`::test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have`）。
- 这一遍对本席的裁决意义：**§5.3 那个政策冲突只发生在"四支拒收"那三族上，不发生在判据④那一族上**。R639-A 单独落地时，红的只有 R633 自己的两枚牙（它们记录的正是本单要治的病），不需要业主改口径、不需要动名册、不需要动量具——这是本单里唯一一枚"现在就签得掉"的部分。

---

## 14. R639-A 已落地（总控 10-04 裁决：签 A；另两族与读腿不动三枚在册钉，转新单）

### 14.1 落盘的产品码（这一版就在盘上，等总控代提交；本席未 commit）

- 件：`app/rag/retriever.py` ＋ 新钉 `tests/test_r639_undo_survives_a_missing_pg_leg.py`。补丁逐字＝`docs/testing/r639-a-product-code.diff`（6 枚 hunk，62 增 25 删）。
- 签的是"三处"，**实际七处**。差在哪儿：只把两枚补偿调用点的腿门摘掉，off 态会出现"撤了本次新行、旧行却没有快照可放回"＝那份文档从唯一持有它的库里整个消失，**比今天更坏**。补齐这一格是判据④"撤销能力存在且被真调用"的必要前提，一处都没往别族扩：
  1. `app/rag/retriever.py::DocumentRetriever._legacy_rows_may_be_shadowed_by_pg`（新增，具名档位判定）——答的是"PostgreSQL 自称正文的住所，而那条腿被旋钮关了"那一格，与 `_writes_go_to_pgvector` 读同样两枚在册开关、答**反**的那一形；出厂默认档（`INDEX_BACKEND` 在 chroma）它为假 ⇒ 那一档的行为一字不改。一不发 SQL，二不开连接。
  2. `_undo_vector_write`：`mirror.rollback()` 包进 `if mirror is not None:` 之内——没有腿就不许把 `None.rollback()` 的 AttributeError 吞成一句"PG 事务状态未知"的假故障。
  3. `_undo_vector_write`：`stale_deleted and not snapshot` ⇒ **扣住不撤**新行，`logger.error` 带在册码。半截回滚比不回滚更糟，这一句是本单唯一新增的"说真话"出口。
  4. `add_document`：旧向量快照的闸门从"有腿"改成"有腿 ∨ 矛盾档"。读不出快照 ⇒ `VectorWriteRejectedError[vector_mirror_unavailable]`，落在删除之前，一笔都不落库。
  5. `delete_document`：同一形，把快照与 `mirror.delete` 解耦；on 态调用顺序逐字不变（先快照、再 PG 删、再遗留删）。
  6. `add_document` 的补偿调用点：摘掉 `if mirror is not None:`。
  7. `delete_document` 的补偿调用点：摘掉 `if mirror is not None:`。
- 🔴 **新造错误码＝零枚**。四支出口沿用在册那枚 `REASON_VECTOR_MIRROR_UNAVAILABLE`（`app/rag/retriever.py::EMBEDDING_REASON_LABELS` 里本来就有这一行），所以 §7 第 5 项"要总控落契约"的欠账没有增加；判据④要的"具名错误码"由在册码满足。
- 顺带一处措辞订正：原两句拒收写着"双写已开启"，在 off 态是句假话，本单改成不认档次的说法（无在册件钉这两句原文，本席现取）。

### 14.2 判据①：同一把量具，改前 10 条／改后 8 条

命令原文（两遍同一枚件，产物落仓外）：

```
.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_before2
.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_final
```

| 原因码 | 改前 | 改后 | 本单签收判据 |
| --- | --- | --- | --- |
| `compensation_needs_a_leg_it_wont_have` | 2 | **0** | ✅ 合格线里正是这一族 |
| `chroma_write_gate_reopens` | 1 | 1 | 裁为不动，转新单（§5.1：与 R625 名册读同一句话） |
| `delete_set_blind_to_pg_only_rows` | 2 | 2 | 裁为不动，转新单（§5.2＋§12：名字判据，三面堵死） |
| `question_rehomes_to_legacy_store` | 3 | 3 | 不在合格线内，原样 |
| `read_leg_waits_for_chroma_receipt` | 2 | 2 | 不在合格线内；写域那一半属 R639-B（§8） |
| 合计 | 10 | 8 | 退出码两遍都是 1（不是 2）⇒ 读数可信 |

- 结构面现取（量具自己的 JSON，不是本席的口头）：`write_sites.leg_guards[*].requires_a_leg` 两枚调用点都翻成 **false**、`leg_guards[*].guards` 交回空列表、`write_sites.sites[role=compensation].blocked_by_missing_leg` 两枚 **false**、`roster_findings=[]`、`void=[]`。
- 量具与名册本单一毫米未动（禁区照守），也没有加任何豁免：改的是产品码里那两道腿门本身。

### 14.3 判据②：on 态差分＝同名在册件两遍同数

改前那一遍在**同一枚干净检出**（`git clone -s` ＋ `checkout --detach 45d5f55`，1661 枚文件全检出，dirty 0）上跑；改后那一遍在 state① 跑。逐枚点名：

| 件 | 改前（45d5f55 干净检出） | 改后（本单货） |
| --- | --- | --- |
| `tests/test_r58_pgvector_dual_write.py` | 21 passed | 21 passed |
| `tests/test_r120_dual_write_passthrough.py` | 14 passed | 14 passed |
| `tests/test_r60_write_path_unique_under_pgvector.py` | 17 passed | 17 passed |
| `tests/test_r60_predicate_terms_and_leg_parity.py` | 9 passed | 9 passed |
| `tests/test_r625_chroma_write_sites_are_named_one_by_one.py` | 23 passed | 23 passed |
| `tests/test_r44_hot_index_chroma.py` | 18 passed | 18 passed |
| `tests/test_r44_hot_index_coverage.py` | 2 passed | 2 passed |
| `tests/test_r59b_pg_read_switch.py` | 24 passed | 24 passed |
| `tests/test_r21_answer_side_degradation.py` | 15 passed | 15 passed |
| `tests/test_r21_embedding_fail_closed.py` | 23 passed | 23 passed |
| `tests/test_r633_dual_write_off_precondition_teeth.py` | 35 passed | 33 passed ＋ **2 failed** |
| 合计（11 枚在册件） | **201 passed / 0 failed** | **199 passed / 2 failed** |

- 唯一那两枚红点＝总控已签"同批代改"的两枚过期期望，逐字改法在 §14.6。除此之外**在册件一枚没红**：`dual_write_enabled()` 为真那一格的行为确实一字未改（R58 21 枚、R60 两枚 26 枚、R625 23 枚全绿）。
- 中间过程本席一度把快照闸门扩到所有 off 态，当场红了一枚 R21 的 `test_a_successful_reupload_deletes_the_old_version_then_writes`（那枚件验的是出厂默认档"删旧与写新都要发生"）。本席判为**自己扩权**，把快照收进 `_legacy_rows_may_be_shadowed_by_pg` 之后该件复绿（15 passed，与基线同数）。这一格记在这儿，不藏。

### 14.4 判据⑤：两态亲跑，逐枚同数

- state①＝本树 `C:\Users\fengx\PycharmProjects\be-r639`（apply 未 commit，dirty 62/25，`rev-list --count 45d5f55..HEAD`＝0）。
- state②＝`git clone -s` ＋ `checkout --detach 45d5f55` 的完整检出，`.venv` 挂到主树 venv 的 Junction，**只投本单货**（`app/rag/retriever.py` ＋ `tests/test_r639_undo_survives_a_missing_pg_leg.py` ＋ `docs/testing/r639-a-product-code.diff`），投完现校：`git hash-object app/rag/retriever.py` 与 state① 逐字相等，`rev-list`=0，dirty 只有那三枚。
- 两态各跑同名 12 枚（11 枚在册件＋本单新钉），**逐枚同数**：

```
13 / 21 / 14 / 17 / 9 / 23 / 33+2F / 18 / 2 / 24 / 15 / 23        （state①）
13 / 21 / 14 / 17 / 9 / 23 / 33+2F / 18 / 2 / 24 / 15 / 23        （state②）
```

合计两态都是 **212 passed / 2 failed**，枚数相同 ⇒ 没有任何一枚钉把"此刻盘面脏不脏"当判据（事故 #96／#107 同族）。

### 14.5 判据③④：本单新钉 13 枚（`tests/test_r639_undo_survives_a_missing_pg_leg.py`）

| 角色 | 件::测试 |
| --- | --- |
| 撤销能力真在且真被调用（判据④主形） | `::test_the_undo_retracts_the_new_rows_and_backfills_the_previous_version` |
| 撤回的前提：off 态必须先读旧向量快照 | `::test_the_snapshot_is_read_before_the_legacy_delete_in_the_contradictory_state` |
| 另一形：写之前拒收，一笔都不落库 | `::test_an_unrestorable_reupload_is_refused_and_lands_nothing` |
| 错误码用在册的那枚，不新造 | `::test_the_refusal_uses_the_in_register_code_and_not_a_new_invention` |
| 正控：出厂默认档一字不改（不许多读快照、不许撤成零行） | `::test_the_factory_default_state_neither_reads_a_snapshot_nor_retracts_new_rows` |
| 正控：on 态 `rollback()` 仍是硬要求 | `::test_the_leg_is_still_rolled_back_when_the_switch_is_on` |
| 正控：没有腿不许谎报"PG 事务状态未知" | `::test_a_missing_leg_is_not_reported_as_an_unknown_pg_transaction` |
| 静态牙：调用点不再站腿门之内（`mirror`→`leg` 改名同判据） | `::test_no_compensation_call_site_is_behind_a_pg_leg_gate` |
| 静态牙：`rollback()` 必须仍被腿门包着 | `::test_the_pg_rollback_is_asked_only_of_a_leg_that_exists` |
| 静态牙：在册口径"只撤真写过的"未被稀释 | `::test_the_chroma_side_compensation_still_only_undoes_a_write_that_happened` |
| 反证刀①：把调用点重新包进腿门 ⇒ 静态牙必抓到 | `::test_knife_rewrapping_a_call_site_into_a_leg_gate_is_caught` |
| 反证刀②：把 `rollback()` 的腿门中和成 `if True` ⇒ 静态牙必抓到 | `::test_knife_unwrapping_the_pg_rollback_is_caught` |
| 反证刀③：运行时把矛盾档判定摘成恒假 ⇒ 那一读快照立刻消失 | `::test_knife_switching_the_contradictory_state_off_hides_the_snapshot_again` |

- 三把反证刀都砍在**内存里的源码副本**上（照 R625/R633 的口径），落盘 `app/**` 一个字节不动；刀②一开始本席写成"直接把 `if` 摘掉"，AST 当场 SyntaxError（留下一段悬空 `except`，什么也量不到），改成"中和成 `if True`"才量到——这一形记下来。
- 本单的腿名一律从**生产者赋值／形参**现取（`vector_mirror`、`_open_vector_mirror`），不写死 `mirror`：本席第一版只认赋值，结果 `_undo_vector_write` 的腿是**形参**交进来的，取到空集合、门永远量不到，是靠正控现读才露馅（同族病：签名与调用点两回事）。

### 14.6 需总控同批落的在册件：两枚过期期望（逐字替换句，已在影子检出实跑）

两枚都在 `tests/test_r633_dual_write_off_precondition_teeth.py`＝本单禁区，仓库里那一枚本席一字未动。下面两段就是**本席实跑过的那份文本**（从影子检出反读回来，不是草稿），逐字复制即可。

跑法（全程在 TEMP，项目历史／共享 ref／主树零动作）：`git clone -s` ＋ `git checkout --detach 45d5f55` 建影子检出 → `git apply docs/testing/r639-a-product-code.diff`（交 `Applied patch app/rag/retriever.py cleanly`，投后 blob 与 state① 同一笔 `b9c0fa7d…`）→ 只把下面两段逐字替换进**那枚影子检出里的**在册牙件（替换脚本 `ast.parse` 复校后才跑）→ `.venv\Scripts\python.exe -m pytest tests/test_r633_dual_write_off_precondition_teeth.py -q -p no:cacheprovider --no-header`。
- 读数：**35 passed / 0 failed**。对照：同一名件在未替换的 state①／state② 上是 33 passed / 2 failed ⇒ 这两段替换句**恰好**吃掉那两枚红，不多不少、不新增红。
- 同一枚影子检出再跑本单新钉 `tests/test_r639_undo_survives_a_missing_pg_leg.py` ＝ **13 passed**；两件合跑 ＝ **48 passed / 0 failed**。

1. `::test_turning_the_switch_off_is_measured_as_a_loss_not_a_green`（整枚替换，函数名不变）——断言体从五族改四族，并**当场断言被治掉的那一族不在场**：少一族＝量具坏了，多一族＝产品码没落地，两个方向都得有牙。

```python
def test_turning_the_switch_off_is_measured_as_a_loss_not_a_green(tool, roster, retriever_source,
                                                                 pg_store_source):
    """本单的核心读数：这一格现在**不能翻**，而且不许由「没发现」冒充「可翻」。

    R639-A 治掉补偿那一族之后，这一枚必须同时钉两件事：剩下的四族仍在场（少一族＝量具坏了，
    不是产品码落地），被治掉的那一族当场断言**不在场**。两个方向都缺就是空转。
    """
    reading = measure_static(tool, roster)
    assert {"chroma_write_gate_reopens",
            "delete_set_blind_to_pg_only_rows",
            "question_rehomes_to_legacy_store",
            "read_leg_waits_for_chroma_receipt"} <= reading["codes"], reading["codes"]
    assert "compensation_needs_a_leg_it_wont_have" not in reading["codes"], reading["findings"]
    assert reading["exit"] == tool.EXIT_CANNOT_FLIP
```

2. `::test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have` → 改名 `..._only_while_a_leg_gate_exists`（整枚替换）。它原来的主语（「这一族必须在场」）已被本单治掉；但它真正钉的是**量具不许把腿名写死成字面量**，那一格留着，并补成三向有牙：现取归零、改名同判据、把门包回去必须复现。

```python
def test_the_compensation_family_is_reported_only_while_a_leg_gate_exists(tool, roster,
                                                                         retriever_source,
                                                                         pg_store_source):
    """补偿那一族的判定仍从**赋值现取腿名**：有门才报；R639-A 把门摘掉之后必须归零。

    R633 立这一枚时两枚调用点都站在 `if mirror is not None:` 之内，量具必须报；R639-A 摘掉
    之后必须不报。谁把「腿」的名字写死成字面量，改名那一刀就会让它闭嘴——那一格照旧留着。
    三个方向都要有牙，缺一个都是空转：现取归零、改名同判据、把门包回去必须复现。
    """
    baseline = measure_static(tool, roster)
    assert "compensation_needs_a_leg_it_wont_have" not in baseline["codes"], baseline["findings"]

    renamed = re.sub(r"\bmirror\b", "leg", retriever_source)
    assert "leg = self._open_vector_mirror()" in renamed, "刀要改的是名字，不是生产者函数"
    reading = measure_static(tool, roster, retriever=renamed)
    assert "compensation_needs_a_leg_it_wont_have" not in reading["codes"], reading["findings"]

    target = "self._undo_vector_write(leg, [], snapshot, stale_deleted=stale_deleted)"
    eol = "\r\n" if "\r\n" in renamed else "\n"
    lines = renamed.split(eol)
    hits = [n for n, line in enumerate(lines) if line.strip() == target]
    assert len(hits) == 1, "变异没落地：调用点原文漂了，本枚牙要重取坐标"
    pad = " " * (len(lines[hits[0]]) - len(lines[hits[0]].lstrip()))
    lines[hits[0]] = pad + "if leg is not None:" + eol + pad + "    " + target
    rewired = eol.join(lines)
    back = measure_static(tool, roster, retriever=rewired)
    assert "compensation_needs_a_leg_it_wont_have" in back["codes"], back["findings"]
```

- 抄过去时有一处**别照草稿手改**：`retriever_source` 那枚 fixture 走 `read_text()`，CRLF 会被归一成 LF，所以变异里的行尾一律从字符串自取（上面这段就是这么写的）。本席最早的草稿把 target 写成了「带两行的字面量」，那一形一旦遇到 CRLF 源就匹配不到、`assert rewired != renamed` 会当场假红——影子检出实跑的是现在这一版。
- 该件模块级已 `import re`，无需新增 import（现取：那枚件的模块级 import 段里有）。
- 🔴 这两枚之外的两族与读腿＝按裁决不动，本单没碰名册、没碰量具、没加任何豁免；账面见 §14.2 的表格与 §14.7。

### 14.7 本单没收的一格（诚实记账，转新单）

- `chroma + off` 那一档的**半截静默仍在**：遗留目录读不出向量快照时（离线 `_JsonCollection` 更是物理上读不出），补偿只能"扣着不撤 ＋ 记一句在册码"，因为它没有货可放回。要治它就得改那一档的写删形状，而 R21 的 `::test_a_successful_reupload_deletes_the_old_version_then_writes` 正把"删旧与写新都要发生"钉着——与 §5.3 同族，属总控/业主裁决面，不在 A 单射程。
- 另两族（`chroma_write_gate_reopens` 1 条、`delete_set_blind_to_pg_only_rows` 2 条）、名单与读回（3 条）、读腿两半（2 条）＝按裁决原样在册，读数见 §14.2。


### 14.8 全量回归门：state① 现取 ＋ 纯基点对照跑（逐枚归因，不靠口头）

- state① 全量门（本树，apply 未 commit、货在盘）：命令原文 `python scripts/run_gate.py`（并发由脚本自选，纸上不写死 `-n`；`scripts/run_gate.py` 本席未动）。读数 **40 failed / 10847 passed / 61 skipped / 2 xfailed / exit=1**，725.83 s，自选 `-n 6`，日志 `r639_gate_clean.out`。
- 上一轮（19:55 起跑，`-n 5`）＝ 41 failed / 10846 passed，**该轮作废**：门跑到一半时本席改了源码，多出的那一枚正是本单新钉 `tests/test_r639_undo_survives_a_missing_pg_leg.py::test_knife_unwrapping_the_pg_rollback_is_caught`。两轮的其余失败集同形（同 18 枚件、同族）⇒ 这堆红与并发数无关。
- 🔴 归因不靠口头：新搭一枚**纯基点干净检出** `C:\Users\fengx\AppData\Local\Temp\r639_base`（`git clone -s` ＋ `git checkout --detach 45d5f55`；`git ls-files` ＝ 1661；porcelain 空；`git hash-object app/rag/retriever.py` ＝ `0f9eebf9…` ＝基点原文），`.venv` 同挂主树 Junction，只跑门里那 18 枚红件（清单落 `r639_fail18.txt`），同参数 `-q -p no:cacheprovider --no-header` 串行：读数 **33 failed / 448 passed / 1 xfailed**，313.30 s，日志 `r639_base_named.out`。
- 逐枚集合差（脚本现取，不是手对）：**33 枚两跑同名同形**＝本单之前就是红的；**7 枚只在本单态红**，拆开如下；反向零枚（没有一枚是「基点红、本单绿」）。

| 只在本单态红 | 件::测试 | 归因 |
| --- | --- | --- |
| 2 | `tests/test_r633_dual_write_off_precondition_teeth.py::test_turning_the_switch_off_is_measured_as_a_loss_not_a_green`、`::test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have` | 过期期望，总控已签「同批代改」。替换句原文见 §14.6，已在 TEMP 影子检出真跑回 **35 passed / 0 failed** |
| 3 | `tests/test_r387_label_ruler_teeth.py::test_lineage_site_is_derived_and_matches_the_doc_table[10]`、`::test_the_prose_under_the_table_quotes_derived_numbers`、`tests/test_r400_derived_ledger_shift_and_silence_pins.py::test_only_the_hops_that_cite_the_shifted_file_go_red` | **本单造成的行号漂移**（不是行为变更）：`app/rag/retriever.py` 被这一笔撑长，`docs/perf/r387-label-lineage-2026-09-27.md` §1 表第 10 跳那一格与表下正文里手抄的行号过期了。红句点名唯一改法＝跑 `python scripts/r387_label_lineage.py --emit-doc-cells` 重落地；目标文件在 `docs/perf/**`＝本单越域，本席没跑那条命令 ⇒ 逐字清单见 §14.9，由总控落 |
| 2 | `tests/test_r496_forbidden_pin_scope.py::test_the_real_tree_reads_its_own_construction_fingerprint`、`tests/test_r623_content_caliber_disk_pins.py::test_counter_evidence_existence_in_porcelain_is_not_evidence` | **三条腿对账型「此刻盘面脏不脏」钉**：两枚红句同一句 `闸门放掉了真改动：app/rag/retriever.py（读数 M app/rag/retriever.py）`，`candidates` 里只有这一枚是真脏（其余三枚是该件自己注入的假 porcelain）。纯基点干净检出这两枚**都是绿的**（现取，见上条）⇒ 判据是「盘上有没有真改动」，不是行为；并树那一刻该候选从 porcelain 消失 ⇒ 复绿。本周第三次同族病（把盘面脏当判据），本席不动在册件，只如实点名 |

- **40 ＝ 33 ＋ 2 ＋ 3 ＋ 2** ✓（逐枚点名，没有一类靠总数对得上糊过去）。
- 🔴 那 33 枚**不是本单造成**（同一批在纯基点干净检出里逐枚同名），但也**不等于「主树今天就是这张脸」**：本席只证明了两枚互相独立的检出（本工作树 ＋ TEMP 完整 clone）在 `45d5f55` 上同形。其中至少一枚已实明是**检出工件**：`core.autocrlf=true` 把 `migrations/0015_dataset_version_scope_columns.sql` 在新检出里 smudge 成 CRLF（盘上现取：主树 0 枚 CR、本工作树与新 clone 各 79 枚 CR），于是 `tests/test_r256_dataset_version_scope.py::test_the_bytes_on_disk_the_manifest_and_the_loader_are_one_document` 在任何新落的工作树里必红、在主树现态不复现。
  其余各枚要不要归到同一格，请总控在主树跑同名件判——本席没去主树跑（那是别席的工作面；本席只读时看见 `chroma_db/chroma.sqlite3` 与 `scripts/audit_plan_ticket_ledger.py` 已在主树 dirty，另有 R640 两枚新件未跟踪，都不是本席动作）。
- 另两枚已实名的账面（都与本单无关、都在本席禁区）：`docs/testing/run9-readout-2026-09-28.md` 那一族手抄坐标，红句一律点名唯一改法 `python scripts/r460_run9_coordinates.py --emit-doc-cells`；`docs/api/contract-v1.md` 第 114053 字节起与基点 `a7ac040` 那一版不同（`tests/test_r354_delete_audit_shares_the_owner_reader.py::test_the_current_contract_is_the_base_plus_an_appendage` 交的红）。

### 14.9 需总控落的坐标账面（逐字清单；本席未动任何在册 .md，也未跑任何落地命令）

本单一笔把 `app/rag/retriever.py` 撑长，在册账面上手抄该文件行号的三处随之过期。三处都在本席写域之外（`docs/perf/**`、`docs/deployment/**`），本席一律只交逐字清单：

1. `docs/perf/r387-label-lineage-2026-09-27.md` §1 表第 10 跳那一格——原文（现读，逐字）：

```
| 10 | 遗留引擎元数据（今天仍在服务的读路径） | `app/api/v1/chat.py:4648-4654` → `app/rag/retriever.py:1613-1614`、`:1657-1661` | `add_document(…, department` 或 `None)` → `"department": department or ""` | 默认值兜底 |
```
   现读（由量具自己算出，本席没手改任何数字；下面这一格是 `python scripts/r387_label_lineage.py --emit-doc-cells` 会落的形状）：

```
`app/api/v1/chat.py:4648-4654` → `app/rag/retriever.py:1639-1640`、`:1683-1687`
```
2. 同一文件表下正文那一枚手抄坐标（现取原文）：

```
- **空值在同一趟里换了两种写法**：`chat.py:1153` 落 `None`、`catalog.py:647` 落 `""`、`catalog.py:762` 又落 `None`、`retriever.py:1659` 落 `""`、`pg_store.py:373` 落 `""`。第 11 跳因此只能"跟着空"，不能"救回来"。
```
   红句点名：`retriever.py:1659` 已不是现读值。派生器现读的 `app/rag/retriever.py` 三枚值＝1639-1640、1683-1687、1685（其中单行那一枚＝1685），⇒ 那一处只把 `1659` 换成 `1685`，其余文字一字不动。
3. 🔴 一张**没被任何在册钉管着、却被本单撑过期**的纸：`docs/deployment/chroma-retirement-path.md`。它手抄了 7 枚 `retriever.py` 行号，本席现取逐枚对账：仍准 5 枚、**已错位 2 枚**——纸上的 `app/rag/retriever.py:1522` 现在落在本单新增的 `app/rag/retriever.py::DocumentRetriever._legacy_rows_may_be_shadowed_by_pg` 那一行，纸上的 `app/rag/retriever.py:2053` 现在落在一句注释上——`app/rag/retriever.py::DocumentRetriever.delete_document` 的 def 已被本单押后（原本各指 `_document_rows_by_leg` 与 `delete_document`）。今天不红（无钉），但 R60 停写那一单照这张纸下刀会砍错位置 ⇒ 建议那一单开工前先把这张纸的坐标改成 `文件::符号`（R638 那一族已经在治这个形）。

### 14.10 判据③ 补口：错误码改一个字⇒在册字典钉必红（已实测），与 TEMP 台账

- 这一句原本只写在 `tests/test_r639_undo_survives_a_missing_pg_leg.py::test_the_refusal_uses_the_in_register_code_and_not_a_new_invention` 的 docstring 里＝**未证之言**。今天补了实测：在影子检出投一枚一次性探针件，把在册那枚 `REASON_VECTOR_MIRROR_UNAVAILABLE` 的**值**加一个后缀，`tests/test_r21_answer_side_degradation.py::test_the_reason_labels_cover_every_stable_code` 当场交 `AssertionError`，红句点名那枚没有文案的码；不加后缀时同一枚钉照旧绿。读数：**2 passed / 0 failed**。
- 为什么这一枚只跑在 TEMP、没并进本单货，理由如实写一条（不写好看的那条）：并进去就是第 14 枚，刚取完的全量门读数（10847 passed）当场作废、要再跑一轮十二分钟。这一格的价值在「证明那句断言不是空话」，不在「多一枚常驻牙」；总控若要常驻牙，下一班补第 14 枚并连带重跑门，本席不在收席那一刻偷偷改枚数。
- TEMP 台账（四枚目录全在仓外；项目历史、共享 ref、容器、库、模型、env 一律零动作）：

| 目录 | 内容 | 用途 | 现取凭据 |
| --- | --- | --- | --- |
| `r639_base` | 纯基点完整检出（`git clone -s` ＋ `git checkout --detach 45d5f55`，porcelain 空，`git ls-files`＝1661） | §14.8 那 33 枚同名红的对照跑 | `git hash-object app/rag/retriever.py` ＝ `0f9eebf9…`（基点原文） |
| `r639_state2` | 基点＋只投本单货 | 判据⑤ 的 state② | `b9c0fa7d…`，与 state① 逐字相等 |
| `r639_verify` | 基点＋本单货（`git apply docs/testing/r639-a-product-code.diff` 交 `Applied patch app/rag/retriever.py cleanly`）＋只把 §14.6 那两段逐字替换进该检出里的 `tests/test_r633_dual_write_off_precondition_teeth.py` ＋一枚一次性探针件 | §14.6 与 §14.10 的实跑 | 投货后 `git hash-object app/rag/retriever.py` ＝ `b9c0fa7d…`（与 state①／state② 同一笔）；替换后 `ast.parse` 通过；35 passed ＋ 13 passed ＋ 探针 2 passed；仓库里那枚在册牙件一字未动 |
| `r639_before2`／`r639_final` | R633 量具的改前／改后 JSON（`--out-dir` 落仓外） | 判据① | 10 条 → 8 条；`compensation_needs_a_leg_it_wont_have` 2 → 0；退出码两遍都 1 |

### 14.11 纸落定之后的最终复跑（判据⑤ 与门归因都在这一版货上重取一遍）

- 判据⑤ 复跑（本纸与五件货全部落定之后再跑一次，免得账面写在货之前）：
  state①＝本树（` M app/rag/retriever.py`，blob `b9c0fa7d…`）跑同名 12 枚 → **212 passed / 2 failed**（53.11 s，日志 `r639_named_state1_after_doc.out`）；
  state②＝干净检出投**全部五件货**（`git status --porcelain` 与 state① 同形：一行 ` M` ＋ 五行 `??`；`rev-list --count 45d5f55..HEAD`＝0；blob 与 state① 逐字相等）跑同一串 → **212 passed / 2 failed**（52.48 s，日志 `r639_named_state2_after_doc.out`）。
  两态 passed 枚数相同 ⇒ 依旧没有任何一枚钉把「此刻盘面脏不脏」当判据；那两枚 failed 仍是总控签好代改的 R633 过期牙（落 §14.6 那两段后该件回到 35 passed，见影子检出实跑）。
- 门的归因复跑（同 18 枚件，state① 纸落定后再跑）：**40 failed / 441 passed / 1 xfailed**（274.65 s，日志 `r639_state1_18_after_doc.out`），失败**集合**与 §14.8 那轮全量门里的 40 枚**逐枚同名**（脚本集合相等判定交 True），与纯基点那 33 枚的差集恰是已点名的 7 枚，反向差集为空 ⇒ 写这纸本席没引入任何一枚新红。
- 判据① 终态复跑（纸与货都落定之后，第三遍量具）：命令原文 `.\.venv\Scripts\python.exe scripts\r633_dual_write_off_precondition.py --out-dir $env:TEMP\r639_final_after_doc` → **8 条发现**（`question_rehomes_to_legacy_store` 3／`delete_set_blind_to_pg_only_rows` 2／`read_leg_waits_for_chroma_receipt` 2／`chroma_write_gate_reopens` 1），`compensation_needs_a_leg_it_wont_have` 现取 **0 条**，exit＝1，产物 `r633-precondition-20261004T131545Z.json`。与 §14.2 那两遍同形，量具与名册依旧一字未动。
