# R630 · 观测面那句「`first_token_at` 落在哪」：现读取证、派生化，与一把放宽了的枚数尺

执行层代号 **Shannon**｜树 `be-r630`｜分支 `codex/be-r630`｜基点 `4da0bad`｜日期 2026-10-04
写域：`app/api/v1/observability.py` ＋ 新建 `tests/test_r630_*.py` ＋ 本纸。盘上不 commit，货交总控验收。

## 0. 一句话结论

- **甲（原 R537 那一格）在基点上已经不是假话**：`bridge_note` 那句今天由 `_slo_bridge_note(members, bridge)`
  现派生，句子与分母都不带手抄数字——那一格由 R533 并树（`4376648`）收掉了。本单**不重抄** R533 的牙，
  补的是它那把尺的**覆盖面**（只量了 `slo_units`／`_slo_bridge_note` 两枚函数，整本对外回执里别的散文一枚没量）。
- **乙（跟进单 §165.3 那一格）确实假**：旧句子把 `first_token_at` 的落点抄给 `app/trace/store.py`，而那枚文件
  全文零命中这一格。本单已改成指真源（文件＋符号名，**零行号**），并配上「文案点名的每一格断言 ↔ 一枚现读谓词」的牙。

## 1. 甲｜桥话那格的现状（现读，不是推断）

```
命令：.venv\Scripts\python.exe -c "from app.api.v1.observability import slo_units; print(slo_units()['model_budget_tier']['bridge_note'])"
读数：not one-to-one: 1 budget tier of the 7 is shared across lanes: lanes `analysis` and `report` on tier
      `analysis`; 5 budget tiers of the 7 are named by no lane: `plan`, `compress`, `rewrite`, `code` and `alert`
```

```
命令：git -C be-r630 log --oneline -1 -- app/api/v1/observability.py
读数：4376648 并树 R533（施工 Schrodinger/01a0f03b-d447-7d10-b752-0796872d9667，树 be-r533@05bec06）：
      observability 的 bridge_note 那句手写枚数改派生
```

`docs/handoff/2026-09-30-v2-gap-recheck-3.md` 那两行（`:137` 立案格 / `:216` 工单格）本来就写着 R537「**默认不投**：
只有 R533 交回时没收到这格才投」。R533 交到了，所以本单收到的「把枚数改派生」这一格在盘上已是完成态；
🔴 本单没有为了「有货可交」去重写那一枚已并树的派生器。

### 1.1 本单补的那一格盲区（这才是 R630 在甲上真做出的东西）

R533 那把尺 `COUNT_IN_PROSE` 只作用在两枚函数的源文字面量与 `bridge_note` 那一枚成品串上。
`tests/test_r520_counter_evidence_teeth.py` 记的就是这一族病：**纸面判据为真，别处压根没有尺**。
所以本件 `roster_count_offenders()` 把同一枚正则（复用 `r533.COUNT_IN_PROSE`／`r533.SPELL_NUMBERS`，不另抄一把）
铺到 `slo_readout()` 交回的**整本对外回执**的每一枚字符串叶子上，两种形状一起判：

- 英文词写名册枚数（`six … budget tiers` 那一形）＝手写，一律红；
- 数字写名册枚数而对不上现取派生读数（`6 budget tiers`，派生＝5）＝手写，红。

派生允许集 `derived_tally()` 逐枚现取：`ModelTier` 枚数、`LANE_TIERS` 桥枚数、无对属枚数、共用枚数、
`CANONICAL_STAGES` 枚数、`slo_tiers()` 行数——一枚数字都不写在纸上。

## 2. 乙｜`first_token_at` 的真链路（现读取证）

```
命令：rg -n "first_token_at" app/trace/store.py app/storage/persistence.py app/common/stage_timing.py
读数：app/storage/persistence.py:407:            "first_token_at",
     （store.py 与 stage_timing.py 各 0 枚）
命令：rg -n "first_token" app/ | 逐枚
读数：app/agents/nodes.py 三处 mark_first_token() 调用｜app/trace/spans.py 四处（字段、落戳、载荷）
     ｜app/trace/schema.py 一处（列名册）｜app/trace/projections.py 一处（折行）
     ｜app/storage/persistence.py 一处（落盘白名单）｜app/api/v1/observability.py 两处（被单的这句话＋引用它的 blocker 名）
```

