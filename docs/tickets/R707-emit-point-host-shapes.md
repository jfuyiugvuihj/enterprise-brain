# R707 · 发点宿主「拿身份」的两种机制：把 R688 那枚只认一种形状的钉改成两种都算（tests-only）

**号**：R707　**性质**：总控亲签亲写（R695 并树当场把 `tests/test_r688_stage_accounts_are_landed.py` 顶红，红句点名 `RetrievalPipeline.search`；AGENTS 与 R695 判据② 都写着「它红了就说明账要跟着改口径」，这一格归总控，不归执行层）　**基点**＝开工那一刻主树 HEAD 现取（派 R695 验收时 HEAD `5984c78`）

## 病形现取（10-06 总控亲跑）

- `tests/test_r688_stage_accounts_are_landed.py::test_every_emit_point_host_accepts_a_config_argument` 只把**形参里有 `config`** 当唯一合法形状，而且只解析 `app/agents/nodes.py` 一枚文件的**模块级函数**。R695 交出两条腿以后，它有两处判不到：`app/rag/retrieval_pipeline.py::RetrievalPipeline.search` 是类方法（不在模块级 `tree.body` 里），`app/api/v1/chat.py::_rewrite_followup` 的合法形状是「端点挂载 `app/trace/spans.py::arm_turn_identity` ＋ 腿内自读 `app/trace/spans.py::current_turn_identity`」。⇒ 合法形状被当成唯一形状，并树必红。
- 同件的 `UNLANDED_STAGES` 手抄成 `("retrieve", "rewrite")`，而 `tests/test_r688_stage_accounts_are_landed.py::stage_emit_points` 现读 rewrite 已有 2 枚发点。手抄名单＝假账（计划书 §10 那类病）。

## 判据（每条可失败，量具路径一律 `文件::符号`）

1. **两种机制都算数，两条都不通才红**：`tests/test_r688_stage_accounts_are_landed.py::test_every_emit_point_host_can_reach_the_turn_identity` 遍历 `::stage_emit_points()` 现读的每一枚 `文件::符号`，凡 `::host_account_shape` 交回 `mechanism == "none"` 即红并逐枚点名。
2. **订正不是把牙磨平**：`tests/test_r707_emit_point_host_account_shapes.py::test_silent_failure_still_reads_none`（既不接 `config`、也没挂载自读 ⇒ `none`）与 `::test_removing_the_arm_call_turns_the_armed_leg_red`（摘掉挂载那一行 ⇒ 同一条腿从 `armed` 掉回 `none`、`module_arms` 转 `False`）必须都绿；后者专门排除「`armed` 是被 import 语句蒙出来的」。
3. **两条腿今天都在位**：`::test_the_real_tree_hosts_are_all_identifiable` 现取真树，要求 `mechanisms` 并集恰为 `{config, armed}`，且走 `armed` 的那一枚必须落在 `app/api/v1/chat.py::` 上、走 `config` 的必须含 `app/rag/retrieval_pipeline.py::`。
4. **发点表按现读，不登记死清单**：`::unlanded_stage_names` = `CANONICAL_STAGES` 减去 `::stage_emit_points` 现读到的段名；`assert_stage_accounts` 的默认 `unlanded` 改走它。反证 `tests/test_r688_counter_evidence_teeth.py::test_the_unlanded_boundary_pin_is_a_real_tooth` 仍须红并点名 `retrieve`（retrieve 段今天仍零枚自有发点，那是 R696 的格子）。
5. **两把尺同名同形**：`::test_def_map_names_match_the_defs_ranges_exactly` 逐文件比 `::_defs` 的符号集与 `::_def_map` 的键集，分叉即红。
6. **全程离线**：本单三枚件零容器、零模型、零库连接，写盘只写 `tmp_path`；`tests/test_r688_…` 与 `tests/test_r636_stage_coverage.py` 同名件读数照 R695 的两态清单逐枚复跑。

## 写域（只许这些）

`tests/test_r688_stage_accounts_are_landed.py`／`tests/test_r688_counter_evidence_teeth.py`（仅文档串与红句字面）／新增 `tests/test_r707_emit_point_host_account_shapes.py`／`docs/tickets/R707-*.md`／`docs/tickets/index.tsv`

## 禁区

不碰 `app/**` 与 `frontend/**`；不动 `scripts/r636_stage_coverage.py` 与 `scripts/r631_stage_sum_delta.py`（夜窗量具，R696/R697 名下）；不改评测集与判分器；不把「`config` 是唯一形状」换成「什么都不查」。

## 事故登记（同批）

- **#127**（现取 max＝126 之后）：总控自己用切片拼接改 `tests/test_r688_stage_accounts_are_landed.py`（`t[:i] + new + seg[cut:]`），把 446 行的件截成 37 行，连带 `test_r707_…`／`test_r688_…` 三枚件收集 ERROR。已 `git checkout --` 从索引恢复（20,751 B／SHA 与基点相等），本单口径改动**重做**为精确整串替换（`str.replace` 前逐枚 `count(old) == 1` 断言）。规矩补一条：改盘上一枚件，只许整串替换或编辑器通道，禁切片拼接。
- 同批第二格：`tests/test_r695_rewrite_stage_accounts.py.r695stray`（9,922 B，未跟踪）是执行层席位误写进主树的半件。对盘：主树与席树终版 SHA-256 均为 `386d00f45617cff0decba208361321115cdf6eedeef7cb73cfd7fbfd5c61dc80`（＝R695 凭据纸 §8 现取值），stray 为 `c46d3a4c7e2ff739785db9b1a6950f9b7fde39f36cd2b6825a35f8c17348ca18` ⇒ **无丢件**，残件按业主授权删除（删前沙盒模拟＋全档 `rg r695stray` 零引用）。
