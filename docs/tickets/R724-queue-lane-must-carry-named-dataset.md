# R724 · 队列道也要认得点名文件（R709 交回件·同一病的第二张脸，总控亲签）

**号**：R724　**性质**：R709 治好在场道，后台道照旧 ⇒ 另立单承接　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（R709 执行层现读，凭据纸 `docs/testing/r709-2026-10-06.md` 残留格）

- `app/api/v1/chat.py::_enqueue_ask_turn` 的载荷里没有点名文件那一格，队列侧起的工作腿拿不到 `data_filename`；在场道由 `app/api/v1/chat.py::_named_dataset_must_travel` 放行，后台道照旧丢。
- 载荷形状被 `tests/test_r37_report_lane_enqueue.py`／`tests/test_r32_lane_contract.py` 逐字段钉死 ⇒ 本单必须同时随账这两枚钉，不许绕开。

## 判据（每条可失败）

1. 带点名文件的提问走队列道 ⇒ 落库的载荷含该文件名，且工作腿读到的可见集与在场道同形（同一账号、同一文件，两道的数据集枚数逐枚相同）。
2. 无权点名文件走队列道时，拒绝码与在场道同名（不许一道 `department_scope_required`、一道静默降级），且不许落任何产物字节。
3. `tests/test_r37_report_lane_enqueue.py`／`tests/test_r32_lane_contract.py` 的逐字段钉随账改后仍绿，且新增字段由名册点名、不许放宽成「少一格也算过」。
4. 反证牙一枚：退回载荷那一格 ⇒ 本单新针当场红。
5. 交付：同名件两态读数＋凭据纸 `docs/testing/r724-<开工日>.md`＋`tickets_index.py --verify` rc=0＋控制符各 0。

## 写域（只许这些）

`app/api/v1/chat.py`（仅 `_enqueue_ask_turn` 载荷及其直接调用点）／`deploy/queue_worker.py`（仅取用该载荷那一格）／`tests/test_r37_report_lane_enqueue.py`／`tests/test_r32_lane_contract.py`（随账）／新增 `tests/test_r724_*.py`／`docs/tickets/R724-*.md`／`docs/testing/r724-<开工日>.md`

## 禁区（踩线即退回）

`app/agents/**`（R715／R723 写域）／`app/storage/datasets.py`（R714 已并）／`frontend/**`／评测夹具与夜窗量具／`docs/api/contract-v1.md` 原地改口／主树任何路径。