链路（文件＋符号，纸上不写行号）：

1. 落戳 `app/trace/spans.py::ExecutionSpan.mark_first_token`（字段就在同一枚 dataclass 上）；
2. 发帧 `app/trace/spans.py::ExecutionSpan.finish` 把 `first_token_at` 放进 finished 载荷；
3. 折行 `app/trace/projections.py::project_span`（`collection == "model_calls"` 那一支）把它折进执行行；
4. 列名册 `app/trace/schema.py::TRACE_TABLE_COLUMNS["model_calls"]`（`project_span` 的空行骨架就是按它铺的）；
5. 写库 `app/storage/persistence.py::PostgresPersistenceAdapter.upsert` → `_prepare` → `_statement`，
   列集合取 `app/storage/persistence.py::_TABLES["model_calls"].columns`；
6. `app/trace/store.py::TraceStore.record_event` 只把 sealed projection 推给 adapter，**它自己一处 `first_token_at` 都没有**
   ⇒ 旧那句「persisted (`store.py` 那一枚抄来的坐标)」是假话；那一行今天躺的是一枚关于 `SEQUENCE_ATTEMPTS` 的注释；
7. 账本确实不经手：`app/common/stage_timing.py::samples_from_span_payload` 与 `StageSample` 零命中，
   `app/trace/spans.py::ExecutionSpan._observe_stage` 交给账本的只有 duration／started／completed／status 那一族
   ⇒ 「不是 stage sample」这句话本身是真的，**假的是它抄的那个落点**。

### 2.1 改的那一句（before → after，逐字）

```
before：first_token_at is recorded on a model span (app/trace/spans.py:174) and persisted
        (app/trace/store.py:259), but app/common/stage_timing.py:330-345 never reads it into
        a sample, so 首屏 is computable per trace and not from the in-process ledger.

after ：first_token_at is stamped by ``app/trace/spans.py::ExecutionSpan.mark_first_token`` and
        emitted on the finished model span by ``app/trace/spans.py::ExecutionSpan.finish``;
        ``app/trace/projections.py::project_span`` folds it into the model_calls row, whose columns
        are the roster in ``app/trace/schema.py::TRACE_TABLE_COLUMNS``, and
        ``app/storage/persistence.py::PostgresPersistenceAdapter.upsert`` writes it, taking the
        column set from ``app/storage/persistence.py::_TABLES`` -- ``app/trace/store.py`` pushes
        sealed projections and names no column; ``app/common/stage_timing.py`` folds finished spans
        into ledger samples yet its ``samples_from_span_payload`` builds a ``StageSample`` with no
        field for it, so 首屏 is computable per trace and not from the in-process ledger.
```

句子长了一倍是有原因的：它现在把**五枚经手的落点**逐枚点名，本件才能给每一枚配一条现读谓词；
短的那句只能靠读者信一个抄来的行号。

## 3. 牙的形状约定（钉与刀共用同一枚代码）

- 带 `::符号` 的锚点＝声称该文件**确实经手**这一格 ⇒ 那枚文件必须现读带着它（`carriers()` 扫 `app/**`），
  那个符号必须现读解析得到（`importlib` + 逐段 `getattr`）；
- 只写文件名不写符号＝声称它**不经手** ⇒ 那枚文件必须现读没有它，且所在分句带否定词（分句按 `;` `,` ` -- ` 切）；
- `文件.py:数字` 这种形状＝手抄坐标 ⇒ 那一格里一枚都不许有；
- 文案点名的每一格断言都配一枚 `CLAIMS` 谓词（名册带不带这列／INSERT 点不点得到／投影折没折进去／
  账本有没有开始吃它），期望值写在表里，**现读反了才红**；
- 真链路每一腿的文件都必须被点名（`chain_violations`）⇒ 落点搬家而句子不改，当场红。

按形状而非按枚数：派生源动了（K5 往名册里把那枚列摘走、正件里往 `ModelTier` 影子注一档）句子不改就红；
反过来只把句子改成另一枚「看着对」的数字（K2／K6／K7）也照样红——所以这不是枚数钉。

## 4. 反证刀（`tests/test_r630_counter_evidence_teeth.py`，全程内存影子，盘上零字节改动）

