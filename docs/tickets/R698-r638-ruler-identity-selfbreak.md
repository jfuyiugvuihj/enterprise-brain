# R698 · r638 棘轮尺身恒等式自断：两个分支各自丢了对侧那张表

**号**：R698　**基点**＝派工那一刻主树 HEAD 现取（由派工指针词带）　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 现取病形（总控 10-06 13:0x 亲读，不是转述）

- 尺：`scripts/r638_doc_pointer_ruler.py::ratchet_diff`。恒等式写在 `scripts/r638_doc_pointer_ruler.py::ratchet_diff` 末尾那条 assert：`cell["after"] - cell["before"] == len(cell.get("added", [])) - len(cell.get("removed", []))`。
- 🔴 病根：`grew` 那一支落袋时只带 `added`，`shrank` 那一支只带 `removed`（见同函数内 `grew.append(...)` 与 `shrank.append(...)` 两行）。于是一枚既增又删的档，恒等式右边少了减数，assert 当场自断——这不是盘面脏，是尺在骗自己。
- 现场形状（执行层 Curie／R693 交回，总控复核）：before=75／after=77／added=31 ⇒ 右边 31、左边 2，`tests/test_r638_pointer_ratchet.py` 三枚红（`test_the_stored_baseline_matches_the_rulers_own_reading`／`test_no_markdown_file_grew_its_paper_coordinates`／`test_shrink_is_named_not_silently_forgiven`）。
- `_multiset_diff` 本身是对的（`Counter(after)-Counter(before)` 与反向各算一张表），坏在调用侧扔掉了其中一张。

## 判据（每条可失败，缺一枚判负）

1. **两支都带两张表**：`grew` 与 `shrank` 落袋时必须同时携带 `added` 与 `removed`；`shifted` 已经带两张（作正例对照，不许改坏）。改完 `ratchet_diff` 的恒等式必须对每一格成立，不许用「把 assert 删掉／放宽」来灭红——删 assert＝摘牙，直接退回。
2. **新牙必须可失败**：新增 `tests/test_r698_*.py` 至少两枚——一枚喂「既增又删」的合成档面，断言 `grew` 格里 `removed` 非空且恒等式成立；另一枚把 `grew.append` 那行改回只带 `added`（盘上真改，跑完还原）⇒ 该牙必须红。读数逐枚贴进交付，标「执行层自报」。
3. **不许拿重落基线当治疗**：`docs/testing/r638-pointer-baseline.json` 与本单无关，**一枚字节都不许动**——它是 R693（在飞席 Curie）的写域，两席同文件即写域冲突；`--land`／`--check-baseline` 之类写回口子本次一概不许跑。
4. **三枚在册红必须归因清楚**：交付里给出「修尺前 vs 修尺后」同名件 `tests/test_r638_pointer_ratchet.py` 的两态读数（同树、同 HEAD 只差本单货），逐枚点名哪几枚由本单转绿、哪几枚仍是先红（先红必须写出归因符号，不许盖过去，也不许为它改判据原文）。
5. **卫兵不许坏**：改完复跑 `python scripts/lint_hand_copied_coordinates.py --check`（rc=0）与 `python scripts/tickets_index.py --verify`（rc=0）；本单不得新增任何 `文件:数字` 形态坐标，交付自带逐枚控制符（00/07/08/0b/0c）＝0 枚自证。
6. **交付**：两态同名件数字＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋凭据纸 `docs/testing/r698-<开工日>.md`＋坐标一律 `文件::符号`。

## 写域（只许这些）

`scripts/r638_doc_pointer_ruler.py`／新增 `tests/test_r698_*.py`／`docs/tickets/R698-*.md`／`docs/testing/r698-<开工日>.md`

## 禁区（踩线即退回）

`docs/testing/r638-pointer-baseline.json`（在飞席写域）／`app/**`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`scripts/run_gate.py`／`pyproject.toml`／`docs/tickets/index.tsv`／容器·镜像·模型动作／夜窗量具 `scripts/eval_*`·`r57*`·`r59*`·`r63*`（除上面点名那把尺）·`r674*`／主树任何路径。

## 这一枚为什么存在

R693 把三枚红交回总控裁（纸面 7-3），尺身在它的写域外；这一格不修，门那格永远带着「r638 需重取基线」这句假话——真实原因是尺自己算错，不是基线过期。