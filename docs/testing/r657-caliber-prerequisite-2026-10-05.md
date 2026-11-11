# R657 · 首屏那一格的「落数前欠」新串，与契约 §4b／§6 两格同批（2026-10-05）

执行层席位 `Bhaskara`，工作树 `C:\Users\fengx\PycharmProjects\be-r657`，基点 `8a52c5c`（开工第一件事现取对账：现读基点＝`8a52c5cfbc83b26908039a6380fb2aa62f2746a8`，与派工词相符才动工）。本纸所有数字一律**执行层自报**（本席在本树与两枚临时干净检出上亲跑，未采信任何他人读数）。

## 一、这单补的是 R649 留下的哪一格

R649（并树 `c00d98d`）把「线上量得到首屏」那一格填平，却把三处口径串留在自己的禁区里：它的凭据纸 `docs/testing/r649-first-screen-ms-is-measurable-2026-10-04.md` §六 写明 `app/api/v1/observability.py::SLO_METRIC_CALIBER` 首屏那一格的 `prerequisite` 仍提 `wire_first_text_not_recorded`，原因不是遗漏，而是 `tests/test_r526_slot_caliber_closure.py::check_doc_agreement` 把码面那一枚字段与契约 §4b 那一行**逐字对判**——只改一边当场红，而契约当时在 R649 禁区。本单就是欠着的那一笔「必须同批」。

## 二、三处逐字落点（同一笔落，一字不分两笔）

1. **码面**：`app/api/v1/observability.py::SLO_METRIC_CALIBER` 里 `("qa", "first_text_p95_ms")` 那一枚 `prerequisite`，旧串 162 字 → 新串 314 字。旧串那一支「②产品侧 wire 事件仍不落盘（blocker `wire_first_text_not_recorded`），本格的凭据是采集器那一侧的外部观察，读数本必须这么署名」整支换掉，新串逐字为：

   > ①R453 名册要先新增一枚首屏格：`first_visible_ms` 是别的东西，拿它顶这格＝走私；②wire 首屏今天已落账也可读回（`app/api/v1/chat.py::_record_wire_first_text` 记账＋`app/api/v1/observability.py::wire_first_text_readout` 读回，R649 已并树），blocker `wire_first_text_not_recorded` 已从 §6 那本名册摘掉 ⇒ 本格不再欠「量得到」这一件；③仍欠两件才谈落数：还没有一枚按 `text` 挑第一枚的在册读数件，且样本量没到 `MIN_SLO_SAMPLES`

2. **契约 §4b**：`docs/api/contract-v1.md` 那一行的「落数前欠」格＝上面**同一串**，原地替换那一格（派工词明令允许的两形之一），逐字对判由第五节两态现跑绿收口。
3. **契约 §6**：`blockers[]` 表里 `wire_first_text_not_recorded` 那一格**不原地改**，由文末追加的一节（`## The 首屏 wire frame is booked now: ... (2026-10-05, R657)`）点名作废；那一节同时点名作废 §4b 交接表家族 B 格里的「产品仍不落 wire 事件（§6 `wire_first_text_not_recorded` 未关）」那句旧话——那一格不在本单写域，原地修留给承接 R453 名册那一格的单。

🔴 三处都不改读数面、不放宽样本门、不碰排名口径：`qa.first_text_p95_ms` 今天仍回答 `not_measurable`。

## 三、为什么 §6 只能走尾追加、不走具名差异账（现跑读数）

尺与把手一律借在册那两枚件，本单不新造：`tests/test_r645_contract_difference_ledger.py`（差异账＋形状尺）与 `tests/test_r523_cached_count_lands.py::contract_cached_note`（追加段节序与自报号）。

| 问的哪一事 | 现跑读数 |
| --- | --- |
| §4b 那一格在冻结基点 `a7ac040`（09-27）里命中几枚 | **0 枚**——那一行是 R526（09-30）之后长出来的，本就不在差异账管的「历史区」里 ⇒ 八枚逐字节前缀钉（r354 两枚＋r340／r366／r367／r373／r388／r414_b）原地替换那一格也碰不到，第五节 r653 那 18 枚在两态全绿就是这一条的凭据 |
| §6 那一格在 `a7ac040` 里命中几枚 | **1 枚** ⇒ 它在历史区里：原地改那一格＝让契约与前缀钉分家 |
| 拿 §4b 那一格去登记差异账行不行 | 该账自己的形状尺当场拒：`旧文里一枚手抄坐标都没有：账只收「把过期的手抄坐标换成运行时派生锚」这一种形状，增句／删句／改数字／改语义／改标题一律不收` |
| 拿 §6 那一格去登记差异账行不行 | 形状那一关过得去（旧格带着 `chat.py:` 那枚手抄坐标），但枚数门 `EXPECTED_DIFFERENCES_TODAY` 仍是等号 1，而在册钉 `tests/test_r653_six_nails_read_the_same_book.py::test_the_book_still_holds_exactly_one_named_difference` 钉的就是「账上仍一枚、枚数门仍等号 1」⇒ 登记第二枚必须改那两枚字面量，判据② 禁「改钉」 |
| 尾追加作废这一路有没有在册先例 | 有，同族同格：R523 那一节原文 `This section is additive, and it voids one dated sentence in the blockers[] table above`，且 `tests/test_r523_cached_count_lands.py::test_the_contract_note_keeps_the_declared_caliber` 明写「作废必须是点名作废，不是把假话抹掉装作没写过」 |

