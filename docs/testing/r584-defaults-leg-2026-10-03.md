# R584 · `__defaults__` 那一腿换成结构尺（2026-10-03）

执行层 R584，独占工作树 `C:\Users\fengx\PycharmProjects\be-r584`，基点 `dfc057b`。
解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe -X utf8`。
本单没有 commit、没有 push、没动容器、没打模型、没跑 `scripts/run_gate.py`、没起 `-n` 并发、没碰主树。

## 0. 交回盘面（现取）

| 项 | 读数 |
|---|---|
| `git -C be-r584 rev-parse --short HEAD` | `dfc057b`（按派工词不 commit，HEAD 未动） |
| `git -C be-r584 diff --numstat HEAD` | `132 4 tests/conftest.py`（只有写域这一条） |
| 未跟踪清单 | `tests/test_r584_the_defaults_leg_compares_structure_not_identity.py` |
| `chroma_db/chroma.sqlite3` | **没被顶脏**：`diff --numstat HEAD` 里不出现这一条（R134 闸门把 4 次 `PersistentClient` 全改道到 `%TEMP%`，见下面 §5） |
| basetemp | 全程 `%TEMP%\r584*` 独占（`r584pre2 / r584preF / r584preR / r584post2 / r584post2b / r584postF / r584postR / r584smoke / r584new1 / r584ext / r584probe / r584probe2 / r584p2`） |

## 1. 病与改前三枚现取读数（判据 1）

派工词给的机理本席逐条复现过，没有一条照抄。

### 1.① 最小复现原文＋rc＋点名

```
$ cd C:\Users\fengx\PycharmProjects\be-r584
$ python -X utf8 -m pytest tests/test_r48_headline_card_lands_on_the_wire.py tests/test_phase9_private_deps.py -q -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r584pre2 -p no:randomly --tb=short
=================================== ERRORS ====================================
_ ERROR at teardown of TestOptionalPsycopgImports.test_chat_and_alerts_import_without_psycopg _
R563：本模块出门把活模块的顶层可调用绑定换成了自己的假身，没还回去。
  - app.api.v1.chat.upload_document：盘上那一版 app.api.v1.chat.upload_document 被换成 app.api.v1.chat.upload_document
...
ERROR tests/test_phase9_private_deps.py::TestOptionalPsycopgImports::test_chat_and_alerts_import_without_psycopg
21 passed, 4 warnings, 1 error in 18.69s
RC=1
```

点名只有 `app.api.v1.chat.upload_document` 一枚，受害者文件只有 `tests/test_phase9_private_deps.py` 一枚。

### 1.② `upload_document.__defaults__` 两版的型与身份（证「同型不同实例」）

诊断件（临时件 `tests/test_r584_probe.py`，读数取完已删，未进交付清单）在 pytest 里跑
（必须在 pytest 里跑：conftest 的 R56 端口闸门先把模型发现换成离线桩，绕开它就是打宿主 Ollama）：

```
[r584probe] watched module app.api.v1.chat: 166 funcs before, 166 after
[r584probe] upload_document defaults len old=4 new=4
[r584probe]   [0] old=fastapi.params.File new=fastapi.params.File is_same=False eq=False code_eq=True
[r584probe]   [1] old=fastapi.params.Form new=fastapi.params.Form is_same=False eq=False code_eq=True
[r584probe]   [2] old=fastapi.params.Form new=fastapi.params.Form is_same=False eq=False code_eq=True
[r584probe]   [3] old=builtins.NoneType new=builtins.NoneType is_same=True eq=True code_eq=True
```

逐语义位（`default`／`default_factory`／`annotation`／`embed`／`alias`／`title`／`description`／
`metadata`／`json_schema_extra`／`media_type`／`include_in_schema`／`examples`／`openapi_examples`）
在 reload 前后**每一位都相同**（`metadata=[]`、`json_schema_extra={}` 两枚是"不同实例同值"，其余连对象都同一枚）。
四腿读数：`co_name=True co_qualname=True co_code=True defaults_eq=False code_identity=False`。
`__kwdefaults__` 前后都是 `None`。

类那一头也现取过：`fastapi.params.File.__mro__ = (File, Form, Body, pydantic.fields.FieldInfo,
pydantic._internal._repr.Representation, object)`，`"__eq__" in FieldInfo.__dict__` → **False**，
`FieldInfo.__eq__ is object.__eq__` → **True** ⇒ `File(...)` == `File(...)` 恒 False（身份比较）。
`repr(File(...))` = `File(PydanticUndefined)`（pydantic 的 `Representation` 只渲染 `default`）。

### 1.③ 同模块其余顶层函数的漂移计数（应为 0）

```
[r584probe] functions failing the 4-leg same(): 1 -> ['upload_document']
[r584probe] OTHER top-level funcs drifting (must be empty): []
```

166 枚顶层函数里带默认值的 27 枚，默认值的材料清点（第二枚临时件 `tests/test_r584_probe2.py`，同样已删）：

```
[r584p2] top-level funcs: 166 | no-defaults: 139 | with defaults: 27
[r584p2] default value types: {'builtins.NoneType': 18, 'builtins.str': 10, 'builtins.int': 3,
    'builtins.tuple': 1, 'builtins.bool': 1,
    'pydantic_core._pydantic_core.PydanticUndefinedType': 2,
    'fastapi.params.File': 1, 'fastapi.params.Form': 2}
