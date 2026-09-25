# R59c 离线自校实录（零容器 · 零模型 · 零网络）

- 出单：执行层 Malthus（R59c）｜日期：2026-09-25｜基点：`4e29141`（主树 HEAD `866c2f3` 只多两笔 docs-only）
- 判据 ④ 的原话要求：脚本在零容器/零模型条件下要能跑通自校，证明**解析、比集合、写表**三路都对；反证钉抽错哪一格，红的必须是那一格的列（教训 #46）。
- 解释器：`C:\\Users\\fengx\\PycharmProjects\\企业智脑\\.venv\\Scripts\\python.exe`（宿主 anaconda `python` 没有 chromadb，用它报错是假红）。
- 本文只记**已经真跑过**的读数；任何一条复现命令都写在下面，逐条可核。

## 0. 怎么复现（三条，全在树根 `C:\\Users\\fengx\\PycharmProjects\\be-r59c`）

```powershell
Set-Location 'C:\Users\fengx\PycharmProjects\be-r59c'
$py = 'C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe'
& $py scripts\r59c_recall_compare.py selfcheck ; "EXIT=$LASTEXITCODE"      # 期望 20 枚钉全绿，verdict=SELF_CHECK_OK
& $py scripts\r59c_sandbox_corpus.py  selfcheck ; "EXIT=$LASTEXITCODE"      # 期望 18 枚钉全绿，verdict=SELF_CHECK_OK
& $py scripts\r59c_recall_compare.py collect --arm chroma-cold --out "$env:TEMP\x.jsonl" --top-k 5 --repeats 2 --dry-run ; "EXIT=$LASTEXITCODE"   # 期望 0，且不落文件
```

🔴 宿主坑（本单实测踩到，写给下一个人在 %TEMP% 前省一轮）：**不要把 `%TEMP%` 当 cwd 跑解释器** —— 那里有一枚 `attr.py` 会遮蔽 `attr` 包，报出来的红与本单无关。

## 1. A 件：`r59c_recall_compare.py` —— 20 枚钉（EXIT=0）

```text
{ "tool": "scripts/r59c_recall_compare.py", "mode": "selfcheck", "offline": true,
  "questions_source": "fixture:tests\fixtures\business_evaluation_100.jsonl",
  "pins_total": 20, "pins_red": [], "blocked_socket_attempts": [], "verdict": "SELF_CHECK_OK" }
EXIT=0
```

| 钉 | 守的是哪一路 | 实录读数 |
|---|---|---|
| P0 | 干净基线不许是红的 | 三臂 collect 退出码 `{chroma-hot:0, chroma-cold:0, pgvector:0}` |
| P1 / P1b | **解析路** | 服务端 float 形状 `chunk_index: 3.0` → int 且 key 同源（`doc-03 hits=5`）；腿凭证按 `answered_by` 增量归一 `{legs:{chroma:1}, hot:{hits:1}, bypass:""}` |
| P2 / P9 | **比集合路** | 手算五行逐值相等 `{k:5, base_rows:3, target_rows:3, overlap:2, overlap_ratio:0.4, ...}`；双空题 `jaccard=null` 且单独计数（不误判成"一致"） |
| P3 / P3b / P3c / P3d | **写表路** | 三臂两两配对 16 题、干净基线 differing=0；CSV 列序 == `PAIR_COLUMNS` 且回读题对数相等；反证钉进得了表（恰一行 `same_set=False` 且是那一个题号）；人读表含三格状态与三臂代价分解 |
| P4 / P4b | 臂身份 | 答腿与声明不符 ⇒ 退出码 **3**（`answered-by-unexpected:chroma`）；未证实臂的产物 `compare` **拒收**："臂 pgvector 有 8/8 枚读数的答复方与声明不符 —— 臂身份未证实，拒绝出对照" |
| P5 / P5b | 反证钉（集合） | 抽错一题 ⇒ 红的恰是那一题：`touched=1 red=[doc-04] differing=1`，且红在集合列（`jaccard=0.5, first_diff_rank=1`） |
| P6 / P6b | 反证钉（权限） | 越权行**只在权限列红**、集合列仍全绿；逐格计数进 `cells.9.3-3.over_permission_rows = 2` |
| P7 / P7b | 可选性硬闸 | 现库形状（class 全 1 / dept 全空）⇒ 判 `NOT_MEASURED` 并指名原因（含"`principal` 走 `administrator_scope`，`app/rag/filters.py` 里它不带部门谓词"）；换成跨部门跨密级语料 ⇒ 同一判据当场变 `SUPPLIED`（`levels:[1,2,3], departments:[fin,hr]`） |
| P8 | 噪声地板 | `--repeats>=2` 才给得出地板；单遍 `repeated_cells=0`、`noise_floor_ms_p95=null` |
| P10 | 零网络 | 假服务没开过一次 socket：`blocked_attempts=[]` |
| P11 | 代价恒等式 | 注入真值 `hot_gain=204.5, switch_cost=-100.0, net_yield_cost=104.5` 且 `net = switch_cost + hot_gain` 成立 |