⇒ 本席一枚钉没动、差异账一格未登记：§6 走文末追加点名作废，§4b 走原地替换那一格。

## 四、本单唯一欠总控收账的两枚红（施工期那一形，逐枚同名）

原地替换 §4b 那一格按定义就不是「相对 HEAD 的纯追加」，于是两枚**拿 HEAD 比现盘**的在册钉在施工期红：

- `tests/test_r523_cached_count_lands.py::test_the_contract_note_keeps_the_declared_caliber`——红句 `契约不是纯追加：文末之前动过字（r367 同形判据）`；
- `tests/test_r645_contract_difference_ledger.py::test_counter_evidence_3_moving_the_frozen_base_forward_reddens`——红句 `三条腿都走不通的话，字面量钉就是空转：这一枚要现交出走得通的那几版`；那一刀要先现证「前移基点＋清账＋枚数门归零」这扇后门真走得通，走法是在最近 8 枚动过契约的版本里找一枚是现盘的前缀，而未并树时那 8 枚全带着旧 §4b 那一格，一枚都对不上。

**机理取证**（同一枚尺、两种盘面，本席现跑）：

| 盘面 | `contract_is_pure_append` | 刀③ 现证「走得通的版本」 |
| --- | --- | --- |
| 基点 `8a52c5c` 干净检出（未投本单） | `True` | `['b1a4760', '497ac38']` ⇒ 非空 ⇒ 该刀绿 |
| 基点干净检出＋投本单两枚在盘件（＝state②） | `False` | `[]` ⇒ 该刀红 |

这两枚红的是「HEAD 还没这一笔」那一形，不是口径分家：并树那一刻 HEAD 那版就是现盘，两枚同时回绿。**请总控并树后现跑一遍收账**：`python -m pytest tests/test_r523_cached_count_lands.py tests/test_r645_contract_difference_ledger.py -q`。本席不拔别人的牙：两枚件一字未动；差异也无需登记进具名差异账（§4b 那一格本就不在差异账的历史区，读数见第三节）。

## 五、两态数字（清单逐枚点名；执行层自报）

state① ＝本树 `be-r657` apply 未 commit；state② ＝以基点建 detached 干净检出（`%TEMP%\r657_state2`）＋只投本单两枚在盘件；解释器一律本树 `.venv`；命令一律 `-q --tb=line -p no:cacheprovider`。「改前」那一列＝本席动工前在同一棵基点树现跑。三列一律 `passed／failed`。

| 件 | 枚数 | 改前 | state① | state② |
| --- | --- | --- | --- | --- |
| tests/test_r526_slot_caliber_closure.py | 19 | 19／0 | 19／0 | 19／0 |
| tests/test_r526_counter_evidence_teeth.py | 21 | 21／0 | 21／0 | 21／0 |
| tests/test_r653_six_nails_read_the_same_book.py | 18 | 18／0 | 18／0 | 18／0 |
| tests/test_r649_first_screen_ms_is_measurable_on_the_wire.py | 14 | 14／0 | 14／0 | 14／0 |
| tests/test_r649_counter_evidence_teeth.py | 5 | 5／0 | 5／0 | 5／0 |
| tests/test_r105_slo_contract.py | 22 | 22／0 | 22／0 | 22／0 |
| tests/test_r459_supervisor_answer_leg_streams.py | 18 | 18／0 | 18／0 | 18／0 |
| tests/test_r459_ask_direct_answer_frames.py | 18 | 18／0 | 18／0 | 18／0 |
| tests/test_r533_bridge_note_is_derived.py | 12 | 12／0 | 12／0 | 12／0 |
| tests/test_r523_cached_count_lands.py | 13 | 13／0 | 12／**1** | 12／**1** |
| tests/test_r645_contract_difference_ledger.py | 15 | 15／0 | 14／**1** | 14／**1** |

