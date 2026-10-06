# R695 · rewrite 段的生产发点（R51② 缺的第二条腿·送身份＋开段账）

**号**：R695　**基点**＝派工那一刻主树 HEAD 现取（本段落盘之后那一枚；产品码代次由总控在名册行点名——必须在 R677／R676 并树之后，写域含 `app/rag/retrieval_pipeline.py`）
**独占工作树**：由总控预配并告知路径，不许换树、不许碰主树。

## 现取病形（总控 10-06 12:3x 亲读，不是转述）

`CANONICAL_STAGES` 现取＝classify／rewrite／retrieve／generate／reflect（`app/common/stage_timing.py::CANONICAL_STAGES`）。R688 并树 `ecbd525` 之后 classify／generate／reflect 三段有发点，**rewrite 今天既无跨度也无身份**：

- `app/api/v1/chat.py::_rewrite_followup(session_id, user_msg)` 与 `app/rag/retrieval_pipeline.py::QueryRewriter.rewrite(question)` 两枚签名里**都没有 config／principal**；
- 两者最终都走 `app/common/model_handler.py` 的非流式 `chat()`，而 `app/trace/spans.py::stage_account`／`record_stage_event` 在 `model_handler.py` 里零枚（R690 只并了流式那一发的 `stream_options.include_usage`，已于 `c82208c` 并树 ⇒ 写域冲突已消）。
- ⇒ 直接给 rewrite 发一枚 `stage_account` 会撞「无主不记」那条规矩（写零字节＝静默失效，比没有更坏）。

## 判据（每条可失败，缺一枚判负）

1. **身份真送进去**：`_rewrite_followup` 与 `QueryRewriter.rewrite` 各加**可选**形参（`config` 或 `principal`，缺省值必须保持今天的调用形状不破），调用点把本轮 config 传下去。🔴 反证牙：把传参那一行摘掉 ⇒ 判据 2 的钉必须红并点名是哪一段没主。
2. **发点可指认**：`scripts/r636_stage_coverage.py::call_sites_of` 现读必须交回 `rewrite` 段 ≥1 枚 `文件::符号`；`tests/test_r688_stage_accounts_are_landed.py::assert_stage_accounts` 里「没落地的段必须零枚」那一格会当场红并点名——**它红了就说明账要跟着改口径，那时停下交回，不许偷偷改它凑绿**。
3. **同区间只一把尺**：rewrite 这一段今天没有第二把尺（既无 model 跨度记账也无工具跨度归段），所以发 `stage.finished` 不构成双记。🔴 若你在实现中发现同一区间已经存在别的跨度（现读取证），必须停下交回——retrieve 那一族就是这么差点双记的（等长区间进 `unresolved_pairs`，`within_one_percent` 从此永闭）。
4. **不改计时纪律**：五段计时不得阻塞热路径，在册计时钉 `tests/test_r149_sse_text_pieces.py`／`tests/test_r661_trace_journal_hot_path_teeth.py` 必须仍绿，读数逐枚贴进交付。
5. **不许翻绿 R51②**：<1% 那一格由今晚 run32／run33 的 `r631` 读数判；本单交付里明写「R51② 仍待窗」，写成达即退回。
6. **交付**：同名件两态读数（dirty／commit 后各一遍，清单逐枚相同）＋`rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋控制符各 0 枚＋坐标一律 `文件::符号`＋凭据纸 `docs/testing/r695-<开工日>.md`＋`python scripts/tickets_index.py --verify` rc=0。

## 写域（只许这些）

`app/api/v1/chat.py`／`app/rag/retrieval_pipeline.py`／`app/trace/spans.py`／`app/common/stage_timing.py`／`app/common/model_handler.py`（仅当必须，且须先取证它未被别席持有）／新增 `tests/test_r695_*.py`／`docs/tickets/R695-*.md`／`docs/testing/r695-<开工日>.md`

## 禁区（踩线即追加）

`app/agents/orchestrator.py`／`app/rag/hot_index.py`（若 R677 未结案）／`frontend/**`／`deploy/**` 与任何 `.env*`／评测夹具与判分器／`docs/handoff/**`／`docs/api/contract-v1.md`／`pyproject.toml`／`scripts/run_gate.py`／夜窗量具 `scripts/eval_*`·`r57*`·`r59*`·`r63*`·`r674*`／容器·镜像·模型动作／主树任何路径。