## 2. B 件：`r59c_sandbox_corpus.py` —— 18 枚钉（EXIT=0）

```text
{ "tool": "scripts/r59c_sandbox_corpus.py", "mode": "selfcheck", "offline": true,
  "corpus_chunks": 36, "pins_total": 18, "pins_red": [], "verdict": "SELF_CHECK_OK" }
EXIT=0
```

| 钉 | 守的是哪一路 | 实录读数 |
|---|---|---|
| S1 | J-1 可选性 | 沙盒语料每一档部门号都只放行**一部分**（不是全命中） |
| S2 / S2b | 谓词来源 | 谓词取自产品本体 `resolve_document_retrieval_scope`，形状 `fin / <=1`；admin 一档退化成全命中 —— **这条就是现库的病，写进判据免得被当成通过** |
| S3 | 精确解可复算 | 精确 top-k 复算得动且落在允许集内 |
| S4 | GREEN 路径 | 完美读数 ⇒ 两侧一致且等于精确解 |
| S5 / S6 / S7 | **反证钉（三路各一枚）** | 抽错一题的**顺序** ⇒ 红只落那一格那一题（J-3）；HNSW 少给一条 ⇒ J-3 红且点名那一题；一条越权块 ⇒ **J-2 直接红**（fail-closed 优先于召回） |
| S8 / S9 | 不许假绿 | 缺读数 ⇒ `NOT_MEASURED`（不许把空表印成通过）；只有全命中谓词 ⇒ `NOT_MEASURED`（**这就是 §9.3 ③ 今天的形状**） |
| S10 | 沙盒守卫 | `--sandbox-db enterprise_brain`（撞生产名）⇒ **REFUSE，EXIT=3，且不产任何文件** |
| S11 | 批单纯度 | 正向批单里零 `DROP`，且每条都过 `current_database()` 守卫 |
| S12 | 探针零写入 | `probes.sql` 没有 INSERT/CREATE/DROP，只有 SELECT + SET |
| S16 | **缺件不抛栈**（本班自纠） | `--run` 指的读数文件不存在 ⇒ 点名"哪一臂、哪条路径"并退出码 **2**；早先版本在这里抛 `FileNotFoundError` 栈，把"上一窗被打断"伪装成"工具坏了" |
| S17 | **半行不抛栈**（同上一枚） | 末行只剩 1/3 截 JSON（= Ctrl-C 现场的典型形状）⇒ 拒判 + 直接把 `--resume` 续跑命令行打出来，退出码 2。两枚都有齿：把守卫撤掉，`read_service_run` 立刻抛 `JSONDecodeError`（实测复现） |
| S13 / S14 / S15 | **跨件接口**（A 件产物直接进 B 件判据） | A 的 `build_record` 产物能被 `verify` 判（两侧 GREEN）；**臂身份未证实的产物被拒收**（误判 #43 不重演）；换掉一发的 top-1 ⇒ 红落在那一档 principal 的 J-2/J-3 |

（注：上面那枚 `corpus_chunks": 36` 是**语料块数**，与钉数无关 —— B 件 18 枚、A 件 20 枚，两件事别记成一件）

## 3. `--dry-run` 实录（判据 ① 的"零网络"要求）

```text
[dry-run] arm=chroma-cold 开关声明=读后端=chroma(默认字面量) + HOT_INDEX_ENABLED 未设/关(env) = 今天生产
[dry-run] 题集 105 题 题号sha=b6d3323da244
[dry-run] 档位 top_k=[5] 重发=2 => 将发 210 发 /api/v1/observability/retrieval/debug
[dry-run] 每发另配 2 拍 /api/v1/health/details（--no-health-probe 可关，但臂身份就无从证实）
[dry-run] 预算闸 --max-requests=260；样例载荷（零网络）：{"query": "住宿费标准是多少？", "top_k": 5,
           "request_id": "r59c-chroma-cold-doc-01-k5-r0-104ea03e", "trace_id": "...:t"}
[dry-run] 未发任何请求，未打开任何 socket。
EXIT=0     落文件否: False（产物路径压根没创建）
```

⇒ 发数公式在这里对得上：`105 题 × 1 档 × 2 遍 = 210 发`，默认 `--max-requests 260` 装得下**一臂两遍**，装不下三臂 ⇒ 操单里每臂各一发 `collect`、各带自己的预算闸。

## 4. `plan` 出料实录（零库访问）

