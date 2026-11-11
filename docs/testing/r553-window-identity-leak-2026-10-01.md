# R553 · 两扇反证窗把活模块的**身份**弄坏了（10-01 门里现取 · 总控亲修）

单号 R553（本席自修，不占执行层）｜基点 `bdcbc78`｜零 commit 由总控代提交｜`app/**` 零改动、零容器、零模型、零起服务。
解释器一律 `C:\Users\fengx\PycharmProjects\企业智脑\.venv\Scripts\python.exe`。

## 一、现象：门里 28 枚红，7 枚「单文件复跑全绿、并进门就红」

`bdcbc78` 全量门（`-n 4 --dist loadfile`）读数：**28 failed / 9655 passed / 52 skipped / 2 xfailed / 646.99 s**。
拆开：21 枚是并树漂的手抄坐标（R551 `62c8973` 给 `app/api/v1/chat.py` 净插 12 行 ⇒ 凡在其后的行号一律 +12），
已按各自量具给的唯一出路重落地（`r455 --emit-doc-cells` 成品串 5 格、`r387 --emit-doc-cells` §1 表 6 行、
§9.3 列 9 格由 `resolve_site` 现场派生、正文两枚引用改「旧 `:X`→派生今值 `:Y`」）——那是另一本账，见看板。

剩下 7 枚**不是回归**：单文件复跑全绿，两两配对就红。

| 受害者 | 门里红数 | 单跑 | 污染源 | 配对复跑（修前） |
|---|---|---|---|---|
| `tests/test_r301_upload_readout.py` | 4 | 23 passed | `tests/test_r353_...caps_reason_classes.py` 刀3 | `r353 + r301` → 4 failed（`NameError: PDF_DEGRADATION_REASON_GROUP_CAP`，红在 `app/api/v1/chat.py:4403`） |
| `tests/test_r499_..._any_file_order.py` | 3 | 6 passed | `tests/test_r495_session_owner_namespace_is_declared.py`（`execs_module = True`） | `r495 + r499` → 3 failed（`assert X is X` 两枚身份 + 一枚影子） |

两对都在昨日 `f3f24b6` 的门里是绿的：R550 新增两枚测试件 ⇒ `loadfile` 的分发把原本不同 worker 的加害者与受害者排到了一起。
🔴 **潜在病，不是新 introduced 的病**——而它同时能造**假绿**（受害者读到的是别人留下的活模块尸体），所以必须治。

## 二、甲腿：还原面用了只收码体的尺子，于是把常量删了

`tests/test_r466_mutation_does_not_leak_into_live_module.py::install_mutation` 窗尾：

```
original = before_view["objects"].get(name, _MISSING)
if original is _MISSING:
    live_dict.pop(name, None)
```

`live_view()` 的 `objects` **只收带 `__code__` 的绑定**（顶层函数与类的方法）⇒ 落在常量上的刀（r353 刀3
`PDF_DEGRADATION_REASON_GROUP_CAP = 10 → 1`）取不到 `original`，走进 `pop` 分支，把盘上本来就有的那枚常量从
**活模块**上删了。下一格 `assert live_dict.get(name, _MISSING) is original` 两边都是同一个 `_MISSING` 哨兵，
`is` 成立 ⇒ **自我认证**，泄漏检查看不见这次删除。

治：还原面直接看 `live_dict`——进门那一刻先给每一枚 `name` 拍一张值快照 `before_values`，
窗尾「场上原本没有的名字」才允许 pop，本来在场上的一律装回窗那一枚对象。`live_view` 只留作码体指纹那半格用。

## 三、乙腿：窗尾「再 exec 一遍盘上的字」救不回身份（两版治法，第一版已作废）

**病根**：`tests/_temp_edit_overlay.py::install_source` 把整份码体 exec 进**同一个**模块对象的
`__dict__`（`importlib.reload` 本来也同形）。于是

