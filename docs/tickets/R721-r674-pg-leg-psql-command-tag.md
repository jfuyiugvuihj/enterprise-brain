# R721 · r674 的 PG 腿被 psql 的命令标签打回 rc=5：逐行 JSON 的读数面混进了 SET

**号**：R721　**性质**：总控亲签（10-06 夜收账现场，R720 修好两枚闸之后才暴露）　**基点**＝动刀那一刻主树 HEAD 现取

## 病形现取（总控亲跑，非推断）

- `python scripts/r674_window_trace_export.py --window run32 --from-postgres --user <现取的用户名>` ⇒ **rc=5**：`psql 第 1 行不是 JSON（只读腿交回的不是件本体）：SET`。
- 对照实验（同一台机、同一枚库，只改一枚开关）：
  - `psql -At -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only = on" -c "SELECT json_build_object('ok',1)"` ⇒ 交回两行，第 1 行是命令标签 `SET`；
  - 同名件加 `-q` ⇒ 只交回 `{"ok" : 1}` 一行。
- 真源：`scripts/r674_window_trace_export.py::psql_jsonl` 的 argv 没有 `-q`，而 `read_events_from_postgres` 对每一枚非空行都 `json.loads`，第一行就撞。

## 判据（每条可失败）

1. 治形只许一把：`-q` 只关命令标签，**一条 SELECT 的口径不许动**，读数面逐字节不许改形状；不许改成「跳过第一行」或「非 JSON 就忽略」——那是把契约闸拆了换一碗温水。
2. 结案读数：`--window run32 --from-postgres` 交回 rc=3 或 rc=0（件落盘＋逐枚缺段点名），且 `run32-traces.jsonl` 行数／sha256 点名；`r631_stage_sum_delta --window run32` 必须从 rc=3 变「跑通并出数」。
3. 同名件不许缩：`tests/test_r674_*.py` 全件复跑 0 failed，两态（dirty＋`git worktree add --detach` 干净检出）各一遍，文件清单逐枚相同。
4. 卫兵不许坏：`scripts/lint_hand_copied_coordinates.py --check` rc=0（棘轮只许降不许升）；`scripts/tickets_index.py --verify` rc=0；控制符各 0 枚；坐标一律 `文件::符号`。
5. 交付：凭据纸 `docs/testing/r721-2026-10-06.md`（含上面那对对照实验的原文命令与逐字读数）。

## 写域（只许这些）

`scripts/r674_window_trace_export.py`（只 `psql_jsonl` 那一枚 argv 与它的 docstring）／`docs/tickets/R721-*.md`／`docs/testing/r721-<开工日>.md`

## 禁区（踩线即退回）

`app/**`／SQL 语句本体（`select_for_sessions`／`READ_ONLY_SQL_PREFIX`）／`scripts/r631_*`·`scripts/r636_*`／`scripts/night1006_queue.py`·`scripts/day1006_queue.py`（那是 R720 的写域）／评测夹具／容器·镜像·模型·GPU／主树以外的树不许动、不 push、不建分支。

## 为什么这单值一枚号

R720 把两枚闸递齐之后才看得见这一格——它不是「调用侧漏了一个参数」，是量具自己从来没能连上过真库。在册那对同形状命令（`scripts/audit_r160_department_columns.py::psql_readonly`）把这条腿的姿势钉成了「会带 SET 标签」，而 r674 的读数面按逐行 JSON 契约收：两本账撞在一起，红的是 r674。
