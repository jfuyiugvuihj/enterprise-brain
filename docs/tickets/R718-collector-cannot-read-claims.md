# R718 · 夜窗量具 `scripts/eval_transport_ask_v2.py::transport` 读不到 `claims`（R702 交回·**C④ 的真阻塞**）

**号**：R718　**性质**：总控亲签（R702 执行层停下交回件 ②）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R702 执行层 Confucius 现读）

- 出口今天已经把 `claims` 放进 SSE 终态帧（R702 并树笔 `620aef5`），但采集器只认 `transport` 那**五枚键**，且这五枚由 `tests/test_r181_text_frame_ruler.py` 以**相等**钉死、没有 `done` 分支 ⇒ 帧里有 `claims` 也进不了读数件。
- 后果直接落到 V1 那一格：**run32／run33 量到的还是 `NOT_MEASURED`，不是 0.0**——R704 交回的分母读数口拿不到东西可数。

## 判据（每条可失败）

1. 采集器新增一枚具名 `done` 分支，把终态帧里的 `claims`／`claims_error` 原样落进窗产物（`%TEMP%\evalrun\<窗名>` 的读数件，字段名与契约一致，不许自创第二套口径）。
2. `tests/test_r181_text_frame_ruler.py` 那枚相等钉**不许摘**：按它的形状把新格登记进去或改成具名子集判（正例照 `tests/test_r504_terminal_frames_carry_data_filename.py` 今天这两笔——在册键不许少、新键只限具名、第四枚不许过）。
3. 改完必须交一枚**真读数**：拿一枚离线合成的 done 帧（含两枚 claim）走采集器，断言读数件里 `claims` 枚数＝2、字段逐枚可指认；再走一枚只带 `claims_error` 的帧，断言稳定码原样落账。
4. 🔴 测量条件变了一次的申报义务：本单并树之后**旧窗的帧账与 C④ 读数一律作废**，不许拿改前的窗顶改后的尺；凭据纸必须写清「并树前／后各是哪一扇窗」。
5. 卫兵不许坏：`tests/test_r181_text_frame_ruler.py`／`tests/test_r149_sse_text_pieces.py`／`scripts/tickets_index.py --verify` rc=0；控制符各 0；不许新增读 markdown 的用例。
6. 交付：同名件两态读数＋凭据纸 `docs/testing/r718-<开工日>.md`；C④ 由**改尺之后的下一扇窗**判，本单交付里明写「C④ 仍待窗」。

## 写域（只许这些）

`scripts/eval_transport_ask_v2.py`／`scripts/eval_frame_caliber_readout.py`（若那格读数面在这里）／`tests/test_r181_text_frame_ruler.py`（只许改钉的形状，不许摘）／新增 `tests/test_r718_*.py`／`docs/tickets/R718-*.md`／`docs/testing/r718-<开工日>.md`

## 禁区（踩线即退回）

`app/**`／`docs/api/contract-v1.md`（契约由 R719／R717 那条腿走）／`frontend/**`／`scripts/run_gate.py`／正在跑的窗的账本与分片目录／主树任何路径。

## 排期硬约束

**夜窗正在跑的时候不许动本单写域**（AGENTS ⑬：量具与窗互斥）。最早开工＝今晨窗收账之后。
