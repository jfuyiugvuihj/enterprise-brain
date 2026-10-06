# R715 · 图（chart）那条腿在属主无部门时没有 preflight、也没有人话（R710 只治了导出腿）

**号**：R715　**性质**：总控亲签（R710 执行层停下交回件 ④）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R710 现读，凭据纸 `docs/testing/r710-2026-10-06.md` 第五节）

- R710 把导出腿拆成四张脸（写盘前问登记表／落了盘才被拒就收回孤儿字节／章节读不出报 `validation_error`／真失败报 `internal_error`），并把 Data 腿的真话守卫留给 R703（`app/agents/nodes.py::_carry_dataset_truth`，已并 `7810f73`）。
- 🔴 **图腿两条都没有**：属主无部门时它会一路走到 `ArtifactRegistry.register` 被拒，客户读到的是没有码的原句或一张白图，屏上不写「为什么没有图」。

## 判据（每条可失败）

1. 图腿拿到与导出腿同形的 preflight：登记不下就**一条字节都不落**，且终答里出现的具名格与读数面一致（离线驱动，假模型、只写 `tmp_path`）。
2. 人话守卫只许追加、不许改写正文，形状照在册正例 `app/agents/nodes.py::_carry_chart_truth`／`_carry_report_truth`，新格另起符号名；日志点名 `leg=chart`。
3. 反证牙两枚：① 置空台账 ⇒ 钉必须红并开口说人话；② 放一枚真件 ⇒ 必须闭嘴（不许与 R703／R710 的既有针认领同一格，动手前 `rg` 在册名册）。
4. 卫兵不许坏：`tests/test_r703_*.py`／`tests/test_r710_reply_never_fakes_an_exported_report.py` 复跑仍绿；`tickets_index.py --verify` rc=0；控制符各 0。
5. 交付：同名件两态读数＋凭据纸 `docs/testing/r715-<开工日>.md`。

## 写域（只许这些）

`app/agents/tools.py` 与 `app/agents/nodes.py` 里**图那一条腿**的支路（分析支路归 R703，导出支路归 R710，两者一字不许动）／新增 `tests/test_r715_*.py`／`docs/tickets/R715-*.md`／`docs/testing/r715-<开工日>.md`

## 禁区（踩线即退回）

`app/api/v1/chat.py`／`app/api/v1/data.py`（R714 写域）／`app/rag/**`／Chroma 新写点／评测夹具与夜窗量具／`frontend/**`／主树任何路径。
