# R722 · 门那格余下 17 枚红的归因与治形（派生坐标族之外，总控亲签亲跑）

**号**：R722　**性质**：总控亲签（10-06 21:3x 亲跑，不是执行层自报）　**基点**＝开工那一刻主树 HEAD 现取（`56bcc59`）

## 读数现取

- 命令口径：主树 `.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q --no-header --tb=short` ＋ 9 枚点名件，**457.57 s**。
- 结果：**17 failed／132 passed**，rc=1。改前那笔全量门记的 19 枚里，`test_r149_sse_text_pieces` 与
  `test_r661_trace_journal_hot_path_teeth[K1]` 这**两枚在安静机器上复跑转绿** ⇒ 归因为 ⑬ 的 CPU 争用假红，
  不是被测对象。剩下 17 枚分六族，逐族根因与治形见 `docs/testing/r722-2026-10-06.md`。

## 判据（每条可失败）

1. 六族各自交出「被测对象真变了／量具自己过期／环境脏」的分栏，逐枚点名，不许用「都是同一类」含糊过去。
2. 治法只许两形：**文档再生**或**量具派生**。不许手抄数字凑绿，不许摘牙，不许把判据阈值改宽。
3. 预算类改动一律「逐枚点名」（病根处置 ⑭）：每枚值带出处与现取读数，且尺必须两头都咬（长了报、短了也报）。
4. 修完复跑同名 29 枚（含 R713／R717／R718 那批）两态读数逐枚点名；`tickets_index.py --check` 与 `--verify` rc=0。
5. 交付：凭据纸 `docs/testing/r722-2026-10-06.md`，内附「牙没摘」的逐条对照（改前后各咬什么）。

## 写域（只许这些）

`scripts/r483_empty_tables_triage.py`（爬链预算改派生）／`scripts/check_vector_wording.py`（误咬形状改按小句读）／
`tests/test_r478_*.py`／`tests/test_r516_*.py`／`tests/test_r695_*.py`（桩改打到类目标）／`tests/test_r310_*.py`（import 面棘轮随账）／
`tests/test_r276_*.py`（误咬组补一格）／`docs/tickets/R722-*.md`／`docs/testing/r722-<开工日>.md`

## 禁区

`app/**`／`frontend/**`／夜窗量具（`scripts/eval_*` 归 R718）／任何判据阈值与反证钉的存在性／`docs/api/contract-v1.md` 原地改口（归 R708／R719）。
