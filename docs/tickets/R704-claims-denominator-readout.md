# R704 · 把 C 门第四格的「零分母」做成可退出码的读数口（量具，不是新判据）

**号**：R704　**性质**：总控亲签亲写（窗前提速单：不接这一枚，今晚两扇窗仍会把「没有分母的 0」读成达标）　**基点**＝开工那一刻主树 HEAD 现取

## 病形现取

- `app/quality/eval.py::evaluate_provenance` 算的是「带 unsupported 断言的行数 ÷ 行数」，它不区分两形：每行都带 claims 且无一不被支撑，与根本没有一行带 claims。
- 昨夜 run31 实测：`%TEMP%\evalrun\run31-answers.jsonl` 105 行里带 `claims` 键 **0 行**，而 `run31-quality.json` 的 `unsupported_claim_rate` ＝ `0.0`。⇒ 在册那句「unsupported_claim_rate 五连 0」是**没有分母的 0**，不是没有幻觉。
- 出口那一腿（R702）没并之前，今晚 run32／run33 仍会是这个形状；没有读数口的话，这一格还会被抄成绿。

## 判据（每条可失败）

1. **两形分开交回**：`scripts/r704_claims_coverage_readout.py::tally` 必须逐枚给出 rows／rows_with_claims_key／rows_with_claims_items／claims_supported／claims_unsupported／rows_with_unsupported／denominator（MEASURED 或 NOT_MEASURED），并把判分器的 `unsupported_claim_rate` 与当场派生的比率并排列出（不相等就点名 false，不许覆盖）。
2. **退出码口径**：0＝MEASURED；3＝NOT_MEASURED（行在而 claims 全空或缺键）；2＝窗件读不到。🔴 反证牙：拿昨夜 run31 真件跑一次必须 rc=3 且 `rows_with_claims_key=0`（10-06 现取已验：105 行／0 行／rc=3）；把同一份件里任意一行的 claims 填上非空列表⇒ rc 必须转 0。
3. **不许改判分器与采集器**：`app/quality/**`、`scripts/collect_evaluation_answers.py`、评测夹具一字节不动；本量具只读窗件。
4. **接线**：`scripts/day1006_queue.py::claims` 在 run32 与 run33 之后各点一次，rc=3 只记「没有分母的 0」，**不许**把夜窗炸掉也不许当达标。
5. **交付**：凭据纸 `docs/testing/r704-<开工日>.md`（含 run31 真件读数与接线自证）；控制符各 0 枚；坐标一律 `文件::符号`。

## 写域

`scripts/r704_claims_coverage_readout.py`／`scripts/day1006_queue.py`／`docs/tickets/R704-*.md`／`docs/testing/r704-<开工日>.md`／`docs/tickets/index.tsv`

## 禁区

`app/**`／`frontend/**`／`app/quality/**`／评测夹具／`scripts/collect_evaluation_answers.py`／`docs/handoff/**`／容器·镜像·模型动作／主树外的树。

## 这一枚为什么存在

C④ 是五道门里唯一「看起来一直绿」的一格，而它绿的原因是分母为零。把这件事做成一枚能非零退出的读数口，比再写十枚账面针有用。