# R646 取证纸 —— Chroma 退役纸的手抄坐标全部锚化（实测第三枚错位在主树那本 env）

工单：R646｜执行层席位 Aristotle 之外的新席（本席只接这一单）｜写域：
`docs/deployment/chroma-retirement-path.md` ＋ 新钉 `tests/test_r646_retirement_paper_anchors_are_derived.py`
＋ 本纸。基点 `246efb7`（开工现取 `git rev-parse HEAD` 与工单逐字对账通过，`status --porcelain` 为零，
`rev-list --count 246efb7..HEAD` 为零）。

🔴 本纸通篇不写「某点 py 冒号数字」这类形状（由新钉最后一格盯着），表格里文件与行号分栏落笔。

## 1. 改前的坐标台账（逐枚现读）

「现读那一行属于」＝本树 `246efb7` 的 AST 现读，走 `ast.parse` 逐层下钻，不 import 产品码。

| 文件 | 纸上抄的行 | 现读那一行属于 | 判定 | 改后派生锚 |
| --- | --- | --- | --- | --- |
| `app/rag/retriever.py` | 1442 | `DocumentRetriever._write_batch` 的 def | 与纸面一致 | `app/rag/retriever.py::DocumentRetriever._write_batch` |
| `app/rag/retriever.py` | 1496 | `DocumentRetriever._writes_go_to_pgvector` 的 def | 与纸面一致 | `app/rag/retriever.py::DocumentRetriever._writes_go_to_pgvector` |
| `app/rag/retriever.py` | 1522 | `DocumentRetriever._legacy_rows_may_be_shadowed_by_pg` 的 def | 🔴 错位：纸面要说 `_document_rows_by_leg`，真身 def 在 1536 | `app/rag/retriever.py::DocumentRetriever._document_rows_by_leg` |
| `app/rag/retriever.py` | 2053 | 一句注释（落在 `DocumentRetriever.document_chunks` 体内） | 🔴 错位：纸面要说 `delete_document`，真身 def 在 2087 | `app/rag/retriever.py::DocumentRetriever.delete_document` |
| `app/rag/retriever.py` | 1018 | `DocumentRetriever.__init__` 的 def（形参 `chroma_dir` 缺省 `./chroma_db`） | 与纸面一致 | `app/rag/retriever.py::DocumentRetriever.__init__` ＋ 限定词 `chroma_dir` |
| `app/rag/retriever.py` | 1027 | `__init__` 体内 `if chromadb is None:` | 与纸面一致 | `app/rag/retriever.py::DocumentRetriever.__init__` ＋ 限定词 `chromadb is None` |
| `app/rag/retriever.py` | 1110 | `__init__` 体内 `self.client = chromadb.PersistentClient(` | 与纸面一致 | `app/rag/retriever.py::DocumentRetriever.__init__` ＋ 限定词 `chromadb.PersistentClient` |
| `app/rag/indexing.py` | 50 | 模块级 `INDEX_BACKEND_DEFAULT = "chroma"` | 与纸面一致 | `app/rag/indexing.py::INDEX_BACKEND_DEFAULT` |
| `app/rag/indexing.py` | 2098 | 模块级 `def pgvector_writes_are_primary()` | 与纸面一致 | `app/rag/indexing.py::pgvector_writes_are_primary` |
| `app/rag/pg_store.py` | 175 | 模块级 `def dual_write_enabled()` | 与纸面一致 | `app/rag/pg_store.py::dual_write_enabled` |
| `app/common/backup.py` | 12 | 模块级元组 `DEFAULT_BACKUP_DIRS` 里的 `"chroma_db"` 那一格 | 与纸面一致 | `app/common/backup.py::DEFAULT_BACKUP_DIRS` |
| `scripts/rebuild_index.py` | 282 | `def open_census_store()` 的 def | 与纸面一致（纸面本来就写着符号名） | `scripts/rebuild_index.py::open_census_store` |
| `scripts/audit_vector_mirror_sets.py` | 1133 | `parse_args` 体内 `--chroma-dir` 那枚缺省 | 与纸面一致 | `scripts/audit_vector_mirror_sets.py::parse_args` ＋ 限定词 `--chroma-dir` |
| `scripts/compare_vector_recall.py` | 102 | `parse_args` 体内同一枚缺省 | 与纸面一致 | `scripts/compare_vector_recall.py::parse_args` ＋ 限定词 `--chroma-dir` |
| `scripts/diag_r162_chroma_zero_rows.py` | 63 | `parse_args` 体内同一枚缺省 | 与纸面一致 | `scripts/diag_r162_chroma_zero_rows.py::parse_args` ＋ 限定词 `--chroma-dir` |

