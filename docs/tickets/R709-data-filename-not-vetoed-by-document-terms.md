# R709 · 带表提问被 `document_terms` 否决：`data_filename` 进不了路由，可见集退化成全量

**号**：R709　**性质**：总控亲签承接单（R703 并树后交回的第 1 格，Lagrange 一手取证）　**基点**＝开工那一刻主树 HEAD 现取　**执行时机**：🔴 必须排在 R702 并树之后——写域含 `app/api/v1/chat.py`，该文件此刻归 Schrodinger（R702）。

## 病形现取（R703 凭据纸 §一 与 §六 第 1 格，`docs/testing/r703-2026-10-06.md`）

- `app/api/v1/chat.py::_should_use_data_context` 里「报销」落进 `document_terms`，于是把本轮带来的 `data_filename` 判成不用；连带 `app/api/v1/chat.py::route_main` 的 `has_data` 取数与 `_authorized_dataset_files` 退化成全量可见。
- 后果两格：① 客户带着表问，分析档答「文档里没有数据」（R703 已在 Data 腿补了真话守卫，但**路由那一半还在**）；② 可见集退化＝越权面（C 门「越权 0 条」那格的真实风险，不是账面风险）。

## 判据（每条可失败，缺一枚判负）

1. **先取证后动刀**：交回纸必须现读点名 `document_terms` 里到底哪一枚词命中、命中之后否决发生在哪两行之间（`文件::符号`），并给出「带表 + 问句含制度词」这一形的最小复现（离线夹具，零真模型）。
2. **路由改口**：本轮 `data_filename` 非空时，`has_data` 必须为真且走 Data 腿；`document_terms` 只许影响「要不要额外检索文档」，**不许**否决已经点名的数据集。判据形态＝离线驱动一次 `/chat`，断言终态件里 Data 腿读数在位（不许用「答复里好像有数字」当判据）。
3. **可见集不许退化**：带 `data_filename` 的那一轮，`_authorized_dataset_files` 交回的集合必须是该文件（或其授权子集），不许是全量。🔴 反证牙：把请求换成一枚无权访问的文件名 ⇒ 必须走在册错误码那一支并点名，不许静默放宽。这枚牙是 C 门的牙，摘掉即退回。
4. **不许碰别的格**：`app/agents/**`（R703 刚并）、`app/documents/**`、`app/rag/**`、`frontend/**`、`app/quality/**` 一律不动；`chat.py` 里 claims 出口那一格归 R702，本单不许顺手改（两单混账＝判负）。
5. **卫兵不许坏**：`tests/test_r149_sse_text_pieces.py`／`tests/test_r459_ask_direct_answer_frames.py`／`tests/test_r379_route_tail_branches_are_gated.py`／`tests/test_r64_row_scope_error_codes.py`／`tests/test_r65_two_path_error_codes.py`／`tests/test_r178_dataset_visibility_faces.py` 复跑仍绿，读数逐枚贴进交付；`lint_hand_copied_coordinates --check` rc=0；`tickets_index --verify` rc=0；控制符各 0。
6. **交付**：同名件两态读数（dirty／`git worktree add --detach` 干净检出各一遍，清单逐枚相同，标「执行层自报」）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋凭据纸 `docs/testing/r709-<开工日>.md`。执行层不得 commit。

## 写域（只许这些）

`app/api/v1/chat.py`（只 `_should_use_data_context`／`route_main` 的 `has_data`／`_authorized_dataset_files` 三处及其直接调用点）／新增 `tests/test_r709_*.py`／`docs/tickets/R709-*.md`／`docs/testing/r709-<开工日>.md`

## 禁区

`docs/api/contract-v1.md`（R702 在飞）／`app/agents/**`／`app/documents/**`／`app/rag/**`／`app/quality/**` 与评测夹具／`frontend/**`／`app/trace/spans.py`／夜窗量具／容器·镜像·模型·GPU／主树任何路径。
