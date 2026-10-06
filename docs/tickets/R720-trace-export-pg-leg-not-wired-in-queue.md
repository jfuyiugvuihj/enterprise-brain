# R720 · `r674` 的 PG 腿两枚闸没接进队列 ⇒ 分段腿恒「量不到」（R51② 的真阻塞·调用侧）

**号**：R720　**性质**：总控亲签（10-06 晚 run32 收窗现取）　**基点**＝派工那一刻主树 HEAD 现取　**独占工作树**：总控预配并告知路径，不许换树、不许碰主树。

## 一手事实（总控亲取，非推测）

- 19:08:37 `run32-run` rc=0（105 片，墙钟 2764.6 s）→ 19:08:38 `run32-commit` rc=0 → 19:08:40 连着四枚红：`run32-r674_window_trace_export` **rc=4**、`run32-r631_stage_sum_delta` **rc=3**、`run32-r636_stage_coverage` **rc=3**、`run32-r631-lane-off` **rc=3**。
- `r674` 自己报的话：「分段腿无货：既没有 `--events`/`--journal` 件，也没开 PG 腿（窗 run32）」。
- 读码现取的根因：`scripts/r674_window_trace_export.py::PG_OPT_IN_ENV` 的值是 `R674_WINDOW_EXPORT_PG`，PG 腿**出厂即关**，要 `--from-postgres` ∧ 该环境变量＝on 两枚闸齐了才肯连库；而 `scripts/night1006_queue.py::readout` 里那一圈 `glob("scripts/r674*.py")` 只递 `--window <tag>`——两枚闸一枚都没给 ⇒ 分段腿**每扇窗都必然空手**，`r631`/`r636` 跟着恒 rc=3。
- 🔴 这不是产品码没发点：`app/trace/spans.py::stage_account` 的生产调用点在树——`app/agents/nodes.py::classify_intent`／`::plan`／`::respond`／`::synthesize`／`::reflect_node` 五处（经 `::_stage_account`）＋`app/api/v1/chat.py` 与 `app/rag/retrieval_pipeline.py` 的 rewrite 腿两处（R688 并树 `ecbd525`）。欠的是**把这枚开关接进调用侧**。
- 今晚窗后总控会手跑一次同一枚导出拿到 R51② 的读数；**那一次不能替代本单**——不接进队列，下一扇窗还是 rc=3，同一枚返工单会继续生。

## 判据（每条可失败）

1. 队列里 r674 那一圈要递 `--from-postgres` ＋ 环境变量 `R674_WINDOW_EXPORT_PG=on`；两枚名字**从量具自己的常量派生**（`PG_OPT_IN_ENV`），不许在队列里手抄第二份字符串（棘轮预算顶格，见 5）。
2. 递了之后 `run32`/`run33` 的 `r631`（端到端 vs 分段加总误差）与 `r636`（逐段覆盖率）要能**出数**；出不了数必须点名卡在哪一格——PG 交回 0 枚事件／frames 件里没有 `session_id`／分段腿件名不在位——🔴 不许静默 rc=3。
3. `r631` 的「量不到不是 PASS」那一档语义**不许动**，不许为了翻绿把 rc=3/4 改成 rc=0；`r636` 同理。
4. 交付里 R51② 一律写「码在树／读数待窗」；这一格只许由**接好之后的下一扇窗**判达，本单不许宣布绿。
5. 卫兵不许坏：`python scripts/tickets_index.py --check` 与 `--verify` rc=0；`python scripts/lint_hand_copied_coordinates.py --check` rc=0（预算顶格＝只许降不许升）；`scripts/run_gate.py` 与 `tests/test_r181_text_frame_ruler.py` 不许碰；不许新增读 markdown 的用例；坐标一律 `文件::符号`，写文件走单引号 here-string 或编辑器通道，写完现读 `0x00/07/08/0b/0c` 各 0 枚。
6. 交付：同名件两态读数（dirty ＋ `git worktree add --detach` 干净检出各一遍）＋凭据纸 `docs/testing/r720-<开工日>.md`。

## 写域（只许这些）

`scripts/night1006_queue.py`（`readout` 里 r674 那一圈）／`scripts/day1006_queue.py`（同形处）／新增 `tests/test_r720_*.py`／`docs/tickets/R720-*.md`／`docs/testing/r720-<开工日>.md`

## 禁区（踩线即退回）

`app/**`／`scripts/r674_window_trace_export.py`（量具本体，本单只改调用侧；要改量具另立单）／`scripts/r631_stage_sum_delta.py`／`scripts/r636_stage_coverage.py`／`scripts/run_gate.py`／正在跑窗的账本与分片目录／`frontend/**`；不 push、不建分支、不碰主树。

## 排期硬约束

夜窗在跑的时候**不许动本单写域**（AGENTS ⑬：量具与窗互斥）。最早开工＝今晚收窗（`day1006.DONE.txt` 落盘）之后。
## 追加（同班窗后·收账现场）：第三枚闸——PG 腿的用户名也不是量具缺省

- 18:22 之后本班按本单把两枚闸递齐再跑，交回 **rc=5**：`psql 第 1 行不是 JSON（只读腿交回的不是件本体）：SET`。
- 现取两枚根因，各自归位：
  1. `scripts/r674_window_trace_export.py::collect` 的 `user` 缺省是 `postgres`，而本部署 `docker compose exec postgres printenv POSTGRES_USER` 现取＝`enterprise_brain`（backend 的 `DATABASE_URL` 同一枚用户名）⇒ 调用侧必须把用户名递进去。
  2. psql 把 `-c SET` 的命令标签 `SET` 打到 stdout，混进逐行 JSON 的读数面 ⇒ 量具自身的缺陷，**不在本单写域**，另立 **R721** 承接（AGENTS ②：新内容文末追加，本单不改判据）。
- 调用侧治法（已落 `scripts/night1006_queue.py::r674_pg_user`）：用户名向 compose 的 postgres 服务现取，容器名不抄第二份；取不到就交回空串退回旧行为——读数腿永远不许把窗带崩。
- 修好之后的第一枚真读数（代次 `922da30`，镜像 10-06 18:21 本地、band 0 代次闸已 PASS）：
  `python scripts/r674_window_trace_export.py --window run32 --from-postgres --user <现取> --out %TEMP%\evalrun\run32-traces.jsonl`
  ⇒ 事件 3,865 枚／trace 124 枚／落件 3,989 行 6,126,224 B（sha256 `9475024bcc69181e`），五段齐的发数 **66/105**；`r631_stage_sum_delta --window run32` 由 rc=3 变 **跑通并出数**（<1% 那一格 FAIL，逐段缺发点名：classify 缺 19／rewrite 缺 44／retrieve 缺 48／generate 缺 21／reflect 缺 38；reflect 加总 0.0 ms）。
- 🔴 R51② 的结论仍按红线写：**码在树／读数待窗**——本枚读数证明的是「分段发点不齐」这件事，不是「端到端与分段加总的误差已判」。判它要 run34（重建镜像之后）的同名件复跑。