```text
& $py scripts\r59c_sandbox_corpus.py plan --out $env:TEMP\r59c_probe_docs1 --chunks 48     EXIT=0
corpus.json 397369 | matrix.json 22360 | matrix.jsonl 13113 | accounts.json 1359 | BATCH.md 3024
documents/ 48 个 .txt（4 部门 exec/fin/hr/ops × 3 密级 l1/l2/l3 × 4 块）
sql/00_guard_note.sql 497 | 01_scope.sql 1154 | 02_table.sql 1364 | 03_chunks.sql 379790
    04_indexes.sql 1256 | 99_rollback.sql 808 | probes.sql 458957
"executed": "NOTHING（本件只出料；DDL/DML 需业主批准）"
```

逐格放行比例（就是"选择性"本身，取自同一份 `BATCH.md`）：`staff-fin-l1` 4/48 = 0.0833 ｜ `manager-hr-l2` 8/48 = 0.1667 ｜ `manager-ops-l2` 8/48 = 0.1667 ｜ `exec-l3` 12/48 = 0.25 ｜ `admin-l3` 48/48 = 1.0（**J-1 判否**，正是现库的病）。
HNSW 参数按生产同一份读数建（`m=16`/`ef_construction=100`/`vector_l2_ops`，出处 `docs/testing/r59b-recall-reading-2026-09-24.md`）—— 否则 J-3 只能量精确解、量不到索引腿。

## 5. 编码与卫生（本单写域）

| 检查 | 命令 | 读数 |
|---|---|---|
| 无 BOM | `& $py scripts\check_no_bom.py` | 新脚本/新文档 **零 BOM**；仓里剩 2 枚 BOM 是**他人历史件**（`docs/testing/run6.stamp.txt`、`docs/testing/run7p1.stamp.txt`），本单未碰 |
| CRLF 一致 | 逐文件比对 `count(CRLF) == count(LF)` | 两份脚本 `crlf_only True`；三份文档 `lone_lf = 0` |
| 写域 | `git status --short` | 只有 `?? scripts/r59c_*.py` 与 `?? docs/testing/r59c-*.md`；`app/rag/**`、`app/documents/catalog.py`、`deploy/.env.server`、`frontend/**`、`docs/handoff/**` 零改动 |
| 无 git 写操作 | `git rev-parse HEAD` | 仍是基点 `4e29141`，无 commit/branch/add |
| 未跑全量门 | —— | 本单没跑 `scripts/run_gate.py`，没开 `-n`，没同时开两发 pytest |

## 5b. 本班内自纠的两枚缺陷（写完量具后自己踩出来的）

| # | 缺陷 | 触发条件 | 修法 | 复验命令 | 读数 |
|---|---|---|---|---|---|
| 1 | `verify` 遇到**不存在的读数件**抛 `FileNotFoundError` 栈（退出码 1） | `--run arm=path` 指到还没生成的文件（Ctrl-C 现场常这样） | 缺失 ⇒ 点名"哪一臂、哪条路径"并退出码 2；`(OSError, ValueError)` 一律降级成点名拒判 + 打出 `--resume` 续跑命令 | `& $py scripts\r59c_sandbox_corpus.py verify --matrix ... --run chroma=不存在的.jsonl` | `[前置不满足] 臂 chroma 的读数文件不存在…` / **EXIT=2**（原来是栈） |
| 2 | `verify` 遇到**不存在的判据表**同样抛栈 | `plan` 被 S10 守卫拒出料之后接着跑 `verify`（目录本来就是空的） | 缺失/读不动 ⇒ 点名 + 退出码 2 | `verify --matrix <空目录>/matrix.jsonl` | `[前置不满足] 判据表不存在…` / **EXIT=2** |

两枚都补了有齿的钉（S16 / S17）：**撤掉守卫就复现 `JSONDecodeError`**，本单实测过撤守卫那条路径确实抛栈（`pre-fix behavior reproduces: JSONDecodeError`），所以这两枚不是自证式绿。
S10 沙盒守卫没被这次改动削掉：`plan --sandbox-db enterprise_brain` 仍然 **EXIT=3 且不产文件**。

## 6. 这一页**没有**证明什么（边界，写给下一个读者）

- 38 枚钉全绿（20 + 18）只证明**三路算法与守卫正确**，不证明任何一条真库召回性质 —— ①②③ 三格的读数**还没有一条存在**。
- `census` / `preflight` 本单没跑过一发（它们要真服务）。操单 §3 的期望值是**按代码推出来的**（热集默认关、`answered_by` 该是谁），不是实测；窗内第一件事就是把它证实或证伪。
- 现库"谓词全命中"这一形状来自计划书 §9.3 ③ 原文，本单在离线侧复算过它的后果（P7/S9 两枚钉），但**没有**在生产库上跑过一次普查。
