# R670 · R38③：`/chat` 打完模型必须落 `model_calls` 行并带原始 usage（V1 欠账格）

**基点**：开工时现取主树 HEAD 写进交付（本班投单时为 `daa12a0` 之后的最新代次）。**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 现取病形（总控 10-05 亲验，代次见看板 §4GG）

- `/ask` 那一腿有行且非零：`input_tokens/output_tokens` 读数 3955／245／467，`cached_tokens` 467／369／493。
- 🔴 `/chat` 那一腿**打完模型不落 `model_calls` 行**，`metadata` 只有 `{"worker":"doc"}`，没存原始 usage ⇒ 计划书 R38 判据③「抽查一问 `input_tokens/output_tokens` 非零且与 Ollama 自报一致」在 `chat` 这条生产主路径上**无法成立**。
- 在册旁证：`app/trace/spans.py` 自己写明「流式那一发的 `model_calls.input_tokens`/`output_tokens` 是 NULL」是事实而非缺陷——本单要治的是**整行都不落**，不是流式取不到数。若取证结论是「只差流式取数」，停下写进交付，不许把 R38③ 硬翻成达。

## 判据（每条都可失败，缺一枚判负）

1. 行为钉：走一次 `/chat`（真发射件、离线夹具，零真模型）后，`model_calls` 里**至少一枚行**，且 `input_tokens`／`output_tokens` 非 NULL 非零、与夹具里 Ollama 自报的 `prompt_eval_count`／`eval_count` **逐枚相等**。改前该钉必须当场红（先落证红，再改码）。
2. `metadata` 必须带上原始 usage 的**键名集合**（不许只留 `worker`），并有一枚钉断言「缺 `cached_tokens` 时那一格记 NULL 而不是记 0」（`app/common/model_handler.py` 在册规矩：绝不默认成 0）。
3. 🔴 **不许改契约口径来迁就实现**：`docs/api/contract-v1.md` 属禁区；若必须改口，停下写进交付由总控裁。
4. 两态复跑同名件（**不是全量门**）：本单新钉＋在册 `tests/test_r635_*`／`tests/test_r506_*`／usage 族在册件，逐枚列清单；改前／改后各一遍，一枚不许新红。窗内禁跑，见 `docs/tickets/WINDOW-2026-10-05.md`。
5. 交付含：取证结论（整行不落 vs 流式取不到，二选一，带现取读数）、写域清单、`rev-list --count <基点>..HEAD`=0、staged 空、未跟踪逐枚点名、控制符 0x00/07/08/0b/0c 各 0 枚。

## 写域（只许这些）

`app/api/v1/chat.py`／`app/trace/`（`spans.py`、`persistence.py`、`schema.py` 里与 `model_calls` 落行直接相关的符号）／新增 `tests/test_r670_*.py`／`docs/tickets/R670-*.md`／新凭据纸 `docs/testing/r670-<今天>.md`

## 禁区（踩线即退回）

`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与 `tests/test_evaluation_report.py`／`scripts/run_gate.py`／`pyproject.toml`／`deploy/.env.server`／`chroma_db/**`／任何镜像与容器动作／主树任何路径。`app/agents/nodes.py` 只在确有必要时改，且必须在交付里点名那一处符号与原因（R662 刚并树，改它要先对账）。
