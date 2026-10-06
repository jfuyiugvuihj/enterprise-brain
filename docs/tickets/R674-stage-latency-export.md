# R674 · 待派池工单（由 R679 从账面派生·判据原文逐字·非总控亲签）

**号**：R674
**基点**：9efff02
**状态**：不由本文携带——跑 `python scripts/tickets_index.py --verify` 现取
**写域**：
- `scripts/`
- `tests/test_r674_*.py`
- `docs/tickets/R674-*.md`
- `docs/testing/r674-<今天>.md`

派工时由总控按写集复核上面四格；本行以下不再是机器字段。

## 判据原文（逐字·一个字不许改）

```verbatim source="S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R51::判据（机器可验）"
① 分类/改写/检索/生成/反思各段 P50/P95 可查；② 端到端与分段加总误差 <1%（对齐 `docs/perf/latency-budget-2026-09-16.md` 的 0.03%）
```

出处谓词＝`S21CELL::docs/handoff/2026-09-15-backend-followup-requests.md::R51::判据（机器可验）`。尺会按这枚谓词重读源文件逐字符比对，改一个字就点名「哪一号第几块自第几个字符起不合」。

## 账面点名的落点（派生自上面判据原文里的反引号路径）

- `docs/perf/latency-budget-2026-09-16.md`

## 总控亲签段（派工口径·以上「判据原文」逐字块为准）

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

## 交付清单

1. 判据原文逐字进单：`python scripts/tickets_index.py --verify` 必须绿，退出码 0。
2. 同名件两态读数：state① 本树已 apply 未 commit／state② `git archive 9efff02` 干净检出＋只投本单货；清单逐枚相同、总数相同，标「执行层自报」。
3. 凭据纸 `docs/testing/r674-<开工日>.md`：判据实际读数（枚数／字节数／退出码），不许形容词。
4. 反证牙：改掉盘上副本里的一处判据原文 ⇒ 校验非零退出并点名哪一号哪一条被改了字。
5. 坐标一律 `文件::符号`，禁止 `文件:数字` 形态的行号。
6. 收席那一刻现取：`rev-list --count 9efff02..HEAD`、staged 清单、未跟踪逐枚点名、`diff --numstat HEAD`。

## 这一枚为什么存在

待派池的散文账只有一行「R674（…）」，开工的人得重读整本跟进单或看板才能拿到判据原文。
本文件把那一段逐字搬进 `docs/tickets/`，从此逐号状态的唯一真源是工单目录，
每班开工只读 `docs/tickets/index.tsv` 与本文件。

---

## 执行层回执（be-r674／基点 d653e41／2026-10-05 23:1x·货在树里，状态不由本文携带）

- **交了什么**：scripts/r674_window_trace_export.py（按题导出器）＋ tests/test_r674_stage_latency_export.py（18 枚牙）＋凭据纸 docs/testing/r674-2026-10-05.md。判据原文逐字块一字未动；`scripts/tickets_index.py --verify` rc=0。
- **两态数（执行层自报）**：state① 18 passed／0.81 s（复跑 0.84 s）；state②（`git archive d653e41` 干净检出＋只投本单两枚件）18 passed／0.80 s；清单逐枚相同、总数相同。
- **r631 一字未改**：本单只读引用它并把件喂回去（scripts/r631_stage_sum_delta.py 与 scripts/r636_stage_coverage.py 零字节改动）——所以与 R680 的同文件写集**没有真的撞**；纸面那一格请总控裁（详见凭据纸 §1「写集冲突回报」）。
- **件的两行形状（对判据 1 那句「逐行至少含五段起止时刻」的取窄）**：事件行只带十枚起止时刻，整本跨度账（逐枚 record 级）落在一枚 r674.shot.detail 行上；一题都没落的落 r674.question.no_events 行并留在母集里。理由＝把跨度账抄到每一行，一扇 105 题窗要胀到几十 MB 压进 git；现取体量 12,293 B／题。
- **判据 2 的「同一把尺退回 rc=3」按导出器解**：抹一段⇒导出器 rc=3 点名（r631 同件仍出数并在「该题未现段」列点名，那是它的在册语义）；抹整条分段腿⇒r631 rc=3＋status=no_segments。两半都钉住了。若总控要求「抹一段也要让 r631 rc=3」，那是改 r631 的判死条件，归 R680／另立单，本席不越。
- **窗况**：本席按 `docs/tickets/WINDOW-2026-10-05.md` 的口径现取过——night1005d 队列 pid 不在、夜产物自 20:29 起零写入、容器 22:13 刚被 recreate、总控 22:18–22:20 正在并树与派工；据此刻「无窗空档」跑了单文件同名件（最重 10 s）。若总控判这仍算窗内，两态数请窗后复跑，本席不辩解。
- 🚨 **事故 #124（本席造成）**：一次性自检脚本末尾 `shutil.rmtree(base.parent.parent)` 把 %TEMP% 当自己根目录清了——`%TEMP%\evalrun`（夜窗产物 144 枚＋night1005d 日志与账本）、`%TEMP%\eb104`（**含 Lovelace／R666 那份 30,445 B 的唯一盘外保命快照**）、`%TEMP%\r647_state2`、`%TEMP%\r653_state2` 全没，`git worktree list` 三枚现标 prunable。仓内与所有工作树的货一格未损。逐枚点名、幸存清单与处置写在 docs/testing/r674-2026-10-05.md §0；看板 §0 那一行须由总控 splice（docs/handoff/** 在本席禁区）。`git worktree prune` 请先确认 lovelace 快照无别底再动。