判据① 的收尾读数：改后拿工单点名的那枚正则原文再扫这张纸，命中 **零枚**（`rg` 亲验 rc=1）。

## 2. 判据② 那一族非 .py 手抄行号（一并派生化）

| 文件 | 纸上抄的行 | 本树/主树现读 | 改后写法 |
| --- | --- | --- | --- |
| `docker-compose.yml` | 44 | 顶层键 `x-persistent-paths` 里 `- vectordb:/app/chroma_db` 那一格；经 `*persistent-paths` 只挂在 backend／worker／scheduler 三枚 service 的 `volumes:` | `docker-compose.yml::x-persistent-paths` ＋ `docker-compose.yml::volumes`，并把「哪三枚 service 挂着它」写进纸面 |
| `docs/handoff/2026-09-17-human-gates.md` | 43 | 该标题＝ `H4 仓库卫生裁定 —— 仅用户本人` | `docs/handoff/2026-09-17-human-gates.md::H4` |
| `docs/handoff/2026-09-17-human-gates.md` | 55 | 该标题＝ `H5 chroma_db 反跟踪 —— 仅用户本人，且必须等` | `docs/handoff/2026-09-17-human-gates.md::H5` |
| `docs/handoff/2026-09-17-human-gates.md` | 76 | 该标题＝ `H8 沙箱拦下的琐碎清理 —— 仅用户本人` | `docs/handoff/2026-09-17-human-gates.md::H8` |
| `deploy/.env.server`（主树，未跟踪） | 77 | 🔴 **已漂**：`INDEX_BACKEND=pgvector` 现读在第 **76** 行，第 77 行是 R586 那段注释 | 纸面改口成键名：`deploy/.env.server` 里 `INDEX_BACKEND=pgvector` 那一格 |
| `deploy/.env.server`（主树，未跟踪） | 56 | `VECTOR_DUAL_WRITE=on` 现读仍在第 56 行（未漂，但同样会漂） | 纸面改口成键名：`deploy/.env.server` 里 `VECTOR_DUAL_WRITE` 那一格 |

⇒ 工单说「实测已发现其中 2 枚错位」，指的是 .py 那一族。**非 .py 那一族本席另交一枚真错位**：主树 env 的 77 已经指到注释行上。这枚不在工单点名的四格（compose 一枚＋human-gates 三枚）里，是判据②「这类非 .py 手抄行号」那句话覆盖到的，一并改了并写进钉的射程（改口成键名，不再给行位）。

## 3. 锚化时的语义损失（就地写明，不自己编）

锚只能落到符号一级，落不到「符号体内第几行／元组里第几格」。两处按此处理，并且都在钉里按值复验：

- `app/common/backup.py` 那枚原指元组里的 `"chroma_db"` 一个元素 → 锚到 `DEFAULT_BACKUP_DIRS`，纸面句子改成「改 `app/common/backup.py::DEFAULT_BACKUP_DIRS` 那本名册」；钉里现读该元组仍含 `chroma_db`。
- 三枚 `scripts/**` 坐标原指 `parse_args` 体内那一行 `add_argument("--chroma-dir", ...)` → 锚到 `parse_args`，纸面补限定词「里 `--chroma-dir` 那枚缺省」。

其余 10 枚 .py 坐标锚化后与原文等价，判语、开关名、风险句一字未改（diff 只有 13 行换字，形状是「替换」而非「增删句子」）。

## 4. 常驻钉（新 `tests/test_r646_retirement_paper_anchors_are_derived.py`）

零 import 产品码、零 git、零盘面态。13 枚用例逐枚点名：