1. 每一枚顶层类都是**新对象** ⇒ 模块属性 `SessionRegistry` 换了，而 `chat.session_registry` 那枚实例仍指着旧类；
2. 顶层那行 `session_registry = SessionRegistry()` **又跑了一遍** ⇒ 模块属性上的单例也是新对象。

窗尾那一次 exec 只会再造第三枚，救不回来。r499 的三枚牙报的就是这个形状
（`assert <class '…SessionRegistry'> is <class '…SessionRegistry'>` 两枚同名同模块的类对象，`is` 为假）。

**第一版（作废）**：在 `install_source` 里补两道守卫——把新身体逐枚 `setattr` 进旧类
（`_reuse_class_identities`）、把「赋值行源码一字没改」的模块级实例换回场上那一枚（`_reuse_live_instances`），
另配 `previous_source()` + `_INSTALLED`（`WeakKeyDictionary`）记住这枚模块上一次真跑的是哪份字节。
并树后门里读数 **115 failed / 9574 passed / 10 errors**（815–888 s）。两处硬伤都是原理性的，不是调参能救：

- 零参 `super()` 读的是码体里那个 `__class__` 格，把新类的方法定进旧类，第一次 `super()` 就
  `TypeError: super(type, obj): obj must be an instance or subtype of type`；
- 模块属性上那枚外部 `APIRouter()` 实例被「换回旧值」之后，重跑时对它的 `router.get(...)` 注册静默丢失——
  那一行正是刀要执行的东西，替它留旧值＝造一枚假绿。

`0dc40b1` 在历史里留着当推翻记录（不删），`fa1cf3e` 换成第二版。今天树上 `_reuse_*` / `previous_source`
三个名字全部不存在（tests/ · app/ · scripts/ 逐档零命中）。

**第二版（今天树上的形态）**：窗尾**根本不再 exec**。`ShadowEdit.__enter__` 在 `install_source(mutant)`
之前先 `self._live_snapshot = dict(module.__dict__)`；`__exit__` 调 `restore_namespace(module, snapshot)`——
快照里没有的名字整片摘掉（变异新造的那些），在快照里的一律装回进门那一刻那一枚对象，返回值是
「身份对不上」的名字清单，交给 `info["identity_diverged"]`。零类手术、零实例手术、模块体一遍都不多跑
⇒ 身份与值都是原来那一枚。

牙：`tests/test_r553_counter_evidence_teeth.py`（7 枚，**7 passed in 5.11 s**）。点名三枚关键的——
`test_the_window_tail_reexecutes_nothing` 计数 `install_source`，整扇窗只准命中一次（进门那次）；
`test_names_invented_by_the_mutant_do_not_survive_the_window` 钉新造名字不留在场上；
`test_a_crashed_window_still_hands_the_module_back_untouched` 钉开窗就抛也要倒回。

## 四、读数（全部总控主树亲跑，串行、`-p no:cacheprovider`）

| 命令 | 修前 | 修后 |
|---|---|---|
| `r353 + r301` | 4 failed（`NameError: PDF_DEGRADATION_REASON_GROUP_CAP`） | **62 passed**（与 `r466` 同跑） |
| `r495 + r499` | 3 failed | **21 passed** |
| `r387 + r455×2 + r400 + r492`（坐标重锚后） | 21 failed | **95 passed** |
| 新钉 `tests/test_r553_counter_evidence_teeth.py` | — | **7 passed in 5.11 s** |
| 16 枚本族件（r466 + r553 + 八枚影子窗 + r48/r495/r497/r499 + r470/r471/r472/r478） | `[r48]` 1 failed；同进程并跑另红一枚 r303 | dirty **309 passed / 1 xfailed / 164.44 s**；`f83372d` 干净树复跑 **309 passed / 1 xfailed / 124.21 s** |

🔴 两遍数字都得交：dirty 与干净树同名件各跑一遍、文件清单逐枚点名（`fa1cf3e` 当时就漏了第二遍，
门里剩一枚红混到今天）。

## 五、本族同一天又量出三枚（10-01 第二班，并树 `f83372d`）

