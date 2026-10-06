# R713 · `app/agents/orchestrator.py::_fallback_export_result` 的二次落盘语义（R710 交回，本单有权不改）

**号**：R713　**性质**：总控亲签（R710 执行层停下交回件 ①）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R710 执行层 Ramanujan 现读，凭据纸 `docs/testing/r710-2026-10-06.md` 第五节）

- 客户去点 `/api/v1/artifacts/…` 那个链接时，编排层会**再调一次** `export_report` ⇒ 改前一枚问话能写出两枚 PDF，第二枚没人登记。
- R710 已把两条腿都在写盘前叫停（孤儿字节归零），但「再调一次」这个语义本身在 R710 的禁区里，本单承接。

## 判据（每条可失败）

1. 离线驱动（假模型、零容器、只写 `tmp_path`）：同一枚问话从发问到取件走完全程，导出目录里的 PDF **枚数恰为一**，且与产物台账的枚数同数；判据形态必须是可失败读数，不许「字符串里好像有」。
2. 反证牙至少两枚：① 让第二次调用真发生一次 ⇒ 钉必须红并点名第二枚的字节路径；② 把登记腿摘掉 ⇒ 必须红（不许与 R710 那三枚针重复认领同一格，认领前先 `rg` 在册名册）。
3. 卫兵不许坏：`tests/test_r710_export_leg_registers_the_report_row.py` 复跑仍绿；`lint_hand_copied_coordinates.py --check` rc=0；`tickets_index.py --verify` rc=0；控制符各 0；坐标一律「文件::符号」。
4. 交付：同名件两态读数（dirty／`git worktree add --detach` 干净检出，清单逐枚相同）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋凭据纸 `docs/testing/r713-<开工日>.md`。

## 写域（只许这些）

`app/agents/orchestrator.py`（只许 `_fallback_export_result` 那一条腿的形状）／新增 `tests/test_r713_*.py`／`docs/tickets/R713-*.md`／`docs/testing/r713-<开工日>.md`

## 禁区（踩线即退回）

`app/api/v1/chat.py`（R717 的写域）／`app/agents/tools.py` 与 `app/storage/artifacts.py`（R710 已并，不许二次改动）／`app/rag/**`／Chroma 任何新写点／评测夹具与夜窗量具／`frontend/**`／主树任何路径。
