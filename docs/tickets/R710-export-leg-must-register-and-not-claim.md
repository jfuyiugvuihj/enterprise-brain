# R710 · 导出腿 status=failed 却答复「报告文件已导出」：产物登记那一腿必须真在册

**号**：R710　**性质**：总控亲签（R694 走查环 8 未达，`Archimedes` 一手读数；与环 7 的图登记同一族病）　**基点**＝开工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树、不许 commit。

## 病形现取（走查账 `docs/testing/walkthrough-2026-10-06/ledger.json` 环 8，总控 10-06 现读）

- 后端一行：`2026-10-06 14:44:19,804 [INFO] enterprise_brain: [export] 完成 status=failed 结果 51 字`——发点在 `app/agents/orchestrator.py::`（`logger.info(f"[{name}] 完成 status=…")` 那一枚），导出腿**自报失败**、只交回 51 字。
- 但终态答复正文声称报告文件已导出（`after_approve.answer_tail` 含「📁 报告文件已导出」字样并给出 .pdf 文件名）。
- 屏侧与 API 侧对盘：`report_artifact.found=false`、`total=0`、`exported_piece=null`、`artifact_rows_after=[]`、`/api/v1/artifacts` 零枚在册；走查纸的结论是「文件已在容器盘上落出来，但产物登记那一腿交回的是 `artifact_leg_error`」。
- 环 7 同族：`chart_artifact.found=false`、`total=0`、`wait_s=151.5`，图登记那一腿也没在册（那一轮还叠着 `[data] 完成 status=failed 结果 0 字`，R703 已治 Data 腿那一半）。

## 判据（每条可失败，缺一枚判负）

1. **先取证**：交回纸必须现读点名——导出腿为什么 `status=failed`（51 字那句原文是什么、错在哪一枚 `文件::符号`）；`app/agents/tools.py::_register_artifact` 与 `app/storage/artifacts.py::register_artifact` 这两级里，登记在哪一级断的；文件在容器盘上的落点与 `ARTIFACT_DIR` 现读是否同源。**取证不支持动手的那一格，停下交回**，不许为绿造链路。
2. **登记真在册**：离线驱动一次导出（假模型、零容器、写盘只写 `tmp_path`），断言 `/api/v1/artifacts` 的账目与导出件**同一枚数**，且件型/文件名/可查回字段逐项可指认。判据形态必须是可失败读数，不许「字符串里好像有」。
3. **答复不许冒充**：产物台账零枚时，终态答复不得声称「已导出／已生成」——守卫形状照在册正例 `app/agents/nodes.py::_carry_chart_truth`／`_carry_dataset_truth`（只追加真话、不改写正文），新格另起符号名。🔴 反证牙：把台账置空 ⇒ 该钉必红并点名是哪条腿在冒充；把台账放一枚真件 ⇒ 必须闭嘴。
4. **环 7 那一半不许重复治**：图登记的在册缺口归本单取证与登记腿，Data 腿真话已由 R703 并树（`7810f73`）——本单若发现图那条腿需要改 `app/agents/tools.py` 的分析支路，只许动导出/登记支路，动分析支路即判负。
5. **不碰退役腿**：零新增 Chroma 依赖／写点；`app/rag/**` 不许动。
6. **卫兵不许坏**：`tests/test_r439_assembly_never_fakes_a_label.py`／`tests/test_r149_sse_text_pieces.py`／`tests/test_r661_trace_journal_hot_path_teeth.py`／`tests/test_r37_report_lane_worker.py` 复跑仍绿；`lint_hand_copied_coordinates --check` rc=0；`tickets_index --verify` rc=0；控制符各 0。
7. **D 门不许提前翻绿**：「报告档 100% 可查回」那一格由真窗判（`REPORT_LANE_VIA_QUEUE` 相 2 窗）；本单交付里明写「D 门仍待窗」，写成达即退回。
8. **交付**：同名件两态读数（dirty／`git worktree add --detach` 干净检出，清单逐枚相同，标「执行层自报」）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋凭据纸 `docs/testing/r710-<开工日>.md`。

## 写域（只许这些）

`app/agents/tools.py`（导出与登记支路）／`app/storage/artifacts.py`／`app/agents/nodes.py`（只许新增那枚只追加守卫）／`app/tools/**`／新增 `tests/test_r710_*.py`／`docs/tickets/R710-*.md`／`docs/testing/r710-<开工日>.md`

## 禁区

`app/api/v1/chat.py`（R702 在飞）／`app/api/v1/data.py`／`app/documents/**`／`app/rag/**`／`app/quality/**` 与评测夹具／`frontend/**`／`app/agents/orchestrator.py`（R30/R31/R33/R42/R38 那一族共抢的文件，本单不动它）／夜窗量具／容器·镜像·真模型·GPU／主树任何路径。


## 订正（总控 10-06 17:1x，据执行层 Ramanujan 一手现读，AGENTS ①：判据改动落账面）

- 🔴 本工单原文点名的键名 `ARTIFACT_DIR` **是过期账**：`rg ARTIFACT_DIR app/` 零命中。真坐标两枚＝`app/tools/export.py::EXPORT_DIR`
  （仓库根下 `static/exports`）与 `app/storage/artifacts.py::_STATIC_ROOT`，两枚同在 compose `generated:/app/static` 一枚卷上，
  不存在「写到库外」。后续一律按符号查，不许按这行抄。
- 本单交回的四件另立号承接：**R713**（编排层二次落盘语义）／**R714**（按原句认拒绝）／**R715**（图腿无 preflight 与人话）／**R716**（生产 `users.department` 全空，属业主）。