| 用例 | 钉的事 |
| --- | --- |
| `test_the_retirement_paper_carries_no_hand_copied_python_coordinate` | 判据①：工单那枚正则原文再扫一次，命中即红，红句带行位；顺手钉住形状本身不许被改窄/改宽 |
| `test_the_retirement_paper_carries_no_hand_copied_line_coordinate_at_all` | 判据②：`yml`/`md`/`json`/`server` 等 17 种后缀的「文件冒号数字」同样一枚不许留 |
| `test_the_shape_ruler_bites_and_names_the_line_it_bites` | 死尺前置：把坐标拆开拼进合成盘面，两把尺都必须咬、且报得出第 4/5 行 |
| `test_the_paper_is_anchored_and_every_anchor_resolves` | 锚化有货（清单 ≥15 枚，实际 18 枚唯一锚）且每一枚 AST／缩进／标题腿现读解析得到 |
| `test_a_fabricated_symbol_dies_on_the_anchor_ruler` | 锚点尺正控：符号名换成不存在的必须解析不到 |
| `test_the_delete_row_anchors_point_at_the_symbols_that_actually_delete` | 🔴 本单根因：「删除」那一格必须挂着 `_document_rows_by_leg` 与 `delete_document`，且现读 `delete_document` 体内真在问那一臂、那一臂体内真发遗留问句 |
| `test_the_cutting_markers_really_sit_inside_the_anchored_symbols` | S0/S5 的锚不许只「符号存在」：`collection.add`／`chromadb.PersistentClient`／`chromadb is None`／`stores_vectors`／`read_backend` 要在体内现读到 |
| `test_the_module_level_anchors_still_hold_the_values_the_paper_cites` | 出厂缺省仍为 `chroma`、`INDEX_BACKEND_ENV`／`DUAL_WRITE_ENV` 两名仍准、备份名册仍含 `chroma_db` |
| `test_the_compose_anchor_still_mounts_the_legacy_directory` | 命名卷 `vectordb:/app/chroma_db` 仍在 `x-persistent-paths` 块里、`volumes:` 名册里仍有 `vectordb`，且挂它的 service 恰为 backend／scheduler／worker 三枚 |
| `test_the_owner_only_gates_behind_S4_are_named_by_gate_number` | H4／H5／H8 三枚标题现读仍在场，且都写着「仅用户本人」；S4 那一格仍写着业主本人 |
| `test_the_env_knob_the_paper_cites_is_named_by_key_not_by_line` | env 那两格必须改口成键名，且旧的 77／56 两枚行号不许被抄回来 |
| `test_this_nail_never_asks_the_working_tree_whether_it_is_dirty` | 自证：本件 import 只有 `ast`/`re`/`pathlib`（＋`__future__`），无任何盘面态把手，源文自身零枚坐标 |
| `test_the_r646_evidence_paper_copies_no_coordinate` | 本纸（`docs/testing/r646-*.md`）自身零枚坐标，两把尺同判 |

🔴 反证那一句（本席真把坐标插回去过一次，不是纸面承诺）：往这张纸第 7 节之前塞回两枚旧落点——
`app/rag/retriever.py` 的那枚 1522 与 `docker-compose.yml` 的那枚 44——两把尺当场红，红句逐枚点名
「第 97 行手抄坐标」与「第 97 行手抄行号」，不是只报一句「有一枚」。随后逐字还原：还原后这枚 .md 的
sha256 与插刀前的备份同值（`C8092B3A7C69746F…`）、`git diff --numstat` 回到 13/13、工单点名那条 `rg`
复验仍零命中、本件 13 枚用例复跑全过。插刀与还原只发生在本树这枚 .md，全程未 commit、未进影子检出。

## 5. 两态数字（并树验收必交的两遍）

同名件＝上面这枚新钉 ＋ 会被这页纸影响的在册钉：`tests/test_r638_pointer_ratchet.py`（棘轮）、
`tests/test_r276_vector_wording_pin.py`（口径扫描覆盖本页）、`tests/test_r60_write_path_unique_under_pgvector.py`
＋ `tests/test_r60_rollback_drill_ledger.py` ＋ `tests/test_r60_predicate_terms_and_leg_parity.py`（这页纸的主人）、
`tests/test_r283_backup_covers_vector_table.py`、`tests/test_deployment_guards.py`、`tests/test_phase8_deployment.py`、
`tests/test_r467_delivery_gate_classification_item.py`（都读 `docs/deployment`）。

跑法只用本树 `.\.venv\Scripts\python.exe -m pytest -p no:randomly -q`。

- state①（apply 未 commit，本树脏）：**163 passed / 0 failed**，exit=0（秒数逐次不同，不当凭据，故不落纸）。
- state②（干净检出复跑同名件）：**163 passed / 0 failed**，exit=0。影子件＝`git archive` 把基点
  `246efb7` 全量落到仓外（除被跟踪的 191 MB `chroma_db` 二进制，本单不读它），再用 Python `tarfile` 解名
  （`bsdtar` 会把中文名文件啃坏，第一版影子就是这么废掉的），最后只放入本单三枚文件复跑。
- 两态逐枚同名：总枚数同为 163，每枚文件的用例数逐格相等（清单见第 9 节）；两态都零红，所以「红逐枚同名」这一格是空集。

## 6. 在册账的连带（不动别人的账）

