# R699 · 答案件带上 claims（C④「零分母的 0」变有牙的唯一正解·判分器一字节不动）

**号**：R699　**基点**＝派工那一刻主树 HEAD 现取（由派工指针词带）　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 现取病形（总控 10-06 13:3x 亲读，不是转述）

- 判分器**今天就会算**：`app/quality/eval.py` 现读取 `answer.get("claims") or []`，再按每条的 `supported` 布尔分 supported／unsupported，报 `provenance.unsupported_claims` 与 `unsupported_claim_rate`；它自己的注释把真相写在那儿——「有没有出处这个布尔，因为采集器从不交 claims，per 行 evidence_coverage 与它同值」。
- 采集侧也只抄不造：`scripts/collect_evaluation_answers.py` 对 `claims`／`confidence`／`confidence_label` 三枚**可选键**只做「响应里有就带走」。
- 答案契约里没有 `claims` 这一格：`app/agents/contracts.py` 现取只有 `confidence_label`（同族还有 `app/agents/evidence.py`）。⇒ 三窗 315 行带 `claims` 键 **0 行** ⇒ `unsupported_claim_rate=0.0` 是**没有分母的 0**，不是「没有幻觉」。路线图 §9 判据 2 明写这一格必须先治好，V1 才叫完成。

## 判据（每条可失败，缺一枚判负）

1. **claims 逐条原子化**：答案件必须带 `claims`，每条至少含①断言文本②`supported` 布尔③指认到具体证据（在册 `chunk_id`／文档号那一形，不许只写「有出处」三个字）。🔴 `supported` 只能由**本轮检索到的证据**决定；拿「答案里出现引用标记就算 supported」当实现＝把 0 换成 1 的假账，直接退回。
2. **牙必须咬得住两形**：新增 `tests/test_r699_*.py` 至少三枚——①喂一条无证据支撑的断言 ⇒ `provenance.unsupported_claims` 非空且 `unsupported_claim_rate > 0`；②把所有 `supported` 强置 True（盘上真改，跑完还原）⇒ ①那枚必须红并点名是哪条断言被洗白；③把 `claims` 清空 ⇒ 必须有一枚钉当场拒绝「零分母翻绿」并写明 `NOT_MEASURED`／零分母，不许交 0.0 冒充达标。
3. **判分器与量具只读**：`app/quality/eval.py`／`app/quality/runner.py`／`scripts/collect_evaluation_answers.py`／评测夹具（含 `tests/fixtures/business_evaluation_100.jsonl`）与 `scripts/` 里 `r460`·`r57*`·`r59*`·`r63*`·`r67*` 各尺**一字节都不许改**。判据 2 的三枚牙必须全部在「产品侧交没交 claims」这条线上变红，靠改尺变绿＝退回。
4. **不许宣布 C④ 达**：真读数今晚 run32／run33 才有（窗内禁并树）。交付里 C④ 一律写「**码在树＋分母待窗**」，写成「达」即退回；离线只用合成夹具证明形状与计数承重，不代表检索质量（反假账第 3 条）。
5. **热路径与不冲突**：claims 的组装不得阻塞流式首字（在册钉 `tests/test_r149_sse_text_pieces.py` 与 `tests/test_r661_trace_journal_hot_path_teeth.py` 必须仍绿，读数逐枚贴进交付）；🔴 写域里若发现唯一可行的落点其实落在在飞席 Bacon／R695 的写域（`app/api/v1/chat.py`／`app/trace/spans.py`／`app/rag/retrieval_pipeline.py`／`app/common/model_handler.py`／`app/common/stage_timing.py`），**停下回报**，不许跨席写。
6. **交付**：同名件两态读数（dirty／commit 后各一遍，清单逐枚相同）＋`git rev-list --count <基点>..HEAD`＋未跟踪逐枚点名＋控制符 00/07/08/0b/0c 各 0 枚＋坐标一律 `文件::符号`（禁 `文件:数字`）＋凭据纸 `docs/testing/r699-<开工日>.md`＋`python scripts/tickets_index.py --verify` rc=0。

## 写域（只许这些）

`app/agents/contracts.py`／`app/agents/evidence.py`／`app/agents/nodes.py`（仅当取证证明必须在此，且不得碰 R695 那五枚文件）／新增 `tests/test_r699_*.py`／`docs/tickets/R699-*.md`／`docs/testing/r699-<开工日>.md`

## 禁区（踩线即退回）

判分器与评测夹具（见判据 3）／`app/api/v1/chat.py`／`app/trace/spans.py`／`app/rag/retrieval_pipeline.py`／`app/common/model_handler.py`／`app/common/stage_timing.py`（在飞席 R695 写域）／`app/rag/hot_index.py`／`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／`scripts/run_gate.py`／`pyproject.toml`／`docs/tickets/index.tsv`／容器·镜像·模型动作／主树任何路径。

## 这一枚为什么存在

C④ 记了五班「量不到（零分母）」，而上一班把它写成 `unsupported_claim_rate=0.0` 的绿字挂在验收表里——那是这台机上最贵的一种假账。判分器早就写好了，缺的只是产品侧不肯交 `claims`。