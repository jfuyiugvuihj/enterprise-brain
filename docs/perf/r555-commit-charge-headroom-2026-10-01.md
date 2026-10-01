# R555 全量门的并发自选按提交电荷收口（2026-10-01 · 总控亲做）

- **单号**：R555（判据全文＝跟进单 §141 第二节，原派 `Erdos`@`be-r535`）。
- **执行者**：🔴 **总控亲做**，不是执行层自报。改口理由：`be-r535` 已被 R562 的 42 枚改动占住（同树两单＝写域冲突），而本单只动一枚脚本＋一枚新钉，本席自己下地比排队快一个班次。原派工词不撤，按「一树一单」改由总控执行，本节就是它的交工纸。
- **落点**：`1c8c64b` 之上，改动面 `scripts/run_gate.py`（40	15	scripts/run_gate.py）＋新钉 `tests/test_r555_commit_charge_limits_the_gate.py`（188 行／8 枚）＋本纸。
- **现取时刻**：2026-10-01 23:31:50（`Get-Date` 直读）。

## 一、欠的形状（不是"参数调大点"那种欠）

`fit_workers()` 原来只问一件事：`ullAvailPhys`（物理空闲）。09-30 08:10 那一遍全量门按它选了 `-n 6`（每枚 worker ≈2 GB），起跑之后被一枚与项目无关的外来 CUDA 训练进程把**提交电荷**吃掉，xdist worker 死于 `0xe0000008`，88-89% 处一片 `E`，跑到 99% 停住、master 最后被 kill（凭据：看板 §4EE 第一节，`.tmpfix/gate_shift6.log` 199 行现读到 100% 那行仍在但**没有汇总行**）。
🔴 关键一句：**电荷耗尽是物理空闲那把尺看不见的那一类失败**。进程可以持有几 GB 已提交但不驻留的内存，页文件余额先见底，`ullAvailPhys` 还好看。

今天 22:35 又撞一次同族的、但方向相反的账：那一遍 `run_gate.py` 因宿主物理空闲被 `train.py` 压到 4 GB，自选成 **serial**（≈70 分钟）。⇒ 自选口径必须"两者取小＋把为什么说出来"，不然一头是 worker 死、另一头是一整班次被无声拖掉。

## 二、改了三处（口径全在码上，不靠自觉）

1. `free_memory_gb()` 拆成 `memory_headroom_gb()`，一次 `GlobalMemoryStatusEx` 问回 **两个数** `(物理空闲, 电荷余额)`，问不到两枚一起给 `-1.0`（不许只缺一枚、更不许拿 0.0 冒充"还有很多"）。旧名字 `free_memory_gb()` 保留成薄把手，外部读数不破。
2. `fit_workers()` 返回 `(枚数, 原因串)`：headroom 取两者**最小**，每枚按 2 GB 计、封顶 8；受限者是谁要按 `commit charge` / `free physical` 逐字点名；余额不足 4 GB 退串行，但原因串必须写"serial"加那枚真实读数。
3. `main()` 把原因串打进 `[run_gate]` 那一行（`xdist -n 2 --dist loadfile [headroom 5.0 GB, 2 GB per worker (limiter: commit charge; phys 20.0 GB, commit 5.0 GB)]` 这个形状）。🔴 留痕在**行上**不在注释里——事后归因只读得到那一行。

不变的一条（AGENTS.md 明规，本单一个字没碰）：`-n` 仍**不进** `pyproject.toml` 的 `addopts`（六枚件嵌套起 pytest，全局并行会递归扇出）；`--dist loadfile` 语义不动；反证钉不分层出门。

## 三、判据逐格对账（五格，按 §141 原文顺序）