- `docs/testing/r638-pointer-baseline.json` 里登记着本页那 15 枚身份串。按 R638 棘轮口径，**枚数变少不红、只逐枚点名**（`shrank`），所以本单不改那件基线——它在总控写域里，且更新基线只有 `scripts/r638_doc_pointer_ruler.py --write-baseline` 这一条路。留给总控并树时处置。
- 本页 §7「谁钉着这页」那一格列的是 R60 那两枚钉。R646 这枚新钉没被任何纸面名册登记，本纸即凭据；若总控要把这枚钉写进 §7，那一格属本单写域之外的自述，本席不代改（纸面判语一字不许动是判据④）。
- `docs/testing/r633-*`、`r639-*` 那两张纸里关于「1522／2053 错位」的记述属他单取证，本席不改，只在此点名：改纸之后那两枚描述成为历史账。

## 7. 零越界声明

- 未 commit、未 add、未建分支、未 push（本纸交回后由总控代提交）。
- 未碰 `app/rag/retriever.py`（R648 在治）、`app/api/v1/chat.py` 与 `app/api/v1/observability.py`（R649 在治）、`scripts/r633_*`、评测集、`frontend/**`、`docs/handoff/**`、`AGENTS.md`、`.gitignore`。
- 零模型调用、不起服务、不动容器与镜像、不跑全量门、不占 GPU。
- 主树 `C:\Users\fengx\PycharmProjects\企业智脑` 全程只读：本席对主树只做过一次读（第 2 节那两枚 env 读数），
  写入只发生在 `be-r646` 与 `%TEMP%\eb104\r646`。工单指定的解释器 `be-r646\.venv` 是指向主树 `.venv` 的
  Junction，本席现取那枚目录今日被改写的文件枚数＝**0**（连解释器自带的 `__pycache__` 都没新增），
  所以「不往主树写任何文件」这一条是真零，不只是没碰仓内文件。
- 本单产物全部落在写域三枚文件内；影子检出与编辑脚本都在 `%TEMP%\eb104\r646`，仓外。

## 8. 诚实清单（这枚钉量不到什么）

- 主树 `deploy/.env.server` 未跟踪、也不在 `be-r646` 里 ⇒ 那两格只能钉「纸面写了键名、旧行号没被抄回来」，钉不到「键现读是什么值」。翻默认的真实凭据仍在那台机器的容器里（跟进单/看板的账），不在本纸射程。
- 锚化把行级信息降成符号级：若 `__init__` 里将来出现两处 `PersistentClient` 构造，本钉仍绿。这一格靠限定词（纸面写的 `chromadb.PersistentClient` 在体内出现）兜住，兜不到「唯一」。
- R648 若把 `_document_rows_by_leg`／`delete_document` 改名，本钉当场红——那是设计意图（下刀点丢了必须响），不是假案，接班别降绿。
- 本钉只扫这一页纸 ＋ `docs/testing/r646-*.md`。全仓其余纸面的坐标由 R638 那把棘轮管，本单不越界去治。

## 9. 回填：两态读数

两枚读数跑的是同一串命令行（只用本树 venv，禁系统 anaconda）：

```
.\.venv\Scripts\python.exe -m pytest -p no:randomly -q <下面十枚同名件>
```

| 同名件 | 用例数 | state① | state② |
| --- | --- | --- | --- |
| `tests/test_r646_retirement_paper_anchors_are_derived.py`（本单新钉） | 13 | 全过 | 全过 |
| `tests/test_r638_pointer_ratchet.py`（坐标棘轮） | 14 | 全过 | 全过 |
| `tests/test_r276_vector_wording_pin.py`（口径扫描覆盖本页） | 16 | 全过 | 全过 |
| `tests/test_r60_write_path_unique_under_pgvector.py`（这页纸的主人） | 17 | 全过 | 全过 |
| `tests/test_r60_rollback_drill_ledger.py` | 25 | 全过 | 全过 |
| `tests/test_r60_predicate_terms_and_leg_parity.py` | 9 | 全过 | 全过 |
| `tests/test_r283_backup_covers_vector_table.py` | 22 | 全过 | 全过 |
| `tests/test_deployment_guards.py` | 25 | 全过 | 全过 |
| `tests/test_phase8_deployment.py` | 8 | 全过 | 全过 |
| `tests/test_r467_delivery_gate_classification_item.py` | 14 | 全过 | 全过 |
| 合计 | **163** | **163 passed** | **163 passed** |

判据① 的收尾读数（工单点名那条命令，本树现取）：

```
rg -o "[A-Za-z0-9_./-]+\.py:[0-9]+" docs/deployment/chroma-retirement-path.md   # 零命中（rc=1）
```

纸面卫生：改后整页 101 行仍是 CRLF、无 BOM、控制字符（00/07/08/0b/0c）枚数＝0、反引号枚数由 218 变 226（增的 8 枚全是新增行内码，成对）；
diff 只有 13 行换字，`git diff --numstat`＝13/13，没有一行是整句增删。
