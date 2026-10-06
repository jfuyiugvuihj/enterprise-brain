# R703 · 分析档带着表却答「文档里没有数据」：本轮数据集必须真进 Data 腿

**号**：R703　**性质**：总控亲签（R694 前端九环走查抓出的环 7 未达，先取证再动刀）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 病形现取（席位 `Archimedes` 交付的走查账，`docs/testing/walkthrough-2026-10-06/ledger.json` 环 7）

- 问题带表：屏上自陈「本轮发问带的表：报销明细表.csv」，档位＝分析档。
- 终态答复（`after_approve.answer_tail` 逐字）：「…无法直接生成按月份统计的报销金额柱状图，因为：1. 文档中未包含实际报销数据：所有文档均为制度、流程、规范类文件，不包含具体的报销金额、月份等统计数据…」，并让客户自己去 SAP／用友导出 Excel。
- 读数：`charts_on_screen=0`、`chart_srcs=[]`、`sources_cards=0`、`steps_cards=1`、`terminal_answer_readouts=[]`；`pending_row_texts_before` 里那枚「生成图表」请求 #req-ba45／#req-af18 在该次读数里 `approved_clicked=false`。
- 🔴 本单**只治产品腿**：批准链在 `app/api/v1/chat.py`（在飞席写域），本单一格都不许碰；挂起请求没点批准不是缺陷，不许顺手"修"。

## 第一步是取证，不许先写码（交回纸必须逐条回答）

1. 分析档那一轮，数据集到底进没进 Data 腿：`app/agents/nodes.py`／`app/agents/tools.py`／`app/tools/**` 里现读取数——`报销明细表.csv` 的行与列以什么形状进上下文（全文？表头？零行？），有没有可指认的调用点（坐标一律 `文件::符号`）。
2. 若"进了但只给表头／只给前 N 行"，N 是多少、写在哪、由哪个开关决定；若"根本没进"，断点在哪一枚函数之间（点名调用链）。
3. 该答复里「所有文档均为制度类文件」这句话是谁的口径：Data 腿真的看不见 csv，还是它看见了仍按文档口径回答（两条腿的上下文在这一档怎么合并的，给代码出处）。

## 判据（每条可失败，缺一枚判负）

1. **带表那一轮必须有数据形状可指认**：离线驱动（假 `ModelHandler`／桩化模型，零真模型零容器零 GPU）一次分析档请求并附 `tests/fixtures` 里现成的 csv，断言 Data 腿拿到的上下文里含该表的表头枚数与行数读数（不是「字符串里好像有」，要能被一枚断言钉住）。
2. **不许再答「没有数据」**：同一夹具下，若数据集非空而答复走「文档中未包含实际报销数据」那一支，必须红；🔴 反证牙：把数据集喂空（盘上副本改成零行）⇒ 走「量不到」那一支并点名是哪张表零行，不许含糊拒答、不许编数据。
3. **图表那腿不许假装有图**：本轮没执行出图工具时，`charts_on_screen`／`chart_srcs` 这类屏上事实不许被文字冒充——产品侧答复不得声称"已生成图表"而没有任何可查回的件（与环 8 的 `artifact_total=0` 同族病，本单只在答复侧钉一句真话，导出件另立号）。
4. **不碰退役腿**：零新增 Chroma 依赖／写点；`app/rag/**` 只在必须且取证支持时才动，动前先停下交回。
5. **卫兵不许坏**：`tests/test_r149_sse_text_pieces.py`／`tests/test_r661_trace_journal_hot_path_teeth.py`／`tests/test_r439_assembly_never_fakes_a_label.py` 复跑仍绿；`python scripts/lint_hand_copied_coordinates.py --check` rc=0；`python scripts/tickets_index.py --verify` rc=0；控制符（00/07/08/0b/0c）各 0 枚。
6. **交付**：取证纸（上面三步的逐条回答＋现取坐标）＋同名件两态读数（dirty／`git archive` 干净检出，清单逐枚相同，标「执行层自报」）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋凭据纸 `docs/testing/r703-<开工日>.md`。判据 1-3 若取证结论是「产品码本来就对、病在夹具或档位选错」，**停下交回由总控裁**，不许改判据凑绿，也不许为绿而造新链路。

## 写域（只许这些）

`app/agents/nodes.py`／`app/agents/tools.py`／`app/tools/**`／`app/agents/evidence.py`（只许读数搬运，不许动 R699 的 claims 判定）／新增 `tests/test_r703_*.py`／`docs/tickets/R703-*.md`／`docs/testing/r703-<开工日>.md`

## 禁区（踩线即退回）

`app/api/v1/chat.py`／`app/api/v1/data.py`／`app/documents/**`／`app/rag/loader.py`／`app/rag/spreadsheets.py`（在飞席写域）／`frontend/**`／`app/quality/**` 与评测夹具／`docs/handoff/**`／`docs/api/contract-v1.md`／`pyproject.toml`／`uv.lock`／夜窗量具 `scripts/eval_*`·`r57*`·`r63*`·`r67*`／容器·镜像·**真模型调用**·GPU／主树任何路径。

## 这一枚为什么存在

走查九环里环 7「数据分析」是演示里最容易被抓的一格：客户带着一张真表提问，系统回他"文档里没有数据，请自己去 SAP 导出"。这既是 V1 的门面缺陷，也是 V2「Dashboard/Artifact 真实数据」那一格的前置。