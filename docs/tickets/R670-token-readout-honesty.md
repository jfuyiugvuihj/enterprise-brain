# R670 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R670
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `app/api/v1/chat.py`
- `app/trace/`
- `spans.py`
- `persistence.py`
- `schema.py`
- `model_calls`
- `tests/test_r670_*.py`
- `docs/tickets/R670-*.md`
- `docs/testing/r670-<今天>.md`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R38::判据（机器可验）"
抽查一问，`input_tokens/output_tokens` 非零且与 Ollama 自报一致
```

出处谓词＝`S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R38::判据（机器可验）`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

（本枚判据原文里没有点名的文件路径——落点由总控派工时给。）

## 总控亲签段（派工口径·以上「判据原文」逐字块为准）

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

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r670-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R670（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。