| 格 | 结论 | 现取凭据 |
|---|---|---|
| ① 两者取小＋本机读数 | ✅ | 23:3x 现取 `memory_headroom_gb()` = **phys 15.9 GB / commit 26.2 GB** ⇒ 受限者是物理空闲 ⇒ 自选 `-n 7`；旧码在这一读数下同样是 7，**这一格在安静机上量不出差别**，所以钉不许拿"今天选了几枚"当判据，只比受限时该选几枚 |
| ② 线程上限单变量 A/B | ⚠️ **交数不交结论** | 同名子集 4 枚件（`test_data_answer_statistics`／`test_phase3_analysis`／`test_phase0_fixes`／`test_prefiltering`，51 枚），串行、同参、三遍：不设上限 **8.27 s** → 设 `OMP`/`OPENBLAS`/`MKL`/`NUMEXPR`=1 **9.17 s** → 复跑不设上限 **27.13 s**。🔴 同一臂的复跑自己漂了 3.3 倍，两臂之差整个躺在噪声带里 ⇒ **只许报"测不出差异"，不许报"上限治好了它"**（上一班两变量同改的错，本单不再犯第二次）。本机此刻有 4 枚 Agent 在跑自己的测试，这一格要出可采信的数必须**安静机** |
| ③ 摘掉电荷那一格必须红 | ✅ | 影子副本道两把，只碰 tmp、真树零写口：刀一把 `headroom = min(free_phys, free_page)` 摘成 `headroom = free_phys` ⇒ 同一 phys=20/commit=5 案例从 **2 枚变 8 枚**（这才是 09-30 那遍的病），且对照组在真源同案例报 `headroom 5.0`；刀二把"问不到数"那格的原因串摘空 ⇒ 留痕当场没话可说，真源那句 `"no answer"` 仍在盘上 |
| ④ 边界不许静默 | ✅ | 电荷余额 3.0 GB ⇒ `(1, "serial: headroom 3.0 GB is under one worker's 4 GB (limiter: commit charge; ...)")`；`GlobalMemoryStatusEx` 问不到 ⇒ `(4, "... gave no answer (phys=-1.0 GB, commit=-1.0 GB), defaulting to -n 4")`。两格都是"退让＋自报"，没有一声不吭 |
| ⑤ 本单不跑全量门 | ✅ | 只点名件串行复跑，见下节两态数字。全量门是并树后那道，不是本单的验收工具 |

## 四、两态数字（同名五件，逐枚点名）

文件清单（两遍完全同一份）：`tests/test_r555_commit_charge_limits_the_gate.py`、`tests/test_r449_nested_pytest_basetemp_contract.py`、`tests/test_r453_cloud_eval_override.py`、`tests/test_r453_nested_pytest_selection_guard.py`、`tests/test_r496_forbidden_pin_scope.py`。

- **dirty（已 apply 未 commit）**：**108 passed / 0 failed / 8 warnings / 34.63 s / rc=0**（`-p no:cacheprovider --no-header`，串行）。
- **clean（`git commit` 之后同名件复跑，落在 `75b227d`）**：**108 passed / 0 failed / 8 warnings / 55.49 s / rc=0**——与 dirty 那一遍**同数**（108），墙钟 34.63 s → 55.49 s 是这台机上 4 枚 Agent 同时在跑自己的测试，不是回归。🔴 两遍文件清单逐枚同一份，本笔不存在"只交 dirty 那一列"的欠账（`fa1cf3e` 与 09-29 R496 各撞过一次，本席不例外）。

## 五、这单不翻的格子（明写，不当成已修）

- 它**不改变**"门必须独占机器跑"这条：`fit_workers()` 只在起跑那一刻取数，起跑之后被挤掉照样会死 worker——那需要一枚按周期的看门狗，不在本单写域（`run_gate.py` 之内能不能做、该不该做，留给下一单裁）。
- 线程上限那一格在争用下**测不出**，本单不据此改任何缺省。
- 电荷余额与"每枚 worker 2 GB"这两个数是**本机经验值**，不是常数；换机器要在同一枚口径下重量一次。