| 刀 | 摘的那一格 | 实取红读数（点名那一支） |
|---|---|---|
| K0 | 整格退回基点那句硬编 | 「抄了行号坐标：[…3 枚]」＋「锚点声称 `app/trace/store.py` 经手这一格，现读没有」＋「真链路上写 INSERT 那枚文件…文案没点名它」 |
| K1 | 落盘那一腿改指 `TraceStore.record_event`（符号解析得到） | 「经手这一格」那支红；`解析不到` 一支**没**红（本件另开一枚用例钉住红的是哪一支） |
| K2 | 句尾再补一枚坐标 | 「抄了行号坐标」那支红 |
| K3 | 「账本不经手」改口成「账本经手」 | 「`stage_timing.py` 那一支不带否定词」那支红 |
| K4 | 整条落盘句子删掉 | `chain_violations`：`persistence.py` 没被点名 |
| K5 | `_TABLES["model_calls"]` 里摘走这枚列（文案一字不动） | CLAIMS：「文案声称『落盘白名单里带着这一格』，现读不是（锚点 `_TABLES`）」 |
| K6 | 桥话退回手写枚数（英文词 ＋ 错数字两种写法） | 整本回执那把尺：两种写法各红一枚 |
| K7 | 手写枚数躲进 blocker 的 detail（R533 那把旧尺扫不到的那一格） | 同一把尺红——本单补的正是这一格盲区 |

每把刀都带正控（`test_the_same_machinery_with_no_edit_reports_nothing`：同一套机械不摘刀＝零违规），
总清点那一枚用例拒「没真摘过的刀／没真咬红的钉」，并逐枚核 11 枚被跟踪文件的 sha256（含契约与本纸之外的所有只读件）。

## 5. 自跑读数（两态，2026-10-04 现取）

| 态 | 树 | 跑的文件 | 读数 |
|---|---|---|---|
| apply（已 apply 未 commit） | `be-r630`（dirty＝本单三枚货） | `tests/test_r630_first_token_pointer_is_derived.py` ＋ `tests/test_r630_counter_evidence_teeth.py` | **22 passed / 3.49 s** |
| apply 态同名族在册件 | 同上 | r533 两枚 ＋ r526 两枚 ＋ r105 ＋ observability_routes ＋ r51 ＋ r257 | **182 passed / 54 warnings / 16.50 s**（10 枚文件一起） |
| apply 态收口合跑 | 同上 | 8 枚同名文件（不含 r51／r257） | **133 passed / 48 warnings / 14.73 s** |
| clean（HEAD ＋ 只有这三枚货） | `git archive 4da0bad` 导到 `%TEMP%\eb103_r630\clean`，只投本单三枚货 | 同 apply 的第一行 | **22 passed / 4.20 s** |
| clean 收口合跑 | 同上 | 8 枚同名文件 | **133 passed / 48 warnings / 15.13 s** |

两态数字同为 22／133：本单没有「判据把此刻盘面脏不脏当条件」那种自毁钉——
`observability.py` 的行尾在收口时统一成 CRLF（与基点 checkout 那副样子逐字节同形，LF 归一后的 sha256
改前改后相等：`FECD956F…3D59AD`），三枚新件按主树在册行尾落成 LF、零 CR。

🔴 clean 态那一列的形状说清楚：导出树里没有 `.git`（所以收席时 `dirty` 只能按「HEAD＋这三枚文件」计），
且 `tar -x` 在 Windows 的码页下**没能解出中文名的样例文档**（`documents/*.txt` 那一批报 Invalid empty pathname），
`app/` `tests/` `docs/` 全部解出——本单的判据只读 `app/**` 与 `tests/**`，那两棵都在，读数有效。
解释器与依赖走同一枚 `.venv`（`be-r630\.venv` 是指向主树虚拟环境的 Junction，`app` 在导出树里现读解析到
`…\clean\app\api\v1\observability.py`，不是主树那一份——这一步是本单亲自 print 过 `__file__` 的）。
全量门按硬规**没跑**。

## 6. 🟡 本单不修的在册账（登记，字节未动）

1. **契约那一行还抄着旧落点**：`docs/api/contract-v1.md` §6 名册表里 `first_token_not_a_stage_sample`
   那一行仍写「recorded (`spans.py` 的某行) and persisted (`store.py` 的某行)」，且它上一行自称
   「Each code is emitted in-band … with the same detail text」——现在代码与纸面**不同文**了。
   🔴 契约在 R630 写域之外，本单一字未动；建议总控把 §2.1 那句 after 原样贴进 §6 那一行。
