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

## 三、乙腿：重跑码体会换掉顶层类与顶层实例的身份

`tests/_temp_edit_overlay.py::install_source` 把整份码体 exec 进活模块的 `__dict__`（与 `importlib.reload` 同形）。
于是：

1. 每一枚顶层类都是**新对象** ⇒ 模块属性 `SessionRegistry` 换了，而 `chat.session_registry` 这枚实例仍指着旧类；
2. 顶层那行 `session_registry = SessionRegistry()` **又跑了一遍** ⇒ 模块属性上的单例也是新对象。

窗尾那一次 exec 只会再造第三枚类/实例，救不回来。r499 的三枚牙报的就是这个形状
（`assert <class 'app.storage.sessions.SessionRegistry'> is <class 'app.storage.sessions.SessionRegistry'>` 成立却 `is` 为假——两枚同名同模块的类对象）。

治（两道守卫，都在 `install_source` 里，紧跟 exec 之后）：

- `_reuse_class_identities`：把新身体逐枚 `setattr` 进旧类、旧类上多出来的属性 `delattr`、模块属性指回旧类。
  🔴 只在**元类与基类都没变**时做——换了基类就不是重跑，宁可换身份也不伪造一枚挂旧名的假类。
- `_reuse_live_instances`：只把**赋值那行源码一字没改**的模块级实例换回场上那一枚（比对 AST `ast.unparse` 的源码，
  不比对象状态：`threading.Lock()` 这类每次都不同的东西拿状态比会误伤）。赋值行变了就绝不插手——
  那一行可能正是刀要执行的东西，替它留旧值＝造一枚假绿。
- `previous_source()` + `_INSTALLED`（`WeakKeyDictionary`）：记住「这枚模块上一次真跑的是哪份字节」。
  窗尾的对照文本必须是**影子副本的变异版**，拿盘上文本当对照就会把「赋值行变了」误判成「没变」。

## 四、读数（全部总控主树亲跑，串行、`-o addopts=`、`-p no:randomly`）

| 命令 | 修前 | 修后 |
|---|---|---|
| `r353 + r301` | 4 failed（`NameError`） | **62 passed**（与 `r466` 同跑） |
| `r495 + r499` | 3 failed | **21 passed** |
| `r387 + r455×2 + r400 + r492`（坐标重锚后） | 21 failed | **95 passed** |
| 新钉 `tests/test_r553_counter_evidence_teeth.py` | — | **11 passed in 5.30 s** |
| 同一枚文件，摘掉两道守卫（`%TEMP%\r553_kill_guards.py` 插件把两个 `_reuse_*` 换成空实现） | — | **4 failed / 7 passed** ⇒ 两道守卫是活的，不是装饰 |

## 五、未达的格子（明写，不洗）

- 本席只治了**这两族形状**（常量被 pop、类与单例被换）。`execs_module = True` 的五扇窗（r472 两扇、r478、r48、r495）
  今天不再漏身份，但它们仍走「整份码体重跑」这条旧姿势：`install_mutation`（只换变了的那几枚绑定）才是新口径。
  迁不迁是下一班的账，**别把「不漏了」读成「姿势统一了」**。
- 顶层实例的状态若由**导入期副作用**决定（而不是那行赋值），守卫会照留旧对象——今天两枚受害模块没有这种形状，
  未证到其他树。
- 跨 worker 的泄漏（不同进程）本就不存在；本件只处理同 worker 内的顺序污染。
- 门里的分法是 `loadfile` 决定的，加一枚测试件就可能换配对 ⇒ 这类病**必然**还会以「换个号就红」的形状回来。
`R555`（门自选不看提交电荷）与「正文裸坐标没人咬」（`r387` §1 里那枚 `:4088` 至今指向一行空行，尺子只咬
`文件名:行号` 全形，裸 `:NNNN` 不在射程内）两枚候选仍未派。