合跑两本（第二本＝本席自取的半径：全仓「读 `docs/api/contract-v1.md`」的 61 枚件，工单未点名但本单一动契约全在那一把尺上）：

| 名册 | 改前 | state① | state② |
| --- | --- | --- | --- |
| 工单点名的六枚件合跑 | 99 passed／0 failed（16.52 s） | 99 passed／0 failed（14.07 s） | 99 passed／0 failed（15.70 s） |
| 读契约的 61 枚件合跑 | 1232 passed／1 xfailed／0 failed（242.13 s） | 1230 passed／1 xfailed／**2 failed**（247.53 s） | 1230 passed／1 xfailed／**2 failed**（217.50 s） |

两态同名件同数、红逐枚同名（就是第四节那两枚，一枚不多一枚不少）；判据① 的逐字对判 `test_the_contract_row_and_the_module_are_the_same_words` 两态都绿。

## 六、判据对账（逐条）

- **判据①** ：`tests/test_r526_slot_caliber_closure.py` 断言一字未改，19 枚两态全绿，含 `check_doc_agreement` 逐字对判与 `test_the_full_suite_of_checks_is_empty_on_the_shipped_tree`。
- **判据②** ：一枚钉未改、差异账一格未登记。本单唯一「让契约与前缀钉分家」的候选是 §4b 那一格，而按现跑读数它根本不在差异账的历史区里（基点 0 命中）；§6 那一格走作废声明，账上仍是一枚、枚数门仍是等号 1。
- **判据③** ：`wire_first_text_readout()` 的读数面一字未改——码面差分只有那一枚 `prerequisite` 字面块（`+4`／`-2` 行，全在 `SLO_METRIC_CALIBER` 首屏那一格内部），r649 那两枚件 14＋5 两态同数。
- **判据④** ：见第五节。

## 七、这格之后仍欠什么（本单不交数）

- `qa.first_text_p95_ms` 仍 `not_measurable`，`p95_ms` 与 `target` 都是 `None`；新串那两件（一枚按 `text` 挑第一枚的在册读数件、样本量到 `MIN_SLO_SAMPLES`）落地之前，谁也不许拿它交数。
- R453 名册那一枚首屏格仍未新增：`roster_cell` 仍空，契约那一格仍读「未在册（不许拿相近枚名走私）」。
- §4b 交接表家族 B 那句旧话已由新节点名作废，原地修未做（写域外）。
- `docs/testing/r526-slo-caliber-closure.md` 两处仍引 `wire_first_text_not_recorded` 未关：那是 R526 那班的 dated 记录、不是对外契约，本单不改别人的凭据纸。
- 归因那一格（`lane_attribution_absent`）与热集让路延迟那一格本单一字未碰。

## 八、纪律自证

- 写域只有三处：`app/api/v1/observability.py` 那一枚字段串、`docs/api/contract-v1.md` 两格（§4b 原地替换那一格＋文末追加一节）、本纸。`app/api/v1/chat.py`、`frontend/**`、评测夹具、`scripts/run_gate.py`、`pyproject.toml`、`deploy/.env.server`、`chroma_db/**`、`docs/handoff/**`、`tests/**`（含 r633／r645／r653／r523 那几族钉）一字节未动。
- 未 commit、未建分支、未 push、未起服务、未动容器、未 rebuild、未打模型、未跑全量门。
- 交付件字节形状现读：`app/api/v1/observability.py` 与 `docs/api/contract-v1.md` 均 lone LF=0、lone CR=0、无 BOM、严格 UTF-8 可解码、控制字符 `0x00/0x07/0x08/0x0b/0x0c` 枚数＝0；新串反引号 12 枚＝6 对，与成文相符（AGENTS.md 命令通道转义坑：正文一律走单引号 here-string，写完现读）。
- 新串里两枚 `文件::符号` 锚点由在册尺现读解析得到（走 `tests/test_r630_first_token_pointer_is_derived.py::anchor_resolves`，两枚都 True）；新串零枚手抄坐标、零枚量级，`tests/test_r635_surface_pointers_are_derived.py` 那把尺与 r526 的数字尺同判绿。
- 派工词预告的那一族坐标漂移红（r387／r455／r460）本席未接手、也未为它改任何纸面：两态读数里出现的红只有第四节那两枚，逐枚同名。
- 取证用的两枚临时检出（`%TEMP%\r657_prefix`＝基点未投、`%TEMP%\r657_state2`＝基点＋本单两枚件）只为本单两态读数服务，收席前已摘登记，仓内不留影子件；三枚只读探针脚本留在 `%TEMP%\r657_*.py`，不落仓。