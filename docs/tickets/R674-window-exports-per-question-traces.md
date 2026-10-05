# R674 · R51②：窗必须按题导出 trace 事件，否则「分段加总误差 <1%」永远量不到

**基点**：开工时现取主树 HEAD。**独占工作树**：总控预配。本单**只改量具与导出腿**，不动产品行为。

## 现取病形（总控 10-05 亲跑）

- `scripts/r631_stage_sum_delta.py --window run22`／`--window run23` 各 **rc=3＝量不到**；`scripts/r636_stage_coverage`（同名在册件）喂 32 MB 隔离事件件能取到 trace 2447／跨度 7405，但 **classify／rewrite／retrieve／generate／reflect 五段全缺**、可比 0 枚。
- 结论：判据 R51② 不是「测出来不达标」，是**根本没有可测的输入**。先补导出，再谈误差。

## 判据（每条都可失败，缺一枚判负）

1. 每一扇真机窗跑完必须在 `docs/perf/raw/<窗号>/` 落一枚**按题**的 trace 事件件（`runXX-traces.jsonl` 形状），逐行至少含 `question_id`／`trace_id`／五段各自的起止时刻；缺任一段 ⇒ 导出器自己必须点名缺哪段并非零退出，🔴 不许静默补 0 或补「估计值」。
2. 喂这份件给 `scripts/r631_stage_sum_delta.py` 必须交回**可比枚数 ≥1**（不再是 rc=3），并打印五段覆盖率逐段读数；把某一段抹掉 ⇒ 同一把尺必须退回 rc=3 并点名那一段（反证牙双向）。
3. 现有在册口径**一字不改**：`scripts/r631_stage_sum_delta.py::CRITERION_LINE_LF` 属另一枚单（R680）的写域，本单**不许碰**；两单同写该文件＝冲突，开工前先现读 `docs/tickets/R680-*.md` 的写域确认，撞上就停下回报。
4. 离线为主：新牙不 import `app`、不起服务、不动容器、不打模型，全离线单跑秒数写进凭据纸（形状照 `tests/test_r132_contract_followup_sync.py`，别照 `test_r302_*`／`test_r491_*` 那一族抄）。
5. 交付含：两态同名件数字（窗内禁跑 ⇒ 标 `NOT_RUN_IN_WINDOW`）、五段覆盖率现取读数、`rev-list`=0 与盘面自证、控制符各 0 枚。

## 写域（只许这些）

`scripts/`（导出器与 r631／r636 的**读数腿**，不含 `CRITERION_LINE_LF` 那一处）／`app/trace/`（仅在确有必要补事件字段时改，必须点名符号与原因）／新增 `tests/test_r674_*.py`／`docs/tickets/R674-*.md`／新凭据纸 `docs/testing/r674-<今天>.md`

## 禁区（踩线即退回）

`frontend/**`／`docs/handoff/**`／`docs/api/contract-v1.md`／评测夹具与判分器／`scripts/run_gate.py`／`pyproject.toml`／`deploy/**`／容器与镜像动作／主树任何路径。
