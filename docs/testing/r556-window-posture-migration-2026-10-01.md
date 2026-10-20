# R556｜五扇 `execs_module = True` 旧姿势窗迁到 `install_mutation`——姿势面读数（总控接手代做）

判据出处＝跟进单 §141 第三节 R556 七格。写域＝只 `tests/**`＋本纸。零产品码。

**接手来历（不遮掩）**：原执行层 `Hume`（`01a0f0e6-…`）于 10-01 22:5x 接单，10-02 00:01 写下七枚件的改动后**死于 provider 403 `AccessDenied.Unpurchased`**，没交回、没读数。总控 10-02 接手：逐行审它那 7 枚改动（296  insert／70 delete），采纳并补齐它引用却没写的两枚产物（新钉 `tests/test_r556_window_posture_is_installed_not_executed.py`＋本纸）。🔴 因此本单一半是「执行层自报」都不算——姿势面是总控现扫，行为面是总控待跑。

## §一 姿势面现扫（静态可证，命令原文 → 读数）

量具：逐枚 `ast.parse` 认**类体内的赋值语句**，注释与 docstring 里的字样一律不算（这一族散文在 `tests/` 里有九处：r303/r310/r337/r353/r354/r373/r381/r388/r466）。

- 扫描范围＝`tests/test_*.py` **593 枚**（`Path('tests').glob` 现取，非抽样）
- 真赋值 `execs_module = True` 现取 **2 枚**，且**两枚都在本单写域之外、明写不许迁**：
  · `tests/test_r482_registered_ceiling_is_the_ceiling.py:324` 类 `_ClampEdit`（越界不迁，坐标交回）
  · `tests/test_r553_counter_evidence_teeth.py:54` 类 `_Probe`（它量的就是 exec 姿势本身，迁了就没牙）
- 判据③ 要求的形状达成：在册姿势表里「exec 活模块」的名单由 `["r48"]` 缩到 **`[]`**——`r48` 现在走 `install_mutation` 只装变了的那几枚顶层绑定，开窗器从裸 `_TempEdit` 换成件自己那枚 `_chat_window`（裸 `_TempEdit` 在今天只落影子根、不碰活模块，拿它当窗会读成空转刀）。
- 四扇迁移姿势的把手用量（现扫字符串出现次数，只作形状证据）：`r472` `install_mutation`×5；`r478` `install_mutation`×3＋`isolated_module`×5；`r48` ×2；`r495` ×3。
- `py_compile` 八枚（新钉＋覆盖层＋六枚在册件）**rc=0**（10-02 17:4x 总控亲跑）。这不是测试，只保证没有语法层低级红。

## §二 `isolated_module` 为什么必须有（判据④「不许迁成空转刀」）

`r478` 那把刀落在 Pydantic 模型类里，而 `description` 是在**类创建那一刻**烘进 JSON schema 的：只把那枚类绑定换掉，活路由上的端点仍指着旧类，发布的文档还是旧句——刀迁成空转，比不迁更坏。所以变异要真被执行就得装进一枚隔离对象（正例姿势在 `tests/test_r457_audit_retention_execution_leg.py`）。落点：`tests/_temp_edit_overlay.py::isolated_module`（＋16 行，唯一新增把手）。
落在顶层类上的另一支走 `install_mutation` 的类分支：在**活命名空间**里现编那一枚类语句，方法体的 `__globals__` 才是这一枚模块的字典，窗内由 monkeypatch 装的夹具替身才看得见；出窗仍按进门那一刻的值逐枚装回，没点名的绑定一枚都不动。

## §三 还没证的格（🔴 全部待收窗后总控亲跑，跑之前本单不许宣布达标）

| 判据 | 欠的读数 | 谁跑 |
|---|---|---|
| ① 逐扇「窗内变异仍真被执行」原证 | 每扇一枚，指纹命中影子副本那份 | 总控亲跑 |
| ② 同进程配对（迁前污染→迁后全绿） | `r466 自证 ↔ test_r303_notification_pins::test_the_counter_evidence_window_touches_no_tracked_file`；`r495 ↔ test_r499_…_any_file_order`；`r353 ↔ test_r301_upload_readout`。10-01 在 HEAD 上配对实取是 **2 failed**，迁完必须 0 failed | 总控亲跑 |
| ④ 两态摘刀 | 摘守卫必须红；摘迁移必须让配对重新污染 | 总控亲跑 |
| ⑥ 两遍数字 | dirty 一遍＋commit 后干净树复跑，文件清单逐枚点名（`fa1cf3e`／#96 那族） | 总控亲跑 |
| 与 `_eb_r563_live_module_guard` 不对撞 | 迁移前后守卫各出手几次（现取），且 `test_r563_live_module_callables_do_not_leak.py` 五枚一路须绿 | 总控亲跑 |
| 门里那枚红 | `test_r48_headline_card_lands_on_the_wire.py::test_counter_evidence_c2` 的 teardown 被 R563 点名（`app.api.v1.chat` 六枚顶层可调用没还账，原文 `KeyError 'excerpted_quote'`）——本单正是治它 | 总控亲跑 |

另记一笔**接手时我自己犯的**：17:3x 我据「覆盖层顶部没有 `import ast`」判这半成品必炸，**查错了层**——`install_mutation`/`_top_level_class_names` 定义在 `tests/test_r466_…` 里，那枚件 `:58` 就有 `import ast`。已当场撤回。口径照旧：说「某物不存在」之前先报在哪一层查。

## §四 本单一手证据的复现命令

```powershell
cd C:\Users\fengx\PycharmProjects\企业智脑
& '.venv\Scripts\python.exe' -X utf8 -m py_compile tests/test_r556_window_posture_is_installed_not_executed.py tests/_temp_edit_overlay.py
# 全仓姿势现扫（AST 认赋值，不认字样）
& '.venv\Scripts\python.exe' -X utf8 -m pytest tests/test_r556_window_posture_is_installed_not_executed.py tests/test_r466_mutation_does_not_leak_into_live_module.py -q
```