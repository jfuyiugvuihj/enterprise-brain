# R690 · `/chat` 流式那一发的 usage opt-in（R38③ 的真达）

**号**：R690　**基点**：现取主树 HEAD（派工时写进名册）
**写域**：`app/common/model_handler.py`／新增 `tests/test_r690_*.py`／`docs/tickets/R690-*.md`／`docs/testing/r690-<开工日>.md`
**禁区**：`app/api/v1/chat.py`（R670 刚落树 `f522b04`，本单不许回头改）／`app/agents/nodes.py`（R688 在飞）／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与 `tests/test_evaluation_report.py`／夜窗量具（`scripts/eval_*`／`r57*`／`r59*`／`r63*`／`r674*`）／`pyproject.toml`／`deploy/.env.server`／任何容器镜像模型动作／主树任何路径。

## 现取病形（总控 10-06 亲验）

R670 已让 `/chat` 落 `model_calls` 行，但 `input_tokens`／`output_tokens` **两枚计数仍是 NULL**。缺的那一格在 `app/common/model_handler.py::ModelHandler.chat`：它没给流式请求带 `stream_options.include_usage`。旁证两处：`app/agents/nodes.py` 里那句「`stream_options.include_usage` 是 R149b 具名的第二条硬前置（计量不许回 NULL）」与 `app/trace/spans.py` 抬头那条「流式那一发的 model_calls 计数是 NULL」的在册说明；`app/orchestrator` 那一腿 `app/agents/orchestrator.py` 早已带 `{"stream_options": {"include_usage": True}}`，`/chat` 这一腿没带——**同仓两条道，一条有计量一条没有**。

## 判据（每条可失败，缺一判负）

1. 行为钉：`ModelHandler.chat` 在流式且调用方**没有**自带 `stream_options` 时才补 `{"include_usage": True}`（调用方已写就不越俎代庖，口径照 `app/agents/nodes.py` 那一处现读，不许另造规则）。
2. 行为钉：末帧 usage 进 `model_calls` 的 `input_tokens`／`output_tokens`，值**逐枚等于**夹具里 Ollama 自报的 `prompt_eval_count`／`eval_count`；改前该钉必须当场红（先落证红再改码）。
3. 反证牙：拿不到 usage 的那一形必须记 **NULL 而不是 0**（`app/common/model_handler.py` 在册规矩「绝不默认成 0」），把这格折成 0 ⇒ 牙红。
4. 🔴 不许改契约迁就实现：`docs/api/contract-v1.md` 属禁区；若取证发现必须改口，停下写进交付由总控裁。
5. 取证结论必须逐枚点名「`/chat` 现在到底缺哪一格」：opt-in 没带／末帧没解析／解析了没落库，三选一，带现取读数与 `文件::符号`。不许写「基本打通」。
6. R38③ 翻绿**不由本单宣布**：本单交码与离线钉，翻绿要一扇真窗抽查一问（run32 之后）。交付里明写「R38③ 待窗」，写成达即退回。
7. 同名件两态读数（清单逐枚相同）＋未跟踪逐枚点名＋控制符 0 枚＋坐标一律 `文件::符号`。

**派工词只送指针**：读 `docs/tickets/R690-*.md` 照做。