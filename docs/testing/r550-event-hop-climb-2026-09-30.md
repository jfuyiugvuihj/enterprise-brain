# R550 · 让空表量具跨过「事件发射点 → 订阅 / 投影 → 写句」这一跳

单号 R550（执行层，代号 A）｜工作树 `be-r550`｜基点 `f3f24b623c8a52361ed3d8ffd756510dbe1cc948`（短 `f3f24b6`，开工时派工词写 `f312eeb`→追平 `4572aa8`→本单读数全部注明追到 `f3f24b6`）｜零 commit、零 push、零动主树、零容器、零模型、零起服务。
解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`（PATH 上的 `python`/`pytest` 是 anaconda3，本单一枚没用）。
🔴 以下所有数字都是**执行层自报**，命令原文逐条附在旁边；总控在主树复跑数不等于本纸数字。

## §0 要治的病

`scripts/r483_empty_tables_triage.py` 认的「走得通的写入道」= 从写语句往上爬到 HTTP 路由或 `add_job`。
`retrieval_traces` 的写句是 `app/trace/projections.py::project_retrieval`，由 trace store 收到
`retrieval.completed` 事件时派发；R536（主树 `7e1c221`）已把发射接进产品问答道
（`app/rag/retrieval_pipeline.py::record_retrieval_completed`，挂点 `app/api/v1/chat.py` 的
`arm_retrieval_trace` 与审批续跑轮），但这枚量具仍读 `no_seed_path`。总控 09-30 17:5x 手动翻
`legitimately_empty` 时被 `--check` 当场驳回「现扫爬不到任何产品面…应改判 no_seed_path」——
**是量具量不到，不是产品道没接通**。本单治量具，不治产品码：`app/**` 零改动。

## §1 改动清单（全在写域内）

| 文件 | 改了什么 |
|---|---|
| `scripts/r483_empty_tables_triage.py` | 沿边走的爬法（新尺 13 枚方法）＋ `TRIAGE["retrieval_traces"]` 按现扫改口 ＋ `validate()` 两枚新牙 ＋ 生成件里逐枚呈现桥与 fail-closed note |
| `docs/testing/r483-empty-tables-2026-09-29.md` | 只由 `--sync --live-from-doc` 自己变，未手写 |
| `tests/test_r483_empty_table_triage_is_derived.py` | 两枚在册钉改口（见 §5） |
| `tests/test_r550_event_hop_climb_is_generic.py` | 新钉：判据① 通用性（静态＋合成小树正控/反控）＋ 两枚新牙的内存级刀 |
| `tests/test_r550_counter_evidence_teeth.py` | 新钉：六把影子树刀（判据②③） |

爬法形状：`surface()` 从「一跳文本匹配」改成**带事件标签的 BFS**。节点 = `(文件, def 行, 事件)`，
四条边：`caller`（谁写了 `<symbol>(`）、`publish`（消费点被 `if event_type == "x.y"` 护着 ⇒ 另一端是
谁发这枚事件）、`gate_token`（函数缺某枚 ContextVar 就 `return`/`raise` ⇒ 那枚 `.set(` 处是谁把这一轮
挂上来的）、`declared_event`（TRIAGE 声明的事件 ⇒ 现扫的发射点）。标签**沿边走**：同一枚 dispatcher 里
别的事件的分支不许借道；一处调用被多枚事件守卫时不带标签上爬。三条边一律 fail closed：守卫解不开、
调用点落在模块级、发射点不在函数里，都只记 note 而**不**把这条道算通。

## §2 判据逐条 → 命令 → 读数

**判据①（通用爬法，不许表名特例）——达标。**

凭据一（静态，AST 级）：
```
& "<venv python>" -X utf8 <TEMP>\r550_precheck_a.py
missing []
FORBIDDEN_HITS 0
surface args ['self', 'entries', 'events']
```
`FORBIDDEN_HITS 0` 的含义：13 枚爬法方法（`surface / event_emitters / dispatch_labels / dispatch_events /
gate_armers / context_set_sites / route_on_chain / enclosing_defs / event_constants / statement /
function_body / shadowed / callers`）里，剥掉文档串之后的**字面量、名字、属性、形参**中，八枚表名、
`retrieval.completed`、`/retrieval/debug`、`project_retrieval`、`project_event`、
`record_retrieval_completed`、`arm_retrieval_trace` 一枚都不出现；`surface` 的形参只有
`self, entries, events`——它拿不到表名，也就无从为这张表写分支。这两格已固化成在册钉
`test_the_climb_code_carries_no_table_name_and_no_real_event_name`、
`test_no_climb_method_takes_a_table_or_collection_argument`。

凭据二（合成小树正控，全 invented 名字）：
```
& "<venv python>" -X utf8 <TEMP>\r550_precheck_synth.py
PASS test_the_synthetic_tree_contains_no_real_name_at_all
PASS test_the_same_climb_crosses_the_event_hop_on_an_invented_tree
PASS test_the_route_on_an_invented_tree_is_paid_for_by_the_gate
PASS test_a_call_guarded_by_two_events_is_not_clothed_with_one_label
PASS test_an_emitter_only_reachable_from_a_script_main_is_not_a_product_face
```
小树里 `synth.completed / project_synth / emit_synth / arm_synth_token / POST /synth/ask` 全套假名，
同一套爬法爬到 `POST /synth/ask`，且四族桥（`declared_event / publish / gate_token / event_guard`）
齐；三枚反控（摘闸门、一处调用两枚事件守卫、发射点只在 `scripts/` 的 `main()`）都读零枚产品面。
⇒ 「通用」不是靠真树读数蒙对。

**判据②（翻绿只能由自洽腿逼出来）——达标。**

逼出改口的原始一笔（在旧基点 `59a9506` 形状上，改口**前**现扫）：`validate()` 恰好报一句
`retrieval_traces 裁为 no_seed_path，但现扫已能从产品面走到它，裁定过期：[… chat.py … POST /ask …]`。
改口**后** problems 归零。这把刀的可复跑形态在影子树上（§3 的 K1/K3a/K3b）：摘掉发射腿，
`validate()` 重新报「应改判 no_seed_path」；逐字节复原后再扫归零。在册侧另有一枚双向牙
`test_the_old_ruling_word_is_now_the_one_that_goes_red`（把裁定按回 `no_seed_path` 当场红）。

**判据③（调试面豁免不许成后门）——达标。** K1：只余调试面时产品叠必须归零且裁定报过期；
K2：两枚发射腿全摘 ⇒ 调试面也归零 ⇒ `unused_exemptions` 必须点名 `/retrieval/debug`；
K4：摘掉调试面的路由装饰器 ⇒ 产品道照在（`POST /ask`/`POST /approve`），但豁免用不上 ⇒
报「豁免成了后门」，不许静默通过。逐枚读数见 §3。

**判据④（在册族不退化＋改口成对）——本单只交 dirty 态。**

```
& "<venv python>" -X utf8 -m pytest tests/test_r550_event_hop_climb_is_generic.py tests/test_r483_empty_table_triage_is_derived.py -q -o addopts= -p no:randomly
34 passed in 64.37s (0:01:04)
& "<venv python>" -X utf8 -m pytest tests/test_r550_counter_evidence_teeth.py -q -o addopts= -p no:randomly
8 passed in 134.61s (0:02:14)
```
B 件在门绿窗内一共跑过三次，逐次如实记：修刀前 `1 failed, 7 passed in 130.63s`（K3b 的断言写反，见 §3 末）；
修刀后 `8 passed in 134.61s`；驱动批次里再 `8 passed in 142.73s`（与另一枚执行层同机争用，只差 8 s）。
三次都是同一基点 `f3f24b6`、同一份盘上文档读数、串行、`-o addopts=`、零 `-n`。
逐枚计数与正/反序合跑（追平 `f3f24b6` 后）：
```
A_alone            14 passed in 11.26s · rc=0
r483_alone         20 passed in 54.90s · rc=0
B_alone            8 passed in 142.73s (0:02:22) · rc=0
together_forward   42 passed in 211.26s (0:03:31) · rc=0
together_reverse   42 passed in 208.70s (0:03:28) · rc=0
```

**判据⑤（`--check` rc=0，生成件只由 `--sync` 自己变）——达标（基点 `f3f24b6`）。**
```
& "<venv python>" -X utf8 scripts/r483_empty_tables_triage.py --sync --live-from-doc
synced C:\Users\fengx\PycharmProjects\be-r550\docs\testing\r483-empty-tables-2026-09-29.md bytes=26422 problems=0     rc_sync=0
& "<venv python>" -X utf8 scripts/r483_empty_tables_triage.py --check
PASS check：八枚表 + 两枚对照 + 现扫写入点全部逐字节复现，problems=0                                                     rc_check=0
```
（旧基点 `59a9506` 上第一次 sync 交回 `bytes=26372 problems=0`；追平 `f3f24b6` 后 `nodes.py`/`contracts.py`
等已变，故重新 `--sync` 归位坐标——本纸引用的是**新基点**那份，旧数字只作为「换基点确实会漂」的记录。）

## §3 反证刀清单（六把，全在影子树；被跟踪文件零改动）

影子树 = `app/ + scripts/ + migrations/` 逐份拷进 tmp（`shutil.copytree`，零 `__pycache__`）。
每把三格凭据：摘前 sha256 前缀 → 红了哪一句（`validate()` 原文）→ 逐字节复原后再扫 problems 归零。
凭命令：
```
& "<venv python>" -X utf8 -m pytest tests/test_r550_counter_evidence_teeth.py -q -o addopts= -p no:randomly   # 8 passed in 134.61s
& "<venv python>" -X utf8 <TEMP>\r550_evidence.py                                                            # 逐枚打印 validate() 原文
```

| 刀 | victim（摘前 sha256 前缀） | 摘的是什么 | 红了哪一条（原文） | 复原 |
|---|---|---|---|---|
| K0 正控 | 五枚 victim 全在位 | 不动 | `validate()==[]`，产品面 `POST /approve, POST /ask`，调试面 `POST /retrieval/debug` | — |
| K1 | `app/rag/retrieval_pipeline.py` `487160315b9e` | 产品发射腿 `event_type="retrieval.completed"` | `retrieval_traces 裁为 legitimately_empty，但现扫爬不到任何产品面 HTTP 路由或 add_job：按判据这条道不存在，应改判 no_seed_path` | ✓ `487160315b9e`，recheck `problems==[]` |
| K2 | 同上 ＋ `app/rag/debug.py` `29eda326261c` | 两枚发射腿全摘 | 上一条 ＋ `retrieval_traces 声明了调试面豁免 /retrieval/debug，但现扫爬不到那枚路由：豁免成了后门，要么删声明要么重裁` | ✓ 两枚，recheck 归零 |
| K3a | `app/rag/retrieval_pipeline.py` `487160315b9e` | 闸门 `if context is None: return None` | 「应改判 no_seed_path」＋`gate_token` 边消失 | ✓ recheck 归零 |
| K3b | `app/api/v1/chat.py` `386eb09f5720` | 问答脸上两枚挂点 `arm_retrieval_trace(`（命中数 2） | 「应改判 no_seed_path」，但 `gate_token` 边**仍在**（armer 与 `.set(` 都还在树里）⇒ 脸没了就不算道 | ✓ `386eb09f5720`，recheck 归零 |
| K4 | `app/api/v1/observability.py` `4caba74f20d0` | 调试面路由装饰器 | 只报「豁免成了后门」，产品面仍 `POST /approve, POST /ask` ⇒ 调试面从来没撑过产品道 | ✓ recheck 归零 |
| K5 | `app/trace/projections.py` `2d2291ffaf4b` | 投影守卫里的事件名漂一格 | `retrieval_traces 声明的事件与现扫守卫到的不等：声明 ['retrieval.completed']，现扫 ['retrieval.drifted']——事件标签漂了，跨跳那条道不作数` | ✓ recheck 归零 |

刀的第一版有一枚**写反**，如实记：K3b 原本断言「摘掉挂点后 `gate_token` 边应消失」，实测 1 failed /
7 passed in 130.63s——边确实还在（setter 与 armer 都没动），消失的是脸。断言改成「边仍在而脸归零」
之后 8 passed。这一格反过来正是 K3a/K3b 的区别：K3a 拆闸门 ⇒ 边没；K3b 拆挂点 ⇒ 边在而道没。

两枚新牙另配了在内存里就能咬的刀（不是死牙）：
`test_an_unlabelled_cross_edge_is_refused`（塞一枚 `via=publish` 而不带事件标签 ⇒ 报「无主的跨跳边」）、
`test_a_drifted_event_declaration_is_reported`（往声明里加一枚 `ghost.completed` ⇒ 报「不等」），
两枚都在 `finally` 后 `validate()==[]` 复跑。

## §4 在册件改口账（两枚，只交 dirty 态）

改前原文一律现取，不手抄：`git show f3f24b6:tests/test_r483_empty_table_triage_is_derived.py`。

1. `test_retrieval_traces_keeps_no_seed_path_only_because_the_gauge_cannot_cross_the_projection_hop`
   → `test_retrieval_traces_reads_legitimately_empty_because_the_gauge_now_crosses_the_hop`。
   旧钉把 `verdict == "no_seed_path"` 当判据；量具跨过那一跳之后，这一句就成了会被 `validate()`
   当场驳回的假话。新钉改咬四格：裁定 = `legitimately_empty`、`owner_ruling` 里那句「已经过期」必须
   留着自曝、产品面必须真在、跨过来的道必须带事件标签、调试面豁免必须用得上。
2. `test_a_stripped_exemption_declaration_turns_the_ruling_red` → 
   `test_an_exemption_that_no_longer_matches_a_route_is_reported_as_a_back_door`。
   旧钉是**永不匹配的死牙**：新形状下摘掉 `debug_only_surface` 声明不再使裁定过期（产品面真在），
   它那句 `assert any("裁定过期" …)` 永远红不到。换成咬「声明了却用不上」；「摘发射腿 ⇒ 裁定过期」
   那把刀移交 `tests/test_r550_counter_evidence_teeth.py`（影子树 K1）。

## §5 未达的格子（明写，不洗）

- **产品面有没有真的往 `retrieval_traces` 写过一行**：未达。本单只让量具看得见「道」，库里这张表
  今天仍读 0 行；判据②要的是量具自洽，不是端到端行为读数。要宣布「问答真的落了行」还欠一次
  真机往返（要容器），那是下一扇窗的活。
- `--verify-live`：未跑（要读库，本单零容器）。本纸引用的库内数字全部来自盘上文档第五节那份在册读数。
- 全量回归门：未跑（`scripts/run_gate.py` 归总控独占）。本单只交定向件。
- 干净树复跑（判据④第二遍）：由总控在并树后代跑；本单按令只交 dirty 态。
- 扫描耗时：新爬法下全树八枚现扫从 9.4 s 抬到 15.0 s（执行层自报，同一 DOC/payload 对拍）。
  影子树六把刀因此合计 ~2 分钟；门里的成本请总控判断。

## §6 时间闸与本机机械教训（自陈）

- 18:15–18:35 闸内：只做静态读与 AST/字节读数，未起 pytest。闸内之前我投过一枚在册 r483 件的
  pytest，会话被线程重置吞掉、读数未取得——那笔不算自证，本纸的 r483 读数以门绿之后那次为准。
- 门禁口令（主树全量门在跑）期间：零 pytest、零子进程量具；期间只写盘与做进程内毫秒级静态自查。
- 本机 `apply_patch` 对多行补丁仍不可用：本单全部走 `exec_command` + PowerShell **单引号 here-string**
  落临时 .py/frag，读—改—写回同一枚命令内完成，锚点 `assert count==1`（K3b 是 `count==2`）当场判命中数。
- 🔴 判 CRLF/BOM 必须在**原始 bytes** 上判：`event_type="retrieval.completed",` 这类单行锚在 CRLF 原文里
  命中数正常，但**多行锚**（`"    if context is None:" + NL + "        return None" + NL`）在 raw bytes 上
  命中 0、在 `read_text()`（通用换行归一）上命中 1。刀里的读取一律走 `read_text()`，锚点检查也走它，
  所以两边同口径；这条如果反过来写（raw 判存在、text 判替换）就是一枚永不咬合的死牙。
- 新钉两枚一律 CRLF 落盘（`core.autocrlf=true` 且无 `.gitattributes`）；`git ls-files --others --eol`
  读数见 §7。生成件那份维持它本来的 `i/lf w/lf`（由 `--sync` 以 `newline=chr(10)` 写，未手改行尾）。
- PowerShell 驱动的坑（本单新踩，记给下一班）：含中文路径的 `.ps1` 若无 BOM，会被 PS 5.1 按 ANSI 解析，
  `Set-Location`/解释器路径全成 mojibake，表现为「五段秒过、rc 全空」。正解：写 `.ps1` 时带 UTF-8 BOM，
  或直接在本席 shell 里跑。

## §7 盘面（追平 `f3f24b6` 后现取）

```
基点与脏件（2026-10-01 00:04 现取，全部在 be-r550；主树 f3f24b6 零改动）：

```
$ git -C be-r550 rev-parse HEAD
f3f24b623c8a52361ed3d8ffd756510dbe1cc948

$ git -C be-r550 diff --numstat
19	9	docs/testing/r483-empty-tables-2026-09-29.md
435	47	scripts/r483_empty_tables_triage.py
23	15	tests/test_r483_empty_table_triage_is_derived.py

$ git -C be-r550 diff --cached --numstat
（空——本单零 `git add`，暂存区干净）

$ git -C be-r550 status --porcelain
 M docs/testing/r483-empty-tables-2026-09-29.md
 M scripts/r483_empty_tables_triage.py
 M tests/test_r483_empty_table_triage_is_derived.py
?? docs/testing/r550-event-hop-climb-2026-09-30.md
?? tests/test_r550_counter_evidence_teeth.py
?? tests/test_r550_event_hop_climb_is_generic.py

$ git -C be-r550 ls-files --eol -- <三枚在册件>
i/lf    w/lf    attr/                 	docs/testing/r483-empty-tables-2026-09-29.md
i/lf    w/crlf  attr/                 	scripts/r483_empty_tables_triage.py
i/lf    w/crlf  attr/                 	tests/test_r483_empty_table_triage_is_derived.py

$ git -C be-r550 ls-files --others --eol -- <三枚本单新件>
i/      w/crlf  attr/                 	docs/testing/r550-event-hop-climb-2026-09-30.md
i/      w/crlf  attr/                 	tests/test_r550_counter_evidence_teeth.py
i/      w/crlf  attr/                 	tests/test_r550_event_hop_climb_is_generic.py
```

行尾归位口径：生成件保持它本来的 `i/lf w/lf`（`--sync` 以 `newline=chr(10)` 写，本单未手改行尾）；
其余四枚 Python/文档新件一律 CRLF（这台机 `core.autocrlf=true` 且无 `.gitattributes`）；
两枚在册件（脚本、测试件）改前改后都是整档 CRLF、lone LF=0、无 BOM——铺树时请按上表逐枚归位。
```
§8 跑数窗口跨了零点：门绿口令 23:4x 收到，五段定向跑数在 23:52:44–00:04:15 之间串行完成（全程 `-o addopts=`、零 `-n`、零 `run_gate.py`）；纸名沿用开工日 2026-09-30。
§9 待总控裁（本单不自作主张）：
- 全树八枚现扫从 9.4 s 抬到 15.0 s（执行层自报，同一 DOC/payload 对拍），门里的增量成本请裁；
- `BFS_NODE_CAP=60` / `hop>5` / `BFS_CALLERS_PER_NODE=8` 在新爬法下的余量（`retrieval_traces` 现扫 nodes=24、桥 6 枚）——本单不敢自行放宽；
- `definition()` 「同名只认按文件名排序第一枚」的旧口径仍用在 `validate()` 的 `blocked_at` 腿上，沿边 BFS 已不走它，是否另立单收紧请裁；
- 生成件里两枚 noise note（`app/api/v1/alerts.py:5`、`scripts/r220_packing_loss.py:13` 的「调用点在模块级」其实是文档串行被当成调用点），要不要收掉请裁——本单宁可留噪声也不放宽爬法；
- 交工纸命名如需改成 2026-10-01，请示下（本席不自己改名，免得并树时坐标对不上）。