[r584p2] funcs carrying defaults: [..., ('File', ('PydanticUndefinedType',)), ('Form', ('PydanticUndefinedType',)),
    ('upload_document', ('File', 'Form', 'Form', 'NoneType'))]
```

⇒ 只有 `upload_document` 这一枚装着**由模块源码在每次 exec 时新造**的 `File()/Form()` 实例，
所以只有它恒漂。旁证形状与派工词一致（"同码体、只因重载换了实例"，不是"有人留了假身"）。

## 2. 改了什么（判据 2：腿不摘，只换比较口径）

`tests/conftest.py`（唯一被改的在册件，`+132 / -4`）：

1. 新增 `_EB_R563_FIELDINFO_SLOTS`（15 位语义位清单）与四枚判据本体：
   `_eb_r563_repr_matches` / `_eb_r563_slot_same` / `_eb_r563_is_fieldinfo` /
   `_eb_r563_values_same` / `_eb_r563_defaults_same`。
2. `_eb_r563_same` 第四腿从
   `getattr(a, "__defaults__", None) == getattr(b, "__defaults__", None)`
   换成 `_eb_r563_defaults_same(getattr(a, "__defaults__", None), getattr(b, "__defaults__", None))`。
   `co_name`／`co_qualname`／`co_code` 三条腿一字未动。
3. 🔴 顺手补了改前那把尺的一个反向漏洞（判据 2 的字面要求）：原尺在
   `if ca is None or cb is None or ca is cb: return ca is cb` 这一支上，**码体是同一枚对象时
   压根不看默认值**——那正是派工词禁止的"只要 co_code 相同就跳过 defaults"的形状。
   现在拆成两支：`ca is cb`（借体造人，`FunctionType(真身.__code__, ...)`，r466 `_rebase` 就长这样）
   这一支**也**把默认值比完；多腿那一支照旧比四条。
   在册钉 `tests/test_r563_live_module_callables_do_not_leak.py::test_jia_...` 要求的
   `ca.co_code == cb.co_code` 原文仍在。

口径本体（写死在 conftest 的注释与钉里，不是"看起来更宽"）：

- 形状先卡死：`None`（压根没默认值）与任何元组不等；`type` 不同不等；长度不同不等。
- 逐位：同型 → `pydantic.FieldInfo` 一族走 15 位语义位 + repr 兜底；函数型默认值
  （`default_factory` 那一族）按码体三条判（reload 重造的是同一枚身体）；其余先按值 `==`，
  比不动才退到「同型 + 不带内存地址的同 repr」。
- `repr` 回退不白送身份：`object.__repr__` 那一族的 repr 里带 ` at 0x...` ⇒ 两枚不同实例必然不同字。
  带自定义 `__eq__` 且说"不等"的类型（`ndarray` 那一族）不进 repr 回退：`__eq__` 存在就采信它。
- 已知并刻意的松：值化 repr 又没有 `__eq__` 的类（`types.SimpleNamespace` 那一族）按结构算同一枚值。
  这条写死在册钉 `::test_zi_a_value_rendered_class_without_eq_is_a_deliberate_pass`——
  下一班要么照它改，要么红在这枚钉上，不许静默改口径。

新钉 `tests/test_r584_the_defaults_leg_compares_structure_not_identity.py`（15 枚用例：
甲／乙／丙／丁／戊／己／庚／辛／壬／癸／子 十一枚正证 + K1／K2／K3／K4 四把反证）。

## 3. 反证逐枚点名（判据 3；≥3，本单交 4 把）

每把 victim 全名、摘法、红了哪条、摘前摘后逐字节 sha256 相同（盘上真字节一枚没动，一律进程内影子）。
六枚 sha 范围：`tests/conftest.py`、`tests/test_phase9_private_deps.py`、
`tests/test_r563_live_module_callables_do_not_leak.py`、
`tests/test_r466_mutation_does_not_leak_into_live_module.py`、`app/api/v1/chat.py`、本单新钉。

| 刀 | victim 全名 | 摘什么（进程内） | 红了哪条 | 摘前摘后 sha256 |
|---|---|---|---|---|
| K1 | `tests/test_r584_...::test_yi_a_changed_default_value_is_still_named` ＋ `::test_bing_a_changed_default_type_is_still_named_on_a_shared_code_object` ＋ `::test_ding_a_shorter_defaults_tuple_is_still_named` ＋ `::test_wu_an_embed_bit_is_named_though_the_repr_is_identical` | `_eb_r563_defaults_same` 整条换成 `lambda da, db: True`（`monkeypatch.setitem(conftest 命名空间)`，＝那一腿判据恒真＝整条摘掉） | 四枚 victim 一起红：`守卫一声不响：这一手没被认出来——尺上少了在判的那一条腿（锯腿＝本单没做完）` | 六枚全等（`digests() == before` 钉死） |
| K2 | 同一枚真漏的两个尺子：`tests/test_r584_...::test_k2_...` 内联驱动在册守卫 | 造真漏：`upload_document.__defaults__[0]` 从 `File(...)` 换成 `Form(...)`，借**同一枚码体对象**（`FunctionType(真身.__code__, ...)`）；再把 `_eb_r563_defaults_same` 摘成恒等复跑同一枚漏 | 真尺：守卫红在 `app.api.v1.chat.upload_document`（点名原文见下）；瞎尺：同一枚漏 0 漂移 ⇒ victim `::test_bing_...` 在瞎尺下必红（K1 已演） | 同上 |
| K3 | `tests/test_r584_...::test_xin_a_fake_body_behind_a_reload_still_reddens_its_owner`（＝判据 3 的 K3：phase9 原样 reload 之后**摘掉还原**，真留一份活模块假身） | `_eb_r563_same` 源码里 `ca.co_code == cb.co_code` 换成 `True`（`ast.get_source_segment` 派生文本，`exec` 进影子 namespace） | `守卫一声不响：这一手没被认出来——尺上少了在判的那一条腿（锯腿＝本单没做完）` | 同上 |
| K4 | `tests/test_r584_...::test_wu_an_embed_bit_is_named_though_the_repr_is_identical` | `_EB_R563_FIELDINFO_SLOTS` 换成 `()`（语义位清单清空，尺子只剩 repr） | 同一条「守卫一声不响」⇒ 证明语义位那一层真在判：`File(...)` 与 `File(embed=True)` 的 repr 逐字节相同，只有语义位认得出 | 同上 |

判据 3 要求的三把逐一对上：K1＝"把 `__defaults__` 那一腿整条摘掉 ⇒ 必须红"；
K2＝"造真漏 ⇒ 必须判成漂移并点名该函数"（`_leak_type`/`_leak_value`/`_leak_length`/`_leak_embed`
四枚漏全部点名，且都断言漂移名单**只有**该点名的一枚：`len(drift) == 1`）；
K3＝"摘掉 `importlib.reload` 那一步的还原 ⇒ 在册守卫必须仍红在凶手模块上"——
本单用真尺演：`_phase9_run()` 合法 reload（0 漂移）之后把 `chat.upload_document` 换成
一枚**同名、同 `__defaults__` 对象、只有身体不同**的假身 ⇒ 守卫红在 `app.api.v1.chat` 上，
红落在 phase9 那格形状自己的 teardown 上，R563 原意没被本单洗白。

靶子纯度（一处派工词没提、本单现取的坑）：路由注册时 FastAPI 会**就地改写**默认值实例的
`annotation`——`chat.upload_document.__defaults__[0].annotation` 是 `UploadFile`，而当场新造的
`File(...)` 是 `None`。所以刀一律走 `_twin()`（`copy.copy` 原件 + 只覆盖点名那一位），
否则咬住了也是冤枉。K2 的换型那一把不受影响（`type` 身份在语义位之前）。

## 4. 同名集两向同数（判据 4）

13 枚名单集（与 `docs/testing/r572-window-posture-migration-2026-10-03.md` §3 ① 逐枚同名同序）：
`test_r253_shadow_root_holds_the_mutation / test_r253_no_test_rewrites_a_tracked_file /
test_r572_window_handles_are_derived_not_transcribed / test_r572_the_migrated_window_still_has_teeth /
test_r466_mutation_does_not_leak_into_live_module / test_r48_headline_card_lands_on_the_wire /
test_r48_headline_never_enters_the_text_ledger / test_r303_notification_pins /
test_r310_owner_lookup_cost / test_r353_degradation_note_caps_reason_classes /
test_r373_the_two_remaining_legs_answer_absence / test_r563_live_module_callables_do_not_leak /
test_phase9_private_deps`（均 `tests/` 下）。

| 跑法 | 命令原文（`cd be-r584` 后） | 改前 | 改后 |
|---|---|---|---|
| 最小复现 | `python -X utf8 -m pytest tests/test_r48_headline_card_lands_on_the_wire.py tests/test_phase9_private_deps.py -q -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r584post2 -p no:randomly` | `21 passed, 4 warnings, 1 error`，RC=1 | `21 passed, 4 warnings in 12.57s`，**RC=0** |
| 13 枚正序 | `python -X utf8 -m pytest <上述 13 枚，逐枚点名> -q -o addopts= -p no:cacheprovider --basetemp=%TEMP%\r584postF -p no:randomly --tb=short` | `157 passed, 98 warnings, 1 error in 80.85s`，RC=1 | `157 passed, 98 warnings in 63.28s`，**0 error**，RC=0 |
| 13 枚反序 | 同上，`[Array]::Reverse` 后传入（首 `test_phase9_private_deps.py`、末 `test_r253_shadow_root_holds_the_mutation.py`） | `157 passed, 96 warnings, 1 error in 109.22s`，RC=1 | `157 passed, 96 warnings in 59.03s`，**0 error**，RC=0 |

passed 数一枚没少（157／157／21），error 从 1 → 0（两向都是）。

扩展相邻集（30 枚件＝上述 13 枚 + 本单新钉 + `test_r354_delete_audit_shares_the_owner_reader`
+ `test_r180_row_scope_preview_and_catalog_honesty`（R563 原案的凶手/受害者对）+
`test_r499_the_ownership_predicate_survives_any_file_order` + `test_r516_the_dataset_stubs_stay_on_the_class`
+ `test_test_isolation_guards` + `test_mcp_identity_scope` + `test_private_model_routing` +
`test_retrieval_pipeline_fallback` + `test_r384/r390/r457/r229/r230/r231` + `test_dashboard_summary`
+ `test_deployment_guards`）：`408 passed, 219 warnings in 173.84s`，**RC=0，0 error**。
挑这 30 枚的理由：本单动的是 conftest 里那把"同一枚函数"的尺，射程 = 会 reload／重 exec／
借体造人碰被盯模块（`app.api.v1.data`／`chat`／`app.common.audit`／
`app.agents.orchestrator`／`app.rag.retrieval_pipeline`）的件——`git grep -l "reload" -- tests`
逐枚点名过，一枚不落。

## 5. 零污染（判据 5）

- `git -C be-r584 diff --numstat HEAD` 全程只有 `tests/conftest.py` 一条；
  未跟踪只有本单新钉一枚（两枚临时诊断件读完数即 `Remove-Item` 删除，未进交付）。
- `chroma_db/chroma.sqlite3` **没被顶脏**，无需总控还原。现取凭据（改后 2 枚跑那一次的 R134 闸门自报）：
  `PersistentClient 调用: 4 次，其中落点被改道出工作树: 4 次（0 个原路径）`，改道落点
  `%TEMP%\enterprise-brain-tests-chroma-*`；另有 `[R53] chroma sandbox left behind` 一条 stdout 提示，
  那是 chromadb 还握着 sqlite 句柄，不落在工作树里。
- CRLF 单形：`tests/conftest.py` 896 行 CRLF、0 裸 LF、0 裸 CR、无 BOM；
  新钉 514 行 CRLF、0 裸 LF、0 裸 CR、无 BOM（`apply_patch` 在本机因 CRLF 不可用，
  全程 here-string + `[IO.File]::WriteAllText(UTF8Encoding $false)` 与 venv python 落笔）。
- 单跑口径逐枚带 `-o addopts= -p no:cacheprovider --basetemp=%TEMP%\r584* -q`；
  另加 `-p no:randomly` 与 R572 同名集的口径对齐（口径差异不影响 passed／error 数，两向互比已证）。
- 主树 `企业智脑/` 一次 `git status --porcelain` 都不干净（别的班的写域与一堆非本单的未跟踪件），
  本单**没有**读改它，只在 be-r584 里写。

## 6. 与派工词不符／派工词没提的现取事实（逐条点名）

1. 🔴 **改前那把尺本来就有"码体相同就跳过 defaults"那一支。** 派工词判据 2 写"不许写成
   只要 `co_code` 相同就跳过 defaults"，但 `tests/conftest.py` 原文
   `if ca is None or cb is None or ca is cb: return ca is cb` 在**码体是同一枚对象**时
   直接放行，压根不进 defaults 那一腿。所以"腿仍在判"这句在改前只对"不同码体"成立。
   本单把它拆成两支、`ca is cb` 那一支也走 `_eb_r563_defaults_same`，并把形状钉在
   `::test_geng_the_ruler_wires_the_defaults_leg_into_both_branches`（AST 派生，不抄文本）。
   后果：借体造人（`FunctionType(真身.__code__, ...)` 换默认值）那一族，改前免检、现在点名。
2. 🔴 **`__kwdefaults__` 这一腿压根不在尺上，本单没扩射程。** 现取：`chat` 有 25 枚顶层函数带
   `__kwdefaults__`，其中模块级 `File()`／`Form()` 包装函数的 kwdefaults 里装着
   `fastapi.datastructures.DefaultPlaceholder` 实例，其 repr 带内存地址
   （`<... DefaultPlaceholder object at 0x...>`，本机实测是同一枚单例）。哪天有人加这一腿又按
   身份/repr 比，phase9 那一族冤枉会当场复发。在册 `tests/test_r499_the_ownership_predicate_survives_any_file_order.py:310`
   已把同一形状记为 r466 的射程缺口。本单按派工词只做"换口径不摘腿"，扩射程另单。
3. **单号不一致**：本派工词号 R584；R572 的 commit message 与证据纸
   （`docs/testing/r572-window-posture-migration-2026-10-03.md` §5，`:117-121`）把这一格另立为 **R582**。
   内容与判据逐条对得上，判是同一枚单，号按派工词走 R584。
4. **诊断必须在 pytest 里跑**：派工词没提，本席踩过一次——直接 `python -c "import app.api.v1.chat"`
   会在 import 期就打宿主 Ollama（`retrieval_pipeline.py:34`／`chat.py:74` 的 `ModelHandler()`），
   撞 AGENTS.md 的"打模型"红线。所有读数一律走 pytest 会话（conftest 的 R56 闸门把发现换成离线桩，
   现取自报 `blocked connect attempts to host model port: 0`／`offline discovery stub calls: 1`）。
5. **靶子纯度**：`File()`／`Form()` 的 `annotation` 会被路由注册就地改写（§3 末），
   派工词说"重载出来的 `upload_document` 码体逐字节相同，但默认值是新造的 `File()/Form()` 实例"
   完全成立；补一刀：新造的那枚连 `annotation` 都与原件不同，所以反证靶子必须走克隆+单位覆盖。
6. `fastapi.params.File` 是 `Form` 的**子类**（MRO：`File → Form → Body → FieldInfo →
   Representation → object`）⇒ 本单的"同型"用 `type(a) is type(b)`（身份），不用 `isinstance`：
   `File(...)` 换成 `Form(...)` 在 `isinstance` 尺下会滑过去。

## 7. 没跑的格子（照实写）

- **全量回归门 `python scripts/run_gate.py`：未跑**（派工词明文禁止）。判据 4 的两向同名集 +
  §4 的 30 枚扩展相邻集是本单全部的回归证据，枚数与最新绿票（看板 §4DT 那笔 `5963dfe`
  时点 8479 passed）不可比——本单没跑过全量，不做同数断言。
- 反证"摘盘上真字节"那一族：未做（派工词禁止动盘上真字节，四把刀一律进程内影子／合成输入面）。
- 前端与 `frontend/`：一枚没碰。
- 容器／模型／数据库：一枚没碰。

## 8. 投前自检三件

| 件 | 判据 | 读数 |
|---|---|---|
| 牙没锯 | 判据 2 | `__defaults__` 那一腿仍在 `_eb_r563_same` 两支上（AST 钉 `::test_geng_...`）；四枚语义不同的漏（换值／换型／少一位／翻 `embed`）全部被点名（`::test_yi／test_bing／test_ding／test_wu`），且每枚都断言漂移名单 `len(drift)==1` |
| 三把反证真咬红 | 判据 3 | K1／K2／K3／K4 四把，`15 passed` 里含四枚 `test_k*`；每把 `digests() == before` 过（六枚文件摘前摘后逐字节同 sha） |
| 同名集 0 error 且 passed 不比改前少 | 判据 4 | 正序 `157 passed`（改前 157＋1 error）；反序 `157 passed`（改前 157＋1 error）；最小复现 `21 passed`（改前 21＋1 error）；RC 全部 0 |

## 9. 产物逐枚 sha256（交回那一刻现取，前 12 位）

| 文件 | sha256(12) | 形制 |
|---|---|---|
| `tests/conftest.py` | `31d51669be9c` | CRLF 911 行，0 裸 LF，0 裸 CR，无 BOM |
| `tests/test_r584_the_defaults_leg_compares_structure_not_identity.py` | `0b8c1be09f2b` | CRLF 514 行，0 裸 LF，0 裸 CR，无 BOM |
| `docs/testing/r584-defaults-leg-2026-10-03.md` | 本纸（追加本节后再取，见 §10） | CRLF，0 裸 LF，0 裸 CR，无 BOM |

追加前全纸 sha256(12) = `28ee793b419a`（本节之前的字节读数）。

## 10. 追加后的收尾读数

- 本纸追加 §9 之后：CRLF 单形（追加用字节拼接 `read_bytes() + new.encode("utf-8")`，见跟进单 §102 第一节口径）；§9 表格里那格不自我引用本纸末次 sha——写一次就变一次，末次读数只记在交回词里，总控验收时现取互比。
- 四枚终局跑法读数：
  - 最小复现（改后）：`21 passed, 4 warnings in 12.57s`，RC=0
  - 13 枚正序（改后）：`157 passed, 98 warnings in 63.28s`，RC=0
  - 13 枚反序（改后）：`157 passed, 96 warnings in 59.03s`，RC=0
  - 30 枚扩展相邻集（改后）：`408 passed, 219 warnings in 173.84s`，RC=0
  - 本单新钉 + 在册守卫 + phase9 + r48 合跑（打磨报错文案后复跑）：`41 passed, 4 warnings in 20.37s`，RC=0
- 判据 5 复述：`git diff --numstat HEAD` 只有 `132 4 tests/conftest.py`；未跟踪只有本单新钉与本纸；
  `chroma_db/chroma.sqlite3` 全程没被顶脏，无需总控还原。