2. **观测面还剩 11 枚手抄行号**，本单只治被派工点名的那一格。现取：
   ```
   命令：rg -o -n "[A-Za-z_/]+\.py:[0-9]+" app/api/v1/observability.py | Measure-Object
   读数：11 枚（躺在 10 行里）
   其中随回执交外的 6 枚：owns_the_name 那格 contracts.py:69 ＋ blockers 的 detail 五枚
     （spans.py:201-215／chat.py:218-243／chat.py:1191-1215／orchestrator.py:1173-1185／stage_timing.py:71）
   其余 5 枚躺在注释与 docstring 里：performance.py:27-28／observability.py:333／
     contracts.py:69（slo_units 的 docstring）／stage_timing.py:48（同一行注释，今天还对得上）／
     model_budget.py:769
   ```
   本席顺手量到其中几枚**已经漂**（读数是 2026-10-04 那一枚「丙类·当时那一次的读数」，不是当下声称）：
   `app/agents/contracts.py:69`（`ModelTier` 现在 70 行）、`app/common/stage_timing.py:71`
   （`TOOL_TO_STAGE["export_report"]` 现在 73 行）、`app/agents/orchestrator.py:1173`
   （`step.progress` 现在 1450 行）、`app/api/v1/chat.py:1191`（`StreamingResponse` 交回点不在这枚行号上）、
   `app/api/v1/chat.py:218`（`text_sse_frame` 现在 262 行）。
   `app/trace/spans.py:174`／`:201-215` 与 `app/common/stage_timing.py:330-345` 三枚今天还对得上位置，但同样是抄的。
   ⇒ 建议另立一单：把这几枚一律换成 `文件.py::符号` 锚点，并把本件 `prose_shape_violations` 那把尺
   从「那一格」放宽到「整本 `SLO_BLOCKERS` ＋ `owns_the_name` 那几格」；本单不动，理由＝写集与判据边界，
   其中 `owns_the_name` 那枚 `contracts.py:69` 另有一层要分清：
   ```
   命令：rg -n "line numbers are a dated snapshot" docs/api/contract-v1.md
   读数：契约同一节开头就声明「行号是当日快照」，所以**纸面**那一枚按快照口径算；
        代码那一格却是随 GET /api/v1/slo 交出去的当下声称，今天对不上（ModelTier 现读在下一行）。
   ```
   ⇒ 该治的是**代码把快照当读数发出去**这一形，不是纸面那一行；只把代码改成符号锚而不写清口径，
   就又造出一格「两本口径各说各话」——那正是 R537 立案的病根形状，所以要连口径一起改。
3. **派工词的第一格前提已过**：R537 的账（跟进单 `:216` 那行「默认不投」）今天已由 R533 并树兑现，
   建议总控在跟进单上把它按「已由 R533 收到」结案，别再按「待修」挂着。

## 7. 未验／量不到（照实写）

- **真库里那一枚值落没落**：本单只量到「组出来的那条 INSERT 点得到这枚列」为止——硬规禁动容器／动库，
  所以 `model_calls.first_token_at` 在生产的非空率今天**没量**。
- **全量门**：按硬规没跑（总控在测量窗里）。
- **K3 的咬合只覆盖「否定词那一形」**：若下一班把句子改成既点名 `stage_timing.py` 又带着否定词的假话
  （例如「…never persisted by stage_timing.py…」这种语义对、指法错的写法），本件的尺认得出「不经手」的形状，
  但认不出「这句话读起来别扭」。要更硬的判据得让那句话本身派生化，那是另一单的活。

## 8. 现取命令（复跑凭证）

```
git -C C:\Users\fengx\PycharmProjects\be-r630 status --porcelain
.venv\Scripts\python.exe -m pytest tests\test_r630_first_token_pointer_is_derived.py tests\test_r630_counter_evidence_teeth.py -q
.venv\Scripts\python.exe -m pytest tests\test_r533_bridge_note_is_derived.py tests\test_r533_counter_evidence_teeth.py tests\test_r526_slot_caliber_closure.py tests\test_r526_counter_evidence_teeth.py tests\test_r105_slo_contract.py tests\test_observability_routes.py -q
```