1. **红的是登记，不是泄漏**：`[r48]` 那格 `len(identity_diff(before, after)) == len(before["objects"])`
   量的正是「窗尾把码体重跑了一遍」这件事本身；第二版之后 r48 出窗不再换身份 ⇒ 它必然红。在册姿势改名
   `live_exec_snapshot`，出窗这一侧九枚同判，另留两格降级哨（`execs_module` 仍须为真 ＋ 窗内「整片换身份」
   那格原样不动）——谁把这扇窗悄悄降级成影子改绑，本件当场红。顺带补强一格：出窗后**本扇窗点名的那几枚
   绑定**必须回到盘上那份码（旧口径只有 r48 一支有这条，八枚影子窗一辈子没被量过；而 `diff_view(before, after)`
   只相对开窗前，快照本身若更早沾了变异它照样绿）。只量点名的那几枚，逐枚比整片会把别枚件在导入期
   合法换过的把手读成假红。
2. **尺子的编法**：`test_r466…` 文件头写着 `from __future__ import annotations`，而 `compiled_view` 原本走
   不带 `dont_inherit` 的 plain `compile()` ⇒ 那一位 future 顺调用帧掺进字节码（3.12+ 连 `__annotate__`
   子码体的形状一起变）。拿它量「导入机器编出来的那份」：10-01 现取 **chat 139/139、data 19/19 枚整片假差**；
   只把 `co_flags` 从指纹里摘掉仍剩 4 枚真差（`_authorize_queue_task` / `_reap_agent_worker` / `approve` /
   `delete_document`）。⇒ 新增 `compiled_view(..., dont_inherit=True)`，只给「以盘上那份码当尺子」的格用；
   窗内比影子副本那两格维持继承帧的编法（`install_source` 同为继承帧，两边同形）。
   notifications 8、sources 9、inbox 7 枚本来就 0 差，不受影响。
3. **判据③ 的自证本体自己是加害者**：它收尾用 `install_source(disk_text)`，只救码不救身份——造出第二枚
   `sources.alert_candidates`，而消费者 `app.notifications.inbox` 手里那枚还是旧的 ⇒ 同 worker 里排在其后的
   `test_r303_notification_pins.py::test_the_counter_evidence_window_touches_no_tracked_file` 当场红。
   **在未经改动的 HEAD 上把这两枚件放进同一进程必红（实取 2 failed）**，门里不炸只是 `--dist loadfile`
   的侥幸，与乙腿同一族形状。⇒ 改成 `overlay.restore_namespace` 按快照倒回，并补一枚「身份也得倒回去」的断言。

## 六、未达的格子（明写，不洗）

- 只治了**这三族形状**（常量被 pop、类与单例被换、自证收尾换身份）。`execs_module = True` 的五扇窗
  （r472 两扇、r478、r48、r495）今天不再漏身份，但它们仍走「进门整份码体重跑」这条旧姿势：
  `install_mutation`（只换变了的那几枚绑定）才是新口径。迁不迁是下一班的账，
  **别把「不漏了」读成「姿势统一了」**。
- `tests/test_r48_headline_card_lands_on_the_wire.py::_reload()`（自己那枚 `finally` 里无条件重跑一遍盘上的字）
  与它类 docstring 里那句「退出再 exec 回盘上的字」——本件只登记不代改，已另立候选号（跟进单 §141）。
- 顶层实例的状态若由**导入期副作用**决定，快照倒回救得回对象身份、救不回那一格状态；
  今天两枚受害模块没有这种形状，未证到其他树。
- 门里的分法是 `loadfile` 决定的，加一枚测试件就可能换配对 ⇒ 这类病**必然**还会以「换个号就红」的形状回来。
- 订正一笔旧账：上面那句「115 failed」不能全记在 v1 治法头上——同一时间窗里本席还在跑另一枚并发 pytest，
  两笔污染叠在一起。v1 那两处硬伤确实存在（§三已写明），但那 115 枚不是它单独造的数。
